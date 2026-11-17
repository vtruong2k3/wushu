"""Adapters of two person detectors for the comparison of P3.09: a YOLO-format ONNX file and the shipping YOLOX.

**Offline tooling.** Nothing of the product imports this module (a guard test checks it). The YOLO adapter reads the
tensor format of a detector exported to ONNX with 80 COCO classes at 640 x 640 (``[1, 84, 8400]``: the centre, the
size and the 80 class scores of each of the 8400 anchors); it is our own code and copies no code of Ultralytics,
whose package and weights (AGPL-3.0) are used only to export the file, in a separate environment
(``Docs/tasks/P3.09.md``, DEC-0043).

Coordinates: image pixels, x to the right, y down; boxes ``(x1, y1, x2, y2)``; a detection is
``(x1, y1, x2, y2, score)``. Frames are BGR ``uint8`` (as ``av`` gives them).

* ``YoloOnnx``: letterbox (the picture is kept in proportion and centred on a grey 114 canvas), RGB, scaled to 0..1,
  the model, then the person class (class 0), a score limit and NMS in NumPy.
* ``ShippingDetector``: the YOLOX file of the registry through the same ONNX Runtime setup as rtmlib, **with the
  scores kept** (the rtmlib call returns boxes only). The preprocessing is that of rtmlib (top-left placement, BGR
  0..255), the NMS is the one inside the graph, and the score limit is applied here (rtmlib applies a constant 0.3
  to a file of this kind).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np

from taiji_ai.bench import BenchError

COCO_CLASSES: Final = 80
PERSON: Final = 0
PAD_VALUE: Final = 114
INPUT_SIZE: Final = (640, 640)  # (height, width)
_ANCHORS_640: Final = 8400  # 80 x 80 + 40 x 40 + 20 x 20


def letterbox(
    image_bgr: np.ndarray, size: tuple[int, int] = INPUT_SIZE, pad_value: int = PAD_VALUE
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize keeping the proportions and centre the picture on a ``pad_value`` canvas of ``size`` (height, width).

    Returns the canvas, the ratio (new size over old size) and the pad ``(left, top)`` in pixels of the canvas.
    """
    h, w = image_bgr.shape[:2]
    th, tw = size
    if (h, w) == (th, tw):
        return image_bgr.copy(), 1.0, (0, 0)
    ratio = min(th / h, tw / w)
    nw, nh = min(tw, round(w * ratio)), min(th, round(h * ratio))
    resized = cv2.resize(image_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((th, tw, 3), pad_value, np.uint8)
    left, top = (tw - nw) // 2, (th - nh) // 2
    canvas[top : top + nh, left : left + nw] = resized
    return canvas, ratio, (left, top)


def unletterbox(boxes: np.ndarray, ratio: float, pad: tuple[int, int], image_shape: tuple[int, int]) -> np.ndarray:
    """Boxes of the canvas back to the original picture, clipped to it (``image_shape`` is height, width)."""
    out = np.array(boxes, dtype=np.float32, copy=True).reshape(-1, 4)
    out[:, [0, 2]] = np.clip((out[:, [0, 2]] - pad[0]) / ratio, 0.0, float(image_shape[1]))
    out[:, [1, 3]] = np.clip((out[:, [1, 3]] - pad[1]) / ratio, 0.0, float(image_shape[0]))
    return out


def to_model_input(canvas_bgr: np.ndarray) -> np.ndarray:
    """The canvas as the YOLO export expects it: RGB, 0..1, float32, ``[1, 3, H, W]``."""
    rgb = canvas_bgr[..., ::-1]
    return np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32) / np.float32(255.0)


