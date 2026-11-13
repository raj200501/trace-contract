# TraceContract (working name): research brief

**Status: DRAFT - pending adversarial verification**

- Access date for every source in this brief: **2026-11-13 (UTC)**. Publication and version dates are recorded separately (tables below and §9).
- Inputs: the nine cluster notes in `docs/research/notes/` (`sfdata.md`, `trace2eval.md`, `swechat.md`, `harbor.md`, `verifier_fidelity.md`, `env_synthesis.md`, `corrections.md`, `training_and_datasets.md`, `newest_closest.md`); the project's own records (`docs/decision_log.md`, `experiments/protocol.md` v0.2, `docs/data_card.md`, `docs/annotation_guide.md`, `STATUS.md`, `README.md`); and primary sources re-opened in this synthesis step (marked **[re-checked]**).
- This brief adds no claim that is not in those notes, those project records, or a source re-opened here. Planning numbers that are our own assumptions are labelled **ASSUMPTION** (§7). Open or conflicting points are marked **UNRESOLVED**.

## 0. Executive summary

TraceContract asks how often a verifier for a coding task reconstructed from an agent session accepts a solution the user rejected because a later user correction was dropped during reconstruction (false acceptance, FA), and how many valid alternative solutions the remedies reject (false rejection, FR). The problem itself is not new: SF Data's public essay (byline 2026-10-01) states that "Preserving the initial prompt alone may produce a task that rewards precisely the behavior the user rejected", but gives no method, data or measurement. Most building blocks are also published: real or agent sessions converted into executable tasks (Trace2Eval, SWE-Together, SessionFarmer, traj2envs, REAP, AfterVibe, RealClawBench, Terminal-Universe); correction-aware task statements with per-clause provenance, plus a first-message vs full-episode coverage comparison (SessionFarmer, 2026-11-02); LLM-written tests refined against mutants and audited for false positives and negatives, but against LLM-assigned patch labels (SessionFarmer); held-out verifier scoring on pools of valid alternatives, near misses, unfinished states and attacks, with construction labels (VerifierBench); adversarial hacker-fixer hardening with held-out attackers; and two-sided verifier metrics on labelled pools in algorithmic coding (CodeContests+, HardTests). In the sources reviewed, no work runs the verifier-level counterfactual proposed here. The search was not exhaustive, and the closest papers are days old. That counterfactual has four parts: verifiers produced by one frozen procedure from initial-request-only vs correction-aware contracts, each with and without a predefined audit; repository tests and a competent full-session LLM baseline as comparisons; scoring of all of them on one frozen, held-out candidate pool whose anchor negatives are the agent's own pre-correction states, alongside independent valid alternatives and near misses; and independent human labels as ground truth. This narrower measurement claim (decision log D25) is the one this brief supports. Task reconstruction, correction-aware statements, mutation-based and held-out verifier audits, and two-sided metrics must be cited as prior work, not claimed. The primary natural data source, SWE-chat, is blocked until the repository owner accepts its terms. It is released under ODC-BY 1.0 and gated with automatic approval that shares the requester's Hugging Face username and e-mail. Its expected yield is pilot-scale (tens of tasks). AIDev-pop, pi-share-hf sessions and Trace Commons are the ranked alternatives. Controlled sessions (CS-01 to CS-04, real agent runs with study-scripted corrections) are the current fallback and must be reported as a separate population. Harbor 0.25.0 supplies the separate-verifier, artifact-allowlist and regrade primitives; trusted in-container grading and network isolation must be added by us. API spend is zero by default. The binding cost is human annotation, estimated for planning at 1.5-3 annotator-hours per task family; the pilot will measure it.

### Conventions

- **VERIFIED** or a quotation: the primary source states it. Quotes are verbatim, at most two sentences, with the section named. Numbers carry their location.
- **INFERENCE**: our judgment, estimate or arithmetic, not stated by the source.
- **[re-checked]**: re-opened on 2026-11-13 in this synthesis step, by exact string match or table reading against a fresh download (copies under `<scratchpad>/dl/synthesis/`, untrusted data, not committed).
- **(abs)**: only the abstract or landing page was read. **(partial)**: targeted sections only.
- Notes pointers: [sf] `sfdata.md`, [t2e] `trace2eval.md`, [sc] `swechat.md`, [hb] `harbor.md`, [vf] `verifier_fidelity.md`, [env] `env_synthesis.md`, [cor] `corrections.md`, [td] `training_and_datasets.md`, [nc] `newest_closest.md`. [DL Dn] = `docs/decision_log.md` entry; [P §n] = `experiments/protocol.md` v0.2.
- "not stated" = the source was checked and does not say it. "not checked" = we did not look.
- Terms: **FA** = the verifier passes a candidate that independent labels mark unacceptable. **FR** = the verifier fails a candidate that labels mark acceptable. A *pre-correction state* is the agent's code state after an earlier request and before the user's correction.

---

## 1. Industry problem statement (SF Data)

### 1.1 Sources used

| Source | URL | Date shown | Notes |
|---|---|---|---|
| SF Data homepage ("San Francisco Data") | https://www.sfdata.com/ | No content date; footer "© 2026 SF Data"; HTTP `last-modified: Thu, 12 Nov 2026 15:30:09 GMT` (deploy time, not a content date) | [re-checked]; sha256 of today's copy equals the one recorded in [sf] (`8278cb39…`) |
| Essay "Production traces and the future of data", byline Brandon Guo, Faiz Siddiqi | https://www.sfdata.com/blog/production-traces/ | `<time datetime="2026-10-01">October 1, 2026</time>`; HTTP `last-modified: Wed, 11 Nov 2026 05:37:13 GMT` | [re-checked]; sections "Why production traces matter", "Turning traces into training data", "Building a market for production traces", "The future of data"; sha256 equals [sf] (`9c4e7748…`) |

- Revision history is **not verified**. The byline date and the last-modified header differ, and web.archive.org was unreachable from this environment [sf §4]. All quotes are from the version served on 2026-11-13.
- The sitemap lists only these two URLs, and no other SF Data blog post exists as of 2026-11-13 [sf §1].
- Only these two pages are used here. Other public company pages recorded in [sf] are not needed for the problem statement.

### 1.2 VERIFIED public statements (all [re-checked] by exact string match)

| # | Statement (verbatim) | Page, section | Problem it names |
|---|---|---|---|
| V1 | "San Francisco Data turns production traces into RL environments." | Homepage, intro | Business framing |
| V2 | "As models surpass human intelligence, we believe the best training data comes from where models fail on real work, not from tasks built to break them." | Homepage, intro | Preference for naturally occurring failures |
| V3 | "We define a production trace as the chronology of AI working on a real task." | Essay, "Why production traces matter" | Definition |
| V4 | "Having only a finished artifact often leaves this gap impossible to reconstruct." | Essay, "Why production traces matter" | Why traces, not final artifacts |
| V5 | "Turning traces into high quality training data that verifiably improves models is a challenging and open research problem." | Essay, "Turning traces into training data" | Framing |
| V6 | "The first problem is identifying sessions that contain something worth learning." / "A failed attempt may reveal a broken environment rather than a model limitation." | same | P1 session selection; failure attribution |
| V7 | "This requires recovering the user’s explicit and implicit objectives, including requirements introduced through later corrections, and enough of the original environment for another model to attempt the work." | same | P2 reconstruction |
| V8 | "Preserving the initial prompt alone may produce a task that rewards precisely the behavior the user rejected." | same | P2; this is TraceContract's hypothesis, stated without data |
| V9 | "A missing input or unavailable service can make an otherwise valuable trace unusable without further augmentation." | same | P2 environment |
| V10 | "Existing tests may overlook an important constraint, and naïve user approval is not always evidence of correctness." | same | P3 verification |
| V11 | "A verifier must capture the behavior the user actually needed and resist attempts to exploit the evaluation. Otherwise, additional training can make a model better at passing the grader without improving its ability to do the work." | same | P3 verification; reward hacking |
| V12 | "The value of this work ultimately depends on the capabilities it produces." / "Internal post-training experiments help establish which data improves performance on new tasks and which merely add volume." | same | P4 downstream training value |
| V13 | "Production sessions often contain customer information and proprietary material so permissions and appropriate filtering inform which tasks we can construct." | Essay, "Building a market for production traces" | Permissions and filtering |
| V14 | "The majority of economically valuable traces generated today come from coding agents, and that’s where we are beginning." | Essay, "The future of data" | Domain focus |

### 1.3 VERIFIED absences (as of 2026-11-13; checked in [sf §2.9])

- No method, algorithm, prompt, schema or task format for reconstruction or verification.
- No definition of "implicit objectives", and no procedure for detecting "requirements introduced through later corrections".
- No verifier type (tests, judge, rubric) and no audit procedure.
- No quantitative result: no FA or FR rate, no session or task counts, no post-training numbers. The essay mentions internal experiments but reports no results.
- No public code, dataset, benchmark or paper. Pages are marked "© 2026" and state no open licence.
- False rejection of valid alternative solutions is not named explicitly. The verification paragraph names missed constraints, unreliable user approval and exploitation. Reading "capture the behavior the user actually needed" as also covering over-strict verifiers is our interpretation, not the essay's text.

### 1.4 INFERENCES about relevance (ours, not SF Data's; nothing here describes SF Data's internal methods)

| SF Data statement | TraceContract component | Coverage (INFERENCE) |
|---|---|---|
| V8 (initial prompt only rewards rejected behaviour) | Initial-request-only vs correction-aware contract factor; observed pre-correction states as candidates | Directly targeted. The claim becomes a measured FA rate on the state the user rejected |
| V7 (requirements introduced through later corrections) | Correction-aware contract; competent full-session LLM baseline (B2) | Directly targeted. B2 tests whether a careful reconstruction already recovers corrections |
| V10, first half (existing tests may overlook a constraint) | Repository-tests baseline B1 | Directly targeted |
| V10, second half (naive user approval is not evidence) | Independent human labels as ground truth | Targeted. Possible extension: compare in-session approval signals with labels |
| V11 (resist exploitation) | Predefined audit (audit:v1); tamper probes kept separate from semantic FA [P §10] | Partly. Near misses probe under-specification, not exploits |
| V12 (training value) | Not in the 2x2 | **Not covered.** State as a limitation, or add a cheap proxy (for example verifier-guided best-of-n selection scored against labels). No GPU is available [DL D2] |
| V6, V9 (broken environments, missing inputs) | Environment-validity gate; outcome classes `environment_failure` and `verifier_error` [P §6]; rejection ledger | Partly. Report attrition with reasons |
| V13 (permissions and filtering) | Authorized-session premise; redaction | Partly. Check whether redaction removes correction content a contract needs |
| V2 (failures on real work, not tasks built to break them) | Candidate origins | Supports making observed pre-correction states the primary negative class and reporting constructed near misses separately |

Novelty implications (INFERENCE):
- The problem framing is a prior public statement. TraceContract must cite it and must not claim to have identified the problem.
- Because SF Data mentions internal post-training experiments, unpublished internal evidence may exist. Any "first" claim should be limited to the first *public, reproducible* measurement, and the academic literature (§2) narrows even that claim.
- The essay's verification concerns are on the FA and exploitation side. Reporting FR on valid alternatives next to FA is a clear, two-sided extension.

---

## 2. Related-work comparison

How to read the tables:
- **Overlap** is our judgment (INFERENCE). **High** means the work covers one of the components we would otherwise claim. **Medium** means it partly covers a component or measures a closely related quantity. **Low** means shared substrate or motivation only. **None** means background only.
- **Accessed** is 2026-11-13 for every row. It is repeated because the table format requires it.
- Rows marked (abs) were read at abstract level only. Their cells say "not stated (abs)" where the abstract is silent.
- Detailed evidence is in the cluster notes named in each row.
- Components of our design used in the overlap column:
  - (A) task construction from sessions;
  - (B) preservation of later corrections as requirements;
  - (C) executable verifier;
  - (D) verifier audit on held-out, human-labelled candidates, including valid alternatives and session-native pre-correction negatives.

### 2.1 Trace- and session-derived evaluation and task construction

| Work (citation + URL) | Version/date | Accessed | Task source | Reconstruction assumptions | User corrections | Verifier type | Independent validation | Training experiments | Artifacts/license | Overlap with TraceContract |
|---|---|---|---|---|---|---|---|---|---|---|
| **SessionFarmer / CropChat / CropEnterprise**: Lu, Zeng, Lan, Xu, Bao, Yan, Lin, Ren, "Harvesting SWE Benchmarks from Wild Vibe Coding Sessions", arXiv:2611.02440, https://arxiv.org/abs/2611.02440 [nc] | v1 2026-11-02 (only version); no venue [re-checked] | 2026-11-13 | Real developer–agent sessions with commit checkpoints. SWE-chat: "5,851 sessions and 13,406 checkpoints" → 2,708 clusters → 338 episodes → 242 tasks (61 repos, 14 languages) [re-checked]. Plus 375 proprietary ByteDance sessions → 56 TypeScript tasks | Entire schema; LLM-confirmed session relevance and episode partition; base checkpoint = start state; diff to final checkpoint = gold patch; Dockerfile validated offline on base and final trees; the full transcript is kept | **Yes, at statement level.** The statement "consolidates all requirements that remain in effect at the end of the episode", with clauses citing event IDs and a `superseded_requirements` field [re-checked]. "87.6% of tasks rely on requirements added, clarified, or revised in later user turns" [re-checked]. Full coverage is 26% / 54% / 75% for first message / first session / full episode on multi-session tasks, against a reference ledger whose construction (human or LLM) is not stated. **No initial-only verifier is built** | LLM-written hidden tests refined against requirement-breaking gold-patch mutants and a blind solver (both used inside the refinement loop); LLM rubric quality gate | Against "independent gpt-6-astra patch correctness labels" (30 tasks, 87 rollouts per solver) [re-checked]: BAcc 61.9→70.8 (terra) and 53.3→60.5 (gpt-5.5); FPR 8.1→24.3 and 12.5→30.0; FNR 68.0→34.0 and 80.9→48.9. Four original developers audited 28 enterprise tasks (boundaries, statements, rubrics). **No human patch-correctness labels** | None. 12 model-harness configurations evaluated; best Pass@1 39.3% | Code and benchmark links stated (github.com/bytedance/SessionFarmer; HF ByteDance/SessionFarmer-CropChat). Neither was publicly reachable on 2026-11-13 (404/401). Paper CC BY 4.0 [re-checked]; code and data licenses not stated | **High (closest).** Covers A, B and C, and D partly (FP/FN against LLM labels). Lacks the initial-only verifier counterfactual, human labels, held-out session-native pre-correction negatives and constructed valid alternatives. Its App. D lists analysis of later-disclosed requirements as future work [re-checked] |
| **SWE-Together**: Wu, Zhao, Li, Lee, Zhu, Wu, Yu, Li, Zhang, Fan, Li, "SWE-Together: Evaluating Coding Agents in Interactive User Sessions", arXiv:2606.29957, https://arxiv.org/abs/2606.29957 [sc][cor] | v1 2026-06-29 (only version). The HTML body shows "date: September 30, 2026", **UNRESOLVED** [re-checked] | 2026-11-13 | "109 repository-level tasks from 11,260 recorded sessions": DataClaw 2,228→29, Pi-staging 2,397→23, Hyperswitch 784→9, SWE-chat 5,851→48 [re-checked] | Deterministic filter (multi-turn, agent edits, mature public repo, final change not mainly human-authored) → LLM viability screen → sandboxed task-generation agent at a pinned commit writes tests. Reference patch comes from the commit or from tool replay. Instruction = first user message | **Preserved.** Oracle intents are replayed by a reactive LLM user simulator (question, redirect, new-requirement, check-external). "Task correctness measures whether the agent’s final repository state satisfies the coding request, including requirements introduced during the interaction." [re-checked] | Harbor `test.sh` with weighted F2P gates (structural and behavioural) and P2P gates, plus a two-phase agentic rubric judge (may consult the reference patch); pass at ≥0.85 | Reference patch passes 73/93 at τ=0.85 [re-checked]; Intent Coverage 0.68–0.72; simulator Turing test 46% (CI 40.5–51.6), 4 annotators, 312 judgments [re-checked]. No human labels of verifier decisions and no FA/FR found in v1 | None (7 frontier models evaluated) | Apache-2.0 code and tasks (Togetherbench/SWE-Together @e9ce8cf); HF yifannnwu/SWE-Together (Apache-2.0). Tasks ship `original_session.json` / `oracle_session.jsonl`, i.e. session content outside the SWE-chat gate (not opened) | **High.** Covers A, B and C, and states our motivation: "Execution-only scoring can also miss requirements introduced later in the interaction ... or reject valid alternative implementations" [re-checked]. Lacks the initial-only vs correction-aware comparison, a shared held-out candidate pool and human FA/FR |
| **Trace2Eval**: Shi, Jie, Zou, Zhu, Yang, Cao, Cai, Zhang, "Trace2Eval: Contextualized Evaluation of Coding Agents from Real-World Traces", arXiv:2611.06506, https://arxiv.org/abs/2611.06506 [t2e] | v1 2026-11-04 (only version); "Preprint". The supporting-repo name suggests an ICLR submission (INFERENCE) [re-checked] | 2026-11-13 | 20,000 consented, desensitized sessions (June–July 2026) from an unnamed online coding-agent service, inferred Chinese-language → 14,603 coding traces → 300 candidates → 129 tasks [re-checked] | q is an LLM summary: "Each query summary captures the user’s objective and explicit requirements from the interaction" [re-checked]. Workspace: "files created or downloaded as part of the recorded solution are excluded from the initial workspace" [re-checked]; missing content is mocked. Environment inferred from temporal dependencies. Accepted by LLM-scored replay of recorded tool calls plus human verification. Excludes "Fragments or continuation requests whose essential context cannot be recovered." [re-checked] | **Not handled or measured** (keyword audit [t2e §5]). Pre-correction states are discarded | Agentic LLM judge (GLM-5.3-Flash) with a generic 11-dimension rubric (accuracy 50 / code quality 35 / UX 15), static plus runtime evidence, 3 rollouts. No per-task executable tests | 2 annotators plus adjudicated GT on 56 artifacts × 11 dimensions, apparently in-sample. Weighted macro κ Agent–GT 0.173 vs Human–GT 0.542 [re-checked]. "Overall usability agreement of 93.0%, compared with 92.9% for humans" [re-checked]. Recovery on calibration subsets: 38/46 workspaces accepted; mean replay 0.9175 | None. Judge-guided revision gains a mean of +10.05 pp, rescored by the same judge [re-checked] | Paper: arXiv non-exclusive licence. Anonymous repo with docs, rubric anchors and one case's prompts; no pipeline, tasks, traces or labels; no LICENSE file | **High on A** (real sessions → containerized tasks with replay validation; q ≈ a full-session reconstruction baseline). **Low on B–D**: no corrections, no executable verifiers, no FA/FR, no held-out candidate pool |
| **traj2envs** (tool) and **harness-hub/traj2envs-rl** (270-task suite), Hugging Face, https://github.com/huggingface/traj2envs ; https://huggingface.co/datasets/harness-hub/traj2envs-rl [td] | Tool HEAD a09204ed 2026-11-05, v0.1.0; suite 2026-11-06. No paper found [re-checked in local clone] | 2026-11-13 | ATIF trajectories converted from Claude Code, Codex and pi logs. The published suite comes from 267 distillation-style traces (242 from TeichAI/Ox-Alpha-Pi-Traces) | Replays Write/Edit/MultiEdit/Read/apply_patch/heredocs into a virtual filesystem; unreconstructable edits mark files lost; Dockerfiles from python:3.12 or node:22; offline trials | **No explicit handling.** `build` "replays up to the second user message" (initial-request-only); `extend` "starts from the files at the end of request k (dependencies installed) and gives the" agent request k+1 [re-checked] | LLM-written hidden pytest (reward = fraction passed; 0 if existing behaviour breaks); `repair` uses the check's exit code | Automated trial matrix: the original fix must score 1; do-nothing, tamper, stub, empty-workspace and delete-project trials must score 0. Kept tests must kill AST mutants (`MINIMUM_MUTANT_KILL_RATE` 0.6 build, 0.5 extend) [re-checked]. No human labels; the optional atif-scan gate was skipped for all 270 tasks | None reported (solve rate measured with one small model, 2 attempts) | Code Apache-2.0 (LICENSE added at HEAD); suite license "other"; pinned images | **High (engineering).** Covers A, C and an automatic audit, with initial-only (`build`) and pre-request (`extend`) variants. Lacks human labels, FA/FR, valid alternatives, a same-candidate contract comparison and real-user sessions in the suite |
| **AfterVibe**: Paltenghi, Chandra, "AfterVibe: What Remains When the Conversation Ends", arXiv:2607.09900, https://arxiv.org/abs/2607.09900 [cor][nc] | v1 2026-07-10 [re-checked] | 2026-11-13 | 72 tasks from a company's internal coding-assistant sessions over 7 days (122 candidates → 81 graded → 72) | An LLM distils an abstract NL spec from conversation plus diff. Requirements are "whatever is observable from the session (the developer’s prompts, corrections, and accepted behaviors)" | Included implicitly in the spec; no ablation | Flexible tests derived from the conversation; LLM-extracted verification conditions (VCs); ground-truth alignment | Negative controls (Table 4): on pre-change (parent-commit) code, VCs pass 0.0% and flex tests 58.0%; on wrong code, 1.4% vs 51.4%. No human labels | None | Prompts only; data internal and not released | **Medium.** Real sessions → graders that include corrections; controls expose weak-grader FA. Its "pre-change" is the parent commit, not the pre-correction state. No human labels, no correction ablation |
| **REAP / Harvest** (Meta): Jha, Paltenghi, Maddila, Murali, Ugare, Chandra, "REAP: Automatic Curation of Coding Agent Benchmarks from Interactive Production Usage", arXiv:2604.01527, https://arxiv.org/abs/2604.01527 [nc] | v1 2026-04-02 … v4 2026-07-28; "Accepted at ASE 2026 Industry Showcase" [re-checked] | 2026-11-13 | Production developer conversations with an internal coding assistant, mapped to landed monorepo diffs (mostly Hack); 132 tasks | Solution diff backed out of current master; rolling re-curation; one conversation per diff | **No, by design.** "we restrict to single-turn conversations in which a developer provides one prompt and the agent produces code changes without intermediate human feedback" [nc §3.2] | Production F2P tests found by probabilistic retrieval, filtered by an agentic relevance classifier, plus multi-run F2P validation; no LLM judge | Two author-annotators: task classifier 87.00% (κ 0.74, n=100); test relevance 86.00% (κ 0.72, n=50). No FA/FR on candidate patches | None (solve rates 42.9–58.2%) | Internal benchmark; an anonymous artifact link was not opened | **Medium.** Industrial A and C. Excludes B by design, and states that test-pass is "necessary, not sufficient" |
| **RealClawBench**: Lv, Li, Tan, Yao, Tian, Sun, Zhang, Lin, Yang, Zhao, arXiv:2606.03889, https://arxiv.org/abs/2606.03889 [cor][sc] | v1 2026-06-02; v3 2026-08-28 | 2026-11-13 | Real OpenClaw sessions → 281 executable tasks | Environments reconstructed from session evidence. "request rewriting turns the original user message into a standalone instruction"; subjective tasks removed | Not described | Deterministic programs over the final workspace and stdout; an LLM auditor is studied separately | Full-evidence LLM auditor vs human labels on 281 cases: κ 0.748; false-positive "done" 4.2% vs 21.0% for an output-only judge | None (14 models; best 65.8%) | [cor] gives github.com/openclaw/clawbench (no LICENSE at root); [sc] recorded an anonymous.4open.science link. Two different links, **UNRESOLVED** | **Medium.** A published initial-request rewrite recipe (our initial-only condition). Measures LLM-auditor FP against humans, not omitted corrections |
| **ARE-bench**: Lin, Ren, Xu, Sha, et al. (27 authors), "ARE-bench: Benchmarking Agents' Research Ability in Real-World Researcher Sessions and Workspaces", arXiv:2611.14364, https://arxiv.org/abs/2611.14364 [nc] | v1 2026-11-10 | 2026-11-13 | Agent sessions and workspaces from recruited researchers' own projects; 75 tasks; 1,173 binary checklist items | Cut at a real request; workspace replayed to the cut point; a Background section summarizes earlier requests still in effect | Partial. Earlier still-active requests are kept, but "Requirements raised only in later turns and personal preferences are excluded." [re-checked] | LLM judge over a binary checklist ("any valid alternative passes") | Judge calibration with empty and fabricated deliveries; cross-judge κ 0.717. "Independent human annotations are the next step" [re-checked] | None. Table 8 holds deliveries fixed: strict success 69.33/69.33/69.78% with contracts and norms only vs 40.00/31.56/28.44% once historical and workspace requirements are added [re-checked] | Minimum workspace content released (URL and license not extracted) | **Medium.** The closest agent-evaluation analogue of omission-induced inflation, but in a research domain, with an LLM judge and no human labels |
| **Terminal-Universe**: Wu, Zhang, Zhang, Wang, Su, Chen, Wang, Wang, Shen, Zhou, Yang, Huang, Yang, Liu (Qwen/Alibaba; Tsinghua), arXiv:2609.04148, https://arxiv.org/abs/2609.04148 [nc] | v1 2026-09-03 | 2026-11-13 | Public agent-trajectory corpora (SWE-rebench, SWE-smith, CoderForge, SWE-Gym, LFM2-Terminal, others) → 37.3k task-sufficient environments | Deterministic replay to the earliest observed file versions, agentic completion of missing files, workspace-sufficiency filter, Intent Recovery | Partial. Later requests are folded in "only when they clarify, constrain, or extend the same task"; a synthetic multi-round user adds "feature conflict" turns | Agent-authored pytest suites; trajectories kept only if all tests pass | None for verifiers. The authors note that a single teacher's errors "may also be missed by its tests" | SFT of Qwen3.5-27B: +11.9 on Terminal-Bench 2.1 (58.1%); +13.8 MT@4 on EvoCode-Bench v2 | Release not stated in the sections read | **Medium.** The same trace→environment mechanism at training scale, from agent rollouts rather than real users. No verifier audit |
| **TerminalWorld** (abs): Chu, Hu, Jiang, Zou, Li, Peng, O'Hearn, Barr, Harman, Sarro, Ye, arXiv:2605.22535, https://arxiv.org/abs/2605.22535 [t2e] | v1 2026-05-21; v2 2026-11-04; arXiv comment: accepted at NeurIPS 2026 Evaluations and Datasets Track | 2026-11-13 | 80,870 in-the-wild terminal recordings → 1,530 validated tasks in 18 categories, plus a 200-task Verified subset | "reverse-engineers high-fidelity evaluation tasks" from in-the-wild terminal recordings (details not read) | not stated (abs) | Executable tests (per Trace2Eval's description; the abstract reports pass rates) | Manual review of the 200-task Verified subset (abs) | None stated (8 models, 6 agents; best 62.5%) | Project website mentioned; not checked | **Medium (abs).** Precedent for reconstructing executable-test tasks from real recordings |
| **SecureForge**: Liu, Einstein, Yang, Baumann, Eddy, Manning, Kochenderfer, Yang, arXiv:2605.08382, https://arxiv.org/abs/2605.08382 [sc] | v1 2026-05-08 (partial) | 2026-11-13 | 203 Python task descriptions distilled from SWE-chat sessions, plus synthetic CWE-scenario prompts | Claude Sonnet 4.6 collapses user turns into one self-contained prompt: preserve every user-stated detail, carry forward standing constraints, leak no agent code, invent no requirements (App. I.7) | Folded into the single description; not evaluated separately | Semgrep CWE findings; LLM-generated pytest for the synthetic tasks (test provenance for the SWE-chat tasks not established) | Manual validation of the 203 descriptions for user intent | No weight training (GEPA prompt optimization) | not checked | **Medium.** A published template for our full-session reconstruction baseline (B2) |
| **VibeSWEBench** (abs): Islam, Ali, Du, Parvez, ICML 2026 workshop poster, https://icml.cc/virtual/2026/82740 (OpenReview id kWrudm978A) [nc] | 2026; exact date not stated | 2026-11-13 | "authentic human–agent failure sessions" on two real backend projects → 109 single-turn tasks | "Trajectory Unrolling" (details not retrieved) | Abstract claims "preserving human-authored corrective signals"; mechanism unknown | "human-validated test suites with no LLM-as-a-judge" | not stated (abs) | None stated (best 20.87%) | not stated; OpenReview blocked by a browser challenge; no arXiv version found | **Unknown, possibly Medium–High.** Must be read in full before any novelty claim |
| **TraceDance**: Min, Zhang, Zeng, et al. (16 authors; ByteDance Inc. USA; UIC), arXiv:2609.33295, https://arxiv.org/abs/2609.33295 [nc] | v1 2026-09-27 (partial) | 2026-11-13 | 252,557 deployed Claude Code and OpenClaw sessions over six weeks | Decision-point continuation from the recorded prefix; no environment replay | Not modelled as requirements | Behaviour-specific LLM rubric judge panel | 84 human-rated instances: judge κ 0.40 vs inter-annotator κ 0.31 | None (9 LLMs; mean pass 26.7%) | Code link only; traces not released | **Low–Medium.** Industrial trace → benchmark; no executable verifier; no corrections |
| **DuMateBench** (abs): Niu, Zhao, Zhang, et al. (15 authors), arXiv:2608.26546, https://arxiv.org/abs/2608.26546 [nc] | v1 2026-08-27 | 2026-11-13 | 200 tasks from "anonymized and privacy-screened user sessions" of a production agent platform | Keeps "pre-solution interaction history, persistent configurations, and workspace state"; Docker | History preserved; correction handling not stated (abs) | Hybrid deterministic checks plus LLM judge | Human verification of tasks | None stated | Code and data stated as public; license not checked | **Low–Medium.** Production sessions → tasks with history (office workflows); no verifier FA/FR |
| **EnterpriseClawBench** (abs): Zhong, Wang, Jiang, Tian, Yuan, Yang, Lei, Zhang, arXiv:2606.23654, https://arxiv.org/abs/2606.23654 [nc] | v1 2026-06-22 | 2026-11-13 | Proprietary real workplace agent sessions → 852 reproducible tasks | Recovered fixtures; rewritten prompts | not stated (abs) | Hard rules plus semantic rubrics | not stated (abs) | None stated | Benchmark data not released; protocol and code released (license not checked) | **Low–Medium.** Session → task, not code-specific |
| **SF Data essay** (industry statement): Guo, Siddiqi, "Production traces and the future of data", https://www.sfdata.com/blog/production-traces/ [sf] | Byline 2026-10-01; last-modified 2026-11-11 [re-checked] | 2026-11-13 | Production traces from partner companies' agents; coding agents first | Stated as requirements only (V7, V9); no method | Central to the argument (V8); not measured | Not stated; requirements only (V10, V11) | Not stated | "Internal post-training experiments"; no public results (V12) | None public; "© 2026" | **Medium (framing only).** No method, data or numbers (§1.3) |

