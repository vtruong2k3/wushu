"""T-CMP-06b to T-CMP-06h: the local tempo along the path and the deviation of each unit (P6.04, W8, Appendix C.4).

``local_tempo`` fits a line to the matched query time against the reference's real clock over a window of ``smooth_s``
seconds; ``deviation_curve`` gives, for each reference row and unit, how far the matched query frames are from the
reference frame. Alignments are built by hand (clocks, paths, features), so a test controls every number; the expected
values are re-derived here by plain loops and ``statistics.linear_regression`` (an implementation of the least-squares
slope that the module under test does not use), never by calling the module's own helpers. The generator and the real
chain are in ``tests/golden/test_compare_tempo_ratio_syn.py`` (T-CMP-06).

* T-CMP-06b: a constant warp gives the same ratio wherever the window holds two rows.
* T-CMP-06c: an uneven clock gives the slope in seconds, not in rows.
* T-CMP-06d: horizontal and vertical runs; the whole-segment ratio.
* T-CMP-06e: the deviation of each unit.
* T-CMP-06f: a window that is too small and no path give NaN with a reason, never 0.
* T-CMP-06g: refusals.
* T-CMP-06h: read-only arrays, inputs unchanged.
"""

from __future__ import annotations

import dataclasses
import math
import statistics
import warnings
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import numpy as np
import pytest

from helpers.compare_cost_ref import (
    ANGLES,
    POSITIONS,
    RECORDING_QRY,
    RECORDING_REF,
    chord,
    make_features,
    make_units,
    random_features,
)
from taiji_ai.compare import CompareError
from taiji_ai.compare.align import Alignment, align
from taiji_ai.compare.cost import CostMatrix
from taiji_ai.compare.features import FrameFeatures
from taiji_ai.compare.tempo_ratio import (
    DeviationCurve,
    DeviationReason,
    TempoCurve,
    TempoReason,
    deviation_curve,
    local_tempo,
)

EDGE_S = 1e-9  # the tolerance of the window's edge, as the task file (section 2.6) writes it
UNIT_NAMES = (*POSITIONS, *ANGLES)
BIG = 10**400  # far above the largest float


