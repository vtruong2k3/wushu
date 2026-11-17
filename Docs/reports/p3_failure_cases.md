# P3.08 — Failure cases of the pose on real footage

**Status: reviewed by the agent and then by the maintainer (H), who looked at all 250 rows, agreed with 249 and changed one
(`fc-161`, failure to ok).** The numbers are regenerated from `review.csv` by `tools/pose_audit.py report`. The agreement of
99.6 % says that H and the agent saw the same frames the same way; it does not say that both are right (one second person
would be needed for that). Date of the review: 2026-11-16.
Task file: `Docs/tasks/P3.08.md`. Decisions: DEC-0039 (rules of the review), DEC-0041 (the two markers).

## 1. What was done

- **Footage:** the four web lesson videos of the registry (D20, `dev-test`, technical use; DEC-0036, DEC-0039), labelled
  `d20-v1` to `d20-v4`: three or more performers, a fixed camera most of the time, but cuts, close-ups, fades and dissolves. It is not
  our capture (P1.09 does not exist yet): the numbers are a first look, to be repeated on our own clips (follow-up X.28).
- **Passes:** the whole of every video, in chunks of 300 s, at the detector cadence N = 1 and at N = 5, same frames
  (157 366 frames inside the segments). The target is the most persistent large person of each chunk (the product asks the
  user; the review has no user), followed by the rules of P3.06.
- **Frames chosen without a threshold:** 11 rules, the worst 20 frames of each, at least 2 s apart and spread over the videos
  by the time each covers, plus 40 frames drawn blind (uniform in time, from tracked frames no rule had taken), 250 frames in
  all. The rules are sampling aids; only the blind sample estimates a rate.
- **Labels:** each frame has a verdict (`ok` or `failure`), a failure type, the wrong joints, a severity (S1 a limb on the
  wrong side, on another body part, or no person; S2 a joint visibly off; S3 minor or not checkable, listed and **not
  counted**), the view, the situation and the cadence (`both`, `n5_only`, `n1_only`, `unknown`). The vocabulary was fixed before
  looking (DEC-0039). The score of the wrong joints comes from the data, never from the reviewer.
- **Who looked:** first the agent's part: six agent reviewers each labelled about 42 frames on tiles of 520 px with both skeletons
  drawn; the lead agent then re-checked at that size every one of the 62 failures counted at that time, the frames the reviewers called
  `back`, and a sample of `ok` frames, and added two **markers** in the note (DEC-0041): `[track]` (the performer is in the
  picture with 25 to 26 valid keypoints in the raw pose, but the target link is lost: a tracker event, not a pose failure; the
  numbers of the raw pose were read for each of those frames) and `[edit]` (a fade, a dissolve or a title of the video
  editing: not a capture). Nothing was dropped: the tables keep every frame and show the markers apart. Then the maintainer
  (H) went through all 250 rows on a local page (the picture, the agent's label and the scores of the wrong joints; Agree or
  Change): 249 agreed, one changed (`fc-161`: the agent had seen the left foot drawn on the front foot at N = 1; H found the
  skeleton right). The agreement table is in section 6.
- Left and right: a frame in which the person faces the camera has the person's **right** side on the **left** of the
  image, and a person seen from behind has it on the **right** (checked on frames where the person was clearly front or back).
  In profile, the side of a limb was judged from the neighbouring frames of the same stance; those labels are the least certain.

## 2. What the numbers say

All figures are in the tables of section 4. Each sentence names the table it comes from.

1. **How often the pose fails on this footage.** In the 40 blind frames, 2 failed (5.0 %, Wilson 95 % interval 1.4 % to
   16.5 %); none of the blind frames is an `[edit]` frame, so the rate is the same without them. With 40 frames the interval is
   wide: it says the rate is probably below one frame in six, nothing more.
