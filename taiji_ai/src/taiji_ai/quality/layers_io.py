"""Save and load ``pose_masked.npz`` and ``pose_filtered.npz``, the two array layers of W6.

The schemas are ``pose_masked/1`` and ``pose_filtered/1`` (X.29). ``quality.json`` (``quality/quality_io.py``) is the
third output of the stage.

Both archives follow ``pose_raw/1`` (``pose/raw_io.py``): arrays with fixed names and dtypes, a 0-d text array
``schema_version`` that any reader can refuse on, a 0-d text array ``meta_json`` (``schemas/quality_layers.py``), one
reader per version, no pickle, no silent upgrade, an atomic write that returns the SHA-256 of the file. The three
layers stay in three files (AGENTS.md section 5.3). Positions are float32 pixels of the upright image (x right, y
down), times float64 seconds from the stream start; a NaN stays a NaN and keeps its reason: nothing is filled, clipped
or cast.

``pose_masked.npz`` is the **mask layer** on the ``T`` rows of the target track, with the swap flags that were read
from it: ``frame_index`` (T,) int32 (row in ``pts.parquet``, strictly increasing), ``t_sec`` (T,) float64,
``in_segment`` (T,) bool, ``tracked`` (T,) bool, ``keypoints`` (T, 26, 2) float32 (the value, or NaN where ``reason``
is not ``ok``), ``scores`` (T, 26) float32 (the model's, as given), ``reason`` (T, 26) uint8 (0 to 4),
``n_essential_valid`` (T,) int8, ``frame_invalid`` (T,) bool, ``swap_suspect`` and ``swap_blocked`` (T, 26) bool.

``pose_filtered.npz`` is the **final layer on the grid** (``G`` rows: the rows themselves for a constant frame rate)
and the map back to the rows. Grid: ``t_grid`` (G,) float64, ``keypoints`` (G, 26, 2) float32, ``reason`` (G, 26)
uint8 (0 to 6), ``interpolated`` and ``filtered`` (G, 26) bool, ``mixed`` and ``grid_in_segment`` (G,) bool. Rows:
``frame_index``, ``t_sec``, ``in_segment``, ``source_usable`` (T, 26) bool (the cell had a value at the source),
``back_left`` (T,) int32, ``back_weight`` (T,) float64 and ``outside`` (T,) bool (the map back: a row is the grid
value ``back_left`` if the weight is 0, else the mix of it and the next with that weight, and has no value if it is
``outside``). The map is stored, not rebuilt: a file must mean the same after the grid rules change.
``PoseFiltered.on_source`` is ``QualityResult.filtered_on_source``.

**Loading is strict, and a file is checked against itself**: a missing or extra array, a wrong dtype or shape, another
version or skeleton, a header that disagrees with the arrays, and every rule of the layer (the contract of the mask
layer or of the gap layer, the frame rule, the counts of the essential joints, the swap flags inside their pairs, the
segment rows, the map back against the two clocks) is a ``QualityLayerError`` that names the field. The writer checks
the same rules before it writes, so nothing is written that the reader would refuse. A later version adds a reader to
``_READERS``. The bytes of an ``.npz`` are not deterministic (zip timestamps): compare layers with ``equals``, and
record the SHA-256 that ``save_*`` returns. The caller chooses the path; its folder must exist.
"""

from __future__ import annotations

import json
import logging
import zipfile
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from taiji_ai.pose.skeleton import NUM_JOINTS, SKELETON_ID
from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import check_gap_layer, check_layer, frozen
from taiji_ai.quality.chain import QualityResult
from taiji_ai.quality.coverage import segment_grid_rows
from taiji_ai.quality.mask import FRAME_INVALID, NO_FRAME, NOT_TRACKED, OK, frame_invalid_mask
from taiji_ai.quality.resample import values_on_rows
from taiji_ai.schemas._base import ManifestError, parse_manifest
from taiji_ai.schemas.quality_layers import DataSource, PoseFilteredMeta, PoseMaskedMeta
from taiji_ai.store.artifacts import atomic_save_npz, sha256_file

log = logging.getLogger(__name__)

