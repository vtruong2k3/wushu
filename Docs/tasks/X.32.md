# X.32 — Fix BUG-0081: `align` leaves out the frames that have no evidence, keeps the index map and reports them

| Field             | Value                                                                                         |
| ----------------- | --------------------------------------------------------------------------------------------- |
| Status            | IN_PROGRESS (2026-11-18)                                                                      |
| Owner             | A (agent), then the coordinator for the gate and the tracking files                           |
| Phase             | P6 (W8), ad-hoc: `X.32` (AGENTS.md section 2.2)                                               |
| Estimate          | About 0.75 day (align and its tests 0.25, the consumers 0.25, the UMONS rerun and report 0.25) |
| Depends on        | P6.02, P6.03a, P6.03b, P6.04, P6.07 (all done in code, 2026-11-18)                            |
| Plan confirmed by | Maintainer, 2026-11-18: chose Option A of BUG-0081 (leave the frames without evidence out, keep the index map, report them). The detailed design below follows that choice; it changes the contract of `P6_overview.md` section 3.4 |
| Started / Done    | 2026-11-18 / —                                                                                |

## 1. Analysis

### 1.1 Goal

A pair of segments must not be refused because tracking dropped one frame. Today `cost_matrix` writes `+inf` in every
cell of a row whose frame has fewer than `min_visible` valid units, `dtw` never steps onto `+inf` and cannot skip a
row, so one such frame in either segment gives `no_path` for any band and step (BUG-0081; on UMONS 23 of 40 pairs of
recordings and 438 of 3,412 pairs of segments under `symmetric1`). With this task `align` **leaves those frames out
before the path**, keeps the map back to the original rows, and **reports** them, so no number is invented and the clock
stays real.

### 1.2 Facts read (2026-11-18)

- `compare/align.py` (P6.03b): `align` = `dtw(cost_matrix(...))`; `Alignment(reference, query, cost, result, settings)`;
  `matched_query_times()` (mean query time per reference row from the path cells; NaN where no cell lies on the row, never
  0); `as_comparison()`; settings are the fingerprint of a distance (8 short-code names), two distances are comparable
  only when the settings are equal (P6.06).
- `compare/dtw.py`: `DtwResult(path, distance, status, accumulated, normalised, params)`, a plain frozen dataclass;
  `params` is `{band, step, n, m}` (the matrix size); `D` is the plain mean of the cost over the path cells; the band is
  defined on the normalised positions `i/(n-1)`, `k/(m-1)` of the matrix it is given; `no_path` has an empty path.
- `compare/cost.py`: `CostMatrix.values` `(n, m)` with `+inf` where fewer than `min_visible` units are valid in both
  frames, `weights` as used (0 = left out), `n_common`.
- Consumers of the path: `compare/tempo_ratio.py` reads `alignment.result.path` (original row indices) and
  `matched_query_times()`; a reference row with NaN matched time is already left out of the local fit (D3 of P6.04) and a
  row with no path cell already has the deviation reason `no_cell`; `bench/umons_compare.py` reads `matched_query_times()`
  and its `transfer_times` refuses a matched clock that is not finite.
- The report of P6.07 (`Docs/reports/p6_umons_check.md`) shows the measured effect and is the evidence for BUG-0081.

### 1.3 Scope

**In:** `align` and `Alignment` (the rule, the index map, the report of the dropped frames); the tests of `align`; the
tests (and, if needed, the docstrings) of `tempo_ratio` for a reference row that was dropped; `bench/umons_compare.py`
(`transfer_times` over the observed rows only and a count of the parts whose boundary lies in a dropped stretch); the rerun
of the P6.07 tool with the same settings and the update of its report (the first run stays in the report as the "before");
docs. **Out:** any change of `cost.py`, `dtw.py`, `features.py`, `guards.py`; Options B and C of the bug; a reason code
for the other causes of `no_path` (the length ratio, the band): not asked; the product pipeline (P7).

### 1.4 Design (the defaults, Q1 to Q7 below, are the plan)

- **The rule.** A frame is **dropped** when it has fewer than `min_visible` valid units among the units whose weight is
  above 0 (`cost.weights`), counted in its own row of `valid`: it has no evidence of its own. A frame that has
  `min_visible` valid units of its own but fewer in common with every frame of the other segment is **not** dropped (that
  is a real incompatibility, `no_path` stays). Applies to the reference and to the query alike.
- **The path.** `cost_matrix` is built on the whole segments as today (`Alignment.cost` keeps the full `(n, m)` shape; the
  rows and columns of dropped frames are `+inf`, which is true). `dtw` is run on `cost.values[np.ix_(kept_query,
  kept_reference)]` (a new array). The path of the result is mapped back to **original row indices**
  (`kept_query[path[:, 0]]`, `kept_reference[path[:, 1]]`), so `alignment.result.path` indexes `alignment.cost` and the
  features as before. The result is `dataclasses.replace(result, path=<mapped, read-only>, params={band, step, n, m with
  the original sizes})`. **When nothing is dropped the result is the unchanged result of `dtw`**, so `align` is still
  exactly `dtw(cost_matrix(...))` in that case.
- **The path runs from the first kept row to the last kept row** of each segment (dropped frames at an end are outside it).
- **`D`** is `DtwResult.distance` as before: the plain mean of the cost over the path cells; a dropped frame has no cell
  on the path, so `D` of a segment with a dropped frame equals `D` of the same segment with that frame cut out.
- **The band** is the band of `dtw` on the **kept** grid (positions are the ranks among the kept rows): written in the
  docstring, tested on a hand-made case.
- **The report.** `Alignment` gets `dropped_query` and `dropped_reference`: read-only int64 arrays of original row
  indices, ascending, **default empty** (an `Alignment` built by hand as the tests of P6.04 do keeps working), and the
  properties `kept_query`, `kept_reference` (the complement) and the methods `dropped_query_times()` and
  `dropped_reference_times()` (real seconds, from the clocks). Counts are not settings: they belong to the pair.
- **`settings`** gets a ninth short-code name, `rows_without_evidence` = `"dropped"`, the fingerprint of the rule, so a
  distance made under another rule (none exists on disk) could not be compared with this one by P6.06. The names of the
  counts are never in `settings` (two pairs with different drops must be comparable).
- **All frames of a segment dropped** (nothing kept on one side): `status="no_path"` with an empty path and `D` `None`;
  the dropped arrays say why (every frame). The band and the step are still validated (use `dtw` on a `1 x 1` infinite
  cost for the result and its params, then replace `n`, `m`).
- **`matched_query_times()`** is unchanged in code: a dropped reference row has no path cell, so it is NaN (never 0, never
  interpolated), and the comment that says every reference row has a cell is corrected.
- **`tempo_ratio`:** no code change expected (NaN matched rows are left out of the fit; a dropped reference row has the
  deviation reason `no_cell` and no value); add tests with a dropped reference row and a dropped query row and fix the
  docstring statements that say the path runs from corner to corner. The ratio of a *kept* row near a dropped stretch is
  fitted over its observed neighbours only.
- **`bench/umons_compare.py`:** `transfer_times(times, ref_t, matched)` accepts NaN in `matched` (a dropped reference row):
  it interpolates over the **observed** rows only; a time before the first or after the last observed row is NaN (counted
  in `parts_outside` as before); `PairBoundary` gets `parts_in_gap` (parts with a boundary that lies between two observed
  reference rows that are not neighbours on the grid: the value there is an interpolation across a stretch without
  evidence, and is counted and shown, never hidden) and the tables show it. Nothing else of the tool changes; the settings
  are still its arguments.

### 1.5 Questions for the maintainer

