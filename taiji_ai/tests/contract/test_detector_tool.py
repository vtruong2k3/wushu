"""T-DET-08: ``tools/detector_compare.py`` refuses what it cannot do, with labels only and exit code 2 (P3.09).

No model of ours, no GPU: every case stops before a detector runs. The order of the checks is part of the contract: the
options, the video folder, the YOLO11 file (exists, is an ONNX model, has the layout of a COCO detector at 640), then
the videos.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "detector_compare.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=TOOL.parents[1],
        check=False,
        timeout=180,
    )


def test_t_det_08_a_missing_video_folder_is_refused_without_its_path(tmp_path: Path):
    done = run_tool("run", "--video-dir", str(tmp_path / "no_such_videos"), "--yolo11", str(tmp_path / "m.onnx"))
    assert done.returncode == 2 and "video folder does not exist" in done.stderr
    assert "no_such_videos" not in done.stderr + done.stdout
    assert not (tmp_path / "out").exists()


def test_t_det_08_a_missing_yolo11_file_is_refused_without_its_path(tmp_path: Path):
    videos = tmp_path / "private_videos"
    videos.mkdir()
    done = run_tool("run", "--video-dir", str(videos), "--yolo11", str(tmp_path / "private_model.onnx"))
    assert done.returncode == 2 and "YOLO11 file does not exist" in done.stderr
    assert "private_model" not in done.stderr + done.stdout and "private_videos" not in done.stderr + done.stdout


def test_t_det_08_a_file_that_is_not_an_onnx_model_is_refused(tmp_path: Path):
    videos = tmp_path / "v"
    videos.mkdir()
    fake = tmp_path / "fake.onnx"
    fake.write_bytes(b"this is not a model" * 100)
    done = run_tool("run", "--video-dir", str(videos), "--yolo11", str(fake))
    assert done.returncode == 2 and "not a readable ONNX model" in done.stderr
    assert "fake.onnx" not in done.stderr + done.stdout


def test_t_det_08_bad_options_are_refused_before_anything_is_read(tmp_path: Path):
    for args, message in (
        (["--repeats", "0"], "repeats"),
        (["--warmup", "-1"], "warmup"),
        (["--score", "1.5"], "score"),
        (["--nms-iou", "0"], "nms"),
    ):
        done = run_tool("run", "--video-dir", str(tmp_path), "--yolo11", str(tmp_path / "m.onnx"), *args)
        assert done.returncode == 2 and message in done.stderr, args


def test_t_det_08_report_and_sheets_need_a_run_first(tmp_path: Path):
    for command in ("report", "sheets"):
        done = run_tool(command, "--out", str(tmp_path / "nothing_here"))
        assert done.returncode == 2 and "run first" in done.stderr
        assert "nothing_here" not in done.stderr + done.stdout


def test_t_det_08_the_default_nms_limit_of_the_tool_is_the_one_of_the_shipping_graph():
    """BUG-0073: the NonMaxSuppression node of the shipping YOLOX graph has IoU 0.65 (read in P3.09, DEC-0043); the
    default of the tool and the value of the rule must be that number, not the 0.45 of rtmlib's constructor."""
    import importlib.util

    from taiji_ai.bench.detector_metrics import DetectorRule

    spec = importlib.util.spec_from_file_location("detector_compare_tool", TOOL)
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    args = tool.build_parser().parse_args(["run", "--video-dir", "v", "--yolo11", "m.onnx"])
    assert args.nms_iou == DetectorRule().matched_nms_iou == 0.65


def test_t_det_08_the_tool_explains_itself_and_its_licence():
    done = run_tool("--help")
    assert done.returncode == 0 and "AGPL-3.0" in done.stdout and "offline" in done.stdout
