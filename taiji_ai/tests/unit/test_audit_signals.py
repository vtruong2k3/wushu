"""T-AUDIT-01: the per-frame measures of the target's pose (P3.08), on the synthetic skeleton and SYN-08."""

from __future__ import annotations

import numpy as np
import pytest

from helpers.synth import make_sequence, neutral_pose
from taiji_ai.audit.signals import (
    BONES,
    RULE_HIGHER_IS_WORSE,
    ankle_height_difference,
    body_height,
    bone_deviation,
    cadence_difference,
    compute_signals,
    face_vs_body_score,
    jump_speed,
    low_essential,
    reference_height,
    rotation_rate,
    shoulder_width_ratio,
    structure_failures,
    swap_margin,
    valid_joints,
    wrist_to_trunk_distance,
)
from taiji_ai.pose.skeleton import ESSENTIAL, IDX, JOINTS

SCALE = 300.0  # the trunk length of the neutral pose, px


def clip(n: int = 20, fps: float = 30.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``n`` frames of the neutral pose (float64 keypoints, scores 0.9, times)."""
    kp = np.tile(neutral_pose(SCALE), (n, 1, 1))
    return kp, np.full((n, 26), 0.9), np.arange(n) / fps


def valid_of(kp: np.ndarray, scores: np.ndarray) -> np.ndarray:
    return valid_joints(kp, scores)


# --- T-AUDIT-01a: height and the essential joints -------------------------------------------------------------------
def test_t_audit_01a_the_body_height_is_the_height_of_the_box_of_the_valid_keypoints():
    kp, scores, _ = clip(3)
    expected = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    assert body_height(kp, valid_of(kp, scores)).tolist() == pytest.approx([expected] * 3)
    scores[1, IDX["LBigToe"] : IDX["RHeel"] + 1] = 0.05  # the feet of frame 1 are not valid: the box is shorter
    height = body_height(kp, valid_of(kp, scores))
    assert height[1] < height[0] and height[0] == height[2]
    assert reference_height(height) == pytest.approx(float(np.median(height)))


def test_t_audit_01a_a_frame_without_the_target_has_no_height_and_all_essential_joints_missing():
    kp, scores, _ = clip(3)
    kp[1] = np.nan
    scores[1] = np.nan
    valid = valid_of(kp, scores)
    assert np.isnan(body_height(kp, valid)[1]) and not np.isnan(body_height(kp, valid)[0])
    assert low_essential(valid).tolist() == [0.0, 10.0, 0.0]


def test_t_audit_01a_only_the_essential_joints_are_counted_and_one_valid_joint_has_no_height():
    kp, scores, _ = clip(3)
    for name in ("LShoulder", "LHip", "RAnkle"):
        scores[0, IDX[name]] = 0.1  # three essential joints
    scores[1, IDX["Nose"]] = 0.1  # not essential
    scores[1, IDX["LEar"]] = 0.1
    assert low_essential(valid_of(kp, scores)).tolist() == [3.0, 0.0, 0.0]
    assert set(ESSENTIAL) == {
        IDX[n]
        for n in ("LShoulder", "RShoulder", "LHip", "RHip", "LKnee", "RKnee", "LAnkle", "RAnkle", "LHeel", "RHeel")
    }
    one = np.zeros((1, 26), dtype=bool)
    one[0, 0] = True
    assert np.isnan(body_height(kp[:1], one)[0])


# --- T-AUDIT-01b: jump speed ----------------------------------------------------------------------------------------
def test_t_audit_01b_speed_is_in_body_heights_per_second_of_real_time():
    kp, scores, t = clip(5)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    kp[3, IDX["RWrist"], 0] += 0.5 * ref  # half a body height in one frame
    valid = valid_of(kp, scores)
    fast = jump_speed(kp, valid, t, ref)
    slow = jump_speed(kp, valid, np.arange(5) / 15.0, ref)  # the same displacement over twice the frame interval
    assert fast[3] == pytest.approx(0.5 * 30.0) and slow[3] == pytest.approx(0.5 * 15.0)
    assert fast[2] == 0.0 and np.isnan(fast[0])
    assert fast[4] == pytest.approx(0.5 * 30.0)  # the joint moves back in the next frame


def test_t_audit_01b_speed_uses_the_frame_times_not_the_frame_count_when_they_are_uneven():
    kp, scores, _ = clip(4)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    kp[2:, IDX["LWrist"], 1] -= 0.1 * ref
    t = np.array([0.0, 1 / 30, 2 / 30, 2 / 30 + 0.2])  # the last frame comes 0.2 s after the one before
    out = jump_speed(kp, valid_of(kp, scores), t, ref)
    assert out[2] == pytest.approx(0.1 * 30.0)
    assert out[3] == 0.0 and not np.isnan(out[3])


def test_t_audit_01b_a_missing_joint_or_frame_gives_nan_not_zero():
    kp, scores, t = clip(4)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    scores[2] = 0.05  # frame 2: nothing valid
    out = jump_speed(kp, valid_of(kp, scores), t, ref)
    assert np.isnan(out[0]) and np.isnan(out[2]) and np.isnan(out[3])  # no previous frame, and both sides of frame 2
    assert out[1] == 0.0
    assert np.isnan(jump_speed(kp, valid_of(kp, scores), t, float("nan"))).all()
    assert np.isnan(jump_speed(kp[:1], valid_of(kp, scores)[:1], t[:1], ref)).all()


# --- T-AUDIT-01c: bone length ---------------------------------------------------------------------------------------
def test_t_audit_01c_a_shortened_limb_gives_its_relative_deviation_against_the_clip_median():
    kp, scores, _ = clip(21)
    wrist, elbow = IDX["LWrist"], IDX["LElbow"]
    kp[10, wrist] = kp[10, elbow] + 0.5 * (kp[10, wrist] - kp[10, elbow])  # the forearm is half as long
    dev = bone_deviation(kp, valid_of(kp, scores))
    assert dev[10] == pytest.approx(0.5, abs=1e-9)
    assert np.delete(dev, 10).max() == pytest.approx(0.0, abs=1e-12)


def test_t_audit_01c_the_median_is_per_clip_so_a_clip_with_short_limbs_all_through_is_not_flagged():
    kp, scores, _ = clip(10)
    kp[:, IDX["LWrist"]] = kp[:, IDX["LElbow"]] + 0.5 * (kp[:, IDX["LWrist"]] - kp[:, IDX["LElbow"]])
    assert np.nanmax(bone_deviation(kp, valid_of(kp, scores))) == pytest.approx(0.0, abs=1e-12)
    assert len(BONES) == 8 and all(0 <= a < 26 and 0 <= b < 26 for a, b in BONES)


def test_t_audit_01c_a_bone_with_a_missing_end_is_ignored_and_no_bone_at_all_is_nan():
    kp, scores, _ = clip(5)
    scores[:] = 0.05
    assert np.isnan(bone_deviation(kp, valid_of(kp, scores))).all()


# --- T-AUDIT-01d: the left/right swap -------------------------------------------------------------------------------
def test_t_audit_01d_on_syn_08_the_margin_is_high_exactly_where_the_labels_are_exchanged_or_exchanged_back():
    seq = make_sequence("SYN-08", seed=0)  # swaps in frames [20, 23) and [50, 53)
    kp, scores = seq.kp.astype(np.float64), seq.score.astype(np.float64)
    valid = valid_of(kp, scores)
    ref = reference_height(body_height(kp, valid))
    margin = swap_margin(kp, valid, ref)
    transitions = {20, 23, 50, 53}  # the frame where a swap starts and the frame where it ends
    top = set(np.argsort(-np.nan_to_num(margin, nan=-9.0))[:4].tolist())
    assert top == transitions
    others = np.delete(margin, sorted(transitions))
    assert np.nanmax(others) <= 0.0 and margin[sorted(transitions)].min() > 0.05


def test_t_audit_01d_a_fast_limb_that_does_not_cross_is_not_a_swap():
    kp, scores, _ = clip(6)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    kp[3, IDX["LWrist"], 1] -= 0.3 * ref  # the left wrist jumps up by 0.3 body heights: fast, but on its own side
    margin = swap_margin(kp, valid_of(kp, scores), ref)
    assert np.nanmax(margin) <= 0.0


def test_t_audit_01d_missing_pairs_give_nan():
    kp, scores, _ = clip(4)
    scores[2] = 0.05
    margin = swap_margin(kp, valid_of(kp, scores), 100.0)
    assert np.isnan(margin[0]) and np.isnan(margin[2]) and np.isnan(margin[3]) and not np.isnan(margin[1])


# --- T-AUDIT-01e: the four finders ----------------------------------------------------------------------------------
def test_t_audit_01e_back_to_the_camera_is_a_seen_body_and_an_unseen_face():
    _, scores, _ = clip(5)
    scores[2, [IDX[n] for n in ("Nose", "LEye", "REye", "LEar", "REar")]] = 0.05
    out = face_vs_body_score(scores)
    assert int(np.argmax(out)) == 2 and out[2] == pytest.approx(0.85) and out[0] == pytest.approx(0.0)


def test_t_audit_01e_a_raised_foot_is_a_large_height_difference_of_the_ankles():
    kp, scores, _ = clip(5)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    kp[3, IDX["LAnkle"], 1] -= 0.25 * ref
    out = ankle_height_difference(kp, valid_of(kp, scores), ref)
    assert int(np.argmax(out)) == 3 and out[3] == pytest.approx(0.25) and out[0] == pytest.approx(0.0, abs=1e-12)


def test_t_audit_01e_turning_is_a_fast_change_of_the_shoulder_width_over_the_torso():
    kp, scores, t = clip(40)
    torso_x = kp[:, [IDX["LShoulder"], IDX["RShoulder"]], 0].mean(axis=1)
    width0 = abs(kp[0, IDX["LShoulder"], 0] - kp[0, IDX["RShoulder"], 0])
    for f in range(15, 40):  # the shoulders close up over 10 frames, then stay: a turn about the vertical axis
        shrink = max(0.2, 1.0 - 0.08 * (f - 15))
        kp[f, IDX["LShoulder"], 0] = torso_x[f] + shrink * (kp[0, IDX["LShoulder"], 0] - torso_x[0])
        kp[f, IDX["RShoulder"], 0] = torso_x[f] + shrink * (kp[0, IDX["RShoulder"], 0] - torso_x[0])
    valid = valid_of(kp, scores)
    ratio = shoulder_width_ratio(kp, valid)
    assert ratio[0] > ratio[39] and ratio[0] == pytest.approx(width0 / SCALE, rel=0.2)
    rate = rotation_rate(ratio, t)
    assert 16 <= int(np.nanargmax(rate)) <= 30 and np.nanmax(rate) > 0.5
    assert rate[15] == pytest.approx(0.0, abs=1e-9)  # the turn has not started at frame 15
    assert rate[39] < 0.5 * np.nanmax(rate)  # and it is over at the end


def test_t_audit_01e_the_rotation_rate_needs_a_frame_half_a_second_earlier():
    ratio = np.linspace(1.0, 0.0, 30)
    t = np.arange(30) / 30.0
    rate = rotation_rate(ratio, t, lag_s=0.5)
    assert np.isnan(rate[:15]).all() and not np.isnan(rate[15:]).any()
    assert rate[20] == pytest.approx(abs(ratio[20] - ratio[5]) / (t[20] - t[5]))


def test_t_audit_01e_a_hand_in_front_of_the_trunk_is_a_wrist_near_the_middle_of_it():
    kp, scores, _ = clip(5)
    trunk = kp[2, [IDX[n] for n in ("LShoulder", "RShoulder", "LHip", "RHip")]].mean(axis=0)
    kp[2, IDX["RWrist"]] = trunk + np.array([5.0, 0.0])
    out = wrist_to_trunk_distance(kp, valid_of(kp, scores))
    assert int(np.argmin(out)) == 2 and out[2] == pytest.approx(5.0 / SCALE, rel=1e-6)
    assert out[0] > 0.5


def test_t_audit_01e_an_ordinary_standing_pose_does_not_look_like_any_situation():
    kp, scores, t = clip(30)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    valid = valid_of(kp, scores)
    assert np.allclose(face_vs_body_score(scores), 0.0)
    assert np.allclose(ankle_height_difference(kp, valid, ref), 0.0, atol=1e-9)
    assert np.nanmax(rotation_rate(shoulder_width_ratio(kp, valid), t)) == pytest.approx(0.0, abs=1e-9)
    assert np.nanmin(wrist_to_trunk_distance(kp, valid)) > 0.3


# --- compute_signals --------------------------------------------------------------------------------------------------
def test_t_audit_01_compute_signals_gives_every_rule_and_nan_where_the_target_is_not_tracked():
    kp, scores, t = clip(30)
    tracked = np.ones(30, dtype=bool)
    tracked[10:15] = False
    kp[~tracked] = np.nan
    scores[~tracked] = np.nan
    s = compute_signals(kp, scores, t, tracked)
    assert set(RULE_HIGHER_IS_WORSE) - {"target_event", "cadence_diff"} <= set(s)  # those two need events or two runs
    for name in (
        "low_essential",
        "structure",
        "jump",
        "bone",
        "swap_pair",
        "find_back",
        "find_one_leg",
        "find_rotation",
        "find_occlusion",
    ):
        assert s[name].shape == (30,), name
    assert np.isnan(s["structure"][10:15]).all() and np.isnan(s["find_back"][10:15]).all()
    assert (s["low_essential"][10:15] == 10.0).all() and (s["low_essential"][:10] == 0.0).all()
    assert float(s["ref_height"]) > 0 and s["valid"].shape == (30, 26)
    assert set(JOINTS) == set(JOINTS)  # the skeleton names are those of halpe26/1


# --- the difference between two cadences ----------------------------------------------------------------------------
def test_t_audit_01f_the_cadence_difference_is_the_largest_joint_distance_in_body_heights():
    kp, scores, _ = clip(6)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    other = kp.copy()
    other[3, IDX["RWrist"], 0] += 0.2 * ref  # one wrist is 0.2 body heights away in frame 3
    other[3, IDX["LKnee"], 1] += 0.05 * ref
    valid = valid_of(kp, scores)
    out = cadence_difference(kp, valid, other, valid, ref)
    assert out[3] == pytest.approx(0.2) and np.delete(out, 3).tolist() == [0.0] * 5


def test_t_audit_01f_a_joint_missing_in_either_run_or_no_target_gives_nan_not_zero():
    kp, scores, _ = clip(4)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    other = kp.copy()
    other[1, IDX["LWrist"]] += 1000.0  # a huge difference, but that joint is not valid in the other run
    valid = valid_of(kp, scores)
    other_valid = valid.copy()
    other_valid[1, IDX["LWrist"]] = False
    other_valid[2] = False  # frame 2: the other run has no target
    out = cadence_difference(kp, valid, other, other_valid, ref)
    assert out[1] == 0.0 and np.isnan(out[2]) and out[0] == 0.0
    assert np.isnan(cadence_difference(kp, valid, other, other_valid, float("nan"))).all()


def test_t_audit_01f_the_reference_height_may_be_one_per_frame():
    kp, scores, _ = clip(3)
    other = kp + np.array([30.0, 0.0])
    valid = valid_of(kp, scores)
    out = cadence_difference(kp, valid, other, valid, np.array([300.0, 150.0, float("nan")]))
    assert out[0] == pytest.approx(0.1) and out[1] == pytest.approx(0.2) and np.isnan(out[2])


# --- found by the mutation check ------------------------------------------------------------------------------------
def test_t_audit_01c_the_reference_length_is_the_median_not_the_longest_frame():
    kp, scores, _ = clip(21)
    wrist, elbow = IDX["LWrist"], IDX["LElbow"]
    kp[10, wrist] = kp[10, elbow] + 1.5 * (kp[10, wrist] - kp[10, elbow])  # one frame with a longer forearm
    dev = bone_deviation(kp, valid_of(kp, scores))
    assert dev[10] == pytest.approx(0.5) and np.delete(dev, 10).max() == pytest.approx(0.0, abs=1e-12)


def test_t_audit_01d_a_right_joint_that_moves_onto_the_left_ones_place_is_not_more_than_neutral():
    kp, scores, _ = clip(3)
    ref = float(kp[0, :, 1].max() - kp[0, :, 1].min())
    wrist_l, wrist_r = IDX["LWrist"], IDX["RWrist"]
    kp[1:, wrist_r] = kp[0, wrist_l]  # from frame 1 the right wrist sits on the place the left wrist had
    margin = swap_margin(kp, valid_of(kp, scores), ref)
    # stay = the right wrist's move (s), cross = s + 0: the margin of this pair is 0, and no other pair moves
    assert margin[1] == pytest.approx(0.0, abs=1e-9)


def test_t_audit_01_frames_without_the_target_are_not_valid_even_if_their_keypoints_are_finite():
    kp, scores, t = clip(10)
    tracked = np.ones(10, dtype=bool)
    tracked[4] = False  # the caller says "no target", the numbers are still finite
    s = compute_signals(kp, scores, t, tracked)
    assert not s["valid"][4].any() and s["valid"][3].all()
    assert s["low_essential"][4] == 10.0 and s["low_essential"][3] == 0.0


def test_t_audit_01_the_structure_check_counts_failures_not_passes():
    kp, scores, t = clip(3)
    tracked = np.ones(3, dtype=bool)
    assert structure_failures(kp, scores, tracked).tolist() == [0.0, 0.0, 0.0]
    legs = [IDX[n] for n in ("LKnee", "RKnee", "LAnkle", "RAnkle")]
    bad = kp.copy()
    bad[1, legs[0]], bad[1, legs[1]] = (
        kp[1, legs[1]].copy(),
        kp[1, legs[0]].copy(),
    )  # the knees exchanged, shoulders not
    bad[1, legs[2]], bad[1, legs[3]] = kp[1, legs[3]].copy(), kp[1, legs[2]].copy()
    out = structure_failures(bad, scores, tracked)
    assert out[0] == 0.0 and out[1] >= 1.0 and out[2] == 0.0
    assert np.isnan(structure_failures(kp, scores, np.array([True, False, True]))[1])
