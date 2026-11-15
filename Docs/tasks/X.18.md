# X.18 — Ontology open questions that need no coach: source check, side of each repetition, review sheet

| Field             | Value                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Status            | DONE (2026-11-15); the coach sign-off stays open                                               |
| Owner             | agent (A)                                                                                      |
| Phase             | P1 follow-up (ad-hoc, after P1.04)                                                             |
| Estimate          | 0.5 day                                                                                        |
| Depends on        | P1.04 (DONE 2026-11-15, checked)                                                               |
| Plan confirmed by | Maintainer, 2026-11-15: approved the proposed order of work, which includes the `side_sequence` field (a schema change) |
| Started / Done    | 2026-11-15 / 2026-11-15                                                                        |

## 1. Analysis

**Goal:** close what P1.04 left open that a coach is not needed for, and make the rest cheap for a coach to answer:
(1) check the 24-form list, names and repetition counts against public sources; (2) let the ontology say which side each
repetition of an alternating movement uses (Q8, and with it Q5), so `check_segment` catches a wrong side; (3) produce a
one-page review sheet a coach can answer in about 15 minutes, without an interview (DEC-0021 is not touched).

**In scope:** the source check and the corrections it supports; an optional `side_sequence` per action with its schema
rules and the pairing check; the YAML update; a generator for the review sheet and the sheet itself; tracking and notices.

**Out of scope:** Q6 (reference from the other number of one technique: P6.05), Q7 (sub-phases inside a movement: P9.04
and a migration), the coach's sign-off (the file stays `draft_unconfirmed`), any interview.

**Existing code and docs read:** `Docs/tasks/P1.04.md` (§5, §6), `taiji_ai/src/taiji_ai/schemas/ontology.py`,
`taiji_ai/config/ontology_v0.yaml`, `taiji_ai/tests/unit/test_ontology.py`, `taiji_ai/tests/unit/test_repo_hygiene.py` (how
tests load a script from `tools/`), `Docs/discovery/interview_checklist.md` (language and tone of coach-facing files),
`taiji_ai/THIRD_PARTY_NOTICES.md` §6.

### 1.1 Source check (2026-11-15)

Only facts were taken (numbers, names, counts); no wording is copied. Pages were read with the fetch tool; summaries of
a search engine were not used as evidence.

| Id | Source | Authority | Used for |
| -- | ------ | --------- | -------- |
| S1 | `en.wikipedia.org/wiki/24-form_tai_chi` (CC BY-SA 4.0) | Encyclopaedia, secondary | numbered list, names, sub-movements |
| S2 | `zh.wikipedia.org/wiki/二十四式太极拳` (CC BY-SA 4.0) | Encyclopaedia, secondary | numbered list, Chinese names |
| S3 | `qialance.com/tai-chi-24-form-moves-chinese-pinyin-english/` | Commercial blog | numbered list, names |
| S4 | `post.smzdm.com/p/aggxp7rw/` | A consumer article (low authority) | repetition counts |

Could not be read, so they say nothing here: a university-press PDF and a Taiji union booklet (compressed streams that the
fetch tool cannot decode), a Baidu Baike page (HTTP 403), a university document (HTTP 404). No authoritative teaching text
was read.

| Point | Result |
| ----- | ------ |
| Numbers 1–24 and Chinese names | S1, S2 and S3 agree with our file on all 24 numbers, including A07/A08 and A16/A17 as separate numbers and the alternating numbers 2, 4, 6, 18. This supports Q3 and Q5; the coach still confirms the variant |
| Name variants | No. 18: S2 `左右穿梭` (ours), S1 and S3 `右左玉女穿梭`. No. 20: S2 and S3 `闪通臂` (ours), S1 `扇通背`; S1 and S3 give the English name "Fan through the back" |
| Repetition counts | S1, S2, S3 give none. S4 alone gives 3, 3, 4, 3, 2 for numbers 2, 4, 6, 10, 18, equal to our file; one low-authority page, so the counts stay unconfirmed |
| Side order | S1 and S3 name no. 18 "right and left", so right comes first; S1 lists no. 6 as 6.1 left, 6.2 right. Nothing for nos. 2, 4, 10 |
| Sub-movements | S1 and S3 split nos. 7 and 8 (ward off, roll back, press, push) and nos. 16 and 17 (snake creeps down, golden rooster): public descriptions do have sub-phases. Input to Q7, no change in v0 |
| Vietnamese readings | Two searches in Vietnamese found no Vietnamese source. Our readings stay unchecked |
| Meaning of "left" and "right" | No source says whether a side means the leading foot, the working hand or the direction of the turn. New question Q9 |