2. **Where the failures are.** 61 frames are counted failures (S1, S2); 15 of them are `[track]` events and 13 are in `[edit]`
   frames; **34 are pose failures of ordinary frames** (11 S1, 23 S2). They are concentrated: 23 of the 34 are in `d20-v4`
   (105 of the 250 frames: a performer in white doing lunges seen from the side, in front of a wall and a hedge), 7 in `d20-v2`,
   2 in `d20-v1`, 2 in `d20-v3`. The types of the 61: `joint_off` 22, `lr_swap` 11, `foot_error` 8, `flicker` 4,
   `missed_person` 1 (a dark frame at N = 1 only), `other` 15 (the `[track]` frames). Seventeen more frames are `hidden_guess`
   (a joint hidden behind the body or another limb, drawn on a plausible spot that cannot be checked): S3, listed, not counted.
3. **The four situations of the plan.** The frames of a hand over the trunk, a turning trunk, one leg and the back to the
   camera were found and reviewed, and they were **not** where the failures are: `occlusion` 35 frames and 2 failures,
   `orientation_change` 7 and 0, `one_leg` 36 and 3, `back` 37 and 5 (tables "by situation" and "by view"). The finders for
   them had a precision of 0 to 5 % (`find_occlusion` 0 of 20, `find_rotation` 0 of 20, `find_back` 1 of 20, `find_one_leg` 1
   of 20). The rules that did find failures were `target_event` (17 of 20, mostly the tracker), `cadence_diff` (12 of 20),
   `jump` (8), `bone` (8), `swap_pair` (8), `low_essential` (7). **This does not show that those situations are safe**: 20 to 37
   frames each, one kind of footage, and a hidden joint is not a failure here but a `hidden_guess` that nobody can check.
4. **The score does not warn.** Of the 34 failures of ordinary frames that name joints, **none** would have been removed by a
   mask at `tau_kp = 0.3`: in every one, at least one wrong joint scores 0.3 or more (table "Does the score warn?"). The
   highest score of a wrong joint is 0.3 to 0.5 in 10 failures, 0.5 to 0.7 in 13, 0.7 to 0.9 in 10 and 0.9 or more in 1; the
   median is 0.67. All 17 `hidden_guess` rows also score high (the case table). Over all 45 failures that name joints, the
   mask would have removed 3, all of them in `[edit]` frames.
5. **Left and right.** 11 failures are `lr_swap` (8 in ordinary frames). They are legs in side and oblique lunge frames of
   `d20-v4` (6 of the 8), one pair of legs in `d20-v1` and one ankle in `d20-v2`, and the labels flip between frames 0.3 s apart in the same stance (for
   example `fc-216` and `fc-217`, `fc-227` and `fc-228`), so a swap can be seen in time, not in the score. Four more
   frames are `flicker`. Eleven of the 37 back-view frames were re-checked by the lead for a whole-body swap and none showed
   one; the other 26 rest on the reviewers.
6. **The detector cadence.** Among the 61 counted failures: `both` 36, `n1_only` 10, `n5_only` 5, `unknown` 10. Failures
   that appear only at N = 1 are more numerous than those that appear only at N = 5, so this review gives **no evidence that
   N = 1 removes failures** (the rule of P3.07 recommends N = 1 from keypoint differences; this review looked at labelled
   frames). The sample is biased by construction (the rules look at N = 1 and at the difference) and 10 cases are `unknown`.
   The maintainer kept the default N = 5 (DEC-0042).
7. **The tracker.** In 15 of the 20 `target_event` frames the performer is in the picture with 25 to 26 valid keypoints and the
   target is lost in both passes (two frames only at N = 1). They are after cuts and close-ups, or with the performer far from
   the camera. It is the behaviour designed in DEC-0037 (no re-attachment when the cost is over the limit, ask the user), not a
   defect found here, but it means that on footage with cuts 38 % to 56 % of the frames of a video are not tracked
   (task file P4.01, M-QLT-01: tracked 44 % to 62 % of the frames per video).

## 3. What it means for the next tasks

