# Downstream training plan (v0.1, draft): not run

**Status: DRAFT. NOT RUN.** No model was trained, fine-tuned, sampled or downloaded for this plan, and nothing was
spent: the study has no GPU and no approved spending (`STATUS.md`, "Not run"). This plan is not hashed, not adopted
and not in force: decision-log entry D82 records that it was written, not that it was adopted, and a later protocol
version must adopt it before any part of it runs. It was written on 2026-11-24, after `fresh-v1` and `natural-pr-v1`
had been graded and analysed.

The configuration it names, `configs/downstream/rft_selection_v0.1.json`, is a configuration of the data step (§2)
applied post hoc to `fresh-v1`, for the illustration of §9. Stage 0 would need a new configuration that names the pool's
run (§2). The configuration and its script are tested (`tests/test_build_training_selection.py`). **A configuration is
not a result.** The only output of anything in this plan is the selection of §9, a post hoc, exploratory description of
what each verifier would have admitted from the recorded `fresh-v1` attempts. It measures no training value.

**Relation to the study.** The study measures reward fidelity: how often a verifier rebuilt from an agent session
accepts an attempt that violates a later user correction, and how often it rejects a valid one. Better verifier
agreement, best-of-N selection, prompt refinement and inference-time feedback are not post-training gains, and nothing
the study has measured shows that training on its environments changes a model. This plan says what a downstream
experiment would have to be for its result to count, and why the study's present families cannot support one (§5).

## 1. Question and hypotheses

**Question.** Does training a model on environments whose verifiers came from the whole session (correction-aware, C3
`full_plain`), against environments whose verifiers came from the first request (initial-only, C1 `initial_plain`),
change its behaviour on held-out task families whose sessions contain corrections?

**Why it could.** In `fresh-v1`, the attempts that saw only the first request and violate the later correction are
honest attempts at that request: they miss what the correction added or changed. C1 accepts 24 of the 27 such attempts
and C3 none (D61); gated C1, the naive-data filter of §3, still admits 14 of the 17 in the three families whose
reference it passes (§9). A training set filtered by C1 therefore reinforces the behaviour the user later corrected.
The two filters keep the same valid first-request attempts: in `fresh-v1` both keep the same 11, and C1 adds the
violators, so the contrast is subtractive, apart from two regression-only CS-02 attempts that C3 admits and C1 rejects
(§9). If the violated corrections share patterns across
repositories, training without the violators could make a model meet held-out corrections more often without being told
them. It could equally teach the model to ignore what a first request explicitly asks, or to fail in some other way,
which is why there are guardrails.

**Hypotheses** (confirmatory, in a fixed sequence, each tested only if every earlier one was rejected, as in the precision
plan §5). Every confirmatory test compares checkpoints of stage 1 (RFT, §2) on the endpoints of §6; the checkpoints of
stage 2 (RL) are compared descriptively only.

1. **H1 (primary).** On held-out families, given only the first request, the model trained on C3-admitted data
   produces fewer final states that violate a correction requirement (E1) than the model trained on C1-admitted data.
2. **G1 (guardrail, non-inferiority).** Given the first request and the correction, the C3-trained model's solve rate
   (E2) is not lower than the unchanged base model's by more than a margin the owner fixes before stage 0.
3. **G2 (guardrail, non-inferiority).** Given only the first request, the C3-trained model does not violate
   requirements of the first request itself (E3, `initial_violating`) more often than the C1-trained model, nor more
   often than the base model, by more than a margin the owner fixes before stage 0: two tests, in that order.
4. **G3 (guardrail, non-inferiority).** Given only the first request, the share of the C3-trained model's attempts
   labelled valid (E4) is not lower than the C1-trained model's, nor than the base model's, by more than a margin the
   owner fixes before stage 0: two tests, in that order. E1 counts correction violators only and E3 initial violators
   only; E4 also counts every other way to fail (an attempt that breaks only the regression norm, an invalid attempt of
   another type, an ambiguous one), so a positive result (§6) cannot come from a model that fails in another way instead.
5. **H2.** On E1, the C3-trained model produces fewer such final states than the unchanged base model.

A hypothesis that is not reached is reported descriptively, never as rejected. The other contrasts (C1-trained against
base; every stage-2 contrast) are descriptive.

## 2. Method, named precisely

The training method is **rejection-sampling fine-tuning (RFT)** in stage 1, which is supervised fine-tuning (SFT) on
the attempts that a verifier admits, and **reinforcement learning (RL) with the verifier as the reward** in stage 2,
which starts only after stage 1 is complete and recorded. Fine-tuning on agent trajectories is the recipe of the
environment-synthesis work the study cites: SWE-smith trains by rejection-sampling fine-tuning on agent trajectories,
and R2E-Gym by SFT on agent trajectories (`yang2025swesmith`, `jain2025r2egym` in `paper/references.bib`, as
`docs/research/notes/env_synthesis.md` records them).

**Stage 0: the pool (no training).** The unchanged base model makes k attempts at each training task, with the first
request alone as the instruction (the `u1` variant of protocol §15.4). It works in an agent scaffold fixed before stage
0, which the study does not have yet, inside the study's per-attempt workspaces and sandbox wrappers
(`scripts/make_agent_workspace.py`). The pool is sampled once, before any filter is applied, and is shared by both
trained conditions, so they differ only in the filter. Each attempt is captured with the patch policy and audited for
reads outside its workspace, as the fresh attempts were (protocol §15.4, §16.2), and the audit checks that each
training example holds nothing beyond the instruction, the scaffold's fixed prompt, the model's messages and tool calls
and the tool results. The scaffold meets protocol §18.3 (a restricted tool set and no harness task lists): no task list
or other material of a build session reaches an
attempt's context, and whatever the scaffold adds besides the instruction and the tool results is fixed in the stage
configuration. The pool is graded like `fresh-v1` (every condition, the reference checks and the independent labeler,
each pair three times), and every condition also
grades each task's reference solution and its no-op, which `fresh-v1` did not do for the no-op. Then the data step runs:
`scripts/build_training_selection.py` with a new configuration for the pool's run, whose standing is `pre-specified`,
whose cell gate requires a graded no-op (`noop_required`), and whose sha256 is logged in the decision log before the pool
is graded. For each condition it lists the attempts that the verifier admits, with the cell gate and without it, and
audits each admitted set against the label rule (labels never filter). Stop rule: if the smaller of the two gated
admitted sets is below the minimum token budget the owner fixes before stage 0, the experiment stops here and reports
the yields.

**Stage 1: RFT.**

* **Training example:** an admitted attempt's whole trajectory in the scaffold: the scaffold's fixed prompt, the
  instruction, the model's messages and tool calls, and the tool results. The loss is taken on the model's own tokens
  only.
* **Admission:** the run's own acceptance rule, which the configuration states and the script checks: a condition admits
  an attempt when the run recorded `pass` for the pair, which with repeats means that every repeat passed; every other
  outcome is a rejection (protocol §6, §15.3). The script refuses a pool with an unresolved pair, an infrastructure
  outcome, a missing pair or an unlabelled attempt.
* **Cell gate:** a condition's verifier contributes data from a task only when it passes the task's reference solution
  (a recorded `pass`, so on every repeat) and fails on the task's no-op (a recorded `task_failure`). The reference part
  is the run's oracle-gated view (protocol §15.7). The no-op part is this plan's: the environment-synthesis pipelines the
  study cites validate a verifier on the gold patch and on the pre-fix state (`docs/research/notes/env_synthesis.md`,
  §0). A cell that fails the gate contributes no data, and the attempts that its verifier admits there are reported as
  lost yield. The data filters are the gated sets. Without the gate, the naive control would be weaker than a standard
  naive pipeline, which validates its tests on the gold patch: C1 fails CS-01's reference, and 10 of its 24 admitted
  violators in `fresh-v1` come from that family (§9; D62). In `natural-pr-v1`, C1 fails its reference in 5 of the 6
  families and C3 in 4 (§5). The ungated sets are reported as a description of each verifier, and nothing trains on
  them.
* **Rounds:** one round of sampling and fine-tuning. Iterating it (expert iteration) would be a later amendment.
* **Pool source:** the base model's own attempts (on-policy), so that the base and both trained models share one
  distribution and the filter is the only difference. A pool from a stronger agent is an alternative for the owner
  (§11): it would raise yields, but the base-against-trained contrast would then include imitation of that agent, and the
  terms of use of its outputs must allow training.

**Stage 2: RL with the verifier as the reward.**

* **Start:** from each condition's stage-1 checkpoint, on the same training tasks and `u1` instructions.
* **Reward:** 1 when the condition's own verifier (C1 or C3) passes the rollout's final state on every repeat, else 0:
  the same acceptance rule as stage 1, so that filter and reward are one function. Rollouts whose repeats disagree get 0
  and are counted. The cell gate applies to the reward as well: a task whose cell the gate drops for a condition is not
  sampled in that condition's stage 2, since its reward would score the accepted solution 0 or the no-op 1. The two
  conditions may therefore train on different tasks; the gate decides which, and they are reported.
* **Algorithm:** on-policy policy-gradient RL with a binary terminal reward. A group-relative method (several rollouts
  per task, advantages relative to the group's mean reward) with a KL penalty toward the stage-1 checkpoint is the
  default; the algorithm and its settings are fixed in a stage-2 configuration hashed before the stage starts.
* **What RL changes in the reading:** stage 2 optimises against the verifier, which the recorded attempts never were
  (§9), so a verifier's gaps can be found and exploited. Section 7 gives the safeguards.

## 3. Conditions

| Condition | Training | Data filter (stage 1) and reward (stage 2) |
| --- | --- | --- |
| Base | none: the unchanged base model, evaluated exactly as the others | none |
| Naive-data control | stage 1, then stage 2 | C1 `initial_plain`, gated (§2): the initial-only contract's plain tests |
| Correction-aware data | stage 1, then stage 2 | C3 `full_plain`, gated (§2): the correction-aware contract's plain tests |

C1 and C3 are the pre-specified contrast of the study (protocol §7, comparison 1). They come from the same proposer
prompt and the same generator template; only the contract differs (paper, Section 2.2). The audited variants (C2, C4)
are left out: the audit changed no C1 outcome on the fresh attempts and added six false rejections to C4 in CS-03
(D61, D62). B1, the repositories' tests, is never a reward: it imports candidate code into the reporting process and an
adversarial candidate can forge its result (D42; paper, Section 9). Ungated C1 is not an arm: its admitted set is
reported as a description of the verifier (§9). Two extra arms are not in the minimum design and are left to the owner:
SFT on the unfiltered pool, which separates training on these tasks at all from the filter's effect, and RL from the
base model without stage 1. B2, the session-LLM baseline, is not an arm: in `fresh-v1` it matched C3 and C4 on false
acceptance (D61), so a positive H1 would speak to whole-session against first-request verifiers, not to the contract
that C3 adds over a transcript-only generator.

## 4. Fixed recipe and matched budgets

**One recipe for both trained conditions,** fixed in a stage configuration and hashed before the stage starts:

* the base model and its revision, the tokenizer and the chat template;
* the scaffold: tools, prompt template, maximum turns and the attempt's wall-time budget (35 minutes for the fresh
  attempts, protocol §15.4);
* the sandbox limits, as `fresh-v1` recorded them in its manifest: 2 CPUs, 4g of memory, 512 processes, 900 s of wall
  time per grade, 512m of temporary and 1g of work space;
* for SFT: full fine-tuning or adapters, optimizer, learning-rate schedule, batch size, sequence length, epochs or steps,
  precision and loss masking;
* for RL: algorithm, rollouts per task, KL coefficient, learning rate, sampling temperature and number of updates;
* the seeds of sampling, data order and training, with S training seeds per trained condition (an owner field; with one
  seed, a difference between two trained models cannot be told from seed variation).

No setting is tuned on a held-out family. Any tuning uses a development split of the training families, logged before
stage 0.

**Matched budgets.**

* **Sampling:** one pool serves both conditions, so its cost is the same for both.
* **Stage 1:** both conditions train on at most T tokens each, with the same number of optimizer steps, fixed in the
  stage configuration. T is derived, not chosen: it is the token count of the smaller gated admitted set, or the owner's
  cap if that is lower, so that neither condition repeats an example within an epoch. Before stage 0 the owner fixes the
  minimum token budget (the stop rule of stage 0) and, if wanted, the cap.
* **Subsampling:** each condition's admitted trajectories are put in an order drawn with a recorded seed, and whole
  trajectories are taken in that order while the running total stays at or below T. A trajectory that would pass T is
  skipped, and the draw goes on to the next. No trajectory is cut, and a condition ends short of T by less than its
  shortest skipped trajectory. The smaller set, when T is its token count, is taken whole. The order, the trajectories
  taken and each condition's tokens are recorded and reported. Where, as in `fresh-v1` (§9), the naive gated set holds
  the correction-aware set's valid `u1` attempts and adds violators, and T is the smaller set's token count, the naive
  condition's subsample can hold only part of the
  trajectories that both filters admit, besides violators, so the trained conditions also differ in how many shared
  trajectories they see. Each condition's count of shared trajectories is recorded and reported.
* **Composition:** budgets are not matched per family, since that would undo the filter, which decides which families
  supply data (in `fresh-v1`, C3 admits no `u1` attempt in CS-01 or CS-04, and gated C1 none in CS-01, §9). Each
  condition's composition by family and configuration is recorded and reported.
* **Stage 2:** both conditions get the same number of RL updates and of rollouts per update. Under the default
  group-relative method, a task whose rollouts in one update all get the same reward has zero advantage and adds no
  policy-gradient signal beyond the KL term, so equal updates need not give the two conditions equal signal. How such
  groups are handled (kept or resampled) is fixed in the stage-2 configuration, and their share per condition and task
  is recorded with the stage-2 logs (§8) and reported. On the §9 pool, C3's `u1` outcomes are all rejections in CS-01
  and CS-04 and all passes in CS-02, and gated C1's are all passes in CS-04. Rollout tokens cannot be matched
  exactly, since a rollout's length depends on the model. Every rollout is capped at the same number of tokens (an
  owner field), and the rollout tokens each condition used are recorded and reported.
* **Evaluation:** every model, the base included, gets the same k, sampling parameters, scaffold and limits.
* **Compute:** GPU hours per stage and condition are recorded. A condition that needs more compute for the same
  budget is reported, not given more budget.

## 5. Families: training, held out, and why the current ones cannot serve

