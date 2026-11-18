"""T-CMP-01a to 01i: the frame features of the comparison with a reference (P6.01, Appendix C.1, W8).

Every expected number is re-derived with plain loops, ``math.atan2`` and ``statistics.median`` from the arrays of the
layer that the module reads (``helpers/compare_features_ref.py``, never the module's own helpers or tables): a position
is ``(p_j - H) / Λ`` in trunk lengths, an angle is ``(sin φ, cos φ)`` with ``φ = atan2(dx, -dy)`` (0 is up, positive
toward the image right, y down), ``H`` is the middle of the hips and ``Λ`` the median trunk length of the rows of the
segment (never per frame). The other tests build their layers so that the answer is known by construction (an angle
asked for, a body scaled or rotated, one row scaled).
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np
import pytest

from helpers.compare_features_ref import (
    JOINTS12,
    SEGMENTS9,
    TABLE,
    expected_features,
    expected_reasons,
    length_ratios,
    trunk_scale_of,
)
from helpers.metric_layers import (
    OTHER_RECORDING_ID,
    OTHER_SOURCES,
    RECORDING_ID,
    SOURCES,
    body,
    bridge,
    cells,
    drop,
    edited,
    exact_layer,
)
from taiji_ai.compare import CompareError
from taiji_ai.compare.features import (
    DEFAULT_JOINTS,
    DEFAULT_SEGMENTS,
    FEATURE_VERSION,
    SEGMENTS,
    FeatureReason,
    FeatureUnit,
    FrameFeatures,
    frame_features,
)
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.geometry import lean_angle_deg, mid_hip, mid_shoulder
from taiji_ai.pose.skeleton import IDX
from taiji_ai.quality.layers_io import PoseFiltered
from taiji_ai.schemas.metric import MissingReason

G = 40
SEG = (5, 35)  # rows of the segment: 30 rows, five margin rows on each side
N_SEG = SEG[1] - SEG[0]
LE, RE, LW, RW = IDX["LElbow"], IDX["RElbow"], IDX["LWrist"], IDX["RWrist"]
LH, RH, LS, RS = IDX["LHip"], IDX["RHip"], IDX["LShoulder"], IDX["RShoulder"]


def check_against_loops(layer: PoseFiltered, f: FrameFeatures, *, atol: float = 1e-12, **kwargs: Any) -> None:
    """The values, the validity, the reasons and Λ of ``f`` are the independent ones."""
    joints = tuple(u.name for u in f.units if u.kind == "position")
    segments = tuple(u.name for u in f.units if u.kind == "angle")
    values, valid, lam = expected_features(layer, joints=joints, segments=segments, **kwargs)
    assert f.values.shape == values.shape and np.array_equal(f.valid, valid)
    assert np.array_equal(f.reason, expected_reasons(layer, joints=joints, segments=segments, **kwargs))
    np.testing.assert_allclose(f.values, values, rtol=0.0, atol=atol)  # NaN equal to NaN
    assert f.scale_px == pytest.approx(lam, rel=1e-12) or (math.isnan(lam) and math.isnan(f.scale_px))


def col(f: FrameFeatures, name: str) -> int:
    return [u.name for u in f.units].index(name)


# --- layers ---------------------------------------------------------------------------------------------------------
def wavy(n: int = G, seed: int = 3, amp: float = 8.0, segment: tuple[int, int] = SEG) -> np.ndarray:
    """``(n, 26, 2)`` float64: a standing body with every joint moved by noise, so that every length and angle varies;
    the shoulders of the margin rows (outside ``segment``) are 100 px higher (the trunk of the margins is longer)."""
    rng = np.random.default_rng(seed)
    kp = body(n, 400.0).astype(np.float64) + rng.normal(0.0, amp, size=(n, 26, 2))
    kp[: segment[0], [LS, RS], 1] -= 100.0
    kp[segment[1] :, [LS, RS], 1] -= 100.0
    return kp


def wavy_layer(**kwargs: Any) -> PoseFiltered:
    return exact_layer(wavy(), segment=SEG, **kwargs)


def grid_body(n: int = G, seed: int = 5) -> np.ndarray:
    """A moving body on a 1/16 pixel grid: a scale by a power of two and an integer shift are exact in float32."""
    rng = np.random.default_rng(seed)
    kp = body(n, 400.0).astype(np.float64) + rng.normal(0.0, 8.0, size=(n, 26, 2))
    return np.round(kp * 16.0) / 16.0


def scenario_layer() -> PoseFiltered:
    """A segment of 30 rows with one situation per row (the row number is counted from the start of the segment):
    1 LWrist missing (1); 2 LHip missing (3); 3 LElbow missing (2) and LHip missing (5); 4 LHip missing (5) and RHip
    missing (3); 5 LShoulder missing (1) and RHip missing (3); 6 the forearm has no length (wrist on the elbow); 7 the
    trunk has no length (shoulders on the hips); 8 LElbow bridged; 9 RHip bridged; 10 LElbow bridged and LWrist missing
    (5); the other rows are clean."""
    layer = wavy_layer()
    k, r, i = cells(layer)

    def at(s: int) -> int:
        return SEG[0] + s

    drop(k, r, at(1), LW, 1)
    drop(k, r, at(2), LH, 3)
    drop(k, r, at(3), LE, 2)
    drop(k, r, at(3), LH, 5)
    drop(k, r, at(4), LH, 5)
    drop(k, r, at(4), RH, 3)
    drop(k, r, at(5), LS, 1)
    drop(k, r, at(5), RH, 3)
    k[at(6), LW] = k[at(6), LE]
    k[at(7), [LS, RS]] = k[at(7), [LH, RH]]
    bridge(k, r, i, at(8), LE)
    bridge(k, r, i, at(9), RH)
    bridge(k, r, i, at(10), LE)
    drop(k, r, at(10), LW, 5)
    return edited(layer, keypoints=k, reason=r, interpolated=i)


def state(f: FrameFeatures, s: int, name: str) -> tuple[bool, int, bool]:
    """``(valid, reason, bridged)`` of the unit ``name`` at row ``s`` of the segment."""
    u = col(f, name)
    return bool(f.valid[s, u]), int(f.reason[s, u]), bool(f.bridged[s, u])


# --- T-CMP-01a: the values ------------------------------------------------------------------------------------------
def test_t_cmp_01a_every_unit_equals_the_independent_derivation_on_a_moving_body():
    layer = wavy_layer()
    f = frame_features(layer)
    assert f.values.shape == (N_SEG, 21, 2) and f.valid.shape == f.reason.shape == f.bridged.shape == (N_SEG, 21)
    assert f.valid.all() and (f.reason == 0).all() and not f.bridged.any()
    check_against_loops(layer, f)
    assert np.ptp(f.values[:, :, 0]) > 0.1 and np.ptp(f.values[:, :, 1]) > 0.1  # the body does move: not a constant


def test_t_cmp_01a_the_scale_is_the_median_of_the_rows_of_the_segment_not_of_the_margins_and_not_per_frame():
    segment = (20, 50)  # 30 rows of the segment and 50 margin rows with a trunk 100 px longer
    layer = exact_layer(wavy(80, segment=segment), segment=segment)
    f = frame_features(layer)
    assert f.scale_px == pytest.approx(trunk_scale_of(layer), rel=1e-12)
    every_row = trunk_scale_of(layer, list(range(80)))
    assert (every_row - f.scale_px) / f.scale_px > 0.3  # the margins would have moved it
    assert f.scale_rows == N_SEG and f.scale_s == pytest.approx(N_SEG * float(layer.meta.timeline.step_s), rel=1e-12)
    # a per-frame scale would give every frame a trunk of exactly 1: here the trunk of the frames is not 1
    mid_shoulders = (f.values[:, col(f, "LShoulder"), :] + f.values[:, col(f, "RShoulder"), :]) / 2.0
    assert np.ptp(np.hypot(mid_shoulders[:, 0], mid_shoulders[:, 1])) > 0.01


def test_t_cmp_01a_the_two_hips_are_opposite_because_the_origin_is_their_middle():
    f = frame_features(wavy_layer())
    left, right = f.values[:, col(f, "LHip")], f.values[:, col(f, "RHip")]
    np.testing.assert_allclose(left, -right, rtol=0.0, atol=1e-12)


def test_t_cmp_01a_a_roll_is_the_rotation_by_minus_the_roll_of_the_points():
    layer = wavy_layer()
    f = frame_features(layer, roll_deg=12.5)
    check_against_loops(layer, f, atol=1e-9, roll=12.5)
    assert f.roll_deg == 12.5
    assert np.abs(f.values - frame_features(layer).values).max() > 0.05  # the roll does change the features


def test_t_cmp_01a_the_default_tables_are_the_twelve_joints_and_the_nine_segments_of_appendix_c():
    assert DEFAULT_JOINTS == JOINTS12 and DEFAULT_SEGMENTS == SEGMENTS9 == tuple(SEGMENTS)
    assert {name: ends for name, ends in SEGMENTS.items()} == TABLE
    f = frame_features(wavy_layer())
    assert [u.kind for u in f.units] == ["position"] * 12 + ["angle"] * 9  # positions first, then angles
    assert [u.name for u in f.units] == [*JOINTS12, *SEGMENTS9]
    assert [u.joints for u in f.units[:12]] == [(IDX[n],) for n in JOINTS12]
    assert [u.joints for u in f.units[12:]] == [(*TABLE[n][0], *TABLE[n][1]) for n in SEGMENTS9]
    assert f.units[-1].joints == (11, 12, 5, 6)  # the trunk: the hips, then the shoulders
    assert all(isinstance(u, FeatureUnit) for u in f.units)


def test_t_cmp_01a_the_joints_and_segments_asked_choose_and_order_the_units():
    layer = wavy_layer()
    f = frame_features(layer, joints=("RWrist", "LAnkle", "Nose"), segments=("trunk", "l_shank"))
    assert [(u.kind, u.name) for u in f.units] == [
        ("position", "RWrist"), ("position", "LAnkle"), ("position", "Nose"), ("angle", "trunk"), ("angle", "l_shank"),
    ]  # fmt: skip
    assert [u.joints for u in f.units] == [(RW,), (IDX["LAnkle"],), (IDX["Nose"],), (11, 12, 5, 6), (13, 15)]
    check_against_loops(layer, f)
    again = frame_features(layer, joints=["LAnkle"], segments=["l_shank", "trunk"])  # lists, another order and layout
    assert [u.name for u in again.units] == ["LAnkle", "l_shank", "trunk"]


def test_t_cmp_01a_a_hip_unit_has_no_repeated_joint_and_the_two_hips_are_valid_and_opposite():
    # the unit of a hip joint is (j, 11, 12) without a repeated joint: LHip and RHip are valid and opposite
    f = frame_features(wavy_layer(), joints=("LHip", "RHip"), segments=("trunk",))
    assert f.valid.all() and np.abs(f.values[:, 0] + f.values[:, 1]).max() < 1e-12


# --- T-CMP-01b: invariance ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("scale", [0.5, 2.0, 4.0])
@pytest.mark.parametrize("shift", [(0.0, 0.0), (130.0, -40.0), (-75.0, 220.0)])
def test_t_cmp_01b_features_are_exactly_invariant_to_translation_and_a_power_of_two_scale(scale, shift):
    kp = grid_body()
    base = frame_features(exact_layer(kp, segment=SEG))
    moved = frame_features(exact_layer(kp * scale + np.array(shift), segment=SEG))
    np.testing.assert_allclose(moved.values, base.values, rtol=0.0, atol=1e-9)  # the plan's 1e-9
    assert np.array_equal(moved.valid, base.valid) and moved.scale_px == pytest.approx(base.scale_px * scale, rel=1e-12)


@pytest.mark.parametrize("scale", [0.63, 1.7, 2.9])
def test_t_cmp_01b_features_are_invariant_to_a_scale_and_a_shift_that_float32_cannot_hold_exactly(scale):
    kp = wavy()
    base = frame_features(exact_layer(kp, segment=SEG))
    moved = frame_features(exact_layer(kp * scale + np.array([-33.3, 71.9]), segment=SEG))
    assert np.abs(moved.values - base.values).max() < 1e-5  # float32 storage of the moved pixels
    assert np.array_equal(moved.valid, base.valid)


def test_t_cmp_01b_the_invariance_is_not_vacuous_a_change_of_shape_changes_the_features():
    kp = wavy()
    base = frame_features(exact_layer(kp, segment=SEG))
    stretched = kp.copy()
    stretched[..., 0] *= 1.5  # x only: not a similarity
    other = frame_features(exact_layer(stretched, segment=SEG))
    assert np.abs(other.values - base.values).max() > 0.05
    sheared = kp.copy()
    sheared[:, LW, :] += np.array([60.0, -60.0])  # one joint moves
    moved = frame_features(exact_layer(sheared, segment=SEG))
    assert np.abs(moved.values[:, col(moved, "LWrist")] - base.values[:, col(base, "LWrist")]).max() > 0.2
    assert np.abs(moved.values[:, col(moved, "RWrist")] - base.values[:, col(base, "RWrist")]).max() < 1e-12


# --- T-CMP-01c: the angle has no wrap -------------------------------------------------------------------------------
WRAP_DEG = [0.0, 1.0, 359.0, 179.9, -179.9, 180.0, -180.0, 90.0, -90.0, 45.0, 270.0, -1.0, 358.0, 2.0]


def forearm_layer(angles_deg: list[float], radius: float = 50.0) -> PoseFiltered:
    """Rows in which the left forearm points at the given angles (0 up, positive to the right, y down)."""
    n = len(angles_deg) + 4
    kp = body(n, 400.0).astype(np.float64)
    elbow = np.array([420.0, 300.0])
    kp[:, LE] = elbow
    for g, a in enumerate(angles_deg):
        kp[g, LW] = elbow + radius * np.array([math.sin(math.radians(a)), -math.cos(math.radians(a))])
    return exact_layer(kp)


def test_t_cmp_01c_the_forearm_unit_is_sin_and_cos_of_the_angle_for_every_quadrant_and_at_the_wrap():
    f = frame_features(forearm_layer(WRAP_DEG))
    u = col(f, "l_forearm")
    for g, a in enumerate(WRAP_DEG):
        want = (math.sin(math.radians(a)), math.cos(math.radians(a)))
        assert f.values[g, u] == pytest.approx(want, abs=2e-6), a
    assert f.values[WRAP_DEG.index(180.0), u] == pytest.approx((0.0, -1.0), abs=2e-6)
    assert np.array_equal(f.values[WRAP_DEG.index(180.0), u], f.values[WRAP_DEG.index(-180.0), u])  # one direction


def test_t_cmp_01c_359_degrees_is_next_to_1_degree_and_179_9_next_to_minus_179_9():
    f = frame_features(forearm_layer(WRAP_DEG))
    u = col(f, "l_forearm")

    def chord(a: float, b: float) -> float:
        ia, ib = WRAP_DEG.index(a), WRAP_DEG.index(b)
        return float(np.hypot(*(f.values[ia, u] - f.values[ib, u])))

    assert chord(359.0, 1.0) == pytest.approx(2.0 * math.sin(math.radians(1.0)), abs=2e-6)  # 2 degrees apart, not 358
    assert chord(179.9, -179.9) == pytest.approx(2.0 * math.sin(math.radians(0.1)), abs=2e-6)
    assert chord(358.0, 359.0) == pytest.approx(chord(359.0, 0.0), abs=4e-6)  # the same step either side of the wrap
    assert chord(0.0, 1.0) == pytest.approx(chord(-1.0, 0.0), abs=4e-6) == pytest.approx(chord(1.0, 2.0), abs=4e-6)
    assert chord(90.0, -90.0) == pytest.approx(2.0, abs=2e-6)  # opposite directions are the farthest apart


TRUNK_DEG = [0.0, 10.0, -10.0, 90.0, 179.9, -179.9, 180.0, -90.0, 359.0, 1.0, -1.0, 135.0, -135.0]


def lean_layer(theta_deg: list[float], trunk: float = 150.0) -> PoseFiltered:
    """Rows in which the middle of the shoulders is ``trunk`` px from the middle of the hips at the lean ``θ``."""
    n = len(theta_deg) + 4
    kp = body(n, 600.0).astype(np.float64)
    hip = (kp[:, LH] + kp[:, RH]) / 2.0
    for g, th in enumerate(theta_deg):
        top = hip[g] + trunk * np.array([math.sin(math.radians(th)), -math.cos(math.radians(th))])
        kp[g, LS], kp[g, RS] = top + np.array([-40.0, 0.0]), top + np.array([40.0, 0.0])
    return exact_layer(kp)


@pytest.mark.parametrize("roll", [0.0, -8.0, 30.0])
def test_t_cmp_01c_the_trunk_unit_is_sin_and_cos_of_the_lean_angle_of_trunk_lean(roll):
    layer = lean_layer(TRUNK_DEG)
    f = frame_features(layer, roll_deg=roll)
    lean = lean_angle_deg(mid_hip(layer.keypoints), mid_shoulder(layer.keypoints), roll)  # degrees, wrapped
    u = col(f, "trunk")
    want = np.stack([np.sin(np.radians(lean)), np.cos(np.radians(lean))], axis=-1)
    np.testing.assert_allclose(f.values[:, u], want, rtol=0.0, atol=1e-9)
    assert f.valid[:, u].all()
    if roll == 0.0:  # and the lean is what was asked for, to the float32 of the pixels
        asked = np.array([[math.sin(math.radians(a)), math.cos(math.radians(a))] for a in TRUNK_DEG])
        np.testing.assert_allclose(f.values[: len(TRUNK_DEG), u], asked, rtol=0.0, atol=2e-6)


# --- T-CMP-01d: one scale per segment -------------------------------------------------------------------------------
def fixed_trunk_layer(scaled_row: int | None = None, factor: float = 2.0) -> PoseFiltered:
    """A body whose trunk is exactly 150 px in every row while the limbs move; one row may be scaled about its hips."""
    rng = np.random.default_rng(11)
    kp = body(G, 400.0).astype(np.float64)
    limbs = [IDX[n] for n in ("LElbow", "RElbow", "LWrist", "RWrist", "LKnee", "RKnee", "LAnkle", "RAnkle")]
    kp[:, limbs] += rng.normal(0.0, 12.0, size=(G, len(limbs), 2))
    kp = np.round(kp * 16.0) / 16.0  # a 1/16 px grid: the scaled row (a 1/32 px grid) is exact in float32
    if scaled_row is not None:
        hip = (kp[scaled_row, LH] + kp[scaled_row, RH]) / 2.0
        kp[scaled_row] = hip + factor * (kp[scaled_row] - hip)
    return exact_layer(kp, segment=SEG)


def test_t_cmp_01d_scaling_one_frame_scales_only_its_position_features_not_its_angles_and_not_the_others():
    k = 12  # a row of the segment
    plain, scaled = frame_features(fixed_trunk_layer()), frame_features(fixed_trunk_layer(SEG[0] + k, 2.0))
    assert plain.scale_px == scaled.scale_px == 150.0  # one median over 30 rows: one scaled row does not move it
    positions = [u for u, x in enumerate(plain.units) if x.kind == "position"]
    angles = [u for u, x in enumerate(plain.units) if x.kind == "angle"]
    np.testing.assert_allclose(scaled.values[k][positions], 2.0 * plain.values[k][positions], rtol=0.0, atol=1e-9)
    np.testing.assert_allclose(scaled.values[k][angles], plain.values[k][angles], rtol=0.0, atol=1e-9)
    others = [r for r in range(N_SEG) if r != k]
    np.testing.assert_allclose(scaled.values[others], plain.values[others], rtol=0.0, atol=1e-12)


def test_t_cmp_01d_scaling_every_frame_is_invisible_but_changes_the_scale():
    half = exact_layer(0.5 * fixed_trunk_layer().keypoints, segment=SEG)
    plain, scaled = frame_features(fixed_trunk_layer()), frame_features(half)
    assert plain.scale_px == 150.0 and scaled.scale_px == 75.0
    np.testing.assert_allclose(scaled.values, plain.values, rtol=0.0, atol=1e-9)


def test_t_cmp_01d_the_scale_is_the_median_not_the_mean_of_the_trunks_of_the_rows():
    kp = body(G, 400.0).astype(np.float64)
    kp[SEG[0] : SEG[0] + 10, [LS, RS], 1] -= 150.0  # 10 rows of the segment with a trunk of 300, 20 rows with 150
    f = frame_features(exact_layer(kp, segment=SEG))
    assert f.scale_px == 150.0 and f.scale_rows == N_SEG  # the mean would be 200


# --- T-CMP-01e: masks and reasons -----------------------------------------------------------------------------------
def test_t_cmp_01e_the_values_and_the_validity_of_the_scenario_are_the_independent_ones():
    layer = scenario_layer()
    f = frame_features(layer)
    check_against_loops(layer, f)
    assert f.scale_rows == 25  # rows 2, 3, 4, 5 (a hip or a shoulder missing) and 7 (a trunk of 0) have no trunk


def test_t_cmp_01e_nan_where_not_valid_a_value_where_valid_and_the_reason_says_which():
    f = frame_features(scenario_layer())
    assert np.array_equal(f.valid, f.reason == 0)
    assert np.isnan(f.values[~f.valid]).all()  # both components, never 0
    assert np.isfinite(f.values[f.valid]).all()
    assert not (f.bridged & ~f.valid).any()  # a feature that is not a value leans on nothing
    assert f.values.dtype == np.float64 and f.reason.dtype == np.uint8


def test_t_cmp_01e_a_missing_joint_makes_its_position_and_the_segments_that_end_on_it_invalid_with_its_reason():
    f = frame_features(scenario_layer())
    assert state(f, 1, "LWrist") == (False, 1, False) and state(f, 1, "l_forearm") == (False, 1, False)
    assert state(f, 1, "l_upper_arm") == (True, 0, False) and state(f, 1, "LElbow") == (True, 0, False)
    assert state(f, 1, "RWrist") == (True, 0, False) and state(f, 1, "trunk") == (True, 0, False)


def test_t_cmp_01e_a_missing_hip_makes_every_position_and_the_segments_on_it_invalid():
    f = frame_features(scenario_layer())
    for name in JOINTS12:
        assert state(f, 2, name) == (False, 3, False), name  # every position is relative to the hips
    assert state(f, 2, "l_thigh") == (False, 3, False) and state(f, 2, "trunk") == (False, 3, False)
    for name in ("r_thigh", "l_shank", "r_shank", "l_upper_arm", "l_forearm", "r_upper_arm", "r_forearm"):
        assert state(f, 2, name) == (True, 0, False), name  # an angle needs its own two ends only


def test_t_cmp_01e_the_reason_is_the_one_of_the_first_unusable_joint_the_joint_itself_before_the_hips():
    f = frame_features(scenario_layer())
    assert state(f, 3, "LElbow")[:2] == (False, 2)  # LElbow (2) before the hip (5)
    assert state(f, 3, "LWrist")[:2] == (False, 5) and state(f, 3, "RWrist")[:2] == (False, 5)  # the hip
    assert state(f, 3, "l_upper_arm")[:2] == (False, 2) and state(f, 3, "l_forearm")[:2] == (False, 2)
    assert state(f, 3, "r_upper_arm")[:2] == (True, 0) and state(f, 3, "r_forearm")[:2] == (True, 0)


def test_t_cmp_01e_the_hips_are_looked_at_in_the_order_left_then_right_and_a_hip_unit_starts_with_itself():
    f = frame_features(scenario_layer())  # row 4: LHip missing (5), RHip missing (3)
    assert state(f, 4, "LHip")[:2] == (False, 5)  # (11, 12): the left hip first
    assert state(f, 4, "RHip")[:2] == (False, 3)  # (12, 11): itself first
    assert state(f, 4, "LKnee")[:2] == (False, 5) and state(f, 4, "RKnee")[:2] == (False, 5)  # (j, 11, 12)
    assert state(f, 4, "l_thigh")[:2] == (False, 5) and state(f, 4, "r_thigh")[:2] == (False, 3)
    assert state(f, 4, "trunk")[:2] == (False, 5)  # (11, 12, 5, 6)


def test_t_cmp_01e_the_trunk_looks_at_the_hips_before_the_shoulders():
    f = frame_features(scenario_layer())  # row 5: LShoulder missing (1), RHip missing (3)
    assert state(f, 5, "trunk")[:2] == (False, 3)  # the right hip (12) comes before the left shoulder (5)
    assert state(f, 5, "LShoulder")[:2] == (False, 1)  # itself first
    assert state(f, 5, "RShoulder")[:2] == (False, 3)  # its own joint is there, the hip is not
    assert state(f, 5, "l_upper_arm")[:2] == (False, 1) and state(f, 5, "r_upper_arm")[:2] == (True, 0)


def test_t_cmp_01e_a_segment_with_no_length_has_no_angle_zero_length_and_its_joints_keep_their_positions():
    f = frame_features(scenario_layer())
    assert (
        state(f, 6, "l_forearm") == (False, int(FeatureReason.zero_length), False)
        and int(FeatureReason.zero_length) == 23
    )
    assert state(f, 6, "LWrist") == (True, 0, False) and state(f, 6, "LElbow") == (True, 0, False)
    assert state(f, 6, "l_upper_arm") == (True, 0, False)
    # the trunk of 0 px: its angle does not exist, the positions still divide by the median of the other rows
    assert state(f, 7, "trunk") == (False, 23, False)
    assert all(state(f, 7, name) == (True, 0, False) for name in JOINTS12)


def test_t_cmp_01e_a_bridged_cell_is_a_value_and_is_flagged_on_the_units_that_lean_on_it():
    f = frame_features(scenario_layer())
    leaning = {"LElbow", "l_upper_arm", "l_forearm"}  # row 8: LElbow bridged
    for name in [*JOINTS12, *SEGMENTS9]:
        assert state(f, 8, name) == (True, 0, name in leaning), name
    leaning = set(JOINTS12) | {"r_thigh", "trunk"}  # row 9: RHip bridged: every position is relative to the hips
    for name in [*JOINTS12, *SEGMENTS9]:
        assert state(f, 9, name) == (True, 0, name in leaning), name


def test_t_cmp_01e_a_unit_that_is_not_a_value_is_not_flagged_even_if_one_of_its_joints_is_bridged():
    f = frame_features(scenario_layer())  # row 10: LElbow bridged, LWrist missing (5)
    assert state(f, 10, "l_forearm") == (False, 5, False) and state(f, 10, "LWrist") == (False, 5, False)
    assert state(f, 10, "LElbow") == (True, 0, True) and state(f, 10, "l_upper_arm") == (True, 0, True)


def test_t_cmp_01e_no_scale_makes_the_positions_scale_unavailable_and_leaves_the_angles_valid():
    layer = exact_layer(body(G, 400.0, trunk=0.0), segment=SEG)  # the shoulders on the hips: no trunk in any row
    f = frame_features(layer)
    assert math.isnan(f.scale_px) and f.scale_rows == 0 and f.scale_s == 0.0
    pos, ang = f.units[:12], f.units[12:]
    assert all(state(f, s, u.name) == (False, 19, False) for s in range(N_SEG) for u in pos)
    assert int(FeatureReason.scale_unavailable) == int(MissingReason.scale_unavailable) == 19
    assert np.isnan(f.values[:, :12]).all()
    for s in range(N_SEG):
        assert all(state(f, s, u.name) == (True, 0, False) for u in ang if u.name != "trunk")
        assert state(f, s, "trunk") == (False, 23, False)  # and the trunk has no direction either


def test_t_cmp_01e_a_pose_reason_comes_before_scale_unavailable():
    layer = exact_layer(body(G, 400.0, trunk=0.0), segment=SEG)
    k, r, i = cells(layer)
    drop(k, r, SEG[0] + 3, LW, 1)
    f = frame_features(edited(layer, keypoints=k, reason=r))
    assert state(f, 3, "LWrist") == (False, 1, False) and state(f, 3, "RWrist") == (False, 19, False)


def test_t_cmp_01e_a_minimum_duration_of_the_scale_rows_withholds_the_scale_and_keeps_the_rows_and_seconds():
    layer = wavy_layer()
    step = float(layer.meta.timeline.step_s)
    ok = frame_features(layer, min_scale_s=0.9)
    assert ok.scale_px == pytest.approx(trunk_scale_of(layer), rel=1e-12) and ok.valid.all()
    edge = frame_features(layer, min_scale_s=N_SEG * step)  # exactly the duration of the rows: enough
    assert edge.scale_px == pytest.approx(ok.scale_px, rel=1e-12)
    short = frame_features(layer, min_scale_s=1.5)  # the 30 rows last 1 s
    assert math.isnan(short.scale_px) and short.scale_rows == N_SEG and short.scale_s == pytest.approx(N_SEG * step)
    assert not short.valid[:, :12].any() and (short.reason[:, :12] == 19).all()
    assert short.valid[:, 12:].all()  # the angles have no scale
    np.testing.assert_array_equal(short.values[:, 12:], ok.values[:, 12:])


# --- T-CMP-01f: the camera roll -------------------------------------------------------------------------------------
def camera(kp: np.ndarray, beta_deg: float, centre: tuple[float, float] = (960.0, 540.0)) -> np.ndarray:
    """The points seen through a camera rolled by ``β``: the true vertical (0, -1) appears as ``(sin β, -cos β)``."""
    b = math.radians(beta_deg)
    rel = kp - np.array(centre)
    out = np.empty_like(rel)
    out[..., 0] = rel[..., 0] * math.cos(b) - rel[..., 1] * math.sin(b)
    out[..., 1] = rel[..., 0] * math.sin(b) + rel[..., 1] * math.cos(b)
    return out + np.array(centre)


@pytest.mark.parametrize("beta", [5.0, -8.0, 30.0, 45.0, -45.0])
def test_t_cmp_01f_rotated_keypoints_with_the_matching_roll_give_the_unrotated_features(beta):
    kp = wavy()
    base = frame_features(exact_layer(kp, segment=SEG))
    rolled = exact_layer(camera(kp, beta), segment=SEG)
    right = frame_features(rolled, roll_deg=beta)
    assert np.abs(right.values - base.values).max() < 1e-5  # float32 storage of the rotated pixels
    assert np.array_equal(right.valid, base.valid) and right.scale_px == pytest.approx(base.scale_px, rel=1e-5)
    wrong = frame_features(rolled)  # the roll is not taken out
    assert np.abs(wrong.values - base.values).max() > 0.05  # 2 sin(2.5 degrees) at the smallest roll


def test_t_cmp_01f_an_upright_trunk_seen_through_a_rolled_camera_leans_by_the_roll_until_it_is_corrected():
    upright = body(G, 400.0).astype(np.float64)
    for beta in (5.0, -8.0, 30.0):
        layer = exact_layer(camera(upright, beta), segment=SEG)
        raw = frame_features(layer).values[:, col(frame_features(layer), "trunk")]
        fixed = frame_features(layer, roll_deg=beta).values[:, col(frame_features(layer), "trunk")]
        assert np.degrees(np.arctan2(raw[:, 0], raw[:, 1])) == pytest.approx(beta, abs=1e-3)
        assert np.degrees(np.arctan2(fixed[:, 0], fixed[:, 1])) == pytest.approx(0.0, abs=1e-3)


def test_t_cmp_01f_the_roll_does_not_change_the_scale_and_the_limit_is_45_degrees():
    layer = wavy_layer()
    assert frame_features(layer, roll_deg=30.0).scale_px == frame_features(layer).scale_px
    for ok in (45.0, -45.0, 0, 7):
        frame_features(layer, roll_deg=ok)
    for bad in (45.5, -46.0, 90.0):
        with pytest.raises(CompareError, match="^roll_deg must be within 45 degrees"):
            frame_features(layer, roll_deg=bad)


# --- T-CMP-01g: edges and refusals ----------------------------------------------------------------------------------
def test_t_cmp_01g_a_segment_with_no_row_gives_empty_features_and_no_scale():
    layer = edited(wavy_layer(), grid_in_segment=np.zeros(G, dtype=bool))
    f = frame_features(layer)
    assert f.values.shape == (0, 21, 2) and f.valid.shape == f.reason.shape == f.bridged.shape == (0, 21)
    assert f.t_sec.shape == (0,) and math.isnan(f.scale_px) and f.scale_rows == 0 and f.scale_s == 0.0
    assert f.step_s is None and len(f.units) == 21


def test_t_cmp_01g_a_segment_of_one_row_has_features_and_no_step():
    only = np.zeros(G, dtype=bool)
    only[10] = True
    layer = edited(wavy_layer(), grid_in_segment=only)
    f = frame_features(layer)
    assert f.values.shape == (1, 21, 2) and f.step_s is None and f.valid.all()
    check_against_loops(layer, f)
    assert f.scale_rows == 1 and f.scale_s == 0.0  # one row has no duration
    assert math.isnan(frame_features(layer, min_scale_s=0.01).scale_px)  # so a minimum duration cannot be met


def test_t_cmp_01g_a_segment_of_two_rows_has_the_step_of_the_layer():
    two = np.zeros(G, dtype=bool)
    two[10:12] = True
    layer = edited(wavy_layer(), grid_in_segment=two)
    f = frame_features(layer)
    assert f.step_s == float(layer.meta.timeline.step_s) and f.values.shape == (2, 21, 2)
    check_against_loops(layer, f)


LAYER = "^layer must be a PoseFiltered, got "
NAMES = "must be a non-empty list of {} names, got "
ROLL = "^roll_deg must be a finite number of degrees, got "
MINIMUM = "^min_scale_s must be None or a finite number of seconds above 0, got "
MIN_LENGTH = "^min_segment_length must be None or a finite number of trunk lengths above 0, got "
BAD_ARGUMENTS = [
    ({"layer": None}, LAYER + "NoneType"),
    ({"layer": "x"}, LAYER + "str"),
    ({"layer": {"keypoints": 1}}, LAYER + "dict"),
    ({"joints": ()}, "^joints must not be empty"),
    ({"joints": None}, "^joints " + NAMES.format("joint") + "NoneType"),
    ({"joints": "LWrist"}, "^joints " + NAMES.format("joint") + "str"),
    ({"joints": 9}, "^joints " + NAMES.format("joint") + "int"),
    ({"joints": ("LWrist", "LWrist")}, "^joints must not repeat a joint name"),
    ({"joints": ("LWrist", "LWristt")}, r"^joints\[1\] must be one of the joint names"),
    ({"joints": ("lwrist",)}, r"^joints\[0\] must be one of the joint names"),
    ({"joints": (9,)}, r"^joints\[0\] must be one of the joint names"),
    ({"joints": (None,)}, r"^joints\[0\] must be one of the joint names"),
    ({"joints": (["LWrist"],)}, r"^joints\[0\] must be one of the joint names"),  # unhashable: not a TypeError
    ({"segments": ()}, "^segments must not be empty"),
    ({"segments": None}, "^segments " + NAMES.format("segment") + "NoneType"),
    ({"segments": "trunk"}, "^segments " + NAMES.format("segment") + "str"),
    ({"segments": ("trunk", "trunk")}, "^segments must not repeat a segment name"),
    ({"segments": ("trunk", "spine")}, r"^segments\[1\] must be one of the segment names"),
    ({"segments": (3,)}, r"^segments\[0\] must be one of the segment names"),
    ({"roll_deg": 45.5}, "^roll_deg must be within 45 degrees, got 45.5"),
    ({"roll_deg": float("nan")}, ROLL + "nan"),
    ({"roll_deg": float("inf")}, ROLL + "inf"),
    ({"roll_deg": "5"}, ROLL + "str"),
    ({"roll_deg": True}, ROLL + "bool"),
    ({"roll_deg": None}, ROLL + "NoneType"),
    ({"min_scale_s": 0.0}, MINIMUM + "0.0"),
    ({"min_scale_s": -1.0}, MINIMUM + "-1.0"),
    ({"min_scale_s": float("nan")}, MINIMUM + "nan"),
    ({"min_scale_s": float("inf")}, MINIMUM + "inf"),
    ({"min_scale_s": True}, MINIMUM + "bool"),
    ({"min_scale_s": "1"}, MINIMUM + "str"),
    ({"min_segment_length": 0.0}, MIN_LENGTH + "0.0"),
    ({"min_segment_length": -0.05}, MIN_LENGTH + "-0.05"),
    ({"min_segment_length": float("nan")}, MIN_LENGTH + "nan"),
    ({"min_segment_length": float("inf")}, MIN_LENGTH + "inf"),
    ({"min_segment_length": True}, MIN_LENGTH + "bool"),
    ({"min_segment_length": "0.05"}, MIN_LENGTH + "str"),
    ({"min_segment_length": [0.05]}, MIN_LENGTH + "list"),
]


@pytest.mark.parametrize(
    ("change", "argument"), BAD_ARGUMENTS, ids=[f"{list(c)[0]}-{i}" for i, (c, _) in enumerate(BAD_ARGUMENTS)]
)
def test_t_cmp_01g_a_bad_argument_is_a_compare_error_that_names_it(change, argument):
    args: dict[str, Any] = dict(change)
    layer = args.pop("layer", wavy_layer())
    with pytest.raises(CompareError, match=argument):
        frame_features(layer, **args)


def test_t_cmp_01g_numpy_numbers_are_numbers_and_the_roll_is_echoed_as_a_float():
    layer = wavy_layer()
    a = frame_features(
        layer, roll_deg=np.float32(5.0), min_scale_s=np.float64(0.5), min_segment_length=np.float64(0.25)
    )
    b = frame_features(layer, roll_deg=5.0, min_scale_s=0.5, min_segment_length=0.25)
    assert a.roll_deg == 5.0 and type(a.roll_deg) is float and np.array_equal(a.values, b.values, equal_nan=True)
    assert (type(a.min_scale_s), type(a.min_segment_length)) == (float, float)  # a number is echoed as a float
    frame_features(layer, roll_deg=np.int64(3), min_scale_s=np.int32(1), min_segment_length=np.int64(1))


def test_t_cmp_01g_a_refusal_never_echoes_a_string_given_by_the_caller():
    secret = "SECRET-participant-name"
    for change in (
        {"joints": (secret,)},
        {"segments": (secret,)},
        {"roll_deg": secret},
        {"min_scale_s": secret},
        {"min_segment_length": secret},
    ):
        with pytest.raises(CompareError) as err:
            frame_features(wavy_layer(), **change)
        assert secret not in str(err.value) and "SECRET" not in str(err.value)
    with pytest.raises(CompareError) as err:
        frame_features(secret)  # type: ignore[arg-type]
    assert secret not in str(err.value)


def test_t_cmp_01g_a_segment_that_is_not_one_run_of_rows_is_refused():
    mask = np.zeros(G, dtype=bool)
    mask[5:10] = mask[12:20] = True
    with pytest.raises(CompareError, match="grid_in_segment") as err:
        frame_features(edited(wavy_layer(), grid_in_segment=mask))
    assert isinstance(err.value.__cause__, MetricError)  # the error of the metrics is chained, not swallowed


def test_t_cmp_01g_a_layer_that_breaks_the_contract_of_a_cell_is_refused_and_not_read_as_a_value():
    layer = wavy_layer()
    k, r, _ = cells(layer)
    k[SEG[0] + 2, LW, 0] = np.nan  # a cell with one NaN coordinate
    with pytest.raises(CompareError, match="one NaN coordinate") as err:
        frame_features(edited(layer, keypoints=k))
    assert isinstance(err.value.__cause__, MetricError)
    k, r, _ = cells(layer)
    k[SEG[0] + 2, LW] = np.nan  # a missing cell whose reason says ok
    with pytest.raises(CompareError, match="reason"):
        frame_features(edited(layer, keypoints=k))
    k, r, i = cells(layer)
    i[SEG[0] + 2, LW] = True
    k[SEG[0] + 2, LW] = np.nan
    r[SEG[0] + 2, LW] = 1  # a flag of a bridge on a cell that has no value
    with pytest.raises(CompareError, match="interpolated"):
        frame_features(edited(layer, keypoints=k, reason=r, interpolated=i))


# --- T-CMP-01h: provenance, immutability, the layer unchanged -------------------------------------------------------
def test_t_cmp_01h_the_features_carry_their_provenance():
    layer = exact_layer(wavy(), segment=SEG, recording_id=OTHER_RECORDING_ID, data_sources=OTHER_SOURCES)
    f = frame_features(layer, roll_deg=-3.5, min_scale_s=0.5)
    assert f.recording_id == OTHER_RECORDING_ID != RECORDING_ID and f.data_sources == OTHER_SOURCES != SOURCES
    assert f.version == FEATURE_VERSION == "1" and f.roll_deg == -3.5
    assert f.scale_px == pytest.approx(trunk_scale_of(layer), rel=1e-12) and f.scale_rows == N_SEG
    assert f.step_s == float(layer.meta.timeline.step_s) and f.scale_s == pytest.approx(N_SEG * f.step_s)
    assert np.array_equal(f.t_sec, layer.t_grid[SEG[0] : SEG[1]]) and f.t_sec.dtype == np.float64  # the real clock
    default = frame_features(exact_layer(wavy(), segment=SEG))
    assert default.recording_id == RECORDING_ID and default.data_sources == SOURCES and default.roll_deg == 0.0
    assert (default.min_scale_s, default.min_segment_length) == (None, None)  # nothing applied is echoed as None
    assert (f.min_scale_s, f.min_segment_length) == (0.5, None)
    g = frame_features(layer, min_scale_s=0.25, min_segment_length=0.125)
    assert (g.min_scale_s, g.min_segment_length) == (0.25, 0.125)


def test_t_cmp_01h_the_two_echoes_have_a_default_so_a_result_built_by_hand_without_them_is_still_valid():
    f = frame_features(wavy_layer())
    names = [x.name for x in dataclasses.fields(FrameFeatures)]
    assert names[-2:] == ["min_scale_s", "min_segment_length"] and len(names) == 16
    built = FrameFeatures(**{n: getattr(f, n) for n in names if n not in names[-2:]})
    assert (built.min_scale_s, built.min_segment_length) == (None, None) and built.version == f.version


def test_t_cmp_01h_every_array_is_read_only_and_new_and_the_result_is_frozen():
    layer = wavy_layer()
    f = frame_features(layer)
    for name in ("t_sec", "values", "valid", "reason", "bridged"):
        a = getattr(f, name)
        assert not a.flags.writeable, name
        with pytest.raises(ValueError, match="read-only"):
            a.flat[0] = a.flat[0]
    for a in (f.t_sec, f.values, f.valid, f.reason, f.bridged):
        for layer_array in (layer.t_grid, layer.keypoints, layer.reason, layer.interpolated):
            assert not np.shares_memory(a, layer_array)
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.scale_px = 1.0  # type: ignore[misc]
    assert isinstance(f.units, tuple) and f.valid.dtype == f.bridged.dtype == np.bool_


def test_t_cmp_01h_the_layer_is_not_changed_and_the_call_is_deterministic():
    layer = scenario_layer()
    names = ("t_grid", "keypoints", "reason", "interpolated", "grid_in_segment")
    before = {n: getattr(layer, n).copy() for n in names}
    a, b = frame_features(layer, roll_deg=4.0), frame_features(layer, roll_deg=4.0)
    for n in names:
        assert np.array_equal(getattr(layer, n), before[n], equal_nan=getattr(layer, n).dtype.kind == "f"), n
    for n in ("t_sec", "values", "valid", "reason", "bridged"):
        assert np.array_equal(getattr(a, n), getattr(b, n), equal_nan=getattr(a, n).dtype.kind == "f"), n


def test_t_cmp_01h_the_margins_around_the_segment_are_not_in_the_features():
    layer = wavy_layer()
    f = frame_features(layer)
    assert len(f.t_sec) == N_SEG and f.t_sec[0] == layer.t_grid[SEG[0]] and f.t_sec[-1] == layer.t_grid[SEG[1] - 1]
    k, r, i = cells(layer)
    k[: SEG[0]] = np.nan  # the margins lose every joint: nothing changes
    k[SEG[1] :] = np.nan
    r[: SEG[0]] = r[SEG[1] :] = 3
    again = frame_features(edited(layer, keypoints=k, reason=r))
    np.testing.assert_array_equal(again.values, f.values)
    assert np.array_equal(again.valid, f.valid) and again.scale_px == f.scale_px


def test_t_cmp_01h_the_feature_reasons_are_the_numbers_of_the_series_reasons_and_one_new_code():
    for name in ("low_conf", "non_finite", "not_tracked", "frame_invalid", "outlier", "no_frame", "scale_unavailable"):
        assert int(FeatureReason[name]) == int(MissingReason[name]), name
    assert int(FeatureReason.valid) == int(MissingReason.measured) == 0
    assert int(FeatureReason.zero_length) == 23 and int(FeatureReason.short_segment) == 24
    assert not {23, 24} & {int(r) for r in MissingReason}  # the two codes of the features only
    assert [r.name for r in FeatureReason] == [
        "valid", "low_conf", "non_finite", "not_tracked", "frame_invalid", "outlier", "no_frame",
        "scale_unavailable", "zero_length", "short_segment",
    ]  # fmt: skip


# --- T-CMP-01i: a minimum length of a segment (R1) -----------------------------------------------------------------
ANGLES = slice(12, None)  # the nine angle units come after the twelve positions
MINIMUM_ARGUMENT = 0.05  # a value chosen for the tests only: the real one is the caller's (AGENTS.md 5.5)


def length_layer() -> PoseFiltered:
    """A standing body whose trunk is exactly 150 px (so ``Λ`` is exactly 150) and whose left forearm has, row by row
    of the segment (lengths in px, so ``length / 150`` is the written ratio): 0 7.4375 | 1 7.5 | 2 7.5625 | 3 7.5 down
    | 4 7.5 up | 5 4.5 and 6 (7.5 on a slant) | 6 0 (the wrist on the elbow) | 7 7.4375 down | 8 7.4375 and the elbow
    bridged | 9 50 and the elbow bridged | 10 50 and the wrist bridged; the other rows 50 (a third of a trunk)."""
    layer = exact_layer(body(G, 400.0), segment=SEG)
    k, r, i = cells(layer)
    offsets = {0: (7.4375, 0.0), 1: (7.5, 0.0), 2: (7.5625, 0.0), 3: (0.0, 7.5), 4: (0.0, -7.5), 5: (4.5, 6.0)}
    offsets |= {6: (0.0, 0.0), 7: (0.0, 7.4375), 8: (7.4375, 0.0)}
    for s, (dx, dy) in offsets.items():
        g = SEG[0] + s
        k[g, LW] = k[g, LE] + np.array([dx, dy], dtype=np.float32)
    bridge(k, r, i, SEG[0] + 8, LE)
    bridge(k, r, i, SEG[0] + 9, LE)
    bridge(k, r, i, SEG[0] + 10, LW)
    return edited(layer, keypoints=k, reason=r, interpolated=i)


def forearm_state(f: FrameFeatures, s: int) -> tuple[bool, int, bool]:
    return state(f, s, "l_forearm")


def test_t_cmp_01i_a_minimum_of_none_gives_the_arrays_of_a_run_without_the_argument():
    for layer in (wavy_layer(), scenario_layer(), length_layer()):
        for roll in (0.0, 9.0):
            a, b = frame_features(layer, roll_deg=roll), frame_features(layer, roll_deg=roll, min_segment_length=None)
            for name in ("t_sec", "values", "valid", "reason", "bridged"):
                assert np.array_equal(getattr(a, name), getattr(b, name), equal_nan=name == "values"), name
            assert [(u.kind, u.name, u.joints) for u in a.units] == [(u.kind, u.name, u.joints) for u in b.units]
            assert (a.scale_px, a.scale_rows, a.scale_s, a.roll_deg, a.step_s, a.version) == (
                b.scale_px, b.scale_rows, b.scale_s, b.roll_deg, b.step_s, b.version,
            )  # fmt: skip
            assert a.min_segment_length is None and b.min_segment_length is None


def test_t_cmp_01i_below_equal_and_above_the_minimum_row_by_row_whatever_the_direction():
    layer = length_layer()
    f = frame_features(layer, min_segment_length=MINIMUM_ARGUMENT)
    assert f.scale_px == 150.0
    below, valid_ = int(FeatureReason.short_segment), int(FeatureReason.valid)
    expected = {0: below, 1: valid_, 2: valid_, 3: valid_, 4: valid_, 5: valid_, 6: 23, 7: below}
    for s, code in expected.items():
        assert forearm_state(f, s)[:2] == (code == 0, code), s
    for s in range(8, N_SEG):  # 8: 7.4375 px is below the minimum too; the rest is a third of a trunk long
        assert forearm_state(f, s)[:2] == ((s != 8), 0 if s != 8 else below), s
    assert np.isnan(f.values[0, col(f, "l_forearm")]).all() and np.isnan(f.values[7, col(f, "l_forearm")]).all()
    assert np.isfinite(f.values[1, col(f, "l_forearm")]).all()  # equal to the minimum is a value
    check_against_loops(layer, f, min_segment_length=MINIMUM_ARGUMENT)


def test_t_cmp_01i_one_step_of_float_either_side_of_the_minimum_decides_it():
    layer = length_layer()  # rows 1, 3, 4, 5 are exactly 0.05 of a trunk, row 0 is 0.04958 and row 2 is 0.05042
    at = frame_features(layer, min_segment_length=0.05)
    up = frame_features(layer, min_segment_length=float(np.nextafter(0.05, 1.0)))
    down = frame_features(layer, min_segment_length=float(np.nextafter(0.05, 0.0)))
    for s in (1, 3, 4, 5):
        assert forearm_state(at, s)[:2] == (True, 0) and forearm_state(down, s)[:2] == (True, 0), s
        assert forearm_state(up, s)[:2] == (False, 24), s  # 0.05 is below the next number
    for f in (at, up, down):
        assert forearm_state(f, 2)[:2] == (True, 0)  # 0.05042 is above all three
        assert forearm_state(f, 0)[:2] == (False, 24)  # 0.04958 is below all three


def test_t_cmp_01i_the_boundary_on_every_segment_of_a_body_whose_lengths_are_exact():
    layer = exact_layer(body(G, 400.0), segment=SEG)  # eight limb segments of 50 px and a trunk of 150 px, Λ = 150
    third = 50.0 / 150.0
    for minimum, short in (
        (third, set()),  # equal: every segment is a value
        (float(np.nextafter(third, 1.0)), set(SEGMENTS9) - {"trunk"}),  # one step above: the limbs are short
        (1.0, set(SEGMENTS9) - {"trunk"}),  # the trunk is exactly 1 and is enough
        (float(np.nextafter(1.0, 2.0)), set(SEGMENTS9)),  # one step above: the trunk is short too
    ):
        f = frame_features(layer, min_segment_length=minimum)
        assert f.scale_px == 150.0
        for name in SEGMENTS9:
            want = (False, 24, False) if name in short else (True, 0, False)
            assert all(state(f, s, name) == want for s in range(N_SEG)), (minimum, name)
        assert f.valid[:, :12].all()  # the positions never look at a length
        check_against_loops(layer, f, min_segment_length=minimum)


def test_t_cmp_01i_a_short_segment_does_not_touch_the_other_segments_or_the_other_rows():
    layer = length_layer()
    f = frame_features(layer, min_segment_length=MINIMUM_ARGUMENT)
    assert forearm_state(f, 0)[:2] == (False, 24) and forearm_state(f, 7)[:2] == (False, 24)  # the cut
    others = [n for n in [*JOINTS12, *SEGMENTS9] if n != "l_forearm"]
    for s in range(N_SEG):
        if s in (8, 9, 10):
            continue  # bridged rows are looked at below
        assert all(state(f, s, n) == (True, 0, False) for n in others), s
    base = frame_features(layer)
    assert forearm_state(base, 0) == (True, 0, False) and forearm_state(base, 6)[:2] == (False, 23)  # no minimum
    for name in ("values", "valid", "reason", "bridged"):
        a, b = getattr(f, name), getattr(base, name)
        keep = [u for u in range(21) if u != col(f, "l_forearm")]
        assert np.array_equal(a[:, keep], b[:, keep], equal_nan=name == "values"), name


def test_t_cmp_01i_the_wavy_body_matches_the_independent_loops_for_minimums_between_its_lengths():
    layer = wavy_layer()
    ratios = length_ratios(layer)
    flat = np.sort(ratios.ravel())
    counts = set()
    for q in (0.1, 0.3, 0.5, 0.8):
        window = flat[int(q * len(flat)) : int(q * len(flat)) + 12]
        gap = int(np.argmax(np.diff(window)))
        assert window[gap + 1] - window[gap] > 1e-4  # no length within float of the minimum
        minimum = float((window[gap] + window[gap + 1]) / 2.0)
        f = frame_features(layer, min_segment_length=minimum)
        check_against_loops(layer, f, min_segment_length=minimum)
        invalid = ~f.valid[:, ANGLES]
        assert invalid.any() and not invalid.all()  # the minimum cuts somewhere
        assert np.array_equal(invalid, ratios < minimum)
        assert (f.reason[:, ANGLES][invalid] == 24).all() and (f.reason[:, ANGLES][~invalid] == 0).all()
        counts.add(tuple(invalid.sum(axis=0)))
    assert len(counts) == 4  # four minimums, four different cuts, and a different number of rows per segment
    assert any(len(set(c)) > 1 for c in counts)


def test_t_cmp_01i_the_scenario_keeps_every_pose_reason_and_zero_length_before_the_new_ones():
    layer = scenario_layer()
    f = frame_features(layer, min_segment_length=0.4)  # every limb segment of the wavy body is about a third long
    check_against_loops(layer, f, min_segment_length=0.4)
    base = frame_features(layer)
    for s, name in ((1, "l_forearm"), (2, "l_thigh"), (3, "l_forearm"), (5, "l_upper_arm"), (4, "r_thigh")):
        assert state(f, s, name)[1] == state(base, s, name)[1] != 24, (s, name)  # a missing joint is not a short one
    assert state(f, 6, "l_forearm")[1] == 23 and state(f, 7, "trunk")[1] == 23  # zero length first
    big = frame_features(layer, min_segment_length=100.0)  # nothing is long enough
    want = np.where(base.reason[:, ANGLES] == 0, 24, base.reason[:, ANGLES])
    assert np.array_equal(big.reason[:, ANGLES], want)
    assert not big.valid[:, ANGLES].any() and np.isnan(big.values[:, ANGLES]).all()
    tiny = frame_features(layer, min_segment_length=1e-12)  # nothing is short: the run of None
    for name in ("values", "valid", "reason", "bridged"):
        assert np.array_equal(getattr(tiny, name), getattr(base, name), equal_nan=name == "values"), name


def test_t_cmp_01i_positions_are_never_touched_by_the_minimum():
    for layer in (wavy_layer(), scenario_layer()):
        base, big = frame_features(layer), frame_features(layer, min_segment_length=100.0)
        for name in ("values", "valid", "reason", "bridged"):
            a, b = getattr(big, name)[:, :12], getattr(base, name)[:, :12]
            assert np.array_equal(a, b, equal_nan=name == "values"), name
        assert (big.scale_px, big.scale_rows, big.scale_s) == (base.scale_px, base.scale_rows, base.scale_s)


def test_t_cmp_01i_without_a_scale_a_minimum_in_trunk_lengths_cannot_be_applied_so_the_angles_are_19():
    layer = exact_layer(body(G, 400.0, trunk=0.0), segment=SEG)  # no trunk in any row: Λ is NaN
    k, r, i = cells(layer)
    k[SEG[0] + 2, LW] = k[SEG[0] + 2, LE]  # a forearm with no length
    drop(k, r, SEG[0] + 3, LW, 1)  # a missing joint
    layer = edited(layer, keypoints=k, reason=r)
    plain = frame_features(layer)  # without a minimum an angle needs no Λ
    f = frame_features(layer, min_segment_length=MINIMUM_ARGUMENT)
    assert math.isnan(f.scale_px)
    for s in range(N_SEG):
        for name in SEGMENTS9:
            if name == "trunk":
                assert state(f, s, name) == (False, 23, False), s  # zero length first
            elif (s, name) == (2, "l_forearm"):
                assert state(f, s, name) == (False, 23, False)  # zero length before 19
            elif (s, name) == (3, "l_forearm"):
                assert state(f, s, name) == (False, 1, False)  # a missing joint before 19
            else:
                assert state(f, s, name) == (False, 19, False), (s, name)
                assert state(plain, s, name) == (True, 0, False), (s, name)
    assert np.isnan(f.values[:, ANGLES]).all()
    assert np.array_equal(f.reason[:, :12], plain.reason[:, :12])  # the positions say 19 either way
    check_against_loops(layer, f, min_segment_length=MINIMUM_ARGUMENT)


def test_t_cmp_01i_a_scale_withheld_by_min_scale_s_has_the_same_effect_and_no_minimum_means_no_effect():
    layer = wavy_layer()
    plain = frame_features(layer, min_scale_s=1.5)  # Λ withheld: 30 rows last 1 s
    f = frame_features(layer, min_scale_s=1.5, min_segment_length=MINIMUM_ARGUMENT)
    assert math.isnan(f.scale_px) and plain.valid[:, ANGLES].all()
    assert (f.reason[:, ANGLES] == 19).all() and not f.valid[:, ANGLES].any()
    assert np.array_equal(f.reason[:, :12], plain.reason[:, :12])


def test_t_cmp_01i_a_bridge_is_flagged_only_on_a_row_that_is_a_value():
    f = frame_features(length_layer(), min_segment_length=MINIMUM_ARGUMENT)
    assert forearm_state(f, 8) == (False, 24, False)  # the elbow is bridged but the forearm is short: no flag
    assert state(f, 8, "l_upper_arm") == (True, 0, True) and state(f, 8, "LElbow") == (True, 0, True)
    assert forearm_state(f, 9) == (True, 0, True)  # a long forearm on a bridged elbow
    assert forearm_state(f, 10) == (True, 0, True) and state(f, 10, "LWrist") == (True, 0, True)
    assert not (f.bridged & ~f.valid).any()


def test_t_cmp_01i_the_minimum_is_in_trunk_lengths_so_a_scale_a_shift_and_a_roll_leave_the_mask_alone():
    kp = wavy()
    base_layer = exact_layer(kp, segment=SEG)
    ratios = length_ratios(base_layer)
    flat = np.sort(ratios.ravel())
    window = flat[len(flat) // 2 - 12 : len(flat) // 2 + 12]
    gap = int(np.argmax(np.diff(window)))
    assert window[gap + 1] - window[gap] > 2e-3  # room for the float32 storage of a moved body
    minimum = float((window[gap] + window[gap + 1]) / 2.0)
    base = frame_features(base_layer, min_segment_length=minimum)
    assert base.valid[:, ANGLES].any() and not base.valid[:, ANGLES].all()
    for scale in (0.5, 2.0, 1.7):
        moved = frame_features(
            exact_layer(kp * scale + np.array([-33.0, 71.0]), segment=SEG), min_segment_length=minimum
        )
        assert np.array_equal(moved.reason, base.reason), scale
    for beta in (5.0, -30.0, 45.0):
        rolled = frame_features(exact_layer(camera(kp, beta), segment=SEG), roll_deg=beta, min_segment_length=minimum)
        assert np.array_equal(rolled.reason, base.reason), beta
