"""T-CMP-03, T-CMP-03b to 03h and T-CMP-05: constrained DTW on a cost matrix (P6.03a; W8 and Appendix C.3, C.4).

The module under test is checked against an independent implementation written in this file: a plain memoised recursion
over every cell, with the band in exact arithmetic (``Fraction``) and the two step patterns written out from their
definition. It shares no helper with ``compare/dtw.py``. ``dtaidistance`` is not installed (P6.03a Q3), so this is the
T-CMP-05 check. Where the cost of a path in a tie depends on which tied path is returned, the reference follows the
documented tie order, and other tests check the returned path without that order (its weighted cost is the minimum).
"""

from __future__ import annotations

import dataclasses
import functools
import math
import time
from fractions import Fraction

import numpy as np
import pytest

from taiji_ai.compare import CompareError
from taiji_ai.compare import dtw as dtw_module
from taiji_ai.compare.dtw import DtwResult, band_mask, dtw

INF = math.inf
STEPS = ("symmetric1", "symmetricP1")
BANDS = (0.1, 0.2, 0.25, 0.3, 0.5, 0.75, 1.0)
CASES = 120  # random matrices per (step, kind) in T-CMP-05
# 900 x 900, band 0.2, symmetricP1: measured 0.04 to 0.08 s (task file, section 5); the bound only catches a gross
# regression
TIMING_BOUND_S = 1.0


# --- the independent reference ----------------------------------------------------------------------------------------
def allowed(i: int, k: int, n: int, m: int, band: float) -> bool:
    """The band in exact arithmetic: |i/(n-1) - k/(m-1)| <= band + 1e-12 (a side of one element sits at 0)."""
    x = Fraction(i, n - 1) if n > 1 else Fraction(0)
    y = Fraction(k, m - 1) if m > 1 else Fraction(0)
    return abs(x - y) <= Fraction(band) + Fraction(1e-12)


def reference(cost: np.ndarray, band: float, step: str) -> tuple[float, tuple[tuple[int, int], ...]] | None:
    """``(accumulated cost, path)`` of the best path, or ``None``; every cell is visited by a memoised recursion.

    ``symmetric1``: ``g = c + min(g(i-1,k-1), g(i-1,k), g(i,k-1))``. ``symmetricP1`` (Sakoe and Chiba, ``P = 1``,
    symmetric weights): ``g(0,0) = 2 c(0,0)``, then the minimum of ``g(i-1,k-1) + 2c(i,k)``,
    ``g(i-1,k-2) + 2c(i,k-1) + c(i,k)`` and ``g(i-2,k-1) + 2c(i-1,k) + c(i,k)``. A cell outside the band or at ``+inf``
    cannot be used, as the middle cell of a step either. Ties go to the first option in the order written here (the
    documented order of ``compare/dtw.py``).
    """
    n, m = cost.shape
    c = cost.tolist()
    nothing = (INF, ())

    def usable(i: int, k: int) -> bool:
        return 0 <= i < n and 0 <= k < m and allowed(i, k, n, m, band) and c[i][k] < INF

    @functools.cache
    def best(i: int, k: int) -> tuple[float, tuple[tuple[int, int], ...]]:
        if not usable(i, k):
            return nothing
        if (i, k) == (0, 0):
            return (c[0][0] if step == "symmetric1" else 2.0 * c[0][0], ((0, 0),))
        options = []
        if step == "symmetric1":
            for pi, pk in ((i - 1, k - 1), (i - 1, k), (i, k - 1)):
                g, path = best(pi, pk)
                options.append((g + c[i][k], (*path, (i, k))))
        else:
            g, path = best(i - 1, k - 1)
            options.append((g + 2.0 * c[i][k], (*path, (i, k))))
            if usable(i, k - 1):
                g, path = best(i - 1, k - 2)
                options.append((g + 2.0 * c[i][k - 1] + c[i][k], (*path, (i, k - 1), (i, k))))
            if usable(i - 1, k):
                g, path = best(i - 2, k - 1)
                options.append((g + 2.0 * c[i - 1][k] + c[i][k], (*path, (i - 1, k), (i, k))))
        winner = min(options, key=lambda option: option[0])  # the first of the smallest
        return winner if winner[0] < INF else nothing

    g, path = best(n - 1, m - 1)
    return None if g == INF else (g, path)


