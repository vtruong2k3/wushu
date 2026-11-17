# X.31 — The grid on a ms-rounded sensor clock: fitted step and phase, and a snap tolerance (amends DEC-0047)

| Field             | Value                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-17)                                                                                                         |
| Owner             | agent                                                                                                                     |
| Phase             | P4 (rework of P4.04; consequences for P4.07 and P4.08)                                                                    |
| Estimate          | 0.75 day                                                                                                                  |
| Depends on        | P4.04, P4.07, P4.08 (all DONE, 2026-11-17; none committed)                                                                |
| Plan confirmed by | Maintainer, 2026-11-17: asked the agent to read the X.31 proposal, analyse it and carry it out. No persisted schema changes |
| Started / Done    | 2026-11-17 / 2026-11-17                                                                                                   |

## 1. Analysis

**Goal.** On a real sensor clock (timestamps rounded to the millisecond, dropped frames, pauses) almost every grid row of the P4.04
stage is a flagged linear mix instead of a copy of a real frame (UMONS Kinect, 111 files: **96.5 % of the grid rows are `mixed`**,
77.8 % with an explicit `grid_hz` = 30; `Docs/reports/p4_umons_quality.md`, finding 2; question Q6 of `Docs/tasks/P4.08.md`). A mixed row is
correct and flagged, but it smooths the data for nothing and the report on a real clock says "mixed" where the clock only has a 0.33 ms
rounding. The task makes a row that is on the clock a copy, and it makes the default grid follow the clock of the clip.

**The proposal being carried out.** (a) step of the grid from the mean interval or a fitted line instead of the median interval; (b) a snap
tolerance of 1 ms: a grid time within it of a row is that row. Estimated from the report: about 68 % copies instead of 22 %.

**What the analysis found (timestamps of the 111 Kinect files only, scratch scripts; numbers are shares of the grid rows):**

| Grid | step (min / median / max, ms) | copies, tol 0 | copies, tol 1 ms |
|---|---|---|---|
| median interval, anchored at the first row (**now**) | 33.000 / 33.000 / 34.000 | 3.2 % | 6.2 % |
| plain mean interval `(t_last - t_0) / (n - 1)` | 33.320 / 34.008 / 45.663 | 0.3 % | 6.5 % |
| plain least-squares line through the rows | 33.332 / 33.979 / 47.413 | 0.0 % | 6.6 % |
| nominal 30 Hz (`grid_hz` = 30), anchored at the first row | 33.333 | 22.0 % | 68.4 % |
| **frame-count-corrected** least-squares step, anchored at the first row | 33.332 / 33.333 / 33.333 | 0.0 % | 70.0 % |
| **frame-count-corrected** step **and fitted phase** | 33.332 / 33.333 / 33.333 | 0.0 % | **90.8 %** |

Findings that change the proposal:

1. **The mean and the plain line do not work on a clock with dropped frames.** Every dropped frame adds a whole step to the interval, so the
   mean is 34 ms (up to 46 ms) instead of 33.33 ms and the grid drifts against the rows (6.5 % copies). The step has to count the *frames*
   that an interval spans: `m = round(interval / step)`, the step is the least-squares slope of the row times against the frame index.
   It then comes out at 33.332 to 33.333 ms in every file (true value 33.3333 ms).
2. **The tolerance is what makes copies; the step alone makes none** (0 to 3 % copies at tol 0 whatever the step), and the step alone
   without the tolerance would still leave rows 0.3 ms off the grid mixed. Both are needed.
3. **The phase of the grid matters as much as the step.** The grid is anchored at the first row, but in many files the first row is more
   than 1 ms off the lattice of the clock (start-up jitter): anchored there only 70 % of the rows are within 1 ms of a grid time; anchored at
   the least-squares phase 90.8 % are (93.7 % of the rows are within 1 ms of the fitted lattice, 80.9 % within 0.5 ms). This is the
   intercept of the "fitted line" of the proposal.
4. **A pause or a burst must not enter the fit.** A pause that is not a whole number of frames shifts the phase of the rows after it; a
   burst of rows finer than the nominal step (the burst case of `test_quality_chain.py`) is not on the lattice at all. A global fit would be
   dragged by both, so the fit is made **inside the runs of regular intervals** (a common step, one phase per run) and the phase of the grid is
   the one of the longest run.

