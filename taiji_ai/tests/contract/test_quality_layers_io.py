"""T-QLT-13b..h: save and load of ``pose_masked.npz`` and ``pose_filtered.npz`` (schemas ``pose_masked/1``,
``pose_filtered/1``, X.29).

The layers come from the real chain (``run_quality_arrays``) on clocks built by hand: fixture F1 (every class of cell
and a swap, a constant frame rate: the grid is the rows), a clock with dropped frames and a pause (resampled), a
jittered clock (mixed rows with real weights) and a clock whose first row is off the lattice (a row before the grid).
No video, no model.
"""

from __future__ import annotations

import dataclasses
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from helpers.quality_fixtures import build_f1, static_pose
from helpers.synth import vfr_times
from taiji_ai.pose.skeleton import IDX
from taiji_ai.quality.chain import QualityResult, run_quality_arrays
from taiji_ai.quality.layers_io import (
    PoseFiltered,
    PoseMasked,
    QualityLayerError,
    load_pose_filtered,
    load_pose_masked,
    pose_filtered_from_result,
    pose_masked_from_result,
    save_pose_filtered,
    save_pose_masked,
)
from taiji_ai.schemas.quality_layers import DataSource
from taiji_ai.store import artifacts
from taiji_ai.store.artifacts import sha256_file

RECORDING_ID = "0b6f3c1e-5a2d-4f8e-9c3a-7d1e2b4a6c80"
SOURCES = (DataSource(dataset_id="D08", license="own recordings"),)
MASKED_ARRAYS = (
    "frame_index", "t_sec", "in_segment", "tracked", "keypoints", "scores", "reason", "n_essential_valid",
    "frame_invalid", "swap_suspect", "swap_blocked",
)  # fmt: skip
FILTERED_ARRAYS = (
    "t_grid", "keypoints", "reason", "interpolated", "filtered", "mixed", "grid_in_segment", "frame_index", "t_sec",
    "in_segment", "source_usable", "back_left", "back_weight", "outside",
)  # fmt: skip


# --- builders ---------------------------------------------------------------------------------------------------------
def moving(t: np.ndarray):
    """A person who moves on a straight line (40 px/s in x, 25 px/s in y); scores 0.95; float32."""
    kp = static_pose(len(t)).astype(np.float64)
    kp[..., 0] += 40.0 * t[:, None]
    kp[..., 1] += 25.0 * t[:, None]
    return kp.astype(np.float32), np.full((len(t), 26), 0.95, dtype=np.float32)


def margins(n: int, k: int = 3) -> np.ndarray:
    seg = np.ones(n, dtype=bool)
    seg[:k] = False
    seg[-k:] = False
    return seg


def scenario(name: str) -> QualityResult:
    """The result of the chain for one clock; ``frame_index`` is ``frame_index_of(result)``."""
    if name == "f1":  # 60 rows at 30 fps: constant rate, every class of cell, a swap in rows 34 and 35
        t, kp, score, tracked, in_segment = build_f1()
        return run_quality_arrays(kp, score, t, tracked=tracked, in_segment=in_segment)
    if name == "dropped":  # two dropped frames and a pause of 0.37 s: resampled, with `no_frame` cells
        t = np.delete(np.arange(150) / 30.0, [40, 41, *range(80, 91)])
        kp, score = moving(t)
        return run_quality_arrays(kp, score, t, in_segment=margins(len(t)))
    if name == "jitter":  # every interval 30 % off: most grid times are mixes with real weights
        t = vfr_times(5.0, 30.0, jitter_frac=0.3, rng=np.random.default_rng(2))
        kp, score = moving(t)
        return run_quality_arrays(kp, score, t, in_segment=margins(len(t)))
    if name == "lattice":  # the first row is 3 ms late for its place on the lattice: it is before the grid
        t = np.concatenate([[0.003], np.delete(np.arange(1, 200) / 30.0, 60)])
        kp, score = moving(t)
        score[100:110, 5] = 0.0  # a hole of 0.33 s: too long to bridge, so a cell with no value at the source
        score[150, 7] = 0.0  # a hole of one cell: bridged, so the layer holds a bridged cell too
        return run_quality_arrays(kp, score, t, in_segment=margins(len(t)))
    raise AssertionError(name)


SCENARIOS = ("f1", "dropped", "jitter", "lattice")


def frame_index_of(result: QualityResult) -> np.ndarray:
    return np.arange(len(result.t_sec), dtype=np.int64) * 2 + 7  # not 0..T-1: the writer must not assume it


def masked_layer(result: QualityResult) -> PoseMasked:
    return pose_masked_from_result(
        result, recording_id=RECORDING_ID, frame_index=frame_index_of(result), data_sources=SOURCES
    )


def filtered_layer(result: QualityResult) -> PoseFiltered:
    return pose_filtered_from_result(
        result, recording_id=RECORDING_ID, frame_index=frame_index_of(result), data_sources=SOURCES
    )


def same(a: np.ndarray, b: np.ndarray) -> bool:
    return a.dtype == b.dtype and a.shape == b.shape and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")


