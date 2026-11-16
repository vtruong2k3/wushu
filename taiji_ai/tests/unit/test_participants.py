"""T-DATA-05: the participant registry (P2.08).

A recording enters the system only with a participant pseudonym and a consent reference (AGENTS.md section 9.5). The
database accepts ``consent_analysis = 0`` and a missing answer is a default, so these rules live in the code: every
consent answer is given explicitly, analysis consent is required, and every write is one transaction with its audit
row (IDs only, no names).
"""

from __future__ import annotations

import inspect
import json
import logging
from datetime import date, datetime, timedelta

import pytest

from taiji_ai.config import PROJECT_ROOT
from taiji_ai.store import participants as participants_module
from taiji_ai.store.db import connect
from taiji_ai.store.participants import (
    Participant,
    ParticipantError,
    get_participant,
    register_participant,
    require_participant,
    update_consent,
)

TODAY = date(2026, 11, 16)
CONSENT_FIELDS = {"consent_ref", "consent_analysis", "consent_train", "consent_share", "retention_until"}


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "app.sqlite3", PROJECT_ROOT / "migrations")
    yield c
    c.close()


def _reg(conn, **over):
    args = {
        "participant_id": "P03",
        "consent_ref": "CONSENT-2026-011",
        "analysis": True,
        "train": False,
        "share": True,
        "retention_until": "2027-12-31",
        "actor": "cli:O",
        "today": TODAY,
    }
    args.update(over)
    return register_participant(conn, args.pop("participant_id"), args.pop("consent_ref"), **args)


def _upd(conn, participant_id="P03", **over):
    args = {"actor": "cli:O", "today": TODAY}
    args.update(over)
    return update_consent(conn, participant_id, **args)


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _nothing_written(conn) -> None:
    assert _count(conn, "participant") == 0
    assert _count(conn, "audit_log") == 0


# --- T-DATA-05a: a valid registration ---------------------------------------------------------------------------------


def test_t_data_05a_a_valid_registration_stores_the_row_and_one_audit_row(conn):
    p = _reg(conn)
    assert p == Participant(
        participant_id="P03",
        consent_ref="CONSENT-2026-011",
        consent_analysis=True,
        consent_train=False,
        consent_share=True,
        retention_until=date(2027, 12, 31),
        created_at=p.created_at,
    )
    row = conn.execute("SELECT * FROM participant").fetchone()
    assert (row["consent_analysis"], row["consent_train"], row["consent_share"]) == (1, 0, 1)
    assert row["retention_until"] == "2027-12-31" and row["consent_ref"] == "CONSENT-2026-011"
    assert row["level_self"] is None and row["level_coach"] is None  # not consent data, not set here
    audit = conn.execute("SELECT * FROM audit_log").fetchall()
    assert len(audit) == 1
    assert (audit[0]["actor"], audit[0]["action"], audit[0]["entity"]) == (
        "cli:O",
        "participant.register",
        "participant:P03",
    )
    assert audit[0]["before"] is None
    after = json.loads(audit[0]["after"])
    assert set(after) == CONSENT_FIELDS  # IDs, flags and a date: no name, no free text
    assert after == {
        "consent_ref": "CONSENT-2026-011",
        "consent_analysis": 1,
        "consent_train": 0,
        "consent_share": 1,
        "retention_until": "2027-12-31",
    }


def test_t_data_05a_get_participant_returns_the_stored_row_or_none(conn):
    assert get_participant(conn, "P03") is None
    p = _reg(conn)
    assert get_participant(conn, "P03") == p


def test_t_data_05a_the_participant_model_exposes_only_consent_data():
    assert set(Participant.__dataclass_fields__) == {"participant_id", *CONSENT_FIELDS, "created_at"}


