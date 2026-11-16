"""T-BENCH-08: ``tools/bench_pose.py`` refuses what it cannot measure, with labels only and exit code 2 (P3.07)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "bench_pose.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=TOOL.parents[1],
        check=False,
        timeout=120,
    )


def test_t_bench_08_a_missing_video_folder_is_refused_without_its_path(tmp_path: Path):
    folder = tmp_path / "no_such_folder_of_videos"

    done = run_tool("--video-dir", str(folder), "--out", str(tmp_path / "out"))

    assert done.returncode == 2
    assert "video folder does not exist" in done.stderr
    assert "no_such_folder_of_videos" not in done.stderr + done.stdout
    assert not (tmp_path / "out").exists()  # nothing was written


def test_t_bench_08_an_empty_folder_names_the_missing_videos_by_label_only(tmp_path: Path):
    videos = tmp_path / "private_video_folder"
    videos.mkdir()

    done = run_tool("--video-dir", str(videos), "--out", str(tmp_path / "out"))

    assert done.returncode == 2
    for label in ("d20-v1", "d20-v2", "d20-v3", "d20-v4"):
        assert label in done.stderr, label
    assert "private_video_folder" not in done.stderr + done.stdout and str(tmp_path) not in done.stderr


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--ns", "5,10"], "N = 1"),
        (["--clips", "c9"], "unknown clip"),
        (["--repeats", "0"], "repeats"),
        (["--ns", "one"], "invalid literal"),
    ],
)
def test_t_bench_08_bad_options_are_refused_before_anything_is_read(tmp_path: Path, args: list[str], message: str):
    done = run_tool("--video-dir", str(tmp_path), "--out", str(tmp_path / "out"), *args)
    assert done.returncode == 2 and message in done.stderr
    assert not (tmp_path / "out").exists()


def test_t_bench_08_the_tool_explains_itself():
    done = run_tool("--help")
    assert done.returncode == 0 and "size and SHA-256" in done.stdout and "d20-v1..v4" in done.stdout
