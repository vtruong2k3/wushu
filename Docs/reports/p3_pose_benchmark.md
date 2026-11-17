# P3.07 — Pose benchmark: speed, GPU memory and the detector cadence N

Date: 2026-11-16. Task: `Docs/tasks/P3.07.md`. Gate G01 asks that RTF and VRAM can be measured; B-PERF-01 asks for RTF p50 and p95, peak VRAM and the end-to-end time of a 30 s segment. This report gives them for this machine.

**Read this first.** The footage is **D20** (four web Tai Chi lessons, labels `d20-v1` to `d20-v4`), **not** the P1.09 phone clips, which do not exist yet (DEC-0038). Five clips of 30 s (and the 1 s margins that `run_pose` adds), chosen before any number was seen. Nothing here is **product accuracy**: "the effect of N" compares N against N = 1 and says nothing about which of them is right. The GPU is shared with the desktop. The tool is `taiji_ai/tools/bench_pose.py`; every table below is generated from its `bench.json` (local, ignored by git), none is typed by hand.

## Summary

- **Speed.** RTF (processing seconds per video second) is **1.23 at N = 1** (slower than real time), **0.335 at N = 5** and **0.259 at N = 10** on the 24 and 30 fps clips. At 30 fps (the capture protocol) it is 1.47, 0.40 and 0.31; at 60 fps 2.9, 0.80 and 0.62. A 6-minute take at 30 fps costs about 8.8, 2.4 and 1.9 minutes of GPU for the pose alone.
- **Where the time goes.** The detector: 73 % at N = 1 (about 36 ms per 1080p call), 44 % at N = 5. The pose model costs about 8 ms per frame for one person (more in a crowd). Decode is 5 to 21 % (AV1 about 20 % dearer than H.264, about 2 ms per frame, never the bottleneck). The stages after `run_pose` (association, target, track, saving) take 0.1 to 0.2 s per clip.
- **One 30 s segment**, pose stage end to end: 37 to 46 s at N = 1, 10 to 13 s at N = 5, 7 to 10 s at N = 10.
- **GPU memory.** Peak 1.8 to 2.0 GB of device memory, **0.6 to 0.8 GB above what other programs held before** (1.2 GB); about 10 GB of the 12 GB stay free. The baseline did not drift (at most 6 MiB).
- **Repeatable.** All 15 (clip, N) cells gave bit-identical poses on every pass. Three cells are marked noisy (spread above 10 % after two extra passes: c4 at N = 5, c2 and c5 at N = 10): one slow pass each, the medians are stable.
- **The effect of N on the target** (the person P4 will use; all frames of the five clips): N = 5 differs from N = 1 by a median of 2.0 px, p95 9.7 px, p99 21.7 px (0.015 and 0.031 body heights), maximum 338 px (0.45 body height). The same person is the target in 5 of 5 clips and the share of `tracked` frames is the same. On all persons the count agrees in 96.3 % of the frames, 100 % on c1, c3 and c5 and 82.7 % on c2 (a lesson with up to four people).
- **The rule written before the measurement recommends N = 1**: N = 5 fails three criteria (count agreement 96.3 % under 99 %; p95 0.0201 over 0.01; p99 0.064 over 0.03). N = 10 fails the same three and is 22.5 % faster than N = 5. **The default stays N = 5 in the code until the maintainer decides** (see "What to decide").

## Method

