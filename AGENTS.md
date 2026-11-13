# AGENTS.md — Working Rules for This Repository

These rules apply to every contributor, human or AI agent (Claude Code, Codex, Cursor, …).
They are mandatory. If a rule blocks you, stop and ask the maintainer instead of skipping it.

---

## 1. Project at a glance

Taijiquan (Wushu Taolu) video-analysis MVP:
video → HALPE_26 pose → quality masks → 3 metrics → reference comparison → coach review → report.

| Path | What it is |
|---|---|
| `Docs/WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md` | Product scope, gates G00–G05 |
| `Docs/TECH_WORKFLOW_V1.md` | Architecture, workflow W0–W9, data contracts, metric formulas |
| `Docs/IMPLEMENTATION_PLAN_V1.md` | Phases P0–P11, task list, test plan (test IDs `T-*`, `B-*`, `UAT-*`) |
| `Docs/tracking/TASK_STATUS.md` | **Live status of every task** (single source of truth for progress) |
| `Docs/tracking/BUGS.md` | **Bug register** (every bug, its ID, its fix plan) |
| `Docs/tracking/CHANGELOG.md` | **Code history**: one entry per completed task / bug fix |
| `Docs/tracking/DECISIONS.md` | Technical/product decisions and their reasons |
| `Docs/tasks/<TASK-ID>.md` | Per-task analysis, plan, implementation log, self-review |
| `Docs/tasks/_TEMPLATE.md` | Template for the file above |
| `taiji_ai/` | Python code base (package `src/taiji_ai`, tests, tools, app) |
| `taiji_ai/THIRD_PARTY_NOTICES.md` | Third-party packages, tools, weights and copied code used by the code base (§9) |
| `Docs/DATASET_REGISTRY_TAIJI.md` | Datasets: license, access status, **allowed use** (§9.4) |
| `repos/` | Third-party repositories — **read-only reference, never execute** |
| `datasets/` | Downloaded datasets — **read-only, license-restricted, never commit** |

The git repository root is this workspace root. `repos/*/*` and `datasets/*/*` are ignored except our own notes
(`repos/*/REPOS.md`, `datasets/*/README.md`); see `.gitignore`.

---

## 2. The task lifecycle (mandatory)

Every piece of work is a **task** with an ID. Work that is not in `IMPLEMENTATION_PLAN_V1.md` gets a new ID
(see §2.2) **before** any code is written. No code without a task. No task closed without review.

```
TODO → ANALYZING → PLAN_READY → IN_PROGRESS → IN_REVIEW → DONE
                       ↑              │              │
                       └── plan changes ─┘   bugs found ─┘ (back to IN_PROGRESS)
Any state → BLOCKED (with reason)        Any state → CANCELLED (maintainer approval)
```

### Step 1 — Analyze (status `ANALYZING`)

1. Read the task row in `Docs/IMPLEMENTATION_PLAN_V1.md` and every section it references in
   `Docs/TECH_WORKFLOW_V1.md` / the v3 plan.
2. Read the existing code, tests and artifacts the task touches. Do not assume; open the files.
3. Write down in `Docs/tasks/<TASK-ID>.md` (copy `_TEMPLATE.md`):
   - goal and scope (in / out),
   - inputs, outputs, interfaces, data contracts, units, coordinate conventions,
   - dependencies and their actual state (are they really DONE?),
   - constraints from §5 that apply,
   - unknowns, risks, open questions (ask the maintainer if they change the design).
4. Set the task to `ANALYZING` in `Docs/tracking/TASK_STATUS.md`.

### Step 2 — Plan (status `PLAN_READY`)

In the same task file, write a **detailed plan**:

- design (functions/classes, signatures, data flow), files to create/modify,
- numbered implementation steps small enough to verify one by one,
- test plan: which test IDs from the implementation plan (`T-…`), new tests to add, fixtures, tolerances,
- acceptance criteria (copied from the plan + anything added),
- rollback / impact on other modules.

Set status `PLAN_READY`. If the task is ≥ 1 day or changes a data contract/schema, get maintainer
confirmation of the plan before coding (note who/when in the task file).

### Step 3 — Re-read the plan, then code (status `IN_PROGRESS`)

1. **Before writing any code, re-read the whole task file** and check every step against the current code
   (things may have changed since planning). Record `Plan re-read: <date> — OK` or the corrections made.
   If the plan must change, update the plan first, then code.
2. Implement step by step, in plan order. Keep tests next to the code they cover.
3. Log in the task file's *Implementation log*: what was done per step, deviations from the plan and why.

