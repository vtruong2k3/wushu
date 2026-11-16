"""P4.01: the mask on the target of P3.06 and on SYN-06 (T-QLT-01d, T-QLT-02b).

The first half goes through the whole chain of the tracking stage (association, target choice, target over time) on
scenes of boxes and then through ``mask_track``; the second half uses the synthetic sequence SYN-06, whose gaps are
known to the frame, so the cells the mask must remove are known exactly.
"""

from __future__ import annotations

import numpy as np
import pytest

from helpers.synth import make_sequence
from helpers.track_build import FPS, HOME_X, Run, person_box, resolve, stands
from taiji_ai.pose.skeleton import ESSENTIAL, IDX, JOINTS, NUM_JOINTS
from taiji_ai.quality.mask import (
    FRAME_INVALID,
    LOW_CONF,
    NON_FINITE,
    NOT_TRACKED,
    OK,
    MaskParams,
    apply_mask,
    mask_track,
)
from taiji_ai.track.state import BEFORE_TARGET, LOST, TARGET_LOST, TRACKED


def usable_essential(n_valid: int) -> int:
    """How many essential joints score 0.9 when the first ``n_valid`` keypoints of the scene person do."""
    return sum(1 for j in ESSENTIAL if j < n_valid)


def run_with_every_status() -> Run:
    """The performer appears at frame 10, is away from frame 40 to 99 (lost, then target lost) and comes back."""
    return resolve(
        {0: stands(HOME_X, first=10, absent=[(40, 100)]), 1: stands(1500)},
        140,
        at_t_sec=20 / FPS,
        segment_start_pos=5,
    )


# --- T-QLT-01d: the target of P3.06 -----------------------------------------------------------------------------------
def test_t_qlt_01d_only_the_tracked_frames_of_the_target_have_values_and_the_others_are_not_tracked():
    run = run_with_every_status()
    tt = run.target
    for status in (BEFORE_TARGET, LOST, TARGET_LOST, TRACKED):  # the scene must exercise every status
        assert (tt.status == status).any(), status
    before = {name: getattr(tt, name).copy() for name in ("keypoints", "scores", "status", "t_sec", "frame_index")}

    masked = mask_track(tt)

    tracked = tt.status == TRACKED
    mask = masked.mask
    assert (mask.reason[~tracked] == NOT_TRACKED).all() and np.isnan(mask.keypoints[~tracked]).all()
    assert (mask.reason[tracked] == OK).all()  # the scene person scores 0.9 everywhere
    assert np.array_equal(mask.keypoints[tracked], tt.keypoints[tracked])
    assert np.array_equal(mask.tracked, tracked) and np.array_equal(mask.usable, tracked)
    assert not mask.frame_invalid.any()  # absent frames are not invalid frames
    assert np.array_equal(mask.scores, tt.scores, equal_nan=True)
    for name, value in before.items():  # the raw layer of the track was not touched
        assert np.array_equal(getattr(tt, name), value, equal_nan=True), name


def test_t_qlt_01d_the_timeline_of_the_track_is_carried_unchanged_and_the_margins_stay():
    run = run_with_every_status()
    tt = run.target
    masked = mask_track(tt)
    for name in ("frame_index", "t_sec", "in_segment", "status"):
        assert np.array_equal(getattr(masked, name), getattr(tt, name)), name
        assert not getattr(masked, name).flags.writeable, name
    assert len(masked.t_sec) == len(tt.t_sec) == masked.mask.keypoints.shape[0]  # no frame is cut
    assert not tt.in_segment[:5].any() and tt.in_segment[5:].all()  # the margin frames are in the result too


def test_t_qlt_01d_the_parameters_reach_the_mask():
    run = resolve({0: stands(HOME_X), 1: stands(1500)}, 20)
    strict = mask_track(run.target, MaskParams(tau_kp=0.95))
    assert (strict.mask.reason == LOW_CONF).all() and strict.mask.frame_invalid.all()
    assert strict.mask.params.tau_kp == 0.95


