# Analysis (proposed labels allowed (automated pilot))

Tasks: 4 | independent task families: 4 | results: 240

> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth. With this few task families the intervals are not meaningful evidence of an effect.

> **Reporting rules of a new run** (protocol §15.7, §16.6): the run was graded with tc-harness/0.3.5, and new runs use tc-harness/0.3.5 or later (protocol §16.1). Each distinct graded patch counts once (31 distinct among 32 held-out candidates). The per-family table is the primary display, every paired comparison carries exact sign-flip p-values over task families with their attainable floors, and the cluster-bootstrap intervals are in the appendix, marked as not inferential (4 task families, fewer than 10).

## Primary display: false acceptance and false rejection per task family

(numerator/denominator) per task family, each distinct graded patch once; the reference solution and the no-op are excluded (see the sanity checks). The last two columns pool the families.

| Condition | CS-01 FA | CS-01 FR | CS-02 FA | CS-02 FR | CS-03 FA | CS-03 FR | CS-04 FA | CS-04 FR | All FA | All FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 1/6 | 2/2 | 0/4 | 0/3 | 1/2 | 0/3 | 3/4 | 0/2 | 0.31 (5/16) | 0.20 (2/10) |
| initial_audited | 1/6 | 2/2 | 0/4 | 0/3 | 0/2 | 0/3 | 3/4 | 0/2 | 0.25 (4/16) | 0.20 (2/10) |
| full_plain | 0/6 | 0/2 | 0/4 | 0/3 | 0/2 | 0/3 | 0/4 | 0/2 | 0.00 (0/16) | 0.00 (0/10) |
| full_audited | 0/6 | 0/2 | 0/4 | 0/3 | 0/2 | 0/3 | 0/4 | 0/2 | 0.00 (0/16) | 0.00 (0/10) |
| llm_freeform | 1/6 | 0/2 | 0/4 | 0/3 | 0/2 | 0/3 | 0/4 | 0/2 | 0.06 (1/16) | 0.00 (0/10) |
| repo_tests | 2/6 | 0/2 | 0/4 | 3/3 | 2/2 | 1/3 | 1/4 | 0/2 | 0.31 (5/16) | 0.40 (4/10) |

## Paired comparisons: exact sign-flip tests over task families

A - B is the pooled difference (same candidates, each distinct graded patch once); the p-values test the sum over families of the count differences (each candidate weighs the same) with an exact sign-flip test, which cannot go below its floor. p (A > B): the first-named condition errs more.

| A | B | Metric | A - B | Per-family A - B | p (A > B) | p (A < B) | p two-sided | p two-sided, family means | Floor one-sided / two-sided | Families | A acc & B rej | A rej & B acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | full_plain | FA | +0.31 | CS-01 +0.17, CS-02 +0.00, CS-03 +0.50, CS-04 +0.75 | 0.125 | 1 | 0.25 | 0.25 | 0.0625 / 0.125 | 4 | 5 | 0 |
| initial_plain | full_plain | FR | +0.20 | CS-01 +1.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 2 |
| initial_audited | full_audited | FA | +0.25 | CS-01 +0.17, CS-02 +0.00, CS-03 +0.00, CS-04 +0.75 | 0.25 | 1 | 0.5 | 0.5 | 0.0625 / 0.125 | 4 | 4 | 0 |
| initial_audited | full_audited | FR | +0.20 | CS-01 +1.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 2 |
| initial_plain | initial_audited | FA | +0.06 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.50, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 1 | 0 |
| initial_plain | initial_audited | FR | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| full_plain | full_audited | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| full_plain | full_audited | FR | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| llm_freeform | full_audited | FA | +0.06 | CS-01 +0.17, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 1 | 0 |
| llm_freeform | full_audited | FR | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| llm_freeform | full_plain | FA | +0.06 | CS-01 +0.17, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 1 | 0 |
| llm_freeform | full_plain | FR | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| repo_tests | full_audited | FA | +0.31 | CS-01 +0.33, CS-02 +0.00, CS-03 +1.00, CS-04 +0.25 | 0.125 | 1 | 0.25 | 0.25 | 0.0625 / 0.125 | 4 | 5 | 0 |
| repo_tests | full_audited | FR | +0.40 | CS-01 +0.00, CS-02 +1.00, CS-03 +0.33, CS-04 +0.00 | 0.25 | 1 | 0.5 | 0.5 | 0.0625 / 0.125 | 4 | 0 | 4 |

