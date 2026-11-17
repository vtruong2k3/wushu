"""P4.05: the Butterworth low-pass, zero phase, on each continuous run of a joint (T-QLT-08 and T-QLT-09).

Layers are built by hand: no video, no model. A *run* is a maximal sequence of rows in which a joint has a value
(observed or bridged); each run is filtered on its own by ``scipy.signal.sosfiltfilt`` (order 4, cutoff 6 Hz by default)
and a run of at most ``padlen`` rows is left as it is and flagged. The oracle of most tests is scipy itself, called run
by run."""

from __future__ import annotations

import numpy as np
import pytest
import scipy.signal as sg

from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import check_gap_layer
from taiji_ai.quality.filters import (
    RUN_ABOVE_NYQUIST,
    RUN_FILTERED,
    RUN_OUTCOME_NAMES,
    RUN_TOO_SHORT,
    ButterworthParams,
    lowpass_grid,
    lowpass_layer,
)
from taiji_ai.quality.mask import LOW_CONF, NOT_TRACKED, OUTLIER
from taiji_ai.quality.resample import resample_layer

FPS = 30.0
STEP = 1.0 / FPS
DEFAULT = ButterworthParams()


# --- builders ---------------------------------------------------------------------------------------------------------
def wave(n: int, fps: float = FPS, noise: float = 0.0, seed: int = 0, dtype=np.float64) -> np.ndarray:
    """Every joint moves smoothly (slow sines of 0.7 and 0.5 Hz, tens of pixels), plus optional white noise (px)."""
    t = np.arange(n) / fps
    j = np.arange(NUM_JOINTS)[None, :]
    kp = np.empty((n, NUM_JOINTS, 2))
    kp[..., 0] = 300.0 + 4.0 * j + 60.0 * np.sin(2.0 * np.pi * 0.7 * t[:, None] + 0.1 * j)
    kp[..., 1] = 400.0 + 3.0 * j + 40.0 * np.cos(2.0 * np.pi * 0.5 * t[:, None] + 0.2 * j)
    if noise:
        kp += np.random.default_rng(seed).normal(0.0, noise, kp.shape)
    return kp.astype(dtype)


def plain(kp: np.ndarray):
    """The layer of ``kp``: every cell observed."""
    return kp, np.zeros(kp.shape[:2], np.uint8), np.zeros(kp.shape[:2], bool)


def hole(kp, reason, joint: int, rows, code: int = LOW_CONF) -> None:
    for r in np.atleast_1d(rows):
        kp[r, joint] = np.nan
        reason[r, joint] = code


def bridge(reason, interp, joint: int, rows, code: int = LOW_CONF) -> None:
    for r in np.atleast_1d(rows):
        reason[r, joint] = code
        interp[r, joint] = True


def column_of_runs(lengths, joint: int = 3, gap: int = 2, noise: float = 1.0, seed: int = 4):
    """One joint made of runs of the given lengths separated by ``gap`` holes; every other joint is one long run."""
    n = sum(lengths) + gap * len(lengths) + 5
    kp = wave(n, noise=noise, seed=seed)
    reason = np.zeros((n, NUM_JOINTS), np.uint8)
    starts, row = [], 0
    for length in lengths:
        starts.append(row)
        row += length
        hole(kp, reason, joint, np.arange(row, row + gap))
        row += gap
    hole(kp, reason, joint, np.arange(row, n))
    return kp, reason, np.zeros((n, NUM_JOINTS), bool), starts


def oracle(kp, step_s: float, params: ButterworthParams):
    """The rules, joint by joint and run by run, with scipy as the filter and its refusal of a run that is too short."""
    n = len(kp)
    fs = 1.0 / step_s
    out = np.array(kp, copy=True)
    filtered = np.zeros((n, NUM_JOINTS), bool)
    rows = []
    above = params.cutoff_hz >= fs / 2.0
    sos = None if above else sg.butter(params.order, params.cutoff_hz, btype="low", fs=fs, output="sos")
    for j in range(NUM_JOINTS):
        usable = np.isfinite(kp[:, j, 0])
        i = 0
        while i < n:
            if not usable[i]:
                i += 1
                continue
            k = i
            while k < n and usable[k]:
                k += 1
            if above:
                outcome = RUN_ABOVE_NYQUIST
            else:
                try:
                    y = sg.sosfiltfilt(sos, kp[i:k, j].astype(np.float64), axis=0, padlen=params.padlen)
                except ValueError:  # scipy: the run is not longer than padlen
                    outcome = RUN_TOO_SHORT
                else:
                    outcome = RUN_FILTERED
                    out[i:k, j] = y.astype(kp.dtype)
                    filtered[i:k, j] = True
            rows.append((j, i, k - 1, k - i, outcome))
            i = k
    return out, filtered, rows