**In scope.**

- `quality/resample.py`: (1) the lattice fit (step and phase) for the default grid; (2) the snap tolerance in both directions (grid time to
  row, row to grid time), taken from `uniform_tol_s`; (3) the grid window `[t_0 - snap, t_last + snap]`; (4) a new row flag `before` in
  `GridMap` (a row before the first grid time has no left neighbour), the twin of `beyond`; (5) the effective tolerance `snap_s` in `GridMap`.
- Tests: T-QLT-07 rules updated, new groups for the snap and the fit, the differential oracle rewritten for the new rules.
- The numbers that the old rule produced: re-run the UMONS report (`Docs/reports/p4_umons_quality.md`) and the two docs that quote it.
- DEC-0052 (amends DEC-0047 rules 2, 3 and 8), W6 note, plan row, README, CHANGELOG, TASK_STATUS.

**Out of scope.** The identity decision (rule 1 stays: a timeline within `uniform_tol_s` of a straight line is the identity); the pause limit
`max_step_s`; interpolation of values (still linear, in float64); re-anchoring the grid after a pause (the grid stays one regular lattice;
rows after a pause that changed the phase are mixed, flagged, as before); the stage order; `quality.json` (schema `quality/1` unchanged, see
below); the Hampel stage on Kinect; X.29.

**Inputs / outputs / interfaces.** Unchanged signatures: `plan_grid(t_sec, params) -> GridMap`, `resample_layer(...) -> GridLayer`,
`resample_gaps`. Times in seconds (real PTS), positions in pixels (y down). `GridMap` gets two fields, `before` `(T,) bool` and `snap_s` `float`
(in memory only); `GridMap.step_s` is now the fitted step for a non-uniform timeline. **No new parameter and no schema change:** the snap
tolerance is `ResampleParams.uniform_tol_s`: both mean "how far a row may be off a regular clock and still count as on it" (the same 1 ms, the
rounding of a time base of 1 ms is 0.5 ms), so `ResampleParamsRecord` and `quality/1` stay as they are; a clip with a 0.01 s time base passes a
larger `uniform_tol_s` and gets both effects. `uniform_tol_s = 0` keeps today's exact behaviour (only 1e-9 s).

**Existing code and docs read.** `quality/resample.py`, `tests/unit/test_quality_resample.py`, `tests/contract/test_quality_resample_chain.py`,
`bench/umons.py`, `quality/chain.py`, `quality/coverage.py`, `quality/filters.py` (uses `step_s` only), `Docs/reports/p4_umons_quality.md`,
`Docs/tasks/P4.04.md`, `Docs/tasks/P4.08.md`, DEC-0047, DEC-0050, DEC-0051, W6 of `Docs/TECH_WORKFLOW_V1.md`. Third-party code: none used.

**Constraints that apply (AGENTS.md §5).** 5.1 no fabricated observations: a snapped cell is a real row, copied whole; the timing offset is at
most the tolerance and is documented, and an interpolated cell stays flagged. 5.2 real timestamps: the grid is built from PTS only, no frame
rate is assumed; the fit uses the row times and the frame counts that they imply. 5.5 the parameters are data-validity ones. 5.8 no persisted
artifact changes. 9.4.4/9.4.7 UMONS (CC BY-NC-SA, `dev-test`): only counts and shares leave the dataset; the tests that read it keep the
`dataset` marker.

**Unknowns, risks, questions.**

- *Timing error of a snapped cell.* A cell at grid time `g` holds the value of a row up to `snap` away. To measure (step 4 of the plan): the
  distance between the copied value and the linear mix at `g`, in pixels and as a share of the torso, on the Kinect files. If it is
  not small against the round-trip error of a mixed cell (p95 2.2 px, 0.94 % of the torso on D20) the tolerance would have to shrink.
- *The first row.* With a fitted phase the first row may lie before the first grid time (it is off the lattice by more than the tolerance); on the way
  back it has no value (`before`, like `beyond` at the end). Cost: at most one row per end of a clip; the grid layer, which P5 reads, loses nothing.
