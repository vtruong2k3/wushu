# X.10 — Drop the "machine B" part of the P0 acceptance (scope change)

| Field             | Value                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------ |
| Status            | DONE (2026-11-15)                                                                                      |
| Owner             | agent (Claude Code)                                                                                    |
| Phase             | Ad-hoc (documentation and decision only)                                                               |
| Estimate          | 0.1 day                                                                                                |
| Depends on        | X.07 DONE (checked 2026-11-15)                                                                         |
| Plan confirmed by | Maintainer, 2026-11-15 (scope change approved by them in the conversation) |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                                |

## 1. Analysis

**Goal:** record that the P0 acceptance no longer needs a gate run on a second machine, because the maintainer has one
machine only, and make the tracking files say so.

**Why a task and a decision:** AGENTS.md §4.1 "Scope change → `IMPLEMENTATION_PLAN_V1.md` (mark the change with date) +
`DECISIONS.md`". The change is to an acceptance criterion, so it needs the maintainer's approval (given above).

**In scope:**

1. `Docs/IMPLEMENTATION_PLAN_V1.md` §4 "Nghiệm thu P0": the old sentence is struck through, the new one is dated.
2. `Docs/tracking/DECISIONS.md`: DEC-0015.
3. Live-state places that still show the item as open: `TASK_STATUS.md` rows P0.05 and P0.07; the open-item lines in
   `Docs/tasks/P0.05.md` §8, `Docs/tasks/P0.07.md` §8 and §9.5 (F-6), `Docs/tasks/X.07.md` §8, `CHANGELOG.md` X.07 entry.
   Each gets a dated note; the original text stays (AGENTS.md §4.3: append-only, superseded text struck through).
4. `CHANGELOG.md`: one X.10 entry that lists the superseded places.

**Out of scope:**

- Any code, any test, any change of `tools/check.ps1`. No commit (CLAUDE.md).
- X.08 (CI) is not started. It is the only way to get a run in a second, clean environment (a GitHub runner), so the
  decision mentions it as optional; whether to do it stays the maintainer's call.
- Other pending items (BUG-0032) and the paused `/usage` and skill-settings work are untouched.

**Facts checked 2026-11-15:**

| Fact | Source |
| ---- | ------ |
| P0.01–P0.07 are DONE; the gate is 10/10 PASS on this machine (last run after X.07, 14.7 s) | `TASK_STATUS.md`, gate run |
| A full gate on cold caches already passed once here (73.8 s, `P0.05.md` §9.1 V-01) | `P0.05.md` §9.1 |
| "machine B" occurs in: plan §4 (the acceptance sentence), `P0.05.md` (lines 23, 132, 376, 551, 574-575), `P0.07.md` (509, 588, 613), `X.07.md` (33, 183, 203), `CHANGELOG.md` (17, 150), `TASK_STATUS.md` (rows P0.05, P0.07). Nothing in `AGENTS.md`, `CLAUDE.md`, README or any script | `grep` over `*.md/*.ps1/*.py/*.json/*.toml/*.yml`, 2026-11-15 |
| "A" and "B" in the plan's owner columns are people, not machines: not touched | plan §3 and §4 tables |

**Constraints that apply:** AGENTS.md §4.1, §4.3 (append-only); §5 nothing is presented as verified that was not
(the decision says what is no longer checked); no absolute personal paths in docs.

**Residual risk (goes into DEC-0015):** an install from `uv.lock` plus the gate is no longer required to pass on a
second environment, so a hidden dependence on this machine (paths, driver, cached packages) would go unseen. Mitigation
already in place: the gate's preflight, `uv lock --check`, and one cold-cache pass; optional: X.08.

## 2. Plan

**Files to create / modify:**