# --- T-DATA-05b: refused registrations leave nothing behind -----------------------------------------------------------


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"analysis": False}, "analysis consent is required"),
        ({"consent_ref": ""}, "consent_ref"),
        ({"consent_ref": "CONSENT-26-011"}, "consent_ref"),
        ({"consent_ref": "consent-2026-011"}, "consent_ref"),
        ({"consent_ref": "CONSENT-2026-11"}, "consent_ref"),
        ({"participant_id": ""}, "participant_id"),
        ({"participant_id": "p03"}, "participant_id"),
        ({"participant_id": "P3"}, "participant_id"),
        ({"participant_id": "P03x"}, "participant_id"),
        ({"participant_id": "Quang"}, "participant_id"),
        ({"retention_until": "31/12/2027"}, "retention_until"),
        ({"retention_until": "20271231"}, "retention_until"),
        ({"retention_until": "2027-13-01"}, "retention_until"),
        ({"retention_until": "2027-02-30"}, "retention_until"),
        ({"retention_until": "2026-11-15"}, "in the past"),  # the day before TODAY
        ({"retention_until": ""}, "retention_until"),
        ({"retention_until": 20271231}, "retention_until"),
        ({"retention_until": datetime(2027, 12, 31, 8, 0)}, "date and time"),
        ({"actor": "O"}, "actor"),
        ({"actor": "cli:"}, "actor"),
        ({"actor": "cli:Quang"}, "actor"),
        ({"actor": "cli:X"}, "actor"),
        ({"actor": "cli:H123"}, "actor"),
        ({"actor": ""}, "actor"),
    ],
)
def test_t_data_05b_a_refused_registration_writes_nothing(conn, over, message):
    with pytest.raises(ParticipantError, match=message):
        _reg(conn, **over)
    _nothing_written(conn)


def test_t_data_05b_the_refusal_of_analysis_points_to_the_consent_form(conn):
    with pytest.raises(ParticipantError, match=r"consent_form\.md"):
        _reg(conn, analysis=False)


def test_t_data_05b_retention_today_is_accepted_and_yesterday_is_not(conn):
    assert _reg(conn, participant_id="P01", retention_until=TODAY).retention_until == TODAY
    with pytest.raises(ParticipantError, match="in the past"):
        _reg(conn, participant_id="P02", retention_until=TODAY - timedelta(days=1))
    assert _count(conn, "participant") == 1


def test_t_data_05b_roles_with_up_to_two_digits_are_accepted(conn):
    for i, actor in enumerate(["cli:A", "cli:B", "cli:O", "cli:H", "cli:H1", "cli:H12"], start=1):
        _reg(conn, participant_id=f"P{i:02d}", actor=actor)
    assert _count(conn, "audit_log") == 6


# --- T-DATA-05c: no silent default for a consent answer ---------------------------------------------------------------


@pytest.mark.parametrize("missing", ["analysis", "train", "share", "actor"])
def test_t_data_05c_a_consent_answer_cannot_be_left_out(conn, missing):
    args = {"analysis": True, "train": False, "share": True, "retention_until": None, "actor": "cli:O"}
    del args[missing]
    with pytest.raises(TypeError, match=missing):
        register_participant(conn, "P03", "CONSENT-2026-011", **args)
    _nothing_written(conn)


def test_t_data_05c_the_answers_are_keyword_only(conn):
    with pytest.raises(TypeError):
        register_participant(conn, "P03", "CONSENT-2026-011", True, False, True)  # type: ignore[misc]
    _nothing_written(conn)


@pytest.mark.parametrize("name", ["analysis", "train", "share"])
@pytest.mark.parametrize("value", [1, 0, "yes", "no", None])
def test_t_data_05c_an_answer_must_be_a_real_boolean(conn, name, value):
    with pytest.raises(ParticipantError, match=f"{name} must be True or False"):
        _reg(conn, **{name: value})
    _nothing_written(conn)


def test_t_data_05c_retention_may_be_left_empty_with_a_warning(conn, caplog):
    with caplog.at_level(logging.WARNING, logger="taiji_ai.store.participants"):
        p = _reg(conn, retention_until=None)
    assert p.retention_until is None
    assert conn.execute("SELECT retention_until FROM participant").fetchone()[0] is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "P03" in warnings[0].getMessage()


# --- T-DATA-05d: update_consent --------------------------------------------------------------------------------------


def test_t_data_05d_an_update_changes_only_the_given_field_and_writes_before_and_after(conn):
    _reg(conn)
    p = _upd(conn, train=True)
    assert (p.consent_train, p.consent_share, p.retention_until, p.consent_ref) == (
        True,
        True,
        date(2027, 12, 31),
        "CONSENT-2026-011",
    )
    audit = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    assert [a["action"] for a in audit] == ["participant.register", "participant.update_consent"]
    before, after = json.loads(audit[1]["before"]), json.loads(audit[1]["after"])
    assert before == json.loads(audit[0]["after"])
    assert set(before) == set(after) == CONSENT_FIELDS
    assert [k for k in after if after[k] != before[k]] == ["consent_train"]
    assert audit[1]["entity"] == "participant:P03"


