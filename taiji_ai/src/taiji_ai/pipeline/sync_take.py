"""Synchronize the two camera recordings of a take (W2 step 5, P2.06).

Combines the audio cross-correlation offset/drift estimation (P2.04) and flash
validation (P2.05), applies the usability decision rule, writes ``data/takes/<take_id>/sync.json``
atomically, and manages the ``sync`` SQLite table row.
"""

from __future__ import annotations

import logging
import re
from contextlib import closing
from datetime import datetime

from taiji_ai.config import Settings, get_settings
from taiji_ai.io.audio_sync import AudioError, SyncError, estimate_sync
from taiji_ai.io.flash import FlashError, validate_sync
from taiji_ai.io.ingest import _tool_versions
from taiji_ai.io.sync_rule import decide_usability
from taiji_ai.schemas._base import TAKE_RE, ToolVersions, write_manifest
from taiji_ai.schemas.sync import SyncManifest
from taiji_ai.store.db import connect
from taiji_ai.store.recordings import find_by_take
from taiji_ai.store.sync import delete_sync, upsert_sync

log = logging.getLogger(__name__)


class SyncTakeError(Exception):
    """Refusal or failure to synchronize a take."""


def sync_take(take_id: str, *, settings: Settings | None = None) -> SyncManifest:
    """Synchronize a take across its two cameras.

    Args:
        take_id: Valid take identifier (e.g. ``S01-P03-T01``).
        settings: Optional configuration settings (defaults to global settings).

    Returns:
        The validated and persisted :class:`SyncManifest`.

    Raises:
        SyncTakeError: if the take is invalid, missing recordings, or estimation fails.
    """
    if not re.fullmatch(TAKE_RE, take_id):
        raise SyncTakeError(f"take_id {take_id!r} is invalid: must match {TAKE_RE}")

    settings = settings or get_settings()

    with closing(connect(settings.db_path, settings.migrations_dir)) as conn:
        recs = find_by_take(conn, take_id)
        if not recs:
            raise SyncTakeError(f"take {take_id}: no recordings found")
        if len(recs) != 2:
            raise SyncTakeError(f"take {take_id}: found {len(recs)} recordings, exactly two required")

        # Sort by camera_id so Camera A is first (cam_a < cam_b)
        recs_sorted = sorted(recs, key=lambda r: r["camera_id"])
        rec_a, rec_b = recs_sorted[0], recs_sorted[1]
        if rec_a["camera_id"] == rec_b["camera_id"]:
            raise SyncTakeError(f"take {take_id}: duplicate camera_id {rec_a['camera_id']}")

        dir_a = settings.data_dir / "recordings" / rec_a["recording_id"]
        dir_b = settings.data_dir / "recordings" / rec_b["recording_id"]

        if not dir_a.is_dir():
            raise SyncTakeError(f"recording directory not found for {rec_a['recording_id']}")
        if not dir_b.is_dir():
            raise SyncTakeError(f"recording directory not found for {rec_b['recording_id']}")

        try:
            audio_sync = estimate_sync(dir_a, dir_b)
        except (SyncError, AudioError) as exc:
            raise SyncTakeError(f"audio sync failed for take {take_id}: {exc}") from exc

        try:
            validation = validate_sync(audio_sync, dir_a, dir_b)
        except FlashError as exc:
            raise SyncTakeError(f"flash validation failed for take {take_id}: {exc}") from exc

        usable_for_metrics, usable_reason = decide_usability(audio_sync, validation)

        tools_dict = _tool_versions()
        tools = ToolVersions(
            ffprobe=tools_dict["ffprobe"],
            pyav=tools_dict["pyav"],
            taiji_ai=tools_dict["taiji_ai"],
        )

        manifest = SyncManifest(
            schema_version="sync/1",
            take_id=take_id,
            cam_a=audio_sync.cam_a,
            cam_b=audio_sync.cam_b,
            recording_id_a=audio_sync.recording_id_a,
            recording_id_b=audio_sync.recording_id_b,
            method="audio_xcorr/1",
            params=audio_sync.params,
            start=audio_sync.start,
            end=audio_sync.end,
            status=audio_sync.status,
            not_found_reason=audio_sync.not_found_reason,
            offset_s=audio_sync.offset_s,
            drift=audio_sync.drift,
            t_ref_s=audio_sync.t_ref_s,
            validation=validation,
            usable_for_metrics=usable_for_metrics,
            usable_reason=usable_reason,
            created_at=datetime.now().astimezone(),
            tools=tools,
        )

        manifest_path = settings.data_dir / "takes" / take_id / "sync.json"
        write_manifest(manifest_path, manifest)

        # The row exists only for a usable take (DEC-0035, BUG-0065): the table has no usable column, so a row of a take
        # that the rule refused would look like a validated mapping. sync.json keeps the full result of every take.
        with conn:
            db_row = manifest.to_db_row() if manifest.usable_for_metrics else None
            if db_row is not None:
                upsert_sync(conn, db_row)
            else:
                delete_sync(conn, take_id, manifest.cam_a, manifest.cam_b)

        log.info(
            "synchronized take %s (%s <-> %s): status=%s, usable=%s (%s)",
            take_id,
            manifest.cam_a,
            manifest.cam_b,
            manifest.status,
            manifest.usable_for_metrics,
            manifest.usable_reason,
        )
        return manifest
