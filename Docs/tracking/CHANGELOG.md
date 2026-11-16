# Changelog — code and documentation history

Newest first. One entry per completed task or bug fix (format: `AGENTS.md` §4.2).

---

## 2026-11-16 — P3.02 run_pose: raw pose of everyone in a segment, by real PTS (DONE)

- Changed: `taiji_ai/src/taiji_ai/pose/runner.py` (new), `taiji_ai/tests/helpers/fake_pose.py` (new), `tests/unit/test_pose_box.py` (new), `tests/contract/test_pose_runner.py` (new),
  `tests/golden/test_pose_d20.py` (new), `taiji_ai/README.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (T-POSE-05, 06 rows), `Docs/tasks/P3.02.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`
- Behaviour: `run_pose(recording_dir, start_s, end_s, model)` reads the frames of `[start - 1 s, end + 1 s]` of the original video by the rows of `pts.parquet` (display rotation applied), runs the detector on the first frame and every N frames
  (default 5) and takes the boxes of the frames between from the previous keypoints (+12 %), runs the detector at once when nobody is followed, and returns the raw persons as compressed rows (`PoseRaw`: `frame_index` = row of the table, `t_sec`,
  boxes, keypoints and scores as the model returned them, `from_detector`). Persons with few valid keypoints are kept (the maintainer's decision) and not followed. A file that does not match its table, a bad segment, a size change or a model
  failure is a `PoseRunError`, never a partial result
- Tests: T-POSE-05a..e, 05g, 06a..h (47, CPU, scripted model), T-POSE-05f and T-POSE-07 (GPU, 2 passed); mutation of `runner.py` 22 of 23 (1 equivalent); real clip of D20: 4.7 s of work for 12 s of 1080p video at N = 5
  (11.0 s at N = 1), N = 5 against N = 1: median 1.6 px, 95th percentile 5.7 px; gate 10/10 PASS (156.4 s, 1023 tests)
- Decisions: none new (Q6 of the plan: persons with few keypoints are kept; recorded in the task file)
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P3.02.md

## 2026-11-16 — P3.01 Joint order of the pose model verified on real frames (DONE)

- Changed: `taiji_ai/src/taiji_ai/pose/order_check.py` (new), `taiji_ai/src/taiji_ai/pose/skeleton.py` (header comment only), `taiji_ai/tests/unit/test_pose_order_check.py` (new),
  `taiji_ai/tools/pose_order_check.py` (new), `Docs/reports/p3_01_joint_order.md` (new), `Docs/DATASET_REGISTRY_TAIJI.md` (D20 allowed use), `Docs/tasks/P3.01.md`,
  `Docs/IMPLEMENTATION_PLAN_V1.md`, `taiji_ai/README.md`, `Docs/tracking/{TASK_STATUS,DECISIONS,CHANGELOG}.md`
- Behaviour: `halpe26/1` is confirmed: on five real frames (one web video, D20, used under DEC-0036) every structure check passes and, in the frontal frames with the face seen, the `L...` joints are on the
  person's left (image right). A first draft of the check failed a correct profile frame because the turned head put the hidden ear on the other side: eyes and ears no longer vote on the side rule
- Tests: T-POSE-04a (16 unit tests; mutation 10 of 10), T-POSE-04 (manual, report); gate 10/10 PASS (133.8 s, 974 tests)
- Decisions: DEC-0036 (D20 used without licence restriction for internal development, maintainer's decision)
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P3.01.md

## 2026-11-16 — X.26 Web Tai Chi videos registered (D20) and an ingest + proxy smoke test (DONE)

- Changed: `Docs/DATASET_REGISTRY_TAIJI.md` (D20: summary row and detail with SHA-256), `Docs/tasks/{X.26,P2.07}.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`. No code.
- Behaviour: none. The four videos of `video/` (third-party web content, licence unknown) may be used for `dev-test`, technical only. Smoke test in a throwaway folder with a test participant:
  H.264 file 92.4 s and AV1 file 132.9 s, proxy check passed (max deviation 0.000 frames), originals unchanged (SHA-256), no VFR; the folder was deleted. Not the acceptance of P2.07 (no phone files, no claps, one camera)
- Tests: none added; gate 10/10 PASS (129.6 s, 958 tests)
- Decisions: none (the allowed use is the registry's)
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/X.26.md

## 2026-11-16 — P2.05 rework after the review: no dead arguments, recording pair checked, tests that bite (BUG-0067, BUG-0068) (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/flash.py` (no `settings` / `rotation_deg`; `FlashError` for other recordings than the audio result's and for a missing `median_dt_s`;
  a missing `t_ref_s` gives `method = none`), `pipeline/sync_take.py` (call), `tests/contract/test_flash_review.py` (new), `tests/unit/test_flash_detector.py` (new),
  `tests/helpers/flash_media.py` (`fps_b`), `test_flash.py` and `test_flash_pairs.py` (call), `Docs/tasks/P2.05.md` (§4-§8 corrected, §10), `Docs/IMPLEMENTATION_PLAN_V1.md`,
  `taiji_ai/README.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: the validation of recordings that are not those of the audio result is refused (it ran silently); no invented 30 fps or reference time 0.0; the tests now
  catch a mapping that ignores drift or `t_ref_s`, a swapped folder order, the faster camera's frame, a search margin of 0, a noise-blind threshold and a missing refractory time
- Tests: T-SYNC-04g..n (17 tests); mutation of `flash.py`: 15 of 17 caught, 2 equivalent (before: 4 of 14 caught by the tests of P2.05); gate 10/10 PASS (159.8 s, 958 tests)
- Decisions: DEC-0032 item (3) marked as replaced by DEC-0034
- Bugs: BUG-0067 and BUG-0068 (S3) closed; BUG-0066 (S2, weak and split flashes) stays planned until the P2.07 numbers
- Commit: not committed
- Plan: Docs/tasks/P2.05.md §10

## 2026-11-16 — X.25 The `sync` database row only for usable takes (BUG-0065) (DONE)

- Changed: `taiji_ai/src/taiji_ai/pipeline/sync_take.py` (row only when `usable_for_metrics`, else delete), docstrings in `store/sync.py` and
  `schemas/sync.py`, `tests/contract/test_sync_take_wrong_lag.py` (T-SYNC-05f), `Docs/IMPLEMENTATION_PLAN_V1.md`, `Docs/tasks/{X.25,P2.01}.md`,
  `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: a take that the usability rule refuses (`residual_too_large`, `flash_not_found`, `start_only`, ...) has no `sync` row and an old row is removed
  on a re-run; before, the row existed for every `ok` take with `validated_by = 'flash'` and a wrong offset. `sync.json` is unchanged
- Tests: T-SYNC-05f (4); `test_sync_take.py` and `test_sync_rule.py` unchanged; 2 of 2 mutants caught; gate 10/10 PASS (121.4 s, 945 tests)
- Decisions: DEC-0035 (amends DEC-0025 item 7 and P2.01 Q4)
- Bugs: BUG-0065 (S2) closed
- Commit: not committed
- Plan: Docs/tasks/X.25.md

## 2026-11-16 — X.24 End-to-end test of `sync_take` with an audio lag wrong by 1 s; BUG-0065 found (DONE)

- Changed: `taiji_ai/tests/contract/test_sync_take_wrong_lag.py` (new), `Docs/IMPLEMENTATION_PLAN_V1.md` (T-SYNC-05e), `Docs/tasks/{X.24,P2.07}.md`,
  `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`
- Behaviour: none in `src/`. T-SYNC-05e shows through `sync_take` and `sync.json` that an audio lag wrong by ±1 s is not usable (`residual_too_large`, or
  `flash_not_found` when camera A hides a flash of each pair). The probe also showed that the `sync` database row is written for such a take with the wrong
  offset and `validated_by = 'flash'` (BUG-0065)
- Tests: T-SYNC-05e (4 cases); gate 10/10 PASS (145.3 s, 941 tests)
- Bugs: BUG-0065 (S2) registered, waits for the maintainer's choice (A: row only for usable takes; B: usable columns by migration 0002)
- Commit: not committed
- Plan: Docs/tasks/X.24.md

## 2026-11-16 — X.23 Flash check: one-to-one pair matching (BUG-0064, S1) (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/flash.py` (`match_flashes` replaces `match_residuals`; `FlashParams.min_flashes`),
  `tests/unit/test_flash_match.py` (new), `tests/contract/test_flash_pairs.py` (new), `tests/helpers/flash_media.py` (new),
  `Docs/TECH_WORKFLOW_V1.md` (W2 step 4), `Docs/capture_protocol.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (T-SYNC-04e, 04f),
  `taiji_ai/README.md`, `Docs/tasks/{X.23,P2.05}.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: a time mapping wrong by one pair gap (1 s) is never `usable_for_metrics`: before, it passed (residual 0.0 ms) when one camera showed
  one flash of a pair, because the check took the closest flash, ignored flashes without a partner and averaged the distances; now the flashes of a
  window are matched one to one in time order, both cameras must show the same number of flashes (at least two) or the window is not judged
  (`flash_not_found`), and the residual is the largest distance. A flash not seen now makes the take unusable for metrics even with the right offset
- Tests: T-SYNC-04e (15), T-SYNC-04f (10 cases; 7 failed on the old code); mutation: 8 of 8 caught; gate 10/10 PASS (179.9 s, 937 tests)
- Decisions: DEC-0034
- Bugs: BUG-0064 (S1) closed; BUG-0063 (S2) stays planned (audio-side limits)
- Commit: not committed
- Plan: Docs/tasks/X.23.md

## 2026-11-16 — P2.06 Sync usability rule, sync.json and SQLite sync row, CLI taiji sync (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/sync_rule.py` (new), `taiji_ai/src/taiji_ai/pipeline/sync_take.py` (new),
  `taiji_ai/src/taiji_ai/store/sync.py` (new), `taiji_ai/src/taiji_ai/store/recordings.py` (added `find_by_take`),
  `taiji_ai/src/taiji_ai/schemas/sync.py` (added `to_db_row`), `taiji_ai/src/taiji_ai/cli.py` (added `sync` subcommand),
  `taiji_ai/tests/unit/test_sync_rule.py` (new), `taiji_ai/tests/contract/test_sync_take.py` (new),
  `Docs/tasks/P2.06.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`, `taiji_ai/README.md`
