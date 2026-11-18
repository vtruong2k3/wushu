"""T-MET-11b and T-MET-11d: the registry of the seven metrics, ``check_record`` and ``apply_record`` (P5.09).

A result is ``conclusive`` only when a signed, enabled record of the same metric, metric version and units supports
its view, matches every value it binds *exactly* and signs every threshold the result uses (AGENTS.md 5.5, T-MET-11).
In every other case the result keeps its numbers, stays ``experimental`` (or ``retired``) and ``apply_record`` says
why. The summaries are real: each metric is run on a standing body through the quality chain.
"""

from __future__ import annotations

from typing import Any

import pytest

from helpers.metric_records import record_for
from helpers.metric_runs import ALL_NAMES, layer_at, run_all
from taiji_ai.metrics.hip_height import hip_height_b
from taiji_ai.metrics.records import METRICS, MetricRecordError, apply_record, check_record
from taiji_ai.metrics.tempo import group_speed
from taiji_ai.schemas.metric import MetricSummary, Statistic
from taiji_ai.schemas.metric_record import MetricRecord

SPEEDS = ("speed_hands", "speed_hips", "speed_feet")
MINIMUM = {name: {"min_valid_s": 0.1} for name in ALL_NAMES}  # the value that the records below bind
PAUSES = {"pause_tau": 0.1, "pause_min_s": 0.3}


def summaries(cutoff_hz: float = 6.0, extra: dict[str, dict[str, Any]] | None = None) -> dict[str, MetricSummary]:
    """The seven summaries of a standing body at ``cutoff_hz``, each in the view it is computed for."""
    layer = layer_at(cutoff_hz)
    merged = {name: {**MINIMUM[name], **(extra or {}).get(name, {})} for name in ALL_NAMES}
    out = {name: result.summary for name, result in run_all(layer, extra=merged).items()}
    out["trunk_lean_fb"] = run_all(layer, view="side", extra=merged)["trunk_lean_fb"].summary
    return out


def numbers(summary: MetricSummary) -> dict[str, Any]:
    """Everything of a summary but the three fields that a record sets."""
    data = summary.model_dump()
    for key in ("record_status", "record_version", "threshold_source"):
        data.pop(key)
    return data


# --- T-MET-11b: the registry ------------------------------------------------------------------------------------------
def test_t_met_11b_the_registry_has_the_seven_metrics_and_each_spec_is_the_one_the_metric_reports():
    assert sorted(METRICS) == sorted(ALL_NAMES) and len(METRICS) == 7
    results = run_all(layer_at(6.0))
    for name, spec in METRICS.items():
        header = results[name].series.header
        assert spec.name == name == header.metric_name
        assert spec.units == header.units and spec.version == header.metric_version, name


def test_t_met_11b_everything_a_record_may_bind_is_something_the_summary_really_echoes():
    for name, result in run_all(layer_at(6.0)).items():
        spec, echoed = METRICS[name], set(result.summary.parameters)
        assert spec.bindable <= echoed and spec.thresholds <= spec.bindable, name
        assert {"filter_cutoff_hz", "min_valid_s"} <= echoed, name  # the cut-off and the column of the minimum
        if spec.views_parameter is not None:
            assert spec.views_parameter in echoed, name


def test_t_met_11b_what_each_metric_lets_a_record_bind_is_pinned_a_change_is_a_decision():
    pinned = {
        "hip_height_a": ({"min_reference_s"}, set(), None),
        "hip_height_b": ({"min_scale_s"}, set(), None),
        "trunk_lean_lr": (set(), set(), "supported_views"),
        "trunk_lean_fb": (set(), set(), "supported_views"),
        **{name: ({"min_scale_s", "pause_tau", "pause_min_s"}, {"pause_tau", "pause_min_s"}, None) for name in SPEEDS},
    }
    for name, (bindable, thresholds, views) in pinned.items():
        spec = METRICS[name]
        assert (set(spec.bindable), set(spec.thresholds), spec.views_parameter) == (bindable, thresholds, views), name


@pytest.mark.parametrize("name", ALL_NAMES)
def test_t_met_11b_a_record_for_each_metric_with_its_own_keys_passes_the_check(name):
    spec = METRICS[name]
    check_record(record_for(name, {key: 1.0 for key in spec.bindable if key not in spec.thresholds}))
    if spec.thresholds:
        check_record(record_for(name, PAUSES))