def table_rows(runs) -> list[tuple[int, int, int, int, int]]:
    return list(
        zip(
            runs.joint.tolist(),
            runs.start.tolist(),
            runs.end.tolist(),
            runs.n.tolist(),
            runs.outcome.tolist(),
            strict=True,
        )
    )


# --- the parameters and the constants ---------------------------------------------------------------------------------
def test_t_qlt_08_the_defaults_are_the_values_of_w6_and_the_outcomes_are_named():
    p = ButterworthParams()
    assert (p.cutoff_hz, p.order, p.padlen) == (6.0, 4, None)
    assert RUN_OUTCOME_NAMES == ("filtered", "too_short", "above_nyquist")
    assert (RUN_FILTERED, RUN_TOO_SHORT, RUN_ABOVE_NYQUIST) == (0, 1, 2)
    assert ButterworthParams(order=np.int64(2), padlen=np.int32(5)).padlen == 5


# --- T-QLT-08a: each run is filtered on its own -----------------------------------------------------------------------
def test_t_qlt_08a_each_run_is_what_sosfiltfilt_gives_for_that_run_alone_bit_for_bit():
    kp = wave(200, noise=1.0, seed=2)
    kp0, reason, interp = plain(kp.copy())
    hole(kp0, reason, 3, np.arange(80, 90))
    r = lowpass_layer(kp0, reason, interp, STEP)
    sos = sg.butter(4, 6.0, btype="low", fs=FPS, output="sos")
    for a, b in ((0, 80), (90, 200)):
        assert np.array_equal(r.keypoints[a:b, 3], sg.sosfiltfilt(sos, kp0[a:b, 3], axis=0))
        assert np.isfinite(r.keypoints[a:b, 3]).all()  # no NaN comes out of a run
    assert np.isnan(r.keypoints[80:90, 3]).all() and (r.reason[80:90, 3] == LOW_CONF).all()
    assert not r.filtered[80:90, 3].any()
    other = [j for j in range(NUM_JOINTS) if j != 3]
    assert np.array_equal(r.keypoints[:, other], sg.sosfiltfilt(sos, kp0[:, other], axis=0))  # one long run each


def test_t_qlt_08a_a_step_at_the_end_of_one_run_does_not_reach_the_next():
    kp = np.zeros((120, NUM_JOINTS, 2))
    kp[:50, 4] = 100.0  # a run at 100 px, then a hole, then a run at 0 px
    kp[50:60, 4] = np.nan
    reason = np.zeros((120, NUM_JOINTS), np.uint8)
    reason[50:60, 4] = LOW_CONF
    r = lowpass_layer(kp, reason, np.zeros(reason.shape, bool), STEP)
    assert np.allclose(r.keypoints[:50, 4], 100.0, atol=1e-9) and np.allclose(r.keypoints[60:, 4], 0.0, atol=1e-9)
    assert (r.keypoints[:50, 4] != 0.0).all()  # not a run of zeros: the other run's value did not leak in


def test_t_qlt_08a_the_x_and_y_of_a_cell_are_one_run():
    kp, reason, interp = plain(wave(60, noise=1.0, seed=1))
    hole(kp, reason, 2, [30])
    r = lowpass_layer(kp, reason, interp, STEP)
    assert (
        np.isnan(r.keypoints[30, 2]).all()
        and np.isfinite(r.keypoints[29, 2]).all()
        and np.isfinite(r.keypoints[31, 2]).all()
    )
    assert (
        (r.runs.joint == 2).sum() == 2
        and not np.isnan(r.keypoints[:30, 2]).any()
        and not np.isnan(r.keypoints[31:, 2]).any()
    )


# --- T-QLT-08b: the response ------------------------------------------------------------------------------------------
def test_t_qlt_08b_a_constant_stays_constant_and_a_straight_line_stays_straight():
    t = np.arange(90) / FPS
    flat = np.full((90, NUM_JOINTS, 2), 321.5)
    r = lowpass_layer(*plain(flat), STEP)
    assert np.allclose(r.keypoints, 321.5, rtol=0.0, atol=1e-9)
    line = np.empty((90, NUM_JOINTS, 2))
    line[..., 0] = (100.0 + 40.0 * t)[:, None]
    line[..., 1] = (200.0 - 25.0 * t)[:, None]
    r = lowpass_layer(*plain(line), STEP)
    assert np.allclose(
        r.keypoints[20:70], line[20:70], rtol=0.0, atol=1e-5
    )  # inside: the tail of the start-up, 3e-7 px
    assert np.abs(r.keypoints - line).max() < 0.01  # at the ends too


@pytest.mark.parametrize("fps", [24.0, 30.0, 60.0])
@pytest.mark.parametrize("hz", [1.0, 3.0, 6.0, 9.0])
def test_t_qlt_08b_a_sine_comes_out_scaled_by_the_squared_magnitude_and_with_no_delay(fps: float, hz: float):
    n = 400
    t = np.arange(n) / fps
    kp = np.zeros((n, NUM_JOINTS, 2))
    kp[..., 0] = (100.0 * np.sin(2.0 * np.pi * hz * t + 0.3))[:, None]
    r = lowpass_layer(*plain(kp), 1.0 / fps)
    sos = sg.butter(4, 6.0, btype="low", fs=fps, output="sos")
    _, h = sg.sosfreqz(sos, worN=[hz], fs=fps)
    gain = float(abs(h[0]) ** 2)  # forward and backward: the magnitude is squared and the phase cancels
    inside = slice(100, 300)
    assert np.allclose(r.keypoints[inside, 0, 0], gain * kp[inside, 0, 0], rtol=0.0, atol=1e-3)
    if hz == 6.0:
        assert gain == pytest.approx(0.5, abs=1e-9)  # the gain at the design frequency is 0.5


@pytest.mark.parametrize(("fps", "ratio"), [(24.0, 0.677), (30.0, 0.601), (60.0, 0.422)])
def test_t_qlt_08b_white_noise_falls_to_the_measured_share_of_its_standard_deviation(fps: float, ratio: float):
    rng = np.random.default_rng(1)
    kp = np.zeros((20000, NUM_JOINTS, 2))
    kp[:, 0] = rng.normal(0.0, 1.0, (20000, 2))
    r = lowpass_layer(*plain(kp), 1.0 / fps)
    assert float(r.keypoints[:, 0].std()) == pytest.approx(ratio, abs=0.02)


# --- T-QLT-08c: invariants --------------------------------------------------------------------------------------------
def noisy_layer_with_holes():
    kp, reason, interp = plain(wave(160, noise=1.0, seed=3))
    hole(kp, reason, 5, np.arange(40, 46))
    hole(kp, reason, 9, [100])
    return kp, reason, interp


def test_t_qlt_08c_joints_are_independent_and_the_layer_commutes_with_a_shift_and_a_scale():
    kp, reason, interp = noisy_layer_with_holes()
    base = lowpass_layer(kp, reason, interp, STEP)
    perm = np.random.default_rng(7).permutation(NUM_JOINTS)
    moved = lowpass_layer(kp[:, perm], reason[:, perm], interp[:, perm], STEP)
    assert np.array_equal(moved.keypoints, base.keypoints[:, perm], equal_nan=True)
    assert np.array_equal(moved.filtered, base.filtered[:, perm])
    shifted = lowpass_layer(kp + 1000.0, reason, interp, STEP)
    assert np.allclose(shifted.keypoints, base.keypoints + 1000.0, rtol=0.0, atol=1e-8, equal_nan=True)
    scaled = lowpass_layer(kp * 3.0, reason, interp, STEP)
    assert np.allclose(scaled.keypoints, base.keypoints * 3.0, rtol=1e-9, atol=1e-8, equal_nan=True)


@pytest.mark.parametrize("k", [0.5, 2.0])
def test_t_qlt_08c_a_clock_scaled_by_k_with_the_cutoff_scaled_by_one_over_k_gives_the_same_layer(k: float):
    kp, reason, interp = noisy_layer_with_holes()
    base = lowpass_layer(kp, reason, interp, STEP)
    other = lowpass_layer(kp, reason, interp, STEP * k, ButterworthParams(cutoff_hz=6.0 / k))
    assert np.allclose(other.keypoints, base.keypoints, rtol=0.0, atol=1e-9, equal_nan=True)
    assert other.sampling_hz == pytest.approx(base.sampling_hz / k)


