"""An independent re-derivation of the frame features (P6.01, Appendix C.1) for the tests of ``compare/features.py``.

Plain loops, ``math.atan2`` and ``statistics.median`` on the arrays of a layer, never the module's own helpers or
tables: a position is ``(p_j - H) / Λ`` in trunk lengths, an angle is ``(sin φ, cos φ)`` with
``φ = atan2(dx, -dy)`` (0 is up, positive toward the image right, y down), ``H`` is the middle of the hips and ``Λ`` the
median trunk length of the rows of the segment (never per frame). The table of segments is written here again **by joint
number** (5 LShoulder, 6 RShoulder, 7 LElbow, 8 RElbow, 9 LWrist, 10 RWrist, 11 LHip, 12 RHip, 13 LKnee, 14 RKnee,
15 LAnkle, 16 RAnkle).
"""

from __future__ import annotations

import math
import statistics

import numpy as np

from taiji_ai.pose.skeleton import IDX
from taiji_ai.quality.layers_io import PoseFiltered

HIPS = (11, 12)
SHOULDERS = (5, 6)
# the joints whose mean is the proximal end and the joints whose mean is the distal end of each segment
TABLE: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "l_upper_arm": ((5,), (7,)),
    "l_forearm": ((7,), (9,)),
    "r_upper_arm": ((6,), (8,)),
    "r_forearm": ((8,), (10,)),
    "l_thigh": ((11,), (13,)),
    "l_shank": ((13,), (15,)),
    "r_thigh": ((12,), (14,)),
    "r_shank": ((14,), (16,)),
    "trunk": ((11, 12), (5, 6)),
}
JOINTS12 = (
    "LShoulder", "RShoulder", "LElbow", "RElbow", "LWrist", "RWrist",
    "LHip", "RHip", "LKnee", "RKnee", "LAnkle", "RAnkle",
)  # fmt: skip
SEGMENTS9 = tuple(TABLE)
NAN = float("nan")


def segment_rows_of(layer: PoseFiltered) -> list[int]:
    return [g for g in range(len(layer.t_grid)) if layer.grid_in_segment[g]]


def point(layer: PoseFiltered, g: int, j: int) -> tuple[float, float]:
    return float(layer.keypoints[g, j, 0]), float(layer.keypoints[g, j, 1])