| File | Change |
| ---- | ------ |
| `Docs/tasks/X.10.md` | new (this file) |
| `Docs/tracking/TASK_STATUS.md` | row X.10; P0.05 and P0.07 rows: the open-item sentence replaced by the dropped note |
| `Docs/IMPLEMENTATION_PLAN_V1.md` | §4 "Nghiệm thu P0": struck-through old text + dated new text |
| `Docs/tracking/DECISIONS.md` | DEC-0015; next free ID DEC-0016 |
| `Docs/tasks/P0.05.md`, `P0.07.md`, `X.07.md` | dated notes on the open items listed above |
| `Docs/tracking/CHANGELOG.md` | X.10 entry; one note under the X.07 entry |

**Implementation steps:**

1. Re-read this file and each target region against the current files (§3).
2. Plan §4 sentence; DEC-0015.
3. TASK_STATUS rows; task-file notes; CHANGELOG.
4. Checks C-1..C-4, gate, `git diff` self-review.
5. Close.

**Test plan:** documentation task, manual checks.

| Check | What it verifies |
| ----- | ---------------- |
| C-1 | `grep "machine B\|máy B\|máy A và B"`: every remaining hit is history followed or preceded by a dated note (X.10 / DEC-0015), or text that quotes the change (this file, DEC-0015, the X.10 entry) |
| C-2 | Plan §4 shows the old sentence struck through and the new dated one; the second sentence (synthetic generator) is unchanged |
| C-3 | `DECISIONS.md`: DEC-0015 present, "Next free ID" is DEC-0016, the row has 6 columns |
| C-4 | Full gate 10/10 PASS; `git status` lists only the files of the table above plus those of X.07 (still uncommitted) |

**Acceptance criteria:**

- [x] AC1 Plan §4 acceptance sentence says the gate passes on the maintainer's single machine (dated, old text kept).
- [x] AC2 DEC-0015 records the decision, the reason, the residual risk and the optional X.08 (C-3).
- [x] AC3 No live-state place (TASK_STATUS, an unticked open item) still asks for a run on machine B (C-1).
- [x] AC4 Gate 10/10 PASS; only the planned files changed; no commit (C-4).

**Impact / rollback:** documentation only. Rollback = `git checkout` of the files above (X.07's uncommitted edits are in
some of the same files, so rollback must be per hunk, not per file).

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK. Checked against the files: plan §4 line 140 holds the old sentence; the "machine B" hits
  are exactly those of §1 (P0.05 lines 23, 132, 376, 551, 575; P0.07 509, 588, 613; X.07 33, 183, 203; CHANGELOG 17,
  150; TASK_STATUS rows P0.05 and P0.07); `DECISIONS.md` next free ID is DEC-0015; `git status` shows only the X.07
  files (uncommitted) and this file. No change to the plan.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1    | 2026-11-15 | Plan re-read (§3). |
| 2    | 2026-11-15 | Plan §4 acceptance sentence: old text struck through, dated Vietnamese note added (one-machine rule, residual risk, X.08 as optional cover); the second sentence (F-SYN scenarios) unchanged. DEC-0015 written, next free ID DEC-0016. |
| 3    | 2026-11-15 | TASK_STATUS rows P0.05 and P0.07: open sentence struck through with the dropped note. Dated notes in `P0.05.md` §8, `P0.07.md` §8 and the F-6 row of §9.5, `X.07.md` (three places), `CHANGELOG.md` under the X.07 entry. History that mentions machine B (P0.05 §1 / R7 / "not covered", P0.07 §9 review text, CHANGELOG 2026-11-15 P0.05 entry) is kept. |
| 4    | 2026-11-15 | Checks C-1..C-4 and the gate (§5). **Found:** an IDE warning MD032 at plan line 409 that is in `HEAD` and is not in X.10's only hunk (line 140): registered as BUG-0033 (S3, planned), not fixed here. |
| 5    | 2026-11-15 | Self-review of the `git diff` (§6); close-out. No deviation from the plan. |

## 5. Verification

Full gate (`tools\check.ps1`, this machine) after the edits of steps 2–3, exit 0:

