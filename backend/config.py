"""
GeoFlood AI backend - settings.

Values are read from environment variables or from the .env file in the project root.
DATABASE_URL is required; the app refuses to start without it.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_name: str = "GeoFlood AI API"
    app_version: str = "0.3.0"
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

    # extra="ignore": .env also contains TEST_DATABASE_URL, which the app itself does not use
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()