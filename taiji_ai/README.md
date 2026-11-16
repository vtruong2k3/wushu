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

```text
src/taiji_ai/
  config.py            paths/settings (TAIJI_DATA_DIR, TAIJI_MODELS_DIR, TAIJI_DEVICE, TAIJI_LOG_LEVEL, TAIJI_MAX_SOURCE_BYTES, TAIJI_MAX_SOURCE_DURATION_S)
  logs.py              unified logging, per-run log file, absolute path redaction
  io/probe.py          ffprobe metadata (rotation, fps, container, audio)
  io/frames.py         PyAV frames with real PTS timestamps, integer-tick scan, VFR rule (`tick_median`), display rotation
  io/ingest.py         `ingest_recording`: read-only copy, SHA-256, `pts.parquet`, `recording.json`, database row (P2.02)
  io/proxy.py          `make_proxy`: browser H.264 720p, strips metadata, timestamp check, `proxy.json` (P2.03)
  io/audio.py          audio extraction to 16 kHz mono WAV (`audio.wav`), cached in recording folder; refuses a track with dropped samples (P2.04)
  io/audio_sync.py     ZNCC envelope cross-correlation, sub-ms parabolic peak, end window on the stretch both cameras recorded, video timeline, drift with a 500 ppm cross-check (P2.04)
  io/flash.py          brightness series, MAD flash onset detection, one-to-one pair matching and residual validation (P2.05, X.23)
  io/sync_rule.py      sync usability decision rule: residual ≤ 1 frame (P2.06)
  pose/skeleton.py     HALPE_26 definition (halpe26/1, verified on real frames in P3.01)
  pose/order_check.py  structure check of one skeleton: does the index mean what skeleton.py says (P3.01)
  pose/registry.py     verified model registry
  pose/rtm.py          YOLOX + RTMPose wrapper (detect / estimate separately)
  pose/runner.py       `run_pose`: raw pose of everyone in a segment by real PTS, detector every N frames (P3.02)
  pose/raw_io.py       `save_pose_raw` / `load_pose_raw`: `pose_raw.npz`, schema `pose_raw/1`, strict and atomic (P3.03)
  schemas/pose.py      header model of `pose_raw.npz` (`PoseRawMeta`)
  bench/timing.py      RTF, per-frame latency, 1 s windows, the timing wrapper of the pose model (P3.07)
  bench/gpu.py         NVML through ctypes and the VRAM sampler (P3.07)
  bench/compare.py     compare two pose runs (persons, distances, entry delay) and their target tracks (P3.07)
  bench/decision.py    the rule, written before the measurement, that recommends the detector cadence N (P3.07)
  bench/{clips,worker,orchestrate,report}.py  the D20 clips, the worker of one N, the run, the report tables (P3.07)
  audit/scan.py        the pose pass over the D20 videos in chunks of 300 s, resumable (P3.08)
  audit/{signals,select,labels,summary}.py  per-frame measures of the target's pose, the choice of the frames to look at, the review file, the numbers and tables (P3.08)
  audit/{render,analyse}.py  skeleton overlays and contact sheets, the analysis of two passes into candidates (P3.08)
  track/target.py      `select_target`: the performer on the first frame (largest box near the centre, or a user box) (P3.04)
  track/associate.py   `associate_tracks`: Hungarian association of persons frame to frame, track ids, `match_margin` (P3.05)
  track/geometry.py    keypoint hull, IoU and usable boxes shared by the others
  track/state.py       `resolve_target`: the performer over time: tracked / lost / target_lost / before_target, re-attachment by cost, `needs_reselect` (P3.06)
  track/track_io.py    `save_track` / `load_track`: `track.parquet`, schema `track/1`, strict and atomic (P3.06)
  schemas/track.py     header model of `track.parquet` (`TrackMeta`, `TrackEvent`)
  pipeline/sync_take.py `sync_take`: orchestrate audio sync, flash validation, write `sync.json`, manage DB (P2.06)
  store/artifacts.py   atomic writes, checksums
  store/db.py          SQLite + numbered migrations (migrations/*.sql)
  schemas/ontology.py  ontology v0 models, loader and `check_segment` (reads config/ontology_v0.yaml)
  schemas/_base.py     manifest base: strict models, atomic write, validated read (ManifestError)
  schemas/recording.py recording.json, proxy.json and the ingest input (recording/1, proxy/1)
  schemas/sync.py      sync.json and the time mapping between two cameras (sync/1)
  store/participants.py participant registry: consent answers and audit log (P2.08)
  store/recordings.py  queries and insert of the `recording` table (P2.02)
  store/sync.py        queries and upsert/delete of the `sync` table (P2.06)
  cli.py               command line: `taiji participant add, set, show`, `taiji ingest`, `taiji proxy`, and `taiji sync`
  quality/mask.py      the mask layer: low_conf, non_finite, not_tracked, frame_invalid, with a reason for every NaN (P4.01)
  metrics/ compare/ report/   (to be implemented)
  api/                 FastAPI app (`python -m taiji_ai.api`, 127.0.0.1 only): /api/health, SPA serving
config/                ontology_v0.yaml: the 24-form actions, sides, views, flags (draft until the coach signs)
web/                   React + Vite + TypeScript UI: src/{api,components,pages}, tests/ (Vitest)
tools/                 check.ps1, repo_hygiene.py, fetch_models.py, env_check.py, render_ontology_review.py, bench_pose.py, pose_audit.py
tests/                 unit/, contract/ (synthetic FFmpeg fixtures; GPU smoke test), api/ (FastAPI TestClient)
tests/helpers/         synth.py synthetic HALPE_26 skeleton generator (F-SYN, SYN-01..12)
```

