"""The pose pass of the failure review (P3.08): every D20 video, in chunks, one pose file per chunk.

``run_pose_pass`` runs ``run_pose`` over each recording in chunks of ``chunk_s`` seconds (default 300 s, plus the 1 s
margins that ``run_pose`` adds) and saves every chunk as ``pose/<label>_<index>.npz`` (``pose_raw/1``). A chunk whose
file already exists is skipped, so an interrupted pass resumes where it stopped. A manifest ``pass.json`` lists the
chunks.
The chunks overlap by the margins; ``chunk_frame_mask`` says which frames of a chunk belong to it (start <= t < end, the
last chunk of a video to its last frame), so that the per-frame results of the chunks can be joined without duplicates.

Videos are named by their label (``d20-v1``); the manifest holds recording IDs, never a path or a file name.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

from taiji_ai.audit import AuditError
from taiji_ai.pose.raw_io import save_pose_raw
from taiji_ai.pose.runner import PoseModel, PoseRaw, PoseRunParams, run_pose
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.recording import RecordingManifest
from taiji_ai.store.artifacts import atomic_write_json

log = logging.getLogger(__name__)

CHUNK_S = 300.0
MIN_LAST_CHUNK_S = 1.0  # a remainder shorter than this joins the previous chunk
_EPS = 1e-9


def plan_chunks(duration_s: float, chunk_s: float = CHUNK_S) -> list[tuple[float, float]]:
    """``(start, end)`` of the chunks that cover ``[0, duration_s]``; a last piece under 1 s joins the one before."""
    if not (math.isfinite(duration_s) and duration_s > 0.0):
        raise AuditError(f"the duration must be a finite number of seconds > 0, got {duration_s!r}")
    if not (math.isfinite(chunk_s) and chunk_s > 0.0):
        raise AuditError(f"the chunk length must be a finite number of seconds > 0, got {chunk_s!r}")
    chunks: list[tuple[float, float]] = []
    i = 0
    while i * chunk_s < duration_s - _EPS:
        chunks.append((i * chunk_s, min((i + 1) * chunk_s, duration_s)))
        i += 1
    if len(chunks) > 1 and chunks[-1][1] - chunks[-1][0] < MIN_LAST_CHUNK_S:
        last = chunks.pop()
        chunks[-1] = (chunks[-1][0], last[1])
    return chunks


def chunk_path(out_dir: Path | str, label: str, index: int) -> Path:
    return Path(out_dir) / "pose" / f"{label}_{index:03d}.npz"


def chunk_frame_mask(t_sec: np.ndarray, start_s: float, end_s: float, *, first: bool, last: bool) -> np.ndarray:
    """The frames of a chunk that belong to it: ``start <= t < end``; the first chunk of a video keeps everything before
    its end (there is no earlier chunk) and the last one everything from its start (there is no later chunk)."""
    t = np.asarray(t_sec, dtype=np.float64)
    keep = np.ones(t.shape, dtype=bool)
    if not first:
        keep &= t >= start_s - _EPS
    if not last:
        keep &= t < end_s - _EPS
    return keep


def run_pose_pass(
    recordings: dict[str, Path],
    out_dir: Path | str,
    model: PoseModel,
    *,
    n: int = 1,
    chunk_s: float = CHUNK_S,
) -> dict[str, Any]:
    """Run the pose over every recording in chunks and save one file per chunk; returns the manifest (also written).

    Args:
        recordings: label -> the stored recording folder (``recording.json``, ``pts.parquet``, ``source.*``).
        out_dir: where ``pose/`` and ``pass.json`` go.
        model: the pose model (the verified estimator, or a fake in tests).
        n: the detector cadence of the pass (``PoseRunParams.detect_every_n``).
        chunk_s: length of a chunk.
    """
    out = Path(out_dir)
    (out / "pose").mkdir(parents=True, exist_ok=True)
    params = PoseRunParams(detect_every_n=n)
    manifest: dict[str, Any] = {"schema": "p3_08_pass/1", "n": n, "chunk_s": chunk_s, "videos": {}}
    for label in sorted(recordings):
        rec = recordings[label]
        info = read_manifest(rec / "recording.json", RecordingManifest)
        chunks = plan_chunks(info.pts_span_s, chunk_s)
        entries = []
        for index, (start, end) in enumerate(chunks):
            path = chunk_path(out, label, index)
            if path.exists():
                log.info("%s chunk %d of %d: already there, skipped", label, index + 1, len(chunks))
            else:
                started = time.perf_counter()
                raw = run_pose(rec, start, end, model, params=params)
                save_pose_raw(path, raw)
                persons = int(raw.person_offsets[-1])
                seconds = time.perf_counter() - started
                log.info(
                    "%s chunk %d of %d: %d frames, %d persons, %.0f s",
                    label,
                    index + 1,
                    len(chunks),
                    raw.n_frames,
                    persons,
                    seconds,
                )
            entries.append({"index": index, "start_s": start, "end_s": end, "file": path.name})
        manifest["videos"][label] = {
            "recording_id": info.recording_id,
            "duration_s": info.pts_span_s,
            "n_frames": info.n_frames,
            "chunks": entries,
        }
        atomic_write_json(out / "pass.json", manifest)  # after every video: a stop keeps what is done
    return manifest


def read_pass(out_dir: Path | str) -> dict[str, Any]:
    """Read ``pass.json``; a missing or malformed file is an ``AuditError``."""
    try:
        data = json.loads((Path(out_dir) / "pass.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditError("pass.json is missing or is not JSON: run the pose pass first") from exc
    if not isinstance(data, dict) or data.get("schema") != "p3_08_pass/1" or not isinstance(data.get("videos"), dict):
        raise AuditError("pass.json is not a pass of this version")
    return data


def load_chunk(out_dir: Path | str, label: str, index: int) -> PoseRaw:
    from taiji_ai.pose.raw_io import load_pose_raw

    path = chunk_path(out_dir, label, index)
    if not path.exists():
        raise AuditError(f"the pose file of chunk {index} of {label} is missing")
    return load_pose_raw(path)
