"""P4.07: the coverage of the quality chain (T-QLT-11a to 11g and the differential test).

Every number of fixture F1 below is counted by hand in the comments (cells in the segment, by class, reason, joint,
gap outcome); the differential test then recounts 200 random chains cell by cell with a slow oracle written from the
rules of the plan (``Docs/tasks/P4.07.md``), so the vectorised counting cannot share a mistake with it.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from helpers.quality_fixtures import FPS, LANKLE, LWRIST, NOSE, PAIR_JOINTS, RWRIST, build_f1, clean, static_pose
from taiji_ai.pose.skeleton import ESSENTIAL, JOINTS, LR_PAIRS, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality.chain import QualityParams, QualityResult, run_quality_arrays
from taiji_ai.quality.coverage import parse_intervals
from taiji_ai.quality.gaps import OUTCOME_NAMES
from taiji_ai.quality.mask import NOT_TRACKED, REASON_NAMES, MaskParams

REASONS = REASON_NAMES[1:]  # the six reasons of the two tables (``ok`` is not a reason for a missing value)
EPS = 1e-9


def rc(**counts: int) -> dict[str, int]:
    """A table of reason counts: the six names, 0 unless given."""
    assert set(counts) <= set(REASONS), set(counts) - set(REASONS)
    return {name: counts.get(name, 0) for name in REASONS}


def oc(**counts: int) -> dict[str, int]:
    """A table of gap outcome counts: the seven names, 0 unless given."""
    assert set(counts) <= set(OUTCOME_NAMES), set(counts) - set(OUTCOME_NAMES)
    return {name: counts.get(name, 0) for name in OUTCOME_NAMES}


# --- fixture F1 (``helpers/quality_fixtures.build_f1``): a segment of 54 rows, every class, reason and outcome --------
def run_f1(**kwargs) -> QualityResult:
    t, kp, score, tracked, in_segment = build_f1()
    return run_quality_arrays(kp, score, t, tracked=tracked, in_segment=in_segment, **kwargs)


def f1_joint(j: int) -> dict:
    """What the segment of F1 holds for joint ``j`` (54 rows), derived joint by joint in the comments.

    missing: 4 rows not tracked (3, 4, 45, 46); a pair joint also 2 outlier rows (34, 35: the swap, taken out by
    Hampel and not bridged: the flag blocks it); LAnkle also its hole of 10 low-confidence rows.
    bridged: row 15 for every joint; Nose also row 8 (outlier), LWrist rows 10 and 11, RWrist row 12.
    filtered: a run of usable rows longer than 15 is filtered. A non-pair joint has rows 5 to 44 (40: filtered) and
    47 to 59 (13: not); a pair joint rows 5 to 33 (29: filtered), 36 to 44 (9) and 47 to 59 (13); LAnkle's runs
    are 15, 4, 9 and 13 rows long: none is filtered.
    """
    pair = j in PAIR_JOINTS
    missing_reasons = rc(not_tracked=4, low_conf=10 if j == LANKLE else 0, outlier=2 if pair else 0)
    missing = sum(missing_reasons.values())
    bridged = 1 + {NOSE: 1, LWRIST: 2, RWRIST: 1}.get(j, 0)
    filtered = 0 if j == LANKLE else 29 if pair else 40
    return {
        "joint": JOINTS[j],
        "observed": 54 - missing - bridged,
        "bridged": bridged,
        "missing": missing,
        "missing_by_reason": missing_reasons,
        "filtered": filtered,
        "suspect": 2 if pair else 0,
        "blocked": 3 if pair else 0,
    }


F1_SEGMENT = {
    "name": "segment",
    "rows": 54,
    "source_rows": 54,
    "cells": 1404,
    # missing: rows 3, 4, 45, 46 for all 26 joints (104) + LAnkle's hole (10) + 22 pair joints x 2 rows (44) = 158;
    # bridged: row 15 (26) + Nose row 8 + LWrist rows 10, 11 + RWrist row 12 = 30; the rest is observed
    "observed": 1216,
    "bridged": 30,
    "missing": 158,
    # all cells whose reason is not ok: 104 not_tracked; 18 low_conf (LAnkle 10, LWrist 2, six essential joints of
    # row 15); 1 non_finite; 20 frame_invalid (row 15); 45 outlier (22 x 2 swapped cells + Nose row 8)
    "unobserved_by_reason": rc(not_tracked=104, low_conf=18, non_finite=1, frame_invalid=20, outlier=45),
    "missing_by_reason": rc(not_tracked=104, low_conf=10, outlier=44),
    "usable_frames": 48,  # 54 rows - 4 not tracked - rows 34 and 35 (every essential joint is a pair joint: none left)
    "not_tracked_frames": 4,
    # gaps are runs of unobserved cells in the Hampel layer; cells counted inside the segment
    "gaps": {
        "gaps": oc(filled=29, too_long=1, never_fill=26, blocked=22, open_start=26),
        "cells": oc(filled=30, too_long=10, never_fill=52, blocked=44, open_start=52),
    },
    "filtered": 769,  # 4 x 40 + 21 x 29 + 0
    "unfiltered": 477,  # (4 x 50 + 21 x 48 + 38) usable cells - 769
    "suspect": 44,  # rows 34 and 35, 22 pair joints
    "blocked": 66,  # rows 34 to 36
    "mixed_rows": 0,
}


def dump(interval) -> dict:
    return interval.model_dump()


def test_t_qlt_11a_fixture_counted_by_hand_the_segment():
    r = run_f1()
    iv = dump(r.report.intervals[0])
    for key, want in F1_SEGMENT.items():
        assert iv[key] == want, key
    assert iv["t_start"] == pytest.approx(3 / FPS) and iv["t_end"] == pytest.approx(56 / FPS)
    assert iv["duration_s"] == pytest.approx(54 / FPS)


def test_t_qlt_11a_fixture_counted_by_hand_every_joint():
    iv = dump(run_f1().report.intervals[0])
    assert [j["joint"] for j in iv["joints"]] == list(JOINTS)
    for j, got in enumerate(iv["joints"]):
        assert got == f1_joint(j), JOINTS[j]
    assert sum(j["observed"] for j in iv["joints"]) == 1216 and sum(j["missing"] for j in iv["joints"]) == 158


def test_t_qlt_11a_fixture_the_run_and_its_warning():
    r = run_f1()
    rep = r.report
    assert rep.schema_version == "quality/1" and rep.skeleton == "halpe26/1"
    assert [iv.name for iv in rep.intervals] == ["segment"]
    assert rep.timeline.rows == 60 and rep.timeline.grid_rows == 60 and rep.timeline.resampled is False
    assert rep.timeline.step_s == pytest.approx(1 / FPS) and rep.timeline.sampling_hz == pytest.approx(FPS)
    assert rep.timeline.torso_px == 150.0
    assert rep.params.hampel.scale_floor_px == pytest.approx(1.5) and rep.params.hampel.floor_fraction == 0.01
    assert rep.warnings == ("lr_swap_suspect@1.13-1.20",)  # blocked rows 34 to 36 (t = 34 / 30 and 36 / 30)


def test_t_qlt_11a_the_report_is_what_the_layers_hold():
    """The counts are the final layer's: spot-check the layer itself, so the fixture and the layers agree."""
    r = run_f1()
    final = r.filtered
    seg = slice(3, 57)
    usable = ~np.isnan(final.keypoints[seg, :, 0])
    assert int(usable.sum()) == 1216 + 30
    assert int(final.interpolated[seg].sum()) == 30
    assert int(final.filtered[seg].sum()) == 769


