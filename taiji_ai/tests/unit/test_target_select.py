"""T-TRK-01a..m: ``select_target``, the performer on the first frame of a segment (P3.04).

Boxes are in a 1920 x 1080 image (area 2 073 600 px2, half diagonal 1101.5 px). The default score of a person is
``area / image area x (1 - min(1, d / half diagonal))``, ``d`` the distance of the box centre to the image centre.
"""

from __future__ import annotations

import dataclasses
import itertools
import math

import numpy as np
import pytest

from helpers.pose_raw_build import box, pose_raw_from_boxes, pose_raw_from_scene
from helpers.synth import make_scene
from taiji_ai.track.target import TargetParams, TargetSelectionError, select_target

PERFORMER = box(960, 540, 300, 700)  # centred: score 210000 / 2073600 = 0.1013
HALF_DIAGONAL = 1101.5


def _frames(*persons, n=4):
    return [list(persons) for _ in range(n)]


def test_t_trk_01a_one_person_is_chosen_and_is_not_ambiguous():
    raw = pose_raw_from_boxes(_frames((PERFORMER, 26)), first_frame_index=100)

    sel = select_target(raw)

    assert (sel.method, sel.person_row, sel.frame_pos, sel.frame_index) == ("default", 0, 0, 100)
    assert sel.t_sec == 0.0 and sel.offset_from_start_s == 0.0
    assert sel.bbox == pytest.approx(PERFORMER)
    assert sel.n_candidates == 1 and not sel.ambiguous and sel.runner_up_ratio is None
    assert sel.weak is False and sel.n_valid_keypoints == 26
    assert sel.score == pytest.approx(210000 / 2073600)


@pytest.mark.parametrize("performer_first", [True, False])
def test_t_trk_01b_the_larger_central_person_is_chosen_whatever_the_order(performer_first: bool):
    small = (box(300, 700, 100, 250), 26)
    persons = [(PERFORMER, 26), small] if performer_first else [small, (PERFORMER, 26)]

    sel = select_target(pose_raw_from_boxes(_frames(*persons)))

    assert sel.person_row == (0 if performer_first else 1) and sel.bbox == pytest.approx(PERFORMER)
    assert sel.n_candidates == 2 and not sel.ambiguous and sel.runner_up_ratio < 0.2


def test_t_trk_01c_a_large_person_near_the_centre_beats_a_smaller_performer_and_is_flagged():
    """Worked out: performer 0.1013; a 500 x 900 person centred 460 px away: 0.2170 x (1 - 460 / 1101.5) = 0.1264."""
    bystander = box(500, 540, 500, 900)

    sel = select_target(pose_raw_from_boxes(_frames((PERFORMER, 26), (bystander, 26))))

    assert sel.person_row == 1 and sel.score == pytest.approx(0.2170 * (1 - 460 / HALF_DIAGONAL), abs=1e-4)
    assert sel.runner_up_ratio == pytest.approx(0.1013 / 0.1264, abs=2e-3) and sel.ambiguous


def test_t_trk_01c_the_same_person_at_the_edge_loses_and_is_not_a_close_call():
    edge = box(100, 540, 500, 900)  # centre 860 px away: score 0.2170 x (1 - 860 / 1101.5) = 0.0476

    sel = select_target(pose_raw_from_boxes(_frames((PERFORMER, 26), (edge, 26))))

    assert sel.person_row == 0 and sel.runner_up_ratio == pytest.approx(0.0476 / 0.1013, abs=2e-3) and not sel.ambiguous


@pytest.mark.parametrize(("ratio", "ambiguous"), [(0.55, False), (0.65, True), (1.0, True)])
def test_t_trk_01d_close_calls_are_flagged_from_a_ratio_of_0_6(ratio: float, ambiguous: bool):
    """Two people the same distance from the centre: the ratio of the scores is the ratio of the areas."""
    first = box(760, 540, 300, 700)
    second = box(1160, 540, 300, 700 * ratio)

    sel = select_target(pose_raw_from_boxes(_frames((first, 26), (second, 26))))

    assert sel.runner_up_ratio == pytest.approx(ratio, abs=1e-6) and sel.ambiguous is ambiguous
    assert sel.person_row == 0  # the larger one (equal scores: the lowest row)