def test_t_met_11b_the_check_refuses_what_no_metric_of_the_code_can_be_computed_with():
    with pytest.raises(MetricRecordError, match="metric_name"):
        check_record(record_for("speed_hips", metric_name="speed_head"))
    with pytest.raises(MetricRecordError, match="units"):
        check_record(record_for("speed_hips", units="deg"))
    with pytest.raises(MetricRecordError, match="metric_version"):
        check_record(record_for("speed_hips", metric_version="2"))
    for key in ("roll_deg", "scale_px", "bogus"):
        with pytest.raises(MetricRecordError, match=key):
            check_record(record_for("speed_hips", {key: 1.0}))
    with pytest.raises(MetricRecordError, match="pause_tau"):  # hip height has no pause
        check_record(record_for("hip_height_b", PAUSES))
    with pytest.raises(MetricRecordError, match="min_reference_s"):  # hip height B has no reference
        check_record(record_for("hip_height_b", {"min_reference_s": 1.0}))


def test_t_met_11b_the_check_applies_to_a_draft_too_and_names_the_allowed_keys():
    draft = record_for("speed_hips", {"nonsense": 1.0}, status="experimental", signed_by=None, signed_at=None)
    with pytest.raises(MetricRecordError, match="min_scale_s"):
        check_record(draft)


# --- T-MET-11d: apply_record ------------------------------------------------------------------------------------------
def test_t_met_11d_the_summaries_of_the_tests_all_have_sufficient_evidence_and_no_record():
    for name, summary in summaries().items():
        assert summary.evidence == "sufficient" and summary.record_status == "experimental", name
        assert summary.record_version is None and summary.conclusive is False, name


@pytest.mark.parametrize("name", ALL_NAMES)
def test_t_met_11d_a_matching_enabled_record_makes_the_result_conclusive_and_changes_no_number(name):
    summary = summaries()[name]
    out = apply_record(summary, record_for(name))
    assert out.decision == "enabled"
    assert out.summary.record_status == "enabled" and out.summary.record_version == "1"
    assert out.summary.conclusive is True
    assert out.summary.threshold_source is None  # nothing in this result uses a threshold
    assert numbers(out.summary) == numbers(summary)


def test_t_met_11d_a_result_that_uses_thresholds_gets_them_from_the_signed_record():
    summary = summaries(extra={"speed_hips": PAUSES})["speed_hips"]
    assert summary.threshold_source == "unsigned_config" and summary.conclusive is False
    out = apply_record(summary, record_for("speed_hips", PAUSES))
    assert out.decision == "enabled" and out.summary.conclusive is True
    assert out.summary.threshold_source == "signed_record" and out.summary.record_version == "1"
    assert numbers(out.summary) == numbers(summary)


def test_t_met_11d_no_record_a_draft_and_a_signed_decision_to_stay_experimental_conclude_nothing():
    summary = summaries()["speed_hips"]
    out = apply_record(summary, None)
    assert out.decision == "no_record" and out.summary == summary and out.summary.conclusive is False
    draft = record_for("speed_hips", status="experimental", signed_by=None, signed_at=None)
    out = apply_record(summary, draft)
    assert out.decision == "record_experimental" and out.summary == summary and out.summary.conclusive is False
    kept = record_for("speed_hips", status="experimental", measurement_error=0.5)  # signed, the error is too large
    out = apply_record(summary, kept)
    assert out.decision == "record_experimental" and out.summary == summary and out.summary.conclusive is False


def test_t_met_11d_a_retired_record_gives_the_status_retired_never_conclusive_and_keeps_the_numbers():
    summary = summaries()["hip_height_b"]
    out = apply_record(summary, record_for("hip_height_b", status="retired", signed_by="cli:H2"))
    assert out.decision == "retired"
    assert out.summary.record_status == "retired" and out.summary.record_version is None
    assert out.summary.conclusive is False and out.summary.threshold_source is None
    assert numbers(out.summary) == numbers(summary)


def test_t_met_11d_a_retired_metric_cannot_be_given_thresholds():
    summary = summaries(extra={"speed_hips": PAUSES})["speed_hips"]
    with pytest.raises(MetricRecordError, match="retired"):
        apply_record(summary, record_for("speed_hips", PAUSES, status="retired"))


def test_t_met_11d_enabled_with_insufficient_evidence_is_enabled_but_not_conclusive():
    layer = layer_at(6.0)
    args: dict[str, Any] = {"flags": {}, "camera_id": "camA", "view_category": "front", "min_valid_s": 0.1}
    result = hip_height_b(layer, stable_intervals=[], **args)
    assert result.summary.evidence == "insufficient_evidence"
    out = apply_record(result.summary, record_for("hip_height_b"))
    assert out.decision == "enabled" and out.summary.record_status == "enabled"
    assert out.summary.conclusive is False  # AGENTS.md 5.5: a number is needed as well as a record


