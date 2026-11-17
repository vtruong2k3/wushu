"""T-SCH-02f and 02g: ``MetricSeries`` (a header and the arrays of one metric), ``build_series``, ``make_summary``.

The reason array is the single source of truth: ``build_series`` derives the valid intervals, the coverage and the
counts of the reasons from it, and ``check_series`` (run by every ``MetricSeries``) recomputes them, so a series whose
header says something the arrays do not cannot exist. The random series (02g) are derived a second time with loops.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from taiji_ai.metrics import MetricError
from taiji_ai.metrics.series import MetricSeries, build_series, check_series, make_summary
from taiji_ai.schemas._base import read_manifest, write_manifest
from taiji_ai.schemas.metric import MetricSummaryFile, MissingCounts, MissingReason
from taiji_ai.schemas.quality_layers import DataSource

REC = "0b6f3c1e-5a2d-4f8e-9c3a-7d1e2b4a6c80"
STEP = 1.0 / 30.0
CODES = (0, 1, 2, 3, 4, 5, 6, 16, 17, 18, 19, 20, 21, 22)
HAND = [16, 16, 1, 1, 0, 0, 0, 19, 0, 0, 21, 21]  # 12 rows: 2 not eligible, 2 bad pose, 5 measured, 1 + 2 not measured


def make(reason, *, step: float | None = STEP, t0: float = 0.0, t=None, values=None, **changes: Any) -> MetricSeries:
    reason = np.asarray(reason, dtype=np.uint8)
    n = len(reason)
    if t is None:
        t = t0 + np.arange(n) * STEP
    if values is None:
        values = np.where(reason == 0, 1.0 + np.arange(n) / max(n, 1), np.nan)
    if n < 2:
        step = None
    args: dict[str, Any] = {
        "metric_name": "hip_height_a", "metric_version": "1", "units": "body_lengths", "recording_id": REC,
        "camera_id": "camA", "view_category": "front", "t_sec": t, "values": values, "reason": reason, "step_s": step,
    }  # fmt: skip
    return build_series(**{**args, **changes})


def flat(intervals) -> list[float]:
    return [x for i in intervals for x in (i.t_start, i.t_end)]


def raw(**changes: Any) -> MetricSeries:
    """``build_series`` with the arrays as given (``make`` converts them): for arrays of the wrong kind."""
    n = len(HAND)
    args: dict[str, Any] = {
        "metric_name": "hip_height_a", "metric_version": "1", "units": "body_lengths", "recording_id": REC,
        "camera_id": "camA", "view_category": "front", "t_sec": np.arange(n) * STEP,
        "values": np.where(np.array(HAND) == 0, 1.0, np.nan), "reason": np.array(HAND, dtype=np.uint8), "step_s": STEP,
    }  # fmt: skip
    return build_series(**{**args, **changes})


# --- T-SCH-02f: the derivation --------------------------------------------------------------------------------------
def test_t_sch_02f_the_header_is_derived_from_the_reason_array():
    s = make(HAND)
    h = s.header
    assert (h.coverage.total, h.coverage.eligible, h.coverage.quality, h.coverage.measured) == (12, 10, 8, 5)
    assert h.missing_by_reason == MissingCounts(
        **{
            **{n: 0 for n in MissingCounts.model_fields},
            "outside_interval": 2,
            "low_conf": 2,
            "scale_unavailable": 1,
            "too_short": 2,
        }
    )
    assert flat(h.valid_intervals) == pytest.approx([4 * STEP, 7 * STEP, 8 * STEP, 10 * STEP])
    assert h.step_s == STEP and h.units == "body_lengths" and h.metric_version == "1"
    assert h.seconds(h.coverage.measured) == pytest.approx(5 * STEP)


def test_t_sch_02f_the_arrays_are_copies_read_only_and_not_shared_with_the_inputs():
    reason = np.array(HAND, dtype=np.uint8)
    t = np.arange(12) * STEP
    values = np.where(reason == 0, 1.5, np.nan)
    before = (reason.copy(), t.copy(), values.copy())
    s = make(reason, t=t, values=values)
    for given, kept in zip((reason, t, values), before, strict=True):
        assert np.array_equal(given, kept, equal_nan=True) and given.flags.writeable  # the input is untouched
    for name in ("t_sec", "values", "reason"):
        arr = getattr(s, name)
        assert not arr.flags.writeable and not any(np.shares_memory(arr, x) for x in (reason, t, values))
    with pytest.raises(ValueError, match="read-only"):
        s.values[0] = 1.0


def test_t_sch_02f_the_dtypes_are_float64_float64_uint8():
    s = make(
        HAND, values=np.where(np.array(HAND) == 0, 2.0, np.nan).astype(np.float32)
    )  # float32 is converted without loss
    assert s.t_sec.dtype == np.float64 and s.values.dtype == np.float64 and s.reason.dtype == np.uint8
    assert s.values[4] == 2.0


def test_t_sch_02f_a_clock_in_whole_milliseconds_is_a_good_series_with_the_step_of_its_grid():
    t = (
        np.round(np.arange(60) * 1000.0 / 30.0) / 1000.0
    )  # the identity grid of a coarse time base: uniform only to 0.5 ms
    s = make([0] * 60, t=t)
    assert s.header.coverage.measured == 60 and len(s.header.valid_intervals) == 1
    assert s.header.valid_intervals[0].t_end == pytest.approx(t[-1] + STEP)


def test_t_sch_02f_every_row_measured_is_one_interval_and_nothing_measured_is_none():
    whole = make([0] * 30)
    assert len(whole.header.valid_intervals) == 1 and whole.header.coverage.measured_ratio() == 1.0
    none = make([19] * 30)
    assert none.header.valid_intervals == () and none.header.coverage.measured_ratio() == 0.0
    assert none.header.missing_by_reason.scale_unavailable == 30


def test_t_sch_02f_a_series_of_no_row_and_of_one_row():
    empty = make([])
    assert empty.header.coverage.total == 0 and empty.header.step_s is None and empty.header.valid_intervals == ()
    assert empty.header.coverage.measured_ratio() is None and len(empty.t_sec) == 0
    one = make([16])
    assert one.header.coverage.total == 1 and one.header.coverage.eligible == 0 and one.header.step_s is None
    with pytest.raises(MetricError, match="step_s|measured"):
        make([0], t=np.zeros(1), values=np.ones(1))  # a measured row has a duration, one row has no step


# --- T-SCH-02f: what a series requires and what it refuses ----------------------------------------------------------
def test_t_sch_02f_a_series_cannot_be_built_without_units_valid_intervals_and_coverage():
    t, v, r = np.arange(3) * STEP, np.ones(3), np.zeros(3, np.uint8)
    for missing in ("units", "metric_version", "metric_name", "recording_id", "camera_id", "view_category", "step_s"):
        args: dict[str, Any] = {
            "metric_name": "hip_height_a", "metric_version": "1", "units": "body_lengths", "recording_id": REC,
            "camera_id": "camA", "view_category": "front", "t_sec": t, "values": v, "reason": r, "step_s": STEP,
        }  # fmt: skip
        del args[missing]
        with pytest.raises(TypeError, match=missing):
            build_series(**args)
    ok = make([0] * 3)
    with pytest.raises(TypeError):
        MetricSeries(t_sec=ok.t_sec, values=ok.values, reason=ok.reason)  # type: ignore[call-arg]  # no header
    for field in ("units", "valid_intervals", "coverage"):
        header = ok.header.model_copy(update={field: None})
        with pytest.raises(MetricError, match=field):
            dataclasses.replace(ok, header=header)


def test_t_sch_02f_build_series_names_the_field_of_a_bad_header_value():
    with pytest.raises(MetricError, match="units"):
        make(HAND, units="meters")
    with pytest.raises(MetricError, match="metric_version"):
        make(HAND, metric_version="v1")
    with pytest.raises(MetricError, match="camera_id"):
        make(HAND, camera_id="cam1")
    with pytest.raises(MetricError, match="data_sources"):
        make(HAND, data_sources=[DataSource(dataset_id="D08", license="a")] * 2)
    with pytest.raises(MetricError, match="parameters"):
        make(HAND, parameters={"path": "C:/x/take.mp4"})


def damaged_header(**update: Any):
    s = make(HAND)
    return lambda: dataclasses.replace(s, header=s.header.model_copy(update=update))


def with_array(name: str, index, value):
    def build():
        s = make(HAND)
        arr = np.array(getattr(s, name), copy=True)
        arr[index] = value
        return dataclasses.replace(s, **{name: arr})

    return build


def with_cast(name: str, dtype):
    def build():
        s = make(HAND)
        return dataclasses.replace(s, **{name: getattr(s, name).astype(dtype)})

    return build


def with_cut(name: str, stop: int):
    def build():
        s = make(HAND)
        return dataclasses.replace(s, **{name: getattr(s, name)[:stop].copy()})

    return build


def with_t(t):
    def build():
        return dataclasses.replace(make(HAND), t_sec=np.asarray(t, dtype=np.float64))

    return build


def interval_moved():
    s = make(HAND)
    first = s.header.valid_intervals[0]
    moved = (first.model_copy(update={"t_start": first.t_start + STEP}), *s.header.valid_intervals[1:])
    return dataclasses.replace(s, header=s.header.model_copy(update={"valid_intervals": moved}))


def counts_changed():
    s = make(HAND)
    miss = s.header.missing_by_reason.model_copy(update={"low_conf": 1, "outlier": 1})  # same sum, other reasons
    return dataclasses.replace(s, header=s.header.model_copy(update={"missing_by_reason": miss}))


def coverage_changed():
    """A header that is valid by itself (one row less not eligible, one more with a bad pose) but is not the rows'."""
    s = make(HAND)
    cov = s.header.coverage.model_copy(update={"eligible": 11})
    miss = s.header.missing_by_reason.model_copy(update={"outside_interval": 1, "low_conf": 3})
    return dataclasses.replace(s, header=s.header.model_copy(update={"coverage": cov, "missing_by_reason": miss}))