### 2.2 Real-session datasets and base-rate studies

| Work (citation + URL) | Version/date | Accessed | Task source | Reconstruction assumptions | User corrections | Verifier type | Independent validation | Training experiments | Artifacts/license | Overlap with TraceContract |
|---|---|---|---|---|---|---|---|---|---|---|
| **SWE-chat**: Baumann, Padmakumar, Li, Yang, Yang, Koyejo, "SWE-chat: Coding Agent Interactions From Real Users in the Wild", arXiv:2604.20779, https://arxiv.org/abs/2604.20779 ; dataset https://huggingface.co/datasets/SALT-NLP/SWE-chat [sc] | v1 2026-04-22; v2 2026-10-01; arXiv comment "Accepted at COLM 2026" (author-controlled, not independently confirmed). Dataset revision `202b071f…`, lastModified 2026-10-03 [re-checked] | 2026-11-13 | Entire-logged sessions from public repos (v2: 17,968 session rows, 707 repos, data through 2026-09-04; about 69% Claude Code) | No tasks released. The analysis code replays file-modifying tool calls from the parent commit; "This includes 47.7% of sessions" with unambiguous commit-level attribution | LLM per-prompt pushback labels (Qwen3.5-9B; accuracy 0.67 four-class and 0.79 binary vs 100 gold labels). Corrections are about 35–38% of Claude Code prompts (read from a figure; medium confidence). "correction" mixes context fixes, misunderstandings, factual errors and requirement changes | None (descriptive). An LLM session-success score | Two author-annotators: 90-item IAA (pushback κ 0.832) plus 100 adjudicated gold labels. The authors "caution against taking these labels at face value" | None | Dataset ODC-BY 1.0, gated with automatic approval, shares HF username and e-mail [re-checked]; analysis code MIT; paper CC BY 4.0 | **Medium.** The primary natural data source and correction signal; no tasks or verifiers |
| **AIDev (v5) / AIDev-pop**: Li, Zhang, Hassan, arXiv:2507.15003 and arXiv:2602.09185; dataset https://huggingface.co/datasets/hao-li/AIDev [td] | Papers 2025-07-20 and 2026-02-09 (abs / partial); dataset v5 cutoff 2026-03-31, lastModified 2026-10-21 | 2026-11-13 | GitHub PRs authored by coding agents (7,685,281). AIDev-pop: 361,296 PRs in 25,402 repos with reviews, inline comments and commits | Not a task dataset. Code states are exact via commit SHAs. Inline review comments carry `commit_id`, `original_commit_id` and `diff_hunk`. Environments would need SWE-bench-style building (INFERENCE) | PR review comments (291,248 inline; 541,831 reviews) followed by commits, as in paper Fig. 1. Not labelled as requirement changes | None (PR merge state only) | not applicable | None in the dataset papers | CC-BY-4.0 compilation; "Each source repository retains its original copyright and license"; `repository.license` field | **Low** (as a method). A candidate data source with exact pre-correction states (§4.3) |
| **Trace Commons**: trace-commons/agent-traces, https://huggingface.co/datasets/trace-commons/agent-traces [td] | sha 112ebd4d; created 2026-06-11; last data change 2026-06-18 | 2026-11-13 | 30 donated sessions from public open-source repos (28 Claude Code, 1 Cursor, 1 opencode); raw native files scrubbed in place | Not a task dataset. No commit or remote is added; `cwd` and `gitBranch` survive scrubbing; base states not recorded | Likely present (median 10 user messages), unlabelled; data not opened | not applicable | Contributor and maintainer review; deterministic scrubber; TruffleHog flag | not applicable | CC-BY-4.0 for the compilation only. Rights rest on "the contributor's certification"; reusers must check embedded licenses. The donate-trace repo has no LICENSE | **Low.** Pilot-scale data source with the cleanest rights story |
| **pi-share-hf session datasets**, e.g. https://huggingface.co/datasets/badlogicgames/pi-mono and aggregate https://huggingface.co/datasets/MaxDevv/real-pi-coding-agent-traces-sessions [td] | 2026-04-06; aggregate 2026-07-19 | 2026-11-13 | Real pi-agent sessions donated per open-source project; the aggregate has 1,291 sessions from 21 datasets | Session header has `cwd` and `timestamp` only (no commit); the base must be matched to public history by time (INFERENCE) | Natural chat turns; tree-structured sessions with `branch_summary`; unlabelled | not applicable | Secret redaction, TruffleHog block, LLM review of relevance to the project | not applicable. SWE-Together built 23 tasks from 2,397 "Pi-staging" sessions | Varies: badlogicgames "other" with no text; thomasmustier/* MIT; aggregate "other" with per-session license | **Low.** Data source already mined by SWE-Together |
| **DataClaw datasets**: exporter https://github.com/banodoco/dataclaw (MIT); 49 tagged HF datasets [td] | Exporter undated (main); e.g. peteromallet/dataclaw-peteromallet 2026-02-24 | 2026-11-13 | Users' exported Claude Code and Codex histories | No repo URL or commit; no open-source-only rule | Present in multi-turn histories; unlabelled | not applicable | Regex and entropy redaction; user review | not applicable. SWE-Together built 29 tasks from 2,228 sessions | Typically MIT per dataset. README: "This is a performance art project." One dataset reports stats identical to another (possible re-upload) | **Low.** Weak provenance and a provider-terms risk |
| **OpenHands Feedback**: https://huggingface.co/datasets/OpenHands/openhands-feedback [td] | Created 2024-12-06; modified 2024-12-14 | 2026-11-13 | 275 publicly shared OpenHands sessions with thumbs up/down (60% positive) | Trajectory events; repo/commit fields not stated | Multi-turn messages, unlabelled except the session-level feedback | not applicable | Sensitive-information review by All Hands | not applicable | MIT | **Low.** Small and dated |
| **DevGPT**: Xiao, Treude, Hata, Matsumoto, arXiv:2309.03914; Zenodo 10.5281/zenodo.10086809 [td] | arXiv v2 2024-02-14 (abs); Zenodo 2023-11-09 | 2026-11-13 | 29,778 prompts and responses from shared ChatGPT links in GitHub and Hacker News | Linked artifacts with commit SHAs; the repo state at chat time is not recorded; ChatGPT is not an agent | Multi-turn, unlabelled | not applicable | not applicable | not applicable | CC-BY-4.0 | **Low** |
| **nebius/SWE-rebench-openhands-trajectories**: https://huggingface.co/datasets/nebius/SWE-rebench-openhands-trajectories [td] | 2025-09-22 / 2025-12-27 | 2026-11-13 | 67,074 **synthetic** agent trajectories (Qwen3-Coder-480B in OpenHands) on SWE-rebench issues; no human users | `instance_id` joins SWE-rebench Docker images; `model_patch` recorded | None | SWE-rebench F2P/P2P (`resolved`). Agent-written tests are scored by `gen_tests_correct` and `pred_passes_gen_test` | Golden-patch check of the agent tests only | SFT trajectories (blog not read) | CC-BY-4.0 plus per-repo licenses | **Low.** A source of synthetic negatives and a free FA signal for agent-written tests |
| **CooperBench/swechat-coop**: https://huggingface.co/datasets/CooperBench/swechat-coop [sc] | Created 2026-05-25; no card | 2026-11-13 | 200 task directories named after SWE-chat repos (file names only) | not stated | not stated | not stated (a per-instance `eval.json` exists) | not stated | not stated | No license, no README | **Unknown.** Possibly executable tasks derived from SWE-chat; treat as a potential threat until documented |
| **TiGanEval**: Liu, Liu, Ju, Ruan, Lei, Li, Liu, "Instructions Are Evidence, Not Objectives: Measuring Outcome Alignment of Agents", arXiv:2610.17757, https://arxiv.org/abs/2610.17757 [nc] | v1 2026-10-13 (partial) | 2026-11-13 | Existing fully specified tasks converted into partial-instruction tasks, plus a study of 100 SWE-chat trajectories | Planner/Builder/Auditor/Calibrator agents; human expert review | Base rate, human-annotated: "56% of the sampled trajectories have incomplete initial instructions"; 52.49% of useful follow-ups were inferable | Executable per-task evaluators (details not read) | Human annotators for the SWE-chat study; expert task review | None (models lose 53–67 points from full to partial instruction) | github.com/THUNLP-MT/TiGanEval (license not checked) | **Low–Medium.** Supports our premise; agent-side; no verifier audit |
| **Requirements After the First Edit**: Jiang, Cheng, Fu, Koziolek, Li, Zhang, arXiv:2609.03028, https://arxiv.org/abs/2609.03028 [nc] | v1 2026-09-02 (partial) | 2026-11-13 | SWE-chat v1 sessions | Edit-by-edit replay of file writes from a recoverable start state | Funnel: "5,851 raw sessions → 3,553 eligible → approximately 2,060 clean-start reconstructible → 402 sessions carrying at least one canonical emergence event → 921 canonical emergence events". Failure-triggered corrections are excluded, so this is a lower bound (INFERENCE) | not applicable (line-invalidation proxy) | 437 units double-coded by humans; LLM detection precision 0.78; blind audit agrees on 93 of 100 events | not applicable | Intermediate outputs released (URL and license not stated) | **Low–Medium.** Base rate (402/2,060 ≈ 19.5%, our arithmetic) and replay feasibility (~58% of eligible sessions) |
| **Anthropic Societal Impacts, "Measuring AI agent autonomy in practice"**, https://www.anthropic.com/research/measuring-agent-autonomy [cor] | Published 2026-02-18 | 2026-11-13 | Interactive Claude Code sessions (samples of 500k) | not applicable | Claude-classified interruption reasons: "To provide missing technical context or corrections (32%)", "To change requirements mid-task (5%)". These are mid-turn interruptions, not post-turn corrections | not applicable | "Our classifications are generated by Claude." Single provider | not applicable | No data released | **None** (base rates only) |

### 2.3 Executable environment synthesis (and the execution substrate)

Pattern across this group ([env §0], INFERENCE): tasks come from PRs, issues, commits or synthetic edits, never from user–agent conversations, and verifier validation is gold-only (pre-state fails, gold passes, sometimes with reruns). No paper in this group scores a fixed held-out candidate set against human acceptability labels.

