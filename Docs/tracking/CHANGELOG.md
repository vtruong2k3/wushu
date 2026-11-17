# Changelog — code and documentation history

Newest first. One entry per completed task or bug fix (format: `AGENTS.md` §4.2).

---

## 2026-11-17 — P5.01 The types of a metric result: `MetricSeries`, `MetricSummary`, coverage and the reasons of a missing row (DONE)

- Changed: `taiji_ai/src/taiji_ai/schemas/metric.py` (new), `taiji_ai/src/taiji_ai/metrics/series.py` (new), `metrics/__init__.py` (`MetricError`), `tests/unit/test_schemas_metric.py` and `tests/unit/test_metric_series.py` (new), `Docs/tasks/P5.01.md` (new), W7 of `Docs/TECH_WORKFLOW_V1.md`, the P5.01 row and T-SCH-02 of `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`
- Behaviour: a series row is one grid row of `pose_filtered.npz` inside the segment (`t_sec`, float64 `values`, uint8 `reason`). `reason` is the single source of truth: 0 measured (finite value), any other code NaN and why: 1 to 6 the quality reasons with the same numbers, 16 to 18 not eligible, 19 to 22 good pose but not measured. `build_series` derives the valid intervals (maximal runs, `[t_first, t_last + step_s)`), the three coverage counts (`measured <= quality <= eligible <= total`) and the counts by reason, and every `MetricSeries` re-checks them, so a header that disagrees with its rows cannot exist; the ratios of v3 8.3 are methods that give `None` at a zero denominator. `MetricSummary`: `insufficient_evidence` has no number (null, never 0), no event and a reason; `record_status` (`experimental`, `enabled`, `retired`) and `conclusive` (only a sufficient result of an enabled metric); a threshold output names its source (`signed_record` needs `enabled`, `unsigned_config` only `experimental`); events lie inside valid intervals; `MetricSummaryFile` is `metric_summary/1`
- Result (DEC-0054): 506 tests (140 damaged cases refused for their own reason, 300 random series derived twice); 55 of 56 mutants caught, one equivalent; gate 10/10 PASS (264.5 s, 4505 tests)
- Tests: T-SCH-02a to 02g
- Bugs: none (a too strict check of `step_s` for short identity series, one empty mutant and two weak tests were found in the task and fixed)
- Decisions: DEC-0054
- Commit: not committed
- Plan: Docs/tasks/P5.01.md

## 2026-11-17 — X.29 File format of the two quality layers: `pose_masked.npz` and `pose_filtered.npz` (DONE)

- Changed: `taiji_ai/src/taiji_ai/schemas/quality_layers.py` (new), `taiji_ai/src/taiji_ai/quality/layers_io.py` (new), one helper each in `quality/mask.py` (`frame_invalid_mask`), `quality/resample.py` (`values_on_rows`) and `quality/coverage.py` (`segment_grid_rows`), docstrings of `quality/__init__.py` and `quality/quality_io.py`, `tests/unit/test_quality_layers_meta.py`, `tests/contract/test_quality_layers_io.py`, `tests/golden/test_quality_layers_umons.py` (new), `Docs/tasks/X.29.md` (new), W6 of `Docs/TECH_WORKFLOW_V1.md`, row T-QLT-13 of `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`
- Behaviour: two archives in the style of `pose_raw/1`. `pose_masked.npz` (`pose_masked/1`) is the mask layer on the rows of the track with the swap flags read from it; `pose_filtered.npz` (`pose_filtered/1`) is the final layer on the grid with the map back to the rows stored (`back_left`, `back_weight`, `outside`, `source_usable`), so a file means the same after the grid rules change; `PoseFiltered.on_source()` equals `QualityResult.filtered_on_source()` bit for bit. Fixed names and dtypes (float32 positions, float64 times), `schema_version` and `meta_json` (parameters as used, the two clocks, counts, `data_sources`; no path or name), one reader per version, no pickle, atomic write returning the SHA-256. The reader checks a file against itself (contract of the mask or gap layer, frame rule, essential counts, swap flags inside their pairs, segment rows, header counts, the map back against both clocks); the writer runs the same checks first; a float64 layer and a layer without rows are refused. The three helpers leave the existing behaviour unchanged
- Result (DEC-0053; UMONS Kinect, `dataset` tests): 11,790 rows give 12,196 grid rows, 1,536,184 and 1,710,569 bytes, saved in 0.21 s and read and checked in 0.04 s; the 733 ms pause stays `no_frame`; both files read back equal
- Tests: T-QLT-13a to 13h (261 tests: 53 headers, 205 contract, 3 on real data; 50 + 10 masked and 66 + 12 filtered damaged-file cases, each refused for its own reason); 33 of 33 mutants caught; gate 10/10 PASS (267.0 s, 3999 tests)
- Bugs: none (a missed mutant and three checks without a case were defects of the tests, fixed in the task)
- Decisions: DEC-0053. Open item for P7: pass the `data_sources` of the recording to the builders (`pose_raw/1` has none)
- Commit: not committed
- Plan: Docs/tasks/X.29.md

## 2026-11-17 — X.31 The grid on a ms-rounded sensor clock: fitted step and phase, and a snap tolerance (DONE)

- Changed: `taiji_ai/src/taiji_ai/quality/resample.py` (`_fit_lattice`, `_window`, the snap in both directions, `GridMap.before` and `snap_s`, docstring), `quality/coverage.py` (docstring only), `tests/unit/test_quality_resample.py` (T-QLT-07n, 07o, 07p new; assertions that stated the old rule updated; oracle rewritten, 300 cases), `Docs/reports/p4_umons_quality.md` (re-run), `Docs/tasks/X.31.md` (new), notes in `Docs/tasks/P4.04.md` and `P4.08.md`, W6 of `Docs/TECH_WORKFLOW_V1.md`, the P4.04 row of `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`
- Behaviour: for a non-uniform timeline the default grid is the lattice that the row times follow: the step counts the frames of each interval (a dropped frame is one more frame, not a longer step), the phase is fitted, pauses and bursts are outside the fit; a grid time within `uniform_tol_s` (1 ms, no new parameter, no schema change) of a row is a copy of that row; a row before the first grid time or after the last has no value on the way back (`before`, `beyond`); the identity decision, the pause limit and the interpolation are unchanged; an explicit `grid_hz` is anchored at the first row as before
- Result (DEC-0052; UMONS Kinect, 111 files, 725,964 grid rows): step 33.3308 to 33.3335 ms; **copies 90.98 % (3.2 % before), mixed 8.78 % (96.5 %)**; timing error of a snapped cell p95 0.25 mm = 0.054 % of the torso (a round trip costs 0.94 %); 26 first and 11 last rows of 703,115 without a value on the way back; 11 files keep more than 20 % mixed rows (wandering clocks); the plain mean interval proposed first gave 34 to 47 ms and 6.5 % copies, so it was not used
- Tests: T-QLT-07n/07o/07p (20 cases) and the differential oracle (300 cases + a branch-coverage meta-test) pass; 9 of 9 mutants caught; gate 10/10 PASS (263.6 s, 3738 tests)
- Bugs: none (two defects of this task's own code were fixed before closing: a float tie in the reason of a mixed cell, a window edge at 1 ulp)
- Decisions: DEC-0052 (amends DEC-0047 rules 2, 3 and 8)
- Commit: not committed
- Plan: Docs/tasks/X.31.md

## 2026-11-17 — P4.08 The quality chain on the UMONS Kinect recordings: adapter, tool, test and report (DONE)

- Changed: `taiji_ai/src/taiji_ai/bench/umons.py` (new), `taiji_ai/tools/umons_adapter.py` (new), `taiji_ai/tests/unit/test_umons_adapter.py`, `tests/contract/test_umons_tool.py`, `tests/golden/test_umons_quality.py`, `tests/helpers/umons_fixtures.py` (new), `Docs/reports/p4_umons_quality.md` (new), `Docs/TECH_WORKFLOW_V1.md` (W6 note and the numbers of M-QLT-08), `Docs/IMPLEMENTATION_PLAN_V1.md` (P4.08 row, T-QLT-12 sub-IDs, M-QLT-08), `Docs/DATASET_REGISTRY_TAIJI.md` (D12 use), `taiji_ai/README.md`, `Docs/tasks/P4.08.md`, `Docs/tracking/*`. **Not changed:** any stage, schema or reason code; nothing from `datasets/` is in the repository
- Behaviour: `bench/umons.py` (never imported by the product path: CC BY-NC-SA data) reads a UMONS Kinect file strictly (76 finite numbers per row, a timestamp that decreases is an error) and gives the layers the chain reads: seconds from the first row, 17 of the 26 HALPE joints (the foot as the big toe), nine absent (NaN, `non_finite`), the position (y, -z) in mm read as pixels, the score 1.0 for a reported joint and 0.0 (with the file's value) for a joint at (0, 0, 0); **a timestamp used by more than one row is two bodies in one frame: the first row is kept as `tracked = False` and the others are dropped and counted**. `find_umons` checks 111 files and the license; `run_folder` runs `run_quality_arrays` on each file (a failure is an error row); `aggregate`, `render_tables` and `write_per_file_csv` give the numbers. `tools/umons_adapter.py run --umons ... --out ... [--grid-hz H] [--only ID ...] [--report FILE]` (exit 0, 1 if a file failed, 2 if it could not start; no path in a message)
- Result (DEC-0051; M-QLT-08, 111 files, 12 performers, 703,146 rows; default chain and `grid_hz` = 30): **0 errors, 29.7 s (0.42 s per 10,000 rows)**; `quality.json` of the longest sequence 13,929 bytes; **no clock is uniform**: 19,148 dropped-frame steps, 275 pauses (largest 0.733 s, 47,866 `no_frame` cells in 54 files), grid rows 732,766 for 703,115 rows; the 31 repeated timestamps are all in `P04T02C03` (two bodies, the last 62 rows); usable frames 99.74 %; over the 17 joints Kinect has **96.80 % observed, 2.857 % bridged on the grid (1.57 % on the rows), 0.344 % missing** (nine absent joints: 34.5 % of the 26-joint cells); Hampel 194,214 cells (1.62 % of the 17 joints on the rows, wrists and big toes about 4 %, trunk and head at most 0.17 %); swap flag 9 warnings in 7 files; **mixed grid rows 96.51 % at the default grid step and 77.75 % at 33.33 ms** (59.7 % of those mixes within 1 ms of a row): a property of P4.04 on a ms-rounded clock, left as it is (candidate X.31, not registered). Out of domain (13 techniques, not the 24 forms): no product number. Limits: one sensor, a constant score, no label of a swap or a spike
- Tests: T-QLT-12a to 12h and T-QLT-12 (73 tests: the reader, the mapping and the plane, the clock and the repeated timestamps, the scores, an end-to-end synthetic sequence with hand counts, `find_umons`, the run, the aggregation, the tables and the CSV, the tool in a subprocess; 16 on six real files under the `dataset` marker); mutation 61 of 61 killed; gate 10/10 PASS (265.4 s, 3617 passed, 1 skipped)
- Bugs: none found in this task
- Commit: not committed
- Plan: Docs/tasks/P4.08.md

## 2026-11-17 — P4.07 The quality chain, its coverage and `quality.json` (DONE)

- Changed: `taiji_ai/src/taiji_ai/quality/chain.py`, `quality/coverage.py`, `quality/quality_io.py`, `taiji_ai/src/taiji_ai/schemas/quality.py` (all new), `quality/__init__.py` (docstring), `taiji_ai/tests/unit/test_quality_coverage.py`, `tests/unit/test_quality_report.py`, `tests/contract/test_quality_chain.py`, `tests/helpers/quality_fixtures.py` (new), `Docs/TECH_WORKFLOW_V1.md` (W6 note and the numbers of M-QLT-07), `Docs/IMPLEMENTATION_PLAN_V1.md` (P4.07 row, T-QLT-11 sub-IDs, M-QLT-07), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 use), `taiji_ai/README.md`, `Docs/tasks/P4.07.md`, `Docs/tracking/*`. **Not changed:** the six stages, the reason codes (none added), any existing schema
- Behaviour: `run_quality_arrays(keypoints, scores, t_sec, tracked, in_segment, params, intervals)` and `run_quality(track, params, intervals)` run the stages in the order of DEC-0046 and DEC-0049: mask; the torso of the mask layer; the swap flag and Hampel, both on the **mask layer**; the gap layer with the swap mask as `blocked`; the uniform grid; the Butterworth filter. Every layer is kept (read-only), nothing passed in is changed, a stage error is re-raised with the stage's name. The Hampel floor is **1 % of the torso** (the fixed floor and the warning `torso_unmeasured` when the torso cannot be measured). The final layer lives on the grid; `QualityResult.filtered_on_source()` gives it on the rows of the video. The report (`QualityReport`, schema `quality/1`) is **counts with their denominators**, no fractions, for the segment (first to last row with `in_segment`, margins left out) and named half-open intervals: cells (observed, bridged, missing; disjoint), reasons twice (all unobserved cells and the NaN cells), usable and not tracked frames, filtered and unfiltered cells, swap `suspect` and `blocked`, mixed rows, gaps by outcome (counted by the cells inside the interval) and the 26 joints, plus the clock, the parameters as used and the warnings (`lr_swap_suspect@12.40-12.73`, `torso_unmeasured`, `grid_resampled`, `filter_skipped_above_nyquist`). `save_quality` / `load_quality`: `quality.json` written atomically and deterministically (returns the SHA-256), read strictly, validators check the partition and every sum; no keypoint value, name or path
- Result (DEC-0050; M-QLT-07, four D20 videos, N = 1, 22 chunks, 158,326 rows, 4,091,516 cells in the segments): the whole chain and the report take **0.33 s per 10,000 rows**; 54.8 % of the rows are frames of the target (45.2 % not tracked: the performer is out of the picture); cells **54.61 % observed, 0.180 % bridged, 45.21 % missing**; 99.91 % of the cells of the rows that are not wholly not-tracked are usable; usable share by video 62.2, 61.7, 43.9, 54.8 %; the Hampel floor of 1 % of the torso (1.41 to 3.07 px) against a fixed 2 px: outlier cells 0.188 % against 0.271 %; `quality.json` of the longest chunk 14,082 bytes (49,752 with three named intervals), round trip equal. SYN-06, SYN-07 and SYN-08 give the expected counts and warnings. Limits: one performer, 24 to 30 fps lesson footage, no real variable-frame-rate clip, a frame of bridged values counts as a usable frame
- Tests: T-QLT-11a to 11m (172 tests: F1 counted by hand, the partition, intervals, frames, reasons, gaps, lattices, a differential test of 200 random chains against a slow cell-by-cell count, the chain against the stages called by hand, SYN-05 to SYN-08, the tracker scene, parameters and floor, the file); mutation 122 of 125 killed (3 equivalent); gate 10/10 PASS (244.0 s, 3544 passed, 1 skipped)
- Bugs: none found in this task (two gate failures of the first run, a docstring line and a mypy `cast`, were fixed before any use)
- Commit: not committed
- Plan: Docs/tasks/P4.07.md

## 2026-11-17 — P4.06 The left/right swap flag: a pair whose two labels jump onto each other's place is marked, nothing is corrected (DONE)

- Changed: `taiji_ai/src/taiji_ai/quality/lr_swap.py` (new), `taiji_ai/src/taiji_ai/quality/__init__.py` (docstring), `taiji_ai/tests/unit/test_quality_lr_swap.py` and `taiji_ai/tests/contract/test_quality_lr_swap_chain.py` (new), `Docs/TECH_WORKFLOW_V1.md` (W6 table row and note with the numbers of M-QLT-06), `Docs/IMPLEMENTATION_PLAN_V1.md` (P4.06 row, T-QLT-10 sub-IDs, M-QLT-06), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 use), `taiji_ai/README.md`, `Docs/tasks/P4.06.md`, `Docs/tracking/*`. **Not changed:** the mask, Hampel, the gap layer, the uniform grid, the filter, `audit/signals.swap_margin`, the reason codes (none added)
- Behaviour: `detect_lr_swaps(keypoints, reason, t_sec, params, torso_px=None)` and `detect_lr_swaps_track(masked)` read the **mask layer** (before Hampel) and return a `SwapResult`: `events (T, 11)`, `suspect (T, 26)`, `blocked` and `frame_suspect` (properties), an event table (pair, row, time, jump in torso lengths, `enter`/`exit`/`unpaired`), the scale and the parameters; **no value, reason or label is changed and the result holds no value of the input**. An event is a **crossed jump** of one pair of `LR_PAIRS` between two observed rows at most 0.25 s apart: both labels moved at least 0.2 torso and each landed within 0.5 of its own move of the other label's previous place (a limb that moves fast alone, two limbs that cross smoothly, a label that jumps alone are not events; a swap of joints closer than 0.2 torso is neither seen nor flagged). Events of one pair are paired greedily in time order within 0.5 s: the rows from the enter (inclusive) to the exit (exclusive) are `suspect` for the pair's two joints; an unpaired event marks only its own row. `blocked` is `suspect` plus the jump rows and is the input of `interpolate_gaps(blocked=...)`
- Result (DEC-0049; M-QLT-06, four D20 videos, N = 1, 22 chunks, 158,326 rows): **270 events (17.1 per 10,000 rows), all in `d20-v4`**, 205 in the leg chain; 68 enter, 68 exit, 134 unpaired; 0.086 % of the rows `suspect`, 0.124 % `blocked`. Of the 11 labelled swap frames (8 ordinary) an event of the labelled pair is within +-2 rows of 9 (6 ordinary) and the labelled cell is in `blocked` in 7; 2 of 172 confirmed-right frames are flagged; **a biased sample, not a recall** (the frames were chosen by a preview of this rule); the two frames without an event have no jump of the pair in their chunk. SYN-08: the suspect rows are exactly the swap mask at 0, 1 and 2 px of noise, every pair flagged but the eyes (0.12 torso apart); swaps up to 0.5 s are exact, longer ones are seen at their two jumps only. `blocked` would refuse 278 of the 9,272 gaps that the gap layer bridged on D20 (3.0 %). Limits: the sensitivity is unknown; the state of a swap is not observed, only its jumps; a whole-body swap cannot be told from a person who turns his back; all events are in one video; 24 to 30 fps lesson footage only
- Tests: T-QLT-10a to 10i and the differential test (280 unit tests: SYN-08 exact, no event on SYN-05 to SYN-07, smooth crossings, the boundaries, the pairing, scale and clock, the result, bad input, 200 random layers against a slow rule; 5 contract tests: SYN-08 through mask, the flag, Hampel and the gap layer with `blocked`, the tracker chain); mutation 54 of 54 killed (2 dead-code mutants removed with the code); gate 10/10 PASS (236.1 s, 3372 passed, 1 skipped)
- Bugs: none found in this task
- Commit: aec82b9
- Plan: Docs/tasks/P4.06.md

