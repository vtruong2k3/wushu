"""T-MET-04a to 04f: hip height, variant B (P5.04): the scale of the segment, the lowest foot joint, the reason of every
row and its value, the range and the events, and what is refused.

Every expected number is re-derived here with plain loops and ``statistics.median`` from the arrays of the layer the
metric reads (never from the metric's own helpers). ``h_B = (g - y'_H) / Λ_segment`` is a true height (up is positive).
"""

from __future__ import annotations

import math
import statistics
from typing import Any

import numpy as np
import pytest

from helpers.metric_layers import (
    FPS,
    LH,
    LS,
    RH,
    body,
    bridge,
    cells,
    drop,
    edited,
    exact_layer,
)
from helpers.synth import apply_roll
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.hip_height import HipHeightResult, hip_height_a, hip_height_b
from taiji_ai.quality.layers_io import PoseFiltered

G = 40
SEG = (5, 35)  # rows of the segment: 30 rows, five margin rows on each side
N_SEG = SEG[1] - SEG[0]
EVERYTHING = [(0.0, 1000.0)]  # the coach confirmed the whole segment
FEET = (15, 16, 24, 25)  # LAnkle, RAnkle, LHeel, RHeel: the candidates of the floor (Appendix B1)
FEET_Y = (700.0, 720.0, 800.0, 810.0)  # px, y down: the heel of the right foot is the lowest


# --- independent re-derivation --------------------------------------------------------------------------------------
def seg_rows(layer: PoseFiltered) -> list[int]:
    return [g for g in range(len(layer.t_grid)) if layer.grid_in_segment[g]]


def trunk_px(row: np.ndarray) -> float:
    """``|mid-shoulder - mid-hip|`` of one row, NaN if a joint is missing."""
    p = row.astype(np.float64)
    sx, sy = (p[5, 0] + p[6, 0]) / 2.0, (p[5, 1] + p[6, 1]) / 2.0
    hx, hy = (p[11, 0] + p[12, 0]) / 2.0, (p[11, 1] + p[12, 1]) / 2.0
    return math.hypot(sx - hx, sy - hy)


def scale_of(layer: PoseFiltered) -> float:
    """The median of the finite trunk lengths over the segment rows of the layer."""
    lengths = [trunk_px(layer.keypoints[g]) for g in seg_rows(layer)]
    lengths = [x for x in lengths if math.isfinite(x) and x > 0.0]
    return statistics.median(lengths) if lengths else float("nan")


def tilt(x: float, y: float, roll_deg: float) -> float:
    """The second coordinate after the roll is taken out (origin 0): ``y' = -x sin r + y cos r``."""
    r = math.radians(roll_deg)
    return -x * math.sin(r) + y * math.cos(r)


def hip_y(row: np.ndarray, roll_deg: float = 0.0) -> float:
    p = row.astype(np.float64)
    return tilt((p[11, 0] + p[12, 0]) / 2.0, (p[11, 1] + p[12, 1]) / 2.0, roll_deg)


def lowest(row: np.ndarray, roll_deg: float = 0.0) -> float:
    """The largest ``y'`` over the foot joints that have a value; NaN if none has."""
    p = row.astype(np.float64)
    ys = [tilt(p[f, 0], p[f, 1], roll_deg) for f in FEET if math.isfinite(p[f, 0]) and math.isfinite(p[f, 1])]
    return max(ys) if ys else float("nan")


def expected_h(layer: PoseFiltered, grid_row: int, roll_deg: float = 0.0) -> float:
    row = layer.keypoints[grid_row]
    return (lowest(row, roll_deg) - hip_y(row, roll_deg)) / scale_of(layer)


