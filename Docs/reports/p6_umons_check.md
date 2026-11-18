# P6.07 — The comparison chain checked on UMONS-TAICHI (out of domain)

Task `P6.07` (test T-CMP-09, manual check M-CMP-01), run on 2026-11-18 with `taiji_ai/tools/umons_compare.py`
(`bench/umons_compare.py`). The tables below are the ones the tool wrote; the prose only quotes them.

**Out of domain, not the product's accuracy** (AGENTS.md §9.4 item 4). The data are UMONS-TAICHI (registry ID **D12**,
CC BY-NC-SA 4.0, allowed use `dev-test` and `benchmark`): 13 basic techniques seen by a Kinect (25 joints, 30 Hz, a
clean 3D sensor), not the 24 forms seen by a video pose. The quality layer is built with the default chain from 17 of
the 26 HALPE joints (the 12 joints and 9 angles of the 21 comparison units are all among them). Nothing was tuned on
these files; the settings were fixed before the runs (plan Q3) and are echoed below. Only dataset file IDs and numbers
are in this report: no skeleton value and no label time. Nothing derived from these files was trained on or shipped.

## 1. What was run

| Item | Value |
|---|---|
| Chain | quality chain (defaults), frame features (12 positions, 9 angles, 21 units), masked cost, constrained DTW (`compare.align.align`) |
| Settings | `min_visible` 11 of 21 (half the units, rounded up), weights 1, `symmetricP1`; `min_scale_s` and `min_segment_length` not applied; **band 0.2 for segments, 0.1 for whole recordings** (plan Q3) |
| Seed | 1 (a SHA-256 of the seed and the ID orders every choice, so the sample can be re-run) |
| Guards | none run: UMONS has no ontology record to give them |
| Classes sample | 3 references and 5 queries per class and side: 66 references and 110 queries, 176 segments, 3,412 pairs |
| Boundaries sample | 40 of the 55 usable pairs of continuous recordings (39 distinct recordings) |
| Time | classes 131 s; boundaries 565 s (band 0.1); one pair of the two longest recordings (12,196 and 8,265 grid rows) takes 45.7 s and peaks at 2.7 GB in the cost and DTW matrices (the cost is built by blocks, the DTW holds the full matrix) |

**Assumptions about the names** (the dataset notes `datasets/taiji/README.md` infer them; the authors do not document
them): in `PxxTxxCxxGxxDxxSxx` P is the performer, T the trial, C the capture, **G the class (13), D the side (left or
right) and S the repetition**. A pair is aligned only inside one side. The `.lab` times are read as seconds from the first
row of the Kinect file; the 131 label files all parse with the strict reader (a time and a label per line, increasing
times, `_` or `ex`/`tech` + number + optional `l`/`r`), the first label is never a rest and the last is always one.
Classes G01 to G04 have segments on side D01 only, so side D02 has 9 classes.

**Performers.** A performer is never compared with themself: 338 pairs of the plan were left out for that reason in the
classes run, and a pair of recordings always has two performers (checked in the tool and by a refusal in the
aggregation).

## 2. Classes: is the same class closer?

Headline (plan Q6: a number, not a gate; "most classes" is read as more than half):
**the own class is closer in 13 of 13 classes (100 %)**, and the nearest reference is of the same class for **95 of 104
queries (91.3 %)** (chance with 13 classes is 7.7 %). Six of the 110 queries had no pair with a distance and are not in
the 104. Side D01: 13 of 13 classes, 55 of 61 queries; side D02: 9 of 9, 40 of 43.

#### Per class, both sides pooled

