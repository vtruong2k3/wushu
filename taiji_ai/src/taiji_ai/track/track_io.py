"""Save and load ``track.parquet``, the target over time (schema ``track/1``, P3.06).

One row per frame of the pose file, in frame order; the columns, in this order, have fixed names and types:

* ``frame_index`` int32: row of the frame in ``pts.parquet``, strictly increasing;
* ``t_sec`` float64: seconds from the stream start (real PTS), finite and strictly increasing;
* ``in_segment`` bool: the frame lies in the segment asked for (the 1 s margins are kept for P4's filter);
* ``status`` string: ``tracked``, ``lost``, ``target_lost`` or ``before_target``;
* ``track_id`` int32 and ``person_row`` int32: the track and the person row of the pose file used in the frame;
  -1 when the status is not ``tracked``;
* ``keypoints`` fixed-size list of 52 float32: ``x0, y0, x1, y1, ...`` [px] of the upright image, y down; **NaN in every
  value of a row that is not ``tracked``** (nothing is filled), exactly the raw values of the model otherwise;
* ``scores`` fixed-size list of 26 float32: the model's scores, NaN where the status is not ``tracked``;
* ``match_cost``, ``match_margin`` float32: association cost and margin of the person (P3.05), NaN where none;
* ``reattach_cost`` float32: on the frame of a re-attachment the cost that allowed it, NaN elsewhere.

``taiji_ai.schemas.track.TrackMeta`` is stored as JSON in the Parquet schema metadata under ``taiji_track_meta``
(version, selection, parameters, counts, whether the user must choose again and why, the events). Nothing in the
file is a path or a file name. Nulls are refused: "not observed" is NaN, never null.

Loading is strict: another version, a missing or extra column, a wrong type, a null, a status that does not exist,
rows that break the rules above, counts or events that disagree with the rows are a ``TrackFileError`` that names the
field. A later version adds a reader to ``_READERS``; an old file is never upgraded silently. Saving checks the same
rules before anything is written, then writes atomically. The caller chooses the path (P7: ``runs/<run_id>/``); its
folder must exist. ``save_track`` returns the SHA-256 of the file for the run manifest.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from taiji_ai.pose.skeleton import NUM_JOINTS, SKELETON_ID
from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.track import TrackMeta
from taiji_ai.store.artifacts import atomic_write_parquet, sha256_file
from taiji_ai.track.state import BEFORE_TARGET, LOST, STATUS_NAMES, TARGET_LOST, TRACKED, TargetTrack

log = logging.getLogger(__name__)

SCHEMA_VERSION = "track/1"
META_KEY = b"taiji_track_meta"
_EPS = 1e-9

# name -> (numpy dtype, shape after the frame axis)
_COLUMNS: dict[str, tuple[np.dtype, tuple[int, ...]]] = {
    "frame_index": (np.dtype(np.int32), ()),
    "t_sec": (np.dtype(np.float64), ()),
    "in_segment": (np.dtype(np.bool_), ()),
    "status": (np.dtype(np.uint8), ()),
    "track_id": (np.dtype(np.int32), ()),
    "person_row": (np.dtype(np.int32), ()),
    "keypoints": (np.dtype(np.float32), (NUM_JOINTS, 2)),
    "scores": (np.dtype(np.float32), (NUM_JOINTS,)),
    "match_cost": (np.dtype(np.float32), ()),
    "match_margin": (np.dtype(np.float32), ()),
    "reattach_cost": (np.dtype(np.float32), ()),
}
_ARROW_TYPES: dict[str, pa.DataType] = {
    "frame_index": pa.int32(),
    "t_sec": pa.float64(),
    "in_segment": pa.bool_(),
    "status": pa.string(),
    "track_id": pa.int32(),
    "person_row": pa.int32(),
    "keypoints": pa.list_(pa.float32(), NUM_JOINTS * 2),
    "scores": pa.list_(pa.float32(), NUM_JOINTS),
    "match_cost": pa.float32(),
    "match_margin": pa.float32(),
    "reattach_cost": pa.float32(),
}
_STATUS_CODE = {name: code for code, name in enumerate(STATUS_NAMES)}


class TrackFileError(Exception):
    """A track file cannot be written or read: damaged, inconsistent, another version, or a failed write."""


def _check_arrays(arrays: dict[str, np.ndarray], meta: TrackMeta) -> None:
    """Dtypes, shapes, the rules of the rows, and the agreement of the header with them. Raises ``TrackFileError``."""
    f = arrays["frame_index"].size
    for name, (dtype, tail) in _COLUMNS.items():
        a = arrays[name]
        if a.dtype != dtype:
            raise TrackFileError(f"{name} has dtype {a.dtype}, expected {dtype}")
        if a.shape != (f, *tail):
            raise TrackFileError(f"{name} has shape {a.shape}, expected {(f, *tail)}")
    if f < 1:
        raise TrackFileError("frame_index must hold at least one frame")
    t_sec, frame_index, status = arrays["t_sec"], arrays["frame_index"], arrays["status"]
    if not np.all(np.isfinite(t_sec)) or np.any(np.diff(t_sec) <= 0):
        raise TrackFileError("t_sec must be finite and strictly increasing")
    if np.any(frame_index < 0) or np.any(np.diff(frame_index) <= 0):
        raise TrackFileError("frame_index must be non-negative and strictly increasing")
    if np.any(status > BEFORE_TARGET):
        raise TrackFileError(f"status has a code above {BEFORE_TARGET}")
    before = np.flatnonzero(status == BEFORE_TARGET)
    if not np.array_equal(before, np.arange(before.size)):
        raise TrackFileError("status: before_target rows must be the first rows, with no other status before them")
    tracked = status == TRACKED
    for name in ("track_id", "person_row"):
        a = arrays[name]
        if np.any(a[tracked] < 0):
            raise TrackFileError(f"{name} is negative on a tracked row")
        if np.any(a[~tracked] != -1):
            raise TrackFileError(f"{name} must be -1 on a row that is not tracked")
    for name in ("keypoints", "scores", "match_cost", "match_margin"):
        if not np.all(np.isnan(arrays[name][~tracked])):
            raise TrackFileError(f"{name} must be NaN on a row that is not tracked (nothing is filled)")
    segment = (t_sec >= meta.segment_s[0] - _EPS) & (t_sec <= meta.segment_s[1] + _EPS)
    if not np.array_equal(segment, arrays["in_segment"]):
        raise TrackFileError("in_segment disagrees with segment_s of the header and t_sec")
    reattached = {e.frame_pos: e.cost for e in meta.events if e.kind == "reattached" and e.cost is not None}
    cost = arrays["reattach_cost"]
    for index in np.flatnonzero(np.isfinite(cost)):
        pos = int(index)
        if pos not in reattached or not tracked[pos] or np.float32(reattached[pos]) != cost[pos]:
            raise TrackFileError(f"reattach_cost is set on frame {pos} without a matching 're-attached' event")
    for pos, event_cost in reattached.items():
        if pos >= f or not tracked[pos] or not np.isfinite(cost[pos]) or np.float32(event_cost) != cost[pos]:
            raise TrackFileError(
                f"the 're-attached' event of frame {pos} has no matching reattach_cost on a tracked row"
            )
    expected = {
        "n_frames": f,
        "n_in_segment": int(segment.sum()),
        "n_tracked": int(tracked.sum()),
        "n_lost": int((status == LOST).sum()),
        "n_target_lost": int((status == TARGET_LOST).sum()),
        "n_before_target": before.size,
    }
    for name, value in expected.items():
        if getattr(meta.counts, name) != value:
            raise TrackFileError(f"the header says {name} = {getattr(meta.counts, name)} but the rows give {value}")
    for e in meta.events:
        if e.frame_pos >= f or e.t_sec != float(t_sec[e.frame_pos]):
            raise TrackFileError(f"events: the event of kind {e.kind} at frame {e.frame_pos} does not match the rows")
    s = meta.selection
    if s.frame_pos >= f or s.frame_index != int(frame_index[s.frame_pos]) or s.t_sec != float(t_sec[s.frame_pos]):
        raise TrackFileError("selection does not match the frame it names")


def _arrays_of(track: TargetTrack) -> dict[str, np.ndarray]:
    return {name: np.asarray(getattr(track, name)) for name in _COLUMNS}


def _table(arrays: dict[str, np.ndarray], meta: TrackMeta) -> pa.Table:
    f = arrays["frame_index"].size
    columns: dict[str, pa.Array] = {}
    for name, (_, tail) in _COLUMNS.items():
        a = arrays[name]
        if name == "status":
            columns[name] = pa.array([STATUS_NAMES[int(code)] for code in a], pa.string())
        elif name in ("keypoints", "scores"):
            width = int(np.prod(tail))
            columns[name] = pa.FixedSizeListArray.from_arrays(
                pa.array(np.ascontiguousarray(a).reshape(f * width)), width
            )
        else:
            columns[name] = pa.array(a)
    table = pa.table(columns, schema=pa.schema(list(_ARROW_TYPES.items())))
    return table.replace_schema_metadata({META_KEY: meta.model_dump_json().encode()})


def save_track(path: Path | str, track: TargetTrack) -> str:
    """Write ``track`` atomically to ``path`` and return the SHA-256 of the written file.

    Raises:
        TrackFileError: the folder of ``path`` does not exist (it is not created), ``track`` breaks a rule of the format
            (nothing is written), or the write failed (the previous file is untouched and no temporary file stays).
    """
    path = Path(path)
    if not path.parent.is_dir():
        raise TrackFileError("the folder of the track file does not exist")
    arrays = _arrays_of(track)
    try:
        meta = parse_manifest(TrackMeta, track.meta.model_dump(mode="json"))
    except ManifestError as exc:
        raise TrackFileError(str(exc)) from exc
    _check_arrays(arrays, meta)
    try:
        atomic_write_parquet(path, _table(arrays, meta))
    except OSError as exc:
        raise TrackFileError("could not write the track file") from exc
    digest = sha256_file(path)
    log.info("track file written for recording %s: %d frames", meta.recording_id, arrays["frame_index"].size)
    return digest


def _check_table(table: pa.Table) -> None:
    expected = list(_ARROW_TYPES)
    names = table.column_names
    missing, extra = [n for n in expected if n not in names], [n for n in names if n not in expected]
    if missing:
        raise TrackFileError(f"the track file lacks the columns {missing}")
    if extra:
        raise TrackFileError(f"the track file has unexpected columns {extra}")
    if names != expected:
        raise TrackFileError(f"the track file has its columns in the wrong order: {names}, expected {expected}")
    for name, want in _ARROW_TYPES.items():
        have = table.schema.field(name).type
        if pa.types.is_fixed_size_list(want):
            ok = (
                pa.types.is_fixed_size_list(have)
                and have.list_size == want.list_size
                and have.value_type == want.value_type
            )
        else:
            ok = have == want
        if not ok:
            raise TrackFileError(f"column {name} has type {have}, expected {want}")
        if table[name].null_count:
            raise TrackFileError(f"column {name} has null values: 'not observed' is NaN, never null")


def _numpy(column: pa.ChunkedArray, name: str) -> np.ndarray:
    dtype, tail = _COLUMNS[name]
    array = column.combine_chunks()
    if tail:
        values = array.flatten().to_numpy(zero_copy_only=False)
        return np.array(values, dtype=dtype).reshape(len(array), *tail)
    return np.array(array.to_numpy(zero_copy_only=False), dtype=dtype)


def _read_v1(table: pa.Table, data: dict[str, Any]) -> TargetTrack:
    try:
        meta = parse_manifest(TrackMeta, data)
    except ManifestError as exc:
        raise TrackFileError(str(exc)) from exc
    if meta.skeleton != SKELETON_ID:
        raise TrackFileError(f"the file is for skeleton {meta.skeleton!r}, this code uses {SKELETON_ID!r}")
    _check_table(table)
    names = table["status"].to_pylist()
    unknown = sorted({n for n in names if n not in _STATUS_CODE})
    if unknown:
        raise TrackFileError(f"status has names that do not exist: {unknown}; valid names are {list(STATUS_NAMES)}")
    arrays = {name: _numpy(table[name], name) for name in _COLUMNS if name != "status"}
    arrays["status"] = np.array([_STATUS_CODE[n] for n in names], dtype=np.uint8)
    _check_arrays(arrays, meta)
    return TargetTrack(**arrays, meta=meta)


# One reader per version: a later version adds a reader here; an old file is never upgraded silently.
_READERS: dict[str, Callable[[pa.Table, dict[str, Any]], TargetTrack]] = {SCHEMA_VERSION: _read_v1}


def load_track(path: Path | str) -> TargetTrack:
    """Read and validate a track file; see the module docstring for the rules.

    Raises:
        TrackFileError: the file is missing, is not a Parquet file of ours, or breaks a rule of its version.
    """
    path = Path(path)
    try:
        table = pq.read_table(path)
    except FileNotFoundError as exc:
        raise TrackFileError("the track file does not exist") from exc
    except (pa.ArrowException, OSError, ValueError) as exc:
        raise TrackFileError("the track file could not be read as a parquet file") from exc
    raw_meta = (table.schema.metadata or {}).get(META_KEY)
    if raw_meta is None:
        raise TrackFileError("the track file has no taiji_track_meta metadata: it is not a track file")
    try:
        data = json.loads(raw_meta)
    except ValueError as exc:
        raise TrackFileError("taiji_track_meta is not valid JSON") from exc
    if not isinstance(data, dict):
        raise TrackFileError("taiji_track_meta is not a JSON object")
    version = data.get("schema_version")
    reader = _READERS.get(version) if isinstance(version, str) else None
    if reader is None:
        raise TrackFileError(f"the track file is version {version!r}; this code reads {sorted(_READERS)}")
    return reader(table, data)
