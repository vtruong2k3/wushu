# X.07 — Close the P0 review leftovers: BUG-0030, BUG-0031, unregistered P0.05 follow-ups

| Field             | Value                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                                 |
| Owner             | agent (Claude Code)                                                                               |
| Phase             | Ad-hoc (documentation only)                                                                       |
| Estimate          | 0.25 day                                                                                          |
| Depends on        | none; P0.05, P0.06, P0.07 are DONE (TASK_STATUS, checked 2026-11-15)                              |
| Plan confirmed by | Not required (< 1 day, no schema or contract change). Maintainer asked to do the list, 2026-11-15 |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                           |

## 1. Analysis

**Goal:** remove the documentation defects found by the Phase 0 review, so that the tracking files say what is true,
and give the two follow-ups that P0.05 promised an ID.

**Why this task exists:** the maintainer asked to do the open items of the P0 review. Work without a task ID gets an
ad-hoc task first (CLAUDE.md, AGENTS.md §2.2). The bugs already have IDs (§3); the register of follow-ups does not.

**In scope:**

1. BUG-0030: statements "local, not pushed / on branch `feat/P0.07-synthetic-skeleton`" in `TASK_STATUS.md` (P0.06 and
   P0.07 rows), `CHANGELOG.md` (the P0.07 and the BUG-0019 entries) and `Docs/tasks/P0.07.md` §8. Fact checked
   2026-11-15: `git ls-remote origin main` = `git rev-parse HEAD` = `22d307823a7b`, working tree clean before this task;
   `84c9bff`, `b060835` and `3bb05c1` are ancestors of `main`.
2. BUG-0031: (a) `BUGS.md` BUG-0009 detail, (b) `Docs/tasks/P0.06.md` §2.5 unticked AC1–AC11.
3. Register the follow-ups of P0.05 §1 / §6 as TODO rows: **X.08** GitHub Actions CI for the gate, **X.09** `mypy` on
   `tests/` and `tools/`. (`pnpm e2e` is already P8.15.)

**Out of scope:**

- Running the gate on machine B (P0 acceptance): maintainer action, stays open. *(Dropped 2026-11-15, X.10, DEC-0015.)*
- Implementing X.08 / X.09: they are registered, not started. X.08 publishes a workflow to the remote and needs the
  maintainer's decision first (Q3 of P0.05).
- Any `/usage` finding and any change to the user's Claude Code settings or skills: paused on the maintainer's
  instruction, not part of this task.
- No code change, no commit (CLAUDE.md: commit only when asked).

**Finding made during the analysis (widens BUG-0031 (a)):** the BUG-0009 detail is not only stale, it lost content.
`Docs/tasks/P0.05.md` §9.1 refers to a "Re-review 2026-11-15" section of BUG-0009 with the revised fix plan. That
section is not in `BUGS.md`, and it is not in any commit either: `git show 4cee272:Docs/tracking/BUGS.md` and the
other commits have no such text, so it was lost in the uncommitted overwrite (same mechanism as BUG-0012 / BUG-0013 /
BUG-0027). It cannot be restored verbatim. It is **reconstructed** from sources that survive, and marked as such:

| Fact to restore                                   | Source                                                                                   |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Why the 2026-11-14 fix was incomplete             | `P0.05.md` §9.2 F-2 (PermissionError/EIO exit 1 with a traceback; ELOOP, winerror 21/123/1921 skip R11 silently; cited tests do not exercise a stat error) |
| The final fix                                     | `taiji_ai/tools/repo_hygiene.py:170-191, 224-229` (read 2026-11-15): one `stat()` per file in `collect_entries()`; `FileNotFoundError`/`NotADirectoryError` → size `None`; other `OSError` → `stat_errors`; `main()` prints `Error: cannot stat <path>: <reason>` and returns 2, never 0 or 1 |
| Regression tests                                  | `tests/unit/test_repo_hygiene.py` `test_bug_0009_*` (7 cases; ran 2026-11-15: 7 passed); 4 red before the fix (`P0.05.md` §5, §9.4 F-2) |
| Closed date / task                                | `P0.05.md` §7 and §8, CHANGELOG 2026-11-15 P0.05 entry: CLOSED 2026-11-15 in P0.05 rework 2 |

