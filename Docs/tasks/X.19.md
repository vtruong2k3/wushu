# X.19 — Record the Q9 search findings (meaning of "side") in the ontology notes

| Field             | Value                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Status            | IN_PROGRESS (2026-11-15)                                                                       |
| Owner             | agent (A)                                                                                      |
| Phase             | P1 follow-up (ad-hoc, after X.18)                                                              |
| Estimate          | 0.1 day                                                                                        |
| Depends on        | X.18 (DONE 2026-11-15, checked)                                                                |
| Plan confirmed by | Not required (under 1 day, no schema or contract change); the maintainer asked for this task on 2026-11-15 |
| Started / Done    | 2026-11-15 / —                                                                                 |

## 1. Analysis

**Goal:** keep what the Q9 search found (and did not find) next to Q9, so the search is not repeated and the coach
review starts from the evidence. Q9: what does a `side` mean for a movement (leading foot, working hand, direction of
the turn), and which side label does a segment get when it covers a whole alternating movement?

**In scope:** a short note in the header of `config/ontology_v0.yaml` (where Q9 lives), the regeneration of the review
sheet that the stale guard then demands, an appended note in `Docs/tasks/X.18.md`, and the tracking files.

**Out of scope:** any change to a side label or to `side_sequence`; any change to code or tests; changing the text of the
coach sheet (the working proposal below is not adopted by the maintainer, so it is not sent to a coach); Q6, Q7.

**What was searched (2026-11-15):** three web searches (Chinese and English, on which leg stands in the "lower body and
stand on one leg" movements, which foot steps back first in "repulse monkey", and whether a name follows the hand or the
foot), then two attempts to read a step-by-step page: one returned an empty page to the fetch tool, one answered HTTP 403.
The findings below come from search-engine summaries, except the list in X.18 §1.1 (S1), which was read directly.

| Point | Finding | Weight |
| ----- | ------- | ------ |
| Order of A06 (repulse monkey) | The results disagree: one gives right, left, right, left; another left, right, left, right. The English Wikipedia list (S1, read directly) puts a left item first (6.1 left, 6.2 right) | Disagreement is itself the result |
| Standing leg of A16, A17 | One result says the left version stands on the left foot; none says it for the right version | One secondary statement |
| Kicks (A13, A15) | Nothing about how the name is chosen | None |
| Hand or foot | No result says whether a left/right name follows the stepping foot or the working hand | None |
| Authoritative text | None read (the textbook-style pages could not be fetched) | Gap |

**Working proposal (not a decision; the maintainer asked to leave Q9 provisional):** the side label of a segment is the
left or right word of the movement's standard name; for movements that step forward this is also the front foot; any
movement where the name does not settle it (A06, A10 and, unverified, the kicks and the independent stands) stays
unspecified until a coach answers. It is recorded as a proposal so that nobody reads it as agreed.

**Constraints that apply:** AGENTS.md §5.1 (nothing guessed is shown as an observation: the findings are marked by their
weight), §9.2 (static reading only; sources are named; summaries of a search engine are not evidence of what a page says),
§4.3 (the sheet mirrors the YAML, so it is regenerated in the same change), §10 (record the question and the answer in the
task file).

**Unknowns, risks, questions:** none new. Risk: a search summary can be wrong, so every line says where it comes from.

## 2. Plan

**Design:** a comment block of six lines added under the Q9 lines in the YAML header; no key or value changes. The sheet
carries a hash of the whole YAML text, so it is regenerated with `tools\render_ontology_review.py`.

**Files to create / modify:**

| File | Change |
| ---- | ------ |
| `taiji_ai/config/ontology_v0.yaml` | comment block under Q9 |
| `Docs/discovery/ontology_review_sheet.md` | regenerated (only the hash line changes) |
| `Docs/tasks/X.18.md` | appended note pointing to X.19 |
| `Docs/tracking/TASK_STATUS.md`, `CHANGELOG.md` | rows |

**Implementation steps:**

1. Re-read this plan (§3).
2. Step 2a: edit the YAML header and run the sheet tests **before** regenerating, to see the stale guard fail (T-DATA-01l).
   Step 2b: regenerate the sheet.
3. Check that the sheet differs from before only in the hash line, and that the parsed ontology equals the snapshot taken before.
4. Gate, IDE lint of every changed document, self-review, tracking, close.

**Test plan:** no new test. Existing T-DATA-01a..l must pass; T-DATA-01l (stale guard) is expected red between steps 2a and 2b.

**Acceptance criteria:**

