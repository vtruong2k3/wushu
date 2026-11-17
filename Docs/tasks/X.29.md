# X.29 — File format of the two quality layers: `pose_masked.npz` and `pose_filtered.npz`

| Field             | Value                                                                                                       |
| ----------------- | ----------------------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-17)                                                                                           |
| Owner             | agent                                                                                                       |
| Phase             | P4 (the files that W6 lists as outputs and no task of P4 owned)                                             |
| Estimate          | 0.75 day (the row said 0.5: the way back and the cross-checks of the reader are in it)                      |
| Depends on        | P4.01 to P4.08 and X.31 (all DONE, 2026-11-17; none committed); the helpers of `store/artifacts.py` (P0)    |
| Plan confirmed by | Maintainer, 2026-11-17: asked the agent to read, plan and carry out X.29 in one go (new schemas, no change to an existing one) |
| Started / Done    | 2026-11-17 / 2026-11-17                                                                                     |

## 1. Analysis

**Goal.** W6 lists three outputs: `pose_masked.npz`, `pose_filtered.npz`, `quality.json`. P4.07 wrote `quality.json` (schema `quality/1`); the two
array layers exist only in memory (`QualityResult`). P5 (metrics), P7 (pipeline, cache, run manifest) and P8 (overlay and review) need them on
disk, keyed and checkable: a strict, versioned, atomically written format for each, read back to the same arrays. (AGENTS.md section 5.3: raw, mask
and filtered layers are stored apart; 5.8: atomic writes; section 6: Pydantic v2 with `schema_version`; 9.4.6: derived artifacts carry their
`data_sources`.)

**In scope.**

- Two archives, schemas `pose_masked/1` and `pose_filtered/1`, in the style of `pose_raw/1` (P3.03): fixed array names and dtypes,
  `schema_version` and `meta_json` as 0-d text arrays, one reader per version, no pickle, no silent upgrade, atomic write, SHA-256 returned.
- `taiji_ai/schemas/quality_layers.py` (headers, `DataSource`), `taiji_ai/quality/layers_io.py` (`save_*`, `load_*`, `PoseMasked`,
  `PoseFiltered`, `QualityLayerError`).
- The reader of the filtered layer gives the **way back to the rows of the video** (`PoseFiltered.on_source()`), equal to
  `QualityResult.filtered_on_source()`; so an overlay does not need the chain, the parameters or `plan_grid`.
- Three small, behaviour-preserving refactors so that the reader uses the rules of the stages and does not copy them: `mask.frame_invalid_mask`
  (the frame rule of `apply_mask`), `resample.values_on_rows` (the formula of `GridMap.to_source`), `coverage.segment_grid_rows` (the grid rows of
  the segment, as the report counts them).
- Tests T-QLT-13a..h, W6 note, DEC-0053, README, plan row, CHANGELOG, TASK_STATUS.

**Out of scope.** The run manifest, the cache key and the choice of paths (P7: the caller passes the path and the folder must exist);
`pose_raw/1` (no change; it has no `data_sources`, see Q3); `track.parquet`; the metrics file; `QualityResult`, `QualityReport` and
`quality.json` (unchanged); deleting or garbage-collecting files; a CLI.

**What is stored (decided from the code that makes the layers).**

`pose_masked.npz` is the **mask layer** on the `T` rows of the target track, with the swap flags that were read from it (the flags change no
value; `quality.json` keeps only their counts). Arrays: `frame_index` (T,) int32; `t_sec` (T,) float64; `in_segment` (T,) bool; `tracked` (T,) bool;
`keypoints` (T, 26, 2) float32 (the value or NaN); `scores` (T, 26) float32 (the model's, as given); `reason` (T, 26) uint8 (codes 0 to 4: the mask
never emits `outlier` or `no_frame`); `n_essential_valid` (T,) int8; `frame_invalid` (T,) bool; `swap_suspect` (T, 26) bool; `swap_blocked` (T, 26) bool;
plus `schema_version` and `meta_json`.

`pose_filtered.npz` is the **final layer on the grid** (`G` rows; the rows themselves for a constant frame rate, which is every clip we have)
and the map back to the `T` rows. Grid arrays: `t_grid` (G,) float64; `keypoints` (G, 26, 2) float32 (filtered values, or the input's where a run
was too short, or NaN); `reason` (G, 26) uint8 (codes 0 to 6); `interpolated` (G, 26) bool; `filtered` (G, 26) bool; `mixed` (G,) bool;
`grid_in_segment` (G,) bool. Source arrays: `frame_index` (T,) int32; `t_sec` (T,) float64; `in_segment` (T,) bool; `source_usable` (T, 26) bool (the
cell had a value at the source: `GridLayer.to_source` gives none to a cell that had none); `back_left` (T,) int32, `back_weight` (T,) float64, `outside`
(T,) bool (a row before the first or after the last grid time and not on one: no value). Plus `schema_version` and `meta_json`. The map back is stored,
not rebuilt from `plan_grid` at load time: a file must mean the same thing after the grid rules change (X.31 changed them yesterday).

`meta_json`. Masked: `schema_version`, `skeleton`, `recording_id`, `mask` (`MaskParamsRecord`) and `swap` (`SwapParamsRecord`) as used, counts
(`n_rows`), `data_sources`. Filtered: `schema_version`, `skeleton`, `recording_id`, `params` (the whole `QualityParamsRecord` as used, the Hampel
floor in pixels), `timeline` (`n_rows`, `n_grid_rows`, `resampled`, `step_s`, `sampling_hz`, `snap_s`), counts (`n_mixed_rows`, `n_filtered_cells`),
`data_sources`. No path, no file name, no name of a person (the `recording_id` is the only identifier, as in `pose_raw/1`); no wall clock.

**The reader checks the file against itself, not only the shapes** (the same stance as `quality.json`): masked: the mask contract (`check_layer`:
finite exactly where `reason` is `ok`), reason codes at most 4, a row that is not tracked has only `not_tracked`, a tracked row has none,
`n_essential_valid` equals the usable essential joints counted from `reason`, `frame_invalid` equals the frame rule on those counts, a
`frame_invalid` row has no `ok` cell, `swap_suspect` is inside `swap_blocked` and both lie on joints of the pairs of the header. Filtered: the contract
of the gap layer (`check_gap_layer`), `filtered` only on cells with a value, `grid_in_segment` equal to the rows the report counts, header counts equal
to the arrays, and the map back against the two clocks: a row that is not `outside` and has weight 0 lies within `snap_s` of its grid time, one with a
weight lies between its two grid times with that weight (to 1e-6), an `outside` row lies outside the grid; for a timeline that is not `resampled` the
grid is the rows (`t_grid` equal to `t_sec`, weight 0, nothing outside, no mixed row).

**Existing code and docs read.** `pose/raw_io.py`, `schemas/pose.py`, `schemas/_base.py`, `store/artifacts.py`, `schemas/quality.py`,
`quality/quality_io.py`, `quality/chain.py` (`QualityResult`), `quality/mask.py`, `quality/resample.py`, `quality/coverage.py`, `quality/_checks.py`,
`tests/contract/test_pose_raw_io.py`, `tests/helpers/quality_fixtures.py`; W6 and the run folder of `Docs/TECH_WORKFLOW_V1.md`; DEC-0040 (item 5),
DEC-0050, DEC-0052; P4.01, P4.07 task files.

**Constraints that apply (AGENTS.md section 5).** 1 nothing is filled or made up on the way in or out: a NaN stays NaN with its reason, flags are
stored as flags, the reader invents nothing; 2 real timestamps: `t_sec` and `t_grid` are stored, never a frame rate; 3 the three layers stay apart
(raw, masked, filtered are three files); 4 units and coordinates in the docstring (pixels of the upright image, y down; seconds from the stream start);
8 atomic writes; 9 privacy: no path, no name, no video; `data_sources` and `consent_scope` (9.4.6, 9.5): see Q3; 11 no third-party code is used.

**Unknowns, risks, questions** (answered with defaults because the maintainer asked to go ahead; each can be reversed before P5 reads the files):

