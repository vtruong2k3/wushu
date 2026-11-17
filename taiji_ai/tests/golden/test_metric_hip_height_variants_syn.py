"""T-MET-04, 04g and T-MET-05: hip height variant B, and both variants against the pinhole model (P5.04).

The truth of ``tests/helpers/synth.py`` comes from the continuous model, never from the sampled output. SYN-02: the hips
move by ``A * Lambda * sin(2 pi f t)`` and the feet stay where they are, so B (a true height, up is positive) has the
same range as A. SYN-09: a person walks away from a pinhole camera while the physical hip height never changes; the
truth holds the Appendix B1 answer of **both** variants (``range_A``, ``range_B``, ``expected_hA``, ``expected_hB``).
DEC-0014: both are computed, each is checked against its own truth, and no order between A and B is asserted. Every
layer is what the pipeline would hand to the metric: ``run_quality_arrays`` then ``pose_filtered_from_result``.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.synth import TOLERANCES, apply_roll, make_sequence
from taiji_ai.metrics.geometry import roll_from_line
from taiji_ai.metrics.hip_height import HipHeightResult, hip_height_a, hip_height_b
from taiji_ai.pose.skeleton import GROUND_CANDIDATES
from taiji_ai.quality.layers_io import PoseFiltered

RANGE_TOL = TOLERANCES["SYN-02"]["range_relative_error"]
SYN09_TOL = TOLERANCES["SYN-09"]["range_abs_error_lambda"]
GEOMETRIES = [(cam, ratio) for cam in (0.6, 1.0, 1.3) for ratio in (1.5, 2.0)]  # camera height m, depth ratio


def run_b(layer: PoseFiltered, last_s: float, **kwargs) -> HipHeightResult:
    return hip_height_b(
        layer,
        stable_intervals=[(0.0, last_s + 1.0)],  # the coach confirmed the whole clip
        flags={},
        camera_id="camA",
        view_category="front",
        **kwargs,
    )


def run_a(layer: PoseFiltered, reference: PoseFiltered, last_s: float, **kwargs) -> HipHeightResult:
    return hip_height_a(
        layer,
        reference=reference,
        stable_intervals=[(0.0, last_s + 1.0)],
        flags={},
        camera_id="camA",
        view_category="front",
        **kwargs,
    )


def range_of(result: HipHeightResult) -> float:
    (s,) = [s for s in result.summary.statistics if s.name == "hip_height_range"]
    assert s.value is not None
    return s.value


# --- T-MET-04: SYN-02 -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("noise", [0.0, 1.0])
@pytest.mark.parametrize("seed", [1, 2])
def test_t_met_04_syn02_variant_b_measures_twice_the_amplitude_within_five_percent(seed: int, noise: float):
    seq = make_sequence("SYN-02", seed=seed, noise_px=noise)
    result = run_b(layer_of_sequence(seq), float(seq.t_sec[-1]))
    amplitude = float(seq.truth["A"])
    assert abs(range_of(result) / (2.0 * amplitude) - 1.0) <= RANGE_TOL
    assert result.series.header.coverage.measured == result.series.header.coverage.total == len(seq.t_sec)
    assert result.summary.parameters["scale_px"] == pytest.approx(float(seq.truth["scale_px"]), abs=1.0)


@pytest.mark.parametrize(("noise", "median_bound", "max_bound"), [(0.0, 1e-4, 1e-3), (1.0, 0.005, 0.02)])
def test_t_met_04_syn02_the_profile_is_the_truth_of_the_continuous_model(noise, median_bound, max_bound):
    # measured on seeds 1 to 3 (section 5 of the task file): no noise, 3e-5 at most (a float32 pixel); 1 px of noise:
    # median under 0.004 and maximum under 0.013 (the feet add their own noise to the hips'); the bounds leave room
    seq = make_sequence("SYN-02", seed=1, noise_px=noise)
    result = run_b(layer_of_sequence(seq), float(seq.t_sec[-1]))
    scale = float(seq.truth["scale_px"])
    ground = np.asarray(seq.kp_true)[:, list(GROUND_CANDIDATES), 1].max(axis=1)  # the true lowest foot point, px
    truth = (ground - np.asarray(seq.truth["hip_y"])) / scale  # Appendix B1 on the noise-free positions, Lambda units
    # B has a level (a height above the floor), so the profile is compared as it is, not up to a constant
    error = np.asarray(result.series.values) - truth
    assert np.median(np.abs(error)) <= median_bound and np.abs(error).max() <= max_bound


def test_t_met_04_syn02_the_extremes_are_where_the_hip_is_highest_and_lowest():
    seq = make_sequence("SYN-02", seed=1, noise_px=0.0)
    result = run_b(layer_of_sequence(seq), float(seq.t_sec[-1]))
    truth_y = np.asarray(seq.truth["hip_y"])  # px, y down, from the continuous model
    ev = {e.kind: e for e in result.summary.events}
    assert ev["max"].t_start == pytest.approx(float(seq.t_sec[int(np.argmin(truth_y))]), abs=3 / 30)  # highest hip
    assert ev["min"].t_start == pytest.approx(float(seq.t_sec[int(np.argmax(truth_y))]), abs=3 / 30)  # lowest hip


# --- T-MET-04g: a rolled camera and a variable frame rate -----------------------------------------------------------
def test_t_met_04g_a_camera_rolled_by_30_degrees_needs_the_roll_taken_out_and_with_it_the_range_is_right():
    beta, centre = 30.0, (960.0, 540.0)
    seq = make_sequence("SYN-02", seed=1, noise_px=1.0)
    rolled = layer_of_sequence(seq, apply_roll(seq.kp, beta, centre))
    world_vertical = apply_roll(np.array([[960.0, 440.0], [960.0, 640.0]]), beta, centre)  # a plumb line, seen rolled
    roll = roll_from_line(world_vertical[0], world_vertical[1])
    assert roll == pytest.approx(beta, abs=1e-9)
    last, amplitude = float(seq.t_sec[-1]), float(seq.truth["A"])
    right = range_of(run_b(rolled, last, roll_deg=roll))
    wrong = range_of(run_b(rolled, last))  # the roll is not taken out
    assert abs(right / (2.0 * amplitude) - 1.0) <= RANGE_TOL
    assert abs(wrong / (2.0 * amplitude) - 1.0) > 0.10  # a rolled camera shrinks a vertical range by cos(beta)


def test_t_met_04g_a_variable_frame_rate_gives_a_series_on_the_uniform_grid_not_on_the_frames():
    seq = make_sequence("SYN-07", seed=1, noise_px=1.0)  # SYN-05 motion at variable-frame-rate timestamps
    layer = layer_of_sequence(seq)
    assert layer.meta.timeline.resampled and len(layer.t_grid) > len(seq.t_sec)  # the grid is not the frames
    result = run_b(layer, float(seq.t_sec[-1]))
    series, step = result.series, result.series.header.step_s
    assert step == pytest.approx(1 / 30, rel=1e-6) and len(series.t_sec) == len(layer.t_grid)
    assert np.allclose(np.diff(series.t_sec), step, rtol=0, atol=1e-9)  # the clock of the series is the uniform grid
    assert series.header.coverage.measured == series.header.coverage.total == len(layer.t_grid)
    assert np.isfinite(series.values).all() and result.summary.evidence == "sufficient"


# --- T-MET-05: SYN-09, both variants against the pinhole model ------------------------------------------------------
def syn09(cam: float, ratio: float, noise: float):
    seq = make_sequence("SYN-09", seed=1, noise_px=noise, cam_height_m=cam, depth_ratio=ratio)
    standing = seq.t_sec < float(seq.truth["reference_s"])  # the first second: the reference is its own segment
    last = float(seq.t_sec[-1])
    layer, reference = layer_of_sequence(seq), layer_of_sequence(seq, rows=standing)
    return seq, run_a(layer, reference, last), run_b(layer, last)


@pytest.mark.parametrize("noise", [0.0, 1.0])
@pytest.mark.parametrize(("cam", "ratio"), GEOMETRIES)
def test_t_met_05_syn09_each_variant_matches_its_own_appendix_b_truth_and_no_order_is_asserted(cam, ratio, noise):
    seq, a, b = syn09(cam, ratio, noise)
    truth = seq.truth
    assert a.summary.parameters["scale_px"] == pytest.approx(float(truth["lambda_take"]), abs=1.0)
    assert b.summary.parameters["scale_px"] == pytest.approx(float(truth["lambda_segment"]), abs=1.0)
    for result in (a, b):
        assert result.series.header.coverage.measured == len(seq.t_sec) and result.summary.evidence == "sufficient"
    assert abs(range_of(a) - float(truth["range_A"])) <= SYN09_TOL
    assert abs(range_of(b) - float(truth["range_B"])) <= SYN09_TOL
    assert np.median(np.abs(np.asarray(a.series.values) - np.asarray(truth["expected_hA"]))) <= SYN09_TOL
    assert np.median(np.abs(np.asarray(b.series.values) - np.asarray(truth["expected_hB"]))) <= SYN09_TOL
    # Which of the two is steadier on a depth change is a measured outcome, not an assumption (DEC-0014, BUG-0022):
    # nothing here compares range_A with range_B.


@pytest.mark.parametrize("ratio", [1.5, 2.0])
def test_t_met_05_syn09_the_range_of_b_does_not_depend_on_the_height_of_the_camera_a_pinhole_property(ratio):
    ranges = [range_of(syn09(cam, ratio, 1.0)[2]) for cam in (0.6, 1.0, 1.3)]
    assert max(ranges) - min(ranges) <= 0.01  # g - y_H is a height difference: the camera height cancels