def weighted_cost(cost: np.ndarray, path: np.ndarray, step: str) -> float:
    """The cost of a path under the weights of the pattern, from its cells alone (no tie order is assumed).

    ``symmetric1`` weighs every cell 1. In ``symmetricP1`` a cell has weight 2 when it is the start or is reached by a
    diagonal unit step, and 1 when it is reached by a horizontal or vertical unit step (the end of a compound step).
    """
    total = 0.0
    for t, (i, k) in enumerate(path.tolist()):
        if step == "symmetric1":
            weight = 1.0
        elif t == 0:
            weight = 2.0
        else:
            weight = 2.0 if (i - path[t - 1, 0], k - path[t - 1, 1]) == (1, 1) else 1.0
        total += weight * float(cost[i, k])
    return total


def unit_steps(path: np.ndarray) -> list[str]:
    """``D`` (1, 1), ``H`` (0, 1) or ``V`` (1, 0) for each step of the path; anything else is ``?``."""
    names = {(1, 1): "D", (0, 1): "H", (1, 0): "V"}
    return [names.get((int(a), int(b)), "?") for a, b in np.diff(path, axis=0)]


# --- random cases -----------------------------------------------------------------------------------------------------
def random_matrix(rng: np.random.Generator, n: int, m: int, *, integer: bool, inf_fraction: float) -> np.ndarray:
    cost = rng.integers(0, 4, size=(n, m)).astype(np.float64) if integer else rng.random((n, m)) * 3.0
    cost[rng.random((n, m)) < inf_fraction] = np.inf
    return cost


