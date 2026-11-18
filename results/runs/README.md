# Evaluation runs

Each folder holds one run's manifest and raw results (`results.jsonl`). The folders
from `pilot-v0.3` on also hold an analysis, comparisons with earlier runs and an HTML
report. `pilot-v0.2` also holds an analysis but no comparisons or report, and
`pilot-v0.2-h2` holds none of these. Raw results and manifests are not edited after
the run. Some derived files were regenerated later with newer scripts, all on
2026-11-18:
* the analysis of `pilot-v0.2` (commit `47b15ad`, which added sections and changed no
  existing line);
* the report and analysis of `pilot-v0.3` (`c9065d1`, `8c13e0c`), and its comparison
  with `pilot-v0.2` (`8c13e0c`);
* all comparison files of `pilot-v0.3` and `pilot-v0.3.1`, with the current
  `scripts/compare_runs.py` (`55a2346`; decision log D44).

Superseded runs are kept for the reliability comparison only and are not reported as
pilot results. `logs/` folders are local only (git-ignored).

| Run | Harness | Graded (UTC) | Pairs | Code revision | Status | Why superseded |
| --- | --- | --- | --- | --- | --- | --- |
| `pilot-v0.3.3` | 0.3.3 | 2026-11-18 17:56–18:11 | 240 | `c997779` | **final** | — |
| `pilot-v0.3.2` | 0.3.2 | 2026-11-18 14:24–14:40 | 240 | `0a94529` | superseded by `pilot-v0.3.3` | a candidate `ast.py` could load while the grader's wrapper formatted a snippet's exception (decision log D44) |
| `pilot-v0.3.1` | 0.3.1 | 2026-11-18 12:18–12:34 | 240 | `c830977` | superseded by `pilot-v0.3.2` | a candidate `encodings` package could still run before the grader's trusted imports (decision log D40) |
| `pilot-v0.3` | 0.3.0 | 2026-11-18 10:22–10:36 | 240 | `fe30c15` | superseded by `pilot-v0.3.1` | a candidate module shadowing the standard library could forge signed results (D36) |
| `pilot-v0.2-h2` | 0.2.0 | 2026-11-13 04:30 (stopped after 4 pairs) | 4 | `e8f2bab` | superseded | address-space cap with glibc malloc arenas stalled threaded tests (D30); CS-04 B1 v1 selection truncated (D31) |
| `pilot-v0.2` | 0.1.0 | 2026-11-13 04:02–04:21 | 108 | `f8e3e65`, `9c2525a+dirty`, `d7a3e02` (see below) | superseded | shared sandbox UID across containers and recorded timeouts as task failures (D28, D29); CS-04 B1 v1 (D31) |

`pilot-v0.2` ran in three invocations (`manifest.json`, `invocations`): CS-04 at
`f8e3e65` (54 pairs), then CS-03 at `9c2525a` with uncommitted changes to tracked files
(4 pairs) and at `d7a3e02` (50 pairs). The other runs listed here have one invocation
each.

The HTML reports of `pilot-v0.3` and `pilot-v0.3.1` predate the output changes of
protocol v0.5 (D40): they show no macro rates, exact intervals, degenerate marks,
per-metric denominators or "covered but contradicted". Their `analysis.md` files show
the macro rates; the paper tables come from `pilot-v0.3.3`.
