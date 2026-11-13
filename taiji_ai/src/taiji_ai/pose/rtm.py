"""Pose estimation wrapper around rtmlib (YOLOX person detector + RTMPose HALPE_26).

- Models are loaded only from local files listed in the verified registry (no downloads).
- Detection and pose are exposed separately so the caller can run the detector every N frames
  and reuse the tracked bbox in between (single performer, fixed camera).
- Input frames are BGR uint8 (``av`` frame.to_ndarray(format="bgr24")).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from taiji_ai.pose.registry import ModelRegistry
from taiji_ai.pose.skeleton import NUM_JOINTS

log = logging.getLogger(__name__)

_ORT_READY = False


def prepare_onnxruntime(device: str) -> None:
    """Load CUDA/cuDNN DLLs shipped by the nvidia-* pip packages (once) and quiet ORT logging."""
    global _ORT_READY
    if _ORT_READY:
        return
    import onnxruntime as ort

    ort.set_default_logger_severity(3)  # errors only; node-placement warnings are expected
    if device == "cuda" and hasattr(ort, "preload_dlls"):
        ort.preload_dlls()
    _ORT_READY = True


@dataclass(frozen=True)
class PoseResult:
    bboxes: np.ndarray  # (N, 4) xyxy in image pixels
    keypoints: np.ndarray  # (N, 26, 2) x, y in image pixels
    scores: np.ndarray  # (N, 26)


class PoseEstimator:
    def __init__(self, registry: ModelRegistry, device: str = "cuda", require_gpu: bool = True):
        prepare_onnxruntime(device)
        from rtmlib import YOLOX, RTMPose  # imported late: rtmlib prints on import of models

        det_e = registry.by_role("det")
        pose_e = registry.by_role("pose")
        if pose_e.skeleton != "halpe26/1":
            raise ValueError(f"pose model skeleton {pose_e.skeleton!r} != 'halpe26/1'")

        self.det = YOLOX(str(det_e.path), model_input_size=det_e.input_size, backend="onnxruntime", device=device)
        self.pose = RTMPose(str(pose_e.path), model_input_size=pose_e.input_size, backend="onnxruntime", device=device)
        self.providers = {
            "det": self.det.session.get_providers()[0],
            "pose": self.pose.session.get_providers()[0],
        }
        if device == "cuda" and require_gpu and any(p != "CUDAExecutionProvider" for p in self.providers.values()):
            raise RuntimeError(f"CUDA requested but sessions use {self.providers}")
        self.model_fingerprint = registry.fingerprint()

    def detect(self, frame_bgr: np.ndarray) -> np.ndarray:
        boxes = np.asarray(self.det(frame_bgr), dtype=np.float32)
        return boxes.reshape(-1, 4)

    def estimate(self, frame_bgr: np.ndarray, bboxes: np.ndarray) -> PoseResult:
        bboxes = np.asarray(bboxes, dtype=np.float32).reshape(-1, 4)
        if len(bboxes) == 0:
            return PoseResult(bboxes, np.empty((0, NUM_JOINTS, 2), np.float32), np.empty((0, NUM_JOINTS), np.float32))
        kp, sc = self.pose(frame_bgr, bboxes=bboxes)
        kp = np.asarray(kp, dtype=np.float32).reshape(len(bboxes), NUM_JOINTS, 2)
        sc = np.asarray(sc, dtype=np.float32).reshape(len(bboxes), NUM_JOINTS)
        return PoseResult(bboxes, kp, sc)

    def __call__(self, frame_bgr: np.ndarray) -> PoseResult:
        return self.estimate(frame_bgr, self.detect(frame_bgr))
