# X.02 — Move the git repository root to the workspace (`wushu/`)

| Field | Value |
|---|---|
| Status | DONE |
| Owner | agent (Claude Code) |
| Phase | ad-hoc |
| Estimate | 0.25 day |
| Depends on | X.01 (DONE) |
| Plan confirmed by | Maintainer, 2026-11-13 ("có" to the proposal) |
| Started / Done | 2026-11-13 / 2026-11-13 |

## 1. Analysis

**Goal:** version `AGENTS.md`, `CLAUDE.md`, `Docs/` and `taiji_ai/` in one git repository rooted at `d:\workspaces\wushu`.

**In scope:** remove the empty `taiji_ai/.git`, `git init` at the root, root `.gitignore`, verification, doc updates.
**Out of scope:** first commit (task P0.04, needs explicit maintainer request), remote setup.

**Facts checked (2026-11-13):**
- `taiji_ai/.git`: branch `master` with no commits, 0 refs, 0 stashes, 0 objects (`git count-objects -v`),
  empty `FETCH_HEAD`, only default local config. Deleting it loses nothing.
- Root is not a git repo. Root contains `AGENTS.md`, `CLAUDE.md`, `Docs/` (264 KB), `datasets/` (1.2 GB),
  `repos/` (315 MB, 7 nested clones with their own `.git`), `taiji_ai/` (2.7 GB, mostly `.venv` and models).
- `taiji_ai/.gitignore` already excludes `.venv/`, `data/*` (keeps `.gitkeep`), `models/*.onnx`; nested
  `.gitignore` files keep working inside the root repository.

**Constraints:** AGENTS.md §5.9 (no datasets, videos, model weights, participant data in git), §5.11 (third-party
repos read-only), §8 (agents don't commit unless asked).

**Risks:** nested clones under `repos/` would appear as embedded repositories (gitlinks) if not ignored → ignore
`repos/` entirely. Large binaries accidentally tracked → verify with `git add --dry-run`.

## 2. Plan

**Files:**

| File | Change |
|---|---|
| `taiji_ai/.git/` | delete (empty repo) |
| `.git/` (root) | `git init -b main` |
| `.gitignore` (root) | new: `repos/`, `datasets/`, `.venv/`, Python caches, OS/editor files, safety patterns for media/weights |
| `AGENTS.md` | §1 note repo root; §8 confirm root-level repo |
| `Docs/IMPLEMENTATION_PLAN_V1.md` | §2 status row "Git" |
| `Docs/tracking/*` | TASK_STATUS (X.02), CHANGELOG, DECISIONS (DEC-0006) |

**Steps:**
1. Delete `taiji_ai/.git` (re-check emptiness right before).
2. `git init -b main` at the root.
3. Write root `.gitignore`.
4. Verify: `git status`, `git add --dry-run .`; assert nothing from `repos/`, `datasets/`, `.venv/`, `taiji_ai/data/`
   (except `.gitkeep`), no `*.onnx`, `*.mp4`, `*.zip`, `*.rar`, `*.npz`; total dry-run size small (< 5 MB).
5. Update docs and tracking.

**Acceptance criteria:**
- [x] Root is a git repo on branch `main`; `taiji_ai/` is a normal subdirectory (no nested `.git`).
- [x] Dry-run add lists only source, tests, tools, config, docs, `uv.lock`, `models/registry.json`, `.gitkeep`s,
      plus `repos/*/REPOS.md` and `datasets/*/README.md`.
- [x] No ignored-category file appears in the dry run.
- [x] Tests still pass from `taiji_ai/`.
- [x] Tracking files updated.

## 3. Plan re-read (before coding)

- 2026-11-13: re-read against current state. **Change:** ignoring `repos/` and `datasets/` wholesale would also
  drop the provenance docs `repos/*/REPOS.md` and `datasets/*/README.md` (md5, licenses, naming). Use
  `/repos/*/*` + `!/repos/*/REPOS.md` and `/datasets/*/*` + `!/datasets/*/README.md` instead: nested clones and
  data folders stay ignored (never scanned, so their `.git` is invisible), the docs are tracked.
  Acceptance criterion 2 extended accordingly. Rest of the plan OK.

## 4. Implementation log

| Step | Done | Notes |
|---|---|---|
| 1 | ✓ | Re-checked right before deletion: `count-objects` = 0, no refs → removed `taiji_ai/.git` |
| 2 | ✓ | `git init -b main` at `D:/workspaces/wushu` |
| 3 | ✓ | Root `.gitignore` with the patterns from §3 (plan re-read) plus caches, OS/editor files, safety net for media/weights/archives/arrays/sqlite |
| 4 | ✓ | Verification below. The first forbidden-file grep mixed `-E` and `-P` and errored, so its "(none)" was a false pass; re-run with `-P` only (exit 1 = no match). The first personal-data scan printed `cut`'s exit code; re-run with `grep -l` (xargs exit 123 = no file matched) |
| 5 | ✓ | AGENTS.md §1/§8, IMPLEMENTATION_PLAN §2, DECISIONS (DEC-0006), TASK_STATUS, CHANGELOG |

**Process deviation (recorded for transparency):** the first version of this file was written with status DONE and all
boxes ticked before execution. It was reset to `PLAN_READY` before any change was made, and results were filled in only
after verification.

## 5. Verification

```
git add --dry-run .                     -> 52 files, total 484,475 bytes (largest: taiji_ai/uv.lock 144,843 B)
forbidden-pattern grep (-P)             -> exit 1 (no match): no .venv, clone content, dataset data, taiji_ai/data
                                           (except .gitkeep), *.onnx/*.mp4/*.zip/*.rar/*.npz/*.npy/*.parquet/*.sqlite3/*.pyc
files outside expected roots            -> none
git check-ignore                         -> repos/taolu/Sports2D, datasets/taiji/umons, taiji_ai/.venv,
                                           taiji_ai/data/app.sqlite3, taiji_ai/models/*.onnx all ignored
personal-data grep (username, email, C:/Users, AppData) -> no file matched
tracked notes                           -> repos/sanda/REPOS.md, repos/taolu/REPOS.md, datasets/taiji/README.md
pytest (taiji_ai)                       -> 12 passed
git status                              -> branch main, all files untracked, nothing staged, no commit
```

## 6. Self-review

- Files reviewed: root `.gitignore`, full dry-run file list (52 entries), AGENTS.md §1 and §8 edits,
  IMPLEMENTATION_PLAN §2 row, DECISIONS/TASK_STATUS/CHANGELOG entries.
- Checklist: correctness ✓ · edge cases (nested clones, nested `.gitignore`, `.gitkeep` exceptions, provenance docs) ✓ ·
  no fabricated data n/a · errors surfaced ✓ (two broken verification commands caught and re-run) ·
  no personal data in tracked files ✓ · docs updated ✓
- Findings: verification commands must not end with `|| echo "(none)"` without checking the command's own exit code;
  this is a process lesson, not a repository defect, so no BUG entry.

## 7. Bugs

| Bug ID | Severity | Status | Note |
|---|---|---|---|
| — | | | none in repository code or config |

## 8. Close-out

- [x] Acceptance criteria met (§5)
- [x] Checks pass (pytest 12 passed)
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] DECISIONS.md updated (DEC-0006)
