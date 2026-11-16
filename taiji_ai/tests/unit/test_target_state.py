"""P3.06: the target over time: tracked, lost, target_lost, re-attached or refused (T-TRK-04, T-TRK-05).

People are boxes on explicit paths (``helpers/track_build.py``) or the SYN-12 scene; no video and no model. Frame ``k``
is at ``k / 30`` s. With the defaults (``max_lost_s = 0.5``) a performer last seen at frame 29 is ``lost`` until frame
44 (``t - t_last = 0.5``) and ``target_lost`` from frame 45.
"""

from __future__ import annotations

import copy
import dataclasses

import numpy as np
import pytest

from helpers.pose_raw_build import box, pose_raw_from_scene, scene_from_paths
from helpers.synth import SynthScene, expected_target_lost, make_scene
from helpers.track_build import BOX_CY, BOX_H, BOX_W, FPS, HOME_X, Run, person_box, resolve, stands, walks
from taiji_ai.pose.runner import PoseRaw
from taiji_ai.track.associate import AssociationParams, associate_tracks, person_cost, track_of_person
from taiji_ai.track.state import (
    BEFORE_TARGET,
    LOST,
    STATUS_NAMES,
    TARGET_LOST,
    TRACKED,
    TargetStateError,
    TargetStateParams,
    resolve_target,
)
from taiji_ai.track.target import select_target

STRANGER_X = 400.0  # far from the performer's home: costs well above the threshold


def kinds(run: Run) -> list[str]:
    return [e.kind for e in run.target.meta.events]


def row_of(run: Run, ident: int, k: int) -> int:
    lo, hi = int(run.raw.person_offsets[k]), int(run.raw.person_offsets[k + 1])
    rows = [r for r in range(lo, hi) if run.ids[r] == ident]
    assert len(rows) == 1
    return rows[0]


def syn_run(seed: int, **params) -> tuple[SynthScene, Run]:
    scene = make_scene("SYN-12", seed=seed, noise_px=2.0, **params)
    raw, ids = pose_raw_from_scene(scene)
    tracks = associate_tracks(raw)
    row = next(r for r in range(int(raw.person_offsets[0]), int(raw.person_offsets[1])) if ids[r] == 0)
    selection = select_target(raw, bbox=tuple(float(v) for v in raw.bboxes[row]))
    return scene, Run(raw, ids, tracks, selection, resolve_target(raw, tracks, selection))


# --- T-TRK-04a: tracked, lost, target_lost ----------------------------------------------------------------------------
def test_t_trk_04a_a_target_gone_for_1_s_is_tracked_then_lost_then_target_lost_and_comes_back():
    run = resolve({0: stands(HOME_X, absent=[(30, 60)]), 1: stands(1500)}, 100)
    tt = run.target
    assert (tt.status[:30] == TRACKED).all()
    assert (tt.status[30:45] == LOST).all()
    assert (tt.status[45:60] == TARGET_LOST).all()
    assert (tt.status[60:] == TRACKED).all()
    gone = slice(30, 60)
    assert np.isnan(tt.keypoints[gone]).all() and np.isnan(tt.scores[gone]).all()
    assert (tt.person_row[gone] == -1).all() and (tt.track_id[gone] == -1).all()
    assert np.isnan(tt.match_cost[gone]).all() and np.isnan(tt.match_margin[gone]).all()
    tracked = tt.status == TRACKED
    assert np.array_equal(tt.keypoints[tracked], run.raw.keypoints[tt.person_row[tracked]])
    assert np.array_equal(tt.scores[tracked], run.raw.scores[tt.person_row[tracked]])
    assert np.array_equal(tt.match_cost[tracked], run.tracks.match_cost[tt.person_row[tracked]], equal_nan=True)
    assert (tt.track_id[tracked] == run.tracks.track_id[tt.person_row[tracked]]).all()


def test_t_trk_04a_the_boundary_between_lost_and_target_lost_is_inclusive_and_follows_max_lost_s():
    paths = {0: stands(HOME_X, absent=[(30, 60)]), 1: stands(1500)}
    one_second = resolve(paths, 100, params=TargetStateParams(max_lost_s=1.0))  # (59 - 29) / 30 = 1.0
    assert (one_second.target.status[30:60] == LOST).all()
    none = resolve(paths, 100, params=TargetStateParams(max_lost_s=0.0))
    assert (none.target.status[30:60] == TARGET_LOST).all()
    assert (none.target.status[60:] == TRACKED).all()