def mean_of(points: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def rotate(p: tuple[float, float], roll_deg: float) -> tuple[float, float]:
    """The point in the frame where the plumb line is vertical: the rotation by ``-roll`` (image coordinates)."""
    a = math.radians(roll_deg)
    return p[0] * math.cos(a) + p[1] * math.sin(a), -p[0] * math.sin(a) + p[1] * math.cos(a)


def trunk_scale_of(layer: PoseFiltered, rows: list[int] | None = None) -> float:
    """The median of the finite trunk lengths above 0 over the rows (default: the segment), on the raw points."""
    lengths = []
    for g in segment_rows_of(layer) if rows is None else rows:
        h = mean_of([point(layer, g, j) for j in HIPS])
        s = mean_of([point(layer, g, j) for j in SHOULDERS])
        length = math.hypot(s[0] - h[0], s[1] - h[1])
        if math.isfinite(length) and length > 0.0:
            lengths.append(length)
    return statistics.median(lengths) if lengths else NAN


def _ends(pts: list[tuple[float, float]], name: str) -> tuple[tuple[float, float], tuple[float, float]]:
    proximal, distal = TABLE[name]
    return mean_of([pts[j] for j in proximal]), mean_of([pts[j] for j in distal])


def length_ratios(layer: PoseFiltered, *, roll: float = 0.0, segments: tuple[str, ...] = SEGMENTS9) -> np.ndarray:
    """``(N, S)`` the length of each segment in trunk lengths, ``hypot(dx, dy) / Λ``; NaN where an end or Λ is NaN."""
    rows = segment_rows_of(layer)
    lam = trunk_scale_of(layer)
    out = np.full((len(rows), len(segments)), np.nan)
    for r, g in enumerate(rows):
        pts = [rotate(point(layer, g, j), roll) for j in range(26)]
        for v, name in enumerate(segments):
            a, b = _ends(pts, name)
            out[r, v] = math.hypot(b[0] - a[0], b[1] - a[1]) / lam
    return out


def expected_features(
    layer: PoseFiltered,
    *,
    roll: float = 0.0,
    joints: tuple[str, ...] = JOINTS12,
    segments: tuple[str, ...] = SEGMENTS9,
    min_segment_length: float | None = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    """``(values (N, U, 2), valid (N, U), Λ)`` of the rows of the segment, by plain loops; NaN where not computable.

    An angle is a value when its ends have values, its length is not exactly 0 and, when ``min_segment_length`` (in
    trunk lengths) is given, ``Λ`` is finite and ``length / Λ`` is not below it (equal is enough).
    """
    rows = segment_rows_of(layer)
    lam = trunk_scale_of(layer)
    n_units = len(joints) + len(segments)
    values = np.full((len(rows), n_units, 2), np.nan)
    valid = np.zeros((len(rows), n_units), dtype=bool)
    for r, g in enumerate(rows):
        pts = [rotate(point(layer, g, j), roll) for j in range(26)]
        hip = mean_of([pts[j] for j in HIPS])
        for u, name in enumerate(joints):
            p = pts[IDX[name]]
            if all(math.isfinite(v) for v in (*p, *hip)) and math.isfinite(lam):
                values[r, u] = ((p[0] - hip[0]) / lam, (p[1] - hip[1]) / lam)
                valid[r, u] = True
        for v, name in enumerate(segments):
            a, b = _ends(pts, name)
            dx, dy = b[0] - a[0], b[1] - a[1]
            if not all(math.isfinite(c) for c in (dx, dy)) or (dx == 0.0 and dy == 0.0):
                continue
            if min_segment_length is not None and not (
                math.isfinite(lam) and math.hypot(dx, dy) / lam >= min_segment_length
            ):
                continue
            phi = math.atan2(dx, -dy)
            values[r, len(joints) + v] = (math.sin(phi), math.cos(phi))
            valid[r, len(joints) + v] = True
    return values, valid, lam


def expected_reasons(
    layer: PoseFiltered,
    *,
    roll: float = 0.0,
    joints: tuple[str, ...] = JOINTS12,
    segments: tuple[str, ...] = SEGMENTS9,
    min_segment_length: float | None = None,
) -> np.ndarray:
    """``(N, U)`` uint8 the reason of every unit, by plain loops: the reason (1 to 6) of the layer at the first joint of
    the unit without a value (a position: its joint, then the hips; an angle: its ends in order), else 19 for a position
    without ``Λ``, else for an angle 23 (the ends coincide exactly), then 19 (a minimum but no ``Λ``) or 24
    (``length / Λ`` below the minimum); 0 for a value."""
    rows = segment_rows_of(layer)
    lam = trunk_scale_of(layer)
    out = np.zeros((len(rows), len(joints) + len(segments)), dtype=np.uint8)

    def first_missing(g: int, needed: list[int]) -> int:
        for j in needed:
            if any(math.isnan(c) for c in point(layer, g, j)):
                return int(layer.reason[g, j])
        return 0

    for r, g in enumerate(rows):
        pts = [rotate(point(layer, g, j), roll) for j in range(26)]
        for u, name in enumerate(joints):
            j = IDX[name]
            code = first_missing(g, [j, *[h for h in HIPS if h != j]])
            if code == 0 and not math.isfinite(lam):
                code = 19
            out[r, u] = code
        for v, name in enumerate(segments):
            proximal, distal = TABLE[name]
            code = first_missing(g, [*proximal, *distal])
            if code == 0:
                a, b = _ends(pts, name)
                dx, dy = b[0] - a[0], b[1] - a[1]
                if dx == 0.0 and dy == 0.0:
                    code = 23
                elif min_segment_length is not None:
                    if not math.isfinite(lam):
                        code = 19
                    elif math.hypot(dx, dy) / lam < min_segment_length:
                        code = 24
            out[r, len(joints) + v] = code
    return out