| Work (citation + URL) | Version/date | Accessed | Task source | Reconstruction assumptions | User corrections | Verifier type | Independent validation | Training experiments | Artifacts/license | Overlap with TraceContract |
|---|---|---|---|---|---|---|---|---|---|---|
| **Harbor**: Harbor Framework Team, "Harbor: A framework for evaluating and optimizing agents and models in container environments", v0.25.0, DOI 10.5281/zenodo.20953922, https://github.com/harbor-framework/harbor [hb] | 0.25.0 on PyPI, wheel uploaded 2026-10-25T20:27:25Z [re-checked]. Local clone main@3bf4cb3 (2026-11-12) is ahead of it | 2026-11-13 | Tasks authored in the Harbor format (`instruction.md`, `task.toml`, `environment/`, `tests/`, optional `solution/`). Prior agent context can be seeded through ATIF `trajectory.json` | not applicable (infrastructure) | No built-in notion. Multi-turn is possible via a simulated-user agent or ATIF `extra` fields | Pluggable. `tests/test.sh` writes `reward.json` or `reward.txt`, or a custom host-side `BaseVerifier` | Our probes on 0.25.0 confirmed several behaviours: reward-file precedence; reward files deleted before verify; only declared artifacts reach a separate verifier, through a tar `data` filter; oracle candidates stay hidden; regrade works; provenance must sit in ATIF `extra` fields [hb §8] | not applicable | Apache-2.0 (PyPI license expression [re-checked]; repo LICENSE and CITATION.cff) | **Substrate by design** (see §5). No overlap with the measurement contribution |
| **SWE-smith**: Yang, Lieret, Jimenez, Wettig, Khandpur, Zhang, Hui, Press, Schmidt, Yang, arXiv:2504.21798, https://arxiv.org/abs/2504.21798 [env] | v1 2025-04-30; v2 2025-05-21; NeurIPS 2025 D&B per README. Local code @9b74ac0: author date 2026-03-21, committer date 2026-03-22 (the two notes differ only by timestamp) [re-checked] | 2026-11-13 | Synthetic bugs injected at one pinned commit per real Python repo (LM modify or rewrite, AST procedural, combine, PR mirror); 50,137 instances from 128 repos | One Docker image per repo; SWE-agent install plus manual review (>80% of tests pass); LM-generated issue text | None | SWE-bench F2P plus P2P. F2P tests are hidden by a "Remove F2P Tests" commit, and edits to test files are reverted at evaluation | No verifier-correctness measurement. Flaky tests are removed post hoc (`repair.py`) | Rejection-sampling SFT on 5,016 trajectories: 32B model 40.2% on SWE-bench Verified | MIT code and data | **Low.** Reusable AST mutators for near misses and harness logic. Needs `swebench<5` [env §2.1] |
| **R2E-Gym**: Jain, Singh, Shetty, Zheng, Sen, Stoica, arXiv:2504.07164, https://arxiv.org/abs/2504.07164 [env] | v1 2025-04-09 (only version). Local code @0d94c4e (2025-07-13) | 2026-11-13 | Real commits → 8,135 instances (Subset: 4,578 instances from 10 repos) | Semi-manual dependency search; per-commit images; problem statements back-translated from code and traces; tests generated with the ground-truth patch in context when a commit has none | None | Exact match to an expected test-status map (its own environments); F2P/P2P modes; hybrid execution-based plus execution-free verifier at test time | Toxicity (tests that pass an incorrect patch but fail a correct one; "up to 10% of total tests") and distinguishability ("less than 20% of tests" are discriminative for most problems). Both measured against hidden-test correctness, not human labels | SFT on 3,321 trajectories: 32B 34.4% pass@1; hybrid Best@26 51.0% | Code Apache-2.0 [re-checked LICENSE]; Subset and V1 data Apache-2.0; Lite untagged | **Medium.** The closest prior metric to FA of generated tests. Labels come from hidden tests; no corrections |
| **SWE-Gym**: Pan, Wang, Neubig, Jaitly, Ji, Suhr, Zhang, arXiv:2412.21139 [env] | v1 2024-12-30; v2 2025-06-06 | 2026-11-13 | Real issues and PRs: 2,438 instances from 11 repos (Raw: 64,689 instances without environments) | Dependencies configured by hand per version (~200 annotation hours; 10,000 CPU hours) | None | SWE-bench tests, plus a learned outcome reward model for reranking | Best@k vs Pass@k only (32.0 vs 42.8 at k=16) | SFT on 491 trajectories: 32B 20.6%; 32.0% with the verifier at k=16 | Repo Apache-2.0; HF data MIT | **Low** |
| **SWE-rebench**: Badertdinov, Golubev, Nekrashevich, Shevtsov, Karasik, Andriushchenko, Trofimova, Litvintseva, Yangel, arXiv:2505.20411 [env][vf] | v1 2025-05-26; v2 2025-11-04 (NeurIPS 2025) | 2026-11-13 | Issue-linked PRs → 21,336 tasks from 3,468 repos | LLM install recipes; internal mirrors; pinned freezes; tests rerun "multiple times" (count not stated) | None | SWE-bench F2P/P2P | An LLM label of test-patch correctness: "67% accuracy (weighted F1: 0.65)" against SWE-bench Verified human annotations (task level) | None (dataset plus leaderboard) | Data CC-BY-4.0; code MIT | **Low.** Static prediction of test validity is hard, which supports executed audits |
| **SWE-rebench V2**: Badertdinov, Nekrashevich, Shevtsov, Golubev, arXiv:2602.23866 [env] | v1 2026-02-27; v2 2026-06-01; ICML 2026 (comment) | 2026-11-13 | Issue-linked PRs → 32,079 tasks in 20 languages from 3,617 repos (plus 120,000+ PR-derived tasks) | Interactive setup agent per repo; images designed "so tests can run without network-dependent installs at runtime"; LLM-synthesized log parsers; full suite run 3 times, keeping only identical outcomes | None | F2P/P2P on the full test suite | Clarity judges vs SWE-bench Verified labels (F1 at most 0.50); leakage audit (23.0% of 509 tasks show some leakage); diagnostic labels such as IMPLICIT_NAMING (Gemini pass@3 34.0% vs 4.0%) | None (authors state no RL ablations) | Data CC-BY-4.0 with a per-instance repo-license field; builder code MIT | **Medium.** Documents FR mechanisms (tests that need unstated names) without human-labelled candidates |
| **SWE-Factory**: Guo, Wang, Li, Tao, Yang, Chen, Song, Tang, Zheng, arXiv:2506.10954 [env] | v1 2025-06-12; v3 2026-01-05 | 2026-11-13 | Real issues and PRs in Python, Java, JS and TS | 4-agent SWE-Builder with a memory pool; GPT-4.1-mini builds 50.2% at $0.047 per instance | None | Exit-code test script (`OMNIGRIL_EXIT_CODE`) | Three researchers labelled fail2pass logs on 1,201 instances: precision 100%, recall 98.3%. This checks status extraction on the gold patch only | Qwen2.5-Coder-14B 5.8%→21.0% on Verified | Code dual-licensed: AGPL (non-commercial) or commercial. HF Gym data has an MIT tag | **Low.** Do not copy the code (licence) |
| **SWE-Universe**: Chen, Zhang, Feng, et al. (19 authors; Qwen), arXiv:2602.02361 [env] | v1 2026-02-02; v2 2026-09-21 | 2026-11-13 | Issue-linked PRs → 807,693 environments from 52,960 repos | A building agent with switch-to-bug and switch-to-resolved tools writes `evaluation.sh`; an in-loop LLM hacking detector rejects grep-style verifiers | None | Exit code of the agent-written `evaluation.sh` | Build benchmark reported with and without hacks (e.g. 78.44% vs 82.50%); a quality judge reaches 78.72% accuracy on a human-labelled benchmark | Mid-training on 500K trajectories; Qwen3-Max-Thinking 75.3% on Verified | No release found | **Medium.** Hacking detection and buggy/fixed self-checks resemble audit checks |
| **SWE-Bench++**: Wang, Ramalho, Celestino, Pham, Liu, Sinha, Portillo, Osunwa, Maduekwe, arXiv:2512.17419 [env] | v1 2025-12-19 | 2026-11-13 | Live PRs in 11 languages → 11,133 instances from 3,971 repos | Templated Dockerfiles; three repository states; log parser validated by synthetic failure injection; gold solution run 3 times | None | F2P/P2P, with hints appended for implicit interface requirements | FP/FN test rubric; automated reviewers vs senior and lead annotators (reviewer FPR 0.154–0.615 vs human 0.308). Task level only | Small SFT additions (7B on Multilingual: 5→11 of 300) | No release found | **Medium.** Task-level FP/FN framing |
| **ScaleSWE**: Zhao, Chen, Meng, et al. (14 authors), "Immersion in the GitHub Universe: Scaling Coding Agents to Mastery", arXiv:2602.09892 [env] | v1 2026-02-10; v4 2026-03-24 | 2026-11-13 | Real merged PRs (6M) → 100k instances from 5.2k Python repos | An environment-builder agent; a unit-test-creator agent writing synthetic `f2p_script`s; a statement-writer agent; git-history sanitization against leakage | None | F2P (often synthetic) plus P2P | Expert audit of 100 random instances: 94 valid | SFT of Qwen3-30B-A3B: 22.0%→64.0% on Verified | Ambiguous: the repo LICENSE says CC BY 4.0 for the work and "dataset is licensed under CC0"; HF data has no tag | **Low.** A template for a competent test-generation baseline |
| **SWE-Hub**: Zeng, Li, Dong, et al. (14 authors; Qianfan Team, Baidu), arXiv:2603.00575 [env] | v1 2026-02-28 | 2026-11-13 | Repository snapshots: synthetic bugs, agentic regressions, hollowed repositories | Env Agent plus Test Agent; readiness means "invocable and parseable", not passing | None | P2F/P2P test partitions; hidden tests | None reported | None reported | No release in v1 | **Low** (design ideas only) |
| **RepoForge**: Chen, Zhao, Chen, et al. (12 authors), arXiv:2508.01550 [env] | v1 2025-08-03; v2 2025-09-03 (partial) | 2026-11-13 | Real commits and issues → 7,304 environments on 937 images | Multi-agent "Foundry"; image pruning | None | F2P/P2P | SPICE labels: 68.5% accuracy on test coverage (task level) | SFT then RL: RepoForge-8B 17.4% on Verified | No release found | **Low** |
| **Multi-SWE-bench**: Zan et al. (ByteDance), arXiv:2504.02605 [env] | v1 2025-04-03 (partial) | 2026-11-13 | Real PRs and issues in 7 languages: 1,632 instances, plus a 4,723-instance RL set | Manual Dockerfiles; three logs per instance (run, test, fix) | None | F2P/P2P | 68 annotators label instance validity; not candidate verdicts | Benchmark evaluation only | Code Apache-2.0; HF license "other" | **Low** |
| **SWE-Flow**: Zhang et al. (Qwen), arXiv:2506.09003 [env] | v1 2025-06-10; v2 2025-06-11; ICML 2025 (partial) | 2026-11-13 | Unit tests of real projects sliced into TDD steps (16,061 train / 2,020 test) | Treats tests as complete specs: "Unit tests enforce strict, verifiable constraints, eliminating ambiguity inherent in natural language requirements." | None | The project's unit tests | None for verifiers | SF-Coder-32B fine-tuned | Code MIT | **Low.** Useful as a contrast to our premise |
| **SWE-Dev (feature-driven)**: Du et al., arXiv:2505.16975 [env] | v1 2025-05-22; v3 2026-02-06 (partial) | 2026-11-13 | 8,000 PyPI packages → masked-function feature tasks (14,000 train / 500 test) | Docker; call trees traced from tests | None | Developer-authored unit tests | Execution validity only | SFT, PPO and DPO gains | No LICENSE found | **Low** |
| **SWE-Dev (THUDM)**: Wang, Hou, Wei, Tang, Dong, arXiv:2506.07636 [env] | v1 2025-06-09; v2 2025-06-23; Findings ACL 2025 (partial) | 2026-11-13 | Real issues and PRs with LLM-synthesized fail-to-pass tests (written via Gherkin scenarios) | Tests validated against the gold patch | None | Synthesized F2P tests plus existing tests | Indirect only (fine-tuning parity with another dataset) | 32B 36.6% on Verified | Code MIT | **Low** |
| **SWE-bench**: Jimenez et al., arXiv:2310.06770 ; card https://huggingface.co/datasets/princeton-nlp/SWE-bench [vf][cor] | v1 2023-10-10 (abs); card sha e48e2bd | 2026-11-13 | GitHub issues and the PRs that resolve them (2,294 tasks) | `problem_statement` is "The issue title and body"; `hints_text` holds "Comments made on the issue prior to the creation of the solution PR’s first commit creation date." | Not as requirements | F2P/P2P from the merged PR | not applicable | None | Card and harness MIT | **Low.** Shows the opposite asymmetry: the verifier comes from the PR, which can encode later thread decisions, so FR is the main risk (INFERENCE [cor §5.6]) |

### 2.4 Verifier adequacy, reward hacking and task review

| Work (citation + URL) | Version/date | Accessed | Task source | Reconstruction assumptions | User corrections | Verifier type | Independent validation | Training experiments | Artifacts/license | Overlap with TraceContract |
|---|---|---|---|---|---|---|---|---|---|---|
| **VerifierBench**: Yin, Chen, Wang, Sun, Jin, Song, Zhang, "VerifierBench: Benchmarking the Generation of Executable Verifiers for LLM Agents", arXiv:2610.28679, https://arxiv.org/abs/2610.28679 [nc] | v1 2026-10-19; v2 2026-10-30 [re-checked] | 2026-11-13 | 222 tasks from six existing agent benchmarks; 45 excluded, including all 37 Terminal-Bench tasks | not applicable. An agent must write a verifier that "must accept every valid solution and reject invalid ones" [re-checked] | None | Agent-generated executable verifiers | 4,993 hidden cases (1,566 PASS / 3,427 FAIL): gold, cosmetic, `overstrict_trap` (504; "Uses an alternative implementation or execution path; tests acceptance of valid alternatives"), `base` (222; "initial, unrepaired, or otherwise unfinished outcome"), partial, near_miss, regression, hack [re-checked]. Labels are construction labels confirmed by source verifiers: "agreement between construction labels and reference decisions does not certify that every label is semantically correct" [re-checked] | None. 19 models; normalized balanced accuracy 10.6–62.1; all-reject verifiers produce 87.9–96.0% of false rejections [re-checked] | Scripts and annotations Apache 2.0; upstream content keeps its source terms [re-checked] | **Medium overall; High on audit design** (held-out pools of valid and invalid variants). No sessions, no corrections, no human labels |
| **Hacker-fixer loop**: Zhong, Segal, Bercovich, Saxena, Zhang, Raghunathan, "Hardening Agent Benchmarks with Adversarial Hacker-Fixer Loops", arXiv:2606.08960, https://arxiv.org/abs/2606.08960 ; code https://github.com/few-sh/harden-v0 [vf] | v1 2026-06-08 [re-checked]; harden-v0 @342b847 (2026-07-03) | 2026-11-13 | Existing benchmarks: an audit of 1,968 terminal tasks, KernelBench L1 (100 tasks) and 77 Terminal-Bench tasks | The task instruction and reference solution define legitimacy; the fixer edits only tests and environment | not applicable | Existing outcome verifiers, iteratively patched by an LLM fixer | "323 (16%) hackable by frontier models given only the task description". Held-out stronger blind attackers plus a public hint corpus. Benign solver pass rate as an FR proxy: on Terminal-Bench it falls from 76.1% to 65.2%. Fixed-corpus rescoring. The first 49 environments were checked by hand | None | harden-v0 Apache-2.0; Terminal Wrench Apache-2.0 | **High for the audit arm** (development vs held-out attacks, an FR guard, rescoring). No user-intent dimension; benign pass is not labelled FR |
| **Terminal-Bench TB3 task review automation**: `docs/TASK_REVIEW_AUTOMATION.md` and scripts in harbor-framework/terminal-bench, local clone [vf] | main@01c0d6d (2026-11-12) [re-checked commit]; pinned Harbor 0.23.1.dev202609170426 | 2026-11-13 | Crowd-sourced, expert-written terminal tasks submitted as PRs | `instruction.md` is the spec; tests must align with it (LLM-judged `test_instruction_alignment`) | not applicable | Task pytest/CTRF in separate-verifier containers; LLM rubric reviewer; LLM trial and cheat analysis | Oracle must reach reward ≥1 and nop <1 (one attempt); single-shot `/cheat` trials; `/regrade` of recorded trials with LLM classification; `/fortify` hacker-fixer run with `--oracle`; the rubric reviewer is regression-tested for recall only. Six doc-vs-code discrepancies are recorded [vf §1.10] | None | Apache-2.0 [re-checked LICENSE]; harden-v0 Apache-2.0 | **Medium.** Reusable gates and rescoring. It cannot see a requirement that is absent from both instruction and tests (a lost correction) |
| **Benchmarks as Software (TB2.1)**: Buchanan, Zhou, Linderman, Ré, "Benchmarks as Software: Terminal-Bench and the Case for Continuous Benchmarks", arXiv:2611.08417 [vf] | v1 2026-11-05 | 2026-11-13 | Terminal-Bench 2.0 (89 tasks) with traces and community reports | Repair rule: "any solution satisfying the task as written is accepted, and invalid solutions are rejected." | not applicable | Task verifiers repaired after an LLM audit, plus the oracle check | 28 of 89 tasks repaired; instruction–verification mismatch in 57% of them; audit workflow precision 57.1% and recall 71.4% vs the release (retrospective); auditor κ 0.80 | None | TB2.1 release; rubrics in the Apache-2.0 repo | **Medium.** The closest defect category ("hidden constraints appear only in tests"), but the reference is the written instruction, not the session |
| **Terminal-Bench (TB2.0 paper)**: Merrill, Shaw, Carlini, Li, et al. (85 authors), arXiv:2601.11868 [vf] | v1 2026-01-17; ICLR 2026 per a search result (proceedings page not opened) (partial) | 2026-11-13 | 229 crowd-sourced tasks → 89 selected | Instruction plus environment | not applicable | Task tests | Oracle must pass; a no-op "dummy" agent must fail; an adversarial exploit agent, with trajectories manually inspected; 3 reviewers at about 3 reviewer-hours per task | None | Apache-2.0 (repo) | **Low–Medium** (review practice) |
| **SWE-ABS**: Yu, Cao, Zhang, Lin, Xu, Zhong, Xu, Wang, Cao, Cheung, He, Briand, arXiv:2603.00520 [vf] | v1 2026-02-28 | 2026-11-13 | SWE-bench Verified (500) plus 150 SWE-bench Pro instances | The gold patch defines intended semantics; LLM judges decide mutant equivalence (98% agreement with humans on 100) | not applicable | Coverage- and mutation-strengthened unit tests | FN = equivalent mutants that fail; FP = non-equivalent mutants that pass. 2,184 of 11,041 previously passing leaderboard patches rejected (19.78%; the abstract says 19.71%); "conservative false-negative rate of 10.6% (53/500)", corrected post hoc | None | MIT | **High** for constructed near misses plus equivalent alternatives. Anchored to gold-patch semantics, not user intent |
| **PROBE**: Li, Xu, Wang, Tan, Chen, arXiv:2604.01518 [vf] | v1 2026-04-02; v2 2026-08-06; ASE 2026 (comment) | 2026-11-13 | SWE-bench Verified | Reference-patch behaviour; surviving variants reveal gaps | not applicable | Tests augmented from variant probes | A test is retained only if it passes on the reference, fails on at least one surviving variant and stays robust under behaviour-preserving rewrites. 77% of instances admit a surviving variant | None | Zenodo 10.5281/zenodo.19247388 (license not checked) | **Medium.** The FR guard is syntactic only |
| **PatchDiff**: Wang, Pradel, Liu, "Are 'Solved Issues' in SWE-bench Really Solved Correctly? An Empirical Study", arXiv:2503.15223 [vf] | v1 2025-03-19; v2 2025-09-09; ICSE 2026 | 2026-11-13 | 877 plausible patches from 3 tools on SWE-bench Verified | Gold patch defines expected behaviour | not applicable | Developer tests plus differential tests (gold vs candidate) | Full developer tests: 7.8% of plausible patches incorrect; 29.6% behaviourally divergent; manual review of 77: 28.6% incorrect, 66.2% "uncertain" because details are "not explicitly specified in the issue statement" | None | github.com/ZJU-CTAG/PatchDiff (license not determined) | **Medium.** The uncertain bucket is where omitted requirements decide correctness |
| **UTBoost**: Yu, Zhu, He, Kang, arXiv:2506.09289 [vf] | v1 2025-06-10; ACL 2025 | 2026-11-13 | SWE-bench Lite and Verified | Gold patch behaviour is ground truth | not applicable | Original tests augmented with LLM tests; improved log parser | Two authors review discrepancies only; 345 erroneous patches found; tests are developed on the patches that are re-scored | None | MIT | **Medium** |
| **SWE-Bench+**: Aleithan, Xue, Mohajer, Nnorom, Uddin, Wang, arXiv:2410.06992 [vf] | v1 2024-10-09; v2 2024-10-10 | 2026-11-13 | SWE-bench plus 548 new issues | Gold patch and issue define correctness | not applicable | Repository unit tests | Manual comparison of 251 passing patches: 32.67% solution leakage; 31.08% weak tests | None | Dataset released (license not checked) | **Low** |
| **SWE-bench Verified annotation** (OpenAI): blog "Introducing SWE-bench Verified" https://openai.com/index/introducing-swe-bench-verified/ ; annotation data https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip [vf] | Blog 2024-08-13 (search snippet; text not retrieved, HTTP 403); zip Last-Modified 2024-08-12 | 2026-11-13 | 1,699 sampled SWE-bench instances × 3 annotators (93 annotators) | The issue text is the spec | not applicable | FAIL_TO_PASS/PASS_TO_PASS tests | Recomputed by [vf] from the released CSVs (not stated in a retrieved primary text): 61.15% flagged false_negative (FR), 38.3% underspecified; Fleiss κ 0.411 (FR) and 0.241 (underspecified); max-severity ensembling raises per-annotator flag rates from 39% to 61% | None | HF princeton-nlp/SWE-bench_Verified; zip license not stated | **Medium.** Human FR labels that are noisy without executed alternatives |
| **Auditing Reward Hackability in Code RL Training Environments**: Rajan, arXiv:2606.16062 [vf] | v1 2026-06-14 | 2026-11-13 | 49 SWE-bench Verified tasks; 20 R2E-Gym tasks | Gold patch is correct; incorrect patches generated and checked by LLM judge plus execution | not applicable | Repository tests; augmented tests behind a gold-sanity gate | 28.5% and 25.0% of tasks accept a Docker-verified incorrect patch; 65 of 105 (61.9%) LLM hardening tests fail on the gold patch, which the LLM judge missed | None | not stated | **Medium.** Shows why generated tests need reference gates |
| **TestJack**: Yao, Wang, Sen, Chen, Ray, Song, arXiv:2610.10619 [nc] | v1 2026-10-07 (partial) | 2026-11-13 | Five existing benchmarks; trials from 6 model backends | not applicable | None | Per-trial generated tests, kept only if the ground-truth patch passes | 34.4% of trials judged correct violate requirements (resolution 50.6% → 33.2%). Precision and recall "measure agreement with the per-trial audit rather than with a human-labeled ground truth" | None | Anonymous repo (not opened) | **Low–Medium.** FA at scale; no sessions, no human labels |
| **UserSWE** (Tencent Hunyuan): Wu, Luo, Wu, Xu, Xuan, Hu, Gao, Hu, arXiv:2610.29822 [nc] | v1 2026-10-21 (partial) | 2026-11-13 | 72 multi-turn bug-fix tasks from repository history; user model calibrated on 20,859 internal sessions | Information pools limit what the simulated user reveals | Simulated, revealed turn by turn | Tests after every turn; Judge plus cross-family Reviewer; an "equivalent pass" route for valid alternatives | The Reviewer rewrote 40.9% of Judge decisions; 51.2% of equivalence requests granted; humans reviewed simulator utterances only | None | Release stated as forthcoming | **Low–Medium.** FR mitigation for valid alternatives |
| **ImpossibleBench**: Zhong, Raghunathan, Carlini, arXiv:2510.20270 [vf] | v1 2025-10-23 | 2026-11-13 | LiveCodeBench (103) and SWE-bench Verified (349) with mutated tests | The specification is authoritative; tests are mutated to conflict with it | not applicable | Mutated unit tests | By construction any pass is cheating; mutations passed by the original or empty patch are removed | None (prompting and monitor experiments) | MIT | **Low.** Spec–test conflict as a way to manufacture labelled negatives |
| **EvilGenie**: Gabor, Lynch, Rosenfeld, arXiv:2511.21654 [vf] | v1 2025-11-26; v2 2026-05-17 | 2026-11-13 | LiveCodeBench problems in a hackable workspace | Problem statement defines correctness | not applicable | Held-out tests, LLM judges, test-file edit detection | Human review of flagged cases (27 problems); unflagged ones spot-checked | None | MIT | **Low** |
| **BenchJack** (abs): Wang, Li, Mang, Cheung, Sen, Song, arXiv:2605.12673 [vf][t2e] | v1 2026-05-12 | 2026-11-13 | 10 existing agent benchmarks | not applicable | not applicable | Audits existing verifiers via coding-agent red-teaming (8-class flaw taxonomy) | 219 flaws found; hackable-task ratio cut from near 100% to under 10% on four benchmarks (abs) | None stated | not checked | **Low** (adversarial auditing precedent) |
| **Terminal Wrench** (abs): Bercovich, Segal, Zhang, Saxena, Raghunathan, Zhong, arXiv:2604.17596 [vf] | v1 2026-04-19 | 2026-11-13 | "331 terminal-agent benchmark environments ... demonstrably reward-hackable" | not applicable | not applicable | Existing verifiers | 3,632 hack trajectories and 2,352 legitimate trajectories. The hacker-fixer paper reports 323 hackable tasks; whether these are the same set is **UNRESOLVED** | None | Apache-2.0 | **Low** |
| **CodeContests+**: Wang, Liu, Sun, Li, Shen (ByteDance Seed), arXiv:2506.05817 [vf] | v1 2025-06-06 (partial) | 2026-11-13 | Competitive programming (11,690 problems) | Problem statement plus ground-truth solutions | not applicable | Generator–validator agent tests with checkers | TPR and TNR on 1.72M judge-labelled human submissions | RL with the high-quality subset improves training | HF cc-by-4.0 | **Medium.** Two-sided verifier fidelity against labelled pools, but algorithmic tasks with official judges |
| **HardTests / HARDTESTGEN**: He et al., arXiv:2505.24098 [vf] | v1 2025-05-30; v2 2026-11-08; ICLR 2026 (partial) | 2026-11-13 | 26.6k algorithmic problems from 13 online judges | Human oracle programs define outputs | not applicable | Synthesized test cases | Precision and recall against official verdicts | Rejection sampling and RL with the generated verifiers | not checked | **Medium** (same as above, algorithmic) |
| **The Verification Horizon**: Wang, Zhang, Liu, Zhang, Chen, Li, Chen, Fang, Zhang, Wang, Jing, Ma, Cui ("listed alphabetically by their first names"), arXiv:2606.26300 [vf][env] | v1 2026-06-24; v2 2026-06-29 [re-checked] (§2 and §4 read) | 2026-11-13 | SWE-Universe tasks; 125,528 real trajectories of senior engineers using an in-company coding assistant | "the extracted instruction provides only a limited and potentially lossy description of that intent" | **Used as training reward, not as verifier requirements.** 535,737 LLM round annotations; 20.0% of later rounds negative | Test verifiers; an agentic quality judge (`instruct_ut_align`); rubric and agent judges; user feedback as reward | `instruct_ut_align` F1 75.00–81.19 on a human-annotated task-quality benchmark | RL on quality-filtered tasks; Span-KTO 59.8% vs SFT 54.2% on Verified | Paper only (internal data) | **Medium.** Same lossy-intent framing and FP/FN definition. No executable reconstruction from sessions, no FA/FR on candidates |
| **SWE-Bench Pro**: Deng, Da, Pan, et al. (22 authors; Scale AI), arXiv:2509.16941 [vf] | v1 2025-09-21; v2 2025-11-14 | 2026-11-13 | 1,865 problems from 41 repos | Human-written requirements and interfaces, "grounded on the unit tests" | not applicable | Human-reviewed F2P/P2P tests | Human verification of tests | None (ablation: GPT-5 25.9% with augmentations vs 8.40% without) | Public set released (license not checked) | **Low.** A caution: test-grounded hints leak the verifier into the contract |
| **SWT-Bench**: Mündler, Müller, He, Vechev, arXiv:2406.12952 [vf] | v1 2024-06-18; v3 2025-02-07 | 2026-11-13 | SWE-bench converted to test generation (1,983 instances) | Issue text suffices; gold patch validates tests | not applicable | Generated fail-to-pass reproduction tests | Measured against SWE-bench tests (inherits their errors) | None | MIT | **Low** |
| **Otter / TDD-Bench-Verified**: Ahmed, Ganhotra, Pan, Shinnar, Sinha, Hirzel, arXiv:2502.05368 [vf] | v1 2025-02-07; v2 2025-05-30; ICML 2025 | 2026-11-13 | 449 SWE-bench Verified instances | Issue plus old code are enough to generate tests | not applicable | LLM fail-to-pass tests | Precision relative to SWE-bench outcomes (60.8% → 91.9% for one system) | None | Apache-2.0 | **Low** |
| **Decision pins** (abs): Mitsui, "Pinning Decisions Before Failure: Executable Records of Underspecified Choices in AI-Assisted Code Generation", arXiv:2610.03237 [nc] | v1 2026-10-02 | 2026-11-13 | A 40-task benchmark with paired reference implementations | not applicable | The user's chosen reading is recorded as an executable pin | Value pins confirmed by execution | Pins agree with the benchmark's classification on 96–97% of 703 implementations; "42.7% contain no test that distinguishes the competing readings" (600 generated suites) | None | not stated | **Low.** Shows the mechanism behind correction-omission FA |
| **When the Reward Suite Is Leaky** (abs): Zhang, arXiv:2607.11022 [nc] | v1 2026-07-13 | 2026-11-13 | MBPP original vs MBPP+ tests | not applicable | not applicable | Unit-test suites as RLVR rewards | Pre-registered; every rewarded false positive audited under human-adjudicated rules (47.57% genuinely wrong, record-weighted) | Two-arm GRPO contrast | Code and audit records linked (license not checked) | **Low.** Precedent for pre-registered, human-adjudicated FP audits |
| **Agentic Benchmark Checklist (ABC)**: Zhu et al. (25 authors), arXiv:2507.02825 [vf] | v1 2025-07-03 … v5 2025-08-07 (partial) | 2026-11-13 | Audit of agentic benchmarks | not applicable | not applicable | not applicable | Task vs outcome validity checklist; a trivial agent passes 38% of τ-bench tasks | None | not checked | **Low** |
| **RLVεR** (abs): Rad, Filom, Keivan, Mohajerin Esfahani, Kamalinejad, arXiv:2601.04411 [vf] | v1 2026-01-07 | 2026-11-13 | Theory | not applicable | not applicable | Noisy verifiable rewards | Under GRPO the drift is "determined solely by Youden's index J=TPR-FPR" (abs) | Theory | not checked | **Low.** Motivates reporting Youden's J |
| **TRACE = Truncated Reasoning AUC Evaluation**: Wang, Joshi, Plank, Angell, He, "Is It Thinking or Cheating? Detecting Implicit Reward Hacking by Measuring Reasoning Effort", arXiv:2510.01367 [td] | v1 2025-10-01; v4 2026-03-02; "ICLR 2026 Oral Presentation" [re-checked] (abs) | 2026-11-13 | Math and coding RL settings with simulated loopholes (search snippet) | not applicable | None | Policy-side detection: truncate the chain of thought and measure how early expected reward saturates | Compared against CoT monitors (abs) | Detects loopholes during training (abs) | not checked | **Low.** A different, policy-side mechanism. Name collision (§2.7) |