@pytest.mark.parametrize("seed", range(10))
def test_t_trk_04a_syn_12_the_target_lost_interval_is_the_expected_one_within_one_frame(seed: int):
    scene, run = syn_run(seed)
    tt = run.target
    ((e0, e1),) = expected_target_lost(scene, 0.5)
    lost_pos = np.flatnonzero(tt.status == TARGET_LOST)
    assert lost_pos.size and (np.diff(lost_pos) == 1).all()
    dt = 1.0 / FPS
    assert abs(tt.t_sec[lost_pos[0]] - e0) <= dt + 1e-9
    assert abs(tt.t_sec[lost_pos[-1]] + dt - e1) <= dt + 1e-9
    assert (tt.status[lost_pos[-1] + 1 :] == TRACKED).all()  # re-attached at the return
    assert np.isnan(tt.keypoints[tt.status != TRACKED]).all()


def test_t_trk_04a_the_lost_time_is_the_real_time_not_a_count_of_frames():
    # 30 frames at 30 fps, then 4 frames one every 0.25 s (the performer is away), then 30 fps again: by the count of
    # frames the absence is 4 frames, by the clock it is 1.0 s.
    raw, _ = scene_from_paths({0: stands(HOME_X, absent=[(30, 34)]), 1: stands(1500)}, n_frames=40, fps=FPS)
    t_gap = 29 / FPS + 0.25 * np.arange(1, 5)
    t = np.concatenate([np.arange(30) / FPS, t_gap, t_gap[-1] + np.arange(1, 7) / FPS])
    raw = dataclasses.replace(raw, t_sec=t, segment_s=(float(t[0]), float(t[-1])))
    tracks = associate_tracks(raw)
    selection = select_target(raw, bbox=person_box(HOME_X))
    tt = resolve_target(raw, tracks, selection)
    # t - t_last: 0.25 (lost), 0.50 (lost), 0.75 and 1.00 (target_lost); frame 34 is back
    assert list(tt.status[30:34]) == [LOST, LOST, TARGET_LOST, TARGET_LOST]
    assert (tt.status[34:] == TRACKED).all()


# --- T-TRK-04b: no jump to another person ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed", range(10))
def test_t_trk_04b_syn_12_no_frame_of_the_target_is_given_to_another_person(seed: int):
    _, run = syn_run(seed)
    assert (run.identities_of_tracked() == 0).all()


def test_t_trk_04b_a_stranger_who_enters_far_away_is_refused_and_nothing_is_guessed():
    run = resolve({0: stands(HOME_X, last=30), 1: stands(1500), 2: stands(STRANGER_X, first=50)}, 120)
    tt = run.target
    assert person_cost(run.raw, row_of(run, 0, 29), row_of(run, 2, 50)) > TargetStateParams().reattach_cost
    assert (tt.status[:30] == TRACKED).all()
    assert (tt.status[30:45] == LOST).all() and (tt.status[45:] == TARGET_LOST).all()
    assert (tt.person_row[30:] == -1).all() and np.isnan(tt.keypoints[30:]).all()
    assert kinds(run) == ["lost", "target_lost", "refused"]
    refused = tt.meta.events[-1]
    assert refused.frame_pos == 50 and refused.reason == "over_threshold"
    assert refused.track_id == track_of_person(run.tracks, row_of(run, 2, 50))
    assert refused.cost is not None and refused.cost > TargetStateParams().reattach_cost
    assert tt.meta.needs_reselect and tt.meta.reselect_reason == "reattach_refused"
    assert tt.meta.counts.n_refused == 1 and tt.meta.counts.n_reattached == 0


def test_t_trk_04b_two_newcomers_close_in_cost_are_ambiguous_nobody_is_chosen():
    run = resolve(
        {
            0: stands(HOME_X, last=30),
            1: stands(1500),
            2: stands(HOME_X - 30, first=50),
            3: stands(HOME_X + 30, first=50),
        },
        120,
    )
    tt = run.target
    last = row_of(run, 0, 29)
    c2, c3 = person_cost(run.raw, last, row_of(run, 2, 50)), person_cost(run.raw, last, row_of(run, 3, 50))
    limit = TargetStateParams()
    assert max(c2, c3) <= limit.reattach_cost and min(c2, c3) / max(c2, c3) >= limit.ambiguity_ratio  # the premise
    assert (tt.status[45:] == TARGET_LOST).all() and (tt.person_row[30:] == -1).all()
    assert kinds(run) == ["lost", "target_lost", "ambiguous"]
    assert tt.meta.events[-1].frame_pos == 50 and tt.meta.events[-1].reason is None
    assert tt.meta.needs_reselect and tt.meta.reselect_reason == "reattach_ambiguous"
    assert tt.meta.counts.n_ambiguous == 1


def test_t_trk_04b_two_identical_newcomers_with_cost_zero_are_ambiguous():
    run = resolve(
        {0: stands(HOME_X, last=30), 1: stands(1500), 2: stands(HOME_X, first=50), 3: stands(HOME_X, first=50)}, 100
    )
    last = row_of(run, 0, 29)
    assert person_cost(run.raw, last, row_of(run, 2, 50)) == 0.0  # the premise: 0 / 0 is not a ratio
    assert kinds(run)[-1] == "ambiguous" and run.target.meta.reselect_reason == "reattach_ambiguous"
    assert (run.target.status[50:] == TARGET_LOST).all()


# --- T-TRK-04c: short absences ----------------------------------------------------------------------------------------
def test_t_trk_04c_an_absence_of_0_3_s_is_only_lost_and_the_return_is_reattached():
    run = resolve({0: stands(HOME_X, absent=[(30, 39)]), 1: stands(1500)}, 80)
    tt = run.target
    assert (tt.status[30:39] == LOST).all() and not (tt.status == TARGET_LOST).any()
    assert tt.status[39] == TRACKED and tt.track_id[39] != tt.track_id[29]  # 0.3 s > 0.1 s: a new track
    assert np.isfinite(tt.reattach_cost[39]) and tt.reattach_cost[39] <= TargetStateParams().reattach_cost
    assert np.isnan(np.delete(tt.reattach_cost, 39)).all()
    assert kinds(run) == ["lost", "reattached"]
    assert tt.meta.events[1].frame_pos == 39 and tt.meta.events[1].track_id == tt.track_id[39]
    assert not tt.meta.needs_reselect and tt.meta.reselect_reason is None


def test_t_trk_04c_a_gap_up_to_the_association_gap_keeps_the_track_and_is_only_recovered():
    run = resolve({0: stands(HOME_X, absent=[(30, 32)]), 1: stands(1500)}, 80)
    tt = run.target
    assert (tt.status[30:32] == LOST).all() and tt.status[32] == TRACKED
    assert tt.track_id[32] == tt.track_id[29]
    assert np.isnan(tt.reattach_cost).all()
    assert kinds(run) == ["lost", "recovered"]
    assert not tt.meta.needs_reselect


# --- T-TRK-05a: a return within the threshold -----------------------------------------------------------------------
@pytest.mark.parametrize("offset", [0.0, 50.0, 100.0])
@pytest.mark.parametrize("seed", range(5))
def test_t_trk_05a_syn_12_a_return_within_the_threshold_is_reattached(seed: int, offset: float):
    scene, run = syn_run(seed, return_offset_px=offset)
    tt = run.target
    back = int(np.flatnonzero(tt.t_sec >= scene.truth["absent_intervals"][0][1] - 1e-9)[0])
    assert (tt.status[back:] == TRACKED).all()
    assert (run.identities_of_tracked() == 0).all()
    assert tt.track_id[back] != tt.track_id[back - 1 - int(np.flatnonzero(tt.status[:back][::-1] == TRACKED)[0])]
    assert np.isfinite(tt.reattach_cost[back]) and tt.reattach_cost[back] <= TargetStateParams().reattach_cost
    assert kinds(run) == ["lost", "target_lost", "reattached"]
    assert not tt.meta.needs_reselect and tt.meta.reselect_reason is None
    assert tt.meta.counts.n_reattached == 1


