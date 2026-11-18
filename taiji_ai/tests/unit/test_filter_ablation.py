"""T-MET-12a to 12d: the machinery of the cut-off ablation (P5.08): the layers of one run at several cut-offs and their
invariants, the measures of a layer, the agreement of a cut-off with the reference, the pooled aggregation and the
tables.

Every expected number is derived here by hand or with plain loops from layers and pauses made in the tests. The layers
are what the chain hands to the metrics: ``run_quality_arrays`` then ``pose_filtered_from_result``. A cut-off
changes the values of the final layer and nothing else: the grid, the reasons, the interpolation flags and the
segment are the same.
"""

from __future__ import annotations

import csv
import io
import math
import statistics
from typing import Any

import numpy as np
import pytest

from helpers.metric_layers import RECORDING_ID, SOURCES, body, cells, drop, edited, exact_layer
from helpers.synth import make_sequence
from taiji_ai.bench import BenchError
from taiji_ai.bench.filter_ablation import (
    ALL_CUTOFFS,
    NO_FILTER_HZ,
    PAUSE_GRID,
    REFERENCE_HZ,
    AblationError,
    GroupMeasure,
    HipMeasure,
    RunMeasure,
    aggregate,
    agree,
    check_invariants,
    layers_at_cutoffs,
    measure_layer,
    render_tables,
)
from taiji_ai.metrics.tempo import Pause
from taiji_ai.quality.chain import QualityParams, run_quality_arrays
from taiji_ai.quality.filters import ButterworthParams
from taiji_ai.quality.layers_io import PoseFiltered, pose_filtered_from_result


# --- the layers of one run at several cut-offs --------------------------------------------------------------------
def noisy_run():
    seq = make_sequence("SYN-05", seed=1, noise_px=1.0)
    return seq, dict(
        recording_id=RECORDING_ID, frame_index=np.arange(len(seq.t_sec), dtype=np.int64), data_sources=SOURCES
    )


def test_t_met_12a_a_run_gives_a_layer_per_cutoff_with_the_same_grid_reasons_flags_and_segment():
    seq, kw = noisy_run()
    layers = layers_at_cutoffs(seq.kp, seq.score, seq.t_sec, **kw)
    assert list(layers) == [4.0, 6.0, 8.0, NO_FILTER_HZ] == list(ALL_CUTOFFS)
    ref = layers[REFERENCE_HZ]
    for hz, layer in layers.items():
        assert np.array_equal(layer.t_grid, ref.t_grid), hz
        assert np.array_equal(layer.reason, ref.reason) and np.array_equal(layer.interpolated, ref.interpolated), hz
        assert np.array_equal(layer.grid_in_segment, ref.grid_in_segment), hz
    keypoints = [layers[hz].keypoints for hz in ALL_CUTOFFS]
    for i in range(len(keypoints)):
        for j in range(i + 1, len(keypoints)):
            assert not np.array_equal(
                keypoints[i], keypoints[j]
            )  # the values differ: that is the point of the ablation


def test_t_met_12a_the_reference_layer_is_the_default_of_the_chain_and_no_filter_is_the_grid_layer_itself():
    seq, kw = noisy_run()
    layers = layers_at_cutoffs(seq.kp, seq.score, seq.t_sec, **kw)
    default = run_quality_arrays(seq.kp, seq.score, seq.t_sec)
    assert np.array_equal(layers[REFERENCE_HZ].keypoints, pose_filtered_from_result(default, **kw).keypoints)
    assert np.array_equal(layers[REFERENCE_HZ].keypoints, default.filtered.keypoints)
    unfiltered = run_quality_arrays(
        seq.kp, seq.score, seq.t_sec, params=QualityParams(filter=ButterworthParams(cutoff_hz=1000.0))
    )
    assert np.array_equal(layers[NO_FILTER_HZ].keypoints, default.grid.keypoints)  # no value touched: the grid layer
    assert np.array_equal(layers[NO_FILTER_HZ].keypoints, unfiltered.grid.keypoints)


def test_t_met_12a_only_the_cutoff_changes_the_other_parameters_of_the_base_are_kept():
    seq, kw = noisy_run()
    base = QualityParams(
        filter=ButterworthParams(cutoff_hz=3.0, order=2)
    )  # the cut-off of the base is replaced, order kept
    layers = layers_at_cutoffs(seq.kp, seq.score, seq.t_sec, base=base, cutoffs=(6.0, 8.0), **kw)
    for hz, layer in layers.items():
        expected = run_quality_arrays(
            seq.kp, seq.score, seq.t_sec, params=QualityParams(filter=ButterworthParams(cutoff_hz=hz, order=2))
        )
        assert np.array_equal(layer.keypoints, expected.filtered.keypoints), hz


@pytest.mark.parametrize(
    ("cutoffs", "message"),
    [
        ((), "cutoffs"),
        ((4.0, 8.0), "6"),  # the reference is missing
        ((6.0, 6.0, 8.0), "distinct"),
        ((6.0, 0.0), "cutoffs"),
        ((6.0, -4.0), "cutoffs"),
        ((6.0, float("nan")), "cutoffs"),
        ((6.0, float("inf")), "cutoffs"),
        ((6.0, True), "cutoffs"),
        ((6.0, "8"), "cutoffs"),
        (6.0, "cutoffs"),
    ],
)
def test_t_met_12a_a_bad_list_of_cutoffs_is_refused_naming_the_argument(cutoffs: Any, message: str):
    seq, kw = noisy_run()
    with pytest.raises(AblationError, match=message) as info:
        layers_at_cutoffs(seq.kp, seq.score, seq.t_sec, cutoffs=cutoffs, **kw)
    assert isinstance(info.value, BenchError)


def test_t_met_12a_a_run_whose_layer_breaks_an_invariant_is_refused_by_layers_at_cutoffs_itself(monkeypatch):
    seq, kw = noisy_run()
    original = pose_filtered_from_result
    calls = []

    def broken(result, **kwargs):
        layer = original(result, **kwargs)
        calls.append(layer)
        if len(calls) == 3:  # the third cut-off of the list, 8 Hz: one reason of one cell is changed
            k, r, _i = cells(layer)
            drop(k, r, 20, 9, 2)
            return edited(layer, keypoints=k, reason=r)
        return layer

    monkeypatch.setattr("taiji_ai.bench.filter_ablation.pose_filtered_from_result", broken)
    with pytest.raises(AblationError, match="reason") as info:
        layers_at_cutoffs(seq.kp, seq.score, seq.t_sec, **kw)
    assert "8 Hz" in str(info.value) and "6 Hz" in str(info.value)


def make_layers(n: int = 40) -> dict[float, PoseFiltered]:
    layer = exact_layer(body(n, 400.0), segment=(5, n - 5))
    return {hz: layer for hz in ALL_CUTOFFS}


def test_t_met_12a_an_invariant_that_is_broken_is_an_error_naming_the_cutoff_and_the_array():
    layers = make_layers()
    check_invariants(layers)  # identical layers pass
    ref = layers[REFERENCE_HZ]
    k, r, i = cells(ref)
    drop(k, r, 10, 9, 2)
    i2 = i.copy()
    i2[12, 9] = True
    segment = np.asarray(ref.grid_in_segment).copy()
    segment[6] = False
    t = np.asarray(ref.t_grid).copy()
    t[3] += 0.001
    cases = {
        "reason": edited(ref, keypoints=k, reason=r),
        "interpolated": edited(ref, interpolated=i2),
        "grid_in_segment": edited(ref, grid_in_segment=segment),
        "t_grid": edited(ref, t_grid=t),
    }
    for name, broken in cases.items():
        with pytest.raises(AblationError, match=name) as info:
            check_invariants({**layers, 8.0: broken})
        assert "8" in str(info.value) and "6" in str(info.value)  # the cut-off and the reference are named
    with pytest.raises(AblationError, match="6"):
        check_invariants({4.0: ref, 8.0: ref})  # no reference to compare with


# --- the measures of a layer ----------------------------------------------------------------------------------------
G = 60
SEG = (5, 55)  # 50 rows of the segment
KNOT_ROWS = [0, 20, 32, 40, 50, 59]
KNOT_X = [0.0, 100.0, 100.0, 140.0, 140.0, 185.0]  # 5 px per row = 1.0 trunk lengths per second at 150 px, or still


