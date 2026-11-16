"""Flash validation of camera synchronization (W2 step 4, P2.05).

The capture protocol (§5) switches a light on with each clap, visible to both cameras.
This module extracts mean brightness (luma), finds rising steps (flash onsets), pairs
them across cameras via the audio sync time mapping, and computes the residual in
milliseconds and in frames of the slower camera.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import av
import numpy as np

from taiji_ai.schemas._base import ManifestError, read_manifest
from taiji_ai.schemas.recording import RecordingManifest
from taiji_ai.schemas.sync import SyncManifest, SyncValidation

if TYPE_CHECKING:
    from collections.abc import Callable

    from taiji_ai.io.audio_sync import AudioSyncResult

log = logging.getLogger(__name__)


class FlashError(Exception):
    """Raised when flash extraction or validation fails."""


@dataclass(frozen=True)
class FlashParams:
    """Parameters for flash onset detection and window matching."""

    min_step: float = 15.0  # Minimum luma step increase (0-255 scale)
    k_mad: float = 5.0  # Multiplier for robust standard deviation (1.4826 * MAD)
    min_separation_s: float = 0.3  # Minimum refractory time between consecutive flashes [s]
    search_margin_s: float = 2.0  # Margin around window to search for matching flash in B [s]
    downscale_step: int = 4  # Spatial subsampling step for luma extraction
    min_flashes: int = 2  # Flashes of one signal (the capture protocol makes a pair, 1 s apart) needed on each camera


def brightness_series(
    path: str | Path,
    t0: float | None = None,
    t1: float | None = None,
    step: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    """Decode frames in [t0, t1] (seconds from stream start) and return timestamps and mean luma.

    Uses PyAV video stream decoding with real PTS timestamps.
    """
    file_path = Path(path).resolve()
    if not file_path.is_file():
        raise FlashError(f"video file does not exist: {file_path.name}")

    ts_list: list[float] = []
    luma_list: list[float] = []

    try:
        with av.open(str(file_path)) as container:
            if not container.streams.video:
                raise FlashError(f"no video stream found in {file_path.name}")
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            tb = stream.time_base
            start = stream.start_time if stream.start_time is not None else 0

            # Seek backward if t0 is specified and positive
            if t0 is not None and t0 > 0.0:
                seek_pts = int(t0 / tb) + start
                container.seek(seek_pts, stream=stream, backward=True, any_frame=False)

            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                t = float((frame.pts - start) * tb)
                if t0 is not None and t < t0 - 1e-6:
                    continue
                if t1 is not None and t > t1 + 1e-6:
                    break

                gray = frame.to_ndarray(format="gray")
                sub = gray[::step, ::step] if step > 1 else gray
                ts_list.append(t)
                luma_list.append(float(np.mean(sub)))
    except (av.error.FFmpegError, OSError, ValueError) as exc:
        raise FlashError(f"decoding error reading brightness series from {file_path.name}") from exc

    return np.asarray(ts_list, dtype=np.float64), np.asarray(luma_list, dtype=np.float32)


def find_flash_onsets(
    t_sec: np.ndarray,
    luma: np.ndarray,
    *,
    params: FlashParams | None = None,
) -> list[float]:
    """Detect flash onsets (rising steps in brightness) using robust difference statistics.

    The onset timestamp is the timestamp of the first bright frame.
    """
    params = params or FlashParams()
    if luma.size < 2:
        return []

    diff = np.diff(luma)
    med = float(np.median(diff))
    mad = float(np.median(np.abs(diff - med)))
    robust_std = 1.4826 * mad
    thresh = max(params.min_step, med + params.k_mad * robust_std)

    onsets: list[float] = []
    for i in range(len(diff)):
        if diff[i] > thresh:
            onset_t = float(t_sec[i + 1])
            if not onsets or (onset_t - onsets[-1]) >= params.min_separation_s:
                onsets.append(onset_t)

    return onsets


def match_flashes(
    onsets_a: list[float],
    onsets_b: list[float],
    a_to_b: Callable[[float], float],
    *,
    min_flashes: int = 2,
) -> float | None:
    """Largest distance [ms] between the flashes of one window and where the time mapping puts them (X.23, BUG-0064).

    The flashes of A and B are matched **one to one in time order** (``a_to_b`` is increasing, so the order is the same
    on both cameras): the i-th flash of A is compared with the i-th flash of B. The window can be judged only if both
    cameras show the same number of flashes and at least ``min_flashes``; otherwise ``None`` (no residual, never 0).

    Why not the closest flash of B for each flash of A: the flashes come in pairs 1 s apart, like the claps, so a
    mapping wrong by one pair gap puts the first flash of A on the second flash of B at 0 ms, and a flash without a
    partner was ignored. Why the largest distance and not the mean: a mean can hide one bad match.

    Args:
        onsets_a: flash onsets seen by camera A in the window [s, A's video timeline].
        onsets_b: flash onsets seen by camera B in its (wider) window [s, B's video timeline].
        a_to_b: the time mapping A -> B of the audio sync [s -> s].
        min_flashes: flashes needed on each camera.

    Returns:
        The residual in milliseconds, or ``None`` when the window cannot be judged.
    """
    if len(onsets_a) < max(1, min_flashes) or len(onsets_a) != len(onsets_b):
        log.info(
            "flash window not judged: %d flashes on A, %d on B (need equal, at least %d)",
            len(onsets_a),
            len(onsets_b),
            min_flashes,
        )
        return None
    distances = [abs(tb - a_to_b(ta)) for ta, tb in zip(sorted(onsets_a), sorted(onsets_b), strict=True)]
    return float(max(distances)) * 1000.0


def validate_sync(
    audio_sync: AudioSyncResult | SyncManifest,
    rec_dir_a: Path | str,
    rec_dir_b: Path | str,
    *,
    params: FlashParams | None = None,
) -> SyncValidation:
    """Validate camera synchronization with visible flash markers (W2 step 4)."""
    params = params or FlashParams()
    path_a = Path(rec_dir_a).resolve()
    path_b = Path(rec_dir_b).resolve()

    try:
        man_a = read_manifest(path_a / "recording.json", RecordingManifest)
        man_b = read_manifest(path_b / "recording.json", RecordingManifest)
    except (OSError, ManifestError) as exc:
        raise FlashError("could not read recording manifest for validation") from exc

    # Ensure Camera A is the reference (cam_a sorts before cam_b)
    if man_a.camera_id > man_b.camera_id:
        path_a, path_b = path_b, path_a
        man_a, man_b = man_b, man_a

    # The mapping belongs to two recordings: refuse any other pair, whatever the audio status (BUG-0067).
    if (man_a.recording_id, man_b.recording_id) != (audio_sync.recording_id_a, audio_sync.recording_id_b):
        raise FlashError("the recordings in the two folders are not those of the audio sync result")

    # Median frame interval of the slower camera; no made-up value when a manifest has none (BUG-0067).
    if man_a.median_dt_s is None or man_b.median_dt_s is None:
        raise FlashError("a recording has no frame interval (median_dt_s): the residual in frames cannot be given")
    frame_dt_s = max(float(man_a.median_dt_s), float(man_b.median_dt_s))

    # Check if time mapping exists
    if (
        audio_sync.status != "ok"
        or audio_sync.offset_s is None
        or audio_sync.drift is None
        or audio_sync.t_ref_s is None
    ):
        log.info("sync status is %s: flash validation unavailable", audio_sync.status)
        return SyncValidation(
            method="none",
            flash_a_s=(),
            flash_b_s=(),
            residual_start_ms=None,
            residual_end_ms=None,
            residual_ms=None,
            residual_frames=None,
            frame_dt_s=None,
        )

    offset_s = float(audio_sync.offset_s)
    drift = float(audio_sync.drift)
    t_ref_s = float(audio_sync.t_ref_s)

    def a_to_b(t_a: float) -> float:
        return t_a + offset_s + drift * (t_a - t_ref_s)

    w_start_a = audio_sync.start.window_a_s
    w_end_a = audio_sync.end.window_a_s

    src_a = path_a / f"source{man_a.source_ext}"
    src_b = path_b / f"source{man_b.source_ext}"

    # Search window bounds for Camera B (mapped from A with search margin)
    w_start_b_t0 = max(0.0, a_to_b(w_start_a[0]) - params.search_margin_s)
    w_start_b_t1 = a_to_b(w_start_a[1]) + params.search_margin_s

    w_end_b_t0 = max(0.0, a_to_b(w_end_a[0]) - params.search_margin_s)
    w_end_b_t1 = a_to_b(w_end_a[1]) + params.search_margin_s

    # 1. Start window
    ts_a_start, luma_a_start = brightness_series(src_a, t0=w_start_a[0], t1=w_start_a[1], step=params.downscale_step)
    ts_b_start, luma_b_start = brightness_series(src_b, t0=w_start_b_t0, t1=w_start_b_t1, step=params.downscale_step)

    onsets_a_start = find_flash_onsets(ts_a_start, luma_a_start, params=params)
    onsets_b_start = find_flash_onsets(ts_b_start, luma_b_start, params=params)

    # 2. End window
    ts_a_end, luma_a_end = brightness_series(src_a, t0=w_end_a[0], t1=w_end_a[1], step=params.downscale_step)
    ts_b_end, luma_b_end = brightness_series(src_b, t0=w_end_b_t0, t1=w_end_b_t1, step=params.downscale_step)

    onsets_a_end = find_flash_onsets(ts_a_end, luma_a_end, params=params)
    onsets_b_end = find_flash_onsets(ts_b_end, luma_b_end, params=params)

    res_start_ms = match_flashes(onsets_a_start, onsets_b_start, a_to_b, min_flashes=params.min_flashes)
    res_end_ms = match_flashes(onsets_a_end, onsets_b_end, a_to_b, min_flashes=params.min_flashes)

    all_onsets_a = tuple(sorted(set(onsets_a_start + onsets_a_end)))
    all_onsets_b = tuple(sorted(set(onsets_b_start + onsets_b_end)))

    if res_start_ms is None and res_end_ms is None:
        log.info("no flash onsets matched between cameras for take %s", man_a.take_id)
        return SyncValidation(
            method="none",
            flash_a_s=all_onsets_a,
            flash_b_s=all_onsets_b,
            residual_start_ms=None,
            residual_end_ms=None,
            residual_ms=None,
            residual_frames=None,
            frame_dt_s=None,
        )

    ends = [r for r in (res_start_ms, res_end_ms) if r is not None]
    residual_ms = float(max(ends))
    residual_frames = float(residual_ms / 1000.0 / frame_dt_s)

    log.info(
        "flash validation for take %s: residual=%.2f ms (%.2f frames), start=%s ms, end=%s ms",
        man_a.take_id,
        residual_ms,
        residual_frames,
        res_start_ms,
        res_end_ms,
    )

    return SyncValidation(
        method="flash",
        flash_a_s=all_onsets_a,
        flash_b_s=all_onsets_b,
        residual_start_ms=res_start_ms,
        residual_end_ms=res_end_ms,
        residual_ms=residual_ms,
        residual_frames=residual_frames,
        frame_dt_s=frame_dt_s,
    )
