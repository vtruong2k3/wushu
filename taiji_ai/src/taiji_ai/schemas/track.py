"""Header of ``track.parquet`` (schema ``track/1``, P3.06).

The file has one row per frame of the pose file (columns documented in ``taiji_ai.track.track_io``) and this model as
JSON in the Parquet schema metadata under the key ``taiji_track_meta``. Units and coordinates: image pixels of the
upright image, x to the right, y down; times in seconds from the stream start. Floats are never NaN or infinite
(AGENTS.md section 6). The header has no path and no file name: the only identifier is the ``recording_id``. Frames and
events are positions in the frames of the pose file (``frame_pos``) next to the frame index of ``pts.parquet``.

Kinds of events (each has its own fields, checked below):

* ``lost``: the target has no person in this frame (the first frame of a missing run); ``track_id`` is the track
  that was followed;
* ``target_lost``: the missing run became longer than ``max_lost_s`` in this frame;
* ``recovered``: the same track has a person again (a gap the association bridged);
* ``reattached``: a track that started after the loss became the target; ``track_id`` is that track, ``cost`` the cost
  of its first pose against the last pose of the target;
* ``refused``: a track that started while the target was missing was not taken: ``reason`` is ``over_threshold``
  (its ``cost`` is above the limit) or ``too_late`` (the absence lasted longer than ``max_reattach_s``);
* ``ambiguous``: two or more new tracks were under the limit with close costs: nobody was taken; ``track_id`` and
  ``cost`` are those of the best of them.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from taiji_ai.schemas._base import UUID4_RE, FrozenModel, Manifest, NonNeg, NonNegInt, PosInt, Seconds

StrictBool = Annotated[bool, Field(strict=True)]
UnitCost = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]  # a cost of the association is in [0, 1]
OpenUnit = Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]  # (0, 1]

EventKind = Literal["lost", "target_lost", "recovered", "reattached", "refused", "ambiguous"]
RefusalReason = Literal["over_threshold", "too_late"]
ReselectReason = Literal["reattach_ambiguous", "reattach_refused", "target_lost_at_end", "default_choice_ambiguous"]


class TrackEvent(FrozenModel):
    """Something that happened to the target; see the module docstring for the fields of each kind."""

    kind: EventKind
    frame_pos: NonNegInt  # position in the frames of the pose file
    t_sec: Seconds  # [s] from the stream start, the time of that frame
    track_id: NonNegInt
    cost: UnitCost | None
    reason: RefusalReason | None

    @model_validator(mode="after")
    def _fields_of_the_kind(self) -> Self:
        needs_cost = self.kind in ("reattached", "refused", "ambiguous")
        if needs_cost != (self.cost is not None):
            raise ValueError(f"an event of kind {self.kind!r} {'needs' if needs_cost else 'has no'} cost")
        if (self.kind == "refused") != (self.reason is not None):
            raise ValueError(f"an event of kind {self.kind!r} {'needs' if self.kind == 'refused' else 'has no'} reason")
        return self


class TrackSelectionMeta(FrozenModel):
    """How the target was chosen (``taiji_ai.track.target.TargetSelection``)."""

    method: Literal["default", "user_box"]
    ambiguous: StrictBool  # the default choice was a close call
    frame_pos: NonNegInt
    frame_index: NonNegInt  # row of the frame in pts.parquet
    t_sec: Seconds
    track_id: NonNegInt  # the track of the chosen person


class TargetStateParamsMeta(FrozenModel):
    """The parameters of ``resolve_target`` (``taiji_ai.track.state.TargetStateParams``)."""

    max_lost_s: NonNeg  # [s]
    reattach_cost: OpenUnit
    max_reattach_s: NonNeg  # [s]
    ambiguity_ratio: OpenUnit

    @model_validator(mode="after")
    def _reattach_is_not_shorter_than_lost(self) -> Self:
        if self.max_reattach_s < self.max_lost_s:
            raise ValueError("max_reattach_s must not be shorter than max_lost_s")
        return self


class AssociationParamsMeta(FrozenModel):
    """The parameters the tracks were made with (``taiji_ai.track.associate.AssociationParams``)."""

    w_iou: NonNeg
    w_kp: NonNeg
    max_cost: OpenUnit
    max_gap_s: NonNeg  # [s]
    min_common_keypoints: Annotated[int, Field(strict=True, ge=1, le=26)]


class TrackCounts(FrozenModel):
    """Deterministic counts; they must agree with the rows and the events."""

    n_frames: PosInt
    n_in_segment: NonNegInt
    n_tracked: NonNegInt
    n_lost: NonNegInt
    n_target_lost: NonNegInt
    n_before_target: NonNegInt
    n_reattached: NonNegInt
    n_refused: NonNegInt
    n_ambiguous: NonNegInt

    @model_validator(mode="after")
    def _statuses_add_up(self) -> Self:
        if self.n_in_segment > self.n_frames:
            raise ValueError("n_in_segment is larger than n_frames")
        if self.n_tracked + self.n_lost + self.n_target_lost + self.n_before_target != self.n_frames:
            raise ValueError("n_tracked + n_lost + n_target_lost + n_before_target must equal n_frames")
        return self


class TrackMeta(Manifest):
    """The metadata JSON of ``track.parquet``."""

    schema_version: Literal["track/1"]
    skeleton: str  # "halpe26/1"; the reader compares it with ``taiji_ai.pose.skeleton.SKELETON_ID``
    recording_id: str = Field(pattern=UUID4_RE)
    image_size: tuple[PosInt, PosInt]  # (width, height) [px] of the upright image the coordinates refer to
    segment_s: tuple[Seconds, Seconds]  # [s] the segment asked for (start, end)
    selection: TrackSelectionMeta
    params: TargetStateParamsMeta
    association: AssociationParamsMeta
    counts: TrackCounts
    needs_reselect: StrictBool  # the user has to choose the performer again (P8 shows it)
    reselect_reason: ReselectReason | None  # why; None exactly when ``needs_reselect`` is false
    events: tuple[TrackEvent, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not self.segment_s[0] < self.segment_s[1]:
            raise ValueError("segment_s must have start < end")
        if self.needs_reselect != (self.reselect_reason is not None):
            raise ValueError("reselect_reason must be given exactly when needs_reselect is true")
        n = self.counts.n_frames
        if self.selection.frame_pos >= n:
            raise ValueError(f"selection.frame_pos {self.selection.frame_pos} is outside the {n} frames")
        previous = -1
        for event in self.events:
            if event.frame_pos >= n:
                raise ValueError(f"events: frame_pos {event.frame_pos} is outside the {n} frames")
            if event.frame_pos < previous:
                raise ValueError("events: the events must be in time order")
            previous = event.frame_pos
        for kind, count_name in (
            ("reattached", "n_reattached"),
            ("refused", "n_refused"),
            ("ambiguous", "n_ambiguous"),
        ):
            listed = sum(event.kind == kind for event in self.events)
            if listed != getattr(self.counts, count_name):
                raise ValueError(
                    f"{count_name} is {getattr(self.counts, count_name)} but the events list {listed} of kind {kind}"
                )
        return self
