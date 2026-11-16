"""T-SCH-03: the header model of ``pose_raw.npz`` (``PoseRawMeta``, schema ``pose_raw/1``) (P3.03)."""

from __future__ import annotations

import copy
import math

import pytest

from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.pose import PoseRawMeta

GOOD = {
    "schema_version": "pose_raw/1",
    "skeleton": "halpe26/1",
    "recording_id": "3f2b8c1e-5d4a-4e7b-9c1a-0b2d3e4f5a6b",
    "image_size": [1920, 1080],
    "display_rotation": 0,
    "segment_s": [0.5, 0.9],
    "params": {
        "detect_every_n": 5,
        "bbox_margin": 0.12,
        "min_score": 0.3,
        "min_valid_keypoints": 6,
        "segment_margin_s": 1.0,
    },
    "model_fingerprint": {"det": "0" * 64, "pose": "1" * 64},
    "providers": {"det": "CUDAExecutionProvider", "pose": "CUDAExecutionProvider"},
    "counts": {"n_frames": 6, "n_detector_calls": 4, "n_pose_calls": 5, "n_persons_total": 7},
}


def _with(**changes):
    data = copy.deepcopy(GOOD)
    for key, value in changes.items():
        if value is None:
            data.pop(key)
        else:
            data[key] = value
    return data


def test_t_sch_03_a_good_header_is_accepted():
    meta = parse_manifest(PoseRawMeta, GOOD)
    assert meta.schema_version == "pose_raw/1" and meta.counts.n_persons_total == 7


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(_with(schema_version=None), id="missing_version"),
        pytest.param(_with(schema_version="pose_raw/2"), id="other_version"),
        pytest.param(_with(extra_field=1), id="unknown_field"),
        pytest.param(_with(recording_id="not-a-uuid"), id="bad_recording_id"),
        pytest.param(_with(image_size=[0, 1080]), id="image_width_zero"),
        pytest.param(_with(image_size=[1920]), id="image_size_one_value"),
        pytest.param(_with(display_rotation=45), id="rotation_45"),
        pytest.param(_with(segment_s=[0.9, 0.5]), id="segment_reversed"),
        pytest.param(_with(segment_s=[0.5, 0.5]), id="segment_empty"),
        pytest.param(_with(segment_s=[0.5, math.nan]), id="segment_nan"),
        pytest.param(_with(segment_s=[0.5, math.inf]), id="segment_inf"),
        pytest.param(_with(model_fingerprint={}), id="fingerprint_empty"),
        pytest.param(_with(model_fingerprint={"det": "xyz"}), id="fingerprint_not_sha256"),
        pytest.param(_with(providers={}), id="providers_empty"),
        pytest.param(_with(counts={**GOOD["counts"], "n_frames": 0}), id="no_frames"),
        pytest.param(_with(counts={**GOOD["counts"], "n_persons_total": -1}), id="negative_count"),
        pytest.param(_with(counts={"n_frames": 6}), id="counts_incomplete"),
        pytest.param(_with(params={**GOOD["params"], "detect_every_n": 0}), id="n_zero"),
        pytest.param(_with(params={**GOOD["params"], "min_valid_keypoints": 27}), id="min_valid_27"),
        pytest.param(_with(params={**GOOD["params"], "bbox_margin": math.nan}), id="margin_nan"),
        pytest.param(_with(params={**GOOD["params"], "unknown": 1}), id="unknown_param"),
        pytest.param(_with(display_rotation="0"), id="rotation_as_text"),
    ],
)
def test_t_sch_03_a_bad_header_is_refused(bad: dict):
    with pytest.raises(ManifestError):
        parse_manifest(PoseRawMeta, bad)
