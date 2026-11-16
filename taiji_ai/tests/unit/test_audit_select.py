"""T-AUDIT-02: which frames the review looks at: rank, spacing, merging, the blind sample (P3.08)."""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from taiji_ai.audit import AuditError
from taiji_ai.audit.select import BLIND, Rule, select_frames

N = 100  # one video at 10 fps: 10 s


def pooled(n: int = N, fps: float = 10.0, videos: tuple[str, ...] = ("d20-v1",)) -> dict:
    per = n // len(videos)
    return {
        "t_sec": np.concatenate([np.arange(per) / fps for _ in videos]),
        "video": [v for v in videos for _ in range(per)],
        "frame_index": np.concatenate([np.arange(per) for _ in videos]),
        "tracked": np.ones(per * len(videos), dtype=bool),
    }


def frames_of(candidates, rule: str) -> list[int]:
    return sorted(c.pos for c in candidates if rule in c.tags)


# --- T-AUDIT-02a: rank, spacing, merging, seed ----------------------------------------------------------------------
def test_t_audit_02a_a_rule_takes_its_worst_frames_at_least_the_gap_apart():
    score = np.arange(N, dtype=float)  # the later, the worse
    out = select_frames([Rule("r", score)], blind_k=0, k=5, min_gap_s=2.0, **pooled())
    assert frames_of(out, "r") == [19, 39, 59, 79, 99]  # 99, then 79: exactly 2.0 s apart is allowed
    fewer = select_frames([Rule("r", score)], blind_k=0, k=10, min_gap_s=2.0, **pooled())
    assert frames_of(fewer, "r") == [19, 39, 59, 79, 99]  # only five fit: never a duplicate or a frame too near


def test_t_audit_02a_the_direction_of_a_rule_is_respected():
    score = np.arange(N, dtype=float)
    low = select_frames([Rule("r", score, higher_is_worse=False)], blind_k=0, k=3, min_gap_s=2.0, **pooled())
    assert frames_of(low, "r") == [0, 20, 40]


def test_t_audit_02a_a_frame_that_two_rules_take_appears_once_with_both_tags_and_each_rule_keeps_its_k():
    score = np.arange(N, dtype=float)
    out = select_frames([Rule("a", score), Rule("b", score)], blind_k=0, k=3, min_gap_s=2.0, **pooled())
    assert len(out) == 3 and all(c.tags == ("a", "b") for c in out)
    assert frames_of(out, "a") == frames_of(out, "b") == [59, 79, 99]
    other = select_frames([Rule("a", score), Rule("b", score[::-1].copy())], blind_k=0, k=3, min_gap_s=2.0, **pooled())
    assert len(other) == 6 and len(frames_of(other, "a")) == 3 == len(frames_of(other, "b"))  # no overlap: 3 + 3


def test_t_audit_02a_ties_are_broken_by_the_seed_not_by_the_position():
    flat = np.ones(N)
    a1 = select_frames([Rule("r", flat)], blind_k=0, k=3, seed=1, **pooled())
    a2 = select_frames([Rule("r", flat)], blind_k=0, k=3, seed=1, **pooled())
    b = select_frames([Rule("r", flat)], blind_k=0, k=3, seed=2, **pooled())
    assert frames_of(a1, "r") == frames_of(a2, "r") and frames_of(a1, "r") != frames_of(b, "r")


def test_t_audit_02a_the_ids_follow_the_video_then_the_time_and_the_scores_are_kept():
    p = pooled(n=40, videos=("d20-v2", "d20-v1"))
    score = np.concatenate([np.arange(20.0), np.arange(20.0) + 100.0])  # the second block (d20-v1) is the worse one
    out = select_frames([Rule("r", score)], blind_k=0, k=4, min_gap_s=0.5, **p)
    assert [c.cid for c in out] == ["fc-001", "fc-002", "fc-003", "fc-004"]
    assert [c.video for c in out] == ["d20-v1", "d20-v1", "d20-v2", "d20-v2"]
    assert [c.frame_index for c in out] == [14, 19, 14, 19]
    assert all(c.t_sec == pytest.approx(c.frame_index / 10.0) for c in out)
    assert out[1].scores == {"r": 119.0} and out[1].tags == ("r",)