def test_t_data_05d_share_and_retention_can_change_and_retention_can_be_cleared(conn, caplog):
    _reg(conn)
    assert _upd(conn, share=False).consent_share is False
    assert _upd(conn, retention_until="2028-06-30").retention_until == date(2028, 6, 30)
    with caplog.at_level(logging.WARNING, logger="taiji_ai.store.participants"):
        assert _upd(conn, retention_until=None).retention_until is None
    assert any("P03" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert conn.execute("SELECT retention_until FROM participant").fetchone()[0] is None


def test_t_data_05d_nothing_given_is_an_error(conn):
    _reg(conn)
    with pytest.raises(ParticipantError, match="nothing to change"):
        _upd(conn)
    assert _count(conn, "audit_log") == 1


def test_t_data_05d_giving_the_current_values_is_a_no_op_without_an_audit_row(conn):
    _reg(conn)
    p = _upd(conn, train=False, share=True, retention_until="2027-12-31")
    assert (p.consent_train, p.consent_share, p.retention_until) == (False, True, date(2027, 12, 31))
    assert _count(conn, "audit_log") == 1


def test_t_data_05d_analysis_and_consent_ref_cannot_be_changed_by_an_update():
    params = set(inspect.signature(update_consent).parameters)
    assert "analysis" not in params and "consent_ref" not in params
    assert {"train", "share", "retention_until", "actor"} <= params


def test_t_data_05d_an_unknown_participant_and_bad_values_are_refused(conn):
    with pytest.raises(ParticipantError, match="not registered"):
        _upd(conn, train=True)
    _reg(conn)
    for over, message in [
        ({"train": 1}, "train must be True or False"),
        ({"share": "yes"}, "share must be True or False"),
        ({"retention_until": "2026-01-01"}, "in the past"),
        ({"retention_until": "soon"}, "retention_until"),
        ({"train": True, "actor": "cli:Quang"}, "actor"),
        ({"participant_id": "Quang", "train": True}, "participant_id"),
    ]:
        with pytest.raises(ParticipantError, match=message):
            _upd(conn, **over)
    row = get_participant(conn, "P03")
    assert row is not None and (row.consent_train, row.consent_share) == (False, True)
    assert _count(conn, "audit_log") == 1


# --- T-DATA-05e: an existing ID --------------------------------------------------------------------------------------


def test_t_data_05e_registering_an_existing_id_is_refused_and_changes_nothing(conn):
    first = _reg(conn)
    with pytest.raises(ParticipantError, match="already registered"):
        _reg(conn, consent_ref="CONSENT-2026-099", train=True, share=False, retention_until="2029-01-01")
    assert get_participant(conn, "P03") == first
    assert _count(conn, "participant") == 1 and _count(conn, "audit_log") == 1


# --- T-DATA-05j: require_participant (BUG-0050) ----------------------------------------------------------------------


def test_t_data_05j_require_participant_returns_the_row_or_raises_without_echoing_the_text(conn):
    first = _reg(conn)
    assert require_participant(conn, "P03") == first
    with pytest.raises(ParticipantError, match="participant P09 is not registered"):
        require_participant(conn, "P09")
    with pytest.raises(ParticipantError, match="participant_id") as exc:
        require_participant(conn, "Nguyen-Van-A")
    assert "Nguyen" not in str(exc.value)


@pytest.mark.parametrize("value", ["", "p03", "P3", "P03\n", " P03", 3, None])
def test_t_data_05j_require_participant_refuses_anything_that_is_not_a_pseudonym(conn, value):
    _reg(conn)
    with pytest.raises(ParticipantError, match="participant_id"):
        require_participant(conn, value)  # type: ignore[arg-type]


# --- T-DATA-05g: one transaction per write ---------------------------------------------------------------------------


def test_t_data_05g_a_failing_audit_row_leaves_no_participant(conn, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(participants_module, "_audit", boom)
    with pytest.raises(RuntimeError, match="audit down"):
        _reg(conn)
    _nothing_written(conn)


def test_t_data_05g_a_failing_audit_row_leaves_the_old_consent_in_place(conn, monkeypatch):
    first = _reg(conn)

    def boom(*args, **kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(participants_module, "_audit", boom)
    with pytest.raises(RuntimeError, match="audit down"):
        _upd(conn, train=True, share=False)
    assert get_participant(conn, "P03") == first
    assert _count(conn, "audit_log") == 1


# --- T-DATA-05h: logs carry IDs only ---------------------------------------------------------------------------------


def test_t_data_05h_log_lines_hold_the_pseudonym_and_no_path(conn, caplog, tmp_path):
    with caplog.at_level(logging.INFO, logger="taiji_ai.store.participants"):
        _reg(conn)
        _upd(conn, train=True)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "P03" in text
    assert str(tmp_path) not in text and "\\" not in text and "/" not in text
