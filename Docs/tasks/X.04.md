# X.04 — Switch the UI stack from Streamlit to React + Vite + FastAPI (decision and re-plan)

| Field | Value |
|---|---|
| Status | DONE |
| Owner | agent (Claude Code) |
| Phase | ad-hoc (affects P7, P8) |
| Estimate | 0.5 day |
| Depends on | X.03 (DONE) |
| Plan confirmed by | Maintainer chose "React + Vite + FastAPI" on 2026-11-14 |
| Started / Done | 2026-11-14 / 2026-11-14 |

## 1. Analysis

**Goal:** record the decision and update every design/plan document so the UI is a React (Vite, TypeScript) SPA
talking to a FastAPI backend, replacing Streamlit. Code changes are out of scope here (they are P8.01/P8.02).

**Why:** the hardest UI needs — frame-accurate time marking, two synchronized videos, charts synced to video —
are native in a browser app (`<video>`, `requestVideoFrameCallback`) and awkward in Streamlit (needed a custom
component). The pipeline stays Python, so a Python API (FastAPI) is required either way; Next.js would add a second
(Node) server and SSR features an internal single-machine app does not need.

**References to Streamlit found (grep 2026-11-14, excluding repos/datasets/.venv):**
- `AGENTS.md:209` (§5.7), `AGENTS.md:244` (§7 commands)
- `Docs/TECH_WORKFLOW_V1.md`: lines 48 (stack), 100 (W3 table), 165–167 (W3 text), 402 (tree), 412–414 (process
  model), 451 (env table), 610 (license table)
- `Docs/IMPLEMENTATION_PLAN_V1.md`: P8 table (299–310), 382 (UI test tier), 671 (risk), totals table, §17 timeline,
  §15.10 UI test table, §15.9/15.8 task refs to P8 numbers
- Code (handled in P8.01/P8.02): `taiji_ai/pyproject.toml`, `taiji_ai/app/Home.py`, `taiji_ai/README.md`,
  `taiji_ai/THIRD_PARTY_NOTICES.md`, `taiji_ai/tools/env_check.py`, `Docs/hardware_inventory.md` (regenerate)
- `Docs/WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md`: maintainer's input plan — **not edited**; DEC-0008 records that it
  supersedes the v3 Streamlit choice.
- Historic entries (CHANGELOG, X.03.md) stay as they are (append-only history).

**Environment:** Node v24.12.0, npm 11.6.2, pnpm 11.10.0 available.

**Effort impact:** P8 grows from 9.5 to ≈ 14 engineering days; total ≈ 50 → ≈ 54 (49.75 − 9.5 + 13.75).

## 2. Plan

**Target architecture:**
- `taiji_ai/src/taiji_ai/api/` — FastAPI app factory, routers (`health`, later `recordings`, `segments`, `runs`,
  `findings`, `reports`, `media`), served by uvicorn on `127.0.0.1`.
- `taiji_ai/web/` — Vite + React + TypeScript SPA; dev server proxies `/api` to FastAPI; production build
  `web/dist/` served by FastAPI as static files (one process for the user).
- Worker subprocess unchanged (heavy work never in the API process).
- Video: proxy MP4 served with HTTP Range by FastAPI; PTS map served as JSON; frame marking with
  `requestVideoFrameCallback` in the browser.
- Charts: one lightweight time-series library chosen in P8.08 (candidate uPlot, MIT); Plotly stays for the
  static HTML report only.
- Tests: FastAPI `TestClient` contract tests (`T-API-*`), Vitest unit tests (`T-WEB-*`), Playwright E2E (`T-E2E-*`);
  manual scenarios `T-UI-*` kept.

**New P8 task list (replaces the Streamlit list):**