### Step 4 — Verify and self-review (status `IN_REVIEW`)

1. Run the checks (§7): lint, format, unit/contract/golden tests; GPU tests if the task touches pose/ORT.
2. **Review everything written in this task**: re-read the full diff (`git diff`/changed files) against the
   plan and the review checklist below. Record findings in the task file's *Self-review* section.
3. Review checklist:
   - [ ] Does the code do exactly what the plan and acceptance criteria say? Nothing missing, nothing extra?
   - [ ] Edge cases: empty input, NaN, single frame, VFR timestamps, missing joints, rotated video, errors.
   - [ ] No fabricated data (no forward-fill / zero-fill presented as observations), units documented.
   - [ ] Errors are raised or reported, never swallowed (`except: pass` is forbidden).
   - [ ] Tests cover every acceptance criterion and fail when the behaviour breaks.
   - [ ] No secrets, participant data, real names, or absolute personal paths in code, tests, logs or docs.
   - [ ] Docs, docstrings, README status, tracking files updated.
4. Any defect found → §3 (bug register) **immediately**. A defect in code written by this task must be fixed
   (back to `IN_PROGRESS`) before the task can be `DONE`.

### Step 5 — Close (status `DONE`)

A task may be marked `DONE` only when **all** are true:

- [ ] All acceptance criteria met, with evidence (test output, numbers, screenshots) in the task file.
- [ ] All checks pass (§7).
- [ ] Self-review complete and clean; no open S1/S2 bug caused by this task.
- [ ] `Docs/tracking/TASK_STATUS.md` updated (status, date, evidence link).
- [ ] `Docs/tracking/CHANGELOG.md` entry added (§4.2).
- [ ] `taiji_ai/README.md` *Status* table updated if a module's state changed.
- [ ] Decisions taken during the task recorded in `Docs/tracking/DECISIONS.md`.

### 2.1 Status values

| Status | Meaning |
|---|---|
| `TODO` | Not started |
| `ANALYZING` | Reading requirements/code, writing the analysis |
| `PLAN_READY` | Detailed plan written (and confirmed if required); no code yet |
| `IN_PROGRESS` | Coding against the re-read plan |
| `IN_REVIEW` | Checks + self-review running |
| `DONE` | Closed per §2 Step 5 |
| `BLOCKED` | Cannot continue; reason and unblocking action written in TASK_STATUS |
| `CANCELLED` | Dropped with maintainer approval; reason recorded |

### 2.2 New / ad-hoc tasks

- Work not in the plan gets the ID `X.<NN>` (next free number) and a row in `TASK_STATUS.md` under
  *Ad-hoc tasks*, with a one-line reason, **before** starting.
- Bug fixes use the bug's own lifecycle (§3); if a fix is large (> 0.5 day) also open a task `X.<NN>` and link it.
- Split any task estimated > 2 days into sub-tasks `<ID>a`, `<ID>b`, … and list them in TASK_STATUS.

---

## 3. Bug register (mandatory)

Every defect — found in review, in tests, by the user, or in existing code — goes to `Docs/tracking/BUGS.md`.
**No bug may be left without a fix plan.**

### 3.1 Rules

1. **ID**: `BUG-NNNN`, sequential, zero-padded, never reused, never renumbered (e.g. `BUG-0007`).
2. **Record immediately** when found, before continuing other work.
3. Required fields: ID, title, severity, status, found in (task ID / file), found by, date, description,
   steps to reproduce (minimal), expected vs actual, root cause (when known), **fix plan**, fix task/commit,
   regression test, verified date.
4. **Severity** (from `IMPLEMENTATION_PLAN_V1.md` §16.2):

   | Level | Definition | Handling |
   |---|---|---|
   | **S1** critical | Wrong person, wrong timestamp, lost data/reviews, fabricated data, personal-data leak | Stop other work; fix now; regression test mandatory |
   | **S2** major | Wrong metric in a condition, wrong abstain, UI does not save | Fix within the current task/sprint; regression test mandatory |
   | **S3** minor | Display, wording, non-critical performance | Plan the fix; schedule it |

5. **Lifecycle**: `OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED`.
   - `PLANNED` requires a written fix plan (cause hypothesis, change, test).
   - `VERIFIED` requires the regression test passing and a second look at the fix.
   - `WONT_FIX` only with maintainer approval and a written reason.
6. Bugs introduced by the current task block that task's `DONE`. Pre-existing bugs found elsewhere are
   registered, planned, and scheduled (link the task that will fix them).
7. Every fix commit/changelog entry references the bug ID.

---

## 4. Documentation and history (mandatory)