def test_t_trk_05a_the_cost_is_against_the_last_pose_of_the_target_not_the_first():
    # the performer walks from x = 900 to x = 1400, stands there, leaves at frame 70 and comes back to x = 1400
    walking = walks(HOME_X, 1400.0, 0, 60)

    def performer(k: int):
        return None if 70 <= k < 120 else walking(k)

    run = resolve({0: performer, 1: stands(300)}, 160)
    tt = run.target
    assert tt.status[120] == TRACKED and tt.reattach_cost[120] < 0.1
    assert kinds(run) == ["lost", "target_lost", "reattached"]


# --- T-TRK-05b: a return outside the threshold ----------------------------------------------------------------------
@pytest.mark.parametrize("offset", [150.0, 200.0, 300.0])
@pytest.mark.parametrize("seed", range(5))
def test_t_trk_05b_syn_12_a_return_outside_the_threshold_is_refused_and_the_user_is_asked(seed: int, offset: float):
    scene, run = syn_run(seed, return_offset_px=offset)
    tt = run.target
    back = int(np.flatnonzero(tt.t_sec >= scene.truth["absent_intervals"][0][1] - 1e-9)[0])
    assert (tt.status[back:] == TARGET_LOST).all()
    assert (tt.person_row[back:] == -1).all() and np.isnan(tt.keypoints[back:]).all()
    assert kinds(run) == ["lost", "target_lost", "refused"]
    assert tt.meta.events[-1].reason == "over_threshold" and tt.meta.events[-1].frame_pos == back
    assert tt.meta.needs_reselect and tt.meta.reselect_reason == "reattach_refused"
    assert np.isnan(tt.reattach_cost).all()


# --- T-TRK-05c: late returns, the better of two ---------------------------------------------------------------------
def test_t_trk_05c_the_time_limit_for_a_return_is_max_reattach_s_inclusive():
    # last seen at frame 29; a return at frame k is t - t_last = (k - 29) / 30 s after
    on_time = resolve({0: stands(HOME_X, absent=[(30, 179)]), 1: stands(1500)}, 260)  # exactly 5.0 s
    assert on_time.target.status[179] == TRACKED and not on_time.target.meta.needs_reselect
    late = resolve({0: stands(HOME_X, absent=[(30, 180)]), 1: stands(1500)}, 260)  # 5.033 s
    assert (late.target.status[180:] == TARGET_LOST).all()
    assert late.target.meta.events[-1].kind == "refused" and late.target.meta.events[-1].reason == "too_late"
    assert late.target.meta.reselect_reason == "reattach_refused"
    longer = resolve(
        {0: stands(HOME_X, absent=[(30, 180)]), 1: stands(1500)}, 260, params=TargetStateParams(max_reattach_s=6.0)
    )
    assert longer.target.status[180] == TRACKED


def test_t_trk_05c_the_threshold_is_inclusive_and_follows_the_parameter():
    shifted = {0: stands(HOME_X, last=30), 1: stands(1500), 2: stands(HOME_X + 60, first=60)}
    probe = resolve(shifted, 100)
    c = person_cost(probe.raw, row_of(probe, 0, 29), row_of(probe, 2, 60))
    assert 0.0 < c < TargetStateParams().reattach_cost
    exactly = resolve(shifted, 100, params=TargetStateParams(reattach_cost=c))
    assert exactly.target.status[60] == TRACKED  # at the threshold: allowed
    just_under = resolve(shifted, 100, params=TargetStateParams(reattach_cost=c - 1e-6))
    assert just_under.target.status[60] == TARGET_LOST and just_under.target.meta.events[-1].kind == "refused"


def test_t_trk_05c_of_two_candidates_the_clearly_better_one_is_chosen():
    run = resolve(
        {0: stands(HOME_X, last=30), 1: stands(1500), 2: stands(HOME_X, first=60), 3: stands(HOME_X + 40, first=60)},
        100,
    )
    last = row_of(run, 0, 29)
    best, other = person_cost(run.raw, last, row_of(run, 2, 60)), person_cost(run.raw, last, row_of(run, 3, 60))
    limit = TargetStateParams()
    assert other <= limit.reattach_cost and best / other < limit.ambiguity_ratio  # the premise
    assert run.target.status[60] == TRACKED and run.ids[run.target.person_row[60]] == 2
    assert (run.identities_of_tracked()[30:] == 2).all()
    assert kinds(run) == ["lost", "target_lost", "reattached"]