**Null results.** 14 of 14 tested comparisons have a two-sided exact p-value of 0.05 or more: initial_plain vs full_plain FA; initial_plain vs full_plain FR; initial_audited vs full_audited FA; initial_audited vs full_audited FR; initial_plain vs initial_audited FA; initial_plain vs initial_audited FR; full_plain vs full_audited FA; full_plain vs full_audited FR; llm_freeform vs full_audited FA; llm_freeform vs full_audited FR; llm_freeform vs full_plain FA; llm_freeform vs full_plain FR; repo_tests vs full_audited FA; repo_tests vs full_audited FR. With at most 4 families no two-sided p-value can go below 0.125, so none can reach 0.05.

## Pooled false acceptance / false rejection by condition

Pooled rates with (numerator/denominator), each distinct graded patch once; reference solution and no-op are excluded (see sanity table). The exact (Clopper-Pearson) interval ignores clustering and is given only as a reference scale; the cluster-bootstrap intervals are in the appendix.

| Condition | False acceptance | FA exact 95% | FA macro | False rejection | FR exact 95% | FR macro | Youden's J | Tasks with an accepted negative | Infra outcomes | Excluded (unlabeled/ambiguous) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0.31 (5/16) | [0.11, 0.59] | 0.35 | 0.20 (2/10) | [0.03, 0.56] | 0.25 | +0.49 | 3/4 | 0/31 | 5 |
| initial_audited | 0.25 (4/16) | [0.07, 0.52] | 0.23 | 0.20 (2/10) | [0.03, 0.56] | 0.25 | +0.55 | 2/4 | 0/31 | 5 |
| full_plain | 0.00 (0/16) | [0.00, 0.21] | 0.00 | 0.00 (0/10) | [0.00, 0.31] | 0.00 | +1.00 | 0/4 | 0/31 | 5 |
| full_audited | 0.00 (0/16) | [0.00, 0.21] | 0.00 | 0.00 (0/10) | [0.00, 0.31] | 0.00 | +1.00 | 0/4 | 0/31 | 5 |
| llm_freeform | 0.06 (1/16) | [0.00, 0.30] | 0.04 | 0.00 (0/10) | [0.00, 0.31] | 0.00 | +0.94 | 1/4 | 0/31 | 5 |
| repo_tests | 0.31 (5/16) | [0.11, 0.59] | 0.40 | 0.40 (4/10) | [0.12, 0.74] | 0.33 | +0.29 | 3/4 | 0/31 | 5 |

## Oracle-gated view (secondary)

A verifier x task cell is dropped when the verifier does not pass the task's reference solution in the run's sanity grading; its held-out candidates are the lost yield (secondary view, protocol §15.7).

| Condition | Cells kept | Dropped | Lost yield (invalid / valid) | False acceptance | False rejection |
| --- | --- | --- | --- | --- | --- |
| initial_plain | 3/4 | CS-01: does not pass its reference (task_failure) | 6 / 2 | 0.40 (4/10) | 0.00 (0/8) |
| initial_audited | 3/4 | CS-01: does not pass its reference (task_failure) | 6 / 2 | 0.30 (3/10) | 0.00 (0/8) |
| full_plain | 4/4 | - | 0 / 0 | 0.00 (0/16) | 0.00 (0/10) |
| full_audited | 4/4 | - | 0 / 0 | 0.00 (0/16) | 0.00 (0/10) |
| llm_freeform | 4/4 | - | 0 / 0 | 0.06 (1/16) | 0.00 (0/10) |
| repo_tests | 4/4 | - | 0 / 0 | 0.31 (5/16) | 0.40 (4/10) |

### Oracle-gated paired comparisons

A - B is the pooled difference (same candidates, on the tasks that both conditions keep); the p-values test the sum over families of the count differences (each candidate weighs the same) with an exact sign-flip test, which cannot go below its floor. p (A > B): the first-named condition errs more.

