"""T-DET-01, T-DET-02: the adapter of a YOLO-format ONNX detector (P3.09): letterbox, decoding, NMS, layout checks.

Hand-made arrays only: no model, no GPU, no video. The adapter is our own code; it reads a tensor format.
"""

from __future__ import annotations

import types

import numpy as np
import pytest

from taiji_ai.bench import BenchError
from taiji_ai.bench.yolo_onnx import (
    check_layout,
    decode_yolo,
    letterbox,
    nms_numpy,
    rtmlib_preprocess,
    to_model_input,
    unletterbox,
)


def image(h: int, w: int) -> np.ndarray:
    """A BGR image whose pixel value encodes its place, so that a resize or a shift is visible."""
    yy, xx = np.mgrid[0:h, 0:w]
    return np.stack([xx % 251, yy % 251, (xx + yy) % 251], axis=-1).astype(np.uint8)


# --- T-DET-01: letterbox --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("h", "w"), [(480, 640), (640, 480), (640, 640), (1080, 1920), (300, 200)])
def test_t_det_01_letterbox_size_ratio_pad_and_inverse(h: int, w: int):
    padded, ratio, (px, py) = letterbox(image(h, w), (640, 640))
    assert padded.shape == (640, 640, 3) and padded.dtype == np.uint8
    assert ratio == pytest.approx(min(640 / h, 640 / w))
    nw, nh = round(w * ratio), round(h * ratio)
    assert (px, py) == ((640 - nw) // 2, (640 - nh) // 2)  # centred
    # the margins are the pad value (114) and the picture is inside
    if py > 0:
        assert (padded[:py] == 114).all() and (padded[py + nh :] == 114).all()
    if px > 0:
        assert (padded[:, :px] == 114).all() and (padded[:, px + nw :] == 114).all()
    # a box drawn in the letterboxed picture maps back to the original within a pixel
    box = np.array([[px + 10.0, py + 20.0, px + 110.0, py + 220.0]])
    back = unletterbox(box, ratio, (px, py), (h, w))
    assert back[0, 0] == pytest.approx(10.0 / ratio, abs=1.0) and back[0, 1] == pytest.approx(20.0 / ratio, abs=1.0)


def test_t_det_01_an_image_that_already_has_the_input_size_is_not_changed():
    img = image(640, 640)
    padded, ratio, pad = letterbox(img, (640, 640))
    assert ratio == 1.0 and pad == (0, 0) and np.array_equal(padded, img)


def test_t_det_01_unletterbox_clips_to_the_image_and_keeps_the_order_of_the_corners():
    out = unletterbox(np.array([[-50.0, -50.0, 700.0, 700.0]]), 1.0, (0, 80), (480, 640))
    assert out.tolist() == [[0.0, 0.0, 640.0, 480.0]]  # x 0..640, y -130..620 clipped to 0..480
    assert (out[:, 2] >= out[:, 0]).all() and (out[:, 3] >= out[:, 1]).all()


def test_t_det_01_the_model_input_is_rgb_scaled_to_one_in_nchw_float32():
    padded = np.zeros((640, 640, 3), np.uint8)
    padded[..., 0], padded[..., 1], padded[..., 2] = 10, 20, 255  # B, G, R
    x = to_model_input(padded)
    assert x.shape == (1, 3, 640, 640) and x.dtype == np.float32
    assert (
        x[0, 0, 0, 0] == pytest.approx(1.0)
        and x[0, 1, 0, 0] == pytest.approx(20 / 255)
        and x[0, 2, 0, 0] == pytest.approx(10 / 255)
    )


@pytest.mark.parametrize(("h", "w"), [(480, 640), (1080, 1920), (640, 640), (300, 200)])
def test_t_det_01_the_shipping_preprocess_is_the_one_of_rtmlib(h: int, w: int):
    from rtmlib import YOLOX

    stub = types.SimpleNamespace(model_input_size=(640, 640))
    expected, expected_ratio = YOLOX.preprocess(stub, image(h, w))  # type: ignore[arg-type]
    got, got_ratio = rtmlib_preprocess(image(h, w), (640, 640))
    assert got_ratio == expected_ratio and np.array_equal(got, expected)  # top-left, pad 114, BGR 0..255


# --- T-DET-02: decoding and NMS -------------------------------------------------------------------------------------
def tensor(rows: list[tuple[float, float, float, float, dict[int, float]]], classes: int = 80) -> np.ndarray:
    """``[1, 4 + classes, A]``: one column per anchor, ``rows``: (cx, cy, w, h, {class: score})."""
    out = np.zeros((1, 4 + classes, len(rows)), np.float32)
    for a, (cx, cy, w, h, scores) in enumerate(rows):
        out[0, :4, a] = (cx, cy, w, h)
        for cls, s in scores.items():
            out[0, 4 + cls, a] = s
    return out


def test_t_det_02_only_the_person_class_above_the_limit_survives_and_nms_keeps_the_best():
    out = tensor(
        [
            (320, 320, 100, 200, {0: 0.90}),  # the performer
            (324, 322, 100, 200, {0: 0.80}),  # the same person again: removed by NMS
            (100, 100, 40, 80, {0: 0.50}),  # another person, kept
            (500, 500, 50, 50, {0: 0.30}),  # exactly the limit: not above it, removed
            (200, 500, 60, 60, {0: 0.05, 2: 0.95}),  # a car: not a person
            (600, 100, 20, 20, {0: 0.29}),  # under the limit
        ]
    )
    dets = decode_yolo(out, ratio=1.0, pad=(0, 0), image_shape=(640, 640), conf=0.3, iou=0.45)
    assert dets.shape == (2, 5)
    assert dets[0].tolist() == pytest.approx([270.0, 220.0, 370.0, 420.0, 0.9])  # cx cy w h to x1 y1 x2 y2, best first
    assert dets[1, :4].tolist() == pytest.approx([80.0, 60.0, 120.0, 140.0]) and dets[1, 4] == pytest.approx(0.5)


def test_t_det_02_coordinates_go_back_through_the_ratio_and_the_pad():
    out = tensor([(320, 320, 100, 200, {0: 0.9})])
    dets = decode_yolo(out, ratio=0.5, pad=(0, 80), image_shape=(960, 1280), conf=0.3, iou=0.45)
    # model box (270, 220, 370, 420): remove the pad (y - 80) and divide by the ratio
    assert dets[0, :4].tolist() == pytest.approx([540.0, 280.0, 740.0, 680.0])


def test_t_det_02_nothing_found_gives_an_empty_array_of_the_right_shape():
    dets = decode_yolo(tensor([(10, 10, 5, 5, {0: 0.1})]), 1.0, (0, 0), (640, 640), 0.3, 0.45)
    assert dets.shape == (0, 5) and dets.dtype == np.float32


def test_t_det_02_the_nms_limit_is_the_given_one():
    out = tensor([(320, 320, 100, 200, {0: 0.9}), (350, 320, 100, 200, {0: 0.8})])  # IoU = 70 / 130 = 0.54
    assert len(decode_yolo(out, 1.0, (0, 0), (640, 640), 0.3, 0.45)) == 1
    assert len(decode_yolo(out, 1.0, (0, 0), (640, 640), 0.3, 0.70)) == 2  # the default of Ultralytics keeps both


def test_t_det_02_nms_numpy_keeps_the_best_of_a_cluster_and_is_stable_on_ties():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [100, 100, 110, 110]], np.float32)
    assert nms_numpy(boxes, np.array([0.5, 0.9, 0.7], np.float32), 0.5).tolist() == [1, 2]
    same = np.array([[0, 0, 10, 10], [0, 0, 10, 10]], np.float32)
    assert nms_numpy(same, np.array([0.5, 0.5], np.float32), 0.5).tolist() == [0]  # the lower index on a tie
    assert nms_numpy(np.empty((0, 4), np.float32), np.empty(0, np.float32), 0.5).tolist() == []


