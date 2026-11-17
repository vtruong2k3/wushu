"""P4.03: the Hampel stage on SYN-05 with spikes and on the target of P3.06 (T-QLT-06k, T-QLT-06l).

The first half puts spikes of known place and size into the smooth movement of SYN-05 (whose true positions are
known) and runs the stages in the order of the plan: mask, Hampel, gaps. The second half goes through the whole chain
of the tracking stage (association, target choice, target over time) on a scene of boxes, then ``mask_track`` and
``hampel_track``.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from helpers.synth import make_sequence
from helpers.track_build import FPS, HOME_X, resolve, stands
from taiji_ai.pose.skeleton import IDX
from taiji_ai.quality.filters import HampelParams, hampel_outliers, hampel_track
from taiji_ai.quality.gaps import FILLED, interpolate_gaps
from taiji_ai.quality.mask import NOT_TRACKED, OUTLIER, apply_mask, mask_track
from taiji_ai.track.state import TRACKED

TOLERANCE_PX = 2.0  # the plan's tolerance for a bridge on the smooth motion of SYN-05 and SYN-06

SPIKES = (  # (frame, joint, dx, dy): single spikes, a vertical one, a diagonal one and two in a row
    (20, IDX["LWrist"], 80.0, 0.0),
    (45, IDX["RAnkle"], 0.0, -90.0),
    (70, IDX["Nose"], 70.0, 70.0),
    (95, IDX["LElbow"], 80.0, 0.0),
    (96, IDX["LElbow"], -80.0, 0.0),
)


def spiked_sequence(noise_px: float = 0.0, seed: int = 5):
    seq = make_sequence("SYN-05", seed=seed, noise_px=noise_px)
    kp = np.array(seq.kp, copy=True)
    cells = np.zeros(kp.shape[:2], bool)
    for frame, joint, dx, dy in SPIKES:
        kp[frame, joint] += (dx, dy)
        cells[frame, joint] = True
    return seq, kp, cells


# --- T-QLT-06k: SYN-05 with spikes through mask, Hampel and the gap layer ---------------------------------------------
def test_t_qlt_06k_every_spike_is_flagged_removed_bridged_and_flagged_again_by_the_gap_layer():
    seq, kp, spikes = spiked_sequence()
    mask = apply_mask(kp, seq.score)
    hampel = hampel_outliers(mask.keypoints, mask.reason, seq.t_sec)
    assert np.array_equal(hampel.outlier, spikes)  # exactly the spikes on the noise-free movement
    assert np.isnan(hampel.keypoints[spikes]).all() and (hampel.reason[spikes] == OUTLIER).all()
    gaps = interpolate_gaps(
        hampel.keypoints, hampel.reason, seq.t_sec
    )  # OUTLIER is not in never_fill: a hole to bridge
    assert np.array_equal(gaps.interpolated, spikes)
    assert (gaps.reason[spikes] == OUTLIER).all()  # a bridged cell still says what made the hole
    error = np.linalg.norm(gaps.keypoints[spikes].astype(np.float64) - seq.kp_true[spikes], axis=-1)
    assert error.max() <= TOLERANCE_PX, error.max()
    assert np.array_equal(gaps.keypoints[~spikes], seq.kp[~spikes])  # the rest of the movement is untouched
    assert len(gaps.gaps) == 4 and set(gaps.gaps.outcome.tolist()) == {FILLED}  # four gaps, the last of two rows


def test_t_qlt_06k_the_hole_of_a_spike_is_the_only_thing_hampel_leaves_and_the_inputs_are_not_touched():
    seq, kp, spikes = spiked_sequence()
    mask = apply_mask(kp, seq.score)
    before = (mask.keypoints.copy(), mask.reason.copy())
    hampel = hampel_outliers(mask.keypoints, mask.reason, seq.t_sec)
    assert np.array_equal(mask.keypoints, before[0]) and np.array_equal(mask.reason, before[1])
    assert hampel.reason.max() == OUTLIER and np.array_equal(hampel.reason != mask.reason, spikes)
    assert np.isnan(hampel.keypoints).sum() == 2 * spikes.sum()  # both coordinates of each flagged cell, nothing else


def test_t_qlt_06k_with_noise_every_spike_is_still_found_and_the_rule_as_written_flags_good_cells_too():
    """The W6 values (no floor) on 1 px of noise: the five spikes are found, and a few percent of the other cells are
    flagged as well (the small-sample MAD, T-QLT-06m); this is the cost that the floor of the defaults removes
    (DEC-0046)."""
    seq, kp, spikes = spiked_sequence(noise_px=1.0)
    mask = apply_mask(kp, seq.score)
    r = hampel_outliers(mask.keypoints, mask.reason, seq.t_sec, HampelParams(scale_floor_px=0.0))
    assert r.outlier[spikes].all()
    false_rate = r.outlier[~spikes].sum() / r.judged[~spikes].sum()
    assert 0.02 < false_rate < 0.15, false_rate


def test_t_qlt_06k_the_defaults_remove_the_false_flags_on_noise_and_keep_the_spikes():
    seq, kp, spikes = spiked_sequence(noise_px=1.0)
    mask = apply_mask(kp, seq.score)
    r = hampel_outliers(mask.keypoints, mask.reason, seq.t_sec)  # the floor is 2 px
    assert np.array_equal(r.outlier, spikes)


# --- T-QLT-06l: the target of P3.06 ---------------------------------------------------------------------------------
SPIKE_FRAME = 120


def scene():
    """The performer appears at frame 10 and is away from frame 40 to 99. Returns the track as the tracker made it and a
    copy in which the left wrist jumps by 80 px for one frame: the person stands, so every window is constant."""
    run = resolve(
        {0: stands(HOME_X, first=10, absent=[(40, 100)]), 1: stands(1500)},
        160,
        at_t_sec=20 / FPS,
        segment_start_pos=5,
    )
    kp = run.target.keypoints.copy()
    kp[SPIKE_FRAME, IDX["LWrist"]] += 80.0
    return run.target, dataclasses.replace(run.target, keypoints=kp)


def test_t_qlt_06l_the_spike_in_the_take_is_flagged_and_the_loss_of_the_target_is_not_touched():
    original, tt = scene()
    masked = mask_track(tt)
    r = hampel_track(masked)
    wrist = IDX["LWrist"]
    assert np.array_equal(np.argwhere(r.outlier), [[SPIKE_FRAME, wrist]])
    assert r.reason[SPIKE_FRAME, wrist] == OUTLIER and np.isnan(r.keypoints[SPIKE_FRAME, wrist]).all()
    lost = tt.status != TRACKED
    assert (r.reason[lost] == NOT_TRACKED).all() and not r.judged[lost].any()  # a loss is not judged, not flagged
    tracked_rest = ~lost[:, None] & ~r.outlier
    assert np.array_equal(r.keypoints[tracked_rest], original.keypoints[tracked_rest], equal_nan=True)
    gaps = interpolate_gaps(r.keypoints, r.reason, masked.t_sec)  # and the gap layer repairs it, flagged
    assert np.array_equal(np.argwhere(gaps.interpolated), [[SPIKE_FRAME, wrist]])
    assert np.allclose(gaps.keypoints[SPIKE_FRAME, wrist], original.keypoints[SPIKE_FRAME, wrist], atol=1e-4)


def test_t_qlt_06l_a_window_is_cut_by_the_loss_so_the_cells_next_to_it_are_not_judged():
    _, tt = scene()
    r = hampel_track(mask_track(tt))
    last_before, first_after = 39, 100  # tracked frames at the two ends of the absence (frames 40 to 99)
    assert r.judged[38].all() and not r.judged[last_before].any()  # rows 35 to 39 count, then only 36 to 39
    assert not r.judged[first_after].any() and r.judged[first_after + 1].all()


def test_t_qlt_06l_the_timeline_and_the_margins_are_carried_and_the_wrapper_is_the_array_function():
    _, tt = scene()
    masked = mask_track(tt)
    r = hampel_track(masked)
    assert r.keypoints.shape[0] == len(masked.t_sec) == tt.n_frames  # no frame is cut, the margins stay
    assert np.array_equal(masked.in_segment, tt.in_segment) and not masked.in_segment[:5].any()
    by_hand = hampel_outliers(masked.mask.keypoints, masked.mask.reason, masked.t_sec)
    assert np.array_equal(r.keypoints, by_hand.keypoints, equal_nan=True)
    assert np.array_equal(r.outlier, by_hand.outlier) and np.array_equal(r.reason, by_hand.reason)
    assert np.array_equal(
        masked.mask.keypoints, mask_track(tt).mask.keypoints, equal_nan=True
    )  # the mask was not touched


def test_t_qlt_06l_a_short_loss_of_the_target_leaves_its_neighbours_unjudged_too():
    run = resolve({0: stands(HOME_X, absent=[(40, 43)]), 1: stands(1500)}, 80)  # 3 frames away: 100 ms
    r = hampel_track(mask_track(run.target))
    assert not r.outlier.any() and (r.reason[40:43] == NOT_TRACKED).all()
    # the window of a row next to the loss lacks the rows that count: 39 and 43 keep 4 of 7, 38 and 44 keep 5
    assert not r.judged[40:43].any() and not r.judged[39].any() and not r.judged[43].any()
    assert r.judged[38].all() and r.judged[44].all()