@contextmanager
def no_warnings() -> Iterator[None]:
    """A division by zero or a NaN comparison would warn: the tests that use this must not produce one."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        yield


def line(xs: Sequence[float], t: Sequence[float] | None = None) -> FrameFeatures:
    """One position unit that moves along x (trunk lengths): a hand-made segment whose cost is ``|x_q - x_r|``."""
    values = np.zeros((len(xs), 1, 2))
    values[:, 0, 0] = xs
    features = make_features(values, np.ones((len(xs), 1), dtype=bool), make_units(("LWrist",), ()))
    return features if t is None else dataclasses.replace(features, t_sec=np.asarray(t, dtype=np.float64))


def with_path(a: Alignment, path: Sequence[Sequence[int]]) -> Alignment:
    """``a`` with the given path (cells ``(query row, reference row)``), the status ``ok`` and nothing else changed."""
    cells = np.array(path, dtype=np.int64).reshape(-1, 2)
    cells.setflags(write=False)
    return dataclasses.replace(a, result=dataclasses.replace(a.result, path=cells, status="ok"))


def made(ref_t: Sequence[float], query_t: Sequence[float], path: Sequence[Sequence[int]]) -> Alignment:
    """An alignment of one position unit (every cost 0) whose two real clocks and whose path are the given ones."""
    base = align(
        line(np.zeros(len(ref_t)), ref_t), line(np.zeros(len(query_t)), query_t), min_visible=1, band=1.0,
        step="symmetric1",
    )  # fmt: skip
    return with_path(base, path)


def diagonal(n: int) -> list[list[int]]:
    return [[i, i] for i in range(n)]


def refusal(function, *args, **kwargs) -> str:
    """The message of the ``CompareError`` that ``function`` raises (the test fails if it raises nothing else)."""
    with pytest.raises(CompareError) as caught:
        function(*args, **kwargs)
    return str(caught.value)


# --- the expected values, by plain loops ------------------------------------------------------------------------------
def expected_tau(query_t: Sequence[float], path: Sequence[Sequence[int]], m: int) -> list[float]:
    """The mean query time of the path cells on every reference row; NaN for a row with no cell."""
    tau = []
    for k in range(m):
        times = [query_t[i] for i, kk in path if kk == k]
        tau.append(sum(times) / len(times) if times else math.nan)
    return tau


def expected_ratio(t_ref: Sequence[float], tau: Sequence[float], smooth_s: float) -> tuple[list[float], list[int]]:
    """``(ratio, window rows)`` per reference row: the least-squares slope of tau against t_ref over the rows with
    ``|t_ref(j) - t_ref(k)| <= smooth_s / 2`` and an observed tau; NaN for fewer than two such rows."""
    ratio, rows = [], []
    for k in range(len(t_ref)):
        window = [
            j
            for j in range(len(t_ref))
            if abs(t_ref[j] - t_ref[k]) <= smooth_s / 2.0 + EDGE_S and not math.isnan(tau[j])
        ]
        rows.append(len(window))
        if len(window) < 2:
            ratio.append(math.nan)
        else:
            ratio.append(statistics.linear_regression([t_ref[j] for j in window], [tau[j] for j in window]).slope)
    return ratio, rows


def expected_deviation(
    reference: FrameFeatures, query: FrameFeatures, path: Sequence[Sequence[int]]
) -> tuple[np.ndarray, np.ndarray]:
    """``(mean distance (m, U) with NaN where no cell has the unit valid in both, cell count (m, U))`` by loops: a
    position's distance is the norm of the difference of the stored vectors, an angle's the chord of the two angles."""
    m, units = reference.valid.shape
    total, count = np.zeros((m, units)), np.zeros((m, units), dtype=np.int64)
    for i, k in path:
        for u, unit in enumerate(reference.units):
            if not (query.valid[i, u] and reference.valid[k, u]):
                continue
            a, b = query.values[i, u].tolist(), reference.values[k, u].tolist()
            total[k, u] += chord(a, b) if unit.kind == "angle" else math.hypot(a[0] - b[0], a[1] - b[1])
            count[k, u] += 1
    return np.where(count > 0, total / np.maximum(count, 1), math.nan), count


def assert_same(got: np.ndarray, want: Sequence[float] | np.ndarray, *, tol: float = 1e-12) -> None:
    """Equal where finite (to ``tol``) and NaN in the same places."""
    got, want = np.asarray(got, dtype=np.float64), np.asarray(want, dtype=np.float64)
    assert got.shape == want.shape
    assert np.array_equal(np.isnan(got), np.isnan(want))
    assert np.allclose(got[~np.isnan(got)], want[~np.isnan(want)], rtol=0.0, atol=tol)


# --- T-CMP-06b: a constant warp ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("factor", "offset"),
    [
        pytest.param(2.0, 0.0, id="the query takes twice as long"),
        pytest.param(0.5, 0.0, id="the query is twice as fast"),
        pytest.param(2.0, 0.3, id="twice as long and starts later"),
        pytest.param(1.0, 0.0, id="the same tempo"),
    ],
)
def test_t_cmp_06b_a_constant_warp_gives_the_same_ratio_on_every_row_where_the_window_holds_two_rows(factor, offset):
    ref_t = np.arange(21) * 0.1
    query_t = factor * ref_t + offset
    with no_warnings():
        got = local_tempo(made(ref_t, query_t, diagonal(21)), smooth_s=0.5)
    assert isinstance(got, TempoCurve) and got.status == "ok" and got.smooth_s == 0.5
    assert np.allclose(got.ratio, factor, rtol=0.0, atol=1e-9)  # every row, the edges (windows of 3 and 4 rows) too
    assert (got.reason == TempoReason.valid).all()
    assert got.window_rows.tolist() == [3, 4, *([5] * 17), 4, 3]  # |dt| <= 0.25 s on a 0.1 s clock: 2 rows each side
    assert np.array_equal(got.t_ref, ref_t) and np.allclose(got.t_query, query_t, atol=1e-12)
    assert got.whole_ratio == pytest.approx(factor, abs=1e-12) and got.whole_reason == TempoReason.valid


def test_t_cmp_06b_two_query_rows_for_every_reference_row_make_a_ratio_of_two_where_the_windows_avoid_the_end():
    ref_t, query_t = np.arange(11) * 0.1, np.arange(21) * 0.1  # the query has twice as many rows at the same step
    path = [[i, i // 2] for i in range(20)] + [[20, 10]]  # vertical runs of two rows on rows 0 to 9
    made_path = made(ref_t, query_t, path)
    got = local_tempo(made_path, smooth_s=0.5)
    tau = expected_tau(query_t, path, 11)
    assert tau[:10] == pytest.approx([0.2 * k + 0.05 for k in range(10)], abs=1e-12)  # the mean of two query times
    assert np.allclose(got.t_query, tau, atol=1e-12)
    assert np.allclose(got.ratio[:8], 2.0, atol=1e-9)  # windows of rows 0 to 9: a straight line of slope 2
    want, rows = expected_ratio(ref_t, tau, 0.5)
    assert_same(got.ratio, want, tol=1e-9)
    assert got.window_rows.tolist() == rows
    assert abs(got.ratio[10] - 2.0) > 0.1  # the last row is on its own: one query row (not two) is its mean


# --- T-CMP-06c: an uneven clock ---------------------------------------------------------------------------------------
STEPS = [
    0.03,
    0.04,
    0.03,
    0.12,
    0.03,
    0.03,
    0.07,
    0.03,
    0.03,
    0.2,
    0.03,
    0.04,
    0.03,
    0.03,
    0.05,
    0.03,
]  # dropped frames


def test_t_cmp_06c_an_uneven_clock_gives_the_slope_in_seconds_not_in_rows():
    ref_t = np.concatenate([[0.0], np.cumsum(STEPS)])  # 17 rows on a VFR-like clock
    query_t = 1.5 * ref_t + 0.2  # a constant warp in seconds along the diagonal
    got = local_tempo(made(ref_t, query_t, diagonal(17)), smooth_s=0.4)
    assert np.allclose(got.ratio, 1.5, atol=1e-9)  # the slope in seconds: the same on every row
    index_slope = np.gradient(got.t_query)  # what a regression on row indices would give: the local step, not the tempo
    assert not np.allclose(index_slope, 1.5, atol=0.1) and index_slope.max() < 0.4
    _, rows = expected_ratio(ref_t, expected_tau(query_t, diagonal(17), 17), 0.4)
    assert got.window_rows.tolist() == rows and len(set(rows)) > 3  # the window is a span of seconds, not a row count


def test_t_cmp_06c_a_changing_warp_on_an_uneven_reference_clock_is_the_least_squares_slope_of_each_window():
    ref_t = np.concatenate([[0.0], np.cumsum(STEPS)])
    query_t = 0.5 * ref_t + ref_t**2  # d t_query / d t_ref = 0.5 + 2 t: a tempo that changes along the segment
    for smooth_s in (0.25, 0.4, 0.9):
        got = local_tempo(made(ref_t, query_t, diagonal(17)), smooth_s=smooth_s)
        want, rows = expected_ratio(ref_t, query_t, smooth_s)
        assert_same(got.ratio, want, tol=1e-9)
        assert got.window_rows.tolist() == rows


def test_t_cmp_06c_an_uneven_query_clock_on_an_even_reference_clock_gives_the_ratio_of_the_local_steps():
    ref_t = np.arange(13) * 0.1
    steps = np.array([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2])  # the query slows down by half
    query_t = np.concatenate([[0.0], np.cumsum(steps)])
    got = local_tempo(made(ref_t, query_t, diagonal(13)), smooth_s=0.3)  # three rows: slope (y2 - y0) / (2 h)
    assert got.ratio[:5].tolist() == pytest.approx([1.0] * 5, abs=1e-9)  # windows inside the first half
    assert got.ratio[8:12].tolist() == pytest.approx([2.0] * 4, abs=1e-9)  # windows inside the second half
    assert (query_t[7] - query_t[5]) / 0.2 == pytest.approx(1.5, abs=1e-9)  # by hand: the slope over rows 5 to 7
    assert got.ratio[6] == pytest.approx(1.5, abs=1e-9)


def test_t_cmp_06c_a_window_edge_is_inclusive_and_a_clock_that_is_not_exact_does_not_change_the_window():
    exact = np.arange(9) * 0.125  # exact in binary: half of 0.5 s is exactly two rows
    got = local_tempo(made(exact, exact * 2.0, diagonal(9)), smooth_s=0.5)
    assert got.window_rows.tolist() == [3, 4, 5, 5, 5, 5, 5, 4, 3]  # a row exactly 0.25 s away is in the window
    inexact = np.arange(9) * 0.1  # 0.1 * 3 - 0.1 * 2 is not exactly 0.1: the edge must not depend on that
    got = local_tempo(made(inexact, inexact * 2.0, diagonal(9)), smooth_s=0.2)  # half is 0.1: one row each side
    assert got.window_rows.tolist() == [2, 3, 3, 3, 3, 3, 3, 3, 2]
    third = np.arange(12) / 30.0  # a 30 fps grid: 3 / 30 is 0.1
    got = local_tempo(made(third, third * 2.0, diagonal(12)), smooth_s=0.2)
    assert got.window_rows.tolist() == [4, 5, 6, 7, 7, 7, 7, 7, 7, 6, 5, 4]  # |dt| <= 0.1 s: 3 rows each side
    just_out = local_tempo(made(exact, exact, diagonal(9)), smooth_s=0.4999)  # a hair under the edge: out
    assert just_out.window_rows[4] == 3


def test_t_cmp_06c_a_window_as_wide_as_the_segment_gives_one_line_through_every_row():
    ref_t = np.concatenate([[0.0], np.cumsum(STEPS)])
    query_t = 0.5 * ref_t + ref_t**2
    got = local_tempo(made(ref_t, query_t, diagonal(17)), smooth_s=1e300)  # no overflow in the edges of the window
    whole = np.polyfit(ref_t, query_t, 1)[0]  # an independent least-squares line through all 17 rows
    assert got.window_rows.tolist() == [17] * 17 and np.allclose(got.ratio, whole, atol=1e-9)


# --- T-CMP-06d: horizontal and vertical runs; the whole-segment ratio -------------------------------------------------
RUN_PATH = [[0, 0], [1, 0], [2, 1], [3, 2], [3, 3], [3, 4], [4, 5], [5, 5], [6, 6], [7, 7]]
RUN_QUERY_T = [0.0, 0.1, 0.35, 0.5, 0.52, 0.9, 1.0, 1.6]  # uneven: the matched time is read in seconds
RUN_TAU = [0.05, 0.35, 0.5, 0.5, 0.5, 0.71, 1.0, 1.6]  # (0 + 0.1) / 2, ..., three rows on query row 3, (0.52 + 0.9) / 2
RUN_RATIO = [
    3.0,
    2.25,
    0.75,
    0.0,
    1.05,
    2.5,
    4.45,
    6.0,
]  # the three-point slope (y2 - y0) / 0.2; two points at the ends


def test_t_cmp_06d_runs_of_the_path_give_the_mean_matched_time_and_the_ratio_of_each_window_by_hand():
    ref_t = np.arange(8) * 0.1
    a = made(ref_t, RUN_QUERY_T, RUN_PATH)
    got = local_tempo(a, smooth_s=0.3)  # half 0.15 s: one row each side
    assert expected_tau(RUN_QUERY_T, RUN_PATH, 8) == pytest.approx(RUN_TAU, abs=1e-12)
    assert np.allclose(got.t_query, RUN_TAU, atol=1e-12) and np.array_equal(got.t_query, a.matched_query_times())
    assert got.ratio.tolist() == pytest.approx(RUN_RATIO, abs=1e-9)  # hand-made numbers
    assert got.window_rows.tolist() == [2, 3, 3, 3, 3, 3, 3, 2]
    assert got.ratio[3] == 0.0 and got.reason[3] == TempoReason.valid  # the query stood still: a measurement, not a gap
    assert (got.reason == TempoReason.valid).all()
    want, rows = expected_ratio(ref_t, RUN_TAU, 0.3)
    assert_same(got.ratio, want, tol=1e-9)
    assert got.window_rows.tolist() == rows
    assert got.whole_ratio == pytest.approx(1.6 / 0.7, abs=1e-12) and got.whole_reason == TempoReason.valid


def test_t_cmp_06d_the_whole_segment_ratio_is_read_from_the_two_clocks_not_from_the_matched_times():
    ref_t = np.arange(8) * 0.1
    got = local_tempo(made(ref_t, RUN_QUERY_T, RUN_PATH), smooth_s=0.3)
    assert got.t_query[0] != RUN_QUERY_T[0] and got.t_query[-1] == RUN_QUERY_T[-1]  # the first row is a mean
    assert got.whole_ratio == pytest.approx((1.6 - 0.0) / (0.7 - 0.0), abs=1e-12)  # not (1.6 - 0.05) / 0.7
    other = made(np.array([5.0, 5.5, 7.0]), np.array([2.0, 2.25, 9.0, 11.0]), [[0, 0], [1, 1], [2, 1], [3, 2]])
    assert local_tempo(other, smooth_s=1.0).whole_ratio == pytest.approx((11.0 - 2.0) / (7.0 - 5.0), abs=1e-12)


def test_t_cmp_06d_a_query_that_stands_still_gives_zero_where_the_window_has_rows_and_no_whole_ratio():
    ref_t = np.arange(5) * 0.1
    path = [[0, 0], [0, 1], [0, 2], [0, 3], [0, 4]]  # one query row against five reference rows (horizontal run)
    one = made(ref_t, [3.0], path)
    got = local_tempo(one, smooth_s=0.3)
    assert got.t_query.tolist() == [3.0] * 5 and got.ratio.tolist() == [0.0] * 5  # tau does not change: slope 0
    assert (got.reason == TempoReason.valid).all()
    assert math.isnan(got.whole_ratio) and got.whole_reason == TempoReason.window_too_small  # one frame has no duration


def test_t_cmp_06d_the_real_alignment_of_a_stretched_ramp_gives_the_ratio_in_seconds():
    # query x 0 0 1 2 2 3 against reference x 0 1 2 3: the only path of cost 0 is (0,0) (1,0) (2,1) (3,2) (4,2) (5,3)
    reference = line([0.0, 1.0, 2.0, 3.0], t=[0.0, 0.2, 0.4, 0.6])
    query = line([0.0, 0.0, 1.0, 2.0, 2.0, 3.0], t=[0.0, 0.1, 0.3, 0.7, 0.8, 1.5])
    a = align(reference, query, min_visible=1, band=1.0, step="symmetric1")
    assert a.result.path.tolist() == [[0, 0], [1, 0], [2, 1], [3, 2], [4, 2], [5, 3]] and a.distance == 0.0
    got = local_tempo(a, smooth_s=0.5)  # half 0.25 s: one row each side
    assert got.t_query.tolist() == pytest.approx([0.05, 0.3, 0.75, 1.5], abs=1e-12)
    # by hand: (0.3 - 0.05) / 0.2, (0.75 - 0.05) / 0.4, (1.5 - 0.3) / 0.4, (1.5 - 0.75) / 0.2
    assert got.ratio.tolist() == pytest.approx([1.25, 1.75, 3.0, 3.75], abs=1e-9)
    assert got.whole_ratio == pytest.approx(1.5 / 0.6, abs=1e-12)


# --- T-CMP-06e: the deviation of each unit ----------------------------------------------------------------------------
def pair(seed: int, n: int = 10, m: int | None = None, **kwargs) -> tuple[FrameFeatures, FrameFeatures]:
    rng = np.random.default_rng(seed)
    reference = random_features(rng, n if m is None else m, **kwargs)
    query = random_features(rng, n, recording_id=RECORDING_QRY, **kwargs)
    return reference, query


def aligned_on_the_diagonal(reference: FrameFeatures, query: FrameFeatures, **kwargs) -> Alignment:
    """A real ``align`` (so the cost is the module's), with the path forced to the diagonal."""
    base = align(reference, query, **{"min_visible": 1, "band": 1.0, "step": "symmetric1", **kwargs})
    return with_path(base, diagonal(len(query.t_sec)))


def test_t_cmp_06e_identical_features_deviate_by_zero_and_a_unit_never_valid_is_nan_with_a_reason():
    rng = np.random.default_rng(1)
    reference = random_features(rng, 10, p_invalid=0.2)
    valid = reference.valid.copy()
    valid[:, 1] = False  # LWrist is never valid
    values = reference.values.copy()
    values[~valid] = math.nan
    reference = make_features(values, valid, reference.units)
    query = dataclasses.replace(reference, recording_id=RECORDING_QRY)
    a = align(reference, query, min_visible=1, band=1.0)
    assert a.result.status == "ok" and a.result.path.tolist() == diagonal(10)  # the real alignment is the diagonal
    with no_warnings():
        got = deviation_curve(a)
    assert isinstance(got, DeviationCurve) and got.status == "ok"
    assert (got.values[valid] == 0.0).all()  # the same feature against itself: exactly 0
    assert np.isnan(got.values[~valid]).all() and (got.reason[~valid] == DeviationReason.not_valid_in_both).all()
    assert (got.reason[valid] == DeviationReason.valid).all() and (got.n_valid == valid).all()
    assert np.isnan(got.values[:, 1]).all() and (got.n_valid[:, 1] == 0).all()
    assert np.isfinite(got.total).all() and (got.total == 0.0).all() and (got.cells == 1).all()


def test_t_cmp_06e_a_unit_that_is_changed_on_some_rows_deviates_only_there_by_the_amount_it_was_changed():
    rng = np.random.default_rng(2)
    reference = random_features(rng, 12, p_invalid=0.0)
    values = reference.values.copy()
    values[4:8, 1, 0] += 0.3  # LWrist (a position): 0.3 trunk lengths to the right on rows 4 to 7
    phi = np.arctan2(values[2:10, 5, 0], values[2:10, 5, 1]) + 0.5  # trunk (an angle): turned by 0.5 rad on rows 2 to 9
    values[2:10, 5] = np.stack([np.sin(phi), np.cos(phi)], axis=-1)
    query = make_features(values, reference.valid, reference.units, recording_id=RECORDING_QRY)
    a = aligned_on_the_diagonal(reference, query)
    got = deviation_curve(a)
    want, count = expected_deviation(reference, query, diagonal(12))
    assert_same(got.values, want, tol=1e-12)
    assert np.array_equal(got.n_valid, count)
    changed = np.zeros(12, dtype=bool)
    changed[4:8] = True
    assert got.values[changed, 1].tolist() == pytest.approx([0.3] * 4, abs=1e-12)
    assert (got.values[~changed, 1] == 0.0).all()  # only where it was changed
    turned = np.zeros(12, dtype=bool)
    turned[2:10] = True
    assert got.values[turned, 5].tolist() == pytest.approx(
        [2.0 * math.sin(0.25)] * 8, abs=1e-12
    )  # the chord of 0.5 rad
    assert (got.values[~turned, 5] == 0.0).all()
    for untouched in (0, 2, 3, 4):  # the other units are the same frames
        assert (got.values[:, untouched] == 0.0).all()
    assert got.units == UNIT_NAMES and got.kinds == ("position",) * 4 + ("angle",) * 2


def test_t_cmp_06e_a_unit_valid_in_both_on_some_rows_only_is_a_value_there_and_nan_with_a_reason_elsewhere():
    reference, query = pair(3, p_invalid=0.0)
    ref_valid, qry_valid = reference.valid.copy(), query.valid.copy()
    ref_valid[5:, 0] = False  # LShoulder: reference rows 0 to 4, query rows 3 to 9: valid in both on rows 3 and 4
    qry_valid[:3, 0] = False
    ref_valid[5:, 2] = False  # RWrist: valid in the reference on rows 0 to 4 only and in the query on rows 5 to 9 only
    qry_valid[:5, 2] = False
    reference = make_features(np.where(ref_valid[:, :, None], reference.values, np.nan), ref_valid, reference.units)
    query = make_features(
        np.where(qry_valid[:, :, None], query.values, np.nan), qry_valid, query.units, recording_id=RECORDING_QRY
    )
    a = aligned_on_the_diagonal(reference, query)
    got = deviation_curve(a)
    want, count = expected_deviation(reference, query, diagonal(10))
    assert_same(got.values, want, tol=1e-12)
    assert np.array_equal(got.n_valid, count)
    assert np.isfinite(got.values[3:5, 0]).all() and np.isnan(got.values[[0, 1, 2, 5, 6, 7, 8, 9], 0]).all()
    assert np.isnan(got.values[:, 2]).all() and (got.n_valid[:, 2] == 0).all()  # never valid in both: NaN, not 0
    assert (got.reason[:, 2] == DeviationReason.not_valid_in_both).all()
    assert (got.reason[3:5, 0] == DeviationReason.valid).all()
    assert (got.reason[np.isnan(got.values)] == DeviationReason.not_valid_in_both).all()
    assert (got.reason[~np.isnan(got.values)] == DeviationReason.valid).all()


def test_t_cmp_06e_runs_of_the_path_average_over_the_cells_where_the_unit_is_valid_in_both():
    reference, query = pair(4, n=5, m=4, p_invalid=0.0)
    qry_valid = query.valid.copy()
    qry_valid[1, 0] = False  # the second query row has no LShoulder: reference row 0 has two cells, one without it
    query = make_features(
        np.where(qry_valid[:, :, None], query.values, np.nan), qry_valid, query.units, recording_id=RECORDING_QRY
    )
    path = [[0, 0], [1, 0], [2, 1], [3, 1], [3, 2], [4, 3]]  # a vertical run, a vertical run, a horizontal run
    base = align(reference, query, min_visible=1, band=1.0, step="symmetric1")
    a = with_path(base, path)
    got = deviation_curve(a)
    want, count = expected_deviation(reference, query, path)
    assert_same(got.values, want, tol=1e-12)
    assert np.array_equal(got.n_valid, count)
    assert got.cells.tolist() == [2, 2, 1, 1]
    assert got.n_valid[0].tolist() == [1, 2, 2, 2, 2, 2] and got.n_valid[1].tolist() == [2] * 6
    one_cell = math.hypot(*(query.values[0, 0] - reference.values[0, 0]))  # row 0, LShoulder: the cell (0, 0) alone
    assert got.values[0, 0] == pytest.approx(one_cell, abs=1e-12)
    both = [math.hypot(*(query.values[i, 1] - reference.values[0, 1])) for i in (0, 1)]
    assert got.values[0, 1] == pytest.approx(sum(both) / 2.0, abs=1e-12) and both[0] != both[1]
    cost = base.cost.values
    assert got.total.tolist() == pytest.approx(
        [(cost[0, 0] + cost[1, 0]) / 2.0, (cost[2, 1] + cost[3, 1]) / 2.0, cost[3, 2], cost[4, 3]], abs=1e-12
    )


def test_t_cmp_06e_a_unit_of_weight_zero_is_still_reported_though_the_cost_leaves_it_out():
    reference, query = pair(5, p_invalid=0.0)
    values = reference.values.copy()
    values[:, 1, 0] += 3.0  # LWrist is 3 trunk lengths away on every row; the other five units are the same
    query = make_features(values, reference.valid, reference.units, recording_id=RECORDING_QRY)
    weighted = deviation_curve(aligned_on_the_diagonal(reference, query, weights={"LWrist": 0.0}))
    plain = deviation_curve(aligned_on_the_diagonal(reference, query))
    for got in (weighted, plain):
        assert np.allclose(got.values[:, 1], 3.0, atol=1e-12) and (got.reason[:, 1] == DeviationReason.valid).all()
    assert (weighted.total == 0.0).all()  # the cost is the mean of the other five units: all 0
    assert np.allclose(plain.total, 3.0 / 6.0, atol=1e-12)  # (3 + 0 * 5) / 6
    assert weighted.settings["weights"][1] == 0.0 and plain.settings["weights"][1] == 1.0


@pytest.mark.parametrize("under_mask", [math.nan, math.inf, 1e308], ids=["NaN", "inf", "1e308"])
def test_t_cmp_06e_a_value_under_a_false_mask_is_never_read(under_mask):
    reference, query = pair(6, p_invalid=0.3, under_mask=under_mask)
    a = aligned_on_the_diagonal(reference, query)
    with no_warnings():  # an inf minus an inf would warn
        got = deviation_curve(a)
    want, count = expected_deviation(reference, query, diagonal(10))
    assert_same(got.values, want, tol=1e-12)
    assert np.array_equal(got.n_valid, count)
    assert np.isfinite(got.values[count > 0]).all() and (count == 0).any() and (count > 0).any()


def test_t_cmp_06e_a_reference_row_without_a_path_cell_has_no_deviation_and_no_matched_time():
    reference, query = pair(7, n=4, p_invalid=0.0)
    path = [[0, 0], [1, 2], [2, 3]]  # reference row 1 has no cell (a path that does not run corner to corner)
    a = with_path(align(reference, query, min_visible=1, band=1.0, step="symmetric1"), path)
    with no_warnings():
        got, tempo = deviation_curve(a), local_tempo(a, smooth_s=1.0)
    assert got.cells.tolist() == [1, 0, 1, 1] and math.isnan(got.total[1]) and np.isnan(got.t_query[1])
    assert np.isnan(got.values[1]).all() and (got.reason[1] == DeviationReason.no_cell).all()
    assert (got.n_valid[1] == 0).all() and np.isfinite(got.values[[0, 2, 3]]).all()
    assert math.isnan(tempo.t_query[1]) and tempo.window_rows[1] == 3  # row 1 is not counted: its tau is not observed
    want, rows = expected_ratio(reference.t_sec.tolist(), expected_tau(query.t_sec.tolist(), path, 4), 1.0)
    assert_same(tempo.ratio, want, tol=1e-9)
    assert tempo.window_rows.tolist() == rows  # the fit leaves the NaN row out


def test_t_cmp_06e_the_curves_say_which_alignment_they_come_from():
    reference, query = pair(8, p_invalid=0.0)
    a = align(reference, query, min_visible=2, band=0.5)
    for got in (deviation_curve(a), local_tempo(a, smooth_s=0.4)):
        assert (got.reference_recording_id, got.query_recording_id) == (RECORDING_REF, RECORDING_QRY)
        assert got.settings == a.settings and dict(got.settings) == dict(a.settings)
        with pytest.raises(TypeError):
            got.settings["band"] = 1.0  # type: ignore[index]
        assert np.array_equal(got.t_ref, reference.t_sec) and np.array_equal(got.t_query, a.matched_query_times())
    assert a.result.status == "ok"


# --- T-CMP-06f: a window too small, no path ---------------------------------------------------------------------------
def test_t_cmp_06f_a_window_that_holds_one_row_gives_nan_with_a_reason_and_never_zero():
    ref_t = np.arange(10) * 0.1
    a = made(ref_t, ref_t * 2.0, diagonal(10))
    with no_warnings():
        got = local_tempo(a, smooth_s=0.1)  # half 0.05 s: only the row itself
    assert np.isnan(got.ratio).all() and not (got.ratio == 0.0).any()
    assert (got.reason == TempoReason.window_too_small).all() and (got.window_rows == 1).all()
    assert got.status == "ok" and got.whole_ratio == pytest.approx(2.0)  # the whole ratio does not need a window
    tiny = local_tempo(a, smooth_s=1e-300)
    assert np.isnan(tiny.ratio).all() and (tiny.reason == TempoReason.window_too_small).all()
    two = local_tempo(a, smooth_s=0.2)  # one row each side: three rows, edges two
    assert np.isfinite(two.ratio).all() and two.window_rows.tolist() == [2, *([3] * 8), 2]


def test_t_cmp_06f_a_row_alone_in_its_window_is_nan_while_its_neighbours_keep_their_ratio():
    ref_t = np.array([0.0, 0.1, 0.2, 3.0, 5.0, 5.1, 5.2])  # row 3 is a second away from every other row
    a = made(ref_t, ref_t * 1.5, diagonal(7))
    with no_warnings():
        got = local_tempo(a, smooth_s=0.5)
    assert got.reason.tolist() == [0, 0, 0, 1, 0, 0, 0] and math.isnan(got.ratio[3]) and got.window_rows[3] == 1
    assert np.allclose(np.delete(got.ratio, 3), 1.5, atol=1e-9)
    assert got.t_query[3] == pytest.approx(4.5, abs=1e-12)  # its matched time is there, only no tempo can be fitted


def test_t_cmp_06f_a_window_whose_squared_spread_underflows_is_nan_and_not_a_zero_over_zero():
    a = made([0.0, 1e-200], [0.0, 2e-200], diagonal(2))
    with no_warnings():
        got = local_tempo(a, smooth_s=1e-199)
    assert got.window_rows.tolist() == [2, 2]  # both rows are in the window ...
    assert (
        np.isnan(got.ratio).all() and (got.reason == TempoReason.window_too_small).all()
    )  # ... but there is no spread


def test_t_cmp_06f_a_segment_of_one_reference_row_has_no_tempo():
    a = made([0.0], [0.0], [[0, 0]])
    with no_warnings():
        got = local_tempo(a, smooth_s=0.5)
        dev = deviation_curve(a)
    assert np.isnan(got.ratio).all() and got.reason.tolist() == [TempoReason.window_too_small]
    assert math.isnan(got.whole_ratio) and got.whole_reason == TempoReason.window_too_small
    assert dev.cells.tolist() == [1] and dev.n_valid.tolist() == [[1]]  # the deviation does not need a window


def blind_alignment() -> Alignment:
    reference = random_features(np.random.default_rng(9), 6, p_invalid=0.0)
    blind = make_features(np.full((5, 6, 2), np.nan), np.zeros((5, 6), dtype=bool), recording_id=RECORDING_QRY)
    return align(reference, blind, min_visible=1, band=0.5)  # no unit is valid in any query frame: every cell is +inf


def test_t_cmp_06f_no_path_gives_curves_of_nan_with_the_reason_no_path_and_never_zeros():
    a = blind_alignment()
    assert a.result.status == "no_path"
    with no_warnings():
        tempo, dev = local_tempo(a, smooth_s=0.5), deviation_curve(a)
    assert tempo.status == "no_path" and dev.status == "no_path"
    assert np.isnan(tempo.ratio).all() and np.isnan(tempo.t_query).all() and (tempo.window_rows == 0).all()
    assert (tempo.reason == TempoReason.no_path).all() and tempo.reason.shape == (6,)
    assert math.isnan(tempo.whole_ratio) and tempo.whole_reason == TempoReason.no_path
    assert np.array_equal(
        tempo.t_ref, a.reference.t_sec
    )  # the clock is the reference's own, observed whatever the path
    assert np.isnan(dev.values).all() and dev.values.shape == (6, 6) and (dev.reason == DeviationReason.no_path).all()
    assert (
        (dev.n_valid == 0).all()
        and (dev.cells == 0).all()
        and np.isnan(dev.total).all()
        and np.isnan(dev.t_query).all()
    )
    for curve in (tempo.ratio, dev.values, dev.total):
        assert not (curve == 0.0).any()


def test_t_cmp_06f_the_slope_pattern_may_leave_no_path_for_two_lengths_and_that_is_a_result_too():
    rng = np.random.default_rng(10)
    long_reference, two_rows = random_features(rng, 9, p_invalid=0.0), random_features(rng, 2, p_invalid=0.0)
    a = align(long_reference, two_rows, min_visible=1, band=1.0)  # symmetricP1: 2 query rows cannot cover 9 rows
    assert a.result.status == "no_path"
    assert (local_tempo(a, smooth_s=0.5).reason == TempoReason.no_path).all()
    assert (deviation_curve(a).reason == DeviationReason.no_path).all()


def test_t_cmp_06f_the_reasons_have_fixed_numbers_that_a_report_can_store():
    assert [int(r) for r in TempoReason] == [0, 1, 2]
    assert (TempoReason.valid, TempoReason.window_too_small, TempoReason.no_path) == (0, 1, 2)
    assert [int(r) for r in DeviationReason] == [0, 1, 2, 3]
    assert (DeviationReason.valid, DeviationReason.not_valid_in_both) == (0, 1)
    assert (DeviationReason.no_path, DeviationReason.no_cell) == (2, 3)


# --- T-CMP-06g: refusals ----------------------------------------------------------------------------------------------
def small_alignment() -> Alignment:
    ref_t = np.arange(6) * 0.1
    return made(ref_t, ref_t * 2.0, diagonal(6))


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(0.0, id="zero"),
        pytest.param(-0.5, id="negative"),
        pytest.param(math.nan, id="NaN"),
        pytest.param(math.inf, id="infinity"),
        pytest.param(-math.inf, id="minus infinity"),
        pytest.param(True, id="a bool"),
        pytest.param(np.bool_(True), id="a numpy bool"),
        pytest.param("0.5", id="a string"),
        pytest.param(None, id="None"),
        pytest.param([0.5], id="a list"),
        pytest.param(np.array([0.5]), id="an array"),
        pytest.param(BIG, id="an integer too large for a float"),
        pytest.param(-BIG, id="a negative integer too large for a float"),
    ],
)
def test_t_cmp_06g_smooth_s_that_is_not_a_positive_finite_number_is_refused_naming_it(bad):
    message = refusal(local_tempo, small_alignment(), smooth_s=bad)
    assert "smooth_s" in message and len(message) < 300  # short: a huge integer or a string is never printed whole


