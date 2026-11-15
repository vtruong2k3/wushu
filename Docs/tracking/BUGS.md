# Bug Register

Rules: `AGENTS.md` §3. IDs are sequential (`BUG-NNNN`), never reused. Every bug must have a fix plan.
Severity: **S1** critical · **S2** major · **S3** minor.
Lifecycle: `OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED` (or `WONT_FIX` with maintainer approval).

**Next free ID:** `BUG-0036`

## Summary

| ID       | Title                                                                                                                      | Sev | Status | Found in                                                                   | Fix task | Regression test                                                  | Opened     | Closed     |
| -------- | -------------------------------------------------------------------------------------------------------------------------- | --- | ------ | -------------------------------------------------------------------------- | -------- | ---------------------------------------------------------------- | ---------- | ---------- |
| BUG-0035 | New task files `X.10.md` and `X.11.md` have markdownlint warnings: X.10 line 19 starts with a plus sign (read as a list item: MD032, and MD004 on its 18 dash lists), X.11 has five bold-only labels (MD036); written by this agent and not checked with the IDE problems list | S3 | CLOSED | X.11 verification (`getDiagnostics`), `Docs/tasks/X.10.md:19`, `Docs/tasks/X.11.md` | X.11 | IDE diagnostics for both files show no warning (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0034 | `Docs/tasks/P0.07.md` has a markdownlint MD022 warning: the heading "### Rework evidence" (line 338) has no blank line above it; in HEAD since the P0.07 rework commit `84c9bff` | S3 | CLOSED | X.11 check of the IDE problems list, pre-existing in HEAD | X.11 | IDE diagnostics for `Docs/tasks/P0.07.md` show no MD022 (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0033 | `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3 has a markdownlint MD032 warning (the list of the three F-SYN functions starts right after its paragraph, no blank line; about line 409); present in HEAD | S3 | CLOSED | X.10 edit of the plan (IDE diagnostics), pre-existing in HEAD | X.11 | IDE diagnostics for `Docs/IMPLEMENTATION_PLAN_V1.md` show no MD032 (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0032 | `Docs/tasks/P0.06.md` §5 has two markdownlint MD031 warnings (fenced code blocks without blank lines around them, "Step 9" evidence, about lines 437–452); present since the P0.06 commit | S3 | CLOSED | X.07 edit of P0.06.md (IDE diagnostics), pre-existing in HEAD | X.11 | IDE diagnostics for `Docs/tasks/P0.06.md` show no MD031 (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0031 | Task-file leftovers: BUG-0009 detail section is stale (Status FIXED, describes the first incomplete fix) and P0.06 §2.5 AC1–AC11 boxes are unticked while §8 says met | S3 | CLOSED | P0 review (2026-11-15), `Docs/tracking/BUGS.md` BUG-0009 detail, `Docs/tasks/P0.06.md` §2.5 | X.07 | Manual check list (BUG-0031 fix plan); `pytest -k bug_0009` (7 passed) | 2026-11-15 | 2026-11-15 |
| BUG-0030 | Docs say the P0.06/P0.07 commits are "local, not pushed" on branch `feat/P0.07-synthetic-skeleton`; they are in `main` and pushed (`origin/main` = `22d3078`) | S3 | CLOSED | P0 review (2026-11-15), `Docs/tracking/CHANGELOG.md:40,52`, `Docs/tracking/TASK_STATUS.md` P0.06/P0.07 rows, `Docs/tasks/P0.07.md` §8 | X.07 | Manual check list (BUG-0030 fix plan): `grep "not pushed"`, `git merge-base --is-ancestor` | 2026-11-15 | 2026-11-15 |
| BUG-0029 | SYN-12 `absent_s` that contains no frame raises `IndexError` instead of `ValueError` naming the parameter | S3 | CLOSED | P0.07 rework self-review, `taiji_ai/tests/helpers/synth.py` `build_syn_12` | P0.07 | `tests/unit/test_synth.py::test_t_syn_04_invalid_values_pair_and_scene[…absent_s…]` (red first; MN21) | 2026-11-15 | 2026-11-15 |
| BUG-0028 | SYN-07 accepts `fps` (inherited from the common defaults) and ignores it; the rework of BUG-0020 left one accepted-but-unused parameter | S3 | CLOSED | P0.07 rework self-review, `taiji_ai/tests/helpers/synth.py` registry | P0.07 | `tests/unit/test_synth.py::test_t_syn_04_every_accepted_parameter_changes_the_output[SYN-01..12]` + `…unknown_parameter…` (SYN-07 case red first; MN22) | 2026-11-15 | 2026-11-15 |
| BUG-0027 | P0.07 task file and TASK_STATUS overwritten with the pre-review versions at 18:00:11 (review §9 and the BUG-0019 note lost, P0.07 shown DONE again); a second writer is still active | S3 | CLOSED | P0.07 rework, `Docs/tasks/P0.07.md`, `Docs/tracking/TASK_STATUS.md` (mtime 2026-11-15 18:00:11-15) | P0.07 | Manual check list (P0.07 §9 present, TASK_STATUS rows) done 2026-11-15 | 2026-11-15 | 2026-11-15 |
| BUG-0026 | P0.07 docs and evidence overstate the work: SYN-07 "exact speeds", SYN-09 "pinhole / Appendix B", "TypeError raised", "10 L/R pairs", tolerance-change rule deleted, unverified maintainer confirmation | S3 | CLOSED | P0.07 review, `Docs/tasks/P0.07.md`, `IMPLEMENTATION_PLAN_V1.md` §14.3 | P0.07 | Manual check list (plan §14.3, DEC-0013, task file) done 2026-11-15 | 2026-11-15 | 2026-11-15 |
| BUG-0025 | SYN-06 gaps: default short gap lies inside a pause; gap past the clip end accepted as "short"; a gap hitting no frame silently dropped; 150 ms hard-coded | S3 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:245-318, 771-780` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn06_*` and `…invalid_values_name_the_parameter[SYN-06…]` (MN11, MN12, MS5) | 2026-11-15 | 2026-11-15 |
| BUG-0024 | SYN-12: detections never shuffled (slot = identity), seed ignored, `crossing_interval` (1.8–2.2 s) falls while the target is absent | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:1055-1128` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn12_*` (MS4, MN9, MN10, MN18) | 2026-11-15 | 2026-11-15 |
| BUG-0023 | SYN-10 query is not the reference re-timed: phase uses `t_ref/duration` vs `t/t_sec[-1]`, up to 4.4 px apart | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:977-995` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn10_*` (MS2, MN7, MN8) | 2026-11-15 | 2026-11-15 |
| BUG-0022 | SYN-09 truth wrong: `expected_hA` in px, not `y_H/Λ_take`; `range_A` (px) compared with `range_B` (Λ); feet fixed, not a pinhole model; with Appendix B formulas B is less stable than A | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:895-967` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn09_pinhole_truth_follows_appendix_b[0.6, 1.0, 1.3]` (MS3, MN5, MN6) | 2026-11-15 | 2026-11-15 |
| BUG-0021 | Tempo truth is not from a continuous model: SYN-05 speed = `np.gradient` of the sampled poses (the metric's own method, non-zero inside pauses, mean not median); SYN-07 has no speed truth | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:359-409, 728-738, 806-843` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn05_*`, `…syn07_vfr_truth`, `…group_speed_is_the_median…` (MS1, MN2–MN4) | 2026-11-15 | 2026-11-15 |
| BUG-0020 | `make_sequence` / `make_pair` / `make_scene` silently ignore unknown or misspelled parameters (defaults used) | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:1230-1272` | P0.07 | `tests/unit/test_synth.py::test_t_syn_04_unknown_parameter_is_rejected_by_every_api` (MN1) | 2026-11-15 | 2026-11-15 |
| BUG-0019 | P0.06 commit `4cee272` ships the stale 21-test `test_logs.py`; BUG-0018 was "fixed" by changing `posix_paths` to `True` so the stale tests pass (Windows request lines like `GET /home/settings` redacted again) | S2 | CLOSED | P0.07 review, commit `4cee272`, `taiji_ai/src/taiji_ai/logs.py:125,139,174` | P0.06 follow-up | `tests/unit/test_logs.py::test_t_core_01e_posix_syntax_default_follows_the_platform` + the restored 41-test file (red first; M1–M9) | 2026-11-15 | 2026-11-15 |
| BUG-0018 | `tests/unit/test_logs.py` overwritten again after P0.06 closed (41 → 21 tests, gate red); a second writer is editing the repo | S2 | CLOSED | P0.07 analysis, file mtime 2026-11-15 16:55:35 | P0.06 follow-up | `posix_paths: bool = True` in `logs.py`, ruff format; full gate 10/10 PASS | 2026-11-15 | 2026-11-15 |
| BUG-0017 | `run_log` writes no end marker when a run is cancelled (`KeyboardInterrupt`, `SystemExit`)                                 | S3  | CLOSED | P0.06 review, `taiji_ai/src/taiji_ai/logs.py:259`                         | P0.06    | `tests/unit/test_logs.py::test_t_core_01i_run_log_exception_closes_handler[exc0..2]` (2 red first; M7) | 2026-11-15 | 2026-11-15 |
| BUG-0016 | API logging tests leave root-logger and uvicorn-logger state behind for the rest of the pytest session                    | S3  | CLOSED | P0.06 review, `taiji_ai/tests/api/test_api_core.py` (T-CORE-01o/p, T-API-04b) | P0.06 | `tests/conftest.py::_logging_state_guard` (autouse; 3 errors red first; M8)          | 2026-11-15 | 2026-11-15 |
| BUG-0015 | `PathRedactor` drops known-root tails in `repr` form (`'<data><path>'`) and redacts non-paths (`/homepage`, `/users`, `/media/x`) | S3 | CLOSED | P0.06 review, `taiji_ai/src/taiji_ai/logs.py:76-85,126-129`            | P0.06    | `test_logs.py::test_t_core_01b_known_roots_keep_tail_in_repr_form`, `…01b_tail_of_known_root_does_not_hide_a_second_path`, `…01e_not_paths_left_unchanged` (M9)                       | 2026-11-15 | 2026-11-15 |
| BUG-0014 | `PathRedactor` leaves the name visible in UNC paths (share with space / non-ASCII / `c$`, non-ASCII server) and after an apostrophe | S2 | CLOSED | P0.06 review, `taiji_ai/src/taiji_ai/logs.py:75-79`                   | P0.06    | `test_logs.py::test_t_core_01a_*` (12 + 4 + 3 + 3 cases; 10 red first; M5a, M5b)                         | 2026-11-15 | 2026-11-15 |
| BUG-0013 | Tracking docs overwritten with stale copies: CHANGELOG lost the 2026-11-15 P0.05 entry; BUGS.md next free ID reset to `BUG-0010`; BUG-0008 detail reverted | S3 | CLOSED | P0.06 review, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/BUGS.md` | P0.06 | Manual check (fix plan item 4) done 2026-11-15; restores verbatim from the session transcript                                 | 2026-11-15 | 2026-11-15 |
| BUG-0012 | P0.05 rework-2 test files overwritten with older versions: BUG-0008 / BUG-0010 regression tests deleted, T-TOOL-05 commits again | S2 | CLOSED | P0.06 review, `taiji_ai/tests/contract/test_check_script.py`, `test_repo_hygiene_git.py` | P0.06 | `tests/contract/test_check_script.py` (9 tests, restored) incl. `test_bug_0010_*` and `test_t_tool_01_parse_check_detects_syntax_errors`            | 2026-11-15 | 2026-11-15 |
| BUG-0011 | `/api/health` returns (and logs) the absolute model-registry path; the user-profile folder name shows on the Status page    | S3  | CLOSED | P0.06 analysis, `taiji_ai/src/taiji_ai/api/app.py:32-33`                  | P0.06    | `tests/api/test_api_core.py::test_bug_0011_*` (red first, mutation-checked) | 2026-11-15 | 2026-11-15 |
| BUG-0010 | T-TOOL-03 tests the nested-run guard with a real gate run; a broken guard makes the gate recurse without bound              | S3  | CLOSED | P0.05 re-review, `taiji_ai/tests/contract/test_check_script.py:147-150` | P0.05    | `tests/contract/test_check_script.py::test_bug_0010_nested_guard_is_checked_before_preflight` (mutation-checked) | 2026-11-15 | 2026-11-15 |
| BUG-0009 | `repo_hygiene.py` silently sets `size = None` on OSError, masking unreadable files                                         | S3  | CLOSED | P0.05 rework analysis, `taiji_ai/tools/repo_hygiene.py:189-194`            | P0.05    | `tests/unit/test_repo_hygiene.py::test_bug_0009_*` (7 tests, 4 red before the fix) | 2026-11-14 | 2026-11-15 |
| BUG-0008 | `test_t_tool_01_check_script_parses_cleanly_in_powershell` passes `[ref]$null`, silently ignoring syntax errors            | S2  | CLOSED | P0.05 rework analysis, `taiji_ai/tests/contract/test_check_script.py:34-45` | P0.05    | `tests/contract/test_check_script.py::test_t_tool_01_parse_check_detects_syntax_errors` (negative control, mutation-checked) | 2026-11-14 | 2026-11-15 |
| BUG-0007 | `taiji_ai/README.md` Status says "Vitest 9"; the suite has 11 tests                                                        | S3  | CLOSED      | P0.05 analysis of `taiji_ai/README.md` Status table                        | P0.05    | Manual check: README Status rows carry no hard-coded test counts | 2026-11-14 | 2026-11-14 |
| BUG-0006 | `atomic_save_npz` silently drops an array named `allow_pickle`; object arrays are pickled into files `np.load` cannot read | S3  | CLOSED | P0.05 analysis (`mypy src`), `taiji_ai/src/taiji_ai/store/artifacts.py:51` | P0.05    | `tests/unit/test_core.py::test_bug_0006_*`                       | 2026-11-14 | 2026-11-14 |
| BUG-0005 | `apiGet` drops `Headers`-object headers and reports aborted requests as `network_error`                                    | S3  | CLOSED | P8.02 self-review of `taiji_ai/web/src/api/client.ts`                      | P8.02    | `tests/client.test.ts` (headers + abort cases)                   | 2026-11-14 | 2026-11-14 |
| BUG-0004 | `Settings.device` reads `TAIJI_DEVICE` at import time, not at construction                                                 | S3  | CLOSED | P8.01 analysis of `taiji_ai/src/taiji_ai/config.py:21`                     | P8.01    | New unit test: env set after import is honoured                  | 2026-11-14 | 2026-11-14 |
| BUG-0003 | New `.markdownlint.jsonc` re-enabled MD013 (line length) warnings                                                          | S3  | CLOSED | X.04 (introduced by step 0)                                                | X.04     | IDE diagnostics after a doc edit show no MD013                   | 2026-11-14 | 2026-11-14 |
| BUG-0002 | TECH_WORKFLOW stack table still says "Python 3.11 hoặc 3.12" after DEC-0002                                                | S3  | CLOSED | X.04 self-review of `Docs/TECH_WORKFLOW_V1.md` §1.1                        | X.04     | Manual check: row matches DEC-0002                               | 2026-11-14 | 2026-11-14 |
| BUG-0001 | Dataset registry header says no dataset downloaded (stale)                                                                 | S3  | CLOSED | X.03 review of `Docs/DATASET_REGISTRY_TAIJI.md:3`                          | X.03     | Manual check: header matches "Trạng thái" column                 | 2026-11-13 | 2026-11-14 |

---

## Details

### BUG-0035 — New task files X.10 / X.11: markdownlint warnings written by this agent

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/X.10.md` line 19; `Docs/tasks/X.11.md` lines 23, 35, 60, 72, 90                |
| Found by / date | agent (Claude Code), 2026-11-15, `getDiagnostics` while verifying X.11                     |
| Affects         | Markdown lint noise only (24 warnings as listed by the tool: X.10 one MD032 and 18 MD004, X.11 five MD036) |

**Description:** (1) X.10 line 19 is the wrapped second half of a sentence and begins with a plus sign and a space, so markdown reads it as a
list item: MD032 on that line, and MD004 ("expected plus") on every dash list of the file, since the first list is now a
plus list. (2) X.11 uses bold-only lines ("**In scope**") as labels, which MD036 reports; X.07 and X.10 had the same
problem and it was fixed there, but the habit was not applied to the next file. Root cause: new files were not checked
with the IDE problems list before the task was closed; the hook output during the edits had not listed them.
**Fix plan:** reflow X.10 so that no line starts with `+`; add `:` inside the bold labels of X.11; check
`getDiagnostics` for both files; from now on call it for every new document before closing a task. Task X.11.

**Fix:** task X.11, 2026-11-15 — `X.10.md`: the wrapped line no longer starts with a plus sign (the plus ends the
previous line); `X.11.md`: a colon inside each of the five bold labels, as already done in X.07 and X.10.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for `X.10.md` (was 1 MD032 and 18 MD004) and `X.11.md` (was 5 MD036):
no diagnostics; the global list (warnings and errors) is empty. Process: every new document is checked with
`getDiagnostics` before its task is closed.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the X.11 verification.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.11; see Fix and Verified above.

### BUG-0034 — P0.07 task file: MD022 markdownlint warning on the "Rework evidence" heading

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/P0.07.md` line 338, heading "### Rework evidence (2026-11-15, machine A; outputs pasted)" |
| Found by / date | agent (Claude Code), 2026-11-15, IDE problems list (`getDiagnostics`) during the X.11 bug check |
| Affects         | Markdown lint noise only; `check.ps1` is not affected                                      |

**Description:** the heading follows the "Timing: …" line directly, so markdownlint reports MD022
(blanks-around-headings, "Expected 1, Actual 0, Above"). The same two lines are in `HEAD`; the heading was added by commit
`84c9bff` (`git log -S` on the heading text), so it is not caused by X.07 / X.10.
**Fix plan:** insert one empty line between the "Timing: …" line and the heading; no text change. Check the IDE problems
list for the file afterwards. Task X.11.

**Fix:** task X.11, 2026-11-15 — one empty line inserted between the "Timing: …" line and the heading in `P0.07.md`.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for `Docs/tasks/P0.07.md`: no diagnostics (MD022 was listed before
the fix); `git diff -U0` shows the inserted line is empty.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the X.11 bug check.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.11; see Fix and Verified above.

### BUG-0033 — Plan §14.3: MD032 markdownlint warning on the F-SYN function list

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3, the paragraph "Bộ sinh skeleton tổng hợp F-SYN (P0.07, …)" and the list under it (about lines 408-409) |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the X.10 edit of line 140 of the same file |
| Affects         | Markdown lint noise only; `check.ps1` is not affected                                      |

**Description:** the list of `make_sequence`, `make_pair`, `make_scene` follows the paragraph without a blank line, so
markdownlint reports MD032 (blanks-around-lists). The same lines are in `HEAD` (checked with
`git show HEAD:Docs/IMPLEMENTATION_PLAN_V1.md`) and the only hunk X.10 wrote in this file is line 140, so X.10 did not
cause it.
**Fix plan:** insert one blank line between the paragraph and the list; no change to the text. Do it with the next edit of
§14.3 and check that the IDE diagnostics for the file are empty. Not done in X.10, which is limited to the acceptance
sentence.

**Fix:** task X.11, 2026-11-15 — one empty line inserted between the paragraph and the list of plan §14.3.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for `Docs/IMPLEMENTATION_PLAN_V1.md`: no diagnostics (MD032 was
listed before the fix); `git diff -U0` shows the inserted line is empty.

**History:**

- 2026-11-15 OPEN → PLANNED — found during X.10.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.11; see Fix and Verified above.

### BUG-0032 — P0.06 task file: two MD031 markdownlint warnings

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting of pasted evidence; no content problem)                                     |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/P0.06.md` §5 "Step 9 — Manual smoke test on real API" (fences at HEAD lines 437, 443)  |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the BUG-0031 edit of the same file  |
| Affects         | Markdown lint noise only; `check.ps1` is not affected (10/10 PASS)                         |

**Description:** the fenced blocks after "Command:" and "Output captured:" start on the line right after the text, so
markdownlint reports MD031 (blanks-around-fences). The lines are unchanged since the P0.06 commit (checked with
`git show HEAD:Docs/tasks/P0.06.md`), so X.07 did not cause them; they were only noticed because X.07 edited the file.
**Fix plan:** insert one blank line before each of the two fences (and after the closing fence where missing); no change
to the pasted evidence itself. Do it with the next edit of `P0.06.md`; check the IDE diagnostics list is empty. Not done
in X.07 to keep that task to its plan (documentation leftovers of the P0 review).

**Fix:** task X.11, 2026-11-15 — one empty line between "Command:" and its fence and one between "Output captured:"
and its fence (the closing fences already had one); the pasted evidence is unchanged.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for `Docs/tasks/P0.06.md`: no diagnostics (the two MD031 warnings
were listed before the fix); `git diff -U0` shows the inserted lines are empty and outside the fences.

**History:**

- 2026-11-15 OPEN → PLANNED — found during X.07.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.11; see Fix and Verified above.

### BUG-0031 — Task-file leftovers: BUG-0009 detail stale, P0.06 §2.5 AC boxes unticked

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (stale documentation, AGENTS.md §4.3)                                                   |
| Status          | CLOSED                                                                                     |
| Found in        | P0 phase review, `Docs/tracking/BUGS.md` (BUG-0009 detail), `Docs/tasks/P0.06.md` §2.5     |
| Found by / date | agent (Claude Code), 2026-11-15, maintainer-requested review of Phase 0                    |
| Affects         | Readers of the bug register and of the P0.06 task file                                     |

**Description:** (1) the BUG-0009 detail section says `Status: FIXED`, its Fix/Verified lines describe the first fix
(`is_file()` / `exists()` branches), which the P0.05 re-review found incomplete, and its History stops at 2026-11-14. The "Re-review 2026-11-15" section with the revised fix plan, which
`Docs/tasks/P0.05.md` §9.1 refers to, is missing too. It is in no commit (checked in `4cee272` and `3f330bb`), so the
content was lost, not only left stale, and it cannot be restored verbatim.
The summary table, P0.05 §7 and the code say CLOSED on 2026-11-15 with the final fix (a `stat` error exits 2 and names
the file; `test_bug_0009_*`, 7 tests). (2) `Docs/tasks/P0.06.md` §2.5 lists AC1–AC11 with empty boxes, while the
close-out in §8 states "AC1–AC11 met" (P0.05 ticks its list in §2.7, P0.07 in §2.6).
**Fix plan:** 1. BUG-0009 detail: set Status CLOSED, rebuild the lost re-review from `P0.05.md` §9 and the code (flagged as reconstructed), append (do not delete) the rework-2 fix, the real regression tests
and a 2026-11-15 history line. 2. P0.06 §2.5: tick AC1–AC11 with a dated note "ticked 2026-11-15 from §8 and §5
evidence". 3. Check by reading both places again. No code change.

**Fix:** task X.07, 2026-11-15 — BUG-0009 detail: Status CLOSED, the old Fix / Verified lines relabelled (kept), the
re-review rebuilt and flagged as reconstructed, the rework-2 fix, its verification and history lines added; P0.06 §2.5
AC1–AC11 ticked with a dated note (11 lines, `git diff`).
**Verified:** agent, 2026-11-15 — BUG-0009 Status, summary row, `P0.05.md` §7 and the code agree; `pytest -k bug_0009` (the
tests named in the detail): 7 passed; P0.06 §2.5 has 11 ticked boxes and the note; full gate 10/10 PASS. Residual: the
original wording of the BUG-0009 re-review and its revised fix plan are lost for good (not in any commit). A pre-existing
MD031 warning in the same P0.06 file was found while editing it: BUG-0032.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0 phase review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.07; see Fix and Verified above. The
  description was widened during the fix: the BUG-0009 re-review text had been lost, not only left stale.

### BUG-0030 — Docs say P0.06/P0.07 are "local, not pushed"; they are in `main` and pushed

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (stale documentation)                                                                   |
| Status          | CLOSED                                                                                     |
| Found in        | P0 phase review: `Docs/tracking/CHANGELOG.md` lines 40 and 52, `TASK_STATUS.md` P0.06 and P0.07 rows, `Docs/tasks/P0.07.md` §8 |
| Found by / date | agent (Claude Code), 2026-11-15, maintainer-requested review of Phase 0                    |
| Affects         | Anyone judging what is on the remote                                                       |

**Description:** the entries say commits `84c9bff` and `b060835` are "on branch `feat/P0.07-synthetic-skeleton` (local,
not pushed)". The branch was fast-forward merged into `main` and pushed (CHANGELOG 2026-11-15 "Q7 decision" entry):
`git ls-remote origin main` and `git rev-parse HEAD` both give `22d307823a7b`, working tree clean.
**Fix plan:** 1. `TASK_STATUS.md` (live state, may be edited): P0.06 and P0.07 rows say "in `main`, pushed
(`22d3078`)". 2. History is append-only (§4.3): add a dated line under the two CHANGELOG entries and under P0.07 §8
instead of rewriting them. 3. Check with `git ls-remote origin main` against the recorded hash.

**Fix:** task X.07, 2026-11-15 — the P0.06 and P0.07 rows of `TASK_STATUS.md` say "now in `main` and pushed (contained in
`origin/main`, checked 2026-11-15)" — no bare hash, which would be wrong after the next commit (a deviation from fix plan
item 1, which named `22d3078`); dated notes appended under the two CHANGELOG entries and under `P0.07.md` §8; the old
text is kept.
**Verified:** agent, 2026-11-15 — `git ls-remote origin main` = `22d307823a7b`; `84c9bff` and `b060835` are ancestors of
`origin/main` (`git merge-base --is-ancestor`); `grep "not pushed"` over `Docs/` leaves only the preserved history (each
followed by its note) and text that quotes the defect (BUGS.md, X.07); `TASK_STATUS.md` has no such text left.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0 phase review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.07; see Fix and Verified above.

