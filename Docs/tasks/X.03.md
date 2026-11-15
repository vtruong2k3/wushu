# X.03 — Rules for third-party code, models and datasets

| Field | Value |
|---|---|
| Status | DONE |
| Owner | agent (Claude Code) |
| Phase | ad-hoc |
| Estimate | 0.5 day |
| Depends on | X.01, X.02 (DONE) |
| Plan confirmed by | Maintainer, 2026-11-13 (approved the proposal in the conversation) |
| Started / Done | 2026-11-13 / 2026-11-14 |

## 1. Analysis

**Goal:** make the use of third-party repositories, model weights and datasets rule-based and traceable, so that
licenses, provenance and data-usage limits are respected and untrustworthy third-party claims are not reused blindly.

**In scope:** a new AGENTS.md section, a third-party notices inventory for the code base, an "allowed use" column in
the dataset registry, a pytest `dataset` marker, CLAUDE.md pointer, tracking updates.
**Out of scope:** legal review (maintainer), changing any dependency, downloading anything.

**Current state (read 2026-11-13):**
- AGENTS.md has only §5.9 (privacy), §5.10 (no copying from unlicensed repos), §5.11 (never run third-party code).
- References to AGENTS.md sections exist for §1–§8 (grep across `AGENTS.md`, `CLAUDE.md`, `Docs/`); **§9 is not
  referenced** → insert the new section as §9 and move "When in doubt" to §10; no reference breaks.
- Inventories already exist: `repos/taolu/REPOS.md`, `repos/sanda/REPOS.md` (commits, licenses, findings),
  `Docs/DATASET_REGISTRY_TAIJI.md` (no "allowed use" column), `datasets/taiji/README.md` (md5, license),
  `taiji_ai/models/registry.json` (SHA-256, `license_note`).
- Installed dependency licenses (from package metadata in `.venv`): rtmlib Apache-2.0, onnxruntime-gpu MIT,
  av BSD-3, numpy BSD-3 (+0BSD/MIT/Zlib/CC0), scipy BSD, pandas BSD-3, pyarrow Apache-2.0, pydantic MIT,
  opencv-python-headless Apache-2.0, tqdm MPL-2.0 AND MIT, streamlit Apache-2.0, plotly MIT, jinja2 BSD,
  protobuf BSD-3, flatbuffers Apache-2.0, **nvidia-* CUDA/cuDNN wheels: NVIDIA proprietary** (redistribution terms).
- FFmpeg is an external CLI (Gyan "essentials" Windows build; GPL build) — called as a separate process, not linked.
- Project-specific cases the rules must cover: UMONS CC BY-NC-SA (derived artifacts), TaiForm peer-review sample,
  OpenWushu content CC BY-SA (share-alike), Ultralytics/pingouin (AGPL/GPL), RTMPose/SMPL/MotionBERT research-only
  weights, unlicensed repos (Pang/Zhang, Motion Embedding), inflated/self-reported metrics in third-party repos.

**Constraints:** AGENTS.md §5.9–§5.11, §8 (no commit). Rules in English (maintainer request). Registry file is in
Vietnamese → new column text in Vietnamese for consistency within the file (§4.3).

**Risks:** legal statements could be read as legal advice → phrase as project policy, require maintainer/legal review
before commercial release.

## 2. Plan

**Files:**

| File | Change |
|---|---|
| `AGENTS.md` | new §9 "Third-party code, models and datasets" (9.1 license tiers, 9.2 repositories, 9.3 models/weights, 9.4 datasets, 9.5 own recordings, 9.6 records); old §9 → §10; §1 table rows for new inventories; §5.10/§5.11 point to §9 |
| `taiji_ai/THIRD_PARTY_NOTICES.md` | new: runtime deps, external tools, model weights, copied code (none yet), reference-only sources |
| `Docs/DATASET_REGISTRY_TAIJI.md` | summary table: new column "Mục đích được phép" |
| `taiji_ai/pyproject.toml` | add pytest marker `dataset` |
| `CLAUDE.md` | one line: apply AGENTS.md §9 before using any third-party repo/model/dataset |
| `Docs/tracking/*` | TASK_STATUS (X.03), CHANGELOG, DECISIONS (DEC-0007) |

**Steps:**
1. Write AGENTS.md §9 and renumber "When in doubt" to §10; update §1 table and §5.10/§5.11.
2. Write `taiji_ai/THIRD_PARTY_NOTICES.md` from the metadata above.
3. Add "Mục đích được phép" column to the dataset registry summary.
4. Add `dataset` marker to `pyproject.toml`; run pytest + ruff to confirm nothing breaks.
5. Add the CLAUDE.md pointer.
6. Verify: grep that every `AGENTS.md §N` reference still points to the intended heading; markers registered
   (`pytest --markers`); dry-run git add includes the new files and nothing forbidden.
