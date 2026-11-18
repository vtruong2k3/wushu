"""T-MET-03e to 03h: hip height, variant A (P5.03): the scale of the reference, the reason of every row, the values,
the range and the events, and what is refused.

Every expected number is re-derived here with plain loops and ``statistics.median`` from the arrays of the layer the
metric reads (never from the metric's own helpers), so a test cannot pass by repeating the code under test.
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
    OTHER_RECORDING_ID,
    OTHER_SOURCES,
    RH,
    TORSO_PX,
    body,
    bridge,
    cells,
    drop,
    edited,
    exact_layer,
)
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.hip_height import (
    HipHeightResult,
    ReferenceScale,
    hip_height_a,
    reference_scale,
)
from taiji_ai.quality.layers_io import PoseFiltered

G = 40
SEG = (5, 35)  # rows of the segment: 30 rows, five margin rows on each side
N_SEG = SEG[1] - SEG[0]
EVERYTHING = [(0.0, 1000.0)]  # the coach confirmed the whole segment


# --- independent re-derivation --------------------------------------------------------------------------------------
def seg_rows(layer: PoseFiltered) -> list[int]:
    return [g for g in range(len(layer.t_grid)) if layer.grid_in_segment[g]]


def trunk_px(kp_row: np.ndarray) -> float:
    """``|mid-shoulder - mid-hip|`` of one row, NaN if a joint is missing; by hand from float32 positions."""
    p = kp_row.astype(np.float64)
    sx, sy = (p[5, 0] + p[6, 0]) / 2.0, (p[5, 1] + p[6, 1]) / 2.0
    hx, hy = (p[11, 0] + p[12, 0]) / 2.0, (p[11, 1] + p[12, 1]) / 2.0
    return math.hypot(sx - hx, sy - hy)


def scale_of(layer: PoseFiltered) -> float:
    """The median of the finite trunk lengths over the segment rows of the layer."""
    lengths = [trunk_px(layer.keypoints[g]) for g in seg_rows(layer)]
    lengths = [x for x in lengths if math.isfinite(x) and x > 0.0]
    return statistics.median(lengths) if lengths else float("nan")


def hip_y(kp_row: np.ndarray, roll_deg: float = 0.0) -> float:
    """The second coordinate of the mid-hip after the roll (``y' = -x sin r + y cos r``, origin 0)."""
    p = kp_row.astype(np.float64)
    x, y = (p[11, 0] + p[12, 0]) / 2.0, (p[11, 1] + p[12, 1]) / 2.0
    r = math.radians(roll_deg)
    return -x * math.sin(r) + y * math.cos(r)


def percentile(values: list[float], q: float) -> float:
    """Linear interpolation between order statistics (``numpy``'s default), written out."""
    v = sorted(values)
    k = (len(v) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def stat(result: HipHeightResult, name: str) -> float | None:
    (s,) = [s for s in result.summary.statistics if s.name == name]
    return s.value


# --- layers -----------------------------------------------------------------------------------------------------------
def swinging(n: int = G) -> np.ndarray:
    """A hip that moves by +-20 px, in every row of ``n``."""
    return 400.0 + 20.0 * np.sin(np.arange(n) * 0.7)


def seg_layer(hip: np.ndarray | float | None = None, **kwargs: Any) -> PoseFiltered:
    return exact_layer(body(G, swinging() if hip is None else hip), segment=SEG, **kwargs)


def ref_layer(trunk: float = TORSO_PX, n: int = 60, **kwargs: Any) -> PoseFiltered:
    return exact_layer(body(n, 420.0, trunk=trunk), **kwargs)  # the whole layer is the reference segment


def run(layer: PoseFiltered, reference: PoseFiltered | None = ..., **kwargs: Any) -> HipHeightResult:  # type: ignore[assignment]
    args: dict[str, Any] = {
        "reference": ref_layer() if reference is ... else reference,
        "stable_intervals": EVERYTHING,
        "flags": {},
        "camera_id": "camA",
        "view_category": "front",
    }
    args.update(kwargs)
    return hip_height_a(layer, **args)


# --- T-MET-03e: the scale of the reference ------------------------------------------------------------------------
def test_t_met_03e_the_scale_is_the_median_trunk_of_the_rows_of_the_reference_segment_only():
    kp = body(50, 420.0, trunk=150.0)
    kp[:10] = body(10, 420.0, trunk=100.0)  # the margins of the reference have another trunk ...
    kp[40:] = body(10, 420.0, trunk=300.0)
    layer = exact_layer(kp, segment=(10, 40))
    out = reference_scale(layer)
    assert isinstance(out, ReferenceScale)
    assert out.scale_px == pytest.approx(150.0, rel=1e-12) and out.scale_px == pytest.approx(scale_of(layer))
    assert out.n_rows == 30 and out.duration_s == pytest.approx(30 / FPS)  # ... and they are not in it


def test_t_met_03e_it_is_a_median_not_a_mean_and_a_missing_row_is_left_out():
    kp = body(40, 420.0, trunk=150.0)
    kp[:10] = body(10, 420.0, trunk=300.0)  # 10 rows at 300, 30 at 150: mean 187.5, median 150
    layer = exact_layer(kp)
    assert reference_scale(layer).scale_px == pytest.approx(150.0)
    k, r, i = cells(layer)
    for row in range(10, 16):
        drop(k, r, row, LS, 1)  # six rows lose a shoulder: they have no trunk
    out = reference_scale(edited(layer, keypoints=k, reason=r))
    assert out.n_rows == 34 and out.scale_px == pytest.approx(150.0)


def test_t_met_03e_a_bridged_cell_counts_because_it_has_a_value():
    layer = ref_layer()
    k, r, i = cells(layer)
    bridge(k, r, i, 3, LH)
    bridge(k, r, i, 4, LS)
    assert reference_scale(edited(layer, reason=r, interpolated=i)).n_rows == 60


def test_t_met_03e_no_valid_row_gives_nan_and_zero_and_a_short_reference_is_not_used_but_keeps_its_rows():
    layer = ref_layer(n=30)
    k, r, i = cells(layer)
    for row in range(30):
        drop(k, r, row, LS, 2)
    out = reference_scale(edited(layer, keypoints=k, reason=r))
    assert math.isnan(out.scale_px) and out.n_rows == 0 and out.duration_s == 0.0
    ok = reference_scale(ref_layer(n=30), min_reference_s=1.0)  # 30 rows at 30 fps last one second
    assert ok.scale_px == pytest.approx(150.0) and ok.n_rows == 30
    short = reference_scale(ref_layer(n=30), min_reference_s=1.001)
    assert math.isnan(short.scale_px) and short.n_rows == 30 and short.duration_s == pytest.approx(1.0)


def test_t_met_03e_a_reference_short_by_less_than_a_nanosecond_is_not_short():
    layer = ref_layer(n=30)  # 30 rows at 30 fps: one second up to a rounding
    assert reference_scale(layer, min_reference_s=1.0 + 1e-12).scale_px == pytest.approx(150.0)
    assert math.isnan(reference_scale(layer, min_reference_s=1.0 + 1e-8).scale_px)


def test_t_met_03e_a_reference_of_one_row_has_no_duration():
    only = np.zeros(10, dtype=bool)
    only[4] = True
    layer = edited(exact_layer(body(10, 420.0)), grid_in_segment=only)
    out = reference_scale(layer)
    assert out.scale_px == pytest.approx(150.0) and out.n_rows == 1 and out.duration_s == 0.0
    assert math.isnan(reference_scale(layer, min_reference_s=0.01).scale_px)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf"), "1", True])
def test_t_met_03e_a_bad_minimum_or_reference_is_refused_naming_it(bad):
    with pytest.raises(MetricError, match="min_reference_s"):
        reference_scale(ref_layer(), min_reference_s=bad)
    with pytest.raises(MetricError, match="reference"):
        reference_scale("not a layer")  # type: ignore[arg-type]


# --- T-MET-03f: the reason of a row and its value -----------------------------------------------------------------
def scenario() -> tuple[PoseFiltered, list[int]]:
    """A segment of 30 rows with one situation per row (rows are numbered from the start of the segment).

    0 to 5: the left hip is missing with the reasons 1 to 6; 6: the right hip, 3; 7: both hips (4 on the left, 2 on the
    right: the first of the list wins); 8: the left hip is a bridged value; 9: a shoulder is missing (a hip height does
    not need it); 12 and 14: a hip missing, so 13 is a run of one row; 25 to 29: outside the stable interval.
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
    drop(k, r, g(12), LH, 1)
    drop(k, r, g(14), RH, 1)
    expected = [1, 2, 3, 4, 5, 6, 3, 4, 0, 0, 0, 0, 1, 21, 1] + [0] * 10 + [16] * 5
    return edited(layer, keypoints=k, reason=r, interpolated=i), expected


def stable_of(layer: PoseFiltered, rows: int = 25) -> list[tuple[float, float]]:
    return [(float(layer.t_grid[SEG[0]]), float(layer.t_grid[SEG[0] + rows]))]


def test_t_met_03f_every_row_has_the_reason_of_the_precedence_and_a_value_only_where_it_is_measured():
    layer, expected = scenario()
    ref = ref_layer()
    result = run(layer, ref, stable_intervals=stable_of(layer), min_valid_s=0.1)
    s = result.series
    assert s.reason.tolist() == expected
    scale = scale_of(ref)
    for row, code in enumerate(expected):
        if code == 0:
            assert s.values[row] == pytest.approx(hip_y(layer.keypoints[SEG[0] + row]) / scale, rel=1e-12), row
        else:
            assert math.isnan(s.values[row]), row
    assert s.t_sec.tolist() == layer.t_grid[SEG[0] : SEG[1]].tolist()


def test_t_met_03f_the_coverage_and_the_counts_are_those_of_the_reasons_counted_by_hand():
    layer, expected = scenario()
    h = run(layer, stable_intervals=stable_of(layer), min_valid_s=0.1).series.header
    count = {code: expected.count(code) for code in set(expected)}
    quality_codes = (1, 2, 3, 4, 5, 6)
    assert h.coverage.total == 30 and h.coverage.eligible == 30 - count[16]
    assert h.coverage.quality == h.coverage.eligible - sum(count.get(c, 0) for c in quality_codes)
    assert h.coverage.measured == h.coverage.quality - count[21] == count[0] == 14
    m = h.missing_by_reason
    assert (m.low_conf, m.non_finite, m.not_tracked, m.frame_invalid, m.outlier, m.no_frame) == (3, 1, 2, 2, 1, 1)
    assert (m.outside_interval, m.too_short, m.interval_flagged, m.scale_unavailable, m.reference_missing) == (
        5,
        1,
        0,
        0,
        0,
    )
    step = layer.meta.timeline.step_s
    first_run = (float(layer.t_grid[SEG[0] + 8]), float(layer.t_grid[SEG[0] + 11]) + step)  # rows 8 to 11
    second_run = (float(layer.t_grid[SEG[0] + 15]), float(layer.t_grid[SEG[0] + 24]) + step)  # rows 15 to 24
    assert [(i.t_start, i.t_end) for i in h.valid_intervals] == [first_run, second_run]


def test_t_met_03f_a_flag_makes_the_rows_inside_18_and_a_row_outside_stays_16():
    layer, _ = scenario()
    r = run(layer, stable_intervals=stable_of(layer), flags={"perspective_shift": True}).series
    assert r.reason.tolist() == [18] * 25 + [16] * 5  # 18 wins over a missing hip; 16 wins over 18


def test_t_met_03f_without_a_reference_a_good_row_is_20_and_a_row_without_a_hip_keeps_its_pose_reason():
    layer, expected = scenario()
    r = run(layer, None, stable_intervals=stable_of(layer)).series
    assert r.reason.tolist() == [c if c not in (0, 21) else 20 for c in expected] and not np.isfinite(r.values).any()


def test_t_met_03f_a_reference_without_a_usable_trunk_makes_a_good_row_19():
    layer, expected = scenario()
    ref = ref_layer(n=30)
    k, r, i = cells(ref)
    for row in range(30):
        drop(k, r, row, LS, 1)
    bad = edited(ref, keypoints=k, reason=r)
    out = run(layer, bad, stable_intervals=stable_of(layer)).series
    assert out.reason.tolist() == [c if c not in (0, 21) else 19 for c in expected]
    too_short = run(layer, ref_layer(n=30), stable_intervals=stable_of(layer), min_reference_s=1.5).series
    assert too_short.reason.tolist() == [
        c if c not in (0, 21) else 19 for c in expected
    ]  # 1 s of reference, 1.5 s asked


def test_t_met_03f_a_run_is_judged_after_the_other_reasons_and_only_measured_rows_can_become_21():
    layer = seg_layer()
    k, r, i = cells(layer)
    for s in (3, 7):
        drop(k, r, SEG[0] + s, LH, 1)  # runs of 3, 3 and 22 rows
    layer = edited(layer, keypoints=k, reason=r)
    kept = run(layer, min_valid_s=3 / FPS).series.reason.tolist()
    assert kept == [0, 0, 0, 1, 0, 0, 0, 1] + [0] * 22  # a run of exactly the minimum stays
    cut = run(layer, min_valid_s=4 / FPS).series.reason.tolist()
    assert cut == [21, 21, 21, 1, 21, 21, 21, 1] + [0] * 22


def test_t_met_03f_the_values_are_the_image_height_of_the_hip_over_the_scale_of_the_reference():
    layer = seg_layer()
    ref = ref_layer(trunk=120.0)  # another scale than the trunk of the segment: Lambda_take is the reference's
    out = run(layer, ref).series
    scale = scale_of(ref)
    assert scale == pytest.approx(120.0)
    for row in range(N_SEG):
        assert out.values[row] == pytest.approx(hip_y(layer.keypoints[SEG[0] + row]) / 120.0, rel=1e-12)
    assert out.header.units == "body_lengths" and out.header.metric_name == "hip_height_a"
    assert out.header.metric_version == "1" and out.header.camera_id == "camA" and out.header.view_category == "front"


def test_t_met_03f_the_roll_is_taken_out_of_the_vertical_coordinate_with_the_sign_of_the_angle():
    layer = seg_layer()
    out = run(layer, roll_deg=20.0).series
    scale = scale_of(ref_layer())
    for row in range(N_SEG):
        assert out.values[row] == pytest.approx(hip_y(layer.keypoints[SEG[0] + row], 20.0) / scale, rel=1e-12)
    assert not np.allclose(out.values, run(layer).series.values)  # and it is not the same as no roll


def test_t_met_03f_the_margins_of_the_segment_are_never_in_the_series():
    layer = seg_layer()
    assert len(run(layer).series.t_sec) == N_SEG and run(layer).series.header.coverage.total == N_SEG


# --- T-MET-03g: the summary -----------------------------------------------------------------------------------------
TIES = [0, 10, 20, 20, 10, 0, -10, -20, -20, -10]  # px below 400: equal maxima at 2 and 3, equal minima at 7 and 8


def ties_layer() -> PoseFiltered:
    """Ten rows in the segment (rows 3 to 12 of 20) that go up and down with equal extremes; row 12 is bridged."""
    hip = np.full(20, 400.0)
    hip[3:13] = 400.0 + np.array(TIES)
    layer = exact_layer(body(20, hip), segment=(3, 13))
    k, r, i = cells(layer)
    bridge(k, r, i, 4, LH)  # a measured row that leans on a bridge
    bridge(k, r, i, 12, RH)  # a bridged row that the stable interval leaves out
    return edited(layer, reason=r, interpolated=i)


def test_t_met_03g_the_range_is_p95_minus_p5_of_the_measured_rows_and_the_events_are_the_first_extremes():
    layer = ties_layer()
    stable = [(float(layer.t_grid[3]), float(layer.t_grid[12]))]  # rows 3 to 11: the row 12 is left out
    result = run(layer, stable_intervals=stable)
    scale = scale_of(ref_layer())
    h = [(400.0 + d) / scale for d in TIES[:9]]
    assert stat(result, "hip_height_range") == pytest.approx(percentile(h, 95) - percentile(h, 5), rel=1e-12)
    assert stat(result, "bridged_rows") == 1.0  # row 4; the bridged row 12 is not measured
    ev = {e.kind: e for e in result.summary.events}
    assert set(ev) == {"max", "min"} and len(result.summary.events) == 2
    assert ev["max"].t_start == ev["max"].t_end == float(layer.t_grid[3 + 2])  # the first of the two equal maxima
    assert ev["max"].value == pytest.approx((400.0 + 20.0) / scale)  # y down: the largest value is the lowest hip
    assert ev["min"].t_start == ev["min"].t_end == float(layer.t_grid[3 + 7])
    assert ev["min"].value == pytest.approx((400.0 - 20.0) / scale)
    assert not any(e.uses_threshold for e in result.summary.events)


def test_t_met_03g_the_summary_is_experimental_never_conclusive_and_uses_no_threshold():
    s = run(ties_layer()).summary
    assert s.evidence == "sufficient" and s.insufficient_reason is None
    assert s.record_status == "experimental" and s.record_version is None and s.threshold_source is None
    assert s.conclusive is False
    assert not any(x.uses_threshold for x in s.statistics)
    assert [x.name for x in s.statistics] == ["hip_height_range", "bridged_rows"]
    assert {x.units for x in s.statistics} == {"body_lengths", "count"}


def test_t_met_03g_the_summary_repeats_the_header_of_the_series_and_the_provenance_of_the_layer():
    result = run(ties_layer())
    s, h = result.summary, result.series.header
    assert (s.metric_name, s.metric_version, s.units, s.recording_id, s.camera_id, s.view_category) == (
        h.metric_name, h.metric_version, h.units, h.recording_id, h.camera_id, h.view_category,
    )  # fmt: skip
    assert (
        s.coverage == h.coverage
        and s.missing_by_reason == h.missing_by_reason
        and s.valid_intervals == h.valid_intervals
    )
    assert s.data_sources == ties_layer().meta.data_sources and s.step_s == h.step_s == pytest.approx(1 / FPS)


def test_t_met_03g_the_parameters_say_what_was_used():
    layer = ties_layer()
    ref = ref_layer()
    p = run(
        layer, ref, stable_intervals=[(0.0, 5.0), (6.0, 7.0)], roll_deg=2.5, min_reference_s=0.5, min_valid_s=0.1
    ).summary.parameters
    expected: dict[str, Any] = {
        "variant": "a", "roll_deg": 2.5, "min_reference_s": 0.5, "min_valid_s": 0.1, "percentile_low": 5,
        "percentile_high": 95, "scale_px": pytest.approx(150.0), "reference_rows": 60,
        "reference_s": pytest.approx(60 / FPS), "n_stable_intervals": 2, "filter_cutoff_hz": 6.0,
    }  # fmt: skip
    assert p == expected
    q = run(layer, ref).summary.parameters
    assert q["min_reference_s"] is None and q["min_valid_s"] is None and q["roll_deg"] == 0.0


def test_t_met_03g_two_measured_rows_are_enough_for_a_range_and_it_is_the_spread_of_the_two():
    layer = exact_layer(body(20, 400.0), segment=(3, 13))
    k, r, i = cells(layer)
    k[3:13, LH : RH + 1, :] = np.nan  # joints 11 and 12, both coordinates: a cell has a position or none
    r[3:13, LH : RH + 1] = 1  # all ten rows lose their hips ...
    k[5:7, :, :] = body(2, np.array([400.0, 430.0]))  # ... but rows 5 and 6 get them back (400 and 430)
    r[5:7, :] = 0
    out = run(edited(layer, keypoints=k, reason=r))
    scale = scale_of(ref_layer())
    assert out.summary.evidence == "sufficient"
    assert stat(out, "hip_height_range") == pytest.approx(0.9 * 30.0 / scale, rel=1e-12)  # P95 - P5 of two values
    ev = {e.kind: e for e in out.summary.events}
    assert ev["max"].t_start == float(layer.t_grid[6]) and ev["min"].t_start == float(layer.t_grid[5])


def assert_no_evidence(result: HipHeightResult, reason: str) -> None:
    s = result.summary
    assert s.evidence == "insufficient_evidence" and s.insufficient_reason == reason
    assert all(x.value is None for x in s.statistics) and len(s.statistics) == 2  # null, never 0
    assert s.events == () and s.conclusive is False


def test_t_met_03g_one_measured_row_is_too_short_for_a_range_and_gives_no_number():
    layer = seg_layer()
    k, r, i = cells(layer)
    for s in range(N_SEG):
        if s != 4:
            drop(k, r, SEG[0] + s, LH, 1)
    out = run(edited(layer, keypoints=k, reason=r))
    assert out.series.header.coverage.measured == 1
    assert_no_evidence(out, "too_short")


def test_t_met_03g_no_stable_interval_no_reference_and_a_flag_each_give_the_reason_that_holds_all_the_rows():
    layer = seg_layer()
    assert_no_evidence(run(layer, stable_intervals=[]), "outside_interval")
    assert_no_evidence(run(layer, None), "reference_missing")
    assert_no_evidence(run(layer, flags={"perspective_shift": True}), "interval_flagged")
    bad = ref_layer(n=30)
    k, r, i = cells(bad)
    k[:, LS] = np.nan
    r[:, LS] = 1
    assert_no_evidence(run(layer, edited(bad, keypoints=k, reason=r)), "scale_unavailable")


def test_t_met_03g_the_most_frequent_reason_is_given_when_the_pose_is_the_problem():
    layer = seg_layer()
    k, r, i = cells(layer)
    for s in range(N_SEG):
        drop(k, r, SEG[0] + s, LH if s % 3 else RH, 5 if s < 20 else 1)  # 20 rows with 5, 10 rows with 1
    assert_no_evidence(run(edited(layer, keypoints=k, reason=r)), "outlier")


def test_t_met_03g_a_segment_with_no_row_is_an_empty_series_and_the_reason_no_frame_not_an_error():
    layer = edited(seg_layer(), grid_in_segment=np.zeros(G, dtype=bool))
    out = run(layer)
    assert len(out.series.t_sec) == 0 and out.series.header.coverage.total == 0 and out.series.header.step_s is None
    assert_no_evidence(out, "no_frame")


def test_t_met_03g_a_segment_of_one_row_has_no_duration_so_the_row_is_21_and_nothing_is_measured():
    only = np.zeros(G, dtype=bool)
    only[10] = True
    out = run(edited(seg_layer(), grid_in_segment=only))
    assert out.series.reason.tolist() == [21] and out.series.header.step_s is None
    assert_no_evidence(out, "too_short")


# --- T-MET-03h: invariances and refusals ----------------------------------------------------------------------------
def test_t_met_03h_moving_the_image_down_moves_the_values_by_the_shift_over_the_scale_and_not_the_range():
    layer, ref = seg_layer(), ref_layer()

    def shifted(lay: PoseFiltered, dy: float) -> PoseFiltered:
        k = lay.keypoints.copy()
        k[..., 1] += np.float32(dy)
        return edited(lay, keypoints=k)

    a, b = run(layer, ref), run(shifted(layer, 100.0), shifted(ref, 100.0))
    assert np.allclose(b.series.values - a.series.values, 100.0 / 150.0, rtol=0, atol=1e-6)  # float32 positions
    assert stat(b, "hip_height_range") == pytest.approx(stat(a, "hip_height_range"), abs=1e-6)


def test_t_met_03h_zooming_the_image_of_both_layers_changes_nothing():
    layer, ref = seg_layer(), ref_layer()

    def zoomed(lay: PoseFiltered) -> PoseFiltered:
        return edited(lay, keypoints=lay.keypoints * np.float32(2.0))

    a, b = run(layer, ref), run(zoomed(layer), zoomed(ref))
    assert np.allclose(a.series.values, b.series.values, rtol=1e-6, atol=0)
    assert stat(b, "hip_height_range") == pytest.approx(stat(a, "hip_height_range"), rel=1e-6)
    assert b.summary.parameters["scale_px"] == pytest.approx(2.0 * a.summary.parameters["scale_px"])


def test_t_met_03h_the_same_layer_may_be_its_own_reference():
    layer = seg_layer()
    out = run(layer, layer)
    assert out.summary.evidence == "sufficient" and out.summary.parameters["scale_px"] == pytest.approx(150.0)


def test_t_met_03h_a_reference_of_another_recording_or_other_sources_is_refused_not_used():
    layer = seg_layer()
    with pytest.raises(MetricError, match="recording_id"):
        run(layer, ref_layer(recording_id=OTHER_RECORDING_ID))
    with pytest.raises(MetricError, match="data_sources"):
        run(layer, ref_layer(data_sources=OTHER_SOURCES))


BAD_ARGUMENTS = [
    ({"layer": "x"}, "layer"),
    ({"layer": None}, "layer"),
    ({"reference": "x"}, "reference"),
    ({"stable_intervals": [(2.0, 1.0)]}, r"stable_intervals\[0\]"),
    ({"stable_intervals": None}, "stable_intervals"),
    ({"flags": {"perspective_shifts": True}}, "flags"),
    ({"flags": None}, "flags"),
    ({"roll_deg": 60.0}, "roll_deg"),
    ({"roll_deg": float("nan")}, "roll_deg"),
    ({"roll_deg": "5"}, "roll_deg"),
    ({"min_valid_s": 0.0}, "min_valid_s"),
    ({"min_valid_s": float("nan")}, "min_valid_s"),
    ({"min_reference_s": -1.0}, "min_reference_s"),
    ({"camera_id": "cam1"}, "camera_id"),
    ({"view_category": "Front!"}, "view_category"),
]


@pytest.mark.parametrize(("change", "message"), BAD_ARGUMENTS, ids=[str(b[0]) for b in BAD_ARGUMENTS])
def test_t_met_03h_a_bad_argument_is_refused_naming_it(change: dict[str, Any], message: str):
    args: dict[str, Any] = {
        "layer": seg_layer(), "reference": ref_layer(), "stable_intervals": EVERYTHING, "flags": {},
        "camera_id": "camA", "view_category": "front",
    }  # fmt: skip
    args.update(change)
    layer = args.pop("layer")
    with pytest.raises(MetricError, match=message):
        hip_height_a(layer, **args)


@pytest.mark.parametrize("roll", [60.0, float("nan"), "5"])
def test_t_met_03h_the_roll_and_the_minimums_are_checked_even_when_no_row_is_measured(roll):
    with pytest.raises(MetricError, match="roll_deg"):
        run(seg_layer(), stable_intervals=[], roll_deg=roll)  # every row is outside: nothing would use the roll
    with pytest.raises(MetricError, match="min_valid_s"):
        run(seg_layer(), stable_intervals=[], min_valid_s=-1.0)
    with pytest.raises(MetricError, match="min_reference_s"):
        run(seg_layer(), None, min_reference_s=0.0)  # no reference: nothing would use its minimum


def test_t_met_03h_the_inputs_are_not_changed_and_the_result_is_read_only():
    layer, ref = seg_layer(), ref_layer()
    before = (layer.keypoints.copy(), layer.reason.copy(), ref.keypoints.copy())
    out = run(layer, ref)
    assert np.array_equal(layer.keypoints, before[0]) and np.array_equal(layer.reason, before[1])
    assert np.array_equal(ref.keypoints, before[2])
    for array in (out.series.values, out.series.reason, out.series.t_sec):
        assert not array.flags.writeable
