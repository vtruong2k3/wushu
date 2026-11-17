"""P4.02: short-gap interpolation: bridge holes of up to 150 ms of real time, flag them, leave the rest NaN
(T-QLT-03, T-QLT-04, T-QLT-05).

Arrays are built by hand: no video, no model. Joint ``j`` moves on a straight line in time,
``x = 100 + 7 j + (10 + j) t`` and ``y = 200 + 3 j - (5 + j) t``, so a bridge that is right reproduces the line and
every value can be checked against the truth that was hidden. A gap is a maximal run of unobserved frames of one
joint; its length is the bridged span ``t[after] - t[before]`` (DEC-0045), never the number of frames.
"""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality.gaps import (
    BLOCKED,
    FILLED,
    MAX_GAP_S,
    NEVER_FILL,
    OPEN_BOTH,
    OPEN_END,
    OPEN_START,
    OUTCOME_NAMES,
    TOO_LONG,
    GapParams,
    interpolate_gaps,
)
from taiji_ai.quality.mask import FRAME_INVALID, LOW_CONF, NON_FINITE, NOT_TRACKED, OK

OUTLIER = 5  # a reason code that a later task (Hampel) may add: the gap layer must treat an unknown code as a hole


def line_kp(t: np.ndarray, dtype=np.float64) -> np.ndarray:
    j = np.arange(NUM_JOINTS)[None, :]
    kp = np.empty((len(t), NUM_JOINTS, 2), np.float64)
    kp[..., 0] = 100.0 + 7.0 * j + (10.0 + j) * t[:, None]
    kp[..., 1] = 200.0 + 3.0 * j - (5.0 + j) * t[:, None]
    return kp.astype(dtype)


