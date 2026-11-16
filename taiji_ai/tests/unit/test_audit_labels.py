"""T-AUDIT-03: the review file: vocabulary, validation, the score of each named joint (P3.08)."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from taiji_ai.audit import AuditError
from taiji_ai.audit.labels import (
    COLUMNS,
    Label,
    ReviewRow,
    agreement,
    expand_joints,
    final_label,
    read_review,
    score_warns,
    write_template,
)
from taiji_ai.pose.skeleton import JOINTS

CANDIDATES = [
    ("fc-001", "d20-v1", 120, 5.0, ("jump", "swap_pair")),
    ("fc-002", "d20-v2", 300, 12.5, ("find_back",)),
    ("fc-003", "d20-v2", 480, 20.0, ("blind",)),
]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in COLUMNS})


def base(cid: str = "fc-001", **fields: str) -> dict[str, str]:
    return {"id": cid, "video": "d20-v1", "frame_index": "120", "t_sec": "5.000", "tags": "jump", **fields}


OK = {"a_verdict": "ok", "a_view": "front", "a_situation": "none"}
FAIL = {
    "a_verdict": "failure", "a_type": "lr_swap", "a_joints": "LWrist|RWrist", "a_severity": "S1", "a_view": "side",
    "a_situation": "occlusion", "a_cadence": "both",
}  # fmt: skip


# --- T-AUDIT-03a: reading and refusing ------------------------------------------------------------------------------
def test_t_audit_03a_the_template_has_the_columns_and_the_data_and_empty_opinions(tmp_path: Path):
    write_template(tmp_path / "r.csv", CANDIDATES)
    rows = read_review(tmp_path / "r.csv", expected_ids=[c[0] for c in CANDIDATES], require_agent=False)
    assert [r.cid for r in rows] == ["fc-001", "fc-002", "fc-003"]
    assert rows[0].video == "d20-v1" and rows[0].frame_index == 120 and rows[0].t_sec == 5.0
    assert rows[0].tags == ("jump", "swap_pair") and rows[0].a == Label() and not rows[0].h_confirmed
    header = (tmp_path / "r.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert tuple(header) == COLUMNS and header[:5] == ["id", "video", "frame_index", "t_sec", "tags"]


def test_t_audit_03a_an_empty_template_is_refused_when_the_agent_must_have_filled_it(tmp_path: Path):
    write_template(tmp_path / "r.csv", CANDIDATES)
    with pytest.raises(AuditError, match="fc-001.*verdict is missing"):
        read_review(tmp_path / "r.csv")


def test_t_audit_03a_a_good_file_is_read(tmp_path: Path):
    write_rows(tmp_path / "r.csv", [base("fc-001", **FAIL), base("fc-002", **OK), base("fc-003", **OK)])
    rows = read_review(tmp_path / "r.csv", expected_ids=["fc-001", "fc-002", "fc-003"])
    assert rows[0].a.joints == ("LWrist", "RWrist") and rows[0].a.severity == "S1" and rows[1].a.verdict == "ok"


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"a_type": "melted"}, "type 'melted'"),
        ({"a_view": "above"}, "view 'above'"),
        ({"a_situation": "dancing"}, "situation 'dancing'"),
        ({"a_severity": "S9"}, "severity 'S9'"),
        ({"a_cadence": "maybe"}, "cadence 'maybe'"),
        ({"a_verdict": "bad"}, "verdict 'bad'"),
        ({"a_joints": "LWrist|Elbow"}, "joint 'Elbow'"),
        ({"h_view": "above"}, "view 'above'"),
        ({"h_joints": "LHand"}, "joint 'LHand'"),
    ],
)
def test_t_audit_03a_a_value_outside_the_vocabulary_is_refused_naming_the_row_and_the_field(
    tmp_path: Path, fields: dict[str, str], message: str
):
    write_rows(tmp_path / "r.csv", [base("fc-001", **{**FAIL, **fields})])
    with pytest.raises(AuditError, match=message) as error:
        read_review(tmp_path / "r.csv")
    assert "fc-001" in str(error.value)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({**OK, "a_severity": "S2"}, "'ok' row has no type"),
        ({**OK, "a_type": "joint_off"}, "'ok' row has no type"),
        ({**OK, "a_joints": "LWrist"}, "'ok' row has no type"),
        ({**FAIL, "a_type": "", "a_severity": "S1"}, "needs a type and a severity"),
        ({**FAIL, "a_severity": ""}, "needs a type and a severity"),
        ({**FAIL, "a_joints": ""}, "names the wrong joints"),
        ({**FAIL, "a_view": ""}, "view and situation are required"),
        ({**FAIL, "a_situation": ""}, "view and situation are required"),
    ],
)
def test_t_audit_03a_a_row_that_is_not_whole_is_refused(tmp_path: Path, fields: dict[str, str], message: str):
    write_rows(tmp_path / "r.csv", [base("fc-001", **fields)])
    with pytest.raises(AuditError, match=message):
        read_review(tmp_path / "r.csv")


def test_t_audit_03a_a_person_or_a_missed_person_failure_needs_no_joints(tmp_path: Path):
    for kind in ("wrong_person", "missed_person", "other"):
        write_rows(tmp_path / "r.csv", [base("fc-001", **{**FAIL, "a_type": kind, "a_joints": ""})])
        assert read_review(tmp_path / "r.csv")[0].a.type == kind


def test_t_audit_03a_columns_ids_and_candidates_are_checked(tmp_path: Path):
    (tmp_path / "wrong.csv").write_text("id,video\nfc-001,d20-v1\n", encoding="utf-8")
    with pytest.raises(AuditError, match="columns"):
        read_review(tmp_path / "wrong.csv")
    write_rows(tmp_path / "twice.csv", [base("fc-001", **OK), base("fc-001", **OK)])
    with pytest.raises(AuditError, match="repeated"):
        read_review(tmp_path / "twice.csv")
    write_rows(tmp_path / "r.csv", [base("fc-001", **OK), base("fc-009", **OK)])
    with pytest.raises(AuditError, match="missing candidates.*fc-002.*unexpected rows.*fc-009"):
        read_review(tmp_path / "r.csv", expected_ids=["fc-001", "fc-002"])
    with pytest.raises(AuditError, match="could not be read"):
        read_review(tmp_path / "nothing.csv")
    write_rows(tmp_path / "num.csv", [base("fc-001", **{**OK, "frame_index": "abc"})])
    with pytest.raises(AuditError, match="numbers"):
        read_review(tmp_path / "num.csv")
    write_rows(tmp_path / "conf.csv", [base("fc-001", **{**OK, "h_confirmed": "perhaps"})])
    with pytest.raises(AuditError, match="h_confirmed"):
        read_review(tmp_path / "conf.csv")


# --- T-AUDIT-03b: the final label, the agreement, the score of the joints -------------------------------------------
def test_t_audit_03b_the_person_overrides_field_by_field_and_an_empty_field_keeps_the_agent(tmp_path: Path):
    write_rows(
        tmp_path / "r.csv",
        [
            base(
                "fc-001",
                **{**FAIL, "h_confirmed": "yes", "h_severity": "S2", "h_view": "oblique", "h_joints": "LAnkle"},
            )
        ],
    )
    row = read_review(tmp_path / "r.csv")[0]
    final = final_label(row)
    assert (final.type, final.severity, final.view, final.joints) == ("lr_swap", "S2", "oblique", ("LAnkle",))
    assert final.situation == "occlusion" and final.cadence == "both" and final.verdict == "failure"
    assert row.a.severity == "S1"  # the agent's opinion is kept as it was


def test_t_audit_03b_a_person_who_finds_the_frame_fine_clears_the_failure_fields_of_the_agent(tmp_path: Path):
    write_rows(tmp_path / "r.csv", [base("fc-001", **{**FAIL, "h_verdict": "ok", "h_confirmed": "yes"})])
    row = read_review(tmp_path / "r.csv")[0]
    final = final_label(row)
    assert (final.verdict, final.type, final.joints, final.severity, final.cadence) == ("ok", "", (), "", "")
    assert (final.view, final.situation) == ("side", "occlusion")  # the rest is still the agent's
    assert row.a.type == "lr_swap" and row.a.joints == ("LWrist", "RWrist")  # the agent's opinion is kept as it was


def test_t_audit_03b_the_final_label_must_be_whole_even_after_the_override(tmp_path: Path):
    # ok, but the person also gives a severity: still not a whole label
    write_rows(tmp_path / "r.csv", [base("fc-001", **{**FAIL, "h_verdict": "ok", "h_severity": "S2"})])
    with pytest.raises(AuditError, match="'ok' row has no type"):
        read_review(tmp_path / "r.csv")
    # a failure over an ok of the agent needs the type, the joints and the severity from the person
    write_rows(tmp_path / "r.csv", [base("fc-001", **{**OK, "h_verdict": "failure", "h_type": "joint_off"})])
    with pytest.raises(AuditError, match="needs a type and a severity"):
        read_review(tmp_path / "r.csv")


def test_t_audit_03b_agreement_counts_only_the_rows_the_person_looked_at(tmp_path: Path):
    write_rows(
        tmp_path / "r.csv",
        [
            base("fc-001", **{**FAIL, "h_confirmed": "yes"}),  # looked, agrees with everything
            base("fc-002", **{**FAIL, "h_confirmed": "yes", "h_severity": "S2", "h_joints": "RWrist|LWrist"}),
            base("fc-003", **FAIL),  # not looked at
        ],
    )
    out = agreement(read_review(tmp_path / "r.csv"))
    assert out["severity"] == (2, 1) and out["verdict"] == (2, 2) and out["type"] == (2, 2)
    assert out["joints"] == (2, 2)  # the same joints in another order are the same
    assert agreement([]) == {f: (0, 0) for f in out}


def test_t_audit_03b_groups_and_names_expand_to_joint_indices():
    assert expand_joints(["feet"]) == sorted(
        JOINTS.index(n) for n in ("LBigToe", "RBigToe", "LSmallToe", "RSmallToe", "LHeel", "RHeel")
    )
    assert expand_joints(["all"]) == list(range(26))
    assert expand_joints(["LWrist", "arms", "LWrist"]) == sorted(
        {JOINTS.index(n) for n in ("LElbow", "RElbow", "LWrist", "RWrist")}
    )
    with pytest.raises(AuditError):
        expand_joints(["tail"])


def test_t_audit_03b_the_score_warns_only_if_every_wrong_joint_is_under_tau():
    scores = np.full(26, 0.9)
    scores[JOINTS.index("LWrist")] = 0.1
    scores[JOINTS.index("RWrist")] = 0.29
    assert score_warns(["LWrist", "RWrist"], scores, 0.3) is True
    assert score_warns(["LWrist", "LElbow"], scores, 0.3) is False  # the elbow scores 0.9: a mask would keep it
    assert score_warns(["arms"], scores, 0.3) is False
    scores[JOINTS.index("LElbow")] = 0.3  # exactly at tau is valid: not warned
    assert score_warns(["LElbow"], scores, 0.3) is False
    scores[JOINTS.index("LElbow")] = np.nan  # no score at all: the mask removes it
    assert score_warns(["LElbow"], scores, 0.3) is True
    assert score_warns([], scores, 0.3) is None


def test_t_audit_03b_a_review_row_is_a_plain_value():
    row = ReviewRow("fc-001", "d20-v1", 1, 0.5, ("blind",), Label(verdict="ok"), Label(), False)
    assert final_label(row).verdict == "ok"
