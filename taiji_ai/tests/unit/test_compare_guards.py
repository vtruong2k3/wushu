"""T-CMP-07a to 07h: the guards of a comparison (P6.05, W8): the same action, side, variant and view, no blocking flag,
and enough coverage on both segments; otherwise a decision that lists every reason.

Every expected number is derived by hand from what the test builds, never with the module's helpers. The features are
built so that the number of valid units of each row is known by construction (``feats``: row ``r`` has ``counts[r]``
valid units), and one test goes through the real ``frame_features`` of a layer with a known pattern of lost joints
(12 positions and 9 angles are 21 units; a lost wrist loses its position and the angle of its forearm: 2 units).
Coverage is the share of rows with at least ``min_visible`` valid units: with ``min_visible = 3`` the counts
``[4, 3, 3, 2, 4, 1, 0, 3, 3, 4]`` have seven such rows of ten, 0.7.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
import pytest

from helpers.metric_layers import RECORDING_ID, SOURCES, body, cells, drop, edited, exact_layer
from taiji_ai.compare import CompareError, guards
from taiji_ai.compare.features import FeatureUnit, FrameFeatures, frame_features
from taiji_ai.compare.guards import BLOCKING_FLAGS, GuardDecision, SegmentInfo, check_comparable
from taiji_ai.pose.skeleton import IDX
from taiji_ai.schemas.ontology import Ontology, load_ontology, parse_ontology

JOINTS = (
    "LShoulder", "RShoulder", "LElbow", "RElbow", "LWrist", "RWrist",
    "LHip", "RHip", "LKnee", "RKnee", "LAnkle", "RAnkle",
)  # fmt: skip
MIN_VISIBLE = 3
MIN_COVERAGE = 0.7


# --- builders ---------------------------------------------------------------------------------------------------------
def features_of(valid: np.ndarray) -> FrameFeatures:
    """A ``FrameFeatures`` by hand whose ``valid`` is the given ``(N, U)`` bool array (``U`` at most 12)."""
    n, u = valid.shape
    values = np.full((n, u, 2), np.nan)
    values[valid] = 0.5
    arrays = {
        "t_sec": np.arange(n, dtype=np.float64) / 30.0,
        "values": values,
        "valid": valid.copy(),
        "reason": np.where(valid, 0, 1).astype(np.uint8),
        "bridged": np.zeros((n, u), dtype=bool),
    }
    for a in arrays.values():
        a.setflags(write=False)
    return FrameFeatures(
        **arrays,
        units=tuple(FeatureUnit("position", name, (IDX[name],)) for name in JOINTS[:u]),
        scale_px=150.0,
        scale_rows=n,
        scale_s=n / 30.0,
        roll_deg=0.0,
        step_s=1 / 30.0 if n > 1 else None,
        recording_id=RECORDING_ID,
        data_sources=SOURCES,
        version="1",
    )


def feats(counts: list[int], units: int = 4) -> FrameFeatures:
    """Row ``r`` has ``counts[r]`` valid units (the first ones) out of ``units``; ``[]`` is a segment without rows."""
    valid = np.zeros((len(counts), units), dtype=bool)
    for r, count in enumerate(counts):
        valid[r, :count] = True
    return features_of(valid)


def info(
    action: str = "A02",
    side: str = "left",
    variant: str = "taiji24/v0",
    view: str = "front",
    flags: tuple[str, ...] = (),
) -> SegmentInfo:
    return SegmentInfo(action=action, side=side, variant=variant, view_category=view, flags=frozenset(flags))


GOOD = feats([4] * 10)  # ten rows, every unit valid
COUNTS = [4, 3, 3, 2, 4, 1, 0, 3, 3, 4]


def decide(
    reference: Any = None,
    query: Any = None,
    reference_features: Any = GOOD,
    query_features: Any = GOOD,
    **kwargs: Any,
) -> GuardDecision:
    kwargs.setdefault("min_visible", MIN_VISIBLE)
    kwargs.setdefault("min_coverage", MIN_COVERAGE)
    return check_comparable(
        info() if reference is None else reference,
        info() if query is None else query,
        reference_features,
        query_features,
        **kwargs,
    )


def reasons_of(reference: Any = None, query: Any = None, **kwargs: Any) -> tuple[str, ...]:
    return decide(reference, query, **kwargs).reasons


def small_ontology() -> Ontology:
    """A made-up ontology: the action ``A99`` exists (the shipped one stops at A24), the flag ``blur`` is new, and the
    view list has no ``back``."""
    action = {"technique": "t", "name_en": "e", "name_zh": "z", "name_vi": "v", "repetitions": 1}
    return parse_ontology(
        {
            "schema_version": "ontology/1",
            "ontology_version": "v9",
            "form": {"id": "demo", "name_en": "Demo", "expected_actions": 2, "status": "draft_unconfirmed"},
            "sides": ["left", "right", "none"],
            "view_categories": ["front", "side", "unknown"],
            "flags": ["orientation_change", "occlusion", "perspective_shift", "blur"],
            "actions": [
                {"id": "A01", "slug": "one", "sides": ["none"], **action},
                {"id": "A99", "slug": "last", "sides": ["left", "right"], **action},
            ],
        }
    )


# --- T-CMP-07a: the same description and enough coverage --------------------------------------------------------------
def test_t_cmp_07a_same_description_with_enough_coverage_is_comparable() -> None:
    d = decide()
    assert d.comparable is True
    assert d.reasons == ()
    assert (d.coverage_reference, d.coverage_query) == (1.0, 1.0)


_PAIRS = [(a.id, side) for a in load_ontology().actions for side in a.sides]


@pytest.mark.parametrize(("action", "side"), _PAIRS)
def test_t_cmp_07a_every_action_and_side_of_the_ontology_is_comparable_with_itself(action: str, side: str) -> None:
    d = decide(info(action=action, side=side), info(action=action, side=side))
    assert d.comparable is True and d.reasons == ()


def test_t_cmp_07a_the_ontology_has_the_pairs_the_parametrization_needs() -> None:
    assert ("A01", "none") in _PAIRS and ("A02", "left") in _PAIRS and ("A02", "right") in _PAIRS
    assert ("A07", "left") in _PAIRS and ("A08", "right") in _PAIRS and len(_PAIRS) > 24


@pytest.mark.parametrize("view", ["front", "side", "oblique", "back"])
def test_t_cmp_07a_a_known_view_is_comparable_with_itself(view: str) -> None:
    assert decide(info(view=view), info(view=view)).reasons == ()


def test_t_cmp_07a_a_variant_without_a_slash_and_a_long_one_are_variants() -> None:
    assert decide(info(variant="taiji24"), info(variant="taiji24")).reasons == ()
    longest = "a" * 64 + "/" + "b" * 64
    assert decide(info(variant=longest), info(variant=longest)).reasons == ()


@pytest.mark.parametrize(
    "variant", ["Ab_9.x-y/Zz_0.1-2", "A", "z", "9", "_", ".", "-", "taiji-24.b/v_0", "a/b", "x" * 64, "0/0"]
)
def test_t_cmp_07a_a_variant_may_use_letters_digits_underscore_dot_and_hyphen_in_both_parts(variant: str) -> None:
    assert decide(info(variant=variant), info(variant=variant)).reasons == ()


def test_t_cmp_07a_real_features_with_every_unit_valid_are_comparable() -> None:
    f = frame_features(exact_layer(body(40, 400.0), segment=(5, 35)))
    assert f.valid.shape == (30, 21)  # 12 positions and 9 angles
    d = decide(reference_features=f, query_features=f, min_visible=21, min_coverage=1.0)
    assert d.comparable is True and d.reasons == () and (d.coverage_reference, d.coverage_query) == (1.0, 1.0)


# --- T-CMP-07b: another action, side, variant or view, each alone -----------------------------------------------------
@pytest.mark.parametrize(
    ("reference", "query", "expected"),
    [
        (info("A02", "left"), info("A04", "left"), ("action_differs",)),  # two alternating movements, same side
        (info("A01", "none"), info("A03", "none"), ("action_differs",)),  # two movements without a side
        (info("A09", "none"), info("A11", "none"), ("action_differs",)),  # one technique under two numbers: Q1
        (info("A02", "left"), info("A02", "right"), ("side_differs",)),
        (info("A06", "right"), info("A06", "left"), ("side_differs",)),
        (info(variant="taiji24/v0"), info(variant="taiji24/v1"), ("variant_differs",)),
        (info(variant="taiji24/v0"), info(variant="bafa/v0"), ("variant_differs",)),
        (info(variant="taiji24"), info(variant="taiji24/v0"), ("variant_differs",)),
        (info(view="front"), info(view="side"), ("view_differs",)),
        (info(view="front"), info(view="oblique"), ("view_differs",)),
        (info(view="back"), info(view="front"), ("view_differs",)),
        (info(view="side"), info(view="oblique"), ("view_differs",)),
    ],
)
def test_t_cmp_07b_each_difference_alone_gives_its_one_reason(
    reference: SegmentInfo, query: SegmentInfo, expected: tuple[str, ...]
) -> None:
    d = decide(reference, query)
    assert d.comparable is False
    assert d.reasons == expected
    assert (d.coverage_reference, d.coverage_query) == (1.0, 1.0)  # the data was fine: a description refused it
    assert decide(query, reference).reasons == expected  # the same either way round


def test_t_cmp_07b_the_other_number_of_a_technique_with_the_other_side_gives_both_reasons() -> None:
    # A07 (left) and A08 (right) are one technique under two numbers, and the side differs too
    assert reasons_of(info("A07", "left"), info("A08", "right")) == ("action_differs", "side_differs")


# --- T-CMP-07c: a view unknown is never compared ----------------------------------------------------------------------
def test_t_cmp_07c_an_unknown_view_on_either_side_gives_view_unknown() -> None:
    # the views also differ, so both reasons, in the fixed order
    assert reasons_of(info(view="unknown"), info(view="front")) == ("view_differs", "view_unknown")
    assert reasons_of(info(view="front"), info(view="unknown")) == ("view_differs", "view_unknown")


def test_t_cmp_07c_two_unknown_views_are_not_comparable_either() -> None:
    d = decide(info(view="unknown"), info(view="unknown"))
    assert d.comparable is False
    assert d.reasons == ("view_unknown",)  # the views are equal, so no view_differs


# --- T-CMP-07d: the blocking flags ------------------------------------------------------------------------------------
def test_t_cmp_07d_the_blocking_flags_are_orientation_change_and_perspective_shift() -> None:
    assert BLOCKING_FLAGS == ("orientation_change", "perspective_shift")


@pytest.mark.parametrize("flag", ["orientation_change", "perspective_shift"])
def test_t_cmp_07d_a_blocking_flag_on_the_reference_gives_its_reason(flag: str) -> None:
    d = decide(info(flags=(flag,)), info())
    assert d.comparable is False and d.reasons == (f"flagged_reference:{flag}",)


@pytest.mark.parametrize("flag", ["orientation_change", "perspective_shift"])
def test_t_cmp_07d_a_blocking_flag_on_the_query_gives_its_reason(flag: str) -> None:
    d = decide(info(), info(flags=(flag,)))
    assert d.comparable is False and d.reasons == (f"flagged_query:{flag}",)


def test_t_cmp_07d_occlusion_does_not_block_on_either_side() -> None:
    d = decide(info(flags=("occlusion",)), info(flags=("occlusion",)))
    assert d.comparable is True and d.reasons == ()


def test_t_cmp_07d_occlusion_beside_a_blocking_flag_adds_no_reason() -> None:
    d = decide(info(flags=("occlusion", "orientation_change")), info(flags=("occlusion",)))
    assert d.reasons == ("flagged_reference:orientation_change",)


def test_t_cmp_07d_both_flags_come_in_the_fixed_order_whatever_the_set_order() -> None:
    both = info(flags=("perspective_shift", "orientation_change"))
    assert reasons_of(both, info()) == ("flagged_reference:orientation_change", "flagged_reference:perspective_shift")
    assert reasons_of(info(), both) == ("flagged_query:orientation_change", "flagged_query:perspective_shift")


def test_t_cmp_07d_the_reference_reasons_come_before_the_query_reasons() -> None:
    d = decide(info(flags=("perspective_shift",)), info(flags=("orientation_change", "perspective_shift")))
    assert d.reasons == (
        "flagged_reference:perspective_shift",
        "flagged_query:orientation_change",
        "flagged_query:perspective_shift",
    )


# --- T-CMP-07e: the coverage ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("min_visible", "expected"),
    [
        (1, 0.9),  # every row but the one with 0 valid units: 9 of 10
        (2, 0.8),  # the counts 4, 3, 3, 2, 4, 3, 3, 4: 8 of 10 (a row with exactly 2 counts)
        (3, 0.7),  # 4, 3, 3, 4, 3, 3, 4: 7 of 10 (the rows with exactly 3 count)
        (4, 0.3),  # 4, 4, 4: 3 of 10
    ],
)
def test_t_cmp_07e_coverage_is_the_share_of_rows_with_at_least_min_visible_valid_units(
    min_visible: int, expected: float
) -> None:
    d = decide(
        reference_features=feats(COUNTS), query_features=feats(COUNTS), min_visible=min_visible, min_coverage=0.1
    )
    assert d.coverage_reference == expected and d.coverage_query == expected
    assert d.comparable is True  # 0.3 is above 0.1


def test_t_cmp_07e_a_coverage_equal_to_the_minimum_is_enough() -> None:
    d = decide(reference_features=feats(COUNTS), query_features=feats(COUNTS), min_coverage=0.7)
    assert d.coverage_reference == 0.7 and d.coverage_query == 0.7
    assert d.comparable is True and d.reasons == ()


def test_t_cmp_07e_a_coverage_just_below_the_minimum_gives_the_reason() -> None:
    d = decide(reference_features=feats(COUNTS), query_features=feats(COUNTS), min_coverage=0.71)
    assert d.comparable is False
    assert d.reasons == ("coverage_low_reference", "coverage_low_query")
    assert (d.coverage_reference, d.coverage_query) == (0.7, 0.7)


def test_t_cmp_07e_a_coverage_just_above_the_minimum_is_enough() -> None:
    d = decide(reference_features=feats(COUNTS), query_features=feats(COUNTS), min_coverage=0.69)
    assert d.comparable is True and d.reasons == ()


def test_t_cmp_07e_a_minimum_of_one_needs_every_row() -> None:
    d = decide(min_visible=4, min_coverage=1.0)
    assert d.comparable is True and (d.coverage_reference, d.coverage_query) == (1.0, 1.0)
    nine = feats([4] * 9 + [3])  # 9 of 10
    d = decide(reference_features=nine, min_visible=4, min_coverage=1.0)
    assert d.reasons == ("coverage_low_reference",) and d.coverage_reference == 0.9


def test_t_cmp_07e_only_the_side_with_the_low_coverage_gets_the_reason() -> None:
    low = feats([4, 4] + [0] * 8)  # 2 rows of 10 have 3 or more units: 0.2
    d = decide(reference_features=low)
    assert d.reasons == ("coverage_low_reference",) and (d.coverage_reference, d.coverage_query) == (0.2, 1.0)
    d = decide(query_features=low)
    assert d.reasons == ("coverage_low_query",) and (d.coverage_reference, d.coverage_query) == (1.0, 0.2)
    d = decide(reference_features=low, query_features=low)
    assert d.reasons == ("coverage_low_reference", "coverage_low_query")


def test_t_cmp_07e_a_coverage_of_zero_is_a_coverage_and_not_a_missing_one() -> None:
    d = decide(reference_features=feats([1, 1, 2]))  # no row has 3 units
    assert d.coverage_reference == 0.0 and d.reasons == ("coverage_low_reference",)
    d = decide(query_features=feats([1, 1, 2]))
    assert d.coverage_query == 0.0 and d.reasons == ("coverage_low_query",)


def test_t_cmp_07e_a_segment_of_one_row_has_a_coverage_of_zero_or_one() -> None:
    assert decide(reference_features=feats([3]), min_coverage=1.0).coverage_reference == 1.0
    assert decide(reference_features=feats([2])).coverage_reference == 0.0


def test_t_cmp_07e_a_segment_without_rows_gives_no_rows_and_no_coverage() -> None:
    d = decide(reference_features=feats([]))
    assert d.comparable is False
    assert d.reasons == ("no_rows_reference",)  # not also coverage_low: a coverage that does not exist is not low
    assert d.coverage_reference is None and d.coverage_query == 1.0
    d = decide(query_features=feats([]))
    assert d.reasons == ("no_rows_query",) and d.coverage_reference == 1.0 and d.coverage_query is None
    d = decide(reference_features=feats([]), query_features=feats([]))
    assert d.reasons == ("no_rows_reference", "no_rows_query")
    assert d.coverage_reference is None and d.coverage_query is None


def test_t_cmp_07e_the_two_segments_may_have_different_unit_sets() -> None:
    # the guard counts the rows of each segment on its own; the units of the two are compared by the cost
    d = decide(reference_features=feats([4] * 10, units=4), query_features=feats([6] * 10, units=6))
    assert d.comparable is True and (d.coverage_reference, d.coverage_query) == (1.0, 1.0)


def test_t_cmp_07e_real_features_count_the_rows_with_enough_units() -> None:
    """21 units. Segment rows 0 to 9 lose LWrist (19 valid: its position and its forearm angle), rows 10 and 11 lose
    both wrists (17 valid) and the other 18 rows are clean (21 valid)."""
    layer = exact_layer(body(40, 400.0), segment=(5, 35))  # the segment is the grid rows 5 to 34
    kp, reason, interp = cells(layer)
    for g in range(5, 15):
        drop(kp, reason, g, IDX["LWrist"], 1)
    for g in range(15, 17):
        drop(kp, reason, g, IDX["LWrist"], 1)
        drop(kp, reason, g, IDX["RWrist"], 1)
    f = frame_features(edited(layer, keypoints=kp, reason=reason, interpolated=interp))
    assert f.valid.shape == (30, 21)
    # 17: all 30 rows; 19: the 10 rows with 19 and the 18 clean ones; 20 and 21: only the 18 clean rows
    for min_visible, usable in ((17, 30), (19, 28), (20, 18), (21, 18)):
        d = decide(reference_features=f, query_features=f, min_visible=min_visible, min_coverage=0.5)
        assert d.coverage_reference == usable / 30 and d.coverage_query == usable / 30
    clean = frame_features(exact_layer(body(40, 400.0), segment=(5, 35)))  # 30 rows of 21 valid units
    d = decide(reference_features=f, query_features=clean, min_visible=19, min_coverage=0.93)
    assert d.coverage_reference == 28 / 30 and d.coverage_query == 1.0  # 0.9333
    assert d.reasons == ()
    d = decide(reference_features=f, query_features=clean, min_visible=19, min_coverage=0.94)
    assert d.reasons == ("coverage_low_reference",)


# --- T-CMP-07f: several problems, every reason, in a fixed order ------------------------------------------------------
def test_t_cmp_07f_every_reason_comes_in_the_fixed_order() -> None:
    reference = info("A02", "left", "taiji24/v0", "front", ("orientation_change", "perspective_shift", "occlusion"))
    query = info("A04", "right", "taiji24/v1", "unknown", ("perspective_shift",))
    d = decide(reference, query, reference_features=feats([]), query_features=feats([4, 0, 0, 0]))
    assert d.comparable is False
    assert d.reasons == (
        "action_differs",
        "side_differs",
        "variant_differs",
        "view_differs",
        "view_unknown",
        "flagged_reference:orientation_change",
        "flagged_reference:perspective_shift",
        "flagged_query:perspective_shift",
        "no_rows_reference",
        "coverage_low_query",
    )
    assert d.coverage_reference is None and d.coverage_query == 0.25


def test_t_cmp_07f_the_other_data_reasons_come_after_the_flags() -> None:
    reference = info(flags=("perspective_shift",))
    query = info(flags=("orientation_change",))
    d = decide(reference, query, reference_features=feats([4, 0]), query_features=feats([]))
    assert d.reasons == (
        "flagged_reference:perspective_shift",
        "flagged_query:orientation_change",
        "no_rows_query",
        "coverage_low_reference",
    )


def test_t_cmp_07f_the_description_reasons_come_before_everything_else() -> None:
    d = decide(info(view="side"), info(side="right"), reference_features=feats([]), query_features=feats([]))
    assert d.reasons == ("side_differs", "view_differs", "no_rows_reference", "no_rows_query")


def test_t_cmp_07f_a_refusal_is_a_decision_and_never_an_error() -> None:
    d = decide(
        info("A01", "none", "x", "unknown", ("orientation_change",)),
        info("A24", "none", "y", "back", ("perspective_shift",)),
        reference_features=feats([]),
        query_features=feats([0]),
    )
    assert isinstance(d, GuardDecision) and d.comparable is False and len(d.reasons) >= 5


# --- T-CMP-07g: a wrong description or setting is an error ------------------------------------------------------------
BAD_FIELDS = [
    ("action", "A99"),
    ("action", "a01"),
    ("action", "A1"),
    ("action", ""),
    ("action", 1),
    ("action", None),
    ("side", "up"),
    ("side", None),
    ("side", 3),
    ("variant", ""),
    ("variant", "has space"),
    ("variant", "a/b/c"),
    ("variant", "v0/"),
    ("variant", "/v0"),
    ("variant", "a\\b"),
    ("variant", "C:x"),
    ("variant", "x" * 65),
    ("variant", "a/" + "x" * 65),
    ("variant", "taiji24/v0\n"),
    ("variant", "taiji\u00e924"),  # a letter that is not one of A to Z
    ("variant", "v\u0663"),  # a digit that is not one of 0 to 9
    ("variant", "a b/c"),
    ("variant", "a/b c"),
    ("variant", "a/taiji\u00e924"),  # the same two characters in the second part
    ("variant", "a/v\u0663"),
    ("variant", "a/b\\c"),
    ("variant", "a/b:c"),
    ("variant", "a/C:x"),
    ("variant", 5),
    ("variant", None),
    ("view_category", "top"),
    ("view_category", "Front"),
    ("view_category", ""),
    ("view_category", None),
    ("view_category", 7),
    ("flags", {"occlusion"}),
    ("flags", ["occlusion"]),
    ("flags", ("occlusion",)),
    ("flags", "occlusion"),
    ("flags", None),
    ("flags", frozenset({"blur"})),
    ("flags", frozenset({"occlusion", "blur"})),
    ("flags", frozenset({1})),
]


@pytest.mark.parametrize("which", ["reference", "query"])
@pytest.mark.parametrize(("field", "bad"), BAD_FIELDS)
def test_t_cmp_07g_a_wrong_field_of_a_segment_is_a_compare_error_naming_it(which: str, field: str, bad: Any) -> None:
    segment = dataclasses.replace(info(), **{field: bad})  # a dataclass that is not checked when it is built
    other = info()
    pair = (segment, other) if which == "reference" else (other, segment)
    with pytest.raises(CompareError, match=rf"{which}\.{field}\b"):
        decide(*pair)


@pytest.mark.parametrize(
    ("action", "side"),
    [("A07", "right"), ("A08", "left"), ("A01", "left"), ("A01", "right"), ("A02", "none"), ("A13", "left")],
)
def test_t_cmp_07g_a_side_the_action_does_not_have_is_a_compare_error(action: str, side: str) -> None:
    with pytest.raises(CompareError, match=r"reference\.side"):
        decide(info(action=action, side=side), info())


def test_t_cmp_07g_the_side_is_checked_against_the_action_of_its_own_segment() -> None:
    # A08 has only the right side: fine as the query, wrong as the query with left
    assert reasons_of(info("A07", "left"), info("A08", "right")) == ("action_differs", "side_differs")
    with pytest.raises(CompareError, match=r"query\.side"):
        decide(info("A07", "left"), info("A08", "left"))


@pytest.mark.parametrize("bad", [None, {"action": "A01"}, "A02", 3, GOOD])
def test_t_cmp_07g_a_description_that_is_not_a_segment_info_is_refused(bad: Any) -> None:
    with pytest.raises(CompareError, match=r"reference must be a SegmentInfo"):
        check_comparable(bad, info(), GOOD, GOOD, min_visible=3, min_coverage=0.7)
    with pytest.raises(CompareError, match=r"query must be a SegmentInfo"):
        check_comparable(info(), bad, GOOD, GOOD, min_visible=3, min_coverage=0.7)


@pytest.mark.parametrize("bad", [None, np.ones((10, 4), dtype=bool), {"valid": 1}, "features", info()])
def test_t_cmp_07g_features_that_are_not_frame_features_are_refused(bad: Any) -> None:
    with pytest.raises(CompareError, match=r"reference_features must be a FrameFeatures"):
        decide(reference_features=bad)
    with pytest.raises(CompareError, match=r"query_features must be a FrameFeatures"):
        decide(query_features=bad)


@pytest.mark.parametrize(
    "valid",
    [
        np.ones((10, 4), dtype=np.uint8),
        np.ones((10, 4), dtype=np.float64),
        np.ones((10,), dtype=bool),
        np.ones((10, 4, 2), dtype=bool),
        None,
        [[True] * 4] * 10,
    ],
)
def test_t_cmp_07g_features_whose_valid_is_not_a_two_dimensional_bool_array_are_refused(valid: Any) -> None:
    broken = dataclasses.replace(GOOD, valid=valid)
    with pytest.raises(CompareError, match=r"reference_features\.valid"):
        decide(reference_features=broken)
    with pytest.raises(CompareError, match=r"query_features\.valid"):
        decide(query_features=broken)


@pytest.mark.parametrize(
    "bad", [0, -1, 1.5, 3.0, float("nan"), True, np.bool_(True), "3", None, [3], np.float64(3.0), 5, 10**9]
)
def test_t_cmp_07g_a_bad_min_visible_is_refused(bad: Any) -> None:
    # 5 and more are above the 4 units of GOOD
    with pytest.raises(CompareError, match=r"min_visible"):
        decide(min_visible=bad)


def test_t_cmp_07g_min_visible_above_the_units_of_either_segment_is_refused() -> None:
    with pytest.raises(CompareError, match=r"min_visible.*reference_features"):
        decide(reference_features=feats([2, 2], units=2), min_visible=3)
    with pytest.raises(CompareError, match=r"min_visible.*query_features"):
        decide(query_features=feats([2, 2], units=2), min_visible=3)
    assert decide(query_features=feats([2, 2], units=2), min_visible=2, min_coverage=1.0).comparable is True


@pytest.mark.parametrize("good", [1, 3, 4, np.int64(3), np.int32(4)])
def test_t_cmp_07g_a_min_visible_from_one_to_the_units_is_accepted(good: Any) -> None:
    assert decide(min_visible=good, min_coverage=0.1).min_visible == int(good)


@pytest.mark.parametrize(
    "bad",
    [0, 0.0, -0.1, 1.0000001, 2, float("nan"), float("inf"), float("-inf"), True, np.bool_(True), "0.5", None, [0.5]],
)
def test_t_cmp_07g_a_bad_min_coverage_is_refused(bad: Any) -> None:
    with pytest.raises(CompareError, match=r"min_coverage"):
        decide(min_coverage=bad)


@pytest.mark.parametrize("good", [1, 1.0, 0.0001, 0.5, np.float64(0.5), np.float32(0.5), np.int64(1)])
def test_t_cmp_07g_a_min_coverage_in_zero_exclusive_to_one_is_accepted(good: Any) -> None:
    assert decide(min_coverage=good).min_coverage == float(good)


def test_t_cmp_07g_min_visible_and_min_coverage_have_no_default() -> None:
    with pytest.raises(TypeError):
        check_comparable(info(), info(), GOOD, GOOD, min_coverage=0.5)
    with pytest.raises(TypeError):
        check_comparable(info(), info(), GOOD, GOOD, min_visible=3)


def test_t_cmp_07g_the_settings_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        check_comparable(info(), info(), GOOD, GOOD, 3, 0.7)


def test_t_cmp_07g_an_ontology_that_is_not_an_ontology_is_refused() -> None:
    for bad in ("ontology_v0.yaml", {"actions": []}, 3):
        with pytest.raises(CompareError, match=r"ontology must be an Ontology"):
            decide(ontology=bad)


def test_t_cmp_07g_an_error_never_echoes_text_given_by_the_caller() -> None:
    secret = "secret-text"
    bad = [
        dataclasses.replace(info(), action=secret),
        dataclasses.replace(info(), side=secret),
        dataclasses.replace(info(), variant=secret + " x"),
        dataclasses.replace(info(), view_category=secret),
        dataclasses.replace(info(), flags=frozenset({secret})),
    ]
    for segment in bad:
        with pytest.raises(CompareError) as caught:
            decide(segment, info())
        assert secret not in str(caught.value)
    for kwargs in ({"min_visible": secret}, {"min_coverage": secret}, {"ontology": secret}):
        with pytest.raises(CompareError) as caught:
            decide(**kwargs)
        assert secret not in str(caught.value)


def test_t_cmp_07g_a_made_up_ontology_replaces_the_shipped_one() -> None:
    onto = small_ontology()
    assert decide(info("A99", "left"), info("A99", "left"), ontology=onto).comparable is True
    with pytest.raises(CompareError, match=r"reference\.action"):
        decide(info("A99", "left"), info("A99", "left"))  # A99 is not in the shipped ontology
    with pytest.raises(CompareError, match=r"reference\.action"):
        decide(info("A02", "left"), info("A02", "left"), ontology=onto)  # and A02 is not in the made-up one
    with pytest.raises(CompareError, match=r"reference\.view_category"):
        decide(info("A99", "left", view="back"), info("A99", "left"), ontology=onto)  # no back view there
    with pytest.raises(CompareError, match=r"query\.side"):
        decide(info("A99", "left"), info("A01", "left"), ontology=onto)  # A01 has no left side there
    # the flag of the made-up ontology is known there and blocks nothing; the shipped one does not know it
    blurred = info("A99", "left", flags=("blur",))
    assert decide(blurred, info("A99", "left"), ontology=onto).reasons == ()
    with pytest.raises(CompareError, match=r"reference\.flags"):
        decide(info("A02", "left", flags=("blur",)), info("A02", "left"))  # the shipped ontology does not know blur


def test_t_cmp_07g_the_shipped_ontology_is_the_default() -> None:
    a, b = info("A13", "right", flags=("orientation_change",)), info("A13", "right")
    assert decide(a, b) == decide(a, b, ontology=load_ontology())


def test_t_cmp_07g_the_default_ontology_is_read_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def counting() -> Ontology:
        calls.append(1)
        return load_ontology()

    guards._default_ontology.cache_clear()
    monkeypatch.setattr(guards, "load_ontology", counting)
    try:
        decide()
        decide(info("A13", "right"), info("A13", "right"))
        assert len(calls) == 1
    finally:
        guards._default_ontology.cache_clear()  # do not keep the counting reader's result for the other tests


# --- T-CMP-07h: the decision echoes the settings; the inputs are unchanged --------------------------------------------
def test_t_cmp_07h_the_decision_echoes_the_settings_and_the_coverages() -> None:
    d = decide(reference_features=feats(COUNTS), query_features=feats([4, 4, 0, 0]), min_visible=3, min_coverage=0.55)
    assert d == GuardDecision(
        comparable=False,
        reasons=("coverage_low_query",),  # the reference has 0.7, the query 2 of 4 = 0.5
        coverage_reference=0.7,
        coverage_query=0.5,
        min_visible=3,
        min_coverage=0.55,
    )


def test_t_cmp_07h_the_settings_are_plain_numbers_in_the_decision() -> None:
    d = decide(min_visible=np.int64(3), min_coverage=np.float32(0.5))
    assert type(d.min_visible) is int and d.min_visible == 3
    assert type(d.min_coverage) is float and d.min_coverage == 0.5
    assert type(d.coverage_reference) is float and type(d.coverage_query) is float
    assert type(d.reasons) is tuple and all(type(r) is str for r in d.reasons)
    assert type(d.comparable) is bool


def test_t_cmp_07h_comparable_means_there_is_no_reason() -> None:
    for reference, query in ((info(), info()), (info(view="side"), info()), (info(flags=("occlusion",)), info())):
        d = decide(reference, query)
        assert d.comparable == (d.reasons == ())


def test_t_cmp_07h_the_inputs_are_unchanged_and_the_decision_is_frozen() -> None:
    reference = info("A02", "left", flags=("orientation_change", "occlusion"))
    query = info("A02", "left", view="side")
    rf, qf = feats(COUNTS), feats(COUNTS)
    before = (rf.valid.copy(), rf.values.copy(), qf.valid.copy(), reference, query, set(reference.flags))
    d = decide(reference, query, reference_features=rf, query_features=qf)
    assert np.array_equal(rf.valid, before[0]) and np.array_equal(rf.values, before[1], equal_nan=True)
    assert np.array_equal(qf.valid, before[2])
    assert reference == before[3] and query == before[4] and set(reference.flags) == before[5]
    assert not rf.valid.flags.writeable and not qf.valid.flags.writeable
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.comparable = True
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference.action = "A03"


def test_t_cmp_07h_the_same_input_gives_the_same_decision() -> None:
    reference = info(flags=("perspective_shift", "orientation_change"))
    query = info(view="unknown")
    first = decide(reference, query, reference_features=feats(COUNTS), query_features=feats([]))
    for _ in range(3):
        assert decide(reference, query, reference_features=feats(COUNTS), query_features=feats([])) == first