- *Fit on jitter.* On a jittered clock (SYN-07, 30 %) there is no lattice; the fit gives the mean step and some phase; no row is a copy
  except by chance, as today.
- *Open for the maintainer (defaults applied):* one tolerance for both roles (no new parameter, no schema change); the phase of the longest run.

## 2. Plan

**Design.** In `plan_grid`, after the identity check:

1. *Fit* (`grid_hz is None` only): `d = diff(t)`; `nominal = median(d)`; an interval is **regular** if `nominal / 2 <= d <= max_step_s`
   (+1e-9); a **run** is a maximal sequence of rows joined by regular intervals (a pause or a burst row ends a run). Frames per interval
   `m = max(1, round(d / step))`, the frame index `k` of a row restarts at 0 in each run. Step = `sum_runs sum (k - kbar)(t - tbar) /
   sum_runs sum (k - kbar)^2` (a common slope, one intercept per run); two passes (first with `nominal`, then with the step found). Phase `a` =
   `tbar - step * kbar` of the run with most rows (the first on a tie). No fit (no run of two rows, or a step that is not finite and above 0):
   `step = median(d)`, `a = t_0` (rule 2 of DEC-0047). An explicit `grid_hz`: `step = 1 / grid_hz`, `a = t_0`.
2. *Snap* `snap = min(uniform_tol_s, step / 4) + 1e-9`; `uniform_tol_s = 0` is the old exact rule.
3. *Grid* `t_grid[j] = a + j * step` for the integers `j0 <= j <= j1`, `j0 = ceil((t_0 - snap - a) / step)`, `j1 = floor((t_last + snap - a) /
   step)`; if the window holds no grid time use `a = t_0` (it holds `j = 0`). For `a = t_0` this is the old grid up to the snap at the end.
4. *Forward map* (grid time to row): the **nearest** row (the earlier on a tie); within `snap` it is a **copy** (`weight` 0, `left` = that row,
   value, reason and flag bit for bit, `mixed` false); else `w = (g - t_l) / (t_{l+1} - t_l)` between the rows around it (always two rows:
   the window ends are within `snap` of the end rows); `stall` as before (`w > 0` and interval over `max_step_s`).
5. *Way back* (row to grid time): the **nearest** grid time within `snap` is a copy (`back_weight` 0); else the mix of the two grid times around
   the row with weight `(t - g_b) / step`; a row before the first grid time is `before`, after the last `beyond`, both NaN.
   `GridMap.to_source` and `GridLayer.to_source` set both to NaN; the rest of their rules stands.
6. Docstring of the module rewritten (rules 2, 3, 8; the limits).

**Files to create / modify.**

| File | Change |
|---|---|
| `taiji_ai/src/taiji_ai/quality/resample.py` | the lattice fit, the snap, the window, `before`, `snap_s`; docstrings |
| `taiji_ai/tests/unit/test_quality_resample.py` | rules updated; groups T-QLT-07n (snap), 07o (fit), 07p (ends); oracle rewritten |
| `taiji_ai/tests/contract/test_quality_resample_chain.py`, `test_quality_chain.py`, `test_quality_coverage.py`, `test_umons_adapter.py` | only expectations that encode the old rule (each reviewed one by one, see the log) |
| `Docs/reports/p4_umons_quality.md` | regenerated (default chain and `grid_hz` = 30), findings rewritten |
| `Docs/tasks/P4.04.md`, `P4.08.md` | one-line notes that X.31 amended the rule / the numbers |
| `Docs/tracking/*`, `Docs/TECH_WORKFLOW_V1.md` (W6), `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md` | DEC-0052 and the amended text, status, changelog |

**Implementation steps.**

1. Re-read this file against the code (section 3).
2. Write the new tests first (07n, 07o, 07p, the oracle) and see them fail on the old code.
3. Implement the fit and the snap in `plan_grid`, then `before` in the map and `to_source`, then `resample_layer` for the nearest copy.
4. Run the resample tests; review every old test that fails: change it only where it states the old rule (median step, grid starts at the first row,
   copies only at exact times), never to hide a defect.
