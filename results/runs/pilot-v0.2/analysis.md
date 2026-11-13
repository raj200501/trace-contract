# Analysis (proposed labels allowed (automated pilot))

Tasks: 2 | independent task families: 2 | results: 108

> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth. With this few task families the intervals are not meaningful evidence of an effect.

## False acceptance / false rejection by condition

Rates with (numerator/denominator) and 95% cluster-bootstrap interval over task families where computable. Reference solution and no-op are excluded (see sanity table).

| Condition | False acceptance | False rejection | Youden's J | Tasks with an accepted negative | Infra outcomes | Excluded (unlabeled/ambiguous) |
| --- | --- | --- | --- | --- | --- | --- |
| initial_plain | 0.71 (5/7) [0.50, 0.80] | 0.00 (0/5) [0.00, 0.00] | +0.29 | 2/2 | 0/16 | 4 |
| initial_audited | 0.57 (4/7) [0.00, 0.80] | 0.00 (0/5) [0.00, 0.00] | +0.43 | 1/2 | 0/16 | 4 |
| full_plain | 0.00 (0/7) [0.00, 0.00] | 0.00 (0/5) [0.00, 0.00] | +1.00 | 0/2 | 0/16 | 4 |
| full_audited | 0.00 (0/7) [0.00, 0.00] | 0.00 (0/5) [0.00, 0.00] | +1.00 | 0/2 | 0/16 | 4 |
| llm_freeform | 0.00 (0/7) [0.00, 0.00] | 0.00 (0/5) [0.00, 0.00] | +1.00 | 0/2 | 0/16 | 4 |
| repo_tests | 0.43 (3/7) [0.20, 1.00] | 0.40 (2/5) [0.33, 0.50] | +0.17 | 2/2 | 0/16 | 4 |

## Accepted negatives by type

| Condition | correction-violating | initial-violating | unspecified |
| --- | --- | --- | --- |
| initial_plain | 5/7 | - | - |
| initial_audited | 4/7 | - | - |
| full_plain | 0/7 | - | - |
| full_audited | 0/7 | - | - |
| llm_freeform | 0/7 | - | - |
| repo_tests | 3/7 | - | - |

## Sanity checks (excluded from primary metrics)

| Condition | reference passes | no-op passes |
| --- | --- | --- |
| initial_plain | -/- | 0/2 |
| initial_audited | -/- | 0/2 |
| full_plain | -/- | 0/2 |
| full_audited | -/- | 0/2 |
| llm_freeform | -/- | 0/2 |
| repo_tests | -/- | 0/2 |

## Paired comparisons (same candidates)

| A | B | Metric | A - B | 95% CI | n candidates | families | A acc & B rej | A rej & B acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| initial_plain | full_plain | FA | +0.71 | [+0.50, +0.80] | 16 | 2 | 5 | 0 |
| initial_plain | full_plain | FR | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| initial_audited | full_audited | FA | +0.57 | [+0.00, +0.80] | 16 | 2 | 4 | 0 |
| initial_audited | full_audited | FR | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| initial_plain | initial_audited | FA | +0.14 | [+0.00, +0.50] | 16 | 2 | 1 | 0 |
| initial_plain | initial_audited | FR | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| full_plain | full_audited | FA | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| full_plain | full_audited | FR | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| llm_freeform | full_audited | FA | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| llm_freeform | full_audited | FR | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| llm_freeform | full_plain | FA | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| llm_freeform | full_plain | FR | +0.00 | [+0.00, +0.00] | 16 | 2 | 0 | 0 |
| repo_tests | full_audited | FA | +0.43 | [+0.20, +1.00] | 16 | 2 | 3 | 0 |
| repo_tests | full_audited | FR | +0.40 | [+0.33, +0.50] | 16 | 2 | 0 | 2 |

## Per-task outcomes

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
| CS-04-eval-alt-1 | valid_alternative | valid | - | pass | pass | pass | pass | pass | task_failure |
| CS-04-eval-alt-2 | valid_alternative | valid | - | pass | pass | pass | pass | pass | pass |
| CS-04-eval-nm-1 | constructed_near_miss | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | pass |
| CS-04-eval-nm-2 | constructed_near_miss | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-eval-nm-3 | constructed_near_miss | invalid | correction_violating | task_failure | task_failure | task_failure | task_failure | task_failure | task_failure |
| CS-04-eval-nm-4 | constructed_near_miss | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |
| CS-04-eval-nm-5 | constructed_near_miss | ambiguous | - | pass | pass | pass | pass | pass | pass |
| CS-04-pre-correction | observed_pre_correction | invalid | correction_violating | pass | pass | task_failure | task_failure | task_failure | task_failure |