def random_case(rng: np.random.Generator) -> tuple[int, int, float, float]:
    """``(n, m, band, inf_fraction)``: sizes 1 to 40 (mostly with a slope the pattern allows), bands 0.1 to 1."""
    n = int(rng.integers(1, 41))
    if rng.random() < 0.7:
        m = int(np.clip(n + rng.integers(-(n // 2) - 1, n // 2 + 2), 1, 40))
    else:
        m = int(rng.integers(1, 41))
    band = float(rng.choice(BANDS)) if rng.random() < 0.7 else float(rng.uniform(0.1, 1.0))
    return n, m, band, float(rng.choice([0.0, 0.0, 0.1, 0.3]))


def ok_cases(rng: np.random.Generator, step: str, count: int, *, integer: bool = False) -> list:
    """``count`` random cases whose result is a path: ``(cost, band, result)``."""
    found = []
    while len(found) < count:
        n, m, band, inf_fraction = random_case(rng)
        cost = random_matrix(rng, n, m, integer=integer, inf_fraction=inf_fraction)
        result = dtw(cost, band=band, step=step)
        if result.status == "ok":
            found.append((cost, band, result))
    return found


# --- T-CMP-03: identical sequences ------------------------------------------------------------------------------------
@pytest.mark.parametrize("band", [0.1, 0.3, 1.0])
@pytest.mark.parametrize("n", [1, 2, 7, 60, 200])
@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03_identical_sequences_have_distance_zero_and_the_diagonal_path(step, n, band):
    rng = np.random.default_rng(n)
    x = np.cumsum(rng.uniform(0.5, 2.0, size=n))  # strictly increasing: no two frames alike
    cost = np.abs(x[:, None] - x[None, :])  # 0 on the diagonal, at least 0.5 elsewhere
    result = dtw(cost, band=band, step=step)
    assert isinstance(result, DtwResult) and result.status == "ok"
    assert result.distance == 0.0 and result.accumulated == 0.0 and result.normalised == 0.0
    assert np.array_equal(result.path, np.column_stack([np.arange(n), np.arange(n)]))


def test_t_cmp_03_a_hand_computed_3x3_matrix_for_both_patterns():
    cost = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
    one = dtw(cost, band=1.0, step="symmetric1")  # g: [[1, 3, 6], [5, 6, 9], [12, 13, 15]]
    assert one.accumulated == 15.0 and one.distance == 5.0 and one.normalised == 5.0
    assert one.path.tolist() == [[0, 0], [1, 1], [2, 2]]
    p1 = dtw(cost, band=1.0, step="symmetricP1")  # g(1,1) = 2 + 10, g(2,2) = 12 + 18
    assert p1.accumulated == 30.0 and p1.normalised == 30.0 / (3 + 3) and p1.distance == 5.0
    assert p1.path.tolist() == [[0, 0], [1, 1], [2, 2]]


def test_t_cmp_03_a_hand_computed_compound_step_is_listed_with_its_middle_cell():
    wide = np.array([[0.0, 9.0, 9.0], [9.0, 1.0, 0.0]])  # 2 x 3: the only path is one step from (0, 0) to (1, 2)
    result = dtw(wide, band=1.0, step="symmetricP1")
    assert result.path.tolist() == [[0, 0], [1, 1], [1, 2]]  # (1, 1) is the middle cell, weight 2
    assert result.accumulated == 0.0 + 2 * 1.0 + 0.0 and result.normalised == 2.0 / (2 + 3)
    assert result.distance == pytest.approx((0.0 + 1.0 + 0.0) / 3)  # the plain mean over the three listed cells
    tall = dtw(wide.T.copy(), band=1.0, step="symmetricP1")
    assert tall.path.tolist() == [[0, 0], [1, 1], [2, 1]]
    assert tall.accumulated == 2.0 and tall.distance == pytest.approx(1.0 / 3)


# --- T-CMP-05: the independent implementation -------------------------------------------------------------------------
@pytest.mark.parametrize("integer", [False, True], ids=["floats", "integers-with-ties"])
@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_05_accumulated_distance_and_path_equal_the_independent_recursion(step, integer):
    rng = np.random.default_rng(20261117 + 2 * STEPS.index(step) + int(integer))
    seen = {"ok": 0, "no_path": 0}
    for _ in range(CASES):
        n, m, band, inf_fraction = random_case(rng)
        cost = random_matrix(rng, n, m, integer=integer, inf_fraction=inf_fraction)
        where = f"{step} {n}x{m} band={band} inf={inf_fraction}"
        expected = reference(cost, band, step)
        got = dtw(cost, band=band, step=step)
        if expected is None:
            seen["no_path"] += 1
            assert got.status == "no_path" and got.distance is None, where
            continue
        seen["ok"] += 1
        accumulated, path = expected
        assert got.status == "ok", where
        assert got.accumulated == pytest.approx(accumulated, rel=1e-12, abs=1e-12), where
        assert got.distance == pytest.approx(sum(cost[c] for c in path) / len(path), rel=1e-12, abs=1e-12), where
        assert [tuple(row) for row in got.path.tolist()] == list(path), where
        normaliser = n + m if step == "symmetricP1" else len(path)
        assert got.normalised == pytest.approx(accumulated / normaliser, rel=1e-12, abs=1e-12), where
    assert seen["ok"] >= CASES * 0.3 and seen["no_path"] >= CASES * 0.03, seen  # the cases are not all one kind


@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_05_the_returned_path_is_a_minimal_path_without_assuming_the_tie_order(step):
    rng = np.random.default_rng(77 + STEPS.index(step))
    for cost, band, result in ok_cases(rng, step, 60, integer=True):
        expected = reference(cost, band, step)
        assert expected is not None
        assert weighted_cost(cost, result.path, step) == pytest.approx(expected[0], rel=1e-12, abs=1e-12)
        assert result.accumulated == pytest.approx(expected[0], rel=1e-12, abs=1e-12)


def test_t_cmp_05_a_wider_band_never_costs_more_and_may_find_a_path_a_narrow_band_cannot():
    rng = np.random.default_rng(5)
    found_gain = 0
    for step in STEPS:
        for _ in range(60):
            n = int(rng.integers(2, 30))
            m = int(np.clip(n + rng.integers(-3, 4), 2, 40))
            cost = random_matrix(rng, n, m, integer=False, inf_fraction=0.1)
            results = [dtw(cost, band=band, step=step) for band in (0.1, 0.3, 0.6, 1.0)]
            accumulated = [r.accumulated for r in results]
            for narrow, wide in zip(accumulated, accumulated[1:], strict=False):
                if narrow is not None:
                    assert wide is not None and wide <= narrow + 1e-12  # a path of the narrow band is in the wide one
            found_gain += results[0].status == "no_path" and results[-1].status == "ok"
    assert found_gain > 0  # the band does remove paths in these cases


# --- T-CMP-03b: the band, and the cells of the path -------------------------------------------------------------------
@pytest.mark.parametrize(
    ("n", "m", "band"),
    [
        (1, 1, 0.1),
        (1, 6, 1.0),
        (1, 6, 0.5),
        (6, 1, 0.5),
        (2, 2, 0.1),
        (5, 9, 0.2),
        (9, 5, 0.2),
        (13, 13, 0.3),
        (30, 41, 0.1),
    ],
)
def test_t_cmp_03b_band_mask_is_the_exact_band(n, m, band):
    mask = band_mask(n, m, band)
    assert mask.shape == (n, m) and mask.dtype == np.bool_ and not mask.flags.writeable
    expected = np.array([[allowed(i, k, n, m, band) for k in range(m)] for i in range(n)])
    assert np.array_equal(mask, expected)


def test_t_cmp_03b_a_cell_exactly_on_the_edge_is_in_the_band_even_where_the_fractions_are_not_exact():
    # r = j / (n - 1): the band of a square matrix is exactly |i - k| <= j
    # (8/10 - 6/10 is 0.20000000000000007 in floats, a hair above 2/10)
    for n in range(2, 41):
        i, k = np.indices((n, n))
        for j in range(1, n):
            mask = band_mask(n, n, j / (n - 1))
            assert np.array_equal(mask, np.abs(i - k) <= j), (n, j)


def test_t_cmp_03b_corners_are_in_every_band_and_band_one_is_no_band():
    for n, m in [(2, 2), (2, 9), (9, 2), (7, 7), (30, 55)]:
        for band in (0.01, 0.1, 0.5):
            mask = band_mask(n, m, band)
            assert mask[0, 0] and mask[n - 1, m - 1]  # n, m >= 2: the corners are on the diagonal
            assert not mask[0, m - 1] or band >= 1.0 - 1e-9
        assert band_mask(n, m, 1.0).all()
    assert band_mask(1, 4, 1.0).all() and band_mask(4, 1, 1.0).all()
    narrow, wide = band_mask(20, 25, 0.1), band_mask(20, 25, 0.3)
    assert (narrow & ~wide).sum() == 0 and wide.sum() > narrow.sum()  # a narrower band lies inside a wider one


@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03b_every_cell_of_the_path_is_in_the_band_and_the_path_runs_from_corner_to_corner(step):
    rng = np.random.default_rng(31 + STEPS.index(step))
    for cost, band, result in ok_cases(rng, step, 80):
        n, m = cost.shape
        path = result.path
        assert path.dtype == np.int64 and path.ndim == 2 and path.shape[1] == 2 and len(path) >= 1
        assert path[0].tolist() == [0, 0] and path[-1].tolist() == [n - 1, m - 1]
        assert all(allowed(int(i), int(k), n, m, band) for i, k in path), (n, m, band)
        steps = unit_steps(path)
        assert "?" not in steps  # monotone: every step is one of the three unit steps
        assert np.isfinite(cost[path[:, 0], path[:, 1]]).all()


@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03b_a_narrow_band_keeps_the_path_near_the_diagonal(step):
    n = m = 40
    i, k = np.indices((n, m))
    cost = np.abs((k - i) - 10.0) / 10.0  # a valley 10 columns right of the diagonal tempts the path to leave it
    wide = dtw(cost, band=1.0, step=step)
    narrow = dtw(cost, band=0.1, step=step)
    assert narrow.status == "ok" and wide.status == "ok"
    gap = np.abs(narrow.path[:, 0] / (n - 1) - narrow.path[:, 1] / (m - 1)).max()
    assert gap <= 0.1 + 1e-9
    assert np.abs(wide.path[:, 0] / (n - 1) - wide.path[:, 1] / (m - 1)).max() > 0.1  # the band was what held it


# --- T-CMP-03c: the slope limit ---------------------------------------------------------------------------------------
def test_t_cmp_03c_the_slope_pattern_never_repeats_a_horizontal_or_a_vertical_step():
    rng = np.random.default_rng(3)
    for _, band, result in ok_cases(rng, "symmetricP1", 120, integer=True):
        steps = unit_steps(result.path)
        text = "".join(steps)
        assert "HH" not in text and "VV" not in text and "HV" not in text and "VH" not in text, (text, band)
        if steps:
            assert steps[0] == "D"  # every compound step starts with a diagonal step
        for t, name in enumerate(steps):
            if name in "HV":
                assert steps[t - 1] == "D" and (t + 1 == len(steps) or steps[t + 1] == "D")


def test_t_cmp_03c_lengths_beyond_slope_two_have_no_path_and_the_others_have_one():
    for n in range(1, 13):
        for m in range(1, 13):
            cost = np.ones((n, m))
            slope_ok = m - 1 <= 2 * (n - 1) and n - 1 <= 2 * (m - 1)
            p1 = dtw(cost, band=1.0, step="symmetricP1")
            assert (p1.status == "ok") == slope_ok, (n, m)
            assert dtw(cost, band=1.0, step="symmetric1").status == "ok"  # unit steps have no slope limit
            if not slope_ok:
                assert p1.distance is None and len(p1.path) == 0


def test_t_cmp_03c_the_limit_changes_the_path_where_the_unit_pattern_runs_flat():
    cost = np.ones((5, 8))
    flat = [(0, 0), (1, 1), (1, 2), (1, 3), (1, 4), (2, 5), (3, 6), (4, 7)]  # three horizontal steps in a row
    for cell in flat:
        cost[cell] = 0.0
    unit = dtw(cost, band=1.0, step="symmetric1")
    assert unit.distance == 0.0 and [tuple(row) for row in unit.path.tolist()] == flat
    assert "HHH" in "".join(unit_steps(unit.path))
    limited = dtw(cost, band=1.0, step="symmetricP1")
    assert limited.status == "ok" and limited.distance > 0.0  # the pattern cannot follow the free cells
    assert "HH" not in "".join(unit_steps(limited.path))


# --- T-CMP-03d: +inf cells --------------------------------------------------------------------------------------------
def test_t_cmp_03d_a_finite_path_around_inf_cells_is_found_and_none_goes_through_one():
    cost = np.ones((5, 5))
    for i in (1, 2, 3):
        cost[i, i] = np.inf  # the diagonal is closed; a path must stay on one side of it
    result = dtw(cost, band=1.0, step="symmetric1")
    assert result.status == "ok" and result.accumulated == 6.0 and result.distance == 1.0
    upper_side = [[0, 0], [0, 1], [1, 2], [2, 3], [3, 4], [4, 4]]  # (i-1, k) is tried before (i, k-1)
    assert result.path.tolist() == upper_side
    assert dtw(cost, band=1.0, step="symmetricP1").status == "no_path"  # every first step of the pattern crosses (1, 1)


@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03d_a_path_never_visits_an_inf_cell_and_its_cost_is_finite(step):
    rng = np.random.default_rng(11 + STEPS.index(step))
    for cost, _, result in ok_cases(rng, step, 80, integer=True):
        assert np.isfinite(cost[result.path[:, 0], result.path[:, 1]]).all()
        assert math.isfinite(result.accumulated) and math.isfinite(result.distance) and math.isfinite(result.normalised)


@pytest.mark.parametrize("step", STEPS)
@pytest.mark.parametrize("where", ["a row", "a column", "the start", "the end", "everything"])
def test_t_cmp_03d_without_a_finite_path_the_result_is_no_path_and_not_an_error(step, where):
    cost = np.ones((6, 6))
    if where == "a row":
        cost[3, :] = np.inf
    elif where == "a column":
        cost[:, 3] = np.inf
    elif where == "the start":
        cost[0, 0] = np.inf
    elif where == "the end":
        cost[5, 5] = np.inf
    else:
        cost[:] = np.inf
    result = dtw(cost, band=1.0, step=step)
    assert result.status == "no_path"
    assert result.distance is None and result.accumulated is None and result.normalised is None
    assert result.path.shape == (0, 2) and result.path.dtype == np.int64 and not result.path.flags.writeable
    # a result without a path still says what was run
    assert result.params == {"band": 1.0, "step": step, "n": 6, "m": 6}


def test_t_cmp_03d_the_band_is_part_of_what_makes_a_path_impossible():
    cost = np.ones((2, 3))  # the end (1, 2) is reached through (1, 1), which is half a length off the diagonal
    assert dtw(cost, band=0.6, step="symmetricP1").status == "ok"
    narrow = dtw(cost, band=0.1, step="symmetricP1")
    assert narrow.status == "no_path"  # the middle cell of the compound step is outside


# --- T-CMP-03e: the distance and the normalisers ----------------------------------------------------------------------
@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03e_the_distance_is_the_mean_cost_of_the_listed_cells_and_accumulated_is_the_weighted_sum(step):
    rng = np.random.default_rng(41 + STEPS.index(step))
    for cost, _, result in ok_cases(rng, step, 80):
        listed = cost[result.path[:, 0], result.path[:, 1]]
        assert result.distance == pytest.approx(listed.sum() / len(result.path), rel=1e-12)
        assert result.accumulated == pytest.approx(weighted_cost(cost, result.path, step), rel=1e-12)
        n, m = cost.shape
        normaliser = n + m if step == "symmetricP1" else len(result.path)
        assert result.normalised == pytest.approx(result.accumulated / normaliser, rel=1e-12)


def test_t_cmp_03e_the_normaliser_of_the_slope_pattern_is_n_plus_m_and_of_the_unit_pattern_the_path_length():
    cost = np.full((6, 6), 2.0)
    p1 = dtw(cost, band=1.0, step="symmetricP1")  # every path weighs n + m = 12 in total: accumulated 24
    assert p1.accumulated == 24.0 and p1.normalised == 2.0 and p1.distance == 2.0
    one = dtw(cost, band=1.0, step="symmetric1")  # the diagonal: 6 cells
    assert one.accumulated == 12.0 and one.normalised == 2.0 and one.distance == 2.0
    ragged = np.full((3, 5), 2.0)
    assert dtw(ragged, band=1.0, step="symmetricP1").normalised == 2.0  # n + m = 8 whatever the path
    r = dtw(ragged, band=1.0, step="symmetric1")
    assert r.normalised == r.distance == 2.0 and r.accumulated == 2.0 * len(r.path)


def test_t_cmp_03e_distance_and_accumulated_are_python_floats_and_the_path_length_is_not_hidden():
    cost = np.array([[0.5, 1.0], [1.0, 0.25]])
    result = dtw(cost, band=1.0, step="symmetric1")
    assert type(result.distance) is float and type(result.accumulated) is float and type(result.normalised) is float
    assert result.distance == pytest.approx((0.5 + 0.25) / 2) and len(result.path) == 2


# --- T-CMP-03f: sizes, and the symmetry of the patterns ---------------------------------------------------------------
@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03f_a_single_cell(step):
    result = dtw(np.array([[0.75]]), band=0.1, step=step)
    assert result.status == "ok" and result.path.tolist() == [[0, 0]]
    assert result.distance == 0.75 and result.normalised == 0.75
    assert result.accumulated == (0.75 if step == "symmetric1" else 1.5)
    assert dtw(np.array([[np.inf]]), band=0.1, step=step).status == "no_path"


def test_t_cmp_03f_one_row_or_one_column():
    row = np.array([[1.0, 2.0, 4.0]])
    full = dtw(row, band=1.0, step="symmetric1")  # a row is walked left to right
    assert full.path.tolist() == [[0, 0], [0, 1], [0, 2]] and full.accumulated == 7.0 and full.distance == 7.0 / 3
    column = dtw(row.T.copy(), band=1.0, step="symmetric1")
    assert column.path.tolist() == [[0, 0], [1, 0], [2, 0]] and column.accumulated == 7.0
    for matrix in (row, row.T.copy()):
        assert dtw(matrix, band=0.5, step="symmetric1").status == "no_path"  # a single row sits at 0: the end is 1 away
        assert dtw(matrix, band=1.0, step="symmetricP1").status == "no_path"  # slope beyond 2
    assert dtw(np.array([[1.0, 2.0]]), band=1.0, step="symmetricP1").status == "no_path"


@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03f_a_transposed_matrix_gives_the_transposed_path(step):
    rng = np.random.default_rng(23 + STEPS.index(step))
    for cost, band, result in ok_cases(rng, step, 60):  # floats: no ties, so the best path is unique
        again = dtw(cost.T.copy(), band=band, step=step)
        assert again.status == "ok"
        assert np.array_equal(again.path, result.path[:, ::-1])
        assert again.accumulated == pytest.approx(result.accumulated, rel=1e-12)
        assert again.distance == pytest.approx(result.distance, rel=1e-12)


@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03f_a_transposed_matrix_has_the_same_accumulated_cost_even_with_ties(step):
    rng = np.random.default_rng(29 + STEPS.index(step))
    for cost, band, result in ok_cases(rng, step, 60, integer=True):
        again = dtw(cost.T.copy(), band=band, step=step)
        assert again.status == "ok" and again.accumulated == pytest.approx(result.accumulated, rel=1e-12)
    for n, m, band in [(7, 11, 0.3), (11, 7, 0.3), (4, 4, 0.1)]:
        assert np.array_equal(band_mask(n, m, band), band_mask(m, n, band).T)


# --- T-CMP-03g: refusals ----------------------------------------------------------------------------------------------
def _with(value: float, shape=(3, 3)) -> np.ndarray:
    cost = np.ones(shape)
    cost[1, 1] = value
    return cost


@pytest.mark.parametrize(
    ("label", "cost"),
    [
        ("NaN", _with(np.nan)),
        ("negative", _with(-0.5)),
        ("minus infinity", _with(-np.inf)),
        ("a tiny negative", np.array([[-1e-300]])),
        ("a vector", np.ones(4)),
        ("a stack of matrices", np.ones((2, 3, 3))),
        ("no rows", np.ones((0, 3))),
        ("no columns", np.ones((3, 0))),
        ("integers", np.ones((3, 3), dtype=np.int64)),
        ("booleans", np.ones((3, 3), dtype=np.bool_)),
        ("objects", np.ones((3, 3), dtype=object)),
        ("a list of lists", [[1.0, 2.0], [3.0, 4.0]]),
        ("None", None),
        ("a number", 1.0),
    ],
)
def test_t_cmp_03g_a_cost_that_is_not_a_matrix_of_costs_is_refused_naming_the_argument(label, cost):
    for step in STEPS:
        with pytest.raises(CompareError, match="cost"):
            dtw(cost, band=0.5, step=step)


def test_t_cmp_03g_the_cost_of_a_cost_matrix_object_is_its_values_and_anything_else_is_refused():
    @dataclasses.dataclass(frozen=True)
    class CostLike:  # stands in for P6.02's CostMatrix: a ``values`` array is all that is read
        values: object

    plain = np.array([[0.0, 1.0], [1.0, 0.0]])
    from_object = dtw(CostLike(plain), band=1.0, step="symmetric1")
    from_array = dtw(plain, band=1.0, step="symmetric1")
    assert from_object.accumulated == from_array.accumulated and np.array_equal(from_object.path, from_array.path)
    with pytest.raises(CompareError, match="cost"):
        dtw(CostLike([[0.0]]), band=1.0, step="symmetric1")
    with pytest.raises(CompareError, match="cost"):
        dtw(CostLike(_with(np.nan)), band=1.0, step="symmetric1")


def test_t_cmp_03g_any_floating_dtype_is_accepted_and_the_result_does_not_depend_on_it():
    base = np.random.default_rng(1).random((9, 9))
    as32 = base.astype(np.float32)
    for step in STEPS:
        a = dtw(as32, band=0.5, step=step)
        b = dtw(as32.astype(np.float64), band=0.5, step=step)
        assert a.status == b.status == "ok" and np.array_equal(a.path, b.path)
        assert a.accumulated == b.accumulated and a.normalised == b.normalised and a.distance == b.distance
        assert type(a.distance) is float  # not a float32: the sums are made in float64


WRONG_STEPS = ["symmetric2", "SYMMETRICP1", "", " symmetric1", None, 1, b"symmetric1", ["symmetric1"]]


@pytest.mark.parametrize("step", WRONG_STEPS)
def test_t_cmp_03g_an_unknown_step_is_refused_naming_the_argument(step):
    with pytest.raises(CompareError, match="step"):
        dtw(np.ones((3, 3)), band=0.5, step=step)


@pytest.mark.parametrize("band", [0, 0.0, -0.1, 1.0000001, 2, np.nan, np.inf, -np.inf, True, False, None, "0.5", [0.5]])
def test_t_cmp_03g_a_band_outside_zero_to_one_is_refused_naming_the_argument(band):
    for step in STEPS:
        with pytest.raises(CompareError, match="band"):
            dtw(np.ones((3, 3)), band=band, step=step)


def test_t_cmp_03g_band_and_step_have_no_default_and_are_keyword_only():
    cost = np.ones((3, 3))
    with pytest.raises(TypeError):
        dtw(cost, step="symmetric1")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        dtw(cost, band=0.5)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        dtw(cost, 0.5, "symmetric1")  # type: ignore[misc]
    with pytest.raises(TypeError):
        band_mask(3, 3)  # type: ignore[call-arg]


def test_t_cmp_03g_the_messages_never_echo_free_text():
    marker = "FREE-TEXT-MARKER-31"
    for call in (
        lambda: dtw(np.ones((3, 3)), band=0.5, step=marker),
        lambda: dtw(np.ones((3, 3)), band=marker, step="symmetric1"),
        lambda: dtw(marker, band=0.5, step="symmetric1"),
        lambda: band_mask(marker, 3, 0.5),
        lambda: band_mask(3, 3, marker),
    ):
        with pytest.raises(CompareError) as error:
            call()
        assert marker not in str(error.value)


@pytest.mark.parametrize(
    ("n", "m", "band", "argument"),
    [
        (0, 3, 0.5, "n"),
        (3, 0, 0.5, "m"),
        (-1, 3, 0.5, "n"),
        (3.0, 3, 0.5, "n"),
        (True, 3, 0.5, "n"),
        (3, None, 0.5, "m"),
        (3, 3, 0.0, "band"),
        (3, 3, 1.5, "band"),
        (3, 3, np.nan, "band"),
    ],
)
def test_t_cmp_03g_band_mask_refuses_what_it_cannot_draw(n, m, band, argument):
    with pytest.raises(CompareError, match=argument):
        band_mask(n, m, band)


# --- T-CMP-03h: ties, the echo, read-only results, timing -------------------------------------------------------------
def test_t_cmp_03h_ties_go_to_the_diagonal_first():
    for step in STEPS:
        zeros = dtw(np.zeros((6, 6)), band=1.0, step=step)  # every path costs 0: the diagonal is chosen
        assert zeros.path.tolist() == [[i, i] for i in range(6)]
    constant = dtw(np.ones((7, 7)), band=1.0, step="symmetricP1")  # every path weighs n + m: all tie
    assert constant.path.tolist() == [[i, i] for i in range(7)]
    wide = dtw(np.ones((3, 4)), band=1.0, step="symmetricP1")  # the last step ties with a compound one: diagonal first
    assert wide.path.tolist() == [[0, 0], [1, 1], [1, 2], [2, 3]]


def test_t_cmp_03h_unit_pattern_ties_between_up_and_left_go_to_up():
    cost = np.zeros((3, 3))
    cost[1, 1] = 100.0  # the diagonal is dear; (1, 2) and (2, 1) tie for the last step
    result = dtw(cost, band=1.0, step="symmetric1")
    assert result.accumulated == 0.0
    assert result.path.tolist() == [[0, 0], [0, 1], [1, 2], [2, 2]]  # up = (i - 1, k) is tried before left = (i, k - 1)


def test_t_cmp_03h_slope_pattern_ties_between_the_two_compound_steps_go_to_the_horizontal_one():
    cost = np.zeros((4, 4))
    cost[2, 2] = 100.0  # the diagonal step into (3, 3) is dear; from (2, 1) and from (1, 2) tie
    result = dtw(cost, band=1.0, step="symmetricP1")
    assert result.accumulated == 0.0
    assert result.path.tolist() == [[0, 0], [1, 1], [2, 1], [3, 2], [3, 3]]  # from (i-1, k-2) before from (i-2, k-1)


def test_t_cmp_03h_the_result_is_deterministic_and_equal_for_equal_input():
    cost = np.random.default_rng(8).integers(0, 3, size=(25, 25)).astype(np.float64)
    for step in STEPS:
        first, second = dtw(cost, band=0.4, step=step), dtw(cost.copy(), band=0.4, step=step)
        assert np.array_equal(first.path, second.path) and first.accumulated == second.accumulated


@pytest.mark.parametrize("step", STEPS)
def test_t_cmp_03h_the_settings_are_echoed(step):
    cost = np.random.default_rng(2).random((8, 11))
    result = dtw(cost, band=0.5, step=step)
    assert result.params == {"band": 0.5, "step": step, "n": 8, "m": 11}
    assert type(result.params["band"]) is float and type(result.params["n"]) is int and type(result.params["m"]) is int
    whole = dtw(cost, band=1, step=step).params["band"]  # an int is accepted and echoed as a float
    assert whole == 1.0 and type(whole) is float
    assert dtw(cost, band=np.float32(0.5), step=step).params["band"] == 0.5
    with pytest.raises(TypeError):
        result.params["band"] = 0.9  # type: ignore[index]


def test_t_cmp_03h_the_result_is_frozen_and_its_arrays_are_new_and_read_only():
    cost = np.random.default_rng(4).random((10, 10))
    cost.setflags(write=False)  # the cost of another module is read-only: it must be accepted and left as it was
    before = cost.copy()
    for step in STEPS:
        result = dtw(cost, band=0.5, step=step)
        assert not result.path.flags.writeable and not np.shares_memory(result.path, cost)
        with pytest.raises(ValueError, match="read-only"):
            result.path[0, 0] = 5
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.distance = 0.0  # type: ignore[misc]
        assert np.array_equal(cost, before)
    mutable = np.random.default_rng(4).random((10, 10))
    result = dtw(mutable, band=0.5, step="symmetric1")
    path = result.path.copy()
    mutable[:] = 99.0  # a later change of the input does not reach the result
    assert np.array_equal(result.path, path)


def test_t_cmp_03h_the_steps_are_the_two_of_the_plan_and_the_module_says_so():
    assert dtw_module.STEPS == STEPS


def test_t_cmp_03h_900_by_900_with_a_band_of_0_2_in_the_slope_pattern_is_fast_enough():
    rng = np.random.default_rng(900)
    x = np.sort(rng.random(900))
    y = np.sort(rng.random(900))
    cost = np.abs(x[:, None] - y[None, :]) + 0.01 * rng.random((900, 900))
    dtw(cost[:50, :50].copy(), band=0.2, step="symmetricP1")  # warm up the imports and the allocator
    started = time.perf_counter()
    result = dtw(cost, band=0.2, step="symmetricP1")
    elapsed = time.perf_counter() - started
    assert result.status == "ok" and result.path[-1].tolist() == [899, 899]
    assert elapsed < TIMING_BOUND_S, f"900 x 900 took {elapsed:.3f} s"
