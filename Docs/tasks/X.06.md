# X.06 — Record the usable repositories from X.05 in the project docs and commit

| Field | Value |
|---|---|
| Status | DONE |
| Owner | agent (Claude Code) |
| Phase | ad-hoc |
| Estimate | 0.1 day |
| Depends on | X.05 (DONE) |
| Plan confirmed by | Maintainer 2026-11-14: "cái có dùng được thì clone về và cập nhật docs rồi commit lên" (commit + push requested) |
| Started / Done | 2026-11-14 / 2026-11-14 |

## 1. Analysis

- Usable items from X.05: `achushu/tpz` (MPL-2.0, reference for E04) and `klsnkmaria/wushu_vision` (no license,
  ideas only). Both already cloned in X.05 (`repos/taolu/tpz` @ e6df070, `repos/taolu/_no-license/wushu_vision`
  @ 82b99f0) and git-ignored; nothing else from the list is worth cloning (see X.05 verdicts).
- Docs not yet reflecting them: `repos/taolu/REPOS.md` summary table ("Tổng kết"), `Docs/TECH_WORKFLOW_V1.md` §11 E04
  row, `taiji_ai/THIRD_PARTY_NOTICES.md` §6 reference-only sources.
- Uncommitted from X.05: REPOS.md, DATASET_REGISTRY (D14), TASK_STATUS, CHANGELOG, `Docs/tasks/X.05.md`.

## 2. Plan

1. REPOS.md summary: add an E04 row (tpz deduction/nandu JSON, verify against official IWUF rules; PDFs © IWUF) and
   extend the rubric row with the stance-check idea from wushu_vision.
2. TECH_WORKFLOW §11 E04: reference tpz.
3. THIRD_PARTY_NOTICES §6: add tpz and wushu_vision.
4. Tracking (TASK_STATUS X.06, CHANGELOG).
5. `git add --dry-run` check (no clone contents), commit, push, verify remote == local.

**Acceptance criteria:**
- [x] The three docs mention tpz / wushu_vision consistently with X.05.
- [x] Commit pushed; remote HEAD == local HEAD; no clone or data files in the commit.

## 3. Plan re-read (before coding)

- 2026-11-14: re-read — OK.

## 4. Implementation log

| Step | Done | Notes |
|---|---|---|
| 1 | ✓ | REPOS.md: rubric row extended, E04 row added |
| 2 | ✓ | TECH_WORKFLOW §11 E04 |
| 3 | ✓ | THIRD_PARTY_NOTICES §6: tpz, wushu_vision |
| 4 | ✓ | TASK_STATUS, CHANGELOG |
| 5 | ✓ | see §5 |

## 5. Verification

- Dry run before commit: only documentation files; no `repos/*/*` clone content, no data (see command output in the session).
- Push: commit `ce859b4` pushed (`0ba768b..ce859b4 main -> main`); remote `refs/heads/main` == local HEAD `ce859b4`.
- **Process deviation:** the push criterion and DONE status were first ticked before pushing; reset to IN_REVIEW before committing.

## 6. Self-review

- Re-read the three edited rows; wording consistent with the X.05 verdicts (reference only, verify against official IWUF rules, PDFs © IWUF, wushu_vision thresholds not used).

## 7. Bugs

| Bug ID | Severity | Status | Note |
|---|---|---|---|
| — | | | none |

## 8. Close-out

- [x] Acceptance criteria met
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
