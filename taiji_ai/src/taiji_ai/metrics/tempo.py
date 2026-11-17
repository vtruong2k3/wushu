"""Speed of a group of joints on the real clock, Appendix B3 (W7, P5.06), in body lengths per second.

For a joint ``j`` at a row ``k`` of the final layer, ``v_j(t_k) = ‖p_j(t_{k+1}) - p_j(t_{k-1})‖ / (t_{k+1} -
t_{k-1}) / Λ``: the central difference of the positions (pixels, y down) over the **real** time between the two
neighbours (``t_grid``, never an assumed step: on a uniform grid it is two steps, on an identity grid of a clock in
whole milliseconds it is the real difference), divided by the scale ``Λ`` of the segment (``rows.scale_of``: the
median trunk length of its valid rows, one value for the whole series; ``min_scale_s`` asks for a minimum duration
of those rows, ``None``: none). The speed of a group ``G`` (``pose.skeleton.GROUPS``: hands 9 and 10, hips 11 and
12, feet 15, 16, 24 and 25) is ``V_G(t_k)``, the median over the **usable** joints of ``v_j(t_k)``. A rotation of
the image does not change the norm of a displacement, so there is no roll here.

**The neighbours are rows of the layer, not of the series.** The series holds the rows of the segment, but the first
and the last of them need the row before and the row after: the margins that the pose pass read on purpose
(``rows.neighbour_rows``). A row has no neighbour on a side only where the grid has no row there (the segment
touches the start or the end of the track): it is ``run_edge`` (22). No one-sided difference is made: it would be
another quantity.

**A joint is usable at a row** when the cells of the row before and of the row after have a value (observed or
bridged, a bridge is a flagged value and is counted); its own cell at the row is not read by the formula. The group
needs one usable joint. **The reason of a row**, the first that applies (P5.01): not eligible, 16 outside the
coach's ``intervals`` (when given; ``None`` is the whole segment, because B3 keeps the original duration of the
segment), else 18 for the flag ``perspective_shift`` (a depth change distorts a speed in trunk lengths, as B1 says
of the height); then the pose, the reason (1 to 6) of the first joint of the group, in the order of the group, when
no joint is usable (its first missing neighbour: the row before, then the row after; a row with no neighbour on a
side is not looked at for the pose); then 19 when the scale is unavailable; then 22; then 0, measured; then a
measured run shorter than ``min_valid_s`` becomes 21 (``None``: none applied; the minimum belongs to the signed
``metric_record``). A view is not a condition (17 is not used) and there is no reference (20).

**The result** (``MetricResult``) is the profile ``V_G`` (the series, units ``body_lengths_per_s``) and an
``experimental`` summary: ``segment_duration_s`` (the original duration of the segment on the real clock, from the
first row to the end of the last), ``speed_median``, ``speed_cv`` (the coefficient of variation of ``V_G``: the
population standard deviation over the mean of the measured values, null when the mean is 0) and ``bridged_rows``
(measured rows that lean on a bridged neighbour of a usable joint). One measured row gives numbers; none gives
``insufficient_evidence`` with null statistics. The speed has a noise floor: 1 px of noise on a 200 px trunk leaves
about 0.07 trunk lengths per second on a joint that does not move (see the task file); the cut-off ablation is P5.08.

**Pauses (P5.07, optional).** With ``pause_tau`` (``τ``, body lengths per second) and ``pause_min_s`` (``d_min``,
seconds), both or neither and no default, the result also holds the pauses of the group (Appendix B3: ``V_G < τ`` for
at least ``d_min``). ``find_pauses`` reads a series: a **pause** is a maximal run of consecutive **measured** rows with
``V < τ`` (strict) that lasts ``n × step >= d_min`` (1e-9 s of tolerance), the interval ``[t_first, t_last + step)`` as
the valid intervals are, so it lies inside one. A row that is not measured has no speed, is neither slow nor fast, ends
a run, and is never bridged. A pause is **cut** when the row just before or just after it exists and was lost by the
pose (reasons 1 to 6: it may go on beyond it); the edge of the segment, a row outside the coach's intervals (16), a
flagged one (18), the end of the track (22) and the other reasons are boundaries of the protocol or the track and do
not cut. A slow stretch that a hole cuts below ``d_min`` is not counted (a pause that is seen is a lower bound). The
summary has one ``pause`` event per pause and the statistics ``pause_count``, ``pause_total_s``, ``pause_longest_s``
and ``pause_cut_count``, all threshold outputs labelled ``unsigned_config`` (the result stays ``experimental``); they
are null when no run of measured rows lasts ``d_min`` (a pause could not have been seen: a 0 would be a 0 nobody
measured) and with ``insufficient_evidence``, and a count of 0 otherwise is a measured 0. ``τ`` has to clear the noise
floor of the footage: at or under it a pause fragments or is never seen. The profile and the four statistics above do
not depend on the two arguments.

Errors are ``MetricError`` naming the argument.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

import numpy as np

from taiji_ai.metrics import MetricError
from taiji_ai.metrics.geometry import unusable_reason
from taiji_ai.metrics.rows import (
    assemble_series,
    eligibility,
    evidence_reason,
    minimum_s,
    neighbour_rows,
    scale_of,
    segment_rows,
)
from taiji_ai.metrics.series import MetricResult, MetricSeries, make_summary
from taiji_ai.pose.skeleton import GROUPS
from taiji_ai.quality.layers_io import PoseFiltered
from taiji_ai.schemas.metric import MetricEvent, MissingReason, Statistic

GROUP_METRIC_NAMES: Final = {"hands": "speed_hands", "hips": "speed_hips", "feet": "speed_feet"}  # one record per group
BLOCKING_FLAGS: Final = ("perspective_shift",)  # a depth change distorts a speed in trunk lengths
METRIC_VERSION: Final = "1"
UNITS: Final = "body_lengths_per_s"
THRESHOLD_SOURCE: Final = "unsigned_config"  # τ and d_min are arguments until a signed record supplies them (P5.09)
_SCALE_UNAVAILABLE: Final = int(MissingReason.scale_unavailable)
_RUN_EDGE: Final = int(MissingReason.run_edge)
_EPS_S: Final = 1e-9  # tolerance of a duration against a minimum, as for the valid intervals
_POSE_LOSS: Final = tuple(range(1, 7))  # the reasons of the quality layer: the pose was lost at the row
_PROFILE_STATISTICS: Final = (
    ("segment_duration_s", "s"),
    ("speed_median", UNITS),
    ("speed_cv", "ratio"),
    ("bridged_rows", "count"),
)
_PAUSE_STATISTICS: Final = (
    ("pause_count", "count"),
    ("pause_total_s", "s"),
    ("pause_longest_s", "s"),
    ("pause_cut_count", "count"),
)


@dataclass(frozen=True)
class Pause:
    """A pause of a series: the rows ``first_row`` to ``last_row`` (indices into the series, both measured and slow).

    ``[t_start, t_end)`` in seconds from the stream start, ``t_end = t[last_row] + step`` so that the length is a whole
    number of steps. ``cut_before`` and ``cut_after``: the row just before the first or just after the last is a row
    that the pose lost (reasons 1 to 6), so the pause may go on beyond it and its length is a lower bound.
    """

    first_row: int
    last_row: int
    t_start: float
    t_end: float
    cut_before: bool
    cut_after: bool

    @property
    def duration_s(self) -> float:
        return self.t_end - self.t_start


def _threshold(value: Any, name: str, unit: str) -> float:
    """``τ`` or ``d_min``: a finite number above 0 (a bool is not one); ``MetricError`` naming the argument."""
    number = isinstance(value, int | float | np.integer | np.floating) and not isinstance(value, bool)
    if not number or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise MetricError(f"{name} must be a finite number of {unit} above 0, got {value!r}")
    return float(value)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """The maximal runs of True of a 1-d boolean array, as ``(first, last)`` indices."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1).tolist(), (np.flatnonzero(edges == -1) - 1).tolist(), strict=True))


