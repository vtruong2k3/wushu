"""``GET /api/health`` — version, model registry status (verified once at startup), DB migrations, web build."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from taiji_ai import __version__
from taiji_ai.api.static import web_build_available
from taiji_ai.store.db import connect

router = APIRouter(tags=["health"])


class ModelInfo(BaseModel):
    name: str
    role: str
    sha256_prefix: str


class ModelStatus(BaseModel):
    ok: bool
    verified_at_startup: bool
    entries: list[ModelInfo] = []
    error: str | None = None


class DatabaseStatus(BaseModel):
    ok: bool
    migrations: list[int] = []
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    models: ModelStatus
    database: DatabaseStatus
    web_build: bool


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    models: ModelStatus = request.app.state.model_status
    try:
        conn = connect(settings.db_path, settings.migrations_dir)
        try:
            versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        finally:
            conn.close()
        database = DatabaseStatus(ok=True, migrations=versions)
    except Exception as exc:  # noqa: BLE001 — reported, not swallowed: status becomes "degraded"
        database = DatabaseStatus(ok=False, error=type(exc).__name__)
    status: Literal["ok", "degraded"] = "ok" if (models.ok and database.ok) else "degraded"
    return HealthResponse(
        status=status,
        version=__version__,
        models=models,
        database=database,
        web_build=web_build_available(settings.web_dist_dir),
    )