# --- T-QLT-11b: the partition -----------------------------------------------------------------------------------------
def check_partition(report) -> None:
    for iv in report.intervals:
        d = iv.model_dump()
        assert d["cells"] == d["rows"] * NUM_JOINTS
        assert d["observed"] + d["bridged"] + d["missing"] == d["cells"]
        assert sum(d["missing_by_reason"].values()) == d["missing"]
        assert sum(d["unobserved_by_reason"].values()) == d["bridged"] + d["missing"]
        assert all(d["unobserved_by_reason"][k] >= d["missing_by_reason"][k] for k in REASONS)
        assert d["filtered"] + d["unfiltered"] == d["observed"] + d["bridged"]
        assert d["usable_frames"] + d["not_tracked_frames"] <= d["rows"] and d["mixed_rows"] <= d["rows"]
        assert d["suspect"] <= d["blocked"] <= d["source_rows"] * NUM_JOINTS
        assert sum(d["gaps"]["cells"].values()) <= d["source_rows"] * NUM_JOINTS
        assert all(d["gaps"]["gaps"][k] <= d["gaps"]["cells"][k] for k in OUTCOME_NAMES)
        assert len(d["joints"]) == NUM_JOINTS
        for j in d["joints"]:
            assert j["observed"] + j["bridged"] + j["missing"] == d["rows"]
            assert sum(j["missing_by_reason"].values()) == j["missing"]
            assert j["filtered"] <= j["observed"] + j["bridged"] and j["suspect"] <= j["blocked"] <= d["source_rows"]
        for key in ("observed", "bridged", "missing", "filtered", "suspect", "blocked"):
            assert sum(j[key] for j in d["joints"]) == d[key], key
        for name in REASONS:
            assert sum(j["missing_by_reason"][name] for j in d["joints"]) == d["missing_by_reason"][name], name
        for value in (d["rows"], d["source_rows"], d["cells"], d["observed"], d["bridged"], d["missing"]):
            assert type(value) is int and value >= 0


