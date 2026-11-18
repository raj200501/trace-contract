# Run comparison: pilot-v0.2 vs pilot-v0.3

Pairs graded in both runs: 108 (only in pilot-v0.2: 0, only in pilot-v0.3: 132).

* Reward agreement (pass vs non-pass): 107/108
* Exact-outcome agreement: 107/108

| Verifier | Candidate | pilot-v0.2 | pilot-v0.3 | Diagnostics (old -> new) |
| --- | --- | --- | --- | --- |
| repo_tests | CS-04-eval-alt-1 | task_failure (600.3 s) | pass (38.4 s) | protected path change removed before grading: tests/test_more.py; [run 0] repository tests failed to collect -> protected path change removed before grading: tests/test_more.py |
