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
  bench/{yolo_onnx,detector_metrics,detector_compare,detector_worker}.py  offline: the detector comparison YOLOX against YOLO11, the adapter, the metrics and the written rule, the tables, one worker per detector (P3.09; nothing of the product imports them)
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
  quality/gaps.py      `interpolate_gaps` / `interpolate_track`: holes of at most 150 ms (anchor to anchor, real time) are bridged and flagged, the rest stays NaN; a gap gets a table row and an outcome (P4.02)
  quality/filters.py   `hampel_outliers` / `hampel_track`: a cell further than 3 robust sigma (floor 2 px) from the median of its 7-row window is set to NaN with the reason `outlier`; `torso_length_px` (P4.03)
  quality/filters.py   (also) `lowpass_layer` / `lowpass_grid`: a zero-phase Butterworth (order 4, 6 Hz) on each continuous run of a joint; a run of at most 15 rows keeps its values and is flagged `filtered = False`; nothing is filtered at 12 fps or less (P4.05)
  quality/lr_swap.py   `detect_lr_swaps` / `detect_lr_swaps_track`: a pair whose two labels jump onto each other's place is a warning (`events`, `suspect`, `blocked` for the gap layer); nothing is corrected (P4.06)
  quality/chain.py     `run_quality_arrays` / `run_quality`: the six stages in their order (mask, swap flag and Hampel on the mask layer, gaps with `blocked`, grid, Butterworth), every layer kept, and the report (P4.07)
  quality/coverage.py  `compute_coverage`: counts with their denominators (observed, bridged, missing; reasons; frames; gaps by outcome; by joint) for the segment and named intervals (P4.07)
  quality/quality_io.py `save_quality` / `load_quality`: `quality.json` (schema `quality/1`, `schemas/quality.py`), atomic and strict, no keypoint value, name or path (P4.07)
  quality/resample.py  `resample_layer` / `resample_gaps`: the gap layer on a regular clock, the identity for a constant frame rate; flagged linear mixes, a pause in the timestamps is NaN `no_frame`; `GridMap.to_source` is the way back to the real timestamps (P4.04)
  bench/umons.py       the UMONS Kinect recordings (D12, CC BY-NC-SA, dev-test only, never on the product path) as input of the quality chain: strict reader, 17 of 26 HALPE joints, plane (y, -z), repeated timestamp = two bodies, run over a folder, tables and CSV; `tools/umons_adapter.py` (P4.08)
  metrics/ compare/ report/   (to be implemented)
  api/                 FastAPI app (`python -m taiji_ai.api`, 127.0.0.1 only): /api/health, SPA serving