| Class | Queries | Own pairs | Other pairs | Own median D | Other median D | Other / own | Own closer | Nearest correct | No path own / other |
|---|---|---|---|---|---|---|---|---|---|
| G01 | 5 | 6 | 60 | 0.0432 | 0.4079 | 9.44 | yes | 4 / 4 | 6 / 106 |
| G02 | 5 | 5 | 79 | 0.1021 | 0.3456 | 3.38 | yes | 4 / 5 | 7 / 83 |
| G03 | 5 | 4 | 71 | 0.1362 | 0.3263 | 2.40 | yes | 3 / 3 | 8 / 94 |
| G04 | 5 | 9 | 90 | 0.1446 | 0.3485 | 2.41 | yes | 4 / 4 | 3 / 72 |
| G05 | 10 | 24 | 179 | 0.1666 | 0.3516 | 2.11 | yes | 10 / 10 | 0 / 98 |
| G06 | 10 | 20 | 173 | 0.2006 | 0.3568 | 1.78 | yes | 9 / 10 | 4 / 108 |
| G07 | 10 | 13 | 111 | 0.1724 | 0.3652 | 2.12 | yes | 9 / 10 | 11 / 168 |
| G08 | 10 | 20 | 152 | 0.1859 | 0.3597 | 1.93 | yes | 9 / 9 | 4 / 120 |
| G09 | 10 | 20 | 66 | 0.2077 | 0.3926 | 1.89 | yes | 9 / 10 | 4 / 208 |
| G10 | 10 | 15 | 184 | 0.2418 | 0.3556 | 1.47 | yes | 8 / 10 | 9 / 90 |
| G11 | 10 | 16 | 175 | 0.2520 | 0.4151 | 1.65 | yes | 7 / 10 | 8 / 105 |
| G12 | 10 | 17 | 141 | 0.2486 | 0.4004 | 1.61 | yes | 10 / 10 | 7 / 133 |
| G13 | 10 | 21 | 79 | 0.2172 | 0.3959 | 1.82 | yes | 9 / 9 | 3 / 203 |

Classes where the own class is closer: 13 of 13 (100.0 %). Nearest-reference class correct: 95 of 104 queries (91.3 %). Pairs with a distance 1750, with no path 1662.

The margins are not equal: the median distance to other classes is 9.4 times the own one for G01 but 1.5 to 1.7 times
for G10, G11 and G12, and 1.8 to 2.1 for most others.

**A confound that the tool reports and that must be read with the numbers: pairs with no path.** `symmetricP1` has
no path when the lengths differ by more than 2 to 1 (segments are 18 to 1,147 frames), so **1,662 of the 3,412 pairs
(48.7 %) have no distance**, and the loss is not even: 74 of 264 own-class pairs (28.0 %) against 1,588 of 3,148
other-class pairs (50.4 %). A reference of the same class is therefore more likely to be compared at all (own classes
share a duration), which can flatter both the class medians and the nearest-class result. Because of that cause, and
not to improve a number, the same sample and settings were run once more with the step pattern without a slope limit
(`symmetric1`): it is reported next to the first run; neither is chosen, and the product's pattern stays `symmetricP1`.

#### Per class, both sides pooled

| Class | Queries | Own pairs | Other pairs | Own median D | Other median D | Other / own | Own closer | Nearest correct | No path own / other |
|---|---|---|---|---|---|---|---|---|---|
| G01 | 5 | 12 | 152 | 0.0494 | 0.4064 | 8.23 | yes | 5 / 5 | 0 / 14 |
| G02 | 5 | 12 | 149 | 0.1529 | 0.3452 | 2.26 | yes | 4 / 5 | 0 / 13 |
| G03 | 5 | 4 | 94 | 0.1257 | 0.3473 | 2.76 | yes | 2 / 3 | 8 / 71 |
| G04 | 5 | 9 | 121 | 0.1405 | 0.3410 | 2.43 | yes | 4 / 4 | 3 / 41 |
| G05 | 10 | 24 | 249 | 0.1668 | 0.3435 | 2.06 | yes | 10 / 10 | 0 / 28 |
| G06 | 10 | 20 | 257 | 0.1981 | 0.3533 | 1.78 | yes | 9 / 10 | 4 / 24 |
| G07 | 10 | 24 | 250 | 0.1842 | 0.3566 | 1.94 | yes | 10 / 10 | 0 / 29 |
| G08 | 10 | 22 | 226 | 0.1871 | 0.3532 | 1.89 | yes | 9 / 9 | 2 / 46 |
| G09 | 10 | 24 | 250 | 0.2103 | 0.4032 | 1.92 | yes | 10 / 10 | 0 / 24 |
| G10 | 10 | 16 | 256 | 0.2429 | 0.3556 | 1.46 | yes | 8 / 10 | 8 / 18 |
| G11 | 10 | 20 | 255 | 0.2357 | 0.4067 | 1.73 | yes | 7 / 10 | 4 / 25 |
| G12 | 10 | 20 | 252 | 0.2272 | 0.3892 | 1.71 | yes | 10 / 10 | 4 / 22 |
| G13 | 10 | 21 | 235 | 0.2171 | 0.3804 | 1.75 | yes | 9 / 9 | 3 / 47 |