MASKED_VERSION = "pose_masked/1"
FILTERED_VERSION = "pose_filtered/1"
_F32, _F64, _I32, _I8, _U8, _BOOL = (
    np.dtype(t) for t in (np.float32, np.float64, np.int32, np.int8, np.uint8, np.bool_)
)
_MASKED_DTYPES: dict[str, np.dtype] = {
    "frame_index": _I32, "t_sec": _F64, "in_segment": _BOOL, "tracked": _BOOL, "keypoints": _F32, "scores": _F32,
    "reason": _U8, "n_essential_valid": _I8, "frame_invalid": _BOOL, "swap_suspect": _BOOL, "swap_blocked": _BOOL,
}  # fmt: skip
_FILTERED_DTYPES: dict[str, np.dtype] = {
    "t_grid": _F64, "keypoints": _F32, "reason": _U8, "interpolated": _BOOL, "filtered": _BOOL, "mixed": _BOOL,
    "grid_in_segment": _BOOL, "frame_index": _I32, "t_sec": _F64, "in_segment": _BOOL, "source_usable": _BOOL,
    "back_left": _I32, "back_weight": _F64, "outside": _BOOL,
}  # fmt: skip
_MASKED_ALL = frozenset(_MASKED_DTYPES) | {"schema_version", "meta_json"}
_FILTERED_ALL = frozenset(_FILTERED_DTYPES) | {"schema_version", "meta_json"}
_COPY_TOL = 1e-9  # a row "within snap_s" of a grid time: the same float tolerance as the plan of the grid


class QualityLayerError(Exception):
    """A layer file cannot be written or read: damaged, inconsistent, another version or skeleton, or a failed write."""


# --- the layers -------------------------------------------------------------------------------------------------------
def _equal(a: np.ndarray, b: np.ndarray) -> bool:
    return a.dtype == b.dtype and a.shape == b.shape and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")


@dataclass(frozen=True, eq=False)
class PoseMasked:
    """The mask layer of ``T`` rows and its swap flags; every array is read-only (see the module docstring)."""

    frame_index: np.ndarray
    t_sec: np.ndarray
    in_segment: np.ndarray
    tracked: np.ndarray
    keypoints: np.ndarray
    scores: np.ndarray
    reason: np.ndarray
    n_essential_valid: np.ndarray
    frame_invalid: np.ndarray
    swap_suspect: np.ndarray
    swap_blocked: np.ndarray
    meta: PoseMaskedMeta

    def equals(self, other: object) -> bool:
        """Same arrays (NaN equal, same dtype and shape) and same header."""
        return (
            isinstance(other, PoseMasked)
            and all(_equal(getattr(self, n), getattr(other, n)) for n in _MASKED_DTYPES)
            and self.meta == other.meta
        )


@dataclass(frozen=True, eq=False)
class PoseFiltered:
    """The final layer on ``G`` grid rows and the map back to ``T`` rows; every array is read-only."""

    t_grid: np.ndarray
    keypoints: np.ndarray
    reason: np.ndarray
    interpolated: np.ndarray
    filtered: np.ndarray
    mixed: np.ndarray
    grid_in_segment: np.ndarray
    frame_index: np.ndarray
    t_sec: np.ndarray
    in_segment: np.ndarray
    source_usable: np.ndarray
    back_left: np.ndarray
    back_weight: np.ndarray
    outside: np.ndarray
    meta: PoseFilteredMeta

    def equals(self, other: object) -> bool:
        """Same arrays (NaN equal, same dtype and shape) and same header."""
        return (
            isinstance(other, PoseFiltered)
            and all(_equal(getattr(self, n), getattr(other, n)) for n in _FILTERED_DTYPES)
            and self.meta == other.meta
        )

    def on_source(self, values: np.ndarray | None = None) -> np.ndarray:
        """Values on the grid as values on the ``T`` rows of the video (a new read-only array of the same dtype).

        ``values`` is ``(G, 26, ...)`` float and defaults to ``keypoints``. The result is exactly
        ``QualityResult.filtered_on_source()`` for the keypoints and ``QualityResult.grid.to_source(values)`` for
        other values: a copy where a row is on a grid time, the linear mix of the two grid values around it
        otherwise, and no value (NaN) for a row outside the grid or a cell that had no value at the source.
        """
        v = self.keypoints if values is None else np.asarray(values)
        g = len(self.t_grid)
        if v.dtype.kind != "f" or v.ndim < 2 or v.shape[0] != g or v.shape[1] != NUM_JOINTS:
            raise QualityLayerError(
                f"values must be a floating-point array of shape ({g}, {NUM_JOINTS}, ...) like the layer, "
                f"got {v.dtype} {v.shape}"
            )
        out = values_on_rows(v, self.back_left, self.back_weight, self.outside)
        keep = self.source_usable.reshape(self.source_usable.shape + (1,) * (out.ndim - 2))
        out[~np.broadcast_to(keep, out.shape)] = np.nan
        return frozen(out)