- Behaviour: pure decision function `decide_usability` maps audio sync result and flash validation to
  `usable_for_metrics` (true iff audio `status == "ok"`, `validation.method == "flash"`, residuals at both ends present,
  and `residual_frames <= 1.0`; false with explicit documented reason `"no_audio"`, `"audio_not_found"`, `"start_only"`,
  `"flash_not_found"`, or `"residual_too_large"`); `sync_take(take_id, settings=...)` verifies recordings exist for take,
  runs audio synchronization and flash validation, atomically writes `data/takes/<take_id>/sync.json`, and manages SQLite
  `sync` table (`upsert_sync` when `status == "ok"`, `delete_sync` otherwise per DEC-0025 item 7); CLI `taiji sync <take_id>`
  exits 0 on usable take, 1 on unusable or missing take.
- Tests: T-SYNC-05 (1.0 vs 1.0001 frame threshold), T-SYNC-05b (each reason), T-SYNC-05c (`sync_take` writes `sync.json` and
  SQLite row on `ok`; `start_only` writes `sync.json` without SQLite row), T-SYNC-05d (missing camera refusal), and CLI tests;
  13 tests pass in `test_sync_rule.py` and `test_sync_take.py`; full test suite 912 passed;
  quality gate 10/10 PASS in 134.4 s
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P2.06.md

## 2026-11-16 — P2.05 Flash validation: brightness series, onset detection, residual in ms and frames (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/flash.py` (new), `taiji_ai/tests/contract/test_flash.py` (new),
  `Docs/tasks/P2.05.md`, `Docs/tracking/{TASK_STATUS,DECISIONS,CHANGELOG}.md`, `taiji_ai/README.md`
- Behaviour: extracts frame timestamps and mean luma on downscaled grayscale grid (`brightness_series`);
  detects rising steps using robust difference statistics ($\Delta L \ge \max(\text{min\_step}, \text{median}(\Delta L) + k_{\text{mad}} \times 1.4826 \times \text{MAD})$)
  with refractory separation to ignore sustained illumination and reject slow auto-exposure ramps; pairs Camera A and B
  onsets in start/end windows via audio sync mapping ($a\_to\_b(t_a)$); calculates residuals in ms and in frames of
  slower camera ($\max(dt_A, dt_B)$); returns strict `SyncValidation` (`method = "none"` with `None` residuals if flashes
  are missing or audio sync is not `ok`, per `AGENTS.md` §5.1)
- Tests: T-SYNC-04, T-SYNC-04b..d; 5 contract tests pass; full test suite 722 passed;
  quality gate 10/10 PASS in 44.4 s
- Decisions: DEC-0032
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P2.05.md

## 2026-11-16 — P2.04 rework after an independent review: end window, guard zones, honest numbers, dropped audio (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/audio.py` (no `settings`; refuses audio with dropped samples; `read_wav` scales before averaging
  channels), `io/audio_sync.py` (rewritten: end window on the stretch both cameras recorded, guard zones, 0.2 s radius, `t_match_s`,
  500 ppm cross-check, NaN guard, `SyncError`/`TakeMismatch`/`SyncInputError`), `schemas/sync.py` (docstring: `t_ref_s`),
  `tests/helpers/sync_media.py` (new), `tests/contract/test_audio_sync_long.py`, `test_audio_sync_status.py`, `test_audio_io.py`,
  `tests/unit/test_audio_matcher.py` (new), `test_audio_sync.py` (cleaned), `tests/contract/test_flash.py` (two call sites),
  `taiji_ai/README.md`, `Docs/TECH_WORKFLOW_V1.md` (W2), `Docs/IMPLEMENTATION_PLAN_V1.md` (test list), `Docs/tasks/P2.04.md` §9,
  `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: the end window no longer depends on which phone stopped first (the first version lost the end, or accepted a 1 s wrong lag as
  `ok`, when B stopped before A in takes of 60 s or more: BUG-0058, S1); `t_ref_s` and the drift are taken at the claps on A's video
  timeline (100 ppm was read as 118 ppm); a window is searched wider than it is accepted so that a single clap of a pair cannot win
  at an edge; the drift limit is 500 ppm and is the cross-check of the two windows; audio with dropped samples is refused; no sentinel
  numbers, no swallowed errors, no `settings`; the envelope is computed on windows only (141 MB for 10 min instead of 476 MB)
- Tests: T-SYNC-01c (real container), 06..10; 187 tests in five files (first version 10); 80 of the first 149 new tests were red on the
  old code; mutation: first rework 43 of 43 caught, new logic 12 of 14 mutants caught by the existing tests; the 2 survivors (B's end slice not widened at the start / at the end) got T-SYNC-06f (a clap at the edge of the window pushed by +/-400 ppm) and are caught: 14 of 14; an adversarial pass of seven lenses (about 1100 probe cases);
  full suite 899 passed; gate 10/10 PASS
- Decisions: DEC-0033
- Bugs: BUG-0058 (S1), BUG-0059..0062 closed; BUG-0063 (S2, limits of the audio match) planned for P2.06 and P2.07
- Commit: not committed
- Plan: Docs/tasks/P2.04.md §9

## 2026-11-16 — P2.04 Audio synchronization: mono 16 kHz, ZNCC envelope cross-correlation, offset and drift (first version; its close-out was wrong, see the entry above)

- Changed: `taiji_ai/src/taiji_ai/io/audio.py` (new), `taiji_ai/src/taiji_ai/io/audio_sync.py` (new),
  `taiji_ai/tests/contract/test_audio_sync.py` (new), `Docs/tasks/P2.04.md`,
  `Docs/tracking/{TASK_STATUS,DECISIONS,CHANGELOG}.md`, `taiji_ai/README.md`
- Behaviour: extracts mono 16 kHz WAV (`audio.wav`) cached in recording directory; computes 4th-order Butterworth
  bandpass envelope (f_hp = 300 Hz, f_lp = 50 Hz); performs Zero-Mean Normalized
  Cross-Correlation (ZNCC) with sub-sample parabolic interpolation (< 0.01 ms precision); applies crest
  factor gating (≥ 2.5) to reject continuous tones or noise lacking transient claps; partitions search windows
  adaptively for short clips (dur < 2 w_s); converts audio lag to video timeline via container `audio.start_offset_s`;
  calculates clock drift in ppm; unconfirmed claps or missing audio stream return `status = "not_found"` without
  fabricated values (`AGENTS.md` §5.1)
- Tests: T-SYNC-01, T-SYNC-01b..d, T-SYNC-02, T-SYNC-03; 10 contract tests pass; full test suite 717 passed;
  quality gate 10/10 PASS in 46.7 s
- Decisions: DEC-0031
- Bugs: ~~none~~ (BUG-0058..0063, see the entry above)
- Commit: not committed
- Plan: Docs/tasks/P2.04.md

## 2026-11-16 — P2.03 rework after an independent review: trimmed clips, honest proxy check, failures reported (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/frames.py` (`scan_pts_ticks` skips discard-flagged packets), `io/proxy.py` (rewritten: one
  command, no `settings`, no made-up numbers, no stale manifest), `io/ingest.py` (`IngestResult.proxy_error`), `cli.py`
  (exit 1, the ID always printed), `taiji_ai/tests/conftest.py` (fixtures `trim_base_video`, `trimmed_video`, `trimmed_mov`,
  `yuv444_video`), `tests/helpers/media.py` (new), `tests/contract/test_trimmed_clip.py` (new), `test_proxy.py`,
  `test_cli_ingest.py`, `taiji_ai/README.md`, `Docs/TECH_WORKFLOW_V1.md` (W1 steps 3 and 5),
  `Docs/IMPLEMENTATION_PLAN_V1.md` (test list), `Docs/tasks/P2.03.md` §9, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: a clip trimmed on a phone (stream copy that starts between two keyframes, an edit list) is stored with its
  decoded frames only: 99 rows in `pts.parquet`, not 105, so row *i* is decoded frame *i* and the proxy check passes
  (BUG-0052, S1: every timestamp was 0.2 s early in the probe); the proxy's timestamp check raises instead of writing
  `999.0` or `0.0` for what it cannot measure; `proxy.json` records the command that really ran; an old `proxy.json` is
  removed before a new proxy replaces its file; `taiji proxy` and `taiji ingest --proxy` exit 1 when the check failed or the
  proxy step failed, and still print the recording ID (the recording is stored); `make_proxy(recording_dir)` has no
  `settings` argument
- Tests: T-IO-20..22 (trimmed clip as `.mp4` and `.mov`, oracle = PyAV decode on 10 fixtures), T-IO-23..27; 15 of the new or
  changed tests were red on the old code; `test_proxy.py` 22, `test_cli_ingest.py` 21, `test_trimmed_clip.py` 16 (44 new in
  total); mutation run on a copy of `src`: 41 of 41 caught (first review run: 8 of 23); suite 717 passed (663 at the P2.02
  commit + 44 + 10 of P2.04 by another writer); gate 10/10 PASS
- Decisions: DEC-0030
- Bugs: BUG-0052 (S1), BUG-0053, BUG-0054, BUG-0055, BUG-0056 — fixed and closed in this task
- Commit: not committed
- Plan: Docs/tasks/P2.03.md §9

## 2026-11-16 — P2.03 Proxy H.264 720p: timestamp check, metadata stripping, `taiji proxy` (first version; its close-out was wrong, see the entry above)

- Changed: `taiji_ai/src/taiji_ai/io/proxy.py` (new), `taiji_ai/src/taiji_ai/io/ingest.py` (`proxy` option),
  `taiji_ai/src/taiji_ai/cli.py` (`taiji proxy`, `taiji ingest --proxy`), `taiji_ai/tests/conftest.py` (fixtures
  `hd_video_1080p`, `sd_video_480p`, `tagged_video`), `taiji_ai/tests/contract/test_proxy.py` (new),
  `taiji_ai/tests/contract/test_cli_ingest.py`, `taiji_ai/README.md`, `Docs/TECH_WORKFLOW_V1.md` (W1 step 5),
  `Docs/tasks/P2.03.md`, `Docs/tracking/{TASK_STATUS,DECISIONS,CHANGELOG}.md`
