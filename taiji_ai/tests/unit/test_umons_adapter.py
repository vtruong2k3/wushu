"""P4.08: the adapter of the UMONS Kinect files (T-QLT-12a to 12g), on text made in the tests.

No dataset content is used here: the files are generated (a standing skeleton with a smooth sway, 33 ms steps, a dropped
frame, a pause, two bodies for six timestamps, a joint at (0, 0, 0)), so the tests run in the gate on every machine. The
real files are read by ``tests/golden/test_umons_quality.py`` (``dataset`` marker).

Kinect row: ``timestamp [ms]`` then 25 joints x ``x y z`` [mm], 76 numbers; the order is Kinect V2 ``JointType``.
"""

from __future__ import annotations

import csv
import dataclasses
import io
from pathlib import Path

import numpy as np
import pytest

from helpers.umons_fixtures import (
    KINECT_V2,
    K,
    clean_text,
    line,
    make_dataset,
    skeleton,
    synthetic_file,
    text_of,
)
from taiji_ai.bench import BenchError
from taiji_ai.bench.umons import (
    EXPECTED_FILES,
    KINECT_JOINTS,
    KINECT_TO_HALPE,
    PROVIDED,
    UmonsError,
    aggregate,
    find_umons,
    load_kinect,
    parse_kinect,
    render_tables,
    run_folder,
    run_sequence,
    write_per_file_csv,
)
from taiji_ai.pose.skeleton import IDX, JOINTS, NUM_JOINTS
from taiji_ai.quality.chain import QualityParams
from taiji_ai.quality.resample import ResampleParams
from taiji_ai.schemas.quality import QualityReport

ABSENT = [j for j in range(NUM_JOINTS) if j not in PROVIDED]


# --- T-QLT-12a: the reader --------------------------------------------------------------------------------------------
def test_t_qlt_12a_three_rows_parse_with_lf_crlf_blank_lines_and_extra_spaces():
    rows = [line(1000 + 33 * i, skeleton(i)) for i in range(3)]
    for text in (
        text_of(rows),
        text_of(rows, "\r\n"),
        text_of(rows) + "\n\n   \n",
        text_of(["  " + r.replace(" ", "   ") + "  " for r in rows]),
    ):
        seq = parse_kinect(text, "P01T01C01")
        assert seq.sequence_id == "P01T01C01" and seq.rows_in_file == 3 and len(seq.t_sec) == 3
        assert seq.keypoints.shape == (3, NUM_JOINTS, 2) and seq.scores.shape == (3, NUM_JOINTS)
        assert seq.tracked.tolist() == [True, True, True] and seq.repeated_rows == 0


def good_row() -> str:
    return line(1000, skeleton())


@pytest.mark.parametrize(
    "text, part",
    [
        (" ".join(good_row().split()[:-1]), "expected 76 numbers, got 75"),
        (good_row() + " 1.0", "expected 76 numbers, got 77"),
        (good_row().replace("1000 ", "word ", 1), "not a number"),
        (good_row().replace("-3300.0", "nan", 1), "not finite"),
        (good_row().replace("-3300.0", "inf", 1), "not finite"),
        (good_row().replace("-3300.0", "-inf", 1), "not finite"),
        ("", "no rows"),
        ("\n  \n\n", "no rows"),
    ],
)
def test_t_qlt_12a_a_bad_file_is_refused_naming_the_sequence_and_the_row(text, part):
    with pytest.raises(UmonsError, match=part) as err:
        parse_kinect(text, "P02T03C04")
    assert "P02T03C04" in str(err.value)


def test_t_qlt_12a_the_row_in_a_message_is_the_line_of_the_file():
    rows = [line(1000 + 33 * i, skeleton(i)) for i in range(4)]
    rows[2] = rows[2] + " 5"
    with pytest.raises(UmonsError, match="row 3"):
        parse_kinect(text_of(rows), "P01T01C01")
    rows = [line(1000 + 33 * i, skeleton(i)) for i in range(4)]
    rows[3] = line(900, skeleton(3))  # the clock goes back at row 4
    with pytest.raises(UmonsError, match=r"row 4.*decrease|decrease.*row 4"):
        parse_kinect(text_of(rows), "P01T01C01")


