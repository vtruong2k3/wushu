"""T-MET-01d and T-MET-02d: the geometry of the metrics on the generator's scenarios, whose truth is analytic (P5.02).

The truth of ``tests/helpers/synth.py`` comes from the continuous model, never from the sampled output: the trunk is
``scale_px`` long in every frame of SYN-01 to SYN-08, SYN-03 has a known lean ``theta_deg(t)``, and SYN-04 is that
body seen through a camera rolled by ``roll_deg`` with a ``vertical_line`` (top, bottom) that is truly vertical. The
tolerances are those of ``TOLERANCES`` (0.5 degree on the median error of theta at 1 px of noise and 200 px of trunk).
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.synth import TOLERANCES, make_sequence
from taiji_ai.metrics.geometry import (
    bridged,
    lean_angle_deg,
    mid_hip,
    mid_shoulder,
    roll_from_line,
    trunk_length,
    trunk_scale,
    unusable_reason,
)
from taiji_ai.pose.skeleton import IDX
from taiji_ai.quality.chain import run_quality_arrays

THETA_TOL = TOLERANCES["SYN-04"]["median_theta_error_deg"]
NOISE = 1.0  # px: the noise at which the tolerances of the plan hold (200 px of trunk)


# --- T-MET-01d: the scale and the midpoints -------------------------------------------------------------------------
@pytest.mark.parametrize("scenario", ["SYN-01", "SYN-02", "SYN-03", "SYN-04", "SYN-05", "SYN-07"])
@pytest.mark.parametrize("seed", [1, 2])
def test_t_met_01d_the_scale_of_a_sequence_is_its_truth_within_the_noise(scenario: str, seed: int):
    seq = make_sequence(scenario, seed=seed, noise_px=NOISE)
    s = trunk_scale(trunk_length(seq.kp))
    assert s.scale_px == pytest.approx(float(seq.truth["scale_px"]), abs=NOISE) and s.n_rows == len(seq.t_sec)


def test_t_met_01d_the_scale_of_a_clean_sequence_is_exact_and_the_trunk_is_that_long_in_every_row():
    seq = make_sequence("SYN-05", seed=1, noise_px=0.0)
    length = trunk_length(seq.kp)
    assert np.allclose(length, float(seq.truth["scale_px"]), rtol=0, atol=1e-3)  # float32 positions
    assert trunk_scale(length).scale_px == pytest.approx(float(seq.truth["scale_px"]), abs=1e-3)


@pytest.mark.parametrize("noise", [0.0, NOISE])
def test_t_met_01d_the_midpoints_agree_with_the_noise_free_truth_within_the_noise(noise: float):
    seq = make_sequence("SYN-05", seed=3, noise_px=noise)
    bound = 1e-3 if noise == 0.0 else 4.0 * noise  # a mean of two joints: sigma 0.7 px at 1 px of noise
    assert np.abs(mid_hip(seq.kp) - mid_hip(seq.kp_true)).max() <= bound
    assert np.abs(mid_shoulder(seq.kp) - mid_shoulder(seq.kp_true)).max() <= bound


def test_t_met_01d_a_variable_frame_rate_does_not_change_the_scale():
    cfr = trunk_scale(trunk_length(make_sequence("SYN-05", seed=1, noise_px=0.0).kp)).scale_px
    vfr = trunk_scale(trunk_length(make_sequence("SYN-07", seed=1, noise_px=0.0).kp)).scale_px
    assert cfr == pytest.approx(vfr, abs=1e-3)  # the geometry does not look at time


def test_t_met_01d_after_the_quality_chain_a_short_gap_is_bridged_and_reported_and_a_long_one_has_its_reason():
    seq = make_sequence("SYN-06", seed=1, noise_px=0.0)
    short, long = list(seq.truth["gaps"])
    r = run_quality_arrays(seq.kp, seq.score, seq.t_sec)
    kp, reason, interp = r.filtered.keypoints, r.filtered.reason, r.filtered.interpolated
    n = len(seq.t_sec)

    def rows(gap: dict) -> np.ndarray:
        mask = np.zeros(n, bool)
        mask[gap["frames"][0] : gap["frames"][1] + 1] = True
        return mask

    joints = set(short["joints"]) | set(long["joints"])  # the two gaps may be on the same joints
    assert joints, "the scenario has gaps"
    for joint in joints:
        j = IDX[joint]
        expect_bridge = rows(short) if joint in short["joints"] else np.zeros(n, bool)
        expect_code = np.where(rows(long) & (joint in long["joints"]), 2, 0)  # non_finite, only on the long gap
        assert np.array_equal(bridged(kp, interp, [j]), expect_bridge), joint  # exactly the rows of the short gap
        assert np.array_equal(unusable_reason(kp, reason, [j]), expect_code), joint  # a bridge is a value: usable
    assert any(joint in short["joints"] for joint in joints) and any(joint in long["joints"] for joint in joints)
    s = trunk_scale(trunk_length(kp))  # the final layer, filtered: the scale is still the trunk
    assert s.scale_px == pytest.approx(float(seq.truth["scale_px"]), abs=0.5) and s.n_rows > 0.8 * n


# --- T-MET-02d: the lean and the roll -------------------------------------------------------------------------------
@pytest.mark.parametrize("beta", [5.0, -8.0, 30.0, 0.0])
@pytest.mark.parametrize("seed", [1, 2])
def test_t_met_02d_syn04_the_roll_from_the_line_is_beta_and_the_corrected_theta_is_the_body_s(beta: float, seed: int):
    seq = make_sequence("SYN-04", seed=seed, noise_px=NOISE, roll_deg=beta)
    top, bottom = seq.truth["vertical_line"]
    roll = roll_from_line(top, bottom)
    assert roll == pytest.approx(beta, abs=1e-9)
    hip, shoulder = mid_hip(seq.kp), mid_shoulder(seq.kp)
    body = np.asarray(seq.truth["theta_body_deg"])
    corrected = lean_angle_deg(hip, shoulder, roll_deg=roll)
    assert np.median(np.abs(corrected - body)) <= THETA_TOL
    raw = lean_angle_deg(hip, shoulder)  # no correction: what the metric would say without the roll
    assert np.median(np.abs(raw - np.asarray(seq.truth["theta_raw_deg"]))) <= THETA_TOL
    assert np.median(np.abs(raw - body)) == pytest.approx(abs(beta), abs=THETA_TOL)  # off by the roll, as the plan says


def test_t_met_02d_syn04_the_correction_matters_more_than_the_noise():
    seq = make_sequence("SYN-04", seed=3, noise_px=NOISE, roll_deg=30.0)
    hip, shoulder = mid_hip(seq.kp), mid_shoulder(seq.kp)
    body = np.asarray(seq.truth["theta_body_deg"])
    roll = roll_from_line(*seq.truth["vertical_line"])
    wrong = np.median(np.abs(lean_angle_deg(hip, shoulder) - body))
    right = np.median(np.abs(lean_angle_deg(hip, shoulder, roll_deg=roll) - body))
    assert wrong > 25.0 and right < THETA_TOL


@pytest.mark.parametrize("theta", [0.0, 10.0, -7.5])
def test_t_met_02d_syn03_a_constant_lean_is_measured_within_the_tolerance(theta: float):
    seq = make_sequence("SYN-03", seed=2, noise_px=NOISE, theta_deg=theta)
    measured = lean_angle_deg(mid_hip(seq.kp), mid_shoulder(seq.kp))
    assert abs(float(np.median(measured)) - float(seq.truth["median_theta_deg"])) <= THETA_TOL
    assert float(seq.truth["median_theta_deg"]) == pytest.approx(theta)


def test_t_met_02d_syn03_a_lean_that_changes_is_followed_frame_by_frame():
    seq = make_sequence("SYN-03", seed=2, noise_px=NOISE)  # 0 to 15 degrees in 3 s
    measured = lean_angle_deg(mid_hip(seq.kp), mid_shoulder(seq.kp))
    truth = np.asarray(seq.truth["theta_deg"])
    assert np.median(np.abs(measured - truth)) <= THETA_TOL
    assert measured[-1] > measured[0] + 10.0  # and it really leans more at the end


def test_t_met_02d_noise_free_syn04_is_exact_up_to_float32():
    seq = make_sequence("SYN-04", seed=1, noise_px=0.0, roll_deg=-12.0)
    roll = roll_from_line(*seq.truth["vertical_line"])
    corrected = lean_angle_deg(mid_hip(seq.kp), mid_shoulder(seq.kp), roll_deg=roll)
    assert np.abs(corrected - np.asarray(seq.truth["theta_body_deg"])).max() < 0.01  # a pixel of float32 on 200 px