def test_t_trk_01d_the_order_of_the_people_does_not_change_the_choice():
    a, b, c = (box(760, 540, 300, 700), 26), (box(1160, 540, 300, 630), 26), (box(300, 500, 150, 400), 26)
    chosen = set()
    for order in itertools.permutations([a, b, c]):
        sel = select_target(pose_raw_from_boxes(_frames(*order)))
        chosen.add(tuple(np.round(sel.bbox, 3)))
        assert sel.ambiguous and sel.n_candidates == 3
    assert chosen == {tuple(np.round(a[0], 3))}


def test_t_trk_01e_a_weak_person_is_never_chosen_by_default():
    weak_large = (box(960, 540, 600, 900), 3)
    sel = select_target(pose_raw_from_boxes(_frames(weak_large, (box(700, 540, 200, 500), 26))))

    assert sel.person_row == 1 and sel.n_candidates == 1 and not sel.ambiguous


def test_t_trk_01e_a_frame_of_weak_persons_only_is_an_error():
    with pytest.raises(TargetSelectionError, match="eligible"):
        select_target(pose_raw_from_boxes(_frames((PERFORMER, 5), (box(300, 500, 100, 250), 2))))


def test_t_trk_01f_when_nobody_is_at_the_start_the_search_goes_forward_only_as_far_as_search_s():
    frames = [[], [], [], [(PERFORMER, 26)], [(PERFORMER, 26)]]
    sel = select_target(pose_raw_from_boxes(frames, fps=30.0))
    assert sel.frame_pos == 3 and sel.offset_from_start_s == pytest.approx(0.1)

    late = [[] for _ in range(70)] + [[(PERFORMER, 26)]]  # first person at 2.33 s: beyond 2 s
    with pytest.raises(TargetSelectionError, match="eligible"):
        select_target(pose_raw_from_boxes(late, fps=30.0))
    assert select_target(pose_raw_from_boxes(late, fps=30.0), params=TargetParams(search_s=3.0)).frame_pos == 70


def test_t_trk_01f_the_search_never_goes_before_the_segment_start():
    frames = [[(PERFORMER, 26)], [(PERFORMER, 26)], [], [], []]  # persons only in the two margin frames

    with pytest.raises(TargetSelectionError, match="eligible"):
        select_target(pose_raw_from_boxes(frames, segment_start_pos=2))


def test_t_trk_01h_a_user_box_selects_the_person_with_the_largest_overlap_also_the_smaller_one():
    big, small = (PERFORMER, 26), (box(300, 700, 100, 250), 26)
    raw = pose_raw_from_boxes(_frames(big, small))
    sloppy = box(305, 695, 110, 270)  # a hand-drawn box around the small person

    sel = select_target(raw, bbox=sloppy)

    assert sel.method == "user_box" and sel.person_row == 1 and sel.bbox == pytest.approx(small[0])
    assert 0.5 < sel.score <= 1.0 and sel.n_candidates == 2 and not sel.weak


def test_t_trk_01h_a_weak_person_can_be_chosen_by_the_user_and_is_flagged():
    weak = box(300, 700, 100, 250)
    raw = pose_raw_from_boxes(_frames((PERFORMER, 26), (weak, 3)))

    sel = select_target(raw, bbox=weak)

    assert sel.person_row == 1 and sel.weak is True and sel.n_valid_keypoints == 3 and sel.score == pytest.approx(1.0)


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(box(1700, 200, 100, 100), id="matches_nobody"),
        pytest.param((float("nan"), 0.0, 10.0, 10.0), id="nan"),
        pytest.param((0.0, 0.0, float("inf"), 10.0), id="inf"),
        pytest.param((100.0, 100.0, 100.0, 200.0), id="zero_width"),
        pytest.param((200.0, 200.0, 100.0, 100.0), id="reversed"),
        pytest.param((1.0, 2.0, 3.0), id="three_values"),
    ],
)
def test_t_trk_01h_a_bad_or_unmatched_user_box_is_an_error_never_the_nearest_person(bad):
    raw = pose_raw_from_boxes(_frames((PERFORMER, 26)))

    with pytest.raises(TargetSelectionError):
        select_target(raw, bbox=bad)


