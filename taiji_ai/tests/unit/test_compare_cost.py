"""T-CMP-02a to 02h: the masked cost matrix between a query and a reference (P6.02, Appendix C.2, W8).

Every expected number is re-derived with plain Python loops over every cell and every unit
(``helpers/compare_cost_ref.py``, ``math`` only, never the module's own helpers): rows are the query, columns the
reference; a cell is the weighted mean ``sum(w_u d_u) / sum(w_u)`` over the units with ``w_u > 0`` valid in both
frames, ``d_u`` the Euclidean norm of the difference of the two 2-vectors (a position in trunk lengths; an angle as the
chord ``2 |sin((a - b) / 2)|``, 0 to 2), ``+inf`` when fewer than ``min_visible`` such units, never NaN. The features
are built by hand, so that a test controls the value, the mask and what is stored under a mask; one test goes through
the real ``frame_features``.
"""

from __future__ import annotations

import dataclasses
import math
import time
import tracemalloc
from collections.abc import Mapping

import numpy as np
import pytest

from helpers.compare_cost_ref import (
    ANGLES,
    POSITIONS,
    RECORDING_QRY,
    RECORDING_REF,
    chord,
    expected_cost,
    make_features,
    make_units,
    random_features,
)
from helpers.metric_layers import body, cells, drop, edited, exact_layer
from taiji_ai.compare import CompareError
from taiji_ai.compare.cost import CostMatrix, cost_matrix
from taiji_ai.compare.dtw import dtw
from taiji_ai.compare.features import DEFAULT_JOINTS, DEFAULT_SEGMENTS, FeatureUnit, FrameFeatures, frame_features
from taiji_ai.pose.skeleton import IDX

INF = math.inf
RTOL = 1e-12  # the sums of the module and of the loops differ by the order of the additions only
U5 = len(POSITIONS) + len(ANGLES)  # 4 positions and 2 angles: 6 units
SEEDS = [0, 1, 2, 3, 4, 5]
# 900 x 900 x 21 units, block of 64 rows: see the task file, section 5 (measured 0.31 s and 29 MB at the peak, of which
# 9.6 MB are the result; one block of all 900 rows peaks at 292 MB and the 4-dimensional array alone would be 260 MB).
# The bounds only catch a gross regression.
TIMING_BOUND_S = 5.0
MEMORY_BOUND_MB = 80.0


def strict_cost(*args, **kwargs) -> CostMatrix:
    """``cost_matrix`` with every floating-point flag an error: the value stored under a mask (NaN, inf) is never
    computed with, so no operation may even be invalid (inf - inf, inf * 0)."""
    with np.errstate(all="raise"):
        return cost_matrix(*args, **kwargs)


def one_unit(x: float, y: float = 0.0) -> FrameFeatures:
    return make_features(np.array([[[x, y]]]), np.array([[True]]), make_units(("LWrist",), ()))


def check(cm: CostMatrix, reference, query, *, min_visible: int, weights=None) -> None:
    """``cm`` is the independent cost and the independent count of common units."""
    want, counts = expected_cost(reference, query, min_visible=min_visible, weights=weights)
    assert cm.values.shape == want.shape == counts.shape
    assert np.array_equal(np.isinf(cm.values), np.isinf(want))
    np.testing.assert_allclose(cm.values, want, rtol=RTOL, atol=RTOL)
    assert np.array_equal(cm.n_common, counts)


# --- T-CMP-02a: the values ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_t_cmp_02a_every_cell_equals_the_independent_loops_on_random_features(seed):
    rng = np.random.default_rng(seed)
    reference, query = random_features(rng, 9), random_features(rng, 7, recording_id=RECORDING_QRY)
    for min_visible in (1, 2, 4):
        cm = cost_matrix(reference, query, min_visible=min_visible)
        check(cm, reference, query, min_visible=min_visible)
        assert cm.values.shape == (7, 9) and cm.n_common.shape == (7, 9)
    values = cost_matrix(reference, query, min_visible=1).values
    assert np.isfinite(values).any() and np.ptp(values[np.isfinite(values)]) > 0.1  # not all inf, not a constant


def test_t_cmp_02a_the_distance_of_a_position_is_the_euclidean_norm_in_trunk_lengths():
    cm = cost_matrix(one_unit(0.0, 0.0), one_unit(3.0, 4.0), min_visible=1)  # the 3, 4, 5 triangle
    assert cm.values.shape == (1, 1) and cm.values[0, 0] == pytest.approx(5.0, abs=1e-15)
    cm = cost_matrix(one_unit(-1.0, 2.0), one_unit(2.0, -2.0), min_visible=1)
    assert cm.values[0, 0] == pytest.approx(5.0, abs=1e-15) and cm.n_common[0, 0] == 1


def angle(degrees: float, units: tuple[FeatureUnit, ...] = make_units((), ("trunk",))) -> FrameFeatures:
    a = math.radians(degrees)
    return make_features(np.array([[[math.sin(a), math.cos(a)]]]), np.array([[True]]), units)


