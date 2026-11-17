"""T-SCH-02a..e: the models of a metric result (``schemas/metric.py``, P5.01): header, coverage, summary, file.

A good document is accepted; every bad field is refused and named. The arrays of a series and the checks across them
are T-SCH-02f and 02g (``tests/unit/test_metric_series.py``).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taiji_ai.quality.mask import REASON_NAMES
from taiji_ai.schemas._base import ManifestError, parse_manifest, read_manifest, write_manifest
from taiji_ai.schemas.metric import (
    AFTER_QUALITY,
    ELIGIBILITY,
    QUALITY,
    Coverage,
    Interval,
    MetricHeader,
    MetricSummary,
    MetricSummaryFile,
    MissingCounts,
    MissingReason,
)

REC = "0b6f3c1e-5a2d-4f8e-9c3a-7d1e2b4a6c80"
REC_2 = "5d7c1b9e-2f4a-4c6d-8e3b-1a9f0c2d4e6f"
ZERO = {name: 0 for name in MissingCounts.model_fields}


def counts(**given: int) -> dict[str, int]:
    return {**ZERO, **given}


def header(**changes: Any) -> dict[str, Any]:
    """90 rows at 30 Hz: 10 outside the interval, 10 with a bad pose (4 low_conf, 6 outlier), 10 too short, 60 ok."""
    base: dict[str, Any] = {
        "metric_name": "hip_height_a",
        "metric_version": "1",
        "units": "body_lengths",
        "recording_id": REC,
        "camera_id": "camA",
        "view_category": "front",
        "step_s": 1 / 30,
        "valid_intervals": [{"t_start": 0.0, "t_end": 2.0}],
        "coverage": {"total": 90, "eligible": 80, "quality": 70, "measured": 60},
        "missing_by_reason": counts(outside_interval=10, low_conf=4, outlier=6, too_short=10),
        "parameters": {"variant": "A", "cutoff_hz": 6.0},
        "data_sources": [],
    }
    return {**base, **changes}


def stat(name: str = "range", value: float | None = 0.25, **changes: Any) -> dict[str, Any]:
    return {"name": name, "value": value, "units": "body_lengths", "uses_threshold": False, **changes}


def event(kind: str = "max", t_start: float = 1.0, t_end: float = 1.0, **changes: Any) -> dict[str, Any]:
    return {"kind": kind, "t_start": t_start, "t_end": t_end, "value": 1.2, "uses_threshold": False, **changes}


def summary(**changes: Any) -> dict[str, Any]:
    """A measured, experimental summary with one number and one extremum."""
    base = {
        **header(),
        "evidence": "sufficient",
        "insufficient_reason": None,
        "record_status": "experimental",
        "record_version": None,
        "threshold_source": None,
        "statistics": [stat()],
        "events": [event()],
    }
    return {**base, **changes}


def nothing_measured(**changes: Any) -> dict[str, Any]:
    """90 rows, the view is not supported: no number, no event, no interval, the reason says why."""
    base = summary(
        valid_intervals=[],
        coverage={"total": 90, "eligible": 0, "quality": 0, "measured": 0},
        missing_by_reason=counts(view_not_supported=90),
        evidence="insufficient_evidence",
        insufficient_reason="view_not_supported",
        statistics=[stat(value=None)],
        events=[],
    )
    return {**base, **changes}


def edited(doc: dict[str, Any], path: tuple[str | int, ...], value: Any) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    node: Any = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


def removed(doc: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    node: Any = out
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return out


# --- the vocabulary -------------------------------------------------------------------------------------------------
def test_t_sch_02e_the_codes_one_to_six_are_the_reasons_of_the_quality_layer():
    for code in range(1, 7):
        assert MissingReason(code).name == REASON_NAMES[code]
    assert MissingReason.measured == 0 and int(MissingReason.measured) == 0


def test_t_sch_02e_every_reason_is_in_exactly_one_group_and_the_counts_have_a_field_for_each():
    groups = (*ELIGIBILITY, *QUALITY, *AFTER_QUALITY)
    reasons = [r for r in MissingReason if r != MissingReason.measured]
    assert sorted(groups) == sorted(reasons) and len(set(groups)) == len(groups)
    assert [int(r) for r in ELIGIBILITY] == [16, 17, 18] and [int(r) for r in QUALITY] == [1, 2, 3, 4, 5, 6]
    assert [int(r) for r in AFTER_QUALITY] == [19, 20, 21, 22]
    assert set(MissingCounts.model_fields) == {r.name for r in reasons}
    assert [r.name for r in QUALITY] == list(REASON_NAMES[1:])


# --- T-SCH-02a: the header ------------------------------------------------------------------------------------------
def test_t_sch_02a_good_documents_are_accepted():
    h = parse_manifest(MetricHeader, header())
    assert (
        h.units == "body_lengths"
        and h.coverage.measured == 60
        and h.valid_intervals == (Interval(t_start=0.0, t_end=2.0),)
    )
    s = parse_manifest(MetricSummary, summary())
    assert s.evidence == "sufficient" and s.statistics[0].value == 0.25 and s.events[0].kind == "max"
    n = parse_manifest(MetricSummary, nothing_measured())
    assert n.evidence == "insufficient_evidence" and n.statistics[0].value is None and n.events == ()


@pytest.mark.parametrize("key", [k for k in header()])
def test_t_sch_02a_every_field_of_the_header_is_required(key: str):
    with pytest.raises(ManifestError, match=key):
        parse_manifest(MetricHeader, removed(header(), (key,)))


@pytest.mark.parametrize(
    "key", ["units", "valid_intervals", "coverage", "metric_version", "missing_by_reason", "parameters", "data_sources"]
)
def test_t_sch_02a_a_null_is_not_an_answer_for_the_required_fields(key: str):
    with pytest.raises(ManifestError, match=key):
        parse_manifest(MetricHeader, edited(header(), (key,), None))


HEADER_BAD = [
    (lambda h: edited(h, ("units",), "meters"), "units"),
    (lambda h: edited(h, ("units",), ""), "units"),
    (lambda h: edited(h, ("units",), 3), "units"),
    (lambda h: edited(h, ("metric_name",), "Hip"), "metric_name"),
    (lambda h: edited(h, ("metric_name",), "h"), "metric_name"),
    (lambda h: edited(h, ("metric_name",), "hip height"), "metric_name"),
    (lambda h: edited(h, ("metric_version",), "0"), "metric_version"),
    (lambda h: edited(h, ("metric_version",), "01"), "metric_version"),
    (lambda h: edited(h, ("metric_version",), "1.2"), "metric_version"),
    (lambda h: edited(h, ("metric_version",), "v1"), "metric_version"),
    (lambda h: edited(h, ("metric_version",), 1), "metric_version"),
    (lambda h: edited(h, ("recording_id",), "not-a-uuid"), "recording_id"),
    (lambda h: edited(h, ("camera_id",), "cam1"), "camera_id"),
    (lambda h: edited(h, ("camera_id",), "camAB"), "camera_id"),
    (lambda h: edited(h, ("view_category",), "Front"), "view_category"),
    (lambda h: edited(h, ("view_category",), "front view"), "view_category"),
    (lambda h: edited(h, ("view_category",), ""), "view_category"),
    (lambda h: edited(h, ("step_s",), 0.0), "step_s"),
    (lambda h: edited(h, ("step_s",), -1 / 30), "step_s"),
    (lambda h: edited(h, ("step_s",), float("nan")), "step_s"),
    (lambda h: edited(h, ("step_s",), None), "step_s"),  # 90 rows have a step
    (lambda h: edited(h, ("parameters", "Variant"), "A"), "Variant"),
    (lambda h: edited(h, ("parameters", "path"), "C:/data/take.mp4"), "path"),
    (lambda h: edited(h, ("parameters", "note"), "free text with spaces"), "note"),
    (lambda h: edited(h, ("parameters", "x"), float("inf")), "x"),
    (lambda h: edited(h, ("parameters", "x"), [1, 2]), "x"),
    (lambda h: edited(h, ("parameters",), {f"p{i}": i for i in range(33)}), "parameters"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "x", "license": "a"}]), "dataset_id"),
    (lambda h: edited(h, ("data_sources",), [{"dataset_id": "D08", "license": "a"}] * 2), "data_sources"),
    (lambda h: {**h, "path": "C:/x"}, "path"),
    (lambda h: {**h, "participant": "Nguyen"}, "participant"),
    (lambda h: {**h, "file": "take.mp4"}, "file"),
    (lambda h: edited(h, ("missing_by_reason", "no_such_reason"), 1), "no_such_reason"),
    (lambda h: edited(h, ("missing_by_reason", "low_conf"), -1), "low_conf"),
    (lambda h: edited(h, ("missing_by_reason", "low_conf"), 4.5), "low_conf"),
    (lambda h: removed(h, ("missing_by_reason", "run_edge")), "run_edge"),
]


@pytest.mark.parametrize(("change", "field"), HEADER_BAD)
def test_t_sch_02a_a_bad_header_is_refused_naming_the_field(change, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricHeader, change(header()))


def test_t_sch_02a_parameters_may_hold_numbers_flags_short_names_and_null():
    h = parse_manifest(
        MetricHeader,
        edited(
            header(),
            ("parameters",),
            {"variant": "B", "n": 3, "cutoff_hz": 6.0, "mirror": False, "roll_deg": None, "group": "hip"},
        ),
    )
    assert (
        h.parameters["n"] == 3
        and h.parameters["cutoff_hz"] == 6.0
        and h.parameters["mirror"] is False
        and h.parameters["roll_deg"] is None
    )


def test_t_sch_02a_every_known_unit_is_accepted():
    for unit in ("body_lengths", "body_lengths_per_s", "deg", "px", "s", "count", "ratio"):
        assert parse_manifest(MetricHeader, edited(header(), ("units",), unit)).units == unit


# --- T-SCH-02b: intervals and coverage ------------------------------------------------------------------------------
INTERVALS_BAD = [
    ([{"t_start": 1.0, "t_end": 1.0}], "t_start"),  # empty
    ([{"t_start": 2.0, "t_end": 1.0}], "t_start"),  # backwards
    ([{"t_start": 0.0, "t_end": float("nan")}], "t_end"),
    ([{"t_start": 0.0, "t_end": 1.0}, {"t_start": 0.5, "t_end": 2.0}], "valid_intervals"),  # overlap
    ([{"t_start": 1.0, "t_end": 2.0}, {"t_start": 0.0, "t_end": 0.5}], "valid_intervals"),  # not ordered
    ([{"t_start": 0.0, "t_end": 1.0}, {"t_start": 1.0, "t_end": 2.0}], "valid_intervals"),  # touching: one run, not two
    ([], "valid_intervals"),  # 60 rows were measured: there must be an interval
]


@pytest.mark.parametrize(("intervals", "field"), INTERVALS_BAD)
def test_t_sch_02b_bad_intervals_are_refused(intervals, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricHeader, header(valid_intervals=intervals))


def test_t_sch_02b_more_intervals_than_measured_rows_and_intervals_without_a_measured_row_are_refused():
    many = [{"t_start": float(i), "t_end": i + 0.5} for i in range(61)]
    with pytest.raises(ManifestError, match="valid_intervals"):
        parse_manifest(MetricHeader, header(valid_intervals=many))
    with pytest.raises(ManifestError, match="valid_intervals"):
        parse_manifest(MetricSummary, nothing_measured(valid_intervals=[{"t_start": 0.0, "t_end": 1.0}]))


def test_t_sch_02b_two_runs_are_two_ordered_intervals_with_a_hole_between():
    h = parse_manifest(
        MetricHeader, header(valid_intervals=[{"t_start": 0.0, "t_end": 1.0}, {"t_start": 1.5, "t_end": 2.5}])
    )
    assert len(h.valid_intervals) == 2


COVERAGE_BAD = [
    ({"total": 90, "eligible": 80, "quality": 70, "measured": 71}, "coverage"),  # measured > quality
    ({"total": 90, "eligible": 80, "quality": 81, "measured": 60}, "coverage"),  # quality > eligible
    ({"total": 90, "eligible": 91, "quality": 70, "measured": 60}, "coverage"),  # eligible > total
    ({"total": 90, "eligible": 80, "quality": 70, "measured": -1}, "measured"),
    ({"total": 90.5, "eligible": 80, "quality": 70, "measured": 60}, "total"),
    ({"total": 90, "eligible": 80, "quality": 70}, "measured"),
    ({"total": 90, "eligible": 80, "quality": 70, "measured": 60, "extra": 1}, "extra"),
    (
        {"total": 90, "eligible": 79, "quality": 70, "measured": 60},
        "coverage",
    ),  # not what the counts of the reasons give
    ({"total": 91, "eligible": 80, "quality": 70, "measured": 60}, "missing_by_reason"),  # the reasons add up to 30
]


@pytest.mark.parametrize(("cov", "field"), COVERAGE_BAD)
def test_t_sch_02b_a_bad_coverage_is_refused(cov, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricHeader, header(coverage=cov))


MISSING_BAD = [
    (counts(outside_interval=10, low_conf=4, outlier=6, too_short=9), "missing_by_reason"),  # does not add up
    (counts(outside_interval=9, low_conf=5, outlier=6, too_short=10), "coverage"),  # adds up, but eligible would be 81
    (counts(outside_interval=10, low_conf=4, outlier=5, too_short=11), "coverage"),  # quality would be 71
    (counts(outside_interval=10, low_conf=4, outlier=6, too_short=10, run_edge=1), "missing_by_reason"),
]


@pytest.mark.parametrize(("missing", "field"), MISSING_BAD)
def test_t_sch_02b_the_counts_of_the_reasons_must_agree_with_the_coverage(missing, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricHeader, header(missing_by_reason=missing))


def test_t_sch_02b_every_reason_lands_in_its_own_class_of_the_coverage():
    # one row of each reason (13 rows) plus 2 measured: eligible = 15 - 3, quality = eligible - 6, measured = 2
    missing = {name: 1 for name in ZERO}
    cov = {"total": 15, "eligible": 12, "quality": 6, "measured": 2}
    h = parse_manifest(
        MetricHeader, header(coverage=cov, missing_by_reason=missing, valid_intervals=[{"t_start": 0.0, "t_end": 0.07}])
    )
    assert h.coverage.quality == 6


@pytest.mark.parametrize(
    "cov",
    [
        {"total": 10, "eligible": 11, "quality": 5, "measured": 3},
        {"total": 10, "eligible": 8, "quality": 9, "measured": 3},
        {"total": 10, "eligible": 8, "quality": 5, "measured": 6},
    ],
)
def test_t_sch_02b_the_nesting_of_the_counts_is_checked_by_the_coverage_itself(cov):
    with pytest.raises(ValueError, match="measured must not exceed"):
        Coverage(**cov)


def test_t_sch_02b_the_ratios_are_none_at_a_zero_denominator_and_never_zero_or_nan():
    c = Coverage(total=90, eligible=80, quality=70, measured=60)
    assert c.eligible_ratio() == pytest.approx(80 / 90) and c.quality_ratio() == pytest.approx(70 / 80)
    assert c.measured_ratio() == pytest.approx(60 / 90)
    empty = Coverage(total=0, eligible=0, quality=0, measured=0)
    assert empty.eligible_ratio() is None and empty.quality_ratio() is None and empty.measured_ratio() is None
    none_eligible = Coverage(total=90, eligible=0, quality=0, measured=0)
    assert (
        none_eligible.eligible_ratio() == 0.0
        and none_eligible.quality_ratio() is None
        and none_eligible.measured_ratio() == 0.0
    )


def test_t_sch_02b_seconds_are_rows_times_the_step_and_none_without_a_step():
    h = parse_manifest(MetricHeader, header())
    assert h.seconds(60) == pytest.approx(2.0)
    one = parse_manifest(
        MetricHeader,
        header(
            step_s=None, valid_intervals=[], coverage={"total": 1, "eligible": 1, "quality": 1, "measured": 0},
            missing_by_reason=counts(too_short=1),
        ),
    )  # fmt: skip
    assert one.seconds(1) is None


STEP_BAD = [
    (header(step_s=None), "step_s"),  # 90 rows without a step
    (
        header(
            step_s=0.033, valid_intervals=[], coverage={"total": 1, "eligible": 1, "quality": 1, "measured": 0},
            missing_by_reason=counts(too_short=1),
        ),
        "step_s",
    ),  # one row with a step
    (
        header(
            step_s=None, valid_intervals=[{"t_start": 0.0, "t_end": 1.0}],
            coverage={"total": 1, "eligible": 1, "quality": 1, "measured": 1}, missing_by_reason=counts(),
        ),
        "step_s",
    ),  # a measured row has a duration
]  # fmt: skip


@pytest.mark.parametrize(("doc", "field"), STEP_BAD)
def test_t_sch_02b_the_step_is_given_for_two_rows_or_more_and_null_for_fewer(doc, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricHeader, doc)


# --- T-SCH-02c: evidence --------------------------------------------------------------------------------------------
EVIDENCE_BAD = [
    (nothing_measured(statistics=[stat(value=0.0)]), "evidence"),  # no evidence and a number: even 0 is a number
    (nothing_measured(statistics=[stat(value=0.25)]), "evidence"),
    (nothing_measured(events=[event()]), "evidence"),
    (nothing_measured(insufficient_reason=None), "insufficient_reason"),
    (nothing_measured(insufficient_reason="measured"), "insufficient_reason"),
    (nothing_measured(insufficient_reason="not_a_reason"), "insufficient_reason"),
    (summary(insufficient_reason="too_short"), "insufficient_reason"),  # sufficient with a reason
    (summary(statistics=[stat(value=None)]), "evidence"),  # sufficient with no number
    (summary(statistics=[]), "evidence"),
    (summary(evidence="maybe"), "evidence"),
    (summary(statistics=[stat(value=float("nan"))]), "value"),
    (summary(statistics=[stat(value=float("inf"))]), "value"),
    (summary(statistics=[stat(value="0.25")]), "value"),
    (summary(statistics=[stat(value=True)]), "value"),
    (summary(events=[event(value=float("nan"))]), "value"),
    (summary(statistics=[stat(units="meters")]), "units"),
    (summary(statistics=[stat(name="Range")]), "name"),
    (summary(statistics=[{"name": "range", "value": 1.0, "units": "s"}]), "uses_threshold"),
    (removed(summary(), ("evidence",)), "evidence"),
    (removed(summary(), ("statistics",)), "statistics"),
    (removed(summary(), ("events",)), "events"),
    (removed(summary(), ("insufficient_reason",)), "insufficient_reason"),
]


@pytest.mark.parametrize(("doc", "field"), EVIDENCE_BAD)
def test_t_sch_02c_a_bad_summary_is_refused_naming_the_field(doc, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricSummary, doc)


def test_t_sch_02c_no_evidence_carries_no_number_not_even_zero_and_a_reason():
    s = parse_manifest(MetricSummary, nothing_measured())
    assert (
        all(st.value is None for st in s.statistics)
        and s.events == ()
        and s.insufficient_reason == "view_not_supported"
    )
    assert s.coverage.measured == 0 and s.valid_intervals == ()


def test_t_sch_02c_a_number_may_sit_beside_a_statistic_that_could_not_be_computed():
    s = parse_manifest(MetricSummary, summary(statistics=[stat("range", 0.25), stat("p95", None)]))
    assert [st.value for st in s.statistics] == [0.25, None]


def test_t_sch_02c_an_integer_is_a_number_and_a_negative_number_is_allowed():
    s = parse_manifest(
        MetricSummary, summary(statistics=[stat("n_events", 3, units="count"), stat("lean_median", -2.5, units="deg")])
    )
    assert s.statistics[0].value == 3.0 and s.statistics[1].value == -2.5


# --- T-SCH-02d: record status and thresholds ------------------------------------------------------------------------
RECORD_BAD = [
    (summary(record_status="enabled"), "record_version"),  # enabled needs the version of the signed record
    (summary(record_status="experimental", record_version="1"), "record_version"),
    (summary(record_status="retired", record_version="1"), "record_version"),
    (summary(record_status="signed"), "record_status"),
    (summary(record_status="enabled", record_version="0"), "record_version"),
    (summary(record_status="enabled", record_version=1), "record_version"),
    (removed(summary(), ("record_status",)), "record_status"),
    (removed(summary(), ("record_version",)), "record_version"),
    (removed(summary(), ("threshold_source",)), "threshold_source"),
]


@pytest.mark.parametrize(("doc", "field"), RECORD_BAD)
def test_t_sch_02d_a_bad_record_status_is_refused(doc, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricSummary, doc)


def pause(**changes: Any) -> dict[str, Any]:
    return event("pause", 0.5, 1.0, uses_threshold=True, value=None, **changes)


THRESHOLD_BAD = [
    (summary(events=[pause()]), "threshold_source"),  # a threshold output with no source
    (summary(statistics=[stat(uses_threshold=True)]), "threshold_source"),
    (summary(threshold_source="unsigned_config"), "threshold_source"),  # a source with no threshold output
    (summary(threshold_source="signed_record"), "threshold_source"),
    (summary(events=[pause()], threshold_source="signed_record"), "threshold_source"),  # signed needs enabled
    (
        summary(events=[pause()], threshold_source="unsigned_config", record_status="enabled", record_version="1"),
        "threshold_source",
    ),
    (summary(events=[pause()], threshold_source="unsigned_config", record_status="retired"), "threshold_source"),
    (summary(events=[pause()], threshold_source="from_the_wind"), "threshold_source"),
]


@pytest.mark.parametrize(("doc", "field"), THRESHOLD_BAD)
def test_t_sch_02d_a_threshold_output_is_labelled_with_its_source(doc, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricSummary, doc)


def test_t_sch_02d_an_unsigned_threshold_is_allowed_only_while_experimental_and_never_concludes():
    s = parse_manifest(MetricSummary, summary(events=[event(), pause()], threshold_source="unsigned_config"))
    assert s.record_status == "experimental" and s.threshold_source == "unsigned_config" and not s.conclusive


def test_t_sch_02d_a_signed_threshold_needs_an_enabled_record():
    s = parse_manifest(
        MetricSummary,
        summary(events=[pause()], threshold_source="signed_record", record_status="enabled", record_version="2"),
    )
    assert s.conclusive and s.record_version == "2"


@pytest.mark.parametrize(
    ("doc", "conclusive"),
    [
        (summary(), False),  # experimental: a value, no conclusion (T-MET-11)
        (summary(record_status="enabled", record_version="1"), True),
        (summary(record_status="retired"), False),
        (nothing_measured(), False),
        (nothing_measured(record_status="enabled", record_version="1"), False),  # enabled but no evidence
    ],
)
def test_t_sch_02d_only_a_sufficient_summary_with_an_enabled_record_is_conclusive(doc, conclusive: bool):
    assert parse_manifest(MetricSummary, doc).conclusive is conclusive


# --- T-SCH-02e: events, names, the file -----------------------------------------------------------------------------
EVENT_BAD = [
    (event(t_start=1.0, t_end=1.5), "events"),  # a maximum is an instant
    (event("pause", 1.0, 1.0, uses_threshold=True), "events"),  # a pause has a length
    (event("pause", 1.0, 0.5, uses_threshold=True), "events"),
    (event("pause", 0.5, 1.0, uses_threshold=False), "events"),  # a pause is defined by thresholds
    (event("max", uses_threshold=True), "events"),  # an extremum is not
    (event("min", uses_threshold=True), "events"),
    (event(t_start=2.5, t_end=2.5), "events"),  # outside the only valid interval [0, 2)
    (event(t_start=-0.1, t_end=-0.1), "events"),
    (event(kind="peak"), "kind"),
    (event(t_start=float("nan"), t_end=float("nan")), "t_start"),
]


@pytest.mark.parametrize(("ev", "field"), EVENT_BAD)
def test_t_sch_02e_a_bad_event_is_refused(ev, field: str):
    doc = summary(events=[ev], threshold_source="unsigned_config" if ev.get("uses_threshold") else None)
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricSummary, doc)


def test_t_sch_02e_an_event_must_lie_inside_a_valid_interval_not_in_a_hole():
    two = {"valid_intervals": [{"t_start": 0.0, "t_end": 1.0}, {"t_start": 1.5, "t_end": 2.5}]}
    parse_manifest(MetricSummary, summary(**two, events=[event(t_start=1.7, t_end=1.7)]))
    with pytest.raises(ManifestError, match="events"):
        parse_manifest(MetricSummary, summary(**two, events=[event(t_start=1.2, t_end=1.2)]))
    with pytest.raises(ManifestError, match="events"):
        parse_manifest(
            MetricSummary, summary(**two, events=[pause_across_a_hole()], threshold_source="unsigned_config")
        )


def pause_across_a_hole() -> dict[str, Any]:
    return event("pause", 0.8, 1.7, uses_threshold=True, value=None)


def test_t_sch_02e_an_event_may_touch_the_ends_of_its_interval():
    parse_manifest(MetricSummary, summary(events=[event(t_start=0.0, t_end=0.0), event(t_start=2.0, t_end=2.0)]))
    parse_manifest(
        MetricSummary,
        summary(events=[event("pause", 0.0, 2.0, uses_threshold=True, value=None)], threshold_source="unsigned_config"),
    )


def test_t_sch_02e_the_names_of_the_statistics_are_distinct():
    with pytest.raises(ManifestError, match="statistics"):
        parse_manifest(MetricSummary, summary(statistics=[stat("range", 0.1), stat("range", 0.2)]))


def file_doc(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "metric_summary/1", "metrics": list(entries)}


FILE_BAD = [
    (file_doc(), "metrics"),
    (file_doc(summary(), summary()), "metrics"),  # the same name and version twice
    (file_doc(summary(), summary(metric_name="hip_height_b", recording_id=REC_2)), "recording_id"),
    (file_doc(summary(), summary(metric_name="hip_height_b", camera_id="camB")), "camera_id"),
    ({**file_doc(summary()), "schema_version": "metric_summary/2"}, "schema_version"),
    ({"metrics": [summary()]}, "schema_version"),
    ({**file_doc(summary()), "path": "C:/x"}, "path"),
    ({"schema_version": "metric_summary/1"}, "metrics"),
]


@pytest.mark.parametrize(("doc", "field"), FILE_BAD)
def test_t_sch_02e_a_bad_summary_file_is_refused_naming_the_field(doc, field: str):
    with pytest.raises(ManifestError, match=field):
        parse_manifest(MetricSummaryFile, doc)


def test_t_sch_02e_two_versions_of_a_metric_and_two_metrics_may_share_a_file():
    doc = file_doc(
        summary(),
        summary(metric_version="2"),
        summary(metric_name="hip_height_b"),
        nothing_measured(metric_name="trunk_lean"),
    )
    f = parse_manifest(MetricSummaryFile, doc)
    assert [(m.metric_name, m.metric_version) for m in f.metrics] == [
        ("hip_height_a", "1"), ("hip_height_a", "2"), ("hip_height_b", "1"), ("trunk_lean", "1"),
    ]  # fmt: skip


def test_t_sch_02e_a_summary_file_round_trips_through_json_unchanged_and_has_no_nan(tmp_path: Path):
    f = parse_manifest(MetricSummaryFile, file_doc(summary(), nothing_measured(metric_name="trunk_lean")))
    path = tmp_path / "metric_summary.json"
    write_manifest(path, f)
    assert read_manifest(path, MetricSummaryFile) == f
    text = path.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    assert json.loads(text)["metrics"][1]["statistics"][0]["value"] is None  # a missing number is null


def test_t_sch_02e_a_hand_edited_file_that_contradicts_itself_is_refused(tmp_path: Path):
    f = parse_manifest(MetricSummaryFile, file_doc(summary()))
    path = tmp_path / "metric_summary.json"
    write_manifest(path, f)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["metrics"][0]["coverage"]["measured"] = 61  # one more row than the quality class has
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ManifestError, match="coverage"):
        read_manifest(path, MetricSummaryFile)


def test_t_sch_02e_a_summary_holds_no_path_no_file_name_and_no_name(tmp_path: Path):
    text = parse_manifest(MetricSummaryFile, file_doc(summary())).model_dump_json()
    for forbidden in (str(tmp_path), "\\", ".mp4", ".mov", "C:", "participant", "Nguyen"):
        assert forbidden not in text, forbidden