# --- the checks (one function for the writer and the reader) ----------------------------------------------------------
def _first_row(bad: np.ndarray) -> int:
    return int(np.argwhere(bad)[0][0])


def _check_dtypes(a: Mapping[str, np.ndarray], dtypes: Mapping[str, np.dtype]) -> None:
    for name, dtype in dtypes.items():
        if a[name].dtype != dtype:
            raise QualityLayerError(f"{name} has dtype {a[name].dtype}, expected {dtype}")


def _check_shapes(a: Mapping[str, np.ndarray], shapes: Mapping[str, tuple[int, ...]]) -> None:
    for name, shape in shapes.items():
        if a[name].shape != shape:
            raise QualityLayerError(f"{name} has shape {a[name].shape}, expected {shape}")


def _check_times(a: Mapping[str, np.ndarray], *names: str) -> None:
    for name in names:
        t = a[name]
        if not np.all(np.isfinite(t)) or np.any(np.diff(t) <= 0):
            raise QualityLayerError(f"{name} must be finite and strictly increasing")


def _check_frame_index(frame_index: np.ndarray) -> None:
    if np.any(frame_index < 0) or np.any(np.diff(frame_index) <= 0):
        raise QualityLayerError("frame_index must be non-negative and strictly increasing")


def _contract(check: Callable[..., Any], *args: Any) -> None:
    try:
        check(*args)
    except QualityError as exc:
        raise QualityLayerError(str(exc)) from exc


def _check_masked(a: Mapping[str, np.ndarray], meta: PoseMaskedMeta) -> int:
    """Check the arrays and the header of a mask layer against each other; returns ``T``.

    Raises ``QualityLayerError``.
    """
    _check_dtypes(a, _MASKED_DTYPES)
    fi = a["frame_index"]
    if fi.ndim != 1 or fi.size < 1:
        raise QualityLayerError(f"frame_index must be a 1-d array of at least one row, got shape {fi.shape}")
    n = fi.size
    _check_shapes(
        a,
        {
            "t_sec": (n,), "in_segment": (n,), "tracked": (n,), "keypoints": (n, NUM_JOINTS, 2),
            "scores": (n, NUM_JOINTS), "reason": (n, NUM_JOINTS), "n_essential_valid": (n,), "frame_invalid": (n,),
            "swap_suspect": (n, NUM_JOINTS), "swap_blocked": (n, NUM_JOINTS),
        },
    )  # fmt: skip
    _check_times(a, "t_sec")
    _check_frame_index(fi)
    if meta.counts.n_rows != n:
        raise QualityLayerError(f"the header says n_rows = {meta.counts.n_rows} but the arrays hold {n} rows")
    keypoints, reason, tracked = a["keypoints"], a["reason"], a["tracked"]
    _contract(check_layer, keypoints, reason, a["t_sec"])  # finite exactly where reason is ok, NaN otherwise
    if reason.max() > FRAME_INVALID:
        row = _first_row(reason > FRAME_INVALID)
        raise QualityLayerError(
            f"reason has a code above {FRAME_INVALID} (row {row}): a mask layer has only the reasons ok, low_conf, "
            "non_finite, not_tracked and frame_invalid"
        )
    bad = ~tracked[:, None] & (reason != NOT_TRACKED)
    if bad.any():
        raise QualityLayerError(
            f"a row that is not tracked must have only not_tracked cells (first: row {_first_row(bad)})"
        )
    bad = tracked[:, None] & (reason == NOT_TRACKED)
    if bad.any():
        raise QualityLayerError(f"a tracked row has a not_tracked cell (first: row {_first_row(bad)})")
    essential = list(meta.mask.essential)
    n_valid = a["n_essential_valid"].astype(np.int64)
    if n_valid.min() < 0 or n_valid.max() > len(essential):
        raise QualityLayerError(f"n_essential_valid must be between 0 and {len(essential)} (the essential joints)")
    usable = (reason == OK) | (reason == FRAME_INVALID)  # a joint that the mask kept, before the frame rule
    counted = np.where(tracked, usable[:, essential].sum(axis=1), 0)
    bad = n_valid != counted
    if bad.any():
        raise QualityLayerError(
            "n_essential_valid does not match reason and the essential joints of the header "
            f"(first: row {_first_row(bad)})"
        )
    invalid = a["frame_invalid"]
    rule = frame_invalid_mask(tracked, counted, len(essential), meta.mask.min_essential_fraction)
    if not np.array_equal(invalid, rule):
        raise QualityLayerError(
            f"frame_invalid does not follow the frame rule of the header (first: row {_first_row(invalid != rule)})"
        )
    bad = invalid[:, None] & (reason == OK)
    if bad.any():
        raise QualityLayerError(f"a frame_invalid row has a cell that is ok (first: row {_first_row(bad)})")
    bad = ~invalid[:, None] & (reason == FRAME_INVALID)
    if bad.any():
        raise QualityLayerError(
            f"reason has a frame_invalid cell in a row that is not frame_invalid (row {_first_row(bad)})"
        )
    suspect, blocked = a["swap_suspect"], a["swap_blocked"]
    bad = suspect & ~blocked
    if bad.any():
        raise QualityLayerError(
            f"swap_suspect has a cell that swap_blocked does not have (first: row {_first_row(bad)})"
        )
    in_pairs = {joint for pair in meta.swap.pairs for joint in pair}
    flagged = {int(j) for j in np.flatnonzero((suspect | blocked).any(axis=0))}
    if flagged - in_pairs:
        raise QualityLayerError(
            f"swap flags are set on joints {sorted(flagged - in_pairs)} that are in no pair of the header"
        )
    return n


