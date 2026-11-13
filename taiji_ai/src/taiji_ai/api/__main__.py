"""Run the local server: ``python -m taiji_ai.api [--port N]``.

The host is always 127.0.0.1 (AGENTS.md §5.7); there is intentionally no ``--host`` option.
"""

from __future__ import annotations

import argparse

from taiji_ai.config import API_HOST, get_settings


def server_config(port: int) -> dict:
    """uvicorn keyword arguments. Single worker: one GPU job at a time is enforced elsewhere, but the API
    process itself must also stay single to keep SQLite access simple."""
    return {"host": API_HOST, "port": port, "workers": 1, "log_level": "info", "factory": True}


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m taiji_ai.api")
    parser.add_argument("--port", type=int, default=settings.api_port)
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run("taiji_ai.api.app:create_app", **server_config(args.port))


if __name__ == "__main__":
    main()
