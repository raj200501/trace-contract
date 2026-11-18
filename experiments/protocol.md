# Experimental protocol

Version: **v0.5 (pilot, exploratory)**. v0.1 was written before the first evaluation run. The v0.2 amendments (§10) were also made before any evaluation run. The v0.3 amendments (§11) were made after two superseded runs and before the final pilot run. The v0.4 amendments (§12) were made after the internal review of that run. The v0.5 amendments (§13) were made after the review of the internal-review dispositions and a final claims audit of `pilot-v0.3.1`, before `pilot-v0.3.2`.
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

## 11. Amendments in v0.3 (after the superseded runs, before the final pilot run)

Harness bugs were found during the pilot (decision log D28–D31). The runs
`pilot-v0.2` (harness 0.1.0) and `pilot-v0.2-h2` (harness 0.2.0) are superseded
under §8. Their results are kept and are not reported as pilot results. This
version fixes how the final pilot run is made and what it reports.

* **Harness.** The final pilot run uses `tc-harness/0.3.0` or later, and every
  condition of every task is re-run. Changes against 0.1.0:
  * a sandbox UID unique to each container;
  * bounded malloc arenas;
  * a per-container `RLIMIT_NPROC` of 256;
  * repository-test timeouts recorded as `timeout`.
* **B1 for CS-04** is version 2 (D31): the same overlay, re-selected on the
  reference under harness 0.3.0.
* **Sanity grading.** The evaluation run grades the reference solution with every
  verifier, alongside the held-out candidates and the no-op (as intended in §5).
  It stays excluded from FA/FR.
* **Run conditions.** The final run grades one container at a time, with no other
  sandbox workload running on the host. This limits CPU contention against the
  time limits inside tests.
* **Harness reliability (secondary, descriptive).** For pairs graded in both a
  superseded run and the final run, pass/non-pass agreement is reported, with the
  discordant pairs listed. It measures sensitivity to the harness changes, not
  verifier flakiness.
* **Contract recovery (secondary).**
  * Coverage counts a reference requirement as covered only when a recovered
    requirement maps to it without contradicting it.
  * A second, independent model mapper (same instructions) maps every task, and
    Cohen's κ between the two mappers is reported. Mapper 1 is primary.
  * Model mappings are proposals.
* **Independent construction checks (advisory).** A second agent checks every
  held-out near miss and alternative, and the observed pre-correction states, in
  the sandbox. It tests whether each candidate violates (or satisfies) the
  reference requirements as claimed. Verdicts are recorded as evidence for human
  review (`tasks/*/labels/construction_checks.json`). They never change a label.
  Candidates whose check disagrees with their D19 proposal are queued for human
  review.
* **Exploratory, not pre-specified.** This analysis was added after superseded
  results showed many near misses marked ambiguous by D19. It reports FA/FR with
  constructed candidates labeled by construction intent; natural candidates keep
  their D19 proposal. It is labeled exploratory wherever it appears, and is never
  primary.
* **Unchanged.** Primary metrics, comparisons, label rule D19, the candidate
  recipe, and the exclusion of the reference and no-op from FA/FR.

## 12. Amendments in v0.4 (after the internal review of `pilot-v0.3`)

The adversarial internal review (decision log D36–D38) found the following:
* **A harness security defect.** Candidate code could replace the wrapper's own
  modules (D36). The fix is `tc-harness/0.3.1`.
* **Integrity issues to disclose (D37):**
  * two held-out CS-04 candidates duplicate a development attack;
  * B1's tests were present in the near-miss workspaces;
  * the reference checks were written concurrently with the pool.
* **Presentation gaps.**

Under §8 every condition of every task is re-run under 0.3.1, and the D19 labels are
re-proposed first (run `pilot-v0.3.1`). `pilot-v0.3` is kept and compared pair by
pair. Primary metrics, comparisons and the label rule are **unchanged**.

The following are added as **exploratory, post-hoc** analyses. They were chosen after
seeing `pilot-v0.3`, are labeled as such, and are never primary:
* acceptance of near misses by D19 status;
* rates under the independent construction checks' labels;
* rates without the duplicated candidates;
* B1 restricted to checks from the base commit's own tests;
* exact unclustered intervals next to the cluster bootstrap.

Macro rates and per-metric denominators, which §6 already required, are now shown in
every output.

## 13. Amendments in v0.5 (after the dispositions review and the claims audit of `pilot-v0.3.1`)

A read-only review of how each internal-review finding was resolved, and a final audit
of every public claim (both run by model agents; decision log D40), found the following:
* **A remaining harness defect.** Harness 0.3.1 still started sandbox children with
  the candidate directory on `PYTHONPATH`. The interpreter imports `encodings` from
  `sys.path` before the wrapper's first line runs, so a candidate `encodings` package,
  shipped in the patch or written to `/work` at runtime, ran before the trusted imports.
  In a Docker proof a wrong candidate received reward 1.0. The fix is
  `tc-harness/0.3.2`: the child starts without `PYTHONPATH`, which the wrapper restores
  after its trusted imports. The fix also keeps the repository-test (B1) output tails
  in the host logs.
* **A third duplicate.** Held-out near miss `CS-01-eval-nm-5` differs from development
  attack `CS-01-dev-attack-full_session-a3` by one docstring line.

Under §8 every condition of every task is re-run under 0.3.2. The D19 labels are
re-proposed first. The run is `pilot-v0.3.2`; `pilot-v0.3.1` is kept and compared pair
by pair. Primary metrics, comparisons and the label rule are **unchanged**.

The following output changes are made:
* Degenerate (zero-width) bootstrap intervals are marked in every table, including
  the paired comparisons and the construction-label sensitivity analysis.
* The sensitivity analysis also shows exact intervals.
* Every output shows the per-family counts behind the macro rates, the per-metric
  denominators and "covered but contradicted".
* The exploratory duplicates view of §12 is widened. It now also excludes held-out
  candidates that have the same code as another candidate apart from comments and
  docstrings (`scripts/find_duplicates.py`). This change was made after seeing
  `pilot-v0.3.1` and is exploratory.

Corrections to the wording of earlier sections, which are kept as written:
* **§5.** "Pre-registered" means hashed and logged locally, not a formal
  preregistration. The reference contract is the labeling standard. It was
  operationalised by a model and has so far been reviewed only by a model.
* **§3 and §11.** The held-out pool is generated after freezing, with two exceptions.
  First, the pre-correction state, which was captured during the session. B2's
  generator and the full-session contract proposer saw its edits, in abbreviated form,
  in the session text. Second, CS-04's B1 re-selection (D31).
* **§11.** The candidate recipe and the mapper instructions were not quite unchanged.
  The 2026-11-18 held-out prompts differ from the CS-03/CS-04 prompts, and mapper 2
  got one extra sentence (D40).
* **§12.** The reference checks were written while the pools were being generated
  (CS-01, CS-02, CS-04), or just before CS-03's pool was registered. CS-02's checks
  were revised after its pool was complete.
* **§6.** The generation costs were not recorded. This is a deviation.
