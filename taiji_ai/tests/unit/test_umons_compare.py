"""P6.07: the UMONS check of the comparison chain (T-CMP-09a to 09d): segmented ids, the ``.lab`` reader, the transfer
of boundaries through the warping path, the temporal IoU, the choice of the segments by performer and the class
aggregation.

Everything here is made in the tests: ids from strings, label text, hand-made features and distances, and Kinect text
from ``helpers/umons_fixtures.py``. No dataset file is read (AGENTS.md 9.4.7); the real files are read by
``tests/golden/test_umons_compare_real.py`` (``dataset`` marker). The expected numbers are re-derived by hand in the
comments (the median of an even count is the mean of the two middle values, a percentile is linear between ranks).
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

from helpers.compare_cost_ref import RECORDING_QRY, make_features, random_features
from helpers.umons_fixtures import LICENSE, clean_text
from taiji_ai.bench import BenchError
from taiji_ai.bench.umons import UmonsError, parse_kinect
from taiji_ai.bench.umons_compare import (
    DEFAULT_BAND_BOUNDARIES,
    DEFAULT_BAND_CLASSES,
    N_UNITS,
    AlignSettings,
    BoundaryCandidates,
    BoundaryExperiment,
    BoundaryRun,
    ClassExperiment,
    ClassRun,
    LabelRow,
    PairBoundary,
    PairDistance,
    PartTransfer,
    SegmentId,
    SequenceId,
    UmonsCompareError,
    boundaries_csv,
    boundary_experiment,
    boundary_parts_csv,
    candidate_pairs,
    cap_pairs,
    check_seed,
    class_pairs_csv,
    class_selection_csv,
    class_table_csv,
    classes_experiment,
    features_of,
    find_folder,
    label_family,
    label_parts,
    list_labels,
    list_segments,
    load_labels,
    load_segment,
    make_settings,
    parse_labels,
    parse_segment_id,
    parse_sequence_id,
    plan_pairs,
    render_boundaries,
    render_classes,
    run_boundaries,
    run_classes,
    select_segments,
    summarise_boundaries,
    summarise_classes,
    temporal_iou,
    transfer_parts,
    transfer_times,
    uniform_times,
)
from taiji_ai.compare import CompareError
from taiji_ai.compare.align import Alignment, align
from taiji_ai.compare.cost import cost_matrix
from taiji_ai.compare.dtw import DtwResult
from taiji_ai.quality import QualityError
from taiji_ai.quality.layers_io import QualityLayerError


def seg(performer: int, klass: int, side: int = 1, rep: int = 1, trial: int = 1, capture: int = 1) -> SegmentId:
    return parse_segment_id(f"P{performer:02d}T{trial:02d}C{capture:02d}G{klass:02d}D{side:02d}S{rep:02d}")


def sid(performer: int, trial: int = 1, capture: int = 3) -> SequenceId:
    return parse_sequence_id(f"P{performer:02d}T{trial:02d}C{capture:02d}")


# --- T-CMP-09a: the ids ----------------------------------------------------------------------------------------------
def test_t_cmp_09a_a_segment_id_is_parsed_into_its_six_fields():
    s = parse_segment_id("P07T02C13G05D02S04")
    fields = (s.sequence.performer, s.sequence.trial, s.sequence.capture, s.klass, s.side, s.repetition)
    assert fields == (7, 2, 13, 5, 2, 4)
    assert s.performer == 7 and s.text == "P07T02C13G05D02S04" and s.sequence.text == "P07T02C13"
    assert parse_segment_id(s.text) == s  # the text gives the same id back


def test_t_cmp_09a_a_sequence_id_is_parsed_into_its_three_fields():
    q = parse_sequence_id("P12T03C15")
    assert (q.performer, q.trial, q.capture, q.text) == (12, 3, 15, "P12T03C15")


@pytest.mark.parametrize(
    "name",
    [
        "P01T01C03",  # a sequence id is not a segment id
        "P01T01C03G05D02",  # a part missing
        "P01T01C03G05D02S0",  # one digit
        "P01T01C03G05D02S004",  # three digits
        "P1T1C3G5D2S4",
        "p01T01C03G05D02S04",  # lower case
        "P01T01C03G05D02S04 ",  # a trailing space
        "P01T01C03G05D02S04\n",  # a trailing newline
        " P01T01C03G05D02S04",
        "P01T01C03G05D02S04.txt",  # a file name, not an id
        "dir/P01T01C03G05D02S04",  # a path
        "P01T01C03G05D02S04P01T01C03G05D02S04",
        "P０１T01C03G05D02S04",  # full-width digits are not the dataset's
        "P01T01C03G05D02S٠4",  # an Arabic-Indic digit
        "",
    ],
)
def test_t_cmp_09a_other_names_are_refused(name: str):
    with pytest.raises(UmonsCompareError):
        parse_segment_id(name)


@pytest.mark.parametrize(
    "name", ["P01T01C03G05D02S04", "P1T01C03", "p01T01C03", "P01T01C03 ", "P01T01C03\n", "", "P０１T01C03"]
)
def test_t_cmp_09a_a_sequence_id_refuses_other_names(name: str):
    with pytest.raises(UmonsCompareError):
        parse_sequence_id(name)


@pytest.mark.parametrize("value", [None, 5, 5.0, b"P01T01C03G05D02S04", ["P01T01C03G05D02S04"]])
def test_t_cmp_09a_a_name_that_is_not_a_string_is_refused(value):
    with pytest.raises(UmonsCompareError):
        parse_segment_id(value)  # type: ignore[arg-type]
    with pytest.raises(UmonsCompareError):
        parse_sequence_id(value)  # type: ignore[arg-type]


def test_t_cmp_09a_the_error_never_echoes_the_name():
    for parse in (parse_segment_id, parse_sequence_id):
        with pytest.raises(UmonsCompareError) as excinfo:
            parse("SECRET-name")
        assert "SECRET" not in str(excinfo.value)
    assert issubclass(UmonsCompareError, BenchError)


def test_t_cmp_09a_ids_sort_by_performer_trial_capture_class_side_repetition():
    ids = [seg(2, 1), seg(1, 3, side=2), seg(1, 3, side=1, rep=2), seg(1, 3, side=1, rep=1), seg(1, 2, trial=2)]
    expected = [
        "P01T01C01G03D01S01",
        "P01T01C01G03D01S02",
        "P01T01C01G03D02S01",
        "P01T02C01G02D01S01",
        "P02T01C01G01D01S01",
    ]
    assert [s.text for s in sorted(ids)] == expected
    assert sorted([sid(2, 1, 1), sid(1, 2, 1), sid(1, 1, 2), sid(1, 1, 1)]) == [
        sid(1, 1, 1),
        sid(1, 1, 2),
        sid(1, 2, 1),
        sid(2, 1, 1),
    ]


# --- T-CMP-09b: the label reader -------------------------------------------------------------------------------------
LAB = "0 _\n2.5 ex1l\n7.25 _\n9 tech3r\n"
LAB_ROWS = (LabelRow(0.0, "_"), LabelRow(2.5, "ex1l"), LabelRow(7.25, "_"), LabelRow(9.0, "tech3r"))


def test_t_cmp_09b_onsets_and_labels_are_read():
    assert parse_labels(LAB, "P01T01C03") == LAB_ROWS


@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"])
def test_t_cmp_09b_every_line_ending_gives_the_same_rows(eol: str):
    assert parse_labels(LAB.replace("\n", eol), "P01T01C03") == LAB_ROWS


def test_t_cmp_09b_some_lines_may_end_with_a_carriage_return_and_the_last_may_have_no_ending():
    text = "0 _\r\n2.5 ex1l\n7.25 _\r\n9 tech3r"
    assert parse_labels(text, "P01T01C03") == LAB_ROWS


def test_t_cmp_09b_blank_lines_tabs_and_spaces_are_allowed():
    text = "\n\n0\t_\n   \n  2.5   ex1l  \n\r\n7.25 _\n\n9\ttech3r\n\n"
    assert parse_labels(text, "P01T01C03") == LAB_ROWS


def test_t_cmp_09b_the_forms_of_a_decimal_time_are_read():
    rows = parse_labels("0.000000 _\n1. ex1\n.5e1 _\n6E0 ex2r\n1.2e+1 _\n", "P01T01C03")
    assert [r.t_sec for r in rows] == [0.0, 1.0, 5.0, 6.0, 12.0]  # 1.  .5e1  6E0  1.2e+1


def test_t_cmp_09b_a_time_that_goes_back_is_refused_with_its_line_number():
    with pytest.raises(UmonsCompareError, match=r"P01T01C03.*line 3"):
        parse_labels("0 _\n5 ex1l\n3 _\n", "P01T01C03")


def test_t_cmp_09b_a_time_that_does_not_increase_is_refused_with_its_line_number():
    with pytest.raises(UmonsCompareError, match=r"line 3"):
        parse_labels("0 _\n5 ex1l\n5 _\n", "P01T01C03")


def test_t_cmp_09b_the_line_number_counts_blank_lines_and_every_ending():
    with pytest.raises(UmonsCompareError, match=r"line 5"):  # 1 "0 _", 2 blank, 3 blank, 4 "1 ex1l", 5 the bad one
        parse_labels("0 _\r\n\r\n   \r\n1 ex1l\r\nbad line here\r\n", "P01T01C03")
    with pytest.raises(UmonsCompareError, match=r"line 4"):
        parse_labels("0 _\r\r1 ex1l\rx\r", "P01T01C03")
    with pytest.raises(UmonsCompareError, match=r"line 2"):
        parse_labels("0 _\n1\n", "P01T01C03")


@pytest.mark.parametrize(
    "line",
    [
        "5",  # a time with no label
        "ex1l",  # a label with no time
        "0 _ extra",  # three fields
        "1 walk",  # a label of no known kind (the times of these lines increase: only the label is wrong)
        "1 ex",  # no number
        "1 tech1x",  # a side that is not l or r
        "1 ex1lr",  # two sides
        "1 tech1ll",
        "1 ex1l_",
        "1 EX1L",
        "abc _",
        "nan _",
        "inf _",
        "-1 _",
        "-0.5 ex1",
        "1e999 _",  # not finite
        "1_0 _",  # an underscore inside a number
        "0x10 _",
        "1,5 _",
        "+3 _",
        "1.2.3 _",
    ],
)
def test_t_cmp_09b_a_bad_line_is_refused_with_its_line_number(line: str):
    with pytest.raises(UmonsCompareError, match=r"P01T01C03: line 2"):
        parse_labels(f"0 _\n{line}\n", "P01T01C03")


def test_t_cmp_09b_a_file_with_no_row_is_refused():
    for text in ("", "\n", "  \r\n\t\n"):
        with pytest.raises(UmonsCompareError, match="no rows"):
            parse_labels(text, "P01T01C03")


def test_t_cmp_09b_the_error_never_echoes_a_label_a_time_or_a_bad_id():
    with pytest.raises(UmonsCompareError) as excinfo:
        parse_labels("0 SECRETLABEL\n", "P01T01C03")
    assert "SECRET" not in str(excinfo.value)
    with pytest.raises(UmonsCompareError) as excinfo:
        parse_labels("SECRETTIME _\n", "P01T01C03")
    assert "SECRET" not in str(excinfo.value)
    with pytest.raises(UmonsCompareError) as excinfo:
        parse_labels(LAB, "SECRET")
    assert "SECRET" not in str(excinfo.value)


def test_t_cmp_09b_a_label_file_is_read_by_its_stem_and_must_be_ascii(tmp_path: Path):
    good = tmp_path / "P02T01C05.lab"
    good.write_bytes(LAB.replace("\n", "\r\n").encode("ascii"))
    assert load_labels(good) == LAB_ROWS
    bad = tmp_path / "P02T01C06.lab"
    bad.write_bytes("0 _\n1 ex1é\n".encode())
    with pytest.raises(UmonsCompareError, match=r"P02T01C06.*ASCII"):
        load_labels(bad)
    with pytest.raises(UmonsCompareError):
        load_labels(tmp_path / "not_an_id.lab")
    with pytest.raises(FileNotFoundError):
        load_labels(tmp_path / "P09T09C09.lab")


def test_t_cmp_09b_the_family_of_a_label():
    assert label_family("_") == "rest"
    assert label_family("ex1") == "ex" and label_family("ex5l") == "ex"
    assert label_family("tech8") == "tech" and label_family("tech12r") == "tech"

    class Looks:
        def __str__(self) -> str:
            return "ex1"

    for bad in ("walk", "", "ex", "tech", "Ex1", "ex1x", None, 5, b"ex1", Looks()):
        with pytest.raises(UmonsCompareError):
            label_family(bad)  # type: ignore[arg-type]


def test_t_cmp_09b_parts_run_from_an_onset_to_the_next_and_the_last_has_no_end():
    parts = label_parts(LAB_ROWS)
    assert [(p.label, p.start_s, p.end_s) for p in parts] == [
        ("_", 0.0, 2.5),
        ("ex1l", 2.5, 7.25),
        ("_", 7.25, 9.0),
        ("tech3r", 9.0, None),
    ]
    assert [p.family for p in parts] == ["rest", "ex", "rest", "tech"]
    assert label_parts((LabelRow(1.0, "ex1"),))[0].end_s is None
    assert label_parts(()) == ()


# --- T-CMP-09c: the transfer through the path and the temporal IoU ----------------------------------------------------
def test_t_cmp_09c_temporal_iou_of_hand_cases():
    assert temporal_iou(0.0, 4.0, 0.0, 4.0) == 1.0
    assert temporal_iou(0.0, 4.0, 2.0, 6.0) == pytest.approx(2.0 / 6.0)  # inter 2, union 4 + 4 - 2
    assert temporal_iou(0.0, 10.0, 2.0, 4.0) == pytest.approx(0.2)  # contained: 2 / 10
    assert temporal_iou(2.0, 4.0, 0.0, 10.0) == pytest.approx(0.2)  # symmetric
    assert temporal_iou(0.0, 2.0, 3.0, 5.0) == 0.0  # apart
    assert temporal_iou(0.0, 2.0, 2.0, 4.0) == 0.0  # touching
    assert temporal_iou(3.0, 3.0, 2.0, 4.0) == 0.0  # a moved part of no length overlaps nothing
    assert temporal_iou(0.30, 0.65, 0.2875, 0.60) == pytest.approx(0.30 / 0.3625)


@pytest.mark.parametrize(
    "args",
    [
        (0.0, 1.0, 2.0, 2.0),  # the query's part has no length
        (0.0, 1.0, 3.0, 2.0),
        (2.0, 1.0, 0.0, 1.0),  # a moved part that ends before it starts
        (math.nan, 1.0, 0.0, 1.0),
        (0.0, math.inf, 0.0, 1.0),
        (0.0, 1.0, 0.0, math.inf),  # the query's part is not finite
        (0.0, 1.0, -math.inf, 1.0),
        (0.0, 1.0, 0.0, math.nan),
        (True, 1.0, 0.0, 1.0),
    ],
)
def test_t_cmp_09c_temporal_iou_refuses_a_part_that_is_not_an_interval(args):
    with pytest.raises(UmonsCompareError):
        temporal_iou(*args)


def test_t_cmp_09c_transfer_times_interpolates_the_matched_clock():
    ref_t = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    matched = np.array([0.0, 0.5, 3.0, 3.0, 4.0])  # a flat piece (rows 2 and 3 share one query time)
    got = transfer_times(np.array([0.0, 1.5, 2.5, 3.0, 4.0]), ref_t, matched)
    assert got.tolist() == pytest.approx([0.0, 1.75, 3.0, 3.0, 4.0])  # 0.5 + 0.5 (3 - 0.5) = 1.75


def test_t_cmp_09c_a_time_outside_the_reference_clock_is_nan_never_clamped():
    ref_t = np.array([0.0, 1.0, 2.0])
    matched = np.array([0.0, 2.0, 4.0])
    got = transfer_times(np.array([-0.001, 2.001, 0.0, 2.0]), ref_t, matched)
    assert math.isnan(got[0]) and math.isnan(got[1])
    assert got[2] == 0.0 and got[3] == 4.0  # the ends are inside


def test_t_cmp_09c_a_known_warp_gives_the_true_boundaries():
    ref_t = np.linspace(0.0, 10.0, 101)
    matched = 1.5 * ref_t + 0.25  # the query runs 1.5 times slower and starts 0.25 s later
    t = np.array([0.0, 1.234, 5.0, 9.99, 10.0])
    assert transfer_times(t, ref_t, matched).tolist() == pytest.approx((1.5 * t + 0.25).tolist())


@pytest.mark.parametrize(
    "ref_t, matched, times",
    [
        ([0.0, 1.0, 1.0], [0.0, 1.0, 2.0], [0.5]),  # the reference clock does not increase
        ([0.0, 2.0, 1.0], [0.0, 1.0, 2.0], [0.5]),
        ([0.0, 1.0, 2.0], [0.0, 2.0, 1.0], [0.5]),  # the matched clock goes back
        ([0.0, 1.0, 2.0], [0.0, math.nan, 2.0], [0.5]),
        ([0.0, 1.0, math.inf], [0.0, 1.0, 2.0], [0.5]),
        ([0.0, 1.0], [0.0, 1.0, 2.0], [0.5]),  # different lengths
        ([0.0], [0.0], [0.0]),  # one row has no span
        ([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], [math.nan]),
        ([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], [[0.5]]),  # not one-dimensional
    ],
)
def test_t_cmp_09c_transfer_times_refuses_clocks_that_are_not_clocks(ref_t, matched, times):
    with pytest.raises(UmonsCompareError):
        transfer_times(np.array(times), np.array(ref_t), np.array(matched))


def test_t_cmp_09c_uniform_times_scale_the_span_without_warping():
    ref_t = np.array([0.0, 1.0, 5.0])  # only the first and the last time count
    query_t = np.array([2.0, 2.1, 3.0])
    got = uniform_times(np.array([0.0, 2.5, 5.0, 5.5]), ref_t, query_t)
    assert got[:3].tolist() == pytest.approx([2.0, 2.5, 3.0])  # 2 + t * (3 - 2) / 5 at t = 2.5
    assert math.isnan(got[3])


def hand_alignment(path, ref_t, query_t, *, status: str = "ok") -> Alignment:
    """An ``Alignment`` with a hand-made path: the cost is real, the path is the test's."""
    rng = np.random.default_rng(3)
    ref = replace(random_features(rng, len(ref_t), p_invalid=0.0), t_sec=np.array(ref_t, dtype=np.float64))
    query = replace(
        random_features(rng, len(query_t), p_invalid=0.0, recording_id=RECORDING_QRY),
        t_sec=np.array(query_t, dtype=np.float64),
    )
    cost = cost_matrix(ref, query, min_visible=2)
    params = MappingProxyType({"band": 1.0, "step": "symmetricP1", "n": len(query_t), "m": len(ref_t)})
    if status == "ok":
        result = DtwResult(np.array(path, dtype=np.int64), 0.0, "ok", 0.0, 0.0, params)
    else:
        result = DtwResult(np.empty((0, 2), dtype=np.int64), None, "no_path", None, None, params)
    return Alignment(ref, query, cost, result, MappingProxyType({"band": 1.0}))


