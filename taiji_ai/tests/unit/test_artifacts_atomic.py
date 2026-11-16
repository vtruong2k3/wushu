"""T-ART-01: ``atomic_write_bytes`` leaves nothing behind when it fails (BUG-0069)."""

from __future__ import annotations

from pathlib import Path

import pytest

from taiji_ai.store import artifacts
from taiji_ai.store.artifacts import atomic_write_bytes


def _only(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_t_art_01_a_failing_replace_keeps_the_old_file_and_leaves_no_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = tmp_path / "a.bin"
    atomic_write_bytes(target, b"old")

    def broken_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(artifacts.os, "replace", broken_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"old"
    assert _only(tmp_path) == ["a.bin"]


def test_t_art_01_a_failing_write_leaves_no_tmp_and_no_new_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def broken_fsync(fd):
        raise OSError("disk full")

    monkeypatch.setattr(artifacts.os, "fsync", broken_fsync)
    with pytest.raises(OSError, match="disk full"):
        atomic_write_bytes(tmp_path / "b.bin", b"data")

    assert _only(tmp_path) == []


def test_t_art_01_success_still_creates_parent_folders_and_replaces_the_file(tmp_path: Path):
    target = tmp_path / "deep" / "er" / "c.bin"
    atomic_write_bytes(target, b"one")
    atomic_write_bytes(target, b"two")

    assert target.read_bytes() == b"two"
    assert _only(target.parent) == ["c.bin"]