def test_t_met_11d_a_view_the_record_does_not_support_leaves_the_result_experimental():
    summary = summaries()["hip_height_b"]
    out = apply_record(summary, record_for("hip_height_b", supported_views=("side", "back")))
    assert out.decision == "view_not_supported" and out.summary == summary and out.summary.conclusive is False


def test_t_met_11d_a_value_that_differs_from_the_one_signed_leaves_the_result_experimental():
    base = summaries()
    skipped = summaries(cutoff_hz=1000.0)["speed_hips"]  # the filter could not be designed: the cut-off echo is None
    assert skipped.parameters["filter_cutoff_hz"] is None
    near = summaries(cutoff_hz=6.000000001)["speed_hips"]  # the same up to a thousandth of a millionth
    lean = base["trunk_lean_lr"]
    computed_for_two = lean.model_copy(update={"parameters": {**lean.parameters, "supported_views": "front-side"}})
    cases: list[tuple[str, MetricSummary, MetricRecord]] = [
        ("another cut-off", base["speed_hips"], record_for("speed_hips", {"filter_cutoff_hz": 8.0})),
        ("filter skipped", skipped, record_for("speed_hips")),
        ("not exactly the same cut-off", near, record_for("speed_hips")),
        ("another minimum", base["speed_hips"], record_for("speed_hips", min_valid_duration_s=0.5)),
        ("a bound argument that was not given", base["speed_hips"], record_for("speed_hips", {"min_scale_s": 0.5})),
        ("a bound pause that was not asked", base["speed_hips"], record_for("speed_hips", PAUSES)),
        ("more views signed than computed", lean, record_for("trunk_lean_lr", supported_views=("front", "side"))),
        ("more views computed than signed", computed_for_two, record_for("trunk_lean_lr", supported_views=("front",))),
    ]
    for label, summary, record in cases:
        out = apply_record(summary, record)
        assert out.decision == "parameters_differ", label
        assert out.summary == summary and out.summary.conclusive is False, label


def test_t_met_11d_a_trunk_lean_summary_that_does_not_say_its_views_does_not_match_any_record():
    lean = summaries()["trunk_lean_lr"]
    without = {k: v for k, v in lean.parameters.items() if k != "supported_views"}
    for parameters in (without, {**without, "supported_views": None}, {**without, "supported_views": 1}):
        out = apply_record(lean.model_copy(update={"parameters": parameters}), record_for("trunk_lean_lr"))
        assert out.decision == "parameters_differ" and out.summary.conclusive is False


def test_t_met_11d_the_views_computed_for_and_the_views_signed_are_the_same_set_in_any_order():
    lean = summaries()["trunk_lean_lr"]
    computed = lean.model_copy(update={"parameters": {**lean.parameters, "supported_views": "back-front"}})
    out = apply_record(computed, record_for("trunk_lean_lr", supported_views=("front", "back")))
    assert out.decision == "enabled" and out.summary.conclusive is True


def test_t_met_11d_a_bound_value_that_the_summary_does_not_echo_at_all_differs():
    summary = summaries()["speed_hips"]
    out = apply_record(summary, record_for("speed_hips", {"made_up_key": 1.0}))
    assert out.decision == "parameters_differ"


def test_t_met_11d_equal_means_equal_a_boolean_is_not_a_number_and_an_integer_is_a_float():
    summary = summaries()["speed_hips"]

    def with_param(value: Any) -> MetricSummary:
        return summary.model_copy(update={"parameters": {**summary.parameters, "flag": value}})

    assert apply_record(with_param(1.0), record_for("speed_hips", {"flag": 1})).decision == "enabled"
    assert apply_record(with_param(1), record_for("speed_hips", {"flag": True})).decision == "parameters_differ"
    assert apply_record(with_param(True), record_for("speed_hips", {"flag": 1})).decision == "parameters_differ"
    assert apply_record(with_param(None), record_for("speed_hips", {"flag": None})).decision == "enabled"
    assert apply_record(with_param(0.0), record_for("speed_hips", {"flag": None})).decision == "parameters_differ"
    assert apply_record(with_param(True), record_for("speed_hips", {"flag": True})).decision == "enabled"
    assert apply_record(with_param(False), record_for("speed_hips", {"flag": True})).decision == "parameters_differ"
    assert apply_record(with_param(False), record_for("speed_hips", {"flag": False})).decision == "enabled"


