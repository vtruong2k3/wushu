# Changelog — code and documentation history

Newest first. One entry per completed task or bug fix (format: `AGENTS.md` §4.2).

---

## 2026-11-15 — P0.06 Unified logging and path redaction — rework after review, closed (DONE)

- Reopened 2026-11-15 by the review (task file §9): a redactor leak (BUG-0014), and P0.05 files and history
  overwritten during P0.06 (BUG-0012, BUG-0013). Closed after the rework R1–R9 (§9.4, §9.5).
- Fixed: BUG-0014 and BUG-0015 (`taiji_ai/src/taiji_ai/logs.py`: `PathRedactor` is one left-to-right pass with
  quote-aware path ends — UNC with spaces / Vietnamese / `c$`, apostrophes and `repr` spellings are redacted whole,
  `repr` tails of known roots are kept; POSIX personal prefixes only with POSIX path syntax, keyword `posix_paths`,
  default off on Windows), BUG-0017 (`run_log` writes its end line on `KeyboardInterrupt`/`SystemExit` too),
  BUG-0016 (`tests/conftest.py`: shared `clean_logging` + autouse logging-state guard), BUG-0012 (P0.05
  `tests/contract/test_check_script.py`, `test_repo_hygiene_git.py` restored verbatim), BUG-0013 (CHANGELOG P0.05
  entries, BUG-0008 detail, BUGS next free ID, TASK_STATUS date restored)
- Changed: `logs.py` docstrings (format, placeholders, end rules, limits, threads); level names limited to the five
  documented ones; unsafe-root check fails closed; `tests/unit/test_logs.py` (41 tests), `tests/api/test_api_core.py`
  (fixture use, traceback assertion); `Docs/TECH_WORKFLOW_V1.md` §10.1, `taiji_ai/README.md`, `DECISIONS.md`
  DEC-0012, `IMPLEMENTATION_PLAN_V1.md` T-CORE-01 (wording with limits, dated)
- Tests: red first (18 failed + 3 errors on the unfixed code); full gate 10/10 PASS in 19.0 s (137 pytest,
  11 Vitest); mutations M1–M9 all caught, files restored hash-equal; BUG-0010 / BUG-0008 mutation checks re-run on the
  restored P0.05 tests; real-API smoke re-run
- Bugs: BUG-0012..BUG-0017 CLOSED (BUG-0011 closed in the first pass)
- Decisions: DEC-0012 (corrected)
- Open: maintainer to confirm Q1–Q6 explicitly (task file F-8); commits
- Commit: not committed
- Plan: `Docs/tasks/P0.06.md` (§9 review, §9.4 rework plan, §9.5 resolution, §5 rework evidence)

## 2026-11-15 — P0.06 Unified logging and path redaction (DONE; reopened, superseded by the entry above)

- **Reopened 2026-11-15 by the review** (`Docs/tasks/P0.06.md` §9): status back to IN_PROGRESS; BUG-0012..0017
  registered. Claims below that the review disproved: ~~"two-pass path redaction prevents personal path leakage"~~
  (BUG-0014: UNC and apostrophe paths leak); ~~`tests/contract/test_check_script.py` "fixed … environment
  inheritance"~~ (that was P0.05 rework 2; the file was overwritten with an older version, BUG-0012). This entry is
  superseded by the rework entry above.