# Reference rows at 0 .. 5 s; query rows at an uneven clock; the path puts query rows 1 and 2 on reference row 1 and
# query rows 6 and 7 on reference row 5, so the matched clock is
#   row 0: 0.00   row 1: (0.10 + 0.25) / 2 = 0.175   row 2: 0.40   row 3: 0.50   row 4: 0.70   row 5: (0.90 + 1.00) / 2
REF_T = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
QUERY_T = [0.00, 0.10, 0.25, 0.40, 0.50, 0.70, 0.90, 1.00]
PATH = [(0, 0), (1, 1), (2, 1), (3, 2), (4, 3), (5, 4), (6, 5), (7, 5)]


def test_t_cmp_09c_the_matched_clock_of_the_hand_path_is_what_the_comments_say():
    matched = hand_alignment(PATH, REF_T, QUERY_T).matched_query_times()
    assert matched.tolist() == pytest.approx([0.0, 0.175, 0.40, 0.50, 0.70, 0.95])


def test_t_cmp_09c_transfer_parts_carries_a_part_through_the_path_and_re_derives_iou_and_errors():
    alignment = hand_alignment(PATH, REF_T, QUERY_T)
    reference_rows = (LabelRow(0.0, "_"), LabelRow(1.5, "ex1l"), LabelRow(3.5, "_"), LabelRow(4.2, "tech3r"))
    query_rows = (LabelRow(0.0, "_"), LabelRow(0.30, "ex1l"), LabelRow(0.65, "_"), LabelRow(0.80, "tech3r"))
    got = transfer_parts(alignment, reference_rows, query_rows, sid(1), sid(2))
    assert got.status == "ok" and got.distance == 0.0
    assert (got.reference, got.query) == (sid(1), sid(2))
    assert (got.parts_open, got.parts_outside) == (1, 0)  # tech3r has no end; the rests are not parts
    (part,) = got.parts
    assert (part.rank, part.label, part.family) == (1, "ex1l", "ex")
    # reference 1.5 s lies between rows 1 and 2: 0.175 + 0.5 (0.40 - 0.175) = 0.2875;
    # 3.5 s lies between rows 3 and 4: 0.50 + 0.5 (0.70 - 0.50) = 0.60
    # query part [0.30, 0.65): intersection [0.30, 0.60) = 0.30, union 0.65 - 0.2875 = 0.3625
    assert part.iou == pytest.approx(0.30 / 0.3625)
    assert part.start_error_s == pytest.approx(0.2875 - 0.30)  # -0.0125: the moved start is earlier than the query's
    assert part.end_error_s == pytest.approx(0.60 - 0.65)  # -0.05
    # uniform scaling: the span 0 .. 5 s becomes 0 .. 1 s, so the factor is 0.2: [0.30, 0.70) against [0.30, 0.65)
    assert part.uniform_iou == pytest.approx(0.35 / 0.40)
    assert part.uniform_start_error_s == pytest.approx(0.0, abs=1e-12)
    assert part.uniform_end_error_s == pytest.approx(0.05)


