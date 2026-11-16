"""Per-frame measures of the target's pose that point at suspect frames (P3.08).

Every function takes arrays of the target track of P3.06 (``keypoints`` ``(F, 26, 2)`` pixels, y down, NaN where the
target is not tracked; ``scores`` ``(F, 26)``; ``valid`` ``(F, 26)`` bool from ``valid_keypoint_mask``; ``t_sec`` the
real times) and returns a float array of length ``F``, **NaN where the measure cannot be decided** (a joint missing,
no previous frame). Nothing is filled. The unit of every distance is the **median body height of the clip**
(``reference_height``): the hull height of the valid keypoints, a dimensionless scale that does not depend on the
zoom.

These measures only rank frames for a person to look at (``taiji_ai.audit.select``); none of them is a threshold or a
verdict (AGENTS.md section 5.5). The four ``find_*`` measures point at the situations of the plan (a hand in front of
the trunk, the trunk turning, one foot raised, the back to the camera); they are sampling aids, and the review says what
the situation really was.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import Final

import numpy as np

from taiji_ai.pose.order_check import check_joint_order
from taiji_ai.pose.runner import valid_keypoint_mask
from taiji_ai.pose.skeleton import ESSENTIAL, IDX, LR_PAIRS

TAU_KP: Final = 0.3  # the proposal of W6, here only evaluated

# Limb bones whose 2D length should stay about the same: upper arm, forearm, thigh, shin, both sides.
BONES: Final[tuple[tuple[int, int], ...]] = ((5, 7), (7, 9), (6, 8), (8, 10), (11, 13), (13, 15), (12, 14), (14, 16))
FACE: Final[tuple[int, ...]] = (IDX["Nose"], IDX["LEye"], IDX["REye"], IDX["LEar"], IDX["REar"])
_TORSO: Final[tuple[int, ...]] = (IDX["LShoulder"], IDX["RShoulder"], IDX["LHip"], IDX["RHip"])


def _nanmax(a: np.ndarray, axis: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an all-NaN row is NaN: undecidable
        return np.nanmax(a, axis=axis)


def valid_joints(keypoints: np.ndarray, scores: np.ndarray, tau: float = TAU_KP) -> np.ndarray:
    """``(F, 26)`` bool: finite coordinates and a score of at least ``tau``."""
    return valid_keypoint_mask(keypoints, scores, tau)


def body_height(keypoints: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Height (pixels) of the box of the valid keypoints of each frame; NaN with fewer than two valid or no extent."""
    y = np.where(valid, keypoints[..., 1], np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        height = np.nanmax(y, axis=1) - np.nanmin(y, axis=1)
    height[(valid.sum(axis=1) < 2) | ~(height > 0.0)] = np.nan
    return height  # type: ignore[no-any-return]


def reference_height(height: np.ndarray) -> float:
    """The median body height of a clip (NaN when no frame has one)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return float(np.nanmedian(height))


def low_essential(valid: np.ndarray) -> np.ndarray:
    """Number of the 10 essential joints that are not valid in each frame (a frame without the target counts all 10)."""
    return (~valid[:, list(ESSENTIAL)]).sum(axis=1).astype(np.float64)


def jump_speed(keypoints: np.ndarray, valid: np.ndarray, t_sec: np.ndarray, ref_height: float) -> np.ndarray:
    """Largest speed of any joint valid in two consecutive frames, in median body heights per second (real time)."""
    out = np.full(keypoints.shape[0], np.nan)
    if keypoints.shape[0] < 2 or not (ref_height > 0.0):
        return out
    step = np.linalg.norm(keypoints[1:] - keypoints[:-1], axis=-1)
    dt = np.diff(np.asarray(t_sec, dtype=np.float64))[:, None]
    speed = np.where(valid[1:] & valid[:-1], step / dt / ref_height, np.nan)
    out[1:] = _nanmax(speed, axis=1)
    return out


def bone_deviation(keypoints: np.ndarray, valid: np.ndarray, bones: Sequence[tuple[int, int]] = BONES) -> np.ndarray:
    """Largest relative deviation of a limb bone's 2D length from the clip median of that bone (0.5: half or 1.5x)."""
    lengths = np.full((keypoints.shape[0], len(bones)), np.nan)
    for i, (a, b) in enumerate(bones):
        ok = valid[:, a] & valid[:, b]
        lengths[ok, i] = np.linalg.norm(keypoints[ok, a] - keypoints[ok, b], axis=-1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nanmedian(lengths, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        deviation = np.abs(lengths / median - 1.0)
    return _nanmax(deviation, axis=1)


def swap_margin(
    keypoints: np.ndarray,
    valid: np.ndarray,
    ref_height: float,
    pairs: Sequence[tuple[int, int]] = LR_PAIRS,
) -> np.ndarray:
    """How much nearer the two labels of a left/right pair are to each other's earlier place than to their own, over the
    pairs, in median body heights. Positive: crossing is cheaper than staying, as when the two labels are exchanged; a
    fast limb that does not cross gives a negative number. A preview of the swap detector of P4.06."""
    out = np.full(keypoints.shape[0], np.nan)
    if keypoints.shape[0] < 2 or not (ref_height > 0.0):
        return out
    left, right = [a for a, _ in pairs], [b for _, b in pairs]
    lk, rk = keypoints[:, left], keypoints[:, right]
    stay = np.linalg.norm(lk[1:] - lk[:-1], axis=-1) + np.linalg.norm(rk[1:] - rk[:-1], axis=-1)
    cross = np.linalg.norm(lk[1:] - rk[:-1], axis=-1) + np.linalg.norm(rk[1:] - lk[:-1], axis=-1)
    ok = valid[1:][:, left] & valid[:-1][:, left] & valid[1:][:, right] & valid[:-1][:, right]
    out[1:] = _nanmax(np.where(ok, (stay - cross) / ref_height, np.nan), axis=1)
    return out


def structure_failures(
    keypoints: np.ndarray, scores: np.ndarray, tracked: np.ndarray, tau: float = TAU_KP
) -> np.ndarray:
    """Number of checks of ``check_joint_order`` that fail in each tracked frame (0 to 4); NaN where not tracked. The
    check is made for an upright person and says undecidable otherwise, which is not a failure."""
    out = np.full(keypoints.shape[0], np.nan)
    for f in np.flatnonzero(tracked):
        report = check_joint_order(keypoints[f], scores[f], min_score=tau)
        out[f] = float(sum(check.status == "fail" for check in report.checks))
    return out


# --- finders of the four situations (sampling aids) ------------------------------------------------------------------
def face_vs_body_score(scores: np.ndarray) -> np.ndarray:
    """Mean score of the essential joints minus mean score of the face joints: high when the body is seen and the face
    is not, as with the back to the camera."""
    return scores[:, list(ESSENTIAL)].mean(axis=1) - scores[:, list(FACE)].mean(axis=1)


def ankle_height_difference(keypoints: np.ndarray, valid: np.ndarray, ref_height: float) -> np.ndarray:
    """Vertical distance of the two ankles in median body heights: large when one foot is raised."""
    la, ra = IDX["LAnkle"], IDX["RAnkle"]
    ok = valid[:, la] & valid[:, ra]
    return np.where(ok, np.abs(keypoints[:, la, 1] - keypoints[:, ra, 1]) / ref_height, np.nan)


def _torso_length(keypoints: np.ndarray, valid: np.ndarray) -> np.ndarray:
    ls, rs, lh, rh = _TORSO
    ok = valid[:, list(_TORSO)].all(axis=1)
    length = np.linalg.norm(
        (keypoints[:, ls] + keypoints[:, rs]) / 2.0 - (keypoints[:, lh] + keypoints[:, rh]) / 2.0, axis=-1
    )
    return np.where(ok & (length > 0.0), length, np.nan)


def shoulder_width_ratio(keypoints: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Distance between the shoulders over the torso length: the width of a front or back view, near 0 in profile."""
    ls, rs = IDX["LShoulder"], IDX["RShoulder"]
    width = np.linalg.norm(keypoints[:, ls] - keypoints[:, rs], axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(valid[:, [ls, rs]].all(axis=1), width / _torso_length(keypoints, valid), np.nan)


def rotation_rate(ratio: np.ndarray, t_sec: np.ndarray, lag_s: float = 0.5) -> np.ndarray:
    """How fast the shoulder-width ratio changes over about ``lag_s`` of real time (per second): high while turning."""
    t = np.asarray(t_sec, dtype=np.float64)
    earlier = np.searchsorted(t, t - lag_s, side="right") - 1  # the last frame at least lag_s before, -1 if none
    out = np.full(t.shape, np.nan)
    ok = earlier >= 0
    out[ok] = np.abs(ratio[ok] - ratio[earlier[ok]]) / (t[ok] - t[earlier[ok]])
    return out


def wrist_to_trunk_distance(keypoints: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Distance of the nearer wrist to the middle of the trunk over the torso length: small when a hand is in front of
    the trunk. NaN without the four torso joints or a valid wrist."""
    centre = keypoints[:, list(_TORSO)].mean(axis=1)
    torso = _torso_length(keypoints, valid)
    best = np.full(keypoints.shape[0], np.nan)
    for name in ("LWrist", "RWrist"):
        j = IDX[name]
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.where(valid[:, j], np.linalg.norm(keypoints[:, j] - centre, axis=-1) / torso, np.nan)
        best = np.fmin(best, d)
    return best


def cadence_difference(
    keypoints: np.ndarray,
    valid: np.ndarray,
    other_keypoints: np.ndarray,
    other_valid: np.ndarray,
    ref_height: float | np.ndarray,
) -> np.ndarray:
    """The largest distance, over the joints valid in both, between the target's keypoints of two runs of the same
    frames (N = 1 and N = 5), in median body heights; NaN where a run has no target or the runs share no joint. Its
    worst frames are where the cadence changes the pose most (a limb cut by a box taken from the previous keypoints)."""
    ref = np.broadcast_to(np.asarray(ref_height, dtype=np.float64), (keypoints.shape[0],))  # one per frame, or one
    usable = ref > 0.0
    both = valid & other_valid & usable[:, None]
    scale = np.where(usable, ref, 1.0)[:, None]
    distance = np.where(both, np.linalg.norm(keypoints - other_keypoints, axis=-1) / scale, np.nan)
    return _nanmax(distance, axis=1)


def compute_signals(
    keypoints: np.ndarray, scores: np.ndarray, t_sec: np.ndarray, tracked: np.ndarray, tau: float = TAU_KP
) -> dict[str, np.ndarray]:
    """All the measures of a clip's target track, by name (arrays of length F), and ``ref_height`` as a 0-d array."""
    valid = valid_joints(keypoints, scores, tau) & tracked[:, None]
    height = body_height(keypoints, valid)
    ref = reference_height(height)
    ratio = shoulder_width_ratio(keypoints, valid)
    return {
        "ref_height": np.asarray(ref),
        "valid": valid,
        "low_essential": low_essential(valid),
        "structure": structure_failures(keypoints, scores, tracked, tau),
        "jump": jump_speed(keypoints, valid, t_sec, ref),
        "bone": bone_deviation(keypoints, valid),
        "swap_pair": swap_margin(keypoints, valid, ref),
        "find_back": np.where(tracked, face_vs_body_score(scores), np.nan),
        "find_one_leg": ankle_height_difference(keypoints, valid, ref),
        "find_rotation": rotation_rate(ratio, t_sec),
        "find_occlusion": wrist_to_trunk_distance(keypoints, valid),
        "shoulder_ratio": ratio,
    }


# The eleven rules of the review and the direction of each: ``True`` means that a higher value is the worse one (the
# frame to look at); ``find_occlusion`` is the one where a low value (a wrist near the middle of the trunk) points at
# the frame. ``target_event`` and ``cadence_diff`` are not made by ``compute_signals`` (they need the events of the
# track, or the two runs).
RULE_HIGHER_IS_WORSE: Final[dict[str, bool]] = {
    "low_essential": True,
    "structure": True,
    "jump": True,
    "bone": True,
    "swap_pair": True,
    "target_event": True,
    "find_back": True,
    "find_one_leg": True,
    "find_rotation": True,
    "find_occlusion": False,
    "cadence_diff": True,
}
