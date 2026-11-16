"""A ``PoseRaw`` of known content, built by hand (no video, no model), for the P3.03 tests.

Six frames with 0, 1, 2, 1, 0 and 3 persons (seven persons in all, one of them weak), a score that is NaN, a keypoint
outside the image and a wall clock in the stats (which the file must not keep).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import numpy as np

from taiji_ai.pose.runner import PoseRaw, PoseRunParams, PoseRunStats

RECORDING_ID = "3f2b8c1e-5d4a-4e7b-9c1a-0b2d3e4f5a6b"
PERSONS_PER_FRAME = (0, 1, 2, 1, 0, 3)


def make_pose_raw(*, empty: bool = False, seed: int = 7) -> PoseRaw:
    rng = np.random.default_rng(seed)
    counts = (0,) * 6 if empty else PERSONS_PER_FRAME
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    d = int(offsets[-1])
    keypoints = rng.uniform(0.0, 300.0, (d, 26, 2)).astype(np.float32)
    scores = rng.uniform(0.0, 1.0, (d, 26)).astype(np.float32)
    bboxes = rng.uniform(0.0, 300.0, (d, 4)).astype(np.float32)
    if d:
        keypoints[0, 0] = (-25.0, 400.0)  # outside the image: the raw layer keeps it
        scores[1, 3] = np.nan  # a score that is NaN: kept as it is
        scores[2, :] = 0.05  # a weak person
    return PoseRaw(
        recording_id=RECORDING_ID,
        frame_index=np.array([10, 11, 12, 13, 14, 15], np.int32),
        t_sec=np.array(
            [0.40, 0.4333333333333333, 0.4666666666666667, 0.5, 0.5333333333333333, 0.5666666666666667], np.float64
        ),
        person_offsets=offsets,
        bboxes=bboxes,
        keypoints=keypoints,
        scores=scores,
        from_detector=(np.arange(d) % 2 == 0),
        image_size=(1920, 1080),
        display_rotation=0,
        segment_s=(0.5, 0.9),
        params=PoseRunParams(
            detect_every_n=3, bbox_margin=0.15, min_score=0.35, min_valid_keypoints=7, segment_margin_s=0.5
        ),
        model_fingerprint={"fake_det": "0" * 64, "fake_pose": "1" * 64},
        providers={"det": "CUDAExecutionProvider", "pose": "CUDAExecutionProvider"},
        stats=PoseRunStats(n_frames=6, n_detector_calls=4, n_pose_calls=5, n_persons_total=d, elapsed_s=1.234),
    )


def box(cx: float, cy: float, w: float, h: float) -> tuple[float, float, float, float]:
    """xyxy box of width ``w`` and height ``h`` centred on ``(cx, cy)``."""
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def pose_raw_from_boxes(
    frames: list[list[tuple[tuple[float, float, float, float], int]]],
    *,
    fps: float = 30.0,
    segment_start_pos: int = 0,
    image_size: tuple[int, int] = (1920, 1080),
    first_frame_index: int = 100,
) -> PoseRaw:
    """A ``PoseRaw`` from explicit boxes: ``frames[k]`` lists ``(box, n_valid_keypoints)`` of the persons of a frame.

    The 26 keypoints are spread over the box; the first ``n_valid`` score 0.9, the others 0.05 (a weak person).
    ``t_sec`` is ``k / fps``; the segment starts at frame ``segment_start_pos`` and ends at the last frame.
    """
    n = len(frames)
    counts = [len(f) for f in frames]
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    d = int(offsets[-1])
    bboxes = np.zeros((d, 4), np.float32)
    keypoints = np.zeros((d, 26, 2), np.float32)
    scores = np.zeros((d, 26), np.float32)
    row = 0
    j = np.arange(26)
    for persons in frames:
        for b, n_valid in persons:
            x0, y0, x1, y1 = b
            bboxes[row] = b
            keypoints[row, :, 0] = x0 + (x1 - x0) * (j % 5) / 4.0
            keypoints[row, :, 1] = y0 + (y1 - y0) * (j // 5) / 5.0
            scores[row] = np.where(j < n_valid, 0.9, 0.05)
            row += 1
    t_sec = np.arange(n) / fps
    return PoseRaw(
        recording_id=RECORDING_ID,
        frame_index=np.arange(first_frame_index, first_frame_index + n, dtype=np.int32),
        t_sec=t_sec,
        person_offsets=offsets,
        bboxes=bboxes,
        keypoints=keypoints,
        scores=scores,
        from_detector=np.ones(d, bool),
        image_size=image_size,
        display_rotation=0,
        segment_s=(float(t_sec[segment_start_pos]), float(t_sec[-1])),
        params=PoseRunParams(),
        model_fingerprint={"fake_det": "0" * 64, "fake_pose": "1" * 64},
        providers={"det": "CUDAExecutionProvider", "pose": "CUDAExecutionProvider"},
        stats=PoseRunStats(n_frames=n, n_detector_calls=n, n_pose_calls=n, n_persons_total=d, elapsed_s=None),
    )


def pose_raw_from_scene(scene) -> tuple[PoseRaw, np.ndarray]:
    """A ``SynthScene`` (SYN-12) as a ``PoseRaw``; also the true identity of every person row (``(D,)`` int)."""
    ids_slots = np.asarray(scene.truth["person_id"])
    n_t = ids_slots.shape[0]
    kp, sc, bb, ids, counts = [], [], [], [], []
    for t in range(n_t):
        slots = [s for s in range(ids_slots.shape[1]) if ids_slots[t, s] >= 0]
        counts.append(len(slots))
        for s in slots:
            kp.append(scene.kp[t, s])
            sc.append(scene.score[t, s])
            bb.append(scene.bbox[t, s])
            ids.append(int(ids_slots[t, s]))
    d = len(ids)
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    raw = PoseRaw(
        recording_id=RECORDING_ID,
        frame_index=np.arange(n_t, dtype=np.int32),
        t_sec=np.asarray(scene.t_sec, np.float64),
        person_offsets=offsets,
        bboxes=np.asarray(bb, np.float32).reshape(d, 4),
        keypoints=np.asarray(kp, np.float32).reshape(d, 26, 2),
        scores=np.asarray(sc, np.float32).reshape(d, 26),
        from_detector=np.ones(d, bool),
        image_size=(1920, 1080),
        display_rotation=0,
        segment_s=(float(scene.t_sec[0]), float(scene.t_sec[-1])),
        params=PoseRunParams(),
        model_fingerprint={"fake_det": "0" * 64, "fake_pose": "1" * 64},
        providers={"det": "CUDAExecutionProvider", "pose": "CUDAExecutionProvider"},
        stats=PoseRunStats(n_frames=n_t, n_detector_calls=n_t, n_pose_calls=n_t, n_persons_total=d, elapsed_s=None),
    )
    return raw, np.asarray(ids, np.int32)


def scene_from_paths(
    paths: dict[int, Callable[[int], tuple[tuple[float, float, float, float], int] | None]],
    *,
    n_frames: int,
    fps: float = 30.0,
    shuffle_seed: int | None = None,
    **kwargs,
) -> tuple[PoseRaw, np.ndarray]:
    """People moving along explicit paths: ``paths[identity](k)`` is ``(box, n_valid)`` in frame ``k``, or ``None``.

    Returns the ``PoseRaw`` (the box is also the hull of the 26 keypoints) and the identity of every person row. The
    people of a frame are listed in the order of their identity, or shuffled when ``shuffle_seed`` is given.
    """
    rng = np.random.default_rng(shuffle_seed) if shuffle_seed is not None else None
    frames, ids = [], []
    for k in range(n_frames):
        present = [(ident, p) for ident, fn in sorted(paths.items()) if (p := fn(k)) is not None]
        if rng is not None:
            present = [present[i] for i in rng.permutation(len(present))]
        frames.append([p for _, p in present])
        ids += [ident for ident, _ in present]
    return pose_raw_from_boxes(frames, fps=fps, **kwargs), np.asarray(ids, np.int32)


def permute_persons_in_frames(raw: PoseRaw, ids: np.ndarray, seed: int) -> tuple[PoseRaw, np.ndarray]:
    """The same ``PoseRaw`` with the persons of every frame listed in another (seeded) order."""
    rng = np.random.default_rng(seed)
    order = np.concatenate(
        [
            int(raw.person_offsets[f]) + rng.permutation(int(raw.person_offsets[f + 1] - raw.person_offsets[f]))
            for f in range(raw.n_frames)
        ]
    ).astype(np.int64)
    permuted = dataclasses.replace(
        raw,
        bboxes=raw.bboxes[order],
        keypoints=raw.keypoints[order],
        scores=raw.scores[order],
        from_detector=raw.from_detector[order],
    )
    return permuted, ids[order]