## 2026-11-17 — P4.05 Butterworth low-pass, zero phase, on each continuous run of a joint (DONE)

- Changed: `taiji_ai/src/taiji_ai/quality/filters.py` (the Butterworth stage added to the Hampel module), `taiji_ai/src/taiji_ai/quality/__init__.py` (docstring), `taiji_ai/tests/unit/test_quality_butterworth.py` and `taiji_ai/tests/contract/test_quality_butterworth_chain.py` (new), `Docs/TECH_WORKFLOW_V1.md` (W6 table row and note with the numbers of M-QLT-05), `Docs/IMPLEMENTATION_PLAN_V1.md` (P4.05 row, T-QLT-08 and T-QLT-09 sub-IDs, M-QLT-05), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 use), `taiji_ai/README.md`, `Docs/tasks/P4.05.md`, `Docs/tracking/*`. **Not changed:** the mask, the gap layer, the uniform grid, Hampel, the reason codes (none added)
- Behaviour: `lowpass_layer(keypoints, reason, interpolated, step_s, params)` and `lowpass_grid(layer)` read the grid layer (never change it) and return a new read-only `FilterResult` (`keypoints`, `filtered`, `reason`, `interpolated`, the run table, `params`, `sampling_hz`). A run is a maximal sequence of rows in which a joint has a value (observed or bridged), x and y together; **each run is filtered on its own** with `scipy.signal.sosfiltfilt` (order 4, design frequency 6 Hz, zero phase; forward and backward the gain at 6 Hz is 0.5 and the -3 dB point is 5.4 to 5.6 Hz), so no NaN is an input of the filter and nothing is filtered across a hole, a loss of the target or a pause. A run of at most `padlen` rows (15 at order 4) is **not filtered**: it keeps its input values, `filtered` is False, the run table says `too_short`. If the cutoff is not below Nyquist (a clip of 12 fps or less at 6 Hz) nothing is filtered and every run says `above_nyquist`. `reason` and `interpolated` are copied: a bridged cell that is filtered is still a bridged value
- Result (DEC-0048; M-QLT-05, four D20 videos, N = 1, 22 chunks): 965 runs, 2,249,882 usable cells, of which 231 (0.010 %) are in runs that are too short. At 6 Hz a filtered cell moves p50 0.83 px, p95 3.76 px (1.53 % of the torso), p99 7.54 px; the jitter falls to 0.316 and the p99 speed to 0.769 of their value (4 Hz: 0.167 and 0.717; 8 Hz: 0.507 and 0.836). SYN-05 with truth: the noise-free movement is distorted by at most 0.046 px, 1 px and 2 px of noise fall to 0.605 of their rms error, and in the pauses (truth 0 px/s) the speed caused by 1 px of noise falls from p50 48.8 / p99 126.8 to 13.4 / 34.9 px/s; the edge cost is one cell per end of a run; a spike that Hampel removes leaves no trace, a lasting jump that Hampel does not flag (60 px for 6 rows) is smeared (error up to 66.8 px). Limits: the values are W6's and not yet judged against a metric (P5.08); no real VFR clip; 24 to 30 fps lesson footage only
- Tests: T-QLT-08a to 08h, T-QLT-09a to 09f and the differential test (288 unit tests: each run against scipy bit for bit, the response, invariants, flags, results, the grid wrapper, short runs, `padlen`, Nyquist, the step, the run table, bad input, 200 random layers against a loop that calls scipy per run; 5 contract tests: SYN-05 and SYN-07 with truth through mask, Hampel, gaps, grid and filter, the tracker chain); mutation 43 of 43 killed; gate 10/10 PASS (246.6 s, 3087 passed, 1 skipped)
- Bugs: none found in this task
- Commit: aec82b9
- Plan: Docs/tasks/P4.05.md

## 2026-11-17 — P4.04 Uniform grid for variable-frame-rate video: resample to a regular clock, keep the map back (DONE)

- Changed: `taiji_ai/src/taiji_ai/quality/resample.py` (new), `taiji_ai/src/taiji_ai/quality/_checks.py` (`check_layer` split into shared pieces, `check_times`, `check_gap_layer`), `quality/mask.py` (reason code `NO_FRAME = 6`, name `no_frame`), `quality/__init__.py` (docstring), `taiji_ai/tests/unit/test_quality_resample.py` and `taiji_ai/tests/contract/test_quality_resample_chain.py` (new), `taiji_ai/tests/unit/test_quality_mask.py` (names, the codes the mask never emits), `taiji_ai/tests/helpers/synth.py` (`truth_at`), `Docs/TECH_WORKFLOW_V1.md` (W6 note with the numbers of M-QLT-04), `Docs/IMPLEMENTATION_PLAN_V1.md` (P4.04 row, T-QLT-07 sub-IDs, M-QLT-04), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 use), `taiji_ai/README.md`, `Docs/tasks/P4.04.md`, `Docs/tracking/*` (and the commit hashes of nine earlier entries). **Not changed:** the tracker, the pose stage, the behaviour of the gap layer, Hampel and the mask
- Behaviour: `resample_layer(keypoints, reason, interpolated, t_sec, params)` and `resample_gaps(result, t_sec)` read the gap layer (never change it) and return a new read-only `GridLayer`; `GridMap` keeps the map between the grid and the source rows (`to_source` is the way back, `GridLayer.to_source` also gives no value to a source cell that was not usable). **The timeline decides**: if every row time is within 1 ms of the least-squares straight line the stage is the identity (the grid is the rows, nothing is touched, `resampled` false; every constant frame rate video, including 29.97 fps on a time base of 1 ms); otherwise a regular grid from the first real row time with the median interval (or `grid_hz`), never beyond the last row. A grid time that is a row is a bit-for-bit copy; between two usable cells a cell is the flagged linear mix `a + w (b - a)` (`interpolated` inherited, the reason keeps the cause, the row flag `mixed`); a cell next to an unusable cell is NaN, never filled, with that cell's reason; a pause in the timestamps of more than 0.150 s is not bridged: NaN with the new reason `no_frame`
- Result (DEC-0047; M-QLT-04, four D20 videos, N = 1, 22 chunks): the plan is the **identity in 22 of 22 chunks** (24 fps in 13, 30 fps in 9; largest deviation 3e-9 s), so on the footage we have the stage changes nothing. Round trip on real motion at every phase (grid rate 1 % above and below the source rate, 4,458,884 observed cells, torso 191 px): p50 0.43 px, p95 2.21 px (0.94 % of the torso), p99 4.30 px; by phase p95 from 0.66 px to 2.93 px (1.23 % of the torso) at the worst phase; 0.070 % of the usable source cells lost at the edges of holes. SYN-07 with 30 % jitter: largest error 0.21 to 0.35 px against an analytic bound of 2.35 to 2.41 px. Limits: no real VFR clip exists yet; 24 to 30 fps lesson footage only; the largest error (175 px) was not examined
- Tests: T-QLT-07a to 07m, the differential test and the changed T-QLT-01 (292 unit tests: the identity, the regular grid, linear motion, SYN-07 with truth, holes, pauses, the reason and flag table, the way back, invariants, bad input, 200 random layers against a slow rule; 12 contract tests: SYN-07 through mask, Hampel, gaps and the grid, the tracker chain, the real PTS of four F-VID files); mutation 72 of 76 killed (4 equivalent); gate 10/10 PASS (229.7 s, 2794 passed, 1 skipped)
- Bugs: none found in this task
- Commit: aec82b9
- Plan: Docs/tasks/P4.04.md

## 2026-11-17 — P4.03 Hampel filter: isolated spikes of a joint are flagged `outlier` and set to NaN (DONE)

- Changed: `taiji_ai/src/taiji_ai/quality/filters.py` (new), `taiji_ai/src/taiji_ai/quality/_checks.py` (new: the number checks and the layer contract that `gaps.py` and `filters.py` share), `quality/gaps.py` (uses `_checks`), `quality/mask.py` (reason code `OUTLIER = 5`, name `outlier`), `quality/__init__.py` (docstring), `taiji_ai/tests/unit/test_quality_hampel.py` and `taiji_ai/tests/contract/test_quality_hampel_chain.py` (new), `taiji_ai/tests/unit/test_quality_mask.py` (names, a test that the mask never emits the code), `Docs/TECH_WORKFLOW_V1.md` (W6 note with the numbers of M-QLT-03), `Docs/IMPLEMENTATION_PLAN_V1.md` (P4.03 row, T-QLT-06 sub-IDs, M-QLT-03), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 use), `taiji_ai/README.md`, `Docs/tasks/P4.03.md`, `Docs/tracking/*`. **Not changed:** the tracker, the pose stage, the behaviour of the gap layer
- Behaviour: `hampel_outliers(keypoints, reason, t_sec, params)` and `hampel_track(masked)` read the mask layer (never change it) and return a new read-only layer. The window of a cell is 7 rows centred on it; a row counts only if its cell is observed and within 0.25 s of the centre (real time, no frame rate assumed); a cell is judged only if it is observed and at least 5 cells count. `sigma = max(1.4826 x MAD, scale_floor_px)`; a cell further than 3 sigma from the median in x or in y (strictly) is an outlier: NaN, reason `outlier`, and nothing else changes (no smoothing, clipping or invention). One pass on the original values. Persistent errors and left/right swaps are not outliers. Stage order: mask, Hampel, gaps (a short hole of an outlier is bridged and flagged `interpolated`, keeping the reason `outlier`), resampling, filter. `torso_length_px(keypoints, reason)` gives the median torso length (NaN if no frame has the four joints) so that P4.07 can pass a floor in torso units
- Result (DEC-0046; M-QLT-03, four D20 videos, N = 1, `tau_kp` 0.3, 22 chunks; 170 frames confirmed right, 118 cells named as wrong in 34 ordinary pose failures of P3.08): the rule as written (no floor) flags 7.06 % of the judged cells and 6.87 % of those of the right frames, because the MAD of seven numbers is noisy (pure noise: 4.8 %) and a still joint has a MAD near 0; with the default floor of 2 px (about 1 % of the torso) 0.49 % and 1.14 %, and 34.8 % of the named wrong cells are found against 39.8 %; 313 more cells stay NaN after the gap layer against 5,780. The maintainer chose the floor with this table. Hampel finds `lr_swap` 26 of 58 cells, `joint_off` 13 of 37, `foot_error` 1 of 13, `flicker` 1 of 10: a cheap safety net, not a detector of what P3.08 found. Limits: 118 cells in frames chosen as suspect; 24 to 30 fps lesson footage only
- Tests: T-QLT-06a to 06n and the changed T-QLT-01 (319 unit tests: spikes, smooth movements at both settings, the boundary and the 1.4826, MAD 0 and the floor, NaN and the count, the time cut, the result, invariants, blocks, a differential test against a slow rule on 200 layers, bad input, the torso; 8 contract tests: SYN-05 with spikes through mask, Hampel and the gap layer, the chain with the tracker); mutation 57 of 57 killed; gate 10/10 PASS (227.0 s, 2490 passed, 1 skipped)
- Bugs: none found in this task
- Commit: bad1c45
- Plan: Docs/tasks/P4.03.md

## 2026-11-17 — P4.02 Short-gap interpolation: bridge holes of up to 150 ms in real time, flag them (DONE)

