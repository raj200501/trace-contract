# Experimental protocol

Version: **v0.6 (pilot, exploratory)**. v0.1 was written before the first evaluation run. The v0.2 amendments (§10) were also made before any evaluation run. The v0.3 amendments (§11) were made after two superseded runs and before the final pilot run. The v0.4 amendments (§12) were made after the internal review of that run. The v0.5 amendments (§13) were made after the review of the internal-review dispositions and a final claims audit of `pilot-v0.3.1`, before `pilot-v0.3.2`. The v0.6 amendments (§14) were made after a verification of the resulting fixes, before `pilot-v0.3.3`.
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

## 14. Amendments in v0.6 (after the verification of the fixes, before `pilot-v0.3.3`)

A read-only verification of the fixes recorded in D40–D43 (model agents, four lenses:
paper, documents, code, and diff and privacy; every finding checked by a second agent,
then a completeness critic; decision log D44) found the following:
* **A harness defect in the error path.** After its trusted imports, the wrapper puts
  the candidate directories on `sys.path`. When a snippet raised, the wrapper's own
  error path then imported modules lazily: Python 3.12's `traceback` imports `ast` and
  `unicodedata` while formatting a traceback. A candidate `ast.py`, shipped in the patch
  or written at runtime, therefore ran inside the trusted reporting code and could forge
  the authenticated result. In a Docker probe under 0.3.2, a snippet that only divides
  by zero was reported as `ok=True` with a forged value. The fix is `tc-harness/0.3.3`:
  the wrapper imports `ast`, `unicodedata`, `linecache` and `tokenize` with its trusted
  imports. After the snippet returns or raises, it restores its own `sys.path` and
  `sys.meta_path` and clears the import cache before it formats, serialises and signs
  the result. No candidate in the pool ships a module of any of these names. Under all
  three candidate-path layouts (`/work`, `/work/src`, `/work/src:/work`), a snippet sees
  the same `sys.path`, `PYTHONPATH`, interpreter flags and environment under 0.3.2 and
  0.3.3; only `ast` (with `_ast`) and `unicodedata` are already loaded.
* **An audit gap.** The held-out generators, the reference-check writers and their
  reviewers ran as subagents of the build session and shared its scratch directory with
  the builder and with each other. The tool-input audit (D26, D37) treated only the
  sealed subfolders of that directory as forbidden. A stricter re-audit (D44) resolves
  paths, treats the whole scratch directory as forbidden and attributes each read there
  to the agent that wrote the file. It finds no read of forbidden material. Some
  listings showed names only:
  * the scratch directory's top level, listed by two agents;
  * `tasks/<id>/verifiers/`, listed by the CS-03 and CS-04 reference-check writers
    (known since D27);
  * the directory that holds CS-02's workspaces, listed by one fixer of CS-02's
    reference checks.

  One reviewer of CS-02's reference checks read the first 50 lines of an earlier
  reviewer's test runner. Every other read in the scratch directory was of the reading
  agent's own files.

Under §8 every condition of every task is re-run under 0.3.3. The D19 labels are
re-proposed first. The run is `pilot-v0.3.3`; `pilot-v0.3.2` is kept and compared pair
by pair. Primary metrics, comparisons and the label rule are **unchanged**.

The following changes are made to the human-label procedure (§5), which has not yet been
used:
* Every task is reviewed by two reviewers. The packets are merged only when each task has
  two complete reviews. Disagreements on validity have no final label until they are
  adjudicated. Before, the last reviewer's label was used.
* The packet hides the origin field, the ids, the descriptions, the proposals and the
  outcomes, but not the origin. A candidate's origin can still be inferred from its
  content: near misses resemble each other and the reference, and the user's corrections
  describe what the agent did first. The packet therefore shows the user turns of the
  session but not the agent's turns or tool output. Identical diffs share one id. Each reviewer
  records an origin guess per candidate, and the merge reports how often the guesses are
  right.
* Contract reviews are recorded per reviewer in the same label file and merged with the
  labels.

