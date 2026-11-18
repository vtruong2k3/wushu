"""Store of the signed metric records (P5.09, v3 section 8.2): the only way a record gets into, or changes in, the
table ``metric_record`` (migration 0002).

A result becomes conclusive only through an ``enabled`` record (``taiji_ai.metrics.records.apply_record``), so the
writes are strict. The database already refuses a record that is enabled without a signature or every number, two
enabled records of one metric version, and any change to an enabled or retired record (the checks and triggers of the
migration); the store adds what SQL cannot say, with messages that tell the person why:

* the record must pass ``check_record``: the metric exists in this code, with these units and this version, and the
  record binds only keys the metric echoes;
* ``actor`` is a role code (``cli:A``, ``cli:B``, ``cli:O``, ``cli:H``, up to two digits), never a name; **a signed
  record is written by the person who signs it** (``actor == signed_by``, a coach: AGENTS.md section 5.12), so neither
  an agent nor the coordinator can sign for a coach; a draft may be written by anyone;
* ``signed_at`` is not in the future;
* an enabled or retired record never changes: new numbers are a new ``version``; a draft (``experimental``) may be
  replaced, also by the signed record that it becomes; an enabled record is retired with ``retire_record`` (status and
  signature only, by a coach), never saved as retired;
* a second enabled record of one metric version is refused, naming both versions: retire the first one first;
* every write is one transaction with its ``audit_log`` row. The audit state holds the fields of the record as JSON
  with ``intended_use`` replaced by its SHA-256, so the coach's sentence is neither in the audit log nor in a message
  or a log line (AGENTS.md section 6: IDs only).

``current_record`` is what the pipeline reads: the enabled record of a metric version, else the one with the highest
version (a draft or a retired record, which ``apply_record`` turns into ``record_experimental`` or ``retired``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import date
from typing import Any, Final

from pydantic import ValidationError

from taiji_ai.metrics.records import MetricRecordError, check_record
from taiji_ai.schemas._base import format_validation_error
from taiji_ai.schemas.metric import NAME_RE, VERSION_RE
from taiji_ai.schemas.metric_record import SIGNER_RE, MetricRecord

log = logging.getLogger(__name__)

_ACTOR_RE: Final = re.compile(r"^cli:(?:A|B|O|H)\d{0,2}$")
_COLUMNS: Final = (
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
)
_SELECT: Final = "SELECT " + ", ".join(_COLUMNS) + " FROM metric_record"


def _check_actor(actor: object) -> str:
    if not isinstance(actor, str) or not _ACTOR_RE.fullmatch(actor):
        raise MetricRecordError(
            "actor must be a role code such as cli:H (A, B, O or H, up to two digits), never a name"
        )
    return actor


def _check_name(value: object, field: str, pattern: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise MetricRecordError(f"{field} does not have the form of a {field.replace('_', ' ')} (pattern {pattern})")
    return value


def _check_key(metric_name: object, version: object) -> tuple[str, str]:
    return _check_name(metric_name, "metric_name", NAME_RE), _check_name(version, "version", VERSION_RE)


def _record_of(row: Any) -> MetricRecord:
    data = dict(zip(_COLUMNS, tuple(row), strict=True))
    for field in ("supported_views", "parameters", "data_sources"):
        data[field] = json.loads(data[field])
    try:
        return MetricRecord.model_validate(data)
    except ValidationError as exc:
        raise MetricRecordError(
            f"metric_record {data['metric_name']} version {data['version']} is invalid"
            f" ({format_validation_error('MetricRecord', exc)})"
        ) from exc


def _state(record: MetricRecord) -> dict[str, object]:
    """The record as stored in the audit log: its JSON fields, the sentence as its SHA-256."""
    state: dict[str, object] = record.model_dump(mode="json")
    sentence = str(state.pop("intended_use"))
    state["intended_use_sha256"] = hashlib.sha256(sentence.encode("utf-8")).hexdigest()
    return state


def _audit(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    record: MetricRecord,
    before: dict[str, object] | None,
    after: dict[str, object],
) -> None:
    conn.execute(
        "INSERT INTO audit_log(actor, action, entity, before, after) VALUES (?, ?, ?, ?, ?)",
        (
            actor,
            action,
            f"metric_record:{record.metric_name}:{record.version}",
            json.dumps(before, sort_keys=True) if before is not None else None,
            json.dumps(after, sort_keys=True),
        ),
    )


def _row(conn: sqlite3.Connection, metric_name: str, version: str) -> Any:
    return conn.execute(_SELECT + " WHERE metric_name = ? AND version = ?", (metric_name, version)).fetchone()


def load_record(conn: sqlite3.Connection, metric_name: str, version: str) -> MetricRecord | None:
    """The record ``(metric_name, version)``, or ``None``.

    Raises:
        MetricRecordError: the key has the wrong form, or the stored row is not a valid record (named by its key).
    """
    name, ver = _check_key(metric_name, version)
    row = _row(conn, name, ver)
    return None if row is None else _record_of(row)


def current_record(conn: sqlite3.Connection, metric_name: str, metric_version: str) -> MetricRecord | None:
    """The record the pipeline uses for a metric version: the enabled one, else the one with the highest version."""
    name = _check_name(metric_name, "metric_name", NAME_RE)
    mv = _check_name(metric_version, "metric_version", VERSION_RE)
    row = conn.execute(
        _SELECT + " WHERE metric_name = ? AND metric_version = ?"
        " ORDER BY (status = 'enabled') DESC, CAST(version AS INTEGER) DESC LIMIT 1",
        (name, mv),
    ).fetchone()
    return None if row is None else _record_of(row)


def save_record(
    conn: sqlite3.Connection, record: MetricRecord, *, actor: str, today: date | None = None
) -> MetricRecord:
    """Write a record (one transaction with its audit row) and return it as stored.

    A new ``(metric_name, version)`` is inserted; an existing draft is replaced; an enabled or retired record is
    never changed. See the module docstring for every rule.

    Raises:
        MetricRecordError: a rule is broken; the message says which and carries no free text.
    """
    who = _check_actor(actor)
    check_record(record)
    if record.status == "retired":
        raise MetricRecordError("a record is retired with retire_record, not saved as retired")
    if record.signed_by is not None and who != record.signed_by:
        raise MetricRecordError(
            f"signed_by is {record.signed_by} but the actor is {who}: a signed record is written by the coach who "
            "signs it (AGENTS.md 5.12)"
        )
    if record.signed_at is not None and record.signed_at > (today or date.today()):
        raise MetricRecordError(f"signed_at {record.signed_at.isoformat()} is in the future")
    name, version = record.metric_name, record.version
    values = (
        record.metric_version,
        record.units,
        record.status,
        record.intended_use,
        json.dumps(record.supported_views),
        record.gold_reference,
        record.human_variability,
        record.smallest_useful_change,
        record.measurement_error,
        record.min_valid_duration_s,
        json.dumps(record.parameters, sort_keys=True, allow_nan=False),
        json.dumps([s.model_dump() for s in record.data_sources], sort_keys=True),
        record.signed_by,
        record.signed_at.isoformat() if record.signed_at is not None else None,
    )
    try:
        with conn:
            existing = _row(conn, name, version)
            before: dict[str, object] | None = None
            if existing is not None:
                old = _record_of(existing)
                if old.status != "experimental":
                    raise MetricRecordError(
                        f"metric_record {name} version {version} is {old.status} and never changes: "
                        "new numbers are a new version"
                    )
                before = _state(old)
            if record.status == "enabled":
                clash = conn.execute(
                    "SELECT version FROM metric_record WHERE metric_name = ? AND metric_version = ? AND"
                    " status = 'enabled' AND version <> ?",
                    (name, record.metric_version, version),
                ).fetchone()
                if clash is not None:
                    raise MetricRecordError(
                        f"metric_record {name}: version {clash[0]} is already enabled for metric version "
                        f"{record.metric_version}; retire it before enabling version {version}"
                    )
            if existing is None:
                conn.execute(
                    f"INSERT INTO metric_record ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                    (name, version, *values),
                )
            else:
                assignments = ", ".join(f"{column} = ?" for column in _COLUMNS[2:])
                conn.execute(
                    f"UPDATE metric_record SET {assignments} WHERE metric_name = ? AND version = ?",
                    (*values, name, version),
                )
            _audit(conn, who, "metric_record.save", record, before, _state(record))
    except sqlite3.IntegrityError as exc:
        raise MetricRecordError(f"metric_record {name} version {version} was refused by the database: {exc}") from exc
    saved = load_record(conn, name, version)
    if saved is None:  # the transaction committed this row a moment ago
        raise MetricRecordError(f"metric_record {name} version {version} is missing after it was saved")
    log.info("metric_record %s version %s saved (%s)", name, version, saved.status)
    return saved


def retire_record(
    conn: sqlite3.Connection,
    metric_name: str,
    version: str,
    *,
    signed_by: str,
    actor: str,
    today: date | None = None,
) -> MetricRecord:
    """Retire an enabled record: its status becomes ``retired`` and its signature the retiring coach's, today's date.

    Nothing else changes (the first signature stays in the audit row). Raises ``MetricRecordError`` when the record
    does not exist or is not enabled, when ``signed_by`` is not a coach's role code or is not the actor.
    """
    name, ver = _check_key(metric_name, version)
    who = _check_actor(actor)
    if not isinstance(signed_by, str) or not re.fullmatch(SIGNER_RE, signed_by):
        raise MetricRecordError(
            "signed_by must be a coach's role code such as cli:H (H, up to two digits), never a name"
        )
    if who != signed_by:
        raise MetricRecordError(
            f"signed_by is {signed_by} but the actor is {who}: a record is retired by the coach who signs it"
        )
    day = (today or date.today()).isoformat()
    with conn:
        row = _row(conn, name, ver)
        if row is None:
            raise MetricRecordError(f"no record {name} version {ver}")
        old = _record_of(row)
        if old.status != "enabled":
            raise MetricRecordError(
                f"metric_record {name} version {ver} is {old.status}, not enabled: only an enabled record is retired"
            )
        conn.execute(
            "UPDATE metric_record SET status = 'retired', signed_by = ?, signed_at = ?"
            " WHERE metric_name = ? AND version = ?",
            (signed_by, day, name, ver),
        )
        retired = _record_of(_row(conn, name, ver))
        _audit(conn, who, "metric_record.retire", retired, _state(old), _state(retired))
    log.info("metric_record %s version %s retired", name, ver)
    return retired
