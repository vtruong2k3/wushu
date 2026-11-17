"""The mask layer of the pose (W6, P4.01): what is observed, and why a value is not.

``apply_mask`` takes the target's keypoints and scores and gives a **new** layer in which

* a keypoint whose score is under ``tau_kp`` is NaN with the reason ``low_conf``;
* a keypoint with a coordinate or a score that is not a finite number is NaN with the reason ``non_finite``;
* every keypoint of a frame that is not a frame of the target (``lost``, ``target_lost``, ``before_target``) is NaN with
  the reason ``not_tracked``;
* a **tracked** frame in which fewer than ``min_essential_fraction`` of the essential joints are usable is
  ``frame_invalid``: all 26 joints of the frame are NaN. A joint that was excluded already keeps its own reason; a joint
  that would have been kept gets the reason ``frame_invalid``.

A joint gets the first reason that applies, in the order ``not_tracked``, ``non_finite``, ``low_conf``,
``frame_invalid``. Nothing is filled, interpolated, clipped or corrected (AGENTS.md section 5.1): every value of the
result is either the input value at the same place or NaN, and every NaN has a reason. The input arrays are not
changed (section 5.3: raw, mask and filtered layers stay apart); the result arrays are new and read-only.

Rules and values (W6, ``Docs/TECH_WORKFLOW_V1.md``): ``tau_kp = 0.3``; essential joints ``ESSENTIAL`` of
``pose/skeleton.py`` (shoulders, hips, knees, ankles, heels: ten); a frame needs at least half of them. A score
**equal** to ``tau_kp`` is kept, and **five of ten** essential joints still make a valid frame (four do not). "Usable"
is exactly ``valid_keypoint_mask`` of the pose stage: finite coordinates, a finite score of at least ``tau_kp``; the
tracker and the review of the pose use the same rule. The values are provisional: the review of the pose on real
footage (P3.08) only *evaluates* them. They are data-validity parameters (what counts as observed), not a threshold
on a movement (AGENTS.md section 5.5); the parameters used travel with the result (``MaskResult.params``) so the run
can state them.

Units and coordinates: positions are pixels of the upright image, x to the right, y down (as in the raw layer); scores
are the model's own (not range-checked: a score below 0 is excluded, a score above 1 is kept as it is); times are
seconds from the stream start and are only carried along.

``mask_track`` applies the mask to a ``TargetTrack`` (W5) and keeps its timeline: the 1 s margins of the segment stay in
the result (the filters of P4.03 and P4.05 need them at the edges); ``in_segment`` marks them.
"""

from __future__ import annotations

import numbers
from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from taiji_ai.pose.runner import valid_keypoint_mask
from taiji_ai.pose.skeleton import ESSENTIAL, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.track.state import TRACKED, TargetTrack

TAU_KP: Final = 0.3  # W6: a score under this is not observed (evaluated by P3.08, not tuned here)
MIN_ESSENTIAL_FRACTION: Final = 0.5  # W6: a frame needs at least this share of the essential joints

OK: Final = 0
LOW_CONF: Final = 1
NON_FINITE: Final = 2
NOT_TRACKED: Final = 3
FRAME_INVALID: Final = 4
OUTLIER: Final = 5  # added by the Hampel stage (``quality/filters.py``, P4.03); ``apply_mask`` never emits it
# added by the resampling stage (``quality/resample.py``, P4.04): a grid time in a pause of the timestamps; the mask
# never emits it either
NO_FRAME: Final = 6
# the index is the code
REASON_NAMES: Final = ("ok", "low_conf", "non_finite", "not_tracked", "frame_invalid", "outlier", "no_frame")

_EPS: Final = 1e-9  # a share such as 0.29 of 100 joints is not an exact float: the boundary must not depend on it


def _is_real(value: Any) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_))


def _is_int(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))