def test_t_audit_02a_every_video_gets_its_share_of_the_frames_of_a_rule():
    t = np.concatenate([np.arange(300) / 10.0, np.arange(100) / 10.0])  # 30 s and 10 s
    p = {
        "t_sec": t,
        "video": ["d20-v1"] * 300 + ["d20-v2"] * 100,
        "frame_index": np.concatenate([np.arange(300), np.arange(100)]),
        "tracked": np.ones(400, dtype=bool),
    }
    score = np.arange(400, dtype=float)  # the second video is the worse one all through
    out = select_frames([Rule("r", score)], blind_k=0, k=8, min_gap_s=0.5, **p)
    assert Counter(c.video for c in out) == {"d20-v1": 6, "d20-v2": 2}  # 3 : 1 as the time they cover
    even = select_frames(
        [Rule("r", score)], blind_k=0, k=8, min_gap_s=0.5, video_share={"d20-v1": 1.0, "d20-v2": 1.0}, **p
    )
    assert Counter(c.video for c in even) == {"d20-v1": 4, "d20-v2": 4}


def test_t_audit_02a_a_video_without_eligible_frames_hands_its_slots_to_the_others():
    t = np.concatenate([np.arange(300) / 10.0, np.arange(100) / 10.0])
    p = {
        "t_sec": t,
        "video": ["d20-v1"] * 300 + ["d20-v2"] * 100,
        "frame_index": np.concatenate([np.arange(300), np.arange(100)]),
        "tracked": np.ones(400, dtype=bool),
    }
    score = np.concatenate([np.arange(300, dtype=float), np.full(100, np.nan)])
    out = select_frames([Rule("r", score)], blind_k=0, k=8, min_gap_s=0.5, **p)
    assert len(out) == 8 and all(c.video == "d20-v1" for c in out)


# --- T-AUDIT-02b: the blind sample ----------------------------------------------------------------------------------
def test_t_audit_02b_the_blind_sample_avoids_taken_frames_and_their_neighbours_and_has_the_size_asked():
    p = pooled(n=1000, fps=10.0)  # 100 s
    score = np.arange(1000, dtype=float)
    out = select_frames([Rule("r", score)], k=5, blind_k=20, min_gap_s=2.0, **p)
    rule_frames = frames_of(out, "r")
    blind = sorted(c.pos for c in out if c.tags == (BLIND,))
    assert len(blind) == 20 and len(set(blind)) == 20
    everything = sorted(set(rule_frames) | set(blind))
    assert all(
        b2 - b1 >= 20 for b1, b2 in zip(everything, everything[1:], strict=False)
    )  # 2 s at 10 fps, for all of them
    assert all(c.scores == {BLIND: pytest.approx(float("nan"), nan_ok=True)} for c in out if c.tags == (BLIND,))


def test_t_audit_02b_only_tracked_frames_are_drawn_and_the_weights_decide_where():
    p = pooled(n=2000, videos=("d20-v1", "d20-v2"))  # 100 s each
    p["tracked"][:1000] = False  # nobody tracked in the first video
    out = select_frames([], blind_k=5, min_gap_s=2.0, **p)
    assert len(out) == 5 and all(c.video == "d20-v2" for c in out)
    weight = np.concatenate([np.ones(1000), np.zeros(1000)])
    p["tracked"][:] = True
    only_first = select_frames([], blind_k=5, min_gap_s=2.0, weight=weight, **p)
    assert len(only_first) == 5 and all(c.video == "d20-v1" for c in only_first)


