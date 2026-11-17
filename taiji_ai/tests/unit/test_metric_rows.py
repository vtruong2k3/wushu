"""T-MET-03a to 03d, T-MET-06a and T-MET-08a: the glue every metric uses (P5.03, P5.05, P5.06): the rows of a
segment and their neighbours, the stable intervals, the eligibility of a row (the intervals, the view, the flags), the
runs that are too short, the reason a summary gives when it has no evidence, the assembly of a series, and the
scale of a set of rows."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from helpers.metric_layers import LH, LS, RECORDING_ID, SOURCES, body, bridge, cells, drop, edited, exact_layer
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.rows import (
    FLAGS,
    VIEWS,
    ScaleEstimate,
    SegmentRows,
    assemble_series,
    drop_short_runs,
    eligibility,
    evidence_reason,
    interval_mask,
    leading_reason,
    neighbour_rows,
    scale_of,
    segment_rows,
)
from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.schemas.ontology import load_ontology


# --- T-MET-03a: the rows of a segment -------------------------------------------------------------------------------
def marked_layer(n: int = 40, segment=(5, 35)):
    """A layer whose row ``g`` has the mid-hip at ``y = 400 + g``, so every row can be told apart."""
    return exact_layer(body(n, 400.0 + np.arange(n)), segment=segment)


def test_t_met_03a_the_segment_rows_are_exactly_the_grid_in_segment_rows_and_not_the_margins():
    layer = marked_layer()
    expected = np.arange(5, 35)  # independent of the code under test: the segment was asked as rows 5 to 34
    assert np.array_equal(np.flatnonzero(layer.grid_in_segment), expected)
    rows = segment_rows(layer)
    assert isinstance(rows, SegmentRows)
    assert len(rows.t_sec) == 30 and rows.keypoints.shape == (30, NUM_JOINTS, 2)
    assert np.array_equal(rows.t_sec, layer.t_grid[expected])
    assert np.array_equal(rows.keypoints, layer.keypoints[expected])
    assert np.array_equal(rows.reason, layer.reason[expected])
    assert np.array_equal(rows.interpolated, layer.interpolated[expected])
    mid_hip_y = (rows.keypoints[:, 11, 1].astype(np.float64) + rows.keypoints[:, 12, 1]) / 2.0
    assert mid_hip_y[0] == 405.0 and mid_hip_y[-1] == 434.0  # the first row of the segment and the last: no margin row


def test_t_met_03a_dtypes_the_step_and_the_provenance_are_those_of_the_layer_and_the_arrays_are_read_only():
    layer = marked_layer()
    rows = segment_rows(layer)
    assert rows.t_sec.dtype == np.float64 and rows.keypoints.dtype == np.float32
    assert rows.reason.dtype == np.uint8 and rows.interpolated.dtype == np.bool_
    assert rows.step_s == layer.meta.timeline.step_s and rows.step_s == pytest.approx(1 / 30)
    assert rows.recording_id == RECORDING_ID and rows.data_sources == SOURCES
    for array in (rows.t_sec, rows.keypoints, rows.reason, rows.interpolated):
        assert not array.flags.writeable
    assert not np.shares_memory(rows.keypoints, layer.keypoints)  # a copy: the layer cannot be changed through it


def test_t_met_03a_a_segment_of_one_row_or_of_none_has_no_step():
    none = segment_rows(edited(marked_layer(), grid_in_segment=np.zeros(40, dtype=bool)))
    assert len(none.t_sec) == 0 and none.keypoints.shape == (0, NUM_JOINTS, 2) and none.step_s is None
    only = np.zeros(40, dtype=bool)
    only[12] = True
    one = segment_rows(edited(marked_layer(), grid_in_segment=only))
    assert len(one.t_sec) == 1 and one.step_s is None  # the layer has a step, a series of one row has none
    two = np.zeros(40, dtype=bool)
    two[12:14] = True
    assert segment_rows(edited(marked_layer(), grid_in_segment=two)).step_s == pytest.approx(1 / 30)


def test_t_met_03a_a_layer_that_is_not_one_or_a_broken_segment_is_refused():
    split = np.zeros(40, dtype=bool)
    split[[5, 6, 9]] = True
    with pytest.raises(MetricError, match="contiguous"):
        segment_rows(edited(marked_layer(), grid_in_segment=split))
    for bad in (None, "layer", np.zeros((3, NUM_JOINTS, 2))):
        with pytest.raises(MetricError, match="PoseFiltered"):
            segment_rows(bad)  # type: ignore[arg-type]


# --- T-MET-03b: the stable intervals --------------------------------------------------------------------------------
T10 = np.arange(10) / 10.0  # 0.0, 0.1, ... 0.9


def mask_rows(intervals: Any, t: np.ndarray = T10) -> list[int]:
    return np.flatnonzero(interval_mask(t, intervals)).tolist()


def test_t_met_03b_an_interval_is_half_open_a_row_at_the_start_is_in_and_one_at_the_end_is_out():
    assert mask_rows([(0.2, 0.5)]) == [2, 3, 4]
    assert mask_rows([(0.0, 0.1)]) == [0]
    assert mask_rows([(0.85, 5.0)]) == [9]


def test_t_met_03b_a_row_one_float_step_off_a_boundary_is_on_it_and_one_further_is_not():
    t = np.array([0.2 - 1e-10, 0.2 - 1e-8, 0.5 - 1e-10, 0.5 - 2e-9])
    assert mask_rows([(0.2, 0.5)], t) == [0, 3]  # 1e-10 before the start: in; 1e-10 before the end: out (on it)


def test_t_met_03b_several_intervals_are_a_union_whatever_their_order_or_overlap():
    assert mask_rows([(0.7, 0.9), (0.0, 0.2)]) == [0, 1, 7, 8]
    assert mask_rows([(0.1, 0.4), (0.3, 0.6)]) == [1, 2, 3, 4, 5]
    assert mask_rows([(0.1, 0.3), (0.1, 0.3)]) == [1, 2]
    assert mask_rows(np.array([[0.2, 0.4]])) == [2, 3]  # an array of pairs is a list of intervals


def test_t_met_03b_no_interval_gives_no_row_and_no_row_gives_an_empty_mask():
    assert mask_rows([]) == []
    out = interval_mask(np.zeros(0), [(0.0, 1.0)])
    assert out.shape == (0,) and out.dtype == np.bool_
    assert not interval_mask(T10, [(0.2, 0.5)]).flags.writeable


INTERVAL_BAD = [
    ([(1.0, 1.0)], "intervals[0]"),
    ([(0.0, 0.5), (2.0, 1.0)], "intervals[1]"),
    ([(np.nan, 1.0)], "intervals[0]"),
    ([(0.0, np.inf)], "intervals[0]"),
    ([(0.0,)], "intervals[0]"),
    ([(0.0, 1.0, 2.0)], "intervals[0]"),
    ([("a", "b")], "intervals[0]"),
    ([None], "intervals[0]"),
    ([(True, 2.0)], "intervals[0]"),
    ("ab", "intervals"),
    ({"a": (0.0, 1.0)}, "intervals"),
    (None, "intervals"),
    ((0.0, 1.0), "intervals"),  # a pair is not a list of intervals
]


@pytest.mark.parametrize(("intervals", "message"), INTERVAL_BAD, ids=[str(b[0]) for b in INTERVAL_BAD])
def test_t_met_03b_a_bad_interval_is_refused_naming_it(intervals: Any, message: str):
    with pytest.raises(MetricError, match=message.replace("[", r"\[").replace("]", r"\]")):
        interval_mask(T10, intervals)


def test_t_met_03b_the_error_names_the_argument_the_caller_knows_the_intervals_by():
    with pytest.raises(MetricError, match=r"stable_intervals\[1\]"):
        interval_mask(T10, [(0.0, 1.0), (3.0, 2.0)], name="stable_intervals")
    with pytest.raises(MetricError, match="stable_intervals must be a list"):
        eligibility(T10, intervals="all", flags={}, blocking=PERSPECTIVE, name="stable_intervals")  # type: ignore[arg-type]


def test_t_met_03b_the_times_must_be_a_one_dimensional_float_array():
    for bad in (np.arange(5), np.zeros((2, 2)), [0.0, 1.0], None):
        with pytest.raises(MetricError, match="t_sec"):
            interval_mask(bad, [(0.0, 1.0)])  # type: ignore[arg-type]


# --- T-MET-03c: the eligibility of a row ----------------------------------------------------------------------------
PERSPECTIVE = ("perspective_shift",)


def test_t_met_03c_a_row_outside_every_interval_is_16_and_one_inside_with_no_flag_is_0():
    out = eligibility(T10, intervals=[(0.2, 0.5)], flags={}, blocking=PERSPECTIVE)
    assert out.tolist() == [16, 16, 0, 0, 0, 16, 16, 16, 16, 16]
    assert out.dtype == np.uint8 and not out.flags.writeable


def test_t_met_03c_a_blocking_flag_makes_the_rows_inside_18_and_16_still_wins_outside():
    out = eligibility(T10, intervals=[(0.2, 0.5)], flags={"perspective_shift": True}, blocking=PERSPECTIVE)
    assert out.tolist() == [16, 16, 18, 18, 18, 16, 16, 16, 16, 16]


def test_t_met_03c_a_flag_that_is_not_blocking_or_is_false_changes_nothing():
    base = eligibility(T10, intervals=[(0.0, 1.0)], flags={}, blocking=PERSPECTIVE)
    for flags in (
        {"perspective_shift": False},
        {"occlusion": True},
        {"orientation_change": True, "occlusion": True},
        {"perspective_shift": False, "occlusion": True},
    ):
        assert np.array_equal(eligibility(T10, intervals=[(0.0, 1.0)], flags=flags, blocking=PERSPECTIVE), base), flags
    assert not base.any()
    # and the list of blocking flags is the metric's: with another list another flag blocks
    out = eligibility(
        T10, intervals=[(0.0, 1.0)], flags={"occlusion": True, "perspective_shift": True}, blocking=("occlusion",)
    )
    assert (out == 18).all()


def test_t_met_03c_an_empty_list_of_intervals_makes_every_row_16_even_with_no_flag():
    assert (eligibility(T10, intervals=[], flags={}, blocking=PERSPECTIVE) == 16).all()


FLAG_BAD = [
    ({"perspective_shifts": True}, "flags"),
    ({"occlusion": 1}, "flags"),
    ({"occlusion": "yes"}, "flags"),
    ({"perspective_shift": None}, "flags"),
    ({"perspective_shift": np.int64(1)}, "flags"),
    ([("occlusion", True)], "flags"),
    (None, "flags"),
]


@pytest.mark.parametrize(("flags", "message"), FLAG_BAD, ids=[str(b[0]) for b in FLAG_BAD])
def test_t_met_03c_an_unknown_flag_name_or_a_value_that_is_not_a_bool_is_refused_naming_the_flags(flags, message):
    with pytest.raises(MetricError, match=message):
        eligibility(T10, intervals=[(0.0, 1.0)], flags=flags, blocking=PERSPECTIVE)


def test_t_met_03c_the_blocking_names_must_be_flags_and_the_intervals_are_checked_too():
    with pytest.raises(MetricError, match="blocking"):
        eligibility(T10, intervals=[(0.0, 1.0)], flags={}, blocking=("tilt",))
    with pytest.raises(MetricError, match="intervals"):
        eligibility(T10, intervals=[(1.0, 0.0)], flags={}, blocking=PERSPECTIVE)


def test_t_met_03c_the_flags_are_the_ones_of_the_ontology():
    assert FLAGS == tuple(load_ontology().flags)


# --- T-MET-03d: runs that are too short, and the reason without evidence --------------------------------------------
STEP = 0.1


def run_reasons(codes: list[int], min_valid_s: float | None, step_s: float | None = STEP) -> list[int]:
    return drop_short_runs(np.array(codes, dtype=np.uint8), step_s=step_s, min_valid_s=min_valid_s).tolist()


def test_t_met_03d_a_run_of_exactly_the_minimum_stays_and_a_shorter_one_becomes_21():
    codes = [0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0]
    assert run_reasons(codes, 0.3) == [0, 0, 0, 1, 21, 21, 1, 0, 0, 0, 0]  # 3 rows = 0.3 s stays; 2 rows do not
    assert run_reasons(codes, 0.4) == [21, 21, 21, 1, 21, 21, 1, 0, 0, 0, 0]  # 4 rows = 0.4 s stays
    assert run_reasons(codes, 0.5) == [21, 21, 21, 1, 21, 21, 1, 21, 21, 21, 21]


def test_t_met_03d_the_duration_of_a_run_is_its_rows_times_the_step_with_a_nanosecond_of_tolerance():
    step = 1.0 / 30.0
    assert run_reasons([0, 0, 0], 0.1, step) == [0, 0, 0]  # 3 x (1/30) is 0.1 up to a rounding
    assert run_reasons([0, 0, 0], 0.1 + 1e-6, step) == [21, 21, 21]


def test_t_met_03d_a_run_that_is_short_by_less_than_a_nanosecond_is_not_short():
    step = 1.0 / 30.0  # 3 rows last 0.1 s up to a rounding; asking 0.1 s plus a picosecond must not cut them
    assert run_reasons([0, 0, 0], 0.1 + 1e-12, step) == [0, 0, 0]
    assert run_reasons([0, 0, 0], 0.1 + 1e-8, step) == [21, 21, 21]  # a hundredth of a microsecond short: it is


def test_t_met_03d_two_runs_are_judged_apart_and_only_measured_rows_change():
    assert run_reasons([0, 0, 0, 0, 5, 0, 0, 16, 0], 0.3) == [0, 0, 0, 0, 5, 21, 21, 16, 21]


def test_t_met_03d_no_minimum_changes_nothing_and_the_result_is_a_new_array():
    codes = np.array([0, 1, 0, 0, 2, 0], dtype=np.uint8)
    out = drop_short_runs(codes, step_s=STEP, min_valid_s=None)
    assert np.array_equal(out, codes) and out is not codes and not out.flags.writeable
    assert codes.tolist() == [0, 1, 0, 0, 2, 0]  # the input is untouched
    demoted = drop_short_runs(codes, step_s=STEP, min_valid_s=0.5)
    assert demoted.tolist() == [21, 1, 21, 21, 2, 21] and codes.tolist() == [0, 1, 0, 0, 2, 0]  # also with a minimum


def test_t_met_03d_without_a_step_a_measured_row_has_no_duration_and_is_21_whatever_the_minimum():
    assert run_reasons([0], None, None) == [21]
    assert run_reasons([0], 0.01, None) == [21]
    assert run_reasons([5], None, None) == [5]
    assert run_reasons([], None, None) == []


DROP_BAD = [
    (np.array([0, 1], dtype=np.int64), STEP, None, "reason"),
    (np.zeros((2, 2), dtype=np.uint8), STEP, None, "reason"),
    ([0, 1], STEP, None, "reason"),
    (np.zeros(3, dtype=np.uint8), 0.0, None, "step_s"),
    (np.zeros(3, dtype=np.uint8), -0.1, None, "step_s"),
    (np.zeros(3, dtype=np.uint8), float("nan"), None, "step_s"),
    (np.zeros(3, dtype=np.uint8), "0.1", None, "step_s"),
    (np.zeros(3, dtype=np.uint8), STEP, 0.0, "min_valid_s"),
    (np.zeros(3, dtype=np.uint8), STEP, -1.0, "min_valid_s"),
    (np.zeros(3, dtype=np.uint8), STEP, float("nan"), "min_valid_s"),
    (np.zeros(3, dtype=np.uint8), STEP, float("inf"), "min_valid_s"),
    (np.zeros(3, dtype=np.uint8), STEP, "1", "min_valid_s"),
    (np.zeros(3, dtype=np.uint8), STEP, True, "min_valid_s"),
]


@pytest.mark.parametrize(("reason", "step", "minimum", "message"), DROP_BAD, ids=[str(i) for i in range(len(DROP_BAD))])
def test_t_met_03d_bad_arguments_of_the_short_run_rule_are_refused_naming_them(reason, step, minimum, message):
    with pytest.raises(MetricError, match=message):
        drop_short_runs(reason, step_s=step, min_valid_s=minimum)


def test_t_met_03d_the_reason_without_evidence_is_the_one_with_the_most_rows_and_the_smaller_code_on_a_tie():
    def lead(codes: list[int]) -> str | None:
        return leading_reason(np.array(codes, dtype=np.uint8))

    assert lead([0, 1, 1, 2, 16]) == "low_conf"
    assert lead([0, 2, 2, 1, 1]) == "low_conf"  # a tie: the smaller code
    assert lead([16, 16, 5, 5, 5, 0, 0, 21]) == "outlier"
    assert lead([22, 0, 19, 19]) == "scale_unavailable"
    assert lead([20, 20, 20, 1]) == "reference_missing"
    assert lead([0, 0, 0]) is None  # nothing is missing: there is no reason to give
    assert lead([]) is None


def test_t_met_03d_a_bad_reason_array_is_refused():
    for bad in (np.zeros(3, dtype=np.int64), np.zeros((2, 2), dtype=np.uint8), None):
        with pytest.raises(MetricError, match="reason"):
            leading_reason(bad)  # type: ignore[arg-type]
    with pytest.raises(MetricError, match="reason"):
        leading_reason(np.array([0, 7], dtype=np.uint8))  # 7 is not a code of the vocabulary


# --- T-MET-06a: the view gate, the whole segment, the reason without evidence, the assembly of a series -------------
LEAN_BLOCKING = ("orientation_change",)


def gate(intervals: Any, view: str | None, supported: Any, flags: dict[str, bool] | None = None, t=T10) -> list[int]:
    out = eligibility(
        t, intervals=intervals, flags=flags or {}, blocking=LEAN_BLOCKING, view=view, supported_views=supported
    )
    return out.tolist()


def test_t_met_06a_the_views_are_the_ones_of_the_ontology():
    assert VIEWS == tuple(load_ontology().view_categories)


def test_t_met_06a_a_row_in_an_interval_is_17_when_the_view_is_not_supported_and_0_when_it_is():
    window = [(0.2, 0.5)]
    assert gate(window, "side", ("front",)) == [16, 16, 17, 17, 17, 16, 16, 16, 16, 16]  # 16 outside, 17 inside
    assert gate(window, "front", ("front",)) == [16, 16, 0, 0, 0, 16, 16, 16, 16, 16]
    assert gate(window, "back", ("front", "back")) == [
        16,
        16,
        0,
        0,
        0,
        16,
        16,
        16,
        16,
        16,
    ]  # a record can widen the set
    assert gate(window, "front", ("back",)) == [16, 16, 17, 17, 17, 16, 16, 16, 16, 16]  # ... or narrow it


def test_t_met_06a_the_precedence_is_16_then_17_then_18():
    window = [(0.2, 0.5)]
    flagged = {"orientation_change": True}
    assert gate(window, "side", ("front",), flagged) == [16, 16, 17, 17, 17, 16, 16, 16, 16, 16]  # 17 beats 18
    assert gate(window, "front", ("front",), flagged) == [16, 16, 18, 18, 18, 16, 16, 16, 16, 16]  # a fitting view: 18
    assert gate(window, "front", ("front",), {"orientation_change": False}) == [16, 16, 0, 0, 0, 16, 16, 16, 16, 16]
    assert gate(window, "front", ("front",), {"occlusion": True}) == [
        16,
        16,
        0,
        0,
        0,
        16,
        16,
        16,
        16,
        16,
    ]  # not blocking


def test_t_met_06a_no_interval_at_all_means_the_whole_segment_and_an_empty_list_means_no_row():
    assert gate(None, "front", ("front",)) == [0] * 10
    assert gate(None, "side", ("front",)) == [17] * 10
    assert gate(None, "front", ("front",), {"orientation_change": True}) == [18] * 10
    assert gate([], "front", ("front",)) == [16] * 10  # the coach confirmed nothing
    assert gate(None, "front", ("front",), t=np.zeros(0)) == []
    assert gate(None, None, None) == [0] * 10  # without a view the rows are eligible: nothing asks for a view


def test_t_met_06a_a_call_without_a_view_is_the_call_of_p5_03_and_a_none_for_a_list_of_intervals_is_not_a_string():
    assert (
        eligibility(T10, intervals=[(0.2, 0.5)], flags={}, blocking=PERSPECTIVE).tolist()
        == [16, 16, 0, 0, 0] + [16] * 5
    )
    with pytest.raises(MetricError, match="intervals"):
        eligibility(T10, intervals="all", flags={}, blocking=PERSPECTIVE)  # type: ignore[arg-type]


GATE_BAD = [
    ("fron", ("front",), "view"),
    (None, ("front",), "view"),
    ("front", None, "view"),
    ("front", (), "supported_views"),
    ("front", ("front", "sideways"), "supported_views"),
    ("front", "front", "supported_views"),
    ("front", ("front", "front"), "supported_views"),
    ("front", ["front", 3], "supported_views"),
]


@pytest.mark.parametrize(("view", "supported", "message"), GATE_BAD, ids=[str(b[:2]) for b in GATE_BAD])
def test_t_met_06a_a_view_that_is_not_a_view_or_a_bad_list_of_supported_views_is_refused_naming_it(
    view, supported, message
):
    with pytest.raises(MetricError, match=message):
        eligibility(T10, intervals=None, flags={}, blocking=LEAN_BLOCKING, view=view, supported_views=supported)


def segment_of(reason: list[int], values: list[float] | None = None):
    """The segment rows of a layer of ``len(reason)`` rows, with the reason and the values of the test."""
    n = len(reason)
    rows = segment_rows(exact_layer(body(n, 400.0)))
    return (
        rows,
        np.array(reason, dtype=np.uint8),
        np.array(values if values is not None else [5.0] * n, dtype=np.float64),
    )


def assemble(rows, reason, values, **kwargs):
    args: dict[str, Any] = {
        "metric_name": "test_metric", "metric_version": "1", "units": "deg", "parameters": {"a": 1},
        "min_valid_s": None, "camera_id": "camA", "view_category": "front",
    }  # fmt: skip
    args.update(kwargs)
    return assemble_series(rows, reason, values, **args)


def test_t_met_06a_a_series_has_values_only_where_a_row_is_measured_and_a_header_that_follows_the_reasons():
    rows, reason, values = segment_of([0, 0, 1, 0, 0, 0, 16, 0], [1, 2, 3, 4, 5, 6, 7, 8])  # NaN is not given for row 2
    out = assemble(rows, reason, values)
    assert out.reason.tolist() == [0, 0, 1, 0, 0, 0, 16, 0]
    assert out.values[[0, 1, 3, 4, 5, 7]].tolist() == [1, 2, 4, 5, 6, 8] and np.isnan(out.values[[2, 6]]).all()
    h = out.header
    assert (h.metric_name, h.metric_version, h.units, h.camera_id, h.view_category) == (
        "test_metric",
        "1",
        "deg",
        "camA",
        "front",
    )
    assert (h.coverage.total, h.coverage.eligible, h.coverage.quality, h.coverage.measured) == (8, 7, 6, 6)
    assert [(i.t_start, i.t_end) for i in h.valid_intervals] == [
        (float(rows.t_sec[0]), float(rows.t_sec[1]) + rows.step_s),
        (float(rows.t_sec[3]), float(rows.t_sec[5]) + rows.step_s),
        (float(rows.t_sec[7]), float(rows.t_sec[7]) + rows.step_s),
    ]
    assert h.recording_id == rows.recording_id and h.data_sources == rows.data_sources and h.step_s == rows.step_s
    assert h.parameters == {"a": 1}


def test_t_met_06a_a_run_shorter_than_the_minimum_becomes_21_and_loses_its_value_and_the_inputs_are_not_changed():
    rows, reason, values = segment_of([0, 0, 1, 0, 1, 0, 0, 0], [1.0] * 8)
    before = (reason.copy(), values.copy())
    out = assemble(rows, reason, values, min_valid_s=2.5 * rows.step_s)  # a run needs three rows
    assert out.reason.tolist() == [21, 21, 1, 21, 1, 0, 0, 0]
    assert np.isnan(out.values[:5]).all() and out.values[5:].tolist() == [1.0, 1.0, 1.0]
    assert np.array_equal(reason, before[0]) and np.array_equal(values, before[1])  # the caller's arrays are untouched
    assert out.header.missing_by_reason.too_short == 3 and out.header.coverage.measured == 3


def test_t_met_06a_a_segment_of_one_row_has_no_step_and_its_row_is_21():
    layer = exact_layer(body(10, 400.0))
    only = np.zeros(10, dtype=bool)
    only[4] = True
    rows = segment_rows(edited(layer, grid_in_segment=only))
    out = assemble(rows, np.zeros(1, dtype=np.uint8), np.array([3.0]))
    assert out.reason.tolist() == [21] and np.isnan(out.values).all() and out.header.step_s is None


def test_t_met_06a_a_series_of_no_row_is_empty_and_a_bad_header_argument_is_refused():
    layer = exact_layer(body(10, 400.0))
    rows = segment_rows(edited(layer, grid_in_segment=np.zeros(10, dtype=bool)))
    out = assemble(rows, np.zeros(0, dtype=np.uint8), np.zeros(0))
    assert len(out.t_sec) == 0 and out.header.coverage.total == 0 and out.header.step_s is None
    rows, reason, values = segment_of([0, 0, 0])
    with pytest.raises(MetricError, match="camera_id"):
        assemble(rows, reason, values, camera_id="cam1")


def evidence(codes: list[int], minimum: int) -> str | None:
    return evidence_reason(np.array(codes, dtype=np.uint8), min_measured=minimum)


def test_t_met_06a_there_is_evidence_when_enough_rows_are_measured_and_the_reason_otherwise():
    assert evidence([0, 1, 1, 2], 1) is None  # a median needs one row
    assert evidence([0, 1, 1, 2], 2) == "too_short"  # a range needs two: one row is a row, not a spread
    assert evidence([0, 0, 16], 2) is None
    assert evidence([1, 1, 2, 16], 1) == "low_conf"  # no row measured: the reason with the most rows
    assert evidence([1, 1, 2, 16], 2) == "low_conf"
    assert evidence([2, 2, 1, 1], 1) == "low_conf"  # a tie: the smaller code
    assert evidence([], 1) == "no_frame" and evidence([], 2) == "no_frame"
    assert evidence([21], 1) == "too_short"  # the single row of a one-row segment is 21
    assert evidence([0, 0, 0], 3) is None and evidence([0, 0, 0], 4) == "too_short"


@pytest.mark.parametrize("minimum", [0, -1, True, 1.5, "2", None])
def test_t_met_06a_the_minimum_of_measured_rows_is_a_whole_number_of_at_least_one(minimum):
    with pytest.raises(MetricError, match="min_measured"):
        evidence_reason(np.zeros(3, dtype=np.uint8), min_measured=minimum)  # type: ignore[arg-type]


def test_t_met_06a_a_bad_reason_array_is_refused_by_the_reason_without_evidence_too():
    for bad in (np.zeros(3, dtype=np.int64), np.zeros((2, 2), dtype=np.uint8), None):
        with pytest.raises(MetricError, match="reason"):
            evidence_reason(bad, min_measured=1)  # type: ignore[arg-type]


# --- T-MET-08a: the neighbours of the rows of a segment, and the scale of a set of rows -----------------------------
def at_edge(first: int, stop: int, n: int = 40):
    """A layer of ``n`` rows (mid-hip ``y = 400 + g``) whose segment is the rows ``first`` to ``stop - 1``."""
    return exact_layer(body(n, 400.0 + np.arange(n)), segment=(first, stop))


def test_t_met_08a_the_neighbours_are_the_grid_rows_before_and_after_each_row_of_the_segment_margins_included():
    layer = marked_layer()  # the segment is the grid rows 5 to 34, with margins on both sides
    nb = neighbour_rows(layer)
    before, after = np.arange(4, 34), np.arange(6, 36)
    assert np.array_equal(nb.keypoints_prev, layer.keypoints[before])
    assert np.array_equal(nb.keypoints_next, layer.keypoints[after])
    assert np.array_equal(nb.reason_prev, layer.reason[before]) and np.array_equal(nb.reason_next, layer.reason[after])
    assert np.array_equal(nb.interpolated_prev, layer.interpolated[before])
    assert np.array_equal(nb.interpolated_next, layer.interpolated[after])
    assert np.array_equal(nb.t_prev, layer.t_grid[before]) and np.array_equal(nb.t_next, layer.t_grid[after])
    assert nb.has_prev.all() and nb.has_next.all()  # the first row of the segment has the margin before it
    assert nb.keypoints_prev[0, 11, 1] != layer.keypoints[5, 11, 1]  # and it is the margin row, not the row itself


def test_t_met_08a_a_segment_at_the_start_or_the_end_of_the_grid_has_no_neighbour_on_that_side():
    first = neighbour_rows(at_edge(0, 30))
    assert first.has_prev.tolist() == [False] + [True] * 29 and first.has_next.all()
    assert np.isnan(first.keypoints_prev[0]).all() and (first.reason_prev[0] == 6).all()  # no frame there
    assert not first.interpolated_prev[0].any() and np.isnan(first.t_prev[0])
    assert np.isfinite(first.t_prev[1:]).all() and np.array_equal(
        first.keypoints_prev[1:], at_edge(0, 30).keypoints[0:29]
    )
    last = neighbour_rows(at_edge(10, 40))
    assert last.has_next.tolist() == [True] * 29 + [False] and last.has_prev.all()
    assert np.isnan(last.keypoints_next[-1]).all() and (last.reason_next[-1] == 6).all() and np.isnan(last.t_next[-1])
    whole = neighbour_rows(exact_layer(body(12, 400.0)))
    assert whole.has_prev.tolist() == [False] + [True] * 11 and whole.has_next.tolist() == [True] * 11 + [False]


def test_t_met_08a_no_row_and_one_row_give_arrays_of_that_length_and_the_arrays_are_copies_that_cannot_be_written():
    empty = neighbour_rows(edited(marked_layer(), grid_in_segment=np.zeros(40, dtype=bool)))
    assert empty.keypoints_prev.shape == (0, NUM_JOINTS, 2) and len(empty.t_next) == 0 and len(empty.has_prev) == 0
    only = np.zeros(40, dtype=bool)
    only[12] = True
    one = neighbour_rows(edited(marked_layer(), grid_in_segment=only))
    assert one.keypoints_next.shape == (1, NUM_JOINTS, 2) and one.has_prev.tolist() == [True]
    layer = marked_layer()
    nb = neighbour_rows(layer)
    for array in (nb.keypoints_prev, nb.keypoints_next, nb.reason_prev, nb.reason_next, nb.interpolated_prev,
                  nb.interpolated_next, nb.t_prev, nb.t_next, nb.has_prev, nb.has_next):  # fmt: skip
        assert not array.flags.writeable
    assert not np.shares_memory(nb.keypoints_prev, layer.keypoints)
    assert (nb.keypoints_prev.dtype, nb.reason_prev.dtype, nb.interpolated_prev.dtype) == (
        np.float32,
        np.uint8,
        np.bool_,
    )
    assert (nb.t_prev.dtype, nb.has_prev.dtype) == (np.float64, np.bool_)


def test_t_met_08a_a_layer_that_is_not_one_or_a_broken_segment_is_refused_by_the_neighbours_too():
    split = np.zeros(40, dtype=bool)
    split[[5, 6, 9]] = True
    with pytest.raises(MetricError, match="contiguous"):
        neighbour_rows(edited(marked_layer(), grid_in_segment=split))
    with pytest.raises(MetricError, match="PoseFiltered"):
        neighbour_rows("layer")  # type: ignore[arg-type]


def trunk_layer(n: int = 40, segment=None):
    return exact_layer(body(n, 420.0), segment=segment)


def test_t_met_08a_the_scale_is_the_median_trunk_of_the_valid_rows_of_the_given_rows_only():
    kp = body(50, 420.0, trunk=150.0)
    kp[:10] = body(10, 420.0, trunk=100.0)  # the margins have other trunks and are not in the rows
    kp[40:] = body(10, 420.0, trunk=300.0)
    out = scale_of(segment_rows(exact_layer(kp, segment=(10, 40))), None)
    assert isinstance(out, ScaleEstimate) and out.scale_px == pytest.approx(150.0, rel=1e-12)
    assert out.n_rows == 30 and out.duration_s == pytest.approx(30 * segment_rows(trunk_layer(50, (10, 40))).step_s)


def test_t_met_08a_it_is_a_median_not_a_mean_a_missing_row_is_left_out_and_a_bridged_cell_counts():
    kp = body(40, 420.0, trunk=150.0)
    kp[:10] = body(10, 420.0, trunk=300.0)  # 10 rows at 300, 30 at 150: mean 187.5, median 150
    layer = exact_layer(kp)
    assert scale_of(segment_rows(layer), None).scale_px == pytest.approx(150.0)
    k, r, i = cells(layer)
    for row in range(10, 16):
        drop(k, r, row, LS, 1)  # six rows lose a shoulder: they have no trunk
    out = scale_of(segment_rows(edited(layer, keypoints=k, reason=r)), None)
    assert out.n_rows == 34 and out.scale_px == pytest.approx(150.0)
    k, r, i = cells(layer)
    bridge(k, r, i, 3, LH)
    assert scale_of(segment_rows(edited(layer, reason=r, interpolated=i)), None).n_rows == 40


def test_t_met_08a_a_minimum_duration_turns_a_short_set_of_rows_into_nan_with_its_rows_kept_and_a_nanosecond_of_slack():
    rows = segment_rows(trunk_layer(30))  # 30 rows at 30 fps: one second up to a rounding
    assert scale_of(rows, 1.0).scale_px == pytest.approx(150.0)
    assert scale_of(rows, 1.0 + 1e-12).scale_px == pytest.approx(150.0)  # a picosecond short is not short
    short = scale_of(rows, 1.0 + 1e-8)  # ten nanoseconds short is
    assert math.isnan(short.scale_px) and short.n_rows == 30 and short.duration_s == pytest.approx(1.0)


def test_t_met_08a_no_valid_row_or_a_single_row_has_no_scale_or_no_duration():
    layer = trunk_layer(30)
    k, r, i = cells(layer)
    for row in range(30):
        drop(k, r, row, LS, 2)
    none = scale_of(segment_rows(edited(layer, keypoints=k, reason=r)), None)
    assert math.isnan(none.scale_px) and none.n_rows == 0 and none.duration_s == 0.0
    only = np.zeros(30, dtype=bool)
    only[4] = True
    one = scale_of(segment_rows(edited(layer, grid_in_segment=only)), None)
    assert one.scale_px == pytest.approx(150.0) and one.n_rows == 1 and one.duration_s == 0.0
    assert math.isnan(scale_of(segment_rows(edited(layer, grid_in_segment=only)), 0.01).scale_px)


def test_t_met_08a_the_scale_of_a_reference_in_hip_height_is_the_same_estimate():
    from taiji_ai.metrics.hip_height import ReferenceScale

    assert ReferenceScale is ScaleEstimate  # one definition: the name of P5.03 stays