@dataclass(frozen=True)
class MaskParams:
    """The parameters of the mask; the defaults are the values of W6. Wrong values raise ``QualityError``."""

    tau_kp: float = TAU_KP  # a finite score in [0, 1]: a keypoint under it is not observed
    essential: tuple[int, ...] = ESSENTIAL  # joint indices (halpe26/1) of the frame rule: non-empty, distinct
    min_essential_fraction: float = MIN_ESSENTIAL_FRACTION  # in (0, 1]: a frame with fewer usable is invalid

    def __post_init__(self) -> None:
        tau, fraction = self.tau_kp, self.min_essential_fraction
        if not (_is_real(tau) and 0.0 <= tau <= 1.0):  # a comparison with NaN is False: NaN is refused too
            raise QualityError(f"tau_kp must be a finite number in [0, 1], got {tau!r}")
        if not (_is_real(fraction) and 0.0 < fraction <= 1.0):
            raise QualityError(f"min_essential_fraction must be a finite number in (0, 1], got {fraction!r}")
        try:
            joints = tuple(self.essential)
        except TypeError as exc:
            raise QualityError(f"essential must be a sequence of joint indices, got {self.essential!r}") from exc
        if not joints or not all(_is_int(j) and 0 <= j < NUM_JOINTS for j in joints) or len(set(joints)) != len(joints):
            raise QualityError(
                f"essential must be a non-empty set of distinct joint indices in [0, {NUM_JOINTS - 1}], got {joints!r}"
            )
        object.__setattr__(self, "tau_kp", float(tau))
        object.__setattr__(self, "min_essential_fraction", float(fraction))
        object.__setattr__(self, "essential", tuple(int(j) for j in joints))


@dataclass(frozen=True, eq=False)
class MaskResult:
    """The mask layer of ``T`` frames; every array is new and read-only (``T`` may be 0)."""

    keypoints: np.ndarray  # (T, 26, 2) the input dtype; the input value, or NaN where ``reason`` is not ``ok``
    scores: np.ndarray  # (T, 26) the input dtype; the model's scores as they were given (NaN stays NaN)
    reason: np.ndarray  # (T, 26) uint8; 0 ok, 1 low_conf, 2 non_finite, 3 not_tracked, 4 frame_invalid (REASON_NAMES)
    # (codes 5, outlier, and 6, no_frame, are added later by the Hampel and resampling stages: never in a mask layer)
    tracked: np.ndarray  # (T,) bool; the frame is a frame of the target
    n_essential_valid: np.ndarray  # (T,) usable essential joints of a tracked frame (before the frame rule); else 0
    frame_invalid: np.ndarray  # (T,) bool; a tracked frame with too few usable essential joints
    params: MaskParams

    @property
    def usable(self) -> np.ndarray:
        """``(T,)`` bool: the frame is the target's and has enough essential joints."""
        return self.tracked & ~self.frame_invalid


@dataclass(frozen=True, eq=False)
class MaskedTrack:
    """``mask_track``: the mask of a ``TargetTrack`` with the timeline of the track (read-only copies)."""

    mask: MaskResult
    frame_index: np.ndarray  # (T,) int32; row of the frame in pts.parquet
    t_sec: np.ndarray  # (T,) float64; [s] from the stream start, real PTS
    in_segment: np.ndarray  # (T,) bool; the frame lies in the segment asked for (False in the margins)
    status: np.ndarray  # (T,) uint8; TRACKED, LOST, TARGET_LOST, BEFORE_TARGET (``track.state.STATUS_NAMES``)


def _frozen(a: np.ndarray) -> np.ndarray:
    a.setflags(write=False)
    return a


def _float_array(value: Any, name: str, shape_tail: tuple[int, ...]) -> np.ndarray:
    a = np.asarray(value)
    if a.dtype.kind != "f":
        raise QualityError(f"{name} must be a floating-point array (an integer array cannot hold NaN), got {a.dtype}")
    if a.ndim != 1 + len(shape_tail) or a.shape[1:] != shape_tail:
        raise QualityError(f"{name} must have shape (T, {', '.join(map(str, shape_tail))}), got {a.shape}")
    return a