- Clips (see the table): 30 s segments of the four videos found by size and SHA-256; ingested into a throwaway data folder (a test participant), deleted at the end. Frames by real PTS through `run_pose`.
- One **fresh process per N** (ONNX Runtime keeps its memory arena, so a peak after a larger run would be the larger peak). In each process: the models are built from the verified registry; one warm-up pass (not counted); three measured passes over the five clips; a clip whose elapsed times spread by more than 10 % gets up to two more passes.
- Time: `time.perf_counter`; detector and pose by a wrapper of the model; per-frame latency from an `on_frame` callback of `run_pose` (added for this task, the result does not depend on it); decode alone by a separate pass of the same frames; "other" is what remains. RTF over 1 s windows pools every window of every measured pass.
- GPU memory: the device total read through NVML (`ctypes`, the driver's library, every 20 ms) in phases (baseline before the models load, load, warm-up, measured); `nvidia-smi` cannot give a per-process figure on this system. The figure is **peak minus baseline** (what the process holds, arena included, not the minimum it needs).
- The effect of N: per frame the persons of run N are matched to those of N = 1 (Hungarian assignment on the mean keypoint distance over the common valid keypoints, over the hull height of the N = 1 person; a pair is accepted up to half a body height); distances per keypoint valid in both. The target view (added after the dry run, **not part of the rule**) compares the target tracks of P3.06 that P4 will receive.
- The rule for N (DEC-0038) was written before the measurement and is applied as written.

## Results

### Machine and software

| Item | Value |
| --- | --- |
| Date | 2026-11-16 |
| GPU | NVIDIA GeForce RTX 3060, 12288 MiB |
| Driver | 596.49 |
| onnxruntime-gpu / rtmlib | 1.32.0 / 0.0.16 |
| PyAV / numpy / Python | 19.0.2 / 2.5.4 / 3.12.10 |
| Providers | det: CUDAExecutionProvider, pose: CUDAExecutionProvider |
| GPU utilisation before each run (other programs) | N=1: 8 %, N=5: 2 %, N=10: 2 % |

### Clips

| Clip | Video | Start [s] | Frames | Codec | fps | Size | Persons per frame: 0 / 1 / 2 / 3 / 4+ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c1 | d20-v2 | 300 | 769 | h264 | 24.00 | 1920x1080 | 0 % / 100 % / 0 % / 0 % / 0 % |
| c2 | d20-v2 | 660 | 769 | h264 | 24.00 | 1920x1080 | 0 % / 49 % / 33 % / 15 % / 3 % |
| c3 | d20-v3 | 600 | 769 | h264 | 24.00 | 1920x1080 | 0 % / 100 % / 0 % / 0 % / 0 % |
| c4 | d20-v1 | 500 | 769 | av1 | 24.00 | 1920x1080 | 0 % / 94 % / 6 % / 0 % / 0 % |
| c5 | d20-v4 | 1200 | 961 | av1 | 30.00 | 1920x1080 | 0 % / 100 % / 0 % / 0 % / 0 % |

### Real-time factor (median of the measured passes, minimum to maximum)

| Clip | N = 1 | N = 5 | N = 10 |
| --- | --- | --- | --- |
| c1 | 1.141 (1.137 to 1.185) | 0.297 (0.297 to 0.299) | 0.222 (0.222 to 0.228) |
| c2 | 1.278 (1.273 to 1.332) | 0.372 (0.370 to 0.376) | 0.304 (0.290 to 0.334) noisy |
| c3 | 1.147 (1.138 to 1.165) | 0.301 (0.294 to 0.301) | 0.224 (0.222 to 0.226) |
| c4 | 1.151 (1.148 to 1.160) | 0.315 (0.314 to 0.347) noisy | 0.241 (0.240 to 0.249) |
| c5 | 1.444 (1.444 to 1.461) | 0.389 (0.389 to 0.422) | 0.306 (0.293 to 0.342) noisy |
| all clips | 1.232 | 0.335 | 0.259 |

### Where the time goes (seconds for one pass over all the clips; the share of the elapsed time in brackets)

| N | Elapsed | Decode | Detector | Pose | Other | After run_pose (not in elapsed) |
| --- | --- | --- | --- | --- | --- | --- |
| N = 1 | 197.41 | 9.65 (5 %) | 145.04 (73 %) | 37.22 (19 %) | 5.50 (3 %) | 0.70 |
| N = 5 | 53.63 | 8.54 (16 %) | 23.61 (44 %) | 23.12 (43 %) | -1.63 (-3 %) | 0.54 |
| N = 10 | 41.57 | 8.68 (21 %) | 11.87 (29 %) | 22.75 (55 %) | -1.73 (-4 %) | 0.54 |

### Per-frame latency and real-time factor over 1 s windows (B-PERF-01)

| N | Mean ms/frame | Frame p50 | Frame p95 | Frame p99 | Window RTF p50 | Window RTF p95 | Windows | RTF at 30 fps | RTF at 60 fps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N = 1 | 48.9 | 47.5 | 58.4 | 66.8 | 1.163 | 1.451 | 480 | 1.467 | 2.934 |
| N = 5 | 13.3 | 6.8 | 36.7 | 46.6 | 0.312 | 0.453 | 544 | 0.399 | 0.797 |
| N = 10 | 10.3 | 6.5 | 35.0 | 43.8 | 0.249 | 0.424 | 608 | 0.309 | 0.618 |

### GPU memory (device total in MiB, one fresh process per N)

| N | Baseline | Baseline drift | Peak in warm-up | Peak in measured passes | Peak minus baseline | Free at the peak |
| --- | --- | --- | --- | --- | --- | --- |
| N = 1 | 1207 | 1 | 1775 | 2034 | 826 | 10254 |
| N = 5 | 1261 | 1 | 1790 | 1930 | 669 | 10358 |
| N = 10 | 1228 | 6 | 1774 | 1833 | 605 | 10455 |

### Cold start (model load, warm-up pass and the steady pass of clip c1, seconds)

| N | Model load | Warm-up pass | Steady pass |
| --- | --- | --- | --- |
| N = 1 | 1.94 | 41.91 | 36.57 |
| N = 5 | 0.64 | 10.30 | 9.53 |
| N = 10 | 0.66 | 8.82 | 7.13 |

### Pose stage of one 30 s segment (run_pose with its 1 s margins, association, target, track, saving), seconds

| Clip | N = 1 | N = 5 | N = 10 |
| --- | --- | --- | --- |
| c1 | 36.8 | 9.6 | 7.2 |
| c2 | 41.2 | 12.1 | 9.9 |
| c3 | 36.8 | 9.7 | 7.3 |
| c4 | 37.0 | 10.2 | 7.8 |
| c5 | 46.4 | 12.6 | 9.9 |

### Effect of N against N = 1: persons (all clips pooled)

| N | Frames with the same count | Matched | Missed | Extra | Uncomparable (N=1 / N) | Entry delay mean / max [frames] | Tracks never matched |
| --- | --- | --- | --- | --- | --- | --- | --- |
| N = 5 | 96.28 % | 4525 | 104 | 67 | 4 / 10 | 0.68 / 4 | 25 |
| N = 10 | 95.02 % | 4464 | 165 | 77 | 4 / 10 | 1.14 / 9 | 36 |

### Effect of N against N = 1: keypoint distance (all clips pooled; pixels, then body heights)

| N | px median | px p95 | px p99 | px max | body median | body p95 | body p99 | body max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N = 5 | 1.85 | 9.50 | 21.11 | 338.32 | 0.0041 | 0.0201 | 0.0641 | 0.8498 |
| N = 10 | 2.17 | 10.06 | 23.07 | 337.98 | 0.0047 | 0.0209 | 0.0659 | 0.7804 |

### p95 distance per joint group (body heights)

| N | head | trunk | arms | legs | feet |
| --- | --- | --- | --- | --- | --- |
| N = 5 | 0.0164 | 0.0141 | 0.0238 | 0.0164 | 0.0292 |
| N = 10 | 0.0170 | 0.0145 | 0.0253 | 0.0170 | 0.0312 |

### Effect of N per clip, and what the target looks like downstream

| N | Clip | Same count | Missed / extra | p95 body | Max px | Same target | Tracked share | needs_reselect |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N = 5 | c1 | 100.00 % | 0 / 0 | 0.0157 | 191.6 | yes | 100.00 % | no |
| N = 5 | c2 | 82.70 % | 92 / 62 | 0.0387 | 199.2 | yes | 100.00 % | no |
| N = 5 | c3 | 100.00 % | 0 / 0 | 0.0165 | 112.3 | yes | 99.35 % | no |
| N = 5 | c4 | 97.79 % | 12 / 5 | 0.0146 | 133.1 | yes | 100.00 % | no |
| N = 5 | c5 | 100.00 % | 0 / 0 | 0.0172 | 338.3 | yes | 100.00 % | no |
| N = 10 | c1 | 100.00 % | 0 / 0 | 0.0166 | 191.6 | yes | 100.00 % | no |
| N = 10 | c2 | 76.72 % | 147 / 71 | 0.0399 | 198.0 | yes | 100.00 % | no |
| N = 10 | c3 | 100.00 % | 1 / 1 | 0.0172 | 109.6 | yes | 99.22 % | no |
| N = 10 | c4 | 97.14 % | 17 / 5 | 0.0152 | 96.8 | yes | 100.00 % | no |
| N = 10 | c5 | 100.00 % | 0 / 0 | 0.0181 | 338.0 | yes | 100.00 % | no |
| N = 1 | c1 | reference |  |  |  | reference | 100.00 % | no |
| N = 1 | c2 | reference |  |  |  | reference | 100.00 % | no |
| N = 1 | c3 | reference |  |  |  | reference | 99.35 % | no |
| N = 1 | c4 | reference |  |  |  | reference | 100.00 % | no |
| N = 1 | c5 | reference |  |  |  | reference | 100.00 % | no |

### Supplementary: the target track that P4 receives, N against N = 1 (added after the dry run; not part of the rule)

| N | Frames | Both have the target | Only N = 1 | Only N | Uncomparable | px median | px p95 | px p99 | px max | body median | body p95 | body p99 | body max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N = 5 | 4037 | 4032 | 0 | 0 | 0 | 2.00 | 9.74 | 21.69 | 338.32 | 0.0038 | 0.0151 | 0.0310 | 0.4491 |
| N = 10 | 4037 | 4031 | 1 | 0 | 0 | 2.32 | 10.33 | 23.71 | 337.98 | 0.0044 | 0.0160 | 0.0339 | 0.4491 |

### The rule written before the measurement, and its result

Limits: agreement at least 99.0 %; p95 at most 0.01 and p99 at most 0.03 body heights; tracked share not lower by more than 0.5 points; no new needs_reselect; a larger N must be at least 15 % faster than the previous one.

| N | Acceptable | Faster than the previous N by | Why not |
| --- | --- | --- | --- |
| N = 5 | no | 72.8 % | person-count agreement 0.9628 is below 0.99; p95 distance 0.02011 body heights is above 0.01; p99 distance 0.06414 body heights is above 0.03 |
| N = 10 | no | 22.5 % | person-count agreement 0.9502 is below 0.99; p95 distance 0.02095 body heights is above 0.01; p99 distance 0.06594 body heights is above 0.03 |

**Recommended N: 1**

## What the numbers say

1. **Speed.** At N = 1 the detector is called on every frame and costs 27.6 s of the 36.6 s of a 769-frame clip; deriving the box from the previous keypoints removes four calls in five and makes the run 3.7 times faster (N = 5). Going from 5 to 10 saves a further 22.5 %. At N = 1 the pose stage is slower than real time on this GPU; for offline analysis that is a cost in waiting time, not a blocker.
2. **Latency is spiky at N > 1.** At N = 5 the median frame takes 6.8 ms and the p95 36.7 ms: a detector frame costs about 45 ms and a derived-box frame about 7 ms. Irrelevant offline; it matters only for a live preview.
3. **Memory is not a constraint**: under 2 GB used of 12 GB, with the desktop included.
4. **The phases do not add up exactly.** "Other" is negative at N = 5 and N = 10 (-3 % and -4 %): the decoder runs in its own threads and overlaps with the GPU work, so the decode-alone pass counts time that the run hides. Read the phase split as the cost of each part, not as a partition of the elapsed time.
5. **About the rule.** It fails N = 5 on three criteria, and two of them say less than they seem to. The **count agreement** is dominated by c2, where small people stand behind the performer; it is 100 % on the three clips with one person. The **distance limits** (p95 0.01, p99 0.03 body heights) were set from the one 10 s clip of P3.02 (p95 5.68 px, about 0.007 of a body height); on five clips the target's p95 is **0.012 to 0.017 on every clip**, also on the single-person ones, so the limit would fail N = 5 anywhere. The rule is not changed here: it was written to avoid choosing the limit after the result, and the maintainer can judge whether it was too strict.
6. **What N changes.** The largest differences are in the feet (p95 0.029 body height at N = 5) and the arms (0.024), the trunk is the least (0.014): a box taken from the previous keypoints can cut a fast limb. The single largest difference is 338 px at one keypoint of one frame of c5; its cause was not examined here (this comparison does not tell whether N = 5, N = 1 or both are wrong). P3.08 looks at the flagged windows at both cadences and marks the failures that depend on N.
7. **Noise.** The GPU was used by other programs at 2 to 8 % before each run; the repeated passes agree to a few percent except in the three noisy cells (one pass about 10 % slow). The informative numbers of P3.02 (0.39 and 0.92 s per second of video) came from one 12 s pass with the warm-up inside and a machine in another state; today's N = 1 takes 48 ms per frame against 38 ms then, so single numbers on this machine should be read with a spread of about 25 %.

## What to decide

The recommendation of the written rule is **N = 1**. The choice is the maintainer's; the code keeps **N = 5** until it is made (changing the default moves the golden tolerances of T-POSE-07 and the cache key of P7).

| Option | Cost | What it gives |
| ------ | ---- | ------------- |
| N = 1 (the rule) | RTF 1.47 at 30 fps: a 6-minute take about 8.8 minutes of GPU | the detector on every frame; the reference every other N was compared with, which has its own errors |
| N = 5 (now) | RTF 0.40: about 2.4 minutes | the target's keypoints differ from N = 1 by a median of 2 px and p95 of 10 px; rare large differences (maximum 338 px) are unexplained |
| N between (2 or 3) | not measured | the tool can measure it: `--ns 1,2,3,5` |

My reading: wait for the P3.08 review, which compares the two cadences on the frames that look wrong and says whether the large differences are N = 5 errors; decide then. If a decision is needed before, keep N = 5 and say in every report that the target keypoints carry this consistency limit.

**Decision (2026-11-16, DEC-0042):** the maintainer kept **N = 5**. The review of P3.08 found no evidence that N = 1 has fewer failures (of 61 counted failures: 36 at both cadences, 10 only at N = 1, 5 only at N = 5, 10 unknown), and N = 5 is about 3.7 times faster. To be looked at again with clips of our own (X.27, X.28); an N between 1 and 5 can be measured with `--ns 1,2,3,5`.

## Limits

- D20 only: a large presenter, a steady camera, lecture lighting, AV1 and H.264 at 24 and 30 fps. Phone clips (the capture protocol: 30 fps H.264, 1080p) can differ; the tool is made to be rerun on them (follow-up X.27, blocked by P1.09) and on the target machine (P11.03).
- Five clips of 30 s. The persons per frame are measured and given; clips with one person dominate.
- The effect of N is a consistency measure against N = 1, not an accuracy.
- Peak VRAM is the memory the process holds; ONNX Runtime keeps its arena. It does not give a minimum.
- The plan has no target for RTF or VRAM, so none is claimed; G01's "RTF/VRAM measurable" is met.
- TensorRT, batching and CPU timing were not measured. Frame rates other than 24 and 30 are derived from ms per frame, not measured.
- The limits of the rule (0.01, 0.03, 99 %, 0.5 points, 15 %) are provisional engineering choices.

## Reproduce

From `taiji_ai/`, with the GPU free of other jobs (about 28 minutes at the default settings):

```powershell
.venv\Scripts\python.exe tools\bench_pose.py --video-dir ..\video --out data\reports\p3_07
```

It writes `bench.json` (every number, including the per-frame latencies) and `report_tables.md` (the tables above) into `--out`, prints labels and a short summary only, and removes the throwaway folder of copies of the videos.

## Appendix A. The detector: YOLOX (shipping) against YOLO11m (P3.09)

Measured on 2026-11-17, same machine and the same footage as above; **nothing in the stack changes**. YOLO11 and its weights are
AGPL-3.0 (Ultralytics) and were used offline for this one measurement (DEC-0043): the ONNX file was exported by the vendor's
command line in an isolated environment, nothing of the repository imports Ultralytics, and the files were deleted afterwards.
Task file: `Docs/tasks/P3.09.md`. A is the shipping YOLOX-m (the registry file, through ONNX Runtime with the scores kept, its own
NMS inside the graph: 0.65, then a score strictly above 0.3 as rtmlib applies); B is YOLO11m exported at 640 x 640 (80 classes,
fp32, person class, score strictly above 0.3, NMS 0.65 in our NumPy code). Both on the CUDA provider, batch 1.

**What was measured** (the rule was written before any number, DEC-0043):

- *Recall on labelled frames:* the 169 frames of P3.08 that the maintainer and the agent labelled `ok` and that have a skeleton
  (its hull, grown by 5 %, is the reference box); a detector finds the performer when one of its boxes has IoU of 0.5 or more with
  it; paired, exact McNemar test. Two more frames without a person test false alarms. These frames come from the pool of P3.08,
  which only held frames the shipping pipeline had followed, so recall here **flatters the shipping detector**.
- *The five clips of P3.07* (3 785 frames): every frame, both detectors; a frame "has the performer" when there is a box of at
  least 20 % of the image height; the stretches (runs) where only one detector has it were to be reviewed; stability of the box
  between consecutive frames; dropouts in seconds.
- *Speed and memory:* a fresh process per detector, 300 frames of clip c1 decoded once, 30 warm-up frames, three repeats.

**The result by the rule: not materially better; DEC-0005 stands** (YOLOX stays, no Ultralytics). R: recall A 98.2 %, B 100.0 %,
gain 1.8 points (needs 3), exact McNemar p 0.25 (needs under 0.05): not met. C: the two detectors have a performer-sized box in
**every one of the 3 785 frames** of the five clips, so there is no run to review (0 of 0): not met. No false alarm on the two
frames without a person.

What the tables say beyond the rule:

1. **Both detectors find the performer.** There is no frame of the clips in which one has them and the other not, and on the
   labelled frames the three that A "misses" at IoU 0.5 are boxes that are **too loose** (IoU 0.46 to 0.50), not absent: at IoU 0.3
   both find 100 % (table "Box agreement").
2. **YOLOX's boxes are looser and less steady than YOLO11's.** The best IoU with the skeleton's hull has a median of 0.76 for A and
   0.87 for B, and at IoU 0.7 A finds 63.3 % and B 95.3 % (the hull of the joints is itself tighter than a box, so absolute values
   are low for both; the difference between them is the finding). Between consecutive frames `1 - IoU` has a p95 of 0.131 for A
   and 0.063 for B (B at 0.48 of A), and the change of the box height against its neighbours has a p95 of 0.047 for A and 0.006
   for B. By the rule this is **a note and not a criterion**: between detector calls the box comes from the keypoints, so at N = 5
   the detector's box reaches the pose on one frame in five. Whether a looser box costs accuracy of the keypoints was **not
   measured here**.
3. **YOLO11m is about 1.6 times faster end to end** (22.4 ms against 36.8 ms per frame, p50; model alone 16.2 ms against 32.0 ms)
   on the same GPU, with a little more memory above the baseline (652 MiB against 516 MiB). The in-graph NMS of the shipping file
   and its opset-11 graph are part of the model time of A, so the model-only times are not a like-for-like speed of the networks.
   For the pipeline the point is that the detector is **not a small part of the time**, as the plan had assumed: in the
   P3.07 runs it took 145 s of 198 s (73 %) over the five clips at N = 1 and 24 s of 54 s (44 %) at N = 5 (`bench.json`,
   `phases_s`). A detector with YOLO11m's end-to-end time (22.4 ms for 36.8 ms) would remove about 39 % of that part, which by
   arithmetic (not measured in the pipeline) is about 29 % of the total time at N = 1 and 17 % at N = 5.
4. **The score limit does not matter here:** recall is the same at 0.3, 0.5 and 0.7 for both (the scores of a performer are high,
   median 0.89 and 0.91), and the same at two NMS limits (0.45 and 0.7 gave the same recall in the first run).

**Limits.** Lesson footage of one large performer, three or more performers, not our capture (P1.09 and X.27 repeat it); the
labelled set flatters the shipping detector; frames where **both** miss cannot be seen (the clips had none, and only 1 of the
250 frames of P3.08 had no person detected at N = 1, a dark fade); the reference boxes come from skeleton hulls; the clips are five
stretches of 30 s; a single GPU (RTX 3060); the detector is measured alone, not its effect on the keypoints. The first run (NMS
0.45 for YOLO11, the limit written in the plan before the graph was read) gave the same recall, the same decision and the same
stability.

**What this means.** There is no case for changing the detector on the grounds of finding the performer. If the looseness of the
boxes or the time at N = 1 matter later, the question to ask is not "YOLO11 or YOLOX" (YOLO11 cannot be shipped under AGPL-3.0) but
whether a **permissive** detector with tighter boxes and the speed of YOLO11 exists (RTMDet, a larger YOLOX, others) and whether the
keypoints improve with it: a follow-up for the maintainer, not started.

### Tables (generated by `tools/detector_compare.py`, unchanged)

#### Speed and memory (median over the repeats, ms per frame, 640 x 640, batch 1, fp32, CUDA)

| Detector | Model p50 | Model p95 | End-to-end p50 | p95 | p99 | VRAM above baseline [MiB] |
| --- | --- | --- | --- | --- | --- | --- |
| YOLOX (shipping) | 31.96 | 34.27 | 36.83 | 40.35 | 43.84 | 516 |
| YOLO11m | 16.20 | 17.45 | 22.35 | 24.12 | 27.86 | 652 |

#### Recall of the performer on the labelled frames (score limit 0.3; 169 frames with a reference box)

| Recall A | Recall B | Both | Only A | Only B | Neither | McNemar p (exact) |
| --- | --- | --- | --- | --- | --- | --- |
| 98.2 % | 100.0 % | 166 | 0 | 3 | 0 | 0.2500 |

Negative frames (no person): 2; false alarms A 0, B 0. Frames without a usable reference box: 79.

#### Recall when the score limit is raised

| Score limit | Frames | Recall A | Recall B |
| --- | --- | --- | --- |
| 0.3 | 169 | 98.2 % | 100.0 % |
| 0.5 | 169 | 98.2 % | 100.0 % |
| 0.7 | 169 | 98.2 % | 100.0 % |

#### Box agreement with the reference box (best IoU per labelled frame; the rule uses IoU 0.5)

| Detector | IoU p10 | p25 | median |
| --- | --- | --- | --- |
| YOLOX (shipping) | 0.61 | 0.66 | 0.76 |
| YOLO11m | 0.76 | 0.80 | 0.87 |

| IoU limit | Recall A | Recall B |
| --- | --- | --- |
| 0.3 | 100.0 % | 100.0 % |
| 0.5 | 98.2 % | 100.0 % |
| 0.7 | 63.3 % | 95.3 % |

#### The clips: frames with a performer-sized box (at least 20 % of the image height)

| Clip | Frames | Both | Only A | Only B | Neither |
| --- | --- | --- | --- | --- | --- |
| c1 | 721 | 721 | 0 | 0 | 0 |
| c2 | 721 | 721 | 0 | 0 | 0 |
| c3 | 721 | 721 | 0 | 0 | 0 |
| c4 | 721 | 721 | 0 | 0 | 0 |
| c5 | 901 | 901 | 0 | 0 | 0 |
| all | 3785 | 3785 | 0 | 0 | 0 |

Runs of frames where only one detector has the performer: only A 0, only B 0. Frames where both miss cannot be seen by this method.

#### Stability of the performer's box (consecutive frames)

| Detector | Pairs | Jumps (IoU < 0.5) | 1 - IoU p50 | p95 | p99 | Height change p95 |
| --- | --- | --- | --- | --- | --- | --- |
| YOLOX (shipping) | 3780 | 0 | 0.0143 | 0.1307 | 0.2942 | 0.0465 |
| YOLO11m | 3780 | 0 | 0.0110 | 0.0625 | 0.1354 | 0.0059 |

#### Dropouts: seconds in which one detector loses the performer while the other has them

| Detector that loses | Runs | Total [s] | Longest [s] | Runs over 0.5 s |
| --- | --- | --- | --- | --- |
| YOLOX (shipping) | 0 | 0.00 | n/a | 0 |
| YOLO11m | 0 | 0.00 | n/a | 0 |

#### The reviewed runs of the clips (one representative frame per run)

| Runs | Reviewed | B right, A wrong | A right, B wrong | Unsure |
| --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | 0 |

#### The decision by the rule written before the measurement (DEC-0043)

**not_materially_better**

- R: recall A 98.2 %, B 100.0 % on 169 frames, gain 1.8 points (needs 3), exact McNemar p 0.250 (needs under 0.05): not met
- C: reviewed 0 of 0 runs (stretches where only one detector finds a person): B right in 0, A right in 0, difference 0 (needs 5): not met
- stability supports a gap but never decides alone: p95 of 1 - IoU A 0.131, B 0.063 (B at 0.48 of A, needs 0.7 or less)
