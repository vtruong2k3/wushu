"""Frame features for the comparison of a segment with a reference segment (W8, Appendix C.1, P6.01).

``frame_features`` turns the segment rows of one final layer (``PoseFiltered``) into the vector that the masked cost of
P6.02 compares: for each frame ``f(t) = [(p_j(t) - H(t)) / Λ for j in J] + [(sin φ_s, cos φ_s) for s in segments]``,
with a mask that says, for every frame and every unit, whether the feature is a value and why not.

* **Units and coordinates.** Pixels of the upright image, x right, y down, float64 (``metrics/geometry.py``). A
  *position* unit is the joint relative to the middle of the hips ``H = (p11 + p12) / 2``, divided by the scale
  ``Λ``: so it is in **trunk lengths**, x right and y down, dimensionless. ``Λ`` is **one number for the whole
  segment**, the median trunk length of its rows (``rows.scale_of``), never a per-frame value (W8): scaling one frame
  changes only that frame's features. An *angle* unit is the direction of a limb segment (or of the trunk axis, middle
  of the hips to middle of the shoulders) as the pair ``(sin φ, cos φ)`` with ``φ = atan2(dx, -dy)``: 0 is up,
  positive toward the image right (the angle of Appendix B2, so the trunk unit is the ``θ`` of trunk lean). The pair
  is taken from the vector itself (``dx / |v|``, ``-dy / |v|``): no angle is ever wrapped, so 359 degrees lies next
  to 1 degree. An angle has no scale (it needs no ``Λ``).
* **Camera roll.** ``roll_deg`` (from ``geometry.roll_from_line``, within 45 degrees, 0 by default) is taken out of
  every joint first (``geometry.correct_roll``): two cameras with a different roll would differ for no movement.
  ``Λ`` is a length and does not change with the roll.
* **The units** are the positions of ``joints`` (``DEFAULT_JOINTS``: 12 trunk and limb joints) and then the angles of
  ``segments`` (``DEFAULT_SEGMENTS``: 9), each in the order asked. ``SEGMENTS`` maps a name to the joints whose mean
  is its proximal end and the joints whose mean is its distal end.
* **A feature is a value only when everything it needs is a value**: a position needs its joint, both hips and
  ``Λ``; an angle needs its two ends (the four joints 11, 12, 5, 6 for the trunk) and a length above 0. A bridged
  cell (a short gap that the quality stage filled and flagged ``interpolated``) is a value; the feature that leans on
  it is flagged in ``bridged``, as in the metrics. Otherwise the feature is **NaN in both components** and ``reason``
  says why (``FeatureReason``): the reason (1 to 6) of the first unusable joint of the unit in the order *the joint
  itself, then the hips* (an angle: its ends in order, the trunk hips before shoulders; the order of
  ``geometry.unusable_reason`` and of ``trunk_lean``), then 19 ``scale_unavailable`` for a position, then 23
  ``zero_length`` for an angle whose ends coincide exactly, then (only when ``min_segment_length`` is given, below)
  19 or 24 ``short_segment`` for an angle. Nothing is filled, forward-filled or set to 0 (AGENTS.md 5.1).
* ``min_segment_length`` is the optional minimum length of a segment **in trunk lengths** (its length in pixels
  divided by ``Λ``); it has no default (it belongs to the caller and to a signed ``metric_record`` later,
  AGENTS.md 5.5) and ``None`` applies none. **Without it a very short segment is still a value**, and its direction
  is arbitrary once its length is comparable to the noise of the pose (R1 of P6.01: the forearm of SYN-10 shrinks to
  0.02 trunk lengths). With it, an *angle* whose length is below the minimum (equal is enough) is not a value: reason
  24 ``short_segment``, NaN in both components. It applies to angle units only (a position has no direction) and
  only after the other tests: a missing joint (1 to 6) and an exact zero length (23) come first. A minimum in trunk
  lengths needs ``Λ``: when ``Λ`` is not finite every angle that would be a value is 19 ``scale_unavailable``
  (with no minimum an angle still needs none).
* **The clock** is the real one: ``t_sec`` are the seconds from the stream start of the grid rows of the segment,
  never a row index (AGENTS.md 5.2). DTW compares shape only; tempo is reported on these times.
* ``min_scale_s`` is the optional minimum duration (seconds) of the rows that ``Λ`` is the median of; it has no
  default (it belongs to a signed ``metric_record`` later, AGENTS.md 5.5): ``None`` applies none, and ``Λ`` is then
  NaN only when no row has a trunk. When it is not met ``Λ`` is NaN and every position is 19, with ``scale_rows``
  and ``scale_s`` kept so that a report can say why.

Ideas, not code (AGENTS.md 9.2): the normalisation by the trunk length and a per-joint similarity masked by
confidence come from the Motion Embedding 24-form repository (``repos/taolu/_no-license``, commit ``77e84bee``, no
licence: read only), and a list of joint and segment angles from QAQA (commit ``013a25a1``, Apache-2.0); Appendix C
is the design and nothing is copied.

Results are frozen dataclasses of new read-only arrays; the layer is never changed. Errors are ``CompareError``
naming the argument; a number or a type is echoed, never a string given by the caller.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

import numpy as np

from taiji_ai.compare import CompareError
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.geometry import (
    HIP_JOINTS,
    MAX_ROLL_DEG,
    SHOULDER_JOINTS,
    bridged,
    correct_roll,
    midpoint,
    unusable_reason,
)
from taiji_ai.metrics.rows import scale_of, segment_rows
from taiji_ai.pose.skeleton import IDX
from taiji_ai.quality.layers_io import PoseFiltered
from taiji_ai.schemas.metric import MissingReason
from taiji_ai.schemas.quality_layers import DataSource

FEATURE_VERSION: Final = "1"


class FeatureReason(enum.IntEnum):
    """Why a feature is not a value: 0 it is; 1 to 6 and 19 have the numbers of ``MissingReason``; 23, 24 are new."""

    valid = 0
    low_conf = int(MissingReason.low_conf)
    non_finite = int(MissingReason.non_finite)
    not_tracked = int(MissingReason.not_tracked)
    frame_invalid = int(MissingReason.frame_invalid)
    outlier = int(MissingReason.outlier)
    no_frame = int(MissingReason.no_frame)
    scale_unavailable = int(MissingReason.scale_unavailable)  # a position and no trunk scale
    zero_length = 23  # an angle whose two ends coincide exactly: the direction does not exist
    short_segment = 24  # an angle whose segment is shorter than ``min_segment_length`` trunk lengths


_ZERO_LENGTH: Final = int(FeatureReason.zero_length)
_NO_SCALE: Final = int(FeatureReason.scale_unavailable)
_SHORT: Final = int(FeatureReason.short_segment)

DEFAULT_JOINTS: Final[tuple[str, ...]] = (
    "LShoulder", "RShoulder", "LElbow", "RElbow", "LWrist", "RWrist",
    "LHip", "RHip", "LKnee", "RKnee", "LAnkle", "RAnkle",
)  # fmt: skip
SEGMENTS: Final[dict[str, tuple[tuple[int, ...], tuple[int, ...]]]] = {
    "l_upper_arm": ((IDX["LShoulder"],), (IDX["LElbow"],)),
    "l_forearm": ((IDX["LElbow"],), (IDX["LWrist"],)),
    "r_upper_arm": ((IDX["RShoulder"],), (IDX["RElbow"],)),
    "r_forearm": ((IDX["RElbow"],), (IDX["RWrist"],)),
    "l_thigh": ((IDX["LHip"],), (IDX["LKnee"],)),
    "l_shank": ((IDX["LKnee"],), (IDX["LAnkle"],)),
    "r_thigh": ((IDX["RHip"],), (IDX["RKnee"],)),
    "r_shank": ((IDX["RKnee"],), (IDX["RAnkle"],)),
    "trunk": (HIP_JOINTS, SHOULDER_JOINTS),  # the trunk axis: middle of the hips to middle of the shoulders
}
DEFAULT_SEGMENTS: Final[tuple[str, ...]] = tuple(SEGMENTS)


@dataclass(frozen=True, eq=False)
class FeatureUnit:
    """One column of the features: a ``position`` of a joint or the ``angle`` of a segment.

    ``name`` is the joint name or the segment name; ``joints`` are the joint indices the unit reads, in the order in
    which the reason of the first unusable one is taken (a position: its joint; an angle: the proximal joints, then the
    distal ones).
    """

    kind: Literal["position", "angle"]
    name: str
    joints: tuple[int, ...]


@dataclass(frozen=True, eq=False)
class FrameFeatures:
    """The features of the rows of one segment; every array is a new read-only array.

    ``t_sec`` ``(N,)`` float64 seconds from the stream start (the grid rows of the segment); ``values`` ``(N, U, 2)``
    float64: a position in trunk lengths from the middle of the hips (x right, y down) or ``(sin φ, cos φ)``, NaN in
    both components where the unit is not valid, never 0; ``valid`` ``(N, U)`` bool; ``reason`` ``(N, U)`` uint8
    (``FeatureReason``, 0 where valid); ``bridged`` ``(N, U)`` bool: a valid feature that leans on a bridged cell;
    ``units`` the ``U`` columns, positions first and then angles, in the order asked. ``scale_px`` is ``Λ`` in pixels
    (NaN when unavailable) with ``scale_rows`` the rows it is the median of and ``scale_s`` the seconds they last;
    ``roll_deg`` the camera roll that was taken out; ``step_s`` the step of the grid (``None`` for fewer than two rows);
    ``recording_id`` and ``data_sources`` the provenance of the layer (a derived artifact inherits its restrictions,
    AGENTS.md 9.4); ``version`` the version of these rules (``FEATURE_VERSION``); ``min_scale_s`` and
    ``min_segment_length`` echo the two optional arguments that decided which features are values (``None``: none was
    applied), so that features made with other settings are never compared as if they were alike.
    """

    t_sec: np.ndarray
    values: np.ndarray
    valid: np.ndarray
    reason: np.ndarray
    bridged: np.ndarray
    units: tuple[FeatureUnit, ...]
    scale_px: float
    scale_rows: int
    scale_s: float
    roll_deg: float
    step_s: float | None
    recording_id: str
    data_sources: tuple[DataSource, ...]
    version: str
    min_scale_s: float | None = None
    min_segment_length: float | None = None


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, (bool, np.bool_))


def _shown(value: Any) -> str:
    """What an error says of an argument: the number itself, or only the type (never a string of the caller)."""
    return repr(_as_float(value)) if _is_number(value) else type(value).__name__


def _as_float(value: Any) -> float:
    """``float(value)``, except that an integer beyond the range of a float is an infinity (BUG-0079), which every
    check below refuses, instead of an ``OverflowError``."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _names(value: Any, argument: str, vocabulary: Mapping[str, Any], what: str) -> tuple[str, ...]:
    """The names as a tuple: a non-empty list of distinct names of ``vocabulary``; ``CompareError`` otherwise."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CompareError(f"{argument} must be a non-empty list of {what} names, got {type(value).__name__}")
    if len(value) == 0:
        raise CompareError(f"{argument} must not be empty: it needs at least one {what} name")
    for i, item in enumerate(value):
        if not isinstance(item, str) or item not in vocabulary:
            raise CompareError(f"{argument}[{i}] must be one of the {what} names known to compare.features")
    if len(set(value)) != len(value):
        raise CompareError(f"{argument} must not repeat a {what} name")
    return tuple(value)


def _roll(roll_deg: Any) -> float:
    if not _is_number(roll_deg) or not math.isfinite(_as_float(roll_deg)):
        raise CompareError(f"roll_deg must be a finite number of degrees, got {_shown(roll_deg)}")
    roll = _as_float(roll_deg)
    try:
        correct_roll(np.zeros((1, 2)), roll)  # the limit (45 degrees and its float tolerance) is the geometry's
    except MetricError as exc:
        raise CompareError(f"roll_deg must be within {MAX_ROLL_DEG:g} degrees, got {roll!r}") from exc
    return roll


def _minimum(value: Any, argument: str, unit: str) -> float | None:
    """``None`` (none applied) or a finite number above 0 in ``unit``; else ``CompareError`` naming ``argument``."""
    if value is None:
        return None
    if not _is_number(value) or not math.isfinite(_as_float(value)) or _as_float(value) <= 0.0:
        raise CompareError(f"{argument} must be None or a finite number of {unit} above 0, got {_shown(value)}")
    return _as_float(value)


def _units(joints: tuple[str, ...], segments: tuple[str, ...]) -> tuple[FeatureUnit, ...]:
    positions = tuple(FeatureUnit("position", name, (IDX[name],)) for name in joints)
    angles = tuple(FeatureUnit("angle", name, (*SEGMENTS[name][0], *SEGMENTS[name][1])) for name in segments)
    return positions + angles


def _needed(unit: FeatureUnit) -> tuple[int, ...]:
    """The joints a unit needs, the one to report first first: a position is its joint then the hips (a hip is not
    repeated: ``LHip`` is ``(11, 12)`` and ``RHip`` is ``(12, 11)``); an angle is its own joints."""
    if unit.kind == "angle":
        return unit.joints
    return (*unit.joints, *(h for h in HIP_JOINTS if h not in unit.joints))


def frame_features(
    layer: PoseFiltered,
    *,
    roll_deg: float = 0.0,
    joints: Sequence[str] = DEFAULT_JOINTS,
    segments: Sequence[str] = DEFAULT_SEGMENTS,
    min_scale_s: float | None = None,
    min_segment_length: float | None = None,
) -> FrameFeatures:
    """The frame features of the segment of ``layer`` (see the module docstring for every rule).

    ``layer``: the final layer (``PoseFiltered``); only the rows of its segment are used (never the margins).
    ``roll_deg``: the camera roll in degrees from ``roll_from_line`` (0 by default, within 45 degrees).
    ``joints``: names of the joints whose normalised positions are features (``DEFAULT_JOINTS``); ``segments``: names of
    the segments in ``SEGMENTS`` whose angles are features (``DEFAULT_SEGMENTS``); both non-empty, without repeats.
    ``min_scale_s``: the minimum duration in seconds of the rows that ``Λ`` is the median of (``None``: none applied).
    ``min_segment_length``: the minimum length of a segment in trunk lengths for its angle to be a value (``None``: none
    applied; equal to the minimum is enough; 24 below it, 19 when there is no ``Λ``). Raises ``CompareError`` naming
    the argument.
    """
    if not isinstance(layer, PoseFiltered):
        raise CompareError(f"layer must be a PoseFiltered, got {type(layer).__name__}")
    joint_names = _names(joints, "joints", IDX, "joint")
    segment_names = _names(segments, "segments", SEGMENTS, "segment")
    roll = _roll(roll_deg)
    minimum = _minimum(min_scale_s, "min_scale_s", "seconds")
    shortest = _minimum(min_segment_length, "min_segment_length", "trunk lengths")
    try:
        return _features(layer, roll, _units(joint_names, segment_names), minimum, shortest)
    except MetricError as exc:  # a layer that breaks the contract of its cells or of its segment: chained, not hidden
        raise CompareError(f"layer: {exc}") from exc


def _features(
    layer: PoseFiltered,
    roll: float,
    units: tuple[FeatureUnit, ...],
    minimum: float | None,
    shortest: float | None,
) -> FrameFeatures:
    rows = segment_rows(layer)
    scale = scale_of(rows, minimum)  # one Λ for the segment, from the rows as observed (a roll does not change it)
    kp = rows.keypoints
    points = correct_roll(kp, roll)  # (N, 26, 2) float64 in the frame where the plumb line is vertical
    hip = midpoint(points, HIP_JOINTS)  # (N, 2): the mean of the corrected hips
    n = len(rows.t_sec)
    values = np.full((n, len(units), 2), np.nan)
    valid = np.zeros((n, len(units)), dtype=bool)
    reason = np.zeros((n, len(units)), dtype=np.uint8)
    leans = np.zeros((n, len(units)), dtype=bool)
    for u, unit in enumerate(units):
        needed = _needed(unit)
        code = unusable_reason(kp, rows.reason, needed).copy()  # 0, or the reason of the first joint without a value
        if unit.kind == "position":
            if not math.isfinite(scale.scale_px):
                code[code == 0] = _NO_SCALE
            ok = code == 0
            values[ok, u] = (points[ok, unit.joints[0]] - hip[ok]) / scale.scale_px
        else:
            proximal, distal = SEGMENTS[unit.name]
            start, end = midpoint(points, proximal), midpoint(points, distal)
            dx, dy = end[:, 0] - start[:, 0], end[:, 1] - start[:, 1]
            code[(code == 0) & (dx == 0.0) & (dy == 0.0)] = _ZERO_LENGTH  # NaN is not 0: a missing end never gets here
            if shortest is not None:  # a length in trunk lengths needs the scale; a zero length is 23 already
                if not math.isfinite(scale.scale_px):
                    code[code == 0] = _NO_SCALE
                else:
                    code[(code == 0) & (np.hypot(dx, dy) / scale.scale_px < shortest)] = _SHORT
            ok = code == 0
            length = np.hypot(dx[ok], dy[ok])
            values[ok, u, 0] = dx[ok] / length  # sin φ
            values[ok, u, 1] = -dy[ok] / length  # cos φ (y points down: up is -dy)
        valid[:, u] = ok
        reason[:, u] = code
        leans[:, u] = bridged(kp, rows.interpolated, needed) & ok
    return FrameFeatures(
        t_sec=_frozen(rows.t_sec.copy()),
        values=_frozen(values),
        valid=_frozen(valid),
        reason=_frozen(reason),
        bridged=_frozen(leans),
        units=units,
        scale_px=scale.scale_px,
        scale_rows=scale.n_rows,
        scale_s=scale.duration_s,
        roll_deg=roll,
        step_s=rows.step_s,
        recording_id=rows.recording_id,
        data_sources=rows.data_sources,
        version=FEATURE_VERSION,
        min_scale_s=minimum,
        min_segment_length=shortest,
    )
