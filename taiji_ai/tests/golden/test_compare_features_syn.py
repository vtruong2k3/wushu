"""T-CMP-01 on the generator: the frame features of SYN-10 (a query that is the reference under a similarity) and of
SYN-03 (a body whose upper joints are rotated about the mid-hip by a known ``θ(t)``), through the real quality chain
(P6.01).

Every layer is what the pipeline would hand to the comparison: ``run_quality_arrays`` then
``pose_filtered_from_result``. The truth comes from the continuous model of ``tests/helpers/synth.py``: for SYN-10 the
query *is* the reference scaled about its mid-hip and shifted (``k_start = k_end = 1``: the same clock), so the two sets
of features must be equal row by row; for SYN-03 a rotation of the upper body about the mid-hip by ``θ`` turns every
upper position and every upper segment by ``θ`` and leaves the legs alone.

Tolerances were measured before they were set (2026-11-17):

* SYN-10 without noise, ``scale_px`` 120 (the query must stay in the 1920 x 1080 image: a scale of 1.7 does not fit
  the default 200), scales 0.5, 0.8 and 1.7: the largest difference of any feature is 5.8e-5 (scale 0.5, the forearm
  angle at the row where the forearm is 0.02 trunk lengths long: a pixel of float32 storage on a 1.2 px segment), 4.7e-5
  and 1.9e-5; the positions of the reference are the noise-free pose to 3.6e-5 (the low-pass filter of the chain). The
  bound is 2e-4.
* SYN-03: without noise every position and angle is the truth to 4.9e-6 (the bound is 2e-5) and the trunk angle to
  0.00024 degree; at 1 px of noise the median error of a unit over the rows is at most 0.0054 (positions in trunk
  lengths, angles as chords; the bound is 0.01) and the median error of the trunk angle at most 0.14 degree, the
  tolerance of SYN-03 (0.5).
* SYN-04 (a camera rolled by 5, -8 and 30 degrees, the roll read from the plumb line, no noise): every feature equals
  that of the unrolled SYN-03 body to 1.9e-6 (the bound is 1e-5), and without the roll every angle is off by exactly the
  chord of the roll, ``2 sin(β / 2)`` (the bound is 1e-4).
* SYN-10 with ``min_segment_length`` 0.05 (a value chosen for these tests only, R1 of the task file): without noise the
  masks and reasons of the reference and the query are equal (the forearm crosses 0.05 at 0.0480 and 0.0538 trunk
  lengths, far from the float noise), 70 angle cells are cut (35 rows of each forearm) and the largest difference on
  the valid cells is 1.5e-5. At 1 px of noise and ``scale_px`` 120 (seeds 1 to 5) 32 to 36 rows of the left forearm
  are cut in each set (35 are shorter than 0.05 in the truth), the largest forearm chord left is 0.36 (it was up to
  1.0), its median 0.020 to 0.025, the positions still agree to 0.035, at least 19 units of 21 are valid in both of
  every row, and the mean distance over the units valid in both on the diagonal is 0.0124 to 0.0141 (0.0202 to 0.0224
  with every unit and no minimum; 0.0084 to 0.0094 against 0.0130 to 0.0140 at the default ``scale_px`` 200), under
  the 0.02 of ``TOLERANCES["SYN-10"]["shape_distance_max"]``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from helpers.compare_features_ref import TABLE
from helpers.metric_layers import layer_of_sequence
from helpers.synth import TOLERANCES, SynthSequence, make_pair, make_sequence
from taiji_ai.compare.features import FrameFeatures, frame_features
from taiji_ai.metrics.geometry import roll_from_line

TOL_DEG = TOLERANCES["SYN-03"]["median_theta_error_deg"]  # degrees
SIMILARITY_TOL = 2e-4  # trunk lengths or chord, measured 5.8e-5 at the worst
POSE_TOL = 2e-4  # SYN-10 reference against the noise-free pose, measured 3.6e-5 (the filter of the chain)
TRUTH_TOL = 2e-5  # SYN-03 without noise: measured 4.9e-6
NOISE_MEDIAN_TOL = 0.01  # SYN-03 at 1 px: measured 0.0054
ROLL_TOL = 1e-5  # SYN-04 with the roll against the unrolled body: measured 1.9e-6
NO_ROLL_TOL = 1e-4  # SYN-04 without the roll: an angle is off by the chord of the roll
MIN_LENGTH = (
    0.05  # trunk lengths: a value chosen for the tests of the minimum length only (the caller's, AGENTS.md 5.5)
)
SCALE_PX = 120.0
SIMILARITIES = [
    pytest.param(0.5, (40.0, -30.0), id="scale 0.5"),
    pytest.param(0.8, (-120.0, 60.0), id="scale 0.8"),
    pytest.param(1.7, (40.0, -30.0), id="scale 1.7"),
]


def col(f: FrameFeatures, name: str) -> int:
    return [u.name for u in f.units].index(name)


def chords(a: FrameFeatures, b: FrameFeatures) -> np.ndarray:
    """``(N, U)`` the distance between the two features of every row and unit (a chord for an angle)."""
    return np.hypot(*(a.values - b.values).transpose(2, 0, 1))


# --- SYN-10: a similarity -------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("query_scale", "shift"), SIMILARITIES)
def test_t_cmp_01_syn10_a_query_that_is_the_reference_under_a_similarity_has_its_features_row_by_row(
    query_scale, shift
):
    pair = make_pair(
        "SYN-10", seed=1, k_start=1.0, k_end=1.0, query_scale=query_scale, query_shift_px=shift, noise_px=0.0,
        scale_px=SCALE_PX,
    )  # fmt: skip
    ref, qry = frame_features(layer_of_sequence(pair.ref)), frame_features(layer_of_sequence(pair.query))
    assert len(ref.t_sec) == len(qry.t_sec) == 120 and np.array_equal(ref.t_sec, qry.t_sec)  # the same clock
    assert ref.valid.all() and qry.valid.all() and (ref.reason == 0).all() and (qry.reason == 0).all()
    assert not ref.bridged.any() and not qry.bridged.any()
    assert np.abs(ref.values - qry.values).max() < SIMILARITY_TOL
    assert ref.scale_px == pytest.approx(SCALE_PX, abs=1e-3)  # the trunk of the reference, in pixels
    assert qry.scale_px == pytest.approx(SCALE_PX * query_scale, rel=1e-6)  # and of the query: the ratio is the scale
    assert [u.name for u in ref.units] == [u.name for u in qry.units]


def test_t_cmp_01_syn10_the_reference_positions_are_the_truth_of_the_pose_and_not_a_constant():
    pair = make_pair("SYN-10", seed=1, k_start=1.0, k_end=1.0, noise_px=0.0, scale_px=SCALE_PX)
    f = frame_features(layer_of_sequence(pair.ref))
    kt = pair.ref.kp_true.astype(np.float64)  # the noise-free keypoints of the continuous pose function
    hip = (kt[:, 11] + kt[:, 12]) / 2.0
    positions = [i for i, u in enumerate(f.units) if u.kind == "position"]
    want = np.stack([(kt[:, f.units[i].joints[0]] - hip) / SCALE_PX for i in positions], axis=1)
    assert np.abs(f.values[:, positions] - want).max() < POSE_TOL  # measured 3.6e-5: the 6 Hz filter of the chain
    wrist_y = f.values[:, col(f, "LWrist"), 1]
    assert np.ptp(wrist_y) > 1.0 and 55 <= int(np.argmin(wrist_y)) <= 65  # the wrists rise and come back: raise_lower


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_cmp_01_syn10_at_one_pixel_of_noise_a_long_segment_keeps_its_features_and_a_short_one_loses_its_direction(
    seed,
):
    pair = make_pair(
        "SYN-10", seed=seed, k_start=1.0, k_end=1.0, query_scale=1.7, query_shift_px=(40.0, -30.0), noise_px=1.0,
        scale_px=SCALE_PX,
    )  # fmt: skip
    ref, qry = frame_features(layer_of_sequence(pair.ref)), frame_features(layer_of_sequence(pair.query))
    assert ref.valid.all() and qry.valid.all()  # a short segment is NOT marked invalid: only a length of exactly 0 is
    kt = pair.ref.kp_true.astype(np.float64)
    trunk = np.linalg.norm((kt[:, 5] + kt[:, 6]) / 2 - (kt[:, 11] + kt[:, 12]) / 2, axis=1)
    forearm = np.linalg.norm(kt[:, 9] - kt[:, 7], axis=1) / trunk  # the left forearm, in trunk lengths
    short, long_ = forearm < 0.05, forearm > 0.3
    assert short.sum() >= 30 and long_.sum() >= 30  # the generator shrinks the forearm to 0.02 and back
    d = chords(ref, qry)
    positions = [i for i, u in enumerate(ref.units) if u.kind == "position"]
    assert d[:, positions].max() < 0.07  # measured at most 0.035: a position is well defined whatever the segments
    assert np.median(d[long_, col(ref, "l_forearm")]) < 0.05  # measured at most 0.018
    # a direction of a segment of 0.02 trunk lengths (2.4 px at this scale, noise 1 px) is arbitrary but valid:
    # measured median chord 0.215 to 0.317 (two unrelated directions are 1.4 apart on average)
    assert np.median(d[short, col(ref, "l_forearm")]) > 0.1


@pytest.mark.parametrize(("query_scale", "shift"), SIMILARITIES)
def test_t_cmp_01_syn10_with_a_minimum_length_the_similarity_still_matches_row_by_row_and_the_short_forearms_are_cut(
    query_scale, shift
):
    pair = make_pair(
        "SYN-10", seed=1, k_start=1.0, k_end=1.0, query_scale=query_scale, query_shift_px=shift, noise_px=0.0,
        scale_px=SCALE_PX,
    )  # fmt: skip
    ref = frame_features(layer_of_sequence(pair.ref), min_segment_length=MIN_LENGTH)
    qry = frame_features(layer_of_sequence(pair.query), min_segment_length=MIN_LENGTH)
    kt = pair.ref.kp_true.astype(np.float64)
    trunk = np.linalg.norm((kt[:, 5] + kt[:, 6]) / 2 - (kt[:, 11] + kt[:, 12]) / 2, axis=1)
    short = np.linalg.norm(kt[:, 9] - kt[:, 7], axis=1) / trunk < MIN_LENGTH  # the truth: the same for both forearms
    assert np.array_equal(ref.valid, qry.valid) and np.array_equal(ref.reason, qry.reason)  # the same cut
    angles = [i for i, u in enumerate(ref.units) if u.kind == "angle"]
    assert (~ref.valid[:, angles]).sum() == 2 * short.sum()  # both forearms, every row that is short in the truth
    assert np.array_equal(~ref.valid[:, col(ref, "l_forearm")], short)
    assert np.isin(ref.reason[:, angles], (0, 24)).all() and ref.valid[:, :12].all()  # positions are not touched
    both = ref.valid & qry.valid
    assert np.nanmax(np.where(both, chords(ref, qry), np.nan)) < SIMILARITY_TOL


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_t_cmp_01_syn10_at_one_pixel_of_noise_a_minimum_length_cuts_the_unstable_directions_and_the_distance(seed):
    pair = make_pair(
        "SYN-10", seed=seed, k_start=1.0, k_end=1.0, query_scale=1.7, query_shift_px=(40.0, -30.0), noise_px=1.0,
        scale_px=SCALE_PX,
    )  # fmt: skip
    layer_ref, layer_qry = layer_of_sequence(pair.ref), layer_of_sequence(pair.query)
    plain = chords(frame_features(layer_ref), frame_features(layer_qry))  # no minimum: R1
    ref = frame_features(layer_ref, min_segment_length=MIN_LENGTH)
    qry = frame_features(layer_qry, min_segment_length=MIN_LENGTH)
    kt = pair.ref.kp_true.astype(np.float64)
    trunk = np.linalg.norm((kt[:, 5] + kt[:, 6]) / 2 - (kt[:, 11] + kt[:, 12]) / 2, axis=1)
    assert (np.linalg.norm(kt[:, 9] - kt[:, 7], axis=1) / trunk < MIN_LENGTH).sum() == 35  # the truth: 35 short rows
    left = col(ref, "l_forearm")
    for f in (ref, qry):  # measured 32 to 36 of the 35 rows
        assert 30 <= (~f.valid[:, left]).sum() <= 40
        assert np.isin(f.reason[:, 12:], (0, 24)).all() and f.valid[:, :12].all()
    both = ref.valid & qry.valid
    assert both.sum(axis=1).min() >= 15  # measured 19 of 21 units at the worst row
    d = np.where(both, chords(ref, qry), np.nan)
    assert np.nanmax(d[:, left]) < 0.5 and np.nanmedian(d[:, left]) < 0.04  # measured 0.36 at most and 0.025 at most
    diagonal = float((np.nansum(d, axis=1) / both.sum(axis=1)).mean())  # the mean over the units valid in both
    assert diagonal < 0.02  # measured 0.0124 to 0.0141: under TOLERANCES["SYN-10"]["shape_distance_max"]
    assert diagonal < 0.75 * float(plain.mean())  # measured 0.61 to 0.63 of the 0.0202 to 0.0224 without the minimum


# --- SYN-03: a rotation about the mid-hip ---------------------------------------------------------------------------
CASES = [
    pytest.param({"theta_deg": 0.0}, id="upright"),
    pytest.param({"theta_deg": 10.0}, id="10 degrees"),
    pytest.param({"theta_deg": -7.5}, id="-7.5 degrees"),
    pytest.param({}, id="linear 0 to 15"),
]


def neutral_angle_deg(name: str) -> float:
    """The direction of a segment of the upright body (SYN-03 with ``θ = 0``), in degrees (0 up, positive right)."""
    kp = make_sequence("SYN-03", seed=1, noise_px=0.0, theta_deg=0.0).kp_true[0].astype(np.float64)
    proximal, distal = TABLE[name]  # the table of the test, by joint number: not the module's
    start, end = kp[list(proximal)].mean(axis=0), kp[list(distal)].mean(axis=0)
    return math.degrees(math.atan2(end[0] - start[0], -(end[1] - start[1])))


def truth_values(seq: SynthSequence, f: FrameFeatures) -> np.ndarray:
    """``(N, U, 2)`` the features of the continuous model: positions from the noise-free keypoints, angles as the
    neutral direction plus ``θ`` for a segment of the upper body (the arms and the trunk), the neutral one for a leg."""
    theta = np.asarray(seq.truth["theta_deg"], dtype=np.float64)
    scale = float(seq.truth["scale_px"])
    kt = seq.kp_true.astype(np.float64)
    hip = (kt[:, 11] + kt[:, 12]) / 2.0
    out = np.empty((len(theta), len(f.units), 2))
    for u, unit in enumerate(f.units):
        if unit.kind == "position":
            out[:, u] = (kt[:, unit.joints[0]] - hip) / scale
            continue
        if unit.name == "trunk":
            angle = theta
        elif unit.name.endswith(("thigh", "shank")):
            angle = np.full(len(theta), neutral_angle_deg(unit.name))
        else:
            angle = neutral_angle_deg(unit.name) + theta
        out[:, u] = np.stack([np.sin(np.radians(angle)), np.cos(np.radians(angle))], axis=-1)
    return out


@pytest.mark.parametrize("kwargs", CASES)
def test_t_cmp_01_syn03_without_noise_every_unit_is_the_truth_of_the_rotation(kwargs):
    seq = make_sequence("SYN-03", seed=1, noise_px=0.0, **kwargs)
    f = frame_features(layer_of_sequence(seq))
    assert f.valid.all() and len(f.t_sec) == len(seq.truth["theta_deg"])
    assert np.abs(f.values - truth_values(seq, f)).max() < TRUTH_TOL
    assert f.scale_px == pytest.approx(float(seq.truth["scale_px"]), abs=1e-3)


@pytest.mark.parametrize("noise", [0.0, 1.0])
@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("kwargs", CASES)
def test_t_cmp_01_syn03_the_trunk_unit_is_sin_and_cos_of_theta_within_half_a_degree(kwargs, seed, noise):
    seq = make_sequence("SYN-03", seed=seed, noise_px=noise, **kwargs)
    f = frame_features(layer_of_sequence(seq))
    trunk = f.values[:, col(f, "trunk")]
    angle = np.degrees(np.arctan2(trunk[:, 0], trunk[:, 1]))  # sin, cos -> degrees: the trunk lean of B2
    truth = np.asarray(seq.truth["theta_deg"])
    assert f.valid[:, col(f, "trunk")].all()
    assert np.median(np.abs(angle - truth)) <= TOL_DEG
    if noise == 0.0:
        assert np.abs(angle - truth).max() < 0.01  # a pixel of float32 on 150 px, as the trunk lean metric


@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("kwargs", CASES)
def test_t_cmp_01_syn03_at_one_pixel_of_noise_every_unit_is_close_to_the_truth_in_the_median(kwargs, seed):
    seq = make_sequence("SYN-03", seed=seed, noise_px=1.0, **kwargs)
    f = frame_features(layer_of_sequence(seq))
    error = np.hypot(*(f.values - truth_values(seq, f)).transpose(2, 0, 1))  # (N, U)
    assert f.valid.all()
    assert (np.median(error, axis=0) < NOISE_MEDIAN_TOL).all()  # measured at most 0.0054 over the 21 units
    assert error.max() < 0.05  # and the worst row of any unit at most 0.02


def test_t_cmp_01_syn03_the_legs_do_not_move_and_the_arms_and_trunk_turn_with_theta():
    seq = make_sequence("SYN-03", seed=1, noise_px=0.0)  # θ from 0 to 15 degrees
    f = frame_features(layer_of_sequence(seq))
    for name in ("l_thigh", "l_shank", "r_thigh", "r_shank", "LKnee", "RAnkle", "LHip"):
        v = f.values[:, col(f, name)]
        assert np.ptp(v, axis=0).max() < 2 * TRUTH_TOL, name  # the lower body is still
    for name in ("trunk", "l_upper_arm", "r_forearm", "LWrist", "RShoulder"):
        v = f.values[:, col(f, name)]
        assert np.ptp(v, axis=0).max() > 0.1, name  # the upper body turns


# --- SYN-04: a rolled camera -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("beta", [5.0, -8.0, 30.0])
def test_t_cmp_01_syn04_with_the_roll_of_the_plumb_line_the_features_are_the_unrolled_bodys_and_without_it_off(beta):
    body = frame_features(layer_of_sequence(make_sequence("SYN-03", seed=1, noise_px=0.0)))  # the same body, no roll
    seq = make_sequence("SYN-04", seed=1, noise_px=0.0, roll_deg=beta)
    roll = roll_from_line(*seq.truth["vertical_line"])
    assert roll == pytest.approx(beta, abs=1e-9)
    layer = layer_of_sequence(seq)
    right, wrong = frame_features(layer, roll_deg=roll), frame_features(layer)
    assert right.valid.all() and right.roll_deg == roll and wrong.roll_deg == 0.0
    assert chords(right, body).max() < ROLL_TOL
    assert right.scale_px == pytest.approx(float(seq.truth["scale_px"]), abs=1e-3)  # a roll does not change a length
    angles = [i for i, u in enumerate(body.units) if u.kind == "angle"]
    off = chords(wrong, body)[:, angles]  # every direction is turned by the roll: a chord of 2 sin(|β| / 2)
    assert np.abs(off - 2.0 * math.sin(math.radians(abs(beta)) / 2.0)).max() < NO_ROLL_TOL
    assert wrong.scale_px == right.scale_px