- Added: `taiji_ai/src/taiji_ai/logs.py` (`PathRedactor`, `RunContextFilter`, `RunMatchFilter`, `RedactingFormatter`, `configure_logging`, `run_log`, `current_run_id`), `taiji_ai/tests/unit/test_logs.py` (T-CORE-01a..n, 21 tests)
- Changed: `taiji_ai/src/taiji_ai/config.py` (`log_level` field, default `"INFO"`), `taiji_ai/src/taiji_ai/api/app.py` (redacted error boundary for BUG-0011), `taiji_ai/src/taiji_ai/api/__main__.py` (`configure_logging` before uvicorn, `log_config: None` in `server_config()`), `taiji_ai/tests/api/test_api_core.py` (T-CORE-01o..p, T-API-04b, BUG-0011 red-first tests), `taiji_ai/tests/unit/test_config.py` (`TAIJI_LOG_LEVEL` tests), `taiji_ai/tests/contract/test_check_script.py` (fixed `TAIJI_CHECK_RUNNING` environment inheritance in child runner)
- Behaviour: unified ISO-8601 logging across application, uvicorn and background runs; per-run `run.log` written in append mode; two-pass path redaction prevents personal path leakage across console, file logs, tracebacks, warnings and API errors
- Tests: T-CORE-01 (a..p), T-API-04b, BUG-0011 regression tests pass; mutation checks M1..M4 verified; full quality gate 10/10 PASS in 26.4s
- Bugs: BUG-0011 (closed in this task)
- Decisions: DEC-0012
- Commit: not committed
- Plan: `Docs/tasks/P0.06.md`

## 2026-11-15 — P0.05 One-command quality gate `tools/check.ps1` — rework after re-review, closed (DONE)

- Reopened 2026-11-15 by the re-review (task file §9): BUG-0009's fix was incomplete, BUG-0010 and findings F-3..F-12
  were new; both bugs were introduced by this task, so it could not stay DONE/IN_REVIEW. Closed after rework 2.
- Fixed: BUG-0009 (`tools/repo_hygiene.py`: one `stat()` per file via `collect_entries()`; any file that cannot be
  stat'ed gives exit 2 naming the file, never 0 or 1), BUG-0010 (`tools/check.ps1`: nested-run guard checked before
  preflight; the test no longer starts a real gate run), BUG-0008 (closed: shared `parse_errors()` helper with a
  negative control)
- Changed: `tools/check.ps1` (`[n/N]` from the step count; relative interpreter path in the plan; `Get-UvLauncher`
  shared by the step and preflight; header prints Python, uv, Node, pnpm versions), `store/artifacts.py` (unneeded
  `type: ignore` removed, docstring), `tests/contract/test_check_script.py` (9 tests), `tests/unit/test_repo_hygiene.py`
  (51 tests, 7 for BUG-0009), `tests/contract/test_repo_hygiene_git.py` (no `git commit`), `tests/unit/test_core.py`
  (BUG-0006 tests check `ValueError` and the message), `taiji_ai/README.md` (gate in its own section after the web
  setup), `Docs/IMPLEMENTATION_PLAN_V1.md` (date markers, T-TOOL rows), `Docs/tracking/DECISIONS.md` (DEC-0011 note)
- Tests: `tools\check.ps1` full run 10/10 PASS in 14.6 s warm (73.8 s cold), pytest 91 passed, Vitest 11 passed,
  0 hygiene violations; regression tests written and run red first (5 failures on the unfixed code); mutation check of
  the guard test; fault injection (lint error), stale lock, `-SkipWeb`, `-NoGpu` from `%TEMP%`, nested run, empty root
- Bugs: BUG-0008, BUG-0009, BUG-0010 CLOSED (with BUG-0006, BUG-0007 from the original task)
- Not covered: a run on machine B (maintainer); GitHub Actions CI (follow-up)
- Commit: not committed
- Plan: `Docs/tasks/P0.05.md` (§3.1 rework plan, §4 step 13, §5 rework-2 evidence, §9 re-review)

## 2026-11-14 — P0.05 One-command quality gate `tools/check.ps1` (IN_REVIEW; superseded by the 2026-11-15 entry above)

