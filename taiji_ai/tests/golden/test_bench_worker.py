"""T-BENCH-07: the benchmark worker with the real models on a short synthetic clip (P3.07).

The clip is the 1 s 1080p test pattern of the fixtures: nobody is in it, so the pose has zero persons; the worker must
run, time everything, sample the GPU memory and leave a loadable pose file without failing on "no target". Skipped when
the models or CUDA are missing (``gpu`` marker). No D20 video is used here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from taiji_ai.bench.clips import PlanEntry, write_plan
from taiji_ai.bench.gpu import try_open_nvml
from taiji_ai.bench.orchestrate import summarise_worker
from taiji_ai.config import Settings, get_settings
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.pose.raw_io import load_pose_raw

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module")
def models_ready() -> None:
    if not get_settings().registry_path.exists():
        pytest.skip("models not fetched (run tools/fetch_models.py)")
    import onnxruntime as ort

    if "CUDAExecutionProvider" not in ort.get_available_providers():
        pytest.skip("CUDA provider not available")


def test_t_bench_07_the_worker_measures_a_clip_without_people(
    models_ready, hd_video_1080p: Path, ingest_settings: Settings, tmp_path: Path
):
    meta = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T01", "camera_id": "camA"}
    rec = (
        ingest_settings.data_dir
        / "recordings"
        / ingest_recording(hd_video_1080p, meta, ingest_settings).manifest.recording_id
    )
    write_plan(tmp_path / "plan.json", [PlanEntry("c1", str(rec), 0.0, 1.0)])
    out, work = tmp_path / "worker.json", tmp_path / "work"

    done = subprocess.run(
        [
            sys.executable, "-m", "taiji_ai.bench.worker", "--plan", str(tmp_path / "plan.json"), "--n", "5",
            "--repeats", "2", "--baseline-s", "0.3", "--work-dir", str(work), "--out", str(out),
        ],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2], check=False, timeout=600,
    )  # fmt: skip

    assert done.returncode == 0, done.stderr[-2000:]
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["n"] == 5 and result["repeats"] == 2 and result["load_s"] > 0.0
    assert result["warmup"]["elapsed_s"] > 0.0
    c1 = result["clips"]["c1"]
    assert len(c1["passes"]) == 2 and c1["all_identical"] is True and c1["persons_per_frame"]["0"] == 1.0
    assert all(p["n_estimate"] == 0 and p["n_detect"] > 0 for p in c1["passes"])  # nobody: no pose call at all
    assert len(c1["decode"]) == 2 and c1["decode"][0]["n_frames"] == c1["n_frames"]
    assert all(p["target_found"] is False and p["post_s"] > 0.0 for p in c1["post"])  # no target is a result
    assert c1["passes"][0]["latency_ms"] and len(c1["passes"][0]["latency_ms"]) == c1["n_frames"]

    raw = load_pose_raw(work / "pose_n5_c1.npz")
    assert raw.n_frames == c1["n_frames"] and int(raw.person_offsets[-1]) == 0

    nvml, _ = try_open_nvml()
    if nvml is None:
        assert result["vram"]["measured"] is False and result["vram"]["reason"]
    else:
        nvml.close()
        vram = result["vram"]
        assert (
            vram["measured"] is True
            and vram["baseline_mib"] > 0
            and {"load", "warmup", "measured"} <= set(vram["peaks_mib"])
        )
        assert vram["peak_total_mib"] >= vram["baseline_mib"] - vram["drift_mib"] - 1.0

    summary = summarise_worker(result)  # the derived numbers work on a real worker result
    assert summary["rtf"] > 0.0 and summary["phases_s"]["detect_s"] > 0.0 and summary["n_windows"] >= 1


def test_t_bench_07_a_plan_that_points_nowhere_makes_the_worker_fail_with_exit_2(models_ready, tmp_path: Path):
    write_plan(tmp_path / "plan.json", [PlanEntry("c1", str(tmp_path / "no_recording"), 0.0, 1.0)])
    done = subprocess.run(
        [
            sys.executable, "-m", "taiji_ai.bench.worker", "--plan", str(tmp_path / "plan.json"), "--n", "1",
            "--repeats", "1", "--baseline-s", "0.0", "--work-dir", str(tmp_path / "w"),
            "--out", str(tmp_path / "o.json"),
        ],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2], check=False, timeout=300,
    )  # fmt: skip
    assert done.returncode == 2 and not (tmp_path / "o.json").exists()
