"""The glue every metric uses (W7, P5.03 to P5.06): the rows of a segment and their neighbours, the stable intervals,
the eligibility of a row, the runs that are too short, the reason a summary gives when it has no evidence, the assembly
of a series and the scale of a set of rows.

A metric reads the **final layer** (``PoseFiltered``, ``pose_filtered.npz``) of one segment: ``G`` grid rows, of which
the rows of ``grid_in_segment`` are the segment (the margins that the pose pass read around it are not). A series has
one row per row of the segment, so:

* ``segment_rows`` cuts those rows out (copies, read-only) with the real clock ``t_sec`` (seconds from the stream
  start), the positions (float32 pixels, y down), the reasons and the ``interpolated`` flags. Its ``step_s`` is the
  layer's step, and ``None`` for fewer than two rows: a series of one row has no step (``MetricHeader``) and a single
  row has no duration.
* ``neighbour_rows`` gives, for every row of the segment, the grid row before and the grid row after it (positions,
  reasons, flags, time), margins included: a difference over time (a speed) needs them, and the pose pass reads one
  second of margin on each side for that. A row of the grid that does not exist (the segment touches the start or the
  end of the track) is marked: ``has_prev`` or ``has_next`` is False and its cells are NaN with the reason ``no_frame``.
* ``scale_of`` is the median trunk length of a set of rows (what a speed and hip height B divide by).
* ``interval_mask`` and ``eligibility`` say which rows the coach confirmed for the metric (``[start, end)`` in stream
  seconds, 1e-9 s of tolerance at both ends, as the named intervals of ``quality.json``; ``None``: the whole segment),
  whether the view of the segment is one the metric supports, and which flag of the segment makes the metric invalid. A
  row outside every interval is ``outside_interval`` (16); inside, a view that is not supported makes it
  ``view_not_supported`` (17); then a blocking flag makes it ``interval_flagged`` (18); the rest is 0. Not eligible
  comes first in the precedence of a row (P5.01): after it the pose reasons (1 to 6), then the reasons that the pose is
  good but nothing was measured (19 to 22).
* ``drop_short_runs`` gives ``too_short`` (21) to the measured rows of a run that lasts less than the minimum valid
  duration (rows x ``step_s``, 1e-9 s of tolerance). The minimum is the metric's argument: ``None`` means none applied
  (it belongs to the signed ``metric_record``, which does not exist yet); a measured row without a step has no
  duration and is 21 whatever the minimum.
* ``leading_reason`` is the reason a summary without evidence gives: the one with the most rows, the smaller code on a
  tie, ``None`` when nothing is missing.

Errors are ``MetricError`` naming the argument.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from taiji_ai.metrics import MetricError
from taiji_ai.metrics.geometry import trunk_length, trunk_scale
from taiji_ai.metrics.series import MetricSeries, build_series
from taiji_ai.quality.layers_io import PoseFiltered
from taiji_ai.schemas.metric import MissingReason
from taiji_ai.schemas.quality_layers import DataSource

FLAGS: Final = (
    "orientation_change",
    "occlusion",
    "perspective_shift",
)  # the flags of ontology_v0 (a test keeps them equal)
VIEWS: Final = (
    "front",
    "side",
    "oblique",
    "back",
    "unknown",
)  # the view categories of ontology_v0 (a test keeps them equal)
_EPS_S: Final = 1e-9  # a row one float step off a boundary is on the boundary (as ``quality.coverage``)
_OUTSIDE: Final = int(MissingReason.outside_interval)
_NOT_SUPPORTED: Final = int(MissingReason.view_not_supported)
_NO_FRAME: Final = int(MissingReason.no_frame)
_FLAGGED: Final = int(MissingReason.interval_flagged)
_TOO_SHORT: Final = int(MissingReason.too_short)
_CODES: Final = np.array(sorted(int(r) for r in MissingReason), dtype=np.uint8)
_NAMES: Final = {int(r): r.name for r in MissingReason if r != MissingReason.measured}


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _describe(value: Any) -> str:
    return f"{value.dtype} array of shape {value.shape}" if isinstance(value, np.ndarray) else type(value).__name__


def _positive(value: Any, name: str) -> float:
    if not _is_number(value) or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise MetricError(f"{name} must be a finite number of seconds above 0, got {value!r}")
    return float(value)


def minimum_s(value: Any, name: str) -> float | None:
    """A minimum duration in seconds: ``None`` (none applied) or a finite number above 0; ``MetricError`` otherwise."""
    return None if value is None else _positive(value, name)


# --- the rows of a segment --------------------------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class SegmentRows:
    """The rows of the segment of a ``PoseFiltered``; every array is a read-only copy.

    ``t_sec`` ``(N,)`` float64 seconds from the stream start; ``keypoints`` ``(N, 26, 2)`` float32 pixels (y down);
    ``reason`` ``(N, 26)`` uint8 and ``interpolated`` ``(N, 26)`` bool as in the layer; ``step_s`` the step of the grid
    in seconds, ``None`` for fewer than two rows.
    """

    t_sec: np.ndarray
    keypoints: np.ndarray
    reason: np.ndarray
    interpolated: np.ndarray
    step_s: float | None
    recording_id: str
    data_sources: tuple[DataSource, ...]


def _segment_slice(layer: PoseFiltered) -> tuple[int, int]:
    """``(first, stop)``: the grid rows of the segment (``(0, 0)`` for none); ``MetricError`` if it is not one run."""
    if not isinstance(layer, PoseFiltered):
        raise MetricError(f"layer must be a PoseFiltered, got {type(layer).__name__}")
    rows = np.flatnonzero(np.asarray(layer.grid_in_segment))
    n = len(rows)
    if n and int(rows[-1]) - int(rows[0]) + 1 != n:
        raise MetricError(
            "grid_in_segment must be one contiguous run of rows: the segment from its first to its last row"
        )
    return (int(rows[0]), int(rows[-1]) + 1) if n else (0, 0)


def segment_rows(layer: PoseFiltered) -> SegmentRows:
    """The rows of ``grid_in_segment`` of the layer (none is allowed), never the margins around the segment."""
    lo, hi = _segment_slice(layer)
    n = hi - lo
    step = layer.meta.timeline.step_s if n >= 2 else None
    if n >= 2 and step is None:
        raise MetricError("the layer has no step_s although its segment has two rows or more")
    return SegmentRows(
        t_sec=_frozen(np.array(layer.t_grid[lo:hi], dtype=np.float64)),
        keypoints=_frozen(np.array(layer.keypoints[lo:hi], copy=True)),
        reason=_frozen(np.array(layer.reason[lo:hi], copy=True)),
        interpolated=_frozen(np.array(layer.interpolated[lo:hi], copy=True)),
        step_s=None if step is None else float(step),
        recording_id=layer.meta.recording_id,
        data_sources=tuple(layer.meta.data_sources),
    )


@dataclass(frozen=True, eq=False)
class Neighbours:
    """The grid row before and the grid row after every row of the segment; every array is a read-only copy.

    ``keypoints_prev`` and ``keypoints_next`` ``(N, 26, 2)`` float32, ``reason_prev`` and ``reason_next`` ``(N, 26)``
    uint8, ``interpolated_prev`` and ``interpolated_next`` ``(N, 26)`` bool, ``t_prev`` and ``t_next`` ``(N,)`` float64
    seconds; ``has_prev`` and ``has_next`` ``(N,)`` bool say whether the grid has that row. Where it has not, the
    positions are NaN with the reason ``no_frame`` (6), the flag is False and the time is NaN.
    """

    keypoints_prev: np.ndarray
    keypoints_next: np.ndarray
    reason_prev: np.ndarray
    reason_next: np.ndarray
    interpolated_prev: np.ndarray
    interpolated_next: np.ndarray
    t_prev: np.ndarray
    t_next: np.ndarray
    has_prev: np.ndarray
    has_next: np.ndarray


def neighbour_rows(layer: PoseFiltered) -> Neighbours:
    """For each row of the segment of ``layer``, the grid row before and the grid row after it (margins included)."""
    lo, hi = _segment_slice(layer)
    n, grid = hi - lo, len(layer.t_grid)
    index = {"prev": np.arange(lo - 1, hi - 1), "next": np.arange(lo + 1, hi + 1)}
    has = {side: (i >= 0) & (i < grid) for side, i in index.items()}

    def take(array: np.ndarray, side: str, fill: Any) -> np.ndarray:
        out = np.full((n, *array.shape[1:]), fill, dtype=array.dtype)
        out[has[side]] = array[index[side][has[side]]]
        return _frozen(out)

    arrays: dict[str, np.ndarray] = {}
    for side in ("prev", "next"):
        arrays[f"keypoints_{side}"] = take(layer.keypoints, side, np.nan)
        arrays[f"reason_{side}"] = take(layer.reason, side, _NO_FRAME)
        arrays[f"interpolated_{side}"] = take(layer.interpolated, side, False)
        arrays[f"t_{side}"] = take(layer.t_grid, side, np.nan)
        arrays[f"has_{side}"] = _frozen(has[side].copy())
    return Neighbours(**arrays)


# --- the stable intervals and the eligibility of a row --------------------------------------------------------------
def _times(t_sec: Any) -> np.ndarray:
    if not isinstance(t_sec, np.ndarray) or t_sec.dtype.kind != "f" or t_sec.ndim != 1:
        raise MetricError(f"t_sec must be a one-dimensional floating-point array of seconds, got {_describe(t_sec)}")
    return t_sec


def _intervals(intervals: Any, name: str) -> list[tuple[float, float]]:
    if isinstance(intervals, (str, bytes, Mapping)) or not isinstance(intervals, (Sequence, np.ndarray)):
        raise MetricError(f"{name} must be a list of (start, end) pairs of seconds, got {type(intervals).__name__}")
    out: list[tuple[float, float]] = []
    for i, item in enumerate(intervals):
        ok = isinstance(item, (Sequence, np.ndarray)) and not isinstance(item, (str, bytes)) and len(item) == 2
        if ok:
            a, b = item
            ok = _is_number(a) and _is_number(b) and math.isfinite(float(a)) and math.isfinite(float(b)) and a < b
        if not ok:
            raise MetricError(
                f"{name}[{i}] must be a pair (start, end) of finite seconds with start < end, got {item!r}"
            )
        out.append((float(a), float(b)))
    return out


def interval_mask(t_sec: np.ndarray, intervals: Sequence[Sequence[float]], *, name: str = "intervals") -> np.ndarray:
    """``(N,)`` bool: the rows whose time is in the union of the half-open intervals ``[start, end)``.

    The tolerance at both ends is 1e-9 s. ``name`` is the argument the caller knows ``intervals`` by (for the errors).
    """
    t = _times(t_sec)
    inside = np.zeros(len(t), dtype=bool)
    for start, end in _intervals(intervals, name):
        inside |= (t >= start - _EPS_S) & (t < end - _EPS_S)
    return _frozen(inside)


def _flags(flags: Any) -> dict[str, bool]:
    if not isinstance(flags, Mapping):
        raise MetricError(f"flags must be a mapping of flag names to booleans, got {type(flags).__name__}")
    for name, value in flags.items():
        if name not in FLAGS:
            raise MetricError(
                f"flags has {name!r}, which is not a flag of the ontology; the flags are {', '.join(FLAGS)}"
            )
        if not isinstance(value, bool):
            raise MetricError(f"flags[{name!r}] must be a bool, got {value!r}")
    return dict(flags)


def check_view(view: Any, name: str = "view") -> str:
    """``view`` if it is a view category of the ontology, else ``MetricError`` naming ``name`` (a typo is not a 17)."""
    if not isinstance(view, str) or view not in VIEWS:
        raise MetricError(f"{name} must be one of the views of the ontology ({', '.join(VIEWS)}), got {view!r}")
    return view


def check_supported_views(supported_views: Any, name: str = "supported_views") -> tuple[str, ...]:
    """The supported views as a tuple: a non-empty list of distinct views of the ontology, else ``MetricError``."""
    if isinstance(supported_views, (str, bytes)) or not isinstance(supported_views, Sequence) or not supported_views:
        raise MetricError(
            f"{name} must be a non-empty list of views of the ontology ({', '.join(VIEWS)}), got {supported_views!r}"
        )
    for view in supported_views:
        if not isinstance(view, str) or view not in VIEWS:
            raise MetricError(
                f"{name} has {view!r}, which is not a view of the ontology; the views are {', '.join(VIEWS)}"
            )
    if len(set(supported_views)) != len(supported_views):
        raise MetricError(f"{name} must not repeat a view, got {list(supported_views)!r}")
    return tuple(supported_views)


def eligibility(
    t_sec: np.ndarray,
    *,
    intervals: Sequence[Sequence[float]] | None,
    flags: Mapping[str, bool],
    blocking: Sequence[str],
    view: str | None = None,
    supported_views: Sequence[str] | None = None,
    name: str = "intervals",
) -> np.ndarray:
    """``(N,)`` uint8: 16 (``outside_interval``) outside every interval; inside, 17 (``view_not_supported``) when the
    view of the segment is not one of the supported views, else 18 (``interval_flagged``) when a flag that blocks the
    metric is set on the segment, else 0.

    ``intervals=None`` means the whole segment (no interval was asked of the coach); ``[]`` means no row. ``view`` and
    ``supported_views`` are given together or not at all (without them no view is asked for); ``view`` is one of
    ``VIEWS`` and ``supported_views`` a non-empty list of them. ``flags`` is the flag mapping of the segment (``{}``:
    none set); ``blocking`` the flags that make this metric invalid. Both name flags of the ontology (``FLAGS``). The
    order is 16, then 17, then 18: a row outside the intervals is not looked at for the view, and a view that does not
    fit is not looked at for flags. ``name`` is the argument the caller knows ``intervals`` by (for the errors).
    """
    if (view is None) != (supported_views is None):
        raise MetricError("view and supported_views are given together or not at all")
    fits = True
    if view is not None:
        fits = check_view(view) in check_supported_views(supported_views)
    inside = (
        np.ones(len(_times(t_sec)), dtype=bool) if intervals is None else interval_mask(t_sec, intervals, name=name)
    )
    given = _flags(flags)
    if isinstance(blocking, (str, bytes)) or not isinstance(blocking, Sequence):
        raise MetricError(f"blocking must be a list of flag names, got {type(blocking).__name__}")
    bad = [b for b in blocking if b not in FLAGS]
    if bad:
        raise MetricError(
            f"blocking has {bad[0]!r}, which is not a flag of the ontology; the flags are {', '.join(FLAGS)}"
        )
    flagged = any(given.get(flag, False) for flag in blocking)
    inside_code = (_FLAGGED if flagged else 0) if fits else _NOT_SUPPORTED
    return _frozen(np.where(inside, inside_code, _OUTSIDE).astype(np.uint8))


# --- runs that are too short, and the reason without evidence -------------------------------------------------------
def _reasons(reason: Any) -> np.ndarray:
    if not isinstance(reason, np.ndarray) or reason.dtype != np.uint8 or reason.ndim != 1:
        raise MetricError(f"reason must be a one-dimensional uint8 array of reason codes, got {_describe(reason)}")
    unknown = ~np.isin(reason, _CODES)
    if unknown.any():
        raise MetricError(f"reason has a code that is not a MissingReason ({int(reason[int(np.argmax(unknown))])})")
    return reason


def drop_short_runs(reason: np.ndarray, *, step_s: float | None, min_valid_s: float | None) -> np.ndarray:
    """A new ``(N,)`` uint8 array: the measured rows (0) of a run that lasts less than ``min_valid_s`` become 21.

    A run is a maximal stretch of rows with reason 0 and lasts ``rows x step_s`` (as ``valid_intervals`` count it), with
    1e-9 s of tolerance. ``min_valid_s=None`` applies no minimum. ``step_s=None`` (fewer than two rows) means a measured
    row has no duration: it becomes 21 whatever the minimum. Other reasons are kept; the input is not changed.
    """
    r = _reasons(reason)
    step = None if step_s is None else _positive(step_s, "step_s")
    minimum = minimum_s(min_valid_s, "min_valid_s")
    out = r.copy()
    measured = r == 0
    if step is None:
        out[measured] = _TOO_SHORT
    elif minimum is not None and measured.any():
        change = np.diff(np.concatenate(([False], measured, [False])).astype(np.int8))
        for start, stop in zip(np.flatnonzero(change == 1), np.flatnonzero(change == -1), strict=True):
            if (stop - start) * step < minimum - _EPS_S:
                out[start:stop] = _TOO_SHORT
    return _frozen(out)


def leading_reason(reason: np.ndarray) -> str | None:
    """The name of the reason with the most rows among the rows that are not measured; the smaller code on a tie.

    ``None`` when no row is missing (there is no reason to give). This is what a summary says when it has no evidence.
    """
    r = _reasons(reason)
    counts = np.bincount(r[r != 0], minlength=256)
    return _NAMES[int(np.argmax(counts))] if counts.any() else None


def evidence_reason(reason: np.ndarray, *, min_measured: int) -> str | None:
    """The reason a summary gives when it has no evidence, or ``None`` when it has some.

    ``None`` when at least ``min_measured`` rows are measured (a range needs two, a median one). Otherwise ``no_frame``
    when there is no row, ``too_short`` when some rows were measured but fewer than that, else the reason with the most
    rows among the rows that are not measured (``leading_reason``).
    """
    r = _reasons(reason)
    if isinstance(min_measured, bool) or not isinstance(min_measured, int) or min_measured < 1:
        raise MetricError(f"min_measured must be an integer of at least 1, got {min_measured!r}")
    measured = int((r == 0).sum())
    if measured >= min_measured:
        return None
    if len(r) == 0:
        return "no_frame"
    return "too_short" if measured > 0 else leading_reason(r)


def assemble_series(
    rows: SegmentRows,
    reason: np.ndarray,
    values: np.ndarray,
    *,
    metric_name: str,
    metric_version: str,
    units: str,
    parameters: dict[str, Any],
    min_valid_s: float | None,
    camera_id: str,
    view_category: str,
) -> MetricSeries:
    """The series of a metric once the reason and the value of every row are known.

    A measured run shorter than ``min_valid_s`` becomes ``too_short`` (``drop_short_runs``) and loses its value; the
    values of every row that is not measured are NaN; the header (intervals, coverage, counts) follows from the
    reasons (``build_series``), with the clock, the recording and the provenance of ``rows``.
    """
    reason = drop_short_runs(reason, step_s=rows.step_s, min_valid_s=min_valid_s)
    values = np.where(reason == 0, values, np.nan)
    return build_series(
        metric_name=metric_name,
        metric_version=metric_version,
        units=units,
        recording_id=rows.recording_id,
        camera_id=camera_id,
        view_category=view_category,
        t_sec=rows.t_sec,
        values=values,
        reason=reason,
        step_s=rows.step_s,
        parameters=parameters,
        data_sources=rows.data_sources,
    )


@dataclass(frozen=True)
class ScaleEstimate:
    """A trunk scale in pixels (``NaN`` when it cannot be used), the rows with a valid trunk it is the median of, and
    the seconds those rows last (rows x step; 0 when the rows have no step)."""

    scale_px: float
    n_rows: int
    duration_s: float


def scale_of(rows: SegmentRows, minimum: float | None) -> ScaleEstimate:
    """The median trunk length of ``rows`` with the rows it is the median of and the seconds they last.

    The median is that of ``geometry.trunk_scale`` over the rows where the trunk is finite and above 0 (a bridged cell
    counts: it has a value). It is ``NaN`` when no row is valid or when the valid rows last less than ``minimum``
    seconds (``None``: no minimum), with 1e-9 s of tolerance; the rows and the duration are kept so that a summary can
    say why.
    """
    trunk = trunk_scale(trunk_length(rows.keypoints))
    duration = 0.0 if rows.step_s is None else trunk.n_rows * rows.step_s
    scale = trunk.scale_px
    if minimum is not None and duration < minimum - _EPS_S:
        scale = float("nan")
    return ScaleEstimate(scale_px=scale, n_rows=trunk.n_rows, duration_s=duration)