- **Q1. Do the swap flags belong in `pose_masked.npz`?** Default **yes**: they are flags on the source rows, read from the mask layer, and
  `quality.json` keeps only counts, so without them a review screen cannot mark the cells. Alternative: counts only (smaller, loses the cells).
- **Q2. Where does `frame_index` come from?** Default: **a parameter of `pose_*_from_result`**, validated (int, non-negative, strictly increasing, `T` long).
  `QualityResult` does not carry it (`run_quality_arrays` has none) and `chain.py` stays untouched; P7 passes `track.frame_index`.
- **Q3. `data_sources`.** Default: an **optional** list of `{dataset_id, license}` passed by the caller, empty meaning "one of our own recordings:
  the restrictions are those of `recording_id` in the store" (AGENTS.md 9.5). `pose_raw/1` has no such field, so the root of the chain does not carry it;
  P7 knows the recording and its dataset and passes it. Recorded as an open item for P7, not guessed here. An NC source makes the artifact NC (9.4.6): the
  files carry the licence text, the rule is the reader's of the file.
- **Q4. Float32 only.** The writer refuses a float64 layer (the pipeline from `pose_raw/1` is float32 end to end; a silent cast would change values).
- **Q5. A layer without rows** is not saved (`T >= 1`, as in `pose_raw/1`).
- *Risk:* the cross-checks duplicate rules of the stages (frame rule, essential count, segment rows). The three small refactors make the reader call the
  stage's own function, so a rule change cannot split the two; the existing tests of the stages guard the refactors.
- *Risk:* the reader rejects a file that a future stage change would still consider fine. That is the point of the version: such a change bumps
  `pose_masked/1` or `pose_filtered/1` and adds a reader; the old one stays.

## 2. Plan

**Design.**

1. `schemas/quality_layers.py` (Pydantic v2, `extra="forbid"`, frozen, `schema_version` a `Literal`): `DataSource` (`dataset_id` `^D\d{2,}$`,
   `license` 1 to 80 characters, no control characters; a tuple of them has distinct ids), `LayerCounts`, `FilteredTimeline`, `PoseMaskedMeta`,
   `PoseFilteredMeta`; they reuse `MaskParamsRecord`, `SwapParamsRecord`, `QualityParamsRecord` of `schemas/quality.py` and `UUID4_RE`.
2. `quality/layers_io.py`:
   - `@dataclass(frozen=True, eq=False) PoseMasked` and `PoseFiltered`: the arrays (read-only), the `meta`, `equals(other)` (content, NaN equal),
     `PoseFiltered.on_source(values=None)` (values default to `keypoints`; `(G, ...)` float in, `(T, ...)` out, no value where the source had none or the
     row is outside the grid); nothing else is added until P5 or P8 needs it.
   - `pose_masked_from_result(result, *, recording_id, frame_index, data_sources=()) -> PoseMasked` and `pose_filtered_from_result(...)`: build the
     layer from a `QualityResult` (read-only copies, the documented dtypes; a float64 layer is refused here).
   - `save_pose_masked(path, layer) -> str` and `save_pose_filtered(path, layer)`: check the layer with the same function the reader uses (so
     nothing is written that the reader would refuse), write with `atomic_save_npz`, return `sha256_file`. The folder must exist (not created).
     Errors: `QualityLayerError`. Build, check and write are three steps so that a damaged layer (`dataclasses.replace`) can be offered to the writer.
   - `load_pose_masked(path)`, `load_pose_filtered(path)`: `np.load(allow_pickle=False)`, version first, `_READERS` per version, then `_check_*`.
