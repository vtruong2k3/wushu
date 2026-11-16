"""Command line of the project: ``taiji <command>`` (P2.08, P2.02; later tasks add ``proxy`` and ``sync``).

``taiji participant add | set | show`` registers a pseudonym with the consent answers of a signed form (see
``Docs/consent_form.md``) and shows or changes them. ``taiji ingest <file> --participant ... --take ... --camera ...``
copies one phone video into the data folder (``taiji_ai.io.ingest``). The result of a command goes to standard output,
errors to standard error. Exit codes: 0 ok, 1 refused (the message says why), 2 usage error (argparse). Only IDs are
printed or logged: never a path and never free text.

Every consent answer is a required ``yes`` or ``no``: there is no default for a consent question. ``--actor`` is a role
code (``cli:O``, ``cli:H1`` ...), never a person's name; it goes to the audit log.
"""

from __future__ import annotations

import argparse
import sys
from typing import TextIO

from taiji_ai.config import Settings, get_settings
from taiji_ai.io.ingest import IngestError, ingest_recording
from taiji_ai.logs import configure_logging
from taiji_ai.schemas.recording import CAMERA_ROLES
from taiji_ai.store.db import connect
from taiji_ai.store.participants import (
    UNSET,
    Participant,
    ParticipantError,
    get_participant,
    register_participant,
    require_participant,
    update_consent,
)

YES_NO = ("yes", "no")


def _write(stream: TextIO, text: str) -> None:
    stream.write(text + "\n")


def _flag(text: str) -> bool:
    return text == "yes"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taiji", description="Taiji AI command line")
    commands = parser.add_subparsers(dest="command", required=True)

    participant = commands.add_parser("participant", help="register, change and show consent answers")
    actions = participant.add_subparsers(dest="action", required=True)

    add = actions.add_parser("add", help="register a pseudonym from a signed consent form")
    add.add_argument("--id", required=True, help="pseudonym, for example P03")
    add.add_argument("--consent-ref", required=True, help="code on the signed form, for example CONSENT-2026-011")
    add.add_argument("--analysis", required=True, choices=YES_NO, help="box (a); must be yes to take part")
    add.add_argument("--train", required=True, choices=YES_NO, help="box (b)")
    add.add_argument("--share", required=True, choices=YES_NO, help="box (c)")
    add.add_argument("--retention", help="keep until this date (YYYY-MM-DD); a warning if left out")
    add.add_argument("--actor", required=True, help="role code, for example cli:O")

    change = actions.add_parser("set", help="change box (b), box (c) or the retention date")
    change.add_argument("--id", required=True)
    change.add_argument("--train", choices=YES_NO)
    change.add_argument("--share", choices=YES_NO)
    retention = change.add_mutually_exclusive_group()
    retention.add_argument("--retention", help="new date (YYYY-MM-DD)")
    retention.add_argument("--clear-retention", action="store_true", help="remove the date (a warning is logged)")
    change.add_argument("--actor", required=True, help="role code, for example cli:O")

    show = actions.add_parser("show", help="show the consent answers of a pseudonym")
    show.add_argument("--id", required=True)

    ingest = commands.add_parser("ingest", help="copy one phone video into the data folder and record it")
    ingest.add_argument("file", help="the video file (.mp4, .mov or .mkv); it is only read, never changed")
    ingest.add_argument("--participant", required=True, help="registered pseudonym, for example P03")
    ingest.add_argument("--session", required=True, help="session, for example S01")
    ingest.add_argument("--take", required=True, help="take, for example S01-P03-T02 (the same for both cameras)")
    ingest.add_argument("--camera", required=True, help="camera, for example camA")
    ingest.add_argument("--role", choices=CAMERA_ROLES, help="camera role from the capture sheet")
    ingest.add_argument("--camera-height-m", type=float, help="camera height [m] (needs --role)")
    ingest.add_argument("--camera-distance-m", type=float, help="distance to the centre of the area [m] (needs --role)")
    ingest.add_argument("--fps-setting", type=float, help="frame rate set in the camera app [Hz] (needs --role)")
    return parser


def _describe(p: Participant) -> list[str]:
    yes_no = {True: "yes", False: "no"}
    return [
        f"participant_id: {p.participant_id}",
        f"consent_ref: {p.consent_ref}",
        f"consent_analysis: {yes_no[p.consent_analysis]}",
        f"consent_train: {yes_no[p.consent_train]}",
        f"consent_share: {yes_no[p.consent_share]}",
        f"retention_until: {p.retention_until.isoformat() if p.retention_until else '-'}",
        f"created_at: {p.created_at}",
    ]


def _participant(args: argparse.Namespace, settings: Settings) -> int:
    conn = connect(settings.db_path, settings.migrations_dir)
    try:
        if args.action == "add":
            p = register_participant(
                conn,
                args.id,
                args.consent_ref,
                analysis=_flag(args.analysis),
                train=_flag(args.train),
                share=_flag(args.share),
                retention_until=args.retention,
                actor=args.actor,
            )
            _write(sys.stdout, f"registered {p.participant_id} (consent {p.consent_ref})")
        elif args.action == "set":
            before = get_participant(conn, args.id)
            p = update_consent(
                conn,
                args.id,
                train=UNSET if args.train is None else _flag(args.train),
                share=UNSET if args.share is None else _flag(args.share),
                retention_until=None if args.clear_retention else (UNSET if args.retention is None else args.retention),
                actor=args.actor,
            )
            _write(sys.stdout, f"no change for {p.participant_id}" if p == before else f"updated {p.participant_id}")
        else:
            for line in _describe(require_participant(conn, args.id)):
                _write(sys.stdout, line)
        return 0
    finally:
        conn.close()


def _ingest(args: argparse.Namespace, settings: Settings) -> int:
    capture = None
    if args.role is not None:
        capture = {
            "camera_role": args.role,
            "height_m": args.camera_height_m,
            "distance_m": args.camera_distance_m,
            "fps_setting": args.fps_setting,
        }
    meta = {  # validated by ingest_recording (IngestMeta); a bad value is a refusal, exit code 1
        "participant_id": args.participant,
        "session_id": args.session,
        "take_id": args.take,
        "camera_id": args.camera,
        "capture": capture,
    }
    result = ingest_recording(args.file, meta, settings)
    m = result.manifest
    if result.created:
        _write(sys.stdout, f"ingested {m.recording_id} (take {m.take_id}, {m.camera_id})")
    else:
        _write(sys.stdout, f"already ingested {m.recording_id}")
    return 0


def main(argv: list[str] | None = None, *, settings: Settings | None = None) -> int:
    """Run one command; returns the exit code (argparse exits with 2 itself on a usage error)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest" and args.role is None:
        given = [n for n in ("camera_height_m", "camera_distance_m", "fps_setting") if getattr(args, n) is not None]
        if given:
            parser.error("--camera-height-m, --camera-distance-m and --fps-setting need --role")
    settings = settings or get_settings()
    configure_logging(settings)
    try:
        return _ingest(args, settings) if args.command == "ingest" else _participant(args, settings)
    except (ParticipantError, IngestError) as exc:
        _write(sys.stderr, f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
