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
| metrics: the geometry (`metrics/geometry.py`) | P5.02 done, tested (T-MET-01, T-MET-02): the middle of the hips and of the shoulders (Appendix B, not the model's own Hip and Neck), the trunk length, the scale Λ (median over the rows given, equal to `quality.torso_length_px` on a layer without a bridged cell), the reason of the first unusable joint of a list (1 to 6) and the rows that lean on a bridged value, the camera roll from a user-drawn vertical line (sign of θ, within 45 degrees), the roll correction of coordinates and the lean angle; on the generator: Λ within the noise, roll exact, corrected θ within 0.5 degree at 1 px noise; no metric is computed yet (P5.03 to P5.07) |
| metrics: hip height A (`metrics/hip_height.py`, `metrics/rows.py`) | P5.03 done, tested (T-MET-03): `h_A = y_H / Λ_take` for the rows of a segment (never the margins), `Λ_take` from the `PoseFiltered` of the reference standing segment (same recording), the reason of every row in the order of P5.01 (outside the coach's stable intervals, flag `perspective_shift`, first hip without a value, no reference, no scale, run too short), range P95 - P5 with at least two rows and the extremes as events, `experimental` and never conclusive; the minimums are arguments, none is invented; on the generator the range is within 2.1 % of 2A (SYN-02, 5 % allowed) and 0.005 Λ of the truth (SYN-09, 0.02 allowed); variant B is P5.04 |
| metrics: hip height B (`hip_height_b` in `metrics/hip_height.py`) | P5.04 done, tested (T-MET-04, T-MET-05): `h_B = (g - y_H) / Λ_segment` where `g` is the lowest valid joint of the ankles and heels after the roll is taken out, `Λ_segment` the median trunk of all valid rows of the segment; a true height (up is positive, the event `max` is the highest hip), the same rows, reasons, range and summary as A through one shared tail (A unchanged); on the generator B is within 2.1 % of 2A (SYN-02, 5 % allowed) and within 0.0018 Λ of the truth on six pinhole geometries (SYN-09, 0.02 allowed), A within 0.0051 Λ; no order between A and B is asserted (DEC-0014): the variant is chosen against hand measurements (P10) |
| metrics: trunk lean (`metrics/trunk_lean.py`; shared glue `metrics/rows.py`) | P5.05 done, tested (T-MET-06, T-MET-07): `θ = atan2(x_S - x_H, y_H - y_S) - roll` for the rows of a segment, positive to the image right; two metrics, `trunk_lean_lr` (front view) and `trunk_lean_fb` (side view); the view is the segment's, a view that does not fit gives every row 17 and `insufficient_evidence` with no number, `orientation_change` gives 18, the coach's intervals are optional; the signed median and the median and P95 of `\|θ\|`, no event and no duration over a threshold (that needs a signed record); the view gate, the series assembly and the reason without evidence are shared with hip height, whose output is unchanged; on the generator the median error of `θ` is under 0.14 degree at 1 px noise (0.5 allowed) |
| metrics: speed of a joint group (`metrics/tempo.py`; neighbours and scale in `metrics/rows.py`) | P5.06 done, tested (T-MET-08): `V_G = median over the usable joints of ‖p(k+1) - p(k-1)‖ / (t(k+1) - t(k-1)) / Λ` in body lengths per second on the real clock of the grid; three metrics, `speed_hands`, `speed_hips`, `speed_feet`; the neighbours are rows of the layer (margins included), so only a row with no neighbour in the grid is `run_edge`; a joint is usable when both neighbour cells have a value (its own cell is not read, a bridge counts and is reported); `Λ` is the median trunk of the segment (shared with hip height B, output unchanged); `perspective_shift` blocks, the coach's intervals are optional; `segment_duration_s`, `speed_median`, `speed_cv` (null at a mean of 0) and `bridged_rows`, no event and no pause (P5.07); `experimental`; on the generator the median relative error is 0.00085 (SYN-07) and 0.00025 (SYN-05) at noise 0 (5 % allowed), and a joint that does not move reads a noise floor of about 0.07 Λ/s at 1 px of noise |
| metrics: pauses of a joint group (`find_pauses` and `pause_tau`, `pause_min_s` of `group_speed` in `metrics/tempo.py`) | P5.07 done, tested (T-MET-09, T-MET-10): a pause is a maximal run of measured rows with `V < τ` (strict) that lasts `n × step >= d_min`, the interval `[t_first, t_last + step)`; `τ` (body lengths per second) and `d_min` (seconds) are optional arguments given together, with no default (none given: the profile only); a row that is not measured ends a run and is never bridged; a pause next to a row the pose lost is cut and counted in `pause_cut_count`; statistics `pause_count`, `pause_total_s`, `pause_longest_s`, `pause_cut_count` (null when no measured run lasts `d_min`), one `pause` event each, labelled `unsigned_config`, `experimental`; on the generator at noise 0 the count is right (2 on SYN-05, 1 on SYN-07) and the boundaries are within 0.53 steps of the true crossings at `τ` = 10 % of the peak, the turning point of a movement is a pause unless `d_min` removes it, and `τ` has to clear the noise floor (a still joint reads up to 0.18 Λ/s at 1 px of noise) |
| metrics: cut-off ablation (`bench/filter_ablation.py`, `tools/filter_ablation.py`; report `Docs/reports/p5_filter_ablation.md`) | P5.08 done, tested (T-MET-12, T-MET-13, M-MET-01): the final layer of a run at 4, 6, 8 Hz and no filter (only `cutoff_hz` changes; the grid, reasons, flags and segment are checked to be the same), the speed quantiles, the pauses of a `(τ, d_min)` grid and the hip range per cut-off, and the agreement with 6 Hz (paused share, row-level IoU, count, matched boundary shift), pooled over runs; the tool runs the 22 D20 chunks and the 111 UMONS files (`python tools/filter_ablation.py d20 ...` and `umons ...`), the generator's truth tables come from `tests/helpers/ablation_sweep.py`; findings: the pauses depend strongly on the cut-off (4 Hz finds the pauses near the floor that 6 Hz loses, at the price of a step more at a sharp onset), the hip amplitude does not (at most 1.5 % on real data), `τ`, `d_min` and the cut-off are one triple; the default 6 Hz is unchanged |
| metrics: signed records (`schemas/metric_record.py`, `metrics/records.py`, `store/metric_records.py`, migration `0002_metric_record.sql`) | P5.09 done, tested (T-MET-11a to 11f, T-STORE-08): a result is born `experimental` and only `apply_record` can make it `conclusive`, never by changing a number: it needs an enabled record of the same metric, metric version and units that supports the view, matches every value it binds **exactly** (the minimum duration, the filter cut-off, the thresholds and arguments, the views a trunk lean was computed for) and signs the thresholds the result uses; otherwise it says why (`no_record`, `record_experimental`, `retired`, `view_not_supported`, `parameters_differ`, `thresholds_not_signed`). An enabled record is complete (a coach's role code, every number, error **below** the smallest useful change, cut-off bound, `pause_tau` and `pause_min_s` as a pair), never changes (a new version instead), one per metric version; the database refuses the rest itself. The store writes a signed record only as its signer (`actor == signed_by`), in one transaction with an audit row that holds the SHA-256 of the coach's sentence, not the sentence. Every metric now echoes `filter_cutoff_hz` (`None` when the filter was skipped). No record is signed here and nothing calls `apply_record` yet (P10.06 signs, P7 applies) |
| compare: constrained DTW (`compare/dtw.py`) | P6.03a done, tested (T-CMP-03, 03b to 03h, T-CMP-05): `dtw(cost, *, band, step)` finds the warping path of minimum cost through any cost matrix (axis 0 the query, axis 1 the reference, `+inf` for a cell that cannot be used) inside a Sakoe-Chiba band `\|i/(n-1) - k/(m-1)\| <= r` with **no default** `r`, with the pattern `symmetricP1` (slope 1/2 to 2, never two horizontal or two vertical unit steps in a row, normaliser `n + m`; the product's pattern) or `symmetric1` (unit steps, to check the code); the result has the path (the middle cells of compound steps listed), `D` = the plain mean of the cost over the path (Appendix C.4), the accumulated and normalised cost, and the settings it was made with; no finite path is a result (`no_path`, every number `None`), never an error. Checked against an independent memoised recursion on 480 random matrices (`dtaidistance` is not installed); 900 x 900 with band 0.2 takes about 0.03 to 0.08 s; 89 mutants, all caught (one equivalent). Open-begin and open-end are not there; nothing calls it yet (P6.03b) |
| compare: normal band (`compare/reference_band.py`) | P6.06 done, tested (T-CMP-08a to 08h): `reference_band(between_references, trainee)` takes one `Comparison` (`reference_id`, `query_id`, `distance` = `D` of an alignment or `None` for no path, `settings`) for every pair of the reference takes and for the trainee against each reference; the band is the smallest, median and largest distance between the references, the trainee's value is the median of its distances to them, and the result says below, within (both ends included) or above with the ratio to the top of the band, and **never a score from 0 to 100 and no label** (AGENTS.md 5.5); one reference or no finite pair is `insufficient_references`, no finite trainee distance is `no_trainee_distance`; an incomplete or repeated set of pairs, a trainee not compared once with every reference, different or empty `settings`, an ID that is not a short code and a distance that is not `None` or a finite number of at least 0 are refused (`CompareError`, never echoing a path or a name). It runs no alignment and never reads `normalised`; 137 tests, 183 mutants, all caught; nothing calls it yet (P6.03b builds the `Comparison`, P8 reads the result) |
| compare: frame features (`compare/features.py`) | P6.01 done, tested (T-CMP-01a to 01i, golden on SYN-10, SYN-03, SYN-04): `frame_features(layer, roll_deg, joints, segments, min_scale_s, min_segment_length)` gives, for the rows of a segment, the positions of 12 joints in trunk lengths from the middle of the hips (one `Λ` per segment, the median trunk, never per frame; the camera roll taken out first) and the `(sin φ, cos φ)` of 9 segments (0 is up, positive to the image right, so the trunk unit is the `θ` of trunk lean; no angle is wrapped, 359 degrees lies next to 1), with `valid`, `reason` (1 to 6 and 19 as `MissingReason`, 23 `zero_length`, 24 `short_segment`) and `bridged` per frame and unit; an invalid unit is NaN in both components, never 0; `t_sec` is the real clock of the grid; the optional `min_segment_length` (trunk lengths, no default, echoed with `min_scale_s`) cuts the angles of segments shorter than it, because the direction of a segment as short as the noise is arbitrary (SYN-10 at 1 px: the diagonal of a same-shape pair goes from 0.020 to 0.022 to 0.012 to 0.014 at a test value of 0.05); the result carries `Λ`, its rows and seconds, the roll, the provenance and `FEATURE_VERSION`; 109 mutants, all caught |
| compare: guards (`compare/guards.py`) | P6.05 done, tested (T-CMP-07a to 07h): `check_comparable(reference, query, reference_features, query_features, *, min_visible, min_coverage, ontology=None)` returns a `GuardDecision` (`comparable`, every `reason` in a fixed order, the two coverages, the settings echoed). Two segments are compared only with the same action number (not technique), side, variant (a short code such as `taiji24/v0`) and view; a view `unknown` is never comparable; `orientation_change` and `perspective_shift` block, `occlusion` does not; coverage = share of rows with at least `min_visible` valid units (`None` without rows; equal to the minimum is enough). `min_visible` and `min_coverage` have no default. A refusal is a result; a description that is not in the ontology (unknown action, a side the action lacks, unknown view or flag, a variant that is not a short code) is a `CompareError`. 250 tests, mutation check 136 mutants, none survives |
| compare: masked cost (`compare/cost.py`) | P6.02 done, tested (T-CMP-02a to 02h and a golden test on SYN-10; 219 unit and 9 golden tests): `cost_matrix(reference, query, *, min_visible, weights=None, block_rows=64)` gives a `CostMatrix` (`values (n, m)`: rows the query, columns the reference; `n_common`; `units`, `weights`, `min_visible` echoed). A cell is the weighted mean of the unit distances over the units valid in both frames (a position: the norm in trunk lengths; an angle: the chord, 0 to 2) and `+inf` when fewer than `min_visible` units are common, never NaN; `min_visible` has no default; a weight of 0 leaves a unit out of the mean and of the count; built by blocks of query rows (900 x 900 x 21 units in 0.31 s and 29 MB at the peak, not the 260 MB of the 4-dimensional array) and independent of the block size; on SYN-10 the diagonal is below 1e-5 under any scale and shift, and the matrix has a second valley on the anti-diagonal because the action is symmetric in time; 100 mutants of `cost.py`, none survives the final run (the 5 survivors of the first run were four test gaps and one equivalent mutant, closed) |
| compare: alignment of two segments (`compare/align.py`) | P6.03b done, tested (T-CMP-03i to 03l, T-CMP-03 through the whole chain, T-CMP-04 and T-CMP-04b on SYN-10 and SYN-11; 135 unit and 24 golden tests): `align(reference, query, *, min_visible, band, step="symmetricP1", weights=None)` is exactly `dtw(cost_matrix(...))` and returns an `Alignment` (the two feature sets, the cost, the DTW result and `settings`, the read-only fingerprint of what made `D`: feature version, units, weights, `min_visible`, band, step and the two feature minimums, which must be equal in the reference and the query or `align` refuses). `matched_query_times()` gives for every reference row the mean query time in seconds along the path (NaN without a path), `as_comparison(reference_id, query_id)` gives the `Comparison` of the normal band with `D` and never the normalised value. No path is a result, and `align` runs no guard (the caller asks `check_comparable` first). With the test settings (`min_visible` 11 of 21, band 0.2, `symmetricP1`) SYN-10 gives `D` 0.0018 against the plan's 0.02 and SYN-11 a ratio of 9.2 to 49.5 in the four tested cases against 2; a layer against itself gives 0; at 1 px of noise a minimum segment length of 0.05 lowers `D` from 0.021 to 0.024 down to 0.015 (R1 of P6.01); 91 mutants, all caught (one equivalent). Nothing calls it yet (P6.04, P6.07) |
| compare: local tempo and deviation (`compare/tempo_ratio.py`) | P6.04 done, tested (T-CMP-06, 06b to 06h; 149 unit and 20 golden tests): `local_tempo(alignment, *, smooth_s)` gives, on the reference's own real clock, the local tempo ratio (query seconds per reference second) as the least-squares slope of the matched query time over a window of `smooth_s` seconds, NaN with a reason (`window_too_small`, `no_path`) and never 0, with `smooth_s` required and echoed and no judgement of the tempo; `deviation_curve(alignment)` gives for every reference row and unit the mean distance (trunk lengths, or the chord of an angle) over the path cells where the unit is valid in both frames, NaN with a reason otherwise, weight-0 units included, and the row cost whose cell-weighted mean is `D`. SYN-10 (warp 0.8 to 1.25, `smooth_s` 0.5 s): median `\|rho / k - 1\|` 0.0134 against the plan's 0.10, largest 0.0526; 145 mutants, 140 killed, 5 equivalent. Nothing calls it yet (P7, P8) |
| compare: UMONS check (`bench/umons_compare.py`, `tools/umons_compare.py`) | P6.07 done, tested (T-CMP-09a to 09e, T-CMP-09 on the dataset; 193 unit, 48 contract and 4 golden tests): `tools/umons_compare.py classes` aligns seeded references and queries of UMONS-TAICHI segments (a performer never against themself) and reports the median `D` to the own class against the others, the share of classes where the own class is closer and the nearest-reference class; `boundaries` aligns whole recordings of two performers with equal `.lab` label sequences, carries the labelled parts through `matched_query_times()` and reports temporal IoU and the start and end errors in seconds next to a uniform-scaling reference line; settings are arguments and are echoed in every table and CSV, only IDs and numbers are written, out of domain (13 techniques, Kinect). With `min_visible` 11 of 21, `symmetricP1`: the own class is closer in 13 of 13 classes and the nearest reference is of the same class for 95 of 104 queries (91.3 %), 48.7 % of the pairs having no path; 23 of 40 pairs of recordings have no path (a row with fewer than 11 valid units), the 17 others give an IoU median of 0.864 (band 0.1) and 0.888 (band 0.2) over 276 parts; 246 mutants, 240 killed and 6 equivalent. Nothing in the product imports it |
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