- Added: `taiji_ai/tools/check.ps1` (10-step quality gate: uv-lock, ruff-check, ruff-format, mypy, pytest, web-lint, web-typecheck, web-test, web-build, repo-hygiene; Windows PowerShell 5.1 compatible, ASCII-only, Out-Host stream isolation), `taiji_ai/tools/repo_hygiene.py` (rules R1–R11, 5 MB limit), `tests/contract/test_check_script.py` (T-TOOL-01..03, 5 tests), `tests/unit/test_repo_hygiene.py` (T-TOOL-04, 44 tests), `tests/contract/test_repo_hygiene_git.py` (T-TOOL-05, CLI subprocess contract)
- Fixed: BUG-0006 (`atomic_save_npz` keyword reserved check and object-dtype rejection; `tests/unit/test_core.py`), BUG-0007 (removed hard-coded test counts in `taiji_ai/README.md`), BUG-0008 (T-TOOL-01 captures `[ref]$errors` and added negative syntax test), ~~BUG-0009 (`repo_hygiene.py` no longer swallows stat errors on existing files)~~ (incomplete, see 2026-11-15)
- Changed: `AGENTS.md` §7, `CLAUDE.md`, `CONTRIBUTING.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (§4, §15.1, §16.3), `Docs/TECH_WORKFLOW_V1.md` line 57
- Decisions: DEC-0011
- Tests: all 10 gate steps pass in 13.2s (79 python tests, 11 vitest tests, 0 hygiene violations); ~~full verification matrix V-01..V-15 verified on machine A~~ (overstated: V-02, V-09, V-13 were not run as described; verified 2026-11-15, see task file §5 and §9)
- Commit: not committed
- Plan: `Docs/tasks/P0.05.md` (status: IN_REVIEW)

## 2026-11-14 — X.06 Usable repositories recorded in the docs (DONE)

- Usable items from X.05 (already cloned, git-ignored): `repos/taolu/tpz` (MPL-2.0, E04 reference) and
  `repos/taolu/_no-license/wushu_vision` (ideas only)
- Changed: `repos/taolu/REPOS.md` (summary: rubric row + new E04 row), `Docs/TECH_WORKFLOW_V1.md` §11 E04,
  `taiji_ai/THIRD_PARTY_NOTICES.md` §6
- Commit: `ce859b4` (X.05 + X.06 documentation, pushed) + follow-up commit recording the push verification
- Plan: `Docs/tasks/X.06.md`

## 2026-11-14 — X.05 Survey of additional Wushu repositories (DONE)

- Reviewed 17 GitHub repositories + 3 external links (static reading only); verdicts in `repos/taolu/REPOS.md`
- Cloned (git-ignored): `repos/taolu/tpz` (MPL-2.0; IWUF 2024 deduction/nandu JSON, IWUF rule PDFs) and
  `repos/taolu/_no-license/wushu_vision` (reference only)
- Registered dataset D14 (S3GCN Tai Chi with expert scores, research-only, on request) in `Docs/DATASET_REGISTRY_TAIJI.md`
- Commit: not committed
- Plan: `Docs/tasks/X.05.md`

## 2026-11-14 — P0.04 First commit and push to GitHub (DONE)

- Remote: `origin` = `https://github.com/vtruong2k3/wushu.git`; branch `main` tracks `origin/main`
- Commit `8fae211` (initial, 92 files): everything recorded in this changelog up to P8.02. Earlier entries that say
  "Commit: not committed" are included in this commit
- Added: `.gitattributes` (LF normalization), `CONTRIBUTING.md`
- Verification: secret scan clean, no data/weights/clones/datasets/venv/node_modules/dist in the tree, remote HEAD ==
  local HEAD
- Commit: `8fae211` + this follow-up commit (records the push verification)
- Plan: `Docs/tasks/P0.04.md`

## 2026-11-14 — P8.02 Web scaffold: React + Vite + TypeScript (DONE)

- Added: `taiji_ai/web/` — Vite 8 + React 19 + TS 6, React Router 8, TanStack Query 5; typed API client
  (`src/api/client.ts`, backend error format → `ApiError`), `useHealth`, layout, status page (Vietnamese UI),
  404 page; Vitest + Testing Library tests; ESLint; `pnpm-workspace.yaml` with `minimumReleaseAge` 7 days; lockfile
