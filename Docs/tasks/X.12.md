# X.12 — Cut every verbatim quote of the maintainer's chat words from the logs

| Field             | Value                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                       |
| Owner             | agent (Claude Code)                                                                     |
| Phase             | Ad-hoc (documentation only)                                                             |
| Estimate          | 0.15 day                                                                                |
| Depends on        | X.11 DONE (checked 2026-11-15)                                                          |
| Plan confirmed by | Maintainer, 2026-11-15: asked in the conversation to cut all of them                    |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                 |

## 1. Analysis

**Goal:** the decision log, task files and tracking files record that the maintainer approved, asked or delegated,
with the date, but not their literal words. The facts stay; only the quotation goes. The maintainer asked for this
for one decision (X.11) and then for all places.

**Why a wider search was needed:** the grep used at the end of X.11 looked for five phrases and found 12 lines in
5 files. A search for any quoted text with Vietnamese letters, and for "answered / asked / said" next to a quotation,
found more places: the "Plan confirmed by" rows of five older tasks, and X.11 itself (its check commands and its list
of phrases contained the words). Quotations of the plan, of UI strings and of test placeholders are not chat words and
stay.

**Inventory (file, kind of quote; the text is not repeated here):**

| File | Place | What was quoted |
| ---- | ----- | --------------- |
| `Docs/tasks/X.02.md` | header, line 10 | one-word approval of a proposal |
| `Docs/tasks/X.03.md` | header, line 10 | approval of a proposal |
| `Docs/tasks/X.05.md` | header, line 10 | the request to review the listed repositories |
| `Docs/tasks/X.06.md` | header, line 10 | the request to clone, update the docs and commit |
| `Docs/tasks/P0.04.md` | header, line 10 | the request to add the remote and commit (the quote also holds the remote URL with the account name) |
| `Docs/tasks/P0.06.md` | line 10 (3 quotes), line 386, line 658 | a request to fix, the reply to the list of open items, the name of one item of that list |
| `Docs/tasks/P0.07.md` | line 10 (3 quotes), 278, 502, 507, 515 | a request to start fixing, the reply to the list, the delegation of one choice |
| `Docs/tasks/X.07.md` | line 10, line 37 | the request to do the list, the instruction not to do the other work |
| `Docs/tracking/TASK_STATUS.md` | X.07 row, P0.07 row | the same request and the same reply |
| `Docs/tracking/DECISIONS.md` | DEC-0014 | the delegation of the hip-height choice |
| `Docs/tasks/X.11.md` | C-3 rows (two), §6 bullet on open quotes | check commands holding the DEC-0015 sentence, a list of the phrases |

**Not touched (not chat words):** quotations of `IMPLEMENTATION_PLAN_V1.md`, `AGENTS.md`, `TECH_WORKFLOW`, the UI
strings of P8.02, the test placeholder names of P0.06, `X.10.md` check patterns for the words "machine B". The grep
patterns in `X.10.md` quote the plan's own wording, not the maintainer's.

**In scope:**

1. Replace each quotation by a neutral statement of the fact with its date (approved, requested, delegated,
   accepted the defaults). Remove the account-name URL from the P0.04 header (the remote is recorded elsewhere).
2. Reword the two C-3 rows and the open-quotes bullet of X.11 so that no chat word remains; mark that bullet closed.
3. Close the open items that refer to these quotes: X.11 §8, the X.11 row of `TASK_STATUS.md`, a note under the X.11
   entry of `CHANGELOG.md`.
4. `CHANGELOG.md` entry; `TASK_STATUS.md` row.

**Out of scope:**

- Git history (commit messages) and the conversation itself. No commit, no code.
- `/usage` and skill settings: not touched.
- A rule in `AGENTS.md` or a DEC about not quoting chat: not asked; offered in the report.

**Constraints that apply:** AGENTS.md §4.3 (append-only history): this is a deliberate removal at the maintainer's
request, recorded here without repeating the words. §9.5 / privacy: no names or account handles in the docs where a
neutral statement is enough.

**Risks:**

| #  | Risk | Mitigation |
| -- | ---- | ---------- |
| R1 | A replacement changes the meaning (for example "confirmed" becomes unconditional) | Each new text keeps the old facts: who, what, date, and the condition (defaults accepted, delegated, commit asked or not) |
| R2 | A quote survives because the search missed a form (single quotes, curly quotes, no accents) | Verify with several greps: the phrase list, any quotation with Vietnamese letters, any quotation after answered / asked / said / requested; list what remains and why it is not chat |
| R3 | The new text itself repeats the words (this file, CHANGELOG, TASK_STATUS) | The verification greps run over `Docs/` including this file |
| R4 | Another writer overwrites a file while the script runs | Re-read the regions first; the script asserts one match per replacement and writes only when all match; `git diff --stat` at the end |

## 2. Plan