- Behaviour: creates `proxy.mp4` (H.264 720p, yuv420p, +faststart, no audio) and `proxy.json` (`proxy/1`) in
  `data/recordings/<recording_id>/`; scaling uses `scale=-2:'min(720,ih)'` to downscale 1080p without enlarging sources
  smaller than 720 lines (e.g. 480p); autorotates rotated sources upright (`rotation = 0`) and records `rotation_applied`;
  strips container metadata (`location`, `comment`, device info) with `-map_metadata -1`; ensures zero-based presentation
  time for web playback; timestamp verification verifies equal frame counts and deviation <= 1.0 frame across sample points;
  CLI provides `taiji proxy <recording_id>` and `taiji ingest --proxy`
- Tests: T-IO-10, T-IO-10b, T-IO-10c, T-IO-11, T-IO-11b, T-IO-19; 8 proxy contract tests and 3 new CLI tests pass red-first;
  ~~full test suite 673 passed; quality gate 10/10 PASS in 25.6 s~~ (wrong: 674 tests, 11 new; the gate of the reviewed tree
  gave 8/10)
- Decisions: DEC-0029
- Bugs: none
- Commit: not committed
- Plan: Docs/tasks/P2.03.md

## 2026-11-16 — P2.02 `ingest_recording`: read-only copy, SHA-256, `pts.parquet`, VFR rule, `taiji ingest` (DONE)

- Changed: `taiji_ai/src/taiji_ai/io/ingest.py` (new), `taiji_ai/src/taiji_ai/store/recordings.py` (new),
  `taiji_ai/src/taiji_ai/io/frames.py` (`PtsScan`, `scan_pts_ticks`, VFR rule, `is_vfr(t_sec, tick_s)`),
  `taiji_ai/src/taiji_ai/io/probe.py` (`NoVideoStreamError`, `AudioMeta`, container name), `store/artifacts.py`
  (`atomic_write_parquet`), `schemas/recording.py` (`CAMERA_ROLES`), `config.py` (size and duration limits), `cli.py`
  (`taiji ingest`), `taiji_ai/tests/conftest.py` (fixtures), new tests `tests/unit/test_vfr.py`,
  `tests/contract/test_ingest.py`, `tests/contract/test_cli_ingest.py`, changed `tests/contract/test_video_io.py`,
  `tests/unit/test_core.py`, `tests/unit/test_config.py`, `taiji_ai/README.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (T-IO-12..19),
  `Docs/tasks/{P2.02,P2.03}.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: one video becomes `data/recordings/<id>/` with `source.<ext>` (read-only copy, hash checked), `pts.parquet` (real
  integer timestamps) and `recording.json` (written last), then one database row; built in a staging folder and renamed
  atomically, a failed insert leaves only an `.orphan-` folder; refused before anything is written: unsupported extension,
  not a file, empty, over 20 GB or 30 minutes, no video stream, unreadable, no frames; the same file returns the existing
  record, under other IDs or for a taken take and camera it is refused; a recording needs a registered participant with
  analysis consent; VFR is decided on integer ticks (rule `tick_median` v1: 1 tick and 1 % of the median, more than 1 % of
  intervals), so a constant 30 fps clip with a 1 ms time base is no longer VFR; messages, logs and CLI output hold IDs only
- Tests: T-IO-06..09 and T-IO-12..19, written red first; mutation check 89 of 90 caught (the survivor is an older filter that
  is equivalent for every fixture); full suite `663 passed` (the summary line of pytest, 565 before); gate 10/10 PASS
- Decisions: DEC-0028
- Bugs: BUG-0046 (S3, `is_vfr` on a coarse time base) fixed and closed; BUG-0051 (S3, the first tests passed with 22 broken
  rules, one dead check) found and closed
- Commit: 2808bc6
- Plan: Docs/tasks/P2.02.md

## 2026-11-16 — P2.08 Participant registry and the `taiji participant` command (DONE)

- Changed: `taiji_ai/src/taiji_ai/store/participants.py` (new), `taiji_ai/src/taiji_ai/cli.py` (new),
  `taiji_ai/pyproject.toml` (`[project.scripts] taiji`), `taiji_ai/tests/unit/test_participants.py` and `test_cli.py` (new),
  `taiji_ai/README.md`, `Docs/consent_form.md` (B1 note), `Docs/tasks/{P2.08,P2.02}.md`,
  `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`
- Behaviour: a pseudonym is registered with the answers of a signed consent form; every answer (analysis, train, share) is
  required and explicit, analysis must be yes, the retention date is an ISO date not in the past (or none, with a warning),
  the actor is a role code, never a name; every write is one transaction with its audit row (consent fields only);
  `update_consent` changes train, share and retention only; messages and logs hold IDs only; `taiji participant add`, `set`
  and `show` with exit codes 0, 1 and 2
- Tests: T-DATA-05a..j, 93 tests written red first; mutation check 46 of 46 caught; full suite 565 passed (the summary
  line of pytest); gate 10/10 PASS in 16.5 s
- Decisions: DEC-0027
- Bugs: BUG-0050 (S3, `show` echoed an unchecked `--id`) found in the self-review and closed
- Commit: 2808bc6
- Plan: Docs/tasks/P2.08.md

## 2026-11-15 — P2.01 Manifest schemas: recording, proxy, sync (DONE)

- Changed: `taiji_ai/src/taiji_ai/schemas/{_base,recording,sync}.py` (new), `taiji_ai/tests/unit/test_schemas_recording.py`
  and `test_schemas_sync.py` (new), `Docs/TECH_WORKFLOW_V1.md` §4.1–4.2, `taiji_ai/README.md`,
  `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`, `Docs/tasks/{P2.01,P1.04,X.18}.md`
- Behaviour: strict manifests `recording/1`, `proxy/1`, `sync/1` and the ingest input (`IngestMeta`, `CaptureInfo`); atomic write
  and validated read (`ManifestError` names the field); the row of the `recording` table built from the manifest (relative
  `source_path`, no made-up duration); the time mapping between two cameras `t_b = t_a + offset_s + drift × (t_a − t_ref_s)`
  with an exact inverse, available only when both ends are matched; unknown values are null; `usable_for_metrics` needs the
  flash at both ends and a residual of at most 1 frame; no field for a name, an original file name or an absolute path
- Tests: T-SCH-01a..i, 136 tests written red first; mutation check 79 of 81 caught (the 2 left are equivalent); full suite
  472 passed; gate 10/10 PASS in 15.0 s
- Decisions: DEC-0026
- Bugs: BUG-0047 (S3, weak tests and a rule weaker than DEC-0025) and BUG-0048 (S3, wrong full-suite counts in the P1.04 and
  X.18 records) closed; BUG-0049 (S3, 15 older lint warnings in the workflow) planned for X.22; BUG-0046 (`is_vfr`) planned for P2.02
- Commit: 2d0cdf4
- Plan: Docs/tasks/P2.01.md

## 2026-11-15 — X.21 Detailed plan for Phase 2 (DONE)

- Changed: `Docs/tasks/P2.01.md` … `P2.08.md` (new), `Docs/tasks/X.21.md` (new), `Docs/IMPLEMENTATION_PLAN_V1.md` §3 and §6
  (P2 estimate 4 → 5,5 days; new row P2.08; P2.01, P2.02, P2.06, P2.07 rows updated), `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`.
  No code
- Findings: BUG-0046 (`is_vfr` flags a CFR video as VFR on a coarse time base); the proxy command would enlarge small sources;
  the sync time mapping of W2 was undefined; `sync.drift` NOT NULL would force a fabricated 0; no task wrote `participant` rows
  (new P2.08)
- Maintainer: confirmed the plans of P2.01, P2.02, P2.04 and accepted the defaults of every question (DEC-0025)
- Tests: none (documents); gate 10/10 PASS; IDE markdownlint clean
- Bugs: BUG-0046 (S3, PLANNED, fix in P2.02)
- Commit: 5c5ca32
- Plan: Docs/tasks/X.21.md

## 2026-11-15 — X.20 Working convention for the side label (Q9, first part) (DONE)

- Changed: `taiji_ai/tools/render_ontology_review.py` (three lines in question 4), `taiji_ai/tests/unit/test_ontology_review_sheet.py`
  (one new case), `taiji_ai/config/ontology_v0.yaml` (Q9 comment block only), `Docs/discovery/ontology_review_sheet.md`
  (regenerated), `Docs/tracking/{DECISIONS,TASK_STATUS,CHANGELOG}.md`, `Docs/tasks/{X.20,X.19}.md`
- Behaviour: none in the code. Documented rule (DEC-0024): the side label is the left/right word of the movement's standard
  name, the front foot for step-forward movements; shown to the coach in question 4. Found at the plan re-read that for A18 the
  name order does not settle the sequence (name left first, sequence right first); recorded
- Not a coach sign-off: the ontology stays `draft_unconfirmed`; no value changed (parsed ontology equal to the snapshot before)
- Tests: new case red first; stale guard seen red then green; 90 ontology and sheet tests pass; gate 10/10 PASS in 20.3 s
- Open: label of a segment that covers a whole alternating movement; order of A06 and A10; the coach sign-off
- Decisions: DEC-0024
- Bugs: none
- Commit: c0567ae
- Plan: Docs/tasks/X.20.md

## 2026-11-15 — X.19 Record the Q9 search findings next to Q9 (DONE)

- Changed: `taiji_ai/config/ontology_v0.yaml` (six comment lines under Q9, no key or value changed),
  `Docs/discovery/ontology_review_sheet.md` (regenerated: only its digest line differs), `Docs/tasks/{X.19,X.18}.md`,
  `Docs/tracking/{TASK_STATUS,CHANGELOG}.md`. No code
- Findings recorded (search-engine summaries; no textbook page could be read): the results disagree on the order of A06; one
  says the left version of A16 stands on the left leg; nothing on kicks; none says whether a name follows the hand or the foot.
  Working proposal (side label = the left/right word of the standard name, exceptions unspecified) is recorded as NOT a
  decision; Q9 stays open for a coach
- Tests: no new test; the stale guard (T-DATA-01l) failed after the YAML edit and passed after regeneration; parsed
  ontology equal to the snapshot before; gate 10/10 PASS
- Bugs: none
- Commit: c0567ae
- Plan: Docs/tasks/X.19.md

## 2026-11-15 — X.18 Ontology open questions without a coach: source check, side order, review sheet (DONE)

- Changed: `taiji_ai/src/taiji_ai/schemas/ontology.py` (optional `Action.side_sequence`, validator, pairing check in
  `check_segment`), `taiji_ai/config/ontology_v0.yaml` (sequences for A02, A04, A18; English names of A18 and A20; header),
  `taiji_ai/tools/render_ontology_review.py` (new), `taiji_ai/tests/unit/test_ontology.py`,
  `taiji_ai/tests/unit/test_ontology_review_sheet.py` (new), `Docs/discovery/ontology_review_sheet.md` (new, generated),
  `taiji_ai/THIRD_PARTY_NOTICES.md`, `taiji_ai/README.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`,
  `Docs/tasks/{X.18,P1.04}.md`