Classes where the own class is closer: 13 of 13 (100.0 %). Nearest-reference class correct: 97 of 105 queries (92.4 %). Pairs with a distance 2974, with no path 438.

With `symmetric1`, 438 of 3,412 pairs have no path (12.8 %; own 13.6 %, other 12.8 %: no longer uneven), the own class
is closer in 13 of 13 classes and the nearest reference is of the same class for 97 of 105 queries (92.4 %); side D01 56
of 62, side D02 41 of 43. The conclusion does not depend on the slope limit. (The remaining no-path pairs have the cause
given in §3.)

The segments of the default run (side tables and the IDs of every reference and query):

#### Side D01

| Class | Queries | Own pairs | Other pairs | Own median D | Other median D | Other / own | Own closer | Nearest correct | No path own / other |
|---|---|---|---|---|---|---|---|---|---|
| G01 | 5 | 6 | 60 | 0.0432 | 0.4079 | 9.44 | yes | 4 / 4 | 6 / 106 |
| G02 | 5 | 5 | 79 | 0.1021 | 0.3456 | 3.38 | yes | 4 / 5 | 7 / 83 |
| G03 | 5 | 4 | 71 | 0.1362 | 0.3263 | 2.40 | yes | 3 / 3 | 8 / 94 |
| G04 | 5 | 9 | 90 | 0.1446 | 0.3485 | 2.41 | yes | 4 / 4 | 3 / 72 |
| G05 | 5 | 12 | 107 | 0.1689 | 0.3529 | 2.09 | yes | 5 / 5 | 0 / 58 |
| G06 | 5 | 12 | 104 | 0.2006 | 0.3463 | 1.73 | yes | 4 / 5 | 0 / 65 |
| G07 | 5 | 5 | 74 | 0.1809 | 0.3660 | 2.02 | yes | 4 / 5 | 7 / 93 |
| G08 | 5 | 10 | 100 | 0.1829 | 0.3587 | 1.96 | yes | 5 / 5 | 2 / 62 |
| G09 | 5 | 8 | 49 | 0.2043 | 0.3967 | 1.94 | yes | 4 / 5 | 4 / 116 |
| G10 | 5 | 8 | 118 | 0.2860 | 0.3642 | 1.27 | yes | 4 / 5 | 4 / 46 |
| G11 | 5 | 8 | 110 | 0.2447 | 0.4129 | 1.69 | yes | 4 / 5 | 4 / 57 |
| G12 | 5 | 11 | 78 | 0.2587 | 0.3981 | 1.54 | yes | 5 / 5 | 1 / 86 |
| G13 | 5 | 12 | 54 | 0.2168 | 0.3953 | 1.82 | yes | 5 / 5 | 0 / 116 |

Classes where the own class is closer: 13 of 13 (100.0 %). Nearest-reference class correct: 55 of 61 queries (90.2 %). Pairs with a distance 1204, with no path 1100.

#### Side D02