| #  | Question | Default if no answer |
| -- | -------- | -------------------- |
| Q1 | What counts as no evidence | **Fewer than `min_visible` valid units of the frame's own, among the units with weight above 0** (not the common count with the other segment) |
| Q2 | Where is the band measured | **On the kept grid** (ranks among the kept rows), written down |
| Q3 | `Alignment.cost` | **Kept whole** `(n, m)`; the dropped rows and columns are `+inf` |
| Q4 | A boundary inside a dropped stretch (UMONS check) | **Interpolated across the stretch, counted as `parts_in_gap` and shown** next to the results |
| Q5 | A new setting name | **`rows_without_evidence = "dropped"`** in `settings`; the counts stay out of the settings |
| Q6 | The first UMONS run | **Kept in the report as the "before"**; the rerun is added as the "after"; neither replaces the other |
| Q7 | Other causes of `no_path` (length ratio, band) | **Unchanged** (no reason code in this task) |

## 2. Plan

### 2.1 Files

| File | Change |
| ---- | ------ |
| `taiji_ai/src/taiji_ai/compare/align.py` | the rule, the sub-matrix, the mapped path, `dropped_*`, `kept_*`, `dropped_*_times()`, the ninth setting, docstrings |
| `taiji_ai/tests/unit/test_compare_align.py` | updated (nine setting names) and new tests T-CMP-03m to 03s |
| `taiji_ai/tests/golden/test_compare_align_syn.py` | a SYN-10 case with frames of the query made invalid |
| `taiji_ai/tests/unit/test_compare_tempo_ratio.py` | tests with a dropped reference row and a dropped query row (T-CMP-06i, 06j) |
| `taiji_ai/src/taiji_ai/compare/tempo_ratio.py` | docstring only, unless a test finds a defect |
| `taiji_ai/src/taiji_ai/bench/umons_compare.py` | `transfer_times` over observed rows, `parts_in_gap`, tables and CSV |
| `taiji_ai/tests/unit/test_umons_compare.py`, `tests/contract/test_umons_compare_tool.py` | updated and new tests (T-CMP-09f, 09g) |
| `Docs/reports/p6_umons_check.md` | the rerun added as the "after" (tables from the tool), the "before" kept; the prose says what changed |
| `Docs/tasks/P6_overview.md` | section 3.4: "as built" note for the rule, the report and the ninth setting |
| docs | drafts in section 9 for the coordinator (W8, README rows, DEC, CHANGELOG, plan, BUG-0081 closing text) |

### 2.2 Steps

1. Re-read this plan against the current code (§3).
2. Tests first for `align`: the BUG-0081 reproduction (30 rows, one query row with no valid unit, `min_visible=2`,
   `band=1.0`: a path and the dropped row), `D` equal to the segment with the frame cut out (both a query row and a
   reference row, a block, the two ends), mapping of the path to original indices, `matched_query_times()` NaN on a dropped
   reference row and equal to the real time elsewhere, nothing dropped gives the exact `dtw(cost_matrix(...))`, all rows
   of one side dropped gives `no_path`, a frame with enough own units but nothing in common is not dropped, the weight-0
   units do not count as evidence, the settings and the dropped arrays (read-only, ascending, new arrays).
3. Implement `align`.
4. Tests and docstrings of `tempo_ratio` with dropped rows.
5. `umons_compare`: tests first for `transfer_times` with NaN rows and `parts_in_gap`; implement; update the tool tables.
6. Run the tool again with the settings of the first run (classes with `symmetricP1` and with `symmetric1`, boundaries at band
   0.1 and 0.2, seed 1); measure the share of pairs with a path before and after; update the report. Nothing is tuned.
