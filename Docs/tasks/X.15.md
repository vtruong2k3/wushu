# X.15 — Stop waiting for access-controlled datasets; record the sizes of the open ones

| Field             | Value                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                       |
| Owner             | agent (Claude Code)                                                                     |
| Phase             | Ad-hoc (decision and registry only)                                                     |
| Estimate          | 0.1 day                                                                                 |
| Depends on        | X.14 DONE (checked 2026-11-15)                                                          |
| Plan confirmed by | Maintainer, 2026-11-15: said that a request (form and e-mail to the authors) got no reply, so that dataset is dropped and the free ready-made ones are used |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                |

## 1. Analysis

**Goal:** record the decision, and put the facts measured today into the registry, so that the next dataset step has
real numbers.

**Decision:** an access request sent by the maintainer (a form and an e-mail to the authors) has had no reply, so the
project stops depending on it. The datasets in use are the ones held and the openly downloadable ones. The maintainer
did not say which dataset the request was for; the registry note therefore does not name one (question Q1).

**Measured today (read-only, no dataset file downloaded):**

| Fact | How |
| ---- | --- |
| Kinetics-400 validation split: 20 parts, 28.3 GB in all | the path list of the CVDF repository (a 20-line text file) and an HTTP HEAD request on each part for `Content-Length` |
| The validation split has 50 clips per class, so 50 tai chi clips of about 10 s each (about 8 minutes) | the Kinetics paper (arXiv 1705.06950, Section 2, Table 2) |
| The 20 parts are shards: the clips of one class are spread over them; no per-class download is documented | CVDF README (read), inference for the spread |
| Disk: drive D has 130 GB free; `datasets/` holds 1.2 GB | `df`, folder size |
| The CMU mirror metadata lists take `12_04` as "tai chi" (FBX); the neighbours 12_01..12_03 are "walk" | `metadata.csv` of the mirror (2549 rows) |
| The file `12_04.fbx` was not found at the guessed URL (404): its path and size are **not** known | one HEAD request |

**In scope:** DEC-0019; registry notes (D15, D16, D17, survey section, roll-out table); tracking.

**Out of scope:** downloading any dataset file (AGENTS.md §9.4: with the maintainer's approval and the size known);
the CMU file format decision (a later task decides between FBX and BVH when something consumes it); reading the MADS and
CMU terms (the maintainer's browser step; MADS leaves the plans).

**Constraints that apply:** AGENTS.md §9.4 (register before download; allowed use stays as registered), §9.1; the
maintainer's words are not quoted in the logs.

**Questions for the maintainer:**

| #  | Question | Default if no answer |
| -- | -------- | -------------------- |
| Q1 | Which dataset was the request for, and when was it sent? | Not named; the note stays generic |
| Q2 | Download the Kinetics validation split (28.3 GB) to keep 50 tai chi clips? | Not now: no task consumes it before P3, and the trial recording P1.09 will give better data |

## 2. Plan

**Steps:** (1) re-read the registry regions (§3); (2) DEC-0019; (3) registry edits; (4) diagnostics and gate; (5) close.

**Checks:** C-1 DEC-0019 present, next free ID DEC-0020; C-2 registry: D15 out of the plans, D16 size and method,
D17 take and what is unknown, roll-out row updated; C-3 `git status`: nothing under `datasets/` or `repos/`; C-4
diagnostics empty, gate 10/10 PASS.

**Acceptance criteria:**

- [x] AC1 DEC-0019 records the decision without quoting the maintainer (C-1).
- [x] AC2 The registry states the measured sizes with their method and marks the unknowns (C-2).
- [x] AC3 Nothing downloaded; diagnostics empty; gate 10/10 PASS; no commit (C-3, C-4).

**Impact / rollback:** documentation only.

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK; the registry regions (rows D15–D17, the D15 and D16 detail sections, the survey section,
  the roll-out table) and `DECISIONS.md` (next free ID DEC-0019) are as expected.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1 | 2026-11-15 | Measurements (see §1): the path list of the Kinetics validation split and one HEAD request per part; the CMU mirror metadata; one HEAD request on a guessed CMU file URL (404, so its size stays unknown). No dataset file downloaded. |
| 2 | 2026-11-15 | DEC-0019; registry: D15 out of the plans, D16 size and method, D17 take and unknowns, survey note on the unanswered request, roll-out table. |
| 3 | 2026-11-15 | Diagnostics, gate, self-review. No deviation from the plan. |

## 5. Verification

Full gate: **RESULT: PASS (10/10) in 19.9s**, exit 0.

| Check | Result |
| ----- | ------ |
| C-1 | DEC-0019 present (no quotation of the maintainer); next free ID DEC-0020 |
| C-2 | Registry: D15 "bỏ khỏi kế hoạch"; D16 states 20 parts, 28.3 GB, 50 val clips per class and how it was measured; D17 states the metadata row and that path, size and format are unknown; roll-out row updated; the unanswered request is noted without naming a dataset |
| C-3 | `git status`: no change under `datasets/` or `repos/`; the `datasets/` folder is still 1188 MB (nothing added) |
| C-4 | `getDiagnostics`: global list empty, registry none; gate above |

## 6. Self-review

- Files reviewed: registry (rows, details, survey, roll-out), `DECISIONS.md` DEC-0019, this file.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ (every number carries its method; the CMU size is marked unknown, not
  guessed) · no fabricated data ☑ · errors surfaced ☑ (the 404 is reported) · no personal data ☑ · docs updated ☑.
- Findings: none. The 28.3 GB figure is the sum of 20 `Content-Length` values; it is the compressed download, the
  extracted size is not known.
- Open for the maintainer: Q1 (which dataset the request was for) and Q2 (download the validation split: not
  recommended now, see the report).

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed
