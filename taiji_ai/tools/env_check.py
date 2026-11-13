"""Print an environment / hardware inventory (P00.05) as Markdown.

Usage:
    .venv/Scripts/python.exe tools/env_check.py                 # print
    .venv/Scripts/python.exe tools/env_check.py --gpu-smoke     # also load models on GPU
    .venv/Scripts/python.exe tools/env_check.py > hardware_inventory.md
"""

from __future__ import annotations

import argparse
import importlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PACKAGES = [
    "numpy",
    "scipy",
    "pandas",
    "pyarrow",
    "pydantic",
    "av",
    "cv2",
    "onnxruntime",
    "rtmlib",
    "fastapi",
    "uvicorn",
    "plotly",
    "jinja2",
]


def _cmd_first_line(*cmd: str) -> str:
    exe = shutil.which(cmd[0])
    if not exe:
        return "not found"
    try:
        out = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


def collect(gpu_smoke: bool) -> list[str]:
    gpu = _cmd_first_line("nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader")
    lines = ["# Environment inventory", "", "## System", ""]
    lines += [
        f"- OS: {platform.platform()}",
        f"- Python: {sys.version.split()[0]} ({sys.executable})",
        f"- GPU: {gpu}",
        f"- FFmpeg: {_cmd_first_line('ffmpeg', '-version')}",
        f"- ffprobe: {_cmd_first_line('ffprobe', '-version')}",
        "",
        "## Python packages",
        "",
    ]
    for name in PACKAGES:
        try:
            mod = importlib.import_module(name)
            lines.append(f"- {name}: {getattr(mod, '__version__', 'installed')}")
        except Exception as e:  # noqa: BLE001
            lines.append(f"- {name}: MISSING ({e.__class__.__name__})")
    try:
        import onnxruntime as ort

        lines += ["", f"- onnxruntime providers: {ort.get_available_providers()}"]
    except Exception:  # noqa: BLE001
        pass

    lines += ["", "## Models", ""]
    from taiji_ai.config import get_settings
    from taiji_ai.pose.registry import ModelIntegrityError, ModelRegistry

    s = get_settings()
    try:
        reg = ModelRegistry(s.registry_path)
        for e in reg.entries.values():
            lines.append(f"- {e.role}: {e.name} `{e.file}` sha256 `{e.sha256[:16]}` OK")
    except ModelIntegrityError as e:
        lines.append(f"- registry problem: {e}")
        reg = None

    if gpu_smoke and reg is not None:
        import time

        import numpy as np

        from taiji_ai.pose.rtm import PoseEstimator

        est = PoseEstimator(reg, device=s.device)
        img = np.full((1080, 1920, 3), 127, np.uint8)
        box = np.array([[760, 140, 1160, 1040]], np.float32)
        est.detect(img)
        est.estimate(img, box)
        t = time.perf_counter()
        for _ in range(20):
            est.detect(img)
        det_ms = (time.perf_counter() - t) / 20 * 1000
        t = time.perf_counter()
        for _ in range(20):
            est.estimate(img, box)
        pose_ms = (time.perf_counter() - t) / 20 * 1000
        lines += [
            "",
            "## GPU smoke test (1080p frame, synthetic)",
            "",
            f"- providers: {est.providers}",
            f"- detector: {det_ms:.1f} ms/frame; pose: {pose_ms:.1f} ms/person",
        ]
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu-smoke", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(collect(args.gpu_smoke)))
