"""P3.06: ``track.parquet`` round trip, strict loading, atomic writing (T-TRK-06a, 06b, 06c)."""

from __future__ import annotations

import copy
import dataclasses
import json
import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from helpers.track_build import FPS, HOME_X, resolve, stands
from taiji_ai.schemas.track import TrackCounts
from taiji_ai.store.artifacts import sha256_file
from taiji_ai.track.state import BEFORE_TARGET, LOST, TARGET_LOST, TRACKED, TargetTrack
from taiji_ai.track.track_io import TrackFileError, load_track, save_track

META_KEY = b"taiji_track_meta"
COLUMNS = [
    ("frame_index", pa.int32()),
    ("t_sec", pa.float64()),
    ("in_segment", pa.bool_()),
    ("status", pa.string()),
    ("track_id", pa.int32()),
    ("person_row", pa.int32()),
    ("keypoints", pa.list_(pa.float32(), 52)),
    ("scores", pa.list_(pa.float32(), 26)),
    ("match_cost", pa.float32()),
    ("match_margin", pa.float32()),
    ("reattach_cost", pa.float32()),
]


@pytest.fixture(scope="module")
def rich() -> TargetTrack:
    """Every status and kinds of events: before_target, tracked, lost, target_lost, a refusal, a re-attachment."""
    paths = {0: stands(HOME_X, first=5, absent=[(30, 50), (80, 130)]), 1: stands(1500), 2: stands(400, first=100)}
    run = resolve(paths, 170, at_t_sec=10 / FPS, segment_start_pos=10)
    assert {e.kind for e in run.target.meta.events} == {"lost", "target_lost", "reattached", "refused"}
    assert set(np.unique(run.target.status)) == {0, 1, 2, 3}
    return run.target


@pytest.fixture
def good_file(tmp_path: Path, rich: TargetTrack) -> Path:
    path = tmp_path / "track.parquet"
    save_track(path, rich)
    return path


# --- T-TRK-06a: round trip --------------------------------------------------------------------------------------------
def test_t_trk_06a_save_then_load_gives_the_same_target_track_bit_for_bit(tmp_path: Path, rich: TargetTrack):
    path = tmp_path / "track.parquet"
    digest = save_track(path, rich)
    loaded = load_track(path)
    assert loaded.equals(rich)
    assert digest == sha256_file(path) and len(digest) == 64
    for name in ("keypoints", "scores", "t_sec", "match_cost", "reattach_cost"):
        assert getattr(loaded, name).tobytes() == getattr(rich, name).tobytes(), name  # NaN included


def test_t_trk_06a_nan_keypoints_and_scores_of_a_tracked_row_survive(tmp_path: Path, rich: TargetTrack):
    pos = int(np.flatnonzero(rich.status == TRACKED)[3])
    keypoints, scores = rich.keypoints.copy(), rich.scores.copy()
    keypoints[pos, 5] = np.nan
    scores[pos, 7] = np.nan
    changed = dataclasses.replace(rich, keypoints=keypoints, scores=scores)
    save_track(tmp_path / "t.parquet", changed)
    loaded = load_track(tmp_path / "t.parquet")
    assert np.isnan(loaded.keypoints[pos, 5]).all() and np.isnan(loaded.scores[pos, 7]) and loaded.equals(changed)


def test_t_trk_06a_the_columns_and_types_are_the_documented_ones(good_file: Path, rich: TargetTrack):
    schema = pq.read_schema(good_file)
    assert [(f.name, f.type) for f in schema] == COLUMNS
    meta = json.loads(schema.metadata[META_KEY])
    assert meta["schema_version"] == "track/1" and meta["counts"]["n_frames"] == rich.n_frames
    table = pq.read_table(good_file)
    assert table.num_rows == rich.n_frames
    assert set(table["status"].to_pylist()) == {"tracked", "lost", "target_lost", "before_target"}
    kp = table["keypoints"].to_pylist()[int(np.flatnonzero(rich.status == TRACKED)[0])]
    assert kp[0] == float(rich.keypoints[int(np.flatnonzero(rich.status == TRACKED)[0]), 0, 0])  # x0, y0, x1, ...


