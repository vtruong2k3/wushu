"""T-CMP-03i to T-CMP-03l: the alignment of two segments, features to cost to DTW in one call (P6.03b, W8, Appendix C).

``align`` is exactly ``dtw(cost_matrix(...))`` with the settings that made the distance recorded; the numbers are
re-derived here from the parts themselves, and the mean query time of a path row (``matched_query_times``) by a plain
loop over the path. Features are built by hand (``helpers/compare_cost_ref.py``), so a test controls the values, the
masks and the clock; the real chain (generator, quality stage, ``frame_features``) is in
``tests/golden/test_compare_align_syn.py``.

* T-CMP-03i: ``align`` equals the parts; the settings are complete, read-only and tell what changes ``D``.
* T-CMP-03j: the parts' refusals pass through with their message; no path is a result; ``align`` runs no guard.
* T-CMP-03k: ``matched_query_times`` (read by P6.04 and P6.07).
* T-CMP-03l: the settings are a fingerprint (short-code names, plain values); two feature sets made with different
  minimums are refused; ``as_comparison`` gives the ``Comparison`` of P6.06.
"""

from __future__ import annotations

import dataclasses
import json
import math
import pathlib
import re
import warnings
from collections.abc import Mapping

import numpy as np
import pytest

import taiji_ai.compare.reference_band as band_module
from helpers.compare_cost_ref import (
    ANGLES,
    POSITIONS,
    RECORDING_QRY,
    RECORDING_REF,
    make_features,
    make_units,
    random_features,
)
from taiji_ai.compare import CompareError
from taiji_ai.compare.align import Alignment, align
from taiji_ai.compare.cost import cost_matrix
from taiji_ai.compare.dtw import DtwResult, dtw
from taiji_ai.compare.features import FrameFeatures
from taiji_ai.compare.reference_band import Comparison, reference_band
from taiji_ai.schemas.quality_layers import DataSource

SETTING_NAMES = {
    "feature_version",
    "units",
    "weights",
    "min_visible",
    "band",
    "step",
    "min_scale_s",
    "min_segment_length",
}
UNIT_NAMES = (*POSITIONS, *ANGLES)
CASES = [
    pytest.param(0.5, "symmetricP1", 2, None, id="P1, band 0.5"),
    pytest.param(1.0, "symmetric1", 1, None, id="unit steps, no band"),
    pytest.param(0.3, "symmetricP1", 3, {"LWrist": 2.0, "trunk": 0.5}, id="P1, band 0.3, weights"),
]
SEEDS = [0, 1, 2]


def pair(seed: int, n: int = 12, m: int = 14) -> tuple[FrameFeatures, FrameFeatures]:
    """``(reference of m rows, query of n rows)`` of random features, few of them invalid (a finite path exists)."""
    rng = np.random.default_rng(seed)
    reference = random_features(rng, m, p_invalid=0.1)
    query = random_features(rng, n, p_invalid=0.1, recording_id=RECORDING_QRY)
    return reference, query


def refusal(function, *args, **kwargs) -> str:
    """The message of the ``CompareError`` that ``function`` raises (the test fails if it raises nothing else)."""
    with pytest.raises(CompareError) as caught:
        function(*args, **kwargs)
    return str(caught.value)


def is_plain(value: object) -> bool:
    """A number, a string, ``None``, or a tuple or a mapping of plain values (no numpy scalar, no list, no array)."""
    if value is None or isinstance(value, str):
        return True
    if type(value) in (int, float):  # a bool and a numpy scalar are not plain here
        return True
    if isinstance(value, tuple):
        return all(is_plain(v) for v in value)
    if isinstance(value, Mapping):
        return all(isinstance(k, str) and is_plain(v) for k, v in value.items())
    return False


def same_result(got: DtwResult, want: DtwResult) -> None:
    assert np.array_equal(got.path, want.path) and got.path.dtype == want.path.dtype
    assert (got.distance, got.status, got.accumulated, got.normalised) == (
        want.distance,
        want.status,
        want.accumulated,
        want.normalised,
    )
    assert dict(got.params) == dict(want.params)


def line(xs, t=None) -> FrameFeatures:
    """One position unit that moves along x (trunk lengths): a hand-made segment whose cost is ``|x_q - x_r|``."""
    values = np.zeros((len(xs), 1, 2))
    values[:, 0, 0] = xs
    features = make_features(values, np.ones((len(xs), 1), dtype=bool), make_units(("LWrist",), ()))
    return features if t is None else dataclasses.replace(features, t_sec=np.asarray(t, dtype=np.float64))


# --- T-CMP-03i: align is exactly the parts --------------------------------------------------------------------------
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize(("band", "step", "min_visible", "weights"), CASES)
def test_t_cmp_03i_align_equals_dtw_of_the_cost_matrix(seed, band, step, min_visible, weights):
    reference, query = pair(seed)
    got = align(reference, query, min_visible=min_visible, band=band, step=step, weights=weights)
    cost = cost_matrix(reference, query, min_visible=min_visible, weights=weights)
    want = dtw(cost, band=band, step=step)
    assert got.reference is reference and got.query is query
    assert np.array_equal(got.cost.values, cost.values) and np.array_equal(got.cost.n_common, cost.n_common)
    assert (got.cost.units, got.cost.weights, got.cost.min_visible) == (cost.units, cost.weights, cost.min_visible)
    assert got.cost.values.shape == (12, 14)  # (query rows, reference rows)
    assert want.status == "ok"
    same_result(got.result, want)
    assert got.distance == want.distance and got.distance is got.result.distance


def test_t_cmp_03i_the_alignment_is_a_frozen_value_that_keeps_the_inputs_unchanged():
    reference, query = pair(3)
    before = [a.copy() for a in (reference.values, reference.valid, query.values, query.valid, query.t_sec)]
    got = align(reference, query, min_visible=2, band=0.5)
    after = (reference.values, reference.valid, query.values, query.valid, query.t_sec)
    for old, new in zip(before, after, strict=True):
        assert np.array_equal(old, new, equal_nan=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        got.result = got.result  # type: ignore[misc]
    assert isinstance(got, Alignment)
    again = align(reference, query, min_visible=2, band=0.5)
    assert got == got and got != again and hash(got) != hash(again)  # identity, like the other results (arrays inside)


def test_t_cmp_03i_read_only_features_are_accepted_and_the_step_defaults_to_the_product_pattern():
    rng = np.random.default_rng(4)
    reference = random_features(rng, 10, p_invalid=0.1, frozen=True)
    query = random_features(rng, 10, p_invalid=0.1, frozen=True)
    got = align(reference, query, min_visible=2, band=0.5)
    assert got.result.params["step"] == "symmetricP1" and got.settings["step"] == "symmetricP1"
    assert got.result.status == "ok"
    assert not got.result.path.flags.writeable and not got.cost.values.flags.writeable


def test_t_cmp_03i_settings_are_complete_and_say_what_decided_the_distance():
    reference, query = pair(0)
    got = align(reference, query, min_visible=3, band=0.4, step="symmetric1", weights={"LWrist": 2.0})
    assert set(got.settings) == SETTING_NAMES
    assert got.settings["feature_version"] == reference.version == "1"
    assert got.settings["units"] == UNIT_NAMES
    assert got.settings["weights"] == (1.0, 2.0, 1.0, 1.0, 1.0, 1.0)  # one per unit, in the order of the units
    assert got.settings["min_visible"] == 3 and got.settings["band"] == 0.4 and got.settings["step"] == "symmetric1"
    assert got.settings["min_scale_s"] is None and got.settings["min_segment_length"] is None
    # plain Python objects, not numpy scalars: a JSON writer takes them as they are
    assert type(got.settings["band"]) is float and type(got.settings["min_visible"]) is int
    assert all(type(w) is float for w in got.settings["weights"])
    assert all(type(u) is str for u in got.settings["units"])
    assert is_plain(got.settings)
    assert json.loads(json.dumps(dict(got.settings)))["units"] == list(UNIT_NAMES)


def test_t_cmp_03i_settings_hold_the_numbers_as_python_floats_and_ints_whatever_the_caller_passed():
    reference, query = pair(0)
    got = align(reference, query, min_visible=np.int64(2), band=np.float32(0.5), weights={"trunk": np.float64(3)})
    assert type(got.settings["min_visible"]) is int and got.settings["min_visible"] == 2
    assert type(got.settings["band"]) is float and got.settings["band"] == float(np.float32(0.5))
    assert got.settings["weights"][-1] == 3.0 and all(type(w) is float for w in got.settings["weights"])
    whole = align(reference, query, min_visible=2, band=1)  # an int band: 1 is no band
    assert type(whole.settings["band"]) is float and whole.settings["band"] == 1.0


def test_t_cmp_03i_settings_are_read_only_and_not_shared_with_the_caller():
    reference, query = pair(0)
    weights = {"LWrist": 2.0}
    got = align(reference, query, min_visible=2, band=0.5, weights=weights)
    assert isinstance(got.settings, Mapping) and not isinstance(got.settings, dict)
    with pytest.raises(TypeError):
        got.settings["band"] = 0.9  # type: ignore[index]
    with pytest.raises(TypeError):
        del got.settings["band"]  # type: ignore[attr-defined]
    weights["LWrist"] = 9.0  # a later change of the caller's mapping changes nothing that was echoed
    assert got.settings["weights"][1] == 2.0
    again = align(reference, query, min_visible=2, band=0.5, weights={"LWrist": 2.0})
    assert dict(again.settings) == dict(got.settings) and again.settings is not got.settings


@pytest.mark.parametrize(
    ("change", "key"),
    [
        pytest.param({"min_visible": 3}, "min_visible", id="min_visible"),
        pytest.param({"band": 0.4}, "band", id="band"),
        pytest.param({"step": "symmetric1"}, "step", id="step"),
        pytest.param({"weights": {"LWrist": 2.0}}, "weights", id="weights"),
    ],
)
def test_t_cmp_03i_changing_one_argument_changes_exactly_one_setting(change, key):
    reference, query = pair(0)
    base = {"min_visible": 2, "band": 0.5, "step": "symmetricP1", "weights": None}
    first = align(reference, query, **base)
    second = align(reference, query, **{**base, **change})
    differ = {name for name in SETTING_NAMES if first.settings[name] != second.settings[name]}
    assert differ == {key}


def test_t_cmp_03i_the_features_decide_the_version_the_units_and_the_minimums_in_the_settings():
    rng = np.random.default_rng(1)
    units = make_units(("LWrist", "RWrist", "LKnee"), ("trunk",))
    reference, query = (random_features(rng, 8, units=units, p_invalid=0.0) for _ in range(2))
    got = align(reference, query, min_visible=2, band=1.0)
    assert got.settings["units"] == ("LWrist", "RWrist", "LKnee", "trunk")
    assert got.settings["weights"] == (1.0, 1.0, 1.0, 1.0)
    newer = [dataclasses.replace(f, version="2") for f in (reference, query)]
    assert align(*newer, min_visible=2, band=1.0).settings["feature_version"] == "2"
    kept = [dataclasses.replace(f, min_scale_s=1.5, min_segment_length=0.05) for f in (reference, query)]
    both = align(*kept, min_visible=2, band=1.0)
    assert both.settings["min_scale_s"] == 1.5 and both.settings["min_segment_length"] == 0.05
    assert type(both.settings["min_scale_s"]) is float and is_plain(both.settings)


# --- T-CMP-03j: refusals pass through; no path is a result; no guard --------------------------------------------------
@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param({"min_visible": 0, "band": 0.5}, id="min_visible 0"),
        pytest.param({"min_visible": 1.5, "band": 0.5}, id="min_visible not an integer"),
        pytest.param({"min_visible": True, "band": 0.5}, id="min_visible a bool"),
        pytest.param({"min_visible": 7, "band": 0.5}, id="min_visible above the number of units"),
        pytest.param({"min_visible": 2, "band": 0.5, "weights": {"NoSuchUnit": 1.0}}, id="a weight for no unit"),
        pytest.param({"min_visible": 2, "band": 0.5, "weights": {"LWrist": -1.0}}, id="a negative weight"),
    ],
)
def test_t_cmp_03j_the_refusals_of_the_cost_pass_through_with_their_message(arguments):
    reference, query = pair(0)
    got = refusal(align, reference, query, **arguments)
    assert got == refusal(cost_matrix, reference, query, **{k: v for k, v in arguments.items() if k != "band"})


