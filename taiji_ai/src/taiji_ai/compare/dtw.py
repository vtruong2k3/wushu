"""Constrained dynamic time warping on a cost matrix (W8, Appendix C.3 and C.4, P6.03a): the warping path of minimum
cost inside a Sakoe-Chiba band, with a step pattern, and the shape distance ``D`` of that path.

``dtw(cost, *, band, step)`` reads any ``(n, m)`` matrix of costs: **axis 0 is the query** (rows ``i``), **axis 1 the
reference** (columns ``k``); the values are finite and non-negative, or ``+inf`` for a cell that cannot be used, in the
unit of whatever built them (the masked cost of P6.02 is dimensionless: trunk lengths and chords). It does not know
frames, seconds or joints: a row index is not a time. The tempo is read from the *real clock* of the two segments,
never from the path (``FrameFeatures.t_sec``; W8: shape is compared with DTW, tempo is reported on the original time
axes).

**Band.** A cell ``(i, k)`` is allowed when ``|i / (n - 1) - k / (m - 1)| <= band`` (with 1e-12 of tolerance, so that a
cell exactly on the edge is in the band whatever the rounding of the fractions; a side of one element counts as 0).
``band`` is the Sakoe-Chiba half-width as a fraction of the length, in ``(0, 1]``, with no default (AGENTS.md 5.5;
Appendix C suggests 0.1 to 0.2): ``1`` is no band. Appendix C writes ``i / n``; with ``n - 1`` and ``m - 1`` the two
corners ``(0, 0)`` and ``(n - 1, m - 1)`` are on the diagonal, so for ``n, m >= 2`` a band never excludes the start or
the end of a path. A matrix of one row (or column) has no diagonal: its end cell is 1 away from the start, so a band
below 1 leaves no path (``no_path``).

**Step patterns** (``STEPS``). ``g`` is the accumulated cost and ``c`` the cost; a cell outside the band or at ``+inf``
cannot be used, as the middle cell of a compound step either.

* ``symmetric1``: unit steps, ``g(i, k) = c(i, k) + min(g(i-1, k-1), g(i-1, k), g(i, k-1))``, ``g(0, 0) = c(0, 0)``. No
  slope limit. It is the classical pattern (the one ``dtaidistance`` runs) and exists so that the implementation can be
  checked against an independent one. Normaliser: the length of the path.
* ``symmetricP1``: Sakoe and Chiba's symmetric pattern with the slope constraint ``P = 1`` (the product's pattern, as
  Appendix C.3 suggests). ``g(0, 0) = 2 c(0, 0)`` and ``g(i, k)`` is the minimum of ``g(i-1, k-1) + 2 c(i, k)``,
  ``g(i-1, k-2) + 2 c(i, k-1) + c(i, k)`` and ``g(i-2, k-1) + 2 c(i-1, k) + c(i, k)``. The slope stays between 1/2
  and 2: a horizontal or a vertical unit step always follows a diagonal one and is followed by one (or ends the path),
  so there are never two in a row. A pair of lengths with ``m - 1 > 2 (n - 1)`` or the reverse has no such path
  (``no_path``). Normaliser: ``n + m``, the sum of the weights of any path.

The path lists the middle cell of a compound step, so every step of the returned path is one of the three unit steps
``(1, 1)``, ``(1, 0)``, ``(0, 1)``. **Ties** go to the first candidate of this order, so a result is deterministic:
``symmetric1`` the diagonal ``(i-1, k-1)``, then ``(i-1, k)``, then ``(i, k-1)``; ``symmetricP1`` the diagonal step,
then the step from ``(i-1, k-2)``, then the step from ``(i-2, k-1)``. The best path in a tie is not unique and ``D``
depends on which one is returned (the mean is over the cells of the path); the accumulated cost does not.

**Result.** ``DtwResult.distance`` is ``D = sum(c(path)) / len(path)`` (Appendix C.4), the plain mean of the cost over
the listed cells (the weights of the pattern are in ``accumulated``, not in ``D``). ``accumulated`` is the cost at the
end of the DP and ``normalised`` is it divided by the pattern's normaliser. When no finite path exists (``+inf`` cells,
the band, the slope) the result is ``status="no_path"`` with an empty path and ``None`` for ``distance``,
``accumulated`` and ``normalised`` (no number that could be added or compared by mistake). ``params`` echoes ``band``,
``step``, ``n`` and ``m`` so that distances made with different settings are never put in one band (P6.06).

The arrays of a result are new and read-only. Open-begin and open-end (Appendix C.3) are not in this version.

Sources of the idea (no code copied): H. Sakoe and S. Chiba, "Dynamic programming algorithm optimization for spoken
word recognition", IEEE Trans. ASSP 26(1), 1978, DOI 10.1109/TASSP.1978.1163055 (the band, the symmetric pattern with
the slope constraint ``P`` and its normaliser); T. Giorgino, "Computing and visualizing dynamic time warping
alignments in R: the dtw package", J. Stat. Softw. 31(7), 2009, DOI 10.18637/jss.v031.i07 (the notation of the step
patterns).

Errors are ``CompareError`` naming the argument; a comparison with no path is a result, not an error.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal

import numpy as np

from taiji_ai.compare import CompareError

STEPS: Final = ("symmetric1", "symmetricP1")  # the step patterns of this module (the docstring says what each is)
_BAND_TOLERANCE: Final = 1e-12  # a cell this close to the edge is on it (fractions of a length are not exact)


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _describe(value: Any) -> str:
    return f"{value.dtype} array of shape {value.shape}" if isinstance(value, np.ndarray) else type(value).__name__


def _shown(value: Any) -> str:
    """A number as it is, anything else by its type: a message never echoes text the caller passed."""
    return repr(_as_float(value)) if _is_number(value) else type(value).__name__


def _as_float(value: Any) -> float:
    """``float(value)``, except that an integer beyond the range of a float is an infinity (BUG-0079), which every
    check below refuses, instead of an ``OverflowError``."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _check_band(band: Any) -> float:
    if not _is_number(band) or not 0.0 < _as_float(band) <= 1.0:  # NaN and infinity fail the comparison
        raise CompareError(
            "band must be a number in (0, 1], the half-width of the Sakoe-Chiba band as a fraction of the length, "
            f"got {_shown(band)}"
        )
    return _as_float(band)


