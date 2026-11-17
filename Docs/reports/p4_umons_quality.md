# P4.08 — The quality chain on the UMONS Kinect recordings

Date: 2026-11-17. Task: `Docs/tasks/P4.08.md`; **re-run after X.31** (`Docs/tasks/X.31.md`, DEC-0052: the grid follows the lattice of the clock and a row within 1 ms of a grid time is a copy). The first version of this report, written before X.31, measured 96.5 % mixed grid rows; its numbers are kept below where they are compared. The plan asks (T-QLT-12) that a sequence of 4,000+ frames runs through the quality layer without error and that the coverage is reasonable. Numbers only: no value of a file is stored in the repository (`datasets/` is read-only, CC BY-NC-SA 4.0, tag `dev-test`).

**Read this first.** The footage is **UMONS-TAICHI (D12): Kinect V2 skeleton recordings** of 12 performers doing 13 techniques, **not** the 24 forms and **not** video pose. It is out of domain for any product number (AGENTS.md 9.4.4) and the 98.0 % below is **not a quality of the pose**: the Kinect output is a complete skeleton at every frame, with no confidence value, no tracking state and no NaN, so the mask and the gap layer have almost nothing to do on it. What this run really exercises is **the grid on real sensor clocks, the filter on runs of thousands of rows, the swap flag and Hampel on another sensor's errors, and the report on 700,000 rows**. The adapter makes three conventions that are stated here and in `taiji_ai/src/taiji_ai/bench/umons.py`: the plane (y, -z) in mm is read as pixels (the stages are scale-free), a joint the file reports gets the score 1.0 ("reported", not a probability), and a repeated timestamp is two bodies in one frame and is not tracked.

## Summary

- **Nothing breaks.** 111 of 111 files (703,146 rows, up to 11,790 per file, 104 files with 4,000 or more) ran through `run_quality_arrays` with the default parameters: no error, the partition of the report holds for every file. The whole run takes **30.5 s (0.43 s per 10,000 rows)**; `quality.json` of the longest sequence is 13,921 bytes and its round trip is equal.
- **No Kinect clock is uniform**, so the non-identity grid of P4.04 runs on every file: the first real variable-frame-rate data of the project. The steps are 33 or 34 ms (milliseconds, rounded) except **19,148 steps of dropped frames** (more than 1.5 median steps, up to the 150 ms limit) and **275 pauses of more than 150 ms** (largest 0.733 s). The pauses become NaN `no_frame` cells (40,794 cells, 54 files) and are never bridged.
- **Two bodies in one frame, one file.** The 31 repeated timestamps are all in `P04T02C03`, in its last 62 rows: the rows alternate between two skeletons about 650 mm apart. The file does not say which is the performer, so those frames are not tracked (31 grid frames), never bridged; their gaps are open at the end of the file (the report counts them as `open_end`).
- **Nine of the 26 HALPE joints do not exist in Kinect** (nose, eyes, ears, small toes, heels): 34.5 % of all cells are missing for that reason. Over the **17 joints Kinect has**: **98.04 % observed, 1.666 % bridged, 0.295 % missing** on the grid (96.80 / 2.857 / 0.344 % before X.31: a mixed cell built on a bridged cell is itself flagged bridged, so fewer mixes mean fewer bridged cells); on the rows of the files 1.57 % of those cells are bridged. Usable frames 99.78 %; per file the lowest is `P09T02C02` (92.00 %), and that performer's files hold 122 of the 275 pauses.
- **Hampel flags 194,214 cells of the 17 joints on the rows of the files (1.62 %; per file 0.66 to 3.02 %)**, concentrated on the distal and foot joints: wrists 3.9 to 4.2 %, big toes 3.8 to 4.3 %, elbows 2.2 to 2.4 %, knees and ankles 1.3 to 1.6 %, shoulders 0.24 %, hips, neck and head at most 0.17 %. On the D20 video pose the same stage flagged 0.19 % of all cells (M-QLT-07); here it is 1.06 % of all 26-joint cells. There is **no ground truth** for these cells: whether they are spikes or the jitter of the Kinect's distal joints is not decided here. 96.7 % of them are bridged (the gap layer filled 187,902 cells in 160,280 gaps).
- **The grid now follows the clock (X.31).** The default chain fits the lattice of each clock: a step that counts the frames of every interval (33.331 to 33.3335 ms in every file; the plain mean interval would be 34 to 47 ms because every dropped frame is one more step) and the phase of the longest regular run, and a grid time within 1 ms of a row is that row. **91.0 % of the grid rows are copies of a real row** (0.02 % at the exact time, 90.98 % within 1 ms; before X.31: 3.2 %), **8.79 % are linear mixes** (96.51 % before) and 0.22 % are pauses (NaN, `no_frame`). A snapped copy holds the value of a row up to 1 ms away from its grid time (median 0.33 ms, 95th percentile 0.80 ms); against the straight line between its two neighbouring rows that is a difference of **0.013 mm (median), 0.25 mm (95th percentile), 0.76 mm (99th) on a joint, 0.054 % of the torso at the 95th percentile**: far below the 0.94 % of the torso that a round trip through the grid costs on video pose (M-QLT-04). The way back has no value for the first row of 26 files and the last row of 11 files (26 + 11 of 703,115 rows): they lie more than 1 ms outside the lattice. With the nominal 30 Hz grid anchored at the first row (`grid_hz` = 30, the old side measurement) 22.0 % are exact copies, 48.2 % snapped copies and 29.55 % mixes: the fitted phase is worth 20 points.
- **Eleven files keep more than 20 % mixed rows** (up to 78.7 %) and hold 54 % of all mixed rows: their timestamps wander up to 70 ms around any straight lattice (runs of 33 ms steps followed by runs of 34 ms steps, with no dropped frame in some of them, e.g. `P03T02C08`), so those rows are not on a regular clock and the mix is correct. That is a property of the sensor's clock and not a defect; a grid that follows a wandering phase would need a different filter input and is not planned.
- **Swap flag:** 9 warnings in 7 files, 6 `suspect` and 24 `blocked` cells in all: the Kinect's left/right flips are rare in this data. There is no label to say whether they are real.

