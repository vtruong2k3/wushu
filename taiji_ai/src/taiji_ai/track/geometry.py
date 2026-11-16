"""Boxes and overlaps shared by the target choice (P3.04) and the association of persons (P3.05).

Boxes are ``(x0, y0, x1, y1)`` in image pixels, x to the right, y down. A box is *usable* when its values are finite and
its area is positive. The hull of a person is the box of its valid keypoints (see ``valid_keypoint_mask``): unlike the
box the detector stored, it does not change with the detector cadence.
"""

from __future__ import annotations

import numpy as np


def usable_boxes(boxes: np.ndarray) -> np.ndarray:
    """Which boxes (``(..., 4)``) are finite and have a positive area."""
    return np.isfinite(boxes).all(axis=-1) & (boxes[..., 2] > boxes[..., 0]) & (boxes[..., 3] > boxes[..., 1])


def keypoint_hull(keypoints: np.ndarray, valid: np.ndarray) -> np.ndarray | None:
    """The box of the valid keypoints (``(26, 2)``, ``(26,)`` bool), or ``None`` when it has no area."""
    points = np.asarray(keypoints, dtype=np.float64)[valid]
    if points.shape[0] < 2:
        return None
    x0, y0 = points.min(axis=0)
    x1, y1 = points.max(axis=0)
    if not (x1 > x0 and y1 > y0):
        return None
    return np.array([x0, y0, x1, y1], dtype=np.float64)


def iou_to_box(boxes: np.ndarray, box: np.ndarray) -> np.ndarray:
    """IoU of every row of ``boxes`` (``(m, 4)``) with ``box``; an unusable row gets 0."""
    b = np.asarray(boxes, dtype=np.float64)
    ok = usable_boxes(b)
    ix = np.clip(np.minimum(b[:, 2], box[2]) - np.maximum(b[:, 0], box[0]), 0.0, None)
    iy = np.clip(np.minimum(b[:, 3], box[3]) - np.maximum(b[:, 1], box[1]), 0.0, None)
    inter = np.where(ok, ix * iy, 0.0)
    union = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) + (box[2] - box[0]) * (box[3] - box[1]) - inter
    return np.where(ok & (union > 0), inter / np.where(union > 0, union, 1.0), 0.0)


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """IoU of two usable boxes."""
    return float(iou_to_box(np.asarray(a, dtype=np.float64)[None, :], np.asarray(b, dtype=np.float64))[0])