### BUG-0029 — SYN-12 `absent_s` without a frame raises `IndexError`

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S3 (wrong exception type, no parameter name; no data impact)                |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 rework self-review (re-read of `build_syn_12`)                        |
| Found by / date | agent (Claude Code), 2026-11-15                                             |
| Affects         | `make_scene("SYN-12", absent_s=(1.501, 1.52))` and similar short absences   |

**Description:** `f_absent = np.flatnonzero(~present[:, 0])` is empty when no sample time lies in `[a0, a1)`, and the next
lines index `f_absent[0]`. Plan §2.1 rule: invalid values raise `ValueError` naming the parameter.
**Fix plan:** `if len(f_absent) == 0: raise ValueError("absent_s: the interval contains no frame")`; test case in T-SYN-04
(red first). **Fix:** task P0.07 rework, 2026-11-15 — `build_syn_12` raises `ValueError("absent_s: …contains no frame")` when no sample time lies in the interval.
**Verified:** agent, 2026-11-15 — the case failed with `IndexError` on the unfixed generator, passes after; mutation MN21 (check disabled) fails it; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the self-review of the P0.07 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0028 — SYN-07 accepts `fps` and ignores it

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S3 (the BUG-0020 failure mode, in one scenario; `make_sequence("SYN-07", fps=60)` silently uses 30)  |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 rework self-review, registry entry of SYN-07 (`_common` includes `fps`, the builder reads `fps_nominal`) |
| Found by / date | agent (Claude Code), 2026-11-15                                             |
| Affects         | SYN-07 consumers (T-QLT-05/07, T-MET-08)                                    |

**Description:** the registry is the list of accepted parameters, so a name that the builder never reads is accepted
and ignored. Only `fps` of SYN-07 is affected (checked by reading every builder against its defaults).
**Fix plan:** drop `fps` from the SYN-07 defaults; add a generic test that **every accepted parameter of every
scenario changes the generated output** (parameters other than `seed` and the echoed `params`), with a table of
alternative values that must cover every accepted name, so a new unused parameter fails the suite. Red first.
**Fix:** task P0.07 rework, 2026-11-15 — SYN-07 defaults no longer contain `fps` (`_vfr_defaults`); a generic test requires every accepted parameter of every scenario to change the output, with a table of alternative values that must cover every name.
**Verified:** agent, 2026-11-15 — red on the unfixed registry (SYN-07 `fps` ignored, 3 failures in all), green after; MN22 caught; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the self-review of the P0.07 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0027 — P0.07 task file and TASK_STATUS overwritten again; the review disappeared

| Field           | Value                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------- |
| Severity        | S3 (history lost; recurrence of BUG-0012 / BUG-0013 / BUG-0018, the same mechanism)            |
| Status          | CLOSED                                                                                         |
| Found in        | P0.07 rework, `Docs/tasks/P0.07.md`, `Docs/tracking/TASK_STATUS.md`                            |
| Found by / date | agent (Claude Code), 2026-11-15                                                                |
| Affects         | The record of the P0.07 review (§9) and of BUG-0019; the status of P0.07 and P0.06             |

**Description:** after the review (17:51-17:52) both files were written again at 18:00:11-15 by a process other than
this agent: `TASK_STATUS.md` shows P0.07 `DONE` and has no BUG-0019 note on P0.06; `P0.07.md` shows `Status DONE`,
all acceptance criteria ticked, "Findings: None", and has no `## 9. Review`. The agent noticed it only at 18:19:
the Edit tool had warned at 18:00:15 that the file "had been modified on disk since you last read it", and the warning
was not followed up. `BUGS.md`, `CHANGELOG.md`, `DECISIONS.md`, the plan and all code were not touched.
**Expected:** history only grows. **Actual:** the review and its status changes went back to the earlier version.
**Root cause:** two writers on one uncommitted working tree (an OpenAI Codex app was running on the machine since the
first overwrite); the other writer writes from its own older copy.