def _check_map(a: Mapping[str, np.ndarray], meta: PoseFilteredMeta, g: int, n: int) -> None:
    """The map back against the two clocks (``t_grid`` and ``t_sec``) and the header."""
    t_grid, t_sec = a["t_grid"], a["t_sec"]
    back_left, back_weight, outside = a["back_left"], a["back_weight"], a["outside"]
    if not meta.timeline.resampled:  # the grid is the rows
        for ok, message in (
            (np.array_equal(t_grid, t_sec), "t_grid must equal t_sec for a timeline that was not resampled"),
            (
                np.array_equal(back_left, np.arange(n)),
                f"back_left must be 0 to {n - 1} for a timeline that was not resampled",
            ),
            (not back_weight.any(), "back_weight must be 0 for a timeline that was not resampled"),
            (not outside.any(), "outside must be false for a timeline that was not resampled"),
            (not a["mixed"].any(), "mixed must be false for a timeline that was not resampled"),
        ):
            if not ok:
                raise QualityLayerError(message)
        return
    if back_left.min() < 0 or back_left.max() > g - 1:
        raise QualityLayerError(f"back_left must be a grid row, between 0 and {g - 1}")
    if not np.all(np.isfinite(back_weight)) or back_weight.min() < 0.0 or back_weight.max() >= 1.0:
        raise QualityLayerError("back_weight must be finite and in [0, 1)")
    snap = meta.timeline.snap_s
    expected = (t_grid[0] - t_sec > snap) | (t_sec - t_grid[-1] > snap)  # before the first grid time or after the last
    if not np.array_equal(outside, expected):
        row = _first_row(outside != expected)
        raise QualityLayerError(f"outside does not match the clocks and snap_s (first: row {row})")
    if (outside & (back_weight != 0.0)).any():
        raise QualityLayerError(
            f"an outside row must have back_weight 0 (first: row {_first_row(outside & (back_weight != 0.0))})"
        )
    inside = ~outside
    copy = inside & (back_weight == 0.0)
    bad = copy & (np.abs(t_sec - t_grid[back_left]) > snap * (1.0 + _COPY_TOL) + 1e-12)
    if bad.any():
        raise QualityLayerError(
            f"back_weight is 0 but t_sec is not within snap_s of its grid time (first: row {_first_row(bad)})"
        )
    mix = inside & (back_weight > 0.0)
    if mix.any():
        left = back_left[mix]
        if (left + 1 > g - 1).any():
            raise QualityLayerError("back_left + 1 must be a grid row for a row that has a back_weight")
        low, high, t = t_grid[left], t_grid[left + 1], t_sec[mix]
        good = (low < t) & (t < high) & np.isclose(back_weight[mix], (t - low) / (high - low), rtol=1e-6, atol=1e-9)
        if not good.all():
            row = int(np.flatnonzero(mix)[np.flatnonzero(~good)[0]])
            raise QualityLayerError(
                f"back_weight does not match the time of the row between its grid times (first: row {row})"
            )