@pytest.mark.parametrize(
    ("deg_ref", "deg_qry", "want"),
    [
        pytest.param(0.0, 0.0, 0.0, id="same"),
        pytest.param(0.0, 90.0, math.sqrt(2.0), id="a quarter turn"),
        pytest.param(0.0, 180.0, 2.0, id="opposite"),
        pytest.param(0.0, 60.0, 1.0, id="60 degrees is a chord of 1"),
        pytest.param(350.0, 10.0, 2.0 * math.sin(math.radians(10.0)), id="350 and 10: across the wrap"),
        pytest.param(359.0, 1.0, 2.0 * math.sin(math.radians(1.0)), id="359 and 1: across the wrap"),
        pytest.param(-170.0, 170.0, 2.0 * math.sin(math.radians(10.0)), id="-170 and 170"),
    ],
)
def test_t_cmp_02a_the_distance_of_an_angle_is_the_chord_and_never_wraps(deg_ref, deg_qry, want):
    cm = cost_matrix(angle(deg_ref), angle(deg_qry), min_visible=1)
    assert cm.values[0, 0] == pytest.approx(want, abs=1e-12)
    assert 0.0 <= cm.values[0, 0] <= 2.0 + 1e-12
    pair_ref = [math.sin(math.radians(deg_ref)), math.cos(math.radians(deg_ref))]
    pair_qry = [math.sin(math.radians(deg_qry)), math.cos(math.radians(deg_qry))]
    assert cm.values[0, 0] == pytest.approx(chord(pair_qry, pair_ref), abs=1e-12)  # the loops' own chord, from atan2


def test_t_cmp_02a_a_cell_is_the_weighted_mean_of_a_position_and_an_angle_and_not_their_sum():
    units = make_units(("LWrist",), ("trunk",))
    ref = make_features(np.array([[[0.0, 0.0], [0.0, 1.0]]]), np.array([[True, True]]), units)  # angle 0: up
    qry = make_features(np.array([[[3.0, 4.0], [1.0, 0.0]]]), np.array([[True, True]]), units)  # angle 90
    cm = cost_matrix(ref, qry, min_visible=1)
    assert cm.values[0, 0] == pytest.approx((5.0 + math.sqrt(2.0)) / 2.0, abs=1e-14)  # equal weights: the mean
    cm = cost_matrix(ref, qry, min_visible=1, weights={"LWrist": 3.0})  # the angle keeps 1: (3 * 5 + 1.414) / 4
    assert cm.values[0, 0] == pytest.approx((15.0 + math.sqrt(2.0)) / 4.0, abs=1e-14)
    cm = cost_matrix(ref, qry, min_visible=1, weights={"LWrist": 3.0, "trunk": 1.0})
    assert cm.values[0, 0] == pytest.approx((15.0 + math.sqrt(2.0)) / 4.0, abs=1e-14)


def test_t_cmp_02a_the_mean_does_not_grow_with_the_number_of_units():
    one = one_unit(3.0, 4.0)
    units = make_units(("LWrist", "RWrist", "LKnee"), ())
    ref3 = make_features(np.zeros((1, 3, 2)), np.ones((1, 3), dtype=bool), units)
    qry3 = make_features(np.tile([3.0, 4.0], (1, 3, 1)), np.ones((1, 3), dtype=bool), units)
    assert cost_matrix(one_unit(0.0), one, min_visible=1).values[0, 0] == pytest.approx(5.0, abs=1e-15)
    assert cost_matrix(ref3, qry3, min_visible=1).values[0, 0] == pytest.approx(5.0, abs=1e-14)  # not 15


def test_t_cmp_02a_rows_are_the_query_and_columns_the_reference():
    units = make_units(("LWrist",), ())
    ref = make_features(np.array([[[0.0, 0.0]], [[1.0, 0.0]], [[2.0, 0.0]]]), np.ones((3, 1), dtype=bool), units)
    qry = make_features(np.array([[[0.0, 0.0]], [[10.0, 0.0]]]), np.ones((2, 1), dtype=bool), units)
    cm = cost_matrix(ref, qry, min_visible=1)
    assert cm.values.shape == (2, 3)  # (query rows, reference columns)
    assert np.array_equal(cm.values, [[0.0, 1.0, 2.0], [10.0, 9.0, 8.0]])
    assert cm.n_common.shape == (2, 3)


def test_t_cmp_02a_real_features_with_dropped_joints_and_a_bridged_joint_equal_the_loops():
    """Through the real ``frame_features``: NaN under the masks, a position and an angle lost, a bridged joint."""

    def wavy(seed: int) -> FrameFeatures:
        rng = np.random.default_rng(seed)
        kp = body(30, 400.0).astype(np.float64) + rng.normal(0.0, 8.0, size=(30, 26, 2))
        layer = exact_layer(kp)
        k, r, i = cells(layer)
        drop(k, r, 3, IDX["LWrist"], 1)  # a position and the forearm angle lost
        drop(k, r, 4, IDX["LHip"], 3)  # every position (they need the hips), the left thigh and the trunk lost
        drop(k, r, 9, IDX["RKnee"], 2)
        r[11, IDX["LElbow"]] = 2  # a bridged joint: a value, flagged
        i[11, IDX["LElbow"]] = True
        return frame_features(edited(layer, keypoints=k, reason=r, interpolated=i))

    reference, query = wavy(1), wavy(2)
    assert not reference.valid.all() and reference.valid.any()  # some NaN under the masks, most valid
    assert np.isnan(reference.values[~reference.valid]).all()
    for min_visible in (1, 10, 21):
        check(cost_matrix(reference, query, min_visible=min_visible), reference, query, min_visible=min_visible)
    cm = cost_matrix(reference, query, min_visible=21)
    assert np.isinf(cm.values[3, 7]) and np.isinf(cm.values[7, 3]) and np.isfinite(cm.values[0, 0])  # row 3: a hole
    assert cm.n_common[0, 0] == 21 and cm.n_common[3, 7] < 21


