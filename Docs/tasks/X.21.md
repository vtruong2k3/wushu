# X.21 — Detailed plan for Phase 2 (ingest and camera sync)

| Field             | Value                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                              |
| Owner             | agent (A)                                                                                      |
| Phase             | P2 (planning)                                                                                  |
| Estimate          | 0.5 day                                                                                        |
| Depends on        | P0 (DONE), P1.05 and P1.06 (drafts written, for the IDs and the consent mapping)               |
| Plan confirmed by | Maintainer, 2026-11-15: confirmed P2.01, P2.02 and P2.04 and accepted the defaults of every question in P2.01..P2.08 |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                        |

**Registered after the work:** the maintainer asked for the Phase 2 plan in a message that had no task ID; this task was
created afterwards to record it (CLAUDE.md asks for the ID first; it was not done first, which is noted here).

## 1. Analysis

**Goal:** a plan for P2.01–P2.07, detailed enough that each task can be coded, tested and reviewed one by one, with the
risks found before they cost a rewrite.

**Read:** `IMPLEMENTATION_PLAN_V1.md` §6 and §14–15 (P2 rows, F-VID, T-IO, T-SCH, T-SYNC), `TECH_WORKFLOW_V1.md` W0–W2, §4
(data contracts), §5, §10; the code `io/probe.py`, `io/frames.py`, `store/artifacts.py`, `store/db.py`, `config.py`,
`migrations/0001_init.sql`, `tests/conftest.py`, `tests/contract/test_video_io.py`; the capture protocol and the consent form.

**Findings:**

1. **BUG-0046** (registered, planned for P2.02): `is_vfr` reports a constant-frame-rate video as VFR when the time base is
   coarse (30 fps at 1/1000: std/median 1.43 % > 1 %). Measured on synthetic clips.
2. Proxy (experiment): FFmpeg keeps the source timestamps (0.000 ms difference) on a VFR source and on a rotated source and
   gives an upright proxy; the filter `scale=-2:720` **enlarges** a smaller source, so the height is capped (P2.03).
3. Audio and video of an FFmpeg-made MP4 start together and a click lands within one sample of its true time (P2.04); real
   phones are measured in P2.07.
4. W2's mapping formula did not say what `t0` is or which camera is the reference: P2.01 fixes
   `t_b = t_a + offset_s + drift × (t_a − t_ref_s)` on each camera's video timeline.
5. The database column `sync.drift` is NOT NULL DEFAULT 0, but an unknown drift stored as 0 would be a fabricated value
   (AGENTS.md §5.1): `sync.json` holds the null, a `sync` row is written only when both ends are matched (P2.01 Q4).
6. **Gap:** no task writes a `participant` row, but ingest must refuse a recording without a participant with consent
   (AGENTS.md §9.5): new task **P2.08**.
7. The estimates grow from 4 to 5.5 days (P2.01 0.5 → 0.75, P2.02 1 → 1.25, P2.06 0.25 → 0.5, P2.08 +0.5).

## 2. Plan

Write `Docs/tasks/P2.01.md` … `P2.08.md`; update `TASK_STATUS.md`, `BUGS.md`; after the maintainer's answers update
`IMPLEMENTATION_PLAN_V1.md` §3 and §6 (dated) and `DECISIONS.md` (DEC-0025).

**Acceptance criteria:**

- [x] AC1 One task file per P2 task and for the new P2.08, each with goal, design, files, steps, tests, acceptance criteria.
- [x] AC2 Every risk found has a registered bug or a recorded decision.
- [x] AC3 The maintainer's confirmations recorded; plan, DEC-0025 and tracking updated; gate 10/10 PASS.

## 3. Plan re-read

Not applicable (documents only).

## 4. Implementation log

Eight task files written; two experiments run in the session scratchpad (not in the repository); BUG-0046 registered;
a table-pipe lint defect of mine (MD056 in P2.03) found by the IDE and fixed. After the maintainer's answers:
DEC-0025, the plan (§3 and §6 of `IMPLEMENTATION_PLAN_V1.md`), the confirmations in P2.01, P2.02, P2.04 and P2.08.

## 5. Verification

Gate 10/10 PASS (21.2 s) after the plans were written; IDE markdownlint clean on all eight task files, `TASK_STATUS.md`
and `BUGS.md`; re-run after the confirmations (see CHANGELOG).

## 6. Self-review

- The experiments are on synthetic clips only; phone files may differ (encoder priming, edit lists): P2.07 and the rehearsal
  (P2.07 Q1) measure them. This is stated in P2.03, P2.04 and P2.07.
- The plans hold no code and no personal data.

## 7. Bugs

BUG-0046 (S3, PLANNED, fix in P2.02).

## 8. Close-out

- [x] Acceptance criteria met
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] DECISIONS.md updated (DEC-0025)