BAD = [
    ("NaN where measured", with_array("values", 4, np.nan), "values"),
    ("a value where not measured", with_array("values", 0, 1.0), "values"),
    ("an infinity where measured", with_array("values", 4, np.inf), "values"),
    ("an infinity where not measured", with_array("values", 0, -np.inf), "values"),
    ("reason code 7 (reserved)", with_array("reason", 0, 7), "unknown code 7"),
    ("reason code 23", with_array("reason", 0, 23), "unknown code 23"),
    ("reason code 255", with_array("reason", 0, 255), "unknown code 255"),
    ("reason int64", with_cast("reason", np.int64), "reason"),
    ("values float32", with_cast("values", np.float32), "values"),
    ("t_sec float32", with_cast("t_sec", np.float32), "t_sec"),
    ("values one row short", with_cut("values", 11), "values"),
    ("reason one row short", with_cut("reason", 11), "reason"),
    ("t_sec one row short", with_cut("t_sec", 11), "t_sec"),
    ("t_sec NaN", with_t([0.0, *[np.nan] * 1, *(np.arange(2, 12) * STEP)]), "t_sec"),
    ("t_sec not increasing", with_t(np.r_[np.arange(5) * STEP, np.arange(4, 11) * STEP]), "t_sec"),
    ("t_sec repeated", with_t(np.r_[np.arange(11) * STEP, 10 * STEP]), "t_sec"),
    ("t_sec with another step", with_t(np.arange(12) * STEP * 1.05), "step_s"),
    ("step_s that is not the clock", damaged_header(step_s=STEP * 1.05), "step_s"),
    ("step_s missing for 12 rows", damaged_header(step_s=None), "step_s"),
    ("a valid interval moved", interval_moved, "valid_intervals"),
    ("the intervals dropped", damaged_header(valid_intervals=()), "valid_intervals"),
    ("the counts of the reasons changed", counts_changed, "missing_by_reason"),
    ("the coverage changed", coverage_changed, "coverage"),
    ("a header that is not a header", damaged_header(units=None), "units"),
]


@pytest.mark.parametrize(("name", "build", "field"), BAD, ids=[b[0] for b in BAD])
def test_t_sch_02f_a_series_that_disagrees_with_itself_is_refused_naming_the_field(name, build, field: str):
    with pytest.raises(MetricError, match=field):
        build()


def test_t_sch_02f_the_step_may_be_within_one_percent_of_the_mean_interval():
    t = np.arange(12) * STEP
    make(HAND, t=t, step=STEP * 1.005)
    with pytest.raises(MetricError, match="step_s"):
        make(HAND, t=t, step=STEP * 1.03)


def test_t_sch_02f_a_short_series_of_an_identity_grid_with_a_millisecond_of_clock_noise_is_accepted():
    for n in (2, 3, 4, 6):
        t = np.round(np.arange(n) * 1000.0 / 30.0) / 1000.0
        t[-1] += 0.001  # the last row is a millisecond late: an identity grid allows it
        make([0] * n, t=t)
    t2 = np.array([0.0, 0.05])  # a step of 50 ms against a grid of 33 ms is not noise
    with pytest.raises(MetricError, match="step_s"):
        make([0, 0], t=t2)


def test_t_sch_02f_build_series_refuses_the_wrong_kind_of_array():
    with pytest.raises(MetricError, match="values"):
        raw(values=np.arange(12))  # integers cannot hold NaN
    with pytest.raises(MetricError, match="reason"):
        raw(reason=np.array(HAND, dtype=np.int64))
    with pytest.raises(MetricError, match="t_sec"):
        raw(t_sec=np.arange(12))
    with pytest.raises(MetricError, match="values"):
        raw(values=np.zeros((12, 2)))
    with pytest.raises(MetricError, match="step_s"):
        make(HAND, step=None)  # twelve rows have a step
    with pytest.raises(MetricError, match="step_s"):
        make(HAND, step=-1.0)
    with pytest.raises(MetricError, match="step_s"):
        make(HAND, step=float("nan"))


