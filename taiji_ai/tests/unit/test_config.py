from __future__ import annotations

from pathlib import Path

from taiji_ai.config import API_HOST, Settings


def test_bug_0004_env_read_at_construction(monkeypatch, tmp_path):
    """BUG-0004: environment overrides must be read when Settings() is built, not at import."""
    monkeypatch.setenv("TAIJI_DEVICE", "cpu")
    monkeypatch.setenv("TAIJI_API_PORT", "8123")
    monkeypatch.setenv("TAIJI_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("TAIJI_WEB_DIST_DIR", str(tmp_path / "dist"))
    monkeypatch.setenv("TAIJI_LOG_LEVEL", "debug")
    s = Settings()
    assert s.device == "cpu"
    assert s.api_port == 8123
    assert s.data_dir == Path(tmp_path / "d")
    assert s.web_dist_dir == Path(tmp_path / "dist")
    assert s.log_level == "DEBUG"


def test_defaults_without_env(monkeypatch):
    for name in ("TAIJI_DEVICE", "TAIJI_API_PORT", "TAIJI_WEB_DIST_DIR", "TAIJI_LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    s = Settings()
    assert s.device == "cuda"
    assert s.api_port == 8007  # default changed by the maintainer on 2026-11-14
    assert s.web_dist_dir.parts[-2:] == ("web", "dist")
    assert s.log_level == "INFO"
    assert API_HOST == "127.0.0.1"
