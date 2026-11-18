# Evaluation runs

Each folder holds one run's manifest, raw results (`results.jsonl`), analysis,
comparisons with earlier runs and HTML report. Recorded outputs are never edited;
superseded runs are kept for the reliability comparison only and are not reported as
pilot results. `logs/` folders are local only (git-ignored).

| Run | Harness | Graded (UTC) | Pairs | Code revision | Status | Why superseded |
| --- | --- | --- | --- | --- | --- | --- |
| `pilot-v0.3.2` | 0.3.2 | 2026-11-18 14:24–14:40 | 240 | `0a94529` | **final** | — |
| `pilot-v0.3.1` | 0.3.1 | 2026-11-18 12:18–12:34 | 240 | `c830977` | superseded by `pilot-v0.3.2` | a candidate `encodings` package could still run before the grader's trusted imports (decision log D40) |
| `pilot-v0.3` | 0.3.0 | 2026-11-18 10:22–10:36 | 240 | `fe30c15` | superseded by `pilot-v0.3.1` | a candidate module shadowing the standard library could forge signed results (D36) |
| `pilot-v0.2-h2` | 0.2.0 | 2026-11-13 04:30 (stopped after 4 pairs) | 4 | `e8f2bab` | superseded | address-space cap with glibc malloc arenas stalled threaded tests (D30); CS-04 B1 v1 selection truncated (D31) |
| `pilot-v0.2` | 0.1.0 | 2026-11-13 04:02–04:21 | 108 | `d7a3e02` | superseded | shared sandbox UID across containers and recorded timeouts as task failures (D28, D29); CS-04 B1 v1 (D31) |

The HTML reports of `pilot-v0.3` and `pilot-v0.3.1` predate the output changes of
protocol v0.5 (D40): they show no macro rates, exact intervals, degenerate marks,
per-metric denominators or "covered but contradicted". Their `analysis.md` files show
the macro rates; the paper tables come from `pilot-v0.3.2`.
