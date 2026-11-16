"""Create an H.264 browser proxy (720 lines at most) that keeps the source timestamps (W1 step 5, P2.03).

The proxy is stored in ``data/recordings/<recording_id>/`` as:
    proxy.mp4     the browser-playable video (libx264, yuv420p, +faststart, no audio, no metadata)
    proxy.json    the manifest (``proxy/1``), which records the result of the timestamp check

The FFmpeg command is written once, in ``PROXY_ARGS_TEMPLATE`` (a list of arguments, never a shell string).
``proxy.json`` records that template and ``_build_command`` makes the command that runs from it, so the two cannot
differ. Time convention: seconds from the stream start, as in ``pts.parquet``.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from functools import cache
from pathlib import Path

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from taiji_ai.io.frames import scan_pts_ticks
from taiji_ai.io.probe import ProbeError, probe_video
from taiji_ai.schemas._base import ManifestError, read_manifest, write_manifest
from taiji_ai.schemas.recording import PROXY_MAX_DT_FRAMES, ProxyCheck, ProxyManifest, RecordingManifest
from taiji_ai.store.artifacts import sha256_file

log = logging.getLogger(__name__)

# The command, with placeholders for the two paths. Recorded in proxy.json (which never holds a real path).
PROXY_ARGS_TEMPLATE: tuple[str, ...] = (
    "-i",
    "{source}",
    "-map",
    "0:v:0",
    "-vf",
    "scale=-2:'min(720,ih)'",
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "23",
    "-g",
    "30",
    "-pix_fmt",
    "yuv420p",
    "-fps_mode",
    "passthrough",
    "-an",
    "-movflags",
    "+faststart",
    "-map_metadata",
    "-1",
    "{proxy}",
)
# Put before the template: quiet output and overwrite the (unique) temporary file. Not part of the recorded command.
_FFMPEG_PREFIX: tuple[str, ...] = ("-hide_banner", "-loglevel", "error", "-y")
_SAMPLE_POINTS = 10  # evenly spaced frames of the plan's check (first and last included); every frame is compared too


class ProxyError(Exception):
    """A proxy operation failed or was refused; the message carries IDs only, never paths or ffmpeg's text."""


@cache
def _ffmpeg_version(exe: str) -> str:
    """The version in the first line of ``<exe> -version``; a failure raises (and is not cached)."""
    try:
        res = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProxyError("could not read the ffmpeg version") from exc
    lines = res.stdout.splitlines()
    parts = lines[0].split() if lines else []
    if res.returncode != 0 or len(parts) < 3 or parts[:2] != ["ffmpeg", "version"]:
        raise ProxyError("could not read the ffmpeg version: unexpected output of 'ffmpeg -version'")
    return parts[2]


def _build_command(ffmpeg_exe: str, source: Path, proxy: Path) -> list[str]:
    """The command that runs: the fixed prefix and ``PROXY_ARGS_TEMPLATE`` with the two paths filled in."""
    paths = {"{source}": str(source), "{proxy}": str(proxy)}
    return [ffmpeg_exe, *_FFMPEG_PREFIX, *(paths.get(arg, arg) for arg in PROXY_ARGS_TEMPLATE)]


def _check_timestamps(
    proxy_path: Path,
    source_t_sec: np.ndarray,
    median_dt_s: float | None,
) -> tuple[int, ProxyCheck]:
    """Compare the frame times of the proxy with those of the source (both seconds from the stream start).

    Returns the number of proxy frames and the check. ``passed`` needs equal frame counts and every frame within
    ``PROXY_MAX_DT_FRAMES`` of the source (stricter than the plan's 10 sample points, which are counted in ``points``).
    When the counts differ the deviation is measured over the frames both files have, and the check fails.
    Raises ``ProxyError`` when nothing can be measured: no number is ever made up.
    """
    n_source = int(source_t_sec.size)
    if n_source == 0:
        raise ProxyError("the source has no frames in pts.parquet")
    scan = scan_pts_ticks(proxy_path)
    n_proxy = int(scan.pts.size)
    if n_proxy == 0:
        raise ProxyError("the proxy has no frames")

    n_common = min(n_source, n_proxy)
    max_abs_dt_s = float(np.max(np.abs(scan.t_sec[:n_common] - source_t_sec[:n_common])))
    if median_dt_s is not None and median_dt_s > 0:
        max_abs_dt_frames = max_abs_dt_s / median_dt_s
    elif max_abs_dt_s == 0.0:
        max_abs_dt_frames = 0.0  # no deviation is no deviation in any unit
    else:
        raise ProxyError("the source has no frame interval, so the timestamp deviation cannot be expressed in frames")

    return n_proxy, ProxyCheck(
        points=min(_SAMPLE_POINTS, n_common),
        max_abs_dt_s=max_abs_dt_s,
        max_abs_dt_frames=max_abs_dt_frames,
        passed=n_proxy == n_source and max_abs_dt_frames <= PROXY_MAX_DT_FRAMES,
    )


