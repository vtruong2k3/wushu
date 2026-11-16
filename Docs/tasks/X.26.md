# X.26 — Register the four web Tai Chi videos (D20) and smoke-test ingest and proxy on two of them

| Field             | Value                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-16)                                                                                  |
| Owner             | agent (A)                                                                                      |
| Phase             | P2 (technical check; not the acceptance task P2.07)                                            |
| Estimate          | 0.1 day                                                                                        |
| Depends on        | P2.02, P2.03, P2.08 (DONE)                                                                     |
| Plan confirmed by | Maintainer, 2026-11-16: asked for the registry entry (`dev-test`, technical only) and for the throwaway-folder test |
| Started / Done    | 2026-11-16 / 2026-11-16                                                                                 |

**Registered after the first step:** the maintainer's message had no task ID; the registry entry D20 was written before this file (CLAUDE.md asks for the ID first; it was
not done first, which is noted here).

## 1. Analysis

**Goal:** (1) register the four videos in `Docs/DATASET_REGISTRY_TAIJI.md` with the allowed use `dev-test` (technical checks only), SHA-256 and the licence rule of AGENTS.md §9.1 (done: D20);
(2) run `taiji ingest --proxy` on two of them (video 2: H.264, video 1: AV1) in a **throwaway data folder** with a **test participant**, and record what it shows: the original is unchanged
(SHA-256 before and after), the VFR verdict, the proxy check (frame count and timestamps), the time and the size.

**Facts (2026-11-16, metadata only, no frame viewed):** 1920x1080, no rotation tag, start 0, AAC; video 1 AV1 24 fps 1029.6 s; video 2 H.264 24 fps 977.3 s; video 3 H.264 24 fps 1328.9 s; video 4 AV1 30 fps 2576.6 s;
`vfr_verdict` says not VFR for all four; the PTS scan takes 0.3 s (0.8 s for 77 297 frames); the AV1 decoder (libdav1d) is available in PyAV.

**In scope:** the registry entry; the smoke test; the numbers in this file.
**Out of scope:** sync (no claps, no flash, not two cameras of one take: P2.07 needs the phone files of P1.09 or the rehearsal), pose (P3), any accuracy statement, moving the files into `datasets/`
(the maintainer decides; the deviation is written in D20).

**Constraints:** AGENTS.md §9.1 (unknown licence = most restrictive), §9.4 (allowed use, register), §9.5 and §5.9 (the test participant exists only in the throwaway folder and is deleted with it; no personal data),
§11 (a file of a dataset is data, never executed).

## 2. Plan

1. Hash the four files (done, in D20). 2. Throwaway folder under the scratchpad (`TAIJI_DATA_DIR`), `taiji participant add` with a test pseudonym `P99` and a test consent code. 3. `taiji ingest --proxy` on video 2 then video 1; time each;
read `recording.json`; hash the originals again. 4. Record the numbers; delete the throwaway folder (look at the target first). 5. Records; gate (no code changed: docs only, the gate is run to keep the claim honest).

**Acceptance criteria:**

- [x] AC1 D20 is in the registry with `dev-test` technical only, the licence rule and SHA-256.
- [x] AC2 SHA-256 of the originals is the same before and after; the VFR verdict and the proxy check are recorded for both files, or the failure is reported with its cause.
- [x] AC3 The throwaway folder is deleted; nothing of the videos or of the test participant is in the repository or the real data folder.

**Impact / rollback:** none on code; the registry row can be removed.

## 3. Plan re-read (before the run)

Plan re-read: 2026-11-16 — OK: `taiji ingest` and `taiji participant add` take the options used below (`--help` read), `TAIJI_DATA_DIR` selects the data folder, the consent code must match `CONSENT-YYYY-NNN`.

## 4. Implementation log

| Step | Done | Notes |
| ---- | ---- | ----- |
| 1 | 2026-11-16 | SHA-256 of the four files; D20 written in the registry (summary row and detail with the hashes, the licence rule and the deviation: the files are in `video/`, not `datasets/`). |
| 2 | 2026-11-16 | Throwaway folder under the scratchpad, `TAIJI_DATA_DIR` set; `taiji participant add --id P99` with a test consent code (`CONSENT-2026-999`, exists only there). |
| 3 | 2026-11-16 | `taiji ingest --proxy` on video 2 (H.264) and video 1 (AV1). |
| 4 | 2026-11-16 | Numbers below; the throwaway folder (886 MB) was looked at, then deleted; the real data folder was checked afterwards (no participant, no recording, files not modified). |

## 5. Verification

| | Video 2 (H.264, 1080p, 24 fps, 977 s) | Video 1 (AV1, 1080p, 24 fps, 1030 s) |
| --- | --- | --- |
| `taiji ingest --proxy` | exit 0, 92.4 s | exit 0, 132.9 s |
| frames in `recording.json` | 23 452 | 24 708 |
| VFR (rule of the project) | no | no |
| proxy | 720p, check passed, max deviation 0.000 frames | 720p, check passed, max deviation 0.000 frames |
| original SHA-256 before = after | yes | yes |

- Throwaway folder size after the two ingests: 928.5 MB (source copies and proxies). Deleted afterwards.
- AV1 is decoded by the system ffmpeg and by PyAV (libdav1d) without a special case.
- Not measured: peak memory; anything about phone files; sync (no claps, no flash, one camera per take).
- Gate `tools/check.ps1`: 10/10 PASS (129.6 s, 958 tests) (no code changed in this task; run to keep the claim honest).

## 6. Self-review

- The task changed documents only: `Docs/DATASET_REGISTRY_TAIJI.md` (D20), this file, tracking. Nothing of the videos or the test participant is in the repository (`*.mp4` is ignored) or in the real data folder.
- The registry says what the videos may be used for: `dev-test`, technical only; no `train`, no `benchmark`, no pose before the licence is clarified. The original URLs were not recorded by the maintainer: asked to add them if they are known.
- Known limits: two of the four files were ingested (videos 3 and 4 only probed); these are re-encoded web videos, not phone files; this does not replace P2.07.

## 7. Bugs

None found.

## 8. Close-out

- [x] Acceptance criteria met (evidence above)
- [x] Checks pass
- [x] No open S1/S2 bug caused by this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed (no decision: the allowed use is in the registry)