# --- T-CMP-02b: a masked unit takes no part --------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("garbage", [7.5, 1e6, -3.0, INF, -INF, float("nan")], ids=lambda g: f"under the mask: {g}")
@pytest.mark.parametrize("weights", [None, {"LWrist": 0.0, "l_forearm": 3.0}], ids=["default weights", "a weight of 0"])
def test_t_cmp_02b_the_value_stored_under_a_false_mask_changes_nothing(seed, garbage, weights):
    rng = np.random.default_rng(seed)
    reference, query = random_features(rng, 8), random_features(rng, 6)
    want = strict_cost(reference, query, min_visible=2, weights=weights)
    for f in (reference, query):
        f.values[~f.valid] = garbage  # the cells that the mask excludes now hold something else
    got = strict_cost(reference, query, min_visible=2, weights=weights)  # no flag either: inf * 0 is never computed
    assert np.array_equal(got.values, want.values) and np.array_equal(got.n_common, want.n_common)


def test_t_cmp_02b_a_valid_value_does_change_the_cost_so_that_the_test_above_is_not_vacuous():
    rng = np.random.default_rng(0)
    reference, query = random_features(rng, 8, p_invalid=0.0), random_features(rng, 6, p_invalid=0.0)
    before = cost_matrix(reference, query, min_visible=1).values.copy()
    query.values[2, 1] += 0.5  # a valid value
    after = cost_matrix(reference, query, min_visible=1).values
    assert not np.array_equal(before, after) and np.array_equal(np.delete(before, 2, 0), np.delete(after, 2, 0))


@pytest.mark.parametrize("seed", SEEDS)
def test_t_cmp_02b_n_common_counts_exactly_the_units_valid_in_both_frames(seed):
    rng = np.random.default_rng(seed)
    reference, query = random_features(rng, 8, p_invalid=0.5), random_features(rng, 6, p_invalid=0.5)
    cm = cost_matrix(reference, query, min_visible=3)
    for i in range(6):
        for k in range(8):
            both = [u for u in range(U5) if query.valid[i, u] and reference.valid[k, u]]
            assert cm.n_common[i, k] == len(both)
    assert np.isinf(cm.values[cm.n_common < 3]).all() and np.isfinite(cm.values[cm.n_common >= 3]).all()
    assert cm.n_common.min() < 3 <= cm.n_common.max()  # the random masks reach both sides of the threshold


def test_t_cmp_02b_a_unit_masked_in_one_frame_only_is_left_out_of_that_cell_and_not_of_the_others():
    units = make_units(("LWrist", "RWrist"), ())
    ref = make_features(np.array([[[0.0, 0.0], [0.0, 0.0]]] * 2), np.array([[True, True], [True, True]]), units)
    qry = make_features(
        np.array([[[3.0, 4.0], [0.0, 1.0]], [[3.0, 4.0], [99.0, 99.0]]]),
        np.array([[True, True], [True, False]]),  # the second query frame has no RWrist (the stored 99 is not read)
        units,
    )
    cm = cost_matrix(ref, qry, min_visible=1)
    assert np.array_equal(cm.values, [[3.0, 3.0], [5.0, 5.0]])  # (5 + 1) / 2 and 5 / 1
    assert np.array_equal(cm.n_common, [[2, 2], [1, 1]])


# --- T-CMP-02c: min_visible -----------------------------------------------------------------------------------------
UNITS3 = make_units(("LWrist", "RWrist", "LKnee"), ())


def three_unit_pair() -> tuple[FrameFeatures, FrameFeatures]:
    """Reference frames: all three units valid; units 1 and 2 valid. Query frames: all; units 0 and 1; unit 0; none."""
    ref_valid = np.array([[True, True, True], [False, True, True]])
    qry_valid = np.array([[True, True, True], [True, True, False], [True, False, False], [False, False, False]])
    ref = make_features(np.where(ref_valid[..., None], 1.0, np.nan) * np.ones((2, 3, 2)), ref_valid, UNITS3)
    qry = make_features(np.where(qry_valid[..., None], 2.0, np.nan) * np.ones((4, 3, 2)), qry_valid, UNITS3)
    return ref, qry


COMMON = np.array([[3, 2], [2, 1], [1, 0], [0, 0]])  # the units valid in both, query frame by reference frame


@pytest.mark.parametrize(
    ("min_visible", "finite"),
    [
        pytest.param(1, [[1, 1], [1, 1], [1, 0], [0, 0]], id="min_visible 1: at least one"),
        pytest.param(2, [[1, 1], [1, 0], [0, 0], [0, 0]], id="min_visible 2: exactly 2 is enough, 1 is not"),
        pytest.param(3, [[1, 0], [0, 0], [0, 0], [0, 0]], id="min_visible 3: all units"),
    ],
)
def test_t_cmp_02c_fewer_common_units_than_min_visible_is_infinity_and_exactly_min_visible_is_a_value(
    min_visible, finite
):
    ref, qry = three_unit_pair()
    cm = cost_matrix(ref, qry, min_visible=min_visible)
    assert np.array_equal(np.isfinite(cm.values), np.array(finite, dtype=bool))
    assert np.array_equal(cm.n_common, COMMON)  # the count is reported whatever the threshold, also in an inf cell
    assert (cm.values[np.isfinite(cm.values)] == math.sqrt(2.0)).all()  # |(2, 2) - (1, 1)|, every unit alike
    assert cm.values.dtype == np.float64 and not np.isnan(cm.values).any()
    assert np.isposinf(cm.values[~np.isfinite(cm.values)]).all()  # +inf, not -inf, not a large number


def test_t_cmp_02c_a_frame_without_any_valid_unit_is_infinity_against_every_frame():
    ref, qry = three_unit_pair()
    cm = cost_matrix(ref, qry, min_visible=1)
    assert np.isposinf(cm.values[3]).all() and (cm.n_common[3] == 0).all()
    all_off = make_features(np.full((2, 3, 2), np.nan), np.zeros((2, 3), dtype=bool), UNITS3)
    cm = cost_matrix(ref, all_off, min_visible=1)
    assert np.isposinf(cm.values).all() and cm.values.shape == (2, 2) and (cm.n_common == 0).all()


