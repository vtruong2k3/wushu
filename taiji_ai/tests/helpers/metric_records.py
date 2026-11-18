"""Signed records for the tests of P5.09: a valid ``MetricRecord`` for any of the seven metrics, in one call."""

from __future__ import annotations

from datetime import date
from typing import Any

from taiji_ai.metrics.records import METRICS
from taiji_ai.schemas.metric_record import MetricRecord

VIEWS = {"trunk_lean_lr": ("front",), "trunk_lean_fb": ("side",)}  # the views each plane is computed for by default
SENTENCE = "Dùng để so sánh nhịp của hông trong một thức, không dùng để chấm điểm"
ENABLED_BASE: dict[str, Any] = {
    "version": "1",
    "status": "enabled",
    "intended_use": SENTENCE,
    "gold_reference": "REPORT-1",
    "human_variability": 0.01,
    "smallest_useful_change": 0.2,
    "measurement_error": 0.05,
    "min_valid_duration_s": 0.1,
    "data_sources": (),
    "signed_by": "cli:H",
    "signed_at": date(2026, 12, 1),
}


def record_for(name: str, parameters: dict[str, Any] | None = None, **changes: Any) -> MetricRecord:
    """An enabled record of metric ``name`` that binds the cut-off 6 Hz and the minimum 0.1 s, plus ``parameters``."""
    spec = METRICS[name]
    data = {
        **ENABLED_BASE,
        "metric_name": name,
        "metric_version": spec.version,
        "units": spec.units,
        "supported_views": VIEWS.get(name, ("front", "side")),
        "parameters": {"filter_cutoff_hz": 6.0, **(parameters or {})},
        **changes,
    }
    return MetricRecord.model_validate(data)


def draft_for(name: str, **changes: Any) -> MetricRecord:
    """An unsigned draft: nothing but the identity, a sentence and the views."""
    data = record_for(name).model_dump()
    data.update(
        {
            "status": "experimental",
            "gold_reference": None,
            "human_variability": None,
            "smallest_useful_change": None,
            "measurement_error": None,
            "min_valid_duration_s": None,
            "parameters": {},
            "signed_by": None,
            "signed_at": None,
            **changes,
        }
    )
    return MetricRecord.model_validate(data)