| Class | Queries | Own pairs | Other pairs | Own median D | Other median D | Other / own | Own closer | Nearest correct | No path own / other |
|---|---|---|---|---|---|---|---|---|---|
| G05 | 5 | 12 | 72 | 0.1602 | 0.3511 | 2.19 | yes | 5 / 5 | 0 / 40 |
| G06 | 5 | 8 | 69 | 0.2001 | 0.3663 | 1.83 | yes | 5 / 5 | 4 / 43 |
| G07 | 5 | 8 | 37 | 0.1616 | 0.3641 | 2.25 | yes | 5 / 5 | 4 / 75 |
| G08 | 5 | 10 | 52 | 0.1883 | 0.3696 | 1.96 | yes | 4 / 4 | 2 / 58 |
| G09 | 5 | 12 | 17 | 0.2077 | 0.3713 | 1.79 | yes | 5 / 5 | 0 / 92 |
| G10 | 5 | 7 | 66 | 0.2298 | 0.3465 | 1.51 | yes | 4 / 5 | 5 / 44 |
| G11 | 5 | 8 | 65 | 0.2608 | 0.4151 | 1.59 | yes | 3 / 5 | 4 / 48 |
| G12 | 5 | 6 | 63 | 0.2216 | 0.4009 | 1.81 | yes | 5 / 5 | 6 / 47 |
| G13 | 5 | 9 | 25 | 0.2239 | 0.3959 | 1.77 | yes | 4 / 4 | 3 / 87 |

Classes where the own class is closer: 9 of 9 (100.0 %). Nearest-reference class correct: 40 of 43 queries (93.0 %). Pairs with a distance 546, with no path 562.

#### Segments used