def test_t_cmp_09c_the_first_and_the_last_row_of_the_clock_are_inside():
    alignment = hand_alignment(PATH, REF_T, QUERY_T)
    reference_rows = (LabelRow(0.0, "ex1"), LabelRow(5.0, "_"))
    query_rows = (LabelRow(0.0, "ex1"), LabelRow(1.0, "_"))
    got = transfer_parts(alignment, reference_rows, query_rows, sid(1), sid(2))
    (part,) = got.parts
    # moved [0, 0.95) against [0, 1.0)
    assert part.iou == pytest.approx(0.95) and part.start_error_s == 0.0 and part.end_error_s == pytest.approx(-0.05)


def test_t_cmp_09c_a_boundary_outside_the_reference_clock_leaves_the_part_out_and_counts_it():
    alignment = hand_alignment(PATH, REF_T, QUERY_T)
    reference_rows = (LabelRow(1.0, "ex1"), LabelRow(6.0, "_"))
    query_rows = (LabelRow(0.1, "ex1"), LabelRow(0.9, "_"))
    got = transfer_parts(alignment, reference_rows, query_rows, sid(1), sid(2))
    assert got.parts == () and (got.parts_open, got.parts_outside) == (0, 1)


def test_t_cmp_09c_a_pair_with_no_path_has_no_part_and_is_not_an_error():
    alignment = hand_alignment(PATH, REF_T, QUERY_T, status="no_path")
    reference_rows = (LabelRow(1.0, "ex1"), LabelRow(2.0, "_"))
    query_rows = (LabelRow(0.1, "ex1"), LabelRow(0.9, "_"))
    got = transfer_parts(alignment, reference_rows, query_rows, sid(1), sid(2))
    assert got.status == "no_path" and got.distance is None and got.parts == ()
    assert (got.parts_open, got.parts_outside) == (0, 0)


def test_t_cmp_09c_label_sequences_that_differ_are_refused():
    alignment = hand_alignment(PATH, REF_T, QUERY_T)
    a = (LabelRow(1.0, "ex1"), LabelRow(2.0, "_"))
    with pytest.raises(UmonsCompareError, match="label"):
        transfer_parts(alignment, a, (LabelRow(0.1, "ex2"), LabelRow(0.9, "_")), sid(1), sid(2))
    with pytest.raises(UmonsCompareError, match="label"):
        transfer_parts(alignment, a, (LabelRow(0.1, "ex1"),), sid(1), sid(2))


def test_t_cmp_09c_the_whole_chain_gives_the_offset_of_the_labels_when_the_sequences_are_equal():
    rng = np.random.default_rng(11)
    ref = random_features(rng, 40, p_invalid=0.0)  # iid frames: only the diagonal has a cost of 0
    clock = 1.5 * ref.t_sec + 0.2
    query = replace(ref, t_sec=clock, recording_id=RECORDING_QRY)
    alignment = align(ref, query, min_visible=2, band=1.0)
    assert alignment.distance == 0.0
    reference_rows = (LabelRow(0.10, "ex1"), LabelRow(0.50, "_"), LabelRow(0.90, "tech2"), LabelRow(1.20, "_"))
    shift = (0.02, -0.03, 0.04, 0.0)  # what the query's annotator did differently
    query_rows = tuple(LabelRow(1.5 * r.t_sec + 0.2 + d, r.label) for r, d in zip(reference_rows, shift, strict=True))
    got = transfer_parts(alignment, reference_rows, query_rows, sid(1), sid(2))
    assert [(p.label, p.rank) for p in got.parts] == [("ex1", 0), ("tech2", 2)]
    first, second = got.parts
    assert first.start_error_s == pytest.approx(-0.02) and first.end_error_s == pytest.approx(0.03)
    assert second.start_error_s == pytest.approx(-0.04) and second.end_error_s == pytest.approx(0.0, abs=1e-9)
    # ex1: moved [0.35, 0.95) against [0.37, 0.92): intersection 0.55, union 0.60
    assert first.iou == pytest.approx(0.55 / 0.60)
    assert second.iou == pytest.approx(0.41 / 0.45)  # moved [1.55, 2.0) against [1.59, 2.0)


# --- the aggregation of the boundary parts ---------------------------------------------------------------------------
def part(
    iou: float, start: float, end: float, family: str = "ex", uniform: tuple[float, float, float] = (0.9, 0.0, 0.0)
) -> PartTransfer:
    label = "ex1" if family == "ex" else "tech1"
    return PartTransfer(sid(1), sid(2), 1, label, family, iou, start, end, uniform[0], uniform[1], uniform[2])


def pair_of(parts, status="ok", distance=0.1, opened=0, outside=0) -> PairBoundary:
    return PairBoundary(
        sid(1), sid(2), status, None if status != "ok" else distance, tuple(parts), opened, outside, 10, 12
    )


def test_t_cmp_09c_the_boundary_statistics_are_re_derived_by_hand():
    parts = [
        part(1.0, 0.0, 0.0, "ex"),
        part(0.5, 0.2, -0.4, "ex"),
        part(0.0, -1.0, 0.9, "tech"),
        part(0.8, 0.1, 0.1, "tech"),
    ]
    summary = summarise_boundaries(
        [pair_of(parts[:2], opened=1), pair_of(parts[2:], outside=2), pair_of([], "no_path")]
    )
    assert (summary.pairs_ok, summary.pairs_no_path, summary.parts) == (2, 1, 4)
    assert (summary.parts_open, summary.parts_outside) == (1, 2)
    overall = summary.stats["all"]
    assert overall.n == 4
    assert overall.iou_median == pytest.approx(0.65)  # (0.5 + 0.8) / 2
    assert overall.iou_mean == pytest.approx(0.575)
    assert overall.iou_share_half == pytest.approx(0.75)  # 1.0, 0.5 and 0.8 reach 0.5
    assert overall.start_abs_median == pytest.approx(0.15)  # |.| = 0, 0.1, 0.2, 1.0
    assert overall.start_abs_p90 == pytest.approx(0.76)  # rank 0.9 * 3 = 2.7: 0.2 + 0.7 (1.0 - 0.2)
    assert overall.start_bias == pytest.approx(0.05)  # -1.0, 0.0, 0.1, 0.2: (0.0 + 0.1) / 2
    assert overall.end_abs_median == pytest.approx(0.25)  # 0, 0.1, 0.4, 0.9
    assert overall.end_abs_p90 == pytest.approx(0.75)  # 0.4 + 0.7 (0.9 - 0.4)
    assert overall.end_bias == pytest.approx(0.05)  # -0.4, 0.0, 0.1, 0.9: the median, not the mean 0.15
    ex = summary.stats["ex"]
    assert ex.n == 2 and ex.iou_median == pytest.approx(0.75) and ex.iou_share_half == 1.0
    assert ex.start_abs_median == pytest.approx(0.1) and ex.start_abs_p90 == pytest.approx(0.18)  # 0.9 * 0.2
    assert ex.end_bias == pytest.approx(-0.2)
    tech = summary.stats["tech"]
    assert tech.n == 2 and tech.iou_median == pytest.approx(0.4) and tech.iou_share_half == pytest.approx(0.5)
    assert summary.distance_median == pytest.approx(0.1)


def test_t_cmp_09c_the_uniform_baseline_has_its_own_statistics():
    parts = [part(0.1, 0.5, 0.5, uniform=(0.9, 0.1, -0.2)), part(0.3, 0.5, 0.5, uniform=(0.7, -0.3, 0.4))]
    summary = summarise_boundaries([pair_of(parts)])
    base = summary.uniform["all"]
    assert base.iou_median == pytest.approx(0.8) and base.iou_mean == pytest.approx(0.8)
    assert base.start_abs_median == pytest.approx(0.2) and base.start_bias == pytest.approx(-0.1)
    assert base.end_abs_median == pytest.approx(0.3) and base.end_bias == pytest.approx(0.1)
    assert summary.stats["all"].iou_median == pytest.approx(0.2)  # not mixed with the warped numbers


def test_t_cmp_09c_no_part_gives_no_number_not_a_zero():
    summary = summarise_boundaries([pair_of([], "no_path")])
    for stats in (summary.stats["all"], summary.stats["ex"], summary.stats["tech"], summary.uniform["all"]):
        assert stats.n == 0
        assert stats.iou_median is None and stats.iou_mean is None and stats.iou_share_half is None
        assert stats.start_abs_median is None and stats.end_abs_p90 is None and stats.start_bias is None
    assert summary.distance_median is None
    empty = summarise_boundaries([])
    assert (empty.pairs_ok, empty.pairs_no_path, empty.parts) == (0, 0, 0)


# --- T-CMP-09d: the settings, the choice of segments, the class aggregation -----------------------------------------
def test_t_cmp_09d_default_settings_are_the_plans_and_half_the_units():
    assert N_UNITS == 21
    s = make_settings(band=DEFAULT_BAND_CLASSES)
    assert (s.min_visible, s.band, s.step) == (11, 0.2, "symmetricP1")  # ceil(21 / 2)
    assert DEFAULT_BAND_BOUNDARIES == 0.1
    t = make_settings(band=1, min_visible=5, step="symmetric1")
    assert (t.min_visible, t.band, t.step) == (5, 1.0, "symmetric1") and isinstance(t.band, float)
    assert isinstance(t, AlignSettings)


@pytest.mark.parametrize("band", [0, -0.1, 1.5, 2, math.nan, math.inf, True, "0.2", None, 10**400, -(10**400), [0.2]])
def test_t_cmp_09d_a_bad_band_is_refused_without_an_overflow(band):
    with pytest.raises(UmonsCompareError):
        make_settings(band=band)


@pytest.mark.parametrize("min_visible", [0, -1, 22, True, 2.5, "SECRET", 10**400, -(10**400), [3]])
def test_t_cmp_09d_a_bad_min_visible_is_refused_without_an_overflow(min_visible):
    with pytest.raises(UmonsCompareError) as excinfo:
        make_settings(band=0.2, min_visible=min_visible)
    assert "SECRET" not in str(excinfo.value)


def test_t_cmp_09d_min_visible_may_be_every_count_of_units():
    assert make_settings(band=0.2, min_visible=1).min_visible == 1
    assert make_settings(band=0.2, min_visible=N_UNITS).min_visible == N_UNITS
    assert make_settings(band=0.2, min_visible=np.int64(7)).min_visible == 7


@pytest.mark.parametrize("step", ["SECRET", "symmetric2", None, 1, ""])
def test_t_cmp_09d_a_bad_step_is_refused(step):
    with pytest.raises(UmonsCompareError) as excinfo:
        make_settings(band=0.2, step=step)
    assert "SECRET" not in str(excinfo.value)


def test_t_cmp_09d_the_band_may_be_one_and_the_smallest_float():
    assert make_settings(band=1.0).band == 1.0
    assert make_settings(band=5e-324).band == 5e-324


def test_t_cmp_09d_a_seed_is_an_integer_below_two_to_the_32():
    assert [check_seed(s) for s in (0, 1, 2**32 - 1)] == [0, 1, 2**32 - 1]
    for bad in (-1, 2**32, True, 1.5, "1", None, 10**400, math.nan):
        with pytest.raises(UmonsCompareError):
            check_seed(bad)  # type: ignore[arg-type]


def groups_of(ids):
    out: dict[tuple[int, int], list[SegmentId]] = {}
    for s in ids:
        out.setdefault((s.klass, s.side), []).append(s)
    return out


