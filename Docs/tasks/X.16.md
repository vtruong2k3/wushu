# X.16 — Verify four candidate datasets from the maintainer's list; download the usable ones

| Field             | Value                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15)                                                                       |
| Owner             | agent (Claude Code)                                                                     |
| Phase             | Ad-hoc (dataset check, registry, download)                                              |
| Estimate          | 0.25 day                                                                                |
| Depends on        | X.14, X.15 DONE (checked 2026-11-15)                                                    |
| Plan confirmed by | Maintainer, 2026-11-15: asked to check these datasets and download and use the ones that can be used |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                |

## 1. Analysis

**Source of the list:** a text pasted by the maintainer, a description of four datasets from another source; its links
were lost. Its statements are treated as unverified (AGENTS.md §9.2.4) and were checked on the primary pages.

**Verified in this task (read 2026-11-15):**

| Dataset | What the primary source says |
| ------- | ---------------------------- |
| UMONS-TAICHI (D12) | Zenodo API, record 2784581: licence id `cc-by-4.0` (the licence file inside the data says CC BY-NC-SA 4.0, already applied in the registry). 7 files with size and md5, among them `Segmented_C3D.zip`, 2,668,864,662 bytes, md5 `6b2746280984014fb18a59f38d0a95d2`. 2200 samples, 13 classes, 12 performers, Qualisys 68 markers at 179 Hz, Kinect V2 25 joints at 30 Hz. Three experts rank the **performers** (0–10), not each recording. No RGB video. The statements of the pasted text match; we already hold `Kinect`, `Segmented_Kinect`, `Labels`. The only new file of its list is `Segmented_C3D` |
| Motion Embedding 24-form (D13) | GitHub page: no `LICENSE` file, no licence statement, the README says nothing about permission; the data is a Google Drive link (guest access not verified). The registry already says `not-usable` |
| Figshare "Raw data of typical balance movements of Tai Chi" | The record was found through the data availability statement of the paper on PubMed Central (PMC10404393): DOI 10.6084/m9.figshare.22574185. Figshare API: public, version 1, licence CC BY 4.0, one file `Raw data (Tai Chi).rar`, 211,846,155 bytes, md5 `d6f770b7f0904d937f64672a1f6ceee4`, description "Lower limb joints and muscles". The paper: 16 men (8 professional athletes, 8 amateurs), two movements (knee lift balance, leg stirrup balance); joint angles, joint moments, muscle forces from an AnyBody model, surface EMG of four muscles; motion capture 250 Hz, force plates and EMG 1000 Hz. The file's content is not known yet |
| PhysioNet "Tai Chi, Physiological Complexity, and Healthy Aging: Gait and EMG data" | Page of v1.0.1 (v1.0.2 is newer): licence Open Data Commons Attribution License v1.0, ZIP 1.5 GB (2.3 GB unpacked), open access. 87 adults aged 50–79 (60 Tai Chi-naïve, 27 experts) **walking** (10 minutes single task, 90 s dual task); footswitch timing and EMG at 1500 Hz. No video and no Tai Chi form data on the page |

**Decisions on the facts:**

| Dataset | Decision | Reason |
| ------- | -------- | ------ |
| UMONS `Segmented_C3D` | download | known licence (non-commercial, share-alike, allowed use `dev-test`, `benchmark` as in D12), published md5, 2.67 GB with 130 GB free; the best open motion capture of Tai Chi techniques we found, for the geometry study that came up in the P10.07 discussion |
| Figshare balance movements | download | CC BY 4.0, published md5, 202 MiB; usefulness is limited (lower limb, two movements, not the three metrics) and is judged after looking at the file list |
| Motion Embedding | do not download | no licence: AGENTS.md §9.1 "no licence: read to learn methods, do not copy data"; the only route is the authors' permission, which the maintainer decides |
| PhysioNet gait | do not download | licence is fine, but it is walking of older adults, not Tai Chi movement, and no task would use 1.5 GB; registered as `reference-only` so it is not surveyed again |

**In scope:** two registry rows (D18 Figshare, D19 PhysioNet), notes on D12 and D13; two downloads; the provenance entry
in `datasets/taiji/README.md` (tracked notes, no data); the file list of each archive.

**Out of scope:** running any code of these projects (the UMONS processing code, the Motion Embedding code and models),
logging in to Google Drive, parsing the C3D or the Figshare data in depth (no task consumes it yet), the D13 permission.

**Constraints that apply:** AGENTS.md §9.4 (register before download; checksum; check archive member paths before
extracting; extract into `extracted/`; never execute anything from a dataset; no dataset in git), §9.1, §5.6 (TLS verification
stays on).

## 2. Plan

**Steps:**

1. Registry rows and notes (before the download).
2. Download `Segmented_C3D.zip` (Zenodo) and the Figshare RAR with `curl` (TLS on) into `datasets/taiji/<name>/raw/`.
3. Compare md5 with the published value; record the sha256 as well.
4. List the members of each archive without extracting (ZIP with Python `zipfile`, RAR with the Windows `bsdtar`): reject
   absolute paths, `..`, links; note the count, the total size and the file types.
5. Extract into `extracted/` only if step 4 is clean and the unpacked size fits the disk.
6. Provenance in `datasets/taiji/README.md`; inventory of the file types; registry status "downloaded".

**Test plan** (manual checks):

| Check | What it verifies |
| ----- | ---------------- |
| C-1 | md5 of each file equals the published md5 |
| C-2 | Member lists clean (no absolute path, no `..`, no link); unpacked size recorded |
| C-3 | `git status` shows nothing from `datasets/` except the README; `repo_hygiene.py` passes |
| C-4 | Registry: rows D18, D19, D12, D13 consistent with the facts above; allowed use stated |
| C-5 | No code from the datasets executed; no Drive access; diagnostics empty; gate 10/10 PASS |

