"""T-POSE-05a..d, 05g, 06a..g: ``run_pose`` with a scripted fake model on the synthetic videos (P3.02).

The cadence tests (05) replace ``iter_frames`` with a wrapper that writes the frame position into the image, so the
scripted fake knows which frame it is looking at; the tests of the decoding (06) use real frames and a script that does
not depend on the position. Everything runs on the CPU: no GPU, no model file.
"""

from __future__ import annotations

import itertools
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from helpers.fake_pose import Person, ScriptedPose, standing_person, with_frame_position
from helpers.media import tamper_pts
from taiji_ai.config import Settings
from taiji_ai.io.ingest import ingest_recording
from taiji_ai.pose import runner
from taiji_ai.pose.runner import PoseRunError, PoseRunParams, box_from_keypoints, run_pose

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not available")

FPS = 30
SIZE = (320, 240)  # (width, height) of the synthetic videos, upright
PERSON = standing_person()
NO_MARGIN = PoseRunParams(segment_margin_s=0.0)


def _ingest(video: Path, settings: Settings, camera: str = "camA") -> Path:
    meta = {"participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T01", "camera_id": camera}
    rec = ingest_recording(video, meta, settings)
    return settings.data_dir / "recordings" / rec.manifest.recording_id


@pytest.fixture
def rec(cfr_video: Path, ingest_settings: Settings) -> Path:
    return _ingest(cfr_video, ingest_settings)


@pytest.fixture
def positions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "iter_frames", with_frame_position(runner.iter_frames))


def _end_of_frame(k: int) -> float:
    """A segment end that includes frame ``k`` (and not frame k + 1) of a 30 fps video that starts at 0."""
    return k / FPS + 1e-6


def _persons_per_frame(out) -> list[int]:
    return [int(n) for n in np.diff(out.person_offsets)]


# --- T-POSE-05: the detector cadence -------------------------------------------------------------------------------


def test_t_pose_05a_the_detector_runs_every_n_frames_and_the_boxes_come_from_the_previous_keypoints(
    rec: Path, positions
):
    model = ScriptedPose(lambda pos: [PERSON])

    out = run_pose(rec, 0.0, _end_of_frame(22), model, params=NO_MARGIN)  # 23 frames, N = 5

    assert out.n_frames == 23
    assert model.detect_calls == [0, 5, 10, 15, 20]
    assert [pos for pos, _ in model.estimate_calls] == list(range(23))
    derived = box_from_keypoints(PERSON.keypoints, PERSON.scores, SIZE, margin=0.12, min_score=0.3, min_valid=6)
    for pos, boxes in model.estimate_calls:
        expected = np.array([PERSON.bbox], np.float32) if pos in (0, 5, 10, 15, 20) else derived[None, :]
        np.testing.assert_allclose(boxes, expected, atol=1e-4, err_msg=f"frame {pos}")
    assert list(out.from_detector) == [pos in (0, 5, 10, 15, 20) for pos in range(23)]
    assert out.stats.n_detector_calls == 5 and out.stats.n_pose_calls == 23 and out.stats.n_persons_total == 23


def test_t_pose_05b_n_equal_one_runs_the_detector_on_every_frame(rec: Path, positions):
    model = ScriptedPose(lambda pos: [PERSON])

    out = run_pose(rec, 0.0, _end_of_frame(9), model, params=PoseRunParams(detect_every_n=1, segment_margin_s=0.0))

    assert model.detect_calls == list(range(10))
    assert all(out.from_detector)


def test_t_pose_05b_the_result_does_not_depend_on_n_when_nobody_moves(rec: Path, positions):
    a = run_pose(
        rec,
        0.0,
        _end_of_frame(11),
        ScriptedPose(lambda pos: [PERSON]),
        params=PoseRunParams(detect_every_n=1, segment_margin_s=0.0),
    )
    b = run_pose(rec, 0.0, _end_of_frame(11), ScriptedPose(lambda pos: [PERSON]), params=NO_MARGIN)

    np.testing.assert_array_equal(a.keypoints, b.keypoints)
    np.testing.assert_array_equal(a.scores, b.scores)
    assert not np.array_equal(a.from_detector, b.from_detector)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"detect_every_n": 0},
        {"bbox_margin": -0.1},
        {"min_score": 1.5},
        {"min_valid_keypoints": 0},
        {"min_valid_keypoints": 27},
        {"segment_margin_s": -1.0},
    ],
)
def test_t_pose_05b_wrong_parameters_are_refused(kwargs: dict):
    with pytest.raises(ValueError):
        PoseRunParams(**kwargs)