def test_t_met_11d_a_bound_argument_that_matches_is_enabled():
    summary = summaries(extra={"speed_hips": {"min_scale_s": 0.5}})["speed_hips"]
    assert summary.parameters["min_scale_s"] == 0.5
    assert apply_record(summary, record_for("speed_hips", {"min_scale_s": 0.5})).decision == "enabled"
    assert apply_record(summary, record_for("speed_hips")).decision == "enabled"  # not bound: not constrained


def test_t_met_11d_thresholds_that_the_result_uses_must_be_the_ones_signed():
    asked = summaries(extra={"speed_hips": PAUSES})["speed_hips"]
    unsigned = apply_record(asked, record_for("speed_hips"))  # the record binds neither threshold
    assert unsigned.decision == "thresholds_not_signed" and unsigned.summary == asked
    assert unsigned.summary.threshold_source == "unsigned_config" and unsigned.summary.conclusive is False
    other = apply_record(asked, record_for("speed_hips", {"pause_tau": 0.2, "pause_min_s": 0.3}))
    assert other.decision == "parameters_differ" and other.summary == asked


def test_t_met_11d_pauses_that_were_asked_for_but_not_found_still_use_a_threshold():
    layer = layer_at(6.0)  # a standing body: it is still the whole time, so ask for a pause longer than the segment
    args: dict[str, Any] = {"flags": {}, "camera_id": "camA", "view_category": "front", "min_valid_s": 0.1}
    asked = group_speed(layer, group="hips", pause_tau=0.1, pause_min_s=100.0, **args).summary
    assert asked.events == () and asked.threshold_source == "unsigned_config"
    assert any(s.uses_threshold for s in asked.statistics) and all(
        s.value is None for s in asked.statistics if s.uses_threshold
    )  # null statistics (no pause lasts 100 s) that still depend on tau and d_min
    assert apply_record(asked, record_for("speed_hips")).decision == "thresholds_not_signed"
    signed = record_for("speed_hips", {"pause_tau": 0.1, "pause_min_s": 100.0})
    assert apply_record(asked, signed).decision == "enabled"


def test_t_met_11d_a_threshold_output_of_a_metric_with_no_signable_threshold_is_never_signed():
    summary = summaries()["hip_height_b"]
    usable = Statistic(name="pretend_count", value=1.0, units="count", uses_threshold=True)
    odd = summary.model_copy(
        update={"statistics": (*summary.statistics, usable), "threshold_source": "unsigned_config"}
    )
    out = apply_record(odd, record_for("hip_height_b"))  # the registry names no threshold of this metric
    assert out.decision == "thresholds_not_signed" and out.summary.conclusive is False


def test_t_met_11d_the_decisions_come_in_a_fixed_order():
    asked = summaries(extra={"speed_hips": PAUSES})["speed_hips"]
    draft = record_for("speed_hips", status="experimental", signed_by=None, signed_at=None, supported_views=("back",))
    assert apply_record(asked, draft).decision == "record_experimental"  # the status first
    both = record_for("speed_hips", {"filter_cutoff_hz": 8.0}, supported_views=("back",))
    assert apply_record(asked, both).decision == "view_not_supported"  # then the view
    values_and_thresholds = record_for("speed_hips", {"filter_cutoff_hz": 8.0})
    assert apply_record(asked, values_and_thresholds).decision == "parameters_differ"  # then the values
    assert apply_record(asked, record_for("speed_hips")).decision == "thresholds_not_signed"  # then the thresholds


def test_t_met_11d_a_record_of_another_metric_version_or_units_is_a_programming_error_not_a_decision():
    summary = summaries()["speed_hips"]
    with pytest.raises(MetricRecordError, match="metric_name"):
        apply_record(summary, record_for("speed_hands"))
    with pytest.raises(MetricRecordError, match="metric_version"):
        apply_record(summary, record_for("speed_hips", metric_version="2"))
    with pytest.raises(MetricRecordError, match="units"):
        apply_record(summary, record_for("speed_hips", units="deg"))


def test_t_met_11d_a_summary_that_already_has_a_record_status_is_refused():
    applied = apply_record(summaries()["speed_hips"], record_for("speed_hips")).summary
    for record in (record_for("speed_hips"), None):
        with pytest.raises(MetricRecordError, match="already"):
            apply_record(applied, record)
    retired = apply_record(summaries()["hip_height_b"], record_for("hip_height_b", status="retired")).summary
    with pytest.raises(MetricRecordError, match="already"):
        apply_record(retired, None)


def test_t_met_11d_the_decision_is_a_closed_list_and_a_recorded_summary_is_frozen():
    out = apply_record(summaries()["speed_hips"], None)
    with pytest.raises(AttributeError):
        out.decision = "enabled"  # type: ignore[misc]
