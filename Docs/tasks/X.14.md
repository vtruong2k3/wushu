# X.14 — Survey of openly downloadable Taijiquan datasets (no access request)

| Field             | Value                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                       |
| Owner             | agent (Claude Code)                                                                     |
| Phase             | Ad-hoc (research and registry only)                                                     |
| Estimate          | 0.25 day                                                                                |
| Depends on        | none                                                                                    |
| Plan confirmed by | Maintainer, 2026-11-15: no access requests for now; use the datasets we hold and look for ones that need no request |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                |

## 1. Analysis

**Goal:** a short list of datasets that can be downloaded without a request form, agreement, e-mail or account, that
contain Taijiquan (ideally the 24-form) as video, 2D or 3D skeleton, or motion capture, with their licence and what our
licence tiers allow. It replaces the access requests of P1.10, which the maintainer decided not to send.

**Already in the registry (not re-surveyed, status only):** D12 UMONS-TAICHI (held, CC BY-NC-SA), D09 TaiForm sample
(held, reference only), D13 Motion Embedding 24-form (no licence), D06, D10, D11, D14 (need a request). The corrected
master plan also names D01–D05 and D07 (for example D02 KungfuAthlete, which is said to have Taiji samples): their
status is checked.

**What the project needs from such data:** (1) real Taiji video to test pose, masks and metrics before our own
recordings (P3–P5); (2) motion capture to check the 2D metrics (P10.07, optional); (3) labels of the 24-form movements
for segmentation or comparison (P6, extension E01).

**In scope:** web search and reading of the official pages (dataset page, Zenodo or repository record, paper); per
candidate: content, access, licence with its source, allowed use under AGENTS.md §9.1, relevance, red flags; registry
rows for the candidates worth keeping, status "not downloaded".

**Also in scope (added 2026-11-15, plan change before the first edit of the registry):** fix BUG-0036 (old markdownlint
warnings in the registry detail sections: an empty line after each detail heading, the two bare e-mail addresses in
angle brackets), since this task edits the same file.

**Out of scope:** downloading any file, running any code from a repository, submitting a form, logging in (AGENTS.md
§9.2, §9.4). Downloads are a separate step after the maintainer chooses (§9.4: register before download).

**Constraints that apply:** AGENTS.md §9.1 (licence tiers; unknown licence is treated as the most restrictive), §9.2.4
(numbers from the providers are self-reported), §9.4 (registry rows with allowed use; never mix label spaces across
routines or styles), privacy (web queries are generic; they name no person and no project).

**Risks:** video datasets built from YouTube or Bilibili links carry the video owners' rights, whatever the licence of
the annotations; a "free" dataset may still require a click-through licence; information on the web may be outdated.
Mitigation: the licence is read on the official page, conflicts are written down, unclear cases are `not-usable`.

## 2. Plan

**Steps:**

1. A research agent searches and reads the official pages (no download), returns a table with sources.
2. The agent's claims are spot-checked on the official pages (licence and access of every candidate kept).
3. Registry: new rows from D15 for the kept candidates; notes for D01–D07 where their status matters; the decision on
   D06, D10, D11 (no request for now) recorded.
4. Self-review, checks, close.

**Test plan** (documentation task, manual checks):

| Check | What it verifies |
| ----- | ---------------- |
| C-1 | Every kept candidate has an official source for its licence and access, read in this task |
| C-2 | Allowed use follows AGENTS.md §9.1; unclear licence gives `not-usable` |
| C-3 | No file downloaded; nothing under `datasets/` changed |
| C-4 | Registry IDs are new (D15 onward) and not reused |
| C-5 | IDE diagnostics empty; gate 10/10 PASS |

**Acceptance criteria:**

- [x] AC1 A list of open candidates with content, access, licence (and source), allowed use, relevance (C-1, C-2).
- [x] AC2 Candidates worth keeping are in the registry with "not downloaded" (C-4).
- [x] AC3 Nothing downloaded (C-3); tracking updated; gate passes (C-5).