def test_t_cmp_09d_the_choice_takes_one_segment_per_performer_before_a_second():
    ids = [seg(p, 1, rep=r) for p in range(1, 6) for r in (1, 2)]  # 5 performers x 2 repetitions
    chosen = select_segments(ids, per_group=3, seed=1)
    assert list(chosen) == [(1, 1)]
    assert len(chosen[(1, 1)]) == 3 and len({s.performer for s in chosen[(1, 1)]}) == 3
    four = select_segments([seg(p, 1, rep=r) for p in (1, 2) for r in (1, 2, 3)], per_group=4, seed=1)[(1, 1)]
    assert sorted(s.performer for s in four) == [1, 1, 2, 2]  # a second round: two of each, not three of one
    assert len(set(four)) == 4


def test_t_cmp_09d_the_choice_is_per_class_and_side_and_sorted():
    ids = [seg(p, g, side=d) for p in range(1, 5) for g in (1, 2) for d in (1, 2)]
    chosen = select_segments(ids, per_group=2, seed=4)
    assert list(chosen) == [(1, 1), (1, 2), (2, 1), (2, 2)]
    for (klass, side), group in chosen.items():
        assert len(group) == 2 and all((s.klass, s.side) == (klass, side) for s in group)
        assert list(group) == sorted(group)


def test_t_cmp_09d_a_group_with_fewer_segments_gives_all_of_them_and_excluded_ones_are_never_chosen():
    ids = [seg(1, 1), seg(2, 1), seg(3, 2)]
    assert select_segments(ids, per_group=5, seed=1) == {(1, 1): (seg(1, 1), seg(2, 1)), (2, 1): (seg(3, 2),)}
    rest = select_segments(ids, per_group=5, seed=1, exclude={seg(1, 1)})
    assert rest == {(1, 1): (seg(2, 1),), (2, 1): (seg(3, 2),)}
    assert select_segments(ids, per_group=5, seed=1, exclude=set(ids)) == {}
    assert select_segments([], per_group=3, seed=1) == {}
    assert select_segments(ids + ids, per_group=5, seed=1) == select_segments(ids, per_group=5, seed=1)  # no repeats


def test_t_cmp_09d_the_choice_depends_on_the_seed_and_only_on_the_seed():
    ids = [seg(p, 1, rep=r) for p in range(1, 13) for r in (1, 2, 3)]
    first = select_segments(ids, per_group=3, seed=1)
    assert select_segments(list(reversed(ids)), per_group=3, seed=1) == first  # the order of the input does not matter
    assert select_segments(ids, per_group=3, seed=1) == first
    picks = {select_segments(ids, per_group=3, seed=s)[(1, 1)] for s in range(8)}
    assert len(picks) >= 4  # the seed changes who is chosen (3 of 12 performers: a repeat is unlikely)
    inside = {select_segments(ids, per_group=1, seed=s)[(1, 1)][0].repetition for s in range(40)}
    assert inside == {1, 2, 3}  # and which repetition of the performer


def test_t_cmp_09d_the_choice_refuses_a_bad_count_or_seed():
    for bad in (0, -1, True, 1.5, None, "3", np.float64(2.0)):
        with pytest.raises(UmonsCompareError):
            select_segments([seg(1, 1)], per_group=bad, seed=1)  # type: ignore[arg-type]
    # a count beyond the float range is a count (it means every segment), not an overflow
    assert select_segments([seg(1, 1)], per_group=10**400, seed=1) == {(1, 1): (seg(1, 1),)}
    assert cap_pairs([(seg(1, 1), seg(2, 1))], 10**400, seed=1) == ((seg(1, 1), seg(2, 1)),)
    with pytest.raises(UmonsCompareError):
        select_segments([seg(1, 1)], per_group=1, seed=-1)


def test_t_cmp_09d_pairs_are_inside_one_side_and_never_one_performer_against_themself():
    refs = {(1, 1): (seg(3, 1, rep=1), seg(4, 1)), (2, 1): (seg(3, 2),)}
    queries = {(1, 1): (seg(1, 1), seg(3, 1, rep=2)), (2, 1): (seg(4, 2),), (1, 2): (seg(1, 1, side=2),)}
    plan = plan_pairs(refs, queries)
    # query P01 G01: the three references; P03 G01: only P04's (two of P03's skipped);
    # P04 G02: P03's two (P04's skipped);
    # the query on side 2 has no reference on its side and is not a skipped pair
    assert plan.skipped_same_performer == 3
    assert len(plan.pairs) == 3 + 1 + 2
    for query, reference in plan.pairs:
        assert query.performer != reference.performer and query.side == reference.side
    assert list(plan.pairs) == sorted(plan.pairs)
    assert (seg(3, 1, rep=2), seg(4, 1)) in plan.pairs
    assert plan_pairs({}, queries).pairs == () and plan_pairs(refs, {}).pairs == ()


def test_t_cmp_09d_a_cap_keeps_a_seeded_subset_in_the_original_order():
    pairs = tuple((seg(p, 1), seg(p + 1, 2)) for p in range(1, 21))
    kept = cap_pairs(pairs, 5, seed=3)
    assert len(kept) == 5 and set(kept) <= set(pairs) and list(kept) == [p for p in pairs if p in set(kept)]
    assert cap_pairs(pairs, 5, seed=3) == kept
    assert any(cap_pairs(pairs, 5, seed=s) != kept for s in range(10))
    assert cap_pairs(pairs, None, seed=3) == pairs and cap_pairs(pairs, 20, seed=3) == pairs
    assert cap_pairs(pairs, 500, seed=3) == pairs
    for bad in (0, -1, True, 2.5, "5"):
        with pytest.raises(UmonsCompareError):
            cap_pairs(pairs, bad, seed=3)  # type: ignore[arg-type]


# distances of the hand-made scenario: queries q1a (P01 G01), q1b (P02 G01), q2a (P01 G02), q2b (P02 G02) against the
# references r1 (P03 G01), r1b (P04 G01), r2 (P03 G02), r2b (P04 G02); None is a pair with no path
Q = {"q1a": seg(1, 1), "q1b": seg(2, 1), "q2a": seg(1, 2), "q2b": seg(2, 2)}
R = {"r1": seg(3, 1), "r1b": seg(4, 1), "r2": seg(3, 2), "r2b": seg(4, 2)}
TABLE = {
    "q1a": {"r1": 0.2, "r1b": 0.4, "r2": 0.9, "r2b": 0.7},
    "q1b": {"r1": 0.3, "r1b": 0.1, "r2": 0.5, "r2b": None},
    "q2a": {"r1": 0.8, "r1b": 0.6, "r2": 0.25, "r2b": None},
    "q2b": {"r1": 0.2, "r1b": 0.3, "r2": 0.6, "r2b": 0.7},
}


def scenario() -> list[PairDistance]:
    return [PairDistance(Q[q], R[r], d) for q, row in TABLE.items() for r, d in row.items()]


def test_t_cmp_09d_the_class_medians_share_and_nearest_class_are_re_derived_by_hand():
    summary = summarise_classes(scenario())
    one, two = summary.rows
    assert (one.klass, two.klass) == (1, 2)
    # class 1: own 0.2 0.4 0.3 0.1 (median (0.2 + 0.3) / 2); other 0.9 0.7 0.5 and one pair with no path (median 0.7)
    assert (one.own_pairs, one.other_pairs, one.own_no_path, one.other_no_path) == (4, 3, 0, 1)
    assert one.own_median == pytest.approx(0.25) and one.other_median == pytest.approx(0.7)
    assert one.own_closer is True
    # class 2: own 0.25 0.6 0.7 and one with no path (median 0.6); other 0.8 0.6 0.2 0.3 (median (0.3 + 0.6) / 2)
    assert (two.own_pairs, two.other_pairs, two.own_no_path, two.other_no_path) == (3, 4, 1, 0)
    assert two.own_median == pytest.approx(0.6) and two.other_median == pytest.approx(0.45)
    assert two.own_closer is False
    assert (summary.classes_compared, summary.classes_own_closer) == (2, 1) and summary.share_own_closer == 0.5
    # nearest reference: q1a 0.2 (G01), q1b 0.1 (G01), q2a 0.25 (G02), q2b 0.2 (G01, a miss)
    assert (one.queries, one.nn_queries, one.nn_correct) == (2, 2, 2)
    assert (two.queries, two.nn_queries, two.nn_correct) == (2, 2, 1)
    assert (summary.queries, summary.nn_queries, summary.nn_correct) == (4, 4, 3) and summary.nn_share == 0.75
    assert (summary.pairs_ok, summary.pairs_no_path) == (14, 2)


def test_t_cmp_09d_the_order_of_the_pairs_does_not_change_the_summary():
    pairs = scenario()
    assert summarise_classes(list(reversed(pairs))) == summarise_classes(pairs)


def test_t_cmp_09d_a_tie_goes_to_the_lower_class():
    q = seg(1, 2)
    tied = [PairDistance(q, seg(3, 1), 0.5), PairDistance(q, seg(4, 2), 0.5)]
    summary = summarise_classes(tied)
    assert summary.nn_correct == 0 and summary.nn_share == 0.0  # the nearest is the class-1 reference
    only_own = [PairDistance(q, seg(3, 2), 0.5), PairDistance(q, seg(4, 2), 0.5), PairDistance(q, seg(5, 3), 0.9)]
    assert summarise_classes(only_own).nn_correct == 1


def test_t_cmp_09d_a_class_with_no_own_distance_is_not_counted_in_the_share():
    pairs = [PairDistance(seg(1, 1), seg(3, 2), 0.4), PairDistance(seg(1, 1), seg(4, 2), 0.6)]
    (row,) = summarise_classes(pairs).rows
    assert row.own_pairs == 0 and row.own_median is None and row.own_closer is None and row.other_median == 0.5
    summary = summarise_classes(pairs)
    assert summary.classes_compared == 0 and summary.share_own_closer is None
    assert summary.nn_share == 0.0 and summary.queries == 1  # its nearest reference is of another class
    nothing = summarise_classes([])
    assert nothing.rows == () and nothing.share_own_closer is None and nothing.nn_share is None
    assert (nothing.pairs_ok, nothing.pairs_no_path, nothing.queries) == (0, 0, 0)


def test_t_cmp_09d_a_query_with_only_pairs_that_have_no_path_has_no_nearest_class():
    pairs = [PairDistance(seg(1, 1), seg(3, 1), None), PairDistance(seg(2, 1), seg(3, 1), 0.2)]
    summary = summarise_classes(pairs)
    (row,) = summary.rows
    assert (row.queries, row.nn_queries, row.nn_correct) == (2, 1, 1)
    assert summary.nn_share == 1.0 and (summary.queries, summary.nn_queries) == (2, 1)
    assert (summary.pairs_ok, summary.pairs_no_path) == (1, 1) and (row.own_pairs, row.own_no_path) == (1, 1)


def test_t_cmp_09d_a_performer_compared_with_themself_is_refused():
    with pytest.raises(UmonsCompareError, match="themself"):
        summarise_classes([PairDistance(seg(1, 1), seg(1, 1, rep=2), 0.1)])
    with pytest.raises(UmonsCompareError, match="themself"):
        summarise_classes(scenario() + [PairDistance(seg(5, 1, trial=2), seg(5, 2, trial=3), 0.1)])


