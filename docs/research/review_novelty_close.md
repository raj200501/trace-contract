# Novelty review A (close reading): do the full texts of the closest works refute the D25 claim?

Reviewer role: novelty skeptic A (close reading). Access date for every source: **2026-11-13 (UTC)**.
Scope: SessionFarmer/CropChat (arXiv 2611.02440), VerifierBench (2610.28679), traj2envs (GitHub `huggingface/traj2envs` + HF `harness-hub/traj2envs-rl`), PersonaCodeBench (2611.05739), SWE-Together (2606.29957), ARE-bench (2611.14364), AfterVibe (2607.09900). Because brief §3.2 bullet "Human ground truth" also makes claims about TraceDance (2609.33295) and TestJack (2610.10619), and the brief's own §2.1 cites RealClawBench (2606.03889) on human-labelled scorer errors, those three were checked by targeted reading of the relevant sections only.

Claim under test (decision log D25 / brief §3.1): a pre-specified, verifier-level counterfactual measurement of correction-attributable FA and FR: verifiers produced by one frozen procedure from initial-only vs correction-aware contracts, with and without a predefined audit, plus repository tests and a full-session LLM baseline, all scored on one frozen, held-out candidate pool whose anchor negatives are the agent's own pre-correction states (rejected by the user in the session), with independent valid alternatives and near misses, against independent human labels (with the model-proposed vs human label discrepancy reported).

Conventions
- Quotes are verbatim, at most two sentences, with the section named. Numbers that arXiv HTML renders as MathML are written as plain digits. Curly apostrophes are normalised to straight ones.
- **TRUE** / **FALSE** / **OVERSTATED** refer to the brief's sentence as written. **INFERENCE** marks my own reasoning or arithmetic.
- All downloads (untrusted data, not committed) are under `/home/user/tc_review_dl/novelty_close/` (one folder per arXiv ID with `abs.html`, `full.html`, `full.txt`; `traj2envs/repo` is a shallow clone at HEAD `a09204ed`; `traj2envs/hf` holds the HF API JSON, card, `sources.json` and two `task.toml` files).
- No project file other than this one was modified.

---

## 0. Bottom line