def _check_size(value: Any, name: str) -> int:
    if not isinstance(value, (int, np.integer)) or isinstance(value, (bool, np.bool_)) or value < 1:
        raise CompareError(f"{name} must be an integer of at least 1, got {_shown(value)}")
    return int(value)


def _check_step(step: Any) -> str:
    if not isinstance(step, str) or step not in STEPS:
        raise CompareError(f"step must be one of {', '.join(STEPS)}, got {_shown(step)}")
    return step


def _check_cost(cost: Any) -> np.ndarray:
    """The cost as a float64 array (the caller's own when it is one; never written to); ``CompareError`` if it is not a
    matrix of costs."""
    values = cost if isinstance(cost, np.ndarray) else getattr(cost, "values", cost)  # a CostMatrix gives its values
    if not isinstance(values, np.ndarray) or values.dtype.kind != "f" or values.ndim != 2:
        raise CompareError(
            f"cost must be a two-dimensional floating-point array (or an object whose values are one), "
            f"got {_describe(values)}"
        )
    if values.shape[0] == 0 or values.shape[1] == 0:
        raise CompareError(f"cost must have at least one row and one column, got shape {values.shape}")
    if np.isnan(values).any():
        raise CompareError("cost must not contain NaN: a cell that cannot be used is +inf")
    if (values < 0.0).any():
        raise CompareError("cost must not be negative (-inf included): a cell that cannot be used is +inf")
    return np.asarray(values, dtype=np.float64)


def band_mask(n: int, m: int, band: float) -> np.ndarray:
    """``(n, m)`` bool, read-only: the cells ``(i, k)`` with ``|i / (n - 1) - k / (m - 1)| <= band`` (1e-12 tolerance).

    ``band`` is the half-width as a fraction of the length, in ``(0, 1]`` (``1``: every cell). A side of one element has
    the coordinate 0. ``CompareError`` for a size below 1 or a band outside ``(0, 1]``.
    """
    rows, cols = _check_size(n, "n"), _check_size(m, "m")
    half = _check_band(band)
    x = np.arange(rows) / (rows - 1) if rows > 1 else np.zeros(1)
    y = np.arange(cols) / (cols - 1) if cols > 1 else np.zeros(1)
    return _frozen(np.abs(x[:, None] - y[None, :]) <= half + _BAND_TOLERANCE)


@dataclass(frozen=True, eq=False)
class DtwResult:
    """The warping path of a cost matrix and its distance.

    ``path`` ``(L, 2)`` int64, read-only: the cells ``(i, k)`` (query row, reference row; 0-based indices, not times)
    from ``(0, 0)`` to ``(n - 1, m - 1)``, every step one of ``(1, 1)``, ``(1, 0)``, ``(0, 1)``, every cell in the band
    and at a finite cost; empty ``(0, 2)`` when there is no path. ``distance`` is ``D = sum(c(path)) / L`` (Appendix
    C.4, in the unit of the cost); ``accumulated`` the cost at the end of the DP under the weights of the step pattern;
    ``normalised`` that divided by the pattern's normaliser (``n + m`` for ``symmetricP1``, ``L`` for ``symmetric1``).
    All three are ``None`` when ``status`` is ``"no_path"`` (``"ok"`` otherwise). ``params`` is a read-only mapping
    with ``band`` (float), ``step``, ``n`` and ``m``: the settings that made the result.
    """

    path: np.ndarray
    distance: float | None
    status: Literal["ok", "no_path"]
    accumulated: float | None
    normalised: float | None
    params: Mapping[str, object]


