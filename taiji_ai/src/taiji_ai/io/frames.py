"""PTS-accurate frame access with PyAV.

Time convention: ``t_sec = (pts - stream_start_pts) * time_base``, i.e. seconds from the first
presentation timestamp of the video stream. Frame rate is never assumed: variable-frame-rate
phone videos keep their real timestamps.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
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


@dataclass(frozen=True)
class PtsScan:
    """Presentation timestamps of a video stream as the container stores them.

    ``pts`` are integer ticks of ``time_base`` seconds, sorted (presentation order); ``start_pts`` is the stream start.
    The time convention is ``t_sec = (pts - start_pts) * time_base``.
    """

    pts: np.ndarray  # int64, ticks
    time_base: Fraction  # seconds per tick, e.g. 1/90000
    start_pts: int

    @property
    def t_sec(self) -> np.ndarray:
        """Seconds from the stream start (float64)."""
        return (self.pts - self.start_pts) * float(self.time_base)


def scan_pts_ticks(path: str | Path) -> PtsScan:
    """Demux the video stream and return the sorted integer timestamps of its frames, without decoding.

    A packet flagged *discard* is not a frame: a clip trimmed on a phone (a stream copy that starts between two
    keyframes) keeps the packets before the edit start, with negative times, and the decoder never outputs them
    (BUG-0052). Counting them would shift row *i* of the frame table away from decoded frame *i*.
    """
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        tb = Fraction(stream.time_base.numerator, stream.time_base.denominator)
        start = _start_pts(stream)
        pts = [p.pts for p in container.demux(stream) if p.pts is not None and p.size > 0 and not p.is_discard]
    return PtsScan(np.sort(np.asarray(pts, dtype=np.int64)), tb, start)


def scan_pts(path: str | Path) -> tuple[np.ndarray, float]:
    """Return sorted presentation timestamps (seconds from stream start) without decoding.

    Returns (t_sec array, time_base as float).
    """
    scan = scan_pts_ticks(path)
    return scan.t_sec, float(scan.time_base)


@dataclass(frozen=True)
class VfrRuleParams:
    """The rule that decides variable frame rate (BUG-0046), recorded in ``recording.json`` as ``vfr_rule``.

    An interval between two frames deviates when it differs from the median interval by more than ``tick_tol`` ticks
    **and** by more than ``rel_tol`` of the median; the video is VFR when more than ``max_share`` of its intervals
    deviate. The tick tolerance is what keeps a constant 30 fps video with a coarse time base (intervals of 33 and 34
    ticks of 1 ms) from being called VFR: its spread is rounding.
    """

    name: str = "tick_median"
    version: int = 1
    rel_tol: float = 0.01
    tick_tol: int = 1
    max_share: float = 0.01


VFR_RULE = VfrRuleParams()


@dataclass(frozen=True)
class VfrVerdict:
    vfr: bool
    n_intervals: int
    n_deviating: int
    deviating_share: float
    median_dt_ticks: float | None  # None without any interval (fewer than two frames)
    n_duplicates: int  # intervals of 0 ticks: frames that share a timestamp (counted, never dropped)


def vfr_verdict(pts: np.ndarray, rule: VfrRuleParams = VFR_RULE) -> VfrVerdict:
    """Apply the rule to sorted integer timestamps (ticks). Fewer than two intervals are never VFR.

    When more than half of the intervals are 0 the median is 0: the timestamps are not those of a constant frame rate,
    so the verdict is VFR (the caller decides whether such a file is usable at all).
    """
    dt = np.diff(np.asarray(pts, dtype=np.int64))
    n = int(dt.size)
    n_dup = int(np.count_nonzero(dt == 0))
    if n == 0:
        return VfrVerdict(False, 0, 0, 0.0, None, n_dup)
    median = float(np.median(dt))
    if n < 2:
        return VfrVerdict(False, n, 0, 0.0, median, n_dup)
    if median <= 0:
        return VfrVerdict(True, n, int(np.count_nonzero(dt != 0)), 1.0, 0.0, n_dup)
    tol = max(float(rule.tick_tol), rule.rel_tol * median)
    n_dev = int(np.count_nonzero(np.abs(dt - median) > tol))
    share = n_dev / n
    return VfrVerdict(share > rule.max_share, n, n_dev, share, median, n_dup)


def is_vfr(t_sec: np.ndarray, tick_s: float, rel_tol: float = 0.01, max_share: float = 0.01, tick_tol: int = 1) -> bool:
    """True when the frame intervals of ``t_sec`` (seconds) are not those of a constant frame rate.

    ``tick_s`` is the time base in seconds per tick: the timestamps are rounded back to whole ticks and the rule of
    ``vfr_verdict`` is applied, so quantisation noise is not mistaken for a change of the frame rate (BUG-0046).
    """
    ticks = np.rint(np.asarray(t_sec, dtype=np.float64) / tick_s).astype(np.int64)
    return vfr_verdict(ticks, VfrRuleParams(rel_tol=rel_tol, tick_tol=tick_tol, max_share=max_share)).vfr


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