def test_t_cmp_06g_a_message_never_echoes_a_string_of_the_caller_and_says_a_number_as_it_is():
    assert "SECRET" not in refusal(local_tempo, small_alignment(), smooth_s="SECRET-window")
    assert "got str" in refusal(local_tempo, small_alignment(), smooth_s="SECRET-window")
    assert "got -0.5" in refusal(local_tempo, small_alignment(), smooth_s=-0.5)
    assert "got nan" in refusal(local_tempo, small_alignment(), smooth_s=math.nan)
    assert "got inf" in refusal(local_tempo, small_alignment(), smooth_s=BIG)
    assert "got -inf" in refusal(local_tempo, small_alignment(), smooth_s=-BIG)


@pytest.mark.parametrize("smooth_s", [0.5, 1, np.float32(0.5), np.float64(0.5), np.int64(1), 1e-3], ids=repr)
def test_t_cmp_06g_a_python_or_numpy_number_is_accepted_and_echoed_as_a_python_float(smooth_s):
    got = local_tempo(small_alignment(), smooth_s=smooth_s)
    assert type(got.smooth_s) is float and got.smooth_s == float(smooth_s)


def test_t_cmp_06g_smooth_s_has_no_default_and_is_keyword_only():
    a = small_alignment()
    with pytest.raises(TypeError):
        local_tempo(a)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        local_tempo(a, 0.5)  # type: ignore[misc]
    with pytest.raises(TypeError):
        deviation_curve(a, smooth_s=0.5)  # type: ignore[call-arg]


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
@pytest.mark.parametrize("wrong", [None, "alignment", 5, np.zeros((3, 3))], ids=["None", "str", "int", "array"])
def test_t_cmp_06g_an_argument_that_is_not_an_alignment_is_refused_naming_it(function, wrong):
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    message = refusal(function, wrong, **arguments)
    assert "alignment" in message and "Alignment" in message and f"got {type(wrong).__name__}" in message
    assert "alignment" in refusal(function, small_alignment().reference, **arguments)  # a FrameFeatures is not one
    assert "alignment" in refusal(function, small_alignment().result, **arguments)  # nor a DtwResult


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
@pytest.mark.parametrize("who", ["reference", "query"])
@pytest.mark.parametrize(
    ("t_sec", "what"),
    [
        pytest.param(np.arange(5) / 30.0, "one entry per row", id="too few entries"),
        pytest.param(np.arange(7) / 30.0, "one entry per row", id="too many entries"),
        pytest.param(
            np.arange(12, dtype=np.float64).reshape(2, 6), "one-dimensional float array", id="two-dimensional"
        ),
        pytest.param(np.arange(6), "one-dimensional float array", id="integers"),
        pytest.param([0.0, 0.1, 0.2, 0.3, 0.4, 0.5], "one-dimensional float array", id="a list"),
        pytest.param(np.array([0.0, 0.1, math.nan, 0.3, 0.4, 0.5]), "must be finite", id="NaN"),
        pytest.param(np.array([0.0, 0.1, math.inf, 0.3, 0.4, 0.5]), "must be finite", id="infinity"),
        pytest.param(np.array([0.0, 0.1, 0.3, 0.2, 0.4, 0.5]), "strictly increasing", id="goes back"),
        pytest.param(np.array([0.0, 0.1, 0.1, 0.2, 0.4, 0.5]), "strictly increasing", id="a repeated time"),
    ],
)
def test_t_cmp_06g_an_alignment_whose_clock_is_not_a_clock_is_refused_naming_it(function, who, t_sec, what):
    a = small_alignment()
    bad = dataclasses.replace(a, **{who: dataclasses.replace(getattr(a, who), t_sec=t_sec)})
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    message = refusal(function, bad, **arguments)
    assert f"alignment.{who}.t_sec" in message and what in message


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
def test_t_cmp_06g_an_alignment_whose_arrays_do_not_fit_each_other_is_refused_naming_the_part(function):
    a = small_alignment()
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    wrong_valid = dataclasses.replace(a.reference, valid=np.ones((6, 2), dtype=bool))
    assert "alignment.reference.valid" in refusal(function, dataclasses.replace(a, reference=wrong_valid), **arguments)
    wrong_query_valid = dataclasses.replace(a.query, valid=np.ones((5, 1), dtype=bool))
    assert "alignment.query.valid" in refusal(function, dataclasses.replace(a, query=wrong_query_valid), **arguments)
    wrong_values = dataclasses.replace(a.reference, values=np.zeros((6, 1)))
    assert "alignment.reference.values" in refusal(
        function, dataclasses.replace(a, reference=wrong_values), **arguments
    )
    other = dataclasses.replace(a.cost, values=np.zeros((6, 7)))
    assert "alignment.cost" in refusal(function, dataclasses.replace(a, cost=other), **arguments)
    assert isinstance(a.cost, CostMatrix)
    non_finite = a.query.values.copy()
    non_finite[2, 0, 0] = math.nan  # a feature that says it is valid and has no value: a defect upstream
    bad = dataclasses.replace(a.query, values=non_finite)
    assert "alignment.query" in refusal(function, dataclasses.replace(a, query=bad), **arguments)


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
@pytest.mark.parametrize(
    ("path", "what"),
    [
        pytest.param(np.array([[0, 0], [1, 1]], dtype=np.float64), "integer array", id="floats"),
        pytest.param([[0, 0], [1, 1]], "integer array", id="a list"),
        pytest.param(np.zeros((3, 3), dtype=np.int64), "shape (L, 2)", id="three columns"),
        pytest.param(np.zeros(4, dtype=np.int64), "shape (L, 2)", id="one-dimensional"),
        pytest.param(np.array([[0, 0], [6, 5]]), "inside the cost matrix", id="a query row too large"),
        pytest.param(np.array([[0, 0], [5, 6]]), "inside the cost matrix", id="a reference row too large"),
        pytest.param(np.array([[0, 0], [-1, 2]]), "inside the cost matrix", id="a negative query row"),
        pytest.param(np.array([[0, -1], [2, 2]]), "inside the cost matrix", id="a negative reference row"),
    ],
)
def test_t_cmp_06g_an_ok_alignment_whose_path_is_not_a_path_of_the_matrix_is_refused_naming_it(function, path, what):
    a = small_alignment()
    bad = dataclasses.replace(a, result=dataclasses.replace(a.result, path=path))
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    message = refusal(function, bad, **arguments)
    assert "alignment.result.path" in message and what in message


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
def test_t_cmp_06g_a_status_that_is_neither_ok_nor_no_path_is_refused_and_a_path_is_read_only_when_ok(function):
    a = small_alignment()
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    bad = dataclasses.replace(a, result=dataclasses.replace(a.result, status="SECRET"))
    message = refusal(function, bad, **arguments)
    assert "alignment.result.status" in message and "SECRET" not in message
    for no_path in (np.zeros((0, 2), dtype=np.int64), None):
        empty = dataclasses.replace(a, result=dataclasses.replace(a.result, status="no_path", path=no_path))
        assert function(empty, **arguments).status == "no_path"  # a path is not read when there is none
    narrow = dataclasses.replace(a.result, path=np.array([[0, 0], [1, 1]], dtype=np.int32))
    assert function(dataclasses.replace(a, result=narrow), **arguments).status == "ok"  # any signed integer width


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
def test_t_cmp_06g_units_that_do_not_fit_the_values_or_each_other_are_refused_naming_the_part(function):
    a = small_alignment()
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    two = make_units(("LWrist", "RWrist"), ())
    query_two = dataclasses.replace(a.query, values=np.zeros((6, 2, 2)), valid=np.ones((6, 2), dtype=bool), units=two)
    assert "same number of units" in refusal(function, dataclasses.replace(a, query=query_two), **arguments)
    as_list = dataclasses.replace(a.reference, units=list(a.reference.units))
    assert "alignment.reference.units" in refusal(function, dataclasses.replace(a, reference=as_list), **arguments)
    short = dataclasses.replace(a.reference, units=())
    assert "alignment.reference.units" in refusal(function, dataclasses.replace(a, reference=short), **arguments)
    names = dataclasses.replace(a.query, units=("LWrist",))
    assert "alignment.query.units" in refusal(function, dataclasses.replace(a, query=names), **arguments)
    cost = dataclasses.replace(a, cost="SECRET")
    message = refusal(function, cost, **arguments)
    assert "alignment.cost" in message and "SECRET" not in message


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
@pytest.mark.parametrize("who", ["reference", "query"])
@pytest.mark.parametrize(
    ("field", "wrong", "what"),
    [
        pytest.param("values", np.zeros((6, 1, 2), dtype=np.int64), "floating-point array", id="values of integers"),
        pytest.param("values", np.zeros((6, 1, 3)), "shape (N, U, 2)", id="values with three components"),
        pytest.param("values", [[[0.0, 0.0]]] * 6, "floating-point array", id="values as a list"),
        pytest.param("valid", np.ones((6, 1), dtype=np.int64), "bool array", id="a valid mask of integers"),
        pytest.param("valid", [[True]] * 6, "bool array", id="a valid mask as a list"),
    ],
)
def test_t_cmp_06g_features_whose_values_or_mask_have_the_wrong_kind_are_refused_naming_the_part(
    function, who, field, wrong, what
):
    a = small_alignment()
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    bad = dataclasses.replace(a, **{who: dataclasses.replace(getattr(a, who), **{field: wrong})})
    message = refusal(function, bad, **arguments)
    assert f"alignment.{who}.{field}" in message and what in message


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
@pytest.mark.parametrize("who", ["reference", "query"])
def test_t_cmp_06g_a_part_that_is_not_features_is_refused_naming_it(function, who):
    a = small_alignment()
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    for wrong in (None, "SECRET", np.zeros((6, 1, 2))):
        message = refusal(function, dataclasses.replace(a, **{who: wrong}), **arguments)
        assert f"alignment.{who} must be a FrameFeatures" in message and f"got {type(wrong).__name__}" in message
        assert "SECRET" not in message


