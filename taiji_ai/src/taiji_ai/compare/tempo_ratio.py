"""The local tempo along the path on the real clock, and the deviation of each unit on the reference timeline (W8,
Appendix C.4, P6.04).

DTW compares shape; **tempo is reported on the original time axes** (W8). Both functions read an ``Alignment``
(``compare.align``) and give curves on **the reference's own timeline**: one entry per reference row ``k``, at the real
time ``t_ref(k)`` = ``reference.t_sec[k]`` (seconds, AGENTS.md 5.2: never a row index, never a constant fps), together
with the **matched query time** ``tau(k)`` = ``Alignment.matched_query_times()[k]`` (seconds; the mean query time of the
path cells ``(i, k)`` on that row), so that a display can put every point on the query's own clock too.

* **``local_tempo(alignment, *, smooth_s)``: the ratio** ``rho(k) = d t_query / d t_ref`` (Appendix C.4), in query
  seconds per reference second and dimensionless: above 1 the query takes longer than the reference at that moment,
  below 1 it is faster, 0 it stands still. It is the **ordinary least-squares slope of** ``tau`` **against** ``t_ref``
  over the window of the reference rows ``j`` with ``|t_ref(j) - t_ref(k)| <= smooth_s / 2`` (a span of seconds, so an
  uneven clock is handled; 1e-9 s is added to the edge so that a row exactly on it is in the window whatever the
  rounding of the clock), taking only the rows whose ``tau`` is observed (a reference row that no path cell touches
  has NaN and is left out, never filled). A window at the start or the end of the segment is one-sided. A window with
  fewer than two such rows, or whose squared spread of time is not above 0, gives **NaN with the reason**
  ``TempoReason.window_too_small`` (never 0; a ratio of 0 is a measurement: ``tau`` did not change). ``window_rows``
  says how many rows each fit used. ``smooth_s`` has **no default** (AGENTS.md 5.5; overview section 3.5; Appendix C
  suggests 0.5 s) and is echoed. **The module makes no judgement of the tempo**: no band, no "too slow": a threshold
  comes from a signed record later. ``whole_ratio`` is the ratio of the two segments' durations,
  ``(t_q,end - t_q,start) / (t_r,end - t_r,start)`` from their clocks (not from ``tau``), NaN with a reason when a
  segment has fewer than two rows (a single frame has no duration).
* **``deviation_curve(alignment)``: the deviation of each unit.** For each reference row ``k`` and unit ``u``, the
  **mean over the path cells** ``(i, k)`` **where the unit is valid in both frames** of ``||q_u(i) - r_u(k)||``, the
  Euclidean norm of the difference of the two stored 2-vectors (as the cost of ``compare.cost``): a *position* in trunk
  lengths, an *angle* the chord ``2 |sin((a - b) / 2)|`` from 0 (the same direction) to 2 (opposite). Where the unit is
  valid in no cell of the row it is **NaN with the reason** ``DeviationReason.not_valid_in_both`` (never 0), and
  ``n_valid`` counts the cells that the mean is made of. A unit of **weight 0** in the alignment is still reported (a
  deviation, not a cost). ``total`` is the mean over the cells of the row of the alignment's own cost ``c(i, k)``
  (weights and ``min_visible`` as in the alignment; NaN for a row without a cell). The stored value under a false mask
  is never read.
* **No path is a result, not an error** (``alignment.result.status == "no_path"``): both curves are NaN with the reason
  ``no_path`` in every row, never zeros; ``status`` echoes it and ``t_ref`` is still the reference's clock.
* **Inputs.** ``alignment`` must be an ``Alignment``; the module also checks what it reads, because only ``align``
  guarantees it and a hand-made ``Alignment`` is possible: each clock is a one-dimensional finite strictly increasing
  float array with one entry per row (AGENTS.md 5.2), the arrays fit each other and the cost, every valid feature has a
  finite value, and the path of an ``ok`` result lies inside the matrix. ``CompareError`` names the argument; a number
  or a type is echoed, never a string given by the caller. The curves say which alignment they come from
  (``reference_recording_id``, ``query_recording_id``, ``settings``: the alignment's read-only fingerprint).

The tempo of two *different* movements is not a tempo ratio: the path of such a pair wanders (SYN-11, another action:
ratios from 0.5 to 2), so the caller asks ``compare.guards.check_comparable`` first, as for ``align``.

The arrays of a result are new and read-only; the alignment is never changed. Appendix C.4 is the design; no third-party
code is used.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

import numpy as np

from taiji_ai.compare import CompareError
from taiji_ai.compare.align import Alignment
from taiji_ai.compare.features import FeatureUnit, FrameFeatures

_EDGE_S: Final = 1e-9  # seconds added to the edge of a window: a row exactly on it is in (a clock is not exact)


class TempoReason(enum.IntEnum):
    """Why a ratio is NaN: 0 it is a value; 1 the window holds fewer than two rows with an observed matched time or no
    spread of time; 2 there is no path."""

    valid = 0
    window_too_small = 1
    no_path = 2


class DeviationReason(enum.IntEnum):
    """Why a deviation is NaN: 0 it is a value; 1 no path cell of the row has the unit valid in both frames; 2 there is
    no path; 3 no path cell lies on the row (only a path that does not run from corner to corner)."""

    valid = 0
    not_valid_in_both = 1
    no_path = 2
    no_cell = 3


@dataclass(frozen=True, eq=False)
class TempoCurve:
    """The local tempo on the reference timeline; every array is a new read-only array of one entry per reference row.

    ``t_ref`` ``(m,)`` float64 seconds: the reference's real clock. ``t_query`` ``(m,)`` float64 seconds: the matched
    query time (NaN where no path cell lies on the row). ``ratio`` ``(m,)`` float64: ``rho(k)``, query seconds per
    reference second (dimensionless), NaN where ``reason`` is not 0. ``reason`` ``(m,)`` uint8 (``TempoReason``).
    ``window_rows`` ``(m,)`` int64: the rows of the window with an observed matched time, the evidence behind a ratio
    (0 without a path). ``smooth_s`` the window in seconds as used (a Python float). ``whole_ratio`` the ratio of the
    two segments' durations (NaN where ``whole_reason`` is not 0; ``whole_reason`` an ``int`` of ``TempoReason``).
    ``status`` ``"ok"`` or ``"no_path"`` as the alignment's; ``reference_recording_id`` and ``query_recording_id`` the
    provenance; ``settings`` the alignment's read-only fingerprint.
    """

    t_ref: np.ndarray
    t_query: np.ndarray
    ratio: np.ndarray
    reason: np.ndarray
    window_rows: np.ndarray
    smooth_s: float
    whole_ratio: float
    whole_reason: int
    status: Literal["ok", "no_path"]
    reference_recording_id: str
    query_recording_id: str
    settings: Mapping[str, object]


@dataclass(frozen=True, eq=False)
class DeviationCurve:
    """The deviation of each unit on the reference timeline; every array is a new read-only array.

    ``t_ref`` ``(m,)`` and ``t_query`` ``(m,)`` float64 seconds as in ``TempoCurve``. ``values`` ``(m, U)`` float64: the
    mean over the path cells on the row with the unit valid in both of the distance between the two stored vectors (a
    position in trunk lengths, an angle the chord 0 to 2), NaN where ``reason`` is not 0. ``reason`` ``(m, U)`` uint8
    (``DeviationReason``). ``n_valid`` ``(m, U)`` int64: the cells that each mean is made of. ``cells`` ``(m,)`` int64:
    the path cells on the row. ``total`` ``(m,)`` float64: the mean of the alignment's cost over those cells (NaN
    without one). ``units`` the ``U`` unit names and ``kinds`` their kinds (``"position"`` or ``"angle"``), in the
    features' order. ``status``, ``reference_recording_id``, ``query_recording_id`` and ``settings`` as in
    ``TempoCurve``.
    """

    t_ref: np.ndarray
    t_query: np.ndarray
    values: np.ndarray
    reason: np.ndarray
    n_valid: np.ndarray
    cells: np.ndarray
    total: np.ndarray
    units: tuple[str, ...]
    kinds: tuple[str, ...]
    status: Literal["ok", "no_path"]
    reference_recording_id: str
    query_recording_id: str
    settings: Mapping[str, object]


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _as_float(value: Any) -> float:
    """``float(value)``, except that an integer beyond the range of a float is an infinity of its own sign (BUG-0079),
    which the check refuses, instead of an ``OverflowError``."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _shown(value: Any) -> str:
    """What an error says of an argument: the number itself, or only the type (never a string of the caller)."""
    return repr(_as_float(value)) if _is_number(value) else type(value).__name__


