# Run comparison: pilot-v0.2 vs pilot-v0.3.2

Pairs graded in both runs: 108 (only in pilot-v0.2: 0, only in pilot-v0.3.2: 132).
Pairs with an unchanged verifier: 99; pairs whose verifier changed between the runs: 9.
Scored check lists compared by: number of checks (108 pairs).

* Reward agreement on unchanged-verifier pairs (pass vs non-pass): 99/99
* Exact-outcome agreement on unchanged-verifier pairs: 99/99
* Changed-verifier pairs with the same reward: 8/9

| Verifier | Candidate | pilot-v0.2 | pilot-v0.3.2 | Diagnostics (old -> new) |
| --- | --- | --- | --- | --- |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-alt-1 | task_failure | pass | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-alt-2 | pass | pass | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-nm-1 | pass | pass | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-nm-2 | task_failure | task_failure | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-nm-3 | task_failure | task_failure | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-nm-4 | task_failure | task_failure | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-nm-5 | pass | pass | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-noop-eval | task_failure | task_failure | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-pre-correction | task_failure | task_failure | verifier changed |
