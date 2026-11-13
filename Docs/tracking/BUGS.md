# Bug Register

Rules: `AGENTS.md` §3. IDs are sequential (`BUG-NNNN`), never reused. Every bug must have a fix plan.
Severity: **S1** critical · **S2** major · **S3** minor.
Lifecycle: `OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED` (or `WONT_FIX` with maintainer approval).

**Next free ID:** `BUG-0006`

## Summary

| ID | Title | Sev | Status | Found in | Fix task | Regression test | Opened | Closed |
|---|---|---|---|---|---|---|---|---|
| BUG-0005 | `apiGet` drops `Headers`-object headers and reports aborted requests as `network_error` | S3 | CLOSED | P8.02 self-review of `taiji_ai/web/src/api/client.ts` | P8.02 | `tests/client.test.ts` (headers + abort cases) | 2026-11-14 | 2026-11-14 |
| BUG-0004 | `Settings.device` reads `TAIJI_DEVICE` at import time, not at construction | S3 | CLOSED | P8.01 analysis of `taiji_ai/src/taiji_ai/config.py:21` | P8.01 | New unit test: env set after import is honoured | 2026-11-14 | 2026-11-14 |
| BUG-0003 | New `.markdownlint.jsonc` re-enabled MD013 (line length) warnings | S3 | CLOSED | X.04 (introduced by step 0) | X.04 | IDE diagnostics after a doc edit show no MD013 | 2026-11-14 | 2026-11-14 |
| BUG-0002 | TECH_WORKFLOW stack table still says "Python 3.11 hoặc 3.12" after DEC-0002 | S3 | CLOSED | X.04 self-review of `Docs/TECH_WORKFLOW_V1.md` §1.1 | X.04 | Manual check: row matches DEC-0002 | 2026-11-14 | 2026-11-14 |
| BUG-0001 | Dataset registry header says no dataset downloaded (stale) | S3 | CLOSED | X.03 review of `Docs/DATASET_REGISTRY_TAIJI.md:3` | X.03 | Manual check: header matches "Trạng thái" column | 2026-11-13 | 2026-11-14 |

---

## Details

### BUG-0005 — `apiGet` drops `Headers`-object headers and reports aborted requests as `network_error`

| Field | Value |
|---|---|
| Severity | S3 (no caller affected yet; would mislead error handling and drop headers later) |
| Status | CLOSED |
| Found in | Task P8.02 self-review, `taiji_ai/web/src/api/client.ts` |
| Found by / date | agent (Claude Code), 2026-11-14 |
| Affects | Web API client (all future API calls) |

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

| Field | Value |
|---|---|
| Severity | S3 (configuration surprise; no wrong data produced so far) |
| Status | CLOSED |
| Found in | Task P8.01 analysis, `taiji_ai/src/taiji_ai/config.py:21` |
| Found by / date | agent (Claude Code), 2026-11-14 |
| Affects | `Settings.device` (pose device selection) |

**Description:** `device: str = os.environ.get("TAIJI_DEVICE", "cuda")` is evaluated once when the module is
imported, while `data_dir`/`models_dir` use `default_factory` and read the environment when `Settings()` is built.
Setting `TAIJI_DEVICE` after import (tests, worker bootstrap) is silently ignored.

**Steps to reproduce:** import `taiji_ai.config`; set `os.environ["TAIJI_DEVICE"]="cpu"`; `Settings().device` → `"cuda"`.

**Expected:** `"cpu"`.  **Actual:** `"cuda"`.

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

| Field | Value |
|---|---|
| Severity | S3 (tooling noise; introduced by task X.04 step 0) |
| Status | CLOSED |
| Found in | Task X.04, after closing: IDE diagnostics on `Docs/tasks/X.04.md` |
| Found by / date | agent (Claude Code), 2026-11-14 |
| Affects | Editor diagnostics only |

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

| Field | Value |
|---|---|
| Severity | S3 (stale documentation, AGENTS.md §4.3) |
| Status | CLOSED |
| Found in | Task X.04 self-review, `Docs/TECH_WORKFLOW_V1.md` §1.1 row "Ngôn ngữ" |
| Found by / date | agent (Claude Code), 2026-11-14 |
| Affects | Documentation only; readers could think the Python version is still open |

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

| Field | Value |
|---|---|
| Severity | S3 (stale documentation, AGENTS.md §4.3) |
| Status | CLOSED |
| Found in | Task X.03, `Docs/DATASET_REGISTRY_TAIJI.md` line 3 |
| Found by / date | agent (Claude Code), 2026-11-13 |
| Affects | Documentation only; a reader could think UMONS/TaiForm were never downloaded |

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