def test_t_cmp_09d_pairs_across_sides_and_distances_that_are_not_distances_are_refused():
    with pytest.raises(UmonsCompareError, match="side"):
        summarise_classes([PairDistance(seg(1, 1, side=1), seg(2, 1, side=2), 0.1)])
    for bad in (math.nan, -0.1, math.inf, -math.inf, True, "0.1"):
        with pytest.raises(UmonsCompareError):
            summarise_classes([PairDistance(seg(1, 1), seg(2, 1), bad)])  # type: ignore[arg-type]
    with pytest.raises(UmonsCompareError):
        summarise_classes([("not", "a pair distance")])  # type: ignore[list-item]


def test_t_cmp_09d_a_distance_of_zero_is_a_distance():
    (row,) = summarise_classes([PairDistance(seg(1, 1), seg(2, 1), 0.0)]).rows
    assert row.own_median == 0.0 and row.own_pairs == 1 and row.own_no_path == 0


# --- the runs on hand-made features -----------------------------------------------------------------------------------
UNITS = 6


def class_features(klass: int, performer: int, repetition: int = 1, rows: int = 30):
    """A class is a pattern (iid frames of its own); a performer adds a little noise."""
    base = np.random.default_rng(100 + klass).normal(size=(rows, UNITS, 2))
    noise = np.random.default_rng(1000 * performer + repetition).normal(scale=0.02, size=base.shape)
    return make_features(base + noise, np.ones((rows, UNITS), dtype=bool))


def class_loader(name: str):
    s = parse_segment_id(name)
    return class_features(s.klass, s.performer, s.repetition)


ALL_SEGMENTS = [seg(p, g, side=d, rep=r) for g in (1, 2, 3) for d in (1, 2) for p in (1, 2, 3, 4) for r in (1, 2)]
SETTINGS = make_settings(band=1.0, min_visible=2)


def test_t_cmp_09d_run_classes_aligns_every_planned_pair_and_returns_its_distance():
    refs = select_segments(ALL_SEGMENTS, per_group=1, seed=1)
    queries = select_segments(ALL_SEGMENTS, per_group=2, seed=1, exclude={s for g in refs.values() for s in g})
    plan = plan_pairs(refs, queries)
    run = run_classes(plan.pairs, class_loader, SETTINGS)
    assert len(run.distances) == len(plan.pairs) and run.failed_segments == () and run.failed_pairs == ()
    assert run.skipped_pairs == 0
    assert [(d.query, d.reference) for d in run.distances] == list(plan.pairs)
    own = [d.distance for d in run.distances if d.query.klass == d.reference.klass]
    other = [d.distance for d in run.distances if d.query.klass != d.reference.klass]
    assert all(d is not None for d in own + other) and max(own) < min(other)  # a pattern is nearer to itself


def test_t_cmp_09d_run_classes_calls_the_loader_once_per_segment():
    calls: list[str] = []

    def counting(name: str):
        calls.append(name)
        return class_loader(name)

    pairs = [(seg(1, 1), seg(3, 1)), (seg(1, 1), seg(4, 2)), (seg(2, 1), seg(3, 1))]
    run_classes(pairs, counting, SETTINGS)
    assert sorted(calls) == sorted({s.text for pair in pairs for s in pair})


def test_t_cmp_09d_a_segment_that_fails_is_listed_and_its_pairs_are_skipped_not_hidden():
    def loader(name: str):
        if name == seg(3, 1).text:
            raise CompareError("made-up failure")
        return class_loader(name)

    pairs = [(seg(1, 1), seg(3, 1)), (seg(1, 1), seg(4, 1)), (seg(2, 1), seg(3, 1))]
    run = run_classes(pairs, loader, SETTINGS)
    assert [(d.query, d.reference) for d in run.distances] == [(seg(1, 1), seg(4, 1))]
    assert run.skipped_pairs == 2
    assert run.failed_segments == ((seg(3, 1).text, "CompareError: made-up failure"),)


@pytest.mark.parametrize(
    "error",
    [
        UmonsError("a file"),
        UmonsCompareError("a file"),
        QualityError("a file"),
        QualityLayerError("a file"),
        CompareError("a file"),
    ],
)
def test_t_cmp_09d_every_error_of_a_file_that_cannot_be_used_is_listed_by_id(error: Exception):
    def loader(name: str):
        if name == seg(3, 1).text:
            raise error
        return class_loader(name)

    run = run_classes([(seg(1, 1), seg(3, 1)), (seg(1, 1), seg(4, 1))], loader, SETTINGS)
    assert [(d.query, d.reference) for d in run.distances] == [(seg(1, 1), seg(4, 1))]
    assert run.failed_segments == ((seg(3, 1).text, f"{type(error).__name__}: a file"),)
    labels = {sid(1): REFERENCE_ROWS, sid(2): SLOW_ROWS}

    def sequence_loader(name: str):
        if name == sid(2).text:
            raise error
        return loader_for_boundaries(name)

    boundaries = run_boundaries([(sid(1), sid(2))], labels, sequence_loader, make_settings(band=1.0, min_visible=2))
    assert boundaries.pairs == () and boundaries.skipped_pairs == 1
    assert boundaries.failed_sequences == ((sid(2).text, f"{type(error).__name__}: a file"),)


def test_t_cmp_09d_an_error_that_is_not_a_known_failure_is_not_swallowed():
    def loader(name: str):
        raise ZeroDivisionError("a bug")

    with pytest.raises(ZeroDivisionError):
        run_classes([(seg(1, 1), seg(3, 1))], loader, SETTINGS)


def test_t_cmp_09d_a_pair_whose_alignment_is_refused_is_listed_with_its_ids():
    bad = make_settings(band=1.0, min_visible=N_UNITS)  # the made-up features have 6 units: the cost refuses
    run = run_classes([(seg(1, 1), seg(3, 1))], class_loader, bad)
    assert run.distances == () and len(run.failed_pairs) == 1
    query, reference, message = run.failed_pairs[0]
    assert (query, reference) == (seg(1, 1).text, seg(3, 1).text) and "min_visible" in message


def test_t_cmp_09d_lengths_that_cannot_be_matched_give_no_path_not_a_distance():
    def loader(name: str):
        s = parse_segment_id(name)
        return class_features(s.klass, s.performer, rows=10 if s.performer == 1 else 40)

    (d,) = run_classes([(seg(1, 1), seg(3, 1))], loader, SETTINGS).distances  # 10 against 40 rows: slope above 2
    assert d.distance is None


def test_t_cmp_09d_progress_is_reported_once_per_pair():
    seen: list[tuple[int, int]] = []
    pairs = [(seg(1, 1), seg(3, 1)), (seg(2, 1), seg(3, 1)), (seg(1, 2), seg(4, 2))]
    run_classes(pairs, class_loader, SETTINGS, progress=lambda done, total: seen.append((done, total)))
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_t_cmp_09d_the_class_experiment_is_deterministic_and_never_compares_a_performer_with_themself():
    kwargs = {"settings": SETTINGS, "seed": 5, "references": 3, "queries": 5}
    first = classes_experiment(ALL_SEGMENTS, class_loader, **kwargs)
    again = classes_experiment(ALL_SEGMENTS, class_loader, **kwargs)
    assert first.run.distances == again.run.distances and first.summary == again.summary
    assert first.run.distances and all(d.query.performer != d.reference.performer for d in first.run.distances)
    assert first.same_performer_skipped > 0
    # 3 classes x 2 sides: 3 references and 5 queries each (8 segments per group), every query against the 9 references
    # of its side: 2 sides x 15 queries x 9 references = 270 pairs, the ones of one performer left out
    assert len(first.run.distances) + first.same_performer_skipped == 270 and first.planned_pairs == len(
        first.run.distances
    )
    assert first.summary.share_own_closer == 1.0 and first.summary.nn_share == 1.0
    assert set(first.by_side) == {1, 2}
    assert all(s.share_own_closer == 1.0 for s in first.by_side.values())
    assert first.references.keys() == first.queries.keys()
    chosen = {s for g in first.references.values() for s in g}
    assert chosen.isdisjoint({s for g in first.queries.values() for s in g})  # a reference is never also a query
    other = classes_experiment(ALL_SEGMENTS, class_loader, **{**kwargs, "seed": 6})
    assert other.run.distances != first.run.distances  # another seed, another choice


def test_t_cmp_09d_max_pairs_keeps_a_subset_and_says_how_many_were_planned():
    capped = classes_experiment(ALL_SEGMENTS, class_loader, settings=SETTINGS, seed=5, max_pairs=40)
    full = classes_experiment(ALL_SEGMENTS, class_loader, settings=SETTINGS, seed=5)
    assert len(capped.run.distances) == 40 and capped.max_pairs == 40 and full.max_pairs is None
    assert capped.planned_pairs == 40 and capped.available_pairs == full.available_pairs == len(full.run.distances)
    assert {(d.query, d.reference) for d in capped.run.distances} <= {
        (d.query, d.reference) for d in full.run.distances
    }


def test_t_cmp_09d_the_class_tables_hold_the_settings_and_only_numbers_and_ids():
    exp = classes_experiment(ALL_SEGMENTS, class_loader, settings=SETTINGS, seed=5, references=2, queries=2)
    text = render_classes(exp)
    for needle in ("min_visible 2", "band 1", "symmetricP1", "seed 5", "Out of domain", "P0", "Class"):
        assert needle in text
    for block in text.split("\n\n"):
        rows = [r for r in block.splitlines() if r.startswith("|")]
        if rows:
            assert len({r.count("|") for r in rows}) == 1  # every row of a table has as many cells as its header
    pairs = list(csv.DictReader(io.StringIO(class_pairs_csv(exp))))
    assert len(pairs) == len(exp.run.distances)
    assert set(pairs[0]) >= {"side", "query", "query_class", "reference", "reference_class", "distance", "status"}
    assert {p["min_visible"] for p in pairs} == {"2"} and {p["band"] for p in pairs} == {"1.0"}
    table = list(csv.DictReader(io.StringIO(class_table_csv(exp))))
    assert [r["class"] for r in table if r["side"] == "all"] == ["1", "2", "3"]
    assert {r["side"] for r in table} == {"all", "1", "2"}
    row = next(r for r in table if r["side"] == "all" and r["class"] == "1")
    expected = exp.summary.rows[0]
    assert float(row["own_median"]) == pytest.approx(expected.own_median) and row["own_closer"] == "1"


def test_t_cmp_09d_a_missing_number_is_an_empty_field_in_the_csv():
    # both repetitions of class 1 are one performer's: the query of class 1 has no pair with its own class
    ids = [seg(1, 1, rep=1), seg(1, 1, rep=2), seg(3, 2)]
    exp = classes_experiment(ids, class_loader, settings=SETTINGS, seed=1, references=1, queries=1)
    assert [(d.query.klass, d.reference.klass) for d in exp.run.distances] == [(1, 2)]
    row = next(r for r in csv.DictReader(io.StringIO(class_table_csv(exp))) if r["side"] == "all")
    assert row["own_median"] == "" and row["own_closer"] == ""