**Training families.** Families whose sessions contain a user correction, each built by the study's recipe: the
initial-only and correction-aware contracts, C1 and C3 from them, the reference contract, the reference checks and the
regression norm (rule D19's label sources), and the independent labeler (protocol §15.5).

**Held-out families.** These are genuinely held out:

* the split is a seeded draw over repositories, not over families: all the families of one repository fall on the same
  side, so the held-out families' repositories are disjoint from the training families'. One repository can hold several
  families: in `natural-pr-v1`, NP-04 and NP-05 share one (`analysis.md`, "Cost and time per accepted task"). The split,
  its seed and the map from family to repository are logged in the decision log before stage 0;
* they are built and frozen (contracts, verifiers, reference checks, labeler) before stage 0 samples anything;
* no training step sees their sessions, corrections or references, and no setting is chosen on them;
* families whose sessions postdate the base model's training data are preferred, and each family's relation to that
  date is recorded, since public fixes may be memorised (paper, Section 8).

**Why the four controlled families cannot serve.**

* **Development families.** CS-01 to CS-04 developed the recipe (protocol §15.1; precision plan §1), and every recorded
  fresh attempt is on them.
* **Synthetic feedback.** Their user turns were written by the study's own agent, so their feedback is synthetic
  (paper, Section 2.1).
* **No power.** With four families, an exact sign-flip test over families cannot give a one-sided p below 0.0625 or a
  two-sided p below 0.125 (D61), and no family would be left to train on.

**Why the six natural families cannot serve.** These are the families of `natural-pr-v1`: NP-03, NP-04, NP-05, NP-18,
NP-19 and NP-20.

* **Case studies.** They are exploratory case studies, reported per family only, since the run grades fewer than 10
  accepted tasks of its own (protocol §19.6, §20.3; D78).
* **Rewards that fail the accepted solution, or accept violators.** C1 and C3 reject every candidate, their own
  reference included, in NP-03, NP-05 and NP-18 (C4 too in NP-03, C1 alone in NP-20). In NP-19, C1, C3 and C4 fail the
  reference and still accept invalid candidates: 2, 1 and 1 of 4 (`analysis.md`, the sanity checks and the primary
  display). In NP-04 and NP-19 the correction-aware verifiers accept near misses that break a correction requirement
  (STATUS; D80). As rewards, they would score the solution the reviewers accepted 0, or reward a violation of the
  correction. The cell gate of §2 would drop every cell named in the first two sentences, since each fails its
  reference, but not NP-04's C3 and C4 cells, which pass theirs (`analysis.md`, the sanity checks).
* **Repository tests that do not discriminate.** The repositories' tests pass the unchanged base in NP-03, NP-05, NP-19
  and NP-20 (STATUS; D80).
* **Second labeling incomplete.** The independent labeler is unusable for NP-03 and NP-19 (D76).
* **No human labels,** and whether pull-request review comments count as user corrections for the claim is an owner
  decision (D47).
* **No fresh attempts.** The natural run graded constructed pools and pre-review states.

**Scale.** The precision plan finds, for the reward-fidelity endpoint, that about 60 eligible families with one natural
negative each are needed for power 0.80 at a difference of 0.20. Thirty families give power 0.45 at 0.20 and 0.87 at
0.35 (precision plan §7), and the inverted sign-flip interval needs at least 8 families to cover (precision plan §6).
The downstream endpoint is a
different estimand: more attempts per family, but variation between trained models and seeds that the fidelity endpoint
lacks, and its unit is the repository (§6). Its number of held-out repositories and families must come from its own
simulation, written before stage 0 (open item O1). Until then the precision plan's figures give the order of magnitude:
tens of held-out repositories, besides the training families.

The training side is further short. The environment-synthesis work above fine-tunes on thousands of verified
trajectories (as the study's research notes record them: 5,016 trajectories for SWE-smith; 3,321 trajectories from
2,048 environments for R2E-Gym). The study has four controlled families and six natural ones, whose corrections are
review comments (D47). Correction-bearing families are also scarce at the source: 31 of 150 and 91 of 534 sampled
review comments qualified at the model-judged stage S9, and 6 of 22 built families of the first sample passed S10
(STATUS; D63, D66, D59). **Even with a GPU, the experiment cannot be run meaningfully on the study's present
families.** Building the families is the first cost (§10).

## 6. Evaluation

**Episodes.** On every held-out task, each model makes k attempts with the first request alone (`u1`) and k with the
first request and the correction (`final`), as the fresh attempts did (protocol §15.4). The scaffold, budget and sandbox
are the same for every model. A two-turn replay, which delivers the correction after the model's first attempt as the
original sessions did, would be closer to a session; the study's tooling does not have one yet (extension X1).

**Judges.** The selecting verifier is never the only judge.

* **Confirmatory: human labels,** two reviewers per family with adjudication, from a blinded review packet
  (`tracecontract review-packet`) extended to hide the model condition. Without human labels the confirmatory analysis
  is not run, as in the precision plan §1.
* **Secondary: rule D19,** the held-out families' reference checks and regression norm, and **the independent labeler**
  (second labeling, protocol §15.5).
* **Reported only, never an endpoint:** the held-out families' own C1, C3 and the other conditions. A model trained on
  C3-filtered data may learn the style of the generated tests. The reference checks are not independent of C3 either:
  by the study's procedure they come from the same model family, the same reference diff and requirement lists that
  cover the same requirements (paper, Section 2.3). That is why human labels are the standard.

**Endpoints, per held-out family f and model m** (each the mean over m's training seeds, over every attempt, as solve
rates are counted under protocol §15.4):

* **E1, for H1 and H2:** the share of m's `u1` attempts whose label is invalid with a violated correction requirement
  (negative type `correction_violating`).
* **E2, for G1:** the share of m's `final` attempts labelled valid.
* **E3, for G2:** the share of m's `u1` attempts whose violated reference requirements are all first-request
  requirements (negative type `initial_violating`); an attempt that also breaks a correction requirement counts in E1
  only.
* **E4, for G3:** the share of m's `u1` attempts labelled valid; an attempt that is invalid of any type, or ambiguous,
  is not valid.
* **Descriptive:** the regression-only, other invalid and ambiguous shares; each condition's verifier outcomes on the
  held-out attempts; and the admitted sets of the stage-0 pool, gated and ungated.

**Analysis,** under the study's reporting rules for new runs (protocol §15.7, §16.6):

* the per-family table is the primary display;
* each paired difference, for example d_f = E1(C1-trained) − E1(C3-trained), is tested with the exact sign-flip test at
  the one-sided α the owner fixes (the precision plan uses 0.025), with its attainable floor reported. The unit of the
  test is the held-out repository: the differences of a repository's families are averaged into one, as in the study's
  repository-clustered view (`tracecontract.analysis.REPOSITORY_RULE`; D64, decision 10), since families of one
  repository are not independent. With one family per repository, the unit is the family;
* intervals are obtained by inverting the test (precision plan §2);
* no pooled rate is presented as an estimate below the number of repositories that the simulation of O1 sets.

**What counts.** A positive result needs H1 rejected, every guardrail met (G1, both tests of G2 and both of G3), and
the direction the same for each training seed. Anything else is reported as what it is: a null is a null.

## 7. Safeguards for stage 2

* **Reward verifiers.** Only process-separated verifiers serve as rewards: C1 and C3 under `tc-harness/0.3.5`, each
  behind the cell gate (§2). The probe suite of the grading boundary (`STATUS.md`, "Tested") is re-run under the harness
  the stage uses before stage 2 starts. Within one call, code that the snippet runs still controls what the call
  reports. The verifiers' tests therefore assert on returned values (the in-call limit; D3, D36, D40), and stage 2 adds
  no verifier that does not.
* **Exporting the environments.** The study's task export (`tc-harbor-export/0.3.0`) was validated under harness 0.3.5
  with an oracle (reward 1.0), a wrong candidate (0.0), the no-op (0.0) and two probes whose candidate code writes its
  own reward file, neither of which received a reward (D52). It is re-validated before any RL run uses it.
* **Monitoring.** At fixed intervals, a fixed sample of rollouts is graded with the training families' reference checks
  and independent labeler, which are not rewards. The stop rule reads, for each condition, only the reference checks
  of requirements that both of the study's model mappers map to the condition's own contract and neither marks as
  contradicted (`map` and `contradicts` in `tasks/*/contracts/mapping_*.json` and `mapping2_*.json` for the controlled
  tasks, with the reference checks' `spec.json`): if the reward rises while their pass rate on the same rollouts falls,
  by a margin fixed before
  stage 2, stage 2 stops for both conditions at the same update, the checkpoints are kept, and the stop is reported.
  The pass rate on the requirements a condition's contract does not cover (for C1, those the correction introduced) is
  a stage-2 outcome, reported and never a stop; so is the pass rate on requirements that only one mapper maps or that
  a mapper marks as contradicted. Rollouts that write to protected test paths are counted. The patch
  policy removes those changes before grading.

## 8. Records to save

Every record is kept as the run records of the study are: hashed, with its code revision, never edited after the fact.

* **Data manifests.**
  * The pool's run directory (manifest, results, analysis).
  * The data step's selection manifest for each condition: admitted ids with the cell gate and without it, the cells
    the gate drops and why, counts, the rules, and the hashes of every input and of the code.
  * The seeded subsample of each condition's budget.
  * The SFT example files with their hashes.
  * The per-attempt audit's records, its check of each training example's content among them.
  * The held-out split, its seed and the map from family to repository.
* **Model revisions:** the base model's identifier and revision, the tokenizer's hash, and every checkpoint's hash.
* **Hyperparameters:** each stage's configuration, hashed before the stage.
* **Seeds:** sampling, data order, training, RL rollouts and evaluation.
* **Checkpoints:** the end of each stage, and fixed intermediate steps named before the stage.
* **Evaluation records:**
  * every graded pair of every model on every held-out task, with the harness version and three repeats;
  * the D19 labels, the second labeling and the human labels;
  * the review packet's key, kept by its coordinator.
* **Logs:** losses, rewards, KL, the share of groups whose rollouts all got the same reward, the stage-2 monitoring
  sample and every stop.
* **Accounting:** GPU hours per stage and condition, tokens sampled and trained, and money spent.
* **Decision log:** entries before (plan adopted, split, configurations, margins) and after (results, every deviation).

## 9. Post hoc illustration: what each filter admits from the `fresh-v1` attempts

**Post hoc, exploratory (not pre-specified).** Generated by `python scripts/build_training_selection.py --config
configs/downstream/rft_selection_v0.1.json` into `results/analyses/fresh-v1-training-selection/` (`selection.md`,
`selection_manifest.json`). It was built from the run's records alone and regenerates byte for byte. Every selected
pair's origin, outcome, label and negative type match the run's `analysis.json`, and so do the excluded attempts and
the cells that its oracle-gated view drops.

**What was selected.**

* **Attempts:** the 79 attempts that the run's analysis keeps. One of the 80, `CS-02-fresh-A-final-1`, is excluded by
  its reviewed audit: it wrote and read back helper files of its own in the build session's scratch directory, and the
  recorded reason is the analysis' generic text (D62). The 4 references are not attempts.
* **Acceptance:** each pair was graded three times, and no pair is unresolved or ended in an infrastructure outcome.
* **The cell gate:** `fresh-v1` graded no no-op, so only the gate's reference part applies, which is the run's
  oracle-gated view. C1 and C2 fail CS-01's reference (`task_failure`), so the gate drops their CS-01 cell; it keeps
  every other cell.
* **Labels:** rule D19's proposals. No attempt has a human label.

Each cell gives the total, then the counts of CS-01, CS-02, CS-03 and CS-04. The totals are sums, not estimates. The
gated rows are the data filters; the ungated row describes C1's verifier.

| | Attempts | Invalid (D19) | Correction violators | Regression-only | Valid |
| --- | --- | --- | --- | --- | --- |
| Every kept attempt (the pool) | 79 (20, 19, 20, 20) | 29 (10, 2, 7, 10) | 27 (10, 0, 7, 10) | 2 (0, 2, 0, 0) | 50 (10, 17, 13, 10) |
| C1 `initial_plain`, gated: naive-data filter | 51 (0, 17, 14, 20) | 14 (0, 0, 4, 10) | 14 (0, 0, 4, 10) | 0 (0, 0, 0, 0) | 37 (0, 17, 10, 10) |
| C1 `initial_plain`, ungated (descriptive) | 61 (10, 17, 14, 20) | 24 (10, 0, 4, 10) | 24 (10, 0, 4, 10) | 0 (0, 0, 0, 0) | 37 (0, 17, 10, 10) |
| C3 `full_plain`, gated: correction-aware filter | 52 (10, 19, 13, 10) | 2 (0, 2, 0, 0) | 0 (0, 0, 0, 0) | 2 (0, 2, 0, 0) | 50 (10, 17, 13, 10) |
| C2 `initial_audited`, gated (ungated as C1's) | 51 (0, 17, 14, 20) | 14 (0, 0, 4, 10) | 14 (0, 0, 4, 10) | 0 (0, 0, 0, 0) | 37 (0, 17, 10, 10) |
| C4 `full_audited` | 46 (10, 19, 7, 10) | 2 (0, 2, 0, 0) | 0 (0, 0, 0, 0) | 2 (0, 2, 0, 0) | 44 (10, 17, 7, 10) |
| B2 `llm_freeform` | 50 (10, 19, 11, 10) | 2 (0, 2, 0, 0) | 0 (0, 0, 0, 0) | 2 (0, 2, 0, 0) | 48 (10, 17, 11, 10) |
| B1 `repo_tests` | 16 (2, 0, 4, 10) | 0 (0, 0, 0, 0) | 0 (0, 0, 0, 0) | 0 (0, 0, 0, 0) | 16 (2, 0, 4, 10) |

The gate drops no cell of C3, C4, B2 or B1, so their gated and ungated sets are the same. No admitted attempt is
ambiguous or of another invalid kind, and no two kept attempts of a task share a graded patch.

**The gate's lost yield.** It removes C1's 10 CS-01 admissions, all of them correction violators; C1 admits none of
CS-01's 10 valid attempts, since its contract encodes the part of the first request that the correction retracted
(D62). Gated C1 admits 14 of the 19 invalid attempts of the three families it keeps and rejects 3 of their 40 valid
ones, which are D62's gated FA of 14/19 and FR of 3/40.

**By instruction variant and configuration.**

* **The pool.** Every invalid attempt is a `u1` attempt: 29 of the 40 `u1` attempts, and none of the 39 `final` ones.
  The `u1` attempts are 20 of configuration A and 20 of B.
* **C1, gated.** It admits 25 `u1` attempts (0, 8, 7, 10), 14 of them invalid, and 26 `final` attempts (0, 9, 7, 10).
  Ungated, it admits 35 `u1` attempts (10, 8, 7, 10), 24 of them invalid.
* **C3.** It admits 13 `u1` attempts (0, 10, 3, 0), 2 of them invalid, and all 39 `final` attempts.
* **Configurations.** Of the `u1` attempts each filter admits, gated C1 holds 12 of configuration A and 13 of B
  (ungated, 17 and 18), and C3 holds 8 and 5.
* **Yield under the plan's default pool.** The default pool holds `u1` attempts only (§2). Of these 40, gated C1 would
  admit 25 from three families, 14 of them correction violators, and C3 would admit 13 from two families, 2 of them
  regression-only. The matched budget T of §4 would then be the token count of those 13 attempts.

**Caveats.** These numbers describe this pool and nothing beyond it.

* **The contrast is subtractive.** Among the `u1` attempts, both filters keep the same 11 valid ones, 8 in CS-02 and 3
  in CS-03. C3 admits no `u1` attempt that C1 rejects except CS-02-fresh-A-u1-4 and -u1-5, the two regression-only
  attempts, which the second labeler calls valid. C1 adds the violators: 14 gated, 24 ungated. So "a set filtered by
  C3 reinforces attempts that met the correction" is as true of C1's set; the filters differ only in whether the
  violators are in; under §4's matched budget the trained conditions would also differ in how many of the 11 shared
  attempts fit C1's subsample. CS-02 has no correction violator, and its initial-only contract already covers
  everything its correction adds (paper, Section 3; D62, item 2). C3 admits no `u1` attempt in CS-01 or CS-04, whose
  corrections include keeping a default unchanged, so no admitted attempt here shows that behaviour. The 3 CS-03
  attempts meet a correction that keeps all-caps input and two other functions as they were at the base commit
  (`tasks/CS-03/contracts/reference.json`).
* **B2 admits what C3 admits.** On this pool B2 admits the same 13 `u1` attempts as C3 (`selection_manifest.json`;
  the full admitted sets differ only in CS-03-fresh-B-final-1 and -final-4, which C3 admits and B2 does not), so the
  illustration cannot separate the contract from whole-session generation.
* **The invalid share follows the study's design.** Half the attempts withheld the correction by design: 40 of the 80
  saw only the first request (protocol §15.4), and every invalid attempt is among them. The C1 against C3 contrast is
  largely fixed by construction: each violator breaks a requirement that only the correction states, which C1's contract
  lacks and C3's covers, and the reference checks that label the attempts were written from a reference contract that
  states it (paper, Section 3; D80).
* **The attempts are honest attempts, not optimised against any verifier.** Fresh attempts get no verifier, reference
  or label (protocol §15.4). Under the optimisation pressure of stage 2, the share of admitted attempts that exploit a
  verifier's gaps can only be measured, not inferred from these counts.
* **The labels are model proposals,** not human labels (D19). The independent labeler agrees with D19 on 77 of 79 units
  (D61), and the two it disputes are the two regression-only attempts that C3 admits. Both pass all 28 reference checks
  and the labeler. They are invalid only because a base test asserts on a private attribute that both deliberately
  removed (D62). The label rule also calls an attempt valid when no reference check exercises its violation (paper,
  Section 2.3), so every valid count here holds only for what those checks exercise.
* **The primary audit rule only.** The selection follows the run's primary rule, the reviewed audit verdicts. The run's
  sensitivity view (protocol §18.1; `analysis_sensitivity.md` in the run directory) also excludes the 25 other attempts
  that the automated audit flagged, CS-02-fresh-A-u1-4 among them. D61 gives that view's FA as 18/21 for C1 and 1/21
  for C3. The selection is not recomputed under that view.
* **The admitted sets differ by configuration** (above), so in this pool the filters also change the mix of the two
  agent configurations. In the planned experiment, one base model makes the whole pool (§2).
* **Nothing here measures training value.** The selection says which attempts a filter would admit, not what training on
  them would do. These attempts are not training data for this plan either:
  * they are on the four development families (§5);
  * they were made by the study's agent configurations, not by a base model to be trained;
  * the repository holds only their final patches, and their transcripts are private run records.
* **Four families; counts only.** No rate here is an estimate of anything.

## 10. Run limits and costs

**Run limits.**

* **Before anything runs:** the owner approves the spending; a protocol version adopts this plan and is hashed; the
  held-out families are frozen; and the split, the configurations and the margins are logged.
* **Fixed in advance (owner fields):** k; S; the minimum token budget and an optional cap (T itself is derived, §4); the
  stage-1 steps; the stage-2 updates, rollouts per update and the rollout-token cap; the checkpoints kept; and the
  evaluation's k.
* **Stopping:** no stage is extended or stopped on the endpoint. A stage stops early only on a stop rule: an
  infrastructure failure, the reward-hacking rule of §7, or a budget cap. Every stop is reported.
* **Sandbox:** every attempt and every grade runs offline in the study's sandbox, as `fresh-v1` did.

**Costs.** Every amount is a field for the owner. A grounded figure is given only where a record supports one, and each
estimate says what it rests on.

| Item | Basis in the records | Estimate | Owner field |
| --- | --- | --- | --- |
| Base model, licence, storage of checkpoints | none | none | owner |
| Building a family (contracts, verifiers, reference checks, labeler) | `natural-pr-v1`, `analysis.md`, "Cost and time per accepted task". Included, per accepted task: 947.7 agent turns, 1,178.0 tool calls and 32,404.9 s of agent wall time from each family's 26 generation records: its 3 contracts; its 8 verifiers other than B1 (C1 to C4, B2, B3, the reference checks and the labeler; the records of C2 and C4 combine their generators and revisers, D64); and its 15 constructed candidates, namely the 10 development candidates of the C2 and C4 audits (four attacks and one valid alternative per variant, D64) and the constructed held-out pool (two valid alternatives and three near misses), which this plan does not need. That table does not separate them. Recorded apart: S10, 1,239.5 s per accepted task (every family S10 processed, both samples), and the run's grading, 2,598.9 s. Not recorded: tokens, stages S1 to S9, S10 re-runs, image builds, the host's own steps and agent runs without a generation record (the mappers among them) | Estimate: about 32,400 s of agent wall time per family as the natural arm built them, the development candidates and the constructed held-out pool included, plus about 1,240 s of S10 and the unrecorded parts | owner |
| Sampling the pool (k attempts per task) | The 80 `fresh-v1` attempt records report 183,712,045 tokens in all, the sum, over each attempt's assistant responses, of the recorded usage: input, cache-creation input, cache-read input and output tokens, as the attempt records define it (`definitions.tokens`), so cache reads are included; and medians of 24 to 24.5 turns (configuration A) and 11 to 13 (configuration B) per attempt | None for a base model of the owner's choice: these attempts used other models | owner |
| Grading the pool and the evaluations | `fresh-v1`: 672 pairs, each three times, in 9,141 s from start to end; the pairs' wall times sum to 9,134.2 s (so the pairs were graded one at a time), a median of 8.98 s per pair, at most 174.1 s (a B1 pair). `natural-pr-v1` (`analysis.md`, "Cost and time per accepted task" and "Build and replay reliability"): 432 pairs, 72 per family, whose wall times sum to 15,593.4 s, from 421.5 s (NP-04) to 6,146.5 s (NP-19) per family | Estimate, on two bases, one pair at a time on this host: about 13.6 s per pair on `fresh-v1`'s controlled families, so about 109 s for an attempt's eight pairs (six conditions, the reference checks and the labeler); about 36.1 s per pair on `natural-pr-v1`'s families, from about 5.9 s (NP-04) to about 85.4 s (NP-19) by family, so about 289 s for eight pairs | owner |
| SFT and RL compute (GPU hours) | none: no training has run | none | owner |
| Human labels of the evaluation | Precision plan §9 (assumed times, not measurements): setup 10 / 15 / 30 minutes per task; reading the user turns at 200 / 150 / 100 words per minute and the contract at 150 / 100 / 70; contract review 2 / 3 / 5 minutes per requirement decision; per item 6 / 10 / 20 minutes, plus 2 / 5 / 10 in the sandbox and 0.1 / 0.2 / 0.4 per changed line; two reviewers per task; adjudication of 10 / 20 / 35% of items at 10 / 15 / 25 minutes each | Items per held-out task: at most (1 + 2S) × 2 × k, for the base model and S seeds of each trained condition, two variants and k attempts each (attempts that share a graded patch are one item), at those assumptions | owner |

## 11. Open decisions (owner)

* **O1.** The downstream power simulation, the number of training and held-out repositories and families, the margins
  of G1, G2 and G3, and α.
* **O2.** Whether to run the experiment at all, its spending and its compute.
* **O3.** The base model, its licence and revision, and where checkpoints are kept and whether they are released.
* **O4.** The pool's source (on-policy, the default, or a stronger agent) and its instructions (`u1` only, the
  default; or both variants, with budgets matched per variant).
* **O5.** k, S, the minimum token budget and its cap, the rollout-token cap, and the stage configurations.
* **O6.** The sources of new families, and whether pull-request review comments count as user corrections (D47).
* **O7.** The human reviewers and the annotation budget.
* **O8.** Whether stage 2 runs, and the extensions: X1, the two-turn replay; the unfiltered-pool arm; and RL without
  stage 1.

## What this draft is not

It is not a result, not a claim that correction-aware training helps, and not a promise that it will. No training was
run, and the configuration is a tested configuration of a planned step, not an experimental result. Protocol v0.12 and
the study's frozen records are unchanged.