def test_t_audit_02b_fewer_eligible_frames_than_asked_give_fewer_never_a_duplicate():
    p = pooled(n=100, fps=10.0)  # 10 s, a 2 s gap: at most 5 frames can be at least 2 s apart
    out = select_frames([], blind_k=40, min_gap_s=2.0, **p)
    assert 1 <= len(out) <= 5 and len({c.pos for c in out}) == len(out)


def test_t_audit_02b_the_sample_is_deterministic_for_a_seed():
    p = pooled(n=500)
    a = select_frames([], blind_k=10, seed=7, **p)
    b = select_frames([], blind_k=10, seed=7, **p)
    c = select_frames([], blind_k=10, seed=8, **p)
    assert [x.pos for x in a] == [x.pos for x in b] and [x.pos for x in a] != [x.pos for x in c]


# --- T-AUDIT-02c: NaN, empty rules, several videos, bad input -------------------------------------------------------
def test_t_audit_02c_nan_scores_are_never_selected_and_an_empty_rule_selects_nothing():
    score = np.full(N, np.nan)
    score[40] = 1.0
    out = select_frames([Rule("r", score), Rule("none", np.full(N, np.nan))], blind_k=0, k=5, **pooled())
    assert frames_of(out, "r") == [40] and frames_of(out, "none") == []


def test_t_audit_02c_the_gap_is_kept_within_a_video_and_not_between_videos():
    p = pooled(n=20, fps=10.0, videos=("d20-v1", "d20-v2"))
    score = np.array([0.0] * 9 + [5.0] + [0.0] * 9 + [5.0])  # frame 9 of each video is the worst, at the same time
    out = select_frames([Rule("r", score)], blind_k=0, k=2, min_gap_s=2.0, **p)
    assert {(c.video, c.frame_index) for c in out if "r" in c.tags} >= {("d20-v1", 9), ("d20-v2", 9)}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k": -1},
        {"blind_k": -1},
        {"min_gap_s": float("nan")},
        {"min_gap_s": -1.0},
    ],
)
def test_t_audit_02c_bad_numbers_are_refused(kwargs: dict):
    with pytest.raises(AuditError):
        select_frames([], **{"blind_k": 0, **kwargs}, **pooled())


def test_t_audit_02c_bad_shapes_and_names_are_refused():
    with pytest.raises(AuditError, match="same length"):
        select_frames(
            [], blind_k=0, t_sec=np.arange(3.0), video=["a", "b"], frame_index=np.arange(3), tracked=np.ones(3, bool)
        )
    with pytest.raises(AuditError, match="scores for"):
        select_frames([Rule("r", np.zeros(5))], blind_k=0, **pooled())
    with pytest.raises(AuditError, match="distinct"):
        select_frames([Rule("r", np.zeros(N)), Rule("r", np.zeros(N))], blind_k=0, **pooled())
    with pytest.raises(AuditError, match="distinct"):
        select_frames([Rule("blind", np.zeros(N))], blind_k=0, **pooled())
    with pytest.raises(AuditError, match="weight"):
        select_frames([], blind_k=1, weight=np.full(N, -1.0), **pooled())


# --- found by the mutation check ------------------------------------------------------------------------------------
def test_t_audit_02b_without_a_gap_the_blind_sample_still_avoids_the_chosen_frames():
    p = pooled(n=200)
    out = select_frames([Rule("r", np.arange(200, dtype=float))], k=5, blind_k=150, min_gap_s=0.0, **p)
    blind = [c.pos for c in out if c.tags == (BLIND,)]
    rule = [c.pos for c in out if c.tags == ("r",)]
    assert len(blind) == 150 and not set(blind) & set(rule) and len(set(blind)) == 150


def test_t_audit_02b_a_heavier_frame_is_drawn_first_not_just_a_frame_with_some_weight():
    p = pooled(n=4000, videos=("d20-v1", "d20-v2"))
    weight = np.concatenate([np.ones(2000), np.full(2000, 1000.0)])
    out = select_frames([], blind_k=5, min_gap_s=2.0, weight=weight, seed=3, **p)
    assert len(out) == 5 and all(c.video == "d20-v2" for c in out)
