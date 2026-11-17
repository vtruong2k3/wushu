"""T-DET-06: the rule of the detector comparison, written before any measurement (DEC-0043, task P3.09).

A is the shipping detector (YOLOX), B the candidate (YOLO11). The rule is a function so that it is applied as written:

* (R) recall of B on the labelled frames higher than A's by 3 points or more, with exact McNemar p under 0.05;
* (C) in the reviewed runs where only one detector finds a person, B right and A wrong in at least 5 more runs than
  the reverse;
* either one makes B materially better; neither, with both evaluable, means A stays; a criterion that cannot be
  evaluated and no other that is met means "no decision", never silently "no gap";
* stability and speed never decide: stability is a supporting reason (p95 of 1 minus IoU at most 0.7 times A's, recall
  of B not lower) or a note.
"""

from __future__ import annotations

import pytest

from taiji_ai.bench.detector_metrics import CReview, DetectorRule, PairedRecall, decide


def paired(n: int, only_a: int, only_b: int, both: int | None = None) -> PairedRecall:
    both = n - only_a - only_b if both is None else both
    return PairedRecall(n_positive=n, both=both, only_a=only_a, only_b=only_b)


def c_review(b_better: int, a_better: int, discordant: int | None = None, reviewed: int | None = None) -> CReview:
    d = b_better + a_better + 3 if discordant is None else discordant
    return CReview(n_discordant=d, n_reviewed=d if reviewed is None else reviewed, b_better=b_better, a_better=a_better)


RULE = DetectorRule()
NO_STAB = (None, None)


def test_t_det_06_the_default_values_are_the_ones_written_before_the_measurement():
    r = DetectorRule()
    assert (r.min_recall_gain_points, r.max_p, r.min_frame_gain, r.stability_ratio, r.min_positives) == (
        3.0,
        0.05,
        5,
        0.7,
        20,
    )
    # 0.65 is the limit of the NonMaxSuppression node of the shipping graph (BUG-0073: it was 0.45 until the read-back)
    assert (r.matched_score_limit, r.matched_nms_iou) == (0.3, 0.65)


def test_t_det_06_recall_gain_of_three_points_with_a_small_p_makes_b_materially_better():
    # 100 frames; B finds 9 that A misses and A finds 1 that B misses: gain 8 points, p = 0.0215
    d = decide(RULE, paired(100, only_a=1, only_b=9), c_review(0, 0), NO_STAB)
    assert d.outcome == "materially_better" and d.criterion == "R"


@pytest.mark.parametrize(
    ("only_b", "met"),
    [
        (3, False),  # exactly 3 points, but p = 0.25: the test does not agree
        (5, False),  # 5 points, p = 0.0625: over the limit
        (6, True),  # 6 points, p = 0.03125
    ],
)
def test_t_det_06_both_the_gain_and_the_p_value_are_needed(only_b: int, met: bool):
    d = decide(RULE, paired(100, only_a=0, only_b=only_b), c_review(0, 0), NO_STAB)
    assert (d.outcome == "materially_better") is met


def test_t_det_06_a_gain_of_2_9_points_is_not_enough_and_3_0_points_is():
    # n = 1000: 29 frames is 2.9 points (p tiny), 30 frames is 3.0 points
    below = decide(RULE, paired(1000, only_a=0, only_b=29), c_review(0, 0), NO_STAB)
    at = decide(RULE, paired(1000, only_a=0, only_b=30), c_review(0, 0), NO_STAB)
    assert below.outcome == "not_materially_better" and at.outcome == "materially_better"


def test_t_det_06_p_exactly_at_the_limit_is_not_under_it():
    # (5, 0) has p = 0.0625 exactly and a gain of 5 points
    at_limit = decide(DetectorRule(max_p=0.0625), paired(100, only_a=0, only_b=5), c_review(0, 0), NO_STAB)
    over_limit = decide(DetectorRule(max_p=0.0626), paired(100, only_a=0, only_b=5), c_review(0, 0), NO_STAB)
    assert at_limit.outcome == "not_materially_better" and over_limit.outcome == "materially_better"


