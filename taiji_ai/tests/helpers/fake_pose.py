"""A scripted pose model for the runner tests (P3.02): no GPU, no ONNX, fully deterministic.

``ScriptedPose`` satisfies ``taiji_ai.pose.runner.PoseModel``. The persons it "sees" in a frame come from a script
keyed by the frame position. The position is read from pixel [0, 0] of the image (blue and green channels): the
cadence tests replace ``iter_frames`` with ``with_frame_position`` so that the fake knows which frame it is looking
at; tests of the decoding use real frames and a script that does not depend on the position (``by_pixel=False``).

``estimate`` answers for each given box with the scripted person whose centre lies in the box (largest overlap); a box
with nobody in it gets keypoints at its centre with a score of 0.05, like a real model that is shown an empty crop.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from taiji_ai.io.frames import VideoFrame
from taiji_ai.pose.rtm import PoseResult

WEAK_SCORE = 0.05


@dataclass(frozen=True)
class Person:
    bbox: tuple[float, float, float, float]  # xyxy, what the detector returns
    keypoints: np.ndarray  # (26, 2)
    scores: np.ndarray  # (26,)


def standing_person(
    cx: float = 160.0, top: float = 40.0, height: float = 160.0, valid: int = 26, score: float = 0.9
) -> Person:
    """A person of 26 keypoints inside a box; the first ``valid`` keypoints have ``score``, the others 0.05."""
    j = np.arange(26)
    kp = np.stack([cx + (j % 5 - 2) * 8.0, top + j / 25.0 * height], axis=1).astype(np.float32)
    scores = np.where(j < valid, score, WEAK_SCORE).astype(np.float32)
    return Person((cx - 30.0, top - 10.0, cx + 30.0, top + height + 10.0), kp, scores)


Script = dict[int, list[Person]] | Callable[[int], list[Person]]


class ScriptedPose:
    providers = {"det": "FakeExecutionProvider", "pose": "FakeExecutionProvider"}
    model_fingerprint = {"fake_det": "0" * 64, "fake_pose": "1" * 64}

    def __init__(self, script: Script, *, by_pixel: bool = True, fail_at: int | None = None):
        self.script = script
        self.by_pixel = by_pixel
        self.fail_at = fail_at
        self.detect_calls: list[int] = []  # frame positions
        self.estimate_calls: list[tuple[int, np.ndarray]] = []  # (frame position, boxes given)
        self.shapes: list[tuple[int, ...]] = []  # image shape of every call

    def _position(self, frame: np.ndarray) -> int:
        return int(frame[0, 0, 0]) + 256 * int(frame[0, 0, 1]) if self.by_pixel else -1

    def _persons(self, pos: int) -> list[Person]:
        return self.script(pos) if callable(self.script) else self.script.get(pos, [])

    def _maybe_fail(self, pos: int) -> None:
        if self.fail_at is not None and pos == self.fail_at:
            raise RuntimeError("scripted failure")

    def detect(self, frame_bgr: np.ndarray) -> np.ndarray:
        pos = self._position(frame_bgr)
        self.detect_calls.append(pos)
        self.shapes.append(frame_bgr.shape)
        self._maybe_fail(pos)
        return np.array([p.bbox for p in self._persons(pos)], np.float32).reshape(-1, 4)

    def estimate(self, frame_bgr: np.ndarray, bboxes: np.ndarray) -> PoseResult:
        pos = self._position(frame_bgr)
        boxes = np.asarray(bboxes, np.float32).reshape(-1, 4)
        self.estimate_calls.append((pos, boxes.copy()))
        self.shapes.append(frame_bgr.shape)
        self._maybe_fail(pos)
        persons = self._persons(pos)
        kps, scs = [], []
        for x0, y0, x1, y1 in boxes:
            best, best_overlap = None, 0.0
            for person in persons:
                cx, cy = person.keypoints[:, 0].mean(), person.keypoints[:, 1].mean()
                if x0 <= cx <= x1 and y0 <= cy <= y1:
                    px0, py0, px1, py1 = person.bbox
                    overlap = max(0.0, min(x1, px1) - max(x0, px0)) * max(0.0, min(y1, py1) - max(y0, py0))
                    if overlap > best_overlap:
                        best, best_overlap = person, overlap
            if best is None:
                kps.append(np.tile(np.array([(x0 + x1) / 2, (y0 + y1) / 2], np.float32), (26, 1)))
                scs.append(np.full(26, WEAK_SCORE, np.float32))
            else:
                kps.append(best.keypoints)
                scs.append(best.scores)
        return PoseResult(
            boxes,
            np.array(kps, np.float32).reshape(len(boxes), 26, 2),
            np.array(scs, np.float32).reshape(len(boxes), 26),
        )


def with_frame_position(real_iter_frames):
    """Wrap ``iter_frames``: write the position of the frame inside the decoded range into pixel [0, 0]."""

    def wrapper(path: str | Path, t0=None, t1=None, rotation_deg: int = 0) -> Iterator[VideoFrame]:
        for pos, frame in enumerate(real_iter_frames(path, t0, t1, rotation_deg)):
            image = frame.image.copy()
            image[0, 0, 0] = pos % 256
            image[0, 0, 1] = pos // 256
            yield replace(frame, image=image)

    return wrapper