def _describe(value: Any) -> str:
    return f"{value.dtype} array of shape {value.shape}" if isinstance(value, np.ndarray) else type(value).__name__


def _check_smooth(smooth_s: Any) -> float:
    if not _is_number(smooth_s) or not math.isfinite(_as_float(smooth_s)) or _as_float(smooth_s) <= 0.0:
        raise CompareError(
            f"smooth_s must be a finite number above 0 (seconds of the reference clock), got {_shown(smooth_s)}"
        )
    return _as_float(smooth_s)


def _check_features(features: Any, name: str) -> FrameFeatures:
    """``features`` if its arrays agree with each other, its clock is a clock and its valid features have values."""
    if not isinstance(features, FrameFeatures):
        raise CompareError(f"{name} must be a FrameFeatures, got {type(features).__name__}")
    values, valid, t = features.values, features.valid, features.t_sec
    if not isinstance(values, np.ndarray) or values.dtype.kind != "f" or values.ndim != 3 or values.shape[2] != 2:
        raise CompareError(f"{name}.values must be a floating-point array of shape (N, U, 2), got {_describe(values)}")
    rows, units = values.shape[:2]
    if not isinstance(valid, np.ndarray) or valid.dtype != np.bool_ or valid.shape != (rows, units):
        raise CompareError(f"{name}.valid must be a bool array of shape {(rows, units)}, got {_describe(valid)}")
    if not isinstance(features.units, tuple) or len(features.units) != units:
        raise CompareError(f"{name}.units must be a tuple with one entry per column of values ({units})")
    if not all(isinstance(unit, FeatureUnit) for unit in features.units):
        raise CompareError(f"{name}.units must be a tuple of FeatureUnit")
    if not isinstance(t, np.ndarray) or t.dtype.kind != "f" or t.ndim != 1:
        raise CompareError(f"{name}.t_sec must be a one-dimensional float array, got {_describe(t)}")
    if t.shape[0] != rows:
        raise CompareError(f"{name}.t_sec must have one entry per row of values ({rows}), got {t.shape[0]}")
    if not np.isfinite(t).all():
        raise CompareError(f"{name}.t_sec must be finite: it is the real clock in seconds")
    if (np.diff(t) <= 0.0).any():
        raise CompareError(f"{name}.t_sec must be strictly increasing: it is the real clock in seconds")
    if not np.isfinite(values[valid]).all():  # a feature that says it is valid and has no value is a producer defect
        raise CompareError(f"{name}: a valid feature has a non-finite value (it must be marked not valid instead)")
    return features


