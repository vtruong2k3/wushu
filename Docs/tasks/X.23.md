# X.23 — Flash check: match flashes one to one and by pair (BUG-0064, S1)

| Field             | Value                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-16)                                                                                  |
| Owner             | agent (A)                                                                                      |
| Phase             | P2 (rework of P2.05, W2 step 4)                                                                |
| Estimate          | 0.25 day                                                                                       |
| Depends on        | P2.05 (DONE), P2.06 (DONE), P2.04 (DONE)                                                       |
| Plan confirmed by | Maintainer, 2026-11-16: raised BUG-0064 to S1 and asked for the fix, including the code of P2.05 (the plan below is the plan of the bug) |
| Started / Done    | 2026-11-16 / 2026-11-16                                                                                 |

## 1. Analysis

**Goal:** a time mapping that is wrong by one pair gap (1 s) must never be `usable_for_metrics`, whether or not every flash of
a pair is seen by both cameras (BUG-0064; BUG-0063 relies on this check).

**Found by:** a probe of the agent on synthetic takes (2026-11-16, task P2.04 close-out). Probe table (30 fps, flash pairs at 2.0/3.0 s and
12.0/13.0 s, B delayed by 0.5 s, audio offset given as true + 1.0 s): all flashes seen: residual 500 ms, `usable = false`; A shows one flash
per pair (A 2 flashes, B 4): residual **0.0 ms**, `usable = true`.

**Cause (code read):** `io/flash.py` `validate_sync.match_residuals`: for each flash of A it takes the closest flash of B within 1.5 s and
averages the distances. A flash without a partner is ignored, the counts of the two cameras are never compared, one flash of B may serve
two flashes of A, and the mean can hide one bad match. The first flash of A, moved by a lag wrong by one pair gap, lands on the second
flash of B at 0 ms.

**In scope:** `match_flashes` (new, pure function) replaces `match_residuals`; `FlashParams.min_flashes` (2); tests (unit of the function,
contract of the five probe cases and one more); `Docs/TECH_WORKFLOW_V1.md` W2 step 4; `Docs/capture_protocol.md` (both flashes of every
signal must be seen by both cameras; the quick check at the take); plan test rows; README; DEC-0034; tracking.

**Out of scope:** flash detection (`find_flash_onsets`, `brightness_series`) and the usability rule (`io/sync_rule.py`): unchanged;
the schema `SyncValidation` (the fields mean the same thing); a new `usable_reason` (a window that cannot be judged is
`flash_not_found`, as before; the reason is logged).

**Interfaces and units:** unchanged: `validate_sync(audio_sync, rec_dir_a, rec_dir_b, *, params, settings) -> SyncValidation`; times in
seconds on each camera's own video timeline; residuals in ms; `residual_frames` in frames of the slower camera.

**Existing code and docs read:** `io/flash.py`, `io/sync_rule.py`, `schemas/sync.py` (`SyncValidation`), `pipeline/sync_take.py`,
`tests/contract/test_flash.py`, `tests/contract/test_sync_take.py`, `tests/unit/test_sync_rule.py`, `Docs/capture_protocol.md`
(§ signals), `Docs/TECH_WORKFLOW_V1.md` W2.

**Constraints that apply:** AGENTS.md §5.1 (no made-up numbers: an unmatched flash is not a residual of 0), §5.4 (units), §6 (log IDs
only), §2 (S1: regression tests mandatory).

**Unknowns, risks:** (1) stricter rule: a false flash on one camera (a reflection, a lamp) now makes the window `flash_not_found` and the take
unusable for metrics (safe: it is shown side by side only and logged); the real rate is measured in P2.07. (2) A flash pair is
two flashes about 1 s apart (protocol); a window with a single flash on both cameras cannot be told from its neighbour and is not accepted.

## 2. Plan

**Design:**

```python
def match_flashes(onsets_a, onsets_b, a_to_b, *, min_flashes=2) -> float | None:
    """Largest |t_b - a_to_b(t_a)| [ms] over the flashes of one window, matched one to one in time order;
    None when the window cannot be judged (fewer than min_flashes on either camera, or different counts)."""
```

`a_to_b` is increasing (slope 1 + drift, |drift| < 1), so the order of A's flashes is the order of B's. Counts must be equal and at
least `min_flashes`; the i-th flash of A is compared with the i-th of B; the window residual is the **largest** distance (not the mean).
The pair gap is checked by the same numbers: the two flashes of each camera must both land within the residual of their
partners. In `validate_sync` the result replaces `match_residuals` for the start and the end window; everything else is unchanged.

**Files:** `taiji_ai/src/taiji_ai/io/flash.py`; tests: `taiji_ai/tests/unit/test_flash_match.py` (new),
`taiji_ai/tests/contract/test_flash_pairs.py` (new), `taiji_ai/tests/helpers/flash_media.py` (new);
docs: `Docs/TECH_WORKFLOW_V1.md`, `Docs/capture_protocol.md`, `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`,
`Docs/tracking/*`, `Docs/tasks/P2.05.md` (a note).

**Steps:**

1. Re-read this file and the code (§3).
2. Tests red first on the old code: unit tests of `match_flashes` (ImportError), contract tests with the probe's cases.
3. Implement `match_flashes`, `FlashParams.min_flashes`, use it in `validate_sync`.
4. Tests green; the whole `test_flash.py`, `test_sync_take.py`, `test_sync_rule.py` still pass.
5. Targeted mutation check of the new function (copies of src, repository untouched).
6. Docs and tracking; gate; self-review; close.

**Test plan:**