def hands_layer() -> PoseFiltered:
    """The hands move, stop, move, stop and move again: V is 1.0, 0.5 at a corner row and 0 in the stops."""
    base = exact_layer(body(G, 400.0, trunk=150.0), segment=SEG)
    kp = base.keypoints.astype(np.float64)
    x = np.interp(np.arange(G), KNOT_ROWS, KNOT_X)
    for joint in (9, 10):
        kp[:, joint, 0] += x
    return edited(base, keypoints=kp)


FEET = (15, 16, 24, 25)


def hips_layer() -> tuple[PoseFiltered, np.ndarray]:
    """The hips go up and down by 30 px while the feet stay: variant B measures the movement of the hips."""
    n = 60
    t = np.arange(n) / 30.0
    hip_y = 400.0 + 30.0 * np.sin(2.0 * np.pi * t / 1.0)
    kp = body(n, hip_y).astype(np.float64)
    kp[:, FEET, :] = kp[0, FEET, :]  # the feet do not move
    return exact_layer(kp.astype(np.float32), segment=(5, 55)), hip_y


def percentile(values: list[float], q: float) -> float:
    """Linear interpolation, written out (the P95 and P5 of the hip range)."""
    v = sorted(values)
    pos = (len(v) - 1) * q / 100.0
    low = math.floor(pos)
    high = min(low + 1, len(v) - 1)
    return v[low] + (v[high] - v[low]) * (pos - low)


def test_t_met_12b_the_speed_quantiles_and_the_pauses_of_a_group_are_what_the_layer_was_built_to_have():
    layer = hands_layer()
    m = measure_layer(layer, grid=((0.25, 0.3), (0.25, 0.4), (1.5, 0.3)))
    hands = m.groups["hands"]
    assert hands.n_rows == 50 and hands.n_measured == 50 and hands.measured.all()
    assert hands.v_p50 == pytest.approx(1.0, abs=1e-3) and hands.v_p95 == pytest.approx(1.0, abs=1e-3)
    spans = [(p.first_row, p.last_row) for p in hands.pauses[(0.25, 0.3)]]
    assert spans == [(16, 26), (36, 44)]  # the stops, 11 and 9 rows
    assert [(p.first_row, p.last_row) for p in hands.pauses[(0.25, 0.4)]] == []  # neither lasts 0.4 s
    assert [(p.first_row, p.last_row) for p in hands.pauses[(1.5, 0.3)]] == [(0, 49)]  # above every speed: one pause
    for group in ("hips", "feet"):  # nothing else moves: V is 0 and the whole run is one pause
        g = m.groups[group]
        assert g.v_p50 == 0.0 and g.v_p95 == 0.0 and g.n_measured == 50
        assert [(p.first_row, p.last_row) for p in g.pauses[(0.25, 0.3)]] == [(0, 49)]
    assert list(hands.pauses) == [(0.25, 0.3), (0.25, 0.4), (1.5, 0.3)]  # a cell is (tau, d_min), in the order asked


def test_t_met_12b_the_quantiles_are_the_median_and_the_p95_of_the_speed_over_the_measured_rows_only():
    layer, _ = hips_layer()
    k, r, _i = cells(layer)
    for joint in (11, 12):
        drop(k, r, 30, joint, 2)  # the rows 29 and 31 have no value for the hips: two rows are not measured
    layer = edited(layer, keypoints=k, reason=r)
    hips = measure_layer(layer).groups["hips"]
    assert hips.n_rows == 50 and hips.n_measured == 48 and not hips.measured[24] and not hips.measured[26]
    speeds = []
    for g in range(5, 55):
        if g in (29, 31):
            continue
        ys = [(layer.keypoints[g + 1, j, 1] - layer.keypoints[g - 1, j, 1]) / 2.0 * 30.0 / 150.0 for j in (11, 12)]
        speeds.append(statistics.median(abs(float(y)) for y in ys))  # |dy| / (2 steps) / the trunk, per second
    assert hips.v_p50 == pytest.approx(statistics.median(speeds), rel=1e-5)
    assert hips.v_p95 == pytest.approx(percentile(speeds, 95), rel=1e-5)
    assert percentile(speeds, 95) != pytest.approx(percentile(speeds, 90), rel=1e-3)  # the P95 is not the P90


