# X.17 — Set aside the coach-interview tasks (P1.02, P1.03)

| Field             | Value                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                       |
| Owner             | agent (Claude Code)                                                                     |
| Phase             | Ad-hoc (tracking only)                                                                  |
| Estimate          | 0.05 day                                                                                |
| Depends on        | none                                                                                    |
| Plan confirmed by | Maintainer, 2026-11-15: asked to set aside, for now, the whole interview part           |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                |

## 1. Analysis

**Goal:** the tracking files say that the interview tasks are paused by the maintainer's decision, what that stops, and
what goes on.

**What the interview part is:** P1.01 (the guide) is DONE and stays so. The interviews (P1.02) and the synthesis (P1.03)
are the tasks that need coaches. Their state today: P1.02 `IN_PROGRESS` (the agent part, template and checklist, is done;
no coach is booked; no `observed` note exists), P1.03 `PLAN_READY`.

**Status chosen:** `BLOCKED` (AGENTS.md §2.1) with the reason and the way out in `TASK_STATUS.md`: the reason is the
maintainer's decision, the way out is that the maintainer books at least two coaches or says to resume. `CANCELLED` is
not used: nothing is dropped.

**What the pause stops (read from the plan, 2026-11-15):**

| Item | Effect |
| ---- | ------ |
| Gate G00 | cannot pass: it needs a concrete need (P1.03) |
| P1.07 metric definitions, P1.08 pilot targets | wait: they depend on P1.03 |
| P1.04, H review part | waits for the H confirmation of the form; the code part is not affected |
| Pilot recording and annotation (P9) | the task row of P9.01 lists only P1.06 as its dependency, but the roadmap diagram (P1 leads to P9) and the weekly schedule put G00 before the pilot recording; whether P9.01 may start before G00 is the maintainer's call, not decided here |
| P2–P8 (ingest, pose, quality, metrics, pipeline, UI) | not affected (plan §3 diagram: P0 leads to P2 and P3) |

**What goes on:** P1.04 code, P1.05, P1.06, P1.09 when people are known, P1.10 (closed), and P2 onwards.

**Not changed:** the guide v0.2, the template, the checklist, the four simulated records. The plan's fallback "fewer than
two coaches: shrink to a geometry proof of concept" is not triggered, because no attempt to book coaches was made.

**In scope:** DEC-0021; `TASK_STATUS.md` (P1.02, P1.03, the notes of P1.04, P1.07, P1.08, the summary counts);
a "set aside" paragraph in the task files of P1.02 and P1.03; the CHANGELOG entry. **Out of scope:** any other task, the
UMONS download of X.16 (running in the background).

**Constraints that apply:** AGENTS.md §2.1 (BLOCKED needs a reason and a way out), §4.1 (a decision goes to
`DECISIONS.md`), §4.3 (nothing deleted).

## 2. Plan

**Steps:** DEC-0021; TASK_STATUS; the two task files; CHANGELOG; diagnostics and gate; close.

**Checks:** C-1 DEC-0021 present, next free ID DEC-0022; C-2 P1.02 and P1.03 are `BLOCKED` in TASK_STATUS with the reason
and the way out, in the task files too; C-3 the summary counts add up (P1: 2 DONE, 6 in progress, 2 BLOCKED); C-4
diagnostics empty, gate 10/10 PASS.

**Acceptance criteria:**

- [x] AC1 The decision is recorded with its consequences (C-1).
- [x] AC2 P1.02 and P1.03 show `BLOCKED` with reason and way out in TASK_STATUS and in their files (C-2, C-3).
- [x] AC3 Diagnostics empty, gate 10/10 PASS, no commit (C-4).

**Impact / rollback:** documentation only; resuming means setting the two rows back to their earlier statuses.

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK. The TASK_STATUS rows of P1.02 to P1.09 were read just before editing; the summary row of
  P1 is `10 / 2 / 8 / 0 / 0` and the Total row `100 / 11 / 8 / 0 / 81`.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1 | 2026-11-15 | DEC-0021 written. |
| 2 | 2026-11-15 | TASK_STATUS: P1.02 and P1.03 `BLOCKED` with reason and way out; notes of P1.04, P1.07, P1.08 say the interview part is set aside; the P1 and Total rows recounted; row X.17. |
| 3 | 2026-11-15 | A "set aside" paragraph added at the top of the task files of P1.02 and P1.03; CHANGELOG entry. |
| 4 | 2026-11-15 | **Correction before the checks:** the effects table of §1 had a row on P9 that claimed more than the plan says; rewritten to state only that P9.01 lists P1.06 as its dependency while the roadmap and the schedule put G00 before the pilot recording, and that the call is the maintainer's. |

## 5. Verification

Full gate: **RESULT: PASS (10/10) in 19.3s**, exit 0.

| Check | Result |
| ----- | ------ |
| C-1 | DEC-0021 present; next free ID DEC-0022 |
| C-2 | `TASK_STATUS.md`: P1.02 and P1.03 are `BLOCKED` (2 rows in the P1 table) with the reason and the way out; both task files carry the "set aside" paragraph under their header |
| C-3 | Summary: P1 is 10 tasks = 2 DONE + 6 in progress + 2 BLOCKED + 0 TODO; Total 100 = 11 + 6 + 2 + 81 (sum checked by script) |
| C-4 | `getDiagnostics` (warnings and errors): empty; gate above |

## 6. Self-review

- Files reviewed: `DECISIONS.md` DEC-0021, the P1.02 to P1.08 rows of `TASK_STATUS.md`, the two task files, this file.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ (BLOCKED has reason and way out; nothing deleted; counts add up) · no
  fabricated data ☑ · errors surfaced ☑ (the P9 overstatement was found and corrected) · no personal data ☑ · docs
  updated ☑.
- Findings: one wrong statement of mine in the effects table (see §4 step 4), fixed before the checks.
- Not decided here: whether P9.01 may start before G00; the maintainer decides if and when it matters.

## 7. Bugs

None found so far.

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed
