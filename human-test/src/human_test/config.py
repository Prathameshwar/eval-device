"""Desktop environment and storage defaults for the shared runtime."""

from pathlib import Path

from pydantic_settings import SettingsConfigDict
from training_client.config import Settings as ClientSettings

ROOT = Path(__file__).resolve().parents[2]


class Settings(ClientSettings):
    model_config = SettingsConfigDict(
        env_prefix="HUMAN_", env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )
    app_root: Path = ROOT
    session_sync_background: bool = True
