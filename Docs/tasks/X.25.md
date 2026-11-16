# X.25 — The `sync` database row only for usable takes (BUG-0065, option A)

| Field             | Value                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-16)                                                                                  |
| Owner             | agent (A)                                                                                      |
| Phase             | P2 (rework of P2.06)                                                                           |
| Estimate          | 0.1 day                                                                                        |
| Depends on        | P2.06 (DONE), X.23 (DONE), X.24 (DONE)                                                         |
| Plan confirmed by | Maintainer, 2026-11-16: chose option A and kept the severity S2                                |
| Started / Done    | 2026-11-16 / 2026-11-16                                                                                 |

## 1. Analysis

**Goal:** a reader of the `sync` table can never take a time mapping that the usability rule refused (BUG-0065).

**Cause (code read):** `pipeline/sync_take.py` upserts the row when `manifest.status == "ok"`; the usability decision is made before but not used.
The table has no usable column (migration 0001) and `validated_by` is `'flash'` whenever the flash method ran.

**Change (option A):** the row is written only when `manifest.usable_for_metrics` is true; otherwise any existing row of the take and camera pair is
deleted (a re-run that becomes unusable removes the old row). `sync.json` is unchanged and keeps the full result of every take. No migration.
**Amends:** DEC-0025 item 7 and P2.01 Q4 ("a row for `status = ok`" becomes "a row only for `usable_for_metrics = true`"): DEC-0035.
**Out of scope:** the schema (option B), the usability rule, readers of the table (none exist).

**Files:** `src/taiji_ai/pipeline/sync_take.py`; docstrings in `store/sync.py`, `schemas/sync.py` (`to_db_row`); tests
`tests/contract/test_sync_take_wrong_lag.py`, `tests/contract/test_sync_take.py` (unchanged cases must still pass); docs `Docs/TECH_WORKFLOW_V1.md` if it
describes the row, `Docs/tasks/P2.01.md` (note), DEC-0035, tracking.

## 2. Plan

1. Re-read (§3). 2. Tests red first: T-SYNC-05f in `test_sync_take_wrong_lag.py`: after `sync_take` with an audio lag wrong by 1 s there is no row; a row written by a
usable run is removed by a later unusable run; a usable take keeps its row. 3. The change. 4. Targeted tests, mutation of the new condition. 5. Docs, gate, close.

**Acceptance criteria:**

- [x] AC1 T-SYNC-05f passes and failed on the old code.
- [x] AC2 `test_sync_take.py` and `test_sync_rule.py` pass unchanged.
- [x] AC3 The mutant (row for `ok` again) is caught.
- [x] AC4 Gate 10/10; DEC-0035, BUG-0065, docs and tracking updated.

**Impact / rollback:** one condition; rows can be regenerated with `taiji sync`.

## 3. Plan re-read (before coding)

Plan re-read: 2026-11-16 — OK. `sync_take.py` still has the `if manifest.status == "ok"` block with `to_db_row()` and the `else: delete_sync`; the cases of
`test_sync_take.py` (usable take has a row; `start_only` has none) stay true under the change; `to_db_row()` returns `None` for a non-`ok` take, so a usable
take (which implies `ok`) always has a row to write.

## 4. Implementation log

| Step | Done | Notes |
| ---- | ---- | ----- |
| 1 | 2026-11-16 | Plan re-read (§3). |
| 2 | 2026-11-16 | T-SYNC-05f written first: 3 of 4 failed on the old code (refused takes had a row; the old row survived a re-run). |
| 3 | 2026-11-16 | `sync_take`: `db_row = manifest.to_db_row() if manifest.usable_for_metrics else None`; upsert if there is a row, delete otherwise. Docstrings of `store/sync.py` and `to_db_row`. |
| 4 | 2026-11-16 | 21 tests of the three sync files pass; 2 mutants caught. |
| 5 | 2026-11-16 | DEC-0035, P2.01 note, plan row, BUG-0065, tracking. |

## 5. Verification

- Red first: T-SYNC-05f 3 failed, 5 passed (with the 4 cases of T-SYNC-05e).
- After: `test_sync_take_wrong_lag.py`, `test_sync_take.py`, `test_sync_rule.py`: 21 passed, the old cases unchanged.
- Mutation: "row for every ok take again" and "old row not deleted" both caught.
- Gate `tools/check.ps1`: 10/10 PASS (121.4 s, 945 tests).

## 6. Self-review

- Files reviewed: the diff of `sync_take.py` (one condition), the two docstrings, the test file, the doc edits.
- A usable take implies `status = ok`, so `to_db_row()` is never `None` for it; a non-ok take still deletes any old row, as before.
- Not covered: a reader of the table (none exists); option B stays a possible later change (DEC-0035).
- Found while closing: nothing new.

## 7. Bugs

| Bug ID | Severity | Status | Note |
| ------ | -------- | ------ | ---- |
| BUG-0065 | S2 | CLOSED | the bug of this task, fixed and verified here |

## 8. Close-out

- [x] Acceptance criteria met (evidence above)
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed
