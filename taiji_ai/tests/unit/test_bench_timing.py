"""T-BENCH-01, T-BENCH-02: timing statistics, the timing wrapper of the pose model and the per-frame clock (P3.07).

No GPU and no video: times are numbers or come from a fake clock.
"""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.bench import BenchError
from taiji_ai.bench.timing import (
    FrameClock,
    TimedModel,
    fps_equivalent_rtf,
    ms_per_frame,
    percentiles,
    rtf,
    video_span_s,
    window_rtf,
)


def fake_clock(*values: float):
    """A clock that returns the given values one after the other (an error if it is asked for more)."""
    it = iter(values)
    return lambda: next(it)


# --- T-BENCH-01a: video span, RTF, windows ----------------------------------------------------------------------------
def test_t_bench_01a_the_video_span_is_the_time_the_frames_cover_not_the_last_timestamp():
    t = np.arange(4) / 30.0
    assert video_span_s(t) == pytest.approx(4 / 30.0)  # four frames of 1/30 s cover 4/30 s
    uneven = np.array([0.0, 0.1, 0.3, 0.4])  # median step 0.1
    assert video_span_s(uneven) == pytest.approx(0.4 + 0.1)


@pytest.mark.parametrize(
    "t",
    [np.array([0.0]), np.array([]), np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.5]), np.array([0.0, np.nan, 1.0])],
    ids=["one frame", "none", "repeated time", "going back", "NaN"],
)
def test_t_bench_01a_a_span_that_cannot_be_computed_is_refused(t: np.ndarray):
    with pytest.raises(BenchError):
        video_span_s(t)


def test_t_bench_01a_rtf_is_processing_seconds_over_video_seconds():
    assert rtf(10.0, 32.0) == pytest.approx(0.3125)
    assert rtf(0.0, 32.0) == 0.0
    for elapsed, span in ((-1.0, 32.0), (float("nan"), 32.0), (1.0, 0.0), (1.0, -3.0), (1.0, float("inf"))):
        with pytest.raises(BenchError):
            rtf(elapsed, span)


def test_t_bench_01a_ms_per_frame_and_the_rtf_at_another_frame_rate():
    assert ms_per_frame(3.0, 300) == pytest.approx(10.0)
    assert fps_equivalent_rtf(10.0, 30.0) == pytest.approx(0.3)
    assert fps_equivalent_rtf(10.0, 60.0) == pytest.approx(0.6)  # a phone at 60 fps doubles the real-time factor
    with pytest.raises(BenchError):
        ms_per_frame(3.0, 0)
    with pytest.raises(BenchError):
        fps_equivalent_rtf(10.0, 0.0)


def test_t_bench_01a_window_rtf_is_the_work_of_the_frames_of_each_second_of_video():
    t = np.arange(30) / 10.0  # 3.0 s of video at 10 fps
    latency = np.concatenate([np.full(10, 0.05), np.full(10, 0.10), np.full(10, 0.20)])

    out = window_rtf(latency, t)

    assert out.values == pytest.approx([0.5, 1.0, 2.0])
    assert out.n_empty_windows == 0 and out.n_dropped_frames == 0


def test_t_bench_01a_the_last_partial_window_is_dropped_and_counted():
    t = np.arange(25) / 10.0  # 2.5 s: two full windows and five frames of a third
    out = window_rtf(np.full(25, 0.1), t)
    assert out.values == pytest.approx([1.0, 1.0])
    assert out.n_dropped_frames == 5


def test_t_bench_01a_windows_follow_the_video_time_not_the_count_of_frames():
    # ten frames in [0, 1), a gap of one second, ten frames in [2, 3): the middle window has no frames
    t = np.concatenate([np.arange(10) / 10.0, 2.0 + np.arange(10) / 10.0])
    out = window_rtf(np.full(20, 0.1), t)
    assert out.values == pytest.approx([1.0, 1.0])
    assert out.n_empty_windows == 1 and out.n_dropped_frames == 0


@pytest.mark.parametrize(
    ("latency", "t", "window_s"),
    [
        (np.array([]), np.array([]), 1.0),
        (np.full(3, 0.1), np.arange(4) / 10.0, 1.0),  # lengths differ
        (np.array([0.1, -0.1, 0.1]), np.arange(3) / 10.0, 1.0),
        (np.array([0.1, np.nan, 0.1]), np.arange(3) / 10.0, 1.0),
        (np.full(3, 0.1), np.array([0.0, 0.1, 0.1]), 1.0),
        (np.full(30, 0.1), np.arange(30) / 10.0, 0.0),
        (np.full(5, 0.1), np.arange(5) / 10.0, 1.0),  # no full window at all
    ],
    ids=["empty", "length", "negative", "NaN", "time", "window", "no full window"],
)
def test_t_bench_01a_bad_window_input_is_refused(latency: np.ndarray, t: np.ndarray, window_s: float):
    with pytest.raises(BenchError):
        window_rtf(latency, t, window_s)


# --- T-BENCH-01b: percentiles -----------------------------------------------------------------------------------------
def test_t_bench_01b_percentiles_of_known_values():
    out = percentiles(np.arange(1.0, 101.0), (50, 95, 99))
    assert out[50] == pytest.approx(50.5) and out[95] == pytest.approx(95.05) and out[99] == pytest.approx(99.01)
    assert list(out) == [50, 95, 99]
    assert percentiles(np.array([7.0]), (50, 99)) == {50: 7.0, 99: 7.0}