### 2.5 Correction and feedback learning; evolving-requirement benchmarks

Pattern ([cor §9.2], INFERENCE), in three families:
- **Fixed-verifier interactive benchmarks.** Simulated feedback only reveals requirements the verifier already encodes.
- **Synthetic evolving-requirement benchmarks.** Later requirements are authored together with their checks. Several already use "fail on the previous stage" and valid-alternative probes.
- **Real-session benchmarks.** Here omission is a real risk. Only CodeAssistBench measures omission, and none measures the resulting FA on a controlled candidate set against human labels.

| Work (citation + URL) | Version/date | Accessed | Task source | Reconstruction assumptions | User corrections | Verifier type | Independent validation | Training experiments | Artifacts/license | Overlap with TraceContract |
|---|---|---|---|---|---|---|---|---|---|---|
| **TellOnce (v2) / TRACE = Test-time Rule Acquisition and Compiled Enforcement (v1)**: Zhou, Guo, Zhuang, Wang, Huang, Liang, Chen, Gao, Moniz, Chawla, Zhang, arXiv:2606.13174, https://arxiv.org/abs/2606.13174 [cor] | v1 2026-06-11, "Getting Better at Working With You: Compiling User Corrections into Runtime Enforcement for Coding Agents". v2 2026-10-25, "TellOnce: Correcting Coding Agents Once, Improving Their Future Actions" [re-checked v2]. No venue | 2026-11-13 | Diagnostic: 32 transcripts from one researcher → 142 correction–conflict records → 19 held-out tasks with 29 checks. End-to-end: ClawArena, MemoryArena and SWE-Together, with simulated users | Diagnostic tasks keep the request and context but remove the target preference | **Central, but only durable cross-task preferences.** v2 §4.1: "Task-specific instructions are not stored as lasting rules". Release notes 1.8.0: "A bare replacement, a new task requirement, or an explicit one-time exception is not stored." | Compiled programmatic or LLM-semantic checks. Final scoring uses native checkers plus an LLM preference scorer | Blind-reviewed validation cases (176 probes: 1 FP, 2 FN); semantic checker on 48 artifacts (2 FP, 1 FN); simulator fidelity vs real corrections F1 0.906; final scorer not human-validated | None (frozen-state personalization layer) | MIT harness (only one of three user profiles released) and MIT skill v1.8.3. Diagnostic tasks and records not found | **Medium.** Corrections → checks under a meaning-preserving rule with blind validation. v1 replays the originating correction–conflict pair as a negative. Scope is *future* tasks, and it excludes task requirements |
| **PersonaCodeBench**: Wang, Hou, Shen, Fan, Huang, Zhu, Li, Li, Yao, Wang, et al. (30 authors), arXiv:2611.05739, https://arxiv.org/abs/2611.05739 [cor] | v1 2026-11-03 [re-checked] | 2026-11-13 | 231 native tasks from Terminal-bench 3, DeepSWE, SWE-bench-Live, SWE-Together (9) and SWE-bench Pro, each paired with a frozen persona (422 "evolved requirements") | Native task kept. Requirement content, disclosure triggers and acceptance criteria fixed before evaluation. Contrastive screening | **Synthetic** later-disclosed persona requirements, delivered by a controller-governed simulator | Native tests plus a personalization verifier (deterministic checkers and LLM judges) | Blinded expert review of 148 requirement judgments: 71.0% agreement (κ 0.473); accept/reject 77.2%; "89.2% precision and 74.5% recall" for Satisfied [re-checked]. "179/874=20.5% of complete native-test passes fail the recorded persona criteria" — "descriptive discrimination, not evidence that all 179 judgments are correct" [re-checked] | None | MIT (MatrAIx-ai/PersonaCodeBench) | **High on the measurement analogue** (native-only verifiers accept outputs that violate later requirements). **Low on source**: synthetic requirements, no reconstruction, no FR on valid alternatives |
| **FeatureLoop**: Feng, Wu, Gao, Wang, Lu, Hu, "Benchmarking Coding Agents under Evolving Requirements", arXiv:2610.35488, https://arxiv.org/abs/2610.35488 [cor] | v1 2026-10-26; v2 2026-10-29 [re-checked] | 2026-11-13 | 61 tasks, each grounded in at least two public issues; 34 repos; 5 languages | Agent-assisted authors work in separate workspaces with information boundaries; a requirement-group DAG is unfolded into stages | Evolution feedback and completion feedback; 85 of 147 later groups need new user information | Cumulative executable checks per requirement group plus a baseline suite | New checks must fail on the previous reference checkpoint and pass on the current and later ones. "valid alternative implementations and deliberately faulty variants" are probed on selected candidates. No aggregate probe outcomes or FA/FR reported | None (best model completes 72.1%) | No artifact link found | **Medium–High on audit design.** Synthetic tasks; no omission of real corrections |
| **EvoCode-Bench**: Shen, Chen, Xu, Ma, Chen, Li, arXiv:2605.24110 [cor] | v1 2026-05-22 ("Work in Progress") | 2026-11-13 | 26 engineer-authored tasks with 227 rounds | not applicable (authored instructions, references and tests) | Authored extension (198), correction (69) and conflict (42) rounds. Cumulative tests are updated when a correction supersedes a requirement | Cumulative behavioural tests per round | Two reviewers check alignment, whether "a competent implementation that differs from the reference can pass", and shortcuts. No FA/FR rates | None | Release stated; link and license not found | **Medium** |
| **SR-Eval**: Zhan, Gao, Hu, Gao, arXiv:2509.18808 [cor] | v1 2025-09-23; v2 2026-03-17 | 2026-11-13 | 443 tasks decomposed backwards from final requirements | Multi-agent decomposition, motivated by "the lack of public interaction traces" | Synthetic evolving requirements | Per-turn LLM tests with distinctiveness validation: current-turn tests must fail on the previous turn's implementation | User study (3 developers); ablation shows tests get easier without distinctiveness validation | None | No LICENSE at repo root | **Medium.** Previous-turn distinctiveness ≈ our pre-correction negative, but synthetic |
| **CodeAssistBench (CAB)**: Kim, Garg, Ray, Kumar, Deoras, arXiv:2507.10646 [cor] | v1 2025-07-14; v5 2026-01-15; NeurIPS 2025 D&B (comment) | 2026-11-13 | 3,286 real GitHub issues tagged as questions (214 repos, 7 languages) | Satisfaction conditions extracted from the full thread, "focusing on the original question and subsequent clarifications" | Later clarifications folded into criteria | LLM judge; Docker execution where available | "86.3% were judged accurate but only 65.7% complete" (663 conditions, 70 issues); judge 65.92% vs inter-human 78.28% (κ 0.68) | None | Apache-2.0 | **Medium.** The only measurement of requirement omission when converting a real conversation into criteria |
| **CodeIF-Bench**: Wang, Zhang, Liu, Shi, Li, Shen, Fu, arXiv:2503.22688 [cor] | v1 2025-03-05; v4 2025-11-23 | 2026-11-13 | 124 MBPP/DevEval tasks with GPT-4o follow-up instructions (internal count inconsistency) | not applicable | Follow-up instructions as later requirements | Cumulative executable tests; Instruction Forgetting Ratio | Two developers refined the data (κ 0.73) | None | No LICENSE at repo root | **Low** |
| **FronTalk**: Wu, Xue, Yin, Zhou, Chang, Peng, Wen, arXiv:2601.04203 [cor] | v1 2025-12-05; v3 2026-08-09; CoLM 2026 (comment) | 2026-11-13 | 100 synthetic 10-turn front-end dialogues | not applicable | Each turn adds an intent; forgetting rate 4.3–44.6% | Web agent checks atomic test cases | Evaluator vs human: accuracy 80.2 (κ 58.9) | None | not checked | **Low** |
| **SWE-INTERACT**: Raghavendra, Gunjal, Sabharwal, He (Scale AI), arXiv:2606.30573 [cor][sc] | v1 2026-06-29 | 2026-11-13 | 75 tasks from SWE-bench Pro, SWE Atlas and DeepSWE | Original specs revealed progressively by a persona simulator grounded in SWE-chat messages | Simulated | "final task success is still judged by the original verifier rather than by simulator approval" | Simulator ablations only | None | scaleapi/SWE-Interact Apache-2.0. Relation to HF sweinteract/sweinteract (MIT, 125 tasks) unclear | **Low** |
| **SpecPath**: Wu, Wang, Yang, Ji, Lin, arXiv:2608.09799 [nc] | v1 2026-08-10 (partial) | 2026-11-13 | Five calibrated tasks with authored revision histories | not applicable | Formal requirement atoms with restatement, override and cancellation; "contract-equivalent" histories | Fixed executable verifier per task | 35 of 100 blocks fail on at least one equivalent history | None | not stated | **Low.** A ready formalism for an active contract |
| **Ambig-SWE**: Vijayvargiya, Zhou, Yerukola, Sap, Neubig, arXiv:2502.13069 [cor] | v1 2025-02-18; v3 2026-02-21; ICLR 2026 (comment) | 2026-11-13 | 500 SWE-bench Verified issues summarized into underspecified versions | Proxy user sees the full issue | None real | Original SWE-bench tests | not applicable | None | MIT | **Low** (mirror image of our problem) |
| **Dialogue SWE-Bench**: King, Flanigan, arXiv:2606.13995 [cor] | v1 2026-06-12 | 2026-11-13 | SWE-bench Verified with vague initial queries | Persona simulator knows the full issue | Simulated replies | SWE-bench Verified execution tests | Human ratings of dialogue (not read in detail) | None | not checked | **Low** |
| **MINT**: Wang, Wang, Liu, Chen, Yuan, Peng, Ji, arXiv:2309.10691 [cor] | v1 2023-09-19; v3 2024-03-12; ICLR 2024 (comment) | 2026-11-13 | Repurposed reasoning, coding and decision tasks | not applicable | GPT-4-simulated feedback | Original ground truths | Feedback realism only | None | not checked | **Low** |
| **ConvCodeWorld**: Han, Hwang, Samdani, He, arXiv:2502.19852 [cor] | v1 2025-02-27; ICLR 2025 (comment) | 2026-11-13 | BigCodeBench (1,140 problems) | not applicable | Expert verbal feedback is generated from the reference code | Hidden tests | Feedback helpfulness only | Effects of feedback training reported (not read) | not checked | **Low** |
| **ColBench / SWEET-RL**: Zhou, Jiang, Tian, Weston, Levine, Sukhbaatar, Li, arXiv:2503.15478 [cor] | v1 2025-03-19 | 2026-11-13 | Procedurally generated backend and frontend tasks | A simulator with access to the hidden reference | Simulated clarifications | 10 hidden unit tests (backend); CLIP similarity (frontend) | Test set manually inspected | Multi-turn RL (SWEET-RL) | CC-BY-NC | **Low** |
| **TiCoder**: Lahiri et al., arXiv:2208.05950; user study Fakhoury, Naik, Sakkas, Chakraborty, Lahiri, arXiv:2404.10100 (IEEE TSE 50(09):2254–2268) [cor] | 2022-08-11 / v2 2023-10-04; TSE 2024 | 2026-11-13 | MBPP and HumanEval; 15-programmer study | The hidden reference implementation is the "idealized proxy" of intent | The user approves or rejects generated tests | Hidden tests; approved tests act as a partial spec | User study: correctness 0.40 without vs 0.84 with the tool | None | not checked | **Low** |
| **ToM-SWE**: Zhou, Chen, Wang, Neubig, Sap, Wang, arXiv:2510.21903 [cor] | v1 2025-10-24; v2 2026-01-29 | 2026-11-13 | 500 SWE-bench Verified instances with profiles derived from 453 consented OpenHands sessions | not applicable | Preferences shape the simulator, not task requirements | SWE-bench tests plus a simulator rating | In-the-wild study (abstract and §1 numbers differ) | None | not checked | **Low** |
| **Asuka-Bench** (abs): Wang, Sun, Zhu, Zhou, Liu, Chen, Qiu, Cao, Cai, Zhang, Mao, arXiv:2606.05920 [t2e][cor] | v1 2026-06-04 ("under review") | 2026-11-13 | 50 web tasks with 784 criteria | not stated (abs) | "a User LLM turns evaluation outcomes into natural-language feedback for the next round" | A UI agent executes test cases on the deployed site | not stated (abs) | None stated | not checked | **Low–Medium** (abs). Shares 3 authors with Trace2Eval |
| **Cursor, "Improving Composer through real-time RL"**: Jackson, Trapani, Wang, Zhu, https://cursor.com/blog/real-time-rl-for-composer [nc] | 2026-03-26; read through a WebFetch summary (quotes not checked against raw HTML) | 2026-11-13 | Live production interactions | none stated | Implicit: "User sends dissatisfied follow-up" is a reward signal | Aggregated user-reaction rewards | not stated | Online RL of Composer; reward hacking reported ("learned to defer risky edits by asking clarifying questions") | Blog only | **Low.** Industry uses corrections as reward, not as verifier requirements |

### 2.6 Failure-driven training and environment generation

| Work (citation + URL) | Version/date | Accessed | Task source | Reconstruction assumptions | User corrections | Verifier type | Independent validation | Training experiments | Artifacts/license | Overlap with TraceContract |
|---|---|---|---|---|---|---|---|---|---|---|
| **TRACE (Kang et al.)** = "Turning Recurrent Agent failures into Capability-targeted training Environments": Kang, Suresh, Saad-Falcon, Mirhoseini, "TRACE: Capability-Targeted Agentic Training", arXiv:2604.05336, https://arxiv.org/abs/2604.05336 ; code https://github.com/ScalingIntelligence/TRACE [td][env][vf] | v1 2026-04-07; v2 2026-07-02 [re-checked]. Local code @d2db230 (2026-07-12) | 2026-11-13 | The policy's own successful and failed rollouts on τ²-bench, ToolSandbox and SWE-bench Verified. Contrastive capability mining (keep capability c if Δ ≥ 0.20 and Cov ≥ 0.10) | Synthetic environments, one per capability. SWE: stdlib-only 300–600 LOC modules with an oracle SEARCH/REPLACE | None (agent failures, not user feedback) | Programmatic. τ²: DB-state hash plus a communication check (1.0 / 0.3 / 0). SWE: target pytest plus regression guards. The released SWE reward gives **0.6** to an applied edit that does not fix the bug (INFERENCE from code) | Self-test (target fails before the oracle and passes after; guards pass) plus smoke pass rate ≤ 0.5. No FA/FR, no human labels. The prompt asserts "No reward hacking, no LLM judge" | GRPO LoRA per capability plus a MoE gate. τ²: 32.9→48.2 (Qwen3-30B-A3B). SWE-bench Verified: 26.0→41.0 and 68.0→73.2 | Code MIT [re-checked LICENSE]. Phase 5 is a stub and helper files are missing. One HF LoRA (Apache-2.0 tag). **UNRESOLVED** discrepancies: the paper says mining used a SWE-smith split while the code and card use Verified failures; Qwen3.6 baselines appear as 68.0 / 58.2 / 52.8 | **Low.** Trajectory → environment for training; no reward-fidelity measurement |
| **Socratic-SWE** (abs): Xiao et al., arXiv:2606.07412 [td] | v1 2026-06-05 | 2026-11-13 | The solver's own historical traces → skills → targeted repair tasks in real repos | Execution-based validation (abs) | None | Execution validation plus a gradient-alignment task reward (abs) | not stated (abs) | 50.40% on Verified after 3 iterations | not stated | **Low** |
| **SENTINEL** (abs): Wang et al., arXiv:2606.12908 [td] | v1 2026-06-11 | 2026-11-13 | Solver rollout failures → Controller/Proposer → executable tasks | not stated (abs) | None | Executable tasks (abs) | not stated | τ² Retail, Qwen3-4B Pass^1 66.4→74.9 | not stated | **Low** |
| **EnvGen** (abs): Zala, Cho, Lin, Yoon, Bansal, arXiv:2403.12014 [td] | v1 2024-03-18; v2 2024-07-12; COLM 2024 | 2026-11-13 | LLM-generated environment configs adapted toward weak skills | Game simulators | None | Simulator reward | not applicable | Small RL agents | not checked | **None.** Early weakness-targeted precedent; TRACE does not cite it |
| **WebRL** (abs): Qi et al., arXiv:2411.02337 [td] | v1 2024-11-04; v3 2025-01-27; ICLR 2025 | 2026-11-13 | "a self-evolving curriculum that generates new tasks from unsuccessful attempts" | Web | None | Outcome reward model | not stated | Web-agent RL | not checked | **Low** |
| **Self-Challenging LM Agents** (abs): Zhou, Levine, Weston, Li, Sukhbaatar, arXiv:2506.01716 [td] | v1 2025-06-02 | 2026-11-13 | Self-generated "Code-as-Task" tasks | Tool use | None | Verification function plus failure cases as tests | Failure cases filter tasks; no human labels | Agent RL | not checked | **Low** |