Corrections to the wording of earlier sections, which are kept as written:
* **§3.** "Workspaces without verifier files": the exported workspaces held no verifier
  files except B1's repository tests in the near-miss workspaces (§12). The agents ran in
  the repository checkout, so frozen verifiers were readable (D41). They also shared the
  build session's scratch directory (above).
* **§4.** The generation prompt asks for 6–14 tests; the audit's reviser may keep 6–16.
* **§12 and §13.** The exact (unclustered) intervals are shown for rates only. No
  exact interval is given for paired differences.
* **§13.** The 2026-11-18 prompts are CS-01's near-miss prompts and all of CS-02's
  prompts for held-out candidates and reference checks. CS-01's alternatives and
  reference checks used the CS-03/CS-04 prompts. CS-03's reference checks, too, were
  written while its pool was being generated; they were frozen before its pool was
  registered.
* **§13 (timing).** v0.5 was hashed after the final claims audit had found and verified
  its findings. The audit's completeness critic finished after the hash and after
  `pilot-v0.3.2` had started; its findings (D43) changed no analysis, label rule or
  graded input.

## 15. Amendments in v0.7 (after the re-audit of 2026-11-21, D47; before any generation for the new strata)

This section makes the protocol v0.7. The version line at the top of the file is left as
it was, so that the earlier text stays a byte prefix of this file.

**15.1 Standing of the pilot.** `pilot-v0.3.3` remains the record of the original pilot,
and nothing in it is edited. Its four families (CS-01 to CS-04) are the development
families for the phases below. Re-analyses of it made after this date are post hoc and
exploratory. They are reported separately, in `results/analyses/pilot-v0.3.3-exploratory/`,
and never replace its pre-specified results.

**15.2 New strata and populations.** Each gets its own run id, manifest and analysis,
and none is pooled with another without saying so.
* `fresh-v1`: fresh-agent attempts on CS-01 to CS-04 (controlled population, a new
  candidate stratum; §15.4).
* `natural-pr-v1`: natural PR-review tasks from AIDev v5 (population `natural:pr-review`;
  §15.6).
* Trace Commons: screening only (population `natural:chat`). Tasks are built only if a
  session proves reconstructable, and then only under a later amendment.
* A controlled expansion is not part of this amendment. It needs its own amendment,
  hashed before any new scenario runs.

**15.3 Harness and grading for new runs.**
* New runs use `tc-harness/0.3.4`. It differs from 0.3.3 only in one respect: a failure
  while formatting a value or an exception for a result message is caught and replaced by
  the type name, so formatting can never change an outcome (D46).
* Before `fresh-v1` is graded, the 240 pairs of `pilot-v0.3.3` are re-graded under 0.3.4
  as a reliability run. Every outcome difference is reported. The run is not a new
  pilot result.
* Every new pair is graded three times. A pair whose repeats disagree is `unresolved`,
  which counts as a rejection, as in §6. The number of unresolved pairs is reported.

**15.4 Fresh-agent stratum (`fresh-v1`).**
* **Instructions.** Two variants per family are fixed before any attempt:
  * `u1`: the session's first user prompt U1, verbatim;
  * `final`: U1 verbatim, then the line `Later in the session the user added:`, then U2
    verbatim.

  Nothing else is given: no reference, no session transcript, no verifier, no candidate
  and no label. The instruction files and their sha256 values are logged in the
  decision log before the first attempt starts.
* **Workspace.** Each attempt gets its own isolated workspace, made by
  `scripts/make_agent_workspace.py`. It holds a copy of the task's base snapshot (a fresh
  git repository with one base commit), the instruction, and the same sandbox wrappers
  the controlled sessions used. It holds nothing from `tasks/`, `results/`, `docs/`,
  `data/`, `paper/`, another workspace or the build session's scratch directory.
* **Agents.** Claude Code general-purpose subagents of the build session, in two
  configurations:
  * configuration A: the session's default model;
  * configuration B: the smallest model tier the agent tool offers.

  Both get the same prompt template, tools and instruction, and the same budget of 35
  minutes of wall time. Model identifiers are kept in the private run records only.