def test_t_pose_05c_a_lost_person_runs_the_detector_at_once_and_again_until_found(rec: Path, positions):
    """The person is absent in frames 7 to 9: the detector must run at frame 7 (not wait for 10) and keep running."""
    model = ScriptedPose(lambda pos: [] if 7 <= pos <= 9 else [PERSON])

    out = run_pose(rec, 0.0, _end_of_frame(19), model, params=NO_MARGIN)

    assert model.detect_calls == [0, 5, 7, 8, 9, 10, 15]
    assert _persons_per_frame(out) == [1] * 7 + [0] * 3 + [1] * 10
    assert [pos for pos, _ in model.estimate_calls].count(
        7
    ) == 1  # the stale-box pass; nothing to estimate after the detector
    assert out.frame_index.tolist() == list(range(20))  # the three empty frames are still frames of the output


def test_t_pose_05d_two_persons_are_followed_in_order_and_a_newcomer_appears_at_the_next_detector_run(
    rec: Path, positions
):
    a, b, c = standing_person(cx=100.0), standing_person(cx=220.0), standing_person(cx=290.0)

    def script(pos: int) -> list[Person]:
        return [a] + ([b] if pos < 12 else []) + ([c] if pos >= 8 else [])

    model = ScriptedPose(script)

    out = run_pose(rec, 0.0, _end_of_frame(14), model, params=NO_MARGIN)

    assert model.detect_calls == [0, 5, 10]
    # B leaves at frame 12: its slot is estimated once more (a weak person is kept: raw layer), then followed no more.
    assert _persons_per_frame(out) == [2] * 10 + [3, 3, 3, 2, 2]
    mean_x = lambda p: float(p.keypoints[:, 0].mean())  # noqa: E731
    for frame in range(10):  # same order as the detector gave
        lo = out.person_offsets[frame]
        assert out.keypoints[lo, :, 0].mean() == pytest.approx(mean_x(a), abs=1e-3)
        assert out.keypoints[lo + 1, :, 0].mean() == pytest.approx(mean_x(b), abs=1e-3)
    first_with_c = out.person_offsets[10]
    assert out.from_detector[first_with_c + 2]  # C appears on the detector frame 10, not before
    ghost = out.person_offsets[12] + 1  # B at frame 12
    assert out.scores[ghost].max() < 0.3
    after = out.person_offsets[13]
    assert out.keypoints[after + 1, :, 0].mean() == pytest.approx(mean_x(c), abs=1e-3)


def test_t_pose_05g_persons_with_few_keypoints_are_kept_but_not_followed(rec: Path, positions):
    weak = standing_person(valid=3)
    model = ScriptedPose(lambda pos: [weak])

    out = run_pose(rec, 0.0, _end_of_frame(5), model, params=NO_MARGIN)

    assert model.detect_calls == [0, 1, 2, 3, 4, 5]  # nobody is followed, so the detector runs every frame
    assert _persons_per_frame(out) == [1] * 6
    assert all(out.from_detector)
    assert all(int((out.scores[i] >= 0.3).sum()) == 3 for i in range(6))  # stored as the model returned them


def test_t_pose_05g_a_weak_stale_box_pass_is_replaced_by_the_detector_pass_of_the_same_frame(rec: Path, positions):
    strong, weak = standing_person(), standing_person(valid=3)
    model = ScriptedPose(lambda pos: [strong] if pos < 3 else [weak])

    out = run_pose(rec, 0.0, _end_of_frame(5), model, params=NO_MARGIN)

    assert model.detect_calls == [0, 3, 4, 5]
    assert [pos for pos, _ in model.estimate_calls].count(3) == 2  # stale-box pass, then the repeat after the detector
    assert list(out.from_detector) == [True, False, False, True, True, True]
    assert _persons_per_frame(out) == [1] * 6


# --- T-POSE-06: reading the frames ---------------------------------------------------------------------------------


def _table(rec: Path) -> tuple[np.ndarray, np.ndarray]:
    t = pq.read_table(rec / "pts.parquet")
    return t["frame_index"].to_numpy(), t["t_sec"].to_numpy()


def test_t_pose_06a_only_the_window_is_read_and_frame_index_is_the_row_of_the_table(
    rec: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[tuple] = []
    real = runner.iter_frames

    def spy(path, t0=None, t1=None, rotation_deg=0):
        calls.append((t0, t1, rotation_deg))
        yield from real(path, t0, t1, rotation_deg)

    monkeypatch.setattr(runner, "iter_frames", spy)
    model = ScriptedPose(lambda pos: [PERSON], by_pixel=False)

    out = run_pose(rec, 0.8, 1.0, model, params=PoseRunParams(segment_margin_s=0.2))  # window 0.6 to 1.2 s

    index, t_sec = _table(rec)
    rows = np.flatnonzero((t_sec >= 0.6 - 1e-9) & (t_sec <= 1.2 + 1e-9))
    assert out.frame_index.tolist() == index[rows].tolist() == list(range(18, 37))
    np.testing.assert_allclose(out.t_sec, t_sec[rows], atol=1e-12)
    assert np.all(np.diff(out.t_sec) > 0)
    assert (
        len(calls) == 1
        and calls[0][0] == pytest.approx(t_sec[rows[0]])
        and calls[0][1] == pytest.approx(t_sec[rows[-1]])
    )
    assert len(model.estimate_calls) == len(rows)  # nothing outside the window reached the model
    assert out.segment_s == (0.8, 1.0)


def test_t_pose_06b_a_variable_frame_rate_video_gets_the_real_timestamps(vfr_video: Path, ingest_settings: Settings):
    rec = _ingest(vfr_video, ingest_settings)
    model = ScriptedPose(lambda pos: [PERSON], by_pixel=False)

    out = run_pose(rec, 0.0, 2.0, model)

    index, t_sec = _table(rec)
    np.testing.assert_allclose(out.t_sec, t_sec, atol=1e-12)
    assert out.frame_index.tolist() == index.tolist()
    assert np.ptp(np.diff(out.t_sec)) > 0.01  # the intervals are not constant: this is VFR


def test_t_pose_06c_the_picture_given_to_the_model_is_upright(rotated_video: Path, ingest_settings: Settings):
    rec = _ingest(rotated_video, ingest_settings)
    model = ScriptedPose(lambda pos: [PERSON], by_pixel=False)

    out = run_pose(rec, 0.0, 1.0, model)

    assert out.display_rotation == 90
    assert out.image_size == (240, 320)  # coded 320x240, shown turned by 90 degrees: 240 wide, 320 high
    assert model.shapes[0][:2] == (320, 240)


@pytest.mark.parametrize(
    ("start", "end", "first", "last_t"),
    [(0.1, 0.3, 0, 1.3), (1.5, 1.9, None, 2.0)],
    ids=["start_of_the_file_is_clipped", "end_of_the_file_is_clipped"],
)
def test_t_pose_06d_a_window_beyond_the_file_is_clipped(
    rec: Path, start: float, end: float, first: int | None, last_t: float
):
    model = ScriptedPose(lambda pos: [PERSON], by_pixel=False)

    out = run_pose(rec, start, end, model)

    index, t_sec = _table(rec)
    if first is not None:
        assert out.frame_index[0] == first
    else:
        assert out.frame_index[-1] == index[-1]
    assert out.t_sec[-1] <= last_t + 1e-9 and out.t_sec[0] >= 0.0


def test_t_pose_06d_a_video_that_does_not_start_at_pts_zero_is_timed_from_the_stream_start(
    offset_video: Path, ingest_settings: Settings
):
    rec = _ingest(offset_video, ingest_settings)
    model = ScriptedPose(lambda pos: [PERSON], by_pixel=False)

    out = run_pose(rec, 0.2, 0.5, model)

    assert out.frame_index[0] == 0 and out.t_sec[0] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    ("start", "end"),
    [(1.0, 1.0), (1.2, 1.0), (5.0, 6.0), (-3.0, -1.0), (float("nan"), 1.0), (0.0, float("inf"))],
    ids=["empty", "reversed", "after_the_file", "before_the_file", "nan", "infinite"],
)
def test_t_pose_06d_a_bad_segment_is_refused(rec: Path, start: float, end: float):
    with pytest.raises(PoseRunError, match="segment"):
        run_pose(rec, start, end, ScriptedPose(lambda pos: [PERSON], by_pixel=False))