def test_t_qlt_11b_the_partition_holds_on_the_fixture_and_with_named_intervals():
    r = run_f1(intervals={"early": (0.0, 0.5), "late": (1.0, 5.0), "none": (100.0, 101.0)})
    assert [iv.name for iv in r.report.intervals] == ["segment", "early", "late", "none"]
    check_partition(r.report)


def test_t_qlt_11b_the_counts_are_integers_and_the_cells_are_rows_times_26():
    r = run_f1()
    iv = r.report.intervals[0]
    assert iv.cells == iv.rows * 26 == 54 * 26


# --- T-QLT-11c: the intervals -----------------------------------------------------------------------------------------
def test_t_qlt_11c_the_segment_leaves_the_margins_out_and_a_named_interval_is_half_open():
    t, kp, score = clean(30)
    in_segment = np.zeros(30, dtype=bool)
    in_segment[5:25] = True
    r = run_quality_arrays(kp, score, t, in_segment=in_segment, intervals={"mid": (0.2, 0.5)})
    seg, mid = r.report.intervals
    assert seg.rows == 20 and seg.cells == 520 and seg.t_start == pytest.approx(5 / FPS)
    assert seg.t_end == pytest.approx(24 / FPS) and seg.duration_s == pytest.approx(20 / FPS)
    assert mid.name == "mid" and mid.rows == 9  # t = 6/30 (= 0.2, included) to 14/30; 15/30 = 0.5 is not
    assert mid.t_start == 0.2 and mid.t_end == 0.5


def test_t_qlt_11c_a_boundary_one_ulp_off_is_the_boundary():
    t, kp, score = clean(30)
    start, end = float(np.nextafter(0.2, 1.0)), float(np.nextafter(0.5, 0.0))
    r = run_quality_arrays(kp, score, t, intervals={"mid": (start, end)})
    assert r.report.intervals[1].rows == 9  # the row at 0.2 is in (1 ulp off), the row at 0.5 is out (1 ulp off)


def test_t_qlt_11c_intervals_may_overlap_and_may_reach_beyond_the_clip():
    t, kp, score = clean(30)
    r = run_quality_arrays(
        kp, score, t, intervals={"a": (0.0, 0.5), "b": (0.3, 0.9), "before": (-1.0, 0.1), "far": (100.0, 101.0)}
    )
    rows = {iv.name: iv.rows for iv in r.report.intervals}
    assert rows == {"segment": 30, "a": 15, "b": 18, "before": 3, "far": 0}
    far = r.report.intervals[-1]
    assert far.t_start == 100.0 and far.t_end == 101.0 and far.cells == 0 and far.duration_s == 0.0
    assert far.observed == far.bridged == far.missing == far.usable_frames == far.filtered == 0
    assert all(j.observed == j.missing == 0 for j in far.joints)
    check_partition(r.report)


def test_t_qlt_11c_no_in_segment_means_the_whole_clip_and_none_in_it_means_an_empty_segment():
    t, kp, score = clean(30)
    whole = run_quality_arrays(kp, score, t).report.intervals[0]
    assert whole.rows == 30 and whole.t_start == 0.0 and whole.t_end == pytest.approx(29 / FPS)
    none = run_quality_arrays(kp, score, t, in_segment=np.zeros(30, dtype=bool)).report.intervals[0]
    assert none.rows == 0 and none.cells == 0 and none.t_start is None and none.t_end is None
    assert none.duration_s == 0.0 and none.source_rows == 0


def test_t_qlt_11c_the_segment_is_the_stretch_from_the_first_to_the_last_row_of_in_segment():
    t, kp, score = clean(30)
    in_segment = np.zeros(30, dtype=bool)
    in_segment[[5, 20]] = True  # a row between them that is False is still inside the stretch
    seg = run_quality_arrays(kp, score, t, in_segment=in_segment).report.intervals[0]
    assert seg.rows == 16 and seg.t_start == pytest.approx(5 / FPS) and seg.t_end == pytest.approx(20 / FPS)


def test_t_qlt_11c_one_row_has_no_duration_and_no_rows_has_zero():
    t, kp, score = clean(1)
    one = run_quality_arrays(kp, score, t).report
    assert one.intervals[0].rows == 1 and one.intervals[0].duration_s is None
    assert one.timeline.step_s is None and one.timeline.sampling_hz is None
    empty = run_quality_arrays(kp[:0], score[:0], t[:0]).report
    assert empty.intervals[0].rows == 0 and empty.intervals[0].duration_s == 0.0
    assert empty.timeline.rows == 0 and empty.timeline.grid_rows == 0 and "torso_unmeasured" in empty.warnings


