"""``MetricSeries``: the rows of one metric, and the header that is derived from them (P5.01).

A series has a header (``taiji_ai.schemas.metric.MetricHeader``: name, version, units, intervals, coverage, reasons)
and three arrays of ``N`` rows, one per grid row of the final layer inside the segment (``pose_filtered.npz``,
``grid_in_segment``):

* ``t_sec`` (N,) float64: seconds from the stream start (real PTS), finite and strictly increasing; the mean interval is
  the ``step_s`` of the grid (an identity grid of a clock in whole milliseconds is uniform only to a millisecond, so the
  step is given by the caller and only checked against the mean interval of the times, to 1 % plus a few
  milliseconds of clock noise spread over the span);
* ``values`` (N,) float64 in the units of the header: **finite exactly where the row is measured, NaN everywhere else**;
* ``reason`` (N,) uint8 (``MissingReason``): 0 is measured, any other code is why the row has no value.

The reason array is the single source of truth. ``build_series`` derives from it the valid intervals (the maximal runs
of measured rows, each ``[t_first, t_last + step_s)``), the coverage (``total``, ``eligible``, ``quality``,
``measured``) and the counts by reason; ``check_series`` computes them again and refuses a series whose header says
anything else, so a header that was edited, or a hole that is not in ``reason``, cannot exist. A series of fewer than
two rows has no step and no measured row. Nothing is filled: a NaN keeps its reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from pydantic import BaseModel

from taiji_ai.metrics import MetricError
from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.metric import (
    ELIGIBILITY,
    QUALITY,
    MetricHeader,
    MetricSummary,
    MissingReason,
)
from taiji_ai.schemas.quality_layers import DataSource

_STEP_TOL = 0.01  # the mean interval of t_sec is within this share of step_s ...
_CLOCK_TOL_S = 0.005  # ... plus this much clock noise spread over the span (an identity grid is uniform to 1 ms)
_REASON_CODES = np.array(sorted(int(r) for r in MissingReason), dtype=np.uint8)
_NAMES = {int(r): r.name for r in MissingReason if r != MissingReason.measured}


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


@dataclass(frozen=True, eq=False)
class MetricSeries:
    """A header and the rows of one metric; every array is read-only. Built by ``build_series``; always consistent."""

    header: MetricHeader
    t_sec: np.ndarray
    values: np.ndarray
    reason: np.ndarray

    def __post_init__(self) -> None:
        check_series(self)


def _derive(
    reason: np.ndarray, t: np.ndarray, step_s: float | None
) -> tuple[dict[str, int], dict[str, int], list[dict[str, float]]]:
    """The coverage, the counts by reason and the valid intervals that the rows give (plain data, for the header)."""
    n = len(reason)
    codes = np.bincount(reason, minlength=256)
    counts = {name: int(codes[code]) for code, name in _NAMES.items()}
    eligible = n - sum(counts[r.name] for r in ELIGIBILITY)
    quality = eligible - sum(counts[r.name] for r in QUALITY)
    measured = int(codes[0])
    coverage = {"total": n, "eligible": eligible, "quality": quality, "measured": measured}
    if measured and step_s is None:
        raise MetricError("step_s is needed for a measured row (it gives its duration); one row has no step")
    padded = np.concatenate(([False], reason == 0, [False])).astype(np.int8)
    change = np.diff(padded)
    starts, stops = np.flatnonzero(change == 1), np.flatnonzero(change == -1)  # a run is rows [start, stop)
    runs = [
        {"t_start": float(t[a]), "t_end": float(t[b - 1]) + float(step_s)}  # type: ignore[arg-type]
        for a, b in zip(starts, stops, strict=True)
    ]
    return coverage, counts, runs


def _parse_header(data: Mapping[str, Any]) -> MetricHeader:
    try:
        return parse_manifest(MetricHeader, data)
    except ManifestError as exc:
        raise MetricError(str(exc)) from exc


def check_series(series: MetricSeries) -> None:
    """Check a series against itself; ``MetricError`` naming the field. Every ``MetricSeries`` has passed it."""
    if not isinstance(series, MetricSeries):
        raise MetricError(f"series must be a MetricSeries, got {type(series).__name__}")
    if not isinstance(series.header, MetricHeader):
        raise MetricError(f"header must be a MetricHeader, got {type(series.header).__name__}")
    header = _parse_header(series.header.model_dump(warnings=False))  # the models are frozen, not immune to model_copy
    t, v, r = np.asarray(series.t_sec), np.asarray(series.values), np.asarray(series.reason)
    for name, array, dtype in (("t_sec", t, np.float64), ("values", v, np.float64), ("reason", r, np.uint8)):
        if array.dtype != np.dtype(dtype):
            raise MetricError(f"{name} has dtype {array.dtype}, expected {np.dtype(dtype)}")
        if array.ndim != 1:
            raise MetricError(f"{name} must be a 1-d array, got shape {array.shape}")
    n = len(r)
    for name, array in (("t_sec", t), ("values", v)):
        if array.shape != (n,):
            raise MetricError(f"{name} has shape {array.shape}, expected ({n},) like reason")
    if not np.all(np.isfinite(t)) or np.any(np.diff(t) <= 0):
        raise MetricError("t_sec must be finite and strictly increasing")
    if n >= 2:
        mean = (float(t[-1]) - float(t[0])) / (n - 1)
        if header.step_s is None or abs(mean - header.step_s) > _STEP_TOL * header.step_s + _CLOCK_TOL_S / (n - 1):
            raise MetricError(f"step_s ({header.step_s}) is not the mean interval of t_sec ({mean})")
    elif header.step_s is not None:
        raise MetricError("step_s must be null for fewer than two rows")
    bad = (r == 0) & ~np.isfinite(v)
    if bad.any():
        raise MetricError(f"values is not finite where reason is 0, a measured row (first: row {int(np.argmax(bad))})")
    bad = (r != 0) & ~np.isnan(v)
    if bad.any():
        raise MetricError(
            f"values must be NaN where reason is not 0: a value needs a measurement (row {int(np.argmax(bad))})"
        )
    unknown = ~np.isin(r, _REASON_CODES)
    if unknown.any():
        row = int(np.argmax(unknown))
        raise MetricError(f"reason has an unknown code {int(r[row])} (row {row}); the codes are those of MissingReason")
    coverage, counts, runs = _derive(r, t, header.step_s)
    if header.coverage.model_dump() != coverage:
        raise MetricError(
            f"coverage does not match the rows of reason: the header says {header.coverage.model_dump()}, "
            f"the rows {coverage}"
        )
    if header.missing_by_reason.model_dump() != counts:
        raise MetricError("missing_by_reason does not match the counts of the reason array")
    if [i.model_dump() for i in header.valid_intervals] != runs:
        raise MetricError("valid_intervals do not match the runs of measured rows in the reason array")


def build_series(
    *,
    metric_name: str,
    metric_version: str,
    units: str,
    recording_id: str,
    camera_id: str,
    view_category: str,
    t_sec: np.ndarray,
    values: np.ndarray,
    reason: np.ndarray,
    step_s: float | None,
    parameters: Mapping[str, Any] | None = None,
    data_sources: Sequence[DataSource] = (),
) -> MetricSeries:
    """A ``MetricSeries`` from the rows of a metric; the header is derived from ``reason`` and the clock.

    ``t_sec`` ``(N,)`` float seconds, ``values`` ``(N,)`` float in ``units`` (NaN where the row is not measured; float32
    is converted without loss), ``reason`` ``(N,)`` uint8 (``MissingReason``), ``step_s`` the interval of the grid
    (``None`` for fewer than two rows). The inputs are not changed; the arrays of the result are new and read-only.
    Raises ``MetricError`` naming the argument.
    """
    t, v, r = np.asarray(t_sec), np.asarray(values), np.asarray(reason)
    if t.dtype.kind != "f":
        raise MetricError(f"t_sec must be a floating-point array of seconds, got {t.dtype}")
    if v.dtype.kind != "f":
        raise MetricError(f"values must be a floating-point array (an integer array cannot hold NaN), got {v.dtype}")
    if r.dtype != np.uint8:
        raise MetricError(f"reason must be a uint8 array of reason codes, got {r.dtype}")
    for name, array in (("t_sec", t), ("values", v), ("reason", r)):
        if array.ndim != 1:
            raise MetricError(f"{name} must be a 1-d array, got shape {array.shape}")
    t, v, r = np.array(t, dtype=np.float64), np.array(v, dtype=np.float64), np.array(r, dtype=np.uint8)
    if not (t.shape == v.shape == r.shape):
        raise MetricError(f"t_sec, values and reason must have the same length, got {t.shape}, {v.shape}, {r.shape}")
    if len(r) >= 2 and step_s is None:
        raise MetricError("step_s is needed for two rows or more")
    if np.any(~np.isin(r, _REASON_CODES)):
        raise MetricError("reason has a code that is not a MissingReason")
    coverage, counts, runs = _derive(r, t, step_s)
    header = _parse_header(
        {
            "metric_name": metric_name, "metric_version": metric_version, "units": units, "recording_id": recording_id,
            "camera_id": camera_id, "view_category": view_category, "step_s": step_s, "valid_intervals": runs,
            "coverage": coverage, "missing_by_reason": counts, "parameters": dict(parameters or {}),
            "data_sources": [s.model_dump() if isinstance(s, DataSource) else s for s in data_sources],
        }
    )  # fmt: skip
    return MetricSeries(header=header, t_sec=_frozen(t), values=_frozen(v), reason=_frozen(r))


def _plain(items: Sequence[Any]) -> list[Any]:
    return [i.model_dump(warnings=False) if isinstance(i, BaseModel) else i for i in items]


def make_summary(
    series: MetricSeries,
    *,
    statistics: Sequence[Any],
    events: Sequence[Any] = (),
    insufficient_reason: str | None = None,
    record_status: str = "experimental",
    record_version: str | None = None,
    threshold_source: str | None = None,
) -> MetricSummary:
    """The summary of a series: its header, the evidence and the numbers drawn from it.

    ``statistics`` and ``events`` are ``Statistic`` and ``MetricEvent`` (or the dicts of their fields). An
    ``insufficient_reason`` (a reason name) makes the evidence ``insufficient_evidence``: every value must then be null
    and there must be no event. ``record_status`` is ``experimental`` until a signed ``metric_record`` enables the
    metric (P5.09). Raises ``MetricError`` naming the field when the numbers contradict the header or the rules of the
    models.
    """
    check_series(series)
    data = series.header.model_dump(warnings=False)
    data.update(
        evidence="sufficient" if insufficient_reason is None else "insufficient_evidence",
        insufficient_reason=insufficient_reason,
        record_status=record_status,
        record_version=record_version,
        threshold_source=threshold_source,
        statistics=_plain(statistics),
        events=_plain(events),
    )
    try:
        return parse_manifest(MetricSummary, data)
    except ManifestError as exc:
        raise MetricError(str(exc)) from exc