@pytest.mark.parametrize(
    ("band", "step"),
    [
        pytest.param(0.0, "symmetricP1", id="band 0"),
        pytest.param(1.5, "symmetricP1", id="band above 1"),
        pytest.param(math.nan, "symmetricP1", id="band NaN"),
        pytest.param(True, "symmetricP1", id="band a bool"),
        pytest.param("0.5", "symmetricP1", id="band a string"),
        pytest.param(0.5, "symmetric2", id="unknown step"),
        pytest.param(0.5, 3, id="step not a string"),
    ],
)
def test_t_cmp_03j_the_refusals_of_dtw_pass_through_with_their_message(band, step):
    reference, query = pair(0)
    got = refusal(align, reference, query, min_visible=2, band=band, step=step)
    cost = cost_matrix(reference, query, min_visible=2)
    assert got == refusal(dtw, cost, band=band, step=step)
    assert "band" in got or "step" in got


def test_t_cmp_03j_a_message_never_echoes_a_string_of_the_caller():
    reference, query = pair(0)
    for kwargs in (
        {"step": "SECRET-step"},
        {"band": "SECRET-band"},
        {"weights": {"SECRET-unit": 1.0}},
    ):
        message = refusal(align, reference, query, **{"min_visible": 2, "band": 0.5, **kwargs})
        assert "SECRET" not in message


def test_t_cmp_03j_features_with_different_units_or_versions_are_refused_like_the_cost_does():
    rng = np.random.default_rng(2)
    reference = random_features(rng, 8, p_invalid=0.0)
    other_units = random_features(rng, 8, units=make_units(("LWrist", "RWrist"), ("trunk",)), p_invalid=0.0)
    got = refusal(align, reference, other_units, min_visible=1, band=0.5)
    assert got == refusal(cost_matrix, reference, other_units, min_visible=1)
    older = dataclasses.replace(random_features(rng, 8, p_invalid=0.0), version="0")
    got = refusal(align, reference, older, min_visible=1, band=0.5)
    assert got == refusal(cost_matrix, reference, older, min_visible=1)
    assert "version" in got


@pytest.mark.parametrize("argument", ["reference", "query"])
@pytest.mark.parametrize("wrong", [None, "features", np.zeros((3, 2, 2))], ids=["None", "str", "array"])
def test_t_cmp_03j_an_argument_that_is_not_features_is_refused_naming_it(argument, wrong):
    reference, query = pair(0)
    arguments = {"reference": reference, "query": query, argument: wrong}
    message = refusal(align, arguments["reference"], arguments["query"], min_visible=2, band=0.5)
    assert argument in message and "FrameFeatures" in message
    assert f"got {type(wrong).__name__}" in message  # the type is named, the text of a string is not echoed


def test_t_cmp_03j_no_path_is_a_result_and_not_an_error():
    reference = random_features(np.random.default_rng(5), 6, p_invalid=0.0)
    blind = make_features(np.full((5, 6, 2), np.nan), np.zeros((5, 6), dtype=bool), recording_id=RECORDING_QRY)
    got = align(reference, blind, min_visible=1, band=0.5)  # no unit is valid in any query frame: every cell is +inf
    assert np.isinf(got.cost.values).all() and got.cost.values.shape == (5, 6)
    assert got.result.status == "no_path" and got.distance is None
    assert got.result.path.shape == (0, 2)
    assert got.result.distance is None and got.result.accumulated is None and got.result.normalised is None
    matched = got.matched_query_times()
    assert matched.shape == (6,) and np.isnan(matched).all()  # one NaN for every reference row, never 0
    comparison = got.as_comparison("ref_a", "trainee_1")
    assert comparison.distance is None and dict(comparison.settings) == dict(got.settings)
    # the lengths of the slope pattern: 2 query rows against 9 reference rows has no path either
    rng = np.random.default_rng(6)
    long_reference, two_rows = random_features(rng, 9, p_invalid=0.0), random_features(rng, 2, p_invalid=0.0)
    short = align(long_reference, two_rows, min_visible=1, band=1.0)
    assert short.result.status == "no_path" and short.distance is None
    assert np.isnan(short.matched_query_times()).all() and short.as_comparison("ref_a", "trainee_1").distance is None


@pytest.mark.parametrize("step", ["symmetricP1", "symmetric1"])
def test_t_cmp_03j_a_single_frame_each_is_aligned_and_a_segment_without_frames_is_refused(step):
    one = align(line([0.0]), line([2.0], t=[7.5]), min_visible=1, band=0.2, step=step)
    assert one.result.status == "ok" and one.result.path.tolist() == [[0, 0]]
    assert one.distance == 2.0 and one.matched_query_times().tolist() == [7.5]
    assert one.settings["step"] == step and one.as_comparison("ref_a", "take_b").distance == 2.0
    nothing = make_features(np.zeros((0, 1, 2)), np.zeros((0, 1), dtype=bool), make_units(("LWrist",), ()))
    for reference, query in ((nothing, line([0.0, 1.0])), (line([0.0, 1.0]), nothing)):
        assert "at least one row" in refusal(align, reference, query, min_visible=1, band=0.5, step=step)


def test_t_cmp_03j_align_runs_no_guard_it_compares_whatever_features_it_is_given():
    """The guards of P6.05 decide whether two segments may be compared; ``align`` only aligns what it is handed."""
    rng = np.random.default_rng(7)
    reference = random_features(rng, 9, p_invalid=0.1)
    query = random_features(rng, 9, p_invalid=0.1, recording_id=RECORDING_QRY)
    other = dataclasses.replace(
        query,
        scale_px=33.0,
        roll_deg=12.0,
        recording_id="d2c8a0b4-3e1f-4a57-9b6c-0f7e5d4c3b2a",
        data_sources=(DataSource(dataset_id="D20", license="web lesson videos"),),
        step_s=0.05,
    )
    plain = align(reference, query, min_visible=2, band=0.5)
    got = align(reference, other, min_visible=2, band=0.5)
    assert got.result.status == "ok" and got.query is other
    same_result(got.result, plain.result)  # nothing but the values, the masks and the units enter the alignment
    assert got.cost.query_recording_id == other.recording_id and got.cost.reference_recording_id == RECORDING_REF


