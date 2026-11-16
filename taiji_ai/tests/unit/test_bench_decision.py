"""T-BENCH-06: the written rule that recommends the detector cadence N (P3.07).

The rule (task file P3.07, section 1, point 8): against N = 1, N is acceptable when the person-count agreement is at
least 99 %, the keypoint distance p95 is at most 0.01 body height and p99 at most 0.03, the ``tracked`` share of the
target is not lower than N = 1's by more than 0.5 percentage points, and no clip gets ``needs_reselect`` that N = 1 does
not have. The recommendation is the largest acceptable N, except that N = 10 beats N = 5 only if it is at least 15 %
faster in median elapsed time; if N = 5 is not acceptable it is N = 1.
"""

from __future__ import annotations

import dataclasses

import pytest

from taiji_ai.bench import BenchError
from taiji_ai.bench.decision import DecisionRule, NStats, recommend_n, speed_gain


def good(n: int, elapsed: float) -> NStats:
    return NStats(
        n=n,
        count_agreement=0.995,
        p95_norm=0.005,
        p99_norm=0.015,
        tracked_loss_points=0.1,
        new_needs_reselect=0,
        elapsed_median_s=elapsed,
    )


REF = NStats(
    n=1, count_agreement=1.0, p95_norm=0.0, p99_norm=0.0, tracked_loss_points=0.0, new_needs_reselect=0,
    elapsed_median_s=30.0,
)  # fmt: skip


def test_t_bench_06_speed_gain_is_the_share_of_time_saved():
    assert speed_gain(slow_s=10.0, fast_s=8.5) == pytest.approx(0.15)
    assert speed_gain(slow_s=10.0, fast_s=12.0) == pytest.approx(-0.2)
    with pytest.raises(BenchError):
        speed_gain(slow_s=0.0, fast_s=1.0)


def test_t_bench_06_n_10_failing_gives_5():
    bad10 = dataclasses.replace(good(10, 8.0), p95_norm=0.02)
    out = recommend_n([REF, good(5, 13.0), bad10])
    assert out.n == 5 and out.acceptable == {5: True, 10: False}
    assert any("p95" in reason for reason in out.reasons[10])


def test_t_bench_06_both_acceptable_n_10_wins_only_if_15_percent_faster_than_5():
    assert recommend_n([REF, good(5, 10.0), good(10, 8.5)]).n == 10  # exactly 15 %: inclusive
    out = recommend_n([REF, good(5, 10.0), good(10, 8.6)])
    assert out.n == 5 and out.speed_gain_vs_previous[10] == pytest.approx(0.14)
    assert recommend_n([REF, good(5, 10.0), good(10, 12.0)]).n == 5  # slower: no gain


def test_t_bench_06_n_5_failing_gives_1_even_if_n_10_looks_acceptable():
    bad5 = dataclasses.replace(good(5, 13.0), count_agreement=0.98)
    out = recommend_n([REF, bad5, good(10, 8.0)])
    assert out.n == 1 and out.acceptable[5] is False
    assert any("agreement" in reason for reason in out.reasons[5])


def test_t_bench_06_each_limit_is_inclusive_and_names_the_criterion_that_fails():
    rule = DecisionRule()
    cases = {
        "agreement": dataclasses.replace(good(5, 13.0), count_agreement=rule.min_count_agreement),
        "p95": dataclasses.replace(good(5, 13.0), p95_norm=rule.max_p95_norm),
        "p99": dataclasses.replace(good(5, 13.0), p99_norm=rule.max_p99_norm),
        "tracked": dataclasses.replace(good(5, 13.0), tracked_loss_points=rule.max_tracked_loss_points),
    }
    for name, stats in cases.items():
        assert recommend_n([REF, stats]).n == 5, name  # at the limit: acceptable
    just_over = {
        "agreement": dataclasses.replace(good(5, 13.0), count_agreement=rule.min_count_agreement - 1e-6),
        "p95": dataclasses.replace(good(5, 13.0), p95_norm=rule.max_p95_norm + 1e-9),
        "p99": dataclasses.replace(good(5, 13.0), p99_norm=rule.max_p99_norm + 1e-9),
        "tracked": dataclasses.replace(good(5, 13.0), tracked_loss_points=rule.max_tracked_loss_points + 1e-9),
        "reselect": dataclasses.replace(good(5, 13.0), new_needs_reselect=1),
    }
    for name, stats in just_over.items():
        out = recommend_n([REF, stats])
        assert out.n == 1 and not out.acceptable[5], name
        assert len(out.reasons[5]) == 1 and name in out.reasons[5][0], (name, out.reasons[5])


def test_t_bench_06_several_reasons_are_all_given():
    stats = dataclasses.replace(good(5, 13.0), count_agreement=0.9, p95_norm=0.05, new_needs_reselect=2)
    assert len(recommend_n([REF, stats]).reasons[5]) == 3


def test_t_bench_06_missing_distances_are_not_acceptable_and_say_so():
    stats = dataclasses.replace(good(5, 13.0), p95_norm=None, p99_norm=None)  # no keypoint pairs were compared
    out = recommend_n([REF, stats])
    assert out.n == 1 and any("no keypoint" in reason for reason in out.reasons[5])


def test_t_bench_06_only_n_1_gives_n_1_and_the_input_is_checked():
    assert recommend_n([REF]).n == 1
    with pytest.raises(BenchError, match="N = 1"):
        recommend_n([good(5, 13.0)])
    with pytest.raises(BenchError, match="twice"):
        recommend_n([REF, good(5, 13.0), good(5, 12.0)])
    with pytest.raises(BenchError):
        recommend_n([])


def test_t_bench_06_the_rule_validates_its_numbers():
    assert DecisionRule() == DecisionRule(0.99, 0.01, 0.03, 0.5, 0.15)
    for bad in (
        {"min_count_agreement": 1.5},
        {"min_count_agreement": 0.0},
        {"max_p95_norm": -0.1},
        {"max_p99_norm": 0.001},  # below p95: impossible to satisfy both
        {"max_tracked_loss_points": -1.0},
        {"min_speed_gain": 1.0},
        {"min_speed_gain": float("nan")},
    ):
        with pytest.raises(ValueError):
            DecisionRule(**bad)


def test_t_bench_06_the_speed_brake_is_inclusive_whatever_the_rounding_of_the_gain():
    gain = speed_gain(10.0, 8.5)
    rule = DecisionRule(min_speed_gain=gain)  # exactly the gain of N = 10 over N = 5
    assert recommend_n([REF, good(5, 10.0), good(10, 8.5)], rule).n == 10


def test_t_bench_06_the_first_acceptable_n_is_taken_even_if_it_saves_little_time():
    assert recommend_n([REF, good(5, 29.0)]).n == 5  # 3 % faster than N = 1: the brake is for the later steps


def test_t_bench_06_an_unknown_tracked_share_is_not_acceptable_and_is_not_taken_as_zero():
    stats = dataclasses.replace(good(5, 13.0), tracked_loss_points=None)  # no clip had a target in both runs
    out = recommend_n([REF, stats])
    assert out.n == 1 and not out.acceptable[5]
    assert (
        len(out.reasons[5]) == 1
        and "tracked share" in out.reasons[5][0]
        and "could not be compared" in out.reasons[5][0]
    )
