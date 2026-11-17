"""T-MET-03, 03i and 03j: hip height, variant A, on the generator's scenarios through the real quality chain (P5.03).

The truth of ``tests/helpers/synth.py`` comes from the continuous model, never from the sampled output. SYN-02 has a hip
that moves by ``A * Lambda * sin(2 pi f t)`` (the continuous ``P95 - P5`` is 0.9877 x 2A); SYN-09 is a person who walks
away from a pinhole camera, with a standing reference at the start whose own layer gives ``Lambda_take``. Every layer
here is what the pipeline would hand to the metric: ``run_quality_arrays`` then ``pose_filtered_from_result``.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.synth import TOLERANCES, apply_roll, make_sequence
from taiji_ai.metrics.geometry import roll_from_line
from taiji_ai.metrics.hip_height import HipHeightResult, hip_height_a
from taiji_ai.quality.layers_io import PoseFiltered

RANGE_TOL = TOLERANCES["SYN-02"]["range_relative_error"]
SYN09_TOL = TOLERANCES["SYN-09"]["range_abs_error_lambda"]


def run(layer: PoseFiltered, reference: PoseFiltered, last_s: float, **kwargs) -> HipHeightResult:
    return hip_height_a(
        layer,
        reference=reference,
        stable_intervals=[(0.0, last_s + 1.0)],  # the coach confirmed the whole clip
        flags={},
        camera_id="camA",
        view_category="front",
        **kwargs,
    )


def range_of(result: HipHeightResult) -> float:
    (s,) = [s for s in result.summary.statistics if s.name == "hip_height_range"]
    assert s.value is not None
    return s.value


# --- T-MET-03: SYN-02 -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("noise", [0.0, 1.0])
@pytest.mark.parametrize("seed", [1, 2])
def test_t_met_03_syn02_variant_a_measures_twice_the_amplitude_within_five_percent(seed: int, noise: float):
    seq = make_sequence("SYN-02", seed=seed, noise_px=noise)
    reference = make_sequence("SYN-01", seed=seed, noise_px=noise)  # the same performer standing still, same scale
    result = run(layer_of_sequence(seq), layer_of_sequence(reference), float(seq.t_sec[-1]))
    amplitude = float(seq.truth["A"])
    assert abs(range_of(result) / (2.0 * amplitude) - 1.0) <= RANGE_TOL
    assert result.series.header.coverage.measured == result.series.header.coverage.total == len(seq.t_sec)
    assert result.summary.parameters["scale_px"] == pytest.approx(float(seq.truth["scale_px"]), abs=1.0)


@pytest.mark.parametrize(("noise", "median_bound", "max_bound"), [(0.0, 1e-4, 1e-3), (1.0, 0.005, 0.02)])
def test_t_met_03_syn02_the_profile_is_the_truth_of_the_continuous_model_up_to_the_level(
    noise, median_bound, max_bound
):
    # measured on seeds 1 to 3 (section 5 of the task file): no noise 0.0000 (a float32 pixel); 1 px of noise: median
    # under 0.003 and maximum under 0.007; the bounds leave room
    seq = make_sequence("SYN-02", seed=1, noise_px=noise)
    reference = make_sequence("SYN-01", seed=1, noise_px=noise)
    result = run(layer_of_sequence(seq), layer_of_sequence(reference), float(seq.t_sec[-1]))
    truth = np.asarray(seq.truth["hip_y"]) / float(seq.truth["scale_px"])  # Lambda units, y down, from the model
    shape = np.asarray(result.series.values) - truth
    shape -= np.median(shape)  # the level is the origin of the roll rotation: only differences mean anything
    assert np.median(np.abs(shape)) <= median_bound and np.abs(shape).max() <= max_bound


def test_t_met_03_syn02_the_extremes_are_where_the_hip_is_lowest_and_highest():
    seq = make_sequence("SYN-02", seed=1, noise_px=0.0)
    reference = make_sequence("SYN-01", seed=1, noise_px=0.0)
    result = run(layer_of_sequence(seq), layer_of_sequence(reference), float(seq.t_sec[-1]))
    truth_y = np.asarray(seq.truth["hip_y"])  # px, y down, from the continuous model
    ev = {e.kind: e for e in result.summary.events}
    assert ev["max"].t_start == pytest.approx(float(seq.t_sec[int(np.argmax(truth_y))]), abs=3 / 30)
    assert ev["min"].t_start == pytest.approx(float(seq.t_sec[int(np.argmin(truth_y))]), abs=3 / 30)


# --- T-MET-03i: SYN-09, variant A -----------------------------------------------------------------------------------
@pytest.mark.parametrize("noise", [0.0, 1.0])
@pytest.mark.parametrize("seed", [1, 2])
def test_t_met_03i_syn09_the_scale_of_the_reference_and_the_range_are_the_truth_of_variant_a(seed: int, noise: float):
    seq = make_sequence("SYN-09", seed=seed, noise_px=noise)
    truth = seq.truth
    standing = seq.t_sec < float(truth["reference_s"])  # the first second: its own segment, its own layer
    result = run(layer_of_sequence(seq), layer_of_sequence(seq, rows=standing), float(seq.t_sec[-1]))
    assert result.summary.parameters["scale_px"] == pytest.approx(float(truth["lambda_take"]), abs=1.0)
    assert result.series.header.coverage.measured == len(seq.t_sec)
    assert abs(range_of(result) - float(truth["range_A"])) <= SYN09_TOL
    values = np.asarray(result.series.values)
    assert np.median(np.abs(values - np.asarray(truth["expected_hA"]))) <= SYN09_TOL


# --- T-MET-03k: a variable frame rate ---------------------------------------------------------------------------------
def test_t_met_03k_a_variable_frame_rate_gives_a_series_on_the_uniform_grid_not_on_the_frames():
    seq = make_sequence("SYN-07", seed=1, noise_px=1.0)  # SYN-05 motion at variable-frame-rate timestamps
    reference = make_sequence("SYN-01", seed=1, noise_px=1.0)
    layer = layer_of_sequence(seq)
    assert layer.meta.timeline.resampled and len(layer.t_grid) > len(seq.t_sec)  # the grid is not the frames
    result = run(layer, layer_of_sequence(reference), float(seq.t_sec[-1]))
    series, step = result.series, result.series.header.step_s
    assert step == pytest.approx(1 / 30, rel=1e-6) and len(series.t_sec) == len(layer.t_grid)
    assert np.allclose(np.diff(series.t_sec), step, rtol=0, atol=1e-9)  # the clock of the series is the uniform grid
    assert series.header.coverage.measured == series.header.coverage.total == len(layer.t_grid)
    assert np.isfinite(series.values).all() and result.summary.evidence == "sufficient"


# --- T-MET-03j: a rolled camera -------------------------------------------------------------------------------------
def test_t_met_03j_a_camera_rolled_by_30_degrees_needs_the_roll_taken_out_and_with_it_the_range_is_right():
    beta, centre = 30.0, (960.0, 540.0)
    seq = make_sequence("SYN-02", seed=1, noise_px=1.0)
    reference = make_sequence("SYN-01", seed=1, noise_px=1.0)
    rolled = layer_of_sequence(seq, apply_roll(seq.kp, beta, centre))
    rolled_ref = layer_of_sequence(reference, apply_roll(reference.kp, beta, centre))
    world_vertical = apply_roll(np.array([[960.0, 440.0], [960.0, 640.0]]), beta, centre)  # a plumb line, seen rolled
    roll = roll_from_line(world_vertical[0], world_vertical[1])
    assert roll == pytest.approx(beta, abs=1e-9)
    last = float(seq.t_sec[-1])
    amplitude = float(seq.truth["A"])
    right = range_of(run(rolled, rolled_ref, last, roll_deg=roll))
    wrong = range_of(run(rolled, rolled_ref, last))  # the roll is not taken out
    assert abs(right / (2.0 * amplitude) - 1.0) <= RANGE_TOL
    assert abs(wrong / (2.0 * amplitude) - 1.0) > 0.10  # a rolled camera shrinks a vertical range by cos(beta)
