# Analysis (proposed labels allowed (automated pilot))

Tasks: 4 | independent task families: 4 | results: 672

> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth. With this few task families the intervals are not meaningful evidence of an effect.

> **Reporting rules of a new run** (protocol §15.7, §16.6): the run was graded with tc-harness/0.3.5, and new runs use tc-harness/0.3.5 or later (protocol §16.1). Each distinct graded patch counts once (79 distinct among 79 held-out candidates). The per-family table is the primary display, every paired comparison carries exact sign-flip p-values over task families with their attainable floors, and the cluster-bootstrap intervals are in the appendix, marked as not inferential (4 task families, fewer than 10).

## Primary display: false acceptance and false rejection per task family

(numerator/denominator) per task family, each distinct graded patch once; the reference solution and the no-op are excluded (see the sanity checks). The last two columns pool the families.

| Condition | CS-01 FA | CS-01 FR | CS-02 FA | CS-02 FR | CS-03 FA | CS-03 FR | CS-04 FA | CS-04 FR | All FA | All FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 10/10 | 10/10 | 0/2 | 0/17 | 4/7 | 3/13 | 10/10 | 0/10 | 0.83 (24/29) | 0.26 (13/50) |
| initial_audited | 10/10 | 10/10 | 0/2 | 0/17 | 4/7 | 3/13 | 10/10 | 0/10 | 0.83 (24/29) | 0.26 (13/50) |
| full_plain | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 0/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.00 (0/50) |
| full_audited | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 6/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.12 (6/50) |
| llm_freeform | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 2/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.04 (2/50) |
| repo_tests | 0/10 | 8/10 | 0/2 | 17/17 | 0/7 | 9/13 | 0/10 | 0/10 | 0.00 (0/29) | 0.68 (34/50) |

## Paired comparisons: exact sign-flip tests over task families

A - B is the pooled difference (same candidates, each distinct graded patch once); the p-values test the sum over families of the count differences (each candidate weighs the same) with an exact sign-flip test, which cannot go below its floor. p (A > B): the first-named condition errs more.

| A | B | Metric | A - B | Per-family A - B | p (A > B) | p (A < B) | p two-sided | p two-sided, family means | Floor one-sided / two-sided | Families | A acc & B rej | A rej & B acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | full_plain | FA | +0.76 | CS-01 +1.00, CS-02 -1.00, CS-03 +0.57, CS-04 +1.00 | 0.125 | 0.938 | 0.25 | 0.625 | 0.0625 / 0.125 | 4 | 24 | 2 |
| initial_plain | full_plain | FR | +0.26 | CS-01 +1.00, CS-02 +0.00, CS-03 +0.23, CS-04 +0.00 | 0.25 | 1 | 0.5 | 0.5 | 0.0625 / 0.125 | 4 | 0 | 13 |
| initial_audited | full_audited | FA | +0.76 | CS-01 +1.00, CS-02 -1.00, CS-03 +0.57, CS-04 +1.00 | 0.125 | 0.938 | 0.25 | 0.625 | 0.0625 / 0.125 | 4 | 24 | 2 |
| initial_audited | full_audited | FR | +0.14 | CS-01 +1.00, CS-02 +0.00, CS-03 -0.23, CS-04 +0.00 | 0.5 | 0.75 | 1 | 1 | 0.0625 / 0.125 | 4 | 5 | 12 |
| initial_plain | initial_audited | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| initial_plain | initial_audited | FR | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| full_plain | full_audited | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| full_plain | full_audited | FR | -0.12 | CS-01 +0.00, CS-02 +0.00, CS-03 -0.46, CS-04 +0.00 | 1 | 0.5 | 1 | 1 | 0.0625 / 0.125 | 4 | 6 | 0 |
| llm_freeform | full_audited | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| llm_freeform | full_audited | FR | -0.08 | CS-01 +0.00, CS-02 +0.00, CS-03 -0.31, CS-04 +0.00 | 1 | 0.5 | 1 | 1 | 0.0625 / 0.125 | 4 | 4 | 0 |
| llm_freeform | full_plain | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| llm_freeform | full_plain | FR | +0.04 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.15, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 2 |
| repo_tests | full_audited | FA | -0.07 | CS-01 +0.00, CS-02 -1.00, CS-03 +0.00, CS-04 +0.00 | 1 | 0.5 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 2 |
| repo_tests | full_audited | FR | +0.56 | CS-01 +0.80, CS-02 +1.00, CS-03 +0.23, CS-04 +0.00 | 0.125 | 1 | 0.25 | 0.25 | 0.0625 / 0.125 | 4 | 0 | 28 |

**Null results.** 14 of 14 tested comparisons have a two-sided exact p-value of 0.05 or more: initial_plain vs full_plain FA; initial_plain vs full_plain FR; initial_audited vs full_audited FA; initial_audited vs full_audited FR; initial_plain vs initial_audited FA; initial_plain vs initial_audited FR; full_plain vs full_audited FA; full_plain vs full_audited FR; llm_freeform vs full_audited FA; llm_freeform vs full_audited FR; llm_freeform vs full_plain FA; llm_freeform vs full_plain FR; repo_tests vs full_audited FA; repo_tests vs full_audited FR. With at most 4 families no two-sided p-value can go below 0.125, so none can reach 0.05.

