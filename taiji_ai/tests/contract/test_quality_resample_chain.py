"""P4.04: the uniform grid in the chain of the quality stages (T-QLT-07k, 07l, 07m).

The first part runs SYN-07 (the SYN-05 motion on a variable frame rate, with its truth) through mask, Hampel, the gap
layer and the resampling, with spikes and a short hole put in; the second goes through the tracking stage (association,
target choice, target over time) on a scene of boxes, then ``mask_track``, ``interpolate_track`` and ``resample_gaps``;
the third reads the real timestamps of the video fixtures of F-VID.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.synth import make_sequence, truth_at
from helpers.track_build import FPS, HOME_X, resolve, stands
from taiji_ai.io.frames import scan_pts
from taiji_ai.pose.skeleton import IDX, NUM_JOINTS
from taiji_ai.quality._checks import check_gap_layer
from taiji_ai.quality.filters import hampel_outliers
from taiji_ai.quality.gaps import interpolate_gaps, interpolate_track
from taiji_ai.quality.mask import NOT_TRACKED, OK, OUTLIER, apply_mask, mask_track
from taiji_ai.quality.resample import plan_grid, resample_gaps, resample_layer

FLOAT32_SLACK = 5e-3  # px
SPIKES = (  # (frame, joint, dx, dy): all in the 30 fps part of SYN-07 (the first two seconds), where a hole is short
    (12, IDX["LWrist"], 80.0, 0.0),
    (25, IDX["RAnkle"], 0.0, -90.0),
    (40, IDX["Nose"], 70.0, 70.0),
)


def max_acceleration(seq) -> float:
    """The largest acceleration (px/s^2) of any joint of the analytic motion, from the truth at 3,000 fps."""
    h = 1.0 / 3000.0
    k = truth_at(seq, np.arange(0.0, float(seq.params["duration"]), h))
    return float((np.linalg.norm(np.diff(k, 2, axis=0), axis=-1) / h**2).max())


def through_the_stages(seed: int, jitter: float):
    """SYN-07 with spikes and a hole of two frames, through mask, Hampel, gaps and the resampling."""
    seq = make_sequence("SYN-07", seed=seed, noise_px=0.0, jitter_frac=jitter)
    t, kp, score = np.asarray(seq.t_sec), np.array(seq.kp, copy=True), np.array(seq.score, copy=True)
    spikes = np.zeros(kp.shape[:2], bool)
    for frame, joint, dx, dy in SPIKES:
        kp[frame, joint] += (dx, dy)
        spikes[frame, joint] = True
    score[30:32, IDX["LElbow"]] = 0.1  # a low score: the mask makes a hole of two frames
    mask = apply_mask(kp, score)
    hampel = hampel_outliers(mask.keypoints, mask.reason, t)
    gaps = interpolate_gaps(hampel.keypoints, hampel.reason, t)
    return seq, t, spikes, mask, hampel, gaps, resample_gaps(gaps, t)


@pytest.mark.parametrize(("seed", "jitter"), [(3, 0.0), (5, 0.3), (6, 0.3)])
def test_t_qlt_07k_nothing_is_filled_or_invented_and_every_derived_cell_is_flagged(seed: int, jitter: float):
    _, t, spikes, _, hampel, gaps, grid = through_the_stages(seed, jitter)
    g = grid.gridmap
    assert not g.identity
    check_gap_layer(grid.keypoints, grid.reason, grid.interpolated, g.t_grid)  # the contract of the gap layer
    assert hampel.outlier[spikes].all()  # the spikes are found, removed and bridged by the gap layer
    assert gaps.interpolated[spikes].all() and (gaps.reason[spikes] == OUTLIER).all()
    # the rules, read from the map and the gap layer alone
    right = np.minimum(g.left + 1, len(t) - 1)
    copy = (g.weight == 0.0)[:, None]
    usable = np.where(copy, gaps.usable[g.left], gaps.usable[g.left] & gaps.usable[right]) & ~g.stall[:, None]
    flagged = np.where(copy, gaps.interpolated[g.left], gaps.interpolated[g.left] | gaps.interpolated[right]) & usable
    assert np.array_equal(grid.usable, usable)  # a cell next to an unusable cell is NaN: no hole is filled
    assert np.array_equal(grid.interpolated, flagged)  # a value built on a bridged value is flagged
    assert (grid.interpolated & (grid.reason == OUTLIER)).any()  # and it still says what made the hole
    assert not g.stall.any()  # no pause longer than 0.15 s in these clocks: the longest interval is 125 ms
    assert np.array_equal(grid.source_usable, gaps.usable)  # the layer remembers what was usable at the source


@pytest.mark.parametrize(("seed", "jitter"), [(3, 0.0), (5, 0.3), (6, 0.3)])
def test_t_qlt_07k_the_observed_cells_come_back_within_the_bound(seed: int, jitter: float):
    seq, t, _, _, _, gaps, grid = through_the_stages(seed, jitter)
    g = grid.gridmap
    back = grid.to_source(grid.keypoints)
    came_back = np.isfinite(back[..., 0]) & gaps.observed
    assert came_back.sum() > 0.9 * gaps.observed.sum()  # only the rows next to a hole are lost
    err = np.linalg.norm(back.astype(np.float64) - gaps.keypoints.astype(np.float64), axis=-1)[came_back]
    if jitter == 0.0:
        assert err.max() == 0.0  # the step-down timeline: every row is on a grid time
    else:
        d, s = float(np.diff(t).max()), g.step_s
        assert err.max() <= 1.05 * max_acceleration(seq) * (d**2 + s**2) / 8.0 + FLOAT32_SLACK
    # no cell is back that was not usable at the source
    assert not (np.isfinite(back[..., 0]) & ~gaps.usable).any()


# --- T-QLT-07l: the chain with the tracker ----------------------------------------------------------------------------
def scene():
    """The performer appears at frame 10 and is away from frame 40 to 99; the margins of the segment are kept."""
    return resolve(
        {0: stands(HOME_X, first=10, absent=[(40, 100)]), 1: stands(1500)},
        160,
        at_t_sec=20 / FPS,
        segment_start_pos=5,
    )


def test_t_qlt_07l_a_constant_rate_track_is_the_identity_and_keeps_its_margins_and_its_losses():
    run = scene()
    masked = mask_track(run.target)
    gaps = interpolate_track(masked)
    grid = resample_gaps(gaps, masked.t_sec)
    assert grid.gridmap.identity and not grid.gridmap.resampled and not grid.mixed.any()
    assert grid.keypoints.shape == gaps.keypoints.shape == (run.target.n_frames, NUM_JOINTS, 2)  # no row is cut
    assert np.array_equal(grid.keypoints, gaps.keypoints, equal_nan=True)
    assert np.array_equal(grid.reason, gaps.reason) and np.array_equal(grid.interpolated, gaps.interpolated)
    lost = ~masked.mask.tracked
    assert lost.any() and (grid.reason[lost] == NOT_TRACKED).all() and np.isnan(grid.keypoints[lost]).all()
    assert np.array_equal(grid.to_source(grid.keypoints), gaps.keypoints, equal_nan=True)


def test_t_qlt_07l_one_dropped_row_gives_one_mixed_row_and_no_loss_of_the_target_is_crossed():
    run = scene()
    masked = mask_track(run.target)
    gaps = interpolate_track(masked)
    drop = 120  # a tracked frame after the absence
    assert masked.mask.tracked[drop] and masked.mask.tracked[drop - 1] and masked.mask.tracked[drop + 1]
    keep = np.delete(np.arange(len(masked.t_sec)), drop)
    t = masked.t_sec[keep]
    grid = resample_layer(gaps.keypoints[keep], gaps.reason[keep], gaps.interpolated[keep], t)
    g = grid.gridmap
    assert not g.identity and np.flatnonzero(grid.mixed).tolist() == [drop]
    assert grid.mixed[drop] and grid.usable[drop].all()  # the slot of the dropped row is mixed from its two neighbours
    copies = ~grid.mixed
    assert np.array_equal(grid.keypoints[copies], gaps.keypoints[keep][g.left[copies]], equal_nan=True)
    untracked = np.flatnonzero(~masked.mask.tracked)
    runs = np.split(untracked, np.flatnonzero(np.diff(untracked) > 1) + 1)
    absence = max(runs, key=len)  # the 60 frames in which the performer is away
    inside = (g.t_grid >= masked.t_sec[absence[0]] - 1e-9) & (g.t_grid <= masked.t_sec[absence[-1]] + 1e-9)
    assert len(absence) >= 55 and inside.sum() >= 55
    assert np.isnan(grid.keypoints[inside]).all() and (grid.reason[inside] == NOT_TRACKED).all()
    assert (grid.reason[grid.usable] == OK).all()  # nothing was bridged here: every usable cell is observed


# --- T-QLT-07m: the real timestamps of the F-VID fixtures -------------------------------------------------------------
def smooth(t: np.ndarray):
    j = np.arange(NUM_JOINTS)[None, :]
    kp = np.empty((len(t), NUM_JOINTS, 2))
    kp[..., 0] = 300.0 + 4.0 * j + 60.0 * np.sin(2.0 * t[:, None] + 0.1 * j)
    kp[..., 1] = 400.0 + 3.0 * j + 40.0 * np.cos(1.5 * t[:, None])
    return kp, np.zeros((len(t), NUM_JOINTS), np.uint8), np.zeros((len(t), NUM_JOINTS), bool)


@pytest.mark.parametrize("fixture", ["coarse_cfr_30", "coarse_cfr_2997"])
def test_t_qlt_07m_a_constant_rate_on_a_time_base_of_one_millisecond_is_the_identity(fixture: str, request):
    t, _ = scan_pts(request.getfixturevalue(fixture))
    g = plan_grid(np.asarray(t))
    assert g.identity and len(t) >= 100
    assert g.step_s == pytest.approx(np.mean(np.diff(t)), rel=5e-3)
    assert np.diff(t).std() > 0.0  # the intervals are 33 and 34 ms, yet the clock is constant
    kp, reason, interp = smooth(np.asarray(t))
    assert resample_layer(kp, reason, interp, np.asarray(t)).keypoints.tobytes() == kp.tobytes()


def test_t_qlt_07m_the_video_with_a_dropped_frame_gets_one_mixed_grid_row(dropped_frame_video):
    t, _ = scan_pts(dropped_frame_video)
    t = np.asarray(t)
    assert len(t) == 299
    kp, reason, interp = smooth(t)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    assert not g.identity and g.step_s == pytest.approx(1.0 / 30.0, rel=1e-9)
    assert np.flatnonzero(r.mixed).tolist() == [150] and g.weight[150] == pytest.approx(0.5)
    assert len(g.t_grid) == 300 and r.usable.all()


def test_t_qlt_07m_the_video_that_slows_down_is_resampled_to_its_median_rate(vfr_video):
    t, _ = scan_pts(vfr_video)
    t = np.asarray(t)
    kp, reason, interp = smooth(t)
    r = resample_layer(kp, reason, interp, t)
    g = r.gridmap
    slow = int(np.sum(np.diff(t) > 0.09))  # the intervals of 100 ms
    assert not g.identity and slow >= 5
    assert g.step_s == pytest.approx(1.0 / 30.0, rel=1e-6) and not g.stall.any()
    assert int(r.mixed.sum()) == 2 * slow  # two grid times inside each slow interval, every row is on the grid
    assert r.usable.all()