## Status

| Module | State |
|---|---|
| io (probe, frames) | done, tested (CFR, VFR, rotation, coarse time bases: T-IO-12, BUG-0046) |
| ingest (io/ingest.py, store/recordings.py, `taiji ingest`) | done, tested (T-IO-06..09, 12..21; clips trimmed on a phone count decoded frames only, BUG-0052); audio and sync are P2.04..P2.06 |
| proxy (io/proxy.py, `taiji proxy`) | done, tested (T-IO-10..11, 22..27; height-capped, metadata stripped, web-ready, timestamps checked, failures reported) |
| audio sync & flash validation (io/audio.py, io/audio_sync.py, io/flash.py) | done, tested (T-SYNC-01..04, 01b..d, 04b..n, 06..10; 16 kHz mono WAV cache, ZNCC cross-correlation, sub-ms peak, drift, flash onset detection on real PTS, residual in ms and frames of slower camera) |
| sync usability & pipeline (io/sync_rule.py, pipeline/sync_take.py, store/sync.py, `taiji sync`) | done, tested (T-SYNC-05, 05b..d; usability decision rule residual ≤ 1 frame, atomic sync.json, SQLite sync row, CLI) |
| pose (registry, rtm, order check, runner, raw I/O) | done, tested on GPU; `halpe26/1` verified on real frames (P3.01); `run_pose` (P3.02); `pose_raw.npz` save/load (P3.03) |
| store (artifacts, db) | done, tested |
| logging (unified logging, run.log, path redaction) | done, tested (T-CORE-01a..p, BUG-0011) |
| api (app factory, /api/health, errors, SPA serving) | done, tested (T-API-01..04) |
| web (React + Vite: router, react-query, typed API client, status page) | done, tested (Vitest, real-browser smoke) |
| tooling (check.ps1 gate, repo_hygiene) | done, tested (T-TOOL-01..05) |
| test helpers (F-SYN skeleton generator, SYN-01..12) | done, tested (T-SYN-01..04) |
| ontology (schemas/ontology.py, config/ontology_v0.yaml, tools/render_ontology_review.py) | code done, tested (T-DATA-01a..l); the 24-action content is `draft_unconfirmed` until the coach signs; `Docs/discovery/ontology_review_sheet.md` is generated from the YAML (stale-guard test) |
| manifests (schemas/_base, recording, sync) | done, tested (T-SCH-01a..i); `recording.json` and `proxy.json` are written by ingest and P2.03, `sync.json` by P2.06 |
| participants + CLI (store/participants.py, cli.py) | done, tested (T-DATA-05a..j); the consent form maps to it (`Docs/consent_form.md` B1) |
| bench (`tools/bench_pose.py`, `bench/*`) | done, tested (T-BENCH-01..09); measured on D20 (not P1.09): RTF 1.23 / 0.335 / 0.259 for N = 1 / 5 / 10, peak VRAM 1.8 to 2.0 GB, report `Docs/reports/p3_pose_benchmark.md`; the written rule recommends N = 1, the default stays 5 until the maintainer decides |
| track (target choice, association, target over time, `track.parquet`) | done, tested (T-TRK-01a..m, T-TRK-02, T-TRK-03, T-TRK-04, T-TRK-05, T-TRK-06); the thresholds (`reattach_cost`, `max_reattach_s`) are provisional: no real clip with a real absence yet |
| quality (mask: `quality/mask.py`) | mask done, tested (T-QLT-01, T-QLT-02; reasons `low_conf`, `non_finite`, `not_tracked`, `frame_invalid`); `tau_kp` 0.3 and the ten essential joints are the W6 values, evaluated by P3.08, not tuned; no file format yet (X.29); gaps, filters, swap flag and coverage not started |
| metrics, compare, pipeline, report | not started |

## Command line

`taiji` is declared in `pyproject.toml`; run `py -3.12 -m uv sync` once to install the command, or call
`.venv\Scripts\python.exe -m taiji_ai.cli`. Register a pseudonym with the answers of a signed consent form before any
recording is ingested:

```powershell
taiji participant add --id P03 --consent-ref CONSENT-2026-011 --analysis yes --train no --share no --retention 2027-12-31 --actor cli:O
taiji participant set --id P03 --train yes --actor cli:O
taiji participant show --id P03
```

Every consent answer is required (`yes` or `no`); `--analysis no` is refused, because without analysis consent no
recording is accepted. `--actor` is a role code (`cli:O`, `cli:H1`), never a person's name, and goes to the audit log.
Exit codes: 0 ok, 1 refused (the message says why) or a proxy that is missing or failed its timestamp check, 2 usage
error. The command `sync` comes with P2.06.

Bring one phone video into the system (the participant must be registered with analysis consent; the file is only read):

```powershell
taiji ingest "D:\phone\clip.mp4" --participant P03 --session S01 --take S01-P03-T02 --camera camA --role main_axis --camera-height-m 1.1 --camera-distance-m 4.5 --fps-setting 30 [--proxy]
```

Generate or remake the H.264 720p browser proxy for a recording:

```powershell
taiji proxy <recording_id>
```

The proxy keeps the source timestamps and is checked against `pts.parquet`. A proxy that fails the check (or that cannot
be made after `taiji ingest --proxy`) exits with code 1 and still prints the recording ID: the recording is stored, the
failed proxy stays on disk marked `passed: false` in `proxy.json`, and the web UI must not use it for frame-accurate
work. Run `taiji proxy <recording_id>` again to remake it.

The command prints `ingested <recording_id> (take ..., camA)`, or `already ingested <recording_id>` when the same file was
ingested before under the same IDs. It copies the video to `data/recordings/<recording_id>/source.<ext>` (read-only) and
writes `pts.parquet` (the real frame timestamps), then `recording.json` last, then one row in the database. A file that
cannot be read, has no video stream, is longer than 30 minutes or larger than 20 GB (`TAIJI_MAX_SOURCE_DURATION_S`,
`TAIJI_MAX_SOURCE_BYTES`), or belongs to a take and camera that already has a recording, is refused and leaves nothing
behind. The second camera of a take uses the same `--take` and its own `--camera`; a retake needs a new take ID. Neither
the path nor the file name is printed or logged. `data/` is never committed. If a folder named `.orphan-<id>` appears
under `data/recordings/`, the database row could not be written: the folder is complete but unused. Ingest the file
again, then delete the orphan folder by hand (no tool lists orphans yet; the database never points to one).

## Logging

- Entry points call `configure_logging(settings)`. Log lines use ISO-8601 with local timezone offset, padded level, logger name, and `[run=<id>]` context (`[run=-]` outside runs).
- `PathRedactor` sanitizes console output, `run.log` and API error texts: known roots keep their relative tail (`<data>\runs\...`, `<project>\src\...`); every other absolute path (drive, UNC, `\\?\`, also in `repr` form) becomes `<path>`, an unquoted one up to the end of the line. It cannot detect relative file names, free text or URL-encoded paths, so log IDs only (rules in the `taiji_ai.logs` docstring).
- Code convention: log IDs (`run_id`, `recording_id`, pseudonym), never user file names or free text. Library modules use `log = logging.getLogger(__name__)`. Log level configurable via `TAIJI_LOG_LEVEL` (default `INFO`).