def test_t_met_12b_the_paused_rows_of_a_cell_are_the_rows_of_its_pauses_and_nothing_else():
    hands = measure_layer(hands_layer(), grid=((0.25, 0.3),)).groups["hands"]
    paused = hands.paused_mask((0.25, 0.3))
    assert paused.dtype == bool and paused.shape == (50,)
    assert np.flatnonzero(paused).tolist() == list(range(16, 27)) + list(range(36, 45))
    with pytest.raises(AblationError, match="cell"):
        hands.paused_mask((9.9, 9.9))


def test_t_met_12b_the_hip_range_is_the_range_of_variant_b_of_the_rows_of_the_segment():
    layer, hip_y = hips_layer()
    m = measure_layer(layer)
    rows = range(5, 55)
    kp = layer.keypoints.astype(np.float64)
    heights = []
    for g in rows:
        hip = (kp[g, 11, 1] + kp[g, 12, 1]) / 2.0
        floor = max(kp[g, j, 1] for j in FEET)
        heights.append((floor - hip) / 150.0)  # a true height, in trunk lengths
    expected = percentile(heights, 95) - percentile(heights, 5)
    assert m.hip_b.reason is None and m.hip_b.range == pytest.approx(expected, rel=1e-6)
    assert 0.3 < expected < 0.5  # 30 px of amplitude over a 150 px trunk: about 0.4, not a vector of zeros
    assert m.hip_a is None  # no reference layer, so no variant A


def test_t_met_12b_a_reference_layer_adds_variant_a_with_the_scale_of_that_layer():
    layer, _ = hips_layer()
    reference = exact_layer(body(40, 400.0, trunk=120.0), segment=(0, 40))  # a trunk of 120 px against the layer's 150
    m = measure_layer(layer, reference=reference)
    assert m.hip_a is not None and m.hip_a.reason is None and m.hip_a.range is not None
    # A divides the height of the hips by the scale of the reference (120 px), B by the scale of the segment (150 px)
    assert m.hip_a.range == pytest.approx(m.hip_b.range * 150.0 / 120.0, rel=1e-6)
    assert measure_layer(layer, reference=exact_layer(body(40, 400.0), segment=(0, 40))).hip_a.range == pytest.approx(  # type: ignore[union-attr]
        m.hip_b.range, rel=1e-6
    )  # with a reference of the same trunk A and B agree: the feet stay on the floor


def test_t_met_12b_a_metric_with_no_evidence_is_none_with_its_reason_never_zero():
    layer = edited(hands_layer(), grid_in_segment=np.zeros(G, dtype=bool))  # a segment with no row
    m = measure_layer(layer)
    assert m.hip_b.range is None and m.hip_b.reason == "no_frame"
    for g in m.groups.values():
        assert g.n_rows == 0 and g.n_measured == 0 and g.v_p50 is None and g.v_p95 is None
        assert all(pauses == () for pauses in g.pauses.values())
    flagged = measure_layer(hands_layer())
    assert flagged.hip_b.range is not None  # and the same layer with rows has a value


def test_t_met_12b_the_default_grid_is_the_one_of_the_plan_and_a_bad_grid_is_refused():
    assert PAUSE_GRID == ((0.1, 0.3), (0.2, 0.3), (0.3, 0.3), (0.5, 0.3), (0.2, 0.5))
    layer = hands_layer()
    for bad in (((0.0, 0.3),), ((0.2, -1.0),), ((float("nan"), 0.3),), (), ((0.2, 0.3), (0.2, 0.3)), ((0.2,),), 5):
        with pytest.raises(AblationError, match="grid"):
            measure_layer(layer, grid=bad)  # type: ignore[arg-type]
    with pytest.raises(AblationError, match="layer"):
        measure_layer("not a layer")  # type: ignore[arg-type]


def test_t_met_12b_a_measure_with_rows_that_do_not_match_its_mask_is_refused():
    with pytest.raises(AblationError, match="measured"):
        GroupMeasure(n_rows=5, measured=np.ones(4, dtype=bool), v_p50=None, v_p95=None, pauses={})
    with pytest.raises(AblationError, match="measured"):
        GroupMeasure(n_rows=4, measured=np.ones((2, 2), dtype=bool), v_p50=None, v_p95=None, pauses={})


