"""P4.06: the swap flag in the chain of the quality stages (T-QLT-10h, 10i).

The first part runs SYN-08 through mask, the flag, Hampel and the gap layer; the second goes through the tracking stage
(association, target choice, target over time) on a scene of boxes, then ``mask_track`` and ``detect_lr_swaps_track``.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from helpers.synth import make_sequence
from helpers.track_build import FPS, HOME_X, resolve, stands
from taiji_ai.pose.skeleton import IDX, LR_PAIRS
from taiji_ai.quality.filters import hampel_outliers
from taiji_ai.quality.gaps import BLOCKED, FILLED, interpolate_gaps
from taiji_ai.quality.lr_swap import detect_lr_swaps, detect_lr_swaps_track
from taiji_ai.quality.mask import apply_mask, mask_track

SHOULDER_PAIR = LR_PAIRS.index((IDX["LShoulder"], IDX["RShoulder"]))


def outcome_at(gaps, joint: int, start: int) -> int:
    row = np.flatnonzero((gaps.gaps.joint == joint) & (gaps.gaps.start == start))
    assert len(row) == 1, (joint, start)
    return int(gaps.gaps.outcome[row[0]])


# --- T-QLT-10h: SYN-08 with the gap layer and with Hampel -------------------------------------------------------------
def test_t_qlt_10h_a_hole_next_to_a_jump_is_not_bridged_when_the_flag_is_given_as_blocked():
    seq = make_sequence("SYN-08", seed=3, noise_px=0.0)  # swaps in rows 20 to 22 and 50 to 52
    score = np.array(seq.score, copy=True)
    joint = IDX["RShoulder"]
    score[24:26, joint] = 0.1  # a hole of two rows right after the jump back (row 23)
    score[80:82, joint] = 0.1  # the same hole far from any swap
    mask = apply_mask(seq.kp, score)
    swap = detect_lr_swaps(mask.keypoints, mask.reason, seq.t_sec)
    assert swap.blocked[23, joint] and not swap.blocked[79, joint] and not swap.blocked[82, joint]
    plain = interpolate_gaps(mask.keypoints, mask.reason, seq.t_sec)
    assert (
        outcome_at(plain, joint, 24) == FILLED and outcome_at(plain, joint, 80) == FILLED
    )  # without the flag: both bridged
    guarded = interpolate_gaps(mask.keypoints, mask.reason, seq.t_sec, blocked=swap.blocked)
    assert outcome_at(guarded, joint, 24) == BLOCKED  # the anchor is a row where the labels are not to be trusted
    assert outcome_at(guarded, joint, 80) == FILLED  # the hole elsewhere is bridged as before
    assert not guarded.interpolated[24:26, joint].any() and guarded.interpolated[80:82, joint].all()


def test_t_qlt_10h_a_swap_of_one_row_is_seen_on_the_mask_layer_but_not_after_hampel_has_made_it_a_hole():
    seq = make_sequence("SYN-08", seed=3, noise_px=0.0, swap_ranges=((40, 41),))
    mask = apply_mask(seq.kp, seq.score)
    seen = detect_lr_swaps(mask.keypoints, mask.reason, seq.t_sec)
    assert np.flatnonzero(seen.events.any(axis=1)).tolist() == [40, 41] and np.flatnonzero(
        seen.frame_suspect
    ).tolist() == [40]
    hampel = hampel_outliers(mask.keypoints, mask.reason, seq.t_sec)
    assert hampel.outlier[40].any()  # the swapped labels of that row are spikes: outliers, now NaN
    after = detect_lr_swaps(hampel.keypoints, hampel.reason, seq.t_sec)
    assert not after.events.any() and not after.suspect.any()  # a swap that was repaired by accident would be invisible


def test_t_qlt_10h_nothing_of_the_mask_layer_is_changed_by_the_flag():
    seq = make_sequence("SYN-08", seed=4, noise_px=1.0)
    mask = apply_mask(seq.kp, seq.score)
    before = (mask.keypoints.copy(), mask.reason.copy(), np.array(seq.t_sec, copy=True))
    detect_lr_swaps(mask.keypoints, mask.reason, seq.t_sec)
    assert np.array_equal(mask.keypoints, before[0], equal_nan=True) and np.array_equal(mask.reason, before[1])
    assert np.array_equal(seq.t_sec, before[2])


# --- T-QLT-10i: the chain with the tracker ----------------------------------------------------------------------------
def scene():
    """The performer appears at frame 10 and is away from frame 40 to 99; the margins of the segment are kept."""
    return resolve(
        {0: stands(HOME_X, first=10, absent=[(40, 100)]), 1: stands(1500)},
        160,
        at_t_sec=20 / FPS,
        segment_start_pos=5,
    )


def test_t_qlt_10i_a_track_without_a_swap_has_no_event_and_the_loss_of_the_target_is_not_one():
    run = scene()
    masked = mask_track(run.target)
    r = detect_lr_swaps_track(masked)
    assert r.events.shape == (run.target.n_frames, len(LR_PAIRS)) and np.isfinite(r.torso_px)
    assert not r.events.any() and not r.suspect.any() and not r.blocked.any() and len(r.table) == 0
    lost = ~masked.mask.tracked
    assert lost.any() and not r.events[lost].any()  # the rows of an absence are not observed: nothing is judged there


def test_t_qlt_10i_a_swap_put_into_the_take_is_found_on_both_sides_of_the_absence_and_not_across_it():
    run = scene()
    kp = run.target.keypoints.copy()
    left, right = IDX["LAnkle"], IDX["RAnkle"]
    tracked = run.target.status == 0
    rows = np.flatnonzero(tracked)
    first, second = int(rows[rows < 40][5]), int(rows[rows >= 100][5])  # one swap before the absence, one after it
    torso = float(np.linalg.norm((kp[first, 5] + kp[first, 6]) / 2 - (kp[first, 11] + kp[first, 12]) / 2))
    assert (
        np.linalg.norm(kp[first, left] - kp[first, right]) >= 0.3 * torso
    )  # the ankles of the scene are far enough apart
    for start in (first, second):
        for row in range(start, start + 3):
            kp[row, [left, right]] = kp[row, [right, left]]
    swapped = dataclasses.replace(run.target, keypoints=kp)
    masked = mask_track(swapped)
    r = detect_lr_swaps_track(masked)
    pair = LR_PAIRS.index((left, right))
    assert np.flatnonzero(r.events[:, pair]).tolist() == [first, first + 3, second, second + 3]
    assert np.flatnonzero(r.suspect[:, left]).tolist() == [*range(first, first + 3), *range(second, second + 3)]
    assert np.array_equal(r.suspect[:, left], r.suspect[:, right])