## Pooled false acceptance / false rejection by condition

Pooled rates with (numerator/denominator), each distinct graded patch once; reference solution and no-op are excluded (see sanity table). The exact (Clopper-Pearson) interval ignores clustering and is given only as a reference scale; the cluster-bootstrap intervals are in the appendix.

| Condition | False acceptance | FA exact 95% | FA macro | False rejection | FR exact 95% | FR macro | Youden's J | Tasks with an accepted negative | Infra outcomes | Excluded (unlabeled/ambiguous) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0.83 (24/29) | [0.64, 0.94] | 0.64 | 0.26 (13/50) | [0.15, 0.40] | 0.31 | -0.09 | 3/4 | 0/79 | 0 |
| initial_audited | 0.83 (24/29) | [0.64, 0.94] | 0.64 | 0.26 (13/50) | [0.15, 0.40] | 0.31 | -0.09 | 3/4 | 0/79 | 0 |
| full_plain | 0.07 (2/29) | [0.01, 0.23] | 0.25 | 0.00 (0/50) | [0.00, 0.07] | 0.00 | +0.93 | 1/4 | 0/79 | 0 |
| full_audited | 0.07 (2/29) | [0.01, 0.23] | 0.25 | 0.12 (6/50) | [0.05, 0.24] | 0.12 | +0.81 | 1/4 | 0/79 | 0 |
| llm_freeform | 0.07 (2/29) | [0.01, 0.23] | 0.25 | 0.04 (2/50) | [0.00, 0.14] | 0.04 | +0.89 | 1/4 | 0/79 | 0 |
| repo_tests | 0.00 (0/29) | [0.00, 0.12] | 0.00 | 0.68 (34/50) | [0.53, 0.80] | 0.62 | +0.32 | 0/4 | 0/79 | 0 |

## By candidate stratum

`task` is the task's own candidates (task.json); every other stratum's candidates are listed in tasks/<id>/strata/<name>.json (reference solution and no-op excluded). The tables above pool the strata.

### fresh-v1 (tasks: CS-01, CS-02, CS-03, CS-04; families: 4)

| Condition | False acceptance | FA exact 95% | False rejection | FR exact 95% | Infra outcomes | Excluded (unlabeled/ambiguous) |
| --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0.83 (24/29) | [0.64, 0.94] | 0.26 (13/50) | [0.15, 0.40] | 0/79 | 0 |
| initial_audited | 0.83 (24/29) | [0.64, 0.94] | 0.26 (13/50) | [0.15, 0.40] | 0/79 | 0 |
| full_plain | 0.07 (2/29) | [0.01, 0.23] | 0.00 (0/50) | [0.00, 0.07] | 0/79 | 0 |
| full_audited | 0.07 (2/29) | [0.01, 0.23] | 0.12 (6/50) | [0.05, 0.24] | 0/79 | 0 |
| llm_freeform | 0.07 (2/29) | [0.01, 0.23] | 0.04 (2/50) | [0.00, 0.14] | 0/79 | 0 |
| repo_tests | 0.00 (0/29) | [0.00, 0.12] | 0.68 (34/50) | [0.53, 0.80] | 0/79 | 0 |

## Fresh-agent attempts: solve rates and audit exclusions

Solved: D19's natural-candidate rule labels the attempt valid (reference checks and regression norm); D19 ambiguous or no proposal: undecided, counted as not solved; every attempt counts, duplicates included; excluded attempts count nowhere (protocol §15.4).

| Configuration | Variant | Attempts | Solved | Not solved | Undecided | Solve rate | Finished / gave up / error | Per family (solved/attempts) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| config-A | final | 19 | 19 | 0 | 0 | 1.00 | 19 / 0 / 0 | CS-01 5/5, CS-02 4/4, CS-03 5/5, CS-04 5/5 |
| config-A | u1 | 20 | 6 | 14 | 0 | 0.30 | 20 / 0 / 0 | CS-01 0/5, CS-02 3/5, CS-03 3/5, CS-04 0/5 |
| config-B | final | 20 | 20 | 0 | 0 | 1.00 | 20 / 0 / 0 | CS-01 5/5, CS-02 5/5, CS-03 5/5, CS-04 5/5 |
| config-B | u1 | 20 | 5 | 15 | 0 | 0.25 | 20 / 0 / 0 | CS-01 0/5, CS-02 5/5, CS-03 0/5, CS-04 0/5 |

### Solve rates under each labeling

Solved under the second labeling: the independent labeler passes the attempt (valid); task_failure: not solved; any other outcome (ambiguous) or not graded by the labeler: undecided, counted as not solved; every attempt counts, duplicates included (protocol §15.4, §15.5).

| Configuration | Variant | Attempts | Solved, D19 | Solve rate, D19 | Solved, independent | Not solved, independent | Undecided, independent | Solve rate, independent | Per family, independent (solved/attempts) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| config-A | final | 19 | 19 | 1.00 | 19 | 0 | 0 | 1.00 | CS-01 5/5, CS-02 4/4, CS-03 5/5, CS-04 5/5 |
| config-A | u1 | 20 | 6 | 0.30 | 8 | 12 | 0 | 0.40 | CS-01 0/5, CS-02 5/5, CS-03 3/5, CS-04 0/5 |
| config-B | final | 20 | 20 | 1.00 | 20 | 0 | 0 | 1.00 | CS-01 5/5, CS-02 5/5, CS-03 5/5, CS-04 5/5 |
| config-B | u1 | 20 | 5 | 0.25 | 5 | 15 | 0 | 0.25 | CS-01 0/5, CS-02 5/5, CS-03 0/5, CS-04 0/5 |

u1 attempts that violate a correction requirement: 27/40 (initial_plain accepts 24/27; full_plain accepts 0/27).

Excluded from every analysis (1):

* CS-02-fresh-A-final-1 (CS-02, attempt CS-02-fresh-A-final-1): the fresh-attempt audit found a read of forbidden material

## Independent labeler: a second labeling (protocol §15.4, §15.5)

The independent labeler (verifier independent_label, condition reference_check; protocol §15.5) labels a candidate valid if it passes, invalid if it fails with task_failure, and ambiguous on any other outcome (unresolved, environment failure, verifier error or timeout, recorded as such); a candidate it did not grade is unlabeled. Its verdicts are a second labeling (§15.4): a model proposal, as D19 is, never a human label. The labeler is label support, never an evaluated condition.

Graded on CS-01, CS-02, CS-03, CS-04. Held-out candidates: 52 valid, 27 invalid, 0 ambiguous, 0 not graded. The labeler passes on (sanity): CS-01 reference 1/1; CS-02 reference 1/1; CS-03 reference 1/1; CS-04 reference 1/1.

### False acceptance and false rejection under each labeling

(numerator/denominator), counted as the primary analysis counts them; primary: D19's proposals, or a human label where one exists (the label rule of the primary analysis); independent: the labeler's verdicts. Unlabeled and ambiguous candidates are excluded and counted.

| Condition | FA, primary | FA, independent | FR, primary | FR, independent | Excluded (unlabeled/ambiguous), primary / independent |
| --- | --- | --- | --- | --- | --- |
| initial_plain | 0.83 (24/29) | 0.89 (24/27) | 0.26 (13/50) | 0.29 (15/52) | 0 / 0 |
| initial_audited | 0.83 (24/29) | 0.89 (24/27) | 0.26 (13/50) | 0.29 (15/52) | 0 / 0 |
| full_plain | 0.07 (2/29) | 0.00 (0/27) | 0.00 (0/50) | 0.00 (0/52) | 0 / 0 |
| full_audited | 0.07 (2/29) | 0.00 (0/27) | 0.12 (6/50) | 0.12 (6/52) | 0 / 0 |
| llm_freeform | 0.07 (2/29) | 0.00 (0/27) | 0.04 (2/50) | 0.04 (2/52) | 0 / 0 |
| repo_tests | 0.00 (0/29) | 0.00 (0/27) | 0.68 (34/50) | 0.69 (36/52) | 0 / 0 |

| Condition | Labeling | CS-01 FA | CS-01 FR | CS-02 FA | CS-02 FR | CS-03 FA | CS-03 FR | CS-04 FA | CS-04 FR | All FA | All FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | primary | 10/10 | 10/10 | 0/2 | 0/17 | 4/7 | 3/13 | 10/10 | 0/10 | 0.83 (24/29) | 0.26 (13/50) |
| initial_plain | independent | 10/10 | 10/10 | 0/0 | 2/19 | 4/7 | 3/13 | 10/10 | 0/10 | 0.89 (24/27) | 0.29 (15/52) |
| initial_audited | primary | 10/10 | 10/10 | 0/2 | 0/17 | 4/7 | 3/13 | 10/10 | 0/10 | 0.83 (24/29) | 0.26 (13/50) |
| initial_audited | independent | 10/10 | 10/10 | 0/0 | 2/19 | 4/7 | 3/13 | 10/10 | 0/10 | 0.89 (24/27) | 0.29 (15/52) |
| full_plain | primary | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 0/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.00 (0/50) |
| full_plain | independent | 0/10 | 0/10 | 0/0 | 0/19 | 0/7 | 0/13 | 0/10 | 0/10 | 0.00 (0/27) | 0.00 (0/52) |
| full_audited | primary | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 6/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.12 (6/50) |
| full_audited | independent | 0/10 | 0/10 | 0/0 | 0/19 | 0/7 | 6/13 | 0/10 | 0/10 | 0.00 (0/27) | 0.12 (6/52) |
| llm_freeform | primary | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 2/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.04 (2/50) |
| llm_freeform | independent | 0/10 | 0/10 | 0/0 | 0/19 | 0/7 | 2/13 | 0/10 | 0/10 | 0.00 (0/27) | 0.04 (2/52) |
| repo_tests | primary | 0/10 | 8/10 | 0/2 | 17/17 | 0/7 | 9/13 | 0/10 | 0/10 | 0.00 (0/29) | 0.68 (34/50) |
| repo_tests | independent | 0/10 | 8/10 | 0/0 | 19/19 | 0/7 | 9/13 | 0/10 | 0/10 | 0.00 (0/27) | 0.69 (36/52) |

### Stratum fresh-v1 (tasks: CS-01, CS-02, CS-03, CS-04)

| Condition | FA, primary | FA, independent | FR, primary | FR, independent | Excluded (unlabeled/ambiguous), primary / independent |
| --- | --- | --- | --- | --- | --- |
| initial_plain | 0.83 (24/29) | 0.89 (24/27) | 0.26 (13/50) | 0.29 (15/52) | 0 / 0 |
| initial_audited | 0.83 (24/29) | 0.89 (24/27) | 0.26 (13/50) | 0.29 (15/52) | 0 / 0 |
| full_plain | 0.07 (2/29) | 0.00 (0/27) | 0.00 (0/50) | 0.00 (0/52) | 0 / 0 |
| full_audited | 0.07 (2/29) | 0.00 (0/27) | 0.12 (6/50) | 0.12 (6/52) | 0 / 0 |
| llm_freeform | 0.07 (2/29) | 0.00 (0/27) | 0.04 (2/50) | 0.04 (2/52) | 0 / 0 |
| repo_tests | 0.00 (0/29) | 0.00 (0/27) | 0.68 (34/50) | 0.69 (36/52) | 0 / 0 |

| Condition | Labeling | CS-01 FA | CS-01 FR | CS-02 FA | CS-02 FR | CS-03 FA | CS-03 FR | CS-04 FA | CS-04 FR | All FA | All FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | primary | 10/10 | 10/10 | 0/2 | 0/17 | 4/7 | 3/13 | 10/10 | 0/10 | 0.83 (24/29) | 0.26 (13/50) |
| initial_plain | independent | 10/10 | 10/10 | 0/0 | 2/19 | 4/7 | 3/13 | 10/10 | 0/10 | 0.89 (24/27) | 0.29 (15/52) |
| initial_audited | primary | 10/10 | 10/10 | 0/2 | 0/17 | 4/7 | 3/13 | 10/10 | 0/10 | 0.83 (24/29) | 0.26 (13/50) |
| initial_audited | independent | 10/10 | 10/10 | 0/0 | 2/19 | 4/7 | 3/13 | 10/10 | 0/10 | 0.89 (24/27) | 0.29 (15/52) |
| full_plain | primary | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 0/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.00 (0/50) |
| full_plain | independent | 0/10 | 0/10 | 0/0 | 0/19 | 0/7 | 0/13 | 0/10 | 0/10 | 0.00 (0/27) | 0.00 (0/52) |
| full_audited | primary | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 6/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.12 (6/50) |
| full_audited | independent | 0/10 | 0/10 | 0/0 | 0/19 | 0/7 | 6/13 | 0/10 | 0/10 | 0.00 (0/27) | 0.12 (6/52) |
| llm_freeform | primary | 0/10 | 0/10 | 2/2 | 0/17 | 0/7 | 2/13 | 0/10 | 0/10 | 0.07 (2/29) | 0.04 (2/50) |
| llm_freeform | independent | 0/10 | 0/10 | 0/0 | 0/19 | 0/7 | 2/13 | 0/10 | 0/10 | 0.00 (0/27) | 0.04 (2/52) |
| repo_tests | primary | 0/10 | 8/10 | 0/2 | 17/17 | 0/7 | 9/13 | 0/10 | 0/10 | 0.00 (0/29) | 0.68 (34/50) |
| repo_tests | independent | 0/10 | 8/10 | 0/0 | 19/19 | 0/7 | 9/13 | 0/10 | 0/10 | 0.00 (0/27) | 0.69 (36/52) |

### Agreement between D19 and the independent labeler

D19's proposal (labeler builder:refcheck+regression+construction:v1) against the second labeling, each distinct graded patch once (a unit's label is its members' when they agree, else ambiguous); the 2x2 table holds the units both label valid or invalid, the cross-table every unit (none: no D19 proposal, or not graded by the labeler); per candidate stratum (§15.4 estimand 4, §15.5).

