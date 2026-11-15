from __future__ import annotations

import errno
import importlib.util
import sys
from pathlib import Path

import pytest

from taiji_ai.config import PROJECT_ROOT

_tool_path = PROJECT_ROOT / "tools" / "repo_hygiene.py"
_spec = importlib.util.spec_from_file_location("repo_hygiene", _tool_path)
assert _spec is not None and _spec.loader is not None
repo_hygiene = importlib.util.module_from_spec(_spec)
sys.modules["repo_hygiene"] = repo_hygiene
_spec.loader.exec_module(repo_hygiene)

classify = repo_hygiene.classify
find_violations = repo_hygiene.find_violations
normalize_repo_relpath = repo_hygiene.normalize_repo_relpath

DEFAULT_MAX_BYTES = 5 * 1024 * 1024


@pytest.mark.parametrize(
    ("path", "size", "expected_prefix"),
    [
        ("video.mp4", 100, "R1"),
        ("audio.WAV", 100, "R1"),
        ("clip.webm", 100, "R1"),
        ("weights.onnx", 100, "R2"),
        ("model.PT", 100, "R2"),
        ("model.safetensors", 100, "R2"),
        ("archive.zip", 100, "R3"),
        ("archive.tar.gz", 100, "R3"),
        ("archive.7Z", 100, "R3"),
        ("arrays.npz", 100, "R4"),
        ("table.PARQUET", 100, "R4"),
        ("data.pkl", 100, "R4"),
        ("app.sqlite3", 100, "R5"),
        ("test.db-wal", 100, "R5"),
        ("datasets/taiji/raw/video.avi", 100, "R1"),
        ("datasets/taiji/raw/data.csv", 100, "R6"),
        ("repos/taolu/clone/script.py", 100, "R7"),
        ("taiji_ai/web/node_modules/pkg/index.js", 100, "R8"),
        ("taiji_ai/.venv/Scripts/python.exe", 100, "R8"),
        ("taiji_ai/web/dist/index.html", 100, "R8"),
        ("taiji_ai/data/rec1/raw.dat", 100, "R9"),
        ("taiji_ai/models/custom.bin", 100, "R9"),
        (".env", 100, "R10"),
        (".env.local", 100, "R10"),
        ("id_rsa", 100, "R10"),
        ("cert.pem", 100, "R10"),
        ("key.KEY", 100, "R10"),
        ("big_file.txt", 6 * 1024 * 1024, "R11"),
    ],
)
def test_t_tool_04_classify_flags_violations(path: str, size: int, expected_prefix: str):
    violations = classify(path, size, DEFAULT_MAX_BYTES)
    assert any(v.startswith(expected_prefix) for v in violations), (
        f"Expected rule {expected_prefix} for {path}, got {violations}"
    )


@pytest.mark.parametrize(
    "path",
    [
        "src/taiji_ai/config.py",
        "Docs/WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md",
        "README.md",
        ".gitignore",
        "datasets/taiji/README.md",
        "datasets/taiji/readme.md",
        "repos/taolu/REPOS.md",
        "repos/taolu/repos.md",
        "taiji_ai/data/.gitkeep",
        "taiji_ai/models/.gitkeep",
        "taiji_ai/models/registry.json",
        ".env.example",
        ".env.sample",
    ],
)
def test_t_tool_04_allowed_exceptions_and_source_files_pass(path: str):
    assert classify(path, 1024, DEFAULT_MAX_BYTES) == []


def test_t_tool_04_normalization_handles_backslashes_and_dots():
    assert normalize_repo_relpath("taiji_ai\\data\\test.txt") == "taiji_ai/data/test.txt"
    assert normalize_repo_relpath("./src/file.py") == "src/file.py"
    assert normalize_repo_relpath("/root/file.py") == "root/file.py"
    # Windows paths with backslashes classified properly
    violations = classify("datasets\\sample\\data.csv", 100, DEFAULT_MAX_BYTES)
    assert any(v.startswith("R6") for v in violations)


def test_t_tool_04_find_violations_aggregates():
    entries = [
        ("clean.py", 100),
        ("bad.mp4", 200),
        ("datasets/bad.csv", 300),
    ]
    v = find_violations(entries, DEFAULT_MAX_BYTES)
    assert len(v) == 2
    paths = {item.path for item in v}
    assert paths == {"bad.mp4", "datasets/bad.csv"}