def _check_filtered(a: Mapping[str, np.ndarray], meta: PoseFilteredMeta) -> tuple[int, int]:
    """Check the arrays and the header of a filtered layer against each other; returns ``(G, T)``."""
    _check_dtypes(a, _FILTERED_DTYPES)
    t_grid, fi = a["t_grid"], a["frame_index"]
    for name, array in (("t_grid", t_grid), ("frame_index", fi)):
        if array.ndim != 1 or array.size < 1:
            raise QualityLayerError(f"{name} must be a 1-d array of at least one row, got shape {array.shape}")
    g, n = t_grid.size, fi.size
    _check_shapes(
        a,
        {
            "keypoints": (g, NUM_JOINTS, 2), "reason": (g, NUM_JOINTS), "interpolated": (g, NUM_JOINTS),
            "filtered": (g, NUM_JOINTS), "mixed": (g,), "grid_in_segment": (g,), "t_sec": (n,), "in_segment": (n,),
            "source_usable": (n, NUM_JOINTS), "back_left": (n,), "back_weight": (n,), "outside": (n,),
        },
    )  # fmt: skip
    _check_times(a, "t_grid", "t_sec")
    _check_frame_index(fi)
    if meta.timeline.n_rows != n:
        raise QualityLayerError(f"the header says n_rows = {meta.timeline.n_rows} but the arrays hold {n} rows")
    if meta.timeline.n_grid_rows != g:
        raise QualityLayerError(
            f"the header says n_grid_rows = {meta.timeline.n_grid_rows} but the arrays hold {g} grid rows"
        )
    _contract(check_gap_layer, a["keypoints"], a["reason"], a["interpolated"], t_grid)
    reason = a["reason"]
    if reason.max() > NO_FRAME:
        raise QualityLayerError(f"reason has a code above {NO_FRAME} (row {_first_row(reason > NO_FRAME)})")
    has_value = ~np.isnan(a["keypoints"][..., 0])
    bad = a["filtered"] & ~has_value
    if bad.any():
        raise QualityLayerError(f"filtered is set on a cell that has no value (first: row {_first_row(bad)})")
    _check_map(a, meta, g, n)
    rows = segment_grid_rows(t_grid, a["t_sec"], a["in_segment"])
    if not np.array_equal(a["grid_in_segment"], rows):
        raise QualityLayerError(
            "grid_in_segment does not match the segment of in_segment and t_sec "
            f"(first: grid row {_first_row(a['grid_in_segment'] != rows)})"
        )
    if int(a["mixed"].sum()) != meta.counts.n_mixed_rows:
        raise QualityLayerError(
            f"the header says n_mixed_rows = {meta.counts.n_mixed_rows} but mixed has {int(a['mixed'].sum())}"
        )
    if int(a["filtered"].sum()) != meta.counts.n_filtered_cells:
        raise QualityLayerError(
            f"the header says n_filtered_cells = {meta.counts.n_filtered_cells} "
            f"but filtered has {int(a['filtered'].sum())}"
        )
    return g, n


# --- building a layer from the result of the chain --------------------------------------------------------------------
def _float32(name: str, array: np.ndarray) -> np.ndarray:
    if array.dtype != _F32:
        raise QualityLayerError(
            f"{name} has dtype {array.dtype}, expected float32: the layers are stored as float32 like pose_raw/1, "
            "and a cast would change values"
        )
    return array


