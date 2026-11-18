# P5.08 — The cut-off of the Butterworth filter (4, 6, 8 Hz) against the pauses and the hip amplitude

Date: 2026-11-17. Task: `Docs/tasks/P5.08.md`. Decision: DEC-0061. Tool: `taiji_ai/tools/filter_ablation.py` (real data) and `taiji_ai/tests/helpers/ablation_sweep.py` (the generator); machinery: `taiji_ai/src/taiji_ai/bench/filter_ablation.py`.

**Read this first.** This report measures how the pauses (P5.07) and the hip amplitude (P5.03, P5.04) change when the final layer is made with a cut-off of 4, 6 or 8 Hz instead of the default 6 Hz, or with no filter at all. It changes nothing: the default is still 6 Hz (W6, DEC-0048) and any change is the maintainer's decision. There are three sources and they are **reported apart** (AGENTS.md 9.4.4): (1) the **generator**, which has a truth; (2) **D20**, the pose of four web lesson videos of one instructor (22 chunks); (3) **UMONS-TAICHI (D12)**, 111 Kinect skeleton files of 13 techniques that are not the 24 forms, out of domain. D20 and UMONS have **no label of a pause and no hip height truth**, so their numbers are *differences from the 6 Hz run*, never errors, and a lower paused share is not a better one. The `(τ, d_min)` cells are a **sensitivity grid**, not the values of any record (AGENTS.md 5.5).

## Summary