| Class | Side | References | Queries |
|---|---|---|---|
| G01 | D01 | P09T01C01G01D01S01, P10T01C01G01D01S01, P12T01C01G01D01S01 | P05T01C02G01D01S01, P07T01C03G01D01S01, P09T01C02G01D01S01, P10T01C02G01D01S01, P12T01C02G01D01S01 |
| G02 | D01 | P03T01C05G02D01S01, P06T01C03G02D01S01, P07T01C03G02D01S01 | P03T01C02G02D01S01, P06T01C01G02D01S01, P07T01C01G02D01S01, P10T01C01G02D01S01, P12T01C01G02D01S01 |
| G03 | D01 | P02T01C05G03D01S02, P05T01C02G03D01S03, P12T01C01G03D01S02 | P02T01C05G03D01S03, P05T01C01G03D01S01, P07T01C01G03D01S01, P11T01C02G03D01S01, P12T01C02G03D01S02 |
| G04 | D01 | P02T01C04G04D01S04, P06T01C02G04D01S04, P10T01C01G04D01S03 | P02T01C05G04D01S04, P06T01C03G04D01S01, P10T01C01G04D01S04, P11T01C01G04D01S02, P12T01C01G04D01S01 |
| G05 | D01 | P03T01C05G05D01S01, P06T01C01G05D01S01, P10T01C01G05D01S02 | P01T01C04G05D01S02, P03T01C02G05D01S01, P04T01C03G05D01S01, P06T01C02G05D01S02, P10T01C02G05D01S01 |
| G05 | D02 | P07T01C01G05D02S01, P08T01C01G05D02S02, P11T01C02G05D02S01 | P03T01C05G05D02S01, P05T01C01G05D02S02, P07T01C03G05D02S02, P08T01C02G05D02S01, P11T01C01G05D02S02 |
| G06 | D01 | P04T02C02G06D01S01, P05T02C04G06D01S01, P07T03C02G06D01S01 | P03T02C14G06D01S03, P04T03C02G06D01S01, P05T03C02G06D01S01, P07T02C03G06D01S01, P11T03C02G06D01S01 |
| G06 | D02 | P02T02C09G06D02S01, P09T03C01G06D02S02, P11T02C04G06D02S02 | P02T02C07G06D02S02, P03T02C12G06D02S01, P07T02C03G06D02S01, P09T02C02G06D02S01, P11T02C04G06D02S01 |
| G07 | D01 | P04T02C03G07D01S02, P07T03C01G07D01S01, P11T02C04G07D01S01 | P03T03C01G07D01S01, P04T03C02G07D01S01, P07T02C03G07D01S02, P10T02C03G07D01S01, P11T02C01G07D01S01 |
| G07 | D02 | P08T03C02G07D02S02, P09T03C02G07D02S01, P10T02C03G07D02S01 | P03T02C08G07D02S01, P07T02C01G07D02S02, P08T03C01G07D02S02, P09T02C02G07D02S02, P10T03C01G07D02S02 |
| G08 | D01 | P02T02C05G08D01S01, P04T02C03G08D01S01, P12T02C01G08D01S01 | P02T02C09G08D01S01, P04T02C02G08D01S01, P06T02C02G08D01S02, P11T02C01G08D01S02, P12T02C01G08D01S02 |
| G08 | D02 | P03T02C02G08D02S01, P07T03C01G08D02S01, P12T02C04G08D02S01 | P02T02C07G08D02S02, P03T02C02G08D02S02, P07T03C02G08D02S01, P08T03C02G08D02S02, P12T03C03G08D02S01 |
| G09 | D01 | P02T02C05G09D01S02, P06T02C02G09D01S01, P08T03C02G09D01S01 | P02T02C05G09D01S01, P06T02C02G09D01S02, P07T02C01G09D01S02, P08T02C03G09D01S01, P09T03C02G09D01S01 |
| G09 | D02 | P08T02C03G09D02S01, P11T02C02G09D02S02, P12T02C04G09D02S02 | P03T02C02G09D02S02, P07T02C03G09D02S02, P08T03C02G09D02S01, P11T02C02G09D02S01, P12T02C02G09D02S01 |
| G10 | D01 | P02T02C05G10D01S01, P07T02C03G10D01S01, P12T02C04G10D01S01 | P01T02C05G10D01S02, P02T02C07G10D01S01, P05T02C04G10D01S02, P07T02C01G10D01S02, P12T03C03G10D01S01 |
| G10 | D02 | P02T02C09G10D02S02, P04T02C02G10D02S01, P12T03C01G10D02S01 | P01T02C05G10D02S02, P02T02C05G10D02S01, P04T03C01G10D02S01, P09T03C02G10D02S01, P12T02C02G10D02S02 |
| G11 | D01 | P01T02C04G11D01S01, P06T02C01G11D01S01, P12T02C05G11D01S02 | P01T02C07G11D01S01, P03T02C11G11D01S01, P06T03C01G11D01S01, P08T02C04G11D01S02, P12T02C03G11D01S02 |
| G11 | D02 | P01T02C04G11D02S02, P05T03C01G11D02S01, P10T02C04G11D02S01 | P01T02C07G11D02S02, P05T02C03G11D02S02, P07T02C04G11D02S02, P09T03C02G11D02S01, P10T03C04G11D02S01 |
| G12 | D01 | P02T02C08G12D01S02, P03T02C15G12D01S02, P10T02C04G12D01S02 | P02T02C10G12D01S01, P03T03C01G12D01S01, P06T02C01G12D01S01, P10T02C02G12D01S02, P11T02C02G12D01S02 |
| G12 | D02 | P01T02C04G12D02S02, P03T02C11G12D02S02, P12T02C02G12D02S01 | P01T02C07G12D02S02, P03T02C13G12D02S02, P04T03C02G12D02S01, P10T02C02G12D02S01, P12T02C02G12D02S02 |
| G13 | D01 | P01T02C05G13D01S01, P04T02C02G13D01S02, P09T03C01G13D01S02 | P01T02C04G13D01S02, P04T02C03G13D01S01, P08T03C01G13D01S02, P09T02C03G13D01S01, P10T03C02G13D01S02 |
| G13 | D02 | P01T02C04G13D02S02, P04T02C03G13D02S02, P06T02C01G13D02S02 | P01T02C07G13D02S01, P04T03C01G13D02S01, P05T03C01G13D02S01, P06T03C02G13D02S01, P12T03C01G13D02S02 |

## 3. Boundaries: segment boundaries carried through the warping path

