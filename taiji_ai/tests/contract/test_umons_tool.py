"""T-QLT-12h: ``tools/umons_adapter.py`` runs the chain over a folder of Kinect files, writes counts only, refuses what
it cannot run with exit code 2 and a message that names no path, and exits 1 when a file failed (P4.08).

The folders are made in the tests (111 small valid files: ``find_umons`` wants the whole dataset's count and a license).
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from helpers.umons_fixtures import clean_text, dataset_name, make_dataset, synthetic_file

TOOL = Path(__file__).resolve().parents[2] / "tools" / "umons_adapter.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=TOOL.parents[1],
        check=False,
        timeout=300,
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


@pytest.fixture(scope="module")
def dataset(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("umons_root") / "private_umons_folder"
    folder = make_dataset(root)
    (folder / f"{dataset_name(1)}.txt").write_text(synthetic_file(), encoding="ascii")
    return root


def test_t_qlt_12h_a_missing_folder_is_refused_without_its_path(tmp_path: Path):
    folder = tmp_path / "no_such_umons_folder"
    done = run_tool("run", "--umons", str(folder), "--out", str(tmp_path / "out"))
    assert done.returncode == 2
    assert "error:" in done.stderr
    assert "no_such_umons_folder" not in done.stderr + done.stdout and str(tmp_path) not in done.stderr
    assert not (tmp_path / "out").exists()


def test_t_qlt_12h_a_folder_with_the_wrong_number_of_files_is_refused(tmp_path: Path):
    root = tmp_path / "private_name"
    make_dataset(root, count=5)
    done = run_tool("run", "--umons", str(root), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "111 files" in done.stderr
    assert "private_name" not in done.stderr + done.stdout and not (tmp_path / "out").exists()


def test_t_qlt_12h_an_unknown_sequence_name_and_a_bad_option_are_refused(dataset: Path, tmp_path: Path):
    done = run_tool("run", "--umons", str(dataset), "--out", str(tmp_path / "out"), "--only", "P09T09C09")
    assert done.returncode == 2 and "P09T09C09" in done.stderr and not (tmp_path / "out").exists()
    done = run_tool("run", "--umons", str(dataset), "--out", str(tmp_path / "out"), "--grid-hz", "-3")
    assert done.returncode == 2 and "grid" in done.stderr.lower()
    done = run_tool("run", "--umons", str(dataset))  # --out is required
    assert done.returncode == 2


def test_t_qlt_12h_a_run_writes_the_csv_and_the_tables_and_exits_zero(dataset: Path, tmp_path: Path):
    out, report = tmp_path / "out", tmp_path / "tables.md"
    done = run_tool(
        "run", "--umons", str(dataset), "--out", str(out), "--only", dataset_name(0), dataset_name(1),
        "--grid-hz", "30", "--report", str(report),
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    rows = read_csv(out / "per_file.csv")
    assert [r["sequence_id"] for r in rows] == [dataset_name(0), dataset_name(1)]
    assert rows[1]["repeated_rows"] == "6" and rows[1]["error"] == "" and rows[0]["rows"] == "20"
    side = read_csv(out / "per_file_grid.csv")
    assert [r["sequence_id"] for r in side] == [dataset_name(0), dataset_name(1)]
    assert side[1]["step_ms"].startswith("33.33") and rows[1]["step_ms"].startswith("33.0")
    text = report.read_text(encoding="utf-8")
    assert "default" in text and "grid 30 Hz" in text and dataset_name(1) in text
    assert str(tmp_path) not in text and str(tmp_path) not in done.stdout + done.stderr
    assert "files run: 2" in done.stdout


def test_t_qlt_12h_a_failing_file_is_an_error_row_the_run_goes_on_and_the_exit_code_is_one(tmp_path: Path):
    root = tmp_path / "umons"
    folder = make_dataset(root)
    (folder / f"{dataset_name(2)}.txt").write_text(clean_text(5).replace("-3300.0", "nan", 1), encoding="ascii")
    done = run_tool(
        "run", "--umons", str(root), "--out", str(tmp_path / "out"), "--only", dataset_name(0), dataset_name(2)
    )
    assert done.returncode == 1, done.stderr
    rows = read_csv(tmp_path / "out" / "per_file.csv")
    assert [r["sequence_id"] for r in rows] == [dataset_name(0), dataset_name(2)]
    assert rows[0]["error"] == "" and "not finite" in rows[1]["error"] and rows[1]["rows"] == ""
    assert "files failed: 1" in done.stdout and str(tmp_path) not in done.stdout + done.stderr
    assert f"failed {dataset_name(2)}: " in done.stdout and "not finite" in done.stdout  # the id and the reason
