"""T-MET-12e: ``tools/filter_ablation.py`` runs the cut-off ablation over a folder of Kinect files or of pose chunks,
writes numbers only, refuses what it cannot run with exit code 2 and a message that names no path, and exits 1 when a
run failed (P5.08).

The Kinect folders are made in the tests (111 small valid files: ``find_umons`` wants the whole dataset's count and a
license); the pose chunks are ``PoseRaw`` files made from boxes (a person who stands, and an empty scene).
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from helpers.pose_raw_build import box, pose_raw_from_boxes
from helpers.umons_fixtures import dataset_name, make_dataset
from taiji_ai.pose.raw_io import save_pose_raw

TOOL = Path(__file__).resolve().parents[2] / "tools" / "filter_ablation.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=TOOL.parents[1],
        check=False,
        timeout=600,
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


@pytest.fixture(scope="module")
def umons_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("umons_root") / "private_umons_folder"
    make_dataset(root, rows=150)
    return root


@pytest.fixture(scope="module")
def pose_folder(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("pose_chunks") / "private_pose_folder"
    folder.mkdir()
    standing = [[(box(960.0, 540.0, 200.0, 700.0), 26)] for _ in range(150)]
    save_pose_raw(folder / "d20-v1_000.npz", pose_raw_from_boxes(standing))
    save_pose_raw(folder / "d20-v1_001.npz", pose_raw_from_boxes([[] for _ in range(30)]))  # nobody in the picture
    return folder


# --- what it refuses --------------------------------------------------------------------------------------------------
def test_t_met_12e_a_missing_umons_folder_is_refused_without_its_path(tmp_path: Path):
    done = run_tool("umons", "--umons", str(tmp_path / "no_such_umons_folder"), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "error:" in done.stderr
    assert "no_such_umons_folder" not in done.stderr + done.stdout and str(tmp_path) not in done.stderr
    assert not (tmp_path / "out").exists()


def test_t_met_12e_a_missing_pose_folder_or_one_with_no_pose_file_is_refused_without_its_path(tmp_path: Path):
    done = run_tool("d20", "--pose", str(tmp_path / "no_such_pose_folder"), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "error:" in done.stderr
    assert "no_such_pose_folder" not in done.stderr + done.stdout and not (tmp_path / "out").exists()
    empty = tmp_path / "private_empty"
    empty.mkdir()
    done = run_tool("d20", "--pose", str(empty), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "no pose file" in done.stderr and "private_empty" not in done.stderr
    assert not (tmp_path / "out").exists()


def test_t_met_12e_an_unknown_id_and_a_missing_option_are_refused(umons_root: Path, pose_folder: Path, tmp_path: Path):
    done = run_tool("umons", "--umons", str(umons_root), "--out", str(tmp_path / "out"), "--only", "P09T09C09")
    assert done.returncode == 2 and "P09T09C09" in done.stderr and not (tmp_path / "out").exists()
    done = run_tool("d20", "--pose", str(pose_folder), "--out", str(tmp_path / "out"), "--only", "nope")
    assert done.returncode == 2 and "nope" in done.stderr and "private_pose_folder" not in done.stderr
    assert run_tool("umons", "--umons", str(umons_root)).returncode == 2  # --out is required
    assert run_tool().returncode == 2  # a command is required


# --- what it writes --------------------------------------------------------------------------------------------------
def test_t_met_12e_a_umons_run_writes_the_csv_and_the_tables_and_exits_zero(umons_root: Path, tmp_path: Path):
    out, report = tmp_path / "out", tmp_path / "tables.md"
    done = run_tool(
        "umons", "--umons", str(umons_root), "--out", str(out), "--only", dataset_name(0), dataset_name(1),
        "--report", str(report),
    )  # fmt: skip
    assert done.returncode == 0, done.stderr + done.stdout
    assert "runs 2" in done.stdout and "failed 0" in done.stdout
    rows = read_csv(out / "per_run.csv")
    assert {r["run_id"] for r in rows} == {dataset_name(0), dataset_name(1)}
    assert {r["cutoff_hz"] for r in rows} == {"4.0", "6.0", "8.0", "1000.0"}
    assert {r["group"] for r in rows} == {"hands", "hips", "feet"} and all(r["error"] == "" for r in rows)
    assert len(rows) == 2 * 4 * 3 * 5  # runs x cut-offs x groups x cells of the grid
    cells = read_csv(out / "cells.csv")
    assert len(cells) == 4 * 3 * 5 and {c["source"] for c in cells} == {"umons"}
    text = report.read_text(encoding="utf-8")
    assert "## umons" in text and "no filter" in text and "Runs: 2" in text


def test_t_met_12e_the_output_holds_ids_and_numbers_and_no_path_or_name(umons_root: Path, tmp_path: Path):
    out, report = tmp_path / "private_out_folder", tmp_path / "tables.md"
    done = run_tool(
        "umons", "--umons", str(umons_root), "--out", str(out), "--only", dataset_name(0), "--report", str(report)
    )
    assert done.returncode == 0, done.stderr
    everything = done.stdout + done.stderr + report.read_text(encoding="utf-8")
    for name in ("private_umons_folder", "private_out_folder", str(tmp_path), "Kinect", ".txt"):
        assert name not in everything, name
    for csv_file in out.glob("*.csv"):
        assert str(tmp_path) not in csv_file.read_text(encoding="utf-8")


def test_t_met_12e_a_d20_run_follows_the_performer_and_a_chunk_with_nobody_is_an_error_row_with_exit_one(
    pose_folder: Path, tmp_path: Path
):
    out = tmp_path / "out"
    done = run_tool("d20", "--pose", str(pose_folder), "--out", str(out))
    assert done.returncode == 1  # the empty chunk has no performer: a failed run, not a skipped one
    assert "runs 2" in done.stdout and "failed 1" in done.stdout and "failed d20-v1_001" in done.stdout
    assert "private_pose_folder" not in done.stdout + done.stderr
    rows = read_csv(out / "per_run.csv")
    errors = [r for r in rows if r["error"]]
    assert [r["run_id"] for r in errors] == ["d20-v1_001"] and "no performer" in errors[0]["error"]
    good = [r for r in rows if not r["error"]]
    assert {r["run_id"] for r in good} == {"d20-v1_000"} and len(good) == 4 * 3 * 5
    assert len(read_csv(out / "cells.csv")) == 4 * 3 * 5  # the summary is of the run that ran


def test_t_met_12e_when_every_run_fails_there_are_no_tables_and_the_exit_code_is_one(tmp_path: Path):
    folder = tmp_path / "chunks"
    folder.mkdir()
    save_pose_raw(folder / "d20-v9_000.npz", pose_raw_from_boxes([[] for _ in range(30)]))
    out, report = tmp_path / "out", tmp_path / "tables.md"
    done = run_tool("d20", "--pose", str(folder), "--out", str(out), "--report", str(report))
    assert done.returncode == 1 and "failed 1" in done.stdout
    assert (out / "per_run.csv").exists() and not (out / "cells.csv").exists() and not report.exists()