**Stratum fresh-v1 (tasks: CS-01, CS-02, CS-03, CS-04)**: 79 unit(s); both decide 79: agree 77, disagree 2 (agreement 0.97, Cohen's kappa 0.94).

| D19 \ independent | valid | invalid |
| --- | --- | --- |
| valid | 50 | 0 |
| invalid | 2 | 27 |

Outside the 2x2 table (none: no D19 proposal, or not graded by the labeler): none.

* CS-02-fresh-A-u1-4 (CS-02): D19 invalid, independent valid (outcome pass)
* CS-02-fresh-A-u1-5 (CS-02): D19 invalid, independent valid (outcome pass)

## Oracle-gated view (secondary)

A verifier x task cell is dropped when the verifier does not pass the task's reference solution in the run's sanity grading; its held-out candidates are the lost yield (secondary view, protocol §15.7).

| Condition | Cells kept | Dropped | Lost yield (invalid / valid) | False acceptance | False rejection |
| --- | --- | --- | --- | --- | --- |
| initial_plain | 3/4 | CS-01: does not pass its reference (task_failure) | 10 / 10 | 0.74 (14/19) | 0.07 (3/40) |
| initial_audited | 3/4 | CS-01: does not pass its reference (task_failure) | 10 / 10 | 0.74 (14/19) | 0.07 (3/40) |
| full_plain | 4/4 | - | 0 / 0 | 0.07 (2/29) | 0.00 (0/50) |
| full_audited | 4/4 | - | 0 / 0 | 0.07 (2/29) | 0.12 (6/50) |
| llm_freeform | 4/4 | - | 0 / 0 | 0.07 (2/29) | 0.04 (2/50) |
| repo_tests | 4/4 | - | 0 / 0 | 0.00 (0/29) | 0.68 (34/50) |

### Oracle-gated paired comparisons

A - B is the pooled difference (same candidates, on the tasks that both conditions keep); the p-values test the sum over families of the count differences (each candidate weighs the same) with an exact sign-flip test, which cannot go below its floor. p (A > B): the first-named condition errs more.

| A | B | Metric | A - B | Per-family A - B | p (A > B) | p (A < B) | p two-sided | p two-sided, family means | Floor one-sided / two-sided | Families | A acc & B rej | A rej & B acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | full_plain | FA | +0.63 | CS-02 -1.00, CS-03 +0.57, CS-04 +1.00 | 0.25 | 0.875 | 0.5 | 1 | 0.125 / 0.25 | 3 | 14 | 2 |
| initial_plain | full_plain | FR | +0.07 | CS-02 +0.00, CS-03 +0.23, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.125 / 0.25 | 3 | 0 | 3 |
| initial_audited | full_audited | FA | +0.63 | CS-02 -1.00, CS-03 +0.57, CS-04 +1.00 | 0.25 | 0.875 | 0.5 | 1 | 0.125 / 0.25 | 3 | 14 | 2 |
| initial_audited | full_audited | FR | -0.07 | CS-02 +0.00, CS-03 -0.23, CS-04 +0.00 | 1 | 0.5 | 1 | 1 | 0.125 / 0.25 | 3 | 5 | 2 |
| initial_plain | initial_audited | FA | +0.00 | CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.125 / 0.25 | 3 | 0 | 0 |
| initial_plain | initial_audited | FR | +0.00 | CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.125 / 0.25 | 3 | 0 | 0 |
| full_plain | full_audited | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| full_plain | full_audited | FR | -0.12 | CS-01 +0.00, CS-02 +0.00, CS-03 -0.46, CS-04 +0.00 | 1 | 0.5 | 1 | 1 | 0.0625 / 0.125 | 4 | 6 | 0 |
| llm_freeform | full_audited | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| llm_freeform | full_audited | FR | -0.08 | CS-01 +0.00, CS-02 +0.00, CS-03 -0.31, CS-04 +0.00 | 1 | 0.5 | 1 | 1 | 0.0625 / 0.125 | 4 | 4 | 0 |
| llm_freeform | full_plain | FA | +0.00 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.00, CS-04 +0.00 | 1 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 0 |
| llm_freeform | full_plain | FR | +0.04 | CS-01 +0.00, CS-02 +0.00, CS-03 +0.15, CS-04 +0.00 | 0.5 | 1 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 2 |
| repo_tests | full_audited | FA | -0.07 | CS-01 +0.00, CS-02 -1.00, CS-03 +0.00, CS-04 +0.00 | 1 | 0.5 | 1 | 1 | 0.0625 / 0.125 | 4 | 0 | 2 |
| repo_tests | full_audited | FR | +0.56 | CS-01 +0.80, CS-02 +1.00, CS-03 +0.23, CS-04 +0.00 | 0.125 | 1 | 0.25 | 0.25 | 0.0625 / 0.125 | 4 | 0 | 28 |

**Null results.** 14 of 14 tested comparisons have a two-sided exact p-value of 0.05 or more: initial_plain vs full_plain FA; initial_plain vs full_plain FR; initial_audited vs full_audited FA; initial_audited vs full_audited FR; initial_plain vs initial_audited FA; initial_plain vs initial_audited FR; full_plain vs full_audited FA; full_plain vs full_audited FR; llm_freeform vs full_audited FA; llm_freeform vs full_audited FR; llm_freeform vs full_plain FA; llm_freeform vs full_plain FR; repo_tests vs full_audited FA; repo_tests vs full_audited FR. With at most 4 families no two-sided p-value can go below 0.125, so none can reach 0.05.

## Distinct graded patches

79 distinct graded patches among 79 held-out candidates: held-out candidates of a task with the same graded patch count once; the representative is the natural state, else the first id (protocol §15.4, §15.7).

## Accepted negatives by type

| Condition | correction-violating | initial-violating | unspecified |
| --- | --- | --- | --- |
| initial_plain | 24/27 | - | 0/2 |
| initial_audited | 24/27 | - | 0/2 |
| full_plain | 0/27 | - | 2/2 |
| full_audited | 0/27 | - | 2/2 |
| llm_freeform | 0/27 | - | 2/2 |
| repo_tests | 0/27 | - | 0/2 |

## Sanity checks (excluded from primary metrics)

| Condition | reference passes | no-op passes |
| --- | --- | --- |
| initial_plain | 3/4 | -/- |
| initial_audited | 3/4 | -/- |
| full_plain | 4/4 | -/- |
| full_audited | 4/4 | -/- |
| llm_freeform | 4/4 | -/- |
| repo_tests | 4/4 | -/- |

## Exploratory sensitivity: construction-intent labels (protocol v0.3; not pre-specified)

Constructed candidates labeled by how they were built (near miss = invalid, alternative = valid), including those the D19 rule marked ambiguous; the observed pre-correction state keeps its D19 label.

| Condition | False acceptance | FA exact 95% | False rejection | FR exact 95% |
| --- | --- | --- | --- | --- |
| initial_plain | 0.83 (24/29) | [0.64, 0.94] | 0.26 (13/50) | [0.15, 0.40] |
| initial_audited | 0.83 (24/29) | [0.64, 0.94] | 0.26 (13/50) | [0.15, 0.40] |
| full_plain | 0.07 (2/29) | [0.01, 0.23] | 0.00 (0/50) | [0.00, 0.07] |
| full_audited | 0.07 (2/29) | [0.01, 0.23] | 0.12 (6/50) | [0.05, 0.24] |
| llm_freeform | 0.07 (2/29) | [0.01, 0.23] | 0.04 (2/50) | [0.00, 0.14] |
| repo_tests | 0.00 (0/29) | [0.00, 0.12] | 0.68 (34/50) | [0.53, 0.80] |

## Post-hoc analyses after the internal review (exploratory, not pre-specified)

### Near misses accepted, by label status

| Condition | D19-confirmed invalid | D19 ambiguous |
| --- | --- | --- |
| initial_plain | 0/0 | 0/0 |
| initial_audited | 0/0 | 0/0 |
| full_plain | 0/0 | 0/0 |
| full_audited | 0/0 | 0/0 |
| llm_freeform | 0/0 | 0/0 |
| repo_tests | 0/0 | 0/0 |

### Rates under the independent construction checks' labels

| Condition | False acceptance | False rejection |
| --- | --- | --- |
| initial_plain | 0.83 (24/29) | 0.26 (13/50) |
| initial_audited | 0.83 (24/29) | 0.26 (13/50) |
| full_plain | 0.07 (2/29) | 0.00 (0/50) |
| full_audited | 0.07 (2/29) | 0.12 (6/50) |
| llm_freeform | 0.07 (2/29) | 0.04 (2/50) |
| repo_tests | 0.00 (0/29) | 0.68 (34/50) |

### Held-out candidates that duplicate another candidate (same graded patch, or same code apart from comments and docstrings)

* CS-01-eval-nm-5: same code as dev CS-01-dev-attack-full_session-a3
* CS-04-pre-correction: same patch as dev CS-04-dev-attack-full_session-a3
* CS-04-eval-nm-2: same patch as dev CS-04-dev-attack-full_session-a3, same patch as heldout CS-04-pre-correction

| Condition | FA without duplicates | FR without duplicates |
| --- | --- | --- |
| initial_plain | 0.83 (24/29) | 0.26 (13/50) |
| initial_audited | 0.83 (24/29) | 0.26 (13/50) |
| full_plain | 0.07 (2/29) | 0.00 (0/50) |
| full_audited | 0.07 (2/29) | 0.12 (6/50) |
| llm_freeform | 0.07 (2/29) | 0.04 (2/50) |
| repo_tests | 0.00 (0/29) | 0.68 (34/50) |

### B1 restricted to the base commit's own tests (checks added by the session agent removed)

False acceptance 0.59 (17/29); false rejection 0.00 (0/50).

## Labels and human-review queue

| Task | valid | invalid | ambiguous | unlabeled | queued for review |
| --- | --- | --- | --- | --- | --- |
| CS-01 | 2 | 6 | 0 | 0 | - |
| CS-01 (stratum fresh-v1) | 10 | 10 | 0 | 0 | CS-01-fresh-A-final-1, CS-01-fresh-A-final-2, CS-01-fresh-A-final-3, CS-01-fresh-A-final-4, CS-01-fresh-A-final-5, CS-01-fresh-A-u1-1, CS-01-fresh-A-u1-2, CS-01-fresh-A-u1-3, CS-01-fresh-A-u1-4, CS-01-fresh-A-u1-5, CS-01-fresh-B-final-1, CS-01-fresh-B-final-2, CS-01-fresh-B-final-3, CS-01-fresh-B-final-4, CS-01-fresh-B-final-5, CS-01-fresh-B-u1-1, CS-01-fresh-B-u1-2, CS-01-fresh-B-u1-3, CS-01-fresh-B-u1-4, CS-01-fresh-B-u1-5 |
| CS-02 | 3 | 4 | 1 | 0 | CS-02-eval-alt-2, CS-02-eval-nm-4 |
| CS-02 (stratum fresh-v1) | 17 | 2 | 0 | 0 | CS-02-fresh-A-final-2, CS-02-fresh-A-final-3, CS-02-fresh-A-final-4, CS-02-fresh-A-final-5, CS-02-fresh-A-u1-1, CS-02-fresh-A-u1-2, CS-02-fresh-A-u1-3, CS-02-fresh-A-u1-4, CS-02-fresh-A-u1-5, CS-02-fresh-B-final-1, CS-02-fresh-B-final-2, CS-02-fresh-B-final-3, CS-02-fresh-B-final-4, CS-02-fresh-B-final-5, CS-02-fresh-B-u1-1, CS-02-fresh-B-u1-2, CS-02-fresh-B-u1-3, CS-02-fresh-B-u1-4, CS-02-fresh-B-u1-5 |
| CS-03 | 3 | 2 | 3 | 0 | CS-03-pre-correction, CS-03-eval-nm-1, CS-03-eval-nm-2, CS-03-eval-nm-4, CS-03-eval-alt-1 |
| CS-03 (stratum fresh-v1) | 13 | 7 | 0 | 0 | CS-03-fresh-A-final-1, CS-03-fresh-A-final-2, CS-03-fresh-A-final-3, CS-03-fresh-A-final-4, CS-03-fresh-A-final-5, CS-03-fresh-A-u1-1, CS-03-fresh-A-u1-2, CS-03-fresh-A-u1-3, CS-03-fresh-A-u1-4, CS-03-fresh-A-u1-5, CS-03-fresh-B-final-1, CS-03-fresh-B-final-2, CS-03-fresh-B-final-3, CS-03-fresh-B-final-4, CS-03-fresh-B-final-5, CS-03-fresh-B-u1-1, CS-03-fresh-B-u1-2, CS-03-fresh-B-u1-3, CS-03-fresh-B-u1-4, CS-03-fresh-B-u1-5 |
| CS-04 | 2 | 5 | 1 | 0 | CS-04-eval-nm-5 |
| CS-04 (stratum fresh-v1) | 10 | 10 | 0 | 0 | CS-04-fresh-A-final-1, CS-04-fresh-A-final-2, CS-04-fresh-A-final-3, CS-04-fresh-A-final-4, CS-04-fresh-A-final-5, CS-04-fresh-A-u1-1, CS-04-fresh-A-u1-2, CS-04-fresh-A-u1-3, CS-04-fresh-A-u1-4, CS-04-fresh-A-u1-5, CS-04-fresh-B-final-1, CS-04-fresh-B-final-2, CS-04-fresh-B-final-3, CS-04-fresh-B-final-4, CS-04-fresh-B-final-5, CS-04-fresh-B-u1-1, CS-04-fresh-B-u1-2, CS-04-fresh-B-u1-3, CS-04-fresh-B-u1-4, CS-04-fresh-B-u1-5 |

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

| Candidate | Stratum | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS-01-fresh-A-final-1 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-01-fresh-A-final-2 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | pass |
| CS-01-fresh-A-final-3 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-01-fresh-A-final-4 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | pass |
| CS-01-fresh-A-final-5 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-01-fresh-A-u1-1 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-A-u1-2 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-A-u1-3 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-A-u1-4 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-A-u1-5 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-B-final-1 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-01-fresh-B-final-2 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-01-fresh-B-final-3 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-01-fresh-B-final-4 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-01-fresh-B-final-5 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-01-fresh-B-u1-1 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-B-u1-2 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-B-u1-3 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-B-u1-4 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-01-fresh-B-u1-5 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |

### CS-02

| Candidate | Stratum | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS-02-fresh-A-final-2 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-A-final-3 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-A-final-4 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-A-final-5 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-A-u1-1 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-A-u1-2 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-A-u1-3 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-A-u1-4 | fresh-v1 | fresh_attempt | invalid | unspecified | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-02-fresh-A-u1-5 | fresh-v1 | fresh_attempt | invalid | unspecified | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-02-fresh-B-final-1 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-final-2 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-final-3 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-final-4 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-final-5 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-u1-1 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-u1-2 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-u1-3 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-u1-4 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-02-fresh-B-u1-5 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |

### CS-03

| Candidate | Stratum | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS-03-fresh-A-final-1 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-03-fresh-A-final-2 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-03-fresh-A-final-3 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-03-fresh-A-final-4 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | pass | pass | task_failure |
| CS-03-fresh-A-final-5 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-03-fresh-A-u1-1 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | task_failure | pass | task_failure |
| CS-03-fresh-A-u1-2 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-03-fresh-A-u1-3 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | task_failure | pass | task_failure |
| CS-03-fresh-A-u1-4 | fresh-v1 | fresh_attempt | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-03-fresh-A-u1-5 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-03-fresh-B-final-1 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | task_failure | task_failure | task_failure |
| CS-03-fresh-B-final-2 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-03-fresh-B-final-3 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | task_failure | pass | task_failure |
| CS-03-fresh-B-final-4 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | task_failure | task_failure | task_failure |
| CS-03-fresh-B-final-5 | fresh-v1 | fresh_attempt | valid | - | task_failure | task_failure | pass | task_failure | pass | task_failure |
| CS-03-fresh-B-u1-1 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-03-fresh-B-u1-2 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-03-fresh-B-u1-3 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-03-fresh-B-u1-4 | fresh-v1 | fresh_attempt | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-03-fresh-B-u1-5 | fresh-v1 | fresh_attempt | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |

### CS-04

| Candidate | Stratum | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS-04-fresh-A-final-1 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-A-final-2 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-A-final-3 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-A-final-4 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-A-final-5 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-A-u1-1 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-A-u1-2 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-A-u1-3 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-A-u1-4 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-A-u1-5 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-B-final-1 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-B-final-2 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-B-final-3 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-B-final-4 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-B-final-5 | fresh-v1 | fresh_attempt | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-fresh-B-u1-1 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-B-u1-2 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-B-u1-3 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-B-u1-4 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-fresh-B-u1-5 | fresh-v1 | fresh_attempt | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |

## Appendix: cluster-bootstrap intervals

95% percentile intervals of a bootstrap that resamples task families (each distinct graded patch once). They are not inferential: the run has 4 task families, fewer than 10. Intervals marked * are degenerate (every family has the same rate or difference).

| Condition | False acceptance [95% bootstrap] | False rejection [95% bootstrap] |
| --- | --- | --- |
| initial_plain | 0.83 (24/29) [0.44, 1.00] | 0.26 (13/50) [0.00, 0.75] |
| initial_audited | 0.83 (24/29) [0.44, 1.00] | 0.26 (13/50) [0.00, 0.75] |
| full_plain | 0.07 (2/29) [0.00, 0.38] | 0.00 (0/50) [0.00, 0.00]* |
| full_audited | 0.07 (2/29) [0.00, 0.38] | 0.12 (6/50) [0.00, 0.37] |
| llm_freeform | 0.07 (2/29) [0.00, 0.38] | 0.04 (2/50) [0.00, 0.12] |
| repo_tests | 0.00 (0/29) [0.00, 0.00]* | 0.68 (34/50) [0.21, 0.94] |

| A | B | Metric | A - B | 95% bootstrap | Families |
| --- | --- | --- | --- | --- | --- |
| initial_plain | full_plain | FA | +0.76 | [+0.22, +1.00] | 4 |
| initial_plain | full_plain | FR | +0.26 | [+0.00, +0.75] | 4 |
| initial_audited | full_audited | FA | +0.76 | [+0.22, +1.00] | 4 |
| initial_audited | full_audited | FR | +0.14 | [-0.16, +0.64] | 4 |
| initial_plain | initial_audited | FA | +0.00 | [+0.00, +0.00]* | 4 |
| initial_plain | initial_audited | FR | +0.00 | [+0.00, +0.00]* | 4 |
| full_plain | full_audited | FA | +0.00 | [+0.00, +0.00]* | 4 |
| full_plain | full_audited | FR | -0.12 | [-0.37, +0.00] | 4 |
| llm_freeform | full_audited | FA | +0.00 | [+0.00, +0.00]* | 4 |
| llm_freeform | full_audited | FR | -0.08 | [-0.24, +0.00] | 4 |
| llm_freeform | full_plain | FA | +0.00 | [+0.00, +0.00]* | 4 |
| llm_freeform | full_plain | FR | +0.04 | [+0.00, +0.12] | 4 |
| repo_tests | full_audited | FA | -0.07 | [-0.38, +0.00] | 4 |
| repo_tests | full_audited | FR | +0.56 | [+0.13, +0.93] | 4 |

By candidate stratum, fresh-v1 (4 families; not inferential):

| Condition | False acceptance [95% bootstrap] | False rejection [95% bootstrap] |
| --- | --- | --- |
| initial_plain | 0.83 (24/29) [0.44, 1.00] | 0.26 (13/50) [0.00, 0.75] |
| initial_audited | 0.83 (24/29) [0.44, 1.00] | 0.26 (13/50) [0.00, 0.75] |
| full_plain | 0.07 (2/29) [0.00, 0.38] | 0.00 (0/50) [0.00, 0.00]* |
| full_audited | 0.07 (2/29) [0.00, 0.38] | 0.12 (6/50) [0.00, 0.37] |
| llm_freeform | 0.07 (2/29) [0.00, 0.38] | 0.04 (2/50) [0.00, 0.12] |
| repo_tests | 0.00 (0/29) [0.00, 0.00]* | 0.68 (34/50) [0.21, 0.94] |

