from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
UPLOADS_DIR = BACKEND_DIR / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Catania Spesa Top API"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    database_path: Path = DATA_DIR / "offers.db"
    upload_dir: Path = UPLOADS_DIR
    poppler_path: Path | None = None
    cors_origins: str = "*"
    seed_demo_data: bool = True

    vision_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openai_image_max_px: int = Field(default=1800, ge=512, le=4096)
    openai_pdf_pages_per_request: int = Field(default=4, ge=1, le=12)
    pdf_render_dpi: int = Field(default=180, ge=96, le=400)
    request_timeout_seconds: float = Field(default=90.0, ge=10.0, le=300.0)

    @field_validator("database_path", "upload_dir", "poppler_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: str | Path | None) -> Path | None:
        if value in (None, ""):
            return None
        if isinstance(value, Path):
            return value
        return Path(value)

    @field_validator("database_path", "upload_dir", "poppler_path")
    @classmethod
    def _resolve_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None

        resolved = value.expanduser()
        if not resolved.is_absolute():
            resolved = PROJECT_ROOT / resolved
        return resolved.resolve(strict=False)

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def demo_data_path(self) -> Path:
        return (DATA_DIR / "demo_offers.json").resolve(strict=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
