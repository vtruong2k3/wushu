"""T-POSE-05f and T-POSE-07: ``run_pose`` with the real models on the GPU (P3.02).

* T-POSE-05f: a 1080p video with nobody in it: no crash, zero persons, the detector on every frame, CUDA providers.
* T-POSE-08j: the same clip saved to ``pose_raw.npz`` and loaded gives the same pose.
* T-POSE-07: a 10 s clip of a real video (D20, video 2 of the registry, found by its size and SHA-256, never by name): a
  person in every frame, two runs agree, and N = 5 agrees with N = 1 within the tolerances measured on 2026-11-16.
  The file is local and third-party (DEC-0036: internal development only): the test is skipped when it is absent and
  stores no frame, no keypoint and no golden number in the repository.

Skipped when the models or CUDA are missing (``gpu`` marker) or when the file is missing (``dataset`` marker).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from taiji_ai.config import Settings, get_settings
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.pose.raw_io import load_pose_raw, save_pose_raw
from taiji_ai.pose.runner import PoseRunParams, run_pose
from taiji_ai.store.artifacts import sha256_file

pytestmark = pytest.mark.gpu

D20_VIDEO_2_SIZE = 257_287_499  # bytes, as listed in Docs/DATASET_REGISTRY_TAIJI.md (D20)
D20_VIDEO_2_SHA256 = "50a6cd2f383ccd8fc3da77b94d300bd80cd5d3f5cf208a13aa12e6004e35bec8"
REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def estimator():
    s = get_settings()
    if not s.registry_path.exists():
        pytest.skip("models not fetched (run tools/fetch_models.py)")
    import onnxruntime as ort

    if "CUDAExecutionProvider" not in ort.get_available_providers():
        pytest.skip("CUDA provider not available")
    from taiji_ai.pose.registry import ModelRegistry
    from taiji_ai.pose.rtm import PoseEstimator

    return PoseEstimator(ModelRegistry(s.registry_path), device="cuda")


def _ingest(video: Path, settings: Settings) -> Path:
    meta = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T01", "camera_id": "camA"}
    rec = ingest_recording(video, meta, settings)
    return settings.data_dir / "recordings" / rec.manifest.recording_id


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


def test_t_pose_05f_a_video_with_nobody_gives_zero_persons_and_a_detector_call_per_frame(
    estimator, hd_video_1080p: Path, ingest_settings: Settings
):
    rec = _ingest(hd_video_1080p, ingest_settings)

    out = run_pose(rec, 0.0, 1.0, estimator)

    assert out.n_frames > 0 and int(out.person_offsets[-1]) == 0
    assert out.keypoints.shape == (0, 26, 2)
    assert out.stats.n_detector_calls == out.n_frames  # nobody is followed, so the detector runs on every frame
    assert out.stats.n_pose_calls == 0
    assert out.providers == {"det": "CUDAExecutionProvider", "pose": "CUDAExecutionProvider"}
    assert out.image_size == (1920, 1080)


@pytest.mark.dataset
def test_t_pose_07_a_real_clip_is_stable_between_runs_and_between_detector_cadences(
    estimator, ingest_settings: Settings
):
    video = _find_d20_video_2()
    if video is None:
        pytest.skip("D20 video 2 not found under video/ (local third-party file, DEC-0036)")
    rec = _ingest(video, ingest_settings)

    a = run_pose(rec, 300.0, 310.0, estimator, params=PoseRunParams(detect_every_n=5))
    b = run_pose(rec, 300.0, 310.0, estimator, params=PoseRunParams(detect_every_n=5))
    every_frame = run_pose(rec, 300.0, 310.0, estimator, params=PoseRunParams(detect_every_n=1))

    # A person in (almost) every frame, one person: measured on 2026-11-16: 289 of 289 frames, always one person.
    assert float((a.n_persons >= 1).mean()) >= 0.95
    assert float(np.median(a.n_persons)) == 1.0
    assert a.image_size == (1920, 1080) and a.display_rotation == 0
    assert np.all(np.diff(a.t_sec) > 0) and a.t_sec[0] >= 299.0 - 1e-6 and a.t_sec[-1] <= 311.0 + 1e-6

    # Two runs of the same input: measured bit-identical on this machine; 0.5 px leaves room for another GPU or driver.
    assert np.array_equal(a.person_offsets, b.person_offsets)
    assert float(np.abs(a.keypoints - b.keypoints).max()) <= 0.5

    # N = 5 against N = 1 (the detector every frame): the person count agrees; the keypoints of the one person differ
    # by a median of 1.6 px and a 95th percentile of 5.7 px (1080p) when measured; the limits are about twice that.
    # They guard against a change of the cadence logic. They are not an accuracy claim: P3.07 measures the effect of N.
    assert float((a.n_persons == every_frame.n_persons).mean()) >= 0.95
    distances = []
    for i in range(a.n_frames):
        if a.n_persons[i] == every_frame.n_persons[i] >= 1:
            lo, lo1 = a.person_offsets[i], every_frame.person_offsets[i]
            distances.append(np.linalg.norm(a.keypoints[lo] - every_frame.keypoints[lo1], axis=1))
    d = np.concatenate(distances)
    assert float(np.median(d)) <= 3.0
    assert float(np.percentile(d, 95)) <= 12.0


@pytest.mark.dataset
def test_t_pose_08j_a_real_clip_saved_and_loaded_is_the_same(estimator, ingest_settings: Settings, tmp_path: Path):
    video = _find_d20_video_2()
    if video is None:
        pytest.skip("D20 video 2 not found under video/ (local third-party file, DEC-0036)")
    rec = _ingest(video, ingest_settings)
    raw = run_pose(rec, 300.0, 310.0, estimator)

    path = tmp_path / "pose_raw.npz"
    digest = save_pose_raw(path, raw)
    loaded = load_pose_raw(path)

    assert loaded.equals(raw) and digest == sha256_file(path)
    assert raw.n_frames > 250 and path.stat().st_size < 2_000_000  # measured on 2026-11-16: see the task file
