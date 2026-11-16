"""T-AUDIT-05: the pictures of the review (P3.08): tiles, strips, contact sheets, on synthetic images."""

from __future__ import annotations

import numpy as np
import pytest

from helpers.synth import neutral_pose
from taiji_ai.audit.render import (
    BOX,
    caption_text,
    contact_sheet,
    draw_skeleton,
    person_crop,
    strip,
    tile,
)

H, W = 540, 960


def scene() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    image = np.full((H, W, 3), 90, dtype=np.uint8)
    kp = neutral_pose(150.0, origin=(480.0, 250.0))
    return image, kp, np.full(26, 0.9)


def test_t_audit_05_the_caption_holds_only_the_id_the_label_the_time_and_the_rules():
    assert caption_text("fc-007", "d20-v2", 12.3456, ("jump", "swap_pair")) == "fc-007  d20-v2  12.35s  jump+swap_pair"
    assert caption_text("fc-001", "d20-v1", 0.0, ("blind",)) == "fc-001  d20-v1  0.00s  blind"


def test_t_audit_05_the_crop_is_a_margin_around_every_skeleton_and_stays_inside_the_image():
    _, kp, _ = scene()
    box = person_crop((H, W), [kp])
    assert box is not None
    x0, y0, x1, y1 = box
    assert 0 <= x0 < kp[:, 0].min() and x1 > kp[:, 0].max() and 0 <= y0 < kp[:, 1].min() and y1 > kp[:, 1].max()
    assert x1 <= W and y1 <= H
    near_edge = person_crop((H, W), [kp + np.array([-470.0, -250.0])])  # the person at the top left corner
    assert near_edge is not None and near_edge[0] == 0 and near_edge[1] == 0
    both = person_crop((H, W), [kp, kp + np.array([300.0, 0.0])])
    assert both is not None and both[0] <= kp[:, 0].min() and both[2] >= kp[:, 0].max() + 300.0  # both are inside


def test_t_audit_05_no_finite_keypoint_gives_no_crop():
    assert person_crop((H, W), [np.full((26, 2), np.nan)]) is None
    assert person_crop((H, W), []) is None


def test_t_audit_05_a_tile_has_the_size_asked_and_shows_the_skeleton():
    image, kp, scores = scene()
    plain = tile(image, [(np.full((26, 2), np.nan), scores, False)], "x", size=200)
    drawn = tile(image, [(kp, scores, False)], "x", size=200)
    assert drawn.shape == (200, 200, 3) and drawn.dtype == np.uint8
    assert int((drawn != plain).any(axis=-1).sum()) > 200  # a skeleton changes many pixels


def test_t_audit_05_nan_keypoints_are_not_drawn_and_a_low_joint_is_a_ring():
    image, kp, scores = scene()
    nan_all = np.full((26, 2), np.nan)
    plain = image.copy()
    draw_skeleton(plain, nan_all, scores)
    assert (plain == image).all()
    disc, ring = image.copy(), image.copy()
    one = nan_all.copy()
    one[0] = kp[0]
    draw_skeleton(disc, one, np.full(26, 0.9))
    draw_skeleton(ring, one, np.full(26, 0.1))
    assert int((disc != image).any(axis=-1).sum()) > int(
        (ring != image).any(axis=-1).sum()
    )  # a disc covers more than a ring


def test_t_audit_05_a_skeleton_at_the_edge_of_the_image_does_not_crash():
    image, kp, scores = scene()
    edge = kp + np.array([-480.0 + 5.0, -300.0 + 5.0])  # joints partly outside the image
    out = tile(image, [(edge, scores, False), (edge, scores, True)], "edge", size=150)
    assert out.shape == (150, 150, 3)


def test_t_audit_05_with_no_skeleton_the_whole_frame_is_shown_with_a_note():
    image, _, scores = scene()
    out = tile(image, [(np.full((26, 2), np.nan), scores, False)], "lost", size=300)
    assert (
        out.shape == (300, 300, 3) and (out[150:, :] != 40).any()
    )  # the picture (gray 90) fills the tile below the bar


def test_t_audit_05_boxes_of_other_persons_are_drawn_gray():
    image, kp, scores = scene()
    without = tile(image, [(kp, scores, False)], "x", size=200)
    with_box = tile(image, [(kp, scores, False)], "x", size=200, boxes=[(100.0, 100.0, 300.0, 400.0)])
    changed = (with_box != without).any(axis=-1)
    assert changed.any() and (with_box[changed] == np.array(BOX)).all()


def test_t_audit_05_strips_and_sheets_have_the_sizes_of_their_tiles():
    image, kp, scores = scene()
    tiles = [tile(image, [(kp, scores, False)], f"t{i}", size=100) for i in range(5)]
    assert strip(tiles[:3]).shape == (100, 300, 3)
    sheet = contact_sheet(tiles, columns=2, pad=4)
    assert sheet.shape == (3 * 104, 2 * 104, 3)  # 3 rows of 2 tiles (the last row has one), each with a 4 px gap
    mixed = contact_sheet([strip(tiles[:3]), tiles[3], tiles[4]], columns=1, pad=4)
    assert mixed.shape[1] == 300 + 4 and mixed.shape[0] == 3 * 104  # rows padded to the widest


@pytest.mark.parametrize("columns", [1, 3, 12])
def test_t_audit_05_the_number_of_columns_only_changes_the_grid(columns: int):
    image, kp, scores = scene()
    tiles = [tile(image, [(kp, scores, False)], str(i), size=50) for i in range(6)]
    sheet = contact_sheet(tiles, columns=columns, pad=2)
    rows = -(-6 // columns)
    assert sheet.shape == (rows * 52, min(columns, 6) * 52, 3)