def _frame_index(value: object, n: int) -> np.ndarray:
    fi = np.asarray(value)
    if fi.dtype.kind not in "iu":
        raise QualityLayerError(f"frame_index must be an integer array, got {fi.dtype}")
    if fi.shape != (n,):
        raise QualityLayerError(f"frame_index has shape {fi.shape}, expected ({n},) like the layer")
    if fi.min() < 0 or fi.max() > np.iinfo(np.int32).max:
        raise QualityLayerError("frame_index must be between 0 and 2**31 - 1")
    if np.any(np.diff(fi.astype(np.int64)) <= 0):
        raise QualityLayerError("frame_index must be strictly increasing")
    return fi.astype(np.int32)


def _meta[M](cls: type[M], header: dict[str, Any]) -> M:
    try:
        return parse_manifest(cls, header)  # type: ignore[type-var,return-value]
    except ManifestError as exc:
        raise QualityLayerError(str(exc)) from exc


def _prepare(result: object, frame_index: object) -> tuple[QualityResult, int, np.ndarray]:
    if not isinstance(result, QualityResult):
        raise TypeError(f"result must be a QualityResult, got {type(result).__name__}")
    n = len(result.t_sec)
    if n == 0:
        raise QualityLayerError("the layer has no rows: a file needs at least one frame")
    return result, n, _frame_index(frame_index, n)


def _sources(data_sources: Sequence[DataSource]) -> list[dict[str, str]]:
    return [s.model_dump() if isinstance(s, DataSource) else s for s in data_sources]  # type: ignore[misc]


def pose_masked_from_result(
    result: QualityResult,
    *,
    recording_id: str,
    frame_index: np.ndarray,
    data_sources: Sequence[DataSource] = (),
) -> PoseMasked:
    """The mask layer and the swap flags of a ``QualityResult`` as a ``PoseMasked`` (read-only copies, checked).

    ``frame_index`` ``(T,)`` integers: the row of each frame in ``pts.parquet`` (``TargetTrack.frame_index``), strictly
    increasing; ``QualityResult`` has none. ``data_sources``: see ``schemas.quality_layers``. Raises ``TypeError`` for
    anything that is not a ``QualityResult`` and ``QualityLayerError`` for a layer that cannot be stored (no row, a
    layer that is not float32, a bad ``frame_index`` or ``recording_id``).
    """
    r, n, fi = _prepare(result, frame_index)
    m = r.mask
    params = r.report.params
    if m.n_essential_valid.min() < 0 or m.n_essential_valid.max() > NUM_JOINTS:
        raise QualityLayerError("n_essential_valid must be between 0 and 26")
    meta = _meta(
        PoseMaskedMeta,
        {
            "schema_version": MASKED_VERSION, "skeleton": SKELETON_ID, "recording_id": recording_id,
            "mask": params.mask.model_dump(), "swap": params.swap.model_dump(), "counts": {"n_rows": n},
            "data_sources": _sources(data_sources),
        },
    )  # fmt: skip
    layer = PoseMasked(
        frame_index=frozen(fi),
        t_sec=frozen(np.array(r.t_sec, dtype=np.float64)),
        in_segment=frozen(np.array(r.in_segment, dtype=np.bool_)),
        tracked=frozen(np.array(m.tracked, dtype=np.bool_)),
        keypoints=frozen(np.array(_float32("keypoints", m.keypoints), copy=True)),
        scores=frozen(np.array(_float32("scores", m.scores), copy=True)),
        reason=frozen(np.array(m.reason, dtype=np.uint8)),
        n_essential_valid=frozen(np.array(m.n_essential_valid, dtype=np.int8)),
        frame_invalid=frozen(np.array(m.frame_invalid, dtype=np.bool_)),
        swap_suspect=frozen(np.array(r.swap.suspect, dtype=np.bool_)),
        swap_blocked=frozen(np.array(r.swap.blocked, dtype=np.bool_)),
        meta=meta,
    )
    _check_masked(_arrays_of(layer, _MASKED_DTYPES), meta)
    return layer