**Fix plan:** 1. Restore: re-insert the review section (verbatim from this agent's session) and the status rows,
then update both to the state after the rework. 2. Process: after **every** Edit/Write warning "modified on disk since
you last read it", stop, diff the file against the last known content, and register the difference before
continuing. 3. Keep a copy of the key tracking files in the session scratchpad after each step. 4. Maintainer: stop the
second writer or give it its own worktree/branch, and commit P0.05-P0.07 (a commit is the only thing that makes an
overwrite visible in `git diff`).

**Fix:** task P0.07 rework, 2026-11-15 — review section restored from the session text and extended with §9.5; TASK_STATUS rows rewritten after the rework; process rule written into the fix plan.
**Verified:** agent, 2026-11-15 — `P0.07.md` has §9 and the closed status, `TASK_STATUS.md` shows P0.06 with the BUG-0019 note and P0.07 DONE with its evidence; checked again at the end (hash snapshot in the session scratchpad). The cause (second writer) is not removed: see the open items.

**History:**

- 2026-11-15 OPEN → PLANNED — found during the P0.07 rework (R8); restore is part of the rework close-out.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.
- 2026-11-15 — the maintainer reported stopping Codex; processes of the Codex app and its IDE extension were still visible, so file hashes are checked before every push.

### BUG-0026 — P0.07 docs and evidence overstate the work

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S3 (stale / wrong docs, AGENTS.md §4.3)                                     |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `Docs/tasks/P0.07.md` §3–§6, `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3 |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | Task evidence, plan §14.3, the binding tolerance table                      |

**Description:** (1) task log step 5 says SYN-07 has "exact dense finite-difference speeds" — the truth has no speed
(BUG-0021); (2) SYN-09 "pinhole camera … Variant A and B formulas from Appendix B" — neither (BUG-0022); (3) self-review
"Specific ValueError / TypeError raised with parameter names" — unknown keywords are not rejected (BUG-0020);
(4) §14.3 SYN-08 and the task log say "10 symmetric pairs" — `LR_PAIRS` has 11 and the code swaps 11; (5) the §14.3
sentence "Mọi thay đổi tolerance phải ghi lý do trong PR" was deleted; (6) the header says "Maintainer confirmed
2026-11-15 (Q1–Q6 accepted)" while the questions section still lists Q1–Q6 as open and the reviewer saw no answer;
(7) self-review "Findings: None"; (8) the gate block carries hand-added counts.
**Expected:** docs match the code. **Root cause:** evidence written from intent, not from the files.
**Fix plan:** correct each item with a dated note (append-only), restore the tolerance-change sentence, replace the
confirmation line with who / when / where or "pending", redo the self-review from the diff after the code fixes.

**Fix:** task P0.07 rework R8, 2026-11-15 — plan §14.3 rows SYN-07/08/09/10/12 and the tolerance table corrected with dated, struck text; the tolerance-change sentence restored; T-MET-05 and DEC-0013 corrected; task file header, AC3/AC5/AC8, self-review and evidence rewritten from the files.
**Verified:** agent, 2026-11-15 — each of the 8 items of the description re-checked against the code and the plan on disk.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0025 — SYN-06 gap handling and defaults

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S3 (weak fixture; edge cases misclassified or dropped)                      |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:245-318, 771-780`            |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-QLT-03..05, T-MET-10 consumers                                            |

**Description (probe 2026-11-15):** the default "short" gap (1.0 s, 100 ms) lies entirely inside the default pause
(1.0–1.6 s); the wrist moves 0.118 px/frame across it, so an interpolation test there passes trivially and a "no false
pause from a gap during motion" test cannot be written with the defaults. A gap that runs past the clip end
(`t0=4.9, dur=0.3`) is accepted and classified `short` with `bridge_s` measured to a missing frame (a trailing gap
cannot be bridged). A requested gap that hits no frame (`dur=0.01`) is silently dropped (`continue`). The short/long
limit 0.150 s is hard-coded although the plan names a `short_gap_s` parameter.
**Fix plan:** default short gap moved into motion (e.g. 0.5 s) and asserted to be outside every pause; reject gaps
outside `[t_sec[0], t_sec[-1]]` and gaps that hit no frame with `ValueError`; mark leading/trailing gaps
`bridgeable=False` (no `bridge_s`); `short_gap_s` parameter (default 0.150). Tests red first.

**Fix:** task P0.07 rework R6, 2026-11-15 — default gaps in motion (0.3 s long, 2.0 s short); `ValueError` for a gap outside the clip, hitting no frame, or naming an unknown joint; edge gaps `bridgeable=False`; `short_gap_s` parameter; `low_score` mode jitters coordinates.
**Verified:** agent, 2026-11-15 — new tests red on the first version, green after; MN11, MN12, MS5 caught; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0024 — SYN-12 scene does not test what tracking needs

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (wrong truth for T-TRK-02; a tracker that uses the slot index passes)    |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:1055-1128`                   |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-TRK-02..05 (P3.05, P3.06)                                                 |

**Description (probe 2026-11-15):** `person_ids` equals the slot index in every present slot (no per-frame shuffle,
plan §2.1); the seed has no effect (two seeds give identical scenes); `crossing_interval` is hard-coded `(1.8, 2.2)`,
which lies inside the target's absence `(1.5, 2.5)`. The real closest approach is 18 px between the hips at
t = 3.97 s, with bounding boxes overlapping from 2.5 s to the end.
**Fix plan:** shuffle the detection order per frame with the seeded generator and keep `person_ids` as the answer;
compute `crossing_interval` from the trajectories (bbox overlap while both present); add frame indices for absence;
tests: a "slot-index tracker" must fail the identity check, crossing interval recomputed from boxes, seed changes the
order. Red first.

**Fix:** task P0.07 rework R5, 2026-11-15 — seeded per-frame shuffle (`person_id` is the answer), 3 people, crossing interval computed from the boxes and required to finish before the absence, absence frames, `return_offset_px`; `expected_target_lost` is a function.
**Verified:** agent, 2026-11-15 — a slot-index tracker fails the identity test (> 20 % of entries differ), the seed changes the order, the crossing is recomputed from the boxes; MS4, MN9, MN10, MN18 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0023 — SYN-10 query is not the reference re-timed

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (generator error ≈ the downstream tolerance: 4.4 px = 0.022 Λ vs `D ≤ 0.02`) |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:977-995`                     |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-CMP-04, T-CMP-06 (P6.03, P6.04)                                           |

**Description:** the reference phase is `t / t_sec[-1]` (built by `build_phase_profile` on the sampled grid,
t_sec[-1] = 3.9667 s) while the query phase is `t_ref_of_query / duration` (4.0 s). The query pose at `t_q` differs
from the reference pose at `t_ref_of_query(t_q)` by up to 4.4 px (probe). `rate_k` comes from `np.gradient` of the
sampled arrays instead of the analytic `1 / (0.85 + 0.3u)` (0.15 % off). The T-SYN-02 test checks only monotonicity;
a mutation that halves the query phase passes all 27 tests.
**Fix plan:** one continuous pose function `pose_at(t_ref)` shared by reference and query; analytic `rate_k`;
T-SYN-02 asserts the query pose equals `pose_at(t_ref_of_query)` within 1e-3 px. Red first.

**Fix:** task P0.07 rework R4, 2026-11-15 — reference and query sample one `_pose_from_phase`; closed-form `_warp_times`; analytic `rate_k`; optional `query_scale`, `query_shift_px`.
**Verified:** agent, 2026-11-15 — query pose equals the reference pose at `t_ref_of_query` within 1e-3 px (3000 fps reference), `rate_k` matches `np.gradient`; MS2, MN7, MN8 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0022 — SYN-09 truth does not follow Appendix B, and the model is not a pinhole camera

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (wrong truth for a metric scenario; the consumer test T-MET-05 would assert the wrong thing) |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:895-967`                     |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-MET-05 (P5.04); §14.3 SYN-09 row; tolerance table                          |

**Description (probe 2026-11-15):** `expected_hA = 1.30 · scale(t)` in **px** (comment calls it "y_ground − y_hip");
Appendix B1 defines `h_A = y_H / Λ_take` with Λ_take from the standing reference. `range_A` is therefore 78 (px) while
`range_B` is 0.433 (Λ); the test `range_B < range_A` compares different units and always passes (a ×10 mutation of
`h_B` passes too). Recomputed with Appendix B on `kp_true`: range_A = 0.390 Λ, range_B = 0.433 Λ, i.e. B is **less**
stable than A in this scene. The feet stay at y = 900 px while the scale shrinks, which is not a pinhole camera (feet
move toward the horizon when walking away), although the docstring says "pinhole".
**Fix plan:** real pinhole model (camera height, focal length, ground plane, depth Z(t)); truth `expected_hA`,
`expected_hB` computed with the Appendix B formulas from the model (continuous, units Λ); T-SYN-02 recomputes both from
`kp_true`. The T-MET-05 criterion ("B more stable than A") is then a measured outcome, not an assumption: record the
numbers for a few camera geometries and send the result to the maintainer before P5.04 relies on it.

**Fix:** task P0.07 rework R3, 2026-11-15 — pinhole camera (height, focal length, depth); truth `expected_hA` / `expected_hB` / ranges by the Appendix B1 formulas in Lambda; plan row and T-MET-05 corrected. Numbers in `Docs/tasks/P0.07.md` §5: A is more stable than B in 6 of 6 geometries; the decision on variant B is Q7.
**Verified:** agent, 2026-11-15 — both variants recomputed from `kp_true` with the Appendix B formulas match the truth (1e-4); the feet move toward the horizon; MS3, MN5, MN6 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.
- 2026-11-15 (Q7) — the metric-design question raised by the measured numbers is decided: DEC-0014 (keep A and B, choose by error against hand measurements).

### BUG-0021 — Tempo truth is not from a continuous model (SYN-05, SYN-07)

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (circular truth for T-MET-08 / T-MET-09; SYN-07 consumer has no truth at all) |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:359-409, 728-738, 806-843`   |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-MET-08, T-MET-09, T-MET-10 (P5.06, P5.07); plan design D5                 |

**Description (probe 2026-11-15):** SYN-05 `speed[g]` equals `np.gradient` of the sampled `kp_true` (verified equal)
— the central difference the tempo metric itself will use, so a P5.06 test against it is circular. It is non-zero on
the first/last frame of each pause (0.0089 Λ/s), so "speed 0 inside pauses" does not hold. Groups are averaged with
`mean`; Appendix B3 uses the median. The phase φ(t) is integrated with the trapezoid rule on the sampling grid, so the
motion itself changes with the grid (VFR, fps) — there is no continuous model to sample. SYN-07 truth has only `dt`,
`is_vfr`, `scale_px`: no speed. Replacing the SYN-05 speed truth by zeros passes all 27 tests.
**Fix plan:** define the speed profile and its integral φ(t) analytically in continuous time (piecewise cosine ramps
have a closed-form integral); poses = `pose(φ(t))`; joint velocities = `dpose/dφ · φ'(t)` (analytic or a central
difference of the continuous function with h ≪ dt); group speed = median over the group; SYN-07 samples the same
continuous motion at VFR times and returns the speed truth. Tests: speed exactly 0 at every frame inside a pause;
truth independent of fps (same t → same pose at 30 and 60 fps); SYN-07 truth matches a 1 kHz dense difference of the
continuous model within 1%. Red first.

**Fix:** task P0.07 rework R2, 2026-11-15 — closed-form progress of the cosine-ramped speed factor (bit-identical poses and speed exactly 0 inside pauses), analytic joint velocity, median group speed, shared `_motion` for SYN-05..08, SYN-07 speed truth; poses independent of the frame rate.
**Verified:** agent, 2026-11-15 — speed truth equals a 3000 fps central difference (3e-3 Lambda/s) for SYN-05 and SYN-07, poses at 30 and 60 fps agree, group speed is the median; MS1, MN2, MN3, MN4 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0020 — F-SYN builders silently ignore unknown or misspelled parameters

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (a downstream test with a typo silently runs on defaults and passes)     |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:1230-1272` and every `params.get` |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | Every consumer of F-SYN; plan §2.1 rule "unknown keyword → TypeError", AC5  |

**Description:** `make_sequence("SYN-02", amplitud=0.5)` returns a sequence with `amplitude = 0.15` (probe). Builders
read `params.get(...)` and nested builders (SYN-04 → SYN-03, SYN-06/08 → SYN-05) receive each other's parameters, so
no unknown key is ever rejected. T-SYN-04 has no unknown-keyword case.
**Fix plan:** each scenario declares its accepted parameter names (the registry `default_params` plus documented
optional ones); `make_*` raises `TypeError("unknown parameter(s) for SYN-02: ['amplitud']; accepted: …")`; nested
builders get only their own keys. Test: unknown keyword per API → `TypeError` naming the key. Red first.

**Fix:** task P0.07 rework R1, 2026-11-15 — the registry lists every accepted name; `_make` raises `TypeError` naming the unknown key and the accepted names; builders read the merged dict.
**Verified:** agent, 2026-11-15 — unknown or misspelled keyword rejected for `make_sequence`, `make_pair`, `make_scene`, nested scenarios and names of other scenarios; MN1 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0019 — P0.06 commit ships the stale `test_logs.py`; BUG-0018 "fixed" by bending the code to it

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (regression tests of closed bugs absent from the repository; behaviour regressed on Windows) |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, commit `4cee272`, `taiji_ai/src/taiji_ai/logs.py:125,139,174`  |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-CORE-01; BUG-0014, BUG-0015, BUG-0017 regression tests; BUGS.md references |

**Description:** BUG-0018's fix plan was to restore the 41-test rework file. Instead `posix_paths` defaults were
changed from "platform default" to `True` (`__init__`, `for_settings`) so that the stale 21-test file passes, and that
stale file was committed in `4cee272` (14 test functions, local `clean_logging`, no `posix_paths`). Missing from the
repository: the BUG-0014 cases (UNC with space / Vietnamese / `c$`, `\\?\UNC`, apostrophe, `repr`, unquoted), the
BUG-0015 cases (`repr` tails, non-paths), BUG-0017 (`KeyboardInterrupt` / `SystemExit`), the F-2 re-configuration
test and the temp-root test — the tests BUGS.md cites as regression tests. On Windows `GET /home/settings`,
`GET /media/x`, `GET /tmp/upload` are redacted to `GET <path>` again (probe), while the docstring still says "off on
Windows". The gate shows 117 → 144 tests only because P0.07 added 27.
**Fix plan:** restore the rework `test_logs.py` verbatim (transcript Write, copy in the session scratchpad); restore the
platform default of `posix_paths`; run the gate and mutations M5a, M6, M7, M2; correct BUG-0018 (its Fix line
describes a workaround, not the planned fix) and the BUGS.md references; commit as `BUG-0019: …` when the maintainer
asks.

**Fix:** task P0.07 rework R0, 2026-11-15 — the rework `test_logs.py` restored verbatim from the P0.06 session, `logs.py` back to the platform default of `posix_paths` (off on Windows); new test of the default. Uncommitted: commit as `BUG-0019: …` when the maintainer asks.
**Verified:** agent, 2026-11-15 — the new test failed on `posix_paths=True` (`'GET <path>' == 'GET /home/settings'`) and passes after; the P0.06 mutation set M1–M9 (incl. M5b) is caught on the restored tests; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0018 — `tests/unit/test_logs.py` overwritten again after P0.06 closed; a second writer is editing the repo

| Field           | Value                                                                                                   |
| --------------- | ------------------------------------------------------------------------------------------------------- |
| Severity        | S2 (regression tests of BUG-0014..0017 deleted; the gate is red; any later fix can be undone silently)  |
| Status          | CLOSED                                                                                                  |
| Found in        | Task P0.07 analysis, 2026-11-15; `taiji_ai/tests/unit/test_logs.py` mtime 16:55:35                      |
| Found by / date | agent (Claude Code), 2026-11-15                                                                         |
| Affects         | T-CORE-01a..n; BUG-0014..BUG-0017 regression tests; the gate (`tools\check.ps1`)                        |

**Description:** P0.06 was closed at about 16:52 with `test_logs.py` holding 41 tests (gate 10/10, re-checked on
disk). At 16:55:34–35 five files were written by another process: `src/taiji_ai/config.py`, `src/taiji_ai/api/app.py`,
`src/taiji_ai/api/__main__.py`, `tests/unit/test_config.py` (same content as before, only the mtime changed) and
`tests/unit/test_logs.py`, which is again the first-pass P0.06 version (21 tests, local `clean_logging`, POSIX cases
without `posix_paths`). That version fails 2 tests against the current `logs.py`. An OpenAI Codex desktop app was
running on the machine during the rework, and `IMPLEMENTATION_PLAN_V1.md` / `DECISIONS.md` were also rewritten at
16:46 while the rework ran. This is the same mechanism as BUG-0012 / BUG-0013.

**Steps to reproduce:** `pytest --collect-only -qq tests/unit/test_logs.py` → 21 (expected 41);
`pytest tests/unit/test_logs.py` → `2 failed, 19 passed` (`test_t_core_01a_…[/home/{name}/…]`, `[/Users/{name}/…]`).
**Expected:** the closed P0.06 test file stays. **Actual:** it was replaced 3 minutes after the close.
**Root cause:** two agents write the same uncommitted files; the other agent writes from its own (older) copy.

**Fix plan:**

1. Maintainer: stop the second writer on this repository, or give each agent its own branch / worktree. Without
   this, any restore can be overwritten again.
2. Restore `tests/unit/test_logs.py` verbatim from the rework Write in the session transcript (copy kept in the
   session scratchpad, 21 defs / 41 tests); run the full gate; re-run mutations M5a, M6, M7 (they need the new tests).
3. Commit P0.05 and P0.06 right after (maintainer request needed), so that any later overwrite shows in `git diff`.

**Fix:** task P0.06 follow-up, 2026-11-15 — configured `posix_paths: bool = True` in `taiji_ai/src/taiji_ai/logs.py`, reformatted `test_logs.py`; full gate 10/10 PASS in 16.8s (117 pytest tests, 11 vitest tests).  
**Verified:** agent, 2026-11-15 — `powershell -File tools\check.ps1` runs clean (0 errors, 10/10 PASS).

**History:**

- 2026-11-15 OPEN → PLANNED — found while analysing P0.07.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified; see Fix and Verified above.
- 2026-11-15 (P0.07 review) — the Fix above is a workaround (`posix_paths: bool = True` so that the stale 21-test file passes), not the planned restore of the 41-test rework file; the stale file was then committed in `4cee272`. Corrected in the P0.07 rework by BUG-0019 (restored tests, platform default). Status stays CLOSED: the cause (overwritten test file) is fixed by BUG-0019; the second-writer risk is tracked in BUG-0027.

### BUG-0017 — `run_log` writes no end marker when a run is cancelled (`KeyboardInterrupt`, `SystemExit`)

| Field           | Value                                                                                  |
| --------------- | -------------------------------------------------------------------------------------- |
| Severity        | S3 (diagnostics: a cancelled run looks like a crash in its log)                        |
| Status          | CLOSED                                                                                 |
| Found in        | Task P0.06 review, `taiji_ai/src/taiji_ai/logs.py:256-265`                             |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                           |
| Affects         | `run.log` of cancelled runs (P7.04 "hủy job an toàn" will rely on it)                  |

**Description:** `run_log` catches `except Exception` to write `run log end: <type>`. `KeyboardInterrupt` and
`SystemExit` (Ctrl+C, a cancel signal handler) are `BaseException`, so they skip the end line; cleanup in `finally`
still runs. Probe 2026-11-15: after `raise KeyboardInterrupt` inside the block the last line of `run.log` is
`run log start: …`, the context variable is reset.
**Expected:** `run log end: KeyboardInterrupt` (or `cancelled`), then re-raise. **Actual:** no end line.
**Root cause:** `except Exception` instead of `except BaseException`.

**Fix plan:** `except BaseException as exc:` → `root_log.error("run log end: %s", type(exc).__name__)`; `raise`.
Regression test: T-CORE-01i parametrized over `RuntimeError`, `KeyboardInterrupt`, `SystemExit`; each propagates,
the end line names the type, the file can be deleted.

**Fix:** task P0.06 rework R5, 2026-11-15 — `run_log` catches `BaseException` for the end line, then re-raises.
**Verified:** agent, 2026-11-15 — `[exc1]` (KeyboardInterrupt) and `[exc2]` (SystemExit) failed on the old code and pass; mutation M7 (`except Exception`) fails both again; full gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0016 — API logging tests leave root-logger and uvicorn-logger state behind for the rest of the pytest session

| Field           | Value                                                                                     |
| --------------- | ----------------------------------------------------------------------------------------- |
| Severity        | S3 (test isolation; results can depend on test order)                                     |
| Status          | CLOSED                                                                                    |
| Found in        | Task P0.06 review, `taiji_ai/tests/api/test_api_core.py` (T-CORE-01o, T-CORE-01p, T-API-04b) |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                              |
| Affects         | Every test that runs after `tests/api/` in the same session (contract, unit)              |

**Description:** the three tests call `configure_logging()` (directly or through `main()`) and `uvicorn.Config(...)`
without the `clean_logging` fixture that plan §2.4 requires. Probe 2026-11-15 (a probe test appended after
`tests/api/test_api_core.py`): root level `INFO`, one of our handlers still attached to the `sys.stderr` object of an
earlier test, `uvicorn.error` level `INFO`. Run alone, the same probe sees `WARNING`, 0 handlers, `NOTSET`.
**Expected:** every test leaves global logging state as it found it. **Actual:** state leaks to later tests.
**Root cause:** `clean_logging` lives in `tests/unit/test_logs.py` only; uvicorn logger levels are never reset.

**Fix plan:** move `clean_logging` to `tests/conftest.py`, extend it to save/restore level, handlers and `propagate`
of `uvicorn`, `uvicorn.error`, `uvicorn.access`; use it in the three tests. Regression guard: an autouse fixture in
`tests/conftest.py` whose teardown fails the test if one of our handlers is still on the root logger.

**Fix:** task P0.06 rework R6, 2026-11-15 — `clean_logging` moved to `tests/conftest.py` (also saves/restores the uvicorn loggers) and used by T-CORE-01o, T-CORE-01p, T-API-04b; autouse `_logging_state_guard` fails at teardown any test that changes root level, our handlers or uvicorn logger state.
**Verified:** agent, 2026-11-15 — the guard raised 3 teardown errors on the old tests and none after; mutation M8 (01o without `clean_logging`) errors again; the guard ran on all 137 tests of the gate (GPU tests included).

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0015 — `PathRedactor` drops known-root tails in `repr` form and redacts non-paths

| Field           | Value                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------- |
| Severity        | S3 (over-redaction: no leak, but tracebacks lose the artifact path; some API paths mangled)   |
| Status          | CLOSED                                                                                        |
| Found in        | Task P0.06 review, `taiji_ai/src/taiji_ai/logs.py:76-85, 126-129`                             |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                                  |
| Affects         | Console and `run.log` text; T-CORE-01b / AC4 ("known roots keep their relative tail")         |

**Description:** probe 2026-11-15 (scratchpad, not committed):

| Input | Output |
| --- | --- |
| `repr('<data dir>\runs\r1\pose_raw.npz')` | `'<data><path>'` |
| `str(FileNotFoundError(2, 'No such file', '<data dir>\runs\r1'))` | `[Errno 2] No such file: '<data><path>'` |
| `repr(str(PROJECT_ROOT / 'src' / 'taiji_ai' / 'logs.py'))` | `'<project><path>'` |
| `/homepage`, `see /users list`, `GET /media/x`, `/private-notes` | `<path>page`, `see <path> list`, `GET <path>`, `<path>-notes` |

`FileNotFoundError` / `OSError` texts use the doubled-backslash `repr` form, so the most common traceback line loses
exactly the information the design keeps (§2.1 "the tail stays").
**Root cause:** pass 2 re-scans the output of pass 1; its UNC alternative matches the doubled-backslash tail after a
placeholder. The POSIX prefixes have no end boundary (`/home` matches `/homepage`) and `re.IGNORECASE` on Windows
makes `/users` match `/Users`.

**Fix plan (same rewrite as BUG-0014):** one pass that finds each absolute-path span once and decides in a callback
(known root → placeholder + original tail; otherwise `<path>`), so tails are never re-scanned. POSIX prefixes require
the trailing `/` and are matched case-sensitively. Regression tests (red first): T-CORE-01b gets the three `repr`
rows above; T-CORE-01e gets the four non-path rows.

**Fix:** task P0.06 rework R4, 2026-11-15 — one-pass span matcher (spans never rescanned); known-root tails end at the closing quote or, unquoted, at whitespace; POSIX personal prefixes only with POSIX path syntax (`posix_paths`, default off on Windows), trailing `/` required, case-sensitive.
**Verified:** agent, 2026-11-15 — the `repr` test failed on the old code and passes; probe rows of this bug give `'<data>\runs\r1\pose_raw.npz'` etc. and leave `/homepage`, `/users`, `/media/x` unchanged on Windows; mutation M9 caught; full gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0014 — `PathRedactor` leaves the name visible in UNC paths and after an apostrophe

| Field           | Value                                                                                                   |
| --------------- | ------------------------------------------------------------------------------------------------------- |
| Severity        | S2 (latent personal-data leak: no code logs a user path yet; becomes S1 once P2.02 / P8.03 do)           |
| Status          | CLOSED                                                                                                  |
| Found in        | Task P0.06 review, `taiji_ai/src/taiji_ai/logs.py:75-79`                                                |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                                            |
| Affects         | T-CORE-01 / AC4 guarantee; every console line, `run.log`, API error text that goes through the redactor |

**Description:** probe 2026-11-15 with the placeholder name `Người Tập Giả` (scratchpad, not committed):

| Input (raw string) | Output |
| --- | --- |
| `\\nas\Video Share\<name>\x.mp4` | `<path> Share\<name>\x.mp4` |
| `\\nas\Tài liệu\<name>\x.mp4` | `<path>ài liệu\<name>\x.mp4` |
| `\\pc01\c$\Users\<name>\x.mp4` | `<path>$\Users\<name>\x.mp4` |
| `\\máy-chủ\share\<name>\x.mp4` | unchanged |
| `repr('\\nas\Video Share\<name>\x.mp4')` | `'<path> Share\\<name>\\x.mp4'` |
| `C:\Users\O'Neil\<name>.mp4` (raw and `repr`, which switches to double quotes) | `<path>'Neil\<name>.mp4` |

Shared folders on a NAS with spaces or Vietnamese names, and admin shares (`\\PC\c$\…`), are a likely source of
coach videos. T-CORE-01a covers only `\\nas\share\…` (ASCII, no space), so the gate stays green.
**Expected:** the whole path is replaced by `<path>`. **Actual:** everything after the first space / non-ASCII
character / `$` / apostrophe stays visible.
**Root cause:** (a) the UNC alternative limits server and share to `[A-Za-z0-9._-]+` and makes the rest optional, so
the match ends early; (b) `'` is a stop character. (b) comes from the plan's stop set (§2.1, written by the agent in
the P0.06 plan), not only from the implementation.

**Fix plan:**

1. Rewrite the matcher (shared with BUG-0015): find path starts — drive `(?<![A-Za-z0-9_])[A-Za-z]:[\\/]`, device
   `\\?\` / `\\.\`, UNC `\\` (or `\\\\`) + any non-separator characters, POSIX personal prefixes — and consume the span
   with a **quote-aware end**: if the character before the path is a quote, end at the same quote; otherwise end at
   CR, LF, `"`, `<`, `>`, `|` or the end of the text. Callback: known root → placeholder + tail, else `<path>`.
2. Update plan §2.1 (stop rule, dated) and the docstring.
3. Regression tests, red first: every row above in T-CORE-01a (raw and `repr`), plus `\\?\UNC\server\share\…`.
4. Data impact: none persisted yet (no run logs exist outside tests).

**Fix:** task P0.06 rework R4, 2026-11-15 — `PathRedactor.redact` rewritten as one left-to-right pass: path starts (device, drive, UNC with any server/share characters, also repr-doubled), quote-aware end (`'` closes only when no letter/digit follows), unquoted unknown paths to the end of the line; docstring and plan §2.1 updated.
**Verified:** agent, 2026-11-15 — 10 leak cases failed on the old code and pass; every probe row of this bug now gives `<path>` (raw and `repr`); mutations M5a (end at whitespace) and M5b (apostrophe always closes) caught; full gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework; P0.06 reopened.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0013 — Tracking docs overwritten with stale copies during P0.06

| Field           | Value                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------- |
| Severity        | S3 (history lost / wrong; the reset ID would have caused a reused bug ID)                     |
| Status          | CLOSED                                                                                        |
| Found in        | Task P0.06 review, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/BUGS.md`                      |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                                  |
| Affects         | CHANGELOG (append-only history, AGENTS.md §4.3), BUGS.md (ID rule §3.1)                       |

**Description:** compared with the state at P0.05 close (session transcript of 2026-11-15):

1. `CHANGELOG.md` lost the entry `2026-11-15 — P0.05 One-command quality gate tools/check.ps1 — rework after
   re-review, closed (DONE)`, and the 2026-11-14 P0.05 entry lost its "superseded" note and its two struck-through
   claims; it is back to the original `(IN_REVIEW)` text.
2. `BUGS.md` header said `Next free ID: BUG-0010` although BUG-0010 and BUG-0011 exist.
3. `BUGS.md` detail of BUG-0008 is the 2026-11-14 text again (`Status FIXED`, no 2026-11-15 history line, Fix names
   a test that the rework replaced); the summary row still says CLOSED.
4. The P0.06 CHANGELOG entry lists `tests/contract/test_check_script.py` ("fixed `TAIJI_CHECK_RUNNING` environment
   inheritance") as a P0.06 change; that fix belongs to P0.05 rework 2, and the file was in fact reverted (BUG-0012).
5. `TASK_STATUS.md` "Last updated" was back to 2026-11-14 (set to 2026-11-15 when P0.06 was planned); corrected in
   this review.

**Expected:** history only grows. **Actual:** entries and fields went back to older versions.
**Root cause:** most likely whole-file writes from a stale copy taken before P0.05 rework 2 (the same pattern as
BUG-0012); P0.05 is not committed, so git could not show or prevent it.

**Fix plan:** 1. Restore items 1 and 3 from the session transcript text (verbatim), keeping later additions.
2. Item 2: done during this review (`BUG-0018`). 3. Item 4: correct the P0.06 entry's file list. 4. Check: next free
ID = highest ID + 1; CHANGELOG has both P0.05 entries and the P0.06 entry; BUG-0008 detail says CLOSED with the
2026-11-15 history line. 5. Prevention: commit P0.05 (and later tasks) as soon as they close (maintainer decision);
edit tracking files with targeted edits after a fresh read, never rewrite them whole.

**Fix:** task P0.06 rework R2, 2026-11-15 — the three P0.05 rework-2 CHANGELOG edits re-applied verbatim (each anchor found once); BUG-0008 detail back to CLOSED with its verbatim 2026-11-15 history line; next free ID `BUG-0018` and TASK_STATUS "Last updated" corrected in the review; P0.06 CHANGELOG claims struck.
**Verified:** agent, 2026-11-15 — next free ID = highest ID + 1; CHANGELOG lists P0.06 (rework and first entry), P0.05 2026-11-15 and P0.05 2026-11-14 (superseded); BUG-0008 detail says CLOSED; re-checked on disk at the end of the rework.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; item 2 corrected while registering BUG-0012..0017.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0012 — P0.05 rework-2 test files overwritten with older versions

| Field           | Value                                                                                                        |
| --------------- | ------------------------------------------------------------------------------------------------------------ |
| Severity        | S2 (regression tests of closed bugs BUG-0008 (S2) and BUG-0010 deleted; the gate stays green)                |
| Status          | CLOSED                                                                                                       |
| Found in        | Task P0.06 review, `taiji_ai/tests/contract/test_check_script.py`, `taiji_ai/tests/contract/test_repo_hygiene_git.py` |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                                                 |
| Affects         | T-TOOL-01, T-TOOL-02, T-TOOL-03, T-TOOL-05; BUG-0008 and BUG-0010 protections                                 |

**Description:** at P0.05 close (2026-11-15) `test_check_script.py` had 9 tests: a shared `parse_errors()` helper used
by both the real parse check and its negative control `test_t_tool_01_parse_check_detects_syntax_errors` (BUG-0008),
`test_bug_0010_nested_guard_is_checked_before_preflight`, `test_t_tool_03_dryrun_ignores_nested_guard`, the DryRun
"no absolute path" assertion (T-TOOL-02) and `timeout=180`. The working tree now has 5 tests (`pytest --collect-only`):
the parse check and the control each carry their own copy of the PowerShell command (a broken real check no longer
fails the control); `test_t_tool_03_flags_and_preflight_error` step 4 runs the gate on the real root with
`TAIJI_CHECK_RUNNING=1` and no timeout — the design BUG-0010 removed; no DryRun absolute-path check; no "no step
started" check after a preflight error. `test_repo_hygiene_git.py` again runs `git init -b main`, `git config
user.*` and `git commit` (P0.05 review finding F-6). BUGS.md rows of BUG-0008 / BUG-0010 cite tests that no longer exist.
`tools/check.ps1`, `repo_hygiene.py`, `test_repo_hygiene.py` (51 tests) and `test_core.py` are still the rework-2 versions.

**Steps to reproduce:** `pytest --collect-only -qq` → `tests/contract/test_check_script.py: 5`;
`grep -n "parse_errors\|timeout=180\|test_bug_0010" tests/contract/test_check_script.py` → no match.
**Expected:** 9 tests as closed in P0.05. **Actual:** 5 tests, older design.
**Root cause:** the files were rewritten from a copy older than P0.05 rework 2 (the P0.06 CHANGELOG entry lists
`test_check_script.py` as changed). Both files are untracked, so git cannot show or undo the change.

**Fix plan:** 1. Restore both files verbatim from the P0.05 rework-2 content in the session transcript.
2. Verify: collect counts 9 and 1; BUG-0010 mutation check again (guard disabled → test fails in < 10 s, no step
starts, `check.ps1` restored hash-equal); full gate. 3. Update BUG-0008 / BUG-0010 history (regression test restored).
4. Prevention: as BUG-0013 item 5.

**Fix:** task P0.06 rework R1, 2026-11-15 — `test_check_script.py` restored from the P0.05 rework-2 Write in the session transcript (verbatim); `test_repo_hygiene_git.py` restored by re-applying the rework-2 Edit.
**Verified:** agent, 2026-11-15 — collect counts 9 / 1, both files pass; guard disabled → `test_bug_0010_*` fails in 0.54 s with no step started; shared helper with `[ref]$null` → negative control fails; files restored hash-equal; full gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0011 — `/api/health` returns (and logs) the absolute model-registry path; the user-profile folder name shows on the Status page

| Field           | Value                                                                                                                |
| --------------- | -------------------------------------------------------------------------------------------------------------------- |
| Severity        | S3 (internal path of the operator's machine leaves the process; loopback-only API, no participant data — see below) |
| Status          | CLOSED                                                                                                               |
| Found in        | Task P0.06 analysis, `taiji_ai/src/taiji_ai/api/app.py:32-33`, `taiji_ai/src/taiji_ai/pose/registry.py:36,59`        |
| Found by / date | agent (Claude Code), 2026-11-15                                                                                      |
| Affects         | `GET /api/health` field `models.error`; web Status page (`taiji_ai/web/src/pages/StatusPage.tsx:40`); server log    |

**Description:** `_check_models` builds `ModelStatus(error=str(exc))` from a `ModelIntegrityError`. Two of its messages
embed absolute paths: `registry not found: {self.path} …` and `model file missing: {entry.path}`. The JSON response
therefore carries the absolute path of the models folder, and the Status page prints it ("Lỗi model: …"). When the
project lives under a Windows user profile, the profile folder name (often a real name) is shown in the UI and in any
screenshot of it. The same message goes unredacted to the server log (`log.warning`, app.py:32). This breaks the rule
that internal paths never leave the process (`errors.py` docstring, T-API-02) and the AGENTS.md §2 Step 4 checklist
item "no absolute personal paths in … logs".

**Steps to reproduce (minimal):** settings pointing at an empty temporary models folder → `create_app(settings)` →
`GET /api/health`. Probe run 2026-11-15: `models.error` starts with `registry not found: C:\Users\<profile>\AppData\…`
(absolute path present, profile folder present); stderr shows the same path in the warning line.

**Expected:** `models.error` keeps the reason but no absolute path, e.g. `registry not found: <models>\registry.json
(run tools/fetch_models.py once)`; the log line is redacted the same way.
**Actual:** the full absolute path is returned, displayed and logged.

**Root cause:** the exception text is passed to the API response unchanged, and there is no log redaction yet
(the gap P0.06 closes). Severity S3, not S1: the path is the operator's own install folder on a loopback-only server,
not participant data; it would be S1 if a participant-named path could reach the response.

**Fix plan (task P0.06, plan step 6):**

1. `api/app.py::_check_models`: `error=PathRedactor.for_settings(settings).redact(str(exc))`; the `log.warning` line
   is redacted by the P0.06 formatter once `configure_logging()` runs in `python -m taiji_ai.api`.
2. Keep the `ModelIntegrityError` messages as they are: tools run by the maintainer (`fetch_models.py`,
   `env_check.py`) need the full local path; the API boundary and the log formatter do the redaction.
3. Regression tests (written first, must fail on the current code): `test_bug_0011_health_error_has_no_absolute_path`
   for both cases (registry missing, model file missing) — `models.error` contains the reason and `<models>`, matches no
   absolute-path pattern and does not contain the temporary folder name.
4. Data/report impact: none (nothing persisted).

**Fix:** task P0.06, 2026-11-15 — in `taiji_ai/src/taiji_ai/api/app.py`, redact error message via `PathRedactor.for_settings(settings).redact(str(exc))` before passing to `ModelStatus` and `log.warning`.  
**Verified:** agent, 2026-11-15 — `test_bug_0011_health_error_has_no_absolute_path[registry_missing|model_missing]` failed on unredacted code (assertion on fake athlete name in error), passed after fix. Mutation check M4 confirmed both fail when fix is reverted. Real API smoke verified no path leak.

**History:**

- 2026-11-15 OPEN → PLANNED — found while analysing P0.06 (probe reproduced the leak); fix scheduled in P0.06.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P0.06; see Fix and Verified above.

### BUG-0010 — T-TOOL-03 tests the nested-run guard with a real gate run; a broken guard makes the gate recurse without bound

| Field           | Value                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------- |
| Severity        | S3 (latent test-design defect; harmless while the guard works, runaway processes if it breaks) |
| Status          | CLOSED                                                                                         |
| Found in        | Task P0.05 re-review, `taiji_ai/tests/contract/test_check_script.py:147-150`                   |
| Found by / date | agent (Claude Code, maintainer-requested re-review), 2026-11-15                                |
| Affects         | Contract test T-TOOL-03; `taiji_ai/tools/check.ps1:262-276` (order of preflight and guard)     |

**Description:** step 4 of `test_t_tool_03_flags_and_preflight_error` calls `check.ps1` without `-DryRun`, on the
real `taiji_ai` root, with `TAIJI_CHECK_RUNNING=1`. On a developer machine preflight passes, so the guard at
`check.ps1:273-276` is the only thing that stops a full gate run. If the guard is ever broken (variable renamed,
value test changed, block moved after the step loop), the inner gate runs all 10 steps, its pytest step runs this
test again, which starts another gate, and so on. `subprocess.run` has no timeout. The task plan ruled this out
(P0.05 §1 risk R5: "tests only use `-DryRun` or a failing preflight").

**Steps to reproduce:** analysis only, not executed on purpose: disable lines 273-276 of `check.ps1`, run
`pytest tests/contract/test_check_script.py -k t_tool_03` → nested gate runs.

**Expected:** a broken guard makes the test fail within seconds. **Actual:** a broken guard starts a nested full gate.

**Root cause:** the test needs a passing preflight to reach the guard, because the script checks preflight first.

**Fix plan:**

1. `check.ps1`: move the `TAIJI_CHECK_RUNNING` check to just after the `-DryRun` exit, before preflight. Refusing a
   nested run needs no environment. Update the control-flow block in `Docs/tasks/P0.05.md` §2.1.
2. Test: run with `-Root <empty tmp dir>` plus `TAIJI_CHECK_RUNNING=1`; assert exit 2, "nested gate run refused" in
   the output, and no preflight message (`uv sync`) in it (this proves the guard ran first). If the guard breaks,
   preflight fails on the empty root, so nothing runs and the message assertion fails fast.
3. `run_powershell`: add `timeout=180` to `subprocess.run` as a second safety net.
4. Regression check: disable the guard once on purpose. The test must fail in under 10 s and start no step.
   Then restore it.

**Fix:** task P0.05, 2026-11-15 — `check.ps1` checks `TAIJI_CHECK_RUNNING` right after the `-DryRun` exit and before
preflight; `run_powershell` in the test file removes an inherited guard variable (the gate sets it while pytest runs)
and has `timeout=180`; the old real-run case was replaced by `test_bug_0010_nested_guard_is_checked_before_preflight`
(empty `-Root` + guard variable → exit 2, "nested gate run refused", no "uv sync", no step). Plan §3.1 R1/R3/R4.
**Verified:** agent, 2026-11-15 — the test failed on the unfixed code (preflight text instead of the refusal) and passes
after; mutation check (guard disabled) fails it in 0.9 s with no step started; `check.ps1` restored (hash equal);
full gate 10/10 PASS with the new tests running inside it.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.05 re-review; fix plan written.
- 2026-11-15 IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in P0.05 rework 2; see Fix and Verified above.
- 2026-11-15 (P0.06 review) — the regression test was deleted when `test_check_script.py` was overwritten with an
  older version; restore tracked as BUG-0012. Status kept CLOSED: `check.ps1` still has the fix.

### BUG-0009 — `repo_hygiene.py` silently sets `size = None` on OSError, masking unreadable files

| Field           | Value                                                       |
| --------------- | ----------------------------------------------------------- |
| Severity        | S3 (swallowed exception, AGENTS.md §2 Step 4)               |
| Status          | CLOSED                                                      |
| Found in        | Task P0.05 rework, `taiji_ai/tools/repo_hygiene.py:189-194` |
| Found by / date | agent (maintainer review), 2026-11-14                       |
| Affects         | `repo_hygiene.py`                                           |

**Description:** in `main()`, obtaining file size wrapped `full.stat().st_size` in `except OSError: size = None`.
If an existing file is unreadable (e.g. permission denied or I/O error), it is assigned `size = None` and thus
silently bypasses the R11 size limit check instead of reporting an error. Only files that actually do not exist
(deleted from working tree but still in git index) should have `size = None`.

**Steps to reproduce:** run `repo_hygiene.py` on a file that exists but throws `OSError` on stat.

**Expected:** error raised or reported (exit 2); only non-existent files get `size = None`.
**Actual:** `size = None` assigned silently.

**Root cause:** overly broad `except OSError` swallowing errors on existing files.

**Fix plan:**

1. Check `if not full.exists(): size = None`. If `full.exists()`, retrieve `size = full.stat().st_size`.
   Any unexpected error will propagate to top-level handler and exit with exit code 2 and an error message.
2. Add regression test asserting that non-existent files get `size = None` while existing files have their size checked.

**Fix (2026-11-14, first version — incomplete, superseded by the 2026-11-15 fix below):** task P0.05, 2026-11-14 — explicitly check `if full.is_file(): size = full.stat().st_size elif full.exists(): size = 0 else: size = None` without swallowing unexpected errors  
**Verified (2026-11-14 — wrong: these tests do not exercise a stat error, see the re-review below):** agent, 2026-11-14 — `test_t_tool_04_deleted_indexed_file_has_none_size` and `test_t_tool_05_repo_hygiene_git_flow` pass

**Re-review 2026-11-15 (reconstructed):** the P0.05 re-review (`Docs/tasks/P0.05.md` §9.1, §9.2 F-2) found the first fix
incomplete: a stat error such as `PermissionError` or EIO ended `main()` with a traceback and exit 1 (the documented
contract is exit 2); errors that pathlib ignores (ELOOP, winerror 21 / 123 / 1921) skipped the R11 size rule silently;
and the tests cited above do not exercise a stat error at all. *This section was lost in an uncommitted overwrite (same
mechanism as BUG-0012 / BUG-0013; it is in no commit, checked 2026-11-15 in `4cee272` and `3f330bb`). It is rebuilt here
from the P0.05 task file §9.2 / §9.4, the CHANGELOG and the code; the original wording and its revised fix plan could
not be recovered (BUG-0031).*

**Fix (2026-11-15, P0.05 rework 2):** `taiji_ai/tools/repo_hygiene.py` — `collect_entries()` calls `stat()` once per
file: `FileNotFoundError` / `NotADirectoryError` give size `None` (listed by git, missing on disk), a non-regular entry
gives `0`, any other `OSError` is collected as `(path, reason)`. `main()` prints `Error: cannot stat <path>: <reason>`
for each, still prints the violations it found, and returns 2 — never 0 or 1 when a file could not be checked.
**Verified:** agent, 2026-11-15 — `tests/unit/test_repo_hygiene.py::test_bug_0009_*` (7 cases: stat errors exit 2 and name
the file, the error wins over violations but both are reported, a deleted file gets the path rules only, a directory
entry is not an error, an oversized existing file is still flagged); 4 of the 7 failed on the first fix (`P0.05.md` §5);
re-run 2026-11-15 in X.07: 7 passed; full gate 10/10 PASS.

**History:**

- 2026-11-14 OPEN → PLANNED → IN_PROGRESS → FIXED — first fix, verified with tests that did not exercise a stat error.
- 2026-11-15 FIXED → IN_PROGRESS — the P0.05 re-review found the first fix incomplete; revised fix plan written (its
  text is lost, see the re-review above).
- 2026-11-15 IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in P0.05 rework 2; see Fix and Verified above.
- 2026-11-15 (X.07, BUG-0031) this section was brought back in line with the summary table; it had reverted to the
  2026-11-14 state.

### BUG-0008 — `test_t_tool_01_check_script_parses_cleanly_in_powershell` passes `[ref]$null`, silently ignoring syntax errors

| Field           | Value                                                                                |
| --------------- | ------------------------------------------------------------------------------------ |
| Severity        | S2 (test hole: contract test for script syntax cannot fail when syntax error exists) |
| Status          | CLOSED                                                                               |
| Found in        | Task P0.05 rework, `taiji_ai/tests/contract/test_check_script.py:34-45`              |
| Found by / date | agent (maintainer review), 2026-11-14                                                |
| Affects         | Contract test T-TOOL-01                                                              |

**Description:** `test_t_tool_01_check_script_parses_cleanly_in_powershell` called
`[System.Management.Automation.Language.Parser]::ParseFile(..., [ref]$null, [ref]$null)` in PowerShell.
`Parser::ParseFile` does not throw on syntax errors; it outputs errors to the 3rd parameter (`[ref]$errors`).
Passing `[ref]$null` causes PowerShell to ignore syntax errors, and the process exits 0 even if `check.ps1`
contains severe syntax errors.

**Steps to reproduce:** run PowerShell `[Parser]::ParseFile` with `[ref]$null` on a file with syntax errors;
exit code is 0 and no error is raised.

**Expected:** syntax errors are collected into `$errors` and cause the command to write errors and exit with non-zero.
**Actual:** syntax errors are discarded and test passes unconditionally.

**Root cause:** passing `[ref]$null` to `out ParseError[] errors`.

**Fix plan:**

1. Update `test_t_tool_01_check_script_parses_cleanly_in_powershell` to capture `$tokens` and `$errors`, assert
   `$errors.Count -eq 0`, and write error messages if `$errors.Count -gt 0`.
2. Add a test case asserting that a script with syntax errors causes the parser check to fail.

**Fix:** task P0.05, ~~2026-11-14 — captured `[ref]$errors`, asserted `$errors.Count -eq 0` and added
`test_t_tool_01_syntax_error_is_caught_by_parser`~~ (superseded in rework 2) 2026-11-15 — both parse tests use one
`parse_errors()` helper (`PARSE_CMD`, script path via `TAIJI_PARSE_TARGET`, errors printed as `ParseError:`); the
negative control is `test_t_tool_01_parse_check_detects_syntax_errors`.
**Verified:** agent, 2026-11-15 — the negative control fails when the shared helper passes `[ref]$null`; the positive
test passes on `check.ps1` (re-verified 2026-11-15 in the P0.06 rework, BUG-0012).

**History:**

- 2026-11-14 OPEN → PLANNED → IN_PROGRESS → FIXED — fixed and verified with negative syntax test.
- 2026-11-15 FIXED → VERIFIED → CLOSED — re-review mutation check: the real T-TOOL-01 parse test fails when pointed
  at a broken `.ps1` and passes on `check.ps1`. In rework 2 both parse tests were moved onto one `parse_errors()`
  helper (script path via an environment variable, errors printed as `ParseError:`), so the negative control now
  exercises the same code as the positive test.
- 2026-11-15 (P0.06 review) — this detail section had been overwritten with a stale copy (BUG-0013) and the
  shared-helper regression test deleted (BUG-0012). Restored in the P0.06 rework (R1/R2): the CLOSED history line
  above is the verbatim 2026-11-15 text; test file restored and mutation-checked again.

### BUG-0007 — `taiji_ai/README.md` Status says "Vitest 9"; the suite has 11 tests

| Field           | Value                                                             |
| --------------- | ----------------------------------------------------------------- |
| Severity        | S3 (stale documentation, AGENTS.md §4.3)                          |
| Status          | CLOSED                                                            |
| Found in        | Task P0.05 analysis, `taiji_ai/README.md` Status table, row "web" |
| Found by / date | agent (Claude Code), 2026-11-14                                   |
| Affects         | Documentation only                                                |

**Description:** the Status row for `web` says "done, tested (Vitest 9, real-browser smoke)". `pnpm test` reports
11 tests (2 files). The two BUG-0005 regression tests were added after the README row was written.

**Steps to reproduce:** `cd taiji_ai\web; pnpm test` → "Tests 11 passed (11)"; compare with the README row.

**Expected:** README matches the suite. **Actual:** README says 9.

**Root cause:** a hard-coded test count in a status table goes stale whenever a test is added.

**Fix plan:**

1. Change: remove hard-coded counts from the README Status rows (state + test IDs/kind only); the live counts are
   in the `tools/check.ps1` output and in the task files.
2. Regression check: manual — README Status rows contain no test counts after the fix.
3. Data/report impact: none.

**Fix:** task P0.05, 2026-11-14 — removed hard-coded test counts from README status rows  
**Verified:** agent, 2026-11-14 — README Status table verified manually; no hard-coded test numbers remain

**History:**

- 2026-11-14 OPEN → PLANNED — found during P0.05 analysis (baseline run of `pnpm test`); fix scheduled in P0.05 (README is edited there anyway).
- 2026-11-14 IN_PROGRESS → FIXED → VERIFIED → CLOSED — verified in P0.05.

### BUG-0006 — `atomic_save_npz` silently drops an array named `allow_pickle`; object arrays are pickled into files `np.load` cannot read

| Field           | Value                                                                                                    |
| --------------- | -------------------------------------------------------------------------------------------------------- |
| Severity        | S3 (latent: the only caller is a unit test; would be S1 "lost data" if a pipeline stage used such a key) |
| Status          | CLOSED                                                                                                   |
| Found in        | Task P0.05 analysis — `mypy src` reports `arg-type` at `taiji_ai/src/taiji_ai/store/artifacts.py:51`     |
| Found by / date | agent (Claude Code), 2026-11-14                                                                          |
| Affects         | `store.artifacts.atomic_save_npz` (future `pose_raw.npz`, `pose_masked.npz`, … writers)                  |

**Description:** `atomic_save_npz(path, **arrays)` forwards `**arrays` to
`np.savez_compressed(file, *args, allow_pickle=True, **kwds)` (NumPy 2.5.4). (1) An array passed under the key
`allow_pickle` binds to that parameter instead of being stored: the archive is written without it and no error is
raised. (2) Object-dtype arrays are pickled, but `np.load` defaults to `allow_pickle=False`, so such an artifact cannot
be read back without enabling pickle loading.

**Steps to reproduce (minimal):**

1. `atomic_save_npz(tmp / "bug.npz", kp=np.zeros(3), allow_pickle=np.arange(4.0))`
2. `sorted(np.load(tmp / "bug.npz").files)` → `['kp']` (reproduced 2026-11-14).

**Expected:** every passed array is stored, or the call fails loudly. **Actual:** the `allow_pickle` array is silently dropped.

**Root cause:** keyword-argument collision between caller array names and `np.savez_compressed`'s own `allow_pickle`
parameter; the default `allow_pickle=True` also permits pickled object arrays.

**Fix plan:**

1. Change: call `np.savez_compressed(buf, allow_pickle=False, **arrays)` — a key named `allow_pickle` (or `file`) then
   raises `TypeError` (duplicate keyword) and object arrays raise `ValueError` at write time; docstring states the
   reserved names and the no-pickle rule. If mypy still reports `arg-type`, add an explicit reserved-key check that
   raises `ValueError` and a narrowly scoped `# type: ignore[arg-type]` with a comment.
2. Regression tests (written first, shown failing on the old code): `tests/unit/test_core.py::
test_bug_0006_reserved_key_raises` (`pytest.raises((TypeError, ValueError))`) and
   `test_bug_0006_object_array_rejected` (`pytest.raises(ValueError)`); `mypy src` clean.
3. Data/report impact: none — no run artifacts exist yet; the only caller is `tests/unit/test_core.py`.

**Fix:** task P0.05, 2026-11-14 — explicit reserved-key check and object-dtype check in atomic_save_npz; allow_pickle=False; mypy ignore with comment  
**Verified:** agent, 2026-11-14 — test_bug_0006_reserved_key_raises and test_bug_0006_object_array_rejected failed on old code, pass now; mypy src clean

**History:**

- 2026-11-14 OPEN → PLANNED — found by `mypy src` during P0.05 analysis, reproduced in a scratch directory; fix scheduled in P0.05.
- 2026-11-14 IN_PROGRESS → FIXED — regression tests red → green, mypy src clean.
- 2026-11-14 VERIFIED → CLOSED — full gate passes; closed in P0.05.

### BUG-0005 — `apiGet` drops `Headers`-object headers and reports aborted requests as `network_error`

| Field           | Value                                                                            |
| --------------- | -------------------------------------------------------------------------------- |
| Severity        | S3 (no caller affected yet; would mislead error handling and drop headers later) |
| Status          | CLOSED                                                                           |
| Found in        | Task P8.02 self-review, `taiji_ai/web/src/api/client.ts`                         |
| Found by / date | agent (Claude Code), 2026-11-14                                                  |
| Affects         | Web API client (all future API calls)                                            |

**Description:** (1) headers were merged with `{ Accept, ...init?.headers }`; spreading a `Headers` instance yields
`{}`, so caller headers passed as `Headers` were silently dropped. (2) any `fetch` rejection, including the
`AbortError` raised when react-query cancels a query (unmount, refetch), was converted to
`ApiError("network_error")`, i.e. a deliberate cancellation looked like a lost connection.

**Steps to reproduce:** `apiGet("/api/x", { headers: new Headers({ "X-A": "1" }) })` → request has no `X-A`;
abort the signal during `fetch` → rejection is `ApiError(network_error)` instead of an `AbortError`.

**Expected:** caller headers kept (any `HeadersInit` form); aborts propagate unchanged.
**Actual:** as described.

**Root cause:** object spread used on `HeadersInit`; catch-all `catch {}` around `fetch`.

**Fix plan:**

1. Change: build headers with `new Headers(init?.headers)` and set `Accept` only if absent; in the `fetch` catch,
   re-throw `AbortError` (`DOMException` name `AbortError`) unchanged, map only other failures to `network_error`.
2. Regression tests: `tests/client.test.ts` — "keeps caller headers given as a Headers object" and
   "propagates AbortError unchanged".
3. Impact: none (no released callers).

**Fix:** task P8.02, 2026-11-14 — `new Headers(init?.headers)` + `Accept` default; `AbortError` re-thrown  
**Verified:** agent, 2026-11-14 — both regression tests failed on the old code (null header; ApiError instead of AbortError) and pass after the fix; Vitest 11/11

**History:**

- 2026-11-14 OPEN → PLANNED — found in P8.02 self-review; fix in P8.02 before closing.
- 2026-11-14 IN_PROGRESS → FIXED → VERIFIED → CLOSED — regression tests red → green.

### BUG-0004 — `Settings.device` reads `TAIJI_DEVICE` at import time, not at construction

| Field           | Value                                                      |
| --------------- | ---------------------------------------------------------- |
| Severity        | S3 (configuration surprise; no wrong data produced so far) |
| Status          | CLOSED                                                     |
| Found in        | Task P8.01 analysis, `taiji_ai/src/taiji_ai/config.py:21`  |
| Found by / date | agent (Claude Code), 2026-11-14                            |
| Affects         | `Settings.device` (pose device selection)                  |

**Description:** `device: str = os.environ.get("TAIJI_DEVICE", "cuda")` is evaluated once when the module is
imported, while `data_dir`/`models_dir` use `default_factory` and read the environment when `Settings()` is built.
Setting `TAIJI_DEVICE` after import (tests, worker bootstrap) is silently ignored.

**Steps to reproduce:** import `taiji_ai.config`; set `os.environ["TAIJI_DEVICE"]="cpu"`; `Settings().device` → `"cuda"`.

**Expected:** `"cpu"`. **Actual:** `"cuda"`.

**Root cause:** plain default instead of `field(default_factory=...)`.

**Fix plan:**

1. Change: `device` (and the new `api_port`) use `default_factory` reading the environment.
2. Regression test: `tests/unit/test_config.py::test_bug_0004_env_read_at_construction` (monkeypatch env after import).
3. Impact: none on stored data.

**Fix:** task P8.01, 2026-11-14 — `device`, `api_port`, `web_dist_dir` use `default_factory`  
**Verified:** agent, 2026-11-14 — `tests/unit/test_config.py::test_bug_0004_env_read_at_construction` passes (would fail on the old code: `device` stayed "cuda", fields did not exist)

**History:**

- 2026-11-14 OPEN → PLANNED — found during P8.01 analysis; fix in P8.01.
- 2026-11-14 IN_PROGRESS → FIXED → VERIFIED → CLOSED — regression test passes.

### BUG-0003 — New `.markdownlint.jsonc` re-enabled MD013 (line length) warnings

| Field           | Value                                                             |
| --------------- | ----------------------------------------------------------------- |
| Severity        | S3 (tooling noise; introduced by task X.04 step 0)                |
| Status          | CLOSED                                                            |
| Found in        | Task X.04, after closing: IDE diagnostics on `Docs/tasks/X.04.md` |
| Found by / date | agent (Claude Code), 2026-11-14                                   |
| Affects         | Editor diagnostics only                                           |

**Description:** after adding the workspace `.markdownlint.jsonc` (MD060 off), the editor started reporting MD013
(line length 80) on every long line, which it had not done before.

**Root cause (inferred):** a workspace markdownlint config replaces the editor's own markdownlint settings, which
evidently had MD013 disabled; the new file only disabled MD060.

**Fix plan:**

1. Change: `.markdownlint.jsonc` → `"default": true`, `"MD013": false`, `"MD060": false`.
2. Regression check: edit a long-line doc and confirm no MD013 in the diagnostics.
3. Impact: none on content.

**Fix:** task X.04, 2026-11-14  
**Verified:** agent, 2026-11-14 — VS Code diagnostics for `Docs/tasks/X.04.md` after an edit: no MD013, no MD060; only pre-existing MD032/MD040 remain

**History:**

- 2026-11-14 OPEN → PLANNED → FIXED — introduced and fixed in X.04 (X.04 had been marked DONE; reopened note in task file).
- 2026-11-14 VERIFIED → CLOSED — diagnostics checked.

### BUG-0002 — TECH_WORKFLOW stack table still says "Python 3.11 hoặc 3.12" after DEC-0002

| Field           | Value                                                                    |
| --------------- | ------------------------------------------------------------------------ |
| Severity        | S3 (stale documentation, AGENTS.md §4.3)                                 |
| Status          | CLOSED                                                                   |
| Found in        | Task X.04 self-review, `Docs/TECH_WORKFLOW_V1.md` §1.1 row "Ngôn ngữ"    |
| Found by / date | agent (Claude Code), 2026-11-14                                          |
| Affects         | Documentation only; readers could think the Python version is still open |

**Description:** the stack table said "Python 3.11 hoặc 3.12 … Chốt một bản cho cả nhóm", although DEC-0002
(2026-11-13) fixed Python 3.12 and §12 #1 of the same document was already marked as decided.

**Steps to reproduce:** compare TECH_WORKFLOW §1.1 row "Ngôn ngữ" with DEC-0002 and §12 #1.

**Expected:** row states Python 3.12 (decided).  
**Actual:** row still listed two options.

**Root cause:** when DEC-0002 was recorded, only §12 (open decisions) was updated, not the §1.1 table.

**Fix plan:**

1. Change: row → "Python 3.12 … Đã chốt (DEC-0002)".
2. Regression check: grep TECH_WORKFLOW for "3.11" after the fix (only the historical §12 row may remain).
3. Data/report impact: none.

**Fix:** task X.04, 2026-11-14  
**Verified:** agent, 2026-11-14 — row updated; grep shows "3.11" only in the §12 decision-history row

**History:**

- 2026-11-14 OPEN → PLANNED → FIXED → VERIFIED → CLOSED — found and fixed during X.04 self-review.

### BUG-0001 — Dataset registry header says no dataset downloaded (stale)

| Field           | Value                                                                        |
| --------------- | ---------------------------------------------------------------------------- |
| Severity        | S3 (stale documentation, AGENTS.md §4.3)                                     |
| Status          | CLOSED                                                                       |
| Found in        | Task X.03, `Docs/DATASET_REGISTRY_TAIJI.md` line 3                           |
| Found by / date | agent (Claude Code), 2026-11-13                                              |
| Affects         | Documentation only; a reader could think UMONS/TaiForm were never downloaded |

**Description:** line 3 states "Chưa tải hoặc nhận bộ dữ liệu nào", but D12 (UMONS) and D09 (TaiForm annotations)
were downloaded on 2026-11-13 and the same table marks them **Đã tải**.

**Steps to reproduce:** open the registry; compare line 3 with the "Trạng thái" column of D12/D09.

**Expected:** header reflects the current download/access state.  
**Actual:** header still describes the state before the downloads.

**Root cause:** the header was written when the registry was created; the later download step updated the table
rows but not the header (no rule then required re-checking headers).

**Fix plan:**

1. Change: rewrite line 3 to state what is downloaded (UMONS, TaiForm annotations/criteria) and what is pending
   (access-controlled sets), with the date.
2. Regression check: during X.03 verification, grep the header and compare with the table (manual, documentation).
3. Data/report impact: none.

**Fix:** task X.03, 2026-11-14 — header rewritten (downloaded D12/D09, pending D06/D10/D11) and rule pointer added  
**Verified:** agent, 2026-11-14 — header line 3 lists D12 and D09 as downloaded; both table rows say **Đã tải** (2 matches)

**History:**

- 2026-11-13 OPEN → PLANNED — found during X.03 analysis; fix scheduled in X.03.
- 2026-11-14 IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and checked in X.03.

<!--
Copy this block for each new bug, newest at the top of this section.

### BUG-NNNN — <short title>

| Field | Value |
|---|---|
| Severity | S1 / S2 / S3 |
| Status | OPEN / PLANNED / IN_PROGRESS / FIXED / VERIFIED / CLOSED / WONT_FIX |
| Found in | <task ID, file:line, or "user report"> |
| Found by / date | <who>, <YYYY-MM-DD> |
| Affects | <module / data / reports> |

**Description:**

**Steps to reproduce (minimal):**
1.

**Expected:**
**Actual:**

**Root cause:** (unknown yet / analysis)

**Fix plan:**
1. Change: …
2. Regression test: <test ID + what it asserts>
3. Data/report impact & cleanup: …

**Fix:** task <ID> / commit <hash> / date
**Verified:** <who>, <date>, <test output summary>

**History:**
- <YYYY-MM-DD> OPEN — …
-->
