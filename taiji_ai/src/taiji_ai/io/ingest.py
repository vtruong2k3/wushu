"""Ingest one phone video into the system (W1 steps 1-4 and 6; the proxy is P2.03).

``ingest_recording(path, meta, settings)`` copies the video into ``data/recordings/<recording_id>/`` and records it::

    source.<ext>      the stored copy, read-only, with the SHA-256 of the original
    pts.parquet       frame_index, pts (integer ticks), t_sec; schema metadata time_base and start_pts
    recording.json    the manifest (``recording/1``), written last

Order of operations (nothing half-done may be left behind):

1. validate the meta (``IngestMeta``) and the source (extension, a regular file, not empty, size limit);
2. hash the source; the same hash with the same IDs returns the existing record (``created = False``), with other IDs
   it is refused; a second file for the same ``take_id`` and ``camera_id`` is refused;
3. the participant must exist with analysis consent and a valid consent reference (AGENTS.md section 9.5);
4. probe and scan the source **in place**: no video stream, unreadable, no frames, or longer than the limit: refused
   before anything is written;
5. in ``recordings/.staging-<id>/``: copy, hash the copy against the hash of step 2, write ``pts.parquet`` and then
   ``recording.json``, make the copy read-only, rename the folder to ``recordings/<id>/`` (one ``os.replace``);
6. insert the row in one transaction. If that fails the folder is moved to ``recordings/.orphan-<id>/``: a folder
   without a row is the only leftover that can exist, never a row without its folder.

The staging folder is removed on any failure. The original file is only read. Messages and log lines hold IDs only,
never the path or the name of the file (AGENTS.md section 6): errors of ffprobe and PyAV carry the path, so they are
replaced by messages of our own.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib import metadata
from pathlib import Path

import av
import numpy as np
import pyarrow as pa

from taiji_ai.config import Settings, get_settings
from taiji_ai.io.frames import VFR_RULE, PtsScan, VfrVerdict, scan_pts_ticks, vfr_verdict
from taiji_ai.io.probe import NoVideoStreamError, ProbeError, VideoMeta, probe_video
from taiji_ai.io.proxy import ProxyError, make_proxy
from taiji_ai.schemas._base import CONSENT_RE, ManifestError, parse_manifest, read_manifest, write_manifest
from taiji_ai.schemas.recording import IngestMeta, ProxyManifest, RecordingManifest
from taiji_ai.store.artifacts import atomic_write_parquet, sha256_file
from taiji_ai.store.db import connect
from taiji_ai.store.participants import ParticipantError, require_participant
from taiji_ai.store.recordings import find_by_sha, find_by_take_camera, insert_recording

log = logging.getLogger(__name__)

EXTENSIONS = (".mkv", ".mov", ".mp4")


class IngestError(Exception):
    """An ingest is refused or failed; the message says why and never holds the path or the name of the file."""


class SourceUnreadable(IngestError):
    pass


class NoVideoStream(IngestError):
    pass


class SourceTooLarge(IngestError):
    """The file is larger, or the video longer, than the limit of the settings."""


class ConsentMissing(IngestError):
    pass


class MetaInvalid(IngestError):
    pass


class AlreadyIngested(IngestError):
    pass


@dataclass(frozen=True)
class IngestResult:
    manifest: RecordingManifest
    created: bool  # False when the same file was already ingested under the same IDs
    proxy: ProxyManifest | None = None  # set when the proxy was asked for and made (check it: ``proxy.check.passed``)
    proxy_error: str | None = None  # set when the proxy was asked for and failed; the recording is stored anyway


def _make_proxy(rec_dir: Path, recording_id: str) -> tuple[ProxyManifest | None, str | None]:
    """The optional proxy step (P2.03). The recording is already stored, so a failure is returned, never raised."""
    try:
        return make_proxy(rec_dir), None
    except ProxyError as exc:
        log.warning("recording %s is stored but its proxy was not made", recording_id)
        return None, str(exc)


def _parse_meta(meta: IngestMeta | Mapping[str, object]) -> IngestMeta:
    if isinstance(meta, IngestMeta):
        return meta
    try:  # anything that is not a mapping of the fields fails validation too (T-IO-14)
        return parse_manifest(IngestMeta, meta)
    except ManifestError as exc:
        raise MetaInvalid(str(exc)) from exc


def _check_source(src: Path, settings: Settings) -> None:
    if src.suffix.lower() not in EXTENSIONS:
        raise SourceUnreadable(f"unsupported container: only {', '.join(EXTENSIONS)} files are accepted")
    try:
        st = src.stat()
    except OSError:
        raise SourceUnreadable("the source file cannot be read (missing, or no permission)") from None
    if not stat.S_ISREG(st.st_mode):
        raise SourceUnreadable("the source is not a regular file")
    if st.st_size == 0:
        raise SourceUnreadable("the source file is empty")
    if st.st_size > settings.max_source_bytes:
        raise SourceTooLarge(f"the source file is larger than the limit of {settings.max_source_bytes} bytes")


def _existing(settings: Settings, row: sqlite3.Row, meta: IngestMeta, *, proxy: bool = False) -> IngestResult:
    rid = row["recording_id"]
    same = (row["participant_id"], row["session_id"], row["take_id"], row["camera_id"]) == (
        meta.participant_id,
        meta.session_id,
        meta.take_id,
        meta.camera_id,
    )
    if not same:
        raise AlreadyIngested(
            f"this file is already ingested as recording {rid} for another participant, session, take or camera"
        )
    rec_dir = settings.data_dir / "recordings" / rid
    try:
        manifest = read_manifest(rec_dir / "recording.json", RecordingManifest)
    except (OSError, ManifestError):
        raise IngestError(f"recording {rid} is in the database but its manifest is missing or invalid") from None
    log.info("recording %s already ingested", rid)
    proxy_manifest, proxy_error = _make_proxy(rec_dir, rid) if proxy else (None, None)
    return IngestResult(manifest, created=False, proxy=proxy_manifest, proxy_error=proxy_error)


def _consent_ref(conn: sqlite3.Connection, participant_id: str) -> str:
    try:
        participant = require_participant(conn, participant_id)
    except ParticipantError as exc:
        raise ConsentMissing(str(exc)) from exc
    if not participant.consent_analysis:
        raise ConsentMissing(f"participant {participant_id} has no analysis consent")
    if not re.fullmatch(CONSENT_RE, participant.consent_ref):
        raise ConsentMissing(f"participant {participant_id} has no valid consent reference")
    return participant.consent_ref


def _read_source(src: Path, settings: Settings) -> tuple[VideoMeta, PtsScan, VfrVerdict]:
    try:
        video = probe_video(src)
    except NoVideoStreamError:
        raise NoVideoStream("the source has no video stream") from None
    except ProbeError:
        raise SourceUnreadable("ffprobe could not read the source file (damaged, or not a video)") from None
    try:
        scan = scan_pts_ticks(src)
    except (av.error.FFmpegError, OSError, IndexError, ValueError):
        raise SourceUnreadable("PyAV could not read the video timestamps") from None
    if scan.pts.size == 0:
        raise SourceUnreadable("the video has no frames")
    verdict = vfr_verdict(scan.pts)
    if verdict.median_dt_ticks is not None and verdict.median_dt_ticks <= 0:
        raise SourceUnreadable("the video timestamps are not increasing (most frames share one timestamp)")
    tick = float(scan.time_base)
    span = float(scan.pts[-1] - scan.pts[0]) * tick
    duration = max(video.duration_s or 0.0, span + (verdict.median_dt_ticks or 0.0) * tick)
    if duration > settings.max_source_duration_s:
        raise SourceTooLarge(f"the video is longer than the limit of {settings.max_source_duration_s:g} seconds")
    return video, scan, verdict


@cache
def _tool_versions() -> dict[str, str]:
    ffprobe = "unknown"
    exe = shutil.which("ffprobe")
    if exe:
        try:
            first = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=15, check=False)
            ffprobe = first.stdout.splitlines()[0].split()[2]
        except (OSError, subprocess.SubprocessError, IndexError):
            log.warning("the ffprobe version could not be read; recorded as unknown")
    try:
        ours = metadata.version("taiji-ai")
    except metadata.PackageNotFoundError:
        ours = "0+unknown"
    return {"ffprobe": ffprobe, "pyav": av.__version__, "taiji_ai": ours}


def _build_manifest(
    *,
    recording_id: str,
    sha: str,
    size: int,
    ext: str,
    consent_ref: str,
    meta: IngestMeta,
    video: VideoMeta,
    scan: PtsScan,
    verdict: VfrVerdict,
) -> RecordingManifest:
    tick = float(scan.time_base)
    n = int(scan.pts.size)
    dt = np.diff(scan.pts)
    median_s = verdict.median_dt_ticks * tick if n >= 2 and verdict.median_dt_ticks else None
    audio = (
        {
            "codec": video.audio.codec,
            "sample_rate": video.audio.sample_rate,
            "channels": video.audio.channels,
            "start_offset_s": video.audio.start_time_s - video.start_time_s,
        }
        if video.audio is not None
        else None
    )
    data = {
        "schema_version": "recording/1",
        "recording_id": recording_id,
        "sha256": sha,
        "participant_id": meta.participant_id,
        "session_id": meta.session_id,
        "take_id": meta.take_id,
        "camera_id": meta.camera_id,
        "consent_ref": consent_ref,
        "source_ext": ext,
        "size_bytes": size,
        "container": video.format_name,
        "codec": video.codec,
        "width": video.width,
        "height": video.height,
        "display_rotation": video.rotation,
        "time_base": f"{scan.time_base.numerator}/{scan.time_base.denominator}",
        "start_pts": int(scan.start_pts),
        "n_frames": n,
        "pts_span_s": float(scan.pts[-1] - scan.pts[0]) * tick,
        "duration_s": video.duration_s,
        "nominal_fps": video.avg_frame_rate or None,
        "r_frame_rate": video.r_frame_rate or None,
        "measured_fps": 1.0 / median_s if median_s else None,
        "median_dt_s": median_s,
        "dt_rel_std": float(np.std(dt) / np.median(dt)) if n >= 2 else None,
        "n_duplicate_pts": int(verdict.n_duplicates),
        "vfr": bool(verdict.vfr),
        "vfr_rule": {
            "name": VFR_RULE.name,
            "version": VFR_RULE.version,
            "rel_tol": VFR_RULE.rel_tol,
            "tick_tol": VFR_RULE.tick_tol,
            "max_share": VFR_RULE.max_share,
        },
        "audio": audio,
        "capture": meta.capture.model_dump() if meta.capture is not None else None,
        "ingested_at": datetime.now().astimezone().isoformat(),
        "tools": _tool_versions(),
    }
    try:
        return parse_manifest(RecordingManifest, data)
    except ManifestError as exc:
        raise IngestError(f"the metadata of the file does not fit recording/1: {exc}") from exc


def _pts_table(scan: PtsScan) -> pa.Table:
    """``pts.parquet``: frame_index (presentation order), pts (ticks), t_sec; time_base, start_pts in the metadata."""
    table = pa.table(
        {
            "frame_index": pa.array(np.arange(scan.pts.size), pa.int32()),
            "pts": pa.array(scan.pts, pa.int64()),
            "t_sec": pa.array(scan.t_sec, pa.float64()),
        }
    )
    time_base = f"{scan.time_base.numerator}/{scan.time_base.denominator}"
    return table.replace_schema_metadata({"time_base": time_base, "start_pts": str(scan.start_pts)})


def _remove_tree(path: Path) -> None:
    """Remove a folder even if it holds read-only files (the stored copy is read-only); no error if it is absent."""

    def clear_and_retry(func, failed_path, exc) -> None:
        os.chmod(failed_path, stat.S_IRWXU)
        func(failed_path)

    if path.exists():
        shutil.rmtree(path, onexc=clear_and_retry)


def ingest_recording(
    path: str | Path,
    meta: IngestMeta | Mapping[str, object],
    settings: Settings | None = None,
    *,
    proxy: bool = False,
) -> IngestResult:
    """Ingest one video (see the module docstring for the order of operations).

    With ``proxy=True`` the browser proxy is made after the recording is stored (also for a file that was already
    ingested). A proxy failure never undoes the recording: it is reported in ``IngestResult.proxy_error``, and a proxy
    that failed its timestamp check is in ``IngestResult.proxy`` with ``check.passed = False``.

    Raises:
        MetaInvalid: ``meta`` does not validate.
        SourceUnreadable, NoVideoStream, SourceTooLarge: the file cannot be used.
        ConsentMissing: the participant is not registered or has no valid analysis consent.
        AlreadyIngested: the file, or the take and camera, already has a recording under other IDs.
        IngestError: writing the recording failed.
    """
    settings = settings or get_settings()
    ids = _parse_meta(meta)
    src = Path(path)
    _check_source(src, settings)
    try:
        sha = sha256_file(src)
    except OSError:
        raise SourceUnreadable("the source file cannot be read (missing, or no permission)") from None

    conn = connect(settings.db_path, settings.migrations_dir)
    try:
        row = find_by_sha(conn, sha)
        if row is not None:
            return _existing(settings, row, ids, proxy=proxy)
        consent_ref = _consent_ref(conn, ids.participant_id)
        taken = find_by_take_camera(conn, ids.take_id, ids.camera_id)
        if taken is not None:
            raise AlreadyIngested(
                f"take {ids.take_id} already has a recording from {ids.camera_id} ({taken['recording_id']}); "
                "a retake needs a new take id"
            )
        video, scan, verdict = _read_source(src, settings)

        recordings = settings.data_dir / "recordings"
        recordings.mkdir(parents=True, exist_ok=True)
        recording_id = str(uuid.uuid4())
        staging = recordings / f".staging-{recording_id}"
        final = recordings / recording_id
        ext = src.suffix.lower()
        renamed = False
        try:
            staging.mkdir()
            stored = staging / f"source{ext}"
            shutil.copyfile(src, stored)
            if sha256_file(stored) != sha:
                raise IngestError("the stored copy differs from the source (did the file change during ingest?)")
            atomic_write_parquet(staging / "pts.parquet", _pts_table(scan))
            manifest = _build_manifest(
                recording_id=recording_id,
                sha=sha,
                size=stored.stat().st_size,  # the stored copy, whose hash was checked, is the truth
                ext=ext,
                consent_ref=consent_ref,
                meta=ids,
                video=video,
                scan=scan,
                verdict=verdict,
            )
            write_manifest(staging / "recording.json", manifest)  # the manifest is written last
            os.chmod(stored, stat.S_IREAD)
            os.replace(staging, final)
            renamed = True
        except OSError as exc:
            raise IngestError("could not write the recording folder (disk full, or no permission)") from exc
        finally:
            if not renamed:
                _remove_tree(staging)

        try:
            with conn:
                insert_recording(conn, manifest.to_db_row())
        except sqlite3.Error as exc:
            orphan = recordings / f".orphan-{recording_id}"
            try:
                os.replace(final, orphan)
            except OSError:
                log.error(
                    "recording %s is not in the database and its folder could not be marked as orphan", recording_id
                )
                raise IngestError(
                    f"the record of {recording_id} could not be stored in the database, and its folder "
                    "could not be renamed to .orphan: remove the folder by hand"
                ) from exc
            log.error("recording %s could not be stored in the database; folder kept as .orphan", recording_id)
            raise IngestError(
                f"the record of {recording_id} could not be stored in the database; "
                f"its folder was moved to .orphan-{recording_id}"
            ) from exc
    finally:
        conn.close()

    proxy_manifest, proxy_error = _make_proxy(final, recording_id) if proxy else (None, None)

    log.info(
        "recording %s ingested (take %s, %s, %d frames, vfr=%s)",
        recording_id,
        ids.take_id,
        ids.camera_id,
        manifest.n_frames,
        manifest.vfr,
    )
    return IngestResult(manifest, created=True, proxy=proxy_manifest, proxy_error=proxy_error)
