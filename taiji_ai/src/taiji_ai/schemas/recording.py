"""``recording.json`` (``recording/1``), ``proxy.json`` (``proxy/1``) and the input of ingest (P2.01).

Units and conventions
---------------------
* Times are seconds on the video timeline: ``t_sec = (pts - start_pts) * time_base``, from the first presentation
  timestamp of the video stream (``io.frames``). Frame rates are in hertz; sizes in pixels as coded
  (``display_rotation`` says how the picture is turned for display); ``size_bytes`` in bytes.
* An unknown value is ``None``: one frame has no interval, a container may give no duration or frame rate.
* No field holds a person's name, the phone's original file name or a path: the capture sheet keeps that mapping, and
  the stored file is always ``recordings/<recording_id>/source<source_ext>`` relative to the data folder.
* Write order (P2.02, P2.03): files first, ``recording.json`` / ``proxy.json`` last (AGENTS.md section 5.8).
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Self, get_args

from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator

from taiji_ai.schemas._base import (
    CAMERA_RE,
    CONSENT_RE,
    PARTICIPANT_RE,
    SESSION_RE,
    SHA256_RE,
    TAKE_RE,
    UUID4_RE,
    FrozenModel,
    Manifest,
    NonNeg,
    NonNegInt,
    PosInt,
    Positive,
    Seconds,
    ToolVersions,
)

PROXY_MAX_DT_FRAMES = 1.0  # a proxy frame may differ from its source frame by at most one frame (P2.03, T-IO-10)

_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\)")

OpenUnit = Annotated[float, Field(gt=0, lt=1, allow_inf_nan=False)]  # 0 < x < 1
HalfOpenUnit = Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)]  # 0 <= x < 1
Ticks = Annotated[int, Field(strict=True)]  # a timestamp in time-base ticks; may be negative
Points = Annotated[int, Field(strict=True, ge=1)]  # a clip with fewer than 10 frames is compared at every frame


class TakeIds(FrozenModel):
    """The identifiers of one recording; ``take_id`` is the same for both cameras of a take."""

    participant_id: str = Field(pattern=PARTICIPANT_RE)
    session_id: str = Field(pattern=SESSION_RE)
    take_id: str = Field(pattern=TAKE_RE)
    camera_id: str = Field(pattern=CAMERA_RE)

    @model_validator(mode="after")
    def _take_id_matches_session_and_participant(self) -> Self:
        prefix = f"{self.session_id}-{self.participant_id}-T"
        if not self.take_id.startswith(prefix):
            raise ValueError(f"take_id {self.take_id!r} must start with {prefix!r} (session_id and participant_id)")
        return self


CameraRole = Literal["main_axis", "side_left", "side_right"]
CAMERA_ROLES: tuple[str, ...] = get_args(CameraRole)


class CaptureInfo(FrozenModel):
    """How the camera was set up, from the capture sheet (structured values only, no free text)."""

    camera_role: CameraRole
    height_m: Positive | None = None  # camera height [m]
    distance_m: Positive | None = None  # distance from the camera to the centre of the capture area [m]
    fps_setting: Positive | None = None  # frame rate set in the app [Hz]


class IngestMeta(TakeIds):
    """The input of ``ingest_recording``. The consent reference is not here: it comes from the participant row."""

    capture: CaptureInfo | None = None


class AudioInfo(FrozenModel):
    codec: str = Field(min_length=1)
    sample_rate: PosInt  # [Hz]
    channels: PosInt
    start_offset_s: Seconds  # audio start minus video start [s]


class VfrRule(FrozenModel):
    """The rule that decided ``vfr`` (BUG-0046).

    An interval deviates when it differs from the median by more than ``tick_tol`` ticks and by more than ``rel_tol`` of
    the median; ``vfr`` is true when more than ``max_share`` of the intervals deviate.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: PosInt
    rel_tol: OpenUnit
    tick_tol: NonNegInt
    max_share: HalfOpenUnit