Pairs: 131 label files, 111 recordings (all labelled); pairs of one capture and two performers: 1,003, of which **55
have equal label sequences** and 948 differ (left out, plan Q4). 40 of the 55 were sampled with seed 1. For each, the
whole recordings are aligned (3,000 to 12,000 grid rows), every labelled non-rest part of the reference is carried
through `Alignment.matched_query_times()` and compared with the part of the same rank of the query: temporal IoU and the
error of the start and of the end in seconds (moved minus the query's own label). 276 parts were measured (168 `ex`, 108
`tech`); none was open (the last label of every file is a rest) and none lay outside the reference clock. A reference
line is shown: **uniform scaling** of the clock (the span of the reference mapped linearly to the span of the query, no
warping).

**Pairs with no path: 23 of the 40, at band 0.1 and at band 0.2 (the same 23).** Only 3 of them are the 2 to 1 length
limit. The other 20 have the same cause as the rest: each of the 23 includes a recording that has at least one grid row
with **fewer than 11 valid units** (a row of the cost where every cell is `+inf`, because tracking dropped), and
neither a band nor a step pattern can cross a row of `+inf` cells: DTW cannot skip a frame. None of the 17 pairs that
have a path has such a row; 18 of the 39 recordings used have such rows (up to 39 rows). So **the 17 pairs measured are
the pairs whose recordings are free of tracking drops**, not a random half. This is reported to the coordinator as an
observation about the chain (task file, section 7), not tuned away here.

