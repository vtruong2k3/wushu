"""Artifact helpers: atomic writes and checksums.

Every artifact is written to ``<name>.tmp`` in the same directory, flushed + fsynced, then moved
into place with ``os.replace`` so readers never see a half-written file. Manifests are written
last: a stage without its manifest is treated as not completed.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write_bytes(path: str | Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def atomic_write_text(path: str | Path, text: str) -> Path:
    return atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: str | Path, obj: Any) -> Path:
    return atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def atomic_save_npz(path: str | Path, **arrays: np.ndarray) -> Path:
    """Save arrays as compressed .npz atomically. NaN values are preserved as-is.

    Array names 'file' and 'allow_pickle' are reserved (they collide with np.savez keywords) and raise ValueError;
    object arrays are refused with ValueError because np.load will not read pickles by default.
    """
    reserved = {"file", "allow_pickle"}
    clash = reserved.intersection(arrays)
    if clash:
        raise ValueError(f"Reserved array names cannot be saved in .npz: {sorted(clash)}")
    for name, arr in arrays.items():
        if getattr(arr, "dtype", None) == np.dtype(object):
            raise ValueError(f"Object arrays cannot be saved without pickle: {name!r}")
    buf = io.BytesIO()
    np.savez_compressed(buf, allow_pickle=False, **arrays)
    return atomic_write_bytes(path, buf.getvalue())


def atomic_write_parquet(path: str | Path, table: pa.Table) -> Path:
    """Write an Arrow table as Parquet atomically; schema metadata (for example ``time_base``) is kept."""
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return atomic_write_bytes(path, buf.getvalue())


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