# --- the boundary experiment on hand-made features --------------------------------------------------------------------
def routine_features(rows: int = 40, speed: float = 1.0, offset: float = 0.0, seed: int = 7):
    """Every performer of a routine has the same frames (iid, so only the diagonal is free); a slower one has a longer
    clock: the clock of a performer at ``speed`` is ``speed * k / 30 + offset`` seconds."""
    rng = np.random.default_rng(seed)
    base = make_features(rng.normal(size=(rows, UNITS, 2)), np.ones((rows, UNITS), dtype=bool))
    return replace(base, t_sec=speed * np.arange(rows) / 30.0 + offset)


REFERENCE_ROWS = (
    LabelRow(0.0, "_"),
    LabelRow(0.20, "ex1l"),
    LabelRow(0.60, "_"),
    LabelRow(0.90, "tech2r"),
    LabelRow(1.20, "_"),
)
SLOW_ROWS = (
    LabelRow(0.0, "_"),
    LabelRow(0.35, "ex1l"),
    LabelRow(0.90, "_"),
    LabelRow(1.40, "tech2r"),
    LabelRow(1.80, "_"),
)


def test_t_cmp_09d_candidate_pairs_are_other_performers_of_one_capture_with_equal_labels():
    a, b = REFERENCE_ROWS, SLOW_ROWS
    different = (LabelRow(0.0, "_"), LabelRow(0.2, "ex2l"), LabelRow(0.6, "_"))
    labels = {
        sid(1, 1, 3): a,
        sid(2, 1, 3): b,  # the same labels in another time: a pair
        sid(2, 2, 3): different,  # other performer, same capture, other labels: counted
        sid(1, 2, 3): a,  # the same performer as the first: never a pair with it
        sid(3, 1, 4): a,  # another capture
        sid(4, 1, 3): a,  # no Kinect file
    }
    available = {sid(1, 1, 3), sid(2, 1, 3), sid(2, 2, 3), sid(1, 2, 3), sid(3, 1, 4)}
    found = candidate_pairs(labels, available)
    # capture 3, different performers, both available: (P01T01, P02T01) equal; (P01T01, P02T02) differs;
    # (P01T02, P02T01) equal; (P01T02, P02T02) differs
    assert found.usable == ((sid(1, 1, 3), sid(2, 1, 3)), (sid(1, 2, 3), sid(2, 1, 3)))
    assert found.different_labels == 2
    assert found.labels_without_sequence == 1 and found.sequences_without_labels == 0
    for reference, query in found.usable:
        assert reference < query and reference.capture == query.capture and reference.performer != query.performer
    extra = candidate_pairs(labels, available | {sid(5, 1, 9)})
    assert extra.sequences_without_labels == 1 and extra.usable == found.usable


def test_t_cmp_09d_a_label_sequence_equal_in_order_includes_the_rests():
    base = (LabelRow(0.0, "_"), LabelRow(1.0, "ex1"), LabelRow(2.0, "_"))
    no_rest = (LabelRow(1.0, "ex1"), LabelRow(2.0, "_"))
    found = candidate_pairs({sid(1): base, sid(2): no_rest}, {sid(1), sid(2)})
    assert found.usable == () and found.different_labels == 1


def loader_for_boundaries(name: str):
    q = parse_sequence_id(name)
    return routine_features(speed=1.0 if q.performer == 1 else 1.5, offset=0.0 if q.performer == 1 else 0.2)


def test_t_cmp_09d_run_boundaries_gives_the_offset_of_the_labels_for_equal_sequences():
    pairs = [(sid(1), sid(2))]
    labels = {sid(1): REFERENCE_ROWS, sid(2): SLOW_ROWS}
    run = run_boundaries(pairs, labels, loader_for_boundaries, make_settings(band=1.0, min_visible=2))
    assert run.failed_sequences == () and run.failed_pairs == () and run.skipped_pairs == 0
    (result,) = run.pairs
    # the query clock is 1.5 t + 0.2 and the path is the diagonal: ex1l [0.20, 0.60) moves to [0.50, 1.10)
    # against [0.35, 0.90): errors 0.15 and 0.20; tech2r [0.90, 1.20) moves to [1.55, 2.0) against [1.40, 1.80)
    assert result.status == "ok" and result.distance == 0.0 and (result.parts_open, result.parts_outside) == (0, 0)
    first, second = result.parts
    assert first.start_error_s == pytest.approx(0.15) and first.end_error_s == pytest.approx(0.20)
    assert first.iou == pytest.approx(0.40 / 0.75)  # intersection [0.5, 0.9) = 0.4, union [0.35, 1.1) = 0.75
    assert second.start_error_s == pytest.approx(0.15) and second.end_error_s == pytest.approx(0.20)


def test_t_cmp_09d_run_boundaries_reports_failed_sequences_and_pairs_that_it_skipped():
    def loader(name: str):
        if name == sid(3).text:
            raise CompareError("made-up failure")
        return loader_for_boundaries(name)

    labels = {sid(1): REFERENCE_ROWS, sid(2): SLOW_ROWS, sid(3): REFERENCE_ROWS}
    run = run_boundaries([(sid(1), sid(2)), (sid(1), sid(3))], labels, loader, make_settings(band=1.0, min_visible=2))
    assert len(run.pairs) == 1 and run.skipped_pairs == 1
    assert run.failed_sequences == ((sid(3).text, "CompareError: made-up failure"),)


def test_t_cmp_09d_run_boundaries_counts_a_pair_with_no_path():
    def loader(name: str):
        return routine_features(rows=10 if name == sid(1).text else 40)

    labels = {sid(1): REFERENCE_ROWS, sid(2): SLOW_ROWS}
    run = run_boundaries([(sid(1), sid(2))], labels, loader, make_settings(band=1.0, min_visible=2))
    assert run.pairs[0].status == "no_path" and run.pairs[0].parts == ()


def test_t_cmp_09d_run_boundaries_refuses_pairs_with_different_labels_before_running():
    labels = {sid(1): REFERENCE_ROWS, sid(2): SLOW_ROWS[:-1]}
    with pytest.raises(UmonsCompareError, match="label"):
        run_boundaries([(sid(1), sid(2))], labels, loader_for_boundaries, make_settings(band=1.0, min_visible=2))
    with pytest.raises(UmonsCompareError, match="label"):
        run_boundaries([(sid(1), sid(9))], labels, loader_for_boundaries, make_settings(band=1.0, min_visible=2))


def test_t_cmp_09d_the_boundary_experiment_samples_pairs_by_the_seed_and_counts_the_rest():
    labels, available = {}, set()
    for p in range(1, 7):
        labels[sid(p, 1, 3)] = REFERENCE_ROWS if p % 2 else SLOW_ROWS  # equal in time shifts, labels equal in kind
        available.add(sid(p, 1, 3))
    labels[sid(7, 1, 3)] = REFERENCE_ROWS[:-1]  # a performer whose labels differ from everyone's
    available.add(sid(7, 1, 3))
    settings = make_settings(band=1.0, min_visible=2)
    full = boundary_experiment(labels, available, loader_for_boundaries, settings=settings, seed=2)
    assert full.candidates.different_labels == 6 and len(full.candidates.usable) == 15  # 6 choose 2
    assert len(full.run.pairs) == 15 and full.max_pairs is None and full.seed == 2
    capped = boundary_experiment(labels, available, loader_for_boundaries, settings=settings, seed=2, max_pairs=4)
    assert len(capped.run.pairs) == 4 and capped.max_pairs == 4
    assert {(p.reference, p.query) for p in capped.run.pairs} <= set(full.candidates.usable)
    again = boundary_experiment(labels, available, loader_for_boundaries, settings=settings, seed=2, max_pairs=4)
    assert [(p.reference, p.query) for p in again.run.pairs] == [(p.reference, p.query) for p in capped.run.pairs]
    assert full.summary.pairs_ok == 15 and full.summary.parts == 30


def test_t_cmp_09d_the_boundary_tables_and_csv_hold_numbers_and_ids_only():
    labels = {sid(1): REFERENCE_ROWS, sid(2): SLOW_ROWS}
    exp = boundary_experiment(
        labels, set(labels), loader_for_boundaries, settings=make_settings(band=1.0, min_visible=2), seed=3
    )
    text = render_boundaries(exp)
    for needle in ("min_visible 2", "band 1", "seed 3", "Out of domain", "uniform", "P01T01C03", "IoU"):
        assert needle in text
    for block in text.split("\n\n"):
        rows = [r for r in block.splitlines() if r.startswith("|")]
        if rows:
            assert len({r.count("|") for r in rows}) == 1
    parts = list(csv.DictReader(io.StringIO(boundary_parts_csv(exp))))
    assert [(p["reference"], p["query"], p["label"], p["family"]) for p in parts] == [
        ("P01T01C03", "P02T01C03", "ex1l", "ex"),
        ("P01T01C03", "P02T01C03", "tech2r", "tech"),
    ]
    assert set(parts[0]) >= {"iou", "start_error_s", "end_error_s", "uniform_iou", "min_visible", "band", "step"}
    assert not {"start_s", "end_s", "ref_start_s", "query_start_s"} & set(parts[0])  # no label time is written
    pairs = list(csv.DictReader(io.StringIO(boundaries_csv(exp))))
    assert len(pairs) == 1 and pairs[0]["status"] == "ok" and pairs[0]["parts"] == "2"


# --- the chain over Kinect text and the folders -----------------------------------------------------------------------
def test_features_of_a_kinect_sequence_has_the_default_units_and_the_files_clock():
    sequence = parse_kinect(clean_text(60), "P01T01C03")
    features = features_of(sequence)
    assert len(features.units) == N_UNITS and features.valid.shape[1] == N_UNITS
    assert features.t_sec[0] == 0.0 and len(features.t_sec) >= 59  # the grid of the chain, from the first row
    assert features.valid.any()
    assert features.data_sources[0].dataset_id == "D12"


def test_load_segment_reads_a_segmented_file_through_its_parent_sequence_id(tmp_path: Path):
    path = tmp_path / "P04T02C07G03D01S02.txt"
    path.write_text(clean_text(30), encoding="ascii")
    sequence = load_segment(path)
    assert sequence.sequence_id == "P04T02C07" and len(sequence.t_sec) == 30


def test_load_segment_names_the_segment_in_an_error_and_never_the_path(tmp_path: Path):
    folder = tmp_path / "private_folder"
    folder.mkdir()
    bad = folder / "P04T02C07G03D01S02.txt"
    bad.write_text("1000 1 2 3\n", encoding="ascii")  # not 76 numbers
    with pytest.raises(UmonsCompareError) as excinfo:
        load_segment(bad)
    assert "P04T02C07G03D01S02" in str(excinfo.value) and "private_folder" not in str(excinfo.value)
    nonascii = folder / "P04T02C07G03D01S03.txt"
    nonascii.write_bytes("1000é".encode())
    with pytest.raises(UmonsCompareError, match="ASCII"):
        load_segment(nonascii)
    with pytest.raises(UmonsCompareError):
        load_segment(folder / "P04T02C07.txt")  # a sequence file is not a segment
    with pytest.raises(FileNotFoundError):
        load_segment(folder / "P04T02C07G03D01S09.txt")