- Changed: root `.gitignore` (node_modules, web/dist, tsbuildinfo, coverage, playwright output); `THIRD_PARTY_NOTICES`
  §2b (web deps, license totals, accepted advisory); README (web commands, status); AGENTS §7; TASK_STATUS P0.05 note
- Tests: Vitest 11 passed; lint/typecheck clean; build OK; FastAPI serves the build; headless Edge renders live data;
  Python 27 passed
- Bugs: BUG-0005 (S3) found in self-review, fixed with regression tests, closed
- Decisions: DEC-0010
- Commit: not committed
- Plan: `Docs/tasks/P8.02.md`

## 2026-11-14 — P8.01 FastAPI skeleton, Streamlit removed (DONE)

- Added: `taiji_ai/src/taiji_ai/api/` — `app.py` (factory, lifespan: migrations + one-time model verification),
  `errors.py` (uniform JSON errors, no traceback leak), `static.py` (web/dist + SPA fallback, `/api/*` stays JSON,
  no-cache index, traversal-safe), `routers/health.py` (`GET /api/health`), `__main__.py` (`python -m taiji_ai.api`,
  127.0.0.1 only); tests `tests/api/test_api_core.py` (T-API-01..04), `tests/unit/test_config.py`
- Changed: `config.py` (`web_dist_dir`, `api_port` default 8007, `API_HOST`; env read at construction — BUG-0004);
  `pyproject.toml` (− streamlit, + fastapi 0.162.6, uvicorn 0.54.0, dev httpx2 2.16.0); README, THIRD_PARTY_NOTICES,
  env_check, AGENTS §7, hardware inventory
- Removed: `taiji_ai/app/` (Streamlit placeholder)
- Tests: 27 passed; ruff clean; real-server smoke (thread + `python -m taiji_ai.api`) OK, health 2.2 ms avg
- Bugs: BUG-0004 (S3) fixed and closed
- Decisions: DEC-0009 (port 8007, httpx2)
- Commit: not committed
- Plan: `Docs/tasks/P8.01.md`

## 2026-11-14 — X.04 UI stack switched to React + Vite + FastAPI: decision and re-plan (DONE)

- Decision: DEC-0008 — React + Vite + TypeScript SPA, FastAPI backend serving `/api` and `web/dist`; Streamlit and
  Next.js rejected for the MVP
- Changed: `Docs/TECH_WORKFLOW_V1.md` → v1.1 (stack, rejected options, W3 video player, code tree with `api/` and
  `web/`, process model, environments, license table, E02); `Docs/IMPLEMENTATION_PLAN_V1.md` (new P8: 16 tasks,
  13.75 days; totals ≈ 54 days; API/Web/E2E test IDs; G04 row; timeline; risks); `AGENTS.md` §5.7 and §7;
  `Docs/tracking/TASK_STATUS.md` (P8 regenerated, 100 tasks)
- Added: `.markdownlint.jsonc` (MD060 off — table pipe style only)
- Bugs: BUG-0002 (S3, stale Python row) found and closed; BUG-0003 (S3, MD013 re-enabled by the new lint config) introduced, fixed and closed
- Not yet changed: code still uses Streamlit until P8.01/P8.02
- Commit: not committed
- Plan: `Docs/tasks/X.04.md`

## 2026-11-14 — X.03 Rules for third-party code, models and datasets (DONE)

- Changed: `AGENTS.md` — new §9 _Third-party code, models and datasets_ (license tiers, repositories, weights,
  datasets, own recordings, where to record); "When in doubt" renumbered §9 → §10 (no existing reference used §9);
  §1 table and §5.10/§5.11 point to §9