- **P4.01 (mask, `tau_kp`):** the mask at 0.3 is needed (it removes what is not observed) but is **not a quality filter**: it
  did not remove any failure of an ordinary frame. A higher `tau_kp` would remove more, at a cost measured on the same tracks
  (task file P4.01, M-QLT-01 at other values, nothing tuned): at 0.5 it excludes 0.5 % to 1.7 % of the joint cells and makes 22
  of 86 303 tracked frames invalid; at 0.7 it excludes 8 % to 19 % of the joint cells and makes 3.95 % of the tracked frames
  invalid (7.3 % in `d20-v4`); at 0.9 it blanks almost everything (the scores of this performer mostly lie between 0.7 and
  0.9). A threshold of 0.7 would take the highest wrong score under it in 23 of the 34 failures, **and** exclude 8 % to 19 %
  of all joint cells, almost all of them right. **No
  change of `tau_kp` or of the essential joints is proposed**: the maintainer kept 0.3 as a hygiene threshold
  (DEC-0042). No frame is `frame_invalid` at 0.3, so the essential list is not stressed by this footage.
- **P4.06 (left/right swap flag):** the swaps that were found are legs in side lunges, flipping between neighbouring
  frames; a detector on the time series of the pairs (the `swap_pair` signal of this review had a precision of 40 %) is the
  base, and the score cannot replace it. The metrics of W7 use mid-points and symmetric groups, so a leg swap changes them
  little; `joint_off` of the feet matters more (24 failures name the feet group; the hip-height
  variant with a ground reference uses the lowest foot point). To be checked when P5 is written, not claimed here.
- **P3.06 / P7 / P8 (target):** on footage with cuts, the performer is lost at a cut and must be chosen again; the UI of P8
  must ask. The `[track]` frames list the moments (case table, type `other`).
- **P1.09 and the capture protocol (hypotheses, for the maintainer and the coach):** the failures of this footage are in
  profile views with the legs together, not in the four situations of the plan; our own clips should be reviewed the same way
  (X.28) before a view limit is written; a clip without cuts and with the performer at one size would remove the `[track]`
  and `[edit]` frames from the question.
- **Metric records (v3 section 8.2):** nothing here sets a threshold. A metric that depends on a wrist, an elbow or a foot
  needs its own check against labels (the 200-frame audit of W8.1, later); a wrong joint with a score of 0.7 or more is not
  visible in the coverage.

## 4. Limits and what was not found

- Labels by the agent and one person (H); H agreed with 249 of 250, so the two opinions are not independent evidence of each
  other's errors. Eye judgement at 520 px, a joint "visibly off" means more than about a hand width; a hidden joint cannot be
  judged and is `hidden_guess`; left and right in profile views are judged from neighbouring frames.
- One kind of footage (lessons, three or more performers, cuts and fades), 250 frames chosen to find failures: only the blind
  sample estimates a rate, and it has 40 frames. No accuracy is given and no threshold is set.
- Of the frames the reviewers called `ok`, the lead looked at a sample, not at all of them; H looked at all of them, including
  the 49 `ok` rows that carry an `unsure:` note.
- The target is the review's rule (most persistent large person), not the product's default; only `tracked` frames can be
  candidates of a pose rule, so frames of the performer after a loss are not in the sample (44 % to 62 % of the frames are
  tracked per video).
- Not found: a failure in the four situations that the finders pointed at (the finders were poor, see section 2, point 3); no
  `wrong_person` (a skeleton on someone else) in the 250 frames; no whole-body left/right swap in the back-view frames that were
  re-checked.

## 5. To reproduce

```text
python tools/pose_audit.py pose --video-dir ../video --out data/reports/p3_08 --work-dir data/bench/p3_08 --n 1
python tools/pose_audit.py pose --video-dir ../video --out data/reports/p3_08/n5 --work-dir data/bench/p3_08 --n 5
python tools/pose_audit.py analyse      # the 250 frames, the sheets and an empty review.csv
python tools/pose_audit.py report       # the tables below, from the filled review.csv
```

Images, pose files and `review.csv` stay in `data/` (ignored by git); this report holds counts, IDs, video labels, times and
frame indices only.

## 6. Generated tables

The tables below are the output of `report` (`report_tables.md`), unchanged.

### The frames reviewed

| Frames | Failures (S1, S2) | Minor (S3) | Ok |
| --- | --- | --- | --- |
| 250 | 61 | 17 | 172 |

### Frames that are not an ordinary pose question (markers in the notes; nothing is dropped)