def test_t_trk_06a_no_path_and_no_file_name_is_inside_the_file(tmp_path: Path, rich: TargetTrack):
    folder = tmp_path / "private_person_folder"
    folder.mkdir()
    path = folder / "secret_name.parquet"
    save_track(path, rich)
    data = path.read_bytes()
    assert b"private_person_folder" not in data and b"secret_name" not in data and str(tmp_path).encode() not in data


def test_t_trk_06a_a_second_save_replaces_the_file(tmp_path: Path, rich: TargetTrack):
    path = tmp_path / "track.parquet"
    save_track(path, rich)
    shorter = _first_frames(rich, 100)
    digest = save_track(path, shorter)
    assert load_track(path).equals(shorter) and digest == sha256_file(path)


def _first_frames(tt: TargetTrack, n: int) -> TargetTrack:
    """A shorter, still consistent target track (the events and counts of the prefix)."""
    events = tuple(e for e in tt.meta.events if e.frame_pos < n)
    status = tt.status[:n]
    counts = TrackCounts(
        n_frames=n,
        n_in_segment=int(tt.in_segment[:n].sum()),
        n_tracked=int((status == TRACKED).sum()),
        n_lost=int((status == LOST).sum()),
        n_target_lost=int((status == TARGET_LOST).sum()),
        n_before_target=int((status == BEFORE_TARGET).sum()),
        n_reattached=sum(e.kind == "reattached" for e in events),
        n_refused=sum(e.kind == "refused" for e in events),
        n_ambiguous=sum(e.kind == "ambiguous" for e in events),
    )
    meta = tt.meta.model_copy(
        update={"counts": counts, "events": events, "needs_reselect": False, "reselect_reason": None}
    )
    fields = {f.name: getattr(tt, f.name)[:n] for f in dataclasses.fields(tt) if f.name not in ("meta",)}
    return TargetTrack(**fields, meta=meta)


# --- T-TRK-06b: refusals of a damaged or inconsistent file ----------------------------------------------------------
def _column(table: pa.Table, name: str) -> list:
    return table[name].to_pylist()


def _replace(table: pa.Table, name: str, values, type_=None) -> pa.Table:
    i = table.schema.get_field_index(name)
    return table.set_column(i, name, pa.array(values, type=type_ or table.schema.field(name).type))


def _meta(table: pa.Table) -> dict:
    return json.loads(table.schema.metadata[META_KEY])


def _with_meta(table: pa.Table, meta: dict | bytes | None) -> pa.Table:
    metadata = dict(table.schema.metadata or {})
    metadata.pop(META_KEY, None)
    if meta is not None:
        metadata[META_KEY] = meta if isinstance(meta, bytes) else json.dumps(meta).encode()
    return table.replace_schema_metadata(metadata)


def _first_of(table: pa.Table, status: str) -> int:
    return _column(table, "status").index(status)


def _set_row(table: pa.Table, name: str, row: int, value) -> pa.Table:
    values = _column(table, name)
    values[row] = value
    return _replace(table, name, values)