@pytest.mark.parametrize(
    "intervals, text",
    [
        ([("a", (0.0, 1.0))], "mapping"),
        ({"segment": (0.0, 1.0)}, "reserved"),
        ({"a b": (0.0, 1.0)}, "name"),
        ({"a" + chr(10): (0.0, 1.0)}, "name"),  # ``$`` alone would let a trailing newline through
        ({"": (0.0, 1.0)}, "name"),
        ({"x" * 65: (0.0, 1.0)}, "name"),
        ({3: (0.0, 1.0)}, "name"),
        ({"a": (1.0, 1.0)}, "start"),
        ({"a": (2.0, 1.0)}, "start"),
        ({"a": (float("nan"), 1.0)}, "finite"),
        ({"a": (0.0, float("inf"))}, "finite"),
        ({"a": (0.0, "1")}, "finite"),
        ({"a": (True, 2.0)}, "finite"),
        ({"a": (0.0, 1.0, 2.0)}, "pair"),
        ({"a": 5.0}, "pair"),
    ],
)
def test_t_qlt_11c_wrong_intervals_are_refused(intervals, text):
    with pytest.raises(QualityError, match=text):
        parse_intervals(intervals)
    t, kp, score = clean(5)
    with pytest.raises(QualityError, match=text):
        run_quality_arrays(kp, score, t, intervals=intervals)


def test_t_qlt_11c_parse_intervals_gives_names_and_floats_in_order():
    assert parse_intervals(None) == []
    assert parse_intervals({"b": (1, 2), "a": (0.5, 0.75)}) == [("b", 1.0, 2.0), ("a", 0.5, 0.75)]


def test_t_qlt_11c_a_wrong_in_segment_is_refused():
    t, kp, score = clean(5)
    for bad in (np.ones(4, dtype=bool), np.ones(5, dtype=np.int8), np.ones((5, 1), dtype=bool)):
        with pytest.raises(QualityError, match="in_segment"):
            run_quality_arrays(kp, score, t, in_segment=bad)


# --- T-QLT-11d: the frames --------------------------------------------------------------------------------------------
def frames_layer():
    """60 rows: 10 to 24 five essential joints out (half: a frame), 30 to 44 six out (a frame_invalid row), 50 to 54
    not the target's. The holes are 15 rows long (0.5 s): too long to bridge, so they stay NaN."""
    t, kp, score = clean(60)
    score[10:25, [5, 6, 11, 12, 13]] = 0.1
    score[30:45, [5, 6, 11, 12, 13, 14]] = 0.1
    tracked = np.ones(60, dtype=bool)
    tracked[50:55] = False
    return t, kp, score, tracked


def test_t_qlt_11d_a_row_is_usable_at_exactly_half_of_the_essential_joints_and_not_below():
    t, kp, score, tracked = frames_layer()
    seg = run_quality_arrays(kp, score, t, tracked=tracked).report.intervals[0]
    assert seg.rows == 60
    assert seg.usable_frames == 60 - 15 - 5  # rows 10 to 24 have 5 of 10 and count; rows 30 to 44 have 4 and do not
    assert seg.not_tracked_frames == 5  # a row of 26 not_tracked cells
    # rows 30 to 44 are neither usable nor not tracked: the two classes are independent
    assert seg.rows - seg.usable_frames - seg.not_tracked_frames == 15


def test_t_qlt_11d_the_frame_rule_uses_the_fraction_of_the_mask_parameters():
    t, kp, score, tracked = frames_layer()
    params = QualityParams(mask=MaskParams(min_essential_fraction=0.6))  # 6 of 10: rows 10 to 24 are invalid too
    seg = run_quality_arrays(kp, score, t, tracked=tracked, params=params).report.intervals[0]
    assert seg.usable_frames == 60 - 15 - 15 - 5


def test_t_qlt_11d_a_bridged_frame_counts_as_a_frame_with_values():
    t, kp, score = clean(30)
    score[10, [5, 6, 11, 12, 13, 14]] = 0.1  # one frame_invalid row: bridged from rows 9 and 11
    seg = run_quality_arrays(kp, score, t).report.intervals[0]
    assert seg.bridged == 26 and seg.usable_frames == 30


# --- T-QLT-11e: the reasons -------------------------------------------------------------------------------------------
def test_t_qlt_11e_all_six_reasons_have_their_own_count_and_a_bridged_cell_is_only_unobserved():
    seg = run_f1().report.intervals[0]
    assert list(seg.unobserved_by_reason.model_dump()) == list(REASONS)
    un, miss = seg.unobserved_by_reason.model_dump(), seg.missing_by_reason.model_dump()
    # non_finite and frame_invalid occur only in bridged cells (row 12 of RWrist, row 15): not missing at all
    assert (un["non_finite"], miss["non_finite"]) == (1, 0) and (un["frame_invalid"], miss["frame_invalid"]) == (20, 0)
    # an outlier that was bridged (Nose, row 8) and 44 that were not (the swap, blocked)
    assert (un["outlier"], miss["outlier"]) == (45, 44)
    assert (un["low_conf"], miss["low_conf"]) == (18, 10) and (un["no_frame"], miss["no_frame"]) == (0, 0)