@pytest.mark.parametrize("values", [np.array([]), np.array([1.0, np.nan]), np.array([1.0, np.inf])])
def test_t_bench_01b_percentiles_refuse_empty_or_non_finite_values(values: np.ndarray):
    with pytest.raises(BenchError):
        percentiles(values)


def test_t_bench_01b_percentiles_refuse_a_level_outside_0_100():
    with pytest.raises(BenchError):
        percentiles(np.arange(3.0), (101,))


# --- T-BENCH-02: the timing wrapper and the frame clock -------------------------------------------------------------
class FakeModel:
    providers = {"det": "CUDAExecutionProvider", "pose": "CUDAExecutionProvider"}
    model_fingerprint = {"det": "0" * 64, "pose": "1" * 64}

    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on

    def detect(self, frame):
        if self.fail_on == "detect":
            raise RuntimeError("detector failed")
        return np.zeros((1, 4), np.float32)

    def estimate(self, frame, boxes):
        if self.fail_on == "estimate":
            raise RuntimeError("pose failed")
        return ("pose result", boxes)


def test_t_bench_02_the_wrapper_forwards_the_calls_and_adds_up_their_durations():
    model = TimedModel(FakeModel(), clock=fake_clock(0.0, 2.0, 10.0, 13.0, 20.0, 20.5))  # 2 s, 3 s, 0.5 s
    frame = np.zeros((4, 4, 3), np.uint8)

    boxes = model.detect(frame)
    result = model.estimate(frame, boxes)
    model.detect(frame)

    assert boxes.shape == (1, 4) and result[0] == "pose result" and result[1] is boxes
    assert model.detect_s == pytest.approx(2.0 + 0.5) and model.estimate_s == pytest.approx(3.0)
    assert (model.n_detect, model.n_estimate) == (2, 1)


def test_t_bench_02_the_wrapper_is_a_pose_model_for_run_pose():
    model = TimedModel(FakeModel())
    assert model.providers == FakeModel.providers and model.model_fingerprint == FakeModel.model_fingerprint


@pytest.mark.parametrize("fail_on", ["detect", "estimate"])
def test_t_bench_02_a_failing_call_is_not_swallowed_and_not_counted(fail_on: str):
    model = TimedModel(FakeModel(fail_on), clock=fake_clock(0.0, 1.0))
    frame = np.zeros((2, 2, 3), np.uint8)
    with pytest.raises(RuntimeError, match="failed"):
        if fail_on == "detect":
            model.detect(frame)
        else:
            model.estimate(frame, np.zeros((1, 4), np.float32))
    assert (model.n_detect, model.n_estimate) == (0, 0) and model.detect_s == 0.0 and model.estimate_s == 0.0


def test_t_bench_02_reset_starts_the_sums_again():
    model = TimedModel(FakeModel(), clock=fake_clock(0.0, 1.0))
    model.detect(np.zeros((2, 2, 3), np.uint8))
    model.reset()
    assert (model.n_detect, model.n_estimate) == (0, 0) and model.detect_s == 0.0 and model.estimate_s == 0.0


def test_t_bench_02_the_frame_clock_gives_the_time_between_frames_from_the_start_mark():
    clock = FrameClock(clock=fake_clock(100.0, 100.5, 101.5, 101.75))
    clock.start()
    for position, t in enumerate((0.0, 1 / 30, 2 / 30)):
        clock.on_frame(position, t)
    assert clock.latencies() == pytest.approx([0.5, 1.0, 0.25])
    assert clock.t_sec == pytest.approx([0.0, 1 / 30, 2 / 30])
    assert clock.n_frames == 3


def test_t_bench_02_the_frame_clock_start_resets_and_refuses_misuse():
    clock = FrameClock(clock=fake_clock(0.0, 1.0, 5.0, 6.0))
    with pytest.raises(BenchError, match="start"):
        clock.on_frame(0, 0.0)
    clock.start()
    clock.on_frame(0, 0.0)
    with pytest.raises(BenchError, match="position"):  # a frame was skipped
        clock.on_frame(2, 0.2)
    clock.start()  # a new pass: nothing of the old one is kept
    clock.on_frame(0, 0.0)
    assert clock.latencies() == pytest.approx([1.0]) and clock.n_frames == 1


def test_t_bench_02_the_frame_clock_without_frames_has_no_latencies():
    clock = FrameClock(clock=fake_clock(0.0))
    with pytest.raises(BenchError, match="start"):
        clock.latencies()
    clock.start()
    with pytest.raises(BenchError, match="frame"):
        clock.latencies()


def test_t_bench_01a_windows_follow_the_video_time_when_the_frame_rate_is_not_ten():
    t = np.arange(60) / 20.0  # 3.0 s at 20 fps: 20 frames per window
    latency = np.concatenate([np.full(20, 0.025), np.full(20, 0.05), np.full(20, 0.1)])
    out = window_rtf(latency, t)
    assert out.values == pytest.approx([0.5, 1.0, 2.0]) and out.n_dropped_frames == 0