- Changed: `taiji_ai/src/taiji_ai/quality/gaps.py` (new), `taiji_ai/src/taiji_ai/quality/__init__.py` (docstring), `taiji_ai/tests/unit/test_quality_gaps.py` and `taiji_ai/tests/contract/test_quality_gaps_track.py` (new), `Docs/TECH_WORKFLOW_V1.md` (W6 note with the numbers of M-QLT-02), `Docs/IMPLEMENTATION_PLAN_V1.md` (P4.02 row, T-QLT-03..05 sub-IDs, M-QLT-02), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 use), `taiji_ai/README.md`, `Docs/tasks/P4.02.md`, `Docs/tracking/*`. **Not changed:** `quality/mask.py`, the tracker, the pose stage
- Behaviour: `interpolate_gaps(keypoints, reason, t_sec, params, blocked)` and `interpolate_track(masked)` read the mask layer (never change it) and return a new read-only layer. A gap is a maximal run of unobserved frames of one joint; it is bridged linearly in real time, x and y apart, and every cell flagged `interpolated`, if the span between its two observed anchors is at most 0.150 s (+1e-9 s; at 30 fps up to 3 missing frames, at 24 and 25 fps up to 2, at 60 fps up to 8). Not bridged, in this order: no anchor on one or both sides (`open_*`: nothing is extrapolated), a cell with a reason in `never_fill` (default `not_tracked`: the target was lost, also for 100 ms), a cell or anchor in the optional `blocked` mask (the place for P4.06's suspected swaps and turning points), a span over the limit. Nothing is held, repeated or set to zero; the mask's `reason` is kept for bridged cells; an interpolated cell has no score; a table gives every gap its length (missing span and bridged span) and outcome; feeding a result back is refused
- Result (DEC-0045; M-QLT-02, four D20 videos, N = 1, `tau_kp` 0.3, 86,303 tracked frames): the mask leaves 0.080 % of the cells unobserved; 219 gaps in tracked stretches are bridged (304 cells), 82 are too long, 0.066 % of the cells stay NaN, every loss of the target is refused. Leave-gap-out: the p95 error of a bridge against the observed value is 2.6 / 2.9 / 3.1 % of the torso for 1 / 2 / 3 missing frames and 4.4 % for 8, against 4.4 to 15.6 % when the last value is held; arms are the hardest (4.2 to 4.8 % for up to 3 frames). The 150 ms of W6 is kept. Limits: the hidden cells sit where the model tracks well; 24 to 30 fps lesson footage only
- Tests: T-QLT-03, 04, 05 (273 tests in 2 files: constructed arrays, a differential test against a slow cell-by-cell rule on 200 layers, SYN-06 in both gap modes, the chain with the tracker); mutation 38 of 38 killed; gate 10/10 PASS (350.8 s, 2162 passed, 1 skipped)
- Decisions: DEC-0045 (the length of a gap is the bridged span, the order of the rules, what is never bridged, `blocked` instead of a detector, the 150 ms evaluated and kept)
- Bugs: BUG-0074 (S3: the D20 registry row did not name the use of P4.01; found and fixed here)
- Commit: bad1c45
- Plan: Docs/tasks/P4.02.md

## 2026-11-17 — P3.09 Quick comparison of the detector: YOLOX (shipping) against YOLO11, measure only (DONE)

- Changed: `taiji_ai/src/taiji_ai/bench/{yolo_onnx,detector_metrics,detector_compare,detector_worker}.py` (new), `taiji_ai/tools/detector_compare.py` and `detector_review_page.html` (new), `taiji_ai/tests/unit/test_{yolo_onnx,detector_metrics,detector_rule,detector_compare}.py`, `tests/contract/test_detector_{guard,tool,report}.py`, `tests/golden/test_detector_shipping.py` (new), `Docs/reports/p3_pose_benchmark.md` (Appendix A), `Docs/IMPLEMENTATION_PLAN_V1.md` (P3.09 row, T-DET-01..10, M-DET-01), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 use), `taiji_ai/THIRD_PARTY_NOTICES.md`, `taiji_ai/README.md`, `Docs/tasks/P3.09.md`, `Docs/tracking/*`. **Not changed:** `pose/rtm.py`, `models/registry.json`, `pyproject.toml`, `uv.lock`
- Behaviour: offline tool, never imported by the product (a guard test fails if it is, or if anything imports Ultralytics): `run` measures both detectors in one process each on the GPU (speed and VRAM; recall on the 169 labelled frames of P3.08 with McNemar; agreement, stability and dropouts in seconds on the five clips of P3.07; the runs in which only one detector has the performer, drawn for a review), `sheets` builds the review page (the direction is hidden), `report` applies the rule written before the numbers (DEC-0043) and writes the tables. The YOLO11 adapter reads the raw `[1, 84, 8400]` tensor with our own code; the shipping YOLOX runs through ONNX Runtime with the scores kept and is tested to give the boxes of rtmlib
- Result (DEC-0044): **YOLO11m is not materially better; DEC-0005 stands, the detector is not changed.** Recall 100.0 % against 98.2 % (3 frames, exact McNemar p 0.25); no run with only one detector in 3,785 clip frames; the shipping boxes are looser (median IoU with the confirmed skeleton's hull 0.76 against 0.87) and less steady (p95 of 1 − IoU 0.131 against 0.063); YOLO11m is 1.65 times faster end to end (22.4 against 36.8 ms) with 136 MiB more GPU memory; the detector is 73 % of the pipeline time at N = 1 and 44 % at N = 5, so a YOLO11-speed detector would save about 29 % and 17 % (estimate). Not measured: the effect of a tighter box on the keypoints
- Licence and safety (DEC-0043): Ultralytics and the weights are AGPL-3.0, used once in an isolated environment (CUDA PyTorch, `yolo` command line, one load of the `.pt` by approval, telemetry off); hashes and versions recorded; the environment (4.69 GB), `yolo11m.pt` and the ONNX were deleted at the close
- Tests: T-DET-01..10, 116 tests in 8 files (6 on the GPU); mutation 40 of 40 and 9 of 9 killed; gate 10/10 PASS (323.6 s, 1889 passed, 1 skipped = the YOLO11 smoke, file deleted)
- Decisions: DEC-0043 (licence reading, rule, shipping NMS limit corrected to 0.65), DEC-0044 (result)
- Bugs: BUG-0072 (S3, `prepare_onnxruntime` after a CPU call; found here, fix = X.30, worked around in `bench/yolo_onnx.py`), BUG-0073 (S3, stale NMS default 0.45; found in the self-review, fixed and closed here)
- Commit: bad1c45
- Plan: Docs/tasks/P3.09.md

## 2026-11-16 — P3.08 Failure cases of the pose on real footage (DONE)

- Changed: `taiji_ai/src/taiji_ai/audit/` (new: `scan.py`, `signals.py`, `select.py`, `labels.py`, `summary.py`, `render.py`, `analyse.py`), `taiji_ai/tools/pose_audit.py` (new), `taiji_ai/tests/unit/test_audit_{signals,select,labels,summary,render,target}.py`, `taiji_ai/tests/contract/test_audit_{scan,analyse,tool}.py` (new), `Docs/reports/p3_failure_cases.md` (new), `Docs/TECH_WORKFLOW_V1.md` (W6 note), `Docs/IMPLEMENTATION_PLAN_V1.md` (P3.08 row, T-AUDIT-01..08, M-AUDIT-01), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 allowed use), `taiji_ai/README.md`, `Docs/tasks/P3.08.md`, `Docs/tracking/*`
- Behaviour: `tools/pose_audit.py pose` runs the pose over the four D20 videos in chunks of 300 s (resumable) at one cadence; `analyse` chooses 250 frames with 11 rank-based rules and a blind sample (no threshold), draws the contact sheets and writes an empty review file; `report` reads the filled file and writes the tables (counts per type, view, situation, joint group, precision per rule, blind rate with a Wilson interval, the share the score does not warn about, the highest score of the wrong joints, the cadence labels, every failure case). Two markers in the notes keep tracker events (`[track]`) and edit frames (`[edit]`) apart without dropping any frame; a person's `ok` clears the agent's failure fields. Images and keypoint files stay in the ignored `data/` folder
- Result (labels by agents, re-checked by the lead and confirmed by the maintainer: 249 of 250 agreed): blind sample 2 of 40 failures (5.0 %, 95 % interval 1.4 % to 16.5 %); 61 counted failures of which 34 are pose failures of ordinary frames (23 in one video: side lunges, left/right swaps of the legs); none of the 34 would be removed by a mask at `tau_kp` 0.3 (highest wrong score: median 0.67); the four situations of the plan were not where the failures are; 15 frames are the tracker losing a performer who has a good skeleton; no evidence that N = 1 removes failures
- Tests: T-AUDIT-01..06 and 04c (131 test cases in the nine audit files); mutation 62 of 62 killed; gate 10/10 PASS (316.4 s, 1774 tests)
- Decisions: DEC-0039 (rules of the review), DEC-0041 (the markers, the person's `ok`)
- Bugs: none
- Commit: 8fc1cfb
- Plan: Docs/tasks/P3.08.md

## 2026-11-16 — P4.01 The mask layer: low-confidence keypoints and invalid frames (DONE)

- Changed: `taiji_ai/src/taiji_ai/quality/__init__.py` (`QualityError`), `taiji_ai/src/taiji_ai/quality/mask.py` (new), `taiji_ai/tests/unit/test_quality_mask.py` (new), `taiji_ai/tests/contract/test_quality_mask_track.py` (new), `Docs/TECH_WORKFLOW_V1.md` (W6 note with the numbers of M-QLT-01), `Docs/IMPLEMENTATION_PLAN_V1.md` (P4.01 row, T-QLT-01 and T-QLT-02 sub-IDs, M-QLT-01), `taiji_ai/README.md`, `Docs/tasks/P4.01.md`, `Docs/tracking/*`
- Behaviour: `apply_mask` gives a new layer in which every cell is the input value or NaN and every NaN has a reason: `low_conf` (score under `tau_kp` = 0.3; equal is kept, compared in the precision of the scores), `non_finite`, `not_tracked` (lost, target lost, before target), `frame_invalid` (a tracked frame with fewer than half of the ten essential joints usable: 5 of 10 is valid, 4 is not; all 26 joints NaN, joints already excluded keep their own reason); `mask_track` does the same on a `TargetTrack` and keeps the timeline and the 1 s margins. Nothing is filled or clipped; inputs are not changed; no file format yet (X.29)
- Measured (M-QLT-01, four D20 videos, `tau_kp` = 0.3): the mask excludes 0.00 % to 0.18 % of the joint cells of tracked frames and no frame is invalid; 54.8 % of the frames are tracked (the rest is the tracker at cuts). The P3.08 report adds that none of the 34 pose failures of ordinary frames would have been removed: the score does not warn; the maintainer kept 0.3 as a hygiene threshold (DEC-0042)
- Tests: T-QLT-01a..e and T-QLT-02a..b (106 tests, red first); mutation 33 of 34 killed (1 equivalent); gate 10/10 PASS (212.0 s, 1772 tests)
- Decisions: DEC-0040 (reasons and their order, the 5-of-10 boundary, the precision of the comparison, parameters kept as W6 values, file format deferred to X.29)
- Bugs: none
- Commit: 8fc1cfb
- Plan: Docs/tasks/P4.01.md

## 2026-11-16 — P3.07 Pose benchmark: speed, GPU memory and the detector cadence N (DONE)

- Changed: `taiji_ai/src/taiji_ai/bench/` (new: `timing.py`, `gpu.py`, `compare.py`, `decision.py`, `clips.py`, `worker.py`, `orchestrate.py`, `report.py`), `taiji_ai/tools/bench_pose.py` (new), `taiji_ai/src/taiji_ai/pose/runner.py` (`run_pose(on_frame=...)`, optional),
  `tests/unit/test_bench_{timing,decision,compare,gpu,clips,orchestrate}.py`, `tests/contract/{test_bench_tool,test_pose_runner}.py`, `tests/golden/test_bench_worker.py`, `Docs/reports/p3_pose_benchmark.md` (new), `Docs/TECH_WORKFLOW_V1.md` (W4 numbers),
  `Docs/IMPLEMENTATION_PLAN_V1.md` (estimate, B-PERF-01, T-BENCH-01..09), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 allowed use), `taiji_ai/README.md`, `taiji_ai/THIRD_PARTY_NOTICES.md` (NVML), `Docs/tasks/P3.07.md`, `Docs/tracking/*`
- Behaviour: `tools/bench_pose.py` finds the D20 videos by size and SHA-256, runs one worker process per N, and writes `bench.json` and the tables of the report. On the RTX 3060 with five 30 s clips: RTF 1.23 / 0.335 / 0.259 (N = 1 / 5 / 10), 1.47 / 0.40 / 0.31 at 30 fps; peak VRAM 1.8 to 2.0 GB of 12; a 30 s segment 37 to 46 s (N = 1) and 10 to 13 s (N = 5).
  The rule for N, written before the measurement, recommends **N = 1** (N = 5 differs from N = 1 on the target keypoints by a median of 2.0 px, p95 9.7 px); the default in the code stays 5 until the maintainer decides
- Tests: T-BENCH-01..09 (124 tests; GPU: the real NVML and the real models on a short clip); mutation 63 of 63 killed; gate 10/10 PASS (200.8 s, 1537 tests)
- Decisions: DEC-0038 (D20 as the stand-in for P1.09 and the reading of `benchmark`; NVML through ctypes; the rule for N; the optional callback)
- Bugs: BUG-0071 (S3) found by the read-back and fixed in this task
- Commit: 8fc1cfb
- Plan: Docs/tasks/P3.07.md

## 2026-11-16 — P3.06 The target over time: lost, re-attached, `target_lost`; and `track.parquet` (DONE)

- Changed: `taiji_ai/src/taiji_ai/track/state.py` (new), `taiji_ai/src/taiji_ai/track/track_io.py` (new), `taiji_ai/src/taiji_ai/schemas/track.py` (new), `taiji_ai/src/taiji_ai/track/associate.py` (`person_cost` public), `tests/unit/{test_target_state,test_track_meta}.py` (new), `tests/unit/test_associate.py`,
  `tests/contract/test_track_io.py` (new), `tests/helpers/track_build.py` (new), `tests/golden/test_pose_d20.py` (T-TRK-05g), `Docs/TECH_WORKFLOW_V1.md` (W5 steps 3 and 4, module layout), `Docs/IMPLEMENTATION_PLAN_V1.md` (estimate, T-TRK-04..06), `taiji_ai/README.md`, `Docs/tasks/P3.06.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG,DECISIONS}.md`
- Behaviour: `resolve_target(raw, tracks, selection)` gives every frame of the pose file one status: `tracked`, `lost` (missing up to 0.5 s of real time), `target_lost`, `before_target`; keypoints are NaN unless tracked. A track that starts after the loss while the target is missing is compared with the last pose of the target by the cost of P3.05:
  one candidate at or under 0.5 is taken, two close ones are `ambiguous`, a worse one or a return after 5 s is `refused`; a person who was in the picture all along is never taken. Nobody taken means NaN and `needs_reselect` with a reason. `save_track` / `load_track`: `track.parquet` (`track/1`), strict and atomic, SHA-256 returned
- Tests: T-TRK-04a..d, 05a..h, 06a..d (93 + 66 + 48 + 6 `person_cost`), T-TRK-05g on two real clips (GPU); mutation 82 of 83 killed (1 equivalent); gate 10/10 PASS (187.8 s, 1413 tests)
- Decisions: DEC-0037 (the rules and the two provisional limits with their evidence)
- Bugs: none
- Commit: 8fc1cfb
- Plan: Docs/tasks/P3.06.md

## 2026-11-16 — P3.05 Hungarian association of persons: track ids and match margin (DONE)

- Changed: `taiji_ai/src/taiji_ai/track/associate.py` (new), `taiji_ai/src/taiji_ai/track/geometry.py` (new, shared), `taiji_ai/src/taiji_ai/track/target.py` (uses the shared geometry), `tests/unit/{test_associate,test_track_geometry}.py` (new), `tests/helpers/pose_raw_build.py`,
  `tests/golden/test_pose_d20.py` (T-TRK-02g), `Docs/TECH_WORKFLOW_V1.md` (W5 step 2, module layout), `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`, `Docs/tasks/P3.05.md`, `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`
- Behaviour: `associate_tracks(raw)` gives every eligible person a track id by Hungarian assignment frame to frame: cost = mean of `1 - IoU` of the keypoint hulls and the keypoint distance over the hull height (capped at 1), a pair above 0.3 is never matched, a track not matched lives 0.1 s (real `t_sec`),
  weak persons have no track. `match_cost`, `match_margin` (about 0 where two people coincide), `gap_frames` and `gap_s` come with it. Measured first: a motion prediction did not help and was left out
- Tests: T-TRK-02a..d, 03a..m (39) and geometry (7); SYN-12: 0 swaps (10 seeds and 6 variations); real clips (GPU): the presenter keeps one track over 289 frames; mutation 25 of 25; gate 10/10 PASS (178.3 s, 1198 tests)
- Decisions: the values of step 2 are in the task file (no DEC: provisional parameters of one module)
- Bugs: BUG-0070 (S3) found by the read-back and fixed in this task
- Commit: 8fc1cfb
- Plan: Docs/tasks/P3.05.md

## 2026-11-16 — P3.04 Choose the target person on the first frame (DONE)

- Changed: `taiji_ai/src/taiji_ai/track/target.py` (new), `taiji_ai/src/taiji_ai/pose/runner.py` (`valid_keypoint_mask` public and shape-generic), `tests/unit/test_target_select.py` (new), `tests/helpers/pose_raw_build.py`, `tests/golden/test_pose_d20.py` (T-TRK-01g),
  `Docs/TECH_WORKFLOW_V1.md` (W5 step 1 rule), `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`, `Docs/tasks/P3.04.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`
- Behaviour: `select_target(raw, bbox=None, at_t_sec=None)` names the performer on the first frame of the segment: by default the eligible person with the best `area share x centrality`; a close call (second / best >= 0.6) is flagged `ambiguous`; weak persons are never chosen
  by default; nobody at the start: it searches forward up to 2 s (never before the start) or raises; a user box picks the person with the largest IoU (>= 0.3, weak allowed and flagged) and refuses a box that matches nobody or covers two people. It returns the frame, the person row,
  the box, the score, `ambiguous`, `weak` and `offset_from_start_s`
- Tests: T-TRK-01a..m (40 unit tests; mutation 22 of 22) and T-TRK-01g on a real frame with two people (GPU); gate 10/10 PASS (163.3 s, 1150 tests)
- Decisions: none new (the maintainer's answers to Q1 to Q7 are in the task file)
- Bugs: none
- Commit: 8fc1cfb
- Plan: Docs/tasks/P3.04.md

## 2026-11-16 — P3.03 pose_raw.npz: strict, atomic save and load (schema pose_raw/1) (DONE)

- Changed: `taiji_ai/src/taiji_ai/pose/raw_io.py` (new), `taiji_ai/src/taiji_ai/schemas/pose.py` (new), `taiji_ai/src/taiji_ai/store/artifacts.py` (`atomic_write_bytes` cleans its `.tmp`: BUG-0069),
  `taiji_ai/src/taiji_ai/pose/runner.py` (`PoseRunStats.elapsed_s` optional, `PoseRaw.equals` NaN-safe), `tests/helpers/pose_raw_build.py`, `tests/unit/{test_pose_raw_meta,test_artifacts_atomic}.py`,
  `tests/contract/test_pose_raw_io.py` (new), `tests/golden/test_pose_d20.py` (T-POSE-08j), `Docs/TECH_WORKFLOW_V1.md` (format of `pose_raw.npz`), `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`,
  `Docs/tasks/P3.03.md`, `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`
- Behaviour: `save_pose_raw(path, raw)` writes nine arrays (the seven of `PoseRaw`, `schema_version`, `meta_json`) atomically and returns the SHA-256 of the file; `load_pose_raw(path)` gives back an equal `PoseRaw` bit for bit (NaN, keypoints outside the image
  and weak persons included) and refuses anything damaged, inconsistent, of another version or skeleton with a `PoseRawError` that names the field. The file keeps the deterministic counts only (the wall clock belongs to the run manifest, so
  `elapsed_s` is `None` after a load). `atomic_write_bytes` no longer leaves a `.tmp` after a failed write or replace
- Tests: T-POSE-08a..i, T-SCH-03, T-ART-01 (85, red first), T-POSE-08j (GPU); mutation 28 of 28; D20 clip: file 82 KB (ratio 0.81), save 17 ms, load 3 ms; gate 10/10 PASS (170.3 s, 1109 tests)
- Decisions: the maintainer's changes to Q1, Q2, Q4 of the plan (task file section 1)
- Bugs: BUG-0069 (S3) found and closed in this task
- Commit: not committed
- Plan: Docs/tasks/P3.03.md

## 2026-11-16 — P3.02 run_pose: raw pose of everyone in a segment, by real PTS (DONE)

- Changed: `taiji_ai/src/taiji_ai/pose/runner.py` (new), `taiji_ai/tests/helpers/fake_pose.py` (new), `tests/unit/test_pose_box.py` (new), `tests/contract/test_pose_runner.py` (new),
  `tests/golden/test_pose_d20.py` (new), `taiji_ai/README.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (T-POSE-05, 06 rows), `Docs/tasks/P3.02.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`
- Behaviour: `run_pose(recording_dir, start_s, end_s, model)` reads the frames of `[start - 1 s, end + 1 s]` of the original video by the rows of `pts.parquet` (display rotation applied), runs the detector on the first frame and every N frames
  (default 5) and takes the boxes of the frames between from the previous keypoints (+12 %), runs the detector at once when nobody is followed, and returns the raw persons as compressed rows (`PoseRaw`: `frame_index` = row of the table, `t_sec`,
  boxes, keypoints and scores as the model returned them, `from_detector`). Persons with few valid keypoints are kept (the maintainer's decision) and not followed. A file that does not match its table, a bad segment, a size change or a model
  failure is a `PoseRunError`, never a partial result
- Tests: T-POSE-05a..e, 05g, 06a..h (47, CPU, scripted model), T-POSE-05f and T-POSE-07 (GPU, 2 passed); mutation of `runner.py` 22 of 23 (1 equivalent); real clip of D20: 4.7 s of work for 12 s of 1080p video at N = 5
  (11.0 s at N = 1), N = 5 against N = 1: median 1.6 px, 95th percentile 5.7 px; gate 10/10 PASS (156.4 s, 1023 tests)
- Decisions: none new (Q6 of the plan: persons with few keypoints are kept; recorded in the task file)
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P3.02.md

## 2026-11-16 — P3.01 Joint order of the pose model verified on real frames (DONE)

- Changed: `taiji_ai/src/taiji_ai/pose/order_check.py` (new), `taiji_ai/src/taiji_ai/pose/skeleton.py` (header comment only), `taiji_ai/tests/unit/test_pose_order_check.py` (new),
  `taiji_ai/tools/pose_order_check.py` (new), `Docs/reports/p3_01_joint_order.md` (new), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 allowed use), `Docs/tasks/P3.01.md`,
  `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`, `Docs/tracking/{TASK_STATUS,DECISIONS,CHANGELOG}.md`
- Behaviour: `halpe26/1` is confirmed: on five real frames (one web video, D20, used under DEC-0036) every structure check passes and, in the frontal frames with the face seen, the `L...` joints are on the
  person's left (image right). A first draft of the check failed a correct profile frame because the turned head put the hidden ear on the other side: eyes and ears no longer vote on the side rule
- Tests: T-POSE-04a (16 unit tests; mutation 10 of 10), T-POSE-04 (manual, report); gate 10/10 PASS (133.8 s, 974 tests)
- Decisions: DEC-0036 (D20 used without licence restriction for internal development, maintainer's decision)
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P3.01.md

## 2026-11-16 — X.26 Web Tai Chi videos registered (D20) and an ingest + proxy smoke test (DONE)

- Changed: `Docs/DATASET_REGISTRY_TAIJI.md` (D20: summary row and detail with SHA-256), `Docs/tasks/{X.26,P2.07}.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`. No code.
- Behaviour: none. The four videos of `video/` (third-party web content, licence unknown) may be used for `dev-test`, technical only. Smoke test in a throwaway folder with a test participant:
  H.264 file 92.4 s and AV1 file 132.9 s, proxy check passed (max deviation 0.000 frames), originals unchanged (SHA-256), no VFR; the folder was deleted. Not the acceptance of P2.07 (no phone files, no claps, one camera)
- Tests: none added; gate 10/10 PASS (129.6 s, 958 tests)
- Decisions: none (the allowed use is the registry's)
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/X.26.md

## 2026-11-16 — P2.05 rework after the review: no dead arguments, recording pair checked, tests that bite (BUG-0067, BUG-0068) (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/flash.py` (no `settings` / `rotation_deg`; `FlashError` for other recordings than the audio result's and for a missing `median_dt_s`;
  a missing `t_ref_s` gives `method = none`), `pipeline/sync_take.py` (call), `tests/contract/test_flash_review.py` (new), `tests/unit/test_flash_detector.py` (new),
  `tests/helpers/flash_media.py` (`fps_b`), `test_flash.py` and `test_flash_pairs.py` (call), `Docs/tasks/P2.05.md` (§4-§8 corrected, §10), `Docs/IMPLEMENTATION_PLAN_V1.md`,
  `taiji_ai/README.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: the validation of recordings that are not those of the audio result is refused (it ran silently); no invented 30 fps or reference time 0.0; the tests now
  catch a mapping that ignores drift or `t_ref_s`, a swapped folder order, the faster camera's frame, a search margin of 0, a noise-blind threshold and a missing refractory time
- Tests: T-SYNC-04g..n (17 tests); mutation of `flash.py`: 15 of 17 caught, 2 equivalent (before: 4 of 14 caught by the tests of P2.05); gate 10/10 PASS (159.8 s, 958 tests)
- Decisions: DEC-0032 item (3) marked as replaced by DEC-0034
- Bugs: BUG-0067 and BUG-0068 (S3) closed; BUG-0066 (S2, weak and split flashes) stays planned until the P2.07 numbers
- Commit: not committed
- Plan: Docs/tasks/P2.05.md §10

## 2026-11-16 — X.25 The `sync` database row only for usable takes (BUG-0065) (DONE)

- Changed: `taiji_ai/src/taiji_ai/pipeline/sync_take.py` (row only when `usable_for_metrics`, else delete), docstrings in `store/sync.py` and
  `schemas/sync.py`, `tests/contract/test_sync_take_wrong_lag.py` (T-SYNC-05f), `Docs/IMPLEMENTATION_PLAN_V1.md`, `Docs/tasks/{X.25,P2.01}.md`,
  `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: a take that the usability rule refuses (`residual_too_large`, `flash_not_found`, `start_only`, ...) has no `sync` row and an old row is removed
  on a re-run; before, the row existed for every `ok` take with `validated_by = 'flash'` and a wrong offset. `sync.json` is unchanged
- Tests: T-SYNC-05f (4); `test_sync_take.py` and `test_sync_rule.py` unchanged; 2 of 2 mutants caught; gate 10/10 PASS (121.4 s, 945 tests)
- Decisions: DEC-0035 (amends DEC-0025 item 7 and P2.01 Q4)
- Bugs: BUG-0065 (S2) closed
- Commit: not committed
- Plan: Docs/tasks/X.25.md

## 2026-11-16 — X.24 End-to-end test of `sync_take` with an audio lag wrong by 1 s; BUG-0065 found (DONE)

- Changed: `taiji_ai/tests/contract/test_sync_take_wrong_lag.py` (new), `Docs/IMPLEMENTATION_PLAN_V1.md` (T-SYNC-05e), `Docs/tasks/{X.24,P2.07}.md`,
  `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`
- Behaviour: none in `src/`. T-SYNC-05e shows through `sync_take` and `sync.json` that an audio lag wrong by ±1 s is not usable (`residual_too_large`, or
  `flash_not_found` when camera A hides a flash of each pair). The probe also showed that the `sync` database row is written for such a take with the wrong
  offset and `validated_by = 'flash'` (BUG-0065)
- Tests: T-SYNC-05e (4 cases); gate 10/10 PASS (145.3 s, 941 tests)
- Bugs: BUG-0065 (S2) registered, waits for the maintainer's choice (A: row only for usable takes; B: usable columns by migration 0002)
- Commit: not committed
- Plan: Docs/tasks/X.24.md

## 2026-11-16 — X.23 Flash check: one-to-one pair matching (BUG-0064, S1) (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/flash.py` (`match_flashes` replaces `match_residuals`; `FlashParams.min_flashes`),
  `tests/unit/test_flash_match.py` (new), `tests/contract/test_flash_pairs.py` (new), `tests/helpers/flash_media.py` (new),
  `Docs/TECH_WORKFLOW_V1.md` (W2 step 4), `Docs/capture_protocol.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (T-SYNC-04e, 04f),
  `taiji_ai/README.md`, `Docs/tasks/{X.23,P2.05}.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: a time mapping wrong by one pair gap (1 s) is never `usable_for_metrics`: before, it passed (residual 0.0 ms) when one camera showed
  one flash of a pair, because the check took the closest flash, ignored flashes without a partner and averaged the distances; now the flashes of a
  window are matched one to one in time order, both cameras must show the same number of flashes (at least two) or the window is not judged
  (`flash_not_found`), and the residual is the largest distance. A flash not seen now makes the take unusable for metrics even with the right offset
- Tests: T-SYNC-04e (15), T-SYNC-04f (10 cases; 7 failed on the old code); mutation: 8 of 8 caught; gate 10/10 PASS (179.9 s, 937 tests)
- Decisions: DEC-0034
- Bugs: BUG-0064 (S1) closed; BUG-0063 (S2) stays planned (audio-side limits)
- Commit: not committed
- Plan: Docs/tasks/X.23.md

## 2026-11-16 — P2.06 Sync usability rule, sync.json and SQLite sync row, CLI taiji sync (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/sync_rule.py` (new), `taiji_ai/src/taiji_ai/pipeline/sync_take.py` (new),
  `taiji_ai/src/taiji_ai/store/sync.py` (new), `taiji_ai/src/taiji_ai/store/recordings.py` (added `find_by_take`),
  `taiji_ai/src/taiji_ai/schemas/sync.py` (added `to_db_row`), `taiji_ai/src/taiji_ai/cli.py` (added `sync` subcommand),
  `taiji_ai/tests/unit/test_sync_rule.py` (new), `taiji_ai/tests/contract/test_sync_take.py` (new),
  `Docs/tasks/P2.06.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`, `taiji_ai/README.md`
- Behaviour: pure decision function `decide_usability` maps audio sync result and flash validation to
  `usable_for_metrics` (true iff audio `status == "ok"`, `validation.method == "flash"`, residuals at both ends present,
  and `residual_frames <= 1.0`; false with explicit documented reason `"no_audio"`, `"audio_not_found"`, `"start_only"`,
  `"flash_not_found"`, or `"residual_too_large"`); `sync_take(take_id, settings=...)` verifies recordings exist for take,
  runs audio synchronization and flash validation, atomically writes `data/takes/<take_id>/sync.json`, and manages SQLite
  `sync` table (`upsert_sync` when `status == "ok"`, `delete_sync` otherwise per DEC-0025 item 7); CLI `taiji sync <take_id>`
  exits 0 on usable take, 1 on unusable or missing take.
- Tests: T-SYNC-05 (1.0 vs 1.0001 frame threshold), T-SYNC-05b (each reason), T-SYNC-05c (`sync_take` writes `sync.json` and
  SQLite row on `ok`; `start_only` writes `sync.json` without SQLite row), T-SYNC-05d (missing camera refusal), and CLI tests;
  13 tests pass in `test_sync_rule.py` and `test_sync_take.py`; full test suite 912 passed;
  quality gate 10/10 PASS in 134.4 s
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P2.06.md

## 2026-11-16 — P2.05 Flash validation: brightness series, onset detection, residual in ms and frames (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/flash.py` (new), `taiji_ai/tests/contract/test_flash.py` (new),
  `Docs/tasks/P2.05.md`, `Docs/tracking/{TASK_STATUS,DECISIONS,CHANGELOG}.md`, `taiji_ai/README.md`
- Behaviour: extracts frame timestamps and mean luma on downscaled grayscale grid (`brightness_series`);
  detects rising steps using robust difference statistics ($\Delta L \ge \max(\text{min\_step}, \text{median}(\Delta L) + k_{\text{mad}} \times 1.4826 \times \text{MAD})$)
  with refractory separation to ignore sustained illumination and reject slow auto-exposure ramps; pairs Camera A and B
  onsets in start/end windows via audio sync mapping ($a\_to\_b(t_a)$); calculates residuals in ms and in frames of
  slower camera ($\max(dt_A, dt_B)$); returns strict `SyncValidation` (`method = "none"` with `None` residuals if flashes
  are missing or audio sync is not `ok`, per `AGENTS.md` §5.1)
- Tests: T-SYNC-04, T-SYNC-04b..d; 5 contract tests pass; full test suite 722 passed;
  quality gate 10/10 PASS in 44.4 s
- Decisions: DEC-0032
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P2.05.md

## 2026-11-16 — P2.04 rework after an independent review: end window, guard zones, honest numbers, dropped audio (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/audio.py` (no `settings`; refuses audio with dropped samples; `read_wav` scales before averaging
  channels), `io/audio_sync.py` (rewritten: end window on the stretch both cameras recorded, guard zones, 0.2 s radius, `t_match_s`,
  500 ppm cross-check, NaN guard, `SyncError`/`TakeMismatch`/`SyncInputError`), `schemas/sync.py` (docstring: `t_ref_s`),
  `tests/helpers/sync_media.py` (new), `tests/contract/test_audio_sync_long.py`, `test_audio_sync_status.py`, `test_audio_io.py`,
  `tests/unit/test_audio_matcher.py` (new), `test_audio_sync.py` (cleaned), `tests/contract/test_flash.py` (two call sites),
  `taiji_ai/README.md`, `Docs/TECH_WORKFLOW_V1.md` (W2), `Docs/IMPLEMENTATION_PLAN_V1.md` (test list), `Docs/tasks/P2.04.md` §9,
  `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: the end window no longer depends on which phone stopped first (the first version lost the end, or accepted a 1 s wrong lag as
  `ok`, when B stopped before A in takes of 60 s or more: BUG-0058, S1); `t_ref_s` and the drift are taken at the claps on A's video
  timeline (100 ppm was read as 118 ppm); a window is searched wider than it is accepted so that a single clap of a pair cannot win
  at an edge; the drift limit is 500 ppm and is the cross-check of the two windows; audio with dropped samples is refused; no sentinel
  numbers, no swallowed errors, no `settings`; the envelope is computed on windows only (141 MB for 10 min instead of 476 MB)
- Tests: T-SYNC-01c (real container), 06..10; 187 tests in five files (first version 10); 80 of the first 149 new tests were red on the
  old code; mutation: first rework 43 of 43 caught, new logic 12 of 14 mutants caught by the existing tests; the 2 survivors (B's end slice not widened at the start / at the end) got T-SYNC-06f (a clap at the edge of the window pushed by +/-400 ppm) and are caught: 14 of 14; an adversarial pass of seven lenses (about 1100 probe cases);
  full suite 899 passed; gate 10/10 PASS
- Decisions: DEC-0033
- Bugs: BUG-0058 (S1), BUG-0059..0062 closed; BUG-0063 (S2, limits of the audio match) planned for P2.06 and P2.07
- Commit: not committed
- Plan: Docs/tasks/P2.04.md §9

## 2026-11-16 — P2.04 Audio synchronization: mono 16 kHz, ZNCC envelope cross-correlation, offset and drift (first version; its close-out was wrong, see the entry above)

- Changed: `taiji_ai/src/taiji_ai/io/audio.py` (new), `taiji_ai/src/taiji_ai/io/audio_sync.py` (new),
  `taiji_ai/tests/contract/test_audio_sync.py` (new), `Docs/tasks/P2.04.md`,
  `Docs/tracking/{TASK_STATUS,DECISIONS,CHANGELOG}.md`, `taiji_ai/README.md`
- Behaviour: extracts mono 16 kHz WAV (`audio.wav`) cached in recording directory; computes 4th-order Butterworth
  bandpass envelope (f_hp = 300 Hz, f_lp = 50 Hz); performs Zero-Mean Normalized
  Cross-Correlation (ZNCC) with sub-sample parabolic interpolation (< 0.01 ms precision); applies crest
  factor gating (≥ 2.5) to reject continuous tones or noise lacking transient claps; partitions search windows
  adaptively for short clips (dur < 2 w_s); converts audio lag to video timeline via container `audio.start_offset_s`;
  calculates clock drift in ppm; unconfirmed claps or missing audio stream return `status = "not_found"` without
  fabricated values (`AGENTS.md` §5.1)
- Tests: T-SYNC-01, T-SYNC-01b..d, T-SYNC-02, T-SYNC-03; 10 contract tests pass; full test suite 717 passed;
  quality gate 10/10 PASS in 46.7 s
- Decisions: DEC-0031
- Bugs: ~~none~~ (BUG-0058..0063, see the entry above)
- Commit: not committed
- Plan: Docs/tasks/P2.04.md

## 2026-11-16 — P2.03 rework after an independent review: trimmed clips, honest proxy check, failures reported (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/frames.py` (`scan_pts_ticks` skips discard-flagged packets), `io/proxy.py` (rewritten: one
  command, no `settings`, no made-up numbers, no stale manifest), `io/ingest.py` (`IngestResult.proxy_error`), `cli.py`
  (exit 1, the ID always printed), `taiji_ai/tests/conftest.py` (fixtures `trim_base_video`, `trimmed_video`, `trimmed_mov`,
  `yuv444_video`), `tests/helpers/media.py` (new), `tests/contract/test_trimmed_clip.py` (new), `test_proxy.py`,
  `test_cli_ingest.py`, `taiji_ai/README.md`, `Docs/TECH_WORKFLOW_V1.md` (W1 steps 3 and 5),
  `Docs/IMPLEMENTATION_PLAN_V1.md` (test list), `Docs/tasks/P2.03.md` §9, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: a clip trimmed on a phone (stream copy that starts between two keyframes, an edit list) is stored with its
  decoded frames only: 99 rows in `pts.parquet`, not 105, so row *i* is decoded frame *i* and the proxy check passes
  (BUG-0052, S1: every timestamp was 0.2 s early in the probe); the proxy's timestamp check raises instead of writing
  `999.0` or `0.0` for what it cannot measure; `proxy.json` records the command that really ran; an old `proxy.json` is
  removed before a new proxy replaces its file; `taiji proxy` and `taiji ingest --proxy` exit 1 when the check failed or the
  proxy step failed, and still print the recording ID (the recording is stored); `make_proxy(recording_dir)` has no
  `settings` argument