def percentile(values: list[float], q: float) -> float:
    v = sorted(values)
    k = (len(v) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def stat(result: HipHeightResult, name: str) -> float | None:
    (s,) = [s for s in result.summary.statistics if s.name == name]
    return s.value


# --- layers -----------------------------------------------------------------------------------------------------------
def swinging(n: int = G) -> np.ndarray:
    return 400.0 + 20.0 * np.sin(np.arange(n) * 0.7)


def seg_layer(hip: np.ndarray | float | None = None, **kwargs: Any) -> PoseFiltered:
    """A segment of 30 rows in which the hips swing by +-20 px and the feet stay on the floor (``FEET_Y``)."""
    kp = body(G, swinging() if hip is None else hip)
    kp[:, list(FEET), 1] = np.array(FEET_Y, dtype=np.float32)
    return exact_layer(kp, segment=SEG, **kwargs)


def run(layer: PoseFiltered, **kwargs: Any) -> HipHeightResult:
    args: dict[str, Any] = {
        "stable_intervals": EVERYTHING,
        "flags": {},
        "camera_id": "camA",
        "view_category": "front",
    }
    args.update(kwargs)
    return hip_height_b(layer, **args)


def stable_of(layer: PoseFiltered, rows: int = 25) -> list[tuple[float, float]]:
    return [(float(layer.t_grid[SEG[0]]), float(layer.t_grid[SEG[0] + rows]))]


# --- T-MET-04a: the scale of the segment ----------------------------------------------------------------------------
def test_t_met_04a_the_scale_is_the_median_trunk_of_the_segment_rows_only():
    kp = body(50, 420.0, trunk=150.0)
    kp[:10] = body(10, 420.0, trunk=100.0)  # the margins have other trunks ...
    kp[40:] = body(10, 420.0, trunk=300.0)
    layer = exact_layer(kp, segment=(10, 40))
    p = run(layer).summary.parameters
    assert p["scale_px"] == pytest.approx(150.0, rel=1e-12) and p["scale_px"] == pytest.approx(scale_of(layer))
    assert p["scale_rows"] == 30 and p["scale_s"] == pytest.approx(30 / FPS)  # ... and they are not in it


def test_t_met_04a_it_is_a_median_not_a_mean_and_a_missing_or_bridged_row_is_handled_as_a_value_is():
    kp = body(40, 420.0, trunk=150.0)
    kp[:10] = body(10, 420.0, trunk=300.0)  # 10 rows at 300, 30 at 150: mean 187.5, median 150
    layer = exact_layer(kp)
    assert run(layer).summary.parameters["scale_px"] == pytest.approx(150.0)
    k, r, i = cells(layer)
    for row in range(10, 16):
        drop(k, r, row, LS, 1)  # six rows lose a shoulder: they have no trunk
    out = run(edited(layer, keypoints=k, reason=r)).summary.parameters
    assert out["scale_rows"] == 34 and out["scale_px"] == pytest.approx(150.0)
    k, r, i = cells(layer)
    bridge(k, r, i, 3, LH)
    bridge(k, r, i, 4, LS)
    assert run(edited(layer, reason=r, interpolated=i)).summary.parameters["scale_rows"] == 40  # a bridge is a value


def test_t_met_04a_the_scale_comes_from_every_valid_row_of_the_segment_not_only_the_eligible_ones():
    kp = body(G, 400.0)
    kp[SEG[0] : SEG[0] + 15] = body(15, 400.0, trunk=100.0)  # the first half of the segment has a shorter trunk
    layer = exact_layer(kp, segment=SEG)
    stable = [(float(layer.t_grid[SEG[0] + 15]), 1000.0)]  # the coach confirmed only the second half
    out = run(layer, stable_intervals=stable)
    assert out.summary.parameters["scale_px"] == pytest.approx(125.0)  # (100 + 150) / 2 over all 30 rows, not 150
    assert out.summary.parameters["scale_px"] == pytest.approx(scale_of(layer))
    assert out.series.reason.tolist() == [16] * 15 + [0] * 15


def test_t_met_04a_a_short_run_of_valid_rows_is_not_a_scale_and_the_good_rows_are_19_without_a_value():
    layer = exact_layer(body(30, 420.0))  # 30 rows at 30 fps: one second up to a rounding
    assert run(layer, min_scale_s=1.0).summary.parameters["scale_px"] == pytest.approx(150.0)
    assert run(layer, min_scale_s=1.0 + 1e-12).summary.parameters["scale_px"] == pytest.approx(150.0)  # a picosecond
    out = run(layer, min_scale_s=1.001)
    assert out.series.reason.tolist() == [19] * 30 and not np.isfinite(out.series.values).any()
    p = out.summary.parameters
    assert p["scale_px"] is None and p["scale_rows"] == 30 and p["scale_s"] == pytest.approx(1.0)
    assert out.summary.evidence == "insufficient_evidence" and out.summary.insufficient_reason == "scale_unavailable"


def test_t_met_04a_a_segment_without_a_valid_trunk_has_no_scale_and_every_good_row_is_19():
    layer = seg_layer()
    k, r, i = cells(layer)
    for row in range(G):
        drop(k, r, row, LS, 2)
    out = run(edited(layer, keypoints=k, reason=r))
    assert out.series.reason.tolist() == [19] * N_SEG
    p = out.summary.parameters
    assert p["scale_px"] is None and p["scale_rows"] == 0 and p["scale_s"] == 0.0


# --- T-MET-04b: the lowest foot joint -------------------------------------------------------------------------------
def feet_layout(lowest_of_row: list[int]) -> PoseFiltered:
    """Hips at 400, in each row one foot joint at 850 and the three others at 700: ``h_B`` is 450 / 150 = 3.0."""
    kp = body(G, 400.0)
    for s, joint in enumerate(lowest_of_row):
        for f in FEET:
            kp[SEG[0] + s, f, 1] = 850.0 if f == joint else 700.0
    return exact_layer(kp, segment=SEG)


def test_t_met_04b_each_of_the_four_joints_is_the_floor_when_it_is_the_lowest():
    order = [FEET[(s // 7) % 4] for s in range(N_SEG)]  # 7 rows with the left ankle lowest, 7 the right, ...
    layer = feet_layout(order)
    out = run(layer)
    assert out.series.reason.tolist() == [0] * N_SEG
    assert np.allclose(out.series.values, 3.0, rtol=0, atol=1e-12)  # the wrong joint would give 2.0
    assert [expected_h(layer, SEG[0] + s) for s in range(N_SEG)] == pytest.approx([3.0] * N_SEG)


def test_t_met_04b_a_missing_foot_joint_is_skipped_and_one_joint_is_enough():
    layer = feet_layout([15] * N_SEG)
    k, r, i = cells(layer)
    for s, joint in enumerate(FEET):
        drop(k, r, SEG[0] + s, joint, 1)  # rows 0 to 3: one joint missing in each; in row 0 it is the lowest (15)
    for f in (16, 24, 25):
        drop(k, r, SEG[0] + 4, f, 1)  # row 4: only the left ankle is left (at 850): still measured
    for f in (15, 16, 25):
        drop(k, r, SEG[0] + 5, f, 3)  # row 5: only the left heel is left, at 700
    out = run(edited(layer, keypoints=k, reason=r))
    assert out.series.reason.tolist() == [0] * N_SEG
    layer2 = edited(layer, keypoints=k, reason=r)
    for s in range(6):
        assert out.series.values[s] == pytest.approx(expected_h(layer2, SEG[0] + s), rel=1e-12), s
    assert out.series.values[0] == pytest.approx((700.0 - 400.0) / 150.0)  # row 0: the lowest (15) is gone: next is 700
    assert out.series.values[1] == pytest.approx(3.0)  # row 1: joint 16 gone, joint 15 is still lowest at 850
    assert out.series.values[4] == pytest.approx(3.0) and out.series.values[5] == pytest.approx(2.0)


def test_t_met_04b_with_no_foot_joint_the_row_has_the_reason_of_the_first_of_the_four():
    layer = seg_layer()
    k, r, i = cells(layer)
    for code, joint in zip((3, 1, 2, 4), FEET, strict=True):  # the four reasons differ: the first (15) gives 3
        drop(k, r, SEG[0] + 0, joint, code)
    for joint in FEET:
        drop(k, r, SEG[0] + 1, joint, 5)
        drop(k, r, SEG[0] + 2, joint, 2)
    drop(k, r, SEG[0] + 2, LH, 6)  # row 2: a hip as well: the hips come first in the order of the metric
    drop(k, r, SEG[0] + 3, RH, 4)  # row 3: only a hip, the feet are fine
    reasons = run(edited(layer, keypoints=k, reason=r)).series.reason.tolist()
    assert reasons[:4] == [3, 5, 6, 4]


# --- T-MET-04c: the value -------------------------------------------------------------------------------------------
def test_t_met_04c_the_values_are_the_height_of_the_hip_over_the_lowest_foot_in_units_of_the_segment_trunk():
    layer = seg_layer()
    out = run(layer)
    assert out.series.header.units == "body_lengths" and out.series.header.metric_name == "hip_height_b"
    assert out.series.header.metric_version == "1" and out.series.header.camera_id == "camA"
    for row in range(N_SEG):
        assert out.series.values[row] == pytest.approx(expected_h(layer, SEG[0] + row), rel=1e-12)
    assert out.series.values[0] == pytest.approx((810.0 - hip_y(layer.keypoints[SEG[0]])) / 150.0, rel=1e-12)
    assert (np.diff(out.series.values) != 0).any()  # the hips swing: the value is not constant
    assert out.series.values[np.argmin(swinging()[SEG[0] : SEG[1]])] == out.series.values.max()  # up is positive


def test_t_met_04c_the_roll_is_taken_out_of_every_foot_joint_before_the_lowest_is_chosen():
    kp = body(G, 400.0)
    kp[:, 15] = (300.0, 700.0)  # LAnkle: the lowest in the raw image
    kp[:, 16] = (900.0, 100.0)
    kp[:, 24] = (900.0, 100.0)
    kp[:, 25] = (800.0, 690.0)  # RHeel: higher in the raw image, but the lowest once the roll of -30 degrees is out
    layer = exact_layer(kp, segment=SEG)
    right = run(layer, roll_deg=-30.0).series.values
    assert right == pytest.approx([expected_h(layer, SEG[0], -30.0)] * N_SEG, rel=1e-12)
    wrong = (tilt(300.0, 700.0, -30.0) - hip_y(layer.keypoints[SEG[0]], -30.0)) / 150.0  # rotate the raw lowest point
    assert abs(right[0] - wrong) > 1.0  # the two readings differ by more than a body length
    assert run(layer).series.values[0] == pytest.approx((700.0 - 400.0) / 150.0)  # roll 0: the left ankle is the floor


@pytest.mark.parametrize("beta", [25.0, -12.5, 40.0])
def test_t_met_04c_the_image_rotated_by_the_roll_and_corrected_gives_the_same_values_as_the_upright_one(beta):
    layer = seg_layer()
    rolled = edited(layer, keypoints=apply_roll(layer.keypoints, beta, (960.0, 540.0)).astype(np.float32))
    assert np.allclose(run(rolled, roll_deg=beta).series.values, run(layer).series.values, rtol=0, atol=1e-4)
    assert not np.allclose(run(rolled).series.values, run(layer).series.values, atol=1e-2)  # and the roll matters


def test_t_met_04c_b_does_not_move_under_a_vertical_shift_or_a_zoom_of_the_image():
    layer = seg_layer()
    base = run(layer).series.values

    def shifted(lay: PoseFiltered, dy: float) -> PoseFiltered:
        k = lay.keypoints.copy()
        k[..., 1] += np.float32(dy)
        return edited(lay, keypoints=k)

    assert np.allclose(run(shifted(layer, 100.0)).series.values, base, rtol=0, atol=5e-6)  # the height has no level
    zoomed = edited(layer, keypoints=layer.keypoints * np.float32(2.0))
    assert np.allclose(run(zoomed).series.values, base, rtol=1e-6, atol=0)  # the scale zooms with the picture
    assert run(zoomed).summary.parameters["scale_px"] == pytest.approx(2.0 * run(layer).summary.parameters["scale_px"])


# --- T-MET-04d: the reason of every row -----------------------------------------------------------------------------
def scenario() -> tuple[PoseFiltered, list[int]]:
    """A segment of 30 rows with one situation per row (rows are numbered from the start of the segment).

    0 to 5: the left hip is missing with the reasons 1 to 6; 6: the right hip, 3; 7: both hips (4 on the left, 2 on the
    right: the first of the list wins); 8: the left hip is a bridged value; 9: a shoulder is missing (it only costs the
    scale a row); 10: no foot joint, with four different reasons (3, 1, 2, 4): the first of the four gives 3; 11: only
    the left ankle is left; 12: a hip and the four feet are missing: the hip's reason; 13: the lowest foot is a bridged
    value; 14 and 16: a hip missing, so 11, 13 and 15 are runs of one row; 27: a hip missing outside the interval.
    """
    layer = seg_layer()
    k, r, i = cells(layer)

    def g(s: int) -> int:
        return SEG[0] + s

    for s, code in enumerate(range(1, 7)):
        drop(k, r, g(s), LH, code)
    drop(k, r, g(6), RH, 3)
    drop(k, r, g(7), LH, 4)
    drop(k, r, g(7), RH, 2)
    bridge(k, r, i, g(8), LH)
    drop(k, r, g(9), LS, 1)
    for code, joint in zip((3, 1, 2, 4), FEET, strict=True):
        drop(k, r, g(10), joint, code)
    for joint in (16, 24, 25):
        drop(k, r, g(11), joint, 1)
    drop(k, r, g(12), LH, 5)
    for joint in FEET:
        drop(k, r, g(12), joint, 1)
    bridge(k, r, i, g(13), 25)
    drop(k, r, g(14), LH, 1)
    drop(k, r, g(16), RH, 1)
    drop(k, r, g(27), LH, 2)
    expected = [1, 2, 3, 4, 5, 6, 3, 4, 0, 0, 3, 21, 5, 21, 1, 21, 1] + [0] * 8 + [16] * 5
    return edited(layer, keypoints=k, reason=r, interpolated=i), expected


def test_t_met_04d_every_row_has_the_reason_of_the_precedence_and_a_value_only_where_it_is_measured():
    layer, expected = scenario()
    result = run(layer, stable_intervals=stable_of(layer), min_valid_s=0.05)
    s = result.series
    assert s.reason.tolist() == expected
    for row, code in enumerate(expected):
        if code == 0:
            assert s.values[row] == pytest.approx(expected_h(layer, SEG[0] + row), rel=1e-12), row
        else:
            assert math.isnan(s.values[row]), row
    assert 20 not in s.reason.tolist()  # B has no reference
    assert s.t_sec.tolist() == layer.t_grid[SEG[0] : SEG[1]].tolist()


def test_t_met_04d_the_coverage_and_the_counts_are_those_of_the_reasons_counted_by_hand():
    layer, expected = scenario()
    h = run(layer, stable_intervals=stable_of(layer), min_valid_s=0.05).series.header
    assert (h.coverage.total, h.coverage.eligible, h.coverage.quality, h.coverage.measured) == (30, 25, 13, 10)
    m = h.missing_by_reason
    assert (m.low_conf, m.non_finite, m.not_tracked, m.frame_invalid, m.outlier, m.no_frame) == (3, 1, 3, 2, 2, 1)
    assert (m.outside_interval, m.too_short, m.interval_flagged, m.scale_unavailable, m.reference_missing) == (
        5,
        3,
        0,
        0,
        0,
    )
    step = layer.meta.timeline.step_s
    first_run = (float(layer.t_grid[SEG[0] + 8]), float(layer.t_grid[SEG[0] + 9]) + step)  # rows 8 and 9
    second_run = (float(layer.t_grid[SEG[0] + 17]), float(layer.t_grid[SEG[0] + 24]) + step)  # rows 17 to 24
    assert [(i.t_start, i.t_end) for i in h.valid_intervals] == [first_run, second_run]


def test_t_met_04d_a_flag_makes_the_rows_inside_18_and_a_row_outside_stays_16():
    layer, _ = scenario()
    r = run(layer, stable_intervals=stable_of(layer), flags={"perspective_shift": True}).series
    assert r.reason.tolist() == [18] * 25 + [16] * 5  # 18 wins over a missing hip or foot; 16 wins over 18


def test_t_met_04d_a_segment_without_a_scale_gives_19_to_a_good_row_and_keeps_the_pose_reason_of_the_others():
    layer, expected = scenario()
    k, r, i = cells(layer)
    for row in range(G):
        for joint in (5, 6):
            drop(k, r, row, joint, 1)  # no row has a trunk
    out = run(edited(layer, keypoints=k, reason=r), stable_intervals=stable_of(layer)).series
    assert out.reason.tolist() == [c if c not in (0, 21) else 19 for c in expected]


# --- T-MET-04e: the summary -----------------------------------------------------------------------------------------
TIES = [0, 10, 20, 20, 10, 0, -10, -20, -20, -10]  # px added to the hip y: equal lowest at 2 and 3, highest at 7 and 8


def ties_layer() -> PoseFiltered:
    """Ten rows in the segment (rows 3 to 12 of 20): the hip goes down and up with equal extremes; the feet stay."""
    hip = np.full(20, 400.0)
    hip[3:13] = 400.0 + np.array(TIES)
    kp = body(20, hip)
    kp[:, list(FEET), 1] = np.array(FEET_Y, dtype=np.float32)
    layer = exact_layer(kp, segment=(3, 13))
    k, r, i = cells(layer)
    bridge(k, r, i, 4, LH)  # a measured row that leans on a bridged hip
    bridge(k, r, i, 6, 25)  # a measured row whose lowest foot joint (the right heel) is a bridge
    bridge(k, r, i, 7, 15)  # a bridged foot joint that is not the lowest: it is not used, so it is not counted
    bridge(k, r, i, 12, RH)  # a bridged row that the stable interval leaves out
    return edited(layer, reason=r, interpolated=i)


def test_t_met_04e_the_range_is_p95_minus_p5_and_the_events_are_the_first_extremes_with_up_positive():
    layer = ties_layer()
    stable = [(float(layer.t_grid[3]), float(layer.t_grid[12]))]  # rows 3 to 11: the row 12 is left out
    result = run(layer, stable_intervals=stable)
    h = [(810.0 - (400.0 + d)) / 150.0 for d in TIES[:9]]
    assert stat(result, "hip_height_range") == pytest.approx(percentile(h, 95) - percentile(h, 5), rel=1e-12)
    ev = {e.kind: e for e in result.summary.events}
    assert set(ev) == {"max", "min"} and len(result.summary.events) == 2
    assert ev["max"].t_start == ev["max"].t_end == float(layer.t_grid[3 + 7])  # the highest hip, the first of two
    assert ev["max"].value == pytest.approx((810.0 - 380.0) / 150.0)
    assert ev["min"].t_start == ev["min"].t_end == float(layer.t_grid[3 + 2])  # the lowest hip, the first of two
    assert ev["min"].value == pytest.approx((810.0 - 420.0) / 150.0)
    assert not any(e.uses_threshold for e in result.summary.events)


def test_t_met_04e_a_row_leans_on_a_bridge_when_a_hip_or_the_foot_joint_that_was_used_is_one():
    layer = ties_layer()
    stable = [(float(layer.t_grid[3]), float(layer.t_grid[12]))]
    assert stat(run(layer, stable_intervals=stable), "bridged_rows") == 2.0  # rows 4 (hip) and 6 (the right heel)


def test_t_met_04e_on_a_tie_for_the_lowest_foot_joint_the_first_of_the_list_is_the_one_used():
    kp = body(20, 400.0)
    kp[:, list(FEET), 1] = np.array((700.0, 720.0, 810.0, 810.0), dtype=np.float32)  # the heels tie for the floor
    layer = exact_layer(kp, segment=(3, 13))
    k, r, i = cells(layer)
    bridge(k, r, i, 5, 24)  # the first of the tie is a bridge: it is used, so counted
    bridge(k, r, i, 6, 25)  # the second of the tie is a bridge: the first (the left heel) is used, so not counted
    bridge(k, r, i, 7, 24)  # counted again: the answer is 2 if the first is used and 1 if the last is
    out = run(edited(layer, reason=r, interpolated=i))
    assert stat(out, "bridged_rows") == 2.0


def test_t_met_04e_the_summary_is_experimental_never_conclusive_and_says_what_was_used():
    layer = ties_layer()
    out = run(layer, stable_intervals=[(0.0, 5.0), (6.0, 7.0)], roll_deg=2.5, min_scale_s=0.2, min_valid_s=0.1)
    s = out.summary
    assert s.evidence == "sufficient" and s.insufficient_reason is None and s.metric_name == "hip_height_b"
    assert s.record_status == "experimental" and s.record_version is None and s.threshold_source is None
    assert s.conclusive is False and not any(x.uses_threshold for x in s.statistics)
    assert [x.name for x in s.statistics] == ["hip_height_range", "bridged_rows"]
    assert {x.units for x in s.statistics} == {"body_lengths", "count"}
    expected: dict[str, Any] = {
        "variant": "b", "roll_deg": 2.5, "min_scale_s": 0.2, "min_valid_s": 0.1, "percentile_low": 5,
        "percentile_high": 95, "scale_px": pytest.approx(150.0), "scale_rows": 10,
        "scale_s": pytest.approx(10 / FPS), "n_stable_intervals": 2, "filter_cutoff_hz": 6.0,
    }  # fmt: skip
    assert s.parameters == expected
    plain = run(layer).summary.parameters
    assert plain["min_scale_s"] is None and plain["min_valid_s"] is None and plain["roll_deg"] == 0.0
    assert s.coverage == out.series.header.coverage and s.valid_intervals == out.series.header.valid_intervals
    assert s.data_sources == layer.meta.data_sources and s.step_s == pytest.approx(1 / FPS)


def test_t_met_04e_two_measured_rows_are_enough_for_a_range_and_it_is_the_spread_of_the_two():
    hip = np.full(20, 400.0)
    hip[5], hip[6] = 380.0, 430.0  # the only two rows that keep their hips (the body moves with them: trunk 150)
    kp = body(20, hip)
    kp[:, list(FEET), 1] = np.array(FEET_Y, dtype=np.float32)
    layer = exact_layer(kp, segment=(3, 13))
    k, r, i = cells(layer)
    for row in (3, 4, 7, 8, 9, 10, 11, 12):
        k[row, LH : RH + 1, :] = np.nan  # joints 11 and 12, both coordinates: a cell has a position or none
        r[row, LH : RH + 1] = 1
    out = run(edited(layer, keypoints=k, reason=r))
    assert out.summary.evidence == "sufficient"
    assert stat(out, "hip_height_range") == pytest.approx(0.9 * 50.0 / 150.0, rel=1e-12)  # P95 - P5 of two values
    ev = {e.kind: e for e in out.summary.events}
    assert ev["max"].t_start == float(layer.t_grid[5]) and ev["min"].t_start == float(layer.t_grid[6])  # hip 380 is up


def assert_no_evidence(result: HipHeightResult, reason: str) -> None:
    s = result.summary
    assert s.evidence == "insufficient_evidence" and s.insufficient_reason == reason
    assert all(x.value is None for x in s.statistics) and len(s.statistics) == 2  # null, never 0
    assert s.events == () and s.conclusive is False


def test_t_met_04e_one_measured_row_is_too_short_for_a_range_and_gives_no_number():
    layer = seg_layer()
    k, r, i = cells(layer)
    for s in range(N_SEG):
        if s != 4:
            drop(k, r, SEG[0] + s, LH, 1)
    out = run(edited(layer, keypoints=k, reason=r))
    assert out.series.header.coverage.measured == 1
    assert_no_evidence(out, "too_short")


def test_t_met_04e_no_stable_interval_a_flag_and_no_scale_give_the_reason_that_holds_all_the_rows():
    layer = seg_layer()
    assert_no_evidence(run(layer, stable_intervals=[]), "outside_interval")
    assert_no_evidence(run(layer, flags={"perspective_shift": True}), "interval_flagged")
    k, r, i = cells(layer)
    k[:, LS] = np.nan
    r[:, LS] = 1
    assert_no_evidence(run(edited(layer, keypoints=k, reason=r)), "scale_unavailable")


def test_t_met_04e_the_most_frequent_reason_is_given_when_the_pose_is_the_problem():
    layer = seg_layer()
    k, r, i = cells(layer)
    for s in range(N_SEG):
        drop(k, r, SEG[0] + s, LH if s % 3 else RH, 5 if s < 20 else 1)  # 20 rows with 5, 10 rows with 1
    assert_no_evidence(run(edited(layer, keypoints=k, reason=r)), "outlier")


def test_t_met_04e_a_segment_with_no_row_is_no_frame_and_one_with_a_single_row_is_too_short():
    empty = run(edited(seg_layer(), grid_in_segment=np.zeros(G, dtype=bool)))
    assert (
        len(empty.series.t_sec) == 0 and empty.series.header.coverage.total == 0 and empty.series.header.step_s is None
    )
    assert_no_evidence(empty, "no_frame")
    only = np.zeros(G, dtype=bool)
    only[10] = True
    one = run(edited(seg_layer(), grid_in_segment=only))
    assert one.series.reason.tolist() == [21] and one.series.header.step_s is None
    assert_no_evidence(one, "too_short")


# --- T-MET-04f: refusals and the relation to variant A --------------------------------------------------------------
BAD_ARGUMENTS = [
    ({"layer": "x"}, "layer"),
    ({"layer": None}, "layer"),
    ({"stable_intervals": [(2.0, 1.0)]}, r"stable_intervals\[0\]"),
    ({"stable_intervals": None}, "stable_intervals"),
    ({"flags": {"perspective_shifts": True}}, "flags"),
    ({"flags": None}, "flags"),
    ({"roll_deg": 60.0}, "roll_deg"),
    ({"roll_deg": float("nan")}, "roll_deg"),
    ({"roll_deg": "5"}, "roll_deg"),
    ({"min_valid_s": 0.0}, "min_valid_s"),
    ({"min_valid_s": float("nan")}, "min_valid_s"),
    ({"min_scale_s": -1.0}, "min_scale_s"),
    ({"min_scale_s": True}, "min_scale_s"),
    ({"camera_id": "cam1"}, "camera_id"),
    ({"view_category": "Front!"}, "view_category"),
]


@pytest.mark.parametrize(("change", "message"), BAD_ARGUMENTS, ids=[str(b[0]) for b in BAD_ARGUMENTS])
def test_t_met_04f_a_bad_argument_is_refused_naming_it(change: dict[str, Any], message: str):
    args: dict[str, Any] = {
        "layer": seg_layer(), "stable_intervals": EVERYTHING, "flags": {}, "camera_id": "camA",
        "view_category": "front",
    }  # fmt: skip
    args.update(change)
    layer = args.pop("layer")
    with pytest.raises(MetricError, match=message):
        hip_height_b(layer, **args)


@pytest.mark.parametrize("roll", [60.0, float("nan"), "5"])
def test_t_met_04f_the_roll_and_the_minimums_are_checked_even_when_no_row_is_measured(roll):
    with pytest.raises(MetricError, match="roll_deg"):
        run(seg_layer(), stable_intervals=[], roll_deg=roll)  # every row is outside: nothing would use the roll
    with pytest.raises(MetricError, match="min_valid_s"):
        run(seg_layer(), stable_intervals=[], min_valid_s=-1.0)
    with pytest.raises(MetricError, match="min_scale_s"):
        run(seg_layer(), stable_intervals=[], min_scale_s=0.0)


def test_t_met_04f_b_has_no_reference_the_inputs_are_not_changed_and_the_result_is_read_only():
    layer = seg_layer()
    with pytest.raises(TypeError):
        hip_height_b(layer, reference=layer, stable_intervals=EVERYTHING, flags={}, camera_id="camA", view_category="f")  # type: ignore[call-arg]
    before = (layer.keypoints.copy(), layer.reason.copy())
    out = run(layer)
    assert np.array_equal(layer.keypoints, before[0]) and np.array_equal(layer.reason, before[1])
    for array in (out.series.values, out.series.reason, out.series.t_sec):
        assert not array.flags.writeable


def test_t_met_04f_the_two_variants_agree_on_which_rows_are_not_eligible():
    layer, _ = scenario()
    ref = exact_layer(body(60, 420.0))
    for flags in ({}, {"perspective_shift": True}):
        common = {"stable_intervals": stable_of(layer), "flags": flags, "camera_id": "camA", "view_category": "front"}
        a = hip_height_a(layer, reference=ref, **common).series.reason
        b = hip_height_b(layer, **common).series.reason
        for code in (16, 18):
            assert ((a == code) == (b == code)).all(), (flags, code)
