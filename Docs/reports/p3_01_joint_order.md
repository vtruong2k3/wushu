# P3.01 — Joint order of the pose model on real frames

Date: 2026-11-16. Task: `Docs/tasks/P3.01.md`. Verdict: **`halpe26/1` is confirmed**: the 26 indices of the model output mean what `pose/skeleton.py` says.

## Method

- Data: one web Tai Chi video of the registry (D20, H.264 1080p, 24 fps), used under DEC-0036 (internal development). Label in this report: `d20-v2`. One person is the subject.
- Five frames decoded by PTS at 120, 300, 480, 660 and 840 s (`taiji_ai.io.frames.iter_frames`); the real detector (YOLOX-m) and pose model (RTMPose-m body7-halpe26) on the GPU; the largest person is taken.
- Automatic structure check (`taiji_ai.pose.order_check`, T-POSE-04a): vertical chain, neck and hip points in the middle, left and right joints of the trunk and legs on the same side of the image,
  toes and heels near the ankle of their own side.
- Visual check (T-POSE-04, manual): an image per frame with the index of every joint, colour (red: left, blue: right, green: centre line) and a legend `index name score`, viewed by the agent.
  The images hold frames of a video: they are in `data/reports/p3_01/` (ignored by git) and not in the repository.
- Tool: `taiji_ai/tools/pose_order_check.py`.

## Result

| Time (s) | Persons found | Lowest score of the chosen person | vertical_chain | centre_points | left_right_sides | feet_near_ankles | Left joints are on the image | By eye |
| -------: | ------------: | ---------------------------------: | -------------- | ------------- | ---------------- | ---------------- | ---------------------------- | ------ |
| 120 | 1 | 0.71 | pass | pass | pass (7 pairs) | pass | right | the person faces the camera, face seen: L labels on the person's left, every name on its joint |
| 300 | 1 | 0.69 | pass | pass | pass (7 pairs) | pass | right | the person faces the camera, face seen: same |
| 480 | 2 | 0.68 | pass | pass | pass (7 pairs) | pass | right | the person faces the camera, face seen: same; the larger person (the subject) was taken |
| 660 | 1 | 0.35 | pass | pass | pass (6 pairs) | pass | right | profile (lunge): the names are on the right joints; the shoulders overlap (not voting) |
| 840 | 1 | 0.64 | pass | pass | pass (7 pairs) | pass | right | profile (lunge): same |

- Frontal frames (120, 300, 480) settle the left/right meaning: with the face seen, the joints named `L...` are on the image right, which is the person's left; `Nose`, `Head` (top of the head), `Neck` (base of the neck) and `Hip` (middle of the hips)
  are where their names say; toes and heels are at the foot of their own side.
- In the two profile frames the hidden arm and leg are estimated behind the body; the names still sit on plausible joints and the trunk and leg pairs keep the same side as in the frontal frames.

## Finding while checking (fixed in this task)

At 660 s the first version of the check reported a failure on the pair `LEar` / `REar`: in a profile the head turns independently of the body and the model puts the hidden ear on the other side. The index was right; the check was wrong.
The eyes and the ears no longer vote on the side rule (unit test `test_t_pose_04a_a_turned_head_does_not_decide_the_side_rule`). The left/right meaning of the head joints is settled by the frontal frames.

## Limits

- One video, one person, lecture footage, five frames: this settles the order of the index, not the quality of the pose (that is P3.07 and P3.08 on the team's own clips).
- A global swap of all left and right labels cannot be told from a person who turns his back by the structure alone; the frontal frames with the face seen rule it out here.
- Noted for P3.02 and P3.03: `iter_frames` numbers the frames it yields from 0 inside the window; it is not the frame index of the file.
