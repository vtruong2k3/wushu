"""T-IO-12 (unit part): the variable-frame-rate rule works on integer time-base ticks (BUG-0046).

``is_vfr`` used to compare the relative spread of the intervals in seconds with 1 %. With a coarse time base
(Matroska and WebM always, some MP4) a constant 30 fps video has intervals of 33 and 34 ms because a tick is 1 ms, a
1.4 % spread that is rounding, not a change of the frame rate. The rule now says an interval deviates when it differs
from the median by more than one tick *and* by more than 1 % of the median, and a video is VFR when more than 1 % of
its intervals deviate.
"""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.io.frames import VFR_RULE, is_vfr, vfr_verdict


def _pts(intervals) -> np.ndarray:
    return np.concatenate([[0], np.cumsum(np.asarray(intervals, dtype=np.int64))])


def test_t_io_12_the_rule_parameters_are_the_ones_of_the_manifest_example():
    assert (VFR_RULE.name, VFR_RULE.version, VFR_RULE.rel_tol, VFR_RULE.tick_tol, VFR_RULE.max_share) == (
        "tick_median",
        1,
        0.01,
        1,
        0.01,
    )


@pytest.mark.parametrize(
    "intervals",
    [
        [33, 33, 34] * 100,  # 30 fps at 1 ms ticks (BUG-0046)
        [33, 34] * 150,  # 29.9 fps, alternating
        [33, 33, 34] * 100,  # 29.97 fps pattern
        [3000] * 300,  # 30 fps at 1/90000
        [1, 1] * 5,  # tiny intervals: one tick of rounding is never a deviation
    ],
    ids=["30fps-1ms", "alternating", "2997-pattern", "90k-exact", "one-tick"],
)
def test_t_io_12_constant_frame_rate_is_not_vfr_whatever_the_time_base(intervals):
    v = vfr_verdict(_pts(intervals))
    assert v.vfr is False and v.n_deviating == 0 and v.deviating_share == 0.0


def test_t_io_12_a_real_change_of_frame_rate_is_vfr():
    v = vfr_verdict(_pts([33] * 30 + [100] * 10))  # 30 fps, then 10 fps
    assert v.vfr is True and v.n_deviating == 10
    assert v.deviating_share == pytest.approx(10 / 40)


def test_t_io_12_a_few_dropped_frames_stay_below_the_share():
    intervals = [33] * 299
    intervals[100] = intervals[200] = 66  # two dropped frames in 300 intervals: 0.67 %
    v = vfr_verdict(_pts(intervals))
    assert v.n_deviating == 2 and v.vfr is False


def test_t_io_12_more_than_one_percent_of_deviating_intervals_is_vfr():
    intervals = [33] * 299
    for i in (50, 100, 150, 200):  # four in 299 intervals: 1.34 %
        intervals[i] = 66
    assert vfr_verdict(_pts(intervals)).vfr is True


def test_t_io_12_the_share_threshold_is_strict():
    intervals = [100] * 100
    intervals[10] = 200  # exactly one in 100 intervals: 1 %, not more than 1 %
    assert vfr_verdict(_pts(intervals)).vfr is False
    intervals[20] = 200  # two in 100: 2 %
    assert vfr_verdict(_pts(intervals)).vfr is True


def test_t_io_12_the_deviation_limits_are_one_tick_and_one_percent_of_the_median():
    base = [33] * 50  # median 33: the limit is max(1 tick, 0.33) = 1 tick
    assert vfr_verdict(_pts(base + [34] * 50 + [33] * 100)).n_deviating == 0  # +1 tick is rounding
    assert vfr_verdict(_pts(base + [35] * 5 + [33] * 150)).n_deviating == 5  # +2 ticks deviates
    big = [1000] * 100  # median 1000: the limit is max(1 tick, 10 ticks) = 10 ticks
    assert vfr_verdict(_pts(big + [1010] * 3)).n_deviating == 0
    assert vfr_verdict(_pts(big + [1011] * 3)).n_deviating == 3
    assert vfr_verdict(_pts(big + [990] * 3)).n_deviating == 0
    assert vfr_verdict(_pts(big + [989] * 3)).n_deviating == 3


@pytest.mark.parametrize("n_frames", [0, 1, 2])
def test_t_io_12_too_few_frames_are_never_vfr(n_frames):
    v = vfr_verdict(np.arange(n_frames, dtype=np.int64) * 33)
    assert v.vfr is False and v.n_deviating == 0


def test_t_io_12_median_interval_is_reported_in_ticks_and_none_without_intervals():
    assert vfr_verdict(_pts([33, 33, 34])).median_dt_ticks == 33.0
    assert vfr_verdict(np.array([5], dtype=np.int64)).median_dt_ticks is None


def test_t_io_12_duplicate_timestamps_are_counted_not_dropped():
    pts = np.array([0, 33, 33, 66, 99, 99, 132], dtype=np.int64)
    v = vfr_verdict(pts)
    assert v.n_duplicates == 2 and v.n_intervals == 6


def test_t_io_12_when_most_frames_share_a_timestamp_the_median_is_zero_and_it_is_vfr():
    v = vfr_verdict(np.array([0, 0, 0, 0, 33, 33, 33], dtype=np.int64))
    assert v.median_dt_ticks == 0.0 and v.vfr is True
    # a case the one-tick tolerance alone would let through: the only non-zero interval is a single tick
    v = vfr_verdict(np.array([0, 0, 0, 0, 1], dtype=np.int64))
    assert v.median_dt_ticks == 0.0 and v.vfr is True


def test_t_io_12_one_interval_is_never_vfr_even_when_it_is_zero():
    v = vfr_verdict(np.array([5, 5], dtype=np.int64))  # two frames with the same timestamp: one interval of 0 ticks
    assert v.vfr is False and v.n_intervals == 1 and v.n_duplicates == 1
    assert vfr_verdict(np.array([5, 38], dtype=np.int64)).vfr is False


@pytest.mark.parametrize("tick_s", [0.001, 1 / 600, 1 / 15360, 1 / 90000])
def test_t_io_12_is_vfr_in_seconds_agrees_with_the_tick_rule(tick_s):
    ticks_per_frame = round(1 / 30 / tick_s)
    cfr = _pts([ticks_per_frame] * 300) * tick_s
    assert is_vfr(cfr, tick_s) is False
    vfr = _pts([ticks_per_frame] * 30 + [3 * ticks_per_frame] * 10) * tick_s
    assert is_vfr(vfr, tick_s) is True


def test_t_io_12_is_vfr_needs_the_tick_and_rounds_back_to_whole_ticks():
    t = _pts([33, 33, 34] * 100) * 0.001
    assert is_vfr(t, 0.001) is False
    with pytest.raises(TypeError):
        is_vfr(t)  # type: ignore[call-arg]


@pytest.mark.parametrize("offset_ticks", [84, 168, 196])
def test_t_io_12_float_noise_in_seconds_is_not_a_deviation(offset_ticks):
    # 60 frames at 30 fps on a 1 ms time base, start offset in ticks. ``pts * 0.001 / 0.001`` is sometimes one ulp
    # below the whole number, so a floor instead of a round would turn a tick of noise into a 2-tick deviation (found
    # by a search over offsets).
    pts = np.round(np.arange(60) * 1000 / 30).astype(np.int64) + offset_ticks
    assert is_vfr(pts * 0.001, 0.001) is False