**Files to create / modify:** the files of the inventory, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/TASK_STATUS.md`,
`Docs/tasks/X.12.md` (new).

**Implementation steps:**

1. Re-read this file and the regions against the current files (§3).
2. One script outside the repository (scratchpad): a table of (file, old text, new text, expected count); it reads every
   file, asserts the counts, and writes all files only if every assertion holds.
3. Hand edits for the X.11 closing items, TASK_STATUS and CHANGELOG.
4. Verification greps, `getDiagnostics` on every changed document, the gate, `git diff` review.
5. Close.

**Test plan:** documentation task, manual checks.

| Check | What it verifies |
| ----- | ---------------- |
| C-1 | Phrase grep over `Docs/` and the root `*.md` files (the phrase list is in the scratch script, not in the repo): no hit |
| C-2 | Any quotation with Vietnamese letters in `Docs/tasks` and `Docs/tracking`: the remaining ones are plan / UI / placeholder quotations, listed in §5 |
| C-3 | Any quotation after answered / asked / said / wrote / requested: none is a maintainer quotation |
| C-4 | `getDiagnostics` (warnings and errors): empty; every changed document checked by URI |
| C-5 | Gate 10/10 PASS; `git diff`: the replaced text keeps who, what, date, condition |

**Acceptance criteria:**

- [x] AC1 No verbatim chat quote of the maintainer remains in `Docs/` (C-1..C-3), and none in this file.
- [x] AC2 Each replaced statement keeps its facts: who, what, date and condition (C-5).
- [x] AC3 The open items about the quotes are closed in X.11, TASK_STATUS and CHANGELOG.
- [x] AC4 Diagnostics empty, gate 10/10 PASS, only planned files changed, no commit (C-4, C-5).

**Impact / rollback:** documentation only. Rollback per hunk (the files hold earlier uncommitted work).

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK. Re-read the five older headers (X.02, X.03, X.05, X.06, P0.04) and the lines of the
  inventory against the current files; the strings are as in the inventory. `git status` shows 12 entries, all earlier
  uncommitted documentation work (X.07, X.10, X.11, BUG entries) plus this file; no `src/`, `tests/`, `tools/` change.
  No change to the plan.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1    | 2026-11-15 | Wider search than the X.11 grep (phrase list, quotations with Vietnamese letters, quotations after answered / asked / said): found the five older headers and X.11 itself in addition to the 12 lines of X.11. Task file, TASK_STATUS row, plan re-read (§3). |
| 2    | 2026-11-15 | One script outside the repo (scratchpad): 25 replacements in 11 files, one count assertion each, files written only after every assertion held. It passed on the first run. |
| 3    | 2026-11-15 | The two C-3 rows and the open-quotes bullet of X.11 reworded and closed; X.11 §8 item struck through; TASK_STATUS X.11 row; note under the X.11 entry of CHANGELOG; CHANGELOG entry for X.12. |
| 4    | 2026-11-15 | Verification greps, `getDiagnostics` (global list and the five older headers by URI), gate, re-reading of every changed line (§5, §6). No deviation from the plan. |

## 5. Verification

Full gate (`tools\check.ps1`, this machine) after the replacements, exit 0: **RESULT: PASS (10/10) in 17.4s**. The
gate does not read the documents' wording; the checks below do.

| Check | Result |
| ----- | ------ |
| C-1   | Phrase grep (case-insensitive, accent forms and the unaccented forms included) over every `*.md` of the workspace: no chat quote. Four hits, none is a chat quote: a line of a third-party notes file in `repos/` (a substring of an ordinary Vietnamese word), two sentences of the corrected master plan (ordinary text), and the `git remote add` command in the P0.04 plan step (a command, not a quotation) |
| C-2   | Quotations with Vietnamese letters in `Docs/tasks` and `Docs/tracking`: what remains quotes the plan, the AGENTS / TECH_WORKFLOW text, a UI string of P8.02, the placeholder names of the P0.06 tests, or table column names; none is a maintainer quotation |
| C-3   | Quotations after answered / asked / said / wrote / requested / confirmed / approved: two hits, both quote a document (the TECH_WORKFLOW stack row in BUG-0002, the word "Reopened" in P0.05), not the maintainer |
| C-4   | `getDiagnostics` (warnings and errors): the global list is `[]`; X.02, X.03, X.05, X.06, P0.04 and this file checked by URI, no diagnostics |
| C-5   | Each replaced statement re-read in the file: the header rows of X.02, X.03, X.05, X.06, P0.04; P0.06 lines 10, 386, 658; P0.07 lines 10, 278, 502, 507, 515; X.07 lines 10 and 36-37; TASK_STATUS (X.07 reason, P0.07 evidence, X.11 evidence); DEC-0014; X.11 C-3 rows, bullet and §8 item. Who, what, date and condition are kept (defaults accepted, delegated to the agent's recommendation, commit asked or not) |

## 6. Self-review

- Files reviewed (re-read after the script and the hand edits): the eleven files of the inventory, `CHANGELOG.md`,
  `TASK_STATUS.md`, this file.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ (25 replacements, each asserted, each re-read) · edge cases ☑ (a string
  that occurs twice in a file was replaced twice with a count check; text that only looks similar, such as plan
  sentences and a third-party notes line, was left alone) · no fabricated data ☑ (the new sentences state only what the
  old ones said, without the wording) · errors surfaced ☑ · tests cover criteria ☑ (documentation task: C-1..C-5 and the
  gate) · no personal data ☑ (the account-name URL left the P0.04 header) · docs updated ☑.
- Findings: none. The first search (X.11) had been too narrow and missed five older headers; the wider search is the
  one recorded in §1.
- Not covered: the commit messages in git history (not changed, not checked for quotations) and the conversation
  itself. The P0.04 plan step and the P0.04 row of TASK_STATUS still name the remote (a project fact, not a quotation).
  No rule against quoting was added to `AGENTS.md` or `DECISIONS.md`: not asked, offered in the report.

## 7. Bugs

None found in this task.

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass (gate 10/10 PASS, `getDiagnostics` clean)
- [x] No open S1/S2 bug from this task; no open bug in `BUGS.md`
- [x] TASK_STATUS.md updated (X.12 DONE)
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md: no change needed
