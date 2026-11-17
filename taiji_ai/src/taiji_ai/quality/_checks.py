"""What the stages of the quality layer have in common (package-private): the number checks, read-only arrays and the
one contract of a layer that goes in.

A layer is ``keypoints`` ``(T, 26, 2)`` float, ``reason`` ``(T, 26)`` uint8 (the codes of ``quality/mask.py``) and
``t_sec`` ``(T,)`` float seconds. The contract: the times are finite and strictly increasing (real PTS, one row per
frame), and a cell is NaN **exactly** where its reason is not ``ok``: a NaN without a reason and a value with a reason
are both refused (every hole has a cause, AGENTS.md section 5.1). ``interpolate_gaps`` (P4.02) and ``hampel_outliers``
(P4.03) read a layer under it.
"""

from __future__ import annotations

import numbers
from typing import Any

import numpy as np

from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality.mask import OK


def is_real(value: Any) -> bool:
    """A real number that is not a bool (a bool is an int in Python and never a quantity here)."""
    return isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_))


def is_int(value: Any) -> bool:
    """A whole number that is not a bool."""
    return isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))


def frozen(a: np.ndarray) -> np.ndarray:
    """The array, made read-only."""
    a.setflags(write=False)
    return a


def check_layer(keypoints: Any, reason: Any, t_sec: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The arrays of a layer as arrays, or a ``QualityError`` that names the argument and what is wrong with it."""
    kp = np.asarray(keypoints)
    if kp.dtype.kind != "f":
        raise QualityError(
            f"keypoints must be a floating-point array (an integer array cannot hold NaN), got {kp.dtype}"
        )
    if kp.ndim != 3 or kp.shape[1:] != (NUM_JOINTS, 2):
        raise QualityError(f"keypoints must have shape (T, {NUM_JOINTS}, 2), got {kp.shape}")
    n = kp.shape[0]
    rs = np.asarray(reason)
    if rs.dtype != np.uint8:
        raise QualityError(f"reason must be a uint8 array of reason codes, got {rs.dtype}")
    if rs.shape != (n, NUM_JOINTS):
        raise QualityError(f"reason must have shape ({n}, {NUM_JOINTS}) like keypoints, got {rs.shape}")
    t = np.asarray(t_sec)
    if t.dtype.kind != "f":
        raise QualityError(f"t_sec must be a floating-point array of seconds, got {t.dtype}")
    if t.shape != (n,):
        raise QualityError(f"t_sec must have shape ({n},) like keypoints, got {t.shape}")
    if not np.isfinite(t).all():
        raise QualityError("t_sec must be finite: a frame without a timestamp cannot be placed in time")
    if n > 1 and not (np.diff(t) > 0.0).all():
        raise QualityError("t_sec must be strictly increasing (real PTS, one row per frame)")
    seen = rs == OK
    bad = seen & ~np.isfinite(kp).all(axis=-1)
    if bad.any():
        frame, joint = np.argwhere(bad)[0]
        raise QualityError(
            f"keypoints has NaN or infinite values where reason is ok (first: frame {frame}, joint {joint})"
        )
    bad = ~seen & ~np.isnan(kp).all(axis=-1)
    if bad.any():
        frame, joint = np.argwhere(bad)[0]
        raise QualityError(
            f"keypoints has a finite or infinite value where reason is not ok (first: frame {frame}, joint {joint}): "
            "a cell that is not observed must be NaN"
        )
    return kp, rs, t
