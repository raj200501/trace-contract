# Analysis (proposed labels allowed (automated pilot))

Tasks: 4 | independent task families: 4 | results: 240

> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth. With this few task families the intervals are not meaningful evidence of an effect.

## False acceptance / false rejection by condition

Rates with (numerator/denominator) and 95% cluster-bootstrap interval over task families where computable. Reference solution and no-op are excluded (see sanity table).

Intervals marked * are degenerate (every family has the same rate, so resampling families cannot vary them); the exact (Clopper-Pearson) interval ignores clustering and is given only as a reference scale.

| Condition | False acceptance | FA exact 95% | FA macro | False rejection | FR exact 95% | FR macro | Youden's J | Tasks with an accepted negative | Infra outcomes | Excluded (unlabeled/ambiguous) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0.35 (6/17) [0.07, 0.71] | [0.14, 0.62] | 0.37 | 0.20 (2/10) [0.00, 0.67] | [0.03, 0.56] | 0.25 | +0.45 | 3/4 | 0/32 | 5 |
| initial_audited | 0.29 (5/17) [0.00, 0.63] | [0.10, 0.56] | 0.24 | 0.20 (2/10) [0.00, 0.67] | [0.03, 0.56] | 0.25 | +0.51 | 2/4 | 0/32 | 5 |
| full_plain | 0.00 (0/17) [0.00, 0.00]* | [0.00, 0.20] | 0.00 | 0.00 (0/10) [0.00, 0.00]* | [0.00, 0.31] | 0.00 | +1.00 | 0/4 | 0/32 | 5 |
| full_audited | 0.00 (0/17) [0.00, 0.00]* | [0.00, 0.20] | 0.00 | 0.00 (0/10) [0.00, 0.00]* | [0.00, 0.31] | 0.00 | +1.00 | 0/4 | 0/32 | 5 |
| llm_freeform | 0.06 (1/17) [0.00, 0.14] | [0.00, 0.29] | 0.04 | 0.00 (0/10) [0.00, 0.00]* | [0.00, 0.31] | 0.00 | +0.94 | 1/4 | 0/32 | 5 |
| repo_tests | 0.29 (5/17) [0.11, 0.64] | [0.10, 0.56] | 0.38 | 0.40 (4/10) [0.00, 0.82] | [0.12, 0.74] | 0.33 | +0.31 | 3/4 | 0/32 | 5 |

## Accepted negatives by type

| Condition | correction-violating | initial-violating | unspecified |
| --- | --- | --- | --- |
| initial_plain | 6/16 | 0/1 | - |
| initial_audited | 5/16 | 0/1 | - |
| full_plain | 0/16 | 0/1 | - |
| full_audited | 0/16 | 0/1 | - |
| llm_freeform | 1/16 | 0/1 | - |
| repo_tests | 5/16 | 0/1 | - |

## Sanity checks (excluded from primary metrics)

| Condition | reference passes | no-op passes |
| --- | --- | --- |
| initial_plain | 3/4 | 0/4 |
| initial_audited | 3/4 | 0/4 |
| full_plain | 4/4 | 0/4 |
| full_audited | 4/4 | 0/4 |
| llm_freeform | 4/4 | 0/4 |
| repo_tests | 4/4 | 0/4 |

## Paired comparisons (same candidates)

| A | B | Metric | A - B | 95% CI | n labeled for metric | families | A acc & B rej | A rej & B acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | full_plain | FA | +0.35 | [+0.07, +0.71] | 17 | 4 | 6 | 0 |
| initial_plain | full_plain | FR | +0.20 | [+0.00, +0.67] | 10 | 4 | 0 | 2 |
| initial_audited | full_audited | FA | +0.29 | [+0.00, +0.63] | 17 | 4 | 5 | 0 |
| initial_audited | full_audited | FR | +0.20 | [+0.00, +0.67] | 10 | 4 | 0 | 2 |
| initial_plain | initial_audited | FA | +0.06 | [+0.00, +0.27] | 17 | 4 | 1 | 0 |
| initial_plain | initial_audited | FR | +0.00 | [+0.00, +0.00] | 10 | 4 | 0 | 0 |
| full_plain | full_audited | FA | +0.00 | [+0.00, +0.00] | 17 | 4 | 0 | 0 |
| full_plain | full_audited | FR | +0.00 | [+0.00, +0.00] | 10 | 4 | 0 | 0 |
| llm_freeform | full_audited | FA | +0.06 | [+0.00, +0.14] | 17 | 4 | 1 | 0 |
| llm_freeform | full_audited | FR | +0.00 | [+0.00, +0.00] | 10 | 4 | 0 | 0 |
| llm_freeform | full_plain | FA | +0.06 | [+0.00, +0.14] | 17 | 4 | 1 | 0 |
| llm_freeform | full_plain | FR | +0.00 | [+0.00, +0.00] | 10 | 4 | 0 | 0 |
| repo_tests | full_audited | FA | +0.29 | [+0.11, +0.64] | 17 | 4 | 5 | 0 |
| repo_tests | full_audited | FR | +0.40 | [+0.00, +0.82] | 10 | 4 | 0 | 4 |

## Exploratory sensitivity: construction-intent labels (not pre-specified)

Constructed candidates labeled by how they were built (near miss = invalid, alternative = valid), including those the D19 rule marked ambiguous; natural candidates keep their D19 label.

| Condition | False acceptance | False rejection |
| --- | --- | --- |
| initial_plain | 0.45 (10/22) [0.18, 0.73] | 0.20 (2/10) [0.00, 0.67] |
| initial_audited | 0.41 (9/22) [0.18, 0.70] | 0.20 (2/10) [0.00, 0.67] |
| full_plain | 0.14 (3/22) [0.04, 0.20] | 0.00 (0/10) [0.00, 0.00] |
| full_audited | 0.14 (3/22) [0.04, 0.20] | 0.00 (0/10) [0.00, 0.00] |
| llm_freeform | 0.23 (5/22) [0.17, 0.33] | 0.00 (0/10) [0.00, 0.00] |
| repo_tests | 0.36 (8/22) [0.10, 0.67] | 0.40 (4/10) [0.00, 0.82] |

## Post-hoc analyses after the internal review (exploratory, not pre-specified)

### Near misses accepted, by label status

| Condition | D19-confirmed invalid | D19 ambiguous |
| --- | --- | --- |
| initial_plain | 4/15 | 4/5 |
| initial_audited | 3/15 | 4/5 |
| full_plain | 0/15 | 3/5 |
| full_audited | 0/15 | 3/5 |
| llm_freeform | 1/15 | 4/5 |
| repo_tests | 5/15 | 3/5 |

### Rates under the independent construction checks' labels

| Condition | False acceptance | False rejection |
| --- | --- | --- |
| initial_plain | 0.52 (13/25) | 0.29 (2/7) |
| initial_audited | 0.48 (12/25) | 0.29 (2/7) |
| full_plain | 0.24 (6/25) | 0.00 (0/7) |
| full_audited | 0.24 (6/25) | 0.00 (0/7) |
| llm_freeform | 0.32 (8/25) | 0.00 (0/7) |
| repo_tests | 0.40 (10/25) | 0.43 (3/7) |

### Held-out candidates whose graded patch duplicates another candidate

* CS-04-pre-correction: same patch as dev CS-04-dev-attack-full_session-a3
* CS-04-eval-nm-2: same patch as dev CS-04-dev-attack-full_session-a3, same patch as heldout CS-04-pre-correction

| Condition | FA without duplicates | FR without duplicates |
| --- | --- | --- |
| initial_plain | 0.27 (4/15) | 0.20 (2/10) |
| initial_audited | 0.20 (3/15) | 0.20 (2/10) |
| full_plain | 0.00 (0/15) | 0.00 (0/10) |
| full_audited | 0.00 (0/15) | 0.00 (0/10) |
| llm_freeform | 0.07 (1/15) | 0.00 (0/10) |
| repo_tests | 0.33 (5/15) | 0.40 (4/10) |

### B1 restricted to the base commit's own tests (checks added by the session agent removed)

False acceptance 0.76 (13/17); false rejection 0.00 (0/10).

## Labels and human-review queue

| Task | valid | invalid | ambiguous | unlabeled | queued for review |
| --- | --- | --- | --- | --- | --- |
| CS-01 | 2 | 6 | 0 | 0 | - |
| CS-02 | 3 | 4 | 1 | 0 | CS-02-eval-alt-2, CS-02-eval-nm-4 |
| CS-03 | 3 | 2 | 3 | 0 | CS-03-pre-correction, CS-03-eval-nm-1, CS-03-eval-nm-2, CS-03-eval-nm-4, CS-03-eval-alt-1 |
| CS-04 | 2 | 5 | 1 | 0 | CS-04-eval-nm-5 |

## Contract recovery (model mappings, proposals)

| Task | Variant | Coverage of active reference requirements (mapper 1) | Unsupported | Contradicting | Coverage (mapper 2) | Mapping agreement (kappa) |
| --- | --- | --- | --- | --- | --- | --- |
| CS-01 | initial_only | 0.50 (2/4) | 4/5 | 4 | 0.50 (2/4) | 1.00 |
| CS-01 | full_session | 1.00 (4/4) | 0/6 | 0 | 1.00 (4/4) | 1.00 |
| CS-02 | initial_only | 1.00 (6/6) | 2/8 | 0 | 1.00 (6/6) | 1.00 |
| CS-02 | full_session | 1.00 (6/6) | 0/10 | 0 | 1.00 (6/6) | 0.92 |
| CS-03 | initial_only | 0.75 (3/4) | 1/5 | 0 | 0.75 (3/4) | 1.00 |
| CS-03 | full_session | 1.00 (4/4) | 1/5 | 0 | 1.00 (4/4) | 1.00 |
| CS-04 | initial_only | 0.50 (3/6) | 0/3 | 0 | 0.50 (3/6) | 1.00 |
| CS-04 | full_session | 1.00 (6/6) | 1/7 | 0 | 1.00 (6/6) | 1.00 |

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