def rtmlib_preprocess(image_bgr: np.ndarray, size: tuple[int, int] = INPUT_SIZE) -> tuple[np.ndarray, float]:
    """The preprocessing of rtmlib's ``YOLOX``: the picture at the top left of a 114 canvas, BGR 0..255, ratio
    returned."""
    if image_bgr.shape[:2] == tuple(size[:2]):
        return image_bgr.copy(), 1.0
    canvas = np.ones((size[0], size[1], 3), dtype=np.uint8) * PAD_VALUE
    ratio = min(size[0] / image_bgr.shape[0], size[1] / image_bgr.shape[1])
    nw, nh = int(image_bgr.shape[1] * ratio), int(image_bgr.shape[0] * ratio)
    canvas[:nh, :nw] = cv2.resize(image_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR).astype(np.uint8)
    return canvas, ratio


def nms_numpy(boxes: np.ndarray, scores: np.ndarray, iou: float) -> np.ndarray:
    """Indices kept by greedy NMS, best score first (the lower index first on a tie); IoU above ``iou`` is removed."""
    if len(boxes) == 0:
        return np.empty(0, dtype=np.int64)
    order = np.argsort(-np.asarray(scores), kind="stable")
    x1, y1, x2, y2 = (np.asarray(boxes, dtype=np.float64)[:, k] for k in range(4))
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        w = np.maximum(0.0, np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest]))
        h = np.maximum(0.0, np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]))
        inter = w * h
        union = areas[i] + areas[rest] - inter
        overlap = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
        order = rest[overlap <= iou]
    return np.array(keep, dtype=np.int64)


def check_layout(input_shape: Sequence[Any], output_shape: Sequence[Any]) -> None:
    """Refuse a model that is not a static 640 x 640 COCO detector with the raw ``[1, 84, 8400]`` output."""
    if list(input_shape) != [1, 3, *INPUT_SIZE]:
        raise BenchError(f"the model input must be [1, 3, 640, 640] (static), found {list(input_shape)}")
    if list(output_shape) != [1, 4 + COCO_CLASSES, _ANCHORS_640]:
        raise BenchError(
            f"the model output must be [1, {4 + COCO_CLASSES}, {_ANCHORS_640}] (80 classes, no NMS inside), "
            f"found {list(output_shape)}"
        )


def decode_yolo(
    output: np.ndarray,
    ratio: float,
    pad: tuple[int, int],
    image_shape: tuple[int, int],
    conf: float = 0.3,
    iou: float = 0.45,
    person_class: int = PERSON,
) -> np.ndarray:
    """The person detections ``(n, 5)`` of a raw output ``[1, 4 + classes, anchors]``, in the original picture.

    The score limit is strict (a score equal to ``conf`` is dropped, as in rtmlib); the NMS limit removes boxes with IoU
    above ``iou``. Raises ``BenchError`` naming the shape when the output is not the layout of a COCO detector.
    """
    out = np.asarray(output)
    if out.ndim != 3 or out.shape[0] != 1:
        raise BenchError(f"expected an output of shape [1, 4 + classes, anchors], found {list(out.shape)}")
    if out.shape[2] == 4 + COCO_CLASSES and out.shape[1] != 4 + COCO_CLASSES:
        raise BenchError(
            f"the output looks transposed: found {list(out.shape)}, expected [1, {4 + COCO_CLASSES}, anchors]"
        )
    classes = out.shape[1] - 4
    if classes != COCO_CLASSES:
        raise BenchError(f"the detector has {classes} classes, expected {COCO_CLASSES} (COCO)")
    pred = out[0].astype(np.float32, copy=False)
    scores = pred[4 + person_class]
    keep = scores > conf
    if not keep.any():
        return np.empty((0, 5), np.float32)
    cx, cy, w, h = pred[0, keep], pred[1, keep], pred[2, keep], pred[3, keep]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    kept_scores = scores[keep]
    chosen = nms_numpy(boxes, kept_scores, iou)
    final = unletterbox(boxes[chosen], ratio, pad, image_shape)
    return np.concatenate([final, kept_scores[chosen, None]], axis=1).astype(np.float32)


