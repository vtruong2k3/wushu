"""Raw pose of every person the models see, frame by frame, over one segment of a recording (W4, P3.02).

``run_pose`` reads the frames of ``[start_s - margin, end_s + margin]`` of the original video by their real
presentation timestamps (the rows of ``pts.parquet``, never an assumed frame rate), turns them to the upright position
(display rotation), and gives them to a pose model. Nothing is chosen, tracked or filtered here: the result is the raw
layer (AGENTS.md section 5.3). A person is a row of ``PoseRaw``; a frame without a person has zero rows, never rows of
zeros.

Detector cadence: the detector runs on the first frame and every ``detect_every_n`` frames; on the frames between, the
box of each followed person is taken from its keypoints in the previous frame (``box_from_keypoints``). A person is
*followed* only if enough of its keypoints are valid; every person the model returns is *stored*, followed or not.
When nobody is followed the detector runs at once, also on a frame that was started with stale boxes (its result
replaces the stale-box result, so all persons of a stored frame come from one pass).

Coordinates: keypoints and boxes are image pixels of the upright image, x to the right, y down (AGENTS.md section 6);
the size of that image is ``PoseRaw.image_size`` ``(width, height)``. Timestamps are seconds from the stream start.

Heavy work: this is a library function. The caller (the worker process, P7) owns the process and the GPU lock; the web
API process never calls it. The model is given already built (and verified by the registry): this module does not
touch it.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from taiji_ai.io.frames import iter_frames
from taiji_ai.pose.rtm import PoseResult
from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.schemas._base import ManifestError, read_manifest
from taiji_ai.schemas.recording import RecordingManifest

log = logging.getLogger(__name__)

_TIME_TOLERANCE_S = 1e-6  # a decoded frame and its table row must agree on t_sec within this


class PoseRunError(Exception):
    """A segment cannot be run: bad segment or files, a file that disagrees with its table, a model failure."""


class PoseModel(Protocol):
    """What ``run_pose`` needs from a pose model: ``PoseEstimator`` (``pose/rtm.py``) satisfies it, tests use a fake."""

    providers: dict[str, str]
    model_fingerprint: dict[str, str]  # name -> sha256, as ModelRegistry.fingerprint()

    def detect(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Boxes of the people in the frame: (N, 4) xyxy, image pixels."""
        ...

    def estimate(self, frame_bgr: np.ndarray, bboxes: np.ndarray) -> PoseResult:
        """Keypoints and scores of the people in the given boxes."""
        ...


@dataclass(frozen=True)
class PoseRunParams:
    # The detector runs on the first frame and every N frames (provisional: P3.07 measures N = 1, 5, 10).
    detect_every_n: int = 5
    # Widening of a box taken from keypoints, share of its width and height on each side (plan: 10 to 15 %).
    bbox_margin: float = 0.12
    min_score: float = 0.3  # a keypoint under this score is not valid
    min_valid_keypoints: int = 6  # a person with fewer valid keypoints is stored but not followed
    segment_margin_s: float = 1.0  # frames read before the start and after the end of the segment (W4) [s]

    def __post_init__(self) -> None:
        if not isinstance(self.detect_every_n, int) or self.detect_every_n < 1:
            raise ValueError(f"detect_every_n must be an integer >= 1, got {self.detect_every_n!r}")
        if not 0.0 <= self.bbox_margin <= 1.0:
            raise ValueError(f"bbox_margin must be in [0, 1], got {self.bbox_margin!r}")
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError(f"min_score must be in [0, 1], got {self.min_score!r}")
        if not isinstance(self.min_valid_keypoints, int) or not 1 <= self.min_valid_keypoints <= NUM_JOINTS:
            raise ValueError(
                f"min_valid_keypoints must be an integer in [1, {NUM_JOINTS}], got {self.min_valid_keypoints!r}"
            )
        if not (math.isfinite(self.segment_margin_s) and self.segment_margin_s >= 0.0):
            raise ValueError(f"segment_margin_s must be a finite number >= 0, got {self.segment_margin_s!r}")


