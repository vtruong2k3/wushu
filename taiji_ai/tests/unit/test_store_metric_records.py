"""T-MET-11c: the store of signed metric records (P5.09).

A record is data the coach signs and a result becomes conclusive only through it, so the store is strict: it writes a
record only if the registry accepts it (``check_record``), only with the role code of the person who signs it as the
actor, never in the future, never over an enabled or retired record, and never as a second enabled record of one metric
version. Every write is one transaction with its ``audit_log`` row, and neither a message nor the audit row carries the
coach's sentence (the audit keeps its SHA-256).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from helpers.metric_records import SENTENCE, draft_for, record_for
from taiji_ai.config import Settings
from taiji_ai.metrics.records import MetricRecordError
from taiji_ai.schemas.metric_record import MetricRecord
from taiji_ai.store.db import connect
from taiji_ai.store.metric_records import current_record, load_record, retire_record, save_record

TODAY = date(2026, 12, 15)
SHA = hashlib.sha256(SENTENCE.encode("utf-8")).hexdigest()


@pytest.fixture
def conn(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    with closing(connect(settings.db_path, settings.migrations_dir)) as connection:
        yield connection


def save(conn: sqlite3.Connection, record: MetricRecord, actor: str | None = None, **kwargs: Any) -> MetricRecord:
    return save_record(conn, record, actor=actor or record.signed_by or "cli:A", today=TODAY, **kwargs)


def audit(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT actor, action, entity, before, after FROM audit_log ORDER BY id"))


def rows(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(r) for r in conn.execute("SELECT * FROM metric_record ORDER BY metric_name, version")]


# --- save and load ----------------------------------------------------------------------------------------------------
def test_t_met_11c_a_saved_record_loads_back_equal_with_its_types():
    with closing(sqlite3.connect(":memory:")) as plain:  # a connection without the Row factory works too
        from taiji_ai.store.db import apply_migrations

        apply_migrations(plain, Settings().migrations_dir)
        record = record_for(
            "speed_hips",
            {"pause_tau": 0.1, "pause_min_s": 0.3},
            data_sources=({"dataset_id": "D08", "license": "own"},),
        )
        saved = save(plain, record)
        loaded = load_record(plain, "speed_hips", "1")
    assert saved == record and loaded == record
    assert isinstance(loaded.supported_views, tuple) and isinstance(loaded.signed_at, date)
    assert loaded.data_sources[0].dataset_id == "D08" and loaded.parameters["pause_tau"] == 0.1


def test_t_met_11c_a_missing_record_is_none_and_the_key_is_checked_not_echoed(conn):
    assert load_record(conn, "speed_hips", "1") is None
    calls = {
        "metric_name": (("Speed Hips", "Nguyễn Văn A", "x" * 70, "", "a;b"), lambda v: load_record(conn, v, "1")),
        "version": (("01", "v1", "Nguyễn", "", "1;2"), lambda v: load_record(conn, "speed_hips", v)),
        "metric_version": (("0", "v1", "Nguyễn", "", "1.5"), lambda v: current_record(conn, "speed_hips", v)),
    }
    for field, (bad_values, call) in calls.items():
        messages = set()
        for bad in bad_values:
            with pytest.raises(MetricRecordError, match=field) as raised:
                call(bad)
            messages.add(str(raised.value))
        assert len(messages) == 1, field  # one fixed message whatever was typed: the input is not echoed


def test_t_met_11c_a_draft_may_be_written_by_anyone_a_signed_record_only_by_its_signer(conn):
    save(conn, draft_for("speed_hips"), "cli:A")
    for actor in ("cli:A", "cli:B", "cli:O", "cli:H2"):
        with pytest.raises(MetricRecordError, match="signed_by"):
            save(conn, record_for("speed_hands"), actor)
    save(conn, record_for("speed_hands"), "cli:H")
    with pytest.raises(MetricRecordError, match="signed_by"):
        save(conn, record_for("speed_feet", signed_by="cli:H2"), "cli:H")  # the writer is not the signer
    save(conn, record_for("speed_feet", signed_by="cli:H2"), "cli:H2")
    kept = record_for("hip_height_b", status="experimental", measurement_error=0.5)  # a signed decision: signer writes
    with pytest.raises(MetricRecordError, match="signed_by"):
        save(conn, kept, "cli:A")
    save(conn, kept, "cli:H")


def test_t_met_11c_the_actor_is_a_role_code_never_a_name_and_is_not_echoed(conn):
    messages = set()
    for actor in ("", "Dr Lan", "cli:", "cli:Z", "cli:H123", "H", "cli:h", "cli:H\n", "Nguyễn Văn A"):
        with pytest.raises(MetricRecordError, match="actor") as raised:
            save_record(conn, draft_for("speed_hips"), actor=actor, today=TODAY)
        messages.add(str(raised.value))
    assert len(messages) == 1  # one fixed message whatever was typed: the input is not echoed
    assert rows(conn) == [] and audit(conn) == []


def test_t_met_11c_a_signature_from_the_future_is_refused_today_is_fine(conn):
    with pytest.raises(MetricRecordError, match="signed_at"):
        save(conn, record_for("speed_hips", signed_at=date(2026, 12, 16)))
    assert rows(conn) == []
    save(conn, record_for("speed_hips", signed_at=TODAY))


def test_t_met_11c_the_registry_check_runs_before_anything_is_written(conn):
    for bad in (
        record_for("speed_hips", metric_version="2"),
        record_for("speed_hips", units="deg"),
        record_for("speed_hips", {"roll_deg": 1.0}),
        record_for("hip_height_b", {"pause_tau": 0.1, "pause_min_s": 0.3}),
    ):
        with pytest.raises(MetricRecordError):
            save(conn, bad)
    assert rows(conn) == [] and audit(conn) == []


def test_t_met_11c_a_retired_record_is_made_by_retiring_not_by_saving(conn):
    with pytest.raises(MetricRecordError, match="retire_record"):
        save(conn, record_for("speed_hips", status="retired"))
    assert rows(conn) == []


# --- the audit row ----------------------------------------------------------------------------------------------------
def test_t_met_11c_a_save_writes_one_audit_row_with_the_hash_of_the_sentence_not_the_sentence(conn):
    save(conn, record_for("speed_hips"))
    (row,) = audit(conn)
    assert (row["actor"], row["action"], row["entity"]) == ("cli:H", "metric_record.save", "metric_record:speed_hips:1")
    assert row["before"] is None
    after = json.loads(row["after"])
    assert after["status"] == "enabled" and after["signed_by"] == "cli:H" and after["intended_use_sha256"] == SHA
    assert "intended_use" not in after and SENTENCE not in row["after"] and "Dùng" not in row["after"]
    assert after["parameters"] == {"filter_cutoff_hz": 6.0} and after["signed_at"] == "2026-12-01"


def test_t_met_11c_replacing_a_draft_audits_the_state_before_and_after(conn):
    first = draft_for("speed_hips", intended_use="first draft")
    save(conn, first, "cli:A")
    second = draft_for("speed_hips", intended_use="second draft", supported_views=("front",))
    save(conn, second, "cli:B")
    assert len(rows(conn)) == 1 and load_record(conn, "speed_hips", "1") == second
    _, replaced = audit(conn)
    assert replaced["action"] == "metric_record.save" and replaced["actor"] == "cli:B"
    before, after = json.loads(replaced["before"]), json.loads(replaced["after"])
    assert before["intended_use_sha256"] == hashlib.sha256(b"first draft").hexdigest()
    assert after["intended_use_sha256"] == hashlib.sha256(b"second draft").hexdigest()
    assert before["supported_views"] == ["front", "side"] and after["supported_views"] == ["front"]
    assert "first draft" not in replaced["before"] and "second draft" not in replaced["after"]


def test_t_met_11c_a_draft_can_be_signed_in_place_and_then_it_never_changes(conn):
    save(conn, draft_for("speed_hips"), "cli:A")
    signed = save(conn, record_for("speed_hips"), "cli:H")  # the same (name, version): the draft becomes the record
    assert signed.status == "enabled" and len(rows(conn)) == 1
    before = rows(conn)
    for other in (
        record_for("speed_hips", measurement_error=0.01),
        draft_for("speed_hips"),
        record_for("speed_hips", status="experimental", signed_by="cli:H", signed_at=date(2026, 12, 2)),
    ):
        with pytest.raises(MetricRecordError, match="never changes"):
            save(conn, other)
    assert rows(conn) == before and len(audit(conn)) == 2


def test_t_met_11c_a_retired_record_never_changes_either(conn):
    save(conn, record_for("speed_hips"))
    retire_record(conn, "speed_hips", "1", signed_by="cli:H2", actor="cli:H2", today=TODAY)
    before = rows(conn)
    with pytest.raises(MetricRecordError, match="never changes"):
        save(conn, record_for("speed_hips"))
    assert rows(conn) == before


# --- one enabled record per metric version ----------------------------------------------------------------------------
def test_t_met_11c_a_second_enabled_record_of_a_metric_version_is_refused_naming_the_ids_and_writes_nothing(conn):
    save(conn, record_for("speed_hips"))
    before, n_audit = rows(conn), len(audit(conn))
    with pytest.raises(MetricRecordError, match=r"speed_hips.*version 1.*version 2|version 2.*version 1") as raised:
        save(conn, record_for("speed_hips", version="2"))
    assert "retire" in str(raised.value) and SENTENCE not in str(raised.value)
    assert rows(conn) == before and len(audit(conn)) == n_audit  # one transaction: nothing of the failed write remains


def test_t_met_11c_other_metrics_and_drafts_and_a_later_record_after_a_retirement_are_fine(conn):
    save(conn, record_for("speed_hips"))
    save(conn, record_for("speed_hands"))
    save(conn, draft_for("speed_hips", version="2"))  # drafts may be many
    save(conn, draft_for("speed_hips", version="3"))
    retire_record(conn, "speed_hips", "1", signed_by="cli:H", actor="cli:H", today=TODAY)
    save(conn, record_for("speed_hips", version="2", measurement_error=0.04))  # the draft of version 2 is signed
    assert load_record(conn, "speed_hips", "2").status == "enabled"  # type: ignore[union-attr]
    assert load_record(conn, "speed_hips", "1").status == "retired"  # type: ignore[union-attr]


# --- retire -----------------------------------------------------------------------------------------------------------
def test_t_met_11c_retiring_changes_the_status_and_the_signature_only_and_is_audited(conn):
    saved = save(conn, record_for("speed_hips"))
    retired = retire_record(conn, "speed_hips", "1", signed_by="cli:H2", actor="cli:H2", today=TODAY)
    assert retired.status == "retired" and retired.signed_by == "cli:H2" and retired.signed_at == TODAY
    assert retired == saved.model_copy(update={"status": "retired", "signed_by": "cli:H2", "signed_at": TODAY})
    assert load_record(conn, "speed_hips", "1") == retired
    _, row = audit(conn)
    assert (row["actor"], row["action"], row["entity"]) == (
        "cli:H2",
        "metric_record.retire",
        "metric_record:speed_hips:1",
    )
    before, after = json.loads(row["before"]), json.loads(row["after"])
    assert (before["status"], before["signed_by"]) == ("enabled", "cli:H")  # the first signature is kept in the audit
    assert (after["status"], after["signed_by"], after["signed_at"]) == ("retired", "cli:H2", "2026-12-15")
    assert SENTENCE not in row["before"] and SENTENCE not in row["after"]


def test_t_met_11c_only_an_enabled_record_can_be_retired_by_the_coach_who_writes_it(conn):
    save(conn, draft_for("speed_hips"), "cli:A")
    with pytest.raises(MetricRecordError, match="not enabled"):
        retire_record(conn, "speed_hips", "1", signed_by="cli:H", actor="cli:H", today=TODAY)
    with pytest.raises(MetricRecordError, match="no record"):
        retire_record(conn, "speed_hips", "9", signed_by="cli:H", actor="cli:H", today=TODAY)
    save(conn, record_for("speed_hands"))
    for signer, actor in (("cli:A", "cli:A"), ("cli:H", "cli:H2"), ("Dr Lan", "cli:H")):
        with pytest.raises(MetricRecordError, match="signed_by|actor") as raised:
            retire_record(conn, "speed_hands", "1", signed_by=signer, actor=actor, today=TODAY)
        assert "Dr Lan" not in str(raised.value)  # a name typed as the signer is refused without being repeated
    assert load_record(conn, "speed_hands", "1").status == "enabled"  # type: ignore[union-attr]
    retire_record(conn, "speed_hands", "1", signed_by="cli:H", actor="cli:H", today=TODAY)
    with pytest.raises(MetricRecordError, match="not enabled"):
        retire_record(conn, "speed_hands", "1", signed_by="cli:H", actor="cli:H", today=TODAY)


# --- the current record -----------------------------------------------------------------------------------------------
def test_t_met_11c_the_current_record_is_the_enabled_one_else_the_highest_version(conn):
    assert current_record(conn, "speed_hips", "1") is None
    save(conn, draft_for("speed_hips", version="1"))
    assert current_record(conn, "speed_hips", "1").version == "1"  # type: ignore[union-attr]
    save(conn, draft_for("speed_hips", version="9"))
    save(conn, draft_for("speed_hips", version="10"))
    current = current_record(conn, "speed_hips", "1")
    assert current is not None and current.version == "10" and current.status == "experimental"  # 10 above 9
    save(conn, record_for("speed_hips", version="2"))
    current = current_record(conn, "speed_hips", "1")
    assert current is not None and current.version == "2" and current.status == "enabled"  # a draft of 10 does not win
    retire_record(conn, "speed_hips", "2", signed_by="cli:H", actor="cli:H", today=TODAY)
    current = current_record(conn, "speed_hips", "1")
    assert current is not None and current.version == "10"  # none enabled: the highest of all


def test_t_met_11c_the_current_record_is_of_one_metric_and_one_metric_version(conn):
    save(conn, record_for("speed_hips"))
    assert current_record(conn, "speed_hands", "1") is None
    assert current_record(conn, "speed_hips", "2") is None
    with pytest.raises(MetricRecordError, match="metric_version"):
        current_record(conn, "speed_hips", "v1")


# --- what never leaks and what never half-happens ---------------------------------------------------------------------
def test_t_met_11c_no_message_carries_the_sentence(conn):
    save(conn, record_for("speed_hips"))
    attempts = [
        lambda: save(conn, record_for("speed_hips")),
        lambda: save(conn, record_for("speed_hips", version="2")),
        lambda: save(conn, record_for("speed_hips", metric_version="2"), "cli:H"),
        lambda: save(conn, record_for("speed_hips", version="3"), "cli:A"),
        lambda: save(conn, record_for("speed_hips", version="4", signed_at=date(2027, 1, 1))),
        lambda: retire_record(conn, "speed_hips", "7", signed_by="cli:H", actor="cli:H", today=TODAY),
    ]
    for attempt in attempts:
        with pytest.raises(MetricRecordError) as raised:
            attempt()
        assert SENTENCE not in str(raised.value) and "Dùng" not in str(raised.value)


def test_t_met_11c_a_row_that_the_model_refuses_is_reported_by_its_key_without_its_text(conn):
    conn.execute(
        "INSERT INTO metric_record (metric_name, version, metric_version, units, status, intended_use, supported_views,"
        " gold_reference, human_variability, smallest_useful_change, measurement_error, min_valid_duration_s,"
        " parameters, data_sources, signed_by, signed_at) VALUES ('speed_hips', '1', '1', 'body_lengths_per_s',"
        " 'enabled', ?, '[\"front\"]', 'REPORT-1', 0.01, 0.2, 0.05, 0.1, '{\"filter_cutoff_hz\": 0.0}', '[]', 'cli:H',"
        " '2026-12-01')",
        (SENTENCE,),
    )  # the database accepts it; the model refuses a cut-off of 0
    with pytest.raises(MetricRecordError, match="speed_hips.*1.*invalid") as raised:
        load_record(conn, "speed_hips", "1")
    assert SENTENCE not in str(raised.value) and "filter_cutoff_hz" in str(raised.value)
    with pytest.raises(MetricRecordError, match="invalid"):
        current_record(conn, "speed_hips", "1")