def _session(path: Path | str, device: str) -> Any:
    import onnxruntime as ort

    # Not ``pose.rtm.prepare_onnxruntime``: it remembers that it ran for any device, so a call for the CPU (reading the
    # shape of a file) would stop a later call for CUDA from loading the DLLs of the nvidia packages (BUG-0072).
    ort.set_default_logger_severity(3)
    if device == "cuda" and hasattr(ort, "preload_dlls"):
        ort.preload_dlls()
    providers = ["CUDAExecutionProvider"] if device == "cuda" else ["CPUExecutionProvider"]  # as rtmlib builds it
    try:
        session = ort.InferenceSession(str(path), providers=providers)
    except Exception as exc:  # onnxruntime raises its own error types for a file it cannot read
        raise BenchError(f"not a readable ONNX model ({type(exc).__name__})") from exc
    if device == "cuda" and session.get_providers()[0] != "CUDAExecutionProvider":
        raise BenchError(f"CUDA was asked for but the session uses {session.get_providers()}")
    return session


def read_shapes(path: Path | str) -> tuple[list[Any], list[Any]]:
    """The input and the first output shape of an ONNX file, read on the CPU (no GPU is needed to check a file)."""
    session = _session(path, "cpu")
    return list(session.get_inputs()[0].shape), list(session.get_outputs()[0].shape)


class YoloOnnx:
    """A YOLO-format ONNX person detector (static 640 x 640, raw ``[1, 84, 8400]`` output)."""

    def __init__(self, path: Path | str, device: str = "cuda", conf: float = 0.3, iou: float = 0.45):
        self.session = _session(path, device)
        check_layout(self.session.get_inputs()[0].shape, self.session.get_outputs()[0].shape)
        self.input_name = self.session.get_inputs()[0].name
        self.conf, self.iou = conf, iou

    def preprocess(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int]]:
        canvas, ratio, pad = letterbox(frame_bgr, INPUT_SIZE)
        return to_model_input(canvas), ratio, pad

    def run(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(self.session.run(None, {self.input_name: x})[0])

    def postprocess(
        self,
        output: np.ndarray,
        ratio: float,
        pad: tuple[int, int],
        image_shape: tuple[int, int],
        conf: float | None = None,
    ) -> np.ndarray:
        return decode_yolo(output, ratio, pad, image_shape, self.conf if conf is None else conf, self.iou)

    def detect(self, frame_bgr: np.ndarray, conf: float | None = None) -> np.ndarray:
        x, ratio, pad = self.preprocess(frame_bgr)
        return self.postprocess(self.run(x), ratio, pad, frame_bgr.shape[:2], conf)  # type: ignore[arg-type]


class ShippingDetector:
    """The YOLOX file of the registry through ONNX Runtime, with the scores kept (the NMS is inside the graph)."""

    def __init__(self, path: Path | str, device: str = "cuda", score_limit: float = 0.3):
        self.session = _session(path, device)
        self.input_name = self.session.get_inputs()[0].name
        self.score_limit = score_limit

    def preprocess(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        canvas, ratio = rtmlib_preprocess(frame_bgr, INPUT_SIZE)
        x = np.ascontiguousarray(canvas.transpose(2, 0, 1), dtype=np.float32)[None]
        return x, ratio

    def run(self, x: np.ndarray) -> np.ndarray:
        """The ``dets`` output ``[1, N, 5]`` of the graph (x1, y1, x2, y2, score), after its own NMS."""
        outputs = self.session.run(None, {self.input_name: x})
        return np.asarray(outputs[0])

    def postprocess(self, dets: np.ndarray, ratio: float, score_limit: float | None = None) -> np.ndarray:
        limit = self.score_limit if score_limit is None else score_limit
        rows = np.asarray(dets, dtype=np.float32).reshape(-1, 5).copy()
        rows = rows[rows[:, 4] > limit]  # strict, as rtmlib does
        rows[:, :4] /= ratio
        return rows

    def detect(self, frame_bgr: np.ndarray, score_limit: float | None = None) -> np.ndarray:
        x, ratio = self.preprocess(frame_bgr)
        return self.postprocess(self.run(x), ratio, score_limit)