# --- the agreement of a cut-off with the reference -------------------------------------------------------------------
CELL = (0.2, 0.3)
STEP = 0.1


def pause(first: int, last: int) -> Pause:
    return Pause(first, last, first * STEP, (last + 1) * STEP, False, False)


def group(spans: list[tuple[int, int]], n: int = 20, *, lost: tuple[int, ...] = ()) -> GroupMeasure:
    measured = np.ones(n, dtype=bool)
    measured[list(lost)] = False
    return GroupMeasure(
        n_rows=n, measured=measured, v_p50=0.5, v_p95=1.0, pauses={CELL: tuple(pause(a, b) for a, b in spans)}
    )


def run_of(**groups: GroupMeasure) -> RunMeasure:
    return RunMeasure(groups=dict(groups), hip_b=HipMeasure(range=0.4, reason=None), hip_a=None)


def agreement(this: GroupMeasure, ref: GroupMeasure):
    return agree(run_of(hands=this), run_of(hands=ref), "hands", CELL)


def test_t_met_12c_identical_pauses_agree_completely():
    a = agreement(group([(2, 9), (12, 15)]), group([(2, 9), (12, 15)]))
    assert (a.n_measured, a.paused_rows, a.paused_share) == (20, 12, pytest.approx(0.6))
    assert (a.intersection_rows, a.union_rows, a.iou) == (12, 12, 1.0)
    assert (a.count, a.ref_count, a.count_equal) == (2, 2, True)
    assert (a.matched, a.lost, a.extra) == (2, 0, 0) and a.shifts == ((0, 0), (0, 0))


def test_t_met_12c_a_shifted_pause_has_an_iou_below_one_and_its_boundary_shifts_in_steps():
    a = agreement(group([(3, 10)]), group([(2, 9)]))  # rows 3..10 against 2..9: 7 in both, 9 in either
    assert (a.intersection_rows, a.union_rows) == (7, 9) and a.iou == pytest.approx(7 / 9)
    assert a.shifts == ((1, 1),) and (a.matched, a.lost, a.extra) == (1, 0, 0)
    assert a.paused_share == pytest.approx(8 / 20)


def test_t_met_12c_one_pause_split_in_two_matches_the_larger_piece_and_leaves_the_other_extra():
    a = agreement(group([(2, 6), (9, 15)]), group([(2, 15)]))
    assert (a.count, a.ref_count, a.count_equal) == (2, 1, False)
    assert (a.matched, a.lost, a.extra) == (1, 0, 1)
    assert a.shifts == ((7, 0),)  # the piece 9..15 against 2..15: the start 7 rows later, the same end
    assert (a.intersection_rows, a.union_rows) == (5 + 7, 14)  # the hole between the pieces is in the union


def test_t_met_12c_two_pauses_merged_into_one_match_one_and_lose_the_other():
    a = agreement(group([(2, 15)]), group([(2, 6), (9, 15)]))
    assert (a.matched, a.lost, a.extra) == (1, 1, 0) and a.shifts == ((7, 0),)


def test_t_met_12c_a_pause_that_the_reference_does_not_have_is_extra_and_one_it_has_is_lost():
    gone = agreement(group([]), group([(2, 9)]))
    assert (gone.paused_rows, gone.paused_share, gone.intersection_rows, gone.union_rows) == (0, 0.0, 0, 8)
    assert gone.iou == 0.0 and (gone.matched, gone.lost, gone.extra) == (0, 1, 0) and gone.shifts == ()
    new = agreement(group([(2, 9)]), group([]))
    assert (new.matched, new.lost, new.extra) == (0, 0, 1) and new.iou == 0.0


def test_t_met_12c_two_runs_with_no_pause_at_all_have_no_iou_and_the_same_count():
    a = agreement(group([]), group([]))
    assert (a.union_rows, a.iou, a.count_equal, a.paused_share) == (0, None, True, 0.0)  # an empty union is not 1


def test_t_met_12c_a_run_with_no_measured_row_has_no_paused_share_not_a_zero():
    a = agreement(group([], n=0), group([], n=0))
    assert (a.n_measured, a.paused_rows, a.paused_share, a.iou, a.count_equal) == (0, 0, None, None, True)


