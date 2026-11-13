"""Smoke test of the real pose models on GPU. Skipped when models or CUDA are unavailable."""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.config import get_settings

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module")
def estimator():
    s = get_settings()
    if not s.registry_path.exists():
        pytest.skip("models not fetched (run tools/fetch_models.py)")
    import onnxruntime as ort

    if "CUDAExecutionProvider" not in ort.get_available_providers():
        pytest.skip("CUDA provider not available")
    from taiji_ai.pose.registry import ModelRegistry
    from taiji_ai.pose.rtm import PoseEstimator

    return PoseEstimator(ModelRegistry(s.registry_path), device="cuda")


def test_sessions_run_on_cuda(estimator):
    assert estimator.providers == {"det": "CUDAExecutionProvider", "pose": "CUDAExecutionProvider"}
    assert len(estimator.model_fingerprint) == 2


def test_output_shapes(estimator):
    img = np.full((720, 1280, 3), 127, np.uint8)
    assert estimator.detect(img).shape[1:] == (4,)
    res = estimator.estimate(img, np.array([[500, 100, 780, 700]], np.float32))
    assert res.keypoints.shape == (1, 26, 2) and res.scores.shape == (1, 26)
    empty = estimator.estimate(img, np.empty((0, 4), np.float32))
    assert empty.keypoints.shape == (0, 26, 2)
