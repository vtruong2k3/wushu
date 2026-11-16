from __future__ import annotations

import json
import sqlite3

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from taiji_ai.config import PROJECT_ROOT
from taiji_ai.pose import skeleton as sk
from taiji_ai.pose.registry import ModelIntegrityError, ModelRegistry
from taiji_ai.store.artifacts import (
    atomic_save_npz,
    atomic_write_json,
    atomic_write_parquet,
    read_json,
    sha256_file,
)
from taiji_ai.store.db import apply_migrations, connect

MIGRATIONS = PROJECT_ROOT / "migrations"


# --- skeleton -------------------------------------------------------------------------------
def test_skeleton_shape_and_pairs():
    assert sk.NUM_JOINTS == 26 and len(set(sk.JOINTS)) == 26
    for a, b in sk.LR_PAIRS:
        na, nb = sk.JOINTS[a], sk.JOINTS[b]
        assert na[0] == "L" and nb[0] == "R" and na[1:] == nb[1:]
    perm = sk.mirror_index()
    assert tuple(perm[i] for i in perm) == tuple(range(26))  # involution
    assert sk.IDX["Hip"] == 19 and sk.IDX["Neck"] == 18


# --- artifacts ------------------------------------------------------------------------------
def test_atomic_writes_leave_no_tmp_and_keep_nan(tmp_path):
    p = atomic_write_json(tmp_path / "a" / "m.json", {"x": 1, "name": "Thái Cực"})
    assert read_json(p) == {"x": 1, "name": "Thái Cực"}
    arr = np.array([[1.0, np.nan], [np.nan, 4.0]])
    q = atomic_save_npz(tmp_path / "pose.npz", kp=arr)
    with np.load(q) as z:
        assert np.array_equal(np.isnan(z["kp"]), np.isnan(arr))
    assert not list(tmp_path.rglob("*.tmp"))


def test_atomic_write_parquet_keeps_columns_types_and_metadata_and_leaves_no_tmp(tmp_path):
    table = pa.table(
        {
            "frame_index": pa.array([0, 1, 2], pa.int32()),
            "pts": pa.array([0, 512, 1024], pa.int64()),
            "t_sec": pa.array([0.0, 1 / 30, 2 / 30], pa.float64()),
        }
    ).replace_schema_metadata({b"time_base": b"1/15360", b"start_pts": b"0"})
    p = atomic_write_parquet(tmp_path / "rec" / "pts.parquet", table)
    back = pq.read_table(p)
    assert back.equals(table, check_metadata=True)
    assert back.schema.types == [pa.int32(), pa.int64(), pa.float64()]
    assert back.schema.metadata[b"time_base"] == b"1/15360"
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("name", ["allow_pickle", "file"])
def test_bug_0006_reserved_key_raises(tmp_path, name):
    with pytest.raises(ValueError, match="Reserved"):
        atomic_save_npz(tmp_path / "x.npz", **{name: np.array([1, 2])})
    assert not (tmp_path / "x.npz").exists(), "a rejected save must leave no file"


def test_bug_0006_object_array_rejected(tmp_path):
    obj_arr = np.array(["hello", {"a": 1}], dtype=object)
    with pytest.raises(ValueError, match="Object arrays"):
        atomic_save_npz(tmp_path / "obj.npz", data=obj_arr)
    assert not (tmp_path / "obj.npz").exists(), "a rejected save must leave no file"


# --- db -------------------------------------------------------------------------------------
def test_migrations_apply_once_and_enforce_constraints(tmp_path):
    conn = connect(tmp_path / "app.sqlite3", MIGRATIONS)
    assert apply_migrations(conn, MIGRATIONS) == []  # second run is a no-op
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"participant", "recording", "segment", "run", "finding", "metric_record", "report"} <= tables
    conn.execute("INSERT INTO participant(participant_id, consent_ref) VALUES ('P01', 'C-1')")
    conn.execute(
        "INSERT INTO recording(recording_id, participant_id, session_id, take_id, camera_id, sha256,"
        " source_path, width, height) VALUES ('r1','P01','S1','T1','camA','abc','x.mp4',1920,1080)"
    )
    with pytest.raises(sqlite3.IntegrityError):  # end_s must be > start_s
        conn.execute(
            "INSERT INTO segment(segment_id, revision, recording_id, start_s, end_s, action,"
            " view_category, created_by) VALUES ('s1',1,'r1',5.0,4.0,'m01','front','coach')"
        )
    with pytest.raises(sqlite3.IntegrityError):  # unknown recording (foreign key)
        conn.execute(
            "INSERT INTO segment(segment_id, revision, recording_id, start_s, end_s, action,"
            " view_category, created_by) VALUES ('s2',1,'nope',1.0,2.0,'m01','front','coach')"
        )


# --- registry -------------------------------------------------------------------------------
def _fake_registry(tmp_path, content: bytes = b"onnx-bytes"):
    (tmp_path / "pose.onnx").write_bytes(content)
    (tmp_path / "det.onnx").write_bytes(b"det-bytes")
    reg = {
        "schema_version": "model-registry/1",
        "models": [
            {"name": "p", "role": "pose", "file": "pose.onnx", "sha256": sha256_file(tmp_path / "pose.onnx"),
             "input_size": [192, 256], "skeleton": "halpe26/1"},
            {"name": "d", "role": "det", "file": "det.onnx", "sha256": sha256_file(tmp_path / "det.onnx"),
             "input_size": [640, 640]},
        ],
    }  # fmt: skip
    (tmp_path / "registry.json").write_text(json.dumps(reg), encoding="utf-8")
    return tmp_path / "registry.json"


def test_registry_verifies_hashes(tmp_path):
    reg = ModelRegistry(_fake_registry(tmp_path))
    assert reg.by_role("pose").skeleton == "halpe26/1"
    (tmp_path / "pose.onnx").write_bytes(b"tampered")
    with pytest.raises(ModelIntegrityError, match="sha256 mismatch"):
        ModelRegistry(tmp_path / "registry.json")


def test_registry_missing_file(tmp_path):
    path = _fake_registry(tmp_path)
    (tmp_path / "det.onnx").unlink()
    with pytest.raises(ModelIntegrityError, match="missing"):
        ModelRegistry(path)