| Marker | Meaning | Frames | Failures among them |
| --- | --- | --- | --- |
| [track] | performer in the picture with a good skeleton, target link lost (tracker event) | 15 | 15 |
| [edit] | fade, dissolve or title of the video editing (not a capture) | 19 | 13 |

Failures (S1, S2) without the [track] frames: 46. Pose failures of ordinary frames (neither marker): 34.

### Frames and failures by video (frames reviewed in the sample, not a rate)

| Video | Frames | Failures (S1, S2) | Pose failures of ordinary frames |
| --- | --- | --- | --- |
| d20-v1 | 42 | 5 | 2 |
| d20-v2 | 40 | 10 | 7 |
| d20-v3 | 63 | 7 | 2 |
| d20-v4 | 105 | 39 | 23 |

### Agreement of the person with the agent (over the rows the person looked at)

| Field | Rows looked at | Agree | Share |
| --- | --- | --- | --- |
| verdict | 250 | 249 | 99.6 % |
| type | 250 | 250 | 100.0 % |
| joints | 250 | 250 | 100.0 % |
| severity | 250 | 250 | 100.0 % |
| view | 250 | 250 | 100.0 % |
| situation | 250 | 250 | 100.0 % |
| cadence | 250 | 250 | 100.0 % |
| note | 250 | 250 | 100.0 % |

### Precision of each rule (failures among the frames the rule took)

| Rule | Frames | Failures | Precision |
| --- | --- | --- | --- |
| blind | 40 | 2 | 5.0 % |
| bone | 20 | 8 | 40.0 % |
| cadence_diff | 20 | 12 | 60.0 % |
| find_back | 20 | 1 | 5.0 % |
| find_occlusion | 20 | 0 | 0.0 % |
| find_one_leg | 20 | 1 | 5.0 % |
| find_rotation | 20 | 0 | 0.0 % |
| jump | 20 | 8 | 40.0 % |
| low_essential | 20 | 7 | 35.0 % |
| structure | 20 | 3 | 15.0 % |
| swap_pair | 20 | 8 | 40.0 % |
| target_event | 20 | 17 | 85.0 % |

### The blind sample (frames no rule pointed at): the only estimate of how often the pose fails

| Sample | Frames | Failures | Rate | Wilson 95 % interval |
| --- | --- | --- | --- | --- |
| all blind frames | 40 | 2 | 5.0 % | 1.4 % to 16.5 % |
| without [edit] frames | 40 | 2 | 5.0 % | 1.4 % to 16.5 % |

### Failures by type

| Type | Failures |
| --- | --- |
| lr_swap | 11 |
| joint_off | 22 |
| hidden_guess | 0 |
| foot_error | 8 |
| flicker | 4 |
| wrong_person | 0 |
| missed_person | 1 |
| other | 15 |

### Failures by view (frames reviewed in the sample, not a rate)

| Value | Frames | Failures |
| --- | --- | --- |
| front | 62 | 11 |
| side | 81 | 25 |
| oblique | 58 | 12 |
| back | 37 | 5 |
| unknown | 12 | 8 |

### Failures by situation (frames reviewed in the sample, not a rate)

| Value | Frames | Failures |
| --- | --- | --- |
| none | 172 | 56 |
| occlusion | 35 | 2 |
| orientation_change | 7 | 0 |
| one_leg | 36 | 3 |

### Failures by joint group (a failure counts in every group it names)

| Group | Failures |
| --- | --- |
| head | 5 |
| trunk | 5 |
| arms | 20 |
| legs | 20 |
| feet | 24 |

### Does the score warn? (a mask at tau_kp = 0.3 would remove every wrong joint)

| Failures | That name joints | Removed by the mask | Kept by the mask | Share kept |
| --- | --- | --- | --- | --- |
| all failures | 45 | 3 | 42 | 93.3 % |
| ordinary frames only | 34 | 0 | 34 | 100.0 % |

### How high is the score of the wrong joints? (ordinary failures that name joints)

| Highest score of a wrong joint | Failures |
| --- | --- |
| under 0.3 | 0 |
| 0.3 to 0.5 | 10 |
| 0.5 to 0.7 | 13 |
| 0.7 to 0.9 | 10 |
| 0.9 or more | 1 |
| median | 0.67 |