| A | B | Metric | A - B | Per-family A - B | p (A > B) | p (A < B) | p two-sided | p two-sided, family means | Floor one-sided / two-sided | Families | A acc & B rej | A rej & B acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | full_plain | FA | +0.40 | CS-02 +0.00, CS-03 +0.50, CS-04 +0.75 | 0.25 | 1 | 0.5 | 0.5 | 0.125 / 0.25 | 3 | 4 | 0 |
| initial_plain | full_plain | FR | +0.00 | CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.125 / 0.25 | 3 | 0 | 0 |
| initial_audited | full_audited | FA | +0.30 | CS-02 +0.00, CS-03 +0.00, CS-04 +0.75 | 0.5 | 1 | 1 | 1 | 0.125 / 0.25 | 3 | 3 | 0 |
| initial_audited | full_audited | FR | +0.00 | CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.125 / 0.25 | 3 | 0 | 0 |
| initial_plain | initial_audited | FA | +0.10 | CS-02 +0.00, CS-03 +0.50, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.125 / 0.25 | 3 | 1 | 0 |
| initial_plain | initial_audited | FR | +0.00 | CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.125 / 0.25 | 3 | 0 | 0 |
| full_plain | full_audited | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| full_plain | full_audited | FR | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| llm_freeform | full_audited | FA | +0.06 | CS-01 +0.17, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 1 | 0 |
| llm_freeform | full_audited | FR | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| llm_freeform | full_plain | FA | +0.06 | CS-01 +0.17, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 1 | 0 |
| llm_freeform | full_plain | FR | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| repo_tests | full_audited | FA | +0.31 | CS-01 +0.33, CS-02 +0.00, CS-03 +1.00, CS-04 +0.25 | 0.125 | 1 | 0.25 | 0.25 | 0.0625 / 0.125 | 4 | 5 | 0 |
| repo_tests | full_audited | FR | +0.40 | CS-01 +0.00, CS-02 +1.00, CS-03 +0.33, CS-04 +0.00 | 0.25 | 1 | 0.5 | 0.5 | 0.0625 / 0.125 | 4 | 0 | 4 |

**Null results.** 14 of 14 tested comparisons have a two-sided exact p-value of 0.05 or more: initial_plain vs full_plain FA; initial_plain vs full_plain FR; initial_audited vs full_audited FA; initial_audited vs full_audited FR; initial_plain vs initial_audited FA; initial_plain vs initial_audited FR; full_plain vs full_audited FA; full_plain vs full_audited FR; llm_freeform vs full_audited FA; llm_freeform vs full_audited FR; llm_freeform vs full_plain FA; llm_freeform vs full_plain FR; repo_tests vs full_audited FA; repo_tests vs full_audited FR. With at most 4 families no two-sided p-value can go below 0.125, so none can reach 0.05.

## Distinct graded patches

31 distinct graded patches among 32 held-out candidates: held-out candidates of a task with the same graded patch count once; the representative is the natural state, else the first id (protocol §15.4, §15.7).

* CS-04: CS-04-pre-correction, CS-04-eval-nm-2 count once, as CS-04-pre-correction (label invalid)

## Accepted negatives by type

| Condition | correction-violating | initial-violating | unspecified |
| --- | --- | --- | --- |
| initial_plain | 5/15 | 0/1 | - |
| initial_audited | 4/15 | 0/1 | - |
| full_plain | 0/15 | 0/1 | - |
| full_audited | 0/15 | 0/1 | - |
| llm_freeform | 1/15 | 0/1 | - |
| repo_tests | 5/15 | 0/1 | - |

## Sanity checks (excluded from primary metrics)

| Condition | reference passes | no-op passes |
| --- | --- | --- |
| initial_plain | 3/4 | 0/4 |
| initial_audited | 3/4 | 0/4 |
| full_plain | 4/4 | 0/4 |
| full_audited | 4/4 | 0/4 |
| llm_freeform | 4/4 | 0/4 |
| repo_tests | 4/4 | 0/4 |

## Exploratory sensitivity: construction-intent labels (protocol v0.3; not pre-specified)

Constructed candidates labeled by how they were built (near miss = invalid, alternative = valid), including those the D19 rule marked ambiguous; the observed pre-correction state keeps its D19 label.

| Condition | False acceptance | FA exact 95% | False rejection | FR exact 95% |
| --- | --- | --- | --- | --- |
| initial_plain | 0.43 (9/21) | [0.22, 0.66] | 0.20 (2/10) | [0.03, 0.56] |
| initial_audited | 0.38 (8/21) | [0.18, 0.62] | 0.20 (2/10) | [0.03, 0.56] |
| full_plain | 0.14 (3/21) | [0.03, 0.36] | 0.00 (0/10) | [0.00, 0.31] |
| full_audited | 0.14 (3/21) | [0.03, 0.36] | 0.00 (0/10) | [0.00, 0.31] |
| llm_freeform | 0.24 (5/21) | [0.08, 0.47] | 0.00 (0/10) | [0.00, 0.31] |
| repo_tests | 0.38 (8/21) | [0.18, 0.62] | 0.40 (4/10) | [0.12, 0.74] |

## Post-hoc analyses after the internal review (exploratory, not pre-specified)

