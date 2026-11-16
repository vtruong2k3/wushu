"""The clips of the pose benchmark (P3.07): the D20 videos found by size and SHA-256, the five clips, the plan file.

The four videos of D20 (``Docs/DATASET_REGISTRY_TAIJI.md``) are local, third-party files kept out of git (DEC-0036: used
for internal development only). They are found in a folder **by size and SHA-256, never by file name**, and everything
that is printed or stored names them ``d20-v1`` to ``d20-v4``.

The five clips and their start times were fixed before any number was seen (task file P3.07, section 1, point 2): mixed
on purpose for codec, frame rate and crowd. A clip is a segment of 30 s; ``run_pose`` adds the margins.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from taiji_ai.bench import BenchError
from taiji_ai.store.artifacts import sha256_file

SEGMENT_S: Final = 30.0


@dataclass(frozen=True)
class VideoSpec:
    label: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ClipSpec:
    clip_id: str
    video_label: str
    start_s: float  # [s] from the stream start


# Sizes and SHA-256 as listed in Docs/DATASET_REGISTRY_TAIJI.md (D20).
D20_VIDEOS: Final[dict[str, VideoSpec]] = {
    "d20-v1": VideoSpec("d20-v1", 215_719_545, "f80bd1594d0311e2493e33ee4ed55e51904267f0151a2323933252f7f501c0cf"),
    "d20-v2": VideoSpec("d20-v2", 257_287_499, "50a6cd2f383ccd8fc3da77b94d300bd80cd5d3f5cf208a13aa12e6004e35bec8"),
    "d20-v3": VideoSpec("d20-v3", 350_787_594, "1eb59b6f01c32dcff463f6c37e53d04ca536a3a5be55ffb3055c71fe393f1d7d"),
    "d20-v4": VideoSpec("d20-v4", 486_260_064, "65d2913540fcff7afb3af1052b5be09e4ec686cb181f28d789b8669e3e57e15a"),
}
CLIPS: Final[dict[str, ClipSpec]] = {
    "c1": ClipSpec("c1", "d20-v2", 300.0),  # H.264 24 fps, one person in every frame (P3.02)
    "c2": ClipSpec("c2", "d20-v2", 660.0),  # H.264 24 fps, up to four people (P3.05)
    "c3": ClipSpec("c3", "d20-v3", 600.0),  # H.264 24 fps
    "c4": ClipSpec("c4", "d20-v1", 500.0),  # AV1 24 fps
    "c5": ClipSpec("c5", "d20-v4", 1200.0),  # AV1 30 fps
}


def find_videos(folder: Path | str, wanted: Mapping[str, VideoSpec]) -> dict[str, Path]:
    """The file of every wanted video in ``folder``, found by size and then SHA-256 (the name is never used).

    Raises:
        BenchError: the folder is missing, or a wanted video is absent or has another SHA-256; the message names the
            labels only, never a file name or a path.
    """
    root = Path(folder)
    if not root.is_dir():
        raise BenchError("the video folder does not exist")
    by_size: dict[int, list[VideoSpec]] = {}
    for spec in wanted.values():
        by_size.setdefault(spec.size_bytes, []).append(spec)
    found: dict[str, Path] = {}
    wrong_hash: set[str] = set()
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        specs = by_size.get(path.stat().st_size)
        if not specs:
            continue
        digest = sha256_file(path)
        for spec in specs:
            if digest == spec.sha256:
                found.setdefault(spec.label, path)
            else:
                wrong_hash.add(spec.label)
    missing = [label for label in wanted if label not in found]
    if missing:
        notes = [
            f"{label} ({'a file of its size has another SHA-256' if label in wrong_hash else 'not found'})"
            for label in missing
        ]
        raise BenchError("video(s) not matching the registry by size and SHA-256: " + ", ".join(notes))
    return found


@dataclass(frozen=True)
class PlanEntry:
    """One clip for the worker: an ingested recording and the segment to run."""

    clip_id: str
    recording_dir: str
    start_s: float
    end_s: float


def write_plan(path: Path | str, entries: list[PlanEntry]) -> None:
    Path(path).write_text(
        json.dumps(
            [
                {"clip_id": e.clip_id, "recording_dir": e.recording_dir, "start_s": e.start_s, "end_s": e.end_s}
                for e in entries
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


def read_plan(path: Path | str) -> list[PlanEntry]:
    """Read and check a plan; any wrong shape is a ``BenchError`` naming the entry."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BenchError("the plan file could not be read as JSON") from exc
    if not isinstance(data, list) or not data:
        raise BenchError("the plan must be a non-empty list of clips")
    entries: list[PlanEntry] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or set(item) != {"clip_id", "recording_dir", "start_s", "end_s"}:
            raise BenchError(f"plan entry {i} must have exactly clip_id, recording_dir, start_s and end_s")
        start, end = item["start_s"], item["end_s"]
        if (
            not isinstance(item["clip_id"], str)
            or not isinstance(item["recording_dir"], str)
            or isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int | float)
            or not isinstance(end, int | float)
            or not (math.isfinite(start) and math.isfinite(end) and start < end)
        ):
            raise BenchError(f"plan entry {i} has a wrong type or a segment that is not a finite range")
        entries.append(PlanEntry(item["clip_id"], item["recording_dir"], float(start), float(end)))
    ids = [e.clip_id for e in entries]
    if len(set(ids)) != len(ids):
        raise BenchError("the plan lists a clip twice")
    return entries