@dataclass(frozen=True)
class PoseRunStats:
    """What a run cost; not part of the identity of the result (wall clock differs between runs)."""

    n_frames: int
    n_detector_calls: int
    n_pose_calls: int
    n_persons_total: int
    # Wall clock [s] of the run (P3.07 divides it by the video seconds to get the real-time factor). ``None`` after a
    # load: pose_raw.npz keeps the deterministic counts only; the wall clock belongs to the run manifest.
    elapsed_s: float | None


@dataclass(frozen=True, eq=False)
class PoseRaw:
    """Raw pose of a segment; persons are compressed rows: frame ``i`` owns rows ``offsets[i]:offsets[i+1]``."""

    recording_id: str
    frame_index: np.ndarray  # (F,) int32, row of the frame in pts.parquet (the frame index of the file)
    t_sec: np.ndarray  # (F,) float64, seconds from the stream start, real PTS, strictly increasing
    person_offsets: np.ndarray  # (F + 1,) int64
    bboxes: np.ndarray  # (D, 4) float32, xyxy [px]
    # (D, 26, 2) float32, x y [px] of the upright image, as the model returned them (never clamped, never filled)
    keypoints: np.ndarray
    scores: np.ndarray  # (D, 26) float32, the model's scores
    from_detector: np.ndarray  # (D,) bool, the box came from the detector (True) or from the previous keypoints (False)
    image_size: tuple[int, int]  # (width, height) [px] of the upright image the coordinates refer to
    display_rotation: int  # [deg] from the manifest, applied before the model saw the frame
    segment_s: tuple[float, float]  # the segment asked for [s]; the frames cover it widened by params.segment_margin_s
    params: PoseRunParams
    model_fingerprint: dict[str, str]
    providers: dict[str, str]
    stats: PoseRunStats

    @property
    def n_frames(self) -> int:
        return int(self.frame_index.size)

    @property
    def n_persons(self) -> np.ndarray:
        """(F,) number of persons in each frame."""
        return np.diff(self.person_offsets)

    def equals(self, other: PoseRaw) -> bool:
        """Same result (``stats`` is ignored: its wall clock differs between runs)."""
        arrays = ("frame_index", "t_sec", "person_offsets", "bboxes", "keypoints", "scores", "from_detector")
        scalars = (
            "recording_id",
            "image_size",
            "display_rotation",
            "segment_s",
            "params",
            "model_fingerprint",
            "providers",
        )
        return all(np.array_equal(getattr(self, a), getattr(other, a), equal_nan=True) for a in arrays) and all(
            getattr(self, s) == getattr(other, s) for s in scalars
        )


def valid_keypoint_mask(keypoints: np.ndarray, scores: np.ndarray, min_score: float) -> np.ndarray:
    """Which keypoints are valid: finite coordinates and a finite score of at least ``min_score``.

    ``keypoints`` is ``(..., 26, 2)`` and ``scores`` ``(..., 26)``; the result is ``(..., 26)`` bool. This one rule
    decides who the runner follows and who the target choice may pick (P3.04).
    """
    return np.isfinite(keypoints).all(axis=-1) & np.isfinite(scores) & (scores >= min_score)


def box_from_keypoints(
    keypoints: np.ndarray,
    scores: np.ndarray,
    image_size: tuple[int, int],
    margin: float,
    min_score: float,
    min_valid: int,
) -> np.ndarray | None:
    """Box (xyxy, float32, pixels) of the valid keypoints widened by ``margin`` on each side, clipped to the image.

    ``image_size`` is ``(width, height)`` in pixels; the box is clipped to ``[0, width] x [0, height]``. ``margin`` is a
    share of the width and of the height of the valid keypoints. Returns ``None`` when fewer than ``min_valid``
    keypoints are valid (finite, score >= ``min_score``) or the box has no area.
    """
    kp = np.asarray(keypoints, dtype=np.float64)
    sc = np.asarray(scores, dtype=np.float64)
    if kp.shape != (NUM_JOINTS, 2):
        raise ValueError(f"keypoints must have shape ({NUM_JOINTS}, 2), got {kp.shape}")
    if sc.shape != (NUM_JOINTS,):
        raise ValueError(f"scores must have shape ({NUM_JOINTS},), got {sc.shape}")
    valid = valid_keypoint_mask(kp, sc, min_score)
    if int(valid.sum()) < min_valid:
        return None
    points = kp[valid]
    x0, y0 = points.min(axis=0)
    x1, y1 = points.max(axis=0)
    width, height = x1 - x0, y1 - y0
    x0, x1 = max(0.0, x0 - margin * width), min(float(image_size[0]), x1 + margin * width)
    y0, y1 = max(0.0, y0 - margin * height), min(float(image_size[1]), y1 + margin * height)
    if x1 - x0 <= 0.0 or y1 - y0 <= 0.0:
        return None
    return np.array([x0, y0, x1, y1], dtype=np.float32)


