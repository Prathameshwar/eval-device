import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict
from training_client.config import Settings as SharedSettings
from training_client.connection import connection_values, read_connection
from training_contracts.privacy import no_link, private_tree


class Settings(SharedSettings):
    model_config = SettingsConfigDict(env_prefix="PI_TEST_", extra="forbid", hide_input_in_errors=True)
    app_root: Path = Path("/var/lib/pi-test")
    control_dir: Path = Path("/run/pi-test")
    use_pms_models: bool = True
    session_sync_background: bool = False
    session_sync_max_bytes: int = Field(512 * 1024 * 1024, ge=1048576, le=107374182400)
    video_quota_mb: int = Field(512, ge=64, le=102400)
    camera_backend: Literal["none", "usb", "csi"] = "none"
    camera_width: int = Field(640, ge=160, le=1920)
    camera_height: int = Field(480, ge=120, le=1080)
    camera_fps: int = Field(10, ge=1, le=30)
    min_free_mb: int = Field(256, ge=64, le=10240)
    readiness_seconds: int = Field(15, ge=2, le=300)
    stream_audio: bool = False
    microphone_strict: bool = True
    listen_on_begin: bool = False
    camera_device: str | None = Field(None, max_length=512)
    processing_video_seconds: int = Field(10, ge=1, le=30)

    @model_validator(mode="after")
    def unattended(self):
        if self.session_sync_background:
            raise ValueError("Pi uploads must be owned by the service")
        if not self.microphone_strict:
            raise ValueError("Pi microphone identity must be strict")
        if self.camera_device and (
            self.camera_backend != "usb" or not self.camera_device.startswith("/dev/")
        ):
            raise ValueError("A stable USB camera path must be under /dev")
        if not self.control_dir.is_absolute():
            raise ValueError("control_dir must be absolute")
        return self


def load(path: Path, *, credentials=True):
    no_link(path)
    if path.stat().st_size > 32768:
        raise ValueError("Configuration exceeds its limit")
    with path.open("rb") as source:
        values = tomllib.load(source)
    settings = Settings(**values)
    if credentials:
        saved = read_connection(settings.app_root / "connection.json")
        if saved:
            for name, value in connection_values(saved).items():
                if name in type(settings).model_fields:
                    setattr(settings, name, value)
            # Validate assignment, including SecretStr and UUID conversion.
            settings = Settings(**settings.model_dump())
    return settings


def private_dir(path):
    path = Path(path)
    private_tree(path)
    if os.name != "nt":
        if path.stat().st_uid != os.getuid():
            raise ValueError("Service directory belongs to another account")
        path.chmod(0o700)
    return path
