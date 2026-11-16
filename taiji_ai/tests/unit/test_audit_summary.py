"""T-AUDIT-04: the numbers and the tables of the review (P3.08), on a constructed review."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from taiji_ai.audit.labels import Label, ReviewRow
from taiji_ai.audit.summary import render_tables, summarise, wilson
from taiji_ai.pose.skeleton import JOINTS

TAU = 0.3


def row(cid: str, tags: tuple[str, ...], a: Label, h: Label | None = None, looked: bool = False) -> ReviewRow:
    return ReviewRow(cid, "d20-v1", int(cid[3:]), float(cid[3:]) / 10.0, tags, a, h or Label(), looked)


def ok(view: str = "front", situation: str = "none") -> Label:
    return Label(verdict="ok", view=view, situation=situation)


def fail(
    kind: str,
    joints: tuple[str, ...],
    sev: str = "S1",
    view: str = "side",
    situation: str = "none",
    cadence: str = "both",
) -> Label:
    return Label(
        verdict="failure", type=kind, joints=joints, severity=sev, view=view, situation=situation, cadence=cadence
    )


def scores_with(**low: float) -> np.ndarray:
    s = np.full(26, 0.9)
    for name, value in low.items():
        s[JOINTS.index(name)] = value
    return s


ROWS = [
    row(
        "fc-001",
        ("jump", "swap_pair"),
        fail("lr_swap", ("LWrist", "RWrist"), view="back", situation="orientation_change"),
    ),
    row("fc-002", ("jump",), fail("joint_off", ("LAnkle",), sev="S2", cadence="n5_only")),
    row("fc-003", ("swap_pair",), fail("flicker", ("LKnee",), sev="S3")),  # minor: listed, not counted
    row("fc-004", ("find_back",), ok(view="back")),
    row("fc-005", ("blind",), ok()),
    row("fc-006", ("blind",), fail("foot_error", ("feet",), sev="S2", situation="one_leg", cadence="unknown")),
    row("fc-007", ("blind",), ok()),
    row("fc-008", ("blind",), fail("wrong_person", (), sev="S1")),
]
SCORES = {
    "fc-001": scores_with(LWrist=0.1, RWrist=0.2),  # every wrong joint is under tau: the score warns
    "fc-002": scores_with(),  # the ankle scores 0.9: not warned
    "fc-003": scores_with(),
    "fc-006": scores_with(LBigToe=0.1),  # one foot joint low, the others high: not warned
}


# --- T-AUDIT-04a: the numbers ---------------------------------------------------------------------------------------
def test_t_audit_04a_wilson_interval_against_known_values():
    lo, hi = wilson(5, 40)  # type: ignore[misc]
    assert lo == pytest.approx(0.0546, abs=1e-3) and hi == pytest.approx(0.2611, abs=1e-3)
    lo0, hi0 = wilson(0, 40)  # type: ignore[misc]
    assert lo0 == 0.0 and hi0 == pytest.approx(0.0877, abs=1e-3)
    lo1, hi1 = wilson(40, 40)  # type: ignore[misc]
    assert hi1 == 1.0 and lo1 == pytest.approx(0.9123, abs=1e-3)
    assert wilson(0, 0) is None


def test_t_audit_04a_counts_precision_and_the_blind_rate():
    s = summarise(ROWS, SCORES, TAU)

    assert (s["n_rows"], s["n_failures"], s["n_minor"], s["n_ok"]) == (8, 4, 1, 3)
    assert s["by_rule"]["jump"] == {"n": 2, "failures": 2, "precision": 1.0}
    assert s["by_rule"]["swap_pair"] == {"n": 2, "failures": 1, "precision": 0.5}  # the minor failure is not counted
    assert s["by_rule"]["find_back"]["precision"] == 0.0
    b = s["blind"]
    assert (b["n"], b["failures"], b["rate"]) == (4, 2, 0.5)
    assert b["wilson95"] == pytest.approx(list(wilson(2, 4)))  # type: ignore[arg-type]
    assert s["by_type"] == {"lr_swap": 1, "joint_off": 1, "foot_error": 1, "wrong_person": 1}


def test_t_audit_04a_by_view_situation_and_joint_group():
    s = summarise(ROWS, SCORES, TAU)
    assert s["by_view"]["back"] == {"frames": 2, "failures": 1} and s["by_view"]["side"] == {"frames": 4, "failures": 3}
    assert s["by_view"]["unknown"] == {"frames": 0, "failures": 0}
    assert s["by_situation"]["orientation_change"] == {"frames": 1, "failures": 1}
    assert s["by_situation"]["one_leg"] == {"frames": 1, "failures": 1}
    # LWrist, RWrist -> arms; LAnkle -> legs; the foot group -> feet; a wrong person names no joint; S3 is not counted
    assert s["by_group"] == {"head": 0, "trunk": 0, "arms": 1, "legs": 1, "feet": 1}


def test_t_audit_04a_the_share_of_failures_the_score_does_not_warn_about():
    s = summarise(ROWS, SCORES, TAU)
    # counted failures with joints: fc-001 (warned), fc-002 (kept), fc-006 (kept); fc-008 names none; fc-003 is minor
    assert s["score"] == {
        "tau_kp": TAU, "failures_with_joints": 3, "not_warned": 2, "warned": 1,
        "share_not_warned": pytest.approx(2 / 3),
    }  # fmt: skip


def test_t_audit_04a_the_cadence_labels_of_the_counted_failures():
    assert summarise(ROWS, SCORES, TAU)["cadence"] == {"both": 2, "n5_only": 1, "unknown": 1}


def test_t_audit_04a_the_person_overrides_the_agent_in_the_counts():
    rows = [
        row(
            "fc-001", ("blind",), fail("lr_swap", ("LWrist",), sev="S1"), Label(severity="S3"), looked=True
        ),  # now minor
        row(
            "fc-002",
            ("blind",),
            ok(),
            Label(verdict="failure", type="joint_off", joints=("LAnkle",), severity="S2"),
            looked=True,
        ),
    ]
    s = summarise(rows, {}, TAU)
    assert (s["n_failures"], s["n_minor"], s["n_ok"]) == (1, 1, 0) and s["blind"]["failures"] == 1
    assert s["agreement"]["severity"] == [2, 0] and s["agreement"]["verdict"] == [2, 1]


def test_t_audit_04a_cases_list_every_failure_with_its_score_verdict_and_no_path():
    cases = {c["id"]: c for c in summarise(ROWS, SCORES, TAU)["cases"]}
    assert set(cases) == {"fc-001", "fc-002", "fc-003", "fc-006", "fc-008"}
    assert cases["fc-001"]["score_warns"] is True and cases["fc-002"]["score_warns"] is False
    assert cases["fc-008"]["score_warns"] is None and cases["fc-003"]["counted"] is False
    assert (
        cases["fc-006"]["frame_index"] == 6
        and cases["fc-006"]["video"] == "d20-v1"
        and cases["fc-006"]["cadence"] == "unknown"
    )


def test_t_audit_04a_a_review_without_blind_frames_or_failures_has_no_rate_not_a_zero():
    s = summarise([row("fc-001", ("jump",), ok())], {}, TAU)
    assert s["blind"] == {"n": 0, "failures": 0, "rate": None, "wilson95": None}
    assert s["score"]["share_not_warned"] is None and s["cases"] == [] and s["by_rule"]["jump"]["precision"] == 0.0


def noted(label: Label, note: str) -> Label:
    return replace(label, note=note)


MARKED = [
    row("fc-001", ("target_event",), noted(fail("other", (), sev="S1"), "[track] performer detected, link lost")),
    row("fc-002", ("blind",), noted(fail("joint_off", ("LAnkle",), sev="S2"), "[edit] fade to black")),
    row("fc-003", ("blind",), noted(ok(), "[edit] title card")),
    row("fc-004", ("blind",), fail("lr_swap", ("LKnee",), sev="S1")),
    row("fc-005", ("blind",), ok()),
    row("fc-006", ("blind",), ok()),
]


def test_t_audit_04c_the_markers_keep_frames_apart_without_dropping_any():
    s = summarise(MARKED, {}, TAU)
    assert s["n_rows"] == 6 and s["n_failures"] == 3  # nothing is dropped from the counts
    assert s["n_failures_pose"] == 2  # the tracker event is not a pose failure
    assert s["markers"] == {"edit": {"frames": 2, "failures": 1}, "track": {"frames": 1, "failures": 1}}
    assert (s["blind"]["n"], s["blind"]["failures"]) == (5, 2)
    without = s["blind_without_edit"]
    assert (without["n"], without["failures"], without["rate"]) == (3, 1, pytest.approx(1 / 3))
    assert without["wilson95"] == pytest.approx(list(wilson(1, 3)))  # type: ignore[arg-type]


def test_t_audit_04c_ordinary_failures_by_video_and_the_score_of_the_ordinary_ones():
    scores = {"fc-002": scores_with(LAnkle=0.1), "fc-004": scores_with()}
    s = summarise(MARKED, scores, TAU)
    assert s["n_failures_ordinary"] == 1  # fc-001 is a tracker event, fc-002 an edit frame; fc-004 is left
    assert s["by_video"] == {"d20-v1": {"frames": 6, "failures": 3, "ordinary_failures": 1}}
    assert s["score"]["failures_with_joints"] == 2 and s["score"]["warned"] == 1 and s["score"]["not_warned"] == 1
    so = s["score_ordinary"]
    assert (so["failures_with_joints"], so["not_warned"], so["warned"], so["share_not_warned"]) == (1, 1, 0, 1.0)
    assert so["wrong_max_bands"] == {
        "under 0.3": 0, "0.3 to 0.5": 0, "0.5 to 0.7": 0, "0.7 to 0.9": 0, "0.9 or more": 1,
    }  # fmt: skip
    assert so["wrong_max_median"] == pytest.approx(0.9)
    text = render_tables(s)
    for expected in (
        "ordinary frames (neither marker): 1",
        "### Frames and failures by video",
        "| d20-v1 | 6 | 3 | 1 |",
        "| all failures | 2 | 1 | 1 | 50.0 % |",
        "| ordinary frames only | 1 | 0 | 1 | 100.0 % |",
    ):
        assert expected.lower() in text.lower(), expected


def test_t_audit_04c_no_ordinary_failure_with_joints_gives_no_share_not_a_zero():
    s = summarise([row("fc-001", ("blind",), ok())], {}, TAU)
    so = s["score_ordinary"]
    assert (so["failures_with_joints"], so["share_not_warned"], so["wrong_max_median"]) == (0, None, None)
    assert set(so["wrong_max_bands"].values()) == {0}
    assert s["n_failures_ordinary"] == 0 and s["by_video"] == {
        "d20-v1": {"frames": 1, "failures": 0, "ordinary_failures": 0}
    }


def test_t_audit_04c_the_note_of_the_person_decides_the_marker():
    rows = [
        row("fc-001", ("blind",), noted(ok(), "[edit] dissolve"), Label(note="a normal frame"), looked=True),
        row("fc-002", ("blind",), ok(), Label(note="[edit] fade"), looked=True),
    ]
    s = summarise(rows, {}, TAU)
    assert s["markers"]["edit"] == {"frames": 1, "failures": 0}  # only fc-002 (fc-001 was corrected by the person)
    assert s["blind_without_edit"]["n"] == 1


def test_t_audit_04c_without_markers_the_two_blind_samples_are_equal_and_the_markers_are_zero():
    s = summarise(ROWS, SCORES, TAU)
    assert s["markers"] == {"edit": {"frames": 0, "failures": 0}, "track": {"frames": 0, "failures": 0}}
    assert s["blind_without_edit"] == s["blind"] and s["n_failures_pose"] == s["n_failures"]


def test_t_audit_04c_the_tables_show_the_markers_and_the_blind_rate_without_edit_frames():
    text = render_tables(summarise(MARKED, {}, TAU))
    for expected in (
        "### Frames that are not an ordinary pose question",
        "| [track] | performer in the picture with a good skeleton, target link lost (tracker event) | 1 | 1 |",
        "| [edit] | fade, dissolve or title of the video editing (not a capture) | 2 | 1 |",
        "without the [track] frames: 2",
        "| all blind frames | 5 | 2 | 40.0 % |",
        "| without [edit] frames | 3 | 1 | 33.3 % |",
    ):
        assert expected.lower() in text.lower(), expected


# --- T-AUDIT-04b: the tables ----------------------------------------------------------------------------------------
def test_t_audit_04b_the_tables_hold_the_numbers():
    text = render_tables(summarise(ROWS, SCORES, TAU))
    for expected in (
        "### The frames reviewed", "| 8 | 4 | 1 | 3 |", "### Precision of each rule", "| jump | 2 | 2 | 100.0 % |",
        "### The blind sample", "| 4 | 2 | 50.0 % |", "### Failures by type", "| lr_swap | 1 |",
        "### Failures by joint group", "| arms | 1 |", "does the score warn", "| 3 | 1 | 2 | 66.7 % |",
        "### Every failure case", "| fc-006 | d20-v1 | 0.60 | 6 | foot_error | feet | S2 |",
    ):  # fmt: skip
        assert expected.lower() in text.lower(), expected


def test_t_audit_04b_an_empty_review_prints_n_a_never_zero_rates():
    text = render_tables(summarise([], {}, TAU))
    assert "n/a" in text and "none" in text
    assert "0.0 %" not in text


def test_t_audit_04b_the_tables_name_no_path_and_no_file():
    text = render_tables(summarise(ROWS, SCORES, TAU))
    assert ".mp4" not in text and "\\" not in text and ".npz" not in text