@pytest.mark.parametrize("function", [local_tempo, deviation_curve])
def test_t_cmp_06g_an_ok_result_with_an_empty_path_is_curves_of_nan_with_a_reason_and_not_an_error(function):
    """Only a hand-made result can be ``ok`` without a cell: no row has an observed time, nothing is invented."""
    a = small_alignment()
    empty = dataclasses.replace(a, result=dataclasses.replace(a.result, path=np.zeros((0, 2), dtype=np.int64)))
    arguments = {"smooth_s": 0.5} if function is local_tempo else {}
    with no_warnings():
        got = function(empty, **arguments)
    assert got.status == "ok" and np.isnan(got.t_query).all()
    if function is local_tempo:
        assert np.isnan(got.ratio).all() and (got.reason == TempoReason.window_too_small).all()
        assert (got.window_rows == 0).all() and got.whole_ratio == pytest.approx(2.0)
    else:
        assert np.isnan(got.values).all() and (got.reason == DeviationReason.no_cell).all()
        assert (got.cells == 0).all() and np.isnan(got.total).all()


def test_t_cmp_06c_the_tolerance_of_the_window_edge_is_a_nanosecond():
    """Two rows 0.25 s plus 0.5 ns apart are in each other's window of half 0.25 s; 5 ns apart they are not."""
    inside = local_tempo(made([0.0, 0.25 + 5e-10], [0.0, 1.0], diagonal(2)), smooth_s=0.5)
    assert inside.window_rows.tolist() == [2, 2] and np.isfinite(inside.ratio).all()
    outside = local_tempo(made([0.0, 0.25 + 5e-9], [0.0, 1.0], diagonal(2)), smooth_s=0.5)
    assert outside.window_rows.tolist() == [1, 1] and np.isnan(outside.ratio).all()
    assert (outside.reason == TempoReason.window_too_small).all()


