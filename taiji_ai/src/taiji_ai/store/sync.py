"""Queries and updates of the ``sync`` table (P2.06).

A row exists only when ``usable_for_metrics`` is true (DEC-0035, BUG-0065; it amends P2.01 Q4 and DEC-0025 item 7).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping


def upsert_sync(conn: sqlite3.Connection, row: Mapping[str, object]) -> None:
    """Insert or update a sync row for (take_id, cam_a, cam_b). The caller owns the transaction.

    The column names come from the code, never from user input.
    """
    columns = list(row)
    marks = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in ("take_id", "cam_a", "cam_b"))
    sql = (
        f"INSERT INTO sync({', '.join(columns)}) VALUES ({marks}) "
        f"ON CONFLICT(take_id, cam_a, cam_b) DO UPDATE SET {updates}"
    )
    conn.execute(sql, [row[c] for c in columns])


def find_sync(conn: sqlite3.Connection, take_id: str, cam_a: str, cam_b: str) -> sqlite3.Row | None:
    """The row of the sync record for this take and camera pair, if any."""
    return conn.execute(
        "SELECT * FROM sync WHERE take_id = ? AND cam_a = ? AND cam_b = ?",
        (take_id, cam_a, cam_b),
    ).fetchone()


def delete_sync(conn: sqlite3.Connection, take_id: str, cam_a: str, cam_b: str) -> None:
    """Delete the sync record for this take and camera pair, if any. The caller owns the transaction."""
    conn.execute(
        "DELETE FROM sync WHERE take_id = ? AND cam_a = ? AND cam_b = ?",
        (take_id, cam_a, cam_b),
    )
