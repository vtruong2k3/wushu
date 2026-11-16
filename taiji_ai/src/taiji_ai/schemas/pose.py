"""Header of ``pose_raw.npz`` (schema ``pose_raw/1``, P3.03).

The archive holds seven data arrays (documented in ``taiji_ai.pose.raw_io``), a 0-d text array ``schema_version`` and
a 0-d text array ``meta_json``: this model as JSON. Units and coordinates: image pixels of the upright image (display
rotation applied), x to the right, y down; times in seconds from the stream start. Floats are never NaN or infinite
(AGENTS.md section 6). The header has no path and no file name: the only identifier is the ``recording_id``. The wall
clock of a run is not here: it belongs to the run manifest (P7).
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from taiji_ai.schemas._base import SHA256_RE, UUID4_RE, FrozenModel, Manifest, NonNeg, PosInt, Seconds

NonNegInt = Annotated[int, Field(strict=True, ge=0)]
Fraction01 = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Sha256 = Annotated[str, StringConstraints(pattern=SHA256_RE)]


class PoseRunParamsMeta(FrozenModel):
    """The parameters of the run, as ``taiji_ai.pose.runner.PoseRunParams``."""

    detect_every_n: PosInt  # the detector runs on the first frame and every N frames
    bbox_margin: Fraction01  # widening of a box taken from keypoints, share of its width and height
    min_score: Fraction01  # a keypoint under this score is not valid
    min_valid_keypoints: Annotated[int, Field(strict=True, ge=1, le=26)]
    segment_margin_s: NonNeg  # [s] frames read before the start and after the end of the segment


class PoseRunCounts(FrozenModel):
    """Deterministic counts of the run; they must agree with the arrays."""

    n_frames: PosInt
    n_detector_calls: NonNegInt
    n_pose_calls: NonNegInt
    n_persons_total: NonNegInt


class PoseRawMeta(Manifest):
    """``meta_json`` of ``pose_raw.npz``."""

    schema_version: Literal["pose_raw/1"]
    skeleton: str  # "halpe26/1"; the reader compares it with ``taiji_ai.pose.skeleton.SKELETON_ID``
    recording_id: str = Field(pattern=UUID4_RE)
    image_size: tuple[PosInt, PosInt]  # (width, height) [px] of the upright image the coordinates refer to
    display_rotation: Literal[0, 90, 180, 270]  # [deg] applied before the model saw the frame
    segment_s: tuple[Seconds, Seconds]  # [s] the segment asked for (start, end)
    params: PoseRunParamsMeta
    model_fingerprint: dict[str, Sha256]  # model name -> sha256
    providers: dict[str, str]  # "det" / "pose" -> execution provider actually used
    counts: PoseRunCounts

    @field_validator("model_fingerprint", "providers")
    @classmethod
    def _not_empty(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("must name at least one entry")
        return value

    @model_validator(mode="after")
    def _segment_is_a_range(self) -> Self:
        if not self.segment_s[0] < self.segment_s[1]:
            raise ValueError("segment_s must have start < end")
        return self