def make_proxy(recording_dir: Path | str) -> ProxyManifest:
    """Create ``proxy.mp4`` and ``proxy.json`` for a recording folder and return the manifest.

    A proxy that fails the timestamp check is kept and marked (``check.passed = false``): the caller must not use it
    for frame-accurate work. An existing proxy is replaced only after the new one is encoded and checked; its
    ``proxy.json`` is removed just before, so a crash never leaves a manifest that describes another file.

    Raises:
        ProxyError: the recording folder is incomplete, ffmpeg is missing, fails or times out, or nothing is measurable.
    """
    rec_path = Path(recording_dir).resolve()
    if not rec_path.is_dir():
        raise ProxyError("the recording folder does not exist or is not a directory")

    try:
        rec_manifest = read_manifest(rec_path / "recording.json", RecordingManifest)
    except (OSError, ManifestError) as exc:
        raise ProxyError("recording manifest is missing or invalid in the recording folder") from exc

    source_path = rec_path / f"source{rec_manifest.source_ext}"
    if not source_path.is_file():
        raise ProxyError("source video is missing in the recording folder")

    pts_path = rec_path / "pts.parquet"
    if not pts_path.is_file():
        raise ProxyError("pts.parquet is missing in the recording folder")
    try:
        source_t_sec = pq.read_table(pts_path)["t_sec"].to_numpy()
    except (OSError, pa.ArrowException, KeyError) as exc:
        raise ProxyError("could not read source timestamps from pts.parquet") from exc

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise ProxyError("ffmpeg is not available on PATH")
    ffmpeg_version = _ffmpeg_version(ffmpeg_exe)

    rec_id = rec_manifest.recording_id
    proxy_tmp = rec_path / f"proxy.tmp-{uuid.uuid4().hex}.mp4"
    proxy_final = rec_path / "proxy.mp4"
    manifest_final = rec_path / "proxy.json"
    timeout_s = max(60.0, (rec_manifest.duration_s or 60.0) * 4.0)
    cmd = _build_command(ffmpeg_exe, source_path, proxy_tmp)

    try:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired:
            raise ProxyError(f"ffmpeg timed out after {timeout_s:.0f} s while making the proxy") from None
        if res.returncode != 0:
            log.error("ffmpeg failed with code %d while making the proxy of recording %s", res.returncode, rec_id)
            raise ProxyError("ffmpeg failed to encode the proxy video")

        proxy_meta = probe_video(proxy_tmp)
        n_proxy, check = _check_timestamps(proxy_tmp, source_t_sec, rec_manifest.median_dt_s)
        manifest = ProxyManifest(
            schema_version="proxy/1",
            recording_id=rec_id,
            source_sha256=rec_manifest.sha256,
            proxy_sha256=sha256_file(proxy_tmp),
            height=proxy_meta.height,
            rotation_applied=rec_manifest.display_rotation,
            ffmpeg=ffmpeg_version,
            args=PROXY_ARGS_TEMPLATE,
            n_frames_source=int(source_t_sec.size),
            n_frames_proxy=n_proxy,
            check=check,
        )

        manifest_final.unlink(missing_ok=True)  # a missing manifest means "not usable"; never a stale one
        os.replace(proxy_tmp, proxy_final)
        write_manifest(manifest_final, manifest)  # the manifest is written last
    except (OSError, ValueError, ProbeError, av.error.FFmpegError) as exc:  # ValueError: ManifestError, pydantic
        raise ProxyError("failed to make the proxy of the recording") from exc
    finally:
        try:
            proxy_tmp.unlink(missing_ok=True)
        except OSError:
            log.warning("could not remove the temporary proxy file of recording %s", rec_id)

    if check.passed:
        log.info(
            "proxy made for recording %s (height=%d, frames=%d, max deviation %.3f frames)",
            rec_id,
            manifest.height,
            n_proxy,
            check.max_abs_dt_frames,
        )
    else:
        log.warning(
            "proxy of recording %s FAILED the timestamp check and is marked unusable "
            "(source frames=%d, proxy frames=%d, max deviation %.3f frames, limit %.1f)",
            rec_id,
            manifest.n_frames_source,
            n_proxy,
            check.max_abs_dt_frames,
            PROXY_MAX_DT_FRAMES,
        )
    return manifest