@pytest.mark.parametrize(
    "bad", ["p01t01c01", "P1T1C1", "P01T01C03.txt", "../P01T01C03", "P01T01C03G01D01S01", "", "P01T01"]
)
def test_t_qlt_12a_the_sequence_id_must_be_a_dataset_id(bad):
    with pytest.raises(UmonsError, match="sequence id"):
        parse_kinect(clean_text(3), bad)


def test_t_qlt_12a_a_decreasing_clock_is_an_error_and_a_umons_error_is_a_bench_error():
    rows = [line(1000, skeleton()), line(1033, skeleton()), line(1000, skeleton())]
    with pytest.raises(BenchError, match="decrease"):
        parse_kinect(text_of(rows), "P01T01C01")


def test_t_qlt_12a_load_kinect_takes_the_id_from_the_file_name(tmp_path: Path):
    path = tmp_path / "P05T02C07.txt"
    path.write_text(clean_text(5), encoding="ascii")
    assert load_kinect(path).sequence_id == "P05T02C07"
    odd = tmp_path / "notes.txt"
    odd.write_text(clean_text(5), encoding="ascii")
    with pytest.raises(UmonsError, match="sequence id"):
        load_kinect(odd)
    with pytest.raises(FileNotFoundError):
        load_kinect(tmp_path / "P01T01C01.txt")


# --- T-QLT-12b: the mapping and the plane -----------------------------------------------------------------------------
def distinct_row() -> tuple[str, np.ndarray]:
    xyz = np.zeros((25, 3))
    for k in range(25):
        xyz[k] = (1000.0 + k, 10.0 * k + 0.5, 100.0 * k + 0.25)
    return line(5000, xyz), xyz


def test_t_qlt_12b_every_halpe_cell_is_y_and_minus_z_of_its_kinect_joint():
    text, xyz = distinct_row()
    seq = parse_kinect(text, "P01T01C01")
    assert len(KINECT_TO_HALPE) == 17 and len(PROVIDED) == 17
    for kinect, halpe in KINECT_TO_HALPE.items():
        k, h = K[kinect], IDX[halpe]
        assert seq.keypoints[0, h].tolist() == [np.float32(xyz[k, 1]), np.float32(-xyz[k, 2])], (kinect, halpe)
        assert seq.scores[0, h] == 1.0
    assert seq.keypoints.dtype == np.float32 and seq.scores.dtype == np.float32


def test_t_qlt_12b_the_pairs_of_the_mapping():
    assert KINECT_TO_HALPE == {
        "SpineBase": "Hip", "Neck": "Neck", "Head": "Head",
        "ShoulderLeft": "LShoulder", "ElbowLeft": "LElbow", "WristLeft": "LWrist",
        "ShoulderRight": "RShoulder", "ElbowRight": "RElbow", "WristRight": "RWrist",
        "HipLeft": "LHip", "KneeLeft": "LKnee", "AnkleLeft": "LAnkle", "FootLeft": "LBigToe",
        "HipRight": "RHip", "KneeRight": "RKnee", "AnkleRight": "RAnkle", "FootRight": "RBigToe",
    }  # fmt: skip
    assert KINECT_JOINTS == KINECT_V2
    assert PROVIDED == tuple(sorted(IDX[h] for h in KINECT_TO_HALPE.values()))


def test_t_qlt_12b_the_nine_absent_joints_are_nan_with_a_nan_score_and_the_dropped_joints_appear_nowhere():
    text, xyz = distinct_row()
    seq = parse_kinect(text, "P01T01C01")
    assert sorted(JOINTS[j] for j in ABSENT) == sorted(
        ["Nose", "LEye", "REye", "LEar", "REar", "LSmallToe", "RSmallToe", "LHeel", "RHeel"]
    )
    for j in ABSENT:
        assert np.isnan(seq.keypoints[0, j]).all() and np.isnan(seq.scores[0, j]), JOINTS[j]
    dropped = [
        K[n]
        for n in (
            "SpineMid",
            "SpineShoulder",
            "HandLeft",
            "HandRight",
            "HandTipLeft",
            "HandTipRight",
            "ThumbLeft",
            "ThumbRight",
        )
    ]
    seen = {float(v) for v in seq.keypoints[0][~np.isnan(seq.keypoints[0])].ravel()}
    for k in dropped:
        assert np.float32(xyz[k, 1]) not in seen and np.float32(-xyz[k, 2]) not in seen, KINECT_JOINTS[k]


def test_t_qlt_12b_x_the_depth_axis_does_not_enter_the_layer():
    a, b = skeleton(), skeleton()
    b[:, 0] += 500.0  # the person is 0.5 m further away
    one = parse_kinect(text_of([line(1000, a)]), "P01T01C01")
    two = parse_kinect(text_of([line(1000, b)]), "P01T01C01")
    assert np.array_equal(one.keypoints, two.keypoints, equal_nan=True)


# --- T-QLT-12c: the clock ---------------------------------------------------------------------------------------------
def test_t_qlt_12c_time_is_seconds_from_the_first_row_and_nothing_is_regularised():
    stamps = [81_752_850, 81_752_884, 81_752_917, 81_752_950, 81_753_050]
    seq = parse_kinect(text_of([line(t, skeleton(i)) for i, t in enumerate(stamps)]), "P01T01C01")
    assert seq.t_sec.dtype == np.float64
    assert seq.t_sec.tolist() == pytest.approx([0.0, 0.034, 0.067, 0.100, 0.200], abs=1e-12)
    assert (np.diff(seq.t_sec) > 0).all() and seq.rows_in_file == 5 and seq.ambiguous_timestamps == 0


def test_t_qlt_12c_a_timestamp_used_more_than_once_keeps_its_first_row_and_is_not_tracked():
    stamps = [1000, 1033, 1033, 1066, 1066, 1066, 1100]
    rows = [line(t, skeleton(i, shift=1000.0 * (i % 2))) for i, t in enumerate(stamps)]
    seq = parse_kinect(text_of(rows), "P04T02C03")
    assert seq.rows_in_file == 7 and len(seq.t_sec) == 4
    assert seq.t_sec.tolist() == pytest.approx([0.0, 0.033, 0.066, 0.1])
    assert seq.tracked.tolist() == [True, False, False, True]
    assert seq.repeated_rows == 3 and seq.ambiguous_timestamps == 2
    first = parse_kinect(text_of([rows[1]]), "P04T02C03")  # the kept row is the first row of its timestamp
    assert np.array_equal(seq.keypoints[1], first.keypoints[0], equal_nan=True)


def test_t_qlt_12c_the_clock_going_back_after_a_repeat_is_still_an_error():
    rows = [line(t, skeleton()) for t in (1000, 1033, 1033, 1000)]
    with pytest.raises(UmonsError, match="decrease"):
        parse_kinect(text_of(rows), "P01T01C01")


def test_t_qlt_12c_a_repeated_last_row_and_a_repeated_first_row():
    rows = [line(t, skeleton()) for t in (1000, 1000, 1033, 1066, 1066)]
    seq = parse_kinect(text_of(rows), "P01T01C01")
    assert seq.t_sec.tolist() == pytest.approx([0.0, 0.033, 0.066])
    assert seq.tracked.tolist() == [False, True, False] and seq.repeated_rows == 2 and seq.ambiguous_timestamps == 2


# --- T-QLT-12d: the scores --------------------------------------------------------------------------------------------
def test_t_qlt_12d_a_joint_at_zero_has_score_zero_and_one_zero_coordinate_is_not_a_zero_joint():
    xyz = skeleton()
    xyz[K["WristLeft"]] = (0.0, 0.0, 0.0)  # the only "not tracked" marker of the files
    xyz[K["KneeRight"], 0] = 0.0  # only x is zero: a joint that is there
    xyz[K["SpineMid"]] = (0.0, 0.0, 0.0)  # a joint that the layer does not have
    seq = parse_kinect(text_of([line(1000, xyz)]), "P01T01C01")
    h = IDX["LWrist"]
    assert (seq.keypoints[0, h] == 0.0).all() and seq.scores[0, h] == 0.0  # the file's value, with no confidence
    h = IDX["RKnee"]
    assert np.isfinite(seq.keypoints[0, h]).all() and seq.scores[0, h] == 1.0
    assert seq.zero_joint_cells == 1  # counted over the 17 joints of the layer: the spine mid is not one of them
    others = [IDX[v] for k, v in KINECT_TO_HALPE.items() if k != "WristLeft"]
    assert (seq.scores[0, others] == 1.0).all() and np.isfinite(seq.keypoints[0, others]).all()