def test_t_met_12c_pauses_that_overlap_by_less_than_half_of_the_shorter_one_do_not_match():
    a = agreement(group([(0, 3)]), group([(3, 10)]))  # one row in common, the shorter pause has 4
    assert (a.matched, a.lost, a.extra) == (0, 1, 1)
    b = agreement(group([(0, 4)]), group([(3, 10)]))  # two rows in common of 5: less than half of 5 is 2.5
    assert (b.matched, b.lost, b.extra) == (0, 1, 1)
    c = agreement(group([(0, 5)]), group([(3, 10)]))  # three of 6: half of the shorter one is enough
    assert (c.matched, c.lost, c.extra) == (1, 0, 0) and c.shifts == ((3, 5),)


def test_t_met_12c_only_the_rows_measured_in_both_count_for_the_intersection_and_the_union():
    this = group([(0, 4), (8, 10)], lost=(5, 6, 7))  # the rows 5 to 7 have no value in this one
    ref = group([(0, 10)])  # and are paused in the reference
    a = agreement(this, ref)
    assert (a.n_measured, a.paused_rows, a.paused_share) == (17, 8, pytest.approx(8 / 17))
    assert (a.intersection_rows, a.union_rows, a.iou) == (8, 8, 1.0)  # the rows 5 to 7 are left out of both
    assert a.count == 2 and a.ref_count == 1


def test_t_met_12c_a_group_or_cell_that_does_not_exist_or_runs_of_different_length_are_refused():
    with pytest.raises(AblationError, match="group"):
        agree(run_of(hands=group([])), run_of(hands=group([])), "knees", CELL)
    with pytest.raises(AblationError, match="cell"):
        agree(run_of(hands=group([])), run_of(hands=group([])), "hands", (9.9, 9.9))
    with pytest.raises(AblationError, match="rows"):
        agree(run_of(hands=group([], n=20)), run_of(hands=group([], n=21)), "hands", CELL)


# --- the aggregation over runs ----------------------------------------------------------------------------------------
def two_cutoff_runs() -> list[dict[float, RunMeasure]]:
    """Three runs, the reference 6 Hz and 8 Hz: a long run, a short one that agrees fully, one with another count."""
    long_ref = group([(0, 49)], n=100)
    long_new = group([(25, 74)], n=100)  # 25 rows in common, 75 in either
    short = group([(0, 9)], n=10)
    split_ref = group([(0, 4)], n=10)
    split_new = group([(0, 1), (3, 4)], n=10)
    return [
        {6.0: run_of(hands=long_ref), 8.0: run_of(hands=long_new)},
        {6.0: run_of(hands=short), 8.0: run_of(hands=short)},
        {6.0: run_of(hands=split_ref), 8.0: run_of(hands=split_new)},
    ]


def test_t_met_12d_the_iou_and_the_paused_share_are_pooled_over_the_runs_not_averaged():
    s = aggregate(two_cutoff_runs(), cutoffs=(6.0, 8.0), grid=(CELL,))
    cell = s.cells[(8.0, "hands", CELL)]
    # run 1: 25 rows in both, 75 in either; run 2: 10 and 10; run 3: paused {0, 1, 3, 4} against {0..4}: 4 and 5
    inter, union = 25 + 10 + 4, 75 + 10 + 5
    assert cell.iou == pytest.approx(inter / union)
    assert cell.iou != pytest.approx(np.mean([25 / 75, 1.0, 4 / 5]))  # not the mean of the three ratios
    assert cell.rows_measured == 120 and cell.paused_rows == 50 + 10 + 4
    assert cell.paused_share == pytest.approx(64 / 120)
    assert cell.pauses == 1 + 1 + 2 and cell.runs == 3
    assert s.cells[(6.0, "hands", CELL)].iou == 1.0  # the reference agrees with itself
    assert s.runs == 3


def test_t_met_12d_the_share_of_runs_with_the_same_count_and_the_matches_are_counted_per_run():
    s = aggregate(two_cutoff_runs(), cutoffs=(6.0, 8.0), grid=(CELL,))
    cell = s.cells[(8.0, "hands", CELL)]
    assert cell.same_count == pytest.approx(2 / 3)  # runs 1 and 2 have the reference count, run 3 has 2 against 1
    assert (cell.matched, cell.lost, cell.extra) == (2 + 1, 0, 1)  # the split piece 3..4 is extra, 0..1 is matched
    # the boundary shifts of the three matches in steps, pooled: run 1 (25, 25), run 2 (0, 0), run 3: the piece 0..1
    # against 0..4 starts together and ends 3 rows early (0, 3)
    shifts = [25, 25, 0, 0, 0, 3]
    assert cell.shifts_n == 6 and cell.shift_max == 25 and cell.shift_median == pytest.approx(1.5)
    assert cell.shift_p95 == pytest.approx(percentile(shifts, 95))