def _read_recording(rec_dir: Path) -> tuple[RecordingManifest, np.ndarray, np.ndarray, np.ndarray]:
    """The manifest and the table (``frame_index``, ``pts`` ticks, ``t_sec``) of a stored recording."""
    try:
        manifest = read_manifest(rec_dir / "recording.json", RecordingManifest)
    except (OSError, ManifestError) as exc:
        raise PoseRunError("recording.json of the recording could not be read") from exc
    try:
        table = pq.read_table(rec_dir / "pts.parquet")
        frame_index = table["frame_index"].to_numpy()
        pts = table["pts"].to_numpy()
        t_sec = table["t_sec"].to_numpy()
    except (OSError, KeyError, pa.ArrowException) as exc:
        raise PoseRunError(f"pts.parquet of recording {manifest.recording_id} could not be read") from exc
    if t_sec.size != manifest.n_frames:
        raise PoseRunError(
            f"pts.parquet of recording {manifest.recording_id} has {t_sec.size} rows "
            f"but recording.json says {manifest.n_frames} frames"
        )
    if t_sec.size == 0 or not (np.all(np.diff(pts) > 0) and np.all(np.diff(t_sec) > 0)):
        raise PoseRunError(f"pts.parquet of recording {manifest.recording_id} is empty or not strictly increasing")
    return manifest, frame_index, pts, t_sec


def _check_result(result: PoseResult, n_boxes: int) -> None:
    ok = (
        result.bboxes.shape == (n_boxes, 4)
        and result.keypoints.shape == (n_boxes, NUM_JOINTS, 2)
        and result.scores.shape == (n_boxes, NUM_JOINTS)
    )
    if not ok:
        raise PoseRunError(f"the pose model returned shapes {result.keypoints.shape} for {n_boxes} boxes")


