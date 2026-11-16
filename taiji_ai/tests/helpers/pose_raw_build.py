"""A ``PoseRaw`` of known content, built by hand (no video, no model), for the P3.03 tests.

Six frames with 0, 1, 2, 1, 0 and 3 persons (seven persons in all, one of them weak), a score that is NaN, a keypoint
outside the image and a wall clock in the stats (which the file must not keep).
"""

from __future__ import annotations

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
