# X.13 — Record the deferral of X.08 (GitHub Actions CI)

| Field             | Value                                                                              |
| ----------------- | ---------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                  |
| Owner             | agent (Claude Code)                                                                |
| Phase             | Ad-hoc (documentation only)                                                        |
| Estimate          | 0.05 day                                                                           |
| Depends on        | X.12 DONE (checked 2026-11-15)                                                     |
| Plan confirmed by | Maintainer, 2026-11-15: answered that CI is not needed for now                     |
| Started / Done    | 2026-11-15 / 2026-11-15                                                            |

## 1. Analysis

**Goal:** the tracking files say what the maintainer decided about X.08: it is deferred, not needed now.

**Decision taken as "defer", not "cancel":** the answer was that CI is not needed for now, not that it is never
wanted. AGENTS.md §2.1 allows `CANCELLED` only with the maintainer's approval and a recorded reason; a deferral keeps
the task in the list. X.08 therefore stays `TODO`, with a note. If the maintainer prefers `CANCELLED`, that is one
more edit.

**Places that still say X.08 waits for the maintainer's go (read 2026-11-15):**

| File | Place |
| ---- | ----- |
| `Docs/tracking/TASK_STATUS.md` | X.08 row: "needs the maintainer's decision before it starts" |
| `Docs/tasks/X.07.md` | §8, the unticked item about the go for X.08 |
| `Docs/tracking/CHANGELOG.md` | the X.07 entry: "X.08 needs a go before it starts", and the X.10 note under it: "only the go for X.08 remains open" |
| `Docs/tracking/DECISIONS.md` | DEC-0015: "Optional cover, not started: X.08" (true, but the answer is not recorded) |

**Not changed:** plan §4 (says CI "can cover if needed", still true), X.10 and X.07 text about X.08 being optional and
not started (still true), the P0.05 history.

**In scope:** the four places above, a CHANGELOG entry, a TASK_STATUS row.

**Out of scope:** any CI work, `.github/`, any code. No commit. No new rule or decision: DEC-0015 only gets the
deferral added to its sentence about X.08.

**Constraints that apply:** AGENTS.md §2.1 (status values), §4.3 (append-only: old text is struck through or followed
by a dated note); the maintainer's words are not quoted in the logs (X.11, X.12).

**Risks:** R1, a stale statement left behind: check with a grep for X.08 and read every hit. R2, an overwrite by another
writer: re-read the lines before the edit and review the diff.

## 2. Plan

**Files to modify:** `TASK_STATUS.md` (X.08 row, X.13 row), `X.07.md` (§8 item), `CHANGELOG.md` (one note, one entry),
`DECISIONS.md` (DEC-0015 sentence); new `X.13.md`.

**Implementation steps:**

1. Re-read this file and the four places (§3).
2. Edit the four places.
3. TASK_STATUS row and CHANGELOG entry.
4. Checks C-1..C-3, diagnostics, gate, `git diff` review; close.

**Test plan:** documentation task, manual checks.

| Check | What it verifies |
| ----- | ---------------- |
| C-1 | `grep X.08` over the `*.md` files: every statement that says it waits for a go is struck through or followed by the deferral note |
| C-2 | `getDiagnostics` (warnings and errors) empty; changed documents checked by URI, including the new one |
| C-3 | Gate 10/10 PASS; only the planned files changed; no commit |

**Acceptance criteria:**

- [x] AC1 X.08 is shown as deferred by the maintainer (still `TODO`, not cancelled) in TASK_STATUS and DEC-0015 (C-1).
- [x] AC2 No live-state place still asks for the maintainer's go on X.08 (C-1).
- [x] AC3 Diagnostics empty, gate 10/10 PASS, only planned files changed, no commit (C-2, C-3).

**Impact / rollback:** documentation only; rollback per hunk.

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK. Each of the four places and the CHANGELOG anchor for the new entry exists exactly once
  in the current files; `git status` shows 18 entries, all earlier uncommitted documentation work plus this file. No
  change to the plan.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1    | 2026-11-15 | Plan re-read (§3); grep of X.08 over the `*.md` files to find every statement that waits for a go (four places, §1). |
| 2    | 2026-11-15 | TASK_STATUS X.08 row (deferred, stays TODO), `X.07.md` §8 item struck through and ticked, a CHANGELOG note under the X.07 entry, DEC-0015 sentence extended. |
| 3    | 2026-11-15 | TASK_STATUS X.13 row, CHANGELOG entry (one wording fixed: no quotation marks around a paraphrase of the answer). |
| 4    | 2026-11-15 | Checks, diagnostics, gate, review (§5, §6). No deviation from the plan. |

## 5. Verification

Full gate (`tools\check.ps1`, this machine), exit 0: **RESULT: PASS (10/10) in 18.5s**.

| Check | Result |
| ----- | ------ |
| C-1   | Grep of X.08 over the `*.md` files, every hit read: TASK_STATUS X.08 row (deferred, status still TODO), `X.07.md` §8 (struck through, ticked, deferral note), DEC-0015 (deferral in the sentence), CHANGELOG (the old open line is followed by the X.10 note and the X.13 note), this file and the X.13 entry (describe the change); plan §4, X.10 and the rest of X.07 say only that X.08 is optional / not started, which is still true. No statement that X.08 waits for a go is left unmarked |
| C-2   | `getDiagnostics` (warnings and errors): global list `[]`; X.07, X.13, TASK_STATUS, CHANGELOG, DECISIONS checked by URI, no diagnostics |
| C-3   | Gate above; `git status`: the files of §2 plus the earlier uncommitted documentation work; no `src/`, `tests/`, `tools/`, `.github/` change; nothing committed |

## 6. Self-review

- Files reviewed (re-read after the edits): `TASK_STATUS.md` X.08 row, `X.07.md` §8, `CHANGELOG.md` X.07 entry and the
  X.13 entry, `DECISIONS.md` DEC-0015, this file.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ (deferral, not cancellation; status stays `TODO`) · edge cases ☑ (old
  text struck through or followed by a dated note, not deleted; statements that are still true were left alone) · no
  fabricated data ☑ · errors surfaced ☑ · tests cover criteria ☑ (documentation task: C-1..C-3) · no personal data ☑ ·
  docs updated ☑.
- Findings: none. One wording slip of my own (quotation marks around a paraphrase of the answer, against the rule of
  X.11 / X.12) was fixed before closing.
- Not covered: whether the maintainer wants `CANCELLED` instead of a deferral (one more edit if so).

## 7. Bugs

None found in this task.

## 8. Close-out

- [x] Acceptance criteria met (evidence above)
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed (DEC-0015 sentence)
