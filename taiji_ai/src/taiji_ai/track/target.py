"""Choose the target person (the performer) on one frame of a segment (W5 step 1, P3.04).

``select_target`` looks at the persons of one frame of a ``PoseRaw`` and says which one is the performer, in a form the
tracking (P3.05) can start from and the UI (P8) can show, confirm or override. Nothing is tracked, nothing is written
and the raw layer is not modified.

**Default rule** (the largest box near the centre; the values are provisional, they are not universal thresholds):

1. Frame: the first frame at or after the segment start that has an eligible person, searched for up to
   ``TargetParams.search_s`` from the start (never before it). ``at_t_sec`` fixes the frame instead: no search.
2. Eligible: at least ``raw.params.min_valid_keypoints`` valid keypoints (the rule of the runner, so a ghost with a few
   keypoints is never chosen by default) and a box of positive area with finite values.
3. Score: ``area share x centrality`` with ``area share = box area / image area`` and
   ``centrality = 1 - min(1, d / (0.5 x image diagonal))``, ``d`` the distance of the box centre to the image centre.
   The highest score wins; equal scores: the lowest person row.
4. Ambiguity: ``runner_up_ratio = second score / best score``; ``ambiguous`` when it is at least
   ``TargetParams.ambiguity_ratio``: two people of similar size and place, the UI must ask. When every score is 0 and
   there are two candidates or more the choice is ``ambiguous`` and the ratio is ``None`` (no 0 / 0).

**User box**: the person whose box has the largest IoU with the given box on the frame, among all persons (also a weak
one: the user decides, ``weak`` says so), if that IoU is at least ``min_iou``; a box that overlaps two people about as
much (the best IoU under ``two_people_iou_ratio`` times the second, both at least ``min_iou``) is refused, and so is a
box that matches nobody: the nearest wrong person is never chosen.

Coordinates are image pixels (``raw.image_size`` is ``(width, height)``), x to the right, y down; times are seconds from
the stream start. An empty frame is an error, never a guess (AGENTS.md section 5.1).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from taiji_ai.pose.runner import PoseRaw, valid_keypoint_mask
from taiji_ai.track.geometry import iou_to_box, usable_boxes

log = logging.getLogger(__name__)

_EPS = 1e-9


class TargetSelectionError(Exception):
    """No person can be chosen: nobody eligible, no such frame, a box that matches nobody or two people."""


@dataclass(frozen=True)
class TargetParams:
    """Provisional values until P3.07 and P3.08 show real failures; each has its reason in the module docstring."""

    search_s: float = 2.0  # [s] how far after the segment start the automatic search looks for a person
    min_iou: float = 0.3  # a user box must overlap a person at least this much (IoU)
    ambiguity_ratio: float = 0.6  # second / best score from which the default choice is flagged ambiguous
    two_people_iou_ratio: float = 1.5  # a user box needs a best IoU at least this many times the second one

    def __post_init__(self) -> None:
        if not (math.isfinite(self.search_s) and self.search_s >= 0.0):
            raise ValueError(f"search_s must be a finite number >= 0, got {self.search_s!r}")
        if not 0.0 < self.min_iou <= 1.0:
            raise ValueError(f"min_iou must be in (0, 1], got {self.min_iou!r}")
        if not 0.0 < self.ambiguity_ratio <= 1.0:
            raise ValueError(f"ambiguity_ratio must be in (0, 1], got {self.ambiguity_ratio!r}")
        if not (math.isfinite(self.two_people_iou_ratio) and self.two_people_iou_ratio >= 1.0):
            raise ValueError(f"two_people_iou_ratio must be a finite number >= 1, got {self.two_people_iou_ratio!r}")


@dataclass(frozen=True)
class TargetSelection:
    """The person chosen as the performer."""

    frame_pos: int  # index into the frames of the ``PoseRaw``
    frame_index: int  # row of the frame in pts.parquet (the frame index of the file)
    t_sec: float  # [s] from the stream start
    offset_from_start_s: float  # [s] frame time minus the segment start (negative: a margin frame)
    person_row: int  # row in the person arrays of the ``PoseRaw``
    bbox: tuple[float, float, float, float]  # xyxy [px] of the chosen person
    method: Literal["default", "user_box"]
    score: float  # default: the score of the chosen person; user box: the IoU with the given box
    n_candidates: int  # default: eligible persons on the frame; user box: all persons on the frame
    ambiguous: bool  # default rule only: a close call, the UI must ask
    runner_up_ratio: float | None  # default rule: second score / best score; None for one candidate or a user box
    weak: bool  # the chosen person has fewer valid keypoints than ``raw.params.min_valid_keypoints``
    n_valid_keypoints: int  # of the chosen person


def _person_rows(raw: PoseRaw, pos: int) -> np.ndarray:
    return np.arange(int(raw.person_offsets[pos]), int(raw.person_offsets[pos + 1]))


def _n_valid(raw: PoseRaw, rows: np.ndarray) -> np.ndarray:
    return valid_keypoint_mask(raw.keypoints[rows], raw.scores[rows], raw.params.min_score).sum(axis=-1)


def _default_scores(raw: PoseRaw, rows: np.ndarray) -> np.ndarray:
    """``area share x centrality`` of the persons in ``rows`` (all with usable boxes)."""
    width, height = raw.image_size
    b = raw.bboxes[rows].astype(np.float64)
    area_share = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) / (width * height)
    centre = np.stack([(b[:, 0] + b[:, 2]) / 2.0, (b[:, 1] + b[:, 3]) / 2.0], axis=1)
    d = np.linalg.norm(centre - np.array([width / 2.0, height / 2.0]), axis=1)
    centrality = 1.0 - np.minimum(1.0, d / (0.5 * math.hypot(width, height)))
    return area_share * centrality


def _check_user_box(bbox: object) -> np.ndarray:
    try:
        box = np.asarray(bbox, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TargetSelectionError("the box must be four numbers (x0, y0, x1, y1)") from exc
    if box.shape != (4,) or not np.all(np.isfinite(box)):
        raise TargetSelectionError("the box must be four finite numbers (x0, y0, x1, y1)")
    if not (box[2] > box[0] and box[3] > box[1]):
        raise TargetSelectionError("the box has no area: it needs x1 > x0 and y1 > y0")
    return box


def _frame_of_time(raw: PoseRaw, at_t_sec: float) -> int:
    """The frame nearest to ``at_t_sec``, if it is within half a frame interval."""
    if not math.isfinite(at_t_sec):
        raise TargetSelectionError("at_t_sec must be a finite time")
    t = raw.t_sec
    pos = int(np.argmin(np.abs(t - at_t_sec)))
    half = 0.5 * float(np.median(np.diff(t))) if t.size >= 2 else 0.0
    if abs(float(t[pos]) - at_t_sec) > half + _EPS:
        raise TargetSelectionError(
            f"no frame near {at_t_sec:.3f} s (the nearest frame is at {float(t[pos]):.3f} s, "
            f"the frames run from {float(t[0]):.3f} to {float(t[-1]):.3f} s)"
        )
    return pos


def select_target(
    raw: PoseRaw,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    at_t_sec: float | None = None,
    params: TargetParams | None = None,
) -> TargetSelection:
    """Choose the performer in ``raw``; see the module docstring for the rules.

    Args:
        raw: the raw pose of the segment (``run_pose`` or ``load_pose_raw``).
        bbox: the box the user drew or clicked, ``(x0, y0, x1, y1)`` in image pixels; ``None`` for the default rule.
        at_t_sec: the time [s from the stream start] of the frame the user looked at; ``None``: the segment start.
        params: provisional parameters.

    Raises:
        TargetSelectionError: nobody eligible on the frame (or within ``search_s`` of the start), no such frame, a bad
            box, a box that matches nobody or covers two people. The target is never invented.
    """
    params = params or TargetParams()
    t = raw.t_sec
    start_s = float(raw.segment_s[0])
    after_start = np.flatnonzero(t >= start_s - _EPS)
    if after_start.size == 0:
        raise TargetSelectionError(f"no frame at or after the segment start ({start_s:.3f} s)")
    start_pos = int(after_start[0])
    user_box = _check_user_box(bbox) if bbox is not None else None
    fixed_pos = _frame_of_time(raw, at_t_sec) if at_t_sec is not None else None
    pos = fixed_pos if fixed_pos is not None else start_pos

    if user_box is not None:
        selection = _choose_by_box(raw, pos, user_box, params)
    else:
        selection = _choose_by_default(raw, pos, fixed_pos is not None, start_pos, params)
    log.info(
        "target for recording %s: frame %d (%s), method %s, ambiguous %s",
        raw.recording_id,
        selection.frame_index,
        f"{selection.offset_from_start_s:+.2f} s from the start",
        selection.method,
        selection.ambiguous,
    )
    return selection


def _build(raw: PoseRaw, pos: int, row: int, **fields) -> TargetSelection:
    n_valid = int(_n_valid(raw, np.array([row]))[0])
    return TargetSelection(
        frame_pos=pos,
        frame_index=int(raw.frame_index[pos]),
        t_sec=float(raw.t_sec[pos]),
        offset_from_start_s=float(raw.t_sec[pos]) - float(raw.segment_s[0]),
        person_row=row,
        bbox=tuple(float(v) for v in raw.bboxes[row]),  # type: ignore[arg-type]
        weak=n_valid < raw.params.min_valid_keypoints,
        n_valid_keypoints=n_valid,
        **fields,
    )


def _choose_by_default(raw: PoseRaw, pos: int, fixed: bool, start_pos: int, params: TargetParams) -> TargetSelection:
    start_s = float(raw.segment_s[0])
    if fixed:
        positions: list[int] = [pos]
    else:
        positions = [
            p for p in range(start_pos, raw.n_frames) if float(raw.t_sec[p]) <= start_s + params.search_s + _EPS
        ]
    for p in positions:
        rows = _person_rows(raw, p)
        eligible = rows[usable_boxes(raw.bboxes[rows]) & (_n_valid(raw, rows) >= raw.params.min_valid_keypoints)]
        if eligible.size:
            scores = _default_scores(raw, eligible)
            best = int(np.argmax(scores))  # the first maximum: equal scores give the lowest row
            ordered = np.sort(scores)[::-1]
            if eligible.size == 1:
                ratio, ambiguous = None, False
            elif ordered[0] > 0.0:
                ratio = float(ordered[1] / ordered[0])
                ambiguous = ratio >= params.ambiguity_ratio
            else:
                ratio, ambiguous = None, True
            return _build(
                raw,
                p,
                int(eligible[best]),
                method="default",
                score=float(scores[best]),
                n_candidates=int(eligible.size),
                ambiguous=ambiguous,
                runner_up_ratio=ratio,
            )
    where = (
        f"the frame at {float(raw.t_sec[pos]):.3f} s"
        if fixed
        else f"the first {params.search_s:.1f} s from the segment start ({start_s:.3f} s)"
    )
    raise TargetSelectionError(
        f"no eligible person in {where}: a person needs at least {raw.params.min_valid_keypoints} valid keypoints "
        f"and a box with an area"
    )


def _choose_by_box(raw: PoseRaw, pos: int, user_box: np.ndarray, params: TargetParams) -> TargetSelection:
    rows = _person_rows(raw, pos)
    if rows.size == 0:
        raise TargetSelectionError(f"no person on the frame at {float(raw.t_sec[pos]):.3f} s")
    iou = iou_to_box(raw.bboxes[rows], user_box)
    order = np.argsort(-iou, kind="stable")  # ties: the lowest row first
    best = float(iou[order[0]])
    if best < params.min_iou:
        raise TargetSelectionError(
            f"the box overlaps no person enough (best IoU {best:.2f}, at least {params.min_iou:.2f} needed)"
        )
    if rows.size > 1:
        second = float(iou[order[1]])
        if second >= params.min_iou and best < params.two_people_iou_ratio * second:
            raise TargetSelectionError(
                f"the box covers two people about as much (IoU {best:.2f} and {second:.2f}): draw it around one person"
            )
    return _build(
        raw,
        pos,
        int(rows[order[0]]),
        method="user_box",
        score=best,
        n_candidates=int(rows.size),
        ambiguous=False,
        runner_up_ratio=None,
    )