def test_t_trk_05c_the_performer_comes_back_together_with_a_stranger_and_gets_his_own_frames():
    run = resolve({0: stands(HOME_X, absent=[(30, 60)]), 1: stands(1500), 2: stands(STRANGER_X, first=60)}, 100)
    assert (run.identities_of_tracked() == 0).all()
    assert run.target.status[60] == TRACKED
    assert kinds(run) == ["lost", "target_lost", "reattached"]  # no refusal is logged when a candidate was taken


# --- T-TRK-05d: only a track that starts after the loss -------------------------------------------------------------
def test_t_trk_05d_a_person_who_was_already_there_and_walks_to_the_performers_place_is_not_a_candidate():
    run = resolve({0: stands(HOME_X, last=30), 1: walks(1500.0, HOME_X, 30, 60)}, 120)
    tt = run.target
    assert (
        person_cost(run.raw, row_of(run, 0, 29), row_of(run, 1, 90)) < TargetStateParams().reattach_cost
    )  # the premise
    assert (tt.status[:30] == TRACKED).all() and (tt.status[45:] == TARGET_LOST).all()
    assert (tt.person_row[30:] == -1).all()
    assert kinds(run) == ["lost", "target_lost"]
    assert tt.meta.needs_reselect and tt.meta.reselect_reason == "target_lost_at_end"


def test_t_trk_05d_a_track_that_starts_while_the_target_is_still_there_is_not_evaluated():
    run = resolve({0: stands(HOME_X), 1: stands(1500), 2: stands(STRANGER_X, first=40)}, 100)
    assert (run.target.status == TRACKED).all() and kinds(run) == []


# --- T-TRK-05e: several losses --------------------------------------------------------------------------------------
def test_t_trk_05e_two_losses_and_two_returns_are_both_handled_and_counted():
    run = resolve({0: stands(HOME_X, absent=[(30, 50), (80, 120)]), 1: stands(1500)}, 160)
    tt = run.target
    assert (tt.status[30:45] == LOST).all() and (tt.status[45:50] == TARGET_LOST).all()
    assert (tt.status[80:95] == LOST).all() and (tt.status[95:120] == TARGET_LOST).all()
    assert kinds(run) == ["lost", "target_lost", "reattached", "lost", "target_lost", "reattached"]
    assert [e.frame_pos for e in tt.meta.events] == [30, 45, 50, 80, 95, 120]
    c = tt.meta.counts
    assert (c.n_frames, c.n_tracked, c.n_lost, c.n_target_lost, c.n_before_target) == (160, 100, 30, 30, 0)
    assert c.n_reattached == 2 and c.n_refused == 0 and c.n_ambiguous == 0
    assert c.n_tracked + c.n_lost + c.n_target_lost + c.n_before_target == c.n_frames
    assert len(set(tt.track_id[tt.status == TRACKED])) == 3  # three tracks of the same performer
    assert not tt.meta.needs_reselect


def test_t_trk_05e_a_refusal_that_is_followed_by_the_real_return_does_not_ask_the_user():
    run = resolve({0: stands(HOME_X, absent=[(30, 100)]), 1: stands(1500), 2: stands(STRANGER_X, first=60)}, 140)
    assert kinds(run) == ["lost", "target_lost", "refused", "reattached"]
    assert run.target.status[100] == TRACKED and not run.target.meta.needs_reselect
    assert run.target.meta.counts.n_refused == 1 and run.target.meta.counts.n_reattached == 1


def test_t_trk_05e_a_clip_that_ends_while_the_target_is_lost_for_a_short_time_does_not_ask_the_user():
    run = resolve({0: stands(HOME_X, last=80), 1: stands(1500)}, 90)  # last seen at 79, 10 frames lost
    assert run.target.status[-1] == LOST and not run.target.meta.needs_reselect


