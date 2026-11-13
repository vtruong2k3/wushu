# Changelog — code and documentation history

Newest first. One entry per completed task or bug fix (format: `AGENTS.md` §4.2).

---

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

- Changed: `AGENTS.md` — new §9 *Third-party code, models and datasets* (license tiers, repositories, weights,
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
