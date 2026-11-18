"""T-CMP-09e: ``tools/umons_compare.py`` runs the classes check and the boundary check over a made-up UMONS folder,
writes numbers and ids only, echoes its settings, refuses what it cannot run with exit code 2 and a message that names
no path or string of the caller, and exits 1 when a file or a pair failed (P6.07).

The folders are made in the tests (``helpers/umons_fixtures.py``: 48 small segmented files with one movement per class,
and 111 Kinect files of which two are a routine at two speeds, with their label files): no dataset content is used.
"""

from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from helpers.umons_fixtures import (
    make_boundary_dataset,
    make_labels,
    make_segments,
    routine_label_text,
    segment_name,
)
from taiji_ai.bench.umons_compare import (  # noqa: E402
    BoundaryCandidates,
    BoundaryExperiment,
    BoundaryRun,
    ClassExperiment,
    ClassRun,
    PairBoundary,
    PairDistance,
    make_settings,
    parse_segment_id,
    parse_sequence_id,
    summarise_boundaries,
    summarise_classes,
)

TOOL = Path(__file__).resolve().parents[2] / "tools" / "umons_compare.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=TOOL.parents[1],
        check=False,
        timeout=600,
    )


def load_tool():
    """The tool as a module (it is a script, not a package): its parser and its helpers can be called directly."""
    spec = importlib.util.spec_from_file_location("umons_compare_tool_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


@pytest.fixture(scope="module")
def classes_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("segments") / "private_umons_folder"
    make_segments(root)
    return root


@pytest.fixture(scope="module")
def boundary_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("sequences") / "private_umons_folder"
    make_boundary_dataset(root)
    return root


@pytest.fixture(scope="module")
def classes_run(classes_root: Path, tmp_path_factory):
    out = tmp_path_factory.mktemp("classes_out") / "out"
    report = out.parent / "report.md"
    done = run_tool("classes", "--umons", str(classes_root), "--out", str(out), "--report", str(report))
    return done, out, report


@pytest.fixture(scope="module")
def boundaries_run(boundary_root: Path, tmp_path_factory):
    out = tmp_path_factory.mktemp("boundaries_out") / "out"
    report = out.parent / "report.md"
    done = run_tool("boundaries", "--umons", str(boundary_root), "--out", str(out), "--report", str(report))
    return done, out, report


# --- what it refuses --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("command", ["classes", "boundaries"])
def test_t_cmp_09e_a_missing_folder_is_refused_without_its_path(command: str, tmp_path: Path):
    done = run_tool(command, "--umons", str(tmp_path / "no_such_umons_folder"), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "error:" in done.stderr
    assert "no_such_umons_folder" not in done.stderr + done.stdout and str(tmp_path) not in done.stderr
    assert not (tmp_path / "out").exists()


def test_t_cmp_09e_a_folder_without_the_segmented_files_or_without_the_labels_is_refused(tmp_path: Path):
    empty = tmp_path / "private_empty"
    empty.mkdir()
    done = run_tool("classes", "--umons", str(empty), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "Segmented_Kinect" in done.stderr and "private_empty" not in done.stderr
    only_kinect = tmp_path / "private_kinect_only"
    make_boundary_dataset(only_kinect)
    (only_kinect / "extracted" / "Labels" / "License.txt").unlink()
    done = run_tool("boundaries", "--umons", str(only_kinect), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "License.txt" in done.stderr and "private_kinect_only" not in done.stderr
    assert not (tmp_path / "out").exists()


def test_t_cmp_09e_no_pair_to_align_is_refused(tmp_path: Path):
    root = tmp_path / "private_one_performer"
    make_segments(root, performers=(1,))  # one performer: every pair would be a performer against themself
    done = run_tool("classes", "--umons", str(root), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "no pair" in done.stderr and "private_one_performer" not in done.stderr
    assert not (tmp_path / "out").exists()
    other = tmp_path / "private_unequal_labels"
    make_boundary_dataset(other, labels_of_two=(routine_label_text(1.0), "0.0 _\n1.0 ex2l\n2.0 _\n"))
    done = run_tool("boundaries", "--umons", str(other), "--out", str(tmp_path / "out2"))
    assert done.returncode == 2 and "no pair" in done.stderr and not (tmp_path / "out2").exists()


@pytest.mark.parametrize(
    "bad",
    [
        ("--seed", "SECRETSEED"),
        ("--seed", "-1"),
        ("--seed", "4294967296"),
        ("--band", "SECRETBAND"),
        ("--band", "0"),
        ("--band", "1.5"),
        ("--band", "nan"),
        ("--band", "inf"),
        ("--band", "1e999"),
        ("--min-visible", "0"),
        ("--min-visible", "22"),
        ("--min-visible", "2.5"),
        ("--min-visible", "1" + "0" * 400),
        ("--step", "SECRETSTEP"),
        ("--max-pairs", "0"),
        ("--max-pairs", "SECRETPAIRS"),
        ("--references", "0"),
        ("--queries", "SECRETQUERIES"),
        ("--bogus-option", "SECRETOPTION"),
    ],
)
def test_t_cmp_09e_a_bad_option_is_refused_and_never_echoed(classes_root: Path, tmp_path: Path, bad):
    done = run_tool("classes", "--umons", str(classes_root), "--out", str(tmp_path / "out"), *bad)
    assert done.returncode == 2
    assert "SECRET" not in done.stderr + done.stdout and "Traceback" not in done.stderr
    assert "OverflowError" not in done.stderr
    assert not (tmp_path / "out").exists()


def test_t_cmp_09e_an_unknown_command_and_missing_options_are_refused(tmp_path: Path):
    done = run_tool("SECRETCOMMAND", "--umons", str(tmp_path), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "SECRET" not in done.stderr + done.stdout
    done = run_tool("classes")
    assert done.returncode == 2 and "--umons" in done.stderr
    done = run_tool()
    assert done.returncode == 2


# --- the classes check ------------------------------------------------------------------------------------------------
def test_t_cmp_09e_classes_runs_writes_numbers_and_ids_and_echoes_its_settings(classes_run, classes_root: Path):
    done, out, report = classes_run
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in out.iterdir()) == ["classes.csv", "pairs.csv", "selection.csv"]
    echoed = "min_visible 11 of 21 units, band 0.2, step symmetricP1"
    assert echoed in done.stdout and echoed in report.read_text(encoding="utf-8")
    pairs = read_csv(out / "pairs.csv")
    assert len(pairs) == 212 and {(p["min_visible"], p["band"], p["step"]) for p in pairs} == {
        ("11", "0.2", "symmetricP1")
    }
    assert all(p["status"] in ("ok", "no_path") and p["side"] in ("1", "2") for p in pairs)
    table = read_csv(out / "classes.csv")
    assert {r["side"] for r in table} == {"all", "1", "2"} and {r["min_visible"] for r in table} == {"11"}
    pooled = [r for r in table if r["side"] == "all"]
    assert [r["class"] for r in pooled] == ["1", "2", "3"]
    assert all(r["own_closer"] == "1" for r in pooled)  # three movements that differ: the own class is nearer
    assert "own class is closer in 3 of 3" in done.stdout and "30 of 30 queries" in done.stdout


def test_t_cmp_09e_no_performer_is_compared_with_themself(classes_run):
    _, out, _ = classes_run
    for p in read_csv(out / "pairs.csv"):
        assert p["query"][:3] != p["reference"][:3]  # PxxTxx...: the first three characters are the performer
        assert p["query"][12:15] == p["reference"][12:15]  # Dxx: one side


def test_t_cmp_09e_classes_prints_and_writes_only_ids_and_numbers(classes_run, classes_root: Path):
    done, out, report = classes_run
    everything = done.stdout + done.stderr + report.read_text(encoding="utf-8")
    everything += "".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    assert "private_umons_folder" not in everything and str(classes_root.parent) not in everything
    assert "-3300" not in everything and "WristLeft" not in everything  # no value or name of a skeleton
    assert "Out of domain" in report.read_text(encoding="utf-8")
    ids = [r["id"] for r in read_csv(out / "selection.csv")]
    assert ids and all(len(i) == 18 and i[0] == "P" for i in ids)


def test_t_cmp_09e_the_same_seed_gives_the_same_files_and_another_seed_another_choice(
    classes_root: Path, classes_run, tmp_path: Path
):
    _, out, _ = classes_run
    again = tmp_path / "again"
    assert run_tool("classes", "--umons", str(classes_root), "--out", str(again)).returncode == 0
    assert (again / "pairs.csv").read_bytes() == (out / "pairs.csv").read_bytes()
    assert (again / "selection.csv").read_bytes() == (out / "selection.csv").read_bytes()
    other = tmp_path / "other"
    assert run_tool("classes", "--umons", str(classes_root), "--out", str(other), "--seed", "2").returncode == 0
    assert (other / "selection.csv").read_bytes() != (out / "selection.csv").read_bytes()


def test_t_cmp_09e_the_settings_and_the_cap_are_arguments_that_are_echoed(classes_root: Path, tmp_path: Path):
    out = tmp_path / "out"
    done = run_tool(
        "classes", "--umons", str(classes_root), "--out", str(out), "--min-visible", "4", "--band", "0.5",
        "--step", "symmetric1", "--max-pairs", "30", "--references", "2", "--queries", "3", "--seed", "7",
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert "min_visible 4 of 21 units, band 0.5, step symmetric1" in done.stdout and "seed 7" in done.stdout
    pairs = read_csv(out / "pairs.csv")
    assert len(pairs) == 30 and {(p["min_visible"], p["band"], p["step"]) for p in pairs} == {
        ("4", "0.5", "symmetric1")
    }
    selection = read_csv(out / "selection.csv")
    assert sum(r["role"] == "reference" for r in selection) == 12 and sum(r["role"] == "query" for r in selection) <= 18


def test_t_cmp_09e_a_segment_that_cannot_be_read_is_listed_by_id_and_the_exit_code_is_1(tmp_path: Path):
    root = tmp_path / "private_umons_folder"
    folder = make_segments(root, classes=(1, 2), performers=(1, 2, 3, 4), repetitions=(1,))
    bad = folder / f"{segment_name(1, 1, 1, 1)}.txt"
    bad.write_text("1000 1 2 3\n", encoding="ascii")  # not 76 numbers
    out = tmp_path / "out"
    # four segments per class and side: two references and two queries use all of them, so the bad one is used
    done = run_tool("classes", "--umons", str(root), "--out", str(out), "--references", "2", "--queries", "2")
    assert done.returncode == 1, done.stdout
    assert f"failed {segment_name(1, 1, 1, 1)}" in done.stdout
    assert "private_umons_folder" not in done.stdout + done.stderr
    assert read_csv(out / "pairs.csv")  # the other pairs ran


# --- the boundary check -----------------------------------------------------------------------------------------------
def test_t_cmp_09e_boundaries_runs_and_measures_the_two_labelled_parts(boundaries_run):
    done, out, report = boundaries_run
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in out.iterdir()) == ["pairs.csv", "parts.csv"]
    echoed = "min_visible 11 of 21 units, band 0.1, step symmetricP1"
    assert echoed in done.stdout and echoed in report.read_text(encoding="utf-8")
    (pair,) = read_csv(out / "pairs.csv")
    assert (pair["reference"], pair["query"], pair["status"], pair["parts"]) == ("P01T01C03", "P02T01C03", "ok", "2")
    parts = read_csv(out / "parts.csv")
    assert [(p["label"], p["family"]) for p in parts] == [("ex1l", "ex"), ("tech2r", "tech")]
    for p in parts:  # the same routine at two speeds: the boundaries land within a fraction of a second
        assert float(p["iou"]) > 0.9 and abs(float(p["start_error_s"])) < 0.15 and abs(float(p["end_error_s"])) < 0.15
        assert 0.0 <= float(p["uniform_iou"]) <= 1.0
    text = report.read_text(encoding="utf-8")
    assert "1 with different labels left out" in text and "labelled recordings without a Kinect file 1" in text
    assert "Out of domain" in text and "uniform scaling" in text


def test_t_cmp_09e_boundaries_prints_and_writes_only_ids_and_numbers(boundaries_run, boundary_root: Path):
    done, out, report = boundaries_run
    everything = done.stdout + done.stderr + report.read_text(encoding="utf-8")
    everything += "".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    assert "private_umons_folder" not in everything and str(boundary_root.parent) not in everything
    assert (
        "-3300" not in everything and "ex1l" not in done.stdout
    )  # no value of a skeleton; labels only in the parts CSV
    header = (out / "parts.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert not {"start_s", "end_s", "t_sec"} & set(header)  # no label time is written


def test_t_cmp_09e_a_label_file_that_does_not_parse_is_listed_with_its_line_and_the_exit_code_is_1(tmp_path: Path):
    root = tmp_path / "private_umons_folder"
    make_boundary_dataset(root)
    make_labels(root, {"P05T01C07": "0.0 _\n3.0 ex1l\n2.0 _\n"})  # goes back at line 3
    out = tmp_path / "out"
    done = run_tool("boundaries", "--umons", str(root), "--out", str(out), "--report", str(tmp_path / "report.md"))
    assert done.returncode == 1, done.stderr
    assert "failed P05T01C07" in done.stdout and "line 3" in done.stdout
    assert "private_umons_folder" not in done.stdout + done.stderr
    assert "P05T01C07" in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert len(read_csv(out / "pairs.csv")) == 1  # the other pair ran


def test_t_cmp_09e_the_cap_applies_to_the_boundary_pairs(boundary_root: Path, tmp_path: Path):
    done = run_tool("boundaries", "--umons", str(boundary_root), "--out", str(tmp_path / "out"), "--max-pairs", "1")
    assert done.returncode == 0 and len(read_csv(tmp_path / "out" / "pairs.csv")) == 1


# --- the options and the listing --------------------------------------------------------------------------------------
def test_t_cmp_09e_the_defaults_are_the_plans_q2_and_q3():
    parser = load_tool()._parser()
    classes = parser.parse_args(["classes", "--umons", "u", "--out", "o"])
    assert (classes.seed, classes.max_pairs, classes.band, classes.min_visible) == (1, None, 0.2, None)
    assert (classes.step, classes.references, classes.queries, classes.report) == ("symmetricP1", 3, 5, None)
    boundaries = parser.parse_args(["boundaries", "--umons", "u", "--out", "o"])
    assert (boundaries.seed, boundaries.max_pairs, boundaries.band, boundaries.min_visible) == (1, 40, 0.1, None)
    assert boundaries.step == "symmetricP1" and not hasattr(boundaries, "references")


def test_t_cmp_09e_only_the_first_failures_are_listed_and_the_rest_are_counted():
    listed = load_tool()._listed
    assert listed(["a", "b"], 2) == ["  failed a", "  failed b"]
    many = [f"id{i}" for i in range(12)]
    lines = listed(many, 12)
    assert lines[:10] == [f"  failed id{i}" for i in range(10)] and len(lines) == 11 and "2 more" in lines[10]
    assert listed(many[:10], 10) == [f"  failed id{i}" for i in range(10)]  # exactly ten: nothing is cut
    assert listed([], 0) == []


def test_t_cmp_09e_progress_is_reported_on_stderr_up_to_the_last_pair(classes_run):
    done, _, _ = classes_run
    assert "classes: 212/212 pairs" in done.stderr and "classes: 21/212 pairs" in done.stderr
    assert done.stdout.count("212/212") == 0  # progress is not part of the numbers on stdout


def test_t_cmp_09e_a_folder_of_segments_with_no_segment_is_refused(tmp_path: Path):
    root = tmp_path / "private_umons_folder"
    make_segments(root, classes=(), performers=(1,))  # the folder and its License.txt, no file
    done = run_tool("classes", "--umons", str(root), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "no segmented file" in done.stderr and not (tmp_path / "out").exists()


# --- the lines the tool prints and the exit codes, on experiments that the test builds ---------------------------
def seg_id(performer: int, klass: int):
    return parse_segment_id(f"P{performer:02d}T01C01G{klass:02d}D01S01")


def class_experiment(*, failed_pairs=(), failed_segments=()) -> ClassExperiment:
    q1, q2, q3a, q3b = seg_id(1, 1), seg_id(2, 2), seg_id(1, 3), seg_id(2, 3)
    r1, r2, r3 = seg_id(3, 1), seg_id(3, 2), seg_id(3, 3)
    distances = (
        PairDistance(q1, r1, 0.2), PairDistance(q1, r2, 0.9),
        PairDistance(q2, r2, 0.6), PairDistance(q2, r1, 0.3),
        PairDistance(q3a, r3, 0.1), PairDistance(q3a, r1, 0.5),
        PairDistance(q3b, r3, 0.4), PairDistance(q3b, r1, 0.2),
    )  # fmt: skip
    run = ClassRun(distances, tuple(failed_segments), tuple(failed_pairs), 0, 1.0)
    summary = summarise_classes(distances)
    return ClassExperiment(make_settings(band=0.2), 1, 3, 5, None, {}, {}, 8, 8, 2, run, summary, {1: summary})


def boundary_experiment_with(*, failed_pairs=(), failed_sequences=()) -> BoundaryExperiment:
    a, b = parse_sequence_id("P01T01C03"), parse_sequence_id("P02T01C03")
    pair = PairBoundary(a, b, "no_path", None, (), 0, 0, 10, 12)
    run = BoundaryRun((pair,), tuple(failed_sequences), tuple(failed_pairs), 0, 1.0)
    candidates = BoundaryCandidates(((a, b),), 0, 0, 0)
    return BoundaryExperiment(make_settings(band=0.1), 1, None, candidates, run, summarise_boundaries(run.pairs))


def test_t_cmp_09e_the_classes_lines_say_the_counts_in_the_right_places():
    tool = load_tool()
    lines = tool._classes_lines(class_experiment(), 1.5)
    assert lines[0].startswith("Settings: min_visible 11 of 21 units, band 0.2, step symmetricP1")
    assert lines[1] == (
        "classes: pairs aligned 8 of 8 available, same-performer pairs left out 2, no path 0, segments failed 0, "
        "pairs refused 0, 1.5 s"
    )
    assert lines[2] == (
        "classes: the own class is closer in 2 of 3 (66.7 %); nearest reference of the same class for 2 of 4 queries "
        "(50.0 %)"
    )
    assert lines[3] == "classes side D01: own closer 2 of 3, nearest correct 2 of 4" and len(lines) == 4
    failing = tool._classes_lines(
        class_experiment(failed_segments=(("P09T01C01G01D01S01", "E1"),), failed_pairs=(("Q", "R", "E2"),)), 1.0
    )
    assert failing[-2:] == ["  failed P09T01C01G01D01S01: E1", "  failed Q/R: E2"]


def test_t_cmp_09e_the_boundary_lines_list_every_kind_of_failure():
    tool = load_tool()
    exp = boundary_experiment_with(
        failed_pairs=(("P01T01C03", "P02T01C03", "E3"),), failed_sequences=(("P05T01C03", "E2"),)
    )
    lines = tool._boundary_lines(exp, (("P04T01C03", "E1"),), 2.0)
    assert lines[-3:] == ["  failed P04T01C03: E1", "  failed P05T01C03: E2", "  failed P01T01C03/P02T01C03: E3"]
    assert "label files failed 1" in lines[1] and "recordings failed 1" in lines[1] and "pairs refused 1" in lines[1]
    assert "boundaries all warping: parts 0, IoU median n/a, start error median n/a s, end error median n/a s" in lines


@pytest.mark.parametrize(
    ("failed_pairs", "failed_segments", "code"),
    [((), (), 0), ((("Q", "R", "E"),), (), 1), ((), (("P09T01C01G01D01S01", "E"),), 1)],
)
def test_t_cmp_09e_the_exit_code_of_classes_follows_the_failures_of_files_and_of_pairs(
    tmp_path: Path, clean_logging, failed_pairs, failed_segments, code
):
    tool = load_tool()
    exp = class_experiment(failed_pairs=failed_pairs, failed_segments=failed_segments)
    tool.find_folder = lambda root, name: tmp_path
    tool.list_segments = lambda folder: {seg_id(1, 1): tmp_path / "x"}
    tool.classes_experiment = lambda *args, **kwargs: exp
    assert tool.main(["classes", "--umons", "u", "--out", str(tmp_path / "out")]) == code


@pytest.mark.parametrize(
    ("failed_pairs", "failed_sequences", "code"),
    [((), (), 0), ((("A", "B", "E"),), (), 1), ((), (("P05T01C03", "E"),), 1)],
)
def test_t_cmp_09e_the_exit_code_of_boundaries_follows_the_failures_of_files_and_of_pairs(
    tmp_path: Path, clean_logging, failed_pairs, failed_sequences, code
):
    tool = load_tool()
    exp = boundary_experiment_with(failed_pairs=failed_pairs, failed_sequences=failed_sequences)
    tool.find_umons = lambda root: tmp_path
    tool.find_folder = lambda root, name: tmp_path
    tool.list_sequences = lambda folder: {}
    tool.list_labels = lambda folder: {}
    tool.boundary_experiment = lambda *args, **kwargs: exp
    assert tool.main(["boundaries", "--umons", "u", "--out", str(tmp_path / "out")]) == code


def test_t_cmp_09e_a_share_is_a_percentage():
    share = load_tool()._share
    assert share(1, 4) == "25.0 %" and share(0, 0) == "n/a" and share(3, 3) == "100.0 %"


def test_t_cmp_09e_boundaries_wants_the_whole_set_of_kinect_files(tmp_path: Path):
    root = tmp_path / "private_umons_folder"
    kinect = make_boundary_dataset(root) / "extracted" / "Kinect"
    (kinect / "P01T01C10.txt").unlink()
    done = run_tool("boundaries", "--umons", str(root), "--out", str(tmp_path / "out"))
    assert done.returncode == 2 and "expected 111" in done.stderr and not (tmp_path / "out").exists()