**Acceptance criteria:**

- [x] AC1 Each of the four datasets has a recorded verdict with its source (§1, registry).
- [x] AC2 The two usable datasets are downloaded, checksum-verified, listed and extracted safely (C-1, C-2).
- [x] AC3 Registry and README updated; nothing of the data in git; gate 10/10 PASS (C-3..C-5).

**Impact / rollback:** about 3 GB under `datasets/` (ignored by git). Rollback: delete the two folders and the registry rows.

## 3. Plan re-read (before the first edit)

- Plan re-read: 2026-11-15 — OK. The disk has 130 GB free; the registry IDs in use are D01–D17 (D18, D19 are free);
  the tools: Python `zipfile` for ZIP, the Windows `bsdtar` 3.8.9 for RAR (no 7-Zip; WinRAR is installed but bsdtar is
  used so that a listing never runs archive-supplied code). `datasets/` is ignored by git except the README files.

## 4. Implementation log

| Step | Done | Notes / deviations from plan |
| ---- | ---- | ---------------------------- |
| 1 | 2026-11-15 | Registry rows D18, D19 and the notes on D12 and D13 written before any download (§9.4). |
| 2a | 2026-11-15 | Figshare file downloaded (`curl`, TLS on); size and md5 equal the published values. |
| 3a | 2026-11-15 | Figshare RAR listed with the Windows `bsdtar` before extraction: 16 xlsx and 3 directories, no absolute path, no `..`, no link, 233,851,850 bytes unpacked; extracted into `extracted/`. Sheet names and ranges read from the XML (no macros): see the registry D18 and the data README. **The content is lower-limb biomechanics model output, so it does not serve the MVP metrics.** |
| 2b | 2026-11-15 | UMONS `Segmented_C3D.zip` downloaded in the background into a `.part` file, renamed only when complete (2,668,864,662 bytes, as published). |
| 3b | 2026-11-15 | One script (scratchpad, outside the repository): md5 against the published value, then every member inspected before extracting (no absolute path, no `..`, no backslash, no link, no duplicate name, no encrypted member, ratio and size limits); extracted only because all passed. 2,151 members (2,150 files), 3.53 GiB. The zip carries its own top folder, which doubled the level after extraction; the folder was moved up one level for consistency with `Kinect` and `Labels` (2,149 `.c3d` and `License.txt` rechecked after the move; a first attempt to delete the empty outer folder failed because my shell stood inside it, nothing was lost). |
| 4 | 2026-11-15 | BUG-0039 (3 old markdownlint warnings in the data README) registered and fixed in the same edit. |
| 5 | 2026-11-15 | README of the data, registry D12 (roll-out table) and D18 updated; gate; self-review. No deviation from the plan. |

## 5. Verification

Full gate: **RESULT: PASS (10/10) in 19.4s**, exit 0.

| Check | Result |
| ----- | ------ |
| C-1 | Figshare RAR: 211,846,155 bytes, md5 `d6f770b7f0904d937f64672a1f6ceee4` = published. UMONS `Segmented_C3D.zip`: 2,668,864,662 bytes, md5 `6b2746280984014fb18a59f38d0a95d2` = published |
| C-2 | Both member lists clean (RAR: 16 files and 3 directories, 233,851,850 bytes; ZIP: 2,150 files and 1 directory, 3.53 GiB, worst compression ratio 1.6); extraction only after the check |
| C-3 | `git status` under `datasets/`: only `README.md`; `git check-ignore` confirms the raw and extracted data are ignored (rule `/datasets/*/*`); `repo_hygiene.py` passes in the gate; `datasets/` is 7.59 GB, 123 GB free on D: |
| C-4 | Registry: D18, D19 added, D12 (C3D downloaded, roll-out table) and D13 (rechecked, not downloaded) updated; allowed use stated for each |
| C-5 | No code of the datasets executed (the UMONS processing code and the Motion Embedding code were not touched); no Google Drive access; `getDiagnostics` empty; gate above |

What the files turned out to be (for the record, not a promise of use): UMONS C3D, 2,149 segments of 12 people and 13
classes named like the Kinect part, licence file CC BY-NC-SA 4.0, content not opened; Figshare, 16 workbooks of
lower-limb model output, no marker coordinates, no video.

## 6. Self-review

- Files reviewed: the registry (D12, D13, D18, D19 and the survey notes), `datasets/taiji/README.md`, this file.
- Checklist (AGENTS.md §2 Step 4): correctness ☑ (md5 and sizes equal the published values; members checked before
  extraction) · no fabricated data ☑ (the content of the C3D files is stated as not opened; the Figshare content comes from
  reading the sheet names; the pasted text's claims were checked, not copied) · errors surfaced ☑ (the failed first delete,
  the doubled folder level, the lint warnings) · no personal data ☑ · docs updated ☑.
- Findings: the pasted description was mostly accurate on UMONS, silent on the Figshare content, and wrong in effect on
  Motion Embedding ("worth trying first", while it has no licence) and on PhysioNet (walking, not Tai Chi). The 2,149 C3D
  segments differ from the 1,815 Kinect segments and the 2,200 samples of the description; the reason is not known and
  nothing depends on it yet.
- Not done on purpose: no download of Motion Embedding or PhysioNet; no opening of the C3D or xlsx content; no code run.
- Decision for later: use of the C3D data (for example a geometry study after P5) needs its own task.

## 7. Bugs

None found so far.

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed
