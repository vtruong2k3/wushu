"""T-CMP-06 and the deviation curve on the generator: ``local_tempo`` and ``deviation_curve`` on SYN-10, SYN-11 (P6.04).

Every layer is what the pipeline would hand to the comparison (``run_quality_arrays``, ``pose_filtered_from_result``,
``frame_features``), then ``align`` (rows the query, columns the reference) and the two curves. **Test settings, not
defaults of the product**: ``min_visible`` 11 of 21 units, ``band`` 0.2, ``symmetricP1``, weights 1 (the settings of
P6.03b), ``smooth_s`` 0.5 s (the suggestion of Appendix C); SYN-10 is generated with ``scale_px`` 120 as in P6.03b.

The truth of SYN-10 is the warp ``t_query = W(t_ref)`` with ``d t_query / d t_ref = k(t_ref) = k0 + (k1 - k0) t_ref /
duration`` (the closed form of the generator; its own arrays agree with it, checked below).

Numbers measured on 2026-11-18 before any bound was set (the task file, section 5, has them all). The noise-free
generator is deterministic: seeds 1, 2 and 3 give the same numbers.

* **T-CMP-06, SYN-10, warp 0.8 to 1.25, noise 0, ``smooth_s`` 0.5 s** (123 query rows, 120 reference rows, 120 of 120
  ratios are values, windows of 8 to 15 rows): the median of ``|rho / k - 1|`` is **0.0134** (the plan's bound is 0.10),
  the mean 0.0157, the 90th percentile 0.0325, the largest 0.0526, and no row is above 10 percent. The ratio runs from
  0.776 to 1.234 (the truth: 0.8 to 1.25). The window matters: at 0.25 s the median is 0.0417, the 90th percentile
  0.1101, the largest 0.1887 and 15.8 percent of the rows are above 10 percent; at 1.0 s the median is 0.0061 and the
  largest 0.0331. The matched time ``tau`` is within 0.0173 s of the truth (median 0.0074 s, a step of the clock is
  0.0333 s: the numbers of P6.03b). ``whole_ratio`` is 1.0252 (the mean warp is 1.025).
* **Other warps** (noise 0, 0.5 s): a constant warp of 1.0 gives the ratio 1.0 exactly and of 1.5 gives 1.5 to 1.1e-15
  (the path is the true one); 0.6 to 1.6: median 0.0087, largest 0.0662; 1.25 to 0.8 (the query speeds up): median
  0.0122, largest 0.0664.
* **At 1 px of noise** (seeds 1, 2, 3; the plan sets no tolerance, so only the direction is asserted): the median error
  is 0.0876, 0.1459, 0.1291 at 0.25 s, 0.0397, 0.0588, 0.0534 at 0.5 s and 0.0393, 0.0370, 0.0307 at 1.0 s; the
  largest at 0.5 s for seed 1 is 0.311. Noise moves the path by whole frames, and a short window shows it.
* **Deviation, SYN-10, noise 0:** no NaN (2520 of 2520 are values); the units that do not move (shoulders, hips, thighs,
  shanks, trunk) deviate by 0.0 exactly; the largest deviation of a wrist is 0.0177 trunk lengths, of a forearm angle
  0.051 (chord); ``total`` is at most 0.0060, and the mean of ``total`` weighted by ``cells`` is **D** (0.0017557, to
  1e-16: ``D`` is the mean of the cost over all path cells).
* **Deviation, SYN-11:** against another action (open_close for raise_lower) the mean deviation is 0.773 trunk lengths
  for a wrist, 0.386 for an elbow, 0.291 (chord) for a forearm angle, 0.025 and 0.051 for a knee and an ankle, and at
  most 1.5e-7 for the units that do not move; the mean ``total`` is 0.1529 against 0.0159 for a variant of the same
  action (a ratio of 9.6).
* **R1 of P6.01 on the curves** (SYN-10 at 1 px, ``min_segment_length`` 0.05, seeds 1 to 3): 74, 76 and 70 of 2520
  deviations are NaN with the reason ``not_valid_in_both``, all of them in the two forearm angles (35 to 39 rows
  each), and each one is a unit that no cell of its row has valid in both frames.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.synth import TOLERANCES, SynthPair, SynthSequence, make_pair
from taiji_ai.compare.align import Alignment, align
from taiji_ai.compare.features import FrameFeatures, frame_features
from taiji_ai.compare.tempo_ratio import DeviationReason, TempoReason, deviation_curve, local_tempo

SCALE_PX = 120.0
MIN_VISIBLE = 11  # of 21 units: half, rounded up (as in P6.03b)
BAND = 0.2
SMOOTH_S = 0.5  # the suggestion of Appendix C, a TEST value here (the product passes it, it has no default)
SHORT_SEGMENT = 0.05  # a TEST value for R1 of P6.01
PLAN_TOLERANCE = TOLERANCES["SYN-10"]["median_rate_k_relative_error"]  # 0.10
CLOSER = TOLERANCES["SYN-11"]["variant_closer_ratio"]  # 2.0
STILL_UNITS = ("LShoulder", "RShoulder", "LHip", "RHip", "l_thigh", "l_shank", "r_thigh", "r_shank", "trunk")
ARM_UNITS = ("LElbow", "RElbow", "LWrist", "RWrist", "l_upper_arm", "l_forearm", "r_upper_arm", "r_forearm")


def features_of(seq: SynthSequence, min_segment_length: float | None = None) -> FrameFeatures:
    return frame_features(layer_of_sequence(seq), min_segment_length=min_segment_length)


@functools.cache
def syn10(
    seed: int = 1,
    noise_px: float = 0.0,
    min_segment_length: float | None = None,
    k_start: float = 0.8,
    k_end: float = 1.25,
    query_scale: float = 1.0,
    shift: tuple[float, float] = (0.0, 0.0),
) -> tuple[SynthPair, FrameFeatures, FrameFeatures, Alignment]:
    """``(pair, reference features, query features, alignment)`` of SYN-10 through the real chain."""
    pair = make_pair(
        "SYN-10",
        seed=seed,
        scale_px=SCALE_PX,
        noise_px=noise_px,
        k_start=k_start,
        k_end=k_end,
        query_scale=query_scale,
        query_shift_px=shift,
    )
    reference, query = features_of(pair.ref, min_segment_length), features_of(pair.query, min_segment_length)
    return pair, reference, query, align(reference, query, min_visible=MIN_VISIBLE, band=BAND)


def true_ratio(pair: SynthPair, t_ref: np.ndarray) -> np.ndarray:
    """The truth of SYN-10: ``d t_query / d t_ref = k0 + (k1 - k0) t_ref / duration``."""
    k0, k1, duration = pair.truth["k_start"], pair.truth["k_end"], pair.params["duration"]
    return k0 + (k1 - k0) * t_ref / duration


def true_query_time(pair: SynthPair, t_ref: np.ndarray) -> np.ndarray:
    """The query time of the reference time ``t``: ``W(t) = k0 t + (k1 - k0) t^2 / (2 duration)``."""
    k0, k1, duration = pair.truth["k_start"], pair.truth["k_end"], pair.params["duration"]
    return k0 * t_ref + (k1 - k0) * t_ref**2 / (2.0 * duration)


def relative_error(pair: SynthPair, reference: FrameFeatures, a: Alignment, smooth_s: float) -> np.ndarray:
    """``|rho / k - 1|`` on every reference row (NaN where no ratio could be made)."""
    return np.abs(local_tempo(a, smooth_s=smooth_s).ratio / true_ratio(pair, reference.t_sec) - 1.0)


# --- T-CMP-06 ---------------------------------------------------------------------------------------------------------
def test_t_cmp_06_syn10_the_local_ratio_follows_the_generators_k_of_t_within_the_plans_tolerance():
    pair, reference, query, a = syn10()
    got = local_tempo(a, smooth_s=SMOOTH_S)
    assert (len(query.t_sec), len(reference.t_sec)) == (123, 120) and got.status == "ok" and got.smooth_s == SMOOTH_S
    assert (got.reason == TempoReason.valid).all() and np.isfinite(got.ratio).all()  # 120 of 120 are values
    assert got.window_rows.min() == 8 and got.window_rows.max() == 15  # 0.5 s on a 30 fps grid: 7 rows each side
    error = np.abs(got.ratio / true_ratio(pair, reference.t_sec) - 1.0)
    assert np.median(error) <= PLAN_TOLERANCE  # the plan, T-CMP-06: 10 percent
    assert np.median(error) < 0.02  # measured 0.0134
    assert error.max() < 0.08 and (error > PLAN_TOLERANCE).sum() == 0  # measured 0.0526: no row is above 10 percent
    assert 0.7 < got.ratio.min() < 0.85 and 1.15 < got.ratio.max() < 1.3  # measured 0.776 to 1.234: truth 0.8 to 1.25
    assert got.ratio[:10].mean() < got.ratio[-10:].mean()  # the query slows down from fast to slow: tempo rises
    assert np.all(got.reason == TempoReason.valid) and got.whole_reason == TempoReason.valid


def test_t_cmp_06_syn10_the_closed_form_of_the_truth_is_the_generators_own():
    pair, reference, query, _ = syn10()
    t_ref_of_query, rate_k = np.asarray(pair.truth["t_ref_of_query"]), np.asarray(pair.truth["rate_k"])
    from_arrays = np.interp(reference.t_sec, t_ref_of_query, rate_k)  # the generator's k at every reference time
    assert np.abs(from_arrays - true_ratio(pair, reference.t_sec)).max() < 1e-3
    assert (
        np.abs(np.interp(reference.t_sec, t_ref_of_query, query.t_sec) - true_query_time(pair, reference.t_sec)).max()
        < 1e-3
    )


def test_t_cmp_06_syn10_the_matched_time_is_the_generators_warp_in_seconds():
    pair, reference, query, a = syn10()
    got = local_tempo(a, smooth_s=SMOOTH_S)
    step = float(query.t_sec[1] - query.t_sec[0])
    error = np.abs(got.t_query - true_query_time(pair, reference.t_sec))
    assert np.array_equal(got.t_ref, reference.t_sec) and np.array_equal(got.t_query, a.matched_query_times())
    assert error.max() < step and np.median(error) < step / 2  # measured 0.0173 s and 0.0074 s (a step is 0.0333 s)
    assert np.all(np.diff(got.t_query) >= 0.0)  # a monotone path: the matched time never goes back


def test_t_cmp_06_syn10_the_whole_segment_ratio_is_the_mean_warp_read_from_the_two_clocks():
    pair, reference, query, a = syn10()
    got = local_tempo(a, smooth_s=SMOOTH_S)
    clocks = (query.t_sec[-1] - query.t_sec[0]) / (reference.t_sec[-1] - reference.t_sec[0])
    assert got.whole_ratio == clocks and got.whole_reason == TempoReason.valid
    assert abs(got.whole_ratio - (pair.truth["k_start"] + pair.truth["k_end"]) / 2.0) < 0.001  # 1.0252 against 1.025


def test_t_cmp_06_syn10_a_wider_window_follows_the_truth_closer_and_a_short_one_does_not():
    pair, reference, _, a = syn10()
    medians = {s: np.median(relative_error(pair, reference, a, s)) for s in (0.25, 0.5, 1.0)}
    assert medians[0.25] > medians[0.5] > medians[1.0]  # measured 0.0417, 0.0134, 0.0061
    short = relative_error(pair, reference, a, 0.25)
    assert (short > PLAN_TOLERANCE).any()  # at 0.25 s some rows are above 10 percent (measured 15.8 percent)
    assert medians[1.0] < 0.01
    for s in (0.25, 1.0):
        got = local_tempo(a, smooth_s=s)
        assert got.smooth_s == s and (got.reason == TempoReason.valid).all()  # every window has two rows or more


@pytest.mark.parametrize(
    ("k_start", "k_end", "median_bound"),
    [
        pytest.param(1.0, 1.0, 1e-9, id="the same tempo"),
        pytest.param(1.5, 1.5, 1e-9, id="a constant 1.5"),
        pytest.param(0.6, 1.6, 0.03, id="0.6 to 1.6"),
        pytest.param(1.25, 0.8, 0.03, id="the query speeds up"),
    ],
)
def test_t_cmp_06_syn10_other_warps_are_followed_too(k_start, k_end, median_bound):
    pair, reference, _, a = syn10(k_start=k_start, k_end=k_end)
    error = relative_error(pair, reference, a, SMOOTH_S)
    assert np.isfinite(error).all()
    assert np.median(error) <= median_bound  # measured 0, 1e-15, 0.0087 and 0.0122
    assert np.median(error) <= PLAN_TOLERANCE  # the plan's bound for the default warp, here for the others too
    assert error.max() < (1e-9 if k_start == k_end else 0.10)  # measured 0, 1.1e-15, 0.0662 and 0.0664


@pytest.mark.parametrize(
    ("query_scale", "shift"),
    [pytest.param(0.8, (-120.0, 60.0), id="scale 0.8"), pytest.param(1.7, (40.0, -30.0), id="scale 1.7")],
)
def test_t_cmp_06_syn10_the_size_and_the_place_of_the_query_in_the_image_do_not_change_the_tempo(query_scale, shift):
    _, _, _, plain = syn10()
    _, _, _, moved = syn10(query_scale=query_scale, shift=shift)
    first, second = local_tempo(plain, smooth_s=SMOOTH_S), local_tempo(moved, smooth_s=SMOOTH_S)
    assert np.allclose(first.ratio, second.ratio, atol=0.01) and np.allclose(first.t_query, second.t_query, atol=0.01)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_cmp_06_syn10_at_one_pixel_of_noise_a_wider_window_follows_the_truth_closer(seed):
    """The plan sets no tolerance for noise, so only the direction is asserted; the numbers are in the docstring."""
    pair, reference, _, a = syn10(seed, noise_px=1.0)
    assert a.result.status == "ok"
    medians = {s: np.nanmedian(relative_error(pair, reference, a, s)) for s in (0.25, 1.0)}
    assert medians[1.0] < medians[0.25]  # measured 0.0393 against 0.0876, 0.0370 against 0.1459, 0.0307 against 0.1291
    got = local_tempo(a, smooth_s=SMOOTH_S)
    assert (got.reason == TempoReason.valid).all()  # the window is full whatever the noise
    assert got.whole_ratio == local_tempo(syn10()[3], smooth_s=SMOOTH_S).whole_ratio  # the clocks do not see the noise


# --- the deviation curve ----------------------------------------------------------------------------------------------
def test_t_cmp_06e_syn10_the_deviation_is_zero_for_the_units_that_do_not_move_and_small_for_the_arms():
    _, reference, _, a = syn10()
    got = deviation_curve(a)
    units = {name: index for index, name in enumerate(got.units)}
    assert got.status == "ok" and got.values.shape == (120, 21) and got.units == tuple(u.name for u in reference.units)
    assert not np.isnan(got.values).any() and (got.reason == DeviationReason.valid).all()  # 2520 of 2520 are values
    assert (got.values[:, [units[n] for n in STILL_UNITS]] == 0.0).all()  # the same pose in both: exactly 0 (measured)
    wrists = got.values[:, [units["LWrist"], units["RWrist"]]]
    assert (
        wrists.max() > 0.005 and wrists.max() < 0.02
    )  # the arms move and the matched frames are close: measured 0.0177
    assert got.values[:, units["l_forearm"]].max() < 0.1  # the forearm angle (chord): measured 0.051
    assert got.total.max() < 0.01  # measured 0.0060
    assert got.kinds == ("position",) * 12 + ("angle",) * 9


def test_t_cmp_06e_syn10_the_mean_of_the_row_costs_weighted_by_the_cells_is_d():
    _, _, _, a = syn10()
    got = deviation_curve(a)
    assert got.cells.sum() == len(a.result.path) == 128 and got.cells.min() == 1 and got.cells.max() == 2
    assert np.average(got.total, weights=got.cells) == pytest.approx(a.distance, abs=1e-12)  # D is the mean over cells
    assert got.total.mean() != pytest.approx(a.distance, abs=1e-6)  # the plain mean over rows is not D


def test_t_cmp_06e_syn11_the_deviation_points_at_the_arms_of_another_action():
    pair = make_pair("SYN-11", seed=1)
    reference = features_of(pair.ref)
    other, variant = features_of(pair.query), features_of(pair.truth["variant"])  # open_close and raise_lower again
    far = deviation_curve(align(reference, other, min_visible=MIN_VISIBLE, band=BAND))
    near = deviation_curve(align(reference, variant, min_visible=MIN_VISIBLE, band=BAND))
    units = {name: index for index, name in enumerate(far.units)}
    mean = {name: float(np.mean(far.values[:, i])) for name, i in units.items()}
    assert mean["LWrist"] > 0.5 and mean["RWrist"] > 0.5  # measured 0.773 trunk lengths
    assert mean["LElbow"] > 0.25 and mean["RElbow"] > 0.25  # measured 0.386
    assert mean["l_forearm"] > 0.15  # the chord of the forearm angle: measured 0.291
    assert far.values[:, [units[n] for n in STILL_UNITS]].max() < 1e-5  # measured 1.5e-7: the units that do not move
    assert far.total.mean() > 0.1 and far.total.mean() >= CLOSER * near.total.mean()  # measured 0.1529 and 9.6 times
    assert not np.isnan(far.values).any() and not np.isnan(near.values).any()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_cmp_06e_syn10_at_one_pixel_with_a_minimum_segment_length_a_dropped_angle_is_nan_with_a_reason_r1(seed):
    _, reference, query, a = syn10(seed, noise_px=1.0, min_segment_length=SHORT_SEGMENT)
    got = deviation_curve(a)
    nan = np.isnan(got.values)
    names = np.array(got.units)
    assert nan.any() and set(names[nan.any(axis=0)]) == {
        "l_forearm",
        "r_forearm",
    }  # only the two short forearm segments
    assert (got.reason[nan] == DeviationReason.not_valid_in_both).all() and (got.n_valid[nan] == 0).all()
    assert (got.reason[~nan] == DeviationReason.valid).all() and (got.n_valid[~nan] > 0).all()
    path = a.result.path
    for k, u in np.argwhere(nan):  # each NaN is a unit that no cell of its row has valid in both frames
        queries = path[path[:, 1] == k, 0]
        assert not (reference.valid[k, u] and query.valid[queries, u].any()), (k, u)
    for k, u in np.argwhere(~nan):  # and each value has a cell that does
        queries = path[path[:, 1] == k, 0]
        assert reference.valid[k, u] and query.valid[queries, u].any(), (k, u)
