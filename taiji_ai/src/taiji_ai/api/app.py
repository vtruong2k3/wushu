"""FastAPI application factory.

One local process serves the JSON API under ``/api`` and the React build. Heavy work (pose, metrics) never runs
here; it belongs to the worker subprocess (AGENTS.md §5.7).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from taiji_ai import __version__
from taiji_ai.api.errors import install_error_handlers
from taiji_ai.api.routers import health
from taiji_ai.api.routers.health import ModelInfo, ModelStatus
from taiji_ai.api.static import API_PREFIX, install_static
from taiji_ai.config import Settings, get_settings
from taiji_ai.pose.registry import ModelIntegrityError, ModelRegistry
from taiji_ai.store.db import connect

log = logging.getLogger(__name__)


def _check_models(settings: Settings, verify: bool) -> ModelStatus:
    """Load the registry once. With ``verify=True`` every model file is SHA-256 checked (slow, startup only)."""
    try:
        reg = ModelRegistry(settings.registry_path, verify=verify)
    except ModelIntegrityError as exc:
        log.warning("model registry problem: %s", exc)
        return ModelStatus(ok=False, verified_at_startup=verify, error=str(exc))
    entries = [ModelInfo(name=e.name, role=e.role, sha256_prefix=e.sha256[:12]) for e in reg.entries.values()]
    return ModelStatus(ok=True, verified_at_startup=verify, entries=entries)


def create_app(settings: Settings | None = None, verify_models: bool = True) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = connect(settings.db_path, settings.migrations_dir)  # applies pending migrations once
        conn.close()
        app.state.model_status = _check_models(settings, verify_models)
        yield

    app = FastAPI(
        title="Taiji AI API",
        version=__version__,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.state.settings = settings
    install_error_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    install_static(app, settings.web_dist_dir)  # must be last: it registers the catch-all GET route
    return app