def test_t_trk_01m_a_box_that_covers_two_close_people_is_refused():
    a, b = box(900, 540, 300, 700), box(1000, 540, 300, 700)
    raw = pose_raw_from_boxes(_frames((a, 26), (b, 26)))

    with pytest.raises(TargetSelectionError, match="two people"):
        select_target(raw, bbox=box(950, 540, 400, 700))  # IoU 0.75 with each
    sel = select_target(raw, bbox=a)  # IoU 1.0 with a, 0.5 with b: clear
    assert sel.person_row == 0 and sel.score == pytest.approx(1.0)


def test_t_trk_01i_at_t_sec_fixes_the_frame_and_does_not_search():
    left, right = box(400, 540, 300, 700), box(1500, 540, 300, 700)
    frames = [[(left, 26)]] * 3 + [[(right, 26)]] * 3 + [[]] * 2
    raw = pose_raw_from_boxes(frames, fps=30.0)

    assert select_target(raw).bbox == pytest.approx(left)
    on_frame_4 = select_target(raw, at_t_sec=4 / 30 + 0.01)  # within half a frame of frame 4
    assert (on_frame_4.frame_pos, on_frame_4.bbox) == (
        4,
        pytest.approx(right),
    ) and on_frame_4.offset_from_start_s == pytest.approx(4 / 30)
    assert select_target(raw, at_t_sec=1 / 30, bbox=left).frame_pos == 1
    with pytest.raises(TargetSelectionError, match="frame"):
        select_target(raw, at_t_sec=5.0)  # no frame there
    with pytest.raises(TargetSelectionError, match="eligible|person"):
        select_target(raw, at_t_sec=6 / 30)  # an empty frame: no search from it


def test_t_trk_01j_equal_scores_give_the_lowest_row_and_the_choice_is_deterministic_and_pure():
    a, b = box(760, 540, 300, 700), box(1160, 540, 300, 700)
    raw = pose_raw_from_boxes(_frames((a, 26), (b, 26)))
    before = {
        f.name: getattr(raw, f.name).tobytes()
        for f in dataclasses.fields(raw)
        if isinstance(getattr(raw, f.name), np.ndarray)
    }

    first, second = select_target(raw), select_target(raw)

    assert first == second and first.person_row == 0
    after = {name: getattr(raw, name).tobytes() for name in before}
    assert before == after  # the raw layer is not touched


@pytest.mark.parametrize("seed", range(5))
def test_t_trk_01k_syn_12_the_default_picks_the_distractor_and_says_so_the_user_box_picks_the_target(seed: int):
    """In SYN-12 the target (scale 1.0, x 700) is bigger but the distractor (0.95, x 1020) is more central."""
    raw, ids = pose_raw_from_scene(make_scene("SYN-12", seed=seed))

    default = select_target(raw)
    assert (
        ids[default.person_row] == 1 and default.ambiguous and default.runner_up_ratio == pytest.approx(0.896, abs=0.03)
    )

    target_row = int(np.flatnonzero((ids == 0) & (np.arange(ids.size) < raw.person_offsets[1]))[0])
    chosen = select_target(raw, bbox=tuple(float(v) for v in raw.bboxes[target_row]))
    assert ids[chosen.person_row] == 0 and chosen.score == pytest.approx(1.0)