**Existing files read:** `AGENTS.md`, `CLAUDE.md`, `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`,
`Docs/tasks/{P0.05,P0.06,P0.07,_TEMPLATE}.md`, `taiji_ai/tools/repo_hygiene.py`, `taiji_ai/README.md`.

**Constraints that apply:** AGENTS.md §4.3 history is append-only (superseded text is struck through or followed by a
dated note, never deleted); stale docs are S3 bugs; no absolute personal paths in docs; a bug record needs ID, fix,
verification; §5.1 nothing fabricated: the reconstructed BUG-0009 text says that it is reconstructed and from where.

**Unknowns / risks:**

| #  | Risk                                                                                                     | Mitigation                                                                                           |
| -- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| R1 | A second writer (Codex processes are running) overwrites a tracking file again (BUG-0027)                | Re-read each file right before editing; the Edit tool refuses stale files; `git diff --stat` at the end to see exactly which files changed; hash snapshot of the edited files after the last edit |
| R2 | Ticking P0.06 §2.5 without evidence would repeat the over-claiming that the reviews found                | Tick only with the evidence of §8 (close-out) plus today's re-run (gate 10/10, `test_logs.py` and API tests pass), and say so in the note |
| R3 | The recorded hash `22d3078` is out of date once this task is committed                                    | Write "contained in `origin/main` (`22d3078` on 2026-11-15)", not "`origin/main` is `22d3078`"         |

## 2. Plan

**Files to create / modify:**

| File                                   | Change                                                                                                                          |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `Docs/tasks/X.07.md`                   | new (this file)                                                                                                                 |
| `Docs/tracking/TASK_STATUS.md`         | rows X.07 (status per step), X.08, X.09 (TODO); P0.06 and P0.07 rows: "in `main`, pushed" instead of "local, not pushed"        |
| `Docs/tracking/CHANGELOG.md`           | new X.07 entry at the top; dated note appended under the P0.07 rework entry and under the BUG-0019 entry (old text kept)         |
| `Docs/tasks/P0.07.md`                  | dated note after the §8 line "committed on a branch … not pushed" (old text kept)                                               |
| `Docs/tasks/P0.06.md`                  | §2.5 AC1–AC11 ticked, one dated note under the list                                                                            |
| `Docs/tracking/BUGS.md`                | BUG-0009 detail: Status CLOSED, reconstructed re-review + final fix + verification + history (old Fix line kept, struck); BUG-0031 text widened; BUG-0030 and BUG-0031 → CLOSED with Fix / Verified |

**Implementation steps:**

1. Re-read this file and the target regions of every file above against the current state (§3).
2. BUG-0030: TASK_STATUS rows, CHANGELOG notes, P0.07 §8 note.
3. BUG-0031 (b): tick P0.06 §2.5 with the note.
4. BUG-0031 (a): restore the BUG-0009 detail as in §1 table; update the BUG-0031 description (content was lost, not only
   stale).
5. Register X.08 and X.09 in TASK_STATUS (TODO) with reason and source.
6. Run the gate (docs only, but it is the mandatory check and runs repo-hygiene); re-run `git ls-remote origin main`.
7. Self-review: re-read `git diff` of every changed file; confirm that only the files above changed.
8. Close: BUGS.md (BUG-0030, BUG-0031 → CLOSED), TASK_STATUS (X.07 DONE), CHANGELOG entry, §8 of this file.

**Test plan:** documentation task, no new automated test (BUGS.md regression-test column says "manual check list").
Manual checks, each with its command or reading:

| Check | What it verifies                                                                                                    |
| ----- | ------------------------------------------------------------------------------------------------------------------- |
| C-1   | `Grep "local, not pushed"` over `Docs/` and `taiji_ai/*.md` finds only the preserved historical text, each followed by a dated note |
| C-2   | `git ls-remote origin main` is a descendant of / equal to the hash written in the notes (`git merge-base --is-ancestor 84c9bff <remote hash>`) |
| C-3   | BUG-0009 detail: Status CLOSED, matches the summary row and `P0.05.md` §7; the cited test names exist (`pytest --collect-only -k bug_0009`) |
| C-4   | P0.06 §2.5: 11 ticked boxes, note present; P0.06 §8 text unchanged                                                  |
| C-5   | TASK_STATUS has rows X.07, X.08, X.09; the P0 summary table is untouched (ad-hoc tasks are not counted there)       |
| C-6   | Full gate 10/10 PASS; `git diff --stat` lists only the files of the table above                                    |

