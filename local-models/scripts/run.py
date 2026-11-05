"""One resident Qwen model, local authenticated API, optional interactive console."""

import argparse
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error

from client import infer, json_request
from common import (
    MODEL_NAMES,
    STATE,
    config,
    credentials,
    model_profile,
    no_link,
    verify_install,
)
from process_guard import ProcessGuard


class Server:
    def __init__(self, settings):
        self.settings = dict(settings)
        self.profile = model_profile(settings)
        self.process = None
        self.guard = None
        self.reader = None
        self.lock = None
        self.locked = False
        self.key = None
        self.metrics = {"offloaded_layers": 0, "total_layers": None, "model_loads": 1}

    def start(self):
        started = time.perf_counter()
        key_path, self.key = credentials()
        lock_path = STATE / "instance.lock"
        if lock_path.exists():
            no_link(lock_path)
        self.lock = lock_path.open("a+b")
        self.lock.seek(0)
        import msvcrt

        try:
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            self.locked = True
        except OSError:
            self.lock.close()
            self.lock = None
            raise RuntimeError("An instance is already running. Use chat.bat to connect.") from None
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", self.settings["port"]))
            except OSError:
                raise RuntimeError("Configured port is in use; no existing process was stopped") from None
        print("Verifying local model and runtime...", flush=True)
        executable = verify_install(self.settings["gpu_enabled"], self.settings)
        if self.settings["gpu_enabled"]:
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits",
                        "--id=" + str(self.settings["gpu_device_index"]),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                available = int(result.stdout.strip()) if result.returncode == 0 else 0
            except (OSError, ValueError, subprocess.TimeoutExpired):
                available = 0
            if available == 0:
                raise RuntimeError("Selected NVIDIA GPU is unavailable. Set gpu_enabled=false for CPU.")
            if self.settings["gpu_layers"] == 99 and available < self.profile["minimum_free_vram_mib"]:
                raise RuntimeError(
                    "Full GPU mode needs free VRAM. Stop other GPU models or explicitly lower gpu_layers/use CPU."
                )
        args = self.arguments(executable, key_path)
        environment = {
            k: v for k, v in os.environ.items() if not k.startswith(("LLAMA_", "GGML_", "HF_", "CUDA_"))
        }
        environment["HF_HUB_OFFLINE"] = "1"
        if self.settings["gpu_enabled"]:
            environment["CUDA_VISIBLE_DEVICES"] = str(self.settings["gpu_device_index"])
        else:
            environment["CUDA_VISIBLE_DEVICES"] = "-1"
        self.process = subprocess.Popen(
            args,
            cwd=executable.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.guard = ProcessGuard(self.process)
        self.reader = threading.Thread(target=self.read_metrics, daemon=True)
        self.reader.start()
        print(f"Loading {self.profile['name']} once; waiting for warmup...", flush=True)
        deadline = time.monotonic() + self.settings["startup_timeout_seconds"]
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Inference server exited during startup (code {self.process.returncode}); check GPU memory/runtime"
                )
            try:
                health = json_request(self.settings["port"], "/health", timeout=1)
                if health.get("status") == "ok":
                    models = json_request(self.settings["port"], "/v1/models", self.key, timeout=2)
                    if not any(m.get("id") == self.profile["alias"] for m in models.get("data", [])):
                        raise RuntimeError("Unexpected model at local endpoint")
                    self.validate_device()
                    self.metrics.update(
                        startup_seconds=time.perf_counter() - started,
                        pid=self.process.pid,
                        device="cuda" if self.settings["gpu_enabled"] else "cpu",
                    )
                    print(
                        f"Ready: {self.metrics['device']}; {self.metrics['offloaded_layers']} layers on GPU; "
                        f"API http://127.0.0.1:{self.settings['port']}/v1",
                        flush=True,
                    )
                    return self
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(0.15)
        raise RuntimeError("Model startup timed out")

    def validate_device(self):
        actual, total = self.metrics["offloaded_layers"], self.metrics["total_layers"]
        if self.settings["gpu_enabled"]:
            if total is None or total <= 0 or actual != min(self.settings["gpu_layers"], total):
                raise RuntimeError("Native GPU offloading did not match the requested layer count")
        elif actual != 0:
            raise RuntimeError("CPU mode unexpectedly reported GPU offloading")

    def arguments(self, executable, key_path):
        s = self.settings
        return [
            str(executable),
            "--model",
            str(self.profile["path"]),
            "--alias",
            self.profile["alias"],
            "--host",
            "127.0.0.1",
            "--port",
            str(s["port"]),
            "--cors-origins",
            f"http://127.0.0.1:{s['port']}",
            "--api-key-file",
            str(key_path),
            "--offline",
            "--no-webui",
            "--no-agent",
            "--no-context-shift",
            "--no-slots",
            "--parallel",
            "1",
            "--ctx-size",
            str(s["context_size"]),
            "--predict",
            str(s["max_tokens"]),
            "--threads",
            str(s["cpu_threads"]),
            "--threads-batch",
            str(s["cpu_threads"]),
            "--batch-size",
            "256",
            "--ubatch-size",
            "128",
            "--cache-ram",
            str(s.get("prompt_cache_mib", 256)),
            "--gpu-layers",
            str(s["gpu_layers"] if s["gpu_enabled"] else 0),
            "--device",
            "CUDA0" if s["gpu_enabled"] else "none",
            "--fit",
            "off",
            "--flash-attn",
            "on" if s["gpu_enabled"] else "off",
            "--jinja",
            "--chat-template-kwargs",
            json.dumps({"enable_thinking": False}),
            "--reasoning",
            "off",
            "--timeout",
            str(s["request_timeout_seconds"]),
            "--log-colors",
            "off",
            "--verbosity",
            "4",
        ]

    def read_metrics(self):
        # Consume/discard native logs. Never persist or echo prompts, keys or model responses.
        while line := self.process.stdout.readline(65536):
            text = line.decode("utf-8", errors="replace")
            match = re.search(r"offloaded (\d+)/(\d+) layers to GPU", text)
            if match:
                self.metrics["offloaded_layers"], self.metrics["total_layers"] = map(int, match.groups())
            match = re.search(r"CUDA0.*?(model|compute|KV) buffer size\s*=\s*([0-9.]+) MiB", text)
            if match:
                self.metrics[match.group(1).lower() + "_buffer_mib"] = float(match.group(2))

    def close(self):
        try:
            # Release the job even if terminate/wait fails; it independently owns the child.
            try:
                if self.process is not None and self.process.poll() is None:
                    self.process.terminate()
                    self.process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                if self.guard:
                    self.guard.close()
                    self.guard = None
            if self.process is not None:
                if self.process.poll() is None:
                    try:
                        self.process.kill()
                    except OSError:
                        pass  # The job may already have stopped it. Confirm by waiting.
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError("Could not confirm inference process stopped") from None
                if self.reader:
                    self.reader.join(timeout=2)
                    if self.reader.is_alive():
                        # Closing a buffered pipe with another reader can block indefinitely.
                        raise RuntimeError("Inference log reader did not stop")
                    self.reader = None
                if self.process.stdout:
                    self.process.stdout.close()
        finally:
            if self.lock:
                import msvcrt

                try:
                    if self.locked:
                        self.lock.seek(0)
                        msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
                finally:
                    self.lock.close()
                    self.lock = None
                    self.locked = False

    def __enter__(self):
        try:
            return self.start()
        except BaseException:
            self.close()
            raise

    def __exit__(self, *_):
        self.close()


def chat(settings, key):
    print("Type a message in English or Hindi. /reset clears history; /quit exits.")
    messages = [{"role": "system", "content": settings["system_prompt"]}]
    while True:
        try:
            text = input("\nYou: ").strip()
        except EOFError:
            return
        if text == "/quit":
            return
        if text == "/reset":
            messages = messages[:1]
            print("Conversation cleared.")
            continue
        if not text:
            continue
        if len(text) > 4000:
            print("Please keep each message under 4,000 characters.")
            continue
        proposed = [*messages, {"role": "user", "content": text}]
        try:
            print("Qwen: ", end="", flush=True)
            result = infer(settings, key, proposed, lambda part: print(part, end="", flush=True))
            print(f"\n[{result['total_seconds']:.2f}s]")
            if result["finish_reason"] == "length":
                print("[Response reached the configured token limit.]")
            messages = [*proposed, {"role": "assistant", "content": result["text"]}]
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError):
            print(
                "\nRequest failed or context is full. Use /reset or shorten the message. It was not retried."
            )


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--server",
        action="store_true",
        help="Keep the local API running without interactive chat",
    )
    group.add_argument(
        "--connect",
        action="store_true",
        help="Chat using the already running local server",
    )
    parser.add_argument("--cpu", action="store_true", help="Explicit CPU mode for this launch")
    parser.add_argument(
        "--gpu-layers", type=int, help="GPU layers for this launch (1-99); config is unchanged"
    )
    parser.add_argument("--model", choices=MODEL_NAMES, help="Model for this launch; overrides config")
    args = parser.parse_args()
    if args.connect and args.cpu:
        parser.error("--cpu selects a new server; it cannot change an already running instance")
    if args.gpu_layers is not None and (args.connect or args.cpu or not 1 <= args.gpu_layers <= 99):
        parser.error("--gpu-layers requires a new GPU server and a value from 1 to 99")
    settings = config()
    if args.model:
        settings["model"] = args.model
    if args.cpu:
        settings["gpu_enabled"] = False
    if args.gpu_layers is not None:
        if not settings["gpu_enabled"]:
            parser.error("--gpu-layers requires gpu_enabled=true in config")
        settings["gpu_layers"] = args.gpu_layers
    if args.connect:
        _, key = credentials()
        models = json_request(settings["port"], "/v1/models", key)
        if not any(m.get("id") == model_profile(settings)["alias"] for m in models.get("data", [])):
            raise RuntimeError("The configured local model is not running")
        chat(settings, key)
        return
    with Server(settings) as server:
        if args.server:
            print(
                "Local API running. Press Ctrl+C to stop and release the model.",
                flush=True,
            )
            while server.process.poll() is None:
                time.sleep(0.5)
            raise RuntimeError("Inference process stopped")
        chat(settings, server.key)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped; model released.")
    except (OSError, ValueError, RuntimeError) as exc:
        # Do not print raw transport errors: they may contain request/server details.
        print(
            "Could not start local inference: "
            + (str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__)
        )
        raise SystemExit(1) from None