def test_t_cmp_06f_a_reference_of_one_row_against_a_longer_query_has_no_whole_ratio_and_no_division_by_zero():
    a = made([0.0], [0.0, 0.4, 1.0], [[0, 0], [1, 0], [2, 0]])  # one reference row, a vertical run of three cells
    with no_warnings():
        got = local_tempo(a, smooth_s=0.5)
    assert math.isnan(got.whole_ratio) and got.whole_reason == TempoReason.window_too_small
    assert got.t_query.tolist() == pytest.approx([(0.0 + 0.4 + 1.0) / 3.0], abs=1e-12)
    assert np.isnan(got.ratio).all() and got.reason.tolist() == [TempoReason.window_too_small]


def test_t_cmp_06g_when_both_arguments_are_bad_the_alignment_is_the_one_named():
    message = refusal(local_tempo, None, smooth_s=-1.0)
    assert "alignment" in message and "smooth_s" not in message


# --- T-CMP-06h: read-only arrays, inputs unchanged --------------------------------------------------------------------
def arrays_of(a: Alignment) -> list[np.ndarray]:
    return [
        a.reference.t_sec, a.reference.values, a.reference.valid, a.reference.reason, a.reference.bridged,
        a.query.t_sec, a.query.values, a.query.valid, a.query.reason, a.query.bridged,
        a.cost.values, a.cost.n_common, a.result.path,
    ]  # fmt: skip