**Acceptance criteria:**

- [x] AC1 No tracking or task document claims that P0.05–P0.07 or the Q7 decision are unpushed or only on the branch,
      except preserved history followed by a dated correction (C-1, C-2).
- [x] AC2 BUG-0009 detail is consistent with the summary table, P0.05 and the code, and says which part is
      reconstructed (C-3).
- [x] AC3 P0.06 §2.5 acceptance boxes are ticked with a dated, evidence-based note (C-4).
- [x] AC4 X.08 and X.09 exist in TASK_STATUS as TODO with a reason; nothing of them is implemented (C-5).
- [x] AC5 Gate 10/10 PASS; only the planned files changed (C-6); no commit made.
- [x] AC6 BUG-0030 and BUG-0031 CLOSED with Fix and Verified lines; BUGS.md "Next free ID" still correct.

**Impact / rollback:** documentation only. Rollback = `git checkout` of the listed files (all tracked, clean at start
except `BUGS.md`, which already carries the BUG-0030/0031 entries of the review).

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK. Re-read the plan against the current state: `git status` shows only `BUGS.md` (the
  BUG-0030/0031 entries), `TASK_STATUS.md` (rows X.07–X.09, added in this task) and this new file; `origin/main` is
  `22d307823a7b` and `84c9bff`, `b060835`, `3bb05c1` are its ancestors; the stale text is at `CHANGELOG.md:40,52`,
  `TASK_STATUS.md` rows P0.06 / P0.07, `P0.07.md:502` exactly as planned. No change to the plan.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1    | 2026-11-15 | Plan re-read (§3). Before it, the analysis found that the BUG-0009 re-review text is lost, not only stale (§1); BUG-0031 widened. |
| 2    | 2026-11-15 | BUG-0030: TASK_STATUS P0.06 / P0.07 rows, dated notes under the two CHANGELOG entries and under `P0.07.md` §8. **Deviation:** the rows say "contained in `origin/main`, checked 2026-11-15" without a hash (risk R3), the BUG-0030 fix plan had named `22d3078`; recorded in the BUG-0030 Fix line. |
| 3    | 2026-11-15 | BUG-0031 (b): `P0.06.md` §2.5 AC1–AC11 ticked (`sed` on lines 321–337 only, `git diff` shows exactly 11 changed lines) and a dated note added. |
| 4    | 2026-11-15 | BUG-0031 (a): BUG-0009 detail: Status CLOSED, old Fix / Verified relabelled and kept, re-review rebuilt (flagged as reconstructed), rework-2 fix, verification, history. Facts read from `repo_hygiene.py:170-229`; the 7 tests ran (7 passed). |
| 5    | 2026-11-15 | X.08 (GitHub Actions CI) and X.09 (`mypy` on `tests/` and `tools/`) registered as TODO in TASK_STATUS; nothing implemented. |
| 6    | 2026-11-15 | Gate 10/10 PASS; checks C-1..C-6 (§5). |
| 7    | 2026-11-15 | Self-review of the `git diff` of every changed file (§6). Found BUG-0032 (pre-existing MD031 in `P0.06.md`, registered, not fixed here). |
| 8    | 2026-11-15 | BUG-0030 and BUG-0031 CLOSED with Fix / Verified; TASK_STATUS and CHANGELOG updated; this file closed. |

## 5. Verification

Full gate (`tools\check.ps1`, machine A, after the last code-free edit of the working files), exit 0:

