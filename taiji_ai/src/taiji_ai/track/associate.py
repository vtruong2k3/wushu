"""Frame-to-frame association of persons: a track id for every eligible person of a ``PoseRaw`` (W5 step 2, P3.05).

The performer chosen by ``select_target`` (P3.04) can then be followed through the segment: the person row of the
selection frame has a track id, and so do the persons of the other frames. This module associates; it does not decide
when a target is lost or when a new track is the same person again (P3.06), it does not smooth, and it writes no file.

**Cost** of a person ``p`` against a track ``k`` (the track's last person)::

    iou_term = 1 - IoU(hull of p, hull of k)
    kp_term  = min(1, mean distance of the common valid keypoints / height of the hull of k)
    cost     = (w_iou x iou_term + w_kp x kp_term) / (w_iou + w_kp)        in [0, 1]

The hull is the box of the valid keypoints; when the person and the track have at least ``min_common_keypoints`` valid
keypoints in common, both hulls are taken on those common keypoints (a person whose legs are hidden for a moment does
not look smaller). The stored box of the detector is not used: it changes with the detector cadence. With fewer common
keypoints the keypoint term does not exist and the cost is the IoU term alone (never a made-up number).

**Assignment**: per frame, ``scipy.optimize.linear_sum_assignment`` over the live tracks and the eligible persons; a
pair whose cost is above ``max_cost`` is never matched. Matched persons extend their track; the others start a new
track (ids in row order). A track that is not matched stays live for ``max_gap_s`` seconds of the real ``t_sec`` (a
missed detection) and then closes. Everything is deterministic: ties go to the lowest index.

**Eligible persons** have at least ``raw.params.min_valid_keypoints`` valid keypoints and a hull with an area (the rule
of the runner and of P3.04). Weak persons get ``track_id = -1``: they steal no match and make no ghost track.

``match_margin`` tells where an identity is uncertain: the smallest cost of any other live track for the person, or of
any other person for the track, minus the cost chosen. It is about 0 where two people coincide (no appearance feature
exists in the MVP, so two identical bodies at the same place cannot be told apart) and large elsewhere.

The values of the parameters are provisional. Measured on 2026-11-16 (task file P3.05): the costs of true matches
reached 0.125 on real clips and on SYN-12; the nearest wrong match on the real clips cost 0.64 or more; a motion
prediction did not help and was left out. Idea source: W5 of ``Docs/TECH_WORKFLOW_V1.md`` (the plan names
``sort_people_sports2d`` of Pose2Sim, BSD-3-Clause; its code was not read and none is copied).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.optimize import linear_sum_assignment

from taiji_ai.pose.runner import PoseRaw, valid_keypoint_mask
from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.track.geometry import iou, keypoint_hull

log = logging.getLogger(__name__)

_BIG: Final = 1.0e6  # cost of a pair that the gate forbids, inside the assignment only
_TIME_EPS: Final = 1e-9


@dataclass(frozen=True)
class AssociationParams:
    """Provisional values, measured on one real clip and synthetic scenes (see the module docstring)."""

    w_iou: float = 1.0  # weight of the IoU term
    w_kp: float = 1.0  # weight of the keypoint term
    # A pair above this cost is never matched (true matches reached 0.125, wrong ones 0.64 or more).
    max_cost: float = 0.3
    max_gap_s: float = 0.1  # [s] a track that is not matched stays live this long (real ``t_sec``)
    min_common_keypoints: int = 4  # keypoints valid in both needed for the keypoint term and the common hull

    def __post_init__(self) -> None:
        for name in ("w_iou", "w_kp"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0.0):
                raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")
        if self.w_iou + self.w_kp <= 0.0:
            raise ValueError("w_iou and w_kp cannot both be 0")
        if not (math.isfinite(self.max_cost) and 0.0 < self.max_cost <= 1.0):
            raise ValueError(f"max_cost must be in (0, 1], got {self.max_cost!r}")
        if not (math.isfinite(self.max_gap_s) and self.max_gap_s >= 0.0):
            raise ValueError(f"max_gap_s must be a finite number >= 0, got {self.max_gap_s!r}")
        if not isinstance(self.min_common_keypoints, int) or not 1 <= self.min_common_keypoints <= NUM_JOINTS:
            raise ValueError(
                f"min_common_keypoints must be an integer in [1, {NUM_JOINTS}], got {self.min_common_keypoints!r}"
            )


@dataclass(frozen=True, eq=False)
class Tracks:
    """Track ids of the person rows of a ``PoseRaw`` (arrays have one entry per person row, in the same order)."""

    track_id: np.ndarray  # (D,) int32; ids from 0 in order of first appearance; -1 = not tracked (weak or unusable)
    match_cost: np.ndarray  # (D,) float32 in [0, 1]; NaN where there is no match (a track start, or not tracked)
    match_margin: np.ndarray  # (D,) float32; how contested the match is (see the module docstring); NaN: no competitor
    # (D,) int32; frames since the previous person of the track; 0 = track start; -1 = not tracked
    gap_frames: np.ndarray
    gap_s: np.ndarray  # (D,) float32; [s] since the previous person of the track; NaN for a track start or not tracked
    track_first_frame: np.ndarray  # (K,) int32; frame position of the first person of each track
    track_last_frame: np.ndarray  # (K,) int32; frame position of the last person
    track_n_persons: np.ndarray  # (K,) int32
    params: AssociationParams

    @property
    def n_tracks(self) -> int:
        return int(self.track_first_frame.size)

    def equals(self, other: Tracks) -> bool:
        """Same tracks (NaN equals NaN)."""
        names = (
            "track_id", "match_cost", "match_margin", "gap_frames", "gap_s",
            "track_first_frame", "track_last_frame", "track_n_persons",
        )  # fmt: skip
        return self.params == other.params and all(
            np.array_equal(getattr(self, n), getattr(other, n), equal_nan=True) for n in names
        )


def track_of_person(tracks: Tracks, person_row: int) -> int:
    """The track id of a person row (-1: not tracked). Raises ``ValueError`` for a row that does not exist."""
    if not 0 <= person_row < tracks.track_id.size:
        raise ValueError(f"person row {person_row} is outside 0..{tracks.track_id.size - 1}")
    return int(tracks.track_id[person_row])


class _Track:
    """The live state of a track: its last person."""

    __slots__ = ("id", "keypoints", "valid", "hull", "t_sec", "frame")

    def __init__(self, track_id: int, keypoints: np.ndarray, valid: np.ndarray, hull: np.ndarray, t: float, frame: int):
        self.id, self.keypoints, self.valid, self.hull = track_id, keypoints, valid, hull
        self.t_sec, self.frame = t, frame


def _pair_cost(track: _Track, kp: np.ndarray, valid: np.ndarray, hull: np.ndarray, params: AssociationParams) -> float:
    common = valid & track.valid
    n_common = int(common.sum())
    hull_p, hull_t = hull, track.hull
    if n_common >= params.min_common_keypoints:
        common_p, common_t = keypoint_hull(kp, common), keypoint_hull(track.keypoints, common)
        if common_p is not None and common_t is not None:
            hull_p, hull_t = common_p, common_t
    iou_term = 1.0 - iou(hull_p, hull_t)
    if n_common < params.min_common_keypoints:
        return iou_term
    height = float(track.hull[3] - track.hull[1])  # the whole body of the track, not the common keypoints only
    distance = float(np.linalg.norm(kp[common] - track.keypoints[common], axis=1).mean())
    kp_term = min(1.0, distance / height)
    return (params.w_iou * iou_term + params.w_kp * kp_term) / (params.w_iou + params.w_kp)


def person_cost(raw: PoseRaw, row_a: int, row_b: int, *, params: AssociationParams | None = None) -> float:
    """The association cost (module docstring) of person row ``row_b`` against person row ``row_a`` of ``raw``.

    ``row_a`` plays the track: its hull height is the scale of the keypoint term. The result is in [0, 1], or ``inf``
    when either person has no hull (fewer than two valid keypoints, or no extent): no cost is made up. It is not
    symmetric (the scale is the height of ``row_a``). Used by P3.06 to compare the first pose of a new track with the
    last pose of the target. Raises ``ValueError`` for a row that does not exist.
    """
    params = params or AssociationParams()
    d = raw.keypoints.shape[0]
    for name, row in (("row_a", row_a), ("row_b", row_b)):
        if not 0 <= row < d:
            raise ValueError(f"{name} {row} is outside 0..{d - 1}")
    kp = raw.keypoints[[row_a, row_b]].astype(np.float64)
    valid = valid_keypoint_mask(raw.keypoints[[row_a, row_b]], raw.scores[[row_a, row_b]], raw.params.min_score)
    hull_a, hull_b = keypoint_hull(kp[0], valid[0]), keypoint_hull(kp[1], valid[1])
    if hull_a is None or hull_b is None:
        return math.inf
    return _pair_cost(_Track(-1, kp[0], valid[0], hull_a, 0.0, 0), kp[1], valid[1], hull_b, params)


def _assign(cost: np.ndarray, max_cost: float) -> list[tuple[int, int]]:
    """Hungarian assignment of tracks (rows) to persons (columns): the pairs of lowest total cost whose own cost is
    at most ``max_cost``. A pair above the gate costs a large constant in the assignment, so the number of valid
    matches is maximal before the total cost is minimal; a pair above the gate is never returned."""
    if cost.size == 0:
        return []
    gated = np.where(cost <= max_cost, cost, _BIG)
    tracks_i, persons_j = linear_sum_assignment(gated)
    return [(int(i), int(j)) for i, j in zip(tracks_i, persons_j, strict=True) if cost[i, j] <= max_cost]


def associate_tracks(raw: PoseRaw, *, params: AssociationParams | None = None) -> Tracks:
    """Give every eligible person of ``raw`` a track id by Hungarian assignment, frame to frame (module docstring).

    Args:
        raw: the raw pose of a segment (``run_pose`` or ``load_pose_raw``); it is not modified.
        params: provisional parameters.

    Returns:
        ``Tracks``, aligned with the person rows of ``raw``.
    """
    params = params or AssociationParams()
    keypoints = raw.keypoints.astype(np.float64)
    valid_all = valid_keypoint_mask(raw.keypoints, raw.scores, raw.params.min_score)
    hulls: list[np.ndarray | None] = [keypoint_hull(keypoints[r], valid_all[r]) for r in range(keypoints.shape[0])]
    eligible = np.array(
        [h is not None and int(valid_all[r].sum()) >= raw.params.min_valid_keypoints for r, h in enumerate(hulls)],
        dtype=bool,
    )

    d = keypoints.shape[0]
    track_id = np.full(d, -1, np.int32)
    match_cost = np.full(d, np.nan, np.float32)
    match_margin = np.full(d, np.nan, np.float32)
    gap_frames = np.full(d, -1, np.int32)
    gap_s = np.full(d, np.nan, np.float32)
    first_frame: list[int] = []
    last_frame: list[int] = []
    n_persons: list[int] = []
    live: list[_Track] = []

    for f in range(raw.n_frames):
        t_now = float(raw.t_sec[f])
        live = [tr for tr in live if t_now - tr.t_sec <= params.max_gap_s + _TIME_EPS]
        rows = [r for r in range(int(raw.person_offsets[f]), int(raw.person_offsets[f + 1])) if eligible[r]]
        cost = np.full((len(live), len(rows)), np.inf)
        for i, tr in enumerate(live):
            for j, r in enumerate(rows):
                cost[i, j] = _pair_cost(tr, keypoints[r], valid_all[r], hulls[r], params)  # type: ignore[arg-type]
        pairs = _assign(cost, params.max_cost)
        matched_persons = set()
        for i, j in pairs:
            tr, r = live[i], rows[j]
            competitors = [cost[k, j] for k in range(len(live)) if k != i] + [
                cost[i, m] for m in range(len(rows)) if m != j
            ]
            finite = [c for c in competitors if np.isfinite(c)]
            if finite:
                match_margin[r] = min(finite) - cost[i, j]
            track_id[r], match_cost[r] = tr.id, cost[i, j]
            gap_frames[r], gap_s[r] = f - tr.frame, t_now - tr.t_sec
            tr.keypoints, tr.valid, tr.hull = keypoints[r], valid_all[r], hulls[r]  # type: ignore[assignment]
            tr.t_sec, tr.frame = t_now, f
            last_frame[tr.id] = f
            n_persons[tr.id] += 1
            matched_persons.add(j)
        for j, r in enumerate(rows):
            if j in matched_persons:
                continue
            new_id = len(first_frame)
            live.append(_Track(new_id, keypoints[r], valid_all[r], hulls[r], t_now, f))  # type: ignore[arg-type]
            track_id[r], gap_frames[r] = new_id, 0
            first_frame.append(f)
            last_frame.append(f)
            n_persons.append(1)

    tracks = Tracks(
        track_id=track_id,
        match_cost=match_cost,
        match_margin=match_margin,
        gap_frames=gap_frames,
        gap_s=gap_s,
        track_first_frame=np.asarray(first_frame, np.int32),
        track_last_frame=np.asarray(last_frame, np.int32),
        track_n_persons=np.asarray(n_persons, np.int32),
        params=params,
    )
    log.info(
        "tracks for recording %s: %d tracks, %d persons", raw.recording_id, tracks.n_tracks, int((track_id >= 0).sum())
    )
    return tracks