3. Refactors: `mask.frame_invalid_mask(is_tracked, n_valid, params)` (used by `apply_mask` and the reader); `resample.values_on_rows(values,
   back_left, back_weight, outside)` (used by `GridMap.to_source` and `PoseFiltered.on_source`); `coverage.segment_grid_rows(t_grid, t_sec,
   in_segment)` (used by the report's segment and by the writer/reader).

**Files to create / modify.**

| File | Change |
|---|---|
| `taiji_ai/src/taiji_ai/schemas/quality_layers.py` | new: headers |
| `taiji_ai/src/taiji_ai/quality/layers_io.py` | new: dataclasses, writers, readers, checks |
| `taiji_ai/src/taiji_ai/quality/mask.py`, `resample.py`, `coverage.py` | one small public helper each (behaviour unchanged) |
| `taiji_ai/tests/unit/test_quality_layers_meta.py` | new: headers (T-QLT-13a) |
| `taiji_ai/tests/contract/test_quality_layers_io.py` | new: round trips through the real chain, strict reader, atomic write (T-QLT-13b..h) |
| `taiji_ai/tests/helpers/quality_fixtures.py` | a builder of chain results for the tests (F1, a dropped-frame clock, SYN-08 swap) |
| `Docs/TECH_WORKFLOW_V1.md`, `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`, `Docs/tracking/*` | W6 note, T-QLT-13 row, status, DEC-0053, CHANGELOG |

**Implementation steps.**

1. Re-read this file against the code (section 3).
2. Tests first (red): the round trip and the refusals for the masked file, then the filtered file.
3. The three helpers (existing tests must stay green), then `quality_layers.py`, then `layers_io.py` (masked, then filtered).
4. Run the new tests; review every refusal test: the damaged file must be refused for the stated reason, not for another.
5. Round trip on real shapes: the D20 clips are not stored in the repo; use the UMONS adapter results of the six real files in a `dataset`-marked
   test (counts only) to check that `T` of 11,790 rows and a non-uniform clock write, read and give `on_source` equal to `filtered_on_source()`;
   time and size reported.
6. Mutation check: mutants of the writer (a column dropped, a dtype changed) and of the checks (the frame rule, the swap subset, the map back, the
   segment rows) are each caught.
7. Docs, tracking, gate, self-review, close.

**Test plan.**

| Test ID | Type | What it checks | New / existing |
|---|---|---|---|
| T-QLT-13a | unit | the headers: good ones accepted, every bad field refused naming it; `data_sources` ids distinct, pattern, licence | new |
| T-QLT-13b | contract | masked round trip: every array and the header equal after a save and a load; SHA-256 of the written file; the archive holds exactly the documented arrays | new |
| T-QLT-13c | contract | filtered round trip on a constant clock (the identity), on a clock with dropped frames and a pause (resampled), on SYN-08 (swap flags): equal; `on_source()` equals `QualityResult.filtered_on_source()` bit for bit | new |
| T-QLT-13d | contract | a damaged or inconsistent masked file is refused naming the field (about 30 cases: array missing, extra, wrong dtype or shape, NaN where `ok`, a value where not `ok`, untracked row with another reason, counts that do not match `reason`, wrong `frame_invalid`, swap outside the pairs, time not increasing, version, skeleton, header counts) | new |
| T-QLT-13e | contract | the same for the filtered file (the contract of the gap layer, `filtered` on a NaN, wrong `grid_in_segment`, a map back that disagrees with the clocks, an identity file with a moved grid, outside rows with a weight, header counts, version) | new |
| T-QLT-13f | contract | not an archive of ours, a pickled array, a missing file, a file of the other kind (masked read as filtered): refused | new |
| T-QLT-13g | contract | atomic: a failing replace keeps the old file and leaves no temporary file; a missing folder is refused and not created; a second save replaces the first completely | new |
| T-QLT-13h | contract | the writer refuses what the reader would refuse (float64 layer, bad `frame_index`, no rows, not a `QualityResult`); the header has no path or file name; a `dataset`-marked run on real UMONS files | new |
| T-QLT-01, T-QLT-07 (+ `07h` formula), T-QLT-11 | unit | the three refactors change nothing | existing |

**Acceptance criteria.**

- [x] AC1 Both layers are written atomically and read back to the same arrays and header (T-QLT-13b, c) for an identity clock (F1), a clock with dropped
  frames and a pause, a jittered clock and a clock whose first row is off the lattice; the SHA-256 is that of the file on disk (13b).
- [x] AC2 `PoseFiltered.on_source()` equals `QualityResult.filtered_on_source()` bit for bit in the four scenarios and on two real Kinect files, and
  `on_source(values)` equals `QualityResult.grid.to_source(values)`; NaN where the source had none or the row is outside the grid (13c and the `dataset` test).
- [x] AC3 A file that disagrees with itself is refused naming the field: 50 masked array cases, 10 masked header cases, 66 filtered array cases and 12 filtered
  header cases (more than the 30 and 25 asked), plus 53 header tests; the messages were printed and read: each case fails for its own reason.
- [x] AC4 No value is made up: NaN and reasons survive, flags are stored as flags, a float64 layer is refused, a layer without rows is not saved, no cast is silent
  (13h, 13b).
- [x] AC5 No path, file name or person name in a header (13h); `data_sources` validated (ids distinct, pattern, licence text) and carried (13a, 13h).
- [x] AC6 The three helpers left the existing tests green unchanged (T-QLT-01, T-QLT-07, T-QLT-11, T-QLT-11h); 33 mutants of the checks, the builders, `on_source`
  and `segment_grid_rows` were run: one survived the first run (a case that raised the header count with the cell, so the count check refused it) and is fixed
  and caught now; 33 of 33 caught.
- [x] AC7 Gate 10/10; W6 note, plan row (T-QLT-13), README, DEC-0053, CHANGELOG and TASK_STATUS updated; no open S1 or S2 bug from this task.

**Impact / rollback.** New modules and tests plus three one-function additions to P4 modules. Nothing reads the new files yet (P5, P7, P8 will).
Rollback: delete the two modules and the tests, revert the three helpers.

## 3. Plan re-read (before coding)

Plan re-read: 2026-11-17 — OK, with one change made first: build, check and write are separate (`pose_*_from_result`, `save_pose_*(path, layer)`),
see section 2. Checked against the code: `mask.py` (unchanged since 09:02, no change by the other agent), `coverage.py` and `resample.py` are
mine and unchanged since X.31; `MaskResult.n_essential_valid` is int64 (the writer range-checks it and stores int8); `check_layer` and `check_gap_layer`
give the contract of the two layers; `QualityResult.report.params` is the `QualityParamsRecord` as used and `grid.gridmap` has `back_left`,
`back_weight`, `before`, `beyond`, `snap_s`, `step_s`; `build_f1()` is float32 and holds every class of cell and a swap in rows 34 and 35. Next free
IDs: DEC-0053, BUG-0075 (re-read just now).

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
|---|---|---|
| 1 | 2026-11-17 | Plan re-read (section 3); one change made to the plan first: build, check and write are three steps (`pose_*_from_result`, `save_pose_*(path, layer)`). |
| 2 | 2026-11-17 | Tests first: `test_quality_layers_meta.py` (53), `test_quality_layers_io.py` (205), `golden/test_quality_layers_umons.py` (3, `dataset`). |
| 3 | 2026-11-17 | The three helpers (`mask.frame_invalid_mask`, `resample.values_on_rows`, `coverage.segment_grid_rows`); the existing tests of the stages stayed green. Then `schemas/quality_layers.py` and `quality/layers_io.py`. |
| 4 | 2026-11-17 | First full run green at once (202 contract tests): suspicious, so the 164 refusal messages were printed and read. Each fires for its own reason. Three checks had no case (the weight of a mixed row, `back_left + 1`, a `frame_invalid` cell in a valid row): cases added. Two things in the tests were wrong and were fixed: a forbidden-word list that matched `data_sources` and the licence text, and cases that set a flag to the value it already had (a flip is used). |
| 5 | 2026-11-17 | Real data: two Kinect files write, read and check in 0.25 s (11,790 rows: 1.54 and 1.71 MB). |
| 6 | 2026-11-17 | 33 mutants; **one missed in the first run** ("the check that `filtered` is only on cells with a value is skipped"): the case raised the count of the header too, so the count check refused it. The case now clears another cell (count unchanged) and the mutant is caught by the reader test and the writer test. |
| 7 | 2026-11-17 | Docs and tracking; gate 10/10; one docstring reworded after the gate (ruff, tests of the three files re-run). |

## 5. Verification

**Gate** (`powershell -NoProfile -ExecutionPolicy Bypass -File tools\check.ps1`, from `taiji_ai/`): **RESULT: PASS (10/10) in 267.0 s**; pytest 3999 passed, 1 skipped (255.9 s;
3738 before this task + 261 new); ruff, ruff-format, mypy (86 files), web-lint, web-typecheck, web-test (11), web-build, repo-hygiene (0 violations, 334 files).
After the gate: one docstring reworded, a README module list edited, `ruff check`, `ruff format --check` and the three new test files re-run, all pass.

**New tests (261):** T-QLT-13a 53 (headers), 13b to 13h 205 in `tests/contract/test_quality_layers_io.py`, and 3 `dataset` tests on real Kinect files.

**Real data** (UMONS Kinect D12, CC BY-NC-SA, `dev-test`; the numbers only): `P08T03C01` 11,790 rows give 12,196 grid rows; `pose_masked.npz` 1,536,184 bytes, `pose_filtered.npz`
1,710,569 bytes; save of both 0.21 s, load and check 0.04 s; one row outside the grid. `P02T02C09` (the 733 ms pause) 8,180 rows give 8,301 grid rows; 1,067,727 and 1,151,181
bytes; the pause is `no_frame`, never bridged. Both read back equal and `on_source()` equals `filtered_on_source()`.

**Mutants** (each caught by a test of the rule it breaks): frame rule, essential recount, swap subset, swap pairs, untracked rule,
`not_tracked` in a tracked row, mask reason codes, `ok` cell in a `frame_invalid` row, `frame_invalid` cell in a valid row, masked `n_rows`, mask contract, gap contract,
filtered reason codes, `filtered` on a NaN cell, `grid_in_segment`, `outside` recompute, `outside` weight, copy within `snap_s`, weight of a mixed row, `back_left + 1`, identity
weight, identity grid, `n_mixed_rows`, `n_filtered_cells`, filtered `n_grid_rows`, `on_source` without `source_usable`, `on_source` without `outside`, builder without `before`,
builder with the wrong swap mask, writers that skip the check (2), dtype check, `segment_grid_rows` that is every row. 33 of 33 caught (after the fix of one case).

## 6. Self-review

- Files reviewed: `quality/layers_io.py` (read in full after the formatter), `schemas/quality_layers.py`, the three helpers (diff against HEAD), the three test files, W6, DEC-0053,
  README row, the plan row.
- Checklist (AGENTS.md section 2 Step 4): correctness x · edge cases x (one row, no row, float64, NaN time, frame_index off by one or negative or float, a clock that is not
  resampled, a row before or after the grid, a copy at the edge of `snap_s`, an unusable source cell, a bridged cell, a swap, an untracked margin) · no fabricated data x (the writer
  refuses a cast, the reader invents nothing, `on_source` gives NaN where there is no value) · errors surfaced x (no `except` that passes; OSError becomes `QualityLayerError` with
  the cause) · tests cover criteria x · no personal data x (headers hold only `recording_id`; real-data test writes to `tmp_path` and stores no value) · docs updated x.
- Findings: (a) a missed mutant, fixed (step 6); (b) three checks with no case, cases added (step 4); (c) **open item for P7, not a bug:** `pose_raw/1` has no `data_sources`, so the
  root of the chain does not carry it; P7 must pass the sources of the recording to the two builders (DEC-0053 item 4); (d) nothing reads the files yet. A bug, if any is found
  later in the new code, goes to `BUGS.md` first.
- Code of the other agent: not touched (`chain.py`, `quality_io.py` docstring line only, `quality/__init__.py` docstring only, `schemas/quality.py` read only).

## 7. Bugs

None registered. Findings (a) and (b) were defects of the tests of this task and were fixed before the task closed. No pre-existing bug found.

## 8. Close-out

- [x] Acceptance criteria met (evidence above)
- [x] Checks pass (gate 10/10, 267.0 s)
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated (DEC-0053)