5. Measure on UMONS: the shares of copies and mixes, the timing error of the snapped cells, the loss of rows at the ends; re-run
   `tools/umons_adapter.py` for the report; M-QLT-04 equivalent on D20 is unchanged (identity in 22 of 22 chunks) and is checked, not re-run.
6. Mutation check: three mutants (no snap; median step; anchor at the first row) must each fail a test.
7. Docs, tracking, gate (`tools\check.ps1`, full), self-review, close.

**Test plan.**

| Test ID | Type | What it checks | New / existing |
|---|---|---|---|
| T-QLT-07a | unit | uniform timeline is the identity (unchanged) | existing |
| T-QLT-07b | unit | regular grid: step from the fit, grid inside `[t_0 - snap, t_last + snap]`, copies inside the tolerance | updated |
| T-QLT-07n | unit | snap: a row within `uniform_tol_s` of a grid time is a copy, one just outside is a mix; tolerance 0 is the old rule; the cap at `step / 4`; nearest row wins, the earlier on a tie; both directions | new |
| T-QLT-07o | unit | fit: a 30 fps clock in whole milliseconds with dropped frames and a pause gives step 1/30 within 1e-6 and more than 95 % copies (the median and the mean would not); a pause that shifts the phase does not move the step; a burst is outside the fit; the longest run sets the phase; no-fit fallback; jitter stays regular | new |
| T-QLT-07p | unit | ends: a first row off the lattice is `before` and NaN on the way back, the grid still starts within `snap` of it when it is on the lattice; a grid time past the last row within `snap` is a copy | new |
| T-QLT-07 diff | unit | the differential oracle (loops) equals the module on 200 random clocks, now with dropped frames, coarse clocks and bursts | updated |
| T-QLT-07k..m | contract | chain and fixtures: unchanged claims (nothing is filled, flags, bounds) | existing, adapted where they say "starts at the first row" |
| T-QLT-11, 12, M-QLT-08 | contract / golden | chain, report, six real Kinect files: sanity bounds only | existing |

**Acceptance criteria.**

- [x] AC1 On the 111 Kinect files the default chain gives **90.98 % copies** (0.02 % at the exact time, 90.98 % snapped; the plan asked for 85 %); the fitted step
  is 33.3308 to 33.3335 ms (the plan asked for within 0.01 ms of 33.333 ms: the worst file is 0.0025 ms off); `mixed` rows fall from 96.51 % to 8.78 % (the plan asked for under 15 %).
- [x] AC2 No value is invented: every cell is a copy of a row, a flagged linear mix of two usable cells, or NaN; `check_gap_layer` holds on every
  result of the 300 differential cases and of the existing tests (all pass).
- [x] AC3 `uniform_tol_s = 0` copies only within 1e-9 s (T-QLT-07n `exact`: grid time 0.8 ms from a row is a mix); the identity decision is unchanged
  (T-QLT-07a, 11 tests, pass without change).
- [x] AC4 The timing error of the snapped cells is measured: p50 0.013 mm, p95 0.248 mm, p99 0.755 mm (max 15.5 mm, a Kinect jump); 0.0027 % /
  **0.054 %** / 0.164 % of the torso at p50 / p95 / p99, against 0.94 % for a round trip through the grid (D20, M-QLT-04). The tolerance stays 1 ms.
- [x] AC5 Nine mutants are caught (section 5); the differential oracle passes on 300 cases and a meta-test shows that the cases reach every
  branch (identity, fit, fallback, snap, mix, stall, `before`, `beyond`).
- [x] AC6 No persisted schema changed (`ResampleParamsRecord`, `quality/1` untouched); the UMONS report is regenerated; DEC-0052, W6, README, plan row,
  CHANGELOG, TASK_STATUS updated; gate 10/10.

**Impact / rollback.** One module and its tests. Constant-frame-rate clips (every D20 clip) are the identity and unchanged. On a non-uniform clip
the grid rows, `step_s` (so the Butterworth sampling frequency) and `mixed_rows` of `quality.json` change; a clip that was resampled has at most
one row less on the way back at each end (`before`, `beyond`). Rollback: revert `resample.py` and the tests; nothing else depends on the new
fields.