def test_t_cmp_02c_the_weighted_count_not_the_valid_count_is_compared_with_min_visible():
    ref, qry = three_unit_pair()
    cm = cost_matrix(ref, qry, min_visible=2, weights={"LWrist": 0.0})  # unit 0 is left out of the count
    assert np.array_equal(cm.n_common, [[2, 2], [1, 1], [0, 0], [0, 0]])
    assert np.array_equal(np.isfinite(cm.values), [[1, 1], [0, 0], [0, 0], [0, 0]])


# --- T-CMP-02d: weights ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("factor", [7.0, 1e-3, 1e5, 0.1])
def test_t_cmp_02d_a_common_factor_of_the_weights_changes_nothing(seed, factor):
    rng = np.random.default_rng(seed)
    reference, query = random_features(rng, 7), random_features(rng, 5)
    weights = {u.name: float(w) for u, w in zip(reference.units, rng.uniform(0.2, 3.0, size=U5), strict=True)}
    base = cost_matrix(reference, query, min_visible=2, weights=weights)
    scaled = cost_matrix(reference, query, min_visible=2, weights={k: v * factor for k, v in weights.items()})
    check(base, reference, query, min_visible=2, weights=weights)
    np.testing.assert_allclose(scaled.values, base.values, rtol=1e-12, atol=0.0)  # inf equals inf
    assert np.array_equal(scaled.n_common, base.n_common)
    assert scaled.weights == tuple(v * factor for v in weights.values())  # the weights are echoed as they were given


@pytest.mark.parametrize("seed", SEEDS)
def test_t_cmp_02d_a_weight_of_zero_is_the_unit_removed_from_the_mean_and_from_the_count(seed):
    rng = np.random.default_rng(seed)
    reference, query = random_features(rng, 7, p_invalid=0.4), random_features(rng, 5, p_invalid=0.4)
    keep = [0, 2, 3, 5]  # the units 1 (LWrist) and 4 (l_forearm) get weight 0
    kept_units = tuple(reference.units[u] for u in keep)
    fewer_ref = make_features(reference.values[:, keep], reference.valid[:, keep], kept_units)
    fewer_qry = make_features(query.values[:, keep], query.valid[:, keep], kept_units)
    zero = {"LWrist": 0.0, "l_forearm": 0.0}
    for min_visible in (1, 2, 3):
        got = cost_matrix(reference, query, min_visible=min_visible, weights=zero)
        want = cost_matrix(fewer_ref, fewer_qry, min_visible=min_visible)  # the same features without those columns
        assert np.array_equal(got.values, want.values) and np.array_equal(got.n_common, want.n_common)
        check(got, reference, query, min_visible=min_visible, weights=zero)
    assert cost_matrix(reference, query, min_visible=1, weights=zero).weights == (1.0, 0.0, 1.0, 1.0, 0.0, 1.0)


def test_t_cmp_02d_the_weights_move_the_mean_toward_the_heavier_unit_and_are_echoed_in_the_units_order():
    units = make_units(("LWrist", "RWrist"), ())
    ref = make_features(np.zeros((1, 2, 2)), np.ones((1, 2), dtype=bool), units)
    qry = make_features(np.array([[[3.0, 4.0], [0.0, 1.0]]]), np.ones((1, 2), dtype=bool), units)  # distances 5 and 1
    assert cost_matrix(ref, qry, min_visible=1).values[0, 0] == pytest.approx(3.0, abs=1e-15)
    heavy = cost_matrix(ref, qry, min_visible=1, weights={"LWrist": 3.0, "RWrist": 1.0})
    assert heavy.values[0, 0] == pytest.approx(4.0, abs=1e-15) and heavy.weights == (3.0, 1.0)
    flipped = cost_matrix(
        ref, qry, min_visible=1, weights={"RWrist": 3.0, "LWrist": 1.0}
    )  # the order of the keys is free
    assert flipped.values[0, 0] == pytest.approx(2.0, abs=1e-15) and flipped.weights == (1.0, 3.0)
    only = cost_matrix(ref, qry, min_visible=1, weights={"LWrist": 0.0})
    assert only.values[0, 0] == pytest.approx(1.0, abs=1e-15) and (only.n_common == 1).all()


def test_t_cmp_02d_default_weights_are_one_for_every_unit_and_a_unit_that_is_not_named_keeps_one():
    rng = np.random.default_rng(3)
    reference, query = random_features(rng, 6), random_features(rng, 5)
    default = cost_matrix(reference, query, min_visible=2)
    assert default.weights == (1.0,) * U5 and all(type(w) is float for w in default.weights)
    explicit = cost_matrix(reference, query, min_visible=2, weights={u.name: 1.0 for u in reference.units})
    partial = cost_matrix(reference, query, min_visible=2, weights={"LWrist": 1.0})
    empty = cost_matrix(reference, query, min_visible=2, weights={})
    for other in (explicit, partial, empty):
        assert np.array_equal(other.values, default.values) and other.weights == default.weights
    assert cost_matrix(reference, query, min_visible=2, weights={"LKnee": 2}).weights == (1.0, 1.0, 1.0, 2.0, 1.0, 1.0)


def test_t_cmp_02d_huge_and_tiny_weights_neither_overflow_nor_give_nan():
    rng = np.random.default_rng(4)
    reference, query = random_features(rng, 6), random_features(rng, 5)
    base = cost_matrix(reference, query, min_visible=1)
    huge = cost_matrix(reference, query, min_visible=1, weights={u.name: 1e308 for u in reference.units})
    tiny = cost_matrix(reference, query, min_visible=1, weights={u.name: 5e-324 for u in reference.units})
    for scaled in (huge, tiny):
        assert not np.isnan(scaled.values).any()
        np.testing.assert_allclose(scaled.values, base.values, rtol=1e-12, atol=0.0)
    # a positive weight so far below the largest that its share is 0 would divide by 0 in a cell that only it covers
    with pytest.raises(CompareError, match="weights"):
        cost_matrix(reference, query, min_visible=1, weights={"LWrist": 1e10, "RWrist": 5e-324})


FINITE = "must be a finite number of 0 or more"
NOT_A_UNIT = "is not the name of a unit"
ALL_UNITS = ("LShoulder", "LWrist", "RWrist", "LKnee", "l_forearm", "trunk")


class UnhashableKey(Mapping):
    """A mapping that breaks the contract of a mapping: its key is a list (a dict could not hold it)."""

    def __getitem__(self, key):
        return 1.0

    def __iter__(self):
        return iter([["LWrist"]])

    def __len__(self):
        return 1


@pytest.mark.parametrize(
    ("weights", "reason"),
    [
        pytest.param({"NotAUnit": 1.0}, NOT_A_UNIT, id="unknown name"),
        pytest.param({"LWrist": 1.0, "lwrist": 1.0}, NOT_A_UNIT, id="a name in the wrong case"),
        pytest.param({3: 1.0}, NOT_A_UNIT, id="a key that is not a string"),
        pytest.param(UnhashableKey(), NOT_A_UNIT, id="a key that cannot be hashed"),
        pytest.param({"LWrist": -1.0}, FINITE, id="negative"),
        pytest.param({"LWrist": -0.0001}, FINITE, id="a little negative"),
        pytest.param({"LWrist": float("nan")}, FINITE, id="NaN"),
        pytest.param({"LWrist": INF}, FINITE, id="infinity"),
        pytest.param({"LWrist": -INF}, FINITE, id="minus infinity"),
        pytest.param({"LWrist": True}, FINITE, id="a boolean"),
        pytest.param({"LWrist": "1"}, FINITE, id="a string"),
        pytest.param({"LWrist": None}, FINITE, id="None"),
        pytest.param({"LWrist": [1.0]}, FINITE, id="a list"),
        pytest.param({"LWrist": 10**400}, FINITE, id="an integer too large for a float"),
        pytest.param({u: 0.0 for u in ALL_UNITS}, "at most the number of units with a weight above 0", id="all zero"),
        pytest.param([("LWrist", 1.0)], "must be None or a mapping", id="not a mapping: a list"),
        pytest.param((1.0,) * U5, "must be None or a mapping", id="not a mapping: a tuple of numbers"),
        pytest.param("LWrist", "must be None or a mapping", id="not a mapping: a string"),
        pytest.param(np.ones(U5), "must be None or a mapping", id="not a mapping: an array"),
    ],
)
def test_t_cmp_02d_a_bad_weights_argument_is_refused_for_its_own_reason(weights, reason):
    rng = np.random.default_rng(0)
    reference, query = random_features(rng, 4), random_features(rng, 3)
    with pytest.raises(CompareError, match="weights") as caught:
        cost_matrix(reference, query, min_visible=1, weights=weights)
    assert reason in str(caught.value)  # the message of this check and not of another guard that also refuses it


def test_t_cmp_02d_the_refusal_names_the_argument_and_never_echoes_the_callers_text():
    rng = np.random.default_rng(0)
    reference, query = random_features(rng, 4), random_features(rng, 3)
    secret = "secret-participant-name"
    for weights in ({secret: 1.0}, {"LWrist": secret}, secret):
        with pytest.raises(CompareError) as caught:
            cost_matrix(reference, query, min_visible=1, weights=weights)
        assert "weights" in str(caught.value) and secret not in str(caught.value)


# --- T-CMP-02e: identical features, symmetry ------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_t_cmp_02e_identical_features_have_a_zero_diagonal_wherever_enough_units_are_valid(seed):
    rng = np.random.default_rng(seed)
    f = random_features(rng, 12, p_invalid=0.45)
    cm = cost_matrix(f, f, min_visible=4)
    enough = f.valid.sum(axis=1) >= 4
    assert enough.any() and not enough.all()  # the masks reach both sides of the threshold
    diagonal = np.diagonal(cm.values)
    assert (diagonal[enough] == 0.0).all()  # exactly 0, not 1e-17
    assert np.isposinf(diagonal[~enough]).all()  # a frame with too few units is not comparable even with itself
    assert np.array_equal(np.isfinite(cm.values), cm.n_common >= 4)  # and off the diagonal the count decides alone
    assert np.array_equal(np.diagonal(cm.n_common), f.valid.sum(axis=1))
    other = random_features(rng, 12, p_invalid=0.0)
    assert (cost_matrix(f, other, min_visible=2).values[np.arange(12), np.arange(12)] > 0.0).all()  # not always 0


@pytest.mark.parametrize("seed", SEEDS)
def test_t_cmp_02e_swapping_reference_and_query_transposes_the_matrix(seed):
    rng = np.random.default_rng(seed)
    a, b = random_features(rng, 9), random_features(rng, 5, recording_id=RECORDING_QRY)
    weights = {"LWrist": 2.0, "trunk": 0.5, "LKnee": 0.0}
    forward = cost_matrix(a, b, min_visible=2, weights=weights)  # reference a (9), query b (5): shape (5, 9)
    backward = cost_matrix(b, a, min_visible=2, weights=weights)  # reference b, query a: shape (9, 5)
    assert forward.values.shape == (5, 9) and backward.values.shape == (9, 5)
    assert np.array_equal(forward.values, backward.values.T) and np.array_equal(forward.n_common, backward.n_common.T)
    assert forward.reference_recording_id == RECORDING_REF and forward.query_recording_id == RECORDING_QRY
    assert backward.reference_recording_id == RECORDING_QRY and backward.query_recording_id == RECORDING_REF