def run_pose(
    recording_dir: Path | str,
    start_s: float,
    end_s: float,
    model: PoseModel,
    *,
    params: PoseRunParams | None = None,
    on_frame: Callable[[int, float], None] | None = None,
) -> PoseRaw:
    """Raw pose of everybody in the frames of ``[start_s - margin, end_s + margin]`` of a stored recording.

    Args:
        recording_dir: ``data/recordings/<recording_id>/`` (``source<ext>``, ``recording.json``, ``pts.parquet``).
        start_s: start of the segment [s from the stream start].
        end_s: end of the segment [s]; must be after ``start_s``.
        model: an already built pose model (detector and pose estimator).
        params: cadence and box parameters; the defaults are provisional until P3.07.
        on_frame: optional ``on_frame(position, t_sec)`` called after each frame has been processed (``position``
            counts the frames of the window from 0, ``t_sec`` is the time of the table); it cannot change the result
            and an exception in it ends the run like any other error (P3.07 times the frames with it, P7 will report
            progress with it).

    Returns:
        ``PoseRaw`` (see there for shapes, units and coordinates). A frame without a person has zero rows.

    Raises:
        PoseRunError: bad segment, unreadable manifest or table, a file whose frames are not the rows of its table,
            a frame whose size changes, a model failure (the frame index is in the message; the cause is chained).
            No partial result.
    """
    params = params or PoseRunParams()
    if not (math.isfinite(start_s) and math.isfinite(end_s) and start_s < end_s):
        raise PoseRunError(f"segment {start_s} to {end_s} s is not a finite range with start before end")
    rec_dir = Path(recording_dir)
    manifest, frame_index, pts, t_sec = _read_recording(rec_dir)
    if end_s <= t_sec[0] or start_s > t_sec[-1]:
        raise PoseRunError(
            f"segment {start_s:.3f} to {end_s:.3f} s does not overlap recording {manifest.recording_id} "
            f"(frames from {t_sec[0]:.3f} to {t_sec[-1]:.3f} s)"
        )
    low, high = start_s - params.segment_margin_s - 1e-9, end_s + params.segment_margin_s + 1e-9
    rows = np.flatnonzero((t_sec >= low) & (t_sec <= high))
    if rows.size == 0:
        raise PoseRunError(f"no frame of recording {manifest.recording_id} lies in the window of the segment")

    source = rec_dir / f"source{manifest.source_ext}"
    started = time.perf_counter()
    n_detector = n_pose = 0
    image_size: tuple[int, int] | None = None
    # (keypoints, scores) of the persons that get a box on the next frame, in the order of the previous frame
    followed: list[tuple[np.ndarray, np.ndarray]] = []
    frames_since_detector = 0
    offsets = [0]
    boxes_out: list[np.ndarray] = []
    kp_out: list[np.ndarray] = []
    score_out: list[np.ndarray] = []
    det_out: list[np.ndarray] = []

    frames = iter(
        iter_frames(source, float(t_sec[rows[0]]), float(t_sec[rows[-1]]), rotation_deg=manifest.display_rotation)
    )
    k = 0
    while True:
        try:
            frame = next(frames)
        except StopIteration:
            break
        except (av.error.FFmpegError, OSError) as exc:
            raise PoseRunError(
                f"decoding recording {manifest.recording_id} failed after {k} frames of the window"
            ) from exc
        if k >= rows.size:
            raise PoseRunError(
                f"the file of recording {manifest.recording_id} has more frames in the window than pts.parquet"
            )
        row = int(rows[k])
        if frame.pts != int(pts[row]) or abs(frame.t_sec - float(t_sec[row])) > _TIME_TOLERANCE_S:
            raise PoseRunError(
                f"frame {int(frame_index[row])} of recording {manifest.recording_id} does not match pts.parquet "
                f"(pts {frame.pts} against {int(pts[row])}, t {frame.t_sec:.6f} against {float(t_sec[row]):.6f} s)"
            )
        image = frame.image
        size = (int(image.shape[1]), int(image.shape[0]))
        if image_size is None:
            image_size = size
        elif size != image_size:
            raise PoseRunError(
                f"the frame size of recording {manifest.recording_id} changes at frame {int(frame_index[row])}"
            )

        try:
            result, from_detector, frames_since_detector, calls = _process_frame(
                model, image, size, followed, frames_since_detector, params
            )
        except PoseRunError:
            raise
        except Exception as exc:  # noqa: BLE001 - a third-party model (ONNX Runtime, OpenCV) can raise anything; re-raised with context
            raise PoseRunError(
                f"the pose model failed on frame {int(frame_index[row])} (t = {frame.t_sec:.3f} s) "
                f"of recording {manifest.recording_id}"
            ) from exc
        n_detector += calls[0]
        n_pose += calls[1]

        n = result.keypoints.shape[0]
        if n:
            boxes_out.append(np.asarray(result.bboxes, dtype=np.float32))
            kp_out.append(np.asarray(result.keypoints, dtype=np.float32))
            score_out.append(np.asarray(result.scores, dtype=np.float32))
            det_out.append(np.full(n, from_detector, dtype=bool))
        offsets.append(offsets[-1] + n)
        followed = [
            (result.keypoints[i], result.scores[i])
            for i in range(n)
            if int(valid_keypoint_mask(result.keypoints[i], result.scores[i], params.min_score).sum())
            >= params.min_valid_keypoints
        ]
        if on_frame is not None:
            on_frame(k, float(t_sec[row]))
        k += 1

    if k != rows.size:
        raise PoseRunError(
            f"decoded {k} frames of recording {manifest.recording_id} but pts.parquet has {rows.size} in the window"
        )
    assert image_size is not None  # rows.size >= 1 and k == rows.size

    def stack(chunks: list[np.ndarray], shape: tuple[int, ...], dtype) -> np.ndarray:
        return np.concatenate(chunks, axis=0) if chunks else np.empty(shape, dtype=dtype)

    stats = PoseRunStats(
        n_frames=k,
        n_detector_calls=n_detector,
        n_pose_calls=n_pose,
        n_persons_total=offsets[-1],
        elapsed_s=time.perf_counter() - started,
    )
    log.info(
        "pose of recording %s: %d frames, %d persons, %d detector calls, %.1f s",
        manifest.recording_id,
        stats.n_frames,
        stats.n_persons_total,
        stats.n_detector_calls,
        stats.elapsed_s,
    )
    return PoseRaw(
        recording_id=manifest.recording_id,
        frame_index=frame_index[rows].astype(np.int32),
        t_sec=t_sec[rows].astype(np.float64),
        person_offsets=np.asarray(offsets, dtype=np.int64),
        bboxes=stack(boxes_out, (0, 4), np.float32),
        keypoints=stack(kp_out, (0, NUM_JOINTS, 2), np.float32),
        scores=stack(score_out, (0, NUM_JOINTS), np.float32),
        from_detector=stack(det_out, (0,), np.bool_),
        image_size=image_size,
        display_rotation=manifest.display_rotation,
        segment_s=(float(start_s), float(end_s)),
        params=params,
        model_fingerprint=dict(model.model_fingerprint),
        providers=dict(model.providers),
        stats=stats,
    )