# --- the clock that enters the alignment ------------------------------------------------------------------------------
@pytest.mark.parametrize("who", ["reference", "query"])
@pytest.mark.parametrize(
    ("t_sec", "what"),
    [
        pytest.param(np.arange(5) / 30.0, "one entry per row", id="too few entries"),
        pytest.param(np.arange(11) / 30.0, "one entry per row", id="too many entries"),
        pytest.param(np.arange(8, dtype=np.float64).reshape(2, 4), "one-dimensional float array", id="two-dimensional"),
        pytest.param(np.array([0, 1, 2, 3, 4, 5, 6, 7]), "one-dimensional float array", id="integers"),
        pytest.param([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], "one-dimensional float array", id="a list"),
        pytest.param(np.array([0.0, 0.1, math.nan, 0.3, 0.4, 0.5, 0.6, 0.7]), "must be finite", id="NaN"),
        pytest.param(np.array([0.0, 0.1, math.inf, 0.3, 0.4, 0.5, 0.6, 0.7]), "must be finite", id="infinity"),
        pytest.param(np.array([0.0, 0.1, 0.3, 0.2, 0.4, 0.5, 0.6, 0.7]), "strictly increasing", id="goes back"),
        pytest.param(np.array([0.0, 0.1, 0.1, 0.2, 0.4, 0.5, 0.6, 0.7]), "strictly increasing", id="a repeated time"),
    ],
)
def test_t_cmp_03j_a_clock_that_is_not_a_clock_is_refused_naming_the_features(who, t_sec, what):
    rng = np.random.default_rng(8)
    features = {"reference": random_features(rng, 8, p_invalid=0.0), "query": random_features(rng, 8, p_invalid=0.0)}
    features[who] = dataclasses.replace(features[who], t_sec=t_sec)
    message = refusal(align, features["reference"], features["query"], min_visible=1, band=1.0)
    assert f"{who}.t_sec" in message and what in message


# --- T-CMP-03k: the mean query time of every reference row ------------------------------------------------------------
def test_t_cmp_03k_a_vertical_run_averages_the_query_times_of_the_row_in_seconds():
    # query x 0 0 1 2 2 3 against reference x 0 1 2 3: the only path of cost 0 is (0,0) (1,0) (2,1) (3,2) (4,2) (5,3)
    reference = line([0.0, 1.0, 2.0, 3.0])
    query = line([0.0, 0.0, 1.0, 2.0, 2.0, 3.0], t=[0.0, 0.1, 0.3, 0.7, 0.8, 1.5])  # an uneven clock
    got = align(reference, query, min_visible=1, band=1.0, step="symmetric1")
    assert got.result.path.tolist() == [[0, 0], [1, 0], [2, 1], [3, 2], [4, 2], [5, 3]] and got.distance == 0.0
    matched = got.matched_query_times()
    assert matched.shape == (4,) and matched.dtype == np.float64
    assert matched.tolist() == pytest.approx([(0.0 + 0.1) / 2, 0.3, (0.7 + 0.8) / 2, 1.5], abs=1e-15)
    index_time = np.array([0.5, 2.0, 3.5, 5.0]) / 30.0  # what row indices at 30 fps would give: not what is returned
    assert not np.allclose(matched, index_time, atol=0.01)


def test_t_cmp_03k_a_horizontal_run_gives_one_query_time_to_several_reference_rows():
    reference = line([0.0, 0.0, 1.0, 2.0], t=[5.0, 6.0, 7.0, 8.0])  # a reference clock that must not enter
    query = line([0.0, 1.0, 2.0], t=[0.0, 0.4, 1.0])
    got = align(reference, query, min_visible=1, band=1.0, step="symmetric1")
    assert got.result.path.tolist() == [[0, 0], [0, 1], [1, 2], [2, 3]] and got.distance == 0.0
    assert got.matched_query_times().tolist() == [0.0, 0.0, 0.4, 1.0]  # the query's seconds, not the reference's


