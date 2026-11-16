"""Timing tools for the pose benchmark (P3.07): real-time factor, per-frame latency, windows, the model wrapper.

**Real-time factor** ``RTF = processing seconds / video seconds`` where the video seconds are the span the processed
frames cover (``video_span_s``: the last timestamp minus the first plus one median frame interval, so N frames of 1/30 s
cover N/30 s). ``ms_per_frame`` and ``fps_equivalent_rtf`` give the same cost at another frame rate (a phone at 60 fps
has twice the RTF of 30 fps for the same cost per frame).

**Windows**: ``window_rtf`` cuts the video time (not the count of frames) into windows of ``window_s`` seconds starting
at the first frame, and gives for each full window the work of its frames divided by the window length. The last
partial window is dropped (its frames are counted), a window without frames (a gap in a variable-frame-rate video) is
skipped and counted. The latency of a frame is the wall-clock time between two ``on_frame`` calls of ``run_pose``
(``FrameClock``), so it contains decode, model calls and bookkeeping.

**TimedModel** wraps a pose model (``detect`` / ``estimate`` / ``providers`` / ``model_fingerprint``) and adds up the
time of each call with ``time.perf_counter`` (ONNX Runtime calls are synchronous, so this includes the GPU work and the
host-side preparation). A call that raises is not counted and the exception is not caught.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from taiji_ai.bench import BenchError

_EPS = 1e-9


def _times(t_sec: Any) -> np.ndarray:
    t = np.asarray(t_sec, dtype=np.float64)
    if t.ndim != 1 or t.size < 2:
        raise BenchError(f"at least two frame times are needed to give a span, got shape {t.shape}")
    if not np.all(np.isfinite(t)) or np.any(np.diff(t) <= 0):
        raise BenchError("frame times must be finite and strictly increasing")
    return t


def video_span_s(t_sec: Any) -> float:
    """Video seconds covered by the frames: last time - first time + one median frame interval."""
    t = _times(t_sec)
    return float(t[-1] - t[0] + np.median(np.diff(t)))


def rtf(elapsed_s: float, span_s: float) -> float:
    """Processing seconds per video second."""
    if not (math.isfinite(elapsed_s) and elapsed_s >= 0.0):
        raise BenchError(f"elapsed seconds must be a finite number >= 0, got {elapsed_s!r}")
    if not (math.isfinite(span_s) and span_s > 0.0):
        raise BenchError(f"the video span must be a finite number > 0, got {span_s!r}")
    return elapsed_s / span_s


def ms_per_frame(elapsed_s: float, n_frames: int) -> float:
    if n_frames < 1:
        raise BenchError(f"at least one frame is needed, got {n_frames}")
    if not (math.isfinite(elapsed_s) and elapsed_s >= 0.0):
        raise BenchError(f"elapsed seconds must be a finite number >= 0, got {elapsed_s!r}")
    return 1000.0 * elapsed_s / n_frames


def fps_equivalent_rtf(ms_per_frame_value: float, fps: float) -> float:
    """The RTF that a cost of ``ms_per_frame_value`` per frame has at ``fps`` frames per second."""
    if not (math.isfinite(ms_per_frame_value) and ms_per_frame_value >= 0.0):
        raise BenchError(f"ms per frame must be a finite number >= 0, got {ms_per_frame_value!r}")
    if not (math.isfinite(fps) and fps > 0.0):
        raise BenchError(f"fps must be a finite number > 0, got {fps!r}")
    return ms_per_frame_value * fps / 1000.0


def percentiles(values: Any, levels: Sequence[int] = (50, 95, 99)) -> dict[int, float]:
    """Linear-interpolation percentiles (numpy default) of finite values, keyed by level in the order given."""
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0 or not np.all(np.isfinite(v)):
        raise BenchError("percentiles need at least one value and all of them finite")
    for q in levels:
        if not 0 <= q <= 100:
            raise BenchError(f"a percentile level must be in [0, 100], got {q}")
    return {q: float(np.percentile(v, q)) for q in levels}


@dataclass(frozen=True, eq=False)
class WindowRtf:
    values: np.ndarray  # RTF of each full window that has frames, in video order
    n_empty_windows: int  # full windows without any frame (a gap in the video time)
    n_dropped_frames: int  # frames of the last partial window


def window_rtf(latency_s: Any, t_sec: Any, window_s: float = 1.0) -> WindowRtf:
    """RTF of each full ``window_s`` window of video time: the latency of its frames divided by ``window_s``."""
    if not (math.isfinite(window_s) and window_s > 0.0):
        raise BenchError(f"the window must be a finite number of seconds > 0, got {window_s!r}")
    latency = np.asarray(latency_s, dtype=np.float64)
    t = _times(t_sec)
    if latency.shape != t.shape:
        raise BenchError(f"{latency.size} latencies for {t.size} frame times")
    if not np.all(np.isfinite(latency)) or np.any(latency < 0.0):
        raise BenchError("latencies must be finite and not negative")
    n_full = int(math.floor(video_span_s(t) / window_s + _EPS))
    if n_full < 1:
        raise BenchError(f"the video is shorter than one window of {window_s} s")
    index = np.floor((t - t[0]) / window_s + _EPS).astype(np.int64)
    values: list[float] = []
    empty = 0
    for j in range(n_full):
        mask = index == j
        if not mask.any():
            empty += 1
            continue
        values.append(float(latency[mask].sum() / window_s))
    return WindowRtf(np.asarray(values, dtype=np.float64), empty, int((index >= n_full).sum()))


class FrameClock:
    """Pass ``on_frame`` to ``run_pose``: records the wall clock after each frame; ``latencies`` are the differences."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter):
        self._clock = clock
        self._start: float | None = None
        self._marks: list[float] = []
        self._t: list[float] = []

    def start(self) -> None:
        """Begin a pass (the first latency is measured from here); anything recorded before is forgotten."""
        self._start = self._clock()
        self._marks, self._t = [], []

    def on_frame(self, position: int, t_sec: float) -> None:
        if self._start is None:
            raise BenchError("FrameClock.start() must be called before the run")
        if position != len(self._marks):
            raise BenchError(f"frame position {position} arrived out of order, expected {len(self._marks)}")
        self._marks.append(self._clock())
        self._t.append(float(t_sec))

    @property
    def n_frames(self) -> int:
        return len(self._marks)

    @property
    def t_sec(self) -> np.ndarray:
        return np.asarray(self._t, dtype=np.float64)

    def latencies(self) -> np.ndarray:
        """Seconds each frame took (from the start mark or the previous frame)."""
        if self._start is None:
            raise BenchError("FrameClock.start() was not called")
        if not self._marks:
            raise BenchError("no frame was recorded")
        return np.diff(np.concatenate([[self._start], self._marks]))


class TimedModel:
    """A pose model that adds up the time and the number of its ``detect`` and ``estimate`` calls."""

    def __init__(self, model: Any, clock: Callable[[], float] = time.perf_counter):
        self._model = model
        self._clock = clock
        self.providers: dict[str, str] = model.providers  # what ``PoseModel`` asks for, read once from the real model
        self.model_fingerprint: dict[str, str] = model.model_fingerprint
        self.reset()

    def reset(self) -> None:
        self.detect_s = 0.0
        self.estimate_s = 0.0
        self.n_detect = 0
        self.n_estimate = 0

    def detect(self, frame_bgr: np.ndarray) -> Any:
        started = self._clock()
        result = self._model.detect(frame_bgr)
        self.detect_s += self._clock() - started
        self.n_detect += 1
        return result

    def estimate(self, frame_bgr: np.ndarray, bboxes: np.ndarray) -> Any:
        started = self._clock()
        result = self._model.estimate(frame_bgr, bboxes)
        self.estimate_s += self._clock() - started
        self.n_estimate += 1
        return result