def test_t_pose_06e_a_table_that_does_not_match_the_file_is_refused(cfr_video: Path, ingest_settings: Settings):
    rec = _ingest(cfr_video, ingest_settings)
    tamper_pts(rec, drop_last=1)  # the file has 60 frames, the table 59
    with pytest.raises(PoseRunError, match=r"pts\.parquet"):
        run_pose(rec, 0.0, 2.0, ScriptedPose(lambda pos: [PERSON], by_pixel=False))


def test_t_pose_06e_a_shifted_table_is_refused(cfr_video: Path, ingest_settings: Settings):
    rec = _ingest(cfr_video, ingest_settings)
    tamper_pts(rec, shift_s=0.5)
    with pytest.raises(PoseRunError, match=r"pts\.parquet"):
        run_pose(rec, 0.0, 2.0, ScriptedPose(lambda pos: [PERSON], by_pixel=False))


def test_t_pose_06f_a_model_failure_names_the_frame_and_gives_no_result(rec: Path, positions):
    model = ScriptedPose(lambda pos: [PERSON], fail_at=3)

    with pytest.raises(PoseRunError, match="frame") as info:
        run_pose(rec, 0.0, _end_of_frame(9), model, params=NO_MARGIN)

    assert isinstance(info.value.__cause__, RuntimeError)
    assert "3" in str(info.value)


def test_t_pose_06f_a_missing_recording_or_table_is_refused(rec: Path, tmp_path: Path):
    model = ScriptedPose(lambda pos: [PERSON], by_pixel=False)
    with pytest.raises(PoseRunError, match="recording"):
        run_pose(tmp_path / "nope", 0.0, 1.0, model)
    (rec / "pts.parquet").chmod(0o600)
    (rec / "pts.parquet").unlink()
    with pytest.raises(PoseRunError, match=r"pts\.parquet"):
        run_pose(rec, 0.0, 1.0, model)


def test_t_pose_06g_two_runs_are_identical_and_the_arrays_have_the_documented_shapes(rec: Path, positions):
    a = run_pose(
        rec, 0.0, _end_of_frame(14), ScriptedPose(lambda pos: [PERSON, standing_person(cx=250.0)]), params=NO_MARGIN
    )
    b = run_pose(
        rec, 0.0, _end_of_frame(14), ScriptedPose(lambda pos: [PERSON, standing_person(cx=250.0)]), params=NO_MARGIN
    )

    assert a.equals(b)
    f, d = a.n_frames, int(a.person_offsets[-1])
    assert (f, d) == (15, 30)
    assert a.frame_index.dtype == np.int32 and a.frame_index.shape == (f,)
    assert a.t_sec.dtype == np.float64 and a.t_sec.shape == (f,)
    assert a.person_offsets.dtype == np.int64 and a.person_offsets.shape == (f + 1,)
    assert a.person_offsets[0] == 0 and np.all(np.diff(a.person_offsets) >= 0)
    assert a.bboxes.dtype == np.float32 and a.bboxes.shape == (d, 4)
    assert a.keypoints.dtype == np.float32 and a.keypoints.shape == (d, 26, 2)
    assert a.scores.dtype == np.float32 and a.scores.shape == (d, 26)
    assert a.from_detector.dtype == np.bool_ and a.from_detector.shape == (d,)
    assert a.params == NO_MARGIN
    assert a.model_fingerprint == ScriptedPose.model_fingerprint and a.providers == ScriptedPose.providers


def test_t_pose_06g_a_frame_without_a_person_is_stored_as_zero_persons_not_as_zeros(rec: Path, positions):
    out = run_pose(rec, 0.0, _end_of_frame(4), ScriptedPose(lambda pos: []), params=NO_MARGIN)

    assert out.n_frames == 5 and _persons_per_frame(out) == [0] * 5
    assert out.keypoints.shape == (0, 26, 2) and out.bboxes.shape == (0, 4) and out.from_detector.shape == (0,)