- Behaviour: when an action has a `side_sequence` and a segment gives an occurrence, `check_segment` requires the side of
  that repetition; an action without a sequence is not paired (unknown stays unknown); A06 and A10 have none. The coach review
  sheet (Vietnamese, 24 rows and six questions) is generated from the YAML and a test fails when it is stale
- Source check: three public pages (English and Chinese Wikipedia, one blog) agree with the 24 numbers and Chinese names;
  none gives repetition counts, side order or Vietnamese names; one low-authority article gives counts equal to ours
- Tests: T-DATA-01i..l (new); `test_ontology.py` 77 and the sheet tests 12; full suite ~~191~~ 335 passed (corrected, BUG-0048); 45 of 45 mutations
  caught; gate 10/10 PASS in 14.9 s
- Open: the coach sign-off (Q3, Q5, Q8 for A06 and A10, Q9, counts of A06 and A10, names); Q6 (P6.05) and Q7 (P9.04)
- Decisions: DEC-0023
- Bugs: BUG-0042 (S3, test gap found by mutation) and BUG-0043 (S3, pre-existing README MD040), both closed
- Commit: c0567ae
- Plan: Docs/tasks/X.18.md

## 2026-11-15 — P1.04 Ontology v0: 24-form actions, sides, occurrences, views, flags (DONE)

- Changed: `taiji_ai/src/taiji_ai/schemas/ontology.py` (new), `taiji_ai/config/ontology_v0.yaml` (new),
  `taiji_ai/tests/unit/test_ontology.py` (new), `taiji_ai/pyproject.toml` and `uv.lock` (`pyyaml>=6.0.3`, 6.0.3 locked),
  `taiji_ai/THIRD_PARTY_NOTICES.md`, `taiji_ai/README.md`, `Docs/tracking/{TASK_STATUS,BUGS,DECISIONS,CHANGELOG}.md`,
  `Docs/tasks/P1.04.md`
- Behaviour: an action is one numbered movement of the 24-form (`A01`..`A24`) with `sides`, `repetitions` and a shared
  `technique`; `Ontology.check_segment` is the guard of `segment.action`, `side`, `occurrence`, view and flags (the
  database checks only the view); the loader uses PyYAML safe loading and rejects a repeated key; the view list is tested
  against the migration CHECK list. The file is `draft_unconfirmed`: no coach has signed (DEC-0021), AC2 is met by
  "open corrections listed"
- Tests: T-DATA-01a..h, 59 tests, written red first; full suite ~~161~~ 305 passed (corrected, BUG-0048); 28 of 28 mutations of the validator caught;
  gate 10/10 PASS in 14.6 s
- Open for H: Q3, Q5, Q6, Q7, Q8 (new: the side of each repetition is not encoded), repetitions of A06 and A10, the
  English names and the unchecked Vietnamese readings
- Decisions: DEC-0022
- Bugs: BUG-0041 (S3, test gaps found by the mutation run, fixed in this task)
- Commit: c0567ae
- Plan: Docs/tasks/P1.04.md

## 2026-11-15 — X.16 Four candidate datasets checked; two downloaded (DONE)

- Checked on the primary pages (the pasted description was not trusted): UMONS-TAICHI (statements match Zenodo; we
  already held 3 of the 4 files of its list), Motion Embedding (no licence: not usable, not downloaded), Figshare "balance
  movements" (CC BY 4.0; content found by reading it: lower-limb model output, no marker coordinates, no video, so it does not
  serve the MVP metrics), PhysioNet Tai Chi gait (ODC-By, but it is walking of older adults: not downloaded)
- Downloaded (TLS on, md5 and size equal to the published values, members checked before extraction, extracted under
  `datasets/taiji/`, nothing in git): UMONS `Segmented_C3D.zip` (2.67 GB; 2,149 `.c3d` of 12 people and 13 classes, licence
  file CC BY-NC-SA 4.0; content not opened) and the Figshare RAR (202 MiB; 16 xlsx workbooks)