# --- T-QLT-02: the frame rule through the whole chain -----------------------------------------------------------------
@pytest.mark.parametrize("n_valid", [26, 17, 14, 13, 8])
def test_t_qlt_02b_five_essential_joints_of_ten_keep_a_frame_and_four_do_not(n_valid: int):
    n_usable = usable_essential(n_valid)
    run = resolve({0: stands(HOME_X, n_valid=n_valid), 1: stands(1500)}, 20)
    assert (run.target.status == TRACKED).all()  # the person is still followed
    mask = mask_track(run.target).mask
    assert (mask.n_essential_valid == n_usable).all()
    if n_usable >= 5:
        assert not mask.frame_invalid.any()
        assert (mask.reason[:, :n_valid] == OK).all() and (mask.reason[:, n_valid:] == LOW_CONF).all()
        assert np.isfinite(mask.keypoints[:, :n_valid]).all() and np.isnan(mask.keypoints[:, n_valid:]).all()
    else:
        assert mask.frame_invalid.all() and np.isnan(mask.keypoints).all()
        assert (mask.reason[:, n_valid:] == LOW_CONF).all() and (mask.reason[:, :n_valid] == FRAME_INVALID).all()


def test_t_qlt_02b_the_boundary_values_are_where_the_plan_says():
    assert [usable_essential(n) for n in (26, 17, 14, 13, 8)] == [10, 8, 5, 4, 2]  # 14 is valid, 13 is not


def test_t_qlt_02b_a_run_of_poor_frames_in_the_middle_of_a_take_is_invalid_and_the_rest_is_not():
    def path(k: int):
        return person_box(HOME_X), (13 if 30 <= k < 40 else 26)

    run = resolve({0: path, 1: stands(1500)}, 70)
    assert (run.target.status == TRACKED).all()
    mask = mask_track(run.target).mask
    assert mask.frame_invalid.tolist() == [30 <= k < 40 for k in range(70)]
    assert np.isnan(mask.keypoints[30:40]).all() and np.isfinite(mask.keypoints[:30]).all()
    assert np.isfinite(mask.keypoints[40:, :]).all()
    assert np.array_equal(mask.usable, ~mask.frame_invalid)


# --- T-QLT-02b: SYN-06, gaps known to the frame -----------------------------------------------------------------------
def gap_cells(truth_gaps, n_frames: int) -> np.ndarray:
    expected = np.zeros((n_frames, NUM_JOINTS), bool)
    for gap in truth_gaps:
        i0, i1 = gap["frames"]
        for joint in gap["joints"]:
            expected[i0 : i1 + 1, IDX[joint]] = True
    return expected


SHORT_AND_LONG = (
    (("LWrist", "RWrist"), 2.0, 0.100),  # short, not essential
    (("LKnee", "RAnkle"), 1.0, 0.300),  # long, essential joints (two of ten: the frames stay valid)
    (("Nose",), 3.5, 0.050),  # a single frame or two
)


@pytest.mark.parametrize("mode", ["low_score", "nan"])
def test_t_qlt_02b_syn_06_the_removed_cells_are_exactly_the_gaps(mode: str):
    seq = make_sequence("SYN-06", seed=3, gap_mode=mode, gaps=SHORT_AND_LONG)
    expected = gap_cells(seq.truth["gaps"], len(seq.t_sec))
    assert expected.any() and not expected.all()

    out = apply_mask(seq.kp, seq.score)  # the sequence arrays are read-only: the mask must not write into them

    assert not out.frame_invalid.any()
    assert np.array_equal(out.reason != OK, expected)  # exactly the cells of the gaps, none more, none fewer
    assert (out.reason[expected] == (LOW_CONF if mode == "low_score" else NON_FINITE)).all()
    assert np.array_equal(out.keypoints[~expected], seq.kp[~expected])  # every other cell is the input cell
    assert np.isnan(out.keypoints[expected]).all()  # nothing was filled from the neighbours
    assert not np.shares_memory(out.keypoints, seq.kp)


def test_t_qlt_02b_syn_06_six_essential_joints_in_a_gap_make_the_gap_frames_invalid_as_a_whole():
    six = tuple(ESSENTIAL[:6])
    names = tuple(JOINTS[j] for j in six)
    seq = make_sequence("SYN-06", seed=4, gap_mode="low_score", gaps=((names, 1.5, 0.200),))
    (gap,) = seq.truth["gaps"]
    i0, i1 = gap["frames"]
    frames = np.zeros(len(seq.t_sec), bool)
    frames[i0 : i1 + 1] = True

    out = apply_mask(seq.kp, seq.score)

    assert np.array_equal(out.frame_invalid, frames)
    assert np.isnan(out.keypoints[frames]).all()  # all 26 joints of the gap frames
    assert (out.reason[frames][:, list(six)] == LOW_CONF).all()  # the joints that failed keep their own reason
    others = [j for j in range(NUM_JOINTS) if j not in six]
    assert (out.reason[frames][:, others] == FRAME_INVALID).all()
    assert (out.reason[~frames] == OK).all() and np.array_equal(out.keypoints[~frames], seq.kp[~frames])
