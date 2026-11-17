"""Small layers for the P4.07 tests: a person who does not move, and fixture F1 with every class of cell.

``static_pose`` is a pose with a known torso (150 px) in which every left/right pair is 100 px apart, so a swap is a
jump far over the thresholds of the swap flag and of Hampel. ``build_f1`` puts a known defect of every kind into 60 rows
(see its docstring); ``tests/unit/test_quality_coverage.py`` counts the result by hand.
"""

from __future__ import annotations

import numpy as np

from taiji_ai.pose.skeleton import IDX, LR_PAIRS, NUM_JOINTS

FPS = 30.0
PAIR_JOINTS = frozenset(j for pair in LR_PAIRS for j in pair)
NOSE, LWRIST, RWRIST, LANKLE = IDX["Nose"], IDX["LWrist"], IDX["RWrist"], IDX["LAnkle"]
N1 = 60


def static_pose(n: int, dtype=np.float32) -> np.ndarray:
    """A person who does not move: left joints at x = 400, right at 500, the rest at 450; y = 50 + 25 j.

    The torso (middle of the shoulders to the middle of the hips) is exactly 150 px; every left/right pair is 100 px
    apart.
    """
    x = np.full(NUM_JOINTS, 450.0)
    for left, right in LR_PAIRS:
        x[left], x[right] = 400.0, 500.0
    y = 50.0 + 25.0 * np.arange(NUM_JOINTS)
    pose = np.stack([x, y], axis=-1).astype(dtype)
    return np.broadcast_to(pose, (n, NUM_JOINTS, 2)).copy()


def clean(n: int = 30):
    """``t_sec`` at 30 fps, a static pose and scores of 0.95 for ``n`` rows."""
    return np.arange(n) / FPS, static_pose(n), np.full((n, NUM_JOINTS), 0.95, dtype=np.float32)


def build_f1():
    """``(t, keypoints, scores, tracked, in_segment)`` of F1: 60 rows at 30 fps, a segment of 54 rows.

    rows 0 to 4 and 45 and 46: not the target's (``not_tracked``); rows 0 to 2 and 57 to 59 are margins (not in the
    segment); row 8: Nose 80 px off (an outlier); rows 10 and 11: LWrist score 0.1; row 12: RWrist NaN
    (``non_finite``); row 15: six essential joints at score 0.1, so the frame is ``frame_invalid``; rows 20 to 29:
    LAnkle score 0.1 (a hole of 10 rows); rows 34 and 35: every left/right pair swapped.
    """
    t, kp, score = clean(N1)
    tracked = np.ones(N1, dtype=bool)
    tracked[0:5] = False
    tracked[45:47] = False
    in_segment = np.ones(N1, dtype=bool)
    in_segment[:3] = False
    in_segment[57:] = False
    kp[8, NOSE, 1] += 80.0
    score[10:12, LWRIST] = 0.1
    kp[12, RWRIST] = np.nan
    score[15, [5, 6, 11, 12, 13, 14]] = 0.1
    score[20:30, LANKLE] = 0.1
    for a, b in LR_PAIRS:
        kp[34:36, [a, b]] = kp[34:36, [b, a]]
    return t, kp, score, tracked, in_segment