A mask removes every wrong joint of a failure only if `tau_kp` is above its highest wrong score.

### Failures that depend on the detector cadence

| Cadence label | Failures |
| --- | --- |
| both | 36 |
| n1_only | 10 |
| n5_only | 5 |
| unknown | 10 |

### Every failure case (S3 is minor and not counted)

| ID | Video | Time [s] | Frame | Type | Joints | Sev | View | Situation | Cadence | Score warns | Rules |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fc-008 | d20-v1 | 129.42 | 3106 | hidden_guess | LElbow | S3 | side | none | unknown | no | cadence_diff |
| fc-014 | d20-v1 | 277.92 | 6670 | lr_swap | legs | S1 | oblique | none | both | no | swap_pair |
| fc-024 | d20-v1 | 627.58 | 15062 | joint_off | RElbow, RWrist | S2 | side | none | unknown | no | cadence_diff |
| fc-033 | d20-v1 | 745.54 | 17893 | other | - | S1 | oblique | none | n1_only | n/a | target_event |
| fc-034 | d20-v1 | 761.58 | 18278 | other | - | S1 | side | none | n1_only | n/a | target_event |
| fc-035 | d20-v1 | 863.96 | 20735 | other | - | S1 | front | none | both | n/a | target_event |
| fc-049 | d20-v2 | 438.21 | 10517 | hidden_guess | RKnee, RAnkle, RBigToe, RSmallToe, RHeel | S3 | oblique | none | unknown | no | low_essential |
| fc-050 | d20-v2 | 450.00 | 10800 | hidden_guess | RElbow, RWrist | S3 | back | none | unknown | no | find_back |
| fc-053 | d20-v2 | 563.29 | 13519 | hidden_guess | LElbow, LWrist | S3 | side | none | unknown | no | swap_pair |
| fc-054 | d20-v2 | 565.79 | 13579 | hidden_guess | LShoulder, LElbow, LWrist | S3 | side | none | unknown | no | bone |
| fc-055 | d20-v2 | 587.04 | 14089 | joint_off | LElbow, LWrist | S2 | front | occlusion | both | no | structure |
| fc-056 | d20-v2 | 665.50 | 15972 | lr_swap | RAnkle | S1 | side | none | n5_only | no | cadence_diff |
| fc-058 | d20-v2 | 688.79 | 16531 | joint_off | LWrist | S2 | side | none | unknown | no | cadence_diff |
| fc-059 | d20-v2 | 688.88 | 16533 | flicker | LElbow, LWrist | S2 | side | none | unknown | no | jump |
| fc-060 | d20-v2 | 698.46 | 16763 | hidden_guess | LElbow, LWrist | S3 | side | none | unknown | no | swap_pair |
| fc-062 | d20-v2 | 739.50 | 17748 | joint_off | RAnkle, RHeel, RBigToe, RSmallToe | S2 | oblique | one_leg | both | no | low_essential |
| fc-068 | d20-v2 | 792.29 | 19015 | hidden_guess | RElbow, RWrist | S3 | side | none | unknown | no | swap_pair |
| fc-070 | d20-v2 | 843.83 | 20252 | other | - | S1 | front | none | both | n/a | target_event |
| fc-071 | d20-v2 | 883.96 | 21215 | other | - | S1 | side | none | both | n/a | target_event |
| fc-072 | d20-v2 | 888.58 | 21326 | other | - | S1 | side | none | both | n/a | target_event |
| fc-073 | d20-v2 | 905.42 | 21730 | joint_off | RElbow, RWrist | S2 | side | none | unknown | no | cadence_diff |
| fc-078 | d20-v2 | 939.29 | 22543 | flicker | RElbow, RWrist | S2 | side | none | unknown | no | jump |
| fc-083 | d20-v3 | 200.00 | 4800 | hidden_guess | RElbow, RWrist | S3 | back | occlusion | unknown | no | find_occlusion |
| fc-101 | d20-v3 | 411.00 | 9864 | hidden_guess | LWrist | S3 | back | occlusion | unknown | no | find_occlusion |
| fc-111 | d20-v3 | 532.88 | 12789 | other | - | S1 | oblique | none | both | n/a | target_event |
| fc-114 | d20-v3 | 813.75 | 19530 | joint_off | RElbow, RWrist | S2 | side | none | unknown | no | blind |
| fc-121 | d20-v3 | 854.54 | 20509 | hidden_guess | LAnkle, RAnkle, feet | S3 | front | occlusion | both | no | find_occlusion |
| fc-122 | d20-v3 | 861.29 | 20671 | hidden_guess | RAnkle, RBigToe, RSmallToe, RHeel | S3 | front | occlusion | both | no | low_essential |
| fc-123 | d20-v3 | 875.46 | 21011 | other | - | S1 | oblique | one_leg | both | n/a | target_event |
| fc-124 | d20-v3 | 882.00 | 21168 | other | - | S1 | front | none | both | n/a | target_event |
| fc-125 | d20-v3 | 886.42 | 21274 | other | - | S1 | front | none | both | n/a | target_event |
| fc-126 | d20-v3 | 890.29 | 21367 | other | - | S1 | front | none | both | n/a | target_event |
| fc-142 | d20-v3 | 1164.54 | 27949 | joint_off | LElbow | S2 | side | none | both | no | bone |
| fc-145 | d20-v3 | 1281.04 | 30745 | hidden_guess | RElbow, RWrist | S3 | side | none | both | no | low_essential |
| fc-151 | d20-v4 | 205.27 | 6158 | hidden_guess | LWrist | S3 | back | none | both | no | find_occlusion |
| fc-154 | d20-v4 | 336.97 | 10109 | hidden_guess | LWrist, RWrist | S3 | back | none | both | no | find_occlusion |
| fc-158 | d20-v4 | 345.33 | 10360 | joint_off | LElbow | S2 | back | none | both | no | bone |
| fc-159 | d20-v4 | 346.57 | 10397 | hidden_guess | LElbow, LWrist | S3 | back | none | both | no | find_back |
| fc-167 | d20-v4 | 443.10 | 13293 | joint_off | head | S2 | front | none | both | no | find_back |
| fc-175 | d20-v4 | 1091.63 | 32749 | joint_off | LWrist, LElbow | S2 | oblique | occlusion | both | no | blind |
| fc-176 | d20-v4 | 1120.63 | 33619 | hidden_guess | LAnkle, LBigToe, LSmallToe, LHeel | S3 | front | none | unknown | no | structure |
| fc-183 | d20-v4 | 1187.03 | 35611 | lr_swap | RShoulder, RElbow | S1 | unknown | none | n5_only | no | low_essential |
| fc-184 | d20-v4 | 1187.07 | 35612 | lr_swap | all | S1 | unknown | none | both | no | bone |
| fc-188 | d20-v4 | 1467.90 | 44037 | joint_off | LElbow, LWrist | S2 | oblique | none | both | no | bone |
| fc-189 | d20-v4 | 1473.97 | 44219 | joint_off | LWrist, LElbow | S2 | oblique | none | both | no | structure |
| fc-192 | d20-v4 | 1739.73 | 52192 | foot_error | feet | S2 | front | none | both | yes | low_essential, jump, swap_pair, cadence_diff |
| fc-193 | d20-v4 | 1739.77 | 52193 | missed_person | - | S1 | unknown | none | n1_only | n/a | target_event |
| fc-194 | d20-v4 | 1786.80 | 53604 | other | - | S1 | side | none | both | n/a | target_event |
| fc-195 | d20-v4 | 1816.67 | 54500 | lr_swap | all | S1 | unknown | none | both | no | low_essential |
| fc-196 | d20-v4 | 1816.73 | 54502 | foot_error | LHeel, LBigToe, LSmallToe | S2 | front | none | n5_only | no | jump, swap_pair, cadence_diff |
| fc-197 | d20-v4 | 1877.47 | 56324 | joint_off | arms, legs, feet | S2 | unknown | none | both | no | bone, target_event |
| fc-200 | d20-v4 | 1891.03 | 56731 | joint_off | all | S2 | unknown | none | both | no | bone |
| fc-201 | d20-v4 | 1891.07 | 56732 | joint_off | all | S2 | unknown | none | both | no | low_essential |
| fc-205 | d20-v4 | 1922.53 | 57676 | foot_error | LHeel, LBigToe | S2 | side | none | unknown | yes | low_essential |
| fc-208 | d20-v4 | 1941.60 | 58248 | joint_off | LWrist, LElbow | S2 | back | one_leg | both | no | find_one_leg |
| fc-209 | d20-v4 | 1945.80 | 58374 | foot_error | RBigToe, RSmallToe | S2 | unknown | none | unknown | yes | low_essential |
| fc-211 | d20-v4 | 2024.00 | 60720 | other | - | S1 | oblique | none | both | n/a | target_event |
| fc-212 | d20-v4 | 2033.53 | 61006 | other | - | S1 | back | none | both | n/a | target_event |
| fc-213 | d20-v4 | 2049.37 | 61481 | other | - | S1 | back | none | both | n/a | target_event |
| fc-215 | d20-v4 | 2167.37 | 65021 | foot_error | LBigToe, LSmallToe, LHeel | S2 | front | none | n1_only | no | cadence_diff |
| fc-216 | d20-v4 | 2167.40 | 65022 | flicker | LBigToe, LSmallToe, LHeel | S2 | front | none | unknown | no | jump |
| fc-217 | d20-v4 | 2167.73 | 65032 | lr_swap | legs, feet | S1 | oblique | none | both | no | swap_pair |
| fc-218 | d20-v4 | 2211.67 | 66350 | joint_off | RKnee, RBigToe, RSmallToe, RHeel | S1 | side | none | n1_only | no | cadence_diff |
| fc-219 | d20-v4 | 2212.20 | 66366 | lr_swap | LAnkle, RKnee, RAnkle | S1 | side | none | n1_only | no | swap_pair |
| fc-223 | d20-v4 | 2258.70 | 67761 | joint_off | LKnee, RBigToe, RHeel | S1 | back | none | n5_only | no | cadence_diff |
| fc-225 | d20-v4 | 2301.13 | 69034 | flicker | RBigToe, RSmallToe, RHeel | S2 | side | none | unknown | no | jump |
| fc-226 | d20-v4 | 2302.57 | 69077 | joint_off | RWrist | S2 | side | none | n1_only | no | bone |
| fc-227 | d20-v4 | 2307.50 | 69225 | joint_off | LAnkle | S2 | side | none | n5_only | no | cadence_diff |
| fc-228 | d20-v4 | 2307.77 | 69233 | lr_swap | legs, feet | S1 | side | none | both | no | swap_pair |
| fc-229 | d20-v4 | 2307.80 | 69234 | lr_swap | legs, feet | S1 | side | none | both | no | jump |
| fc-230 | d20-v4 | 2308.97 | 69269 | joint_off | RKnee, RBigToe, RSmallToe, RHeel | S1 | side | none | both | no | bone |
| fc-233 | d20-v4 | 2332.50 | 69975 | lr_swap | legs, feet | S1 | oblique | none | n1_only | no | swap_pair |
| fc-234 | d20-v4 | 2332.70 | 69981 | joint_off | LAnkle | S2 | oblique | none | n1_only | no | cadence_diff |
| fc-235 | d20-v4 | 2346.37 | 70391 | hidden_guess | LElbow, LWrist | S3 | back | occlusion | both | no | find_occlusion |
| fc-246 | d20-v4 | 2512.87 | 75386 | foot_error | RBigToe, RSmallToe, RHeel | S2 | side | none | both | no | structure |
| fc-247 | d20-v4 | 2513.80 | 75414 | foot_error | RBigToe, RSmallToe, RHeel | S2 | side | none | n1_only | no | cadence_diff |
| fc-248 | d20-v4 | 2514.10 | 75423 | foot_error | RBigToe, RSmallToe, RHeel, RKnee | S2 | side | none | both | no | jump |
| fc-249 | d20-v4 | 2515.27 | 75458 | lr_swap | legs, feet | S1 | side | none | both | no | swap_pair |