def test_t_qlt_08c_the_cutoff_and_the_order_are_the_ones_of_scipy():
    kp, reason, interp = noisy_layer_with_holes()
    for params in (
        ButterworthParams(cutoff_hz=4.0),
        ButterworthParams(cutoff_hz=8.0),
        ButterworthParams(order=2),
        ButterworthParams(order=6),
    ):
        want, filtered, _ = oracle(kp, STEP, params)
        got = lowpass_layer(kp, reason, interp, STEP, params)
        assert np.array_equal(got.keypoints, want, equal_nan=True) and np.array_equal(got.filtered, filtered)
        assert got.params == params
    assert not np.array_equal(
        lowpass_layer(kp, reason, interp, STEP, ButterworthParams(cutoff_hz=4.0)).keypoints,
        lowpass_layer(kp, reason, interp, STEP, ButterworthParams(cutoff_hz=8.0)).keypoints,
        equal_nan=True,
    )


# --- T-QLT-08d: the flags ---------------------------------------------------------------------------------------------
def test_t_qlt_08d_reasons_and_flags_are_copied_and_a_bridged_cell_stays_bridged():
    kp, reason, interp = plain(wave(120, noise=1.0, seed=5))
    bridge(reason, interp, 7, [50, 51], OUTLIER)
    hole(kp, reason, 8, np.arange(60, 70), NOT_TRACKED)
    r = lowpass_layer(kp, reason, interp, STEP)
    assert np.array_equal(r.reason, reason) and np.array_equal(r.interpolated, interp)
    assert r.filtered[50, 7] and r.interpolated[50, 7] and r.reason[50, 7] == OUTLIER  # filtered, still a bridged value
    assert (r.reason[60:70, 8] == NOT_TRACKED).all() and np.isnan(r.keypoints[60:70, 8]).all()
    usable = np.isfinite(kp[..., 0])
    assert np.array_equal(r.filtered, usable)  # every run here is long enough
    check_gap_layer(r.keypoints, r.reason, r.interpolated, np.arange(120) * STEP)  # the contract of the gap layer


# --- T-QLT-08e: the result --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_t_qlt_08e_inputs_are_not_changed_outputs_are_new_and_read_only_and_dtypes_are_kept(dtype):
    kp, reason, interp = plain(wave(100, noise=1.0, seed=6, dtype=dtype))
    hole(kp, reason, 3, [40, 41])
    before = (kp.copy(), reason.copy(), interp.copy())
    r = lowpass_layer(kp, reason, interp, STEP)
    for given, kept in zip((kp, reason, interp), before, strict=True):
        assert np.array_equal(given, kept, equal_nan=True)
    assert r.keypoints.dtype == dtype and r.reason.dtype == np.uint8 and r.interpolated.dtype == bool
    assert r.filtered.dtype == bool
    for arr in (
        r.keypoints,
        r.reason,
        r.interpolated,
        r.filtered,
        r.runs.joint,
        r.runs.start,
        r.runs.end,
        r.runs.n,
        r.runs.outcome,
    ):
        assert not arr.flags.writeable and not any(np.shares_memory(arr, x) for x in (kp, reason, interp))
    with pytest.raises(ValueError, match="read-only"):
        r.keypoints[0, 0, 0] = 1.0
    assert r.runs.joint.dtype == np.int16 and r.runs.start.dtype == np.int32 and r.runs.end.dtype == np.int32
    assert r.runs.n.dtype == np.int32 and r.runs.outcome.dtype == np.uint8


def test_t_qlt_08e_a_float32_layer_is_filtered_in_double_precision():
    kp, reason, interp = plain(wave(150, noise=1.0, seed=7, dtype=np.float32))
    r = lowpass_layer(kp, reason, interp, STEP)
    want = sg.sosfiltfilt(sg.butter(4, 6.0, btype="low", fs=FPS, output="sos"), kp.astype(np.float64), axis=0)
    assert np.array_equal(r.keypoints, want.astype(np.float32))