Band 0.1 (the plan's setting for whole recordings):

#### Temporal IoU and boundary errors (seconds; moved minus the query's own label)

| Family | Transfer | Parts | IoU median | IoU mean | IoU >= 0.5 | Start abs median | Start abs p90 | End abs median | End abs p90 | Start bias | End bias |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all | warping path | 276 | 0.864 | 0.706 | 80.4 % | 0.527 | 9.879 | 0.595 | 10.669 | -0.243 | -0.288 |
| all | uniform scaling | 276 | 0.205 | 0.291 | 28.6 % | 5.353 | 21.017 | 5.384 | 21.947 | -2.816 | -3.298 |
| ex | warping path | 168 | 0.901 | 0.724 | 79.8 % | 0.407 | 10.384 | 0.490 | 10.621 | -0.128 | -0.217 |
| ex | uniform scaling | 168 | 0.145 | 0.255 | 19.6 % | 6.509 | 20.045 | 6.821 | 20.493 | -4.978 | -5.308 |
| tech | warping path | 108 | 0.769 | 0.678 | 81.5 % | 0.744 | 6.484 | 0.733 | 9.711 | -0.435 | -0.432 |
| tech | uniform scaling | 108 | 0.306 | 0.346 | 42.6 % | 3.871 | 28.817 | 3.878 | 30.530 | -0.032 | -0.283 |

Band 0.2 (a sensitivity run on the same 40 pairs, reported because 0.1 is narrow for recordings of thousands of rows;
neither run is preferred, and the band did not change which pairs have a path):

#### Temporal IoU and boundary errors (seconds; moved minus the query's own label)

| Family | Transfer | Parts | IoU median | IoU mean | IoU >= 0.5 | Start abs median | Start abs p90 | End abs median | End abs p90 | Start bias | End bias |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all | warping path | 276 | 0.888 | 0.783 | 88.8 % | 0.452 | 2.326 | 0.501 | 2.369 | -0.118 | -0.177 |
| all | uniform scaling | 276 | 0.205 | 0.291 | 28.6 % | 5.353 | 21.017 | 5.384 | 21.947 | -2.816 | -3.298 |
| ex | warping path | 168 | 0.909 | 0.824 | 90.5 % | 0.302 | 2.332 | 0.426 | 2.453 | -0.051 | -0.111 |
| ex | uniform scaling | 168 | 0.145 | 0.255 | 19.6 % | 6.509 | 20.045 | 6.821 | 20.493 | -4.978 | -5.308 |
| tech | warping path | 108 | 0.809 | 0.719 | 86.1 % | 0.705 | 2.296 | 0.703 | 2.309 | -0.384 | -0.358 |
| tech | uniform scaling | 108 | 0.306 | 0.346 | 42.6 % | 3.871 | 28.817 | 3.878 | 30.530 | -0.032 | -0.283 |

Reading: for the pairs that have a path, half of the boundaries land within about half a second of the query's own
label (median errors 0.53 and 0.60 s at band 0.1, 0.45 and 0.50 s at band 0.2; the Kinect step is 33 ms). The tails
depend on the band: at band 0.1, 80.4 % of the parts reach an IoU of 0.5, the 90th percentile of the error is about 10 s,
39 parts have an IoU below 0.1 (37 exactly 0) and 38 parts have a start error above 5 s; at band 0.2, 88.8 % reach 0.5,
the 90th percentile is 2.3 to 2.4 s, 15 parts are below 0.1 and 16 have a start error above 5 s. In both runs the gross
errors come from the same 5 of the 17 pairs (a repeated movement matched to its neighbour) while most pairs are close.
The band is a run setting, not tuned here: 0.1 is the plan's, 0.2 is the setting of the segment runs and of the golden
tests of P6.03b; both are reported and none is a recommendation. Uniform scaling is far worse (median error about 5 s),
but performers start the routine at different times, so that line is a weak reference and "warping beats scaling"
should not be read as a measured benefit for a coach.

The pairs of the band 0.1 run (IDs, status, `D`, parts measured, lengths in grid rows):

#### Pairs

| Reference | Query | Status | D | Parts | Open | Outside | Reference rows | Query rows |
|---|---|---|---|---|---|---|---|---|
| P01T02C03 | P07T02C03 | no_path | n/a | 0 | 0 | 0 | 6003 | 6516 |
| P01T02C03 | P08T02C03 | ok | 0.1710 | 20 | 0 | 0 | 6003 | 6598 |
| P01T02C03 | P10T02C03 | ok | 0.2021 | 20 | 0 | 0 | 6003 | 9584 |
| P01T02C03 | P10T03C03 | no_path | n/a | 0 | 0 | 0 | 6003 | 7285 |
| P02T01C04 | P03T01C04 | no_path | n/a | 0 | 0 | 0 | 5715 | 4732 |
| P03T01C01 | P09T01C01 | ok | 0.1565 | 14 | 0 | 0 | 5903 | 4515 |
| P03T01C01 | P10T01C01 | ok | 0.1736 | 14 | 0 | 0 | 5903 | 6233 |
| P03T01C01 | P11T01C01 | ok | 0.1775 | 14 | 0 | 0 | 5903 | 4905 |
| P03T01C02 | P08T01C02 | ok | 0.1340 | 14 | 0 | 0 | 5572 | 4337 |
| P03T01C02 | P09T01C02 | ok | 0.1192 | 14 | 0 | 0 | 5572 | 3940 |
| P03T01C02 | P10T01C02 | ok | 0.1384 | 14 | 0 | 0 | 5572 | 6422 |
| P03T03C01 | P06T03C01 | no_path | n/a | 0 | 0 | 0 | 5947 | 3908 |
| P03T03C01 | P07T03C01 | no_path | n/a | 0 | 0 | 0 | 5947 | 5062 |
| P03T03C01 | P11T03C01 | no_path | n/a | 0 | 0 | 0 | 5947 | 9296 |
| P04T01C02 | P06T01C02 | no_path | n/a | 0 | 0 | 0 | 4627 | 4561 |
| P04T01C03 | P06T01C03 | ok | 0.1150 | 14 | 0 | 0 | 4716 | 4472 |
| P04T03C02 | P06T03C02 | ok | 0.1871 | 16 | 0 | 0 | 4044 | 4134 |
| P04T03C02 | P07T03C02 | no_path | n/a | 0 | 0 | 0 | 4044 | 5248 |
| P04T03C02 | P11T03C02 | no_path | n/a | 0 | 0 | 0 | 4044 | 9570 |
| P06T01C03 | P07T01C03 | ok | 0.1259 | 14 | 0 | 0 | 4472 | 3315 |
| P06T03C01 | P07T03C01 | no_path | n/a | 0 | 0 | 0 | 3908 | 5062 |
| P06T03C01 | P11T03C01 | no_path | n/a | 0 | 0 | 0 | 3908 | 9296 |
| P06T03C02 | P11T03C02 | no_path | n/a | 0 | 0 | 0 | 4134 | 9570 |
| P07T02C01 | P08T02C01 | no_path | n/a | 0 | 0 | 0 | 6551 | 7369 |
| P07T02C01 | P10T03C01 | no_path | n/a | 0 | 0 | 0 | 6551 | 8060 |
| P07T02C02 | P08T02C02 | no_path | n/a | 0 | 0 | 0 | 6102 | 6230 |
| P07T02C03 | P08T02C03 | no_path | n/a | 0 | 0 | 0 | 6516 | 6598 |
| P07T02C03 | P10T03C03 | no_path | n/a | 0 | 0 | 0 | 6516 | 7285 |
| P07T02C04 | P08T02C04 | no_path | n/a | 0 | 0 | 0 | 5603 | 5827 |
| P07T02C04 | P10T02C04 | no_path | n/a | 0 | 0 | 0 | 5603 | 8991 |
| P07T03C01 | P11T03C01 | no_path | n/a | 0 | 0 | 0 | 5062 | 9296 |
| P07T03C02 | P11T03C02 | no_path | n/a | 0 | 0 | 0 | 5248 | 9570 |
| P08T02C03 | P10T02C03 | ok | 0.1911 | 20 | 0 | 0 | 6598 | 9584 |
| P08T02C03 | P10T03C03 | no_path | n/a | 0 | 0 | 0 | 6598 | 7285 |
| P08T03C01 | P09T03C01 | ok | 0.2776 | 32 | 0 | 0 | 12196 | 8265 |
| P09T01C01 | P10T01C01 | ok | 0.1093 | 14 | 0 | 0 | 4515 | 6233 |
| P09T01C01 | P11T01C01 | ok | 0.1182 | 14 | 0 | 0 | 4515 | 4905 |
| P09T01C02 | P10T01C02 | ok | 0.1437 | 14 | 0 | 0 | 3940 | 6422 |
| P09T01C02 | P11T01C02 | no_path | n/a | 0 | 0 | 0 | 3940 | 4166 |
| P10T01C01 | P11T01C01 | ok | 0.1416 | 14 | 0 | 0 | 6233 | 4905 |

## 4. What these numbers do not say

- They are **out of domain**: 13 basic techniques, a clean Kinect skeleton, performers of four levels; not 24-form video
  pose with occlusions and a moving camera. No threshold or conclusion for the product follows (AGENTS.md §5.5).
- Classes: a seeded sample (3 references and 5 queries per class and side), medians over pairs that share references, so
  the pairs are not independent; 12 performers; the "own class is closer" result is per class median, not per query.
  The pairs with no path are left out of the medians and counted, own and other apart.
- Boundaries: the labels are the dataset's own annotation, taken as truth without a second look; the 17 pairs with a
  path are the recordings without tracking drops; 40 pairs reuse recordings (39 distinct); the errors are of onsets of
  parts of basic techniques, not of the key frames of a form.
- The class IDs, sides and repetitions are the README's inference; the label times are assumed to start at the first
  Kinect row.
- Distances `D` of different pairs are not compared outside one setting (the settings are echoed in every table and CSV).

## 5. Re-running

From `taiji_ai/` (the CSV of each run goes to `--out`, which git ignores; the dataset is read through the project's own
parsers only):

```text
python tools/umons_compare.py classes    --umons ../datasets/taiji/umons --out data/reports/p6_07/classes    --report data/reports/p6_07/classes.md
python tools/umons_compare.py classes    --umons ../datasets/taiji/umons --out data/reports/p6_07/classes_symmetric1 --report data/reports/p6_07/classes_symmetric1.md --step symmetric1
python tools/umons_compare.py boundaries --umons ../datasets/taiji/umons --out data/reports/p6_07/boundaries --report data/reports/p6_07/boundaries.md
python tools/umons_compare.py boundaries --umons ../datasets/taiji/umons --out data/reports/p6_07/boundaries_band02 --report data/reports/p6_07/boundaries_band02.md --band 0.2
```
