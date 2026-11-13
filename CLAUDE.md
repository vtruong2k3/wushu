# CLAUDE.md

All repository rules live in AGENTS.md and are mandatory:

@AGENTS.md

## Claude Code specifics

- **Lifecycle is not optional.** For every task: analyze → write the plan in `Docs/tasks/<TASK-ID>.md` →
  update `Docs/tracking/TASK_STATUS.md` → **Read the task file again right before the first code edit** →
  implement → run checks → re-read your own changes → register bugs → close. Do not skip steps for "small" tasks.
- If the user asks for work that has no task ID, create an ad-hoc task (`X.<NN>`, AGENTS.md §2.2) first and say so.
- Keep a todo list mirroring the plan's numbered steps while implementing; tick them as you go.
- Self-review means actually re-reading the changed files or the diff, not summarizing from memory.
- Found a bug (yours or pre-existing)? Add it to `Docs/tracking/BUGS.md` with a fix plan **before** moving on,
  and tell the user its ID.
- At the end of each task, report to the user: status, what changed (files), test evidence, bugs (IDs), and
  which tracking files were updated.
- Run Python through `taiji_ai\.venv\Scripts\python.exe`; run uv as `py -3.12 -m uv`.
- Never execute code from `repos/` or files from `datasets/`; read them only.
- Before using any third-party repo, package, model or dataset, apply AGENTS.md §9: check its license tier and
  allowed use, read the existing notes (`REPOS.md`, `DATASET_REGISTRY_TAIJI.md`, `THIRD_PARTY_NOTICES.md`),
  and do not trust its self-reported metrics.
- Do not commit or push unless the user explicitly asks.
- Communication: the maintainer writes in Vietnamese — reply in Vietnamese unless asked otherwise.
  Code, comments, commit messages and rule files are in English.