### 4.1 What to update and when

| Event | Update |
|---|---|
| Start analyzing a task | `TASK_STATUS.md` (status), create `Docs/tasks/<ID>.md` |
| Plan written / changed | `Docs/tasks/<ID>.md` (plan, plan re-read note), `TASK_STATUS.md` |
| Bug found | `BUGS.md` (new entry with fix plan), task file *Bugs* section |
| Bug status changes | `BUGS.md` |
| Task done | `TASK_STATUS.md`, `CHANGELOG.md`, task file (evidence + review), README status if needed |
| Design/tech decision | `DECISIONS.md` (`DEC-NNNN`) and the relevant design doc |
| Scope change | `IMPLEMENTATION_PLAN_V1.md` (mark the change with date) + `DECISIONS.md` |

### 4.2 Changelog entry format (`Docs/tracking/CHANGELOG.md`, newest first)

```
## 2026-11-20 — P4.02 Short-gap interpolation (DONE)
- Changed: taiji_ai/src/taiji_ai/quality/gaps.py (new), tests/unit/test_gaps.py (new)
- Behaviour: gaps ≤ 150 ms interpolated with `interpolated` flag; longer gaps stay NaN
- Tests: T-QLT-03, T-QLT-04, T-QLT-05 pass; check.ps1 pass
- Bugs: BUG-0003 (fixed in this task)
- Commit: <hash or "not committed">
- Plan: Docs/tasks/P4.02.md
```

### 4.3 General documentation rules

- Dates are ISO `YYYY-MM-DD`. Times, when needed, include the timezone.
- History is append-only: do not delete past entries; mark superseded items (`~~text~~` + note).
- Keep docs in sync with code in the **same change**; a stale doc is a bug (S3).
- Documentation language: rule files in English; project docs may be Vietnamese or English, but be consistent
  within a file.

---

## 5. Engineering rules (non-negotiable)

1. **Never fabricate observations.** Missing/low-confidence joints are `NaN` with a reason. No forward-fill,
   no zero-fill presented as data. Short-gap interpolation is allowed only when flagged.
2. **Real timestamps.** Use PTS from PyAV (`t_sec = (pts − start_pts) × time_base`). Never assume constant fps.
3. **Keep layers separate.** Raw, mask and filtered pose are stored separately. Human reviews are stored in
   SQLite, never inside run artifact folders.
4. **Units and coordinates documented.** Metrics are computed in image pixels (y down) unless a documented
   calibration exists; every metric carries version, units, valid intervals, coverage and missing reason.
5. **No universal thresholds.** Thresholds come only from a signed `metric_record`; otherwise the metric is
   `experimental` and the report draws no conclusion.
6. **Models only from the verified registry.** No runtime downloads, never disable TLS/SSL verification.
7. **One GPU job at a time**; heavy work runs in the worker subprocess, never inside the FastAPI process.
   The web UI (React, `taiji_ai/web/`) talks only to the API (`/api/*`); the API binds to `127.0.0.1` only.
8. **Atomic writes** for every artifact and manifest; manifests written last.
9. **Privacy.** No participant data, real names, videos, model weights or datasets in git. Pseudonymous IDs only.
   Respect `consent_scope` (analysis / train / share).
10. **Licenses.** Follow the license tiers in §9.1. Do not copy code from repositories without a license
    (`repos/taolu/_no-license/`). Copied permissive code keeps its notice and is recorded in
    `taiji_ai/THIRD_PARTY_NOTICES.md` and `DECISIONS.md`.
11. **Untrusted third-party code and data.** Never run code from `repos/` or files from `datasets/` (§9.2, §9.4).
12. **Domain content needs the coach.** Thresholds, rubric text and feedback templates require coach (H) approval.

---

## 6. Code conventions

- Python 3.12, `taiji_ai/src/taiji_ai/...`; type hints on public functions; docstrings state units and
  coordinate conventions.
- Formatting/lint: `ruff` (line length 120). Tests: `pytest`; GPU tests marked `@pytest.mark.gpu`.
- Arrays: keypoints `(T, 26, 2)` float32 pixels, scores `(T, 26)`, `t_sec (T,)`, masks `(T, 26)`;
  NaN = not observed.
- Schemas: Pydantic v2 with `schema_version` in every persisted manifest.
- Errors: raise specific exceptions with actionable messages; no bare `except`.
- Tests live in `taiji_ai/tests/{unit,contract,golden,integration}`; test names reference test IDs where they exist
  (e.g. `test_t_qlt_04_long_gap_stays_nan`).

---

## 7. Commands (run from `taiji_ai/`)

