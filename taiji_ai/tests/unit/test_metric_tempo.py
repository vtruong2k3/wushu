"""T-MET-08b to 08e: the speed of a group of joints on the real clock (P5.06): the values, the reason of every row, the
statistics, and what is refused.

Every expected number is re-derived here with plain loops, ``math.hypot`` and ``statistics`` from the arrays of the
layer the metric reads (never from the metric's own helpers): ``V_G(t_k)`` is the median over the usable joints of
``|p_j(k+1) - p_j(k-1)| / (t_{k+1} - t_{k-1}) / Λ`` in body lengths per second.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

import numpy as np
import pytest

from helpers.metric_layers import LS, RS, body, bridge, cells, drop, edited, exact_layer
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.series import MetricResult
from taiji_ai.metrics.tempo import GROUP_METRIC_NAMES, group_speed
from taiji_ai.pose.skeleton import GROUPS
from taiji_ai.quality.layers_io import PoseFiltered

G = 40
SEG = (5, 35)  # rows of the segment: 30 rows, five margin rows on each side
N_SEG = SEG[1] - SEG[0]
HANDS_MOVING = {9: (150.0, 0.0), 10: (0.0, 300.0)}  # px/s: 1.0 and 2.0 trunk lengths per second at a trunk of 150 px


# --- independent re-derivation --------------------------------------------------------------------------------------
def trunk_px(row: np.ndarray) -> float:
    p = row.astype(np.float64)
    sx, sy = (p[5, 0] + p[6, 0]) / 2.0, (p[5, 1] + p[6, 1]) / 2.0
    hx, hy = (p[11, 0] + p[12, 0]) / 2.0, (p[11, 1] + p[12, 1]) / 2.0
    return math.hypot(sx - hx, sy - hy)


def scale_of(layer: PoseFiltered) -> float:
    """The median of the finite trunk lengths over the segment rows of the layer."""
    rows = [g for g in range(len(layer.t_grid)) if layer.grid_in_segment[g]]
    lengths = [x for x in (trunk_px(layer.keypoints[g]) for g in rows) if math.isfinite(x) and x > 0.0]
    return statistics.median(lengths) if lengths else float("nan")


def joint_speed(layer: PoseFiltered, g: int, joint: int, scale: float) -> float:
    """``|p(g+1) - p(g-1)| / (t(g+1) - t(g-1)) / Λ`` of one joint, NaN when a neighbour cell has no value."""
    a, b = layer.keypoints[g - 1, joint].astype(np.float64), layer.keypoints[g + 1, joint].astype(np.float64)
    dt = float(layer.t_grid[g + 1] - layer.t_grid[g - 1])
    return math.hypot(b[0] - a[0], b[1] - a[1]) / dt / scale


def group_value(layer: PoseFiltered, g: int, joints: tuple[int, ...], scale: float) -> float:
    speeds = [v for v in (joint_speed(layer, g, j, scale) for j in joints) if math.isfinite(v)]
    return statistics.median(speeds) if speeds else float("nan")


def stat(result: MetricResult, name: str) -> float | None:
    (s,) = [s for s in result.summary.statistics if s.name == name]
    return s.value


# --- layers -----------------------------------------------------------------------------------------------------------
def moving_layer(
    velocity: dict[int, tuple[float, float]],
    *,
    n: int = G,
    segment: tuple[int, int] | None = SEG,
    trunk: float = 150.0,
    t_grid: np.ndarray | None = None,
) -> PoseFiltered:
    """A standing body in which the given joints move at a constant velocity (px/s) along the clock ``t_grid``."""
    base = exact_layer(body(n, 400.0, trunk=trunk), segment=segment)
    t = np.asarray(base.t_grid if t_grid is None else t_grid, dtype=np.float64)
    kp = base.keypoints.astype(np.float64)
    for joint, (vx, vy) in velocity.items():
        kp[:, joint, 0] += vx * t
        kp[:, joint, 1] += vy * t
    return edited(base, keypoints=kp, t_grid=t)


def run(layer: PoseFiltered, **kwargs: Any) -> MetricResult:
    args: dict[str, Any] = {"group": "hands", "flags": {}, "camera_id": "camA", "view_category": "front"}
    args.update(kwargs)
    return group_speed(layer, **args)


def stable_of(layer: PoseFiltered, rows: int = 25) -> list[tuple[float, float]]:
    return [(float(layer.t_grid[SEG[0]]), float(layer.t_grid[SEG[0] + rows]))]


# --- T-MET-08b: the value ---------------------------------------------------------------------------------------------
def test_t_met_08b_a_joint_that_moves_at_a_constant_velocity_has_that_speed_over_the_trunk():
    layer = moving_layer(HANDS_MOVING)
    out = run(layer)
    assert out.series.header.units == "body_lengths_per_s" and out.series.header.metric_name == "speed_hands"
    assert out.series.header.metric_version == "1" and out.series.reason.tolist() == [0] * N_SEG
    assert np.allclose(out.series.values, 1.5, rtol=0, atol=1e-4)  # the median of 1.0 and 2.0 body lengths per second
    scale = scale_of(layer)
    assert scale == pytest.approx(150.0)
    for s in range(N_SEG):
        assert out.series.values[s] == pytest.approx(group_value(layer, SEG[0] + s, GROUPS["hands"], scale), abs=1e-9)


def test_t_met_08b_the_difference_is_divided_by_the_real_time_between_the_neighbours_not_by_a_constant_step():
    step = 1.0 / 30.0
    n, segment = 44, (5, 38)  # 33 rows: 32 intervals, eight whole cycles of the pattern, so the mean step is exact
    pattern = np.array([1.3, 1.3, 0.7, 0.7])  # the sum of two consecutive steps is 2.6, 2.0, 1.4, 2.0 steps: it changes
    t = np.concatenate([[0.0], np.cumsum(step * np.tile(pattern, n // 4))])[:n]
    layer = moving_layer(HANDS_MOVING, n=n, segment=segment, t_grid=t)
    out = run(layer)
    assert out.series.reason.tolist() == [0] * 33
    assert np.ptp(np.diff(out.series.t_sec)) > 0.01  # the clock is not uniform
    assert np.allclose(out.series.values, 1.5, rtol=0, atol=1e-4)  # the positions follow the true times: exact
    k = 7  # the two steps around the row 7 are the steps 2 and 3 of the pattern: 1.4 steps, not 2
    assert t[k + 1] - t[k - 1] == pytest.approx(1.4 * step)
    assumed = math.hypot(*(layer.keypoints[k + 1, 10] - layer.keypoints[k - 1, 10])) / (2 * step) / 150.0
    assert abs(assumed - 2.0) > 0.5  # what a constant step would say of the fast joint, against its true 2.0


def test_t_met_08b_each_group_uses_its_own_joints_and_the_median_of_them():
    velocity = {
        9: (150.0, 0.0), 10: (0.0, 300.0),  # hands: 1.0 and 2.0
        11: (90.0, 0.0), 12: (90.0, 0.0),  # hips: 0.6 and 0.6 ...
        5: (90.0, 0.0), 6: (90.0, 0.0),  # ... and the shoulders with them, so the trunk is still 150 px
        15: (0.0, 0.0), 16: (30.0, 0.0), 24: (60.0, 0.0), 25: (300.0, 0.0),  # feet: 0, 0.2, 0.4, 2.0
        13: (600.0, 0.0),  # a knee: in no group
    }  # fmt: skip
    layer = moving_layer(velocity)
    scale = scale_of(layer)
    expected = {"hands": 1.5, "hips": 0.6, "feet": 0.3}  # the median of the feet is the mean of the middle two
    for group, want in expected.items():
        out = run(layer, group=group)
        assert out.series.header.metric_name == GROUP_METRIC_NAMES[group] == f"speed_{group}"
        assert np.allclose(out.series.values, want, rtol=0, atol=1e-3), group
        for s in range(N_SEG):
            assert out.series.values[s] == pytest.approx(group_value(layer, SEG[0] + s, GROUPS[group], scale), abs=1e-9)


def test_t_met_08b_a_group_that_does_not_move_reads_exactly_zero_not_a_floor_and_not_a_missing_value():
    out = run(moving_layer(HANDS_MOVING), group="feet")
    assert out.series.reason.tolist() == [0] * N_SEG and (out.series.values == 0.0).all()


def test_t_met_08b_the_scale_is_the_median_trunk_of_the_rows_of_the_segment_only():
    velocity = {9: (120.0, 0.0), 10: (120.0, 0.0)}
    assert np.allclose(run(moving_layer(velocity, trunk=120.0)).series.values, 1.0, rtol=0, atol=1e-4)
    assert np.allclose(run(moving_layer(velocity, trunk=150.0)).series.values, 0.8, rtol=0, atol=1e-4)
    layer = moving_layer(velocity)  # trunk 150 inside; the margins get a trunk of 250 and must not move the scale
    k = layer.keypoints.copy()
    k[: SEG[0], [LS, RS], 1] -= np.float32(100.0)
    k[SEG[1] :, [LS, RS], 1] -= np.float32(100.0)
    out = run(edited(layer, keypoints=k))
    assert out.summary.parameters["scale_px"] == pytest.approx(150.0)
    assert np.allclose(out.series.values, 0.8, rtol=0, atol=1e-4)


# --- T-MET-08c: the reason of every row -------------------------------------------------------------------------------
def scenario() -> tuple[PoseFiltered, list[int]]:
    """The hands (joints 9 and 10) move; cells are lost, one by one, and a row is rated by its two neighbour cells.

    A cell (grid row ``g``, joint) that is missing takes away that joint at the rows ``g - 1`` and ``g + 1``, and a row
    is lost only when both joints are. The edits and what they mean for the rows ``s = g - 5`` of the segment:

    * (6, 9): the joint 9 is lost at s0 and s2, the joint 10 carries them: measured;
    * (10, 9) and (10, 10) with the reasons 2 and 4: s4 and s6 have no usable joint (reason 2: the first joint's first
      missing neighbour), while s5, whose own cells are the missing ones but whose neighbours are there, is measured;
    * (14, 10): the joint 10 is lost at s8 and s10: measured;
    * (17, 9) with 5 and (19, 10) with 6: s13 has no usable joint and gets the reason of the joint 9's missing
      neighbour (5); s11 and s15 are measured;
    * (22, 9) and (24, 9): s18 has both neighbours of the joint 9 missing: the joint 10 carries it;
    * (27, 9) bridged: s21 and s23 lean on a bridge and are measured;
    * (32, 9) and (32, 10): outside the interval, where 16 wins.
    """
    layer = moving_layer(HANDS_MOVING)
    k, r, i = cells(layer)
    drop(k, r, 6, 9, 1)
    drop(k, r, 10, 9, 2)
    drop(k, r, 10, 10, 4)
    drop(k, r, 14, 10, 3)
    drop(k, r, 17, 9, 5)
    drop(k, r, 19, 10, 6)
    drop(k, r, 22, 9, 1)
    drop(k, r, 24, 9, 1)
    bridge(k, r, i, 27, 9)
    drop(k, r, 32, 9, 2)
    drop(k, r, 32, 10, 2)
    expected = [0, 0, 0, 0, 2, 0, 2] + [0] * 6 + [5] + [0] * 11 + [16] * 5
    return edited(layer, keypoints=k, reason=r, interpolated=i), expected


def test_t_met_08c_a_row_is_rated_by_its_two_neighbour_cells_and_not_by_its_own():
    layer, expected = scenario()
    s = run(layer, intervals=stable_of(layer)).series
    assert s.reason.tolist() == expected
    scale = scale_of(layer)
    for row, code in enumerate(expected):
        if code == 0:
            want = group_value(layer, SEG[0] + row, GROUPS["hands"], scale)
            assert s.values[row] == pytest.approx(want, abs=1e-9), row
        else:
            assert math.isnan(s.values[row]), row


def test_t_met_08c_when_one_joint_is_lost_the_group_is_the_speed_of_the_other_one():
    layer, expected = scenario()
    out = run(layer, intervals=stable_of(layer)).series.values
    assert out[0] == pytest.approx(2.0, abs=1e-3)  # s0: the joint 9 (1.0) is lost, the joint 10 (2.0) is the group
    assert out[2] == pytest.approx(2.0, abs=1e-3)  # s2: the joint 9 is lost by its cell before
    assert out[8] == pytest.approx(1.0, abs=1e-3)  # s8: the joint 10 is lost, the joint 9 (1.0) is the group
    assert out[10] == pytest.approx(1.0, abs=1e-3) and out[15] == pytest.approx(1.0, abs=1e-3)  # the joint 10 again
    assert out[11] == pytest.approx(2.0, abs=1e-3) and out[18] == pytest.approx(2.0, abs=1e-3)  # the joint 9 again
    assert out[21] == pytest.approx(1.5, abs=1e-3) and out[23] == pytest.approx(1.5, abs=1e-3)  # a bridge is a value
    assert out[5] == pytest.approx(1.5, abs=1e-3)  # s5: its own cells are lost but its neighbours are not: both joints


def test_t_met_08c_a_row_that_lost_both_neighbours_of_the_first_joint_is_given_the_reason_of_the_cell_before():
    layer = moving_layer(HANDS_MOVING)
    k, r, _ = cells(layer)
    drop(k, r, 19, 9, 2)  # the row g20 has the cell before (reason 2) and the cell after (reason 4) of the joint 9 lost
    drop(k, r, 21, 9, 4)
    drop(k, r, 19, 10, 1)  # ... and its cell before of the joint 10, so that no joint is usable at it
    out = run(edited(layer, keypoints=k, reason=r)).series
    # s13 (g18): the cell after of both joints is lost, the joint 9's reason 2 is the group's; s15 (g20): 2, not 4;
    # s17 (g22) has the cell before of the joint 9 lost but the joint 10 is usable: measured
    assert out.reason.tolist() == [0] * 13 + [2, 0, 2] + [0] * 14
    assert math.isnan(out.values[13]) and math.isnan(out.values[15]) and out.values[17] == pytest.approx(2.0, abs=1e-3)


def test_t_met_08c_the_coverage_and_the_counts_are_those_of_the_reasons_counted_by_hand():
    layer, expected = scenario()
    h = run(layer, intervals=stable_of(layer)).series.header
    assert (h.coverage.total, h.coverage.eligible, h.coverage.quality, h.coverage.measured) == (30, 25, 22, 22)
    m = h.missing_by_reason
    assert (m.non_finite, m.outlier, m.outside_interval) == (2, 1, 5)
    assert (m.view_not_supported, m.interval_flagged, m.scale_unavailable, m.reference_missing) == (0, 0, 0, 0)
    assert (m.too_short, m.run_edge) == (0, 0)
    step = layer.meta.timeline.step_s
    runs = [(0, 3), (5, 5), (7, 12), (14, 24)]
    assert [(i.t_start, i.t_end) for i in h.valid_intervals] == [
        (float(layer.t_grid[SEG[0] + a]), float(layer.t_grid[SEG[0] + b]) + step) for a, b in runs
    ]


def test_t_met_08c_a_measured_run_shorter_than_the_minimum_becomes_21_and_only_that_row_changes():
    layer, expected = scenario()
    out = run(layer, intervals=stable_of(layer), min_valid_s=0.05)  # two rows are needed: the row s5 stands alone
    want = list(expected)
    want[5] = 21
    assert out.series.reason.tolist() == want and math.isnan(out.series.values[5])
    h = out.series.header
    assert (h.coverage.quality, h.coverage.measured, h.missing_by_reason.too_short) == (22, 21, 1)
    assert len(h.valid_intervals) == 3


def test_t_met_08c_a_flag_makes_the_rows_inside_18_and_the_others_do_not_block():
    layer, expected = scenario()
    flagged = run(layer, intervals=stable_of(layer), flags={"perspective_shift": True}).series
    assert flagged.reason.tolist() == [18] * 25 + [16] * 5  # 18 wins over a lost joint; 16 wins over 18
    for flags in ({"occlusion": True}, {"orientation_change": True}, {"perspective_shift": False}):
        assert run(layer, intervals=stable_of(layer), flags=flags).series.reason.tolist() == expected, flags


def test_t_met_08c_without_intervals_the_whole_segment_is_looked_at():
    layer, expected = scenario()
    out = run(layer).series.reason.tolist()
    assert 16 not in out and out[:25] == expected[:25]
    assert out[26] == 2 and out[28] == 2  # the cells of the grid row 32 take the joints away at the rows 31 and 33


def test_t_met_08c_a_segment_without_a_scale_gives_19_to_a_good_row_and_keeps_the_pose_reason_of_the_others():
    layer, expected = scenario()
    k, r, i = cells(layer)
    for row in range(G):
        for joint in (5, 6):
            drop(k, r, row, joint, 1)  # no row has a trunk
    out = run(edited(layer, keypoints=k, reason=r), intervals=stable_of(layer)).series
    assert out.reason.tolist() == [19 if c == 0 else c for c in expected]


def test_t_met_08c_valid_rows_that_do_not_last_the_minimum_give_no_scale_and_every_good_row_is_19():
    layer = moving_layer(HANDS_MOVING)  # 30 rows in the segment: one second up to a rounding
    assert run(layer, min_scale_s=1.0).series.reason.tolist() == [0] * N_SEG
    assert run(layer, min_scale_s=1.0 + 1e-12).series.reason.tolist() == [0] * N_SEG  # a picosecond short is not short
    out = run(layer, min_scale_s=1.001)
    assert out.series.reason.tolist() == [19] * N_SEG and np.isnan(out.series.values).all()
    p = out.summary.parameters
    assert p["scale_px"] is None and p["scale_rows"] == N_SEG and p["scale_s"] == pytest.approx(1.0)
    assert out.summary.insufficient_reason == "scale_unavailable"


def test_t_met_08c_a_row_with_no_neighbour_on_a_side_of_the_grid_is_22_and_a_missing_scale_comes_first():
    first = run(moving_layer(HANDS_MOVING, segment=(0, 30))).series
    assert first.reason.tolist() == [22] + [0] * 29 and math.isnan(first.values[0])
    last = run(moving_layer(HANDS_MOVING, segment=(10, 40))).series
    assert last.reason.tolist() == [0] * 29 + [22]
    whole = run(moving_layer(HANDS_MOVING, segment=None)).series
    assert whole.reason.tolist() == [22] + [0] * 38 + [22]
    h = whole.header
    assert (h.coverage.total, h.coverage.quality, h.coverage.measured, h.missing_by_reason.run_edge) == (40, 40, 38, 2)
    layer = moving_layer(HANDS_MOVING, segment=(0, 30))
    k, r, i = cells(layer)
    for row in range(G):
        drop(k, r, row, 5, 1)
    assert run(edited(layer, keypoints=k, reason=r)).series.reason.tolist() == [19] * 30  # 19 before 22


def test_t_met_08c_the_margin_is_used_so_the_first_and_the_last_row_of_a_segment_inside_the_grid_are_measured():
    layer = moving_layer(HANDS_MOVING)
    out = run(layer).series
    assert out.reason[0] == 0 and out.reason[-1] == 0 and not {17, 20, 22} & set(out.reason.tolist())


# --- T-MET-08d: the statistics ----------------------------------------------------------------------------------------
def wave_layer() -> PoseFiltered:
    """The two hands swing, so the speed of the group changes from row to row."""
    layer = moving_layer({})
    t = layer.t_grid
    k = layer.keypoints.astype(np.float64)
    k[:, 9, 0] += 40.0 * np.sin(2.0 * np.pi * 1.2 * t)
    k[:, 10, 1] += 25.0 * np.cos(2.0 * np.pi * 0.8 * t)
    return edited(layer, keypoints=k)


def test_t_met_08d_the_duration_the_median_and_the_variation_are_the_independent_ones():
    layer = wave_layer()
    result = run(layer)
    scale = scale_of(layer)
    values = [group_value(layer, g, GROUPS["hands"], scale) for g in range(SEG[0], SEG[1])]
    assert stat(result, "segment_duration_s") == pytest.approx(N_SEG * layer.meta.timeline.step_s, rel=1e-12)
    assert stat(result, "speed_median") == pytest.approx(statistics.median(values), abs=1e-9)
    assert stat(result, "speed_cv") == pytest.approx(statistics.pstdev(values) / statistics.mean(values), abs=1e-9)
    assert 0.1 < stat(result, "speed_cv") < 2.0  # the speed does change: a variation that is not 0


def test_t_met_08d_the_duration_is_that_of_the_whole_segment_even_when_some_rows_are_not_measured():
    layer, _ = scenario()
    out = run(layer, intervals=stable_of(layer))
    assert out.series.header.coverage.measured < N_SEG
    assert stat(out, "segment_duration_s") == pytest.approx(N_SEG * layer.meta.timeline.step_s, rel=1e-12)


def test_t_met_08d_a_group_that_does_not_move_has_a_median_of_zero_and_no_variation_to_report():
    out = run(moving_layer(HANDS_MOVING), group="feet")
    assert out.summary.evidence == "sufficient" and stat(out, "speed_median") == 0.0
    assert stat(out, "speed_cv") is None  # a mean of 0 has no coefficient of variation: null, not 0 and not NaN


def test_t_met_08d_one_measured_row_gives_numbers_and_a_variation_of_zero():
    layer = moving_layer(HANDS_MOVING)
    k, r, i = cells(layer)
    for g in range(G):
        if g not in (19, 21):  # only the cells of the rows 19 and 21 exist: the row 20 is the only one that can be read
            for joint in (9, 10):
                drop(k, r, g, joint, 1)
    out = run(edited(layer, keypoints=k, reason=r))
    assert out.series.header.coverage.measured == 1 and out.summary.evidence == "sufficient"
    assert stat(out, "speed_median") == pytest.approx(1.5, abs=1e-3) and stat(out, "speed_cv") == 0.0


def test_t_met_08d_a_row_leans_on_a_bridge_when_a_usable_joint_has_a_bridged_neighbour_and_is_measured():
    layer, _ = scenario()
    assert stat(run(layer, intervals=stable_of(layer)), "bridged_rows") == 2.0  # s21 and s23, around the bridged cell
    k, r, i = cells(layer)
    bridge(k, r, i, 31, 10)  # a bridged neighbour of rows that are outside the interval
    assert stat(run(edited(layer, reason=r, interpolated=i), intervals=stable_of(layer)), "bridged_rows") == 2.0


def test_t_met_08d_a_bridge_of_a_joint_that_is_not_usable_at_the_row_is_not_counted():
    layer = moving_layer(HANDS_MOVING)
    k, r, i = cells(layer)
    bridge(k, r, i, 20, 9)  # g19 reads it (the joint 9 is usable there): counted
    drop(k, r, 22, 9, 1)  # g21 has the bridged cell before and a lost cell after for the joint 9: not usable, not read
    out = run(edited(layer, keypoints=k, reason=r, interpolated=i))
    assert out.series.reason.tolist() == [0] * N_SEG  # the joint 10 carries g21
    assert out.series.values[16] == pytest.approx(2.0, abs=1e-3)  # s16 = g21: the joint 10 alone
    assert stat(out, "bridged_rows") == 1.0


def test_t_met_08d_the_summary_is_experimental_never_conclusive_has_no_event_and_uses_no_threshold():
    s = run(wave_layer()).summary
    assert s.evidence == "sufficient" and s.insufficient_reason is None and s.metric_name == "speed_hands"
    assert s.record_status == "experimental" and s.record_version is None and s.threshold_source is None
    assert s.conclusive is False and s.events == () and not any(x.uses_threshold for x in s.statistics)
    assert [x.name for x in s.statistics] == ["segment_duration_s", "speed_median", "speed_cv", "bridged_rows"]
    assert [x.units for x in s.statistics] == ["s", "body_lengths_per_s", "ratio", "count"]


def test_t_met_08d_the_parameters_say_what_was_used():
    layer = wave_layer()
    p = run(layer, intervals=[(0.0, 5.0), (6.0, 7.0)], min_valid_s=0.1, min_scale_s=0.5).summary.parameters
    assert p == {
        "group": "hands", "min_valid_s": 0.1, "min_scale_s": 0.5, "scale_px": pytest.approx(150.0), "scale_rows": 30,
        "scale_s": pytest.approx(30 * layer.meta.timeline.step_s), "n_intervals": 2, "pause_tau": None,
        "pause_min_s": None,
    }  # fmt: skip
    plain = run(layer).summary.parameters
    assert plain["n_intervals"] is None and plain["min_valid_s"] is None and plain["min_scale_s"] is None
    asked = run(
        layer, pause_tau=0.25, pause_min_s=0.3
    ).summary.parameters  # the pauses of P5.07: what was asked is echoed
    assert asked["pause_tau"] == 0.25 and asked["pause_min_s"] == 0.3 and plain["pause_tau"] is None
    for group in GROUP_METRIC_NAMES:  # the group that was asked for is the one that is echoed
        result = run(layer, group=group)
        assert result.summary.parameters["group"] == group and result.series.header.metric_name == f"speed_{group}"


def assert_no_evidence(result: MetricResult, reason: str) -> None:
    s = result.summary
    assert s.evidence == "insufficient_evidence" and s.insufficient_reason == reason
    assert all(x.value is None for x in s.statistics) and len(s.statistics) == 4  # null, never 0
    assert s.events == () and s.conclusive is False


def test_t_met_08d_no_measured_row_gives_no_number_and_the_reason_that_holds_the_rows():
    layer = moving_layer(HANDS_MOVING)
    assert_no_evidence(run(layer, intervals=[]), "outside_interval")
    assert_no_evidence(run(layer, flags={"perspective_shift": True}), "interval_flagged")
    k, r, i = cells(layer)
    for row in range(G):
        drop(k, r, row, 5, 1)
    assert_no_evidence(run(edited(layer, keypoints=k, reason=r)), "scale_unavailable")
    k, r, i = cells(layer)
    for row in range(G):  # both hands lost everywhere: a row has the reason of the joint 9's cell before it
        for joint in (9, 10):
            drop(k, r, row, joint, 5 if row < 25 else 1)
    assert_no_evidence(run(edited(layer, keypoints=k, reason=r)), "outlier")  # 21 rows with 5, 9 rows with 1


def test_t_met_08d_a_segment_with_no_row_is_no_frame_and_one_with_a_single_row_is_too_short():
    empty = run(edited(moving_layer(HANDS_MOVING), grid_in_segment=np.zeros(G, dtype=bool)))
    assert (
        len(empty.series.t_sec) == 0 and empty.series.header.coverage.total == 0 and empty.series.header.step_s is None
    )
    assert_no_evidence(empty, "no_frame")
    only = np.zeros(G, dtype=bool)
    only[10] = True
    one = run(edited(moving_layer(HANDS_MOVING), grid_in_segment=only))
    assert one.series.reason.tolist() == [21] and one.series.header.step_s is None
    assert_no_evidence(one, "too_short")


# --- T-MET-08e: refusals ----------------------------------------------------------------------------------------------
BAD_ARGUMENTS = [
    ({"layer": "x"}, "layer"),
    ({"layer": None}, "layer"),
    ({"group": "arms"}, "group"),
    ({"group": None}, "group"),
    ({"group": "Hands"}, "group"),
    ({"intervals": [(2.0, 1.0)]}, r"intervals\[0\]"),
    ({"intervals": "all"}, "intervals"),
    ({"flags": {"perspective_shifts": True}}, "flags"),
    ({"flags": None}, "flags"),
    ({"min_valid_s": 0.0}, "min_valid_s"),
    ({"min_valid_s": float("nan")}, "min_valid_s"),
    ({"min_scale_s": -1.0}, "min_scale_s"),
    ({"min_scale_s": True}, "min_scale_s"),
    ({"camera_id": "cam1"}, "camera_id"),
    ({"view_category": "Front!"}, "view_category"),
]


@pytest.mark.parametrize(("change", "message"), BAD_ARGUMENTS, ids=[str(b[0]) for b in BAD_ARGUMENTS])
def test_t_met_08e_a_bad_argument_is_refused_naming_it(change: dict[str, Any], message: str):
    args: dict[str, Any] = {
        "layer": moving_layer(HANDS_MOVING), "group": "hands", "flags": {}, "camera_id": "camA",
        "view_category": "front",
    }  # fmt: skip
    args.update(change)
    layer = args.pop("layer")
    with pytest.raises(MetricError, match=message):
        group_speed(layer, **args)


def test_t_met_08e_the_minimums_are_checked_even_when_no_row_is_measured_and_there_is_no_roll():
    layer = moving_layer(HANDS_MOVING)
    with pytest.raises(MetricError, match="min_valid_s"):
        run(layer, intervals=[], min_valid_s=-1.0)  # every row is outside: nothing would use the minimum
    with pytest.raises(MetricError, match="min_scale_s"):
        run(layer, intervals=[], min_scale_s=0.0)
    with pytest.raises(TypeError):
        run(layer, roll_deg=5.0)  # a speed is the norm of a displacement: a rotation of the image does not change it


def test_t_met_08e_the_three_groups_are_three_metrics_the_inputs_are_not_changed_and_the_result_is_read_only():
    assert GROUP_METRIC_NAMES == {"hands": "speed_hands", "hips": "speed_hips", "feet": "speed_feet"}
    layer = moving_layer(HANDS_MOVING)
    before = (layer.keypoints.copy(), layer.reason.copy(), layer.t_grid.copy())
    out = run(layer)
    assert np.array_equal(layer.keypoints, before[0]) and np.array_equal(layer.reason, before[1])
    assert np.array_equal(layer.t_grid, before[2])
    for array in (out.series.values, out.series.reason, out.series.t_sec):
        assert not array.flags.writeable