# Backpointers (int8): which candidate of the tie order won the cell. ``symmetric1``: 0 diagonal, 1 up, 2 left.
# ``symmetricP1``: 0 diagonal step, 1 from (i-1, k-2) through (i, k-1), 2 from (i-2, k-1) through (i-1, k).
def _accumulate_unit(c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The DP of ``symmetric1`` over ``c`` (``+inf`` outside the band): ``(g, back)``, both ``(n, m)``."""
    n, m = c.shape
    g = np.full((n, m), math.inf)
    back = np.zeros((n, m), dtype=np.int8)
    padded = np.full(m + 1, math.inf)  # padded[k + 1] = g(i-1, k), padded[0] = +inf (there is no column -1)
    for i in range(n):
        diagonal, up = padded[:-1], padded[1:]  # g(i-1, k-1) and g(i-1, k)
        best = np.minimum(diagonal, up).tolist()
        move = np.argmin(np.stack((diagonal, up)), axis=0).tolist()  # the first on a tie: the diagonal
        cost_row = c[i].tolist()
        row = [math.inf] * m
        left = math.inf
        for k in range(m):
            lowest = best[k]
            if i == 0 and k == 0:
                lowest = 0.0  # the start: nothing before it
            elif left < lowest:  # strictly: on a tie the diagonal or the up cell stays
                lowest = left
                move[k] = 2
            left = row[k] = cost_row[k] + lowest
        g[i] = row
        back[i] = move
        padded[1:] = g[i]
    return g, back


def _accumulate_p1(c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The DP of ``symmetricP1`` over ``c`` (``+inf`` outside the band): ``(g, back)``, one vectorised step per row."""
    n, m = c.shape
    g = np.full((n, m), math.inf)
    back = np.zeros((n, m), dtype=np.int8)
    g[0, 0] = 2.0 * c[0, 0]
    columns = np.arange(m)
    for i in range(1, n):
        row = c[i]
        candidates = np.full((3, m), math.inf)
        candidates[0, 1:] = g[i - 1, :-1] + 2.0 * row[1:]
        candidates[1, 2:] = g[i - 1, :-2] + 2.0 * row[1:-1] + row[2:]
        if i >= 2:
            candidates[2, 1:] = g[i - 2, :-1] + 2.0 * c[i - 1, 1:] + row[1:]
        move = np.argmin(candidates, axis=0)  # the first on a tie: diagonal, then horizontal, then vertical
        g[i] = candidates[move, columns]
        back[i] = move
    return g, back


def _backtrack_unit(back: np.ndarray, n: int, m: int) -> list[tuple[int, int]]:
    i, k = n - 1, m - 1
    cells = [(i, k)]
    while (i, k) != (0, 0):
        move = back[i, k]
        if move == 0:
            i, k = i - 1, k - 1
        elif move == 1:
            i -= 1
        else:
            k -= 1
        cells.append((i, k))
    cells.reverse()
    return cells


def _backtrack_p1(back: np.ndarray, n: int, m: int) -> list[tuple[int, int]]:
    i, k = n - 1, m - 1
    cells: list[tuple[int, int]] = []
    while (i, k) != (0, 0):
        move = back[i, k]
        if move == 0:
            cells.append((i, k))
            i, k = i - 1, k - 1
        elif move == 1:
            cells.extend(((i, k), (i, k - 1)))
            i, k = i - 1, k - 2
        else:
            cells.extend(((i, k), (i - 1, k)))
            i, k = i - 2, k - 1
    cells.append((0, 0))
    cells.reverse()
    return cells


def dtw(cost: Any, *, band: float, step: str) -> DtwResult:
    """The warping path of minimum cost through ``cost`` inside the band, and its distance.

    ``cost`` is an ``(n, m)`` floating-point array (axis 0 the query, axis 1 the reference) of finite non-negative
    values and ``+inf``, or an object whose ``values`` is one (a ``CostMatrix``); ``band`` in ``(0, 1]`` and ``step``
    (one of ``STEPS``) have no default. The input is not changed and the result shares no memory with it.
    ``CompareError`` for NaN, a negative value, ``-inf``, an array that is not two-dimensional floating point or has no
    cell, an unknown step or a band outside ``(0, 1]``. No finite path is a result: ``status="no_path"``.
    """
    c = _check_cost(cost)
    half = _check_band(band)
    name = _check_step(step)
    n, m = c.shape
    params = MappingProxyType({"band": half, "step": name, "n": n, "m": m})
    inside = np.where(band_mask(n, m, half), c, math.inf)  # outside the band a cell cannot be used
    g, back = _accumulate_unit(inside) if name == "symmetric1" else _accumulate_p1(inside)
    end = float(g[n - 1, m - 1])
    if not math.isfinite(end):
        return DtwResult(_frozen(np.empty((0, 2), dtype=np.int64)), None, "no_path", None, None, params)
    cells = _backtrack_unit(back, n, m) if name == "symmetric1" else _backtrack_p1(back, n, m)
    path = _frozen(np.array(cells, dtype=np.int64))
    length = len(path)
    distance = float(c[path[:, 0], path[:, 1]].sum()) / length
    normaliser = n + m if name == "symmetricP1" else length
    return DtwResult(path, distance, "ok", end, end / normaliser, params)