```text
QUALITY GATE SUMMARY
------------------------------------------------------------
uv-lock            PASS          0.1s
ruff-check         PASS          0.1s
ruff-format        PASS          0.1s
mypy               PASS          0.3s
pytest             PASS         10.4s
web-lint           PASS          1.6s
web-typecheck      PASS          1.6s
web-test           PASS          2.1s
web-build          PASS          1.9s
repo-hygiene       PASS          0.1s
------------------------------------------------------------
RESULT: PASS (10/10) in 18.9s
```

(Afterwards only two one-line notes in `X.07.md` and the close-out text of the tracking files were written; the gate was
run once more at the very end, result in the close-out report.)

| Check | Result |
| ----- | ------ |
| C-1   | `grep -rnE "machine B\|máy B\|máy A và B" Docs`: plan line 140 (struck through + note); `P0.05.md` lines 23, 132, 376, 551 (history) and 575-576 (note); `P0.07.md` 509 (struck through), 589 (review text, row 614 carries the note); `X.07.md` 33, 183, 203 (each with the note); `CHANGELOG.md` 17-18 (note) and 151 (history); `TASK_STATUS.md` rows P0.05 and P0.07 (struck through); this file and DEC-0015 (quote the change). No live-state place still asks for the run |
| C-2   | Plan §4: old sentence struck through, dated note, second sentence unchanged (`git diff -U0`: one hunk, line 140) |
| C-3   | `DECISIONS.md`: DEC-0015 present, next free ID `DEC-0016`, the row splits into 6 columns |
| C-4   | `git status`: modified plan, P0.05, P0.06, P0.07, BUGS, CHANGELOG, DECISIONS, TASK_STATUS (P0.06 and part of the others are X.07's uncommitted work); new `X.07.md`, `X.10.md`. No `src/`, `tests/`, `tools/` file; nothing committed |

## 6. Self-review

- Files reviewed (`git diff -U0` of the plan, P0.05, P0.07; the DEC-0015 row and the CHANGELOG / TASK_STATUS lines read
  again after the edits): plan, `P0.05.md`, `P0.07.md`, `X.07.md`, `DECISIONS.md`, `TASK_STATUS.md`, `CHANGELOG.md`, this file.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ (the criterion is changed in the plan, the decision and every live
  place; nothing else in the plan changed) · edge cases ☑ (history kept, struck through not deleted; "A" and "B" as
  owner columns left alone; no code or script mentioned machine B) · no fabricated data ☑ (DEC-0015 states the residual
  risk and cites the one cold-cache pass that exists, `P0.05.md` §9.1 V-01; it does not claim a second environment was
  tested) · errors surfaced ☑ · tests cover criteria ☑ (documentation task: C-1..C-4 and the gate) · no personal data ☑
  (no names, emails or paths; the maintainer's sentence is not quoted since X.11) · docs updated ☑.
- Findings: BUG-0033 (pre-existing MD032 in plan §14.3), registered. *(2026-11-15, X.11: the maintainer's wording had
  been quoted in DEC-0015 and in the header of this file; both quotes were cut at the maintainer's request.)*
- Not covered: no cross-environment run; that is the accepted risk of DEC-0015. X.08 (CI) would give one and is not started.

## 7. Bugs

| Bug ID   | Severity | Status  | Note                                                                                             |
| -------- | -------- | ------- | ------------------------------------------------------------------------------------------------ |
| BUG-0033 | S3       | PLANNED | pre-existing MD032 in plan §14.3, found while editing line 140; registered, not part of this task |

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass (gate 10/10 PASS)
- [x] No open S1/S2 bug from this task (BUG-0033 is S3, pre-existing, planned)
- [x] TASK_STATUS.md updated (X.10 DONE, P0.05 and P0.07 rows)
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated (DEC-0015); README needs no change (it never mentioned machine B)