7. Update tracking files.

**Acceptance criteria:**
- [x] AGENTS.md §9 covers: license tiers with allowed actions, repo workflow (read REPOS.md first, clone rules,
      static reading, citing idea sources, no trust in self-reported metrics), weights, dataset workflow (register
      before download, checksum, safe extraction, allowed purposes, no label mixing across routines, grouped splits,
      out-of-domain reported separately, `data_sources` + license on derived artifacts, `dataset` test marker,
      no dataset content in fixtures), own recordings (consent scope), where to record.
- [x] No existing `§` reference broken.
- [x] THIRD_PARTY_NOTICES lists every runtime dependency in `pyproject.toml` + NVIDIA wheels + FFmpeg + models.
- [x] Registry has an allowed-use value for every dataset row.
- [x] `pytest` passes and `dataset` marker is registered; ruff clean.
- [x] Tracking files updated.

**Impact / rollback:** documentation + one pytest marker; revert the files to roll back.

## 3. Plan re-read (before coding)

- 2026-11-13: re-read against current files — OK. Clarification: THIRD_PARTY_NOTICES lists direct runtime deps,
  dev-only tools, NVIDIA wheels, FFmpeg and models; transitive deps are referenced via `uv.lock` with an
  "audit before distribution" note (not listed one by one).

## 4. Implementation log

| Step | Done | Notes |
|---|---|---|
| 1 | ✓ | AGENTS.md: new §9 (9.1–9.6), "When in doubt" → §10, §1 table +2 rows, §5.10/§5.11 point to §9 |
| 2 | ✓ | `taiji_ai/THIRD_PARTY_NOTICES.md`. Self-correction during writing: PyAV's bundled FFmpeg build license was first written as "LGPL" without evidence → changed to "not yet verified" |
| 3 | ✓ | Registry: column "Mục đích được phép" for all rows + new row D08 (own recordings); header rewritten (BUG-0001) |
| 4 | ✓ | `dataset` pytest marker |
| 5 | ✓ | CLAUDE.md pointer to §9 |
| 6 | ✓ | See §5 |
| 7 | ✓ | TASK_STATUS, CHANGELOG, DECISIONS (DEC-0007), BUGS (BUG-0001) |

## 5. Verification

```
AGENTS.md headings      -> §1..§8 unchanged; §9 (9.1–9.6) new; §10 When in doubt
§ references            -> every existing reference (§1–§8, §2.2, §2 Step 4/5, §3, §4.2, §4.3, §5, §5.6, §5.9)
                           resolves to the intended heading; new refs §9, §9.1, §9.2, §9.4 resolve
pytest --markers        -> gpu and dataset markers registered
pytest (taiji_ai)       -> 12 passed
ruff check / format     -> all checks passed / 26 files already formatted
uv lock --check         -> resolved 68 packages (lock unchanged)
git add --dry-run .     -> 54 files (+X.03.md, +THIRD_PARTY_NOTICES.md); forbidden-pattern grep exit 1 (no match)
personal-data grep      -> one match: Docs/tasks/X.02.md:94, the sentence describing the scan itself
                           ("username, email, C:/Users, AppData") — false positive, no personal data
licenses stated from memory, re-checked on PyPI -> pose2sim BSD-3-Clause, pingouin GPL-3.0, ultralytics AGPL-3.0
BUG-0001                -> registry line 3 now lists D12/D09 as downloaded; table rows agree (2 matches)
```

## 6. Self-review

- Files reviewed by re-reading: AGENTS.md §9 in full (lines 264–352), §1 and §5 edits; THIRD_PARTY_NOTICES.md;
  registry header and table; pyproject marker; CLAUDE.md line; tracking entries.
- Checklist: correctness ✓ · edge cases (unknown/conflicting licenses → most restrictive; own recordings; derived
  artifacts; tests needing datasets) ✓ · no unverified claims left (PyAV FFmpeg build marked "not yet verified";
  Pose2Sim/pingouin/Ultralytics verified) ✓ · errors surfaced ✓ · no personal data ✓ · docs updated ✓
- Findings: (1) stale registry header → BUG-0001, fixed; (2) the unverified "LGPL" statement about PyAV's bundled
  FFmpeg was caught while writing and corrected before review (not a committed defect).
- Open follow-up (not a bug): verify the license of the FFmpeg libraries bundled in the PyAV wheel before any
  distribution — tracked as a note in THIRD_PARTY_NOTICES §1.

## 7. Bugs

| Bug ID | Severity | Status | Note |
|---|---|---|---|
| BUG-0001 | S3 | CLOSED | Stale dataset-registry header; fixed and verified in this task |

## 8. Close-out

- [x] Acceptance criteria met (§5)
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] DECISIONS.md updated (DEC-0007)
