"""Pictures for the review (P3.08): the skeleton on a crop of the person, and contact sheets.

A **tile** is a square picture of one frame: the crop around the person (all the skeletons given, with a margin), the
skeletons drawn on it (the left joints red, the right joints blue, the centre line green; a joint under the score
limit is a ring, not a disc; a second skeleton is drawn thinner and lighter), a bar with the caption. Keypoints that
are NaN are not drawn. The caption holds the candidate ID, the video label, the time and the rules only: never a file
name or a path.

The pictures hold frames of a video: they are written under ``data/reports/p3_08/`` (ignored by git) and never
committed.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from taiji_ai.pose.skeleton import EDGES, JOINTS

LEFT = (60, 60, 255)  # BGR: red
RIGHT = (255, 120, 40)  # blue
CENTRE = (60, 200, 60)  # green
LEFT_LIGHT = (150, 150, 255)
RIGHT_LIGHT = (255, 200, 140)
CENTRE_LIGHT = (160, 230, 160)
BOX = (150, 150, 150)  # gray: the other persons
BACKGROUND = (40, 40, 40)
_SIDE = {name: ("L" if name.startswith("L") else "R" if name.startswith("R") else "C") for name in JOINTS}
_PALETTE = {"L": (LEFT, LEFT_LIGHT), "R": (RIGHT, RIGHT_LIGHT), "C": (CENTRE, CENTRE_LIGHT)}


def _edge_colour(a: int, b: int, light: bool) -> tuple[int, int, int]:
    sides = {_SIDE[JOINTS[a]], _SIDE[JOINTS[b]]}
    side = sides.pop() if len(sides) == 1 else "C"
    return _PALETTE[side][1 if light else 0]


def draw_skeleton(
    image: np.ndarray,
    keypoints: np.ndarray,
    scores: np.ndarray,
    *,
    tau: float = 0.3,
    thickness: int = 3,
    light: bool = False,
) -> None:
    """Draw one skeleton on ``image`` in place; NaN keypoints are skipped, a joint under ``tau`` is a ring."""
    finite = np.isfinite(keypoints).all(axis=-1)
    for a, b in EDGES:
        if finite[a] and finite[b]:
            cv2.line(
                image,
                tuple(int(v) for v in keypoints[a]),
                tuple(int(v) for v in keypoints[b]),
                _edge_colour(a, b, light),
                thickness,
            )
    for j in np.flatnonzero(finite):
        colour = _PALETTE[_SIDE[JOINTS[j]]][1 if light else 0]
        centre = (int(keypoints[j, 0]), int(keypoints[j, 1]))
        if np.isfinite(scores[j]) and scores[j] >= tau:
            cv2.circle(image, centre, thickness + 1, colour, -1)
        else:
            cv2.circle(image, centre, thickness + 2, colour, 1)


def person_crop(
    shape: tuple[int, int], skeletons: Sequence[np.ndarray], margin: float = 0.25, min_size: int = 96
) -> tuple[int, int, int, int] | None:
    """``(x0, y0, x1, y1)`` of a square-ish crop around every finite keypoint of ``skeletons``, widened by ``margin``
    of its size and clipped to an image of ``shape = (height, width)``; ``None`` when there is no finite keypoint."""
    points = [s[np.isfinite(s).all(axis=-1)] for s in skeletons]
    points = [p for p in points if p.size]
    if not points:
        return None
    all_points = np.concatenate(points)
    x0, y0 = all_points.min(axis=0)
    x1, y1 = all_points.max(axis=0)
    side = max(x1 - x0, y1 - y0, float(min_size)) * (1.0 + 2.0 * margin)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    height, width = shape
    left, top = int(max(0, round(cx - side / 2))), int(max(0, round(cy - side / 2)))
    right, bottom = int(min(width, round(cx + side / 2))), int(min(height, round(cy + side / 2)))
    if right - left < 2 or bottom - top < 2:
        return None
    return left, top, right, bottom


def caption_text(cid: str, video: str, t_sec: float, tags: Sequence[str]) -> str:
    return f"{cid}  {video}  {t_sec:.2f}s  {'+'.join(tags)}"


def tile(
    image: np.ndarray,
    skeletons: Sequence[tuple[np.ndarray, np.ndarray, bool]],
    caption: str,
    *,
    size: int = 380,
    tau: float = 0.3,
    boxes: Sequence[Sequence[float] | np.ndarray] = (),
) -> np.ndarray:
    """A ``size`` x ``size`` BGR tile of ``image``: the crop around the skeletons (``(keypoints, scores, light)``), the
    skeletons, the gray ``boxes`` of the other persons and a caption bar. With no finite keypoint the whole frame is
    shown."""
    height, width = image.shape[:2]
    crop = person_crop((height, width), [kp for kp, _, _ in skeletons]) or (0, 0, width, height)
    x0, y0, x1, y1 = crop
    scale = size / max(x1 - x0, y1 - y0)
    resized = cv2.resize(image[y0:y1, x0:x1], None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    canvas = np.full((size, size, 3), BACKGROUND, dtype=np.uint8)
    h, w = resized.shape[:2]
    oy, ox = (size - h) // 2, (size - w) // 2
    canvas[oy : oy + h, ox : ox + w] = resized[: size - oy, : size - ox]
    shift = np.array([ox - x0 * scale, oy - y0 * scale])
    for x_a, y_a, x_b, y_b in boxes:
        a, b = np.array([x_a, y_a]) * scale + shift, np.array([x_b, y_b]) * scale + shift
        cv2.rectangle(canvas, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), BOX, 1)
    for index, (kp, scores, light) in enumerate(skeletons):
        draw_skeleton(canvas, kp * scale + shift, scores, tau=tau, thickness=2 if light else 3, light=light)
        if index == 0 and not np.isfinite(kp).any():
            cv2.putText(
                canvas, "no skeleton for the target", (6, size - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1
            )
    cv2.rectangle(canvas, (0, 0), (size, 20), (0, 0, 0), -1)
    cv2.putText(canvas, caption, (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
    return canvas


def strip(tiles: Sequence[np.ndarray]) -> np.ndarray:
    """Tiles side by side (consecutive frames)."""
    return np.concatenate(list(tiles), axis=1)


def contact_sheet(tiles: Sequence[np.ndarray], columns: int = 4, pad: int = 4) -> np.ndarray:
    """A grid of tiles (rows of ``columns``); tiles may differ in size, each row is padded to the widest row."""
    rows = [list(tiles[i : i + columns]) for i in range(0, len(tiles), columns)]
    built = []
    for row in rows:
        height = max(t.shape[0] for t in row)
        parts = []
        for t in row:
            parts.append(np.pad(t, ((0, height - t.shape[0]), (0, pad), (0, 0)), constant_values=0))
        built.append(np.concatenate(parts, axis=1))
    width = max(r.shape[1] for r in built)
    padded = [np.pad(r, ((0, pad), (0, width - r.shape[1]), (0, 0)), constant_values=0) for r in built]
    return np.concatenate(padded, axis=0)