def test_t_met_12d_the_speed_quantiles_are_the_median_over_the_runs_and_a_run_with_nothing_is_left_out():
    quiet = GroupMeasure(n_rows=0, measured=np.zeros(0, dtype=bool), v_p50=None, v_p95=None, pauses={CELL: ()})
    fast = lambda p50, p95: GroupMeasure(  # noqa: E731
        n_rows=10, measured=np.ones(10, dtype=bool), v_p50=p50, v_p95=p95, pauses={CELL: ()}
    )
    runs = [
        {6.0: run_of(hands=fast(0.2, 1.0)), 8.0: run_of(hands=fast(0.4, 2.0))},
        {6.0: run_of(hands=fast(0.6, 3.0)), 8.0: run_of(hands=fast(0.8, 4.0))},
        {6.0: run_of(hands=fast(1.0, 5.0)), 8.0: run_of(hands=fast(2.0, 10.0))},
        {6.0: run_of(hands=quiet), 8.0: run_of(hands=quiet)},
    ]
    s = aggregate(runs, cutoffs=(6.0, 8.0), grid=(CELL,))
    v = s.speed[(8.0, "hands")]
    # the median of 0.4, 0.8 and 2.0 is 0.8 (their mean is 1.07), of 2.0, 4.0 and 10.0 it is 4.0
    assert (v.runs, v.v_p50, v.v_p95) == (3, pytest.approx(0.8), pytest.approx(4.0))
    assert s.runs == 4 and s.cells[(8.0, "hands", CELL)].runs == 3  # a run with no row is a run, not a number
    assert s.cells[(8.0, "hands", CELL)].rows_measured == 30


def test_t_met_12d_the_reference_is_6_hz_whatever_the_order_of_the_cutoffs():
    a = aggregate(two_cutoff_runs(), cutoffs=(6.0, 8.0), grid=(CELL,))
    b = aggregate(two_cutoff_runs(), cutoffs=(8.0, 6.0), grid=(CELL,))
    assert b.cells[(8.0, "hands", CELL)] == a.cells[(8.0, "hands", CELL)]
    assert b.cells[(6.0, "hands", CELL)].iou == 1.0 and b.cells[(8.0, "hands", CELL)].iou != 1.0


def test_t_met_12d_the_p95_of_the_boundary_shifts_is_the_95th_percentile_of_all_of_them():
    runs = []
    for k in range(10):  # the pause starts k rows late in run k and ends together with the reference's
        runs.append({6.0: run_of(hands=group([(0, 20)], n=30)), 8.0: run_of(hands=group([(k, 20)], n=30))})
    cell = aggregate(runs, cutoffs=(6.0, 8.0), grid=(CELL,)).cells[(8.0, "hands", CELL)]
    shifts = list(range(10)) + [0] * 10  # the start shifts 0 to 9 and the ten end shifts of 0
    assert cell.shifts_n == 20 and cell.shift_max == 9
    assert cell.shift_median == pytest.approx(percentile(shifts, 50)) and cell.shift_p95 == pytest.approx(
        percentile(shifts, 95)
    )
    assert percentile(shifts, 95) != pytest.approx(percentile(shifts, 90))