def test_t_qlt_08e_a_run_of_a_hundred_thousand_rows_is_what_scipy_gives():
    n = 100_000
    kp = np.zeros((n, NUM_JOINTS, 2), np.float32)
    kp[:, 0] = np.random.default_rng(1).normal(300.0, 20.0, (n, 2))
    kp[:, 1:] = 100.0
    r = lowpass_layer(*plain(kp), STEP)
    want = sg.sosfiltfilt(sg.butter(4, 6.0, btype="low", fs=FPS, output="sos"), kp[:, 0].astype(np.float64), axis=0)
    assert r.filtered.all() and len(r.runs) == NUM_JOINTS and (r.runs.n == n).all()
    assert np.array_equal(r.keypoints[:, 0], want.astype(np.float32))


def test_t_qlt_08e_thousands_of_runs_agree_with_the_loop():
    n = 4000
    kp, reason, interp = plain(wave(n, noise=1.0, seed=8))
    for joint in range(NUM_JOINTS):
        hole(kp, reason, joint, np.arange(joint, n, 20))  # a hole every 20 rows: runs of 19, shifted per joint
    r = lowpass_layer(kp, reason, interp, STEP)
    want, filtered, rows = oracle(kp, STEP, DEFAULT)
    assert len(r.runs) == len(rows) > 5000
    assert np.array_equal(r.keypoints, want, equal_nan=True) and np.array_equal(r.filtered, filtered)
    assert table_rows(r.runs) == rows


# --- T-QLT-08f: the grid ----------------------------------------------------------------------------------------------
def test_t_qlt_08f_lowpass_grid_takes_the_step_from_the_map_for_the_identity_and_for_a_regular_grid():
    t = np.arange(120) / FPS
    kp, reason, interp = plain(wave(120, noise=1.0, seed=9))
    hole(kp, reason, 3, [60])
    ident = resample_layer(kp, reason, interp, t)
    r = lowpass_grid(ident)
    direct = lowpass_layer(ident.keypoints, ident.reason, ident.interpolated, ident.gridmap.step_s)
    assert ident.gridmap.identity and r.sampling_hz == pytest.approx(FPS, rel=1e-9)
    assert np.array_equal(r.keypoints, direct.keypoints, equal_nan=True) and table_rows(r.runs) == table_rows(
        direct.runs
    )
    dropped = np.delete(t, 50)  # a dropped frame: a regular grid with one mixed row
    kp2, reason2, interp2 = plain(wave(len(dropped), noise=1.0, seed=9))
    grid = resample_layer(kp2, reason2, interp2, dropped)
    g = lowpass_grid(grid)
    assert not grid.gridmap.identity and grid.mixed.sum() == 1
    assert g.sampling_hz == pytest.approx(FPS, rel=1e-9) and g.keypoints.shape == grid.keypoints.shape
    assert g.filtered.all() and np.array_equal(g.reason, grid.reason)  # the mixed row is data like any other
    assert np.array_equal(g.interpolated, grid.interpolated)


def test_t_qlt_08f_lowpass_grid_uses_the_step_of_its_own_map_and_the_parameters_it_is_given():
    fps = 24.0
    t = np.arange(150) / fps
    kp, reason, interp = plain(wave(150, fps=fps, noise=1.0, seed=3))
    grid = resample_layer(kp, reason, interp, t)
    params = ButterworthParams(cutoff_hz=4.0, order=2)
    r = lowpass_grid(grid, params)
    want, filtered, rows = oracle(kp, 1.0 / fps, params)
    assert r.sampling_hz == pytest.approx(fps, rel=1e-9) and r.params == params
    assert np.allclose(r.keypoints, want, rtol=0.0, atol=1e-9) and np.array_equal(r.filtered, filtered)
    assert table_rows(r.runs) == rows
    assert not np.array_equal(r.keypoints, lowpass_grid(grid).keypoints)  # the parameters were used


# --- T-QLT-09a: a run that is too short -------------------------------------------------------------------------------
def test_t_qlt_09a_a_run_of_at_most_padlen_rows_is_not_filtered_and_says_so():
    lengths = [1, 5, 14, 15, 16, 17, 40]
    kp, reason, interp, starts = column_of_runs(lengths)
    r = lowpass_layer(kp, reason, interp, STEP)
    j = 3
    got = [
        (int(a), int(b), int(o))
        for jj, a, b, o in zip(r.runs.joint, r.runs.start, r.runs.n, r.runs.outcome, strict=True)
        if jj == j
    ]
    assert got == [
        (s, length, RUN_TOO_SHORT if length <= 15 else RUN_FILTERED) for s, length in zip(starts, lengths, strict=True)
    ]
    for s, length in zip(starts, lengths, strict=True):
        rows = slice(s, s + length)
        if length <= 15:
            assert np.array_equal(r.keypoints[rows, j], kp[rows, j]) and not r.filtered[rows, j].any()  # bit for bit
        else:
            assert r.filtered[rows, j].all() and not np.array_equal(r.keypoints[rows, j], kp[rows, j])
    assert np.array_equal(r.reason, reason)  # nothing was set to NaN or given another reason


