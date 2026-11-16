"""T-POSE-05e: ``box_from_keypoints``, the box of the next frame from the keypoints of the previous one (P3.02)."""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.pose.runner import box_from_keypoints

SIZE = (640, 480)  # (width, height) of the image, pixels


def _person(x0=200.0, y0=100.0, x1=300.0, y1=400.0, valid=26):
    """26 keypoints spread over the box [x0, y0, x1, y1]; the first ``valid`` have a high score."""
    j = np.arange(26)
    kp = np.stack([x0 + (x1 - x0) * (j % 2), y0 + (y1 - y0) * j / 25.0], axis=1).astype(np.float64)
    scores = np.where(j < valid, 0.9, 0.05)
    return kp, scores


def test_t_pose_05e_the_box_is_the_valid_keypoints_widened_by_the_margin_on_each_side():
    kp, sc = _person()
    box = box_from_keypoints(kp, sc, SIZE, margin=0.10, min_score=0.3, min_valid=6)
    assert box is not None
    # width 100 and height 300: 10 % is 10 px and 30 px on each side
    np.testing.assert_allclose(box, [190.0, 70.0, 310.0, 430.0], atol=1e-6)
    assert box.dtype == np.float32 and box.shape == (4,)


def test_t_pose_05e_margin_zero_is_exactly_the_hull():
    kp, sc = _person()
    np.testing.assert_allclose(
        box_from_keypoints(kp, sc, SIZE, margin=0.0, min_score=0.3, min_valid=6), [200, 100, 300, 400]
    )


def test_t_pose_05e_the_box_is_clipped_to_the_image():
    kp, sc = _person(x0=-30.0, y0=-20.0, x1=660.0, y1=500.0)
    box = box_from_keypoints(kp, sc, SIZE, margin=0.10, min_score=0.3, min_valid=6)
    np.testing.assert_allclose(box, [0.0, 0.0, 640.0, 480.0])


def test_t_pose_05e_keypoints_under_the_score_limit_do_not_widen_the_box():
    kp, sc = _person(valid=10)
    kp[20] = (5.0, 5.0)  # a wild keypoint with a low score: it must be ignored
    box = box_from_keypoints(kp, sc, SIZE, margin=0.0, min_score=0.3, min_valid=6)
    assert box is not None and box[0] >= 200.0 and box[1] >= 100.0


def test_t_pose_05e_nan_and_infinite_values_are_not_valid():
    kp, sc = _person()
    kp[3] = np.nan
    kp[4] = (np.inf, 100.0)
    sc[5] = np.nan
    box = box_from_keypoints(kp, sc, SIZE, margin=0.0, min_score=0.3, min_valid=6)
    assert box is not None and np.all(np.isfinite(box))


@pytest.mark.parametrize("valid", [0, 5])
def test_t_pose_05e_fewer_than_min_valid_keypoints_gives_no_box(valid: int):
    kp, sc = _person(valid=valid)
    assert box_from_keypoints(kp, sc, SIZE, margin=0.1, min_score=0.3, min_valid=6) is None


def test_t_pose_05e_exactly_min_valid_keypoints_is_enough():
    kp, sc = _person(valid=6)
    assert box_from_keypoints(kp, sc, SIZE, margin=0.1, min_score=0.3, min_valid=6) is not None


def test_t_pose_05e_a_box_without_area_gives_none():
    kp = np.tile(np.array([[250.0, 250.0]]), (26, 1))
    assert box_from_keypoints(kp, np.full(26, 0.9), SIZE, margin=0.1, min_score=0.3, min_valid=6) is None
    kp2 = np.stack([np.full(26, 250.0), np.linspace(100, 400, 26)], axis=1)  # zero width
    assert box_from_keypoints(kp2, np.full(26, 0.9), SIZE, margin=0.1, min_score=0.3, min_valid=6) is None


def test_t_pose_05e_wrong_shapes_are_refused():
    kp, sc = _person()
    with pytest.raises(ValueError, match="26"):
        box_from_keypoints(kp[:20], sc[:20], SIZE, margin=0.1, min_score=0.3, min_valid=6)
    with pytest.raises(ValueError, match="scores"):
        box_from_keypoints(kp, sc[:20], SIZE, margin=0.1, min_score=0.3, min_valid=6)
