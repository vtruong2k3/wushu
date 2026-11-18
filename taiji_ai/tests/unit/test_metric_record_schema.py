"""T-MET-11a: ``MetricRecord``, the model of a signed metric record (v3 section 8.2, P5.09).

An ``enabled`` record is the only thing that lets a metric draw a conclusion, so what it may hold is strict: a coach's
signature, every number of the record, an error below the smallest useful change (G03), and the cut-off bound next to
the thresholds (DEC-0061). A draft or a signed decision to keep a metric experimental may be incomplete.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from taiji_ai.schemas.metric_record import MAX_INTENDED_USE, MetricRecord

ENABLED: dict[str, Any] = {
    "metric_name": "speed_hips",
    "version": "3",
    "metric_version": "1",
    "units": "body_lengths_per_s",
    "status": "enabled",
    "intended_use": "Dùng để so sánh nhịp chuyển động của hông trong một thức, không dùng để chấm điểm",
    "supported_views": ("front", "side"),
    "gold_reference": "REPORT-P10-02",
    "human_variability": 0.05,
    "smallest_useful_change": 0.2,
    "measurement_error": 0.08,
    "min_valid_duration_s": 0.5,
    "parameters": {"filter_cutoff_hz": 6.0, "pause_tau": 0.1, "pause_min_s": 0.3},
    "data_sources": (),
    "signed_by": "cli:H",
    "signed_at": date(2026, 12, 1),
}
DRAFT: dict[str, Any] = {
    "metric_name": "speed_hips",
    "version": "1",
    "metric_version": "1",
    "units": "body_lengths_per_s",
    "status": "experimental",
    "intended_use": "draft",
    "supported_views": (),
    "gold_reference": None,
    "human_variability": None,
    "smallest_useful_change": None,
    "measurement_error": None,
    "min_valid_duration_s": None,
    "parameters": {},
    "data_sources": (),
    "signed_by": None,
    "signed_at": None,
}


def make(base: dict[str, Any] = ENABLED, **changes: Any) -> MetricRecord:
    return MetricRecord.model_validate({**base, **changes})


def refused(match: str, base: dict[str, Any] = ENABLED, **changes: Any) -> None:
    with pytest.raises(ValidationError, match=match):
        make(base, **changes)


# --- the shapes -------------------------------------------------------------------------------------------------------
def test_t_met_11a_a_complete_enabled_record_is_valid_and_survives_a_round_trip():
    record = make()
    assert record.status == "enabled" and record.version == "3" and record.metric_version == "1"
    assert MetricRecord.model_validate(record.model_dump()) == record
    assert MetricRecord.model_validate_json(record.model_dump_json()) == record
    assert record.signed_at == date(2026, 12, 1) and record.supported_views == ("front", "side")


def test_t_met_11a_a_draft_may_be_empty_and_unsigned():
    record = make(DRAFT)
    assert record.status == "experimental" and record.signed_by is None and record.supported_views == ()


def test_t_met_11a_a_signed_decision_to_keep_a_metric_experimental_may_have_an_error_as_large_as_the_change():
    record = make(
        DRAFT,
        gold_reference="REPORT-P10-02",
        human_variability=0.05,
        smallest_useful_change=0.1,
        measurement_error=0.3,  # the finding: the metric cannot see the change the coach wants (v3 8.2)
        min_valid_duration_s=0.5,
        signed_by="cli:H2",
        signed_at=date(2026, 12, 1),
    )
    assert record.status == "experimental" and record.measurement_error > record.smallest_useful_change


def test_t_met_11a_a_retired_record_says_who_retired_it_and_when():
    make(ENABLED, status="retired", signed_by="cli:H2", signed_at=date(2027, 1, 5))
    refused("retired record needs signed_by", status="retired", signed_by=None)
    refused("retired record needs signed_at", status="retired", signed_at=None)


def test_t_met_11a_an_unsigned_or_half_signed_experimental_record_is_not_a_record_of_a_decision():
    refused("signed_by and signed_at", DRAFT, signed_by="cli:H")
    refused("signed_by and signed_at", DRAFT, signed_at=date(2026, 12, 1))


# --- an enabled record is complete ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "field",
    [
        "gold_reference",
        "human_variability",
        "smallest_useful_change",
        "measurement_error",
        "min_valid_duration_s",
        "signed_by",
        "signed_at",
    ],
)
def test_t_met_11a_an_enabled_record_names_the_missing_field(field):
    refused(f"enabled record needs {field}", **{field: None})


def test_t_met_11a_an_enabled_record_needs_a_view():
    refused("enabled record needs at least one supported view", supported_views=())


def test_t_met_11a_the_error_must_be_below_the_smallest_useful_change_and_equal_is_refused():
    refused("measurement_error must be below smallest_useful_change", measurement_error=0.2, smallest_useful_change=0.2)
    refused("measurement_error must be below smallest_useful_change", measurement_error=0.3)
    make(measurement_error=0.1999999, smallest_useful_change=0.2)


def test_t_met_11a_an_enabled_record_binds_a_positive_cutoff():
    ok = {k: v for k, v in ENABLED["parameters"].items() if k != "filter_cutoff_hz"}
    refused("enabled record must bind filter_cutoff_hz", parameters=ok)
    refused("filter_cutoff_hz must be a number above 0", parameters={**ok, "filter_cutoff_hz": None})
    refused("filter_cutoff_hz must be a number above 0", parameters={**ok, "filter_cutoff_hz": 0.0})
    refused("filter_cutoff_hz must be a number above 0", parameters={**ok, "filter_cutoff_hz": -6.0})
    refused("filter_cutoff_hz must be a number above 0", parameters={**ok, "filter_cutoff_hz": "6"})
    refused("filter_cutoff_hz must be a number above 0", parameters={**ok, "filter_cutoff_hz": True})
    make(parameters={**ok, "filter_cutoff_hz": 4})  # an integer is a number
    make(DRAFT, parameters={"pause_tau": 0.1, "pause_min_s": 0.3})  # a draft need not bind it yet


def test_t_met_11a_the_two_pause_thresholds_are_bound_together_or_not_at_all():
    cut = {"filter_cutoff_hz": 6.0}
    make(parameters=cut)  # a record may bind neither (the pauses are then not signed: P5.09 apply_record)
    refused("pause_tau and pause_min_s", parameters={**cut, "pause_tau": 0.1})
    refused("pause_tau and pause_min_s", parameters={**cut, "pause_min_s": 0.3})
    refused("pause_tau and pause_min_s", base=DRAFT, parameters={"pause_tau": 0.1})  # also a draft: it is a pair
    refused("pause_tau must be a number above 0", parameters={**cut, "pause_tau": None, "pause_min_s": 0.3})
    refused("pause_min_s must be a number above 0", parameters={**cut, "pause_tau": 0.1, "pause_min_s": 0.0})
    refused("pause_tau must be a number above 0", parameters={**cut, "pause_tau": 0.0, "pause_min_s": 0.3})


def test_t_met_11a_the_minimum_duration_is_the_column_not_a_second_parameter():
    refused("min_valid_duration_s", parameters={"filter_cutoff_hz": 6.0, "min_valid_s": 0.5})


# --- fields -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["human_variability", "measurement_error", "min_valid_duration_s"])
def test_t_met_11a_a_number_may_be_zero_but_not_negative_nor_not_finite(field):
    make(**{field: 0.0, "smallest_useful_change": 1.0, "measurement_error": 0.0})
    refused("greater than or equal to 0", **{field: -0.001})
    for bad in (math.nan, math.inf, -math.inf):
        refused("finite", **{field: bad})
    refused("valid number", **{field: "0.1"})
    refused("valid number", **{field: True})


def test_t_met_11a_the_smallest_useful_change_is_above_zero():
    refused("greater than 0", smallest_useful_change=0.0)
    refused("greater than 0", smallest_useful_change=-0.1)
    refused("finite", smallest_useful_change=math.inf)


@pytest.mark.parametrize("version", ["0", "01", "v1", "", "1.2", "10000", "-1"])
def test_t_met_11a_versions_are_positive_integers_as_text(version):
    refused("String should match pattern", version=version)
    refused("String should match pattern", metric_version=version)


@pytest.mark.parametrize("name", ["Speed", "1speed", "speed hips", "a", "x" * 65, "speed-hips", ""])
def test_t_met_11a_metric_names_are_patterns(name):
    refused("String should match pattern", metric_name=name)


def test_t_met_11a_units_are_a_closed_list():
    refused("Input should be", units="m/s")
    refused("Input should be", units="")
    make(units="deg")


def test_t_met_11a_the_intended_use_is_one_short_non_blank_line_and_may_be_vietnamese():
    for bad in ("", "   ", "a\nb", "a\rb", "a\tb", "a\x00b", "a\x7fb", "x" * (MAX_INTENDED_USE + 1)):
        refused("intended_use", intended_use=bad)
    make(intended_use="x" * MAX_INTENDED_USE)
    make(intended_use="Đo độ nghiêng thân của người tập ở góc nhìn chính diện")


def test_t_met_11a_views_are_known_categories_without_unknown_and_without_repeats():
    refused("Input should be", supported_views=("front", "unknown"))
    refused("Input should be", supported_views=("diagonal",))
    refused("supported_views must not repeat", supported_views=("front", "front"))
    make(supported_views=("back", "oblique", "side", "front"))


@pytest.mark.parametrize("code", ["a/b", "a\\b", "has space", "x" * 65, "", "C:file", "ü"])
def test_t_met_11a_the_gold_reference_is_a_short_code_not_a_path(code):
    refused("gold_reference", gold_reference=code)


@pytest.mark.parametrize("who", ["cli:A", "cli:B", "cli:O", "cli:", "cli:H123", "H", "Dr Lan", "cli:h", ""])
def test_t_met_11a_a_signature_is_a_coach_role_code_never_a_name(who):
    refused("signed_by", signed_by=who)


@pytest.mark.parametrize("who", ["cli:H", "cli:H1", "cli:H12"])
def test_t_met_11a_the_coach_role_codes_are_accepted(who):
    assert make(signed_by=who).signed_by == who


def test_t_met_11a_parameters_are_bounded_keys_and_short_values():
    many = {f"p{i}": 1 for i in range(33)}
    refused("at most 32", parameters={"filter_cutoff_hz": 6.0, **many})
    refused("String should match pattern", parameters={"filter_cutoff_hz": 6.0, "Bad Key": 1})
    refused("String should match pattern", parameters={"filter_cutoff_hz": 6.0, "path": "C:/data/x"})
    refused("finite", parameters={"filter_cutoff_hz": 6.0, "x": math.nan})
    make(parameters={"filter_cutoff_hz": 6.0, "min_scale_s": None, "group": "hips", "flag": True, "n": 3})


def test_t_met_11a_data_sources_name_each_dataset_once():
    source = {"dataset_id": "D08", "license": "internal"}
    make(data_sources=(source,))
    refused("data_sources must name each dataset once", data_sources=(source, {**source}))
    make(data_sources=(source, {"dataset_id": "D20", "license": "internal"}))


def test_t_met_11a_a_record_is_frozen_and_refuses_unknown_fields():
    record = make()
    with pytest.raises(ValidationError, match="frozen"):
        record.status = "retired"  # type: ignore[misc]
    refused("Extra inputs", threshold=0.1)


@pytest.mark.parametrize("field", sorted(ENABLED))
def test_t_met_11a_every_field_is_required_an_unknown_value_is_null_never_a_default(field):
    data = {k: v for k, v in ENABLED.items() if k != field}
    with pytest.raises(ValidationError, match=f"{field}\n  Field required"):
        MetricRecord.model_validate(data)