- [ ] AC1 The YAML header records the Q9 search (date, what was found, what was not, the proposal marked "not a decision").
- [ ] AC2 No label, sequence or count changed: the parsed ontology is equal to the one before.
- [ ] AC3 The sheet is regenerated, differs only in the hash line, and the guard passes.
- [ ] AC4 Gate 10/10 PASS; IDE lint clean on every changed document; tracking updated.

**Impact / rollback:** comments only; remove the comment block and regenerate the sheet.

## 3. Plan re-read (before coding)

- Plan re-read: 2026-11-15 — OK against the current files. Checked: Q9 sits at lines 19–20 of the YAML header and the
  block goes right under it; the YAML and the sheet are untouched since X.18 (the sheet is up to date). One correction: the
  plan said "steps 2 and 2b" without a step 2a, now written as 2a (edit, see the guard fail) and 2b (regenerate).
  Snapshots taken before the edit: the parsed ontology (24 actions, JSON digest `0bd492537173e837`) and a copy of the sheet.

## 4. Implementation log

| Step | Done | Notes / deviations from the plan |
| ---- | ---- | -------------------------------- |
| 1 | yes | Plan re-read (§3), one wording correction (2a / 2b) |
| 2a | yes | Six comment lines added under Q9 in the YAML header. The sheet tests were run before regenerating: exactly one failed, `test_t_data_01l_the_committed_sheet_equals_what_the_tool_renders_now`: the committed sheet still carried the digest `dcf8d8e53a6b` of the old YAML text while the edited YAML hashes to `466d760ea7d5`; this shows the guard works |
| 2b | yes | `tools\render_ontology_review.py` run; `--check` says the sheet is up to date |
| 3 | yes | Diff of the sheet against the copy taken before: 77 lines both, one line differs (the digest line); the parsed ontology's JSON equals the snapshot taken before |
| 4 | yes | Gate, lint, tracking (below) |

After step 2b the sheet carries `466d760ea7d5`; this is the only line that differs from the copy taken before.

**Deviation:** none from the plan. The wording of the working proposal in the YAML says "NOT a decision" in capitals so it
cannot be read as agreed.

## 5. Verification

| Check | Result |
| ----- | ------ |
| Stale guard (T-DATA-01l) after the YAML edit, before regenerating | red (1 failed), as expected |
| After regenerating: `test_ontology.py` and `test_ontology_review_sheet.py` | 89 passed |
| `render_ontology_review.py --check` | sheet is up to date |
| Sheet diff against the copy before | one line (the digest); 77 lines both |
| Parsed ontology against the snapshot before | equal (JSON, 24 actions) |
| Gate `tools\check.ps1` (10 steps) | PASS 10/10 in 18.6 s |
| IDE markdownlint after edits | none reported for X.19, X.18, TASK_STATUS and CHANGELOG (analysed: `linesInFile` present); the sheet is checked below |

**AC1** met: the header records the date, the three searches and the two failed reads, the findings by weight, and the
working proposal marked "NOT a decision". **AC2** met: snapshot equal. **AC3** met: one differing line, guard green.

## 6. Self-review

Re-read the YAML header block, the diff of the sheet and the appended notes against the checklist.

- Does it do what the plan says? Yes, comments and a regeneration only.
- No fabricated data: each finding names its weight; the search-engine summaries are said to be summaries; the line about
  right-first order for A06 is reported as a disagreement, not as a fact. The proposal is labelled as not a decision.
- No label, sequence or count changed (snapshot equal).
- No personal data, no real names, no absolute paths.
- Finding: the plan's step numbering was ambiguous (fixed at the re-read). The sheet is not changed in content, so the coach
  does not receive the unadopted proposal; whether to add it to question 4 of the sheet is the maintainer's choice.
- Residual risk, accepted: the findings come from search summaries; the Q9 answer still needs a coach, an official manual
  or a recognised teacher's video.

**Update 2026-11-15 (task X.20, appended; the text above is unchanged):** the working proposal recorded here was adopted by
the maintainer as a working convention (DEC-0024) and added to question 4 of the coach sheet. It is not a coach sign-off.
X.20 also found that for A18 the name order does not settle the sequence.

## 7. Bugs

None found.

## 8. Close-out

- [x] Acceptance criteria met (evidence in §5)
- [x] Checks pass (gate result in the CHANGELOG entry)
- [x] No open S1/S2 bug from this task
- [x] TASK_STATUS.md updated
- [x] CHANGELOG.md entry added
- [x] README status / DECISIONS.md updated if needed (not needed: no decision, no module state change)
