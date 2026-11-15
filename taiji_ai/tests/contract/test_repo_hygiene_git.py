from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from taiji_ai.config import PROJECT_ROOT

_tool_path = PROJECT_ROOT / "tools" / "repo_hygiene.py"
git_available = shutil.which("git") is not None


def run_hygiene(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_tool_path), *args],
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.mark.skipif(not git_available, reason="git CLI required for contract test")
def test_t_tool_05_repo_hygiene_git_flow(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Initialize a clean git repo. No commit is made (and no identity or signing config is needed):
    # `git ls-files --cached` reads the index, so staged files are enough.
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True, capture_output=True)

    # 1. Ignored files are not checked; clean repo passes
    (repo_dir / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
    (repo_dir / "clean.py").write_text("print('hello')\n", encoding="utf-8")
    (repo_dir / "bad.ignored").write_bytes(b"\x00" * 10)  # would be violation if not ignored
    subprocess.run(["git", "add", ".gitignore", "clean.py"], cwd=repo_dir, check=True, capture_output=True)

    res_clean = run_hygiene(["--repo-root", str(repo_dir)])
    assert res_clean.returncode == 0, f"Clean repo should pass, got stderr: {res_clean.stderr}"
    assert "PASS: 0 violations" in res_clean.stdout
    assert "2 files checked" in res_clean.stdout

    # 2. Untracked unignored violation causes exit 1 and prints relative path
    bad_mp4 = repo_dir / "clip.mp4"
    bad_mp4.write_bytes(b"\x00" * 10)
    res_bad = run_hygiene(["--repo-root", str(repo_dir)])
    assert res_bad.returncode == 1, "Untracked media file should trigger violation (exit 1)"
    assert "clip.mp4: R1 media file (.mp4)" in res_bad.stderr
    bad_mp4.unlink()

    # 3. Tracked violation deleted from working tree still violates path rules (size=None)
    bad_tracked = repo_dir / "deleted_later.weights.onnx"
    bad_tracked.write_bytes(b"\x00" * 10)
    subprocess.run(["git", "add", "deleted_later.weights.onnx"], cwd=repo_dir, check=True, capture_output=True)
    bad_tracked.unlink()  # exists in git index, but deleted from disk
    res_deleted = run_hygiene(["--repo-root", str(repo_dir)])
    assert res_deleted.returncode == 1, "Tracked deleted forbidden file must still fail"
    assert "deleted_later.weights.onnx: R2 model weights (.onnx)" in res_deleted.stderr
    subprocess.run(["git", "rm", "-f", "deleted_later.weights.onnx"], cwd=repo_dir, check=True, capture_output=True)

    # 4. Non-ASCII filenames are handled without decode errors
    (repo_dir / "thái_cực_quyền.txt").write_text("bài 24 thức\n", encoding="utf-8")
    res_non_ascii = run_hygiene(["--repo-root", str(repo_dir)])
    assert res_non_ascii.returncode == 0, f"Non-ASCII filename should pass, got stderr: {res_non_ascii.stderr}"
    assert "PASS: 0 violations" in res_non_ascii.stdout

    # 5. Non-git directory causes exit 2 with actionable error
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    res_nongit = run_hygiene(["--repo-root", str(empty_dir)])
    assert res_nongit.returncode == 2, "Non-git directory should return exit 2"
    assert "Error:" in res_nongit.stderr
