# X.11 — Fix the open markdownlint bugs (BUG-0032, BUG-0033, BUG-0034) and cut the chat quote from DEC-0015

| Field             | Value                                                                                     |
| ----------------- | ----------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                         |
| Owner             | agent (Claude Code)                                                                       |
| Phase             | Ad-hoc (documentation only)                                                               |
| Estimate          | 0.1 day                                                                                   |
| Depends on        | X.10 DONE (checked 2026-11-15)                                                            |
| Plan confirmed by | Maintainer, 2026-11-15: asked in the conversation to check the bugs, fix them and cut the quote from DEC-0015 |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                   |

## 1. Analysis

**Goal:** leave no open bug in `BUGS.md`, and remove verbatim chat text from the decision log at the maintainer's request.

**Open bugs found by the check (2026-11-15):** `BUGS.md` summary rows with a status other than CLOSED: BUG-0033, BUG-0032
(both S3, PLANNED). The IDE problems list (`getDiagnostics`, warnings and errors, all files it analyses) shows one more
markdownlint warning that nobody had registered: `Docs/tasks/P0.07.md` line 338, MD022 (a heading without a blank line
above it). It is in `HEAD`, introduced by the P0.07 rework commit `84c9bff` (`git log -S` on the heading), so it is
pre-existing, not caused by X.10. It is registered as **BUG-0034** (S3) before the fix.

**In scope:**

1. BUG-0032: `Docs/tasks/P0.06.md` §5 "Step 9": a blank line between "Command:" and its fence, and between
   "Output captured:" and its fence (lines 440-441 and 446-447 now). The closing fences are already followed by a blank line.