def make_folder(root: Path, name: str, files: list[str], license_text: str | None = LICENSE, nest: str = "") -> Path:
    folder = root / nest / name if nest else root / name
    folder.mkdir(parents=True)
    for f in files:
        (folder / f).write_text("x", encoding="ascii")
    if license_text is not None:
        (folder / "License.txt").write_text(license_text, encoding="ascii")
    return folder


def test_find_folder_looks_in_the_root_in_extracted_and_at_the_folder_itself(tmp_path: Path):
    inner = make_folder(tmp_path / "a", "Labels", ["P01T01C03.lab"])
    assert find_folder(tmp_path / "a", "Labels") == inner
    nested = make_folder(tmp_path / "b", "Labels", ["P01T01C03.lab"], nest="extracted")
    assert find_folder(tmp_path / "b", "Labels") == nested
    assert find_folder(nested, "Labels") == nested  # the folder itself


def test_find_folder_refuses_what_is_not_the_dataset_without_naming_a_path(tmp_path: Path):
    with pytest.raises(UmonsCompareError) as excinfo:
        find_folder(tmp_path / "private_root", "Labels")
    assert "private_root" not in str(excinfo.value)
    (tmp_path / "empty").mkdir()
    with pytest.raises(UmonsCompareError, match="Labels"):
        find_folder(tmp_path / "empty", "Labels")
    make_folder(tmp_path / "nolic", "Labels", ["P01T01C03.lab"], license_text=None)
    with pytest.raises(UmonsCompareError, match="License"):
        find_folder(tmp_path / "nolic", "Labels")
    make_folder(tmp_path / "otherlic", "Labels", ["P01T01C03.lab"], license_text="MIT\n")
    with pytest.raises(UmonsCompareError, match="CC BY-NC-SA"):
        find_folder(tmp_path / "otherlic", "Labels")
    with pytest.raises(UmonsCompareError):
        find_folder(tmp_path / "empty", "Elsewhere")  # only the three folders of the dataset


def test_list_segments_and_list_labels_map_ids_to_files_in_order(tmp_path: Path):
    names = ["P02T01C03G02D01S01.txt", "P01T01C03G01D01S01.txt", "P01T01C03G01D02S01.txt"]
    folder = make_folder(tmp_path, "Segmented_Kinect", names)
    found = list_segments(folder)
    assert list(found) == sorted(found) and [s.text for s in found] == [
        "P01T01C03G01D01S01",
        "P01T01C03G01D02S01",
        "P02T01C03G02D01S01",
    ]
    assert all(path.parent == folder for path in found.values())
    labels = make_folder(tmp_path, "Labels", ["P02T01C03.lab", "P01T01C03.lab"])
    assert [q.text for q in list_labels(labels)] == ["P01T01C03", "P02T01C03"]


def test_list_segments_and_list_labels_refuse_a_foreign_entry_without_naming_it(tmp_path: Path):
    folder = make_folder(tmp_path / "s", "Segmented_Kinect", ["P01T01C03G01D01S01.txt", "SECRET_notes.txt"])
    with pytest.raises(UmonsCompareError) as excinfo:
        list_segments(folder)
    assert "SECRET" not in str(excinfo.value)
    labels = make_folder(tmp_path / "l", "Labels", ["P01T01C03.lab", "P01T01C03.txt"])
    with pytest.raises(UmonsCompareError):
        list_labels(labels)
    with pytest.raises(UmonsCompareError):  # a segment name in the labels folder, and a label name in the segments one
        list_labels(make_folder(tmp_path / "m", "Labels", ["P01T01C03G01D01S01.lab"]))
    with pytest.raises(UmonsCompareError):
        list_segments(make_folder(tmp_path / "n", "Segmented_Kinect", ["P01T01C03.txt"]))
    sub = make_folder(tmp_path / "o", "Labels", ["P01T01C03.lab"])
    (sub / "P02T01C03.lab").mkdir()  # a folder with a label's name is not a file
    with pytest.raises(UmonsCompareError):
        list_labels(sub)


# --- found by the mutation check ----------------------------------------------------------------------------
def test_t_cmp_09c_a_clock_that_is_not_numbers_is_refused_as_such():
    for bad in (["a", "b"], "abc", [None, 1.0], [object()]):
        with pytest.raises(UmonsCompareError):
            transfer_times(bad, [0.0, 1.0], [0.0, 1.0])
        with pytest.raises(UmonsCompareError):
            transfer_times([0.5], bad, [0.0, 1.0])
        with pytest.raises(UmonsCompareError):
            transfer_times([0.5], [0.0, 1.0], bad)


def test_t_cmp_09c_the_uniform_line_needs_two_rows_and_an_increasing_clock_on_both_sides():
    with pytest.raises(UmonsCompareError):
        uniform_times([0.5], [0.0, 1.0, 2.0], [3.0])  # the query has one row: no span
    with pytest.raises(UmonsCompareError):
        uniform_times([0.5], [0.0], [3.0, 4.0])
    with pytest.raises(UmonsCompareError):
        uniform_times([0.5], [0.0, 1.0, 2.0], [3.0, 5.0, 4.0])  # the query clock goes back
    with pytest.raises(UmonsCompareError):
        uniform_times([0.5], [0.0, 1.0, 1.0], [3.0, 4.0, 5.0])
    with pytest.raises(UmonsCompareError):
        uniform_times([0.5], [0.0, 1.0, 2.0], [3.0, 3.0, 3.0])  # a span of no length


