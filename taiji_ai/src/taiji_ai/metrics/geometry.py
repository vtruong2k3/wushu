"""Geometry for the metrics (W7, P5.02): middle of the hips and of the shoulders, the trunk, its scale, the camera
roll.

Every metric of Appendix B starts here (hip height, trunk lean, speed in trunk lengths; P6.01 normalises with the same
scale), so the conventions are written once:

* **Pixels of the upright image, x right, y down**; computed in float64 whatever the input dtype; the arrays returned
  are new and read-only; inputs are never changed. Nothing here looks at time.
* **The middle of the hips** is ``H = (p11 + p12) / 2`` and **of the shoulders** ``S = (p5 + p6) / 2``: Appendix B's
  own definition, not the model's ``Hip`` (19) and ``Neck`` (18). A row is NaN where a joint of the pair is NaN.
* **A joint is usable when its value is finite**, observed or bridged (a short gap that the quality stage filled and
  flagged ``interpolated``). ``unusable_reason`` gives a row the reason (1 to 6, the numbers of the quality layer and
  of ``MissingReason``) of the **first joint of the list** that has no value, or 0; ``bridged`` says which rows lean
  on a bridged value, so that a metric can count them and a report can show them. Nothing is hidden and nothing is
  filled.
* **The trunk length** ``L(t) = |S - H|`` is NaN where a midpoint is NaN and where the distance is exactly 0
  (shoulders on the hips: not a trunk). **The scale** ``Λ`` is the median of ``L`` over the rows it is given (the
  segment, the reference standing segment of hip variant A, the segment of a comparison) where ``L`` is finite and
  above 0; it is NaN with 0 rows when there is none, and the caller then gives its rows the reason
  ``scale_unavailable``. There is no minimum count here: ``n_rows`` is returned and the metric (or its
  ``metric_record``) decides. It is the definition of ``quality.filters.torso_length_px`` on the mask layer; that
  function cannot read a final layer (a bridged cell is a value whose reason is not ``ok``) and a test keeps the two
  equal.
* **Angles** follow Appendix B2: ``θ = atan2(x_S - x_H, y_H - y_S)`` in degrees, 0 is vertical and positive when the
  top of the trunk leans to the image right; the result is wrapped to (-180, 180]. **The camera roll** has the same
  sign: ``roll_from_line(top, bottom)`` is the angle of a line the user drew along a true vertical, so ``θ_corrected =
  θ_raw - roll`` subtracts two angles of one convention and ``correct_roll`` is its coordinate form: with ``u = (sin
  roll, -cos roll)`` the corrected "up" and ``r = (cos roll, sin roll)`` the corrected "right", ``x' = (p - o) . r``
  and ``y' = (p - o) . (-u)``. The origin ``o`` is arbitrary: only differences of the result (a range, a height above
  a point) mean anything. The roll is limited to 45 degrees: more is a rotated video (the display rotation of ingest),
  not a camera roll to correct; that is a validity limit of an input, not a threshold on a movement (AGENTS.md section
  5.5).

Errors are ``MetricError`` naming the argument.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from taiji_ai.metrics import MetricError
from taiji_ai.pose.skeleton import IDX, NUM_JOINTS

HIP_JOINTS: Final = (IDX["LHip"], IDX["RHip"])
SHOULDER_JOINTS: Final = (IDX["LShoulder"], IDX["RShoulder"])
MAX_ROLL_DEG: Final = 45.0  # [deg] a line or a roll that leans more than this is refused
_ROLL_EPS: Final = 1e-9  # exactly 45 degrees, or what floating point makes of it, is allowed
_QUALITY_REASONS: Final = (1, 2, 3, 4, 5, 6)  # low_conf, non_finite, not_tracked, frame_invalid, outlier, no_frame


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _keypoints(keypoints: Any) -> np.ndarray:
    kp = np.asarray(keypoints)
    if kp.dtype.kind != "f":
        raise MetricError(
            f"keypoints must be a floating-point array (an integer array cannot hold NaN), got {kp.dtype}"
        )
    if kp.ndim != 3 or kp.shape[1:] != (NUM_JOINTS, 2):
        raise MetricError(f"keypoints must have shape (N, {NUM_JOINTS}, 2), got {kp.shape}")
    if np.isinf(kp).any():
        row, joint = np.argwhere(np.isinf(kp).any(axis=-1))[0]
        raise MetricError(f"keypoints has infinite values (first: row {row}, joint {joint})")
    return kp


def _joints(joints: Any) -> list[int]:
    if isinstance(joints, (str, bytes)) or not isinstance(joints, Sequence | np.ndarray) or len(joints) == 0:
        raise MetricError(f"joints must be a non-empty list of joint indices, got {joints!r}")
    out: list[int] = []
    for j in joints:
        if isinstance(j, (bool, np.bool_)) or not isinstance(j, (int, np.integer)) or not 0 <= j < NUM_JOINTS:
            raise MetricError(f"joints must be indices from 0 to {NUM_JOINTS - 1}, got {j!r}")
        out.append(int(j))
    if len(set(out)) != len(out):
        raise MetricError(f"joints must be distinct, got {out}")
    return out


def midpoint(keypoints: np.ndarray, joints: Sequence[int]) -> np.ndarray:
    """``(N, 2)`` float64: the mean of the given joints in every row; NaN where any of them is NaN."""
    kp = _keypoints(keypoints)
    return _frozen(kp[:, _joints(joints)].astype(np.float64).mean(axis=1))


def mid_hip(keypoints: np.ndarray) -> np.ndarray:
    """``H(t) = (p11 + p12) / 2``, ``(N, 2)`` float64 pixels; NaN where a hip is NaN."""
    return midpoint(keypoints, HIP_JOINTS)


def mid_shoulder(keypoints: np.ndarray) -> np.ndarray:
    """``S(t) = (p5 + p6) / 2``, ``(N, 2)`` float64 pixels; NaN where a shoulder is NaN."""
    return midpoint(keypoints, SHOULDER_JOINTS)


def unusable_reason(keypoints: np.ndarray, reason: np.ndarray, joints: Sequence[int]) -> np.ndarray:
    """``(N,)`` uint8: 0 where every joint of the list has a value, else the reason of the first that has none.

    ``keypoints`` ``(N, 26, 2)`` float pixels (NaN where there is no value), ``reason`` ``(N, 26)`` uint8: the final
    layer (a bridged cell has a value and a reason that is not ``ok``: it is usable). A cell without a value must have
    a reason of the quality layer (1 to 6) and a cell has both coordinates or neither; anything else is refused.
    """
    kp = _keypoints(keypoints)
    rs = np.asarray(reason)
    if rs.dtype != np.uint8:
        raise MetricError(f"reason must be a uint8 array of reason codes, got {rs.dtype}")
    if rs.shape != kp.shape[:2]:
        raise MetricError(f"reason must have shape {kp.shape[:2]} like keypoints, got {rs.shape}")
    cols = _joints(joints)
    nan = np.isnan(kp[:, cols])  # (N, k, 2)
    half = nan.any(axis=-1) & ~nan.all(axis=-1)
    if half.any():
        row, k = np.argwhere(half)[0]
        raise MetricError(
            f"keypoints has a cell with one NaN coordinate (row {row}, joint {cols[k]}): a cell has a position or none"
        )
    missing = nan.all(axis=-1)  # (N, k)
    codes = rs[:, cols]
    bad = missing & ~np.isin(codes, _QUALITY_REASONS)
    if bad.any():
        row, k = np.argwhere(bad)[0]
        raise MetricError(
            f"reason is {int(codes[row, k])} on a cell without a value (row {row}, joint {cols[k]}): "
            "a missing cell has a reason of the quality layer, 1 to 6"
        )
    first = np.argmax(missing, axis=1)  # the first joint of the list without a value (0 when there is none)
    picked = codes[np.arange(len(codes)), first]
    return _frozen(np.where(missing.any(axis=1), picked, 0).astype(np.uint8))


def bridged(keypoints: np.ndarray, interpolated: np.ndarray, joints: Sequence[int]) -> np.ndarray:
    """``(N,)`` bool: a joint of the list has a value that is a bridge (the flag ``interpolated`` of the final layer).

    The flag is only legal on a cell that has a value; a flag on a missing cell is refused.
    """
    kp = _keypoints(keypoints)
    flag = np.asarray(interpolated)
    if flag.dtype != np.bool_:
        raise MetricError(f"interpolated must be a bool array of flags, got {flag.dtype}")
    if flag.shape != kp.shape[:2]:
        raise MetricError(f"interpolated must have shape {kp.shape[:2]} like keypoints, got {flag.shape}")
    cols = _joints(joints)
    has_value = ~np.isnan(kp[:, cols]).any(axis=-1)
    marked = flag[:, cols]
    if (marked & ~has_value).any():
        row, k = np.argwhere(marked & ~has_value)[0]
        raise MetricError(f"interpolated is set on a cell that has no value (row {row}, joint {cols[k]})")
    return _frozen((marked & has_value).any(axis=1))


def trunk_length(keypoints: np.ndarray) -> np.ndarray:
    """``L(t) = |S - H|`` in pixels, ``(N,)`` float64; NaN where a midpoint is NaN or the distance is exactly 0."""
    kp = _keypoints(keypoints)
    length = np.linalg.norm(
        midpoint(kp, SHOULDER_JOINTS) - midpoint(kp, HIP_JOINTS), axis=-1
    )  # NaN where a midpoint is NaN
    return _frozen(np.where(length > 0.0, length, np.nan))


@dataclass(frozen=True)
class TrunkScale:
    """``Λ`` in pixels and the number of rows it is the median of (``NaN`` and 0 when no row was valid)."""

    scale_px: float
    n_rows: int


def trunk_scale(length: np.ndarray, rows: np.ndarray | None = None) -> TrunkScale:
    """``Λ``: the median of ``L`` over the rows given (a bool array, default all) where ``L`` is finite and above 0.

    ``length`` ``(N,)`` float (``trunk_length``). The rows are the caller's: the segment, the reference standing segment
    of hip variant A, the segment of a comparison. No valid row gives ``TrunkScale(nan, 0)``: nothing is guessed.
    """
    a = np.asarray(length)
    if a.dtype.kind != "f" or a.ndim != 1:
        raise MetricError(f"length must be a one-dimensional floating-point array, got {a.dtype} {a.shape}")
    if np.isinf(a).any():
        raise MetricError("length has infinite values")
    if rows is None:
        chosen = np.ones(a.shape, dtype=bool)
    else:
        chosen = np.asarray(rows)
        if chosen.dtype != np.bool_ or chosen.shape != a.shape:
            raise MetricError(f"rows must be a bool array with one entry per length, got {chosen.dtype} {chosen.shape}")
    valid = chosen & (a > 0.0)  # NaN is not above 0
    n = int(valid.sum())
    return TrunkScale(scale_px=float(np.median(a[valid])) if n else float("nan"), n_rows=n)


def _point(value: Any, name: str) -> np.ndarray:
    p = np.asarray(value)
    if p.dtype.kind not in "fiu" or p.shape != (2,):
        raise MetricError(f"{name} must be a point of two numbers (x, y), got {value!r}")
    return p.astype(np.float64)


def roll_from_line(top: Any, bottom: Any) -> float:
    """The camera roll in degrees from two points of a line drawn along a true vertical.

    It is ``atan2(x_top - x_bottom, y_bottom - y_top)``.

    Positive when the top of the line is to the right of its bottom: the sign of ``θ``. The two points may be given in
    either order (the one with the smaller ``y`` is the top) and the line may be any length. Raises ``MetricError``
    for a line that is a point, level, has a non-finite point, or leans more than 45 degrees from the vertical.
    """
    p, q = _point(top, "top"), _point(bottom, "bottom")
    if not (np.isfinite(p).all() and np.isfinite(q).all()):
        raise MetricError("the line must have finite points")
    if p[1] > q[1]:
        p, q = q, p  # the top is the point with the smaller y
    dy = q[1] - p[1]
    if dy <= 0.0:
        raise MetricError("the line must have two different heights: a point or a level line is not a vertical")
    roll = math.degrees(math.atan2(p[0] - q[0], dy))
    if abs(roll) > MAX_ROLL_DEG + _ROLL_EPS:
        raise MetricError(
            f"the line leans {roll:.1f} degrees from the vertical, more than {MAX_ROLL_DEG:g}: "
            "that is a rotated video, not a camera roll to correct"
        )
    return roll


def _roll(roll_deg: Any) -> float:
    if not _is_number(roll_deg) or not math.isfinite(float(roll_deg)):
        raise MetricError(f"roll_deg must be a finite number of degrees, got {roll_deg!r}")
    if abs(float(roll_deg)) > MAX_ROLL_DEG + _ROLL_EPS:
        raise MetricError(f"roll_deg must be within {MAX_ROLL_DEG:g} degrees, got {roll_deg!r}")
    return float(roll_deg)


def correct_roll(points: np.ndarray, roll_deg: float, origin: Sequence[float] = (0.0, 0.0)) -> np.ndarray:
    """The points in the frame where the reference line is vertical: ``x' = (p - o) . r`` and ``y' = (p - o) . (-u)``.

    ``points`` float ``(..., 2)`` pixels (x right, y down; NaN stays NaN), ``roll_deg`` from ``roll_from_line``
    (within 45 degrees), ``origin`` the point the result is measured from (arbitrary: only differences are
    meaningful). The result is float64, the same shape, read-only; a roll of 0 only subtracts the origin.
    """
    pts = np.asarray(points)
    if pts.dtype.kind != "f" or pts.ndim < 1 or pts.shape[-1] != 2:
        raise MetricError(f"points must be a floating-point array of shape (..., 2), got {pts.dtype} {pts.shape}")
    if np.isinf(pts).any():
        raise MetricError("points has infinite values")
    roll = math.radians(_roll(roll_deg))
    try:
        o = np.asarray(origin, dtype=np.float64)
    except (TypeError, ValueError):
        o = np.array([np.nan])
    if o.shape != (2,) or not np.isfinite(o).all():
        raise MetricError(f"origin must be a pair (x, y) of finite numbers, got {origin!r}")
    c, s = math.cos(roll), math.sin(roll)
    rel = pts.astype(np.float64) - o
    out = np.empty_like(rel)
    out[..., 0] = rel[..., 0] * c + rel[..., 1] * s
    out[..., 1] = -rel[..., 0] * s + rel[..., 1] * c
    return _frozen(out)


def _pair_array(value: Any, name: str) -> np.ndarray:
    a = np.asarray(value)
    if a.dtype.kind != "f" or a.ndim != 2 or a.shape[1] != 2:
        raise MetricError(f"{name} must be a floating-point array of shape (N, 2), got {a.dtype} {a.shape}")
    if np.isinf(a).any():  # atan2(inf, dy) is 90 degrees: an angle that no observation gave (BUG-0075)
        raise MetricError(f"{name} has infinite values")
    return a.astype(np.float64)


def lean_angle_deg(mid_hip: np.ndarray, mid_shoulder: np.ndarray, roll_deg: float = 0.0) -> np.ndarray:
    """``θ = atan2(x_S - x_H, y_H - y_S) - roll`` in degrees, ``(N,)`` float64 wrapped to (-180, 180].

    0 is vertical and the angle is positive when the top of the trunk leans to the image right. ``mid_hip`` and
    ``mid_shoulder`` are ``(N, 2)`` pixels (``mid_hip``, ``mid_shoulder``); ``roll_deg`` comes from ``roll_from_line``
    (0 by default, within 45 degrees). NaN where a midpoint is NaN or the two coincide: no angle is guessed.
    """
    hip, shoulder = _pair_array(mid_hip, "mid_hip"), _pair_array(mid_shoulder, "mid_shoulder")
    if len(shoulder) != len(hip):
        raise MetricError(f"mid_shoulder has {len(shoulder)} rows, expected {len(hip)} like mid_hip")
    roll = _roll(roll_deg)
    dx, dy = shoulder[:, 0] - hip[:, 0], hip[:, 1] - shoulder[:, 1]
    theta = np.degrees(np.arctan2(dx, dy)) - roll
    wrapped = (theta + 180.0) % 360.0 - 180.0
    wrapped = np.where(wrapped == -180.0, 180.0, wrapped)
    return _frozen(np.where((dx == 0.0) & (dy == 0.0), np.nan, wrapped))