# --- T-TRK-05f: the selection frame, the start of the track, the segment --------------------------------------------
def test_t_trk_05f_frames_before_the_track_exists_are_before_target():
    run = resolve({0: stands(HOME_X, first=20), 1: stands(1500)}, 80, at_t_sec=40 / FPS)
    tt = run.target
    assert (tt.status[:20] == BEFORE_TARGET).all() and (tt.status[20:] == TRACKED).all()
    assert (tt.track_id[:20] == -1).all() and np.isnan(tt.keypoints[:20]).all()
    assert tt.meta.counts.n_before_target == 20
    assert not tt.meta.needs_reselect


def test_t_trk_05f_frames_before_the_selection_frame_come_from_the_same_track():
    run = resolve({0: stands(HOME_X), 1: stands(1500)}, 80, at_t_sec=40 / FPS)
    tt = run.target
    assert run.selection.frame_pos == 40
    assert (tt.status == TRACKED).all() and len(set(tt.track_id)) == 1
    assert (run.identities_of_tracked() == 0).all()
    assert tt.meta.selection.frame_pos == 40 and tt.meta.selection.method == "user_box"


def test_t_trk_05f_one_row_per_frame_with_the_segment_marked_and_the_margins_kept():
    run = resolve({0: stands(HOME_X), 1: stands(1500)}, 100, segment_start_pos=10)
    tt = run.target
    assert tt.n_frames == run.raw.n_frames == 100
    assert not tt.in_segment[:10].any() and tt.in_segment[10:].all()
    assert tt.meta.counts.n_in_segment == 90
    assert tt.meta.segment_s == run.raw.segment_s


# --- T-TRK-05h: refusals of the inputs ------------------------------------------------------------------------------
def test_t_trk_05h_a_weak_chosen_person_cannot_be_followed():
    paths = {0: stands(HOME_X, n_valid=3), 1: stands(1500)}
    raw, _ = scene_from_paths(paths, n_frames=60, fps=FPS)
    tracks = associate_tracks(raw)
    selection = select_target(raw, bbox=person_box(HOME_X))
    assert selection.weak and tracks.track_id[selection.person_row] == -1
    with pytest.raises(TargetStateError, match="weak"):
        resolve_target(raw, tracks, selection)


def test_t_trk_05h_a_selection_or_tracks_of_another_pose_raw_are_refused():
    raw_a, _ = scene_from_paths({0: stands(HOME_X), 1: stands(1500)}, n_frames=60, fps=FPS)
    raw_b, _ = scene_from_paths({0: stands(HOME_X), 1: stands(1500)}, n_frames=60, fps=25.0)
    tracks_a, tracks_b = associate_tracks(raw_a), associate_tracks(raw_b)
    selection_a = select_target(raw_a, bbox=person_box(HOME_X), at_t_sec=30 / FPS)  # frame 30: 1.0 s in A, 1.2 s in B
    with pytest.raises(TargetStateError, match="t_sec"):
        resolve_target(raw_b, tracks_b, selection_a)
    with pytest.raises(TargetStateError, match="person_row"):
        resolve_target(raw_b, tracks_b, dataclasses.replace(selection_a, t_sec=float(raw_b.t_sec[30]), person_row=9999))
    raw_c, _ = scene_from_paths({0: stands(HOME_X)}, n_frames=60, fps=FPS)  # one person per frame instead of two
    with pytest.raises(TargetStateError, match="tracks"):
        resolve_target(raw_c, tracks_a, select_target(raw_c, bbox=person_box(HOME_X)))


def test_t_trk_05h_a_frame_position_outside_the_frames_is_refused():
    raw, _ = scene_from_paths({0: stands(HOME_X)}, n_frames=40, fps=FPS)
    tracks = associate_tracks(raw)
    selection = select_target(raw, bbox=person_box(HOME_X))
    for bad in (-1, 40):
        with pytest.raises(TargetStateError, match="frame_pos"):
            resolve_target(raw, tracks, dataclasses.replace(selection, frame_pos=bad))


def test_t_trk_05h_an_ambiguous_default_choice_is_carried_into_needs_reselect():
    raw, _ = scene_from_paths({0: stands(800), 1: stands(1000)}, n_frames=60, fps=FPS)
    tracks = associate_tracks(raw)
    selection = select_target(raw)
    assert selection.ambiguous and selection.method == "default"
    tt = resolve_target(raw, tracks, selection)
    assert (tt.status == TRACKED).all()
    assert tt.meta.needs_reselect and tt.meta.reselect_reason == "default_choice_ambiguous"
    assert tt.meta.selection.ambiguous and tt.meta.selection.method == "default"


