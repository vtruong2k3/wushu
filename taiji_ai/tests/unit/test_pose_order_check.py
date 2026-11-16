"""T-POSE-04a: the structure check of one HALPE_26 skeleton (P3.01).

The skeleton below is a person who faces the camera, standing upright: the person's left joints are on the right of the
image (x grows to the right, y grows down, pixels).
"""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.pose.order_check import check_joint_order
from taiji_ai.pose.skeleton import IDX, LR_PAIRS

GOOD = {
    "Nose": (500, 150), "LEye": (520, 140), "REye": (480, 140), "LEar": (540, 150), "REar": (460, 150),
    "LShoulder": (580, 250), "RShoulder": (420, 250), "LElbow": (600, 350), "RElbow": (400, 350),
    "LWrist": (610, 450), "RWrist": (390, 450), "LHip": (550, 500), "RHip": (450, 500),
    "LKnee": (555, 650), "RKnee": (445, 650), "LAnkle": (555, 800), "RAnkle": (445, 800),
    "Head": (500, 100), "Neck": (500, 230), "Hip": (500, 500),
    "LBigToe": (570, 830), "RBigToe": (430, 830), "LSmallToe": (585, 825), "RSmallToe": (415, 825),
    "LHeel": (555, 820), "RHeel": (445, 820),
}  # fmt: skip


def _skeleton() -> tuple[np.ndarray, np.ndarray]:
    kp = np.zeros((26, 2), np.float32)
    for name, xy in GOOD.items():
        kp[IDX[name]] = xy
    return kp, np.full(26, 0.9, np.float32)


def _status(report, name: str) -> str:
    return next(c.status for c in report.checks if c.name == name)


def test_t_pose_04a_a_good_skeleton_passes_every_check():
    kp, sc = _skeleton()

    report = check_joint_order(kp, sc)

    assert report.ok
    assert [c.status for c in report.checks] == ["pass"] * len(report.checks), report.checks
    assert report.facing_side == "left_on_image_right"


def test_t_pose_04a_a_person_who_turns_his_back_is_consistent_the_other_way():
    kp, sc = _skeleton()
    kp[:, 0] = 1000 - kp[:, 0]  # the same pose seen from behind: the left joints are on the left of the image

    report = check_joint_order(kp, sc)

    assert report.ok
    assert report.facing_side == "left_on_image_left"


def test_t_pose_04a_a_global_left_right_swap_is_only_caught_by_eye():
    """Every L and R label swapped looks like a person seen from behind: the structure is consistent, the report
    says which side the left joints are on, and a frame with the face visible (the visual check) decides."""
    kp, sc = _skeleton()
    perm = list(range(26))
    for a, b in LR_PAIRS:
        perm[a], perm[b] = b, a

    report = check_joint_order(kp[perm], sc[perm])

    assert report.ok
    assert report.facing_side == "left_on_image_left"


@pytest.mark.parametrize("pair", [(5, 6), (11, 12), (13, 14), (15, 16)], ids=["shoulders", "hips", "knees", "ankles"])
def test_t_pose_04a_one_swapped_left_right_pair_is_caught(pair: tuple[int, int]):
    kp, sc = _skeleton()
    a, b = pair
    kp[[a, b]] = kp[[b, a]]

    report = check_joint_order(kp, sc)

    assert not report.ok
    assert _status(report, "left_right_sides") == "fail"


def test_t_pose_04a_a_turned_head_does_not_decide_the_side_rule():
    """Found on a real frame (P3.01): the head turns independently of the body; in a profile the model puts the hidden
    ear and eye on the other side. The eyes and the ears must not vote, or a correct index is reported as a failure."""
    kp, sc = _skeleton()
    kp[[IDX["LEar"], IDX["REar"]]] = kp[[IDX["REar"], IDX["LEar"]]]
    kp[[IDX["LEye"], IDX["REye"]]] = kp[[IDX["REye"], IDX["LEye"]]]

    report = check_joint_order(kp, sc)

    assert _status(report, "left_right_sides") == "pass"
    assert report.facing_side == "left_on_image_right"


def test_t_pose_04a_head_and_neck_swapped_is_caught():
    kp, sc = _skeleton()
    kp[[IDX["Head"], IDX["Neck"]]] = kp[[IDX["Neck"], IDX["Head"]]]

    report = check_joint_order(kp, sc)

    assert _status(report, "vertical_chain") == "fail"


def test_t_pose_04a_the_hip_point_far_from_the_hips_is_caught():
    kp, sc = _skeleton()
    kp[IDX["Hip"]] = (500, 700)

    assert _status(check_joint_order(kp, sc), "centre_points") == "fail"


def test_t_pose_04a_a_toe_far_from_its_ankle_is_caught():
    kp, sc = _skeleton()
    kp[IDX["LBigToe"]] = (570, 100)

    assert _status(check_joint_order(kp, sc), "feet_near_ankles") == "fail"


def test_t_pose_04a_the_two_foot_groups_swapped_are_caught():
    kp, sc = _skeleton()
    left, right = [IDX["LBigToe"], IDX["LSmallToe"], IDX["LHeel"]], [IDX["RBigToe"], IDX["RSmallToe"], IDX["RHeel"]]
    kp[left + right] = kp[right + left]

    report = check_joint_order(kp, sc)

    assert _status(report, "feet_near_ankles") == "fail"
    assert _status(report, "left_right_sides") == "fail"


def test_t_pose_04a_a_low_score_is_undecidable_never_a_pass():
    kp, sc = _skeleton()
    sc[[IDX["LAnkle"], IDX["RAnkle"]]] = 0.1

    report = check_joint_order(kp, sc)

    assert _status(report, "vertical_chain") == "undecidable"
    assert _status(report, "feet_near_ankles") == "undecidable"
    assert report.ok  # nothing failed; nothing was proved either


def test_t_pose_04a_a_nan_keypoint_is_not_available():
    kp, sc = _skeleton()
    kp[IDX["Nose"]] = np.nan

    assert _status(check_joint_order(kp, sc), "vertical_chain") == "undecidable"


def test_t_pose_04a_a_person_lying_down_is_undecidable():
    kp, sc = _skeleton()
    kp = kp[:, ::-1].copy()  # x and y exchanged: the body now lies along x

    report = check_joint_order(kp, sc)

    assert _status(report, "vertical_chain") == "undecidable"
    assert _status(report, "centre_points") == "undecidable"
    assert _status(report, "left_right_sides") == "undecidable"
    assert report.facing_side is None


def test_t_pose_04a_wrong_shapes_are_refused():
    kp, sc = _skeleton()
    with pytest.raises(ValueError, match="26"):
        check_joint_order(kp[:25], sc[:25])
    with pytest.raises(ValueError, match="scores"):
        check_joint_order(kp, sc[:20])