# --- T-CMP-02f: blocks, empty segments, size ------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_t_cmp_02f_the_matrix_does_not_depend_on_block_rows(seed):
    rng = np.random.default_rng(seed)
    reference, query = random_features(rng, 23), random_features(rng, 30)
    whole = cost_matrix(reference, query, min_visible=2, block_rows=30)
    for block_rows in (1, 2, 7, 29, 31, 64, 10_000, np.int64(5)):
        other = cost_matrix(reference, query, min_visible=2, block_rows=block_rows)
        assert np.array_equal(other.values, whole.values) and np.array_equal(other.n_common, whole.n_common)
    assert np.array_equal(
        cost_matrix(reference, query, min_visible=2).values, whole.values
    )  # the default is a block size
    check(whole, reference, query, min_visible=2)  # and the one value is the right one


def test_t_cmp_02f_empty_segments_give_empty_matrices_of_the_right_shape():
    rng = np.random.default_rng(0)
    full, none = random_features(rng, 5), random_features(rng, 0)
    assert none.values.shape == (0, U5, 2)
    for reference, query, shape in ((full, none, (0, 5)), (none, full, (5, 0)), (none, none, (0, 0))):
        cm = cost_matrix(reference, query, min_visible=1)
        assert cm.values.shape == cm.n_common.shape == shape
        assert cm.values.dtype == np.float64 and cm.n_common.dtype == np.int16
        assert not cm.values.flags.writeable and not cm.n_common.flags.writeable


@pytest.mark.parametrize(
    "block_rows",
    [0, -1, 1.0, 2.5, True, "8", None, float("nan"), np.float64(4.0), [4]],
)
def test_t_cmp_02f_block_rows_must_be_an_integer_of_at_least_one(block_rows):
    rng = np.random.default_rng(0)
    reference, query = random_features(rng, 4), random_features(rng, 3)
    with pytest.raises(CompareError, match="block_rows"):
        cost_matrix(reference, query, min_visible=1, block_rows=block_rows)


def long_features(seed: int, n: int = 900) -> FrameFeatures:
    return random_features(
        np.random.default_rng(seed), n, units=make_units(DEFAULT_JOINTS, DEFAULT_SEGMENTS), p_invalid=0.1
    )


def traced(f, *args, **kwargs):
    """``(result, seconds, peak megabytes of allocations made by the call)`` (numpy reports to ``tracemalloc``)."""
    tracemalloc.start()
    try:
        start = time.perf_counter()
        result = f(*args, **kwargs)
        seconds = time.perf_counter() - start
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return result, seconds, peak / 2**20


def test_t_cmp_02f_a_long_segment_is_done_by_blocks_and_never_builds_the_four_dimensional_array():
    reference, query = long_features(1), long_features(2)
    assert len(reference.units) == 21
    cm, seconds, peak_mb = traced(cost_matrix, reference, query, min_visible=4)
    full_array_mb = 900 * 900 * 21 * 2 * 8 / 2**20  # (n, m, U, 2) float64: 260 MB
    assert cm.values.shape == (900, 900) and cm.n_common.dtype == np.int16
    assert seconds < TIMING_BOUND_S and peak_mb < MEMORY_BOUND_MB < full_array_mb
    assert np.isfinite(cm.values).mean() > 0.99  # 10 % invalid units, 4 needed of 21: almost every cell is a value


def test_t_cmp_02f_the_memory_is_that_of_a_block_of_rows_not_of_the_whole_matrix():
    reference, query = long_features(3, 300), long_features(4, 300)
    _, _, small = traced(cost_matrix, reference, query, min_visible=4, block_rows=8)
    _, _, large = traced(cost_matrix, reference, query, min_visible=4, block_rows=300)
    assert small * 4 < large  # the blocks, not the matrix, set the size of the temporary arrays


# --- T-CMP-02g: refusals --------------------------------------------------------------------------------------------
def make_pair(**changes) -> tuple[FrameFeatures, FrameFeatures]:
    rng = np.random.default_rng(0)
    reference, query = random_features(rng, 4), random_features(rng, 3)
    return reference, dataclasses.replace(query, **changes)


def test_t_cmp_02g_two_feature_sets_with_different_units_are_refused_and_never_intersected():
    reference, query = make_pair()
    names = [u.name for u in reference.units]
    cases = {
        "fewer units": (
            reference,
            make_features(query.values[:, :5], query.valid[:, :5], make_units(POSITIONS, ANGLES[:1])),
        ),
        "other order": (reference, make_features(query.values[:, ::-1], query.valid[:, ::-1], reference.units[::-1])),
        "other name": (
            reference,
            make_features(query.values, query.valid, make_units(("RKnee", *POSITIONS[1:]), ANGLES)),
        ),
        "other kind": (
            reference,
            dataclasses.replace(
                query,
                units=(*query.units[:4], FeatureUnit("position", "l_forearm", query.units[4].joints), query.units[5]),
            ),
        ),
        "other joints": (
            reference,
            dataclasses.replace(query, units=(*query.units[:5], FeatureUnit("angle", "trunk", (11, 12, 5)))),
        ),
        "more units": (
            reference,
            make_features(
                np.concatenate([query.values, query.values[:, :1]], axis=1),
                np.concatenate([query.valid, query.valid[:, :1]], axis=1),
                (*query.units, FeatureUnit("position", "RKnee", (IDX["RKnee"],))),
            ),
        ),
    }
    assert names == [u.name for u in query.units]
    for ref, qry in cases.values():
        with pytest.raises(CompareError, match="units"):
            cost_matrix(ref, qry, min_visible=1)
        with pytest.raises(CompareError, match="units"):
            cost_matrix(qry, ref, min_visible=1)  # in both orders: the check is symmetric