```powershell
py -3.12 -m uv sync                                   # install / update env from uv.lock
.venv\Scripts\python.exe -m ruff check src tests tools
.venv\Scripts\python.exe -m ruff format --check src tests tools
.venv\Scripts\python.exe -m pytest                     # all tests (GPU tests auto-skip without CUDA/models)
.venv\Scripts\python.exe -m pytest -m "not gpu"
.venv\Scripts\python.exe tools\env_check.py --gpu-smoke
.venv\Scripts\python.exe -m taiji_ai.api              # FastAPI on http://127.0.0.1:8007 (TAIJI_API_PORT), serves web/dist
```

Web (run from `taiji_ai/web/`, Node ≥ 24, pnpm):

```powershell
pnpm install --frozen-lockfile
pnpm dev          # Vite dev server, proxies /api to 127.0.0.1:8007
pnpm lint; pnpm typecheck; pnpm test
pnpm build        # outputs web/dist, served by FastAPI
```

`tools/check.ps1` (task P0.05) will wrap lint + format + tests; once it exists it is the required gate.

---

## 8. Git

- One repository, rooted at the workspace root (`main` branch). Never run `git init` inside a subfolder;
  never add the third-party clones under `repos/` as submodules or embedded repos.
- Before staging, run `git add --dry-run .` and check that no data, video, weights or archives appear.
- Branch per task: `feat/<TASK-ID>-short-name`, `fix/BUG-NNNN-short-name`.
- Commit message: `<TASK-ID|BUG-ID>: <imperative summary>` (e.g. `P4.02: interpolate short gaps with flags`).
- One task (or one bug) per commit/PR when possible; reference the task file.
- Never commit `data/`, `models/*.onnx`, datasets or videos. Never force-push shared branches.
- AI agents: **do not commit or push unless the maintainer explicitly asks.**

---

## 9. Third-party code, models and datasets (mandatory)

Anything not written in this project — repositories, packages, model weights, datasets, papers' claims — is
third-party. Its license limits what we may do with it, and its quality must be verified, not assumed.
These rules are project policy, not legal advice; commercial release needs a separate license review (maintainer).

### 9.1 License tiers

| Tier | Examples in this project | Allowed | Not allowed |
|---|---|---|---|
| **Permissive code** (MIT, BSD, Apache-2.0, ISC) | rtmlib, QAQA, Pose2Sim, onnxruntime, PyAV | Use as dependency; copy code **with** its copyright/license notice; record in `THIRD_PARTY_NOTICES.md` + `DECISIONS.md` | Removing notices; copying without recording |
| **Weak copyleft** (LGPL, MPL-2.0) | tqdm (MPL-2.0 part), FFmpeg LGPL builds | Use unmodified as a library or separate process | Copying source into our files |
| **Strong copyleft** (GPL, AGPL) | Ultralytics YOLO (AGPL-3.0), pingouin (GPL-3.0), GPL FFmpeg builds as a CLI | Offline analysis scripts outside the product; calling a GPL CLI as a separate process | Importing into `taiji_ai/src`, shipping in the product or a hosted service |
| **No license** | Pang/Zhang repos, Motion Embedding (`repos/taolu/_no-license/`) | Read to learn methods; re-implement ideas from the paper in our own code, citing the source | Copying code, data, weights, file layouts verbatim |
| **Proprietary redistributable** | NVIDIA CUDA/cuDNN pip wheels | Install and use locally | Bundling into installers/containers without checking NVIDIA's redistribution terms |
| **Data: CC BY-NC / BY-NC-SA** | UMONS-TAICHI, fight-judge dataset | Development, testing, research benchmarks | Training models that ship in a commercial product; commercial use of derived artifacts |
| **Data: CC BY-SA** | OpenWushu content | Use with attribution | Derived content under a different license (share-alike applies) |
| **Data/weights: research-only or unclear** | RTMPose body7 weights, SMPL, MotionBERT H36M weights, TaiForm peer-review sample | Internal research/MVP use as documented | Commercial release before a license audit; redistribution |
| **Access-controlled data** | TaiChi-AQA, TaiChi-24, PSU-TMM100 | Only what the signed agreement allows | Use before access is granted; mirrors of unknown origin |

Unknown or conflicting license → treat as the most restrictive plausible tier and register a question in the task file.

### 9.2 Third-party repositories

1. **Check what we already know first:** `repos/*/REPOS.md` records commit, license, audit findings and what is
   reusable. Do not re-audit from scratch; extend the existing notes.
