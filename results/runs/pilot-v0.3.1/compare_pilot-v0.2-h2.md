# Run comparison: pilot-v0.2-h2 vs pilot-v0.3.1

Pairs graded in both runs: 4 (only in pilot-v0.2-h2: 0, only in pilot-v0.3.1: 236).
Pairs with an unchanged verifier: 0; pairs whose verifier changed between the runs: 4.
Scored check lists compared by: number of checks (4 pairs).

* Reward agreement on unchanged-verifier pairs (pass vs non-pass): 0/0
* Exact-outcome agreement on unchanged-verifier pairs: 0/0
* Changed-verifier pairs with the same reward: 4/4

| Verifier | Candidate | pilot-v0.2-h2 | pilot-v0.3.1 | Diagnostics (old -> new) |
| --- | --- | --- | --- | --- |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-alt-1 | pass | pass | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-eval-alt-2 | pass | pass | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-noop-eval | task_failure | task_failure | verifier changed |
| repo_tests (v1, 616 checks -> v2, 777 checks) | CS-04-pre-correction | task_failure | task_failure | verifier changed |
