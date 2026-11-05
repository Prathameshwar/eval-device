"""Cloud synthesis through existing device processing; provider keys stay on the platform."""

import io
import json
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from training_contracts.privacy import no_link, private_directory, private_tree

from .media import media_url
from .speech import ManagerPlayback, Unavailable
from .telemetry import heartbeat


class Journal:
    def __init__(self, directory):
        root = Path(directory).absolute()
        private_tree(root)
        self.path = root / "synthesis.sqlite3"
        if self.path.exists() or self.path.is_symlink():
            no_link(self.path)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, run TEXT, state TEXT, stamp REAL)"
            )
        private_directory(self.path)

    def write(self, key, state, run=None):
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM requests WHERE stamp < ?", (time.time() - 86400,))
            if (
                not db.execute("SELECT 1 FROM requests WHERE id=?", (key,)).fetchone()
                and db.execute("SELECT count(*) FROM requests").fetchone()[0] >= 1000
            ):
                raise Unavailable("Synthesis journal is full")
            db.execute(
                "INSERT INTO requests VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "run=coalesce(excluded.run, requests.run), state=excluded.state",
                (key, run, state, time.time()),
            )

    def recent(self):
        with sqlite3.connect(self.path) as db:
            return [
                {"request_key": key, "run_id": run, "state": state}
                for key, run, state in db.execute(
                    "SELECT id, run, state FROM requests ORDER BY stamp DESC LIMIT 20"
                )
            ]


class PlatformVoice:
    def __init__(self, settings, interrupted, *, transport=None):
        self.settings, self.interrupted, self.transport = settings, interrupted, transport
        self.config = SimpleNamespace(sample_rate=22050)

    def synthesize(self, text, _tuning=None):
        settings = self.settings
        origin = settings.pms_url.rstrip("/")
        journal = Journal(settings.app_root / "synthesis")
        key = str(uuid4())
        deadline = time.monotonic() + min(180, settings.timeout_seconds)
        with httpx.Client(
            trust_env=False, follow_redirects=False, timeout=10, transport=self.transport
        ) as http:

            def call(method, path, payload=None):
                if self.interrupted.is_set() or time.monotonic() > deadline:
                    raise Unavailable("Synthesis stopped")
                with http.stream(
                    method,
                    origin + path,
                    json=payload,
                    headers={"Authorization": "Bearer " + settings.pms_token.get_secret_value()},
                ) as response:
                    raw = bytearray()
                    for part in response.iter_bytes():
                        raw.extend(part)
                        if len(raw) > 131072 or self.interrupted.is_set() or time.monotonic() > deadline:
                            raise Unavailable("Invalid platform response")
                    if response.status_code not in {200, 202}:
                        raise Unavailable("Platform synthesis is unavailable")
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise Unavailable("Invalid platform response")
                    return value

            configuration = call("GET", "/api/v1/device/config")
            output = configuration["settings"]["audio_output"]
            if not output.get("enabled") or output.get("execution_mode", output.get("mode")) != "cloud":
                raise Unavailable("No cloud output model is assigned")
            call(
                "POST",
                "/api/v1/device/heartbeat",
                heartbeat(configuration),
            )
            # Persist before submission. Unknown outcomes are inspected, never automatically resubmitted.
            journal.write(key, "unknown")
            result = call(
                "POST",
                "/api/v1/device/runs",
                {
                    "request_key": key,
                    "operation": "audio.synthesize",
                    "text": text,
                    "profile_revision_id": configuration["profile_revision_id"],
                    "playback": False,
                },
            )
            run = result["run"]
            identity = str(run["id"])
            journal.write(key, "submitted", identity)
            while run["status"] not in {"succeeded", "failed", "cancelled", "expired", "unknown"}:
                if self.interrupted.wait(0.25):
                    raise Unavailable("Playback was cancelled")
                run = call("GET", "/api/v1/device/runs/" + identity)
            if run["status"] != "succeeded":
                journal.write(key, run["status"], identity)
                raise Unavailable("Cloud synthesis did not complete")
            directory = call("GET", f"/api/v1/organizations/{settings.organization_id}/runs/{identity}/media")
            item = next((item for item in directory["items"] if item["role"] == "output"), None)
            if item is None:
                raise Unavailable("Synthesis output is unavailable")
            media = call("POST", f"/api/v1/device/runs/{identity}/media/{item['index']}/access")
            address = media_url(media["url"], origin)
            # A signed URL is itself authorization. Never forward the device credential to storage.
            with httpx.Client(
                trust_env=False, follow_redirects=False, timeout=10, transport=self.transport
            ) as storage:
                with storage.stream("GET", address) as response:
                    if response.status_code != 200:
                        raise Unavailable("Cannot download synthesized audio")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 8000000 or self.interrupted.is_set() or time.monotonic() > deadline:
                            raise Unavailable("Synthesized audio exceeded its budget")
            journal.write(key, "completed", identity)
        import av

        pcm = bytearray()
        with av.open(io.BytesIO(raw)) as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=self.config.sample_rate)
            for frame in container.decode(audio=0):
                for output in resampler.resample(frame):
                    pcm.extend(output.to_ndarray().tobytes())
                    if len(pcm) > 4000000 or self.interrupted.is_set() or time.monotonic() > deadline:
                        raise Unavailable("Decoded audio exceeded its budget")
            for output in resampler.resample(None):
                pcm.extend(output.to_ndarray().tobytes())
        if not pcm or len(pcm) > 4000000:
            raise Unavailable("Invalid synthesized audio")
        for start in range(0, len(pcm), 32768):
            yield SimpleNamespace(audio_int16_bytes=bytes(pcm[start : start + 32768]))


class RoutedPlayback(ManagerPlayback):
    """Use the currently assigned platform output route, keeping shared interruption/gates."""

    def __init__(self, settings, route, inference=None):
        super().__init__(inference)
        self.settings, self.route = settings, route
        local_catalogue = self.catalogue

        def catalogue():
            if not self.cloud():
                return local_catalogue()
            revision = (self.route() or {}).get("configuration_hash", "")[:16]
            return [
                {
                    "key": "platform." + language + "." + revision,
                    "label": "Platform output",
                    "language": language,
                    "gender": "male",
                    "default": True,
                }
                for language in settings.language_choices
            ]

        self.catalogue = catalogue

    def cloud(self):
        route = self.route() or {}
        output = route.get("platform_media", {}).get("audio_output", {}).get("settings", {})
        return output.get("enabled") and output.get("execution_mode", output.get("mode")) == "cloud"

    def voice(self, key, spec):
        if key.startswith("platform.") and self.cloud():
            return PlatformVoice(self.settings, self._interrupt)
        return super().voice(key, spec)

    def warm(self, language, gender="male", preferred=None):
        return (
            self.load(language, gender, preferred)
            if self.cloud()
            else super().warm(language, gender, preferred)
        )