## Method

- **Data.** `datasets/taiji/umons/extracted/Kinect`: 111 files `PxxTxxCxx.txt`, found and checked by `find_umons` (exactly 111 files, a `License.txt` naming CC BY-NC-SA 4.0). A row is a timestamp in ms and 25 joints x (x, y, z) in mm, Kinect V2 `JointType` order (checked on the data: the spine joints climb the vertical axis, the left joints lie on one side of the spine and the right ones on the other; the depth axis is x and the plane (y, z) keeps 97 to 100 % of the 3D torso, median 99.5 %; the median torso per file is 434 to 539 mm).
- **Adapter** (`bench/umons.py`, `parse_kinect`): strict reader (76 finite numbers per row, a timestamp that decreases is an error); seconds from the first row, nothing regularised; 17 HALPE joints (the foot as the big toe, an approximation), nine absent (NaN, `non_finite`), the Kinect spine mid, spine shoulder, hands, hand tips and thumbs dropped; position (y, -z); score 1.0 for a reported joint, 0.0 and the file's value for a joint at (0, 0, 0) (12 cells in one file, `P01T02C07`, at its end; the mask turns them into `low_conf`); the first row of a repeated timestamp kept as not tracked.
- **Chain.** `run_quality_arrays` with `QualityParams()` for the baseline ("default") and with `grid_hz` = 30 for the side measurement; the segment is the whole sequence. All numbers come from `QualityReport` (the partition is guaranteed by the schema's validators) plus the adapter's counts and, for Hampel per joint, the result's outlier mask on the rows of the files.
- **Reproduce:** `python tools/umons_adapter.py run --umons ../datasets/taiji/umons --out data/reports/p4_08 --grid-hz 30 --report data/reports/p4_08/report_tables.md` (about 60 to 90 s for both runs); the tables below are that file. `per_file.csv` holds one row per file (counts only) and stays in `data/` (ignored by git).
- **Tests:** `tests/unit/test_umons_adapter.py` (text made in the tests), `tests/contract/test_umons_tool.py` (the tool in a subprocess), `tests/golden/test_umons_quality.py` (six real files: the longest, the two bodies, a 733 ms pause, the lowest coverage, the zero joints, the swap warnings; `dataset` marker, skipped when the data is absent).

## Results

#### Run

| Measure | default | grid 30 Hz |
|---|---|---|
| Files that ran / failed | 111 / 0 | 111 / 0 |
| Rows in the files | 703,146 | 703,146 |
| Rows after repeated timestamps | 703,115 | 703,115 |
| Repeated rows dropped / timestamps with two bodies | 31 / 31 | 31 / 31 |
| Cells of the 17 joints at (0, 0, 0) | 12 | 12 |
| Steps of dropped frames / pauses over 150 ms | 19,148 / 275 | 19,148 / 275 |
| Largest step [s] | 0.733 | 0.733 |
| Grid rows (files resampled) | 725,859 (111) | 725,925 (111) |
| Mixed grid rows | 63,770 (8.79 %) | 214,540 (29.55 %) |
| Usable frames | 99.78 % | 99.77 % |
| Not tracked frames | 31 (0.004 %) | 31 (0.004 %) |
| Cells, 26 joints: observed | 64.10 % | 63.91 % |
| Cells, 26 joints: bridged | 1.089 % | 1.273 % |
| Cells, 26 joints: missing | 34.81 % | 34.81 % |
| Cells, the 17 provided joints: observed | 98.04 % | 97.75 % |
| Cells, the 17 provided joints: bridged | 1.666 % | 1.947 % |
| Cells, the 17 provided joints: missing | 0.295 % | 0.302 % |
| Filtered cells / usable cells not filtered | 65.13 % / 10,928 | 65.13 % / 11,118 |
| Swap cells suspect / blocked; warnings | 6 / 24; 9 | 6 / 24; 9 |
| Bridged cells on the rows of the files, 17 joints (gap table) | 187,902 (1.57 %) | 187,902 (1.57 %) |
| Hampel cells of the 17 joints (rows of the files) | 194,214 (1.62 %) | 194,214 (1.62 %) |
| Seconds, chain and report | 30.5 | 30.3 |

#### Cells by reason: all cells whose reason is not ok (missing in brackets)

| Reason | default | grid 30 Hz |
|---|---|---|
| low_conf | 12 (12) | 12 (12) |
| non_finite | 6,518,331 (6,518,331) | 6,518,619 (6,518,619) |
| not_tracked | 806 (806) | 806 (806) |
| frame_invalid | 10 (10) | 10 (10) |
| outlier | 214,697 (9,155) | 249,778 (9,503) |
| no_frame | 40,794 (40,794) | 41,678 (41,678) |

#### Gaps of the rows of the files by outcome (cells inside the segment)

| Outcome | default | grid 30 Hz |
|---|---|---|
| filled | 160,280 (187,902) | 160,280 (187,902) |
| too_long | 2,085 (6,300) | 2,085 (6,300) |
| never_fill | 0 (0) | 0 (0) |
| blocked | 9 (12) | 9 (12) |
| open_start | 0 (0) | 0 (0) |
| open_end | 34 (549) | 34 (549) |
| open_both | 999 (6,328,035) | 999 (6,328,035) |

#### Hampel: cells set to NaN, by joint of the 17 provided (share of the rows of the files)

| Joint | default | grid 30 Hz |
|---|---|---|
| LShoulder | 1,693 (0.24 %) | 1,693 (0.24 %) |
| RShoulder | 1,726 (0.25 %) | 1,726 (0.25 %) |
| LElbow | 17,062 (2.43 %) | 17,062 (2.43 %) |
| RElbow | 15,189 (2.16 %) | 15,189 (2.16 %) |
| LWrist | 29,452 (4.19 %) | 29,452 (4.19 %) |
| RWrist | 27,159 (3.86 %) | 27,159 (3.86 %) |
| LHip | 1,187 (0.17 %) | 1,187 (0.17 %) |
| RHip | 1,121 (0.16 %) | 1,121 (0.16 %) |
| LKnee | 9,225 (1.31 %) | 9,225 (1.31 %) |
| RKnee | 9,907 (1.41 %) | 9,907 (1.41 %) |
| LAnkle | 10,263 (1.46 %) | 10,263 (1.46 %) |
| RAnkle | 11,327 (1.61 %) | 11,327 (1.61 %) |
| Head | 697 (0.10 %) | 697 (0.10 %) |
| Neck | 885 (0.13 %) | 885 (0.13 %) |
| Hip | 834 (0.12 %) | 834 (0.12 %) |
| LBigToe | 26,457 (3.76 %) | 26,457 (3.76 %) |
| RBigToe | 30,030 (4.27 %) | 30,030 (4.27 %) |

#### Per file, default: min / p10 / median / max

| Measure | Value |
|---|---|
| Usable frames | 92.00 / 99.63 / 100.00 / 100.00 % |
| Usable cells of the 17 joints | 91.62 / 99.54 / 99.91 / 100.00 % |
| Mixed grid rows | 0.07 / 0.31 / 3.17 / 78.67 % |
| Hampel cells of the 17 joints | 0.66 / 0.95 / 1.48 / 3.02 % |
| Torso in the plane [mm] | 434 / 440 / 452 / 539 mm |
| Step of the grid [ms] | 33.33 / 33.33 / 33.33 / 33.33 ms |

#### Files worth naming, default

| What | Sequence ids |
|---|---|
| ambiguous | P04T02C03 |
| zero_joint | P01T02C07 |
| no_frame | 54 files, the first 10: P01T01C03, P01T02C07, P02T01C04, P02T01C05, P02T02C05, P02T02C06, P02T02C09, P02T02C10, P03T01C04, P03T02C02 |
| swap | P01T02C04, P01T02C05, P07T02C02, P07T02C04, P08T02C04, P12T02C03, P12T02C05 |
| longest | P08T03C01 |
| largest_step | P02T02C09 |
| lowest_provided | P09T02C02 |
| lowest_usable_frames | P09T02C02 |
| most_outliers | P02T02C10 |

#### Per file, grid 30 Hz: min / p10 / median / max

| Measure | Value |
|---|---|
| Usable frames | 92.00 / 99.63 / 100.00 / 100.00 % |
| Usable cells of the 17 joints | 91.62 / 99.53 / 99.90 / 100.00 % |
| Mixed grid rows | 0.07 / 0.30 / 3.65 / 99.97 % |
| Hampel cells of the 17 joints | 0.66 / 0.95 / 1.48 / 3.02 % |
| Torso in the plane [mm] | 434 / 440 / 452 / 539 mm |
| Step of the grid [ms] | 33.33 / 33.33 / 33.33 / 33.33 ms |

#### Files worth naming, grid 30 Hz

| What | Sequence ids |
|---|---|
| ambiguous | P04T02C03 |
| zero_joint | P01T02C07 |
| no_frame | 54 files, the first 10: P01T01C03, P01T02C07, P02T01C04, P02T01C05, P02T02C05, P02T02C06, P02T02C09, P02T02C10, P03T01C04, P03T02C02 |
| swap | P01T02C04, P01T02C05, P07T02C02, P07T02C04, P08T02C04, P12T02C03, P12T02C05 |
| longest | P08T03C01 |
| largest_step | P02T02C09 |
| lowest_provided | P09T02C02 |
| lowest_usable_frames | P09T02C02 |
| most_outliers | P02T02C10 |

#### Per participant (default run; counts from `per_file.csv`)

| Performer | Files | Rows | Usable frames | Usable cells of the 17 joints | Mixed grid rows | Hampel cells (17 joints) | `no_frame` cells | Pauses | Swap warnings |
|---|---|---|---|---|---|---|---|---|---|
| P01 | 8 | 44,316 | 99.98 % | 99.93 % | 1.4 % | 1.79 % | 234 | 2 | 2 |
| P02 | 9 | 61,201 | 99.63 % | 99.51 % | 7.1 % | 1.99 % | 6,214 | 36 | 0 |
| P03 | 18 | 109,661 | 99.98 % | 99.93 % | 5.9 % | 1.88 % | 468 | 4 | 0 |
| P04 | 7 | 40,235 | 99.86 % | 99.81 % | 9.8 % | 1.85 % | 650 | 5 | 0 |
| P05 | 9 | 45,174 | 99.83 % | 99.78 % | 3.1 % | 1.15 % | 2,028 | 13 | 0 |
| P06 | 7 | 40,665 | 99.87 % | 99.84 % | 1.7 % | 1.22 % | 1,430 | 9 | 0 |
| P07 | 9 | 43,919 | 99.84 % | 99.76 % | 11.3 % | 1.48 % | 1,924 | 16 | 4 |
| P08 | 8 | 54,943 | 99.92 % | 99.84 % | 17.1 % | 1.77 % | 1,170 | 10 | 1 |
| P09 | 7 | 42,394 | 98.36 % | 98.26 % | 6.1 % | 1.20 % | 19,136 | 122 | 0 |
| P10 | 10 | 79,702 | 99.99 % | 99.95 % | 17.9 % | 1.31 % | 156 | 1 | 0 |
| P11 | 9 | 68,013 | 99.86 % | 99.76 % | 4.5 % | 1.92 % | 2,496 | 20 | 0 |
| P12 | 10 | 72,892 | 99.76 % | 99.66 % | 13.7 % | 1.53 % | 4,888 | 37 | 2 |

The pauses and the `no_frame` cells are concentrated in one performer's files (`P09`: 122 of 275 pauses, 19,136 of 40,794 cells): the sensor's dropped frames are not spread evenly over the sessions.

## What this shows, and what it does not

- **It shows** that the six stages and the report hold on long, real, imperfect data of a different sensor: no error in 111 files, a partition that holds, a time that is linear in the rows (0.43 s per 10,000 rows), a `quality.json` of 14 kB for a 12,000-row sequence, and the real clocks (dropped frames, pauses, ms-rounded steps, two bodies in a frame) handled as the rules of W6 say (never bridged across a pause, never filled across a not-tracked frame, flagged where mixed).
- **It does not show** that the chain is accurate on Kinect or on video: there is no ground truth for any flagged cell, the score is a constant, and 9 of 26 joints are absent. The 99.78 % of usable frames is the share of frames that have values, not a judgement of their quality.
- **It does not use** the `.lab` labels, the segmented sequences or the Qualisys data: those are P6.07's.

## Findings to carry forward

1. **No defect of a stage was found.** One property of P4.04 needed a decision and was changed: see 2.
2. **The `mixed` rows (DEC-0047, "a coarse time base") were real on real sensor clocks, and X.31 fixed them** (DEC-0052): before, a grid step taken from the median interval of a ms-rounded clock (33.0 ms against a true 33.33 ms) slid 1 % against the rows (96.5 % mixed, median weight 0.27); now the step counts frames and the phase is fitted, and a row within the 1 ms of a time stamp is on the grid (8.8 % mixed). The idea in the first version of this report, "a mean or fitted interval and a snap tolerance", was right about the tolerance but not about the mean: on a clock with dropped frames the plain mean or line step is 34 to 47 ms (6.5 % copies); only a step that counts the frames of each interval gives 33.333 ms. What remains is the eleven wandering clocks above.
3. **Hampel on Kinect flags the distal joints 16 to 40 times more often than the trunk** (wrists and toes about 4 %, shoulders 0.24 %, hips, neck and head 0.10 to 0.17 %). The floor is 1 % of the torso, here 4.4 to 5.4 mm, which has no relation to the sensor's noise; the stage is a data-validity flag and its parameters are not tuned for Kinect. If P6.07 or P5 use Kinect skeletons as input, the question of whether those cells should be removed is theirs.
4. **A repeated timestamp is a defect of one file** (two bodies in a frame). The adapter does not guess the performer (W5's tracking would need a cost and a threshold); P6.07 should skip or segment around `P04T02C03`'s last 62 rows.
5. **The Kinect files have no confidence.** A comparison on them (P6.07) will not have the mask's score to lean on; the (0, 0, 0) joints (12 cells) are the only marker.

## Limits

One dataset, one sensor, 12 performers, 30 Hz, 13 techniques that are not the 24 forms; no label of a swap or a spike, so no recall or precision is measured; the foot-to-big-toe mapping is an approximation; the plane (y, -z) was checked on the data (torso ratio 0.97 to 1.00) and not on documentation; timestamps are the file's (milliseconds, probably the sensor's system clock): the dropped-frame interpretation is supported by the joint displacement growing with the step (33 ms: 5.1 mm, 56 to 80 ms: 7.9 mm, 81 to 120 ms: 11.3 mm, 121 to 150 ms: 14.0 mm) but not proved. The numbers of this report are of the dataset at md5 `d2802095beec3736ecfb35ab4eac70e8` (`Kinect.zip`, `datasets/taiji/README.md`).