def test_t_trk_05h_a_pending_refusal_comes_before_an_ambiguous_default_choice_in_the_reason():
    # the default rule picks the person nearer to the centre (x = 1000, identity 0), who then leaves
    paths = {0: stands(1000, last=30), 1: stands(800), 2: stands(STRANGER_X, first=50)}
    raw, ids = scene_from_paths(paths, n_frames=90, fps=FPS)
    tracks = associate_tracks(raw)
    selection = select_target(raw)
    assert selection.ambiguous and ids[selection.person_row] == 0
    tt = resolve_target(raw, tracks, selection)
    assert tt.meta.reselect_reason == "reattach_refused"


# --- T-TRK-04d: form, determinism, inputs untouched, parameters -----------------------------------------------------
def test_t_trk_04d_the_outputs_have_the_documented_form():
    run = resolve({0: stands(HOME_X, absent=[(30, 60)]), 1: stands(1500)}, 100, segment_start_pos=10)
    tt, raw = run.target, run.raw
    n = 100
    expected = {
        "frame_index": (np.int32, (n,)),
        "t_sec": (np.float64, (n,)),
        "in_segment": (np.bool_, (n,)),
        "status": (np.uint8, (n,)),
        "track_id": (np.int32, (n,)),
        "person_row": (np.int32, (n,)),
        "keypoints": (np.float32, (n, 26, 2)),
        "scores": (np.float32, (n, 26)),
        "match_cost": (np.float32, (n,)),
        "match_margin": (np.float32, (n,)),
        "reattach_cost": (np.float32, (n,)),
    }
    for name, (dtype, shape) in expected.items():
        array = getattr(tt, name)
        assert array.dtype == dtype and array.shape == shape, name
    assert np.array_equal(tt.frame_index, raw.frame_index) and np.array_equal(tt.t_sec, raw.t_sec)
    assert STATUS_NAMES == ("tracked", "lost", "target_lost", "before_target")
    assert (TRACKED, LOST, TARGET_LOST, BEFORE_TARGET) == (0, 1, 2, 3)
    assert set(np.unique(tt.status)) <= {0, 1, 2, 3}
    c = tt.meta.counts
    assert c.n_tracked == int((tt.status == TRACKED).sum()) and c.n_lost == int((tt.status == LOST).sum())
    assert c.n_target_lost == int((tt.status == TARGET_LOST).sum())
    assert tt.meta.recording_id == raw.recording_id and tt.meta.skeleton == "halpe26/1"
    assert tt.meta.image_size == raw.image_size
    assert tt.meta.selection.track_id == track_of_person(run.tracks, run.selection.person_row)
    assert tt.meta.params.reattach_cost == TargetStateParams().reattach_cost
    assert tt.meta.association.max_cost == run.tracks.params.max_cost
    assert tt.meta.events[0].track_id == tt.meta.selection.track_id and tt.meta.events[0].cost is None


def test_t_trk_04d_the_result_is_deterministic_and_the_inputs_are_not_modified():
    paths = {0: stands(HOME_X, absent=[(30, 60)]), 1: stands(1500)}
    run = resolve(paths, 100)
    raw_copy: PoseRaw = copy.deepcopy(run.raw)
    tracks_copy = copy.deepcopy(run.tracks)
    again = resolve_target(run.raw, run.tracks, run.selection)
    assert again.equals(run.target)
    assert run.raw.equals(raw_copy) and run.tracks.equals(tracks_copy)
    assert not again.equals(resolve(paths, 100, params=TargetStateParams(max_lost_s=1.0)).target)


@pytest.mark.parametrize(
    "bad",
    [
        {"max_lost_s": -0.1},
        {"max_lost_s": float("nan")},
        {"reattach_cost": 0.0},
        {"reattach_cost": 1.5},
        {"reattach_cost": float("nan")},
        {"max_reattach_s": float("inf")},
        {"max_reattach_s": 0.2},  # below max_lost_s
        {"ambiguity_ratio": 0.0},
        {"ambiguity_ratio": 1.2},
    ],
)
def test_t_trk_04d_bad_parameters_are_refused(bad: dict):
    with pytest.raises(ValueError):
        TargetStateParams(**bad)


