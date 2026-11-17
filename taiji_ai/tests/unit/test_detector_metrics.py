"""T-DET-03, T-DET-04, T-DET-05: the metrics of the detector comparison (P3.09), on hand-made boxes and times.

Boxes are ``(x1, y1, x2, y2)`` pixels, y down; a detection is ``(x1, y1, x2, y2, score)``. No model, no video.
"""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.bench.detector_metrics import (
    agreement,
    box_iou,
    dropout_runs,
    finds,
    mcnemar_exact,
    performer_box,
    recall_paired,
    reference_box,
    stability,
)


def det(*boxes: tuple[float, float, float, float], score: float = 0.9) -> np.ndarray:
    return np.array([(*b, score) for b in boxes], np.float32).reshape(-1, 5)


# --- T-DET-03: IoU, the reference box, finding the performer -------------------------------------------------------
def test_t_det_03_iou_of_known_boxes():
    assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert box_iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)
    assert box_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert box_iou((0, 0, 10, 10), (10, 0, 20, 10)) == 0.0  # touching is not overlapping
    assert box_iou((0, 0, 0, 10), (0, 0, 10, 10)) == 0.0  # a box without area has no IoU, not a division by zero


def skeleton(valid: list[int], x0: float = 100.0, y0: float = 50.0, w: float = 80.0, h: float = 200.0):
    kp = np.full((26, 2), np.nan, np.float32)
    sc = np.full(26, 0.05, np.float32)
    corners = [(x0, y0), (x0 + w, y0 + h), (x0 + w / 2, y0 + h / 2), (x0, y0 + h)]
    for slot, j in enumerate(valid):
        kp[j] = corners[slot % 4]
        sc[j] = 0.9
    return kp, sc


def test_t_det_03_the_reference_box_is_the_hull_of_the_valid_joints_grown_by_the_margin():
    kp, sc = skeleton([0, 5, 11, 15])
    box = reference_box(kp, sc, min_score=0.3, margin=0.05)
    assert box == pytest.approx((100 - 4.0, 50 - 10.0, 180 + 4.0, 250 + 10.0))  # 5 % of 80 and of 200 on every side
    no_margin = reference_box(kp, sc, margin=0.0)
    assert no_margin == pytest.approx((100.0, 50.0, 180.0, 250.0))


def test_t_det_03_a_weak_joint_is_not_in_the_hull_and_too_few_joints_give_no_box():
    kp, sc = skeleton([0, 5, 11, 15])
    kp[20] = (900.0, 900.0)
    sc[20] = 0.1  # far away but under the score limit
    assert reference_box(kp, sc, margin=0.0) == pytest.approx((100.0, 50.0, 180.0, 250.0))
    few_kp, few_sc = skeleton([0, 5, 11])
    assert reference_box(few_kp, few_sc) is None  # three joints are not enough
    flat_kp, flat_sc = skeleton([0, 5, 11, 15], w=0.0)
    assert reference_box(flat_kp, flat_sc) is None  # no width: not a person box
    assert reference_box(np.full((26, 2), np.nan, np.float32), np.full(26, np.nan, np.float32)) is None


def test_t_det_03_a_detector_finds_the_performer_at_the_iou_limit_and_above():
    ref = (0.0, 0.0, 10.0, 10.0)
    assert finds(det((0, 0, 10, 10)), ref)
    assert finds(det((0, 0, 10, 20)), ref, iou_min=0.5)  # IoU exactly 0.5 counts
    assert not finds(det((0, 0, 10, 21)), ref, iou_min=0.5)
    assert finds(det((50, 50, 60, 60), (0, 0, 10, 10)), ref)  # any of the boxes
    assert not finds(det(), ref)  # nothing detected
    assert not finds(det((0, 0, 10, 10)), None)  # no reference, nothing to find


def test_t_det_03_the_performer_is_the_largest_box_of_at_least_a_fifth_of_the_image_height():
    boxes = det((0, 0, 50, 300), (100, 0, 400, 250), (500, 0, 520, 90))  # areas 15000, 75000, 1800
    picked = performer_box(boxes, image_height=1000, min_height_frac=0.2)
    assert picked is not None and picked.tolist() == pytest.approx([100.0, 0.0, 400.0, 250.0])
    assert performer_box(det((500, 0, 520, 90)), 1000, 0.2) is None  # too small: a person far behind
    assert performer_box(det(), 1000, 0.2) is None
    assert performer_box(det((0, 0, 50, 200)), 1000, 0.2) is not None  # exactly 20 % counts


# --- T-DET-04: stability --------------------------------------------------------------------------------------------
def test_t_det_04_a_box_that_does_not_move_has_no_jitter():
    boxes = [np.array([100.0, 100.0, 200.0, 400.0])] * 10
    s = stability(boxes, np.arange(10) / 30.0)
    assert s["pairs"] == 9 and s["jumps"] == 0
    assert s["one_minus_iou"]["p50"] == 0.0 and s["one_minus_iou"]["p95"] == 0.0
    assert s["height_change"]["p95"] == 0.0