- Registry: D18 (Figshare), D19 (PhysioNet, `reference-only`), D12 and D13 updated; data README updated with provenance
- Fixed: BUG-0039 (3 old markdownlint warnings in the data README)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md`, `datasets/taiji/README.md` (the only tracked file under `datasets/`),
  `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`, `Docs/tasks/X.16.md`. No code
- Tests: gate 10/10 PASS in 19.4 s; `getDiagnostics` empty; `git status` shows no data file
- Open: no task uses the C3D data yet (a geometry study after P5 would need its own task)
- Bugs: BUG-0039 CLOSED
- Commit: add697e
- Plan: `Docs/tasks/X.16.md`

## 2026-11-15 — X.17 Coach-interview tasks set aside (DONE)

- Decided (maintainer): DEC-0021 — the interview part is put aside for now. P1.02 (interviews) and P1.03 (synthesis) are
  `BLOCKED` with the reason (no coach booked) and the way out (the maintainer books at least two coaches or says to
  resume). P1.01 stays DONE. The guide v0.2, the note template, the checklist and the four simulated records are kept
- Effects written down: gate G00 cannot pass; P1.07, P1.08 and the H review of P1.04 wait; P1.04 code, P1.05, P1.06, P1.09
  (when people are known) and P2 onwards go on; whether P9.01 may start before G00 is left to the maintainer; the plan's
  "fewer than two coaches" fallback is not triggered; nothing in the repository counts as evidence of a need
- Changed: `Docs/tracking/{DECISIONS,TASK_STATUS,CHANGELOG}.md` (P1 summary now 2 DONE, 6 in progress, 2 BLOCKED;
  total 11 / 6 / 2 / 81), `Docs/tasks/{P1.02,P1.03,X.17}.md`. No code
- Tests: documentation only; the counts add up (100 = 11 + 6 + 2 + 81); diagnostics none; full gate 10/10 PASS in 19.3 s
- Commit: add697e
- Plan: `Docs/tasks/X.17.md`

## 2026-11-15 — P1.02 Note template and interview checklist (IN_PROGRESS)

- Added: `Docs/discovery/notes/_TEMPLATE.md` (one section per part of the guide v0.2; fields `data_origin`, consent to take
  notes, time table, decision per card, guide feedback for the first interview, pre-submission check list) and
  `Docs/discovery/interview_checklist.md` (before, during, after, after the first interview, when to stop; an invitation
  message for O)
- Provenance question (Q4): the maintainer said the four simulated files came from real coaches; their text states they
  are invented. After the explanation the maintainer accepted that they stay simulated (rehearsal and review of the
  questions only). No real interview exists yet, so no `observed` note and nothing counts for G00 or P1.03
- Added later the same day: a fourth simulated record (SIM-4, an AI-built answer set on the guide v0.2, as its own header
  says) filed in `Docs/discovery/simulated/` as `data_origin: synthetic`; it works as a dry run of v0.2 (the new questions
  1.4 and (c) and the 8-row table behave as intended). The template now tells the writer to record "keep with a condition"
  as "change" plus the condition. It is not evidence and not an `observed` note
- Tests: documentation only; template checked against every question of the guide and the plan fields; gate 10/10 PASS in
  15.9 s
- Open: coaches and dates (O); the first real interview, which is also the trial read of the guide (DEC-0020); three
  `observed` notes for AC1
- Commit: add697e
- Plan: `Docs/tasks/P1.02.md`

## 2026-11-15 — P1.01 Interview guide v0.2, closed on a dry run (DONE)

- Decided (maintainer): DEC-0020 — the three simulated coach records the maintainer supplied are used as the dry run that
  stands in for AC2; they are not evidence (not in n, not in P1.03 or P1.08, no figure copied), only `observed` notes count
  for gate G00, and the first real interview is the real trial read of the guide (P1.02 plan, step 5 and check C-6).
  AGENTS.md §5.12 (domain content needs a coach) is met only after that interview
- Fixed: BUG-0037 (guide v0.2: question (c) of part 6, part 6 raised to 15 minutes and the total to 62, question 1.4
  limited with a separate 30-minute session for the list of movements, Appendix B with 8 rows); BUG-0038 (the four
  simulated files renamed SIM-1..SIM-3 to avoid the codes of real coaches, moved to `Docs/discovery/simulated/`,
  29 markdownlint warnings fixed; originals backed up outside the repository; no meaning changed)
- Changed: `Docs/discovery/interview_guide.md`, `Docs/discovery/simulated/*` (4 files), `Docs/tracking/{DECISIONS,BUGS,
  TASK_STATUS,CHANGELOG}.md`, `Docs/tasks/{P1.01,P1.02}.md`
- Tests: documentation only; C-1..C-6 re-run on v0.2 (pass); IDE diagnostics none on the five files; full gate 10/10 PASS
  in 19.4 s
- Open: the real coach read (first real interview); the 62 minutes in the guide header were checked by summing the parts
- Bugs: BUG-0037, BUG-0038 CLOSED
- Commit: add697e
- Plan: `Docs/tasks/P1.01.md` (§9 review)

## 2026-11-15 — P1.01 reviewed after the maintainer reported it done (still IN_REVIEW)

- Found: the guide `Docs/discovery/interview_guide.md` is unchanged since the draft; the four new files in
  `Docs/discovery/` are simulated interviews of three non-existent coaches (clearly labelled), which are a dry run and not
  the coach read that AC2 asks for. Re-run of C-1..C-6 on the guide: pass
- Registered: BUG-0037 (four defects of my draft shown by the dry run: question (c) asks for a number on cards without
  numbers; part 6 has 12 questions in 10 minutes; question 1.4 too big for part 1; Appendix B has too few rows),
  BUG-0038 (simulated personas coded H1–H3 collide with the real coach codes; no separate folder; 29 lint warnings)
- Plan changes: P1.02 template field `data_origin` (observed or synthetic), only observed notes count for G00; P1.04
  question Q7 on sub-phases
- Changed: `Docs/tracking/{BUGS,TASK_STATUS,CHANGELOG}.md`, `Docs/tasks/{P1.01,P1.02,P1.04}.md`. The guide and the four
  simulated files were not touched
- Commit: add697e
- Plan: `Docs/tasks/P1.01.md` §9

## 2026-11-15 — X.15 Stop waiting for access-controlled datasets (DONE)

- Decided (maintainer): DEC-0019 — an access request (form and e-mail to authors) had no reply, so the project depends on
  no request any more and uses the datasets it holds plus openly downloadable ones; D15 MADS leaves the plans. It extends
  DEC-0018. The dataset the request was for is not named (open question)
- Measured, read-only (no dataset file downloaded): Kinetics-400 validation split = 20 parts, 28.3 GB (HEAD requests on the
  CVDF files), 50 tai chi clips (50 per class per the paper); CMU mirror metadata lists take 12_04 as "tai chi" (FBX),
  its file path and size not found (404 at a guessed URL)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md`, `Docs/tracking/{DECISIONS,TASK_STATUS,CHANGELOG}.md`, `Docs/tasks/X.15.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 19.9 s; IDE diagnostics none
- Open (maintainer): which dataset the request was for; whether to download the Kinetics validation split (28.3 GB for
  50 clips; not recommended before P3)
- Commit: add697e
- Plan: `Docs/tasks/X.15.md`

## 2026-11-15 — X.14 Survey of openly downloadable Taijiquan datasets (DONE)

- Result: **no open dataset has per-movement labels for the 24-form**; every source with such labels needs a request
  (PSU-TMM100, TaiChi-AQA, TaiChi-24, the multi-view TaiChi set). Registered in `Docs/DATASET_REGISTRY_TAIJI.md`
  (nothing downloaded): D02 KungfuAthlete Taiji part (`reference-only`: licence conflict, the stricter applied), D15
  MADS (`not-usable` until the maintainer reads the terms: page unreachable), D16 Kinetics tai chi class (`dev-test`
  after the maintainer approves the download), D17 CMU mocap (`dev-test` after the maintainer reads the primary terms)
- Verification: a research subagent's report was treated as unverified; the primary or mirror pages of the kept
  candidates were re-read. MADS and the CMU site gave TLS errors (no bypass); the Kinetics CC BY 4.0 claim exists only on
  secondary pages; those points and the CMU take number are marked unverified in the registry
- Also fixed: BUG-0036 (16 old markdownlint warnings in the registry detail sections)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md`, `Docs/tracking/{TASK_STATUS,BUGS,CHANGELOG}.md`, `Docs/tasks/X.14.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 18.6 s; IDE diagnostics for the registry none
- Open (maintainer): read the MADS and CMU terms in a browser; decide on the Kinetics download; decide whether MADS or
  CMU may stand in for PSU-TMM100 in P10.07
- Bugs: BUG-0036 CLOSED
- Commit: add697e
- Plan: `Docs/tasks/X.14.md`

## 2026-11-15 — P1.01 Interview guide, draft v0.1 (IN_REVIEW)

- Added: `Docs/discovery/interview_guide.md` (Vietnamese): interviewer rules (open questions first, no number or tool
  before part 6, minutes as numbers, pseudonyms H1, H2…, notes only), parts 0–8 (about 57 minutes, including the
  24-form version taught for P1.04 and the pilot hours for P1.08), three sketch cards matching TECH_WORKFLOW Appendix
  B1–B3 with no number on them, and a time table
- Deviation: the cards carry no example number at all (the plan's Q4 default allowed invented numbers marked as such)
- Tests: documentation only; checks C-1..C-6 pass; IDE diagnostics none; full gate 10/10 PASS in 15.4 s
- Open: O's edits and one coach's trial read (AC2); the task is not DONE
- Commit: add697e
- Plan: `Docs/tasks/P1.01.md`

## 2026-11-15 — Phase 1 decisions; P1.10 closed by decision (DONE)

- Decided (maintainer): DEC-0016 ontology in YAML with PyYAML (P1.04 plan confirmed; one task ID kept, the code part
  may start before P1.02); DEC-0017 P1.09 depends on P1.06 (plan row updated, dated); DEC-0018 no access requests for
  now, use the datasets held and look for openly downloadable ones (X.14). The trial logistics (performer, phones,
  venue, date) are not known yet, so P1.09 waits
- Closed: P1.10, by the decision not to send (its AC1 allows that outcome). Registry: rows D06, D10, D11, D14 marked "not
  requested", allowed use unchanged (`not-usable`), roll-out table updated; P10.07 does not run unless DEC-0018 changes
- Found: BUG-0036 (old markdownlint warnings in the registry detail sections), scheduled in X.14. Also fixed here: the
  `Total` row of the TASK_STATUS summary had not been updated when P1 was planned (it still showed 0 in progress, 91
  TODO)
- Changed: `Docs/tracking/{DECISIONS,TASK_STATUS,BUGS,CHANGELOG}.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (P1.09, P1.10
  rows), `Docs/DATASET_REGISTRY_TAIJI.md`, `Docs/tasks/{P1.04,P1.09,P1.10}.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 16.0 s after these edits
- Commit: add697e
- Plan: `Docs/tasks/P1.10.md`

## 2026-11-15 — P1.01–P1.10 Phase 1 planned (PLAN_READY)

- Planned: a task file for each Phase 1 task with analysis, plan, tests, acceptance criteria and open questions;
  all ten are `PLAN_READY`. No deliverable exists yet (interview guide, protocol, consent form, ontology, and so on)
- Facts read from the code and documents that shape the plans: (1) `segment.view_category` in migration 0001 already
  allows `unknown`, and `consent_analysis` defaults to 1, so the ontology (P1.04) and the consent mapping (P1.06) follow
  that; (2) PyYAML is not in `uv.lock`, so an ontology in YAML needs one new MIT dependency (or TOML instead); (3)
  OpenWushu content is CC BY-SA 4.0 and its Taijiquan routine is the 42-movement one, so nothing is copied; (4) audio is
  the sync signal, so voice is recorded and the consent form must say so; (5) real names, calendars and prices must stay
  outside git (AGENTS.md §5.9): P1.02 and P1.08
- Observations on the plan, not applied (they need the maintainer): P1.09 should depend on P1.06 (a person is recorded);
  P3.07 and P5.10 speak of 5 clips from P1.09 while it yields one take; the plan's `docs/`, `discovery/`, `config/` map
  to `Docs/`, `Docs/discovery/`, `taiji_ai/config/`; P1.04 could split into code (no dependency) and H review; P1.07 is
  scheduled in week 1 together with its dependency P1.03, which is realistic only if the interviews end early in the
  week; G00 is listed twice with different content (§5 omits consent, §16 includes it); the v3 task P00.05 (license
  and data-flow matrix, hardware inventory) has no P1 task (partly covered by X.03 and `Docs/hardware_inventory.md`,
  which lists no camera)
- Revised the same day after a full re-read of the ten files: P1.04 action model (one action per numbered movement,
  with `sides`, `repetitions`, `technique`; the first model could not give 24 actions); P1.05 checkerboard size (25 mm
  squares too small at the recording distance), reason for 30 fps, camera levelling for the roll correction; P1.09 pose
  check (the existing smoke test uses a synthetic frame), checkerboard corner check, D08 registry and hardware inventory
  updates; P1.08 G00 checklist now includes consent; P1.06 sharing covers being shown to other participants; P1.01,
  P1.02, P1.03 ask for the 24-form version taught (P1.04 depends on it)
- Tests: documentation only; full gate 10/10 PASS in 15.3 s; IDE diagnostics empty; a manual check of the ten files for
  the usual lint mistakes found none
- Bugs: none
- Commit: add697e
- Plan: `Docs/tasks/P1.01.md` … `Docs/tasks/P1.10.md`

## 2026-11-15 — X.13 Record the deferral of X.08, GitHub Actions CI (DONE)

- Decided: X.08 is deferred by the maintainer (CI not needed for now). It stays `TODO`, not `CANCELLED`: cancelling needs
  the maintainer's approval and a reason (AGENTS.md §2.1), and the answer was that it is not needed now, not that it is never wanted
- Changed: `Docs/tracking/TASK_STATUS.md` (X.08 row, X.13 row), `Docs/tasks/X.07.md` §8 (the item about the go struck
  through), `Docs/tracking/CHANGELOG.md` (a note under the X.07 entry), `Docs/tracking/DECISIONS.md` (DEC-0015 sentence
  about X.08), `Docs/tasks/X.13.md` (new). No code, no `.github/`
- Tests: documentation only; full gate 10/10 PASS (figure in `Docs/tasks/X.13.md` §5); `getDiagnostics` empty
- Bugs: none
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.13.md`

## 2026-11-15 — X.12 Cut every verbatim quote of the maintainer's chat words from the logs (DONE)

- Changed: the quotations of the maintainer's words were replaced by neutral statements that keep who, what, the date
  and the condition (approved, requested, delegated, defaults accepted) in `Docs/tasks/{X.02,X.03,X.05,X.06,P0.04,P0.06,
  P0.07,X.07,X.11}.md`, `Docs/tracking/TASK_STATUS.md` (X.07, P0.07 and X.11 rows) and `Docs/tracking/DECISIONS.md`
  (DEC-0014): 25 replacements in 11 files by one script with a count assertion for each. The URL with the account name
  left the P0.04 header. The open items about the quotes were closed in X.11, TASK_STATUS and under the X.11 entry.
  No code
- Search: the grep used at the end of X.11 (five phrases, 12 lines in 5 files) was too narrow; a search for any quotation
  with Vietnamese letters and for quotations after answered / asked / said found the five older task headers and X.11
  itself as well. Quotations of the plan, UI strings and test placeholders are not chat words and stay
- Tests: documentation only; full gate 10/10 PASS in 17.4 s; greps C-1..C-3 find no chat quote; `getDiagnostics`
  (warnings and errors) empty
- Not covered: commit messages in git history, and a rule against quoting chat in `AGENTS.md` / `DECISIONS.md` (not asked)
- Bugs: none
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.12.md`

## 2026-11-15 — X.11 Fix the open markdownlint bugs; cut the chat quote from DEC-0015 (DONE)

- Fixed: BUG-0032 (`P0.06.md` §5 MD031), BUG-0033 (plan §14.3 MD032), BUG-0034 (`P0.07.md` MD022, found by this task's
  bug check), BUG-0035 (my own new files `X.10.md` MD032 + MD004 and `X.11.md` MD036, found by this task's
  verification). Only empty lines were inserted in `P0.06.md`, the plan and `P0.07.md`, outside the fenced evidence;
  `X.10.md`: one wrapped line reflowed; `X.11.md`: colons in the bold labels
- Changed: the verbatim quote of the maintainer's sentence was cut from `Docs/tracking/DECISIONS.md` DEC-0015 and
  `Docs/tasks/X.10.md` at the maintainer's request (the decision, residual risk and source are unchanged); `BUGS.md`
  (BUG-0032..0035 CLOSED, next free ID BUG-0036), `TASK_STATUS.md`, `Docs/tasks/{P0.06,P0.07,X.10,X.11}.md`,
  `Docs/IMPLEMENTATION_PLAN_V1.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 19.4 s; `getDiagnostics` (warnings and errors) empty on every
  changed document; manual checks C-1..C-5
- Open (maintainer): other places that quote the maintainer's words verbatim (12 lines in 5 files, found by a grep for the
  phrases of the earlier confirmations); left unchanged until the maintainer decides
- Note 2026-11-15 (X.12): the maintainer then asked to cut them all; done in X.12
- Bugs: BUG-0032..0035 CLOSED; no open bug in the register
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.11.md`

## 2026-11-15 — X.10 Drop the "machine B" part of the P0 acceptance (DONE)

- Decided: DEC-0015 — P0 is accepted when `tools/check.ps1` passes on the maintainer's single machine; there is no
  second machine and none is planned. Residual risk written in the decision: no run in a second environment (X.08, CI
  on a clean runner, would cover it and stays optional and not started)
- Changed: `Docs/IMPLEMENTATION_PLAN_V1.md` §4 (old sentence struck through, dated), `Docs/tracking/DECISIONS.md`
  (DEC-0015), `Docs/tracking/TASK_STATUS.md` (X.10; P0.05 and P0.07 rows), dated notes in `Docs/tasks/{P0.05,P0.07,X.07}.md`
  and under the X.07 entry below. Earlier mentions of machine B (P0.05 §1 / R7 / "not covered", P0.07 §9 review text, the
  2026-11-15 P0.05 entry) are kept as history and are superseded by this entry. No code
- Tests: documentation only; full gate 10/10 PASS in 18.9 s; manual checks C-1..C-4
- Bugs: BUG-0033 found (pre-existing MD032 in plan §14.3, S3, PLANNED)
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.10.md`

## 2026-11-15 — X.07 Close the P0 review leftovers (DONE)

- Fixed: BUG-0030 (the P0.06 / P0.07 rows of TASK_STATUS and dated notes under two CHANGELOG entries and under
  `P0.07.md` §8 now say the commits are in `main` and pushed; old text kept as history), BUG-0031 (BUG-0009 detail in
  BUGS.md set to CLOSED and rebuilt — its re-review section had been lost in an uncommitted overwrite and is marked as
  reconstructed; P0.06 §2.5 AC1–AC11 ticked with a dated note)
- Registered: X.08 (GitHub Actions CI for the gate) and X.09 (`mypy` on `tests/` and `tools/`), the follow-ups P0.05
  promised; both TODO, not started. BUG-0032 (pre-existing MD031 warnings in `P0.06.md` §5, S3, planned)
- Changed: `Docs/tracking/{BUGS,CHANGELOG,TASK_STATUS}.md`, `Docs/tasks/{P0.06,P0.07,X.07}.md`. No code
- Tests: documentation only; full gate 10/10 PASS in 14.9 s; `pytest -k bug_0009` 7 passed; manual checks C-1..C-6
- Open (maintainer): P0 acceptance needs the gate on machine B; X.08 needs a go before it starts
- Note 2026-11-15 (X.10): the machine B item is dropped (DEC-0015); only the go for X.08 remains open
- Note 2026-11-15 (X.13): the go for X.08 was answered: deferred, not needed now (X.08 stays TODO)
- Bugs: BUG-0030, BUG-0031 CLOSED; BUG-0032 PLANNED
- Commit: 9cce18f on branch `docs/X.07-X.13-p0-closeout` (local, not pushed)
- Plan: `Docs/tasks/X.07.md`

## 2026-11-15 — Q7 decision: hip-height variants A and B (DONE)

- Decided: DEC-0014 — P5.04 computes both variants as defined in Appendix B1 and reports both; no ordering criterion;
  the variant is chosen by the error against hand measurements (TECH_WORKFLOW §12 #4); no per-frame-Lambda variant now.
  Basis: A is more stable than B on 6 of 6 pinhole geometries of F-SYN SYN-09 (`Docs/tasks/P0.07.md` §5). The
  maintainer delegated the choice to the agent's recommendation
- Changed: `Docs/tracking/DECISIONS.md` (DEC-0014), `Docs/IMPLEMENTATION_PLAN_V1.md` (T-MET-05 and SYN-09 tolerance row),
  `Docs/tasks/P0.07.md`, `Docs/tracking/{TASK_STATUS,BUGS}.md`
- Merge and push: branch `feat/P0.07-synthetic-skeleton` merged into `main` (fast-forward) and `main` pushed on the
  maintainer's request
- Commit: this commit (branch `docs/Q7-hip-height-decision`, fast-forward merged)

## 2026-11-15 — P0.07 Synthetic HALPE_26 skeleton generator F-SYN — rework after review, closed (DONE)

- Reopened 2026-11-15 by the review (`Docs/tasks/P0.07.md` §9): five S2 bugs in the truth of the scenarios, four
  truth-breaking mutants passed all 27 tests. Closed after the rework R0–R9 (§9.4, §9.5).
- Fixed: BUG-0020 (unknown parameters rejected with `TypeError`), BUG-0021 (tempo truth from a closed-form continuous
  model: exact zero speed in pauses, analytic velocity, median group speed, poses independent of the frame rate;
  SYN-07 speed truth), BUG-0022 (SYN-09 is a pinhole camera; truth by the Appendix B1 formulas in Lambda), BUG-0023
  (SYN-10 query is the reference re-timed through one pose function, analytic `rate_k`, optional query offset/scale),
  BUG-0024 (SYN-12 shuffled detections, computed crossing interval, `return_offset_px`, `expected_target_lost()`),
  BUG-0025 (gap defaults in motion, edge-gap handling, `short_gap_s`), BUG-0026 (docs and evidence), BUG-0027 (task
  file and TASK_STATUS restored after a second overwrite), BUG-0028 (SYN-07 accepted and ignored `fps`), BUG-0029
  (SYN-12 empty absence raised `IndexError`)
- Changed: `taiji_ai/tests/helpers/synth.py` (rewritten, `SYNTH_VERSION = "syn/2"`, adult proportions, read-only truth),
  `taiji_ai/tests/unit/test_synth.py` (27 → 108 tests), `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3 / §15.1 / T-MET-05
  (dated, struck text kept, tolerance-change sentence restored), `Docs/tracking/DECISIONS.md` DEC-0013 (corrected)
- Tests: red first (59 failed on the first-version generator; later 3 failed for BUG-0028/0029); gate 10/10 PASS in
  14.6 s (246 pytest, 11 Vitest); mutation checks 32/32 caught (M1–M5, the survivors MS1–MS5, MN1–MN22)
- Findings for the maintainer: hip-height variant A is more stable than B on 6 of 6 pinhole geometries (range_A
  0.057–0.374, range_B 0.661–1.147 Lambda) — T-MET-05's "B more stable" is not asserted; decision Q7
- Bugs: BUG-0019..BUG-0029 CLOSED
- Decisions: DEC-0013 (corrected)
- Commit: 84c9bff on branch `feat/P0.07-synthetic-skeleton` (local, not pushed)
- Note 2026-11-15 (BUG-0030): the line above is history. The branch was later fast-forward merged into `main` and
  pushed; `84c9bff` is contained in `origin/main` (`22d3078` on 2026-11-15)
- Plan: `Docs/tasks/P0.07.md` (§9 review, §9.5 resolution, §5 rework evidence)

## 2026-11-15 — BUG-0019 P0.06 follow-up: stale `test_logs.py` and `posix_paths` default (DONE)

- Fixed: BUG-0019 — commit `4cee272` shipped the 21-test `test_logs.py` and `posix_paths=True` (made so that the stale
  tests pass). Restored `taiji_ai/tests/unit/test_logs.py` (42 tests: the 41 of the P0.06 rework + a test of the
  platform default) and the platform default of `taiji_ai/src/taiji_ai/logs.py` (`posix_paths` off on Windows, so
  request lines such as `GET /home/settings` stay readable)
- Tests: red first (`'GET <path>' == 'GET /home/settings'` on `posix_paths=True`); P0.06 mutation set M1–M9 (incl. M5b)
  caught on the restored tests; gate 10/10
- Bugs: BUG-0019 CLOSED; BUG-0018's history corrected (its Fix was a workaround)
- Commit: b060835 on branch `feat/P0.07-synthetic-skeleton` (local, not pushed)
- Note 2026-11-15 (BUG-0030): the line above is history. `b060835` is contained in `origin/main` (`22d3078` on
  2026-11-15)
- Plan: `Docs/tasks/P0.07.md` §4 R0

## 2026-11-15 — P0.07 Synthetic HALPE_26 skeleton generator F-SYN (DONE; reopened, superseded by the entry above)

- **Reopened 2026-11-15 by the review** (`Docs/tasks/P0.07.md` §9): status back to IN_PROGRESS; BUG-0020..0026
  registered (and BUG-0019 for P0.06). Claims below that the review disproved: ~~"analytic continuous-model ground
  truth"~~ (SYN-05 speed is `np.gradient` of the samples, SYN-07 has no speed truth, SYN-09 truth in px — BUG-0021,
  BUG-0022); ~~"Variant B hip height non-invariance confirmed"~~ (with the Appendix B formulas B is less stable than A
  in this scene — BUG-0022); ~~"T-SYN-02 (independent truth checks per scenario)"~~ (four truth-breaking mutations
  pass all 27 tests); ~~"no bugs caused by P0.07"~~. This entry will be superseded by the entry that closes the rework.
- Added: `taiji_ai/tests/helpers/__init__.py`, `taiji_ai/tests/helpers/synth.py` (synthetic HALPE_26 generator F-SYN, test-only, version `syn/1`), `taiji_ai/tests/unit/test_synth.py` (27 unit tests covering T-SYN-01..04)
- Changed: `taiji_ai/pyproject.toml` (`pythonpath = ["tests"]`, `known-first-party = ["taiji_ai", "helpers"]`), `Docs/IMPLEMENTATION_PLAN_V1.md` (§14.3, §15.1, P0.07 row), `Docs/tracking/DECISIONS.md` (DEC-0013), `taiji_ai/README.md` (Layout and Status), `Docs/tracking/TASK_STATUS.md` (P0: 7/7 DONE)
- Behaviour: deterministic generator covering 12 scenarios SYN-01..12 with analytic continuous-model ground truth; exports `make_sequence` (SYN-01..09), `make_pair` (SYN-10..11), and `make_scene` (SYN-12); SYN-01 defined as a single whole-clip pause (`n_pauses=1`); Variant B hip height non-invariance confirmed; binding tolerances table fixed for downstream tests (P3–P6); read-only arrays with `synthetic=True`
- Tests: T-SYN-01 (contract across all 12 scenarios), T-SYN-01b (body conventions, trunk length, facing), T-SYN-02 (independent truth checks per scenario), T-SYN-03 (seed determinism and global RNG isolation), T-SYN-04 (input error handling); 27 tests run in 0.11s; mutation checks M1–M5 all caught and restored hash-equal; full gate 10/10 PASS in 14.0s (144 pytest, 11 Vitest, 0 repo-hygiene violations)
- Bugs: BUG-0018 CLOSED (resolved prior to implementation; no bugs caused by P0.07)
- Decisions: DEC-0013
- Commit: not committed
- Plan: `Docs/tasks/P0.07.md`

## 2026-11-15 — P0.06 Unified logging and path redaction — rework after review, closed (DONE)

- Reopened 2026-11-15 by the review (task file §9): a redactor leak (BUG-0014), and P0.05 files and history
  overwritten during P0.06 (BUG-0012, BUG-0013). Closed after the rework R1–R9 (§9.4, §9.5).
- Fixed: BUG-0014 and BUG-0015 (`taiji_ai/src/taiji_ai/logs.py`: `PathRedactor` is one left-to-right pass with
  quote-aware path ends — UNC with spaces / Vietnamese / `c$`, apostrophes and `repr` spellings are redacted whole,
  `repr` tails of known roots are kept; POSIX personal prefixes only with POSIX path syntax, keyword `posix_paths`,
  default off on Windows), BUG-0017 (`run_log` writes its end line on `KeyboardInterrupt`/`SystemExit` too),
  BUG-0016 (`tests/conftest.py`: shared `clean_logging` + autouse logging-state guard), BUG-0012 (P0.05
  `tests/contract/test_check_script.py`, `test_repo_hygiene_git.py` restored verbatim), BUG-0013 (CHANGELOG P0.05
  entries, BUG-0008 detail, BUGS next free ID, TASK_STATUS date restored)
- Changed: `logs.py` docstrings (format, placeholders, end rules, limits, threads); level names limited to the five
  documented ones; unsafe-root check fails closed; `tests/unit/test_logs.py` (41 tests), `tests/api/test_api_core.py`
  (fixture use, traceback assertion); `Docs/TECH_WORKFLOW_V1.md` §10.1, `taiji_ai/README.md`, `DECISIONS.md`
  DEC-0012, `IMPLEMENTATION_PLAN_V1.md` T-CORE-01 (wording with limits, dated)
- Tests: red first (18 failed + 3 errors on the unfixed code); full gate 10/10 PASS in 19.0 s (137 pytest,
  11 Vitest); mutations M1–M9 all caught, files restored hash-equal; BUG-0010 / BUG-0008 mutation checks re-run on the
  restored P0.05 tests; real-API smoke re-run
- Bugs: BUG-0012..BUG-0017 CLOSED (BUG-0011 closed in the first pass)
- Decisions: DEC-0012 (corrected)
- Open: maintainer to confirm Q1–Q6 explicitly (task file F-8)
- Commit: 4cee272
- Plan: `Docs/tasks/P0.06.md` (§9 review, §9.4 rework plan, §9.5 resolution, §5 rework evidence)

## 2026-11-15 — P0.06 Unified logging and path redaction (DONE; reopened, superseded by the entry above)

- **Reopened 2026-11-15 by the review** (`Docs/tasks/P0.06.md` §9): status back to IN_PROGRESS; BUG-0012..0017
  registered. Claims below that the review disproved: ~~"two-pass path redaction prevents personal path leakage"~~
  (BUG-0014: UNC and apostrophe paths leak); ~~`tests/contract/test_check_script.py` "fixed … environment
  inheritance"~~ (that was P0.05 rework 2; the file was overwritten with an older version, BUG-0012). This entry is
  superseded by the rework entry above.

- Added: `taiji_ai/src/taiji_ai/logs.py` (`PathRedactor`, `RunContextFilter`, `RunMatchFilter`, `RedactingFormatter`, `configure_logging`, `run_log`, `current_run_id`), `taiji_ai/tests/unit/test_logs.py` (T-CORE-01a..n, 21 tests)
- Changed: `taiji_ai/src/taiji_ai/config.py` (`log_level` field, default `"INFO"`), `taiji_ai/src/taiji_ai/api/app.py` (redacted error boundary for BUG-0011), `taiji_ai/src/taiji_ai/api/__main__.py` (`configure_logging` before uvicorn, `log_config: None` in `server_config()`), `taiji_ai/tests/api/test_api_core.py` (T-CORE-01o..p, T-API-04b, BUG-0011 red-first tests), `taiji_ai/tests/unit/test_config.py` (`TAIJI_LOG_LEVEL` tests), `taiji_ai/tests/contract/test_check_script.py` (fixed `TAIJI_CHECK_RUNNING` environment inheritance in child runner)
- Behaviour: unified ISO-8601 logging across application, uvicorn and background runs; per-run `run.log` written in append mode; two-pass path redaction prevents personal path leakage across console, file logs, tracebacks, warnings and API errors
- Tests: T-CORE-01 (a..p), T-API-04b, BUG-0011 regression tests pass; mutation checks M1..M4 verified; full quality gate 10/10 PASS in 26.4s
- Bugs: BUG-0011 (closed in this task)
- Decisions: DEC-0012
- Commit: not committed
- Plan: `Docs/tasks/P0.06.md`

## 2026-11-15 — P0.05 One-command quality gate `tools/check.ps1` — rework after re-review, closed (DONE)

- Reopened 2026-11-15 by the re-review (task file §9): BUG-0009's fix was incomplete, BUG-0010 and findings F-3..F-12
  were new; both bugs were introduced by this task, so it could not stay DONE/IN_REVIEW. Closed after rework 2.
- Fixed: BUG-0009 (`tools/repo_hygiene.py`: one `stat()` per file via `collect_entries()`; any file that cannot be
  stat'ed gives exit 2 naming the file, never 0 or 1), BUG-0010 (`tools/check.ps1`: nested-run guard checked before
  preflight; the test no longer starts a real gate run), BUG-0008 (closed: shared `parse_errors()` helper with a
  negative control)
- Changed: `tools/check.ps1` (`[n/N]` from the step count; relative interpreter path in the plan; `Get-UvLauncher`
  shared by the step and preflight; header prints Python, uv, Node, pnpm versions), `store/artifacts.py` (unneeded
  `type: ignore` removed, docstring), `tests/contract/test_check_script.py` (9 tests), `tests/unit/test_repo_hygiene.py`
  (51 tests, 7 for BUG-0009), `tests/contract/test_repo_hygiene_git.py` (no `git commit`), `tests/unit/test_core.py`
  (BUG-0006 tests check `ValueError` and the message), `taiji_ai/README.md` (gate in its own section after the web
  setup), `Docs/IMPLEMENTATION_PLAN_V1.md` (date markers, T-TOOL rows), `Docs/tracking/DECISIONS.md` (DEC-0011 note)
- Tests: `tools\check.ps1` full run 10/10 PASS in 14.6 s warm (73.8 s cold), pytest 91 passed, Vitest 11 passed,
  0 hygiene violations; regression tests written and run red first (5 failures on the unfixed code); mutation check of
  the guard test; fault injection (lint error), stale lock, `-SkipWeb`, `-NoGpu` from `%TEMP%`, nested run, empty root
- Bugs: BUG-0008, BUG-0009, BUG-0010 CLOSED (with BUG-0006, BUG-0007 from the original task)
- Not covered: a run on machine B (maintainer); GitHub Actions CI (follow-up)
- Commit: b69f8ee
- Plan: `Docs/tasks/P0.05.md` (§3.1 rework plan, §4 step 13, §5 rework-2 evidence, §9 re-review)

## 2026-11-14 — P0.05 One-command quality gate `tools/check.ps1` (IN_REVIEW; superseded by the 2026-11-15 entry above)

- Added: `taiji_ai/tools/check.ps1` (10-step quality gate: uv-lock, ruff-check, ruff-format, mypy, pytest, web-lint, web-typecheck, web-test, web-build, repo-hygiene; Windows PowerShell 5.1 compatible, ASCII-only, Out-Host stream isolation), `taiji_ai/tools/repo_hygiene.py` (rules R1–R11, 5 MB limit), `tests/contract/test_check_script.py` (T-TOOL-01..03, 5 tests), `tests/unit/test_repo_hygiene.py` (T-TOOL-04, 44 tests), `tests/contract/test_repo_hygiene_git.py` (T-TOOL-05, CLI subprocess contract)
- Fixed: BUG-0006 (`atomic_save_npz` keyword reserved check and object-dtype rejection; `tests/unit/test_core.py`), BUG-0007 (removed hard-coded test counts in `taiji_ai/README.md`), BUG-0008 (T-TOOL-01 captures `[ref]$errors` and added negative syntax test), ~~BUG-0009 (`repo_hygiene.py` no longer swallows stat errors on existing files)~~ (incomplete, see 2026-11-15)
- Changed: `AGENTS.md` §7, `CLAUDE.md`, `CONTRIBUTING.md`, `Docs/IMPLEMENTATION_PLAN_V1.md` (§4, §15.1, §16.3), `Docs/TECH_WORKFLOW_V1.md` line 57
- Decisions: DEC-0011
- Tests: all 10 gate steps pass in 13.2s (79 python tests, 11 vitest tests, 0 hygiene violations); ~~full verification matrix V-01..V-15 verified on machine A~~ (overstated: V-02, V-09, V-13 were not run as described; verified 2026-11-15, see task file §5 and §9)
- Commit: not committed
- Plan: `Docs/tasks/P0.05.md` (status: IN_REVIEW)

## 2026-11-14 — X.06 Usable repositories recorded in the docs (DONE)

- Usable items from X.05 (already cloned, git-ignored): `repos/taolu/tpz` (MPL-2.0, E04 reference) and
  `repos/taolu/_no-license/wushu_vision` (ideas only)
- Changed: `repos/taolu/REPOS.md` (summary: rubric row + new E04 row), `Docs/TECH_WORKFLOW_V1.md` §11 E04,
  `taiji_ai/THIRD_PARTY_NOTICES.md` §6
- Commit: `ce859b4` (X.05 + X.06 documentation, pushed) + follow-up commit recording the push verification
- Plan: `Docs/tasks/X.06.md`

## 2026-11-14 — X.05 Survey of additional Wushu repositories (DONE)

- Reviewed 17 GitHub repositories + 3 external links (static reading only); verdicts in `repos/taolu/REPOS.md`
- Cloned (git-ignored): `repos/taolu/tpz` (MPL-2.0; IWUF 2024 deduction/nandu JSON, IWUF rule PDFs) and
  `repos/taolu/_no-license/wushu_vision` (reference only)
- Registered dataset D14 (S3GCN Tai Chi with expert scores, research-only, on request) in `Docs/DATASET_REGISTRY_TAIJI.md`
- Commit: not committed
- Plan: `Docs/tasks/X.05.md`

## 2026-11-14 — P0.04 First commit and push to GitHub (DONE)

- Remote: `origin` = `https://github.com/vtruong2k3/wushu.git`; branch `main` tracks `origin/main`
- Commit `8fae211` (initial, 92 files): everything recorded in this changelog up to P8.02. Earlier entries that say
  "Commit: not committed" are included in this commit
- Added: `.gitattributes` (LF normalization), `CONTRIBUTING.md`
- Verification: secret scan clean, no data/weights/clones/datasets/venv/node_modules/dist in the tree, remote HEAD ==
  local HEAD
- Commit: `8fae211` + this follow-up commit (records the push verification)
- Plan: `Docs/tasks/P0.04.md`

## 2026-11-14 — P8.02 Web scaffold: React + Vite + TypeScript (DONE)

- Added: `taiji_ai/web/` — Vite 8 + React 19 + TS 6, React Router 8, TanStack Query 5; typed API client
  (`src/api/client.ts`, backend error format → `ApiError`), `useHealth`, layout, status page (Vietnamese UI),
  404 page; Vitest + Testing Library tests; ESLint; `pnpm-workspace.yaml` with `minimumReleaseAge` 7 days; lockfile
- Changed: root `.gitignore` (node_modules, web/dist, tsbuildinfo, coverage, playwright output); `THIRD_PARTY_NOTICES`
  §2b (web deps, license totals, accepted advisory); README (web commands, status); AGENTS §7; TASK_STATUS P0.05 note
- Tests: Vitest 11 passed; lint/typecheck clean; build OK; FastAPI serves the build; headless Edge renders live data;
  Python 27 passed
- Bugs: BUG-0005 (S3) found in self-review, fixed with regression tests, closed
- Decisions: DEC-0010
- Commit: not committed
- Plan: `Docs/tasks/P8.02.md`

## 2026-11-14 — P8.01 FastAPI skeleton, Streamlit removed (DONE)

- Added: `taiji_ai/src/taiji_ai/api/` — `app.py` (factory, lifespan: migrations + one-time model verification),
  `errors.py` (uniform JSON errors, no traceback leak), `static.py` (web/dist + SPA fallback, `/api/*` stays JSON,
  no-cache index, traversal-safe), `routers/health.py` (`GET /api/health`), `__main__.py` (`python -m taiji_ai.api`,
  127.0.0.1 only); tests `tests/api/test_api_core.py` (T-API-01..04), `tests/unit/test_config.py`
- Changed: `config.py` (`web_dist_dir`, `api_port` default 8007, `API_HOST`; env read at construction — BUG-0004);
  `pyproject.toml` (− streamlit, + fastapi 0.162.6, uvicorn 0.54.0, dev httpx2 2.16.0); README, THIRD_PARTY_NOTICES,
  env_check, AGENTS §7, hardware inventory
- Removed: `taiji_ai/app/` (Streamlit placeholder)
- Tests: 27 passed; ruff clean; real-server smoke (thread + `python -m taiji_ai.api`) OK, health 2.2 ms avg
- Bugs: BUG-0004 (S3) fixed and closed
- Decisions: DEC-0009 (port 8007, httpx2)
- Commit: not committed
- Plan: `Docs/tasks/P8.01.md`

## 2026-11-14 — X.04 UI stack switched to React + Vite + FastAPI: decision and re-plan (DONE)

- Decision: DEC-0008 — React + Vite + TypeScript SPA, FastAPI backend serving `/api` and `web/dist`; Streamlit and
  Next.js rejected for the MVP
- Changed: `Docs/TECH_WORKFLOW_V1.md` → v1.1 (stack, rejected options, W3 video player, code tree with `api/` and
  `web/`, process model, environments, license table, E02); `Docs/IMPLEMENTATION_PLAN_V1.md` (new P8: 16 tasks,
  13.75 days; totals ≈ 54 days; API/Web/E2E test IDs; G04 row; timeline; risks); `AGENTS.md` §5.7 and §7;
  `Docs/tracking/TASK_STATUS.md` (P8 regenerated, 100 tasks)
- Added: `.markdownlint.jsonc` (MD060 off — table pipe style only)
- Bugs: BUG-0002 (S3, stale Python row) found and closed; BUG-0003 (S3, MD013 re-enabled by the new lint config) introduced, fixed and closed
- Not yet changed: code still uses Streamlit until P8.01/P8.02
- Commit: not committed
- Plan: `Docs/tasks/X.04.md`

## 2026-11-14 — X.03 Rules for third-party code, models and datasets (DONE)

- Changed: `AGENTS.md` — new §9 *Third-party code, models and datasets* (license tiers, repositories, weights,
  datasets, own recordings, where to record); "When in doubt" renumbered §9 → §10 (no existing reference used §9);
  §1 table and §5.10/§5.11 point to §9
- Added: `taiji_ai/THIRD_PARTY_NOTICES.md` (direct deps with metadata licenses, NVIDIA proprietary CUDA/cuDNN wheels,
  FFmpeg CLI, model weights, copied code = none, reference-only sources)
- Changed: `Docs/DATASET_REGISTRY_TAIJI.md` — column "Mục đích được phép" for every dataset, new row D08 (own recordings),
  header rewritten; `taiji_ai/pyproject.toml` — pytest marker `dataset`; `CLAUDE.md` — pointer to §9
- Tests: pytest 12 passed; ruff clean; `uv lock --check` unchanged; `§` references verified; git dry-run 54 files,
  no forbidden files
- Bugs: BUG-0001 (S3, stale registry header) found and closed in this task
- Decisions: DEC-0007
- Commit: not committed
- Plan: `Docs/tasks/X.03.md`

## 2026-11-13 — X.02 Git repository moved to the workspace root (DONE)

- Removed: `taiji_ai/.git` (empty: 0 commits, 0 refs, 0 objects — verified before deletion)
- Added: root git repository (`git init -b main`), root `.gitignore`
  (ignores `repos/*/*` except `REPOS.md`, `datasets/*/*` except `README.md`, `.venv`, caches, media/weights/archives/arrays)
- Changed: `AGENTS.md` §1 (repo root note), §8 (single repo, dry-run before staging);
  `Docs/IMPLEMENTATION_PLAN_V1.md` §2 (Git row); `Docs/tracking/DECISIONS.md` (DEC-0006)
- Verification: `git add --dry-run .` → 52 files, ≈ 484 KB, largest `taiji_ai/uv.lock` 145 KB;
  forbidden-pattern grep → no match; personal-data grep → no match; `check-ignore` confirms clones, dataset data,
  `.venv`, `app.sqlite3`, `*.onnx` ignored; `pytest` 12 passed
- Bugs: none
- Commit: not committed (first commit is P0.04, awaits maintainer request)
- Plan: `Docs/tasks/X.02.md`

## 2026-11-13 — X.01 Repository working rules and tracking files (DONE)

- Added: `AGENTS.md`, `CLAUDE.md` (imports AGENTS.md), `Docs/tasks/_TEMPLATE.md`, `Docs/tracking/TASK_STATUS.md`,
  `Docs/tracking/BUGS.md`, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/DECISIONS.md`
- Behaviour: mandatory task lifecycle (analyze → plan → re-read → code → self-review → close),
  bug register with fix plans, history updates
- Tests: n/a (documentation)
- Commit: not committed

## 2026-11-13 — P0.01–P0.03 Code base foundation (DONE, recorded retroactively)

Done before the task lifecycle existed; no per-task plan files.

- Added: `taiji_ai/pyproject.toml`, `uv.lock`, package skeleton `src/taiji_ai/{io,pose,store,…}`,
  `io/probe.py`, `io/frames.py`, `pose/skeleton.py`, `pose/registry.py`, `pose/rtm.py`, `store/artifacts.py`,
  `store/db.py`, `migrations/0001_init.sql`, `tools/fetch_models.py`, `tools/env_check.py`, `app/Home.py`,
  tests (`tests/conftest.py`, `tests/unit/test_core.py`, `tests/contract/test_video_io.py`,
  `tests/contract/test_pose_gpu.py`)
- Environment: Python 3.12.10, uv 0.13.8, onnxruntime-gpu 1.32.0 [cuda,cudnn], rtmlib 0.0.16, PyAV 19.0.2,
  OpenCV headless 4.14 (held < 5)
- Models: YOLOX-m HumanArt + RTMPose-m body7-halpe26 fetched, SHA-256 in `models/registry.json`
- Tests: 12 passed (T-IO-01..05, T-POSE-01..03, T-STORE-01..03, skeleton); ruff clean;
  GPU smoke: det 29 ms/frame, pose 5 ms/person on RTX 3060
- Docs: `Docs/hardware_inventory.md`; decisions DEC-0001..0005
- Commit: not committed (`git init` only)

## 2026-11-13 — Documentation baseline

- `Docs/WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md` (provided), `Docs/TECH_WORKFLOW_V1.md`, `Docs/IMPLEMENTATION_PLAN_V1.md`,
  `Docs/DATASET_REGISTRY_TAIJI.md`, `datasets/taiji/README.md`, `repos/taolu/REPOS.md`, `repos/sanda/REPOS.md`
