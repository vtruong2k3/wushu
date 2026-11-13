# <TASK-ID> — <Task title>

| Field | Value |
|---|---|
| Status | TODO / ANALYZING / PLAN_READY / IN_PROGRESS / IN_REVIEW / DONE / BLOCKED |
| Owner | A / B / O / H / agent name |
| Phase | P? |
| Estimate | ? days |
| Depends on | <task IDs> (state checked on <date>) |
| Plan confirmed by | <name, date> (required if ≥ 1 day or schema/contract change) |
| Started / Done | <YYYY-MM-DD> / <YYYY-MM-DD> |

## 1. Analysis

**Goal:**

**In scope:**

**Out of scope:**

**Inputs / outputs / interfaces** (shapes, units, coordinate conventions, file formats):

**Existing code and docs read** (paths):

**Constraints that apply** (AGENTS.md §5):

**Unknowns, risks, questions** (and answers when received):

## 2. Plan

**Design:**

**Files to create / modify:**

| File | Change |
|---|---|
| | |

**Implementation steps:**

1.
2.
3.

**Test plan:**

| Test ID | Type | What it checks | New / existing |
|---|---|---|---|
| | | | |

**Acceptance criteria:**

- [ ]
- [ ]

**Impact / rollback:**

## 3. Plan re-read (before coding)

- <YYYY-MM-DD>: re-read against current code — OK / changes: …

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
|---|---|---|
| 1 | | |

## 5. Verification

```
<paste command + summarized output: ruff, pytest, gpu tests, benchmarks>
```

## 6. Self-review

- Files reviewed: …
- Checklist (AGENTS.md §2 Step 4): correctness ☐ · edge cases ☐ · no fabricated data ☐ · errors surfaced ☐ ·
  tests cover criteria ☐ · no personal data ☐ · docs updated ☐
- Findings:

## 7. Bugs

| Bug ID | Severity | Status | Note |
|---|---|---|---|
| | | | |

## 8. Close-out

- [ ] Acceptance criteria met (evidence above)
- [ ] Checks pass
- [ ] No open S1/S2 bug from this task
- [ ] TASK_STATUS.md updated
- [ ] CHANGELOG.md entry added
- [ ] README status / DECISIONS.md updated if needed
