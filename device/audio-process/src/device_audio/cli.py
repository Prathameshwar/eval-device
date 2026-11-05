import argparse
import json
import logging
import math
import secrets
import sys
import time
import wave
from pathlib import Path

from .audio import SAMPLE_RATE, AudioChunk
from .config import MODEL_NAMES, VOSK_LANGUAGES, Settings
from .recording_store import no_link, private_directory


def init_local() -> None:
    path = Path(".env")
    for parent in reversed(path.absolute().parents):
        no_link(parent)
    token_map = json.dumps({"pi-1": secrets.token_urlsafe(32)})
    content = (
        "# Private local client credentials. Do not commit or share this file.\n"
        f"AUDIO_CLIENT_TOKENS='{token_map}'\n"
        "AUDIO_HOST=127.0.0.1\nAUDIO_PORT=8765\n"
        "AUDIO_MODEL_NAME=large-v3\nAUDIO_CPU_THREADS=4\nAUDIO_BEAM_SIZE=1\n"
        "AUDIO_GPU_ENABLED=false\nAUDIO_GPU_DEVICE_INDEX=0\n"
        "AUDIO_CONSOLE_OUTPUT=true\n"
        "AUDIO_MODEL_LOAD_TIMEOUT_SECONDS=180\nAUDIO_INFERENCE_SHUTDOWN_SECONDS=5\n"
        "AUDIO_RECORDING_ENABLED=true\nAUDIO_RECORDING_DIR=.recordings\n"
        "AUDIO_RECORDING_MAX_BYTES=1000000000\nAUDIO_RECORDING_RETENTION_HOURS=168\n"
        "AUDIO_RECORDING_RETRY_ATTEMPTS=3\nAUDIO_RECORDING_RETRY_DELAY_SECONDS=0.05\n"
        "AUDIO_CALLBACK_RETRY_ATTEMPTS=3\nAUDIO_CALLBACK_RETRY_DELAY_SECONDS=0.2\n"
        "# AUDIO_MODEL_PATH=.models/large-v3\n"
        "# AUDIO_CALLBACK_URL=https://your-selected-receiver.example/transcripts\n"
        "# AUDIO_CALLBACK_TOKEN=\n"
        "# For Wi-Fi: supply a trusted TLS certificate/key, then set AUDIO_HOST=0.0.0.0.\n"
        "# AUDIO_TLS_CERT=path/to/server-cert.pem\n# AUDIO_TLS_KEY=path/to/server-key.pem\n"
    )
    with path.open("x", encoding="utf-8") as target:
        private_directory(path)
        target.write(content)
    print("Created private .env. Client token was not printed. Download a model before starting.")


