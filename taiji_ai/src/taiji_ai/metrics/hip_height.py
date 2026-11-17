"""Hip height, variants A and B of Appendix B1 (W7, P5.03 and P5.04) and their range.

**Variant A**: ``h_A(t) = y_H(t) / Λ_take``.

``y_H`` is the vertical image position of the middle of the hips (``geometry.mid_hip``) after the camera roll is
taken out (``geometry.correct_roll``, origin ``(0, 0)``), in pixels, y down; ``Λ_take`` is the trunk length of the
take's **reference standing segment** (``reference_scale``: the median of ``L(t)`` over the rows of that segment, the
definition of ``geometry.trunk_scale``), kept fixed so that it cannot cancel the variation that is measured. At a roll
of 0 the values are exactly ``y_H / Λ_take``; they grow when the hip goes **down** the image, so the event ``max`` is
the lowest hip. The absolute level depends on the origin and on where the camera looks: only differences mean
anything, so the statistic is the range and no level is reported.

The result (``HipHeightResult``) is a series (one row per row of the segment of the layer: ``MetricSeries``, units
``body_lengths``) and a summary (``MetricSummary``): ``hip_height_range`` = P95 - P5 of the measured rows (linear
interpolation, at least two rows; fewer is ``insufficient_evidence`` with no number), ``bridged_rows`` (measured rows
that lean on a bridged hip value, a flagged value that the quality stage filled in), the events ``max`` and ``min`` at
the first row of the largest and of the smallest value, and the parameters that were used. The summary is
``experimental``: the value is shown and nothing is concluded (AGENTS.md section 5.5).

**The reference is another layer.** The pose pass of a segment reads the segment and one second around it, so the
reference standing segment is a segment of its own with its own ``PoseFiltered``; it must be of the same recording
(one stored video, hence one camera) and carry the same ``data_sources``, or it is refused. The same layer may be its
own reference.

**The reason of a row**, the first that applies (P5.01): not eligible, 16 when the row is outside every interval that
the coach confirmed as "expected stable height", else 18 when the segment has the flag ``perspective_shift``; then the
pose, the reason (1 to 6) of the first of the two hips without a value; then no reference (20) or no usable scale
(19); then 0, measured. A measured run shorter than ``min_valid_s`` becomes 21 (``too_short``). The two minimums
(``min_reference_s`` for the reference, ``min_valid_s`` for a run) belong to the signed ``metric_record`` and are
arguments here: ``None`` means none applied, and the summary says what was used. A view is not a condition of hip
height, so 17 is not used.

**Variant B** (P5.04, ``hip_height_b``): ``h_B(t) = (g(t) - y_H(t)) / Λ_segment`` where ``g(t)`` is the lowest point of
the feet (an estimate of the floor): the largest vertical coordinate, after the roll is taken out of every joint, over
the joints 15, 16, 24 and 25 (ankles and heels, ``GROUND_CANDIDATES``) that have a value in the row; the first joint of
the list on a tie. ``Λ_segment`` is the median trunk length over **all valid rows of the segment** (``min_scale_s``
asks for a minimum duration of those rows; ``None``: none). B has no reference, so it never gives 20. It is a true
height, up is positive: it grows when the hip goes **up**, so the event ``max`` is the highest hip, and it does not
depend on the origin or on a vertical shift of the image. The reason of the feet is 0 when at least one of the four has
a value and otherwise the reason of the first of them; the hips come first in the order of the metric. A row leans on a
bridged value when a hip or **the foot joint that gave ``g``** is bridged. Everything else (the rows, 16 and 18, the
runs, the range, the events, no evidence, ``experimental``) is A's, in one shared tail. DEC-0014: both variants are
computed and reported, no order between them is asserted, and the variant is chosen by the error against hand
measurements.

Errors are ``MetricError`` naming the argument.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np

from taiji_ai.metrics import MetricError
from taiji_ai.metrics.geometry import (
    HIP_JOINTS,
    bridged,
    correct_roll,
    mid_hip,
    unusable_reason,
)
from taiji_ai.metrics.rows import (
    ScaleEstimate,
    SegmentRows,
    assemble_series,
    eligibility,
    evidence_reason,
    minimum_s,
    scale_of,
    segment_rows,
)
from taiji_ai.metrics.series import MetricResult, MetricSeries, make_summary
from taiji_ai.pose.skeleton import GROUND_CANDIDATES
from taiji_ai.quality.layers_io import PoseFiltered
from taiji_ai.schemas.metric import MetricEvent, MissingReason, Statistic

METRIC_NAME_A: Final = "hip_height_a"  # variants A and B are two metrics (DEC-0014)
METRIC_NAME_B: Final = "hip_height_b"
METRIC_VERSION: Final = "1"
UNITS: Final = "body_lengths"
BLOCKING_FLAGS: Final = ("perspective_shift",)  # the only flag that makes hip height invalid (Appendix B1)
PERCENTILES: Final = (5.0, 95.0)  # Appendix B1: range = P95 - P5
_REFERENCE_MISSING: Final = int(MissingReason.reference_missing)
_SCALE_UNAVAILABLE: Final = int(MissingReason.scale_unavailable)


# --- the scale of the reference ------------------------------------------------------------------------------------
ReferenceScale = ScaleEstimate  # ``Λ_take`` of a reference: the same estimate as B's scale of its segment


def reference_scale(reference: PoseFiltered, *, min_reference_s: float | None = None) -> ReferenceScale:
    """``Λ_take`` from the rows of the **segment** of the reference layer (never its margins).

    ``Λ_take`` is the median of the trunk length over the rows where it is finite and above 0 (a bridged cell counts:
    it has a value). It is ``NaN`` when no row is valid or when those rows last less than ``min_reference_s`` seconds
    (``None``: no minimum); the rows and the duration are kept so that a summary can say why.
    """
    if not isinstance(reference, PoseFiltered):
        raise MetricError(f"reference must be a PoseFiltered, got {type(reference).__name__}")
    minimum = minimum_s(min_reference_s, "min_reference_s")
    return scale_of(segment_rows(reference), minimum)


# --- the metric ----------------------------------------------------------------------------------------------------
HipHeightResult = MetricResult  # the series of a hip height variant (``h_A`` or ``h_B``) and its summary


def _confirmed(stable_intervals: Any) -> Any:
    """The intervals as given, but never ``None``: B1 asks the coach to confirm the stretch, so there is no default."""
    if stable_intervals is None:
        raise MetricError(
            "stable_intervals must be a list of (start, end) pairs of seconds, got NoneType: "
            "the coach confirms them (Appendix B1), there is no default"
        )
    return stable_intervals


def _check_reference(rows: SegmentRows, reference: Any) -> None:
    if not isinstance(reference, PoseFiltered):
        raise MetricError(f"reference must be a PoseFiltered or None, got {type(reference).__name__}")
    if reference.meta.recording_id != rows.recording_id:
        raise MetricError("reference is of another recording_id than the layer: a scale from another video is refused")
    if tuple(reference.meta.data_sources) != rows.data_sources:
        raise MetricError("reference has other data_sources than the layer: the result would mix two provenances")


def _row_reasons(rows: SegmentRows, eligible: np.ndarray, scale: ReferenceScale | None) -> np.ndarray:
    pose = unusable_reason(rows.keypoints, rows.reason, HIP_JOINTS)
    after = np.zeros(len(rows.t_sec), dtype=np.uint8)
    if scale is None:
        after[:] = _REFERENCE_MISSING
    elif not math.isfinite(scale.scale_px):
        after[:] = _SCALE_UNAVAILABLE
    return np.where(eligible != 0, eligible, np.where(pose != 0, pose, after)).astype(np.uint8)


def _statistics(series: MetricSeries, leaning: np.ndarray) -> tuple[list[Statistic], list[MetricEvent], str | None]:
    """The statistics, the events and the reason for no evidence (``None`` when there is evidence).

    ``leaning`` ``(N,)`` bool: the rows that lean on a bridged value (each variant says which joints count).
    """
    reason = np.asarray(series.reason)
    measured = np.flatnonzero(reason == 0)
    why = evidence_reason(reason, min_measured=2)  # a range needs two values: one row has no spread (not a 0)
    if why is not None:
        none = [
            Statistic(name="hip_height_range", value=None, units=UNITS, uses_threshold=False),
            Statistic(name="bridged_rows", value=None, units="count", uses_threshold=False),
        ]
        return none, [], why
    h = np.asarray(series.values)[measured]
    low, high = np.percentile(h, PERCENTILES)
    bridged_rows = int(leaning[measured].sum())
    statistics = [
        Statistic(name="hip_height_range", value=float(high - low), units=UNITS, uses_threshold=False),
        Statistic(name="bridged_rows", value=float(bridged_rows), units="count", uses_threshold=False),
    ]
    t = np.asarray(series.t_sec)
    top, bottom = int(np.argmax(h)), int(np.argmin(h))  # argmax and argmin give the first row of equal values
    t_max, t_min = float(t[measured[top]]), float(t[measured[bottom]])
    events = [
        MetricEvent(kind="max", t_start=t_max, t_end=t_max, value=float(h[top]), uses_threshold=False),
        MetricEvent(kind="min", t_start=t_min, t_end=t_min, value=float(h[bottom]), uses_threshold=False),
    ]
    return statistics, events, None


def _finish(
    rows: SegmentRows,
    reason: np.ndarray,
    values: np.ndarray,
    *,
    metric_name: str,
    parameters: dict[str, Any],
    leaning: np.ndarray,
    minimum_run: float | None,
    camera_id: str,
    view_category: str,
) -> HipHeightResult:
    """What both variants do once the reason and the value of every row are known (see the module docstring).

    A measured run shorter than ``minimum_run`` becomes ``too_short`` and loses its value; the series, its header, the
    statistics, the events and the ``experimental`` summary follow from the reasons.
    """
    series = assemble_series(
        rows,
        reason,
        values,
        metric_name=metric_name,
        metric_version=METRIC_VERSION,
        units=UNITS,
        parameters=parameters,
        min_valid_s=minimum_run,
        camera_id=camera_id,
        view_category=view_category,
    )
    statistics, events, why = _statistics(series, leaning)
    summary = make_summary(
        series, statistics=statistics, events=events, insufficient_reason=why, record_status="experimental"
    )
    return HipHeightResult(series=series, summary=summary)


def hip_height_a(
    layer: PoseFiltered,
    *,
    reference: PoseFiltered | None,
    stable_intervals: Sequence[Sequence[float]],
    flags: Mapping[str, bool],
    camera_id: str,
    view_category: str,
    roll_deg: float = 0.0,
    min_reference_s: float | None = None,
    min_valid_s: float | None = None,
) -> HipHeightResult:
    """Hip height, variant A, of the segment of ``layer`` (see the module docstring for every rule).

    ``reference``: the final layer of the take's reference standing segment (same recording), or ``None`` (every good
    row is then ``reference_missing``). ``stable_intervals``: the ``[start, end)`` intervals in stream seconds that
    the coach confirmed as expected stable height (``[]``: none, every row is ``outside_interval``). ``flags``: the
    flags of the segment (``{}``: none set). ``roll_deg``: the camera roll from ``roll_from_line`` (0 by default,
    within 45 degrees). ``min_reference_s``, ``min_valid_s``: the minimums of the reference and of a valid run, in
    seconds (``None``: none applied). Raises ``MetricError`` naming the argument.
    """
    rows = segment_rows(layer)
    if reference is not None:
        _check_reference(rows, reference)
    minimum_run = minimum_s(min_valid_s, "min_valid_s")
    minimum_ref = minimum_s(min_reference_s, "min_reference_s")
    correct_roll(np.zeros((1, 2)), roll_deg)  # validates the roll: a number within 45 degrees
    eligible = eligibility(
        rows.t_sec,
        intervals=_confirmed(stable_intervals),
        flags=flags,
        blocking=BLOCKING_FLAGS,
        name="stable_intervals",
    )
    scale = None if reference is None else reference_scale(reference, min_reference_s=minimum_ref)
    reason = _row_reasons(rows, eligible, scale)
    values = np.full(len(reason), np.nan)
    measured = reason == 0
    if measured.any() and scale is not None:  # a measured row has a hip and a scale
        y = correct_roll(mid_hip(rows.keypoints), roll_deg)[:, 1]
        values[measured] = y[measured] / scale.scale_px
    parameters: dict[str, Any] = {
        "variant": "a",
        "roll_deg": float(roll_deg),
        "min_reference_s": minimum_ref,
        "min_valid_s": minimum_run,
        "percentile_low": PERCENTILES[0],
        "percentile_high": PERCENTILES[1],
        "scale_px": float(scale.scale_px) if scale is not None and math.isfinite(scale.scale_px) else None,
        "reference_rows": None if scale is None else scale.n_rows,
        "reference_s": None if scale is None else float(scale.duration_s),
        "n_stable_intervals": len(stable_intervals),
    }
    return _finish(
        rows,
        reason,
        values,
        metric_name=METRIC_NAME_A,
        parameters=parameters,
        leaning=bridged(rows.keypoints, rows.interpolated, HIP_JOINTS),
        minimum_run=minimum_run,
        camera_id=camera_id,
        view_category=view_category,
    )


def _feet_reason(rows: SegmentRows) -> np.ndarray:
    """0 where a foot joint has a value, else the reason of the first of the four (15, 16, 24, 25)."""
    per_joint = np.stack([unusable_reason(rows.keypoints, rows.reason, [j]) for j in GROUND_CANDIDATES], axis=1)
    return np.where((per_joint == 0).any(axis=1), 0, per_joint[:, 0]).astype(np.uint8)


def hip_height_b(
    layer: PoseFiltered,
    *,
    stable_intervals: Sequence[Sequence[float]],
    flags: Mapping[str, bool],
    camera_id: str,
    view_category: str,
    roll_deg: float = 0.0,
    min_scale_s: float | None = None,
    min_valid_s: float | None = None,
) -> HipHeightResult:
    """Hip height, variant B, of the segment of ``layer`` (see the module docstring for every rule).

    ``stable_intervals``: the ``[start, end)`` intervals in stream seconds that the coach confirmed as expected stable
    height (``[]``: none, every row is ``outside_interval``). ``flags``: the flags of the segment (``{}``: none set).
    ``roll_deg``: the camera roll from ``roll_from_line`` (0 by default, within 45 degrees). ``min_scale_s``,
    ``min_valid_s``: the minimums of the scale (the valid rows of the segment) and of a valid run, in seconds
    (``None``: none applied). The values are in body lengths, up is positive. Raises ``MetricError`` naming the
    argument.
    """
    rows = segment_rows(layer)
    minimum_run = minimum_s(min_valid_s, "min_valid_s")
    minimum_scale = minimum_s(min_scale_s, "min_scale_s")
    eligible = eligibility(
        rows.t_sec,
        intervals=_confirmed(stable_intervals),
        flags=flags,
        blocking=BLOCKING_FLAGS,
        name="stable_intervals",
    )
    scale = scale_of(rows, minimum_scale)
    hips = unusable_reason(rows.keypoints, rows.reason, HIP_JOINTS)
    pose = np.where(hips != 0, hips, _feet_reason(rows))  # the hips come first in the order of the metric
    after = np.full(len(pose), 0 if math.isfinite(scale.scale_px) else _SCALE_UNAVAILABLE, dtype=np.uint8)
    reason = np.where(eligible != 0, eligible, np.where(pose != 0, pose, after)).astype(np.uint8)
    n, feet = len(reason), list(GROUND_CANDIDATES)
    y_hip = correct_roll(mid_hip(rows.keypoints), roll_deg)[:, 1]  # also validates the roll, measured row or not
    y_feet = correct_roll(rows.keypoints[:, feet, :], roll_deg)[..., 1]  # (N, 4), NaN where the joint has no value
    valid = np.isfinite(y_feet)
    lowest = np.where(valid, y_feet, -np.inf)
    used = np.argmax(lowest, axis=1)  # the foot joint that gives g: the lowest, the first of the list on a tie
    ground = lowest[np.arange(n), used]
    values = np.full(n, np.nan)
    measured = reason == 0
    if measured.any():  # a measured row has both hips, a foot joint and a scale
        values[measured] = (ground[measured] - y_hip[measured]) / scale.scale_px
    foot_bridged = rows.interpolated[np.arange(n), np.asarray(feet)[used]] & valid[np.arange(n), used]
    parameters: dict[str, Any] = {
        "variant": "b",
        "roll_deg": float(roll_deg),
        "min_scale_s": minimum_scale,
        "min_valid_s": minimum_run,
        "percentile_low": PERCENTILES[0],
        "percentile_high": PERCENTILES[1],
        "scale_px": float(scale.scale_px) if math.isfinite(scale.scale_px) else None,
        "scale_rows": scale.n_rows,
        "scale_s": float(scale.duration_s),
        "n_stable_intervals": len(stable_intervals),
    }
    return _finish(
        rows,
        reason,
        values,
        metric_name=METRIC_NAME_B,
        parameters=parameters,
        leaning=bridged(rows.keypoints, rows.interpolated, HIP_JOINTS) | foot_bridged,
        minimum_run=minimum_run,
        camera_id=camera_id,
        view_category=view_category,
    )
