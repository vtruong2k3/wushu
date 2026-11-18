"""What a signed ``metric_record`` does to a result (P5.09, v3 section 8.2): the registry of the seven metrics, the
check of a record against it, and ``apply_record``.

A metric result is born ``experimental``: its numbers are shown and ``MetricSummary.conclusive`` is false (AGENTS.md
section 5.5, T-MET-11). ``apply_record`` is the only place where that changes. It never changes a number, a statistic,
an event or a parameter: it sets ``record_status``, ``record_version`` and (for a result that uses thresholds)
``threshold_source``, and it says why when it does not enable the result. In this order:

1. a record of another metric, metric version or units is a programming error (``MetricRecordError``), and so is a
   summary that already has a record status;
2. no record: ``no_record``; a draft or a signed decision to keep the metric experimental: ``record_experimental``;
3. a retired record: ``retired`` (status ``retired``, not conclusive); a result that uses thresholds cannot have it (a
   retired metric signs no threshold: compute it without them or not at all);
4. an enabled record: the view of the summary must be one the record supports (``view_not_supported``); every value the
   record binds must be the one the summary echoes, *exactly* (``parameters_differ``): the minimum valid duration
   (``min_valid_duration_s`` against ``min_valid_s``), the cut-off of the filter (``filter_cutoff_hz``: the error budget
   was measured on a layer filtered at one cut-off, DEC-0061), every key of ``parameters`` and, for trunk lean, the
   set of views the metric was computed for; a result that uses thresholds needs the registry's threshold keys bound
   (``thresholds_not_signed``). Then the result is ``enabled`` with the record's version, its thresholds come from
   ``signed_record``, and it is ``conclusive`` when its evidence is sufficient.

The pipeline (P7) will read the record, compute the metric with the record's own values on a layer filtered at the
record's cut-off, and apply it; that is why equality is exact and why a value that differs is a decision, not a
tolerance. ``check_record`` is what the store runs before it saves a record: the metric must exist in this code, with
these units and this version, and the record may bind only the keys the metric echoes as arguments.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal

from taiji_ai.metrics import MetricError, hip_height, tempo, trunk_lean
from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.metric import MetricSummary, Unit
from taiji_ai.schemas.metric_record import CUTOFF_KEY, MINIMUM_KEY, PAUSE_KEYS, MetricRecord

Decision = Literal[
    "enabled",
    "no_record",
    "record_experimental",
    "retired",
    "view_not_supported",
    "parameters_differ",
    "thresholds_not_signed",
]
_MISSING: Final = object()  # a key the summary does not echo


class MetricRecordError(MetricError):
    """A record or its use is refused; the message names the field and never echoes free text."""


@dataclass(frozen=True)
class MetricSpec:
    """One metric of this code as a record sees it.

    ``bindable`` are the keys of ``parameters`` that a record may bind besides ``filter_cutoff_hz`` (the arguments of
    the metric: not the values it measures and not the camera roll, which belongs to a camera); ``thresholds`` are the
    keys that carry the thresholds of its outputs, which a result that uses them needs signed; ``views_parameter`` is
    the key that echoes the views the metric was computed for (``None``: the metric has no view argument).
    """

    name: str
    units: Unit
    version: str
    bindable: frozenset[str]
    thresholds: frozenset[str]
    views_parameter: str | None


def _speed_spec(name: str) -> MetricSpec:
    return MetricSpec(
        name=name,
        units=tempo.UNITS,
        version=tempo.METRIC_VERSION,
        bindable=frozenset({"min_scale_s", *PAUSE_KEYS}),
        thresholds=frozenset(PAUSE_KEYS),
        views_parameter=None,
    )


def _lean_spec(name: str) -> MetricSpec:
    return MetricSpec(
        name=name,
        units=trunk_lean.UNITS,
        version=trunk_lean.METRIC_VERSION,
        bindable=frozenset(),
        thresholds=frozenset(),
        views_parameter="supported_views",
    )


def _hip_spec(name: str, bindable: str) -> MetricSpec:
    return MetricSpec(
        name=name,
        units=hip_height.UNITS,
        version=hip_height.METRIC_VERSION,
        bindable=frozenset({bindable}),
        thresholds=frozenset(),
        views_parameter=None,
    )


_SPECS: Final = (
    _hip_spec(hip_height.METRIC_NAME_A, "min_reference_s"),
    _hip_spec(hip_height.METRIC_NAME_B, "min_scale_s"),
    *(_lean_spec(name) for name in trunk_lean.METRIC_NAMES.values()),
    *(_speed_spec(name) for name in tempo.GROUP_METRIC_NAMES.values()),
)
METRICS: Final[Mapping[str, MetricSpec]] = MappingProxyType({spec.name: spec for spec in _SPECS})


def check_record(record: MetricRecord) -> None:
    """Refuse a record that no metric of this code can be computed for.

    The metric must exist, with the units and the version of this code, and ``parameters`` may bind only
    ``filter_cutoff_hz`` and the arguments the metric echoes. Raises ``MetricRecordError`` naming the field.
    """
    spec = METRICS.get(record.metric_name)
    if spec is None:
        raise MetricRecordError(
            f"metric_name {record.metric_name} is not a metric of this code (known: {sorted(METRICS)})"
        )
    if record.units != spec.units:
        raise MetricRecordError(f"units of {spec.name} are {spec.units}, the record says {record.units}")
    if record.metric_version != spec.version:
        raise MetricRecordError(
            f"metric_version of {spec.name} in this code is {spec.version}, the record says {record.metric_version}"
        )
    allowed = spec.bindable | {CUTOFF_KEY}
    for key in record.parameters:
        if key not in allowed:
            raise MetricRecordError(f"parameter {key} cannot be bound for {spec.name} (allowed: {sorted(allowed)})")


@dataclass(frozen=True)
class RecordedSummary:
    """The summary after ``apply_record`` and the decision that says why it is, or is not, enabled."""

    summary: MetricSummary
    decision: Decision


def _same(a: object, b: object) -> bool:
    """Exactly equal: an integer equals the float of the same value, a boolean is not a number, ``None`` is itself."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def _uses_thresholds(summary: MetricSummary) -> bool:
    return any(s.uses_threshold for s in summary.statistics) or any(e.uses_threshold for e in summary.events)


