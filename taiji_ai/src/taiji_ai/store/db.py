"""SQLite access with numbered SQL migrations (``migrations/NNNN_name.sql``)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_MIGRATION_RE = re.compile(r"^(\d{4})_[\w-]+\.sql$")


def connect(db_path: str | Path, migrations_dir: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    apply_migrations(conn, Path(migrations_dir))
    return conn


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[int]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
        " applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))"
    )
    done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    applied: list[int] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        m = _MIGRATION_RE.match(path.name)
        if not m:
            continue
        version = int(m.group(1))
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        name = path.name.replace("'", "''")
        script = f"BEGIN;\n{sql}\n;INSERT INTO schema_migrations(version, name) VALUES ({version}, '{name}');\nCOMMIT;"
        try:  # one transaction per migration: all of it or nothing
            conn.executescript(script)
        except Exception:
            conn.rollback()
            raise
        applied.append(version)
    return applied