def pose_filtered_from_result(
    result: QualityResult,
    *,
    recording_id: str,
    frame_index: np.ndarray,
    data_sources: Sequence[DataSource] = (),
) -> PoseFiltered:
    """The final layer, its grid and the map back of a ``QualityResult`` as a ``PoseFiltered`` (copies, checked).

    Arguments and errors as ``pose_masked_from_result``.
    """
    r, n, fi = _prepare(result, frame_index)
    grid, gm, fl, tl = r.grid, r.grid.gridmap, r.filtered, r.report.timeline
    meta = _meta(
        PoseFilteredMeta,
        {
            "schema_version": FILTERED_VERSION, "skeleton": SKELETON_ID, "recording_id": recording_id,
            "params": r.report.params.model_dump(),
            "timeline": {
                "n_rows": n, "n_grid_rows": len(gm.t_grid), "resampled": gm.resampled, "step_s": tl.step_s,
                "sampling_hz": tl.sampling_hz, "snap_s": float(gm.snap_s),
            },
            "counts": {"n_mixed_rows": int(grid.mixed.sum()), "n_filtered_cells": int(fl.filtered.sum())},
            "data_sources": _sources(data_sources),
        },
    )  # fmt: skip
    layer = PoseFiltered(
        t_grid=frozen(np.array(gm.t_grid, dtype=np.float64)),
        keypoints=frozen(np.array(_float32("keypoints", fl.keypoints), copy=True)),
        reason=frozen(np.array(fl.reason, dtype=np.uint8)),
        interpolated=frozen(np.array(fl.interpolated, dtype=np.bool_)),
        filtered=frozen(np.array(fl.filtered, dtype=np.bool_)),
        mixed=frozen(np.array(grid.mixed, dtype=np.bool_)),
        grid_in_segment=frozen(segment_grid_rows(gm.t_grid, r.t_sec, r.in_segment)),
        frame_index=frozen(fi),
        t_sec=frozen(np.array(r.t_sec, dtype=np.float64)),
        in_segment=frozen(np.array(r.in_segment, dtype=np.bool_)),
        source_usable=frozen(np.array(grid.source_usable, dtype=np.bool_)),
        back_left=frozen(np.array(gm.back_left, dtype=np.int32)),
        back_weight=frozen(np.array(gm.back_weight, dtype=np.float64)),
        outside=frozen(np.array(gm.before | gm.beyond, dtype=np.bool_)),
        meta=meta,
    )
    _check_filtered(_arrays_of(layer, _FILTERED_DTYPES), meta)
    return layer


def _arrays_of(layer: object, names: Mapping[str, np.dtype]) -> dict[str, np.ndarray]:
    return {name: np.asarray(getattr(layer, name)) for name in names}


# --- writing and reading ----------------------------------------------------------------------------------------------
def _write(path: Path | str, arrays: dict[str, np.ndarray], version: str, meta_json: str) -> str:
    path = Path(path)
    if not path.parent.is_dir():
        raise QualityLayerError("the folder of the layer file does not exist")
    try:
        atomic_save_npz(path, **arrays, schema_version=np.array(version), meta_json=np.array(meta_json))
    except OSError as exc:
        raise QualityLayerError("could not write the layer file") from exc
    return sha256_file(path)


def save_pose_masked(path: Path | str, layer: PoseMasked) -> str:
    """Write ``layer`` atomically to ``path`` and return the SHA-256 of the written file.

    Raises ``TypeError`` for anything that is not a ``PoseMasked``; ``QualityLayerError`` if the folder of ``path`` does
    not exist (it is not created), if the layer breaks a rule of the format (nothing is written) or if the write failed
    (the previous file is untouched and no temporary file stays).
    """
    if not isinstance(layer, PoseMasked):
        raise TypeError(f"layer must be a PoseMasked, got {type(layer).__name__}")
    arrays = _arrays_of(layer, _MASKED_DTYPES)
    n = _check_masked(arrays, layer.meta)
    digest = _write(path, arrays, MASKED_VERSION, layer.meta.model_dump_json())
    log.info("masked layer written for recording %s: %d rows", layer.meta.recording_id, n)
    return digest