def _process_frame(
    model: PoseModel,
    image: np.ndarray,
    size: tuple[int, int],
    followed: list[tuple[np.ndarray, np.ndarray]],
    frames_since_detector: int,
    params: PoseRunParams,
) -> tuple[PoseResult, bool, int, tuple[int, int]]:
    """One frame: decide detector or derived boxes, run the pose model, repeat with the detector if nobody is followed.

    Returns the result, whether its boxes came from the detector, the new ``frames_since_detector`` (0 on a detector
    frame) and the calls made ``(detector, pose)``.
    """
    detector_calls = pose_calls = 0
    boxes: np.ndarray | None = None
    from_detector = not followed or frames_since_detector + 1 >= params.detect_every_n
    if not from_detector:
        derived = [
            box_from_keypoints(kp, sc, size, params.bbox_margin, params.min_score, params.min_valid_keypoints)
            for kp, sc in followed
        ]
        derived_boxes = [b for b in derived if b is not None]
        if derived_boxes:
            boxes = np.stack(derived_boxes)
        else:
            from_detector = True
    if from_detector:
        boxes = np.asarray(model.detect(image), dtype=np.float32).reshape(-1, 4)
        detector_calls += 1
    assert boxes is not None
    result = _estimate(model, image, boxes)
    pose_calls += int(len(boxes) > 0)
    since = 0 if from_detector else frames_since_detector + 1

    if not from_detector:
        stale_followed = any(
            int(valid_keypoint_mask(result.keypoints[i], result.scores[i], params.min_score).sum())
            >= params.min_valid_keypoints
            for i in range(result.keypoints.shape[0])
        )
        if not stale_followed:  # nobody can be followed from the stale boxes: run the detector now, on this same frame
            boxes = np.asarray(model.detect(image), dtype=np.float32).reshape(-1, 4)
            detector_calls += 1
            result = _estimate(model, image, boxes)
            pose_calls += int(len(boxes) > 0)
            from_detector, since = True, 0
    return result, from_detector, since, (detector_calls, pose_calls)


def _estimate(model: PoseModel, image: np.ndarray, boxes: np.ndarray) -> PoseResult:
    """``model.estimate`` for the boxes; no call (and no persons) when there is no box."""
    if len(boxes) == 0:
        return PoseResult(
            np.empty((0, 4), np.float32),
            np.empty((0, NUM_JOINTS, 2), np.float32),
            np.empty((0, NUM_JOINTS), np.float32),
        )
    result = model.estimate(image, boxes)
    _check_result(result, len(boxes))
    return result
