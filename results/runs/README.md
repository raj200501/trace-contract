# Evaluation runs

Each folder holds one run's manifest (`manifest.json`) and its graded pairs: the raw
results (`results.jsonl`) in every folder but `natural-pr-v1`, which publishes
`results_public.jsonl` instead (see below). The folders from `pilot-v0.3` on also hold
an analysis (`analysis.md`, `analysis.json`), and all of them but `natural-pr-v1` an
HTML report. Comparisons with earlier runs are in the folders of `pilot-v0.3` to
`pilot-v0.3.3`, and in `pilot-v0.3.5-regrade` (with `pilot-v0.3.3`); `fresh-v1` and
`natural-pr-v1` grade new candidates and hold none. `pilot-v0.2` also holds an analysis
but no comparisons or report, and `pilot-v0.2-h2` holds none of these. Raw results and
manifests are not edited after the run. Some derived files were regenerated later with
newer scripts, all on 2026-11-18:
* the analysis of `pilot-v0.2` (commit `47b15ad`, which added sections and changed no
  existing line);
* the report and analysis of `pilot-v0.3` (`c9065d1`, `8c13e0c`), and its comparison
  with `pilot-v0.2` (`8c13e0c`);
* all comparison files of `pilot-v0.3` and `pilot-v0.3.1`, with the current
  `scripts/compare_runs.py` (`55a2346`; decision log D44).

The three later runs were each committed once (`ea847cd`, `affb1ba`, `d05dd39`), and no
file of theirs has changed since.

Superseded runs are kept for the reliability comparison only and are not reported as
pilot results. `logs/` folders are local only (git-ignored). Post hoc re-analyses of
`pilot-v0.3.3` are not runs: they are in `results/analyses/pilot-v0.3.3-exploratory/`
(protocol §15.1, decision log D49).

| Run | Harness | Graded (UTC) | Pairs | Repeats | Code revision | Status | Why superseded |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `natural-pr-v1` | 0.3.5 | 2026-11-23 04:14–08:35 (two invocations) | 432 | 3 | `e9c9c91` | the natural PR-review arm's run for the first sample: six families, reported as case studies (automated pilot; D76 to D78) | — |
| `fresh-v1` | 0.3.5 | 2026-11-21 12:40–15:12 | 672 | 3 | `eb56aec` | the fresh-agent stratum of the controlled tasks (automated pilot; D61, D62) | — |
| `pilot-v0.3.5-regrade` | 0.3.5 | 2026-11-21 07:21–08:18 | 240 | 3 | `a0542bb` | reliability re-grade of `pilot-v0.3.3`, not a new pilot result (D54) | — |
| `pilot-v0.3.3` | 0.3.3 | 2026-11-18 17:56–18:11 | 240 | 1 | `c997779` | **final** run of the construction pilot; since protocol v0.7 its four families are the development families for the phases that follow (§15.1) | — |
| `pilot-v0.3.2` | 0.3.2 | 2026-11-18 14:24–14:40 | 240 | 1 | `0a94529` | superseded by `pilot-v0.3.3` | a candidate `ast.py` could load while the grader's wrapper formatted a snippet's exception (decision log D44) |
| `pilot-v0.3.1` | 0.3.1 | 2026-11-18 12:18–12:34 | 240 | 1 | `c830977` | superseded by `pilot-v0.3.2` | a candidate `encodings` package could still run before the grader's trusted imports (decision log D40) |
| `pilot-v0.3` | 0.3.0 | 2026-11-18 10:22–10:36 | 240 | 1 | `fe30c15` | superseded by `pilot-v0.3.1` | a candidate module shadowing the standard library could forge signed results (D36) |
| `pilot-v0.2-h2` | 0.2.0 | 2026-11-13 04:30 (stopped after 4 pairs) | 4 | 1 | `e8f2bab` | superseded | address-space cap with glibc malloc arenas stalled threaded tests (D30); CS-04 B1 v1 selection truncated (D31) |
| `pilot-v0.2` | 0.1.0 | 2026-11-13 04:02–04:21 | 108 | 1 | `f8e3e65`, `9c2525a+dirty`, `d7a3e02` (see below) | superseded | shared sandbox UID across containers and recorded timeouts as task failures (D28, D29); CS-04 B1 v1 (D31) |

`pilot-v0.2` ran in three invocations (`manifest.json`, `invocations`): CS-04 at
`f8e3e65` (54 pairs), then CS-03 at `9c2525a` with uncommitted changes to tracked files
(4 pairs) and at `d7a3e02` (50 pairs). `natural-pr-v1` ran in two (below). The other
runs listed here have one invocation each.