def test_t_qlt_09a_a_layer_in_which_every_run_is_short_comes_back_as_it_was():
    n = 90
    kp, reason, interp = plain(wave(n, noise=1.0, seed=3))
    for joint in range(NUM_JOINTS):
        hole(kp, reason, joint, np.arange(10, n, 11))  # runs of 10 rows
    r = lowpass_layer(kp, reason, interp, STEP)
    assert not r.filtered.any() and np.array_equal(r.keypoints, kp, equal_nan=True)
    assert set(r.runs.outcome.tolist()) == {RUN_TOO_SHORT} and (r.runs.n <= 10).all()


# --- T-QLT-09b: padlen ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("order", range(1, 11))
def test_t_qlt_09b_the_default_padlen_is_the_one_of_scipy_for_the_design(order: int):
    """A run is filtered exactly when scipy accepts it (it refuses a run that is not longer than its default padlen)."""
    lengths = list(range(1, 41))
    kp, reason, interp, starts = column_of_runs(lengths, gap=1)
    params = ButterworthParams(order=order)
    r = lowpass_layer(kp, reason, interp, STEP, params)
    sos = sg.butter(order, 6.0, btype="low", fs=FPS, output="sos")
    for jj, a, n, o in zip(r.runs.joint, r.runs.start, r.runs.n, r.runs.outcome, strict=True):
        if jj != 3:
            continue
        try:
            sg.sosfiltfilt(sos, np.zeros((int(n), 2)), axis=0)
            accepted = True
        except ValueError:
            accepted = False
        assert (int(o) == RUN_FILTERED) is accepted, (order, int(a), int(n))


def test_t_qlt_09b_padlen_is_a_parameter():
    kp, reason, interp, starts = column_of_runs([5, 6, 20, 21, 30])
    for padlen in (0, 5, 20):
        params = ButterworthParams(padlen=padlen)
        r = lowpass_layer(kp, reason, interp, STEP, params)
        want, filtered, rows = oracle(kp, STEP, params)
        assert np.array_equal(r.keypoints, want, equal_nan=True) and np.array_equal(r.filtered, filtered)
        assert table_rows(r.runs) == rows
    runs = lowpass_layer(kp, reason, interp, STEP, ButterworthParams(padlen=20)).runs
    outcome = {int(n): int(o) for jj, n, o in zip(runs.joint, runs.n, runs.outcome, strict=True) if jj == 3}
    assert outcome[20] == RUN_TOO_SHORT and outcome[21] == RUN_FILTERED  # more than padlen, not at least padlen


# --- T-QLT-09c: the cutoff at or above Nyquist ------------------------------------------------------------------------
@pytest.mark.parametrize("fps", [5.0, 10.0, 12.0])
def test_t_qlt_09c_a_clip_whose_nyquist_is_not_above_the_cutoff_is_not_filtered(fps: float):
    kp, reason, interp = plain(wave(100, fps=fps, noise=1.0, seed=2))
    hole(kp, reason, 3, [40])
    r = lowpass_layer(kp, reason, interp, 1.0 / fps)
    assert not r.filtered.any() and np.array_equal(
        r.keypoints, kp, equal_nan=True
    )  # no clamping: the values are the input's
    assert set(r.runs.outcome.tolist()) == {RUN_ABOVE_NYQUIST} and len(r.runs) == NUM_JOINTS + 1
    assert r.sampling_hz == pytest.approx(fps)