* **Number of attempts.** k = 5 per family, variant and configuration, which makes 80
  attempts. Any reduction is recorded in an appended amendment before the attempts
  start.
* **Capture.** The attempt's final workspace state becomes a candidate, without `.git`,
  caches and the files the patch policy excludes, with origin `fresh_attempt` and split
  `eval`. It is registered in a stratum manifest `tasks/<id>/strata/fresh-v1.json`, so
  `task.json` is not edited. Each attempt record holds:
  * the attempt id, configuration label and variant;
  * start and end times, turns, tool calls and tokens where available;
  * how the attempt ended (finished, gave up or error);
  * the patch sha256.
* **Audit.** Each attempt's transcript gets the strict re-audit over tool inputs and
  tool outputs. An attempt that read forbidden material is excluded from every analysis,
  and the exclusion is reported.
* **Deduplication.** Attempts with identical graded patches count once in FA and FR.
  All attempts count in solve rates.
* **Grading.** Each attempt is graded under the task's six frozen conditions, the
  reference checks and the independent labeler (§15.5).
* **Labels.** D19 applies unchanged, with fresh attempts treated as natural candidates
  (sources 1 and 2). The independent labeler's verdict is reported as a second labeling.
  No human labels exist; every attempt is queued for the review packet.
* **Estimands.** All are descriptive, since there are four families:
  1. the solve rate per configuration and variant, by the reference checks and the
     regression norm;
  2. FA and FR per condition on this stratum, under each labeling;
  3. the share of `u1` attempts that violate a correction requirement (natural
     correction-violating negatives no generator saw), and how C1 and C3 grade them;
  4. agreement between D19 and the independent labeler.

**15.5 Independent labeler.** One per family, for CS-01 to CS-04 and for every natural
task.
* **Author and inputs.** A configuration-B agent writes it, so its author differs from
  the reference-check writers, who were configuration A. Its inputs are the reference
  contract and the base snapshot. It may not read the reference diff, the reference
  checks, any generated verifier, any candidate or any label.
* **Form.** Per-requirement checks: properties of the specified behaviour, invariants
  checked differentially against the base, and examples quoted in the contract.
* **Validation.** It may run its tests in the sandbox against the base and, without
  reading its files, against the materialised reference state. It must pass on the
  reference and fail on the no-op for every requirement the task changes. One revision
  is allowed, after which the agent sees only the names of failing checks. A labeler
  that still fails on the reference is reported as unusable for that family.
* **Freezing.** It is frozen before any fresh attempt or natural held-out candidate
  exists. Its agreement with D19 on the 32 existing candidates of `pilot-v0.3.3` is
  reported as exploratory, since those candidates existed before it was written.

**15.6 Natural PR-review arm (`natural-pr-v1`).**
* **Sampling frame.** AIDev v5 at `b37f9fd1`, with stages S1 to S8a exactly as
  implemented in `scripts/screen_aidev.py` at the commit that adds this amendment, and
  recorded in `data/manifests/screening_natural_aidev.json`:
  * S2: Python repositories under MIT, Apache-2.0 or BSD licences, not forks;
  * S4: human, thread-starting comments not written by the PR's author;
  * S5: on a `.py` file, with a diff hunk;
  * S6: the commented code changed afterwards;
  * S7: the reviewed commit is in the PR's commit list, and a later commit exists;
  * S8: a linked issue written by a person;
  * S8a: the first later commit is attributed to an agent.

  The S9 sample is the one fixed in D47: 150 of the 684 comments that survive S8a,
  drawn with `random.Random(20261121)` over the survivors sorted by comment id. No
  top-up was needed.
* **Diffs for S9.** Each sampled comment's repository is fetched as a partial clone
  (blobs on demand), together with the PR head ref (`refs/pull/<n>/head`). The diff of
  the reviewed commit against the first later commit, for the commented file, is
  computed outside the repository. Fetches are capped at 300 MB per repository and 5 GB
  in all, and every fetch is recorded. A comment whose commits cannot be fetched fails
  S9 with that reason.
