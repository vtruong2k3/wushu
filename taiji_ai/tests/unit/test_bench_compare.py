"""T-BENCH-03: comparing two pose runs of the same frames (N against N = 1) and the downstream summary (P3.07).

People are boxes on explicit paths (``helpers/track_build.py``); the 26 keypoints are spread over the box, so the hull
of a person of 26 valid keypoints is the box (500 px high here). No GPU and no video.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from helpers.pose_raw_build import permute_persons_in_frames, scene_from_paths
from helpers.track_build import BOX_H, FPS, HOME_X, stands
from taiji_ai.bench import BenchError
from taiji_ai.bench.compare import (
    JOINT_GROUPS,
    compare_runs,
    compare_target_tracks,
    downstream_summary,
    pool_comparisons,
    pool_target_comparisons,
    same_target,
)
from taiji_ai.pose.runner import PoseRaw
from taiji_ai.pose.skeleton import JOINTS


def scene(paths: dict, n: int = 40, fps: float = FPS) -> tuple[PoseRaw, np.ndarray]:
    return scene_from_paths(paths, n_frames=n, fps=fps)


def shifted(path, dx: float):
    def moved(k: int):
        p = path(k)
        if p is None:
            return None
        (x0, y0, x1, y1), n_valid = p
        return (x0 + dx, y0, x1 + dx, y1), n_valid

    return moved


def key(c) -> tuple:
    return (
        c.n_frames, c.n_equal_count_frames, c.n_pairs, c.n_missed, c.n_extra, c.n_uncomparable_ref,
        c.n_uncomparable_other, c.entry_delays, c.n_tracks_never_matched, c.dist_px.tolist(),
    )  # fmt: skip


# --- T-BENCH-03a: matching and distances ----------------------------------------------------------------------------
def test_t_bench_03a_identical_runs_have_zero_distance_and_full_agreement():
    ref, _ = scene({0: stands(HOME_X), 1: stands(1500)})
    other, _ = scene({0: stands(HOME_X), 1: stands(1500)})

    c = compare_runs(ref, other)

    assert (c.n_frames, c.n_equal_count_frames, c.count_agreement) == (40, 40, 1.0)
    assert (c.n_ref_persons, c.n_other_persons, c.n_pairs, c.n_missed, c.n_extra) == (80, 80, 80, 0, 0)
    assert (c.n_uncomparable_ref, c.n_uncomparable_other) == (0, 0)
    assert c.px is not None and c.norm is not None
    assert c.px.max == 0.0 and c.norm.max == 0.0 and c.px.n == 80 * 26


def test_t_bench_03a_a_shift_of_d_pixels_gives_d_pixels_and_d_over_the_body_height():
    ref, _ = scene({0: stands(HOME_X)})
    other, _ = scene({0: shifted(stands(HOME_X), 10.0)})

    c = compare_runs(ref, other)

    assert c.px is not None and c.norm is not None
    for value in (c.px.median, c.px.p95, c.px.p99, c.px.max):
        assert value == pytest.approx(10.0, abs=1e-3)
    for value in (c.norm.median, c.norm.p95, c.norm.p99, c.norm.max):
        assert value == pytest.approx(10.0 / BOX_H, abs=1e-5)  # the height of the reference person, not of the other
    assert c.px.n == 26 * 40 and c.n_pairs == 40


def test_t_bench_03a_the_body_height_is_the_one_of_the_reference_run():
    ref, _ = scene({0: stands(HOME_X)})
    other, _ = scene({0: shifted(stands(HOME_X), 10.0)})
    swapped = compare_runs(other, ref)  # the same pair with the roles exchanged: the same height here
    assert swapped.norm is not None and swapped.norm.max == pytest.approx(10.0 / BOX_H, abs=1e-5)
    # a taller reference makes the same pixels a smaller share of the body
    tall_kp = ref.keypoints.copy()
    tall_kp[..., 1] = (tall_kp[..., 1] - tall_kp[..., 1].mean()) * 2.0 + tall_kp[..., 1].mean()
    tall = dataclasses.replace(ref, keypoints=tall_kp)
    shift_only = dataclasses.replace(tall, keypoints=tall.keypoints + np.array([10.0, 0.0], np.float32))
    c = compare_runs(tall, shift_only)
    assert c.norm is not None and c.norm.max == pytest.approx(10.0 / (2.0 * BOX_H), abs=1e-5)


def test_t_bench_03a_a_person_that_only_one_run_has_is_counted_missed_or_extra():
    two, _ = scene({0: stands(HOME_X), 1: stands(1500)})
    one, _ = scene({0: stands(HOME_X)})

    lost = compare_runs(two, one)
    gained = compare_runs(one, two)

    assert (lost.n_pairs, lost.n_missed, lost.n_extra, lost.count_agreement) == (40, 40, 0, 0.0)
    assert (gained.n_pairs, gained.n_missed, gained.n_extra, gained.count_agreement) == (40, 0, 40, 0.0)


def test_t_bench_03a_the_order_of_the_persons_in_a_frame_does_not_change_the_result():
    ref, ids = scene({0: stands(HOME_X), 1: stands(1500), 2: stands(300)})
    other, _ = scene({0: shifted(stands(HOME_X), 4.0), 1: stands(1500), 2: shifted(stands(300), -6.0)})
    permuted, _ = permute_persons_in_frames(other, ids, seed=3)

    a, b = compare_runs(ref, other), compare_runs(ref, permuted)

    assert key(a)[:9] == key(b)[:9] and sorted(a.dist_px.tolist()) == sorted(b.dist_px.tolist())


def test_t_bench_03a_a_person_with_fewer_than_4_common_valid_keypoints_is_uncomparable_not_dropped():
    ref, _ = scene({0: stands(HOME_X, n_valid=3), 1: stands(1500)})
    other, _ = scene({0: stands(HOME_X, n_valid=3), 1: stands(1500)})

    c = compare_runs(ref, other)

    assert (c.n_pairs, c.n_uncomparable_ref, c.n_uncomparable_other, c.n_missed, c.n_extra) == (40, 40, 40, 0, 0)
    assert c.n_ref_persons == 80 and c.n_other_persons == 80  # the weak person is counted as a person


def test_t_bench_03a_a_weak_person_against_an_empty_frame_is_missed():
    ref, _ = scene({0: stands(HOME_X, n_valid=3)})
    other, _ = scene({0: lambda k: None})
    c = compare_runs(ref, other)
    assert (c.n_missed, c.n_uncomparable_ref, c.n_pairs) == (40, 0, 0)


def test_t_bench_03a_the_match_gate_is_inclusive_and_is_a_share_of_the_body_height():
    ref, _ = scene({0: stands(HOME_X)})
    other, _ = scene({0: shifted(stands(HOME_X), 250.0)})
    probe = compare_runs(ref, other, gate=10.0)
    cost = float(probe.pair_costs[0])
    assert cost == pytest.approx(0.5, abs=1e-4) and probe.n_pairs == 40  # 250 px of a 500 px body

    at_gate = compare_runs(ref, other, gate=cost)
    just_under = compare_runs(ref, other, gate=float(np.nextafter(cost, 0.0)))

    assert at_gate.n_pairs == 40 and at_gate.n_missed == 0
    assert just_under.n_pairs == 0 and just_under.n_missed == 40 and just_under.n_extra == 40
    assert just_under.px is None and just_under.norm is None  # no pair: no distance, not a zero


def test_t_bench_03a_nobody_in_either_run_is_full_agreement_without_distances():
    ref, _ = scene({0: lambda k: None}, n=10)
    other, _ = scene({0: lambda k: None}, n=10)
    c = compare_runs(ref, other)
    assert c.count_agreement == 1.0 and c.n_pairs == 0 and c.px is None and c.norm is None
    assert c.entry_delays == () and c.n_tracks_never_matched == 0


# --- T-BENCH-03b: entry delay, joint groups, pooling, refusals ------------------------------------------------------
def test_t_bench_03b_a_person_that_appears_k_frames_late_has_an_entry_delay_of_k():
    ref, _ = scene({0: stands(HOME_X, first=5)})
    other, _ = scene({0: stands(HOME_X, first=8)})

    c = compare_runs(ref, other)

    assert c.entry_delays == (3,) and c.n_missed == 3 and c.n_extra == 0 and c.n_tracks_never_matched == 0


def test_t_bench_03b_a_person_present_from_the_start_has_delay_0_and_a_never_found_one_is_counted():
    ref, _ = scene({0: stands(HOME_X), 1: stands(1500, first=10)})
    other, _ = scene({0: stands(HOME_X)})

    c = compare_runs(ref, other)

    assert c.entry_delays == (0,) and c.n_tracks_never_matched == 1


def test_t_bench_03b_the_p95_per_joint_group_uses_the_right_joints():
    ref, _ = scene({0: stands(HOME_X)})
    keypoints = ref.keypoints.copy()
    feet = [JOINTS.index(name) for name in JOINT_GROUPS["feet"]]
    keypoints[:, feet, 0] += 20.0  # only the feet move, 6 of 26 joints: the match still holds
    other = dataclasses.replace(ref, keypoints=keypoints)

    c = compare_runs(ref, other)

    groups = c.group_p95
    assert groups["feet"] == pytest.approx(20.0 / BOX_H, abs=1e-5)
    for name in ("head", "trunk", "arms", "legs"):
        assert groups[name] == pytest.approx(0.0, abs=1e-9), name


def test_t_bench_03b_the_joint_groups_cover_the_26_joints_once():
    names = [name for group in JOINT_GROUPS.values() for name in group]
    assert sorted(names) == sorted(JOINTS) and set(JOINT_GROUPS) == {"head", "trunk", "arms", "legs", "feet"}


def test_t_bench_03b_pooling_takes_the_percentiles_over_all_distances_not_the_mean_of_percentiles():
    ref, _ = scene({0: stands(HOME_X)})
    near, _ = scene({0: shifted(stands(HOME_X), 10.0)})
    far, _ = scene({0: shifted(stands(HOME_X), 30.0)})

    pooled = pool_comparisons([compare_runs(ref, near), compare_runs(ref, far)])

    assert pooled.n_frames == 80 and pooled.n_pairs == 80 and pooled.px is not None
    assert pooled.px.median == pytest.approx(20.0, abs=1e-3) and pooled.px.max == pytest.approx(30.0, abs=1e-3)
    assert pooled.px.n == 2 * 26 * 40 and pooled.count_agreement == 1.0
    with pytest.raises(BenchError):
        pool_comparisons([])


def test_t_bench_03b_runs_of_different_frames_are_refused():
    ref, _ = scene({0: stands(HOME_X)}, fps=30.0)
    other, _ = scene({0: stands(HOME_X)}, fps=25.0)
    with pytest.raises(BenchError, match="frames"):
        compare_runs(ref, other)
    shorter, _ = scene({0: stands(HOME_X)}, n=39)
    with pytest.raises(BenchError, match="frames"):
        compare_runs(ref, shorter)


# --- T-BENCH-03c: the downstream summary ----------------------------------------------------------------------------
def test_t_bench_03c_the_downstream_summary_of_a_target_that_leaves_for_a_second():
    raw, _ = scene({0: stands(HOME_X, absent=[(30, 60)]), 1: stands(1500)}, n=100)

    d = downstream_summary(raw)

    assert d.target_found and d.error is None and d.selection_frame_pos == 0
    assert (d.share_tracked, d.share_lost, d.share_target_lost, d.share_before_target) == (0.7, 0.15, 0.15, 0.0)
    assert d.events == {"lost": 1, "target_lost": 1, "reattached": 1}
    assert d.needs_reselect is False and d.reselect_reason is None
    assert d.target_keypoints is not None and d.target_keypoints.shape == (26, 2)


def test_t_bench_03c_the_same_poses_give_the_same_target_and_another_person_does_not():
    paths = {0: stands(HOME_X), 1: stands(1500)}
    raw, _ = scene(paths, n=40)
    same, _ = scene(paths, n=40)
    other_person, _ = scene({1: stands(1500)}, n=40)  # the person at the centre is not in this run

    ref = downstream_summary(raw)

    assert same_target(ref, downstream_summary(same)) is True
    assert same_target(ref, downstream_summary(other_person)) is False


def test_t_bench_03c_no_target_is_reported_not_raised():
    empty, _ = scene({0: lambda k: None}, n=10)
    d = downstream_summary(empty)
    assert d.target_found is False and d.error and d.share_tracked is None and d.events == {}
    assert d.needs_reselect is None and d.target_keypoints is None
    assert same_target(d, d) is None  # nothing to compare
    full = downstream_summary(scene({0: stands(HOME_X)}, n=10)[0])
    assert same_target(full, d) is False and same_target(d, full) is False


# --- T-BENCH-03d: the target track of two runs (what P4 receives); added after the dry run, not in the rule ----
def target_of(paths: dict, n: int = 40, scores=None):
    raw, _ = scene(paths, n=n)
    if scores is not None:
        raw = dataclasses.replace(raw, scores=scores(raw.scores))
    return raw, downstream_summary(raw)


def test_t_bench_03d_the_same_target_track_has_zero_distance_and_a_shifted_one_has_the_shift():
    raw_a, a = target_of({0: stands(HOME_X)})
    raw_b, b = target_of({0: shifted(stands(HOME_X), 10.0)})

    same = compare_target_tracks(a, a, raw_a.params.min_score)
    moved = compare_target_tracks(a, b, raw_a.params.min_score)

    assert same is not None and (same.n_frames, same.n_both_tracked, same.n_ref_only, same.n_other_only) == (
        40,
        40,
        0,
        0,
    )
    assert same.px is not None and same.px.max == 0.0
    assert moved is not None and moved.px is not None and moved.norm is not None
    assert moved.px.median == pytest.approx(10.0, abs=1e-3) and moved.norm.max == pytest.approx(10.0 / BOX_H, abs=1e-5)
    assert moved.px.n == 26 * 40 and raw_b.n_frames == 40


def test_t_bench_03d_frames_where_only_one_run_has_the_target_are_counted_not_compared():
    raw, ref = target_of({0: stands(HOME_X)})
    _, other = target_of({0: stands(HOME_X, absent=[(20, 30)])})  # the target is away for 10 frames

    c = compare_target_tracks(ref, other, raw.params.min_score)
    back = compare_target_tracks(other, ref, raw.params.min_score)

    assert c is not None and (c.n_both_tracked, c.n_ref_only, c.n_other_only) == (30, 10, 0)
    assert c.n_uncomparable_frames == 0  # a frame without the target in the other run is not 'uncomparable'
    assert back is not None and (back.n_both_tracked, back.n_ref_only, back.n_other_only) == (30, 0, 10)
    assert c.px is not None and c.px.max == 0.0  # the 30 common frames are the same pose


def test_t_bench_03d_frames_with_fewer_than_4_common_valid_keypoints_are_uncomparable():
    raw, ref = target_of({0: stands(HOME_X, n_valid=6)})  # keypoints 0 to 5 valid
    _, other = target_of(
        {0: stands(HOME_X)}, scores=lambda s: np.where(np.arange(26) >= 20, 0.9, 0.05).astype(np.float32) + 0 * s
    )  # keypoints 20 to 25 valid: nothing in common with the other run
    c = compare_target_tracks(ref, other, raw.params.min_score)
    assert c is not None and c.n_both_tracked == 40 and c.n_uncomparable_frames == 40 and c.px is None


def test_t_bench_03d_no_target_in_either_run_gives_none_and_other_frames_are_refused():
    raw, ref = target_of({0: stands(HOME_X)})
    _, none = target_of({0: lambda k: None}, n=40)
    assert compare_target_tracks(ref, none, raw.params.min_score) is None
    assert compare_target_tracks(none, none, raw.params.min_score) is None
    _, shorter = target_of({0: stands(HOME_X)}, n=39)
    with pytest.raises(BenchError, match="frames"):
        compare_target_tracks(ref, shorter, raw.params.min_score)


def test_t_bench_03d_pooling_target_comparisons_adds_up_the_counts_and_pools_the_distances():
    raw, ref = target_of({0: stands(HOME_X)})
    _, near = target_of({0: shifted(stands(HOME_X), 10.0)})
    _, far = target_of({0: shifted(stands(HOME_X), 30.0)})
    a = compare_target_tracks(ref, near, raw.params.min_score)
    b = compare_target_tracks(ref, far, raw.params.min_score)
    assert a is not None and b is not None

    pooled = pool_target_comparisons([a, b])

    assert pooled.n_frames == 80 and pooled.n_both_tracked == 80 and pooled.px is not None
    assert pooled.px.median == pytest.approx(20.0, abs=1e-3) and pooled.px.n == 2 * 26 * 40
    with pytest.raises(BenchError):
        pool_target_comparisons([])


# --- found by the mutation check: boundaries and counts ---------------------------------------------------------------
def test_t_bench_03a_exactly_four_common_valid_keypoints_are_enough_to_compare():
    # four joints in four different rows and columns, so that their hull has a width and a height
    four = np.where(np.isin(np.arange(26), [0, 6, 12, 18]), 0.9, 0.05).astype(np.float32)

    def only_four(raw: PoseRaw) -> PoseRaw:
        return dataclasses.replace(raw, scores=np.broadcast_to(four, raw.scores.shape).copy())

    ref, _ = scene({0: stands(HOME_X)})
    other, _ = scene({0: shifted(stands(HOME_X), 5.0)})
    ref, other = only_four(ref), only_four(other)

    enough = compare_runs(ref, other)
    too_few = compare_runs(ref, other, min_common=5)

    assert enough.n_pairs == 40 and enough.n_uncomparable_ref == 0 and enough.px is not None and enough.px.n == 4 * 40
    assert too_few.n_pairs == 0 and too_few.n_uncomparable_ref == 40


def test_t_bench_03c_a_target_chosen_on_another_frame_is_not_the_same_target():
    ref = downstream_summary(scene({0: stands(HOME_X)}, n=40)[0])
    late = downstream_summary(scene({0: stands(HOME_X, first=5)}, n=40)[0])  # nobody before frame 5: chosen there
    assert (ref.selection_frame_pos, late.selection_frame_pos) == (0, 5)
    assert same_target(ref, late) is False


def test_t_bench_03c_the_same_target_gate_is_inclusive():
    ref = downstream_summary(scene({0: stands(HOME_X)}, n=40)[0])
    moved = downstream_summary(scene({0: shifted(stands(HOME_X), 250.0)}, n=40)[0])  # exactly half the 500 px body
    assert same_target(ref, moved, gate=0.5) is True
    assert same_target(ref, moved, gate=0.499) is False
