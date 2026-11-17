"""Models of a metric result (W7, P5.01): what a metric says, where it holds, how much it covers and why the rest is
missing.

A metric (hip height, trunk lean, tempo) is a **series** (one value per grid row of the final layer inside the
segment, ``taiji_ai.metrics.series.MetricSeries``) and a **summary** (``MetricSummary``: the numbers and events drawn
from it, the entry of ``metric_summary.json``). Both share ``MetricHeader``: name and version, units, the valid
intervals, the coverage and the reasons why rows are missing. Positions are image pixels (y down) and times seconds
from the stream start, as everywhere (AGENTS.md section 5.4); the values of a metric are in the units the header
names.

**Reasons** (``MissingReason``, a closed list). A row of a series is *measured* (code 0) or it has one reason: codes 1
to 6 are the six reasons of the quality layer with the same numbers (the first unusable joint the metric needs); 16 to
18 say that the row is *not eligible* (outside the interval the coach chose, a view the metric does not support, an
interval flag); 19 to 22 that the pose is good but the metric could not be computed (no scale, no reference, a run
that is too short, the edge of a run). Adding a reason bumps the version.

**Coverage** (v3 section 8.3) is counts of rows with one nesting, ``measured <= quality <= eligible <= total``: a row
with a reason of 16 to 18 is not eligible; of 1 to 6 it is eligible but the pose is not good enough; of 19 to 22 the
pose is good but nothing was measured. So the three ratios are ``eligible / total`` (time that is fit to measure),
``quality / eligible`` (good pose in that time) and ``measured / total`` (time that gave a metric), and the counts of
the reasons add up to ``total - measured``. The model keeps the counts and ``step_s`` (seconds = rows x ``step_s``, as
in ``quality.json``); a ratio is ``None`` at a zero denominator, never 0 and never NaN. The validators check these
sums, so a file that disagrees with itself is refused.

**Evidence and conclusion** (AGENTS.md section 5.5). ``insufficient_evidence`` has no number (every statistic is null,
never 0), no event, and a reason. A metric without a signed ``metric_record`` is ``experimental``: it shows its value
and ``conclusive`` is false. An output that depends on a threshold says so (``uses_threshold``) and the summary states
where the threshold came from: a signed record (needs ``enabled``) or an unsigned configuration (allowed only while
``experimental``, for the development of a metric and its ablation).

Headers hold no path, no file name and no person's name; ``data_sources`` is the provenance of AGENTS.md section 9.4.6
(an empty list means one of our own recordings). Floats are never NaN or infinite, so every file is valid JSON.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StrictInt, StringConstraints, model_validator

from taiji_ai.schemas._base import CAMERA_RE, UUID4_RE, FrozenModel, Manifest, NonNegInt, Positive, Seconds
from taiji_ai.schemas.quality_layers import DataSource

SCHEMA_VERSION = "metric_summary/1"
NAME_RE = r"^[a-z][a-z0-9_]{1,63}$"  # a metric or a statistic
VERSION_RE = r"^[1-9][0-9]{0,3}$"  # a positive integer as text: the key of ``metric_record`` is (name, version) as text
VIEW_RE = r"^[a-z_]{1,32}$"  # the ontology owns the valid views, not this file
PARAM_KEY_RE = r"^[a-z][a-z0-9_]{0,63}$"
PARAM_TEXT_RE = r"^[A-Za-z0-9_.-]{0,64}$"  # a short code, not free text and not a path
MAX_PARAMETERS = 32
_EPS_S = 1e-9  # an event at the very end of an interval is inside it

Unit = Literal["body_lengths", "body_lengths_per_s", "deg", "px", "s", "count", "ratio"]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]  # an int is a number; a string or a bool is not
ParamValue = Annotated[str, StringConstraints(pattern=PARAM_TEXT_RE)] | StrictBool | StrictInt | Number | None


class MissingReason(enum.IntEnum):
    """The code of a row of a series: 0 measured, else why not. 1 to 6 are those of ``quality.mask.REASON_NAMES``."""

    measured = 0
    low_conf = 1
    non_finite = 2
    not_tracked = 3
    frame_invalid = 4
    outlier = 5
    no_frame = 6
    outside_interval = 16
    view_not_supported = 17
    interval_flagged = 18
    scale_unavailable = 19
    reference_missing = 20
    too_short = 21
    run_edge = 22


R = MissingReason
ELIGIBILITY = (R.outside_interval, R.view_not_supported, R.interval_flagged)  # the row is not fit to measure
QUALITY = (
    R.low_conf,
    R.non_finite,
    R.not_tracked,
    R.frame_invalid,
    R.outlier,
    R.no_frame,
)  # the pose is not good enough
AFTER_QUALITY = (R.scale_unavailable, R.reference_missing, R.too_short, R.run_edge)  # good pose, not measured
InsufficientReason = Literal[
    "low_conf", "non_finite", "not_tracked", "frame_invalid", "outlier", "no_frame", "outside_interval",
    "view_not_supported", "interval_flagged", "scale_unavailable", "reference_missing", "too_short", "run_edge",
]  # fmt: skip


class Interval(FrozenModel):
    """``[t_start, t_end)`` in seconds from the stream start: a run of measured rows and the step after its last."""

    t_start: Seconds
    t_end: Seconds

    @model_validator(mode="after")
    def _forward(self) -> Self:
        if not self.t_start < self.t_end:
            raise ValueError("t_start must be below t_end")
        return self


class MissingCounts(FrozenModel):
    """Rows that are not measured, by reason (a field for each reason: a typo cannot make a new one)."""

    low_conf: NonNegInt
    non_finite: NonNegInt
    not_tracked: NonNegInt
    frame_invalid: NonNegInt
    outlier: NonNegInt
    no_frame: NonNegInt
    outside_interval: NonNegInt
    view_not_supported: NonNegInt
    interval_flagged: NonNegInt
    scale_unavailable: NonNegInt
    reference_missing: NonNegInt
    too_short: NonNegInt
    run_edge: NonNegInt

    def count(self, reasons: Sequence[MissingReason]) -> int:
        """The rows whose reason is one of ``reasons``."""
        return sum(getattr(self, reason.name) for reason in reasons)

    def total(self) -> int:
        return self.count([r for r in MissingReason if r != MissingReason.measured])


class Coverage(FrozenModel):
    """The three counts of v3 section 8.3, in grid rows: ``measured <= quality <= eligible <= total``."""

    total: NonNegInt  # rows of the segment
    eligible: NonNegInt  # rows whose view and interval are fit to measure
    quality: NonNegInt  # eligible rows with a pose good enough for the joints the metric needs
    measured: NonNegInt  # rows that gave a value

    @model_validator(mode="after")
    def _nested(self) -> Self:
        if not self.measured <= self.quality <= self.eligible <= self.total:
            raise ValueError("measured must not exceed quality, quality eligible, nor eligible total")
        return self

    def eligible_ratio(self) -> float | None:
        """Time fit to measure over the time of the segment; ``None`` for a segment of no row."""
        return None if self.total == 0 else self.eligible / self.total

    def quality_ratio(self) -> float | None:
        """Rows with a good pose over the eligible rows; ``None`` when no row is eligible."""
        return None if self.eligible == 0 else self.quality / self.eligible

    def measured_ratio(self) -> float | None:
        """Time that gave a metric over the time of the segment; ``None`` for a segment of no row."""
        return None if self.total == 0 else self.measured / self.total


def _distinct_sources(sources: tuple[DataSource, ...]) -> None:
    ids = [s.dataset_id for s in sources]
    if len(set(ids)) != len(ids):
        raise ValueError("data_sources must name each dataset once")


class MetricHeader(FrozenModel):
    """What every result of a metric says about itself; the arrays of a series add the rows."""

    metric_name: str = Field(
        pattern=NAME_RE
    )  # for example ``hip_height_a``: variants A and B are two metrics (DEC-0014)
    metric_version: str = Field(pattern=VERSION_RE)
    units: Unit  # of the values of the series
    recording_id: str = Field(pattern=UUID4_RE)
    camera_id: str = Field(pattern=CAMERA_RE)
    view_category: str = Field(pattern=VIEW_RE)
    step_s: Positive | None  # [s] the interval of the grid; null for fewer than two rows
    valid_intervals: tuple[Interval, ...]  # the runs of measured rows, ordered, with a hole between two of them
    coverage: Coverage
    missing_by_reason: MissingCounts
    parameters: dict[Annotated[str, StringConstraints(pattern=PARAM_KEY_RE)], ParamValue]  # as used, bounded
    data_sources: tuple[DataSource, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        cov, miss = self.coverage, self.missing_by_reason
        if (self.step_s is None) != (cov.total < 2):
            raise ValueError("step_s must be given for two rows or more and null for fewer")
        if cov.measured > 0 and self.step_s is None:
            raise ValueError("step_s is needed for a measured row: it gives its duration")
        if miss.total() != cov.total - cov.measured:
            raise ValueError("missing_by_reason must add up to coverage.total - coverage.measured")
        if (
            cov.eligible != cov.total - miss.count(ELIGIBILITY)
            or cov.quality != cov.eligible - miss.count(QUALITY)
            or cov.measured != cov.quality - miss.count(AFTER_QUALITY)
        ):
            raise ValueError("coverage does not agree with missing_by_reason (the classes of the reasons)")
        runs = self.valid_intervals
        if (len(runs) == 0) != (cov.measured == 0):
            raise ValueError("valid_intervals must be empty exactly when nothing was measured")
        if len(runs) > cov.measured:
            raise ValueError("valid_intervals has more intervals than measured rows")
        for i in range(len(runs) - 1):
            if not runs[i].t_end < runs[i + 1].t_start:
                raise ValueError(f"valid_intervals must be ordered with a hole between two (interval {i + 1})")
        if len(self.parameters) > MAX_PARAMETERS:
            raise ValueError(f"parameters has more than {MAX_PARAMETERS} entries")
        _distinct_sources(self.data_sources)
        return self

    def seconds(self, rows: int) -> float | None:
        """``rows`` of the grid as seconds (rows x ``step_s``); ``None`` when there is no step."""
        return None if self.step_s is None else rows * self.step_s


class Statistic(FrozenModel):
    """A number drawn from the series, in its own units; ``value`` is null when it could not be computed (never 0)."""

    name: str = Field(pattern=NAME_RE)
    value: Number | None
    units: Unit
    uses_threshold: StrictBool  # the number depends on a threshold (a pause count, a duration over an angle)


class MetricEvent(FrozenModel):
    """A moment or a stretch of the series: an extremum (an instant) or a pause (a stretch under a speed threshold)."""

    kind: Literal["max", "min", "pause"]
    t_start: Seconds  # [s] from the stream start
    t_end: Seconds
    value: Number | None  # the value at an extremum, null for a pause
    uses_threshold: StrictBool

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.kind == "pause":
            if not self.t_start < self.t_end:
                raise ValueError("a pause is a stretch: t_start must be below t_end")
            if not self.uses_threshold:
                raise ValueError("a pause is defined by thresholds: uses_threshold must be true")
        else:
            if self.t_start != self.t_end:
                raise ValueError("an extremum is an instant: t_start must equal t_end")
            if self.uses_threshold:
                raise ValueError("an extremum uses no threshold: uses_threshold must be false")
        return self


class MetricSummary(MetricHeader):
    """The entry of ``metric_summary.json`` for one metric: the header, the evidence and the numbers."""

    evidence: Literal["sufficient", "insufficient_evidence"]
    insufficient_reason: InsufficientReason | None  # why there is no evidence; null when it is sufficient
    record_status: Literal["experimental", "enabled", "retired"]  # the vocabulary of the table ``metric_record``
    record_version: str | None = Field(pattern=VERSION_RE)  # the signed record that enabled the metric
    threshold_source: Literal["signed_record", "unsigned_config"] | None
    statistics: tuple[Statistic, ...]
    events: tuple[MetricEvent, ...]

    @model_validator(mode="after")
    def _evidence(self) -> Self:
        numbers = [s for s in self.statistics if s.value is not None]
        if self.evidence == "insufficient_evidence":
            if self.insufficient_reason is None:
                raise ValueError("insufficient_reason must say why when the evidence is insufficient")
            if numbers:
                raise ValueError("evidence is insufficient_evidence: every statistic must be null (never 0)")
            if self.events:
                raise ValueError("evidence is insufficient_evidence: there must be no event")
        else:
            if self.insufficient_reason is not None:
                raise ValueError("insufficient_reason must be null when the evidence is sufficient")
            if not self.valid_intervals or not numbers:
                raise ValueError("evidence is sufficient: it needs a valid interval and a statistic with a value")
        return self

    @model_validator(mode="after")
    def _record(self) -> Self:
        if (self.record_status == "enabled") != (self.record_version is not None):
            raise ValueError("record_version is given exactly when record_status is enabled")
        uses = any(s.uses_threshold for s in self.statistics) or any(e.uses_threshold for e in self.events)
        if uses != (self.threshold_source is not None):
            raise ValueError("threshold_source must be given exactly when an output uses a threshold")
        if self.threshold_source == "signed_record" and self.record_status != "enabled":
            raise ValueError("threshold_source signed_record needs record_status enabled")
        if self.threshold_source == "unsigned_config" and self.record_status != "experimental":
            raise ValueError("threshold_source unsigned_config is allowed only while record_status is experimental")
        return self

    @model_validator(mode="after")
    def _outputs(self) -> Self:
        names = [s.name for s in self.statistics]
        if len(set(names)) != len(names):
            raise ValueError("statistics must have distinct names")
        for i, e in enumerate(self.events):
            inside = any(
                run.t_start - _EPS_S <= e.t_start and e.t_end <= run.t_end + _EPS_S for run in self.valid_intervals
            )
            if not inside:
                raise ValueError(f"events[{i}] lies outside the valid intervals")
        return self

    @property
    def conclusive(self) -> bool:
        """True only for a sufficient result of a metric whose signed record enabled it (AGENTS.md section 5.5)."""
        return self.evidence == "sufficient" and self.record_status == "enabled"


class MetricSummaryFile(Manifest):
    """``metric_summary.json`` of a run: the summaries of its metrics, for one recording and one camera."""

    schema_version: Literal["metric_summary/1"]
    metrics: tuple[MetricSummary, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        keys = [(m.metric_name, m.metric_version) for m in self.metrics]
        if len(set(keys)) != len(keys):
            raise ValueError("metrics must have distinct (metric_name, metric_version)")
        if len({m.recording_id for m in self.metrics}) != 1:
            raise ValueError("metrics must all be of one recording_id")
        if len({m.camera_id for m in self.metrics}) != 1:
            raise ValueError("metrics must all be of one camera_id")
        return self