def _stat_fails_for(monkeypatch: pytest.MonkeyPatch, name: str, error: OSError) -> None:
    """Make Path.stat() raise `error` for files called `name`; every other path behaves normally."""
    real_stat = Path.stat

    def fake_stat(self: Path, *args: object, **kwargs: object):
        if self.name == name:
            raise error
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)


@pytest.mark.parametrize(
    "error",
    [
        PermissionError(errno.EACCES, "permission denied"),
        OSError(errno.EIO, "input/output error"),
        OSError(errno.ELOOP, "too many levels of symbolic links"),  # pathlib's is_file()/exists() hide this one
    ],
    ids=["permission", "io-error", "eloop"],
)
def test_bug_0009_stat_error_exits_2_and_names_the_file(tmp_path, monkeypatch, capsys, error):
    (tmp_path / "ok.txt").write_text("x")
    (tmp_path / "unreadable.txt").write_text("x")
    monkeypatch.setattr(repo_hygiene, "list_candidate_files", lambda root: ["ok.txt", "unreadable.txt"])
    _stat_fails_for(monkeypatch, "unreadable.txt", error)

    assert repo_hygiene.main(["--repo-root", str(tmp_path)]) == 2

    err = capsys.readouterr().err
    assert "cannot stat unreadable.txt" in err


def test_bug_0009_stat_error_wins_over_violations_but_both_are_reported(tmp_path, monkeypatch, capsys):
    (tmp_path / "clip.mp4").write_bytes(b"x")
    (tmp_path / "unreadable.txt").write_text("x")
    monkeypatch.setattr(repo_hygiene, "list_candidate_files", lambda root: ["clip.mp4", "unreadable.txt"])
    _stat_fails_for(monkeypatch, "unreadable.txt", PermissionError(errno.EACCES, "permission denied"))

    # A file that could not be checked means the verdict is unknown: never 0 (clean) or 1 (violations only).
    assert repo_hygiene.main(["--repo-root", str(tmp_path)]) == 2

    err = capsys.readouterr().err
    assert "clip.mp4: R1" in err
    assert "cannot stat unreadable.txt" in err


def test_bug_0009_deleted_file_checks_path_rules_only(tmp_path, monkeypatch, capsys):
    # Indexed in git but missing on disk: size is unknown (None), path rules still apply, no error.
    monkeypatch.setattr(repo_hygiene, "list_candidate_files", lambda root: ["gone.onnx"])
    assert repo_hygiene.main(["--repo-root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "gone.onnx: R2" in err
    assert "cannot stat" not in err

    monkeypatch.setattr(repo_hygiene, "list_candidate_files", lambda root: ["gone.txt"])
    assert repo_hygiene.main(["--repo-root", str(tmp_path)]) == 0


def test_bug_0009_directory_entry_is_not_an_error(tmp_path, monkeypatch):
    # A directory in the index (for example a gitlink/submodule) has no size; it must not be an error.
    (tmp_path / "sub").mkdir()
    monkeypatch.setattr(repo_hygiene, "list_candidate_files", lambda root: ["sub"])
    assert repo_hygiene.main(["--repo-root", str(tmp_path)]) == 0


def test_bug_0009_oversized_existing_file_is_still_flagged(tmp_path, monkeypatch, capsys):
    (tmp_path / "big.txt").write_bytes(b"\0" * (2 * 1024 * 1024))
    monkeypatch.setattr(repo_hygiene, "list_candidate_files", lambda root: ["big.txt"])
    assert repo_hygiene.main(["--repo-root", str(tmp_path), "--max-mb", "1"]) == 1
    assert "big.txt: R11" in capsys.readouterr().err


def test_t_tool_04_deleted_indexed_file_has_none_size():
    # R1 still flags with size=None
    violations = classify("deleted.mp4", None, DEFAULT_MAX_BYTES)
    assert any(v.startswith("R1") for v in violations)
    # clean file with size=None has no violations
    assert classify("clean.py", None, DEFAULT_MAX_BYTES) == []
    # clean file with size=None does not trigger R11
    assert classify("some_file.txt", None, DEFAULT_MAX_BYTES) == []
