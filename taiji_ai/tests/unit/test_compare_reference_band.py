"""T-CMP-08a to T-CMP-08h: the "normal band" from several reference takes and the trainee's place against it (P6.06;
W8 and Appendix C.5).

The module works on plain values: ``Comparison`` records made by hand here, with no DTW. Every number below is derived
by hand in a comment or by ``middle`` (a sorted list and an index), which shares nothing with the module's code.
``distance`` is ``D`` of an alignment (the plain mean cost, overview section 3.3); the module never reads
``normalised``.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
import random

import numpy as np
import pytest

from taiji_ai.compare import CompareError
from taiji_ai.compare.reference_band import Comparison, ReferenceBand, reference_band

SETTINGS = {
    "band": 0.2,
    "step": "symmetricP1",
    "min_visible": 8,
    "feature_version": "features/1",
    "weights": (1.0, 1.0),
}
A, B, C, D = "ref_a", "ref_b", "ref_c", "ref_d"
TRAINEE = "trainee_1"
# three references: pairs ab = 1, ac = 4, bc = 2 (sorted 1, 2, 4)
THREE = {(A, B): 1.0, (A, C): 4.0, (B, C): 2.0}
FIELDS = {
    "status",
    "references",
    "n_pairs",
    "n_pairs_without_path",
    "band_low",
    "band_median",
    "band_high",
    "trainee_distances",
    "trainee_value",
    "position",
    "ratio_to_high",
}


def comparison(reference_id, query_id, distance, settings=None) -> Comparison:
    return Comparison(
        reference_id=reference_id,
        query_id=query_id,
        distance=distance,
        settings=dict(SETTINGS if settings is None else settings),
    )


def between(distances, settings=None) -> list[Comparison]:
    """The pairs of the references: ``{(first, second): distance}``."""
    return [comparison(a, b, d, settings) for (a, b), d in distances.items()]


def trainee_of(distances, trainee_id=TRAINEE, settings=None) -> list[Comparison]:
    """The trainee against each reference: ``{reference: distance}``."""
    return [comparison(r, trainee_id, d, settings) for r, d in distances.items()]


def all_pairs(names, value) -> dict:
    """Every pair of ``names`` with the distance ``value(first, second)``."""
    return {(a, b): value(a, b) for i, a in enumerate(names) for b in names[i + 1 :]}


def middle(values):
    """The median by hand: the middle of the sorted list, or the mean of the two middle ones."""
    ordered = sorted(values)
    half = len(ordered) // 2
    return ordered[half] if len(ordered) % 2 else (ordered[half - 1] + ordered[half]) / 2


def refused(between_references, trainee, *needles) -> str:
    """The call is refused with a ``CompareError``; every needle is in the message. Returns the message."""
    with pytest.raises(CompareError) as error:
        reference_band(between_references, trainee)
    message = str(error.value)
    for needle in needles:
        assert needle in message, (needle, message)
    return message


# --- T-CMP-08a: the band and the value on hand-made distances --------------------------------------------------------
def test_t_cmp_08a_three_references_the_band_is_min_median_max_of_the_three_pairs_and_the_value_the_median_of_three():
    # pairs 1, 4, 2 -> sorted 1, 2, 4: band 1 to 4, median 2; trainee 3, 5, 1 -> sorted 1, 3, 5: value 3, inside
    result = reference_band(between(THREE), trainee_of({A: 3.0, B: 5.0, C: 1.0}))
    assert isinstance(result, ReferenceBand)
    assert result.status == "ok"
    assert result.references == (A, B, C)
    assert (result.n_pairs, result.n_pairs_without_path) == (3, 0)
    assert (result.band_low, result.band_median, result.band_high) == (1.0, 2.0, 4.0)
    assert result.trainee_distances == (3.0, 5.0, 1.0)  # in the order of the references
    assert result.trainee_value == 3.0
    assert result.position == "within"
    assert result.ratio_to_high == 3.0 / 4.0


def test_t_cmp_08a_four_references_the_median_of_six_pairs_is_the_mean_of_the_two_middle_ones():
    # ab 0.5, ac 1.5, ad 1.0, bc 2.5, bd 2.0, cd 3.0 -> sorted 0.5 1.0 1.5 2.0 2.5 3.0: low 0.5, median (1.5 + 2.0) / 2,
    # high 3.0. Trainee 1.0, 2.0, 3.0, 4.0 -> value (2.0 + 3.0) / 2 = 2.5, inside, 2.5 / 3.0 of the top
    pairs = {(A, B): 0.5, (A, C): 1.5, (A, D): 1.0, (B, C): 2.5, (B, D): 2.0, (C, D): 3.0}
    result = reference_band(between(pairs), trainee_of({A: 1.0, B: 2.0, C: 3.0, D: 4.0}))
    assert result.status == "ok" and result.references == (A, B, C, D)
    assert (result.n_pairs, result.n_pairs_without_path) == (6, 0)
    assert (result.band_low, result.band_median, result.band_high) == (0.5, 1.75, 3.0)
    assert result.trainee_value == 2.5 and result.position == "within"
    assert result.ratio_to_high == pytest.approx(2.5 / 3.0, rel=1e-12)


def test_t_cmp_08a_the_value_is_the_median_of_the_trainee_distances_not_their_smallest_or_their_mean():
    # trainee 0.2, 1.0, 9.0: the smallest 0.2 would be below the band 1 to 4, the mean 3.4 inside it, the largest 9
    # above: the median 1.0 is on its low edge
    result = reference_band(between(THREE), trainee_of({A: 9.0, B: 0.2, C: 1.0}))
    assert result.trainee_value == 1.0 and result.position == "within"
    # trainee 0.2, 0.4, 9.0: the median 0.4 is below although the mean (3.2) is inside the band
    result = reference_band(between(THREE), trainee_of({A: 9.0, B: 0.2, C: 0.4}))
    assert result.trainee_value == 0.4 and result.position == "below"


def test_t_cmp_08a_the_band_is_made_of_the_pairs_only_never_of_the_trainee():
    low = reference_band(between(THREE), trainee_of({A: 0.0, B: 0.0, C: 0.0}))
    high = reference_band(between(THREE), trainee_of({A: 99.0, B: 99.0, C: 99.0}))
    for result in (low, high):
        assert (result.band_low, result.band_median, result.band_high) == (1.0, 2.0, 4.0)
        assert result.n_pairs == 3


def test_t_cmp_08a_the_order_and_the_direction_of_the_inputs_do_not_change_the_result():
    expected = reference_band(between(THREE), trainee_of({A: 3.0, B: 5.0, C: 1.0}))
    reversed_pairs = [comparison(b, a, d) for (a, b), d in reversed(list(THREE.items()))]  # (b, a) and another order
    shuffled_trainee = trainee_of({C: 1.0, A: 3.0, B: 5.0})
    assert reference_band(reversed_pairs, shuffled_trainee) == expected
    assert reference_band(tuple(reversed_pairs), tuple(shuffled_trainee)) == expected  # tuples are sequences too


def test_t_cmp_08a_random_complete_sets_equal_the_hand_derivation_and_every_status_is_met():
    rng = random.Random(20261117)
    seen = {"ok": 0, "insufficient_references": 0, "no_trainee_distance": 0}
    positions = set()
    for _ in range(400):
        names = [f"r{n}" for n in range(rng.randint(0, 6))]
        pair_none, trainee_none = rng.choice([0.0, 0.0, 0.3, 0.8, 1.0]), rng.choice([0.0, 0.0, 0.3, 0.8, 1.0])

        def draw(chance_none):
            return None if rng.random() < chance_none else round(rng.uniform(0.0, 5.0), 3)

        pair_values = all_pairs(names, lambda a, b, chance=pair_none: draw(chance))
        trainee_values = {r: draw(trainee_none) for r in names}
        pairs = [comparison(*sorted(pair, reverse=rng.random() < 0.5), d) for pair, d in pair_values.items()]
        rng.shuffle(pairs)
        trainee = trainee_of(trainee_values)
        rng.shuffle(trainee)
        got = reference_band(pairs, trainee)

        finite_pairs = [d for d in pair_values.values() if d is not None]
        finite_trainee = [d for d in trainee_values.values() if d is not None]
        assert got.references == tuple(sorted(names))
        assert got.n_pairs == len(names) * (len(names) - 1) // 2
        assert got.n_pairs_without_path == got.n_pairs - len(finite_pairs)
        assert got.trainee_distances == tuple(trainee_values[r] for r in sorted(names))
        if not finite_pairs:
            assert got.status == "insufficient_references"
            assert (got.band_low, got.band_median, got.band_high) == (None, None, None)
            assert got.position is None and got.ratio_to_high is None
        else:
            assert got.band_low == min(finite_pairs) and got.band_high == max(finite_pairs)
            assert got.band_median == pytest.approx(middle(finite_pairs), rel=1e-12, abs=1e-12)
            if not finite_trainee:
                assert got.status == "no_trainee_distance"
                assert got.trainee_value is None and got.position is None and got.ratio_to_high is None
            else:
                value = middle(finite_trainee)
                assert got.status == "ok" and got.trainee_value == pytest.approx(value, rel=1e-12, abs=1e-12)
                want = "below" if value < min(finite_pairs) else "above" if value > max(finite_pairs) else "within"
                assert got.position == want
                top = max(finite_pairs)
                assert got.ratio_to_high == (pytest.approx(value / top, rel=1e-12) if top > 0 else None)
                positions.add(got.position)
        seen[got.status] += 1
    assert all(count >= 20 for count in seen.values()), seen  # the cases are not all one kind
    assert positions == {"below", "within", "above"}


# --- T-CMP-08b: one reference is not enough ---------------------------------------------------------------------------
def test_t_cmp_08b_one_reference_says_not_enough_and_gives_no_band_position_or_ratio():
    result = reference_band([], trainee_of({A: 2.0}))
    assert result.status == "insufficient_references"
    assert result.references == (A,)
    assert (result.n_pairs, result.n_pairs_without_path) == (0, 0)
    assert (result.band_low, result.band_median, result.band_high) == (None, None, None)
    assert result.position is None and result.ratio_to_high is None
    assert result.trainee_distances == (2.0,) and result.trainee_value == 2.0  # what the trainee's comparison says


def test_t_cmp_08b_no_reference_at_all_is_not_enough_either():
    result = reference_band([], [])
    assert result.status == "insufficient_references"
    assert result.references == () and result.trainee_distances == ()
    assert (result.n_pairs, result.n_pairs_without_path) == (0, 0)
    assert result.band_low is None and result.trainee_value is None and result.position is None


def test_t_cmp_08b_two_references_give_a_band_of_one_pair():
    result = reference_band(between({(A, B): 1.5}), trainee_of({A: 1.0, B: 2.5}))
    assert result.status == "ok" and result.references == (A, B)
    assert (result.n_pairs, result.n_pairs_without_path) == (1, 0)
    assert (result.band_low, result.band_median, result.band_high) == (1.5, 1.5, 1.5)
    assert result.trainee_value == 1.75 and result.position == "above"  # (1.0 + 2.5) / 2, above the band 1.5 to 1.5
    assert result.ratio_to_high == pytest.approx(1.75 / 1.5, rel=1e-12)
    flat = reference_band(between({(A, B): 1.5}), trainee_of({A: 1.5, B: 1.5}))
    assert flat.position == "within" and flat.ratio_to_high == 1.0


def test_t_cmp_08b_a_trainee_distance_with_one_reference_is_not_put_against_a_band():
    # the trainee's number is still reported (it is an observation) but no position or ratio comes with it
    result = reference_band([], trainee_of({A: 0.0}))
    assert result.status == "insufficient_references"
    assert result.trainee_value == 0.0  # zero is a distance, not a missing value
    assert result.position is None and result.ratio_to_high is None


# --- T-CMP-08c: the position and the ratio ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "position", "ratio"),
    [
        (0.0, "below", 0.0),
        (0.5, "below", 0.125),  # 0.5 / 4
        (1.0, "within", 0.25),  # exactly the smallest distance between the references
        (2.5, "within", 0.625),
        (4.0, "within", 1.0),  # exactly the largest
        (4.5, "above", 1.125),
        (8.0, "above", 2.0),
    ],
)
def test_t_cmp_08c_below_within_at_both_ends_exactly_and_above_with_the_ratio_to_the_top(value, position, ratio):
    # the band is 1 to 4; every trainee distance is the value, so the median is the value
    result = reference_band(between(THREE), trainee_of({A: value, B: value, C: value}))
    assert result.status == "ok" and result.trainee_value == value
    assert result.position == position
    assert result.ratio_to_high == ratio


def test_t_cmp_08c_one_step_of_float_precision_outside_the_band_is_outside():
    below = float(np.nextafter(1.0, 0.0))
    above = float(np.nextafter(4.0, 5.0))
    assert reference_band(between(THREE), trainee_of({A: below, B: below, C: below})).position == "below"
    assert reference_band(between(THREE), trainee_of({A: above, B: above, C: above})).position == "above"
    assert reference_band(between(THREE), trainee_of({A: 1.0, B: 1.0, C: 1.0})).position == "within"
    assert reference_band(between(THREE), trainee_of({A: 4.0, B: 4.0, C: 4.0})).position == "within"


def test_t_cmp_08c_the_ratio_is_none_when_the_top_of_the_band_is_zero_identical_references():
    pairs = between({(A, B): 0.0})  # the two references are identical
    same = reference_band(pairs, trainee_of({A: 0.0, B: 0.0}))
    assert same.status == "ok" and same.band_high == 0.0 and same.position == "within"
    assert same.ratio_to_high is None  # 0 / 0 is not a number
    far = reference_band(pairs, trainee_of({A: 1.5, B: 1.5}))
    assert far.position == "above" and far.ratio_to_high is None  # and 1.5 / 0 is not one either
    assert far.trainee_value == 1.5 and far.band_low == 0.0


def test_t_cmp_08c_a_zero_distance_in_the_band_is_a_distance_not_a_missing_one():
    pairs = {(A, B): 0.0, (A, C): 3.0, (B, C): 1.0}  # sorted 0, 1, 3
    result = reference_band(between(pairs), trainee_of({A: 0.0, B: 0.0, C: 0.0}))
    assert (result.band_low, result.band_median, result.band_high) == (0.0, 1.0, 3.0)
    assert result.n_pairs_without_path == 0
    assert result.trainee_value == 0.0 and result.position == "within" and result.ratio_to_high == 0.0


# --- T-CMP-08d: no path -----------------------------------------------------------------------------------------------
def test_t_cmp_08d_a_pair_without_a_path_is_left_out_and_counted():
    # ab has no path: the band is made of ac = 4 and bc = 2 (low 2, median (2 + 4) / 2 = 3, high 4)
    result = reference_band(between({(A, B): None, (A, C): 4.0, (B, C): 2.0}), trainee_of({A: 3.0, B: 3.0, C: 3.0}))
    assert result.status == "ok"
    assert (result.n_pairs, result.n_pairs_without_path) == (3, 1)
    assert (result.band_low, result.band_median, result.band_high) == (2.0, 3.0, 4.0)
    assert result.position == "within"


def test_t_cmp_08d_a_trainee_distance_without_a_path_is_left_out_but_kept_in_its_place():
    # trainee None, 2.0, 5.0: the value is (2 + 5) / 2 = 3.5 and the tuple keeps the None where the reference is
    result = reference_band(between(THREE), trainee_of({A: None, B: 2.0, C: 5.0}))
    assert result.status == "ok"
    assert result.trainee_distances == (None, 2.0, 5.0)
    assert result.trainee_value == 3.5 and result.position == "within"
    one = reference_band(between(THREE), trainee_of({A: None, B: None, C: 6.0}))
    assert one.trainee_distances == (None, None, 6.0) and one.trainee_value == 6.0 and one.position == "above"


def test_t_cmp_08d_every_pair_without_a_path_is_insufficient_references_whatever_the_trainee_has():
    none_pairs = {pair: None for pair in THREE}
    result = reference_band(between(none_pairs), trainee_of({A: 1.0, B: 2.0, C: 3.0}))
    assert result.status == "insufficient_references"
    assert (result.n_pairs, result.n_pairs_without_path) == (3, 3)
    assert (result.band_low, result.band_median, result.band_high) == (None, None, None)
    assert result.position is None and result.ratio_to_high is None
    assert result.references == (A, B, C) and result.trainee_distances == (1.0, 2.0, 3.0)
    both = reference_band(between(none_pairs), trainee_of({A: None, B: None, C: None}))
    # the band comes first: with no band the trainee has nothing to meet
    assert both.status == "insufficient_references" and both.trainee_value is None


def test_t_cmp_08d_every_trainee_distance_without_a_path_is_no_trainee_distance_with_the_band_kept():
    result = reference_band(between(THREE), trainee_of({A: None, B: None, C: None}))
    assert result.status == "no_trainee_distance"
    assert (result.band_low, result.band_median, result.band_high) == (1.0, 2.0, 4.0)
    assert (result.n_pairs, result.n_pairs_without_path) == (3, 0)
    assert result.trainee_distances == (None, None, None)
    assert result.trainee_value is None and result.position is None and result.ratio_to_high is None


def test_t_cmp_08d_a_single_finite_pair_among_missing_ones_still_makes_a_band_of_one_pair():
    pairs = {(A, B): None, (A, C): 2.5, (B, C): None}
    result = reference_band(between(pairs), trainee_of({A: 2.5, B: 2.5, C: 2.5}))
    assert result.status == "ok" and (result.n_pairs, result.n_pairs_without_path) == (3, 2)
    assert (result.band_low, result.band_median, result.band_high) == (2.5, 2.5, 2.5)
    assert result.position == "within"


# --- T-CMP-08e: incomplete or repeated pairs, the trainee's comparisons -----------------------------------------------
def test_t_cmp_08e_an_incomplete_set_of_pairs_is_refused_naming_the_missing_pair():
    pairs = {(A, B): 1.0, (A, C): 4.0}  # bc is missing
    message = refused(between(pairs), trainee_of({A: 1.0, B: 1.0, C: 1.0}), B, C, "pair")
    assert A not in message  # only the missing pair is named
    assert "more" not in message  # and it is the only one
    # four references with only the chain ab, bc, cd: ac is the first missing pair in sorted order
    chain = {(A, B): 1.0, (B, C): 1.0, (C, D): 1.0}
    refused(between(chain), trainee_of({A: 1.0, B: 1.0, C: 1.0, D: 1.0}), A, C, "pair")


def test_t_cmp_08e_a_pair_given_twice_in_either_direction_is_refused_with_the_ids():
    twice = between(THREE) + between({(A, B): 1.0})
    refused(twice, trainee_of({A: 1.0, B: 1.0, C: 1.0}), A, B, "between_references[3]")
    back = between(THREE) + [comparison(B, A, 1.0)]
    refused(back, trainee_of({A: 1.0, B: 1.0, C: 1.0}), A, B, "between_references[3]")


def test_t_cmp_08e_a_pair_that_repeats_with_the_same_distance_is_still_refused():
    pairs = between({(A, B): 1.0}) * 2
    refused(pairs, trainee_of({A: 1.0, B: 1.0}), A, B, "between_references[1]")


def test_t_cmp_08e_a_trainee_that_misses_a_reference_is_refused_naming_it():
    message = refused(between(THREE), trainee_of({A: 1.0, B: 1.0}), C, "trainee")
    assert "more" not in message and A not in message and B not in message
    message = refused(between(THREE), trainee_of({B: 1.0}), A, "trainee", "1 more")  # a and c are absent
    assert B not in message
    refused(between(THREE), [], A, "trainee", "2 more")  # no comparison at all, with references present


def test_t_cmp_08e_a_trainee_compared_twice_with_a_reference_is_refused_naming_it():
    twice = trainee_of({A: 1.0, B: 1.0, C: 1.0}) + trainee_of({B: 2.0})
    refused(between(THREE), twice, B, "trainee[3]")


def test_t_cmp_08e_a_trainee_compared_with_a_reference_that_no_pair_has_is_refused_as_a_missing_pair():
    # d is compared with the trainee but no pair holds it: ad, bd and cd are missing (the first in sorted order is ad)
    message = refused(between(THREE), trainee_of({A: 1.0, B: 1.0, C: 1.0, D: 1.0}), A, D, "pair")
    assert "2 more" in message


def test_t_cmp_08e_a_trainee_whose_id_is_a_reference_is_refused():
    refused(between(THREE), [comparison(B, A, 1.0), comparison(C, A, 1.0)], A, "trainee", "one of the references")
    # a trainee whose comparisons carry different ids is two segments, not one
    mixed = [comparison(A, TRAINEE, 1.0), comparison(B, "trainee_2", 1.0), comparison(C, TRAINEE, 1.0)]
    refused(between(THREE), mixed, TRAINEE, "trainee_2", "trainee[1]")


def test_t_cmp_08e_a_comparison_of_a_segment_with_itself_is_refused():
    refused([comparison(A, A, 1.0)], [], A, "between_references[0]")
    refused([], [comparison(A, A, 1.0)], A, "trainee[0]")


def test_t_cmp_08e_the_arguments_must_be_sequences_of_comparisons():
    for bad in (None, "", "SECRET text", b"", b"SECRET", 5, {"a": 1}, (c for c in between(THREE)), np.zeros(3)):
        assert "SECRET" not in refused(bad, trainee_of({A: 1.0}), "between_references")
        assert "SECRET" not in refused([], bad, "trainee")
    refused([comparison(A, B, 1.0), "not a comparison"], [], "between_references[1]", "str")
    refused([], [{"reference_id": A}], "trainee[0]", "dict")
    assert "SECRET" not in refused([comparison(A, B, 1.0), "SECRET item"], [], "between_references[1]")


@pytest.mark.parametrize(
    "bad",
    [float("nan"), float("inf"), float("-inf"), -0.5, -3, 10**400, -(10**400), True, False, "1.0", 1 + 2j, [1.0]],
    ids=["nan", "inf", "-inf", "-0.5", "-3", "huge", "-huge", "True", "False", "text", "complex", "list"],
)
def test_t_cmp_08e_a_distance_must_be_none_or_a_finite_number_of_at_least_zero(bad):
    pairs = between(THREE)
    pairs[1] = comparison(A, C, bad)
    refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "between_references[1].distance")
    pairs[1] = comparison(A, C, "SECRET text")
    assert "SECRET" not in refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "between_references[1].distance")
    trainee = trainee_of({A: 1.0, B: 1.0, C: 1.0})
    trainee[2] = comparison(C, TRAINEE, bad)
    refused(between(THREE), trainee, "trainee[2].distance")


def test_t_cmp_08e_distances_given_as_integers_or_numpy_numbers_come_back_as_floats():
    pairs = between({(A, B): 2, (A, C): np.float32(4.0), (B, C): np.int64(3)})
    result = reference_band(pairs, trainee_of({A: np.float64(1), B: 2, C: np.float32(3.0)}))
    assert result.status == "ok"
    for number in (result.band_low, result.band_median, result.band_high, result.trainee_value, result.ratio_to_high):
        assert type(number) is float
    assert all(type(number) is float for number in result.trainee_distances)
    assert (result.band_low, result.band_median, result.band_high) == (2.0, 3.0, 4.0)
    assert result.trainee_distances == (1.0, 2.0, 3.0) and result.trainee_value == 2.0


# --- T-CMP-08f: settings must be the same everywhere ------------------------------------------------------------------
def with_setting(**changes) -> dict:
    return {**SETTINGS, **changes}


def test_t_cmp_08f_settings_that_differ_in_a_pair_are_refused_naming_the_setting():
    pairs = between(THREE)
    pairs[2] = comparison(B, C, 2.0, with_setting(band=0.3))
    message = refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "between_references[2]", "band")
    assert "between_references[0]" in message  # what it differs from
    for name in ("step", "min_visible", "feature_version"):
        assert name not in message  # only the setting that differs is named


def test_t_cmp_08f_settings_that_differ_in_the_trainees_comparison_are_refused():
    trainee = trainee_of({A: 1.0, B: 1.0, C: 1.0})
    trainee[1] = comparison(B, TRAINEE, 1.0, with_setting(step="symmetric1"))
    refused(between(THREE), trainee, "trainee[1]", "step")


def test_t_cmp_08f_a_trainee_made_with_other_settings_than_a_single_pair_is_refused():
    trainee = [comparison(A, TRAINEE, 1.0), comparison(B, TRAINEE, 1.0, with_setting(min_visible=9))]
    refused([comparison(A, B, 1.0)], trainee, "trainee[1]", "between_references[0]", "min_visible")
    refused([], trainee, "trainee[1]", "trainee[0]", "min_visible")  # with no pair it differs from the trainee's first


def test_t_cmp_08f_every_setting_that_differs_is_named_in_sorted_order():
    pairs = between(THREE)
    pairs[1] = comparison(A, C, 4.0, with_setting(step="symmetric1", band=0.4, min_visible=3))
    message = refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "band", "min_visible", "step")
    assert message.index("band") < message.index("min_visible") < message.index("step")
    assert "feature_version" not in message and "weights" not in message
    everything = {"step": "x", "band": 0.9, "min_visible": 1, "feature_version": "x", "weights": (2.0,)}
    pairs[1] = comparison(A, C, 4.0, everything)
    message = refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "band", "feature_version", "weights")
    names = [message.index(name) for name in ("band", "feature_version", "min_visible", "step", "weights")]
    assert names == sorted(names)  # all five, in alphabetical order


def test_t_cmp_08f_a_setting_that_one_comparison_has_and_another_lacks_is_a_difference():
    fewer = {key: value for key, value in SETTINGS.items() if key != "min_visible"}
    pairs = between(THREE)
    pairs[1] = comparison(A, C, 4.0, fewer)
    refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "min_visible")
    pairs[1] = comparison(A, C, 4.0, with_setting(extra_setting=1))
    refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "extra_setting")


def test_t_cmp_08f_settings_equal_by_value_are_accepted_whatever_the_objects():
    pairs = [comparison(a, b, d, dict(SETTINGS)) for (a, b), d in THREE.items()]  # a new dict each time
    trainee = [comparison(r, TRAINEE, 1.0, with_setting(band=0.2, min_visible=8.0)) for r in (A, B, C)]  # 8 == 8.0
    assert reference_band(pairs, trainee).status == "ok"


def test_t_cmp_08f_settings_that_hold_sequences_mappings_and_arrays_are_compared_by_value():
    rich = {
        "weights": (1.0, 2.0, 3.0),
        "units": ["hand", "foot"],
        "nested": {"a": (1, 2), "b": np.array([1.0, 2.0])},
        "groups": [(1, 2), (3, 4)],
    }

    def run(second, trainee_settings=None):
        pairs = [comparison(A, B, 1.0, rich), comparison(A, C, 1.0, rich), comparison(B, C, 1.0, second)]
        return reference_band(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}, settings=trainee_settings or rich))

    same = {
        "weights": [1.0, 2.0, 3.0],
        "units": ("hand", "foot"),
        "nested": {"a": [1, 2], "b": np.array([1.0, 2.0])},
        "groups": [[1, 2], [3, 4]],
    }
    assert run(same).status == "ok"  # a list and a tuple of the same items are the same setting (a JSON round trip)
    assert run({**same, "groups": [np.array([1, 2]), (3, 4)]}).status == "ok"  # an array in a sequence is by value
    for changes, name in (
        ({"weights": (1.0, 2.0, 3.5)}, "weights"),
        ({"weights": (1.0, 2.0)}, "weights"),
        ({"units": ["hand"]}, "units"),
        ({"nested": {"a": (1, 3), "b": np.array([1.0, 2.0])}}, "nested"),
        ({"nested": {"a": (1, 2), "b": np.array([1.0, 2.5])}}, "nested"),
        ({"nested": {"a": (1, 2), "b": np.array([1.0, 2.0, 3.0])}}, "nested"),
        ({"nested": {"a": (1, 2)}}, "nested"),
        ({"nested": {"a": (1, 2), "b": np.array([1.0, 2.0]), "c": 1}}, "nested"),
        ({"nested": 5}, "nested"),  # a mapping in one, a number in the other
        ({"nested": None}, "nested"),
        ({"weights": 1.0}, "weights"),  # a sequence in one, a number in the other
        ({"weights": "text"}, "weights"),
        ({"units": None}, "units"),
        ({"groups": [(1, 2), (3, 5)]}, "groups"),  # a difference inside a sequence of sequences
        ({"groups": [[1, 2]]}, "groups"),
        ({"groups": [np.array([1, 2]), (3, 5)]}, "groups"),
    ):
        with pytest.raises(CompareError, match=name):
            run({**same, **changes})
    # an array against a list or a tuple of the same numbers is the same setting, against other numbers it is not
    for kind in (list, tuple, np.array):
        assert run({**same, "nested": {"a": (1, 2), "b": kind([1.0, 2.0])}}).status == "ok"
        with pytest.raises(CompareError, match="nested"):
            run({**same, "nested": {"a": (1, 2), "b": kind([1.0, 2.1])}})
        with pytest.raises(CompareError, match="nested"):
            run({**same, "nested": {"a": (1, 2), "b": kind([1.0])}})
    only_list = {**same, "nested": {"a": (1, 2), "b": [1.0, 2.0]}}  # the first has the array, this one the list
    assert (
        reference_band(
            [comparison(A, B, 1.0, only_list), comparison(A, C, 1.0, rich), comparison(B, C, 1.0, rich)],
            trainee_of({A: 1.0, B: 1.0, C: 1.0}, settings=rich),
        ).status
        == "ok"
    )
    with pytest.raises(CompareError, match="nested"):  # and the first has the list, the later one the array
        reference_band(
            [
                comparison(A, B, 1.0, only_list),
                comparison(A, C, 1.0, only_list),
                comparison(B, C, 1.0, rich | {"nested": {"a": (1, 2), "b": np.array([9.0, 9.0])}}),
            ],
            trainee_of({A: 1.0, B: 1.0, C: 1.0}, settings=only_list),
        )


def test_t_cmp_08f_settings_must_be_a_non_empty_mapping_with_short_code_names():
    for bad in (None, [], {}, [("band", 0.2)], "band", "SECRET settings", 3):
        pairs = between(THREE)
        pairs[0] = Comparison(reference_id=A, query_id=B, distance=1.0, settings=bad)
        message = refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "between_references[0].settings must be")
        assert "non-empty mapping" in message and "SECRET" not in message
    # settings that are empty everywhere would make the equality check vacuous: refused, not "equal"
    empty = [Comparison(reference_id=a, query_id=b, distance=d, settings={}) for (a, b), d in THREE.items()]
    refused(empty, [], "between_references[0].settings", "non-empty mapping")
    refused([], [Comparison(reference_id=A, query_id=TRAINEE, distance=1.0, settings={})], "trainee[0].settings")
    for name in ("two words", "a/b", 5, "", "x" * 65, "SECRET\n"):
        pairs = between(THREE)
        pairs[0] = Comparison(reference_id=A, query_id=B, distance=1.0, settings={**SETTINGS, name: 1})
        message = refused(pairs, trainee_of({A: 1.0, B: 1.0, C: 1.0}), "between_references[0].settings")
        assert "SECRET" not in message and "two words" not in message and "a/b" not in message


# --- T-CMP-08g: the ids are short codes and are never logged ----------------------------------------------------------
BAD_IDS = [
    "",
    "has some SECRET spaces",
    "D:/videos/SECRET.mp4",
    "C:\\Users\\SECRET\\take.mp4",
    "../SECRET",
    "/home/SECRET",
    "SECRET\n",
    "ref\t1",
    "x" * 65,
    "caf\u00e9",
    "a/b",
    "ref:1",
    "ref\\1",
    "ref 1",
    "ref\x01",
    5,
    None,
    b"ref",
    ("a",),
]


def broken(where, field, bad):
    """A valid call with one id replaced by ``bad``: ``(between, trainee)``."""
    pairs, trainee = between(THREE), trainee_of({A: 1.0, B: 1.0, C: 1.0})
    target = pairs if where == "between_references" else trainee
    target[0] = dataclasses.replace(target[0], **{field: bad})
    return pairs, trainee


@pytest.mark.parametrize("field", ["reference_id", "query_id"])
@pytest.mark.parametrize("where", ["between_references", "trainee"])
@pytest.mark.parametrize("bad", BAD_IDS, ids=[f"bad{n}" for n in range(len(BAD_IDS))])
def test_t_cmp_08g_an_id_that_is_not_a_short_code_is_refused_and_never_echoed(where, field, bad):
    pairs, trainee = broken(where, field, bad)
    message = refused(pairs, trainee, f"{where}[0].{field}", "short code")
    assert "SECRET" not in message
    if isinstance(bad, str) and bad:
        assert bad not in message


def test_t_cmp_08g_short_codes_up_to_64_characters_of_letters_digits_underscore_dot_and_dash_are_accepted():
    names = ["P01", "ref_a.take-2", "A" * 64, "0", "seg.12-b_C"]
    pairs = between(all_pairs(names, lambda a, b: 1.0))
    result = reference_band(pairs, trainee_of({n: 1.0 for n in names}, trainee_id="t" * 64))
    assert result.status == "ok" and result.references == tuple(sorted(names))


def test_t_cmp_08g_nothing_is_logged_by_a_result_or_a_refusal(caplog):
    caplog.set_level(logging.DEBUG)
    reference_band(between(THREE), trainee_of({A: 1.0, B: 2.0, C: 3.0}))
    reference_band([], [])
    pairs, trainee = broken("trainee", "query_id", "D:/videos/SECRET.mp4")
    with pytest.raises(CompareError):
        reference_band(pairs, trainee)
    with pytest.raises(CompareError):
        reference_band(between({(A, B): 1.0, (A, C): 1.0}), trainee_of({A: 1.0, B: 1.0, C: 1.0}))
    assert caplog.records == []  # no log line at all, so no id can be in one
    assert "SECRET" not in caplog.text


# --- T-CMP-08h: no score, no label, the inputs are unchanged ----------------------------------------------------------
def test_t_cmp_08h_the_result_holds_the_description_and_no_score_or_label():
    names = {field.name for field in dataclasses.fields(ReferenceBand)}
    assert names == FIELDS
    for word in ("score", "grade", "label", "verdict", "good", "bad", "pass", "fail", "rating", "percent"):
        assert not any(word in name for name in names), word
    for pairs, trainee in (
        (THREE, {A: 0.1, B: 0.1, C: 0.1}),
        (THREE, {A: 2.0, B: 2.0, C: 2.0}),
        (THREE, {A: 50.0, B: 50.0, C: 50.0}),
    ):
        result = reference_band(between(pairs), trainee_of(trainee))
        assert result.status in {"ok", "insufficient_references", "no_trainee_distance"}
        assert result.position in {"below", "within", "above"}
        assert result.ratio_to_high is not None and result.ratio_to_high == result.trainee_value / result.band_high
    # a ratio to the top of the band, not a score: it is not capped at 1 or at 100 and it never rounds to a grade
    far = reference_band(between(THREE), trainee_of({A: 1000.0, B: 1000.0, C: 1000.0}))
    assert far.ratio_to_high == 250.0 and far.position == "above"
    near = reference_band(between(THREE), trainee_of({A: 1.0001, B: 1.0001, C: 1.0001}))
    assert near.ratio_to_high == pytest.approx(0.250025, rel=1e-12) and near.trainee_value == 1.0001


def test_t_cmp_08h_the_result_is_frozen_and_holds_tuples():
    result = reference_band(between(THREE), trainee_of({A: 3.0, B: 5.0, C: 1.0}))
    assert isinstance(result.references, tuple) and isinstance(result.trainee_distances, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.position = "above"  # type: ignore[misc]
    record = comparison(A, B, 1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.distance = 2.0  # type: ignore[misc]
    assert {field.name for field in dataclasses.fields(Comparison)} == {
        "reference_id",
        "query_id",
        "distance",
        "settings",
    }


def test_t_cmp_08h_the_inputs_are_unchanged_and_a_call_is_repeatable():
    pairs = between(THREE)
    pairs.reverse()
    trainee = trainee_of({C: 1.0, A: 3.0, B: 5.0})
    pairs_before, trainee_before = copy.deepcopy(pairs), copy.deepcopy(trainee)
    identities = [id(c) for c in pairs], [id(c) for c in trainee]
    first = reference_band(pairs, trainee)
    assert pairs == pairs_before and trainee == trainee_before  # same records, same order, same settings
    assert ([id(c) for c in pairs], [id(c) for c in trainee]) == identities
    assert reference_band(pairs, trainee) == first


def test_t_cmp_08h_a_refused_call_changes_nothing_either():
    pairs = between({(A, B): 1.0, (A, C): 1.0})
    trainee = trainee_of({A: 1.0, B: 1.0, C: 1.0})
    before = copy.deepcopy(pairs), copy.deepcopy(trainee)
    with pytest.raises(CompareError):
        reference_band(pairs, trainee)
    assert (pairs, trainee) == before