def test_t_qlt_12d_the_arrays_are_read_only():
    seq = parse_kinect(clean_text(4), "P01T01C01")
    for a in (seq.t_sec, seq.keypoints, seq.scores, seq.tracked):
        assert not a.flags.writeable


# --- T-QLT-12e: end to end on a synthetic sequence --------------------------------------------------------------------
@pytest.fixture(scope="module")
def synthetic_result():
    seq = parse_kinect(synthetic_file(), "P09T09C09")
    return seq, run_sequence(seq)


def test_t_qlt_12e_the_counts_of_the_sequence(synthetic_result):
    seq, result = synthetic_result
    assert (seq.rows_in_file, len(seq.t_sec), seq.repeated_rows, seq.ambiguous_timestamps) == (406, 400, 6, 6)
    assert seq.zero_joint_cells == 3
    assert (~seq.tracked).sum() == 6 and not seq.tracked[300:306].any() and seq.tracked[:300].all()
    assert result.error is None and result.report is not None and result.sequence_id == "P09T09C09"
    assert (result.steps_long, result.steps_pause) == (1, 1)  # the dropped frame (66 ms) and the pause (400 ms)


def test_t_qlt_12e_the_grid_is_not_the_rows_and_the_pause_is_no_frame(synthetic_result):
    _, result = synthetic_result
    rep = result.report
    assert rep.timeline.resampled is True and rep.timeline.rows == 400
    # 13,567 ms from the first to the last row on a 33 ms grid: floor(411.1) + 1 rows
    assert rep.timeline.grid_rows == 412 and rep.timeline.step_s == pytest.approx(0.033)
    seg = rep.intervals[0]
    assert seg.missing_by_reason.no_frame == 12 * NUM_JOINTS  # the grid times inside the 400 ms pause
    assert seg.mixed_rows > 0 and seg.rows == 412 and seg.source_rows == 400


def test_t_qlt_12e_two_bodies_are_not_tracked_and_never_bridged(synthetic_result):
    _, result = synthetic_result
    seg = result.report.intervals[0]
    assert seg.gaps.gaps.never_fill == len(PROVIDED) and seg.gaps.cells.never_fill == len(PROVIDED) * 6
    assert seg.gaps.gaps.open_both == len(ABSENT) and seg.gaps.cells.open_both == len(ABSENT) * 400
    assert seg.unobserved_by_reason.not_tracked >= len(PROVIDED) * 6  # the grid rows around them are marked too


def test_t_qlt_12e_the_zero_joint_is_low_conf_and_bridged(synthetic_result):
    _, result = synthetic_result
    joint = {j.joint: j for j in result.report.intervals[0].joints}["LWrist"]
    assert joint.bridged == 3  # three rows between observed anchors 132 ms apart: bridged, flagged
    assert result.report.intervals[0].unobserved_by_reason.low_conf == 3
    assert result.report.intervals[0].gaps.cells.filled == 3 and result.report.intervals[0].gaps.gaps.filled == 1


def test_t_qlt_12e_the_absent_joints_are_missing_and_the_provided_ones_are_not(synthetic_result):
    _, result = synthetic_result
    joints = {j.joint: j for j in result.report.intervals[0].joints}
    for j in ABSENT:
        assert joints[JOINTS[j]].observed == 0 and joints[JOINTS[j]].bridged == 0, JOINTS[j]
    for j in PROVIDED:
        assert joints[JOINTS[j]].observed > 300, JOINTS[j]
    assert result.report.intervals[0].missing_by_reason.non_finite > 0
    assert result.hampel_outliers == tuple([0] * NUM_JOINTS)  # a smooth sway is no outlier
    assert result.report.warnings[-1:] == ("grid_resampled",)


def test_t_qlt_12e_the_report_of_a_run_is_a_valid_quality_report(synthetic_result):
    _, result = synthetic_result
    assert isinstance(result.report, QualityReport) and result.seconds >= 0.0
    seg = result.report.intervals[0]
    assert seg.observed + seg.bridged + seg.missing == seg.cells


def test_t_qlt_12e_the_parameters_are_the_ones_given():
    seq = parse_kinect(synthetic_file(), "P09T09C09")
    nominal = run_sequence(seq, QualityParams(resample=ResampleParams(grid_hz=30.0)))
    assert nominal.report.timeline.step_s == pytest.approx(1 / 30.0)
    default = run_sequence(seq)
    assert default.report.timeline.step_s == pytest.approx(0.033)
    assert default.report.params == run_sequence(seq).report.params != nominal.report.params