def save_pose_filtered(path: Path | str, layer: PoseFiltered) -> str:
    """Write ``layer`` atomically to ``path`` and return the SHA-256 of the file; errors as ``save_pose_masked``."""
    if not isinstance(layer, PoseFiltered):
        raise TypeError(f"layer must be a PoseFiltered, got {type(layer).__name__}")
    arrays = _arrays_of(layer, _FILTERED_DTYPES)
    g, n = _check_filtered(arrays, layer.meta)
    digest = _write(path, arrays, FILTERED_VERSION, layer.meta.model_dump_json())
    log.info("filtered layer written for recording %s: %d grid rows, %d rows", layer.meta.recording_id, g, n)
    return digest


def _header(arrays: dict[str, np.ndarray], cls: type[Any]) -> Any:
    try:
        data = json.loads(str(arrays["meta_json"]))
    except ValueError as exc:
        raise QualityLayerError("meta_json is not valid JSON") from exc
    return _meta(cls, data)


def _read_masked_v1(arrays: dict[str, np.ndarray]) -> PoseMasked:
    missing, extra = sorted(_MASKED_ALL - set(arrays)), sorted(set(arrays) - _MASKED_ALL)
    if missing:
        raise QualityLayerError(f"the masked file lacks the arrays {missing}")
    if extra:
        raise QualityLayerError(f"the masked file has unexpected arrays {extra}")
    meta: PoseMaskedMeta = _header(arrays, PoseMaskedMeta)
    if meta.skeleton != SKELETON_ID:
        raise QualityLayerError(f"the file is for skeleton {meta.skeleton!r}, this code uses {SKELETON_ID!r}")
    _check_masked(arrays, meta)
    return PoseMasked(**{name: frozen(arrays[name]) for name in _MASKED_DTYPES}, meta=meta)


def _read_filtered_v1(arrays: dict[str, np.ndarray]) -> PoseFiltered:
    missing, extra = sorted(_FILTERED_ALL - set(arrays)), sorted(set(arrays) - _FILTERED_ALL)
    if missing:
        raise QualityLayerError(f"the filtered file lacks the arrays {missing}")
    if extra:
        raise QualityLayerError(f"the filtered file has unexpected arrays {extra}")
    meta: PoseFilteredMeta = _header(arrays, PoseFilteredMeta)
    if meta.skeleton != SKELETON_ID:
        raise QualityLayerError(f"the file is for skeleton {meta.skeleton!r}, this code uses {SKELETON_ID!r}")
    _check_filtered(arrays, meta)
    return PoseFiltered(**{name: frozen(arrays[name]) for name in _FILTERED_DTYPES}, meta=meta)


# One reader per version: a later version adds a reader here; an old file is never upgraded silently.
_MASKED_READERS: dict[str, Callable[[dict[str, np.ndarray]], PoseMasked]] = {MASKED_VERSION: _read_masked_v1}
_FILTERED_READERS: dict[str, Callable[[dict[str, np.ndarray]], PoseFiltered]] = {FILTERED_VERSION: _read_filtered_v1}


def _load[L](path: Path | str, readers: Mapping[str, Callable[[dict[str, np.ndarray]], L]], what: str) -> L:
    path = Path(path)
    try:
        with np.load(path, allow_pickle=False) as archive:
            if "schema_version" not in archive.files:
                raise QualityLayerError(f"the file has no schema_version array: it is not a {what} file")
            version = str(archive["schema_version"])
            reader = readers.get(version)
            if reader is None:
                raise QualityLayerError(f"the file is version {version!r}; this reader reads {sorted(readers)}")
            arrays = {name: archive[name] for name in archive.files}
    except QualityLayerError:
        raise
    except (OSError, ValueError, EOFError, zipfile.BadZipFile, zlib.error) as exc:
        raise QualityLayerError(f"the {what} file could not be read as an .npz archive") from exc
    return reader(arrays)


def load_pose_masked(path: Path | str) -> PoseMasked:
    """Read and validate ``pose_masked.npz``; see the module docstring for the rules.

    Raises ``QualityLayerError``: the file is missing, is not an archive of ours, or breaks a rule of its version (the
    field is named).
    """
    return _load(path, _MASKED_READERS, "pose_masked")


def load_pose_filtered(path: Path | str) -> PoseFiltered:
    """Read and validate ``pose_filtered.npz``; errors as ``load_pose_masked``."""
    return _load(path, _FILTERED_READERS, "pose_filtered")