2. **Adding a repository:** clone into `repos/<area>/` with `git clone --depth 1` and hooks disabled
   (`-c core.hooksPath=/dev/null`); unlicensed ones go to `repos/<area>/_no-license/`. Record URL, commit, date,
   license and purpose in that area's `REPOS.md` in the same change.
3. **Static reading only.** Never import, install or execute third-party repo code (including notebooks and
   `setup.py`). If running it is truly needed (e.g. reproducing a baseline), get maintainer approval and run it in
   an isolated environment outside `taiji_ai/.venv`; record the reason and result.
4. **Do not trust self-reported results.** Third-party metrics, README claims and paper numbers are hypotheses until
   reproduced on our data with our splits. Known examples: leakage in fight-judge splits, duplicated scores in
   the Pang 2025 repo, hand-edited histogram counts in the Zhang 2022 notebook, unverified Sports2D defaults.
5. **Cite idea sources.** When a design or algorithm comes from a third-party source, write repo + commit + file
   (or paper DOI) in the task file and in a code comment near the implementation.
6. **Copying permissive code:** copy the smallest unit needed, keep the original notice in the file header, add an
   entry to `taiji_ai/THIRD_PARTY_NOTICES.md` (source, commit, license, files) and a `DEC-NNNN` decision.

### 9.3 Model weights

1. Fetch weights only with `taiji_ai/tools/fetch_models.py` (or an equivalent reviewed script) and register them in
   `taiji_ai/models/registry.json` with SHA-256, source URL and `license_note`. The pipeline loads only registered,
   hash-verified files (§5.6).
2. Every new model needs a tier from §9.1 recorded in `THIRD_PARTY_NOTICES.md` before it is used in a run.
3. Weights trained on research-only data are acceptable for the internal MVP; flag them in reports' model section.

### 9.4 Datasets

1. **Register before download.** Add or update the row in `Docs/DATASET_REGISTRY_TAIJI.md` (source, license, access
   status, **allowed use**) before fetching anything. Access-controlled data: only after access is granted, and the
   maintainer decides whether to apply — agents never submit request forms or e-mails.
2. **Download safely.** Into `datasets/<area>/<name>/raw/`, verify the published checksum, inspect archive member
   paths before extracting (no absolute paths or `..`), extract into `extracted/`. Never execute anything from a
   dataset. Record md5/sha, file list and license in `datasets/<area>/README.md`.
3. **Allowed use is explicit.** Each dataset is tagged with what it may be used for: `dev-test`, `benchmark`,
   `train`, `reference-only`, `not-usable`. Using it for anything else needs a registry update and maintainer approval.
4. **Never mix label spaces across routines or styles** (e.g. Bafa Wubu ≠ 24-form, Long Fist ≠ Taijiquan, Qigong ≠
   Taijiquan). Out-of-domain results are reported separately and never counted as product accuracy.
5. **Grouped splits.** Split by participant (then session, then source video) before any clipping or augmentation;
   all views of one performance stay in the same split; no test data in templates, scalers, thresholds or ensembles.
6. **Derived artifacts inherit restrictions.** Features, embeddings, references and models built from a dataset carry
   `data_sources` (dataset IDs + license) in their manifest; an NC source makes the artifact NC.
7. **Tests:** no dataset content in the repository or in test fixtures. Tests that need a local dataset use
   `@pytest.mark.dataset` and skip when the dataset is absent.
8. **Keep datasets out of git** (`/datasets/*/*` is ignored except `README.md`).

### 9.5 Our own recordings (Taiji24-Local / D08)

1. A recording enters the system only with a participant pseudonym and a consent reference.
2. `consent_train = 0` → never used for training or model selection; `consent_share = 0` → never leaves the
   controlled machine, never shown to other participants.
3. Withdrawal or deletion requests remove the recording and everything derived from it (§5.9, task P8.12).

### 9.6 Where to record

| What | File |
|---|---|
| Third-party repos (commit, license, audit, reuse verdict) | `repos/<area>/REPOS.md` |
| Packages, tools, weights, copied code actually used by `taiji_ai` | `taiji_ai/THIRD_PARTY_NOTICES.md` |
| Model files and hashes | `taiji_ai/models/registry.json` |
| Datasets (license, access, allowed use) | `Docs/DATASET_REGISTRY_TAIJI.md` |
| Downloaded files (checksums, structure) | `datasets/<area>/README.md` |
| Decisions to adopt/copy/reject a third-party component | `Docs/tracking/DECISIONS.md` |

---

## 10. When in doubt

Stop and ask. Record the question and the answer in the task file. A wrong assumption about timestamps,
identity or data provenance is worse than a delay.