# --- T-QLT-12f: find_umons --------------------------------------------------------------------------------------------
def test_t_qlt_12f_the_dataset_root_the_extracted_folder_and_the_kinect_folder_are_accepted(tmp_path: Path):
    folder = make_dataset(tmp_path / "umons")
    assert EXPECTED_FILES == 111
    assert find_umons(folder) == folder
    assert find_umons(tmp_path / "umons" / "extracted") == folder
    assert find_umons(tmp_path / "umons") == folder


@pytest.mark.parametrize("count", [0, 110, 112])
def test_t_qlt_12f_a_wrong_number_of_files_is_refused(tmp_path: Path, count: int):
    make_dataset(tmp_path / "umons", count=count)
    with pytest.raises(UmonsError, match=f"{EXPECTED_FILES} files"):
        find_umons(tmp_path / "umons")


def test_t_qlt_12f_a_stray_file_a_missing_license_and_another_license_are_refused(tmp_path: Path):
    folder = make_dataset(tmp_path / "a")
    (folder / "P01T01C01.txt.bak").write_text("x", encoding="ascii")
    with pytest.raises(UmonsError, match="unexpected"):
        find_umons(folder)
    make_dataset(tmp_path / "b", license_text=None)
    with pytest.raises(UmonsError, match="License.txt"):
        find_umons(tmp_path / "b")
    make_dataset(tmp_path / "c", license_text="Creative Commons Attribution 4.0 International (CC BY 4.0)\n")
    with pytest.raises(UmonsError, match="CC BY-NC-SA"):
        find_umons(tmp_path / "c")


def test_bug_0082_a_stray_entry_is_refused_without_its_name(tmp_path: Path):
    # the message of find_umons names no file name of the folder (a name is free text of the user's disk)
    folder = make_dataset(tmp_path / "umons")
    (folder / "SECRET_name.txt").write_text("x", encoding="ascii")
    (folder / "SECRET_folder").mkdir()
    with pytest.raises(UmonsError, match="unexpected entry") as err:
        find_umons(folder)
    assert "SECRET" not in str(err.value)
    assert "PxxTxxCxx.txt" in str(err.value)  # it still says what is expected


def test_t_qlt_12f_a_missing_folder_is_refused_without_its_path(tmp_path: Path):
    with pytest.raises(UmonsError) as err:
        find_umons(tmp_path / "private_folder_name")
    assert "private_folder_name" not in str(err.value) and str(tmp_path) not in str(err.value)


