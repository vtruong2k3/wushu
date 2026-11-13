"""Serve the React build (``web/dist``) with single-page-app fallback.

- ``/assets/*`` → files from ``web/dist/assets`` (StaticFiles; no path traversal outside the directory).
- Any other non-API ``GET`` → ``index.html`` so client-side routes work on reload.
- ``/api/*`` is never answered with ``index.html``: unknown API paths stay JSON 404s.
- Without a build, ``GET /`` explains how to build instead of failing silently.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from taiji_ai.api.errors import error_response

API_PREFIX = "/api"
# index.html must be revalidated so a rebuilt UI is picked up; hashed /assets files may be cached.
NO_CACHE = {"Cache-Control": "no-cache"}


def web_build_available(dist_dir: Path) -> bool:
    return (dist_dir / "index.html").is_file()


def install_static(app: FastAPI, dist_dir: Path) -> None:
    index = dist_dir / "index.html"
    assets = dist_dir / "assets"
    if web_build_available(dist_dir) and assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa(full_path: str, request: Request) -> FileResponse | JSONResponse:
        path = request.url.path
        if path == API_PREFIX or path.startswith(API_PREFIX + "/"):
            return error_response(404, "not_found", "Not Found")
        if not web_build_available(dist_dir):
            return error_response(
                503,
                "web_not_built",
                "Web UI build not found. Run `pnpm build` in taiji_ai/web (or `pnpm dev` for development).",
            )
        candidate = (dist_dir / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist_dir.resolve()):
            return FileResponse(candidate)  # e.g. favicon.ico at the dist root
        return FileResponse(index, headers=NO_CACHE)
