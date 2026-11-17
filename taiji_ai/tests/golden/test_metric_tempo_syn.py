"""T-MET-08 and 08f: the speed of a group of joints on the real clock, on SYN-07 and SYN-05 through the real chain
(P5.06).

The truth of ``tests/helpers/synth.py`` comes from the continuous model: the group speed is the median over the
joints of ``|v| / Λ``, analytic in time, so ``speed_at`` gives it at the times of the uniform grid that a
variable-frame-rate video is resampled to (they are not the frames). SYN-07 is the SYN-05 motion sampled at 30 fps
and then 10 fps; its default has **no noise**, which is the case of the tolerance of the plan (median relative error
of the speed within 5 % on the valid frames). A relative error is undefined at a speed of 0, so the valid frames are
the measured rows whose true speed is at least 10 % of the peak of the group (a definition of the test, not of the
product). Every layer is what the pipeline would hand to the metric: ``run_quality_arrays`` then
``pose_filtered_from_result``.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.synth import TOLERANCES, make_sequence, speed_at
from taiji_ai.metrics.series import MetricResult
from taiji_ai.metrics.tempo import group_speed
from taiji_ai.quality.layers_io import PoseFiltered

TOL = TOLERANCES["SYN-07"]["median_speed_relative_error"]  # 5 %
VALID_FRACTION = 0.10  # a valid frame: the true speed is at least this share of the peak of the group
SCENARIOS = ["SYN-07", "SYN-05"]


def run(layer: PoseFiltered, group: str, **kwargs) -> MetricResult:
    return group_speed(layer, group=group, flags={}, camera_id="camA", view_category="front", **kwargs)


def stat(result: MetricResult, name: str) -> float | None:
    (s,) = [s for s in result.summary.statistics if s.name == name]
    return s.value


def valid_errors(result: MetricResult, truth: np.ndarray) -> np.ndarray:
    """The relative errors of the group speed on the valid frames."""
    measured = np.asarray(result.series.reason) == 0
    valid = measured & (truth >= VALID_FRACTION * truth.max())
    assert valid.sum() > 50, "too few valid frames to say anything"
    return np.abs(np.asarray(result.series.values)[valid] - truth[valid]) / truth[valid]


# --- T-MET-08: the speed on the real clock, noise-free, on a resampled grid ---------------------------------------
@pytest.mark.parametrize("group", ["hands", "hips"])
@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_t_met_08_the_median_relative_error_of_the_group_speed_is_within_five_percent(scenario, seed, group):
    seq = make_sequence(scenario, seed=seed)  # the default of the scenario: no noise
    result = run(layer_of_sequence(seq), group)
    truth = speed_at(seq, np.asarray(result.series.t_sec))[group]
    errors = valid_errors(result, truth)
    assert np.median(errors) <= TOL
    assert (
        np.percentile(errors, 90) <= TOL
    )  # measured about 1 %: the whole bulk of the valid frames, not only the median


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_t_met_08_inside_the_pause_the_speed_is_near_zero_and_a_group_that_does_not_move_reads_zero(scenario):
    seq = make_sequence(scenario, seed=1)
    layer = layer_of_sequence(seq)
    hands = run(layer, "hands")
    truth = speed_at(seq, np.asarray(hands.series.t_sec))["hands"]
    inside = (np.asarray(hands.series.reason) == 0) & (truth == 0.0)
    assert inside.sum() > 5 and np.asarray(hands.series.values)[inside].max() < 0.01  # measured at most 0.0063 Lambda/s
    feet = run(layer, "feet")  # the feet do not move in the generator's motion
    values = np.asarray(feet.series.values)[np.asarray(feet.series.reason) == 0]
    assert len(values) > 50 and np.abs(values).max() < 1e-6


def test_t_met_08_the_series_is_on_the_uniform_grid_and_only_its_two_ends_have_no_neighbour():
    seq = make_sequence("SYN-07", seed=1)  # 30 fps, then 10 fps from 2 s: the video is not uniform
    layer = layer_of_sequence(seq)
    assert layer.meta.timeline.resampled and len(layer.t_grid) > len(seq.t_sec)  # the grid is not the frames
    result = run(layer, "hands")
    series, step = result.series, result.series.header.step_s
    assert step == pytest.approx(1 / 30, rel=1e-6) and len(series.t_sec) == len(layer.t_grid)
    assert np.allclose(np.diff(series.t_sec), step, rtol=0, atol=1e-9)  # the clock of the series is the uniform grid
    reason = np.asarray(series.reason)
    assert reason[0] == 22 and reason[-1] == 22 and set(reason[1:-1].tolist()) == {0}  # the ends of the whole track
    assert series.header.coverage.measured == len(layer.t_grid) - 2
    assert stat(result, "segment_duration_s") == pytest.approx(len(layer.t_grid) * step, rel=1e-9)


# --- T-MET-08f: noise, its floor, and a clip that does not move -----------------------------------------------------
@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_t_met_08f_at_one_pixel_of_noise_a_still_group_reads_a_floor_and_the_fast_group_stays_within_15_percent(
    scenario, seed
):
    # measured on seeds 1 to 3 (section 5 of the task file): the feet, whose true speed is 0, read a median of about
    # 0.07 Lambda/s; the hands, the fast group, a median relative error of 4 to 8 %. The hips move at about 0.05 to 0.1
    # Lambda/s in the generator, as much as the noise: their error is large and is a limit, not asserted here.
    seq = make_sequence(scenario, seed=seed, noise_px=1.0)
    layer = layer_of_sequence(seq)
    feet = run(layer, "feet")
    floor = float(np.median(np.asarray(feet.series.values)[np.asarray(feet.series.reason) == 0]))
    assert 0.02 < floor < 0.15
    hands = run(layer, "hands")
    truth = speed_at(seq, np.asarray(hands.series.t_sec))["hands"]
    assert np.median(valid_errors(hands, truth)) <= 0.15


def test_t_met_08f_a_clip_that_does_not_move_and_has_no_noise_has_a_speed_of_zero_and_no_variation_to_report():
    seq = make_sequence("SYN-01", seed=1, noise_px=0.0)
    layer = layer_of_sequence(seq)
    for group in ("hands", "hips", "feet"):
        result = run(layer, group)
        assert result.summary.evidence == "sufficient" and stat(result, "speed_median") == 0.0
        assert stat(result, "speed_cv") is None  # a mean of 0: null, not 0 and not NaN
        values = np.asarray(result.series.values)[np.asarray(result.series.reason) == 0]
        assert len(values) == len(layer.t_grid) - 2 and (values == 0.0).all()
