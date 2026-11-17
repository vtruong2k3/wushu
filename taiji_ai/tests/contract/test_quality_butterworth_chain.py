"""P4.05: the Butterworth stage in the chain of the quality stages (T-QLT-08g, 08h).

The first part runs SYN-05 and SYN-07 (the same motion, with its truth) through mask, Hampel, the gap layer, the uniform
grid and the filter; the second goes through the tracking stage (association, target choice, target over time) on a
scene of boxes, then ``mask_track``, ``interpolate_track``, ``resample_gaps`` and ``lowpass_grid``. The bounds of the
first part are measured on the generator (they are written next to the number that they were set from) and checked
against the truth of the motion."""

from __future__ import annotations

import numpy as np
import pytest

from helpers.synth import make_sequence, truth_at
from helpers.track_build import FPS, HOME_X, resolve, stands
from taiji_ai.pose.skeleton import IDX, NUM_JOINTS
from taiji_ai.quality._checks import check_gap_layer
from taiji_ai.quality.filters import RUN_FILTERED, hampel_outliers, lowpass_grid
from taiji_ai.quality.gaps import interpolate_gaps, interpolate_track
from taiji_ai.quality.mask import NOT_TRACKED, OUTLIER, apply_mask, mask_track
from taiji_ai.quality.resample import resample_gaps

INTERIOR = slice(30, -30)  # rows far enough from both ends of a run for the start-up of the filter to be over
SPIKES = (  # (frame, joint, dx, dy): in the 30 fps part, where a hole of one frame is bridged
    (40, IDX["LWrist"], 80.0, 0.0),
    (70, IDX["RAnkle"], 0.0, -90.0),
)


def through_the_stages(name: str, seed: int, noise_px: float = 0.0, spikes=()):
    seq = make_sequence(name, seed=seed, noise_px=noise_px)
    t, kp = np.asarray(seq.t_sec), np.array(seq.kp, copy=True)
    for frame, joint, dx, dy in spikes:
        kp[frame, joint] += (dx, dy)
    mask = apply_mask(kp, seq.score)
    hampel = hampel_outliers(mask.keypoints, mask.reason, t)
    gaps = interpolate_gaps(hampel.keypoints, hampel.reason, t)
    grid = resample_gaps(gaps, t)
    return seq, t, hampel, gaps, grid, lowpass_grid(grid)


def error_against_truth(seq, layer_keypoints: np.ndarray, times: np.ndarray) -> np.ndarray:
    """The distance (px) of every cell of a layer from the noise-free motion at its time: ``(rows, 26)``."""
    return np.linalg.norm(layer_keypoints.astype(np.float64) - truth_at(seq, times), axis=-1)


# --- T-QLT-08g: SYN-05 and SYN-07 with known truth --------------------------------------------------------------------
def test_t_qlt_08g_without_noise_the_filter_stays_within_a_small_distance_of_the_truth_of_syn_05():
    seq, t, _, _, grid, filt = through_the_stages("SYN-05", seed=5)
    assert grid.gridmap.identity and filt.filtered.all() and len(filt.runs) == NUM_JOINTS
    err = error_against_truth(seq, filt.keypoints, t)
    assert err[INTERIOR].max() <= BOUND_SYN_05_PX, err[INTERIOR].max()  # set from the measurement below
    assert err[INTERIOR].max() > 0.01  # not vacuous: a 6 Hz filter does change a movement with ramps of 0.2 s


def test_t_qlt_08g_with_one_pixel_of_noise_the_filtered_layer_is_nearer_the_truth_than_the_unfiltered_one():
    seq, t, _, gaps, _, filt = through_the_stages("SYN-05", seed=6, noise_px=1.0)
    before = error_against_truth(seq, gaps.keypoints, t)[INTERIOR]
    after = error_against_truth(seq, filt.keypoints, t)[INTERIOR]
    assert float(np.sqrt((after**2).mean())) < RMS_RATIO_WITH_NOISE * float(np.sqrt((before**2).mean()))
    assert float(np.sqrt((after**2).mean())) < float(np.sqrt((before**2).mean()))


