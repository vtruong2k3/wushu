"""T-SYNC-04e: ``match_flashes`` pairs the flashes of one window one to one, in time order (X.23, BUG-0064).

A time mapping wrong by one pair gap (1 s) sends the first flash of A onto the second flash of B. Matching to the
closest flash, ignoring flashes without a partner and averaging the distances let that pass; none of those is allowed.
"""

from __future__ import annotations

import pytest

from taiji_ai.io.flash import match_flashes


def _plus(lag_s: float):
    return lambda t: t + lag_s


def test_t_sync_04e_a_perfect_pair_has_zero_residual():
    assert match_flashes([2.0, 3.0], [2.5, 3.5], _plus(0.5)) == pytest.approx(0.0, abs=1e-9)


def test_t_sync_04e_the_residual_is_the_largest_distance_not_the_mean():
    # distances 0 ms and 100 ms: the mean (50 ms) would hide the bad flash
    assert match_flashes([2.0, 3.0], [2.5, 3.6], _plus(0.5)) == pytest.approx(100.0)


@pytest.mark.parametrize("wrong_lag_s", [1.5, -0.5], ids=["plus_one_pair_gap", "minus_one_pair_gap"])
def test_t_sync_04e_a_lag_wrong_by_one_pair_gap_is_not_a_perfect_match(wrong_lag_s: float):
    """With the right count, the first flash of A is compared with the first of B, so the 1 s error shows."""
    residual = match_flashes([2.0, 3.0], [2.5, 3.5], _plus(wrong_lag_s))
    assert residual is not None
    assert residual == pytest.approx(1000.0)


@pytest.mark.parametrize(
    ("onsets_a", "onsets_b"),
    [
        pytest.param([2.0, 3.0], [2.5], id="b_missed_one"),
        pytest.param([2.0], [2.5, 3.5], id="a_missed_one"),
        pytest.param([2.0, 3.0], [2.5, 3.5, 4.0], id="b_has_a_third_flash"),
        pytest.param([2.0, 3.0, 4.0], [2.5, 3.5], id="a_has_a_third_flash"),
    ],
)
def test_t_sync_04e_different_counts_cannot_be_judged(onsets_a: list[float], onsets_b: list[float]):
    assert match_flashes(onsets_a, onsets_b, _plus(0.5)) is None


@pytest.mark.parametrize(
    ("onsets_a", "onsets_b"),
    [
        pytest.param([], [], id="none"),
        pytest.param([2.0], [], id="only_a"),
        pytest.param([], [2.5], id="only_b"),
        pytest.param([2.0], [2.5], id="one_flash_each"),
    ],
)
def test_t_sync_04e_fewer_than_two_flashes_cannot_be_judged(onsets_a: list[float], onsets_b: list[float]):
    """One flash each cannot be told from its neighbour in the pair (they may be different flashes of the pair)."""
    assert match_flashes(onsets_a, onsets_b, _plus(0.5)) is None


def test_t_sync_04e_min_flashes_is_a_parameter():
    assert match_flashes([2.0], [2.5], _plus(0.5), min_flashes=1) == pytest.approx(0.0, abs=1e-9)
    assert match_flashes([2.0, 3.0], [2.5, 3.5], _plus(0.5), min_flashes=3) is None
    assert match_flashes([], [], _plus(0.5), min_flashes=0) is None  # no flash is never a residual of 0


def test_t_sync_04e_the_order_of_the_input_does_not_matter():
    assert match_flashes([3.0, 2.0], [2.5, 3.5], _plus(0.5)) == pytest.approx(0.0, abs=1e-9)
    assert match_flashes([2.0, 3.0], [3.5, 2.5], _plus(0.5)) == pytest.approx(0.0, abs=1e-9)


def test_t_sync_04e_a_mapping_with_drift_and_a_negative_lag():
    def a_to_b(t: float) -> float:
        return t - 0.7 + 200e-6 * (t - 10.0)

    onsets_a = [12.0, 13.0]
    onsets_b = [a_to_b(t) + 0.002 for t in onsets_a]  # B is 2 ms later than the mapping says
    assert match_flashes(onsets_a, onsets_b, a_to_b) == pytest.approx(2.0, abs=1e-6)