# --- T-QLT-11f: the gaps ----------------------------------------------------------------------------------------------
def test_t_qlt_11f_on_a_uniform_clock_the_gap_cells_are_the_bridged_and_the_missing_cells():
    seg = run_f1().report.intervals[0]
    g = seg.gaps.cells.model_dump()
    assert g["filled"] == seg.bridged
    assert sum(g.values()) - g["filled"] == seg.missing


def test_t_qlt_11f_a_gap_is_counted_by_the_cells_inside_the_interval():
    r = run_f1(intervals={"head": (0.0, 0.2), "swap": (1.1, 1.3)})
    head = r.report.intervals[1]  # rows 0 to 5: the not_tracked rows 0 to 4 of every joint, one gap per joint
    assert head.rows == 6 and head.gaps.gaps.model_dump() == oc(open_start=26)
    assert head.gaps.cells.model_dump() == oc(open_start=26 * 5)  # all 5 cells of each gap are inside
    swap = r.report.intervals[2]  # rows 33 to 38: the 22 blocked gaps, 2 cells each
    assert swap.gaps.gaps.model_dump() == oc(blocked=22) and swap.gaps.cells.model_dump() == oc(blocked=44)
    # the segment starts at row 3: the gaps that begin at row 0 are in it by their two cells (rows 3 and 4)
    assert r.report.intervals[0].gaps.cells.open_start == 52


def test_t_qlt_11f_a_gap_is_counted_once_in_an_interval_that_holds_part_of_it():
    r = run_f1(intervals={"half": (20 / FPS, 25 / FPS)})  # rows 20 to 24 of LAnkle's hole of 10 rows
    half = r.report.intervals[1]
    assert half.gaps.gaps.too_long == 1 and half.gaps.cells.too_long == 5


# --- T-QLT-11g: the lattice -------------------------------------------------------------------------------------------
def test_t_qlt_11g_a_uniform_clock_is_the_identity_and_the_rows_are_the_grid():
    r = run_f1()
    assert r.report.timeline.resampled is False and "grid_resampled" not in r.report.warnings
    seg = r.report.intervals[0]
    assert seg.rows == seg.source_rows == 54 and seg.mixed_rows == 0


def vfr_timeline():
    """30 rows at 1/30 s, then 9 rows at 0.1 s steps (the last at 1.9 s): 39 rows, a step-down like SYN-07."""
    first = np.arange(30) / FPS
    return np.concatenate([first, 1.0 + 0.1 * np.arange(1, 10)])


def test_t_qlt_11g_a_variable_rate_clip_is_counted_on_the_grid():
    t = vfr_timeline()
    n = len(t)
    assert n == 39
    r = run_quality_arrays(static_pose(n), np.full((n, NUM_JOINTS), 0.95, dtype=np.float32), t)
    seg = r.report.intervals[0]
    # grid times k / 30 for k = 0 to 57 (the median interval is 1/30): 58 rows, of which 30 + 9 are source rows
    assert r.report.timeline.resampled is True and r.report.timeline.grid_rows == 58 and r.report.timeline.rows == 39
    assert seg.rows == 58 and seg.source_rows == 39 and seg.mixed_rows == 58 - 39
    assert seg.cells == 58 * 26 and seg.observed == seg.cells  # a mixed row of observed cells is observed
    assert seg.filtered == seg.cells  # one run of 58 rows per joint
    assert seg.duration_s == pytest.approx(58 / FPS)
    assert r.report.timeline.step_s == pytest.approx(1 / FPS) and "grid_resampled" in r.report.warnings
    check_partition(r.report)


def test_t_qlt_11g_a_dropped_frame_is_a_grid_row_with_a_mix():
    t = np.delete(np.arange(30) / FPS, 15)  # 29 rows; 33 ms off the straight clock
    n = len(t)
    r = run_quality_arrays(static_pose(n), np.full((n, NUM_JOINTS), 0.95, dtype=np.float32), t)
    seg = r.report.intervals[0]
    assert (seg.rows, seg.source_rows, seg.mixed_rows) == (30, 29, 1)
    assert seg.observed == 30 * 26 and r.report.timeline.resampled is True