@pytest.mark.parametrize("seed", range(5))
def test_t_trk_01k_syn_12_with_a_central_target_the_default_picks_the_target(seed: int):
    raw, ids = pose_raw_from_scene(make_scene("SYN-12", seed=seed, target_x0_px=960.0))

    default = select_target(raw)

    assert ids[default.person_row] == 0


def test_t_trk_01l_bad_parameters_and_a_segment_without_frames_are_refused():
    bad = [
        {"search_s": -1.0},
        {"search_s": math.nan},
        {"min_iou": 0.0},
        {"min_iou": 1.5},
        {"ambiguity_ratio": 0.0},
        {"ambiguity_ratio": 1.1},
        {"two_people_iou_ratio": 0.9},
    ]
    for kwargs in bad:
        with pytest.raises(ValueError):
            TargetParams(**kwargs)
    raw = pose_raw_from_boxes(_frames((PERFORMER, 26)))
    with pytest.raises(TargetSelectionError, match="frame"):
        select_target(dataclasses.replace(raw, segment_s=(100.0, 101.0)))


def test_t_trk_01h_a_small_person_inside_the_box_of_a_large_one_is_chosen_by_the_box_around_it():
    """IoU, not 'how much of the smaller box is covered': a box around the small person does not match the large one."""
    large, small = box(960, 540, 400, 900), box(960, 700, 80, 200)  # the small person stands in front of the large one
    raw = pose_raw_from_boxes(_frames((large, 26), (small, 26)))

    sel = select_target(raw, bbox=small)

    assert sel.person_row == 1 and sel.score == pytest.approx(1.0)


def test_t_trk_01d_a_ratio_exactly_at_the_limit_is_ambiguous():
    first, second = box(760, 540, 300, 700), box(1160, 540, 300, 350)  # exactly half the score

    sel = select_target(
        pose_raw_from_boxes(_frames((first, 26), (second, 26))), params=TargetParams(ambiguity_ratio=0.5)
    )

    assert sel.runner_up_ratio == 0.5 and sel.ambiguous


def test_t_trk_01d_when_every_score_is_zero_two_candidates_are_ambiguous_without_a_ratio():
    """Both centres at corners of the image: centrality 0, so the score is 0 for both (no 0 / 0)."""
    corners = [(box(0, 0, 100, 200), 26), (box(1920, 1080, 100, 200), 26)]

    two = select_target(pose_raw_from_boxes(_frames(*corners)))
    one = select_target(pose_raw_from_boxes(_frames(corners[0])))

    assert two.person_row == 0 and two.ambiguous and two.runner_up_ratio is None and two.score == 0.0
    assert not one.ambiguous and one.runner_up_ratio is None


def test_t_trk_01e_a_person_with_a_box_that_cannot_be_used_is_not_eligible():
    raw = pose_raw_from_boxes(_frames((PERFORMER, 26), (box(300, 500, 100, 250), 26)))
    bad = raw.bboxes.copy()
    bad[0::2] = np.nan  # the first person of every frame has a box of NaN but valid keypoints
    raw = dataclasses.replace(raw, bboxes=bad)

    sel = select_target(raw)

    assert sel.person_row == 1 and sel.n_candidates == 1 and sel.bbox == pytest.approx(box(300, 500, 100, 250))
    only_bad = dataclasses.replace(
        pose_raw_from_boxes(_frames((PERFORMER, 26))), bboxes=np.full((4, 4), np.nan, np.float32)
    )
    with pytest.raises(TargetSelectionError, match="eligible"):
        select_target(only_bad)


def test_t_trk_01i_a_time_far_from_every_frame_is_refused_as_such():
    raw = pose_raw_from_boxes(_frames((PERFORMER, 26), n=8), fps=30.0)

    with pytest.raises(TargetSelectionError, match="no frame near"):
        select_target(raw, at_t_sec=5.0)
    with pytest.raises(TargetSelectionError, match="finite"):
        select_target(raw, at_t_sec=float("nan"))