def _bound_values_match(summary: MetricSummary, spec: MetricSpec, record: MetricRecord) -> bool:
    params = summary.parameters
    if not _same(params.get(MINIMUM_KEY, _MISSING), record.min_valid_duration_s):
        return False
    if any(not _same(params.get(key, _MISSING), value) for key, value in record.parameters.items()):
        return False
    if spec.views_parameter is not None:
        echoed = params.get(spec.views_parameter)
        if not isinstance(echoed, str) or set(echoed.split("-")) != set(record.supported_views):
            return False
    return True


def _with(summary: MetricSummary, **changes: Any) -> MetricSummary:
    try:
        return parse_manifest(MetricSummary, {**summary.model_dump(), **changes})
    except ManifestError as exc:
        raise MetricRecordError(str(exc)) from exc


def apply_record(summary: MetricSummary, record: MetricRecord | None) -> RecordedSummary:
    """Give a result the status its record allows (see the module docstring for the order of the decisions).

    Never changes a number. Raises ``MetricRecordError`` when the summary already has a record status, when the record
    is of another metric, metric version or units, or when a retired record meets a result that uses thresholds.
    """
    if summary.record_status != "experimental":  # a record_version exists exactly when the status is enabled
        raise MetricRecordError(
            f"the summary of {summary.metric_name} already has the record status {summary.record_status}: "
            "a record is applied once, to a result made without one"
        )
    if record is None:
        return RecordedSummary(summary, "no_record")
    for field in ("metric_name", "metric_version", "units"):
        if getattr(summary, field) != getattr(record, field):
            raise MetricRecordError(
                f"the record has {field} {getattr(record, field)} and the summary {getattr(summary, field)}"
            )
    spec = METRICS.get(summary.metric_name)
    if spec is None:
        raise MetricRecordError(f"metric_name {summary.metric_name} is not a metric of this code")
    uses = _uses_thresholds(summary)
    if record.status == "experimental":
        return RecordedSummary(summary, "record_experimental")
    if record.status == "retired":
        if uses:
            raise MetricRecordError(
                f"{spec.name} is retired: a result that uses thresholds cannot have the status retired "
                "(compute it without thresholds, or not at all)"
            )
        return RecordedSummary(_with(summary, record_status="retired"), "retired")
    if summary.view_category not in record.supported_views:
        return RecordedSummary(summary, "view_not_supported")
    if not _bound_values_match(summary, spec, record):
        return RecordedSummary(summary, "parameters_differ")
    if uses and (not spec.thresholds or not spec.thresholds <= set(record.parameters)):
        return RecordedSummary(summary, "thresholds_not_signed")
    enabled = _with(
        summary,
        record_status="enabled",
        record_version=record.version,
        threshold_source="signed_record" if uses else None,
    )
    return RecordedSummary(enabled, "enabled")