| ID | Task | Est |
|---|---|---:|
| P8.01 | FastAPI skeleton: app factory, settings, `/api/health`, error format, static serving of `web/dist`, `python -m taiji_ai.api` | 0.5 |
| P8.02 | Web scaffold: Vite + React + TS, router, TanStack Query, typed API client, dev proxy, layout, health page; ESLint + `tsc` + Vitest | 0.75 |
| P8.03 | API: participants/recordings list + ingest (calls `io.ingest`) | 1 |
| P8.04 | Media API: proxy MP4 with HTTP Range, PTS map JSON | 0.5 |
| P8.05 | Video player component: frame-accurate marking (`requestVideoFrameCallback`), ±1 frame, proxy↔source PTS | 1.5 |
| P8.05b | Fallback: import segments from Kinovea/ELAN CSV | 0.5 |
| P8.06 | Segment form + API with revisions | 1 |
| P8.07 | Runs API (create, progress via polling/SSE, cancel) wired to the worker; progress UI | 1 |
| P8.08 | Metrics page: time-series chart synced to the video cursor, NaN gaps, coverage | 1.5 |
| P8.09 | Skeleton overlay render (A) | 0.5 |
| P8.10 | Finding templates (B+H) | 0.5 |
| P8.11 | Review page: confirm/reject/edit/insufficient + audit log | 1 |
| P8.12 | Export JSON/CSV/HTML + evidence clips, immutable snapshot | 1 |
| P8.13 | Compare view: two synced videos + deviation curves | 1 |
| P8.14 | Backup/restore, delete participant | 0.5 |
| P8.15 | Playwright E2E for the G04 workflow | 1 |
| | **Total** | **≈ 14** |

**Files / steps:**
1. `Docs/tracking/DECISIONS.md`: DEC-0008 (supersedes the Streamlit part of TECH_WORKFLOW §1.1 and v3).
2. `Docs/TECH_WORKFLOW_V1.md`: stack table, §1.2 (why not Streamlit / Next.js), W3 table + text, §5.1 tree,
   §5.2 process model, §6.1 env table, §10.3 license table; add a dated change note at the top.
3. `Docs/IMPLEMENTATION_PLAN_V1.md`: replace P8 table; update §3 totals, §14.2 test tiers, §15.8–15.10 test
   tables (add `T-API-*`, `T-WEB-*`, `T-E2E-*`, remap `T-UI-*`), §16.1 G04 row, §17 timeline B column, §18 risk row;
   add a dated change note.
4. `AGENTS.md` §5.7 (worker vs API process), §7 commands (uvicorn, pnpm).
5. `Docs/tracking/TASK_STATUS.md`: regenerate the P8 section from the new table (keep everything else).
6. Verify: grep for remaining "Streamlit" outside history/v3/code-to-change; task count and totals consistent;
   `§` references in AGENTS still valid.
7. Tracking: CHANGELOG, TASK_STATUS (X.04).

**Acceptance criteria:**
- [x] DEC-0008 recorded; TECH_WORKFLOW and IMPLEMENTATION_PLAN describe React + Vite + FastAPI consistently.
- [x] No "Streamlit" left in TECH_WORKFLOW / IMPLEMENTATION_PLAN / AGENTS except in change notes explaining the switch.
- [x] P8 has 16 tasks (P8.01–P8.15 + P8.05b) with estimates summing to ≈ 14; totals updated.
- [x] Test plan has API/Web/E2E test IDs mapped to P8 tasks.
- [x] TASK_STATUS P8 section matches the plan; other sections unchanged.

**Impact / rollback:** documentation only; revert files to roll back.

## 3. Plan re-read (before coding)

- 2026-11-14: re-read — steps and estimates consistent (P8 sum 13.75 ≈ 14). **Added step 0:** root
  `.markdownlint.jsonc` disabling MD060 (table pipe spacing style only), because every doc edit produces hundreds
  of MD060 warnings that hide real ones. No other rule is disabled.

## 4. Implementation log