def frame_invalid_mask(
    is_tracked: np.ndarray, n_valid: np.ndarray, n_essential: int, min_essential_fraction: float
) -> np.ndarray:
    """The frame rule: ``(T,)`` bool, True for a tracked frame with fewer than ``min_essential_fraction`` of the
    ``n_essential`` essential joints usable (``n_valid``), with the tolerance that keeps a boundary such as 5 of 10 off
    float rounding. The one place of the rule: ``apply_mask`` and the reader of ``pose_masked.npz`` both call it."""
    return is_tracked & (n_valid < min_essential_fraction * n_essential - _EPS)


def apply_mask(
    keypoints: np.ndarray,
    scores: np.ndarray,
    tracked: np.ndarray | None = None,
    params: MaskParams | None = None,
) -> MaskResult:
    """Mask ``keypoints`` ``(T, 26, 2)`` (pixels) by ``scores`` ``(T, 26)``; see the module docstring for the rules.

    ``tracked`` is ``(T,)`` bool, True for a frame of the target; ``None`` means every frame is. The inputs are not
    changed. Raises ``QualityError`` for arrays of another shape or type.
    """
    params = MaskParams() if params is None else params
    kp = _float_array(keypoints, "keypoints", (NUM_JOINTS, 2))
    n = kp.shape[0]
    sc = _float_array(scores, "scores", (NUM_JOINTS,))
    if sc.shape[0] != n:
        raise QualityError(f"scores must have shape ({n}, {NUM_JOINTS}) like keypoints, got {sc.shape}")
    if tracked is None:
        is_tracked = np.ones(n, dtype=bool)
    else:
        given = np.asarray(tracked)
        if given.dtype != np.bool_ or given.shape != (n,):
            raise QualityError(f"tracked must be a bool array of shape ({n},), got {given.dtype} {given.shape}")
        is_tracked = given.copy()

    finite = np.isfinite(kp).all(axis=-1) & np.isfinite(sc)
    usable_joint = valid_keypoint_mask(kp, sc, params.tau_kp)  # the one rule of "valid" of the pose stage
    reason = np.full((n, NUM_JOINTS), OK, dtype=np.uint8)
    reason[~usable_joint] = LOW_CONF
    reason[~finite] = NON_FINITE

    essential = list(params.essential)
    n_valid = np.where(is_tracked, usable_joint[:, essential].sum(axis=1), 0)
    frame_invalid = frame_invalid_mask(is_tracked, n_valid, len(essential), params.min_essential_fraction)
    reason[(reason == OK) & frame_invalid[:, None]] = FRAME_INVALID
    reason[~is_tracked] = NOT_TRACKED

    masked = np.array(kp, copy=True)
    masked[reason != OK] = np.nan
    return MaskResult(
        keypoints=_frozen(masked),
        scores=_frozen(np.array(sc, copy=True)),
        reason=_frozen(reason),
        tracked=_frozen(is_tracked),
        n_essential_valid=_frozen(n_valid),
        frame_invalid=_frozen(frame_invalid),
        params=params,
    )


def mask_track(track: TargetTrack, params: MaskParams | None = None) -> MaskedTrack:
    """The mask of the target over time: a frame is the target's when its status is ``tracked`` (W5).

    The frames that are not (``lost``, ``target_lost``, ``before_target``) are ``not_tracked`` here; which of the three
    it was stays in ``status``. Every frame of the track is kept, the margins of the segment included.
    """
    return MaskedTrack(
        mask=apply_mask(track.keypoints, track.scores, track.status == TRACKED, params),
        frame_index=_frozen(np.array(track.frame_index, copy=True)),
        t_sec=_frozen(np.array(track.t_sec, copy=True)),
        in_segment=_frozen(np.array(track.in_segment, copy=True)),
        status=_frozen(np.array(track.status, copy=True)),
    )