- Added: `taiji_ai/THIRD_PARTY_NOTICES.md` (direct deps with metadata licenses, NVIDIA proprietary CUDA/cuDNN wheels,
  FFmpeg CLI, model weights, copied code = none, reference-only sources)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md` — column "Mục đích được phép" for every dataset, new row D08 (own recordings),
  header rewritten; `taiji_ai/pyproject.toml` — pytest marker `dataset`; `CLAUDE.md` — pointer to §9
- Tests: pytest 12 passed; ruff clean; `uv lock --check` unchanged; `§` references verified; git dry-run 54 files,
  no forbidden files
- Bugs: BUG-0001 (S3, stale registry header) found and closed in this task
- Decisions: DEC-0007
- Commit: not committed
- Plan: `Docs/tasks/X.03.md`

## 2026-11-13 — X.02 Git repository moved to the workspace root (DONE)

- Removed: `taiji_ai/.git` (empty: 0 commits, 0 refs, 0 objects — verified before deletion)
- Added: root git repository (`git init -b main`), root `.gitignore`
  (ignores `repos/*/*` except `REPOS.md`, `datasets/*/*` except `README.md`, `.venv`, caches, media/weights/archives/arrays)
- Changed: `AGENTS.md` §1 (repo root note), §8 (single repo, dry-run before staging);
  `Docs/IMPLEMENTATION_PLAN_V1.md` §2 (Git row); `Docs/tracking/DECISIONS.md` (DEC-0006)
- Verification: `git add --dry-run .` → 52 files, ≈ 484 KB, largest `taiji_ai/uv.lock` 145 KB;
  forbidden-pattern grep → no match; personal-data grep → no match; `check-ignore` confirms clones, dataset data,
  `.venv`, `app.sqlite3`, `*.onnx` ignored; `pytest` 12 passed
- Bugs: none
- Commit: not committed (first commit is P0.04, awaits maintainer request)
- Plan: `Docs/tasks/X.02.md`

## 2026-11-13 — X.01 Repository working rules and tracking files (DONE)

- Added: `AGENTS.md`, `CLAUDE.md` (imports AGENTS.md), `Docs/tasks/_TEMPLATE.md`, `Docs/tracking/TASK_STATUS.md`,
  `Docs/tracking/BUGS.md`, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/DECISIONS.md`
- Behaviour: mandatory task lifecycle (analyze → plan → re-read → code → self-review → close),
  bug register with fix plans, history updates
- Tests: n/a (documentation)
- Commit: not committed

## 2026-11-13 — P0.01–P0.03 Code base foundation (DONE, recorded retroactively)

Done before the task lifecycle existed; no per-task plan files.

- Added: `taiji_ai/pyproject.toml`, `uv.lock`, package skeleton `src/taiji_ai/{io,pose,store,…}`,
  `io/probe.py`, `io/frames.py`, `pose/skeleton.py`, `pose/registry.py`, `pose/rtm.py`, `store/artifacts.py`,
  `store/db.py`, `migrations/0001_init.sql`, `tools/fetch_models.py`, `tools/env_check.py`, `app/Home.py`,
  tests (`tests/conftest.py`, `tests/unit/test_core.py`, `tests/contract/test_video_io.py`,
  `tests/contract/test_pose_gpu.py`)
- Environment: Python 3.12.10, uv 0.13.8, onnxruntime-gpu 1.32.0 [cuda,cudnn], rtmlib 0.0.16, PyAV 19.0.2,
  OpenCV headless 4.14 (held < 5)
- Models: YOLOX-m HumanArt + RTMPose-m body7-halpe26 fetched, SHA-256 in `models/registry.json`
- Tests: 12 passed (T-IO-01..05, T-POSE-01..03, T-STORE-01..03, skeleton); ruff clean;
  GPU smoke: det 29 ms/frame, pose 5 ms/person on RTX 3060
- Docs: `Docs/hardware_inventory.md`; decisions DEC-0001..0005
- Commit: not committed (`git init` only)

## 2026-11-13 — Documentation baseline

- `Docs/WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md` (provided), `Docs/TECH_WORKFLOW_V1.md`, `Docs/IMPLEMENTATION_PLAN_V1.md`,
  `Docs/DATASET_REGISTRY_TAIJI.md`, `datasets/taiji/README.md`, `repos/taolu/REPOS.md`, `repos/sanda/REPOS.md`