```text
QUALITY GATE SUMMARY
------------------------------------------------------------
uv-lock            PASS          0.1s
ruff-check         PASS          0.1s
ruff-format        PASS          0.1s
mypy               PASS          0.3s
pytest             PASS          6.7s
web-lint           PASS          1.6s
web-typecheck      PASS          1.5s
web-test           PASS          2.0s
web-build          PASS          1.8s
repo-hygiene       PASS          0.1s
------------------------------------------------------------
RESULT: PASS (10/10) in 14.9s
```

Manual checks of §2:

| Check | Result |
| ----- | ------ |
| C-1   | `grep "not pushed"` over `Docs/`, `taiji_ai/README.md`, `CONTRIBUTING.md`: `CHANGELOG.md` lines 40 and 54 and `P0.07.md` §8 (preserved history, each followed by a dated note); `BUGS.md` and this file (they quote the defect). `TASK_STATUS.md`: none |
| C-2   | `git ls-remote origin main` = `22d307823a7b`; `git merge-base --is-ancestor` is true for `84c9bff` and `b060835` |
| C-3   | BUG-0009 detail Status CLOSED, as in the summary row and `P0.05.md` §7; `pytest tests/unit/test_repo_hygiene.py -k bug_0009`: 7 passed |
| C-4   | `P0.06.md` §2.5: 11 ticked boxes (`git diff` 11 changed lines), the note present; §8 unchanged |
| C-5   | `TASK_STATUS.md` has the rows X.07, X.08, X.09; the P0 summary table is untouched |
| C-6   | `git status`: only `P0.06.md`, `P0.07.md`, `BUGS.md`, `CHANGELOG.md`, `TASK_STATUS.md` modified and `X.07.md` new (123 insertions, 18 deletions before the close-out edits); no `src/`, `tests/` or `tools/` file; nothing committed |

## 6. Self-review

- Files reviewed (`git diff` and a re-read after the last edit): `Docs/tasks/P0.06.md`, `Docs/tasks/P0.07.md`,
  `Docs/tracking/BUGS.md`, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/TASK_STATUS.md`, this file.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ (every AC has a check in §5) · edge cases ☑ (history kept, notes
  appended, no deletion; the hash is not written as "the current remote") · no fabricated data ☑ (the rebuilt BUG-0009
  re-review is flagged as reconstructed and cites its sources; the tests and the remote hash were run, not copied) ·
  errors surfaced ☑ (the lost section is reported, not hidden) · tests cover criteria ☑ (documentation task: manual
  checks C-1..C-6 plus the gate) · no personal data ☑ (no absolute paths, names or emails written) · docs updated ☑.
- Findings: (1) the BUG-0030 fix deviates from its plan (no hash in TASK_STATUS): recorded in the bug's Fix line.
  (2) BUG-0032: two MD031 warnings in `P0.06.md` §5 that exist in HEAD; registered with a fix plan, not fixed here.
  (3) The BUG-0009 re-review cannot be restored verbatim; the reconstruction says so.
- Not covered (stays open, maintainer; *dropped 2026-11-15, X.10, DEC-0015*): P0 acceptance run of the gate on machine B. A second writer (Codex processes) is
  still running on the machine: the six files above were re-read after the last edit and the diff showed only the
  planned changes.

## 7. Bugs

| Bug ID   | Severity | Status  | Note                                                         |
| -------- | -------- | ------- | ------------------------------------------------------------ |
| BUG-0030 | S3       | CLOSED  | fixed by this task                                           |
| BUG-0031 | S3       | CLOSED  | fixed by this task; widened: BUG-0009 re-review text was lost |
| BUG-0032 | S3       | PLANNED | found during this task (pre-existing MD031 in `P0.06.md` §5); registered, not part of this task |

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass (gate 10/10 PASS)
- [x] No open S1/S2 bug from this task (BUG-0030, BUG-0031 CLOSED; BUG-0032 is S3, pre-existing, planned)
- [x] TASK_STATUS.md updated (X.07 DONE, X.08 / X.09 TODO)
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md: no change needed (no module state or decision changed)
- [x] ~~Open, maintainer: X.08 needs the maintainer's go before it starts~~ — deferred by the maintainer 2026-11-15, X.13 (~~P0 acceptance needs the gate on machine B~~:
      dropped 2026-11-15, X.10, DEC-0015)
