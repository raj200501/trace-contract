# Analysis (proposed labels allowed (automated pilot))

> **Exploratory case studies** (protocol §19.6, §20.3): the run grades 6 accepted task(s) of its own (its families accepted, S11, in the committed index), fewer than 10; each run is reported on its own (protocol §20.3). Every table below is per task family: no pooled rate, interval or p-value is reported, and the tasks are exploratory case studies.

The run's 6 families are the 6 accepted families (S11) of its sample(s), first, in the committed index (data/manifests/natural_tasks_index.json at the run's code revision e9c9c91450c0), which counts 6 over both samples (first 6); each run grades the accepted families of its sample (protocol §20.2).

Tasks: 6 | independent task families: 6 | results: 432

> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth.

Population: natural:pr-review: NP-03, NP-04, NP-05, NP-18, NP-19, NP-20.

## Primary display: false acceptance and false rejection per task family

(numerator/denominator) per task family under D19, each distinct graded patch once; the reference solution and the no-op are excluded (see the sanity checks), and so is the secondary condition (diff_derived). No column pools the families (case-study mode, §19.6).

| Condition | NP-03 FA | NP-03 FR | NP-04 FA | NP-04 FR | NP-05 FA | NP-05 FR | NP-18 FA | NP-18 FR | NP-19 FA | NP-19 FR | NP-20 FA | NP-20 FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0/3 | 2/2 | 3/4 | 0/1 | 0/3 | 2/2 | 0/4 | 2/2 | 2/4 | 0/2 | 0/3 | 2/2 |
| initial_audited | 1/3 | 2/2 | 3/4 | 0/1 | 1/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 1/3 | 0/2 |
| full_plain | 0/3 | 2/2 | 2/4 | 0/1 | 0/3 | 2/2 | 0/4 | 2/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| full_audited | 0/3 | 2/2 | 2/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| llm_freeform | 0/3 | 0/2 | 1/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| repo_tests | 3/3 | 0/2 | 3/4 | 0/1 | 3/3 | 0/2 | 1/4 | 0/2 | 4/4 | 0/2 | 3/3 | 0/2 |

## Secondary condition: B3 (diff-derived)

B3 (diff_derived) is a secondary arm of the natural PR-review arm (protocol §15.6): its rates, per-family table and paired comparisons are reported here, apart from the primary conditions, and its comparisons stay out of the primary null tally.

(numerator/denominator) per task family, each distinct graded patch once; the reference solution and the no-op are excluded.

| Condition | NP-03 FA | NP-03 FR | NP-04 FA | NP-04 FR | NP-05 FA | NP-05 FR | NP-18 FA | NP-18 FR | NP-19 FA | NP-19 FR | NP-20 FA | NP-20 FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diff_derived | 1/3 | 0/2 | 4/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 2/4 | 0/2 | 1/3 | 0/2 |

## Source-evidence labels (reported apart from D19)

> **Source evidence, not a human label: the reviewer's request, the addressing commit and the agreement of both S9 judges label each pre-review state invalid with respect to the correction (protocol §15.6).**

Labeler kind source_evidence: the reviewer's request, the addressing commit and the S9 agreement; reported apart from D19 and never a human label (protocol §15.6).

Pre-review states accepted, per task family and condition (invalid by source evidence; accepted is a false acceptance under this labeling):

| Condition | NP-03 | NP-04 | NP-05 | NP-18 | NP-19 | NP-20 |
| --- | --- | --- | --- | --- | --- | --- |
| initial_plain | rejected | rejected | rejected | rejected | rejected | rejected |
| initial_audited | rejected | rejected | rejected | rejected | rejected | rejected |
| full_plain | rejected | rejected | rejected | rejected | rejected | rejected |
| full_audited | rejected | rejected | rejected | rejected | rejected | rejected |
| llm_freeform | rejected | rejected | rejected | rejected | rejected | rejected |
| repo_tests | accepted | rejected | accepted | rejected | accepted | accepted |
| diff_derived (secondary) | rejected | accepted | rejected | rejected | rejected | rejected |

| Family | Candidate | Source evidence | D19 | Independent labeler (outcome) | Reference checks in the run | Correction requirements |
| --- | --- | --- | --- | --- | --- | --- |
| NP-03 | NP-03-pre-review | invalid | invalid | left out (labeler not usable) | task_failure | R8, R9 |
| NP-04 | NP-04-pre-review | invalid | invalid | invalid (task_failure) | task_failure | R4, R5 |
| NP-05 | NP-05-pre-review | invalid | invalid | invalid (task_failure) | task_failure | R7, R8 |
| NP-18 | NP-18-pre-review | invalid | invalid | invalid (task_failure) | task_failure | R2, R3 |
| NP-19 | NP-19-pre-review | invalid | invalid | left out (labeler not usable) | task_failure | R3, R4 |
| NP-20 | NP-20-pre-review | invalid | invalid | invalid (task_failure) | task_failure | R4, R5, R6, R11, R13 |

## Independent labeler: a second labeling, per task family (protocol §15.4, §15.5)

The independent labeler (verifier independent_label, condition reference_check; protocol §15.5) labels a candidate valid if it passes, invalid if it fails with task_failure, and ambiguous on any other outcome (unresolved, environment failure, verifier error or timeout, recorded as such); a candidate it did not grade is unlabeled. Its verdicts are a second labeling (§15.4): a model proposal, as D19 is, never a human label. The labeler is label support, never an evaluated condition.

A pass on a natural pre-review state (origin natural_pre_review) is ambiguous, as D19's natural rule makes it: the correction is not observable by the checks (D64); the pre-review states existed before the labeler was written, so the agreement on them is marked as such (§15.5); a task whose labeler the run graded and whose verifiers/independent_label/status.json does not record the status usable is left out of the second labeling and reported.

Graded on NP-04, NP-05, NP-18, NP-20. The labeler passes on (sanity): NP-04 noop 0/1; NP-04 reference 1/1; NP-05 noop 0/1; NP-05 reference 1/1; NP-18 noop 0/1; NP-18 reference 1/1; NP-20 noop 0/1; NP-20 reference 1/1.

Left out of the second labeling (2; their labeler is not usable, protocol §15.5):

* NP-03: verifiers/independent_label/status.json records the status 'unusable', not 'usable' (protocol §15.5) (the run's outcomes of its labeler: noop task_failure 1; reference task_failure 1)
* NP-19: verifiers/independent_label/status.json records the status 'unusable', not 'usable' (protocol §15.5) (the run's outcomes of its labeler: noop task_failure 1; reference task_failure 1)

| Family | valid | invalid | ambiguous | not graded |
| --- | --- | --- | --- | --- |
| NP-03 | 0 | 0 | 0 | 6 |
| NP-04 | 2 | 4 | 0 | 0 |
| NP-05 | 3 | 3 | 0 | 0 |
| NP-18 | 2 | 4 | 0 | 0 |
| NP-19 | 0 | 0 | 0 | 6 |
| NP-20 | 3 | 3 | 0 | 0 |

### False acceptance and false rejection per family under each labeling

(numerator/denominator), counted as the primary analysis counts them; primary: D19's proposals, or a human label where one exists (the label rule of the primary analysis); independent: the labeler's verdicts. No column pools the families.

| Condition | Labeling | NP-03 FA | NP-03 FR | NP-04 FA | NP-04 FR | NP-05 FA | NP-05 FR | NP-18 FA | NP-18 FR | NP-19 FA | NP-19 FR | NP-20 FA | NP-20 FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | primary | 0/3 | 2/2 | 3/4 | 0/1 | 0/3 | 2/2 | 0/4 | 2/2 | 2/4 | 0/2 | 0/3 | 2/2 |
| initial_plain | independent | 0/0 | 0/0 | 3/4 | 1/2 | 0/3 | 3/3 | 0/4 | 2/2 | 0/0 | 0/0 | 0/3 | 3/3 |
| initial_audited | primary | 1/3 | 2/2 | 3/4 | 0/1 | 1/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 1/3 | 0/2 |
| initial_audited | independent | 0/0 | 0/0 | 3/4 | 1/2 | 1/3 | 0/3 | 0/4 | 0/2 | 0/0 | 0/0 | 1/3 | 0/3 |
| full_plain | primary | 0/3 | 2/2 | 2/4 | 0/1 | 0/3 | 2/2 | 0/4 | 2/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| full_plain | independent | 0/0 | 0/0 | 2/4 | 0/2 | 0/3 | 3/3 | 0/4 | 2/2 | 0/0 | 0/0 | 0/3 | 0/3 |
| full_audited | primary | 0/3 | 2/2 | 2/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| full_audited | independent | 0/0 | 0/0 | 2/4 | 0/2 | 0/3 | 0/3 | 0/4 | 0/2 | 0/0 | 0/0 | 0/3 | 0/3 |
| llm_freeform | primary | 0/3 | 0/2 | 1/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| llm_freeform | independent | 0/0 | 0/0 | 1/4 | 0/2 | 0/3 | 1/3 | 0/4 | 0/2 | 0/0 | 0/0 | 0/3 | 0/3 |
| repo_tests | primary | 3/3 | 0/2 | 3/4 | 0/1 | 3/3 | 0/2 | 1/4 | 0/2 | 4/4 | 0/2 | 3/3 | 0/2 |
| repo_tests | independent | 0/0 | 0/0 | 3/4 | 1/2 | 3/3 | 0/3 | 1/4 | 0/2 | 0/0 | 0/0 | 3/3 | 0/3 |
| diff_derived (secondary) | primary | 1/3 | 0/2 | 4/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 2/4 | 0/2 | 1/3 | 0/2 |
| diff_derived (secondary) | independent | 0/0 | 0/0 | 4/4 | 0/2 | 0/3 | 1/3 | 0/4 | 0/2 | 0/0 | 0/0 | 1/3 | 0/3 |

### Agreement between D19 and the independent labeler, per family

D19's proposal (labeler builder:refcheck+regression+construction:v1) against the second labeling, each distinct graded patch once (a unit's label is its members' when they agree, else ambiguous); the 2x2 table holds the units both label valid or invalid, the cross-table every unit (none: no D19 proposal, or not graded by the labeler); per task family (case-study mode, §19.6: no pooled agreement) (§15.4 estimand 4, §15.5).

Each family's units are also given apart. Units holding a natural pre-review state: the tree the reviewer commented on, which has existed since S10 and so before the labeler was written, although no labeler writer could read it (protocol §15.5; D64). The other units: the held-out pool, which protocol §15.5 and §19.7 have generated after the labeler was frozen; the order is checked here, each member's generation start against its family's labeler's frozen_at.

**Family NP-03**: 6 unit(s); both decide 0: agree 0, disagree 0 (agreement n/a, Cohen's kappa n/a).

| D19 \ independent | valid | invalid |
| --- | --- | --- |
| valid | 0 | 0 |
| invalid | 0 | 0 |

Outside the 2x2 table (none: no D19 proposal, or not graded by the labeler): D19 valid, independent none: 2; D19 invalid, independent none: 3; D19 ambiguous, independent none: 1.

* Pre-review states, which existed before the labeler was written: 1 unit(s); both decide 0: agree 0, disagree 0 (agreement n/a).

* The held-out pool: 5 unit(s); both decide 0: agree 0, disagree 0 (agreement n/a). Generated after the labeler was frozen: 5 of 5 candidate(s).

**Family NP-04**: 6 unit(s); both decide 5: agree 5, disagree 0 (agreement 1.00, Cohen's kappa 1.00).

| D19 \ independent | valid | invalid |
| --- | --- | --- |
| valid | 1 | 0 |
| invalid | 0 | 4 |

Outside the 2x2 table (none: no D19 proposal, or not graded by the labeler): D19 ambiguous, independent valid: 1.

* Pre-review states, which existed before the labeler was written: 1 unit(s); both decide 1: agree 1, disagree 0 (agreement 1.00).

* The held-out pool: 5 unit(s); both decide 4: agree 4, disagree 0 (agreement 1.00). Generated after the labeler was frozen: 5 of 5 candidate(s).

**Family NP-05**: 6 unit(s); both decide 5: agree 5, disagree 0 (agreement 1.00, Cohen's kappa 1.00).

| D19 \ independent | valid | invalid |
| --- | --- | --- |
| valid | 2 | 0 |
| invalid | 0 | 3 |

Outside the 2x2 table (none: no D19 proposal, or not graded by the labeler): D19 ambiguous, independent valid: 1.

* Pre-review states, which existed before the labeler was written: 1 unit(s); both decide 1: agree 1, disagree 0 (agreement 1.00).

* The held-out pool: 5 unit(s); both decide 4: agree 4, disagree 0 (agreement 1.00). Generated after the labeler was frozen: 5 of 5 candidate(s).

**Family NP-18**: 6 unit(s); both decide 6: agree 6, disagree 0 (agreement 1.00, Cohen's kappa 1.00).

| D19 \ independent | valid | invalid |
| --- | --- | --- |
| valid | 2 | 0 |
| invalid | 0 | 4 |

Outside the 2x2 table (none: no D19 proposal, or not graded by the labeler): none.

* Pre-review states, which existed before the labeler was written: 1 unit(s); both decide 1: agree 1, disagree 0 (agreement 1.00).

* The held-out pool: 5 unit(s); both decide 5: agree 5, disagree 0 (agreement 1.00). Generated after the labeler was frozen: 5 of 5 candidate(s).

**Family NP-19**: 6 unit(s); both decide 0: agree 0, disagree 0 (agreement n/a, Cohen's kappa n/a).

| D19 \ independent | valid | invalid |
| --- | --- | --- |
| valid | 0 | 0 |
| invalid | 0 | 0 |

Outside the 2x2 table (none: no D19 proposal, or not graded by the labeler): D19 valid, independent none: 2; D19 invalid, independent none: 4.

* Pre-review states, which existed before the labeler was written: 1 unit(s); both decide 0: agree 0, disagree 0 (agreement n/a).

* The held-out pool: 5 unit(s); both decide 0: agree 0, disagree 0 (agreement n/a). Generated after the labeler was frozen: 5 of 5 candidate(s).

**Family NP-20**: 6 unit(s); both decide 5: agree 5, disagree 0 (agreement 1.00, Cohen's kappa 1.00).

| D19 \ independent | valid | invalid |
| --- | --- | --- |
| valid | 2 | 0 |
| invalid | 0 | 3 |

Outside the 2x2 table (none: no D19 proposal, or not graded by the labeler): D19 ambiguous, independent valid: 1.

* Pre-review states, which existed before the labeler was written: 1 unit(s); both decide 1: agree 1, disagree 0 (agreement 1.00).

* The held-out pool: 5 unit(s); both decide 4: agree 4, disagree 0 (agreement 1.00). Generated after the labeler was frozen: 5 of 5 candidate(s).

## Sanity checks per family (excluded from FA and FR)

Passes of the reference solution and of the no-op (the run's grading, numerator/denominator).

| Condition | NP-03 reference | NP-03 no-op | NP-04 reference | NP-04 no-op | NP-05 reference | NP-05 no-op | NP-18 reference | NP-18 no-op | NP-19 reference | NP-19 no-op | NP-20 reference | NP-20 no-op |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| initial_audited | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| full_plain | 0/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | 0/1 |
| full_audited | 0/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 | 1/1 | 0/1 |
| llm_freeform | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| repo_tests | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| diff_derived (secondary) | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 |

## Distinct graded patches

36 distinct graded patches among 36 held-out candidates: held-out candidates of a task with the same graded patch count once; the representative is the natural state, else the first id (protocol §15.4, §15.7).

## Oracle-gated view per family (secondary)

A verifier x task cell is dropped when the verifier does not pass the task's reference solution in the run's sanity grading; its held-out candidates are the lost yield (secondary view, protocol §15.7); per family only (case-study mode, §19.6).

| Condition | Cells kept | Dropped | Lost yield per family (invalid / valid) |
| --- | --- | --- | --- |
| initial_plain | 1/6 | NP-03: does not pass its reference (task_failure); NP-05: does not pass its reference (task_failure); NP-18: does not pass its reference (task_failure); NP-19: does not pass its reference (task_failure); NP-20: does not pass its reference (task_failure) | NP-03 3 / 2, NP-05 3 / 2, NP-18 4 / 2, NP-19 4 / 2, NP-20 3 / 2 |
| initial_audited | 6/6 | - | - |
| full_plain | 2/6 | NP-03: does not pass its reference (task_failure); NP-05: does not pass its reference (task_failure); NP-18: does not pass its reference (task_failure); NP-19: does not pass its reference (task_failure) | NP-03 3 / 2, NP-05 3 / 2, NP-18 4 / 2, NP-19 4 / 2 |
| full_audited | 4/6 | NP-03: does not pass its reference (task_failure); NP-19: does not pass its reference (task_failure) | NP-03 3 / 2, NP-19 4 / 2 |
| llm_freeform | 6/6 | - | - |
| repo_tests | 6/6 | - | - |
| diff_derived (secondary) | 6/6 | - | - |

False acceptance and false rejection on the cells kept:

| Condition | NP-03 FA | NP-03 FR | NP-04 FA | NP-04 FR | NP-05 FA | NP-05 FR | NP-18 FA | NP-18 FR | NP-19 FA | NP-19 FR | NP-20 FA | NP-20 FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | - | - | 3/4 | 0/1 | - | - | - | - | - | - | - | - |
| initial_audited | 1/3 | 2/2 | 3/4 | 0/1 | 1/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 1/3 | 0/2 |
| full_plain | - | - | 2/4 | 0/1 | - | - | - | - | - | - | 0/3 | 0/2 |
| full_audited | - | - | 2/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | - | - | 0/3 | 0/2 |
| llm_freeform | 0/3 | 0/2 | 1/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| repo_tests | 3/3 | 0/2 | 3/4 | 0/1 | 3/3 | 0/2 | 1/4 | 0/2 | 4/4 | 0/2 | 3/3 | 0/2 |
| diff_derived (secondary) | 1/3 | 0/2 | 4/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 2/4 | 0/2 | 1/3 | 0/2 |

## Accepted negatives by type, per family

| Condition | Family | correction-violating | initial-violating | unspecified |
| --- | --- | --- | --- | --- |
| initial_plain | NP-03 | 0/3 | - | - |
| initial_plain | NP-04 | 3/4 | - | - |
| initial_plain | NP-05 | 0/3 | - | - |
| initial_plain | NP-18 | 0/4 | - | - |
| initial_plain | NP-19 | 2/4 | - | - |
| initial_plain | NP-20 | 0/3 | - | - |
| initial_audited | NP-03 | 1/3 | - | - |
| initial_audited | NP-04 | 3/4 | - | - |
| initial_audited | NP-05 | 1/3 | - | - |
| initial_audited | NP-18 | 0/4 | - | - |
| initial_audited | NP-19 | 1/4 | - | - |
| initial_audited | NP-20 | 1/3 | - | - |
| full_plain | NP-03 | 0/3 | - | - |
| full_plain | NP-04 | 2/4 | - | - |
| full_plain | NP-05 | 0/3 | - | - |
| full_plain | NP-18 | 0/4 | - | - |
| full_plain | NP-19 | 1/4 | - | - |
| full_plain | NP-20 | 0/3 | - | - |
| full_audited | NP-03 | 0/3 | - | - |
| full_audited | NP-04 | 2/4 | - | - |
| full_audited | NP-05 | 0/3 | - | - |
| full_audited | NP-18 | 0/4 | - | - |
| full_audited | NP-19 | 1/4 | - | - |
| full_audited | NP-20 | 0/3 | - | - |
| llm_freeform | NP-03 | 0/3 | - | - |
| llm_freeform | NP-04 | 1/4 | - | - |
| llm_freeform | NP-05 | 0/3 | - | - |
| llm_freeform | NP-18 | 0/4 | - | - |
| llm_freeform | NP-19 | 1/4 | - | - |
| llm_freeform | NP-20 | 0/3 | - | - |
| repo_tests | NP-03 | 3/3 | - | - |
| repo_tests | NP-04 | 3/4 | - | - |
| repo_tests | NP-05 | 3/3 | - | - |
| repo_tests | NP-18 | 1/4 | - | - |
| repo_tests | NP-19 | 4/4 | - | - |
| repo_tests | NP-20 | 3/3 | - | - |
| diff_derived (secondary) | NP-03 | 1/3 | - | - |
| diff_derived (secondary) | NP-04 | 4/4 | - | - |
| diff_derived (secondary) | NP-05 | 0/3 | - | - |
| diff_derived (secondary) | NP-18 | 0/4 | - | - |
| diff_derived (secondary) | NP-19 | 2/4 | - | - |
| diff_derived (secondary) | NP-20 | 1/3 | - | - |

## Every held-out candidate (duplicates included, for comparison), per family

| Condition | NP-03 FA | NP-03 FR | NP-04 FA | NP-04 FR | NP-05 FA | NP-05 FR | NP-18 FA | NP-18 FR | NP-19 FA | NP-19 FR | NP-20 FA | NP-20 FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0/3 | 2/2 | 3/4 | 0/1 | 0/3 | 2/2 | 0/4 | 2/2 | 2/4 | 0/2 | 0/3 | 2/2 |
| initial_audited | 1/3 | 2/2 | 3/4 | 0/1 | 1/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 1/3 | 0/2 |
| full_plain | 0/3 | 2/2 | 2/4 | 0/1 | 0/3 | 2/2 | 0/4 | 2/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| full_audited | 0/3 | 2/2 | 2/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| llm_freeform | 0/3 | 0/2 | 1/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| repo_tests | 3/3 | 0/2 | 3/4 | 0/1 | 3/3 | 0/2 | 1/4 | 0/2 | 4/4 | 0/2 | 3/3 | 0/2 |
| diff_derived (secondary) | 1/3 | 0/2 | 4/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 2/4 | 0/2 | 1/3 | 0/2 |

## Exploratory sensitivity: construction-intent labels (not pre-specified), per family

| Condition | NP-03 FA | NP-03 FR | NP-04 FA | NP-04 FR | NP-05 FA | NP-05 FR | NP-18 FA | NP-18 FR | NP-19 FA | NP-19 FR | NP-20 FA | NP-20 FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0/4 | 2/2 | 3/4 | 1/2 | 0/4 | 2/2 | 0/4 | 2/2 | 2/4 | 0/2 | 0/4 | 2/2 |
| initial_audited | 2/4 | 2/2 | 3/4 | 1/2 | 2/4 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 2/4 | 0/2 |
| full_plain | 0/4 | 2/2 | 2/4 | 0/2 | 0/4 | 2/2 | 0/4 | 2/2 | 1/4 | 0/2 | 1/4 | 0/2 |
| full_audited | 0/4 | 2/2 | 2/4 | 0/2 | 1/4 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 1/4 | 0/2 |
| llm_freeform | 1/4 | 0/2 | 1/4 | 0/2 | 0/4 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 1/4 | 0/2 |
| repo_tests | 4/4 | 0/2 | 3/4 | 1/2 | 4/4 | 0/2 | 1/4 | 0/2 | 4/4 | 0/2 | 4/4 | 0/2 |
| diff_derived (secondary) | 2/4 | 0/2 | 4/4 | 0/2 | 0/4 | 0/2 | 0/4 | 0/2 | 2/4 | 0/2 | 2/4 | 0/2 |

## Post hoc: the independent construction checks' labels, per family

| Condition | NP-03 FA | NP-03 FR | NP-04 FA | NP-04 FR | NP-05 FA | NP-05 FR | NP-18 FA | NP-18 FR | NP-19 FA | NP-19 FR | NP-20 FA | NP-20 FR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0/3 | 2/2 | 3/4 | 0/1 | 0/3 | 2/2 | 0/4 | 2/2 | 2/4 | 0/2 | 0/3 | 2/2 |
| initial_audited | 1/3 | 2/2 | 3/4 | 0/1 | 1/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 1/3 | 0/2 |
| full_plain | 0/3 | 2/2 | 2/4 | 0/1 | 0/3 | 2/2 | 0/4 | 2/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| full_audited | 0/3 | 2/2 | 2/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| llm_freeform | 0/3 | 0/2 | 1/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 1/4 | 0/2 | 0/3 | 0/2 |
| repo_tests | 3/3 | 0/2 | 3/4 | 0/1 | 3/3 | 0/2 | 1/4 | 0/2 | 4/4 | 0/2 | 3/3 | 0/2 |
| diff_derived (secondary) | 1/3 | 0/2 | 4/4 | 0/1 | 0/3 | 0/2 | 0/4 | 0/2 | 2/4 | 0/2 | 1/3 | 0/2 |

## Post hoc: near misses accepted, by D19 status, per family

| Condition | Family | D19-confirmed invalid | D19 ambiguous |
| --- | --- | --- | --- |
| initial_plain | NP-03 | 0/2 | 0/1 |
| initial_plain | NP-04 | 3/3 | 0/0 |
| initial_plain | NP-05 | 0/2 | 0/1 |
| initial_plain | NP-18 | 0/3 | 0/0 |
| initial_plain | NP-19 | 2/3 | 0/0 |
| initial_plain | NP-20 | 0/2 | 0/1 |
| initial_audited | NP-03 | 1/2 | 1/1 |
| initial_audited | NP-04 | 3/3 | 0/0 |
| initial_audited | NP-05 | 1/2 | 1/1 |
| initial_audited | NP-18 | 0/3 | 0/0 |
| initial_audited | NP-19 | 1/3 | 0/0 |
| initial_audited | NP-20 | 1/2 | 1/1 |
| full_plain | NP-03 | 0/2 | 0/1 |
| full_plain | NP-04 | 2/3 | 0/0 |
| full_plain | NP-05 | 0/2 | 0/1 |
| full_plain | NP-18 | 0/3 | 0/0 |
| full_plain | NP-19 | 1/3 | 0/0 |
| full_plain | NP-20 | 0/2 | 1/1 |
| full_audited | NP-03 | 0/2 | 0/1 |
| full_audited | NP-04 | 2/3 | 0/0 |
| full_audited | NP-05 | 0/2 | 1/1 |
| full_audited | NP-18 | 0/3 | 0/0 |
| full_audited | NP-19 | 1/3 | 0/0 |
| full_audited | NP-20 | 0/2 | 1/1 |
| llm_freeform | NP-03 | 0/2 | 1/1 |
| llm_freeform | NP-04 | 1/3 | 0/0 |
| llm_freeform | NP-05 | 0/2 | 0/1 |
| llm_freeform | NP-18 | 0/3 | 0/0 |
| llm_freeform | NP-19 | 1/3 | 0/0 |
| llm_freeform | NP-20 | 0/2 | 1/1 |
| repo_tests | NP-03 | 2/2 | 1/1 |
| repo_tests | NP-04 | 3/3 | 0/0 |
| repo_tests | NP-05 | 2/2 | 1/1 |
| repo_tests | NP-18 | 1/3 | 0/0 |
| repo_tests | NP-19 | 3/3 | 0/0 |
| repo_tests | NP-20 | 2/2 | 1/1 |
| diff_derived (secondary) | NP-03 | 1/2 | 1/1 |
| diff_derived (secondary) | NP-04 | 3/3 | 0/0 |
| diff_derived (secondary) | NP-05 | 0/2 | 0/1 |
| diff_derived (secondary) | NP-18 | 0/3 | 0/0 |
| diff_derived (secondary) | NP-19 | 2/3 | 0/0 |
| diff_derived (secondary) | NP-20 | 1/2 | 1/1 |

## Natural families: sample, B1 and correction requirements

Natural PR-review arm (protocol §15.6, §17, §19): per family, its sample, whether B1 is available (s10.json) and whether its overlay equals D19's regression norm (labels/base_tests_overlay, by file), the correction requirements (the reference contract's scored active requirements introduced at the review comment or one of the reviewer's replies; D64, decision 14), the held-out near misses that name one in their construction label, and its construction facts (contract counts, checks per verifier, the audits of C2 and C4, whether B3 is available, the reference checks' status record; construction_rule); the funnel S1 to S11 of both samples with reasons; build and replay reliability; and cost and time per accepted task. Ids, outcomes, counts and hashes only.

| Family | Sample | S11 | Session | B1 available (S10) | B1 graded | B1 = D19 regression norm | B3 graded | Labeler | Correction requirements | Near misses on the correction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-03 | first | yes | readable | yes | yes | yes (14 of 14 B1 files identical; norm 14 files) | yes | not usable (unusable), round 2 | R8, R9 | 2 of 3 (NP-03-eval-nm-1, NP-03-eval-nm-2) |
| NP-04 | first | yes | readable | yes | yes | no (0 of 1 B1 files identical; norm 1 files) | yes | usable, round 1 | R4, R5 | 2 of 3 (NP-04-eval-nm-1, NP-04-eval-nm-2) |
| NP-05 | first | yes | readable | yes | yes | yes (16 of 16 B1 files identical; norm 16 files) | yes | usable, round 2 | R7, R8 | 2 of 3 (NP-05-eval-nm-1, NP-05-eval-nm-2) |
| NP-18 | first | yes | readable | yes | yes | no (0 of 1 B1 files identical; norm 1 files) | yes | usable, round 1 | R2, R3 | 2 of 3 (NP-18-eval-nm-1, NP-18-eval-nm-2) |
| NP-19 | first | yes | readable | yes | yes | no (1 of 2 B1 files identical; norm 2 files) | yes | not usable (unusable), round 2 | R3, R4 (unscored at a correction event, not counted: R5) | 2 of 3 (NP-19-eval-nm-1, NP-19-eval-nm-2) |
| NP-20 | first | yes | readable | yes | yes | yes (3 of 3 B1 files identical; norm 3 files) | yes | usable, round 2 | R4, R5, R6, R11, R13 | 2 of 3 (NP-20-eval-nm-1, NP-20-eval-nm-2) |

### Construction facts per family

Per family, from its task directory (D64; the counts of D70): each contract's requirements, active ones and scored active ones (the reference contract's also at the correction: its correction requirements); the checks of each registered verifier, by condition (the label-support verifiers by id); the audit of C2 and C4 from each spec's audit record (whether it passed, its revisions, the finding codes of its last iteration; never a finding's message); whether B3 is available (a registered B3 spec, else why not); and the reference checks' status record (verifiers/reference_check/status.json: whether a readable record exists, its status, usable or unusable, and its fix rounds, an integer fix_rounds; usable is null without a readable record holding one of the two statuses, fix_rounds is null without that integer, and why says which). Ids, counts and codes only.

| Family | Reference contract: requirements, scored active, at the correction | Recovered contracts, scored active: initial-only, full-session | Checks: C1, C2, C3, C4, B2, B1, B3 | Checks: reference checks, labeler | C2 audit | C4 audit | B3 | Reference checks' status record |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-03 | 9, 7, 2 | 4, 6 | 11, 14, 14, 15, 14, 954, 11 | 19, 17 | 2 revision(s), passed | 3 revision(s), failed (reference_not_passing) | available | usable; fix rounds 0 |
| NP-04 | 5, 4, 2 | 3, 3 | 11, 12, 14, 14, 11, 34, 14 | 18, 9 | 3 revision(s), failed (false_rejection_dev) | 0 revision(s), passed | available | usable; fix rounds 0 |
| NP-05 | 13, 10, 2 | 10, 11 | 14, 14, 14, 15, 12, 354, 14 | 18, 17 | 3 revision(s), failed (false_acceptance_dev) | 3 revision(s), failed (false_acceptance_dev) | available | usable; fix rounds 2 |
| NP-18 | 5, 4, 2 | 5, 3 | 12, 12, 11, 12, 12, 26, 13 | 14, 10 | 1 revision(s), passed | 1 revision(s), passed | available | usable; fix rounds 0 |
| NP-19 | 5, 4, 2 | 4, 3 | 10, 13, 11, 15, 13, 1, 8 | 10, 7 | 2 revision(s), passed | 3 revision(s), failed (reference_not_passing) | available | usable; fix rounds 1 |
| NP-20 | 16, 12, 5 | 3, 5 | 12, 13, 13, 13, 12, 48, 11 | 20, 20 | 1 revision(s), passed | 0 revision(s), passed | available | usable; fix rounds 0 |

## Funnel S1 to S11, both samples

S1 to S8a: the deterministic screen (D48); S9: the model judges per sample (§15.6, §19.2); S10: replayability per sample, with each rejection's reason (§15.6, §17); S11: accepted, that is passing S10 within the family cap (§16.4); counts only, from the records named.

| Stage | Unit | Count | PRs | Repositories |
| --- | --- | --- | --- | --- |
| S1 | pull_request | 361296 | 361296 | 25402 |
| S2 | pull_request | 44914 | 44914 | 3333 |
| S3 | review_comment | 28732 | 5030 | 757 |
| S4 | review_comment | 6751 | 2070 | 427 |
| S5 | review_comment | 3895 | 1241 | 306 |
| S6 | review_comment | 3540 | 1085 | 268 |
| S7 | review_comment | 3126 | 987 | 246 |
| S8 | review_comment | 926 | 255 | 92 |
| S8a | review_comment | 684 | 190 | 63 |

| S9 sample | Comments | Judged | Qualifying | Excluded (judges disagree) | Failed | Qualifying PRs | Qualifying repositories | Families |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| first | 150 | - | 31 | 2 | 117 | 25 | 14 | 20 |
| extension | 534 | 405 | 91 | 10 | 433 | 42 | 19 | 19 |

| S10 sample | Index rows | Roles | S10 outcomes | S11 (accepted) |
| --- | --- | --- | --- | --- |
| first | 25 | family 20, reserve 5 | not built 3, passed 6, rejected 16 | 6: NP-03, NP-04, NP-05, NP-18, NP-19, NP-20 |
| extension | 23 | family 19, reserve 4 | not built 23 | 0: none |

S11: 6 accepted task(s) over both samples (first 6, extension 0).

Reasons:

* S9, first: addressing commit not agent attributed 0; commits not fetchable 19; not addressed 6; not behaviour change or defect 92; not testable offline 0
* S9, extension: addressing commit not agent attributed 1; commits not fetchable 56; fetch over the caps 59; no later commit changes the commented file 14; not addressed 23; not behaviour change or defect 278; not testable offline 2
* S10, first, a merge between the base and the addressing commit changes the commented file (§15.6) (1): NP-12
* S10, first, base tests fail to collect (8): NP-01, NP-02, NP-06, NP-09, NP-11, NP-14, NP-21, NP-22
* S10, first, base tests: the base-test subset is empty (1): NP-07
* S10, first, environment too large (1): NP-15
* S10, first, fetch over the caps (§15.6) (1): NP-08
* S10, first, no resolvable closure (4): NP-10, NP-13, NP-16, NP-17

## Build and replay reliability

Per family: the S10 record, the reconstruction record, the task image's id as the run, snapshot.json and s10.json record it, the run's grading of the reference and the no-op by every verifier (label support included), and the pairs whose three repeats disagree (unresolved, counted as a rejection, §15.3) or that ended in an infrastructure outcome (environment failure, verifier error or timeout; an unresolved pair is counted as unresolved only).

| Family | S10 | Base tests: passed / failed / error / skipped | Reconstruction | Image id: run = snapshot = S10 | Reference passes (every verifier) | No-op passes | Pairs | Unresolved | Infrastructure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-03 | passed | 954 / 10 / 0 / 2 | passed (approximate) | yes | 5/9 | 1/9 | 72 | 0 | none |
| NP-04 | passed | 33 / 0 / 0 / 0 | passed (exact) | yes | 9/9 | 0/9 | 72 | 0 | none |
| NP-05 | passed | 354 / 5 / 0 / 0 | passed (exact) | yes | 7/9 | 1/9 | 72 | 0 | none |
| NP-18 | passed | 24 / 0 / 0 / 0 | passed (exact) | yes | 7/9 | 0/9 | 72 | 0 | none |
| NP-19 | passed | 1 / 5 / 3 / 0 | passed (exact) | yes | 5/9 | 1/9 | 72 | 0 | none |
| NP-20 | passed | 48 / 0 / 0 / 0 | passed (exact) | yes | 8/9 | 1/9 | 72 | 0 | none |

The run: 432 pairs; 0 unresolved (repeats that disagree, counted as rejections, protocol §15.3); infrastructure outcomes: none.

## Cost and time per accepted task

Per family: the generation records of its generated artifacts (contracts, verifiers other than B1, constructed candidates; a combined record sums its runs), its S10 record's time from built_at to passed_at and its base-test run, the S10 fetch log's bytes of the family's repository (a repository's fetches include those made for any family of it) and the run's grading time (the sum of each pair's wall time); the totals over the run's families, and each total divided by their number (per accepted task, when the run grades every accepted family of its sample: see the index check); a total is n/a when a family lacks the value. S10's cost per accepted task counts its time and its fetches on one basis, the S10 work of every family S10 processed, both samples, rejected families included (s10_every_family: the time from built_at to passed_at or rejected_at; every S10 fetch in the log, its bytes and seconds), divided by the same number; the run's families' own S10 time (s10_seconds_run_families) and their repositories' fetches are given beside it.

| Family | Generated artifacts with a record | Turns | Tool calls | Agent wall time (s) | Tokens | Grading wall time (s) | S10 (s) | S10 fetch bytes of its repository | Without a record |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-03 | 26/26 | 1085 | 1391 | 34948.5 | n/a | 1111.2 | 24.0 | 1912745 | none |
| NP-04 | 26/26 | 741 | 940 | 24987.7 | n/a | 421.5 | 7.0 | 298186 (shared with NP-05) | none |
| NP-05 | 26/26 | 967 | 1185 | 31105.7 | n/a | 871.2 | 38.0 | 298186 (shared with NP-04) | none |
| NP-18 | 26/26 | 712 | 837 | 23735.4 | n/a | 5732.6 | 199.0 | 16262066 | none |
| NP-19 | 26/26 | 1247 | 1532 | 55541.3 | n/a | 6146.5 | 113.0 | 1719619 | none |
| NP-20 | 26/26 | 934 | 1183 | 24110.6 | n/a | 1310.4 | 67.0 | 478162 | none |
| All 6 families | - | 5686 | 7068 | 194429.2 | n/a | 15593.4 | 448.0 | 20670778 | - |
| Per accepted task | - | 947.7 | 1178.0 | 32404.9 | n/a | 2598.9 | see S10 below | see S10 below | - |

S10 per accepted task, its time and its fetches counted on one basis: the S10 work of every family S10 processed, both samples, rejected families included, divided by the run's families. The run's families alone are given below it.

| S10 work | Families | Build time (s) | Fetches (s) | Fetch bytes | Build time per accepted task (s) | Fetches per accepted task (s) | Fetch bytes per accepted task |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Every family S10 processed | 32 processed; a recorded time for 28 of them | 7437.0 | 155.8 | 702174525 | 1239.5 | 26.0 | 117029087.5 |
| The run's families alone (their repositories' fetches) | 6 | 448.0 | - | 20670778 | 74.7 | - | 3445129.7 |

Counted, with an S10 record under the tasks root but no S10 outcome in the committed index: NP-26, NP-27, NP-28, NP-29, NP-30, NP-31, NP-32, NP-33, NP-34, NP-35.

Not built by S10, so with no S10 work: NP-23, NP-24, NP-25, NP-36, NP-37, NP-38, NP-39, NP-40, NP-41, NP-42, NP-43, NP-44, NP-45, NP-46, NP-47, NP-48.

Not recorded, so not counted:

* stages S1 to S9: the funnel queries, the S9 fetches and the S9 judges' agent runs (their records are kept outside the repository)
* S10 re-runs after compiler fixes (D59): s10.json keeps the times of the last build only, while the fetch log keeps every fetch
* the S10 compile step's time before built_at (resolving the commits, materialising the base and the candidates), apart from its fetches, whose seconds the log records: s10.json records no start of it
* image builds and wheel downloads, apart from the wheelhouse bytes that s10.json records
* the host's own steps (D24): workspaces, builds, audits, freezing and labelling, apart from the run's grading time
* agent runs that leave no generation record: the mappers, the optional construction checkers and any run before a re-run
* the S10 time of NP-07, NP-08, NP-12, left out of the S10 time of every processed family: rejected during the build: its task directory keeps only rejection.json, which records the rejection's time and no start
* the S10 time of NP-35, left out of the S10 time of every processed family: its s10.json records no end (outcome 'built')
* the time of 1 S10 fetch(es) of the log, which record no seconds (their bytes are counted)

## Labels and human-review queue

| Task | valid | invalid | ambiguous | unlabeled | queued for review |
| --- | --- | --- | --- | --- | --- |
| NP-03 | 2 | 3 | 1 | 0 | NP-03-eval-nm-1 |
| NP-04 | 1 | 4 | 1 | 0 | NP-04-eval-alt-2 |
| NP-05 | 2 | 3 | 1 | 0 | NP-05-eval-nm-3 |
| NP-18 | 2 | 4 | 0 | 0 | - |
| NP-19 | 2 | 4 | 0 | 0 | - |
| NP-20 | 2 | 3 | 1 | 0 | NP-20-eval-nm-3 |

D19's proposals per task (valid, invalid, ambiguous, unlabeled), with the reason category of each candidate D19 labels ambiguous (natural.d19_rule):

* NP-03: 2, 3, 1, 0; ambiguous: NP-03-eval-nm-1 (construction invalid but reference checks and regression norm pass)
* NP-04: 1, 4, 1, 0; ambiguous: NP-04-eval-alt-2 (construction valid but checks fail)
* NP-05: 2, 3, 1, 0; ambiguous: NP-05-eval-nm-3 (construction invalid but failing checks map to other requirements)
* NP-18: 2, 4, 0, 0; ambiguous: none
* NP-19: 2, 4, 0, 0; ambiguous: none
* NP-20: 2, 3, 1, 0; ambiguous: NP-20-eval-nm-3 (construction invalid but reference checks and regression norm pass)

## Contract recovery (model mappings, proposals)

| Task | Variant | Coverage of active reference requirements (mapper 1) | Covered but contradicted | Unsupported | Contradicting | Coverage (mapper 2) | Mapping agreement (kappa) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NP-03 | initial_only | 0.29 (2/7) | - | 0/4 | 0 | 0.29 (2/7) | 1.00 |
| NP-03 | full_session | 0.71 (5/7) | - | 0/6 | 0 | 0.71 (5/7) | 0.92 |
| NP-04 | initial_only | 0.50 (2/4) | - | 1/3 | 0 | 0.50 (2/4) | 1.00 |
| NP-04 | full_session | 0.75 (3/4) | - | 0/3 | 0 | 0.75 (3/4) | 1.00 |
| NP-05 | initial_only | 0.80 (8/10) | - | 1/10 | 2 | 0.80 (8/10) | 1.00 |
| NP-05 | full_session | 0.70 (7/10) | - | 1/11 | 3 | 0.70 (7/10) | 1.00 |
| NP-18 | initial_only | 1.00 (4/4) | - | 1/5 | 0 | 1.00 (4/4) | 1.00 |
| NP-18 | full_session | 0.75 (3/4) | - | 1/3 | 0 | 0.75 (3/4) | 1.00 |
| NP-19 | initial_only | 0.50 (2/4) | - | 0/4 | 0 | 0.50 (2/4) | 1.00 |
| NP-19 | full_session | 0.75 (3/4) | - | 0/3 | 0 | 0.75 (3/4) | 1.00 |
| NP-20 | initial_only | 0.33 (4/12) | R4 | 0/3 | 1 | 0.25 (3/12) | 0.90 |
| NP-20 | full_session | 0.50 (6/12) | - | 0/5 | 1 | 0.50 (6/12) | 1.00 |

## Per-task outcomes

### NP-03

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests | diff_derived |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-03-eval-alt-1 | valid_alternative | valid | - | task_failure | task_failure | task_failure | task_failure | pass | pass | pass |
| NP-03-eval-alt-2 | valid_alternative | valid | - | task_failure | task_failure | task_failure | task_failure | pass | pass | pass |
| NP-03-eval-nm-1 | constructed_near_miss | ambiguous | - | task_failure | pass | task_failure | task_failure | pass | pass | pass |
| NP-03-eval-nm-2 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | pass |
| NP-03-eval-nm-3 | constructed_near_miss | invalid | correction_violating | task_failure | pass | task_failure | task_failure | task_failure | pass | task_failure |
| NP-03-pre-review | natural_pre_review | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | task_failure |

### NP-04

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests | diff_derived |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-04-eval-alt-1 | valid_alternative | valid | - | pass | pass | pass | pass | pass | pass | pass |
| NP-04-eval-alt-2 | valid_alternative | ambiguous | - | task_failure | task_failure | pass | pass | pass | task_failure | pass |
| NP-04-eval-nm-1 | constructed_near_miss | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | pass | pass |
| NP-04-eval-nm-2 | constructed_near_miss | invalid | correction_violating | pass | pass | pass | pass | task_failure | pass | pass |
| NP-04-eval-nm-3 | constructed_near_miss | invalid | correction_violating | pass | pass | pass | pass | pass | pass | pass |
| NP-04-pre-review | natural_pre_review | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure | pass |

### NP-05

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests | diff_derived |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-05-eval-alt-1 | valid_alternative | valid | - | task_failure | pass | task_failure | pass | pass | pass | pass |
| NP-05-eval-alt-2 | valid_alternative | valid | - | task_failure | pass | task_failure | pass | pass | pass | pass |
| NP-05-eval-nm-1 | constructed_near_miss | invalid | correction_violating | task_failure | pass | task_failure | task_failure | task_failure | pass | task_failure |
| NP-05-eval-nm-2 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | task_failure |
| NP-05-eval-nm-3 | constructed_near_miss | ambiguous | - | task_failure | pass | task_failure | pass | task_failure | pass | task_failure |
| NP-05-pre-review | natural_pre_review | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | task_failure |

### NP-18

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests | diff_derived |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-18-eval-alt-1 | valid_alternative | valid | - | task_failure | pass | task_failure | pass | pass | pass | pass |
| NP-18-eval-alt-2 | valid_alternative | valid | - | task_failure | pass | task_failure | pass | pass | pass | pass |
| NP-18-eval-nm-1 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| NP-18-eval-nm-2 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| NP-18-eval-nm-3 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | task_failure |
| NP-18-pre-review | natural_pre_review | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |

### NP-19

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests | diff_derived |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-19-eval-alt-1 | valid_alternative | valid | - | pass | pass | pass | pass | pass | pass | pass |
| NP-19-eval-alt-2 | valid_alternative | valid | - | pass | pass | pass | pass | pass | pass | pass |
| NP-19-eval-nm-1 | constructed_near_miss | invalid | correction_violating | pass | task_failure | pass | pass | pass | pass | pass |
| NP-19-eval-nm-2 | constructed_near_miss | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | pass | pass |
| NP-19-eval-nm-3 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | task_failure |
| NP-19-pre-review | natural_pre_review | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | task_failure |

### NP-20

| Candidate | Origin | Label | Negative type | initial_plain | initial_audited | full_plain | full_audited | llm_freeform | repo_tests | diff_derived |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NP-20-eval-alt-1 | valid_alternative | valid | - | task_failure | pass | pass | pass | pass | pass | pass |
| NP-20-eval-alt-2 | valid_alternative | valid | - | task_failure | pass | pass | pass | pass | pass | pass |
| NP-20-eval-nm-1 | constructed_near_miss | invalid | correction_violating | task_failure | pass | task_failure | task_failure | task_failure | pass | pass |
| NP-20-eval-nm-2 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | task_failure |
| NP-20-eval-nm-3 | constructed_near_miss | ambiguous | - | task_failure | pass | pass | pass | pass | pass | pass |
| NP-20-pre-review | natural_pre_review | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | pass | task_failure |