* **S9 (model proposal).** A comment qualifies only if all three hold:
  1. it requests a change of behaviour or reports a defect, rather than style, naming,
     documentation, refactoring, tests only or a question;
  2. the first later commit of the PR that touches the commented file changes the
     commented region in a way that addresses the request;
  3. the requested behaviour can be checked by an offline Python test.

  Two independent configuration-A agents judge each comment from pseudonymised text and
  from diffs fetched from the public repository. A comment qualifies only if both say
  yes. Disagreements are excluded and counted. These judgments are proposals and are
  queued for human coding.
* **S10 (replayability).**
  * The S9 fetches are reused: the PR head ref from the public repository, as a partial
    clone within the same caps, with every fetch recorded.
  * The reviewed and the addressing commits must be reachable.
  * The base is the merge-base of the PR's first commit's parent with the default
    branch. If that cannot be determined, the base is the parent of the first commit,
    and the task is recorded as approximate.
  * A merge commit between the base and the addressing commit makes the task approximate
    when the merge does not touch the commented file. Otherwise the task is rejected.
  * The environment is Python 3.12 with a wheels-only, pinned dependency closure,
    resolved from the repository's declared dependencies at the base in a separate,
    network-enabled build step. Grading is offline.
  * The repository's tests at the base must collect and run in the sandbox within 10
    minutes.

  Every rejection is written to the ledger with its stage and reason.
* **Families and stopping.**
  * A family is one PR. If a PR has several qualifying comments, the earliest becomes
    the task's correction, and the others are recorded.
  * At most 2 families come from one repository: the earliest PRs by creation time.
  * Building stops at 30 accepted tasks, or when the whole S9 sample has been screened.
  * If fewer than 10 tasks reach S10, the arm is reported as a screening study only.
* **Task definition.**
  * The initial request is the linked issue's title and body, sanitised.
  * The correction is the review comment, together with any later replies in the same
    thread by the same reviewer before the addressing commit, sanitised, plus its diff
    hunk as context.
  * The pre-review state is the tree at `original_commit_id`. It becomes a held-out
    candidate with origin `natural_pre_review`.
  * The reference solution is the tree at the addressing commit, relative to the base.
* **Contracts and verifiers.**
  * The contracts follow §4: `initial_only` from the issue alone, and `full_session`
    from the issue and the review thread, using the contract:v1 template on a rendered
    PR thread.
  * C1 to C4 and B2 use the existing templates.
  * B1 uses the repository's tests at the addressing commit that pass on it.
  * A secondary arm B3 (diff-derived) gets the initial request and the reference diff,
    with no contract; its tests must fail on the base and pass on the reference.
  * Every generated artifact carries a generation record.
* **Reference contract and checks.**
  * A configuration-A agent drafts the reference contract from the issue, the thread and
    the addressing diff. It is a model proposal.
  * The reference checks are written from it by a separate agent. They must pass on the
    reference and fail on the no-op.
  * Their verdict on the pre-review state is recorded but not required. If they pass the
    pre-review state, that candidate is labelled ambiguous for D19 (the correction is
    not observable by the checks).
* **Held-out pool, generated after freezing.** The pool holds the pre-review state, two
  valid alternatives and three near misses, at least two of which target the
  correction. Each is generated in its own isolated workspace.
* **Labels.** Two labelings are reported:
  1. A source-evidence label for the pre-review state: invalid with respect to the
     correction, on the strength of the reviewer's request, the addressing commit and
     the S9 agreement. Its labeler kind is `source_evidence`, and it is reported
     separately.
  2. D19 for every candidate (reference checks, regression norm and construction
     intent), together with the independent labeler (§15.5).

  None of these is a human label.
* **Estimands.** All are descriptive:
  * acceptance of the pre-review states by condition (C1, C2, C3, C4, B1, B2, B3) under
    the source-evidence label;
  * FA and FR per condition over the whole pool under D19, as per-family tables;
  * the funnel S1 to S11 with reasons;
  * build and replay reliability;
  * cost and time per accepted task.
* **Contamination and privacy.** AIDev v5 PRs and their repositories predate the
  generators' training data, and public merged fixes may be memorised. This is
  disclosed. Privacy follows D47.