Damage = Callable[[pa.Table], pa.Table]
DAMAGES: dict[str, tuple[Damage, str]] = {
    "another version": (lambda t: _with_meta(t, {**_meta(t), "schema_version": "track/2"}), "track/2"),
    "no metadata": (lambda t: _with_meta(t, None), "taiji_track_meta"),
    "metadata not JSON": (lambda t: _with_meta(t, b"{not json"), "JSON"),
    "metadata unknown field": (lambda t: _with_meta(t, {**_meta(t), "extra": 1}), "extra"),
    "another skeleton": (lambda t: _with_meta(t, {**_meta(t), "skeleton": "coco17/1"}), "skeleton"),
    "missing column": (lambda t: t.drop_columns(["scores"]), "scores"),
    "extra column": (lambda t: t.append_column("surprise", pa.array([0] * t.num_rows)), "surprise"),
    "columns in another order": (lambda t: t.select(list(reversed(t.column_names))), "order"),
    "status as a number": (lambda t: _replace(t, "status", [0] * t.num_rows, pa.int64()), "status"),
    "t_sec as float32": (lambda t: _replace(t, "t_sec", _column(t, "t_sec"), pa.float32()), "t_sec"),
    "keypoint list of 50": (
        lambda t: _replace(t, "keypoints", [[0.0] * 50] * t.num_rows, pa.list_(pa.float32(), 50)),
        "keypoints",
    ),
    "variable-size scores": (lambda t: _replace(t, "scores", _column(t, "scores"), pa.list_(pa.float32())), "scores"),
    "unknown status": (lambda t: _set_row(t, "status", 3, "vanished"), "status"),
    "counts disagree with the rows": (
        lambda t: _with_meta(
            t,
            {
                **_meta(t),
                "counts": {
                    **_meta(t)["counts"],
                    "n_tracked": _meta(t)["counts"]["n_tracked"] + 1,
                    "n_lost": _meta(t)["counts"]["n_lost"] - 1,
                },
            },
        ),
        "n_tracked",
    ),
    "t_sec does not increase": (lambda t: _set_row(t, "t_sec", 20, _column(t, "t_sec")[19]), "t_sec"),
    "t_sec is NaN": (lambda t: _set_row(t, "t_sec", 20, float("nan")), "t_sec"),
    "frame_index does not increase": (
        lambda t: _set_row(t, "frame_index", 20, _column(t, "frame_index")[19]),
        "frame_index",
    ),
    "a null": (lambda t: _set_row(t, "match_cost", 12, None), "match_cost"),
    "keypoints on a lost row": (lambda t: _set_row(t, "keypoints", _first_of(t, "lost"), [1.0] * 52), "keypoints"),
    "scores on a target_lost row": (lambda t: _set_row(t, "scores", _first_of(t, "target_lost"), [0.5] * 26), "scores"),
    "tracked row without a person": (lambda t: _set_row(t, "person_row", _first_of(t, "tracked"), -1), "person_row"),
    "tracked row without a track": (lambda t: _set_row(t, "track_id", _first_of(t, "tracked"), -1), "track_id"),
    "lost row with a person": (lambda t: _set_row(t, "person_row", _first_of(t, "lost"), 3), "person_row"),
    "lost row with a cost": (lambda t: _set_row(t, "match_cost", _first_of(t, "lost"), 0.1), "match_cost"),
    "in_segment disagrees with the segment": (lambda t: _set_row(t, "in_segment", 0, True), "in_segment"),
    "a re-attachment without its cost": (lambda t: _set_row(t, "reattach_cost", 50, float("nan")), "reattach_cost"),
    "a cost where no re-attachment happened": (lambda t: _set_row(t, "reattach_cost", 12, 0.1), "reattach_cost"),
    "before_target in the middle": (lambda t: _set_row(t, "status", 60, "before_target"), "before_target"),
    "event outside the frames": (
        lambda t: _with_meta(
            t, {**_meta(t), "events": [*_meta(t)["events"][:-1], {**_meta(t)["events"][-1], "frame_pos": 9999}]}
        ),
        "events",
    ),
    "selection names another frame": (
        lambda t: _with_meta(t, {**_meta(t), "selection": {**_meta(t)["selection"], "frame_index": 12345}}),
        "selection",
    ),
    "event time is not the frame time": (
        lambda t: _with_meta(
            t, {**_meta(t), "events": [{**_meta(t)["events"][0], "t_sec": 0.123}, *_meta(t)["events"][1:]]}
        ),
        "events",
    ),
}


@pytest.mark.parametrize("name", list(DAMAGES))
def test_t_trk_06b_a_damaged_or_inconsistent_file_is_refused_and_the_field_is_named(
    tmp_path: Path, good_file: Path, name: str
):
    damage, field = DAMAGES[name]
    bad = tmp_path / "bad.parquet"
    pq.write_table(damage(pq.read_table(good_file)), bad)
    with pytest.raises(TrackFileError, match=field):
        load_track(bad)