def test_t_cmp_09c_a_moved_part_of_no_length_has_an_iou_of_zero_and_its_errors():
    # reference rows 1 and 2 are matched to one query row (a horizontal run of the path), so a part from 1.0 s to 2.0 s
    # moves to a point: [0.25, 0.25) against the query's [0.20, 0.30)
    path = [(0, 0), (1, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    alignment = hand_alignment(path, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], [0.0, 0.25, 0.5, 0.75, 1.0])
    reference_rows = (LabelRow(1.0, "ex1"), LabelRow(2.0, "_"))
    query_rows = (LabelRow(0.20, "ex1"), LabelRow(0.30, "_"))
    (part,) = transfer_parts(alignment, reference_rows, query_rows, sid(1), sid(2)).parts
    assert part.iou == 0.0
    assert part.start_error_s == pytest.approx(0.05) and part.end_error_s == pytest.approx(-0.05)


def test_t_cmp_09c_a_part_ends_inside_the_clock_when_both_ends_are_inside():
    alignment = hand_alignment(PATH, REF_T, QUERY_T)
    # the start is inside and the end is not: the part is counted as outside, never clamped
    got = transfer_parts(
        alignment,
        (LabelRow(2.0, "ex1"), LabelRow(5.5, "_")),
        (LabelRow(0.3, "ex1"), LabelRow(0.9, "_")),
        sid(1),
        sid(2),
    )
    assert got.parts == () and got.parts_outside == 1
    before = transfer_parts(
        alignment,
        (LabelRow(-0.5, "ex1"), LabelRow(2.0, "_")),
        (LabelRow(0.0, "ex1"), LabelRow(0.3, "_")),
        sid(1),
        sid(2),
    )
    assert before.parts == () and before.parts_outside == 1


def test_t_cmp_09d_a_pair_with_the_same_performer_in_another_trial_is_never_made():
    refs = {(1, 1): (seg(3, 1, trial=2),)}
    queries = {(1, 1): (seg(3, 1, trial=1, rep=2), seg(1, 1))}
    plan = plan_pairs(refs, queries)
    assert plan.pairs == ((seg(1, 1), seg(3, 1, trial=2)),) and plan.skipped_same_performer == 1


def test_t_cmp_09d_pairs_are_sorted_whatever_the_order_of_the_input():
    refs = {(2, 1): (seg(9, 2),), (1, 1): (seg(8, 1),)}
    queries = {(2, 1): (seg(2, 2), seg(1, 2)), (1, 1): (seg(4, 1), seg(3, 1))}
    plan = plan_pairs(refs, queries)
    assert [q.performer for q, _ in plan.pairs[:4]] == [1, 1, 2, 2] and list(plan.pairs) == sorted(plan.pairs)


def test_t_cmp_09d_the_seed_is_checked_even_when_nothing_is_capped():
    with pytest.raises(UmonsCompareError):
        cap_pairs([(seg(1, 1), seg(2, 1))], None, seed=-1)
    with pytest.raises(UmonsCompareError):
        cap_pairs([(seg(1, 1), seg(2, 1))], 1, seed=2**32)


def test_t_cmp_09d_an_equal_median_is_not_closer_and_a_class_with_no_own_is_not_counted_as_closer():
    tied = [PairDistance(seg(1, 1), seg(3, 1), 0.5), PairDistance(seg(1, 1), seg(4, 2), 0.5)]
    (row,) = summarise_classes(tied).rows
    assert row.own_median == row.other_median == 0.5 and row.own_closer is False
    mixed = tied[:1] + [PairDistance(seg(1, 1), seg(4, 2), 0.9)]  # class 1 is closer to itself
    only_other = [PairDistance(seg(2, 2), seg(3, 1), 0.2), PairDistance(seg(2, 2), seg(4, 1), 0.4)]  # class 2: no own
    summary = summarise_classes(mixed + only_other)
    assert [r.own_closer for r in summary.rows] == [True, None]
    assert (summary.classes_compared, summary.classes_own_closer, summary.share_own_closer) == (1, 1, 1.0)
    none_closer = summarise_classes(only_other)
    assert (none_closer.classes_compared, none_closer.classes_own_closer) == (0, 0)


def test_t_cmp_09d_features_of_a_file_with_two_bodies_leave_those_rows_without_a_value():
    from helpers.umons_fixtures import line, skeleton, text_of

    rows = []
    for i in range(80):
        rows.append(line(1_000_000 + 33 * i, skeleton(i)))
        if 40 <= i <= 45:  # two skeletons for the timestamps of rows 40 to 45: whose are they? (not the target's)
            rows.append(line(1_000_000 + 33 * i, skeleton(i, shift=600.0)))
    features = features_of(parse_kinect(text_of(rows), "P01T01C03"))
    middle = int(np.argmin(np.abs(features.t_sec - 0.033 * 42.5)))
    assert not features.valid[middle].any()  # nothing is observed there
    assert features.valid[5].all() and features.valid[70].all()  # and the rows around are


def test_t_cmp_09d_the_quality_settings_reach_the_features():
    from taiji_ai.quality.chain import QualityParams
    from taiji_ai.quality.resample import ResampleParams

    sequence = parse_kinect(clean_text(60), "P01T01C03")
    default = features_of(sequence)
    slow = features_of(sequence, QualityParams(resample=ResampleParams(grid_hz=10.0)))
    assert len(slow.t_sec) < len(default.t_sec) / 2
    from taiji_ai.bench.umons_compare import features_loader

    loader = features_loader(
        {"P01T01C03": Path("unused")}, lambda path: sequence, QualityParams(resample=ResampleParams(grid_hz=10.0))
    )
    assert len(loader("P01T01C03").t_sec) == len(slow.t_sec)


def test_find_folder_names_what_is_wrong_and_knows_only_the_three_folders(tmp_path: Path):
    with pytest.raises(UmonsCompareError, match="does not exist"):
        find_folder(tmp_path / "gone", "Labels")
    make_folder(
        tmp_path / "x", "Elsewhere", ["P01T01C03.lab"]
    )  # a folder that exists, with a license, not a dataset one
    with pytest.raises(UmonsCompareError, match="must be one of"):
        find_folder(tmp_path / "x", "Elsewhere")


def test_run_boundaries_checks_every_pair_before_it_loads_anything():
    loaded: list[str] = []

    def loader(name: str):
        loaded.append(name)
        return loader_for_boundaries(name)

    labels = {sid(1): REFERENCE_ROWS, sid(2): SLOW_ROWS, sid(3): REFERENCE_ROWS[:-1]}
    with pytest.raises(UmonsCompareError, match="different label"):
        run_boundaries([(sid(1), sid(2)), (sid(1), sid(3))], labels, loader, make_settings(band=1.0, min_visible=2))
    assert loaded == []


def test_run_boundaries_lists_a_refused_pair_as_reference_then_query():
    bad = make_settings(band=1.0, min_visible=N_UNITS)  # 6 units in the made-up features: the cost refuses
    labels = {sid(1): REFERENCE_ROWS, sid(2): SLOW_ROWS}
    run = run_boundaries([(sid(1), sid(2))], labels, loader_for_boundaries, bad)
    assert run.pairs == () and len(run.failed_pairs) == 1
    reference, query, message = run.failed_pairs[0]
    assert (reference, query) == (sid(1).text, sid(2).text) and "min_visible" in message


# --- the tables and CSV of hand-made experiments: every number is one that the test chose ------------------------
TABLE_HEADER = (
    "side,class,queries,own_pairs,other_pairs,own_no_path,other_no_path,own_median,other_median,own_closer,"
    "nn_queries,nn_correct,min_visible,band,step"
).split(",")
PAIRS_HEADER = (
    "reference,query,status,distance,parts,parts_open,parts_outside,reference_rows,query_rows,min_visible,band,step"
).split(",")
PARTS_HEADER = (
    "reference,query,rank,label,family,iou,start_error_s,end_error_s,uniform_iou,uniform_start_error_s,"
    "uniform_end_error_s,min_visible,band,step"
).split(",")


def hand_class_experiment() -> ClassExperiment:
    distances = tuple(scenario())
    one = tuple(d for d in distances if d.query.klass == 1)
    run = ClassRun(
        distances,
        (("P09T01C01G01D01S01", "UmonsCompareError: made | up"),),
        (("P01T01C01G01D01S01", "P04T01C01G02D01S01", "CompareError: refused"),),
        4,
        1.5,
    )
    return ClassExperiment(
        settings=SETTINGS,
        seed=7,
        references_per_group=2,
        queries_per_group=3,
        max_pairs=16,
        references={(1, 1): (R["r1"],), (2, 1): (R["r2"], R["r2b"])},
        queries={(1, 1): (Q["q1a"],)},
        available_pairs=20,
        planned_pairs=16,
        same_performer_skipped=3,
        run=run,
        summary=summarise_classes(distances),
        by_side={1: summarise_classes(distances), 2: summarise_classes(one)},
    )


def test_the_class_report_has_the_numbers_the_summary_has():
    text = render_classes(hand_class_experiment())
    assert "| G01 | 2 | 4 | 3 | 0.2500 | 0.7000 | 2.80 | yes | 2 / 2 | 0 / 1 |" in text
    assert "| G02 | 2 | 3 | 4 | 0.6000 | 0.4500 | 0.75 | no | 1 / 2 | 1 / 0 |" in text
    totals = (
        "Classes where the own class is closer: 1 of 2 (50.0 %). Nearest-reference class correct: 3 of 4 queries "
        "(75.0 %). Pairs with a distance 14, with no path 2."
    )
    assert text.count(totals) == 2  # pooled and side D01 (the same pairs); side D02 has class 1 only
    assert "Classes where the own class is closer: 1 of 1 (100.0 %). Nearest-reference class correct: 2 of 2" in text
    assert "### Side D01" in text and "### Side D02" in text
    assert (
        "Sample: 2 references and 3 queries per class and side; pairs available 20 (capped to 16), aligned 16, "
        "left out because both were one performer's 3, skipped for a failed segment 4, refused 1; segments that "
        "failed 1; 1.5 s." in text
    )
    assert "| G01 | D01 | P03T01C01G01D01S01 | P01T01C01G01D01S01 |" in text
    assert "| G02 | D01 | P03T01C01G02D01S01, P04T01C01G02D01S01 | none |" in text
    assert "| P09T01C01G01D01S01 | UmonsCompareError: made / up |" in text  # a pipe never breaks a table
    assert "| P01T01C01G01D01S01 | P04T01C01G02D01S01 | CompareError: refused |" in text
    assert "Settings: min_visible 2 of 21 units, band 1, step symmetricP1, weights 1 for every unit" in text
    assert "seed 7." in text
    assert "no cap" in render_classes(replace_max_pairs(hand_class_experiment(), None))


def replace_max_pairs(exp, value):
    return replace(exp, max_pairs=value)


def test_the_class_csv_files_have_the_columns_and_the_values_the_summary_has():
    exp = hand_class_experiment()
    pairs = list(csv.reader(io.StringIO(class_pairs_csv(exp))))
    assert pairs[0] == [
        "side",
        "query",
        "query_class",
        "reference",
        "reference_class",
        "distance",
        "status",
        "min_visible",
        "band",
        "step",
    ]
    assert [
        "1",
        "P02T01C01G01D01S01",
        "1",
        "P04T01C01G02D01S01",
        "2",
        "",
        "no_path",
        "2",
        "1.0",
        "symmetricP1",
    ] in pairs
    assert ["1", "P01T01C01G01D01S01", "1", "P03T01C01G01D01S01", "1", "0.2", "ok", "2", "1.0", "symmetricP1"] in pairs
    table = list(csv.reader(io.StringIO(class_table_csv(exp))))
    assert table[0] == TABLE_HEADER
    by_key = {(r[0], r[1]): r for r in table[1:]}
    one, two = by_key[("all", "1")], by_key[("all", "2")]
    assert one[2:7] == ["2", "4", "3", "0", "1"] and one[9:] == ["1", "2", "2", "2", "1.0", "symmetricP1"]
    assert (float(one[7]), float(one[8])) == pytest.approx((0.25, 0.7))
    assert two[2:7] == ["2", "3", "4", "1", "0"] and two[9:] == ["0", "2", "1", "2", "1.0", "symmetricP1"]
    assert (float(two[7]), float(two[8])) == pytest.approx((0.6, 0.45))
    assert [r[0] for r in table[1:]] == ["all", "all", "1", "1", "2"]
    selection = list(csv.reader(io.StringIO(class_selection_csv(exp))))
    assert selection == [
        ["role", "side", "class", "id"],
        ["reference", "1", "1", "P03T01C01G01D01S01"],
        ["reference", "1", "2", "P03T01C01G02D01S01"],
        ["reference", "1", "2", "P04T01C01G02D01S01"],
        ["query", "1", "1", "P01T01C01G01D01S01"],
    ]


def hand_boundary_experiment() -> BoundaryExperiment:
    good = [part(0.9, 0.1, -0.2, "ex", (0.5, 0.2, 0.2)), part(0.3, -0.3, 0.4, "ex", (0.1, 0.1, 0.1))]
    pairs = (pair_of(good, distance=0.1234, opened=1, outside=2), pair_of([], "no_path"), pair_of([], "no_path"))
    usable = tuple((sid(p, 1, 3), sid(p + 1, 1, 3)) for p in range(1, 8))
    run = BoundaryRun(
        pairs, (("P05T01C03", "CompareError: a | b"),), (("P01T01C03", "P02T01C03", "CompareError: refused"),), 6, 2.5
    )
    return BoundaryExperiment(SETTINGS, 3, 9, BoundaryCandidates(usable, 5, 3, 2), run, summarise_boundaries(pairs))


def test_the_boundary_report_has_the_numbers_the_summary_has():
    text = render_boundaries(hand_boundary_experiment())
    assert (
        "Pairs: 7 usable (one capture, two performers, equal label sequences), 5 with different labels left out; "
        "at most 9; aligned 3, with a path 1, with no path 2, skipped for a failed recording 6, refused 1; labelled "
        "recordings without a Kinect file 3, Kinect recordings without labels 2; 2.5 s." in text
    )
    assert (
        "Parts measured 2; left out because the last part has no end 1, because a boundary lies outside the reference "
        "clock 2. Median D of the pairs with a path 0.1234." in text
    )
    # warped: IoU 0.9 and 0.3 (median and mean 0.600, one of two reaches 0.5: 50.0 %); start errors 0.1 and -0.3 (abs
    # median 0.200, p90 0.1 + 0.9 * 0.2 = 0.280, bias -0.100); end errors -0.2 and 0.4 (0.300, 0.2 + 0.9 * 0.2 = 0.380,
    # bias 0.100)
    assert (
        "| all | warping path | 2 | 0.600 | 0.600 | 50.0 % | 0.200 | 0.280 | 0.300 | 0.380 | -0.100 | 0.100 |" in text
    )
    assert "| ex | warping path | 2 | 0.600 | 0.600 | 50.0 % | 0.200 | 0.280 | 0.300 | 0.380 | -0.100 | 0.100 |" in text
    # uniform: IoU 0.5 and 0.1, errors 0.2 and 0.1 at the start and at the end
    assert (
        "| all | uniform scaling | 2 | 0.300 | 0.300 | 50.0 % | 0.150 | 0.190 | 0.150 | 0.190 | 0.150 | 0.150 |" in text
    )
    assert "| tech | warping path | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |" in text
    assert "| P01T01C03 | P02T01C03 | ok | 0.1234 | 2 | 1 | 2 | 10 | 12 |" in text
    assert "| P01T01C03 | P02T01C03 | no_path | n/a | 0 | 0 | 0 | 10 | 12 |" in text
    assert "| P05T01C03 | CompareError: a / b |" in text
    assert "| P01T01C03 | P02T01C03 | CompareError: refused |" in text
    assert "at most 9" in text and "no cap" in render_boundaries(replace(hand_boundary_experiment(), max_pairs=None))


def test_the_boundary_csv_files_have_the_columns_and_the_values_the_summary_has():
    exp = hand_boundary_experiment()
    pairs = list(csv.reader(io.StringIO(boundaries_csv(exp))))
    assert pairs[0] == PAIRS_HEADER
    assert pairs[1] == ["P01T01C03", "P02T01C03", "ok", "0.1234", "2", "1", "2", "10", "12", "2", "1.0", "symmetricP1"]
    assert pairs[2] == ["P01T01C03", "P02T01C03", "no_path", "", "0", "0", "0", "10", "12", "2", "1.0", "symmetricP1"]
    parts = list(csv.reader(io.StringIO(boundary_parts_csv(exp))))
    assert parts[0] == PARTS_HEADER
    assert parts[1] == [
        "P01T01C03",
        "P02T01C03",
        "1",
        "ex1",
        "ex",
        "0.9",
        "0.1",
        "-0.2",
        "0.5",
        "0.2",
        "0.2",
        "2",
        "1.0",
        "symmetricP1",
    ]
    assert parts[2][5:11] == ["0.3", "-0.3", "0.4", "0.1", "0.1", "0.1"] and len(parts) == 3