| Test ID | Type | What it checks | New / existing |
| ------- | ---- | -------------- | -------------- |
| T-SYNC-04e | unit | `match_flashes`: equal counts in order, max not mean, fewer than 2 flashes, different counts, the 1 s alias, unsorted input, a negative lag | new |
| T-SYNC-04f | contract | The probe cases through `estimate_sync` + `validate_sync` + `decide_usability`: right offset usable; +1 s and −1 s with every flash seen: `residual_too_large`; A or B missing a flash of each pair: not usable (`flash_not_found`); only the end pair damaged | new |
| T-SYNC-04c | contract | Right offset ≤ 1 frame; a 3 frame error gives ≈ 3 frames | existing (must still pass) |

**Acceptance criteria:**

- [x] AC1 T-SYNC-04e and 04f pass and were red on the old code (04f: the two "A shows one flash per pair" cases).
- [x] AC2 The five cases of BUG-0064 give `usable_for_metrics = false`; the control gives `true`.
- [x] AC3 `test_flash.py`, `test_sync_take.py`, `test_sync_rule.py` pass unchanged.
- [x] AC4 The mutants of `match_flashes` (count check removed, min_flashes 1, mean instead of max, closest-flash matching) are caught.
- [x] AC5 Gate 10/10; docs, DEC-0034, BUG-0064 and BUG-0063 plan updated.

**Impact / rollback:** one function and one `FlashParams` field; `sync.json` can be regenerated (`taiji sync`), takes synchronized before
this task must be synchronized again (no real takes exist yet).

## 3. Plan re-read (before coding)

Plan re-read: 2026-11-16 — OK. Checked against the current `io/flash.py`: `match_residuals` is still the nested function at the lines the
analysis names, used twice (start and end window) and nowhere else; `FlashParams` is used only inside `flash.py` (no test builds it with
positional arguments), so a new field with a default is safe; `SyncValidation` needs no change (a window that cannot be judged gives a
`None` residual for that end, which the schema and `decide_usability` already treat as `flash_not_found`). One thing sharpened while
re-reading: the pair gap is not checked by a separate number; the per-flash residual of every partner (largest, not mean) already fails a
pair whose gap differs by more than the residual limit, and it also fails a pair moved as a whole, which a gap check alone would miss.

## 4. Implementation log

| Step | Done | Notes / deviations from the plan |
| ---- | ---- | -------------------------------- |
| 1 | 2026-11-16 | Plan re-read (§3). |
| 2 | 2026-11-16 | Tests red first on the old code: T-SYNC-04e `ImportError`; T-SYNC-04f 7 of 10 failed (A shows one flash per pair, +1 s and −1 s; B shows only the first flashes; only the end pair damaged; only the start pair damaged; right offset with A showing one flash per pair; each camera hiding a different flash); the 3 that passed are the control and the two cases with every flash seen. |
| 3 | 2026-11-16 | `match_flashes`, `FlashParams.min_flashes`; `validate_sync` calls it for both windows. Deviation: no separate pair-gap number (§3). |
| 4 | 2026-11-16 | 43 tests of the three flash/sync files plus the new ones pass; lint, format and mypy clean after two lines were shortened. |
| 5 | 2026-11-16 | Mutation check on copies of `src`: 7 of 8 caught at once; "input order not sorted" survived because the order test passed two reversed lists in the same order; the test was strengthened and the mutant is caught. |
| 6 | 2026-11-16 | Docs: W2 step 4, capture protocol (both flashes of each signal on both cameras), plan rows, README, P2.05 note, DEC-0034, BUGS, CHANGELOG, TASK_STATUS. |

## 5. Verification

- Probe before the fix (synthetic takes, scratch script): right offset 0.0 ms usable; ±1 s with every flash seen 500 ms not usable; +1 s and −1 s with A showing
  one flash per pair **0.0 ms usable (the bug)**; B showing one flash per pair 1000 ms not usable.
- Red first: `test_flash_match.py` ImportError; `test_flash_pairs.py` 7 failed, 3 passed.
- After: `test_flash_match.py` 15 passed; `test_flash_pairs.py` 10 passed; `test_flash.py`, `test_sync_take.py`, `test_sync_rule.py` pass unchanged.
- Mutation (8 mutants of `match_flashes`): 8 of 8 caught.
- Gate `tools/check.ps1`: 10/10 PASS (179.9 s, 937 tests).

## 6. Self-review

- Files reviewed: the diff of `io/flash.py` (one new function, one field, two call sites; the nested function is gone), the three new test files, the doc edits.
- Does the code do what the plan says, nothing missing, nothing extra? Yes. `np` is still used by `find_flash_onsets`; `Callable` is imported under `TYPE_CHECKING`.
- Edge cases: empty windows, one flash each, different counts (A or B with one more or one fewer), unsorted input, negative lag, a mapping with drift, `min_flashes`
  changed, the right offset with a flash hidden (refused: the take must be shot again), each camera hiding a different flash.
- No fabricated data: an unmatched flash gives a null residual, never 0; errors are not swallowed (the module's decode errors still raise `FlashError`).
- Known limits, not fixed: a false flash on one camera (reflection, lamp) makes the window not judged (safe, shown side by side only); the real rate and the real
  flash detection thresholds are for P2.07; the audio-side limits of BUG-0063 remain.
- Found while re-reading the function: `min_flashes=0` with two empty windows would raise `ValueError` from `max([])`; fixed (`max(1, min_flashes)`), asserted in `test_t_sync_04e_min_flashes_is_a_parameter`, gate run again on the final tree.

## 7. Bugs

| Bug ID | Severity | Status | Note |
| ------ | -------- | ------ | ---- |
| BUG-0064 | S1 | CLOSED | the bug of this task, fixed and verified here |

## 8. Close-out

- [x] Acceptance criteria met (evidence above)
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed
