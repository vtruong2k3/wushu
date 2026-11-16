"""Compare two pose runs of the same frames (N against N = 1) and summarise what a run gives downstream (P3.07).

**Matching.** In every frame the persons of the reference run are matched to the persons of the other run by
Hungarian assignment on ``cost = mean distance of the keypoints valid in both / hull height of the reference person``
(at least ``min_common`` common valid keypoints; the hull is the box of the reference person's valid keypoints). A pair
is accepted when ``cost <= gate`` (0.5 body height). An unmatched reference person is **missed**, an unmatched person of
the other run is **extra**; a person that has no finite cost with anybody (fewer than ``min_common`` common valid
keypoints with every person of the other frame) is **uncomparable** and counted apart, never dropped, never called a
miss. Where one frame has no person at all the people of the other are missed or extra.

**Distances** of the matched pairs, per keypoint valid in both: in pixels of the image and in body heights (the pixel
distance over the hull height of the reference person), pooled over all pairs and frames; the arrays are kept so that
runs can be pooled (``pool_comparisons``) and the percentiles computed over all distances, not averaged.

**Entry delay.** The persons of the reference run have tracks (``associate_tracks``); for each track that is matched at
least once, the delay is the number of frames between the first frame of the track and the first frame in which it is
matched; a track that is never matched is counted.

This measures the **consistency** of two runs; it does not say which run is right (no labels are used).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from scipy.optimize import linear_sum_assignment

from taiji_ai.bench import BenchError
from taiji_ai.pose.runner import PoseRaw, valid_keypoint_mask
from taiji_ai.pose.skeleton import JOINTS
from taiji_ai.track.associate import associate_tracks
from taiji_ai.track.geometry import keypoint_hull
from taiji_ai.track.state import TRACKED, TargetStateError, TargetTrack, resolve_target
from taiji_ai.track.target import TargetSelectionError, select_target

JOINT_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "head": ("Nose", "LEye", "REye", "LEar", "REar", "Head"),
    "trunk": ("Neck", "LShoulder", "RShoulder", "LHip", "RHip", "Hip"),
    "arms": ("LElbow", "RElbow", "LWrist", "RWrist"),
    "legs": ("LKnee", "RKnee", "LAnkle", "RAnkle"),
    "feet": ("LBigToe", "RBigToe", "LSmallToe", "RSmallToe", "LHeel", "RHeel"),
}
_BIG: Final = 1.0e6


@dataclass(frozen=True)
class DistanceStats:
    median: float
    p95: float
    p99: float
    max: float
    n: int


def _stats(values: np.ndarray) -> DistanceStats | None:
    if values.size == 0:
        return None
    return DistanceStats(
        float(np.median(values)),
        float(np.percentile(values, 95)),
        float(np.percentile(values, 99)),
        float(values.max()),
        int(values.size),
    )


@dataclass(frozen=True, eq=False)
class RunComparison:
    """The other run against the reference run; counts are persons (or person-frames), arrays are per keypoint pair."""

    n_frames: int
    n_equal_count_frames: int  # frames in which both runs have the same number of persons
    n_ref_persons: int
    n_other_persons: int
    n_pairs: int  # matched persons
    n_missed: int  # persons of the reference run without a match
    n_extra: int  # persons of the other run without a match
    n_uncomparable_ref: int
    n_uncomparable_other: int
    entry_delays: tuple[int, ...]  # frames, one per reference track that was matched
    n_tracks_never_matched: int
    dist_px: np.ndarray  # (K,) float64, pixels, one per keypoint valid in both of a matched pair
    dist_norm: np.ndarray  # (K,) float64, body heights of the reference person
    dist_joint: np.ndarray  # (K,) int16, the keypoint index of each distance
    pair_costs: np.ndarray  # (n_pairs,) float64, the matching cost of each accepted pair

    @property
    def count_agreement(self) -> float:
        return self.n_equal_count_frames / self.n_frames

    @property
    def px(self) -> DistanceStats | None:
        return _stats(self.dist_px)

    @property
    def norm(self) -> DistanceStats | None:
        return _stats(self.dist_norm)

    @property
    def group_p95(self) -> dict[str, float | None]:
        """p95 of the distance in body heights per joint group (None where the group has no distance)."""
        out: dict[str, float | None] = {}
        for name, joints in JOINT_GROUPS.items():
            index = [JOINTS.index(j) for j in joints]
            values = self.dist_norm[np.isin(self.dist_joint, index)]
            out[name] = float(np.percentile(values, 95)) if values.size else None
        return out


def _hull_heights(raw: PoseRaw, valid: np.ndarray) -> list[float | None]:
    heights: list[float | None] = []
    for row in range(raw.keypoints.shape[0]):
        hull = keypoint_hull(raw.keypoints[row].astype(np.float64), valid[row])
        heights.append(None if hull is None or hull[3] - hull[1] <= 0.0 else float(hull[3] - hull[1]))
    return heights


def compare_runs(ref: PoseRaw, other: PoseRaw, *, gate: float = 0.5, min_common: int = 4) -> RunComparison:
    """Match the persons of ``other`` to those of ``ref`` frame by frame and measure the distances (see above)."""
    if not (math.isfinite(gate) and gate > 0.0):
        raise BenchError(f"the gate must be a finite number > 0, got {gate!r}")
    if not (np.array_equal(ref.frame_index, other.frame_index) and np.array_equal(ref.t_sec, other.t_sec)):
        raise BenchError("the two runs do not cover the same frames (frame_index and t_sec must be equal)")
    valid_a = valid_keypoint_mask(ref.keypoints, ref.scores, ref.params.min_score)
    valid_b = valid_keypoint_mask(other.keypoints, other.scores, other.params.min_score)
    heights = _hull_heights(ref, valid_a)
    kp_a, kp_b = ref.keypoints.astype(np.float64), other.keypoints.astype(np.float64)
    tracks = associate_tracks(ref)

    n_equal = n_pairs = n_missed = n_extra = unc_a = unc_b = 0
    dist_px: list[np.ndarray] = []
    dist_norm: list[np.ndarray] = []
    dist_joint: list[np.ndarray] = []
    costs: list[float] = []
    first_matched: dict[int, int] = {}
    for f in range(ref.n_frames):
        rows_a = list(range(int(ref.person_offsets[f]), int(ref.person_offsets[f + 1])))
        rows_b = list(range(int(other.person_offsets[f]), int(other.person_offsets[f + 1])))
        n_equal += int(len(rows_a) == len(rows_b))
        cost = np.full((len(rows_a), len(rows_b)), np.inf)
        for i, a in enumerate(rows_a):
            height = heights[a]
            if height is None:
                continue
            for j, b in enumerate(rows_b):
                common = valid_a[a] & valid_b[b]
                if int(common.sum()) >= min_common:
                    cost[i, j] = float(np.linalg.norm(kp_a[a][common] - kp_b[b][common], axis=1).mean()) / height
        matched_a: set[int] = set()
        matched_b: set[int] = set()
        if cost.size:
            gated = np.where(cost <= gate, cost, _BIG)
            for i, j in zip(*linear_sum_assignment(gated), strict=True):
                if cost[i, j] > gate:
                    continue
                a, b = rows_a[i], rows_b[j]
                height = heights[a]
                assert height is not None  # a pair with a finite cost has a reference height
                matched_a.add(i)
                matched_b.add(j)
                n_pairs += 1
                costs.append(float(cost[i, j]))
                common = valid_a[a] & valid_b[b]
                d = np.linalg.norm(kp_a[a][common] - kp_b[b][common], axis=1)
                dist_px.append(d)
                dist_norm.append(d / height)
                dist_joint.append(np.flatnonzero(common).astype(np.int16))
                track = int(tracks.track_id[a])
                if track >= 0:
                    first_matched.setdefault(track, f)
        for i in range(len(rows_a)):
            if i in matched_a:
                continue
            if rows_b and not np.isfinite(cost[i]).any():
                unc_a += 1
            else:
                n_missed += 1
        for j in range(len(rows_b)):
            if j in matched_b:
                continue
            if rows_a and not np.isfinite(cost[:, j]).any():
                unc_b += 1
            else:
                n_extra += 1

    delays = tuple(
        int(first_matched[t] - int(tracks.track_first_frame[t])) for t in range(tracks.n_tracks) if t in first_matched
    )

    def cat(chunks: list[np.ndarray], dtype: Any) -> np.ndarray:
        return np.concatenate(chunks).astype(dtype) if chunks else np.empty(0, dtype=dtype)

    return RunComparison(
        n_frames=ref.n_frames,
        n_equal_count_frames=n_equal,
        n_ref_persons=int(ref.person_offsets[-1]),
        n_other_persons=int(other.person_offsets[-1]),
        n_pairs=n_pairs,
        n_missed=n_missed,
        n_extra=n_extra,
        n_uncomparable_ref=unc_a,
        n_uncomparable_other=unc_b,
        entry_delays=delays,
        n_tracks_never_matched=tracks.n_tracks - len(first_matched),
        dist_px=cat(dist_px, np.float64),
        dist_norm=cat(dist_norm, np.float64),
        dist_joint=cat(dist_joint, np.int16),
        pair_costs=np.asarray(costs, dtype=np.float64),
    )


def pool_comparisons(comparisons: list[RunComparison]) -> RunComparison:
    """One comparison over several clips: counts add up, the distances are pooled (percentiles over all of them)."""
    if not comparisons:
        raise BenchError("no comparison to pool")
    return RunComparison(
        n_frames=sum(c.n_frames for c in comparisons),
        n_equal_count_frames=sum(c.n_equal_count_frames for c in comparisons),
        n_ref_persons=sum(c.n_ref_persons for c in comparisons),
        n_other_persons=sum(c.n_other_persons for c in comparisons),
        n_pairs=sum(c.n_pairs for c in comparisons),
        n_missed=sum(c.n_missed for c in comparisons),
        n_extra=sum(c.n_extra for c in comparisons),
        n_uncomparable_ref=sum(c.n_uncomparable_ref for c in comparisons),
        n_uncomparable_other=sum(c.n_uncomparable_other for c in comparisons),
        entry_delays=tuple(d for c in comparisons for d in c.entry_delays),
        n_tracks_never_matched=sum(c.n_tracks_never_matched for c in comparisons),
        dist_px=np.concatenate([c.dist_px for c in comparisons]),
        dist_norm=np.concatenate([c.dist_norm for c in comparisons]),
        dist_joint=np.concatenate([c.dist_joint for c in comparisons]),
        pair_costs=np.concatenate([c.pair_costs for c in comparisons]),
    )


@dataclass(frozen=True, eq=False)
class Downstream:
    """What P3.04 to P3.06 make of a run: the default target, its share of tracked frames, the events."""

    target_found: bool
    error: str | None  # why there is no target
    selection_frame_pos: int | None
    target_keypoints: np.ndarray | None  # (26, 2) of the chosen person at the selection frame
    target_valid: np.ndarray | None  # (26,) bool
    share_tracked: float | None
    share_lost: float | None
    share_target_lost: float | None
    share_before_target: float | None
    events: dict[str, int]
    needs_reselect: bool | None
    reselect_reason: str | None
    track: TargetTrack | None  # the whole target track (P3.06), kept to compare the tracks of two runs


def downstream_summary(raw: PoseRaw) -> Downstream:
    """Run ``select_target`` (default rule), ``associate_tracks`` and ``resolve_target`` and summarise; no target is a
    result (``target_found = False`` with the reason), not an exception."""
    empty: dict[str, Any] = dict(
        selection_frame_pos=None, target_keypoints=None, target_valid=None, share_tracked=None, share_lost=None,
        share_target_lost=None, share_before_target=None, events={}, needs_reselect=None, reselect_reason=None,
        track=None,
    )  # fmt: skip
    try:
        selection = select_target(raw)
        track = resolve_target(raw, associate_tracks(raw), selection)
    except (TargetSelectionError, TargetStateError) as exc:
        return Downstream(target_found=False, error=str(exc), **empty)
    n = track.n_frames
    counts = track.meta.counts
    events: dict[str, int] = {}
    for event in track.meta.events:
        events[event.kind] = events.get(event.kind, 0) + 1
    valid = valid_keypoint_mask(
        raw.keypoints[selection.person_row], raw.scores[selection.person_row], raw.params.min_score
    )
    return Downstream(
        target_found=True,
        error=None,
        selection_frame_pos=selection.frame_pos,
        target_keypoints=raw.keypoints[selection.person_row].copy(),
        target_valid=valid,
        share_tracked=counts.n_tracked / n,
        share_lost=counts.n_lost / n,
        share_target_lost=counts.n_target_lost / n,
        share_before_target=counts.n_before_target / n,
        events=events,
        needs_reselect=track.meta.needs_reselect,
        reselect_reason=track.meta.reselect_reason,
        track=track,
    )


@dataclass(frozen=True, eq=False)
class TargetComparison:
    """The target track of the other run against the one of the reference run (what P4 will receive).

    Added after the dry run of P3.07 as a supplementary view; it is **not** part of the rule for N, which was written
    before. Frames are counted by who has the target there; the distances are per keypoint valid in both runs, in pixels
    and in body heights (the hull height of the reference keypoints of that frame).
    """

    n_frames: int
    n_both_tracked: int
    n_ref_only: int  # the reference run has the target, the other run does not
    n_other_only: int
    n_uncomparable_frames: int  # both have the target but fewer than ``min_common`` common valid keypoints
    dist_px: np.ndarray
    dist_norm: np.ndarray

    @property
    def px(self) -> DistanceStats | None:
        return _stats(self.dist_px)

    @property
    def norm(self) -> DistanceStats | None:
        return _stats(self.dist_norm)


def compare_target_tracks(
    ref: Downstream, other: Downstream, min_score: float, *, min_common: int = 4
) -> TargetComparison | None:
    """Compare the target tracks of two runs of the same frames; ``None`` when either run has no target."""
    if ref.track is None or other.track is None:
        return None
    a, b = ref.track, other.track
    if not (np.array_equal(a.frame_index, b.frame_index) and np.array_equal(a.t_sec, b.t_sec)):
        raise BenchError("the two target tracks do not cover the same frames (frame_index and t_sec must be equal)")
    tracked_a, tracked_b = a.status == TRACKED, b.status == TRACKED
    valid_a = valid_keypoint_mask(a.keypoints, a.scores, min_score)
    valid_b = valid_keypoint_mask(b.keypoints, b.scores, min_score)
    px: list[np.ndarray] = []
    norm: list[np.ndarray] = []
    uncomparable = 0
    for f in np.flatnonzero(tracked_a & tracked_b):
        common = valid_a[f] & valid_b[f]
        hull = keypoint_hull(a.keypoints[f].astype(np.float64), valid_a[f])
        if int(common.sum()) < min_common or hull is None or hull[3] - hull[1] <= 0.0:
            uncomparable += 1
            continue
        d = np.linalg.norm(
            a.keypoints[f][common].astype(np.float64) - b.keypoints[f][common].astype(np.float64), axis=1
        )
        px.append(d)
        norm.append(d / float(hull[3] - hull[1]))
    return TargetComparison(
        n_frames=a.n_frames,
        n_both_tracked=int((tracked_a & tracked_b).sum()),
        n_ref_only=int((tracked_a & ~tracked_b).sum()),
        n_other_only=int((~tracked_a & tracked_b).sum()),
        n_uncomparable_frames=uncomparable,
        dist_px=np.concatenate(px) if px else np.empty(0),
        dist_norm=np.concatenate(norm) if norm else np.empty(0),
    )


def pool_target_comparisons(comparisons: list[TargetComparison]) -> TargetComparison:
    """One target comparison over several clips: counts add up, the distances are pooled."""
    if not comparisons:
        raise BenchError("no target comparison to pool")
    return TargetComparison(
        n_frames=sum(c.n_frames for c in comparisons),
        n_both_tracked=sum(c.n_both_tracked for c in comparisons),
        n_ref_only=sum(c.n_ref_only for c in comparisons),
        n_other_only=sum(c.n_other_only for c in comparisons),
        n_uncomparable_frames=sum(c.n_uncomparable_frames for c in comparisons),
        dist_px=np.concatenate([c.dist_px for c in comparisons]),
        dist_norm=np.concatenate([c.dist_norm for c in comparisons]),
    )


def same_target(ref: Downstream, other: Downstream, *, gate: float = 0.5, min_common: int = 4) -> bool | None:
    """Is the chosen performer the same person in the two runs? ``None``: neither run has a target or there are fewer
    than ``min_common`` common valid keypoints to tell. The distance is measured as in ``compare_runs``."""
    if not ref.target_found and not other.target_found:
        return None
    if ref.target_found != other.target_found or ref.selection_frame_pos != other.selection_frame_pos:
        return False
    assert ref.target_keypoints is not None and other.target_keypoints is not None
    assert ref.target_valid is not None and other.target_valid is not None
    common = ref.target_valid & other.target_valid
    hull = keypoint_hull(ref.target_keypoints.astype(np.float64), ref.target_valid)
    if int(common.sum()) < min_common or hull is None or hull[3] - hull[1] <= 0.0:
        return None
    distance = float(
        np.linalg.norm(
            ref.target_keypoints[common].astype(np.float64) - other.target_keypoints[common].astype(np.float64), axis=1
        ).mean()
    )
    return distance / float(hull[3] - hull[1]) <= gate
