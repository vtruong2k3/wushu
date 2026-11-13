"""PTS-accurate frame access with PyAV.

Time convention: ``t_sec = (pts - stream_start_pts) * time_base``, i.e. seconds from the first
presentation timestamp of the video stream. Frame rate is never assumed: variable-frame-rate
phone videos keep their real timestamps.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import av
import cv2
import numpy as np


@dataclass(frozen=True)
class VideoFrame:
    index: int  # presentation-order index within the decoded range
    pts: int
    t_sec: float
    image: np.ndarray  # H x W x 3, BGR uint8, display-rotated if requested


_ROTATE = {
    # ffprobe display-matrix rotation (degrees, counter-clockwise positive) -> cv2 op to display it
    90: cv2.ROTATE_90_COUNTERCLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_CLOCKWISE,
}


def apply_display_rotation(img: np.ndarray, rotation_deg: int) -> np.ndarray:
    op = _ROTATE.get(int(rotation_deg) % 360)
    return img if op is None else cv2.rotate(img, op)


def _start_pts(stream: av.video.stream.VideoStream) -> int:
    return int(stream.start_time) if stream.start_time is not None else 0


def scan_pts(path: str | Path) -> tuple[np.ndarray, float]:
    """Return sorted presentation timestamps (seconds from stream start) without decoding.

    Returns (t_sec array, time_base as float).
    """
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        tb = float(stream.time_base)
        start = _start_pts(stream)
        pts = [p.pts for p in container.demux(stream) if p.pts is not None and p.size > 0]
    arr = (np.sort(np.asarray(pts, dtype=np.int64)) - start) * tb
    return arr, tb


def is_vfr(t_sec: np.ndarray, rel_tol: float = 0.01) -> bool:
    """True when frame intervals vary by more than ``rel_tol`` (std/median of dt)."""
    if len(t_sec) < 3:
        return False
    dt = np.diff(t_sec)
    med = float(np.median(dt))
    return med > 0 and float(np.std(dt)) / med > rel_tol


def iter_frames(
    path: str | Path,
    t0: float | None = None,
    t1: float | None = None,
    rotation_deg: int = 0,
) -> Iterator[VideoFrame]:
    """Decode frames with t0 <= t_sec <= t1 (seconds from stream start), in presentation order."""
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        tb = stream.time_base
        start = _start_pts(stream)
        if t0 is not None and t0 > 0:
            container.seek(int(t0 / tb) + start, stream=stream, backward=True, any_frame=False)
        idx = 0
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            t = float((frame.pts - start) * tb)
            if t0 is not None and t < t0 - 1e-9:
                continue
            if t1 is not None and t > t1 + 1e-9:
                break
            img = frame.to_ndarray(format="bgr24")
            yield VideoFrame(idx, int(frame.pts), t, apply_display_rotation(img, rotation_deg))
            idx += 1