def _check_alignment(alignment: Any) -> Alignment:
    """``alignment`` if it is an ``Alignment`` whose parts fit each other (see the module docstring)."""
    if not isinstance(alignment, Alignment):
        raise CompareError(f"alignment must be an Alignment, got {type(alignment).__name__}")
    reference = _check_features(alignment.reference, "alignment.reference")
    query = _check_features(alignment.query, "alignment.query")
    rows_ref, rows_qry = reference.values.shape[0], query.values.shape[0]
    if reference.values.shape[1] != query.values.shape[1]:
        raise CompareError("alignment.reference and alignment.query must have the same number of units")
    cost = getattr(alignment.cost, "values", None)
    if not isinstance(cost, np.ndarray) or cost.shape != (rows_qry, rows_ref):
        raise CompareError(
            f"alignment.cost must be a CostMatrix of shape (query rows, reference rows) = {(rows_qry, rows_ref)}, "
            f"got {_describe(cost)}"
        )
    status = alignment.result.status
    if status not in ("ok", "no_path"):
        raise CompareError(f"alignment.result.status must be 'ok' or 'no_path', got {type(status).__name__}")
    if status == "ok":
        path = alignment.result.path
        if not isinstance(path, np.ndarray) or path.dtype.kind != "i" or path.ndim != 2 or path.shape[1] != 2:
            raise CompareError(f"alignment.result.path must be an integer array of shape (L, 2), got {_describe(path)}")
        if path.size and (path.min() < 0 or (path[:, 0] >= rows_qry).any() or (path[:, 1] >= rows_ref).any()):
            raise CompareError(
                "alignment.result.path must lie inside the cost matrix: a cell is (query row, reference row)"
            )
    return alignment


