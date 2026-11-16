"""P3.01: run the real pose model on a few frames and draw the joint index, to check the order of ``halpe26/1`` by eye.

For each requested time the frame is decoded by PTS (``taiji_ai.io.frames.iter_frames``), the detector and the pose
model run on the GPU, the largest person is taken, the automatic structure check of ``taiji_ai.pose.order_check`` is
printed and an image is written: the crop of the person with the index of every joint (red: left, blue: right, green:
centre line) and a legend ``index name score``. The images are written under the data folder (ignored by git): they
hold frames of a video and are never committed.

Usage (from ``taiji_ai/``)::

    python tools/pose_order_check.py VIDEO --label d20-v2 --times 120,300,480,660,840

Only the label (an ID you choose) is used in file names and output, never the file name of the video.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from taiji_ai.config import get_settings
from taiji_ai.io.frames import iter_frames
from taiji_ai.pose.order_check import check_joint_order
from taiji_ai.pose.registry import ModelRegistry
from taiji_ai.pose.rtm import PoseEstimator
from taiji_ai.pose.skeleton import JOINTS

LEFT_BGR = (60, 60, 255)  # red
RIGHT_BGR = (255, 120, 40)  # blue
CENTRE_BGR = (60, 200, 60)  # green
CENTRE_JOINTS = {"Nose", "Head", "Neck", "Hip"}


def _colour(name: str) -> tuple[int, int, int]:
    if name in CENTRE_JOINTS:
        return CENTRE_BGR
    return LEFT_BGR if name.startswith("L") else RIGHT_BGR


def _first_frame(video: Path, t: float) -> tuple[float, np.ndarray] | None:
    for f in iter_frames(video, t0=t, t1=t + 1.0):
        return f.t_sec, f.image
    return None


def _draw(image: np.ndarray, bbox: np.ndarray, kp: np.ndarray, scores: np.ndarray) -> np.ndarray:
    """Crop of the person with the index of each joint, and a legend panel on the right."""
    h, w = image.shape[:2]
    x0, y0, x1, y1 = bbox
    mx, my = 0.25 * (x1 - x0), 0.1 * (y1 - y0)
    cx0, cy0 = int(max(0, x0 - mx)), int(max(0, y0 - my))
    cx1, cy1 = int(min(w, x1 + mx)), int(min(h, y1 + my))
    crop = image[cy0:cy1, cx0:cx1].copy()
    scale = 900.0 / crop.shape[0]
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    for i, (name, (x, y)) in enumerate(zip(JOINTS, kp, strict=True)):
        p = (int((x - cx0) * scale), int((y - cy0) * scale))
        colour = _colour(name)
        cv2.circle(crop, p, 5, colour, -1)
        cv2.putText(crop, str(i), (p[0] + 6, p[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(crop, str(i), (p[0] + 6, p[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 1, cv2.LINE_AA)
    panel = np.full((crop.shape[0], 330, 3), 255, np.uint8)
    for i, (name, s) in enumerate(zip(JOINTS, scores, strict=True)):
        y = 30 + i * 33
        cv2.putText(
            panel, f"{i:2d} {name}  {s:.2f}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, _colour(name), 2, cv2.LINE_AA
        )
    return np.hstack([crop, panel])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--label", required=True, help="an ID for file names and output (never the video's file name)")
    ap.add_argument("--times", required=True, help="comma-separated times in seconds on the video timeline")
    ap.add_argument("--out", type=Path, default=None, help="output folder (default: <data>/reports/p3_01)")
    args = ap.parse_args(argv)

    settings = get_settings()
    out = args.out or settings.data_dir / "reports" / "p3_01"
    out.mkdir(parents=True, exist_ok=True)
    estimator = PoseEstimator(ModelRegistry(settings.registry_path), device="cuda")

    for t_req in (float(s) for s in args.times.split(",")):
        got = _first_frame(args.video, t_req)
        if got is None:
            sys.stdout.write(f"[{args.label} t={t_req:.1f}s] no frame\n")
            continue
        t, image = got
        res = estimator(image)
        sys.stdout.write(f"[{args.label} t={t:.3f}s] persons: {len(res.bboxes)}\n")
        if len(res.bboxes) == 0:
            continue
        areas = (res.bboxes[:, 2] - res.bboxes[:, 0]) * (res.bboxes[:, 3] - res.bboxes[:, 1])
        k = int(np.argmax(areas))
        report = check_joint_order(res.keypoints[k], res.scores[k])
        sys.stdout.write(f"  facing_side={report.facing_side} ok={report.ok} min_score={res.scores[k].min():.2f}\n")
        for c in report.checks:
            sys.stdout.write(f"  {c.name:18s} {c.status:12s} {c.detail}\n")
        path = out / f"{args.label}_t{t:08.3f}.png"
        cv2.imwrite(str(path), _draw(image, res.bboxes[k], res.keypoints[k], res.scores[k]))
        sys.stdout.write(f"  image: {path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