7. Mutation check of the new code of `align.py` and of the changed code of `umons_compare.py` (`-B`, BUG-0078 rules).
8. Drafts, self-review, close (the gate is the coordinator's).

### 2.3 Test plan

| Test ID | Type | What it checks |
| ------- | ---- | -------------- |
| T-CMP-03m | unit | the BUG-0081 reproduction gives a path and reports the dropped row with its real time |
| T-CMP-03n | unit | `D` of a segment with dropped frames equals `D` of the segment with them cut out (query, reference, block, ends); the path is the mapped one |
| T-CMP-03o | unit | nothing dropped: `align` equals `dtw(cost_matrix(...))` field by field; the arrays are read-only and new |
| T-CMP-03p | unit | all frames of one side dropped, or nothing left to align: `no_path`, `D` `None`, the dropped arrays say why; a bad band or step is still refused |
| T-CMP-03q | unit | the rule: own units count, weight 0 does not, a frame with enough own units and nothing in common is kept (and may give `no_path`) |
| T-CMP-03r | unit | `matched_query_times()` is NaN on a dropped reference row and the real mean elsewhere; the settings have the ninth name and no counts |
| T-CMP-03s | golden | SYN-10 with a block of query frames made invalid: a path, `D` close to the intact pair, the block reported |
| T-CMP-06i, 06j | unit | local tempo and deviation with a dropped reference row and a dropped query row (NaN not filled; `no_cell`) |
| T-CMP-09f | unit | `transfer_times` over observed rows only; outside the observed span is NaN; refusals as before |
| T-CMP-09g | unit | `parts_in_gap` counted on a hand-made alignment with a dropped stretch; the tables and the CSV show it |
| M-CMP-02 | manual | the report: before and after, per experiment |

### 2.4 Acceptance criteria

- [ ] AC1 The BUG-0081 reproduction gives a path; the dropped rows are reported with their real times; no value is invented.
- [ ] AC2 `D` with dropped frames equals `D` of the segment with them cut out; with nothing dropped `align` is exactly `dtw(cost_matrix(...))`.
- [ ] AC3 All the earlier tests of the compare modules and of P6.07 pass (the nine setting names are the only change of an assertion).
- [ ] AC4 The UMONS rerun uses the same settings; the share of pairs with a path before and after, and the boundary results with `parts_in_gap`, are reported; nothing is tuned.
- [ ] AC5 Mutation check done; docs updated; gate 10/10 PASS; BUG-0081 verified and closed; tracking updated.

### 2.5 Impact / rollback

Changes the contract of `align` (new fields with defaults, a ninth setting, the path may start after row 0 and end before
the last row) and the numbers of P6.07 (rerun, documented). `tempo_ratio` and `reference_band` need no change in code.
Rollback: restore `align.py` and the three consumers; the first run of the report stays.

## 3. Plan re-read (before coding)

Plan re-read: 2026-11-18 — OK, with the clarifications below (read against `align.py`, `cost.py`, `dtw.py`,
`tempo_ratio.py`, `bench/umons_compare.py`, `tools/umons_compare.py`, the tests of those modules and the P6.07 report; no
code was edited before this note). None of them changes the design or a data contract; each is the safest behaviour for a
point the plan left open, and each gets a test.

1. **The band on the kept grid with one kept row (or column).** `dtw` already defines this: `band_mask` gives a side of one
   element the coordinate 0, so a kept matrix of one row and `m > 1` columns has the end cell `1` away from the start and
   `no_path` below `band = 1` (P6.03a "As built" 5), and with `symmetricP1` no path whatever the band (`g[0, m-1]` is never
   reached without a row to step over). That is exactly what a segment of those lengths cut out of the feature arrays gives
   today, so no special case is written: `align` hands the kept sub-matrix to `dtw` and the result is the cut-out result.
   A `1 x 1` kept matrix is a path of one cell (as a segment of one frame each already is, `test_t_cmp_03j`).
2. **How `dtw` treats a 1-row matrix with `symmetricP1`:** `_accumulate_p1` never enters its loop for `n = 1`, so only
   `g[0, 0]` is finite: `m = 1` gives the one-cell path, `m > 1` gives `no_path`. Unchanged and tested through `align`.
3. **An empty segment keeps its refusal.** `dtw` refuses a cost with no row or no column (`at least one row and one
   column`). If `align` found "all frames dropped" before calling `dtw`, a segment with zero rows would silently become
   `no_path`. The dropped rule is therefore applied only when both segments have at least one row; with none, `align`
   calls `dtw` on the whole matrix as today, which refuses.
4. **No path because one side is entirely dropped.** `dtw` is called on a `1 x 1` matrix of `+inf` for the band and step
   validation and for the result object, then `params` gets the original `n` and `m`. A bad band or step is still refused
   (T-CMP-03p).
5. **`DtwResult` of a result with dropped frames.** `path` is in original indices; `params` has the original `n` and `m`;
   `accumulated` and `normalised` are those of the **kept** grid (for `symmetricP1` normalised is divided by the kept `n_k +
   m_k`), `distance` is `D` (the plain mean over the path cells, unchanged). A step of the mapped path may jump over dropped
   rows, so "every step is one of the three unit steps" holds on the kept grid only. All three statements go into the
   docstring.
6. **`Alignment` validates the dropped arrays** in `__post_init__` (a hand-made `Alignment` is possible, and an unsorted or
   out-of-range array would make `kept_*` and the times silently wrong): integer dtype, one-dimensional, strictly
   ascending, inside `[0, n)` and `[0, m)` of the cost, stored as new read-only `int64` arrays. The default is the empty
   array, so the hand-made alignments of P6.04 and P6.07 keep working. This is an addition to the plan (the plan only said
   "default empty").
7. **`local_tempo` at a dropped reference row.** The ratio at row `k` is the least-squares slope over the *observed* rows
   of its window (D3 of P6.04, already tested for a row without a path cell in
   `test_t_cmp_06e_a_reference_row_without_a_path_cell_...`): a dropped reference row has `t_query` NaN, is not counted in
   `window_rows` and is left out of every fit, and its own ratio is the slope of its observed neighbours (a property of the
   window, not an observation of that row). No code change; the docstrings say it and the new tests pin it. A dropped
   *query* row only removes a point from the matched times: the query clock keeps its real jump over the stretch, so the
   local ratio over it is larger, which is what happened in real time.
8. **`transfer_times` with NaN rows.** It accepts NaN in `matched` (a dropped reference row) and refuses any other non
   finite value (infinity); the observed values must not decrease; it interpolates over the observed rows only; a time
   outside the span of the first and the last observed rows is NaN, and **fewer than two observed rows give NaN for every
   time** (no span, nothing can be carried; the part is counted in `parts_outside`). With no NaN it is the function of P6.07.
   The test case `matched = [0, nan, 2]` that P6.07 listed among the clocks that are refused now becomes a valid input and
   moves to the new test; infinity stays refused.
9. **`parts_in_gap`** is decided by a small helper that works on the observed rows and the times the transfer uses (a time
   exactly on an observed row is not in a gap; strictly between two observed rows that are not neighbours on the grid is).
10. **The report needs the dropped counts, so the tool carries them.** The plan said "nothing else of the tool changes"; the
    acceptance criterion AC4 and the instruction to report "the number of dropped frames" need them per pair, so
    `PairDistance` and `PairBoundary` get `dropped_query` / `dropped_reference` (defaults 0, so existing hand-made values
    keep working), the CSV files and the pair tables show them next to `parts_in_gap`. Settings and options of the tool do
    not change. This is the only addition to the plan in `umons_compare.py` beyond `transfer_times` and `parts_in_gap`.
11. Line endings: every file I edit is LF (checked with Python bytes); new files are LF.

## 4. Implementation log

Not started.

## 5. Verification

Not started.

## 6. Self-review

Not started.

## 7. Bugs

BUG-0081 (the bug this task fixes). None new yet.

## 8. Close-out

- [ ] Acceptance criteria met (evidence in section 5)
- [ ] Checks pass
- [ ] No open S1/S2 bug from this task; BUG-0081 verified
- [ ] TASK_STATUS.md updated
- [ ] CHANGELOG.md entry added
- [ ] README status / DECISIONS.md updated if needed