def test_t_cmp_06h_the_arrays_are_new_and_read_only_and_the_alignment_is_not_changed():
    reference, query = pair(11, n=12, p_invalid=0.1)
    a = align(reference, query, min_visible=2, band=0.6)
    assert a.result.status == "ok"
    before = [x.copy() for x in arrays_of(a)]
    flags_before = [x.flags.writeable for x in arrays_of(a)]
    settings_before = dict(a.settings)
    tempo, dev = local_tempo(a, smooth_s=0.4), deviation_curve(a)
    for old, new, flag in zip(before, arrays_of(a), flags_before, strict=True):
        assert np.array_equal(old, new, equal_nan=True)
        assert new.flags.writeable == flag  # a read-only input stays read-only, a writeable one is not frozen by us
    assert dict(a.settings) == settings_before
    for curve in (tempo, dev):
        for field in dataclasses.fields(curve):
            value = getattr(curve, field.name)
            if isinstance(value, np.ndarray):
                assert not value.flags.writeable, field.name
                with pytest.raises(ValueError):
                    value.flat[0] = 1
                assert not any(np.shares_memory(value, x) for x in arrays_of(a)), field.name
        with pytest.raises(dataclasses.FrozenInstanceError):
            curve.status = "no_path"  # type: ignore[misc]
    assert tempo.reason.dtype == np.uint8 and tempo.window_rows.dtype == np.int64 and tempo.ratio.dtype == np.float64
    assert dev.reason.dtype == np.uint8 and dev.n_valid.dtype == np.int64 and dev.cells.dtype == np.int64
    assert dev.values.dtype == np.float64 and dev.values.shape == (12, 6) and dev.total.shape == (12,)
    assert tempo.t_ref.dtype == np.float64 and tempo.t_query.dtype == np.float64 and dev.t_query.dtype == np.float64


def test_t_cmp_06h_every_call_gives_new_arrays_with_the_same_numbers_and_read_only_inputs_are_accepted():
    rng = np.random.default_rng(12)
    reference = random_features(rng, 10, p_invalid=0.05, frozen=True)
    query = random_features(rng, 11, p_invalid=0.05, frozen=True, recording_id=RECORDING_QRY)
    a = align(reference, query, min_visible=2, band=0.6)
    first, second = local_tempo(a, smooth_s=0.4), local_tempo(a, smooth_s=0.4)
    assert first is not second and first.ratio is not second.ratio and np.array_equal(first.ratio, second.ratio, True)
    d1, d2 = deviation_curve(a), deviation_curve(a)
    assert d1.values is not d2.values and np.array_equal(d1.values, d2.values, equal_nan=True)
    assert np.array_equal(d1.t_query, first.t_query, equal_nan=True) and np.array_equal(d1.t_ref, first.t_ref)