def test_t_det_06_five_more_frames_on_the_reviewed_disagreements_is_the_second_criterion():
    four = decide(RULE, paired(100, 0, 0), c_review(b_better=7, a_better=3), NO_STAB)  # 4 more
    five = decide(RULE, paired(100, 0, 0), c_review(b_better=8, a_better=3), NO_STAB)  # 5 more
    assert four.outcome == "not_materially_better"
    assert five.outcome == "materially_better" and five.criterion == "C"


def test_t_det_06_both_criteria_are_named_together():
    d = decide(RULE, paired(100, only_a=0, only_b=9), c_review(10, 0), NO_STAB)
    assert d.outcome == "materially_better" and d.criterion == "R and C"


def test_t_det_06_a_detector_that_is_better_in_the_other_direction_does_not_count():
    d = decide(RULE, paired(100, only_a=9, only_b=0), c_review(0, 10), NO_STAB)
    assert d.outcome == "not_materially_better"


def test_t_det_06_stability_never_decides_alone():
    stab = (0.20, 0.10)  # p95 of 1 minus IoU: A 0.20, B 0.10 (half): well under 0.7 times
    d = decide(RULE, paired(100, 0, 0), c_review(0, 0), stab)
    assert d.outcome == "not_materially_better" and d.criterion is None
    assert any("stability" in r.lower() for r in d.reasons)  # but it is noted


def test_t_det_06_stability_is_a_supporting_reason_only_with_no_recall_loss_and_at_the_ratio():
    def reasons(stab: tuple[float, float], only_a: int, only_b: int) -> list[str]:
        return decide(RULE, paired(100, only_a, only_b), c_review(0, 0), stab).reasons

    assert any("supports" in r for r in reasons((0.20, 0.14), 0, 9))  # 0.14 = 0.7 x 0.20: at the ratio counts
    assert not any("supports" in r for r in reasons((0.20, 0.15), 0, 9))  # 0.75 x: no
    assert not any("supports" in r for r in reasons((0.20, 0.10), 9, 0))  # B finds fewer: a recall loss


def test_t_det_06_speed_and_memory_are_not_inputs():
    import inspect

    assert set(inspect.signature(decide).parameters) == {"rule", "recall", "review", "stability"}


def test_t_det_06_too_few_positive_frames_cannot_evaluate_recall_and_say_so():
    d = decide(RULE, paired(19, only_a=0, only_b=9), c_review(0, 0), NO_STAB)
    assert d.outcome == "no_decision" and any("fewer than 20" in r for r in d.reasons)


def test_t_det_06_a_met_criterion_decides_even_if_the_other_cannot_be_evaluated():
    d = decide(RULE, paired(19, 0, 9), c_review(8, 1), NO_STAB)  # R not evaluable, C met
    assert d.outcome == "materially_better" and d.criterion == "C"
    d2 = decide(RULE, paired(100, 0, 9), None, NO_STAB)  # C not evaluated, R met
    assert d2.outcome == "materially_better" and d2.criterion == "R"


def test_t_det_06_no_review_of_the_disagreements_is_no_decision_when_recall_is_not_met():
    d = decide(RULE, paired(100, 0, 1), None, NO_STAB)
    assert d.outcome == "no_decision" and any("review" in r.lower() for r in d.reasons)
    d2 = decide(RULE, paired(100, 0, 1), c_review(0, 0, discordant=12, reviewed=0), NO_STAB)  # due but not done
    assert d2.outcome == "no_decision"


def test_t_det_06_no_disagreement_at_all_is_an_evaluated_c_and_not_a_gap():
    d = decide(RULE, paired(100, 0, 1), CReview(n_discordant=0, n_reviewed=0, b_better=0, a_better=0), NO_STAB)
    assert d.outcome == "not_materially_better"


def test_t_det_06_the_decision_names_its_numbers():
    d = decide(RULE, paired(100, only_a=1, only_b=9), c_review(2, 1), (0.2, 0.1))
    text = " ".join(d.reasons)
    for expected in ("8.0", "0.021", "reviewed", "p95"):
        assert expected in text, expected


def test_t_det_06_exactly_the_minimum_number_of_positive_frames_can_be_evaluated():
    d = decide(RULE, paired(20, only_a=0, only_b=10), c_review(0, 0), NO_STAB)
    assert d.outcome == "materially_better" and d.criterion == "R"  # 10 of 20: 50 points, p = 0.002
    assert decide(RULE, paired(19, 0, 10), c_review(0, 0), NO_STAB).outcome == "no_decision"