**Impact / rollback:** registry and task file only.

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK; the registry IDs in use were checked (D01–D14 across the registry and the corrected
  master plan), so new rows start at D15.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1 | 2026-11-15 | A research subagent searched and read official pages (about 75 tool calls; no download, no login). Its report is model output and was treated as unverified. |
| 2 | 2026-11-15 | I re-read the official or primary pages for the candidates kept: KungfuAthlete (project page, Hugging Face card, GitHub README), Kinetics (CVDF repository, DeepMind page), CMU terms (Hugging Face mirror). MADS and the CMU site could not be read (TLS errors at their servers; no bypass). Kinetics licence: one web search found only secondary sources. |
| 3 | 2026-11-15 | Registry: rows D02, D15, D16, D17; detail sections; a survey section with the candidates not kept; roll-out table. **Deviation:** KungfuAthlete already had the ID D02 in the corrected master plan, so it is registered as D02 and not as D15; new IDs start at D15 as planned. BUG-0036 fixed in the same edit session (see §7). |
| 4 | 2026-11-15 | Diagnostics, gate, self-review. |

## 5. Verification

Full gate (`tools\check.ps1`): **RESULT: PASS (10/10) in 18.6s**, exit 0.

| Check | Result |
| ----- | ------ |
| C-1 | Read in this task: KungfuAthlete (licence conflict confirmed: Hugging Face card `apache-2.0`; project page "research and academic" only), Kinetics CVDF (no licence stated), DeepMind page (no terms), CMU terms (quoted from the mirror card, tag `cmu-mocap`). **Not verified:** MADS access and licence (page unreachable), the CMU primary page, the Kinetics CC BY 4.0 claim (secondary sources only), the Tai Chi take number of CMU, class size of Kinetics, the content of the KungfuAthlete paper. Every such item is marked "chưa xác minh" in the registry |
| C-2 | Allowed use follows AGENTS.md §9.1: KungfuAthlete `reference-only` (stricter licence applied), MADS `not-usable` until the maintainer reads the terms, Kinetics and CMU `dev-test` only after the maintainer approves the download or reads the primary terms |
| C-3 | No download: `git status` shows no change under `datasets/` or `repos/`; no file fetched except web pages |
| C-4 | New IDs D15–D17; D02 reused from the master plan, not a new number; no ID duplicated |
| C-5 | `getDiagnostics` for the registry: none; gate 10/10 PASS |

## 6. Self-review

- Files reviewed: `Docs/DATASET_REGISTRY_TAIJI.md` (rows, details, survey section, roll-out table, header),
  `Docs/tasks/X.14.md`.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ · no fabricated data ☑ (items I did not read are labelled as the
  agent's report or as unverified; the Kinetics licence is not stated as fact) · errors surfaced ☑ · no personal data ☑
  (generic dataset queries; no project or person named) · docs updated ☑.
- Findings: the research report contains an unverified claim that a dataset is "the best open-looking candidate": the
  registry says only what was read. The agent said KungfuAthlete's paper contradicts the project page about videos; I
  did not read the paper and wrote it as unverified.
- Decisions for the maintainer: (1) open the MADS page and the CMU site in a browser and read the terms; (2) approve or
  not the download of the Kinetics tai chi class (size and subset extraction unchecked); (3) whether MADS or CMU may
  replace PSU-TMM100 in P10.07 (DEC-0018 made that task conditional).
- Not done on purpose: nothing was downloaded, and no TLS error was bypassed (AGENTS.md §5.6, §9.4).

## 7. Bugs

| Bug ID | Severity | Status | Note |
| ------ | -------- | ------ | ---- |
| BUG-0036 | S3 | CLOSED | markdownlint warnings in the registry; fixed here with one-off script (7 empty lines after detail headings, 2 e-mail addresses in angle brackets); diagnostics for the file empty |

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed
