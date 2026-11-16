"""``sync.json`` (``sync/1``): how the timeline of camera B maps onto camera A's (P2.01).

Convention (this fixes the undefined ``t0`` of W2 in TECH_WORKFLOW)
-------------------------------------------------------------------
Times are seconds on each camera's own **video** timeline (``io.frames``: seconds from the first presentation
timestamp). Camera A is the reference (``cam_a`` sorts before ``cam_b``). For a moment seen by camera A at ``t_a``::

    t_b = t_a + offset_s + drift * (t_a - t_ref_s)

``t_ref_s`` is the time on camera A of the matched claps in the start window (where the matched evidence is, not the
centre of the search window; BUG-0059); ``drift`` is dimensionless (the rate of B's timeline
per second of A's, minus 1; 1e-4 is 100 ppm). ``offset_s > 0`` means B shows the same moment later on its own timeline.
``b_to_a`` is the exact inverse: ``t_a = (t_b - offset_s + drift * t_ref_s) / (1 + drift)``.

Unknown values are ``None``, never 0 (AGENTS.md section 5.1): ``status`` is ``ok`` only when the sound signal was
matched at the start and at the end; ``start_only`` leaves ``drift`` unknown; ``not_found`` leaves the offset unknown
too. A time mapping exists only for ``ok`` (``SyncUnavailable`` otherwise): with an unknown drift it would silently
assume 0.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self, TypeVar

import numpy as np
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator

from taiji_ai.schemas._base import (
    CAMERA_RE,
    TAKE_RE,
    UUID4_RE,
    FrozenModel,
    Manifest,
    NonNeg,
    Positive,
    Seconds,
    ToolVersions,
)

# Two cameras are combined in metrics only if the flash check, at the start and at the end, differs by at most one
# frame (P2.06, DEC-0025).
MAX_RESIDUAL_FRAMES = 1.0

Correlation = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Ratio = Annotated[float, Field(ge=1, allow_inf_nan=False)]
Drift = Annotated[float, Field(gt=-1, lt=1, allow_inf_nan=False)]

_T = TypeVar("_T", float, np.ndarray)


class SyncUnavailable(ValueError):
    """There is no time mapping for this take (status is not ``ok``)."""


class SyncWindow(FrozenModel):
    """The result of matching the sound signal in one window of camera A against camera B."""

    window_a_s: tuple[Seconds, Seconds]  # [t0, t1] on camera A's video timeline
    lag_s: Seconds | None  # B minus A, in seconds, at this window; None when not found
    peak: Correlation | None  # normalised correlation of the best match
    peak_ratio: Ratio | None  # best peak over the second best
    found: StrictBool

    @field_validator("window_a_s")
    @classmethod
    def _window_is_ordered(cls, v: tuple[float, float]) -> tuple[float, float]:
        if not (0 <= v[0] < v[1]):
            raise ValueError("window_a_s must satisfy 0 <= t0 < t1")
        return v

    @model_validator(mode="after")
    def _found_matches_values(self) -> Self:
        if self.found and (self.lag_s is None or self.peak is None or self.peak_ratio is None):
            raise ValueError("found is true, so lag_s, peak and peak_ratio are required")
        if not self.found and self.lag_s is not None:
            raise ValueError("found is false, so lag_s must be null (no offset is made up)")
        return self


class SyncValidation(FrozenModel):
    """Independent check of the sound result with the visible flash (P2.05)."""

    method: Literal["flash", "none"]
    flash_a_s: tuple[Seconds, ...]  # flash onsets seen by camera A, on its timeline
    flash_b_s: tuple[Seconds, ...]  # flash onsets seen by camera B, on its timeline
    residual_start_ms: NonNeg | None  # |t_b - a_to_b(t_a)| at the start flash [ms]
    residual_end_ms: NonNeg | None  # same at the end flash [ms]
    residual_ms: NonNeg | None  # the larger of the two [ms]
    residual_frames: NonNeg | None  # residual_ms in frames of the slower camera
    frame_dt_s: Positive | None  # that camera's median frame interval [s]

    @model_validator(mode="after")
    def _numbers_match_the_method(self) -> Self:
        values = (
            self.residual_start_ms,
            self.residual_end_ms,
            self.residual_ms,
            self.residual_frames,
            self.frame_dt_s,
        )
        if self.method == "none":
            if any(v is not None for v in values):
                raise ValueError("validation method is none, so every residual and frame_dt_s must be null")
            return self
        ends = [v for v in (self.residual_start_ms, self.residual_end_ms) if v is not None]
        if not ends or self.residual_ms is None or self.residual_frames is None or self.frame_dt_s is None:
            raise ValueError(
                "validation method is flash: at least one end, residual_ms, residual_frames and frame_dt_s are required"
            )
        if not math.isclose(self.residual_ms, max(ends), rel_tol=1e-6, abs_tol=1e-9):
            raise ValueError("residual_ms must be the larger of residual_start_ms and residual_end_ms")
        if not math.isclose(
            self.residual_frames, self.residual_ms / 1000.0 / self.frame_dt_s, rel_tol=1e-6, abs_tol=1e-9
        ):
            raise ValueError("residual_frames must equal residual_ms / 1000 / frame_dt_s")
        return self


class SyncManifest(Manifest):
    """``data/takes/<take_id>/sync.json``: one per take and camera pair."""

    schema_version: Literal["sync/1"]
    take_id: str = Field(pattern=TAKE_RE)
    cam_a: str = Field(pattern=CAMERA_RE)  # the reference camera
    cam_b: str = Field(pattern=CAMERA_RE)
    recording_id_a: str = Field(pattern=UUID4_RE)
    recording_id_b: str = Field(pattern=UUID4_RE)

    method: Literal["audio_xcorr/1"]
    params: dict[str, float | int | str]  # sample rate, envelope cut-offs, window lengths, maximum lag, minimum peaks
    start: SyncWindow
    end: SyncWindow

    status: Literal["ok", "start_only", "not_found"]
    not_found_reason: Literal["no_audio", "clap_not_found"] | None
    offset_s: Seconds | None  # [s] at t_ref_s
    drift: Drift | None  # dimensionless
    t_ref_s: Seconds | None  # [s] on camera A's timeline

    validation: SyncValidation
    usable_for_metrics: StrictBool
    usable_reason: Literal[
        "usable", "no_audio", "audio_not_found", "start_only", "flash_not_found", "residual_too_large"
    ]

    created_at: AwareDatetime
    tools: ToolVersions

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        problems: list[str] = []
        if not self.cam_a < self.cam_b:
            problems.append("cam_a must sort before cam_b")
        if self.recording_id_a == self.recording_id_b:
            problems.append("recording_id_a and recording_id_b must differ")

        expected = "ok" if self.start.found and self.end.found else "start_only" if self.start.found else "not_found"
        if self.status != expected:
            problems.append(f"status is {self.status!r} but the windows give {expected!r}")

        offset_known = self.status in ("ok", "start_only")
        for name, value, needed in (
            ("offset_s", self.offset_s, offset_known),
            ("t_ref_s", self.t_ref_s, offset_known),
            ("drift", self.drift, self.status == "ok"),
            ("not_found_reason", self.not_found_reason, self.status == "not_found"),
        ):
            if needed and value is None:
                problems.append(f"{name} is required when status is {self.status!r}")
            if not needed and value is not None:
                problems.append(f"{name} must be null when status is {self.status!r}")

        if self.usable_for_metrics != (self.usable_reason == "usable"):
            problems.append("usable_reason is 'usable' exactly when usable_for_metrics is true")
        if self.usable_for_metrics:
            if self.status != "ok":
                problems.append("usable_for_metrics needs status 'ok'")
            v = self.validation
            if v.method != "flash":
                problems.append("usable_for_metrics needs a flash validation")
            elif v.residual_start_ms is None or v.residual_end_ms is None:
                problems.append("usable_for_metrics needs the flash residual at both the start and the end")
            elif v.residual_frames is None or v.residual_frames > MAX_RESIDUAL_FRAMES:
                problems.append(f"usable_for_metrics needs a flash residual of at most {MAX_RESIDUAL_FRAMES} frame")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _mapping(self) -> tuple[float, float, float]:
        if self.status != "ok" or self.offset_s is None or self.drift is None or self.t_ref_s is None:
            raise SyncUnavailable(f"no time mapping: status is {self.status!r}; both ends must be matched")
        return self.offset_s, self.drift, self.t_ref_s

    def a_to_b(self, t: _T) -> _T:
        """Camera A's video time (seconds) to camera B's video time. Accepts a float or a numpy array."""
        offset, drift, ref = self._mapping()
        return t + offset + drift * (t - ref)

    def b_to_a(self, t: _T) -> _T:
        """Exact inverse of :meth:`a_to_b`."""
        offset, drift, ref = self._mapping()
        return (t - offset + drift * ref) / (1.0 + drift)

    def to_db_row(self) -> dict[str, object] | None:
        """Values of one ``sync`` row (migration 0001). None when status is not 'ok'.

        The caller writes the row only for a usable take (DEC-0035, BUG-0065).
        """
        if self.status != "ok" or self.offset_s is None or self.drift is None:
            return None
        return {
            "take_id": self.take_id,
            "cam_a": self.cam_a,
            "cam_b": self.cam_b,
            "offset_s": float(self.offset_s),
            "drift": float(self.drift),
            "residual_ms": float(self.validation.residual_ms) if self.validation.residual_ms is not None else None,
            "method": self.method,
            "validated_by": self.validation.method if self.validation.method == "flash" else None,
            "created_at": self.created_at.isoformat(),
        }