def test_t_cmp_03k_the_mean_is_over_every_cell_of_the_row_not_the_first_the_last_or_the_median():
    reference = line([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    query = line([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], t=[0.0, 0.1, 0.7, 0.9, 1.0, 2.0, 2.5, 4.0])
    got = align(reference, query, min_visible=1, band=1.0, step="symmetric1")
    # hand-made path: reference row 1 holds query rows 1, 2, 3 (a vertical run of three) and query row 5 holds 3, 4, 5
    path = np.array([[0, 0], [1, 1], [2, 1], [3, 1], [4, 2], [5, 3], [5, 4], [5, 5], [6, 5], [7, 5]], dtype=np.int64)
    made = dataclasses.replace(got, result=dataclasses.replace(got.result, path=path))
    t = query.t_sec
    want = [
        t[0],  # row 0: (0, 0)
        (t[1] + t[2] + t[3]) / 3,  # row 1: three query rows
        t[4],  # row 2
        t[5],  # row 3
        t[5],  # row 4: the run of query row 5 ...
        (t[5] + t[6] + t[7]) / 3,  # row 5: ... and three query rows again
    ]
    matched = made.matched_query_times()
    assert matched.tolist() == pytest.approx(want, abs=1e-15)
    assert matched[1] != pytest.approx(np.median(t[1:4])) and matched[1] != t[1] and matched[1] != t[3]


def test_t_cmp_03k_a_reference_row_that_no_path_cell_touches_is_nan_and_never_zero():
    """A path from corner to corner touches every row; for a path that does not (a defect upstream) the row is not
    observed: NaN, with no warning raised, and the other rows keep their mean."""
    reference = line([0.0, 1.0, 2.0, 3.0])
    query = line([0.0, 1.0, 2.0], t=[0.5, 0.75, 2.0])
    got = align(reference, query, min_visible=1, band=1.0, step="symmetric1")
    path = np.array([[0, 0], [1, 2], [2, 3]], dtype=np.int64)  # reference row 1 has no cell
    made = dataclasses.replace(got, result=dataclasses.replace(got.result, path=path))
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a division by zero would warn
        matched = made.matched_query_times()
    assert matched[0] == 0.5 and matched[2] == 0.75 and matched[3] == 2.0
    assert np.isnan(matched[1]) and not (matched == 0.0).any()
    short = np.array([[0, 0], [1, 1], [2, 2]], dtype=np.int64)  # the last reference row has no cell either
    made = dataclasses.replace(got, result=dataclasses.replace(got.result, path=short))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        matched = made.matched_query_times()
    assert matched.shape == (4,) and matched[:3].tolist() == [0.5, 0.75, 2.0] and np.isnan(matched[3])


def test_t_cmp_03k_the_result_is_a_new_read_only_float64_array_and_the_clock_is_the_query_s():
    reference, query = pair(9, n=10, m=10)
    got = align(reference, query, min_visible=2, band=1.0, step="symmetric1")
    assert got.result.status == "ok"
    first, second = got.matched_query_times(), got.matched_query_times()
    assert first is not second and np.array_equal(first, second)
    assert first.dtype == np.float64 and first.shape == (len(reference.t_sec),) and not first.flags.writeable
    with pytest.raises(ValueError):
        first[0] = 1.0
    shifted = dataclasses.replace(query, t_sec=query.t_sec + 100.0)
    again = align(reference, shifted, min_visible=2, band=1.0, step="symmetric1").matched_query_times()
    assert np.allclose(again, first + 100.0, atol=1e-12)  # it follows the query clock and nothing else
    path = got.result.path
    for k in range(len(reference.t_sec)):  # the plain loop over the path
        rows = [int(i) for i, kk in path.tolist() if kk == k]
        assert rows and first[k] == pytest.approx(sum(query.t_sec[i] for i in rows) / len(rows), abs=1e-12)
    assert query.t_sec[0] <= first[0] and first[-1] <= query.t_sec[-1]  # a mean of times that lie in the segment
    assert np.all(np.diff(first) >= 0.0)  # a monotone path gives a non-decreasing time


def test_t_cmp_03k_the_product_pattern_gives_a_non_decreasing_time_on_an_uneven_clock():
    rng = np.random.default_rng(10)
    reference = random_features(rng, 12, p_invalid=0.0)
    query = random_features(rng, 15, p_invalid=0.0, recording_id=RECORDING_QRY)
    clock = np.cumsum(rng.uniform(0.01, 0.2, size=15))
    query = dataclasses.replace(query, t_sec=clock)
    got = align(reference, query, min_visible=2, band=1.0)
    assert got.result.status == "ok"
    matched = got.matched_query_times()
    # P1: column 0 holds only (0, 0); the last column the last query row (and the one before it)
    assert matched[0] == clock[0] and matched[-1] in (clock[-1], (clock[-2] + clock[-1]) / 2)
    assert np.all(np.diff(matched) >= 0.0) and clock[0] <= matched.min() and matched.max() <= clock[-1]


# --- T-CMP-03l: the settings as a fingerprint; the minimums; as_comparison ------------------------------------------
def test_t_cmp_03l_the_settings_are_non_empty_with_short_code_names_and_plain_values():
    reference, query = pair(0)
    for arguments in (
        {"min_visible": 2, "band": 0.5},
        {"min_visible": 1, "band": 1.0, "step": "symmetric1", "weights": {"trunk": 0.0}},
    ):
        got = align(reference, query, **arguments)
        assert len(got.settings) == len(SETTING_NAMES)
        assert all(re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name) for name in got.settings)
        assert is_plain(got.settings)


@pytest.mark.parametrize("name", ["min_scale_s", "min_segment_length"])
@pytest.mark.parametrize(
    ("first", "second", "said"),
    [
        pytest.param(None, 0.5, "(reference None, query 0.5)", id="none and a number"),
        pytest.param(0.5, None, "(reference 0.5, query None)", id="a number and none"),
        pytest.param(0.5, 0.6, "(reference 0.5, query 0.6)", id="two numbers"),
    ],
)
def test_t_cmp_03l_features_made_with_different_minimums_are_refused_naming_the_setting(name, first, second, said):
    reference, query = pair(0)
    one = dataclasses.replace(reference, **{name: first})
    two = dataclasses.replace(query, **{name: second})
    message = refusal(align, one, two, min_visible=2, band=0.5)
    assert name in message and said in message  # the two values (numbers or None) are said, in this order
    other = "min_segment_length" if name == "min_scale_s" else "min_scale_s"
    assert other not in message  # only the setting that differs is named
    assert name in refusal(align, two, one, min_visible=2, band=0.5)  # either way round


def test_t_cmp_03l_equal_minimums_are_accepted_and_the_two_minimums_are_checked_independently():
    reference, query = pair(0)
    one = dataclasses.replace(reference, min_scale_s=1.5, min_segment_length=0.05)
    two = dataclasses.replace(query, min_scale_s=1.5, min_segment_length=0.05)
    got = align(one, two, min_visible=2, band=0.5)
    assert got.settings["min_scale_s"] == 1.5 and got.settings["min_segment_length"] == 0.05
    mixed = dataclasses.replace(two, min_segment_length=0.06)
    message = refusal(align, one, mixed, min_visible=2, band=0.5)
    assert "min_segment_length" in message and "min_scale_s" not in message


@pytest.mark.parametrize("name", ["min_scale_s", "min_segment_length"])
@pytest.mark.parametrize("number", [np.float32(0.5), np.float64(0.5), np.int64(1), 2, 0.25], ids=repr)
def test_t_cmp_03l_a_minimum_that_is_a_numpy_scalar_is_echoed_as_a_python_float(name, number):
    reference, query = pair(0)
    one = dataclasses.replace(reference, **{name: number})
    two = dataclasses.replace(query, **{name: number})
    got = align(one, two, min_visible=2, band=0.5)
    assert type(got.settings[name]) is float and got.settings[name] == float(number)
    other = "min_segment_length" if name == "min_scale_s" else "min_scale_s"
    assert got.settings[other] is None


@pytest.mark.parametrize("name", ["min_scale_s", "min_segment_length"])
@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(math.nan, id="NaN"),
        pytest.param(math.inf, id="infinity"),
        pytest.param(-math.inf, id="minus infinity"),
        pytest.param("SECRET", id="a string"),
        pytest.param(True, id="a bool"),
        pytest.param([0.5], id="a list"),
        pytest.param(10**400, id="an integer too large for a float"),
    ],
)
def test_t_cmp_03l_a_minimum_that_is_not_none_or_a_finite_number_is_refused_naming_it(name, bad):
    reference, query = pair(0)
    one = dataclasses.replace(reference, **{name: bad})
    two = dataclasses.replace(query, **{name: bad})
    message = refusal(align, one, two, min_visible=2, band=0.5)
    assert name in message and "SECRET" not in message


def test_t_cmp_03l_as_comparison_gives_the_ids_d_never_the_normalised_value_and_the_same_settings():
    reference, query = pair(0)
    got = align(reference, query, min_visible=2, band=0.5)
    assert got.result.status == "ok" and got.result.normalised != got.result.distance  # P1: they differ
    c = got.as_comparison("ref_01", "trainee_7")
    assert isinstance(c, Comparison)
    assert (c.reference_id, c.query_id) == ("ref_01", "trainee_7")
    assert c.distance == got.result.distance and c.distance != got.result.normalised
    assert c.distance == got.distance and type(c.distance) is float
    assert c.settings == got.settings and dict(c.settings) == dict(got.settings)
    with pytest.raises(TypeError):
        c.settings["band"] = 1.0  # type: ignore[index]
    assert got.as_comparison("a", "a").distance == got.distance  # the band refuses a segment against itself, not this


VALID_IDS = ["ref_01", "A.b-c_9", "a", "a" * 64, "0b6f3c1e-5a2d-4f8e-9c3a-7d1e2b4a6c80"]
BAD_IDS = [
    "",
    "a" * 65,
    "a b",
    "../x",
    "C:\\x",
    "x/y",
    "naïve",
    "line\nbreak",
    "tab\t",
    "end\n",
    None,
    5,
    b"abc",
]


