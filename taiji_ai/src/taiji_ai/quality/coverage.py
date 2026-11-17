"""The coverage of the quality layer (W6, P4.07): how much of an interval the final layer measured, and why not.

``compute_coverage`` only **counts**: it reads the final layer (the Butterworth result), the grid and the gap table,
the swap flags and the times, and changes nothing (AGENTS.md section 5.1). The counts and their rules are documented
with the schema (``taiji_ai.schemas.quality``); in short, for each interval (the **segment** first, then the named
intervals of the caller):

* rows and cells are counted on the **grid** (a cell is exactly one of observed, bridged, missing; the reasons twice:
  every cell whose reason is not ``ok``, and the cells that are NaN); frames, mixed rows and the filter flags too. The
  time of a grid row is the step of the grid, so ``duration_s`` = rows x ``step_s``;
* the gap table and the swap flags live on the **source rows** and are counted there; for a gap, the cells of it that
  lie in the interval (a gap that starts in a 1 s margin and goes on into the segment is in the segment by those cells).

The **segment** is the stretch from the first to the last row with ``in_segment``, closed at both ends (+-1e-9 s): the
margins that the pose stage reads on both sides are in the layers (the filters need them) but not in the coverage. A
**named interval** is ``[start, end)`` in seconds of the stream, with 1e-9 s of tolerance at both ends (a row one float
step off a boundary is on the boundary). Intervals may overlap and may reach beyond the clip; one without rows has zero
counts. Rows are counted by their own time: a grid row that is the copy of an end row but lies up to the snap
tolerance of the grid (1 ms, X.31) outside the segment is not in it. The coverage judges nothing: "too low" is a
limit of a metric (AGENTS.md section 5.5).

Units: seconds from the stream start for times; counts are whole numbers. Nothing here is a keypoint value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

import numpy as np

from taiji_ai.pose.skeleton import JOINTS, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import is_real
from taiji_ai.quality.filters import FilterResult
from taiji_ai.quality.gaps import OUTCOME_NAMES, GapResult
from taiji_ai.quality.mask import NOT_TRACKED, REASON_NAMES
from taiji_ai.quality.resample import GridLayer
from taiji_ai.schemas.quality import (
    INTERVAL_NAME_RE,
    SEGMENT_NAME,
    GapCounts,
    IntervalCoverage,
    JointCoverage,
    OutcomeCounts,
    ReasonCounts,
)

_EPS_S: Final = 1e-9  # a row one float step off a boundary is on the boundary
_EPS_FRACTION: Final = 1e-9  # the boundary of the frame rule must not depend on float rounding (as in the mask)
_NAME = re.compile(INTERVAL_NAME_RE)
_REASON_CODES: Final = range(1, len(REASON_NAMES))  # the codes of the six reasons, in the order of ``ReasonCounts``


def parse_intervals(intervals: Mapping[str, tuple[float, float]] | None) -> list[tuple[str, float, float]]:
    """The named intervals as ``(name, start, end)`` in order; ``QualityError`` for anything that is not valid.

    ``intervals`` maps a name (letters, digits, ``_``, ``.``, ``-``; 1 to 64 characters; not ``segment``) to a pair
    ``(start, end)`` of finite seconds with ``start < end``.
    """
    if intervals is None:
        return []
    if not isinstance(intervals, Mapping):
        raise QualityError(f"intervals must be a mapping of name to (start, end) in seconds, got {intervals!r}")
    out = []
    for name, pair in intervals.items():
        if not (isinstance(name, str) and _NAME.fullmatch(name)):
            raise QualityError(f"interval name must match {INTERVAL_NAME_RE}, got {name!r}")
        if name == SEGMENT_NAME:
            raise QualityError(f"the interval name {SEGMENT_NAME!r} is reserved for the segment")
        if not (isinstance(pair, (tuple, list)) and len(pair) == 2):
            raise QualityError(f"interval {name!r} must be a (start, end) pair of seconds, got {pair!r}")
        start, end = pair
        if not (is_real(start) and is_real(end) and np.isfinite(start) and np.isfinite(end)):
            raise QualityError(f"interval {name!r}: start and end must be finite numbers of seconds, got {pair!r}")
        if not start < end:
            raise QualityError(f"interval {name!r}: start must be below end, got {pair!r}")
        out.append((name, float(start), float(end)))
    return out


def segment_bounds(t_sec: np.ndarray, in_segment: np.ndarray) -> tuple[float, float] | None:
    """The times of the first and the last row with ``in_segment``; ``None`` if there is none."""
    rows = np.flatnonzero(in_segment)
    if rows.size == 0:
        return None
    return float(t_sec[rows[0]]), float(t_sec[rows[-1]])


def segment_grid_rows(t_grid: np.ndarray, t_sec: np.ndarray, in_segment: np.ndarray) -> np.ndarray:
    """``(G,)`` bool: the grid rows of the segment, exactly the rows that ``compute_coverage`` counts in it.

    The segment is the stretch from the first to the last source row with ``in_segment``, closed at both ends (1e-9 s);
    no row is in it when there is none. ``pose_filtered.npz`` stores this mask and its reader recomputes it.
    """
    out = np.zeros(len(t_grid), dtype=bool)
    bounds = segment_bounds(t_sec, in_segment)
    if bounds is not None:
        out[_rows_between(t_grid, bounds[0], bounds[1], closed=True)] = True
    return out


def _rows_between(t: np.ndarray, start: float, end: float, *, closed: bool) -> slice:
    """The rows of the sorted times ``t`` in ``[start, end]`` (closed) or ``[start, end)``, with the tolerance."""
    lo = int(np.searchsorted(t, start - _EPS_S, side="left"))
    if closed:
        hi = int(np.searchsorted(t, end + _EPS_S, side="right"))
    else:
        hi = int(np.searchsorted(t, end - _EPS_S, side="left"))
    return slice(lo, hi)  # hi >= lo: the interval has start <= end (a segment of one row has start == end)


def _reasons(counts: np.ndarray) -> ReasonCounts:
    """``counts`` ``(6,)``: one count per reason, in the order of ``ReasonCounts``."""
    return ReasonCounts(**{REASON_NAMES[code]: int(counts[code - 1]) for code in _REASON_CODES})


def _outcomes(counts: np.ndarray) -> OutcomeCounts:
    return OutcomeCounts(**{name: int(counts[i]) for i, name in enumerate(OUTCOME_NAMES)})


def _gap_counts(gaps: GapResult, rows: slice) -> GapCounts:
    """The gaps by outcome with the cells of each that lie in the source rows ``rows``."""
    table = gaps.gaps
    start, end = table.start.astype(np.int64), table.end.astype(np.int64)
    inside = np.clip(np.minimum(end + 1, rows.stop) - np.maximum(start, rows.start), 0, None)
    hit = inside > 0
    outcome = table.outcome[hit].astype(np.int64)
    n_outcomes = len(OUTCOME_NAMES)
    n_gaps = np.bincount(outcome, minlength=n_outcomes)
    n_cells = np.bincount(outcome, weights=inside[hit], minlength=n_outcomes).astype(np.int64)
    return GapCounts(gaps=_outcomes(n_gaps), cells=_outcomes(n_cells))


def _interval(
    name: str,
    t_start: float | None,
    t_end: float | None,
    grid_rows: slice,
    source_rows: slice,
    *,
    grid: GridLayer,
    filtered: FilterResult,
    gaps: GapResult,
    suspect: np.ndarray,
    blocked: np.ndarray,
    essential: list[int],
    min_essential_fraction: float,
) -> IntervalCoverage:
    reason = filtered.reason[grid_rows]  # (r, 26) uint8
    value = ~np.isnan(filtered.keypoints[grid_rows][..., 0])  # (r, 26) bool: the cell has a value
    bridged = filtered.interpolated[grid_rows]  # implies a value
    observed = value & ~bridged
    missing = ~value
    rows = value.shape[0]
    by_reason_joint = np.stack([((reason == code) & missing).sum(axis=0) for code in _REASON_CODES])  # (6, 26)
    unobserved = np.array([(reason == code).sum() for code in _REASON_CODES])
    n_essential = value[:, essential].sum(axis=1)
    usable_frames = int((n_essential >= min_essential_fraction * len(essential) - _EPS_FRACTION).sum())
    not_tracked_frames = int((reason == NOT_TRACKED).all(axis=1).sum())
    flag = filtered.filtered[grid_rows]
    filtered_joint = flag.sum(axis=0)
    suspect_joint = suspect[source_rows].sum(axis=0)
    blocked_joint = blocked[source_rows].sum(axis=0)
    joints = tuple(
        JointCoverage(
            joint=JOINTS[j],
            observed=int(observed[:, j].sum()),
            bridged=int(bridged[:, j].sum()),
            missing=int(missing[:, j].sum()),
            missing_by_reason=_reasons(by_reason_joint[:, j]),
            filtered=int(filtered_joint[j]),
            suspect=int(suspect_joint[j]),
            blocked=int(blocked_joint[j]),
        )
        for j in range(NUM_JOINTS)
    )
    step = grid.gridmap.step_s
    if rows == 0:
        duration: float | None = 0.0
    else:
        duration = None if np.isnan(step) else float(rows * step)
    return IntervalCoverage(
        name=name,
        t_start=t_start,
        t_end=t_end,
        rows=rows,
        source_rows=source_rows.stop - source_rows.start,
        duration_s=duration,
        usable_frames=usable_frames,
        not_tracked_frames=not_tracked_frames,
        cells=rows * NUM_JOINTS,
        observed=int(observed.sum()),
        bridged=int(bridged.sum()),
        missing=int(missing.sum()),
        unobserved_by_reason=_reasons(unobserved),
        missing_by_reason=_reasons(by_reason_joint.sum(axis=1)),
        gaps=_gap_counts(gaps, source_rows),
        filtered=int(flag.sum()),
        unfiltered=int(value.sum()) - int(flag.sum()),
        suspect=int(suspect_joint.sum()),
        blocked=int(blocked_joint.sum()),
        mixed_rows=int(grid.mixed[grid_rows].sum()),
        joints=joints,
    )


def compute_coverage(
    *,
    t_sec: np.ndarray,
    in_segment: np.ndarray,
    gaps: GapResult,
    suspect: np.ndarray,
    blocked: np.ndarray,
    grid: GridLayer,
    filtered: FilterResult,
    essential: tuple[int, ...],
    min_essential_fraction: float,
    intervals: Mapping[str, tuple[float, float]] | None = None,
) -> tuple[IntervalCoverage, ...]:
    """The coverage of the segment and of every named interval, as a tuple (the segment first).

    ``t_sec`` ``(T,)`` the real row times (finite, strictly increasing); ``in_segment`` ``(T,)`` bool; ``gaps`` the gap
    layer and ``suspect`` and ``blocked`` ``(T, 26)`` bool the swap flags (all on the ``T`` source rows); ``grid`` the
    grid layer and ``filtered`` the final layer on the ``G`` grid rows; ``essential`` and ``min_essential_fraction`` the
    frame rule of the mask. Nothing is changed. Raises ``QualityError`` for wrong ``intervals``.
    """
    named = parse_intervals(intervals)
    t_grid = grid.gridmap.t_grid
    context: dict[str, Any] = {
        "grid": grid,
        "filtered": filtered,
        "gaps": gaps,
        "suspect": suspect,
        "blocked": blocked,
        "essential": list(essential),
        "min_essential_fraction": min_essential_fraction,
    }
    out = []
    bounds = segment_bounds(t_sec, in_segment)
    if bounds is None:
        out.append(_interval(SEGMENT_NAME, None, None, slice(0, 0), slice(0, 0), **context))
    else:
        t0, t1 = bounds
        out.append(
            _interval(
                SEGMENT_NAME,
                t0,
                t1,
                _rows_between(t_grid, t0, t1, closed=True),
                _rows_between(t_sec, t0, t1, closed=True),
                **context,
            )
        )
    for name, start, end in named:
        out.append(
            _interval(
                name,
                start,
                end,
                _rows_between(t_grid, start, end, closed=False),
                _rows_between(t_sec, start, end, closed=False),
                **context,
            )
        )
    return tuple(out)


def swap_warnings(t_sec: np.ndarray, in_segment: np.ndarray, blocked: np.ndarray) -> list[str]:
    """``lr_swap_suspect@<t0>-<t1>`` for each maximal run of source rows of the segment with a blocked cell.

    The times are those of the first and the last row of the run, seconds with two decimals (``@<t0>`` for one row);
    a run is clipped to the segment (the stretch from the first to the last row with ``in_segment``). In time order.
    """
    bounds = segment_bounds(t_sec, in_segment)
    if bounds is None:
        return []
    rows = _rows_between(t_sec, bounds[0], bounds[1], closed=True)
    flagged = np.zeros(len(t_sec), dtype=bool)
    flagged[rows] = blocked[rows].any(axis=1)
    edges = np.diff(np.concatenate([[False], flagged, [False]]).astype(np.int8))
    first, last = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1  # last is inclusive
    out = []
    for a, b in zip(first, last, strict=True):
        span = f"{t_sec[a]:.2f}" if a == b else f"{t_sec[a]:.2f}-{t_sec[b]:.2f}"
        out.append(f"lr_swap_suspect@{span}")
    return out