The HTML reports of `pilot-v0.3` and `pilot-v0.3.1` predate the output changes of
protocol v0.5 (D40): they show no macro rates, exact intervals, degenerate marks,
per-metric denominators or "covered but contradicted". Their `analysis.md` files show
the macro rates; the construction pilot's paper tables come from `pilot-v0.3.3`. The
paper's tables of the later runs come from `fresh-v1`, `pilot-v0.3.5-regrade` and
`natural-pr-v1` (`paper/make_tables.py --fresh`, `--regrade` and `--natural-run`).

## The runs since protocol v0.7

All three were graded with `tc-harness/0.3.5`, every pair three times, with the
`--pilot` flag: their labels are model proposals and no human label exists. Their
analyses follow the reporting rules of protocol v0.8 (§16.6): the per-family table is
the primary display, and each distinct graded patch counts once.

**`pilot-v0.3.5-regrade`** (decision log D54; protocol §15.3, §16.1). The 240 pairs of
`pilot-v0.3.3` graded again under harness 0.3.5, from a clean working tree on an
otherwise quiet host. It agrees with `pilot-v0.3.3` on all 240 pairs, in reward and in
exact outcome (112 pass, 128 task failures; `compare_pilot-v0.3.3.json`), and no pair's
repeats disagreed, so no outcome is unresolved. Under §15.3 it is a reliability run, not
a new pilot result. Its `analysis.json` records the analysis's revision as `4aecca0`
with uncommitted changes (`+dirty`); the grading ran at `a0542bb`.

**`fresh-v1`** (decision log D55 to D58, D61, D62; protocol §15.4, §15.5, §16.2, §18).
It grades the 80 fresh-agent attempts on CS-01 to CS-04, registered as the stratum
`fresh-v1` (`tasks/<id>/strata/fresh-v1.json`), and each task's reference solution,
under the six frozen conditions, the reference checks and the independent labeler: 4
families × 21 candidates × 8 verifiers = 672 pairs. 427 pass and 245 are task failures,
with no infrastructure outcome and no unresolved pair. One invocation:
`tracecontract evaluate tasks/CS-01 tasks/CS-02 tasks/CS-03 tasks/CS-04 --run-id fresh-v1
--strata fresh-v1 --only-strata --conditions initial_plain initial_audited full_plain
full_audited llm_freeform repo_tests reference_check --with-extra-verifiers --repeats 3
--pilot`.
* The analysis ran from a clean worktree at `cbdcd92` (D61). The reviewed audit excludes
  one attempt (CS-02-fresh-A-final-1), so 79 attempts are analysed: 29 invalid and 50
  valid by rule D19.
* `analysis_sensitivity.json` and `analysis_sensitivity.md` are the sensitivity view of
  §18.1, which excludes all 26 attempts that the audit script flagged.
* D62 recomputes the run's numbers independently, gives the error analysis and corrects
  D58 and §18.2.

**`natural-pr-v1`** (decision log D64, D65, D70 to D78; protocol §15.6, §17, §19, §20).
It grades the first sample's six accepted natural PR-review families, NP-03, NP-04,
NP-05, NP-18, NP-19 and NP-20 (§20.2): 9 verifiers (C1 to C4, B1, B2, B3, the reference
checks and the independent labeler) × 8 candidates (six held-out ones, the reference
solution and the no-op) × 6 families = 432 pairs. No pair is unresolved and none ended
in an infrastructure outcome (D78).
* D19's labels of the 36 held-out candidates were made first, as the run's first step
  (D73, D74, D76). The run is an automated pilot because every family's acceptance gate
  is pending: provenance eligibility needs a human reviewer (§16.4).
* Two invocations, both at `e9c9c91`: the first (04:14:36) was stopped within seconds,
  before any pair was graded, and the second started at 04:15:05 (D76).
* The analysis (at `cd5cee4`) is in case-study mode: per-family tables only, with no
  pooled rate, interval or p-value (§19.6, §20.3; D78). B3 is a secondary condition,
  reported apart.
* The folder holds only what `scripts/publish_natural_run.py` writes (D78):
  `manifest.json`, `analysis.json` and `analysis.md`, copied byte for byte, and
  `results_public.jsonl`, one line per graded pair with its ids, outcome, reward,
  harness version, counts of checks by status, and the sha256 of its log and of its
  private line. The raw results, whose check ids, messages and diagnostics carry upstream
  code, the logs and the HTML report stay in the git-ignored
  `data/natural/runs/natural-pr-v1/` (protocol §17.4).
* The extension's families are to be graded in a run of their own, `natural-pr-v2`
  (§20.2).
