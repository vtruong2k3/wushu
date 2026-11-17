"""P4.02: the gap layer on SYN-06 and on the target of P3.06 (T-QLT-03e, T-QLT-03f).

The first half feeds the synthetic sequence SYN-06 through the mask and then through ``interpolate_gaps``: its gaps are
known to the frame and to the position (``kp_true``), so what must be bridged, what must stay NaN and how far a bridge
is from the truth are all known. The second half goes through the whole chain of the tracking stage (association, target
choice, target over time) on a scene of boxes, then ``mask_track`` and ``interpolate_track``.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from helpers.synth import make_sequence
from helpers.track_build import FPS, HOME_X, resolve, stands
from taiji_ai.pose.skeleton import IDX
from taiji_ai.quality.gaps import (
    FILLED,
    NEVER_FILL,
    OPEN_END,
    OPEN_START,
    GapParams,
    interpolate_gaps,
    interpolate_track,
)
from taiji_ai.quality.mask import NOT_TRACKED, OK, apply_mask, mask_track
from taiji_ai.track.state import BEFORE_TARGET, LOST, TARGET_LOST, TRACKED

TOLERANCE_PX = 2.0  # the plan's tolerance for a bridge on the smooth motion of SYN-06 (SYN-06, T-QLT-03)

SHORT_AND_LONG = (
    (("LWrist", "RWrist"), 2.0, 0.100),  # short: three frames, a bridge of 133 ms at 30 fps
    (("LKnee", "RAnkle"), 1.0, 0.300),  # long: 300 ms
    (("Nose",), 3.5, 0.050),  # one or two frames
)


def chain(mode: str, gaps=SHORT_AND_LONG, seed: int = 3):
    seq = make_sequence("SYN-06", seed=seed, gap_mode=mode, gaps=gaps)
    mask = apply_mask(seq.kp, seq.score)  # the sequence arrays are read-only: nothing may write into them
    return seq, mask, interpolate_gaps(mask.keypoints, mask.reason, seq.t_sec)


# --- T-QLT-03e: SYN-06 -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["nan", "low_score"])
def test_t_qlt_03e_syn_06_short_gaps_are_bridged_within_2_px_and_long_gaps_stay_nan(mode: str):
    seq, mask, result = chain(mode)
    truth_gaps = seq.truth["gaps"]
    assert {g["kind"] for g in truth_gaps} == {"short", "long"}  # the scene exercises both
    bridged = np.zeros(mask.reason.shape, bool)
    left_nan = np.zeros(mask.reason.shape, bool)
    for gap in truth_gaps:
        first, last = gap["frames"]
        for name in gap["joints"]:
            cells = (slice(first, last + 1), IDX[name])
            if gap["kind"] == "short":
                bridged[cells] = True
                error = np.linalg.norm(result.keypoints[cells].astype(np.float64) - seq.kp_true[cells], axis=-1)
                assert error.max() <= TOLERANCE_PX, (name, error.max())
            else:
                left_nan[cells] = True
    assert np.array_equal(result.interpolated, bridged)  # exactly the short gaps, none more, none fewer
    assert np.isnan(result.keypoints[left_nan]).all() and not result.interpolated[left_nan].any()
    untouched = ~bridged & ~left_nan
    assert np.array_equal(result.keypoints[untouched], seq.kp[untouched])  # every other cell is the input cell
    assert np.array_equal(result.reason, mask.reason)  # the mask's reason stays, also under the bridged cells
    assert (result.reason[bridged] != OK).all()


def test_t_qlt_03e_syn_06_the_table_agrees_with_the_generator_about_which_gaps_are_short():
    seq, _, result = chain("nan")
    want = {
        (IDX[name], *gap["frames"]): "filled" if gap["kind"] == "short" else "too_long"
        for gap in seq.truth["gaps"]
        for name in gap["joints"]
    }
    g = result.gaps
    names = ("filled", "too_long")
    got = {
        (int(j), int(s), int(e)): names[int(o)] for j, s, e, o in zip(g.joint, g.start, g.end, g.outcome, strict=True)
    }
    assert got == want  # the generator's bridged span and this module's rule are the same definition
    for gap in seq.truth["gaps"]:  # and the lengths in the table are the generator's own
        for name in gap["joints"]:
            row = int(np.flatnonzero((g.joint == IDX[name]) & (g.start == gap["frames"][0]))[0])
            assert g.bridge_s[row] == pytest.approx(gap["bridge_s"]) and g.missing_s[row] == pytest.approx(
                gap["missing_s"]
            )


def test_t_qlt_03e_syn_06_gaps_at_the_ends_of_the_clip_cannot_be_bridged():
    probe = make_sequence("SYN-06", seed=3)
    last_start = float(probe.t_sec[-1]) - 0.1
    gaps = ((("LWrist",), 0.0, 0.2), (("RWrist",), last_start, 0.5))
    seq = make_sequence("SYN-06", seed=3, gaps=gaps)
    assert [g["kind"] for g in seq.truth["gaps"]] == ["unbridgeable"] * 2
    mask = apply_mask(seq.kp, seq.score)
    result = interpolate_gaps(mask.keypoints, mask.reason, seq.t_sec)
    assert not result.interpolated.any()
    assert np.isnan(result.keypoints[: seq.truth["gaps"][0]["frames"][1] + 1, IDX["LWrist"]]).all()
    assert np.isnan(result.keypoints[seq.truth["gaps"][1]["frames"][0] :, IDX["RWrist"]]).all()
    g = result.gaps
    outcomes = {(int(j), int(s)): int(o) for j, s, o in zip(g.joint, g.start, g.outcome, strict=True)}
    assert outcomes[(IDX["LWrist"], 0)] == OPEN_START
    assert outcomes[(IDX["RWrist"], seq.truth["gaps"][1]["frames"][0])] == OPEN_END


def test_t_qlt_03e_syn_06_the_limit_of_the_generator_and_the_parameter_move_together():
    gaps = ((("LWrist",), 2.0, 0.200),)  # 6 missing frames at 30 fps: a bridge of 233 ms
    seq = make_sequence("SYN-06", seed=3, gaps=gaps, short_gap_s=0.300)
    assert seq.truth["gaps"][0]["kind"] == "short"  # short for a limit of 300 ms
    mask = apply_mask(seq.kp, seq.score)
    default = interpolate_gaps(mask.keypoints, mask.reason, seq.t_sec)
    wide = interpolate_gaps(mask.keypoints, mask.reason, seq.t_sec, GapParams(max_gap_s=0.300))
    first, last = seq.truth["gaps"][0]["frames"]
    assert not default.interpolated.any() and wide.interpolated.sum() == last - first + 1
    cells = (slice(first, last + 1), IDX["LWrist"])
    assert np.linalg.norm(wide.keypoints[cells].astype(np.float64) - seq.kp_true[cells], axis=-1).max() <= TOLERANCE_PX


# --- T-QLT-03f: the target of P3.06 ---------------------------------------------------------------------------------
# three tracked frames in which one wrist has a low score: a short hole inside the take
LOW_SCORE_FRAMES = slice(120, 123)


def scene():
    """The performer appears at frame 10 and is away from frame 40 to 99; one wrist has a low score at frames 120 to
    122. Returns the track as the tracker made it and a copy with the low scores."""
    run = resolve(
        {0: stands(HOME_X, first=10, absent=[(40, 100)]), 1: stands(1500)},
        160,
        at_t_sec=20 / FPS,
        segment_start_pos=5,
    )
    scores = run.target.scores.copy()
    scores[LOW_SCORE_FRAMES, IDX["LWrist"]] = 0.1
    return run.target, dataclasses.replace(run.target, scores=scores)


def test_t_qlt_03f_a_loss_of_the_target_is_never_bridged_but_a_low_score_inside_the_take_is():
    original, tt = scene()
    for status in (BEFORE_TARGET, LOST, TARGET_LOST, TRACKED):
        assert (tt.status == status).any(), status  # the scene must exercise every status
    masked = mask_track(tt)
    result = interpolate_track(masked)
    not_tracked = tt.status != TRACKED
    assert (masked.mask.reason[not_tracked] == NOT_TRACKED).all()
    assert not result.interpolated[not_tracked].any() and np.isnan(result.keypoints[not_tracked]).all()
    wrist = IDX["LWrist"]
    cells = (LOW_SCORE_FRAMES, wrist)
    # the three cells of the low score and no more; the person stands, so the bridge equals what the model saw
    assert result.interpolated[cells].all() and result.interpolated.sum() == 3
    assert np.allclose(result.keypoints[cells], original.keypoints[cells], atol=1e-4)
    g = result.gaps
    outcomes = {(int(j), int(s), int(e)): int(o) for j, s, e, o in zip(g.joint, g.start, g.end, g.outcome, strict=True)}
    assert outcomes[(wrist, 120, 122)] == FILLED
    lost_from, lost_to = int(np.flatnonzero(tt.status == LOST)[0]), int(np.flatnonzero(tt.status == TARGET_LOST)[-1])
    assert outcomes[(wrist, lost_from, lost_to)] == NEVER_FILL  # the absence, anchored on both sides
    assert outcomes[(wrist, 0, int(np.flatnonzero(tt.status == BEFORE_TARGET)[-1]))] == OPEN_START  # nothing before


def test_t_qlt_03f_a_short_loss_of_the_target_is_not_bridged_even_when_the_clock_would_allow_it():
    # the performer is away for 3 frames (100 ms), a bridge of 133 ms at 30 fps
    run = resolve({0: stands(HOME_X, absent=[(40, 43)]), 1: stands(1500)}, 80)
    tt = run.target
    assert (tt.status[40:43] == LOST).all() and (tt.status[:40] == TRACKED).all() and (tt.status[43:] == TRACKED).all()
    result = interpolate_track(mask_track(tt))
    assert not result.interpolated.any() and np.isnan(result.keypoints[40:43]).all()
    assert set(result.gaps.outcome.tolist()) == {NEVER_FILL}  # every one of the 26 gaps
    assert len(result.gaps) == 26 and result.gaps.bridge_s[0] == pytest.approx(4 / FPS)
    allowed = interpolate_track(mask_track(tt), GapParams(never_fill=()))  # the caller's own choice
    assert allowed.interpolated[40:43].all()


def test_t_qlt_03f_the_timeline_and_the_margins_are_carried_and_the_wrapper_is_the_array_function():
    _, tt = scene()
    masked = mask_track(tt)
    result = interpolate_track(masked)
    assert result.keypoints.shape[0] == len(masked.t_sec) == tt.n_frames  # no frame is cut, the margins stay
    assert np.array_equal(masked.in_segment, tt.in_segment) and not masked.in_segment[:5].any()
    by_hand = interpolate_gaps(masked.mask.keypoints, masked.mask.reason, masked.t_sec)
    assert np.array_equal(result.keypoints, by_hand.keypoints, equal_nan=True)
    assert np.array_equal(result.interpolated, by_hand.interpolated)
    assert np.array_equal(result.gaps.outcome, by_hand.gaps.outcome)
    # the mask that was read has not been touched
    assert np.array_equal(masked.mask.keypoints, mask_track(tt).mask.keypoints, equal_nan=True)
