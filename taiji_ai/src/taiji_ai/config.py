"""Project paths and runtime settings.

Values can be overridden with environment variables, read when ``Settings()`` is constructed (not at import):
TAIJI_DATA_DIR, TAIJI_MODELS_DIR, TAIJI_WEB_DIST_DIR, TAIJI_DEVICE, TAIJI_API_PORT.

The API host is deliberately not configurable: the server only listens on the loopback interface
(AGENTS.md §5.7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_HOST: Final = "127.0.0.1"


def _env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: _env_path("TAIJI_DATA_DIR", PROJECT_ROOT / "data"))
    models_dir: Path = field(default_factory=lambda: _env_path("TAIJI_MODELS_DIR", PROJECT_ROOT / "models"))
    web_dist_dir: Path = field(default_factory=lambda: _env_path("TAIJI_WEB_DIST_DIR", PROJECT_ROOT / "web" / "dist"))
    migrations_dir: Path = PROJECT_ROOT / "migrations"
    device: str = field(default_factory=lambda: os.environ.get("TAIJI_DEVICE", "cuda"))
    api_port: int = field(default_factory=lambda: int(os.environ.get("TAIJI_API_PORT", "8007")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.sqlite3"

    @property
    def registry_path(self) -> Path:
        return self.models_dir / "registry.json"


def get_settings() -> Settings:
    return Settings()