Also reviewed in this family, abstract level only [td §4], none measuring verifier fidelity: LLMs-as-Instructors (arXiv:2407.00497), DataEnvGym (2410.06215), TDG (2305.17804), AutoDetect (2406.16714), SwS (2506.08989), EEF (2504.13145), Agent Learning via Early Experience (2510.08558), BugPilot (2510.19898), RLVE (2511.07317), Self-play SWE-RL (2512.18552), Agent World Model (2602.10090), Agent-World (2604.18292), Environment Evolution for Terminal Agents (2609.04128).

### 2.7 Disambiguation of similarly named projects (TRACE and others)

Always cite these with first author and arXiv ID, never as a bare "TRACE" [td §3].

| Name as written | Expansion / title | Authors (first) | arXiv / date | What it is | Relation to us |
|---|---|---|---|---|---|
| TRACE (Kang et al.) | "Turning Recurrent Agent failures into Capability-targeted training Environments"; paper title "TRACE: Capability-Targeted Agentic Training". Its HF LoRA card expands it as "Test-time Reinforcement Learning Adaptation via Capability Environments" | H. Kang | 2604.05336; v1 2026-04-07, v2 2026-07-02 | Failure-contrastive environment synthesis plus LoRA/MoE training | The `ScalingIntelligence/TRACE` clone in our references; §2.6 |
| TRACE (Zhou et al. v1) → **TellOnce** (v2) | "Test-time Rule Acquisition and Compiled Enforcement" | Y. Zhou | 2606.13174; v1 2026-06-11, v2 2026-10-25 | User corrections → runtime checks for future tasks | §2.5; cite by version |
| TRACE (Wang et al.) | "Truncated Reasoning AUC Evaluation" (paper "Is It Thinking or Cheating? ...") | X. Wang | 2510.01367; v1 2025-10-01, v4 2026-03-02; ICLR 2026 Oral (comment) | Policy-side reward-hacking detection | §2.4 |
| TRACE (Guo et al.) | "Trajectory-based Validated-by-Reproducing Agent-benchmark Complexity Evolution" | D. Guo | 2510.00415; v1 2025-10-01, v3 2026-03-24 | Self-evolving benchmark tasks (GAIA, AIME) | None |
| TRACE (Mittapalli et al.) | "Trajectory Reasoning through Adaptive Cross-Step Evidence Aggregation" | V. Mittapalli | 2606.07054; 2026-06-05 | Trajectory monitor for sabotage | None |
| TRACE (Zabolotnii) | Metrology-grounded trustworthy agentic-AI framework | S. Zabolotnii | 2605.03838; 2026-05-05 | Engineering reference architecture | None |
| TRACE (2023, 2024) | Continual-learning benchmark (2310.06762); video temporal grounding (2410.05643); "TRACE the Evidence" RAG (2406.11460); attribution (2407.04981) | various | 2023–2024 | Unrelated | None |
| Trace (Microsoft) | "Trace is the Next AutoDiff" | C.-A. Cheng | 2406.16218 | Optimization library | None |
| TRACED, TraceRL, TraceCoder, CodeTracer, TRAIL | Execution-aware pre-training (2306.07487); RL for diffusion LMs (2509.06949); runtime-trace debugging (2602.06875); agent-state trace trees (2604.11641); annotated agent traces (2505.08638) | various | 2023–2026 | Trace-named, unrelated | None |
| Trace2Eval | Contextualized evaluation from real traces | J. Shi | 2611.06506 | §2.1 | Closest substrate work |
| TraceDance; Trace Commons; traj2envs | §2.1 / §2.2 | — | 2026 | §2.1 / §2.2 | As listed |
| **TraceContract (FM 2011)** | "TraceContract: A Scala DSL for Trace Analysis" | H. Barringer, K. Havelund | FM 2011, LNCS pp. 57–72, DOI 10.1007/978-3-642-21437-0_7 [re-checked via Crossref] | Runtime-verification DSL | **Name collision with our working name** (decision in §8). The package names `tracecontract`, `trace-contract` and `trace_contract` were unused on PyPI and npm on 2026-11-13 [td §3] |

### 2.8 Also reviewed (low or no overlap; details in the notes)

- Interactive or feedback benchmarks [cor §3]:
  - InterCode (arXiv:2306.14898)
  - CodeFlowBench (2504.21751)
  - "When Benchmarks Talk" (2502.18413; venue from web search only)
  - RECODE-H (2510.06186)
  - LLMs Get Lost In Multi-Turn Conversation (2505.06120)
  - ICAE-Bench (2607.21217)
  - SWE-Shift (2610.32196)
  - SLUMP (2603.17104)
- User-simulator reliability [cor §6]:
  - SimulatorArena (2510.05444)
  - Lost in Simulation (2601.17087)
  - Mind the Sim2Real Gap (2603.11245)
  - Suh et al. (2605.09808)
  - HumanLM (2603.03303)
- Rules and personalization from feedback [cor §7]:
  - ZORO (2604.15625)
  - ContextCov (2603.00822)
  - ILF (2303.16749)
  - Coffee-Gym (2409.19715)
  - PRELUDE/CIPHER (2404.15269)
  - MultiSessionCollab (2601.02702)
- Specification inference: SpecRover (2408.02232), nl2postcond (2310.01831), RECOVER (2411.19552) [cor §5.7].
- Empirical studies of developer–LLM conversations and agent PRs [cor §8]:
  - Decoding Human–LLM Collaboration (2512.10493)
  - CodeChat (2509.10402)
  - Hao et al. (2403.10468)
  - Watanabe et al. (2509.14745)
  - Ehsani et al. (2601.15195)
- Newest abstract-level items [nc §4]:
  - Intent-Eval (2610.06496): "mentioned-as-in-effect" errors
  - IntentDelta (2610.33806)
  - LiveAsset (2611.11560)
  - Specification-Oracle Gaps (2610.30635)
  - Veritas (2611.13336)
  - Groundability (2610.01023)
  - Re-executing Coding-Agent Evaluations (2610.14460)
  - How Coding Agents Fail Their Users (2605.29442)
  - RealSWE (2608.27831)
  - SWE-TaskFlow (2610.09633)
  - FeatureArc (2610.37434)
  - K-Bench (2608.21601)
  - and others listed in [nc §2, §4]
- Other verifier work [vf]:
  - EvalPlus (2305.01210)
  - METR reward-hacking blog (2025-06-05)
  - MacDiarmid et al. (2511.18397)
  - Baker et al. (2503.11926)
  - Meerkat (2604.11806)
  - Berkeley RDI blog (April 2026)
  - Terminal-Bench leaderboard integrity update
  - OpenAI's 2026 SWE-bench Verified posts: HTTP 403, so the reported "59.4% flawed tests" figure is secondary-source only and **unverified**

---

## 3. Proposed contribution

### 3.1 The claim, stated precisely

This follows decision log D25 and protocol v0.2 ([DL D25], [P §1–§7]).

**Question.** When coding tasks are reconstructed from agent sessions, how often does omitting a user's later correction make the task's verifier accept a solution the user rejected? Which reconstruction and validation methods reduce that error without rejecting valid alternatives?

**What is measured.** For each verifier condition V, computed on held-out evaluation candidates only:
- FA(V) = the share of label-invalid candidates that V passes.
- FR(V) = the share of label-valid candidates that V does not pass.

The conditions [P §4]:
- **C1 `initial_plain`**: tests generated from an initial-request-only contract.
- **C2 `initial_audited`**: C1 plus the predefined audit audit:v1, with at most 3 revisions.
- **C3 `full_plain`**: tests generated from a correction-aware contract.
- **C4 `full_audited`**: C3 plus audit:v1.
- **B1 `repo_tests`**: repository tests at the reference state, keeping only those that pass on the reference.
- **B2 `llm_freeform`**: tests from an LLM given the whole session without contract machinery. This is the competent full-session reconstruction baseline.

All generated conditions share one generator model and prompt template; only the contract input differs [DL D14].

**Pre-specified paired comparisons** on the same candidates [P §7]:
- C1 vs C3 and C2 vs C4: information lost by initial-request-only reconstruction.
- C1 vs C2 and C3 vs C4: effect of the audit.
- B2 vs C3/C4: structured contract vs competent full-session LLM baseline.
- B1 vs C4: repository tests vs the proposed verifier.

**Primary estimand.** Correction-attributable FA on observed pre-correction states, FA_pre(C1) − FA_pre(C3), and likewise C2 vs C4. FR on independent valid alternatives is the guardrail. Choosing it as primary is an open decision (§8).

**Secondary measures:**
- Youden's J = (1 − FR) − FA, and the number of task families with at least one accepted negative [P §10].
- Negatives stratified by origin (observed pre-correction vs constructed near miss) and by type (correction-violating vs initial-violating) [P §6, §10].
- Contract completeness (requirement recall and precision against the reference contract) as a mediator.
- The disagreement between model-proposed and human labels.
- Task yield with rejection reasons.
- Infrastructure outcomes, reported separately and never scored as rewards [P §6].

**On what data.** Task families, each one source session plus everything derived from it:
- **Natural** sessions (SWE-chat, once access is granted; §4).
- **Controlled** sessions (protocol CS-v1). These are reported separately and never pooled with natural ones.

Each family's **evaluation candidates** [P §5]:
- the agent's observed pre-correction state;
- 2 independent valid alternatives, written from the reference contract by separate agents without the reference diff;
- 4–6 constructed near misses, each meant to violate one requirement, prioritising correction-introduced ones;
- no-op and reference, used only as sanity checks.

Verifiers are frozen (content hashes) before any evaluation candidate exists. Evaluation candidates are then generated by separate agents in workspaces without verifier files, and are never used during verifier construction or audit [DL D14], [P §3, §8].

**Against what ground truth.** Human labels: valid, invalid or ambiguous, with the violated requirement ids.
- Labels are given relative to a human-reviewed reference contract: evidence-quoted user requirements with explicit, inferred, superseded or unresolved status. A regression norm applies: unrelated existing behaviour must keep working (`docs/annotation_guide.md`).
- Annotators are blind to verifier outputs. A second annotator labels an overlap subset, and disagreements are adjudicated.
- Until human labels exist, results are an **automated pilot** with proposed labels (rule D19), never called ground truth [DL D19], [P §5].

**Unit of analysis.** The task family, with cluster-bootstrap intervals. With fewer than about 10 families, results are descriptive [P §3].

**Interpretation boundary.** The initial-only arm measures information lost during dataset construction, not the ability of an agent that was never told a requirement [P §1].

### 3.2 Strongest argument that this is already covered (steelman)

1. **SessionFarmer** (arXiv 2611.02440, 2026-11-02) already covers most of the pipeline:
   - It reconstructs executable tasks from the **same SWE-chat sessions**.
   - It writes correction-aware statements that consolidate "all requirements that remain in effect at the end of the episode", with event-cited clauses and withdrawals.
   - It shows that first-message statements fully cover only 26% of a reference ledger's requirements, against 75% for full episodes, on multi-session tasks.
   - It audits its LLM-written tests for both error directions, reporting FPR, FNR and BAcc (Table 3).
   
   On this reading, "reward fidelity" is SessionFarmer's Table 3 under a new name, and "correction-aware contracts" are its full-episode statements [nc §3.1].
2. **VerifierBench** (arXiv 2610.28679) already scores generated verifiers on **held-out** pools that include valid alternatives (`overstrict_trap`), unfinished "base" states, partial solutions, near misses and hacks. It finds that verifiers over-reject valid solutions [nc §3.5].
3. **SWE-Together** (arXiv 2606.29957) already builds tasks from real sessions, including 48 from SWE-chat. Its correctness includes "requirements introduced during the interaction". It states our motivation almost verbatim, covering both missed later requirements and rejected valid alternatives [sc §5.1], [cor §5.1].
4. **traj2envs** (Hugging Face, 2026-11-05) already has an initial-request-only family (`build`) and a family that starts from the pre-request state (`extend`). It also has a predefined automatic verifier audit: a trial matrix plus a mutant kill rate [td §6].
5. **PersonaCodeBench** already quantifies that native verifiers accept outputs violating later-disclosed requirements: 20.5% of native passes. Its requirement judgments are checked by blinded experts [cor §4.5].
6. **ARE-bench** shows on real sessions that omitting historical requirements inflates strict success from about 28–40% to about 69% [nc §3.4].
7. **AfterVibe** shows that conversation-derived flex tests accept 58.0% of pre-change code [cor §5.3].
8. **Trace2Eval** already reconstructs tasks from real coding sessions with a q that "captures the user’s objective and explicit requirements from the interaction". A competent summarizer may therefore already carry corrections [t2e §14].
9. **Hacker-fixer** and **SWE-ABS** already provide audits with held-out attackers or equivalent mutants and measure both error directions [vf §2 A6, B1].
10. **SF Data** has publicly stated the hypothesis itself (§1).

Conclusion of the steelman: the 2×2 recombines published parts, and its novelty reduces to a re-labelled ablation.

**Why the argument does not fully hold.** These are verified gaps in the sources read; the search was not exhaustive.
- **Verifier-level counterfactual.** SessionFarmer measures first-message information only as statement coverage. It never builds verifiers from the opening request and asks how often *those* verifiers accept what the user later rejected. Its Appendix D lists that analysis as future use [nc §3.1, §8] [re-checked].
- **Human ground truth.** SessionFarmer's FP/FN rest on gpt-6-astra labels [re-checked]. VerifierBench uses construction labels and says they do not "certify that every label is semantically correct" [re-checked]. TestJack, ARE-bench, TraceDance and traj2envs have no human candidate labels.
- **Session-native negatives.** No audit pool found contains the agent's own pre-correction state that the user rejected in the session:
  - SessionFarmer's mutants are constructed and used inside its refinement loop;
  - VerifierBench's "base" cases are constructed;
  - AfterVibe's "pre-change" is the parent commit;
  - TellOnce v1 replays correction–conflict pairs, but for future-task rules.
- **Held-out discipline on session-derived tasks.** No session-derived study found scores a frozen pool, never used in construction, that also contains independent valid alternatives.
- **The FA/FR trade-off is real and under-measured.** SessionFarmer's refinement cut FNR by 32–34 pp but raised FPR by 16.2–17.5 pp. An audit must therefore be judged on both directions against independent labels.

**Residual risks to the claim:**
- VibeSWEBench's full text could not be read.
- SessionFarmer's code and data are not public.
- Papers from 12–13 Nov 2026 may be missing [nc §1, §10].

All three must be re-checked before submission.

### 3.3 What remains if the main improvement is zero

Here "main improvement" means a reduction of FA from correction-aware contracts (C1→C3) or from the audit (C3→C4). With a handful of families, "zero" will often mean "inconclusive". The pilot is descriptive [P §3]. What would still be worth reporting (INFERENCE):
1. **A measured null against a public, untested claim.**
   - If C1 and C3 have similar FA on observed pre-correction states, then for this population the industry hypothesis V8 does not translate into verifier error. That is informative because nobody has published the number. Possible reasons include generated tests that reject the pre-correction state for unrelated reasons, or corrections that restate behaviour the agent already had. CS-03 is a case where the pre-correction state passes all B1 checks [DL D18].
   - If both conditions are high, the bottleneck is verifier generation, not contract content.
2. **The FR cost of each remedy** on independent valid alternatives. Prior session-derived work did not measure this against human labels; SessionFarmer's own audit shows a trade-off.
3. **The LLM-label vs human-label gap** on pre-correction states and valid alternatives. SessionFarmer, TestJack, VerifierBench and ARE-bench rely on LLM or construction labels.
4. **Contract completeness against a human reference**, a mediator that only CodeAssistBench has measured for real conversations (65.7% complete).
5. **A small human-labelled release**: tasks, frozen verifiers, candidates, labels and the rejection funnel. It is subject to data rights (§4).
6. **Infrastructure:**
   - process-separated grading with adversarial isolation tests;
   - a Harbor 0.25.0 export;
   - an auditable controlled-session protocol.
7. **A testable negative.** A high trial-matrix or mutation-kill pass rate (the traj2envs-style audit) may fail to predict correction-omission FA. This hypothesis should be pre-registered [td §9].

### 3.4 Design commitments implied by the prior work

These are cited choices, not new claims:
- Freeze verifiers before scoring and keep development candidates disjoint from evaluation candidates. The models are hacker-fixer and SWE-ABS, and Trace2Eval's in-sample calibration is the counter-example [vf §5], [t2e §15].
- Gate every generated test on the reference *and* on valid alternatives. Rajan found that 61.9% of LLM hardening tests broke the gold patch [vf A8].
- Never treat a missing or crashed verifier result as rejection. Report it as an infrastructure outcome [hb §4.2], [P §6].
- Keep tampering probes out of semantic FA [P §10], [vf §5].
- Include in a contract only requirements the user stated. Avoid test-grounded hints of the SWE-Bench Pro kind, which leak the verifier [vf §5].
- Represent the full-session contract with explicit activate, override and cancel semantics, as in SpecPath atoms and the superseded status [nc §9].
- Guard extraction against "mentioned-as-in-effect" errors (Intent-Eval) [nc §9].
- Do not replay corrections through a user simulator in the core measurement. Simulators drop about 30% of intents (SWE-Together Intent Coverage of about 0.7) [cor §11].

---

## 4. Data sources and access

### 4.1 Populations (never pooled without saying so) [P §2], [DL D4]

| Population | Definition | Source(s) | Status on 2026-11-13 | Candidate origins it can supply |
|---|---|---|---|---|
| **Natural (naturally occurring)** | Real users' sessions with real corrections | SWE-chat (primary); alternatives in §4.3 | **Blocked**: dataset terms not accepted by the repository owner; saved token check returns 401 [DL D4], STATUS.md | Observed pre-correction states from real sessions; user-accepted final states |
| **Controlled** | Real agent runs on pinned public repos with user turns written and hashed by the study before the run (CS-v1) | CS-01 humanize, CS-02 tinydb, CS-03 inflection, CS-04 more-itertools (all MIT) [data card] | In use (pilot) | Observed pre-correction states of a real agent under scripted corrections. **Not** natural user behaviour |
| **Synthetic** | Hand-written fixtures; model-constructed candidates; distillation trace sets | `tests/fixtures/`; constructed near misses and generated valid alternatives; e.g. TeichAI distillation sets | Fixtures: tests only, never evidence. Constructed candidates: evaluation pool. Distillation sets: not used | Constructed near misses and alternatives (reported separately from observed states) |

### 4.2 SWE-chat (primary natural source)

**Identity.**
- Paper: Baumann et al., arXiv:2604.20779. v1 2026-04-22; v2 2026-10-01; arXiv comment "Accepted at COLM 2026", not independently confirmed; paper CC BY 4.0 [re-checked].
- Dataset `SALT-NLP/SWE-chat`: revision `202b071f18e03c79df5a7287565ce2ebc5ee7756`, lastModified 2026-10-03 [re-checked]. The v2 snapshot holds data through 2026-09-04 [sc §1].

**License.** ODC-BY 1.0 (card `license: odc-by` [re-checked]) [sc §3.2].
- It permits sharing, producing works and adapting, including commercially, with attribution and notice obligations (§4.2 for public conveyance of the database or a derivative database; §4.3 for publicly used produced works).
- §2.4: the license "does not cover any rights ... in individual Contents". User prompts, agent outputs and repository code therefore keep their own rights status.
- Code stays under each repository's licence. Inclusion required "licenses allow redistribution" [sc §2.2].

**Gate.**
- `gated: auto` [re-checked].
- The page reads "You need to agree to share your Hugging Face information to access this dataset". The page source shows `gatedProfileSharing` username and e-mail set to true [re-checked].
- Data files return **HTTP 401** without authorization. Re-checked today with a 4-byte range request, which returned a 127-byte error and no data.
- The gate's conditions text needs a login and was **not retrieved**, so any extra restriction it imposes is **UNRESOLVED**.

**Removal policy (card).** "If you would like your data removed from SWE-chat, or if you encounter content that is illegal, you may request deletion." [re-checked] Requests go to the contact on the card and cite `repo_id`, `session_id` or `turn_id` [sc §3.4].

**Personal data in the dataset.**
- The commits table has `user_id`, "Canonical user identity: GitHub username if resolved, else email, else author name.", and `github_username` [re-checked on the card].
- PII redaction (Presidio plus TruffleHog) covers prompts, assistant responses, subagent prose and skills. It does not explicitly cover tool inputs and outputs.
- A derived dataset card reports a residual plaintext password in tool-derived content [sc §3.3].

**What can and cannot be redistributed.** INFERENCE; needs the owner's confirmation and, if wanted, legal advice.

