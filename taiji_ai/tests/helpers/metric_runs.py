"""Run the seven metrics of the product on one layer with the plain arguments the tests of P5.09 need.

``run_all`` returns ``{metric_name: MetricResult}`` for hip height A and B, trunk lean (both planes) and the speed of
the three groups, every optional minimum left out and every row of the layer in the segment. The layer is also the
reference of hip height A (a standing segment of the same recording). ``extra`` adds arguments for one metric.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

from helpers.metric_layers import FPS, body, layer_of
from taiji_ai.metrics.hip_height import hip_height_a, hip_height_b
from taiji_ai.metrics.series import MetricResult
from taiji_ai.metrics.tempo import GROUP_METRIC_NAMES, group_speed
from taiji_ai.metrics.trunk_lean import METRIC_NAMES as LEAN_NAMES
from taiji_ai.metrics.trunk_lean import trunk_lean
from taiji_ai.quality.chain import QualityParams
from taiji_ai.quality.filters import ButterworthParams
from taiji_ai.quality.layers_io import PoseFiltered

EVERYTHING = [(0.0, 1.0e6)]  # a stable interval that holds every row
HIP_NAMES = ("hip_height_a", "hip_height_b")
ALL_NAMES = (*HIP_NAMES, *LEAN_NAMES.values(), *GROUP_METRIC_NAMES.values())


def layer_at(cutoff_hz: float, fps: float = FPS, n: int = 60) -> PoseFiltered:
    """The final layer of a standing body through the real chain with the given Butterworth cut-off."""
    params = QualityParams(filter=ButterworthParams(cutoff_hz=cutoff_hz))
    return layer_of(body(n), np.arange(n) / fps, params=params)


def with_cutoff(layer: PoseFiltered, cutoff_hz: float) -> PoseFiltered:
    """The same arrays with another cut-off written in the header (what the echo reads)."""
    filter_record = layer.meta.params.filter.model_copy(update={"cutoff_hz": cutoff_hz})
    params = layer.meta.params.model_copy(update={"filter": filter_record})
    return dataclasses.replace(layer, meta=layer.meta.model_copy(update={"params": params}))


def run_all(
    layer: PoseFiltered, *, view: str = "front", extra: dict[str, dict[str, Any]] | None = None
) -> dict[str, MetricResult]:
    """The seven results; ``extra[metric_name]`` adds keyword arguments to that metric only."""
    extra = extra or {}
    common: dict[str, Any] = {"flags": {}, "camera_id": "camA", "view_category": view}
    out: dict[str, MetricResult] = {
        "hip_height_a": hip_height_a(
            layer, reference=layer, stable_intervals=EVERYTHING, **common, **extra.get("hip_height_a", {})
        ),
        "hip_height_b": hip_height_b(layer, stable_intervals=EVERYTHING, **common, **extra.get("hip_height_b", {})),
    }
    for plane, name in LEAN_NAMES.items():
        out[name] = trunk_lean(layer, plane=plane, **common, **extra.get(name, {}))  # type: ignore[arg-type]
    for group, name in GROUP_METRIC_NAMES.items():
        out[name] = group_speed(layer, group=group, **common, **extra.get(name, {}))  # type: ignore[arg-type]
    return out
