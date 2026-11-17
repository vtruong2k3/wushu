"""``quality.json`` of a run (schema ``quality/1``, P4.07): what the quality layer kept and why it dropped the rest.

The report holds **counts** with their denominators, times, names of joints, intervals and reasons, the parameters the
stages used and the warnings of the run. It holds no keypoint value, no person's name, no file name and no path
(AGENTS.md section 5.9). No coverage is judged here: "too low" is a limit of a metric (AGENTS.md section 5.5); the three
ratios of v3 section 8.3 are divisions of two numbers of this file.

Each interval (the segment first, then the named intervals of the caller) is counted on two lattices:

* the **grid** (``rows``, ``cells``): cells, reasons, frames and the filter flags, read from the final layer. For a
  clip with a constant frame rate the grid is the rows of the video; otherwise it is the regular grid of the resampling
  stage and ``mixed_rows`` says how many of its rows are linear mixes and not measurements;
* the **source rows** (``source_rows``): the gap table and the swap flag, which belong to the rows of the video.

A cell of the final layer is exactly one of **observed** (a measurement, or a mix of two when its row is ``mixed``),
**bridged** (a short gap that the gap layer filled, flagged) or **missing** (NaN). ``unobserved_by_reason`` counts
every cell whose reason is not ``ok`` (bridged cells included, because they keep it), ``missing_by_reason`` the NaN
cells; so ``observed + bridged + missing = cells``, ``missing_by_reason`` adds up to ``missing`` and
``unobserved_by_reason`` to ``bridged + missing``. The validators below check these sums, so a file that disagrees with
itself is refused. An unknown value is ``null``, never 0 or an invented number.

Warnings have a fixed form: ``lr_swap_suspect@12.40-12.73`` (seconds of the first and last row of a run of rows with a
cell the swap flag blocks; ``@12.40`` for one row), ``torso_unmeasured``, ``grid_resampled``,
``filter_skipped_above_nyquist``.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from taiji_ai.pose.skeleton import JOINTS, NUM_JOINTS
from taiji_ai.schemas._base import FrozenModel, Manifest, NonNeg, NonNegInt, PosInt, Positive, Seconds

SEGMENT_NAME = "segment"  # the name of the first interval; a caller's interval may not use it
INTERVAL_NAME_RE = r"^[A-Za-z0-9_.-]{1,64}$"  # no free text in a file that is logged and shared
WARNING_RE = (
    r"^(lr_swap_suspect@-?\d+\.\d{2}(--?\d+\.\d{2})?|torso_unmeasured|grid_resampled|filter_skipped_above_nyquist)$"
)

StrictBool = Annotated[bool, Field(strict=True)]
Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]  # [0, 1]
OpenUnit = Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]  # (0, 1]
JointIndex = Annotated[int, Field(strict=True, ge=0, le=NUM_JOINTS - 1)]
ReasonCode = Annotated[int, Field(strict=True, ge=0, le=255)]
_RATE_TOL = 1e-6  # sampling_hz * step_s is 1 up to this


class ReasonCounts(FrozenModel):
    """One count per reason a cell has no measurement (``quality.mask.REASON_NAMES`` without ``ok``).

    A new reason code is a new field here and a new schema version; a test ties the two together.
    """

    low_conf: NonNegInt
    non_finite: NonNegInt
    not_tracked: NonNegInt
    frame_invalid: NonNegInt
    outlier: NonNegInt
    no_frame: NonNegInt

    def total(self) -> int:
        return sum(self.model_dump().values())


class OutcomeCounts(FrozenModel):
    """One count per outcome of a gap (``quality.gaps.OUTCOME_NAMES``)."""

    filled: NonNegInt
    too_long: NonNegInt
    never_fill: NonNegInt
    blocked: NonNegInt
    open_start: NonNegInt
    open_end: NonNegInt
    open_both: NonNegInt

    def total(self) -> int:
        return sum(self.model_dump().values())


class GapCounts(FrozenModel):
    """The gaps of the source rows by outcome: how many touch the interval, and how many of their cells lie in it."""

    gaps: OutcomeCounts
    cells: OutcomeCounts

    @model_validator(mode="after")
    def _a_gap_has_a_cell_in_the_interval(self) -> Self:
        gaps, cells = self.gaps.model_dump(), self.cells.model_dump()
        for name, n_gaps in gaps.items():
            if n_gaps > cells[name]:
                raise ValueError(f"gaps: {name} has more gaps ({n_gaps}) than cells ({cells[name]})")
            if cells[name] > 0 and n_gaps == 0:
                raise ValueError(f"gaps: {name} has cells but no gap")
        return self


class JointCoverage(FrozenModel):
    """The counts of one joint over the rows of an interval (the sum over joints is the interval's count)."""

    joint: str  # the name in halpe26/1
    observed: NonNegInt
    bridged: NonNegInt
    missing: NonNegInt
    missing_by_reason: ReasonCounts
    filtered: NonNegInt  # cells whose value comes from the low-pass filter
    suspect: NonNegInt  # cells of the swap flag (source rows)
    blocked: NonNegInt

    @model_validator(mode="after")
    def _own_sums(self) -> Self:
        if self.joint not in JOINTS:
            raise ValueError(f"joint {self.joint!r} is not a joint of halpe26/1")
        if self.missing_by_reason.total() != self.missing:
            raise ValueError(f"joint {self.joint}: missing_by_reason must add up to missing")
        if self.filtered > self.observed + self.bridged:
            raise ValueError(f"joint {self.joint}: filtered must not exceed observed + bridged")
        if self.suspect > self.blocked:
            raise ValueError(f"joint {self.joint}: suspect must not exceed blocked")
        return self


class IntervalCoverage(FrozenModel):
    """The counts of one interval; see the module docstring for the lattices and the sums."""

    name: str = Field(pattern=INTERVAL_NAME_RE)
    t_start: Seconds | None  # [s]; for the segment the first row with ``in_segment``, null when there is none
    t_end: Seconds | None  # [s]; the last such row (the segment, closed) or the end of the interval (half-open)
    rows: NonNegInt  # grid rows in the interval
    source_rows: NonNegInt  # rows of the video in the interval (the denominator of the gap and swap counts)
    duration_s: NonNeg | None  # rows x the step of the grid [s]; null for one row (no step is known)
    usable_frames: NonNegInt  # rows with at least the essential share of joints having a value
    not_tracked_frames: NonNegInt  # rows whose 26 cells are all ``not_tracked``
    cells: NonNegInt  # rows x 26
    observed: NonNegInt
    bridged: NonNegInt
    missing: NonNegInt
    unobserved_by_reason: ReasonCounts
    missing_by_reason: ReasonCounts
    gaps: GapCounts
    filtered: NonNegInt  # cells with a value that come from the low-pass filter
    unfiltered: NonNegInt  # cells with a value that do not (a run too short, a clip too slow)
    suspect: NonNegInt  # cells of the swap flag, over the source rows
    blocked: NonNegInt
    mixed_rows: NonNegInt  # grid rows that are linear mixes of two rows of the video
    joints: tuple[JointCoverage, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.t_start is None) != (self.t_end is None):
            raise ValueError("t_start and t_end must both be given or both be null")
        if self.t_start is not None and self.t_end is not None and self.t_start > self.t_end:
            raise ValueError("t_start must not be after t_end")
        if self.cells != self.rows * NUM_JOINTS:
            raise ValueError(f"cells must be rows * {NUM_JOINTS}")
        if self.observed + self.bridged + self.missing != self.cells:
            raise ValueError("observed + bridged + missing must equal cells")
        if self.missing_by_reason.total() != self.missing:
            raise ValueError("missing_by_reason must add up to missing")
        if self.unobserved_by_reason.total() != self.bridged + self.missing:
            raise ValueError("unobserved_by_reason must add up to bridged + missing")
        unobserved, missing = self.unobserved_by_reason.model_dump(), self.missing_by_reason.model_dump()
        for reason, n_missing in missing.items():
            if unobserved[reason] < n_missing:
                raise ValueError(f"unobserved_by_reason is below missing_by_reason for {reason}")
        if self.filtered + self.unfiltered != self.observed + self.bridged:
            raise ValueError("filtered + unfiltered must equal observed + bridged")
        if self.usable_frames + self.not_tracked_frames > self.rows:
            raise ValueError("usable_frames + not_tracked_frames must not exceed rows")
        if self.mixed_rows > self.rows:
            raise ValueError("mixed_rows must not exceed rows")
        if self.suspect > self.blocked:
            raise ValueError("suspect must not exceed blocked")
        if self.blocked > self.source_rows * NUM_JOINTS:
            raise ValueError(f"blocked must not exceed source_rows * {NUM_JOINTS}")
        if self.gaps.cells.total() > self.source_rows * NUM_JOINTS:
            raise ValueError(f"gaps.cells add up to more than source_rows * {NUM_JOINTS}")
        self._joints_agree()
        return self

    def _joints_agree(self) -> None:
        if tuple(j.joint for j in self.joints) != JOINTS:
            raise ValueError("joints must be the 26 joints of halpe26/1, in order")
        for j in self.joints:
            if j.observed + j.bridged + j.missing != self.rows:
                raise ValueError(f"joint {j.joint}: observed + bridged + missing must equal rows")
            if j.blocked > self.source_rows:
                raise ValueError(f"joint {j.joint}: blocked must not exceed source_rows")
        for key in ("observed", "bridged", "missing", "filtered", "suspect", "blocked"):
            if sum(getattr(j, key) for j in self.joints) != getattr(self, key):
                raise ValueError(f"the joints do not add up to {key}")
        for reason, n_missing in self.missing_by_reason.model_dump().items():
            if sum(getattr(j.missing_by_reason, reason) for j in self.joints) != n_missing:
                raise ValueError(f"the joints do not add up to missing_by_reason {reason}")


class Timeline(FrozenModel):
    """The clock of the run: the rows of the video, the grid the layers live on, and the scale."""

    rows: NonNegInt  # rows of the video (the target track)
    grid_rows: NonNegInt  # rows of the final layer
    resampled: StrictBool  # the timeline was not uniform: the grid is not the rows (W6 manifest entry)
    step_s: Positive | None  # [s] the interval of the grid; null for fewer than two rows
    sampling_hz: Positive | None  # [Hz] 1 / step_s
    torso_px: Positive | None  # [px] median torso length of the mask layer; null when it could not be measured

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not self.resampled and self.grid_rows != self.rows:
            raise ValueError("grid_rows must equal rows when the timeline was not resampled")
        if (self.step_s is None) != (self.sampling_hz is None):
            raise ValueError("step_s and sampling_hz must both be given or both be null")
        if self.step_s is not None and self.sampling_hz is not None:
            if not math.isclose(self.sampling_hz * self.step_s, 1.0, rel_tol=_RATE_TOL):
                raise ValueError("sampling_hz must be 1 / step_s")
        return self


class MaskParamsRecord(FrozenModel):
    tau_kp: Unit  # a score under this is not observed
    essential: tuple[JointIndex, ...]  # joint indices (halpe26/1) of the frame rule
    min_essential_fraction: OpenUnit


class SwapParamsRecord(FrozenModel):
    min_jump: Positive  # [torso]
    max_cross_ratio: OpenUnit
    max_dt_s: Positive  # [s]
    max_swap_s: Positive  # [s]
    pairs: tuple[tuple[JointIndex, JointIndex], ...]


class HampelParamsRecord(FrozenModel):
    window: PosInt
    n_sigma: Positive
    min_observed: PosInt
    max_half_span_s: Positive  # [s]
    scale_floor_px: NonNeg  # [px] the floor that was used (a share of the torso when ``floor_fraction`` is given)
    floor_fraction: NonNeg | None  # as asked for: the floor is this share of the torso; null: the floor is fixed


class GapParamsRecord(FrozenModel):
    max_gap_s: Positive  # [s]
    never_fill: tuple[ReasonCode, ...]  # reason codes that are never bridged


class ResampleParamsRecord(FrozenModel):
    grid_hz: Positive | None
    max_step_s: Positive  # [s]
    uniform_tol_s: NonNeg  # [s]


class FilterParamsRecord(FrozenModel):
    cutoff_hz: Positive  # [Hz]
    order: PosInt
    padlen: NonNegInt | None


class QualityParamsRecord(FrozenModel):
    """The parameters of the stages as they were used (data-validity parameters, not thresholds on a movement)."""

    mask: MaskParamsRecord
    swap: SwapParamsRecord
    hampel: HampelParamsRecord
    gaps: GapParamsRecord
    resample: ResampleParamsRecord
    filter: FilterParamsRecord


class QualityReport(Manifest):
    """The content of ``quality.json``."""

    schema_version: Literal["quality/1"]
    skeleton: Literal["halpe26/1"]  # the reader compares it with ``taiji_ai.pose.skeleton.SKELETON_ID``
    params: QualityParamsRecord
    timeline: Timeline
    intervals: tuple[IntervalCoverage, ...] = Field(min_length=1)  # the segment first, then the caller's intervals
    warnings: tuple[Annotated[str, Field(pattern=WARNING_RE)], ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        names = [iv.name for iv in self.intervals]
        if names[0] != SEGMENT_NAME:
            raise ValueError(f"the first interval must be named {SEGMENT_NAME!r}")
        if len(set(names)) != len(names):
            raise ValueError("interval names must be distinct")
        for iv in self.intervals:
            if iv.rows > self.timeline.grid_rows:
                raise ValueError(f"interval {iv.name!r} has more rows than the grid rows ({self.timeline.grid_rows})")
            if iv.source_rows > self.timeline.rows:
                raise ValueError(f"interval {iv.name!r} has more source rows than the timeline ({self.timeline.rows})")
        return self
