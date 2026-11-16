"""T-AUDIT-06: ``tools/pose_audit.py`` refuses what it cannot do, with labels only and exit code 2 (P3.08).

No GPU and no model is used: every case stops before the pose pass.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "pose_audit.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=TOOL.parents[1],
        check=False,
        timeout=120,
    )


def test_t_audit_06_a_missing_video_folder_is_refused_without_its_path(tmp_path: Path):
    folder = tmp_path / "no_such_folder_of_videos"
    out, work = tmp_path / "out", tmp_path / "work"

    done = run_tool("pose", "--video-dir", str(folder), "--out", str(out), "--work-dir", str(work))

    assert done.returncode == 2
    assert "video folder does not exist" in done.stderr
    assert "no_such_folder_of_videos" not in done.stderr + done.stdout
    assert not out.exists() and not work.exists()  # nothing was written


def test_t_audit_06_an_empty_folder_names_the_missing_videos_by_label_only(tmp_path: Path):
    videos = tmp_path / "private_video_folder"
    videos.mkdir()

    done = run_tool(
        "pose", "--video-dir", str(videos), "--out", str(tmp_path / "out"), "--work-dir", str(tmp_path / "work")
    )

    assert done.returncode == 2
    for label in ("d20-v1", "d20-v2", "d20-v3", "d20-v4"):
        assert label in done.stderr, label
    assert "private_video_folder" not in done.stderr + done.stdout and str(tmp_path) not in done.stderr
    assert not (tmp_path / "out").exists() and not (tmp_path / "work").exists()


def test_t_audit_06_the_analysis_of_a_folder_without_a_pass_is_refused_without_its_path(tmp_path: Path):
    folder = tmp_path / "no_pass_here"
    folder.mkdir()

    done = run_tool("analyse", "--out", str(folder), "--work-dir", str(tmp_path / "work"))

    assert done.returncode == 2
    assert "run the pose pass first" in done.stderr
    assert "no_pass_here" not in done.stderr + done.stdout
    assert sorted(p.name for p in folder.iterdir()) == []  # no review file, no sheets


def test_t_audit_06_the_report_without_an_analysis_is_refused_without_its_path(tmp_path: Path):
    folder = tmp_path / "not_analysed"
    folder.mkdir()

    done = run_tool("report", "--out", str(folder))

    assert done.returncode == 2
    assert "run analyse first" in done.stderr
    assert "not_analysed" not in done.stderr + done.stdout
    assert sorted(p.name for p in folder.iterdir()) == []


def test_t_audit_06_a_command_is_required_and_the_tool_explains_itself():
    assert run_tool().returncode == 2  # argparse: a command is required
    done = run_tool("--help")
    assert done.returncode == 0 and "size and SHA-256" in done.stdout and "d20-v1" in done.stdout
