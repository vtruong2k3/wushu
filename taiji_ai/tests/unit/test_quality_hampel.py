"""P4.03: the Hampel filter: isolated spikes of a joint are flagged ``outlier`` and set to NaN (T-QLT-06).

Arrays are built by hand: no video, no model. A window of 7 rows is centred on a cell; the cell is an outlier if it is
further from the median of the counted cells of the window than ``n_sigma`` x ``1.4826`` x MAD, in x or in y (the floor
``scale_floor_px`` and the time cut ``max_half_span_s`` are described in ``quality/filters.py``). To know exactly what a
test window holds, many tests use one joint (joint 0), x only, and keep y at 0 (a constant: its MAD is 0 and its
deviation 0, so it is never flagged); the cells of every other joint are constant too.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.synth import make_sequence
from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality.filters import (
    DEFAULT_SCALE_FLOOR_PX,
    MAD_TO_SIGMA,
    TORSO_JOINTS,
    HampelParams,
    hampel_outliers,
    torso_length_px,
)
from taiji_ai.quality.mask import LOW_CONF, NON_FINITE, NOT_TRACKED, OK, OUTLIER

# the rule as written in W6 (window 7, 3 sigma, no floor); the defaults add the floor chosen with M-QLT-03 (DEC-0046)
W6 = HampelParams(scale_floor_px=0.0)


def smooth_kp(t: np.ndarray, dtype=np.float64, speed: float = 1.0) -> np.ndarray:
    """A smooth, large movement of every joint: a sine in x and a cosine in y, no noise."""
    j = np.arange(NUM_JOINTS)[None, :]
    kp = np.empty((len(t), NUM_JOINTS, 2), np.float64)
    kp[..., 0] = 300.0 + 20.0 * j + 80.0 * np.sin(1.5 * speed * t[:, None] + 0.3 * j)
    kp[..., 1] = 400.0 + 5.0 * j + 60.0 * np.cos(1.1 * speed * t[:, None] + 0.2 * j)
    return kp.astype(dtype)


def smooth_layer(frames: int = 60, fps: float = 30.0, dtype=np.float64, speed: float = 1.0):
    t = np.arange(frames) / fps
    return smooth_kp(t, dtype, speed), np.zeros((frames, NUM_JOINTS), np.uint8), t


def window_layer(values, fps: float = 30.0, y: float = 0.0):
    """The x of joint 0 follows ``values``; everything else is constant. One cell per row for joint 0."""
    n = len(values)
    kp = np.zeros((n, NUM_JOINTS, 2), np.float64)
    kp[:, 0, 0] = values
    kp[..., 1] = y
    return kp, np.zeros((n, NUM_JOINTS), np.uint8), np.arange(n) / fps


def hide(kp, reason, joint: int, rows, code: int = LOW_CONF) -> None:
    for r in np.atleast_1d(rows):
        kp[r, joint] = np.nan
        reason[r, joint] = code


# --- the constants and the defaults -------------------------------------------------------------------------------
def test_t_qlt_06_the_defaults_are_the_w6_values_the_proposals_of_the_plan_and_the_floor_of_m_qlt_03():
    p = HampelParams()
    assert (p.window, p.n_sigma, p.min_observed, p.max_half_span_s, p.scale_floor_px) == (7, 3.0, 5, 0.25, 2.0)
    assert DEFAULT_SCALE_FLOOR_PX == 2.0 and W6.scale_floor_px == 0.0 and HampelParams(scale_floor_px=0).window == 7
    assert MAD_TO_SIGMA == 1.4826
    assert HampelParams(window=5).min_observed == 4 and HampelParams(window=3).min_observed == 3
    assert HampelParams(window=9).min_observed == 6 and HampelParams(window=7, min_observed=3).min_observed == 3


# --- T-QLT-06a: spikes are found exactly ------------------------------------------------------------------------------
def test_t_qlt_06a_isolated_spikes_are_flagged_exactly_and_nothing_else_changes():
    kp, reason, t = smooth_layer(60)
    expected = np.zeros(reason.shape, bool)
    for frame, joint, dx, dy in (
        (10, 3, 50.0, 0.0),  # x only
        (25, 9, 0.0, -60.0),  # y only
        (40, 17, 45.0, 45.0),  # both
        (30, 20, 0.0, 70.0),  # two spikes in a row on one joint, later
        (31, 20, 0.0, -70.0),
    ):
        kp[frame, joint] += (dx, dy)
        expected[frame, joint] = True
    spiked, reason_before = kp.copy(), reason.copy()
    r = hampel_outliers(spiked, reason, t)  # the defaults
    assert np.array_equal(r.outlier, expected)
    assert np.isnan(r.keypoints[expected]).all() and (r.reason[expected] == OUTLIER).all()
    assert r.keypoints[~expected].tobytes() == spiked[~expected].tobytes()  # every other cell is byte-identical
    assert np.array_equal(r.reason[~expected], reason_before[~expected])
    assert r.params == HampelParams()
    assert np.array_equal(hampel_outliers(spiked, reason, t, W6).outlier, expected)  # and the rule as written


def test_t_qlt_06a_the_parameters_that_were_used_travel_with_the_result():
    kp, reason, t = smooth_layer(30)
    params = HampelParams(window=5, n_sigma=4.0, min_observed=3, max_half_span_s=0.5, scale_floor_px=1.5)
    assert hampel_outliers(kp, reason, t, params).params == params
    assert hampel_outliers(kp, reason, t).params == HampelParams()


@pytest.mark.parametrize("run", [1, 2, 3])
def test_t_qlt_06a_a_run_of_up_to_three_spiked_rows_in_a_window_of_seven_is_found(run: int):
    """With three spikes the MAD is the largest deviation of a good row, so the spike must be large against the local
    movement (here 300 px against about 4 px per frame): the rule is about the rows, and the size has to carry."""
    kp, reason, t = smooth_layer(60)
    rows = np.arange(30, 30 + run)
    kp[rows, 5, 0] += 300.0
    r = hampel_outliers(kp, reason, t)
    assert np.array_equal(np.flatnonzero(r.outlier[:, 5]), rows) and r.outlier.sum() == run


# --- T-QLT-06b: real movement is not a spike -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "make",
    [
        lambda: smooth_layer(120, 30.0, speed=1.0),
        lambda: smooth_layer(120, 30.0, speed=2.0),  # twice as fast: 20 px per frame at the peak
        lambda: smooth_layer(120, 60.0, speed=2.0),
        lambda: window_layer(100.0 + 400.0 * np.arange(60) / 30.0),  # a straight line at 400 px/s
        lambda: window_layer(np.abs(np.arange(-30, 31)) * 12.0),  # a sharp reversal: a triangle wave
        lambda: window_layer(np.concatenate([np.zeros(30), np.full(30, 200.0)])),  # a step: a jump is not a spike
    ],
)
@pytest.mark.parametrize("params", [W6, HampelParams()], ids=["rule-as-written", "defaults"])
def test_t_qlt_06b_smooth_large_movements_reversals_and_steps_are_not_flagged(make, params: HampelParams):
    kp, reason, t = make()
    assert not hampel_outliers(kp, reason, t, params).outlier.any()


@pytest.mark.parametrize("params", [W6, HampelParams()], ids=["rule-as-written", "defaults"])
def test_t_qlt_06b_the_fast_cosine_ramps_and_pauses_of_syn_05_are_not_flagged(params: HampelParams):
    seq = make_sequence("SYN-05", seed=5, noise_px=0.0)
    kp = np.asarray(seq.kp_true, dtype=np.float64)
    r = hampel_outliers(kp, np.zeros(kp.shape[:2], np.uint8), seq.t_sec, params)
    assert r.judged.sum() > 0.9 * kp.shape[0] * NUM_JOINTS and not r.outlier.any()


# --- T-QLT-06c: the boundary and the 1.4826 ---------------------------------------------------------------------------
# The window [-2, -1, -1, v, 1, 1, 2] has the median 1 and the MAD 2 for any v from 2 on: sigma = 1.4826 x 2 = 2.9652,
# so the cell is an outlier from a deviation of 3 x 2.9652 = 8.8956 on (3 x MAD alone would be 6). Its mirror image
# has the median -1.
@pytest.mark.parametrize(
    ("v", "flagged"),
    [(9.8, False), (10.0, True), (8.0, False), (30.0, True), (-6.0, False), (-9.8, False), (-10.0, True)],
)
def test_t_qlt_06c_three_sigma_is_three_times_1_4826_mad_not_three_times_mad(v: float, flagged: bool):
    """A deviation of 7 (v = 8) would be flagged by 3 x MAD (6) and is kept by 3 x 1.4826 x MAD (8.9)."""
    values = [-2.0, -1.0, -1.0, v, 1.0, 1.0, 2.0] if v > 0 else [2.0, 1.0, 1.0, v, -1.0, -1.0, -2.0]
    kp, reason, t = window_layer(values)
    r = hampel_outliers(kp, reason, t, W6)
    assert bool(r.outlier[3, 0]) is flagged and r.outlier.sum() == int(flagged)
    assert r.judged[3, 0]


def test_t_qlt_06c_a_deviation_of_exactly_n_sigma_is_kept_and_a_hair_more_is_flagged():
    # a constant window has MAD 0, so sigma is the floor: 2.0 x 3 = 6.0 exactly
    params = HampelParams(scale_floor_px=2.0)
    at, over = (window_layer([0, 0, 0, v, 0, 0, 0]) for v in (6.0, 6.000001))
    assert not hampel_outliers(*at, params).outlier.any()
    assert hampel_outliers(*over, params).outlier[3, 0]
    wide = HampelParams(scale_floor_px=2.0, n_sigma=3.5)  # the number of sigmas is a parameter
    assert not hampel_outliers(*over, wide).outlier.any()
    assert hampel_outliers(*window_layer([0, 0, 0, 7.000001, 0, 0, 0]), wide).outlier[3, 0]


# --- T-QLT-06d: MAD = 0 ---------------------------------------------------------------------------------------------
def test_t_qlt_06d_in_a_constant_window_a_spike_is_flagged_and_an_identical_value_is_not():
    spike = hampel_outliers(*window_layer([100, 100, 100, 150, 100, 100, 100]), W6)
    assert spike.outlier[3, 0] and spike.outlier.sum() == 1  # the neighbours see the spike only as one of seven
    still = hampel_outliers(*window_layer([100.0] * 12), W6)
    assert not still.outlier.any() and still.judged[1:-1].all()
    tiny = hampel_outliers(*window_layer([100, 100, 100, 100.000001, 100, 100, 100]), W6)
    assert tiny.outlier[3, 0]  # with no floor, any deviation from a window with MAD 0 counts: the rule as written
    assert not hampel_outliers(*window_layer([100, 100, 100, 100.000001, 100, 100, 100])).outlier.any()  # the default


def test_t_qlt_06d_the_floor_keeps_a_tiny_deviation_and_still_finds_a_large_spike():
    params = HampelParams(scale_floor_px=0.5)  # 3 x 0.5 = 1.5 px
    assert not hampel_outliers(*window_layer([100, 100, 100, 101.4, 100, 100, 100]), params).outlier.any()
    assert hampel_outliers(*window_layer([100, 100, 100, 101.6, 100, 100, 100]), params).outlier[3, 0]
    assert hampel_outliers(*window_layer([100, 100, 100, 150, 100, 100, 100]), params).outlier[3, 0]
    noisy = window_layer([100, 103, 97, 150, 99, 104, 96])  # a floor below the real spread changes nothing
    assert np.array_equal(hampel_outliers(*noisy, params).outlier, hampel_outliers(*noisy, W6).outlier)


def test_t_qlt_06d_the_floor_is_a_lower_bound_of_sigma_not_an_addition_to_it():
    """The window [-2, -1, -1, v, 1, 1, 2] has sigma 2.9652: a floor of 2 is below it and changes nothing, so the cell
    is an outlier from a deviation of 8.8956 on, with or without the floor."""
    below = HampelParams(scale_floor_px=2.0)
    assert hampel_outliers(*window_layer([-2.0, -1.0, -1.0, 10.0, 1.0, 1.0, 2.0]), below).outlier[3, 0]  # deviation 9
    assert not hampel_outliers(*window_layer([-2.0, -1.0, -1.0, 9.8, 1.0, 1.0, 2.0]), below).outlier.any()  # 8.8
    above = HampelParams(scale_floor_px=4.0)  # a floor above sigma takes over: 3 x 4 = 12
    assert not hampel_outliers(*window_layer([-2.0, -1.0, -1.0, 12.0, 1.0, 1.0, 2.0]), above).outlier.any()  # 11
    assert hampel_outliers(*window_layer([-2.0, -1.0, -1.0, 13.5, 1.0, 1.0, 2.0]), above).outlier[3, 0]  # 12.5


# --- T-QLT-06e: unobserved cells and the number of cells that count -----------------------------------------------
def test_t_qlt_06e_unobserved_cells_are_never_flagged_nor_changed_and_do_not_count():
    kp, reason, t = smooth_layer(40)
    hide(kp, reason, 4, 10, NON_FINITE)
    hide(kp, reason, 4, 11, NOT_TRACKED)
    hide(kp, reason, 6, 20, LOW_CONF)
    kp[25, 4, 0] += 80.0
    before_kp, before_reason = kp.copy(), reason.copy()
    r = hampel_outliers(kp, reason, t)
    assert np.array_equal(np.argwhere(r.outlier), [[25, 4]])
    holes = before_reason != OK
    assert np.array_equal(r.reason[holes], before_reason[holes])  # a hole keeps its own reason
    assert np.isnan(r.keypoints[holes]).all() and not r.judged[holes].any()
    assert np.array_equal(r.keypoints[~holes & ~r.outlier], before_kp[~holes & ~r.outlier])


def test_t_qlt_06e_fewer_than_min_observed_counted_cells_means_not_judged_and_never_flagged():
    values = [0, 0, 0, 90.0, 0, 0, 0, 0, 0]  # the spike at row 3, window rows 0 to 6
    kp, reason, t = window_layer(values)
    hide(kp, reason, 0, 5)  # rows 0 to 6 hold 6 observed cells, the spike included
    assert hampel_outliers(kp, reason, t).outlier[3, 0] and hampel_outliers(kp, reason, t).judged[3, 0]
    hide(kp, reason, 0, 6)  # 5 left: still judged (min_observed is 5)
    assert hampel_outliers(kp, reason, t).outlier[3, 0]
    hide(kp, reason, 0, 1)  # 4 left: not judged, so not flagged, and the spike stays
    r = hampel_outliers(kp, reason, t)
    assert not r.judged[3, 0] and not r.outlier.any() and r.keypoints[3, 0, 0] == 90.0
    assert hampel_outliers(kp, reason, t, HampelParams(min_observed=4)).outlier[3, 0]  # the count is a parameter


def test_t_qlt_06e_the_first_and_last_rows_get_a_short_window_and_are_judged_only_if_enough_rows_count():
    kp, reason, t = smooth_layer(12)
    r = hampel_outliers(kp, reason, t)
    assert not r.judged[0].any() and not r.judged[-1].any()  # 4 rows at the edge: under 5
    assert r.judged[1].all() and r.judged[-2].all() and r.judged[1:-1].all()  # 5 rows from the second
    short = hampel_outliers(kp, reason, t, HampelParams(min_observed=3))
    assert short.judged.all()
    edge = window_layer([200.0, 0, 0, 0, 0, 0, 0, 0, 0])[0]
    assert hampel_outliers(
        edge, np.zeros(edge.shape[:2], np.uint8), np.arange(9) / 30.0, HampelParams(min_observed=3)
    ).outlier[0, 0]


# --- T-QLT-06f: real time cuts the window ---------------------------------------------------------------------------
def test_t_qlt_06f_a_stall_in_the_middle_of_a_window_cuts_it():
    values = [0, 0, 0, 90.0, 0, 0, 0, 0, 0, 0]
    kp, reason, _ = window_layer(values)
    t = np.array([0.0, 0.033, 0.066, 0.1, 10.0, 10.033, 10.066, 10.1, 10.133, 10.166])  # a 10 s stall after row 3
    r = hampel_outliers(kp, reason, t)
    assert not r.judged[3, 0] and not r.outlier.any()  # rows 0 to 3 count: 4 cells, under 5
    assert hampel_outliers(kp, reason, t, HampelParams(min_observed=4)).outlier[3, 0]
    t_fast = np.arange(10) / 30.0  # the same values without the stall
    assert hampel_outliers(kp, reason, t_fast).outlier[3, 0]


@pytest.mark.parametrize(("fps", "judged"), [(60.0, True), (30.0, True), (15.0, True), (10.0, True), (5.0, False)])
def test_t_qlt_06f_the_window_counts_rows_and_time_only_cuts_it_at_a_stall(fps: float, judged: bool):
    kp, reason, t = window_layer([0, 0, 0, 90.0, 0, 0, 0, 0, 0], fps=fps)
    r = hampel_outliers(kp, reason, t)
    assert bool(r.judged[3, 0]) is judged and bool(r.outlier[3, 0]) is judged
    # at 10 fps rows 3 away are 0.3 s off and are cut, 5 rows remain; at 5 fps only the rows next to the cell remain


@pytest.mark.parametrize(
    ("spacing", "judged"),
    [(0.25, True), (0.25 + 5e-10, True), (0.25 + 1e-6, False), (0.1, True)],
)
def test_t_qlt_06f_a_row_exactly_at_the_limit_counts_and_one_beyond_it_does_not(spacing: float, judged: bool):
    """Rows next to the cell are ``spacing`` away, the next ones twice that; only rows within 0.25 s (+1e-9 s) count."""
    kp, reason, _ = window_layer([0, 0, 0, 90.0, 0, 0, 0])
    r = hampel_outliers(kp, reason, np.arange(7) * spacing, HampelParams(min_observed=3, max_half_span_s=0.25))
    assert bool(r.judged[3, 0]) is judged and bool(r.outlier[3, 0]) is judged


def test_t_qlt_06f_the_time_cut_is_a_parameter():
    kp, reason, _ = window_layer([0, 0, 0, 90.0, 0, 0, 0])
    t = np.arange(7) * 0.4  # the outer rows are 1.2 s away
    assert not hampel_outliers(kp, reason, t, HampelParams(min_observed=7)).judged[3, 0]  # cut at 0.25 s: 1 row counts
    assert hampel_outliers(kp, reason, t, HampelParams(min_observed=7, max_half_span_s=1.2)).outlier[3, 0]


# --- T-QLT-06g: the result ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_t_qlt_06g_inputs_are_not_changed_outputs_are_new_and_read_only_and_dtypes_are_kept(dtype):
    kp, reason, t = smooth_layer(40, dtype=dtype)
    kp[20, 7, 1] += 70.0
    before = (kp.copy(), reason.copy(), t.copy())
    r = hampel_outliers(kp, reason, t)
    for given, kept in zip((kp, reason, t), before, strict=True):
        assert np.array_equal(given, kept)
    assert r.keypoints.dtype == dtype and r.reason.dtype == np.uint8
    assert r.outlier.dtype == bool and r.judged.dtype == bool
    for arr in (r.keypoints, r.reason, r.outlier, r.judged):
        assert not arr.flags.writeable and not np.shares_memory(arr, kp) and not np.shares_memory(arr, reason)
    with pytest.raises(ValueError, match="read-only"):
        r.keypoints[0, 0, 0] = 1.0
    assert r.outlier[20, 7] and r.outlier.sum() == 1


def test_t_qlt_06g_the_outliers_are_inside_the_judged_cells_and_the_reasons_change_only_there():
    kp, reason, t = smooth_layer(50)
    hide(kp, reason, 2, [5, 6, 7])
    kp[25, 2, 0] += 60.0
    kp[30, 11, 1] -= 60.0
    r = hampel_outliers(kp, reason, t)
    assert (r.outlier <= r.judged).all() and (r.judged <= (reason == OK)).all()
    changed = r.reason != reason
    assert np.array_equal(changed, r.outlier) and (r.reason[r.outlier] == OUTLIER).all()


def test_t_qlt_06g_a_result_can_be_run_again_and_its_holes_stay_what_they_were():
    kp, reason, t = smooth_layer(50)
    kp[25, 2, 0] += 60.0
    first = hampel_outliers(kp, reason, t)
    second = hampel_outliers(first.keypoints, first.reason, t)  # a valid layer: NaN exactly where reason is not ok
    holes = first.reason != OK
    assert np.array_equal(second.reason[holes], first.reason[holes]) and np.isnan(second.keypoints[holes]).all()
    assert not (second.outlier & holes).any()


# --- T-QLT-06h: invariants ----------------------------------------------------------------------------------------
def spiky_layer(seed: int = 3):
    rng = np.random.default_rng(seed)
    n = 80
    t = np.cumsum(rng.uniform(0.02, 0.06, n))
    kp = np.cumsum(rng.normal(0, 2.0, (n, NUM_JOINTS, 2)), axis=0) + 500.0
    spikes = rng.random((n, NUM_JOINTS)) < 0.05
    kp[spikes] += rng.choice([-1, 1], (spikes.sum(), 2)) * 40.0
    reason = np.zeros((n, NUM_JOINTS), np.uint8)
    holes = rng.random((n, NUM_JOINTS)) < 0.05
    reason[holes] = LOW_CONF
    kp[holes] = np.nan
    return kp, reason, t


@pytest.mark.parametrize("floor", [0.0, 1.5])
def test_t_qlt_06h_scaling_the_coordinates_and_the_floor_by_k_changes_no_flag(floor: float):
    kp, reason, t = spiky_layer()
    base = hampel_outliers(kp, reason, t, HampelParams(scale_floor_px=floor))
    assert 0 < base.outlier.sum() < base.judged.sum()  # the layer is not trivial
    for k in (0.25, 3.0, 8.0):
        scaled = hampel_outliers(kp * k, reason, t, HampelParams(scale_floor_px=floor * k))
        assert np.array_equal(scaled.outlier, base.outlier), k


def test_t_qlt_06h_shifting_the_coordinates_and_the_clock_and_permuting_the_joints_change_nothing_else():
    kp, reason, t = spiky_layer()
    base = hampel_outliers(kp, reason, t)
    assert 0 < base.outlier.sum() < base.judged.sum()  # the layer is not trivial
    shifted = hampel_outliers(kp + 1000.0, reason, t + 123.456)
    assert np.array_equal(shifted.outlier, base.outlier)
    perm = np.random.default_rng(7).permutation(NUM_JOINTS)
    moved = hampel_outliers(kp[:, perm], reason[:, perm], t)
    assert np.array_equal(moved.outlier, base.outlier[:, perm]) and np.array_equal(moved.judged, base.judged[:, perm])


@pytest.mark.parametrize("block_rows", [1, 5, 7, 64])
def test_t_qlt_06h_blocks_of_rows_give_the_answer_of_one_pass(block_rows: int):
    kp, reason, t = spiky_layer()
    whole = hampel_outliers(kp, reason, t, block_rows=10_000)
    assert 0 < whole.outlier.sum() < whole.judged.sum()  # the layer is not trivial
    blocks = hampel_outliers(kp, reason, t, block_rows=block_rows)
    assert np.array_equal(blocks.outlier, whole.outlier) and np.array_equal(blocks.judged, whole.judged)
    assert np.array_equal(blocks.keypoints, whole.keypoints, equal_nan=True)


# --- T-QLT-06i: a differential test against the rule written the slow way ---------------------------------------------
def oracle(kp, reason, t, p: HampelParams):
    """The rule of the plan cell by cell and window by window, with ``np.median``."""
    n, half = len(t), p.window // 2
    outlier = np.zeros((n, NUM_JOINTS), bool)
    judged = np.zeros((n, NUM_JOINTS), bool)
    kp64 = np.asarray(kp, dtype=np.float64)
    for j in range(NUM_JOINTS):
        for i in range(n):
            if reason[i, j] != OK:
                continue
            rows = [
                k
                for k in range(max(0, i - half), min(n, i + half + 1))
                if reason[k, j] == OK and abs(t[k] - t[i]) <= p.max_half_span_s + 1e-9
            ]
            if len(rows) < p.min_observed:
                continue
            judged[i, j] = True
            for c in range(2):
                values = kp64[rows, j, c]
                m = np.median(values)
                mad = np.median(np.abs(values - m))
                sigma = max(MAD_TO_SIGMA * mad, p.scale_floor_px)
                if abs(kp64[i, j, c] - m) > p.n_sigma * sigma:
                    outlier[i, j] = True
    return outlier, judged


def random_layer(seed: int):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 60))
    t = float(rng.uniform(0, 5)) + np.cumsum(rng.uniform(0.01, 0.4, n))  # some steps are longer than the time cut
    kp = np.cumsum(rng.normal(0, 3.0, (n, NUM_JOINTS, 2)), axis=0) + 500.0
    spikes = rng.random((n, NUM_JOINTS)) < 0.05
    kp[spikes] += rng.normal(0, 40.0, (int(spikes.sum()), 2))
    if rng.random() < 0.3:
        kp[: n // 2] = np.round(kp[: n // 2])  # ties and constant stretches: MAD = 0 happens
    reason = np.zeros((n, NUM_JOINTS), np.uint8)
    holes = rng.random((n, NUM_JOINTS)) < 0.2
    reason[holes] = rng.choice([LOW_CONF, NON_FINITE, NOT_TRACKED], size=int(holes.sum()))
    kp[reason != OK] = np.nan
    window = int(rng.choice([3, 5, 7, 9]))
    params = HampelParams(
        window=window,
        n_sigma=float(rng.choice([2.0, 3.0, 4.0])),
        min_observed=int(rng.integers(3, window + 1)),
        max_half_span_s=float(rng.choice([0.1, 0.25, 0.5])),
        scale_floor_px=float(rng.choice([0.0, 0.5, 2.0])),
    )
    return kp.astype(np.float32 if seed % 2 else np.float64), reason, t, params


@pytest.mark.parametrize("seed", range(200))
def test_t_qlt_06i_the_module_equals_the_slow_rule_and_keeps_its_invariants(seed: int):
    kp, reason, t, params = random_layer(seed)
    r = hampel_outliers(kp, reason, t, params, block_rows=int(np.random.default_rng(seed).integers(1, 90)))
    want_outlier, want_judged = oracle(kp, reason, t, params)
    assert np.array_equal(r.judged, want_judged) and np.array_equal(r.outlier, want_outlier)
    observed = reason == OK
    assert (r.outlier <= r.judged).all() and (r.judged <= observed).all()
    keep = ~r.outlier
    assert np.array_equal(r.keypoints[keep], kp[keep], equal_nan=True)  # nothing but the outliers changes
    assert np.isnan(r.keypoints[r.outlier]).all()
    assert np.array_equal(r.reason != reason, r.outlier) and (r.reason[r.outlier] == OUTLIER).all()


# --- the weakness of the rule as written, as a measured fact -------------------------------------------------------
def test_t_qlt_06m_on_pure_gaussian_noise_the_rule_as_written_flags_about_five_percent_of_the_coordinates():
    """Window 7 and 3 sigma: the MAD of seven numbers is a noisy estimate, so the rule flags 4.8 % of noise with no
    spike in it (a simulation of 200,000 samples). This is why the defaults carry a floor (DEC-0046): with the floor of
    2 px, jitter of 1 px (sigma) is never flagged."""
    rng = np.random.default_rng(11)
    n = 8000
    kp = np.zeros((n, NUM_JOINTS, 2))
    kp[..., 0] = rng.normal(0.0, 1.0, (n, NUM_JOINTS))  # y stays 0: only x can flag a cell
    reason, t = np.zeros((n, NUM_JOINTS), np.uint8), np.arange(n) / 30.0
    r = hampel_outliers(kp, reason, t, W6)
    rate = r.outlier.sum() / r.judged.sum()
    assert 0.046 < rate < 0.050, rate
    floored = hampel_outliers(kp, reason, t)  # the defaults: 3 x 2 px = 6 px, six sigma of this noise
    assert floored.outlier.sum() == 0 and floored.judged.sum() == r.judged.sum()


# --- T-QLT-06j: bad input is refused naming the argument -----------------------------------------------------------
def good():
    return smooth_layer(12)


def with_nan_ok():
    kp, reason, t = good()
    kp[3, 4] = np.nan
    return kp, reason, t


def with_value_and_reason():
    kp, reason, t = good()
    reason[3, 4] = LOW_CONF
    return kp, reason, t


def with_equal_times():
    kp, reason, t = good()
    t[5] = t[4]
    return kp, reason, t


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: (good()[0].astype(np.int32), good()[1], good()[2]), "keypoints"),
        (lambda: (good()[0][:, :, 0], good()[1], good()[2]), "keypoints"),
        (lambda: (good()[0][:, :25], good()[1], good()[2]), "keypoints"),
        (lambda: (good()[0], good()[1][:-1], good()[2]), "reason"),
        (lambda: (good()[0], good()[1].astype(np.int64), good()[2]), "reason"),
        (lambda: (good()[0], good()[1], good()[2][:-1]), "t_sec"),
        (lambda: (good()[0], good()[1], (good()[2] * 30).astype(np.int64)), "t_sec"),
        (with_equal_times, "strictly increasing"),
        (with_nan_ok, "NaN"),
        (with_value_and_reason, "finite"),
    ],
)
def test_t_qlt_06j_bad_arrays_are_refused_naming_the_argument(make, message: str):
    kp, reason, t = make()
    with pytest.raises(QualityError, match=message):
        hampel_outliers(kp, reason, t)


@pytest.mark.parametrize("bad", [0, -1, 6, 1, 2, True, 7.5, "7", None, 4])
def test_t_qlt_06j_a_wrong_window_is_refused(bad):
    with pytest.raises(QualityError, match="window must"):  # the window is named, not another argument
        HampelParams(window=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf"), True, "3", None])
def test_t_qlt_06j_a_wrong_n_sigma_is_refused(bad):
    with pytest.raises(QualityError, match="n_sigma"):
        HampelParams(n_sigma=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [2, 8, 0, -3, True, 4.5, "5"])
def test_t_qlt_06j_a_wrong_min_observed_is_refused(bad):
    with pytest.raises(QualityError, match="min_observed"):
        HampelParams(window=7, min_observed=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0.0, -0.1, float("nan"), float("inf"), True, "0.25", None])
def test_t_qlt_06j_a_wrong_time_cut_is_refused(bad):
    with pytest.raises(QualityError, match="max_half_span_s"):
        HampelParams(max_half_span_s=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf"), True, "1", None])
def test_t_qlt_06j_a_wrong_floor_is_refused(bad):
    with pytest.raises(QualityError, match="scale_floor_px"):
        HampelParams(scale_floor_px=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, -4, True, 2.5, "8", None])
def test_t_qlt_06j_a_wrong_block_size_is_refused(bad):
    kp, reason, t = good()
    with pytest.raises(QualityError, match="block_rows"):
        hampel_outliers(kp, reason, t, block_rows=bad)  # type: ignore[arg-type]


def test_t_qlt_06j_empty_and_tiny_inputs_are_fine():
    empty = hampel_outliers(np.zeros((0, NUM_JOINTS, 2)), np.zeros((0, NUM_JOINTS), np.uint8), np.zeros(0))
    assert empty.keypoints.shape == (0, NUM_JOINTS, 2) and not empty.outlier.any() and not empty.judged.any()
    one = hampel_outliers(np.zeros((1, NUM_JOINTS, 2)), np.zeros((1, NUM_JOINTS), np.uint8), np.array([0.0]))
    assert not one.judged.any() and not one.outlier.any()


# --- T-QLT-06n: the torso, the scale a floor in pixels is read against ------------------------------------------------
LS, RS, LH, RH = TORSO_JOINTS


def torso_layer(lengths, x: float = 100.0):
    """Shoulders at y = 100, hips ``length`` below, both pairs centred on ``x``; every other joint is hidden."""
    n = len(lengths)
    kp = np.full((n, NUM_JOINTS, 2), np.nan)
    reason = np.full((n, NUM_JOINTS), LOW_CONF, np.uint8)
    for i, length in enumerate(lengths):
        hips = 100.0 + length
        for joint, (dx, y) in ((LS, (-10.0, 100.0)), (RS, (10.0, 100.0)), (LH, (-5.0, hips)), (RH, (5.0, hips))):
            kp[i, joint] = (x + dx, y)
            reason[i, joint] = OK
    return kp, reason


def test_t_qlt_06n_the_torso_is_the_distance_between_the_middle_of_the_shoulders_and_the_middle_of_the_hips():
    kp, reason = torso_layer([200.0] * 4)
    assert torso_length_px(kp, reason) == pytest.approx(200.0)
    kp[:, [LH, RH], 0] += 30.0  # the hips shift sideways: the distance is not the height
    assert torso_length_px(kp, reason) == pytest.approx(np.hypot(30.0, 200.0))
    assert torso_length_px(kp * 3.0, reason) == pytest.approx(3.0 * np.hypot(30.0, 200.0))  # it is in pixels
    assert TORSO_JOINTS == (5, 6, 11, 12)  # LShoulder, RShoulder, LHip, RHip of halpe26/1


def test_t_qlt_06n_it_is_the_median_over_the_frames_that_have_all_four_joints():
    kp, reason = torso_layer([190.0, 200.0, 210.0, 1000.0])
    hide(kp, reason, RH, 3)  # the frame that would say 1000 lacks a hip: it is not used
    assert torso_length_px(kp, reason) == pytest.approx(200.0)
    outlier = torso_layer([100.0, 100.0, 400.0])  # the median, not the mean
    assert torso_length_px(*outlier) == pytest.approx(100.0)
    kp, reason = torso_layer([200.0] * 3)
    hide(kp, reason, LS, 1, code=OUTLIER)  # a flagged cell is not observed either
    hide(kp, reason, LH, 2, code=NOT_TRACKED)
    assert torso_length_px(kp, reason) == pytest.approx(200.0)
    assert torso_length_px(kp.astype(np.float32), reason) == pytest.approx(200.0)


def test_t_qlt_06n_a_float32_layer_is_measured_in_double_precision():
    """The formula is written out here, on the float32 values, in float64: the answer must agree to rounding error, so
    the sum of two float32 coordinates is not rounded to float32 on the way."""
    kp, reason = torso_layer([180.0, 195.5, 201.25, 190.0, 210.75])
    kp = (kp + np.random.default_rng(3).normal(0.0, 3.0, kp.shape)).astype(np.float32)
    k = kp.astype(np.float64)
    want = np.median(np.linalg.norm((k[:, LS] + k[:, RS]) / 2.0 - (k[:, LH] + k[:, RH]) / 2.0, axis=-1))
    assert torso_length_px(kp, reason) == pytest.approx(want, rel=1e-12)


def test_t_qlt_06n_a_torso_that_cannot_be_measured_is_nan_not_zero():
    kp, reason = torso_layer([200.0, 200.0])
    hide(kp, reason, LS, 0)
    hide(kp, reason, RH, 1)
    assert np.isnan(torso_length_px(kp, reason))  # no frame has the four joints
    assert np.isnan(torso_length_px(np.zeros((0, NUM_JOINTS, 2)), np.zeros((0, NUM_JOINTS), np.uint8)))
    flat = torso_layer([0.0, 0.0])  # shoulders and hips on one point: no length to speak of
    assert np.isnan(torso_length_px(*flat))
    mixed = torso_layer([0.0, 150.0, 0.0])
    assert torso_length_px(*mixed) == pytest.approx(150.0)  # the degenerate frames are left out


@pytest.mark.parametrize("bad", ["ints", "shape", "reason"])
def test_t_qlt_06n_bad_arrays_are_refused_like_everywhere_else(bad: str):
    kp, reason = torso_layer([200.0] * 3)
    args = {
        "ints": (np.zeros((3, NUM_JOINTS, 2), np.int32), reason),
        "shape": (kp[:, :, 0], reason),
        "reason": (kp, reason.astype(np.int64)),
    }[bad]
    with pytest.raises(QualityError):
        torso_length_px(*args)
    with pytest.raises(QualityError, match="keypoints"):
        torso_length_px(5.0, reason)  # type: ignore[arg-type]
    with pytest.raises(QualityError, match="NaN"):
        torso_length_px(np.where(reason[..., None] == OK, np.nan, kp), np.zeros_like(reason))


def test_t_qlt_06n_the_floor_of_the_defaults_is_about_one_percent_of_the_torso_of_the_footage_it_was_measured_on():
    assert DEFAULT_SCALE_FLOOR_PX / 197.0 == pytest.approx(0.01, abs=0.001)  # M-QLT-03: torso 197 px, floor 2 px