def test_t_qlt_11g_a_pause_in_the_timestamps_is_no_frame_and_the_gap_table_does_not_see_it():
    first = np.arange(20) / FPS
    t = np.concatenate([first, first[-1] + 0.4 + np.arange(20) / FPS])  # a pause of 0.4 s after row 19
    n = len(t)
    r = run_quality_arrays(static_pose(n), np.full((n, NUM_JOINTS), 0.95, dtype=np.float32), t)
    seg = r.report.intervals[0]
    stall = 11 * NUM_JOINTS  # grid times 19/30 + j/30 for j = 1 to 11 are inside the pause (j = 12 is the next row)
    assert seg.missing == stall and seg.missing_by_reason.no_frame == stall
    assert seg.unobserved_by_reason.no_frame == stall and seg.bridged == 0
    # the stall is on the grid only: the source rows have no hole, so the gap table has nothing
    assert sum(seg.gaps.cells.model_dump().values()) == 0 and seg.source_rows == 40
    assert seg.rows == 40 + 11 and seg.filtered == 40 * 26  # two runs of 20 rows per joint are filtered (> 15)
    assert seg.not_tracked_frames == 0 and seg.usable_frames == 40
    check_partition(r.report)


# --- the differential test --------------------------------------------------------------------------------------------
def random_case(seed: int):
    rng = np.random.default_rng(seed)
    n = int(rng.choice([0, 1, 2, 5, 20, 40, 70, 90]))
    dtype = rng.choice([np.float32, np.float64])
    kind = str(rng.choice(["cfr", "vfr", "pause"]))
    dt = np.full(max(n - 1, 0), 1 / FPS)
    if kind == "vfr":
        dt = dt * rng.uniform(0.6, 1.8, size=dt.shape)
    elif kind == "pause" and n >= 4:
        dt[int(rng.integers(0, n - 1))] += float(rng.uniform(0.2, 0.5))
    start = float(rng.uniform(0.0, 5.0))
    t = start + np.concatenate([np.zeros(min(n, 1)), np.cumsum(dt)])
    kp = static_pose(n, np.float64) + np.cumsum(rng.normal(0.0, 1.0, size=(n, NUM_JOINTS, 2)), axis=0) * 0.3
    kp += rng.normal(0.0, 0.5, size=kp.shape)
    for _ in range(int(rng.integers(0, 4)) if n else 0):  # spikes
        kp[int(rng.integers(0, n)), int(rng.integers(0, NUM_JOINTS))] += float(rng.choice([-1.0, 1.0])) * 60.0
    if n >= 8 and rng.random() < 0.5:  # a swap of every pair
        a = int(rng.integers(0, n - 4))
        b = a + int(rng.integers(1, 4))
        for left, right in LR_PAIRS:
            kp[a:b, [left, right]] = kp[a:b, [right, left]]
    score = np.full((n, NUM_JOINTS), 0.9)
    for _ in range(int(rng.integers(0, 5)) if n else 0):  # holes of 1 to 14 rows
        j, a = int(rng.integers(0, NUM_JOINTS)), int(rng.integers(0, n))
        score[a : a + int(rng.integers(1, 15)), j] = 0.1
    for _ in range(int(rng.integers(0, 3)) if n else 0):  # a coordinate that is not a number
        kp[int(rng.integers(0, n)), int(rng.integers(0, NUM_JOINTS))] = np.nan
    tracked = np.ones(n, dtype=bool)
    if n and rng.random() < 0.5:
        a = int(rng.integers(0, n))
        tracked[a : a + int(rng.integers(1, 9))] = False
    if n and rng.random() < 0.1:
        tracked[:] = False
    choice = int(rng.integers(0, 3))
    if choice == 0:
        in_segment = None
    elif choice == 1:
        in_segment = np.zeros(n, dtype=bool)
    else:
        in_segment = np.zeros(n, dtype=bool)
        if n:
            a = int(rng.integers(0, n))
            in_segment[a : a + int(rng.integers(1, n + 1))] = True
    span = float(t[-1] - t[0]) if n else 1.0
    named = {}
    for i in range(int(rng.integers(0, 4))):
        a = float(t[0] if n else 0.0) + float(rng.uniform(-0.5, span + 0.5))
        named[f"n{i}"] = (a, a + float(rng.uniform(0.03, 1.5)))
    return kp.astype(dtype), score.astype(dtype), t, tracked, in_segment, named