**Constraints that apply:** AGENTS.md §5.12 (domain content needs the coach: nothing here is marked confirmed), §5.1
(never present a guess as an observation: unknown sides stay unspecified, no filling), §9.1 and §9.2 (CC BY-SA sources:
facts only, cited), §4.3 (a document that mirrors a data file must not go stale), §6 (Pydantic v2, ruff 120, tests under
`tests/unit`, `tools/` scripts without package imports of the app beyond `taiji_ai`).

**Unknowns, risks, questions:**

| #  | Question | Default if no answer |
| -- | -------- | -------------------- |
| Q9 | What does `side` mean for a movement (leading foot, working hand or direction of the turn), and which side label does a segment get when it covers a whole alternating movement (`occurrence` empty)? *(new, from the source check)* | Not defined in v0; `check_segment` accepts any listed side when `occurrence` is empty; the coach decides; P8.06 needs the answer before its editor |
| R1 | A `side_sequence` filled from a name order is a guess if the coach teaches the other order, and a wrong guess would reject a correct segment | Fill it only where names or sources point to one order (nos. 2, 4, 18), mark each as provisional in the YAML, leave nos. 6 and 10 unspecified, and keep the file `draft_unconfirmed` |
| R2 | The review sheet can go stale when the YAML changes | The sheet embeds a hash of the YAML; a test fails when they differ |

## 2. Plan

**Design:**

1. `Action.side_sequence: tuple[str, ...] | None = None`: the side of repetition 1, 2, … in order. Rules when present:
   length equals `repetitions`; every entry is in `sides`; every side of `sides` occurs. Absent means "not specified":
   no pairing check (so unknown stays unknown). The schema stays `ontology/1`: nothing reads the file yet (P6.05 and P8.06
   are not started), recorded in DEC-0023.
2. `Ontology.check_segment`: when the action has a `side_sequence` and `occurrence` is an integer, `side` must equal
   `side_sequence[occurrence - 1]`; the error names the expected side. With `occurrence=None` nothing changes (Q9).
   The "Limit (v0)" note of the docstring is updated.
3. `config/ontology_v0.yaml`: `side_sequence` for A02 (left, right, left), A04 (left, right, left), A18 (right, left), each
   with a comment "provisional: name order / S1, S3"; A06 and A10 without one; English names of A18 and A20 corrected to
   the common names of S1 and S3; header: source-check summary, Q9, Q8 now partly answered.
4. `tools/render_ontology_review.py`: renders `Docs/discovery/ontology_review_sheet.md` (Vietnamese, like the other coach
   files) from the YAML: a 24-row table (number, names, sides, repetitions, side order or "chưa xác định", a column for
   "đúng" and one for "sửa thành"), the open questions in plain words with one example each, a sign-off block that asks for
   a role code and a date (no names). It embeds the first 12 hex characters of the SHA-256 of the YAML (line ends
   normalised to LF). `--check` exits 1 when the committed sheet is stale.

**Files to create / modify:**

| File | Change |
| ---- | ------ |
| `taiji_ai/src/taiji_ai/schemas/ontology.py` | `side_sequence`, its validator, the pairing check, docstring |
| `taiji_ai/config/ontology_v0.yaml` | sequences, name fixes, header |
| `taiji_ai/tests/unit/test_ontology.py` | T-DATA-01i..k |
| `taiji_ai/tools/render_ontology_review.py` | new |
| `taiji_ai/tests/unit/test_ontology_review_sheet.py` | new, T-DATA-01l |
| `Docs/discovery/ontology_review_sheet.md` | new, generated |
| `taiji_ai/THIRD_PARTY_NOTICES.md`, `Docs/tracking/DECISIONS.md` (DEC-0023), `taiji_ai/README.md`, tracking files, `Docs/tasks/P1.04.md` (Q8, Q9 note) | docs |

**Implementation steps:**

1. Re-read this plan and the files above (§3).
2. Tests first, red: T-DATA-01i, j, k.
3. Model, validator and pairing check; green.
4. YAML update.
5. Generator and its tests (red first), generate the sheet, markdownlint via the IDE.
6. Mutation run on the new rules; notices, DEC-0023, README, P1.04 note.
7. Gate, self-review, tracking, close.

**Test plan:**

| Test ID | Type | What it checks | New / existing |
| ------- | ---- | -------------- | -------------- |
| T-DATA-01i | unit | `side_sequence` schema: wrong length, a side outside `sides`, a side of `sides` that never occurs are rejected; absent is accepted; an unspecified alternating action is accepted | new |
| T-DATA-01j | unit | `check_segment` accepts each `(side_sequence[k-1], k)` and rejects the other side at repetition k, naming the expected side; `occurrence=None` and actions without a sequence are unchanged | new |
| T-DATA-01k | unit | Shipped file: every present sequence follows the schema; A02, A04 and A18 have one; A06 and A10 have none (pins the "unspecified stays unspecified" rule, not the sides themselves) | new |
| T-DATA-01l | unit | Sheet generator: 24 rows, every id once, sequences and "chưa xác định" rendered, status line follows `form.status`, hash line present; the committed sheet's hash equals the current YAML's (stale guard); `--check` result | new |
| T-DATA-01a..h | unit | unchanged behaviour | existing |