1. **The D25 conjunction is not refuted.** None of the seven works, read in full, builds verifiers from initial-only vs correction-aware inputs with one frozen procedure, scores them on a held-out pool anchored on the session's own user-rejected pre-correction state, and grades them against independent human candidate labels. The claim survives **only in its full conjunctive form**; every component except "verifiers from initial-only vs correction-aware contracts, scored on the user-rejected state" has a close precedent.
2. **Four of the five "why the argument does not fully hold" bullets in brief §3.2 are inaccurate in part:**
   - **"Held-out discipline on session-derived tasks" is FALSE as stated** (high). SessionFarmer's Table 3 replays a fixed set of held-out evaluation rollouts (not used in construction) against its pre- and post-refinement suites on session-derived tasks; the rollouts labelled correct are independent valid solutions. Its labels are LLM labels, which is the real gap.
   - **"Session-native negatives" is OVERSTATED** (medium). traj2envs `extend` calibrates tests to fail on the agent's own end-of-previous-request state, and ARE-bench calibrates its judge on "the original agent's output", which "later turns often show ... fell short". Neither is a held-out, labelled negative, which is what survives.
   - **"Human ground truth" is OVERSTATED and partly FALSE** (medium). TraceDance does have human pass/fail labels on candidate responses (contradicting the brief's own §2.1 row), ARE-bench has author review of every failed item, PersonaCodeBench reports accept/reject accuracy and precision/recall against adjudicated expert labels, and RealClawBench reports FP/FN of two scorer conditions against human labels on 281 session-derived cases.
   - **"Verifier-level counterfactual"**: the SessionFarmer statements are TRUE, but "Its Appendix D lists that analysis as future use" misdescribes App. D (agent-side analyses only), and the bullet omits the two closest verifier-scope counterfactuals (ARE-bench Table 8 with its "latent items discovered through subsequent rework"; PersonaCodeBench's same-run native vs persona verifiers).
   - **"FA/FR trade-off"** numbers are TRUE.
3. **Design-level precedents the brief should state explicitly:** (a) SessionFarmer Table 3 is already a paired "with vs without predefined audit, same held-out pool, FPR/FNR/BAcc" comparison (the C3 vs C4 form), with LLM labels; (b) traj2envs `build` writes initial-request-only tests and *requires* them to accept the agent's end-of-first-request state, i.e. it instantiates SF Data's V8 failure mode by construction (supports the motivation; no measurement); (c) for the controlled-session pilot, PersonaCodeBench (frozen later-disclosed requirements, same-run native vs persona verifiers, expert-labelled online assessments of in-session states) is the closest precedent; (d) AfterVibe's regeneration test (a blind agent implements from the recovered spec alone) is the recipe precedent for "independent valid alternatives written from the contract".

---

## 1. Sources read

| Work | Primary source(s) | Version / date (from `citation_*` metas and submission history) | Depth in this review |
|---|---|---|---|
| SessionFarmer (Lu, Zeng, Lan, Xu, Bao, Yan, Lin, Ren), "Harvesting SWE Benchmarks from Wild Vibe Coding Sessions" | https://arxiv.org/abs/2611.02440 ; https://arxiv.org/html/2611.02440 | v1 Mon 2 Nov 2026 03:02:59 UTC (only version); CC BY 4.0 | Full: §1–§5, App. A.1–A.6, B.1, B.3, C.1–C.5, D, E.1–E.5 (references and the repository-composition and cost tables skimmed) |
| VerifierBench (Yin, Chen, Wang, Sun, Jin, Song, Zhang) | https://arxiv.org/abs/2610.28679 ; html (v2) | v1 19 Oct 2026; v2 30 Oct 2026 | Full: abstract, §1–§2, §3.1, §3.4, §4 intro, §5–§7, Limitations, App. A, B (B.1–B.4), C, D intro; full-text grep for human/annotat/manual (no human labelling found) |
| PersonaCodeBench (Wang, Hou, Shen, ... 30 authors) | https://arxiv.org/abs/2611.05739 ; html | v1 3 Nov 2026 | Full: abstract, §1–§2.4, §3.1–§3.2, §3.5, §4–§5, App. A, D (D.1–D.6), E; grep of remaining sections |
| SWE-Together (Wu, Zhao, Li, Lee, Zhu, Wu, Yu, Li, Zhang, Fan, Li; Meta) | https://arxiv.org/abs/2606.29957 ; html | v1 29 Jun 2026 (only version); HTML body says "date: September 30, 2026" (UNRESOLVED, as in the brief) | Full main text (§1–§5) |
| ARE-bench (Lin, Ren, Xu, Sha, ... 27 authors) | https://arxiv.org/abs/2611.14364 ; html | v1 10 Nov 2026 | Full: abstract, §1–§3, §4.2.2, §4.6, Limitations, Ethics, App. A, D, E (text); §4.1/§4.3–§4.5 skimmed |
| AfterVibe (Paltenghi, Chandra; "Affiliation: Meta, USA") | https://arxiv.org/abs/2607.09900 ; html | v1 10 Jul 2026 | Full main text (§1–§7), Data Availability, App. A.1 prompts |
| traj2envs (tool) | https://github.com/huggingface/traj2envs (shallow clone) | HEAD `a09204ed` 2026-11-05 "add license" | README, `docs/how-envs-are-built.md`, `families/build.py`, `families/extend.py`, `mutants.py`, `gate.py` |
| traj2envs-rl (suite) | https://huggingface.co/datasets/harness-hub/traj2envs-rl | sha `191a751b…`; created/modified 2026-11-06; `license: other` | API JSON, card, `sources.json`, two `extend` `task.toml` files. Counted from the file list: 270 tasks = 253 `build`, 6 `extend`, 11 other (repair). Sources: 242 of 267 files from `TeichAI/Ox-Alpha-Pi-Traces` |
| TraceDance (Min, Zhang, Zeng, ... 16 authors) | https://arxiv.org/abs/2609.33295 ; html | v1 27 Sep 2026 | Targeted: §5.1–§5.3, App. C.2 |
| TestJack (Yao, Wang, Sen, Chen, Ray, Song) | https://arxiv.org/abs/2610.10619 ; html | v1 7 Oct 2026 | Targeted: abstract, §1–§2 grep, appendix sentence on precision/recall |
| RealClawBench (Lv, Li, Tan, ... 10 authors) | https://arxiv.org/abs/2606.03889 ; html (v3) | v1 2 Jun; v2 5 Jun; v3 28 Aug 2026 | Targeted: App. F (Table 11) |

Re-check of the brief's residual risk: SessionFarmer's code and data are **still not publicly reachable** on 2026-11-13 (HF API for `ByteDance/SessionFarmer-CropChat` → HTTP 401; raw GitHub README → 404; `git ls-remote` asks for credentials).

---

## 2. The four checks requested

### Check 1. Does any work build verifiers from the initial request only and measure how often they accept what the user later rejected?

**Answer: No.** Three works come close in form, and the brief should name them.

- **SessionFarmer: statement coverage only.** §4.3: "we rerun statement authoring on all 34 multi-session tasks and a stratified sample of 20 single-session tasks from CropChat under 3 evidence conditions—First message, First session, and Full episode—and audit each generated statement against an independent reference requirement ledger constructed from the full episode and gold patch." No test suite is ever generated from the first-message statement. App. D confirms this: "the statements written from the opening message in RQ1 already show how much such initial inputs omit." Who built the ledger (human or LLM) is not stated anywhere (grep for ledger/human/annotat/manual).
- **traj2envs `build`: initial-only tests, calibrated to accept the end-of-first-request state, with no measurement.** `families/build.py` docstring: "The reference is the agent's Python project at the end of the trajectory's first request." It continues: "A test is kept only if it passes on the reference (twice) and fails on both the stub and an empty workspace; together the kept tests must catch most mutants of the reference." INFERENCE: when the second user message is a correction, the `build` verifier is *required* to score 1.0 on the state the user then corrected. That is SF Data's V8 failure mode by construction. traj2envs neither detects nor measures it.
- **ARE-bench Table 8: a verifier-scope counterfactual with deliveries and verdicts held fixed, LLM-judged.** §4.2.2 (RQ2.2): "To examine these gaps, we hold actor deliveries and item-level judge verdicts fixed and change only the checklist items included in ISR." Table 8 caption: "The second scope adds inherited + anchored, while the full checklist also includes latent items discovered through subsequent rework but inferable at the task cut point." Values: 69.33/69.33/69.78 (contract + norm) → 40.00/31.56/28.44 (+ inherited and anchored) → 39.56/30.67/28.00 (full).
  - INFERENCE (arithmetic): adding the rework-derived "latent" items lowers ISR by only 0.44, 0.89 and 0.44 pp. This is the closest published number to a "correction-attributable" verifier effect.
  - It differs from D25 on every axis: fresh actor deliveries, not the user-rejected original output; a checklist subset, not separately generated verifiers; an LLM judge; a research domain; "Requirements raised only in later turns and personal preferences are excluded" (§3.2.2).
- **PersonaCodeBench D.3: same-run native vs persona verifiers.** D.3: "Thus, 179/874=20.5% of complete native-test passes fail the recorded persona criteria." And: "This is descriptive discrimination, not evidence that all 179 judgments are correct or that evolved requirements causally reduced performance."
  - The native verifier is the source benchmark's own verifier, not one built from an initial-only contract.
  - The later requirements are synthetic and were disclosed to the agent.
  - The persona verdicts mix deterministic checks and LLM judges.
- **VerifierBench, SWE-Together, AfterVibe: no initial-only verifier.**
  - VerifierBench has no sessions: "We draw tasks from open-source agent benchmarks with executable evaluation procedures, each supplying an instruction, an environment, and a source verifier" (§2.2).
  - SWE-Together keeps later requirements in the rubric and has no initial-only arm.
  - AfterVibe's RQ6 compares the human-authored summary with its spec as the *regeneration input*, not as a verifier source.

### Check 2. Does any work use human labels for candidate correctness when reporting verifier FP/FN or FA/FR?

**Answer: Yes, in a partial form, in one of the seven (PersonaCodeBench) and in two works the brief itself cites (TraceDance, RealClawBench).** None does this for executable verifiers of session-reconstructed coding tasks, or across contract-source conditions.

- **SessionFarmer: LLM labels only.** Table 3 caption: "Test suite verdicts evaluated against independent gpt-6-astra patch correctness labels on 30 CropChat tasks where refinement modified the initial suite (87 labeled rollouts per solver after excluding 3 uncertain patches), alongside 2 reference benchmarks (150 rollouts from 50 tasks each)." Humans audited episodes, not patches (§4.4): "Each task was independently reviewed by 2 engineers across 56 total reviews in pipeline order: episode boundaries, attributed sessions, task statement, and quality rubrics, stopping early in 4 reviews where upstream boundary or session disagreements occurred."
- **VerifierBench: construction labels.** Limitations: "As detailed in Appendix B, V4V excludes 45 tasks with confirmed source defects, but agreement between construction labels and reference decisions does not certify that every label is semantically correct." The full-text grep found no human labelling.
- **PersonaCodeBench: human expert labels for verifier (requirement-evaluator) decisions, with FP/FN-type metrics.**
  - D.6: "Two software engineering experts independently annotate each case as Satisfied, Unmet, or Unresolved, with disagreements resolved through a separate adjudication process."
  - D.6: "When reduced to the operational accept/reject decision, agreement increases to 77.2%, with a Matthews correlation coefficient of 0.541. Notably, Satisfied judgments achieve 89.2% precision and 74.5% recall, indicating that most accepted requirements are also supported by expert review."
  - INFERENCE: 1 − recall = 25.5% of expert-Satisfied judgments were not accepted (an FR analogue), and 1 − precision = 10.8% of accepted judgments lack expert support.
  - The unit is a requirement-level judgment, not a whole candidate. The sample is 148 judgments, "including 126 online and 22 final assessments", on persona obligations.
- **ARE-bench: human review of every failed item, used inside the construction loop and not reported as rates.** §3.2.3: "In human review, the task author checks every failed item. A task proceeds to peer review only when each failure is a valid item that the actor genuinely missed." For judge reliability, §4.6.1: "Independent human annotations are the next step for attributing disagreements and completing the evidence on judge reliability."
- **SWE-Together: humans judge only the simulator.** §3.3: "We evaluate whether human annotators can distinguish simulated users from real users." No human candidate labels.
- **AfterVibe: no human labels.** §5: "Our oracle is LLM-generated, so the test suite could encode hallucinated or trivial behavior."
- **traj2envs: no human step.** README: the LLM "only proposes questions, contracts and tests". The trial matrix is automated.
- **TraceDance (named in brief §3.2): human candidate labels exist.** §5.3: "To assess the reliability of automated grading, we compare the judge panel's pass/fail decisions with those of human annotators." App. C.2: "The judge panel recovers 60.7% of human passes, and 44.7% of its passes are also human passes." Cohen's κ is 0.40 for the panel vs 0.31 between annotators, on 84 instances.
- **TestJack (named in brief §3.2): no human ground truth.** Appendix: "Recall and precision in RQ2–RQ4 measure agreement with the per-trial audit rather than with a human-labeled ground truth."
- **RealClawBench (cited in brief §2.1): human-labelled FP/FN of two scorer conditions on the same 281 session-derived cases.**
  - App. F: "We compare human judgment with the RealClawBench full-evidence LLM auditor and an output-only LLM judge baseline on the final benchmark."
  - App. F: "It also reduces false-positive done from 21.0% to 4.2% and false-negative done from 64.9% to 12.3%, supporting execution-aware LLM auditing for stateful agent tasks."
  - The audited scorers are LLM auditors, not the deterministic verifiers: "The main leaderboard uses case-specific rule-based programmatic verifiers rather than LLM judges."

### Check 3. Does any work use the agent's own pre-correction state, from a real or controlled session, as a held-out negative?

**Answer: No, not as a held-out negative.** But two works put the agent's own earlier state, or the original agent output, into a *construction-time* audit or calibration set. A third has expert labels on in-session intermediate states.

- **traj2envs `extend` (agent sessions; mostly distillation traces in the published suite).** `families/extend.py` docstring: "The task starts from the files at the end of request k (dependencies installed) and gives the agent request k+1."
  - Calibration: 'a "new" test passes on the reference (twice) and fails on the start state'. The trial matrix requires `do_nothing` (the start state) to score 0.
  - INFERENCE: when request k+1 is a correction, the start state *is* the agent's pre-correction state. It is used as a construction-time filter, so its FA is 0 by construction. traj2envs does not classify whether k+1 is a correction.
  - The published suite has 6 `extend` tasks, built from generated traces. One examined task's request reads "Add dry-run output and rollback guidance."
- **ARE-bench (real researcher sessions).** §3.2.3: "Calibration scores three deliveries with the checklist judge. The original agent's output, when available, tests whether each verdict cites evidence present in the delivery." Then: "It calibrates the judge rather than serving as an answer key, because later turns often show that it fell short."
  - So the original agent's output at the cut point, which is often what the user later corrected, sits in the judge's calibration set.
  - It is not held out, not labelled as a negative, and no acceptance rate on it is reported.
- **PersonaCodeBench (controlled simulated sessions).** Of the 148 expert-labelled judgments, 126 are online assessments of the agent's intermediate in-session state. §1: "Unmet obligations elicit feedback."
  - INFERENCE: these are labels on pre-feedback states. But the party that rejects the state is the evaluator itself, the requirement was already known to that evaluator, and no omission counterfactual exists.
- **SessionFarmer: the base checkpoint and constructed mutants, not intermediate states.**
  - §3.4 criteria check: "(ii) it must fail on the unmodified base repository in at least 1 test scenario targeting the requested changes".
  - §3.4 mutants: "Meanwhile, at the end of task authoring, the Task Author constructs a set of requirement-breaking mutants: variants of the gold patch where each mutant deliberately breaks exactly 1 requirement clause from the statement, serving as negative controls that mimic incomplete or shortcut solutions [18]."
  - Tasks keep only base and final states. §1: "An episode pairs the repository state before the work (base checkpoint) and after the work (final checkpoint) with the full transcripts of the confirmed sessions; the diff between the two states serves as the reference implementation (gold patch)."
- **VerifierBench: constructed "base" cases.** App. C: "The category records how a test case was constructed and its intended positive or negative outcome; V4V checks the assigned label against the source verifier before the test suite is fixed." The base row reads: "Uses an initial, unrepaired, or otherwise unfinished outcome; tests recognition of basic task failure."
- **AfterVibe: the parent commit.** §4.7: "Each task keeps its own oracle (verification conditions and test commands) but is graded against the repository state before the task's code was landed (the parent commit)."
- **SWE-Together: none.** The evaluated agents' own pre-correction states exist during simulator replay but are never scored as candidates.

### Check 4. Does any work score a frozen, held-out pool containing independent valid alternatives on session-derived tasks?

**Answer: Yes. SessionFarmer does, with LLM labels.**

- §4.4: "To evaluate our test refinement pipeline (Section 3.4) when it actively modifies candidate tests, we audit 30 CropChat tasks where refinement triggered suite revisions, replaying the 3 gpt-5.5 and 3 terra Codex rollouts per task against both the initial ungated suite and the final calibrated suite." The next sentence: "Following the protocol of DeepSWE [13], an independent frontier judge, gpt-6-astra, labels each patch's functional correctness across 87 non-ambiguous rollouts per solver (Table 3)."
- **The pool is held out.** Construction used a different solver, per §3.5: "multi-turn agent roles (Environment Builder, Task Author, Test Author, and the solver) run in the Pi harness [9] powered by gpt-5.6-sol".
- **The pool contains independent valid alternatives.** §4.4: "Without refinement, initial LLM-written tests frequently over-constrain implementation details from the gold patch, causing conditional false-negative rates (FNR) of 68.0% for terra and 80.9% for gpt-5.5."
- **What it lacks relative to D25** (INFERENCE):
  - labels are gpt-6-astra, not human;
  - no constructed alternatives and no constructed near misses in the pool;
  - no pre-correction state in the pool;
  - tasks were selected *because* refinement changed the suite (30 of 242), which conditions the measured audit effect.
- **VerifierBench** has frozen hidden pools with `overstrict_trap` alternatives ("Uses an alternative implementation or execution path; tests acceptance of valid alternatives."), but its tasks are not session-derived.
- **AfterVibe** has independent regenerations ("A fresh LLM instance—with no access to the original code C or conversation T —receives only the spec S and is asked to implement the artifact from scratch.", §3.4). They are scored only by its own three-tier verifier, and its RQ5 control pool has no alternatives.
- **ARE-bench, SWE-Together, PersonaCodeBench and traj2envs** have no such pool. PersonaCodeBench's D.2 fixtures (30 valid and 93 invalid handoffs) are construction-audit fixtures: "The 133 targeted fixtures are not independent sampled tasks."

---

## 3. Verdict on each "why the argument does not fully hold" bullet (brief §3.2, lines 394–403)

### B1. "Verifier-level counterfactual" (line 395)
- "SessionFarmer measures first-message information only as statement coverage." **TRUE** (§4.3 quote in Check 1).
- "It never builds verifiers from the opening request and asks how often *those* verifiers accept what the user later rejected." **TRUE** (no first-message test suite anywhere; App. D quote in Check 1).
- "Its Appendix D lists that analysis as future use." **FALSE as stated (mis-citation).** App. D lists *agent-side* analyses:
  - "Because the Task Author cites the user turns that support each requirement clause, one can test whether the requirements missed by evaluated agents concentrate on those disclosed after the opening message."
  - "Giving an agent only the opening message or early turns, paired with a user simulator that answers from later turns, yields underspecified variants of each task that measure whether agents proactively ask for missing requirements [30]; the statements written from the opening message in RQ1 already show how much such initial inputs omit."
  - The third future use compares pushback turns with autonomous trajectories.
  - No verifier-FA analysis is proposed.
- **Omission.** The bullet should name the nearest verifier-level counterfactual analyses (Check 1): ARE-bench Table 8, including its latent-item increment of ≈0.4–0.9 pp ISR; PersonaCodeBench D.3 (20.5%); traj2envs `build`. It should also say why each is not the D25 design.

### B2. "Human ground truth" (line 396)
- "SessionFarmer's FP/FN rest on gpt-6-astra labels." **TRUE.**
- "VerifierBench uses construction labels and says they do not 'certify that every label is semantically correct'." **TRUE.**
- "TestJack ... ha[s] no human candidate labels." **TRUE.**
- "traj2envs ... ha[s] no human candidate labels." **TRUE.**
- "ARE-bench ... ha[s] no human candidate labels." **OVERSTATED.** The task author reviews every failed item in actor runs (FR direction). No independent labels and no rates are reported.
- "TraceDance ... ha[s] no human candidate labels." **FALSE.** Two annotators score the evaluated LLM's response on 84 instances, and judge-panel precision and recall against human passes are reported.
  - This **contradicts the brief's own §2.1 row** (line 116: "84 human-rated instances: judge κ 0.40 vs inter-annotator κ 0.31").
  - INFERENCE: 55.3% of judge-panel passes are human fails.
- **Omission.** The bullet omits the two works that *do* report grader accept/reject errors against human labels:
  - PersonaCodeBench D.6 (expert adjudication; accept/reject 77.2%, MCC 0.541, Satisfied precision 89.2% and recall 74.5%);
  - RealClawBench App. F (281 session-derived cases; FP-done 21.0% → 4.2% and FN-done 64.9% → 12.3% across two scorer conditions on the same cases).
- **What survives:** no work reports FA/FR of *executable verifiers of session-reconstructed coding tasks* against independent human candidate-level labels, and none compares contract-source conditions that way.

### B3. "Session-native negatives" (lines 397–401)
- Sub-claims:
  - SessionFarmer's mutants are constructed and used in the loop: **TRUE** (§3.4 quotes).
  - VerifierBench's "base" cases are constructed: **TRUE** (App. C quote).
  - AfterVibe's "pre-change" is the parent commit: **TRUE** (§4.7 quote).
  - TellOnce v1: **not checked in this review.**
- Headline "No audit pool found contains the agent's own pre-correction state that the user rejected in the session": **OVERSTATED.**
  - traj2envs `extend` puts the agent's own end-of-request-k state into its calibration set and trial matrix as a must-fail negative.
  - ARE-bench puts the original agent's output, which later turns often show fell short, into its judge-calibration set (Check 3 quotes).
  - INFERENCE: traj2envs `build` does the opposite. It uses the end-of-first-request state as the *positive* reference.
- **What survives:** no work uses the user-rejected pre-correction state as a *held-out, labelled* negative, scored against verifiers frozen before it was seen.

### B4. "Held-out discipline on session-derived tasks" (line 402)
- "No session-derived study found scores a frozen pool, never used in construction, that also contains independent valid alternatives." **FALSE as stated.** See Check 4 (SessionFarmer §4.4, §3.5, Table 3).
- The brief's own §2.1 SessionFarmer row is more accurate ("Lacks ... held-out session-native pre-correction negatives and constructed valid alternatives"). So does the cluster note `newest_closest.md` §8 point 4 ("Its evaluation rollouts are separate, but the labels are LLM-generated"). The §3.2 bullet dropped that nuance.

### B5. "The FA/FR trade-off is real and under-measured" (line 403)
- **TRUE.** §4.4: "Closed-loop refinement cuts FNR by 34.0 and 32.0 percentage points for terra and gpt-5.5, respectively; while relaxing overly rigid assertions increases conditional false-positive rates by 16.2 and 17.5 points, the large reduction in false negatives raises balanced accuracy by 8.9 points for terra and 7.2 points for gpt-5.5, placing SessionFarmer's refined suites within the verification accuracy range of SWE-Bench-Pro and DeepSWE."
- The paper's own heading sentence is "Test refinement substantially reduces false rejections at the cost of higher false acceptances."
- Caveats worth adding (INFERENCE): the numbers come from 30 tasks selected because refinement changed the suite, with 87 rollouts per solver and LLM labels.

---

## 4. Other inaccuracies or omissions found while checking

1. **The audit-effect comparison form is precedented.** SessionFarmer Table 3 compares "w/o refinement" and "SessionFarmer" suites on the same held-out rollouts, reporting FP, FN, FPR, FNR and BAcc. This is the form of the pre-specified C1 vs C2 and C3 vs C4 comparisons (brief §3.1), with LLM labels. Steelman item 1 mentions Table 3 but not that it is a paired, same-pool with/without-audit comparison.
2. **Steelman item 6 (line 386)** says "omitting historical requirements". Table 8's second scope adds "historical and material or workspace requirements" ("inherited + anchored"), and the full checklist adds "latent items discovered through subsequent rework". The §2.1 ARE-bench row (line 111) also omits:
   - the latent column;
   - the original-agent-output calibration;
   - the task author's review of every failed item.
3. **§2.1 SessionFarmer row (line 104)** attributes a `superseded_requirements` field to the statement.
   - In the paper it is part of the *episode-reconstruction* output. App. A.2: "For each proposed episode, the LLM supplies the included confirmed sessions, surviving requirements, superseded requirements, completion evidence, a behavioral verification plan, and the relevant implementation hunks."
   - The Task Contract schema (App. E.3) records scope decisions in `source_resolution_notes`.
   - Minor.
4. **§3.3 item 2 (line 418)** says "Prior session-derived work did not measure this against human labels". RealClawBench App. F reports a false-negative "done" rate (an FR) of two scorer conditions against human labels on session-derived tasks, and TraceDance reports judge recall of human passes. The qualifier "on independent valid alternatives" keeps the sentence defensible, but it should name these works.
5. **Controlled-population precedent.** For the controlled sessions (CS-v1, the only population currently available, decision log D25 last sentence), the closest precedent is PersonaCodeBench, not SessionFarmer:
   - frozen later-disclosed requirements ("Requirements and their acceptance meanings are fixed before evaluation, while their disclosure and activation evolve according to the agent's progress and the prescribed interaction policy", §2.2);
   - same-run native vs persona verifiers (D.3);
   - expert labels on online in-session assessments (D.6).
   - INFERENCE: a controlled automated pilot with proposed labels adds little over PersonaCodeBench unless it delivers human labels *and* the generated initial-only vs correction-aware verifier contrast.
6. **Alternative-generation recipe.** AfterVibe's regeneration test (a blind agent implements from the recovered spec alone; §3.4) is the published recipe closest to TraceContract's "valid alternatives written from the reference contract by separate agents without the reference diff". The brief should cite it as the recipe precedent.

---

## 5. Per-work close-reading notes (what bears on D25)

### 5.1 SessionFarmer / CropChat (2611.02440 v1)
- **Correction-aware statements.** Per-clause provenance; still-effective clarifications and withdrawals are included (App. E.3 prompt: "include still-effective clarifications, necessary conditions and withdrawals").
- **Verifier construction.** Tests are LLM-written by a Test Author who sees the statement, base, gold and session context (App. A.5). There are two loops:
  - a criteria check: gold passes 3 times, base fails, every mutant is caught;
  - solver-based refinement against one blind gpt-5.6-sol solver whose patch is labelled by the Test Author's own semantic review (App. E.4: "Tests pass + incorrect submission is a false positive; tests fail + correct submission is a false negative.").
- **Audit of verifiers.** Table 3 (see Checks 2 and 4). The 30 tasks are conditioned on the refinement having modified the suite.
- **Human involvement.** Four original engineers audited 28 CropEnterprise tasks: boundaries, sessions, statements and rubrics. There were no patch labels.
- **First-message condition.** Statement coverage only (26/54/75% full coverage; App. B.3 gives 75.0% / 78.0% for rerun full-episode statements and 75.3% / 79.7% for the released statements).
- **Pushback labels.** These come from the source sessions and appear only in solver-outcome Table 17. §C.4 says "these labels describe the source conversations and do not establish a causal effect on solver success".
- **Artifacts.** Still not reachable (§1 above).
- **D25 components covered:** reconstruction (A), correction-aware statements (B), executable LLM tests (C), a held-out with/without-audit pool with natural valid alternatives (D, LLM labels).
- **D25 components not covered:** initial-only verifiers, pre-correction anchors, constructed alternatives and near misses in the scored pool, human candidate labels.

### 5.2 VerifierBench (2610.28679 v2)
- Fig. 1 caption: "The agent receives the instruction and environment used for ordinary task solving and generates one verifier, which is fixed before it is scored on multiple positive and negative test cases."
- The suite has 4,993 cases in 9 categories: 1,566 PASS and 3,427 FAIL; `overstrict_trap` has 504 cases and `base` 222.
- Labels are construction labels checked by replay against source verifiers. Limitations: "Scores measure agreement with retained reference verifiers on finite, constructed test suites."
- No sessions, no corrections, no human labels.
- Covers the held-out pool with valid alternatives, near misses and unfinished states for non-session tasks, which D25 already concedes.

### 5.3 traj2envs (tool `a09204ed`; suite `191a751b`)
- Families: `build` (the first request; the reference is the end-of-first-request project), `extend` (request k+1 from the end-of-request-k state), `repair` and `qa`.
- The audit is a predefined trial matrix plus AST-mutant kill rates (`build` ≥0.6, `extend` ≥0.5).
- No human labels and no FA/FR.
- In the suite, 242 of 267 sources come from `TeichAI/Ox-Alpha-Pi-Traces`; there are 6 `extend` tasks.
- Two D25-relevant facts:
  - `build` forces acceptance of the possibly-rejected first-request state (Check 1);
  - `extend` uses the agent's own prior state as a construction-time negative (Check 3).

### 5.4 PersonaCodeBench (2611.05739 v1)
- Native tasks are paired with synthetic persona obligations. The obligations are frozen before evaluation and disclosed progressively by a controller-governed simulator.
- Two final verifiers: native completion, and persona (deterministic checks plus GPT-6 Luna judges).
- D.3: 20.5% of native passes fail persona criteria (descriptive, LLM-involved).
- D.6: expert-adjudicated labels on 148 requirement judgments (Check 2).
- §3.5 ablation: without personas, Joint pass rises from 19% to 45%. "PersonaCodeBench w/o Persona removes the persona profile, persona-specific communication style, added obligations, and associated judges and grading."
- There is no reconstruction from real sessions and no constructed valid alternatives. The only valid fixtures are 30 handoff-format fixtures for one checker.

### 5.5 SWE-Together (2606.29957 v1)
- 109 tasks from 11,260 sessions (48 from SWE-chat).
- Agents start from the first user message, and a simulator replays later intents. §1: "Each task includes the restored repository, the user's initial request as the first-turn instruction, and task-specific artifacts derived from the recorded session, including decomposed user intents and trigger conditions for each feedback turn."
- Correctness includes later requirements (§2.3 quote). The motivation is stated in §2.3.1: "Execution-only scoring can also miss requirements introduced later in the interaction, fail to exercise behavior that depends on realistic repository context, or reject valid alternative implementations."
- Validation: the reference patch passes 73 of 93; Intent Coverage is 0.68–0.72; the Turing test gives 46%.
- No FA/FR, no candidate labels, no initial-only verifier, no held-out pool. The brief's statements about it are accurate.

### 5.6 ARE-bench (2611.14364 v1)
- Real researcher sessions. Each task is cut at a request; Background summarises earlier requests still in effect; the workspace is replayed to the cut.
- The rubric policy uses later feedback only to sharpen inferable items, and "Requirements raised only in later turns and personal preferences are excluded."
- The judge is an LLM. Cross-judge agreement is 92.76% with κ 0.717. Human reviews of failed items happen inside the loop.
- The original agent's output is used in judge calibration (Check 3).
- Table 8 is a same-delivery, same-verdict scope counterfactual (Check 1).
- **This is the most important omission in brief §3.2.** It is the only work that reports a number for the verifier-scope effect of rework-derived requirements with deliveries held fixed. The effect is small (≤0.89 pp ISR), which is informative for the TraceContract null-result discussion (§3.3).

### 5.7 AfterVibe (2607.09900 v1)
- An LLM spec is distilled from conversation plus diff. Requirements include "the developer's prompts, corrections, and accepted behaviors" (§3.1).
- Verification conditions and flex tests are extracted from the conversation and validated on the landed code. The VC prompt (App. A.3) covers "behavior, scope, user corrections, or acceptance criteria".
- Negative controls (Table 4, conditioned on the 72 tasks whose correct code passes both graders): partial 47.0% / 42.4%, pre-change (parent commit) 0.0% / 58.0%, wrong 1.4% / 51.4%.
- §4.7: "The flex-test grader drops to 42% on partial code but remains elevated on pre-change (58%) and wrong code (51%)—because many test commands pre-exist the change and can pass on unrelated code that happens to compile (e.g., “build the target”)."
- No human labels, no correction ablation, data internal (prompts only).

---

## 6. Component matrix (D25 components × closest works; my reading)

Legend: **Y** = done; **P** = partial or analogous form; **–** = not done. The numbers in parentheses refer to Section 2 checks.

| D25 component | SessionFarmer | VerifierBench | traj2envs | PersonaCodeBench | SWE-Together | ARE-bench | AfterVibe |
|---|---|---|---|---|---|---|---|
| Session-derived tasks | Y | – | Y (mostly generated traces) | – (synthetic personas on benchmarks) | Y | Y (research) | Y |
| Verifiers from initial-only vs correction-aware input, one frozen procedure | – (statements only) (1) | – | P (`build` initial-only; no correction-aware twin) | P (native vs persona verifiers on the same runs) | – | P (checklist-scope subsets, fixed verdicts) | – |
| With vs without predefined audit, same pool | P (Table 3, LLM labels) | – (V4V audits sources) | P (trial matrix and mutants as gates; no with/without scoring) | – | – | – | – |
| Repository tests and full-session LLM baseline as comparison arms | – (the pipeline is itself a full-session LLM reconstruction; no repository-test arm on the same tasks) | – | – | P (native benchmark tests vs persona verifier) | P (repository test commands plus generated gates, not compared) | – | P (flex tests from developer-run session commands) |
| Frozen held-out pool | Y (rollouts) (4) | Y | – | – | – | – | – |
| Pre-correction state as anchor negative | – | – (constructed base) | P (construction-time negative in `extend`) (3) | P (online states, evaluator-rejected) | – | P (judge calibration) (3) | – (parent commit) |
| Independent valid alternatives and near misses in the pool | P (natural alternatives; mutants in the loop) | Y | – | P (fixtures) | – | – | P (regenerations, unlabelled) |
| Independent human candidate labels | – | – | – | P (requirement-level, expert-adjudicated) (2) | – | P (author review of failures, in the loop) | – |
| Model-label vs human-label gap reported | – | – | – | P (κ 0.473; accept/reject 77.2%) | – | – ("next step") | – |

INFERENCE: every row has at least a partial precedent. The **conjunction** of rows 2, 5, 6 and 8 (generated initial-only vs correction-aware verifiers, a frozen held-out pool, the user-rejected pre-correction state as anchor, human candidate labels) appears in no work read here.

---

## 7. Suggested replacement text for brief §3.2 "Why the argument does not fully hold"

- **Verifier-level counterfactual.**
  - SessionFarmer measures first-message information only as statement coverage (§4.3) and never generates tests from it. Its App. D proposes only agent-side uses of later-disclosed requirements.
  - The nearest verifier-level analyses differ in kind:
    - ARE-bench Table 8 holds deliveries and LLM verdicts fixed and narrows the checklist scope. Adding rework-derived "latent" items changes ISR by ≤0.89 pp;
    - PersonaCodeBench compares its native and persona verifiers on the same runs (20.5% of native passes fail persona criteria; LLM-involved; synthetic requirements);
    - traj2envs `build` writes initial-request-only tests but calibrates them to *accept* the end-of-first-request state.
  - None generates verifiers by one frozen procedure from initial-only vs correction-aware contracts and scores them on the state the user rejected.
- **Human ground truth.**
  - SessionFarmer (gpt-6-astra), VerifierBench (construction labels), TestJack (per-trial audit) and traj2envs (none) score verifiers without human candidate labels. ARE-bench's authors review failed items only inside its construction loop.
  - Human-labelled grader errors do exist, for LLM judges and auditors and for requirement-level judgments, not for reconstructed executable verifiers:
    - TraceDance: 84 instances; judge-panel precision 44.7%, recall 60.7%;
    - RealClawBench App. F: 281 session-derived cases; FP-done 21.0% → 4.2% and FN-done 64.9% → 12.3% across two scorer conditions;
    - PersonaCodeBench D.6: 148 expert-adjudicated requirement judgments.
- **Session-native negatives.**
  - Agents' earlier states appear only as construction-time material: traj2envs `extend` requires its tests to fail on the agent's end-of-previous-request state, and ARE-bench calibrates its judge on the original agent's output. No work holds the user-rejected pre-correction state out as a labelled negative against verifiers frozen before it is seen.
  - SessionFarmer's mutants, VerifierBench's "base" cases and AfterVibe's parent-commit controls are constructed or pre-task states.
- **Held-out discipline.**
  - SessionFarmer already scores a fixed pool of held-out evaluation rollouts, including LLM-labelled-correct alternatives, against its pre- and post-refinement suites (Table 3), with LLM labels, on 30 tasks selected because refinement changed the suite.
  - No session-derived study scores a frozen pool that also contains the session's own pre-correction state and constructed alternatives and near misses, against independent human labels.
- **The FA/FR trade-off** (unchanged; numbers verified).

---

## 8. Limitations of this review

- Not read: TellOnce, Hacker-fixer, SWE-ABS, Trace2Eval, VibeSWEBench (outside this task's list). B3's TellOnce sub-claim is therefore unverified here.
- TraceDance, TestJack and RealClawBench were read only in the sections relevant to B2.
- Figures were not inspected. Numbers come from the HTML text and tables. Text was converted from arXiv HTML with a local converter, so whitespace around inline math differs from the rendered page.
- traj2envs: no trajectories or task test files were opened beyond two `task.toml` files. Whether any of the six `extend` requests is a correction was not determined; the one examined is a feature extension.
- Papers announced after 2026-11-11 were not searched (out of scope for close reading).
