"""T-CMP-03 (the whole chain), T-CMP-04 and T-CMP-04b on the generator: ``align`` on SYN-10 and SYN-11 (P6.03b).

Every layer is what the pipeline would hand to the comparison: ``run_quality_arrays``, ``pose_filtered_from_result``,
then ``frame_features`` and ``align`` (rows the query, columns the reference). **Test settings, not defaults of the
product** (task P6.03b Q1): ``min_visible`` 11 of 21 units (half, rounded up), ``band`` 0.2, ``symmetricP1``, weights
1; SYN-10 is generated with ``scale_px`` 120 because the generator refuses ``query_scale`` 1.7 at the default 200.
``min_segment_length`` 0.05 trunk lengths is a test value for the risk R1 of P6.01 (the direction of a limb segment
that is very short in the image is arbitrary), not a default.

Numbers measured on 2026-11-17 before any bound was set (seed 1 unless said; the task file, section 5, has them all):

* T-CMP-03: a layer against itself gives ``D`` = 0.0 exactly, a diagonal path of 120 cells and, as matched query times,
  the clock of the layer itself, for both patterns and for band 0.2 and 1.0, with 1 px of noise too.
* T-CMP-04: SYN-10, warp 0.8 to 1.25 (123 query rows, 120 reference rows), noise 0: ``D`` = 0.001756 (``symmetricP1``)
  and 0.001747 (``symmetric1``), against the plan's 0.02; the same for the query under a scale of 0.5, 0.8 and 1.7
  (the features carry no scale): the three ``D`` agree to 1e-5. The path leaves the diagonal by at most 0.0563 of the
  length (the band is 0.2) and stays within 0.63 reference rows of the true correspondence (median 0.25).
* **The two valleys.** SYN-10's action (raise then lower) is symmetric in time, so the cost matrix has a second valley
  on the anti-diagonal (P6.02: at most 0.0185). A monotone path cannot follow a valley that runs the other way: it can
  only cross it, and it does, at the middle of the movement where the two valleys meet (one cell of 128 is nearer to
  the mirror valley than to the truth: cell (55, 60), 0.24 reference rows from both valleys). The path at band 1.0 is
  cell for cell the path at band 0.2, with either pattern. A band **narrower than the true drift (0.0563)** does change
  the path: at 0.05, 0.04, 0.03, 0.02 and 0.01 ``D`` is 0.0042, 0.0095, 0.0159, 0.0224 and 0.0302.
* ``matched_query_times()`` against the generator's truth ``t_query = W(t_ref)``: the largest error is 0.0173 s and the
  median 0.0074 s (the step of the clock is 0.0333 s); the bounds are one step and half a step. The truth is the
  closed form of the generator's warp; the arrays of the generator agree with it to 2e-5 s.
* R1, SYN-10 at 1 px of noise, seeds 1 to 3: ``D`` is 0.0205, 0.0235, 0.0231 without a minimum segment length and
  0.0149, 0.0152, 0.0148 with 0.05 (the two forearm angles of 35 of the 120 frames are dropped: 70 of 2520 cells).
  The plan sets no tolerance for noise, so the test asserts only the direction (the minimum lowers ``D``) and that the
  path stays in the band; the numbers are reported, not bounded.
* T-CMP-04b, SYN-11 (90 frames): ``D(ref, other)`` is 0.159 (0.148 with the minimum) at noise 0 and 0.163 (0.151) at 1
  px; ``D(ref, variant)`` is 0.0032 (0.0021) at noise 0, 0.0151 (0.0098) at 1 px and 0.0172 (0.0107) with the
  generator's default variant noise of 1.5 px: ratios 49.5 (71.8), 10.8 (15.4) and 9.2 (13.8); the plan asks for 2.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.synth import TOLERANCES, SynthPair, SynthSequence, make_pair
from taiji_ai.compare import CompareError
from taiji_ai.compare.align import Alignment, align
from taiji_ai.compare.cost import cost_matrix
from taiji_ai.compare.dtw import dtw
from taiji_ai.compare.features import FrameFeatures, frame_features

SCALE_PX = 120.0
MIN_VISIBLE = 11  # of 21 units: half, rounded up (Q1)
BAND = 0.2
STEP = "symmetricP1"
SHORT_SEGMENT = 0.05  # a TEST value (R1 of P6.01), not a default
SHAPE_MAX = TOLERANCES["SYN-10"]["shape_distance_max"]  # 0.02 trunk lengths, noise-free
CLOSER = TOLERANCES["SYN-11"]["variant_closer_ratio"]  # 2.0
EDGE = 1e-12  # the tolerance of the band at its edge (the same as dtw's, written again here)
SIMILARITIES = [
    pytest.param(1.0, (0.0, 0.0), id="same size"),
    pytest.param(0.8, (-120.0, 60.0), id="scale 0.8"),
    pytest.param(1.7, (40.0, -30.0), id="scale 1.7"),
]


def features_of(seq: SynthSequence, min_segment_length: float | None = None) -> FrameFeatures:
    return frame_features(layer_of_sequence(seq), min_segment_length=min_segment_length)


@functools.cache
def syn10(
    seed: int = 1,
    query_scale: float = 1.0,
    shift: tuple[float, float] = (0.0, 0.0),
    noise_px: float = 0.0,
    min_segment_length: float | None = None,
) -> tuple[SynthPair, FrameFeatures, FrameFeatures]:
    """``(pair, reference features, query features)`` of SYN-10 through the real chain (default warp 0.8 to 1.25)."""
    pair = make_pair(
        "SYN-10", seed=seed, scale_px=SCALE_PX, query_scale=query_scale, query_shift_px=shift, noise_px=noise_px
    )
    return pair, features_of(pair.ref, min_segment_length), features_of(pair.query, min_segment_length)


def drift(path: np.ndarray, n: int, m: int) -> float:
    """The largest ``|i / (n - 1) - k / (m - 1)|`` over the cells of the path: how far it leaves the diagonal."""
    return float(np.abs(path[:, 0] / (n - 1) - path[:, 1] / (m - 1)).max())


def assert_a_path_from_corner_to_corner(a: Alignment) -> None:
    path = a.result.path
    n, m = a.cost.values.shape
    assert path[0].tolist() == [0, 0] and path[-1].tolist() == [n - 1, m - 1]
    assert set(map(tuple, np.diff(path, axis=0).tolist())) <= {(1, 1), (1, 0), (0, 1)}  # monotone unit steps
    assert np.isfinite(a.cost.values[path[:, 0], path[:, 1]]).all()


def true_query_time(pair: SynthPair, ref_t: np.ndarray) -> np.ndarray:
    """The truth of SYN-10: the query time of the reference time ``t``, ``W(t) = k0 t + (k1 - k0) t^2 / (2 duration)``
    (the closed form of ``d t_query / d t_ref = k0 + (k1 - k0) t_ref / duration``)."""
    k0, k1, duration = pair.truth["k_start"], pair.truth["k_end"], pair.params["duration"]
    return k0 * ref_t + (k1 - k0) * ref_t**2 / (2.0 * duration)


def distance_to_valleys(pair: SynthPair, ref: FrameFeatures, a: Alignment) -> tuple[np.ndarray, np.ndarray]:
    """For every path cell, its distance in reference rows from the true correspondence and from the mirror valley
    (the pose at phase ``phi`` equals the pose at ``1 - phi``)."""
    duration, step = pair.params["duration"], float(ref.t_sec[1] - ref.t_sec[0])
    phase = np.asarray(pair.truth["t_ref_of_query"]) / duration  # the phase of every query row
    true_row, mirror_row = phase * duration / step, (1.0 - phase) * duration / step
    i, k = a.result.path[:, 0], a.result.path[:, 1]
    return np.abs(k - true_row[i]), np.abs(k - mirror_row[i])


# --- T-CMP-03 through the whole chain ---------------------------------------------------------------------------------
@pytest.mark.parametrize("noise_px", [0.0, 1.0], ids=["noise 0", "noise 1 px"])
@pytest.mark.parametrize("step", ["symmetricP1", "symmetric1"])
@pytest.mark.parametrize("band", [BAND, 1.0])
def test_t_cmp_03_a_layer_compared_with_itself_has_distance_zero_and_the_diagonal_path(band, step, noise_px):
    pair = make_pair("SYN-10", seed=1, scale_px=SCALE_PX, noise_px=noise_px)
    reference, copy = features_of(pair.ref), features_of(pair.ref)  # two builds of the same segment
    got = align(reference, copy, min_visible=MIN_VISIBLE, band=band, step=step)
    n = len(reference.t_sec)
    assert n == 120 and got.result.status == "ok"
    assert got.distance == 0.0 and got.result.accumulated == 0.0  # exactly: the cost of a frame with itself is 0
    assert np.array_equal(got.result.path, np.stack([np.arange(n), np.arange(n)], axis=1))
    assert (np.diagonal(got.cost.values) == 0.0).all()
    assert np.array_equal(got.matched_query_times(), reference.t_sec)  # the segment's own clock, in seconds
    c = got.as_comparison("take_a", "take_a_again")
    assert c.distance == 0.0 and dict(c.settings) == dict(got.settings)
    assert got.settings["band"] == band and got.settings["step"] == step and got.settings["min_visible"] == MIN_VISIBLE


def test_t_cmp_03_the_same_movement_re_timed_to_the_same_clock_under_a_similarity_is_the_diagonal_with_d_about_zero():
    pair = make_pair(
        "SYN-10", seed=1, scale_px=SCALE_PX, k_start=1.0, k_end=1.0, query_scale=1.7, query_shift_px=(40.0, -30.0)
    )
    reference, query = features_of(pair.ref), features_of(pair.query)
    got = align(reference, query, min_visible=MIN_VISIBLE, band=BAND)
    assert got.result.path[:, 0].tolist() == got.result.path[:, 1].tolist() == list(range(120))
    assert got.distance is not None and got.distance < 1e-4  # measured 5.1e-7: a scale and a shift enter no cell


# --- T-CMP-04: SYN-10 -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("query_scale", "shift"), SIMILARITIES)
def test_t_cmp_04_syn10_a_stretched_query_keeps_its_shape_and_the_path_stays_in_the_band(query_scale, shift):
    pair, reference, query = syn10(1, query_scale, shift)
    got = align(reference, query, min_visible=MIN_VISIBLE, band=BAND, step=STEP)
    n, m = len(query.t_sec), len(reference.t_sec)
    assert (n, m) == (123, 120) and got.cost.values.shape == (123, 120) and got.result.status == "ok"
    assert got.distance is not None and got.distance <= SHAPE_MAX  # the plan: 0.02 trunk lengths; measured 0.001756
    assert got.distance == pytest.approx(0.001756, abs=2e-5)  # the same for every scale: the features carry none
    assert_a_path_from_corner_to_corner(got)
    path = got.result.path
    # the formula of the band, written here again and not read from ``dtw``
    assert (np.abs(path[:, 0] / (n - 1) - path[:, 1] / (m - 1)) <= BAND + EDGE).all()
    assert drift(path, n, m) < 0.07  # measured 0.0563: a third of the band is enough for a warp of 0.8 to 1.25
    assert got.settings["band"] == BAND and got.settings["min_visible"] == MIN_VISIBLE
    assert got.settings["feature_version"] == reference.version and len(got.settings["units"]) == 21


def test_t_cmp_04_syn10_align_is_the_parts_on_real_features_for_both_patterns():
    _, reference, query = syn10()
    for step in ("symmetricP1", "symmetric1"):
        got = align(reference, query, min_visible=MIN_VISIBLE, band=BAND, step=step)
        want = dtw(cost_matrix(reference, query, min_visible=MIN_VISIBLE), band=BAND, step=step)
        assert np.array_equal(got.result.path, want.path)
        assert (got.distance, got.result.accumulated, got.result.normalised) == (
            want.distance,
            want.accumulated,
            want.normalised,
        )
    p1 = align(reference, query, min_visible=MIN_VISIBLE, band=BAND, step="symmetricP1")
    unit = align(reference, query, min_visible=MIN_VISIBLE, band=BAND, step="symmetric1")
    assert p1.distance == pytest.approx(0.001756, abs=2e-5) and unit.distance == pytest.approx(0.001747, abs=2e-5)
    assert p1.result.normalised != p1.distance  # D is the mean of the cost over the path, not the normalised value
    assert p1.as_comparison("ref_take", "query_take").distance == p1.distance


def test_t_cmp_04_syn10_the_path_follows_the_true_valley_at_band_1_and_at_band_0_2_and_only_crosses_the_mirror():
    pair, reference, query = syn10()
    for step in ("symmetricP1", "symmetric1"):
        narrow = align(reference, query, min_visible=MIN_VISIBLE, band=BAND, step=step)
        free = align(reference, query, min_visible=MIN_VISIBLE, band=1.0, step=step)
        assert np.array_equal(narrow.result.path, free.result.path)  # measured: the same cells, whatever the band
        assert narrow.distance == free.distance
        to_true, to_mirror = distance_to_valleys(pair, reference, free)
        assert np.median(to_true) < 0.5 and to_true.max() < 1.5  # measured 0.25 and 0.63 reference rows
        assert (to_mirror < to_true).mean() <= 0.05  # measured 1 cell of 128: where the two valleys cross
        assert to_mirror.min() < 1.0 < np.median(to_mirror)  # it touches the mirror valley where they cross, only there
        crossing = free.result.path[np.argmin(to_mirror)]  # measured (55, 60): the middle of the movement
        assert 0.4 < crossing[0] / (len(query.t_sec) - 1) < 0.6 and 0.4 < crossing[1] / (len(reference.t_sec) - 1) < 0.6


def test_t_cmp_04_syn10_a_band_narrower_than_the_true_drift_changes_the_path_and_raises_d():
    pair, reference, query = syn10()
    n, m = len(query.t_sec), len(reference.t_sec)
    wide = align(reference, query, min_visible=MIN_VISIBLE, band=BAND)
    before = wide
    for band in (0.06, 0.05, 0.04, 0.03, 0.02, 0.01):
        got = align(reference, query, min_visible=MIN_VISIBLE, band=band)
        assert got.result.status == "ok"
        path = got.result.path
        assert (np.abs(path[:, 0] / (n - 1) - path[:, 1] / (m - 1)) <= band + EDGE).all()
        assert got.result.accumulated >= before.result.accumulated  # a subset of the paths cannot be cheaper
        if band >= 0.06:
            assert np.array_equal(path, wide.result.path)  # the true path (0.0563) still fits: nothing changes
        else:
            assert not np.array_equal(path, wide.result.path) and got.distance > before.distance  # measured
            assert drift(path, n, m) > band - 0.002  # the path presses against the edge of the band
        before = got
    assert got.distance > 2.0 * wide.distance  # measured at band 0.01: 0.0302 against 0.001756


def test_t_cmp_04_syn10_matched_query_times_agree_with_the_generators_truth_in_seconds():
    pair, reference, query = syn10()
    got = align(reference, query, min_visible=MIN_VISIBLE, band=BAND)
    truth = true_query_time(pair, reference.t_sec)
    from_arrays = np.interp(reference.t_sec, np.asarray(pair.truth["t_ref_of_query"]), query.t_sec)
    assert np.abs(from_arrays - truth).max() < 1e-3  # the closed form is the one of the generator (measured 2e-5 s)
    matched = got.matched_query_times()
    step = float(query.t_sec[1] - query.t_sec[0])
    error = np.abs(matched - truth)
    assert matched.shape == (120,) and np.isfinite(matched).all()
    assert error.max() < step  # measured 0.0173 s against a step of 0.0333 s
    assert np.median(error) < step / 2  # measured 0.0074 s
    assert np.all(np.diff(matched) >= 0.0)
    assert matched[0] == query.t_sec[0]  # symmetricP1: reference row 0 holds only the cell (0, 0)
    # the query seconds per reference second, as a straight line through the matches: the truth's own slope (1.0231,
    # about the mean rate (0.8 + 1.25) / 2 of the warp) and not a flattened one
    rate, true_rate = np.polyfit(reference.t_sec, matched, 1)[0], np.polyfit(reference.t_sec, truth, 1)[0]
    assert abs(rate - true_rate) < 0.01  # measured: 1.0239 against the truth's line


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_cmp_04_syn10_at_one_pixel_of_noise_a_minimum_segment_length_lowers_d_r1(seed):
    """R1 of P6.01 on the whole chain: at 1 px the arbitrary direction of a short forearm adds to ``D``. The plan sets
    no tolerance for noise, so only the direction is asserted (measured 0.0205 to 0.0235 without the minimum and 0.0148
    to 0.0152 with 0.05); the numbers are in the task file."""
    _, plain_ref, plain_qry = syn10(seed, noise_px=1.0)
    _, kept_ref, kept_qry = syn10(seed, noise_px=1.0, min_segment_length=SHORT_SEGMENT)
    plain = align(plain_ref, plain_qry, min_visible=MIN_VISIBLE, band=BAND)
    kept = align(kept_ref, kept_qry, min_visible=MIN_VISIBLE, band=BAND)
    assert plain.result.status == "ok" and kept.result.status == "ok"
    assert (~plain_ref.valid).sum() == 0 and (~kept_ref.valid).sum() > 30  # the minimum drops short-segment angles
    assert kept.distance < plain.distance
    assert drift(plain.result.path, len(plain_qry.t_sec), len(plain_ref.t_sec)) <= BAND
    assert drift(kept.result.path, len(kept_qry.t_sec), len(kept_ref.t_sec)) <= BAND
    assert plain.settings["min_segment_length"] is None and kept.settings["min_segment_length"] == SHORT_SEGMENT
    assert plain.settings != kept.settings  # a distance made with the minimum is not comparable with one made without


def test_t_cmp_04_features_made_with_and_without_a_minimum_segment_length_are_not_aligned():
    _, plain_ref, _ = syn10(1, noise_px=1.0)
    _, _, kept_qry = syn10(1, noise_px=1.0, min_segment_length=SHORT_SEGMENT)
    with pytest.raises(CompareError, match="min_segment_length"):
        align(plain_ref, kept_qry, min_visible=MIN_VISIBLE, band=BAND)


# --- T-CMP-04b: SYN-11 ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("noise_px", "variant_noise_px", "min_segment_length"),
    [
        pytest.param(0.0, 0.0, None, id="noise 0"),
        pytest.param(1.0, 1.0, None, id="1 px"),
        pytest.param(1.0, 1.0, SHORT_SEGMENT, id="1 px with a minimum segment length"),
        pytest.param(0.0, None, None, id="generator default variant noise of 1.5 px"),
    ],
)
def test_t_cmp_04b_syn11_another_action_is_farther_than_a_variant_of_the_same_one(
    noise_px, variant_noise_px, min_segment_length
):
    params = {"noise_px": noise_px}
    if variant_noise_px is not None:  # else the generator's own default of 1.5 px for the variant
        params["variant_noise_px"] = variant_noise_px
    pair = make_pair("SYN-11", seed=1, **params)
    variant = pair.truth["variant"]
    reference = features_of(pair.ref, min_segment_length)
    other, same = features_of(pair.query, min_segment_length), features_of(variant, min_segment_length)
    to_other = align(reference, other, min_visible=MIN_VISIBLE, band=BAND)  # reference raise_lower, query open_close
    to_variant = align(reference, same, min_visible=MIN_VISIBLE, band=BAND)  # reference raise_lower, query raise_lower
    assert to_other.result.status == "ok" and to_variant.result.status == "ok"
    assert pair.truth["action_query"] != pair.truth["action_ref"] and variant.params["action"] == "raise_lower"
    d_other, d_variant = to_other.distance, to_variant.distance
    assert d_other > 0.05  # measured 0.148 to 0.163: another action is clearly away (not a ratio of two small numbers)
    assert d_other >= CLOSER * d_variant  # the plan: 2; measured 9.2 to 71.8
    assert to_other.settings == to_variant.settings  # the two distances were made alike: comparable
    assert_a_path_from_corner_to_corner(to_other)
    assert_a_path_from_corner_to_corner(to_variant)
    other_c = to_other.as_comparison("ref_take", "other_action")
    variant_c = to_variant.as_comparison("ref_take", "variant_take")
    assert other_c.distance == d_other and variant_c.distance == d_variant  # D, as P6.06 reads it