def test_t_sch_02f_check_series_is_the_check_that_every_series_has_already_passed():
    s = make(HAND)
    check_series(s)  # no error
    with pytest.raises(MetricError):
        check_series("a series")  # type: ignore[arg-type]


# --- T-SCH-02g: the summary builder ---------------------------------------------------------------------------------
def stat(name="range", value: float | None = 0.25, units="body_lengths") -> dict[str, Any]:
    return {"name": name, "value": value, "units": units, "uses_threshold": False}


def event_at(t: float) -> dict[str, Any]:
    return {"kind": "max", "t_start": t, "t_end": t, "value": 1.5, "uses_threshold": False}


def test_t_sch_02g_a_summary_copies_the_header_of_the_series_and_adds_the_evidence():
    s = make(HAND)
    m = make_summary(s, statistics=[stat()], events=[event_at(5 * STEP)])
    for field in type(s.header).model_fields:
        assert getattr(m, field) == getattr(s.header, field), field
    assert m.evidence == "sufficient" and m.insufficient_reason is None and m.record_status == "experimental"
    assert m.record_version is None and m.threshold_source is None and not m.conclusive
    assert m.statistics[0].value == 0.25 and m.events[0].t_start == pytest.approx(5 * STEP)


def test_t_sch_02g_a_reason_makes_it_insufficient_evidence_and_the_numbers_must_be_null():
    s = make([19] * 20)
    m = make_summary(s, statistics=[stat(value=None)], insufficient_reason="scale_unavailable")
    assert (
        m.evidence == "insufficient_evidence"
        and m.insufficient_reason == "scale_unavailable"
        and m.statistics[0].value is None
    )
    with pytest.raises(MetricError, match="evidence"):
        make_summary(s, statistics=[stat(value=0.0)], insufficient_reason="scale_unavailable")  # not even 0
    with pytest.raises(MetricError, match="evidence"):
        make_summary(s, statistics=[stat(value=0.25)])  # nothing measured, so not sufficient
    with pytest.raises(MetricError, match="insufficient_reason"):
        make_summary(s, statistics=[stat(value=None)], insufficient_reason="measured")


def test_t_sch_02g_the_records_and_the_thresholds_are_passed_through_and_checked():
    s = make(HAND)
    pause = {"kind": "pause", "t_start": 4 * STEP, "t_end": 6 * STEP, "value": None, "uses_threshold": True}
    m = make_summary(
        s,
        statistics=[stat()],
        events=[pause],
        threshold_source="signed_record",
        record_status="enabled",
        record_version="3",
    )
    assert m.conclusive and m.record_version == "3" and m.threshold_source == "signed_record"
    with pytest.raises(MetricError, match="threshold_source"):
        make_summary(s, statistics=[stat()], events=[pause])
    with pytest.raises(MetricError, match="record_version"):
        make_summary(s, statistics=[stat()], record_status="enabled")


def test_t_sch_02g_an_event_outside_the_valid_intervals_is_refused():
    s = make(HAND)
    with pytest.raises(MetricError, match="events"):
        make_summary(s, statistics=[stat()], events=[event_at(7.5 * STEP)])  # the hole at row 7 (scale unavailable)
    make_summary(s, statistics=[stat()], events=[event_at(6 * STEP), event_at(8 * STEP)])