**Acceptance criteria:**

- [x] AC1 The source check is recorded (§1.1) with sources, access date and a result per point; names are corrected only where the sources agree; every uncertain point stays a question.
- [x] AC2 `side_sequence` works as designed; tests written red first; every mutation of the new rules is caught.
- [x] AC3 The YAML carries the provisional sequences with comments, no guessed side for A06 and A10, Q9 recorded, and stays `draft_unconfirmed`.
- [x] AC4 The review sheet is generated from the YAML, passes markdownlint in the IDE, holds no personal data, and goes stale loudly (guard test).
- [x] AC5 Notices, DEC-0023, README, P1.04 note, CHANGELOG, TASK_STATUS updated; gate 10/10 PASS.

**Impact / rollback:** one optional field and one stricter check that only applies where a sequence is given; no consumer
exists yet. Rollback: remove the field and the three YAML entries.

## 3. Plan re-read (before coding)

- Plan re-read: 2026-11-15 — OK against the current files. Checked: `ontology.py`, the YAML and `test_ontology.py` are
  unchanged since P1.04 (59 tests pass, no other writer touched them); the "Limit (v0)" note is in the `check_segment`
  docstring (line 161) and is the text to replace; `Action` already validates `sides` per action, so the sequence rules fit
  a model validator on `Action`; tests load `tools/` scripts with `importlib` (pattern in `test_repo_hygiene.py`), so the
  generator is tested the same way; the coach-facing files in `Docs/discovery/` are Vietnamese. No change to the plan.

## 4. Implementation log

All on 2026-11-15, in plan order.

| Step | Done | Notes / deviations from the plan |
| ---- | ---- | -------------------------------- |
| 1 | yes | Plan re-read (§3), no change |
| 2 | yes | T-DATA-01i, j, k written first: 6 failed and 3 errors, all on the missing attribute `side_sequence` |
| 3 | yes | `Action.side_sequence` with a model validator; pairing check in `check_segment`; docstring and module note. First run: only the shipped-file tests and T-DATA-01d were red. **Deviation 1:** T-DATA-01d enumerated every side with every occurrence and so met the new rule; it now takes the allowed sides per occurrence (`_allowed_sides`), which is the intended behaviour change |
| 4 | yes | YAML: sequences for A02, A04, A18 (provisional comments), A06 and A10 left unspecified with a comment, English names of A18 and A20, header (source check, Q8, Q9) |
| 5 | yes | `tests/unit/test_ontology_review_sheet.py` written first (collection error: tool missing); `tools/render_ontology_review.py`; ruff E501 on eight long Vietnamese strings, rewrapped; sheet generated; two more tests for the question lists (found while reading the sheet) |
| 6 | yes | Mutation run (script in the session scratchpad, not in the repository): first run crashed in my script (cp1252 decoding of test names), fixed; then one survivor, **BUG-0042**, fixed; then 45 of 45 caught. Notices, DEC-0023, README, P1.04 note |
| 7 | yes | Gate, self-review, tracking |

**Deviation 2:** to learn whether `getDiagnostics` analyses a file that was only written, I created a temporary file with
deliberate errors in `Docs/tasks/`, read the IDE answer and deleted it (no trace in `git status`). Result: an empty answer
without `linesInFile` means "not analysed"; the analysis runs when a file is edited with the edit tool.
**Deviation 3:** the sheet was checked by editing it and restoring the exact text; the tool's `--check` then confirmed it is
still equal to the generated one.

## 5. Verification

| Check | Result |
| ----- | ------ |
| T-DATA-01i, j, k (`test_ontology.py`, now 77 tests) | pass; red first |
| T-DATA-01l (`test_ontology_review_sheet.py`, 12 tests) | pass; red first (tool missing) |
| Full suite `pytest` | ~~191 passed~~ 335 passed (corrected 2026-11-15, BUG-0048: recomputed as 246 tests in the other files plus the 77 ontology and 12 sheet tests of that day) |
| Mutation check: 28 earlier mutations plus 17 new (6 on `side_sequence`, 11 on the sheet tool) | 45 of 45 caught |
| `ruff check`, `ruff format --check`, `mypy src` | clean |
| Gate `tools\check.ps1` (10 steps) | PASS 10/10 in 14.9 s |
| `tools\render_ontology_review.py --check` | "sheet is up to date" |
| IDE markdownlint after an edit of the file | sheet: none (78 lines); README: one pre-existing MD040, fixed (BUG-0043), none after; DECISIONS, THIRD_PARTY_NOTICES, BUGS, this file: none |

