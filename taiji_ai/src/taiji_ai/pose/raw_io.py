"""Save and load ``pose_raw.npz``, the raw pose of a segment (schema ``pose_raw/1``, P3.03).

The archive has nine arrays, all with fixed names and dtypes (the raw layer: AGENTS.md section 5.3):

* ``frame_index`` (F,) int32: row of each frame in ``pts.parquet``, strictly increasing;
* ``t_sec`` (F,) float64: seconds from the stream start (real PTS), strictly increasing;
* ``person_offsets`` (F + 1,) int64: persons of frame ``i`` are rows ``[i]:[i + 1]``; starts at 0, never decreases,
  ends at D;
* ``bboxes`` (D, 4) float32: xyxy [px];
* ``keypoints`` (D, 26, 2) float32: x y [px] of the upright image, y down, exactly as the model returned them;
* ``scores`` (D, 26) float32: the model's scores;
* ``from_detector`` (D,) bool: the box came from the detector (True) or from the previous keypoints (False);
* ``schema_version`` () text: ``"pose_raw/1"``, read first so that any reader can refuse another version;
* ``meta_json`` () text: ``taiji_ai.schemas.pose.PoseRawMeta`` as JSON (no path, no file name).

Keypoints and scores are never validated for range, clamped or filled: NaN stays NaN. Loading is strict: a missing or
extra array, a wrong dtype or shape, inconsistent counts, another schema version or another skeleton is a
``PoseRawError`` that names the field. A later version adds a reader to ``_READERS``; an old file is never upgraded
silently. The wall clock of the run is not stored (it belongs to the run manifest): ``PoseRunStats.elapsed_s`` is
``None`` after a load.

The bytes of an ``.npz`` are not deterministic (zip timestamps): compare poses with ``PoseRaw.equals``, and record the
SHA-256 that ``save_pose_raw`` returns for the file that was written. The caller chooses the path; its folder must
exist.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import zipfile
import zlib
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np

from taiji_ai.pose.runner import PoseRaw, PoseRunParams, PoseRunStats
from taiji_ai.pose.skeleton import NUM_JOINTS, SKELETON_ID
from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.pose import PoseRawMeta
from taiji_ai.store.artifacts import atomic_save_npz, sha256_file

log = logging.getLogger(__name__)

SCHEMA_VERSION = "pose_raw/1"
_DATA_DTYPES: dict[str, np.dtype] = {
    "frame_index": np.dtype(np.int32),
    "t_sec": np.dtype(np.float64),
    "person_offsets": np.dtype(np.int64),
    "bboxes": np.dtype(np.float32),
    "keypoints": np.dtype(np.float32),
    "scores": np.dtype(np.float32),
    "from_detector": np.dtype(np.bool_),
}
_ALL_ARRAYS = frozenset(_DATA_DTYPES) | {"schema_version", "meta_json"}


class PoseRawError(Exception):
    """A pose file cannot be written or read: damaged, inconsistent, another version or skeleton, or a failed write."""


def _check_arrays(arrays: Mapping[str, np.ndarray]) -> tuple[int, int]:
    """Check dtypes, shapes and consistency of the seven data arrays; returns ``(F, D)``. Raises ``PoseRawError``."""
    for name, dtype in _DATA_DTYPES.items():
        if arrays[name].dtype != dtype:
            raise PoseRawError(f"{name} has dtype {arrays[name].dtype}, expected {dtype}")
    frame_index, t_sec, offsets = arrays["frame_index"], arrays["t_sec"], arrays["person_offsets"]
    if frame_index.ndim != 1 or frame_index.size < 1:
        raise PoseRawError(f"frame_index must be a 1-d array of at least one frame, got shape {frame_index.shape}")
    f = frame_index.size
    if t_sec.shape != (f,):
        raise PoseRawError(f"t_sec has shape {t_sec.shape}, expected ({f},) like frame_index")
    if offsets.shape != (f + 1,):
        raise PoseRawError(f"person_offsets has shape {offsets.shape}, expected ({f + 1},)")
    if offsets[0] != 0:
        raise PoseRawError(f"person_offsets must start at 0, starts at {int(offsets[0])}")
    if np.any(np.diff(offsets) < 0):
        raise PoseRawError("person_offsets decreases")
    d = int(offsets[-1])
    expected = {"bboxes": (d, 4), "keypoints": (d, NUM_JOINTS, 2), "scores": (d, NUM_JOINTS), "from_detector": (d,)}
    for name, shape in expected.items():
        if arrays[name].shape != shape:
            raise PoseRawError(f"{name} has shape {arrays[name].shape}, expected {shape}: person_offsets ends at {d}")
    if not np.all(np.isfinite(t_sec)) or np.any(np.diff(t_sec) <= 0):
        raise PoseRawError("t_sec must be finite and strictly increasing")
    if np.any(frame_index < 0) or np.any(np.diff(frame_index) <= 0):
        raise PoseRawError("frame_index must be non-negative and strictly increasing")
    return f, d


def save_pose_raw(path: Path | str, raw: PoseRaw) -> str:
    """Write ``raw`` atomically to ``path`` and return the SHA-256 of the written file.

    Raises:
        PoseRawError: the folder of ``path`` does not exist (it is not created), ``raw`` breaks the rules of the format
            (nothing is written), or the write failed (the previous file is untouched and no temporary file stays).
    """
    path = Path(path)
    if not path.parent.is_dir():
        raise PoseRawError("the folder of the pose file does not exist")
    arrays = {name: np.asarray(getattr(raw, name)) for name in _DATA_DTYPES}
    f, d = _check_arrays(arrays)
    if raw.stats.n_frames != f:
        raise PoseRawError(f"stats.n_frames is {raw.stats.n_frames} but the arrays hold {f} frames")
    if raw.stats.n_persons_total != d:
        raise PoseRawError(f"stats.n_persons_total is {raw.stats.n_persons_total} but the arrays hold {d} persons")
    header = {
        "schema_version": SCHEMA_VERSION,
        "skeleton": SKELETON_ID,
        "recording_id": raw.recording_id,
        "image_size": list(raw.image_size),
        "display_rotation": raw.display_rotation,
        "segment_s": list(raw.segment_s),
        "params": dataclasses.asdict(raw.params),
        "model_fingerprint": dict(raw.model_fingerprint),
        "providers": dict(raw.providers),
        "counts": {
            "n_frames": raw.stats.n_frames,
            "n_detector_calls": raw.stats.n_detector_calls,
            "n_pose_calls": raw.stats.n_pose_calls,
            "n_persons_total": raw.stats.n_persons_total,
        },
    }
    try:
        meta = parse_manifest(PoseRawMeta, header)
    except ManifestError as exc:
        raise PoseRawError(str(exc)) from exc
    try:
        atomic_save_npz(
            path, **arrays, schema_version=np.array(SCHEMA_VERSION), meta_json=np.array(meta.model_dump_json())
        )
    except OSError as exc:
        raise PoseRawError("could not write the pose file") from exc
    digest = sha256_file(path)
    log.info("pose file written for recording %s: %d frames, %d persons", raw.recording_id, f, d)
    return digest


def _read_v1(arrays: dict[str, np.ndarray]) -> PoseRaw:
    missing, extra = sorted(_ALL_ARRAYS - set(arrays)), sorted(set(arrays) - _ALL_ARRAYS)
    if missing:
        raise PoseRawError(f"the pose file lacks the arrays {missing}")
    if extra:
        raise PoseRawError(f"the pose file has unexpected arrays {extra}")
    try:
        data = json.loads(str(arrays["meta_json"]))
    except ValueError as exc:
        raise PoseRawError("meta_json is not valid JSON") from exc
    try:
        meta = parse_manifest(PoseRawMeta, data)
    except ManifestError as exc:
        raise PoseRawError(str(exc)) from exc
    if meta.skeleton != SKELETON_ID:
        raise PoseRawError(f"the file is for skeleton {meta.skeleton!r}, this code uses {SKELETON_ID!r}")
    f, d = _check_arrays(arrays)
    if meta.counts.n_frames != f:
        raise PoseRawError(f"the header says n_frames = {meta.counts.n_frames} but the arrays hold {f} frames")
    if meta.counts.n_persons_total != d:
        raise PoseRawError(
            f"the header says n_persons_total = {meta.counts.n_persons_total} but the arrays hold {d} persons"
        )
    return PoseRaw(
        recording_id=meta.recording_id,
        frame_index=arrays["frame_index"],
        t_sec=arrays["t_sec"],
        person_offsets=arrays["person_offsets"],
        bboxes=arrays["bboxes"],
        keypoints=arrays["keypoints"],
        scores=arrays["scores"],
        from_detector=arrays["from_detector"],
        image_size=(int(meta.image_size[0]), int(meta.image_size[1])),
        display_rotation=meta.display_rotation,
        segment_s=(float(meta.segment_s[0]), float(meta.segment_s[1])),
        params=PoseRunParams(**meta.params.model_dump()),
        model_fingerprint=dict(meta.model_fingerprint),
        providers=dict(meta.providers),
        stats=PoseRunStats(
            n_frames=meta.counts.n_frames,
            n_detector_calls=meta.counts.n_detector_calls,
            n_pose_calls=meta.counts.n_pose_calls,
            n_persons_total=meta.counts.n_persons_total,
            elapsed_s=None,
        ),
    )


# One reader per version: a later version adds a reader here; an old file is never upgraded silently.
_READERS: dict[str, Callable[[dict[str, np.ndarray]], PoseRaw]] = {SCHEMA_VERSION: _read_v1}


def load_pose_raw(path: Path | str) -> PoseRaw:
    """Read and validate a pose file; see the module docstring for the rules.

    Raises:
        PoseRawError: the file is missing, is not an archive of ours, or breaks a rule of its version (field named).
    """
    path = Path(path)
    try:
        with np.load(path, allow_pickle=False) as archive:
            if "schema_version" not in archive.files:
                raise PoseRawError("the file has no schema_version array: it is not a pose_raw file")
            version = str(archive["schema_version"])
            reader = _READERS.get(version)
            if reader is None:
                raise PoseRawError(f"the pose file is version {version!r}; this code reads {sorted(_READERS)}")
            arrays = {name: archive[name] for name in archive.files}
    except PoseRawError:
        raise
    except (OSError, ValueError, EOFError, zipfile.BadZipFile, zlib.error) as exc:
        raise PoseRawError("the pose file could not be read as an .npz archive") from exc
    return reader(arrays)