config/                ontology_v0.yaml: the 24-form actions, sides, views, flags (draft until the coach signs)
web/                   React + Vite + TypeScript UI: src/{api,components,pages}, tests/ (Vitest)
tools/                 check.ps1, repo_hygiene.py, fetch_models.py, env_check.py, render_ontology_review.py, bench_pose.py, pose_audit.py, detector_compare.py
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
| detector comparison (`tools/detector_compare.py`, `bench/{yolo_onnx,detector_*}.py`) | done, tested (T-DET-01..10); offline measurement only, the stack is unchanged: on D20 YOLO11m is not materially better than the shipping YOLOX by the rule written before the numbers (recall 100.0 % against 98.2 % on 169 labelled frames, p = 0.25; no run to review in 3,785 clip frames), so DEC-0005 stands (DEC-0044); YOLO11m has tighter and steadier boxes and is 1.65 times faster end to end; Ultralytics and the YOLO11 weights are AGPL-3.0: used once in an isolated environment, now deleted, never imported or registered; report `Docs/reports/p3_pose_benchmark.md` appendix A |
| track (target choice, association, target over time, `track.parquet`) | done, tested (T-TRK-01a..m, T-TRK-02, T-TRK-03, T-TRK-04, T-TRK-05, T-TRK-06); the thresholds (`reattach_cost`, `max_reattach_s`) are provisional: no real clip with a real absence yet |
| audit (`tools/pose_audit.py`, `audit/*`) | done, tested (T-AUDIT-01..06, 04c); run over the four D20 videos at N = 1 and N = 5, 250 frames reviewed by agents and the maintainer; report `Docs/reports/p3_failure_cases.md`; images and keypoint files stay in `data/` (ignored by git) |
| quality (mask, gaps, Hampel, the uniform grid, the Butterworth low-pass and the swap flag: `quality/mask.py`, `quality/gaps.py`, `quality/filters.py`, `quality/resample.py`, `quality/lr_swap.py`, the chain and its report: `quality/chain.py`, `quality/coverage.py`, `quality/quality_io.py`, `quality/layers_io.py`, `schemas/quality.py`, `schemas/quality_layers.py`) | mask done, tested (T-QLT-01, T-QLT-02; reasons `low_conf`, `non_finite`, `not_tracked`, `frame_invalid`, `outlier` from the Hampel stage and `no_frame` from the resampling); `tau_kp` 0.3 and the ten essential joints are the W6 values, evaluated by P3.08, not tuned; gap bridging done, tested (T-QLT-03..05): a gap of at most 150 ms between its two observed anchors is filled linearly in real time and flagged `interpolated`; nothing is extrapolated, held or zero-filled; a gap with a cell of a frame that is not the target's is never bridged; `blocked` input for P4.06; on D20 the 150 ms is kept (leave-gap-out p95 error 2.6 to 3.1 % of the torso for 1 to 3 missing frames, DEC-0045); Hampel done, tested (T-QLT-06): window 7, 3 sigma from 1.4826 x MAD, sigma never under 2 px (the rule as written flagged 7.1 % of the D20 cells, the floor gives 0.49 %, DEC-0046), an outlier is NaN with the reason `outlier` and only the gap layer repairs it, flagged; Hampel is a cheap safety net and finds about a third of the cells that P3.08 named as wrong, not a detector of swaps or lasting errors; uniform grid done, tested (T-QLT-07): the identity when every frame time is within 1 ms of a straight line (all of D20, 22 of 22 chunks), otherwise a regular grid on the lattice that the frame times follow (X.31, DEC-0052: a step that counts the frames of every interval and the fitted phase; a grid time within 1 ms of a frame is a copy of it, up to 1 ms off in time) with flagged linear mixes elsewhere, NaN (never filled) next to a hole, NaN `no_frame` across a pause of more than 150 ms, and `to_source` back to the real timestamps (a row outside the grid has no value; round trip on real motion at the worst phase: p95 1.2 % of the torso, DEC-0047); Butterworth done, tested (T-QLT-08, T-QLT-09): zero phase (`sosfiltfilt`), order 4, 6 Hz (W6, not tuned: P5.08), each continuous run of a joint filtered on its own, a run of 15 rows or fewer keeps its values and is flagged, nothing is filtered at 12 fps or less, reasons and flags copied; on D20 99.99 % of the usable cells are filtered, a cell moves 0.83 px (p50) and the jitter falls to 0.32; with 1 px of noise the speed in a still pause falls from p50 49 to 13 px/s (DEC-0048); swap flag done, tested (T-QLT-10): a crossed jump of a left/right pair (both labels move at least 0.2 torso onto each other's place) between two observed rows is an event, events are paired within 0.5 s into `suspect` rows, `blocked` goes to the gap layer, no value or label is changed; on D20 270 events, all in the side-view lunges of one video, 0.12 % of the rows blocked, and on SYN-08 the suspect rows are exactly the swap mask (DEC-0049); chain and coverage done, tested (T-QLT-11): `run_quality` wires the six stages in their order (the swap flag and Hampel both read the mask layer, the gap layer gets the swap mask as `blocked`, the Hampel floor is 1 % of the torso), keeps every layer and returns the report, which counts (no fractions) observed, bridged and missing cells, reasons, frames and gaps by outcome for the segment and named intervals; `quality.json` (schema `quality/1`) is atomic, strict and self-consistent and holds no keypoint value, name or path; the two array layers are `pose_masked.npz` (the mask layer and the swap flags, `pose_masked/1`) and `pose_filtered.npz` (the final layer on the grid and the stored map back to the rows, `pose_filtered/1`: X.29, `quality/layers_io.py`, T-QLT-13): atomic, strict, checked against themselves, `on_source()` equal bit for bit to `filtered_on_source()`, `data_sources` carried; on D20 54.8 % of the rows are frames of the target and 99.91 % of the cells of those rows are usable, the whole chain and report take 0.33 s per 10,000 rows (DEC-0050); `pose_masked.npz` and `pose_filtered.npz` have no file format yet (X.29) |
| umons (`bench/umons.py`, `tools/umons_adapter.py`) | done, tested (T-QLT-12a..h; six real files under the `dataset` marker): the quality chain ran on all 111 UMONS Kinect files (703,146 rows, 12 performers) with no error in 30.5 s; no Kinect clock is uniform, so the non-identity grid ran on real data (275 pauses, 19,148 dropped-frame steps; after X.31 91.0 % of the grid rows are copies of a real row and 8.8 % flagged mixes, before it 96.5 % were mixes); a repeated timestamp is two bodies in one frame and is not tracked; over the 17 joints Kinect has 98.0 % of the cells are observed; report `Docs/reports/p4_umons_quality.md`; out of domain (13 techniques, not the 24 forms), no product number (DEC-0051) |
| metrics: the types of a result (`schemas/metric.py`, `metrics/series.py`) | P5.01 done, tested (T-SCH-02a..g): a series row is one grid row of `pose_filtered.npz`; `reason` (uint8: 0 measured, 1 to 6 the quality reasons, 16 to 22 the reasons of the metric) is the single source of truth and the valid intervals, the three nested coverage counts (`measured <= quality <= eligible <= total`) and the counts by reason are derived from it and checked; `insufficient_evidence` has no number (null, never 0) and a reason; an `experimental` summary is never `conclusive`; a threshold output names its source (`signed_record` needs `enabled`, `unsigned_config` only while `experimental`); the summary file is `metric_summary/1`; no metric is computed yet (P5.02 to P5.07) |
| compare, pipeline, report | not started |

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
