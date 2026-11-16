"""The target over time: tracked, lost, target_lost, before_target, and who may take its place (W5 steps 3-4, P3.06).

``resolve_target`` follows the performer chosen by ``select_target`` (P3.04) through the tracks of ``associate_tracks``
(P3.05) and gives every frame of the ``PoseRaw`` one row: the keypoints of the performer, or NaN with the reason.
Nothing is filled or interpolated (AGENTS.md section 5.1): P4 interpolates gaps of at most 150 ms by time; a frame
that is ``lost`` or ``target_lost`` stays NaN here. Nothing is written: ``taiji_ai.track.track_io`` saves the result.

**Statuses** (per frame, ``t`` the real ``t_sec``, ``t_last`` the time of the last frame in which the target was seen):

* ``tracked``: the target's track has a person; keypoints and scores are those of the raw layer;
* ``lost``: the target is missing and ``t - t_last <= max_lost_s``: expected to come back (default 0.5 s, W5);
* ``target_lost``: the target is missing for more than ``max_lost_s``;
* ``before_target``: before the first frame of the target's track (a performer who walks in after the margin starts).

**Who may take the place of a lost target.** The association (P3.05) closes a track after ``max_gap_s`` (0.1 s), so a
performer who was away longer comes back as a *new* track. Only a track that **starts after the target's last frame,
while the target is missing**, is a candidate: a person who was in the picture all along (the distractor who crossed
the performer) is never one. The candidate's first pose is compared with the last pose of the target by the cost of the
association (``person_cost``, in [0, 1]):

* one candidate at or under ``reattach_cost``: it becomes the target from that frame (``reattached``);
* two or more under it with close costs (best / second >= ``ambiguity_ratio``, or both 0): nobody is chosen
  (``ambiguous``);
* none under it, or the absence lasted longer than ``max_reattach_s``: nobody is chosen (``refused``).

Nobody chosen means the frame stays ``lost`` / ``target_lost`` and the user is asked: ``needs_reselect`` with the
reason ``reattach_ambiguous`` or ``reattach_refused`` while no re-attachment or recovery came after the last refusal;
``target_lost_at_end`` when the last frame is ``target_lost``; ``default_choice_ambiguous`` when the default choice of
P3.04 was a close call. The first reason of that list that applies is given; the events say the rest. A weak chosen
person (fewer valid keypoints than ``raw.params.min_valid_keypoints``) is never followed: ``TargetStateError``.

The values are provisional (task file P3.06, section 4: measured on SYN-12 and on real clips of D20 with rows removed;
there is no real clip with a real absence yet). Idea source: W5 of ``Docs/TECH_WORKFLOW_V1.md``; no third-party code.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np

from taiji_ai.pose.runner import PoseRaw
from taiji_ai.pose.skeleton import NUM_JOINTS, SKELETON_ID
from taiji_ai.schemas._base import parse_manifest
from taiji_ai.schemas.track import EventKind, RefusalReason, TrackCounts, TrackEvent, TrackMeta
from taiji_ai.track.associate import Tracks, person_cost
from taiji_ai.track.target import TargetSelection

log = logging.getLogger(__name__)

TRACKED: Final = 0
LOST: Final = 1
TARGET_LOST: Final = 2
BEFORE_TARGET: Final = 3
STATUS_NAMES: Final = ("tracked", "lost", "target_lost", "before_target")  # the index is the code in ``status``

_EPS: Final = 1e-9


class TargetStateError(Exception):
    """The target cannot be followed: a weak chosen person, or a selection / tracks that do not belong to the pose."""


@dataclass(frozen=True)
class TargetStateParams:
    """Provisional values; each has its evidence in the task file P3.06 (section 4) and the module docstring."""

    max_lost_s: float = 0.5  # [s] missing up to this long: ``lost``; longer: ``target_lost`` (W5)
    # A new track is taken as the target at or under this cost. Measured: true returns of SYN-12 up to 100 px away
    # cost 0.44 at most, real returns 0.5 or less in 83 to 100 % of the positions, every stranger 0.65 or more.
    reattach_cost: float = 0.5
    max_reattach_s: float = 5.0  # [s] a safety limit, not measured: after this long the user decides
    ambiguity_ratio: float = 0.6  # best / second cost from which two candidates are a close call

    def __post_init__(self) -> None:
        for name in ("max_lost_s", "max_reattach_s"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0.0):
                raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")
        if self.max_reattach_s < self.max_lost_s:
            raise ValueError(f"max_reattach_s ({self.max_reattach_s}) must not be shorter than max_lost_s")
        for name in ("reattach_cost", "ambiguity_ratio"):
            value = getattr(self, name)
            if not (math.isfinite(value) and 0.0 < value <= 1.0):
                raise ValueError(f"{name} must be in (0, 1], got {value!r}")


@dataclass(frozen=True, eq=False)
class TargetTrack:
    """The target in every frame of a ``PoseRaw`` (arrays have one entry per frame, in frame order)."""

    frame_index: np.ndarray  # (F,) int32; row of the frame in pts.parquet
    t_sec: np.ndarray  # (F,) float64; [s] from the stream start, real PTS
    in_segment: np.ndarray  # (F,) bool; the frame lies in the segment asked for (False in the margins)
    status: np.ndarray  # (F,) uint8; TRACKED, LOST, TARGET_LOST, BEFORE_TARGET (names in STATUS_NAMES)
    track_id: np.ndarray  # (F,) int32; the track of the person used in the frame; -1 when none
    person_row: np.ndarray  # (F,) int32; row in the person arrays of the ``PoseRaw``; -1 when none
    keypoints: np.ndarray  # (F, 26, 2) float32; x y [px], upright image, y down; NaN where status != TRACKED
    scores: np.ndarray  # (F, 26) float32; the model's scores; NaN where status != TRACKED
    match_cost: np.ndarray  # (F,) float32; association cost to the previous person of the track; NaN where none
    match_margin: np.ndarray  # (F,) float32; the margin of the association (about 0: two people coincide); NaN: none
    reattach_cost: np.ndarray  # (F,) float32; on the frame of a re-attachment the cost that allowed it; NaN elsewhere
    meta: TrackMeta

    @property
    def n_frames(self) -> int:
        return int(self.frame_index.size)

    def equals(self, other: TargetTrack) -> bool:
        """Same target track (NaN equals NaN)."""
        names = (
            "frame_index", "t_sec", "in_segment", "status", "track_id", "person_row", "keypoints", "scores",
            "match_cost", "match_margin", "reattach_cost",
        )  # fmt: skip
        return self.meta == other.meta and all(
            np.array_equal(getattr(self, n), getattr(other, n), equal_nan=True) for n in names
        )


def _check_inputs(raw: PoseRaw, tracks: Tracks, selection: TargetSelection) -> int:
    """Check that ``tracks`` and ``selection`` belong to ``raw``; returns the track id of the chosen person."""
    d = raw.keypoints.shape[0]
    if tracks.track_id.size != d:
        raise TargetStateError(
            f"the tracks have {tracks.track_id.size} person rows but the pose file has {d}: "
            f"they were made from another pose file"
        )
    pos = selection.frame_pos
    if not 0 <= pos < raw.n_frames:
        raise TargetStateError(f"the selection's frame_pos {pos} is outside 0..{raw.n_frames - 1}")
    low, high = int(raw.person_offsets[pos]), int(raw.person_offsets[pos + 1])
    if not low <= selection.person_row < high:
        raise TargetStateError(
            f"the selection's person_row {selection.person_row} is not a person of frame {pos} "
            f"(rows {low}..{high - 1}): it was made from another pose file"
        )
    if selection.frame_index != int(raw.frame_index[pos]):
        raise TargetStateError(
            f"the selection's frame_index {selection.frame_index} is not the one of frame {pos} "
            f"({int(raw.frame_index[pos])}): it was made from another pose file"
        )
    if selection.t_sec != float(raw.t_sec[pos]):
        raise TargetStateError(
            f"the selection's t_sec {selection.t_sec!r} is not the time of frame {pos} "
            f"({float(raw.t_sec[pos])!r}): it was made from another pose file"
        )
    track = int(tracks.track_id[selection.person_row])
    if track < 0:
        raise TargetStateError(
            f"the chosen person is weak (fewer than {raw.params.min_valid_keypoints} valid keypoints) and has no "
            f"track: it cannot be followed; choose another person"
        )
    return track


def resolve_target(
    raw: PoseRaw, tracks: Tracks, selection: TargetSelection, *, params: TargetStateParams | None = None
) -> TargetTrack:
    """Follow the chosen performer through ``raw``; see the module docstring for the rules.

    Args:
        raw: the raw pose of the segment; it is not modified.
        tracks: ``associate_tracks(raw)``.
        selection: ``select_target(raw, ...)``.
        params: provisional parameters.

    Raises:
        TargetStateError: the selection or the tracks do not belong to ``raw``, or the chosen person is weak.
    """
    params = params or TargetStateParams()
    current = _check_inputs(raw, tracks, selection)
    n = raw.n_frames
    d = raw.keypoints.shape[0]
    pos_of_row = np.searchsorted(raw.person_offsets, np.arange(d), side="right") - 1
    row_at: dict[tuple[int, int], int] = {}
    for person in np.flatnonzero(tracks.track_id >= 0):
        row_at[int(tracks.track_id[person]), int(pos_of_row[person])] = int(person)
    starts_at: dict[int, list[int]] = {}
    for track, first in enumerate(tracks.track_first_frame):
        starts_at.setdefault(int(first), []).append(track)

    status = np.full(n, BEFORE_TARGET, np.uint8)
    track_id = np.full(n, -1, np.int32)
    person_row = np.full(n, -1, np.int32)
    keypoints = np.full((n, NUM_JOINTS, 2), np.nan, np.float32)
    scores = np.full((n, NUM_JOINTS), np.nan, np.float32)
    match_cost = np.full(n, np.nan, np.float32)
    match_margin = np.full(n, np.nan, np.float32)
    reattach_cost = np.full(n, np.nan, np.float32)
    events: list[TrackEvent] = []

    def event(
        kind: EventKind, f: int, track: int, cost: float | None = None, reason: RefusalReason | None = None
    ) -> None:
        events.append(
            TrackEvent(kind=kind, frame_pos=f, t_sec=float(raw.t_sec[f]), track_id=track, cost=cost, reason=reason)
        )

    def take(f: int, row: int, track: int) -> None:
        status[f], track_id[f], person_row[f] = TRACKED, track, row
        keypoints[f], scores[f] = raw.keypoints[row], raw.scores[row]
        match_cost[f], match_margin[f] = tracks.match_cost[row], tracks.match_margin[row]

    first_pos = int(tracks.track_first_frame[current])
    missing, target_lost_logged = False, False
    pending: str | None = None  # "refused" or "ambiguous": nobody was taken and nobody has come back since
    t_last, last_row = float(raw.t_sec[first_pos]), -1
    for f in range(first_pos, n):
        t = float(raw.t_sec[f])
        row = row_at.get((current, f))
        if row is not None:
            if missing:
                event("recovered", f, current)
                missing, pending = False, None
            take(f, row, current)
            t_last, last_row = t, row
            continue
        if not missing:
            missing, target_lost_logged = True, False
            event("lost", f, current)
        candidates = [(k, row_at[k, f]) for k in starts_at.get(f, ()) if (k, f) in row_at]
        chosen, attach_cost = None, math.nan
        if candidates:
            chosen, attach_cost, pending = _decide(
                raw, tracks, params, candidates, last_row, t - t_last, f, event, pending
            )
        if chosen is not None:
            current = chosen[0]
            event("reattached", f, current, attach_cost)
            missing, pending = False, None
            take(f, chosen[1], current)
            reattach_cost[f] = attach_cost
            t_last, last_row = t, chosen[1]
        elif t - t_last <= params.max_lost_s + _EPS:
            status[f] = LOST
        else:
            status[f] = TARGET_LOST
            if not target_lost_logged:
                event("target_lost", f, current)
                target_lost_logged = True

    reason = _reselect_reason(pending, int(status[-1]), selection.ambiguous)
    in_segment = (raw.t_sec >= raw.segment_s[0] - _EPS) & (raw.t_sec <= raw.segment_s[1] + _EPS)
    counts = TrackCounts(
        n_frames=n,
        n_in_segment=int(in_segment.sum()),
        n_tracked=int((status == TRACKED).sum()),
        n_lost=int((status == LOST).sum()),
        n_target_lost=int((status == TARGET_LOST).sum()),
        n_before_target=int((status == BEFORE_TARGET).sum()),
        n_reattached=sum(e.kind == "reattached" for e in events),
        n_refused=sum(e.kind == "refused" for e in events),
        n_ambiguous=sum(e.kind == "ambiguous" for e in events),
    )
    meta = parse_manifest(
        TrackMeta,
        {
            "schema_version": "track/1",
            "skeleton": SKELETON_ID,
            "recording_id": raw.recording_id,
            "image_size": list(raw.image_size),
            "segment_s": list(raw.segment_s),
            "selection": {
                "method": selection.method,
                "ambiguous": selection.ambiguous,
                "frame_pos": selection.frame_pos,
                "frame_index": selection.frame_index,
                "t_sec": selection.t_sec,
                "track_id": int(tracks.track_id[selection.person_row]),
            },
            "params": {
                "max_lost_s": params.max_lost_s,
                "reattach_cost": params.reattach_cost,
                "max_reattach_s": params.max_reattach_s,
                "ambiguity_ratio": params.ambiguity_ratio,
            },
            "association": {
                "w_iou": tracks.params.w_iou,
                "w_kp": tracks.params.w_kp,
                "max_cost": tracks.params.max_cost,
                "max_gap_s": tracks.params.max_gap_s,
                "min_common_keypoints": tracks.params.min_common_keypoints,
            },
            "counts": counts.model_dump(),
            "needs_reselect": reason is not None,
            "reselect_reason": reason,
            "events": [e.model_dump() for e in events],
        },
    )
    log.info(
        "target track for recording %s: %d frames, %d tracked, %d lost, %d target_lost, %d re-attached, reselect %s",
        raw.recording_id,
        n,
        counts.n_tracked,
        counts.n_lost,
        counts.n_target_lost,
        counts.n_reattached,
        reason,
    )
    return TargetTrack(
        frame_index=raw.frame_index.astype(np.int32, copy=True),
        t_sec=raw.t_sec.astype(np.float64, copy=True),
        in_segment=in_segment,
        status=status,
        track_id=track_id,
        person_row=person_row,
        keypoints=keypoints,
        scores=scores,
        match_cost=match_cost,
        match_margin=match_margin,
        reattach_cost=reattach_cost,
        meta=meta,
    )


def _decide(
    raw: PoseRaw,
    tracks: Tracks,
    params: TargetStateParams,
    candidates: list[tuple[int, int]],
    last_row: int,
    away_s: float,
    f: int,
    event: Callable[..., None],
    pending: str | None,
) -> tuple[tuple[int, int] | None, float, str | None]:
    """Decide among the tracks that start in frame ``f`` while the target is missing.

    Returns ``(chosen (track, row) or None, its cost, the new pending state)``; logs ``refused`` / ``ambiguous``.
    """
    costed = []
    for track, row in candidates:
        cost = person_cost(raw, last_row, row, params=tracks.params)
        if not math.isfinite(cost):
            raise TargetStateError("a candidate has no comparable pose: the tracks do not match the pose file")
        costed.append((cost, track, row))
    costed.sort()
    if away_s > params.max_reattach_s + _EPS:
        for cost, track, _ in costed:
            event("refused", f, track, cost, "too_late")
        return None, math.nan, "refused"
    under = [c for c in costed if c[0] <= params.reattach_cost]
    if not under:
        for cost, track, _ in costed:
            event("refused", f, track, cost, "over_threshold")
        return None, math.nan, "refused"
    best = under[0]
    if len(under) > 1:
        second = under[1][0]
        if second <= 0.0 or best[0] / second >= params.ambiguity_ratio:
            event("ambiguous", f, best[1], best[0])
            return None, math.nan, "ambiguous"
    return (best[1], best[2]), best[0], pending


def _reselect_reason(pending: str | None, last_status: int, default_ambiguous: bool) -> str | None:
    if pending == "ambiguous":
        return "reattach_ambiguous"
    if pending == "refused":
        return "reattach_refused"
    if last_status == TARGET_LOST:
        return "target_lost_at_end"
    if default_ambiguous:
        return "default_choice_ambiguous"
    return None
