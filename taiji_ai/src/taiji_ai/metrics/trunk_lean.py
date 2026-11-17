"""Trunk lean in the image plane, Appendix B2 (W7, P5.05): ``θ(t) = atan2(x_S - x_H, y_H - y_S) - roll_cam`` in
degrees.

``H`` is the middle of the hips and ``S`` the middle of the shoulders (``geometry.mid_hip``,
``geometry.mid_shoulder``), in pixels of the upright image (x right, y down); ``θ`` is ``geometry.lean_angle_deg``
(P5.02): 0 is vertical, the angle is positive when the top of the trunk leans to the **image right** and is wrapped
to (-180, 180]. The roll of the camera (``roll_deg``, from ``geometry.roll_from_line``, 0 by default, within 45
degrees) is subtracted. An angle does not depend on the trunk length, a shift or a zoom of the image, so there is no
scale and no reference here: no reason 19 or 20.

**Two metrics, one function.** The same angle means two things (B2): on a **front** view it is the left/right lean
(``plane="lr"``, metric ``trunk_lean_lr``), on a **side** view the forward/back lean (``plane="fb"``, metric
``trunk_lean_fb``). The signed record of each will say its supported views, its smallest useful change and its
threshold, so each has its own name. The sign stays an image sign: which side of the performer, or forward or back,
is for the report, which knows the facing.

**Only where the view fits.** The view is the segment's ``view_category`` (one per segment). It must be one of
``SUPPORTED_VIEWS[plane]`` (``front`` for ``lr``, ``side`` for ``fb``; ``supported_views`` replaces them with the
list of a signed record). A view that does not fit gives **every row 17** (``view_not_supported``) and a summary
that is ``insufficient_evidence`` with no number (T-MET-07). A performer who turns during the segment is the flag
``orientation_change`` (the view assumption fails): every row is 18.

**The reason of a row**, the first that applies (P5.01): outside the coach's ``intervals`` (when given; ``None`` is
the whole segment, because B2 asks for the view and not for a confirmed stable stretch), 16; the view, 17; the flag,
18; then the pose, the reason (1 to 6) of the first of the four joints without a value in the order hips (11, 12)
then shoulders (5, 6); then ``frame_invalid`` (4) when the four joints have values and the two middle points
coincide (the angle is undefined; P5.02); then 0, measured. A measured run shorter than ``min_valid_s`` becomes 21
(``too_short``); the minimum belongs to the signed ``metric_record`` and is an argument (``None``: none applied).

**The result** (``MetricResult``) is the series of ``θ`` (units ``deg``) and an ``experimental`` summary: the signed
median of ``θ`` (the direction of the habitual lean), the median and the P95 of ``|θ|`` (linear interpolation), and
``bridged_rows`` (measured rows with a bridged hip or shoulder). One measured row is enough for a number; no
measured row gives ``insufficient_evidence`` with null statistics and the reason of ``rows.evidence_reason``. There
is no event and no duration over a threshold: B2 asks for it only with a signed ``metric_record`` (AGENTS.md section
5.5). The P95 of ``|θ|`` has a floor under it: an upright trunk read at 1 px of noise on 200 px has a P95 of about
0.3 degree.

Errors are ``MetricError`` naming the argument.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal

import numpy as np

from taiji_ai.metrics import MetricError
from taiji_ai.metrics.geometry import (
    HIP_JOINTS,
    SHOULDER_JOINTS,
    bridged,
    lean_angle_deg,
    mid_hip,
    mid_shoulder,
    unusable_reason,
)
from taiji_ai.metrics.rows import (
    assemble_series,
    check_supported_views,
    check_view,
    eligibility,
    evidence_reason,
    minimum_s,
    segment_rows,
)
from taiji_ai.metrics.series import MetricResult, make_summary
from taiji_ai.quality.layers_io import PoseFiltered
from taiji_ai.schemas.metric import MissingReason, Statistic

METRIC_NAMES: Final = {"lr": "trunk_lean_lr", "fb": "trunk_lean_fb"}  # two metrics: each has its own record
SUPPORTED_VIEWS: Final = {"lr": ("front",), "fb": ("side",)}  # Appendix B2: front for left/right, side for forward/back
BLOCKING_FLAGS: Final = ("orientation_change",)  # the performer turns: the view assumption fails
METRIC_VERSION: Final = "1"
UNITS: Final = "deg"
PERCENTILE: Final = 95.0
_JOINTS: Final = (*HIP_JOINTS, *SHOULDER_JOINTS)  # the order of the metric: the hips, then the shoulders
_FRAME_INVALID: Final = int(MissingReason.frame_invalid)


def trunk_lean(
    layer: PoseFiltered,
    *,
    plane: Literal["lr", "fb"],
    view_category: str,
    flags: Mapping[str, bool],
    camera_id: str,
    roll_deg: float = 0.0,
    intervals: Sequence[Sequence[float]] | None = None,
    supported_views: Sequence[str] | None = None,
    min_valid_s: float | None = None,
) -> MetricResult:
    """The trunk lean of the segment of ``layer`` in the image plane (see the module docstring for every rule).

    ``plane``: ``"lr"`` (left/right lean, front view) or ``"fb"`` (forward/back lean, side view). ``view_category``:
    the segment's view, one of the ontology's. ``flags``: the flags of the segment (``{}``: none set). ``roll_deg``:
    the camera roll from ``roll_from_line`` (0 by default, within 45 degrees). ``intervals``: the ``[start, end)``
    intervals in stream seconds that the coach chose (``None``: the whole segment; ``[]``: none). ``supported_views``:
    the views of a signed record (``None``: the default of the plane). ``min_valid_s``: the minimum duration of a valid
    run in seconds (``None``: none applied). Raises ``MetricError`` naming the argument.
    """
    if not isinstance(plane, str) or plane not in METRIC_NAMES:
        raise MetricError(
            f"plane must be 'lr' (left/right lean, front view) or 'fb' (forward/back lean, side view), got {plane!r}"
        )
    rows = segment_rows(layer)
    minimum_run = minimum_s(min_valid_s, "min_valid_s")
    view = check_view(view_category, "view_category")
    views = SUPPORTED_VIEWS[plane] if supported_views is None else check_supported_views(supported_views)
    eligible = eligibility(
        rows.t_sec, intervals=intervals, flags=flags, blocking=BLOCKING_FLAGS, view=view, supported_views=views
    )
    pose = unusable_reason(rows.keypoints, rows.reason, _JOINTS)
    # on every row, which also validates the roll whether or not a row is measured
    theta = lean_angle_deg(mid_hip(rows.keypoints), mid_shoulder(rows.keypoints), roll_deg)
    undefined = np.where(np.isnan(theta), _FRAME_INVALID, 0)  # with the four joints present: the middle points coincide
    reason = np.where(eligible != 0, eligible, np.where(pose != 0, pose, undefined)).astype(np.uint8)
    parameters: dict[str, Any] = {
        "plane": plane,
        "roll_deg": float(roll_deg),
        "supported_views": "-".join(views),
        "min_valid_s": minimum_run,
        "percentile": PERCENTILE,
        "n_intervals": None if intervals is None else len(intervals),
    }
    series = assemble_series(
        rows,
        reason,
        theta,
        metric_name=METRIC_NAMES[plane],
        metric_version=METRIC_VERSION,
        units=UNITS,
        parameters=parameters,
        min_valid_s=minimum_run,
        camera_id=camera_id,
        view_category=view,
    )
    why = evidence_reason(series.reason, min_measured=1)
    names = ("lean_median", "lean_abs_median", "lean_abs_p95")
    if why is not None:
        statistics = [Statistic(name=n, value=None, units="deg", uses_threshold=False) for n in names]
        statistics.append(Statistic(name="bridged_rows", value=None, units="count", uses_threshold=False))
    else:
        measured = series.reason == 0
        angle = np.asarray(series.values)[measured]
        magnitude = np.abs(angle)
        leaning = int(bridged(rows.keypoints, rows.interpolated, _JOINTS)[measured].sum())
        numbers = (float(np.median(angle)), float(np.median(magnitude)), float(np.percentile(magnitude, PERCENTILE)))
        statistics = [
            Statistic(name=n, value=v, units="deg", uses_threshold=False) for n, v in zip(names, numbers, strict=True)
        ]
        statistics.append(Statistic(name="bridged_rows", value=float(leaning), units="count", uses_threshold=False))
    summary = make_summary(series, statistics=statistics, insufficient_reason=why, record_status="experimental")
    return MetricResult(series=series, summary=summary)