| Item | Plan |
|---|---|
| Derived tasks, contracts written by us (paraphrased, with hashed pointers to the source turn), tests, labels, IDs and hashes | Redistribute with the ODC-BY notice and citation |
| Code from permissively licensed repositories | Redistribute under each repo's licence. Filter on SPDX in `repo_github_metadata`, not only `license_type`, whose categories are undocumented [sc §3.5] |
| Raw transcripts and verbatim prompts | **Do not redistribute.** The contents' rights are unclear, and redistribution would bypass the gate. Reference by `(repo_id, session_id)` and revision |
| Identity fields (`user_id`, `github_username`, author e-mails) | **Never** redistribute |
| Ungated mirrors (`cfahlgren1/SWE-chat`) and SWE-Together's `original_session.json` / `oracle_session.jsonl` | **Do not use** as a route to gated content [sc §4] |

**Feasibility** (VERIFIED facts first, then estimates).

Facts:
- v2 has 17,968 session rows; about 69% are Claude Code. Codex rows lack tool calls and OpenCode rows lack tool results [sc §2.3, §4].
- Parquet `content` is truncated to 10 KB for tool results. Exact replay therefore needs raw transcripts: 33.2 GB in total, median about 0.6 MB per file [sc §3.1].
- Entire checkpoints store **no base commit**. The base must be inferred as the parent of the linked commit, which is exact only for single-commit, single-session, clean-tree cases [sc §6.3].
- 47.7% of sessions map unambiguously to commit-level lines [sc §2.6].
- Claude Code `toolUseResult` for Edit and Write carries `originalFile` and `structuredPatch`. This structure was checked in one MIT repo's checkpoint branch (CLI 0.4.2). Whether SWE-chat raw transcripts keep the fields intact must be verified after access [sc §6.5].
- Correction labels are LLM labels (Qwen3.5-9B, 0.67 four-class accuracy) and are not requirement labels [sc §2.4].

Yield anchors:

| Source | Funnel | Yield |
|---|---|---|
| SWE-Together | 48 tasks from 5,851 v1 sessions | 0.82% |
| SessionFarmer | 242 tasks from 5,851 v1 sessions (different criteria, all languages, multi-session episodes) | ≈4.1%, our arithmetic |
| Requirements After the First Edit | ~2,060 clean-start reconstructible sessions → 402 with a narrowly defined late requirement | ≈19.5%, our arithmetic; a lower bound for our purposes |

Estimate (INFERENCE, low confidence): **15–35 candidate Python tasks from v2** under our strict filters: Python, permissive licence, linked single commit, exact replay, a requirement-adding testable correction, offline tests [sc §7.1]. That supports a pilot of 10–30 tasks; a larger study likely needs other languages or sources. The first sampling step must measure these rates.

**Bounded sampling plan once access is granted** (condensed from [sc §8]):
- **Step 0, compliance.** Accept the gate with a project account. Pin the revision. Keep `(repo_id, session_id)` provenance and a removal-propagation list.
- **Step 1, footers.** Read parquet footers first.
- **Step 2, small tables.** Download them in full: about 62 MB for `repositories`, `sessions` and `checkpoints`, plus three columns of `session_logs` (a 43.7 MB file).
- **Step 3, repository filter.** Not a fork; MIT, Apache-2.0 or BSD by SPDX; Python; exclude the machine-generated repo; cap `entireio/cli` (about 16% of sessions).
- **Step 4, session filter.** Claude Code only. `kind` empty. At least 2 prompts. A canonical checkpoint with `commit_link_status = linked` and a single commit, in a single-session checkpoint. Enrich by persona without restricting on it.
- **Step 5, column-pruned conversation scan.** Pick `correction` prompts **plus a random sample of `non_pushback`** prompts that come after agent edits on `.py` files.
- **Step 6, screening.** An LLM pre-screen into three classes, then two-annotator human coding with a requirement-delta codebook.
- **Step 7, raw transcripts.** At most 200 sessions and 1 GB, skipping files over 20 MB.
- **Step 8, commits.** Read small commit columns first; fetch patches only for selected commits.
- **Step 9, pre-correction state.** Base = parent of the linked commit. Replay main-agent Edit/Write/MultiEdit calls before the correction turn, with exactness checks:
  - `old_string` unique;
  - replayed file equals `originalFile`;
  - later Reads agree;
  - full replay equals the commit tree;
  - no Bash edits to the affected files.
- **Step 10, bookkeeping.** Log every rejection reason. Stop the pilot at 30 adjudicated tasks. Store only hashes and IDs of SWE-chat content in the repository.

### 4.3 Alternatives, ranked [td §8]

| Rank | Source | Why | Caveats |
|---|---|---|---|
| 1 | **AIDev-pop** (`hao-li/AIDev` v5; CC-BY-4.0 compilation) | Human PR review comments are natural corrections. Each inline comment pins the reviewed commit (`original_commit_id`), so the pre-correction state is exact. Follow-up commits and the merged state give the accepted target. Public repos with a licence field. 291,248 inline review comments. Not used by SWE-Together | Not a chat session: the initial contract would be the PR body or linked issue. Not every comment changes a requirement. Environments need SWE-bench-style building. Consent basis is public posting, not donation |
| 2 | **pi-share-hf** datasets (e.g. `badlogicgames/pi-mono`; `MaxDevv` aggregate of 1,291 sessions) | Real chat corrections on named public repos, explicitly donated; tree-structured sessions record abandoned branches | No commit in the header, so the base must be matched by timestamp. TypeScript-heavy. Licences vary ("other" without text for the largest set). Already mined by SWE-Together (23 tasks) |
| 3 | **Trace Commons** (`trace-commons/agent-traces`; CC-BY-4.0 compilation) | Raw native files; contributor-certified open-source scope; GDPR takedown path; the cleanest rights story | 30 sessions; intake apparently stalled since June 2026; no commits; embedded-code licences are our responsibility |
| Runner-up | DataClaw datasets | Larger; SWE-Together got 29 tasks from them | No repo URL or commit; no open-source-only rule; "performance art project" framing (provider-terms risk); a possible re-upload |
| Runner-up | OpenHands feedback | 275 sessions, MIT, thumbs labels | 2024-era; state fields unknown |
| Negatives only | `nebius/SWE-rebench-openhands-trajectories` | Synthetic, replayable agent runs. `pred_passes_gen_test > 0` with `resolved = 0` gives a free pilot estimate of FA by agent-written tests | No users and no corrections. Synthetic population |
| Not available | SessionFarmer CropChat (HF 401), Trace2Eval tasks (not released), TellOnce diagnostic tasks (not found) | — | Re-check before submission |

### 4.4 Controlled-session fallback (CS-v1) [DL D4, D5, D10–D12, D14, D23], [data card]

**What it is.**
- Each scenario fixes in advance the initial request U1, the correction U2, a fixed neutral reply to clarification questions, and the intended requirements. Scenarios are written and hashed **before** the agent run and kept outside the agent's reach (registration hashes in [DL D5]).
- Intended requirements are the independent ground truth for the reference contract, subject to human review.
- State is captured between U1 and U2. That captured state is the observed pre-correction candidate.
- Transcripts are sanitized and audited for out-of-workspace file access. Ground truth is sealed while verifiers and candidates are generated [DL D12].

**Strengths.** Exact pre-correction states; pre-registered ground truth; no third-party data rights issues (MIT repositories at pinned commits).

**Limitations, to be reported:**
- Corrections are designed by the study.
- U2 arrives through a subagent message channel with coordinator framing [DL D10].
- One model family produced the sessions, contracts, verifiers, candidates and label proposals [data card].
- Results generalize only to controlled sessions [P §2].

---

## 5. Harbor integration summary (pinned 0.25.0)

Details, code line references and probe logs are in `docs/research/notes/harbor.md` [hb]. Release facts [re-checked]:
- PyPI `harbor` 0.25.0: wheel uploaded 2026-10-25T20:27:25Z; requires Python ≥3.12; license expression Apache-2.0.
- The local clone at main@3bf4cb3 (2026-11-12) is ahead of the release.
- The public error-classification docs describe main, not 0.25.0 [hb §4.3, §9].

**What we reuse.** VERIFIED on 0.25.0 by probes with a toy task, oracle and nop agents only, and zero spend [hb §8]:
- **Task format.** `instruction.md`, `task.toml` (schema 1.4), `environment/`, `tests/` and `solution/`. `[metadata]` accepts arbitrary keys (session id, requirement ids, correction turns) and survives `harbor lint --extend-select ALL`.
- **Separate verifier mode** (`[verifier] environment_mode = "separate"`). The agent container is stopped and the verifier runs in a fresh container. This mode is required for `harbor trial regrade`.
- **Artifact allowlist.** Only `/logs/artifacts/` and the paths declared in `artifacts` reach the separate verifier. They are re-materialized at their source path through a tar `data` filter that strips setuid bits and escaping symlinks. An undeclared file did not reach the verifier in the probe. Automatic `/logs/artifacts/` collection is slated for removal, so declare artifacts explicitly.
- **Reward semantics.**
  - `reward.json` (a dict of labelled numbers) takes precedence over `reward.txt`.
  - Harbor deletes both as root before the test runs, so a planted reward cannot survive.
  - The test's exit code is ignored; only the reward file counts.
  - A crash, timeout or parse error gives `verifier_result = null` with a typed `exception_info`, which 0.25.0 job aggregation excludes from the mean.
  - TraceContract treats a null result as "no decision", never as a rejection.
- **Candidate application.** Held-out candidates live under `solution/candidates/` and are applied by the Oracle agent, selected through `CANDIDATE`. They stay hidden from the agent environment and from the verifier. The nop agent scores the environment as built.
- **Regrade.** `harbor trial regrade` re-verifies a recorded trial's artifacts under a changed verifier without re-running the agent, and records the source trial. This is the primitive for scoring the same candidate under every condition.
- **Provenance.** ATIF ≤v1.8 forbids undeclared fields, so TraceContract metadata must sit in `extra` dicts.

**What we must add or replace:**
1. **Trusted grading inside the verifier container.** Harbor's isolation does not stop candidate code from writing a fake reward while the verifier runs it. A naive in-process verifier in the probe false-accepted a tampering candidate and false-rejected a valid alternative. A hardened verifier got all five toy candidates right. It ran the candidate as an unprivileged user, deleted any planted `reward.*` in a root checker before writing the true reward, and used property checks [hb §7, §8]. The repository's own grader takes the same approach:
   - candidate code runs only as an unprivileged UID that cannot read hidden tests or write results;
   - per-call results are HMAC-authenticated;
   - the host recomputes outcomes;
   - containers run with `--init`.
   
   Missing or stale results become `verifier_error`, never `pass` [DL D3, D7].
2. **Artifact transfer.** Each task declares exactly the candidate files the verifier needs. Protected test edits are discarded before grading [DL D13, D20].
3. **Network isolation.**
   - Harbor's `no-network` and `allowlist` modes need nftables egress control. On this rootless host a `no-network` trial was rejected at validation [hb §7]. That is fail-safe, but no isolated Harbor run is possible here.
   - Plain `docker run --network none` gives a loopback-only container on this host [env §6.3]. The repository grades in Docker with `--network none`, dropped capabilities, `no-new-privileges`, read-only mounts and resource limits [DL D2].
   - Exported Harbor tasks declare `no-network`. A `local-validation` variant with public network is used only for oracle and no-op checks [DL D20], STATUS.md.
4. **Error semantics.** Read `models/trial/error_policy.py` of 0.25.0, which uses `ErrorPolicy(cause, retry, grade)` and has no `override_error_policy`. Do not rely on the public docs page [hb §4.3].
5. **Not validated:** multi-step tasks, sidecar artifact collection, `harbor check` and `harbor analyze` (the last two need API keys) [hb §10].

**Status.** `harbor_export.export_task` was validated on a synthetic fixture (population `fixture`, not evidence) [DL D20]:
- `harbor lint` rc=0;
- oracle with the reference candidate → reward 1.0;
- a wrong candidate → 0.0;
- nop → 0.0.

---

## 6. Reproducibility and validity risks

| Risk | Evidence | Mitigation (planned or in place) | Residual |
|---|---|---|---|
| **Selection bias, natural data** | SWE-chat: opt-in public logging by early adopters. "If the user abandons the agent’s output entirely, session logs are not committed and thus not captured by our data." `entireio/cli` is about 16% of sessions [sc §2.2]. Published SWE-chat conversion yields are 0.82% (SWE-Together) and about 4.1% (SessionFarmer, our arithmetic). Our stricter filters (Python, permissive licence, exact replay) will likely yield less (INFERENCE). Trace2Eval excluded "continuation requests", which may be exactly the correction-bearing sessions [t2e §15] | Log every exclusion with its reason (rejection ledger). Cap sessions per repo. Report the funnel as a result | Results describe the filtered population only |
| **Selection bias, controlled data** | Corrections are designed by the study. U2 is delivered with coordinator framing [DL D10]. CS-03's correction mostly restated behaviour the agent already had [DL D18] | Separate population label. Pre-registered scenarios. Report per-task behaviour | No claim about natural correction frequency or content |
| **Approximate environments and states** | Entire stores no base commit [sc §6.3]. Bash edits cannot be replayed from Edit/Write records. Entire `REDACTED` substitutions may alter code [sc §3.3]. Trace2Eval mocked missing files and found solution leakage in 1 of 41 workspaces [t2e §9]. CS-01 adds a fixed `_version.py` (fidelity approximate) [DL D6] | Exactness checks on replay. Record `fidelity` per snapshot. Offline image builds from a pinned wheelhouse [DL D2]. Three reruns with only stable outcomes kept [P §6], [env §6.2] | Tasks with inferred bases are reported separately from exact ones |
| **Network and host dependence** | Harbor `no-network` is unavailable on this host [hb §7]. Upstream SWE-bench, SWE-smith and R2E-Gym launchers do not disable networking [env §3] | Our own launcher with `--network none` | A reproducer needs Docker. Harbor isolation must be confirmed on the target host |
| **Contamination and leakage** | Public repositories, and SWE-chat sessions public since 2026-04, may be in model training data (INFERENCE). Git-history leakage is possible without sanitization (ScaleSWE App. D) [env §2.4]. 23.0% of SWE-rebench V2's PR-derived tasks show some leakage [env §2.7]. A CS-02 agent noticed the state-capture folder [DL D23] | `git archive` exports without history [DL D5]. Ground truth sealed during generation and generator transcripts audited [DL D12]. Captures stored outside the workspace | Model memorization of public repos cannot be ruled out |
| **Model-generated test and candidate bias** | One model family produces sessions, contracts, verifiers, candidates and label proposals [data card], [P §10]. 61.9% of LLM hardening tests failed on the gold patch [vf A8]. SessionFarmer's refinement raised FPR by 16–17.5 pp [nc §3.1]. 42.7% of generated suites could not distinguish competing readings (decision pins, abs) | Gate tests on the reference and on alternatives. Report FR. Stratify negatives by origin. A second model family would need approved spend (§8) | Correlated errors across conditions and labels remain possible |
| **LLM annotations are proposals, not ground truth** | SWE-chat pushback labels have 0.67 four-class accuracy [sc §2.4]. SessionFarmer FP/FN rest on gpt-6-astra labels. VerifierBench uses construction labels. PersonaCodeBench requirement judgments reach κ 0.473 against experts. CAB's judge agrees 65.92% vs 78.28% inter-human [cor §5.2] | Rule D19: proposed labels need agreement of three sources, otherwise `ambiguous`; `labeler_kind = model`; model labels never override human ones [DL D19]. Pilot results always marked "automated pilot" [P §5] | No validated result until human labels exist |
| **Single-annotator risk** | SWE-bench Verified false_negative labels: Fleiss κ ≈ 0.41 by recomputation; max-severity ensembling raised flag rates from 39% to 61% [vf A1]. TellOnce's diagnostic corpus comes from one user [cor §2.3]. Trace2Eval's adjudicator saw both annotators' grades, so Human–GT agreement is partly built in [t2e §8] | A second annotator on an overlap subset, blind to verifier outputs and to the first annotator. A pre-specified adjudication rule (not max-severity) | Agreement is unknown until piloted |
| **Circular labels** | D19's regression norm uses base-commit tests that also appear in B1, which can favour B1 on regression-only negatives [DL D19] | Report negatives by type | B1 comparisons on regression negatives must be read with care |
| **Simulator confound** | SWE-Together Intent Coverage is about 0.70. LLM simulators are "excessively cooperative" (Sim2Real, abs) [cor §6] | Freeze contracts and score fixed candidates; no simulator in the core measurement | — |
| **Small N and power** | Expected natural yield is tens of tasks. The pilot has 4 controlled families [P §3] | Cluster bootstrap over families. Descriptive pilot. A confirmatory size is set only after the pilot [P §9] | Pilot intervals are not evidence of effects |
| **Moving prior work** | The closest works are days old: SessionFarmer (11-02), PersonaCodeBench (11-03), Trace2Eval (11-04), ARE-bench (11-10). SessionFarmer and VibeSWEBench details are unverifiable. The SF Data essay's revision history is unknown | Re-run the novelty search and re-read these works before any submission | Novelty can still erode |

---

## 7. Cost estimates and the smallest useful implementation

### 7.1 Compute

**Known facts:**
- **Host** [DL D2]: 4 CPUs, 15 GiB RAM, about 31 GB free disk, no GPU.
- **Harbor timings** on a toy task [hb §8]:
  - one trial with a separate verifier takes about 30 s;
  - a regrade takes about 15 s;
  - a 6-trial job takes about 85 s.
  
  These toy timings do not represent real repository suites.
- **Repository suites** in the sandbox at the pinned commits: CS-01 741 passed, CS-02 227, CS-03 467, CS-04 771 [DL D8]. B1 for CS-01 has 737 checks [DL D13].
- Per-call grading time for the repository's own grader is **not yet measured**. No timing field exists in the recorded audit results.

**Planning arithmetic (ASSUMPTION, to be replaced by measurements):**
- Per family: 6 conditions × about 10 evaluation candidates × 3 reruns ≈ 180 grading calls, plus sanity checks.
- At an assumed 0.5–3 min per call, that is about 1.5–9 CPU-hours per family.
- A 4-family pilot needs about 6–36 CPU-hours, which fits on this host.

**Data volume:**
- The whole SWE-chat repository is 47 GB, which exceeds the free disk, so it must not be mirrored.
- The bounded plan (§4.2) reads about 62 MB of small tables, column-pruned conversation columns (estimated at hundreds of MB, INFERENCE) and at most about 1 GB of raw transcripts.

### 7.2 Annotation hours (ASSUMPTION; the pilot measures them, annotation guide §3)

| Item | Planning range |
|---|---|
| Read one source session | 20–40 min |
| Review its reference contract (evidence, status, supersession, observability) | 20–40 min |
| Label about 8–10 evaluation candidates at 5–10 min each | 40–100 min |
| **Per annotator per task family** | **about 1.5–3 h** |
| Second annotator on an overlap subset, plus adjudication of disagreements | about +30–40% of the first-annotator total (if about 30% of families overlap, plus adjudication) |
| 4 controlled families (pilot) | about 6–12 h, plus about 2–4 h of overlap |
| 30 natural families | about 45–90 h, plus about 15–30 h of overlap and adjudication |
| Natural-data screening: human coding of a few hundred candidate correction prompts with the requirement-delta codebook | about 10–25 h at 2–5 min each |

For orientation only (these are different jobs, not our tasks):
- Terminal-Bench 2.0 used "about 3 reviewer-hours per task" for task review [vf A13].
- SWE-Gym spent about 200 annotation hours on environment configuration [env §2.5].
- SWE-smith spent about 20 hours of one author's time [env §2.1].

### 7.3 API spend

**Zero by default.** No paid API key is configured. Model-generated artifacts are produced by this Claude Code session's own subagents and recorded with prompts and outputs [DL D2].

Excluded unless the owner approves spending:
- `harbor check` and `harbor analyze`;
- a second model family for generators or labels;
- a stronger held-out attacker (hacker-fixer weak-to-strong design);
- LLM patch labelling of the gpt-6-astra kind;
- re-running a SessionFarmer-style pipeline with external models.

For orientation only, other pipelines report per-instance costs, which are not estimates for ours:
- SWE-ABS $4.98 per strengthened instance;
- UTBoost $1.6 per instance [vf];
- SWE-Factory $0.047 per instance environment build with GPT-4.1-mini [env §2.8];
- SWE-smith $1,360 in total [env §2.1].

### 7.4 Smallest useful implementation (first end-to-end case)

**Controlled first case: CS-01** (humanize `naturalsize`).
- The task is already compiled: session, snapshot, reference contract pending human review, natural candidates, and the B1 verifier (STATUS.md).
- The correction supersedes a default: "keep the default output exactly as before; make trimming opt-in" (README).

End-to-end steps:
1. Recover the initial-only and full contracts with `contract:v1` (the full contract has 9 requirements, 0 rejected [DL D17]).
2. Generate C1/C3 and B2, then audit C2/C4 with development candidates only. Freeze all six verifiers.
3. Generate evaluation candidates after freezing: the observed pre-correction state, 2 valid alternatives, 4–6 near misses, plus no-op and reference as sanity.
4. Grade every candidate under every condition in the sandbox with network off.
5. Produce an FA/FR table marked "automated pilot", using D19 labels and denominators.
6. Have one human review the contract and label all candidates (about 2–3 h). Then recompute FA/FR on human labels and report the model-vs-human label disagreement.
7. Optionally export one condition to Harbor and regrade the recorded candidates under the other conditions.

**Done when:**
- every evaluation candidate has an outcome under every condition, and no `verifier_error` is unexplained;
- every evaluation candidate has a human label;
- the report shows denominators and separates infrastructure outcomes.

**First natural case (after SWE-chat access).** One Claude Code session meeting all of these: a permissively licensed Python repository, a linked single-commit single-session checkpoint, and a correction that adds or overrides a testable requirement after agent edits. Reconstruct S_pre by replay with all exactness checks (§4.2 step 9), then run the same pipeline. Report it under the natural population label.

---

## 8. Open questions requiring the human researcher's decision

1. **SWE-chat access.** Will you accept the dataset terms? Accepting shares your Hugging Face username and e-mail with the dataset authors. If yes, supply a valid read token; the saved token currently fails authentication [DL D4]. Otherwise, should the pilot stay controlled-only, with the claim limited accordingly?
2. **Annotators.** Decide:
   - who labels, with what qualifications and time budget;
   - who is the second annotator for the overlap subset, and what fraction overlaps;
   - which adjudication rule applies;
   - whether external annotators are used, and on what terms.