def test_t_qlt_09c_just_above_the_boundary_it_filters_and_another_cutoff_moves_the_boundary():
    kp, reason, interp = plain(wave(100, fps=12.0001, noise=1.0, seed=2))
    assert lowpass_layer(kp, reason, interp, 1.0 / 12.0001).filtered.all()
    kp, reason, interp = plain(wave(100, fps=12.0, noise=1.0, seed=2))
    assert lowpass_layer(kp, reason, interp, 1.0 / 12.0, ButterworthParams(cutoff_hz=5.9)).filtered.all()
    assert not lowpass_layer(kp, reason, interp, 1.0 / 12.0, ButterworthParams(cutoff_hz=6.0)).filtered.any()


def test_t_qlt_09c_above_nyquist_takes_precedence_over_too_short():
    kp, reason, interp, starts = column_of_runs([4, 30], gap=1)
    r = lowpass_layer(kp, reason, interp, 1.0 / 10.0)
    assert set(r.runs.outcome.tolist()) == {RUN_ABOVE_NYQUIST}


# --- T-QLT-09d: the step ----------------------------------------------------------------------------------------------
def test_t_qlt_09d_a_nan_step_is_for_fewer_than_two_rows_only():
    for n in (0, 1):
        kp, reason, interp = plain(wave(n))
        r = lowpass_layer(kp, reason, interp, float("nan"))
        assert not r.filtered.any() and r.keypoints.shape == (n, NUM_JOINTS, 2) and np.isnan(r.sampling_hz)
        assert len(r.runs) == n * NUM_JOINTS and set(r.runs.outcome.tolist()) <= {RUN_TOO_SHORT}
    with pytest.raises(QualityError, match="step_s"):
        lowpass_layer(*plain(wave(20)), float("nan"))


@pytest.mark.parametrize("bad", [0.0, -0.033, float("inf"), True, "0.033", None])
def test_t_qlt_09d_a_wrong_step_is_refused(bad):
    with pytest.raises(QualityError, match="step_s"):
        lowpass_layer(*plain(wave(20)), bad)  # type: ignore[arg-type]


# --- T-QLT-09e: the table of runs -------------------------------------------------------------------------------------
def test_t_qlt_09e_the_table_lists_every_run_by_joint_and_then_by_first_row():
    kp, reason, interp = plain(wave(80, noise=1.0, seed=2))
    hole(kp, reason, 2, np.arange(0, 3))  # a run that starts after the first row
    hole(kp, reason, 2, np.arange(30, 33))
    hole(kp, reason, 2, np.arange(79, 80))  # a run that ends before the last row
    hole(kp, reason, 11, np.arange(0, 80))  # a joint without a run
    bridge(reason, interp, 5, [40])
    r = lowpass_layer(kp, reason, interp, STEP)
    _, _, rows = oracle(kp, STEP, DEFAULT)
    assert table_rows(r.runs) == rows and len(r.runs) == NUM_JOINTS  # 25 joints with a run, one of them with two
    assert (np.diff(r.runs.joint.astype(int)) >= 0).all()
    assert [row[1:4] for row in rows if row[0] == 2] == [(3, 29, 27), (33, 78, 46)]
    assert (r.runs.end - r.runs.start + 1 == r.runs.n).all()
    assert 11 not in r.runs.joint.tolist()
    assert len(r.runs) == len(r.runs.joint) == len(r.runs.outcome)


def test_t_qlt_09e_no_run_at_all_is_an_empty_table():
    kp = np.full((30, NUM_JOINTS, 2), np.nan)
    reason = np.full((30, NUM_JOINTS), LOW_CONF, np.uint8)
    r = lowpass_layer(kp, reason, np.zeros(reason.shape, bool), STEP)
    assert len(r.runs) == 0 and not r.filtered.any() and np.isnan(r.keypoints).all()


# --- T-QLT-09f: bad input is refused naming the argument --------------------------------------------------------------
def good():
    return plain(wave(40, noise=1.0, seed=2))


def with_half_nan_cell():
    kp, reason, interp = good()
    kp[3, 4, 0] = np.nan
    reason[3, 4] = LOW_CONF
    return kp, reason, interp


def with_infinite_cell():
    kp, reason, interp = good()
    kp[3, 4] = np.inf
    return kp, reason, interp


def with_value_not_ok_and_not_flagged():
    kp, reason, interp = good()
    reason[3, 4] = LOW_CONF
    return kp, reason, interp