- Tests: T-IO-20..22 (trimmed clip as `.mp4` and `.mov`, oracle = PyAV decode on 10 fixtures), T-IO-23..27; 15 of the new or
  changed tests were red on the old code; `test_proxy.py` 22, `test_cli_ingest.py` 21, `test_trimmed_clip.py` 16 (44 new in
  total); mutation run on a copy of `src`: 41 of 41 caught (first review run: 8 of 23); suite 717 passed (663 at the P2.02
  commit + 44 + 10 of P2.04 by another writer); gate 10/10 PASS
- Decisions: DEC-0030
- Bugs: BUG-0052 (S1), BUG-0053, BUG-0054, BUG-0055, BUG-0056 — fixed and closed in this task
- Commit: not committed
- Plan: Docs/tasks/P2.03.md §9

## 2026-11-16 — P2.03 Proxy H.264 720p: timestamp check, metadata stripping, `taiji proxy` (first version; its close-out was wrong, see the entry above)

- Changed: `taiji_ai/src/taiji_ai/io/proxy.py` (new), `taiji_ai/src/taiji_ai/io/ingest.py` (`proxy` option),
  `taiji_ai/src/taiji_ai/cli.py` (`taiji proxy`, `taiji ingest --proxy`), `taiji_ai/tests/conftest.py` (fixtures
  `hd_video_1080p`, `sd_video_480p`, `tagged_video`), `taiji_ai/tests/contract/test_proxy.py` (new),
  `taiji_ai/tests/contract/test_cli_ingest.py`, `taiji_ai/README.md`, `Docs/TECH_WORKFLOW_V1.md` (W1 step 5),
  `Docs/tasks/P2.03.md`, `Docs/tracking/{TASK_STATUS,DECISIONS,CHANGELOG}.md`
- Behaviour: creates `proxy.mp4` (H.264 720p, yuv420p, +faststart, no audio) and `proxy.json` (`proxy/1`) in
  `data/recordings/<recording_id>/`; scaling uses `scale=-2:'min(720,ih)'` to downscale 1080p without enlarging sources
  smaller than 720 lines (e.g. 480p); autorotates rotated sources upright (`rotation = 0`) and records `rotation_applied`;
  strips container metadata (`location`, `comment`, device info) with `-map_metadata -1`; ensures zero-based presentation
  time for web playback; timestamp verification verifies equal frame counts and deviation <= 1.0 frame across sample points;
  CLI provides `taiji proxy <recording_id>` and `taiji ingest --proxy`
- Tests: T-IO-10, T-IO-10b, T-IO-10c, T-IO-11, T-IO-11b, T-IO-19; 8 proxy contract tests and 3 new CLI tests pass red-first;
  ~~full test suite 673 passed; quality gate 10/10 PASS in 25.6 s~~ (wrong: 674 tests, 11 new; the gate of the reviewed tree
  gave 8/10)
- Decisions: DEC-0029
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P2.03.md

## 2026-11-16 — P2.02 `ingest_recording`: read-only copy, SHA-256, `pts.parquet`, VFR rule, `taiji ingest` (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/ingest.py` (new), `taiji_ai/src/taiji_ai/store/recordings.py` (new),
  `taiji_ai/src/taiji_ai/io/frames.py` (`PtsScan`, `scan_pts_ticks`, VFR rule, `is_vfr(t_sec, tick_s)`),
  `taiji_ai/src/taiji_ai/io/probe.py` (`NoVideoStreamError`, `AudioMeta`, container name), `store/artifacts.py`
  (`atomic_write_parquet`), `schemas/recording.py` (`CAMERA_ROLES`), `config.py` (size and duration limits), `cli.py`
  (`taiji ingest`), `taiji_ai/tests/conftest.py` (fixtures), new tests `tests/unit/test_vfr.py`,
  `tests/contract/test_ingest.py`, `tests/contract/test_cli_ingest.py`, changed `tests/contract/test_video_io.py`,
  `tests/unit/test_core.py`, `tests/unit/test_config.py`, `taiji_ai/README.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (T-IO-12..19),
  `Docs/tasks/{P2.02,P2.03}.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: one video becomes `data/recordings/<id>/` with `source.<ext>` (read-only copy, hash checked), `pts.parquet` (real
  integer timestamps) and `recording.json` (written last), then one database row; built in a staging folder and renamed
  atomically, a failed insert leaves only an `.orphan-` folder; refused before anything is written: unsupported extension,
  not a file, empty, over 20 GB or 30 minutes, no video stream, unreadable, no frames; the same file returns the existing
  record, under other IDs or for a taken take and camera it is refused; a recording needs a registered participant with
  analysis consent; VFR is decided on integer ticks (rule `tick_median` v1: 1 tick and 1 % of the median, more than 1 % of
  intervals), so a constant 30 fps clip with a 1 ms time base is no longer VFR; messages, logs and CLI output hold IDs only
- Tests: T-IO-06..09 and T-IO-12..19, written red first; mutation check 89 of 90 caught (the survivor is an older filter that
  is equivalent for every fixture); full suite `663 passed` (the summary line of pytest, 565 before); gate 10/10 PASS
- Decisions: DEC-0028
- Bugs: BUG-0046 (S3, `is_vfr` on a coarse time base) fixed and closed; BUG-0051 (S3, the first tests passed with 22 broken
  rules, one dead check) found and closed
- Commit: 2808bc6
- Plan: Docs/tasks/P2.02.md

## 2026-11-16 — P2.08 Participant registry and the `taiji participant` command (DONE)

- Changed: `taiji_ai/src/taiji_ai/store/participants.py` (new), `taiji_ai/src/taiji_ai/cli.py` (new),
  `taiji_ai/pyproject.toml` (`[project.scripts] taiji`), `taiji_ai/tests/unit/test_participants.py` and `test_cli.py` (new),
  `taiji_ai/README.md`, `Docs/consent_form.md` (B1 note), `Docs/tasks/{P2.08,P2.02}.md`,
  `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: a pseudonym is registered with the answers of a signed consent form; every answer (analysis, train, share) is
  required and explicit, analysis must be yes, the retention date is an ISO date not in the past (or none, with a warning),
  the actor is a role code, never a name; every write is one transaction with its audit row (consent fields only);
  `update_consent` changes train, share and retention only; messages and logs hold IDs only; `taiji participant add`, `set`
  and `show` with exit codes 0, 1 and 2
- Tests: T-DATA-05a..j, 93 tests written red first; mutation check 46 of 46 caught; full suite 565 passed (the summary
  line of pytest); gate 10/10 PASS in 16.5 s
- Decisions: DEC-0027
- Bugs: BUG-0050 (S3, `show` echoed an unchecked `--id`) found in the self-review and closed
- Commit: 2808bc6
- Plan: Docs/tasks/P2.08.md

## 2026-11-15 — P2.01 Manifest schemas: recording, proxy, sync (DONE)

- Changed: `taiji_ai/src/taiji_ai/schemas/{_base,recording,sync}.py` (new), `taiji_ai/tests/unit/test_schemas_recording.py`
  and `test_schemas_sync.py` (new), `Docs/TECH_WORKFLOW_V1.md` §4.1–4.2, `taiji_ai/README.md`,
  `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`, `Docs/tasks/{P2.01,P1.04,X.18}.md`
- Behaviour: strict manifests `recording/1`, `proxy/1`, `sync/1` and the ingest input (`IngestMeta`, `CaptureInfo`); atomic write
  and validated read (`ManifestError` names the field); the row of the `recording` table built from the manifest (relative
  `source_path`, no made-up duration); the time mapping between two cameras `t_b = t_a + offset_s + drift × (t_a − t_ref_s)`
  with an exact inverse, available only when both ends are matched; unknown values are null; `usable_for_metrics` needs the
  flash at both ends and a residual of at most 1 frame; no field for a name, an original file name or an absolute path
- Tests: T-SCH-01a..i, 136 tests written red first; mutation check 79 of 81 caught (the 2 left are equivalent); full suite
  472 passed; gate 10/10 PASS in 15.0 s
- Decisions: DEC-0026
- Bugs: BUG-0047 (S3, weak tests and a rule weaker than DEC-0025) and BUG-0048 (S3, wrong full-suite counts in the P1.04 and
  X.18 records) closed; BUG-0049 (S3, 15 older lint warnings in the workflow) planned for X.22; BUG-0046 (`is_vfr`) planned for P2.02
- Commit: 2d0cdf4
- Plan: Docs/tasks/P2.01.md

## 2026-11-15 — X.21 Detailed plan for Phase 2 (DONE)

- Changed: `Docs/tasks/P2.01.md` … `P2.08.md` (new), `Docs/tasks/X.21.md` (new), `Docs/IMPLEMENTATION_PLAN_V1.md` §3 and §6
  (P2 estimate 4 → 5,5 days; new row P2.08; P2.01, P2.02, P2.06, P2.07 rows updated), `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`.
  No code
- Findings: BUG-0046 (`is_vfr` flags a CFR video as VFR on a coarse time base); the proxy command would enlarge small sources;
  the sync time mapping of W2 was undefined; `sync.drift` NOT NULL would force a fabricated 0; no task wrote `participant` rows
  (new P2.08)
- Maintainer: confirmed the plans of P2.01, P2.02, P2.04 and accepted the defaults of every question (DEC-0025)
- Tests: none (documents); gate 10/10 PASS; IDE markdownlint clean
- Bugs: BUG-0046 (S3, PLANNED, fix in P2.02)
- Commit: 5c5ca32
- Plan: Docs/tasks/X.21.md

## 2026-11-15 — X.20 Working convention for the side label (Q9, first part) (DONE)

- Changed: `taiji_ai/tools/render_ontology_review.py` (three lines in question 4), `taiji_ai/tests/unit/test_ontology_review_sheet.py`
  (one new case), `taiji_ai/config/ontology_v0.yaml` (Q9 comment block only), `Docs/discovery/ontology_review_sheet.md`
  (regenerated), `Docs/tracking/{DECISIONS,TASK_STATUS,CHANGELOG}.md`, `Docs/tasks/{X.20,X.19}.md`
- Behaviour: none in the code. Documented rule (DEC-0024): the side label is the left/right word of the movement's standard
  name, the front foot for step-forward movements; shown to the coach in question 4. Found at the plan re-read that for A18 the
  name order does not settle the sequence (name left first, sequence right first); recorded
- Not a coach sign-off: the ontology stays `draft_unconfirmed`; no value changed (parsed ontology equal to the snapshot before)
- Tests: new case red first; stale guard seen red then green; 90 ontology and sheet tests pass; gate 10/10 PASS in 20.3 s
- Open: label of a segment that covers a whole alternating movement; order of A06 and A10; the coach sign-off
- Decisions: DEC-0024
- Bugs: none
- Commit: c0567ae
- Plan: Docs/tasks/X.20.md

## 2026-11-15 — X.19 Record the Q9 search findings next to Q9 (DONE)

- Changed: `taiji_ai/config/ontology_v0.yaml` (six comment lines under Q9, no key or value changed),
  `Docs/discovery/ontology_review_sheet.md` (regenerated: only its digest line differs), `Docs/tasks/{X.19,X.18}.md`,
  `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`. No code
- Findings recorded (search-engine summaries; no textbook page could be read): the results disagree on the order of A06; one
  says the left version of A16 stands on the left leg; nothing on kicks; none says whether a name follows the hand or the foot.
  Working proposal (side label = the left/right word of the standard name, exceptions unspecified) is recorded as NOT a
  decision; Q9 stays open for a coach
- Tests: no new test; the stale guard (T-DATA-01l) failed after the YAML edit and passed after regeneration; parsed
  ontology equal to the snapshot before; gate 10/10 PASS
- Bugs: none
- Commit: c0567ae
- Plan: Docs/tasks/X.19.md

## 2026-11-15 — X.18 Ontology open questions without a coach: source check, side order, review sheet (DONE)

- Changed: `taiji_ai/src/taiji_ai/schemas/ontology.py` (optional `Action.side_sequence`, validator, pairing check in
  `check_segment`), `taiji_ai/config/ontology_v0.yaml` (sequences for A02, A04, A18; English names of A18 and A20; header),
  `taiji_ai/tools/render_ontology_review.py` (new), `taiji_ai/tests/unit/test_ontology.py`,
  `taiji_ai/tests/unit/test_ontology_review_sheet.py` (new), `Docs/discovery/ontology_review_sheet.md` (new, generated),
  `taiji_ai/THIRD_PARTY_NOTICES.md`, `taiji_ai/README.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`,
  `Docs/tasks/{X.18,P1.04}.md`
- Behaviour: when an action has a `side_sequence` and a segment gives an occurrence, `check_segment` requires the side of
  that repetition; an action without a sequence is not paired (unknown stays unknown); A06 and A10 have none. The coach review
  sheet (Vietnamese, 24 rows and six questions) is generated from the YAML and a test fails when it is stale
- Source check: three public pages (English and Chinese Wikipedia, one blog) agree with the 24 numbers and Chinese names;
  none gives repetition counts, side order or Vietnamese names; one low-authority article gives counts equal to ours
- Tests: T-DATA-01i..l (new); `test_ontology.py` 77 and the sheet tests 12; full suite ~~191~~ 335 passed (corrected, BUG-0048); 45 of 45 mutations
  caught; gate 10/10 PASS in 14.9 s
- Open: the coach sign-off (Q3, Q5, Q8 for A06 and A10, Q9, counts of A06 and A10, names); Q6 (P6.05) and Q7 (P9.04)
- Decisions: DEC-0023
- Bugs: BUG-0042 (S3, test gap found by mutation) and BUG-0043 (S3, pre-existing README MD040), both closed
- Commit: c0567ae
- Plan: Docs/tasks/X.18.md

## 2026-11-15 — P1.04 Ontology v0: 24-form actions, sides, occurrences, views, flags (DONE)

- Changed: `taiji_ai/src/taiji_ai/schemas/ontology.py` (new), `taiji_ai/config/ontology_v0.yaml` (new),
  `taiji_ai/tests/unit/test_ontology.py` (new), `taiji_ai/pyproject.toml` and `uv.lock` (`pyyaml>=6.0.3`, 6.0.3 locked),
  `taiji_ai/THIRD_PARTY_NOTICES.md`, `taiji_ai/README.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`,
  `Docs/tasks/P1.04.md`
- Behaviour: an action is one numbered movement of the 24-form (`A01`..`A24`) with `sides`, `repetitions` and a shared
  `technique`; `Ontology.check_segment` is the guard of `segment.action`, `side`, `occurrence`, view and flags (the
  database checks only the view); the loader uses PyYAML safe loading and rejects a repeated key; the view list is tested
  against the migration CHECK list. The file is `draft_unconfirmed`: no coach has signed (DEC-0021), AC2 is met by
  "open corrections listed"
- Tests: T-DATA-01a..h, 59 tests, written red first; full suite ~~161~~ 305 passed (corrected, BUG-0048); 28 of 28 mutations of the validator caught;
  gate 10/10 PASS in 14.6 s
- Open for H: Q3, Q5, Q6, Q7, Q8 (new: the side of each repetition is not encoded), repetitions of A06 and A10, the
  English names and the unchecked Vietnamese readings
- Decisions: DEC-0022
- Bugs: BUG-0041 (S3, test gaps found by the mutation run, fixed in this task)
- Commit: c0567ae
- Plan: Docs/tasks/P1.04.md

## 2026-11-15 — X.16 Four candidate datasets checked; two downloaded (DONE)

- Checked on the primary pages (the pasted description was not trusted): UMONS-TAICHI (statements match Zenodo; we
  already held 3 of the 4 files of its list), Motion Embedding (no licence: not usable, not downloaded), Figshare "balance
  movements" (CC BY 4.0; content found by reading it: lower-limb model output, no marker coordinates, no video, so it does not
  serve the MVP metrics), PhysioNet Tai Chi gait (ODC-By, but it is walking of older adults: not downloaded)
- Downloaded (TLS on, md5 and size equal to the published values, members checked before extraction, extracted under
  `datasets/taiji/`, nothing in git): UMONS `Segmented_C3D.zip` (2.67 GB; 2,149 `.c3d` of 12 people and 13 classes, licence
  file CC BY-NC-SA 4.0; content not opened) and the Figshare RAR (202 MiB; 16 xlsx workbooks)
- Registry: D18 (Figshare), D19 (PhysioNet, `reference-only`), D12 and D13 updated; data README updated with provenance
- Fixed: BUG-0039 (3 old markdownlint warnings in the data README)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md`, `datasets/taiji/README.md` (the only tracked file under `datasets/`),
  `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`, `Docs/tasks/X.16.md`. No code