**15.7 Reporting rules for every new run.**
* The per-family table is the primary display.
* Each paired comparison carries an exact sign-flip randomization p-value over families,
  with its attainable floor.
* Bootstrap intervals go to an appendix and are marked as not inferential below 10
  families.
* Each distinct graded patch counts once.
* The oracle-gated view, which drops verifiers that fail their own reference and reports
  the drop as lost yield, is secondary.
* Null results are stated with the main results.

**What this amendment does not change.** D19, the freezing rules and §8 still apply; the
frozen pilot, its verifiers and the harness it used are not changed.

## 16. Amendments in v0.8 (after a verification of round 4 by model agents, D51; before any run, fresh attempt or natural verifier under v0.7)

This section makes the protocol v0.8. The version line at the top of the file is left as
it was, so that the earlier text stays a byte prefix of this file. No run, fresh attempt
or natural verifier exists under v0.7.

**16.1 Harness.**
* §15.3's description of 0.3.4 was too broad. 0.3.4 catches exceptions raised inside
  `repr()` and `str()` and while formatting a traceback, but a successful call can still
  be reported as failed when its result cannot be encoded: for example a dict with mixed
  key types, a self-referencing list, or a dict subclass whose methods raise. 0.3.4 is
  never used for a run.
* New runs use `tc-harness/0.3.5`. It differs from 0.3.3 in one respect: a failure while
  formatting or encoding a value or an exception for a result message never turns a
  successful call into a failed one, and never leaves a call without a result. A value
  that cannot be encoded is converted by trusted code that calls no candidate method,
  with a placeholder naming the type wherever conversion is not possible. The order of
  trust restoration in 0.3.3 is unchanged.
* Candidate code that runs while the result is formatted can still end or stall the
  call. That is the in-call limit, unchanged.
* Every use of 0.3.4 in §15 is to be read as 0.3.5. The reliability re-grade of
  `pilot-v0.3.3` (§15.3) runs under 0.3.5, with three repeats.

**16.2 Fresh-agent instructions and audit (§15.4).**
* The controlled sessions' first prompts name the build session's workspace paths. Those
  directories were sealed on 2026-11-21 (D50).
* `u1` and `final` therefore use U1 and U2 with each absolute path of the old workspace
  replaced by the corresponding path of the attempt's workspace: the repository
  checkout, `run_tests.sh` and `run_python.sh`. Nothing else is changed. Each
  substitution is recorded, and the sha256 of every instruction file is logged before
  the first attempt.
* A fresh-attempt audit profile applies. Everything outside the attempt's own workspace
  counts as forbidden: the repository, the sealed directory, the third-party data under
  `/home/user/ext`, and other workspaces. Tool inputs and tool outputs are both scanned.
  A flagged attempt is excluded and reported.

**16.3 Identifiers.** The schema records:
* the candidate origins `fresh_attempt` and `natural_pre_review`, both labelled by D19's
  natural-candidate rule (sources 1 and 2);
* the labeler kind `source_evidence`;
* the condition B3 (`diff_derived`);
* the sub-populations `natural:pr-review` and `natural:chat`.

Records of the pilot are unchanged.

**16.4 Natural arm (§15.6).**
* S6 is a proxy. It passes a comment when GitHub moved its commit or marked it outdated,
  which does not prove that the commented file changed. S9 criterion 2 therefore
  rejects a comment with the reason "no later commit changes the commented file" when
  no later commit in the PR changes that file.
* S11 means: accepted for building, that is, passes S10 and is within the family cap.
* Every S9 failure is written to the rejection ledger with its stage and reason.

**16.5 Reconstruction check.** Every newly built task must pass the reconstruction check
(`tracecontract reconstruction-check`) before it can pass the acceptance gate or enter a
run. The vacuous leakage field is no longer recorded as a pass for new builds.

**16.6 Analysis of new runs.** `tracecontract analyze` implements the reporting rules of
§15.7 for new runs:
* exact sign-flip p-values with their floors;
* each distinct graded patch counted once;
* the oracle-gated view;
* solve rates per configuration and variant, and the audit exclusions, for `fresh-v1`;
* bootstrap intervals marked as not inferential below 10 families.