def test_t_pose_06h_keypoints_outside_the_image_are_kept_as_the_model_returned_them(rec: Path, positions):
    """The raw layer is not clamped or filled (AGENTS.md 5.1): a keypoint beyond the border stays where it is."""
    person = standing_person()
    keypoints = person.keypoints.copy()
    keypoints[0] = (-25.0, 120.0)  # left of the image (the image is 320 wide)
    keypoints[1] = (400.0, 500.0)  # right of and below the image (320 x 240)
    out = run_pose(
        rec,
        0.0,
        _end_of_frame(2),
        ScriptedPose(lambda pos: [Person(person.bbox, keypoints, person.scores)]),
        params=NO_MARGIN,
    )

    np.testing.assert_array_equal(out.keypoints[:, 0], np.tile(keypoints[0], (3, 1)))
    np.testing.assert_array_equal(out.keypoints[:, 1], np.tile(keypoints[1], (3, 1)))


def test_t_pose_06e_a_file_that_ends_before_its_table_is_refused(rec: Path, monkeypatch: pytest.MonkeyPatch):
    real = runner.iter_frames

    def ends_early(path, t0=None, t1=None, rotation_deg=0):
        yield from itertools.islice(real(path, t0, t1, rotation_deg), 10)

    monkeypatch.setattr(runner, "iter_frames", ends_early)

    with pytest.raises(PoseRunError, match=r"decoded 10 frames.*pts\.parquet"):
        run_pose(rec, 0.0, 2.0, ScriptedPose(lambda pos: [PERSON], by_pixel=False))


def test_t_pose_06e_a_table_a_few_milliseconds_early_is_refused(cfr_video: Path, ingest_settings: Settings):
    """Same frame count, same ticks, only ``t_sec`` is 10 ms off: nothing but the time check can see it."""
    rec = _ingest(cfr_video, ingest_settings)
    tamper_pts(rec, shift_s=-0.01)

    with pytest.raises(PoseRunError, match=r"pts\.parquet"):
        run_pose(rec, 0.0, 2.0, ScriptedPose(lambda pos: [PERSON], by_pixel=False))


def test_t_pose_06e_a_frame_size_that_changes_is_refused(rec: Path, monkeypatch: pytest.MonkeyPatch):
    real = runner.iter_frames

    def shrinks(path, t0=None, t1=None, rotation_deg=0):
        for i, frame in enumerate(real(path, t0, t1, rotation_deg)):
            yield replace(frame, image=frame.image[:100] if i == 5 else frame.image)

    monkeypatch.setattr(runner, "iter_frames", shrinks)

    with pytest.raises(PoseRunError, match="frame size"):
        run_pose(rec, 0.0, 2.0, ScriptedPose(lambda pos: [PERSON], by_pixel=False))


def _edit_table(rec: Path, column: str, row: int, delta: float) -> None:
    """Change one value of ``pts.parquet`` in the middle (the first and last rows, the count and the order stay)."""
    path = rec / "pts.parquet"
    table = pq.read_table(path)
    metadata = table.schema.metadata
    field = table.schema.field(column)
    values = table[column].to_numpy().copy()
    values[row] += delta
    table = table.set_column(table.schema.get_field_index(column), field, pa.array(values, type=field.type))
    pq.write_table(table.replace_schema_metadata(metadata), path)


def test_t_pose_06e_one_wrong_pts_tick_in_the_middle_of_the_table_is_refused(
    cfr_video: Path, ingest_settings: Settings
):
    rec = _ingest(cfr_video, ingest_settings)
    _edit_table(rec, "pts", 30, 7)

    with pytest.raises(PoseRunError, match=r"frame 30 .*pts\.parquet"):
        run_pose(rec, 0.0, 2.0, ScriptedPose(lambda pos: [PERSON], by_pixel=False))


def test_t_pose_06e_one_wrong_t_sec_in_the_middle_of_the_table_is_refused(cfr_video: Path, ingest_settings: Settings):
    rec = _ingest(cfr_video, ingest_settings)
    _edit_table(rec, "t_sec", 30, 0.005)

    with pytest.raises(PoseRunError, match=r"frame 30 .*pts\.parquet"):
        run_pose(rec, 0.0, 2.0, ScriptedPose(lambda pos: [PERSON], by_pixel=False))
