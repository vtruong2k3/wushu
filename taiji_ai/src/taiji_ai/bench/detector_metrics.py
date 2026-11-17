"""Metrics and the written rule of the detector comparison (P3.09); pure numpy, no I/O, no model.

A is the shipping detector (YOLOX of rtmlib), B the candidate (YOLO11). Boxes are ``(x1, y1, x2, y2)`` image pixels
with y down; a detection is ``(x1, y1, x2, y2, score)``. Times are real seconds (``t_sec`` of the pts table), never
frame counts.

* ``reference_box``: the box of the performer taken from a skeleton that a person has confirmed (the hull of the
  joints with a score of 0.3 or more, grown by a margin); ``finds`` says whether a detector's boxes cover it (IoU at
  or above a limit).
* ``recall_paired`` / ``mcnemar_exact``: the two detectors on the same frames, and the exact two-sided test of the
  frames where only one of them finds the performer.
* ``stability``: how the performer's box moves from frame to frame; ``dropout_runs``: how long, in seconds, one
  detector loses the performer while the other still has them.
* ``decide``: the rule written **before** any measurement (DEC-0043), applied as written.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

_EPS = 1e-12


def box_iou(a: Sequence[float] | np.ndarray, b: Sequence[float] | np.ndarray) -> float:
    """IoU of two boxes; a box without area (or boxes that only touch) has IoU 0, never a division by zero."""
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    area_a, area_b = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1), max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    w, h = min(ax2, bx2) - max(ax1, bx1), min(ay2, by2) - max(ay1, by1)
    inter = max(0.0, w) * max(0.0, h)
    union = area_a + area_b - inter
    return inter / union if union > 0.0 and inter > 0.0 else 0.0


def reference_box(
    keypoints: np.ndarray,
    scores: np.ndarray,
    min_score: float = 0.3,
    margin: float = 0.05,
    min_joints: int = 4,
) -> tuple[float, float, float, float] | None:
    """The hull of the joints with a finite score of at least ``min_score``, grown by ``margin`` of its size on each
    side.

    ``None`` when fewer than ``min_joints`` joints are usable or the hull has no width or no height.
    """
    kp = np.asarray(keypoints, dtype=np.float64)
    sc = np.asarray(scores, dtype=np.float64)
    valid = np.isfinite(kp).all(axis=1) & np.isfinite(sc) & (sc >= min_score)
    if int(valid.sum()) < min_joints:
        return None
    x0, y0 = kp[valid].min(axis=0)
    x1, y1 = kp[valid].max(axis=0)
    w, h = x1 - x0, y1 - y0
    if not (w > 0.0 and h > 0.0):
        return None
    return (float(x0 - margin * w), float(y0 - margin * h), float(x1 + margin * w), float(y1 + margin * h))


def finds(detections: np.ndarray, reference: Sequence[float] | None, iou_min: float = 0.5) -> bool:
    """One of the detections has IoU of at least ``iou_min`` with the reference box (equal counts); no reference,
    no find."""
    if reference is None:
        return False
    return any(box_iou(d[:4], reference) >= iou_min for d in np.asarray(detections).reshape(-1, 5)[:, :4])


def performer_box(detections: np.ndarray, image_height: float, min_height_frac: float = 0.2) -> np.ndarray | None:
    """The largest detection (by area) whose height is at least ``min_height_frac`` of the image height, or ``None``."""
    rows = np.asarray(detections, dtype=np.float64).reshape(-1, 5)
    if len(rows) == 0:
        return None
    heights = rows[:, 3] - rows[:, 1]
    areas = np.maximum(0.0, rows[:, 2] - rows[:, 0]) * np.maximum(0.0, heights)
    eligible = np.flatnonzero(heights >= min_height_frac * image_height - _EPS)
    if len(eligible) == 0:
        return None
    return rows[eligible[int(np.argmax(areas[eligible]))], :4].copy()


def _spread(values: Sequence[float]) -> dict[str, float] | None:
    if len(values) == 0:
        return None
    v = np.asarray(values, dtype=np.float64)
    return {
        "p50": float(np.percentile(v, 50)),
        "p95": float(np.percentile(v, 95)),
        "p99": float(np.percentile(v, 99)),
        "max": float(v.max()),
    }


def stability(boxes: Sequence[np.ndarray | None], t_sec: Sequence[float] | np.ndarray) -> dict[str, Any]:
    """How the box of the performer moves: ``1 - IoU`` of consecutive frames (both with a box; nothing is paired
    across a missing frame), the pairs with IoU under 0.5 (jumps), and the change of the height against the median
    of the (up to four) neighbours within two frames. ``None`` instead of a spread when there is nothing to
    measure."""
    if len(boxes) != len(t_sec):
        raise ValueError("boxes and t_sec must have the same length")
    d: list[float] = []
    jumps = 0
    for a, b in zip(boxes[:-1], boxes[1:], strict=True):
        if a is None or b is None:
            continue
        iou = box_iou(a, b)
        d.append(1.0 - iou)
        jumps += int(iou < 0.5)
    heights = [None if b is None else float(b[3] - b[1]) for b in boxes]
    change: list[float] = []
    for i, h in enumerate(heights):
        if h is None:
            continue
        near = [heights[j] for j in range(max(0, i - 2), min(len(heights), i + 3)) if j != i and heights[j] is not None]
        if len(near) < 2:
            continue
        median = float(np.median(near))  # type: ignore[arg-type]
        if median > 0.0:
            change.append(abs(h - median) / median)
    return {
        "frames": len(boxes),
        "frames_with_box": sum(b is not None for b in boxes),
        "pairs": len(d),
        "jumps": jumps,
        "one_minus_iou": _spread(d),
        "height_change": _spread(change),
    }


def dropout_runs(
    own_found: Sequence[bool] | np.ndarray,
    other_found: Sequence[bool] | np.ndarray,
    t_sec: Sequence[float] | np.ndarray,
) -> list[float]:
    """Durations in seconds of the runs of frames where the other detector finds the performer and this one does not.

    A run lasts from the time of its first frame to the time of the first frame after it (to one median frame interval
    after its last frame at the end of the clip): the clock decides, not the number of frames.
    """
    own, other, t = np.asarray(own_found, bool), np.asarray(other_found, bool), np.asarray(t_sec, dtype=np.float64)
    if not (len(own) == len(other) == len(t)):
        raise ValueError("own_found, other_found and t_sec must have the same length")
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.0
    missing = other & ~own
    runs: list[float] = []
    i = 0
    while i < len(missing):
        if not missing[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(missing) and missing[j + 1]:
            j += 1
        end = float(t[j + 1]) if j + 1 < len(t) else float(t[j]) + dt
        runs.append(end - float(t[i]))
        i = j + 1
    return runs


def recall_paired(found_a: Sequence[bool] | np.ndarray, found_b: Sequence[bool] | np.ndarray) -> dict[str, Any]:
    """Counts of the two detectors on the same frames: both find, only A, only B, neither; and each recall (``None``
    if empty)."""
    a, b = np.asarray(found_a, bool), np.asarray(found_b, bool)
    if len(a) != len(b):
        raise ValueError("found_a and found_b must have the same length")
    n = len(a)
    return {
        "n": n,
        "both": int((a & b).sum()),
        "only_a": int((a & ~b).sum()),
        "only_b": int((~a & b).sum()),
        "neither": int((~a & ~b).sum()),
        "recall_a": float(a.sum()) / n if n else None,
        "recall_b": float(b.sum()) / n if n else None,
    }


def agreement(found_a: Sequence[bool], found_b: Sequence[bool]) -> dict[str, Any]:
    """The same counts for frames of the clips (no ground truth): both, only A, only B, neither."""
    return recall_paired(found_a, found_b)


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar p of ``b`` and ``c`` discordant pairs (a binomial test of b against b + c at 1/2)."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


@dataclass(frozen=True)
class DetectorRule:
    """The values of the rule of DEC-0043, fixed before any measurement."""

    min_recall_gain_points: float = 3.0  # (R) B's recall over A's, in percentage points, at least
    max_p: float = 0.05  # (R) the exact McNemar two-sided p must be under this
    min_frame_gain: int = 5  # (C) frames where B is right and A wrong, minus the reverse, at least
    stability_ratio: float = 0.7  # B's p95 of 1 - IoU at most this times A's (a supporting reason only)
    min_positives: int = 20  # (R) fewer positive frames cannot be evaluated
    matched_score_limit: float = 0.3  # the score limit of both detectors in the comparison (rtmlib's for YOLOX)
    # The NMS limit given to YOLO11: the IoU of the NonMaxSuppression node inside the shipping YOLOX graph (read from
    # the file in P3.09, DEC-0043; rtmlib's constructor value 0.45 is not used for this file).
    matched_nms_iou: float = 0.65


@dataclass(frozen=True)
class PairedRecall:
    """Set R: the paired outcome on the labelled frames that have a person."""

    n_positive: int
    both: int
    only_a: int
    only_b: int

    @property
    def a_found(self) -> int:
        return self.both + self.only_a

    @property
    def b_found(self) -> int:
        return self.both + self.only_b


@dataclass(frozen=True)
class CReview:
    """Set C: the frames where only one detector finds a person, and what the review of them says."""

    n_discordant: int
    n_reviewed: int
    b_better: int  # B right and A wrong
    a_better: int  # A right and B wrong


@dataclass(frozen=True)
class Decision:
    outcome: str  # "materially_better" | "not_materially_better" | "no_decision"
    criterion: str | None  # "R", "C" or "R and C" when materially better
    reasons: list[str] = field(default_factory=list)


def decide(
    rule: DetectorRule,
    recall: PairedRecall,
    review: CReview | None,
    stability: tuple[float | None, float | None],
) -> Decision:
    """Apply the rule as written. ``stability`` is ``(p95 of 1 - IoU of A, the same of B)``; speed and memory are not
    inputs.

    B is *materially better* if (R) or (C) is met; if neither is met and both could be evaluated, A stays; if one
    could not be evaluated and the other is not met, there is no decision from this measurement (never silently
    "no gap"). Stability never decides: it is listed as a supporting reason when B's p95 is at most
    ``stability_ratio`` times A's and B finds at least as many performers as A, and as a note otherwise.
    """
    reasons: list[str] = []
    n = recall.n_positive
    eval_r = n >= rule.min_positives
    met_r = False
    if eval_r:
        gain = 100.0 * (recall.b_found - recall.a_found) / n
        p = mcnemar_exact(recall.only_b, recall.only_a)
        met_r = (recall.b_found - recall.a_found) * 100 >= rule.min_recall_gain_points * n and p < rule.max_p
        reasons.append(
            f"R: recall A {100.0 * recall.a_found / n:.1f} %, B {100.0 * recall.b_found / n:.1f} % on {n} frames, gain "
            f"{gain:.1f} points (needs {rule.min_recall_gain_points:g}), exact McNemar p {p:.3f} (needs under "
            f"{rule.max_p:g}): {'met' if met_r else 'not met'}"
        )
    else:
        reasons.append(f"R not evaluated: fewer than {rule.min_positives} positive frames ({n})")

    eval_c = review is not None and (review.n_discordant == 0 or review.n_reviewed > 0)
    met_c = False
    if review is not None and eval_c:
        diff = review.b_better - review.a_better
        met_c = diff >= rule.min_frame_gain
        reasons.append(
            f"C: reviewed {review.n_reviewed} of {review.n_discordant} runs (stretches where only one detector finds "
            f"a person): B right in {review.b_better}, A right in {review.a_better}, difference {diff} "
            f"(needs {rule.min_frame_gain}): {'met' if met_c else 'not met'}"
        )
    else:
        reasons.append("C not evaluated: the runs where the detectors disagree were not reviewed")

    p95_a, p95_b = stability
    if p95_a is not None and p95_b is not None and p95_a > 0.0:
        ratio = p95_b / p95_a
        no_loss = recall.b_found >= recall.a_found
        if ratio <= rule.stability_ratio + _EPS and no_loss:
            reasons.append(
                f"stability supports a gap but never decides alone: p95 of 1 - IoU A {p95_a:.3f}, B {p95_b:.3f} "
                f"(B at {ratio:.2f} of A, needs {rule.stability_ratio:g} or less)"
            )
        else:
            why = "B finds fewer performers" if not no_loss else f"B at {ratio:.2f} of A, over {rule.stability_ratio:g}"
            reasons.append(f"stability noted only: p95 of 1 - IoU A {p95_a:.3f}, B {p95_b:.3f} ({why})")

    if met_r or met_c:
        criterion = "R and C" if met_r and met_c else ("R" if met_r else "C")
        return Decision("materially_better", criterion, reasons)
    if eval_r and eval_c:
        return Decision("not_materially_better", None, reasons)
    return Decision("no_decision", None, reasons)