def slow_report(r: QualityResult, named: dict) -> list[dict]:
    """The counts of the plan's rules 2 to 7, recounted with loops over rows, joints and cells."""
    t_src, t_grid = r.t_sec, r.grid.gridmap.t_grid
    final = r.filtered
    kp, reason, bridged_flag, filt = final.keypoints, final.reason, final.interpolated, final.filtered
    blocked, suspect = r.swap.blocked, r.swap.suspect
    table = r.gaps.gaps
    essential, fraction = r.params.mask.essential, r.params.mask.min_essential_fraction
    seg_rows = [i for i in range(len(t_src)) if r.in_segment[i]]
    if seg_rows:
        t0, t1 = float(t_src[seg_rows[0]]), float(t_src[seg_rows[-1]])
        specs = [("segment", lambda x: t0 - EPS <= x <= t1 + EPS, t0, t1)]
    else:
        specs = [("segment", lambda x: False, None, None)]
    for name, (a, b) in named.items():
        specs.append((name, lambda x, a=a, b=b: a - EPS <= x < b - EPS, a, b))
    out = []
    for name, inside, lo, hi in specs:
        grid_rows = [k for k in range(len(t_grid)) if inside(float(t_grid[k]))]
        src_rows = [i for i in range(len(t_src)) if inside(float(t_src[i]))]
        d = {
            "name": name,
            "t_start": lo,
            "t_end": hi,
            "rows": len(grid_rows),
            "source_rows": len(src_rows),
            "cells": len(grid_rows) * NUM_JOINTS,
            "observed": 0,
            "bridged": 0,
            "missing": 0,
            "unobserved_by_reason": rc(),
            "missing_by_reason": rc(),
            "usable_frames": 0,
            "not_tracked_frames": 0,
            "filtered": 0,
            "unfiltered": 0,
            "suspect": 0,
            "blocked": 0,
            "mixed_rows": 0,
            "joints": [
                {
                    "joint": JOINTS[j],
                    "observed": 0,
                    "bridged": 0,
                    "missing": 0,
                    "missing_by_reason": rc(),
                    "filtered": 0,
                    "suspect": 0,
                    "blocked": 0,
                }
                for j in range(NUM_JOINTS)
            ],
            "gaps": {"gaps": oc(), "cells": oc()},
        }
        for k in grid_rows:
            have = [not math.isnan(float(kp[k, j, 0])) for j in range(NUM_JOINTS)]
            if sum(have[j] for j in essential) >= fraction * len(essential) - EPS:
                d["usable_frames"] += 1
            if all(reason[k, j] == NOT_TRACKED for j in range(NUM_JOINTS)):
                d["not_tracked_frames"] += 1
            d["mixed_rows"] += int(r.grid.mixed[k])
            for j in range(NUM_JOINTS):
                jd = d["joints"][j]
                name_r = REASON_NAMES[int(reason[k, j])]
                if name_r != "ok":
                    d["unobserved_by_reason"][name_r] += 1
                if have[j] and bridged_flag[k, j]:
                    d["bridged"] += 1
                    jd["bridged"] += 1
                elif have[j]:
                    d["observed"] += 1
                    jd["observed"] += 1
                else:
                    d["missing"] += 1
                    jd["missing"] += 1
                    d["missing_by_reason"][name_r] += 1
                    jd["missing_by_reason"][name_r] += 1
                if have[j]:
                    if filt[k, j]:
                        d["filtered"] += 1
                        jd["filtered"] += 1
                    else:
                        d["unfiltered"] += 1
        for i in src_rows:
            for j in range(NUM_JOINTS):
                if suspect[i, j]:
                    d["suspect"] += 1
                    d["joints"][j]["suspect"] += 1
                if blocked[i, j]:
                    d["blocked"] += 1
                    d["joints"][j]["blocked"] += 1
        inside_rows = set(src_rows)
        for g in range(len(table)):
            cells = sum(1 for i in range(int(table.start[g]), int(table.end[g]) + 1) if i in inside_rows)
            if cells:
                oname = OUTCOME_NAMES[int(table.outcome[g])]
                d["gaps"]["gaps"][oname] += 1
                d["gaps"]["cells"][oname] += cells
        out.append(d)
    return out


@pytest.mark.parametrize("block", range(4))
def test_t_qlt_11_differential_200_random_chains_against_a_slow_cell_by_cell_count(block):
    for seed in range(block * 50, block * 50 + 50):
        kp, score, t, tracked, in_segment, named = random_case(seed)
        r = run_quality_arrays(kp, score, t, tracked=tracked, in_segment=in_segment, intervals=named)
        want = slow_report(r, named)
        got = [iv.model_dump() for iv in r.report.intervals]
        assert len(got) == len(want), seed
        for g, w in zip(got, want, strict=True):
            for key in ("t_start", "t_end"):
                if w[key] is None:
                    assert g[key] is None, (seed, w["name"], key)
                else:
                    assert g[key] == pytest.approx(w[key]), (seed, w["name"], key)
            for key, value in w.items():
                if key not in ("t_start", "t_end"):
                    got_value = list(g[key]) if key == "joints" else g[key]  # a tuple in the model, a list here
                    assert got_value == value, (seed, w["name"], key)
        check_partition(r.report)


def test_t_qlt_11_the_essential_joints_of_the_oracle_are_the_mask_ones():
    assert QualityParams().mask.essential == ESSENTIAL


