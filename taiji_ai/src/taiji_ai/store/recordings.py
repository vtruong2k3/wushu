"""Queries and the insert of the ``recording`` table (P2.02).

The table has a unique key on ``sha256`` only. A take is found by ``take_id`` and ``camera_id`` (P2.06), so ingest also
refuses a second file for the same pair; the database itself does not (migration 0001 has a plain index).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping


def find_by_sha(conn: sqlite3.Connection, sha256: str) -> sqlite3.Row | None:
    """The row of the recording with this file hash, if any."""
    return conn.execute("SELECT * FROM recording WHERE sha256 = ?", (sha256,)).fetchone()


def find_by_take_camera(conn: sqlite3.Connection, take_id: str, camera_id: str) -> sqlite3.Row | None:
    """The row of the recording of this camera in this take, if any."""
    return conn.execute("SELECT * FROM recording WHERE take_id = ? AND camera_id = ?", (take_id, camera_id)).fetchone()


def insert_recording(conn: sqlite3.Connection, row: Mapping[str, object]) -> None:
    """Insert one row; the keys are the column names (``RecordingManifest.to_db_row``). The caller owns the transaction.

    The column names come from the manifest code, never from user input.
    """
    columns = list(row)
    marks = ", ".join("?" for _ in columns)
    conn.execute(f"INSERT INTO recording({', '.join(columns)}) VALUES ({marks})", [row[c] for c in columns])
