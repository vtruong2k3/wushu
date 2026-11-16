"""T-SYNC-04k, 04l: ``find_flash_onsets`` on synthetic brightness series (P2.05 rework, BUG-0068).

The series are mean-luma values per frame at 30 fps: a flat level with Gaussian noise and a flash that adds a step.
"""

from __future__ import annotations

import numpy as np

from taiji_ai.io.flash import FlashParams, find_flash_onsets

FPS = 30
T = np.arange(0, 20, 1 / FPS)  # 600 frames


def _series(noise_std: float, steps: list[tuple[int, float]], seed: int) -> np.ndarray:
    """Level 100 with noise; each ``(frame, step)`` raises the level by ``step`` from that frame on, for 15 frames."""
    rng = np.random.default_rng(seed)
    luma = 100.0 + rng.normal(0.0, noise_std, T.size)
    for frame, step in steps:
        luma[frame : frame + 15] += step
    return luma


def test_t_sync_04k_a_noisy_window_raises_the_threshold_and_gives_only_the_real_flash():
    """Frame noise of 4 levels throws differences above the fixed 15 levels; the spread-based threshold ignores them."""
    luma = _series(noise_std=4.0, steps=[(300, 70.0)], seed=3)
    # The scenario is meaningful only if the fixed step alone would let noise through.
    assert len(find_flash_onsets(T, luma, params=FlashParams(k_mad=0.0))) > 1

    onsets = find_flash_onsets(T, luma)

    assert onsets == [float(T[300])]


def test_t_sync_04l_an_onset_that_rises_over_two_frames_is_one_onset():
    """Two consecutive frames above the threshold are one flash: the refractory time keeps the first."""
    luma = _series(noise_std=0.3, steps=[(150, 40.0), (151, 40.0)], seed=1)

    assert find_flash_onsets(T, luma) == [float(T[150])]


def test_t_sync_04l_two_flashes_one_second_apart_are_two_onsets():
    luma = _series(noise_std=0.3, steps=[(150, 60.0), (180, 60.0)], seed=2)

    assert find_flash_onsets(T, luma) == [float(T[150]), float(T[180])]


def test_t_sync_04l_empty_and_one_sample_input_have_no_onset():
    assert find_flash_onsets(np.array([]), np.array([])) == []
    assert find_flash_onsets(np.array([0.0]), np.array([100.0])) == []