**Correction to my P1.04 summary:** I counted `THIRD_PARTY_NOTICES.md` among the checked files, but like `README.md` and
`DECISIONS.md` it had returned an empty answer without `linesInFile`, so it had not been analysed. All three were
analysed in this task (the edits above); the only finding is BUG-0043.

**AC1** met: §1.1 lists the sources, the access date and a result per point. Names were changed only where S1 and S3 agree
(A20 English "Fan through the back"; A18 English "Fair lady works the shuttles"). Repetition counts, Vietnamese readings and the
side order of A06 and A10 stay unconfirmed and are questions.

**AC2** met: `side_sequence` and the pairing check work as designed; tests were red first; all 6 mutations of the new rules are caught.

**AC3** met: `config/ontology_v0.yaml` has the provisional sequences for A02, A04 and A18 with comments, none for A06 and A10,
Q8 and Q9 in the header, and stays `draft_unconfirmed`.

**AC4** met: the sheet is generated from the YAML, IDE markdownlint is clean, it holds no personal data (a role code and a date
are asked, never a name), and the guard test fails when the YAML changes without a regeneration (mutations "check ignores
staleness" and "sheet embeds a wrong digest" are caught).

**AC5** met: notices (§6 row), DEC-0023, README, the P1.04 note, CHANGELOG and TASK_STATUS updated; gate 10/10.

## 6. Self-review

Re-read `ontology.py` (the new validator and the pairing check), the YAML diff, both test files, the tool and the generated
sheet against the checklist.

- Does it do what the plan says? Yes. Extra beyond the plan: two tests for the question lists and the `_allowed_sides`
  change in T-DATA-01d (deviation 1).
- Edge cases: a sequence of the wrong length, empty, with an unknown side, with a declared side missing, with a bad label;
  `occurrence=None` with a sequence; an action without a sequence; a confirmed form on the sheet; CRLF in the YAML (digest);
  a missing, stale and fresh sheet; an invalid ontology file given to the tool.
- No fabricated data: A06 and A10 get no side order because no source read gives one; A02, A04 and A18 carry one, marked
  provisional, because names and two sources point to it. Nothing is marked confirmed.
- Errors are raised: the tool returns 2 for an invalid file and 1 for a stale sheet, never writes on error.
- No personal data: the sheet and the YAML hold only movement names; the sign-off asks for a role code.
- **Findings:** (1) BUG-0042, a test gap found by mutation, fixed. (2) BUG-0043, a pre-existing README lint warning shown by the
  IDE, fixed. (3) Question 3 of the sheet quotes "left, right, left" for A02 as an example, which may anchor the coach; the
  same value is already in the table, so it is accepted, and the sheet says the order column is a tentative suggestion.
  (4) The three provisional sequences would make `check_segment` reject a correct segment if the coach teaches another
  order. No consumer exists yet (P8.06 is not started) and the coach confirms before real use; the YAML comments and DEC-0023
  say so.
- **Residual risks, accepted:** the sources are secondary (two encyclopaedia pages, a blog, a low-authority article); no
  authoritative teaching text could be read (§1.1); Q9 must be answered before the P8.06 editor.

## 7. Bugs

| Bug ID | Severity | Status | Note |
| ------ | -------- | ------ | ---- |
| BUG-0042 | S3 | CLOSED | `side_sequence` rule masked by a neighbouring rule in the tests; case `[left, right, up]` added |
| BUG-0043 | S3 | CLOSED | pre-existing MD040 in `taiji_ai/README.md` (Layout block), fixed |

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass (gate 10/10, 2026-11-15)
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated (DEC-0023)

**Still open, for a coach:** the sign-off of `config/ontology_v0.yaml` through `Docs/discovery/ontology_review_sheet.md`
(Q3, Q5, Q8, Q9, the counts of A06 and A10, the names), and the later questions Q6 (P6.05) and Q7 (P9.04). The sheet
works without an interview; whether to send it to a coach is the maintainer's decision.

**Update 2026-11-15 (task X.19, appended; the text above is unchanged):** a search for an authoritative answer to Q9 found
none. The results disagree on the order of A06, one result says the left version of A16 stands on the left leg, and nothing
was found on kicks or on whether a name follows the hand or the foot. The findings and a working proposal (marked "not a
decision") are in `Docs/tasks/X.19.md` and in the Q9 lines of the YAML header; no label, sequence or count changed.
