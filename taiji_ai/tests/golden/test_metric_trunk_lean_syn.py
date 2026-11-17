"""T-MET-06 and 06f: the trunk lean on the generator's scenarios through the real quality chain (P5.05).

The truth of ``tests/helpers/synth.py`` comes from the continuous model, never from the sampled output. SYN-03 is a body
whose upper joints are rotated about the mid-hip by a known ``theta(t)`` (constant or linear); SYN-04 is that body seen
through a camera rolled by ``beta`` with a plumb line that is truly vertical. The tolerance of the plan is 0.5 degree on
the median error of ``theta`` at noise up to 1 px and a trunk of 200 px ("1 px on 200 px is about 0.4 degree before the
median"). Every layer is what the pipeline would hand to the metric: ``run_quality_arrays`` then
``pose_filtered_from_result``.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.metric_layers import layer_of_sequence
from helpers.synth import TOLERANCES, make_sequence
from taiji_ai.metrics.geometry import roll_from_line
from taiji_ai.metrics.series import MetricResult
from taiji_ai.metrics.trunk_lean import trunk_lean
from taiji_ai.quality.layers_io import PoseFiltered

TOL = TOLERANCES["SYN-03"]["median_theta_error_deg"]  # degrees
CASES = [
    pytest.param({"theta_deg": 0.0}, id="upright"),
    pytest.param({"theta_deg": 10.0}, id="10 degrees"),
    pytest.param({"theta_deg": -7.5}, id="-7.5 degrees"),
    pytest.param({}, id="linear 0 to 15"),
]


def run(layer: PoseFiltered, **kwargs) -> MetricResult:
    args = {"plane": "lr", "view_category": "front", "flags": {}, "camera_id": "camA"}
    args.update(kwargs)
    return trunk_lean(layer, **args)  # type: ignore[arg-type]


def stat(result: MetricResult, name: str) -> float:
    (s,) = [s for s in result.summary.statistics if s.name == name]
    assert s.value is not None
    return s.value


# --- T-MET-06: SYN-03 -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("noise", [0.0, 1.0])
@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("kwargs", CASES)
def test_t_met_06_syn03_the_angle_and_its_statistics_are_the_truth_within_half_a_degree(kwargs, seed, noise):
    seq = make_sequence("SYN-03", seed=seed, noise_px=noise, **kwargs)
    result = run(layer_of_sequence(seq))
    truth = np.asarray(seq.truth["theta_deg"])
    values = np.asarray(result.series.values)
    assert result.series.header.coverage.measured == result.series.header.coverage.total == len(truth)
    assert np.median(np.abs(values - truth)) <= TOL
    assert abs(stat(result, "lean_median") - float(seq.truth["median_theta_deg"])) <= TOL
    assert abs(stat(result, "lean_abs_median") - float(np.median(np.abs(truth)))) <= TOL
    # P95 of |theta| has a floor under it: an upright trunk read at 1 px of noise has a P95 of about 0.3 degree
    assert abs(stat(result, "lean_abs_p95") - float(np.percentile(np.abs(truth), 95))) <= TOL


@pytest.mark.parametrize("kwargs", CASES)
def test_t_met_06_syn03_without_noise_the_angle_is_exact_up_to_float32(kwargs):
    seq = make_sequence("SYN-03", seed=1, noise_px=0.0, **kwargs)
    result = run(layer_of_sequence(seq))
    truth = np.asarray(seq.truth["theta_deg"])
    assert np.abs(np.asarray(result.series.values) - truth).max() < 0.01  # a pixel of float32 on 150 px
    assert abs(stat(result, "lean_median") - float(np.median(truth))) < 0.01
    assert abs(stat(result, "lean_abs_p95") - float(np.percentile(np.abs(truth), 95))) < 0.01


def test_t_met_06_syn03_the_two_planes_give_the_same_angle_on_the_views_that_fit_them():
    seq = make_sequence("SYN-03", seed=1, noise_px=1.0)
    layer = layer_of_sequence(seq)
    lr = run(layer, plane="lr", view_category="front")
    fb = run(layer, plane="fb", view_category="side")
    assert np.array_equal(lr.series.values, fb.series.values)
    assert (lr.summary.metric_name, fb.summary.metric_name) == ("trunk_lean_lr", "trunk_lean_fb")


def test_t_met_07_syn03_a_view_that_does_not_fit_gives_no_number_whatever_the_quality_of_the_data():
    layer = layer_of_sequence(make_sequence("SYN-03", seed=1, noise_px=0.0, theta_deg=10.0))  # a perfect segment
    for view in ("side", "oblique", "back", "unknown"):
        result = run(layer, view_category=view)
        assert (
            result.summary.evidence == "insufficient_evidence"
            and result.summary.insufficient_reason == "view_not_supported"
        )
        assert all(s.value is None for s in result.summary.statistics) and np.isnan(result.series.values).all()


# --- T-MET-06f: SYN-04 and a variable frame rate ----------------------------------------------------------------------
@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("beta", [5.0, -8.0, 30.0])
def test_t_met_06f_syn04_with_the_roll_from_the_plumb_line_the_angle_is_the_body_s_and_without_it_off_by_the_roll(
    beta, seed
):
    seq = make_sequence("SYN-04", seed=seed, noise_px=1.0, roll_deg=beta)
    roll = roll_from_line(*seq.truth["vertical_line"])
    assert roll == pytest.approx(beta, abs=1e-9)
    layer = layer_of_sequence(seq)
    body = np.asarray(seq.truth["theta_body_deg"])
    right = np.asarray(run(layer, roll_deg=roll).series.values)
    wrong = np.asarray(run(layer).series.values)  # the roll is not taken out
    assert np.median(np.abs(right - body)) <= TOL
    assert abs(float(np.median(np.abs(wrong - body))) - abs(beta)) <= TOL
    assert abs(stat(run(layer, roll_deg=roll), "lean_median") - float(np.median(body))) <= TOL


def test_t_met_06f_a_variable_frame_rate_gives_a_series_on_the_uniform_grid_not_on_the_frames():
    seq = make_sequence("SYN-07", seed=1, noise_px=1.0)  # SYN-05 motion at variable-frame-rate timestamps
    layer = layer_of_sequence(seq)
    assert layer.meta.timeline.resampled and len(layer.t_grid) > len(seq.t_sec)  # the grid is not the frames
    result = run(layer)
    series, step = result.series, result.series.header.step_s
    assert step == pytest.approx(1 / 30, rel=1e-6) and len(series.t_sec) == len(layer.t_grid)
    assert np.allclose(np.diff(series.t_sec), step, rtol=0, atol=1e-9)  # the clock of the series is the uniform grid
    assert series.header.coverage.measured == series.header.coverage.total == len(layer.t_grid)
    assert np.isfinite(series.values).all() and result.summary.evidence == "sufficient"
