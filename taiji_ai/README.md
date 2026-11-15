# taiji-ai

Taijiquan video-analysis MVP: video → HALPE_26 pose → quality masks → three metrics → reference comparison → coach review → report.
Design: `../Docs/TECH_WORKFLOW_V1.md` · Plan: `../Docs/WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md`.

## Requirements

- Windows 10/11 or Linux, Python **3.12** (PyAV 19 requires ≥3.12)
- NVIDIA GPU with a driver that supports **CUDA 13** (onnxruntime-gpu 1.32 ships CUDA 13 runtime + cuDNN 9 via pip; no system CUDA/cuDNN install needed). CPU fallback works but is slow.
- FFmpeg + ffprobe on `PATH`
- [uv](https://docs.astral.sh/uv/) (`py -3.12 -m pip install --user uv`)

## Setup

```powershell
cd taiji_ai
py -3.12 -m uv sync                              # creates .venv from uv.lock
.venv\Scripts\python.exe tools\fetch_models.py   # one-time: YOLOX-m + RTMPose-m HALPE_26 -> models/, writes registry.json
.venv\Scripts\python.exe tools\env_check.py --gpu-smoke
.venv\Scripts\python.exe -m taiji_ai.api               # API on http://127.0.0.1:8007 (serves web/dist when built)
```

In VS Code select the interpreter `taiji_ai\.venv\Scripts\python.exe`.

### Web UI (Node ≥ 24, pnpm)

```powershell
cd taiji_ai\web
pnpm install --frozen-lockfile
pnpm dev           # http://127.0.0.1:5173, proxies /api to the API on 127.0.0.1:8007 (TAIJI_API_PORT)
pnpm lint; pnpm typecheck; pnpm test
pnpm build         # web/dist, then the API serves the UI at http://127.0.0.1:8007/
```

Supported browser: current Chromium (Chrome / Edge).

### Quality gate

Run it after both setups above (it needs `.venv` and `web/node_modules`; a missing piece gives exit 2 with the fix):

```powershell
cd taiji_ai
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check.ps1   # uv lock, ruff, mypy, pytest, web lint/typecheck/test/build, repo hygiene
```

Flags (`-NoGpu`, `-SkipWeb`, `-DryRun`) and exit codes: `AGENTS.md` §7.

## Dependency notes

- `rtmlib` declares `onnxruntime` (CPU), `opencv-python` and `opencv-contrib-python`. They are removed via `[tool.uv] override-dependencies`:
  `onnxruntime-gpu` provides the `onnxruntime` module, `opencv-python-headless` provides `cv2` (rtmlib needs only core + dnn).
- OpenCV is held at `<5` until rtmlib is verified on OpenCV 5.
- The pipeline never downloads models at runtime; `taiji_ai.pose.registry` refuses to load files whose SHA-256 differs from `models/registry.json`.

## Layout

```
src/taiji_ai/
  config.py            paths/settings (TAIJI_DATA_DIR, TAIJI_MODELS_DIR, TAIJI_DEVICE, TAIJI_LOG_LEVEL)
  logs.py              unified logging, per-run log file, absolute path redaction
  io/probe.py          ffprobe metadata (rotation, fps, audio)
  io/frames.py         PyAV frames with real PTS timestamps, VFR detection, display rotation
  pose/skeleton.py     HALPE_26 definition (halpe26/1)
  pose/registry.py     verified model registry
  pose/rtm.py          YOLOX + RTMPose wrapper (detect / estimate separately)
  store/artifacts.py   atomic writes, checksums
  store/db.py          SQLite + numbered migrations (migrations/*.sql)
  track/ quality/ metrics/ compare/ pipeline/ report/   (to be implemented)
  api/                 FastAPI app (`python -m taiji_ai.api`, 127.0.0.1 only): /api/health, SPA serving
web/                   React + Vite + TypeScript UI: src/{api,components,pages}, tests/ (Vitest)
tools/                 check.ps1, repo_hygiene.py, fetch_models.py, env_check.py
tests/                 unit/, contract/ (synthetic FFmpeg fixtures; GPU smoke test), api/ (FastAPI TestClient)
```

## Status

| Module | State |
|---|---|
| io (probe, frames) | done, tested (CFR, VFR, rotation) |
| pose (registry, rtm) | done, tested on GPU |
| store (artifacts, db) | done, tested |
| logging (unified logging, run.log, path redaction) | done, tested (T-CORE-01a..p, BUG-0011) |
| api (app factory, /api/health, errors, SPA serving) | done, tested (T-API-01..04) |
| web (React + Vite: router, react-query, typed API client, status page) | done, tested (Vitest, real-browser smoke) |
| tooling (check.ps1 gate, repo_hygiene) | done, tested (T-TOOL-01..05) |
| track, quality, metrics, compare, pipeline, report | not started |

## Logging

- Entry points call `configure_logging(settings)`. Log lines use ISO-8601 with local timezone offset, padded level, logger name, and `[run=<id>]` context (`[run=-]` outside runs).
- `PathRedactor` sanitizes console output, `run.log` and API error texts: known roots keep their relative tail (`<data>\runs\...`, `<project>\src\...`); every other absolute path (drive, UNC, `\\?\`, also in `repr` form) becomes `<path>`, an unquoted one up to the end of the line. It cannot detect relative file names, free text or URL-encoded paths, so log IDs only (rules in the `taiji_ai.logs` docstring).
- Code convention: log IDs (`run_id`, `recording_id`, pseudonym), never user file names or free text. Library modules use `log = logging.getLogger(__name__)`. Log level configurable via `TAIJI_LOG_LEVEL` (default `INFO`).