def test_t_cmp_02g_two_feature_sets_of_different_versions_are_refused():
    reference, query = make_pair(version="2")
    for ref, qry in ((reference, query), (query, reference)):
        with pytest.raises(CompareError, match="version"):
            cost_matrix(ref, qry, min_visible=1)
    assert cost_matrix(*make_pair(version="1"), min_visible=1).feature_version == "1"


@pytest.mark.parametrize(
    "min_visible",
    [0, -1, U5 + 1, 100, 1.0, 2.5, True, False, "2", None, float("nan"), np.float64(2.0), [2]],
)
def test_t_cmp_02g_min_visible_must_be_an_integer_from_one_to_the_number_of_weighted_units(min_visible):
    reference, query = make_pair()
    with pytest.raises(CompareError, match="min_visible"):
        cost_matrix(reference, query, min_visible=min_visible)


def test_t_cmp_02g_min_visible_counts_the_units_that_have_a_weight_and_nothing_else():
    reference, query = make_pair()
    assert cost_matrix(reference, query, min_visible=U5).min_visible == U5  # every unit: allowed
    assert cost_matrix(reference, query, min_visible=np.int64(3)).min_visible == 3
    assert type(cost_matrix(reference, query, min_visible=np.int64(3)).min_visible) is int
    zero_two = {"LWrist": 0.0, "trunk": 0.0}
    assert cost_matrix(reference, query, min_visible=U5 - 2, weights=zero_two).min_visible == U5 - 2
    with pytest.raises(CompareError, match="min_visible"):
        cost_matrix(reference, query, min_visible=U5 - 1, weights=zero_two)  # only U5 - 2 units have a weight


def test_t_cmp_02g_min_visible_has_no_default():
    reference, query = make_pair()
    with pytest.raises(TypeError):
        cost_matrix(reference, query)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        cost_matrix(reference, query, 2)  # type: ignore[misc]  # keyword only


@pytest.mark.parametrize("bad", [None, 3, "features", {"values": 1}, np.zeros((3, 6, 2)), [1, 2]], ids=repr)
def test_t_cmp_02g_the_arguments_must_be_frame_features(bad):
    reference, query = make_pair()
    with pytest.raises(CompareError, match="^reference must be a FrameFeatures"):
        cost_matrix(bad, query, min_visible=1)
    with pytest.raises(CompareError, match="^query must be a FrameFeatures"):
        cost_matrix(reference, bad, min_visible=1)


def test_t_cmp_02g_the_refusals_name_the_argument_and_never_echo_a_string_of_the_caller():
    reference, query = make_pair()
    secret = "secret-participant-name"
    calls = [
        lambda: cost_matrix(secret, query, min_visible=1),
        lambda: cost_matrix(reference, secret, min_visible=1),
        lambda: cost_matrix(reference, query, min_visible=secret),
        lambda: cost_matrix(reference, query, min_visible=1, block_rows=secret),
        lambda: cost_matrix(reference, dataclasses.replace(query, version=secret), min_visible=1),
        lambda: cost_matrix(
            reference,
            dataclasses.replace(query, units=(*query.units[:5], FeatureUnit("angle", secret, (5,)))),
            min_visible=1,
        ),
    ]
    for call in calls:
        with pytest.raises(CompareError) as caught:
            call()
        assert secret not in str(caught.value) and str(caught.value)


def test_t_cmp_02g_features_that_break_their_own_contract_are_refused_so_that_nan_never_reaches_the_matrix():
    reference, query = make_pair()
    row, unit = (int(a[0]) for a in np.nonzero(query.valid))  # the first cell that says it is valid
    nan_valid = query.values.copy()
    nan_valid[row, unit, 0] = np.nan  # a feature that says it is valid and has no value
    shape = "values must be a floating-point array of shape"
    broken = {  # the features, and the words of the check that must be the one that refuses them
        "a valid cell with NaN": (dataclasses.replace(query, values=nan_valid), "a valid feature has a non-finite"),
        "a valid cell with inf": (
            dataclasses.replace(query, values=np.where(query.valid[..., None], np.inf, query.values)),
            "a valid feature has a non-finite",
        ),
        "values of two dimensions": (dataclasses.replace(query, values=query.values[..., 0]), shape),
        "values of the wrong width": (
            dataclasses.replace(query, values=np.concatenate([query.values, query.values], axis=2)),
            shape,
        ),
        "values that are not floats": (
            dataclasses.replace(query, values=np.zeros(query.values.shape, dtype=np.int64)),
            shape,
        ),
        "valid of the wrong shape": (
            dataclasses.replace(query, valid=query.valid[:, :4]),
            "valid must be a bool array",
        ),
        "valid with other rows": (dataclasses.replace(query, valid=query.valid[:2]), "valid must be a bool array"),
        "valid that is not bool": (
            dataclasses.replace(query, valid=query.valid.astype(np.int8)),
            "valid must be a bool array",
        ),
        "units of another count": (
            dataclasses.replace(query, units=query.units[:5]),
            "units must have one entry per column",
        ),
        "units that are not a tuple": (
            dataclasses.replace(query, units=list(query.units)),  # type: ignore[arg-type]
            "units must be a tuple of FeatureUnit",
        ),
        "units that are not FeatureUnit": (
            dataclasses.replace(query, units=(*query.units[:5], "trunk")),  # type: ignore[arg-type]
            "units must be a tuple of FeatureUnit",
        ),
        "a name twice (a weight is given by name)": (
            dataclasses.replace(query, units=(*query.units[:5], query.units[0])),
            "units must have distinct names",
        ),
    }
    for qry, words in broken.values():
        with pytest.raises(CompareError, match=rf"^query[.:] ?{words}"):
            cost_matrix(reference, qry, min_visible=1)
        with pytest.raises(CompareError, match=rf"^reference[.:] ?{words}"):
            cost_matrix(qry, reference, min_visible=1)  # the same check on the reference