def arrays_of(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def damage(
    path: Path,
    arrays: Callable[[dict[str, np.ndarray]], None] | None = None,
    meta: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Change the archive behind the writer's back: ``arrays`` edits the arrays in place, ``meta`` the header."""
    data = arrays_of(path)
    if arrays is not None:
        arrays(data)
    if meta is not None:
        header = json.loads(str(data["meta_json"]))
        meta(header)
        data["meta_json"] = np.array(json.dumps(header))
    np.savez_compressed(path, **data)


@pytest.fixture(scope="module")
def results() -> dict[str, QualityResult]:
    return {name: scenario(name) for name in SCENARIOS}


@pytest.fixture
def make_masked(tmp_path: Path, results):
    def make(name: str = "f1") -> Path:
        path = tmp_path / f"pose_masked_{name}.npz"
        save_pose_masked(path, masked_layer(results[name]))
        return path

    return make


@pytest.fixture
def make_filtered(tmp_path: Path, results):
    def make(name: str = "f1") -> Path:
        path = tmp_path / f"pose_filtered_{name}.npz"
        save_pose_filtered(path, filtered_layer(results[name]))
        return path

    return make


def test_t_qlt_13_the_scenarios_hold_what_the_tests_below_need(results):
    f1, dropped, jitter, lattice = (results[n] for n in SCENARIOS)
    assert not f1.grid.gridmap.resampled and f1.swap.blocked.any() and f1.mask.frame_invalid.any()
    assert (~f1.mask.tracked).any() and (~f1.in_segment).any()
    assert dropped.grid.gridmap.resampled and dropped.grid.gridmap.stall.any()
    assert jitter.grid.gridmap.resampled and (jitter.grid.gridmap.weight > 0).sum() > 50
    g = lattice.grid.gridmap
    assert g.resampled and g.before.tolist()[:2] == [True, False] and lattice.grid.interpolated.any()
    for r in results.values():
        assert r.mask.keypoints.dtype == np.float32 and r.filtered.keypoints.dtype == np.float32


# --- T-QLT-13b: the masked layer round trip ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", SCENARIOS)
def test_t_qlt_13b_a_saved_masked_layer_comes_back_identical(make_masked, results, name: str):
    result = results[name]
    layer = masked_layer(result)
    loaded = load_pose_masked(make_masked(name))
    assert loaded.equals(layer)
    for field in MASKED_ARRAYS:
        assert same(getattr(loaded, field), getattr(layer, field)), field
        assert not getattr(loaded, field).flags.writeable
    assert loaded.meta == layer.meta
    assert loaded.meta.recording_id == RECORDING_ID and loaded.meta.data_sources == SOURCES
    assert loaded.meta.counts.n_rows == len(result.t_sec)


@pytest.mark.parametrize("name", SCENARIOS)
def test_t_qlt_13b_the_masked_layer_is_the_mask_layer_of_the_chain_and_the_swap_flags(results, name: str):
    r = results[name]
    m = masked_layer(r)
    assert same(m.keypoints, r.mask.keypoints) and same(m.scores, r.mask.scores) and same(m.reason, r.mask.reason)
    assert np.array_equal(m.tracked, r.mask.tracked) and np.array_equal(m.frame_invalid, r.mask.frame_invalid)
    assert np.array_equal(m.n_essential_valid, r.mask.n_essential_valid) and m.n_essential_valid.dtype == np.int8
    assert np.array_equal(m.swap_suspect, r.swap.suspect) and np.array_equal(m.swap_blocked, r.swap.blocked)
    assert np.array_equal(m.t_sec, r.t_sec) and np.array_equal(m.in_segment, r.in_segment)
    assert np.array_equal(m.frame_index, frame_index_of(r)) and m.frame_index.dtype == np.int32
    assert m.meta.mask == r.report.params.mask and m.meta.swap == r.report.params.swap


def test_t_qlt_13b_f1_has_every_class_of_cell_in_the_file(make_masked, results):
    loaded = load_pose_masked(make_masked("f1"))
    assert {int(c) for c in np.unique(loaded.reason)} == {
        0,
        1,
        2,
        3,
        4,
    }  # ok, low_conf, non_finite, not_tracked, invalid
    assert loaded.swap_blocked.any() and loaded.swap_suspect.any() and loaded.frame_invalid.sum() == 1
    assert (
        np.isnan(loaded.keypoints[loaded.reason != 0]).all() and np.isfinite(loaded.keypoints[loaded.reason == 0]).all()
    )


def test_t_qlt_13b_the_masked_archive_holds_the_documented_arrays_and_nothing_else(make_masked):
    with zipfile.ZipFile(make_masked("f1")) as z:
        assert {n.removesuffix(".npy") for n in z.namelist()} == {*MASKED_ARRAYS, "schema_version", "meta_json"}
    data = arrays_of(make_masked("f1"))
    assert str(data["schema_version"]) == "pose_masked/1" and data["meta_json"].ndim == 0
    assert {k: str(v.dtype) for k, v in data.items() if k in MASKED_ARRAYS} == {
        "frame_index": "int32", "t_sec": "float64", "in_segment": "bool", "tracked": "bool", "keypoints": "float32",
        "scores": "float32", "reason": "uint8", "n_essential_valid": "int8", "frame_invalid": "bool",
        "swap_suspect": "bool", "swap_blocked": "bool",
    }  # fmt: skip


def test_t_qlt_13b_save_returns_the_sha256_of_the_file_on_disk(tmp_path: Path, results):
    path = tmp_path / "pose_masked.npz"
    digest = save_pose_masked(path, masked_layer(results["f1"]))
    assert digest == sha256_file(path) and len(digest) == 64


def test_t_qlt_13b_a_nan_score_and_a_nan_cell_survive_with_their_reason(make_masked, results):
    r = results["f1"]
    assert (r.mask.reason == 2).any() and np.isnan(r.mask.keypoints[r.mask.reason == 2]).all()  # non_finite
    loaded = load_pose_masked(make_masked("f1"))
    assert same(loaded.keypoints, r.mask.keypoints) and same(loaded.reason, r.mask.reason)


# --- T-QLT-13c: the filtered layer round trip and the way back --------------------------------------------------------
@pytest.mark.parametrize("name", SCENARIOS)
def test_t_qlt_13c_a_saved_filtered_layer_comes_back_identical(make_filtered, results, name: str):
    result = results[name]
    layer = filtered_layer(result)
    loaded = load_pose_filtered(make_filtered(name))
    assert loaded.equals(layer)
    for field in FILTERED_ARRAYS:
        assert same(getattr(loaded, field), getattr(layer, field)), field
        assert not getattr(loaded, field).flags.writeable
    assert loaded.meta == layer.meta
    g = result.grid.gridmap
    assert loaded.meta.timeline.n_grid_rows == len(g.t_grid) and loaded.meta.timeline.n_rows == len(result.t_sec)
    assert loaded.meta.timeline.resampled is g.resampled and loaded.meta.timeline.snap_s == g.snap_s
    assert loaded.meta.counts.n_mixed_rows == int(result.grid.mixed.sum())
    assert loaded.meta.counts.n_filtered_cells == int(result.filtered.filtered.sum())
    assert loaded.meta.params == result.report.params  # the parameters as used, the Hampel floor in pixels


@pytest.mark.parametrize("name", SCENARIOS)
def test_t_qlt_13c_the_filtered_layer_is_the_final_layer_of_the_chain(results, name: str):
    r = results[name]
    f = filtered_layer(r)
    assert same(f.keypoints, r.filtered.keypoints) and same(f.reason, r.filtered.reason)
    assert np.array_equal(f.interpolated, r.filtered.interpolated) and np.array_equal(f.filtered, r.filtered.filtered)
    assert np.array_equal(f.t_grid, r.grid.gridmap.t_grid) and np.array_equal(f.mixed, r.grid.mixed)
    assert np.array_equal(f.source_usable, r.grid.source_usable)
    assert np.array_equal(f.outside, r.grid.gridmap.before | r.grid.gridmap.beyond)
    assert np.array_equal(f.back_left, r.grid.gridmap.back_left) and np.array_equal(
        f.back_weight, r.grid.gridmap.back_weight
    )


@pytest.mark.parametrize("name", SCENARIOS)
def test_t_qlt_13c_the_way_back_from_the_file_is_the_way_back_of_the_chain_bit_for_bit(
    make_filtered, results, name: str
):
    result = results[name]
    loaded = load_pose_filtered(make_filtered(name))
    assert same(loaded.on_source(), result.filtered_on_source())
    values = np.random.default_rng(4).normal(size=(len(loaded.t_grid), 26, 2)).astype(np.float32)
    values[np.random.default_rng(5).random((len(values), 26)) < 0.1] = np.nan
    assert same(loaded.on_source(values), result.grid.to_source(values))
    flat = values[:, :, 0]  # any trailing shape, as GridLayer.to_source
    assert same(loaded.on_source(flat), result.grid.to_source(flat))


def test_t_qlt_13c_the_way_back_has_no_value_where_the_source_had_none_or_the_row_is_outside(make_filtered, results):
    lattice = load_pose_filtered(make_filtered("lattice"))
    back = lattice.on_source()
    assert lattice.outside[0] and np.isnan(back[0]).all()  # the first row is before the grid
    assert not np.isnan(back[1:, 0]).all()
    unusable = ~lattice.source_usable & ~lattice.outside[:, None]
    assert unusable.any() and np.isnan(back[unusable]).all()  # a cell that had no value at the source gets none


def test_t_qlt_13c_the_constant_clock_is_the_identity_in_the_file(make_filtered, results):
    f = load_pose_filtered(make_filtered("f1"))
    n = len(f.t_sec)
    assert not f.meta.timeline.resampled and len(f.t_grid) == n and np.array_equal(f.t_grid, f.t_sec)
    assert np.array_equal(f.back_left, np.arange(n)) and not f.back_weight.any() and not f.outside.any()
    assert not f.mixed.any()
    assert same(f.on_source(), results["f1"].filtered_on_source())


def test_t_qlt_13c_a_resampled_clock_keeps_the_pause_as_no_frame_cells(make_filtered, results):
    f = load_pose_filtered(make_filtered("dropped"))
    assert (
        (f.reason == 6).any() and np.isnan(f.keypoints[f.reason == 6]).all() and not f.interpolated[f.reason == 6].any()
    )
    assert f.meta.timeline.resampled and len(f.t_grid) > len(f.t_sec)


def test_t_qlt_13c_grid_in_segment_is_the_set_of_rows_that_the_report_counts(make_filtered, results):
    for name in SCENARIOS:
        f = load_pose_filtered(make_filtered(name))
        seg = results[name].report.intervals[0]
        assert int(f.grid_in_segment.sum()) == seg.rows, name


def test_t_qlt_13c_a_saved_pair_and_the_quality_json_agree_on_the_counts(make_filtered, make_masked, results):
    r = results["jitter"]
    f = load_pose_filtered(make_filtered("jitter"))
    assert (
        f.meta.timeline.n_rows == r.report.timeline.rows and f.meta.timeline.n_grid_rows == r.report.timeline.grid_rows
    )
    assert (
        f.meta.timeline.resampled == r.report.timeline.resampled and f.meta.timeline.step_s == r.report.timeline.step_s
    )
    m = load_pose_masked(make_masked("jitter"))
    assert m.meta.counts.n_rows == r.report.timeline.rows


# --- T-QLT-13d: a damaged or inconsistent masked file ----------------------------------------------------------------
def _set(name: str, index, value):
    def apply(a: dict[str, np.ndarray]) -> None:
        arr = np.array(a[name], copy=True)
        arr[index] = value
        a[name] = arr

    return apply


def _flip(name: str, index):
    def apply(a: dict[str, np.ndarray]) -> None:
        arr = np.array(a[name], copy=True)
        arr[index] = ~arr[index]
        a[name] = arr

    return apply


def _cast(name: str, dtype):
    return lambda a: a.__setitem__(name, a[name].astype(dtype))


def _cut(name: str, index):
    return lambda a: a.__setitem__(name, a[name][index])


def _drop(name: str):
    return lambda a: a.pop(name)


def _both(*steps):
    def apply(a):
        for step in steps:
            step(a)

    return apply


ROW_OK = 30  # an observed, tracked, valid row of F1 (not near a defect)
ROW_INVALID = 15  # the frame_invalid row of F1
ROW_UNTRACKED = 2  # not tracked (and not in the segment)
ROW_HOLE = 25  # LAnkle score 0.1: low_conf, NaN
ANKLE = IDX["LAnkle"]

MASKED_ARRAY_CASES: list[tuple[str, Callable, str]] = [
    *[(f"missing {n}", _drop(n), "lacks the arrays") for n in MASKED_ARRAYS],
    ("extra array", lambda a: a.__setitem__("extra", np.zeros(3)), "unexpected arrays"),
    ("keypoints float64", _cast("keypoints", np.float64), "keypoints has dtype"),
    ("scores float64", _cast("scores", np.float64), "scores has dtype"),
    ("reason int16", _cast("reason", np.int16), "reason has dtype"),
    ("frame_index int64", _cast("frame_index", np.int64), "frame_index has dtype"),
    ("t_sec float32", _cast("t_sec", np.float32), "t_sec has dtype"),
    ("tracked uint8", _cast("tracked", np.uint8), "tracked has dtype"),
    ("in_segment int8", _cast("in_segment", np.int8), "in_segment has dtype"),
    ("n_essential_valid int64", _cast("n_essential_valid", np.int64), "n_essential_valid has dtype"),
    ("frame_invalid uint8", _cast("frame_invalid", np.uint8), "frame_invalid has dtype"),
    ("swap_suspect uint8", _cast("swap_suspect", np.uint8), "swap_suspect has dtype"),
    ("keypoints 25 joints", _cut("keypoints", (slice(None), slice(0, 25))), "keypoints has shape"),
    ("keypoints one row short", _cut("keypoints", slice(0, -1)), "keypoints has shape"),
    ("scores one row short", _cut("scores", slice(0, -1)), "scores has shape"),
    ("reason one row short", _cut("reason", slice(0, -1)), "reason has shape"),
    ("t_sec one row short", _cut("t_sec", slice(0, -1)), "t_sec has shape"),
    ("frame_index one row short", _cut("frame_index", slice(0, -1)), "has shape"),
    ("tracked one row short", _cut("tracked", slice(0, -1)), "tracked has shape"),
    ("n_essential_valid one row short", _cut("n_essential_valid", slice(0, -1)), "n_essential_valid has shape"),
    ("swap_blocked 25 joints", _cut("swap_blocked", (slice(None), slice(0, 25))), "swap_blocked has shape"),
    ("t_sec not increasing", _set("t_sec", 10, 9 / 30.0), "t_sec"),
    ("t_sec NaN", _set("t_sec", 5, np.nan), "t_sec"),
    ("frame_index repeated", _set("frame_index", 10, 7 + 2 * 9), "frame_index"),
    ("frame_index negative", _set("frame_index", 0, -1), "frame_index"),
    ("NaN where ok", _set("keypoints", (ROW_OK, 3), np.nan), "where reason is ok"),
    ("a value where not ok", _set("keypoints", (ROW_HOLE, ANKLE), 5.0), "reason is not ok"),
    ("reason code 5 (outlier) in a mask layer", _set("reason", (ROW_HOLE, ANKLE), 5), "reason"),
    ("reason code 7", _set("reason", (ROW_HOLE, ANKLE), 7), "reason"),
    ("untracked row with another reason", _set("reason", (ROW_UNTRACKED, 0), 1), "not tracked"),
    ("tracked row with not_tracked", _set("reason", (ROW_HOLE, ANKLE), 3), "not_tracked"),
    ("n_essential_valid off by one", _set("n_essential_valid", ROW_OK, 9), "n_essential_valid"),
    ("n_essential_valid on an untracked row", _set("n_essential_valid", ROW_UNTRACKED, 3), "n_essential_valid"),
    ("n_essential_valid negative", _set("n_essential_valid", ROW_OK, -1), "n_essential_valid"),
    ("frame_invalid cleared", _set("frame_invalid", ROW_INVALID, False), "frame_invalid"),
    ("frame_invalid set on a valid row", _set("frame_invalid", ROW_OK, True), "frame_invalid"),
    (
        "an ok cell in a frame_invalid row",
        _both(_set("reason", (ROW_INVALID, 0), 0), _set("keypoints", (ROW_INVALID, 0), 5.0)),
        "frame_invalid",
    ),
    (
        "a frame_invalid cell in a valid row",
        _both(_set("reason", (ROW_OK, 0), 4), _set("keypoints", (ROW_OK, 0), np.nan)),
        "frame_invalid cell",
    ),
    ("swap_suspect outside swap_blocked", _set("swap_suspect", (ROW_OK, 5), True), "swap_suspect"),
    (
        "a swap flag on a joint with no pair",
        _both(_set("swap_suspect", (ROW_OK, 0), True), _set("swap_blocked", (ROW_OK, 0), True)),
        "pair",
    ),
]


@pytest.mark.parametrize(("name", "change", "field"), MASKED_ARRAY_CASES, ids=[c[0] for c in MASKED_ARRAY_CASES])
def test_t_qlt_13d_a_damaged_masked_archive_is_refused_naming_the_field(make_masked, name: str, change, field: str):
    path = make_masked("f1")
    damage(path, arrays=change)
    with pytest.raises(QualityLayerError, match=field):
        load_pose_masked(path)


def _meta_set(*keys, value):
    def apply(h: dict[str, Any]) -> None:
        node = h
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value

    return apply


def _meta_add(*keys, by):
    def apply(h: dict[str, Any]) -> None:
        node = h
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] += by

    return apply


def _meta_drop(key: str):
    return lambda h: h.pop(key)


MASKED_META_CASES: list[tuple[str, Callable, str]] = [
    ("version in the header", _meta_set("schema_version", value="pose_masked/2"), "schema_version"),
    ("skeleton", _meta_set("skeleton", value="coco17/1"), "skeleton"),
    ("recording_id", _meta_set("recording_id", value="x"), "recording_id"),
    ("n_rows of the header", _meta_set("counts", "n_rows", value=61), "n_rows"),
    ("a key missing", _meta_drop("recording_id"), "recording_id"),
    ("a key more", lambda h: h.__setitem__("path", "C:/x"), "path"),
    ("a bad data source", _meta_set("data_sources", value=[{"dataset_id": "x", "license": "a"}]), "dataset_id"),
    ("the frame rule of the header", _meta_set("mask", "min_essential_fraction", value=0.95), "frame_invalid"),
    ("the essential joints of the header", _meta_set("mask", "essential", value=[5, 6]), "n_essential_valid"),
    ("the pairs of the header", _meta_set("swap", "pairs", value=[[1, 2]]), "pair"),
]


@pytest.mark.parametrize(("name", "change", "field"), MASKED_META_CASES, ids=[c[0] for c in MASKED_META_CASES])
def test_t_qlt_13d_a_bad_masked_header_is_refused_naming_the_field(make_masked, name: str, change, field: str):
    path = make_masked("f1")
    damage(path, meta=change)
    with pytest.raises(QualityLayerError, match=field):
        load_pose_masked(path)


def test_t_qlt_13d_another_version_is_refused_naming_both_versions(make_masked):
    path = make_masked("f1")
    damage(path, arrays=lambda a: a.__setitem__("schema_version", np.array("pose_masked/2")))
    with pytest.raises(QualityLayerError) as info:
        load_pose_masked(path)
    assert "pose_masked/2" in str(info.value) and "pose_masked/1" in str(info.value)


def test_t_qlt_13d_every_refusal_above_fires_for_its_own_reason(make_masked):
    """The undamaged file loads, and each case changes exactly one thing (so a refusal is not an accident)."""
    for name in ("f1", "dropped"):
        load_pose_masked(make_masked(name))
    assert len({c[0] for c in MASKED_ARRAY_CASES}) == len(MASKED_ARRAY_CASES) >= 46


# --- T-QLT-13e: a damaged or inconsistent filtered file ---------------------------------------------------------------
IDENT_ROW = 30  # a row of F1's grid that is an observed, filtered cell for every joint
J_ROW = 60  # a grid row of the jittered clock that is a mix with a weight
CELL = (IDENT_ROW, 3)


def _a_mixed_row(a: dict[str, np.ndarray]) -> int:
    """The sixth row of the jittered clock that has a weight (a row between two grid times)."""
    return int(np.flatnonzero(a["back_weight"] > 0.0)[5])


def _nudge_weight(a: dict[str, np.ndarray]) -> None:
    """Move the weight of a mixed row to another value of [0, 1): the row is no longer where its time says."""
    w, i = np.array(a["back_weight"], copy=True), _a_mixed_row(a)
    w[i] = w[i] + 0.2 if w[i] < 0.7 else w[i] - 0.2
    a["back_weight"] = w


def _last_grid_row(a: dict[str, np.ndarray]) -> None:
    """Point a mixed row at the last grid row: it has no grid row to its right."""
    left = np.array(a["back_left"], copy=True)
    left[_a_mixed_row(a)] = len(a["t_grid"]) - 1
    a["back_left"] = left


FILTERED_ARRAY_CASES: list[tuple[str, str, Callable, str]] = [
    *[(f"missing {n}", "f1", _drop(n), "lacks the arrays") for n in FILTERED_ARRAYS],
    ("extra array", "f1", lambda a: a.__setitem__("extra", np.zeros(3)), "unexpected arrays"),
    ("keypoints float64", "f1", _cast("keypoints", np.float64), "keypoints has dtype"),
    ("reason int16", "f1", _cast("reason", np.int16), "reason has dtype"),
    ("interpolated uint8", "f1", _cast("interpolated", np.uint8), "interpolated has dtype"),
    ("filtered uint8", "f1", _cast("filtered", np.uint8), "filtered has dtype"),
    ("mixed uint8", "f1", _cast("mixed", np.uint8), "mixed has dtype"),
    ("t_grid float32", "f1", _cast("t_grid", np.float32), "t_grid has dtype"),
    ("back_left int64", "f1", _cast("back_left", np.int64), "back_left has dtype"),
    ("back_weight float32", "f1", _cast("back_weight", np.float32), "back_weight has dtype"),
    ("outside uint8", "f1", _cast("outside", np.uint8), "outside has dtype"),
    ("source_usable uint8", "f1", _cast("source_usable", np.uint8), "source_usable has dtype"),
    ("keypoints one row short", "f1", _cut("keypoints", slice(0, -1)), "keypoints has shape"),
    ("reason 25 joints", "f1", _cut("reason", (slice(None), slice(0, 25))), "reason has shape"),
    ("t_grid one row short", "f1", _cut("t_grid", slice(0, -1)), "has shape"),
    ("mixed one row short", "f1", _cut("mixed", slice(0, -1)), "mixed has shape"),
    ("grid_in_segment one row short", "f1", _cut("grid_in_segment", slice(0, -1)), "grid_in_segment has shape"),
    ("t_sec one row short", "f1", _cut("t_sec", slice(0, -1)), "t_sec has shape"),
    ("frame_index one row short", "f1", _cut("frame_index", slice(0, -1)), "has shape"),
    ("source_usable one row short", "f1", _cut("source_usable", slice(0, -1)), "source_usable has shape"),
    ("back_left one row short", "f1", _cut("back_left", slice(0, -1)), "back_left has shape"),
    ("back_weight one row short", "f1", _cut("back_weight", slice(0, -1)), "back_weight has shape"),
    ("outside one row short", "f1", _cut("outside", slice(0, -1)), "outside has shape"),
    ("t_grid not increasing", "f1", _set("t_grid", 10, 9 / 30.0), "t_grid"),
    ("t_grid NaN", "f1", _set("t_grid", 5, np.nan), "t_grid"),
    ("t_sec not increasing", "f1", _set("t_sec", 10, 9 / 30.0), "t_sec"),
    ("frame_index decreasing", "f1", _set("frame_index", 10, 3), "frame_index"),
    ("NaN where ok", "f1", _set("keypoints", CELL, np.nan), "where reason is ok"),
    ("a value where not ok, not flagged", "f1", _set("reason", CELL, 1), "not flagged"),
    ("interpolated on an ok cell", "f1", _set("interpolated", CELL, True), "reason is ok"),
    ("a reason code 9", "f1", _both(_set("reason", CELL, 9), _set("interpolated", CELL, True)), "reason"),
    (  # one cell cleared elsewhere keeps the header count: only the check on a cell without a value can refuse it
        "filtered on a NaN cell",
        "f1",
        _both(_set("filtered", (ROW_HOLE, ANKLE), True), _set("filtered", CELL, False)),
        "no value",
    ),
    ("grid_in_segment flipped", "f1", _flip("grid_in_segment", 10), "grid_in_segment"),
    ("grid_in_segment flipped (jitter)", "jitter", _flip("grid_in_segment", 0), "grid_in_segment"),
    ("identity: the grid moved", "f1", _set("t_grid", 3, 3 / 30.0 + 0.01), "grid"),
    ("identity: a mixed row", "f1", _set("mixed", 3, True), "mixed"),
    ("identity: a map that is not the rows", "f1", _set("back_left", 3, 4), "back_left"),
    ("identity: a weight", "f1", _set("back_weight", 3, 0.25), "back_weight"),
    ("identity: a row outside", "f1", _set("outside", 3, True), "outside"),
    ("back_left past the grid", "jitter", _set("back_left", 10, 10_000), "back_left"),
    ("back_left negative", "jitter", _set("back_left", 10, -1), "back_left"),
    ("back_weight of one", "jitter", _set("back_weight", J_ROW, 1.0), "back_weight"),
    ("back_weight negative", "jitter", _set("back_weight", J_ROW, -0.1), "back_weight"),
    ("back_weight NaN", "jitter", _set("back_weight", J_ROW, np.nan), "back_weight"),
    ("back_weight that the clocks do not give", "jitter", _set("back_weight", slice(None), 0.0), "back_weight"),
    ("a mixed row whose weight is not its time", "jitter", _nudge_weight, "back_weight does not match"),
    ("a mixed row with no grid row to its right", "jitter", _last_grid_row, "back_left"),
    ("a copy that is far from its grid time", "lattice", _set("back_left", 50, 52), "snap_s"),
    ("an outside row with a weight", "lattice", _set("back_weight", 0, 0.5), "outside"),
    ("outside cleared on a row before the grid", "lattice", _set("outside", 0, False), "outside"),
    ("outside set on a row inside the grid", "lattice", _set("outside", 50, True), "outside"),
    ("mixed row count of the header", "jitter", _flip("mixed", 0), "n_mixed_rows"),
    ("filtered cell count of the header", "f1", _set("filtered", CELL, False), "n_filtered_cells"),
]


@pytest.mark.parametrize(
    ("name", "kind", "change", "field"), FILTERED_ARRAY_CASES, ids=[f"{c[1]}: {c[0]}" for c in FILTERED_ARRAY_CASES]
)
def test_t_qlt_13e_a_damaged_filtered_archive_is_refused_naming_the_field(
    make_filtered, name: str, kind: str, change, field: str
):
    path = make_filtered(kind)
    damage(path, arrays=change)
    with pytest.raises(QualityLayerError, match=field):
        load_pose_filtered(path)


FILTERED_META_CASES: list[tuple[str, str, Callable, str]] = [
    ("version in the header", "f1", _meta_set("schema_version", value="pose_filtered/2"), "schema_version"),
    ("skeleton", "f1", _meta_set("skeleton", value="coco17/1"), "skeleton"),
    ("n_rows of the header", "f1", _meta_set("timeline", "n_rows", value=61), "n_rows"),
    ("n_grid_rows of the header (identity)", "f1", _meta_set("timeline", "n_grid_rows", value=61), "n_grid_rows"),
    ("n_grid_rows of the header (resampled)", "dropped", _meta_add("timeline", "n_grid_rows", by=1), "n_grid_rows"),
    (
        "resampled cleared on a resampled file",
        "dropped",
        _meta_set("timeline", "resampled", value=False),
        "n_grid_rows",
    ),
    ("snap_s too small for the copies", "lattice", _meta_set("timeline", "snap_s", value=1e-9), "snap_s"),
    ("n_mixed_rows of the header", "jitter", _meta_set("counts", "n_mixed_rows", value=1), "n_mixed_rows"),
    ("n_filtered_cells of the header", "f1", _meta_set("counts", "n_filtered_cells", value=1), "n_filtered_cells"),
    ("a key missing", "f1", _meta_drop("timeline"), "timeline"),
    ("a key more", "f1", lambda h: h.__setitem__("file", "a.mp4"), "file"),
    ("a bad parameter record", "f1", _meta_set("params", "filter", "order", value=0), "order"),
]


@pytest.mark.parametrize(
    ("name", "kind", "change", "field"), FILTERED_META_CASES, ids=[f"{c[1]}: {c[0]}" for c in FILTERED_META_CASES]
)
def test_t_qlt_13e_a_bad_filtered_header_is_refused_naming_the_field(
    make_filtered, name: str, kind: str, change, field: str
):
    path = make_filtered(kind)
    damage(path, meta=change)
    with pytest.raises(QualityLayerError, match=field):
        load_pose_filtered(path)


def test_t_qlt_13e_another_version_is_refused_naming_both_versions(make_filtered):
    path = make_filtered("f1")
    damage(path, arrays=lambda a: a.__setitem__("schema_version", np.array("pose_filtered/2")))
    with pytest.raises(QualityLayerError) as info:
        load_pose_filtered(path)
    assert "pose_filtered/2" in str(info.value) and "pose_filtered/1" in str(info.value)


def test_t_qlt_13e_the_cases_are_many_and_distinct():
    assert len({(c[1], c[0]) for c in FILTERED_ARRAY_CASES}) == len(FILTERED_ARRAY_CASES) >= 57


# --- T-QLT-13f: files that are not an archive of ours ----------------------------------------------------------------
def test_t_qlt_13f_files_that_are_not_an_archive_are_refused(tmp_path: Path, make_masked, make_filtered):
    for loader, good in ((load_pose_masked, make_masked("f1")), (load_pose_filtered, make_filtered("f1"))):
        content = good.read_bytes()
        cases = {
            "random": np.random.default_rng(1).bytes(4096),
            "empty": b"",
            "text": b"this is not an archive\n",
            "truncated": content[: len(content) // 2],
        }
        for name, data in cases.items():
            path = tmp_path / f"{name}.npz"
            path.write_bytes(data)
            with pytest.raises(QualityLayerError) as info:
                loader(path)
            assert info.value.__cause__ is not None, name


def test_t_qlt_13f_an_archive_without_a_version_or_with_a_pickled_array_is_refused(tmp_path: Path, make_masked):
    path = tmp_path / "noversion.npz"
    data = arrays_of(make_masked("f1"))
    data.pop("schema_version")
    np.savez(path, **data)
    with pytest.raises(QualityLayerError, match="schema_version"):
        load_pose_masked(path)
    path = tmp_path / "pickled.npz"
    data = arrays_of(make_masked("f1"))
    data["meta_json"] = np.array([{"a": 1}], dtype=object)
    np.savez(path, **data)
    with pytest.raises(QualityLayerError):
        load_pose_masked(path)


def test_t_qlt_13f_a_missing_file_is_refused(tmp_path: Path):
    with pytest.raises(QualityLayerError):
        load_pose_masked(tmp_path / "nope.npz")
    with pytest.raises(QualityLayerError):
        load_pose_filtered(tmp_path / "nope.npz")


def test_t_qlt_13f_a_masked_file_is_not_a_filtered_file_and_the_reverse(make_masked, make_filtered):
    with pytest.raises(QualityLayerError, match="pose_masked/1"):
        load_pose_filtered(make_masked("f1"))
    with pytest.raises(QualityLayerError, match="pose_filtered/1"):
        load_pose_masked(make_filtered("f1"))


def test_t_qlt_13f_a_pose_raw_file_is_not_a_layer_file(tmp_path: Path):
    from helpers.pose_raw_build import make_pose_raw
    from taiji_ai.pose.raw_io import save_pose_raw

    path = tmp_path / "pose_raw.npz"
    save_pose_raw(path, make_pose_raw())
    for loader in (load_pose_masked, load_pose_filtered):
        with pytest.raises(QualityLayerError, match="pose_raw/1"):
            loader(path)


# --- T-QLT-13g: the write is atomic ----------------------------------------------------------------------------------
def test_t_qlt_13g_a_failing_replace_keeps_the_previous_file_and_leaves_no_tmp(
    tmp_path: Path, results, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "pose_masked.npz"
    old = masked_layer(results["f1"])
    save_pose_masked(path, old)

    def broken_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(artifacts.os, "replace", broken_replace)
    with pytest.raises(QualityLayerError, match="could not write"):
        save_pose_masked(path, masked_layer(results["dropped"]))
    with pytest.raises(QualityLayerError, match="could not write"):
        save_pose_filtered(tmp_path / "pose_filtered.npz", filtered_layer(results["f1"]))
    monkeypatch.undo()
    assert load_pose_masked(path).equals(old)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pose_masked.npz"]


def test_t_qlt_13g_a_second_save_replaces_the_first_completely(tmp_path: Path, results):
    path = tmp_path / "pose_filtered.npz"
    save_pose_filtered(path, filtered_layer(results["f1"]))
    new = filtered_layer(results["dropped"])
    save_pose_filtered(path, new)
    assert load_pose_filtered(path).equals(new)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pose_filtered.npz"]


def test_t_qlt_13g_a_missing_folder_is_refused_and_not_created(tmp_path: Path, results):
    with pytest.raises(QualityLayerError, match="folder"):
        save_pose_masked(tmp_path / "no_such" / "pose_masked.npz", masked_layer(results["f1"]))
    with pytest.raises(QualityLayerError, match="folder"):
        save_pose_filtered(tmp_path / "no_such" / "pose_filtered.npz", filtered_layer(results["f1"]))
    assert not (tmp_path / "no_such").exists()


# --- T-QLT-13h: the writer refuses what the reader would refuse; privacy; the builders ------------------------------
MASKED_WRITE_BAD = [
    ("float64 keypoints", lambda m: dataclasses.replace(m, keypoints=m.keypoints.astype(np.float64)), "keypoints"),
    ("float64 scores", lambda m: dataclasses.replace(m, scores=m.scores.astype(np.float64)), "scores"),
    (
        "frame_index not increasing",
        lambda m: dataclasses.replace(m, frame_index=m.frame_index[::-1].copy()),
        "frame_index",
    ),
    ("a row short", lambda m: dataclasses.replace(m, t_sec=m.t_sec[:-1].copy()), "t_sec"),
    ("NaN where ok", lambda m: dataclasses.replace(m, keypoints=_with(m.keypoints, (30, 3), np.nan)), "reason is ok"),
    ("reason code 5", lambda m: dataclasses.replace(m, reason=_with(m.reason, (25, 15), 5)), "reason"),
    ("n_rows of the header", lambda m: dataclasses.replace(m, meta=_meta_n(m.meta, 5)), "n_rows"),
    (
        "swap_suspect outside swap_blocked",
        lambda m: dataclasses.replace(m, swap_suspect=_with(m.swap_suspect, (30, 5), True)),
        "swap_suspect",
    ),
]


def _with(a: np.ndarray, index, value) -> np.ndarray:
    b = np.array(a, copy=True)
    b[index] = value
    return b


def _meta_n(meta, n: int):
    return meta.model_copy(update={"counts": meta.counts.model_copy(update={"n_rows": n})})


@pytest.mark.parametrize(("name", "change", "field"), MASKED_WRITE_BAD, ids=[c[0] for c in MASKED_WRITE_BAD])
def test_t_qlt_13h_a_masked_layer_that_breaks_the_rules_is_not_written(tmp_path: Path, results, name, change, field):
    with pytest.raises(QualityLayerError, match=field):
        save_pose_masked(tmp_path / "pose_masked.npz", change(masked_layer(results["f1"])))
    assert list(tmp_path.iterdir()) == []


FILTERED_WRITE_BAD = [
    ("float64 keypoints", lambda f: dataclasses.replace(f, keypoints=f.keypoints.astype(np.float64)), "keypoints"),
    ("a grid row short", lambda f: dataclasses.replace(f, mixed=f.mixed[:-1].copy()), "mixed"),
    ("t_grid not increasing", lambda f: dataclasses.replace(f, t_grid=f.t_grid[::-1].copy()), "t_grid"),
    (
        "filtered on a NaN cell",
        lambda f: dataclasses.replace(f, filtered=_with(_with(f.filtered, (25, 15), True), (30, 3), False)),
        "no value",
    ),
    ("a value not flagged", lambda f: dataclasses.replace(f, reason=_with(f.reason, (30, 3), 1)), "not flagged"),
    (
        "grid_in_segment",
        lambda f: dataclasses.replace(f, grid_in_segment=_with(f.grid_in_segment, 10, False)),
        "grid_in_segment",
    ),
    ("back_weight", lambda f: dataclasses.replace(f, back_weight=_with(f.back_weight, 3, 0.25)), "back_weight"),
    (
        "n_mixed_rows of the header",
        lambda f: dataclasses.replace(f, meta=_filtered_meta(f.meta, n_mixed_rows=3)),
        "n_mixed_rows",
    ),
]


def _filtered_meta(meta, **counts):
    return meta.model_copy(update={"counts": meta.counts.model_copy(update=counts)})


@pytest.mark.parametrize(("name", "change", "field"), FILTERED_WRITE_BAD, ids=[c[0] for c in FILTERED_WRITE_BAD])
def test_t_qlt_13h_a_filtered_layer_that_breaks_the_rules_is_not_written(tmp_path: Path, results, name, change, field):
    with pytest.raises(QualityLayerError, match=field):
        save_pose_filtered(tmp_path / "pose_filtered.npz", change(filtered_layer(results["f1"])))
    assert list(tmp_path.iterdir()) == []


def test_t_qlt_13h_the_builders_refuse_a_float64_layer_a_bad_frame_index_and_a_wrong_type(results):
    t = np.arange(40) / 30.0
    kp, score = moving(t)
    r64 = run_quality_arrays(kp.astype(np.float64), score.astype(np.float64), t)
    for build in (pose_masked_from_result, pose_filtered_from_result):
        with pytest.raises(QualityLayerError, match="float32"):
            build(r64, recording_id=RECORDING_ID, frame_index=np.arange(40))
        r = results["f1"]
        for bad in (np.arange(59), np.arange(60)[::-1], np.arange(60) - 1, np.zeros(60), np.arange(60.0) + 0.5):
            with pytest.raises(QualityLayerError, match="frame_index"):
                build(r, recording_id=RECORDING_ID, frame_index=bad)
        with pytest.raises(QualityLayerError, match="recording_id"):
            build(r, recording_id="not-a-uuid", frame_index=frame_index_of(r))
        with pytest.raises(TypeError):
            build("a result", recording_id=RECORDING_ID, frame_index=frame_index_of(r))  # type: ignore[arg-type]


def test_t_qlt_13h_a_layer_without_rows_is_not_saved(tmp_path: Path):
    t = np.zeros(0)
    kp = np.zeros((0, 26, 2), np.float32)
    r = run_quality_arrays(kp, np.zeros((0, 26), np.float32), t)
    for build in (pose_masked_from_result, pose_filtered_from_result):
        with pytest.raises(QualityLayerError, match="no rows"):
            build(r, recording_id=RECORDING_ID, frame_index=np.zeros(0, dtype=np.int64))


def test_t_qlt_13h_the_data_sources_are_carried_and_default_to_none(tmp_path: Path, results):
    r = results["f1"]
    two = (
        DataSource(dataset_id="D08", license="own recordings"),
        DataSource(dataset_id="D12", license="CC BY-NC-SA 4.0"),
    )
    m = pose_masked_from_result(r, recording_id=RECORDING_ID, frame_index=frame_index_of(r), data_sources=two)
    save_pose_masked(tmp_path / "m.npz", m)
    assert load_pose_masked(tmp_path / "m.npz").meta.data_sources == two
    f = pose_filtered_from_result(r, recording_id=RECORDING_ID, frame_index=frame_index_of(r))
    save_pose_filtered(tmp_path / "f.npz", f)
    assert load_pose_filtered(tmp_path / "f.npz").meta.data_sources == ()


@pytest.mark.parametrize("kind", ["masked", "filtered"])
def test_t_qlt_13h_the_header_holds_no_path_and_no_file_name(tmp_path: Path, make_masked, make_filtered, kind: str):
    path = make_masked("f1") if kind == "masked" else make_filtered("f1")
    text = str(arrays_of(path)["meta_json"])
    meta = json.loads(text)
    assert meta["recording_id"] == RECORDING_ID
    # the only text that may hold a slash is a schema or skeleton id; the licence text of the source is the caller's
    allowed = ("pose_masked/1", "pose_filtered/1", "halpe26/1", "data_sources", "own recordings")
    stripped = text
    for token in allowed:
        stripped = stripped.replace(token, "")
    for forbidden in (str(tmp_path), "\\", ".mp4", ".mov", ".mkv", "C:", "/", "participant", "file"):
        assert forbidden not in stripped, forbidden
    assert meta["data_sources"] == [{"dataset_id": "D08", "license": "own recordings"}]


def test_t_qlt_13h_a_nan_in_the_header_is_impossible_and_wall_clock_is_not_stored(make_filtered):
    text = str(arrays_of(make_filtered("jitter"))["meta_json"])
    assert "NaN" not in text and "Infinity" not in text and "elapsed" not in text and "wall" not in text


def test_t_qlt_13h_layers_do_not_share_memory_with_the_result_and_the_result_is_not_changed(results):
    r = results["jitter"]
    before = (r.filtered.keypoints.copy(), r.mask.keypoints.copy(), r.grid.gridmap.back_weight.copy())
    f, m = filtered_layer(r), masked_layer(r)
    assert not np.shares_memory(f.keypoints, r.filtered.keypoints) and not np.shares_memory(
        m.keypoints, r.mask.keypoints
    )
    for got, want in zip((r.filtered.keypoints, r.mask.keypoints, r.grid.gridmap.back_weight), before, strict=True):
        assert np.array_equal(got, want, equal_nan=True)
    with pytest.raises(ValueError, match="read-only"):
        f.keypoints[0, 0, 0] = 1.0


def test_t_qlt_13h_equals_is_false_for_a_different_layer_and_for_another_type(results):
    a, b = masked_layer(results["f1"]), masked_layer(results["dropped"])
    assert a.equals(a) and not a.equals(b) and not a.equals("x")  # type: ignore[arg-type]
    c = filtered_layer(results["f1"])
    assert c.equals(c) and not c.equals(filtered_layer(results["jitter"]))
    nan_a = dataclasses.replace(a, keypoints=_with(a.keypoints, (30, 3), 1.0))
    assert not a.equals(nan_a)


def test_t_qlt_13h_on_source_refuses_values_of_the_wrong_shape(results):
    f = filtered_layer(results["jitter"])
    n = len(f.t_grid)
    with pytest.raises(QualityLayerError, match="values"):
        f.on_source(np.zeros((n - 1, 26, 2), np.float32))
    with pytest.raises(QualityLayerError, match="values"):
        f.on_source(np.zeros((n, 25, 2), np.float32))
    with pytest.raises(QualityLayerError, match="values"):
        f.on_source(np.zeros((n, 26, 2), np.int32))
