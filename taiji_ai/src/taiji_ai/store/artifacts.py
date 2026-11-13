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
    """Save arrays as compressed .npz atomically. NaN values are preserved as-is."""
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrays)
    return atomic_write_bytes(path, buf.getvalue())


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
