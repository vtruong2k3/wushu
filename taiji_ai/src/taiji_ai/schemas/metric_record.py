"""Model of a signed metric record (v3 section 8.2, P5.09): what a coach signs for a metric before a result of it may
draw a conclusion.

A record belongs to one metric (``metric_name``) and one version of that metric's code (``metric_version``) and has a
version of its own (``version``: new numbers are a new version, a record that is enabled never changes). Its numbers are
in the units of the metric (``units``; ``min_valid_duration_s`` in seconds): the *human variability* (how much two
coaches differ), the *smallest useful change* (what a coach wants to see move) and the *measurement error* of the
metric. Only an ``enabled`` record lets a result be ``conclusive`` (``MetricSummary.conclusive``, AGENTS.md section
5.5), and the gate G03 asks that its error is below the smallest useful change.

``parameters`` are the values the metric must be computed with for the record to apply: the thresholds the coach signed
(``pause_tau`` and ``pause_min_s`` of the speed metrics, always a pair), the arguments of the metric (``min_scale_s``,
``min_reference_s``...) and **the cut-off of the Butterworth filter** (``filter_cutoff_hz``): the error budget was
measured on a layer filtered at one cut-off, and ``tau``, ``d_min`` and the cut-off are one triple (DEC-0061). The
minimum valid duration is the column ``min_valid_duration_s`` and not a second parameter.

An ``enabled`` record is complete: a coach's signature (a role code, never a name), every number, a view, and the
cut-off. A draft (``experimental``) may be empty and unsigned; a *signed* ``experimental`` record is a decision to keep
the metric experimental (P10.06), and its error may be as large as the change (v3 8.2: then the scope or the capture
changes, not the threshold). A ``retired`` record says who retired it and when. The time of signing is checked against
the clock by the store, not here, so the model is the same on every day.

The model holds no path, no person's name and no free text but the coach's one sentence about the metric
(``intended_use``), which is never logged.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Literal, Self, cast

from pydantic import Field, StringConstraints, field_validator, model_validator

from taiji_ai.schemas._base import FrozenModel
from taiji_ai.schemas.metric import MAX_PARAMETERS, NAME_RE, PARAM_KEY_RE, VERSION_RE, ParamValue, Unit
from taiji_ai.schemas.quality_layers import DataSource

MAX_INTENDED_USE: Final = 500
GOLD_RE: Final = r"^[A-Za-z0-9_.-]{1,64}$"  # a short code (a report or a task ID), not a path
SIGNER_RE: Final = r"^cli:H\d{0,2}$"  # a coach's role code (AGENTS.md 5.12: thresholds need the coach), never a name
CUTOFF_KEY: Final = "filter_cutoff_hz"
PAUSE_KEYS: Final = ("pause_tau", "pause_min_s")
MINIMUM_KEY: Final = "min_valid_s"  # the argument that the column ``min_valid_duration_s`` binds

RecordStatus = Literal["experimental", "enabled", "retired"]  # the vocabulary of the table ``metric_record``
RecordView = Literal["front", "side", "oblique", "back"]  # the categories of ontology_v0 a metric can be signed for
NonNegNumber = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0)]
PositiveNumber = Annotated[float, Field(strict=True, allow_inf_nan=False, gt=0)]

_REQUIRED_WHEN_ENABLED: Final = (
    "gold_reference",
    "human_variability",
    "smallest_useful_change",
    "measurement_error",
    "min_valid_duration_s",
    "signed_by",
    "signed_at",
)


def _positive(value: object) -> bool:
    """A number above 0 (an integer counts; a boolean, a string and ``None`` do not)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


class MetricRecord(FrozenModel):
    """One row of ``metric_record``; every field is required (an unknown value is ``None``, never a default)."""

    metric_name: str = Field(pattern=NAME_RE)
    version: str = Field(pattern=VERSION_RE)  # the record's own version
    metric_version: str = Field(pattern=VERSION_RE)  # the version of the metric code it applies to
    units: Unit  # of the numbers below: the units of the metric
    status: RecordStatus
    intended_use: str = Field(min_length=1, max_length=MAX_INTENDED_USE)  # the coach's sentence; never logged
    supported_views: tuple[RecordView, ...]
    gold_reference: str | None = Field(pattern=GOLD_RE)
    human_variability: NonNegNumber | None  # in ``units``
    smallest_useful_change: PositiveNumber | None  # in ``units``
    measurement_error: NonNegNumber | None  # in ``units``
    min_valid_duration_s: NonNegNumber | None  # [s]: binds the argument ``min_valid_s`` of the metric
    parameters: dict[Annotated[str, StringConstraints(pattern=PARAM_KEY_RE)], ParamValue]
    data_sources: tuple[DataSource, ...]  # provenance of the numbers (AGENTS.md 9.4.6); empty: our own recordings
    signed_by: str | None = Field(pattern=SIGNER_RE)
    signed_at: date | None

    @field_validator("intended_use")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if not value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("intended_use must be one non-blank line without control characters")
        return value

    @field_validator("supported_views")
    @classmethod
    def _views_once(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("supported_views must not repeat a view")
        return value

    @field_validator("data_sources")
    @classmethod
    def _sources_once(cls, value: tuple[DataSource, ...]) -> tuple[DataSource, ...]:
        ids = [s.dataset_id for s in value]
        if len(set(ids)) != len(ids):
            raise ValueError("data_sources must name each dataset once")
        return value

    @model_validator(mode="after")
    def _parameters(self) -> Self:
        params = self.parameters
        if len(params) > MAX_PARAMETERS:
            raise ValueError(f"parameters must have at most {MAX_PARAMETERS} entries")
        if MINIMUM_KEY in params:
            raise ValueError(f"{MINIMUM_KEY} is the column min_valid_duration_s: do not repeat it in parameters")
        for key in (CUTOFF_KEY, *PAUSE_KEYS):
            if key in params and not _positive(params[key]):
                raise ValueError(f"{key} must be a number above 0 (or the key left out)")
        if (PAUSE_KEYS[0] in params) != (PAUSE_KEYS[1] in params):
            raise ValueError("pause_tau and pause_min_s must be bound together or not at all")
        return self

    @model_validator(mode="after")
    def _status(self) -> Self:
        if self.status == "experimental":
            if (self.signed_by is None) != (self.signed_at is None):
                raise ValueError("signed_by and signed_at must be given together or not at all")
        elif self.status == "retired":
            for name in ("signed_by", "signed_at"):
                if getattr(self, name) is None:
                    raise ValueError(f"retired record needs {name}: who retired it and when")
        else:
            self._check_enabled()
        return self

    def _check_enabled(self) -> None:
        for name in _REQUIRED_WHEN_ENABLED:
            if getattr(self, name) is None:
                raise ValueError(f"enabled record needs {name}")
        if not self.supported_views:
            raise ValueError("enabled record needs at least one supported view")
        error = cast(float, self.measurement_error)  # not None: checked in the loop above
        change = cast(float, self.smallest_useful_change)
        if not error < change:
            raise ValueError(
                "measurement_error must be below smallest_useful_change: a metric whose error is as large as the "
                "change the coach wants to see stays experimental (v3 8.2, G03)"
            )
        if CUTOFF_KEY not in self.parameters:
            raise ValueError(f"enabled record must bind {CUTOFF_KEY}: the error was measured at one cut-off (DEC-0061)")
