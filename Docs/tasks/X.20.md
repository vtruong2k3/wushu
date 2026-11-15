# X.20 — Adopt the working convention for the side label (Q9, first part)

| Field             | Value                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Status            | IN_PROGRESS (2026-11-15)                                                                       |
| Owner             | agent (A); decision by the maintainer                                                          |
| Phase             | P1 follow-up (ad-hoc, after X.19)                                                              |
| Estimate          | 0.1 day                                                                                        |
| Depends on        | X.19 (DONE 2026-11-15, checked)                                                                |
| Plan confirmed by | Not required (under 1 day, no schema or contract change); the maintainer asked for it on 2026-11-15 |
| Started / Done    | 2026-11-15 / —                                                                                 |

## 1. Analysis

**Goal:** record the working convention proposed in X.19 as a decision of the maintainer, show it on the coach review
sheet (question 4) so a coach can confirm or change it, and update the Q9 note in the YAML header from "proposal" to
"working convention".

**The convention:** the side label of a segment is the left or right word (`左` / `右`) of the movement's standard name; for
movements that step forward that is the front foot. Consequences for the data, checked against the YAML (no value changes):

| Movements | Name gives | In the YAML | Effect |
| --------- | ---------- | ----------- | ------ |
| A07, A08 | `左揽雀尾`, `右揽雀尾` | one side each | settled |
| A13, A15 | `右蹬脚`, `转身左蹬脚` | right, left | settled by the name (the kicking foot is then simply what the name says) |
| A16, A17 | `左下势独立`, `右下势独立` | left, right | settled by the name |
| A02, A04 | `左右…` | `side_sequence` left, right, left (provisional, from the name order) | unchanged |
| A18 | `左右穿梭` in our file, `右左玉女穿梭` in two sources | `side_sequence` right, left (provisional, from those two sources) | unchanged, but **the name order does not settle it**: our `name_zh` says left first and the sequence says right first; the sheet shows both and the coach decides |
| A06 | `左右倒卷肱`, no per-repetition order | no sequence | still unspecified |
| A10 | `云手`, no side word | no sequence | still unspecified |

**Still open (not decided here):** the second part of Q9, which label a segment gets when it covers a whole alternating
movement (no occurrence). The validator keeps accepting any listed side then. The order of A06 and A10 also stays open.

**What this is not:** a coach sign-off. No coach exists yet; the maintainer agreed to the convention as the project's
working rule. The ontology stays `draft_unconfirmed` (AGENTS.md §5.12) and `confirmed_by` / `confirmed_at` are not set.

**In scope:** DEC-0024; question 4 of the sheet (tool text, a test, regenerated sheet); the Q9 lines of the YAML header; an
appended note in `Docs/tasks/X.19.md`; tracking.

**Out of scope:** any value of the ontology; the validator; the second part of Q9; the order of A06 and A10.

**Constraints that apply:** AGENTS.md §5.12 (domain content needs the coach: the status stays draft), §4.3 (the sheet
mirrors the YAML and is regenerated), §4.1 (a decision goes to `DECISIONS.md`), §2 (tests first).

**Unknowns, risks, questions:** none new. Risk: a coach who reads question 4 may prefer another convention; the sheet asks
them to confirm or change it, and the label set stays valid either way because the labels are the same words.

## 2. Plan