class RecordingManifest(TakeIds, Manifest):
    """``data/recordings/<recording_id>/recording.json``."""

    schema_version: Literal["recording/1"]
    recording_id: str = Field(pattern=UUID4_RE)
    sha256: str = Field(pattern=SHA256_RE)  # of the stored source file
    consent_ref: str = Field(pattern=CONSENT_RE)  # copied from the participant row at ingest time

    source_ext: str = Field(pattern=r"^\.(mp4|mov|mkv)$")
    size_bytes: PosInt
    container: str = Field(min_length=1)  # ffprobe format_name
    codec: str = Field(min_length=1)

    width: PosInt  # [px, as coded]
    height: PosInt  # [px, as coded]
    display_rotation: Literal[0, 90, 180, 270]  # [deg] turn applied for display

    time_base: str = Field(pattern=r"^[1-9]\d*/[1-9]\d*$")  # video stream, seconds per tick
    start_pts: Ticks  # [ticks] of the first presentation timestamp
    n_frames: PosInt
    pts_span_s: NonNeg  # last minus first presentation timestamp [s]
    duration_s: NonNeg | None  # as given by the container [s]
    nominal_fps: Positive | None  # container average frame rate [Hz]
    r_frame_rate: Positive | None  # container base rate [Hz]
    measured_fps: Positive | None  # 1 / median interval [Hz]; None for one frame
    median_dt_s: Positive | None  # median interval between frames [s]; None for one frame
    dt_rel_std: NonNeg | None  # std / median of the intervals; None for one frame
    n_duplicate_pts: NonNegInt  # frames sharing a timestamp (counted, never dropped)
    vfr: StrictBool
    vfr_rule: VfrRule

    audio: AudioInfo | None
    capture: CaptureInfo | None
    ingested_at: AwareDatetime
    tools: ToolVersions

    @model_validator(mode="after")
    def _intervals_exist_only_with_two_frames(self) -> Self:
        problems = []
        if self.n_frames == 1:
            for name in ("median_dt_s", "measured_fps", "dt_rel_std"):
                if getattr(self, name) is not None:
                    problems.append(f"{name} must be null for one frame (there is no interval)")
            if self.pts_span_s != 0:
                problems.append("pts_span_s must be 0 for one frame")
        elif self.median_dt_s is None:
            problems.append("median_dt_s is required when n_frames is 2 or more")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def to_db_row(self) -> dict[str, object]:
        """The values of one ``recording`` row (migration 0001).

        ``source_path`` is relative to the data folder. ``duration_s`` is the container value, or the span plus one
        median interval when the container gives none, or ``None`` (one frame): never an invented 0.
        """
        if self.duration_s is not None:
            duration: float | None = self.duration_s
        elif self.median_dt_s is not None:
            duration = self.pts_span_s + self.median_dt_s
        else:
            duration = None
        return {
            "recording_id": self.recording_id,
            "participant_id": self.participant_id,
            "session_id": self.session_id,
            "take_id": self.take_id,
            "camera_id": self.camera_id,
            "sha256": self.sha256,
            "source_path": f"recordings/{self.recording_id}/source{self.source_ext}",
            "width": self.width,
            "height": self.height,
            "rotation": self.display_rotation,
            "nominal_fps": self.nominal_fps,
            "vfr": int(self.vfr),
            "duration_s": duration,
            "has_audio": int(self.audio is not None),
            "ingested_at": self.ingested_at.isoformat(),
        }


class ProxyCheck(FrozenModel):
    points: Points  # frames compared (evenly spaced, first and last included)
    max_abs_dt_s: NonNeg
    max_abs_dt_frames: NonNeg  # in source frames (median interval)
    passed: StrictBool


class ProxyManifest(Manifest):
    """``data/recordings/<recording_id>/proxy.json``: the browser copy and the result of its timestamp check."""

    schema_version: Literal["proxy/1"]
    recording_id: str = Field(pattern=UUID4_RE)
    source_sha256: str = Field(pattern=SHA256_RE)
    proxy_sha256: str = Field(pattern=SHA256_RE)
    height: PosInt  # [px] of the proxy, upright
    rotation_applied: Literal[0, 90, 180, 270]  # [deg] the source's display rotation, applied to the picture
    ffmpeg: str = Field(min_length=1)
    args: tuple[str, ...] = Field(min_length=1)  # arguments with placeholders, never a real path
    n_frames_source: PosInt
    n_frames_proxy: PosInt
    check: ProxyCheck

    @field_validator("args")
    @classmethod
    def _args_hold_no_absolute_path(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        bad = [a for a in v if _ABSOLUTE_PATH.match(a)]
        if bad:
            raise ValueError("args must not hold an absolute path (use placeholders)")
        return v

    @model_validator(mode="after")
    def _passed_needs_equal_counts_and_one_frame(self) -> Self:
        if self.check.passed:
            if self.n_frames_source != self.n_frames_proxy:
                raise ValueError("check.passed is true but the frame counts differ")
            if self.check.max_abs_dt_frames > PROXY_MAX_DT_FRAMES:
                raise ValueError(f"check.passed is true but max_abs_dt_frames exceeds {PROXY_MAX_DT_FRAMES}")
        return self