def with_nan_and_ok():
    kp, reason, interp = good()
    kp[3, 4] = np.nan
    return kp, reason, interp


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: (good()[0].astype(np.int32), *good()[1:]), "keypoints"),
        (lambda: (good()[0][:, :, 0], *good()[1:]), "keypoints"),
        (lambda: (good()[0], good()[1].astype(np.int64), good()[2]), "reason"),
        (lambda: (good()[0], good()[1][:-1], good()[2]), "reason"),
        (lambda: (good()[0], good()[1], good()[2].astype(np.uint8)), "interpolated"),
        (lambda: (good()[0], good()[1], good()[2][:-1]), "interpolated"),
        (with_half_nan_cell, "one NaN coordinate"),
        (with_infinite_cell, "infinite"),
        (with_value_not_ok_and_not_flagged, "not flagged"),
        (with_nan_and_ok, "where reason is ok"),
    ],
)
def test_t_qlt_09f_bad_arrays_are_refused_naming_the_argument(make, message: str):
    kp, reason, interp = make()
    with pytest.raises(QualityError, match=message):
        lowpass_layer(kp, reason, interp, STEP)


@pytest.mark.parametrize("bad", [0.0, -6.0, float("nan"), float("inf"), True, "6", None])
def test_t_qlt_09f_a_wrong_cutoff_is_refused(bad):
    with pytest.raises(QualityError, match="cutoff_hz"):
        ButterworthParams(cutoff_hz=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, -1, 11, 2.5, True, "4", None])
def test_t_qlt_09f_a_wrong_order_is_refused(bad):
    with pytest.raises(QualityError, match="order"):
        ButterworthParams(order=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-1, True, 2.5, "15"])
def test_t_qlt_09f_a_wrong_padlen_is_refused(bad):
    with pytest.raises(QualityError, match="padlen"):
        ButterworthParams(padlen=bad)  # type: ignore[arg-type]


def test_t_qlt_09f_the_extremes_that_are_allowed_are_allowed():
    assert ButterworthParams(order=1).order == 1 and ButterworthParams(order=10).order == 10
    assert ButterworthParams(padlen=0).padlen == 0 and ButterworthParams(cutoff_hz=np.float32(4.0)).cutoff_hz == 4.0


# --- the differential test: the rules written the slow way, with scipy as the filter ----------------------------------
def random_case(seed: int):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(0, 120))
    fps = float(rng.uniform(12.5, 60.0))
    kp = wave(n, fps=fps, noise=float(rng.uniform(0.0, 3.0)), seed=seed)
    reason = np.zeros((n, NUM_JOINTS), np.uint8)
    interp = np.zeros((n, NUM_JOINTS), bool)
    holes = rng.random((n, NUM_JOINTS)) < float(rng.choice([0.05, 0.15, 0.3]))
    reason[holes] = rng.choice([LOW_CONF, NOT_TRACKED, OUTLIER], size=int(holes.sum()))
    kp[holes] = np.nan
    bridged = ~holes & (rng.random((n, NUM_JOINTS)) < 0.05)
    reason[bridged] = LOW_CONF
    interp[bridged] = True
    params = ButterworthParams(
        cutoff_hz=float(rng.choice([3.0, 4.0, 6.0, 8.0])),
        order=int(rng.integers(1, 7)),
        padlen=rng.choice([None, None, 0, 5, 20]),
    )
    return kp.astype(np.float32 if seed % 2 else np.float64), reason, interp, fps, params


@pytest.mark.parametrize("seed", range(200))
def test_t_qlt_08_diff_the_module_equals_the_slow_rules(seed: int):
    kp, reason, interp, fps, params = random_case(seed)
    step = 1.0 / fps
    r = lowpass_layer(kp, reason, interp, step, params)
    want, filtered, rows = oracle(kp, step, params)
    assert np.array_equal(r.keypoints, want, equal_nan=True) and np.array_equal(r.filtered, filtered)
    assert table_rows(r.runs) == rows and r.params == params
    assert np.array_equal(r.reason, reason) and np.array_equal(r.interpolated, interp)
    assert r.sampling_hz == pytest.approx(fps)
    usable = np.isfinite(kp[..., 0])
    assert (r.filtered <= usable).all() and np.array_equal(np.isnan(r.keypoints[..., 0]), ~usable)  # no hole filled
    untouched = usable & ~r.filtered
    assert np.array_equal(r.keypoints[untouched], kp[untouched])  # a run that was not filtered keeps its values
    if len(kp):
        check_gap_layer(r.keypoints, r.reason, r.interpolated, np.arange(len(kp)) * step)