def line_layer(frames: int = 30, fps: float = 30.0, dtype=np.float64) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Keypoints on their lines, nothing missing yet, and the times of a constant frame rate."""
    t = np.arange(frames) / fps
    return line_kp(t, dtype), np.zeros((frames, NUM_JOINTS), np.uint8), t


def hide(kp: np.ndarray, reason: np.ndarray, joint: int, first: int, last: int, code: int = LOW_CONF) -> None:
    """Make frames ``first..last`` (inclusive) of one joint unobserved, as the mask does."""
    kp[first : last + 1, joint] = np.nan
    reason[first : last + 1, joint] = code


def gap_series(bridge_s: float, n_missing: int = 2, lead: int = 2, tail: int = 2):
    """One gap on joint 0 whose bridged span is exactly ``bridge_s``: the anchors are ``bridge_s`` apart and the missing
    frames sit between them, evenly. Returns ``kp, reason, t, (first, last)`` (the frames that are missing)."""
    before = 0.1 * (lead - 1)
    times = [0.1 * k for k in range(lead)]
    times += [before + bridge_s * k / (n_missing + 1) for k in range(1, n_missing + 1)]
    times += [before + bridge_s + 0.1 * k for k in range(tail)]
    t = np.array(times)
    kp, reason = line_kp(t), np.zeros((len(t), NUM_JOINTS), np.uint8)
    hide(kp, reason, 0, lead, lead + n_missing - 1)
    return kp, reason, t, (lead, lead + n_missing - 1)


def rows(result) -> list[tuple[int, int, int, str]]:
    g = result.gaps
    return [
        (int(j), int(s), int(e), OUTCOME_NAMES[o])
        for j, s, e, o in zip(g.joint, g.start, g.end, g.outcome, strict=True)
    ]


# --- the constants of W6 ------------------------------------------------------------------------------------------
def test_t_qlt_03_the_defaults_are_the_values_of_w6():
    p = GapParams()
    assert (p.max_gap_s, p.never_fill) == (0.150, (NOT_TRACKED,)) and MAX_GAP_S == 0.150
    assert OUTCOME_NAMES == ("filled", "too_long", "never_fill", "blocked", "open_start", "open_end", "open_both")
    codes = (FILLED, TOO_LONG, NEVER_FILL, BLOCKED, OPEN_START, OPEN_END, OPEN_BOTH)
    assert [OUTCOME_NAMES[c] for c in codes] == list(OUTCOME_NAMES)


# --- T-QLT-03: what is bridged and how ----------------------------------------------------------------------------
@pytest.mark.parametrize("n_missing", [1, 2, 3])
def test_t_qlt_03a_a_straight_line_is_reproduced_flagged_and_everything_else_is_untouched(n_missing: int):
    kp, reason, t = line_layer(30, 30.0)
    truth = kp.copy()
    hide(kp, reason, 4, 10, 9 + n_missing)
    hide(kp, reason, 17, 20, 19 + n_missing, NON_FINITE)  # another joint, another reason
    reason_before = reason.copy()
    r = interpolate_gaps(kp, reason, t)
    hidden = reason_before != OK
    assert np.array_equal(r.interpolated, hidden) and np.array_equal(r.observed, ~hidden)
    assert np.allclose(r.keypoints, truth, atol=1e-9, rtol=0)  # both coordinates, on the line
    assert r.keypoints[~hidden].tobytes() == truth[~hidden].tobytes()  # observed cells are bit-identical
    assert np.array_equal(r.reason, reason_before)  # why the cell was missing is kept, also for a filled cell
    assert r.usable.all() and r.params == GapParams()
    assert rows(r) == [(4, 10, 9 + n_missing, "filled"), (17, 20, 19 + n_missing, "filled")]


@pytest.mark.parametrize(
    ("bridge", "filled"),
    [
        (0.150, True),  # exactly the limit: bridged (a float sum gives 0.15000000000000002)
        (0.150 + 5e-10, True),  # inside the epsilon of 1e-9 s
        (0.150 + 1e-6, False),  # beyond it
        (0.150 - 1e-6, True),
        (0.04, True),
        (0.30, False),
    ],
)
def test_t_qlt_03b_the_limit_is_in_seconds_and_a_bridge_of_exactly_150_ms_is_filled(bridge: float, filled: bool):
    kp, reason, t, (first, last) = gap_series(bridge)
    r = interpolate_gaps(kp, reason, t)
    assert r.interpolated[:, 0].any() == filled
    assert rows(r) == [(0, first, last, "filled" if filled else "too_long")]
    assert r.gaps.bridge_s[0] == pytest.approx(bridge)


def test_t_qlt_03b_a_frame_rate_of_20_hz_puts_the_limit_at_two_missing_frames():
    kp, reason, t = line_layer(14, 20.0)
    hide(kp, reason, 2, 3, 4)  # 2 missing: anchors 3 steps = 150 ms apart
    hide(kp, reason, 6, 3, 5)  # 3 missing: 4 steps = 200 ms
    assert rows(interpolate_gaps(kp, reason, t)) == [(2, 3, 4, "filled"), (6, 3, 5, "too_long")]


def test_t_qlt_03c_inputs_are_not_changed_outputs_are_new_and_read_only_and_dtypes_are_kept():
    for dtype in (np.float32, np.float64):
        kp, reason, t = line_layer(20, 30.0, dtype)
        hide(kp, reason, 3, 5, 6)
        blocked = np.zeros(reason.shape, bool)
        before = (kp.copy(), reason.copy(), t.copy(), blocked.copy())
        r = interpolate_gaps(kp, reason, t, blocked=blocked)
        for given, kept in zip((kp, reason, t, blocked), before, strict=True):
            assert np.array_equal(given, kept, equal_nan=True)  # the layer that was read was not touched
        assert r.keypoints.dtype == dtype and r.interpolated.dtype == bool and r.observed.dtype == bool
        assert r.reason.dtype == np.uint8
        for arr in (r.keypoints, r.interpolated, r.observed, r.reason):
            assert not arr.flags.writeable
            assert not np.shares_memory(arr, kp) and not np.shares_memory(arr, reason)
        g = r.gaps
        for arr in (g.joint, g.start, g.end, g.missing_s, g.bridge_s, g.outcome):
            assert not arr.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            r.keypoints[0, 0, 0] = 1.0
        assert np.allclose(r.keypoints[5:7, 3], line_kp(t)[5:7, 3], atol=1e-3)  # float32 holds the line to its ulp


def test_t_qlt_03c_the_result_cannot_be_fed_back_a_bridged_value_is_never_taken_for_an_observed_one():
    kp, reason, t = line_layer(20, 30.0)
    hide(kp, reason, 3, 5, 6)
    r = interpolate_gaps(kp, reason, t)
    assert np.isfinite(r.keypoints[5:7, 3]).all() and (r.reason[5:7, 3] == LOW_CONF).all()  # a value, with a reason
    with pytest.raises(QualityError, match="finite"):
        interpolate_gaps(r.keypoints, r.reason, t)


def test_t_qlt_03d_joints_are_independent_and_two_gaps_one_observed_frame_apart_are_two_gaps():
    kp, reason, t = line_layer(20, 30.0)
    hide(kp, reason, 3, 4, 5)
    hide(kp, reason, 3, 7, 8)  # frame 6 is observed: two gaps, each anchored on it
    hide(kp, reason, 9, 4, 7)  # 4 missing at 30 fps: 5 steps, 167 ms
    r = interpolate_gaps(kp, reason, t)
    assert rows(r) == [(3, 4, 5, "filled"), (3, 7, 8, "filled"), (9, 4, 7, "too_long")]
    assert r.interpolated[4:6, 3].all() and r.interpolated[7:9, 3].all() and not r.interpolated[:, 9].any()
    assert np.isnan(r.keypoints[4:8, 9]).all()
    assert r.interpolated.sum() == 4


def test_t_qlt_03d_the_limit_is_a_parameter_that_travels_with_the_result():
    kp, reason, t = line_layer(30, 30.0)
    hide(kp, reason, 1, 5, 5)  # one missing frame: 2 steps = 66.7 ms
    hide(kp, reason, 2, 5, 12)  # 8 missing: 9 steps = 300 ms
    hide(kp, reason, 3, 5, 13)  # 9 missing: 10 steps = 333 ms
    tight = interpolate_gaps(kp, reason, t, GapParams(max_gap_s=0.05))
    loose = interpolate_gaps(kp, reason, t, GapParams(max_gap_s=0.3))
    assert [x[3] for x in rows(tight)] == ["too_long"] * 3 and tight.params.max_gap_s == 0.05
    assert [x[3] for x in rows(loose)] == ["filled", "filled", "too_long"] and loose.params.max_gap_s == 0.3


def test_t_qlt_03g_the_table_lists_every_gap_with_its_two_lengths_and_its_outcome():
    kp, reason, t = line_layer(12, 20.0)
    hide(kp, reason, 2, 3, 4)  # filled
    hide(kp, reason, 4, 5, 8)  # 4 missing: 5 steps = 250 ms: too long
    hide(kp, reason, 5, 0, 1)  # no observed frame before
    hide(kp, reason, 7, 10, 11)  # none after
    hide(kp, reason, 9, 0, 11)  # never observed
    result = interpolate_gaps(kp, reason, t)
    g = result.gaps
    assert rows(result) == [
        (2, 3, 4, "filled"),
        (4, 5, 8, "too_long"),
        (5, 0, 1, "open_start"),
        (7, 10, 11, "open_end"),
        (9, 0, 11, "open_both"),
    ]  # ordered by joint, then by first frame
    assert g.missing_s[:2] == pytest.approx([0.1, 0.2])  # frames x the median interval 50 ms
    assert g.bridge_s[:2] == pytest.approx([0.15, 0.25])  # t[after] - t[before]
    assert np.isnan(g.bridge_s[2:]).all() and g.missing_s[2:] == pytest.approx([0.1, 0.1, 0.6])
    assert (g.joint.dtype, g.start.dtype, g.end.dtype, g.outcome.dtype) == (np.int16, np.int32, np.int32, np.uint8)
    assert g.missing_s.dtype == g.bridge_s.dtype == np.float64


def test_t_qlt_03g_the_missing_span_uses_the_median_interval_of_the_clip_not_the_mean():
    t = np.array([0.0, 0.1, 0.2, 0.3, 1.3, 1.4, 1.5])  # intervals 0.1, 0.1, 0.1, 1.0, 0.1, 0.1: median 0.1, mean 0.25
    kp, reason = line_kp(t), np.zeros((len(t), NUM_JOINTS), np.uint8)
    hide(kp, reason, 3, 1, 2)
    g = interpolate_gaps(kp, reason, t).gaps
    assert g.missing_s[0] == pytest.approx(0.2) and g.bridge_s[0] == pytest.approx(0.3)  # 2 x 0.1; t[3] - t[0]


def test_t_qlt_03g_empty_inputs_all_observed_and_a_single_frame():
    empty = interpolate_gaps(np.zeros((0, NUM_JOINTS, 2)), np.zeros((0, NUM_JOINTS), np.uint8), np.zeros(0))
    assert empty.keypoints.shape == (0, NUM_JOINTS, 2) and len(empty.gaps.joint) == 0
    kp, reason, t = line_layer(10)
    clean = interpolate_gaps(kp, reason, t)
    assert len(clean.gaps.joint) == 0 and not clean.interpolated.any() and clean.usable.all()
    one_kp, one_reason = np.full((1, NUM_JOINTS, 2), 5.0), np.zeros((1, NUM_JOINTS), np.uint8)
    one_kp[0, 4], one_reason[0, 4] = np.nan, LOW_CONF
    one = interpolate_gaps(one_kp, one_reason, np.array([2.0]))
    assert rows(one) == [(4, 0, 0, "open_both")] and np.isnan(one.gaps.missing_s[0])  # no interval to multiply with


# --- T-QLT-04: what is not bridged --------------------------------------------------------------------------------
def test_t_qlt_04a_a_long_gap_stays_nan_no_value_is_held_and_no_zero_is_written():
    kp, reason, t = line_layer(40, 30.0)
    truth = kp.copy()
    hide(kp, reason, 5, 10, 17)  # 8 missing: 300 ms
    r = interpolate_gaps(kp, reason, t)
    gap = r.keypoints[10:18, 5]
    assert np.isnan(gap).all() and not r.interpolated.any()  # not the last value, not the next one, not zero
    assert np.array_equal(r.keypoints[9, 5], truth[9, 5]) and np.array_equal(r.keypoints[18, 5], truth[18, 5])
    assert rows(r) == [(5, 10, 17, "too_long")] and (r.reason[10:18, 5] == LOW_CONF).all()


def test_t_qlt_04b_nothing_is_extrapolated_at_the_ends_or_for_a_joint_never_observed():
    kp, reason, t = line_layer(20, 30.0)
    hide(kp, reason, 2, 0, 1)  # the first two frames: 67 ms, short, but nothing before
    hide(kp, reason, 4, 17, 19)  # the last three
    hide(kp, reason, 6, 0, 19)  # all
    r = interpolate_gaps(kp, reason, t)
    assert rows(r) == [(2, 0, 1, "open_start"), (4, 17, 19, "open_end"), (6, 0, 19, "open_both")]
    assert np.isnan(r.keypoints[0:2, 2]).all() and np.isnan(r.keypoints[17:20, 4]).all()
    assert np.isnan(r.keypoints[:, 6]).all() and not r.interpolated.any()


def test_t_qlt_04c_a_gap_that_holds_a_cell_of_a_frame_that_is_not_the_targets_is_never_bridged():
    kp, reason, t = line_layer(30, 30.0)
    reason[7:10, :] = NOT_TRACKED  # the target is away for 100 ms (frames 7 to 9), every joint
    kp[7:10] = np.nan
    hide(kp, reason, 3, 4, 5)  # a low score just before it: its own gap, anchored on frames 3 and 6
    hide(kp, reason, 8, 20, 20, FRAME_INVALID)  # elsewhere
    r = interpolate_gaps(kp, reason, t)
    by_joint = {(j, s, e): o for j, s, e, o in rows(r)}
    assert by_joint[(3, 4, 5)] == "filled"  # next to a lost stretch, but not touching it
    assert by_joint[(0, 7, 9)] == "never_fill" and np.isnan(r.keypoints[7:10]).all()
    assert by_joint[(8, 7, 9)] == "never_fill" and by_joint[(8, 20, 20)] == "filled"  # frame_invalid may be bridged
    mixed_kp, mixed_reason, t2 = line_layer(20, 30.0)
    hide(mixed_kp, mixed_reason, 3, 6, 6)
    hide(mixed_kp, mixed_reason, 3, 7, 7, NOT_TRACKED)  # one run: a low score, then a lost frame
    assert rows(interpolate_gaps(mixed_kp, mixed_reason, t2)) == [(3, 6, 7, "never_fill")]


def test_t_qlt_04d_a_blocked_cell_in_the_gap_or_at_an_anchor_refuses_the_bridge():
    base_kp, base_reason, t = line_layer(20, 30.0)
    hide(base_kp, base_reason, 3, 8, 9)
    free = interpolate_gaps(base_kp, base_reason, t)
    assert rows(free) == [(3, 8, 9, "filled")]
    for frame, where in (
        (8, "inside the gap"),
        (9, "inside the gap"),
        (7, "the anchor before"),
        (10, "the anchor after"),
    ):
        blocked = np.zeros(base_reason.shape, bool)
        blocked[frame, 3] = True
        r = interpolate_gaps(base_kp, base_reason, t, blocked=blocked)
        assert rows(r) == [(3, 8, 9, "blocked")], where
        assert np.isnan(r.keypoints[8:10, 3]).all() and not r.interpolated.any()
    elsewhere = np.zeros(base_reason.shape, bool)
    elsewhere[7, 4] = elsewhere[8, 2] = elsewhere[6, 3] = elsewhere[11, 3] = True  # other joints, or two frames away
    assert rows(interpolate_gaps(base_kp, base_reason, t, blocked=elsewhere)) == [(3, 8, 9, "filled")]
    none_blocked = interpolate_gaps(base_kp, base_reason, t, blocked=np.zeros(base_reason.shape, bool))
    assert np.array_equal(none_blocked.keypoints, free.keypoints, equal_nan=True)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("open_and_lost", "open_start"),  # a lost stretch at the start: the first rule that applies names it
        ("lost_blocked_long", "never_fill"),
        ("blocked_long", "blocked"),
        ("long_only", "too_long"),
        ("short_only", "filled"),
    ],
)
def test_t_qlt_04e_the_first_rule_that_applies_names_the_outcome(case: str, expected: str):
    kp, reason, t = line_layer(30, 30.0)
    blocked = np.zeros(reason.shape, bool)
    if case == "open_and_lost":
        hide(kp, reason, 1, 0, 3, NOT_TRACKED)
    elif case == "lost_blocked_long":
        hide(kp, reason, 1, 10, 20, NOT_TRACKED)
        blocked[12, 1] = True
    elif case == "blocked_long":
        hide(kp, reason, 1, 10, 20)
        blocked[12, 1] = True
    elif case == "long_only":
        hide(kp, reason, 1, 10, 20)
    else:
        hide(kp, reason, 1, 10, 11)
    assert [o for _, _, _, o in rows(interpolate_gaps(kp, reason, t, blocked=blocked))] == [expected]


def test_t_qlt_04f_the_codes_that_are_never_bridged_are_a_parameter():
    kp, reason, t = line_layer(20, 30.0)
    hide(kp, reason, 2, 5, 6, OUTLIER)  # a code this module does not know: a hole like any other
    hide(kp, reason, 3, 5, 6, NOT_TRACKED)
    default = interpolate_gaps(kp, reason, t)
    assert rows(default) == [(2, 5, 6, "filled"), (3, 5, 6, "never_fill")]
    strict = interpolate_gaps(kp, reason, t, GapParams(never_fill=(NOT_TRACKED, OUTLIER)))
    assert rows(strict) == [(2, 5, 6, "never_fill"), (3, 5, 6, "never_fill")]
    lax = interpolate_gaps(kp, reason, t, GapParams(never_fill=()))
    assert rows(lax) == [(2, 5, 6, "filled"), (3, 5, 6, "filled")]  # the caller's choice: not tracked is bridged
    assert strict.params.never_fill == (NOT_TRACKED, OUTLIER)


# --- T-QLT-05: real time, not frame counts ------------------------------------------------------------------------
def test_t_qlt_05a_the_same_number_of_missing_frames_is_bridged_or_not_by_the_clock():
    for fps, filled in ((60.0, True), (30.0, False), (15.0, False)):
        kp, reason, t = line_layer(40, fps)
        hide(kp, reason, 5, 10, 13)  # 4 missing frames: 5 steps, 83 ms at 60 fps, 167 ms at 30, 333 ms at 15
        assert interpolate_gaps(kp, reason, t).interpolated[:, 5].any() == filled, fps
    # an irregular series: the same three missing frames, a bridge of 140 ms and one of 160 ms
    for bridge, filled in ((0.140, True), (0.160, False)):
        kp, reason, t, _ = gap_series(bridge, n_missing=3)
        assert interpolate_gaps(kp, reason, t).interpolated[:, 0].any() == filled, bridge


def test_t_qlt_05b_the_weights_use_the_real_times_not_the_frame_index():
    t = np.array([0.0, 0.05, 0.10, 0.11, 0.12, 0.20, 0.25])  # the two missing frames sit near the right anchor
    kp = np.full((len(t), NUM_JOINTS, 2), np.nan)
    kp[..., 0], kp[..., 1] = (100.0 + 50.0 * t)[:, None], (400.0 - 30.0 * t)[:, None]  # linear in time
    truth = kp.copy()
    reason = np.zeros((len(t), NUM_JOINTS), np.uint8)
    hide(kp, reason, 0, 3, 4)  # anchors at 0.10 and 0.20: bridge 100 ms
    r = interpolate_gaps(kp, reason, t)
    assert r.interpolated[3:5, 0].all()
    assert np.allclose(r.keypoints[:, 0], truth[:, 0], atol=1e-9, rtol=0)
    index_weights = np.array([1 / 3, 2 / 3])  # what a bridge by frame index would use: x = 105, 110 against 105.5, 106
    assert np.abs(truth[3:5, 0, 0] - (truth[2, 0, 0] + index_weights * (truth[5, 0, 0] - truth[2, 0, 0]))).max() > 1.0


@pytest.mark.parametrize("k", [0.5, 2.0, 4.0])
def test_t_qlt_05c_scaling_the_clock_and_the_limit_together_changes_nothing(k: float):
    kp, reason, t = line_layer(60, 30.0)
    for joint, (first, last) in enumerate([(3, 3), (10, 11), (20, 22), (30, 33), (40, 44), (50, 55)]):
        hide(kp, reason, joint, first, last)  # 1 to 6 missing frames: bridges of 67 ms to 233 ms
    base = interpolate_gaps(kp, reason, t)
    scaled = interpolate_gaps(kp, reason, t * k, GapParams(max_gap_s=0.150 * k))
    assert rows(scaled) == rows(base) and np.array_equal(scaled.interpolated, base.interpolated)
    assert np.allclose(scaled.keypoints, base.keypoints, atol=1e-9, equal_nan=True)
    assert [o for _, _, _, o in rows(base)] == ["filled"] * 3 + ["too_long"] * 3


# --- T-QLT-03i: bad input is refused naming the argument ----------------------------------------------------------
def good(frames: int = 6):
    kp, reason, t = line_layer(frames)
    return kp, reason, t


def case_nan_with_ok():
    kp, reason, t = good()
    kp[2, 3] = np.nan
    return kp, reason, t, None


def case_value_with_a_reason():
    kp, reason, t = good()
    reason[2, 3] = LOW_CONF
    return kp, reason, t, None


def case_nan_time():
    kp, reason, t = good()
    t[3] = np.nan
    return kp, reason, t, None


def case_equal_times():
    kp, reason, t = good()
    t[3] = t[2]
    return kp, reason, t, None


def case_decreasing_times():
    kp, reason, t = good()
    t[3], t[4] = t[4], t[3]
    return kp, reason, t, None


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: (good()[0].astype(np.int32), good()[1], good()[2], None), "keypoints"),
        (lambda: (good()[0][:, :, 0], good()[1], good()[2], None), "keypoints"),
        (lambda: (good()[0][:, :25], good()[1], good()[2], None), "keypoints"),
        (lambda: (good()[0], good()[1][:-1], good()[2], None), "reason"),
        (lambda: (good()[0], good()[1].astype(np.float32), good()[2], None), "reason"),
        (lambda: (good()[0], good()[1].astype(np.int64), good()[2], None), "reason"),
        (lambda: (good()[0], good()[1], good()[2][:-1], None), "t_sec"),
        (lambda: (good()[0], good()[1], np.stack([good()[2]] * 2), None), "t_sec"),
        (lambda: (good()[0], good()[1], (good()[2] * 30).astype(np.int64), None), "t_sec"),
        (case_nan_time, "finite"),
        (case_equal_times, "strictly increasing"),
        (case_decreasing_times, "strictly increasing"),
        (case_nan_with_ok, "NaN"),
        (case_value_with_a_reason, "finite"),
        (lambda: (good()[0], good()[1], good()[2], np.zeros((6, 25), bool)), "blocked"),
        (lambda: (good()[0], good()[1], good()[2], np.zeros((6, NUM_JOINTS), np.int8)), "blocked"),
    ],
)
def test_t_qlt_03i_bad_arrays_are_refused_naming_the_argument(make, message: str):
    kp, reason, t, blocked = make()
    with pytest.raises(QualityError, match=message):
        interpolate_gaps(kp, reason, t, blocked=blocked)


@pytest.mark.parametrize("value", [0.0, -0.1, float("nan"), float("inf"), True, "0.15", None])
def test_t_qlt_03i_a_wrong_limit_is_refused(value):
    with pytest.raises(QualityError, match="max_gap_s"):
        GapParams(max_gap_s=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [(3.5,), ("a",), (256,), (-1,), (True,), 3, None, (3, 3)])
def test_t_qlt_03i_wrong_never_fill_codes_are_refused(value):
    with pytest.raises(QualityError, match="never_fill"):
        GapParams(never_fill=value)  # type: ignore[arg-type]


def test_t_qlt_03i_the_limit_may_be_any_positive_number_and_the_codes_are_stored_as_integers():
    p = GapParams(max_gap_s=1, never_fill=(np.uint8(3), 7))  # type: ignore[arg-type]
    assert p.max_gap_s == 1.0 and isinstance(p.max_gap_s, float) and p.never_fill == (3, 7)
    assert all(type(c) is int for c in p.never_fill)


# --- T-QLT-03h: a differential and invariant test on random layers ---------------------------------------------------
def oracle(kp, reason, t, params: GapParams, blocked):
    """The rule of the plan written the slow way, cell by cell, to compare with the vectorised module."""
    out = np.array(kp, dtype=np.float64, copy=True)
    flagged = np.zeros(reason.shape, bool)
    table = []
    for j in range(reason.shape[1]):
        i = 0
        while i < reason.shape[0]:
            if reason[i, j] == OK:
                i += 1
                continue
            s = i
            while i < reason.shape[0] and reason[i, j] != OK:
                i += 1
            e = i - 1
            before, after = s - 1, e + 1
            if before < 0 and after >= len(t):
                outcome = "open_both"
            elif before < 0:
                outcome = "open_start"
            elif after >= len(t):
                outcome = "open_end"
            elif any(int(reason[k, j]) in params.never_fill for k in range(s, e + 1)):
                outcome = "never_fill"
            elif blocked is not None and any(blocked[k, j] for k in (before, after, *range(s, e + 1))):
                outcome = "blocked"
            elif t[after] - t[before] <= params.max_gap_s + 1e-9:
                outcome = "filled"
            else:
                outcome = "too_long"
            if outcome == "filled":
                for k in range(s, e + 1):
                    w = (t[k] - t[before]) / (t[after] - t[before])
                    out[k, j] = out[before, j] + w * (out[after, j] - out[before, j])
                    flagged[k, j] = True
            table.append((j, s, e, outcome))
    return out, flagged, table


def random_layer(seed: int):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 45))
    t = float(rng.uniform(0, 5)) + np.cumsum(rng.uniform(0.01, 0.09, n))
    kp = rng.uniform(0.0, 1000.0, (n, NUM_JOINTS, 2))
    hole = rng.random((n, NUM_JOINTS)) < 0.25
    hole |= np.roll(hole, 1, axis=0) & (rng.random((n, NUM_JOINTS)) < 0.6)  # longer runs
    reason = np.zeros((n, NUM_JOINTS), np.uint8)
    codes = rng.choice([LOW_CONF, NON_FINITE, FRAME_INVALID, OUTLIER], size=(n, NUM_JOINTS))
    reason[hole] = codes[hole].astype(np.uint8)
    reason[rng.random(n) < 0.08, :] = NOT_TRACKED  # whole frames of the target being away
    kp[reason != OK] = np.nan
    blocked = (rng.random((n, NUM_JOINTS)) < 0.05) if seed % 2 else None
    never_fill = (NOT_TRACKED,) if seed % 3 else (NOT_TRACKED, OUTLIER)
    params = GapParams(max_gap_s=float(rng.choice([0.05, 0.10, 0.15, 0.25, 0.40])), never_fill=never_fill)
    return kp, reason, t, params, blocked


@pytest.mark.parametrize("seed", range(200))
def test_t_qlt_03h_the_module_equals_the_slow_rule_and_keeps_its_invariants(seed: int):
    kp, reason, t, params, blocked = random_layer(seed)
    r = interpolate_gaps(kp, reason, t, params, blocked=blocked)
    want_kp, want_flag, want_table = oracle(kp, reason, t, params, blocked)
    assert np.array_equal(r.interpolated, want_flag) and np.allclose(r.keypoints, want_kp, atol=1e-9, equal_nan=True)
    assert rows(r) == want_table
    observed = reason == OK
    assert r.keypoints[observed].tobytes() == kp[observed].tobytes()  # observed cells never change
    changed = ~np.isclose(r.keypoints, kp, atol=0, rtol=0, equal_nan=True).all(axis=-1)
    assert np.array_equal(changed, r.interpolated)  # a cell changes if and only if it is flagged
    assert np.isfinite(r.keypoints[r.interpolated]).all() and np.isnan(r.keypoints[~observed & ~r.interpolated]).all()
    g = r.gaps
    for j, s, e, o in zip(g.joint, g.start, g.end, g.outcome, strict=True):
        if o == FILLED:  # inside the box of its anchors, the length is within the limit, no never-fill cell inside
            lo = np.minimum(kp[s - 1, j], kp[e + 1, j]) - 1e-9
            hi = np.maximum(kp[s - 1, j], kp[e + 1, j]) + 1e-9
            assert ((r.keypoints[s : e + 1, j] >= lo) & (r.keypoints[s : e + 1, j] <= hi)).all()
            assert t[e + 1] - t[s - 1] <= params.max_gap_s + 1e-9
            assert not np.isin(reason[s : e + 1, j], params.never_fill).any()
    covered = np.zeros(reason.shape, np.int32)  # the rows tile the unobserved cells exactly, once
    for j, s, e in zip(g.joint, g.start, g.end, strict=True):
        covered[s : e + 1, j] += 1
    assert np.array_equal(covered, (~observed).astype(np.int32))
    assert np.array_equal(r.usable, observed | r.interpolated)