def test_t_met_12d_the_csv_has_a_row_per_source_cutoff_group_and_cell_with_the_numbers_of_the_summary():
    s = aggregate(two_cutoff_runs(), cutoffs=(6.0, 8.0), grid=(CELL,))
    from taiji_ai.bench.filter_ablation import cells_csv

    rows = list(csv.DictReader(io.StringIO(cells_csv({"example": s}))))
    assert len(rows) == 2 and {r["source"] for r in rows} == {"example"}
    row = next(r for r in rows if r["cutoff_hz"] == "8.0")
    cell = s.cells[(8.0, "hands", CELL)]
    assert (row["group"], float(row["tau"]), float(row["d_min_s"])) == ("hands", 0.2, 0.3)
    assert int(row["pauses"]) == cell.pauses and int(row["paused_rows"]) == cell.paused_rows
    assert float(row["iou"]) == pytest.approx(cell.iou) and int(row["shift_max"]) == cell.shift_max
    quiet = GroupMeasure(n_rows=0, measured=np.zeros(0, dtype=bool), v_p50=None, v_p95=None, pauses={CELL: ()})
    empty = aggregate([{6.0: run_of(hands=quiet), 8.0: run_of(hands=quiet)}], cutoffs=(6.0, 8.0), grid=(CELL,))
    blank = list(csv.DictReader(io.StringIO(cells_csv({"empty": empty}))))[0]
    assert blank["iou"] == "" and blank["paused_share"] == "" and blank["shift_max"] == ""  # missing: empty, not "None"


def test_t_met_12d_the_hip_range_difference_is_relative_to_the_reference_in_percent():
    def with_hip(b: float | None) -> RunMeasure:
        return RunMeasure(
            groups={"hands": group([])}, hip_b=HipMeasure(range=b, reason=None if b else "no_frame"), hip_a=None
        )

    runs = [
        {6.0: with_hip(0.50), 8.0: with_hip(0.505)},  # +1 %
        {6.0: with_hip(0.40), 8.0: with_hip(0.38)},  # -5 %
        {6.0: with_hip(0.30), 8.0: with_hip(0.30)},  # 0
        {6.0: with_hip(None), 8.0: with_hip(0.30)},  # no reference value: not a pair
    ]
    h = aggregate(runs, cutoffs=(6.0, 8.0), grid=(CELL,)).hip[(8.0, "B")]
    assert (h.runs, h.n) == (4, 3)
    assert h.abs_diff_max == pytest.approx(5.0) and h.abs_diff_median == pytest.approx(1.0)
    assert h.abs_diff_p95 == pytest.approx(percentile([1.0, 5.0, 0.0], 95))
    assert (6.0, "A") not in aggregate(runs, cutoffs=(6.0, 8.0), grid=(CELL,)).hip  # no variant A was given


def test_t_met_12d_a_run_without_every_cutoff_or_the_reference_is_refused():
    runs = two_cutoff_runs()
    with pytest.raises(AblationError, match="8"):
        aggregate([{6.0: runs[0][6.0]}], cutoffs=(6.0, 8.0), grid=(CELL,))
    with pytest.raises(AblationError, match="6"):
        aggregate(runs, cutoffs=(8.0, 10.0), grid=(CELL,))
    with pytest.raises(AblationError, match="runs"):
        aggregate([], cutoffs=(6.0, 8.0), grid=(CELL,))


# --- the tables ------------------------------------------------------------------------------------------------------
def test_t_met_12d_the_tables_are_deterministic_and_hold_numbers_and_names_but_no_path():
    s = aggregate(two_cutoff_runs(), cutoffs=(6.0, 8.0), grid=(CELL,))
    text = render_tables({"synthetic example": s})
    assert text == render_tables({"synthetic example": s})  # the same input, the same text
    assert "synthetic example" in text and "8 Hz" in text and "6 Hz" in text and "hands" in text
    assert "0.2" in text and "0.3" in text  # the cell (tau, d_min)
    assert "\\" not in text and "/" not in text.replace("n/a", "").replace("and/or", "")  # no path separators
    assert "nan" not in text.lower().replace("n/a", "")  # a missing number is written n/a, never nan
    order = render_tables({"b source": s, "a source": s})
    assert order.index("b source") < order.index("a source")  # the order of the mapping: nothing is sorted away


def test_t_met_12d_a_missing_number_is_written_as_not_available():
    quiet = GroupMeasure(n_rows=0, measured=np.zeros(0, dtype=bool), v_p50=None, v_p95=None, pauses={CELL: ()})
    runs = [{6.0: run_of(hands=quiet), 8.0: run_of(hands=quiet)}]
    text = render_tables({"empty": aggregate(runs, cutoffs=(6.0, 8.0), grid=(CELL,))})
    assert "n/a" in text and "nan" not in text.lower() and "none" not in text.lower()  # every table writes n/a