# --- T-QLT-12g: the run over a folder, the aggregation, the tables and the CSV ----------------------------------------
@pytest.fixture(scope="module")
def small_folder(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("kinect")
    (folder / "P01T01C01.txt").write_text(clean_text(80), encoding="ascii")
    (folder / "P01T01C02.txt").write_text(synthetic_file(), encoding="ascii")
    (folder / "P02T01C01.txt").write_text(clean_text(40, t0=5_000), encoding="ascii")
    (folder / "P02T01C02.txt").write_text(" ".join(good_row().split()[:-1]) + "\n", encoding="ascii")  # a bad file
    return folder


def test_t_qlt_12g_a_failing_file_is_an_error_row_and_the_run_goes_on(small_folder: Path):
    results = run_folder(small_folder)
    assert [r.sequence_id for r in results] == ["P01T01C01", "P01T01C02", "P02T01C01", "P02T01C02"]
    bad = results[-1]
    assert (
        bad.report is None and bad.error is not None and "expected 76 numbers" in bad.error and "P02T01C02" in bad.error
    )
    assert all(r.error is None and r.report is not None for r in results[:3])
    assert str(small_folder) not in bad.error


def test_t_qlt_12g_names_select_files_and_an_unknown_name_is_refused(small_folder: Path):
    assert [r.sequence_id for r in run_folder(small_folder, names=["P02T01C01", "P01T01C01"])] == [
        "P01T01C01",
        "P02T01C01",
    ]
    with pytest.raises(UmonsError, match="P09T09C09"):
        run_folder(small_folder, names=["P09T09C09"])
    with pytest.raises(UmonsError, match="not a sequence id"):
        run_folder(small_folder, names=["../x"])


def test_t_qlt_12g_the_aggregate_is_the_sum_of_the_reports(small_folder: Path):
    results = run_folder(small_folder)
    summary = aggregate(results)
    ok = [r for r in results if r.report is not None]
    assert summary.files == 3 and [e[0] for e in summary.errors] == ["P02T01C02"]
    segs = [r.report.intervals[0] for r in ok]
    for key in (
        "cells",
        "observed",
        "bridged",
        "missing",
        "usable_frames",
        "not_tracked_frames",
        "filtered",
        "mixed_rows",
    ):
        assert getattr(summary, key) == sum(getattr(s, key) for s in segs), key
    assert summary.rows == sum(s.source_rows for s in segs) and summary.grid_rows == sum(s.rows for s in segs)
    assert summary.rows_in_file == sum(r.rows_in_file for r in ok) == 80 + 406 + 40
    assert summary.repeated_rows == 6 and summary.ambiguous_timestamps == 6 and summary.zero_joint_cells == 3
    assert summary.observed + summary.bridged + summary.missing == summary.cells
    assert summary.resampled_files == sum(r.report.timeline.resampled for r in ok)


def test_t_qlt_12g_the_17_joint_numbers_leave_out_the_absent_joints(small_folder: Path):
    summary = aggregate(run_folder(small_folder))
    assert summary.provided_cells == summary.grid_rows * len(PROVIDED)
    assert summary.provided_observed + summary.provided_bridged + summary.provided_missing == summary.provided_cells
    assert summary.cells == summary.grid_rows * NUM_JOINTS
    assert summary.missing - summary.provided_missing == summary.grid_rows * len(ABSENT)  # the nine are always missing
    assert sum(summary.missing_by_reason.values()) == summary.missing
    assert sum(summary.unobserved_by_reason.values()) == summary.bridged + summary.missing
    assert set(summary.gap_cells) == {
        "filled",
        "too_long",
        "never_fill",
        "blocked",
        "open_start",
        "open_end",
        "open_both",
    }


def test_t_qlt_12g_distributions_and_the_named_files(small_folder: Path):
    summary = aggregate(run_folder(small_folder))
    lo, p10, median, hi = summary.usable_frames_share
    assert lo <= p10 <= median <= hi <= 1.0
    for d in (summary.provided_usable_share, summary.mixed_share, summary.outlier_share):
        assert d[0] <= d[1] <= d[2] <= d[3]
    # two of the three files have a uniform clock (no mixed row), the synthetic one has many: the 10th percentile
    # and the median are 0 and only the maximum is not
    assert summary.mixed_share[:3] == (0.0, 0.0, 0.0) and summary.mixed_share[3] > 0.05
    assert summary.notable["longest"] == "P01T01C02" and summary.notable["ambiguous"] == ["P01T01C02"]
    assert summary.notable["zero_joint"] == ["P01T01C02"] and summary.notable["no_frame"] == ["P01T01C02"]
    assert summary.steps_pause == 1 and summary.steps_long == 1


def _timeless(results):
    """The results with the wall-clock ``seconds`` set to 0: the one number of a run that is not a function of the data
    (BUG-0083)."""
    return [dataclasses.replace(r, seconds=0.0) for r in results]


def test_bug_0083_the_wall_clock_row_is_the_only_thing_that_differs_between_two_runs(small_folder: Path):
    results = run_folder(small_folder)
    fast = render_tables({"default": aggregate([dataclasses.replace(r, seconds=0.0) for r in results])})
    slow = render_tables({"default": aggregate([dataclasses.replace(r, seconds=7.0) for r in results])})
    assert fast != slow  # the timing is in the tables ("Seconds, chain and report")
    clock = "Seconds, chain and report"
    without = [[ln for ln in text.splitlines() if clock not in ln] for text in (fast, slow)]
    assert without[0] == without[1]  # and nothing else depends on it


def test_t_qlt_12g_the_tables_are_deterministic_and_hold_only_numbers_and_ids(small_folder: Path):
    results = _timeless(run_folder(small_folder))
    a = render_tables({"default": aggregate(results)})
    b = render_tables({"default": aggregate(_timeless(run_folder(small_folder)))})
    assert a == b  # the wall clock is out of it: two runs of the same data differ in the rounding of the seconds
    assert "P01T01C02" in a and "P02T01C02" in a  # the notable file and the failed one, by id
    assert str(small_folder) not in a and "\\" not in a and "/tmp" not in a
    assert "default" in a and "provided" in a.lower()
    assert "Bridged cells on the rows of the files" in a and "Not tracked frames" in a
    two = render_tables({"default": aggregate(results), "grid 30 Hz": aggregate(results)})
    assert two.count("grid 30 Hz") >= 1 and len(two) > len(a)


def test_t_qlt_12g_the_csv_has_one_row_per_file_counts_only_and_an_error_column(small_folder: Path, tmp_path: Path):
    results = run_folder(small_folder)
    path = write_per_file_csv(tmp_path / "out" / "per_file.csv", results)
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    assert [r["sequence_id"] for r in rows] == ["P01T01C01", "P01T01C02", "P02T01C01", "P02T01C02"]
    assert rows[1]["rows_in_file"] == "406" and rows[1]["repeated_rows"] == "6" and rows[1]["error"] == ""
    assert "expected 76 numbers" in rows[3]["error"] and rows[3]["rows"] == ""
    assert write_per_file_csv(tmp_path / "again.csv", results).read_bytes() == path.read_bytes()
    assert list(tmp_path.glob("*.tmp")) == [] and not list((tmp_path / "out").glob("*.tmp"))


def test_t_qlt_12g_a_failure_of_the_chain_is_an_error_row_too(small_folder: Path, monkeypatch: pytest.MonkeyPatch):
    from taiji_ai.bench import umons
    from taiji_ai.quality import QualityError

    def refuse(*_args, **_kwargs):
        raise QualityError("boom")

    monkeypatch.setattr(umons, "run_quality_arrays", refuse)
    results = run_folder(small_folder, names=["P01T01C01"])
    assert results[0].report is None and results[0].error == "P01T01C01: QualityError: boom"


def test_t_qlt_12g_the_csv_columns_hold_what_their_names_say(small_folder: Path, tmp_path: Path):
    results = run_folder(small_folder, names=["P01T01C02"])
    path = write_per_file_csv(tmp_path / "one.csv", results)
    (row,) = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
    rep = results[0].report
    seg = rep.intervals[0]
    assert (row["rows_in_file"], row["rows"], row["grid_rows"]) == ("406", "400", "412")
    assert (row["repeated_rows"], row["ambiguous_timestamps"], row["zero_joint_cells"]) == ("6", "6", "3")
    assert (row["steps_long"], row["steps_pause"], row["resampled"]) == ("1", "1", "1")
    assert float(row["max_step_s"]) == pytest.approx(0.4) and float(row["duration_s"]) == pytest.approx(13.567)
    assert float(row["step_ms"]) == pytest.approx(33.0) and 400 < float(row["torso_mm"]) < 700
    assert (row["observed"], row["bridged"], row["missing"]) == (str(seg.observed), str(seg.bridged), str(seg.missing))
    assert int(row["provided_observed"]) + int(row["provided_bridged"]) + int(row["provided_missing"]) == 412 * 17
    assert (row["usable_frames"], row["not_tracked_frames"]) == (str(seg.usable_frames), str(seg.not_tracked_frames))
    assert row["no_frame_cells"] == str(12 * NUM_JOINTS) and row["hampel_outliers"] == "0"
    assert (row["filtered"], row["unfiltered"]) == (str(seg.filtered), str(seg.unfiltered))
    assert (row["suspect"], row["blocked"], row["swap_warnings"], row["error"]) == ("0", "0", "0", "")
    assert row["mixed_rows"] == str(seg.mixed_rows) and float(row["seconds"]) >= 0.0


def test_t_qlt_12g_a_long_list_of_ids_is_a_count_and_its_first_ten(small_folder: Path):
    import dataclasses

    summary = aggregate(run_folder(small_folder))
    ids = [f"P01T01C{i:02d}" for i in range(1, 13)]
    text = render_tables({"default": dataclasses.replace(summary, notable={**summary.notable, "no_frame": ids})})
    assert "12 files, the first 10: " + ", ".join(ids[:10]) in text and ids[10] not in text
    ten = render_tables({"default": dataclasses.replace(summary, notable={**summary.notable, "no_frame": ids[:10]})})
    assert ", ".join(ids[:10]) in ten and "files, the first" not in ten
