"""Layers for the metric tests (P5.03): a real ``PoseFiltered`` from the quality chain, and edits that keep its
contract.

A ``PoseFiltered`` is a plain frozen dataclass whose checks run in ``pose_filtered_from_result`` and in the file
reader. So a test gets a valid layer (meta, grid, map back) once, through the real chain, and then replaces the arrays
it cares about with ``dataclasses.replace``. The edits keep the contract of the final layer that the metrics read:
a cell without a value has a reason from 1 to 6, a cell with a value and a reason other than ``ok`` is a bridged one
and is flagged ``interpolated``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

from helpers.quality_fixtures import static_pose
from helpers.synth import SynthSequence
from taiji_ai.pose.skeleton import IDX, NUM_JOINTS
from taiji_ai.quality.chain import QualityParams, run_quality_arrays
from taiji_ai.quality.layers_io import PoseFiltered, pose_filtered_from_result
from taiji_ai.schemas.quality_layers import DataSource

RECORDING_ID = "0b6f3c1e-5a2d-4f8e-9c3a-7d1e2b4a6c80"
OTHER_RECORDING_ID = "5d2f9a47-1c3b-4e60-8a7d-2b9e4c1f6a13"
SOURCES = (DataSource(dataset_id="D08", license="own recordings"),)
OTHER_SOURCES = (DataSource(dataset_id="D20", license="web lesson videos"),)
FPS = 30.0
LH, RH, LS, RS = IDX["LHip"], IDX["RHip"], IDX["LShoulder"], IDX["RShoulder"]
TORSO_PX = 150.0  # the trunk of ``static_pose``
_STATIC_HIP_Y = 337.5  # the middle of the hips of ``static_pose``


def body(n: int, hip_y: float | np.ndarray = 400.0, trunk: float = TORSO_PX) -> np.ndarray:
    """``(n, 26, 2)`` float32: a standing person whose mid-hip is at ``hip_y`` (a number, or one per row) and whose
    trunk (mid-shoulder to mid-hip) is ``trunk`` pixels, y down. The other joints keep their place relative to the
    hips."""
    kp = static_pose(n, dtype=np.float64)
    hip = np.broadcast_to(np.asarray(hip_y, dtype=np.float64), (n,))
    kp[..., 1] += (hip - _STATIC_HIP_Y)[:, None]
    kp[:, [LS, RS], 1] += TORSO_PX - trunk  # shoulders closer to or farther from the hips
    return kp.astype(np.float32)


def layer_of(
    keypoints: np.ndarray,
    t_sec: np.ndarray | None = None,
    scores: np.ndarray | None = None,
    *,
    in_segment: np.ndarray | None = None,
    recording_id: str = RECORDING_ID,
    data_sources: tuple[DataSource, ...] = SOURCES,
    params: QualityParams | None = None,
) -> PoseFiltered:
    """The final layer of ``keypoints`` through the real quality chain (``t_sec`` at 30 fps, scores 0.95 by default;
    ``params`` are the parameters of the chain, the defaults when ``None``)."""
    n = len(keypoints)
    t = np.arange(n) / FPS if t_sec is None else np.asarray(t_sec, dtype=np.float64)
    score = np.full((n, NUM_JOINTS), 0.95, dtype=np.float32) if scores is None else scores
    result = run_quality_arrays(keypoints, score, t, in_segment=in_segment, params=params)
    return pose_filtered_from_result(
        result, recording_id=recording_id, frame_index=np.arange(n, dtype=np.int64), data_sources=data_sources
    )


def layer_of_sequence(
    seq: SynthSequence,
    keypoints: np.ndarray | None = None,
    rows: np.ndarray | None = None,
    *,
    recording_id: str = RECORDING_ID,
    params: QualityParams | None = None,
) -> PoseFiltered:
    """The final layer of a generator sequence through the real chain: its own keypoints or ``keypoints`` (for a rolled
    camera), all rows or only the boolean ``rows`` (the standing reference of SYN-09 is its own segment)."""
    kp = seq.kp if keypoints is None else keypoints
    kp, t, score = (kp, seq.t_sec, seq.score) if rows is None else (kp[rows], seq.t_sec[rows], seq.score[rows])
    return layer_of(np.asarray(kp, dtype=np.float32), t, score, recording_id=recording_id, params=params)


def exact_layer(
    keypoints: np.ndarray,
    *,
    segment: tuple[int, int] | None = None,
    recording_id: str = RECORDING_ID,
    data_sources: tuple[DataSource, ...] = SOURCES,
) -> PoseFiltered:
    """A layer whose grid keypoints are exactly ``keypoints`` (no filter), every cell ``ok``.

    ``segment`` is ``(first_row, stop_row)`` of the rows in the segment (all rows by default); the rows outside are
    the margins. The meta, the clock and the map back come from the real chain run on a static body of the same length.
    """
    n = len(keypoints)
    in_segment = None
    if segment is not None:
        in_segment = np.zeros(n, dtype=bool)
        in_segment[segment[0] : segment[1]] = True
    base = layer_of(body(n), in_segment=in_segment, recording_id=recording_id, data_sources=data_sources)
    return edited(
        base,
        keypoints=keypoints,
        reason=np.zeros((n, NUM_JOINTS), dtype=np.uint8),
        interpolated=np.zeros((n, NUM_JOINTS), dtype=bool),
    )


def edited(layer: PoseFiltered, **arrays: Any) -> PoseFiltered:
    """The same layer with some arrays replaced by read-only copies of the given ones (same dtype as before)."""
    changes: dict[str, np.ndarray] = {}
    for name, value in arrays.items():
        copy = np.array(value, dtype=getattr(layer, name).dtype, copy=True)
        copy.setflags(write=False)
        changes[name] = copy
    return dataclasses.replace(layer, **changes)


def cells(layer: PoseFiltered) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Writable copies of ``(keypoints, reason, interpolated)`` of the grid, to edit and give back to ``edited``."""
    return layer.keypoints.copy(), layer.reason.copy(), layer.interpolated.copy()


def drop(kp: np.ndarray, reason: np.ndarray, row: int, joint: int, code: int) -> None:
    """The cell has no value: NaN with the reason ``code`` (1 to 6)."""
    kp[row, joint] = np.nan
    reason[row, joint] = code


def bridge(kp: np.ndarray, reason: np.ndarray, interp: np.ndarray, row: int, joint: int, code: int = 2) -> None:
    """The cell keeps its value but is a bridged one: a reason other than ``ok`` and the flag ``interpolated``."""
    reason[row, joint] = code
    interp[row, joint] = True