## 3. Plan re-read (before coding)

Plan re-read: 2026-11-17 — OK. `quality/resample.py` and `tests/unit/test_quality_resample.py` have no uncommitted change (the other
agent did not touch them since commit `aec82b9`); `GridMap` is built only in `plan_grid` and `_identity_map`, `beyond` is read only in
`resample.py` and its tests, and `ResampleParamsRecord` (`schemas/quality.py`) records only `grid_hz`, `max_step_s`, `uniform_tol_s`, so the
plan needs no schema change. The next free IDs are DEC-0052 and BUG-0075 (re-read just now).

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
|---|---|---|
| 1 | 2026-11-17 | Plan re-read (section 3). |
| 2 | 2026-11-17 | New tests first: T-QLT-07n (5 tests), 07o (7), 07p (5 tests, 8 cases, the window-edge one added in step 4b): they failed on the old code (no `snap_s`, no `before`, copies only at exact times). |
| 3 | 2026-11-17 | `resample.py`: `_fit_lattice`, `_window`, the snap in both directions, `before`, `snap_s`; docstring rewritten. The new tests pass. |
| 4 | 2026-11-17 | Old tests reviewed one by one: `assert_grid` (the grid starts at the first row), the median step in three tests, `beyond` without `before` in three tests, the "exact on linear motion" claims (now off by at most the speed x the tolerance: the price of a snapped cell, encoded as a bound), two tests on the end of the grid that now ask for `grid_hz` so that float rounding stays their point. No test was relaxed to hide a defect. The oracle was rewritten for the new rules (nearest row, fit with loops, `before`) and run on 300 cases with new kinds of clock (`msdrop`, `burst`, `slow`). |
| 4a | 2026-11-17 | **Deviation found by the oracle:** the reason of a mixed cell with two unusable parents flipped at the exact middle of a dropped frame (`w` = 0.49999999999999734 in the module, 0.5000000000000004 in the oracle: the fitted phase is summed in another order). The tie now has 1e-9 s of tolerance in both (DEC-0052 item 5). |
| 4b | 2026-11-17 | **Defect found in self-review of my own code:** at the edge of the window `t_0 - snap` a grid time could be 1 ulp farther than `snap` from the end row and become a mix with a weight below 0 (extrapolation by 1 ms). A grid time at or past an end row is now a copy; the test sweeps the binades where it happens (it fails without the fix). Not a registered bug: it never left this task. |
| 5 | 2026-11-17 | Measured on the 111 files (section 5); `tools/umons_adapter.py run` re-run for the report (default and `grid_hz` = 30). **Finding not in the plan:** the report's "grid rows" is the sum of the segment rows and is 105 below `timeline.grid_rows` (grid rows that copy an end row from up to 1 ms outside `[t_0, t_last]` are outside the segment); documented in `coverage.py`, the report and DEC-0052, no change to the coverage (rows are counted by their own time). |
| 6 | 2026-11-17 | Eight mutants, all caught (section 5); the ninth, for 4b, was run when 4b was written. |
| 7 | 2026-11-17 | Docs and tracking; gate 10/10; two local variables renamed after the gate (`last_row`, `last_grid`), ruff, mypy and the affected tests re-run. |

## 5. Verification

**Gate** (`powershell -NoProfile -ExecutionPolicy Bypass -File tools\check.ps1`, from `taiji_ai/`): **RESULT: PASS (10/10) in 263.6 s**; pytest 3738 passed,
1 skipped (253.2 s); ruff, ruff-format, mypy (84 files), web-lint, web-typecheck, web-test (11), web-build, repo-hygiene (0 violations, 328 files). The
tree held the other agent's work in progress; nothing of it failed. After the gate: two renames, `ruff check`, `ruff format --check`, `mypy` and
`test_quality_resample.py`, `test_quality_resample_chain.py`, `test_quality_chain.py`, `test_quality_coverage.py`, `test_umons_adapter.py` pass.

**Measure on the 111 UMONS Kinect files** (CC BY-NC-SA, `dev-test`; counts and shares only; scratch scripts in the session scratchpad, not in the repository):

