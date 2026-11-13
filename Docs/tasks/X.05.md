# X.05 — Survey of additional Wushu / martial-arts repositories (maintainer list 2026-11-14)

| Field | Value |
|---|---|
| Status | DONE |
| Owner | agent (Claude Code) |
| Phase | ad-hoc |
| Estimate | 0.5 day |
| Depends on | X.03 (third-party policy) — DONE |
| Plan confirmed by | Maintainer request 2026-11-14 ("đọc đống repo này xem có repo nào dùng được không") |
| Started / Done | 2026-11-14 / 2026-11-14 |

## 1. Analysis

**Goal:** decide, per repository/resource in the maintainer's list, whether anything is reusable for the Taolu
platform (Taijiquan first), under AGENTS.md §9 (license tiers, static reading only, no trust in self-reported metrics).

**Already known (repos/taolu/REPOS.md):** `dntod/wushu-judge` — only LICENSE + README (no code);
`cloudsbird/OpenWushu` — cloned and audited (routine data, CC BY-SA content).

**Inputs:** 17 GitHub repositories (pose/scoring/competition management/reference) + 3 external links (Kaggle
notebook, Hugging Face LoRA, IWUF page).

## 2. Plan

1. Batch metadata via GitHub API (license, size, stars, last push, archived, language, file count) and README text
   into the scratchpad — no cloning yet.
2. Triage: discard empty/irrelevant/unlicensed-and-weak repos; shortlist candidates.
3. Deep static read of shortlisted repos (code structure, data, models, claims vs code, license of code/data/weights).
4. External links: read the pages (no downloads).
5. Clone only repositories worth keeping as references (`--depth 1`, hooks off, `_no-license/` if unlicensed);
   record commit/license/verdict in `repos/taolu/REPOS.md`.
6. Tracking: TASK_STATUS, CHANGELOG; bugs if any.

**Acceptance criteria:**
- [x] Every item in the list has a verdict (use / reference-only / not usable) with the reason and license.
- [x] Kept repos recorded in REPOS.md with commit and license; nothing executed.
- [x] Tracking updated.

## 3. Plan re-read (before coding)

- 2026-11-14: re-read — OK (survey, no product code).

## 4. Implementation log

| Step | Done | Notes |
|---|---|---|
| 1 | ✓ | Metadata, README, tree for 17 repos via GitHub API (scratchpad `x05/`); `PercyShenJackson/wushu` → 404 |
| 2 | ✓ | Triage: competition-management apps (no license or GPL) and karate/kempo repos discarded; shortlist tpz, wushu_vision, SSSGCN, Alan42x |
| 3 | ✓ | Deep read: tpz deduction JSON (77 codes), KataForge LICENSE (Elastic-v2-based), wushu_vision `stance_rules.py` (hard-coded thresholds), SSSGCN README (dataset access) |
| 4 | ✓ | HF LoRA model card and IWUF page read; Kaggle page not readable (JS/login); IEEE page blocked (418) → web search for paper metadata |
| 5 | ✓ | Cloned tpz (MPL-2.0) and wushu_vision (`_no-license/`); both git-ignored. `IWUF-TJ-DEDUCTION-TABLES.pdf` text extraction with pypdf in a throwaway uv env → no text layer (scanned) |
| 6 | ✓ | `repos/taolu/REPOS.md` (survey section), `Docs/DATASET_REGISTRY_TAIJI.md` (D14), tracking |

## 5. Verification

- Every list item has a verdict with reason and license in `repos/taolu/REPOS.md` ("Khảo sát bổ sung").
- Nothing executed from any repository; binaries in cheng-cheng-x were not downloaded.
- New clones are ignored by git (`git status` shows only docs changes).

## 6. Self-review

- Claims checked against sources: licenses from GitHub API / LICENSE files; tpz codes from the JSON itself;
  thresholds quoted from `stance_rules.py`; HF/IWUF statements from the pages. Unverified items are marked as such
  (Kaggle content, S3GCN dataset size/form, TJ deduction table content).
- The dataset authors' e-mail from the SSSGCN README was not copied into the registry (pointer to the README instead).

## 7. Bugs

| Bug ID | Severity | Status | Note |
|---|---|---|---|
| — | | | none |

## 8. Close-out

- [x] Acceptance criteria met
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
