"""T-MET-09, 09e and T-MET-10: the pauses of a joint group on SYN-05, SYN-07, SYN-06 and SYN-01 through the real chain
(P5.07).

The truth is the continuous speed profile of the generator, not its exact pauses: ``slow_intervals`` gives the
stretches where the analytic group speed is below ``τ``, which are a little longer than the pauses (the cosine ramps)
and include the turning point of the movement. ``τ`` is chosen by the test (a share of the true peak of the group, or an
absolute value above the noise floor), never by the product: ``group_speed`` has no default for it. Every layer is what
the pipeline would hand to the metric: ``run_quality_arrays`` then ``pose_filtered_from_result``.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.synth import make_sequence, slow_intervals, speed_at
from taiji_ai.metrics.series import MetricResult
from taiji_ai.metrics.tempo import find_pauses, group_speed
from taiji_ai.quality.layers_io import PoseFiltered

SHARE = 0.10  # τ as a share of the true peak of the group: where the boundary is resolved to about half a step
D_MIN = 0.3  # s: the pauses of the generator last 0.6 s, the turning point of its movement about 0.2 s
FLOOR_TAU = 0.3  # body lengths per second: 1.7 times the largest speed that 1 px of noise gives a still joint (0.18)


def run(layer: PoseFiltered, group: str, **kwargs) -> MetricResult:
    return group_speed(layer, group=group, flags={}, camera_id="camA", view_category="front", **kwargs)


def peak(seq, group: str) -> float:
    return float(speed_at(seq, np.linspace(0.0, float(seq.params["duration"]), 5001))[group].max())


def stat(result: MetricResult, name: str) -> float | None:
    (s,) = [s for s in result.summary.statistics if s.name == name]
    return s.value


def edges(result: MetricResult) -> list[float]:
    """The start and the end of every pause, flattened (``pytest.approx`` does not take nested lists)."""
    return [t for e in result.summary.events for t in (e.t_start, e.t_end)]


def truth_stretches(seq, group: str, tau: float, d_min: float) -> list[tuple[float, float]]:
    return [iv for iv in slow_intervals(seq, group, tau) if iv[1] - iv[0] >= d_min]


def boundary_errors(result: MetricResult, truth: list[tuple[float, float]]) -> list[float]:
    """The error of every boundary of the pauses against the true crossings, in steps of the grid."""
    step = result.series.header.step_s
    assert len(result.summary.events) == len(truth)
    out = []
    for event, (a, b) in zip(result.summary.events, truth, strict=True):
        out += [abs(event.t_start - a) / step, abs(event.t_end - b) / step]
    return out


# --- T-MET-09: the right number of pauses, boundaries within one frame, noise-free ------------------------------------
@pytest.mark.parametrize("group", ["hands", "hips"])
@pytest.mark.parametrize("scenario", ["SYN-05", "SYN-07"])
def test_t_met_09_the_pauses_are_the_true_slow_stretches_and_their_boundaries_are_within_one_frame(scenario, group):
    seq = make_sequence(scenario, seed=1)  # the default of the scenario: no noise
    layer = layer_of_sequence(seq)
    tau = SHARE * peak(seq, group)
    result = run(layer, group, pause_tau=tau, pause_min_s=D_MIN)
    truth = truth_stretches(seq, group, tau, D_MIN)
    assert len(result.summary.events) == len(truth) == seq.truth["n_pauses"]  # 2 on SYN-05, 1 on SYN-07
    errors = boundary_errors(result, truth)
    assert max(errors) <= 1.0  # the tolerance of the plan, one frame (a step of the grid); measured 0.51 and 0.53
    assert max(errors) < 0.75  # and not by a hair: the bulk of the margin is there
    assert stat(result, "pause_count") == float(len(truth)) and stat(result, "pause_cut_count") == 0.0
    step = result.series.header.step_s
    lengths = [e.t_end - e.t_start for e in result.summary.events]
    assert stat(result, "pause_total_s") == pytest.approx(sum(lengths))
    assert stat(result, "pause_longest_s") == pytest.approx(max(lengths))  # on SYN-05 the second pause is the longer
    assert all(
        abs((e.t_end - e.t_start) - (b - a)) <= step for e, (a, b) in zip(result.summary.events, truth, strict=True)
    )


def test_t_met_09_the_hips_and_the_hands_have_the_same_pauses_at_the_same_share_of_their_own_peak():
    seq = make_sequence("SYN-05", seed=1)
    layer = layer_of_sequence(seq)
    found = {g: run(layer, g, pause_tau=SHARE * peak(seq, g), pause_min_s=D_MIN) for g in ("hands", "hips")}
    assert len(edges(found["hands"])) == 4 and edges(found["hands"]) == pytest.approx(edges(found["hips"]))


def test_t_met_09_a_group_that_does_not_move_is_one_pause_over_all_its_measured_rows():
    seq = make_sequence("SYN-05", seed=1)
    result = run(layer_of_sequence(seq), "feet", pause_tau=0.05, pause_min_s=D_MIN)  # the feet's true speed is 0
    (event,) = result.summary.events
    series = result.series
    measured = np.flatnonzero(np.asarray(series.reason) == 0)
    step = series.header.step_s
    assert measured.tolist() == list(range(1, len(series.t_sec) - 1))  # the two ends of the track are run_edge
    assert event.t_start == pytest.approx(series.t_sec[measured[0]]) and event.t_end == pytest.approx(
        series.t_sec[measured[-1]] + step
    )
    assert (
        stat(result, "pause_count") == 1.0 and stat(result, "pause_cut_count") == 0.0
    )  # the ends of a track do not cut


# --- T-MET-09e: the limits, measured --------------------------------------------------------------------------------
def test_t_met_09e_the_turning__point_of_the_movement_is_a_pause_unless_the_minimum_removes_it():
    seq = make_sequence("SYN-05", seed=1)
    layer = layer_of_sequence(seq)
    tau = SHARE * peak(seq, "hands")
    apex = slow_intervals(seq, "hands", 1e-7)[1]  # the speed crosses 0 at the top of the movement, between the pauses
    assert 2.4 < 0.5 * (apex[0] + apex[1]) < 2.6
    short = run(layer, "hands", pause_tau=tau, pause_min_s=0.2).summary.events
    assert (
        len(short) == 3 and 0.2 <= short[1].t_end - short[1].t_start < 0.3
    )  # measured 0.233 s: not a pause of the performer
    assert short[1].t_start < 0.5 * (apex[0] + apex[1]) < short[1].t_end
    assert len(run(layer, "hands", pause_tau=tau, pause_min_s=D_MIN).summary.events) == 2


def test_t_met_09e_a_higher_threshold_merges_the_turning_point_into_the_pause_that_follows():
    seq = make_sequence("SYN-05", seed=1)
    layer = layer_of_sequence(seq)
    events = run(layer, "hands", pause_tau=0.20 * peak(seq, "hands"), pause_min_s=D_MIN).summary.events
    assert len(events) == 2
    assert events[1].t_start < 2.5 and events[1].t_end > 3.4  # measured (2.30, 3.57): the exact pause is (2.8, 3.4)


@pytest.mark.parametrize("scenario", ["SYN-05", "SYN-07"])
def test_t_met_09e_a_threshold_near_zero_resolves_a_boundary_worse_than_a_frame_but_not_by_much(scenario):
    seq = make_sequence(scenario, seed=1)
    layer = layer_of_sequence(seq)
    tau = 0.05 * peak(seq, "hands")  # the ramp is a cosine: near 0 it is flat, so a small error in V moves the edge far
    result = run(layer, "hands", pause_tau=tau, pause_min_s=D_MIN)
    errors = boundary_errors(result, truth_stretches(seq, "hands", tau, D_MIN))
    assert max(errors) < 1.2  # measured 1.05 and 1.07 steps against the 1 frame that holds at a share of 10 %


# --- T-MET-10: no false pause from noise or from a gap --------------------------------------------------------------
@pytest.mark.parametrize("group", ["hands", "hips", "feet"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_met_10_a_still_clip_at_one_pixel_of_noise_is_one_pause_when_tau_clears_the_floor(seed, group):
    seq = make_sequence("SYN-01", seed=seed, noise_px=1.0)
    result = run(layer_of_sequence(seq), group, pause_tau=FLOOR_TAU, pause_min_s=D_MIN)
    series = result.series
    measured = np.flatnonzero(np.asarray(series.reason) == 0)
    step = series.header.step_s
    assert np.asarray(series.values)[measured].max() < FLOOR_TAU  # measured 0.129 to 0.180: the floor is below tau
    (event,) = result.summary.events  # no fragment: noise does not split the pause
    assert event.t_start == pytest.approx(series.t_sec[measured[0]])
    assert event.t_end == pytest.approx(series.t_sec[measured[-1]] + step)
    assert stat(result, "pause_count") == 1.0 and stat(result, "pause_cut_count") == 0.0
    assert stat(result, "pause_total_s") == pytest.approx(len(measured) * step)


def test_t_met_10_a_still_clip_without_noise_is_one_pause_at_any_threshold_above_zero():
    seq = make_sequence("SYN-01", seed=1, noise_px=0.0)
    result = run(layer_of_sequence(seq), "hands", pause_tau=1e-6, pause_min_s=D_MIN)  # V is exactly 0
    assert len(result.summary.events) == 1 and stat(result, "pause_count") == 1.0


@pytest.mark.parametrize("group", ["hands", "hips"])
def test_t_met_10_a_hole_and_a_bridge_in_the_wrists_leave_no_trace_on_the_pauses_without_noise(group):
    plain = make_sequence("SYN-05", seed=1)  # the same motion as SYN-06, without the two gaps of the wrists
    gapped = make_sequence("SYN-06", seed=1)  # a 300 ms hole at 0.3 s and a 100 ms one at 2.0 s (bridged by the chain)
    tau = SHARE * peak(plain, group)
    a = run(layer_of_sequence(plain), group, pause_tau=tau, pause_min_s=D_MIN)
    b = run(layer_of_sequence(gapped), group, pause_tau=tau, pause_min_s=D_MIN)
    lost = int((np.asarray(b.series.reason) == 2).sum())
    assert lost == (
        11 if group == "hands" else 0
    )  # the 300 ms hole costs the hands 11 rows (a row needs both neighbours)
    assert len(edges(a)) == 4 and edges(b) == pytest.approx(edges(a))
    assert stat(b, "pause_count") == stat(a, "pause_count") == 2.0 and stat(b, "pause_cut_count") == 0.0


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_met_10_with_noise_and_gaps_the_count_is_the_true_one_and_no_pause_lies_in_a_moving_stretch(seed):
    seq = make_sequence("SYN-06", seed=seed, noise_px=1.0)
    result = run(layer_of_sequence(seq), "hands", pause_tau=FLOOR_TAU, pause_min_s=D_MIN)
    truth = truth_stretches(seq, "hands", FLOOR_TAU, D_MIN)
    assert len(truth) == len(result.summary.events) == 2
    for event, (a, b) in zip(result.summary.events, truth, strict=True):
        assert event.t_start < b and event.t_end > a  # every pause overlaps its true stretch, and there is none besides
    assert max(boundary_errors(result, truth)) < 2.0  # noise moves a boundary: measured up to 1.5 steps


def test_t_met_10_a_hole_inside_a_real_pause_cuts_it_and_a_minimum_above_the_pieces_loses_it():
    seq = make_sequence("SYN-06", seed=1, gaps=((("LWrist", "RWrist"), 1.2, 0.300),))  # the hole falls in (1.0, 1.6)
    layer = layer_of_sequence(seq)
    tau = SHARE * peak(seq, "hands")
    series = run(layer, "hands").series
    lost = np.asarray(series.t_sec)[np.asarray(series.reason) == 2]
    assert 1.1 < lost.min() and lost.max() < 1.6  # the hole is inside the pause
    pieces = run(layer, "hands", pause_tau=tau, pause_min_s=0.1)
    found = find_pauses(pieces.series, tau=tau, min_pause_s=0.1)
    first = [p for p in found if p.t_start < 2.0]  # the two pieces of the first pause (the turning point is later)
    assert len(first) == 2 and (first[0].cut_before, first[0].cut_after) == (False, True)
    assert (first[1].cut_before, first[1].cut_after) == (True, False)  # one real pause seen as two cut pieces
    assert first[0].t_end <= lost.min() + 1e-9 and first[1].t_start >= lost.max()  # never joined across the hole
    assert stat(pieces, "pause_cut_count") == 2.0
    # measured (the limit of Q14): with the minimum at 0.3 s neither piece lasts it and the pause is gone, with no trace
    gone = run(layer, "hands", pause_tau=tau, pause_min_s=D_MIN)
    assert [e for e in gone.summary.events if e.t_start < 2.0] == []
    assert stat(gone, "pause_count") == 1.0 and stat(gone, "pause_cut_count") == 0.0