| Step | Done | Notes |
|---|---|---|
| 0 | ✓ | `.markdownlint.jsonc` (MD060 off) |
| 1 | ✓ | DEC-0008 |
| 2 | ✓ | TECH_WORKFLOW v1.1: header + change note, §1.1 (API, UI, UI data, UI charts, UI tests, Node rows), §1.2 (Streamlit, Next.js rows), W3 table/text, §5.1 tree (api/, web/; fixed `report/` branch char), §5.2, §6.1 (`web` env), §10.3, §11 E02 |
| 3 | ✓ | IMPLEMENTATION_PLAN: new P8 table (16 tasks, 13.75 d); old→new P8 IDs remapped by regex outside the table (simultaneous mapping); §3 totals; §14.2 tiers; §15.10b T-API/T-WEB/T-E2E; §16.1 G04; §17 timeline rewritten by hand (auto-remap produced ranges like "P8.03–02"); one-engineer path; §18 risks; change note; "97" → "100 task" |
| 4 | ✓ | AGENTS.md §5.7, §7 (API/web commands marked "after P8.01/P8.02") |
| 5 | ✓ | TASK_STATUS P8 section regenerated (13 → 16 rows), summary 97 → 100 |
| 6 | ✓ | See §5. Arithmetic error caught: total first written as ≈ 54.5, correct is ≈ 54 (49.75 − 9.5 + 13.75) |
| 7 | ✓ | CHANGELOG, TASK_STATUS (X.04), BUGS (BUG-0002) |

**Process deviation:** BUG-0002's fix was written to disk before the bug entry, because the script that did both
aborted (console encoding) after writing the fix. The entry was added immediately afterwards.

## 5. Verification

```
"Streamlit" in AGENTS / TECH_WORKFLOW / PLAN -> only change notes (TECH_WORKFLOW:10, :71; PLAN:298, :302)
AGENTS.md top-level headings                 -> 10 (unchanged structure)
P8 table                                     -> 16 tasks, sum 13.75; all IDs P8.01–P8.15 + P8.05b referenced
remapped refs                                 -> T-UI-01..10, T-STORE-04..07, T-REP-01..05, P9.04 dep → correct new IDs
table column counts                          -> TECH_WORKFLOW §1.1 rows all 5 cols; new test-tier rows 5 cols
TASK_STATUS                                  -> 100 plan rows (P8 = 16) + X.01–X.04
DEC-0008                                     -> referenced in DECISIONS, TECH_WORKFLOW (4), PLAN (3)
"3.11" in TECH_WORKFLOW                      -> only the §12 decision-history row (BUG-0002 check)
```

## 6. Self-review

- Re-read: TECH_WORKFLOW stack table (rows 40–62) and tree; P8 table; timeline; test tables; AGENTS §5.7/§7.
- Findings fixed in this task: tree branch character for `report/`; Plotly row contradicted the new "UI: biểu đồ" row
  (renamed "Biểu đồ report"); timeline ranges broken by the automatic remap; total ≈ 54.5 → ≈ 54.
- Pre-existing defect found: stale Python row → BUG-0002 (S3), fixed and closed.
- Not changed on purpose: `Docs/WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md` (maintainer input; superseded via DEC-0008) and
  historic CHANGELOG / X.03 entries (append-only). Code still contains Streamlit (`pyproject.toml`, `app/Home.py`,
  README, NOTICES, env_check) — removed in P8.01/P8.02 as planned.

## 7. Bugs

| Bug ID | Severity | Status | Note |
|---|---|---|---|
| BUG-0002 | S3 | CLOSED | Stale "Python 3.11 hoặc 3.12" row in TECH_WORKFLOW §1.1 |
| BUG-0003 | S3 | CLOSED | Introduced by step 0: workspace markdownlint config re-enabled MD013; fixed by disabling MD013 explicitly. Found after the task was first marked DONE |

## 8. Close-out

- [x] Acceptance criteria met (§5)
- [x] Checks pass (documentation checks in §5; no code changed)
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] DECISIONS.md updated (DEC-0008)