# --- T-CMP-02h: never NaN, read-only arrays, inputs unchanged -------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_t_cmp_02h_the_values_are_never_nan_whatever_the_masks_and_the_weights(seed):
    rng = np.random.default_rng(seed)
    for p_invalid in (0.0, 0.5, 0.9, 1.0):
        reference, query = random_features(rng, 9, p_invalid=p_invalid), random_features(rng, 8, p_invalid=p_invalid)
        for min_visible, weights in ((1, None), (3, {"LWrist": 0.0}), (2, {"trunk": 1e-9, "LKnee": 1e9})):
            cm = strict_cost(reference, query, min_visible=min_visible, weights=weights)
            assert not np.isnan(cm.values).any()
            # a distance: 0 or more, finite or +inf; and a cell is a number or +inf by the count alone
            assert (cm.values >= 0.0).all() and not np.isneginf(cm.values).any()
            assert (np.isfinite(cm.values) == (cm.n_common >= min_visible)).all()
    assert np.isposinf(cost_matrix(reference, query, min_visible=1).values).all()  # p_invalid 1: nothing is comparable


def test_t_cmp_02h_the_result_arrays_are_new_read_only_and_of_the_documented_dtype():
    rng = np.random.default_rng(0)
    reference, query = random_features(rng, 6, frozen=True), random_features(rng, 5, frozen=True)
    cm = cost_matrix(reference, query, min_visible=2)
    assert cm.values.dtype == np.float64 and cm.n_common.dtype == np.int16
    assert cm.values.shape == cm.n_common.shape == (5, 6)
    for a in (cm.values, cm.n_common):
        assert not a.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            a[0, 0] = 1
        assert not np.shares_memory(a, reference.values) and not np.shares_memory(a, query.values)
    assert not np.shares_memory(cm.values, cm.n_common)
    again = cost_matrix(reference, query, min_visible=2)
    assert again.values is not cm.values and np.array_equal(again.values, cm.values)  # a call gives its own arrays


def test_t_cmp_02h_the_inputs_are_not_changed():
    rng = np.random.default_rng(1)
    reference, query = random_features(rng, 7), random_features(rng, 6)  # writable on purpose: any write would show
    snapshots = [
        (f.values.copy(), f.valid.copy(), f.reason.copy(), f.bridged.copy(), f.t_sec.copy(), f.units)
        for f in (reference, query)
    ]
    weights = {"LWrist": 2.0, "trunk": 0.0}
    cost_matrix(reference, query, min_visible=2, weights=weights, block_rows=3)
    assert weights == {"LWrist": 2.0, "trunk": 0.0}
    for f, (values, valid, reason, bridged, t_sec, units) in zip((reference, query), snapshots, strict=True):
        np.testing.assert_array_equal(f.values, values)  # NaN equal to NaN
        assert (
            np.array_equal(f.valid, valid) and np.array_equal(f.reason, reason) and np.array_equal(f.bridged, bridged)
        )
        assert np.array_equal(f.t_sec, t_sec) and f.units is units and f.version == "1"
        assert f.values.flags.writeable  # and the flags are what they were


def test_t_cmp_02h_the_result_echoes_what_made_it_and_is_frozen():
    rng = np.random.default_rng(2)
    reference = random_features(rng, 4, recording_id=RECORDING_REF)
    query = random_features(rng, 3, recording_id=RECORDING_QRY)
    cm = cost_matrix(reference, query, min_visible=np.int64(2), weights={"LKnee": 4.0})
    assert isinstance(cm, CostMatrix)
    assert (
        cm.units
        == tuple(u.name for u in reference.units)
        == ("LShoulder", "LWrist", "RWrist", "LKnee", "l_forearm", "trunk")
    )
    assert all(type(name) is str for name in cm.units)
    assert cm.weights == (1.0, 1.0, 1.0, 4.0, 1.0, 1.0) and cm.min_visible == 2
    assert cm.reference_recording_id == RECORDING_REF and cm.query_recording_id == RECORDING_QRY
    assert cm.feature_version == reference.version == "1"
    with pytest.raises(dataclasses.FrozenInstanceError):
        cm.min_visible = 3  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        cm.values = cm.values  # type: ignore[misc]


# --- the contract with P6.03a ---------------------------------------------------------------------------------------
def test_t_cmp_02_the_matrix_is_accepted_by_dtw_through_its_values():
    rng = np.random.default_rng(5)
    reference, query = random_features(rng, 12, p_invalid=0.1), random_features(rng, 10, p_invalid=0.1)
    cm = cost_matrix(reference, query, min_visible=3)
    assert np.isfinite(cm.values).all()
    for step in ("symmetric1", "symmetricP1"):
        from_matrix, from_values = dtw(cm, band=1.0, step=step), dtw(cm.values, band=1.0, step=step)
        assert from_matrix.status == from_values.status == "ok"
        assert np.array_equal(from_matrix.path, from_values.path) and from_matrix.distance == from_values.distance
        assert from_matrix.path[0].tolist() == [0, 0] and from_matrix.path[-1].tolist() == [9, 11]  # (query, reference)
        assert from_matrix.params["n"] == 10 and from_matrix.params["m"] == 12  # n rows are the query