@pytest.mark.parametrize(
    ("shape", "message"),
    [
        ((1, 8400, 84), "84"),  # already transposed: another layout
        ((1, 5, 8400), "classes"),  # one class (4 + 1): not a COCO detector
        ((2, 84, 8400), "84"),  # a batch
        ((84, 8400), "84"),
    ],
)
def test_t_det_02_another_layout_is_refused_naming_what_was_found(shape: tuple[int, ...], message: str):
    with pytest.raises(BenchError, match=message):
        decode_yolo(np.zeros(shape, np.float32), 1.0, (0, 0), (640, 640), 0.3, 0.45)


def test_t_det_02_the_layout_check_of_a_model_file():
    check_layout([1, 3, 640, 640], [1, 84, 8400])  # the export of a COCO detector at 640
    for inp, out, message in (
        ([1, 3, 320, 320], [1, 84, 2100], "640"),
        ([1, 3, 640, 640], [1, 84, 8400, 1], "84"),
        ([1, 3, 640, 640], [1, 8400, 84], "84"),
        ([1, 3, "h", "w"], [1, 84, 8400], "640"),  # dynamic input: not what the plan measures
        ([1, 3, 640, 640], [1, 6, 300], "84"),  # an exported-with-NMS layout
    ):
        with pytest.raises(BenchError, match=message):
            check_layout(inp, out)


def test_t_det_02_nms_keeps_a_box_whose_overlap_is_exactly_the_limit():
    boxes = np.array([[0, 0, 10, 10], [0, 0, 10, 20]], np.float32)  # IoU exactly 0.5
    scores = np.array([0.9, 0.8], np.float32)
    assert nms_numpy(boxes, scores, 0.5).tolist() == [0, 1]  # above the limit is removed, at the limit stays
    assert nms_numpy(boxes, scores, 0.49).tolist() == [0]


def test_t_det_02_the_shipping_postprocess_keeps_scores_strictly_above_the_limit_and_divides_by_the_ratio():
    from taiji_ai.bench.yolo_onnx import ShippingDetector

    stub = types.SimpleNamespace(score_limit=0.3)
    dets = np.array([[100, 200, 300, 600, 0.31], [10, 20, 30, 60, 0.30], [50, 50, 90, 90, 0.95]], np.float32)
    out = ShippingDetector.postprocess(stub, dets, 0.5)  # type: ignore[arg-type]
    assert out.shape == (2, 5) and out[:, 4].tolist() == pytest.approx([0.31, 0.95])
    assert out[0, :4].tolist() == pytest.approx(
        [200.0, 400.0, 600.0, 1200.0]
    )  # the boxes of the canvas back to the picture
    limited = ShippingDetector.postprocess(stub, dets, 1.0, score_limit=0.5)  # type: ignore[arg-type]
    assert limited.shape == (1, 5)  # a limit given to the call wins