def local_tempo(alignment: Alignment, *, smooth_s: float) -> TempoCurve:
    """The local tempo ratio ``rho(k)`` along the path on the real clock, on the reference timeline (module docstring).

    ``alignment``: an ``Alignment`` (``compare.align.align``). ``smooth_s``: the width of the window in **seconds of
    the reference clock**, a finite number above 0 with no default (Appendix C suggests 0.5 s). Returns a
    ``TempoCurve`` of one entry per reference row; the ratio is query seconds per reference second (dimensionless),
    NaN with a reason where the window is too small or there is no path. ``CompareError`` naming the argument for an
    argument or an alignment it cannot use; the alignment is not changed.
    """
    a = _check_alignment(alignment)
    window = _check_smooth(smooth_s)
    t_ref = _frozen(np.array(a.reference.t_sec, dtype=np.float64))
    t_query = a.matched_query_times()
    m = t_ref.shape[0]
    ratio = np.full(m, math.nan)
    reason = np.full(m, TempoReason.no_path, dtype=np.uint8)
    rows = np.zeros(m, dtype=np.int64)
    whole, whole_reason = math.nan, TempoReason.no_path
    if a.result.status == "ok":
        half = window / 2.0 + _EDGE_S
        first = np.searchsorted(t_ref, t_ref - half, side="left")
        last = np.searchsorted(t_ref, t_ref + half, side="right")
        observed = np.isfinite(t_query)
        for k in range(m):
            span = slice(int(first[k]), int(last[k]))
            seen = observed[span]
            rows[k] = int(seen.sum())
            reason[k] = TempoReason.window_too_small
            if rows[k] < 2:
                continue
            dt, dq = t_ref[span][seen], t_query[span][seen]
            dt, dq = dt - dt.mean(), dq - dq.mean()  # centred on the window's own mean
            spread = float(dt @ dt)
            if not spread > 0.0:  # the squared spread underflowed: there is no slope to give
                continue
            ratio[k] = float(dt @ dq) / spread
            reason[k] = TempoReason.valid
        whole_reason = TempoReason.window_too_small
        clock_q = a.query.t_sec
        if m >= 2 and clock_q.shape[0] >= 2:
            whole = float((clock_q[-1] - clock_q[0]) / (t_ref[-1] - t_ref[0]))
            whole_reason = TempoReason.valid
    return TempoCurve(
        t_ref=t_ref,
        t_query=t_query,
        ratio=_frozen(ratio),
        reason=_frozen(reason),
        window_rows=_frozen(rows),
        smooth_s=window,
        whole_ratio=whole,
        whole_reason=int(whole_reason),
        status=a.result.status,
        reference_recording_id=a.reference.recording_id,
        query_recording_id=a.query.recording_id,
        settings=a.settings,
    )


def deviation_curve(alignment: Alignment) -> DeviationCurve:
    """The deviation of each unit on the reference timeline (module docstring).

    ``alignment``: an ``Alignment``. Returns a ``DeviationCurve``: for each reference row and unit, the mean over the
    path cells on the row with the unit valid in both frames of the distance between the two stored vectors (trunk
    lengths for a position, the chord 0 to 2 for an angle), NaN with a reason where there is none or no path. A unit of
    weight 0 is reported too. ``CompareError`` naming the argument for an alignment it cannot use; the alignment is not
    changed.
    """
    a = _check_alignment(alignment)
    reference, query = a.reference, a.query
    m, units = reference.valid.shape
    values = np.full((m, units), math.nan)
    n_valid = np.zeros((m, units), dtype=np.int64)
    cells = np.zeros(m, dtype=np.int64)
    total = np.full(m, math.nan)
    reason = np.full((m, units), DeviationReason.no_path, dtype=np.uint8)
    if a.result.status == "ok":
        query_row, reference_row = a.result.path[:, 0], a.result.path[:, 1]
        cells = np.bincount(reference_row, minlength=m).astype(np.int64)
        both = query.valid[query_row] & reference.valid[reference_row]  # (L, U): valid in both frames of the cell
        # a value under a false mask is never read: the zero is a placeholder that ``both`` excludes, not data
        qv = np.where(query.valid[:, :, None], query.values, 0.0)
        rv = np.where(reference.valid[:, :, None], reference.values, 0.0)
        distance = np.hypot(
            qv[query_row, :, 0] - rv[reference_row, :, 0], qv[query_row, :, 1] - rv[reference_row, :, 1]
        )
        for u in range(units):
            used = both[:, u]
            n_valid[:, u] = np.bincount(reference_row[used], minlength=m)
            sums = np.bincount(reference_row[used], weights=distance[used, u], minlength=m)
            np.divide(sums, n_valid[:, u], out=values[:, u], where=n_valid[:, u] > 0)
        cost = np.bincount(reference_row, weights=a.cost.values[query_row, reference_row], minlength=m)
        np.divide(cost, cells, out=total, where=cells > 0)
        reason = np.where(n_valid > 0, DeviationReason.valid, DeviationReason.not_valid_in_both).astype(np.uint8)
        reason[cells == 0] = DeviationReason.no_cell
    return DeviationCurve(
        t_ref=_frozen(np.array(reference.t_sec, dtype=np.float64)),
        t_query=a.matched_query_times(),
        values=_frozen(values),
        reason=_frozen(reason),
        n_valid=_frozen(n_valid),
        cells=_frozen(cells),
        total=_frozen(total),
        units=tuple(unit.name for unit in reference.units),
        kinds=tuple(unit.kind for unit in reference.units),
        status=a.result.status,
        reference_recording_id=reference.recording_id,
        query_recording_id=query.recording_id,
        settings=a.settings,
    )
