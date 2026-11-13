# Cluster notes: adversarial novelty search for the newest and closest work (TraceContract)

Cluster: newest/closest work, 2025-2026 (focus Aug-Nov 2026), for the TraceContract (working name) related-work review.
Access date for every source below: **2026-11-13 (UTC)**. Publication and version dates are recorded separately from the access date.
No commits were made in this research step, and no git commands were run inside `/home/user/trace-contract`. The only file written in the repository is this notes file.

Conventions:
- "States:" or a quotation means the source says it. "Inference:" or "My check:" marks my own reasoning or arithmetic.
- Quotations are verbatim (at most 2 sentences) and give the section they come from. Section numbers are those of the arXiv version I read (v1 unless noted).
- "Verified" means I opened the primary page myself in this session (arXiv abstract page, arXiv HTML full text, or the vendor's own page).
- Sibling notes in this folder (`swechat.md`, `trace2eval.md`, `corrections.md`, `verifier_fidelity.md`, `env_synthesis.md`, `training_and_datasets.md`, `sfdata.md`) already cover SWE-chat, SWE-Together, SecureForge, SWE-INTERACT, RealClawBench, Trace2Eval, TellOnce, PersonaCodeBench, FeatureLoop, EvoCode-Bench, SWE-Shift, AfterVibe, the Verification Horizon, traj2envs, Trace Commons, SF Data, and the SWE-bench-audit literature. I re-verified only what I needed for comparisons. **Everything in sections 3-6 is new relative to those notes** (I grepped the sibling notes for every arXiv ID and title I report as new; none appeared).

---

## 0. Bottom line (short)

1. **There is a new, very close paper: SessionFarmer / CropChat (arXiv 2611.02440 v1, 2 Nov 2026; ShanghaiTech, ByteDance, Shanghai AI Lab).** It turns real SWE-chat sessions (and proprietary ByteDance enterprise logs) into executable SWE tasks. It writes a full-episode, correction-aware statement: requirements "that remain in effect at the end of the episode", including withdrawals, with each clause citing its supporting conversation event IDs. It compares *first message vs first session vs full episode* statements against a requirement ledger (full coverage 26% vs 54% vs 75% on multi-session tasks). It refines LLM-written tests against requirement-breaking mutants and a blind solver, explicitly to reduce false rejection of valid alternatives and false acceptance of incomplete solutions. It reports FP/FN/FPR/FNR/balanced accuracy against **LLM (gpt-6-astra) patch-correctness labels**: BAcc +8.9 pp and +7.2 pp, with FNR down 34.0 and 32.0 pp but FPR **up** 16.2 and 17.5 pp. This single paper covers, in some form, three of our four components. It is the strongest novelty threat found so far.
2. **What SessionFarmer does not do (verified in full text):**
   - (a) No human patch-correctness labels. Humans (the original developers) audited only episode boundaries, statements and rubrics on CropEnterprise.
   - (b) It never builds a verifier from the initial request only, so it cannot attribute false acceptance to omitted corrections. Its first-message condition is measured only as statement *coverage*.
   - (c) Its negatives are constructed mutants that are used *inside* the refinement loop. They are not held out, and they are not the agent's naturally observed pre-correction state.
   - (d) It constructs no valid-alternative candidates; FN is measured on solver rollouts.
   - (e) The code and data links were not publicly reachable on 2026-11-13.
   - Its own Appendix D lists "requirements ... disclosed after the opening message" and "turns where developers pushed back" as *future* uses.
3. **The verifier-audit half of our design now has very close prior art, independent of trace reconstruction.**
   - **VerifierBench** (2610.28679; UPenn/UIUC/Berkeley/NYU) scores generated verifiers on 4,993 held-out cases. The cases are gold, cosmetic and alternative-implementation (valid) variants, plus "base" (initial/unfinished), partial, near-miss, regression and hack negatives. It reports normalized balanced accuracy and finds that generated verifiers over-reject valid solutions.
   - **TestJack** (2610.10619) finds that 34.4% of trials judged correct violate prompt requirements.
   - **UserSWE** (Tencent Hunyuan) has an execution-based "equivalent pass" route for valid alternatives.
   - None of these uses human labels for the final FA/FR, and none builds tasks from real sessions.
4. **Context-omission effects are now measured in several places, but never as verifier false acceptance against human labels on a fixed candidate pool.**
   - **ARE-bench** (2611.14364) holds deliveries and judge verdicts fixed. Checking only the current request's contracts and norms gives ~69% strict success. Adding historical and workspace requirements gives 28.4-40.0%, so roughly half of failed runs would pass the narrower checks. Its judge is an LLM, and the authors say human annotation is "the next step".
   - **TiGanEval** (2610.17757) human-annotated 100 SWE-chat trajectories: 56% have incomplete initial instructions.
   - **Requirements After the First Edit** (2609.03028, KIT/Waseda/Adelaide) mines late requirement emergence in SWE-chat, with replayed code-invalidation proxies.
5. **More trace-to-environment pipelines from industry:**
   - Meta: **REAP/Harvest** (production sessions → F2P-tested tasks, single-turn only) and, in sibling notes, AfterVibe.
   - Qwen/Alibaba: **Terminal-Universe** (public agent trajectories → 37.3k environments; "Intent Recovery" folds in later clarifying requests).
   - ByteDance: SessionFarmer, plus **TraceDance**, built on 252,557 deployed Claude Code/OpenClaw sessions.
   - Tencent: UserSWE persona model from 20,859 internal sessions, and **FeatureArc** used internally for Hunyuan.
   - Baidu: **DuMateBench**, from production agent-platform sessions.
   - JetBrains: 4,782 "Production Sessions" → **SWE-TaskFlow**.
   - Cursor: **real-time RL**, where production user reactions become rewards, with no reconstructed tasks.
   - Also the ICML-2026-workshop **VibeSWEBench**, whose "Trajectory Unrolling" converts human-agent failure sessions into single-turn tasks "while preserving human-authored corrective signals" (abstract only).
6. **Strongest novelty objection (section 8):** "SessionFarmer already reconstructs correction-aware executable tasks from SWE-chat and audits test FP/FN, and VerifierBench already scores verifiers on held-out valid-alternative/near-miss/base/attack pools. TraceContract's 2x2 is a recombination."
   - **Surviving, narrower contribution (INFERENCE):** a pre-registered, verifier-level counterfactual measurement of *correction-attributable* false acceptance. Its parts:
     - Verifiers are generated by the same frozen procedure from initial-only vs full-session contracts, with and without a predefined audit.
     - All verifiers are scored on one frozen, held-out candidate pool, never used during construction or refinement. The pool's anchor negatives are the agent's actual pre-correction code states, which the user explicitly rejected in the session. It also contains independently written valid alternatives and near-misses.
     - Labels come from independent human adjudication, with the LLM-label vs human-label discrepancy itself reported.
     - Results are FA and FR per cell.
   - This is an evaluation-methodology and measurement contribution with a small, high-quality labeled dataset, not a new pipeline.

---

## 1. Search method and coverage

- **Citation graph (most productive).** Semantic Scholar Graph API (`api.semanticscholar.org/graph/v1/paper/arXiv:<id>/citations`), snapshot on 2026-11-13.
  - Seeds and citing-record counts:
    - SWE-chat 2604.20779: **68 citing records**. Trace2Eval 2611.06506: **0**. SWE-Together 2606.29957, the Verification Horizon 2606.26300, PersonaCodeBench, AfterVibe, RealClawBench, SecureForge, FeatureLoop, TellOnce 2606.13174 and SWE-INTERACT 2606.30573: non-zero lists.
    - Second round: SessionFarmer 2611.02440 (0), Terminal-Universe 2609.04148, TraceDance, Requirements-After-First-Edit, TiGanEval, CodeAssistBench 2507.10646, PatchDiff 2503.15223, hacker-fixer 2606.08960, Benchmarks-as-Software 2611.08417, SpecPath, Reward-Suite-Leaky, UserSWE, ARE-bench, TRACE 2604.05336.
    - Third round: REAP 2604.01527 (5), VerifierBench (0), DeepSWE 2607.07946 (98), Veritas (0).
  - S2 rate-limited (HTTP 429) its keyword *search* endpoint after a few calls, so keyword search on S2 returned nothing usable.
- **arXiv listings.**
  - `arxiv.org/list/{cs.SE,cs.AI,cs.CL}/pastweek?show=2000` covers announcements of 5-11 Nov 2026 (220, 1,363 and 581 entries). I keyword-filtered titles.
  - arXiv abstract search (`arxiv.org/search/?searchtype=abstract`), newest first, with ~40 distinct phrasings. Examples: "user corrections" verifier; sessions "executable tasks"; "false acceptance" verifier; "reward fidelity"; "requirement drift"; "trace-derived"; "correction-aware"; "pre-correction"; "verifier audit"; "valid alternatives" verifier; "developer-agent sessions"; "agent sessions" benchmark; "work episodes"; "blind solver"; "requirement-breaking"; "intent recovery"; "human-adjudicated" verifier; "production traces" agents; "session logs" coding agent; "change of mind".
- **WebSearch (standard).** About 12 queries, including industry phrasings (trace-to-environment startups, Cursor online RL, traj2envs, vibe-coding session benchmarks, DuMateBench, late requirement arrival).
- **Not searched / limits:**
  - Google Scholar (not used).
  - OpenReview: `openreview.net` and `api2.openreview.net` returned a browser challenge (HTTP 403 "ChallengeRequiredError"), so OpenReview-only papers are abstract-level at best.
  - Hugging Face papers pages were not crawled systematically.
  - The S2 snapshot misses papers that S2 had not yet linked; the most recent days (Nov 12-13) are likely under-covered.

---

## 2. Source index

All accessed 2026-11-13. "Full" = arXiv HTML full text converted to text and read in the stated sections. "Abs" = abstract page only. "Grep" = full-text keyword search of specific sections.

| # | Title (short) | URL | Kind | Version / publication date | Depth |
|---|---|---|---|---|---|
| N1 | Harvesting SWE Benchmarks from Wild Vibe Coding Sessions (SessionFarmer, CropChat, CropEnterprise) | https://arxiv.org/abs/2611.02440 ; https://arxiv.org/html/2611.02440 | paper | v1 Mon 2 Nov 2026 (only version) | Full: §1-§5, App. A.2, A.4 (prompts), B.3, D, E (grep) |
| N1a | SessionFarmer code / CropChat data links | https://github.com/bytedance/SessionFarmer ; https://huggingface.co/datasets/ByteDance/SessionFarmer-CropChat | code/data | n/a | **Not accessible**: raw README/LICENSE 404 at main and master; `git ls-remote` asked for credentials; HF API and raw README returned 401 |
| N2 | REAP: Automatic Curation of Coding Agent Benchmarks from Interactive Production Usage (Harvest) | https://arxiv.org/abs/2604.01527 | paper (Meta) | v1 2 Apr 2026; v2 3 Apr; v3 10 May; v4 28 Jul 2026; "Accepted at ASE 2026 Industry Showcase" | Full (v4 HTML): §3, §4.2-4.3, §5, §6 |
| N3 | Terminal-Universe: Turning Agent Trajectories into Scalable Terminal Environments | https://arxiv.org/abs/2609.04148 | paper (Qwen Team, Alibaba; Tsinghua) | v1 3 Sep 2026 | Grep: §1-§3, §6, §7, App. A (Table 12), C.1 |
| N4 | ARE-bench: Benchmarking Agents' Research Ability in Real-World Researcher Sessions and Workspaces | https://arxiv.org/abs/2611.14364 | paper | v1 10 Nov 2026 | Full: §2, §3.1-3.2, §4.2.2 (Table 8), §4.6 |
| N5 | VerifierBench: Benchmarking the Generation of Executable Verifiers for LLM Agents | https://arxiv.org/abs/2610.28679 | paper (UPenn, UIUC, UC Berkeley, NYU) | v1 19 Oct 2026; v2 30 Oct 2026 | Full: §2.2-2.4, §3.4, Limitations, App. C (Table 10) |
| N6 | Instructions Are Evidence, Not Objectives: Measuring Outcome Alignment of Agents (TiGanEval) | https://arxiv.org/abs/2610.17757 | paper | v1 13 Oct 2026 | Grep: §1, §4.2, §5.6, App. B |
| N7 | Requirements After the First Edit: Mining Late Requirement Emergence and Rework in Real-World Coding-Agent Sessions | https://arxiv.org/abs/2609.03028 | paper (KIT, Waseda, Adelaide) | v1 2 Sep 2026 | Grep: abstract, §5.1, §6.5 |
| N8 | TestJack: Agentic Coding Benchmarks Auditing via Evaluator Evolution | https://arxiv.org/abs/2610.10619 | paper | v1 7 Oct 2026 | Grep: §1-§2, §4.3-4.4, App. E |
| N9 | UserSWE: Evaluating Coding Agents in Multi-Turn Conversations with Dynamic Users | https://arxiv.org/abs/2610.29822 | paper (Tencent Hunyuan) | v1 21 Oct 2026 | Grep: §4.3, §5.3, App. B.4 |
| N10 | TraceDance: Building Agent Behavior Benchmarks from Real-World Agent Deployment Traces | https://arxiv.org/abs/2609.33295 | paper (ByteDance Inc., USA; UIC) | v1 27 Sep 2026 | Grep: §1, §4 (data), appendix agreement table |
| N11 | SpecPath: Testing Coding Agents Across Contract-Equivalent Specification Histories | https://arxiv.org/abs/2608.09799 | paper | v1 10 Aug 2026 | Abs + grep of §3 definitions |
| N12 | Pinning Decisions Before Failure: Executable Records of Underspecified Choices | https://arxiv.org/abs/2610.03237 | paper | v1 2 Oct 2026 | Abs |
| N13 | When the Reward Suite Is Leaky: A Preregistered Causal Contrast of Natural Verifier False Positives in RLVR | https://arxiv.org/abs/2607.11022 | paper | v1 13 Jul 2026 | Abs |
| N14 | Veritas: A Verifier Generation Harness for Agent Tasks | https://arxiv.org/abs/2611.13336 | paper | v1 9 Nov 2026 | Abs |
| N15 | Validation Evidence in LLM Repair Agents (BSG-VA) | https://arxiv.org/abs/2607.28871 | paper | v1 30 Jul 2026 | Abs |
| N16 | SWE-Touch: Benchmarking Coding Agents When Users Touch the Code | https://arxiv.org/abs/2608.02499 | paper | v1 3 Aug 2026 | Abs |
| N17 | Coding-Agent Benchmarks Should Match Their Users' Task Flows (SWE-TaskFlow) | https://arxiv.org/abs/2610.09633 | paper (JetBrains Research) | v1 7 Oct 2026; v2 11 Oct 2026 | Abs + HTML front matter |
| N18 | Interaction-as-a-Judge | https://arxiv.org/abs/2610.17895 | paper | v1 13 Oct; v2 14 Oct; v3 23 Oct 2026 | Abs |
| N19 | K-Bench: measuring model performance on real scientific agent requests | https://arxiv.org/abs/2608.21601 | paper (K-Dense) | v1 21 Aug 2026; v2 2 Sep 2026 | Abs |
| N20 | LiveAsset: Learning Intent Assets from Corrective Interactions for Agent Runtime Control | https://arxiv.org/abs/2611.11560 | paper | v1 8 Nov 2026 | Abs |
| N21 | SWE-DIVE: Multi-Turn Coding Agent Evaluation with Dynamic User Simulation | https://arxiv.org/abs/2610.30047 | paper; NeurIPS 2026 workshop (non-archival), per arXiv comment | v1 21 Oct 2026 | Abs |
| N22 | SWE-Journey | https://arxiv.org/abs/2610.11559 | paper | v1 8 Oct 2026 | Abs |
| N23 | FeatureArc: Benchmarking Coding Agents on Evolving Features | https://arxiv.org/abs/2610.37434 | paper (Tencent, per abstract) | v1 27 Oct 2026 | Abs |
| N24 | RealSWE: Compositional Evaluation under Realistic User Requests | https://arxiv.org/abs/2608.27831 | paper | v1 28 Aug; v2 31 Aug; v3 5 Oct 2026 | Abs |
| N25 | ProgramDistill | https://arxiv.org/abs/2609.18805 | paper | v1 16 Sep 2026 | Abs |
| N26 | RealCLI | https://arxiv.org/abs/2610.22507 | paper | v1 15 Oct 2026 | Abs |
| N27 | MTAC-IFBench | https://arxiv.org/abs/2609.14992 | paper | v1 14 Sep 2026 | Abs |
| N28 | LLMs Get Lost in Evolving User Intent | https://arxiv.org/abs/2607.20734 | paper | v1 22 Jul 2026 | Abs |
| N29 | How Coding Agents Fail Their Users (20,574 sessions) | https://arxiv.org/abs/2605.29442 | paper | v1 28 May 2026; v2 31 Aug 2026 | Abs |
| N30 | DECODE (53.6K developer edits of AI-generated code) | https://arxiv.org/abs/2607.25130 | paper | v1 27 Jul; v2 14 Sep; v3 27 Oct 2026 | Abs |
| N31 | Building to the Test | https://arxiv.org/abs/2606.28430 | paper | v1 26 Jun 2026 | Abs |
| N32 | What the Specification Did Not Say: Specification-Oracle Gaps | https://arxiv.org/abs/2610.30635 | paper | v1 22 Oct 2026 | Abs |
| N33 | Between Spoilers and Guesswork | https://arxiv.org/abs/2610.22760 | paper | v1 16 Oct 2026 | Abs |
| N34 | Well-Specified and Well-Tested? (ExLabel, SWE-TQ) | https://arxiv.org/abs/2610.39417 | paper | v1 29 Oct 2026 | Abs |
| N35 | Maintaining Benchmarks ... Unearned Passes | https://arxiv.org/abs/2609.34262 | paper | v1 28 Sep 2026 | Abs |
| N36 | SpecGuard | https://arxiv.org/abs/2610.09159 | paper | v1 6 Oct 2026 | Abs |
| N37 | Who Guards the Benchmarks? (BenchGuard) | https://arxiv.org/abs/2604.24955 | paper; "Camera-ready version for COLM 2026" | v1 27 Apr 2026; v2 2 Oct 2026 | Abs |
| N38 | Can Agent Benchmarks Support Their Scores? | https://arxiv.org/abs/2605.10448 | paper | v1 11 May 2026 | Abs |
| N39 | Reality Is the Final Verifier | https://arxiv.org/abs/2609.12039 | position paper | v1 10 Sep 2026 | Abs |
| N40 | Groundability, Not Scale Alone | https://arxiv.org/abs/2610.01023 | paper | v1 1 Oct 2026 | Abs |
| N41 | When Requirements Interact (CodeSpecWeave) | https://arxiv.org/abs/2610.40256 | paper | v1 29 Oct 2026 | Abs |
| N42 | DeepSWE | https://arxiv.org/abs/2607.07946 | paper | v1 8 Jul 2026 | Abs |
| N43 | DuMateBench | https://arxiv.org/abs/2608.26546 | paper (Baidu per secondary press; abstract says "a large-scale production agent platform") | v1 27 Aug 2026 | Abs |
| N44 | EnterpriseClawBench | https://arxiv.org/abs/2606.23654 | paper | v1 22 Jun 2026 | Abs |
| N45 | SWE-RPG (A Unified Issue Resolution Benchmark for Requirement Clarification, Planning, and Code Generation) | https://arxiv.org/abs/2608.09072 | paper | v1 10 Aug 2026 | Abs |
| N46 | You Changed Your Mind, The Model Didn't (Intent-Eval) | https://arxiv.org/abs/2610.06496 | paper | v1 5 Oct 2026 | Abs |
| N47 | IntentDelta | https://arxiv.org/abs/2610.33806 | paper | v1 24 Oct 2026 | Abs |
| N48 | Beyond Oracle Communication (Drift-Bench++) | https://arxiv.org/abs/2609.38604 | paper | v1 29 Sep 2026 | Abs |
| N49 | Fewer Clarifications, Better Code (CAPA) | https://arxiv.org/abs/2607.26611 | paper | v1 29 Jul 2026 | Abs |
| N50 | Re-executing Coding-Agent Evaluations | https://arxiv.org/abs/2610.14460 | paper | v1 10 Oct 2026 | Abs |
| N51 | When Terminal-Agent Training Stalls | https://arxiv.org/abs/2610.02405 | paper | v1 1 Oct 2026 | Abs |
| N52 | AutoRefine: Auto-Calibrating Code Judges from Workflow Outcomes | https://arxiv.org/abs/2611.09291 | paper ("prepared for submission to CAIN 2027 industrial track") | v1 6 Nov 2026 | Abs |
| N53 | Tracybot | https://arxiv.org/abs/2611.09395 | tool paper | v1 6 Nov 2026 | Abs |
| N54 | JoyFrontBench | https://arxiv.org/abs/2611.14952 | paper | v1 11 Nov 2026 | Abs |
| N55 | WorkBorne | https://arxiv.org/abs/2610.14915 | paper | v1 10 Oct 2026 | Abs |
| N56 | Trajectory2Gym | https://arxiv.org/abs/2610.33568 | paper | v1 24 Oct 2026 | Abs |
| N57 | From Traces to Agentic Worlds (Trace2Env) | https://arxiv.org/abs/2610.06100 | paper | v1 5 Oct 2026 | Abs |
| N58 | BenchMeUp | https://arxiv.org/abs/2610.37283 | paper | v1 27 Oct 2026 | Abs |
| N59 | Replay Fidelity in LLM Agent Evaluation (AppWorld) | https://arxiv.org/abs/2611.11216 | paper | v1 8 Nov 2026 | Abs |
| N60 | VibeSWEBench | https://icml.cc/virtual/2026/82740 (OpenReview forum id kWrudm978A) | ICML 2026 workshop poster ("Deep Learning for Code: Towards Human-Centered Coding Agents") | 2026 (exact date not stated on the page) | **Abstract only, via the ICML virtual page.** OpenReview blocked (browser challenge); no arXiv version found by arXiv search |
| N61 | Cursor, "Improving Composer through real-time RL" | https://cursor.com/blog/real-time-rl-for-composer | company blog | Mar 26, 2026 | Read via WebFetch (summarized quotes) |
| N62 | SWE-chat (re-verification only) | https://arxiv.org/abs/2604.20779 | paper | v1 22 Apr 2026; v2 1 Oct 2026; "Accepted at COLM 2026" | Abs |
| N63 | Trace2Eval (re-verification only) | https://arxiv.org/abs/2611.06506 | paper | v1 4 Nov 2026 | Abs (deep read in `trace2eval.md`) |
| N64 | AfterVibe (re-verification of Table 4) | https://arxiv.org/abs/2607.09900 ; html | paper (Meta authors Paltenghi & Chandra) | v1 10 Jul 2026 | Grep: §4.1.1, §4.7 Table 4 |
| N65 | Abs re-checks for version history: SWE-Together 2606.29957 (v1 only), RealClawBench 2606.03889 (v3 28 Aug 2026), PersonaCodeBench 2611.05739 (v1 3 Nov 2026), FeatureLoop 2610.35488 (v2 29 Oct 2026), Verification Horizon 2606.26300 (v2 29 Jun 2026) | arxiv.org/abs/<id> | papers | as listed | Abs (history only) |
| N66 | Semantic Scholar citation snapshots | https://api.semanticscholar.org/graph/v1/paper/arXiv:2604.20779/citations (and others listed in §1) | citation index | snapshot 2026-11-13 | JSON saved in scratch |
| N67 | Other abstract-only items: WatchPoint and similar are not repeated here. Also seen: 2609.01354 "Where the Verifier Fails", 2610.17824 "Checking the Checkers", 2610.35716 "Audit Where Hacks Pay", 2610.09142 "Finding Side-Effect Loopholes", 2611.10837 patch-correctness evidence framework, 2610.24206 SWE-Bench Pro V2, 2609.08149 SWE-Bench Pro Verified, 2609.06780 "Shortcutting the Fix", 2610.13022 "Don't Guess, Just Ask", 2610.31854 SWE-Clar, 2610.22382 "Eliciting Specifications", 2610.32313 Copilot trajectories, 2608.29204 AgentLogs, 2611.06866 GH-AWTrace | arxiv.org/abs/<id> | papers | titles and dates from S2 / arXiv listings only | **Titles only** (not opened unless listed above) |

---

## 3. Tier 1: closest new works (read in full or by targeted grep)

### 3.1 SessionFarmer / CropChat / CropEnterprise (arXiv 2611.02440): HIGH overlap

**Bibliographic record (verified).**
- Title: "Harvesting SWE Benchmarks from Wild Vibe Coding Sessions".
- Authors: Ao Lu, Yuanhao Zeng, Shaocheng Lan, Sijie Xu, Jiacheng Bao, Kuang Yan, Heng Lin, Kan Ren.
- Affiliations listed in the HTML: ShanghaiTech University; ByteDance, China; Shanghai AI Laboratory. The author-to-affiliation mapping was not extracted. Contact: Ao Lu and Kan Ren (ShanghaiTech).
- v1 submitted Mon 2 Nov 2026 03:02:59 UTC. cs.SE; cs.AI. No venue stated.
- Code link: github.com/bytedance/SessionFarmer. Benchmark link: huggingface.co/datasets/ByteDance/SessionFarmer-CropChat. **Neither was publicly accessible on 2026-11-13** (N1a).

**Task source.**
- Public: SWE-chat, using the Entire recording schema (sessions and commit checkpoints).
- Private: "an internal enterprise development-platform repository over a 2-month record of sessions" (§3.5). The data owners authorized this use (Ethics).
- CropChat funnel (§3.5): "Starting from an initial pool of 5,851 sessions and 13,406 checkpoints in SWE-Chat, mechanical filtering and cluster formation yield 2,708 work clusters, which are filtered and partitioned into 338 qualified episodes and ultimately 242 verified tasks". That covers 61 repositories and 14 languages.
- CropEnterprise: 375 sessions → 56 tasks (32 bug fixes, 22 features, 2 refactors), in a TypeScript repo of 1,592 source files and 473.3k LOC.

**Reconstruction.**
- *Work episodes.* Checkpoints within 24 h sharing a session form clusters. An LLM confirms session relevance against commit diffs, and an LLM partitions clusters into goal-centered episodes, with agreement required across repeated calls.
  - The base checkpoint is the start state, and the diff to the final checkpoint is the gold patch.
  - Quote (§3.1): "Crucially, we retain the complete transcript of each confirmed session instead of clipping dialogue turns to the timestamps between the base and final checkpoints".
- *Environment.* Session-mined tool requirements are verified verbatim against the transcript. An Environment Builder agent produces a Dockerfile, which must pass offline validation on both the base and final trees (§3.2).
- *Statement* (§3.3, correction-aware). Quote: "Because the evaluated benchmark agent runs autonomously without a human in the loop, SessionFarmer synthesizes a self-contained task statement that consolidates all requirements that remain in effect at the end of the episode."
  - Grounding rule, quote (§3.3): "requirements must be derived from the developer's instructions and explicitly approved agent proposals; the gold patch is used only to verify which discussed behaviors were actually completed at the final checkpoint."
  - Clauses ("obligations") cite exact conversation event IDs.
  - An independent LLM validator checks "source fidelity, requirement completeness, and implementation openness". A task gets at most 2 revisions before it is discarded.
  - The prompt schema (App. E) includes a `"superseded_requirements"` field "describing requirements revised or withdrawn". The authoring prompt says: "include still-effective clarifications, necessary conditions and withdrawals".
- *Rubrics.* Three dimensions (Clarity, Design, Repository fit), scored 0/1/2 by an LLM judge over 3 trials, with the QualityResolved rule Eq. (1). The gold patch must pass this quality gate.
- *Models* (§3.5): agent roles are gpt-5.6-sol in the Pi harness; single-call judgments use deepseek-v4-flash.

**Verifier and verifier audit (§3.4, §4.4).** The test suites are LLM-written.
- *Criteria-based refinement.* Quote (§3.4): requirement-breaking mutants are "variants of the gold patch where each mutant deliberately breaks exactly 1 requirement clause from the statement, serving as negative controls that mimic incomplete or shortcut solutions".
  - The suite must pass gold in 3 fresh runs, fail on base in at least 1 scenario, and reject every mutant "in a test scenario bound to the specific requirement that mutant violates". It gets up to 3 versions.
  - The Test Author is "completely blind to the mutant patches". It is shown only the violated clause and a trigger description when a mutant escapes.
- *Solver-based refinement.* A blind solver attempts the task. The Test Author compares its own "independent semantic judgment" of the patch with the mechanical verdict and revises tests on disagreement, for up to 2 rounds of 3 versions.
- *Audit result* (Table 3; 30 CropChat tasks where refinement modified the suite; 87 labeled rollouts per solver; labels from "independent gpt-6-astra patch correctness labels" following the DeepSWE protocol):

| Solver | Suite | Pass | FP | FN | FPR | FNR | BAcc |
|---|---|---|---|---|---|---|---|
| terra | w/o refinement | 21.8 | 3.4 | 39.1 | 8.1 | 68.0 | 61.9 |
| terra | SessionFarmer | 48.3 | 10.3 | 19.5 | 24.3 | 34.0 | 70.8 |
| gpt-5.5 | w/o refinement | 16.1 | 5.7 | 43.7 | 12.5 | 80.9 | 53.3 |
| gpt-5.5 | SessionFarmer | 41.4 | 13.8 | 26.4 | 30.0 | 48.9 | 60.5 |
| terra | SWE-Bench-Pro official (150 rollouts) | 54.7 | 18.7 | 17.3 | 40.0 | 32.5 | 63.8 |
| terra | DeepSWE official (150 rollouts) | 26.0 | 17.3 | 3.3 | 19.7 | 27.8 | 76.3 |

- Quote (§4.4 heading sentence): "Test refinement substantially reduces false rejections at the cost of higher false acceptances."
- *My check:* FPR rises by +16.2 pp (terra) and +17.5 pp (gpt-5.5). FNR falls by 34.0 pp and 32.0 pp. These match the text.
- *Human validation* (§4.4, Fig. 7). "4 full-time software engineers who authored the original commits" audited 28 CropEnterprise tasks (56 reviews):
  - episode boundaries accepted in 94.6% of reviews and sessions in 96.4%; both reviewers endorsed 89.3% of tasks;
  - of the 52 downstream reviews, 100.0% accepted the statement (84.6% "exact match");
  - rubric criteria endorsed at 97.0%, 99.1% and 99.6%.
  - **There are no human patch-correctness labels**, and the developers did not label FA/FR.

**Correction / requirement evolution (§1, §4.3).**
- "87.6% of tasks rely on requirements added, clarified, or revised in later user turns" (§1). 14.0% of CropChat tasks and 14.3% of CropEnterprise tasks span multiple sessions.
- Later-session roles (40 later sessions, 76 role assignments): 36.8% add new behaviors, 27.6% "modify or replace an earlier requirement", 18.4% clarify, 11.9% pure implementation, confirmation or plan carryover.
- *Evidence ablation* (Fig. 5a). The statement is rerun under First message / First session / Full episode and audited against "an independent reference requirement ledger constructed from the full episode and gold patch". The ledger has 516 requirements over the 34 multi-session tasks and 205 over the 20 single-session tasks.
  - Full coverage: 26% → 54% → 75% on multi-session tasks; 49% → 78% on single-session tasks.
  - Released statements reach 75.3% and 79.7%. 89.3% (183/205) of the not-fully-covered items are shared.
  - **The paper does not state whether the ledger is built by humans or an LLM.** The surrounding text mentions an "independent audit model" for the later-session role audit. Inference: the ledger is probably LLM-built. Not confirmed.
- App. D (future uses), quote: "Because the Task Author cites the user turns that support each requirement clause, one can test whether the requirements missed by evaluated agents concentrate on those disclosed after the opening message." Second quote: "The turns where developers pushed back on the original agent (Appendix C.4) further mark decisions that went wrong during development; comparing these decisions against autonomous trajectories can reveal recurring errors and help investigate why autonomous agents fail."

**Experiments.**
- 12 model-harness configurations on CropChat and 3 on CropEnterprise. Best Pass@1 is 39.3%. Harness choice shifts Pass@1 by up to 8.4 pp for the same model. 22.8% of task-configuration pairs are inconsistent across 3 runs.
- 57.9% of CropChat gold patches modify no test files (§3.4).
- No training (RL/SFT) experiments.

**Component overlap with TraceContract (my assessment).**
- Trace-derived task construction: **high**. Same data source (SWE-chat), executable Docker tasks.
- Correction preservation: **high** at the statement level, including withdrawals and per-clause provenance.
- Executable verifier: **high**. LLM-written tests are calibrated against mutants and a blind solver.
- Verifier audit: **medium**. FP/FN and BAcc are measured, but:
  - against LLM labels;
  - mutants are construction-time, not held out;
  - there are no constructed valid alternatives;
  - there is no initial-only verifier arm;
  - no session-native negative (the agent's pre-correction state) is used.

### 3.2 REAP / Harvest (arXiv 2604.01527, Meta): MEDIUM overlap

- Authors: Smriti Jha, Matteo Paltenghi, Chandra Maddila, Vijayaraghavan Murali, Shubham Ugare, Satish Chandra (Meta, USA). v4 28 Jul 2026, "Accepted at ASE 2026 Industry Showcase".
- Source: "authentic conversations between developers and a production AI coding assistant", each mapped to an approved, landed diff via an AI-provenance log (§3.2).
- Single-turn only, quote (§3.2): "To maintain a strict one-to-one mapping between developer intent and code modifications, we exclude diffs that resulted from more than one developer-agent conversation." Scope, quote (§4): "we restrict to single-turn conversations in which a developer provides one prompt and the agent produces code changes without intermediate human feedback."
- Environment: the solution diff is "backed out" from the current monorepo, and the benchmark is rolling and re-curated.
- Verifier: F2P tests retrieved from production ("probabilistic test retrieval"). An agentic test-relevance filter (Claude Sonnet 4.5) and multi-run F2P validation with warmups follow. No LLM judges.
- Human validation (§4.2): two annotators (the first two authors).
  - Task-type classifier: 87.00% agreement with consensus, κ=0.74 (100 tasks; 3 FP, 10 FN). Inter-annotator agreement was 85% (κ=0.70).
  - Test relevance: 86.00%, κ=0.72 (50 pairs). Inter-annotator agreement was 70% (κ=0.41).
- Results: 132 tasks under relevance-first ordering. Solve rates 42.9%-58.2% across five frontier models.
- Stated limitation, quote (§6 Construct Validity): "test-pass remains a necessary, not sufficient, correctness signal: a model could in principle satisfy the tests through narrow patches or test-specific workarounds without addressing the developer's broader intent." Planned work, quote (§6): "extending REAP to multi-turn conversations would require revisiting the task classifier to handle iterative prompts".
- Artifact: an anonymous artifact link (anonymous.4open.science/r/REAP_artifact) appears in the HTML. Not opened. The benchmark itself is internal.
- Overlap: trace → executable task (production) **high**; corrections **none** (excluded by design); verifier audit **low** (classifier accuracy only, no FA/FR on candidate patches).

### 3.3 Terminal-Universe (arXiv 2609.04148, Qwen Team, Alibaba; Tsinghua): MEDIUM overlap

- v1 3 Sep 2026. Turns recorded agent trajectories into reusable terminal environments in four steps:
  - deterministic replay of file operations;
  - agentic completion of missing files;
  - Intent Recovery of the original task;
  - new tasks: Single-WS, Cross-WS, and Multi-Round via a user agent.
- Sources are **public agent-trajectory corpora**, not real-user sessions (Table 12, App. A). Trajectories → environments: SWE-rebench 67,074 → 6,118; SWE-smith 95,851 → 8,476; CoderForge 32,964 → 3,978; SWE-Gym 4,152 → 929; LFM2-Terminal 139,841 → 46,037; others. Terminal-Bench-derived sources are excluded.
- Correction handling in Intent Recovery, quote (App. C.1): "For a multi-round trajectory, the first substantive request sets the task topic; later requests are incorporated only when they clarify, constrain, or extend the same task, and unrelated task shifts are excluded." The Multi-Round user agent synthesizes "feature conflict" turns that "modif[y] or override[] prior specifications" (§3.2).
- Verifier: an agent-authored pytest suite. Trajectories are kept only if all tests pass. No human validation of verifiers.
  - Limitation, quote (§7): "a single teacher generates tasks, solutions, and verifiers. Its capability gaps may therefore limit task coverage, while errors it makes in solutions may also be missed by its tests."
- Results: 37.3k task-sufficient environments; 31,977 SFT demonstrations. SFT of Qwen3.5-27B gives +11.9 on Terminal-Bench 2.1 (58.1%) and +13.8 MT@4 on EvoCode-Bench v2.
- Overlap: trace-derived construction **high** (agent traces, training scale); corrections **low-medium** (folded into intent for multi-round traces, but the traces are mostly benchmark rollouts); verifier audit **none**.

### 3.4 ARE-bench (arXiv 2611.14364): MEDIUM overlap (on the measured quantity, in a research domain)

- v1 10 Nov 2026. 75 tasks "built on agent sessions and full workspaces from recruited researchers' own projects", with 1,173 binary checklist items.
- Construction (§3.2):
  - a Curator recovers goals, requirements and "their revisions" and flags rejections and redo requests;
  - a Builder cuts the session at a real request, summarizes "earlier requests still in effect" as Background, and replays the workspace to the cut point;
  - a Validator calibrates the judge with an empty delivery and a fabricated delivery, plus human review of failed items.
- Rubric policy, quote (§3.2.2): "Requirements raised only in later turns and personal preferences are excluded." Second quote (§3.2.2): "Items do not prescribe implementation paths, so any valid alternative passes."
- Key measurement (§4.2.2, Table 8; same deliveries and item verdicts, only the checklist scope changes):

| Model | Contracts + norms | + historical & material/workspace reqs | Full checklist |
|---|---|---|---|
| DeepSeek-V4.1-Flash | 69.33 | 40.00 | 39.56 |
| GLM-5.3-Flash | 69.33 | 31.56 | 30.67 |
| Kimi-K3 | 69.78 | 28.44 | 28.00 |

- Quote: "Among runs passing the first group of checks, 66, 85, and 93 still fail at least one historical or material or workspace requirement, accounting for 48.5%, 54.5%, and 57.4% of each model's total failed runs."
- The judge is an LLM. Cross-judge binary agreement is 92.76%, κ=0.717, on 9,874 paired verdicts. Quote (§4.6.1): "Independent human annotations are the next step for attributing disagreements and completing the evidence on judge reliability."
- Release: "We release only the minimum workspace content needed to reproduce each task" (Ethics). The repository URL was not extracted.
- Overlap: session-derived tasks **high**, but research tasks with LLM-judged checklists rather than executable tests. Carrying forward still-active earlier requests **high**. The measured "score inflation when context requirements are omitted" is the closest *agent-evaluation* analogue of our correction-omission FA. It is not a verifier-FA study, and it has no human labels.

### 3.5 VerifierBench (arXiv 2610.28679): MEDIUM overlap overall, HIGH on audit design

- Authors: Jianing Yin, Ziyi Chen, Hao Wang, Yiyou Sun, Zijian Jin, Dawn Song, Daoan Zhang (UPenn, UIUC, UC Berkeley, NYU per HTML). v1 19 Oct 2026; v2 30 Oct 2026. Two authors (Daoan Zhang, Ziyi Chen) also appear on TraceDance (ByteDance/UIC) and Veritas.
- Task: "from the instruction and environment available for solving a task, an agent writes an executable verifier that must accept every valid solution and reject invalid ones" (abstract).
  - 222 tasks from six agent benchmarks; 4,993 hidden test cases (1,566 PASS, 3,427 FAIL).
  - Categories (App. C, Table 10): gold 222; cosmetic 840; overstrict_trap 504 ("Uses an alternative implementation or execution path; tests acceptance of valid alternatives"); base 222 ("Uses an initial, unrepaired, or otherwise unfinished outcome"); partial 999; near_miss 907; regression 501; hack 796; process_violation 2.
- V4V screening (§2.3) has six checks: replay, repeatability, provenance, input-label consistency, trivial baselines, mutation testing. 45 of 267 initial tasks were excluded, including all 37 Terminal-Bench tasks: "35 of them because its test-output parser counts skipped tests as passes".
- Metric: normalized task-averaged balanced accuracy, BA_norm = TPR + TNR − 100. It ranges from 10.6 to 62.1 across 19 models.
  - Quote (abstract): "generated verifiers consistently rejecting invalid solutions more reliably than they accept valid ones."
  - All-reject verifiers contribute 87.9-96.0% of each model's false rejections (§3.4).
- Label validity, quote (Limitations): "agreement between construction labels and reference decisions does not certify that every label is semantically correct." So the labels are construction labels confirmed by source verifiers, **not human adjudication**.
- License: "Original VerifierBench scripts and annotations use Apache 2.0; upstream-derived content retains its source terms" (App. B).
- Overlap: tasks are taken from existing benchmarks, so trace-derived construction **none** and corrections **none**. The held-out pool of valid variants, near misses, base/unfinished states and hacks is **high** overlap with our candidate design and with "verifiers that over-reject valid alternatives".

### 3.6 TiGanEval (arXiv 2610.17757): LOW-MEDIUM overlap; useful base rate

- Authors: Kaiming Liu, Yuxuan Liu, Jinrui Ju, Minyuan Ruan, Xuanyu Lei, Peng Li, Yang Liu. v1 13 Oct 2026. Code: github.com/THUNLP-MT/TiGanEval (link seen; not opened).
- Base-rate study (App. B): 100 randomly sampled SWE-chat trajectories, "with an average of 17.11 user turns per trajectory". Human annotators.
  - Quote (App. B, Results): "We find that 56% of the sampled trajectories have incomplete initial instructions, indicating that the initial request does not cover all requirements that ultimately emerge during task completion."
  - 52.49% of useful follow-up requirements "could have been inferred from the preceding trajectory".
- Benchmark: TiGanTrans converts existing fully specified tasks into partial-instruction tasks with discoverable requirements, plus human expert review. Models "lose 53 to 67 points of success rate when moving from the full specification to the partial instruction" (abstract).
- Overlap: supports our premise that initial-only contracts omit requirements; agent-side; no verifier audit.

### 3.7 Requirements After the First Edit (arXiv 2609.03028): LOW-MEDIUM overlap; base rates and replay feasibility

- Authors: Bowen Jiang, Haowei Cheng, Yuhong Fu, Anne Koziolek, Jialong Li, Weixing Zhang (KIT, Waseda, Adelaide). v1 2 Sep 2026.
- Funnel (§5.1, Fig. 7): "5,851 raw sessions → 3,553 eligible → approximately 2,060 clean-start reconstructible → 402 sessions carrying at least one canonical emergence event → 921 canonical emergence events."
  - *My arithmetic:* 402/2,060 ≈ 19.5% of reconstructible sessions carry such an event. A secondary site (agentpatterns.ai) summarized this as 18-22%; not used as a source.
- Scope caveat, quote (§6.5): "it excludes failure-triggered correction and does not encompass all forms of progressive clarification or environmentally induced requirements change." Inference: their count is therefore a *lower bound* on the corrections TraceContract cares about.
- Core finding, quote (abstract): "A requirement's arrival is followed by roughly twice as much invalidation as matched non-requirement edits, robust to user-turn and net-deletion checks, though not demonstrated as causal."
- Measurement reliability (§5.1.1):
  - 437 stratified units double-coded by humans; 329 held out.
  - Pooled LLM requirement-detection precision is 0.78.
  - In a blind audit, human recoding agrees with 93 of 100 auto-accepted events.
  - On 150 sampled events, a semantic LLM-adjudicated audit labels 55% requirement-driven, 31% incidental, 14% unclear.
- Overlap: no tasks and no verifiers. It shows SWE-chat line-level replay is feasible in about 58% of eligible sessions and gives a conservative prevalence estimate.

### 3.8 TestJack (arXiv 2610.10619) and UserSWE (arXiv 2610.29822)

- **TestJack.**
  - Authors include Koushik Sen, Baishakhi Ray, Dawn Song. v1 7 Oct 2026.
  - Per-trial auditing generates tests "targeting prompt requirements the patch may violate". It keeps only tests passed by the ground-truth patch.
  - Result: "about 34.4% of the model trials currently judged correct violate the task requirements, lowering the overall resolution rate from 50.6% to 33.2%" (abstract; 6 backends × 5 benchmarks).
  - Its precision/recall are internal. Quote (App. E): "Recall and precision in RQ2–RQ4 measure agreement with the per-trial audit rather than with a human-labeled ground truth."
  - Code: anonymous.4open.science/r/testjack-C1A7 (not opened).
  - Overlap: false-acceptance measurement on benchmark tasks; no sessions; no corrections.
- **UserSWE** (Tencent Hunyuan).
  - Multi-turn bug fixing with a dynamic simulated user, persona transitions calibrated on "20,859 real development sessions from an internally deployed commercial coding assistant" (§4.2). 72 tasks, 42 repos, 11 agents.
  - The abstract explicitly frames existing evaluation as producing "both false positives and false negatives".
  - Verdicts are written by a Judge and gated by a Reviewer from another model family. The Reviewer "rewrote 40.9% of Judge decisions" (§5.3.1).
  - An "equivalent pass" route rewrites interface-bound tests for valid alternatives. 14.6% of cells filed at least one equivalence request, and 51.2% of requests were granted (§5.3.2).
  - Humans review simulator utterances (50 human-hours; App. B.4), not verdicts.
  - Overlap: low-medium (FR mitigation for valid alternatives; tasks built from repo history, not sessions).

### 3.9 TraceDance (arXiv 2609.33295; ByteDance Inc. USA and UIC): LOW-MEDIUM overlap

- v1 27 Sep 2026. Builds "targeted benchmarks from deployment traces for user-specified undesirable behaviors".
- Data: 252,557 sessions over six weeks from Claude Code (coding) and OpenClaw (general tool use), "collected from agents powered by frontier LLMs, primarily the Doubao Seed 2.0 family" (data section). Traces are not released ("not release these agent traces").
- Evaluation is by "decision-point continuation ... without a reference answer or environment replay" (abstract), with behavior-specific rubrics.
- Human agreement (appendix): on 84 instances, the judge panel has κ=0.40 against humans versus 0.31 between annotators. Humans pass only 16.7% of responses.
- Output: 107 benchmarks, 4,125 instances; nine LLMs have a mean pass rate of 26.7%.
- Overlap: a trace-to-benchmark pipeline at an industrial lab. It does not produce executable tasks, does not model corrections as requirements, and has no FA/FR on code.

### 3.10 SpecPath (arXiv 2608.09799) and decision pins (arXiv 2610.03237)

- **SpecPath** (v1 10 Aug 2026).
  - Formalizes an evolving request as requirement atoms with restatement, override and cancellation: M_t = (M_{t-1} \ D_t) ∪ A_t (Eq. 2). Histories are "contract-equivalent" when replay and normalization give the same final contract (Eq. 3).
  - It holds "repository, final contract, verifier, agent system, and execution budget fixed while changing only the revision path".
  - Result: "35 of 100 complete blocks that succeed on the direct specification fail on at least one equivalent history" (abstract). Five calibrated tasks; 14 agent configurations.
  - Overlap: a formal model of an active contract under corrections that resembles our full-session contract. It is used to test agents, not verifiers.
- **Decision pins** (Takeharu Mitsui; v1 2 Oct 2026).
  - Quote (abstract): "across 600 generated test suites from three models, 42.7% contain no test that distinguishes the competing readings."
  - Pins are confirmed by executing two throwaway implementations that differ in one decision point. They "agree with the benchmark's classification on 96-97%" of 703 implementations.
  - Overlap: generated tests silently fail to encode a user's chosen reading. This is the mechanism behind correction-omission FA, shown on a 40-task benchmark without sessions.

### 3.11 When the Reward Suite Is Leaky (arXiv 2607.11022): LOW overlap; methodological precedent

- Chuyifei Zhang, v1 13 Jul 2026. A preregistered GRPO contrast on MBPP original tests (leaky) vs MBPP+ (hardened).
- Quote (abstract): "Auditing every rewarded FP under signed, human-adjudicated rules finds a large residual of verified genuinely wrong code: 47.57% record-weighted". A static leakiness audit tracks rewarded FP mass (Spearman 0.80).
- Overlap: precedent for preregistration plus human-adjudicated FP audits of verifiers. Function-level tasks, no sessions.

---

## 4. Tier 2: other 2026 candidates (abstract-level unless noted); one-line overlap

| Work (arXiv; v1 date) | What it is (as stated in abstract) | Overlap with TraceContract |
|---|---|---|
| VibeSWEBench (ICML 2026 workshop; OpenReview kWrudm978A) | "Trajectory Unrolling ... converts authentic human–agent failure sessions into independent single-turn tasks" "while preserving human-authored corrective signals"; "human-validated test suites with no LLM-as-a-judge"; 109 tasks on two real backend projects; best 20.87% (Codex + GPT-5.5) | **Medium, but unverifiable details.** Correction-preserving session → task conversion with human-validated tests. Whose sessions, how corrections are encoded, and any FA/FR measurement are all unknown (full text not retrieved) |
| DuMateBench (2608.26546; 27 Aug 2026) | 200 tasks from "anonymized and privacy-screened user sessions collected from a large-scale production agent platform"; preserves "pre-solution interaction history, persistent configurations, and workspace state"; human verification; hybrid deterministic + LLM judge | Low-medium: real sessions → tasks with history, office workflows; no verifier FA/FR |
| EnterpriseClawBench (2606.23654; 22 Jun 2026) | 852 reproducible tasks from proprietary real workplace sessions; "recovered fixtures, rewritten prompts ... hard rules, and semantic rubrics"; data not released | Low-medium: session → task, not code-specific, no verifier audit |
| K-Bench 01 (2608.21601; 21 Aug 2026) | First-turn requests sampled from live K-Dense Web traffic; 1,602 runs; three blinded LLM judges, 8-dimension rubric | Low: initial-request-only by design |
| SWE-TaskFlow (2610.09633; 7 Oct 2026; JetBrains Research) | 4,782 JetBrains-IDE "Production Sessions"; transforms issue benchmarks into multi-turn flows "while steering the interaction toward a target Task Flow"; pilot on 700 SWE-Bench Pro tasks | Low: real session statistics shape interaction; tasks and tests from existing benchmarks |
| RealSWE (2608.27831; 28 Aug 2026) | SWE-chat prompt taxonomy: "requests carrying only a problem statement ... account for 88% of real prompts but just 7% of benchmark problems"; 381 task families from SWE-bench Verified/Pro | Low: prompt realism, not corrections |
| SWE-RPG (2608.09072; 10 Aug 2026) | 163 tasks with ground truth for requirement clarification and planning; implicit requirement recovery is the main bottleneck in "24.5%--46.0% of agent runs" | Low |
| FeatureArc (2610.37434; 27 Oct 2026; Tencent) | Evolving-feature tasks from repository histories with per-stage F2P/P2P; success falls from 62.7% at the first stage to 28.5% on the whole feature; "guides the development of Hunyuan" | Low-medium: cumulative requirements; synthetic from history |
| SWE-DIVE (2610.30047; 21 Oct 2026) | User simulator plus "conversation validator", embedded in Harbor | Low |
| SWE-Journey (2610.11559; 8 Oct 2026) | Long-horizon synthesized tasks; four personas mined from real interaction data | Low |
| RealCLI (2610.22507; 15 Oct 2026) | Scripted user delivering "progressive information, corrections, constraint revisions, and authorization decisions" | Low-medium (scripted corrections) |
| MTAC-IFBench (2609.14992; 14 Sep 2026) | Multi-turn agentic coding instruction-following; 7.04 turns and 91.33 constraints per instance; checklist with scripts plus judge agents | Low |
| LLMs Get Lost in Evolving User Intent (2607.20734; 22 Jul 2026) | Transforms single-turn tasks into conversations where intent is "incrementally revealed, revised, and at times redirected ... while preserving each task's original evaluation protocol" | Low (agent-side) |
| Intent-Eval (2610.06496; 5 Oct 2026) | "mentioned-as-in-effect confusion" for rejected and superseded requirements | Low; relevant failure mode for LLM contract extraction |
| IntentDelta (2610.33806; 24 Oct 2026) | 638 human-constructed trajectories with cumulative intention states (WebShop, TravelPlanner) | Low; useful for annotating active contracts |
| Drift-Bench++ (2609.38604; 29 Sep 2026) | "verified executable tasks with controlled misalignment and intent shifts"; validated on "deployed ProdAgent sessions" | Low |
| LiveAsset (2611.11560; 8 Nov 2026) | Learns "intent assets" from multi-turn corrections, "preserving earlier requirements that remain applicable", for runtime verification | Low-medium (corrections → checks, runtime) |
| CAPA (2607.26611; 29 Jul 2026) | Cross-session personalized ambiguity; 600 sessions, synthetic | Low |
| How Coding Agents Fail Their Users (2605.29442; v2 31 Aug 2026) | 20,574 sessions from 1,639 repos; "91.49% of visible resolutions still require explicit user correction" | Low (base rate) |
| DECODE (2607.25130; v3 27 Oct 2026) | 53.6K in-IDE edits of AI code; LLMs inferring edits | Low |
| TestJack (§3.8) / BSG-VA (2607.28871) | BSG-VA: "46.0% of positive comparable events carry no bug-discriminating information" | Low |
| Building to the Test (2606.28430; 26 Jun 2026) | Agents with an oracle in the loop reach a near-perfect score "from a demo holding the tested behavior directly" | Low (verifier gaming case study) |
| Specification-oracle gaps (2610.30635; 22 Oct 2026) | Static audit (held-out precision 89.2%, recall 92.9%); 25 of 98 SWE-Milestone milestones depend on unstated names or paths | Low-medium (FR from over-specific tests) |
| Between Spoilers and Guesswork (2610.22760; 16 Oct 2026) | Over- vs under-specification of task statements | Low |
| ExLabel / SWE-TQ (2610.39417; 29 Oct 2026) | LLM annotator of task clarity and test coverage vs cleaned human annotations | Low |
| Unearned passes (2609.34262; 28 Sep 2026) | 3,810 passing trajectories; confirmed violation rates "rise from 24% to 73% between Opus 4.7 and Fable 5" on SWE-Bench Pro V1.0 | Low |
| SpecGuard (2610.09159; 6 Oct 2026) | Lean-certified intent–test conflicts; "detects up to 72.8% of conflicts and formally certifies up to 51.1%" | Low |
| BenchGuard (2604.24955; COLM 2026) | LLM auditor of benchmark artifacts; "exactly matched 83.3% of expert-identified issues" | Low |
| Groundability (2610.01023; 1 Oct 2026) | Weak reviewers on 411 execution-labeled traces; frozen cascade over-rejection 0.66 and 0.67 | Low-medium (held-out, frozen-format review evaluation) |
| CodeSpecWeave (2610.40256; 29 Oct 2026) | Synthesizes interdependent specifications; review agent audits multi-model trajectories so tests avoid "overlooking hidden flaws or rejecting valid alternatives"; RL on 4,670 tasks | Low |
| DeepSWE (2607.07946; 8 Jul 2026) | Hand-written verifiers; independent LLM judge disagrees "1.4% versus 32.4%" (DeepSWE vs SWE-Bench Pro) | Low; source of the LLM-judge label protocol that SessionFarmer copies |
| Veritas (2611.13336; 9 Nov 2026) | Verifier-generation harness; "official verifiers we first certify"; agreement with official verdicts | Low-medium (verifier generation baseline) |
| Interaction-as-a-Judge (2610.17895; v3 23 Oct 2026) | 222 apps with "human-verified requirement labels"; requirement verification 77.0% → 81.6% | Low |
| Re-executing evaluations (2610.14460; 10 Oct 2026) | Preregistered; a "reconstructed module cache ... rejected accepted alternatives from four models" | Low (environment-induced FR) |
| When Terminal-Agent Training Stalls (2610.02405; 1 Oct 2026) | Calls for "verifier audits ... as first-class evaluation criteria" in meta-agent task generation | Low |
| AutoRefine (2611.09291; 6 Nov 2026) | Calibrates code judges to merge/abandon outcomes (Scott's π 0.16 → 0.51 on 17 held-out diffs) | Low (production outcome labels as noisy ground truth) |
| Terminal-Universe follow-ons: WorkBorne (2610.14915), Trajectory2Gym (2610.33568), Trace2Env (2610.06100), BenchMeUp (2610.37283), CodeMidas (2609.22068, title/search only) | Environment and task synthesis from artifacts, trajectories or specifications. Trace2Env builds a "worldbook" rather than an executable environment | Low |
| JoyFrontBench (2611.14952; 11 Nov 2026) | "goal-oriented acceptance contracts" fixed before generation; 2,596 atomic criteria from practitioner requirements | Low (term "contract" overlaps; not session-derived) |
| Tracybot (2611.09395; 6 Nov 2026) | Links agent-generated lines to the prompts ("Tasklets") that produced them | Low (provenance tooling) |
| Replay Fidelity in AppWorld (2611.11216; 8 Nov 2026) | Replays 71 failed executions; hidden-state discrepancies "despite matching outputs and verdicts" | Low (replay-fidelity caveats) |

---

## 5. Companies and labs publicly describing trace-to-environment or trace-to-benchmark pipelines (2026)

All verified on the primary page unless marked otherwise. This adds to `sfdata.md` (SF Data) and `training_and_datasets.md` (Hugging Face traj2envs).

| Org | Artifact | What is stated | Corrections? | Verifier validation |
|---|---|---|---|---|
| Meta | REAP/Harvest (2604.01527, ASE 2026 Industry Showcase); AfterVibe (2607.09900, affiliation "Meta, USA" in HTML; "TechInternal" sessions from "an internal AI coding assistant") | Production developer-agent sessions → rolling F2P-tested benchmark; AfterVibe extracts graders from multi-turn sessions | REAP: single-turn only, by design. AfterVibe: multi-turn sessions | REAP: classifier accuracy vs 2 annotators. AfterVibe negative controls: pre-change (parent commit) code passes 0.0% of VCs and 58.0% of flex tests (Table 4; re-verified) |
| ByteDance (with ShanghaiTech, Shanghai AI Lab) | SessionFarmer/CropEnterprise (2611.02440); TraceDance (2609.33295) | Enterprise sessions → executable tasks (56 tasks; developer audit); 252,557 deployment sessions → behavior benchmarks | SessionFarmer: yes (full episode) | LLM-labeled FP/FN; developer audit of statements |
| Alibaba Qwen | Terminal-Universe (2609.04148); Verification Horizon (2606.26300; see sibling notes) | Public trajectories → 37.3k environments for SFT | Partially (Intent Recovery) | None for verifiers |
| Tencent (Hunyuan) | UserSWE (2610.29822); FeatureArc (2610.37434) | 20,859 internal sessions calibrate the user model; FeatureArc "extends internal evaluations" | Simulated | Judge plus cross-family reviewer; F2P/P2P |
| Baidu (per secondary press) | DuMateBench (2608.26546) | Production agent-platform sessions → 200 tasks with pre-solution history | History preserved | Human verification of tasks |
| JetBrains Research | SWE-TaskFlow (2610.09633) | 4,782 IDE production sessions measured; interaction distribution transferred to benchmarks | n/a | Existing benchmark tests |
| K-Dense | K-Bench 01 (2608.21601) | Live-traffic first-turn requests | No | 3 LLM judges |
| Cursor | Blog "Improving Composer through real-time RL" (Mar 26, 2026) | Quote: "We serve model checkpoints to production, observe user responses, and aggregate those responses as reward signals." Signals include "Agent edit persists in codebase" and "User sends dissatisfied follow-up" | Implicit, via dissatisfied follow-ups as reward | No tests or human labels mentioned. Reward hacking reported: Composer "learned to defer risky edits by asking clarifying questions" |
| Unnamed Chinese coding-agent service | Trace2Eval (2611.06506; see `trace2eval.md`) | 20,000 traces → 129 tasks | Not modeled | Calibrated LLM rubric judge vs humans |

Secondary-only (not primary, not used as evidence):
- AWS AgentCore RL-toolkit blog (Sept 2026, seen in search results). It reportedly argues production traces are skewed and unlabeled.
- Gradient blog (Jan 2026) on environment startups collecting production data.
- Bespoke Labs funding news.

---

## 6. Works citing SWE-chat or Trace2Eval (Semantic Scholar snapshot, 2026-11-13)

- **SWE-chat (2604.20779): 68 citing records.**
  - Closest to us: SessionFarmer 2611.02440; Requirements After the First Edit 2609.03028; TiGanEval 2610.17757; PersonaCodeBench 2611.05739; SWE-Together 2606.29957; RealSWE 2608.27831; TraceDance 2609.33295; FeatureArc 2610.37434; SWE-DIVE 2610.30047; SWE-Journey 2610.11559; SWE-TaskFlow 2610.09633; LiveAsset 2611.11560; How Coding Agents Fail Their Users 2605.29442; DECODE 2607.25130; LLMs Get Lost in Evolving User Intent 2607.20734; "Don't Guess, Just Ask" 2610.13022; Dialogue SWE-Bench 2606.13995.
  - Also listed without arXiv IDs: "Do Personalized Skills Help Coding Agents? An Empirical Study of Developer Interaction Histories" and "GHAW-H: A Dataset of GitHub Agentic Workflow Histories" (not opened).
- **Trace2Eval (2611.06506): 0 citing records in S2** (published 4 Nov 2026). No citing work was discoverable by arXiv search either.
- **SessionFarmer (2611.02440): 0 citing records.**
- ARE-bench 2611.14364 is **not** in the SWE-chat citing list. S2 lists it as citing SWE-Together 2606.29957 and RealClawBench 2606.03889.
- Citing SWE-Together or SWE-INTERACT, the newest relevant: Switch-SWE 2611.02017; RealCLI 2610.22507; UserSWE 2610.29822; SWE-Clar 2610.31854; StateHarness 2610.17616; Terminal-Universe 2609.04148; "Eliciting Specifications" 2610.22382; SWE-Touch 2608.02499; SpecPath 2608.09799.

---

## 7. Component-by-component overlap matrix (my assessment; H/M/L/–)

Components: (A) trace-derived executable task construction; (B) preservation of later user corrections as requirements; (C) executable verifier; (D) verifier audit with held-out, human-labeled candidates including valid alternatives (and, for us, session-native pre-correction negatives).

| Work | A | B | C | D | Notes |
|---|---|---|---|---|---|
| SessionFarmer (2611.02440) | H (SWE-chat + enterprise) | H (statement level, provenance, withdrawals) | H (LLM tests + rubrics) | M | FP/FN vs **LLM** labels; mutants inside the loop; no initial-only verifier; no valid-alternative pool |
| SWE-Together (sibling notes) | H | H (simulator, gates, rubric) | M (rubric judge) | L | |
| traj2envs (sibling notes) | H (trace → Harbor tasks; `build` = initial-only, `extend`) | M | H | L-M (trial matrix, mutants; trivial negatives) | |
| REAP (2604.01527) | H (production) | – (single-turn by design) | H (production F2P tests) | L | |
| Terminal-Universe (2609.04148) | H (agent traces) | L-M | M | – | |
| ARE-bench (2611.14364) | H (research sessions) | H (Background of still-active requests) | L (LLM checklist) | L-M (context-omission inflation; LLM judge) | |
| VerifierBench (2610.28679) | – | – | H (generated verifiers) | H (held-out valid and invalid pools; construction labels, not human) | |
| PersonaCodeBench (sibling notes) | L-M (persona-derived) | H | M | M (blinded expert review of requirement judgments) | |
| AfterVibe (sibling notes, re-verified) | H (internal sessions) | M | H | M (negative controls: pre-change = parent commit, degraded, wrong) | |
| TellOnce (sibling notes) | – (future tasks) | H (corrections → checks) | H | M (generated probes; correction-conflict replay) | |
| TestJack (2610.10619) | – | – | H | M (FA, no human labels) | |
| UserSWE (2610.29822) | L | M (simulated) | H | L-M (equivalence passes) | |
| TiGanEval (2610.17757) | – | M (partial vs full instruction) | H | – | |
| Requirements After First Edit (2609.03028) | – (replay only) | M (measures late requirements) | – | – | |
| SpecPath (2608.09799) | – | M (formal active contract) | H | – | |
| Decision pins (2610.03237) | – | M (user-chosen readings) | H | M (96-97% agreement on 703 implementations) | |
| VibeSWEBench (ICML-W) | H? | H? ("preserving human-authored corrective signals") | H ("human-validated test suites") | ? | Abstract only |

Inference: no single work has A+B+C+D with **human-labeled** FA/FR. No work runs the **initial-only vs full-session verifier** counterfactual on one fixed candidate pool. No work uses the **agent's observed pre-correction state** as a held-out negative.

---

## 8. Strongest novelty objection and a surviving narrower contribution

**Strongest objection (steel-manned).**
- SessionFarmer (2 Nov 2026) already does the following:
  - (i) reconstructs executable tasks from the same SWE-chat sessions;
  - (ii) builds full-episode, correction-aware specifications with per-clause turn provenance, including withdrawn requirements;
  - (iii) shows that first-message-only specifications miss most requirements (26% vs 75% full coverage on multi-session tasks);
  - (iv) audits LLM-written verifiers for both false acceptance and false rejection, with requirement-breaking mutants and a blind solver, reporting FPR, FNR and balanced accuracy.
- VerifierBench (Oct 2026) already scores verifiers on held-out pools of valid alternatives, near misses, unfinished "base" states and hacks.
- ARE-bench (10 Nov 2026) already shows that omitting historical requirements roughly halves strict success.
- On this reading, TraceContract's 2x2 (contract source × audit) is a recombination of published parts. Its "reward fidelity" is SessionFarmer's Table 3 renamed.

**What the objection does not cover (verified gaps).**
1. Verifier-level counterfactual on contract source.
   - SessionFarmer measures the initial-only condition only as statement coverage.
   - It never builds verifiers from the opening request and asks how often *they* accept solutions the user later rejected.
   - Its App. D lists the analysis of later-disclosed requirements as future work.
2. Human ground truth.
   - SessionFarmer, VerifierBench, TestJack, ARE-bench and TraceDance all score against LLM judges, construction labels or reference verifiers.
   - SessionFarmer's humans validate statements and rubrics, not patch correctness.
   - ARE-bench calls human annotation "the next step".
3. Session-native negatives with provenance.
   - The agent's actual pre-correction code state, which the user explicitly rejected in the session, appears in no audit pool.
   - The nearest relatives are different: SessionFarmer's mutants are constructed and used in the loop; VerifierBench's "base" cases are constructed; AfterVibe's "pre-change" is the parent commit; TellOnce v1 replays correction-conflict pairs, but for future-task rules.
4. Held-out discipline.
   - SessionFarmer's mutants and blind-solver patches shape the final tests. Its evaluation rollouts are separate, but the labels are LLM-generated.
   - A frozen, never-used-in-construction pool that includes valid alternatives does not exist for session-derived tasks.

**Narrower contribution that should survive (INFERENCE; to be pre-registered).**
- "*How often does omitting a user's later correction make a session-derived verifier accept the very behavior the user rejected, and what false-rejection cost do audits that prevent this impose?*"
- Measured on session-derived tasks with the following design:
  - (a) one frozen verifier-generation procedure, run from initial-only vs full-session contracts, each with and without a predefined audit; plus existing repository tests and a competent full-session LLM reconstruction baseline (for example, a SessionFarmer-style pipeline, if its code becomes available);
  - (b) one frozen held-out candidate pool per task: the agent's pre-correction state, constructed near-misses, and independently written valid alternatives;
  - (c) independent human adjudication of every candidate, with LLM-judge labels reported next to it, so the LLM-vs-human label gap becomes a secondary result;
  - (d) the primary estimand, correction-attributable FA: FA on pre-correction states under initial-only verifiers minus FA under full-session verifiers, with FR on valid alternatives as the guardrail.
- Framed as a measurement study plus a small, high-quality, human-labeled release (tasks, verifiers, candidates, labels). It should not be framed as a new trace-to-task pipeline.
- It must cite SessionFarmer, SWE-Together, traj2envs, VerifierBench, ARE-bench, TiGanEval, PersonaCodeBench, AfterVibe and TellOnce as prior art for each component.

---

## 9. Design implications (INFERENCE)

1. **Use SessionFarmer as the "competent full-session LLM reconstruction baseline".** Its statement-authoring and test-refinement recipe is described in enough detail (App. E prompts) to re-implement if the code stays unreleased. Report its verifiers' FA/FR on our human-labeled pool. This directly tests whether its LLM-label BAcc (60.5-70.8) holds against humans.
2. **Report the LLM-vs-human label disagreement explicitly.** SessionFarmer, DeepSWE and TestJack rely on LLM correctness labels. A quantified gap on pre-correction states and valid alternatives is a contribution in itself.
3. **Separate FA from FR and expect a tradeoff.** SessionFarmer's refinement *raised* FPR by 16-17.5 pp while cutting FNR by 32-34 pp. The audit arm of our 2x2 should be judged on both, with a pre-registered primary metric (for example, FA on pre-correction states at a capped FR on valid alternatives).
4. **Borrow VerifierBench's candidate taxonomy and V4V-style checks for label hygiene**: replay, repeatability, provenance, input-label consistency, trivial baselines, mutation. Then add human adjudication on top, which VerifierBench itself says its labels lack.
5. **Expect small task counts and justify them with base rates.**
   - SessionFarmer: 242 of 5,851 sessions.
   - Late-requirements study: about 58% of sessions are clean-start reconstructible, and about 19.5% of those carry a narrowly defined late requirement.
   - TiGanEval: 56% of 100 SWE-chat trajectories have incomplete initial instructions.
   - These support a design with tens, not hundreds, of high-quality tasks, and power calculations should be per candidate rather than per task.
6. **Handle "mentioned-as-in-effect" errors** (Intent-Eval) and over/under-constraining in contract extraction. SpecPath's atom model (activate, override, cancel) is a ready formalism for the full-session contract and its human audit.
7. **Avoid specification-oracle gaps** (2610.30635) and over-specific tests (SessionFarmer's 68-81% initial FNR): tests must not depend on gold-patch names or paths unless the contract states them.
8. **Positioning against industry.** Meta (REAP) excludes multi-turn sessions. Cursor uses dissatisfied follow-ups as reward, not as verifier requirements. ByteDance (SessionFarmer) uses LLM labels. A human-labeled measurement of correction-omission FA speaks to all three without competing on pipeline scale.

---

## 10. Open questions

1. Will SessionFarmer's code and CropChat be released, and under what license? Both links failed on 2026-11-13. CropChat derives from ODC-By SWE-chat; the paper says an additional redaction pass was applied.
2. How is SessionFarmer's "independent reference requirement ledger" built (human or LLM)? It is not stated in the sections read.
3. Does CropChat preserve the original agent's intermediate (pre-correction) states, or only base and final checkpoints? The paper describes base and final checkpoints plus transcripts. Intermediate states would need replay (as in 2609.03028).
4. VibeSWEBench: what does "preserving human-authored corrective signals" mean operationally, whose sessions are used, and is there any FA/FR measurement? Full text not retrieved: OpenReview challenge, no arXiv version found.
5. Does any lab report human-labeled FA/FR for verifiers of *session-derived* tasks in a venue not indexed by arXiv or S2 (internal reports, blogs)? None found.
6. Are there post-Nov-11 arXiv papers (Nov 12-13 announcements) not yet in S2 or the listings I fetched?

## 11. Not accessed / limitations

- **SessionFarmer artifacts**: github.com/bytedance/SessionFarmer (raw 404; `git ls-remote` prompted for credentials) and huggingface.co/datasets/ByteDance/SessionFarmer-CropChat (HTTP 401). Not accessible on 2026-11-13.
- **OpenReview** (VibeSWEBench, any OpenReview-only work): blocked by a browser challenge (HTTP 403). VibeSWEBench is known only from its ICML virtual page.
- **Semantic Scholar search endpoint**: HTTP 429 after a few calls. Citation endpoints worked. S2 coverage of the newest papers (Nov 2026) is incomplete by nature.
- **Full text not read** for everything in sections 4-5 marked "Abs": abstracts only. Tier-1 items were read in the sections listed in §2, not cover to cover. Figures were not inspected; all numbers come from text and tables in the HTML.
- **Cursor blog**: read via WebFetch, which returns a model-generated summary with quotes. The quotes were not checked against raw HTML.
- Companies' internal pipelines (OpenAI, Anthropic, Google, Cognition, etc.) are not publicly described at the level of trace-to-environment conversion in anything I found. I did not search exhaustively by vendor.
- Downloads (abstract HTML, full-text HTML converted to text, S2 JSON, listings) are in `/tmp/claude-0/-home-user-trace-contract/3951c995-db7e-5b4e-a703-97e326bb42c5/scratchpad/dl/newest_closest/` (about 25 MB). Helper scripts are in `.../scratchpad/scripts_nc/`.
