"""P4.04: the uniform grid for variable-frame-rate video: resample the gap layer to a regular clock (T-QLT-07).

Layers and timelines are built by hand: no video, no model. A timeline is *uniform* when every row time is within
``uniform_tol_s`` of a straight line; then the stage is the identity. Otherwise the grid is the lattice that the row
times follow (X.31: a frame-count-corrected step and a fitted phase; an explicit ``grid_hz`` is anchored at the first
row); a grid time within ``uniform_tol_s`` of a row is that row; any other grid time between two rows takes the linear
mix of two usable cells (flagged), a cell next to an unusable cell is NaN, and a stretch of time with no frame beyond
``max_step_s`` is NaN with ``no_frame``. Most tests use ``linear_layer``: every joint moves on a straight line in
time, so linear interpolation is exact and any deviation is a fault of the stage, not of the interpolation; a copy
that is not exactly on its grid time is the one exception, off by at most the speed times ``snap_s``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from helpers.synth import make_sequence, truth_at, vfr_times
from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import check_gap_layer
from taiji_ai.quality.gaps import MAX_GAP_S
from taiji_ai.quality.mask import FRAME_INVALID, LOW_CONF, NO_FRAME, NON_FINITE, NOT_TRACKED, OK, OUTLIER
from taiji_ai.quality.resample import MAX_STEP_S, UNIFORM_TOL_S, ResampleParams, plan_grid, resample_layer

STEP = 1.0 / 30.0
FLOAT32_SLACK = 5e-3  # px: a float32 row of 1,500 px is stored to about 1e-4 px


# --- builders ---------------------------------------------------------------------------------------------------------
def linear_layer(t: np.ndarray, dtype=np.float64):
    """Every joint moves on a straight line in time: x = 100 + 3 j + 40 t, y = 200 + 5 j - 25 t (px). All observed."""
    j = np.arange(NUM_JOINTS)[None, :]
    kp = np.empty((len(t), NUM_JOINTS, 2))
    kp[..., 0] = 100.0 + 3.0 * j + 40.0 * t[:, None]
    kp[..., 1] = 200.0 + 5.0 * j - 25.0 * t[:, None]
    return kp.astype(dtype), np.zeros((len(t), NUM_JOINTS), np.uint8), np.zeros((len(t), NUM_JOINTS), bool)


def hole(kp, reason, joint: int, rows, code: int = LOW_CONF) -> None:
    for r in np.atleast_1d(rows):
        kp[r, joint] = np.nan
        reason[r, joint] = code


def bridge(reason, interp, joint: int, rows, code: int = LOW_CONF) -> None:
    """The cell keeps its value and becomes a bridged one: a reason that is not ok and the flag ``interpolated``."""
    for r in np.atleast_1d(rows):
        reason[r, joint] = code
        interp[r, joint] = True


def jittered(seed: int = 1, duration: float = 4.0, jitter: float = 0.3) -> np.ndarray:
    return vfr_times(duration, 30.0, jitter_frac=jitter, rng=np.random.default_rng(seed))


def dropped(n: int = 100, rows=(50,)) -> np.ndarray:
    """A 30 fps clock with some frames removed: the rows that remain keep the phase of the clock."""
    return np.delete(np.arange(n) / 30.0, list(rows))


def assert_grid(g, max_step_s: float = MAX_STEP_S) -> None:
    """The rules 2 to 4 of the plan (DEC-0047 as amended by DEC-0052), from the map alone."""
    t, tg, snap = g.t_source, g.t_grid, g.snap_s
    assert tg[0] >= t[0] - snap and tg[-1] <= t[-1] + snap  # inside the window of the clip
    assert tg[0] - g.step_s < t[0] - snap and tg[-1] + g.step_s > t[-1] + snap  # and all of it: none is left out
    assert np.allclose(np.diff(tg), g.step_s, rtol=0.0, atol=1e-9)  # regular
    assert ((g.weight >= 0.0) & (g.weight < 1.0)).all()
    exact = g.weight == 0.0
    assert (np.abs(tg[exact] - t[g.left[exact]]) <= snap).all()  # a copy is a row within the tolerance
    left = g.left[~exact]
    assert (t[left] < tg[~exact]).all() and (tg[~exact] < t[left + 1]).all()
    assert (tg[~exact] - t[left] > snap).all() and (t[left + 1] - tg[~exact] > snap).all()  # a mix is farther than that
    assert np.allclose(g.weight[~exact], (tg[~exact] - t[left]) / (t[left + 1] - t[left]))
    right = np.minimum(g.left + 1, len(t) - 1)
    assert np.array_equal(g.stall, ~exact & ((t[right] - t[g.left]) > max_step_s + 1e-9))


# --- the defaults -----------------------------------------------------------------------------------------------------
def test_t_qlt_07_the_defaults_are_the_limit_of_the_gap_layer_and_one_millisecond():
    p = ResampleParams()
    assert p.grid_hz is None and p.max_step_s == MAX_STEP_S == MAX_GAP_S == 0.150
    assert p.uniform_tol_s == UNIFORM_TOL_S == 0.001


def test_t_qlt_07_the_truth_helper_gives_the_motion_between_the_rows_too():
    seq = make_sequence("SYN-07", seed=3, noise_px=0.0)
    assert np.allclose(truth_at(seq, seq.t_sec), seq.kp_true, atol=1e-3)
    mid = truth_at(seq, (seq.t_sec[:-1] + seq.t_sec[1:]) / 2.0)
    assert mid.shape == (len(seq.t_sec) - 1, NUM_JOINTS, 2) and np.isfinite(mid).all()


# --- T-QLT-07a: a uniform timeline is the identity --------------------------------------------------------------------
@pytest.mark.parametrize("fps", [24.0, 25.0, 30.0, 60.0])
def test_t_qlt_07a_exact_constant_rates_are_the_identity(fps: float):
    t = 12.5 + np.arange(120) / fps
    g = plan_grid(t)
    assert g.identity and not g.resampled
    assert np.array_equal(g.t_grid, t) and np.array_equal(g.t_source, t)
    assert g.step_s == pytest.approx(1.0 / fps, rel=1e-9)
    assert np.array_equal(g.left, np.arange(120)) and not g.weight.any() and not g.stall.any() and not g.beyond.any()
    assert np.array_equal(g.back_left, np.arange(120)) and not g.back_weight.any()


@pytest.mark.parametrize("ms_per_frame", [1001.0 / 30.0, 1000.0 / 30.0])  # 29.97 and 30 fps in whole milliseconds
def test_t_qlt_07a_a_constant_rate_on_a_coarse_time_base_is_the_identity(ms_per_frame: float):
    t = np.round(np.arange(600) * ms_per_frame) / 1000.0  # every row is up to 0.5 ms off the line
    g = plan_grid(t)
    assert g.identity and g.step_s == pytest.approx(ms_per_frame / 1000.0, rel=1e-4)
    assert not plan_grid(t, ResampleParams(uniform_tol_s=0.0)).identity  # the tolerance is what makes it uniform


def test_t_qlt_07a_a_clock_that_runs_fast_is_still_uniform():
    t = 1.01 * np.arange(200) / 30.0
    g = plan_grid(t)
    assert g.identity and g.step_s == pytest.approx(1.01 / 30.0, rel=1e-9)


def test_t_qlt_07a_one_row_a_little_off_is_uniform_and_one_far_off_is_not():
    t = np.arange(120) / 30.0
    near, far = t.copy(), t.copy()
    near[60] += 0.0009
    far[60] += 0.0015
    assert plan_grid(near).identity and not plan_grid(far).identity
    assert not plan_grid(near, ResampleParams(uniform_tol_s=0.0005)).identity  # the tolerance is a parameter


def test_t_qlt_07a_the_identity_copies_values_reasons_and_flags_bit_for_bit():
    t = np.arange(90) / 24.0
    kp, reason, interp = linear_layer(t, np.float32)
    hole(kp, reason, 3, [10, 11])
    hole(kp, reason, 4, 20, NOT_TRACKED)
    bridge(reason, interp, 5, 30, OUTLIER)
    r = resample_layer(kp, reason, interp, t)
    assert r.gridmap.identity and not r.mixed.any()
    assert r.keypoints.tobytes() == kp.tobytes()  # NaN included
    assert np.array_equal(r.reason, reason) and np.array_equal(r.interpolated, interp)
    assert r.keypoints.dtype == np.float32


def test_t_qlt_07a_an_exact_clock_is_the_identity_even_with_a_tolerance_of_zero():
    # the line is exact up to float rounding, far below the 1e-9 s that is always allowed
    t = 12.5 + np.arange(300) / 24.0
    assert plan_grid(t, ResampleParams(uniform_tol_s=0.0)).identity


def test_t_qlt_07a_the_identity_result_does_not_share_memory_with_the_input():
    t = np.arange(40) / 30.0
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    assert r.gridmap.identity
    for arr in (r.keypoints, r.reason, r.interpolated):
        assert not arr.flags.writeable
    assert not np.shares_memory(r.keypoints, kp) and not np.shares_memory(r.reason, reason)
    assert not np.shares_memory(r.interpolated, interp)
    assert kp.flags.writeable and reason.flags.writeable and interp.flags.writeable  # the input was not frozen
    kp[0, 0, 0] = -1.0
    assert r.keypoints[0, 0, 0] != -1.0


def test_t_qlt_07a_times_must_be_a_one_dimensional_float_array_of_increasing_seconds():
    assert plan_grid(np.arange(60, dtype=np.float32) / 30.0).identity  # float32 times are fine
    for bad in (np.zeros((3, 2)), np.arange(5), np.array([0.0, 0.0, 1.0]), np.array([0.0, np.nan, 1.0])):
        with pytest.raises(QualityError, match="t_sec"):
            plan_grid(bad)


def test_t_qlt_07a_zero_one_and_two_rows():
    zero = plan_grid(np.zeros(0))
    assert zero.identity and len(zero.t_grid) == 0 and np.isnan(zero.step_s)
    one = plan_grid(np.array([3.5]))
    assert one.identity and one.t_grid.tolist() == [3.5] and np.isnan(one.step_s)
    two = plan_grid(np.array([0.0, 0.5]))
    assert two.identity and two.step_s == 0.5
    for n in (0, 1, 2):
        t = np.arange(n) * 0.5
        kp, reason, interp = linear_layer(t)
        r = resample_layer(kp, reason, interp, t)
        assert r.keypoints.shape == (n, NUM_JOINTS, 2) and np.array_equal(r.keypoints, kp) and not r.mixed.any()
    assert plan_grid(np.array([3.5]), ResampleParams(grid_hz=20.0)).identity  # one row has nothing to resample


# --- T-QLT-07b: a regular grid for a timeline that is not uniform -----------------------------------------------------
def test_t_qlt_07b_a_dropped_frame_gives_a_regular_grid_with_one_mixed_row():
    t = dropped(100, (50,))
    g = plan_grid(t)
    assert not g.identity and g.resampled
    assert_grid(g)
    assert g.step_s == pytest.approx(STEP, rel=1e-12) and len(g.t_grid) == 100 and len(t) == 99
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    assert np.flatnonzero(r.mixed).tolist() == [50]
    assert g.left[50] == 49 and g.weight[50] == pytest.approx(0.5)
    copies = ~r.mixed
    assert np.array_equal(r.keypoints[copies], kp[g.left[copies]])  # the rows on the grid are copied bit for bit
    assert np.allclose(r.keypoints[50], 0.5 * (kp[49] + kp[50]), rtol=0.0, atol=1e-9)


def test_t_qlt_07b_the_step_down_of_syn_07_keeps_every_row_on_the_grid_and_mixes_between_the_slow_rows():
    seq = make_sequence("SYN-07", seed=3, noise_px=0.0)
    t = np.asarray(seq.t_sec)
    g = plan_grid(t)
    assert not g.identity
    assert_grid(g)
    assert g.step_s == pytest.approx(STEP, rel=1e-9)  # the frames: 59 intervals of one frame and 20 of three
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    assert len(r.mixed) == 120 and int(r.mixed.sum()) == 40  # two grid times inside each of the 20 intervals of 100 ms
    assert np.array_equal(r.keypoints[~r.mixed], kp[g.left[~r.mixed]])


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_t_qlt_07b_a_jittered_clock_gives_a_regular_grid(seed: int):
    t = jittered(seed)
    g = plan_grid(t)
    assert not g.identity
    assert_grid(g)
    assert g.step_s == pytest.approx(np.polyfit(np.arange(len(t)), t, 1)[0], rel=1e-9)  # one frame each


def test_t_qlt_07b_the_last_grid_time_may_sit_on_the_last_row_despite_float_rounding():
    t = np.array([0.0, 0.1, 0.25, 0.3])  # a step of 0.1 s asked for, and 0.3 / 0.1 is 2.9999999999999996
    g = plan_grid(t, ResampleParams(grid_hz=10.0))
    assert not g.identity and g.step_s == pytest.approx(0.1) and len(g.t_grid) == 4
    assert g.t_grid[-1] == pytest.approx(0.3, abs=1e-12) and g.weight[-1] == 0.0 and g.left[-1] == 3


def test_t_qlt_07b_grid_hz_is_an_explicit_request_and_overrides_the_rate_of_the_clip():
    t = np.arange(90) / 30.0
    params = ResampleParams(grid_hz=20.0)
    g = plan_grid(t, params)
    assert not g.identity and g.step_s == 0.05
    assert_grid(g)
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t, params)
    assert np.flatnonzero(r.mixed).tolist() == list(range(1, 60, 2))  # 0.05 k is a row (m / 30) for even k only
    same = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=30.0))
    assert not same.gridmap.identity and not same.mixed.any() and np.array_equal(same.keypoints, kp)


# --- T-QLT-07c: exact on linear motion --------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_qlt_07c_a_straight_movement_comes_out_straight(seed: int):
    t = jittered(seed)
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    want, _, _ = linear_layer(r.gridmap.t_grid)
    assert np.allclose(r.keypoints[r.mixed], want[r.mixed], rtol=0.0, atol=1e-9)  # x and y apart, each exact
    price = 40.0 * r.gridmap.snap_s  # a copy is the row up to the tolerance away: 40 px/s is the fastest axis
    assert np.allclose(r.keypoints, want, rtol=0.0, atol=price + 1e-9)
    assert (~r.mixed).any() and r.usable.all() and r.observed.all() and not r.interpolated.any()
    assert r.mixed.sum() > 0.5 * len(r.mixed)  # on a jittered clock most grid times are not rows


def test_t_qlt_07c_a_float32_layer_is_straight_too_and_a_constant_stays_constant():
    t = jittered(2)
    kp, reason, interp = linear_layer(t, np.float32)
    r = resample_layer(kp, reason, interp, t)
    want, _, _ = linear_layer(r.gridmap.t_grid)
    assert r.keypoints.dtype == np.float32
    assert np.allclose(r.keypoints, want, rtol=0.0, atol=40.0 * r.gridmap.snap_s + 1e-3)
    flat = np.full((len(t), NUM_JOINTS, 2), 321.5)
    r = resample_layer(flat, reason, interp, t)
    assert (r.keypoints == 321.5).all()  # the weights sum to one: no drift


# --- T-QLT-07d: smooth motion with known truth ------------------------------------------------------------------------
def max_acceleration(seq) -> float:
    """The largest acceleration (px/s^2) of any joint of the analytic motion, from the truth at 3,000 fps."""
    h = 1.0 / 3000.0
    k = truth_at(seq, np.arange(0.0, float(seq.params["duration"]), h))
    return float((np.linalg.norm(np.diff(k, 2, axis=0), axis=-1) / h**2).max())


def test_t_qlt_07d_the_step_down_timeline_is_exact_on_the_way_back_and_within_the_bound_on_the_grid():
    seq = make_sequence("SYN-07", seed=3, noise_px=0.0)
    t, kp = np.asarray(seq.t_sec), np.asarray(seq.kp)
    r = resample_layer(kp, np.zeros(kp.shape[:2], np.uint8), np.zeros(kp.shape[:2], bool), t)
    g = r.gridmap
    err = np.linalg.norm(r.keypoints.astype(np.float64) - truth_at(seq, g.t_grid), axis=-1)  # (G, 26)
    d = t[np.minimum(g.left + 1, len(t) - 1)] - t[g.left]  # the source interval that holds the grid time
    bound = max_acceleration(seq) / 8.0 * d**2 + FLOAT32_SLACK  # linear interpolation: a d^2 / 8
    assert (err <= bound[:, None]).all()
    assert err.max() > 0.01  # not vacuous: the mixed rows are not the truth
    assert np.array_equal(g.to_source(r.keypoints), kp)  # every row sits on a grid time: the way back is exact


@pytest.mark.parametrize("seed", [5, 6])
def test_t_qlt_07d_a_jittered_clock_comes_back_within_the_bound_of_both_interpolations(seed: int):
    seq = make_sequence("SYN-07", seed=seed, noise_px=0.0, jitter_frac=0.3)
    t, kp = np.asarray(seq.t_sec), np.asarray(seq.kp)
    r = resample_layer(kp, np.zeros(kp.shape[:2], np.uint8), np.zeros(kp.shape[:2], bool), t)
    g = r.gridmap
    back = g.to_source(r.keypoints)
    inside = ~(g.before | g.beyond)  # the rows outside the grid have a neighbour on one side only
    assert np.isfinite(back[inside]).all()
    err = np.linalg.norm(back[inside].astype(np.float64) - kp[inside].astype(np.float64), axis=-1)
    d, s = float(np.diff(t).max()), g.step_s
    bound = 1.05 * max_acceleration(seq) * (d**2 + s**2) / 8.0 + FLOAT32_SLACK  # error of both interpolations
    assert err.max() <= bound, (err.max(), bound)
    assert err.max() > 0.05  # not vacuous: two linear interpolations are lossy on a curve


# --- T-QLT-07e: nothing is invented -----------------------------------------------------------------------------------
def test_t_qlt_07e_a_hole_is_not_filled_across_and_not_held():
    t = jittered(2)
    kp, reason, interp = linear_layer(t)
    hole(kp, reason, 7, 20)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    inside = (g.t_grid > t[19] + 1e-9) & (g.t_grid < t[21] - 1e-9)  # between the two anchors of the hole
    assert inside.sum() >= 1
    assert np.isnan(r.keypoints[inside, 7]).all() and (r.reason[inside, 7] == LOW_CONF).all()
    assert not r.interpolated[inside, 7].any() and not r.usable[inside, 7].any()
    assert r.usable[~inside, 7].all() and r.usable[:, np.arange(NUM_JOINTS) != 7].all()  # nothing else is touched


def test_t_qlt_07e_a_loss_of_the_target_is_not_crossed():
    t = jittered(3)
    kp, reason, interp = linear_layer(t)
    for joint in range(NUM_JOINTS):
        hole(kp, reason, joint, np.arange(40, 60), NOT_TRACKED)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    inside = (g.t_grid > t[39] + 1e-9) & (g.t_grid < t[60] - 1e-9)
    assert inside.sum() > 15
    assert np.isnan(r.keypoints[inside]).all() and (r.reason[inside] == NOT_TRACKED).all()
    assert r.usable[g.t_grid <= t[39] + 1e-9].all() and r.usable[g.t_grid >= t[60] - 1e-9].all()
    back = r.to_source(r.keypoints)
    assert np.isnan(back[40:60]).all()  # NaN stays NaN on the way back


def test_t_qlt_07e_no_value_is_outside_the_range_of_its_two_parents():
    rng = np.random.default_rng(8)
    t = jittered(4)
    kp = np.cumsum(rng.normal(0.0, 5.0, (len(t), NUM_JOINTS, 2)), axis=0) + 500.0
    r = resample_layer(kp, np.zeros(kp.shape[:2], np.uint8), np.zeros(kp.shape[:2], bool), t)
    g = r.gridmap
    a, b = kp[g.left], kp[np.minimum(g.left + 1, len(t) - 1)]
    assert (r.keypoints >= np.minimum(a, b) - 1e-9).all() and (r.keypoints <= np.maximum(a, b) + 1e-9).all()


# --- T-QLT-07f: a pause in the timestamps is not bridged --------------------------------------------------------------
def test_t_qlt_07f_a_pause_of_more_than_the_limit_is_nan_with_no_frame():
    t = np.delete(np.arange(60) / 30.0, np.arange(20, 40))  # rows 19 and 40 are 0.7 s apart
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    assert np.flatnonzero(g.stall).tolist() == list(range(20, 40))
    assert np.isnan(r.keypoints[20:40]).all() and (r.reason[20:40] == NO_FRAME).all()
    assert not r.interpolated[20:40].any() and not r.mixed[20:40].any()
    assert np.array_equal(r.keypoints[:20], kp[:20]) and np.array_equal(r.keypoints[40:], kp[20:])  # copies outside
    assert np.array_equal(g.to_source(r.keypoints), kp)  # every row sits on a grid time: the pause is not in the way


def test_t_qlt_07f_exactly_the_limit_is_bridged_and_a_hair_more_is_not():
    # median interval 0.05; the interval between rows 2 and 3 is 0.15 (0.15000000000000002 in floats)
    at = np.array([0.0, 0.05, 0.1, 0.25, 0.3, 0.35, 0.4])
    over = np.array([0.0, 0.05, 0.1, 0.250001, 0.3, 0.35, 0.4])
    for t, stalled in ((at, False), (over, True)):
        kp, reason, interp = linear_layer(t)
        r = resample_layer(kp, reason, interp, t)
        assert bool(r.gridmap.stall[3]) is stalled and bool(r.gridmap.stall[4]) is stalled
        assert bool(np.isnan(r.keypoints[3]).all()) is stalled and bool(r.mixed[3]) is not stalled
    wide = resample_layer(*linear_layer(over), over, ResampleParams(max_step_s=0.2))  # the limit is a parameter
    assert not wide.gridmap.stall.any() and wide.usable.all()
    narrow = resample_layer(*linear_layer(at), at, ResampleParams(max_step_s=0.1))
    assert narrow.gridmap.stall[3] and narrow.gridmap.stall[4]


def test_t_qlt_07f_at_a_low_rate_nothing_between_the_rows_is_interpolated():
    t = np.array([0.0, 0.2, 0.4, 0.7, 0.9, 1.1])  # median interval 0.2 s: more than the limit
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    assert g.step_s == pytest.approx(0.2) and len(g.t_grid) == 6
    assert g.stall.tolist() == [False, False, False, True, True, True]
    assert np.array_equal(r.keypoints[:3], kp[:3]) and np.isnan(r.keypoints[3:]).all()
    assert (r.reason[3:] == NO_FRAME).all()


def test_t_qlt_07f_a_grid_time_that_is_a_row_inside_a_pause_is_a_copy():
    t = np.array([0.0, 0.1, 0.2, 0.9, 1.0, 1.1])  # a pause between 0.2 and 0.9; the grid time 1.0 is a row
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    assert g.step_s == pytest.approx(0.1)
    copies = np.flatnonzero(~g.stall & (g.weight == 0.0))
    assert np.array_equal(r.keypoints[copies], kp[g.left[copies]]) and r.usable[copies].all()
    assert (r.reason[g.stall] == NO_FRAME).all() and g.stall.sum() == 6  # grid times 0.3 to 0.8


# --- T-QLT-07g: reasons and flags -------------------------------------------------------------------------------------
def two_rows():
    t = np.array([0.0, 0.1])
    kp = np.zeros((2, NUM_JOINTS, 2))
    kp[0] = (10.0, 20.0)
    kp[1] = (110.0, 220.0)
    return t, kp, np.zeros((2, NUM_JOINTS), np.uint8), np.zeros((2, NUM_JOINTS), bool)


def put(kp, reason, interp, row: int, joint: int, kind: str, code: int = OK) -> None:
    if kind == "hole":
        kp[row, joint] = np.nan
        reason[row, joint] = code
    elif kind == "bridged":
        reason[row, joint] = code
        interp[row, joint] = True


def test_t_qlt_07g_the_reason_and_the_flag_of_a_mixed_cell_follow_the_rules():
    """Rows at 0 and 0.1 s, grid at 40 Hz: grid times 0, 0.025, 0.05, 0.075, 0.1 s, weights 0, 0.25, 0.5, 0.75, 0."""
    t, kp, reason, interp = two_rows()
    put(kp, reason, interp, 1, 1, "bridged", LOW_CONF)  # j1: ok, bridged
    put(kp, reason, interp, 0, 2, "bridged", OUTLIER)  # j2: bridged, ok
    put(kp, reason, interp, 0, 3, "bridged", LOW_CONF)  # j3: bridged, bridged
    put(kp, reason, interp, 1, 3, "bridged", OUTLIER)
    put(kp, reason, interp, 1, 4, "hole", NON_FINITE)  # j4: ok, hole
    put(kp, reason, interp, 0, 5, "hole", LOW_CONF)  # j5: hole, hole
    put(kp, reason, interp, 1, 5, "hole", NOT_TRACKED)
    put(kp, reason, interp, 0, 6, "hole", LOW_CONF)  # j6: hole, bridged
    put(kp, reason, interp, 1, 6, "bridged", OUTLIER)
    put(kp, reason, interp, 0, 7, "bridged", OUTLIER)  # j7: bridged, hole
    put(kp, reason, interp, 1, 7, "hole", NOT_TRACKED)
    put(kp, reason, interp, 0, 8, "bridged", FRAME_INVALID)  # j8: the same reason twice
    put(kp, reason, interp, 1, 8, "bridged", FRAME_INVALID)
    r = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=40.0))
    g = r.gridmap
    assert g.t_grid.tolist() == pytest.approx([0.0, 0.025, 0.05, 0.075, 0.1]) and g.weight[2] == 0.5
    # per joint: (reasons at the weights 0.25, 0.5, 0.75; usable; interpolated)
    expected = {
        0: ((OK, OK, OK), True, False),
        1: ((LOW_CONF,) * 3, True, True),
        2: ((OUTLIER,) * 3, True, True),
        3: ((LOW_CONF, LOW_CONF, OUTLIER), True, True),  # the nearer parent, the left one on the tie at 0.5
        4: ((NON_FINITE,) * 3, False, False),
        5: ((LOW_CONF, LOW_CONF, NOT_TRACKED), False, False),
        6: ((LOW_CONF,) * 3, False, False),  # the unusable parent, not the nearer
        7: ((NOT_TRACKED,) * 3, False, False),
        8: ((FRAME_INVALID,) * 3, True, True),
    }
    for joint, (reasons, usable, flagged) in expected.items():
        assert r.reason[1:4, joint].tolist() == list(reasons), joint
        assert r.usable[1:4, joint].tolist() == [usable] * 3, joint
        assert r.interpolated[1:4, joint].tolist() == [flagged] * 3, joint
    assert r.mixed.tolist() == [False, True, True, True, False]
    for k, row in ((0, 0), (4, 1)):  # the copies keep value, reason and flag
        assert np.array_equal(r.keypoints[k], kp[row], equal_nan=True)
        assert np.array_equal(r.reason[k], reason[row]) and np.array_equal(r.interpolated[k], interp[row])
    check_gap_layer(r.keypoints, r.reason, r.interpolated, g.t_grid)  # the result obeys the contract of the input


def test_t_qlt_07g_a_mixed_cell_between_two_observed_cells_is_ok_and_not_interpolated():
    t, kp, reason, interp = two_rows()
    r = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=40.0))
    assert np.allclose(r.keypoints[1], (10.0 + 0.25 * 100.0, 20.0 + 0.25 * 200.0)) and r.observed[1].all()
    assert r.observed[1:4].all() and not r.interpolated.any() and r.usable.all()


# --- T-QLT-07h: the way back ------------------------------------------------------------------------------------------
def test_t_qlt_07h_when_every_row_sits_on_the_grid_the_way_back_is_exact():
    t = dropped(100, (50,))
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    back = r.gridmap.to_source(r.keypoints)
    assert np.array_equal(back, kp) and not r.gridmap.beyond.any()
    assert np.array_equal(r.gridmap.back_left[:50], np.arange(50)) and not r.gridmap.back_weight.any()


def test_t_qlt_07h_a_hole_costs_only_the_rows_within_one_step_of_it_on_a_jittered_clock():
    t = jittered(2)
    kp, reason, interp = linear_layer(t)
    hole(kp, reason, 7, 20)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    back = r.to_source(r.keypoints)
    source_usable = np.isfinite(kp[..., 0])
    assert np.array_equal(r.source_usable, source_usable)
    lost = source_usable & np.isnan(back[..., 0]) & ~(g.before | g.beyond)[:, None]
    assert not lost[:, np.arange(NUM_JOINTS) != 7].any()  # the other joints lose nothing
    rows = np.flatnonzero(lost[:, 7])
    assert 0 < len(rows) <= 6
    reach = g.step_s + max(t[21] - t[20], t[20] - t[19])  # a lost row has a grid neighbour inside the hole
    assert (np.abs(t[rows] - t[20]) < reach).all()
    assert np.isnan(back[20, 7]).all()  # the hole itself stays a hole
    finite = np.isfinite(back[..., 0])
    price = 40.0 * g.snap_s  # a snapped grid cell is a row up to the tolerance away: 40 px/s is the fastest axis
    assert np.allclose(back[finite], kp[finite], rtol=0.0, atol=price + 1e-9)  # linear motion: right up to that price


def test_t_qlt_07h_a_source_hole_stays_a_hole_even_when_the_grid_is_coarser_than_the_rows():
    t = np.arange(30) * 0.01  # a uniform clock of 100 Hz asked for a grid of 20 Hz
    kp, reason, interp = linear_layer(t)
    hole(kp, reason, 0, 7)
    r = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=20.0))
    assert not r.gridmap.identity and r.usable.all()  # the hole row is no parent of any grid time: the grid has no hole
    bare = r.gridmap.to_source(r.keypoints)  # the bare map would give the hole a value from the grid times around it
    assert np.isfinite(bare[7, 0]).all()
    back = r.to_source(r.keypoints)  # the layer remembers what was usable at the source: no value is made for the hole
    assert np.isnan(back[7, 0]).all() and reason[7, 0] == LOW_CONF
    assert np.isfinite(back[:25]).sum() == np.isfinite(bare[:25]).sum() - 2  # only that cell (x and y) differs
    assert np.allclose(back[6], kp[6], rtol=0.0, atol=1e-9)  # linear motion: the mix of the two grid times is exact
    with pytest.raises(QualityError, match="values"):
        r.to_source(r.keypoints[:-1])
    with pytest.raises(QualityError, match="values"):
        r.to_source(r.keypoints[:, :5])  # not 26 joints


def test_t_qlt_07h_the_way_back_is_computed_in_double_precision_and_the_formula_is_the_plan_s():
    t = jittered(4)
    g = plan_grid(t)
    values = np.random.default_rng(6).uniform(100.0, 1800.0, (len(g.t_grid), NUM_JOINTS, 2)).astype(np.float32)
    back = g.to_source(values)
    left = g.back_left.astype(np.int64)
    a = values[left].astype(np.float64)
    b = values[np.minimum(left + 1, len(values) - 1)].astype(np.float64)
    w = g.back_weight[:, None, None]
    want = np.where(w > 0.0, a + w * (b - a), a).astype(np.float32)
    outside = g.before | g.beyond
    want[outside] = np.nan
    assert np.array_equal(back, want, equal_nan=True)
    assert np.isfinite(back[~outside]).all() and np.isnan(back[outside]).all()


def test_t_qlt_07h_the_rows_after_the_last_grid_time_have_no_right_neighbour():
    t = np.array([0.0, 0.1, 0.2, 0.35])  # a step of 0.1 s asked for: the grid ends at 0.3, before the last row
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=10.0))
    g = r.gridmap
    assert len(g.t_grid) == 4 and g.beyond.tolist() == [False, False, False, True]
    back = g.to_source(r.keypoints)
    assert np.array_equal(back[:3], kp[:3]) and np.isnan(back[3]).all()


def test_t_qlt_07h_the_identity_way_back_is_a_new_copy_and_a_wrong_input_is_refused():
    t = np.arange(40) / 30.0
    g = plan_grid(t)
    values = np.random.default_rng(1).normal(size=(40, NUM_JOINTS, 2))
    back = g.to_source(values)
    assert np.array_equal(back, values) and not np.shares_memory(back, values)
    assert g.to_source(values[:, 0, 0]).shape == (40,)  # any trailing shape
    with pytest.raises(QualityError, match="values"):
        g.to_source(values[:-1])
    with pytest.raises(QualityError, match="values"):
        g.to_source(values.astype(np.int64))
    with pytest.raises(QualityError, match="values"):
        g.to_source(np.float64(3.0))


# --- T-QLT-07i: the result and its invariants -------------------------------------------------------------------------
@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_t_qlt_07i_inputs_are_not_changed_outputs_are_new_and_read_only_and_dtypes_are_kept(dtype):
    t = jittered(1)
    kp, reason, interp = linear_layer(t, dtype)
    hole(kp, reason, 3, [10, 11])
    bridge(reason, interp, 5, 30, OUTLIER)
    before = (kp.copy(), reason.copy(), interp.copy(), t.copy())
    r = resample_layer(kp, reason, interp, t)
    for given, kept in zip((kp, reason, interp, t), before, strict=True):
        assert np.array_equal(given, kept, equal_nan=True)
    g = r.gridmap
    assert r.keypoints.dtype == dtype and r.reason.dtype == np.uint8
    assert r.interpolated.dtype == bool and r.mixed.dtype == bool
    back = g.to_source(r.keypoints)
    assert back.dtype == dtype and r.to_source(r.keypoints).dtype == dtype
    assert np.array_equal(r.source_usable, np.isfinite(kp[..., 0]))
    arrays = (r.keypoints, r.reason, r.interpolated, r.mixed, r.source_usable, back, r.to_source(r.keypoints))
    maps = (g.t_source, g.t_grid, g.left, g.weight, g.stall, g.back_left, g.back_weight, g.beyond)
    for arr in (*arrays, *maps):
        assert not arr.flags.writeable and not any(np.shares_memory(arr, x) for x in (kp, reason, interp, t))
    with pytest.raises(ValueError, match="read-only"):
        r.keypoints[0, 0, 0] = 1.0


def test_t_qlt_07i_float32_is_mixed_in_double_precision():
    t = jittered(4)
    kp = np.random.default_rng(3).uniform(100.0, 1800.0, (len(t), NUM_JOINTS, 2)).astype(np.float32)
    r = resample_layer(kp, np.zeros(kp.shape[:2], np.uint8), np.zeros(kp.shape[:2], bool), t)
    g = r.gridmap
    a, b = kp[g.left].astype(np.float64), kp[np.minimum(g.left + 1, len(t) - 1)].astype(np.float64)
    w = g.weight[:, None, None]
    assert np.array_equal(r.keypoints, (a + w * (b - a)).astype(np.float32))


def test_t_qlt_07i_a_shifted_clock_gives_the_same_layer_on_a_shifted_grid():
    t = jittered(2)
    kp, reason, interp = linear_layer(t)
    hole(kp, reason, 4, [30, 31])
    bridge(reason, interp, 6, 50, OUTLIER)
    base = resample_layer(kp, reason, interp, t)
    shifted = resample_layer(kp, reason, interp, t + 123.456)
    assert np.allclose(shifted.gridmap.t_grid, base.gridmap.t_grid + 123.456, rtol=0.0, atol=1e-9)
    assert np.array_equal(shifted.reason, base.reason) and np.array_equal(shifted.interpolated, base.interpolated)
    assert np.array_equal(shifted.mixed, base.mixed) and np.array_equal(shifted.gridmap.stall, base.gridmap.stall)
    assert np.allclose(shifted.keypoints, base.keypoints, rtol=0.0, atol=1e-6, equal_nan=True)


@pytest.mark.parametrize("k", [0.5, 2.0, 4.0])
def test_t_qlt_07i_scaling_the_clock_and_the_limits_together_changes_no_value(k: float):
    t = np.delete(jittered(3), [30, 31, 32, 33, 34, 35, 70])  # a pause of about 0.25 s and a dropped row as well
    kp, reason, interp = linear_layer(t)
    hole(kp, reason, 4, [10, 11])
    base = resample_layer(kp, reason, interp, t)
    scaled = resample_layer(
        kp, reason, interp, t * k, ResampleParams(max_step_s=MAX_STEP_S * k, uniform_tol_s=UNIFORM_TOL_S * k)
    )
    assert np.array_equal(scaled.reason, base.reason) and np.array_equal(scaled.mixed, base.mixed)
    assert np.array_equal(scaled.gridmap.stall, base.gridmap.stall) and base.gridmap.stall.any()
    assert np.allclose(scaled.keypoints, base.keypoints, rtol=0.0, atol=1e-9, equal_nan=True)


def test_t_qlt_07i_joints_are_independent():
    t = jittered(2)
    rng = np.random.default_rng(5)
    kp, reason, interp = linear_layer(t)
    holes = rng.random(reason.shape) < 0.1
    reason[holes] = LOW_CONF
    kp[holes] = np.nan
    base = resample_layer(kp, reason, interp, t)
    perm = rng.permutation(NUM_JOINTS)
    moved = resample_layer(kp[:, perm], reason[:, perm], interp[:, perm], t)
    assert np.array_equal(moved.reason, base.reason[:, perm]) and np.array_equal(moved.mixed, base.mixed)
    assert np.array_equal(moved.keypoints, base.keypoints[:, perm], equal_nan=True)


def test_t_qlt_07i_a_long_timeline_has_the_right_shapes_and_agrees_with_its_prefix():
    t = np.delete(np.arange(101_000) / 30.0, np.arange(100, 101_000, 100))  # a row dropped every 100 rows
    kp, reason, interp = linear_layer(t, np.float32)
    hole(kp, reason, 9, np.arange(400, 405))
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    assert r.keypoints.shape == (len(g.t_grid), NUM_JOINTS, 2) and len(g.t_grid) > len(t)
    m = 1000
    head = resample_layer(kp[:m], reason[:m], interp[:m], t[:m])
    upto = int(np.searchsorted(g.t_grid, t[m - 1] - 1e-6))
    assert upto > 900 and len(head.keypoints) >= upto
    assert np.array_equal(head.reason[:upto], r.reason[:upto]) and np.array_equal(head.mixed[:upto], r.mixed[:upto])
    assert np.allclose(head.keypoints[:upto], r.keypoints[:upto], rtol=0.0, atol=1e-3, equal_nan=True)


# --- T-QLT-07j: bad input is refused naming the argument --------------------------------------------------------------
def good():
    t = jittered(1)
    return (*linear_layer(t), t)


def with_half_nan_cell():
    kp, reason, interp, t = good()
    kp[3, 4, 0] = np.nan
    reason[3, 4] = LOW_CONF
    return kp, reason, interp, t


def with_infinite_cell():
    kp, reason, interp, t = good()
    kp[3, 4] = np.inf
    return kp, reason, interp, t


def with_value_not_ok_and_not_flagged():
    kp, reason, interp, t = good()
    reason[3, 4] = LOW_CONF
    return kp, reason, interp, t


def with_flag_on_a_nan_cell():
    kp, reason, interp, t = good()
    kp[3, 4] = np.nan
    reason[3, 4] = LOW_CONF
    interp[3, 4] = True
    return kp, reason, interp, t


def with_flag_on_an_ok_cell():
    kp, reason, interp, t = good()
    interp[3, 4] = True
    return kp, reason, interp, t


def with_nan_and_ok():
    kp, reason, interp, t = good()
    kp[3, 4] = np.nan
    return kp, reason, interp, t


def with_equal_times():
    kp, reason, interp, t = good()
    t[5] = t[4]
    return kp, reason, interp, t


def with_nan_time():
    kp, reason, interp, t = good()
    t[5] = np.nan
    return kp, reason, interp, t


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: (good()[0].astype(np.int32), *good()[1:]), "keypoints"),
        (lambda: (good()[0][:, :, 0], *good()[1:]), "keypoints"),
        (lambda: (good()[0][:, :25], *good()[1:]), "keypoints"),
        (lambda: (good()[0], good()[1].astype(np.int64), good()[2], good()[3]), "reason"),
        (lambda: (good()[0], good()[1][:-1], good()[2], good()[3]), "reason"),
        (lambda: (good()[0], good()[1], good()[2].astype(np.uint8), good()[3]), "interpolated"),
        (lambda: (good()[0], good()[1], good()[2][:-1], good()[3]), "interpolated"),
        (lambda: (*good()[:3], (good()[3] * 30).astype(np.int64)), "t_sec"),
        (lambda: (*good()[:3], good()[3][:-1]), "t_sec"),
        (with_equal_times, "strictly increasing"),
        (with_nan_time, "finite"),
        (with_half_nan_cell, "one NaN coordinate"),
        (with_infinite_cell, "infinite"),
        (with_value_not_ok_and_not_flagged, "not flagged"),
        (with_flag_on_a_nan_cell, "no value"),
        (with_flag_on_an_ok_cell, "whose reason is ok"),
        (with_nan_and_ok, "where reason is ok"),
    ],
)
def test_t_qlt_07j_bad_arrays_are_refused_naming_the_argument(make, message: str):
    kp, reason, interp, t = make()
    with pytest.raises(QualityError, match=message):
        resample_layer(kp, reason, interp, t)
    with pytest.raises(QualityError, match=message):
        check_gap_layer(kp, reason, interp, t)


@pytest.mark.parametrize("bad", [0.0, -30.0, float("nan"), float("inf"), True, "30", 0])
def test_t_qlt_07j_a_wrong_grid_rate_is_refused(bad):
    with pytest.raises(QualityError, match="grid_hz"):
        ResampleParams(grid_hz=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0.0, -0.15, float("nan"), float("inf"), True, None, "0.15"])
def test_t_qlt_07j_a_wrong_stall_limit_is_refused(bad):
    with pytest.raises(QualityError, match="max_step_s"):
        ResampleParams(max_step_s=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-0.001, float("nan"), float("inf"), True, None, "1"])
def test_t_qlt_07j_a_wrong_uniform_tolerance_is_refused(bad):
    with pytest.raises(QualityError, match="uniform_tol_s"):
        ResampleParams(uniform_tol_s=bad)  # type: ignore[arg-type]


def test_t_qlt_07j_the_parameters_that_were_used_travel_with_the_result_and_zero_tolerance_is_allowed():
    kp, reason, interp, t = good()
    params = ResampleParams(grid_hz=25.0, max_step_s=0.2, uniform_tol_s=0.0)
    assert resample_layer(kp, reason, interp, t, params).params == params
    assert resample_layer(kp, reason, interp, t).params == ResampleParams()
    assert ResampleParams(grid_hz=np.float32(24.0)).grid_hz == 24.0


# --- X.31: the lattice of a sensor clock and the snap tolerance -------------------------------------------------------
def ms_clock(n: int = 900, drop=(), start: int = 0) -> np.ndarray:
    """A 30 fps sensor clock in whole milliseconds (every row up to 0.5 ms off the lattice) with some frames dropped."""
    frames = np.delete(np.arange(start, start + n), [d - start for d in drop])
    return np.round(frames * (1000.0 / 30.0)) / 1000.0


def on_the_grid(g) -> np.ndarray:
    """Rows that are a grid time (a copy on the way back): ``back_weight`` 0 and not outside the grid."""
    return (g.back_weight == 0.0) & ~g.before & ~g.beyond


def test_t_qlt_07n_a_row_within_the_tolerance_of_a_grid_time_is_a_copy_and_one_outside_is_a_mix():
    t = np.array([0.0, 0.0508, 0.1, 0.1512, 0.2, 0.25, 0.3])  # grid 20 Hz: 0.05 is 0.8 ms from a row, 0.15 is 1.2 ms
    params = ResampleParams(grid_hz=20.0)
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t, params)
    g = r.gridmap
    assert g.t_grid.tolist() == pytest.approx([0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3])
    assert r.mixed.tolist() == [False, False, False, True, False, False, False]
    assert g.left[1] == 1 and g.weight[1] == 0.0  # the copy is the row itself, 0.8 ms away: bit for bit
    assert np.array_equal(r.keypoints[1], kp[1]) and np.array_equal(r.reason[1], reason[1])
    assert g.left[3] == 2 and g.weight[3] == pytest.approx((0.15 - 0.1) / (0.1512 - 0.1))  # 1.2 ms away: a mix
    assert g.snap_s == pytest.approx(0.001, abs=1e-8)
    # the way back: a row 0.8 ms from a grid time takes that grid value, one 1.2 ms away mixes its two grid times
    assert on_the_grid(g).tolist() == [True, True, True, False, True, True, True]
    assert g.back_left[3] == 3 and g.back_weight[3] == pytest.approx(0.0012 / 0.05)
    values = np.arange(len(g.t_grid), dtype=np.float64)[:, None] * np.ones((1, 4))
    back = g.to_source(values)
    assert back[1, 0] == 1.0 and back[3, 0] == pytest.approx(3.0 + 0.0012 / 0.05)


def test_t_qlt_07n_a_tolerance_of_zero_copies_only_at_exact_times_and_the_tolerance_is_a_parameter():
    t = np.array([0.0, 0.0508, 0.1, 0.1512, 0.2, 0.25, 0.3])
    kp, reason, interp = linear_layer(t)
    exact = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=20.0, uniform_tol_s=0.0))
    assert exact.mixed.tolist() == [False, True, False, True, False, False, False]
    assert exact.gridmap.snap_s == pytest.approx(0.0, abs=2e-9)
    wide = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=20.0, uniform_tol_s=0.002))
    assert not wide.mixed.any() and wide.gridmap.snap_s == pytest.approx(0.002, abs=1e-8)


def test_t_qlt_07n_the_tolerance_never_exceeds_a_quarter_of_the_step():
    t = np.arange(40) * 0.0021  # a 2.1 ms clock asked for 500 Hz: the step is 2 ms, 1 ms would swallow it
    g = plan_grid(t, ResampleParams(grid_hz=500.0))
    assert g.snap_s == pytest.approx(0.0005, abs=1e-8)
    t = np.arange(40) / 30.0
    assert plan_grid(t, ResampleParams(grid_hz=30.0)).snap_s == pytest.approx(0.001, abs=1e-8)  # the default stands


def test_t_qlt_07n_the_nearest_row_is_the_copy_and_the_earlier_one_on_a_tie():
    h = 2.0**-10  # exact in binary: 0.000977 s, inside the default tolerance of 1 ms
    t = np.array([0.0, 0.0625, 0.125 - h, 0.125 + h, 0.1875, 0.25])  # grid 16 Hz: 0.125 has two rows, as near
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=16.0))
    g = r.gridmap
    assert g.left[2] == 2 and g.weight[2] == 0.0  # the tie goes to the earlier row
    assert np.array_equal(r.keypoints[2], kp[2])
    t2 = np.array([0.0, 0.0625, 0.125 - 1.5 * h / 2, 0.125 + h / 2, 0.1875, 0.25])  # now the later row is nearer
    r2 = resample_layer(*linear_layer(t2), t2, ResampleParams(grid_hz=16.0))
    assert r2.gridmap.left[2] == 3 and r2.gridmap.weight[2] == 0.0


def test_t_qlt_07n_a_snapped_cell_keeps_value_reason_and_flag_of_its_row():
    t = np.array([0.0, 0.0508, 0.1, 0.15, 0.2])
    kp, reason, interp = linear_layer(t)
    hole(kp, reason, 3, 1)
    bridge(reason, interp, 5, 1, OUTLIER)
    r = resample_layer(kp, reason, interp, t, ResampleParams(grid_hz=20.0))
    assert not r.mixed[1]
    assert np.array_equal(r.keypoints[1], kp[1], equal_nan=True)
    assert np.array_equal(r.reason[1], reason[1]) and np.array_equal(r.interpolated[1], interp[1])
    check_gap_layer(r.keypoints, r.reason, r.interpolated, r.gridmap.t_grid)


def test_t_qlt_07o_a_ms_clock_with_dropped_frames_gives_the_step_of_the_frames_and_copies_every_row():
    drops = [37, 90, 91, 200, 333, 334, 335, 500, 777]
    t = ms_clock(900, drops)
    g = plan_grid(t)
    assert not g.identity
    assert abs(g.step_s - 1.0 / 30.0) < 1e-6  # the frames, not the intervals
    assert abs(float(np.median(np.diff(t))) - 1.0 / 30.0) > 2e-4  # the median interval is 33 ms
    assert abs((t[-1] - t[0]) / (len(t) - 1) - 1.0 / 30.0) > 2e-4  # and the plain mean is dragged by the dropped frames
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    assert len(g.t_grid) == 900 and int(r.mixed.sum()) == len(drops)  # the only mixed rows are the dropped frames
    assert on_the_grid(g).all() and np.array_equal(r.keypoints[~r.mixed], kp[g.left[~r.mixed]])
    assert (np.abs(g.t_grid[~r.mixed] - t[g.left[~r.mixed]]) <= 0.001).all()  # a copy is at most the tolerance off


def test_t_qlt_07o_the_fit_does_not_depend_on_where_the_clock_starts():
    t = ms_clock(600, [100, 101, 300])
    base = plan_grid(t)
    far = plan_grid(t + 7200.0)  # two hours into the recording
    assert far.step_s == pytest.approx(base.step_s, abs=1e-9) and len(far.t_grid) == len(base.t_grid)
    assert np.array_equal(on_the_grid(far), on_the_grid(base))
    assert np.array_equal(far.left, base.left) and np.array_equal(far.weight == 0.0, base.weight == 0.0)


def pause_clock(before: int, after: int) -> np.ndarray:
    """``before`` rows of a 30 fps clock, a pause of 0.4 s and 12.3 ms more than whole frames, then ``after`` rows."""
    first = np.arange(before) / 30.0
    return np.concatenate([first, first[-1] + 0.4123 + np.arange(1, after + 1) / 30.0])


def test_t_qlt_07o_a_pause_that_moves_the_phase_does_not_move_the_step_and_the_longest_run_sets_the_phase():
    t = pause_clock(300, 500)
    g = plan_grid(t)
    assert abs(g.step_s - 1.0 / 30.0) < 1e-9  # the pause is not in the fit
    on = on_the_grid(g)
    assert on[300:].all() and not on[:300].any()  # the 500 rows of the longer run are copies, the 300 before 12 ms off
    r = resample_layer(*linear_layer(t), t)
    assert g.stall.sum() >= 10 and (r.reason[g.stall] == NO_FRAME).all()  # the pause itself is not bridged
    on2 = on_the_grid(plan_grid(pause_clock(500, 200)))  # now the run before the pause is the longer one
    assert on2[:500].all() and not on2[500:].any()


def test_t_qlt_07o_a_burst_of_rows_finer_than_the_step_is_outside_the_fit():
    before = np.arange(80) / 30.0
    burst = before[-1] + np.arange(1, 21) / 150.0  # 20 rows in 0.133 s = four frames of the clock
    after = burst[-1] + np.arange(1, 81) / 30.0
    t = np.concatenate([before, burst, after])
    g = plan_grid(t)
    assert abs(g.step_s - 1.0 / 30.0) < 1e-9
    on = on_the_grid(g)
    assert on[:80].all() and on[100:].all()  # the rows of the regular parts are copies, whatever the burst did
    assert not on[80:99].all()  # the burst rows that are not on the lattice are not copies


def test_t_qlt_07o_no_regular_interval_falls_back_to_the_median_and_the_first_row():
    t = np.array([0.0, 0.2, 0.4, 0.7, 0.9, 1.1])  # every interval is over the limit of 0.15 s
    g = plan_grid(t)
    assert g.step_s == pytest.approx(0.2) and g.t_grid[0] == t[0] and not g.identity
    assert g.stall.tolist() == [False, False, False, True, True, True]


def test_t_qlt_07o_a_jittered_clock_gets_the_mean_step_and_stays_regular():
    t = jittered(2)
    g = plan_grid(t)
    index = np.arange(len(t), dtype=np.float64)
    slope = np.polyfit(index, t, 1)[0]
    assert g.step_s == pytest.approx(slope, rel=1e-9)  # every interval is regular: one frame each
    assert np.allclose(np.diff(g.t_grid), g.step_s, rtol=0.0, atol=1e-9)
    assert g.t_grid[0] >= t[0] - g.snap_s and g.t_grid[-1] <= t[-1] + g.snap_s


def test_t_qlt_07o_an_explicit_grid_rate_keeps_the_first_row_as_the_anchor_and_the_step():
    t = ms_clock(300, [50]) + 0.003  # the first row is 3 ms off a whole-millisecond lattice: the anchor is the row
    g = plan_grid(t, ResampleParams(grid_hz=30.0))
    assert g.t_grid[0] == t[0] and g.step_s == 1.0 / 30.0
    assert np.allclose(np.diff(g.t_grid), 1.0 / 30.0, rtol=0.0, atol=1e-12)


def test_t_qlt_07p_a_first_row_off_the_lattice_is_before_the_grid_and_has_no_value_on_the_way_back():
    t = np.concatenate([[0.003], np.arange(1, 300) / 30.0])  # row 0 is 3 ms late for its place on the lattice
    kp, reason, interp = linear_layer(t)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    assert not g.identity and abs(g.step_s - 1.0 / 30.0) < 2e-6
    assert g.before.tolist() == [True] + [False] * 299 and not g.beyond.any()
    assert g.t_grid[0] == pytest.approx(1.0 / 30.0, abs=1e-4) and g.left[0] == 1  # the grid starts at the first copy
    assert not r.mixed.any() and len(g.t_grid) == 299
    back = r.to_source(r.keypoints)
    assert np.isnan(back[0]).all() and np.array_equal(back[1:], kp[1:])  # a value is never made up before the grid


def test_t_qlt_07p_a_first_row_within_the_tolerance_of_the_lattice_starts_the_grid_before_it():
    t = np.concatenate([[0.0004], np.delete(np.arange(1, 300) / 30.0, 40)])  # 0.4 ms late, and a dropped frame
    g = plan_grid(t)
    assert not g.identity and not g.before.any()
    assert g.t_grid[0] < t[0] and t[0] - g.t_grid[0] <= g.snap_s  # the first grid time is the row, 0.4 ms early
    assert g.left[0] == 0 and g.weight[0] == 0.0


@pytest.mark.parametrize(("late", "beyond"), [(0.0006, False), (-0.0006, False), (0.003, True), (-0.003, True)])
def test_t_qlt_07p_the_last_row_is_on_the_grid_within_the_tolerance_and_beyond_it_outside(late: float, beyond: bool):
    t = np.delete(np.arange(300) / 30.0, 40)
    t[-1] += late  # the last row is 0.6 or 3 ms late or early for its place on the lattice
    g = plan_grid(t)
    assert bool(g.beyond[-1]) is beyond
    assert not g.beyond[:-1].any() and not g.before.any()
    assert g.t_grid[-1] <= t[-1] + g.snap_s  # the grid never goes past the last row by more than the tolerance
    assert len(g.t_grid) == (299 if beyond and late < 0 else 300)  # a lattice time 3 ms past the last row is not in it


def test_t_qlt_07p_a_lattice_time_at_the_edge_of_the_window_is_a_copy_never_a_mix_with_a_weight_below_zero(monkeypatch):
    # the first lattice time is put exactly where the window starts, t_0 - snap, in the clocks of a long recording where
    # float rounding makes its distance from the row a hair over the tolerance: it must still be the copy of row 0
    from taiji_ai.quality import resample as module

    snap = 0.001 + 1e-9  # ``min(tolerance, step / 4) + 1e-9``
    base = np.delete(np.arange(200) / 30.0, 40)
    holder = {}
    monkeypatch.setattr(module, "_fit_lattice", lambda t, max_step_s: (1.0 / 30.0, holder["phase"]))
    for t0 in [300.0 + 0.5 * k for k in range(40)] + [10000.0 + 0.7 * k for k in range(40)]:  # binades where it does
        holder["phase"] = t0 - snap
        g = plan_grid(t0 + base)
        assert (g.weight >= 0.0).all() and (g.weight < 1.0).all(), t0
        assert g.left[0] == 0 and g.weight[0] == 0.0 and g.t_grid[0] <= t0, t0


def test_t_qlt_07p_the_rows_outside_the_grid_are_nan_on_the_way_back_for_any_values():
    t = np.concatenate([[0.003], np.arange(1, 100) / 30.0, [99 / 30.0 + 0.0125]])  # both ends are off the lattice
    g = plan_grid(t)
    assert g.before[0] and g.beyond[-1]
    values = np.random.default_rng(1).normal(size=(len(g.t_grid), 5))
    back = g.to_source(values)
    assert np.isnan(back[g.before | g.beyond]).all() and np.isfinite(back[~(g.before | g.beyond)]).all()


# --- the differential test: the rules written the slow way ------------------------------------------------------------
def oracle_fit(t: np.ndarray, p: ResampleParams):
    """The lattice fit of DEC-0052 with loops: ``(step, phase)`` or None."""
    n = len(t)
    d = [float(t[i + 1] - t[i]) for i in range(n - 1)]
    nominal = float(np.median(d))
    regular = [0.5 * nominal <= x <= p.max_step_s + 1e-9 for x in d]
    if not any(regular):
        return None
    runs, current = [], [0]
    for i, ok in enumerate(regular):
        if ok:
            current.append(i + 1)
        else:
            runs.append(current)
            current = [i + 1]
    runs.append(current)
    step, stats = nominal, []
    for _ in range(2):
        num = den = 0.0
        stats = []
        for run in runs:
            k = [0.0]
            for a in range(len(run) - 1):
                k.append(k[-1] + max(1.0, float(round(d[run[a]] / step))))
            tm = sum(float(t[i]) for i in run) / len(run)
            km = sum(k) / len(k)
            for kk, i in zip(k, run, strict=True):
                num += (kk - km) * (float(t[i]) - tm)
                den += (kk - km) ** 2
            stats.append((len(run), tm, km))
        if den <= 0.0:
            return None
        step = num / den
        if not (math.isfinite(step) and step > 0.0):
            return None
    rows, tm, km = max(stats, key=lambda x: x[0])  # the first of the longest
    return step, tm - step * km


def oracle_plan(t: np.ndarray, p: ResampleParams) -> dict:
    """Rules 1 to 4 and the inverse map of rule 8 (DEC-0047 as amended by DEC-0052), with loops."""
    n = len(t)
    if n <= 1:
        uniform, slope = True, float("nan")
    else:
        i = np.arange(n)
        slope, icpt = np.polyfit(i, t, 1)
        uniform = bool(np.abs(t - (icpt + slope * i)).max() <= p.uniform_tol_s + 1e-9) if n > 2 else True
    if n <= 1 or (uniform and p.grid_hz is None):
        return {
            "identity": True, "tg": t.copy(), "step": slope, "left": np.arange(n), "w": np.zeros(n),
            "stall": np.zeros(n, bool), "bl": np.arange(n), "bw": np.zeros(n), "before": np.zeros(n, bool),
            "beyond": np.zeros(n, bool), "snap": 0.0,
        }  # fmt: skip
    if p.grid_hz is not None:
        step, phase = 1.0 / p.grid_hz, float(t[0])
    else:
        fit = oracle_fit(t, p)
        step, phase = fit if fit is not None else (float(np.median(np.diff(t))), float(t[0]))
    snap = min(p.uniform_tol_s, 0.25 * step) + 1e-9
    j0, j1 = math.ceil((t[0] - snap - phase) / step), math.floor((t[-1] + snap - phase) / step)
    if j1 < j0:
        phase = float(t[0])
        j0, j1 = math.ceil((t[0] - snap - phase) / step), math.floor((t[-1] + snap - phase) / step)
    tg = np.array([phase + j * step for j in range(j0, j1 + 1)])
    count = len(tg)
    left, w, stall = [], [], []
    for g in tg:
        dist = [abs(g - float(x)) for x in t]
        near = min(range(n), key=lambda r: (dist[r], r))  # the nearest row, the earlier on a tie
        if dist[near] <= snap or g <= t[0] or g >= t[-1]:
            left.append(near)
            w.append(0.0)
            stall.append(False)
        else:
            li = max(i for i in range(n) if t[i] <= g)
            left.append(li)
            w.append((g - t[li]) / (t[li + 1] - t[li]))
            stall.append(bool(t[li + 1] - t[li] > p.max_step_s + 1e-9))
    bl, bw, before, beyond = [], [], [], []
    for ti in t:
        dist = [abs(ti - float(g)) for g in tg]
        near = min(range(count), key=lambda r: (dist[r], r))
        earlier = [k for k in range(count) if tg[k] <= ti]
        if dist[near] <= snap:
            bl.append(near)
            bw.append(0.0)
            before.append(False)
            beyond.append(False)
        elif not earlier:
            bl.append(0)
            bw.append(0.0)
            before.append(True)
            beyond.append(False)
        elif max(earlier) == count - 1:
            bl.append(count - 1)
            bw.append(0.0)
            before.append(False)
            beyond.append(True)
        else:
            b = max(earlier)
            bl.append(b)
            bw.append((ti - tg[b]) / step)
            before.append(False)
            beyond.append(False)
    return {
        "identity": False, "tg": tg, "step": step, "left": np.array(left), "w": np.array(w), "stall": np.array(stall),
        "bl": np.array(bl), "bw": np.array(bw), "before": np.array(before), "beyond": np.array(beyond), "snap": snap,
    }  # fmt: skip


def oracle_cells(kp, reason, interp, plan):
    count = len(plan["tg"])
    out_kp = np.full((count, NUM_JOINTS, 2), np.nan)
    out_reason = np.zeros((count, NUM_JOINTS), np.uint8)
    out_interp = np.zeros((count, NUM_JOINTS), bool)
    mixed = np.zeros(count, bool)
    for k in range(count):
        li, w = int(plan["left"][k]), float(plan["w"][k])
        mixed[k] = w > 0.0 and not plan["stall"][k]
        for j in range(NUM_JOINTS):
            if w == 0.0:
                out_kp[k, j], out_reason[k, j], out_interp[k, j] = kp[li, j], reason[li, j], interp[li, j]
                continue
            if plan["stall"][k]:
                out_reason[k, j] = NO_FRAME
                continue
            a_ok, b_ok = bool(np.isfinite(kp[li, j, 0])), bool(np.isfinite(kp[li + 1, j, 0]))
            ra, rb = int(reason[li, j]), int(reason[li + 1, j])
            nearer = ra if w <= 0.5 + 1e-9 else rb  # the tie is the middle of a dropped frame: float noise
            if a_ok and b_ok:
                out_kp[k, j] = (1.0 - w) * np.float64(kp[li, j]) + w * np.float64(kp[li + 1, j])
                out_interp[k, j] = bool(interp[li, j] or interp[li + 1, j])
                if ra == OK and rb == OK:
                    out_reason[k, j] = OK
                elif rb == OK:
                    out_reason[k, j] = ra
                elif ra == OK:
                    out_reason[k, j] = rb
                else:
                    out_reason[k, j] = nearer
            elif b_ok:
                out_reason[k, j] = ra
            elif a_ok:
                out_reason[k, j] = rb
            else:
                out_reason[k, j] = nearer
    return out_kp, out_reason, out_interp, mixed


def oracle_back(values, plan):
    n = len(plan["bl"])
    out = np.full((n,) + values.shape[1:], np.nan)
    for i in range(n):
        b, w = int(plan["bl"][i]), float(plan["bw"][i])
        if plan["beyond"][i] or plan["before"][i]:
            continue
        if w == 0.0:
            out[i] = values[b]
            continue
        a, c = np.float64(values[b]), np.float64(values[b + 1])
        mix = (1.0 - w) * a + w * c
        out[i] = np.where(np.isfinite(a) & np.isfinite(c), mix, np.nan)
    return out


def random_case(seed: int):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(0, 50))
    step = 1.0 / float(rng.choice([24.0, 30.0, 60.0]))
    kinds = ["cfr", "drop", "jitter", "stepdown", "stall", "coarse", "msdrop", "burst", "slow"]
    kind = str(rng.choice(kinds)) if n >= 3 else "cfr"
    if kind == "cfr":
        t = np.arange(n) * step
    elif kind == "drop":
        t = (np.arange(n + 8) * step)[np.sort(rng.choice(n + 8, n, replace=False))]
    elif kind == "jitter":
        t = np.cumsum(step * (1.0 + rng.uniform(-0.3, 0.3, n)))
    elif kind == "stepdown":
        t = np.concatenate([np.arange(n // 2) * step, (n // 2 - 1) * step + np.arange(1, n - n // 2 + 1) * 0.1])
    elif kind == "stall":
        t = np.arange(n) * step
        t[int(rng.integers(1, n)) :] += float(rng.uniform(0.05, 0.6))
    elif kind == "coarse":
        t = np.round(np.arange(n) * step * 1000.0) / 1000.0
    elif kind == "msdrop":  # a sensor clock in whole milliseconds with dropped frames and a first row that is off
        t = np.round(np.sort(rng.choice(n + 10, n, replace=False)) * step * 1000.0) / 1000.0
        t[0] += float(rng.uniform(-0.004, 0.004))
    elif kind == "slow":  # a clock slower than the pause limit: every interval is a stall, nothing is regular
        t = np.cumsum(0.2 * (1.0 + rng.uniform(-0.1, 0.1, n)))
    else:  # a burst of five rows at a fifth of the step inside a regular clock
        at = int(rng.integers(1, n - 1))
        gaps = np.full(n - 1, step)
        gaps[at : at + 5] = step / 5.0
        t = np.concatenate([[0.0], np.cumsum(gaps)])
    t = t + float(rng.uniform(0.0, 3.0))
    kp = np.cumsum(rng.normal(0.0, 4.0, (n, NUM_JOINTS, 2)), axis=0) + 500.0
    reason = np.zeros((n, NUM_JOINTS), np.uint8)
    interp = np.zeros((n, NUM_JOINTS), bool)
    holes = rng.random((n, NUM_JOINTS)) < 0.15
    reason[holes] = rng.choice([LOW_CONF, NON_FINITE, NOT_TRACKED, OUTLIER, FRAME_INVALID], size=int(holes.sum()))
    kp[holes] = np.nan
    bridged = ~holes & (rng.random((n, NUM_JOINTS)) < 0.1)
    reason[bridged] = rng.choice([LOW_CONF, OUTLIER, FRAME_INVALID], size=int(bridged.sum()))
    interp[bridged] = True
    params = ResampleParams(
        grid_hz=rng.choice([None, None, 20.0, 30.0, 50.0]),
        max_step_s=float(rng.choice([0.05, 0.15, 0.3])),
        uniform_tol_s=float(rng.choice([0.0, 0.001, 0.001, 0.01])),
    )
    return kp.astype(np.float32 if seed % 2 else np.float64), reason, interp, t, params


@pytest.mark.parametrize("seed", range(300))
def test_t_qlt_07_diff_the_module_equals_the_slow_rules(seed: int):
    kp, reason, interp, t, params = random_case(seed)
    r = resample_layer(kp, reason, interp, t, params)
    g = r.gridmap
    plan = oracle_plan(t, params)
    assert g.identity == plan["identity"] and g.resampled == (not plan["identity"])
    assert len(g.t_grid) == len(plan["tg"]) and np.allclose(g.t_grid, plan["tg"], rtol=0.0, atol=1e-12)
    assert np.allclose(g.step_s, plan["step"], rtol=1e-9, atol=0.0, equal_nan=True)
    assert np.allclose(g.snap_s, plan["snap"], rtol=1e-9, atol=1e-12)
    assert np.array_equal(g.left, plan["left"]) and np.allclose(g.weight, plan["w"], rtol=0.0, atol=1e-12)
    assert np.array_equal(g.stall, plan["stall"])
    assert np.array_equal(g.back_left, plan["bl"]) and np.allclose(g.back_weight, plan["bw"], rtol=0.0, atol=1e-9)
    assert np.array_equal(g.before, plan["before"]) and np.array_equal(g.beyond, plan["beyond"])
    want_kp, want_reason, want_interp, want_mixed = oracle_cells(kp, reason, interp, plan)
    assert np.array_equal(r.reason, want_reason) and np.array_equal(r.interpolated, want_interp)
    assert np.array_equal(r.mixed, want_mixed)
    assert np.allclose(r.keypoints, want_kp.astype(kp.dtype), rtol=1e-6, atol=1e-4, equal_nan=True)
    assert np.array_equal(np.isnan(r.keypoints), np.isnan(want_kp))
    if len(g.t_grid):
        check_gap_layer(r.keypoints, r.reason, r.interpolated, g.t_grid)  # the result obeys the contract
        values = np.array(r.keypoints)
        values[np.random.default_rng(seed).random(values.shape[:2]) < 0.1] = np.nan
        assert np.allclose(g.to_source(values), oracle_back(values, plan), rtol=1e-6, atol=1e-4, equal_nan=True)
        assert np.array_equal(np.isnan(g.to_source(values)), np.isnan(oracle_back(values, plan)))
        usable = np.isfinite(kp[..., 0])  # the layer gives no value where the source had none
        want = np.where(usable[..., None], oracle_back(values, plan), np.nan)
        assert np.array_equal(r.source_usable, usable)
        assert np.allclose(r.to_source(values), want, rtol=1e-6, atol=1e-4, equal_nan=True)
        assert np.array_equal(np.isnan(r.to_source(values)), np.isnan(want))


def test_t_qlt_07_diff_the_random_cases_reach_every_branch_of_the_rules():
    """The 300 cases are not all identities or empty: every kind of clock and every outcome of the map is in them."""
    seen = {"identity": 0, "fit": 0, "fallback": 0, "snap": 0, "mix": 0, "stall": 0, "before": 0, "beyond": 0}
    for seed in range(300):
        _, _, _, t, params = random_case(seed)
        plan = oracle_plan(t, params)
        if plan["identity"]:
            seen["identity"] += 1
            continue
        if params.grid_hz is None:
            seen["fit" if oracle_fit(t, params) is not None else "fallback"] += 1
        seen["snap"] += int(((plan["w"] == 0.0) & (np.abs(plan["tg"] - t[plan["left"]]) > 1e-9)).any())
        seen["mix"] += int((plan["w"] > 0.0).any())
        seen["stall"] += int(plan["stall"].any())
        seen["before"] += int(plan["before"].any())
        seen["beyond"] += int(plan["beyond"].any())
    assert all(v >= 5 for v in seen.values()), seen