def find_pauses(series: MetricSeries, *, tau: float, min_pause_s: float) -> tuple[Pause, ...]:
    """The pauses of a speed series: runs of measured rows with ``V < tau`` that last at least ``min_pause_s``.

    ``tau`` in the units of the series (body lengths per second), ``min_pause_s`` in seconds; both finite and above 0,
    else ``MetricError``. A run is a maximal stretch of consecutive rows with reason 0 and a value below ``tau``
    (strict); a row that is not measured ends it and is never read as slow. It lasts ``n × step_s`` and is kept when
    that is at least ``min_pause_s`` (1e-9 s of tolerance). The pauses come in time order; see ``Pause`` for the
    interval and the cut flags. A series of fewer than two rows has no step and no pause.
    """
    if not isinstance(series, MetricSeries):
        raise MetricError(f"series must be a MetricSeries, got {type(series).__name__}")
    limit = _threshold(tau, "tau", "body lengths per second")
    minimum = _threshold(min_pause_s, "min_pause_s", "seconds")
    step = series.header.step_s
    if step is None or len(series.t_sec) < 2:
        return ()
    t, reason = np.asarray(series.t_sec), np.asarray(series.reason)
    slow = (reason == 0) & (np.asarray(series.values) < limit)  # NaN is never below: a hole is not slow
    lost = np.isin(reason, _POSE_LOSS)
    n = len(reason)
    out = []
    for first, last in _runs(slow):
        if (last - first + 1) * step >= minimum - _EPS_S:
            out.append(
                Pause(
                    first,
                    last,
                    float(t[first]),
                    float(t[last]) + step,
                    cut_before=bool(first > 0 and lost[first - 1]),
                    cut_after=bool(last + 1 < n and lost[last + 1]),
                )  # fmt: skip
            )
    return tuple(out)


def _median_of_usable(speeds: np.ndarray, usable: np.ndarray) -> np.ndarray:
    """The median over the usable joints of each row (NaN for a row with none), by sorting: no all-NaN warning."""
    ordered = np.sort(np.where(usable, speeds, np.nan), axis=1)  # NaN sorts last: the usable values come first
    count = usable.sum(axis=1)
    rows = np.arange(len(count))
    low, high = np.maximum(count - 1, 0) // 2, count // 2
    middle = (ordered[rows, low] + ordered[rows, np.minimum(high, ordered.shape[1] - 1)]) / 2.0
    return np.where(count > 0, middle, np.nan)


def group_speed(
    layer: PoseFiltered,
    *,
    group: Literal["hands", "hips", "feet"],
    flags: Mapping[str, bool],
    camera_id: str,
    view_category: str,
    intervals: Sequence[Sequence[float]] | None = None,
    min_valid_s: float | None = None,
    min_scale_s: float | None = None,
    pause_tau: float | None = None,
    pause_min_s: float | None = None,
) -> MetricResult:
    """The speed of a group of joints of the segment of ``layer`` on the real clock (see the module docstring).

    ``group``: ``"hands"``, ``"hips"`` or ``"feet"``. ``flags``: the flags of the segment (``{}``: none set).
    ``intervals``: the ``[start, end)`` intervals in stream seconds that the coach chose (``None``: the whole segment;
    ``[]``: none). ``min_valid_s``, ``min_scale_s``: the minimum duration of a valid run and of the valid rows that give
    the scale, in seconds (``None``: none applied). ``pause_tau`` (body lengths per second) and ``pause_min_s``
    (seconds): the threshold and the minimum length of a pause, given together or not at all (``None``: the profile
    only, no pause and no threshold output). Raises ``MetricError`` naming the argument.
    """
    if not isinstance(group, str) or group not in GROUP_METRIC_NAMES:
        raise MetricError(f"group must be one of {', '.join(GROUP_METRIC_NAMES)}, got {group!r}")
    rows = segment_rows(layer)
    minimum_run = minimum_s(min_valid_s, "min_valid_s")
    minimum_scale = minimum_s(min_scale_s, "min_scale_s")
    if (pause_tau is None) != (pause_min_s is None):
        raise MetricError("pause_tau and pause_min_s must be given together or not at all")
    tau = None if pause_tau is None else _threshold(pause_tau, "pause_tau", "body lengths per second")
    d_min = None if pause_min_s is None else _threshold(pause_min_s, "pause_min_s", "seconds")
    eligible = eligibility(rows.t_sec, intervals=intervals, flags=flags, blocking=BLOCKING_FLAGS)
    nb = neighbour_rows(layer)
    scale = scale_of(rows, minimum_scale)
    joints = GROUPS[group]
    n = len(rows.t_sec)
    edge = ~(nb.has_prev & nb.has_next)  # the grid has no row on one side: nothing can be read
    elapsed = nb.t_next - nb.t_prev  # the real time between the two neighbours (NaN at an edge)
    speeds = np.full((n, len(joints)), np.nan)
    usable = np.zeros((n, len(joints)), dtype=bool)
    first_missing = np.zeros((n, len(joints)), dtype=np.uint8)  # the reason of a joint: its first missing neighbour
    leaning = np.zeros(n, dtype=bool)
    for c, joint in enumerate(joints):
        before = unusable_reason(nb.keypoints_prev, nb.reason_prev, [joint])
        after = unusable_reason(nb.keypoints_next, nb.reason_next, [joint])
        usable[:, c] = (before == 0) & (after == 0) & ~edge
        first_missing[:, c] = np.where(before != 0, before, after)
        shift = nb.keypoints_next[:, joint, :].astype(np.float64) - nb.keypoints_prev[:, joint, :]
        with np.errstate(invalid="ignore", divide="ignore"):
            speeds[:, c] = np.hypot(shift[:, 0], shift[:, 1]) / elapsed / scale.scale_px
        leaning |= usable[:, c] & (nb.interpolated_prev[:, joint] | nb.interpolated_next[:, joint])
    pose = np.where(usable.any(axis=1) | edge, 0, first_missing[:, 0])  # the first joint of the group gives the reason
    after_quality = np.full(n, _SCALE_UNAVAILABLE if not math.isfinite(scale.scale_px) else 0)
    after_quality = np.where((after_quality == 0) & edge, _RUN_EDGE, after_quality)
    reason = np.where(eligible != 0, eligible, np.where(pose != 0, pose, after_quality)).astype(np.uint8)
    parameters: dict[str, Any] = {
        "group": group,
        "min_valid_s": minimum_run,
        "min_scale_s": minimum_scale,
        "scale_px": float(scale.scale_px) if math.isfinite(scale.scale_px) else None,
        "scale_rows": scale.n_rows,
        "scale_s": float(scale.duration_s),
        "n_intervals": None if intervals is None else len(intervals),
        "pause_tau": tau,
        "pause_min_s": d_min,
    }
    series = assemble_series(
        rows,
        reason,
        _median_of_usable(speeds, usable),
        metric_name=GROUP_METRIC_NAMES[group],
        metric_version=METRIC_VERSION,
        units=UNITS,
        parameters=parameters,
        min_valid_s=minimum_run,
        camera_id=camera_id,
        view_category=view_category,
    )
    why = evidence_reason(series.reason, min_measured=1)
    asked = tau is not None and d_min is not None
    pauses: tuple[Pause, ...] = ()
    if why is not None:
        numbers: list[float | None] = [None] * len(_PROFILE_STATISTICS)
        pause_numbers: list[float | None] = [None] * len(_PAUSE_STATISTICS)
    else:
        measured = series.reason == 0
        profile = np.asarray(series.values)[measured]
        t, step = np.asarray(series.t_sec), float(rows.step_s or 0.0)
        mean = float(np.mean(profile))
        duration = float(t[-1] - t[0]) + step  # the original duration: from the first row to the end of the last
        variation = None if mean == 0.0 else float(np.std(profile)) / mean  # a mean of 0 has none: null
        numbers = [duration, float(np.median(profile)), variation, float(leaning[measured].sum())]
        pause_numbers = [None] * len(_PAUSE_STATISTICS)
        if asked:
            pauses = find_pauses(series, tau=tau, min_pause_s=d_min)  # type: ignore[arg-type]
            # a pause could only have been seen if some run of measured rows lasts d_min: else a 0 is not a measurement
            if any((last - first + 1) * step >= d_min - _EPS_S for first, last in _runs(measured)):  # type: ignore[operator]
                lengths = [p.duration_s for p in pauses]
                cut = sum(p.cut_before or p.cut_after for p in pauses)
                pause_numbers = [float(len(pauses)), float(sum(lengths)), float(max(lengths, default=0.0)), float(cut)]
    statistics = [
        Statistic(name=name, value=value, units=unit, uses_threshold=False)  # type: ignore[arg-type]
        for (name, unit), value in zip(_PROFILE_STATISTICS, numbers, strict=True)
    ]
    if asked:
        statistics += [
            Statistic(name=name, value=value, units=unit, uses_threshold=True)  # type: ignore[arg-type]
            for (name, unit), value in zip(_PAUSE_STATISTICS, pause_numbers, strict=True)
        ]
    events = [
        MetricEvent(kind="pause", t_start=p.t_start, t_end=p.t_end, value=None, uses_threshold=True) for p in pauses
    ]
    summary = make_summary(
        series,
        statistics=statistics,
        events=events,
        insufficient_reason=why,
        record_status="experimental",
        threshold_source=THRESHOLD_SOURCE if asked else None,
    )
    return MetricResult(series=series, summary=summary)
