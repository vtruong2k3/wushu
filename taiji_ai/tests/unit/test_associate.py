"""T-TRK-02a..d, T-TRK-03a..k: ``associate_tracks``, the identity of each person from frame to frame (P3.05).

People are boxes (the 26 keypoints are spread over the box, so the hull is the box). The cost of a person against a
track is ``(w_iou x (1 - IoU) + w_kp x min(1, mean keypoint distance / track height)) / (w_iou + w_kp)``; for a box of
300 x 700 px that moves by ``s`` px sideways it is ``((1 - (300 - s) / (300 + s)) + s / 700) / 2``.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from helpers.pose_raw_build import (
    box,
    permute_persons_in_frames,
    pose_raw_from_scene,
    scene_from_paths,
)
from helpers.synth import make_scene
from taiji_ai.pose.runner import valid_keypoint_mask
from taiji_ai.track.associate import AssociationParams, _assign, associate_tracks, person_cost, track_of_person
from taiji_ai.track.geometry import iou, keypoint_hull

W, H = 300.0, 700.0


def still(cx: float, cy: float = 540.0, n_valid: int = 26):
    return lambda k: (box(cx, cy, W, H), n_valid)


def moving(cx0: float, dx: float, cy: float = 540.0, first: int = 0, last: int | None = None, n_valid: int = 26):
    def path(k: int):
        if k < first or (last is not None and k > last):
            return None
        return (box(cx0 + dx * k, cy, W, H), n_valid)

    return path


def shift_cost(s: float) -> float:
    """The cost of a 300 x 700 person that moved ``s`` px sideways (default weights)."""
    return ((1 - (W - s) / (W + s)) + min(1.0, s / H)) / 2


def swaps(track_id: np.ndarray, ids: np.ndarray) -> int:
    n = 0
    for t in np.unique(track_id[track_id >= 0]):
        seq = ids[track_id == t]
        n += int((seq[1:] != seq[:-1]).sum())
    return n


def tracks_of_identity(track_id: np.ndarray, ids: np.ndarray) -> dict[int, int]:
    return {int(i): len(np.unique(track_id[(ids == i) & (track_id >= 0)])) for i in np.unique(ids)}


# --- T-TRK-02: SYN-12, no identity swap --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_t_trk_02a_syn_12_has_no_identity_swap_and_the_target_has_two_tracks(seed: int):
    raw, ids = pose_raw_from_scene(make_scene("SYN-12", seed=seed))

    tracks = associate_tracks(raw)

    assert swaps(tracks.track_id, ids) == 0
    # the target (0) is absent for a second: two tracks (re-attaching them is P3.06); the others have one each
    assert tracks_of_identity(tracks.track_id, ids) == {0: 2, 1: 1, 2: 1}
    assert tracks.n_tracks == 4 and np.all(tracks.track_id >= 0)


@pytest.mark.parametrize(
    "params",
    [
        {"noise_px": 2.0},
        {"noise_px": 4.0},
        {"walk_px_s": 800.0},
        {"target_x0_px": 960.0},
        {"cross_s": 0.5},
        {"n_people": 2},
    ],
    ids=["noise2", "noise4", "fast", "central_target", "early_crossing", "two_people"],
)
def test_t_trk_02b_syn_12_variations_have_no_identity_swap(params: dict):
    for seed in range(5):
        raw, ids = pose_raw_from_scene(make_scene("SYN-12", seed=seed, **params))
        assert swaps(associate_tracks(raw).track_id, ids) == 0, f"seed {seed}"


def test_t_trk_02c_the_order_of_the_persons_in_a_frame_does_not_change_the_result():
    raw, ids = pose_raw_from_scene(make_scene("SYN-12", seed=3, noise_px=2.0))
    base = associate_tracks(raw)

    for seed in range(4):
        shuffled, shuffled_ids = permute_persons_in_frames(raw, ids, seed)
        tracks = associate_tracks(shuffled)
        assert swaps(tracks.track_id, shuffled_ids) == 0
        assert tracks.n_tracks == base.n_tracks
        assert tracks_of_identity(tracks.track_id, shuffled_ids) == tracks_of_identity(base.track_id, ids)


def test_t_trk_02d_two_identical_bodies_that_coincide_are_flagged_by_the_margin_not_hidden():
    """No appearance feature exists: where two identical people coincide the match is a tie and the margin says so (0);
    far from the crossing the nearest competitor is far (margin large)."""
    paths = {0: still(700.0), 1: moving(1300.0, -400.0 / 30)}  # B passes through A at frame 45
    raw, ids = scene_from_paths(paths, n_frames=90, shuffle_seed=1)

    tracks = associate_tracks(raw)

    frame_of_row = np.searchsorted(raw.person_offsets, np.arange(ids.size), side="right") - 1
    at_crossing = tracks.match_margin[frame_of_row == 45]
    far = tracks.match_margin[(frame_of_row >= 1) & (frame_of_row <= 10)]
    assert at_crossing.size == 2 and np.all(at_crossing < 0.02)
    assert far.size == 20 and np.all(far > 0.3)


# --- T-TRK-03: the number of people changes, gaps, the gate, weak persons ----------------------------------------


def test_t_trk_03a_a_person_who_leaves_and_one_who_enters_far_away_do_not_share_a_track():
    paths = {
        0: still(500.0),
        1: moving(1400.0, 0.0, last=4),  # leaves after frame 4
        2: moving(300.0, 0.0, first=5, cy=300.0),  # enters at frame 5, far from where 1 was
    }
    raw, ids = scene_from_paths(paths, n_frames=10)

    tracks = associate_tracks(raw)

    assert tracks_of_identity(tracks.track_id, ids) == {0: 1, 1: 1, 2: 1}
    assert len(set(tracks.track_id.tolist())) == 3 and tracks.n_tracks == 3
    steady = tracks.track_id[ids == 0]
    assert len(set(steady.tolist())) == 1 and np.all(tracks.gap_frames[ids == 0][1:] == 1)


def test_t_trk_03a_a_person_who_misses_one_frame_and_comes_back_at_the_same_place_keeps_the_track():
    paths = {0: lambda k: None if k == 4 else (box(900, 540, W, H), 26)}
    raw, _ = scene_from_paths(paths, n_frames=9)

    tracks = associate_tracks(raw)

    assert tracks.n_tracks == 1 and np.all(tracks.track_id == 0)
    assert tracks.gap_frames.tolist() == [0, 1, 1, 1, 2, 1, 1, 1]  # frame 5 follows frame 3: two frames after it


def test_t_trk_03b_a_gap_up_to_max_gap_s_keeps_the_track_a_longer_one_closes_it():
    def gap(first_missing: int, n_missing: int):
        return lambda k: None if first_missing <= k < first_missing + n_missing else (box(900, 540, W, H), 26)

    short, _ = scene_from_paths({0: gap(5, 3)}, n_frames=14, fps=60.0)  # 3 missing frames: 0.05 s
    long, _ = scene_from_paths({0: gap(5, 8)}, n_frames=20, fps=60.0)  # 8 missing frames: 0.133 s

    kept, closed = associate_tracks(short), associate_tracks(long)

    assert kept.n_tracks == 1 and kept.gap_frames.max() == 4 and np.nanmax(kept.gap_s) == pytest.approx(4 / 60)
    assert closed.n_tracks == 2 and closed.gap_frames.tolist().count(0) == 2


def test_t_trk_03c_the_gate_is_inclusive_and_an_unmatched_person_is_not_forced_onto_a_free_track():
    s = 60.0
    raw, _ = scene_from_paths({0: moving(700.0, s)}, n_frames=3)
    cost = shift_cost(s)

    inside = associate_tracks(raw, params=AssociationParams(max_cost=cost + 1e-6))
    outside = associate_tracks(raw, params=AssociationParams(max_cost=cost - 1e-6))

    assert inside.n_tracks == 1 and inside.match_cost[1] == pytest.approx(cost, abs=1e-6)
    assert outside.n_tracks == 3 and np.all(np.isnan(outside.match_cost)) and outside.gap_frames.tolist() == [0, 0, 0]


def test_t_trk_03c_the_default_gate_separates_a_normal_step_from_a_jump():
    assert associate_tracks(scene_from_paths({0: moving(700.0, 20.0)}, n_frames=5)[0]).n_tracks == 1
    assert associate_tracks(scene_from_paths({0: moving(700.0, 100.0)}, n_frames=5)[0]).n_tracks == 5


def test_t_trk_03d_weak_persons_are_not_tracked_and_take_nothing_from_a_real_person():
    paths = {0: still(900.0), 1: still(930.0, n_valid=3)}  # a weak person overlapping the real one
    raw, ids = scene_from_paths(paths, n_frames=6)
    scores = raw.scores.copy()
    scores[ids == 1] = 0.05
    scores[np.ix_(ids == 1, [0, 4, 5, 9, 10])] = (
        0.9  # five valid keypoints on three rows: a hull with an area, but weak
    )
    raw = dataclasses.replace(raw, scores=scores)

    tracks = associate_tracks(raw)

    weak = ids == 1
    assert np.all(tracks.track_id[weak] == -1) and np.all(np.isnan(tracks.match_cost[weak]))
    assert np.all(tracks.gap_frames[weak] == -1) and np.all(np.isnan(tracks.gap_s[weak]))
    assert tracks.n_tracks == 1 and np.all(tracks.track_id[~weak] == 0)


def test_t_trk_03e_a_person_with_missing_keypoints_is_matched_on_the_common_ones():
    raw, _ = scene_from_paths({0: still(900.0)}, n_frames=4)
    scores = raw.scores.copy()
    scores[1:, 10:] = 0.05  # from frame 1 only the first 10 keypoints are valid (still eligible: 6 needed)
    kp = raw.keypoints.copy()
    kp[2, 3] = np.nan
    raw = dataclasses.replace(raw, scores=scores, keypoints=kp)

    tracks = associate_tracks(raw)

    assert tracks.n_tracks == 1 and np.all(np.isfinite(tracks.match_cost[1:]))
    assert np.all(tracks.match_cost[1:] < 0.4)


def test_t_trk_03e_fewer_than_four_common_keypoints_leave_the_iou_term_alone():
    raw, _ = scene_from_paths({0: still(900.0)}, n_frames=2)
    scores = raw.scores.copy()
    scores[0, :] = 0.05
    scores[0, :6] = 0.9  # the track starts with keypoints 0 to 5 (the two top rows of the body)
    scores[1, :] = 0.05
    scores[1, 3:17] = 0.9  # the next frame has 3 to 16: three in common (3, 4, 5), and a taller hull
    # the boxes the detector stored are unrelated to the hulls: only the keypoints count
    odd = np.random.default_rng(0).uniform(0, 1900, raw.bboxes.shape).astype(np.float32)
    raw = dataclasses.replace(raw, scores=scores, bboxes=odd)
    valid = valid_keypoint_mask(raw.keypoints, raw.scores, raw.params.min_score)
    expected = 1.0 - iou(keypoint_hull(raw.keypoints[0], valid[0]), keypoint_hull(raw.keypoints[1], valid[1]))

    tracks = associate_tracks(raw, params=AssociationParams(max_cost=1.0))

    assert 0.3 < expected < 0.9  # the two hulls really differ, so the test can tell the terms apart
    assert tracks.n_tracks == 1 and tracks.match_cost[1] == pytest.approx(expected, abs=1e-6)


def test_t_trk_03f_the_gap_is_measured_in_real_time_not_in_frames():
    paths = {0: lambda k: None if 4 <= k <= 6 else (box(900, 540, W, H), 26)}  # the same three missing frames
    at_60, _ = scene_from_paths(paths, n_frames=12, fps=60.0)  # 0.067 s from frame 3 to 7
    at_10, _ = scene_from_paths(paths, n_frames=12, fps=10.0)  # 0.4 s

    assert associate_tracks(at_60).n_tracks == 1
    assert associate_tracks(at_10).n_tracks == 2


def test_t_trk_03f_uneven_frame_times_do_not_break_a_steady_walker():
    raw, _ = scene_from_paths({0: moving(700.0, 15.0)}, n_frames=10)
    t = np.cumsum(np.where(np.arange(10) % 2 == 0, 1 / 60, 1 / 20)).astype(np.float64)
    raw = dataclasses.replace(raw, t_sec=t, segment_s=(float(t[0]), float(t[-1])))

    assert associate_tracks(raw).n_tracks == 1


def test_t_trk_03g_the_outputs_have_the_documented_form():
    paths = {0: still(500.0), 1: moving(1400.0, 0.0, first=2), 2: still(300.0, n_valid=2)}
    raw, ids = scene_from_paths(paths, n_frames=6)
    before = {n: getattr(raw, n).tobytes() for n in ("bboxes", "keypoints", "scores", "person_offsets", "t_sec")}

    tracks = associate_tracks(raw)

    d = int(raw.person_offsets[-1])
    assert tracks.track_id.dtype == np.int32 and tracks.track_id.shape == (d,)
    for name in ("match_cost", "match_margin", "gap_s"):
        assert getattr(tracks, name).dtype == np.float32 and getattr(tracks, name).shape == (d,)
    assert tracks.gap_frames.dtype == np.int32 and tracks.gap_frames.shape == (d,)
    assert tracks.track_id[ids == 0].tolist() == [0] * 6 and tracks.track_id[ids == 1].tolist() == [1] * 4
    starts = (tracks.gap_frames == 0) | (tracks.gap_frames == -1)
    assert np.all(np.isnan(tracks.match_cost[starts])) and np.all(np.isfinite(tracks.match_cost[~starts]))
    assert tracks.n_tracks == 2
    assert tracks.track_first_frame.tolist() == [0, 2] and tracks.track_last_frame.tolist() == [5, 5]
    assert tracks.track_n_persons.tolist() == [6, 4]
    assert {n: getattr(raw, n).tobytes() for n in before} == before  # the raw layer is not touched
    assert tracks.equals(associate_tracks(raw))  # deterministic


def test_t_trk_03g_frames_without_persons_and_a_single_frame():
    raw, _ = scene_from_paths({0: lambda k: None if k in (1, 2) else (box(900, 540, W, H), 26)}, n_frames=5)
    assert (
        associate_tracks(raw).n_tracks == 1
    )  # two missing frames at 30 fps: 0.1 s from the last person, still allowed
    one, _ = scene_from_paths({0: still(900.0)}, n_frames=1)
    result = associate_tracks(one)
    assert result.n_tracks == 1 and result.gap_frames.tolist() == [0] and np.isnan(result.match_margin[0])
    nobody, _ = scene_from_paths({0: lambda k: None}, n_frames=3)
    empty = associate_tracks(nobody)
    assert empty.n_tracks == 0 and empty.track_id.size == 0 and empty.track_first_frame.size == 0


def test_t_trk_03h_bad_parameters_are_refused():
    bad = [
        {"w_iou": -1.0},
        {"w_kp": float("nan")},
        {"w_iou": 0.0, "w_kp": 0.0},
        {"max_cost": 0.0},
        {"max_cost": 1.5},
        {"max_gap_s": -0.1},
        {"max_gap_s": float("inf")},
        {"min_common_keypoints": 0},
        {"min_common_keypoints": 27},
    ]
    for kwargs in bad:
        with pytest.raises(ValueError):
            AssociationParams(**kwargs)


def test_t_trk_03i_the_boxes_the_detector_stored_do_not_matter_only_the_keypoints_do():
    paths = {0: moving(700.0, 10.0), 1: still(1400.0)}
    raw, ids = scene_from_paths(paths, n_frames=8)
    odd = dataclasses.replace(
        raw, bboxes=np.random.default_rng(0).uniform(0, 1900, raw.bboxes.shape).astype(np.float32)
    )

    assert associate_tracks(odd).equals(associate_tracks(raw))


def test_t_trk_03j_track_of_person_and_the_margin_of_a_simple_case():
    """A track at x = 500 and one person at 500 and one at 560: the match costs 0 and the competitor 0.2108 more."""
    raw, ids = scene_from_paths(
        {0: still(500.0), 1: lambda k: (box(560, 540, W, H), 26) if k == 1 else None}, n_frames=2
    )

    tracks = associate_tracks(raw)

    first, second_a, second_b = 0, 1, 2  # person rows: frame 0 has one person; frame 1 has two
    assert ids.tolist() == [0, 0, 1]
    assert track_of_person(tracks, second_a) == tracks.track_id[1] == tracks.track_id[0]
    assert (
        track_of_person(tracks, second_b) == 1
    )  # the person at 560 starts a track (its cost to track 0 is the margin)
    assert tracks.match_margin[1] == pytest.approx(shift_cost(60.0), abs=1e-6)
    with pytest.raises(ValueError):
        track_of_person(tracks, 99)
    assert first == 0


def test_t_trk_03k_the_margin_also_sees_a_competing_track():
    paths = {0: still(500.0), 1: lambda k: (box(560, 540, W, H), 26) if k == 0 else None}
    raw, ids = scene_from_paths(paths, n_frames=2)  # frame 0: two people; frame 1: only the one at 500

    tracks = associate_tracks(raw)

    row_at_500_in_frame_1 = 2
    assert tracks.track_id[row_at_500_in_frame_1] == tracks.track_id[0]
    assert tracks.match_margin[row_at_500_in_frame_1] == pytest.approx(shift_cost(60.0), abs=1e-6)


def test_t_trk_03l_the_assignment_is_global_not_greedy():
    """A is nearer to the person that B is nearer to: the greedy choice leaves one person without a match."""
    paths = {0: lambda k: (box(500 + 50 * k, 540, W, H), 26), 1: lambda k: (box(580 + 50 * k, 540, W, H), 26)}
    raw, ids = scene_from_paths(paths, n_frames=2)  # frame 1: A at 550 (30 px from B's old place), B at 630

    tracks = associate_tracks(raw)

    assert swaps(tracks.track_id, ids) == 0 and tracks.n_tracks == 2 and np.all(tracks.gap_frames[2:] == 1)


def test_t_trk_03l_assign_maximises_the_valid_matches_before_the_total_cost():
    inf = float("inf")
    # the cheapest total is (0, 1) + (1, 0) = 0.32 but (0, 1) is above the gate: two valid matches are better than one
    cost = np.array([[0.25, 0.31], [0.01, 0.25]])
    assert sorted(_assign(cost, 0.3)) == [(0, 0), (1, 1)]
    assert _assign(np.array([[0.9, 0.8]]), 0.3) == []  # nothing within the gate
    assert _assign(np.empty((0, 3)), 0.3) == [] and _assign(np.empty((2, 0)), 0.3) == []
    assert _assign(np.array([[inf, 0.1]]), 0.3) == [
        (0, 1)
    ]  # an infinite cost (no hull) is a pair that cannot be matched


def test_t_trk_03m_the_cost_is_between_0_and_1_a_far_person_costs_exactly_1():
    paths = {
        0: still(500.0),
        1: lambda k: (box(2600, 540, W, H), 26) if k == 1 else None,
    }  # 2100 px away: 3 body heights
    raw, ids = scene_from_paths(paths, n_frames=2)

    tracks = associate_tracks(raw)

    assert tracks.match_margin[1] == pytest.approx(1.0, abs=1e-6)  # the far person costs (1 + min(1, 3)) / 2 = 1
    assert float(np.nanmax(tracks.match_cost)) <= 1.0


def test_t_trk_03l_a_pair_exactly_at_the_gate_is_valid_inside_the_assignment_too():
    # the valid pairs cost exactly the gate, the others a little more: the valid pairs must win
    assert sorted(_assign(np.array([[0.31, 0.3], [0.3, 0.31]]), 0.3)) == [(0, 1), (1, 0)]


def test_t_trk_03e_the_keypoint_distance_is_divided_by_the_height_of_the_whole_track_not_of_the_common_keypoints():
    """Only the two top rows of the body are common (a short hull of 140 px) but the track is 700 px high."""
    raw, _ = scene_from_paths({0: moving(900.0, 20.0)}, n_frames=2)
    scores = raw.scores.copy()
    scores[1, 10:] = 0.05  # frame 1: only keypoints 0 to 9 (two rows) are valid
    raw = dataclasses.replace(raw, scores=scores)
    s = 20.0
    expected = (
        (1 - (W - s) / (W + s)) + s / H
    ) / 2  # the common hull (300 x 140) moved by s: the same IoU as the full box

    tracks = associate_tracks(raw)

    assert tracks.n_tracks == 1 and tracks.match_cost[1] == pytest.approx(expected, abs=1e-6)


# --- person_cost: the public cost of two person rows (used by P3.06) -----------------------------------------------
def test_t_trk_03n_person_cost_of_the_same_pose_is_0_and_of_a_shifted_box_the_documented_formula():
    raw, _ = scene_from_paths({0: still(900.0), 1: still(1000.0)}, n_frames=1)  # two people of one frame, 100 px apart
    assert person_cost(raw, 0, 0) == 0.0
    assert person_cost(raw, 0, 1) == pytest.approx(shift_cost(100.0), abs=1e-9)
    assert isinstance(person_cost(raw, 0, 1), float)


def test_t_trk_03n_person_cost_is_the_cost_the_association_used_for_the_match():
    raw, _ = scene_from_paths({0: moving(900.0, 20.0)}, n_frames=2)
    tracks = associate_tracks(raw)
    assert tracks.n_tracks == 1
    assert person_cost(raw, 0, 1) == pytest.approx(float(tracks.match_cost[1]), abs=1e-6)


def test_t_trk_03n_person_cost_uses_the_height_of_the_first_person_so_it_is_not_symmetric():
    raw, _ = scene_from_paths(
        {0: lambda k: (box(900.0, 540.0, W, H), 26), 1: lambda k: (box(900.0, 540.0, W / 2, H / 2), 26)}, n_frames=1
    )
    kp_a, kp_b = raw.keypoints[0].astype(float), raw.keypoints[1].astype(float)
    distance = float(np.linalg.norm(kp_a - kp_b, axis=1).mean())
    iou_term = 1.0 - 0.25  # the small box is a quarter of the big one and inside it
    assert person_cost(raw, 0, 1) == pytest.approx((iou_term + min(1.0, distance / H)) / 2, abs=1e-6)
    assert person_cost(raw, 1, 0) == pytest.approx((iou_term + min(1.0, distance / (H / 2))) / 2, abs=1e-6)
    assert person_cost(raw, 0, 1) != person_cost(raw, 1, 0)


def test_t_trk_03n_person_cost_follows_the_parameters():
    raw, _ = scene_from_paths({0: still(900.0), 1: still(1000.0)}, n_frames=1)
    iou_only = person_cost(raw, 0, 1, params=AssociationParams(w_kp=0.0))
    assert iou_only == pytest.approx(1.0 - (W - 100.0) / (W + 100.0), abs=1e-9)
    kp_only = person_cost(raw, 0, 1, params=AssociationParams(w_iou=0.0))
    assert kp_only == pytest.approx(100.0 / H, abs=1e-9)


def test_t_trk_03n_person_cost_is_infinite_when_a_person_has_no_hull_and_refuses_a_missing_row():
    raw, _ = scene_from_paths({0: still(900.0), 1: still(1000.0, n_valid=1)}, n_frames=1)  # one valid keypoint: no hull
    assert person_cost(raw, 0, 1) == float("inf") and person_cost(raw, 1, 0) == float("inf")
    for a, b in ((-1, 0), (0, 2), (2, 0), (0, -1)):
        with pytest.raises(ValueError, match="row"):
            person_cost(raw, a, b)


def test_t_trk_03n_person_cost_does_not_modify_the_pose():
    raw, _ = scene_from_paths({0: still(900.0), 1: still(1000.0)}, n_frames=1)
    keypoints, scores = raw.keypoints.copy(), raw.scores.copy()
    person_cost(raw, 0, 1)
    assert np.array_equal(raw.keypoints, keypoints) and np.array_equal(raw.scores, scores)