# --- more of T-QLT-11c and 11d: what the plan's mutants pointed at ----------------------------------------------------
def test_t_qlt_11c_an_end_one_ulp_above_a_row_time_does_not_take_the_row_in():
    t, kp, score = clean(30)
    above = float(np.nextafter(0.5, 1.0))  # the row at 0.5 is 1 ulp below the end: half-open, so it is out
    r = run_quality_arrays(kp, score, t, intervals={"a": (0.2, above)})
    assert r.report.intervals[1].rows == 9


def test_t_qlt_11d_the_frame_rule_uses_the_essential_joints_of_the_mask_parameters():
    t, kp, score = clean(60)
    score[10:25, [13, 14, 15, 16, 24, 25]] = 0.1  # six of the ten default essential joints out for 15 rows
    params = QualityParams(mask=MaskParams(essential=(5, 6, 11, 12)))
    assert run_quality_arrays(kp, score, t, params=params).report.intervals[0].usable_frames == 60  # 4 of 4 are there
    default = run_quality_arrays(kp, score, t).report.intervals[0]
    assert default.usable_frames == 45  # 4 of 10: rows 10 to 24 are frame_invalid in the mask, and not usable here


def test_t_qlt_11d_the_boundary_of_the_frame_rule_does_not_depend_on_float_rounding():
    t, kp, score = clean(60)
    score[10:25, [13, 14, 15]] = 0.1  # 7 of the 10 essential joints stay: exactly 0.7 of them (0.7 * 10 > 7 in floats)
    fraction = 0.1 * 7  # a share computed in floats: 0.7000000000000001, and fraction * 10 is 7.000000000000001
    params = QualityParams(mask=MaskParams(min_essential_fraction=fraction))
    assert run_quality_arrays(kp, score, t, params=params).report.intervals[0].usable_frames == 60


# --- T-QLT-11m: the swap warnings are about the segment ---------------------------------------------------------------
def swap_rows(kp, first: int, stop: int) -> None:
    for left, right in LR_PAIRS:
        kp[first:stop, [left, right]] = kp[first:stop, [right, left]]


def test_t_qlt_11m_a_swap_in_the_margin_is_no_warning_and_one_across_the_edge_is_clipped_to_the_segment():
    t, kp, score = clean(40)
    in_segment = np.zeros(40, dtype=bool)
    in_segment[10:31] = True
    swap_rows(kp, 2, 4)  # in the margin: the flag sees it, the report does not
    r = run_quality_arrays(kp, score, t, in_segment=in_segment)
    assert r.swap.blocked[2:5].any() and r.report.warnings == ()
    assert r.report.intervals[0].blocked == 0 and r.report.intervals[0].suspect == 0
    kp2 = clean(40)[1]
    swap_rows(kp2, 9, 11)  # events at rows 9 and 11: blocked rows 9 to 11, of which rows 10 and 11 are in the segment
    r2 = run_quality_arrays(kp2, score, t, in_segment=in_segment)
    assert r2.report.warnings == ("lr_swap_suspect@0.33-0.37",)
    seg = r2.report.intervals[0]
    assert seg.blocked == 2 * 2 * len(LR_PAIRS) and seg.suspect == 1 * 2 * len(LR_PAIRS)  # rows 10, 11 and row 10


def test_t_qlt_11m_a_run_of_one_row_has_one_time_in_its_warning():
    t, kp, score = clean(40)
    swap_rows(kp, 35, 40)  # the swap lasts to the end of the clip: one event, no exit, one blocked row
    r = run_quality_arrays(kp, score, t)
    assert r.report.warnings == ("lr_swap_suspect@1.17",)  # 35 / 30 s


def test_t_qlt_11m_two_swaps_are_two_warnings_in_time_order():
    t, kp, score = clean(60)
    swap_rows(kp, 40, 42)
    swap_rows(kp, 10, 12)
    r = run_quality_arrays(kp, score, t)
    # swapped rows [10, 12): events at rows 10 and 12, blocked rows 10 to 12 (t = 0.333 and 0.4); the same at 40 to 42
    assert r.report.warnings == ("lr_swap_suspect@0.33-0.40", "lr_swap_suspect@1.33-1.40")


def test_t_qlt_11d_the_frame_rule_counts_the_joints_that_are_left_after_the_chain_not_those_the_mask_kept():
    t, kp, score = clean(60)
    kp[20:22, [5, 6]] = kp[20:22, [6, 5]]  # the shoulders swap for two rows: events, outliers, blocked: NaN at the end
    params = QualityParams(mask=MaskParams(min_essential_fraction=0.9))  # the mask keeps all 10; 8 are left: not 9
    seg = run_quality_arrays(kp, score, t, params=params).report.intervals[0]
    assert seg.missing == 2 * 2 and seg.usable_frames == 58
    assert run_quality_arrays(kp, score, t).report.intervals[0].usable_frames == 60  # at 0.5, 8 of 10 are enough
