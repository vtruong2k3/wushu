"""One-time download of the pose models into ./models and record them in models/registry.json.

The runtime pipeline never downloads models: it only loads files listed in the registry and
refuses to run when a SHA-256 does not match (see taiji_ai.pose.registry).

Usage:
    .venv/Scripts/python.exe tools/fetch_models.py            # download + register
    .venv/Scripts/python.exe tools/fetch_models.py --verify   # only re-check hashes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"
REGISTRY = MODELS_DIR / "registry.json"

# Source: rtmlib 0.0.16, BodyWithFeet.MODE["balanced"] (OpenMMLab ONNX SDK exports).
MODELS = [
    {
        "name": "yolox_m_humanart",
        "role": "det",
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
        "yolox_m_8xb8-300e_humanart-c2c7a14a.zip",
        "input_size": [640, 640],
        "license_note": "YOLOX code Apache-2.0; weights trained on HumanArt - verify terms before commercial use",
    },
    {
        "name": "rtmpose_m_body7_halpe26",
        "role": "pose",
        "url": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
        "rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.zip",
        "input_size": [192, 256],
        "skeleton": "halpe26/1",
        "license_note": "RTMPose code Apache-2.0; weights trained on body7 (includes research-only "
        "datasets) - verify terms before commercial use",
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract_onnx(zip_path: Path, dest_dir: Path, stem: str) -> Path:
    """Extract the single .onnx file from an SDK zip, rejecting unsafe member paths."""
    with zipfile.ZipFile(zip_path) as z:
        onnx_members = [m for m in z.infolist() if m.filename.lower().endswith(".onnx")]
        if len(onnx_members) != 1:
            raise RuntimeError(f"{zip_path.name}: expected exactly one .onnx, found {len(onnx_members)}")
        member = onnx_members[0]
        if member.filename.startswith(("/", "\\")) or ".." in Path(member.filename).parts:
            raise RuntimeError(f"unsafe path in zip: {member.filename}")
        target = dest_dir / f"{stem}.onnx"
        tmp = target.with_suffix(".onnx.tmp")
        with z.open(member) as src, tmp.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        tmp.replace(target)
        return target


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "taiji-ai-model-fetch"})
    with urllib.request.urlopen(req, timeout=120) as r, dest.open("wb") as f:  # TLS verified by default
        shutil.copyfileobj(r, f)


def fetch() -> None:
    MODELS_DIR.mkdir(exist_ok=True)
    entries = []
    for m in MODELS:
        stem = Path(m["url"]).stem
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / f"{stem}.zip"
            print(f"downloading {m['name']} ...", flush=True)
            download(m["url"], zpath)
            zip_sha = sha256_file(zpath)
            onnx_path = safe_extract_onnx(zpath, MODELS_DIR, stem)
        entry = {k: v for k, v in m.items() if k != "url"}
        entry.update(
            file=onnx_path.name,
            sha256=sha256_file(onnx_path),
            bytes=onnx_path.stat().st_size,
            source_url=m["url"],
            source_zip_sha256=zip_sha,
            downloaded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        entries.append(entry)
        print(f"  -> {onnx_path.name}  sha256={entry['sha256'][:16]}...  {entry['bytes'] / 1e6:.1f} MB")
    registry = {"schema_version": "model-registry/1", "models": entries}
    tmp = REGISTRY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    tmp.replace(REGISTRY)
    print(f"registry written: {REGISTRY}")


def verify() -> int:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    bad = 0
    for e in reg["models"]:
        p = MODELS_DIR / e["file"]
        ok = p.exists() and sha256_file(p) == e["sha256"]
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {e['name']}  {e['file']}")
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    sys.exit(verify() if args.verify else (fetch() or 0))