def test_t_sch_02g_a_summary_file_made_from_series_round_trips(tmp_path: Path):
    a = make_summary(make(HAND), statistics=[stat()], events=[event_at(5 * STEP)])
    b = make_summary(
        make([19] * 12, metric_name="trunk_lean", units="deg"),
        statistics=[stat(value=None, units="deg")],
        insufficient_reason="scale_unavailable",
    )
    f = MetricSummaryFile(schema_version="metric_summary/1", metrics=(a, b))
    write_manifest(tmp_path / "metric_summary.json", f)
    assert read_manifest(tmp_path / "metric_summary.json", MetricSummaryFile) == f


# --- T-SCH-02g: random series, derived a second time with loops -----------------------------------------------------
def independent(reason: np.ndarray, t: np.ndarray, step: float | None):
    """Coverage numbers and runs with loops (no numpy shortcuts), from the rules of the plan."""
    names = {int(r): r.name for r in MissingReason if r != MissingReason.measured}
    counts = {n: 0 for n in names.values()}
    for code in reason:
        if code:
            counts[names[int(code)]] += 1
    total = len(reason)
    not_eligible = sum(1 for c in reason if c in (16, 17, 18))
    bad_pose = sum(1 for c in reason if c in (1, 2, 3, 4, 5, 6))
    measured = sum(1 for c in reason if c == 0)
    runs, i = [], 0
    while i < total:
        if reason[i] == 0:
            j = i
            while j + 1 < total and reason[j + 1] == 0:
                j += 1
            runs.append((float(t[i]), float(t[j]) + step))
            i = j + 1
        else:
            i += 1
    return total, total - not_eligible, total - not_eligible - bad_pose, measured, counts, runs


def random_reason(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(rng.integers(0, 60))
    mode = int(rng.integers(0, 4))
    if mode == 0:
        return np.zeros(n, np.uint8)
    if mode == 1:
        return rng.choice(CODES, size=n).astype(np.uint8)
    weights = np.array([8.0] + [1.0] * (len(CODES) - 1))
    if mode == 2:
        return rng.choice(CODES, size=n, p=weights / weights.sum()).astype(np.uint8)
    runs = np.repeat(rng.choice(CODES, size=n), int(rng.integers(1, 6)))[:n]  # long runs of one reason
    return runs.astype(np.uint8)


@pytest.mark.parametrize("seed", range(300))
def test_t_sch_02g_random_series_have_the_nesting_the_sums_and_the_runs_that_the_rules_give(seed: int):
    reason = random_reason(seed)
    n = len(reason)
    if n == 1 and reason[0] == 0:
        reason[0] = 16  # one row cannot be measured (no step, no duration)
    step = None if n < 2 else float(np.random.default_rng(seed).choice([1 / 24, 1 / 30, 1 / 60]))
    t = np.arange(n) * (step or 1.0) + float(np.random.default_rng(seed + 1).uniform(0.0, 5.0))
    values = np.where(reason == 0, np.random.default_rng(seed).normal(size=n), np.nan)
    s = build_series(
        metric_name="speed_hand", metric_version="2", units="body_lengths_per_s", recording_id=REC, camera_id="camB",
        view_category="side", t_sec=t, values=values, reason=reason, step_s=step,
    )  # fmt: skip
    h = s.header
    total, eligible, quality, measured, counts, runs = independent(reason, t, step)
    assert (h.coverage.total, h.coverage.eligible, h.coverage.quality, h.coverage.measured) == (
        total,
        eligible,
        quality,
        measured,
    )
    assert h.coverage.measured <= h.coverage.quality <= h.coverage.eligible <= h.coverage.total
    assert h.missing_by_reason.model_dump() == counts
    assert sum(counts.values()) == total - measured
    assert flat(h.valid_intervals) == pytest.approx([x for run in runs for x in run])
    if step is not None:
        assert h.seconds(measured) == pytest.approx(measured * step)
    if total == 0:
        assert h.coverage.eligible_ratio() is None and h.coverage.measured_ratio() is None
    if eligible == 0:
        assert h.coverage.quality_ratio() is None
    assert np.array_equal(np.isfinite(s.values), s.reason == 0)
    if measured:  # a summary of the series is valid whatever the runs are
        assert make_summary(s, statistics=[stat(units="body_lengths_per_s")]).evidence == "sufficient"
    else:
        first = int(reason[reason != 0][0]) if (reason != 0).any() else 19
        m = make_summary(
            s, statistics=[stat(value=None, units="body_lengths_per_s")], insufficient_reason=MissingReason(first).name
        )
        assert m.evidence == "insufficient_evidence" and m.statistics[0].value is None