The frozen pilot's analysis is unchanged.

## 17. Amendments in v0.9 (stage S10 of the natural arm, D53; before any S10 build)

This section makes the protocol v0.9. The version line at the top of the file is left as
it was. These rules were written after a read-only feasibility scout of the 20
provisional families (D53). The scout read base trees, dependency declarations and wheel
availability, and built nothing. They were fixed before any S10 build, verifier or
grading of a natural task.

**17.1 Environments.**
* Wheels-only, as in §15.6, with one exception. An sdist of a pure-Python package may be
  built into a wheel inside the sandbox, with the network disabled. A pure-Python
  package here is one whose source distribution contains no C, C++, Cython, Rust or
  Fortran sources and declares no extension modules. Each such build is recorded with
  the sdist's sha256 and the resulting wheel's.
* A task whose wheelhouse would exceed 1.5 GB is rejected at S10, with the reason
  "environment too large".
* The closure is resolved from the dependencies declared at the base. Packages that the
  PR adds and that the pre-review or reference state imports are added to it. Versions
  are bounded by the base commit's date where the resolver allows. The closure is pinned
  and recorded.

**17.2 Base tests.**
* The test subset is fixed from the base tree before any verifier generation. It holds
  the test files that import a module the PR changes, together with the test files the
  PR changes that exist at the base. If that set is empty, it holds the test directory
  of the changed package.
* "Collect and run" means: collection succeeds, and the subset runs to completion
  offline in the sandbox within 10 minutes. Skipped tests count as run.
* B1 consists of the tests of the subset at the addressing commit that pass on the
  reference. If no such test exists, B1 is reported as unavailable for that family; this
  is not a rejection.

**17.3 Families.** "The earliest PRs by creation time" (§15.6) is read as the earliest
among those that pass S10. If a family is rejected at S10, the next qualifying PR of the
same repository by creation time takes its place, still with at most 2 per repository.
Every rejection, and every replacement, is written to the ledger.

**17.4 Storage.**
* Natural tasks are built under `data/natural/`, which git ignores, because they hold
  pseudonymised third-party text. The repository holds an index with ids, SHAs, licences
  and file hashes, together with the run records and the analyses.
* Whether generated tests, contracts or texts derived from the threads may be published
  is the owner's decision (D47).

## 18. Amendments in v0.10 (the fresh-v1 audit rule, D57; before any fresh-v1 grading)

This section makes the protocol v0.10. The version line at the top of the file is left as
it was. It is fixed after the 80 attempts ran, and before any of them is graded or
labelled.

**18.1 Audit rule (§16.2).**
* The automated fresh-attempt audit flags possible accesses outside the attempt's
  workspace. Each flag is reviewed by reading the transcript at that point.
* An attempt is excluded when the review confirms that it read, listed or searched
  material outside its workspace: anything under the study repository, the sealed
  directory, `/home/user/ext`, another workspace, or the build session's records.
* These do not exclude an attempt:
  * use of system locations (interpreters, system libraries, the container's
    temporary directory);
  * a harness notice that names a file the attempt never opened;
  * tokens that the audit's parser resolved against the wrong directory, when the
    transcript shows the attempt never touched that path.
* The primary analysis uses the reviewed verdicts. A sensitivity analysis instead
  excludes every attempt the automated audit flagged. Both are reported.

**18.2 Disclosures.**
* Every attempt's context included harness material that is neither a tool input nor a
  tool output: task-list reminders with the build session's task titles, and an
  environment block naming the study repository as the working directory. It holds no
  reference, transcript, verifier, candidate or label.
* One configuration-B attempt (CS-04-fresh-B-final-1) tried to call an unrelated
  session-management tool. The permission system denied the call, so it had no effect.
  It reports this itself, and it is not an exclusion criterion.

**18.3 Later attempts.** Fresh attempts in later rounds run with a restricted tool set
and without harness task lists, where the agent tool allows it.
