# Bug Register

Rules: `AGENTS.md` §3. IDs are sequential (`BUG-NNNN`), never reused. Every bug must have a fix plan.
Severity: **S1** critical · **S2** major · **S3** minor.
Lifecycle: `OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED` (or `WONT_FIX` with maintainer approval).

**Next free ID:** `BUG-0075`

## Summary

| ID       | Title                                                                                                                      | Sev | Status | Found in                                                                   | Fix task | Regression test                                                  | Opened     | Closed     |
| -------- | -------------------------------------------------------------------------------------------------------------------------- | --- | ------ | -------------------------------------------------------------------------- | -------- | ---------------------------------------------------------------- | ---------- | ---------- |
| BUG-0074 | The allowed-use text of D20 in `Docs/DATASET_REGISTRY_TAIJI.md` does not list the look at the mask layer of P4.01 (M-QLT-01, counts only on the P3.08 pose files): AGENTS.md 9.4 item 3 asks for the use to be written there before it happens | S3 | CLOSED | `Docs/DATASET_REGISTRY_TAIJI.md` (D20 row), found by the agent while adding M-QLT-02 for P4.02 | P4.02 | Manual check: the row names P4.01 and P4.02 and their limits (2026-11-17) | 2026-11-17 | 2026-11-17 |
| BUG-0073 | The detector tool (P3.09) and its rule kept the NMS limit **0.45** as the default for YOLO11 ("YOLOX uses 0.45") after the limit of the shipping graph was read as **0.65**: running `detector_compare.py run` without `--nms-iou` measures a different operating point than DEC-0043 and the report state; `DetectorRule.matched_nms_iou` (unused) and its test hold the same stale 0.45 | S3 | CLOSED | `taiji_ai/tools/detector_compare.py`, `bench/detector_metrics.py` (P3.09, found by the agent in the self-review read-back) | P3.09 | `test_t_det_08_the_default_nms_limit_of_the_tool_is_the_one_of_the_shipping_graph` | 2026-11-17 | 2026-11-17 |
| BUG-0072 | `prepare_onnxruntime` (P3.02) remembers that it ran for **any** device: a call for the CPU stops a later call for CUDA from loading the DLLs of the nvidia packages, and the CUDA session then falls back to the CPU or fails | S3 | PLANNED | `taiji_ai/src/taiji_ai/pose/rtm.py` `prepare_onnxruntime` (P3.02), found while writing P3.09 | X.30 | to be written with the fix (a subprocess test, `gpu` marker); the workaround in `bench/yolo_onnx.py` has `test_t_det_09_a_cpu_session_before_a_cuda_session_does_not_break_cuda` | 2026-11-17 | |
| BUG-0071 | The benchmark orchestrator (P3.07, first version) handed an unknown loss of the tracked share (no clip had a target in both runs) to the rule for N as 0.0, so a missing measurement counted as "no loss" and could let an N pass | S3 | CLOSED | `taiji_ai/src/taiji_ai/bench/orchestrate.py`, `bench/decision.py` (P3.07, first version) | P3.07 | `test_t_bench_06_an_unknown_tracked_share_is_not_acceptable_and_is_not_taken_as_zero` | 2026-11-16 | 2026-11-16 |
| BUG-0070 | `associate_tracks` (first version, P3.05) divided the keypoint distance by the height of the hull of the *common* keypoints instead of the height of the whole track: when only a few keypoints are common (the head, two rows of the body) the term was inflated (a 20 px move: 0.14 instead of 0.03), so a partly visible person could be refused and split into two tracks | S3 | CLOSED | `taiji_ai/src/taiji_ai/track/associate.py` `_pair_cost`, found by the agent when reading the file back before closing P3.05 | P3.05 | T-TRK-03e (the height test) | 2026-11-16 | 2026-11-16 |
| BUG-0069 | `store/artifacts.atomic_write_bytes` leaves `<name>.tmp` behind when the write or `os.replace` fails, and creates missing parent folders silently: a failed save litters the run folder and a typo in a path creates a new tree | S3 | CLOSED | `taiji_ai/src/taiji_ai/store/artifacts.py`, found by the agent while planning the atomic test of P3.03 | P3.03 | T-ART-01 (3 tests) | 2026-11-16 | 2026-11-16 |
| BUG-0068 | P2.05 tests and records do not show what they claim: the tests of `test_flash.py` leave 10 of 14 mutants of `flash.py` alive (9 after the tests of X.23 and X.24; 2 of the 9 are equivalent): the drift and `t_ref_s` of the mapping (every fixture has drift 0), the swap of the folder order, the slower-camera frame (both cameras 30 fps), the search margin, the adaptive threshold (`k_mad`), the refractory time; step 4 of the plan ("run mutation checks") has no evidence; §7 says "None found" (BUG-0064 was in this task); "edge cases: empty input, single flash" are not tested; LaTeX in the task file and DEC-0032; counts of a moving tree (722, 44.4 s) | S3 | CLOSED | P2.05 review, `Docs/tasks/P2.05.md`, `taiji_ai/tests/contract/test_flash.py` | P2.05 rework | T-SYNC-04g..n (13 tests) | 2026-11-16 | 2026-11-16 |
| BUG-0067 | `io/flash.py` breaks repository rules: dead arguments (`settings` of `validate_sync`, `rotation_deg` of `brightness_series`), a made-up frame interval (`median_dt_s or 1/30`), and no check that the two recording folders are the ones the audio result was made from (`recording_id_a/b`, take): the validation of another pair runs silently | S3 | CLOSED | P2.05 review, `taiji_ai/src/taiji_ai/io/flash.py` | P2.05 rework | T-SYNC-04n (4 tests) | 2026-11-16 | 2026-11-16 |
| BUG-0066 | The flash detector needs a frame-mean luma step of 15 levels: a lamp that lights 5 % of a 640x360 frame (step 8) or 2 % (step 3) is not found, 10 % (step 16) only just; a flash whose first step is split over two frames is found one frame late (step 40, 0.3 split) or not at all (step 25, 0.5 split), so two cameras can differ by a frame on a perfect mapping, against a limit of one frame; the thresholds rest on synthetic full-frame flashes only | S2 | PLANNED | P2.05 review, `taiji_ai/src/taiji_ai/io/flash.py` (`find_flash_onsets`), DEC-0032 | to open after the maintainer's decision | regression tests named in the fix plan | 2026-11-16 | |
| BUG-0065 | `sync_take` writes the `sync` database row for every take with `status = ok`, also when `usable_for_metrics` is false, and the row has no usable column: a take whose mapping is wrong by 1 s (flash residual 1000 ms) has a row with `offset_s` 1.5 (true 0.5) and `validated_by = 'flash'`; no code reads the row yet | S2 | CLOSED | P2.06 `taiji_ai/src/taiji_ai/pipeline/sync_take.py`, `schemas/sync.py` (`to_db_row`), migration 0001 (`sync`), found by the agent while writing the end-to-end test of X.24 | X.25 | T-SYNC-05f (4 tests) | 2026-11-16 | 2026-11-16 |
| BUG-0064 | The flash check passes a take as usable when the audio lag is wrong by one pair gap (1 s) and one camera shows only one flash of a pair: unmatched flashes are ignored and there is no check of the pair structure (probe: residual 0.0 ms, `usable_for_metrics = true`) | S1 | CLOSED | P2.05 `taiji_ai/src/taiji_ai/io/flash.py` `validate_sync`/`match_residuals`, found while planning the fix of BUG-0063 | X.23 | T-SYNC-04e (15 tests) and T-SYNC-04f (10 cases) | 2026-11-16 | 2026-11-16 |
| BUG-0063 | Known limits of the audio match that sound alone cannot remove: (1) a clap pair damaged the same way at both ends on one camera (one clap missing or swallowed, a tap of the phone louder than the claps, unequal claps) gives a lag wrong by one pair gap that the two windows agree on, so `ok` is possible with a wrong offset; (2) takes under 60 s keep the 45 % windows (a large start difference abstains); (3) weak claps (amplitude 0.3 with noise 0.02) are refused by `min_crest` 2.5 and `min_peak` 0.25 | S2 | PLANNED | P2.04 adversarial pass (about 1100 probe cases), `taiji_ai/src/taiji_ai/io/audio_sync.py` | P2.06, P2.07 | P2.06: a take whose audio lag is wrong by 1 s is `usable_for_metrics = false` through the flash residual | 2026-11-16 | |
| BUG-0062 | The P2.04 records do not match the code: "Bugs: none" (see BUG-0058..0061), AC1 "mutations caught" ticked and plan step 5 (mutation check) missing from the log, the claim "< 0.01 ms precision" (DEC-0031, CHANGELOG, README) is not asserted by any test, T-SYNC-01b..d are not in the plan's test list, the reason of `min_peak` and `min_peak_ratio` is not recorded (AC2), LaTeX in the records | S3 | CLOSED | P2.04 review, `Docs/tasks/P2.04.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG,DECISIONS}.md` | P2.04 | Gate 10/10 on the final tree; records match the output | 2026-11-16 | 2026-11-16 |
| BUG-0061 | `io/audio.py` and `io/audio_sync.py` break repository rules (the same kinds as BUG-0054): dead `settings` argument, an `except OSError: pass` and two broad `except Exception`, invented numbers (`peak_ratio` 999.0, a placeholder window `(0.0, 1.0)` for "no audio", `drift` 0.0), the sample rate of the files ignored, generic `ValueError`, a 1.15 GB envelope for a 30 min take, a duplicated block | S3 | CLOSED | P2.04 review, `taiji_ai/src/taiji_ai/io/{audio,audio_sync}.py` | P2.04 | T-SYNC-10 (50 tests: refusals, cache, ffmpeg failure, windows only, dropped audio, damaged headers) | 2026-11-16 | 2026-11-16 |
| BUG-0060 | The P2.04 tests passed with 13 broken rules (a mutation run on a copy: 34 mutants, 14 survived, one is equivalent): sub-sample interpolation (removed or with the wrong sign), the A/V offset of the end window, the status `start_only`, the `min_peak` and `min_peak_ratio` gates, the take-mismatch refusal, the `audio.wav` cache, the stereo downmix, the low-pass cut-off, the 15 s search limit; no test on a take of 60 s or more; T-SYNC-01c fakes the A/V offset by editing `recording.json`; debug prints left in two tests | S3 | CLOSED | P2.04 mutation check, `taiji_ai/tests/contract/test_audio_sync.py` | P2.04 | 187 tests in five files (the first version had 10); every mutant of the review's list is caught | 2026-11-16 | 2026-11-16 |
| BUG-0059 | `estimate_sync` takes `t_ref_s` and the drift at the centres of the 30 s search windows, not at the claps: a 100 ppm drift is reported as 118.5 ppm on a 120 s take (+18 %) and 106 ppm on a 300 s take, with 0.8 ms of offset error at `t_ref_s`; `window_a_s` and `t_ref_s` are on A's audio timeline, the schema says video timeline | S3 | CLOSED | P2.04 review (probe E2), `taiji_ai/src/taiji_ai/io/audio_sync.py` | P2.04 | T-SYNC-07a..g in `test_audio_sync_long.py` (red first); the mutations are caught | 2026-11-16 | 2026-11-16 |
| BUG-0058 | `estimate_sync` loses the end window or accepts a wrong lag when camera B stops before camera A (takes of 60 s or more): at 120 s and 300 s, B stopping 3 s early gives `start_only` although both files hold both claps; B stopping 0.4 s early (or starting early and stopping 1 s early) gives `status ok` with the end lag exactly 1 s wrong (the other clap of the pair): drift −11111 ppm at 120 s, −3704 ppm at 300 s, `peak_ratio` 120+. No test has a take longer than 16 s | S1 | CLOSED | P2.04 review (probe E1), `taiji_ai/src/taiji_ai/io/audio_sync.py` (end window, lines 314–344) | P2.04 | T-SYNC-06 (30 cases), 06b, 06d, 06e, 06f, T-SYNC-08 (drift of either sign around the limit); 80 of the 149 new tests were red first | 2026-11-16 | 2026-11-16 |
| BUG-0057 | `Docs/tracking/CHANGELOG.md` has two markdownlint MD049 warnings in the X.03 entry (2026-11-14, in HEAD): the words _Third-party code, models and datasets_ use underscore emphasis where the project style is the asterisk; shown by the IDE when the P2.03 rework edited the file | S3 | CLOSED | P2.03 rework, `Docs/tracking/CHANGELOG.md` (X.03 entry) | P2.03 | IDE diagnostics clean for that line after the edit (2026-11-16) | 2026-11-16 | 2026-11-16 |
| BUG-0056 | The P2.03 records do not match the tree: the gate is red now (`cli.py:158`, E501 and format), the suite has 674 tests (records say 673, "10 new" is 11), step 2 is logged done without the planned edit-list fixture, the self-review claims "no bugs" and "errors never swallowed", the test IDs `T-IO-10b/10c/11b` are not in the plan | S3 | CLOSED | P2.03 review, `Docs/tasks/P2.03.md`, `Docs/tracking/{TASK_STATUS,CHANGELOG,DECISIONS}.md`, `taiji_ai/src/taiji_ai/cli.py` | P2.03 | Gate 10/10 on the final tree (2026-11-16); counts measured from the run output | 2026-11-16 | 2026-11-16 |
| BUG-0055 | A proxy whose timestamp check failed is reported as success (INFO log, exit code 0), and `taiji ingest --proxy` reports "error" without the recording ID when the proxy step fails after the recording was stored | S3 | CLOSED | P2.03 review (probes P2 and P3), `taiji_ai/src/taiji_ai/io/proxy.py`, `io/ingest.py`, `cli.py` | P2.03 | T-IO-27 in `test_proxy.py` and `test_cli_ingest.py` (red first); the mutations are caught (2026-11-16) | 2026-11-16 | 2026-11-16 |
| BUG-0054 | `io/proxy.py` breaks repository rules: a Vietnamese docstring line, the `settings` argument is never used, two `except OSError: pass`, invented numbers in `proxy.json` (`999.0`, `points=1` with nothing measured), the command is written twice (manifest `args` can drift from what runs), `PtsScan.t_sec` re-implemented, `proxy.mp4` replaced before `proxy.json` | S3 | CLOSED | P2.03 review, `taiji_ai/src/taiji_ai/io/proxy.py`, `io/ingest.py` | P2.03 | T-IO-24, 25, 26 in `test_proxy.py`; the mutations are caught (2026-11-16) | 2026-11-16 | 2026-11-16 |
| BUG-0053 | The P2.03 tests passed with 14 broken rules (a mutation run on a copy: 15 of 23 mutants survived, one is equivalent): `+faststart`, `-an`, `-pix_fmt`, `-g`, `-crf`, the source/proxy hashes, `n_frames_source` and `args` in `proxy.json`, an ignored ffmpeg failure, the temporary-file cleanup, **AC2 (a failed check keeps and marks the proxy) has no test**, and `ingest` with `proxy=True` on an already ingested file | S3 | CLOSED | P2.03 mutation check, `taiji_ai/tests/contract/test_proxy.py`, `tests/contract/test_cli_ingest.py` | P2.03 | T-IO-23..27 in `test_proxy.py` and `test_cli_ingest.py`; mutation run 41 of 41 caught (2026-11-16) | 2026-11-16 | 2026-11-16 |
| BUG-0052 | `scan_pts_ticks` counts packets that are never shown: a clip trimmed on a phone (stream copy that starts between two keyframes, so the file has an edit list) gives `pts.parquet` and `n_frames` with 6 extra rows that have negative times, so row *i* is no longer decoded frame *i* (every timestamp is 0.2 s early in the probe) and the proxy check fails (105 source frames, 99 proxy frames) | S1 | CLOSED | P2.03 review (probe P1), `taiji_ai/src/taiji_ai/io/frames.py` (`scan_pts_ticks`, P2.02 code), `io/ingest.py` | P2.03 | `test_trimmed_clip.py` (T-IO-20..22: 16 cases, 6 red first); the mutation is caught (2026-11-16) | 2026-11-16 | 2026-11-16 |
| BUG-0051 | The first version of the P2.02 tests passed with 22 broken rules (a mutation run on a copy; 24 of 88 mutants survived in two runs: 22 test gaps, one dead check and one equivalent): the size and duration limits at their exact value and the two sources of the duration, an upper-case extension, the PyAV error branch, zero frames, a zero median interval, a path in the "not a regular file" message, the stored `start_pts` and the audio offset (no fixture started at a non-zero timestamp), the duplicate count, the container frame rates, the relative spread, the numbers of the VFR rule and the ffprobe version in the manifest, a zero median and a single interval in the VFR rule, the float rounding in `is_vfr`, the audio start in the probe, `--participant` optional; the self-review found two more (the row may only be inserted when the folder is complete; a video with one frame, which has no interval); `_parse_meta` also held a type check that `parse_manifest` already made | S3 | CLOSED | P2.02 mutation check and self-review, `taiji_ai/tests/contract/test_ingest.py`, `tests/unit/test_vfr.py`, `tests/contract/test_cli_ingest.py`, `taiji_ai/src/taiji_ai/io/ingest.py` | P2.02 | 21 test cases added (collected: 116 → 125 → 135 → 137 in the files of the task; `test_ingest.py`, `test_vfr.py`, `test_cli_ingest.py`) and the fixtures `offset_video` and `one_frame_video`; the dead check removed; mutation runs 89 of 90 caught, the survivor is `p.size > 0` in the older `scan_pts_ticks` filter (equivalent for every fixture) (2026-11-16) | 2026-11-16 | 2026-11-16 |
| BUG-0050 | `taiji participant show --id <text>` echoed the text typed by the user in its "not registered" message without checking that it is a pseudonym, so a name typed there would reach the terminal (and a log or screenshot); found in the P2.08 re-read of the first version; the first tests only used valid IDs | S3 | CLOSED | P2.08 self-review, `taiji_ai/src/taiji_ai/cli.py` (`show`) | P2.08 | `test_cli.py::test_t_data_05i_a_name_given_as_a_value_is_refused_and_never_echoed[show]`, `test_participants.py::test_t_data_05j_require_participant_*` (red first); mutation of the check caught (2026-11-16) | 2026-11-16 | 2026-11-16 |
| BUG-0049 | `Docs/TECH_WORKFLOW_V1.md` has 15 markdownlint warnings that were there before P2.01 and that the IDE showed when P2.01 edited the file (it had never been analysed): MD032 (nine lists without a blank line: W0, W1, W2, W5, §9, Appendix B), MD040 (two fenced blocks without a language: the folder tree in §4.1 and the block of §5.1), MD031 (the `run_manifest.json` fence), MD036 (three bold labels used as headings in Appendix B) | S3 | PLANNED | P2.01 edit of the workflow (IDE diagnostics), pre-existing | X.22 | IDE diagnostics for `TECH_WORKFLOW_V1.md` show no warning | 2026-11-15 | |
| BUG-0048 | The "full suite" test counts in the P1.04 and X.18 records are wrong: the P1.04 task file §5 and its CHANGELOG entry say 161 passed, the X.18 task file §5 and its CHANGELOG entry say 191 passed; the true totals were 305 and 335 (non-ontology files 246, plus the ontology and sheet tests of that day); I added up the dots of the last three progress lines only, a cut-off view of the output | S3 | CLOSED | P2.01 (a count taken from `pytest --collect-only`), `Docs/tasks/P1.04.md:198`, `Docs/tasks/X.18.md:167`, `Docs/tracking/CHANGELOG.md:65,84` | P2.01 | Each place now shows the old number struck through and the recomputed one; the current full run is 472 passed (2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0047 | The first version of the P2.01 sync tests matched only the field name in the error, so five rules could be removed and the tests still passed (found by a mutation run: 60 of 67 caught); one was a real gap, because `usable_for_metrics` was also accepted with the flash residual at one end only, against DEC-0025 (flash needed at both ends); the validator and a test said the opposite | S3 | CLOSED | P2.01 mutation check, `taiji_ai/src/taiji_ai/schemas/sync.py` and `taiji_ai/tests/unit/test_schemas_sync.py` | P2.01 | Cases now match the message of the right rule (`_EXPECT`); `usable` needs both ends; mutation run caught all but the two equivalent ones (2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0046 | `io.frames.is_vfr` flags a constant-frame-rate video as VFR when the time base is coarse: a 30 fps CFR clip with time base 1/1000 has frame intervals of 33 and 34 ms (rounding to the tick), std/median = 1.43 % > the 1 % tolerance, so `is_vfr` returns True; same for 29.97 fps | S3 (S2 once a stage acts on the flag) | CLOSED | Phase 2 planning experiment (2026-11-15), `taiji_ai/src/taiji_ai/io/frames.py` `is_vfr`, pre-existing since P0.03 | P2.02 | T-IO-12: `test_vfr.py` (26 tests), `test_video_io.py` and `test_ingest.py` (CFR 30 and 29.97 fps with `-video_track_timescale 1000` are not VFR; the real VFR fixture still is); every weakening of the rule is caught by the mutation run (2026-11-16) | 2026-11-15 | 2026-11-16 |
| BUG-0045 | `AGENTS.md` has two markdownlint MD040 warnings: the lifecycle diagram (line 40) and the changelog-entry example (line 177) are fenced blocks without a language; present before P1.06, shown by the IDE when P1.06 edited the file for BUG-0044 | S3 | CLOSED | P1.06 (IDE diagnostics after the BUG-0044 fix), `AGENTS.md:40,177`, pre-existing | P1.06 | IDE diagnostics for `AGENTS.md` show no warning after the fix (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0044 | The deletion task is cited as P8.12 in `AGENTS.md` §9.5 item 3, `Docs/tasks/P0.06.md` (two places) and `Docs/tasks/P1.06.md` (three places); the plan gives deletion of a participant's data to P8.14 (`tools/delete_participant.py`, T-STORE-07), and P8.12 is the report export | S3 | CLOSED | P1.06 analysis (2026-11-15), `AGENTS.md:357`, `Docs/tasks/P0.06.md:145,379`, `Docs/tasks/P1.06.md:26,48,79` | P1.06 | Manual check: `grep -rn "P8.12"` over `*.md` shows only export contexts after the fix (2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0043 | `taiji_ai/README.md` has a markdownlint MD040 warning: the fenced block of the Layout section (line 57) has no language; present before X.18, shown by the IDE when X.18 edited the file (the P1.04 check of this file returned an empty answer because the IDE had not analysed it) | S3 | CLOSED | X.18 edit of the README (IDE diagnostics), pre-existing | X.18 | IDE diagnostics for the README show no warning after the fix (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0042 | The first version of the X.18 `side_sequence` tests passed with the rule "every entry must be one of the action's sides" removed: every test case for it also broke the rule "every side must occur", which rejected it instead, so a mutation run left the rule alive | S3 | CLOSED | X.18 mutation check, `taiji_ai/tests/unit/test_ontology.py` (T-DATA-01i) | X.18 | Case `[left, right, up]` added (an unknown side while every declared side occurs); mutation run 45/45 caught (2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0041 | The first version of the P1.04 tests (T-DATA-01) passed with four rules broken: a mutation run left 4 of 26 mutations alive (strict integer `repetitions`, repeated declared sides passed for the wrong reason, repeated sides inside an action, the "mapping" message); the immutability test caught a bare `Exception`; no test for an unquoted YAML date in `confirmed_at` | S3 | CLOSED | P1.04 mutation check, `taiji_ai/tests/unit/test_ontology.py` | P1.04 | Mutation run on a copy of the module: 28/28 caught (2026-11-15); `test_ontology.py` 59 passed | 2026-11-15 | 2026-11-15 |
| BUG-0040 | The P1.02 note template `Docs/discovery/notes/_TEMPLATE.md` has two MD037 warnings: the blanks written as `___` on the line of question 2.4 are read as emphasis markers; my first verification said "lint ok" because the IDE had not analysed the new file yet | S3 | CLOSED | P1.02 (IDE diagnostics after the SIM-4 edit), `Docs/discovery/notes/_TEMPLATE.md:53` | P1.02 | IDE diagnostics for the template show no warning (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0039 | `datasets/taiji/README.md` has 3 markdownlint warnings in text older than X.16: the tree block has no language (MD040), the lists after "Thống kê" and "Giới hạn" have no blank line above (MD032) | S3 | CLOSED | X.16 edit of the README (IDE diagnostics), pre-existing | X.16 | IDE diagnostics for the README show no warning (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0038 | The simulated interview files in `Docs/discovery/` (three personas and a comparison): the personas are coded H1–H3, the codes of the real coaches (collision with P1.02 notes and the P1.08 roles); they sit next to the real guide with no separate folder; 29 markdownlint warnings (20 bare URLs, 6 bold-only labels, 3 double blank lines) | S3 | CLOSED | P1.01 review (2026-11-15), `Docs/discovery/P1.01_*_MO_PHONG.md` | P1.01 | Manual check: codes SIM-n, folder `simulated/`, IDE diagnostics empty (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0037 | The interview guide v0.1 (my draft) has four defects shown by the dry run: question (c) of part 6 asks for a "number" on cards that show none; part 6 has 12 questions in 10 minutes; question 1.4 is too big for part 1; the time table of Appendix B has 5 rows and one persona needs 6 | S3 | CLOSED | P1.01 review (2026-11-15), `Docs/discovery/interview_guide.md` | P1.01 | Re-run C-1..C-6 on v0.2 plus a read of the four changes (done 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0036 | `Docs/DATASET_REGISTRY_TAIJI.md` has 16 markdownlint warnings in the detail sections: each `###` heading is followed by a list without a blank line (MD022 and MD032, 7 sections) and two e-mail addresses are bare (MD034, line 42); present in HEAD | S3 | CLOSED | P1.10 edit of the registry (IDE diagnostics), pre-existing in HEAD | X.14 | IDE diagnostics for the registry show no warning (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0035 | New task files `X.10.md` and `X.11.md` have markdownlint warnings: X.10 line 19 starts with a plus sign (read as a list item: MD032, and MD004 on its 18 dash lists), X.11 has five bold-only labels (MD036); written by this agent and not checked with the IDE problems list | S3 | CLOSED | X.11 verification (`getDiagnostics`), `Docs/tasks/X.10.md:19`, `Docs/tasks/X.11.md` | X.11 | IDE diagnostics for both files show no warning (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0034 | `Docs/tasks/P0.07.md` has a markdownlint MD022 warning: the heading "### Rework evidence" (line 338) has no blank line above it; in HEAD since the P0.07 rework commit `84c9bff` | S3 | CLOSED | X.11 check of the IDE problems list, pre-existing in HEAD | X.11 | IDE diagnostics for `Docs/tasks/P0.07.md` show no MD022 (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0033 | `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3 has a markdownlint MD032 warning (the list of the three F-SYN functions starts right after its paragraph, no blank line; about line 409); present in HEAD | S3 | CLOSED | X.10 edit of the plan (IDE diagnostics), pre-existing in HEAD | X.11 | IDE diagnostics for `Docs/IMPLEMENTATION_PLAN_V1.md` show no MD032 (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0032 | `Docs/tasks/P0.06.md` §5 has two markdownlint MD031 warnings (fenced code blocks without blank lines around them, "Step 9" evidence, about lines 437–452); present since the P0.06 commit | S3 | CLOSED | X.07 edit of P0.06.md (IDE diagnostics), pre-existing in HEAD | X.11 | IDE diagnostics for `Docs/tasks/P0.06.md` show no MD031 (checked 2026-11-15) | 2026-11-15 | 2026-11-15 |
| BUG-0031 | Task-file leftovers: BUG-0009 detail section is stale (Status FIXED, describes the first incomplete fix) and P0.06 §2.5 AC1–AC11 boxes are unticked while §8 says met | S3 | CLOSED | P0 review (2026-11-15), `Docs/tracking/BUGS.md` BUG-0009 detail, `Docs/tasks/P0.06.md` §2.5 | X.07 | Manual check list (BUG-0031 fix plan); `pytest -k bug_0009` (7 passed) | 2026-11-15 | 2026-11-15 |
| BUG-0030 | Docs say the P0.06/P0.07 commits are "local, not pushed" on branch `feat/P0.07-synthetic-skeleton`; they are in `main` and pushed (`origin/main` = `22d3078`) | S3 | CLOSED | P0 review (2026-11-15), `Docs/tracking/CHANGELOG.md:40,52`, `Docs/tracking/TASK_STATUS.md` P0.06/P0.07 rows, `Docs/tasks/P0.07.md` §8 | X.07 | Manual check list (BUG-0030 fix plan): `grep "not pushed"`, `git merge-base --is-ancestor` | 2026-11-15 | 2026-11-15 |
| BUG-0029 | SYN-12 `absent_s` that contains no frame raises `IndexError` instead of `ValueError` naming the parameter | S3 | CLOSED | P0.07 rework self-review, `taiji_ai/tests/helpers/synth.py` `build_syn_12` | P0.07 | `tests/unit/test_synth.py::test_t_syn_04_invalid_values_pair_and_scene[…absent_s…]` (red first; MN21) | 2026-11-15 | 2026-11-15 |
| BUG-0028 | SYN-07 accepts `fps` (inherited from the common defaults) and ignores it; the rework of BUG-0020 left one accepted-but-unused parameter | S3 | CLOSED | P0.07 rework self-review, `taiji_ai/tests/helpers/synth.py` registry | P0.07 | `tests/unit/test_synth.py::test_t_syn_04_every_accepted_parameter_changes_the_output[SYN-01..12]` + `…unknown_parameter…` (SYN-07 case red first; MN22) | 2026-11-15 | 2026-11-15 |
| BUG-0027 | P0.07 task file and TASK_STATUS overwritten with the pre-review versions at 18:00:11 (review §9 and the BUG-0019 note lost, P0.07 shown DONE again); a second writer is still active | S3 | CLOSED | P0.07 rework, `Docs/tasks/P0.07.md`, `Docs/tracking/TASK_STATUS.md` (mtime 2026-11-15 18:00:11-15) | P0.07 | Manual check list (P0.07 §9 present, TASK_STATUS rows) done 2026-11-15 | 2026-11-15 | 2026-11-15 |
| BUG-0026 | P0.07 docs and evidence overstate the work: SYN-07 "exact speeds", SYN-09 "pinhole / Appendix B", "TypeError raised", "10 L/R pairs", tolerance-change rule deleted, unverified maintainer confirmation | S3 | CLOSED | P0.07 review, `Docs/tasks/P0.07.md`, `IMPLEMENTATION_PLAN_V1.md` §14.3 | P0.07 | Manual check list (plan §14.3, DEC-0013, task file) done 2026-11-15 | 2026-11-15 | 2026-11-15 |
| BUG-0025 | SYN-06 gaps: default short gap lies inside a pause; gap past the clip end accepted as "short"; a gap hitting no frame silently dropped; 150 ms hard-coded | S3 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:245-318, 771-780` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn06_*` and `…invalid_values_name_the_parameter[SYN-06…]` (MN11, MN12, MS5) | 2026-11-15 | 2026-11-15 |
| BUG-0024 | SYN-12: detections never shuffled (slot = identity), seed ignored, `crossing_interval` (1.8–2.2 s) falls while the target is absent | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:1055-1128` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn12_*` (MS4, MN9, MN10, MN18) | 2026-11-15 | 2026-11-15 |
| BUG-0023 | SYN-10 query is not the reference re-timed: phase uses `t_ref/duration` vs `t/t_sec[-1]`, up to 4.4 px apart | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:977-995` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn10_*` (MS2, MN7, MN8) | 2026-11-15 | 2026-11-15 |
| BUG-0022 | SYN-09 truth wrong: `expected_hA` in px, not `y_H/Λ_take`; `range_A` (px) compared with `range_B` (Λ); feet fixed, not a pinhole model; with Appendix B formulas B is less stable than A | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:895-967` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn09_pinhole_truth_follows_appendix_b[0.6, 1.0, 1.3]` (MS3, MN5, MN6) | 2026-11-15 | 2026-11-15 |
| BUG-0021 | Tempo truth is not from a continuous model: SYN-05 speed = `np.gradient` of the sampled poses (the metric's own method, non-zero inside pauses, mean not median); SYN-07 has no speed truth | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:359-409, 728-738, 806-843` | P0.07 | `tests/unit/test_synth.py::test_t_syn_02_syn05_*`, `…syn07_vfr_truth`, `…group_speed_is_the_median…` (MS1, MN2–MN4) | 2026-11-15 | 2026-11-15 |
| BUG-0020 | `make_sequence` / `make_pair` / `make_scene` silently ignore unknown or misspelled parameters (defaults used) | S2 | CLOSED | P0.07 review, `taiji_ai/tests/helpers/synth.py:1230-1272` | P0.07 | `tests/unit/test_synth.py::test_t_syn_04_unknown_parameter_is_rejected_by_every_api` (MN1) | 2026-11-15 | 2026-11-15 |
| BUG-0019 | P0.06 commit `4cee272` ships the stale 21-test `test_logs.py`; BUG-0018 was "fixed" by changing `posix_paths` to `True` so the stale tests pass (Windows request lines like `GET /home/settings` redacted again) | S2 | CLOSED | P0.07 review, commit `4cee272`, `taiji_ai/src/taiji_ai/logs.py:125,139,174` | P0.06 follow-up | `tests/unit/test_logs.py::test_t_core_01e_posix_syntax_default_follows_the_platform` + the restored 41-test file (red first; M1–M9) | 2026-11-15 | 2026-11-15 |
| BUG-0018 | `tests/unit/test_logs.py` overwritten again after P0.06 closed (41 → 21 tests, gate red); a second writer is editing the repo | S2 | CLOSED | P0.07 analysis, file mtime 2026-11-15 16:55:35 | P0.06 follow-up | `posix_paths: bool = True` in `logs.py`, ruff format; full gate 10/10 PASS | 2026-11-15 | 2026-11-15 |
| BUG-0017 | `run_log` writes no end marker when a run is cancelled (`KeyboardInterrupt`, `SystemExit`)                                 | S3  | CLOSED | P0.06 review, `taiji_ai/src/taiji_ai/logs.py:259`                         | P0.06    | `tests/unit/test_logs.py::test_t_core_01i_run_log_exception_closes_handler[exc0..2]` (2 red first; M7) | 2026-11-15 | 2026-11-15 |
| BUG-0016 | API logging tests leave root-logger and uvicorn-logger state behind for the rest of the pytest session                    | S3  | CLOSED | P0.06 review, `taiji_ai/tests/api/test_api_core.py` (T-CORE-01o/p, T-API-04b) | P0.06 | `tests/conftest.py::_logging_state_guard` (autouse; 3 errors red first; M8)          | 2026-11-15 | 2026-11-15 |
| BUG-0015 | `PathRedactor` drops known-root tails in `repr` form (`'<data><path>'`) and redacts non-paths (`/homepage`, `/users`, `/media/x`) | S3 | CLOSED | P0.06 review, `taiji_ai/src/taiji_ai/logs.py:76-85,126-129`            | P0.06    | `test_logs.py::test_t_core_01b_known_roots_keep_tail_in_repr_form`, `…01b_tail_of_known_root_does_not_hide_a_second_path`, `…01e_not_paths_left_unchanged` (M9)                       | 2026-11-15 | 2026-11-15 |
| BUG-0014 | `PathRedactor` leaves the name visible in UNC paths (share with space / non-ASCII / `c$`, non-ASCII server) and after an apostrophe | S2 | CLOSED | P0.06 review, `taiji_ai/src/taiji_ai/logs.py:75-79`                   | P0.06    | `test_logs.py::test_t_core_01a_*` (12 + 4 + 3 + 3 cases; 10 red first; M5a, M5b)                         | 2026-11-15 | 2026-11-15 |
| BUG-0013 | Tracking docs overwritten with stale copies: CHANGELOG lost the 2026-11-15 P0.05 entry; BUGS.md next free ID reset to `BUG-0010`; BUG-0008 detail reverted | S3 | CLOSED | P0.06 review, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/BUGS.md` | P0.06 | Manual check (fix plan item 4) done 2026-11-15; restores verbatim from the session transcript                                 | 2026-11-15 | 2026-11-15 |
| BUG-0012 | P0.05 rework-2 test files overwritten with older versions: BUG-0008 / BUG-0010 regression tests deleted, T-TOOL-05 commits again | S2 | CLOSED | P0.06 review, `taiji_ai/tests/contract/test_check_script.py`, `test_repo_hygiene_git.py` | P0.06 | `tests/contract/test_check_script.py` (9 tests, restored) incl. `test_bug_0010_*` and `test_t_tool_01_parse_check_detects_syntax_errors`            | 2026-11-15 | 2026-11-15 |
| BUG-0011 | `/api/health` returns (and logs) the absolute model-registry path; the user-profile folder name shows on the Status page    | S3  | CLOSED | P0.06 analysis, `taiji_ai/src/taiji_ai/api/app.py:32-33`                  | P0.06    | `tests/api/test_api_core.py::test_bug_0011_*` (red first, mutation-checked) | 2026-11-15 | 2026-11-15 |
| BUG-0010 | T-TOOL-03 tests the nested-run guard with a real gate run; a broken guard makes the gate recurse without bound              | S3  | CLOSED | P0.05 re-review, `taiji_ai/tests/contract/test_check_script.py:147-150` | P0.05    | `tests/contract/test_check_script.py::test_bug_0010_nested_guard_is_checked_before_preflight` (mutation-checked) | 2026-11-15 | 2026-11-15 |
| BUG-0009 | `repo_hygiene.py` silently sets `size = None` on OSError, masking unreadable files                                         | S3  | CLOSED | P0.05 rework analysis, `taiji_ai/tools/repo_hygiene.py:189-194`            | P0.05    | `tests/unit/test_repo_hygiene.py::test_bug_0009_*` (7 tests, 4 red before the fix) | 2026-11-14 | 2026-11-15 |
| BUG-0008 | `test_t_tool_01_check_script_parses_cleanly_in_powershell` passes `[ref]$null`, silently ignoring syntax errors            | S2  | CLOSED | P0.05 rework analysis, `taiji_ai/tests/contract/test_check_script.py:34-45` | P0.05    | `tests/contract/test_check_script.py::test_t_tool_01_parse_check_detects_syntax_errors` (negative control, mutation-checked) | 2026-11-14 | 2026-11-15 |
| BUG-0007 | `taiji_ai/README.md` Status says "Vitest 9"; the suite has 11 tests                                                        | S3  | CLOSED      | P0.05 analysis of `taiji_ai/README.md` Status table                        | P0.05    | Manual check: README Status rows carry no hard-coded test counts | 2026-11-14 | 2026-11-14 |
| BUG-0006 | `atomic_save_npz` silently drops an array named `allow_pickle`; object arrays are pickled into files `np.load` cannot read | S3  | CLOSED | P0.05 analysis (`mypy src`), `taiji_ai/src/taiji_ai/store/artifacts.py:51` | P0.05    | `tests/unit/test_core.py::test_bug_0006_*`                       | 2026-11-14 | 2026-11-14 |
| BUG-0005 | `apiGet` drops `Headers`-object headers and reports aborted requests as `network_error`                                    | S3  | CLOSED | P8.02 self-review of `taiji_ai/web/src/api/client.ts`                      | P8.02    | `tests/client.test.ts` (headers + abort cases)                   | 2026-11-14 | 2026-11-14 |
| BUG-0004 | `Settings.device` reads `TAIJI_DEVICE` at import time, not at construction                                                 | S3  | CLOSED | P8.01 analysis of `taiji_ai/src/taiji_ai/config.py:21`                     | P8.01    | New unit test: env set after import is honoured                  | 2026-11-14 | 2026-11-14 |
| BUG-0003 | New `.markdownlint.jsonc` re-enabled MD013 (line length) warnings                                                          | S3  | CLOSED | X.04 (introduced by step 0)                                                | X.04     | IDE diagnostics after a doc edit show no MD013                   | 2026-11-14 | 2026-11-14 |
| BUG-0002 | TECH_WORKFLOW stack table still says "Python 3.11 hoặc 3.12" after DEC-0002                                                | S3  | CLOSED | X.04 self-review of `Docs/TECH_WORKFLOW_V1.md` §1.1                        | X.04     | Manual check: row matches DEC-0002                               | 2026-11-14 | 2026-11-14 |
| BUG-0001 | Dataset registry header says no dataset downloaded (stale)                                                                 | S3  | CLOSED | X.03 review of `Docs/DATASET_REGISTRY_TAIJI.md:3`                          | X.03     | Manual check: header matches "Trạng thái" column                 | 2026-11-13 | 2026-11-14 |

---

## Details

### BUG-0074 — The D20 allowed use does not name the look at the mask layer (P4.01)

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (a record, no data was copied or committed; the maintainer had approved the plan of P4.01 with M-QLT-01 in it) |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/DATASET_REGISTRY_TAIJI.md`, the D20 row, allowed use (written for P3.07, P3.08 and P3.09 only) |
| Found by / date | agent (Claude Code), 2026-11-17, checking the row before adding M-QLT-02 to P4.02            |

**Description:** M-QLT-01 (P4.01, 2026-11-16) applied the mask to the target tracks of the D20 pose pass and reported counts; the D20 row lists the uses that are allowed and does not list it. AGENTS.md 9.4 item 3 says each dataset is tagged with what it may be used for and another use needs a registry update.
**Steps to reproduce:** read the D20 row: P3.07, P3.08, P3.09 and the technical smoke tests are named; the mask check is not.
**Expected:** the row names every use made of D20. **Actual:** two uses missing (P4.01 and, now, P4.02). **Root cause:** the registry was not re-read when the plan of P4.01 added a look at real footage.
**Fix plan:** add to the row "the mask layer and the gap layer (P4.01 M-QLT-01, P4.02 M-QLT-02): counts of holes and errors of a bridge computed on the existing pose files of P3.08, numbers and labels only, no image and no pose file in git (DEC-0040, DEC-0045)". Regression: none possible (a record); the check is manual.
**Fix task / commit:** P4.02 (this task), not committed. **Regression test:** manual check. **Verified:** agent, 2026-11-17: the row reads the two uses with their limits.

**History:**

- 2026-11-17 OPEN → PLANNED → FIXED → VERIFIED → CLOSED — found and fixed in P4.02.

### BUG-0073 — The detector tool keeps a stale NMS default (0.45) after the shipping limit was read as 0.65

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (found before the task closed; the final run passed `--nms-iou 0.65` explicitly, so no number of the report is affected) |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/tools/detector_compare.py` (`--nms-iou` default and help text), `taiji_ai/src/taiji_ai/bench/detector_metrics.py` (`DetectorRule.matched_nms_iou`), `tests/unit/test_detector_rule.py` (P3.09) |
| Found by / date | agent (Claude Code), 2026-11-17, read-back of the changed files in the self-review of P3.09 |

**Description:** after the first run, the NonMaxSuppression node of the shipping graph was read: its IoU limit is 0.65, not the 0.45 of the plan (DEC-0043 was corrected, the final run used 0.65). The code kept the old value in three places: the default of `--nms-iou` ("YOLOX uses 0.45" in its help), the field `DetectorRule.matched_nms_iou` (not used by `decide`, so a dead field with a wrong value) and the unit test that pins that value.
**Steps to reproduce:** `python tools/detector_compare.py run --video-dir ... --yolo11 ...` without `--nms-iou` → `detector.json` `settings.nms_iou` is 0.45.
**Expected:** the default is the limit of the shipping graph (0.65), from one place that the rule and the tool share. **Actual:** 0.45 in the tool, 0.45 in the rule. **Root cause:** the correction was made in the records and in the command line of the final run, not in the defaults.
**Fix plan:** `DetectorRule.matched_nms_iou = 0.65` with a comment on where the number comes from; the tool builds its parser in `build_parser()` and takes the default of `--nms-iou` from `DetectorRule().matched_nms_iou`, with a help text that states the source; the unit test pins 0.65; a contract test checks that the parser default equals the rule's value and 0.65 (it fails on the old code).
**Fix task / commit:** P3.09 (this task), not committed. **Regression test:** `test_t_det_08_the_default_nms_limit_of_the_tool_is_the_one_of_the_shipping_graph`. **Verified:** agent, 2026-11-17: the test fails on the old value (0.45 against 0.65, after `build_parser` was split out so that it fails for the right reason) and passes after the fix; the mutant "default back to 0.45" is killed; the fixed lines were read again (the rule's field and its comment, the tool's `default=DetectorRule().matched_nms_iou`); gate 10/10 on the closing tree.

**History:**

- 2026-11-17 OPEN → PLANNED → IN_PROGRESS — found in the read-back; fixed in P3.09 before the close.
- 2026-11-17 IN_PROGRESS → FIXED → VERIFIED → CLOSED — regression test red then green, mutant killed, gate 10/10.

### BUG-0072 — `prepare_onnxruntime` ignores a CUDA request that comes after a CPU one

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (latent: the product always asks for the same device in one process; found by a tool that read a model file on the CPU and then built a CUDA session) |
| Status          | PLANNED                                                                                    |
| Found in        | `taiji_ai/src/taiji_ai/pose/rtm.py` `prepare_onnxruntime` (P3.02); found while writing P3.09 |
| Found by / date | agent (Claude Code), 2026-11-17, the first script of the detector comparison               |

**Description:** `prepare_onnxruntime(device)` sets the module flag `_ORT_READY` on its first call whatever the device, and returns at once on every later call. `ort.preload_dlls()`, which makes the CUDA provider find the DLLs shipped by the `nvidia-*` pip packages, is called only when the **first** call is for `"cuda"`.
**Steps to reproduce:** in a fresh process: `prepare_onnxruntime("cpu")`, then `prepare_onnxruntime("cuda")`, then `onnxruntime.InferenceSession(<any model>, providers=["CUDAExecutionProvider"])` → `Error loading ...onnxruntime_providers_cuda.dll which depends on "cublasLt64_13.dll" which is missing` and the session uses the CPU (reproduced 2026-11-17 with the exported detector of P3.09).
**Expected:** the DLLs are preloaded whenever CUDA is asked for, once. **Actual:** only if CUDA was the first device asked for. **Root cause:** one boolean for two different preparations.
**Fix plan:** keep a set of the devices already prepared (or two flags); `prepare_onnxruntime("cuda")` preloads once even after a call for `"cpu"`; the logger severity is set once. Regression test: a subprocess (the DLL search path is per process) that calls the CPU first and then builds a CUDA session on the registry's detector and asserts the provider (`gpu` marker). P3.09 does not touch `rtm.py` (its acceptance says so) and works around it in `bench/yolo_onnx.py`; the fix is the ad-hoc task X.30 (about 0.25 day).
**Fix task / commit:** X.30, not yet. **Regression test:** to be written with the fix. **Verified:** —

**History:**

- 2026-11-17 OPEN → PLANNED — found in P3.09; fix scheduled as X.30; the task's own code does not depend on it.

### BUG-0071 — An unknown tracked-share loss was passed to the rule for N as zero

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (found before the task closed; the five real clips all have a target, so no result was affected) |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/bench/orchestrate.py` `run_benchmark` and `bench/decision.py` `NStats` (P3.07, first version) |
| Found by / date | agent (Claude Code), 2026-11-16, read-back of the orchestrator while the first gate was running |

**Description:** `_effect` returns `None` for the loss of the tracked share when no clip has a target in both runs, and `run_benchmark` replaced it with `0.0` (`0.0 if loss is None else loss`) before the rule: a measurement that does not exist became "no loss" (AGENTS.md 5.1, no made-up numbers).
**Steps to reproduce:** `NStats(..., tracked_loss_points=None)` was not allowed by the type; the orchestrator turned the `None` into 0.0 and the criterion passed.
**Expected:** the criterion cannot be decided, so N is not acceptable and the reason says so. **Root cause:** a convenience default in the orchestrator.
**Fix:** `NStats.tracked_loss_points` is `float | None`; the rule gives the reason "the tracked share of the target could not be compared (no clip has a target in both runs)"; the orchestrator passes the value as it is. Regression test `test_t_bench_06_an_unknown_tracked_share_is_not_acceptable_and_is_not_taken_as_zero`.
**Verified:** agent, 2026-11-16 — the test fails with a `TypeError` on the old comparison and passes after the fix; gate in the close-out of P3.07.

**History:**

- 2026-11-16 OPEN → FIXED → VERIFIED → CLOSED — found and fixed in P3.07 before the task closed.

### BUG-0070 — The keypoint term of the association was normalised by the wrong height

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (found before the task closed; no clip showed it: the real clips have all keypoints valid)      |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/track/associate.py` `_pair_cost` (P3.05, first version)             |
| Found by / date | agent (Claude Code), 2026-11-16, read-back of the whole file after the gate and the mutation run |

**Description:** the plan and the module docstring say the keypoint distance is divided by the height of the track's hull. The code took `hull_t`, which is replaced by the hull of the keypoints valid in both frames when at least four are common, so with few common
keypoints (two rows of the body, 140 px against 700 px) the height was too small and the cost too large.
**Steps to reproduce:** a track of 300 x 700 px and a person that shows only the top two rows of the body, moved by 20 px: cost 0.134 (expected 0.077).
**Expected:** 0.077 (the common hull has the IoU of the full box, the distance is 20 / 700). **Root cause:** `height = hull_t[3] - hull_t[1]` after `hull_t` had been reassigned.
**Fix:** `height = track.hull[3] - track.hull[1]` (the whole body of the track); regression test `test_t_trk_03e_the_keypoint_distance_is_divided_by_the_height_of_the_whole_track_not_of_the_common_keypoints`, and the mutant "height of the common hull" is caught.
**Verified:** agent, 2026-11-16 — the new test failed before the fix (cost 0.134) and passes; mutation 25 of 25; gate 10/10 PASS (178.3 s, 1198 tests).

**History:**

- 2026-11-16 OPEN → FIXED → VERIFIED → CLOSED — found and fixed in P3.05 before the task closed.

### BUG-0069 — `atomic_write_bytes` leaves a `.tmp` file after a failure

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3                                                                                         |
| Status          | CLOSED                                                                                      |
| Found in        | `taiji_ai/src/taiji_ai/store/artifacts.py` `atomic_write_bytes` (used by every artifact writer) |
| Found by / date | agent (Claude Code), 2026-11-16, reading the helper while planning the atomic-write test of P3.03 |
| Affects         | any failed write: disk full, a failing `os.replace` (file in use on Windows)               |

**Description:** the function writes `<name>.tmp`, fsyncs and calls `os.replace`; there is no cleanup, so when the write or the replace raises, the `.tmp` stays in the folder. The old file is intact (the guarantee that matters holds), but a re-run finds
a stale `.tmp`, and the run folder is littered. The function also creates missing parent folders (`mkdir(parents=True)`), so a wrong path silently creates a new tree; some callers rely on it (ingest), so it stays and the P3.03 writer checks the folder itself.

**Steps to reproduce:** monkeypatch `os.replace` to raise in `store.artifacts`, call `atomic_write_bytes(path, b"x")`: the exception is raised and `path.with_name(path.name + ".tmp")` exists.
**Expected:** the exception is raised, the old file is intact, no `.tmp` remains. **Actual:** the `.tmp` remains.

**Fix plan:** wrap the write and the replace in `try/except BaseException`: remove the `.tmp` (ignore a failure to remove, log it) and re-raise; keep the parent-folder creation. Regression test `T-ART-01` (replace fails, write fails, old content kept, no `.tmp`).
**Fix:** task P3.03, 2026-11-16 — `atomic_write_bytes` removes its `.tmp` (and logs, without a file name, if the removal fails) and re-raises on any failure of the write or of `os.replace`; the parent-folder creation stays.
**Verified:** agent, 2026-11-16 — T-ART-01: the two failure cases failed on the old helper and pass; the success case (parent folders created, file replaced, no `.tmp`) passes; the mutants 'tmp not removed' and 'failure not re-raised' are caught; gate 10/10 PASS (170.3 s, 1109 tests).

**History:**

- 2026-11-16 OPEN → PLANNED → IN_PROGRESS — found while planning P3.03; fixed in that task (small).
- 2026-11-16 IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P3.03.

### BUG-0068 — P2.05 tests and records do not show what they claim

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3                                                                                         |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/P2.05.md`, `taiji_ai/tests/contract/test_flash.py`, DEC-0032                    |
| Found by / date | agent (Claude Code), review of P2.05, 2026-11-16                                           |

**Description / evidence:** mutation run on copies of `src` (14 mutants of `flash.py`). With `test_flash.py` alone 4 are caught (onset one frame early, `min_step` 0.1,
residual in seconds, `min` instead of `max` of the two ends) and 10 survive; with all flash and sync tests of today (X.23, X.24) 5 are caught and 9 survive:
drift ignored in the mapping, `t_ref_s` ignored, camera swap removed, slower camera replaced by the faster, search margin 0, `k_mad` 0, refractory removed, and two
that are equivalent (the backward seek is an optimisation: the frames before `t0` are skipped anyway; the `status` check repeats the `offset_s` and `drift` checks). The
records: plan step 4 says "run mutation checks" and no result is recorded; §7 says "None found during this task" (BUG-0064 was in it); §6 lists "empty input, single flash"
as edge cases but no test has them; LaTeX in the task file and in DEC-0032; "722 passed, 44.4 s" is a count of a moving tree; DEC-0032 item (3) (closest onset) is replaced by DEC-0034.

**Fix plan:** tests (all on encoded fixtures, red first on the mutant): a take with a drift of ±300 ppm whose start and end flashes are only mapped right if `drift` and `t_ref_s` are used;
the two folders given in the opposite order; cameras of 30 and 60 fps (residual in frames of the slower); a flash in B that lies beyond the margin; a noisy window (adaptive threshold);
a two-step onset (refractory); an empty window; a clip longer than the 30 s window (a flash outside the window is not seen). Records: strike through the false statements in the task file,
record the mutation result, replace LaTeX, mark DEC-0032 (3) as replaced by DEC-0034.
**Fix:** P2.05 rework (task file §10), 2026-11-16 — T-SYNC-04g..n (drift and `t_ref_s`, folder order, slower camera, search margin, window of a long clip, noisy window, two-frame onset, refusals); the false statements of §4-§8 of the task file are struck through, LaTeX replaced, DEC-0032 item (3) marked as replaced by DEC-0034; the mutation result is recorded.
**Verified:** agent, 2026-11-16 — mutation on copies of `src`: 17 mutants of `flash.py`, 15 caught, 2 alive and equivalent (backward seek; `status` check), before: 4 of 14 caught by `test_flash.py` alone; gate 10/10 PASS (159.8 s, 958 tests).

**History:**

- 2026-11-16 OPEN → PLANNED — found by the review of P2.05; scheduled with the rework after the maintainer's approval.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — approved by the maintainer; fixed and verified in the P2.05 rework.

### BUG-0067 — `io/flash.py` has dead arguments, a made-up frame interval and no check of the recording pair

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3                                                                                         |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/io/flash.py` (`validate_sync`, `brightness_series`)                  |
| Found by / date | agent (Claude Code), review of P2.05, 2026-11-16                                           |

**Description:** (1) `validate_sync(..., settings=None)` and `brightness_series(..., rotation_deg=0)` never use these arguments (the same kind as BUG-0061); (2) `man.median_dt_s or (1.0 / 30.0)`
invents 30 fps when the manifest has no interval (only a one-frame video; the residual in frames would use a number nobody measured, AGENTS.md §5.1); (3) the function never compares
`audio_sync.recording_id_a/b` or the take with the two folders it is given, so the validation of another pair, or of an old audio result against new files, runs silently and can give a
usable result for a mapping that belongs to something else.

**Fix plan:** remove the two dead arguments (update `sync_take.py` and the tests that pass `settings=`); raise `FlashError` when `median_dt_s` is `None`; raise `FlashError` when the recording ids
of the folders are not those of the audio result (after the camera sort); tests: other take, swapped but right folders (still works), one-frame video.
**Fix:** P2.05 rework (task file §10), 2026-11-16 — no `settings` argument of `validate_sync`, no `rotation_deg` of `brightness_series`; `FlashError` for recordings that are not those of the audio result (checked after the camera sort, before the status check), for a manifest without `median_dt_s` (no 1/30 s), and a missing `t_ref_s` gives `method = none` (no 0.0).
**Verified:** agent, 2026-11-16 — T-SYNC-04n: the two refusals failed on the old code (no error was raised); the `t_ref_s` case; mutants 'recording pair not checked', 'missing frame interval not refused' and 'missing t_ref not refused' are caught; callers updated; gate 10/10 PASS (159.8 s, 958 tests).

**History:**

- 2026-11-16 OPEN → PLANNED — found by the review of P2.05.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — approved by the maintainer; fixed and verified in the P2.05 rework.

### BUG-0066 — The flash detector misses weak flashes and is a frame late on split flashes

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S2 (wrong abstain: a real flash is not seen and the take is refused; a one frame timing jitter against a limit of one frame) |
| Status          | PLANNED                                                                                    |
| Found in        | `taiji_ai/src/taiji_ai/io/flash.py` `find_flash_onsets`, `brightness_series`; DEC-0032      |
| Found by / date | agent (Claude Code), review of P2.05, 2026-11-16, probe on synthetic data                  |
| Affects         | `validate_sync`: windows are `flash_not_found`, so takes are not usable for metrics         |

**Description / evidence (probe, scratch script):**

| Lit area of a 640x360 frame (white box, encoded, grey scene with noise) | 50 % | 20 % | 10 % | 5 % | 2 % |
| --- | --- | --- | --- | --- | --- |
| largest step of the frame-mean luma | 80.3 | 32.0 | 16.4 | 8.0 | 3.3 |
| onset found at frame 45 (true) | yes | yes | yes | **no** | **no** |

A lamp held at the chest in a wide frame can light far less than 10 % of the image. Split onsets (frame 45 holds a share of the step): step 40 with 0.3 in frame 45 is reported at frame 46
(one frame late); step 25 with 0.5 is not found; step 18 with 0.3 is not found. A frame late on one camera and on time on the other is a residual of one frame on a perfect mapping, which is the
whole budget of the usability rule.

**Root cause:** the detector uses the mean luma of the whole frame, a fixed absolute step of 15 levels, and the first single frame difference above it as the onset. The values come from synthetic
full-frame flashes (DEC-0032); the plan's real-data check is P2.07.

**Fix plan (needs the maintainer's approval: it changes the algorithm, about 0.5 to 1 day):** (1) P2.07 rehearsal (Q1) first measures the real lamp in the real scene (area, step, how many frames it takes to
rise) with the current detector and reports the numbers; (2) block-wise detection: mean luma on a coarse grid (for example 16 x 9 blocks), a rise is flagged when a block (or a few neighbours) rises by more than
k times the noise of that block in the window, which does not depend on the lit area of the whole frame; (3) onset by the cumulative rise over two consecutive frames (the frame where the cumulative step crosses half
of the plateau, so a split onset gives the same frame on both cameras up to the sub-frame phase); (4) thresholds recorded with their reason in a DEC; (5) tests: lit area 2 to 50 % on encoded video,
split onsets at several phases, a perfect mapping gives a residual of at most half a frame whatever the phase; (6) the capture protocol says how large and how bright the lamp must be, from the P2.07 numbers.
**Fix:** —
**Verified:** —

**History:**

- 2026-11-16 OPEN → PLANNED — found by the review of P2.05; waits for the maintainer's decision and the P2.07 numbers.

### BUG-0065 — The sync database row is written for takes that are not usable and does not say so

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S2 (no code reads the row yet; S1 once P3, P5 or P8 reads it without `sync.json`: the row would carry a wrong time mapping and `validated_by = 'flash'`; the maintainer may raise it) |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/pipeline/sync_take.py` (writes the row when `status = ok`), `schemas/sync.py` `to_db_row`, migration 0001 table `sync` (no usable column), P2.06 |
| Found by / date | agent (Claude Code), 2026-11-16, probe while writing the end-to-end test of X.24           |
| Affects         | any reader of the `sync` table (P3, P5, P8 are expected to read the mapping)                |

**Description:** P2.01 Q4 and DEC-0025 item 7 say "a row only for `status = ok`". The table has `offset_s`, `drift`, `residual_ms`, `method`,
`validated_by` and no `usable_for_metrics`. `sync_take` writes the row for every `ok` take, including takes that the usability rule refuses
(`residual_too_large`, `flash_not_found`). `validated_by` is `'flash'` whenever the flash method ran, also when its residual failed.

**Steps to reproduce (probe, synthetic take with every flash seen, audio result forced +1.0 s wrong after the real audio sync):**
`sync_take("S01-P03-T01")` gives `sync.json` with `usable_for_metrics = false`, `usable_reason = residual_too_large`; `SELECT * FROM sync` returns
a row with `offset_s = 1.4999979` (true 0.5), `residual_ms = 999.998`, `validated_by = 'flash'`.

**Expected:** a reader of the database cannot take a mapping that the rule refused. **Actual:** the row looks like a validated mapping.

**Root cause:** the row was defined (P2.01 Q4) before the usability rule existed (P2.06); P2.06 kept the "row for `ok`" condition and did not add the usable condition.

**Fix plan (the maintainer chooses):** (A, recommended) write the row only when `usable_for_metrics` is true and delete it otherwise (as for `start_only` now):
a small change in `sync_take` (`if manifest.usable_for_metrics`), `sync.json` keeps the full result of unusable takes, DEC-0025 item 7 and P2.01 Q4 are amended,
T-SYNC-05c/05f updated (an `ok` but unusable take writes the file and no row). (B) keep the row and add `usable_for_metrics` and `usable_reason` columns with
migration 0002 (a schema change: every reader must then filter on it; more work and more ways to forget). Regression test T-SYNC-05f: after `sync_take` of
a take whose audio lag is wrong by 1 s there is no `sync` row (A) or the row says `usable_for_metrics = 0` (B).
**Fix:** task X.25, 2026-11-16 — option A chosen by the maintainer: `sync_take` writes the row only when `usable_for_metrics` and deletes the row otherwise; DEC-0035 amends DEC-0025 item 7 and P2.01 Q4; no migration.
**Verified:** agent, 2026-11-16 — T-SYNC-05f (4 tests; 3 failed on the old code); `test_sync_take.py`, `test_sync_rule.py` unchanged and passing; 2 mutants of the new condition caught (row for every ok take again, old row not deleted); gate 10/10 PASS (121.4 s, 945 tests).

**History:**

- 2026-11-16 OPEN → PLANNED — found by a probe in X.24; waits for the maintainer's choice between A and B.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — option A chosen by the maintainer (severity kept S2); fixed and verified in X.25.

### BUG-0064 — The flash check misses an audio lag wrong by one pair gap when a flash of a pair is not seen

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S1 (raised by the maintainer on 2026-11-16: two faults must coincide, BUG-0063 and a flash not seen, but the result is a wrong time mapping marked usable) |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/io/flash.py` (`validate_sync`, `match_residuals`), P2.05; `io/sync_rule.py` (P2.06) trusts its result |
| Found by / date | agent (Claude Code), 2026-11-16, probe on synthetic takes (scratch script, not in the repository) |
| Affects         | `sync.json.usable_for_metrics`, the `sync` row                                              |

**Description:** `match_residuals` takes each flash of camera A, predicts its place in B with the audio mapping, picks the closest flash of B
(within 1.5 s) and averages the distances. A flash of A without a partner is ignored, the number of flashes of the two cameras is not compared,
and one flash of B may serve two flashes of A. The flashes come in pairs 1 s apart, like the claps, so a mapping wrong by one pair gap
(BUG-0063) lands the first flash of A on the second flash of B at 0 ms; the pair is caught only because the second flash of A has no partner
and adds 1000 ms to the mean. If a flash of the pair is not seen on camera A (hidden, too weak, over exposure), nothing adds that 1000 ms.

**Steps to reproduce (probe on synthetic takes, 30 fps, flash pairs at 2.0/3.0 s and 12.0/13.0 s, B delayed by 0.5 s, audio offset given as
true + 1.0 s):**

| Case | Flashes seen A / B | Residual | `usable_for_metrics` |
| ---- | ------------------ | -------- | -------------------- |
| right offset | 4 / 4 | 0.0 ms | true |
| +1.0 s and -1.0 s | 4 / 4 | 500 ms (15 frames) | false (`residual_too_large`) |
| +1.0 s, A shows only the first flash of each pair | 2 / 4 | **0.0 ms** | **true** |
| -1.0 s, A shows only the second flash of each pair | 2 / 4 | **0.0 ms** | **true** |
| +1.0 s, B shows only the first flash of each pair | 4 / 2 | 1000 ms | false |

**Expected:** a time mapping wrong by one second is never usable. **Actual:** it is usable when A shows one flash per pair.

**Root cause:** the check matches by the closest flash and ignores the structure that makes the flashes identifiable (two flashes, the
gap between them).

**Fix plan:** (1) compare the pair structure in each window: A and B must show the same number of flashes, at least two, and the gap between
the two flashes of A must equal the gap between the two flashes of B within one frame of the slower camera; otherwise `flash_not_found`
(no new reason: the reason is logged); (2) match one to one (a flash of B serves one flash of A), an
unmatched flash of either camera makes the window `flash_not_found`; (3) the residual of a window is the largest matched distance, not the
mean (a mean can dilute one bad match); (4) regression tests: the five cases of the table above plus +1.0 s with the pair of the end window
only damaged; (5) the capture protocol (`Docs/capture_protocol.md`) must say that both flashes of each pair must be visible on both cameras
(the check of the coach/operator at the take). Where to fix: task X.23 (maintainer approved on 2026-11-16, including the code of P2.05); P2.06's rule needs no change.
**Fix:** task X.23, 2026-11-16 — `match_flashes` (one to one in time order, equal counts and at least two flashes, largest distance) replaces `match_residuals`; `FlashParams.min_flashes` = 2; no schema change, no new reason (`flash_not_found`); DEC-0034; the capture protocol asks for both flashes of each signal on both cameras. Difference from the plan: the pair gap is not a second number, the per-flash residual covers it (task file §3).
**Verified:** agent, 2026-11-16 — the 10 cases of T-SYNC-04f pass (7 of them failed on the old code: the old code gave `usable = true` when A showed one flash per pair, also with the right offset, and when each camera hid a different flash); T-SYNC-04e (15 tests, ImportError before); `test_flash.py`, `test_sync_take.py`, `test_sync_rule.py` unchanged and passing; 8 mutants of `match_flashes` caught (count check removed, `min_flashes` 1 in two places and not passed on, mean instead of max, no sorting (needed a stronger test), mapping not applied, residual in seconds); gate 10/10 PASS (179.9 s, 937 tests). Not claimed: real recordings (P2.07), and the audio part of BUG-0063 (consistent damage at both ends) is still open.

**History:**

- 2026-11-16 OPEN → PLANNED — found while planning the fix of BUG-0063; the probe is reproducible with `tests/contract/test_flash.py` helpers.
- 2026-11-16 PLANNED → IN_PROGRESS — severity raised S2 → S1 and the fix approved by the maintainer; task X.23 opened.
- 2026-11-16 IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in X.23.

### BUG-0063 — Known limits of the audio match that sound alone cannot remove

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S2 (a documented limit of the method, mitigated by the flash check; the maintainer may raise it to S1, then P2.04 cannot close) |
| Status          | PLANNED                                                                                    |
| Found in        | `taiji_ai/src/taiji_ai/io/audio_sync.py`, found by the adversarial pass of the P2.04 rework |
| Found by / date | agent (Claude Code), 2026-11-16, seven attack lenses, about 1100 probe cases, independent verifiers |
| Affects         | `status = ok` from sound alone: it is not proof of a right offset                          |

**Description:**

1. *Consistent damage.* One camera hears only one clap of the pair (or the claps with unequal amplitudes, or a louder tap of the
   phone at the start and stop) at **both** ends: both windows match the wrong clap, so both lags are wrong by one pair gap
   and agree with each other (drift 0). Nothing in the sound tells the claps apart. Damage at **one** end only is caught by the
   drift limit (500 ppm cross-check) for takes up to 2000 s (1 s error) or 600 s (0.3 s error).
2. *Short takes.* A take under 60 s uses windows of 45 % of the take: a start difference larger than the window abstains
   (not found), a pair cut by the window edge gives a start lag that the end rejects (`start_only`).
3. *Weak claps.* Claps of amplitude 0.3 with noise 0.02 (a 15:1 ratio) are refused by the crest gate (2.07 against 2.5) and
   would be refused by `min_peak` 0.25 (0.13). The refusal is safe (never a wrong lag).

**Fix plan:** (0) 2026-11-16: the flash check that this plan relies on had its own hole, BUG-0064 (a flash of a pair not seen): fixed in X.23, so a mapping wrong by 1 s is not usable (T-SYNC-04f tests it through `estimate_sync`, `validate_sync` and `decide_usability`); item (a) below is covered at that level, a test through `sync_take` and `sync.json` was added in X.24 (T-SYNC-05e: audio forced 1 s wrong, `sync.json` not usable); the database row of such a take is BUG-0065. (a) P2.06 (usability rule): a test that a take whose audio lag is wrong by one second is not usable because the flash
residual at the start and at the end exceeds one frame, and that `ok` from sound alone is never usable (DEC-0025 (6)); (b) P2.07
(real pairs): measure the peak, ratio and crest of real claps and the real drift of the phones, set `min_peak`, `min_peak_ratio`,
`min_crest` and `max_drift` from them, and evaluate a pair-structure check (the number and spacing of the transients must agree on
the two cameras) if real recordings show damaged pairs; (c) capture protocol: both claps must be clearly audible on both phones.
**Fix:** —
**Verified:** —

**History:**

- 2026-11-16 OPEN → PLANNED — found by the adversarial pass of the P2.04 rework; the limits are in DEC-0033 and the README.

### BUG-0062 — P2.04 records do not match the code

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (records; the code is not affected)                                                     |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/P2.04.md` §2, §4–§8, `Docs/tracking/{TASK_STATUS,CHANGELOG,DECISIONS}.md`, `taiji_ai/README.md` |
| Found by / date | agent (Claude Code), 2026-11-16, independent review of P2.04                               |
| Affects         | The `DONE` status of P2.04 and the value of its evidence                                   |

**Description:**

1. "Bugs: none" / "None found during this task" (task file §7 and the CHANGELOG entry) and "No open S1/S2 bug": see BUG-0058 (S1)
   and BUG-0059..0061.
2. AC1 is ticked "mutations caught" and plan step 5 asks for a mutation check (sign of the lag, the window choice, the found gate),
   but the implementation log has no mutation run. The review's run (34 mutants) left 14 alive (BUG-0060).
3. DEC-0031, the CHANGELOG and the README say "< 0.01 ms" / "sub-ms" precision from the parabolic interpolation. No test asserts it: the
   contract tolerance is 1 ms (16 samples) and the unit tolerance 1e-4 s (1.6 samples); removing the interpolation passes.
4. AC2 says the parameters and the found/not-found minimums are recorded "with their reason". DEC-0031 gives the reason of ZNCC and
   of the crest factor; `min_peak = 0.25`, `min_peak_ratio = 1.25`, the 30 s window and the 15 s limit (Q1) have a value and no
   evidence of how they were chosen on the fixtures (plan step 4).
5. The test IDs T-SYNC-01b, 01c and 01d are used in the test names and the task file, but the plan's test list has only T-SYNC-01..03.
6. The records write formulas in LaTeX (`$f_{\text{hp}} = 300\text{ Hz}$`) in the task file, DEC-0031 and the CHANGELOG; the other
   records use plain text (BUG-0056 item 6 replaced it in P2.03).
7. The implementation log writes `extract_audio(recording_dir, settings)`; the argument is keyword-only (and unused, BUG-0061).

**Fix plan:** after BUG-0058..0061 are fixed: record the mutation run and the real gate output; correct "Bugs" and the AC1/AC2 text
(strike through, keep the history); record how each minimum was chosen (a short table of the peak and ratio seen on the fixtures and
on the new long takes) in DEC-0031 or a new DEC; add a test that asserts the sub-sample precision (a pulse delayed by a
fractional number of samples, error < 0.01 ms) or remove the claim; register T-SYNC-01b..d and the new IDs in `IMPLEMENTATION_PLAN_V1.md`;
replace the LaTeX; ask the maintainer to put P2.04 back to `IN_PROGRESS` until then.
**Fix:** task P2.04 (rework), 2026-11-16 — the false statements of §5–§8 of the task file are struck through and listed in §9.12; the mutation run, the gate and the counts are recorded from the real output; T-SYNC-01b..d and 06..10 are in the plan's test list; the reason of each parameter is in DEC-0033; LaTeX replaced by plain text in the task file, DEC-0031 and the CHANGELOG.
**Verified:** agent, 2026-11-16 — final gate 10/10 (task file §9.11).

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.04 review; `TASK_STATUS.md` and the task file were **not** edited by the reviewer
  because another writer is changing them (recommendation: reopen P2.04).
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.04 (rework, task file §9).

### BUG-0061 — `io/audio.py` and `io/audio_sync.py` break repository rules

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (conventions, dead code, made-up numbers in rare paths, memory; the normal path is correct) |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/io/audio.py`, `taiji_ai/src/taiji_ai/io/audio_sync.py`              |
| Found by / date | agent (Claude Code), 2026-11-16, P2.04 review (reading the code, probe E9)                 |
| Affects         | Maintainability; AGENTS.md §5.1, §6, §2 Step 4 checklist ("errors never swallowed")        |

**Description:**

1. `extract_audio(..., settings=...)` reads `settings = settings or get_settings()` (audio.py line 46) and never uses it; `estimate_sync`
   accepts `settings` only to pass it on. A dead argument (the same as BUG-0054 item 2).
2. `except OSError: pass` around the cleanup (audio.py lines 108–111); `except Exception` in `extract_audio` (line 104, which also turns
   a timeout into the same message as any other error) and in `read_wav` (line 125).
3. Invented numbers: `ratio = 999.0` when there is no second peak (two places in `xcorr_lag`); one clean pulse then passes the
   ratio gate on a made-up value (checked: `xcorr_lag` on the one-pulse signals of the unit test gives `found = True`, peak 1.0,
   `peak_ratio` 999.0; the mutation "999 → 0" breaks that test); `SyncWindow(window_a_s=(0.0, 1.0))` is returned for "no audio",
   twice, a window that was never observed; `drift = 0.0` when `dt_ref <= 0` (a dead branch, but unknown must be `None`).
4. `dur_a`, `dur_b`, the window arithmetic and `xcorr_lag` use `params.sr`, while `envelope` uses the `sr_a` and `sr_b` returned by
   `read_wav`; nothing checks `sr_a == sr_b == params.sr`, so a wav with another rate (a cache written by an older version, a later
   change of the extraction) shifts every time without an error.
5. `ValueError` for a take mismatch and for an unreadable manifest: a specific exception is the rule (AGENTS.md §6).
6. The envelope is computed on the whole recording: probe E9, 30 min (the limit of DEC-0025): 1.15 GB of peak numpy memory per camera
   for 115 MB of audio. Only the two windows plus their margin are used.
7. The "no audio" result is built twice (the early check and the `except NoAudioStream`), 20 duplicated lines.

**Fix plan:** remove `settings` from both functions (callers and tests); log a warning for a failed delete, narrow the two `except`
clauses (OSError, `scipy` errors, `subprocess.TimeoutExpired` with its own message); replace 999.0 by a documented constant for "no
second peak" and carry it as `None`/a named cap in `LagEstimate` (decide with the maintainer if `SyncWindow.peak_ratio` may be `None`
when `found`), build the "no audio" result in one helper with a window taken from the real recording duration, or make the window optional
in the schema (a `proxy/1` style decision: DEC); `drift = None` instead of 0.0; compare the three sample rates and raise `AudioError`;
specific exceptions; filter the windows only. Tests: a wav with another rate, one-sided "no audio", a timeout, memory of the envelope of
a 10 min take under a limit.
**Fix:** task P2.04 (rework), 2026-11-16 — no `settings`; no swallowed error (the failed delete is logged, the third-party parser's own errors become `AudioError`); no made-up number (`ratio_floor`, the ratio never below 1, the no-audio windows from the container duration, no 0.0 drift); the sample rate of both wavs is checked; `SyncError`, `TakeMismatch`, `SyncInputError`; the envelope is computed on the windows only (141 MB for 10 min, 282 MB for 28 min); the no-audio result is built once. Also: audio with dropped samples is refused, NaN/inf is not found, multichannel `read_wav` scales first, the same recording twice is refused.
**Verified:** agent, 2026-11-16 — T-SYNC-10 passes (50 tests); the mutations of the refusals, the cache, the stereo mix, the rate check, the gap check, the NaN guard and the parser errors are caught; ruff and mypy clean; the diff was re-read.

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.04 review.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.04 (rework, task file §9).

### BUG-0060 — P2.04 tests passed with 13 broken rules (mutation run)

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (test strength; no wrong data in the cases they cover)                                  |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/tests/contract/test_audio_sync.py`                                               |
| Found by / date | agent (Claude Code), 2026-11-16, mutation run on a copy of `src` (the repository was not modified) |
| Affects         | A later change could break one of these rules with every test still green; AC1 has no evidence |

**Description:** 34 one-rule breakages of `audio.py` and `audio_sync.py` against `test_audio_sync.py` (baseline green): **20 caught,
14 survived**. Survivors: (1) no sub-sample interpolation and (2) the interpolation with the wrong sign (the tolerance is 16 samples
in the contract tests and 1.6 in the unit test); (3) the sign of the A/V offset in the **end** window (the test fakes the offset
and checks the offset only, not the drift); (4) `start_only` reported as `ok` and (5) `start_only` without its offset (no test has a
take where only the start claps are found); (6) `min_peak` and (7) `min_peak_ratio` removed one by one (only the crest gate is
exercised: a flat tone is rejected by it first), and `found = True`; (8) the take-mismatch refusal; (9) the `audio.wav` cache (the test
compares only the returned path); (10) `-ac 1` (every fixture is mono); (11) the low-pass cut-off; (12) the 15 s search limit (no
test that an offset beyond `max_lag_s` is refused). The 14th survivor, an ignored ffmpeg failure, is equivalent (the later `os.replace` fails and becomes the same `AudioError`).
Other defects of the tests: every fixture is 10–16 s, so the long-take branch (windows of 30 s) never runs (BUG-0058);
T-SYNC-01c edits `recording.json` instead of a file whose audio starts later (the plan says a fixture; the probe E6 shows the real path
is right: 0.0 ms of error, but nothing tests it); `print("DEBUG 01B:", result)` is left in T-SYNC-01c and in the drift test
(mislabelled); the last assertion of T-SYNC-03 is duplicated; `rec_dir` in the first test is unused; the plan's F-VID fixtures in
`conftest.py` and its step 5 (mutation check) were not done.

**Fix plan:** one test per survivor, each on the specific rule: (1)–(2) a pulse delayed by a fractional number of samples, error under
0.01 ms (the claim of DEC-0031); (3) a non-zero A/V offset with a drift: the drift must not change; (4)–(5) a take with claps only
at the start (`start_only`, offset kept, drift `None`) and only at the end (`not_found`); (6)–(7) a clap pair that is correlated but
weak (a peak below 0.25) and one with two equal pairs (a ratio below 1.25): not found; (8) two recordings of different takes:
`ValueError`/the new specific exception; (9) a stale marker in `audio.wav` is returned without a new ffmpeg run; (10) a stereo
source gives a mono wav; (11) a burst whose spectrum separates the cut-off values (or drop the claim); (12) an offset of 16 s is not
found. Replace the faked A/V offset by a real container (`-itsoffset`, as in the probe E6);
remove the debug prints and the duplicate assertion. Rerun the 34 mutations until every survivor is caught or shown equivalent.
**Fix:** task P2.04 (rework), 2026-11-16 — four independent agents wrote the tests red first (new files), four others reviewed them; the lead extended them from the reviews (start differences of ±8 s, B stopping 23 and 50 s early, AAC long take, exact no-audio windows, the failed-cleanup and message checks, multichannel read_wav, the structural check that the envelope is computed on windows only, matcher cases) and replaced the faked A/V offset of T-SYNC-01c by a real container; debug prints, the duplicated assertion and the unused variable are gone.
**Verified:** agent, 2026-11-16 — a mutation run of the reworked code (43 mutants) ended with 39 caught; the 4 survivors got a test each and are caught; targeted run of the new logic: 12 of 14 mutants caught by the existing tests; the 2 survivors (B's end slice not widened at the start / at the end) got T-SYNC-06f (a clap at the edge of the window pushed by +/-400 ppm) and are caught: 14 of 14.

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.04 review (mutation run).
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.04 (rework, task file §9).

### BUG-0059 — Drift and `t_ref_s` are taken at the window centres, not at the claps

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (a systematic bias of at most 2 ms at the end of a take, under 1/16 frame; the 1 ms claim of the offset is only just met) |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/io/audio_sync.py` (`t_ref_start`, `t_ref_end`, `window_a_s`)        |
| Found by / date | agent (Claude Code), 2026-11-16, probe E2 of the P2.04 review (synthetic takes with a known drift) |
| Affects         | The drift and the offset in `sync.json` (P2.06), the mapping of times near the claps       |

**Description:** the offset is measured where the claps are (about 6 s after the start, 6 s before the end), but it is assigned to
`t_ref_s`, the centre of the 30 s window (15 s), and the drift divides the lag difference by the distance of the two window centres
instead of the distance of the two clap pairs. Probe E2 (A records [0, T], B starts 0.5 s late and stops 1 s late, claps 6–7 s after
the later start and 7–6 s before the earlier stop, B's clock scaled by 1 ± 1e-4): T = 120 s: drift +100 ppm reported as 118.5 ppm,
−100 ppm as −118.4 ppm, offset error −0.8 ms / +0.8 ms at `t_ref_s`; T = 300 s: 106.4 ppm and −106.1 ppm. The bias is about
(T − 13.5) / (T − 30) − 1 for this geometry: +18 % at 120 s, +6 % at 300 s, +55 % at 60 s. T-SYNC-02 (±20 %) passes only because its 16 s fixture puts the clap pair at the centre of the
7.2 s windows. Second point: `window_a_s` and `t_ref_s` are computed on A's audio timeline, while the schema and P2.01 say A's video
timeline; the difference is `audio.start_offset_s` of A (0 in every test; 4.5 s in the `offset_video` fixture), worth 100 ppm × that
number of seconds of offset error (0.45 ms for 4.5 s).

**Fix plan:** take `t_ref` of each window at the clap pair (the energy-weighted centre of the transient in A's window, or the A-time of the
correlation peak) and convert it to A's video timeline by adding `av_offset_a`; compute the drift between the two `t_ref`; state in the
`SyncManifest` docstring and DEC-0026 that "the matched window" is the window around the claps (a wording change, no schema change).
Tests: takes of 60, 120 and 300 s with ±100 ppm: drift within 10 %, offset error at `t_ref_s` under 0.2 ms; a non-zero `audio.start_offset_s`
of A (a real container, `-itsoffset`).
**Fix:** task P2.04 (rework), 2026-11-16 — `t_match_s` (centroid of the part of the product above 5 % of its maximum) gives `t_ref_s` at the claps on A's video timeline; the windows are on A's video timeline; `offset_s` is the start lag at `t_ref_s`; DEC-0033. The adversarial pass found the whole-product centroid dragged to the window middle by noise (2 to 3 ms at 1500 ppm): thresholded.
**Verified:** agent, 2026-11-16 — T-SYNC-07a..g pass (drift within 10 %, offset ≤ 0.2 ms at `t_ref_s`, the mapping hits the claps of both pairs within 0.5 ms, windows on A's video timeline with an audio offset, noise case); the mutations 't_match = window centre', 't_ref = window centre' and 'windows on the audio timeline' are caught.

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.04 review.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.04 (rework, task file §9).

### BUG-0058 — The end window loses the claps or accepts a wrong lag when B stops before A (takes of 60 s or more)

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S1 (wrong timestamp: a wrong end lag is accepted as `ok`, AGENTS.md §3.1). Mitigations: P2.05 (flash) and P2.06 (usability rule) are not built and must catch it; the maintainer may reclassify |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/io/audio_sync.py` (`estimate_sync`, end window: `t0_end_b`, lines 314–344) |
| Found by / date | agent (Claude Code), 2026-11-16, probe E1 of the P2.04 review (synthetic takes with exact truth) |
| Affects         | `status`, `drift` and the end lag of every take of 60 s or more in which camera B stops before camera A; the takes that Taiji 24 needs (minutes) |

**Description:** for a take of 60 s or more the A end window is the last 30 s, the B end window starts `window + 15 s` before the end of B
(45 s long), and the correlation accepts lags of ±15 s counted from the two window starts. The offset that is found is therefore
`lag + (t0_end_b − t0_end_a)` with `t0_end_b − t0_end_a = (dur_b − dur_a) − 15 s`: the real offset must lie in
`[dur_b − dur_a − 30, dur_b − dur_a]`, which holds only when B stops **between 0 and 30 s after A**. When B stops earlier the true
peak is outside the search range.

**Steps to reproduce (synthetic, `.mov` with PCM audio, 64×48 video, mono 16 kHz, noise σ 0.002, 5 ms 1.2 kHz bursts; a pair of claps
1 s apart 6 s after the later start and 7 s before the earlier stop, as the capture protocol's margins; A records [0, T], B starts
0.5 s late):**

| Take | B stops | status | end found | offset error | drift (true 0) |
| ---- | ------- | ------ | --------- | ------------ | -------------- |
| 120 s | same time as A | ok | yes | −0.01 ms | 0.1 ppm |
| 120 s | 3 s after A | ok | yes | −0.01 ms | 0.1 ppm |
| 120 s | **3 s before A** | **start_only** | no (peak 0.0) | −0.01 ms | `null` |
| 120 s | **0.4 s before A** | **ok** | yes (peak 0.5, ratio 122) | −0.01 ms | **−11111 ppm** |
| 120 s | B starts 0.5 s early, stops 1 s before A | **ok** | yes (ratio 121) | 0.0 ms | **−11111 ppm** |
| 300 s | 3 s before A | **start_only** | no | −0.01 ms | `null` |
| 300 s | 0.4 s before A | **ok** | yes (ratio 143) | −0.01 ms | **−3704 ppm** |

The wrong drift is exactly the 1 s gap of the clap pair divided by the distance of the window centres (90 s and 270 s): the end window
matched the second clap of the pair, a wrong lag of 1 s (30 frames at 30 fps) with a high ratio, because the true peak is out of range and the
neighbour is unique inside it.

**Expected vs actual:** expected `ok`, offset error under 1 ms and drift near 0 whichever phone stops first; actual `start_only` or `ok` with
the end lag 1 s wrong. Every fixture of the tests is 10–16 s long, so only the short-take branch (`dur < 60 s`, windows of 45 % of the take)
runs; the branch of the real use (30 s windows) has no test.

**Root cause:** the end search is anchored on the durations (`dur_b − dur_a`) and offset by an arbitrary 15 s instead of on the offset that
the start window has just measured; its ±15 s range is not centred on where the claps are.

**Fix plan:** (1) predict the claps in B from the start result: the B end window is A's end window shifted by `offset_start`, widened by
±`max_end_lag_s` (default 2 s: 1000 ppm over 30 min is 1.8 s), whatever the stop times; when the start was not found the end cannot be
predicted: report `not_found` (no guess); (2) add a plausibility bound on the drift (for example 2000 ppm: phone clocks stay within a few
hundred ppm); a larger value turns the result into `start_only`, not `ok` (a wrong lag then cannot become a mapping); (3) tests, red
first: takes of 60, 120 and 300 s; B stopping 20 s, 3 s and 0.4 s before and after A; B starting before and after A; the claps of the end
pair missing in one file; assert status `ok`, offset error ≤ 1 ms, drift error ≤ 20 ppm, and that the mapped time of the end claps is within
1 ms; (4) a mutation run on the new window and on the bound; (5) tell P2.05/P2.06 that `ok` is not proof: the flash check stays mandatory.
**Fix:** task P2.04 (rework), 2026-11-16 — the end window is the last 30 s of the stretch both cameras recorded, searched in B where the start offset predicts it, in a slice wider than A's window by the margin on both sides (cut to what B recorded, no zero fill), lag range centred on the prediction; a window is searched wider than it is accepted (start: `max_lag_s` + 3.5 s guard; end: `end_margin_s` 3.5 s + drift allowance, accepted only within `max_drift`, now 500 ppm: the cross-check of the two windows); exclusion radius 0.2 s; DEC-0033. The first draft of the fix (margin 0.5 s) failed the T-SYNC-08 case of 9091 ppm and was corrected; the adversarial pass then found three more ways to the same S1 (a pair cut by a window or slice edge, a true match just beyond the start range, an end window anchored on A's own end): all fixed, their cases are tests.
**Verified:** agent, 2026-11-16 — T-SYNC-06/06b/06d/06e/06f/08 pass (80 of the 149 new tests of the first rework were red on the old code); the 13 cases found by the adversarial pass are tests; targeted mutation run of the new logic: 12 of 14 mutants caught by the existing tests; the 2 survivors (B's end slice not widened at the start / at the end) got T-SYNC-06f (a clap at the edge of the window pushed by +/-400 ppm) and are caught: 14 of 14; the whole-take mutation run of the first rework ended at 43 of 43; gate 10/10. Not claimed: a wrong lag is still possible when a clap pair is damaged the same way at both ends (BUG-0063): the flash check must gate use.

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.04 review. Not fixed by the reviewer: the code of P2.04 is the other writer's; the maintainer decides who fixes it.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.04 (rework, task file §9).

### BUG-0057 — CHANGELOG: two MD049 warnings in the X.03 entry

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (style of old text)                                                                     |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tracking/CHANGELOG.md`, entry "2026-11-14 — X.03" (present in HEAD)                  |
| Found by / date | agent (Claude Code), 2026-11-16, IDE diagnostics after the P2.03 rework edited the file    |
| Affects         | Nothing but the lint count of the file                                                     |

**Description:** the X.03 entry writes the title of `AGENTS.md` §9 with underscores (MD049 expects asterisks).
**Fix plan:** replace the two underscores by asterisks (no change of meaning).
**Fix:** task P2.03 (rework), 2026-11-16 — done.
**Verified:** agent, 2026-11-16 — the IDE shows no MD049 warning for that line.

**History:**

- 2026-11-16 OPEN → PLANNED → FIXED → VERIFIED → CLOSED — found and fixed in P2.03 (rework).

### BUG-0056 — P2.03 records do not match the tree

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (records; the code is not affected)                                                     |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/P2.03.md` §4–§8, `Docs/tracking/{TASK_STATUS,CHANGELOG,DECISIONS}.md`, `taiji_ai/src/taiji_ai/cli.py:158` |
| Found by / date | agent (Claude Code), 2026-11-16, independent review of P2.03                               |
| Affects         | The `DONE` status of P2.03 and the value of its evidence                                   |

**Description:**

1. **The gate is red on the current tree.** `check.ps1` gave 8/10 (ruff-check and ruff-format failed); run directly, `ruff
   check` reports E501 and `ruff format --check` wants to reformat `cli.py:158` (the `msg = ... if result.created else ...`
   line is 132 characters). The task file, CHANGELOG and TASK_STATUS say "Gate 10/10 PASS in 25.6 s". The diff read at the
   start of this review showed that statement already wrapped in parentheses; `cli.py` was modified at 09:13:37, after the
   task records (09:11–09:12), and `Docs/tasks/P2.04.md` and `TASK_STATUS.md` were written at 09:15, so another writer is
   active (the BUG-0027 situation). Who changed it is not known. The close-out box "Checks pass" is false for this tree.
2. **Test counts.** The records say "673 passed (was 663 before; 10 new tests)". The suite collects and passes 674 tests;
   the task adds 8 (`test_proxy.py`) + 3 (`test_cli_ingest.py`) = 11 (same kind of error as BUG-0048).
3. **Step 2 is logged as done, but the edit-list fixture is missing.** Plan §2 step 2 says "Fixture with a non-zero start
   time (`-output_ts_offset`) **and with an edit list**" and §1 says phone files with an edit list "were not covered". Only
   the existing `offset_video` was used; the omission is not recorded as a deviation. That fixture is what finds BUG-0052.
4. **Self-review claims that are not true.** "Bugs: None found" (see BUG-0052..0055), "Errors are raised ..., never swallowed"
   (two `except OSError: pass`, BUG-0054), AC2 ticked although no test covers a failed check (BUG-0053). No red-run output is
   recorded for "written red first", and no mutation run was made although BUG-0041/0047/0051 show the first tests of this
   project were weak each time.
5. **Test IDs.** `T-IO-10b`, `T-IO-10c` and `T-IO-11b` are used in test names and in the task file but are not in
   `IMPLEMENTATION_PLAN_V1.md` (only T-IO-10, T-IO-11); `T-IO-11b` (metadata) is not even in the task file's test table.
6. DEC-0029 and the task file write the tolerance with LaTeX (`$\le 1.0$`); the other records use plain text (`≤`).

**Fix plan:** after BUG-0052..0055 are fixed: wrap `cli.py:158` (ruff format), run the full gate and record the real output;
re-measure the test count and correct task file §5, CHANGELOG and TASK_STATUS; add the edit-list fixture to the
implementation log as "done late, found BUG-0052" (history is append-only: mark the old statement, do not delete it);
correct self-review §6/§7; register `T-IO-10b/10c/11b` (and the new ones) in `IMPLEMENTATION_PLAN_V1.md` §test list; replace
the LaTeX; ask the maintainer to put P2.03 back to `IN_PROGRESS` in `TASK_STATUS.md` until then.
**Fix:** task P2.03 (rework), 2026-11-16 — the gate is green on the final tree (`cli.py:158` had been wrapped by the other writer at 09:29); counts re-measured (files of the task 22 + 21 + 16, 44 new; suite 717 with the 10 tests of P2.04); the edit-list fixture built and logged as done late; the false statements of §5–§7 struck through and listed in §9.10 of the task file; T-IO-10b, 10c, 11b, 20..27 registered in `IMPLEMENTATION_PLAN_V1.md`; LaTeX replaced; CHANGELOG and TASK_STATUS corrected by strike-through (history kept); P2.03 was put back to `IN_PROGRESS` and is `DONE` again.
**Verified:** agent, 2026-11-16 — final gate 10/10 PASS (task file §9.9).

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.03 review; `TASK_STATUS.md` and the task file were **not** edited by the
  reviewer because another writer was changing them (recommendation: reopen P2.03).
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.03 (rework, task file §9).

### BUG-0055 — A failed proxy check and a half-finished `ingest --proxy` are reported badly

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (wrong or missing report; no data is wrong)                                             |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/io/proxy.py` (`make_proxy`), `io/ingest.py` (`ingest_recording`), `cli.py` (`_ingest`, `_proxy`) |
| Found by / date | agent (Claude Code), 2026-11-16, probes P2 and P3 of the P2.03 review (synthetic clips, throwaway data folder) |
| Affects         | Batch runs (P2.07, P9.03) cannot tell a usable proxy from a refused one                    |

**Description:**

1. *Failed check.* With `pts.parquet` shifted by +0.2 s, `taiji proxy <id>` prints `proxy <id> (240p, check failed)` on
   standard output, **exits 0**, and the library logs "proxy created ... check=False" at **INFO**. `proxy.mp4` and
   `proxy.json` (`passed: false`, 6.0 frames) are kept, as the plan says, but nothing in the exit code or the log level says
   the proxy must not be used for frame-accurate work.
2. *Half-finished ingest.* `make_proxy` runs after the ingest transaction is committed. When it raises (probe: ffmpeg not
   found), `taiji ingest ... --proxy` prints only `error: ffmpeg is not available on PATH` (exit 1, empty standard output).
   The recording **was** stored (folder and `recording.json` exist), its ID is not printed, and the user is told "error"
   about something that succeeded. Running the same command again does recover (`already ingested <id> (proxy: 240p, check
   passed)`), but nothing says so.

**Fix plan:** (1) log a WARNING with `recording_id`, both frame counts and `max_abs_dt_frames` when the check fails; the CLI
prints a one-line explanation to standard error and exits 1 (the maintainer confirms the exit code, it is part of the
contract in `cli.py` and DEC-0027 (7)); (2) `ingest_recording` catches `ProxyError` after the commit and returns
`IngestResult(..., proxy=None, proxy_error=<message>)`; the CLI prints `ingested <id> ...` on standard output, `warning: proxy
not made: ...` on standard error, exit 1. Tests: tampered `pts.parquet` (as in probe P2) and a failing proxy step after ingest
(monkeypatch `subprocess.run`).
**Fix:** task P2.03 (rework), 2026-11-16 — WARNING log on a failed check; `taiji proxy` and `taiji ingest --proxy` exit 1 with the explanation on standard error and the ID on standard output (the maintainer confirmed exit code 1); `ingest_recording` returns `IngestResult.proxy_error` instead of raising after the commit; the CLI prints the ID and `error: the proxy of <id> was not made: ...`; `re.fullmatch` for the UUID.
**Verified:** agent, 2026-11-16 — T-IO-27 (four CLI cases and two ingest cases) was red on the old code and is green; the mutations 'cli: failed check exits 0', 'cli: proxy step failure exits 0', 'ingest: ProxyError raised again', 'proxy_error lost' are caught; probes P2 and P3 on the fixed code give the expected output.

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.03 review.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.03 (rework, task file §9).

### BUG-0054 — `io/proxy.py` breaks repository rules

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (conventions, dead code and a few made-up numbers in a rare path; the normal path is correct) |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/io/proxy.py`, `io/ingest.py`                                        |
| Found by / date | agent (Claude Code), 2026-11-16, P2.03 review (reading the code, then probe P4)            |
| Affects         | Maintainability; AGENTS.md §5.1, §6, §2 Step 4 checklist ("errors never swallowed")        |

**Description:**

1. Line 7 of the module docstring is Vietnamese ("Lệnh FFmpeg (không dùng shell, có timeout)"); code and comments are in
   English (CLAUDE.md, Communication).
2. `make_proxy(..., settings=...)` reads `settings = settings or get_settings()` (line 140) and never uses it again: a dead
   argument that every caller passes.
3. Two `except OSError: pass`: `_ffmpeg_version` (lines 78–79) returns `"unknown"` silently and `@cache` keeps that value
   for the life of the process after one transient failure; the cleanup in `finally` (lines 256–257) hides a failed delete.
4. Invented numbers in `proxy.json`: `_check_timestamps` writes `999.0` for `max_abs_dt_frames` when the median interval is
   unknown or zero (lines 96, 110, 120), and for an empty scan it writes `points=1`, `max_abs_dt_s=0.0` and
   `max_abs_dt_frames=0.0` although nothing was measured (AGENTS.md §5.1: no fabricated values; unknown is not 0).
5. The command exists twice: `PROXY_ARGS_TEMPLATE` (what `proxy.json` records) and the literal `cmd` list (what runs). Nothing
   ties them; a mutation that changes `args` survives (BUG-0053).
6. `_check_timestamps` recomputes `(pts - start_pts) * time_base` (line 100), which is `PtsScan.t_sec`
   (`io/frames.py:58`).
7. `ingest.py` imports `make_proxy` inside `_existing` and `ingest_recording`; `proxy.py` does not import `ingest`, so a
   top-level import works.
8. `os.replace(proxy_tmp, proxy_final)` happens before `proxy.json` is written: a crash or a full disk in between leaves the
   new `proxy.mp4` with the old `proxy.json` (wrong `proxy_sha256`).

**Fix plan:** translate the docstring; use `settings` (for example the ffmpeg timeout and the cap of 720 lines) or remove the
argument in `make_proxy`, `ingest.py`, `cli.py` and the tests; log a WARNING and do not cache the failure in
`_ffmpeg_version` (an unknown version is logged), and log a failed delete; for the degenerate cases raise `ProxyError`
("proxy has no frames") or add an explicit reason to the check instead of 999.0/0.0 (a schema change of `proxy/1` needs a DEC
and the maintainer: decide in the task); build `cmd` from `PROXY_ARGS_TEMPLATE` (fixed prefix `-hide_banner -loglevel error
-y`, placeholders replaced) so there is one source; use `scan.t_sec`; import `make_proxy` at the top of `ingest.py`; delete the
old `proxy.json` before replacing `proxy.mp4` (a missing manifest means "not usable").
**Fix:** task P2.03 (rework), 2026-11-16 — docstring in English; `settings` removed from `make_proxy`; `_ffmpeg_version` raises and does not cache a failure; the cleanup logs a warning; `_check_timestamps` raises `ProxyError` for no frames and for a deviation without a frame interval (no `999.0`, no `0.0`); one command (`_build_command` from `PROXY_ARGS_TEMPLATE`); `PtsScan.t_sec` reused; `make_proxy` imported at the top of `ingest.py`; the old `proxy.json` removed before `proxy.mp4` is replaced; a narrow `except` tuple instead of `except Exception`. No schema change of `proxy/1` was needed: the unmeasurable cases raise.
**Verified:** agent, 2026-11-16 — T-IO-24..26 and the mutations 'args do not match the command', 'invented 999.0', 'stale proxy.json kept', 'ffmpeg version failure -> unknown' are caught; ruff and mypy are clean; the diff was re-read.

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.03 review.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.03 (rework, task file §9).

### BUG-0053 — P2.03 tests passed with 14 broken rules (mutation run)

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (test strength; no wrong data was written by these rules in the tests' cases)           |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/tests/contract/test_proxy.py`, `tests/contract/test_cli_ingest.py` (first versions) |
| Found by / date | agent (Claude Code), 2026-11-16, mutation run on a copy of `src` (the repository was not modified) |
| Affects         | A later change could break one of these rules with every test still green; AC2 has no evidence |

**Description:** 23 one-rule breakages of `proxy.py`, `ingest.py` and `cli.py`, run against `test_proxy.py` and
`test_cli_ingest.py` (baseline green): **8 caught, 15 survived**. Caught: `-map_metadata -1`, the 720-line cap,
`rotation_applied`, an always-true check, `check.points`, the fresh-ingest `proxy` flag, the UUID check, the CLI wording.
Survivors: (1) no `+faststart` (the UI needs it for Range playback, P8.04); (2) audio kept (no `-an`; the plan says video
only); (3) no `-pix_fmt yuv420p` (a 4:4:4 or 10-bit source would not play in a browser); (4) no `-g 30` (seek granularity);
(5) `-crf 23` changed to 40; (6) `source_sha256` replaced by the proxy hash; (7) `proxy_sha256` replaced by the source hash;
(8) `ffmpeg` version replaced by `"unknown"`; (9) `args` no longer the command that ran; (10) `n_frames_source` replaced by
`n_frames_proxy` (hides a count mismatch); (11) a non-zero ffmpeg exit code ignored; (12) the temporary file not removed on
failure; (13) **a failed check hides the proxy (raises) instead of keeping and marking it: AC2 is untested**; (14)
`ingest_recording(..., proxy=True)` on an already ingested file ignores the flag. The 15th survivor, removing
`-fps_mode passthrough`, is equivalent with the installed FFmpeg (the plan records that the default already keeps the
timestamps; the explicit argument is a guard against a future default).

**Fix plan:** one test per survivor, each checking the specific rule: (1) the `moov` atom comes before `mdat` in `proxy.mp4`;
(2) `ffprobe` finds no audio stream in the proxy of `cfr_video` (it has audio); (3) a `yuv444p` fixture gives a `yuv420p`
proxy; (4) keyframes at most 30 frames apart (3 s clip); (5) and (9) after BUG-0054 builds `cmd` from the template, assert
the template holds `-crf 23`, `-g 30`, `-fps_mode passthrough` and that `proxy.json` `args` equal it; (6)–(8)
`source_sha256` equals the recording's, `proxy_sha256` equals `sha256_file(proxy.mp4)`, `n_frames_source` equals the rows of
`pts.parquet`, `ffmpeg` equals the first line of `ffmpeg -version`; (10) and (13) tamper `pts.parquet` by +0.2 s (probe P2):
`make_proxy` returns `passed=false`, both files exist, the counts in the manifest are the real ones; (11) and (12)
monkeypatch `subprocess.run` to exit 1: `ProxyError`, no `proxy.mp4`, no `proxy.json`, no `proxy.tmp-*`; (14) ingest the same
file twice with `proxy=True`: second call `created=False` and a proxy manifest. Rerun the 23 mutations (the harness is a
short script; keep it out of the repository unless the maintainer asks) until every survivor is caught or shown equivalent.
**Fix:** task P2.03 (rework), 2026-11-16 — one test per survivor: T-IO-23 (faststart, no audio, yuv420p, keyframes), T-IO-24 (hashes, counts, version, `args` = the executed command, the template pins `-crf`, `-g`, `-fps_mode`), T-IO-25 (failure, timeout, missing ffmpeg, unreadable version, stale manifest), T-IO-26 (AC2), T-IO-27 (already ingested file, proxy failure); the second mutation list also showed an untested branch (`ffmpeg -version` unreadable): two cases added.
**Verified:** agent, 2026-11-16 — mutation run on a copy of `src` against the reworked code: 41 caught, 0 survived (the 23 mutations of the first review rewritten for the new code plus 18 for the new branches); the former equivalent mutant (`-fps_mode passthrough`) is caught by the template test.

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.03 review (mutation run).
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.03 (rework, task file §9).

### BUG-0052 — `scan_pts_ticks` counts packets that are never shown (trimmed phone clips)

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S1 (wrong timestamp: AGENTS.md §3.1). Mitigations: no consumer exists yet (P3 not started) and the P2.03 check marks the proxy as failed; the maintainer may reclassify |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/io/frames.py` (`scan_pts_ticks`, written in P2.02), used by `io/ingest.py:168` and `io/proxy.py` |
| Found by / date | agent (Claude Code), 2026-11-16, probe P1 of the P2.03 review (synthetic clips)            |
| Affects         | `pts.parquet`, `recording.json` (`n_frames`, duration, VFR verdict), every later stage that maps a decoded frame to its time by row number, and the proxy check |

**Description:** a clip made on a phone by trimming (stream copy that starts between two keyframes) carries an edit list. The
packets before the edit start stay in the file with negative times and the flag `D` (discard); the decoder never outputs
them. `scan_pts_ticks` keeps every packet that has a `pts` and a size, so they become frames.

**Steps to reproduce (synthetic):** base clip 4 s, 30 fps, 320×240, `-g 15`; `ffmpeg -ss 0.7 -i base.mp4 -c copy trimmed.mp4`.
`ffprobe` lists 105 packets, six with the flag `D` and `pts_time` −0.200, −0.167, −0.133, −0.100, −0.067, −0.033;
PyAV decoding and `ffprobe -count_frames` give **99** frames, the first one at `pts` 0 (stream `start_time` 0).

**Expected vs actual:** expected 99 rows in `pts.parquet`, the first at `t_sec` 0, `n_frames` 99. Actual: 105 rows, six with
negative `t_sec`, `n_frames` 105. Decoded frame *k* would get the time of row *k*, which is 0.2 s early for every frame. The
proxy has 99 frames, so the check fails (`max_abs_dt_frames` 6.0, `passed: false`): the safeguard works, but a normal
phone file ends up with an unusable proxy and wrong source times.

**Root cause:** `scan_pts_ticks` (`frames.py:69`) filters only `p.pts is not None and p.size > 0`; it does not drop packets
flagged as discard. P2.02 had no fixture with an edit list, and the P2.03 plan promised one (BUG-0056 item 3).

**Fix plan:** (1) fixture `trimmed_video` in `tests/conftest.py` (the command above); (2) tests, red first: for **every**
video fixture the packet scan has the same count and the same timestamps as the PyAV decode (the strong oracle; it also
guards future fixtures); `ingest_recording` of `trimmed_video` gives `n_frames` 99 and no negative `t_sec`; the proxy check
of `trimmed_video` passes (99 / 99); a `.mov` container variant, since iPhone files are `.mov`; (3) fix: skip packets with
`p.is_discard` in `scan_pts_ticks` (checked on PyAV 19.0.2: 105 → 99, smallest kept `pts` 0 = `start_time`); if the
oracle test shows a container where the flag is not set, fall back to the decode as the authority for the frame list;
(4) record the rule "packets flagged discard are not frames" in `TECH_WORKFLOW_V1.md` W1 step 3 and in a DEC; (5) check
that no recording ingested before the fix from such a file exists (P2.07 has not run on real files; the folder of tests is
throw-away); (6) consider whether the capture protocol should say "do not trim on the phone" (Docs of P1; maintainer
decision, not a code change).
**Fix:** task P2.03 (rework), 2026-11-16 — as planned: fixtures `trimmed_video` and `trimmed_mov`; `scan_pts_ticks` skips packets flagged discard; T-IO-20 (the oracle: the packet scan equals the PyAV decode on 10 fixtures), T-IO-21, T-IO-22; TECH_WORKFLOW W1 step 3 and DEC-0030 record the rule. The real database held no recording (0 rows), so nothing needed to be ingested again. The capture protocol was not changed (the maintainer's call).
**Verified:** agent, 2026-11-16 — the six trimmed-clip cases were red on the old code and are green; probe P1 on the fixed code: 99 source frames, 99 proxy frames, check passed (was 105 / 99, 6.0 frames); the mutation 'discarded packets counted again' is caught; gate 10/10.

**History:**

- 2026-11-16 OPEN → PLANNED — found by the P2.03 review; probe output kept in the review report. Not fixed by the
  reviewer: the code of P2.02/P2.03 is the maintainer's to change.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P2.03 (rework, task file §9).

### BUG-0051 — P2.02 tests passed with 22 broken rules (mutation run)

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (test strength and one dead check; no wrong data was written)                           |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/tests/contract/test_ingest.py`, `tests/unit/test_vfr.py`, `tests/contract/test_cli_ingest.py` (first versions), `taiji_ai/src/taiji_ai/io/ingest.py` (`_parse_meta`) |
| Found by / date | agent (Claude Code), 2026-11-16, the mutation check of P2.02 (two runs) and a review of the order of writes |
| Affects         | A later change could break one of these rules with every test still green                  |

**Description:** the first versions of the P2.02 tests were all green at the first run, so a mutation run on a copy (88
one-rule breakages) was the only evidence of their strength. 24 mutants survived in two runs: 22 test gaps, one dead check
(`_parse_meta` tested the type of `meta`, which `parse_manifest` already rejects, so the check could not be reached) and one
equivalent mutant. The gaps: the size and duration limits at their exact value; the two sources of the duration (the
container value and the timestamps); an upper-case extension; the branch for a PyAV error; zero frames; a zero median
interval; a path inside the message "not a regular file"; the stored `start_pts` and the audio start offset (no fixture
started at a non-zero timestamp, so `t_sec` from zero and `start_pts` 0 were both accepted); the duplicate count; the
container frame rates; the relative spread; the numbers of the VFR rule and the ffprobe version in the manifest; a zero
median and a single interval in the VFR rule; floor instead of round in `is_vfr` (float noise of one ulp turns into a 2-tick
deviation for some start offsets, found by a search); the audio start in the probe; `--participant`, `--session` and
`--camera` optional on the command line. The self-review found two more: nothing tested that the row is inserted only when
the folder is complete under its final name, and no test ingested a video with one frame (the manifest has a separate
branch for it: no interval, no fps, no spread).
**Fix plan:** a test for each gap, matching the specific rule; the fixtures `offset_video` (video starting at 5.0 s, audio
about 0.5 s later) and `one_frame_video`; remove the dead check; rerun the mutations until every survivor is caught or shown
to be equivalent.
**Fix:** task P2.02, 2026-11-16 — as planned: 21 test cases, two fixtures, the dead check removed.
**Verified:** agent, 2026-11-16 — the full run caught 86 of 87; the three mutations added after the self-review (insert
order, two for the one-frame video) were run on their own and are all caught: 89 of 90. The survivor is `p.size > 0` in
`scan_pts_ticks` (code older than this task; the end-of-stream packet has no timestamp and is already excluded, and no
fixture can make an empty packet with a timestamp), so it is equivalent for every fixture.

**History:**

- 2026-11-16 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in P2.02.

### BUG-0050 — `taiji participant show` echoed an unchecked `--id`

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (a path for personal text to reach the terminal; nothing is stored; no real data was involved) |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/cli.py`, the `show` branch of `_participant` (first version)        |
| Found by / date | agent (Claude Code), 2026-11-16, re-reading the code written for P2.08 before the mutation run |
| Affects         | The rule "log and print IDs only, never free text" (AGENTS.md section 6, `logs.py` rule 2)  |

**Description:** `show` looked the id up with `get_participant` and, when it found nothing, wrote
`participant <id> is not registered` with the id exactly as typed. `add` and `set` were safe because the library functions
check the pattern first, and their messages are generic. The tests used valid ids only, so they could not see it.
**Fix plan:** a library function `require_participant(conn, id)` that checks the pattern, then looks up, with generic
messages (no echo of an invalid value); `show` and `update_consent` use it; tests with a name given as `--id` for `add`,
`set` and `show` that assert the name appears nowhere in the output.
**Fix:** task P2.08, 2026-11-16 — as planned.
**Verified:** agent, 2026-11-16 — the tests are red before the fix; the mutation run catches the removal of the check.

**History:**

- 2026-11-16 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in P2.08.

### BUG-0049 — TECH_WORKFLOW_V1.md: 15 older markdownlint warnings

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | PLANNED (task X.22)                                                                        |
| Found in        | `Docs/TECH_WORKFLOW_V1.md`: lines about 127, 135, 171, 178, 228, 607, 737, 743, 749 (MD032), 271 and 417 (MD040), 363 (MD031), 736, 742, 748 (MD036) |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the P2.01 edit of §4.1 and §4.2     |
| Affects         | Markdown lint noise only                                                                   |

**Description:** the file had never been analysed by the IDE in this workspace. After P2.01 added two blank lines before its
own new `json` blocks (its own two MD031 warnings were fixed in P2.01), 15 older warnings remain: nine lists that follow a
paragraph or a bold label without a blank line, two fenced blocks without a language, one fence glued to its label, and three
bold labels in Appendix B that markdownlint reads as headings.
**Fix plan (X.22):** add the blank lines; open the two blocks as `text`; separate the `run_manifest.json` label from its
fence; for the three Appendix B labels either make them real headings (`####`, which adds them to the structure) or keep them as
bold text inside the list; no wording changes; read the IDE answer after the edits.
**Fix:** —
**Verified:** —

**History:**

- 2026-11-15 OPEN → PLANNED — found while editing §4 in P2.01; scheduled in X.22.

### BUG-0048 — Wrong "full suite" test counts in the P1.04 and X.18 records

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (documentation numbers; the tests themselves passed)                                    |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/P1.04.md:198`, `Docs/tasks/X.18.md:167`, `Docs/tracking/CHANGELOG.md:65,84`    |
| Found by / date | agent (Claude Code), 2026-11-15, when `pytest --collect-only` gave 472 for the whole suite during P2.01 |
| Affects         | The evidence of two closed tasks overstated nothing but understated the suite size and was not what the run showed |

**Description:** I reported "161 passed" at P1.04 and "191 passed" at X.18 by adding the dots of the last three progress
lines of `pytest -q` that I had cut with `Select-Object -Last 3`. The suite had more lines, so the sums were far too low. The
true totals follow from the per-file counts: the files that are not ontology, sheet or schema tests hold 246 tests; with the
59 ontology tests of P1.04 that is 305, with the 77 ontology and 12 sheet tests of X.18 that is 335. The gate passed both times
(the gate does not print a count), so no result was wrong, only the number written down.
**Fix plan:** strike the two wrong numbers in the four places and write the recomputed ones with the reason; from now on
a full-suite count is taken from `pytest`'s own summary line ("N passed") or `--collect-only`, never from the visible dots.
**Fix:** task P2.01, 2026-11-15 — the four places corrected; the P2.01 record uses the summary line (472 passed).
**Verified:** agent, 2026-11-15 — `pytest` summary line: 472 passed; per-file counts add up (246 + 81 + 55 + 77 + 13).

**History:**

- 2026-11-15 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in P2.01.

### BUG-0047 — P2.01 sync tests passed for the wrong reason; `usable_for_metrics` accepted one flash end

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (test strength, and a validator weaker than DEC-0025; no data written yet)              |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/src/taiji_ai/schemas/sync.py` (`SyncManifest._consistent`), `taiji_ai/tests/unit/test_schemas_sync.py` |
| Found by / date | agent (Claude Code), 2026-11-15, the mutation check of P2.01 and a re-read of the validator |
| Affects         | A later change could drop a sync rule without a failing test; a take with the flash found at one end only could be marked usable for metrics |

**Description:** (1) the invalid cases of T-SCH-01e expected only a field name in the message. Removing the rule "a validation
with method `none` has no numbers" still passed because the later rules crash or fire on the same field, and a crash
inside a validator (`max()` of an empty list) is turned by pydantic into a validation error that also names the field.
Five mutations survived this way. (2) DEC-0025 says two cameras are combined only with a flash validation at both ends, but
the validator required one residual only, and a test asserted that a take with only the start flash could be usable.
**Fix plan:** a table of the message of the right rule for each case (`_EXPECT`); `usable_for_metrics` needs
`residual_start_ms` and `residual_end_ms`; the test now says that such a take is kept (end null, no made-up number) but not
usable; rerun the mutations.
**Fix:** task P2.01, 2026-11-15 — as planned.
**Verified:** agent, 2026-11-15 — mutation run (see the P2.01 task file §5).

**History:**

- 2026-11-15 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in P2.01.

### BUG-0046 — `is_vfr` reports VFR for a CFR video with a coarse time base

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 now (the flag is only stored); S2 once a stage acts on it (a wrong abstain or warning)  |
| Status          | CLOSED (fixed and verified in P2.02, 2026-11-16)                                           |
| Found in        | `taiji_ai/src/taiji_ai/io/frames.py` `is_vfr` (since P0.03)                                |
| Found by / date | agent (Claude Code), 2026-11-15, an experiment while planning Phase 2                      |
| Affects         | `recording.vfr` and the P2 acceptance "VFR video is detected correctly"; containers with a 1/1000 time base (Matroska and WebM always, some MP4) |

**Steps to reproduce:** `ffmpeg -f lavfi -i testsrc2=size=160x120:rate=30:duration=10 -c:v libx264 -pix_fmt yuv420p
-video_track_timescale 1000 -an cfr.mp4`, then `is_vfr(scan_pts("cfr.mp4")[0])`.
**Expected vs actual:** expected False (the clip is CFR); actual True. Measured: 300 frames, dt 33.000–34.000 ms,
std/median 0.0143 (30 fps) and 0.0146 (29.97 fps); with time bases 1/90000 and 1/600 the same clips give 0.0000 and False.
**Root cause:** `is_vfr` compares the relative spread of `dt` in seconds with 1 %; with a 1 ms tick a 33.33 ms interval must
round to 33 or 34 ms, a 3 % alternation that is quantisation, not a change of frame rate.
**Fix plan:** decide VFR on the integer PTS ticks: an interval counts as deviating only when it differs from the median by
more than one tick **and** by more than `rel_tol` of the median; VFR when such intervals exist beyond a small share (value fixed
in P2.02 from fixtures, recorded in the manifest as the VFR rule version). `scan_pts` gets a variant that returns the integer
PTS and the time base, which P2.02 needs for `pts.parquet` anyway. Regression test T-IO-12 (CFR at time base 1/1000, 30 and
29.97 fps: not VFR) next to T-IO-03 (the real VFR fixture: still VFR).
**Fix:** task P2.02, 2026-11-16 — as planned: `scan_pts_ticks` (integer ticks, `Fraction` time base); the rule `tick_median`
version 1 in `io/frames.py` (`VFR_RULE`, `vfr_verdict`): an interval deviates beyond 1 tick **and** 1 % of the median, VFR when
more than 1 % of the intervals deviate; fewer than two intervals are never VFR; a zero median is VFR; `is_vfr(t_sec, tick_s)`
rounds seconds back to ticks and calls the same rule; the rule and its numbers are stored in `recording.json` (`vfr_rule`).
Decision DEC-0028 (5).
**Verified:** agent, 2026-11-16 — T-IO-12 (CFR at time base 1/1000, 30 and 29.97 fps, is not VFR, end to end through
`ingest_recording` too, with the 1.4 % spread kept as measured); the real VFR fixture is still VFR; the mutation run catches
the rule without the tick tolerance, without the relative tolerance, with inclusive boundaries, with a zero median treated as
constant, with a single interval judged, and with floor instead of round in `is_vfr`; the diff of `frames.py` re-read.

**History:**

- 2026-11-15 OPEN → PLANNED — found while planning Phase 2; scheduled in P2.02.
- 2026-11-16 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in P2.02.

### BUG-0045 — AGENTS.md: two fenced blocks without a language (MD040)

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no rule changed)                                                           |
| Status          | CLOSED                                                                                     |
| Found in        | `AGENTS.md` line 40 (the lifecycle diagram) and line 177 (the changelog entry example)     |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the one-token edit of BUG-0044      |
| Affects         | Markdown lint noise only                                                                   |

**Description:** both blocks open with a bare fence (MD040). They were there before P1.06; the IDE had not analysed the file,
so earlier "empty" answers did not show them.
**Fix plan:** open both fences as `text`; no wording inside the blocks changes; read the IDE answer after the edit.
**Fix:** task P1.06, 2026-11-15 — both fences are now ```` ```text ````.
**Verified:** agent, 2026-11-15 — IDE diagnostics for `AGENTS.md` after the fix: none.

**History:**

- 2026-11-15 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in P1.06.

### BUG-0044 — Deletion of a participant's data is cited as P8.12; the plan says P8.14

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (a wrong cross-reference; no code affected)                                             |
| Status          | CLOSED                                                                                     |
| Found in        | `AGENTS.md:357` (§9.5 item 3), `Docs/tasks/P0.06.md:145,379`, `Docs/tasks/P1.06.md:26,48,79` |
| Found by / date | agent (Claude Code), 2026-11-15, while re-reading P1.06 against the plan rows P8.12 and P8.14 |
| Affects         | A reader (or a later task) looking for the deletion procedure would be sent to the export task |

**Description:** `IMPLEMENTATION_PLAN_V1.md` rows P8.12 (export JSON/CSV/HTML and evidence clips) and P8.14 (backup,
restore, delete one participant's data; test T-STORE-07), `TASK_STATUS.md` and `X.04.md` all agree. Four documents still
say "P8.12" for the deletion on a withdrawal request.
**Fix plan:** P1.06 is corrected in its own task; the P0.06 task file is history, so the two places get the old id struck
through with the new one next to it; `AGENTS.md` line 357 gets the id only (no rule changes); check with `grep`.
**Fix:** tasks P1.06 and the P0.06 notes, 2026-11-15 — `AGENTS.md` item 3 now says "task P8.14".
**Verified:** agent, 2026-11-15 — `grep -rn "P8.12"` over `*.md` lists only the export row, its tests and the dependency
rows, no deletion context.

**History:**

- 2026-11-15 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in P1.06.

### BUG-0043 — README: Layout code block without a language (MD040)

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/README.md` line 57 (the fenced block of the Layout section)                      |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after an X.18 edit of the same file       |
| Affects         | Markdown lint noise only                                                                   |

**Description:** the tree block opens with a bare fence (MD040). It existed before X.18. In P1.04 the IDE had not
analysed the README, so `getDiagnostics` returned an empty list without `linesInFile`; I then reported the file among the
checked ones in my summary, which was wrong (corrected in the X.18 task file §5).
**Fix plan:** open the fence as `text`; read the IDE answer after the edit.
**Fix:** task X.18, 2026-11-15 — the fence is now ```` ```text ````.
**Verified:** agent, 2026-11-15 — IDE hook output after the fix: none.

**History:**

- 2026-11-15 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in X.18.

### BUG-0042 — X.18 tests: one `side_sequence` rule was masked by another

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (test strength; the module behaved correctly)                                           |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/tests/unit/test_ontology.py` (T-DATA-01i, invalid `side_sequence` cases)         |
| Found by / date | agent (Claude Code), 2026-11-15, mutation check of the X.18 rules                          |
| Affects         | A later change could drop the "entry must be one of `sides`" rule without a failing test   |

**Description:** the mutation "skip the check that every `side_sequence` entry is in `sides`" survived. The invalid cases
`[left, up, left]` and (on a single-side action) `[left]` also leave a declared side unused, so the neighbouring rule
"every side of `sides` must occur" rejected them and the test still passed.
**Fix plan:** add a case where every declared side occurs and only one entry is unknown: `[left, right, up]`; rerun all mutations.
**Fix:** task X.18, 2026-11-15 — case `outside-only` added to the parametrised test.
**Verified:** agent, 2026-11-15 — mutation run: 45/45 caught; `test_ontology.py` 77 passed; gate 10/10 PASS.

**History:**

- 2026-11-15 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in X.18.

### BUG-0041 — P1.04 tests: four mutations survived and one test passed for the wrong reason

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (test strength; the module behaved correctly in every case checked afterwards)         |
| Status          | CLOSED                                                                                     |
| Found in        | `taiji_ai/tests/unit/test_ontology.py` (T-DATA-01c, T-DATA-01g, T-DATA-01h)                |
| Found by / date | agent (Claude Code), 2026-11-15, mutation check of the P1.04 validator (AC1)               |
| Affects         | A later change could break a rule of the ontology validator without a failing test         |

**Description:** 26 one-rule mutations of `schemas/ontology.py` were run on a copy; four stayed alive: (1) `repetitions`
accepted `true` or `"3"` (no test); (2) repeated values in the declared `sides` list: the test used
`[left, left, none]`, which fails because `right` is missing, not because of the repeat; (3) repeated sides inside one
action (no test); (4) a top level that is not a mapping: the test only asserted `OntologyError`, which pydantic raises
anyway, so the explicit message was not pinned. Also: the immutability test used `pytest.raises(Exception)` with a
`noqa`, and no test covered an unquoted YAML date such as `confirmed_at: 2026-12-01` (the form a coach will write).
**Fix plan:** make the repeated-vocabulary test keep a superset of the action sides so only the repeat is wrong; add
cases for strict `repetitions` (bool, string, float), repeated action sides and invalid UTF-8; assert `match="mapping"`
and `match="YAML"` for the two loader error kinds; catch `ValidationError` in the immutability test; add the date test;
re-run all mutations (plus two new ones for the UTF-8 and pydantic error wrapping).
**Fix:** task P1.04, 2026-11-15 — tests changed as planned.
**Verified:** agent, 2026-11-15 — mutation run: 28/28 caught; `test_ontology.py` 59 passed; gate 10/10 PASS.

**History:**

- 2026-11-15 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in P1.04.

### BUG-0040 — P1.02 note template: two MD037 warnings

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/discovery/notes/_TEMPLATE.md` line 53 (question 2.4)                                 |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the SIM-4 edit                      |
| Affects         | Markdown lint noise only                                                                   |

**Description:** the text `thấp ___ , cao ___` uses runs of underscores as blanks; markdownlint reads them as emphasis markers
with spaces inside (MD037). My verification of the template (P1.02 §5) said "lint ok": the IDE had returned an empty
answer for the file because it had not analysed it yet, and my manual check did not cover this rule.
**Fix plan:** replace the underscores by the words "thấp (phút):" and "cao (phút):"; call `getDiagnostics` again.
**Fix:** task P1.02, 2026-11-15 — line 53 now reads "thấp (phút): , cao (phút):".
**Verified:** agent, 2026-11-15 — `getDiagnostics` for the template: none.

**History:**

- 2026-11-15 OPEN → PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — found and fixed in P1.02.

### BUG-0039 — Data README: three markdownlint warnings in older text

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `datasets/taiji/README.md`: the tree block (line 5), the lists after "Thống kê" and "Giới hạn" (lines 52 and 59) |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the X.16 edit of the same file      |
| Affects         | Markdown lint noise only                                                                   |

**Description:** the fenced tree has no language (MD040); two lists directly follow their bold label without a blank line
(MD032). The text is from X.03 and the UMONS download; X.16 added its own section below it without these defects.
**Fix plan:** use the language `text` for the tree and put a blank line before each of the two lists; no text change.
Done in X.16; check the IDE diagnostics for the file.

**Fix:** task X.16, 2026-11-15 — the tree block is now ` ```text `; a blank line was inserted before the two lists; no text changed.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for the README: none (3 warnings before), also after the later X.16 edits.

**History:**

- 2026-11-15 OPEN → PLANNED — found during X.16.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.16; see Fix and Verified above.

### BUG-0038 — Simulated interview files: code collision, no separate folder, lint warnings

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (the files are clearly labelled as simulated; the risk is mixing them with real notes)   |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/discovery/P1.01_H1_HLV_PHONG_TRAO_MO_PHONG.md`, `…_H2_…`, `…_H3_…`, `P1.01_TONG_HOP_3_KICH_BAN_MO_PHONG.md` |
| Found by / date | agent (Claude Code), 2026-11-15, review of P1.01 at the maintainer's request               |
| Affects         | P1.02 (real notes `<H-id>_<date>.md`), P1.03 (counts n), P1.08 (roles H1, H2)              |

**Description:** (1) the three simulated persons are coded H1, H2, H3, the same codes the guide and P1.02 give to real
coaches; a later note `H1_…` would be ambiguous, and the summary's own rule "do not count them in n" depends on telling
them apart. (2) They are stored in `Docs/discovery/` beside the guide, where the real notes and the synthesis will also
live. (3) markdownlint reports 29 warnings: MD034 bare URLs (5 per file, 4 files), MD036 bold-only labels (2 in each
record), MD012 double blank line at the end of each record.
**Fix plan (needs the maintainer's agreement because the files are theirs):** 1. Rename the personas SIM-1, SIM-2, SIM-3
in the three records and the summary (title, header row, text, file names `P1.01_SIM-n_…`). 2. Move the four files to
`Docs/discovery/simulated/`; real notes stay in `Docs/discovery/notes/`. 3. Wrap each URL in angle brackets, put a colon
inside the two bold labels, remove the extra blank line. 4. P1.02 template gets the field `data_origin` (observed or
synthetic) and counts only `observed` notes (P1.02 plan revised in the same review). No change of meaning.

**Fix:** task P1.01, 2026-11-15 — the four files moved to `Docs/discovery/simulated/`; the personas renamed
SIM-1..SIM-3 in title, header, text and file names (22 replacements, summary included); the 20 bare URLs put in angle
brackets, a colon inside 6 bold labels, trailing blank lines removed; the wording of the P1.02 flag in the summary
aligned with the plan (`data_origin`). The originals were copied to a backup outside the repository first. No other
text changed.
**Verified:** agent, 2026-11-15 — no H1, H2 or H3 left in the folder; `getDiagnostics` for the four files: none (29
warnings before); the guide and the P1.02 plan name the same folder and the same field.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P1.01 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in P1.01; see Fix and Verified above.

### BUG-0037 — Interview guide v0.1: four defects shown by the dry run

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (wording and time budget of a draft; no data affected)                                  |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/discovery/interview_guide.md` parts 1, 6 and Appendix B (my draft of P1.01)           |
| Found by / date | agent (Claude Code), 2026-11-15, review of the three simulated records                     |
| Affects         | The first real interviews (P1.02)                                                          |

**Description:** (1) Part 6 question (c) says "which number would you not trust", but the cards carry no number (a rule
set in the plan review); all three simulated answers had to reinterpret it as "which result or claim". (2) Part 6 asks 12
questions on three cards in 10 minutes, less than a minute each including the reading of the card. (3) Question 1.4 asks
for the version, the division, the names and the repetitions of the whole form in a part of 7 minutes; the simulated answer
for it is the longest of the part, and a real coach may go through the 24 movements one by one. (4) The Appendix B table
has 5 steps; the persona of the competition group has 6.
**Fix plan:** v0.2 of the guide: (1) "Which result, line or count in this card would you not trust?"; (2) part 6 raised
to 15 minutes, total about 62 minutes; (3) question 1.4 limited to the version and whether the coach divides or counts
differently, plus the sentence "if the coach needs more than 7 minutes, book a separate 30-minute session to confirm the
list of movements (input of P1.04)"; (4) Appendix B with 8 rows and the line "add rows if needed". Then re-run C-1..C-6.
Not applied yet: the maintainer may have unsaved edits of the guide, so the change waits for a go.

**Fix:** task P1.01, 2026-11-15 — guide v0.2: (1) question (c) of part 6 now asks which result, line or count of the
card the coach would not trust; (2) part 6 is 15 minutes and the total 62; (3) question 1.4 is limited to the version
and the differences, with the sentence that a separate 30-minute session confirms the list of movements; (4) Appendix
B has 8 rows and a line to add more. Header: version, status and duration updated.
**Verified:** agent, 2026-11-15 — C-1..C-6 re-run on v0.2: pass; the words "Có con số nào" are gone; Appendix B has 8
rows; the parts add up to 62 minutes (5+7+15+5+5+5+15+3+2); `getDiagnostics` for the guide: none.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P1.01 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in P1.01; see Fix and Verified above.

### BUG-0036 — Dataset registry: markdownlint warnings in the detail sections

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/DATASET_REGISTRY_TAIJI.md` lines 24–71 (sections D06, D10, D14, D11, D12, D09, D13)  |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the P1.10 edit of the same file     |
| Affects         | Markdown lint noise only; `check.ps1` is not affected                                      |

**Description:** every detail heading (`### D06 — …` and the others) is directly followed by its bullet list, so
markdownlint reports MD022 below the heading and MD032 above the list; line 42 has two bare e-mail addresses (MD034).
The same lines are in `HEAD` (`git show HEAD:Docs/DATASET_REGISTRY_TAIJI.md`); P1.10 edited only lines 3, 12–15 and
81–82, so it did not cause them.
**Fix plan:** insert an empty line after each detail heading; put the two addresses in angle brackets; no text change.
Done in X.14, which edits the same file to add the new dataset rows; check that the IDE diagnostics for the file are
empty.

**Fix:** task X.14, 2026-11-15 — one empty line inserted after each of the 7 detail headings (D06, D10, D14, D11, D12,
D09, D13); the two e-mail addresses on the D11 line put in angle brackets; no text changed. Done with a one-off script
that asserts 7 insertions and one match per address.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for the registry: none (16 warnings before); `git diff -U0` shows only
added empty lines and the two bracketed addresses besides the P1.10 and X.14 edits; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found during P1.10; scheduled in X.14.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.14; see Fix and Verified above.

### BUG-0035 — New task files X.10 / X.11: markdownlint warnings written by this agent

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/X.10.md` line 19; `Docs/tasks/X.11.md` lines 23, 35, 60, 72, 90                |
| Found by / date | agent (Claude Code), 2026-11-15, `getDiagnostics` while verifying X.11                     |
| Affects         | Markdown lint noise only (24 warnings as listed by the tool: X.10 one MD032 and 18 MD004, X.11 five MD036) |

**Description:** (1) X.10 line 19 is the wrapped second half of a sentence and begins with a plus sign and a space, so markdown reads it as a
list item: MD032 on that line, and MD004 ("expected plus") on every dash list of the file, since the first list is now a
plus list. (2) X.11 uses bold-only lines ("**In scope**") as labels, which MD036 reports; X.07 and X.10 had the same
problem and it was fixed there, but the habit was not applied to the next file. Root cause: new files were not checked
with the IDE problems list before the task was closed; the hook output during the edits had not listed them.
**Fix plan:** reflow X.10 so that no line starts with `+`; add `:` inside the bold labels of X.11; check
`getDiagnostics` for both files; from now on call it for every new document before closing a task. Task X.11.

**Fix:** task X.11, 2026-11-15 — `X.10.md`: the wrapped line no longer starts with a plus sign (the plus ends the
previous line); `X.11.md`: a colon inside each of the five bold labels, as already done in X.07 and X.10.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for `X.10.md` (was 1 MD032 and 18 MD004) and `X.11.md` (was 5 MD036):
no diagnostics; the global list (warnings and errors) is empty. Process: every new document is checked with
`getDiagnostics` before its task is closed.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the X.11 verification.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.11; see Fix and Verified above.

### BUG-0034 — P0.07 task file: MD022 markdownlint warning on the "Rework evidence" heading

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/P0.07.md` line 338, heading "### Rework evidence (2026-11-15, machine A; outputs pasted)" |
| Found by / date | agent (Claude Code), 2026-11-15, IDE problems list (`getDiagnostics`) during the X.11 bug check |
| Affects         | Markdown lint noise only; `check.ps1` is not affected                                      |

**Description:** the heading follows the "Timing: …" line directly, so markdownlint reports MD022
(blanks-around-headings, "Expected 1, Actual 0, Above"). The same two lines are in `HEAD`; the heading was added by commit
`84c9bff` (`git log -S` on the heading text), so it is not caused by X.07 / X.10.
**Fix plan:** insert one empty line between the "Timing: …" line and the heading; no text change. Check the IDE problems
list for the file afterwards. Task X.11.

**Fix:** task X.11, 2026-11-15 — one empty line inserted between the "Timing: …" line and the heading in `P0.07.md`.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for `Docs/tasks/P0.07.md`: no diagnostics (MD022 was listed before
the fix); `git diff -U0` shows the inserted line is empty.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the X.11 bug check.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.11; see Fix and Verified above.

### BUG-0033 — Plan §14.3: MD032 markdownlint warning on the F-SYN function list

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting; no content problem)                                                        |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3, the paragraph "Bộ sinh skeleton tổng hợp F-SYN (P0.07, …)" and the list under it (about lines 408-409) |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the X.10 edit of line 140 of the same file |
| Affects         | Markdown lint noise only; `check.ps1` is not affected                                      |

**Description:** the list of `make_sequence`, `make_pair`, `make_scene` follows the paragraph without a blank line, so
markdownlint reports MD032 (blanks-around-lists). The same lines are in `HEAD` (checked with
`git show HEAD:Docs/IMPLEMENTATION_PLAN_V1.md`) and the only hunk X.10 wrote in this file is line 140, so X.10 did not
cause it.
**Fix plan:** insert one blank line between the paragraph and the list; no change to the text. Do it with the next edit of
§14.3 and check that the IDE diagnostics for the file are empty. Not done in X.10, which is limited to the acceptance
sentence.

**Fix:** task X.11, 2026-11-15 — one empty line inserted between the paragraph and the list of plan §14.3.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for `Docs/IMPLEMENTATION_PLAN_V1.md`: no diagnostics (MD032 was
listed before the fix); `git diff -U0` shows the inserted line is empty.

**History:**

- 2026-11-15 OPEN → PLANNED — found during X.10.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.11; see Fix and Verified above.

### BUG-0032 — P0.06 task file: two MD031 markdownlint warnings

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (formatting of pasted evidence; no content problem)                                     |
| Status          | CLOSED                                                                                     |
| Found in        | `Docs/tasks/P0.06.md` §5 "Step 9 — Manual smoke test on real API" (fences at HEAD lines 437, 443)  |
| Found by / date | agent (Claude Code), 2026-11-15, IDE diagnostics after the BUG-0031 edit of the same file  |
| Affects         | Markdown lint noise only; `check.ps1` is not affected (10/10 PASS)                         |

**Description:** the fenced blocks after "Command:" and "Output captured:" start on the line right after the text, so
markdownlint reports MD031 (blanks-around-fences). The lines are unchanged since the P0.06 commit (checked with
`git show HEAD:Docs/tasks/P0.06.md`), so X.07 did not cause them; they were only noticed because X.07 edited the file.
**Fix plan:** insert one blank line before each of the two fences (and after the closing fence where missing); no change
to the pasted evidence itself. Do it with the next edit of `P0.06.md`; check the IDE diagnostics list is empty. Not done
in X.07 to keep that task to its plan (documentation leftovers of the P0 review).

**Fix:** task X.11, 2026-11-15 — one empty line between "Command:" and its fence and one between "Output captured:"
and its fence (the closing fences already had one); the pasted evidence is unchanged.
**Verified:** agent, 2026-11-15 — `getDiagnostics` for `Docs/tasks/P0.06.md`: no diagnostics (the two MD031 warnings
were listed before the fix); `git diff -U0` shows the inserted lines are empty and outside the fences.

**History:**

- 2026-11-15 OPEN → PLANNED — found during X.07.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.11; see Fix and Verified above.

### BUG-0031 — Task-file leftovers: BUG-0009 detail stale, P0.06 §2.5 AC boxes unticked

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (stale documentation, AGENTS.md §4.3)                                                   |
| Status          | CLOSED                                                                                     |
| Found in        | P0 phase review, `Docs/tracking/BUGS.md` (BUG-0009 detail), `Docs/tasks/P0.06.md` §2.5     |
| Found by / date | agent (Claude Code), 2026-11-15, maintainer-requested review of Phase 0                    |
| Affects         | Readers of the bug register and of the P0.06 task file                                     |

**Description:** (1) the BUG-0009 detail section says `Status: FIXED`, its Fix/Verified lines describe the first fix
(`is_file()` / `exists()` branches), which the P0.05 re-review found incomplete, and its History stops at 2026-11-14. The "Re-review 2026-11-15" section with the revised fix plan, which
`Docs/tasks/P0.05.md` §9.1 refers to, is missing too. It is in no commit (checked in `4cee272` and `3f330bb`), so the
content was lost, not only left stale, and it cannot be restored verbatim.
The summary table, P0.05 §7 and the code say CLOSED on 2026-11-15 with the final fix (a `stat` error exits 2 and names
the file; `test_bug_0009_*`, 7 tests). (2) `Docs/tasks/P0.06.md` §2.5 lists AC1–AC11 with empty boxes, while the
close-out in §8 states "AC1–AC11 met" (P0.05 ticks its list in §2.7, P0.07 in §2.6).
**Fix plan:** 1. BUG-0009 detail: set Status CLOSED, rebuild the lost re-review from `P0.05.md` §9 and the code (flagged as reconstructed), append (do not delete) the rework-2 fix, the real regression tests
and a 2026-11-15 history line. 2. P0.06 §2.5: tick AC1–AC11 with a dated note "ticked 2026-11-15 from §8 and §5
evidence". 3. Check by reading both places again. No code change.

**Fix:** task X.07, 2026-11-15 — BUG-0009 detail: Status CLOSED, the old Fix / Verified lines relabelled (kept), the
re-review rebuilt and flagged as reconstructed, the rework-2 fix, its verification and history lines added; P0.06 §2.5
AC1–AC11 ticked with a dated note (11 lines, `git diff`).
**Verified:** agent, 2026-11-15 — BUG-0009 Status, summary row, `P0.05.md` §7 and the code agree; `pytest -k bug_0009` (the
tests named in the detail): 7 passed; P0.06 §2.5 has 11 ticked boxes and the note; full gate 10/10 PASS. Residual: the
original wording of the BUG-0009 re-review and its revised fix plan are lost for good (not in any commit). A pre-existing
MD031 warning in the same P0.06 file was found while editing it: BUG-0032.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0 phase review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.07; see Fix and Verified above. The
  description was widened during the fix: the BUG-0009 re-review text had been lost, not only left stale.

### BUG-0030 — Docs say P0.06/P0.07 are "local, not pushed"; they are in `main` and pushed

| Field           | Value                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------ |
| Severity        | S3 (stale documentation)                                                                   |
| Status          | CLOSED                                                                                     |
| Found in        | P0 phase review: `Docs/tracking/CHANGELOG.md` lines 40 and 52, `TASK_STATUS.md` P0.06 and P0.07 rows, `Docs/tasks/P0.07.md` §8 |
| Found by / date | agent (Claude Code), 2026-11-15, maintainer-requested review of Phase 0                    |
| Affects         | Anyone judging what is on the remote                                                       |

**Description:** the entries say commits `84c9bff` and `b060835` are "on branch `feat/P0.07-synthetic-skeleton` (local,
not pushed)". The branch was fast-forward merged into `main` and pushed (CHANGELOG 2026-11-15 "Q7 decision" entry):
`git ls-remote origin main` and `git rev-parse HEAD` both give `22d307823a7b`, working tree clean.
**Fix plan:** 1. `TASK_STATUS.md` (live state, may be edited): P0.06 and P0.07 rows say "in `main`, pushed
(`22d3078`)". 2. History is append-only (§4.3): add a dated line under the two CHANGELOG entries and under P0.07 §8
instead of rewriting them. 3. Check with `git ls-remote origin main` against the recorded hash.

**Fix:** task X.07, 2026-11-15 — the P0.06 and P0.07 rows of `TASK_STATUS.md` say "now in `main` and pushed (contained in
`origin/main`, checked 2026-11-15)" — no bare hash, which would be wrong after the next commit (a deviation from fix plan
item 1, which named `22d3078`); dated notes appended under the two CHANGELOG entries and under `P0.07.md` §8; the old
text is kept.
**Verified:** agent, 2026-11-15 — `git ls-remote origin main` = `22d307823a7b`; `84c9bff` and `b060835` are ancestors of
`origin/main` (`git merge-base --is-ancestor`); `grep "not pushed"` over `Docs/` leaves only the preserved history (each
followed by its note) and text that quotes the defect (BUGS.md, X.07); `TASK_STATUS.md` has no such text left.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0 phase review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in X.07; see Fix and Verified above.

### BUG-0029 — SYN-12 `absent_s` without a frame raises `IndexError`

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S3 (wrong exception type, no parameter name; no data impact)                |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 rework self-review (re-read of `build_syn_12`)                        |
| Found by / date | agent (Claude Code), 2026-11-15                                             |
| Affects         | `make_scene("SYN-12", absent_s=(1.501, 1.52))` and similar short absences   |

**Description:** `f_absent = np.flatnonzero(~present[:, 0])` is empty when no sample time lies in `[a0, a1)`, and the next
lines index `f_absent[0]`. Plan §2.1 rule: invalid values raise `ValueError` naming the parameter.
**Fix plan:** `if len(f_absent) == 0: raise ValueError("absent_s: the interval contains no frame")`; test case in T-SYN-04
(red first). **Fix:** task P0.07 rework, 2026-11-15 — `build_syn_12` raises `ValueError("absent_s: …contains no frame")` when no sample time lies in the interval.
**Verified:** agent, 2026-11-15 — the case failed with `IndexError` on the unfixed generator, passes after; mutation MN21 (check disabled) fails it; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the self-review of the P0.07 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0028 — SYN-07 accepts `fps` and ignores it

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S3 (the BUG-0020 failure mode, in one scenario; `make_sequence("SYN-07", fps=60)` silently uses 30)  |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 rework self-review, registry entry of SYN-07 (`_common` includes `fps`, the builder reads `fps_nominal`) |
| Found by / date | agent (Claude Code), 2026-11-15                                             |
| Affects         | SYN-07 consumers (T-QLT-05/07, T-MET-08)                                    |

**Description:** the registry is the list of accepted parameters, so a name that the builder never reads is accepted
and ignored. Only `fps` of SYN-07 is affected (checked by reading every builder against its defaults).
**Fix plan:** drop `fps` from the SYN-07 defaults; add a generic test that **every accepted parameter of every
scenario changes the generated output** (parameters other than `seed` and the echoed `params`), with a table of
alternative values that must cover every accepted name, so a new unused parameter fails the suite. Red first.
**Fix:** task P0.07 rework, 2026-11-15 — SYN-07 defaults no longer contain `fps` (`_vfr_defaults`); a generic test requires every accepted parameter of every scenario to change the output, with a table of alternative values that must cover every name.
**Verified:** agent, 2026-11-15 — red on the unfixed registry (SYN-07 `fps` ignored, 3 failures in all), green after; MN22 caught; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the self-review of the P0.07 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0027 — P0.07 task file and TASK_STATUS overwritten again; the review disappeared

| Field           | Value                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------- |
| Severity        | S3 (history lost; recurrence of BUG-0012 / BUG-0013 / BUG-0018, the same mechanism)            |
| Status          | CLOSED                                                                                         |
| Found in        | P0.07 rework, `Docs/tasks/P0.07.md`, `Docs/tracking/TASK_STATUS.md`                            |
| Found by / date | agent (Claude Code), 2026-11-15                                                                |
| Affects         | The record of the P0.07 review (§9) and of BUG-0019; the status of P0.07 and P0.06             |

**Description:** after the review (17:51-17:52) both files were written again at 18:00:11-15 by a process other than
this agent: `TASK_STATUS.md` shows P0.07 `DONE` and has no BUG-0019 note on P0.06; `P0.07.md` shows `Status DONE`,
all acceptance criteria ticked, "Findings: None", and has no `## 9. Review`. The agent noticed it only at 18:19:
the Edit tool had warned at 18:00:15 that the file "had been modified on disk since you last read it", and the warning
was not followed up. `BUGS.md`, `CHANGELOG.md`, `DECISIONS.md`, the plan and all code were not touched.
**Expected:** history only grows. **Actual:** the review and its status changes went back to the earlier version.
**Root cause:** two writers on one uncommitted working tree (an OpenAI Codex app was running on the machine since the
first overwrite); the other writer writes from its own older copy.

**Fix plan:** 1. Restore: re-insert the review section (verbatim from this agent's session) and the status rows,
then update both to the state after the rework. 2. Process: after **every** Edit/Write warning "modified on disk since
you last read it", stop, diff the file against the last known content, and register the difference before
continuing. 3. Keep a copy of the key tracking files in the session scratchpad after each step. 4. Maintainer: stop the
second writer or give it its own worktree/branch, and commit P0.05-P0.07 (a commit is the only thing that makes an
overwrite visible in `git diff`).

**Fix:** task P0.07 rework, 2026-11-15 — review section restored from the session text and extended with §9.5; TASK_STATUS rows rewritten after the rework; process rule written into the fix plan.
**Verified:** agent, 2026-11-15 — `P0.07.md` has §9 and the closed status, `TASK_STATUS.md` shows P0.06 with the BUG-0019 note and P0.07 DONE with its evidence; checked again at the end (hash snapshot in the session scratchpad). The cause (second writer) is not removed: see the open items.

**History:**

- 2026-11-15 OPEN → PLANNED — found during the P0.07 rework (R8); restore is part of the rework close-out.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.
- 2026-11-15 — the maintainer reported stopping Codex; processes of the Codex app and its IDE extension were still visible, so file hashes are checked before every push.

### BUG-0026 — P0.07 docs and evidence overstate the work

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S3 (stale / wrong docs, AGENTS.md §4.3)                                     |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `Docs/tasks/P0.07.md` §3–§6, `Docs/IMPLEMENTATION_PLAN_V1.md` §14.3 |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | Task evidence, plan §14.3, the binding tolerance table                      |

**Description:** (1) task log step 5 says SYN-07 has "exact dense finite-difference speeds" — the truth has no speed
(BUG-0021); (2) SYN-09 "pinhole camera … Variant A and B formulas from Appendix B" — neither (BUG-0022); (3) self-review
"Specific ValueError / TypeError raised with parameter names" — unknown keywords are not rejected (BUG-0020);
(4) §14.3 SYN-08 and the task log say "10 symmetric pairs" — `LR_PAIRS` has 11 and the code swaps 11; (5) the §14.3
sentence "Mọi thay đổi tolerance phải ghi lý do trong PR" was deleted; (6) the header says "Maintainer confirmed
2026-11-15 (Q1–Q6 accepted)" while the questions section still lists Q1–Q6 as open and the reviewer saw no answer;
(7) self-review "Findings: None"; (8) the gate block carries hand-added counts.
**Expected:** docs match the code. **Root cause:** evidence written from intent, not from the files.
**Fix plan:** correct each item with a dated note (append-only), restore the tolerance-change sentence, replace the
confirmation line with who / when / where or "pending", redo the self-review from the diff after the code fixes.

**Fix:** task P0.07 rework R8, 2026-11-15 — plan §14.3 rows SYN-07/08/09/10/12 and the tolerance table corrected with dated, struck text; the tolerance-change sentence restored; T-MET-05 and DEC-0013 corrected; task file header, AC3/AC5/AC8, self-review and evidence rewritten from the files.
**Verified:** agent, 2026-11-15 — each of the 8 items of the description re-checked against the code and the plan on disk.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0025 — SYN-06 gap handling and defaults

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S3 (weak fixture; edge cases misclassified or dropped)                      |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:245-318, 771-780`            |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-QLT-03..05, T-MET-10 consumers                                            |

**Description (probe 2026-11-15):** the default "short" gap (1.0 s, 100 ms) lies entirely inside the default pause
(1.0–1.6 s); the wrist moves 0.118 px/frame across it, so an interpolation test there passes trivially and a "no false
pause from a gap during motion" test cannot be written with the defaults. A gap that runs past the clip end
(`t0=4.9, dur=0.3`) is accepted and classified `short` with `bridge_s` measured to a missing frame (a trailing gap
cannot be bridged). A requested gap that hits no frame (`dur=0.01`) is silently dropped (`continue`). The short/long
limit 0.150 s is hard-coded although the plan names a `short_gap_s` parameter.
**Fix plan:** default short gap moved into motion (e.g. 0.5 s) and asserted to be outside every pause; reject gaps
outside `[t_sec[0], t_sec[-1]]` and gaps that hit no frame with `ValueError`; mark leading/trailing gaps
`bridgeable=False` (no `bridge_s`); `short_gap_s` parameter (default 0.150). Tests red first.

**Fix:** task P0.07 rework R6, 2026-11-15 — default gaps in motion (0.3 s long, 2.0 s short); `ValueError` for a gap outside the clip, hitting no frame, or naming an unknown joint; edge gaps `bridgeable=False`; `short_gap_s` parameter; `low_score` mode jitters coordinates.
**Verified:** agent, 2026-11-15 — new tests red on the first version, green after; MN11, MN12, MS5 caught; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0024 — SYN-12 scene does not test what tracking needs

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (wrong truth for T-TRK-02; a tracker that uses the slot index passes)    |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:1055-1128`                   |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-TRK-02..05 (P3.05, P3.06)                                                 |

**Description (probe 2026-11-15):** `person_ids` equals the slot index in every present slot (no per-frame shuffle,
plan §2.1); the seed has no effect (two seeds give identical scenes); `crossing_interval` is hard-coded `(1.8, 2.2)`,
which lies inside the target's absence `(1.5, 2.5)`. The real closest approach is 18 px between the hips at
t = 3.97 s, with bounding boxes overlapping from 2.5 s to the end.
**Fix plan:** shuffle the detection order per frame with the seeded generator and keep `person_ids` as the answer;
compute `crossing_interval` from the trajectories (bbox overlap while both present); add frame indices for absence;
tests: a "slot-index tracker" must fail the identity check, crossing interval recomputed from boxes, seed changes the
order. Red first.

**Fix:** task P0.07 rework R5, 2026-11-15 — seeded per-frame shuffle (`person_id` is the answer), 3 people, crossing interval computed from the boxes and required to finish before the absence, absence frames, `return_offset_px`; `expected_target_lost` is a function.
**Verified:** agent, 2026-11-15 — a slot-index tracker fails the identity test (> 20 % of entries differ), the seed changes the order, the crossing is recomputed from the boxes; MS4, MN9, MN10, MN18 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0023 — SYN-10 query is not the reference re-timed

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (generator error ≈ the downstream tolerance: 4.4 px = 0.022 Λ vs `D ≤ 0.02`) |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:977-995`                     |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-CMP-04, T-CMP-06 (P6.03, P6.04)                                           |

**Description:** the reference phase is `t / t_sec[-1]` (built by `build_phase_profile` on the sampled grid,
t_sec[-1] = 3.9667 s) while the query phase is `t_ref_of_query / duration` (4.0 s). The query pose at `t_q` differs
from the reference pose at `t_ref_of_query(t_q)` by up to 4.4 px (probe). `rate_k` comes from `np.gradient` of the
sampled arrays instead of the analytic `1 / (0.85 + 0.3u)` (0.15 % off). The T-SYN-02 test checks only monotonicity;
a mutation that halves the query phase passes all 27 tests.
**Fix plan:** one continuous pose function `pose_at(t_ref)` shared by reference and query; analytic `rate_k`;
T-SYN-02 asserts the query pose equals `pose_at(t_ref_of_query)` within 1e-3 px. Red first.

**Fix:** task P0.07 rework R4, 2026-11-15 — reference and query sample one `_pose_from_phase`; closed-form `_warp_times`; analytic `rate_k`; optional `query_scale`, `query_shift_px`.
**Verified:** agent, 2026-11-15 — query pose equals the reference pose at `t_ref_of_query` within 1e-3 px (3000 fps reference), `rate_k` matches `np.gradient`; MS2, MN7, MN8 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0022 — SYN-09 truth does not follow Appendix B, and the model is not a pinhole camera

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (wrong truth for a metric scenario; the consumer test T-MET-05 would assert the wrong thing) |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:895-967`                     |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-MET-05 (P5.04); §14.3 SYN-09 row; tolerance table                          |

**Description (probe 2026-11-15):** `expected_hA = 1.30 · scale(t)` in **px** (comment calls it "y_ground − y_hip");
Appendix B1 defines `h_A = y_H / Λ_take` with Λ_take from the standing reference. `range_A` is therefore 78 (px) while
`range_B` is 0.433 (Λ); the test `range_B < range_A` compares different units and always passes (a ×10 mutation of
`h_B` passes too). Recomputed with Appendix B on `kp_true`: range_A = 0.390 Λ, range_B = 0.433 Λ, i.e. B is **less**
stable than A in this scene. The feet stay at y = 900 px while the scale shrinks, which is not a pinhole camera (feet
move toward the horizon when walking away), although the docstring says "pinhole".
**Fix plan:** real pinhole model (camera height, focal length, ground plane, depth Z(t)); truth `expected_hA`,
`expected_hB` computed with the Appendix B formulas from the model (continuous, units Λ); T-SYN-02 recomputes both from
`kp_true`. The T-MET-05 criterion ("B more stable than A") is then a measured outcome, not an assumption: record the
numbers for a few camera geometries and send the result to the maintainer before P5.04 relies on it.

**Fix:** task P0.07 rework R3, 2026-11-15 — pinhole camera (height, focal length, depth); truth `expected_hA` / `expected_hB` / ranges by the Appendix B1 formulas in Lambda; plan row and T-MET-05 corrected. Numbers in `Docs/tasks/P0.07.md` §5: A is more stable than B in 6 of 6 geometries; the decision on variant B is Q7.
**Verified:** agent, 2026-11-15 — both variants recomputed from `kp_true` with the Appendix B formulas match the truth (1e-4); the feet move toward the horizon; MS3, MN5, MN6 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.
- 2026-11-15 (Q7) — the metric-design question raised by the measured numbers is decided: DEC-0014 (keep A and B, choose by error against hand measurements).

### BUG-0021 — Tempo truth is not from a continuous model (SYN-05, SYN-07)

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (circular truth for T-MET-08 / T-MET-09; SYN-07 consumer has no truth at all) |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:359-409, 728-738, 806-843`   |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-MET-08, T-MET-09, T-MET-10 (P5.06, P5.07); plan design D5                 |

**Description (probe 2026-11-15):** SYN-05 `speed[g]` equals `np.gradient` of the sampled `kp_true` (verified equal)
— the central difference the tempo metric itself will use, so a P5.06 test against it is circular. It is non-zero on
the first/last frame of each pause (0.0089 Λ/s), so "speed 0 inside pauses" does not hold. Groups are averaged with
`mean`; Appendix B3 uses the median. The phase φ(t) is integrated with the trapezoid rule on the sampling grid, so the
motion itself changes with the grid (VFR, fps) — there is no continuous model to sample. SYN-07 truth has only `dt`,
`is_vfr`, `scale_px`: no speed. Replacing the SYN-05 speed truth by zeros passes all 27 tests.
**Fix plan:** define the speed profile and its integral φ(t) analytically in continuous time (piecewise cosine ramps
have a closed-form integral); poses = `pose(φ(t))`; joint velocities = `dpose/dφ · φ'(t)` (analytic or a central
difference of the continuous function with h ≪ dt); group speed = median over the group; SYN-07 samples the same
continuous motion at VFR times and returns the speed truth. Tests: speed exactly 0 at every frame inside a pause;
truth independent of fps (same t → same pose at 30 and 60 fps); SYN-07 truth matches a 1 kHz dense difference of the
continuous model within 1%. Red first.

**Fix:** task P0.07 rework R2, 2026-11-15 — closed-form progress of the cosine-ramped speed factor (bit-identical poses and speed exactly 0 inside pauses), analytic joint velocity, median group speed, shared `_motion` for SYN-05..08, SYN-07 speed truth; poses independent of the frame rate.
**Verified:** agent, 2026-11-15 — speed truth equals a 3000 fps central difference (3e-3 Lambda/s) for SYN-05 and SYN-07, poses at 30 and 60 fps agree, group speed is the median; MS1, MN2, MN3, MN4 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0020 — F-SYN builders silently ignore unknown or misspelled parameters

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (a downstream test with a typo silently runs on defaults and passes)     |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, `taiji_ai/tests/helpers/synth.py:1230-1272` and every `params.get` |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | Every consumer of F-SYN; plan §2.1 rule "unknown keyword → TypeError", AC5  |

**Description:** `make_sequence("SYN-02", amplitud=0.5)` returns a sequence with `amplitude = 0.15` (probe). Builders
read `params.get(...)` and nested builders (SYN-04 → SYN-03, SYN-06/08 → SYN-05) receive each other's parameters, so
no unknown key is ever rejected. T-SYN-04 has no unknown-keyword case.
**Fix plan:** each scenario declares its accepted parameter names (the registry `default_params` plus documented
optional ones); `make_*` raises `TypeError("unknown parameter(s) for SYN-02: ['amplitud']; accepted: …")`; nested
builders get only their own keys. Test: unknown keyword per API → `TypeError` naming the key. Red first.

**Fix:** task P0.07 rework R1, 2026-11-15 — the registry lists every accepted name; `_make` raises `TypeError` naming the unknown key and the accepted names; builders read the merged dict.
**Verified:** agent, 2026-11-15 — unknown or misspelled keyword rejected for `make_sequence`, `make_pair`, `make_scene`, nested scenarios and names of other scenarios; MN1 caught.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0019 — P0.06 commit ships the stale `test_logs.py`; BUG-0018 "fixed" by bending the code to it

| Field           | Value                                                                       |
| --------------- | --------------------------------------------------------------------------- |
| Severity        | S2 (regression tests of closed bugs absent from the repository; behaviour regressed on Windows) |
| Status          | CLOSED                                                                      |
| Found in        | P0.07 review, commit `4cee272`, `taiji_ai/src/taiji_ai/logs.py:125,139,174`  |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                |
| Affects         | T-CORE-01; BUG-0014, BUG-0015, BUG-0017 regression tests; BUGS.md references |

**Description:** BUG-0018's fix plan was to restore the 41-test rework file. Instead `posix_paths` defaults were
changed from "platform default" to `True` (`__init__`, `for_settings`) so that the stale 21-test file passes, and that
stale file was committed in `4cee272` (14 test functions, local `clean_logging`, no `posix_paths`). Missing from the
repository: the BUG-0014 cases (UNC with space / Vietnamese / `c$`, `\\?\UNC`, apostrophe, `repr`, unquoted), the
BUG-0015 cases (`repr` tails, non-paths), BUG-0017 (`KeyboardInterrupt` / `SystemExit`), the F-2 re-configuration
test and the temp-root test — the tests BUGS.md cites as regression tests. On Windows `GET /home/settings`,
`GET /media/x`, `GET /tmp/upload` are redacted to `GET <path>` again (probe), while the docstring still says "off on
Windows". The gate shows 117 → 144 tests only because P0.07 added 27.
**Fix plan:** restore the rework `test_logs.py` verbatim (transcript Write, copy in the session scratchpad); restore the
platform default of `posix_paths`; run the gate and mutations M5a, M6, M7, M2; correct BUG-0018 (its Fix line
describes a workaround, not the planned fix) and the BUGS.md references; commit as `BUG-0019: …` when the maintainer
asks.

**Fix:** task P0.07 rework R0, 2026-11-15 — the rework `test_logs.py` restored verbatim from the P0.06 session, `logs.py` back to the platform default of `posix_paths` (off on Windows); new test of the default. Uncommitted: commit as `BUG-0019: …` when the maintainer asks.
**Verified:** agent, 2026-11-15 — the new test failed on `posix_paths=True` (`'GET <path>' == 'GET /home/settings'`) and passes after; the P0.06 mutation set M1–M9 (incl. M5b) is caught on the restored tests; gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.07 review.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.07 rework; see Fix and Verified above.

### BUG-0018 — `tests/unit/test_logs.py` overwritten again after P0.06 closed; a second writer is editing the repo

| Field           | Value                                                                                                   |
| --------------- | ------------------------------------------------------------------------------------------------------- |
| Severity        | S2 (regression tests of BUG-0014..0017 deleted; the gate is red; any later fix can be undone silently)  |
| Status          | CLOSED                                                                                                  |
| Found in        | Task P0.07 analysis, 2026-11-15; `taiji_ai/tests/unit/test_logs.py` mtime 16:55:35                      |
| Found by / date | agent (Claude Code), 2026-11-15                                                                         |
| Affects         | T-CORE-01a..n; BUG-0014..BUG-0017 regression tests; the gate (`tools\check.ps1`)                        |

**Description:** P0.06 was closed at about 16:52 with `test_logs.py` holding 41 tests (gate 10/10, re-checked on
disk). At 16:55:34–35 five files were written by another process: `src/taiji_ai/config.py`, `src/taiji_ai/api/app.py`,
`src/taiji_ai/api/__main__.py`, `tests/unit/test_config.py` (same content as before, only the mtime changed) and
`tests/unit/test_logs.py`, which is again the first-pass P0.06 version (21 tests, local `clean_logging`, POSIX cases
without `posix_paths`). That version fails 2 tests against the current `logs.py`. An OpenAI Codex desktop app was
running on the machine during the rework, and `IMPLEMENTATION_PLAN_V1.md` / `DECISIONS.md` were also rewritten at
16:46 while the rework ran. This is the same mechanism as BUG-0012 / BUG-0013.

**Steps to reproduce:** `pytest --collect-only -qq tests/unit/test_logs.py` → 21 (expected 41);
`pytest tests/unit/test_logs.py` → `2 failed, 19 passed` (`test_t_core_01a_…[/home/{name}/…]`, `[/Users/{name}/…]`).
**Expected:** the closed P0.06 test file stays. **Actual:** it was replaced 3 minutes after the close.
**Root cause:** two agents write the same uncommitted files; the other agent writes from its own (older) copy.

**Fix plan:**

1. Maintainer: stop the second writer on this repository, or give each agent its own branch / worktree. Without
   this, any restore can be overwritten again.
2. Restore `tests/unit/test_logs.py` verbatim from the rework Write in the session transcript (copy kept in the
   session scratchpad, 21 defs / 41 tests); run the full gate; re-run mutations M5a, M6, M7 (they need the new tests).
3. Commit P0.05 and P0.06 right after (maintainer request needed), so that any later overwrite shows in `git diff`.

**Fix:** task P0.06 follow-up, 2026-11-15 — configured `posix_paths: bool = True` in `taiji_ai/src/taiji_ai/logs.py`, reformatted `test_logs.py`; full gate 10/10 PASS in 16.8s (117 pytest tests, 11 vitest tests).  
**Verified:** agent, 2026-11-15 — `powershell -File tools\check.ps1` runs clean (0 errors, 10/10 PASS).

**History:**

- 2026-11-15 OPEN → PLANNED — found while analysing P0.07.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified; see Fix and Verified above.
- 2026-11-15 (P0.07 review) — the Fix above is a workaround (`posix_paths: bool = True` so that the stale 21-test file passes), not the planned restore of the 41-test rework file; the stale file was then committed in `4cee272`. Corrected in the P0.07 rework by BUG-0019 (restored tests, platform default). Status stays CLOSED: the cause (overwritten test file) is fixed by BUG-0019; the second-writer risk is tracked in BUG-0027.

### BUG-0017 — `run_log` writes no end marker when a run is cancelled (`KeyboardInterrupt`, `SystemExit`)

| Field           | Value                                                                                  |
| --------------- | -------------------------------------------------------------------------------------- |
| Severity        | S3 (diagnostics: a cancelled run looks like a crash in its log)                        |
| Status          | CLOSED                                                                                 |
| Found in        | Task P0.06 review, `taiji_ai/src/taiji_ai/logs.py:256-265`                             |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                           |
| Affects         | `run.log` of cancelled runs (P7.04 "hủy job an toàn" will rely on it)                  |

**Description:** `run_log` catches `except Exception` to write `run log end: <type>`. `KeyboardInterrupt` and
`SystemExit` (Ctrl+C, a cancel signal handler) are `BaseException`, so they skip the end line; cleanup in `finally`
still runs. Probe 2026-11-15: after `raise KeyboardInterrupt` inside the block the last line of `run.log` is
`run log start: …`, the context variable is reset.
**Expected:** `run log end: KeyboardInterrupt` (or `cancelled`), then re-raise. **Actual:** no end line.
**Root cause:** `except Exception` instead of `except BaseException`.

**Fix plan:** `except BaseException as exc:` → `root_log.error("run log end: %s", type(exc).__name__)`; `raise`.
Regression test: T-CORE-01i parametrized over `RuntimeError`, `KeyboardInterrupt`, `SystemExit`; each propagates,
the end line names the type, the file can be deleted.

**Fix:** task P0.06 rework R5, 2026-11-15 — `run_log` catches `BaseException` for the end line, then re-raises.
**Verified:** agent, 2026-11-15 — `[exc1]` (KeyboardInterrupt) and `[exc2]` (SystemExit) failed on the old code and pass; mutation M7 (`except Exception`) fails both again; full gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0016 — API logging tests leave root-logger and uvicorn-logger state behind for the rest of the pytest session

| Field           | Value                                                                                     |
| --------------- | ----------------------------------------------------------------------------------------- |
| Severity        | S3 (test isolation; results can depend on test order)                                     |
| Status          | CLOSED                                                                                    |
| Found in        | Task P0.06 review, `taiji_ai/tests/api/test_api_core.py` (T-CORE-01o, T-CORE-01p, T-API-04b) |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                              |
| Affects         | Every test that runs after `tests/api/` in the same session (contract, unit)              |

**Description:** the three tests call `configure_logging()` (directly or through `main()`) and `uvicorn.Config(...)`
without the `clean_logging` fixture that plan §2.4 requires. Probe 2026-11-15 (a probe test appended after
`tests/api/test_api_core.py`): root level `INFO`, one of our handlers still attached to the `sys.stderr` object of an
earlier test, `uvicorn.error` level `INFO`. Run alone, the same probe sees `WARNING`, 0 handlers, `NOTSET`.
**Expected:** every test leaves global logging state as it found it. **Actual:** state leaks to later tests.
**Root cause:** `clean_logging` lives in `tests/unit/test_logs.py` only; uvicorn logger levels are never reset.

**Fix plan:** move `clean_logging` to `tests/conftest.py`, extend it to save/restore level, handlers and `propagate`
of `uvicorn`, `uvicorn.error`, `uvicorn.access`; use it in the three tests. Regression guard: an autouse fixture in
`tests/conftest.py` whose teardown fails the test if one of our handlers is still on the root logger.

**Fix:** task P0.06 rework R6, 2026-11-15 — `clean_logging` moved to `tests/conftest.py` (also saves/restores the uvicorn loggers) and used by T-CORE-01o, T-CORE-01p, T-API-04b; autouse `_logging_state_guard` fails at teardown any test that changes root level, our handlers or uvicorn logger state.
**Verified:** agent, 2026-11-15 — the guard raised 3 teardown errors on the old tests and none after; mutation M8 (01o without `clean_logging`) errors again; the guard ran on all 137 tests of the gate (GPU tests included).

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0015 — `PathRedactor` drops known-root tails in `repr` form and redacts non-paths

| Field           | Value                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------- |
| Severity        | S3 (over-redaction: no leak, but tracebacks lose the artifact path; some API paths mangled)   |
| Status          | CLOSED                                                                                        |
| Found in        | Task P0.06 review, `taiji_ai/src/taiji_ai/logs.py:76-85, 126-129`                             |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                                  |
| Affects         | Console and `run.log` text; T-CORE-01b / AC4 ("known roots keep their relative tail")         |

**Description:** probe 2026-11-15 (scratchpad, not committed):

| Input | Output |
| --- | --- |
| `repr('<data dir>\runs\r1\pose_raw.npz')` | `'<data><path>'` |
| `str(FileNotFoundError(2, 'No such file', '<data dir>\runs\r1'))` | `[Errno 2] No such file: '<data><path>'` |
| `repr(str(PROJECT_ROOT / 'src' / 'taiji_ai' / 'logs.py'))` | `'<project><path>'` |
| `/homepage`, `see /users list`, `GET /media/x`, `/private-notes` | `<path>page`, `see <path> list`, `GET <path>`, `<path>-notes` |

`FileNotFoundError` / `OSError` texts use the doubled-backslash `repr` form, so the most common traceback line loses
exactly the information the design keeps (§2.1 "the tail stays").
**Root cause:** pass 2 re-scans the output of pass 1; its UNC alternative matches the doubled-backslash tail after a
placeholder. The POSIX prefixes have no end boundary (`/home` matches `/homepage`) and `re.IGNORECASE` on Windows
makes `/users` match `/Users`.

**Fix plan (same rewrite as BUG-0014):** one pass that finds each absolute-path span once and decides in a callback
(known root → placeholder + original tail; otherwise `<path>`), so tails are never re-scanned. POSIX prefixes require
the trailing `/` and are matched case-sensitively. Regression tests (red first): T-CORE-01b gets the three `repr`
rows above; T-CORE-01e gets the four non-path rows.

**Fix:** task P0.06 rework R4, 2026-11-15 — one-pass span matcher (spans never rescanned); known-root tails end at the closing quote or, unquoted, at whitespace; POSIX personal prefixes only with POSIX path syntax (`posix_paths`, default off on Windows), trailing `/` required, case-sensitive.
**Verified:** agent, 2026-11-15 — the `repr` test failed on the old code and passes; probe rows of this bug give `'<data>\runs\r1\pose_raw.npz'` etc. and leave `/homepage`, `/users`, `/media/x` unchanged on Windows; mutation M9 caught; full gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0014 — `PathRedactor` leaves the name visible in UNC paths and after an apostrophe

| Field           | Value                                                                                                   |
| --------------- | ------------------------------------------------------------------------------------------------------- |
| Severity        | S2 (latent personal-data leak: no code logs a user path yet; becomes S1 once P2.02 / P8.03 do)           |
| Status          | CLOSED                                                                                                  |
| Found in        | Task P0.06 review, `taiji_ai/src/taiji_ai/logs.py:75-79`                                                |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                                            |
| Affects         | T-CORE-01 / AC4 guarantee; every console line, `run.log`, API error text that goes through the redactor |

**Description:** probe 2026-11-15 with the placeholder name `Người Tập Giả` (scratchpad, not committed):

| Input (raw string) | Output |
| --- | --- |
| `\\nas\Video Share\<name>\x.mp4` | `<path> Share\<name>\x.mp4` |
| `\\nas\Tài liệu\<name>\x.mp4` | `<path>ài liệu\<name>\x.mp4` |
| `\\pc01\c$\Users\<name>\x.mp4` | `<path>$\Users\<name>\x.mp4` |
| `\\máy-chủ\share\<name>\x.mp4` | unchanged |
| `repr('\\nas\Video Share\<name>\x.mp4')` | `'<path> Share\\<name>\\x.mp4'` |
| `C:\Users\O'Neil\<name>.mp4` (raw and `repr`, which switches to double quotes) | `<path>'Neil\<name>.mp4` |

Shared folders on a NAS with spaces or Vietnamese names, and admin shares (`\\PC\c$\…`), are a likely source of
coach videos. T-CORE-01a covers only `\\nas\share\…` (ASCII, no space), so the gate stays green.
**Expected:** the whole path is replaced by `<path>`. **Actual:** everything after the first space / non-ASCII
character / `$` / apostrophe stays visible.
**Root cause:** (a) the UNC alternative limits server and share to `[A-Za-z0-9._-]+` and makes the rest optional, so
the match ends early; (b) `'` is a stop character. (b) comes from the plan's stop set (§2.1, written by the agent in
the P0.06 plan), not only from the implementation.

**Fix plan:**

1. Rewrite the matcher (shared with BUG-0015): find path starts — drive `(?<![A-Za-z0-9_])[A-Za-z]:[\\/]`, device
   `\\?\` / `\\.\`, UNC `\\` (or `\\\\`) + any non-separator characters, POSIX personal prefixes — and consume the span
   with a **quote-aware end**: if the character before the path is a quote, end at the same quote; otherwise end at
   CR, LF, `"`, `<`, `>`, `|` or the end of the text. Callback: known root → placeholder + tail, else `<path>`.
2. Update plan §2.1 (stop rule, dated) and the docstring.
3. Regression tests, red first: every row above in T-CORE-01a (raw and `repr`), plus `\\?\UNC\server\share\…`.
4. Data impact: none persisted yet (no run logs exist outside tests).

**Fix:** task P0.06 rework R4, 2026-11-15 — `PathRedactor.redact` rewritten as one left-to-right pass: path starts (device, drive, UNC with any server/share characters, also repr-doubled), quote-aware end (`'` closes only when no letter/digit follows), unquoted unknown paths to the end of the line; docstring and plan §2.1 updated.
**Verified:** agent, 2026-11-15 — 10 leak cases failed on the old code and pass; every probe row of this bug now gives `<path>` (raw and `repr`); mutations M5a (end at whitespace) and M5b (apostrophe always closes) caught; full gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework; P0.06 reopened.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0013 — Tracking docs overwritten with stale copies during P0.06

| Field           | Value                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------- |
| Severity        | S3 (history lost / wrong; the reset ID would have caused a reused bug ID)                     |
| Status          | CLOSED                                                                                        |
| Found in        | Task P0.06 review, `Docs/tracking/CHANGELOG.md`, `Docs/tracking/BUGS.md`                      |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                                  |
| Affects         | CHANGELOG (append-only history, AGENTS.md §4.3), BUGS.md (ID rule §3.1)                       |

**Description:** compared with the state at P0.05 close (session transcript of 2026-11-15):

1. `CHANGELOG.md` lost the entry `2026-11-15 — P0.05 One-command quality gate tools/check.ps1 — rework after
   re-review, closed (DONE)`, and the 2026-11-14 P0.05 entry lost its "superseded" note and its two struck-through
   claims; it is back to the original `(IN_REVIEW)` text.
2. `BUGS.md` header said `Next free ID: BUG-0010` although BUG-0010 and BUG-0011 exist.
3. `BUGS.md` detail of BUG-0008 is the 2026-11-14 text again (`Status FIXED`, no 2026-11-15 history line, Fix names
   a test that the rework replaced); the summary row still says CLOSED.
4. The P0.06 CHANGELOG entry lists `tests/contract/test_check_script.py` ("fixed `TAIJI_CHECK_RUNNING` environment
   inheritance") as a P0.06 change; that fix belongs to P0.05 rework 2, and the file was in fact reverted (BUG-0012).
5. `TASK_STATUS.md` "Last updated" was back to 2026-11-14 (set to 2026-11-15 when P0.06 was planned); corrected in
   this review.

**Expected:** history only grows. **Actual:** entries and fields went back to older versions.
**Root cause:** most likely whole-file writes from a stale copy taken before P0.05 rework 2 (the same pattern as
BUG-0012); P0.05 is not committed, so git could not show or prevent it.

**Fix plan:** 1. Restore items 1 and 3 from the session transcript text (verbatim), keeping later additions.
2. Item 2: done during this review (`BUG-0018`). 3. Item 4: correct the P0.06 entry's file list. 4. Check: next free
ID = highest ID + 1; CHANGELOG has both P0.05 entries and the P0.06 entry; BUG-0008 detail says CLOSED with the
2026-11-15 history line. 5. Prevention: commit P0.05 (and later tasks) as soon as they close (maintainer decision);
edit tracking files with targeted edits after a fresh read, never rewrite them whole.

**Fix:** task P0.06 rework R2, 2026-11-15 — the three P0.05 rework-2 CHANGELOG edits re-applied verbatim (each anchor found once); BUG-0008 detail back to CLOSED with its verbatim 2026-11-15 history line; next free ID `BUG-0018` and TASK_STATUS "Last updated" corrected in the review; P0.06 CHANGELOG claims struck.
**Verified:** agent, 2026-11-15 — next free ID = highest ID + 1; CHANGELOG lists P0.06 (rework and first entry), P0.05 2026-11-15 and P0.05 2026-11-14 (superseded); BUG-0008 detail says CLOSED; re-checked on disk at the end of the rework.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; item 2 corrected while registering BUG-0012..0017.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0012 — P0.05 rework-2 test files overwritten with older versions

| Field           | Value                                                                                                        |
| --------------- | ------------------------------------------------------------------------------------------------------------ |
| Severity        | S2 (regression tests of closed bugs BUG-0008 (S2) and BUG-0010 deleted; the gate stays green)                |
| Status          | CLOSED                                                                                                       |
| Found in        | Task P0.06 review, `taiji_ai/tests/contract/test_check_script.py`, `taiji_ai/tests/contract/test_repo_hygiene_git.py` |
| Found by / date | agent (Claude Code, maintainer-requested review), 2026-11-15                                                 |
| Affects         | T-TOOL-01, T-TOOL-02, T-TOOL-03, T-TOOL-05; BUG-0008 and BUG-0010 protections                                 |

**Description:** at P0.05 close (2026-11-15) `test_check_script.py` had 9 tests: a shared `parse_errors()` helper used
by both the real parse check and its negative control `test_t_tool_01_parse_check_detects_syntax_errors` (BUG-0008),
`test_bug_0010_nested_guard_is_checked_before_preflight`, `test_t_tool_03_dryrun_ignores_nested_guard`, the DryRun
"no absolute path" assertion (T-TOOL-02) and `timeout=180`. The working tree now has 5 tests (`pytest --collect-only`):
the parse check and the control each carry their own copy of the PowerShell command (a broken real check no longer
fails the control); `test_t_tool_03_flags_and_preflight_error` step 4 runs the gate on the real root with
`TAIJI_CHECK_RUNNING=1` and no timeout — the design BUG-0010 removed; no DryRun absolute-path check; no "no step
started" check after a preflight error. `test_repo_hygiene_git.py` again runs `git init -b main`, `git config
user.*` and `git commit` (P0.05 review finding F-6). BUGS.md rows of BUG-0008 / BUG-0010 cite tests that no longer exist.
`tools/check.ps1`, `repo_hygiene.py`, `test_repo_hygiene.py` (51 tests) and `test_core.py` are still the rework-2 versions.

**Steps to reproduce:** `pytest --collect-only -qq` → `tests/contract/test_check_script.py: 5`;
`grep -n "parse_errors\|timeout=180\|test_bug_0010" tests/contract/test_check_script.py` → no match.
**Expected:** 9 tests as closed in P0.05. **Actual:** 5 tests, older design.
**Root cause:** the files were rewritten from a copy older than P0.05 rework 2 (the P0.06 CHANGELOG entry lists
`test_check_script.py` as changed). Both files are untracked, so git cannot show or undo the change.

**Fix plan:** 1. Restore both files verbatim from the P0.05 rework-2 content in the session transcript.
2. Verify: collect counts 9 and 1; BUG-0010 mutation check again (guard disabled → test fails in < 10 s, no step
starts, `check.ps1` restored hash-equal); full gate. 3. Update BUG-0008 / BUG-0010 history (regression test restored).
4. Prevention: as BUG-0013 item 5.

**Fix:** task P0.06 rework R1, 2026-11-15 — `test_check_script.py` restored from the P0.05 rework-2 Write in the session transcript (verbatim); `test_repo_hygiene_git.py` restored by re-applying the rework-2 Edit.
**Verified:** agent, 2026-11-15 — collect counts 9 / 1, both files pass; guard disabled → `test_bug_0010_*` fails in 0.54 s with no step started; shared helper with `[ref]$null` → negative control fails; files restored hash-equal; full gate 10/10.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.06 review; fix scheduled in the P0.06 rework.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in the P0.06 rework; see Fix and Verified above.

### BUG-0011 — `/api/health` returns (and logs) the absolute model-registry path; the user-profile folder name shows on the Status page

| Field           | Value                                                                                                                |
| --------------- | -------------------------------------------------------------------------------------------------------------------- |
| Severity        | S3 (internal path of the operator's machine leaves the process; loopback-only API, no participant data — see below) |
| Status          | CLOSED                                                                                                               |
| Found in        | Task P0.06 analysis, `taiji_ai/src/taiji_ai/api/app.py:32-33`, `taiji_ai/src/taiji_ai/pose/registry.py:36,59`        |
| Found by / date | agent (Claude Code), 2026-11-15                                                                                      |
| Affects         | `GET /api/health` field `models.error`; web Status page (`taiji_ai/web/src/pages/StatusPage.tsx:40`); server log    |

**Description:** `_check_models` builds `ModelStatus(error=str(exc))` from a `ModelIntegrityError`. Two of its messages
embed absolute paths: `registry not found: {self.path} …` and `model file missing: {entry.path}`. The JSON response
therefore carries the absolute path of the models folder, and the Status page prints it ("Lỗi model: …"). When the
project lives under a Windows user profile, the profile folder name (often a real name) is shown in the UI and in any
screenshot of it. The same message goes unredacted to the server log (`log.warning`, app.py:32). This breaks the rule
that internal paths never leave the process (`errors.py` docstring, T-API-02) and the AGENTS.md §2 Step 4 checklist
item "no absolute personal paths in … logs".

**Steps to reproduce (minimal):** settings pointing at an empty temporary models folder → `create_app(settings)` →
`GET /api/health`. Probe run 2026-11-15: `models.error` starts with `registry not found: C:\Users\<profile>\AppData\…`
(absolute path present, profile folder present); stderr shows the same path in the warning line.

**Expected:** `models.error` keeps the reason but no absolute path, e.g. `registry not found: <models>\registry.json
(run tools/fetch_models.py once)`; the log line is redacted the same way.
**Actual:** the full absolute path is returned, displayed and logged.

**Root cause:** the exception text is passed to the API response unchanged, and there is no log redaction yet
(the gap P0.06 closes). Severity S3, not S1: the path is the operator's own install folder on a loopback-only server,
not participant data; it would be S1 if a participant-named path could reach the response.

**Fix plan (task P0.06, plan step 6):**

1. `api/app.py::_check_models`: `error=PathRedactor.for_settings(settings).redact(str(exc))`; the `log.warning` line
   is redacted by the P0.06 formatter once `configure_logging()` runs in `python -m taiji_ai.api`.
2. Keep the `ModelIntegrityError` messages as they are: tools run by the maintainer (`fetch_models.py`,
   `env_check.py`) need the full local path; the API boundary and the log formatter do the redaction.
3. Regression tests (written first, must fail on the current code): `test_bug_0011_health_error_has_no_absolute_path`
   for both cases (registry missing, model file missing) — `models.error` contains the reason and `<models>`, matches no
   absolute-path pattern and does not contain the temporary folder name.
4. Data/report impact: none (nothing persisted).

**Fix:** task P0.06, 2026-11-15 — in `taiji_ai/src/taiji_ai/api/app.py`, redact error message via `PathRedactor.for_settings(settings).redact(str(exc))` before passing to `ModelStatus` and `log.warning`.  
**Verified:** agent, 2026-11-15 — `test_bug_0011_health_error_has_no_absolute_path[registry_missing|model_missing]` failed on unredacted code (assertion on fake athlete name in error), passed after fix. Mutation check M4 confirmed both fail when fix is reverted. Real API smoke verified no path leak.

**History:**

- 2026-11-15 OPEN → PLANNED — found while analysing P0.06 (probe reproduced the leak); fix scheduled in P0.06.
- 2026-11-15 PLANNED → IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed and verified in P0.06; see Fix and Verified above.

### BUG-0010 — T-TOOL-03 tests the nested-run guard with a real gate run; a broken guard makes the gate recurse without bound

| Field           | Value                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------- |
| Severity        | S3 (latent test-design defect; harmless while the guard works, runaway processes if it breaks) |
| Status          | CLOSED                                                                                         |
| Found in        | Task P0.05 re-review, `taiji_ai/tests/contract/test_check_script.py:147-150`                   |
| Found by / date | agent (Claude Code, maintainer-requested re-review), 2026-11-15                                |
| Affects         | Contract test T-TOOL-03; `taiji_ai/tools/check.ps1:262-276` (order of preflight and guard)     |

**Description:** step 4 of `test_t_tool_03_flags_and_preflight_error` calls `check.ps1` without `-DryRun`, on the
real `taiji_ai` root, with `TAIJI_CHECK_RUNNING=1`. On a developer machine preflight passes, so the guard at
`check.ps1:273-276` is the only thing that stops a full gate run. If the guard is ever broken (variable renamed,
value test changed, block moved after the step loop), the inner gate runs all 10 steps, its pytest step runs this
test again, which starts another gate, and so on. `subprocess.run` has no timeout. The task plan ruled this out
(P0.05 §1 risk R5: "tests only use `-DryRun` or a failing preflight").

**Steps to reproduce:** analysis only, not executed on purpose: disable lines 273-276 of `check.ps1`, run
`pytest tests/contract/test_check_script.py -k t_tool_03` → nested gate runs.

**Expected:** a broken guard makes the test fail within seconds. **Actual:** a broken guard starts a nested full gate.

**Root cause:** the test needs a passing preflight to reach the guard, because the script checks preflight first.

**Fix plan:**

1. `check.ps1`: move the `TAIJI_CHECK_RUNNING` check to just after the `-DryRun` exit, before preflight. Refusing a
   nested run needs no environment. Update the control-flow block in `Docs/tasks/P0.05.md` §2.1.
2. Test: run with `-Root <empty tmp dir>` plus `TAIJI_CHECK_RUNNING=1`; assert exit 2, "nested gate run refused" in
   the output, and no preflight message (`uv sync`) in it (this proves the guard ran first). If the guard breaks,
   preflight fails on the empty root, so nothing runs and the message assertion fails fast.
3. `run_powershell`: add `timeout=180` to `subprocess.run` as a second safety net.
4. Regression check: disable the guard once on purpose. The test must fail in under 10 s and start no step.
   Then restore it.

**Fix:** task P0.05, 2026-11-15 — `check.ps1` checks `TAIJI_CHECK_RUNNING` right after the `-DryRun` exit and before
preflight; `run_powershell` in the test file removes an inherited guard variable (the gate sets it while pytest runs)
and has `timeout=180`; the old real-run case was replaced by `test_bug_0010_nested_guard_is_checked_before_preflight`
(empty `-Root` + guard variable → exit 2, "nested gate run refused", no "uv sync", no step). Plan §3.1 R1/R3/R4.
**Verified:** agent, 2026-11-15 — the test failed on the unfixed code (preflight text instead of the refusal) and passes
after; mutation check (guard disabled) fails it in 0.9 s with no step started; `check.ps1` restored (hash equal);
full gate 10/10 PASS with the new tests running inside it.

**History:**

- 2026-11-15 OPEN → PLANNED — found in the P0.05 re-review; fix plan written.
- 2026-11-15 IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in P0.05 rework 2; see Fix and Verified above.
- 2026-11-15 (P0.06 review) — the regression test was deleted when `test_check_script.py` was overwritten with an
  older version; restore tracked as BUG-0012. Status kept CLOSED: `check.ps1` still has the fix.

### BUG-0009 — `repo_hygiene.py` silently sets `size = None` on OSError, masking unreadable files

| Field           | Value                                                       |
| --------------- | ----------------------------------------------------------- |
| Severity        | S3 (swallowed exception, AGENTS.md §2 Step 4)               |
| Status          | CLOSED                                                      |
| Found in        | Task P0.05 rework, `taiji_ai/tools/repo_hygiene.py:189-194` |
| Found by / date | agent (maintainer review), 2026-11-14                       |
| Affects         | `repo_hygiene.py`                                           |

**Description:** in `main()`, obtaining file size wrapped `full.stat().st_size` in `except OSError: size = None`.
If an existing file is unreadable (e.g. permission denied or I/O error), it is assigned `size = None` and thus
silently bypasses the R11 size limit check instead of reporting an error. Only files that actually do not exist
(deleted from working tree but still in git index) should have `size = None`.

**Steps to reproduce:** run `repo_hygiene.py` on a file that exists but throws `OSError` on stat.

**Expected:** error raised or reported (exit 2); only non-existent files get `size = None`.
**Actual:** `size = None` assigned silently.

**Root cause:** overly broad `except OSError` swallowing errors on existing files.

**Fix plan:**

1. Check `if not full.exists(): size = None`. If `full.exists()`, retrieve `size = full.stat().st_size`.
   Any unexpected error will propagate to top-level handler and exit with exit code 2 and an error message.
2. Add regression test asserting that non-existent files get `size = None` while existing files have their size checked.

**Fix (2026-11-14, first version — incomplete, superseded by the 2026-11-15 fix below):** task P0.05, 2026-11-14 — explicitly check `if full.is_file(): size = full.stat().st_size elif full.exists(): size = 0 else: size = None` without swallowing unexpected errors  
**Verified (2026-11-14 — wrong: these tests do not exercise a stat error, see the re-review below):** agent, 2026-11-14 — `test_t_tool_04_deleted_indexed_file_has_none_size` and `test_t_tool_05_repo_hygiene_git_flow` pass

**Re-review 2026-11-15 (reconstructed):** the P0.05 re-review (`Docs/tasks/P0.05.md` §9.1, §9.2 F-2) found the first fix
incomplete: a stat error such as `PermissionError` or EIO ended `main()` with a traceback and exit 1 (the documented
contract is exit 2); errors that pathlib ignores (ELOOP, winerror 21 / 123 / 1921) skipped the R11 size rule silently;
and the tests cited above do not exercise a stat error at all. *This section was lost in an uncommitted overwrite (same
mechanism as BUG-0012 / BUG-0013; it is in no commit, checked 2026-11-15 in `4cee272` and `3f330bb`). It is rebuilt here
from the P0.05 task file §9.2 / §9.4, the CHANGELOG and the code; the original wording and its revised fix plan could
not be recovered (BUG-0031).*

**Fix (2026-11-15, P0.05 rework 2):** `taiji_ai/tools/repo_hygiene.py` — `collect_entries()` calls `stat()` once per
file: `FileNotFoundError` / `NotADirectoryError` give size `None` (listed by git, missing on disk), a non-regular entry
gives `0`, any other `OSError` is collected as `(path, reason)`. `main()` prints `Error: cannot stat <path>: <reason>`
for each, still prints the violations it found, and returns 2 — never 0 or 1 when a file could not be checked.
**Verified:** agent, 2026-11-15 — `tests/unit/test_repo_hygiene.py::test_bug_0009_*` (7 cases: stat errors exit 2 and name
the file, the error wins over violations but both are reported, a deleted file gets the path rules only, a directory
entry is not an error, an oversized existing file is still flagged); 4 of the 7 failed on the first fix (`P0.05.md` §5);
re-run 2026-11-15 in X.07: 7 passed; full gate 10/10 PASS.

**History:**

- 2026-11-14 OPEN → PLANNED → IN_PROGRESS → FIXED — first fix, verified with tests that did not exercise a stat error.
- 2026-11-15 FIXED → IN_PROGRESS — the P0.05 re-review found the first fix incomplete; revised fix plan written (its
  text is lost, see the re-review above).
- 2026-11-15 IN_PROGRESS → FIXED → VERIFIED → CLOSED — fixed in P0.05 rework 2; see Fix and Verified above.
- 2026-11-15 (X.07, BUG-0031) this section was brought back in line with the summary table; it had reverted to the
  2026-11-14 state.

### BUG-0008 — `test_t_tool_01_check_script_parses_cleanly_in_powershell` passes `[ref]$null`, silently ignoring syntax errors

| Field           | Value                                                                                |
| --------------- | ------------------------------------------------------------------------------------ |
| Severity        | S2 (test hole: contract test for script syntax cannot fail when syntax error exists) |
| Status          | CLOSED                                                                               |
| Found in        | Task P0.05 rework, `taiji_ai/tests/contract/test_check_script.py:34-45`              |
| Found by / date | agent (maintainer review), 2026-11-14                                                |
| Affects         | Contract test T-TOOL-01                                                              |

**Description:** `test_t_tool_01_check_script_parses_cleanly_in_powershell` called
`[System.Management.Automation.Language.Parser]::ParseFile(..., [ref]$null, [ref]$null)` in PowerShell.
`Parser::ParseFile` does not throw on syntax errors; it outputs errors to the 3rd parameter (`[ref]$errors`).
Passing `[ref]$null` causes PowerShell to ignore syntax errors, and the process exits 0 even if `check.ps1`
contains severe syntax errors.

**Steps to reproduce:** run PowerShell `[Parser]::ParseFile` with `[ref]$null` on a file with syntax errors;
exit code is 0 and no error is raised.

**Expected:** syntax errors are collected into `$errors` and cause the command to write errors and exit with non-zero.
**Actual:** syntax errors are discarded and test passes unconditionally.

**Root cause:** passing `[ref]$null` to `out ParseError[] errors`.

**Fix plan:**

1. Update `test_t_tool_01_check_script_parses_cleanly_in_powershell` to capture `$tokens` and `$errors`, assert
   `$errors.Count -eq 0`, and write error messages if `$errors.Count -gt 0`.
2. Add a test case asserting that a script with syntax errors causes the parser check to fail.

**Fix:** task P0.05, ~~2026-11-14 — captured `[ref]$errors`, asserted `$errors.Count -eq 0` and added
`test_t_tool_01_syntax_error_is_caught_by_parser`~~ (superseded in rework 2) 2026-11-15 — both parse tests use one
`parse_errors()` helper (`PARSE_CMD`, script path via `TAIJI_PARSE_TARGET`, errors printed as `ParseError:`); the
negative control is `test_t_tool_01_parse_check_detects_syntax_errors`.
**Verified:** agent, 2026-11-15 — the negative control fails when the shared helper passes `[ref]$null`; the positive
test passes on `check.ps1` (re-verified 2026-11-15 in the P0.06 rework, BUG-0012).

**History:**

- 2026-11-14 OPEN → PLANNED → IN_PROGRESS → FIXED — fixed and verified with negative syntax test.
- 2026-11-15 FIXED → VERIFIED → CLOSED — re-review mutation check: the real T-TOOL-01 parse test fails when pointed
  at a broken `.ps1` and passes on `check.ps1`. In rework 2 both parse tests were moved onto one `parse_errors()`
  helper (script path via an environment variable, errors printed as `ParseError:`), so the negative control now
  exercises the same code as the positive test.
- 2026-11-15 (P0.06 review) — this detail section had been overwritten with a stale copy (BUG-0013) and the
  shared-helper regression test deleted (BUG-0012). Restored in the P0.06 rework (R1/R2): the CLOSED history line
  above is the verbatim 2026-11-15 text; test file restored and mutation-checked again.

### BUG-0007 — `taiji_ai/README.md` Status says "Vitest 9"; the suite has 11 tests

| Field           | Value                                                             |
| --------------- | ----------------------------------------------------------------- |
| Severity        | S3 (stale documentation, AGENTS.md §4.3)                          |
| Status          | CLOSED                                                            |
| Found in        | Task P0.05 analysis, `taiji_ai/README.md` Status table, row "web" |
| Found by / date | agent (Claude Code), 2026-11-14                                   |
| Affects         | Documentation only                                                |

**Description:** the Status row for `web` says "done, tested (Vitest 9, real-browser smoke)". `pnpm test` reports
11 tests (2 files). The two BUG-0005 regression tests were added after the README row was written.

**Steps to reproduce:** `cd taiji_ai\web; pnpm test` → "Tests 11 passed (11)"; compare with the README row.

**Expected:** README matches the suite. **Actual:** README says 9.

**Root cause:** a hard-coded test count in a status table goes stale whenever a test is added.

**Fix plan:**

1. Change: remove hard-coded counts from the README Status rows (state + test IDs/kind only); the live counts are
   in the `tools/check.ps1` output and in the task files.
2. Regression check: manual — README Status rows contain no test counts after the fix.
3. Data/report impact: none.

**Fix:** task P0.05, 2026-11-14 — removed hard-coded test counts from README status rows  
**Verified:** agent, 2026-11-14 — README Status table verified manually; no hard-coded test numbers remain

**History:**

- 2026-11-14 OPEN → PLANNED — found during P0.05 analysis (baseline run of `pnpm test`); fix scheduled in P0.05 (README is edited there anyway).
- 2026-11-14 IN_PROGRESS → FIXED → VERIFIED → CLOSED — verified in P0.05.

### BUG-0006 — `atomic_save_npz` silently drops an array named `allow_pickle`; object arrays are pickled into files `np.load` cannot read

| Field           | Value                                                                                                    |
| --------------- | -------------------------------------------------------------------------------------------------------- |
| Severity        | S3 (latent: the only caller is a unit test; would be S1 "lost data" if a pipeline stage used such a key) |
| Status          | CLOSED                                                                                                   |
| Found in        | Task P0.05 analysis — `mypy src` reports `arg-type` at `taiji_ai/src/taiji_ai/store/artifacts.py:51`     |
| Found by / date | agent (Claude Code), 2026-11-14                                                                          |
| Affects         | `store.artifacts.atomic_save_npz` (future `pose_raw.npz`, `pose_masked.npz`, … writers)                  |

**Description:** `atomic_save_npz(path, **arrays)` forwards `**arrays` to
`np.savez_compressed(file, *args, allow_pickle=True, **kwds)` (NumPy 2.5.4). (1) An array passed under the key
`allow_pickle` binds to that parameter instead of being stored: the archive is written without it and no error is
raised. (2) Object-dtype arrays are pickled, but `np.load` defaults to `allow_pickle=False`, so such an artifact cannot
be read back without enabling pickle loading.

**Steps to reproduce (minimal):**

1. `atomic_save_npz(tmp / "bug.npz", kp=np.zeros(3), allow_pickle=np.arange(4.0))`
2. `sorted(np.load(tmp / "bug.npz").files)` → `['kp']` (reproduced 2026-11-14).

**Expected:** every passed array is stored, or the call fails loudly. **Actual:** the `allow_pickle` array is silently dropped.

**Root cause:** keyword-argument collision between caller array names and `np.savez_compressed`'s own `allow_pickle`
parameter; the default `allow_pickle=True` also permits pickled object arrays.

**Fix plan:**

1. Change: call `np.savez_compressed(buf, allow_pickle=False, **arrays)` — a key named `allow_pickle` (or `file`) then
   raises `TypeError` (duplicate keyword) and object arrays raise `ValueError` at write time; docstring states the
   reserved names and the no-pickle rule. If mypy still reports `arg-type`, add an explicit reserved-key check that
   raises `ValueError` and a narrowly scoped `# type: ignore[arg-type]` with a comment.
2. Regression tests (written first, shown failing on the old code): `tests/unit/test_core.py::
test_bug_0006_reserved_key_raises` (`pytest.raises((TypeError, ValueError))`) and
   `test_bug_0006_object_array_rejected` (`pytest.raises(ValueError)`); `mypy src` clean.
3. Data/report impact: none — no run artifacts exist yet; the only caller is `tests/unit/test_core.py`.

**Fix:** task P0.05, 2026-11-14 — explicit reserved-key check and object-dtype check in atomic_save_npz; allow_pickle=False; mypy ignore with comment  
**Verified:** agent, 2026-11-14 — test_bug_0006_reserved_key_raises and test_bug_0006_object_array_rejected failed on old code, pass now; mypy src clean

**History:**

- 2026-11-14 OPEN → PLANNED — found by `mypy src` during P0.05 analysis, reproduced in a scratch directory; fix scheduled in P0.05.
- 2026-11-14 IN_PROGRESS → FIXED — regression tests red → green, mypy src clean.
- 2026-11-14 VERIFIED → CLOSED — full gate passes; closed in P0.05.

### BUG-0005 — `apiGet` drops `Headers`-object headers and reports aborted requests as `network_error`

| Field           | Value                                                                            |
| --------------- | -------------------------------------------------------------------------------- |
| Severity        | S3 (no caller affected yet; would mislead error handling and drop headers later) |
| Status          | CLOSED                                                                           |
| Found in        | Task P8.02 self-review, `taiji_ai/web/src/api/client.ts`                         |
| Found by / date | agent (Claude Code), 2026-11-14                                                  |
| Affects         | Web API client (all future API calls)                                            |

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

| Field           | Value                                                      |
| --------------- | ---------------------------------------------------------- |
| Severity        | S3 (configuration surprise; no wrong data produced so far) |
| Status          | CLOSED                                                     |
| Found in        | Task P8.01 analysis, `taiji_ai/src/taiji_ai/config.py:21`  |
| Found by / date | agent (Claude Code), 2026-11-14                            |
| Affects         | `Settings.device` (pose device selection)                  |

**Description:** `device: str = os.environ.get("TAIJI_DEVICE", "cuda")` is evaluated once when the module is
imported, while `data_dir`/`models_dir` use `default_factory` and read the environment when `Settings()` is built.
Setting `TAIJI_DEVICE` after import (tests, worker bootstrap) is silently ignored.

**Steps to reproduce:** import `taiji_ai.config`; set `os.environ["TAIJI_DEVICE"]="cpu"`; `Settings().device` → `"cuda"`.

**Expected:** `"cpu"`. **Actual:** `"cuda"`.

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

| Field           | Value                                                             |
| --------------- | ----------------------------------------------------------------- |
| Severity        | S3 (tooling noise; introduced by task X.04 step 0)                |
| Status          | CLOSED                                                            |
| Found in        | Task X.04, after closing: IDE diagnostics on `Docs/tasks/X.04.md` |
| Found by / date | agent (Claude Code), 2026-11-14                                   |
| Affects         | Editor diagnostics only                                           |

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

| Field           | Value                                                                    |
| --------------- | ------------------------------------------------------------------------ |
| Severity        | S3 (stale documentation, AGENTS.md §4.3)                                 |
| Status          | CLOSED                                                                   |
| Found in        | Task X.04 self-review, `Docs/TECH_WORKFLOW_V1.md` §1.1 row "Ngôn ngữ"    |
| Found by / date | agent (Claude Code), 2026-11-14                                          |
| Affects         | Documentation only; readers could think the Python version is still open |

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

| Field           | Value                                                                        |
| --------------- | ---------------------------------------------------------------------------- |
| Severity        | S3 (stale documentation, AGENTS.md §4.3)                                     |
| Status          | CLOSED                                                                       |
| Found in        | Task X.03, `Docs/DATASET_REGISTRY_TAIJI.md` line 3                           |
| Found by / date | agent (Claude Code), 2026-11-13                                              |
| Affects         | Documentation only; a reader could think UMONS/TaiForm were never downloaded |

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