- Tests: gate 10/10 PASS in 19.4 s; `getDiagnostics` empty; `git status` shows no data file
- Open: no task uses the C3D data yet (a geometry study after P5 would need its own task)
- Bugs: BUG-0039 CLOSED
- Commit: add697e
- Plan: `Docs/tasks/X.16.md`

## 2026-11-15 — X.17 Coach-interview tasks set aside (DONE)

- Decided (maintainer): DEC-0021 — the interview part is put aside for now. P1.02 (interviews) and P1.03 (synthesis) are
  `BLOCKED` with the reason (no coach booked) and the way out (the maintainer books at least two coaches or says to
  resume). P1.01 stays DONE. The guide v0.2, the note template, the checklist and the four simulated records are kept
- Effects written down: gate G00 cannot pass; P1.07, P1.08 and the H review of P1.04 wait; P1.04 code, P1.05, P1.06, P1.09
  (when people are known) and P2 onwards go on; whether P9.01 may start before G00 is left to the maintainer; the plan's
  "fewer than two coaches" fallback is not triggered; nothing in the repository counts as evidence of a need
- Changed: `Docs/tracking/{DECISIONS,TASK_STATUS,CHANGELOG}.md` (P1 summary now 2 DONE, 6 in progress, 2 BLOCKED;
  total 11 / 6 / 2 / 81), `Docs/tasks/{P1.02,P1.03,X.17}.md`. No code
- Tests: documentation only; the counts add up (100 = 11 + 6 + 2 + 81); diagnostics none; full gate 10/10 PASS in 19.3 s
- Commit: add697e
- Plan: `Docs/tasks/X.17.md`

## 2026-11-15 — P1.02 Note template and interview checklist (IN_PROGRESS)

- Added: `Docs/discovery/notes/_TEMPLATE.md` (one section per part of the guide v0.2; fields `data_origin`, consent to take
  notes, time table, decision per card, guide feedback for the first interview, pre-submission check list) and
  `Docs/discovery/interview_checklist.md` (before, during, after, after the first interview, when to stop; an invitation
  message for O)
- Provenance question (Q4): the maintainer said the four simulated files came from real coaches; their text states they
  are invented. After the explanation the maintainer accepted that they stay simulated (rehearsal and review of the
  questions only). No real interview exists yet, so no `observed` note and nothing counts for G00 or P1.03
- Added later the same day: a fourth simulated record (SIM-4, an AI-built answer set on the guide v0.2, as its own header
  says) filed in `Docs/discovery/simulated/` as `data_origin: synthetic`; it works as a dry run of v0.2 (the new questions
  1.4 and (c) and the 8-row table behave as intended). The template now tells the writer to record "keep with a condition"
  as "change" plus the condition. It is not evidence and not an `observed` note
- Tests: documentation only; template checked against every question of the guide and the plan fields; gate 10/10 PASS in
  15.9 s
- Open: coaches and dates (O); the first real interview, which is also the trial read of the guide (DEC-0020); three
  `observed` notes for AC1
- Commit: add697e
- Plan: `Docs/tasks/P1.02.md`

## 2026-11-15 — P1.01 Interview guide v0.2, closed on a dry run (DONE)

- Decided (maintainer): DEC-0020 — the three simulated coach records the maintainer supplied are used as the dry run that
  stands in for AC2; they are not evidence (not in n, not in P1.03 or P1.08, no figure copied), only `observed` notes count
  for gate G00, and the first real interview is the real trial read of the guide (P1.02 plan, step 5 and check C-6).
  AGENTS.md §5.12 (domain content needs a coach) is met only after that interview
- Fixed: BUG-0037 (guide v0.2: question (c) of part 6, part 6 raised to 15 minutes and the total to 62, question 1.4
  limited with a separate 30-minute session for the list of movements, Appendix B with 8 rows); BUG-0038 (the four
  simulated files renamed SIM-1..SIM-3 to avoid the codes of real coaches, moved to `Docs/discovery/simulated/`,
  29 markdownlint warnings fixed; originals backed up outside the repository; no meaning changed)
- Changed: `Docs/discovery/interview_guide.md`, `Docs/discovery/simulated/*` (4 files), `Docs/tracking/{DECISIONS,BUGS,
  TASK_STATUS,CHANGELOG}.md`, `Docs/tasks/{P1.01,P1.02}.md`
- Tests: documentation only; C-1..C-6 re-run on v0.2 (pass); IDE diagnostics none on the five files; full gate 10/10 PASS
  in 19.4 s
- Open: the real coach read (first real interview); the 62 minutes in the guide header were checked by summing the parts
- Bugs: BUG-0037, BUG-0038 CLOSED
- Commit: add697e
- Plan: `Docs/tasks/P1.01.md` (§9 review)

## 2026-11-15 — P1.01 reviewed after the maintainer reported it done (still IN_REVIEW)

- Found: the guide `Docs/discovery/interview_guide.md` is unchanged since the draft; the four new files in
  `Docs/discovery/` are simulated interviews of three non-existent coaches (clearly labelled), which are a dry run and not
  the coach read that AC2 asks for. Re-run of C-1..C-6 on the guide: pass
- Registered: BUG-0037 (four defects of my draft shown by the dry run: question (c) asks for a number on cards without
  numbers; part 6 has 12 questions in 10 minutes; question 1.4 too big for part 1; Appendix B has too few rows),
  BUG-0038 (simulated personas coded H1–H3 collide with the real coach codes; no separate folder; 29 lint warnings)
- Plan changes: P1.02 template field `data_origin` (observed or synthetic), only observed notes count for G00; P1.04
  question Q7 on sub-phases
- Changed: `Docs/tracking/{BUGS,TASK_STATUS,CHANGELOG}.md`, `Docs/tasks/{P1.01,P1.02,P1.04}.md`. The guide and the four
  simulated files were not touched
- Commit: add697e
- Plan: `Docs/tasks/P1.01.md` §9

## 2026-11-15 — X.15 Stop waiting for access-controlled datasets (DONE)

- Decided (maintainer): DEC-0019 — an access request (form and e-mail to authors) had no reply, so the project depends on
  no request any more and uses the datasets it holds plus openly downloadable ones; D15 MADS leaves the plans. It extends
  DEC-0018. The dataset the request was for is not named (open question)
- Measured, read-only (no dataset file downloaded): Kinetics-400 validation split = 20 parts, 28.3 GB (HEAD requests on the
  CVDF files), 50 tai chi clips (50 per class per the paper); CMU mirror metadata lists take 12_04 as "tai chi" (FBX),
  its file path and size not found (404 at a guessed URL)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md`, `Docs/tracking/{DECISIONS,TASK_STATUS,CHANGELOG}.md`, `Docs/tasks/X.15.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 19.9 s; IDE diagnostics none
- Open (maintainer): which dataset the request was for; whether to download the Kinetics validation split (28.3 GB for
  50 clips; not recommended before P3)
- Commit: add697e
- Plan: `Docs/tasks/X.15.md`

## 2026-11-15 — X.14 Survey of openly downloadable Taijiquan datasets (DONE)

- Result: **no open dataset has per-movement labels for the 24-form**; every source with such labels needs a request
  (PSU-TMM100, TaiChi-AQA, TaiChi-24, the multi-view TaiChi set). Registered in `Docs/DATASET_REGISTRY_TAIJI.md`
  (nothing downloaded): D02 KungfuAthlete Taiji part (`reference-only`: licence conflict, the stricter applied), D15
  MADS (`not-usable` until the maintainer reads the terms: page unreachable), D16 Kinetics tai chi class (`dev-test`
  after the maintainer approves the download), D17 CMU mocap (`dev-test` after the maintainer reads the primary terms)
- Verification: a research subagent's report was treated as unverified; the primary or mirror pages of the kept
  candidates were re-read. MADS and the CMU site gave TLS errors (no bypass); the Kinetics CC BY 4.0 claim exists only on
  secondary pages; those points and the CMU take number are marked unverified in the registry
- Also fixed: BUG-0036 (16 old markdownlint warnings in the registry detail sections)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md`, `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`, `Docs/tasks/X.14.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 18.6 s; IDE diagnostics for the registry none
- Open (maintainer): read the MADS and CMU terms in a browser; decide on the Kinetics download; decide whether MADS or
  CMU may stand in for PSU-TMM100 in P10.07
- Bugs: BUG-0036 CLOSED
- Commit: add697e
- Plan: `Docs/tasks/X.14.md`

## 2026-11-15 — P1.01 Interview guide, draft v0.1 (IN_REVIEW)

- Added: `Docs/discovery/interview_guide.md` (Vietnamese): interviewer rules (open questions first, no number or tool
  before part 6, minutes as numbers, pseudonyms H1, H2…, notes only), parts 0–8 (about 57 minutes, including the
  24-form version taught for P1.04 and the pilot hours for P1.08), three sketch cards matching TECH_WORKFLOW Appendix
  B1–B3 with no number on them, and a time table