def test_t_trk_06b_the_undamaged_table_passes_through_the_same_path(tmp_path: Path, good_file: Path):
    again = tmp_path / "again.parquet"
    pq.write_table(pq.read_table(good_file), again)  # the harness itself does not break a good file
    assert load_track(again).equals(load_track(good_file))


def test_t_trk_06b_a_file_that_is_not_parquet_or_is_missing_is_refused(tmp_path: Path, good_file: Path):
    garbage = tmp_path / "garbage.parquet"
    garbage.write_bytes(b"this is not a parquet file at all")
    with pytest.raises(TrackFileError, match="parquet"):
        load_track(garbage)
    truncated = tmp_path / "truncated.parquet"
    truncated.write_bytes(good_file.read_bytes()[:200])
    with pytest.raises(TrackFileError, match="parquet"):
        load_track(truncated)
    with pytest.raises(TrackFileError, match="exist|found|read"):
        load_track(tmp_path / "nothing.parquet")


def test_t_trk_06b_the_reader_table_names_the_versions_it_reads(tmp_path: Path, good_file: Path):
    bad = tmp_path / "v9.parquet"
    table = pq.read_table(good_file)
    pq.write_table(_with_meta(table, {**_meta(table), "schema_version": "track/9"}), bad)
    with pytest.raises(TrackFileError, match=r"track/9.*track/1"):
        load_track(bad)


# --- T-TRK-06c: writing ---------------------------------------------------------------------------------------------
def test_t_trk_06c_a_failing_replace_keeps_the_old_file_and_leaves_no_temporary_file(
    tmp_path: Path, rich: TargetTrack, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "track.parquet"
    save_track(path, rich)
    before = path.read_bytes()
    shorter = _first_frames(rich, 100)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(TrackFileError, match="could not write"):
        save_track(path, shorter)
    monkeypatch.undo()
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["track.parquet"]


def test_t_trk_06c_a_missing_folder_is_refused_and_not_created(tmp_path: Path, rich: TargetTrack):
    folder = tmp_path / "no_such_folder"
    with pytest.raises(TrackFileError, match="folder"):
        save_track(folder / "track.parquet", rich)
    assert not folder.exists()


@pytest.mark.parametrize(
    ("damage", "field"),
    [
        (lambda t: dataclasses.replace(t, keypoints=t.keypoints.astype(np.float64)), "keypoints"),
        (lambda t: dataclasses.replace(t, status=t.status.astype(np.int64)), "status"),
        (lambda t: dataclasses.replace(t, status=np.where(t.status == LOST, 9, t.status).astype(np.uint8)), "status"),
        (lambda t: dataclasses.replace(t, scores=t.scores[:-1]), "scores"),
        (lambda t: dataclasses.replace(t, t_sec=t.t_sec[::-1].copy()), "t_sec"),
        (
            lambda t: dataclasses.replace(t, status=np.where(t.status == LOST, TARGET_LOST, t.status).astype(np.uint8)),
            "n_lost",
        ),
        (
            lambda t: dataclasses.replace(
                t, keypoints=np.where((t.status == LOST)[:, None, None], 1.0, t.keypoints).astype(np.float32)
            ),
            "keypoints",
        ),
    ],
    ids=[
        "float64 keypoints",
        "int64 status",
        "status code 9",
        "short scores",
        "time reversed",
        "counts disagree",
        "keypoints on a lost row",
    ],
)
def test_t_trk_06c_an_inconsistent_target_track_is_refused_before_anything_is_written(
    tmp_path: Path, rich: TargetTrack, damage, field: str
):
    path = tmp_path / "track.parquet"
    with pytest.raises(TrackFileError, match=field):
        save_track(path, damage(copy.copy(rich)))
    assert list(tmp_path.iterdir()) == []