def test_t_det_04_a_known_shift_gives_the_known_one_minus_iou_and_a_jump_is_counted_under_half():
    still = np.array([0.0, 0.0, 10.0, 10.0])
    shifted = np.array([5.0, 0.0, 15.0, 10.0])  # IoU 1/3
    s = stability([still, still, shifted, shifted], np.arange(4) / 30.0)
    assert s["pairs"] == 3 and s["jumps"] == 1  # only the pair still -> shifted has IoU under 0.5
    assert s["one_minus_iou"]["p50"] == 0.0 and s["one_minus_iou"]["p99"] == pytest.approx(2 / 3, abs=0.02)


def test_t_det_04_frames_without_a_box_break_the_pairs_instead_of_pairing_across_the_gap():
    box = np.array([0.0, 0.0, 10.0, 10.0])
    s = stability([box, box, None, None, box, box], np.arange(6) / 30.0)
    assert s["pairs"] == 2  # (0,1) and (4,5): nothing is paired over the missing frames
    assert s["frames_with_box"] == 4 and s["frames"] == 6


def test_t_det_04_the_height_change_is_against_the_median_of_the_neighbours():
    boxes = (
        [np.array([0.0, 0.0, 10.0, 100.0])] * 5
        + [np.array([0.0, 0.0, 10.0, 150.0])]
        + [np.array([0.0, 0.0, 10.0, 100.0])] * 5
    )
    s = stability(boxes, np.arange(11) / 30.0)
    assert s["height_change"]["max"] == pytest.approx(0.5)  # 150 against the median 100 of its neighbours
    assert s["height_change"]["p50"] == 0.0


def test_t_det_04_no_box_at_all_gives_n_a_not_zero():
    s = stability([None, None, None], np.arange(3) / 30.0)
    assert s["pairs"] == 0 and s["one_minus_iou"] is None and s["height_change"] is None and s["jumps"] == 0


def test_t_det_04_dropout_runs_are_measured_in_seconds_of_the_clock_not_in_frames():
    own = np.array([True, True, False, False, False, True, True, False])
    other = np.array([True, True, True, True, True, True, True, True])
    t30 = np.arange(8) / 30.0
    runs = dropout_runs(own, other, t30)
    assert runs == pytest.approx(
        [3 / 30.0, 1 / 30.0]
    )  # the interior run of 3 frames, then the run at the end (one frame)
    t10 = np.arange(8) / 10.0  # the same frames at a slower rate: the same runs last three times longer
    assert dropout_runs(own, other, t10) == pytest.approx([3 / 10.0, 1 / 10.0])
    # a variable frame rate: the run lasts what the clock says
    t_vfr = np.array([0.0, 0.1, 0.2, 0.9, 1.0, 1.5, 1.6, 1.7])
    assert dropout_runs(own, other, t_vfr)[0] == pytest.approx(
        1.5 - 0.2
    )  # from the first missing frame to the next found one


def test_t_det_04_a_frame_where_the_other_also_misses_is_not_a_dropout():
    own = np.array([True, False, False, True])
    other = np.array([True, True, False, True])
    assert dropout_runs(own, other, np.arange(4) / 30.0) == pytest.approx([1 / 30.0])  # only frame 1


def test_t_det_04_no_dropout_gives_an_empty_list():
    assert dropout_runs(np.ones(5, bool), np.ones(5, bool), np.arange(5) / 30.0) == []


# --- T-DET-05: paired counts and the exact test ---------------------------------------------------------------------
def test_t_det_05_paired_counts():
    a = np.array([True, True, False, False, True, False])
    b = np.array([True, False, True, False, True, True])
    c = recall_paired(a, b)
    assert c == {
        "n": 6,
        "both": 2,
        "only_a": 1,
        "only_b": 2,
        "neither": 1,
        "recall_a": 0.5,
        "recall_b": pytest.approx(4 / 6),
    }
    assert agreement(a, b)["only_b"] == 2


def test_t_det_05_empty_sets_give_n_a_not_zero_rates():
    c = recall_paired(np.zeros(0, bool), np.zeros(0, bool))
    assert c["n"] == 0 and c["recall_a"] is None and c["recall_b"] is None


def test_t_det_05_arrays_of_different_length_are_refused():
    with pytest.raises(ValueError, match="same length"):
        recall_paired(np.ones(3, bool), np.ones(4, bool))


@pytest.mark.parametrize(
    ("b", "c", "p"),
    [(8, 1, 0.0390625), (5, 0, 0.0625), (3, 3, 1.0), (0, 0, 1.0), (10, 0, 0.001953125), (1, 8, 0.0390625), (2, 1, 1.0)],
)
def test_t_det_05_mcnemar_exact_two_sided_against_known_values(b: int, c: int, p: float):
    assert mcnemar_exact(b, c) == pytest.approx(p)


def test_t_det_05_mcnemar_is_symmetric_and_never_above_one():
    for b in range(0, 12):
        for c in range(0, 12):
            assert mcnemar_exact(b, c) == pytest.approx(mcnemar_exact(c, b))
            assert 0.0 < mcnemar_exact(b, c) <= 1.0


def test_t_det_04_a_pair_with_an_iou_of_exactly_half_is_not_a_jump():
    a = np.array([0.0, 0.0, 10.0, 10.0])
    b = np.array([0.0, 0.0, 10.0, 20.0])  # IoU exactly 0.5
    assert stability([a, b], np.arange(2) / 30.0)["jumps"] == 0
    c = np.array([0.0, 0.0, 10.0, 21.0])  # IoU just under half
    assert stability([a, c], np.arange(2) / 30.0)["jumps"] == 1