2. BUG-0033: `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3: a blank line between the paragraph ending "Cung cấp 3 hàm công khai:"
   (line 408) and the list (line 409).
3. BUG-0034: `Docs/tasks/P0.07.md`: a blank line between the "Timing: …" line (337) and the heading "### Rework evidence" (338).
4. Cut the verbatim quote of the maintainer's sentence from `DECISIONS.md` DEC-0015 (the reason cell) and from
   `Docs/tasks/X.10.md` (header "Plan confirmed by" and the self-review finding that offered the cut). The facts stay
   (single machine, decision of 2026-11-15, source task).
5. BUG-0035 (found while verifying this task, registered before the fix; plan changed 2026-11-15, see §3): `X.10.md`
   line 19 begins with a plus sign, which markdown reads as a list item (MD032, and MD004 on its dash lists), and
   `X.11.md` has five bold-only labels (MD036). Reflow the X.10 line; put a colon inside the X.11 labels.
6. `BUGS.md` (BUG-0032..0035 CLOSED), `TASK_STATUS.md`, `CHANGELOG.md`.

**Out of scope:**

- Any text change: only blank lines are inserted in 1-3; the pasted evidence is unchanged.
- Other verbatim chat quotes that exist in the logs (X.07 "Plan confirmed by" and its TASK_STATUS reason, DEC-0014, the
  confirmation lines of P0.06 / P0.07): the maintainer named only the DEC-0015 quote. They are listed in the close-out
  report and left unchanged until the maintainer says so.
- `/usage` and skill settings: untouched. No code, no commit.

**Existing files read:** `BUGS.md` (open rows), the IDE diagnostics, `P0.06.md` lines 437-461, `P0.07.md` lines 334-340,
`IMPLEMENTATION_PLAN_V1.md` lines 404-412, `DECISIONS.md` DEC-0015, `X.10.md` (the two quotes).

**Constraints that apply:** AGENTS.md §3 (a bug found gets an ID and a fix plan before other work), §4.3 (append-only:
the quote cut is the one deliberate removal, done at the maintainer's request and recorded without repeating the quote),
§2 Step 4 (self-review).

**Unknowns / risks:**

| #  | Risk | Mitigation |
| -- | ---- | ---------- |
| R1 | The IDE only analyses open files, so a clean result for a closed file may mean "not checked" | Verify each fix by reading the changed lines against the rule text (blank line present), and call `getDiagnostics` with the file's URI after the edit; the earlier hook output proved the three warnings appear on edit |
| R2 | A blank line inside a fenced block would change the pasted evidence | The blank lines go **outside** the fences (before the opening fence); `git diff -U0` must show only added empty lines for 1-3 |
| R3 | Another writer (Codex processes still run) overwrites a file | Re-read each region right before editing; `git diff --stat` at the end shows only the planned files |

## 2. Plan

**Files to create / modify:**

| File | Change |
| ---- | ------ |
| `Docs/tasks/X.11.md` | new (this file); bold labels get a colon (BUG-0035) |
| `Docs/tasks/P0.06.md` | 2 empty lines inserted (BUG-0032) |
| `Docs/IMPLEMENTATION_PLAN_V1.md` | 1 empty line inserted (BUG-0033) |
| `Docs/tasks/P0.07.md` | 1 empty line inserted (BUG-0034) |
| `Docs/tracking/DECISIONS.md`, `Docs/tasks/X.10.md` | quote cut; X.10 also one wrapped line reflowed (BUG-0035) |
| `Docs/tracking/BUGS.md` | BUG-0034 and BUG-0035 registered, BUG-0032..0035 CLOSED with Fix / Verified; next free ID BUG-0036 |
| `Docs/tracking/TASK_STATUS.md`, `Docs/tracking/CHANGELOG.md` | X.11 row and entry |

**Implementation steps:**

1. Register BUG-0034 in `BUGS.md` (fix plan before the fix); X.11 row in TASK_STATUS.
2. Re-read this file and each region against the current files (§3).
3. Insert the blank lines (BUG-0032, 0033, 0034); cut the quote (DEC-0015, X.10).
4. Checks C-1..C-5, gate, `git diff` self-review.
5. Close the three bugs, the task, CHANGELOG.

**Test plan:** documentation task, manual checks.

| Check | What it verifies |
| ----- | ---------------- |
| C-1 | `git diff -U0` of `P0.06.md`, the plan, `P0.07.md` against the X.07 / X.10 state: the X.11 hunks are added empty lines only (outside fences) |
| C-2 | `getDiagnostics` (warnings and errors): no MD031 for `P0.06.md`, no MD032 for the plan, no MD022 for `P0.07.md`, nothing for `X.10.md` and `X.11.md`; the global list (warnings and errors) is empty, and every other changed document is checked by URI |
| C-3 | a grep of `Docs/` for the maintainer's sentence quoted in DEC-0015 returns nothing; DEC-0015 still has 6 columns and its facts |
| C-4 | `BUGS.md`: no summary row with a status other than CLOSED; next free ID is BUG-0035 |
| C-5 | Full gate 10/10 PASS; `git status` shows only the planned files plus the earlier uncommitted work |

**Acceptance criteria:**

- [x] AC1 The warnings of BUG-0032..0035 are gone (P0.06, plan, P0.07, X.10, X.11); the text of P0.06, the plan and
      P0.07 is unchanged except added empty lines (C-1, C-2).
- [x] AC2 DEC-0015 and X.10 contain no verbatim quote of the maintainer's sentence and keep every fact (C-3).
- [x] AC3 BUG-0032..BUG-0035 CLOSED with Fix and Verified lines; no open bug left (C-4).
- [x] AC4 Gate 10/10 PASS; only planned files changed; no commit (C-5).

**Impact / rollback:** documentation only. Rollback per hunk (the files also hold X.07 / X.10 uncommitted edits).

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK, with one addition. Checked the regions against the files: `P0.06.md` 440/441 and 446/447
  ("Command:" and "Output captured:" directly above their fences), plan 408/409, `P0.07.md` 337/338; the exact quote
  strings are in DEC-0015 (reason cell) and `X.10.md` lines 10 and 151-152. **Addition:** `X.10.md` line 150 (self-review
  checklist) says "the decision quotes the maintainer's one sentence", which is false after the cut, so it is corrected
  too. `git status`: only the X.07 / X.10 work, BUG-0034 and the X.11 row (all uncommitted). No other change to the plan.
- **Plan change, 2026-11-15 (after the first edits, before the closing steps):** the verification step (`getDiagnostics`
  on every changed document, not only the three target files) found warnings in my own new files, `X.10.md` (a wrapped
  line starting with a plus sign: 1 MD032 and 18 MD004) and `X.11.md` (5 MD036). Registered as BUG-0035 and added to the
  scope (§1 item 5, files table, AC1, C-2, §7) before fixing them. The blank-line fixes and the quote cut were already
  applied under the original plan; nothing already done changes.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1    | 2026-11-15 | Bug check: `BUGS.md` open rows (BUG-0033, BUG-0032) plus `getDiagnostics` (found the unregistered MD022 in `P0.07.md`). BUG-0034 registered with its fix plan; X.11 row; plan re-read (§3). |
| 2    | 2026-11-15 | BUG-0032 (two empty lines before the fences in `P0.06.md`), BUG-0033 (one in the plan §14.3), BUG-0034 (one in `P0.07.md`). All outside fences; text unchanged. |
| 3    | 2026-11-15 | Quote cut: DEC-0015 reason cell ("a single machine (stated 2026-11-15)"), `X.10.md` header, one `X.10.md` self-review line that said the decision quotes the sentence, and the `X.10.md` finding that offered the cut (now a one-line note that it was cut). |
| 4    | 2026-11-15 | Verification with `getDiagnostics` on every changed document found my own warnings: `X.10.md` (1 MD032 + 18 MD004 from a wrapped line starting with a plus sign), `X.11.md` (5 MD036), and in `BUGS.md` one MD038 (a code span with a trailing space) plus a wrong count (19 instead of 18 MD004) in the BUG-0035 text, both fixed at once. Plan changed before fixing (§3), BUG-0035 registered. |
| 5    | 2026-11-15 | BUG-0035 fixed (X.10 line reflowed, X.11 labels with a colon). BUG-0032..0035 closed in `BUGS.md` with a one-off script kept outside the repo (scratchpad): one assertion per replacement; its first run stopped on a Python 3.12 API error before writing anything (`BUGS.md` hash unchanged), the second run applied all eight replacements. |
| 6    | 2026-11-15 | Gate, `getDiagnostics`, `git diff` self-review (§5, §6); close-out. |

## 5. Verification

Full gate (`tools\check.ps1`, this machine) after the fixes and the bug closing, exit 0:

```text
QUALITY GATE SUMMARY
------------------------------------------------------------
uv-lock            PASS          0.1s
ruff-check         PASS          0.1s
ruff-format        PASS          0.1s
mypy               PASS          0.3s
pytest             PASS         10.4s
web-lint           PASS          1.7s
web-typecheck      PASS          1.8s
web-test           PASS          2.2s
web-build          PASS          2.0s
repo-hygiene       PASS          0.1s
------------------------------------------------------------
RESULT: PASS (10/10) in 19.4s
```

| Check | Result |
| ----- | ------ |
| C-1   | `git diff -U0`: the added empty lines are 1 in the plan, 1 in `P0.07.md`, and 3 in `P0.06.md` (2 are this task's, 1 is the blank line after the BUG-0031 note of X.07); no other X.11 hunk in those three files |
| C-2   | `getDiagnostics` (warnings and errors) before the fixes: `P0.07.md` MD022; X.10 and X.11 (24 warnings); after the fixes the global list is `[]` and the URI checks of `P0.06.md`, the plan, `P0.07.md`, `X.10.md`, `X.11.md`, `X.07.md`, `P0.05.md`, `BUGS.md`, `DECISIONS.md`, `CHANGELOG.md`, `TASK_STATUS.md` return no diagnostics |
| C-3   | a grep of `Docs/` for the maintainer's sentence returns nothing (this row once held the grep pattern itself, which was the one hit; reworded in X.12); DEC-0015 splits into 6 columns and keeps the decision, the residual risk and the source |
| C-4   | `BUGS.md`: before the closing, 3 summary rows with a status other than CLOSED (BUG-0032..0034; BUG-0035 was added to them); after, none; next free ID BUG-0036 |
| C-5   | gate 10/10 above; `git status`: the files of §2 plus the earlier uncommitted X.07 / X.10 work; no `src/`, `tests/`, `tools/` file; nothing committed |

## 6. Self-review

- Files reviewed (`git diff` and a re-read after the last edit): `P0.06.md`, `P0.07.md`, `IMPLEMENTATION_PLAN_V1.md`,
  `DECISIONS.md`, `X.10.md`, `X.11.md`, `BUGS.md`, `TASK_STATUS.md`, `CHANGELOG.md`.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ (each warning is gone, checked by the tool and not only by eye) ·
  edge cases ☑ (blank lines go outside the fenced evidence; the "+" fix keeps the sentence, only the line break moved) ·
  no fabricated data ☑ (the warning counts are the tool's list, one count that I had wrong was corrected) · errors
  surfaced ☑ (my own warnings were registered, not just patched) · tests cover criteria ☑ (documentation task:
  C-1..C-5 and the gate) · no personal data ☑ · docs updated ☑.
- Findings: BUG-0035 (my own new files; found by this task's verification, fixed). Also fixed in place while writing
  it: an MD038 warning in the BUG-0035 text and a wrong count in it. Lesson applied: call `getDiagnostics` for every
  new document before closing its task.
- Left open at the time (the maintainer had named only the DEC-0015 quote): other places that quote the maintainer's
  words verbatim, 12 lines in 5 files by the grep used then. *(Closed 2026-11-15 by X.12: the maintainer asked to cut
  them all; a wider search found more places than that grep, and all were cut.)*

## 7. Bugs

| Bug ID   | Severity | Status  | Note |
| -------- | -------- | ------- | ---- |
| BUG-0032 | S3       | CLOSED  | fixed by this task |
| BUG-0033 | S3       | CLOSED  | fixed by this task |
| BUG-0034 | S3       | CLOSED  | found by the check at the start of this task; fixed by this task |
| BUG-0035 | S3       | CLOSED  | found while verifying this task (warnings in my own new files X.10 / X.11); fixed by this task |

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass (gate 10/10 PASS, `getDiagnostics` clean)
- [x] No open S1/S2 bug from this task; no open bug at all in `BUGS.md`
- [x] TASK_STATUS.md updated (X.11 DONE)
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated (DEC-0015 quote cut); README needs no change
- [x] ~~Open, maintainer: whether to cut the other verbatim chat quotes~~ — cut in X.12 (2026-11-15)
