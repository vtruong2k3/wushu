"""BUG-0079: a huge integer where a number is expected is a ``CompareError``, never an ``OverflowError``.

``float(10**400)`` raises ``OverflowError``; the checks of ``compare/dtw.py``, ``compare/features.py`` and
``compare/guards.py`` converted the argument before they judged it, so a caller who passed an integer beyond the range
of a float (a bad configuration, a unit mix-up) got a crash instead of the message that names the argument. The checks
of ``cost.py`` and ``reference_band.py`` already turn such an integer into an infinity; these tests hold the other three
to the same rule, for both signs, and check that the message stays short (it must not print the 400 digits).
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from helpers.metric_layers import body, layer_of
from taiji_ai.compare import CompareError
from taiji_ai.compare.cost import cost_matrix
from taiji_ai.compare.dtw import band_mask, dtw
from taiji_ai.compare.features import frame_features
from taiji_ai.compare.guards import check_comparable

BIG = 10**400  # far above the largest float (about 1.8e308)
BOTH_SIGNS = pytest.mark.parametrize("value", [BIG, -BIG], ids=["positive", "negative"])
MESSAGE_LIMIT = 400  # a message that printed the integer would be longer than this


def refused(call, argument: str) -> None:
    with pytest.raises(CompareError, match=argument) as raised:
        call()
    assert len(str(raised.value)) < MESSAGE_LIMIT


@BOTH_SIGNS
def test_bug_0079_dtw_refuses_a_huge_band(value):
    refused(lambda: dtw(np.zeros((3, 3)), band=value, step="symmetric1"), "band")
    refused(lambda: dtw(np.zeros((3, 3)), band=value, step="symmetricP1"), "band")
    refused(lambda: band_mask(3, 3, value), "band")


@BOTH_SIGNS
def test_bug_0079_features_refuses_a_huge_roll_or_minimum(value):
    layer = layer_of(body(12))
    refused(lambda: frame_features(layer, roll_deg=value), "roll_deg")
    refused(lambda: frame_features(layer, min_scale_s=value), "min_scale_s")
    refused(lambda: frame_features(layer, min_segment_length=value), "min_segment_length")


@BOTH_SIGNS
def test_bug_0079_guards_refuses_a_huge_coverage(value):
    # the settings are judged before the descriptions and the features are touched
    refused(
        lambda: check_comparable(None, None, None, None, min_visible=1, min_coverage=value),  # type: ignore[arg-type]
        "min_coverage",
    )


@BOTH_SIGNS
def test_bug_0080_cost_matrix_messages_stay_short_for_a_huge_integer(value):
    # cost.py already refused these (an integer beyond the float range becomes an infinity); its message printed the
    # whole integer (401 digits) until BUG-0080
    layer = layer_of(body(12))
    features = frame_features(layer)
    refused(lambda: cost_matrix(features, features, min_visible=value), "min_visible")
    unit = features.units[0].name
    refused(lambda: cost_matrix(features, features, min_visible=1, weights={unit: value}), "weights")
    if value < 0:
        refused(lambda: cost_matrix(features, features, min_visible=1, block_rows=value), "block_rows")


def test_bug_0080_a_huge_positive_block_is_a_valid_block():
    # a block of more rows than the segment has is the whole segment in one block: not a refusal, not a crash
    layer = layer_of(body(12))
    features = frame_features(layer)
    whole = cost_matrix(features, features, min_visible=1, block_rows=10**400)
    assert np.array_equal(whole.values, cost_matrix(features, features, min_visible=1).values)


def test_bug_0080_an_integer_that_a_float_holds_is_still_shown_as_it_is():
    layer = layer_of(body(12))
    features = frame_features(layer)
    with pytest.raises(CompareError, match=r"got 0\b"):
        cost_matrix(features, features, min_visible=0)
    with pytest.raises(CompareError, match=r"got -3\b"):
        cost_matrix(features, features, min_visible=-3)


def test_bug_0080_a_huge_integer_is_shown_with_its_own_sign():
    # the message of a huge integer keeps the sign (a negative one must not read as +inf), also inside the float range
    layer = layer_of(body(12))
    features = frame_features(layer)
    for value, text in ((-BIG, "-inf"), (-(10**20), "-1e+20"), (-(10**15), "-1000000000000000.0")):
        with pytest.raises(CompareError, match=rf"got {re.escape(text)}$"):
            cost_matrix(features, features, min_visible=value)
    with pytest.raises(CompareError, match=r"got -999999999999999$"):  # just below the limit: shown as an integer
        cost_matrix(features, features, min_visible=-(10**15 - 1))


@BOTH_SIGNS
def test_bug_0079_the_message_shows_an_infinity_with_the_sign_of_the_integer(value):
    # a refusal of 10**400 must not read "got 0.0" or lose the sign: the message says what was given
    shown = "inf" if value > 0 else "-inf"
    layer = layer_of(body(12))
    calls = {
        "dtw band": lambda: dtw(np.zeros((3, 3)), band=value, step="symmetric1"),
        "features roll": lambda: frame_features(layer, roll_deg=value),
        "features minimum": lambda: frame_features(layer, min_scale_s=value),
        "guards coverage": lambda: check_comparable(
            None,
            None,
            None,
            None,
            min_visible=1,
            min_coverage=value,  # type: ignore[arg-type]
        ),
    }
    for name, call in calls.items():
        with pytest.raises(CompareError, match=rf"got {re.escape(shown)}$") as raised:
            call()
        assert shown in str(raised.value), name


def test_bug_0079_an_integer_that_a_float_holds_is_shown_as_a_float_by_guards():
    # 10**20 is above the shown-integer limit (10**15) and inside the float range: shown as 1e+20, not as 21 digits
    with pytest.raises(CompareError, match=r"got 1e\+20$"):
        check_comparable(None, None, None, None, min_visible=1, min_coverage=10**20)  # type: ignore[arg-type]


def test_bug_0079_an_ordinary_large_integer_is_still_judged_by_its_value():
    layer = layer_of(body(12))
    assert frame_features(layer, min_scale_s=10**9).min_scale_s == 1e9  # representable: a minimum, not a refusal
    refused(lambda: dtw(np.zeros((3, 3)), band=2, step="symmetric1"), "band")  # above 1: refused as before
