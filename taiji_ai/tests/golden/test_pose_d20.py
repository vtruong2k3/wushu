"""T-POSE-05f and T-POSE-07: ``run_pose`` with the real models on the GPU (P3.02).

* T-POSE-05f: a 1080p video with nobody in it: no crash, zero persons, the detector on every frame, CUDA providers.
* T-TRK-02g: on real clips the presenter keeps one track over the whole clip.
* T-TRK-01g: a real frame with two people: the presenter is the chosen target.
* T-TRK-05g: the presenter's persons removed for 0.3 s, 1 s and for good from a real clip (the only real absences
  available; P1.09 has none): lost, target_lost, re-attached by the real cost, or never given to anybody else.
* T-POSE-08j: the same clip saved to ``pose_raw.npz`` and loaded gives the same pose.
* T-POSE-07: a 10 s clip of a real video (D20, video 2 of the registry, found by its size and SHA-256, never by name): a
  person in every frame, two runs agree, and N = 5 agrees with N = 1 within the tolerances measured on 2026-11-16.
  The file is local and third-party (DEC-0036: internal development only): the test is skipped when it is absent and
  stores no frame, no keypoint and no golden number in the repository.

Skipped when the models or CUDA are missing (``gpu`` marker) or when the file is missing (``dataset`` marker).
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import numpy as np
import pytest

from taiji_ai.config import Settings, get_settings
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.pose.raw_io import load_pose_raw, save_pose_raw
from taiji_ai.pose.runner import PoseRaw, PoseRunParams, run_pose
from taiji_ai.store.artifacts import sha256_file
from taiji_ai.track.associate import associate_tracks, track_of_person
from taiji_ai.track.state import LOST, TARGET_LOST, TRACKED, TargetStateParams, resolve_target
from taiji_ai.track.target import select_target

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
    assert raw.n_frames > 250 and path.stat().st_size < 500_000  # measured 2026-11-16: 82 KB


@pytest.mark.dataset
def test_t_trk_01g_on_a_real_frame_with_two_people_the_presenter_is_chosen(estimator, ingest_settings: Settings):
    """Segment 470 to 472 s of D20 video 2: the presenter (large) and a tiny person far behind; checked on the image."""
    video = _find_d20_video_2()
    if video is None:
        pytest.skip("D20 video 2 not found under video/ (local third-party file, DEC-0036)")
    rec = _ingest(video, ingest_settings)
    raw = run_pose(rec, 470.0, 472.0, estimator)

    sel = select_target(raw)

    lo, hi = raw.person_offsets[sel.frame_pos], raw.person_offsets[sel.frame_pos + 1]
    areas = (raw.bboxes[lo:hi, 2] - raw.bboxes[lo:hi, 0]) * (raw.bboxes[lo:hi, 3] - raw.bboxes[lo:hi, 1])
    assert hi - lo == 2 and sel.n_candidates == 2  # measured 2026-11-16: the presenter and one tiny person
    assert sel.person_row == lo + int(np.argmax(areas)) and not sel.ambiguous
    assert sel.runner_up_ratio is not None and sel.runner_up_ratio < 0.05  # measured 0.004
    assert not sel.weak and sel.offset_from_start_s == pytest.approx(0.0, abs=1e-6)


@pytest.mark.dataset
@pytest.mark.parametrize("start", [470.0, 660.0], ids=["two_people", "up_to_four_people"])
def test_t_trk_02g_on_a_real_clip_the_presenter_keeps_one_track_from_the_first_to_the_last_frame(
    estimator, ingest_settings: Settings, start: float
):
    video = _find_d20_video_2()
    if video is None:
        pytest.skip("D20 video 2 not found under video/ (local third-party file, DEC-0036)")
    rec = _ingest(video, ingest_settings)
    raw = run_pose(rec, start, start + 10.0, estimator)

    tracks = associate_tracks(raw)
    chosen = select_target(raw)

    main = track_of_person(tracks, chosen.person_row)
    rows = np.flatnonzero(tracks.track_id == main)
    frame_of_row = np.searchsorted(raw.person_offsets, rows, side="right") - 1
    assert main >= 0 and rows.size == raw.n_frames and np.array_equal(frame_of_row, np.arange(raw.n_frames))
    assert tracks.track_first_frame[main] == 0 and tracks.track_last_frame[main] == raw.n_frames - 1
    costs = tracks.match_cost[
        rows[1:]
    ]  # measured 2026-11-16: largest 0.125 (470 s), 0.143 (660 s) with the old variants; 0.036 here
    assert float(costs.max()) < 0.2 < tracks.params.max_cost
    margins = tracks.match_margin[rows[1:]]
    margins = margins[np.isfinite(margins)]  # NaN where nobody else was around
    assert margins.size > 0 and float(np.percentile(margins, 5)) > 0.3  # measured: 0.62 to 0.67


def _without_rows(raw: PoseRaw, drop: np.ndarray) -> PoseRaw:
    """The same pose with some person rows removed (a simulated absence); frames and times are untouched."""
    keep = ~drop
    frame_of_row = np.searchsorted(raw.person_offsets, np.arange(drop.size), side="right") - 1
    counts = np.bincount(frame_of_row[keep], minlength=raw.n_frames)
    return dataclasses.replace(
        raw,
        person_offsets=np.concatenate([[0], np.cumsum(counts)]).astype(np.int64),
        bboxes=raw.bboxes[keep],
        keypoints=raw.keypoints[keep],
        scores=raw.scores[keep],
        from_detector=raw.from_detector[keep],
        stats=dataclasses.replace(raw.stats, n_persons_total=int(keep.sum())),
    )


@pytest.mark.dataset
@pytest.mark.parametrize("start", [470.0, 660.0], ids=["two_people", "up_to_four_people"])
def test_t_trk_05g_a_real_clip_with_the_presenter_removed_for_a_while_or_for_good(
    estimator, ingest_settings: Settings, start: float
):
    """The presenter's person rows are removed from 3 s after the start: for 0.3 s, for 1 s, and for good.

    This is a simulated absence on real poses (the presenter stays in the picture in the video; P1.09 has no real
    absence yet), so it tests the cost of a return to the same place after real movement and the refusal to give frames
    to anybody else, not a real walk out of the frame. Measured 2026-11-16 (deterministic on this machine).
    """
    video = _find_d20_video_2()
    if video is None:
        pytest.skip("D20 video 2 not found under video/ (local third-party file, DEC-0036)")
    rec = _ingest(video, ingest_settings)
    raw = run_pose(rec, start, start + 10.0, estimator)
    tracks = associate_tracks(raw)
    main = track_of_person(tracks, select_target(raw).person_row)
    main_rows = np.flatnonzero(tracks.track_id == main)
    frame_of_row = np.searchsorted(raw.person_offsets, np.arange(raw.keypoints.shape[0]), side="right") - 1
    presenter_row = {int(frame_of_row[r]): int(r) for r in main_rows}  # the presenter has a person in every frame
    assert len(presenter_row) == raw.n_frames
    first = int(np.searchsorted(raw.t_sec, start + 3.0))

    def run(seconds: float | None):
        end = raw.n_frames if seconds is None else int(np.searchsorted(raw.t_sec, start + 3.0 + seconds))
        drop = np.zeros(raw.keypoints.shape[0], bool)
        drop[[presenter_row[f] for f in range(first, end)]] = True
        raw2 = _without_rows(raw, drop)
        tracks2 = associate_tracks(raw2)
        return end, resolve_target(raw2, tracks2, select_target(raw2))

    def presenter_frames_are_the_presenters(tt) -> bool:
        return all(
            np.array_equal(tt.keypoints[f], raw.keypoints[presenter_row[f]])
            for f in np.flatnonzero(tt.status == TRACKED)
        )

    # 0.3 s: only lost, then re-attached
    end, tt = run(0.3)
    assert (tt.status[first:end] == LOST).all() and not (tt.status == TARGET_LOST).any()
    assert (tt.status[end:] == TRACKED).all() and presenter_frames_are_the_presenters(tt)
    assert [e.kind for e in tt.meta.events] == ["lost", "reattached"] and not tt.meta.needs_reselect
    assert float(tt.reattach_cost[end]) <= TargetStateParams().reattach_cost

    # 1 s: lost for 0.5 s, then target_lost, then re-attached by the cost of the real poses
    end, tt = run(1.0)
    assert (tt.status[first:end] != TRACKED).all() and (tt.status[:first] == TRACKED).all()
    assert tt.meta.counts.n_lost > 0 and tt.meta.counts.n_target_lost > 0
    assert (tt.status[end:] == TRACKED).all() and presenter_frames_are_the_presenters(tt)
    kinds = [e.kind for e in tt.meta.events]
    assert kinds[0] == "lost" and kinds[-1] == "reattached" and "target_lost" in kinds
    assert set(kinds) <= {"lost", "target_lost", "refused", "reattached"}
    # Other real people may start a track while the presenter is away (clip 660 s: two of them, costs 0.737 and 0.738
    # against the presenter's last pose): they are refused; the presenter's own return cost 0.035 there.
    assert all(e.cost > 0.65 and e.reason == "over_threshold" for e in tt.meta.events if e.kind == "refused")
    assert not tt.meta.needs_reselect and float(tt.reattach_cost[end]) <= TargetStateParams().reattach_cost

    # for good: nobody else takes his place, the user is asked
    end, tt = run(None)
    assert (tt.status[first:] != TRACKED).all() and tt.status[-1] == TARGET_LOST
    assert tt.meta.counts.n_reattached == 0 and tt.meta.needs_reselect
    assert tt.meta.reselect_reason in ("target_lost_at_end", "reattach_refused")
    assert presenter_frames_are_the_presenters(tt)
