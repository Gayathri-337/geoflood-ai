"""
GeoFlood AI backend - settings.

Values are read from environment variables or from the .env file in the project root.
DATABASE_URL and SECRET_KEY are required; the app refuses to start without them.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_name: str = "GeoFlood AI API"
    app_version: str = "0.5.0"
    database_url: str
    # Browser origins allowed to call the API (the React dev servers)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # --- model and uploads (Phase 16) ---
    model_checkpoint: Path = ROOT / "ai" / "models" / "unet_flood_best.pth"
    uploads_dir: Path = ROOT / "backend" / "uploads"
    outputs_dir: Path = ROOT / "backend" / "outputs"
    max_upload_mb: int = 200
    max_pixels: int = 25_000_000

    # --- accounts and login (Phase 17c) ---
    # Signs the login tokens. Changing it logs everybody out. Keep it out of git.
    secret_key: str = Field(min_length=32)
    access_token_minutes: int = Field(480, ge=5, le=10080)

    # extra="ignore": .env also contains TEST_DATABASE_URL, which the app itself does not use
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()