- **The pauses depend strongly on the cut-off; the hip amplitude hardly does.** On real data the share of the measured rows that is paused moves by tens of percent between 4 and 8 Hz at one `(τ, d_min)` (D20 hips at `τ` 0.3 Λ/s: 74 %, 65 %, 56 %, 48 % at 4, 6, 8 Hz and no filter), the number of pauses of a run equals its 6 Hz count in about 1 run in 10, and the rows that are paused agree with the 6 Hz run at 0.40 to 0.98 (an IoU); the hip range moves by at most **1.5 %** of its value on both real sources (median 0.1 % to 0.3 %) and within **3.1 %** of the truth at every cut-off on the generator. So the cut-off is chosen by the pauses; the hip amplitude does not ask for a cut-off.
- **`τ`, `d_min` and the cut-off are one triple.** A `τ` learned from the coach's labels is valid for the filter that made the layer. The signed `metric_record` (P5.09) has to carry the cut-off with them; the layer already does (`quality.json` and the layer's meta record `cutoff_hz`), the metric summaries do not echo it yet (a small follow-up, Q14 of the task).
- **A lower cut-off lowers the noise floor of the speed and smears a sharp onset.** On the generator (white noise, 1 px on a 200 px trunk) a joint that does not move reads a median speed of **0.040 / 0.066 / 0.094 / 0.127 Λ/s** at 4 / 6 / 8 Hz / no filter (maximum 0.145 / 0.180 / 0.191 / 0.285), proportional to the noise. At a `τ` near that floor (10 % of the true peak, 0.094 Λ/s) **4 Hz finds the right number of pauses in 5 of 5 seeds, 6 Hz in 2 of 5, 8 Hz in 1 of 5, no filter in 0 of 5** (SYN-05; SYN-07: 5, 3, 0, 1). At a `τ` above the floor (0.3 Λ/s) all four find them at 1 px of noise. The price of 4 Hz: with an onset of 0.1 s or of 0.02 s a pause boundary moves by **1.75 and 2.15 steps** where 6 and 8 Hz give 0.75 and 1.15 (the plan's tolerance is 1 frame; at 0.05 s the three filters are equal at 1.38 steps, so the cost is not monotone in the ramp); a slow movement (a 0.2 s ramp) is not touched by any cut-off (0.51 steps at every one).
- **A right count is not a right pause.** At a `τ` near the floor the count can be right while the pauses are shortened (SYN-05 at 1 px, `τ` 10 % of the peak: boundary errors of 8.5 to 12.5 steps in the seeds with the right count, against 0.51 at noise 0), and on real data a pause count is unstable between cut-offs because many short pauses flicker around `τ`. Lead with the paused share and the row-level agreement, not with the count.
- **Nothing here says which cut-off is right on real footage.** That needs the coach's pauses and the real sharpness of the onsets; the tool makes the re-run cheap (Proposal below).

## Method

- **Chain.** Each run goes through `run_quality_arrays` (Kinect, generator) or `run_quality` (D20: the target track) once per cut-off, with the defaults of every stage and only `ButterworthParams.cutoff_hz` changing: 4, 6, 8 Hz and 1000 Hz, which is above Nyquist for every grid here, so the filter is skipped and every run says `above_nyquist` (the values of the grid layer, untouched). The reference of every difference is 6 Hz. Order 4 and everything else are the defaults.
- **Invariant, checked on every run.** The filter copies `reason` and `interpolated` cell by cell, so the grid, the reasons, the flags and the segment must be the same at every cut-off. `check_invariants` raised on none of the **22 + 111 real runs** nor on any generator run; the number of rows with a speed is the same at every cut-off.
- **Measures of a run and a cut-off** (`bench/filter_ablation.py`): the quantiles (median and P95) of the speed of each group over its measured rows (P5.06); the pauses of each `(τ, d_min)` cell with `find_pauses` (P5.07); the hip range of variant B (`stable_intervals` = the whole segment, an explicit convention: nobody confirmed a stable height; variant A needs a reference standing segment that no chunk or file has, so it is measured on the generator only).
- **Grid.** On real data `τ` in {0.1, 0.2, 0.3, 0.5} Λ/s with `d_min` 0.3 s, and `τ` 0.2 Λ/s with `d_min` 0.5 s. On the generator `τ` as 10 % of the true peak of the group, and as an absolute 0.3 Λ/s (1.7 times the largest speed that 1 px of noise gave a still joint at 6 Hz).
- **Agreement with the reference** on a run, in rows of the shared grid: the **paused share** (paused rows over measured rows), the **row-level agreement** (intersection over union of the paused rows, on the rows measured in both; 1 is identical), the **count** and whether it equals the reference count, and the pauses **matched one to one by overlap** (at least half of the shorter pause, the largest overlap first) with the shift of their start and end in steps. Numerators and denominators are pooled over the runs.
- **Truth on the generator.** SYN-01 (still): the speed of a still joint is 0. SYN-05 and SYN-07 (the variable frame rate, resampled to 1/30 s): the pauses are the stretches where the analytic group speed is below `τ` (`slow_intervals`), not the generator's exact pauses (they are shorter by the ramps and leave out the turning point of the movement). SYN-02: the hip range is 2A.
- **D20.** 22 chunks of 300 s (4 videos, N = 1), the pose files of the P3.08 pass; the performer is the one `audit.analyse.target_track` follows (the most persistent large person of the chunk, the P3.08 review rule): the product's default rule (the largest person near the centre at the segment start) fails on 4 of the 22 chunks (a title card or another shot at the start) and the review has no user to ask. The instructor is the target in about 55 % of the rows; the rest are other shots (`not_tracked`).
- **UMONS.** 111 files, 30 Hz Kinect, 17 of the 26 HALPE joints (the feet group is the two ankles), the plane (y, -z) in mm read as pixels (the metrics are scale-free); the grid of X.31.
- **Reproduce** (from `taiji_ai/`): `python tools/filter_ablation.py d20 --pose data/reports/p3_08/pose --out data/reports/p5_08/d20 --report data/reports/p5_08/d20/tables.md` (90 s) and `python tools/filter_ablation.py umons --umons ../datasets/taiji/umons --out data/reports/p5_08/umons --report data/reports/p5_08/umons/tables.md` (257 s); the generator: `python tests/helpers/ablation_sweep.py` (about 3 minutes). Only run ids and numbers leave the tool.
- **Tests.** `tests/unit/test_filter_ablation.py` (the machinery, derived by hand), `tests/contract/test_filter_ablation_tool.py` (the tool in a subprocess), `tests/golden/test_filter_ablation_syn.py` (the claims below that hold on the generator, with margins), `tests/golden/test_filter_ablation_real.py` (two UMONS files and one D20 chunk behind `dataset`).

## Results

### 1. The generator (with a truth)

**The floor of the speed of a joint that does not move** (SYN-01, the hands, 3 seeds; V in body lengths per second):

| noise | cut-off | median | P95 | max |
|---|---|---|---|---|
| 0.5 px | 4 Hz | 0.020 | 0.035 | 0.073 |
| 0.5 px | 6 Hz | 0.033 | 0.056 | 0.090 |
| 0.5 px | 8 Hz | 0.047 | 0.078 | 0.096 |
| 0.5 px | no filter | 0.063 | 0.109 | 0.143 |
| 1 px | 4 Hz | 0.040 | 0.070 | 0.145 |
| 1 px | 6 Hz | 0.066 | 0.112 | 0.180 |
| 1 px | 8 Hz | 0.094 | 0.155 | 0.191 |
| 1 px | no filter | 0.127 | 0.218 | 0.285 |
| 2 px | 4 Hz | 0.080 | 0.140 | 0.291 |
| 2 px | 6 Hz | 0.133 | 0.223 | 0.358 |
| 2 px | 8 Hz | 0.187 | 0.310 | 0.383 |
| 2 px | no filter | 0.252 | 0.436 | 0.570 |

The floor rises with the cut-off and is proportional to the noise (2 px reads 1.98 to 2.02 times 1 px). The 6 Hz filter takes about half of the unfiltered floor away, 4 Hz two thirds.

**Pauses, SYN-05 (2 pauses), hands, `d_min` 0.3 s, 5 seeds; the count found per seed and the seeds with the right count:**

| noise | cut-off | `τ` = 10 % of the true peak (0.094 Λ/s) | `τ` = 0.3 Λ/s |
|---|---|---|---|
| 0 px | all four | 2, 2, 2, 2, 2 (5 of 5); boundary error 0.51 steps | 2, 2, 2, 2, 2 (5 of 5); 0.87 steps |
| 1 px | 4 Hz | 2, 2, 2, 2, 2 (**5 of 5**) | 5 of 5 |
| 1 px | 6 Hz | 1, 1, 2, 3, 2 (**2 of 5**) | 5 of 5 |
| 1 px | 8 Hz | 0, 0, 2, 0, 0 (**1 of 5**) | 5 of 5 |
| 1 px | no filter | 0, 0, 0, 0, 0 (**0 of 5**) | 5 of 5 |
| 2 px | 4 Hz | 1, 1, 1, 1, 1 (0 of 5) | 5 of 5 |
| 2 px | 6 Hz | 0, 0, 0, 0, 0 (0 of 5) | 5 of 5 |
| 2 px | 8 Hz | 0, 0, 0, 0, 0 (0 of 5) | 3, 3, 3, 2, 3 (**1 of 5**: fragments) |
| 2 px | no filter | 0, 0, 0, 0, 0 (0 of 5) | 0, 1, 2, 0, 2 (2 of 5) |

SYN-07 (one pause, variable frame rate) at 1 px and `τ` 10 %: 5, 3, 0 and 1 of 5 seeds right at 4, 6, 8 Hz and no filter; at `τ` 0.3 all five of five. At 2 px and `τ` 0.3: 5, 5, 4, 2 of 5. The worst boundary error in the seeds where the count is right: 0.51 and 0.53 steps at noise 0 for SYN-05 and SYN-07 at every cut-off (1 frame allowed); at 1 px and `τ` 10 % of the peak SYN-05 gives 8.5 (4 Hz), 12.0 (6 Hz) and 12.5 steps (8 Hz) (no seed of no filter is right) and SYN-07 1.5 steps at 4 and 6 Hz: with a `τ` near the floor a right count can hide pauses that are shortened by tens of rows; at `τ` 0.3 and 1 px the worst is 1.5 steps at 4 and 6 Hz and 5.5 at 8 Hz and no filter.

**The cost of a low cut-off: a sharp onset** (SYN-05, hands, noise 0, `τ` 10 %, `d_min` 0.3 s; boundary error in steps of 1/30 s):

| ramp (the generator's onset) | 4 Hz | 6 Hz | 8 Hz | no filter |
|---|---|---|---|---|
| 0.2 s (the default) | 0.51 | 0.51 | 0.51 | 0.51 |
| 0.1 s | **1.75** | 0.75 | 0.75 | 0.75 |
| 0.05 s | 1.38 | 1.38 | 1.38 | 0.69 |
| 0.02 s | **2.15** | 1.15 | 1.15 | 1.15 |

At 0.1 s and 0.02 s 4 Hz moves the boundary by one step more than 6 Hz; at 0.05 s the three filters are equal and cost 0.69 steps against no filter. The pattern is not monotone in the ramp: one clip, noise 0, and a boundary is a whole number of steps, so a small change of the speed profile can move it by one. How sharp the onsets of a real tai chi form are is not known from this data.

**Hip range** (SYN-02, relative error against 2A, 5 seeds; worst absolute error in percent; tolerance 5 %):

| variant | noise | 4 Hz | 6 Hz | 8 Hz | no filter |
|---|---|---|---|---|---|
| A and B | 0 px | 2.10 | 2.10 | 2.10 | 2.10 (the sampling at 30 fps) |
| A | 1 px | 2.11 | 2.05 | 2.08 | 2.92 |
| A | 2 px | 3.00 | 2.94 | 3.07 | 2.78 |
| B | 1 px | 1.91 | 2.52 | 2.51 | 2.25 |
| B | 2 px | 2.52 | 2.15 | 1.74 | 2.72 |

The range is within the tolerance at every cut-off and the three filtered cut-offs differ by under 2 points per seed (at most 1.6, variant A at 2 px). Without noise the range is identical to 0.01 point.

### 2. D20, real video pose (22 chunks, 4 videos, one instructor; sensitivity, no truth)

Speed of the groups, body lengths per second (median over the 22 chunks of the chunk's quantile):

| cut-off | hands p50 | hands p95 | hips p50 | hips p95 | feet p50 | feet p95 |
|---|---|---|---|---|---|---|
| 4 Hz | 0.418 | 1.440 | 0.139 | 0.594 | 0.095 | 0.612 |
| 6 Hz | 0.434 | 1.495 | 0.157 | 0.622 | 0.119 | 0.640 |
| 8 Hz | 0.438 | 1.544 | 0.171 | 0.646 | 0.138 | 0.662 |
| no filter | 0.429 | 1.567 | 0.185 | 0.667 | 0.152 | 0.674 |

Pauses, 22 runs, 86,243 measured rows for the hands (86,222 and 86,199 for the hips and the feet), `d_min` 0.3 s. Paused share of the measured rows, agreement with the 6 Hz run (IoU of the paused rows), pauses found and the share of the runs with the same count as 6 Hz:

| `τ` (Λ/s) | group | 4 Hz | 6 Hz | 8 Hz | no filter |
|---|---|---|---|---|---|
| 0.1 | hands | 10.4 %, 0.64, 378, 14 % | 6.7 %, 1, 312 | 4.3 %, 0.62, 230, 18 % | 2.8 %, 0.40, 156, 5 % |
| 0.2 | hands | 23.9 %, 0.80, 589, 5 % | 19.4 %, 1, 553 | 16.2 %, 0.82, 529, 5 % | 13.8 %, 0.70, 475, 5 % |
| 0.2 | hips | 55.2 %, 0.75, 1299, 5 % | 42.2 %, 1, 1357 | 33.0 %, 0.76, 1276, 0 % | 26.3 %, 0.61, 1068, 5 % |
| 0.2 | feet | 69.3 %, 0.84, 949, 0 % | 58.7 %, 1, 1271 | 48.6 %, 0.82, 1341, 0 % | 39.7 %, 0.67, 1223, 5 % |
| 0.3 | hands | 34.6 %, 0.85, 709, 9 % | 29.9 %, 1, 728 | 26.3 %, 0.86, 691, 18 % | 23.1 %, 0.76, 624, 14 % |
| 0.3 | hips | 73.7 %, 0.86, 1136, 0 % | 64.5 %, 1, 1462 | 55.7 %, 0.85, 1556, 0 % | 47.6 %, 0.73, 1435, 0 % |
| 0.3 | feet | 80.3 %, 0.94, 687, 5 % | 76.2 %, 1, 953 | 70.6 %, 0.92, 1163, 9 % | 63.7 %, 0.83, 1253, 0 % |
| 0.5 | hands | 54.4 %, 0.89, 960, 5 % | 49.5 %, 1, 1002 | 45.0 %, 0.90, 1002, 9 % | 40.3 %, 0.80, 929, 9 % |

The matched pauses start and end a median of 0 to 4.5 rows (steps) from their 6 Hz counterpart, a p95 of 15 to 83 rows (0.5 to 2.8 s at 30 fps), so at the tail the boundaries of a pause move by seconds. `d_min` 0.5 s at `τ` 0.2: the same picture (hands paused share 21.7, 17.2, 14.0, 11.8 %).

**Hip range, variant B, difference from the 6 Hz value** (22 chunks): median 0.20 % (4 Hz), 0.23 % (8 Hz), 0.28 % (no filter); P95 0.92, 0.77, 1.23 %; maximum 0.95, 0.82, 1.28 %.

### 3. UMONS Kinect (111 files, 723,557 measured rows for the hands; sensitivity, no truth, out of domain)

| cut-off | hands p50 | hands p95 | hips p50 | hips p95 | feet p50 | feet p95 |
|---|---|---|---|---|---|---|
| 4 Hz | 0.404 | 1.113 | 0.106 | 0.519 | 0.091 | 0.479 |
| 6 Hz | 0.429 | 1.242 | 0.108 | 0.554 | 0.104 | 0.540 |
| 8 Hz | 0.444 | 1.380 | 0.108 | 0.563 | 0.110 | 0.576 |
| no filter | 0.438 | 1.572 | 0.104 | 0.574 | 0.112 | 0.634 |

Pauses, `d_min` 0.3 s (the same cells; paused share, agreement with 6 Hz, pauses found, share of the runs with the same count):

| `τ` (Λ/s) | group | 4 Hz | 6 Hz | 8 Hz | no filter |
|---|---|---|---|---|---|
| 0.1 | hands | 6.0 %, 0.73, 1474, 9 % | 4.6 %, 1, 1291 | 3.8 %, 0.81, 1192, 21 % | 3.2 %, 0.66, 1040, 10 % |
| 0.2 | hands | 14.6 %, 0.76, 3420, 10 % | 11.5 %, 1, 2857 | 9.9 %, 0.83, 2567, 13 % | 8.6 %, 0.72, 2410, 5 % |
| 0.2 | hips | 63.5 %, 0.93, 8560, 5 % | 60.5 %, 1, 9007 | 58.5 %, 0.95, 9224, 6 % | 56.7 %, 0.91, 9543, 6 % |
| 0.2 | feet | 71.9 %, 0.88, 8078, 3 % | 64.2 %, 1, 9738 | 58.6 %, 0.90, 10416, 1 % | 53.0 %, 0.81, 10936, 5 % |
| 0.3 | hands | 24.9 %, 0.76, 5932, 3 % | 19.6 %, 1, 4918 | 16.8 %, 0.83, 4320, 5 % | 14.6 %, 0.71, 3978, 5 % |
| 0.3 | hips | 77.1 %, 0.94, 8259, 3 % | 74.0 %, 1, 9178 | 71.9 %, 0.96, 9604, 5 % | 69.9 %, 0.92, 9995, 2 % |
| 0.3 | feet | 83.5 %, 0.93, 6758, 2 % | 78.1 %, 1, 8530 | 73.8 %, 0.94, 9573, 5 % | 69.0 %, 0.87, 10728, 1 % |
| 0.5 | hands | 48.7 %, 0.78, 9948, 3 % | 39.1 %, 1, 9465 | 33.4 %, 0.83, 8584, 2 % | 28.7 %, 0.71, 7819, 2 % |

The matched pauses have a median shift of 0 to 1 row; the p95 is 8 to 61 rows. **Hip range, variant B, difference from 6 Hz** (111 files): median 0.18 % (4 Hz), 0.14 % (8 Hz), 0.29 % (no filter); P95 0.76, 0.65, 0.94 %; maximum 1.48, 1.07, 1.46 %.

## What the numbers do not say

- **No accuracy on real data.** D20 and UMONS have no label of a pause and no hip height truth. A lower paused share at a higher cut-off is not "better" or "worse"; the filter lowers the speed of a still joint, so fewer rows sit below a given `τ` at a higher cut-off. They say how much a pause number depends on a parameter that nobody has judged yet.
- **The generator's noise is white and Gaussian; the noise of a real pose is correlated in time.** The floor of a real joint is not the generator's: on real data the speed of the feet (which mostly stand) has a median of 0.095 to 0.152 Λ/s on D20 and 0.091 to 0.112 on UMONS, of the same order but with a different shape.
- **The data are not the product's.** D20 is a web video of one instructor (AV1 and H.264, 24 and 30 fps), UMONS is a Kinect of 12 performers doing 13 techniques that are not the 24 forms. No recording of the product's cameras and none of the participants exists yet (P9).
- **The grid is arbitrary.** The cells say how a pause number moves, not where a threshold belongs. A threshold learned from the coach's labels for one kind of movement is what B3 asks for.
- **The generator's onsets are cosine ramps**; whether a real onset is 0.02 s or 0.2 s is unknown, and the cost of 4 Hz depends on it.
- **The hip amplitude is of variant B on real data** (A needs a reference standing segment); the stable interval is the whole segment, a convention of the ablation.

## Proposal for the maintainer (changes nothing)

1. **Keep 6 Hz as the default for the MVP.** On the generator it is the middle of the trade-off (a floor 30 % lower than 8 Hz's and 65 % higher than 4 Hz's; a boundary within a frame for onsets of 0.1 s or slower) and nothing on real data says it is wrong. A change before the pilot would move the golden numbers of P4 and P5 and settle a question that the pilot can answer.
2. **Fix the triple.** `τ`, `d_min` and the cut-off are learned together; the record (P5.09) carries the cut-off with them, and the metric summary should echo the cut-off of the layer it read (proposed follow-up, Q14).
3. **Keep `τ` above the floor of the footage.** On the generator `τ` = 0.3 Λ/s clears the 6 Hz floor at 1 px (maximum 0.18) and gives the right pauses at every cut-off; at 0.1 Λ/s a pause is fragmented or shortened. The floor scales with the noise and with the cut-off (it is 2 times higher at 2 px and 1.4 times higher at 8 Hz than at 6 Hz), so the record's `τ` has to be set from the floor of the real footage (P9, P10), not from this table.
4. **Re-run this tool on the pilot data with the coach's pauses.** With a label of each pause, the same tool at 4, 5, 6 and 8 Hz and a grid around the coach's `τ` can measure accuracy (count and boundary against the labels) and choose the triple; if the real onsets are as sharp as the 0.1 s and 0.02 s ramps of the generator, 4 Hz costs a step more than 6 Hz at the boundary of a pause; if they are slow, 4 Hz finds pauses that 6 Hz loses at a low `τ` (SYN-05 at 1 px: 5 of 5 seeds against 2 of 5).

## Open questions for the maintainer

- Is 6 Hz kept for the MVP (point 1)? Changing it is a separate task with a DEC and new golden numbers.
- Is the small follow-up (the cut-off echoed in the speed summary's `parameters`) wanted before P5.09, so that a pause number carries its filter?
