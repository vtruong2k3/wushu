"""T-DET-09: the shipping detector wrapper and the detector worker with the real YOLOX model (P3.09).

* ``ShippingDetector`` at the limit 0.3 returns the boxes of ``PoseEstimator.detect`` (rtmlib) and keeps the scores;
* the worker runs the three sets on the 1 s test pattern (nobody in it) and writes the detections and the timings;
* on a real frame of D20 (video 2, found by size and SHA-256, skipped when absent) the same equality holds with a
  person.

Skipped when the models or CUDA are missing (``gpu`` marker). The YOLO11 smoke runs only if the exported file exists
in the ignored folder of the task (it is deleted when the task closes).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from taiji_ai.bench.detector_worker import run_job, unpack
from taiji_ai.bench.yolo_onnx import ShippingDetector
from taiji_ai.config import get_settings
from taiji_ai.io.frames import iter_frames
from taiji_ai.pose.registry import ModelRegistry

pytestmark = pytest.mark.gpu

REPO_ROOT = Path(__file__).resolve().parents[3]
D20_VIDEO_2_SIZE = 257_287_499
D20_VIDEO_2_SHA256 = "50a6cd2f383ccd8fc3da77b94d300bd80cd5d3f5cf208a13aa12e6004e35bec8"
YOLO11_ONNX = Path(__file__).resolve().parents[2] / "data" / "bench" / "p3_09" / "models" / "yolo11m.onnx"


@pytest.fixture(scope="module")
def registry() -> ModelRegistry:
    if not get_settings().registry_path.exists():
        pytest.skip("models not fetched (run tools/fetch_models.py)")
    import onnxruntime as ort

    if "CUDAExecutionProvider" not in ort.get_available_providers():
        pytest.skip("CUDA provider not available")
    return ModelRegistry(get_settings().registry_path)


@pytest.fixture(scope="module")
def estimator(registry: ModelRegistry):
    from taiji_ai.pose.rtm import PoseEstimator

    return PoseEstimator(registry, device="cuda")


@pytest.fixture(scope="module")
def shipping(registry: ModelRegistry) -> ShippingDetector:
    return ShippingDetector(registry.by_role("det").path, device="cuda", score_limit=0.3)


def _same_boxes(ours: np.ndarray, theirs: np.ndarray) -> None:
    assert ours.shape[0] == theirs.shape[0], (ours.shape, theirs.shape)
    assert np.allclose(ours[:, :4], theirs, atol=1e-3)
    assert (ours[:, 4] > 0.3).all()  # the scores are kept, and all are above the limit


def test_t_det_09_the_wrapper_returns_the_boxes_of_rtmlib_on_noise_and_on_the_test_pattern(
    estimator, shipping: ShippingDetector, hd_video_1080p: Path
):
    rng = np.random.default_rng(7)
    noise = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
    _same_boxes(shipping.detect(noise), estimator.detect(noise))
    frame = next(iter(iter_frames(hd_video_1080p, 0.0, 0.2))).image
    _same_boxes(shipping.detect(frame), estimator.detect(frame))


def test_t_det_09_a_higher_limit_keeps_a_subset_of_the_detections_of_the_lower_one(
    shipping: ShippingDetector, hd_video_1080p: Path
):
    frame = next(iter(iter_frames(hd_video_1080p, 0.0, 0.2))).image
    low, high = shipping.detect(frame, 0.3), shipping.detect(frame, 0.7)
    assert len(high) <= len(low) and (high[:, 4] > 0.7).all()


def _find_d20_video_2() -> Path | None:
    folder = REPO_ROOT / "video"
    if not folder.is_dir():
        return None
    for path in folder.glob("*.mp4"):
        if path.stat().st_size == D20_VIDEO_2_SIZE:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest() == D20_VIDEO_2_SHA256:
                return path
    return None


@pytest.mark.dataset
def test_t_det_09_on_a_real_frame_with_a_person_the_wrapper_equals_rtmlib(estimator, shipping: ShippingDetector):
    video = _find_d20_video_2()
    if video is None:
        pytest.skip("D20 video 2 not found under video/ (local third-party file, DEC-0036)")
    frame = next(iter(iter_frames(video, 300.0, 300.2))).image
    ours, theirs = shipping.detect(frame), estimator.detect(frame)
    assert len(ours) >= 1  # the presenter is in the picture
    _same_boxes(ours, theirs)


def _job(kind: str, model_path: Path, video: Path, tmp: Path) -> dict:
    return {
        "detector": kind, "model_path": str(model_path), "device": "cuda",
        "score": 0.3, "nms_iou": 0.65, "nms_iou_alt": 0.7,
        "repeats": 2, "warmup": 2, "n_speed_frames": 12, "baseline_s": 0.2,
        "sources": {"d20-v9": {"path": str(video), "rotation": 0}},
        "set_s": {"video": "d20-v9", "start_s": 0.0},
        "set_r": [{"id": "fc-900", "video": "d20-v9", "t_sec": 0.2}, {"id": "fc-901", "video": "d20-v9", "t_sec": 0.6}],
        "set_c": [{"clip": "c1", "video": "d20-v9", "start_s": 0.0, "end_s": 1.0}],
    }  # fmt: skip


def _check_run(result: dict, npz: Path, alt: bool) -> None:
    assert result["load_s"] > 0.0 and result["speed"]["n_frames"] == 12 and len(result["speed"]["repeats"]) == 2
    for rep in result["speed"]["repeats"]:
        assert rep["model_ms"]["p50"] > 0.0 and rep["end_to_end_ms"]["p50"] >= rep["model_ms"]["p50"]
    assert result["r"]["n_frames"] == 2 and result["c"]["c1"]["n_frames"] > 5
    assert result["image_shapes"]["d20-v9"] == [1080, 1920]
    arrays = np.load(npz)
    assert arrays["r_ids"].tolist() == ["fc-900", "fc-901"] and len(arrays["r_offsets"]) == 3
    assert len(arrays["c_c1_t_sec"]) == result["c"]["c1"]["n_frames"] == len(arrays["c_c1_offsets"]) - 1
    assert len(unpack(arrays["r_offsets"], arrays["r_dets"])) == 2
    assert ("r_dets_alt" in arrays.files) is alt  # the second NMS limit exists for YOLO11 only


def test_t_det_09_the_worker_runs_the_three_sets_with_the_shipping_detector(
    registry: ModelRegistry, hd_video_1080p: Path, tmp_path: Path
):
    result = run_job(_job("shipping", registry.by_role("det").path, hd_video_1080p, tmp_path), tmp_path / "ship.npz")
    _check_run(result, tmp_path / "ship.npz", alt=False)
    assert result["providers"] == ["CUDAExecutionProvider"]


@pytest.mark.skipif(not YOLO11_ONNX.exists(), reason="the YOLO11 file is not there (offline export of P3.09)")
def test_t_det_09_the_worker_runs_the_three_sets_with_yolo11(
    registry: ModelRegistry, hd_video_1080p: Path, tmp_path: Path
):
    result = run_job(_job("yolo11", YOLO11_ONNX, hd_video_1080p, tmp_path), tmp_path / "yolo.npz")
    _check_run(result, tmp_path / "yolo.npz", alt=True)


def test_t_det_09_a_cpu_session_before_a_cuda_session_does_not_break_cuda(registry: ModelRegistry):
    """BUG-0072: the tool reads the shape of a model file on the CPU and then builds a CUDA session in the same process.

    The DLL search path is per process, so this runs in a fresh one.
    """
    import subprocess
    import sys

    code = (
        "import sys\n"
        "from taiji_ai.bench.yolo_onnx import ShippingDetector, read_shapes\n"
        "path = sys.argv[1]\n"
        "read_shapes(path)\n"
        "det = ShippingDetector(path, device='cuda')\n"
        "print(det.session.get_providers()[0])\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, str(registry.by_role("det").path)],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2], check=False, timeout=300,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-1500:]
    assert done.stdout.strip().endswith("CUDAExecutionProvider")
