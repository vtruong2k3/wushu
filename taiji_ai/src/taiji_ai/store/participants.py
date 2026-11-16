"""Participant registry: pseudonym, consent reference and the three consent answers (P2.08).

A recording enters the system only with a participant pseudonym and a consent reference (AGENTS.md section 9.5). The
``participant`` table cannot enforce that by itself: ``consent_analysis`` accepts 0 and every consent column has a
default. So the rules live here:

* every consent answer (``analysis``, ``train``, ``share``) is a keyword argument with **no default** and must be a real
  boolean; analysis consent must be true, because without box (a) of the consent form (``Docs/consent_form.md``) no
  recording is accepted;
* ``retention_until`` is an ISO date (``YYYY-MM-DD``) that is not in the past, or none (a warning is logged);
* ``actor`` is a role code (``cli:A``, ``cli:B``, ``cli:O``, ``cli:H``, up to two digits), never a person's name;
* every write is one transaction together with its ``audit_log`` row, whose ``before`` and ``after`` hold only the
  consent fields as JSON (IDs, flags and a date: no name, no free text);
* ``update_consent`` never changes ``analysis`` (withdrawing it means deleting the person's data, task P8.14) or the
  consent reference.

Logging follows AGENTS.md section 6: the pseudonym and the consent reference only.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from taiji_ai.schemas._base import CONSENT_RE, PARTICIPANT_RE

log = logging.getLogger(__name__)

_ACTOR_RE = re.compile(r"^cli:(?:A|B|O|H)\d{0,2}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ParticipantError(ValueError):
    """A registration or update is refused; the message says why and never echoes free text."""


class _Unset:
    """Marks an argument that was not given (``None`` is a value for ``retention_until``)."""

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


@dataclass(frozen=True)
class Participant:
    participant_id: str
    consent_ref: str
    consent_analysis: bool
    consent_train: bool
    consent_share: bool
    retention_until: date | None
    created_at: str


def _check_id(participant_id: object) -> str:
    if not isinstance(participant_id, str) or not re.fullmatch(PARTICIPANT_RE, participant_id):
        raise ParticipantError("participant_id must be a pseudonym such as P03 (letter P and two or more digits)")
    return participant_id


def _check_consent_ref(consent_ref: object) -> str:
    if not isinstance(consent_ref, str) or not re.fullmatch(CONSENT_RE, consent_ref):
        raise ParticipantError("consent_ref must look like CONSENT-2026-011 (the code written on the signed form)")
    return consent_ref


def _check_flag(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ParticipantError(f"{name} must be True or False, got {type(value).__name__}")
    return value


def _check_actor(actor: object) -> str:
    if not isinstance(actor, str) or not _ACTOR_RE.fullmatch(actor):
        raise ParticipantError("actor must be a role code such as cli:O (A, B, O or H, up to two digits), never a name")
    return actor


def _check_retention(value: object, today: date) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ParticipantError("retention_until must be a date (YYYY-MM-DD), not a date and time")
    if isinstance(value, date):
        parsed = value
    elif isinstance(value, str) and _ISO_DATE_RE.fullmatch(value):
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ParticipantError("retention_until is not a real calendar date (YYYY-MM-DD)") from exc
    else:
        raise ParticipantError("retention_until must be an ISO date (YYYY-MM-DD) or None")
    if parsed < today:
        raise ParticipantError(
            f"retention_until {parsed.isoformat()} is in the past (today is {today.isoformat()}): "
            "the data would be due for deletion at once"
        )
    return parsed


def _from_row(row: sqlite3.Row) -> Participant:
    retention = row["retention_until"]
    return Participant(
        participant_id=row["participant_id"],
        consent_ref=row["consent_ref"],
        consent_analysis=bool(row["consent_analysis"]),
        consent_train=bool(row["consent_train"]),
        consent_share=bool(row["consent_share"]),
        retention_until=date.fromisoformat(retention) if retention is not None else None,
        created_at=row["created_at"],
    )


def _state(p: Participant) -> dict[str, object]:
    """The consent fields as stored in the audit log (flags as 0 or 1, the date as ISO text)."""
    return {
        "consent_ref": p.consent_ref,
        "consent_analysis": int(p.consent_analysis),
        "consent_train": int(p.consent_train),
        "consent_share": int(p.consent_share),
        "retention_until": p.retention_until.isoformat() if p.retention_until is not None else None,
    }


def _audit(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    entity: str,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> None:
    conn.execute(
        "INSERT INTO audit_log(actor, action, entity, before, after) VALUES (?, ?, ?, ?, ?)",
        (
            actor,
            action,
            entity,
            json.dumps(before, sort_keys=True) if before is not None else None,
            json.dumps(after, sort_keys=True) if after is not None else None,
        ),
    )


def get_participant(conn: sqlite3.Connection, participant_id: str) -> Participant | None:
    """The stored participant, or ``None`` if the pseudonym is not registered."""
    row = conn.execute("SELECT * FROM participant WHERE participant_id = ?", (participant_id,)).fetchone()
    return _from_row(row) if row is not None else None


def require_participant(conn: sqlite3.Connection, participant_id: str) -> Participant:
    """The stored participant. The id is checked against the pseudonym pattern first, so a message never repeats text
    that is not a pseudonym (BUG-0050).

    Raises:
        ParticipantError: the id is not a pseudonym, or it is not registered.
    """
    pid = _check_id(participant_id)
    found = get_participant(conn, pid)
    if found is None:
        raise ParticipantError(f"participant {pid} is not registered")
    return found


def register_participant(
    conn: sqlite3.Connection,
    participant_id: str,
    consent_ref: str,
    *,
    analysis: bool,
    train: bool,
    share: bool,
    retention_until: date | str | None = None,
    actor: str,
    today: date | None = None,
) -> Participant:
    """Register a pseudonym with the consent answers of a signed form (one transaction with its audit row).

    Raises:
        ParticipantError: an input is invalid, analysis consent is missing, or the pseudonym is already registered.
    """
    pid = _check_id(participant_id)
    ref = _check_consent_ref(consent_ref)
    analysis = _check_flag("analysis", analysis)
    train = _check_flag("train", train)
    share = _check_flag("share", share)
    if not analysis:
        raise ParticipantError(
            "analysis consent is required to take part: without box (a) of the consent form (Docs/consent_form.md) "
            "no recording is accepted"
        )
    retention = _check_retention(retention_until, today or date.today())
    who = _check_actor(actor)

    try:
        with conn:
            if conn.execute("SELECT 1 FROM participant WHERE participant_id = ?", (pid,)).fetchone() is not None:
                raise ParticipantError(
                    f"participant {pid} is already registered; use update_consent to change train, share or retention"
                )
            conn.execute(
                "INSERT INTO participant(participant_id, consent_ref, consent_analysis, consent_train, consent_share, "
                "retention_until) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, ref, int(analysis), int(train), int(share), retention.isoformat() if retention else None),
            )
            created = get_participant(conn, pid)
            assert created is not None  # just inserted in this transaction
            _audit(conn, who, "participant.register", f"participant:{pid}", None, _state(created))
    except sqlite3.IntegrityError as exc:
        if get_participant(conn, pid) is not None:  # another process registered the same pseudonym in between
            raise ParticipantError(f"participant {pid} is already registered") from exc
        raise

    log.info("participant %s registered (consent %s)", pid, ref)
    if retention is None:
        log.warning("participant %s has no retention date; set one before the first recording", pid)
    return created


def update_consent(
    conn: sqlite3.Connection,
    participant_id: str,
    *,
    train: bool | _Unset = UNSET,
    share: bool | _Unset = UNSET,
    retention_until: date | str | None | _Unset = UNSET,
    actor: str,
    today: date | None = None,
) -> Participant:
    """Change ``train``, ``share`` and/or ``retention_until``; only the fields that are given change.

    ``retention_until=None`` clears the date (a warning is logged). Giving the current values is a no-op without an
    audit row. Analysis consent and the consent reference cannot be changed here.

    Raises:
        ParticipantError: nothing is given, an input is invalid, or the pseudonym is not registered.
    """
    pid = _check_id(participant_id)
    who = _check_actor(actor)
    if isinstance(train, _Unset) and isinstance(share, _Unset) and isinstance(retention_until, _Unset):
        raise ParticipantError("nothing to change: give train, share or retention_until")
    new_train = train if isinstance(train, _Unset) else _check_flag("train", train)
    new_share = share if isinstance(share, _Unset) else _check_flag("share", share)
    new_retention: date | None | _Unset = (
        retention_until
        if isinstance(retention_until, _Unset)
        else _check_retention(retention_until, today or date.today())
    )

    with conn:
        current = require_participant(conn, pid)
        updated = Participant(
            participant_id=pid,
            consent_ref=current.consent_ref,
            consent_analysis=current.consent_analysis,
            consent_train=current.consent_train if isinstance(new_train, _Unset) else new_train,
            consent_share=current.consent_share if isinstance(new_share, _Unset) else new_share,
            retention_until=current.retention_until if isinstance(new_retention, _Unset) else new_retention,
            created_at=current.created_at,
        )
        if updated == current:
            return current
        conn.execute(
            "UPDATE participant SET consent_train = ?, consent_share = ?, retention_until = ? WHERE participant_id = ?",
            (
                int(updated.consent_train),
                int(updated.consent_share),
                updated.retention_until.isoformat() if updated.retention_until else None,
                pid,
            ),
        )
        _audit(conn, who, "participant.update_consent", f"participant:{pid}", _state(current), _state(updated))

    log.info("participant %s consent updated", pid)
    if updated.retention_until is None and current.retention_until is not None:
        log.warning("participant %s has no retention date any more; set one before the next recording", pid)
    return updated