| Grid | step ms (min / median / max) | exact copies | snapped copies | mixed | stall |
|---|---|---|---|---|---|
| before X.31: median step from the first row | 33.000 / 33.000 / 34.000 | 3.2 % | 0 % | 96.5 % | 0.25 % |
| plain mean interval (analysis) | 33.320 / 34.008 / 45.663 | 0.3 % | 6.2 % | 93.3 % | 0.22 % |
| **after X.31, default** (725,964 grid rows) | 33.3308 / 33.3333 / 33.3335 | 0.02 % | **90.98 %** | **8.78 %** | 0.22 % |
| after X.31, `grid_hz` = 30 from the first row | 33.3333 | 22.00 % | 48.22 % | 29.55 % | 0.22 % |

Rows without a value on the way back: 26 first rows (26 files) and 11 last rows (11 files) of 703,115 (0.005 %). |offset| of a snapped cell: p50 0.33 ms,
p95 0.80 ms, max 1.00 ms. Timing error of a snapped cell (11.2 million joint cells; value against the straight line between its two neighbouring rows):
0.013 / 0.248 / 0.755 mm at p50 / p95 / p99. Chain over the 111 files: 0 errors, 30.5 s. Files that keep more than 20 % mixed rows: 11 (54 % of all
mixed rows); in them the clock wanders up to 70 ms around the best straight lattice (runs of 33 ms steps, then of 34 ms steps).

**Mutants** (`tests/unit/test_quality_resample.py`, first failing test shown): no snap (T-QLT-07c); median step and first row, no fit (07b jittered);
fitted step anchored at the first row (07o pause); one frame per interval, drops not counted (07b dropped frame); bursts and pauses inside the fit
(07f low rate); always the earlier row of the pair (07b dropped frame); a row before the grid keeps a value (07h hole); the phase of the first run
instead of the longest (07o pause); and, separately, no clamp at the end rows (07p edge of the window). 9 of 9 caught; the file was restored and compared with its backup each time.

## 6. Self-review

- Files reviewed: `quality/resample.py` (full diff against HEAD re-read), `quality/coverage.py` (docstring), `tests/unit/test_quality_resample.py` (new groups,
  oracle), `Docs/reports/p4_umons_quality.md` (every number of the changed bullets against `report_tables.md` and the measure), DEC-0052, W6, README, plan row.
- Checklist (AGENTS.md section 2 Step 4): correctness x · edge cases x (empty, one and two rows, NaN times, VFR, a first or last row off the lattice, a window
  edge at 1 ulp, rows closer than the tolerance, a clip slower than the pause limit, float32 and float64) · no fabricated data x (a snapped cell is a real
  row whole, up to 1 ms off in time, bounded, measured and flagged by the grid map; no value outside the grid on the way back) · errors surfaced x (the
  parameters are validated as before; the fit returns None instead of guessing and the fallback is the documented DEC-0047 rule) · tests cover criteria x ·
  no personal data x (UMONS counts and shares only, performer ids as in the dataset) · docs updated x.
- Findings: (a) the tie of the reason at the middle of a dropped frame and (b) the window edge at 1 ulp, both fixed in this task (steps 4a, 4b); (c) the report's
  "grid rows" and `timeline.grid_rows` differ by the grid rows outside the segment: documented, not a defect (the coverage counts by time); (d) **open observation
  for the maintainer, not a bug:** 11 Kinect files have a wandering clock that no regular grid follows; the mixes there are correct and flagged. A grid that
  follows a wandering phase would break the regular clock that the filter needs; nothing is planned. (e) The first analysis proposal (mean interval or plain line)
  was wrong on clocks with dropped frames; the plan says so and the measure shows it.
- Code written by the other agent: none touched (`chain.py`, `quality_io.py`, the schema and `bench/umons.py` read only; `coverage.py` got a docstring sentence).

## 7. Bugs

None registered. Defects found in the code of this task during the work (4a, 4b) were fixed before the task closed. No pre-existing bug found.

## 8. Close-out

- [x] Acceptance criteria met (evidence above)
- [x] Checks pass (gate 10/10, 263.6 s)
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated (DEC-0052; the `uniform_tol_s` doc, the module docstring and the status row)
