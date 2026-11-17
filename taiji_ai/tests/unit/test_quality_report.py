"""P4.07: the schema ``quality/1`` and its file ``quality.json`` (T-QLT-11l).

The reader is strict (an unknown or missing field, a wrong type, a NaN, another version, a count that disagrees with
the others) and the writer is atomic and deterministic. The document holds counts, times, names of joints, intervals
and reasons, the parameters and the warnings: no keypoint value, no person's name, no path.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re

import pytest

from helpers.quality_fixtures import build_f1
from taiji_ai.pose.skeleton import JOINTS, SKELETON_ID
from taiji_ai.quality.chain import run_quality_arrays
from taiji_ai.quality.gaps import OUTCOME_NAMES
from taiji_ai.quality.mask import REASON_NAMES
from taiji_ai.quality.quality_io import load_quality, save_quality
from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.quality import GapCounts, OutcomeCounts, QualityReport, ReasonCounts, Timeline


@pytest.fixture(scope="module")
def report() -> QualityReport:
    t, kp, score, tracked, in_segment = build_f1()
    named = {"first_half": (0.0, 1.0), "second_half": (1.0, 2.0)}
    return run_quality_arrays(kp, score, t, tracked=tracked, in_segment=in_segment, intervals=named).report


@pytest.fixture
def doc(report, tmp_path) -> dict:
    return json.loads(json.dumps(report.model_dump(mode="json")))


def put(path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")  # NaN is written as NaN: the reader must refuse it


# --- the models -------------------------------------------------------------------------------------------------------
def test_t_qlt_11l_the_two_tables_have_one_field_per_reason_and_per_outcome():
    assert list(ReasonCounts.model_fields) == list(REASON_NAMES[1:])
    assert list(OutcomeCounts.model_fields) == list(OUTCOME_NAMES)
    assert list(GapCounts.model_fields) == ["gaps", "cells"]


def test_t_qlt_11l_the_report_states_its_schema_and_skeleton(report):
    assert report.schema_version == "quality/1" and report.skeleton == SKELETON_ID
    assert [iv.name for iv in report.intervals] == ["segment", "first_half", "second_half"]
    assert [j.joint for j in report.intervals[0].joints] == list(JOINTS)


def test_t_qlt_11l_a_model_is_frozen_and_refuses_unknown_fields(report):
    with pytest.raises(Exception, match="frozen"):
        report.warnings = ()  # type: ignore[misc]
    data = report.model_dump()
    data["extra"] = 1
    with pytest.raises(ManifestError, match="extra"):
        parse_manifest(QualityReport, data)


# --- the file ---------------------------------------------------------------------------------------------------------
def test_t_qlt_11l_save_then_load_gives_an_equal_report_and_save_returns_the_sha256(report, tmp_path):
    path = tmp_path / "run" / "quality.json"  # the folder is created
    digest = save_quality(path, report)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_quality(path) == report


def test_t_qlt_11l_the_same_report_gives_the_same_bytes(report, tmp_path):
    save_quality(tmp_path / "a.json", report)
    save_quality(tmp_path / "b.json", load_quality(tmp_path / "a.json"))
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    first = (tmp_path / "a.json").read_bytes()
    save_quality(tmp_path / "a.json", report)  # overwriting writes the same bytes
    assert (tmp_path / "a.json").read_bytes() == first


def test_t_qlt_11l_a_failed_write_leaves_the_old_file_and_no_temporary_one(report, tmp_path, monkeypatch):
    path = tmp_path / "quality.json"
    save_quality(path, report)
    before = path.read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        save_quality(path, report)
    monkeypatch.undo()
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["quality.json"]


def test_t_qlt_11l_a_missing_file_is_a_file_not_found_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_quality(tmp_path / "nope.json")


def test_t_qlt_11l_a_truncated_file_a_file_that_is_not_utf8_and_a_top_level_that_is_not_an_object(report, tmp_path):
    path = tmp_path / "quality.json"
    save_quality(path, report)
    text = path.read_text(encoding="utf-8")
    path.write_text(text[:-40], encoding="utf-8")
    with pytest.raises(ManifestError, match="not valid JSON"):
        load_quality(path)
    path.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(ManifestError, match="UTF-8"):
        load_quality(path)
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ManifestError, match="top level"):
        load_quality(path)


def mutate_fn(doc, path, fn):
    out = copy.deepcopy(doc)
    node = out
    for key in path[:-1]:
        node = node[key]
    fn(node, path[-1])
    return out


def setv(value):
    return lambda node, key: node.__setitem__(key, value)


def delete(node, key):
    del node[key]


NOT_A_NUMBER = float("nan")

BROKEN = [
    # (path to the field, what to do, a word of the message)
    (["extra"], setv(1), "extra"),
    (["intervals", 0, "extra"], setv(1), "intervals.0.extra"),
    (["intervals", 0, "joints", 3, "extra"], setv(1), "intervals.0.joints.3.extra"),
    (["warnings"], delete, "warnings"),
    (["intervals", 0, "joints", 3, "observed"], delete, "intervals.0.joints.3.observed"),
    (["intervals", 0, "rows"], setv("54"), "intervals.0.rows"),
    (["intervals", 0, "rows"], setv(True), "intervals.0.rows"),
    (["intervals", 0, "rows"], setv(54.5), "intervals.0.rows"),
    (["intervals", 0, "rows"], setv(-1), "intervals.0.rows"),
    (["intervals", 0, "t_start"], setv(NOT_A_NUMBER), "intervals.0.t_start"),
    (["timeline", "step_s"], setv(NOT_A_NUMBER), "timeline.step_s"),
    (["timeline", "step_s"], setv(-1.0), "timeline.step_s"),
    (["timeline", "torso_px"], setv(0.0), "timeline.torso_px"),
    (["params", "hampel", "scale_floor_px"], setv(NOT_A_NUMBER), "params.hampel.scale_floor_px"),
    (["schema_version"], setv("quality/2"), "schema_version"),
    (["schema_version"], delete, "schema_version"),
    (["skeleton"], setv("halpe25/1"), "skeleton"),
    (["intervals"], setv([]), "intervals"),  # the segment is always there
]


@pytest.mark.parametrize("path, change, text", BROKEN)
def test_t_qlt_11l_the_reader_refuses_a_wrong_document_and_names_the_field(doc, tmp_path, path, change, text):
    put(tmp_path / "quality.json", mutate_fn(doc, path, change))
    with pytest.raises(ManifestError) as err:
        load_quality(tmp_path / "quality.json")
    assert text in str(err.value)


def inc(delta):
    return lambda node, key: node.__setitem__(key, node[key] + delta)


SEG = ["intervals", 0]
LEAR = ["intervals", 0, "joints", 3]  # joint 3 is LEar, a left/right joint

INCONSISTENT = [
    # a hand-edited file that disagrees with itself is refused; each case breaks one rule (the message is that rule's)
    ([([*SEG, "observed"], inc(1))], "must equal cells"),
    ([([*SEG, "rows"], inc(1))], "cells must be rows * 26"),
    ([([*SEG, "missing_by_reason", "low_conf"], inc(1))], "missing_by_reason must add up to missing"),
    ([([*SEG, "unobserved_by_reason", "outlier"], inc(1))], "unobserved_by_reason must add up to"),
    (
        # the totals agree, but not_tracked has fewer unobserved cells than missing ones
        [
            ([*SEG, "unobserved_by_reason", "not_tracked"], inc(-1)),
            ([*SEG, "unobserved_by_reason", "frame_invalid"], inc(1)),
        ],
        "is below missing_by_reason for not_tracked",
    ),
    ([([*SEG, "filtered"], inc(1))], "filtered + unfiltered must equal"),
    ([([*SEG, "filtered"], inc(1)), ([*SEG, "unfiltered"], inc(-1))], "do not add up to filtered"),
    ([([*SEG, "usable_frames"], setv(54))], "usable_frames + not_tracked_frames must not exceed rows"),
    ([([*SEG, "mixed_rows"], setv(55))], "mixed_rows must not exceed rows"),
    ([([*SEG, "suspect"], setv(67))], "suspect must not exceed blocked"),
    ([([*SEG, "suspect"], inc(1))], "do not add up to suspect"),
    ([([*SEG, "blocked"], setv(10000))], "blocked must not exceed source_rows * 26"),
    ([([*SEG, "blocked"], inc(1))], "do not add up to blocked"),
    ([([*SEG, "gaps", "cells", "filled"], setv(10000))], "gaps.cells add up to more than"),
    ([([*SEG, "gaps", "gaps", "filled"], setv(10000))], "has more gaps"),
    ([([*SEG, "gaps", "gaps", "filled"], setv(0))], "has cells but no gap"),
    (
        # the totals agree, but the joints do not add up to the reasons of the interval
        [([*SEG, "missing_by_reason", "low_conf"], inc(-1)), ([*SEG, "missing_by_reason", "outlier"], inc(1))],
        "do not add up to missing_by_reason",
    ),
    ([([*LEAR, "observed"], inc(1))], "joint LEar: observed + bridged + missing must equal rows"),
    ([([*LEAR, "filtered"], setv(10000))], "joint LEar: filtered must not exceed observed + bridged"),
    ([([*LEAR, "blocked"], setv(10000))], "joint LEar: blocked must not exceed source_rows"),
    ([([*LEAR, "suspect"], setv(10000))], "joint LEar: suspect must not exceed blocked"),
    ([([*LEAR, "missing_by_reason", "outlier"], inc(1))], "joint LEar: missing_by_reason must add up to missing"),
    ([([*LEAR, "joint"], setv("Elbow"))], "is not a joint of halpe26/1"),
    ([(["intervals", 0, "name"], setv("other"))], "the first interval must be named 'segment'"),
    ([(["intervals", 1, "name"], setv("segment"))], "interval names must be distinct"),
    ([(["intervals", 2, "name"], setv("first_half"))], "interval names must be distinct"),
    ([(["intervals", 1, "name"], setv("has space"))], "intervals.1.name"),
    ([([*SEG, "t_start"], setv(99.0))], "t_start must not be after t_end"),
    ([([*SEG, "t_end"], setv(None))], "t_start and t_end must both be given or both be null"),
    ([(["timeline", "grid_rows"], setv(61))], "grid_rows must equal rows when the timeline was not resampled"),
    ([(["timeline", "grid_rows"], setv(10))], "grid_rows must equal rows when the timeline was not resampled"),
    ([(["timeline", "sampling_hz"], setv(None))], "step_s and sampling_hz must both be given or both be null"),
    ([(["timeline", "sampling_hz"], setv(10.0))], "sampling_hz must be 1 / step_s"),
    ([(["warnings"], setv(["something else"]))], "warnings.0"),
    ([(["warnings"], setv(["lr_swap_suspect@12.4"]))], "warnings.0"),
]


@pytest.mark.parametrize("changes, text", INCONSISTENT)
def test_t_qlt_11l_the_reader_refuses_counts_that_disagree(doc, tmp_path, changes, text):
    edited = doc
    for path, change in changes:
        edited = mutate_fn(edited, path, change)
    put(tmp_path / "quality.json", edited)
    with pytest.raises(ManifestError) as err:
        load_quality(tmp_path / "quality.json")
    assert text in str(err.value)


def test_t_qlt_11l_an_interval_cannot_have_more_rows_than_the_timeline(doc, tmp_path):
    few = copy.deepcopy(doc)
    few["timeline"].update(resampled=True, grid_rows=10)  # the segment has 54 grid rows
    put(tmp_path / "quality.json", few)
    with pytest.raises(ManifestError, match="grid rows"):
        load_quality(tmp_path / "quality.json")
    fewer = copy.deepcopy(doc)
    fewer["timeline"].update(rows=10)  # the segment has 54 source rows (and the grid is not the rows any more)
    fewer["timeline"]["resampled"] = True
    put(tmp_path / "quality.json", fewer)
    with pytest.raises(ManifestError, match="source rows"):
        load_quality(tmp_path / "quality.json")


def test_t_qlt_11l_the_joints_must_be_the_26_of_the_skeleton_in_order(doc, tmp_path):
    swapped = copy.deepcopy(doc)
    joints = swapped["intervals"][0]["joints"]
    joints[0], joints[1] = joints[1], joints[0]
    put(tmp_path / "quality.json", swapped)
    with pytest.raises(ManifestError, match="joints"):
        load_quality(tmp_path / "quality.json")
    short = copy.deepcopy(doc)
    short["intervals"][0]["joints"].pop()
    put(tmp_path / "quality.json", short)
    with pytest.raises(ManifestError, match="joints"):
        load_quality(tmp_path / "quality.json")


@pytest.mark.parametrize(
    "text, ok",
    [
        ("lr_swap_suspect@12.40-12.73", True),
        ("lr_swap_suspect@12.40", True),
        ("lr_swap_suspect@0.00-0.03", True),
        ("lr_swap_suspect@-0.50-0.25", True),
        ("grid_resampled", True),
        ("filter_skipped_above_nyquist", True),
        ("torso_unmeasured", True),
        ("lr_swap_suspect@12.4", False),
        ("lr_swap_suspect@12.40-", False),
        ("lr_swap_suspect", False),
        ("lr_swap_suspect@a-b", False),
        ("grid_resampled ", False),
        ("", False),
    ],
)
def test_t_qlt_11l_the_warnings_have_a_fixed_form(doc, text, ok):
    doc["warnings"] = [text]
    if ok:
        assert parse_manifest(QualityReport, doc).warnings == (text,)
    else:
        with pytest.raises(ManifestError, match="warnings"):
            parse_manifest(QualityReport, doc)


def test_t_qlt_11l_the_timeline_rules(doc):
    ok = parse_manifest(QualityReport, doc)
    assert isinstance(ok.timeline, Timeline)
    one = copy.deepcopy(doc)
    one["timeline"].update(rows=1, grid_rows=1, step_s=None, sampling_hz=None, torso_px=None)
    # an unknown step and rate are null, not 0 or NaN; the intervals of ``doc`` still have their counts, so only the
    # timeline is checked here through the model
    assert Timeline.model_validate(one["timeline"]).step_s is None
    with pytest.raises(ValueError, match="grid_rows"):
        Timeline.model_validate({**doc["timeline"], "resampled": False, "grid_rows": doc["timeline"]["rows"] + 1})
    Timeline.model_validate({**doc["timeline"], "resampled": True, "grid_rows": doc["timeline"]["rows"] + 3})


# --- what the document holds ------------------------------------------------------------------------------------------
def walk(node, keys, strings, lists):
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            walk(value, keys, strings, lists)
    elif isinstance(node, list):
        lists.append(len(node))
        for value in node:
            walk(value, keys, strings, lists)
    elif isinstance(node, str):
        strings.add(node)


def test_t_qlt_11l_the_document_holds_no_keypoint_no_name_and_no_path(report, tmp_path):
    path = tmp_path / "quality.json"
    save_quality(path, report)
    doc = json.loads(path.read_text(encoding="utf-8"))
    keys, strings, lists = set(), set(), []
    walk(doc, keys, strings, lists)
    assert not keys & {"keypoints", "scores", "xy", "path", "file", "name_of_person", "video", "recording_id"}
    assert max(lists) <= 26  # the longest list is the 26 joints: no array of coordinates
    allowed = {"quality/1", SKELETON_ID, *JOINTS, "segment", "first_half", "second_half"}
    pattern = re.compile(r"^(lr_swap_suspect@-?\d+\.\d\d(--?\d+\.\d\d)?)$")
    for text in strings:
        assert text in allowed or pattern.match(text), text
    assert not any("/" in text or "\\" in text or ":" in text for text in strings - {"quality/1", SKELETON_ID})


def test_t_qlt_11l_save_quality_refuses_anything_that_is_not_a_report(tmp_path):
    with pytest.raises(TypeError, match="QualityReport"):
        save_quality(tmp_path / "quality.json", {"schema_version": "quality/1"})  # type: ignore[arg-type]
    assert not (tmp_path / "quality.json").exists()
