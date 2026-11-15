# Contributing

The binding rules are in **[AGENTS.md](AGENTS.md)** (humans and AI agents alike). This page is a short summary.

## Every change is a task

1. Pick a task from `Docs/tracking/TASK_STATUS.md` (or create an ad-hoc `X.NN` row first).
2. Analyze and write the plan in `Docs/tasks/<TASK-ID>.md` (template: `Docs/tasks/_TEMPLATE.md`).
3. Re-read the plan right before coding; implement step by step.
4. Run the checks, then review your own diff against the plan.
5. Register every defect in `Docs/tracking/BUGS.md` (`BUG-NNNN`) with a fix plan.
6. Close the task: TASK_STATUS, `Docs/tracking/CHANGELOG.md`, README/DECISIONS if needed.

## Setup

```powershell
cd taiji_ai
py -3.12 -m uv sync
.venv\Scripts\python.exe tools\fetch_models.py      # one-time model download (hash-verified)
cd web; pnpm install --frozen-lockfile; cd ..
```

## Checks before a pull request

Run the one-command quality gate from `taiji_ai/`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check.ps1
```

(Machine without a supported GPU: append `-NoGpu`).

Under the hood, the gate runs:
- `uv lock --check`
- `.venv\Scripts\python.exe -m ruff check src tests tools`
- `.venv\Scripts\python.exe -m ruff format --check src tests tools`
- `.venv\Scripts\python.exe -m mypy src`
- `.venv\Scripts\python.exe -m pytest -rs` (all tests)
- `cd web; pnpm lint; pnpm typecheck; pnpm test; pnpm build`
- `.venv\Scripts\python.exe tools\repo_hygiene.py`

## Branches, commits, pull requests

- Branch from `main`: `feat/<TASK-ID>-short-name` or `fix/BUG-NNNN-short-name`.
- Commit message: `<TASK-ID|BUG-ID>: <imperative summary>`; one task or bug per PR where possible.
- PR description: task ID, what changed, evidence (test output, numbers, screenshots), risks, link to the task file.
- Before staging: `git add --dry-run .` — no data, videos, model weights, datasets, `node_modules` or `dist`.
- Never force-push `main`.
