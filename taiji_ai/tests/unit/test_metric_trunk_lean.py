"""T-MET-06b to 06e and T-MET-07: the trunk lean in the image plane (P5.05): the angle, the reason of every row, the
statistics, what is refused, and the view that does not fit.

Every expected number is re-derived here with plain loops, ``math.atan2`` and ``statistics.median`` from the arrays of
the layer the metric reads (never from the metric's own helpers). ``θ = atan2(x_S - x_H, y_H - y_S) - roll`` in
degrees: 0 is vertical and the angle is positive when the top of the trunk leans to the image right.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

import numpy as np
import pytest

from helpers.metric_layers import LH, LS, RH, RS, body, bridge, cells, drop, edited, exact_layer
from helpers.synth import apply_roll
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.rows import VIEWS
from taiji_ai.metrics.series import MetricResult
from taiji_ai.metrics.trunk_lean import METRIC_NAMES, SUPPORTED_VIEWS, trunk_lean
from taiji_ai.quality.layers_io import PoseFiltered

G = 40
SEG = (5, 35)  # rows of the segment: 30 rows, five margin rows on each side
N_SEG = SEG[1] - SEG[0]


# --- independent re-derivation --------------------------------------------------------------------------------------
def wrap(angle: float) -> float:
    """To (-180, 180]."""
    w = (angle + 180.0) % 360.0 - 180.0
    return 180.0 if w == -180.0 else w


def expected_theta(row: np.ndarray, roll_deg: float = 0.0) -> float:
    p = row.astype(np.float64)
    hx, hy = (p[11, 0] + p[12, 0]) / 2.0, (p[11, 1] + p[12, 1]) / 2.0
    sx, sy = (p[5, 0] + p[6, 0]) / 2.0, (p[5, 1] + p[6, 1]) / 2.0
    dx, dy = sx - hx, hy - sy
    if dx == 0.0 and dy == 0.0:
        return float("nan")
    return wrap(math.degrees(math.atan2(dx, dy)) - roll_deg)


def percentile(values: list[float], q: float) -> float:
    v = sorted(values)
    k = (len(v) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def stat(result: MetricResult, name: str) -> float | None:
    (s,) = [s for s in result.summary.statistics if s.name == name]
    return s.value


# --- layers -----------------------------------------------------------------------------------------------------------
def lean_body(theta_deg: np.ndarray) -> np.ndarray:
    """``(n, 26, 2)`` float32: the mid-hip at (450, 400), the mid-shoulder 150 px away at ``theta`` from vertical."""
    n = len(theta_deg)
    kp = body(n, 400.0)
    t = np.radians(np.asarray(theta_deg, dtype=np.float64))
    sx, sy = 450.0 + 150.0 * np.sin(t), 400.0 - 150.0 * np.cos(t)
    kp[:, LS, 0], kp[:, LS, 1] = sx - 50.0, sy
    kp[:, RS, 0], kp[:, RS, 1] = sx + 50.0, sy
    return kp


def seg_layer(theta: np.ndarray | None = None, **kwargs: Any) -> PoseFiltered:
    th = np.linspace(-25.0, 35.0, G) if theta is None else np.asarray(theta, dtype=np.float64)
    return exact_layer(lean_body(th), segment=SEG, **kwargs)


def run(layer: PoseFiltered, **kwargs: Any) -> MetricResult:
    args: dict[str, Any] = {"plane": "lr", "view_category": "front", "flags": {}, "camera_id": "camA"}
    args.update(kwargs)
    return trunk_lean(layer, **args)


def stable_of(layer: PoseFiltered, rows: int = 25) -> list[tuple[float, float]]:
    return [(float(layer.t_grid[SEG[0]]), float(layer.t_grid[SEG[0] + rows]))]


# --- T-MET-06b: the angle ---------------------------------------------------------------------------------------------
MIXED = [0.0, 10.0, -7.5, 30.0, 89.0, -89.0, 120.0, 179.5, -179.5, 45.0, 180.0, -170.0, 170.0, 1e-3]


def mixed_layer() -> PoseFiltered:
    th = np.zeros(G)
    th[SEG[0] : SEG[0] + len(MIXED)] = MIXED
    return seg_layer(th)


def test_t_met_06b_theta_is_atan2_of_the_hip_to_shoulder_vector_in_degrees_positive_to_the_image_right():
    layer = mixed_layer()
    out = run(layer)
    assert out.series.header.units == "deg" and out.series.header.metric_name == "trunk_lean_lr"
    assert out.series.header.metric_version == "1" and out.series.header.view_category == "front"
    for s in range(N_SEG):
        assert out.series.values[s] == pytest.approx(expected_theta(layer.keypoints[SEG[0] + s]), abs=1e-9), s
    for s, intended in enumerate(MIXED):  # the fixture is what it says: the top leans to the right for a positive angle
        want = 180.0 if intended == -180.0 else intended
        assert out.series.values[s] == pytest.approx(want, abs=1e-3), (s, intended)
    assert out.series.values[1] > 0.0 > out.series.values[2]  # +10 leans to the image right, -7.5 to the left
    assert out.series.values[10] == 180.0  # exactly upside down is +180, never -180


@pytest.mark.parametrize("roll", [20.0, -30.0, 44.0])
def test_t_met_06b_the_roll_is_subtracted_and_the_result_is_wrapped_to_minus_180_exclusive_180_inclusive(roll):
    layer = mixed_layer()
    out = run(layer, roll_deg=roll)
    for s in range(N_SEG):
        assert out.series.values[s] == pytest.approx(expected_theta(layer.keypoints[SEG[0] + s], roll), abs=1e-9), s
    assert out.series.values[11] == pytest.approx(wrap(-170.0 - roll), abs=1e-3)  # -170 - 20 = -190 wraps to 170
    assert (np.abs(out.series.values) <= 180.0).all()


def test_t_met_06b_theta_does_not_move_under_a_shift_or_a_zoom_of_the_image():
    layer = seg_layer()
    base = run(layer).series.values

    def moved(lay: PoseFiltered, dx: float, dy: float) -> PoseFiltered:
        k = lay.keypoints.copy()
        k[..., 0] += np.float32(dx)
        k[..., 1] += np.float32(dy)
        return edited(lay, keypoints=k)

    assert np.allclose(run(moved(layer, 200.0, 100.0)).series.values, base, rtol=0, atol=1e-3)
    zoomed = edited(layer, keypoints=layer.keypoints * np.float32(2.0))
    assert np.allclose(run(zoomed).series.values, base, rtol=0, atol=1e-9)  # an angle has no scale


@pytest.mark.parametrize("beta", [25.0, -12.5, 40.0])
def test_t_met_06b_the_image_rotated_by_the_roll_and_corrected_gives_the_same_angle_as_the_upright_one(beta):
    layer = seg_layer()
    rolled = edited(layer, keypoints=apply_roll(layer.keypoints, beta, (960.0, 540.0)).astype(np.float32))
    assert np.allclose(run(rolled, roll_deg=beta).series.values, run(layer).series.values, rtol=0, atol=1e-3)
    assert np.allclose(run(rolled).series.values - run(layer).series.values, beta, rtol=0, atol=1e-3)  # off by the roll


def test_t_met_06b_the_two_planes_are_two_metrics_with_the_same_angle():
    layer = seg_layer()
    lr, fb = run(layer, plane="lr", view_category="front"), run(layer, plane="fb", view_category="side")
    assert (lr.series.header.metric_name, fb.series.header.metric_name) == ("trunk_lean_lr", "trunk_lean_fb")
    assert METRIC_NAMES == {"lr": "trunk_lean_lr", "fb": "trunk_lean_fb"}
    assert np.array_equal(lr.series.values, fb.series.values)
    assert (lr.series.header.view_category, fb.series.header.view_category) == ("front", "side")


# --- T-MET-06c: the reason of every row -------------------------------------------------------------------------------
def scenario() -> tuple[PoseFiltered, list[int]]:
    """A segment of 30 rows with one situation per row (rows are numbered from the start of the segment).

    0 to 3: the left hip is missing with the reasons 1 to 4; 4: the right hip, 5; 5: a shoulder, 6; 6: the other, 3;
    7: all four joints (the first of the order hips then shoulders gives 2); 8: a shoulder (1) and a hip (6): the hip's;
    9: the left hip is a bridged value; 10: a shoulder is; 11: the middle of the shoulders on the middle of the hips
    (the angle is undefined: 4); 14 and 16: a joint missing, so 15 is a run of one row; 27: a hip missing outside the
    interval.
    """
    layer = seg_layer(np.linspace(-20.0, 25.0, G))
    k, r, i = cells(layer)

    def g(s: int) -> int:
        return SEG[0] + s

    for s, code in enumerate((1, 2, 3, 4)):
        drop(k, r, g(s), LH, code)
    drop(k, r, g(4), RH, 5)
    drop(k, r, g(5), LS, 6)
    drop(k, r, g(6), RS, 3)
    for joint, code in ((LH, 2), (RH, 4), (LS, 1), (RS, 5)):
        drop(k, r, g(7), joint, code)
    drop(k, r, g(8), LS, 1)
    drop(k, r, g(8), LH, 6)
    bridge(k, r, i, g(9), LH)
    bridge(k, r, i, g(10), RS)
    k[g(11), LS] = (400.0, 400.0)  # the shoulders on the hips: (450, 400) is the middle of both
    k[g(11), RS] = (500.0, 400.0)
    drop(k, r, g(14), LH, 1)
    drop(k, r, g(16), RS, 1)
    drop(k, r, g(27), LH, 2)
    expected = [1, 2, 3, 4, 5, 6, 3, 2, 6, 0, 0, 4, 0, 0, 1, 21, 1] + [0] * 8 + [16] * 5
    return edited(layer, keypoints=k, reason=r, interpolated=i), expected


def test_t_met_06c_every_row_has_the_reason_of_the_precedence_and_a_value_only_where_it_is_measured():
    layer, expected = scenario()
    result = run(layer, intervals=stable_of(layer), min_valid_s=0.05)
    s = result.series
    assert s.reason.tolist() == expected
    for row, code in enumerate(expected):
        if code == 0:
            assert s.values[row] == pytest.approx(expected_theta(layer.keypoints[SEG[0] + row]), abs=1e-9), row
        else:
            assert math.isnan(s.values[row]), row
    assert not {19, 20} & set(s.reason.tolist())  # an angle needs no scale and no reference
    assert s.t_sec.tolist() == layer.t_grid[SEG[0] : SEG[1]].tolist()


def test_t_met_06c_the_coverage_and_the_counts_are_those_of_the_reasons_counted_by_hand():
    layer, expected = scenario()
    h = run(layer, intervals=stable_of(layer), min_valid_s=0.05).series.header
    assert (h.coverage.total, h.coverage.eligible, h.coverage.quality, h.coverage.measured) == (30, 25, 13, 12)
    m = h.missing_by_reason
    assert (m.low_conf, m.non_finite, m.not_tracked, m.frame_invalid, m.outlier, m.no_frame) == (3, 2, 2, 2, 1, 2)
    assert (m.outside_interval, m.too_short, m.view_not_supported, m.interval_flagged) == (5, 1, 0, 0)
    assert (m.scale_unavailable, m.reference_missing) == (0, 0)
    step = layer.meta.timeline.step_s
    runs = [(9, 10), (12, 13), (17, 24)]
    assert [(i.t_start, i.t_end) for i in h.valid_intervals] == [
        (float(layer.t_grid[SEG[0] + a]), float(layer.t_grid[SEG[0] + b]) + step) for a, b in runs
    ]


def test_t_met_06c_a_flag_makes_the_rows_inside_18_and_an_unsupported_view_17_and_a_row_outside_stays_16():
    layer, _ = scenario()
    flagged = run(layer, intervals=stable_of(layer), flags={"orientation_change": True}).series
    assert flagged.reason.tolist() == [18] * 25 + [16] * 5  # 18 wins over a missing joint; 16 wins over 18
    wrong_view = run(layer, intervals=stable_of(layer), view_category="side", flags={"orientation_change": True})
    assert wrong_view.series.reason.tolist() == [17] * 25 + [16] * 5  # 17 wins over 18; 16 wins over 17
    other = run(layer, intervals=stable_of(layer), flags={"perspective_shift": True, "occlusion": True}).series
    assert (
        18 not in other.reason.tolist()
    )  # a depth change does not change an angle, an occlusion shows as pose reasons


def test_t_met_06c_without_intervals_the_whole_segment_is_looked_at():
    layer, expected = scenario()
    out = run(layer, min_valid_s=0.05).series.reason.tolist()
    assert 16 not in out and out[:25] == expected[:25]  # rows 25 to 29 are no longer outside


# --- T-MET-06d: the statistics ----------------------------------------------------------------------------------------
ASYMMETRIC = [-4.0, -1.0, 0.0, 2.0, 3.0, 5.0, 8.0, 12.0, -2.0, 6.0]
SYMMETRIC = [-10.0, -5.0, 5.0, 10.0, -8.0, 8.0, -3.0, 3.0, -9.0, 9.0]


def ten_layer(values: list[float]) -> PoseFiltered:
    """Ten rows in the segment (rows 3 to 12 of 20) with the angles ``values``, the others upright."""
    th = np.zeros(20)
    th[3:13] = values
    return exact_layer(lean_body(th), segment=(3, 13))


@pytest.mark.parametrize("values", [ASYMMETRIC, SYMMETRIC], ids=["asymmetric", "symmetric"])
def test_t_met_06d_the_signed_median_and_the_median_and_p95_of_the_magnitude_are_the_independent_ones(values):
    layer = ten_layer(values)
    result = run(layer)
    theta = [expected_theta(layer.keypoints[g]) for g in range(3, 13)]
    assert stat(result, "lean_median") == pytest.approx(statistics.median(theta), abs=1e-9)
    assert stat(result, "lean_abs_median") == pytest.approx(statistics.median(abs(x) for x in theta), abs=1e-9)
    assert stat(result, "lean_abs_p95") == pytest.approx(percentile([abs(x) for x in theta], 95), abs=1e-9)
    if values is SYMMETRIC:
        assert abs(stat(result, "lean_median")) < 1.0 < stat(result, "lean_abs_median")  # the sign and the size differ


def test_t_met_06d_the_summary_is_experimental_never_conclusive_has_no_event_and_uses_no_threshold():
    s = run(ten_layer(ASYMMETRIC)).summary
    assert s.evidence == "sufficient" and s.insufficient_reason is None and s.metric_name == "trunk_lean_lr"
    assert s.record_status == "experimental" and s.record_version is None and s.threshold_source is None
    assert s.conclusive is False and s.events == () and not any(x.uses_threshold for x in s.statistics)
    assert [x.name for x in s.statistics] == ["lean_median", "lean_abs_median", "lean_abs_p95", "bridged_rows"]
    assert [x.units for x in s.statistics] == ["deg", "deg", "deg", "count"]


def test_t_met_06d_a_row_leans_on_a_bridge_when_a_hip_or_a_shoulder_is_one_and_the_row_is_measured():
    layer = ten_layer(ASYMMETRIC)
    k, r, i = cells(layer)
    bridge(k, r, i, 4, LH)  # a measured row with a bridged hip
    bridge(k, r, i, 6, RS)  # a measured row with a bridged shoulder
    bridge(k, r, i, 12, RH)  # a bridged row that the interval leaves out
    stable = [(float(layer.t_grid[3]), float(layer.t_grid[12]))]
    out = run(edited(layer, reason=r, interpolated=i), intervals=stable)
    assert stat(out, "bridged_rows") == 2.0


def test_t_met_06d_one_measured_row_is_enough_for_a_number():
    layer = ten_layer(ASYMMETRIC)
    k, r, i = cells(layer)
    for g in range(3, 13):
        if g != 7:
            drop(k, r, g, LH, 1)
    out = run(edited(layer, keypoints=k, reason=r))
    only = expected_theta(layer.keypoints[7])
    assert out.series.header.coverage.measured == 1 and out.summary.evidence == "sufficient"
    assert stat(out, "lean_median") == pytest.approx(only) and stat(out, "lean_abs_p95") == pytest.approx(abs(only))


def test_t_met_06d_the_parameters_say_what_was_used():
    layer = ten_layer(ASYMMETRIC)
    p = run(layer, intervals=[(0.0, 5.0), (6.0, 7.0)], roll_deg=2.5, min_valid_s=0.1).summary.parameters
    assert p == {
        "plane": "lr", "roll_deg": 2.5, "supported_views": "front", "min_valid_s": 0.1, "percentile": 95,
        "n_intervals": 2,
    }  # fmt: skip
    plain = run(layer).summary.parameters
    assert plain["n_intervals"] is None and plain["min_valid_s"] is None and plain["roll_deg"] == 0.0
    fb = run(layer, plane="fb", view_category="side").summary.parameters
    assert (fb["plane"], fb["supported_views"]) == ("fb", "side")
    widened = run(layer, view_category="back", supported_views=("front", "back")).summary.parameters
    assert widened["supported_views"] == "front-back"


def assert_no_evidence(result: MetricResult, reason: str) -> None:
    s = result.summary
    assert s.evidence == "insufficient_evidence" and s.insufficient_reason == reason
    assert all(x.value is None for x in s.statistics) and len(s.statistics) == 4  # null, never 0
    assert s.events == () and s.conclusive is False


def test_t_met_06d_no_measured_row_gives_no_number_and_the_reason_that_holds_the_rows():
    layer = seg_layer()
    assert_no_evidence(run(layer, intervals=[]), "outside_interval")
    assert_no_evidence(run(layer, flags={"orientation_change": True}), "interval_flagged")
    assert_no_evidence(run(layer, view_category="side"), "view_not_supported")
    k, r, i = cells(layer)
    for s in range(N_SEG):
        drop(k, r, SEG[0] + s, LH if s % 3 else RH, 5 if s < 20 else 1)  # 20 rows with 5, 10 rows with 1
    assert_no_evidence(run(edited(layer, keypoints=k, reason=r)), "outlier")


def test_t_met_06d_a_segment_with_no_row_is_no_frame_and_one_with_a_single_row_is_too_short():
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


# --- T-MET-06e: refusals ----------------------------------------------------------------------------------------------
BAD_ARGUMENTS = [
    ({"layer": "x"}, "layer"),
    ({"layer": None}, "layer"),
    ({"plane": "ud"}, "plane"),
    ({"plane": None}, "plane"),
    ({"plane": "LR"}, "plane"),
    ({"view_category": "fron"}, "view_category"),
    ({"view_category": None}, "view_category"),
    ({"supported_views": ()}, "supported_views"),
    ({"supported_views": ("sideways",)}, "supported_views"),
    ({"supported_views": "front"}, "supported_views"),
    ({"supported_views": 5}, "supported_views"),
    ({"intervals": [(2.0, 1.0)]}, r"intervals\[0\]"),
    ({"intervals": "all"}, "intervals"),
    ({"flags": {"orientation_changes": True}}, "flags"),
    ({"flags": None}, "flags"),
    ({"roll_deg": 60.0}, "roll_deg"),
    ({"roll_deg": float("nan")}, "roll_deg"),
    ({"roll_deg": "5"}, "roll_deg"),
    ({"min_valid_s": 0.0}, "min_valid_s"),
    ({"min_valid_s": float("nan")}, "min_valid_s"),
    ({"camera_id": "cam1"}, "camera_id"),
]


@pytest.mark.parametrize(("change", "message"), BAD_ARGUMENTS, ids=[str(b[0]) for b in BAD_ARGUMENTS])
def test_t_met_06e_a_bad_argument_is_refused_naming_it(change: dict[str, Any], message: str):
    args: dict[str, Any] = {
        "layer": seg_layer(), "plane": "lr", "view_category": "front", "flags": {}, "camera_id": "camA",
    }  # fmt: skip
    args.update(change)
    layer = args.pop("layer")
    with pytest.raises(MetricError, match=message):
        trunk_lean(layer, **args)


@pytest.mark.parametrize("roll", [60.0, float("nan"), "5"])
def test_t_met_06e_the_roll_and_the_minimum_are_checked_even_when_no_row_is_measured(roll):
    with pytest.raises(MetricError, match="roll_deg"):
        run(seg_layer(), view_category="side", roll_deg=roll)  # every row is 17: nothing would use the roll
    with pytest.raises(MetricError, match="min_valid_s"):
        run(seg_layer(), intervals=[], min_valid_s=-1.0)


def test_t_met_06e_the_inputs_are_not_changed_and_the_result_is_read_only():
    layer = seg_layer()
    before = (layer.keypoints.copy(), layer.reason.copy())
    out = run(layer)
    assert np.array_equal(layer.keypoints, before[0]) and np.array_equal(layer.reason, before[1])
    for array in (out.series.values, out.series.reason, out.series.t_sec):
        assert not array.flags.writeable


# --- T-MET-07: a view that does not fit gives no number --------------------------------------------------------------
@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("plane", ["lr", "fb"])
def test_t_met_07_only_the_view_of_the_plane_gives_numbers_the_others_give_insufficient_evidence(plane, view):
    out = run(seg_layer(), plane=plane, view_category=view)
    fits = view == SUPPORTED_VIEWS[plane][0]
    if fits:
        assert out.summary.evidence == "sufficient" and out.series.header.coverage.measured == N_SEG
        assert stat(out, "lean_abs_p95") is not None
    else:
        assert_no_evidence(out, "view_not_supported")
        assert out.series.reason.tolist() == [17] * N_SEG and np.isnan(out.series.values).all()
        assert out.series.header.view_category == view and len(out.series.t_sec) == N_SEG  # the series is still there
        h = out.series.header
        assert (h.coverage.total, h.coverage.eligible, h.coverage.quality, h.coverage.measured) == (N_SEG, 0, 0, 0)
        assert h.missing_by_reason.view_not_supported == N_SEG and h.valid_intervals == ()


def test_t_met_07_the_default_views_are_front_for_left_right_and_side_for_forward_back():
    assert SUPPORTED_VIEWS == {"lr": ("front",), "fb": ("side",)}


def test_t_met_07_a_turn_of_the_performer_inside_the_segment_is_18_on_the_fitting_view():
    out = run(seg_layer(), flags={"orientation_change": True})
    assert out.series.reason.tolist() == [18] * N_SEG
    assert_no_evidence(out, "interval_flagged")
    h = out.series.header
    assert (h.coverage.eligible, h.missing_by_reason.interval_flagged) == (0, N_SEG)


def test_t_met_07_a_signed_record_can_widen_or_narrow_the_views_and_the_numbers_follow():
    layer = seg_layer()
    assert_no_evidence(run(layer, view_category="back"), "view_not_supported")
    widened = run(layer, view_category="back", supported_views=("front", "back"))
    assert widened.summary.evidence == "sufficient" and widened.series.header.coverage.measured == N_SEG
    assert_no_evidence(run(layer, view_category="side", supported_views=("front", "back")), "view_not_supported")
    assert_no_evidence(run(layer, view_category="front", supported_views=("back",)), "view_not_supported")