@pytest.mark.parametrize("bad", BAD_IDS, ids=repr)
@pytest.mark.parametrize("which", ["reference_id", "query_id"])
def test_t_cmp_03l_an_id_that_is_not_a_short_code_is_refused_naming_the_argument(which, bad):
    reference, query = pair(0)
    got = align(reference, query, min_visible=2, band=0.5)
    ids = {"reference_id": "ref_01", "query_id": "trainee_7", which: bad}
    message = refusal(got.as_comparison, ids["reference_id"], ids["query_id"])
    assert which in message
    if isinstance(bad, str) and len(bad) > 1:
        assert bad not in message  # a string of the caller (a path, a name) is never echoed


@pytest.mark.parametrize("good", VALID_IDS)
def test_t_cmp_03l_short_codes_are_accepted_as_either_id(good):
    reference, query = pair(0)
    got = align(reference, query, min_visible=2, band=0.5)
    assert got.as_comparison(good, "trainee_7").reference_id == good
    assert got.as_comparison("ref_01", good).query_id == good


def test_t_cmp_03l_the_id_check_is_the_one_of_reference_band():
    """The band refuses an ID that is not a short code; ``as_comparison`` accepts exactly the IDs that it accepts."""

    def band_accepts(reference_id, query_id) -> bool:
        c = Comparison(reference_id=reference_id, query_id=query_id, distance=1.0, settings={"band": 0.2})
        try:
            reference_band([], [c])
        except CompareError:
            return False
        return True

    reference, query = pair(0)
    got = align(reference, query, min_visible=2, band=0.5)

    def align_accepts(reference_id, query_id) -> bool:
        try:
            got.as_comparison(reference_id, query_id)
        except CompareError:
            return False
        return True

    for candidate in VALID_IDS + BAD_IDS:
        assert align_accepts(candidate, "trainee_7") == band_accepts(candidate, "trainee_7"), repr(candidate)
        assert align_accepts("ref_zz", candidate) == band_accepts("ref_zz", candidate), repr(candidate)


def test_t_cmp_03l_comparisons_of_alignments_made_alike_go_through_reference_band_and_unlike_ones_do_not():
    rng = np.random.default_rng(11)
    takes = {name: random_features(rng, 10, p_invalid=0.05) for name in ("ref_a", "ref_b", "ref_c")}
    trainee = random_features(rng, 11, p_invalid=0.05, recording_id=RECORDING_QRY)
    arguments = {"min_visible": 2, "band": 0.6}

    def compare(first: str, second: str, **override):
        got = align(takes[first], takes[second], **{**arguments, **override})
        assert got.result.status == "ok"
        return got.as_comparison(first, second)

    between = [compare("ref_a", "ref_b"), compare("ref_a", "ref_c"), compare("ref_b", "ref_c")]
    trainee_alignments = [align(takes[name], trainee, **arguments) for name in takes]
    assert all(a.result.status == "ok" for a in trainee_alignments)
    own = [a.as_comparison(name, "trainee_1") for a, name in zip(trainee_alignments, takes, strict=True)]
    band = reference_band(between, own)
    assert band.status == "ok" and band.n_pairs == 3
    assert band.band_low == min(c.distance for c in between) and band.band_high == max(c.distance for c in between)
    unlike = [compare("ref_a", "ref_b"), compare("ref_a", "ref_c", band=0.7), compare("ref_b", "ref_c")]
    message = refusal(reference_band, unlike, own)
    assert "band" in message


def test_t_cmp_03l_reference_band_does_not_import_align():
    """``align.py`` imports ``Comparison`` from ``reference_band``; ``reference_band.py`` must not import ``align``."""
    source = pathlib.Path(band_module.__file__).read_text(encoding="utf-8")
    assert "compare.align" not in source and "import align" not in source