def test_t_qlt_08g_a_spike_that_hampel_removes_leaves_no_trace_after_the_gap_layer_and_the_filter():
    seq, t, hampel, gaps, _, filt = through_the_stages("SYN-05", seed=7, spikes=SPIKES)
    for frame, joint, _, _ in SPIKES:
        assert hampel.outlier[frame, joint] and gaps.interpolated[frame, joint] and gaps.reason[frame, joint] == OUTLIER
        assert filt.filtered[frame, joint] and filt.interpolated[frame, joint]  # filtered, and still a bridged value
    clean = through_the_stages("SYN-05", seed=7)[5]
    near = np.zeros(filt.filtered.shape, bool)
    for frame, joint, _, _ in SPIKES:
        near[frame - 3 : frame + 4, joint] = True
    assert np.abs(filt.keypoints[near] - clean.keypoints[near]).max() <= BOUND_SPIKE_TRACE_PX


def test_t_qlt_08g_on_the_variable_frame_rate_of_syn_07_the_grid_layer_is_filtered_on_its_regular_clock():
    seq, t, _, _, grid, filt = through_the_stages("SYN-07", seed=3)
    g = grid.gridmap
    assert not g.identity and filt.sampling_hz == pytest.approx(30.0, rel=1e-9)
    assert filt.filtered.all() and set(filt.runs.outcome.tolist()) == {RUN_FILTERED}
    err = error_against_truth(seq, filt.keypoints, g.t_grid)
    assert err[INTERIOR].max() <= BOUND_SYN_07_PX, err[INTERIOR].max()
    check_gap_layer(
        filt.keypoints, filt.reason, filt.interpolated, g.t_grid
    )  # the filtered layer is a layer of the same kind


# the bounds, each set to about twice the largest value measured on the generator over several seeds
# (Docs/tasks/P4.05.md, M-QLT-05 C): SYN-05 without noise, interior rows: largest error 0.046 px; SYN-07 on its grid
# (30 fps, linear mix between the slow rows included): 0.147 px; the trace of a spike that Hampel removed and the gap
# layer bridged, against the same run without the spike: under 0.001 px; the root-mean-square error with 1 px of noise
# falls to 0.595 to 0.617 of its value
BOUND_SYN_05_PX = 0.1
BOUND_SYN_07_PX = 0.3
BOUND_SPIKE_TRACE_PX = 0.05
RMS_RATIO_WITH_NOISE = 0.7


# --- T-QLT-08h: the chain with the tracker ----------------------------------------------------------------------------
def scene():
    """The performer appears at frame 10 and is away from frame 40 to 99; the margins of the segment are kept."""
    return resolve(
        {0: stands(HOME_X, first=10, absent=[(40, 100)]), 1: stands(1500)},
        160,
        at_t_sec=20 / FPS,
        segment_start_pos=5,
    )


def test_t_qlt_08h_the_loss_of_the_target_splits_the_runs_and_the_take_is_filtered_on_both_sides():
    run = scene()
    masked = mask_track(run.target)
    gaps = interpolate_track(masked)
    grid = resample_gaps(gaps, masked.t_sec)
    filt = lowpass_grid(grid)
    assert grid.gridmap.identity and filt.keypoints.shape == gaps.keypoints.shape == (
        run.target.n_frames,
        NUM_JOINTS,
        2,
    )
    untracked = ~masked.mask.tracked
    assert (
        untracked.any() and (filt.reason[untracked] == NOT_TRACKED).all() and np.isnan(filt.keypoints[untracked]).all()
    )
    assert not filt.filtered[untracked].any()
    tracked = masked.mask.tracked
    assert np.array_equal(filt.filtered, np.isfinite(gaps.keypoints[..., 0])) and filt.filtered[tracked].all()
    joint0 = [
        (int(a), int(b), int(o))
        for j, a, b, o in zip(filt.runs.joint, filt.runs.start, filt.runs.end, filt.runs.outcome, strict=True)
        if j == 0
    ]
    assert len(joint0) == 2 and all(o == RUN_FILTERED for _, _, o in joint0)  # the absence splits the take in two
    assert joint0[0][1] < np.flatnonzero(untracked & (np.arange(len(untracked)) > joint0[0][1]))[0] <= joint0[1][0]
    # the performer stands still: a filter that sees only its own run leaves a constant exactly constant
    assert np.allclose(filt.keypoints[tracked], gaps.keypoints[tracked], rtol=0.0, atol=1e-6)