### Near misses accepted, by label status

| Condition | D19-confirmed invalid | D19 ambiguous |
| --- | --- | --- |
| initial_plain | 3/14 | 4/5 |
| initial_audited | 2/14 | 4/5 |
| full_plain | 0/14 | 3/5 |
| full_audited | 0/14 | 3/5 |
| llm_freeform | 1/14 | 4/5 |
| repo_tests | 5/14 | 3/5 |

### Rates under the independent construction checks' labels

| Condition | False acceptance | False rejection |
| --- | --- | --- |
| initial_plain | 0.50 (12/24) | 0.29 (2/7) |
| initial_audited | 0.46 (11/24) | 0.29 (2/7) |
| full_plain | 0.25 (6/24) | 0.00 (0/7) |
| full_audited | 0.25 (6/24) | 0.00 (0/7) |
| llm_freeform | 0.33 (8/24) | 0.00 (0/7) |
| repo_tests | 0.42 (10/24) | 0.43 (3/7) |

### Held-out candidates that duplicate another candidate (same graded patch, or same code apart from comments and docstrings)

* CS-01-eval-nm-5: same code as dev CS-01-dev-attack-full_session-a3
* CS-04-pre-correction: same patch as dev CS-04-dev-attack-full_session-a3
* CS-04-eval-nm-2: same patch as dev CS-04-dev-attack-full_session-a3, same patch as heldout CS-04-pre-correction

| Condition | FA without duplicates | FR without duplicates |
| --- | --- | --- |
| initial_plain | 0.29 (4/14) | 0.20 (2/10) |
| initial_audited | 0.21 (3/14) | 0.20 (2/10) |
| full_plain | 0.00 (0/14) | 0.00 (0/10) |
| full_audited | 0.00 (0/14) | 0.00 (0/10) |
| llm_freeform | 0.07 (1/14) | 0.00 (0/10) |
| repo_tests | 0.29 (4/14) | 0.40 (4/10) |

### B1 restricted to the base commit's own tests (checks added by the session agent removed)

False acceptance 0.75 (12/16); false rejection 0.00 (0/10).

## Labels and human-review queue

| Task | valid | invalid | ambiguous | unlabeled | queued for review |
| --- | --- | --- | --- | --- | --- |
| CS-01 | 2 | 6 | 0 | 0 | - |
| CS-02 | 3 | 4 | 1 | 0 | CS-02-eval-alt-2, CS-02-eval-nm-4 |
| CS-03 | 3 | 2 | 3 | 0 | CS-03-pre-correction, CS-03-eval-nm-1, CS-03-eval-nm-2, CS-03-eval-nm-4, CS-03-eval-alt-1 |
| CS-04 | 2 | 5 | 1 | 0 | CS-04-eval-nm-5 |

## Contract recovery (model mappings, proposals)

| Task | Variant | Coverage of active reference requirements (mapper 1) | Covered but contradicted | Unsupported | Contradicting | Coverage (mapper 2) | Mapping agreement (kappa) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CS-01 | initial_only | 0.50 (2/4) | R-default-unchanged | 4/5 | 4 | 0.50 (2/4) | 1.00 |
| CS-01 | full_session | 1.00 (4/4) | - | 0/6 | 0 | 1.00 (4/4) | 1.00 |
| CS-02 | initial_only | 1.00 (6/6) | - | 2/8 | 0 | 1.00 (6/6) | 1.00 |
| CS-02 | full_session | 1.00 (6/6) | - | 0/10 | 0 | 1.00 (6/6) | 0.92 |
| CS-03 | initial_only | 0.75 (3/4) | - | 1/5 | 0 | 0.75 (3/4) | 1.00 |
| CS-03 | full_session | 1.00 (4/4) | - | 1/5 | 0 | 1.00 (4/4) | 1.00 |
| CS-04 | initial_only | 0.50 (3/6) | - | 0/3 | 0 | 0.50 (3/6) | 1.00 |
| CS-04 | full_session | 1.00 (6/6) | - | 1/7 | 0 | 1.00 (6/6) | 1.00 |

## Per-task outcomes

### CS-01

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS-01-eval-alt-1 | valid_alternative | valid | - | task_failure | task_failure | pass | pass | pass | pass |
| CS-01-eval-alt-2 | valid_alternative | valid | - | task_failure | task_failure | pass | pass | pass | pass |
| CS-01-eval-nm-1 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-01-eval-nm-2 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-01-eval-nm-3 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | pass | pass |
| CS-01-eval-nm-4 | constructed_near_miss | invalid | initial_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-01-eval-nm-5 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass |
| CS-01-pre-correction | observed_pre_correction | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |

### CS-02

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS-02-eval-alt-1 | valid_alternative | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-eval-alt-2 | valid_alternative | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-eval-nm-1 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-02-eval-nm-2 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-02-eval-nm-3 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-02-eval-nm-4 | constructed_near_miss | ambiguous | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-eval-nm-5 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-02-pre-correction | observed_pre_correction | valid | - | pass | pass | pass | pass | pass | task_failure |

### CS-03

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS-03-eval-alt-1 | valid_alternative | valid | - | pass | pass | pass | pass | pass | pass |
| CS-03-eval-alt-2 | valid_alternative | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-03-eval-nm-1 | constructed_near_miss | ambiguous | - | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-03-eval-nm-2 | constructed_near_miss | ambiguous | - | pass | pass | task_failure | task_failure | pass | pass |
| CS-03-eval-nm-3 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass |
| CS-03-eval-nm-4 | constructed_near_miss | ambiguous | - | task_failure | task_failure | pass | pass | pass | pass |
| CS-03-eval-nm-5 | constructed_near_miss | invalid | correction_violating | pass | task_failure | task_failure | task_failure | task_failure | pass |
| CS-03-pre-correction | observed_pre_correction | valid | - | pass | pass | pass | pass | pass | pass |

### CS-04

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS-04-eval-alt-1 | valid_alternative | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-eval-alt-2 | valid_alternative | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-eval-nm-1 | constructed_near_miss | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | pass |
| CS-04-eval-nm-2 | constructed_near_miss | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-eval-nm-3 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-04-eval-nm-4 | constructed_near_miss | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-eval-nm-5 | constructed_near_miss | ambiguous | - | pass | pass | pass | pass | pass | pass |
| CS-04-pre-correction | observed_pre_correction | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |

## Appendix: cluster-bootstrap intervals

95% percentile intervals of a bootstrap that resamples task families (each distinct graded patch once). They are not inferential: the run has 4 task families, fewer than 10. Intervals marked * are degenerate (every family has the same rate or difference).

| Condition | False acceptance [95% bootstrap] | False rejection [95% bootstrap] |
| --- | --- | --- |
| initial_plain | 0.31 (5/16) [0.07, 0.67] | 0.20 (2/10) [0.00, 0.67] |
| initial_audited | 0.25 (4/16) [0.00, 0.56] | 0.20 (2/10) [0.00, 0.67] |
| full_plain | 0.00 (0/16) [0.00, 0.00]* | 0.00 (0/10) [0.00, 0.00]* |
| full_audited | 0.00 (0/16) [0.00, 0.00]* | 0.00 (0/10) [0.00, 0.00]* |
| llm_freeform | 0.06 (1/16) [0.00, 0.14] | 0.00 (0/10) [0.00, 0.00]* |
| repo_tests | 0.31 (5/16) [0.11, 0.67] | 0.40 (4/10) [0.00, 0.82] |

| A | B | Metric | A - B | 95% bootstrap | Families |
| --- | --- | --- | --- | --- | --- |
| initial_plain | full_plain | FA | +0.31 | [+0.07, +0.67] | 4 |
| initial_plain | full_plain | FR | +0.20 | [+0.00, +0.67] | 4 |
| initial_audited | full_audited | FA | +0.25 | [+0.00, +0.56] | 4 |
| initial_audited | full_audited | FR | +0.20 | [+0.00, +0.67] | 4 |
| initial_plain | initial_audited | FA | +0.06 | [+0.00, +0.30] | 4 |
| initial_plain | initial_audited | FR | +0.00 | [+0.00, +0.00]* | 4 |
| full_plain | full_audited | FA | +0.00 | [+0.00, +0.00]* | 4 |
| full_plain | full_audited | FR | +0.00 | [+0.00, +0.00]* | 4 |
| llm_freeform | full_audited | FA | +0.06 | [+0.00, +0.14] | 4 |
| llm_freeform | full_audited | FR | +0.00 | [+0.00, +0.00]* | 4 |
| llm_freeform | full_plain | FA | +0.06 | [+0.00, +0.14] | 4 |
| llm_freeform | full_plain | FR | +0.00 | [+0.00, +0.00]* | 4 |
| repo_tests | full_audited | FA | +0.31 | [+0.11, +0.67] | 4 |
| repo_tests | full_audited | FR | +0.40 | [+0.00, +0.82] | 4 |

