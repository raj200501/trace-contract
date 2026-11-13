# Experimental protocol

Version: **v0.2 (pilot, exploratory)** — v0.1 written before the first evaluation run; v0.2 amendments (§10) also made before any evaluation run.
Timestamp and SHA-256 of this file are recorded in `docs/decision_log.md`. This is a
locally timestamped protocol, **not** a formal preregistration. Any later change is
made in a new version with a decision-log entry; results are always reported
against the protocol version in force when they were produced.

## 1. Question

When coding tasks are reconstructed from agent sessions, how often do omitted
user corrections cause a verifier to reward an unacceptable solution, and which
reconstruction and validation methods reduce that error without rejecting valid
alternatives?

The comparison of initial-request-only vs correction-aware reconstruction measures
**information lost during dataset construction**, not the capability of an agent
that was never told a requirement.

## 2. Populations (never pooled without saying so)

* **Natural** — naturally occurring sessions (planned: SWE-chat; currently blocked
  on data-access terms, see decision log D4).
* **Controlled** — real agent runs (Claude Code subagent) on pinned public
  repositories with user turns written and hashed by the study before the run
  (protocol CS-v1). Scripted user feedback is synthetic.
* **Fixture** — hand-written unit-test fixtures (code tests only, never evidence).

The pilot uses controlled tasks only. Claims from it are limited to controlled
sessions.

## 3. Unit of analysis and splitting

* Primary unit: an independent **task family** (one source session and everything
  derived from it: contracts, verifiers, all candidates and their variants).
* Uncertainty: percentile intervals from a cluster bootstrap over task families
  (2,000 resamples, seed 0). Candidates or mutants are never treated as independent
  samples. With fewer than ~10 families, intervals are reported but are not
  evidence of an effect; the pilot is descriptive.
* Development vs evaluation: each family has development candidates (used only by
  audit:v1) and evaluation candidates (held out). Evaluation candidates are
  generated after all verifiers of the family are frozen, by separate agents in
  workspaces without verifier files.

## 4. Verifier conditions (same generator model and prompt template)

| Id | Contract input | Audit | Notes |
| --- | --- | --- | --- |
| C1 `initial_plain` | initial-request-only contract | none | single-pass generation |
| C2 `initial_audited` | initial-request-only contract | audit:v1 (≤3 revisions) | starts from C1 tests |
| C3 `full_plain` | correction-aware structured contract | none | single-pass generation |
| C4 `full_audited` | correction-aware structured contract | audit:v1 (≤3 revisions) | starts from C3 tests (proposed method) |
| B1 `repo_tests` | — | — | repository tests at the reference state, PASS-on-reference selection, `in_process` |
| B2 `llm_freeform` | whole session transcript | none | competent full-session LLM baseline without contract machinery |

Contracts are recovered by the same proposer prompt (`contract:v1`), given the
whole session (full) or only the first user request (initial). All generators may
read the base repository and the reference diff and may query base behaviour; plain
generators may not execute their tests on any candidate. Generation costs (agent
turns/tokens where recorded) are reported per condition; budgets are matched by
prompt (6–14 tests) rather than by tokens, and unequal costs are reported.

## 5. Candidates and labels

Evaluation candidates per family:

* `observed_pre_correction` — the agent's workspace state captured after the
  initial request and before the scripted correction (naturally observed);
* independent **valid alternatives** (2 per family), written from the reference
  contract instruction by separate agents without access to the reference diff;
* **constructed near misses** (4–6 per family), each intended to violate exactly
  one reference requirement, prioritising requirements introduced by corrections;
* `noop` (sanity only).

The reference solution is shown to every generator and used by audit:v1; it is a
sanity check, not an evaluation positive. Reference and no-op are **excluded from
the primary FA/FR** and reported in a sanity table.

Labels:

* Ground truth is the **reference contract** (pre-registered intended requirements
  for controlled tasks, operationalised with evidence quotes) plus the regression
  norm: a candidate that breaks existing, unrelated behaviour covered by the
  repository's tests is invalid (see `docs/annotation_guide.md`).
* Primary analysis uses **human labels** (adjudicated where two reviewers exist).
* Until human review exists, an **automated pilot** analysis uses proposed labels
  (construction intent, checked against independent reference checks). Such results
  are always marked "automated pilot" and are never described as validated ground
  truth.
* Ambiguous or unlabeled candidates are excluded from FA/FR and counted.

## 6. Outcomes and metrics

* Outcomes: `pass`, `task_failure`, `environment_failure`, `verifier_error`,
  `timeout`, `unresolved` (repeated runs disagree). Only `pass` yields reward.
* **False acceptance** FA(V) = fraction of invalid evaluation candidates with
  outcome `pass`. **False rejection** FR(V) = fraction of valid evaluation candidates
  without `pass`.
* Primary analysis: every non-pass outcome counts as rejection. Infrastructure
  outcomes are reported separately per condition, and a sensitivity analysis
  excludes them.
* Pooled rates (all candidates) and macro rates (mean over tasks with a non-zero
  denominator) are both reported, with denominators.
* Negatives are broken down by type: `correction_violating` (violates a reference
  requirement introduced after the first user request), `initial_violating`,
  `unspecified`.
* Secondary: requirement coverage and unsupported-requirement rate of recovered
  contracts against the reference contract; valid task yield from all screened
  sessions with rejection reasons; environment/replay reliability; verifier
  flakiness (audit repeats); cost/time per accepted task.

## 7. Pre-specified comparisons (paired, same candidates)

1. C1 vs C3 and C2 vs C4 — information lost by initial-request-only reconstruction.
2. C1 vs C2 and C3 vs C4 — effect of the audit procedure.
3. B2 vs C4 and B2 vs C3 — structured contract vs competent full-session LLM baseline.
4. B1 vs C4 — repository tests vs the proposed verifier.

For each: difference in FA and FR, cluster-bootstrap interval, and discordant-pair
counts. Null and negative results are reported. No significance-driven stopping:
the pilot's size is fixed by the scenarios registered before it ran.

## 8. Freezing and versioning

Verifiers are frozen (content hash recorded) before evaluation. If a verifier or
harness bug is found afterwards, the benchmark version is bumped and every
affected condition is re-run; results of both versions are kept.

## 9. Confirmatory study (to be frozen after the pilot)

The pilot estimates annotation effort, variability, and yield. Before any
confirmatory run, a v1.0 protocol will fix: data source and sampling frame
(natural sessions), target number of independent task families justified by the
pilot's variability (the 60–100 figure in the project brief is a planning
placeholder, not a requirement), annotation procedure with a second reviewer on an
overlap subset and agreement statistics, the final candidate-generation recipe, and
the analysis plan above with any revisions.

## 10. Amendments in v0.2 (made before any evaluation run)

* Additional descriptive metrics per condition: Youden's J = (1 − FR) − FA, and the
  number of task families with at least one accepted negative.
* Negatives are additionally stratified by origin (naturally observed
  pre-correction state vs constructed near miss); tampering probes are never mixed
  into semantic false acceptance.
* Automated-pilot labels follow the pre-specified proposal rule in decision log D19
  (reference checks + regression norm + construction intent; disagreement →
  ambiguous).
* Generator diversity: all held-out negatives and alternatives come from the same
  model family as the verifiers (no stronger or different generator was available
  within the zero-spend budget); reported as a limitation.
