"""T-TRK-geometry: hull, IoU and usable boxes shared by P3.04 and P3.05."""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.track.geometry import iou, iou_to_box, keypoint_hull, usable_boxes


def test_usable_boxes_need_finite_values_and_an_area():
    boxes = np.array(
        [[0, 0, 10, 10], [0, 0, 0, 10], [5, 5, 4, 9], [np.nan, 0, 1, 1], [0, 0, np.inf, 5]], dtype=np.float64
    )
    assert usable_boxes(boxes).tolist() == [True, False, False, False, False]


def test_keypoint_hull_is_the_box_of_the_valid_keypoints_only():
    kp = np.array([[10.0, 20.0], [50.0, 80.0], [1000.0, 1000.0], [30.0, 40.0]])
    valid = np.array([True, True, False, True])

    assert keypoint_hull(kp, valid).tolist() == [10.0, 20.0, 50.0, 80.0]


@pytest.mark.parametrize(
    "valid",
    [[False, False, False], [True, False, False], [True, True, False]],
    ids=["none", "one", "two_on_a_line"],
)
def test_keypoint_hull_without_area_is_none(valid):
    kp = np.array([[10.0, 20.0], [10.0, 50.0], [3.0, 3.0]])  # the first two share x: no width
    assert keypoint_hull(kp, np.array(valid)) is None


def test_iou_known_values():
    a = np.array([0.0, 0.0, 10.0, 10.0])
    assert iou(a, a) == pytest.approx(1.0)
    assert iou(a, np.array([5.0, 0.0, 15.0, 10.0])) == pytest.approx(50 / 150)
    assert iou(a, np.array([20.0, 20.0, 30.0, 30.0])) == 0.0
    assert iou(a, np.array([2.0, 2.0, 4.0, 4.0])) == pytest.approx(4 / 100)  # a box inside another


def test_iou_to_box_gives_zero_for_unusable_rows():
    boxes = np.array([[0, 0, 10, 10], [np.nan, 0, 1, 1], [3, 3, 3, 9]], dtype=np.float64)
    assert iou_to_box(boxes, np.array([0.0, 0.0, 10.0, 10.0])).tolist() == pytest.approx([1.0, 0.0, 0.0])
