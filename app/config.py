"""Immutable application settings with environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_env: str = "dev"
    host: str = "127.0.0.1"
    port: int = 5003
    api_key: str = "dev-service-key"
    provider_mode: str = "mock"  # mock | iflytek
    iflytek_base_url: str = "http://127.0.0.1:5100"
    iflytek_app_id: str = "demo-app"
    iflytek_api_key: str = "demo-api-key"
    provider_timeout: float = 3.0
    provider_retries: int = 1
    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "runtime" / "face.db")
    max_image_bytes: int = 4 * 1024 * 1024
    max_image_side: int = 8000
    min_image_side: int = 32
    max_gallery: int = 50
    top_k_max: int = 50
    idempotency_ttl: int = 600
    face_threshold: float = 0.75
    allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "https://face-demo.example.com",
    )
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        provider_mode = os.getenv("PROVIDER_MODE", "mock").strip().lower()
        if provider_mode not in {"mock", "iflytek"}:
            raise ValueError("PROVIDER_MODE must be mock or iflytek")
        return cls(
            app_env=os.getenv("APP_ENV", "dev"),
            host=os.getenv("APP_HOST", "127.0.0.1"),
            port=int(os.getenv("APP_PORT", "5003")),
            api_key=os.getenv("API_KEY", "dev-service-key"),
            provider_mode=provider_mode,
            iflytek_base_url=os.getenv("IFLYTEK_BASE_URL", "http://127.0.0.1:5100").rstrip("/"),
            iflytek_app_id=os.getenv("IFLYTEK_APP_ID", "demo-app"),
            iflytek_api_key=os.getenv("IFLYTEK_API_KEY", "demo-api-key"),
            provider_timeout=float(os.getenv("PROVIDER_TIMEOUT", "3")),
            provider_retries=int(os.getenv("PROVIDER_RETRIES", "1")),
            db_path=Path(os.getenv("FACE_DB_PATH", str(PROJECT_ROOT / "runtime" / "face.db"))),
            max_image_bytes=int(os.getenv("MAX_IMAGE_BYTES", str(4 * 1024 * 1024))),
            max_image_side=int(os.getenv("MAX_IMAGE_SIDE", "8000")),
            min_image_side=int(os.getenv("MIN_IMAGE_SIDE", "32")),
            max_gallery=int(os.getenv("MAX_GALLERY", "50")),
            top_k_max=int(os.getenv("TOP_K_MAX", "50")),
            idempotency_ttl=int(os.getenv("IDEMPOTENCY_TTL", "600")),
            face_threshold=float(os.getenv("FACE_THRESHOLD", "0.75")),
            allowed_origins=_csv_env(
                "ALLOWED_ORIGINS",
                "http://localhost:3000,https://face-demo.example.com",
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
