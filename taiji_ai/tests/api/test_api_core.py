"""Contract tests for the API skeleton (T-API-01..04). Every test uses temporary settings, never ./data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from taiji_ai import __version__
from taiji_ai.api.__main__ import server_config
from taiji_ai.api.app import create_app
from taiji_ai.config import PROJECT_ROOT, Settings
from taiji_ai.store.artifacts import sha256_file


def _fake_models(models_dir: Path) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "det.onnx").write_bytes(b"det")
    (models_dir / "pose.onnx").write_bytes(b"pose")
    reg = {
        "schema_version": "model-registry/1",
        "models": [
            {"name": "det-x", "role": "det", "file": "det.onnx", "sha256": sha256_file(models_dir / "det.onnx"),
             "input_size": [640, 640]},
            {"name": "pose-x", "role": "pose", "file": "pose.onnx", "sha256": sha256_file(models_dir / "pose.onnx"),
             "input_size": [192, 256], "skeleton": "halpe26/1"},
        ],
    }  # fmt: skip
    (models_dir / "registry.json").write_text(json.dumps(reg), encoding="utf-8")


def _settings(tmp_path: Path, *, models: bool = True, dist: bool = False) -> Settings:
    if models:
        _fake_models(tmp_path / "models")
    dist_dir = tmp_path / "dist"
    if dist:
        (dist_dir / "assets").mkdir(parents=True)
        (dist_dir / "index.html").write_text("<!doctype html><div id=root>SPA</div>", encoding="utf-8")
        (dist_dir / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
        (dist_dir / "favicon.ico").write_bytes(b"ico")
    return Settings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        web_dist_dir=dist_dir,
        migrations_dir=PROJECT_ROOT / "migrations",
        device="cpu",
        api_port=0,
    )


def _add_api_route(app, path: str, fn) -> None:
    """Register a test-only route and keep the SPA catch-all route last, as create_app() does."""
    app.add_api_route(path, fn, methods=["GET"])
    spa = [r for r in app.router.routes if getattr(r, "path", "") == "/{full_path:path}"]
    for r in spa:
        app.router.routes.remove(r)
        app.router.routes.append(r)


# --- T-API-01 ---------------------------------------------------------------------------------
def test_t_api_01_health_ok(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["models"]["ok"] and body["models"]["verified_at_startup"]
    assert {m["role"] for m in body["models"]["entries"]} == {"det", "pose"}
    assert all(len(m["sha256_prefix"]) == 12 for m in body["models"]["entries"])
    assert body["database"] == {"ok": True, "migrations": [1], "error": None}
    assert body["web_build"] is False


def test_t_api_01_health_degraded_without_registry(tmp_path):
    with TestClient(create_app(_settings(tmp_path, models=False))) as client:
        body = client.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["models"]["ok"] is False
    assert "registry not found" in body["models"]["error"]


def test_t_api_01_models_verified_once_not_per_request(tmp_path, monkeypatch):
    calls = {"n": 0}
    import taiji_ai.pose.registry as reg_mod

    real = reg_mod.sha256_file

    def counting(path, *a, **k):
        calls["n"] += 1
        return real(path, *a, **k)

    monkeypatch.setattr(reg_mod, "sha256_file", counting)
    with TestClient(create_app(_settings(tmp_path))) as client:
        after_startup = calls["n"]
        for _ in range(3):
            assert client.get("/api/health").status_code == 200
    assert after_startup == 2  # two model files hashed at startup
    assert calls["n"] == after_startup  # no hashing per request


def test_t_api_01_health_reports_tampered_model(tmp_path):
    s = _settings(tmp_path)
    (tmp_path / "models" / "pose.onnx").write_bytes(b"tampered")
    with TestClient(create_app(s)) as client:
        body = client.get("/api/health").json()
    assert body["status"] == "degraded"
    assert "sha256 mismatch" in body["models"]["error"]


# --- T-API-02 ---------------------------------------------------------------------------------
def test_t_api_02_unhandled_error_is_generic(tmp_path):
    app = create_app(_settings(tmp_path))

    def boom() -> None:
        raise RuntimeError(r"secret at C:\internal\path\x.py")

    _add_api_route(app, "/api/_boom", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/api/_boom")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "Internal server error"}}
    assert "secret" not in r.text
    assert "Traceback" not in r.text
    assert "internal\\path" not in r.text and "x.py" not in r.text


def test_t_api_02_unknown_api_path_is_json_404(tmp_path):
    with TestClient(create_app(_settings(tmp_path, dist=True))) as client:
        r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"]["code"] == "not_found"


def test_t_api_02_method_not_allowed_is_json(tmp_path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        r = client.post("/api/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


def test_t_api_02_validation_error_is_json_without_input_echo(tmp_path):
    app = create_app(_settings(tmp_path))

    def needs_int(n: int) -> dict:
        return {"n": n}

    _add_api_route(app, "/api/_int", needs_int)
    with TestClient(app) as client:
        r = client.get("/api/_int", params={"n": "SENSITIVE-VALUE"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"][0]["loc"] == ["query", "n"]
    assert "SENSITIVE-VALUE" not in r.text


# --- T-API-03 ---------------------------------------------------------------------------------
def test_t_api_03_spa_served_with_fallback(tmp_path):
    with TestClient(create_app(_settings(tmp_path, dist=True))) as client:
        root = client.get("/")
        deep = client.get("/recordings/abc/segments")
        asset = client.get("/assets/app.js")
        ico = client.get("/favicon.ico")
        health = client.get("/api/health").json()
    assert root.status_code == 200 and "SPA" in root.text
    assert root.headers["cache-control"] == "no-cache"
    assert deep.status_code == 200 and "SPA" in deep.text  # client-side route
    assert asset.status_code == 200 and "console.log" in asset.text
    assert ico.status_code == 200 and ico.content == b"ico"
    assert health["web_build"] is True


def test_t_api_03_no_traversal_outside_dist(tmp_path):
    (tmp_path / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    with TestClient(create_app(_settings(tmp_path, dist=True))) as client:
        for url in (
            "/../secret.txt",
            "/%2e%2e/secret.txt",
            "/assets/../../secret.txt",
            f"/{tmp_path.as_posix()}/secret.txt",
        ):
            r = client.get(url)
            assert "TOP-SECRET" not in r.text, url


def test_t_api_03_without_build_explains(tmp_path):
    with TestClient(create_app(_settings(tmp_path, dist=False))) as client:
        r = client.get("/")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "web_not_built"


# --- T-API-04 ---------------------------------------------------------------------------------
@pytest.mark.parametrize("port", [8007, 9123])
def test_t_api_04_loopback_only(port):
    cfg = server_config(port)
    assert cfg["host"] == "127.0.0.1"
    assert cfg["port"] == port
    assert cfg["workers"] == 1