def benchmark(settings: Settings, audio_path: Path, language: str, output: Path | None) -> None:
    from .engine import create_engine

    if language not in settings.supported_languages:
        raise ValueError("selected model requires an explicit supported language")
    with wave.open(str(audio_path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, SAMPLE_RATE):
            raise ValueError("benchmark requires mono 16 kHz PCM16 WAV")
        frames = source.getnframes()
        if not 0 < frames <= SAMPLE_RATE * 30:
            raise ValueError("benchmark audio must contain 0-30 seconds of speech")
        pcm = source.readframes(frames)
        if len(pcm) != frames * 2:
            raise SystemExit("WAV data is truncated")
    before = time.perf_counter()
    engine = create_engine(settings)
    load_seconds = time.perf_counter() - before
    chunk = AudioChunk(pcm, 0, frames)
    started = time.perf_counter()
    result = engine.transcribe(chunk, language)
    elapsed = time.perf_counter() - started
    metrics = {
        "model": settings.model_name,
        "engine": settings.engine_name,
        "compute_type": settings.compute_type,
        "device": settings.inference_device,
        "gpu_enabled": settings.gpu_enabled,
        "gpu_device_index": settings.gpu_device_index if settings.gpu_enabled else None,
        "cpu_threads": settings.effective_cpu_threads,
        "beam_size": None if settings.streaming else settings.beam_size,
        "decoding_method": "greedy_search" if settings.streaming else "whisper_beam_search",
        "audio_seconds": frames / SAMPLE_RATE,
        "load_and_warmup_seconds": round(load_seconds, 3),
        "inference_seconds": round(elapsed, 3),
        "real_time_factor": round(elapsed / (frames / SAMPLE_RATE), 4),
        "detected_language": result.language,
        "transcript_characters": len(result.text),
        "note": "Single recorded clip; not a live-stream latency or accuracy guarantee.",
    }
    rendered = json.dumps(metrics, indent=2, ensure_ascii=False)
    if output:
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Standalone local audio transcription")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-local", help="create .env with a random client token")
    commands.add_parser("serve", help="load/warm one model and start the standalone API")
    download = commands.add_parser("download-model", help="explicitly download a model; requires Internet")
    download.add_argument("--model", choices=MODEL_NAMES, default="large-v3")
    download.add_argument("--output-dir", type=Path)
    download.add_argument(
        "--vosk-source",
        choices=("official", "huggingface"),
        default="official",
        help="Vosk only: publisher or pinned Hugging Face mirror",
    )
    bench = commands.add_parser("benchmark", help="measure a local 16 kHz mono PCM16 WAV clip")
    bench.add_argument("--audio", type=Path, required=True)
    bench.add_argument("--language", choices=("auto", "hi", "en"), default="auto")
    bench.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "init-local":
        try:
            init_local()
        except FileExistsError:
            parser.exit(1, ".env already exists; it was not overwritten.\n")
        except Exception:
            parser.exit(1, "Could not create private settings; check directory permissions.\n")
        return
    if args.command == "download-model":
        from faster_whisper.utils import download_model

        if args.vosk_source != "official" and args.model not in VOSK_LANGUAGES:
            parser.error("--vosk-source applies only to Vosk models")
        directory = args.output_dir or Path(".models") / args.model
        try:
            if args.model == "nemotron-3.5-asr-streaming-0.6b":
                from .model_download import download_nemotron

                download_nemotron(directory)
            elif args.model == "whisper-medical-v1":
                from .medical_download import download_medical

                download_medical(directory)
            elif args.model in VOSK_LANGUAGES:
                from .vosk_download import download_vosk

                download_vosk(args.model, directory, source=args.vosk_source)
            else:
                download_model(args.model, output_dir=str(directory))
        except FileExistsError:
            parser.exit(1, "Model directory already exists; choose a new --output-dir.\n")
        except RuntimeError:
            if args.model == "whisper-medical-v1":
                parser.exit(
                    1, "Whisper Medical setup failed; run setup-medical.bat and check network access.\n"
                )
            parser.exit(
                1, "Model download failed; check connectivity, trusted certificates and disk space.\n"
            )
        except Exception:
            parser.exit(
                1, "Model download failed; check connectivity, trusted certificates and disk space.\n"
            )
        print(f"Model {args.model} downloaded. Serving never downloads models automatically.")
        return
    try:
        settings = Settings()
    except ValueError:
        parser.exit(1, "Invalid AUDIO_* settings; check .env and the configuration reference.\n")
    if args.command == "benchmark":
        benchmark(settings, args.audio, args.language, args.output)
        return
    import uvicorn

    from .app import create_app

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("device_audio").info("loading local model; readiness follows warmup")
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=1,
        access_log=False,
        proxy_headers=False,
        ws="websockets",
        ws_max_size=settings.max_frame_bytes,
        ws_max_queue=4,
        ws_per_message_deflate=False,
        timeout_graceful_shutdown=math.ceil(settings.inference_shutdown_seconds),
        ssl_certfile=str(settings.tls_cert) if settings.tls_cert else None,
        ssl_keyfile=str(settings.tls_key) if settings.tls_key else None,
    )


if __name__ == "__main__":
    main()