3. **Primary estimand and stopping rules.** Confirm FA on observed pre-correction states (C1 vs C3, C2 vs C4) as primary, with an FR cap on valid alternatives. Fix the confirmatory number of families after the pilot; the "60–100" figure is a placeholder [P §9].
4. **Scope of the claim.** Confirm the narrowed measurement claim (D25) and the venue or timing, given that the closest works appeared on 2–10 Nov 2026 and may be revised.
5. **Spending.** Keep API spend at zero, or approve a limited budget for:
   - a second model family (generators or label proposals);
   - a stronger held-out attacker;
   - `harbor check` and `harbor analyze`.
6. **Additional data arms.**
   - Add an AIDev-pop arm (PR review comments as corrections)?
   - Use pi-share-hf or Trace Commons sessions?
   - Use SWE-Together's Apache-2.0 tasks for cross-checks, even though they ship session content outside the SWE-chat gate?
7. **Outreach.** Contact authors? This involves outreach on your behalf. Possible contacts:
   - SessionFarmer, for code, data, and how the requirement ledger was built;
   - SWE-chat, for the unreleased replay code, the licence registry and the gate conditions;
   - TRACE (Kang et al.), about the mining split and baselines;
   - Trace2Eval, for the q prompt.
8. **Name.** Rename the project or disambiguate it explicitly from *TraceContract: A Scala DSL for Trace Analysis* (FM 2011)?
9. **Licences.** Choose a licence for the repository's code, and one for released tasks and labels. Both must be compatible with ODC-BY notices and per-repository code licences.
10. **Harbor version and isolation standard.**
    - Stay on 0.25.0, or move to a newer release (`override_error_policy`, serialized `reward_valid`)?
    - Accept plain Docker `--network none` as the isolation standard, or require a host with nftables egress control for Harbor runs?
11. **Optional extensions.**
    - Exploit-style candidates (tampering, hard-coded outputs) in the held-out pool, reported separately.
    - Comparison of in-session user approval signals with human labels.
    - A downstream-value proxy, such as verifier-guided best-of-n selection scored against labels. There is no GPU.
12. **Industry framing.** How should the paper cite the SF Data essay, a company blog post whose revision history cannot be checked?

---

## 9. Source list

- Every source below was accessed on **2026-11-13 (UTC)**.
- "Depth": full = full text read (all or named sections); partial = targeted sections; abs = abstract or landing page only; data = metadata, card or code inspected; not retrieved = blocked.
- [re-checked] = re-opened in this synthesis step.
- Keys match the citation list returned with this draft.

### 9.1 Primary sources cited in §1–§8

| Key | Source | URL | Version / publication date | Accessed | Depth | Notes |
|---|---|---|---|---|---|---|
| sfdata2026home | SF Data homepage | https://www.sfdata.com/ | No content date; last-modified 2026-11-12 | 2026-11-13 | full [re-checked] | [sf] |
| guo2026productiontraces | Guo, Siddiqi, "Production traces and the future of data" | https://www.sfdata.com/blog/production-traces/ | Byline 2026-10-01; last-modified 2026-11-11 | 2026-11-13 | full [re-checked] | [sf] |
| lu2026sessionfarmer | Lu et al., "Harvesting SWE Benchmarks from Wild Vibe Coding Sessions" | https://arxiv.org/abs/2611.02440 | v1 2026-11-02 | 2026-11-13 | full (sections) [re-checked] | [nc] |
| wu2026swetogether | Wu et al., "SWE-Together: Evaluating Coding Agents in Interactive User Sessions" | https://arxiv.org/abs/2606.29957 | v1 2026-06-29 (HTML date line "September 30, 2026") | 2026-11-13 | full §1–5 [re-checked] | [sc][cor] |
| shi2026trace2eval | Shi et al., "Trace2Eval: Contextualized Evaluation of Coding Agents from Real-World Traces" | https://arxiv.org/abs/2611.06506 | v1 2026-11-04 | 2026-11-13 | full [re-checked] | [t2e] |
| traj2envs2026 | Hugging Face, traj2envs (tool) and traj2envs-rl (suite) | https://github.com/huggingface/traj2envs ; https://huggingface.co/datasets/harness-hub/traj2envs-rl | HEAD a09204ed 2026-11-05; suite 2026-11-06 | 2026-11-13 | data (code, docs, suite metadata) [re-checked] | [td] |
| paltenghi2026aftervibe | Paltenghi, Chandra, "AfterVibe: What Remains When the Conversation Ends" | https://arxiv.org/abs/2607.09900 | v1 2026-07-10 | 2026-11-13 | partial [re-checked abs] | [cor][nc] |
| jha2026reap | Jha et al., "REAP: Automatic Curation of Coding Agent Benchmarks from Interactive Production Usage" | https://arxiv.org/abs/2604.01527 | v1 2026-04-02 … v4 2026-07-28; ASE 2026 Industry Showcase (comment) | 2026-11-13 | partial [re-checked abs] | [nc] |
| lv2026realclawbench | Lv et al., "RealClawBench: Live OpenClaw Benchmarks from Real Developer-Agent Sessions" | https://arxiv.org/abs/2606.03889 | v1 2026-06-02; v3 2026-08-28 | 2026-11-13 | partial | [cor][sc] |
| lin2026arebench | Lin et al., "ARE-bench: Benchmarking Agents' Research Ability in Real-World Researcher Sessions and Workspaces" | https://arxiv.org/abs/2611.14364 | v1 2026-11-10 | 2026-11-13 | partial [re-checked Table 8] | [nc] |
| wu2026terminaluniverse | Wu et al., "Terminal-Universe: Turning Agent Trajectories into Scalable Terminal Environments" | https://arxiv.org/abs/2609.04148 | v1 2026-09-03 | 2026-11-13 | partial | [nc] |
| chu2026terminalworld | Chu et al., "TerminalWorld: Benchmarking Agents on Real-World Terminal Tasks" | https://arxiv.org/abs/2605.22535 | v1 2026-05-21; v2 2026-11-04 | 2026-11-13 | abs | [t2e] |
| liu2026secureforge | Liu et al., "SecureForge: Finding and Preventing Vulnerabilities in LLM-Generated Code via Prompt Optimization" | https://arxiv.org/abs/2605.08382 | v1 2026-05-08 | 2026-11-13 | partial | [sc] |
| islam2026vibeswebench | Islam, Ali, Du, Parvez, "VibeSWEBench: Can AI Co-Worker Agents Do Real-World Software Engineering by Vibe Coding?" | https://icml.cc/virtual/2026/82740 | ICML 2026 workshop; date not stated | 2026-11-13 | abs | [nc] |
| min2026tracedance | Min et al., "TraceDance: An Automated System for Building Agent Behavior Benchmarks from Real-World Agent Deployment Traces" | https://arxiv.org/abs/2609.33295 | v1 2026-09-27 | 2026-11-13 | partial | [nc] |
| niu2026dumatebench | Niu et al., "DuMateBench: Evaluating Autonomous Agents in Complex Real-World Workflows" | https://arxiv.org/abs/2608.26546 | v1 2026-08-27 | 2026-11-13 | abs | [nc] |
| zhong2026enterpriseclawbench | Zhong et al., "EnterpriseClawBench: Benchmarking Agents from Real Workplace Sessions" | https://arxiv.org/abs/2606.23654 | v1 2026-06-22 | 2026-11-13 | abs | [nc] |
| baumann2026swechat | Baumann et al., "SWE-chat: Coding Agent Interactions From Real Users in the Wild"; dataset SALT-NLP/SWE-chat | https://arxiv.org/abs/2604.20779 ; https://huggingface.co/datasets/SALT-NLP/SWE-chat | v1 2026-04-22; v2 2026-10-01; dataset rev 202b071f (lastModified 2026-10-03) | 2026-11-13 | full; card and API [re-checked] | [sc] |
| odcby10 | Open Data Commons Attribution License v1.0 | https://opendatacommons.org/licenses/by/1-0/ | v1.0 | 2026-11-13 | full (§2–4) | [sc] |
| entire2026cli | Entire CLI source and docs | https://github.com/entireio/cli ; https://docs.entire.io/guides/checkpoints/checkpoint-storage.md | HEAD ce16562 (2026-11-12, v0.13.3) | 2026-11-13 | partial | [sc] |
| li2026aidev | Li, Zhang, Hassan, AIDev papers and dataset v5 | https://arxiv.org/abs/2507.15003 ; https://arxiv.org/abs/2602.09185 ; https://huggingface.co/datasets/hao-li/AIDev | 2025-07-20; 2026-02-09; v5 cutoff 2026-03-31, lastModified 2026-10-21 | 2026-11-13 | abs / partial / card | [td] |
| tracecommons2026 | Trace Commons, agent-traces | https://huggingface.co/datasets/trace-commons/agent-traces | sha 112ebd4d; 2026-06-11 / 2026-06-18 | 2026-11-13 | card and metadata | [td] |
| pishare2026 | pi-share-hf README and session datasets | https://raw.githubusercontent.com/badlogic/pi-share-hf/main/README.md ; https://huggingface.co/datasets/badlogicgames/pi-mono ; https://huggingface.co/datasets/MaxDevv/real-pi-coding-agent-traces-sessions | README undated; 2026-04-06; 2026-07-19 | 2026-11-13 | cards | [td] |
| dataclaw2026 | DataClaw exporter and datasets | https://raw.githubusercontent.com/banodoco/dataclaw/main/README.md | README undated; datasets e.g. 2026-02-24 | 2026-11-13 | cards | [td] |
| openhands2024feedback | OpenHands Feedback Dataset | https://huggingface.co/datasets/OpenHands/openhands-feedback | 2024-12-06 / 2024-12-14 | 2026-11-13 | card | [td] |
| xiao2023devgpt | Xiao, Treude, Hata, Matsumoto, "DevGPT" | https://arxiv.org/abs/2309.03914 ; Zenodo 10.5281/zenodo.10086809 | v2 2024-02-14; Zenodo 2023-11-09 | 2026-11-13 | abs and metadata | [td] |
| nebius2025openhandstraj | nebius/SWE-rebench-openhands-trajectories | https://huggingface.co/datasets/nebius/SWE-rebench-openhands-trajectories | 2025-09-22 / 2025-12-27 | 2026-11-13 | card | [td] |
| cooperbench2026swechatcoop | CooperBench/swechat-coop | https://huggingface.co/datasets/CooperBench/swechat-coop | 2026-05-25 | 2026-11-13 | API metadata only | [sc] |
| cfahlgren2026swechatmirror | cfahlgren1/SWE-chat (ungated mirror; not to be used) | https://huggingface.co/datasets/cfahlgren1/SWE-chat | 2026-04-28 / 2026-09-25 | 2026-11-13 | card only | [sc] |
| liu2026tiganeval | Liu et al., "Instructions Are Evidence, Not Objectives: Measuring Outcome Alignment of Agents" | https://arxiv.org/abs/2610.17757 | v1 2026-10-13 | 2026-11-13 | partial | [nc] |
| jiang2026reqfirstedit | Jiang et al., "Requirements After the First Edit: Mining Late Requirement Emergence and Rework in Real-World Coding-Agent Sessions" | https://arxiv.org/abs/2609.03028 | v1 2026-09-02 | 2026-11-13 | partial | [nc] |
| anthropic2026autonomy | Anthropic Societal Impacts, "Measuring AI agent autonomy in practice" | https://www.anthropic.com/research/measuring-agent-autonomy | 2026-02-18 | 2026-11-13 | full | [cor] |
| harbor2026 | Harbor Framework Team, Harbor v0.25.0 (DOI 10.5281/zenodo.20953922) and docs | https://pypi.org/project/harbor/0.25.0/ ; https://github.com/harbor-framework/harbor ; https://docs.harborframework.com | 0.25.0 2026-10-25; main@3bf4cb3 2026-11-12 | 2026-11-13 | code, docs, probes [re-checked PyPI] | [hb] |
| atif2026rfc | ATIF RFC 0001 (in the Harbor repo) | local clone `rfcs/0001-trajectory-format.md` | v1.8, "April 2026" | 2026-11-13 | partial | [hb] |
| yang2025swesmith | Yang et al., "SWE-smith: Scaling Data for Software Engineering Agents" | https://arxiv.org/abs/2504.21798 | v1 2025-04-30; v2 2025-05-21; code @9b74ac0 (2026-03-21 author / 2026-03-22 committer) | 2026-11-13 | full; code [re-checked commit] | [env] |
| jain2025r2egym | Jain et al., "R2E-Gym: Procedural Environments and Hybrid Verifiers for Scaling Open-Weights SWE Agents" | https://arxiv.org/abs/2504.07164 | v1 2025-04-09; code @0d94c4e (2025-07-13) | 2026-11-13 | full; code | [env] |
| pan2024swegym | Pan et al., "Training Software Engineering Agents and Verifiers with SWE-Gym" | https://arxiv.org/abs/2412.21139 | v1 2024-12-30; v2 2025-06-06 | 2026-11-13 | full (sections) | [env] |
| badertdinov2025swerebench | Badertdinov et al., "SWE-rebench: An Automated Pipeline for Task Collection and Decontaminated Evaluation of Software Engineering Agents" | https://arxiv.org/abs/2505.20411 | v1 2025-05-26; v2 2025-11-04 | 2026-11-13 | full (sections) | [env][vf] |
| badertdinov2026swerebenchv2 | Badertdinov et al., "SWE-rebench V2: Language-Agnostic SWE Task Collection at Scale" | https://arxiv.org/abs/2602.23866 | v1 2026-02-27; v2 2026-06-01 | 2026-11-13 | full (sections) | [env] |
| guo2025swefactory | Guo et al., "SWE-Factory: Your Automated Factory for Issue Resolution Training Data and Evaluation Benchmarks" | https://arxiv.org/abs/2506.10954 | v1 2025-06-12; v3 2026-01-05 | 2026-11-13 | full (sections) | [env] |
| chen2026sweuniverse | Chen et al., "SWE-Universe: Scale Real-World Verifiable Environments to Millions" | https://arxiv.org/abs/2602.02361 | v1 2026-02-02; v2 2026-09-21 | 2026-11-13 | full | [env] |
| wang2025swebenchpp | Wang et al., "SWE-Bench++: A Framework for the Scalable Generation of Software Engineering Benchmarks from Open-Source Repositories" | https://arxiv.org/abs/2512.17419 | v1 2025-12-19 | 2026-11-13 | full (sections) | [env] |
| zhao2026scaleswe | Zhao et al., "Immersion in the GitHub Universe: Scaling Coding Agents to Mastery" | https://arxiv.org/abs/2602.09892 | v1 2026-02-10; v4 2026-03-24 | 2026-11-13 | full (sections) | [env] |
| zeng2026swehub | Zeng et al., "SWE-Hub: A Unified Production System for Scalable, Executable Software Engineering Tasks" | https://arxiv.org/abs/2603.00575 | v1 2026-02-28 | 2026-11-13 | full | [env] |
| chen2025repoforge | Chen et al., "RepoForge: Training a SOTA Fast-thinking SWE Agent with an End-to-End Data Curation Pipeline Synergizing SFT and RL at Scale" | https://arxiv.org/abs/2508.01550 | v1 2025-08-03; v2 2025-09-03 | 2026-11-13 | partial | [env] |
| zan2025multiswebench | Zan et al., "Multi-SWE-bench: A Multilingual Benchmark for Issue Resolving" | https://arxiv.org/abs/2504.02605 | v1 2025-04-03 | 2026-11-13 | partial | [env] |
| zhang2025sweflow | Zhang et al., "SWE-Flow: Synthesizing Software Engineering Data in a Test-Driven Manner" | https://arxiv.org/abs/2506.09003 | v1 2025-06-10; v2 2025-06-11 | 2026-11-13 | partial | [env] |
| du2025swedev | Du et al., "SWE-Dev: Evaluating and Training Autonomous Feature-Driven Software Development" | https://arxiv.org/abs/2505.16975 | v1 2025-05-22; v3 2026-02-06 | 2026-11-13 | partial | [env] |
| wang2025swedev | Wang et al., "SWE-Dev: Building Software Engineering Agents with Training and Inference Scaling" | https://arxiv.org/abs/2506.07636 | v1 2025-06-09; v2 2025-06-23 | 2026-11-13 | partial | [env] |
| jimenez2023swebench | Jimenez et al., "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?"; HF card princeton-nlp/SWE-bench | https://arxiv.org/abs/2310.06770 ; https://huggingface.co/datasets/princeton-nlp/SWE-bench | v1 2023-10-10; card sha e48e2bd (2025-03-03) | 2026-11-13 | abs; card | [vf][cor] |
| swebench2026harness | SWE-bench harness (swebench 5.0.2) | https://github.com/SWE-bench/SWE-bench | @02e7a74 (2026-09-02) | 2026-11-13 | code (partial) | [env] |
| yin2026verifierbench | Yin et al., "VerifierBench: Benchmarking the Generation of Executable Verifiers for LLM Agents" | https://arxiv.org/abs/2610.28679 | v1 2026-10-19; v2 2026-10-30 | 2026-11-13 | full (sections) [re-checked] | [nc] |
| zhong2026hackerfixer | Zhong et al., "Hardening Agent Benchmarks with Adversarial Hacker-Fixer Loops"; harden-v0 | https://arxiv.org/abs/2606.08960 ; https://github.com/few-sh/harden-v0 | v1 2026-06-08; harden-v0 @342b847 (2026-07-03) | 2026-11-13 | full; code [re-checked abs] | [vf] |
| tb2026review | Terminal-Bench TB3 task review automation (`docs/TASK_REVIEW_AUTOMATION.md`) | local clone of https://github.com/harbor-framework/terminal-bench | main@01c0d6d (2026-11-12) | 2026-11-13 | full [re-checked commit] | [vf] |
| buchanan2026benchsoftware | Buchanan, Zhou, Linderman, Ré, "Benchmarks as Software: Terminal-Bench and the Case for Continuous Benchmarks" | https://arxiv.org/abs/2611.08417 | v1 2026-11-05 | 2026-11-13 | full | [vf] |
| merrill2026terminalbench | Merrill et al., "Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks in Command Line Interfaces" | https://arxiv.org/abs/2601.11868 | v1 2026-01-17 | 2026-11-13 | partial | [vf] |
| yu2026sweabs | Yu et al., "SWE-ABS: Adversarial Benchmark Strengthening Exposes Inflated Success Rates on Test-based Benchmark" | https://arxiv.org/abs/2603.00520 | v1 2026-02-28 | 2026-11-13 | full | [vf] |
| li2026probe | Li et al., "Probe to Generate: Program Variant-Guided Test Augmentation for Repository-Level Repair Benchmarks" | https://arxiv.org/abs/2604.01518 | v1 2026-04-02; v2 2026-08-06 | 2026-11-13 | full | [vf] |
| wang2025patchdiff | Wang, Pradel, Liu, "Are 'Solved Issues' in SWE-bench Really Solved Correctly? An Empirical Study" | https://arxiv.org/abs/2503.15223 | v1 2025-03-19; v2 2025-09-09 | 2026-11-13 | full | [vf] |
| yu2025utboost | Yu, Zhu, He, Kang, "UTBoost: Rigorous Evaluation of Coding Agents on SWE-Bench" | https://arxiv.org/abs/2506.09289 | v1 2025-06-10 | 2026-11-13 | full | [vf] |
| aleithan2024swebenchplus | Aleithan et al., "SWE-Bench+: Enhanced Coding Benchmark for LLMs" | https://arxiv.org/abs/2410.06992 | v1 2024-10-09; v2 2024-10-10 | 2026-11-13 | full | [vf] |
| openai2024swebenchverified | OpenAI, "Introducing SWE-bench Verified"; annotation results zip; HF card | https://openai.com/index/introducing-swe-bench-verified/ ; https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip ; https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified | Blog 2024-08-13 (snippet); zip Last-Modified 2024-08-12; card 2024-08-13 / 2025-02-18 | 2026-11-13 | blog not retrieved (403); data analyzed | [vf] |
| rajan2026hackability | Rajan, "Auditing Reward Hackability in Code RL Training Environments" | https://arxiv.org/abs/2606.16062 | v1 2026-06-14 | 2026-11-13 | full | [vf] |
| yao2026testjack | Yao et al., "TestJack: ... Agentic Coding Benchmarks Auditing via Evaluator Evolution" | https://arxiv.org/abs/2610.10619 | v1 2026-10-07 | 2026-11-13 | partial | [nc] |
| wu2026userswe | Wu et al., "UserSWE: Evaluating Coding Agents in Multi-Turn Conversations with Dynamic Users" | https://arxiv.org/abs/2610.29822 | v1 2026-10-21 | 2026-11-13 | partial | [nc] |
| zhong2025impossiblebench | Zhong, Raghunathan, Carlini, "ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases" | https://arxiv.org/abs/2510.20270 | v1 2025-10-23 | 2026-11-13 | full | [vf] |
| gabor2025evilgenie | Gabor, Lynch, Rosenfeld, "EvilGenie: A Reward Hacking Benchmark" | https://arxiv.org/abs/2511.21654 | v1 2025-11-26; v2 2026-05-17 | 2026-11-13 | full | [vf] |
| wang2026benchjack | Wang et al., "Do Androids Dream of Breaking the Game? Systematically Auditing AI Agent Benchmarks with BenchJack" | https://arxiv.org/abs/2605.12673 | v1 2026-05-12 | 2026-11-13 | abs | [vf][t2e] |
| bercovich2026terminalwrench | Bercovich et al., "Terminal Wrench: A Dataset of 331 Reward-Hackable Environments and 3,632 Exploit Trajectories" | https://arxiv.org/abs/2604.17596 | v1 2026-04-19 | 2026-11-13 | abs | [vf] |
| wang2025codecontestsplus | Wang et al., "CodeContests+: High-Quality Test Case Generation for Competitive Programming" | https://arxiv.org/abs/2506.05817 | v1 2025-06-06 | 2026-11-13 | partial | [vf] |
| he2025hardtests | He et al., "HARDTESTGEN: A High-Quality RL Verifier Generation Pipeline for LLM Algorithmic Coding" | https://arxiv.org/abs/2505.24098 | v1 2025-05-30; v2 2026-11-08 | 2026-11-13 | partial | [vf] |
| wang2026verificationhorizon | Wang et al., "The Verification Horizon: No Silver Bullet for Coding Agent Rewards" | https://arxiv.org/abs/2606.26300 | v1 2026-06-24; v2 2026-06-29 | 2026-11-13 | §2 and §4 [re-checked abs] | [vf][env] |
| deng2025swebenchpro | Deng et al., "SWE-Bench Pro: Can AI Agents Solve Long-Horizon Software Engineering Tasks?" | https://arxiv.org/abs/2509.16941 | v1 2025-09-21; v2 2025-11-14 | 2026-11-13 | full | [vf] |
| mundler2024swtbench | Mündler et al., "SWT-Bench: Testing and Validating Real-World Bug-Fixes with Code Agents" | https://arxiv.org/abs/2406.12952 | v1 2024-06-18; v3 2025-02-07 | 2026-11-13 | full | [vf] |
| ahmed2025otter | Ahmed et al., "Otter: Generating Tests from Issues to Validate SWE Patches" | https://arxiv.org/abs/2502.05368 | v1 2025-02-07; v2 2025-05-30 | 2026-11-13 | full | [vf] |
| mitsui2026decisionpins | Mitsui, "Pinning Decisions Before Failure: Executable Records of Underspecified Choices in AI-Assisted Code Generation" | https://arxiv.org/abs/2610.03237 | v1 2026-10-02 | 2026-11-13 | abs | [nc] |
| zhang2026leakyreward | Zhang, "When the Reward Suite Is Leaky: A Preregistered Causal Contrast of Natural Verifier False Positives in RLVR" | https://arxiv.org/abs/2607.11022 | v1 2026-07-13 | 2026-11-13 | abs | [nc] |
| zhu2025abc | Zhu et al., "Establishing Best Practices for Building Rigorous Agentic Benchmarks" | https://arxiv.org/abs/2507.02825 | v1 2025-07-03; v5 2025-08-07 | 2026-11-13 | partial | [vf] |
| rad2026rlver | Rad et al., "Rate or Fate? RLVεR: Reinforcement Learning with Verifiable Noisy Rewards" | https://arxiv.org/abs/2601.04411 | v1 2026-01-07 | 2026-11-13 | abs | [vf] |
| wang2025truncauc | Wang, Joshi, Plank, Angell, He, "Is It Thinking or Cheating? Detecting Implicit Reward Hacking by Measuring Reasoning Effort" | https://arxiv.org/abs/2510.01367 | v1 2025-10-01; v4 2026-03-02 | 2026-11-13 | abs [re-checked] | [td] |
| zhou2026tellonce | Zhou et al., arXiv:2606.13174 v1 "Getting Better at Working With You ..." / v2 "TellOnce ..."; repos TellOnce_exp, tellonce | https://arxiv.org/abs/2606.13174 ; https://github.com/YujunZhou/TellOnce_exp ; https://github.com/YujunZhou/tellonce | v1 2026-06-11; v2 2026-10-25; repos abc78f7 (2026-10-23), v1.8.3 b918869 (2026-10-24) | 2026-11-13 | full [re-checked abs] | [cor] |
| wang2026personacodebench | Wang et al., "PersonaCodeBench: Evaluating Coding Agents in Persona-driven Human-Interactive Sessions" | https://arxiv.org/abs/2611.05739 | v1 2026-11-03 | 2026-11-13 | full (sections) [re-checked] | [cor] |
| feng2026featureloop | Feng et al., "Benchmarking Coding Agents under Evolving Requirements" | https://arxiv.org/abs/2610.35488 | v1 2026-10-26; v2 2026-10-29 | 2026-11-13 | partial [re-checked abs] | [cor] |
| shen2026evocodebench | Shen et al., "EvoCode-Bench: Evaluating Coding Agents in Multi-Turn Iterative Interactions" | https://arxiv.org/abs/2605.24110 | v1 2026-05-22 | 2026-11-13 | partial | [cor] |
| zhan2025sreval | Zhan et al., "SR-Eval: Evaluating LLMs on Code Generation under Stepwise Requirement Refinement" | https://arxiv.org/abs/2509.18808 | v1 2025-09-23; v2 2026-03-17 | 2026-11-13 | partial | [cor] |
| kim2025codeassistbench | Kim et al., "CodeAssistBench (CAB): Dataset & Benchmarking for Multi-turn Chat-Based Code Assistance" | https://arxiv.org/abs/2507.10646 | v1 2025-07-14; v5 2026-01-15 | 2026-11-13 | partial | [cor] |
| wang2025codeifbench | Wang et al., "CodeIF-Bench: Evaluating Instruction-Following Capabilities of Large Language Models in Interactive Code Generation" | https://arxiv.org/abs/2503.22688 | v1 2025-03-05; v4 2025-11-23 | 2026-11-13 | partial | [cor] |
| wu2025frontalk | Wu et al., "FronTalk: Benchmarking Front-End Development as Conversational Code Generation with Multi-Modal Feedback" | https://arxiv.org/abs/2601.04203 | v1 2025-12-05; v3 2026-08-09 | 2026-11-13 | partial | [cor] |
| raghavendra2026sweinteract | Raghavendra et al., "SWE-INTERACT: Reimagining SWE Benchmarks as User-Driven Long-Horizon Coding Sessions" | https://arxiv.org/abs/2606.30573 | v1 2026-06-29 | 2026-11-13 | partial | [cor][sc] |
| wu2026specpath | Wu et al., "SpecPath: Testing Coding Agents Across Contract-Equivalent Specification Histories" | https://arxiv.org/abs/2608.09799 | v1 2026-08-10 | 2026-11-13 | partial | [nc] |
| vijayvargiya2025ambigswe | Vijayvargiya et al., "Ambig-SWE: Interactive Agents to Overcome Underspecificity in Software Engineering" | https://arxiv.org/abs/2502.13069 | v1 2025-02-18; v3 2026-02-21 | 2026-11-13 | partial | [cor] |
| king2026dialogueswebench | King, Flanigan, "Dialogue SWE-Bench: A Benchmark for Dialogue-Driven Coding Agents" | https://arxiv.org/abs/2606.13995 | v1 2026-06-12 | 2026-11-13 | partial | [cor] |
| wang2023mint | Wang et al., "MINT: Evaluating LLMs in Multi-turn Interaction with Tools and Language Feedback" | https://arxiv.org/abs/2309.10691 | v1 2023-09-19; v3 2024-03-12 | 2026-11-13 | partial | [cor] |
| han2025convcodeworld | Han et al., "ConvCodeWorld: Benchmarking Conversational Code Generation in Reproducible Feedback Environments" | https://arxiv.org/abs/2502.19852 | v1 2025-02-27 | 2026-11-13 | partial | [cor] |
| zhou2025sweetrl | Zhou et al., "SWEET-RL: Training Multi-Turn LLM Agents on Collaborative Reasoning Tasks" | https://arxiv.org/abs/2503.15478 | v1 2025-03-19 | 2026-11-13 | partial | [cor] |
| lahiri2022ticoder | Lahiri et al., "Interactive Code Generation via Test-Driven User-Intent Formalization" | https://arxiv.org/abs/2208.05950 | v1 2022-08-11; v2 2023-10-04 | 2026-11-13 | abs and grep | [cor] |
| fakhoury2024ticodertse | Fakhoury et al., "LLM-Based Test-Driven Interactive Code Generation: User Study and Empirical Evaluation" | https://arxiv.org/abs/2404.10100 | v2 2024-10-02; IEEE TSE 50(09) 2024 | 2026-11-13 | partial | [cor] |
| zhou2025tomswe | Zhou et al., "ToM-SWE: User Mental Modeling for Software Engineering Agents" | https://arxiv.org/abs/2510.21903 | v1 2025-10-24; v2 2026-01-29 | 2026-11-13 | partial | [cor] |
| wang2026asukabench | Wang et al., "Asuka-Bench: Benchmarking Code Agents on Underspecified User Intent and Multi-Round Refinement" | https://arxiv.org/abs/2606.05920 | v1 2026-06-04 | 2026-11-13 | abs | [t2e][cor] |
| cursor2026realtimerl | Jackson, Trapani, Wang, Zhu, "Improving Composer through real-time RL" (Cursor blog) | https://cursor.com/blog/real-time-rl-for-composer | 2026-03-26 | 2026-11-13 | WebFetch summary | [nc] |
| kang2026trace | Kang, Suresh, Saad-Falcon, Mirhoseini, "TRACE: Capability-Targeted Agentic Training"; code; HF LoRA card | https://arxiv.org/abs/2604.05336 ; https://github.com/ScalingIntelligence/TRACE ; https://huggingface.co/ScalingIntelligence/qwen3.6-trace-semantic-logic-precision-v1 | v1 2026-04-07; v2 2026-07-02; code @d2db230 (2026-07-12); card 2026-06-10 | 2026-11-13 | full; code; card [re-checked abs] | [td][env] |
| xiao2026socraticswe | Xiao et al., "Socratic-SWE: Self-Evolving Coding Agents via Trace-Derived Agent Skills" | https://arxiv.org/abs/2606.07412 | 2026-06-05 | 2026-11-13 | abs | [td] |
| wang2026sentinel | Wang et al., "SENTINEL: Failure-Driven Reinforcement Learning for Tool-Using LM Agents" | https://arxiv.org/abs/2606.12908 | 2026-06-11 | 2026-11-13 | abs | [td] |
| zala2024envgen | Zala, Cho, Lin, Yoon, Bansal, "EnvGen" | https://arxiv.org/abs/2403.12014 | v1 2024-03-18; v2 2024-07-12 | 2026-11-13 | abs | [td] |
| qi2024webrl | Qi et al., "WebRL" | https://arxiv.org/abs/2411.02337 | v1 2024-11-04; v3 2025-01-27 | 2026-11-13 | abs | [td] |
| zhou2025selfchallenging | Zhou, Levine, Weston, Li, Sukhbaatar, "Self-Challenging Language Model Agents" | https://arxiv.org/abs/2506.01716 | 2025-06-02 | 2026-11-13 | abs | [td] |
| barringer2011tracecontract | Barringer, Havelund, "TraceContract: A Scala DSL for Trace Analysis", FM 2011, LNCS pp. 57–72 | https://doi.org/10.1007/978-3-642-21437-0_7 | 2011 | 2026-11-13 | Crossref metadata [re-checked] | [td] |

