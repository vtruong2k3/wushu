# X.24 — End-to-end test of `sync_take` with an audio lag wrong by 1 s (BUG-0063 plan item a)

| Field             | Value                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-16)                                                                              |
| Owner             | agent (A)                                                                                      |
| Phase             | P2 (tests)                                                                                     |
| Estimate          | 0.1 day                                                                                        |
| Depends on        | X.23 (DONE), P2.06 (DONE)                                                                      |
| Plan confirmed by | Not required (a test only, under 1 day)                                                        |
| Started / Done    | 2026-11-16 / 2026-11-16                                                                        |

**Registered after the work:** the maintainer pasted the open items of the X.23 report without a task ID; this task records the
work that followed (CLAUDE.md asks for the ID first; it was not done first, which is noted here).

## 1. Analysis

**Goal:** close what the X.23 report listed as missing: a test that goes through `sync_take` and `sync.json` and shows that a take whose
audio lag is wrong by one second is not `usable_for_metrics` (BUG-0063 fix plan item a).

**In scope:** `tests/contract/test_sync_take_wrong_lag.py` (T-SYNC-05e); the P2.07 notes for the two other open items (the rate of false
flashes, real video); anything the test shows about the pipeline.
**Out of scope:** changing `sync_take`, the database schema or the usability rule (BUG-0065 waits for the maintainer's choice); real
recordings (P2.07).

**Method:** a real take (`helpers/flash_media.make_flash_take`: real container, real audio claps and flash frames) is synchronized by
`sync_take`; the audio result is forced wrong by ±1 s after the real audio sync ran (a clap pair damaged the same way at both ends
cannot be made reliably from synthetic audio: one missing clap gives two equal peaks that the ratio gate refuses, which is safe), so
the test fixes the outcome of BUG-0063 (`status = ok`, a wrong offset) and leaves the rest real.

**Constraints:** AGENTS.md §5.1, §5.9 (IDs only in the fixtures).

## 2. Plan

Steps: (1) write T-SYNC-05e (control, +1 s, −1 s with every flash seen, +1 s with camera A hiding a flash of each pair); (2) run it;
(3) probe what the database holds for such a take (the answer is BUG-0065); (4) register the bug, update BUG-0063's plan, the plan
rows and the P2.07 notes; (5) gate; close. A test that passes at once is not red first: its value is checked by what it asserts
(status `ok`, reason, `sync.json` read back, residual in frames) and by mutating the rule (§5).

**Acceptance criteria:**

- [x] AC1 T-SYNC-05e: the control is usable; the three wrong-lag cases are not usable with the right reason, in the returned manifest and in `sync.json` read back.
- [x] AC2 What the database holds for an unusable take is checked and registered (BUG-0065).
- [x] AC3 Gate 10/10; tracking updated.

## 3. Plan re-read (before coding)

Plan re-read: 2026-11-16 — OK (the plan was written in the same hour as the first code edit; `sync_take` and the fixtures were read just before: `sync_take`
calls `estimate_sync` by its module-level name, so the test patches `taiji_ai.pipeline.sync_take.estimate_sync` and the rest runs for real).

## 4. Implementation log

| Step | Done | Notes |
| ---- | ---- | ----- |
| 1 | 2026-11-16 | `test_sync_take_wrong_lag.py`, 4 cases. |
| 2 | 2026-11-16 | 4 passed (11 s). |
| 3 | 2026-11-16 | Probe: after `sync_take` with audio +1 s, `sync.json` is `usable = false (residual_too_large)` and the database holds a row with `offset_s` 1.5 (true 0.5), `residual_ms` 999.998, `validated_by = 'flash'`: BUG-0065. |
| 4 | 2026-11-16 | BUG-0065 registered (S2, PLANNED, the maintainer chooses A or B); BUG-0063 plan updated; plan row T-SYNC-05e; P2.07 notes. |

## 5. Verification

- `pytest tests/contract/test_sync_take_wrong_lag.py`: 4 passed.
- Mutation of `decide_usability` (copies of `src`): "residual limit ignored" is caught by T-SYNC-05e and by `test_sync_rule.py`; "missing end residual accepted" is
  caught by `test_sync_rule.py` only (the end-to-end case also fails the earlier `method` check: defense in depth); "flash method not required" survives both:
  equivalent, because `SyncValidation` forces every residual to null when the method is `none`, so the next guard returns the same reason.
- Gate `tools/check.ps1`: 10/10 PASS (145.3 s, 941 tests).

## 6. Self-review

- Files reviewed: the new test file; the doc edits. Nothing in `src/` changed.
- The test forces the audio result: it proves the flash safeguard and the pipeline, not that the audio match can be fooled (BUG-0063 stays open for that).
- Known limits: synthetic video only (P2.07 measures real files); the false-flash rate is not measured.

## 7. Bugs

| Bug ID | Severity | Status | Note |
| ------ | -------- | ------ | ---- |
| BUG-0065 | S2 | PLANNED | found by the probe of step 3; not caused by this task (P2.06 code); waits for the maintainer's choice |

## 8. Close-out

- [x] Acceptance criteria met (evidence above)
- [x] Checks pass
- [x] No open S1/S2 bug caused by this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed (no decision, README unchanged: no module state changed)