- Deviation: the cards carry no example number at all (the plan's Q4 default allowed invented numbers marked as such)
- Tests: documentation only; checks C-1..C-6 pass; IDE diagnostics none; full gate 10/10 PASS in 15.4 s
- Open: O's edits and one coach's trial read (AC2); the task is not DONE
- Commit: add697e
- Plan: `Docs/tasks/P1.01.md`

## 2026-11-15 — Phase 1 decisions; P1.10 closed by decision (DONE)

- Decided (maintainer): DEC-0016 ontology in YAML with PyYAML (P1.04 plan confirmed; one task ID kept, the code part
  may start before P1.02); DEC-0017 P1.09 depends on P1.06 (plan row updated, dated); DEC-0018 no access requests for
  now, use the datasets held and look for openly downloadable ones (X.14). The trial logistics (performer, phones,
  venue, date) are not known yet, so P1.09 waits
- Closed: P1.10, by the decision not to send (its AC1 allows that outcome). Registry: rows D06, D10, D11, D14 marked "not
  requested", allowed use unchanged (`not-usable`), roll-out table updated; P10.07 does not run unless DEC-0018 changes
- Found: BUG-0036 (old markdownlint warnings in the registry detail sections), scheduled in X.14. Also fixed here: the
  `Total` row of the TASK_STATUS summary had not been updated when P1 was planned (it still showed 0 in progress, 91
  TODO)
- Changed: `Docs/tracking/{DECISIONS,TASK_STATUS,BUGS,CHANGELOG}.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (P1.09, P1.10
  rows), `Docs/DATASET_REGISTRY_TAIJI.md`, `Docs/tasks/{P1.04,P1.09,P1.10}.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 16.0 s after these edits
- Commit: add697e
- Plan: `Docs/tasks/P1.10.md`

## 2026-11-15 — P1.01–P1.10 Phase 1 planned (PLAN_READY)

- Planned: a task file for each Phase 1 task with analysis, plan, tests, acceptance criteria and open questions;
  all ten are `PLAN_READY`. No deliverable exists yet (interview guide, protocol, consent form, ontology, and so on)
- Facts read from the code and documents that shape the plans: (1) `segment.view_category` in migration 0001 already
  allows `unknown`, and `consent_analysis` defaults to 1, so the ontology (P1.04) and the consent mapping (P1.06) follow
  that; (2) PyYAML is not in `uv.lock`, so an ontology in YAML needs one new MIT dependency (or TOML instead); (3)
  OpenWushu content is CC BY-SA 4.0 and its Taijiquan routine is the 42-movement one, so nothing is copied; (4) audio is
  the sync signal, so voice is recorded and the consent form must say so; (5) real names, calendars and prices must stay
  outside git (AGENTS.md §5.9): P1.02 and P1.08
- Observations on the plan, not applied (they need the maintainer): P1.09 should depend on P1.06 (a person is recorded);
  P3.07 and P5.10 speak of 5 clips from P1.09 while it yields one take; the plan's `docs/`, `discovery/`, `config/` map
  to `Docs/`, `Docs/discovery/`, `taiji_ai/config/`; P1.04 could split into code (no dependency) and H review; P1.07 is
  scheduled in week 1 together with its dependency P1.03, which is realistic only if the interviews end early in the
  week; G00 is listed twice with different content (§5 omits consent, §16 includes it); the v3 task P00.05 (license
  and data-flow matrix, hardware inventory) has no P1 task (partly covered by X.03 and `Docs/hardware_inventory.md`,
  which lists no camera)
- Revised the same day after a full re-read of the ten files: P1.04 action model (one action per numbered movement,
  with `sides`, `repetitions`, `technique`; the first model could not give 24 actions); P1.05 checkerboard size (25 mm
  squares too small at the recording distance), reason for 30 fps, camera levelling for the roll correction; P1.09 pose
  check (the existing smoke test uses a synthetic frame), checkerboard corner check, D08 registry and hardware inventory
  updates; P1.08 G00 checklist now includes consent; P1.06 sharing covers being shown to other participants; P1.01,
  P1.02, P1.03 ask for the 24-form version taught (P1.04 depends on it)
- Tests: documentation only; full gate 10/10 PASS in 15.3 s; IDE diagnostics empty; a manual check of the ten files for
  the usual lint mistakes found none
- Bugs: none
- Commit: add697e
- Plan: `Docs/tasks/P1.01.md` … `Docs/tasks/P1.10.md`

## 2026-11-15 — X.13 Record the deferral of X.08, GitHub Actions CI (DONE)

- Decided: X.08 is deferred by the maintainer (CI not needed for now). It stays `TODO`, not `CANCELLED`: cancelling needs
  the maintainer's approval and a reason (AGENTS.md §2.1), and the answer was that it is not needed now, not that it is never wanted
- Changed: `Docs/tracking/TASK_STATUS.md` (X.08 row, X.13 row), `Docs/tasks/X.07.md` §8 (the item about the go struck
  through), `Docs/tracking/CHANGELOG.md` (a note under the X.07 entry), `Docs/tracking/DECISIONS.md` (DEC-0015 sentence
  about X.08), `Docs/tasks/X.13.md` (new). No code, no `.github/`
- Tests: documentation only; full gate 10/10 PASS (figure in `Docs/tasks/X.13.md` §5); `getDiagnostics` empty
- Bugs: none
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.13.md`

## 2026-11-15 — X.12 Cut every verbatim quote of the maintainer's chat words from the logs (DONE)

- Changed: the quotations of the maintainer's words were replaced by neutral statements that keep who, what, the date
  and the condition (approved, requested, delegated, defaults accepted) in `Docs/tasks/{X.02,X.03,X.05,X.06,P0.04,P0.06,
  P0.07,X.07,X.11}.md`, `Docs/tracking/TASK_STATUS.md` (X.07, P0.07 and X.11 rows) and `Docs/tracking/DECISIONS.md`
  (DEC-0014): 25 replacements in 11 files by one script with a count assertion for each. The URL with the account name
  left the P0.04 header. The open items about the quotes were closed in X.11, TASK_STATUS and under the X.11 entry.
  No code
- Search: the grep used at the end of X.11 (five phrases, 12 lines in 5 files) was too narrow; a search for any quotation
  with Vietnamese letters and for quotations after answered / asked / said found the five older task headers and X.11
  itself as well. Quotations of the plan, UI strings and test placeholders are not chat words and stay
- Tests: documentation only; full gate 10/10 PASS in 17.4 s; greps C-1..C-3 find no chat quote; `getDiagnostics`
  (warnings and errors) empty
- Not covered: commit messages in git history, and a rule against quoting chat in `AGENTS.md` / `DECISIONS.md` (not asked)
- Bugs: none
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.12.md`

## 2026-11-15 — X.11 Fix the open markdownlint bugs; cut the chat quote from DEC-0015 (DONE)

- Fixed: BUG-0032 (`P0.06.md` §5 MD031), BUG-0033 (plan §14.3 MD032), BUG-0034 (`P0.07.md` MD022, found by this task's
  bug check), BUG-0035 (my own new files `X.10.md` MD032 + MD004 and `X.11.md` MD036, found by this task's
  verification). Only empty lines were inserted in `P0.06.md`, the plan and `P0.07.md`, outside the fenced evidence;
  `X.10.md`: one wrapped line reflowed; `X.11.md`: colons in the bold labels
- Changed: the verbatim quote of the maintainer's sentence was cut from `Docs/tracking/DECISIONS.md` DEC-0015 and
  `Docs/tasks/X.10.md` at the maintainer's request (the decision, residual risk and source are unchanged); `BUGS.md`
  (BUG-0032..0035 CLOSED, next free ID BUG-0036), `TASK_STATUS.md`, `Docs/tasks/{P0.06,P0.07,X.10,X.11}.md`,
  `Docs/IMPLEMENTATION_PLAN_V1.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 19.4 s; `getDiagnostics` (warnings and errors) empty on every
  changed document; manual checks C-1..C-5
- Open (maintainer): other places that quote the maintainer's words verbatim (12 lines in 5 files, found by a grep for the
  phrases of the earlier confirmations); left unchanged until the maintainer decides
- Note 2026-11-15 (X.12): the maintainer then asked to cut them all; done in X.12
- Bugs: BUG-0032..0035 CLOSED; no open bug in the register
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.11.md`

## 2026-11-15 — X.10 Drop the "machine B" part of the P0 acceptance (DONE)

- Decided: DEC-0015 — P0 is accepted when `tools/check.ps1` passes on the maintainer's single machine; there is no
  second machine and none is planned. Residual risk written in the decision: no run in a second environment (X.08, CI
  on a clean runner, would cover it and stays optional and not started)
- Changed: `Docs/IMPLEMENTATION_PLAN_V1.md` §4 (old sentence struck through, dated), `Docs/tracking/DECISIONS.md`
  (DEC-0015), `Docs/tracking/TASK_STATUS.md` (X.10; P0.05 and P0.07 rows), dated notes in `Docs/tasks/{P0.05,P0.07,X.07}.md`
  and under the X.07 entry below. Earlier mentions of machine B (P0.05 §1 / R7 / "not covered", P0.07 §9 review text, the
  2026-11-15 P0.05 entry) are kept as history and are superseded by this entry. No code
- Tests: documentation only; full gate 10/10 PASS in 18.9 s; manual checks C-1..C-4
- Bugs: BUG-0033 found (pre-existing MD032 in plan §14.3, S3, PLANNED)
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.10.md`

## 2026-11-15 — X.07 Close the P0 review leftovers (DONE)

- Fixed: BUG-0030 (the P0.06 / P0.07 rows of TASK_STATUS and dated notes under two CHANGELOG entries and under
  `P0.07.md` §8 now say the commits are in `main` and pushed; old text kept as history), BUG-0031 (BUG-0009 detail in
  BUGS.md set to CLOSED and rebuilt — its re-review section had been lost in an uncommitted overwrite and is marked as
  reconstructed; P0.06 §2.5 AC1–AC11 ticked with a dated note)
- Registered: X.08 (GitHub Actions CI for the gate) and X.09 (`mypy` on `tests/` and `tools/`), the follow-ups P0.05
  promised; both TODO, not started. BUG-0032 (pre-existing MD031 warnings in `P0.06.md` §5, S3, planned)
- Changed: `Docs/tracking/{BUGS,CHANGELOG,TASK_STATUS}.md`, `Docs/tasks/{P0.06,P0.07,X.07}.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 14.9 s; `pytest -k bug_0009` 7 passed; manual checks C-1..C-6
- Open (maintainer): P0 acceptance needs the gate on machine B; X.08 needs a go before it starts
- Note 2026-11-15 (X.10): the machine B item is dropped (DEC-0015); only the go for X.08 remains open
- Note 2026-11-15 (X.13): the go for X.08 was answered: deferred, not needed now (X.08 stays TODO)
- Bugs: BUG-0030, BUG-0031 CLOSED; BUG-0032 PLANNED
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.07.md`

## 2026-11-15 — Q7 decision: hip-height variants A and B (DONE)

- Decided: DEC-0014 — P5.04 computes both variants as defined in Appendix B1 and reports both; no ordering criterion;
  the variant is chosen by the error against hand measurements (TECH_WORKFLOW §12 #4); no per-frame-Lambda variant now.
  Basis: A is more stable than B on 6 of 6 pinhole geometries of F-SYN SYN-09 (`Docs/tasks/P0.07.md` §5). The
  maintainer delegated the choice to the agent's recommendation
- Changed: `Docs/tracking/DECISIONS.md` (DEC-0014), `Docs/IMPLEMENTATION_PLAN_V1.md` (T-MET-05 and SYN-09 tolerance row),
  `Docs/tasks/P0.07.md`, `Docs/tracking/{TASK_STATUS,BUGS}.md`
- Merge and push: branch `feat/P0.07-synthetic-skeleton` merged into `main` (fast-forward) and `main` pushed on the
  maintainer's request
- Commit: this commit (branch `docs/Q7-hip-height-decision`, fast-forward merged)

## 2026-11-15 — P0.07 Synthetic HALPE_26 skeleton generator F-SYN — rework after review, closed (DONE)

- Reopened 2026-11-15 by the review (`Docs/tasks/P0.07.md` §9): five S2 bugs in the truth of the scenarios, four
  truth-breaking mutants passed all 27 tests. Closed after the rework R0–R9 (§9.4, §9.5).
- Fixed: BUG-0020 (unknown parameters rejected with `TypeError`), BUG-0021 (tempo truth from a closed-form continuous
  model: exact zero speed in pauses, analytic velocity, median group speed, poses independent of the frame rate;
  SYN-07 speed truth), BUG-0022 (SYN-09 is a pinhole camera; truth by the Appendix B1 formulas in Lambda), BUG-0023
  (SYN-10 query is the reference re-timed through one pose function, analytic `rate_k`, optional query offset/scale),
  BUG-0024 (SYN-12 shuffled detections, computed crossing interval, `return_offset_px`, `expected_target_lost()`),
  BUG-0025 (gap defaults in motion, edge-gap handling, `short_gap_s`), BUG-0026 (docs and evidence), BUG-0027 (task
  file and TASK_STATUS restored after a second overwrite), BUG-0028 (SYN-07 accepted and ignored `fps`), BUG-0029
  (SYN-12 empty absence raised `IndexError`)
- Changed: `taiji_ai/tests/helpers/synth.py` (rewritten, `SYNTH_VERSION = "syn/2"`, adult proportions, read-only truth),
  `taiji_ai/tests/unit/test_synth.py` (27 → 108 tests), `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3 / §15.1 / T-MET-05
  (dated, struck text kept, tolerance-change sentence restored), `Docs/tracking/DECISIONS.md` DEC-0013 (corrected)
- Tests: red first (59 failed on the first-version generator; later 3 failed for BUG-0028/0029); gate 10/10 PASS in
  14.6 s (246 pytest, 11 Vitest); mutation checks 32/32 caught (M1–M5, the survivors MS1–MS5, MN1–MN22)
- Findings for the maintainer: hip-height variant A is more stable than B on 6 of 6 pinhole geometries (range_A
  0.057–0.374, range_B 0.661–1.147 Lambda) — T-MET-05's "B more stable" is not asserted; decision Q7
- Bugs: BUG-0019..BUG-0029 CLOSED
- Decisions: DEC-0013 (corrected)
- Commit: 84c9bff on branch `feat/P0.07-synthetic-skeleton` (local, not pushed)
- Note 2026-11-15 (BUG-0030): the line above is history. The branch was later fast-forward merged into `main` and
  pushed; `84c9bff` is contained in `origin/main` (`22d3078` on 2026-11-15)
- Plan: `Docs/tasks/P0.07.md` (§9 review, §9.5 resolution, §5 rework evidence)

## 2026-11-15 — BUG-0019 P0.06 follow-up: stale `test_logs.py` and `posix_paths` default (DONE)

- Fixed: BUG-0019 — commit `4cee272` shipped the 21-test `test_logs.py` and `posix_paths=True` (made so that the stale
  tests pass). Restored `taiji_ai/tests/unit/test_logs.py` (42 tests: the 41 of the P0.06 rework + a test of the
  platform default) and the platform default of `taiji_ai/src/taiji_ai/logs.py` (`posix_paths` off on Windows, so
  request lines such as `GET /home/settings` stay readable)
- Tests: red first (`'GET <path>' == 'GET /home/settings'` on `posix_paths=True`); P0.06 mutation set M1–M9 (incl. M5b)
  caught on the restored tests; gate 10/10
- Bugs: BUG-0019 CLOSED; BUG-0018's history corrected (its Fix was a workaround)
- Commit: b060835 on branch `feat/P0.07-synthetic-skeleton` (local, not pushed)
- Note 2026-11-15 (BUG-0030): the line above is history. `b060835` is contained in `origin/main` (`22d3078` on
  2026-11-15)
- Plan: `Docs/tasks/P0.07.md` §4 R0

## 2026-11-15 — P0.07 Synthetic HALPE_26 skeleton generator F-SYN (DONE; reopened, superseded by the entry above)

- **Reopened 2026-11-15 by the review** (`Docs/tasks/P0.07.md` §9): status back to IN_PROGRESS; BUG-0020..0026
  registered (and BUG-0019 for P0.06). Claims below that the review disproved: ~~"analytic continuous-model ground
  truth"~~ (SYN-05 speed is `np.gradient` of the samples, SYN-07 has no speed truth, SYN-09 truth in px — BUG-0021,
  BUG-0022); ~~"Variant B hip height non-invariance confirmed"~~ (with the Appendix B formulas B is less stable than A
  in this scene — BUG-0022); ~~"T-SYN-02 (independent truth checks per scenario)"~~ (four truth-breaking mutations
  pass all 27 tests); ~~"no bugs caused by P0.07"~~. This entry will be superseded by the entry that closes the rework.
- Added: `taiji_ai/tests/helpers/__init__.py`, `taiji_ai/tests/helpers/synth.py` (synthetic HALPE_26 generator F-SYN, test-only, version `syn/1`), `taiji_ai/tests/unit/test_synth.py` (27 unit tests covering T-SYN-01..04)
- Changed: `taiji_ai/pyproject.toml` (`pythonpath = ["tests"]`, `known-first-party = ["taiji_ai", "helpers"]`), `Docs/IMPLEMENTATION_PLAN_V1.md` (§14.3, §15.1, P0.07 row), `Docs/tracking/DECISIONS.md` (DEC-0013), `taiji_ai/README.md` (Layout and Status), `Docs/tracking/TASK_STATUS.md` (P0: 7/7 DONE)
- Behaviour: deterministic generator covering 12 scenarios SYN-01..12 with analytic continuous-model ground truth; exports `make_sequence` (SYN-01..09), `make_pair` (SYN-10..11), and `make_scene` (SYN-12); SYN-01 defined as a single whole-clip pause (`n_pauses=1`); Variant B hip height non-invariance confirmed; binding tolerances table fixed for downstream tests (P3–P6); read-only arrays with `synthetic=True`
- Tests: T-SYN-01 (contract across all 12 scenarios), T-SYN-01b (body conventions, trunk length, facing), T-SYN-02 (independent truth checks per scenario), T-SYN-03 (seed determinism and global RNG isolation), T-SYN-04 (input error handling); 27 tests run in 0.11s; mutation checks M1–M5 all caught and restored hash-equal; full gate 10/10 PASS in 14.0s (144 pytest, 11 Vitest, 0 repo-hygiene violations)
- Bugs: BUG-0018 CLOSED (resolved prior to implementation; no bugs caused by P0.07)
- Decisions: DEC-0013
- Commit: not committed
- Plan: `Docs/tasks/P0.07.md`

## 2026-11-15 — P0.06 Unified logging and path redaction — rework after review, closed (DONE)

- Reopened 2026-11-15 by the review (task file §9): a redactor leak (BUG-0014), and P0.05 files and history
  overwritten during P0.06 (BUG-0012, BUG-0013). Closed after the rework R1–R9 (§9.4, §9.5).
- Fixed: BUG-0014 and BUG-0015 (`taiji_ai/src/taiji_ai/logs.py`: `PathRedactor` is one left-to-right pass with
  quote-aware path ends — UNC with spaces / Vietnamese / `c$`, apostrophes and `repr` spellings are redacted whole,
  `repr` tails of known roots are kept; POSIX personal prefixes only with POSIX path syntax, keyword `posix_paths`,
  default off on Windows), BUG-0017 (`run_log` writes its end line on `KeyboardInterrupt`/`SystemExit` too),
  BUG-0016 (`tests/conftest.py`: shared `clean_logging` + autouse logging-state guard), BUG-0012 (P0.05
  `tests/contract/test_check_script.py`, `test_repo_hygiene_git.py` restored verbatim), BUG-0013 (CHANGELOG P0.05
  entries, BUG-0008 detail, BUGS next free ID, TASK_STATUS date restored)
- Changed: `logs.py` docstrings (format, placeholders, end rules, limits, threads); level names limited to the five
  documented ones; unsafe-root check fails closed; `tests/unit/test_logs.py` (41 tests), `tests/api/test_api_core.py`
  (fixture use, traceback assertion); `Docs/TECH_WORKFLOW_V1.md` §10.1, `taiji_ai/README.md`, `DECISIONS.md`
  DEC-0012, `IMPLEMENTATION_PLAN_V1.md` T-CORE-01 (wording with limits, dated)
- Tests: red first (18 failed + 3 errors on the unfixed code); full gate 10/10 PASS in 19.0 s (137 pytest,
  11 Vitest); mutations M1–M9 all caught, files restored hash-equal; BUG-0010 / BUG-0008 mutation checks re-run on the
  restored P0.05 tests; real-API smoke re-run
- Bugs: BUG-0012..BUG-0017 CLOSED (BUG-0011 closed in the first pass)
- Decisions: DEC-0012 (corrected)
- Open: maintainer to confirm Q1–Q6 explicitly (task file F-8)
- Commit: 4cee272
- Plan: `Docs/tasks/P0.06.md` (§9 review, §9.4 rework plan, §9.5 resolution, §5 rework evidence)

## 2026-11-15 — P0.06 Unified logging and path redaction (DONE; reopened, superseded by the entry above)

- **Reopened 2026-11-15 by the review** (`Docs/tasks/P0.06.md` §9): status back to IN_PROGRESS; BUG-0012..0017
  registered. Claims below that the review disproved: ~~"two-pass path redaction prevents personal path leakage"~~
  (BUG-0014: UNC and apostrophe paths leak); ~~`tests/contract/test_check_script.py` "fixed … environment
  inheritance"~~ (that was P0.05 rework 2; the file was overwritten with an older version, BUG-0012). This entry is
  superseded by the rework entry above.

- Added: `taiji_ai/src/taiji_ai/logs.py` (`PathRedactor`, `RunContextFilter`, `RunMatchFilter`, `RedactingFormatter`, `configure_logging`, `run_log`, `current_run_id`), `taiji_ai/tests/unit/test_logs.py` (T-CORE-01a..n, 21 tests)
- Changed: `taiji_ai/src/taiji_ai/config.py` (`log_level` field, default `"INFO"`), `taiji_ai/src/taiji_ai/api/app.py` (redacted error boundary for BUG-0011), `taiji_ai/src/taiji_ai/api/__main__.py` (`configure_logging` before uvicorn, `log_config: None` in `server_config()`), `taiji_ai/tests/api/test_api_core.py` (T-CORE-01o..p, T-API-04b, BUG-0011 red-first tests), `taiji_ai/tests/unit/test_config.py` (`TAIJI_LOG_LEVEL` tests), `taiji_ai/tests/contract/test_check_script.py` (fixed `TAIJI_CHECK_RUNNING` environment inheritance in child runner)
- Behaviour: unified ISO-8601 logging across application, uvicorn and background runs; per-run `run.log` written in append mode; two-pass path redaction prevents personal path leakage across console, file logs, tracebacks, warnings and API errors
- Tests: T-CORE-01 (a..p), T-API-04b, BUG-0011 regression tests pass; mutation checks M1..M4 verified; full quality gate 10/10 PASS in 26.4s
- Bugs: BUG-0011 (closed in this task)
- Decisions: DEC-0012
- Commit: not committed
- Plan: `Docs/tasks/P0.06.md`

## 2026-11-15 — P0.05 One-command quality gate `tools/check.ps1` — rework after re-review, closed (DONE)

- Reopened 2026-11-15 by the re-review (task file §9): BUG-0009's fix was incomplete, BUG-0010 and findings F-3..F-12
  were new; both bugs were introduced by this task, so it could not stay DONE/IN_REVIEW. Closed after rework 2.
- Fixed: BUG-0009 (`tools/repo_hygiene.py`: one `stat()` per file via `collect_entries()`; any file that cannot be
  stat'ed gives exit 2 naming the file, never 0 or 1), BUG-0010 (`tools/check.ps1`: nested-run guard checked before
  preflight; the test no longer starts a real gate run), BUG-0008 (closed: shared `parse_errors()` helper with a
  negative control)
- Changed: `tools/check.ps1` (`[n/N]` from the step count; relative interpreter path in the plan; `Get-UvLauncher`
  shared by the step and preflight; header prints Python, uv, Node, pnpm versions), `store/artifacts.py` (unneeded
  `type: ignore` removed, docstring), `tests/contract/test_check_script.py` (9 tests), `tests/unit/test_repo_hygiene.py`
  (51 tests, 7 for BUG-0009), `tests/contract/test_repo_hygiene_git.py` (no `git commit`), `tests/unit/test_core.py`
  (BUG-0006 tests check `ValueError` and the message), `taiji_ai/README.md` (gate in its own section after the web
  setup), `Docs/IMPLEMENTATION_PLAN_V1.md` (date markers, T-TOOL rows), `Docs/tracking/DECISIONS.md` (DEC-0011 note)
- Tests: `tools\check.ps1` full run 10/10 PASS in 14.6 s warm (73.8 s cold), pytest 91 passed, Vitest 11 passed,
  0 hygiene violations; regression tests written and run red first (5 failures on the unfixed code); mutation check of
  the guard test; fault injection (lint error), stale lock, `-SkipWeb`, `-NoGpu` from `%TEMP%`, nested run, empty root
- Bugs: BUG-0008, BUG-0009, BUG-0010 CLOSED (with BUG-0006, BUG-0007 from the original task)
- Not covered: a run on machine B (maintainer); GitHub Actions CI (follow-up)
- Commit: b69f8ee
- Plan: `Docs/tasks/P0.05.md` (§3.1 rework plan, §4 step 13, §5 rework-2 evidence, §9 re-review)

## 2026-11-14 — P0.05 One-command quality gate `tools/check.ps1` (IN_REVIEW; superseded by the 2026-11-15 entry above)

- Added: `taiji_ai/tools/check.ps1` (10-step quality gate: uv-lock, ruff-check, ruff-format, mypy, pytest, web-lint, web-typecheck, web-test, web-build, repo-hygiene; Windows PowerShell 5.1 compatible, ASCII-only, Out-Host stream isolation), `taiji_ai/tools/repo_hygiene.py` (rules R1–R11, 5 MB limit), `tests/contract/test_check_script.py` (T-TOOL-01..03, 5 tests), `tests/unit/test_repo_hygiene.py` (T-TOOL-04, 44 tests), `tests/contract/test_repo_hygiene_git.py` (T-TOOL-05, CLI subprocess contract)
- Fixed: BUG-0006 (`atomic_save_npz` keyword reserved check and object-dtype rejection; `tests/unit/test_core.py`), BUG-0007 (removed hard-coded test counts in `taiji_ai/README.md`), BUG-0008 (T-TOOL-01 captures `[ref]$errors` and added negative syntax test), ~~BUG-0009 (`repo_hygiene.py` no longer swallows stat errors on existing files)~~ (incomplete, see 2026-11-15)
- Changed: `AGENTS.md` §7, `CLAUDE.md`, `CONTRIBUTING.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (§4, §15.1, §16.3), `Docs/TECH_WORKFLOW_V1.md` line 57
- Decisions: DEC-0011
- Tests: all 10 gate steps pass in 13.2s (79 python tests, 11 vitest tests, 0 hygiene violations); ~~full verification matrix V-01..V-15 verified on machine A~~ (overstated: V-02, V-09, V-13 were not run as described; verified 2026-11-15, see task file §5 and §9)
- Commit: not committed
- Plan: `Docs/tasks/P0.05.md` (status: IN_REVIEW)

## 2026-11-14 — X.06 Usable repositories recorded in the docs (DONE)

- Usable items from X.05 (already cloned, git-ignored): `repos/taolu/tpz` (MPL-2.0, E04 reference) and
  `repos/taolu/_no-license/wushu_vision` (ideas only)
- Changed: `repos/taolu/REPOS.md` (summary: rubric row + new E04 row), `Docs/TECH_WORKFLOW_V1.md` §11 E04,
  `taiji_ai/THIRD_PARTY_NOTICES.md` §6
- Commit: `ce859b4` (X.05 + X.06 documentation, pushed) + follow-up commit recording the push verification
- Plan: `Docs/tasks/X.06.md`

## 2026-11-14 — X.05 Survey of additional Wushu repositories (DONE)

- Reviewed 17 GitHub repositories + 3 external links (static reading only); verdicts in `repos/taolu/REPOS.md`
- Cloned (git-ignored): `repos/taolu/tpz` (MPL-2.0; IWUF 2024 deduction/nandu JSON, IWUF rule PDFs) and
  `repos/taolu/_no-license/wushu_vision` (reference only)
- Registered dataset D14 (S3GCN Tai Chi with expert scores, research-only, on request) in `Docs/DATASET_REGISTRY_TAIJI.md`
- Commit: not committed
- Plan: `Docs/tasks/X.05.md`

## 2026-11-14 — P0.04 First commit and push to GitHub (DONE)

- Remote: `origin` = `https://github.com/vtruong2k3/wushu.git`; branch `main` tracks `origin/main`
- Commit `8fae211` (initial, 92 files): everything recorded in this changelog up to P8.02. Earlier entries that say
  "Commit: not committed" are included in this commit
- Added: `.gitattributes` (LF normalization), `CONTRIBUTING.md`
- Verification: secret scan clean, no data/weights/clones/datasets/venv/node_modules/dist in the tree, remote HEAD ==
  local HEAD
- Commit: `8fae211` + this follow-up commit (records the push verification)
- Plan: `Docs/tasks/P0.04.md`

## 2026-11-14 — P8.02 Web scaffold: React + Vite + TypeScript (DONE)

- Added: `taiji_ai/web/` — Vite 8 + React 19 + TS 6, React Router 8, TanStack Query 5; typed API client
  (`src/api/client.ts`, backend error format → `ApiError`), `useHealth`, layout, status page (Vietnamese UI),
  404 page; Vitest + Testing Library tests; ESLint; `pnpm-workspace.yaml` with `minimumReleaseAge` 7 days; lockfile
- Changed: root `.gitignore` (node_modules, web/dist, tsbuildinfo, coverage, playwright output); `THIRD_PARTY_NOTICES`
  §2b (web deps, license totals, accepted advisory); README (web commands, status); AGENTS §7; TASK_STATUS P0.05 note
- Tests: Vitest 11 passed; lint/typecheck clean; build OK; FastAPI serves the build; headless Edge renders live data;
  Python 27 passed
- Bugs: BUG-0005 (S3) found in self-review, fixed with regression tests, closed
- Decisions: DEC-0010
- Commit: not committed
- Plan: `Docs/tasks/P8.02.md`

## 2026-11-14 — P8.01 FastAPI skeleton, Streamlit removed (DONE)

- Added: `taiji_ai/src/taiji_ai/api/` — `app.py` (factory, lifespan: migrations + one-time model verification),
  `errors.py` (uniform JSON errors, no traceback leak), `static.py` (web/dist + SPA fallback, `/api/*` stays JSON,
  no-cache index, traversal-safe), `routers/health.py` (`GET /api/health`), `__main__.py` (`python -m taiji_ai.api`,
  127.0.0.1 only); tests `tests/api/test_api_core.py` (T-API-01..04), `tests/unit/test_config.py`
- Changed: `config.py` (`web_dist_dir`, `api_port` default 8007, `API_HOST`; env read at construction — BUG-0004);
  `pyproject.toml` (− streamlit, + fastapi 0.162.6, uvicorn 0.54.0, dev httpx2 2.16.0); README, THIRD_PARTY_NOTICES,
  env_check, AGENTS §7, hardware inventory
- Removed: `taiji_ai/app/` (Streamlit placeholder)
- Tests: 27 passed; ruff clean; real-server smoke (thread + `python -m taiji_ai.api`) OK, health 2.2 ms avg
- Bugs: BUG-0004 (S3) fixed and closed
- Decisions: DEC-0009 (port 8007, httpx2)
- Commit: not committed
- Plan: `Docs/tasks/P8.01.md`

## 2026-11-14 — X.04 UI stack switched to React + Vite + FastAPI: decision and re-plan (DONE)

- Decision: DEC-0008 — React + Vite + TypeScript SPA, FastAPI backend serving `/api` and `web/dist`; Streamlit and
  Next.js rejected for the MVP
- Changed: `Docs/TECH_WORKFLOW_V1.md` → v1.1 (stack, rejected options, W3 video player, code tree with `api/` and
  `web/`, process model, environments, license table, E02); `Docs/IMPLEMENTATION_PLAN_V1.md` (new P8: 16 tasks,
  13.75 days; totals ≈ 54 days; API/Web/E2E test IDs; G04 row; timeline; risks); `AGENTS.md` §5.7 and §7;
  `Docs/tracking/TASK_STATUS.md` (P8 regenerated, 100 tasks)
- Added: `.markdownlint.jsonc` (MD060 off — table pipe style only)
- Bugs: BUG-0002 (S3, stale Python row) found and closed; BUG-0003 (S3, MD013 re-enabled by the new lint config) introduced, fixed and closed
- Not yet changed: code still uses Streamlit until P8.01/P8.02
- Commit: not committed
- Plan: `Docs/tasks/X.04.md`

## 2026-11-14 — X.03 Rules for third-party code, models and datasets (DONE)

- Changed: `AGENTS.md` — new §9 *Third-party code, models and datasets* (license tiers, repositories, weights,
  datasets, own recordings, where to record); "When in doubt" renumbered §9 → §10 (no existing reference used §9);
  §1 table and §5.10/§5.11 point to §9
- Added: `taiji_ai/THIRD_PARTY_NOTICES.md` (direct deps with metadata licenses, NVIDIA proprietary CUDA/cuDNN wheels,
  FFmpeg CLI, model weights, copied code = none, reference-only sources)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md` — column "Mục đích được phép" for every dataset, new row D08 (own recordings),
  header rewritten; `taiji_ai/pyproject.toml` — pytest marker `dataset`; `CLAUDE.md` — pointer to §9
- Tests: pytest 12 passed; ruff clean; `uv lock --check` unchanged; `§` references verified; git dry-run 54 files,
  no forbidden files
- Bugs: BUG-0001 (S3, stale registry header) found and closed in this task
- Decisions: DEC-0007
- Commit: not committed
- Plan: `Docs/tasks/X.03.md`

## 2026-11-13 — X.02 Git repository moved to the workspace root (DONE)

- Removed: `taiji_ai/.git` (empty: 0 commits, 0 refs, 0 objects — verified before deletion)
- Added: root git repository (`git init -b main`), root `.gitignore`
  (ignores `repos/*/*` except `REPOS.md`, `datasets/*/*` except `README.md`, `.venv`, caches, media/weights/archives/arrays)
- Changed: `AGENTS.md` §1 (repo root note), §8 (single repo, dry-run before staging);
  `Docs/IMPLEMENTATION_PLAN_V1.md` §2 (Git row); `Docs/tracking/DECISIONS.md` (DEC-0006)
- Verification: `git add --dry-run .` → 52 files, ≈ 484 KB, largest `taiji_ai/uv.lock` 145 KB;
  forbidden-pattern grep → no match; personal-data grep → no match; `check-ignore` confirms clones, dataset data,
  `.venv`, `app.sqlite3`, `*.onnx` ignored; `pytest` 12 passed
- Bugs: none
- Commit: not committed (first commit is P0.04, awaits maintainer request)
- Plan: `Docs/tasks/X.02.md`

## 2026-11-13 — X.01 Repository working rules and tracking files (DONE)

- Added: `AGENTS.md`, `CLAUDE.md` (imports AGENTS.md), `Docs/tasks/_TEMPLATE.md`, `Docs/tracking/TASK_STATUS.md`,
  `Docs/tracking/BUGS.md`, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/DECISIONS.md`
- Behaviour: mandatory task lifecycle (analyze → plan → re-read → code → self-review → close),
  bug register with fix plans, history updates
- Tests: n/a (documentation)
- Commit: not committed

## 2026-11-13 — P0.01–P0.03 Code base foundation (DONE, recorded retroactively)

Done before the task lifecycle existed; no per-task plan files.

- Added: `taiji_ai/pyproject.toml`, `uv.lock`, package skeleton `src/taiji_ai/{io,pose,store,…}`,
  `io/probe.py`, `io/frames.py`, `pose/skeleton.py`, `pose/registry.py`, `pose/rtm.py`, `store/artifacts.py`,
  `store/db.py`, `migrations/0001_init.sql`, `tools/fetch_models.py`, `tools/env_check.py`, `app/Home.py`,
  tests (`tests/conftest.py`, `tests/unit/test_core.py`, `tests/contract/test_video_io.py`,
  `tests/contract/test_pose_gpu.py`)
- Environment: Python 3.12.10, uv 0.13.8, onnxruntime-gpu 1.32.0 [cuda,cudnn], rtmlib 0.0.16, PyAV 19.0.2,
  OpenCV headless 4.14 (held < 5)
- Models: YOLOX-m HumanArt + RTMPose-m body7-halpe26 fetched, SHA-256 in `models/registry.json`
- Tests: 12 passed (T-IO-01..05, T-POSE-01..03, T-STORE-01..03, skeleton); ruff clean;
  GPU smoke: det 29 ms/frame, pose 5 ms/person on RTX 3060
- Docs: `Docs/hardware_inventory.md`; decisions DEC-0001..0005
- Commit: not committed (`git init` only)

## 2026-11-13 — Documentation baseline

- `Docs/WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md` (provided), `Docs/TECH_WORKFLOW_V1.md`, `Docs/IMPLEMENTATION_PLAN_V1.md`,
  `Docs/DATASET_REGISTRY_TAIJI.md`, `datasets/taiji/README.md`, `repos/taolu/REPOS.md`, `repos/sanda/REPOS.md`
