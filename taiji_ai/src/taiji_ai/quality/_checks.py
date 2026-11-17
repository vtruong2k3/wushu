"""What the stages of the quality layer have in common (package-private): the number checks, read-only arrays and the
one contract of a layer that goes in.

A layer is ``keypoints`` ``(T, 26, 2)`` float, ``reason`` ``(T, 26)`` uint8 (the codes of ``quality/mask.py``) and
``t_sec`` ``(T,)`` float seconds. The contract: the times are finite and strictly increasing (real PTS, one row per
frame), and a cell is NaN **exactly** where its reason is not ``ok``: a NaN without a reason and a value with a reason
are both refused (every hole has a cause, AGENTS.md section 5.1). ``interpolate_gaps`` (P4.02) and ``hampel_outliers``
(P4.03) read a layer under it. The **gap layer** that ``interpolate_gaps`` returns has a second contract
(``check_gap_layer``, read by ``resample_layer``, P4.04): a bridged cell has a value, a reason that is not ``ok`` and
the flag ``interpolated``.
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


def _check_shapes(keypoints: Any, reason: Any) -> tuple[np.ndarray, np.ndarray, int]:
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
    return kp, rs, n


def check_times(t_sec: Any, n: int) -> np.ndarray:
    t = np.asarray(t_sec)
    if t.dtype.kind != "f":
        raise QualityError(f"t_sec must be a floating-point array of seconds, got {t.dtype}")
    if t.shape != (n,):
        raise QualityError(f"t_sec must have shape ({n},) like keypoints, got {t.shape}")
    if not np.isfinite(t).all():
        raise QualityError("t_sec must be finite: a frame without a timestamp cannot be placed in time")
    if n > 1 and not (np.diff(t) > 0.0).all():
        raise QualityError("t_sec must be strictly increasing (real PTS, one row per frame)")
    return t


def check_layer(keypoints: Any, reason: Any, t_sec: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The arrays of a layer as arrays, or a ``QualityError`` that names the argument and what is wrong with it."""
    kp, rs, n = _check_shapes(keypoints, reason)
    t = check_times(t_sec, n)
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


def _first(bad: np.ndarray) -> tuple[int, int]:
    frame, joint = np.argwhere(bad)[0]
    return int(frame), int(joint)


def check_gap_layer(
    keypoints: Any, reason: Any, interpolated: Any, t_sec: Any
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The arrays of a **gap layer** (the result of ``interpolate_gaps``) as arrays, or a ``QualityError``.

    Same arrays as ``check_layer`` plus ``interpolated`` ``(T, 26)`` bool. The contract: a cell is observed (both
    coordinates finite and ``reason == ok``), bridged (both finite, a reason that is not ``ok`` and ``interpolated``) or
    not usable (both NaN, a reason that is not ``ok``, not ``interpolated``). So a value that is not ``ok`` must say
    that it was made up, and a NaN must say why it is missing (AGENTS.md section 5.1). ``resample_layer`` reads such a
    layer and returns one.
    """
    kp, rs, n = _check_shapes(keypoints, reason)
    flag = np.asarray(interpolated)
    if flag.dtype != np.bool_:
        raise QualityError(f"interpolated must be a bool array of flags, got {flag.dtype}")
    if flag.shape != (n, NUM_JOINTS):
        raise QualityError(f"interpolated must have shape ({n}, {NUM_JOINTS}) like keypoints, got {flag.shape}")
    t = check_times(t_sec, n)
    if np.isinf(kp).any():
        frame, joint = _first(np.isinf(kp).any(axis=-1))
        raise QualityError(f"keypoints has infinite values (first: frame {frame}, joint {joint})")
    nan = np.isnan(kp)
    half = nan.any(axis=-1) & ~nan.all(axis=-1)
    if half.any():
        frame, joint = _first(half)
        raise QualityError(
            f"keypoints has a cell with one NaN coordinate and one finite coordinate (first: frame {frame}, joint "
            f"{joint}): a cell has a position or it has none"
        )
    has_value = ~nan.all(axis=-1)
    seen = rs == OK
    checks = (
        (seen & ~has_value, "keypoints has NaN values where reason is ok"),
        (has_value & ~seen & ~flag, "keypoints has a value where reason is not ok that is not flagged interpolated"),
        (flag & ~has_value, "interpolated is set on a cell that has no value"),
        (flag & seen, "interpolated is set on a cell whose reason is ok"),
    )
    for bad, message in checks:
        if bad.any():
            frame, joint = _first(bad)
            raise QualityError(f"{message} (first: frame {frame}, joint {joint})")
    return kp, rs, flag, t
