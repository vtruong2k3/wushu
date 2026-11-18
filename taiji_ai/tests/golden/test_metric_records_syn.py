"""T-MET-11f: a signed record applied to results of the generator through the real quality chain (P5.09).

SYN-05 (a mover with two pauses) gives a speed result that uses thresholds: the pauses of a joint group. SYN-03 (a trunk
at a known angle) gives a result that depends on the view. The layers are what the pipeline would hand to a metric
(``run_quality_arrays`` then ``pose_filtered_from_result``), and the summaries are what ``group_speed`` and
``trunk_lean`` return. The record binds what the pipeline will pass to the metric: ``tau``, ``d_min``, the minimum
valid duration and the cut-off. ``tau`` is chosen here, as a share of the true peak, never by the product.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.metric_records import record_for
from helpers.synth import TOLERANCES, make_sequence, speed_at
from taiji_ai.metrics.records import apply_record
from taiji_ai.metrics.series import MetricResult
from taiji_ai.metrics.tempo import group_speed
from taiji_ai.metrics.trunk_lean import trunk_lean
from taiji_ai.quality.chain import QualityParams
from taiji_ai.quality.filters import ButterworthParams
from taiji_ai.quality.layers_io import PoseFiltered
from taiji_ai.schemas.metric import MetricSummary

SHARE = 0.10  # tau as a share of the true peak of the group
D_MIN = 0.3  # s
MIN_VALID = 0.1  # s
TOL_DEG = TOLERANCES["SYN-03"]["median_theta_error_deg"]


def hips(layer: PoseFiltered, tau: float | None, **kwargs) -> MetricResult:
    pauses = {} if tau is None else {"pause_tau": tau, "pause_min_s": D_MIN}
    return group_speed(
        layer,
        group="hips",
        flags={},
        camera_id="camA",
        view_category="front",
        min_valid_s=MIN_VALID,
        **pauses,
        **kwargs,
    )


def lean(layer: PoseFiltered, plane: str = "lr", view: str = "front") -> MetricResult:
    args = {"plane": plane, "view_category": view, "flags": {}, "camera_id": "camA", "min_valid_s": MIN_VALID}
    return trunk_lean(layer, **args)  # type: ignore[arg-type]


def stat(summary: MetricSummary, name: str) -> float:
    (s,) = [s for s in summary.statistics if s.name == name]
    assert s.value is not None
    return s.value


@pytest.fixture(scope="module")
def syn05():
    seq = make_sequence("SYN-05", seed=1)  # the default of the scenario: no noise
    tau = SHARE * float(speed_at(seq, np.linspace(0.0, float(seq.params["duration"]), 5001))["hips"].max())
    return seq, tau


def numbers(summary: MetricSummary) -> dict:
    data = summary.model_dump()
    for key in ("record_status", "record_version", "threshold_source"):
        data.pop(key)
    return data


# --- SYN-05: the speed of the hips and its pauses ---------------------------------------------------------------------
def test_t_met_11f_syn05_a_record_that_binds_the_triple_makes_the_pauses_conclusive(syn05):
    seq, tau = syn05
    summary = hips(layer_of_sequence(seq), tau).summary
    assert summary.record_status == "experimental" and summary.threshold_source == "unsigned_config"
    assert stat(summary, "pause_count") == float(seq.truth["n_pauses"]) == 2.0
    record = record_for("speed_hips", {"pause_tau": tau, "pause_min_s": D_MIN, "filter_cutoff_hz": 6.0})
    out = apply_record(summary, record)
    assert out.decision == "enabled" and out.summary.conclusive is True
    assert out.summary.threshold_source == "signed_record" and out.summary.record_version == "1"
    assert numbers(out.summary) == numbers(summary)  # the pauses are the same two, whatever the record says
    assert stat(out.summary, "pause_count") == 2.0 and len(out.summary.events) == 2


def test_t_met_11f_syn05_the_same_record_on_a_layer_filtered_at_8_hz_does_not_apply(syn05):
    seq, tau = syn05
    layer8 = layer_of_sequence(seq, params=QualityParams(filter=ButterworthParams(cutoff_hz=8.0)))
    summary = hips(layer8, tau).summary
    assert summary.parameters["filter_cutoff_hz"] == 8.0
    out = apply_record(summary, record_for("speed_hips", {"pause_tau": tau, "pause_min_s": D_MIN}))  # signed at 6 Hz
    assert out.decision == "parameters_differ" and out.summary == summary
    assert out.summary.conclusive is False and out.summary.record_status == "experimental"
    assert stat(out.summary, "pause_count") >= 0.0  # the numbers are still there: only their status is not
    signed_at_8 = record_for("speed_hips", {"pause_tau": tau, "pause_min_s": D_MIN, "filter_cutoff_hz": 8.0})
    again = apply_record(summary, signed_at_8)  # the triple of that record is the one the layer was made with
    assert again.decision == "enabled" and again.summary.conclusive is True


def test_t_met_11f_syn05_without_a_record_or_without_the_thresholds_signed_nothing_is_concluded(syn05):
    seq, tau = syn05
    summary = hips(layer_of_sequence(seq), tau).summary
    none = apply_record(summary, None)
    assert none.decision == "no_record" and none.summary == summary and none.summary.conclusive is False
    unsigned = apply_record(summary, record_for("speed_hips"))  # the record signs the cut-off, not the thresholds
    assert unsigned.decision == "thresholds_not_signed" and unsigned.summary.conclusive is False
    assert unsigned.summary.threshold_source == "unsigned_config"
    other_tau = apply_record(summary, record_for("speed_hips", {"pause_tau": tau * 1.001, "pause_min_s": D_MIN}))
    assert other_tau.decision == "parameters_differ" and other_tau.summary.conclusive is False


def test_t_met_11f_syn05_a_result_without_pauses_is_enabled_by_a_record_without_thresholds(syn05):
    seq, _ = syn05
    summary = hips(layer_of_sequence(seq), None).summary  # the profile only: no pause was asked for
    assert summary.threshold_source is None
    out = apply_record(summary, record_for("speed_hips"))
    assert out.decision == "enabled" and out.summary.threshold_source is None and out.summary.conclusive is True
    pairs = apply_record(summary, record_for("speed_hips", {"pause_tau": 0.1, "pause_min_s": D_MIN}))
    assert pairs.decision == "parameters_differ"  # the record signs pauses that this result does not have


# --- SYN-03: the trunk lean and the view ------------------------------------------------------------------------------
def test_t_met_11f_syn03_a_record_for_the_front_view_makes_the_angle_conclusive_and_changes_none_of_it():
    seq = make_sequence("SYN-03", seed=1, theta_deg=10.0, noise_px=1.0)
    summary = lean(layer_of_sequence(seq)).summary
    assert abs(stat(summary, "lean_median") - float(seq.truth["median_theta_deg"])) <= TOL_DEG
    out = apply_record(summary, record_for("trunk_lean_lr", supported_views=("front",)))
    assert out.decision == "enabled" and out.summary.conclusive is True and out.summary.threshold_source is None
    assert numbers(out.summary) == numbers(summary)
    assert abs(stat(out.summary, "lean_median") - float(seq.truth["median_theta_deg"])) <= TOL_DEG


def test_t_met_11f_syn03_a_record_for_another_view_does_not_apply():
    seq = make_sequence("SYN-03", seed=1, theta_deg=10.0)
    summary = lean(layer_of_sequence(seq)).summary
    out = apply_record(summary, record_for("trunk_lean_lr", supported_views=("side",)))
    assert out.decision == "view_not_supported" and out.summary == summary and out.summary.conclusive is False


def test_t_met_11f_syn03_the_side_plane_on_a_front_segment_has_no_number_and_no_record_changes_that():
    seq = make_sequence("SYN-03", seed=1, theta_deg=10.0)
    result = lean(layer_of_sequence(seq), plane="fb", view="front")
    assert result.summary.evidence == "insufficient_evidence"  # T-MET-07: the view does not fit the plane
    assert all(s.value is None for s in result.summary.statistics)
    for record in (record_for("trunk_lean_fb"), record_for("trunk_lean_fb", supported_views=("front",))):
        out = apply_record(result.summary, record)
        assert out.decision in ("view_not_supported", "parameters_differ") and out.summary.conclusive is False
        assert all(
            s.value is None for s in out.summary.statistics
        )  # a record gives no number to a result that has none