def test_t_trk_04d_the_defaults_are_the_documented_ones():
    p = TargetStateParams()
    assert (p.max_lost_s, p.reattach_cost, p.max_reattach_s, p.ambiguity_ratio) == (0.5, 0.5, 5.0, 0.6)


# --- boundaries and cases found while checking the tests against mutants ---------------------------------------------
def test_t_trk_04b_the_ambiguity_limit_is_inclusive():
    paths = {
        0: stands(HOME_X, last=30),
        1: stands(1500),
        2: stands(HOME_X - 30, first=50),
        3: stands(HOME_X + 45, first=50),
    }
    probe = resolve(paths, 100)
    last = row_of(probe, 0, 29)
    best, second = sorted(person_cost(probe.raw, last, row_of(probe, i, 50)) for i in (2, 3))
    assert 0.0 < best < second <= TargetStateParams().reattach_cost
    ratio = best / second
    at_the_limit = resolve(paths, 100, params=TargetStateParams(ambiguity_ratio=ratio))
    assert at_the_limit.target.meta.events[-1].kind == "ambiguous"
    just_above = resolve(paths, 100, params=TargetStateParams(ambiguity_ratio=min(1.0, ratio + 1e-6)))
    assert just_above.target.meta.events[-1].kind == "reattached" and just_above.target.status[50] == TRACKED


def test_t_trk_05e_a_refusal_during_a_short_gap_is_cleared_when_the_same_track_comes_back():
    run = resolve({0: stands(HOME_X, absent=[(30, 32)]), 1: stands(1500), 2: stands(STRANGER_X, first=31)}, 80)
    assert kinds(run) == ["lost", "refused", "recovered"]
    assert run.target.status[32] == TRACKED and run.target.track_id[32] == run.target.track_id[29]
    assert not run.target.meta.needs_reselect


def test_t_trk_05h_a_selection_with_another_frame_index_is_refused():
    raw, _ = scene_from_paths({0: stands(HOME_X)}, n_frames=40, fps=FPS)
    tracks = associate_tracks(raw)
    selection = select_target(raw, bbox=person_box(HOME_X))
    with pytest.raises(TargetStateError, match="frame_index"):
        resolve_target(raw, tracks, dataclasses.replace(selection, frame_index=selection.frame_index + 1))


def test_t_trk_05c_the_cost_of_a_return_is_measured_against_the_size_of_the_last_pose_of_the_target():
    def smaller(k: int):  # identity 2: half the size of the performer, same centre
        return (box(HOME_X, BOX_CY, BOX_W / 2, BOX_H / 2), 26) if k >= 60 else None

    paths = {0: stands(HOME_X, last=30), 1: stands(1500), 2: smaller}
    probe = resolve(paths, 100)
    last, new = row_of(probe, 0, 29), row_of(probe, 2, 60)
    forward, backward = person_cost(probe.raw, last, new), person_cost(probe.raw, new, last)
    assert 0.0 < forward < backward <= 1.0  # the smaller the reference, the larger the keypoint term
    between = (forward + backward) / 2
    assert resolve(paths, 100, params=TargetStateParams(reattach_cost=between)).target.status[60] == TRACKED
    refused = resolve(paths, 100, params=TargetStateParams(reattach_cost=forward - 1e-6))
    assert refused.target.status[60] == TARGET_LOST


def test_t_trk_05c_the_cost_of_a_return_uses_the_association_parameters_of_the_tracks():
    paths = {0: stands(HOME_X, last=30), 1: stands(1500), 2: stands(HOME_X + 100, first=60)}
    raw, _ = scene_from_paths(paths, n_frames=100, fps=FPS)
    selection = select_target(raw, bbox=person_box(HOME_X))
    default = resolve_target(raw, associate_tracks(raw), selection)
    assert default.status[60] == TRACKED  # IoU term 0.667, keypoint term 0.2: cost 0.43
    iou_only = AssociationParams(w_kp=0.0)  # cost 0.667, above the limit
    custom = resolve_target(raw, associate_tracks(raw, params=iou_only), selection)
    assert custom.status[60] == TARGET_LOST and custom.meta.association.w_kp == 0.0