**Design:** two added lines in question 4 of the sheet text in `tools/render_ontology_review.py` ("Quy ước tạm đang dùng
(người quản lý dự án chấp thuận, chờ thầy/cô xác nhận): bên là chữ trái hoặc phải trong tên chuẩn của thức; với thức tiến
bước đó là chân bước ra trước. Thầy/cô đồng ý, hay muốn đổi?"); the Q9 lines of the YAML header reworded; DEC-0024.

**Files to create / modify:**

| File | Change |
| ---- | ------ |
| `taiji_ai/tests/unit/test_ontology_review_sheet.py` | new test (red first) |
| `taiji_ai/tools/render_ontology_review.py` | question 4 text |
| `taiji_ai/config/ontology_v0.yaml` | Q9 comment lines (comments only) |
| `Docs/discovery/ontology_review_sheet.md` | regenerated |
| `Docs/tracking/DECISIONS.md` (DEC-0024), `TASK_STATUS.md`, `CHANGELOG.md`, `Docs/tasks/X.19.md` (appended note) | docs |

**Implementation steps:**

1. Re-read this plan (§3); snapshot the parsed ontology.
2. Test first: the sheet states the working convention in question 4 (red).
3. Tool text; YAML header; regenerate the sheet; green.
4. DEC-0024, the X.19 note, tracking.
5. Gate, IDE lint of every changed document, self-review, close.

**Test plan:**

| Test ID | Type | What it checks | New / existing |
| ------- | ---- | -------------- | -------------- |
| T-DATA-01l | unit | the sheet's question 4 names the working convention and asks the coach to confirm or change it | new case |
| T-DATA-01a..l | unit | everything else unchanged, including the stale guard | existing |

**Acceptance criteria:**

- [ ] AC1 DEC-0024 records the convention as a maintainer decision and says it is not a coach sign-off.
- [ ] AC2 Question 4 of the sheet shows the convention; the sheet is regenerated and the guard passes.
- [ ] AC3 The Q9 note of the YAML header says "working convention", names what stays open, and no value of the ontology changed (snapshot equal); `status` is still `draft_unconfirmed`.
- [ ] AC4 Gate 10/10 PASS; IDE lint clean on every changed document; tracking updated.

**Impact / rollback:** a sentence in a generated sheet and comments in the YAML; remove them and regenerate.

## 3. Plan re-read (before coding)

- Plan re-read: 2026-11-15 — checked against the real data (sides and sequences printed from `load_ontology()`; status
  `draft_unconfirmed`). One correction found: the analysis table put A18 together with A02 and A04 as "from the name order".
  That is wrong for A18: our `name_zh` is `左右穿梭` (left first) but its sequence is right, left, taken from two sources whose
  name is `右左玉女穿梭`. The table now has a separate A18 row and the YAML note and DEC-0024 will say so. No other change.
  Snapshot of the parsed ontology taken before the edit.

## 4. Implementation log

| Step | Done | Notes / deviations from the plan |
| ---- | ---- | -------------------------------- |
| 1 | yes | Plan re-read (§3): the A18 correction; snapshot of the parsed ontology |
| 2 | yes | New case in T-DATA-01l (question 4 states the convention): red, the sheet had no such text |
| 3 | yes | Three lines added to question 4 in the tool; the Q9 block of the YAML header reworded; the sheet tests then showed exactly one failure, the stale guard (sheet older than the YAML), and after `render_ontology_review.py` everything passed |
| 4 | yes | DEC-0024; appended note in X.19; tracking |
| 5 | yes | Gate, lint, self-review (below) |

**Deviation:** none from the plan. The first draft of the convention note in the YAML was written as "proposal"; it now
says "working convention (agreed by the maintainer, DEC-0024)" and says it is not a coach sign-off.

## 5. Verification

| Check | Result |
| ----- | ------ |
| New case in T-DATA-01l before the sheet text was changed | red (`Quy ước tạm đang dùng` not found in question 4) |
| Stale guard after the YAML edit, before regenerating | red (1 failed), as expected |
| After regenerating: `test_ontology.py` and `test_ontology_review_sheet.py` | 90 passed |
| Parsed ontology against the snapshot before | equal; `status` is `draft_unconfirmed` |
| Sheet against the copy taken at the start of X.19 | three added lines in question 4 and the digest line; nothing else |
| `ruff check`, `ruff format --check` | clean |
| Gate `tools\check.ps1` (10 steps) | PASS 10/10 in 20.3 s |
| `render_ontology_review.py --check` | sheet is up to date |

**AC1** met: DEC-0024 says maintainer decision, working convention, not a coach sign-off. **AC2** met: question 4 shows it,
the sheet is regenerated, the guard passes. **AC3** met: the Q9 block says "working convention", lists what stays open
(whole-movement label; A06 and A10 order; A18 name versus sequence), the snapshot is equal, the status is still draft.

## 6. Self-review

Re-read the added tool lines, the YAML block, the generated question 4, DEC-0024 and the notes against the checklist.

- Does it do what the plan says? Yes. Nothing extra.
- No fabricated data: no value of the ontology changed; the convention is a labelling rule, not an observation. The A18
  inconsistency (name says left first, sequence says right first) is stated in the YAML, in DEC-0024 and in this file
  instead of being hidden; it was found at the plan re-read, not after the edit.
- The ontology is not marked confirmed: the maintainer agreed to a working rule, which is a different thing from the coach's
  sign-off that AGENTS.md §5.12 asks for. The YAML, DEC-0024 and the sheet all say so.
- No personal data: the sheet says "người quản lý dự án", never a name; no chat words are quoted.
- Finding: on the sheet the A18 row shows the name `左右穿梭` and the order "phải → trái", which a coach will notice;
  the sheet already says the order column is only a tentative suggestion. Not changed (it would need A18-specific text in the tool).
- Residual risk, accepted: the whole-movement label is still open, and P8.06 needs it before its editor.

## 7. Bugs

None found.

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass (gate 10/10, 20.3 s, 2026-11-15)
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated (DEC-0024)