### 9.2 Sources mentioned only in §2.6–§2.8 (abstract level unless noted; dates from the cluster notes)

| Source | arXiv / URL | Version / publication date | Accessed | Notes |
|---|---|---|---|---|
| LLMs-as-Instructors | 2407.00497 | 2024-06-29 | 2026-11-13 | [td] |
| DataEnvGym | 2410.06215 | v1 2024-10-08; v3 2025-03-13 | 2026-11-13 | [td] |
| Targeted Data Generation | 2305.17804 | 2023-05-28 | 2026-11-13 | [td] |
| AutoDetect | 2406.16714 | v1 2024-06-24; v2 2024-12-10 | 2026-11-13 | [td] |
| SwS | 2506.08989 | 2025-06-10 | 2026-11-13 | [td] |
| EEF (Exploring Expert Failures) | 2504.13145 | v1 2025-04-17 (withdrawn); v2 2025-04-18 | 2026-11-13 | [td] |
| Agent Learning via Early Experience | 2510.08558 | v1 2025-10-09; v3 2026-05-24 | 2026-11-13 | [td] |
| BugPilot | 2510.19898 | v1 2025-10-22; v2 2025-10-28 | 2026-11-13 | [td][env] |
| RLVE | 2511.07317 | v1 2025-11-10; v2 2026-06-06 | 2026-11-13 | [td] |
| Self-play SWE-RL | 2512.18552 | v1 2025-12-21; v3 2026-06-02 | 2026-11-13 | [td] |
| Agent World Model | 2602.10090 | v1 2026-02-10; v3 2026-05-22 | 2026-11-13 | [td] |
| Agent-World | 2604.18292 | 2026-04-20 | 2026-11-13 | [td] |
| Environment Evolution for Terminal Agents | 2609.04128 | 2026-09-03 | 2026-11-13 | [td] |
| TRACE (Guo et al.), "Towards Self-Evolving Benchmarks" | 2510.00415 | v1 2025-10-01; v3 2026-03-24 | 2026-11-13 | [td] |
| TRACE (Mittapalli et al.) | 2606.07054 | 2026-06-05 | 2026-11-13 | [td] |
| TRACE (Zabolotnii) | 2605.03838 | 2026-05-05 | 2026-11-13 | [td] |
| TRACE continual-learning benchmark | 2310.06762 | 2023-10-10 | 2026-11-13 | [td] |
| TRACE video temporal grounding | 2410.05643 | v1 2024-10-08; v3 2025-03-03 | 2026-11-13 | [td] |
| TRACE the Evidence | 2406.11460 | 2024-06-17 | 2026-11-13 | [td] |
| TRACE attribution | 2407.04981 | 2024-07-06 | 2026-11-13 | [td] |
| Trace (Microsoft) | 2406.16218 | v1 2024-06-23; v2 2024-11-01 | 2026-11-13 | [td] |
| TRACED | 2306.07487 | 2023-06-13 | 2026-11-13 | [td] |
| TraceRL | 2509.06949 | 2025-09-08 | 2026-11-13 | [td] |
| TraceCoder | 2602.06875 | 2026-02-06 | 2026-11-13 | [td] |
| CodeTracer | 2604.11641 | v1 2026-04-13; v3 2026-04-15 | 2026-11-13 | [td] |
| TRAIL | 2505.08638 | v1 2025-05-13; v3 2025-06-23 | 2026-11-13 | [td] |
| InterCode | 2306.14898 | v1 2023-06-26; v3 2023-10-30 | 2026-11-13 | [cor] |
| CodeFlowBench | 2504.21751 | v1 2025-04-30; v4 2026-04-15 | 2026-11-13 | [cor] |
| When Benchmarks Talk | 2502.18413 | v1 2025-02-25 | 2026-11-13 | [cor] |
| RECODE-H | 2510.06186 | v1 2025-10-07; v2 2025-10-24 | 2026-11-13 | [cor] |
| LLMs Get Lost In Multi-Turn Conversation | 2505.06120 | v1 2025-05-09 | 2026-11-13 | [cor] (§3–4 read) |
| ICAE-Bench | 2607.21217 | v1 2026-07-23 | 2026-11-13 | [cor] |
| SWE-Shift | 2610.32196 | v1 2026-10-23 | 2026-11-13 | [cor] |
| SLUMP | 2603.17104 | v1 2026-03-17 | 2026-11-13 | [cor] |
| SimulatorArena | 2510.05444 | v1 2025-10-06 (notes also list a v2 dated 2025-10-08) | 2026-11-13 | [cor] |
| Lost in Simulation | 2601.17087 | v1 2026-01-23; v2 2026-01-28 | 2026-11-13 | [cor] |
| Mind the Sim2Real Gap | 2603.11245 | v1 2026-03-11; v2 2026-07-31 | 2026-11-13 | [cor] |
| Suh et al., utility of user simulators | 2605.09808 | v1 2026-05-10 | 2026-11-13 | [cor] |
| HumanLM | 2603.03303 | v1 2026-02-07 | 2026-11-13 | [cor] |
| ZORO | 2604.15625 | v1 2026-04-17; v3 2026-10-19 | 2026-11-13 | [cor] |
| ContextCov | 2603.00822 | v1 2026-02-28; v2 2026-05-04 | 2026-11-13 | [cor] |
| ILF | 2303.16749 | v1 2023-03-28; v2 2024-02-22 | 2026-11-13 | [cor] |
| Coffee-Gym | 2409.19715 | v2 2024-10-04 | 2026-11-13 | [cor] |
| PRELUDE/CIPHER | 2404.15269 | v3 2024-11-23 | 2026-11-13 | [cor] |
| MultiSessionCollab | 2601.02702 | v3 2026-03-15 | 2026-11-13 | [cor] |
| SpecRover | 2408.02232 | v1 2024-08-05; v4 2024-12-11 | 2026-11-13 | [cor] |
| nl2postcond | 2310.01831 | v1 2023-10-03; v2 2024-04-15 | 2026-11-13 | [cor] |
| RECOVER | 2411.19552 | v1 2024-11-29; v2 2025-05-17 | 2026-11-13 | [cor] |
| Decoding Human-LLM Collaboration in Coding | 2512.10493 | v1 2025-12-11; v2 2025-12-12 | 2026-11-13 | [cor] |
| CodeChat (Developer-LLM Conversations) | 2509.10402 | v1 2025-09-12; v2 2026-08-28 | 2026-11-13 | [cor] |
| Hao et al., shared ChatGPT conversations | 2403.10468 | v1 2024-03-15 | 2026-11-13 | [cor] |
| Watanabe et al., agentic coding PRs | 2509.14745 | v3 2026-02-09 | 2026-11-13 | [cor] |
| Ehsani et al., failed agentic PRs | 2601.15195 | v1 2026-01-21 | 2026-11-13 | [cor] |
| Intent-Eval ("You Changed Your Mind, The Model Didn't") | 2610.06496 | v1 2026-10-05 | 2026-11-13 | [nc] |
| IntentDelta | 2610.33806 | v1 2026-10-24 | 2026-11-13 | [nc] |
| LiveAsset | 2611.11560 | v1 2026-11-08 | 2026-11-13 | [nc] |
| Specification-Oracle Gaps | 2610.30635 | v1 2026-10-22 | 2026-11-13 | [nc] |
| Veritas | 2611.13336 | v1 2026-11-09 | 2026-11-13 | [nc] |
| Groundability, Not Scale Alone | 2610.01023 | v1 2026-10-01 | 2026-11-13 | [nc] |
| Re-executing Coding-Agent Evaluations | 2610.14460 | v1 2026-10-10 | 2026-11-13 | [nc] |
| How Coding Agents Fail Their Users | 2605.29442 | v1 2026-05-28; v2 2026-08-31 | 2026-11-13 | [nc] |
| RealSWE | 2608.27831 | v1 2026-08-28; v3 2026-10-05 | 2026-11-13 | [nc] |
| SWE-TaskFlow | 2610.09633 | v1 2026-10-07; v2 2026-10-11 | 2026-11-13 | [nc] |
| FeatureArc | 2610.37434 | v1 2026-10-27 | 2026-11-13 | [nc] |
| K-Bench | 2608.21601 | v1 2026-08-21; v2 2026-09-02 | 2026-11-13 | [nc] |
| EvalPlus | 2305.01210 | v1 2023-05-02; v3 2023-10-30 | 2026-11-13 | [vf] |
| MacDiarmid et al., emergent misalignment from reward hacking | 2511.18397 | v1 2025-11-23 | 2026-11-13 | [vf] (partial) |
| Baker et al., monitoring reasoning models | 2503.11926 | v1 2025-03-14 | 2026-11-13 | [vf] |
| Meerkat | 2604.11806 | v1 2026-04-13 | 2026-11-13 | [vf] |
| METR, "Recent frontier models are reward hacking" | https://metr.org/blog/2025-06-05-recent-reward-hacking/ | 2025-06-05 | 2026-11-13 | [vf] (full) |
| Berkeley RDI, "How We Broke Top AI Agent Benchmarks" | https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/ | April 2026 | 2026-11-13 | [vf] (full) |
| Terminal-Bench leaderboard integrity update | https://www.tbench.ai/news/leaderboard-integrity-update | date not visible (secondary: April 2026) | 2026-11-13 | [vf] (full) |
| OpenAI, "Why we no longer evaluate SWE-bench Verified" | https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/ | Feb 2026 (secondary) | 2026-11-13 | [vf]; **not retrieved (HTTP 403)** |

### 9.3 Project records and local reference clones used

| Source | Location | Version / date | Accessed |
|---|---|---|---|
| Decision log (D1–D25) | `docs/decision_log.md` | entries dated 2026-11-13 | 2026-11-13 |
| Experimental protocol v0.2 | `experiments/protocol.md` | v0.2, 2026-11-13T02:29:52Z, sha256 `b507dc23…` (per [DL D22]) | 2026-11-13 |
| Data card; annotation guide v0.1; STATUS; README | `docs/data_card.md`; `docs/annotation_guide.md`; `STATUS.md`; `README.md` | 2026-11-13 | 2026-11-13 |
| Harbor (read-only clone) | `/home/user/harbor-framework/harbor` | main@3bf4cb3 (2026-11-12), Apache-2.0 | 2026-11-13 [re-checked commit] |
| Terminal-Bench (read-only clone) | `/home/user/harbor-framework/terminal-bench` | main@01c0d6d (2026-11-12), Apache-2.0 | 2026-11-13 [re-checked commit] |
| SWE-smith (read-only clone) | `/home/user/SWE-bench/SWE-smith` | @9b74ac0 (author 2026-03-21 / committer 2026-03-22), MIT | 2026-11-13 [re-checked commit] |
| R2E-Gym (read-only clone) | `/home/user/R2E-Gym/R2E-Gym` | @0d94c4e (2025-07-13), Apache-2.0 | 2026-11-13 [re-checked commit] |
| TRACE (Kang et al.) (read-only clone) | `/home/user/ScalingIntelligence/TRACE` | @d2db230 (2026-07-12), MIT | 2026-11-13 [re-checked commit] |

### 9.4 UNRESOLVED items carried forward

1. SWE-Together's arXiv v1 date (2026-06-29) vs the "date: September 30, 2026" line in its HTML.
2. RealClawBench code link: github.com/openclaw/clawbench vs an anonymous.4open.science link.
3. Terminal Wrench's 331 environments vs the hacker-fixer paper's 323 hackable tasks.
4. TRACE (Kang et al.): paper vs released code on the mining split, the evaluation settings and the baselines.
5. Whether SessionFarmer's reference requirement ledger was built by humans or by an LLM.
6. The content of VibeSWEBench.
7. The text of the SWE-chat gate conditions.
8. The SF Data essay's revision history.
9. The primary text of OpenAI's 2026 SWE-bench Verified audit.
10. Whether SWE-chat raw transcripts keep `toolUseResult.originalFile`.
11. What CooperBench/swechat-coop contains.
