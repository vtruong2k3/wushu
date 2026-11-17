"""T-DET-08: ``detector_compare.py sheets`` and ``report`` on a made-up result with disagreement runs (P3.09).

The real run of the task had no run in which only one detector found the performer, so the review path (the page, the
labels, the count of who was right, criterion C of the rule) had never run on a non-empty sample. These tests build a
``detector.json`` from made-up detections with the library functions and run the tool on it: no model, no GPU, no
video. The direction of a run (which detector has the box) is never shown to the reviewer; ``report`` joins it back.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from taiji_ai.bench.detector_compare import pick_sample, recall_by_limit, summarise_c, summarise_r

TOOL = Path(__file__).resolve().parents[2] / "tools" / "detector_compare.py"
REF = (100.0, 100.0, 200.0, 400.0)
BOX = (100.0, 100.0, 300.0, 700.0)  # 600 px of 1000: a performer-sized box
H = 1000.0


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=TOOL.parents[1],
        check=False,
        timeout=180,
    )


def det(*boxes: tuple[float, float, float, float], score: float = 0.9) -> np.ndarray:
    return np.array([(*b, score) for b in boxes], np.float32).reshape(-1, 5)


def make_result(n_only_b: int = 8, n_only_a: int = 1) -> dict:
    """A result whose clip has ``n_only_b`` runs where only B has the performer and ``n_only_a`` where only A has
    them, each run one frame long and set apart by frames where both have them; 25 labelled frames that both find."""
    seq: list[tuple[bool, bool]] = []
    for _ in range(n_only_b):
        seq += [(True, True)] * 2 + [(False, True)]
    for _ in range(n_only_a):
        seq += [(True, True)] * 2 + [(True, False)]
    seq += [(True, True)] * 2
    clip = {
        "t_sec": np.arange(len(seq)) / 10.0,
        "dets_a": [det(BOX) if a else det() for a, _ in seq],
        "dets_b": [det(BOX) if b else det() for _, b in seq],
        "image_height": H,
    }
    c = summarise_c({"c1": clip})
    entries = [{"id": f"fc-{i:03d}", "reference": REF, "negative": False, "image_height": H} for i in range(25)]
    a = b = [det(REF)] * 25
    return {
        "schema": "p3_09_detector/1",
        "speed": {"a": {}, "b": {}},
        "r": summarise_r(entries, a, b),
        "r_by_limit": recall_by_limit(entries, a, b),
        "c": c,
        "sample": pick_sample(c["runs"]),
    }


def write_run(tmp_path: Path, result: dict) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    (out / "detector.json").write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    return out


def label_file(out: Path, name: str, labels: dict[str, str]) -> None:
    (out / name).write_text(json.dumps(labels), encoding="utf-8")


def answers(result: dict, only_b: str, only_a: str) -> dict[str, str]:
    return {s["id"]: (only_b if s["direction"] == "only_b" else only_a) for s in result["sample"]}


def reviewed(out: Path) -> dict:
    return json.loads((out / "detector.json").read_text(encoding="utf-8"))["review"]


def test_t_det_08_the_made_up_result_has_the_runs_the_tests_expect():
    result = make_result()
    assert (result["c"]["runs_only_b"], result["c"]["runs_only_a"], len(result["sample"])) == (8, 1, 9)
    assert result["r"]["n_positive"] == 25


def test_t_det_08_the_review_page_lists_the_runs_and_hides_which_detector_has_the_box(tmp_path: Path):
    result = make_result()
    out = write_run(tmp_path, result)
    label_file(out, "dc_labels_agent.json", {result["sample"][0]["id"]: "yes"})
    done = run_tool("sheets", "--out", str(out))
    assert done.returncode == 0 and "9 frames in the review page" in done.stdout
    page = (out / "dc_review.html").read_text(encoding="utf-8")
    assert "__DATA__" not in page and "__LABELS__" not in page
    assert all(s["id"] in page for s in result["sample"])
    assert "only_a" not in page and "only_b" not in page and "direction" not in page
    assert f'"{result["sample"][0]["id"]}": "yes"' in page  # the agent's answer is shown beside the radio buttons


def test_t_det_08_a_detector_that_has_the_box_where_a_person_is_counts_as_right(tmp_path: Path):
    result = make_result()
    out = write_run(tmp_path, result)
    label_file(out, "dc_labels_h.json", answers(result, only_b="yes", only_a="yes"))  # a person in every picture
    done = run_tool("report", "--out", str(out))
    assert done.returncode == 0 and "decision: materially_better (C)" in done.stdout, done.stdout
    assert reviewed(out) == {"n_discordant": 9, "n_reviewed": 9, "b_better": 8, "a_better": 1, "unsure": 0}


def test_t_det_08_a_box_where_nobody_is_counts_against_the_detector_that_drew_it(tmp_path: Path):
    result = make_result()
    out = write_run(tmp_path, result)
    label_file(out, "dc_labels_h.json", answers(result, only_b="no", only_a="no"))  # nobody in any picture
    done = run_tool("report", "--out", str(out))
    assert done.returncode == 0 and "decision: not_materially_better" in done.stdout, done.stdout
    assert reviewed(out) == {"n_discordant": 9, "n_reviewed": 9, "b_better": 1, "a_better": 8, "unsure": 0}


def test_t_det_08_cannot_tell_counts_for_neither_detector(tmp_path: Path):
    result = make_result()
    out = write_run(tmp_path, result)
    labels = answers(result, only_b="yes", only_a="yes")
    for s in [s for s in result["sample"] if s["direction"] == "only_b"][:3]:
        labels[s["id"]] = "unsure"
    label_file(out, "dc_labels_h.json", labels)
    done = run_tool("report", "--out", str(out))
    assert done.returncode == 0 and "decision: not_materially_better" in done.stdout, done.stdout  # 5 - 1 = 4, under 5
    assert reviewed(out) == {"n_discordant": 9, "n_reviewed": 9, "b_better": 5, "a_better": 1, "unsure": 3}


def test_t_det_08_the_answer_of_the_person_wins_over_the_one_of_the_agent_row_by_row(tmp_path: Path):
    result = make_result()
    out = write_run(tmp_path, result)
    label_file(out, "dc_labels_agent.json", answers(result, only_b="yes", only_a="yes"))
    first_b = next(s["id"] for s in result["sample"] if s["direction"] == "only_b")
    label_file(out, "dc_labels_h.json", {first_b: "no"})  # the person says there is nobody in that one
    done = run_tool("report", "--out", str(out))
    assert done.returncode == 0, done.stderr
    assert reviewed(out) == {"n_discordant": 9, "n_reviewed": 9, "b_better": 7, "a_better": 2, "unsure": 0}


def test_t_det_08_without_any_answer_the_runs_are_not_evaluated_and_there_is_no_decision(tmp_path: Path):
    out = write_run(tmp_path, make_result())
    done = run_tool("report", "--out", str(out))
    assert done.returncode == 0 and "decision: no_decision" in done.stdout, done.stdout
    assert "C not evaluated" in done.stdout
    assert reviewed(out)["n_reviewed"] == 0 and reviewed(out)["n_discordant"] == 9


def test_t_det_08_with_more_runs_than_the_sample_the_report_counts_all_runs_and_the_reviewed_ones(tmp_path: Path):
    result = make_result(n_only_b=70, n_only_a=0)
    assert len(result["sample"]) == 60 and result["c"]["runs_only_b"] == 70  # the sample is capped at 60
    out = write_run(tmp_path, result)
    label_file(out, "dc_labels_h.json", answers(result, only_b="yes", only_a="yes"))
    done = run_tool("report", "--out", str(out))
    assert done.returncode == 0 and "decision: materially_better (C)" in done.stdout, done.stdout
    assert reviewed(out) == {"n_discordant": 70, "n_reviewed": 60, "b_better": 60, "a_better": 0, "unsure": 0}


def test_t_det_08_a_run_with_no_disagreement_needs_no_review_and_the_rule_can_answer(tmp_path: Path):
    out = write_run(tmp_path, make_result(n_only_b=0, n_only_a=0))
    done = run_tool("report", "--out", str(out))
    assert done.returncode == 0 and "decision: not_materially_better" in done.stdout, done.stdout


def test_t_det_08_an_answer_that_is_not_yes_no_or_unsure_is_refused_without_the_folder(tmp_path: Path):
    result = make_result()
    out = write_run(tmp_path, result)
    label_file(out, "dc_labels_h.json", {result["sample"][0]["id"]: "maybe"})
    done = run_tool("report", "--out", str(out))
    assert done.returncode == 2 and "must be yes, no or unsure" in done.stderr
    assert str(tmp_path) not in done.stderr + done.stdout


def test_t_det_08_a_label_file_that_is_not_json_is_refused(tmp_path: Path):
    out = write_run(tmp_path, make_result())
    (out / "dc_labels_h.json").write_text("{not json", encoding="utf-8")
    for command in ("report", "sheets"):
        done = run_tool(command, "--out", str(out))
        assert done.returncode == 2 and "not valid JSON" in done.stderr, command
