"""T-MET-01a..c, T-MET-02a..c and 02e: the geometry that every metric starts from (``metrics/geometry.py``, P5.02).

Arrays are made by hand with numbers that can be checked on paper; the generator's scenarios are in
``tests/golden/test_metric_geometry_syn.py``. Pixels of the upright image, x right, y down; angles in degrees with the sign
of Appendix B2 (0 is vertical, positive leans to the image right).
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pytest

from helpers.quality_fixtures import build_f1
from helpers.synth import apply_roll, make_sequence
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.geometry import (
    HIP_JOINTS,
    MAX_ROLL_DEG,
    SHOULDER_JOINTS,
    TrunkScale,
    bridged,
    correct_roll,
    lean_angle_deg,
    mid_hip,
    mid_shoulder,
    midpoint,
    roll_from_line,
    trunk_length,
    trunk_scale,
    unusable_reason,
)
from taiji_ai.pose.skeleton import IDX, NUM_JOINTS
from taiji_ai.quality.filters import torso_length_px
from taiji_ai.quality.mask import apply_mask

LS, RS, LH, RH = IDX["LShoulder"], IDX["RShoulder"], IDX["LHip"], IDX["RHip"]


def blank(n: int, dtype=np.float32) -> np.ndarray:
    return np.full((n, NUM_JOINTS, 2), np.nan, dtype=dtype)


def torso(n: int, hip=(100.0, 200.0), shoulder=(100.0, 100.0), half=10.0, dtype=np.float32) -> np.ndarray:
    """``n`` rows with the four torso joints: hips at ``hip`` +- (half, 0), shoulders at ``shoulder`` +- (half, 0)."""
    kp = blank(n, dtype)
    kp[:, LH], kp[:, RH] = (hip[0] - half, hip[1]), (hip[0] + half, hip[1])
    kp[:, LS], kp[:, RS] = (shoulder[0] - half, shoulder[1]), (shoulder[0] + half, shoulder[1])
    return kp


# --- T-MET-01a: midpoints ------------------------------------------------------------------------------------------------
def test_t_met_01a_the_middle_of_the_hips_and_of_the_shoulders_are_the_means_of_their_two_joints():
    kp = blank(3)
    kp[0, LS], kp[0, RS], kp[0, LH], kp[0, RH] = (10, 20), (30, 40), (100, 200), (120, 220)
    kp[1, LS], kp[1, RS], kp[1, LH], kp[1, RH] = (10, 20), (np.nan, np.nan), (100, 200), (120, 220)
    kp[2, LS], kp[2, RS], kp[2, LH], kp[2, RH] = (0, 0), (-4, 8), (50, 60), (52, 64)
    hip, shoulder = mid_hip(kp), mid_shoulder(kp)
    assert np.allclose(hip[[0, 1, 2]], [[110, 210], [110, 210], [51, 62]])
    assert np.allclose(shoulder[0], [20, 30]) and np.isnan(shoulder[1]).all() and np.allclose(shoulder[2], [-2, 4])
    assert HIP_JOINTS == (11, 12) and SHOULDER_JOINTS == (5, 6)  # Appendix B: not the model's own Hip (19) and Neck (18)
    assert np.allclose(midpoint(kp, [LS, RS, LH, RH])[0], [65, 120])  # any list of joints


def test_t_met_01a_the_model_s_own_hip_and_neck_joints_are_not_used():
    kp = torso(2)
    kp[:, IDX["Hip"]] = (999.0, 999.0)
    kp[:, IDX["Neck"]] = (-999.0, -999.0)
    assert np.allclose(mid_hip(kp), [[100, 200]] * 2) and np.allclose(mid_shoulder(kp), [[100, 100]] * 2)


def test_t_met_01a_a_missing_joint_makes_its_own_row_nan_and_no_other():
    kp = torso(5)
    kp[1, LH] = np.nan
    kp[3, RS] = np.nan
    assert np.isnan(mid_hip(kp)[1]).all() and np.isfinite(mid_hip(kp)[[0, 2, 3, 4]]).all()
    assert np.isnan(mid_shoulder(kp)[3]).all() and np.isfinite(mid_shoulder(kp)[[0, 1, 2, 4]]).all()


def test_t_met_01a_float32_in_float64_out_new_read_only_arrays_and_the_input_is_untouched():
    kp = torso(4, hip=(100.1, 200.3))
    before = kp.copy()
    out = mid_hip(kp)
    assert out.dtype == np.float64 and out.shape == (4, 2)
    assert np.array_equal(kp, before, equal_nan=True) and not np.shares_memory(out, kp)
    assert not out.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        out[0, 0] = 0.0
    assert out[0, 0] == pytest.approx(float(np.float32(100.1) - np.float32(10.0)) / 2 + float(np.float32(100.1) + np.float32(10.0)) / 2)


def test_t_met_01a_no_rows_give_no_rows():
    kp = blank(0)
    assert mid_hip(kp).shape == (0, 2) and mid_shoulder(kp).shape == (0, 2) and trunk_length(kp).shape == (0,)


@pytest.mark.parametrize(
    "joints", [[], [26], [-1], [5, 5], [True, 6], [1.5], "ab", None, [[5, 6]], [np.int64(5), 26]]
)
def test_t_met_01a_bad_joint_lists_are_refused_naming_the_argument(joints: Any):
    with pytest.raises(MetricError, match="joints"):
        midpoint(torso(2), joints)


@pytest.mark.parametrize(
    ("kp", "message"),
    [
        (np.zeros((3, NUM_JOINTS, 2), dtype=np.int32), "keypoints"),  # an integer array cannot hold NaN
        (np.zeros((3, 25, 2), dtype=np.float32), "keypoints"),
        (np.zeros((3, NUM_JOINTS, 3), dtype=np.float32), "keypoints"),
        (np.zeros((NUM_JOINTS, 2), dtype=np.float32), "keypoints"),
        (np.full((3, NUM_JOINTS, 2), np.inf, dtype=np.float32), "infinite"),
        ([[0.0]], "keypoints"),
    ],
)
def test_t_met_01a_a_bad_keypoint_array_is_refused_naming_the_argument(kp: Any, message: str):
    with pytest.raises(MetricError, match=message):
        mid_hip(kp)


# --- T-MET-01b: which joint has no value, and which rows lean on a bridge ----------------------------------------------------
def layer(n: int = 4):
    """A final layer of ``n`` rows, every joint observed; the tests then take cells away."""
    kp = np.zeros((n, NUM_JOINTS, 2), dtype=np.float32) + np.arange(NUM_JOINTS, dtype=np.float32)[None, :, None]
    return kp, np.zeros((n, NUM_JOINTS), np.uint8), np.zeros((n, NUM_JOINTS), bool)


def drop(kp, reason, row: int, joint: int, code: int) -> None:
    kp[row, joint] = np.nan
    reason[row, joint] = code


def test_t_met_01b_every_joint_has_a_value_means_reason_zero():
    kp, reason, _ = layer()
    assert not unusable_reason(kp, reason, [LH, RH, LS, RS]).any()


def test_t_met_01b_the_reason_is_that_of_the_first_unusable_joint_of_the_list():
    kp, reason, _ = layer()
    drop(kp, reason, 1, LH, 1)  # low_conf
    drop(kp, reason, 1, RH, 5)  # outlier
    drop(kp, reason, 2, RS, 6)  # no_frame
    drop(kp, reason, 2, LS, 3)  # not_tracked
    assert unusable_reason(kp, reason, [LH, RH]).tolist() == [0, 1, 0, 0]
    assert unusable_reason(kp, reason, [RH, LH]).tolist() == [0, 5, 0, 0]  # the order of the list decides
    assert unusable_reason(kp, reason, [LS, RS]).tolist() == [0, 0, 3, 0]
    assert unusable_reason(kp, reason, [RS, LS]).tolist() == [0, 0, 6, 0]
    assert unusable_reason(kp, reason, [LH, RH, LS, RS]).tolist() == [0, 1, 3, 0]
    assert unusable_reason(kp, reason, [LH, RH, LS, RS]).dtype == np.uint8


@pytest.mark.parametrize("code", [1, 2, 3, 4, 5, 6])
def test_t_met_01b_every_reason_of_the_quality_layer_comes_through_with_its_own_number(code: int):
    kp, reason, _ = layer(2)
    drop(kp, reason, 1, LH, code)
    assert unusable_reason(kp, reason, [LH]).tolist() == [0, code]


def test_t_met_01b_a_bridged_cell_has_a_value_and_so_it_is_usable_and_reported():
    kp, reason, interp = layer()
    reason[1, LH], interp[1, LH] = 1, True  # a short gap that was bridged: a value, a reason, the flag
    reason[3, RS], interp[3, RS] = 5, True
    assert not unusable_reason(kp, reason, [LH, RH, LS, RS]).any()
    assert bridged(kp, interp, [LH, RH]).tolist() == [False, True, False, False]
    assert bridged(kp, interp, [LS, RS]).tolist() == [False, False, False, True]
    assert bridged(kp, interp, [LH, RH, LS, RS]).tolist() == [False, True, False, True]
    assert bridged(kp, interp, [RH, LS]).tolist() == [False, False, False, False]  # the flags are on other joints


def test_t_met_01b_a_flag_on_a_cell_that_has_no_value_is_refused():
    kp, reason, interp = layer()
    drop(kp, reason, 1, LH, 2)
    interp[1, LH] = True
    with pytest.raises(MetricError, match="interpolated"):
        bridged(kp, interp, [LH])


UNUSABLE_BAD = [
    ("NaN where the reason is ok", lambda kp, r: kp.__setitem__((1, LH), np.nan), "reason"),
    ("a NaN whose reason is not a quality reason", lambda kp, r: (kp.__setitem__((1, LH), np.nan), r.__setitem__((1, LH), 16)), "reason"),
    ("half a cell", lambda kp, r: (kp.__setitem__((1, LH, 0), np.nan), r.__setitem__((1, LH), 1)), "keypoints"),
    ("an infinity", lambda kp, r: kp.__setitem__((1, LH, 0), np.inf), "infinite"),
]


@pytest.mark.parametrize(("name", "damage", "message"), UNUSABLE_BAD, ids=[b[0] for b in UNUSABLE_BAD])
def test_t_met_01b_a_layer_that_breaks_the_contract_is_refused_naming_the_argument(name, damage, message):
    kp, reason, _ = layer()
    damage(kp, reason)
    with pytest.raises(MetricError, match=message):
        unusable_reason(kp, reason, [LH, RH])


def test_t_met_01b_the_arrays_must_have_the_shapes_and_dtypes_of_a_layer():
    kp, reason, interp = layer()
    with pytest.raises(MetricError, match="reason"):
        unusable_reason(kp, reason.astype(np.int64), [LH])
    with pytest.raises(MetricError, match="reason"):
        unusable_reason(kp, reason[:-1], [LH])
    with pytest.raises(MetricError, match="interpolated"):
        bridged(kp, interp.astype(np.uint8), [LH])
    with pytest.raises(MetricError, match="interpolated"):
        bridged(kp, interp[:, :25], [LH])
    with pytest.raises(MetricError, match="joints"):
        unusable_reason(kp, reason, [])


# --- T-MET-01c: the trunk and its scale --------------------------------------------------------------------------------------
def test_t_met_01c_the_length_is_the_distance_from_the_middle_of_the_hips_to_the_middle_of_the_shoulders():
    kp = torso(3, hip=(100.0, 200.0), shoulder=(100.0, 100.0))
    kp[1, [LS, RS]] += (30.0, 0.0)  # the shoulders move 30 px right: 100 px up and 30 across
    kp[2, [LS, RS]] += (0.0, 60.0)  # and 60 px down: a shorter trunk
    assert trunk_length(kp) == pytest.approx([100.0, math.hypot(30.0, 100.0), 40.0])
    assert trunk_length(kp).dtype == np.float64


def test_t_met_01c_a_missing_midpoint_and_a_distance_of_zero_are_nan_not_zero():
    kp = torso(4, hip=(100.0, 200.0), shoulder=(100.0, 100.0))
    kp[1, RH] = np.nan
    kp[2, [LS, RS]] = kp[2, [LH, RH]]  # the shoulders on the hips: not a trunk
    length = trunk_length(kp)
    assert length[0] == pytest.approx(100.0) and length[3] == pytest.approx(100.0)
    assert np.isnan(length[1]) and np.isnan(length[2])


def test_t_met_01c_the_scale_is_the_median_of_the_finite_lengths_for_an_odd_and_an_even_count():
    assert trunk_scale(np.array([3.0, 1.0, 2.0])) == TrunkScale(scale_px=2.0, n_rows=3)
    assert trunk_scale(np.array([4.0, 1.0, 3.0, 2.0])) == TrunkScale(scale_px=2.5, n_rows=4)
    assert trunk_scale(np.array([7.0])) == TrunkScale(scale_px=7.0, n_rows=1)


def test_t_met_01c_nan_and_zero_are_ignored_and_the_count_says_how_many_rows_gave_the_scale():
    s = trunk_scale(np.array([np.nan, 10.0, np.nan, 20.0, 0.0, 30.0, -1.0]))
    assert s.scale_px == 20.0 and s.n_rows == 3


def test_t_met_01c_a_few_wild_rows_do_not_move_the_median():
    length = np.r_[np.full(50, 200.0), [2000.0, 1.0, 5000.0]]
    assert trunk_scale(length).scale_px == 200.0


def test_t_met_01c_the_rows_given_are_the_rows_that_count():
    length = np.array([100.0, 100.0, 100.0, 300.0, 300.0, 300.0, 300.0])
    assert trunk_scale(length).scale_px == 300.0  # all rows
    assert trunk_scale(length, rows=np.array([1, 1, 1, 0, 0, 0, 0], dtype=bool)) == TrunkScale(100.0, 3)
    assert trunk_scale(length, rows=np.array([0, 0, 0, 1, 1, 0, 0], dtype=bool)) == TrunkScale(300.0, 2)


def test_t_met_01c_no_valid_row_gives_nan_and_zero_rows_never_a_guess():
    for length, rows in (
        (np.array([np.nan, np.nan]), None),
        (np.array([]), None),
        (np.array([5.0, 6.0]), np.array([False, False])),
        (np.array([np.nan, 5.0]), np.array([True, False])),
        (np.array([0.0, 0.0]), None),
    ):
        s = trunk_scale(length, rows=rows)
        assert math.isnan(s.scale_px) and s.n_rows == 0


def test_t_met_01c_the_scale_is_a_frozen_pair():
    s = TrunkScale(scale_px=1.0, n_rows=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.scale_px = 2.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("length", "rows", "message"),
    [
        (np.array([1, 2, 3]), None, "length"),  # integers
        (np.zeros((2, 2)), None, "length"),
        (np.array([1.0, 2.0]), np.array([1, 0]), "rows"),  # not bool
        (np.array([1.0, 2.0]), np.array([True]), "rows"),
        (np.array([np.inf, 2.0]), None, "infinite"),
    ],
)
def test_t_met_01c_bad_arguments_are_refused_naming_them(length, rows, message: str):
    with pytest.raises(MetricError, match=message):
        trunk_scale(length, rows=rows)


def test_t_met_01c_the_scale_of_a_layer_is_the_scale_of_the_quality_stage_on_a_layer_without_a_bridge():
    """One definition, two doors: ``quality.torso_length_px`` (mask layer) and ``trunk_scale`` (final layer) agree."""
    t, kp, score, tracked, _ = build_f1()
    f1 = apply_mask(kp, score, tracked)
    seq = make_sequence("SYN-03", seed=2, noise_px=1.0)
    syn = apply_mask(seq.kp, seq.score)
    for mask in (f1, syn):
        want = torso_length_px(mask.keypoints, mask.reason)
        got = trunk_scale(trunk_length(mask.keypoints))
        assert got.scale_px == pytest.approx(want, rel=1e-12) and got.n_rows > 0


# --- T-MET-02a: the roll from the user's line --------------------------------------------------------------------------------
def line_at(beta_deg: float, centre=(960.0, 540.0), half=200.0):
    """A line through ``centre`` that leans by ``beta_deg`` from the vertical: (top, bottom), the top to the right if beta > 0."""
    b = math.radians(beta_deg)
    dx, dy = half * math.sin(b), half * math.cos(b)
    return (centre[0] + dx, centre[1] - dy), (centre[0] - dx, centre[1] + dy)


@pytest.mark.parametrize("beta", [0.0, 5.0, -12.5, 30.0, -44.0, 45.0, -45.0, 0.001])
def test_t_met_02a_the_roll_is_the_angle_of_the_line_from_the_vertical_with_the_sign_of_theta(beta: float):
    top, bottom = line_at(beta)
    assert roll_from_line(top, bottom) == pytest.approx(beta, abs=1e-9)


def test_t_met_02a_the_order_of_the_two_points_and_the_length_of_the_line_do_not_matter():
    top, bottom = line_at(7.0)
    assert roll_from_line(bottom, top) == pytest.approx(roll_from_line(top, bottom), abs=1e-12)
    short_top, short_bottom = line_at(7.0, half=3.0)
    assert roll_from_line(short_top, short_bottom) == pytest.approx(7.0, abs=1e-9)
    assert roll_from_line(np.array(top), np.array(bottom)) == pytest.approx(7.0, abs=1e-9)  # arrays or tuples


def test_t_met_02a_a_line_that_leans_right_has_a_positive_roll_and_one_that_leans_left_a_negative_one():
    assert roll_from_line((110.0, 0.0), (100.0, 100.0)) > 0.0  # the top is to the right of the bottom
    assert roll_from_line((90.0, 0.0), (100.0, 100.0)) < 0.0
    assert roll_from_line((100.0, 0.0), (100.0, 100.0)) == 0.0


ROLL_BAD = [
    ((100.0, 50.0), (100.0, 50.0), "line"),  # a point
    ((100.0, 50.0), (200.0, 50.0), "line"),  # horizontal
    ((np.nan, 0.0), (100.0, 100.0), "line"),
    ((0.0, np.inf), (100.0, 100.0), "line"),
    ((100.0, 0.0), (100.0, 100.0, 5.0), "bottom"),
    ((100.0, 0.0), "ab", "bottom"),
    ((100.0 + 101.0, 0.0), (100.0, 100.0), "45"),  # 45.2 degrees
    ((100.0 - 150.0, 0.0), (100.0, 100.0), "45"),  # 56 degrees
    ((300.0, 90.0), (100.0, 100.0), "45"),  # almost horizontal
]


@pytest.mark.parametrize(("top", "bottom", "message"), ROLL_BAD)
def test_t_met_02a_a_degenerate_or_too_tilted_line_is_refused_naming_the_reason(top, bottom, message: str):
    with pytest.raises(MetricError, match=message):
        roll_from_line(top, bottom)


def test_t_met_02a_the_limit_is_forty_five_degrees():
    assert MAX_ROLL_DEG == 45.0


# --- T-MET-02b: taking the roll out of the coordinates -----------------------------------------------------------------------
def test_t_met_02b_a_roll_of_zero_changes_nothing():
    p = np.random.default_rng(1).uniform(-500, 500, (7, 2))
    assert np.array_equal(correct_roll(p, 0.0), p)
    assert np.array_equal(correct_roll(p, 0.0, origin=(30.0, -20.0)), p - (30.0, -20.0))  # only the origin moves them


@pytest.mark.parametrize("beta", [5.0, -12.5, 30.0, 45.0])
def test_t_met_02b_the_rotation_keeps_every_distance(beta: float):
    p = np.random.default_rng(2).uniform(0, 1000, (30, 2))
    q = correct_roll(p, beta)
    assert np.allclose(np.linalg.norm(q[1:] - q[:-1], axis=1), np.linalg.norm(p[1:] - p[:-1], axis=1), rtol=0, atol=1e-9)


@pytest.mark.parametrize("beta", [5.0, -12.5, 30.0])
def test_t_met_02b_the_line_that_gave_the_roll_is_vertical_after_the_correction(beta: float):
    top, bottom = line_at(beta)
    roll = roll_from_line(top, bottom)
    t2, b2 = correct_roll(np.array([top, bottom]), roll)
    assert t2[0] == pytest.approx(b2[0], abs=1e-9) and t2[1] < b2[1]  # the same x, the top still above the bottom


@pytest.mark.parametrize("beta", [5.0, -12.5, 30.0, 45.0, -45.0])
def test_t_met_02b_it_undoes_the_rotation_of_the_generator_exactly(beta: float):
    """``apply_roll`` of the generator is independent code with the sign of theta: the correction inverts it."""
    centre = (960.0, 540.0)
    p = np.random.default_rng(3).uniform(0, 1000, (40, 2))
    back = correct_roll(apply_roll(p, beta, centre), beta, origin=centre)
    assert np.allclose(back, p - centre, rtol=0, atol=1e-9)


def test_t_met_02b_a_different_origin_only_shifts_the_result_by_a_constant():
    p = np.random.default_rng(4).uniform(0, 1000, (20, 2))
    a = correct_roll(p, 17.0, origin=(0.0, 0.0))
    b = correct_roll(p, 17.0, origin=(300.0, -80.0))
    shift = a - b
    assert np.allclose(shift, shift[0], rtol=0, atol=1e-9)
    assert np.allclose(np.ptp(a[:, 1]), np.ptp(b[:, 1]), rtol=1e-12)  # the range of a height does not depend on it


def test_t_met_02b_any_leading_shape_nan_stays_nan_and_the_input_is_kept():
    kp = torso(5)
    before = kp.copy()
    out = correct_roll(kp, 10.0)
    assert out.shape == kp.shape and out.dtype == np.float64 and np.isnan(out[0, 0]).all()
    assert np.array_equal(kp, before, equal_nan=True) and not out.flags.writeable
    assert correct_roll(np.array([1.0, 2.0]), 3.0).shape == (2,)


@pytest.mark.parametrize(
    ("points", "roll", "origin", "message"),
    [
        (np.zeros((3, 3)), 5.0, (0.0, 0.0), "points"),
        (np.zeros((3, 2), dtype=np.int64), 5.0, (0.0, 0.0), "points"),
        (np.array([[np.inf, 0.0]]), 5.0, (0.0, 0.0), "points"),
        (np.zeros((3, 2)), 45.5, (0.0, 0.0), "roll_deg"),
        (np.zeros((3, 2)), -46.0, (0.0, 0.0), "roll_deg"),
        (np.zeros((3, 2)), float("nan"), (0.0, 0.0), "roll_deg"),
        (np.zeros((3, 2)), True, (0.0, 0.0), "roll_deg"),
        (np.zeros((3, 2)), "5", (0.0, 0.0), "roll_deg"),
        (np.zeros((3, 2)), 5.0, (np.nan, 0.0), "origin"),
        (np.zeros((3, 2)), 5.0, (0.0,), "origin"),
    ],
)
def test_t_met_02b_bad_arguments_are_refused_naming_them(points, roll, origin, message: str):
    with pytest.raises(MetricError, match=message):
        correct_roll(points, roll, origin=origin)


# --- T-MET-02c: the lean angle ------------------------------------------------------------------------------------------------
def pair(*hip_shoulder: tuple[tuple[float, float], tuple[float, float]]):
    hip = np.array([h for h, _ in hip_shoulder], dtype=np.float64)
    shoulder = np.array([s for _, s in hip_shoulder], dtype=np.float64)
    return hip, shoulder


def test_t_met_02c_the_angle_is_zero_when_vertical_and_positive_when_the_top_leans_to_the_image_right():
    hip, shoulder = pair(
        ((100, 200), (100, 100)),  # vertical
        ((100, 200), (200, 100)),  # the shoulders 100 px to the right and 100 up: +45
        ((100, 200), (0, 100)),  # to the left: -45
        ((100, 200), (200, 200)),  # level to the right: +90
        ((100, 200), (100, 300)),  # upside down: 180
    )
    assert lean_angle_deg(hip, shoulder).tolist() == pytest.approx([0.0, 45.0, -45.0, 90.0, 180.0], abs=1e-12)


def test_t_met_02c_the_angle_is_the_formula_of_appendix_b2():
    rng = np.random.default_rng(5)
    hip, shoulder = rng.uniform(0, 1000, (30, 2)), rng.uniform(0, 1000, (30, 2))
    want = np.degrees(np.arctan2(shoulder[:, 0] - hip[:, 0], hip[:, 1] - shoulder[:, 1]))
    assert np.allclose(lean_angle_deg(hip, shoulder), want, rtol=0, atol=1e-12)


def test_t_met_02c_the_roll_is_subtracted_and_the_result_is_wrapped_to_minus_180_exclusive_180_inclusive():
    hip, shoulder = pair(((0, 0), (math.sin(math.radians(20)), -math.cos(math.radians(20)))))
    assert lean_angle_deg(hip, shoulder, roll_deg=5.0)[0] == pytest.approx(15.0, abs=1e-12)
    assert lean_angle_deg(hip, shoulder, roll_deg=-5.0)[0] == pytest.approx(25.0, abs=1e-12)
    far, far_s = pair(((0, 0), (math.sin(math.radians(-178)), -math.cos(math.radians(-178)))))
    assert lean_angle_deg(far, far_s, roll_deg=5.0)[0] == pytest.approx(177.0, abs=1e-9)  # -183 wraps to 177
    down_h, down_s = pair(((0, 0), (0, 1)))  # exactly upside down: +180, not -180
    assert lean_angle_deg(down_h, down_s)[0] == 180.0


def test_t_met_02c_a_missing_midpoint_and_coincident_midpoints_give_nan_not_a_guess():
    hip, shoulder = pair(((100, 200), (100, 100)), ((100, 200), (np.nan, 100)), ((np.nan, 200), (100, 100)), ((7, 7), (7, 7)))
    out = lean_angle_deg(hip, shoulder)
    assert out[0] == 0.0 and np.isnan(out[1:]).all()


def test_t_met_02c_the_arrays_have_two_columns_and_the_same_rows_and_the_roll_is_limited():
    hip, shoulder = pair(((0, 0), (0, -1)))
    with pytest.raises(MetricError, match="mid_shoulder"):
        lean_angle_deg(hip, np.zeros((2, 2)))
    with pytest.raises(MetricError, match="mid_hip"):
        lean_angle_deg(np.zeros((1, 3)), shoulder)
    with pytest.raises(MetricError, match="mid_hip"):
        lean_angle_deg(np.zeros((1, 2), dtype=np.int64), shoulder)
    with pytest.raises(MetricError, match="roll_deg"):
        lean_angle_deg(hip, shoulder, roll_deg=60.0)
    with pytest.raises(MetricError, match="roll_deg"):
        lean_angle_deg(hip, shoulder, roll_deg=float("nan"))
    assert lean_angle_deg(np.zeros((0, 2)), np.zeros((0, 2))).shape == (0,)


# --- T-MET-02e: a rotation and a shift change what they should and nothing else ---------------------------------------------
def wrap(angle: np.ndarray) -> np.ndarray:
    w = (angle + 180.0) % 360.0 - 180.0
    return np.where(w == -180.0, 180.0, w)


@pytest.mark.parametrize("seed", range(200))
def test_t_met_02e_a_rotation_shifts_theta_by_the_roll_and_leaves_the_scale_alone(seed: int):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(2, 25))
    kp = torso(n, hip=tuple(rng.uniform(300, 1500, 2)), shoulder=tuple(rng.uniform(100, 900, 2)), half=float(rng.uniform(5, 60)), dtype=np.float64)
    kp[..., :] += rng.normal(0.0, 3.0, kp.shape)  # a trunk that is not the same in every row
    kp[rng.random(n) < 0.2, LH] = np.nan  # some rows without a hip
    beta = float(rng.uniform(-45.0, 45.0))
    centre = tuple(rng.uniform(0.0, 1500.0, 2))
    shift = rng.uniform(-300.0, 300.0, 2)
    rotated = apply_roll(kp, beta, centre) + shift  # a camera rolled by beta about a point, then the image moved
    theta = lean_angle_deg(mid_hip(kp), mid_shoulder(kp))
    raw = lean_angle_deg(mid_hip(rotated), mid_shoulder(rotated))
    assert np.allclose(np.nan_to_num(wrap(raw - theta - beta), nan=0.0), 0.0, atol=1e-8)  # raw = theta + beta
    corrected = lean_angle_deg(mid_hip(rotated), mid_shoulder(rotated), roll_deg=beta)
    assert np.allclose(corrected, theta, rtol=0, atol=1e-8, equal_nan=True)
    assert np.array_equal(np.isnan(raw), np.isnan(theta))
    assert trunk_scale(trunk_length(rotated)).scale_px == pytest.approx(trunk_scale(trunk_length(kp)).scale_px, rel=1e-9)
    assert trunk_scale(trunk_length(rotated)).n_rows == trunk_scale(trunk_length(kp)).n_rows
