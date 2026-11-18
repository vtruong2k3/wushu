"""T-STORE-08: migration 0002 rebuilds ``metric_record`` for the signed records of P5.09.

The table of migration 0001 had one ``threshold`` column, no metric version, no units and no place for the parameters a
record binds (the thresholds and the cut-off of DEC-0061). Nothing wrote it, so 0002 rebuilds it, and it refuses to run
if a row exists. The database itself refuses what the store would refuse (an enabled record without a signature, an
error that is not below the smallest useful change, two enabled records of one metric version, a change to an enabled
or retired record), so a direct SQL write cannot make a metric conclusive by accident.
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from taiji_ai.config import Settings
from taiji_ai.store.db import apply_migrations, connect

MIGRATIONS = Settings().migrations_dir
COLUMNS = [
    "metric_name",
    "version",
    "metric_version",
    "units",
    "status",
    "intended_use",
    "supported_views",
    "gold_reference",
    "human_variability",
    "smallest_useful_change",
    "measurement_error",
    "min_valid_duration_s",
    "parameters",
    "data_sources",
    "signed_by",
    "signed_at",
]
SIGNED: dict[str, Any] = {
    "metric_name": "speed_hips",
    "version": "1",
    "metric_version": "1",
    "units": "body_lengths_per_s",
    "status": "enabled",
    "intended_use": "a test sentence",
    "supported_views": '["front", "side"]',
    "gold_reference": "REPORT-1",
    "human_variability": 0.1,
    "smallest_useful_change": 0.5,
    "measurement_error": 0.2,
    "min_valid_duration_s": 0.5,
    "parameters": '{"filter_cutoff_hz": 6.0}',
    "data_sources": "[]",
    "signed_by": "cli:H",
    "signed_at": "2026-11-17",
}
DRAFT: dict[str, Any] = {
    **SIGNED,
    "status": "experimental",
    "gold_reference": None,
    "human_variability": None,
    "smallest_useful_change": None,
    "measurement_error": None,
    "min_valid_duration_s": None,
    "signed_by": None,
    "signed_at": None,
}


def insert(conn: sqlite3.Connection, **changes: Any) -> None:
    row = {**SIGNED, **changes}
    conn.execute(
        f"INSERT INTO metric_record ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
        list(row.values()),
    )


@pytest.fixture
def only_0001(tmp_path: Path) -> Path:
    folder = tmp_path / "only_0001"
    folder.mkdir()
    shutil.copyfile(MIGRATIONS / "0001_init.sql", folder / "0001_init.sql")
    return folder


@pytest.fixture
def conn(tmp_path: Path):
    with closing(connect(tmp_path / "taiji.db", MIGRATIONS)) as connection:
        yield connection


def columns(conn: sqlite3.Connection) -> list[str]:
    return [row["name"] for row in conn.execute("PRAGMA table_info(metric_record)")]


def versions(conn: sqlite3.Connection) -> list[int]:
    return [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


# --- the migration ---------------------------------------------------------------------------------------------------
def test_t_store_08a_a_fresh_database_has_the_new_table_and_one_enabled_index(conn):
    assert versions(conn) == [1, 2]
    assert columns(conn) == COLUMNS
    index = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'idx_metric_record_enabled'")
    sql = index.fetchone()["sql"]
    assert "UNIQUE" in sql and "metric_name, metric_version" in sql and "status = 'enabled'" in sql


def test_t_store_08b_a_database_at_0001_keeps_its_rows_when_it_reaches_0002(only_0001, tmp_path):
    with closing(sqlite3.connect(tmp_path / "old.db")) as old:
        old.row_factory = sqlite3.Row
        old.execute("PRAGMA foreign_keys = ON")
        apply_migrations(old, only_0001)
        old.execute("INSERT INTO participant (participant_id, consent_ref) VALUES ('P03', 'CONSENT-2026-011')")
        old.execute(
            "INSERT INTO recording (recording_id, participant_id, session_id, take_id, camera_id, sha256, source_path,"
            " width, height) VALUES ('r1', 'P03', 'S01', 'S01-P03-T01', 'camA', 'abc', 'x', 1920, 1080)"
        )
        old.commit()
        before = [tuple(r) for r in old.execute("SELECT * FROM recording")]
        assert apply_migrations(old, MIGRATIONS) == [2]
        assert versions(old) == [1, 2] and columns(old) == COLUMNS
        assert [tuple(r) for r in old.execute("SELECT * FROM recording")] == before
        assert old.execute("SELECT participant_id FROM participant").fetchone()[0] == "P03"
        assert old.execute("SELECT COUNT(*) FROM metric_record").fetchone()[0] == 0
        assert apply_migrations(old, MIGRATIONS) == []  # it runs once


def test_t_store_08c_a_table_that_holds_a_row_stops_the_migration_and_nothing_changes(only_0001, tmp_path):
    with closing(sqlite3.connect(tmp_path / "old.db")) as old:
        old.row_factory = sqlite3.Row
        apply_migrations(old, only_0001)
        old.execute(
            "INSERT INTO metric_record (metric_name, version, intended_use, supported_views)"
            " VALUES ('speed_hips', '1', 'old use', '[]')"
        )
        old.commit()
        with pytest.raises(sqlite3.IntegrityError, match="metric_record_0002_needs_an_empty_table"):
            apply_migrations(old, MIGRATIONS)
        assert versions(old) == [1]
        assert "threshold" in columns(old) and "metric_version" not in columns(old)
        assert old.execute("SELECT intended_use FROM metric_record").fetchone()[0] == "old use"
        leftovers = old.execute("SELECT name FROM sqlite_temp_master").fetchall()
        assert leftovers == []  # the guard's temporary table is gone with the rolled-back transaction


# --- what the database refuses on its own ----------------------------------------------------------------------------
def test_t_store_08d_an_enabled_record_needs_a_signature_and_every_number(conn):
    insert(conn)  # the valid one
    for column in (
        "signed_by",
        "signed_at",
        "gold_reference",
        "human_variability",
        "smallest_useful_change",
        "measurement_error",
        "min_valid_duration_s",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="metric_record_enabled_is_complete"):
            insert(conn, version="2", metric_version="2", **{column: None})


def test_t_store_08e_the_error_must_be_below_the_smallest_useful_change(conn):
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_enabled_is_complete"):
        insert(conn, measurement_error=0.5, smallest_useful_change=0.5)  # equal is refused (G03)
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_enabled_is_complete"):
        insert(conn, measurement_error=0.6, smallest_useful_change=0.5)
    insert(conn, measurement_error=0.4999, smallest_useful_change=0.5)


def test_t_store_08f_a_retired_record_says_who_retired_it_and_the_vocabularies_are_closed(conn):
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_retired_is_signed"):
        insert(conn, status="retired", signed_by=None)
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_retired_is_signed"):
        insert(conn, status="retired", signed_at=None)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        insert(conn, status="signed")
    insert(conn, status="retired")


def test_t_store_08g_parameters_are_a_json_object_and_views_and_sources_are_json_lists(conn):
    for column, bad in (
        ("parameters", "{not json"),
        ("parameters", "[1, 2]"),
        ("supported_views", "{}"),
        ("supported_views", "front"),
        ("data_sources", "{}"),
        ("data_sources", "nothing"),
    ):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            insert(conn, **{column: bad})
    insert(conn, parameters="{}", supported_views="[]", data_sources="[]")


def test_t_store_08h_one_enabled_record_per_metric_version(conn):
    insert(conn)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        insert(conn, version="2")  # a second enabled record of metric speed_hips, metric version 1
    insert(conn, version="2", metric_version="2")  # another metric version
    insert(conn, version="2", metric_name="speed_hands")  # another metric
    insert(conn, version="3", status="retired")  # retired records may be many
    insert(conn, version="4", status="retired")
    insert(conn, **{**DRAFT, "version": "5", "metric_name": "speed_feet"})  # drafts may be many, even of one version
    insert(conn, **{**DRAFT, "version": "6", "metric_name": "speed_feet"})


def test_t_store_08i_a_draft_may_change_and_be_deleted_an_enabled_or_retired_record_may_not(conn):
    insert(conn, **{**DRAFT, "version": "1", "metric_name": "trunk_lean_lr"})
    conn.execute("UPDATE metric_record SET intended_use = 'a new sentence' WHERE metric_name = 'trunk_lean_lr'")
    conn.execute("DELETE FROM metric_record WHERE metric_name = 'trunk_lean_lr'")
    insert(conn)
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_is_immutable"):
        conn.execute("UPDATE metric_record SET measurement_error = 0.1")
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_is_immutable"):
        conn.execute("UPDATE metric_record SET parameters = '{}'")
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_is_immutable"):
        conn.execute("DELETE FROM metric_record")
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_is_immutable"):
        conn.execute("UPDATE metric_record SET status = 'experimental'")  # enabled never goes back
    conn.execute("UPDATE metric_record SET status = 'retired', signed_by = 'cli:H2', signed_at = '2026-12-01'")
    row = conn.execute("SELECT status, signed_by, signed_at, measurement_error FROM metric_record").fetchone()
    assert tuple(row) == ("retired", "cli:H2", "2026-12-01", 0.2)
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_is_immutable"):
        conn.execute("UPDATE metric_record SET status = 'enabled'")  # retired is final
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_is_immutable"):
        conn.execute("DELETE FROM metric_record")


# every column that is not the status or the signature, with a value that the other checks of the table accept
OTHER_VALUE = {
    "metric_name": "'speed_hands'",
    "version": "'9'",
    "metric_version": "'2'",
    "units": "'deg'",
    "intended_use": "'rewritten'",
    "supported_views": "'[\"back\"]'",
    "gold_reference": "'OTHER'",
    "human_variability": "0.9",
    "smallest_useful_change": "0.3",
    "measurement_error": "0.1",
    "min_valid_duration_s": "9.0",
    "parameters": "'{}'",
    "data_sources": '\'[{"dataset_id": "D01", "license": "x"}]\'',
}


@pytest.mark.parametrize("column", sorted(OTHER_VALUE))
def test_t_store_08j_retiring_changes_the_status_and_the_signature_only(conn, column):
    insert(conn)
    with pytest.raises(sqlite3.IntegrityError, match="metric_record_is_immutable"):
        conn.execute(f"UPDATE metric_record SET status = 'retired', {column} = {OTHER_VALUE[column]}")
    row = conn.execute("SELECT status, signed_by FROM metric_record").fetchone()
    assert tuple(row) == ("enabled", "cli:H")  # nothing changed
    conn.execute("UPDATE metric_record SET status = 'retired', signed_by = 'cli:H2', signed_at = '2027-01-01'")
    assert conn.execute("SELECT status FROM metric_record").fetchone()[0] == "retired"  # the legal retirement
