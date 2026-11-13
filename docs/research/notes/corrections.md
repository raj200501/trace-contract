# Cluster notes: user corrections and feedback in coding-agent interactions (TraceContract)

Access date for every source in this file: **2026-11-13 (UTC)**. Publication and version dates are recorded separately for each source.
Scratch downloads (not part of the repo): `/tmp/claude-0/-home-user-trace-contract/3951c995-db7e-5b4e-a703-97e326bb42c5/scratchpad/dl/corrections/`.

Conventions:
- **VERIFIED** means I read it in the primary source (section named). Quotes are verbatim and at most 2 sentences.
- **INFERENCE** means my reading or judgment, not stated by the source.
- "Abstract only" means I read only the arXiv abstract page (title, authors, dates, abstract), not the full text.
- Q1 = "Does it treat later corrections as requirements that must be preserved in a reconstructed task or verifier?" Q2 = "Does it measure verifier or reward fidelity?"
- Cross-references: SWE-chat, SecureForge, SWE-INTERACT (partly), RealClawBench (abstract), Dialogue SWE-Bench (abstract) and the SWE-Together task-package format are in `swechat.md`. Verifier audits (SWE-bench Verified, UTBoost, PatchDiff, DeepSWE, etc.) are in `verifier_fidelity.md`. Trace2Eval is in `trace2eval.md`. Here I re-verify only what I need for comparisons, and I add new full-text facts for SWE-Together, SWE-INTERACT, RealClawBench and Dialogue SWE-Bench.

---

## 0. Bottom line (short)

1. **The primary paper has two different versions.** arXiv 2606.13174 v1 (2026-06-11) is "Getting Better at Working With You: Compiling User Corrections into Runtime Enforcement for Coding Agents" (method name **TRACE**). v2 (2026-10-25) is "TellOnce: Correcting Coding Agents Once, Improving Their Future Actions" (method **TellOnce**). The experiments, baselines, models and headline numbers differ between versions. Cite the version you mean. v1's TRACE is unrelated to the `ScalingIntelligence/TRACE` repository in our references (that one is "Turning Recurrent Agent failures into Capability-targeted training Environments", arXiv 2604.05336).
2. **TellOnce mines real user corrections, but for the opposite purpose.** It keeps **durable, cross-task personal preferences** and enforces them in **future** tasks. It deliberately **excludes task-specific requirements**: v2 §4.1 says "Task-specific instructions are not stored as lasting rules". The tellonce v1.8.0 release notes (the version used for the paper's runs) say "A bare replacement, a new task requirement, or an explicit one-time exception is not stored." It never reconstructs a task from a session and never asks whether a task verifier rewards what the user wanted in that session. **Q1: no. Q2: partial.** It validates compiled checks on generated cases (176 probes: 1 FP, 2 FN) and its semantic checker on 48 artifacts (2 FP, 1 FN). It does not report human validation of its final preference scorer.
3. **Two TellOnce mechanisms are prior art for our design.** (a) v1 replays "the correction-conflict pair that originated the rule" in a sandbox, so the originating agent mistake serves as a negative test for the compiled check (Appendix C.1). (b) v2 requires that a check "must preserve the meaning, scope, and exceptions of the original rule rather than change the requirement to make it easier to verify". An independent reviewer labels each validation case without seeing the expected labels, and any disagreement rejects the check (§4.2, App. B.2).
4. **Most interactive coding benchmarks invert our setting.** In MINT, ConvCodeWorld, ColBench, Ambig-SWE, Dialogue SWE-Bench, SWE-INTERACT, "When Benchmarks Talk" and RECODE-H, the verifier is fixed in advance (hidden tests or a reference artifact). The simulated feedback only *reveals* requirements the verifier already encodes, and the simulator often sees the ground truth. No user turn ever *adds* a requirement that the verifier lacks. None of these benchmarks measures verifier false acceptance against human labels.
5. **A 2025-2026 line of "evolving requirement" benchmarks already builds cumulative verifiers that preserve later requirements.** These are CodeIF-Bench, FronTalk, SR-Eval, EvoCode-Bench, FeatureLoop, PersonaCodeBench, SWE-Shift and SLUMP. Several also already use our candidate-construction ideas as verifier-construction checks: new-requirement tests must fail on the previous-stage reference (SR-Eval; FeatureLoop eq. 6), plus valid-alternative and targeted-faulty-variant probes (FeatureLoop App. B.3.9). But all of them are **synthetic or author-written** requirement sequences, not real sessions, and none reports FA/FR rates against independent human labels on a fixed candidate set.
6. **Measured analogues of our quantity already exist.**
   - PersonaCodeBench: "179/874=20.5% of complete native-test passes fail the recorded persona criteria" (App. D.3), plus a blinded expert review of its requirement judgments (71.0% agreement, κ=0.473; Satisfied precision 89.2%, recall 74.5%).
   - AfterVibe: graders extracted from real vibe-coding conversations pass 58.0% (flex tests) vs 0.0% (verification conditions) of *pre-change* code (Table 4).
   - CodeAssistBench: LLM-extracted "satisfaction conditions" from issue threads (including later clarifications) were 86.3% accurate but only 65.7% complete by human annotation.
7. **The three works closest to TraceContract** (Section 9.3) are **SWE-Together**, **PersonaCodeBench** and **FeatureLoop**. Next come AfterVibe, TellOnce, CodeAssistBench, EvoCode-Bench and SR-Eval. What still looks open (INFERENCE) is the combination of four things: a controlled initial-only vs correction-aware contract ablation; real sessions; a shared held-out candidate set that includes the agent's *actual pre-correction state* from the session, near-misses and valid alternatives; and FA/FR rates per verifier against independent human adjudication.

---

## 1. Sources consulted

All accessed 2026-11-13. "Depth" says what I read.

| ID | Source | URL | Version / publication date | Depth |
|---|---|---|---|---|
| C1 | Zhou et al., "Getting Better at Working With You: Compiling User Corrections into Runtime Enforcement for Coding Agents", arXiv 2606.13174**v1** | https://arxiv.org/abs/2606.13174v1 ; https://arxiv.org/html/2606.13174v1 | v1 Thu 11 Jun 2026 | full text (HTML, all sections and appendices A-C) |
| C2 | Zhou et al., "TellOnce: Correcting Coding Agents Once, Improving Their Future Actions", arXiv 2606.13174**v2** | https://arxiv.org/abs/2606.13174 ; https://arxiv.org/html/2606.13174v2 | v2 Sun 25 Oct 2026 | full text (HTML, all sections and appendices A-D) |
| C3 | GitHub `YujunZhou/TellOnce_exp` (experiment harness) | https://github.com/YujunZhou/TellOnce_exp (shallow clone) | HEAD abc78f7, committed 2026-10-23; MIT | README, experiments/README.md, LICENSE, `profile_data_clawarena.py` |
| C4 | GitHub `YujunZhou/tellonce` (deployable skill) | https://github.com/YujunZhou/tellonce (shallow clone) | HEAD b918869 = release 1.8.3, committed 2026-10-24; MIT ("Copyright (c) 2026 Tellonce contributors") | README.md, docs/releases/README.md, docs/releases/1.8.0.md |
| C5 | `YujunZhou/TRACE_exp` README (v1's experiment link) | https://raw.githubusercontent.com/YujunZhou/TRACE_exp/main/README.md | fetched 2026-11-13 | byte-identical to the TellOnce_exp README (probably a renamed repo; not confirmed) |
| C6 | Wang et al., "MINT: Evaluating LLMs in Multi-turn Interaction with Tools and Language Feedback", arXiv 2309.10691 | https://arxiv.org/abs/2309.10691 | v1 19 Sep 2023; v3 12 Mar 2024; ICLR 2024 (arXiv comment) | §2.1, §3.6, App. B, App. C.1, F.4.2 |
| C7 | Yang et al., "InterCode: Standardizing and Benchmarking Interactive Coding with Execution Feedback", arXiv 2306.14898 | https://arxiv.org/abs/2306.14898 | v1 26 Jun 2023; v3 30 Oct 2023 | abstract only |
| C8 | Han et al., "ConvCodeWorld: Benchmarking Conversational Code Generation in Reproducible Feedback Environments", arXiv 2502.19852 | https://arxiv.org/abs/2502.19852 | v1 27 Feb 2025; ICLR 2025 (arXiv comment) | §3, §5.1, App. C.3, C.5 |
| C9 | Wang et al., "CodeFlowBench: A Multi-turn, Iterative Benchmark for Complex Code Generation", arXiv 2504.21751 | https://arxiv.org/abs/2504.21751 | v1 30 Apr 2025; v4 15 Apr 2026 | abstract + keyword grep of full text |
| C10 | Zhou et al., "SWEET-RL: Training Multi-Turn LLM Agents on Collaborative Reasoning Tasks" (ColBench), arXiv 2503.15478 | https://arxiv.org/abs/2503.15478 | v1 19 Mar 2025 | §3, §5 Table 2 |
| C11 | Vijayvargiya et al., "Ambig-SWE: Interactive Agents to Overcome Underspecificity in Software Engineering", arXiv 2502.13069 | https://arxiv.org/abs/2502.13069 | v1 18 Feb 2025 (title then "Interactive Agents to Overcome Ambiguity in Software Engineering"); v3 21 Feb 2026; "Accepted at ICLR 2026" | §2, §7 |
| C12 | Pan et al., "When Benchmarks Talk: Re-Evaluating Code LLMs with Interactive Feedback", arXiv 2502.18413 | https://arxiv.org/abs/2502.18413 | v1 25 Feb 2025 (Findings of ACL 2025 per web search only, not verified) | abstract + grep |
| C13 | Laban et al., "LLMs Get Lost In Multi-Turn Conversation", arXiv 2505.06120 | https://arxiv.org/abs/2505.06120 | v1 9 May 2025 | §3-§4 |
| C14 | Wang et al., "CodeIF-Bench: Evaluating Instruction-Following Capabilities of Large Language Models in Interactive Code Generation", arXiv 2503.22688 | https://arxiv.org/abs/2503.22688 | v1 5 Mar 2025; v4 23 Nov 2025 | §3 |
| C15 | Miao et al., "RECODE-H: A Benchmark for Research Code Development with Interactive Human Feedback", arXiv 2510.06186 | https://arxiv.org/abs/2510.06186 | v1 7 Oct 2025; v2 24 Oct 2025 | abstract + §3 |
| C16 | Wu et al., "FronTalk: Benchmarking Front-End Development as Conversational Code Generation with Multi-Modal Feedback", arXiv 2601.04203 | https://arxiv.org/abs/2601.04203 | v1 5 Dec 2025; v3 9 Aug 2026; CoLM 2026 (arXiv comment) | §1-§2, §3 (grep), §4 |
| C17 | King & Flanigan, "Dialogue SWE-Bench: A Benchmark for Dialogue-Driven Coding Agents", arXiv 2606.13995 | https://arxiv.org/abs/2606.13995 | v1 12 Jun 2026 | §3 |
| C18 | Raghavendra et al., "SWE-INTERACT: Reimagining SWE Benchmarks as User-Driven Long-Horizon Coding Sessions", arXiv 2606.30573 | https://arxiv.org/abs/2606.30573 | v1 29 Jun 2026 | §2.2-§2.4, §3.1, §4.1, §5 |
| C19 | Wang et al., "Asuka-Bench: Benchmarking Code Agents on Underspecified User Intent and Multi-Round Refinement", arXiv 2606.05920 | https://arxiv.org/abs/2606.05920 | v1 4 Jun 2026 | abstract only |
| C20 | Peng et al., "ICAE-Bench: Evaluating Coding Agents as Interactive Project Builders", arXiv 2607.21217 | https://arxiv.org/abs/2607.21217 | v1 23 Jul 2026 | abstract only |
| C21 | Zhan et al., "SR-Eval: Evaluating LLMs on Code Generation under Stepwise Requirement Refinement", arXiv 2509.18808 | https://arxiv.org/abs/2509.18808 | v1 23 Sep 2025; v2 17 Mar 2026 | §1, §3, §4.3-§4.4, §5.3, §6.1, §6.3 |
| C22 | Shen et al., "EvoCode-Bench: Evaluating Coding Agents in Multi-Turn Iterative Interactions", arXiv 2605.24110 | https://arxiv.org/abs/2605.24110 | v1 22 May 2026 ("Work in Progress") | §1, §3.2, §4.3, §5, App. B.5, D |
| C23 | Feng et al., "Benchmarking Coding Agents under Evolving Requirements" (FeatureLoop), arXiv 2610.35488 | https://arxiv.org/abs/2610.35488 | v1 26 Oct 2026; v2 29 Oct 2026 | §2, §5, App. B.3.8-B.3.10, C.1 |
| C24 | Huang et al., "SWE-Shift: Evaluating Coding Agents in Evolving Workspaces", arXiv 2610.32196 | https://arxiv.org/abs/2610.32196 | v1 23 Oct 2026 | abstract only |
| C25 | Wang et al., "PersonaCodeBench: Evaluating Coding Agents in Persona-driven Human-Interactive Sessions", arXiv 2611.05739 | https://arxiv.org/abs/2611.05739 | v1 3 Nov 2026 | §1, §2.2-§2.4, §3.5, §4.3, §5, App. A.4, D |
| C26 | Yan, Chen & Zhang, "When the Specification Emerges: Benchmarking Faithfulness Loss in Long-Horizon Coding Agents" (SLUMP), arXiv 2603.17104 | https://arxiv.org/abs/2603.17104 | v1 17 Mar 2026 | abstract only |
| C27 | Wu et al., "SWE-Together: Evaluating Coding Agents in Interactive User Sessions", arXiv 2606.29957 | https://arxiv.org/abs/2606.29957 | v1 29 Jun 2026 | §1-§5 (full text) |
| C28 | Kim et al., "CodeAssistBench (CAB): Dataset & Benchmarking for Multi-turn Chat-Based Code Assistance", arXiv 2507.10646 | https://arxiv.org/abs/2507.10646 | v1 14 Jul 2025; v5 15 Jan 2026; NeurIPS 2025 Datasets and Benchmarks Track (arXiv comment) | §3.1.3, §3.2, §4.3, §5, App. A.4, H, I |
| C29 | Lv et al., "RealClawBench: Live OpenClaw Benchmarks from Real Developer-Agent Sessions", arXiv 2606.03889 | https://arxiv.org/abs/2606.03889 | v1 2 Jun 2026; v3 28 Aug 2026 | §4.2-§4.3, App. B, F |
| C30 | Paltenghi & Chandra, "AfterVibe: What Remains When the Conversation Ends", arXiv 2607.09900 | https://arxiv.org/abs/2607.09900 | v1 10 Jul 2026 | §3.1, §3.3, §4.1, §4.5, §4.7, §4.8, §5, Data Availability |
| C31 | Zhou et al., "ToM-SWE: User Mental Modeling for Software Engineering Agents", arXiv 2510.21903 | https://arxiv.org/abs/2510.21903 | v1 24 Oct 2025; v2 29 Jan 2026 | abstract, §1, §4 |
| C32 | SWE-bench dataset card, `princeton-nlp/SWE-bench` | https://huggingface.co/datasets/princeton-nlp/SWE-bench | HF sha e48e2bd, lastModified 2025-03-03 | field definitions |
| C33 | Ruan, Zhang & Roychoudhury, "SpecRover: Code Intent Extraction via LLMs", arXiv 2408.02232 | https://arxiv.org/abs/2408.02232 | v1 5 Aug 2024; v4 11 Dec 2024; "To appear in ICSE 2025" | abstract only |
| C34 | Endres et al., "Can Large Language Models Transform Natural Language Intent into Formal Method Postconditions?", arXiv 2310.01831 | https://arxiv.org/abs/2310.01831 | v1 3 Oct 2023; v2 15 Apr 2024; FSE 2024 (PACMSE) | abstract only |
| C35 | Voria et al., "RECOVER: Toward Requirements Generation from Stakeholders' Conversations", arXiv 2411.19552 | https://arxiv.org/abs/2411.19552 | v1 29 Nov 2024; v2 17 May 2025 | abstract only |
| C36 | Dou et al., "SimulatorArena: Are User Simulators Reliable Proxies for Multi-Turn Evaluation of AI Assistants?", arXiv 2510.05444 | https://arxiv.org/abs/2510.05444 | v1 6 Oct 2025; EMNLP 2025 Main (arXiv comment) | abstract only |
| C37 | Seshadri et al., "Lost in Simulation: LLM-Simulated Users are Unreliable Proxies for Human Users in Agentic Evaluations", arXiv 2601.17087 | https://arxiv.org/abs/2601.17087 | v1 23 Jan 2026; v2 28 Jan 2026 | abstract only |
| C38 | Zhou et al., "Mind the Sim2Real Gap in User Simulation for Agentic Tasks", arXiv 2603.11245 | https://arxiv.org/abs/2603.11245 | v1 11 Mar 2026; v2 31 Jul 2026; COLM 2026 | abstract only |
| C39 | Suh et al., "Quantifying the Utility of User Simulators for Building Collaborative LLM Assistants", arXiv 2605.09808 | https://arxiv.org/abs/2605.09808 | v1 10 May 2026 | abstract only |
| C40 | Wu et al., "HumanLM: Simulating Users with State Alignment Beats Response Imitation", arXiv 2603.03303 | https://arxiv.org/abs/2603.03303 | v1 7 Feb 2026 | abstract only |
| C41 | Qian et al., "UserBench: An Interactive Gym Environment for User-Centric Agents", arXiv 2507.22034 | https://arxiv.org/abs/2507.22034 | v1 29 Jul 2025 | abstract only (not a coding benchmark) |
| C42 | Wu et al., "CollabLLM: From Passive Responders to Active Collaborators", arXiv 2502.00640 | https://arxiv.org/abs/2502.00640 | v1 2 Feb 2025; v3 29 Jul 2025; ICML 2025 Outstanding Paper (arXiv comment) | abstract only |
| C43 | Lahiri et al., "Interactive Code Generation via Test-Driven User-Intent Formalization" (TiCoder), arXiv 2208.05950 | https://arxiv.org/abs/2208.05950 | v1 11 Aug 2022; v2 4 Oct 2023 | abstract + grep |
| C44 | Fakhoury et al., "LLM-Based Test-Driven Interactive Code Generation: User Study and Empirical Evaluation", arXiv 2404.10100 | https://arxiv.org/abs/2404.10100 | v2 2 Oct 2024; IEEE TSE vol. 50 no. 09 pp. 2254-2268, 2024 (arXiv journal-ref) | §IV, §VI-A, §VII-D, §VII-E |
| C45 | Chen et al., "Improving Code Generation by Training with Natural Language Feedback" (ILF), arXiv 2303.16749 | https://arxiv.org/abs/2303.16749 | v1 28 Mar 2023; v2 22 Feb 2024; TMLR (arXiv comment) | abstract only |
| C46 | Chae et al., "Coffee-Gym: An Environment for Evaluating and Improving Natural Language Feedback on Erroneous Code", arXiv 2409.19715 | https://arxiv.org/abs/2409.19715 | v2 4 Oct 2024; EMNLP 2024 | abstract only |
| C47 | Gao et al., "Aligning LLM Agents by Learning Latent Preference from User Edits" (PRELUDE/CIPHER), arXiv 2404.15269 | https://arxiv.org/abs/2404.15269 | v3 23 Nov 2024 (NeurIPS 2024 per TellOnce reference list) | abstract only |
| C48 | Mehri et al., "MultiSessionCollab: Learning User Preferences with Memory to Improve Long-Term Collaboration", arXiv 2601.02702 | https://arxiv.org/abs/2601.02702 | v3 15 Mar 2026 | abstract only |
| C49 | Ma et al., "ZORO", arXiv 2604.15625 | https://arxiv.org/abs/2604.15625 | v1 17 Apr 2026, "ZORO: Active Rules for Reliable Vibe Coding"; v3 19 Oct 2026, "ZORO: Active Controls to Support Rule Following in Vibe Coding" | abstract only |
| C50 | Sharma, "ContextCov: Deriving and Enforcing Executable Constraints from Agent Instruction Files", arXiv 2603.00822 | https://arxiv.org/abs/2603.00822 | v1 28 Feb 2026; v2 4 May 2026 | abstract only |
| C51 | Anthropic (Societal Impacts), "Measuring AI agent autonomy in practice" | https://www.anthropic.com/research/measuring-agent-autonomy | published Feb 18, 2026 | full page |
| C52 | Hao et al., "An Empirical Study on Developers Shared Conversations with ChatGPT in GitHub Pull Requests and Issues", arXiv 2403.10468 | https://arxiv.org/abs/2403.10468 | v1 15 Mar 2024 | abstract only |
| C53 | Xiao et al., "DevGPT: Studying Developer-ChatGPT Conversations", arXiv 2309.03914 | https://arxiv.org/abs/2309.03914 | v2 14 Feb 2024; MSR 2024 Mining Challenge proposal | abstract only |
| C54 | Zhang et al., "Decoding Human-LLM Collaboration in Coding: An Empirical Study of Multi-Turn Conversations in the Wild", arXiv 2512.10493 | https://arxiv.org/abs/2512.10493 | v1 11 Dec 2025; v2 12 Dec 2025 | abstract + §3 and §5 grep |
| C55 | Zhong, Zou & Adams, "Developer-LLM Conversations: An Empirical Study of Interactions and Generated Code Quality" (CodeChat), arXiv 2509.10402 | https://arxiv.org/abs/2509.10402 | v1 12 Sep 2025; v2 28 Aug 2026 | abstract (v2) only |
| C56 | Watanabe et al., "On the Use of Agentic Coding: An Empirical Study of Pull Requests on GitHub", arXiv 2509.14745 | https://arxiv.org/abs/2509.14745 | v3 9 Feb 2026 | abstract only |
| C57 | Li, Zhang & Hassan, "The Rise of AI Teammates in Software Engineering (SE) 3.0" (AIDev), arXiv 2507.15003 | https://arxiv.org/abs/2507.15003 | v1 20 Jul 2025 | abstract only |
| C58 | Ehsani et al., "Where Do AI Coding Agents Fail? An Empirical Study of Failed Agentic Pull Requests in GitHub", arXiv 2601.15195 | https://arxiv.org/abs/2601.15195 | v1 21 Jan 2026; MSR 2026 | abstract only |
| C59 | Local `/home/user/ScalingIntelligence/TRACE/README.md` | local read-only clone | (task-provided @d2db230) | README head (name-collision check) |
| C60 | Repository LICENSE files fetched via raw.githubusercontent.com (main branch) | see Section 1a | 2026-11-13 | first line of LICENSE only |

### 1a. Artifact licenses I checked (raw LICENSE at `main`, 2026-11-13)
- `Togetherbench/SWE-Together`: Apache-2.0. `MatrAIx-ai/PersonaCodeBench`: MIT. `amazon-science/CodeAssistBench`: Apache-2.0. `scaleapi/SWE-Interact`: Apache-2.0. `sani903/InteractiveSWEAgents` (Ambig-SWE): MIT. `facebookresearch/sweet_rl`: CC-BY-NC ("LICENSE.md"). `YujunZhou/TellOnce_exp` and `YujunZhou/tellonce`: MIT.
- No LICENSE file found at the repo root on `main` or `master` for `AjaxZhan/SR-Eval`, `zhu-zhu-ding/CodeIF-Bench` and `openclaw/clawbench`. That does not prove they lack a license.
- FeatureLoop: I found no artifact link in the HTML. EvoCode-Bench says "We release the benchmark data and Harbor multi-turn infrastructure" (abstract), but I found no link in the HTML. AfterVibe releases prompts only (see 5.3).

---

## 2. PRIMARY: arXiv 2606.13174 (v1 "Getting Better at Working With You" / v2 "TellOnce")

### 2.1 Bibliographic record and version history (VERIFIED, arXiv abstract pages C1, C2)
- Authors (both versions, 11): Yujun Zhou, Kehan Guo, Haomin Zhuang, Xiangqi Wang, Yue Huang, Zhenwen Liang, Pin-Yu Chen, Tian Gao, Nuno Moniz, Nitesh V. Chawla, Xiangliang Zhang. Affiliations in the HTML: University of Notre Dame (most), Tencent AI Lab (Liang), IBM Research (Chen, Gao). Corresponding author: Xiangliang Zhang.
- Subjects: cs.LG, cs.CL. License: arXiv non-exclusive distribution license. No venue is stated in either version.
- v1: submitted Thu 11 Jun 2026 (723 KB). Title "Getting Better at Working With You: Compiling User Corrections into Runtime Enforcement for Coding Agents". Method: "Test-time Rule Acquisition and Compiled Enforcement (Trace)". Code links: `YujunZhou/TRACE_exp` and `YujunZhou/tellonce`.
- v2: submitted Sun 25 Oct 2026 (1,275 KB). Title "TellOnce: Correcting Coding Agents Once, Improving Their Future Actions". Method: TellOnce. Code links: `YujunZhou/TellOnce_exp` and `YujunZhou/tellonce`.
- The tellonce README's BibTeX still uses the v1 title, key `zhou2026trace`.

### 2.2 What counts as a correction
- v1 §4.1 (VERIFIED): a lightweight LLM "evaluates whether it contains a correction signal, such as a durable preference, a notification of a repeated error, or workflow friction."
- v1 §3.1, the diagnostic unit (VERIFIED): "correction-conflict records: instances where a user correction is explicitly paired with an agent behavior that violated it."
- v2 App. B.1, "Admission and interpretation" (VERIFIED): "The correction learner records behavioral requirements that should remain useful in future tasks, including user preferences, recurring sources of friction, and mistakes the user wants the agent to avoid. Task answers and instructions that apply only to the current task are not automatically stored as durable rules."
- v2 App. B.1 gives the boundary examples (VERIFIED): "For example, “Refactor this file” is a task request, while “for this refactor only, add no dependencies” is a temporary constraint. Neither establishes a lasting preference." The same section says "in this project, do not add new dependencies" can establish a project-level rule.
- v2 App. B.1, "Temporary exceptions and lasting updates" (VERIFIED): "be detailed this time" changes only the current task, while "from now on, be more detailed" is processed as an update to the stored rule.
- tellonce 1.8.0 release notes, "Learning from corrections" (VERIFIED, C4): "A bare replacement, a new task requirement, or an explicit one-time exception is not stored."
- INFERENCE: TellOnce's "temporary constraint" and "task request" categories are exactly the corrections TraceContract must keep in a reconstructed task contract. TellOnce discards them by design. Its admission taxonomy is still a useful starting codebook if we invert which classes we keep.

### 2.3 How corrections are mined
- **Diagnostic corpus** (v1 §3.1, App. B.1; v2 §3.1, App. A.1; VERIFIED): one AI researcher's daily work over about two months. It has 32 long-context coding-agent transcripts, each "containing roughly one million tokens of interaction history", from which the authors extracted 142 correction-conflict records. "The diagnostic source corpus is a deliberately single-user dataset" (v1 B.1). All transcripts were anonymized before annotation.
- **Held-out task selection** (VERIFIED): 19 tasks were hand-curated with three filters applied in order: Repetition, Deduplication, Self-contained context. "The underlying preference is removed from each task prompt, so the agent receives the coding request and surrounding context but not the target preference itself" (v1 §3.1). The 19 tasks contain 29 manually annotated preference checks, "labeled by one author and independently audited by a second, with disagreements resolved by discussion before finalization." The stores are built only from the remaining 123 records.
- **v1 detection pipeline** (§4.1, App. C.1; VERIFIED): Gemma 4 31B (`google/gemma-4-31B-it`, served through DeepInfra, configurable via `COMPILE_MODEL`) runs all three stages: correction-signal detection, atomic-rule extraction, and enforcement-artifact compilation. It builds a correction record that links the feedback to "the original task request, the relevant agent action, and the corresponding workspace state."
- v1 App. C.1 gives no detector validation (VERIFIED): "We do not currently report a held-out detector precision/recall on the 142 correction-conflict records: the corpus was used as the source of all annotated rules, so a fair detector benchmark would require an additional held-out conversational corpus."
- **v2 pipeline** (§4.1, App. B.1, Table 8; VERIFIED), in five steps:
  1. Signal detection reads the current message only, "erring toward identifying a possible learning signal when uncertain".
  2. A separate interpretation step identifies "what the user rejects, what remains acceptable, and what reusable behavior the correction may imply, supported by exact quotations from the user’s message."
  3. Rule resolution checks the interpretation against the user's words and the library. If a reference is unclear, up to five exact excerpts from the session are retrieved and resolution is retried once.
  4. "Each proposed update must be supported by the user’s original words."
  5. Existing requirements are removed only when explicitly retracted.
  - Learning context is about the last 10,000 characters of the session (Table 9).
- **v2 experimental learning protocol** (§5.1, App. C.1; VERIFIED): simulated users give at most one additional correction per original benchmark question. "Agents receive full feedback, but only reusable preferences update long-term memory." In App. C.1: "When feedback combines task-specific corrections with user preferences, only the sentences expressing those preferences are used for long-term updates."

### 2.4 Rule representation and lifecycle
- An atomic rule is "a concise directive governing the agent’s future behavior, paired with an applicability condition delineating precisely when the rule should and should not trigger" (v1 §4.1, VERIFIED).
- **v1 resolver** (§4.2, App. C.4; VERIFIED) has five actions: Noop, Update, Supersede, Split, New.
  - Supersede annotates the older rule with `superseded_by:<new_id>`. An offline pass renames it with an `_archived_` prefix.
  - A forced-format line "Decision: NOOP | UPDATE existing <id> | SUPERSEDE existing <id> | NEW --- because <one-sentence reason>" is required before any write.
  - Stated limitation: wrongly archived rules need a manual edit to restore.
- **v2 resolver** (Table 8, VERIFIED) has library changes "keep, revise, replace, split, add, defer, or reject", each with supporting quotations. A library version is fixed for the whole user turn (App. B.1).
- **Deployed skill** (C4 README, VERIFIED): "Memory mutations use one SQLite transaction per complete user turn: NOOP|UPDATE|SUPERSEDE|SPLIT|NEW|NEEDS_USER|REJECT|ARCHIVE|RESTORE. Each mutation must cite short exact spans from that user turn; context cannot authorize a rule."
- **v1 worked example** (App. C.5, VERIFIED): rule F2 "CLEAN UP AFTER PROJECT" compiles into a deterministic PreToolUse-Bash hook with four regular expressions. On a match it returns `verdict: block` with exit code 2. A later "except scratch logs in /tmp" would be an Update. "actually, keep the run logs for replay" would be a Supersede.

### 2.5 Compilation into runtime enforcement
- **v1 enforcement tiers** (§4.3, VERIFIED): deterministic, semantic, and intent-level ("runtime reminders"). Each rule compiles into "an applicability check, a behavior instruction, and a verifier".
  - Hooks fire at prompt, tool-use, file-write or termination events, and a failure interrupts the event.
  - "All 47 entries in our deployed hierarchical library (Appendix C.2) carry a verify-retry enforcement marker, meaning their verifiers interrupt the corresponding hook event on failure; the semantic tier remained available as a fallback but was not required by any rule in this snapshot."
  - Library: 37 atomic, 7 refinement, 3 composite (Table 4).
- **v1 compile-time validation** (App. C.1, VERIFIED): "Each compilation pass runs a four-stage self-verify loop—JSON parse, schema check, unit test on a small set of canonical inputs, and a Phase-3 sandbox replay of the correction-conflict pair that originated the rule—and rejects outputs that fail any stage."
  - INFERENCE: this replays the originating agent violation as a negative test for the new check. That is the same idea as our "pre-correction state" negative candidate, applied to a check in a future-task setting.
- **v2 four outcomes** (§4.2, App. B.2; VERIFIED):
  1. Programmatic checks for global rules without conditions or exceptions. There are three types: required JSON fields, explicit word limit, and a field compared to a literal.
  2. LLM-based semantic checks.
  3. Guidance-only, when no reliable check validates.
  4. Inactive, when meaning is ambiguous ("neither shown to the agent nor checked").
- **v2 fidelity constraint** (§4.2, VERIFIED): "The check must preserve the meaning, scope, and exceptions of the original rule rather than change the requirement to make it easier to verify."
- **v2 validation** (§4.2, App. B.2; VERIFIED):
  - The compiler generates 3-9 validation cases covering compliance, violation and non-applicability. Each selected stage has both compliant and violating cases, and the set has at least one non-applicable case.
  - A separate reviewer gets the rule, proposed check and cases, "but not the compiler’s expected labels or rationale". "Any disagreement with the compiler’s expected labels rejects the proposal."
  - Then every case is executed through the real check. "The check is activated only if the labels agree and its execution matches the expected results on every example."
  - Up to three revision rounds are allowed.
- **v2 runtime checking** (§4.3, App. B.3; VERIFIED):
  - Stages are `pre_action`, `artifact` and `delivery`. Results are pass, fail, not_applicable, unknown and error.
  - "Insufficient evidence yields unknown, which is not treated as compliance." "Importantly, an unknown result cannot clear an existing violation of the same rule on an unchanged candidate."
  - Up to three revision requests per user input. The agent can appeal once per delivery, and an overturn does not change the stored rules.
  - The selector shows a fixed instruction "that current user requirements and submission formats take precedence over learned rules".
- **Platform hooks** (v2 Table 7, VERIFIED):
  - Claude Code: UserPromptSubmit guidance, Stop checks.
  - Codex: UserPromptSubmit, PostToolUse.
  - Copilot CLI: SessionStart, Stop.
  - The experiments used a separate experimental execution layer, not the native plugins (App. B.3).

### 2.6 Evaluation design
- **Diagnostic** (§3, both versions; VERIFIED): five conditions, No Rules, All Rules (29-rule prompt store), Mem0 (121 records, up to 5 retrieved), Relevant Rules, and Compiled Rules (47-entry library with applicability and verifier). Six models. v1 footnote: the downstream evaluation uses four model families "because it requires the most widely deployed coding-agent harnesses, Claude Code and Codex CLI". Neither version names the six models in the text (grep of both HTML versions); they appear only in Figure 2.
- **v1 end-to-end design** (§5; VERIFIED):
  - Simulated user-in-the-loop "following PersonaGym (Ma et al., 2026)". The reference entry is actually "Synthetic interaction data for scalable personalization in large language models", arXiv 2602.12394.
  - ClawArena: 62 scenario templates. Training uses 32 scenarios from four families; ID eval uses held-out rounds of those 32; OOD uses 30 scenarios from five unseen families.
  - MemoryArena: rows wrapped with a "user-in-the-loop wrapper that introduces project-level constraints and correction opportunities".
  - Frozen-state evaluation with the target preference removed from prompts.
  - Baselines: No Memory, Mem0, Hindsight, ReMe-Light.
  - Metrics: task pass, violation rate, mean corrections. The simulator "is not the final arbiter of task success; all outcomes are independently scored by benchmark-specific checkers and explicit preference overlays."
- **v2 end-to-end design** (§5.1, App. C; VERIFIED):
  - ClawArena: 8 learning and 16 test scenarios (240 and 474 original questions). MemoryArena `group_travel_planner`: 30 learning and 60 test rows (211 and 415 questions).
  - Three solvers: GPT-5.6 Luna via Codex (medium effort), GPT-5.6 Sol via Codex (low effort), Claude Haiku 4.5 via Claude Code (default). Three fixed simulated-user profiles. Methods: No Memory, Mem0, PGMem (arXiv 2608.01708), Zoro (arXiv 2604.15625), TellOnce. That is 90 test groups and 72 learning groups.
  - All auxiliary calls use "GPT-6 Luna" at low reasoning effort: learning, compilation, checking, appeal, the simulated user, preference scoring, and the baselines' memory calls (App. B.4).
  - **Preference violation rate** (§5.1, VERIFIED): "the percentage of original evaluation units (474 ClawArena rounds or 415 MemoryArena questions per user) with at least one confirmed violation of an applicable user preference in the delivered response or artifact." "Questions judged unknown or not applicable are not counted as violations" (App. C.5).
  - **The final evaluation uses an LLM preference scorer** (Table 8, "Preference scoring (evaluation)"). I found no human validation of this scorer (grep for human / agreement / kappa in v2).
  - **SWE-Together transfer experiment** (§5.4, App. C.4; VERIFIED): 109 tasks in 26 repository or family groups. Split is 60 learning / 49 test, stratified by family and ordered by original interaction time. Timestamps are available for 100/109; for the nine Hyperswitch tasks "pull-request order is used". A "general simulated user" gives task-improvement feedback. Test interaction allows up to 15 more turns (at most 16 deliveries) and 2 repairs per user turn. Results are averaged over three runs.
- **Simulator fidelity** (v1 App. A, v2 App. C.3.3; VERIFIED): 790 held-out judgments (357 correction, 433 non-correction). Precision 0.864, Recall 0.953, F1 0.906, Specificity 0.940, Rule recall 0.668. v2: "held-out interaction data from five AI researchers", and "Each metric is computed separately for each researcher and then averaged across the five researchers." v1 called the same numbers "Aggregate simulator fidelity on 790 held-out judgments". The numbers are identical; the described aggregation differs between versions.
- **Simulator profile in the released harness** (C3 `profile_data_clawarena.py`, VERIFIED): `PROFILES` contains only `user_a`, with four habits K1-K4 written in Chinese. They are mostly response-format conventions: a fixed three-line opening ("目标:/依据文件:/拿不准:"), an exclusion line before `\boxed{}` answers, "结论:/依据:" first lines in deliveries, and a language split (opening in Chinese, everything else in the task language). Each has `applies_when` / `does_not_apply_when` fields. The experiments README: "The simulated user is `user_a`. Its persona has four habits with conditions and exceptions: K1 to K4 for ClawArena and H1, H2, H3 and H6 for travel planning."
- INFERENCE: the evaluated corrections are persona formatting and workflow habits, not functional code requirements. The other two of the three profiles named in the paper were not found in the released harness.

### 2.7 Results (exact numbers, with locations)
- **Diagnostic** (§3.2, both versions): compliance under No Rules 31.6%, All Rules 55.0%, Mem0 42.5%, Relevant Rules 54.0%, Compiled Rules 70.1%. The abstract's "Mem0 still violate 57.5%" is 100 − 42.5.
- **v1 ClawArena** (abstract, §5.1-§5.3): held-out violation 100.0% → 37.6% (ID) and 100.0% → 2.0% (OOD). "Trace reaches zero observed violations on three of four models" (OOD). Memory baselines are above 50% ID, "three of four exceed 94%". Average user turns 2.00 (no memory) → 1.37 ID and 1.02 OOD, against Mem0 1.51 ID and 1.31 OOD. Wall-clock 42.5 s ID and 41.8 s OOD per round, against ReMe-Light 228 s ID and 174 s OOD.
- **v1 MemoryArena-derived**: ID violation 100.0% → 60.5% with task pass 17.3% (highest). OOD violation 97.0% and mean corrections 86.5% ("the only one below 90%").
- **v2 Table 1** (mean ± sd over three simulated users; task scores on native scales; violation %):

| Solver | Bench | Metric | No Memory | Mem0 | PGMem | Zoro | TellOnce |
|---|---|---|---|---|---|---|---|
| GPT-5.6 Luna | ClawArena | Task | 77.4±1.9 | 77.0±1.1 | 77.0±1.1 | 75.4±0.1 | 77.2±1.8 |
| | | Violation | 99.8±0.4 | 83.1±4.8 | 73.6±8.5 | 99.3±0.1 | **34.7±7.5** |
| | MemoryArena | Task | 57.5±2.6 | 57.8±1.0 | 55.6±1.1 | 57.1±2.0 | 56.3±4.1 |
| | | Violation | 56.5±6.9 | 53.6±3.2 | 36.5±10.8 | 55.4±2.3 | **13.6±2.0** |
| GPT-5.6 Sol | ClawArena | Task | 77.8±2.9 | 76.7±1.2 | 77.5±0.4 | 77.6±1.2 | 78.5±0.2 |
| | | Violation | 100.0±0.0 | 93.0±6.9 | 81.5±10.5 | 100.0±0.0 | **39.2±4.1** |
| | MemoryArena | Task | 93.3±1.1 | 92.9±0.9 | 91.4±1.8 | 91.2±0.8 | 91.7±1.9 |
| | | Violation | 56.2±0.8 | 47.5±7.6 | 15.6±1.8 | 57.8±3.9 | **12.6±6.4** |
| Claude Haiku 4.5 | ClawArena | Task | 74.0±1.6 | 72.7±1.7 | 67.7±1.1 | 72.9±0.9 | 72.9±0.9 |
| | | Violation | 98.8±0.6 | 96.1±2.3 | 88.1±10.9 | 99.0±0.3 | **68.8±5.7** |
| | MemoryArena | Task | 53.7±2.5 | 54.6±3.6 | 48.0±0.4 | 39.8±6.2 | 53.4±1.6 |
| | | Violation | 37.8±2.1 | 33.8±0.5 | 32.7±3.5 | 33.4±2.4 | **14.5±1.3** |

- I checked the stated deltas against PGMem: ClawArena 19.3 (Haiku) to 42.3 (Sol) points; MemoryArena 3.0 (Sol) to 22.9 (Luna) points. They match the table. Task scores are within about 1.6 points of the strongest baseline (§5.2).
- **v2 ablation** (Table 2; same frozen library; violation %; columns All Rules as Text / Selected Rules as Text / Before Final Repair / TellOnce):
  - Luna: ClawArena 54.6 / 49.8 / 36.8 / 34.7; MemoryArena 16.8 / 14.3 / 13.8 / 13.6.
  - Sol: ClawArena 58.7 / 55.5 / 44.1 / 39.2; MemoryArena 16.9 / 14.1 / 13.6 / 12.6.
  - Haiku: ClawArena 86.3 / 84.7 / 74.0 / 68.8; MemoryArena 18.2 / 17.2 / 16.0 / 14.5.
  - Selection helps 1.0-4.8 points. Checking plus intervention helps most on ClawArena. Final repair adds 2.1-5.2 points (ClawArena) and 0.2-1.5 (MemoryArena).
  - INFERENCE: TellOnce's learned rules shown as plain text already beat the Mem0 and PGMem memories on violation (e.g., Luna ClawArena 54.6 vs 83.1 and 73.6). So much of the gain comes from the learned representation, not runtime enforcement.
- **v2 SWE-Together** (§5.4): first-delivery quality 36.4 → 38.2 (Luna) and 37.0 → 38.6 (Sol). Final delivery 57.6 → 58.2 (Luna) and 62.8 → 68.2 (Sol). These are three runs on 49 paired test tasks. INFERENCE: the gains are small for first delivery, and no significance test is reported.

### 2.8 Component diagnostics (v2 Appendix D; VERIFIED)
- **D.1, admission and extraction** (192 controlled instructions from 24 recurring behaviors × 8 framings):
  - All 48 task-local instructions rejected; all 24 underspecified-activation instructions deferred.
  - 113/120 persistent instructions admitted (94.2%).
  - Structural decision, scope and activation correct in 175/192 (91.1%).
  - Semantic fidelity 105/120 (87.5%) by two independent semantic judges.
  - Model sensitivity: Gemma 4 31B 175/192, GPT-5.6 Luna 173/192, Claude Haiku 4.5 160/192.
- **D.2, resolution**: on 16 held-out cases from real correction logs across three users, the correct decision in 15/16 and decision plus target rule in 13/16. Library-growth stress test at 2, 47, 197 and 497 rules gives 13/16 to 15/16.
- **D.3, check compilation** on 31 correctly specified rules:
  - "Nineteen rules cannot be reliably judged from the observable runtime event; the compiler correctly declines to construct an executable check for all 19."
  - Of 12 checkable rules, 11 produce a specification and 8 pass all validation cases.
  - Probes: 176 total, 86 TP, 87 TN, 1 FP, 2 FN (98.3% agreement with expected labels).
  - Semantic runtime checker: 6 rules, 48 artifacts, 23 TP, 22 TN, 2 FP, 1 FN (93.8% balanced accuracy).
  - The paper does not say who produced the 48 artifacts' labels.
- **D.4, selection**: precision and recall 84.8%/93.3% at 47 rules, 75.2%/86.7% at 97, 74.6%/84.4% at 197, 70.2%/80.0% at 497.

### 2.9 Artifacts, licenses, versions, and README claims (C3, C4; VERIFIED)
- `TellOnce_exp` (MIT, HEAD abc78f7, 2026-10-23, "Update to the paper's final TellOnce harness (ClawArena, MemoryArena travel planning)"). It contains the harness only: "The paper's runs used tellonce v1.8.0".
  - Data pins: ClawArena HF `Haonian/ClawArena` @146bf9a952a9833fa949061aa93ec7eaa3a05ce0; MemoryArena GitHub `ZexueHe/MemoryArena` @6cd9de14b71915e39ac742a20dc33785e14b6aab.
  - Requires Codex CLI 0.153.4 and OpenAI API access for "gpt-6-luna".
  - I found no SWE-Together harness in this repo, and no release of the 19-task diagnostic or the 142 records.
- `tellonce` skill (MIT, v1.8.3, 2026-10-24).
  - Modes: `observe` (default), `enforce`, `full`. The deterministic layer "ships with **no built-in rules**".
  - Background learning sends "a redacted copy of each complete user turn to the current platform's CLI model".
- **README claims that do not appear in either paper version** (VERIFIED as README text only): "the author's own library grew to ~280 rules in its first two months of intensive use — then **new-rule creation fell by 97%**", and "**88% of rules were right on the first write**". The README headline "from **100% to 2.0%**" is the v1 OOD number, which v2's protocol does not reproduce.

### 2.10 Stated limitations (v2 "Limitations", VERIFIED)
- "Our evaluation primarily relies on simulated users to provide feedback during interaction."
- "Moreover, not every learned requirement can be checked automatically from available execution evidence. In such cases, TellOnce retains the requirement as behavioral guidance, while semantic checking may also introduce judgment errors."
- Rule-update evaluation "is primarily based on controlled component diagnostics". Compute is "not explicitly matched across methods".

### 2.11 Discrepancies and caveats noted
- v1 and v2 differ in benchmark splits (62 scenario templates vs 8/16 scenarios), solvers (four vs three), baselines (Hindsight and ReMe-Light vs PGMem and Zoro), detection model (Gemma 4 31B vs GPT-6 Luna for auxiliary roles) and headline results.
- v1 Table 1's "Aggregate" simulator fidelity and v2 Table 10's "averaged across the five researchers" report identical numbers.
- v2 cites Zoro as "ZORO: active rules for reliable vibe coding", which is the arXiv v1 title. arXiv v3 is "ZORO: Active Controls to Support Rule Following in Vibe Coding".
- The tellonce README cites `TRACE_exp`, while the v2 paper cites `TellOnce_exp`. The two READMEs are identical as fetched.

### 2.12 Relevance to TraceContract
- **Q1: No.** TellOnce turns corrections into **cross-task** rules for future tasks. It explicitly drops task-specific requirements and new task requirements (v2 §4.1; release notes 1.8.0), and it never rebuilds a task or verifier for the session in which the correction happened.
  - Partial exception (INFERENCE): the §3 diagnostic is in effect a set of 19 tasks **reconstructed from real transcripts**, with 29 human-annotated, correction-derived checks and the target preference removed from the prompt. Its purpose is to test recall of an unstated preference, not reward fidelity.
- **Q2: Partial.**
  - Measured: check-level validation against generated cases with blind reviewer labels (98.3% probe agreement), semantic-checker accuracy on 48 artifacts, simulator decision fidelity against real corrections, and rule-extraction fidelity.
  - Not measured: human validation of the final preference scorer, and false-acceptance or false-rejection of task verifiers on real candidate patches.
- **Closest TellOnce mechanisms to reuse** (INFERENCE):
  1. The meaning-, scope- and exception-preserving check constraint.
  2. Blind independent labeling of validation cases, rejecting on any disagreement.
  3. The four-valued result where `unknown` is not compliance.
  4. v1's replay of the originating correction-conflict pair as a negative test.
  5. The admission taxonomy (task request, temporary constraint, lasting rule) as a codebook seed.

---

## 3. Interactive and multi-turn coding benchmarks with (simulated) user feedback

Pattern (INFERENCE, supported item by item below): in all of these, **the verifier exists before the interaction and does not change**. Feedback reveals hidden information from a ground-truth artifact. None reconstructs a verifier from a real session or measures verifier false acceptance.

### 3.1 MINT (C6), ICLR 2024
- Setup (§2.1, VERIFIED): "Upon a proposed solution, MINT simulates users that check the solution’s correctness with ground truths. When the first attempt is wrong, the user responds “Your answer is wrong.”" Informative feedback is simulated by GPT-4. By default it is generated without the ground-truth solution ("w/o GT, default setting", App. C.1.1); a w/ GT variant exists.
- Data: tasks are repurposed from existing reasoning, coding and decision-making datasets and evaluated with "established evaluation metrics".
- Results (abstract): 20 LLMs; gains of 1-8% per turn of tool use and 2-17% with language feedback.
- Human evaluation (§3.6, App. B): "human annotators consider 91.2% of GPT-4 generated language feedback to be as helpful as, if not better than, human written feedback". Feedback was indistinguishable from human feedback "in 92% of the cases"; 113 trajectories were annotated.
- Q1: no. Q2: no (it validates feedback realism, not the verifier).

### 3.2 InterCode (C7), abstract only
- An interactive coding RL environment "with code as actions and execution feedback as observations". Environments: Bash, SQL and Python from NL2Bash, Spider and MBPP. Docker-based.
- Q1: no (execution feedback only). Q2: no.

### 3.3 ConvCodeWorld / ConvCodeBench (C8), ICLR 2025
- Setup (§3, §5.1): 9 feedback combinations of compilation feedback, execution feedback (partial or full test coverage) and verbal feedback (novice or expert, GPT-4o). Built on BigCodeBench-Full-Instruct (1,140 problems); Pass@1, MRR and Recall within n=10 turns.
- VERIFIED (§3.1.1): "Expert-level verbal feedback is produced by showing the agent’s code with the correct reference code (Wang et al., 2024), enabling a comparison and subsequent detailed feedback on required modifications." App. C.5 analyzes ground-truth code leakage.
- ConvCodeBench (abstract) has "strong Spearman's rank correlations (0.82 to 0.99)" with ConvCodeWorld.
- Human eval (App. C.3, Table 10): expert feedback rated helpful 55% (ConvCodeWorld) vs 35% (ShareGPT real users), and human-expert-like 25% vs 30%. Two evaluators.
- Q1: no. Q2: no.

### 3.4 CodeFlowBench (C9), abstract and grep
- Multi-turn "codeflow": implementing functions that reuse earlier-turn functions. Data: Codeforces (5,000+ problems) and a repository component. Turns come from AST-based subproblem decomposition, not user feedback (grep found no user-feedback mechanism).
- Q1: no. Q2: no.

### 3.5 ColBench / SWEET-RL (C10)
- VERIFIED (§3.1): "the human collaborator can be easily simulated by an LLM with access to the reference artifact to faithfully answer the uncertainties from the LLM agent."
- VERIFIED (§3.2): "The human simulator will provide a brief explanation in natural language to each clarification question based on the reference code visible only to the human simulator, but it will not write code."
- Backend tasks: 10 hidden unit tests, 0/1 reward, up to 10 rounds. Data: 10k train / 1k test Python functions, LLM-generated from DCLM excerpts; the test set was manually inspected.
- Frontend tasks: CLIP similarity to the WebSight reference; 10k train / 500 test.
- Table 2 (Backend success rate): GPT-4o 40.4%, o1-mini 30.3%, Llama-3.1-8B zero-shot 22.4%.
- Artifacts: HF `facebook/collaborative_agent_bench`; code `facebookresearch/sweet_rl` (CC-BY-NC).
- Q1: no (the requirements are the reference code). Q2: no.

### 3.6 Ambig-SWE (C11), ICLR 2026
- Setup (§2.1-§2.3): 500 SWE-bench Verified issues. A GPT-4o "summarized" (underspecified) issue goes to the agent; a GPT-4o user proxy gets the full issue plus file locations. Verification uses the standard SWE-bench tests.
- VERIFIED (§2.1): "We did not evaluate on naturally underspecified SWE-Bench examples because they lack the paired ground truth (complete specifications) necessary for causal measurement of interaction impact."
- VERIFIED (§2.2): "The goal is not to simulate real users but provide the information injection to the trajectory and analyze model behaviors."
- Results: interaction gives up to 74% improvement over non-interactive; only Claude Sonnet 4 (89%) and Sonnet 3.5 (84%) reliably distinguish under- from well-specified inputs (§1).
- Q1: no. Q2: no.
- INFERENCE: this is the mirror image of our problem. Their verifier is the complete specification; our worry is a verifier built from an incomplete one.

### 3.7 "When Benchmarks Talk" (C12), abstract and grep
- "we perturb static coding benchmarks so that the code model must interact with a simulated user to retrieve key information about the problem". 10 models, 3 datasets (APPS, LiveCodeBench, ClassEval); metric is test case accuracy.
- The simulated user's prompt (appendix): "You have access to the full question, including formatting instructions and some test cases."
- Q1: no. Q2: no.

### 3.8 LLMs Get Lost In Multi-Turn Conversation (C13)
- Sharded simulation (§3.1, §4.1): fully specified single-turn instructions (Code from HumanEval and LiveCodeBench, plus five non-code tasks) are split into shards revealed one per turn. "Taken jointly, the set of shards reflects the same information provided in the fully-specified instruction". "For each task, we reuse the metrics used in the original benchmarks."
- Results (abstract): an average performance drop of 39% across six tasks, from 200,000+ simulated conversations.
- Q1: no (the original verifier already covers every shard). Q2: no.

### 3.9 CodeIF-Bench (C14)
- Design (§3.2, §3.3):
  - Each task is a sequence of verifiable instructions, each with its own tests. Conversation Accuracy runs all tests T1..Tn at turn n.
  - "Second, we analyze the instruction forgetting phenomenon, where previously followed instructions are no longer respected in later turns."
  - The Instruction Forgetting Ratio measures previously passed tests that later fail.
- Data: 9 verifiable-instruction strategies, extracted with GPT-4o from real code-review comments and filtered by 2 experts.
  - Instructions and tests are generated by GPT-4o; "two developers ... identified over 55% of the samples requiring refinement and achieved a Cohen’s Kappa score of 0.73."
  - 124 tasks: the text says "50 tasks from MBPP ... and 74 tasks from DevEval", but Table 2 lists L-1 70, L-2 40, L-3 14. That is an internal inconsistency.
- Q1: yes, but synthetic. Later instructions are preserved as cumulative tests. Q2: no (test refinement agreement only, no FA/FR).

### 3.10 RECODE-H (C15)
- 102 tasks from research papers and repositories. Unit tests are written by Gemini-2.5-Pro, then reviewed by annotators to cover 80% of canonical code. A five-level feedback hierarchy runs from Level 0 (execution log only) to Level 4 ("the correct code snippet is explicitly provided"). Feedback is generated by o4-mini, conditioned on test outcomes and canonical code (§3.2).
- Abstract: GPT-5 recall rises from 29.4% with no feedback to 71.6% with the richest feedback (per the search summary and §1).
- Q1: no. Q2: no.

### 3.11 FronTalk (C16), CoLM 2026
- Data: 100 dialogues × 10 turns with intents and test cases generated by GPT-4o from C4-seeded real websites. The 3,676 test cases were manually refined: "removal of 66 test cases (1.7%) and the editing of 2,783 test cases (73.4%)", and validity rose from 90.1% to 94.7% on a 224-case sample (§2.2).
- Evaluation: pass rate by a web agent. The **forgetting rate** measures functionality from earlier turns that is lost in the final output. FR ranges 4.3%-44.6% across models (§3); AceCoder reduces it "to nearly zero".
- Human agreement for the evaluator (§3): "accuracy of 80.2 (Cohen’s κ of 58.9) for pass rate".
- Q1: yes, synthetic (cumulative intent tests). Q2: partial (evaluator vs human agreement).

### 3.12 Dialogue SWE-Bench (C17)
- Setup (§3.2-§3.4): SWE-bench Verified with the issue text replaced by a semi-automated vague initial query; 13% of queries needed manual modification. A persona-grounded Llama-3.3-70B user simulator knows the full issue and self-revises.
- VERIFIED (§3.4): "To evaluate this, we use the execution tests corresponding to each problem from SWE-Bench Verified Chowdhury et al. (2024)."
- Q1: no. Q2: no.

### 3.13 SWE-INTERACT (C18); see also swechat.md 5.3
- Setup: 25 tasks each from SWE-bench Pro, SWE Atlas (Refactoring) and DeepSWE (75 total). The persona is grounded in SWE-chat. The simulator "progressively reveals requirements".
- VERIFIED (§5): "Our testbed has the simulated user hold latent requirements and reveals them through persona-conditioned feedback and interactions with the agent’s workspace, while final task success is still judged by the original verifier rather than by simulator approval."
- Results (§3.1): about 50% single-turn vs about 25-27% multi-turn resolve rates. Remaining failures include "forget requirements".
- Q1: no (the original verifier). Q2: no.
- Its related work cites simulator-reliability papers (C36-C38).

### 3.14 Asuka-Bench (C19) and ICAE-Bench (C20), abstracts only
- Asuka-Bench: 50 web tasks with 784 evaluation criteria and 2,402 expected outcomes. "a User LLM turns evaluation outcomes into natural-language feedback for the next round".
- ICAE-Bench: "each task derives ambiguity from a precise real open-source repository with executable behavior". The User Agent may "reveal hidden constraints without inventing new requirements"; scoring uses standardized black-box tests.
- Both: Q1 no (the verifier is fixed by the source). Q2: not stated in the abstracts.

---

## 4. Evolving-requirement benchmarks with cumulative verifiers (closest construction-level prior art)

### 4.1 SR-Eval (C21)
- Construction (§3.1.2): multi-agent decomposition (Decomposer, Evaluator, Analyzer) of a final complex requirement into a core requirement plus 2-5 evolving turns. Totals: 443 tasks and 1,857 questions in Python and Java, at function and repository level; 4.19 turns on average (§3.2).
- **Distinctiveness validation** (§3.1.3, VERIFIED): "When current_turn>1, the tests produced in the current turn are executed against the implementation from the previous turn. If they still pass, the tests lack sufficient discriminative power."
- Evidence of effect (§5.3): removing distinctiveness validation and the evaluator makes tests easier to pass. Example: Qwen3-Coder's Python accuracy goes up by 13.32%.
- User study (§6.1): 3 developers, 80 tasks, 333 interactions; Likert means above 4.6 for code and test quality.
- Motivation quote (abstract): "Constructing such iterative benchmarks is challenging due to the lack of public interaction traces and the difficulty of creating discriminative, turn-specific test cases."
- Q1: yes, synthetic (requirements are recovered backwards "from final requirements"). Q2: partial. Discriminative power is shown indirectly through model accuracy; there are no human-labeled FA/FR rates.

### 4.2 EvoCode-Bench (C22)
- 26 engineer-authored tasks, 227 rounds, 5-15 rounds per task. Round change types: extension 198, correction 69, conflict 42; "110 rounds carry ≥ 1 correction or conflict" (Fig. 2).
- **Superseded requirements** (App. B.5, VERIFIED): "When a later round’s conflict or correction supersedes an earlier requirement, the cumulative test is updated accordingly: assertions that check the now-obsolete behavior are replaced by assertions that check the new behavior."
- Review (§3.2): "Reviewers ask whether a competent implementation that differs from the reference can pass, whether each test assertion follows from a current requirement, and whether later rounds preserve all requirements that have not been explicitly superseded." Cross-validation audits shortcut strategies (App. D.2).
- Results: SR exceeds MT@4 by 22-40 points. Mid-tier failures include "stale behavior (28.6%) from superseded requirements left in the codebase" (§4.3). Human check of the failure labels: 50/50 agreement (App. D.3).
- Q1: yes, synthetic (authored corrections and conflicts with updated cumulative tests). Q2: partial (qualitative review for alternatives and shortcuts; no FA/FR numbers).

### 4.3 FeatureLoop, "Benchmarking Coding Agents under Evolving Requirements" (C23)
- 61 human-reviewed tasks (from 123 candidates; App. C.1) in 34 repositories and 5 primary languages. Each task is grounded in "at least two complete public issues" (App. B.3.1). Two feedback types: evolution feedback (adds or clarifies requirements) and completion feedback (reports failures of stated requirements). Of 147 later requirement groups, 42 follow earlier requests and 85 need new user information (§2.4).
- **Cross-state validation** (§2.3, App. B.3.9, VERIFIED): "For every new group g∈A_i, its checks must fail on W*_{i−1} and pass on W*_i and all later checkpoints." "Selected candidates additionally use valid alternative implementations and deliberately faulty variants to check acceptance and failure detection." The Test and Reference authors work in separate workspaces with information boundaries (App. B.4). Human reviewers simulate each turn and check that the contract is "permissive of different valid implementations" (App. B.3.10).
- Results (abstract): the best model completes 72.1% of tasks with both feedback types. "only 15.4% of observed failed stages recover within two corrective revisions."
- I found **no aggregate pass or fail rates for the alternative and faulty-variant probes** (grep for alternative, faulty, variant).
- Q1: yes, synthetic (cumulative checks preserve every earlier group). Q2: partial (the construction-time probes exist, but no reported FA/FR and no held-out human labels).

### 4.4 SWE-Shift (C24), abstract only
- 120 scenarios in 12 change families, each at nine intervention positions; 17 systems evaluated. "Success requires completing the current task, preserving still-valid work, and satisfying the applicable state and evidence checks." GPT-6 Astra drops from 67.35% to 24.79% (20.34% paired success).
- Q1: yes, synthetic mid-execution updates. Q2: not stated.

### 4.5 PersonaCodeBench (C25); very close on measurement
- Construction (§2.2-§2.3): native tasks T=(I, W0, V) from Terminal-bench 3 (52), DeepSWE (64), SWE-bench-Live (45), **SWE-Together (9)** and SWE-bench Pro (61). That gives 231 pairs with 422 "evolved requirements" derived from personas; Lite has 100 pairs and 186 requirements.
  - VERIFIED: "Requirements emerge progressively, with their content, disclosure conditions, and acceptance criteria fixed before evaluation" (abstract).
  - Feasibility needs a joint solution that satisfies native and persona contracts. "targeted negative variants and semantic controls probe whether the corresponding evaluator rejects violated obligations and unsupported claims" (§2.3).
  - Contrastive screening keeps pairs where the reference agent passes native but fails persona-adapted.
- Verifiers: a completion verifier (native) and a personalization verifier (deterministic checkers plus LLM judges, GPT-6 Luna).
- **Outcome discrimination** (App. D.3, VERIFIED): "Thus, 179/874=20.5% of complete native-test passes fail the recorded persona criteria." "This is descriptive discrimination, not evidence that all 179 judgments are correct or that evolved requirements causally reduced performance." Denominator: 1,962 of 2,574 records, after excluding 612.
- **Human validation** (App. D, VERIFIED): "a blinded expert review of 148 requirement-level judgments sampled from 15,100 recoverable assessment records". Results: 71.0% agreement with the adjudicated expert reference (κ=0.473); accept/reject 77.2% (MCC 0.541); "Satisfied judgments achieve 89.2% precision and 74.5% recall". The deterministic checker matched all 133 fixture outcomes (30 valid accepted, 93 invalid rejected, 10 unresolved; App. D.2).
- Ablation (§3.5): removing personas raises Joint pass from 19% to 45%.
- Artifacts: `MatrAIx-ai/PersonaCodeBench` (MIT).
- Q1: partial. Later-disclosed requirements are preserved in a separate verifier, but they are synthetic persona obligations, not real corrections. Q2: yes, partially (expert review of requirement judgments; native-vs-joint discrimination).
- INFERENCE: the 20.5% figure is the closest published analogue of "false acceptance of an initial-only verifier". It is conditioned on contrastive screening, and it is LLM-judged.

### 4.6 SLUMP (C26), abstract only
- 20 ML papers and 371 atomic components, with interaction scripts of about 60 requests that "progressively disclose the target design". Repositories are scored with a five-level faithfulness rubric "and accompanied by an exposure audit to verify that scored components are recoverable from the visible interaction". The single-shot control is higher on 16/20 (Claude Code) and 14/20 (Codex) papers.
- Q1: yes, synthetic. Q2: partial (the exposure audit guards against scoring undisclosed requirements, which is the false-rejection side).

---

## 5. Tasks or specifications from real sessions and issue threads (requirement extraction)

### 5.1 SWE-Together (C27); new full-text facts beyond swechat.md 5.1
- Sources (Table 1): DataClaw 2,228 → 29, Pi-staging 2,397 → 23, Hyperswitch 784 → 9, SWE-chat 5,851 → 48. That is 109/11,260 = 0.97%.
- Simulator (§2.2, VERIFIED): "Real software-engineering tasks often evolve through user interventions: clarification, correction, new requirements, or requests to inspect external artifacts." The action space is no-op, question, redirect, new-requirement and check-external. Each simulator is "conditioned on a session analysis reconstructed from the original user–agent interaction (Wu et al., 2026a)". That reference is HumanLM, C40.
- Correctness (§2.3, VERIFIED): "Task correctness measures whether the agent’s final repository state satisfies the coding request, including requirements introduced during the interaction."
- §2.3.1 (VERIFIED): "Execution-only scoring can also miss requirements introduced later in the interaction, fail to exercise behavior that depends on realistic repository context, or reject valid alternative implementations." The evaluator combines deterministic verifiers with a two-phase agentic rubric judge (Phase 1 rubric fixed offline, possibly consulting the reference patch). Pass threshold τ=0.85.
- Diagnostics (§2.3.2):
  - IntentCoverage = round(0.70·I_recall + 0.30·I_precision, 2).
  - UserCorrection = N_correction + 0.2·N_nudge.
  - Six of seven cohorts score 0.70-0.72 and GPT-5.5 scores 0.68 (§3.2).
- Validation (§3.1-§3.3): the reference patch passes 73/93 (≈78%) at τ=0.85. Human Turing test: 4 annotators, 52 tasks, 156 pairs, 312 judgments; pass rate 46% (95% CI [40.5, 51.6]%).
- Limitation (§5): "The user simulator cannot interrupt the coding agent during its turns, cannot directly edit files, and relies solely on textual trajectories and tool outputs rather than visual information from the interface."
- Repo: `Togetherbench/SWE-Together` (Apache-2.0 LICENSE).
- Not found in my read: human validation of the rubric judge or gates against labeled candidate patches; FA/FR rates; any comparison of initial-only vs correction-aware verifiers.
- Q1: yes (real sessions). Q2: partial.

### 5.2 CodeAssistBench, CAB (C28), NeurIPS 2025 D&B
- Data: 3,286 GitHub issues tagged as questions, in 214 repositories and 7 languages. Docker environments are generated automatically.
- **Satisfaction conditions from the full thread** (§3.1.3, VERIFIED): "The model analyzes the full conversation, focusing on the original question and subsequent clarifications, to extract concrete conditions that would satisfy the user’s needs." The extraction prompt (App. A.4) requires conditions to be "TRANSFERABLE (solution-agnostic)", "VERIFIABLE", "EVIDENCED (grounded in user utterances)" and "NEED-FOCUSED". It feeds the comments "(chronological, at most 100)". A post-hoc check discards conditions without evidence from the thread.
- Evaluation: a simulated user (BM25-retrieved style references) and an LLM judge that grades "technical correctness", "satisfaction completeness" and "interaction quality". Docker execution success is a hard requirement where available (§3.2).
- **Human validation**:
  - §4.3.3: "Across 663 conditions from 70 randomly sampled issues, 86.3% were judged accurate but only 65.7% complete, indicating high precision with conservative recall." App. H Table 7 gives per-language recall, from 26.67% (C++) to 96.67% (C); overall 572/663 correct and 34.3% "Additional Needed".
  - Judge (§4.3.1): 310 responses with two engineers; inter-human 78.28% (κ=0.68); LLM judge 65.92% average agreement.
- Q1: yes for the evaluation criteria (later clarifications enter the satisfaction conditions). The verifier is an LLM judge, not executable tests. Q2: partial (condition accuracy and completeness, judge-human agreement; no FA/FR).
- INFERENCE: the 65.7% completeness is a direct measurement of requirement omission when converting a conversation into criteria. This is the mediator our study hypothesizes for false acceptance.

### 5.3 AfterVibe (C30)
- Data: 72 tasks from a company's internal coding-assistant sessions over a 7-day window. The funnel was 122 candidates, 81 graded, and 72 passing both graders on the landed code (88.9%; §4.1.1).
- VERIFIED (§3.1): "we treat requirements as implicit—whatever is observable from the session (the developer’s prompts, corrections, and accepted behaviors) is a sufficient expression of the requirements."
- Spec quality is measured by a regeneration test with a three-tier verifier: flexible tests, verification conditions and ground-truth alignment. Mean regeneration is 5.06/6.0, rising to 5.74 after strengthening.
- **Grader validity** (§4.7, VERIFIED): "If task A’s VCs still pass on the pre-change checkout, the VCs are not checking the task’s intended behavior." Table 4 pass rates on correct / partial / pre-change / wrong code:
  - Verification conditions: 100.0% / 47.0% / 0.0% / 1.4%.
  - Flex tests: 100.0% / 42.4% / 58.0% / 51.4%.
- No human labels on candidates. Data is not released ("no human vibe-coding trajectory dataset with execution environments is yet openly available"; only prompts are provided).
- Q1: yes (the specification includes corrections), but not ablated. Q2: partial (negative controls; no human labels).
- INFERENCE: its "pre-change" control is the parent commit, not the agent's pre-correction state.

### 5.4 RealClawBench (C29)
- 281 executable tasks from real OpenClaw sessions; max final-vs-source JSD 0.0448; best model 65.8%.
- VERIFIED (§4.2): "Second, request rewriting turns the original user message into a standalone instruction x, resolving local references and conversational ellipsis while removing private identifiers." Verifiers are deterministic programs over the final workspace and stdout. "Tasks requiring subjective or aesthetic judgment are removed."
- Scorer validation (App. F, Table 11): a full-evidence LLM auditor vs human labels on 281 cases, compared with an output-only judge:
  - Exact agreement 0.815 vs 0.317; κ 0.748 vs 0.128.
  - False-positive "done" 4.2% vs 21.0%; false-negative "done" 12.3% vs 64.9%; violation miss 11.4% vs 29.7%.
- Q1: not described (the rewrite is from "the original user message"). Q2: yes for the LLM auditor (not for corrections).
- INFERENCE: this is a published example of an initial-request-centric reconstruction, so it is a natural reference point for our initial-only condition.

### 5.5 ToM-SWE (C31)
- Stateful SWE benchmark (§4): "we begin by collecting 453 real, consented sessions between human software developers and coding agents through the OpenHands platform". From these come 15 developer profiles, paired with 500 SWE-bench Verified instances. Evaluation is standard SWE-bench tests plus a simulator satisfaction rating from 1 to 5.
- Number discrepancy: the abstract says "59.7% compared to 18.1% for OpenHands", while §1 says "57.4%" vs "13.5%".
- Q1: no (preferences enter only through simulator ratings). Q2: no.

### 5.6 SWE-bench `hints_text` (C32)
- Dataset card, VERIFIED: "hints_text: (str) - Comments made on the issue prior to the creation of the solution PR’s first commit creation date." and "problem_statement: (str) - The issue title and body."
- INFERENCE: issue-derived benchmarks have the **opposite asymmetry** to ours. The prompt is the initial issue, while the verifier comes from the merged PR, which may reflect later thread decisions. That leads to underspecification and false rejection, as audited in SWE-bench Verified (`verifier_fidelity.md` A1). In trace-derived tasks the risk runs the other way: a verifier built from the initial request omits later corrections, leading to false acceptance.

### 5.7 SpecRover (C33), nl2postcond (C34), RECOVER (C35), abstracts only
- SpecRover: iterative specification inference from the issue plus code inside an agent, and a reviewer agent that vets patches.
- nl2postcond: LLM-generated postconditions from natural-language intent, measured by "correctness and discriminative power of generated postconditions". This is a close methodological cousin for measuring FA/FR of verifiers derived from NL intent, though without conversations.
- RECOVER: requirements generation from stakeholder conversations; turn-level and conversation-level evaluation of "correctness, completeness, and actionability".
- All three: Q1 no (no later-correction handling stated). Q2: nl2postcond partial (discriminative power); the others no.

---

## 6. User simulators for coding agents and their fidelity

- SWE-Together's human Turing test: 46%, CI [40.5, 51.6] (5.1).
- TellOnce's simulator: decision F1 0.906, rule recall 0.668 vs real corrections (2.6).
- MINT feedback: 91.2% as helpful as human (3.1). ConvCodeWorld feedback: 55% vs 35% helpful (3.3). FronTalk textual simulator: about 98% fidelity per §3 (the 98% textual and 95% Gemini visual figures are from §3; details in App. C.4, not read).
- General simulator-reliability evidence (abstracts only):
  - **SimulatorArena** (C36): 909 annotated conversations. Profile-conditioned simulators "reach Spearman's ρ of 0.7".
  - **Lost in Simulation** (C37): on τ-Bench retail, "agent success rates varying up to 9 percentage points across different user LLMs", with systematic miscalibration.
  - **Mind the Sim2Real Gap** (C38): 451 participants, 165 tasks, 31 simulators. "LLM simulators are excessively cooperative, stylistically uniform, and lack realistic frustration or ambiguity, creating an "easy mode" that inflates agent success rates above the human baseline."
  - **Suh et al.** (C39): an assistant trained against a role-playing simulator was indistinguishable from the initial one (51% win rate), against 58% for a WildChat-fine-tuned simulator.
  - **HumanLM** (C40): state-aligned user simulators; 16.3% relative alignment improvement.
- Not coding: UserBench (C41) and CollabLLM (C42), which use simulated users with incrementally revealed preferences or multiturn-aware rewards.
- INFERENCE for TraceContract: replaying corrections through a simulator, as SWE-Together, SWE-INTERACT and TellOnce do, adds simulator error to verifier error. Freezing the reconstructed contract and scoring a fixed candidate set avoids this confound, and this literature supports that choice.

---

## 7. Learning from natural-language feedback and corrections (code)

- **TiCoder** (C43, C44): lightweight user feedback on LLM-generated tests "formalize[s] the user intent using generated tests" and prunes and ranks code.
  - Scale evaluation uses the reference implementation as an "idealized proxy". VERIFIED (§VII-D): "In other words, we assume that the intent of the user is precisely captured by the semantics of the (hidden) reference implementation."
  - User study (15 programmers; §VI-A): mean correctness 0.40 (no TiCoder), 0.84 (TiCoder with test outputs shown; p=0.001) and 0.64 (outputs obfuscated). Participants "were also more prone to making mistakes while providing test outputs that dealt with edge cases."
  - Average absolute pass@1 improvement within 5 interactions: 45.97% in the abstract vs 45.73% in §VII-E (inconsistent).
  - Q1: partial (user feedback becomes tests that gate code, but within one fresh task and with no reconstruction). Q2: partial (human ability to evaluate code; no verifier FA/FR).
- **ILF** (C45): imitation learning from human-written language feedback on code; CodeGen-Mono 6.1B pass@1 on MBPP +38% relative (+10% absolute). **Coffee-Gym** (C46): a dataset of human code-edit traces plus "CoffeeEval, a reward function that faithfully reflects the helpfulness of feedback by assessing the performance of the revised code in unit tests." Both: Q1 no, Q2 no for task verifiers (CoffeeEval validates feedback helpfulness via unit tests).
- **PRELUDE/CIPHER** (C47): learns latent preferences from user edits for summarization and email writing, with a GPT-4 simulated user (not coding). **MultiSessionCollab** (C48): memory of user preferences across sessions. Both are cross-session personalization in the same family as TellOnce.
- **ZORO** (C49): rules files (AGENTS.md, CLAUDE.md) become active controls during vibe coding. It enriches the plan with rules, requires the agent to "prove that each rule was followed", and "allows users to provide in-situ feedback when they are unsatisfied with a rule application to evolve the ruleset". **ContextCov** (C50): compiles instruction files into AST queries, shell shims and architectural validators; on SWE-bench Lite (300 tasks), 88.3% constraint compliance vs 67.0% (prompt-only) and 50.3% (reflection). Both: Q1 no (curated rule source, not session corrections). Q2: not stated (abstract level).

---

## 8. Empirical studies of real developer-agent sessions (base rates for corrections and steering)

- **Anthropic, "Measuring AI agent autonomy in practice"** (C51, Feb 18 2026, full page, VERIFIED).
  - Data: interactive Claude Code sessions; "n = 500k interactive Claude Code sessions" for the complexity figure.
  - Reasons humans interrupt Claude (Table 1, "based on a sample of 500k human interruptions and 500k completed turns"): "To provide missing technical context or corrections (32%)", "Claude was slow, hanging, or excessive (17%)", "They received enough help to proceed independently (7%)", "They want to take the next step themselves (e.g., manual testing, deployment, committing, etc.) (7%)", "To change requirements mid-task (5%)".
  - Reasons Claude stops: choice between approaches 35%, diagnostics 21%, "To clarify vague or incomplete requests (13%)", credentials 12%, approval 11%.
  - "New users (those with around 10 sessions) interrupt Claude in 5% of turns, while more experienced users interrupt in around 9% of turns." Full auto-approve rises from about 20% (newer users) to over 40% by 750 sessions.
  - Caveat: "Our classifications are generated by Claude." "We can only analyze traffic from a single model provider: Anthropic."
  - INFERENCE: these count mid-turn interruptions, not post-turn follow-up corrections, so they undercount corrections. SWE-chat's post-turn pushback numbers are in `swechat.md` 2.5.
- **SWE-chat** (`swechat.md`): LLM-labeled pushback after about 46% of prompts; "Mind Changer" persona in 6.7% of annotated sessions (cross-reference only).
- **Decoding Human-LLM Collaboration** (C54): 66,371 coding conversations (19,507 multi-turn) from LMSYS-Chat-1M and WildChat; 378 sampled. "roughly 75.93% of conversations in the dataset include at least one instance of non-compliance" (§5). Abstract: "Bug fixing and code refactoring pose greater challenges to LLMs' instruction following".
- **CodeChat** (C55, v2 abstract): 587,568 developer-LLM conversations from WildChat. "prompts that explicitly identify the error and request a fix are the most frequently observed" among successful syntax-error resolutions.
- **Hao et al.** (C52): 210 and 370 shared ChatGPT conversations in PRs and issues. "Multi-turn conversations account for 33.2% of the conversations shared in PRs and 36.9% in issues." Prompt roles include "unveiling initial or new tasks, iterative follow-up, and prompt refinement". **DevGPT** (C53): 29,778 prompts and responses linked to GitHub artifacts.
- **Agentic PR studies**:
  - Watanabe et al. (C56): 567 Claude Code PRs in 157 projects; 83.8% merged, 54.9% of merged PRs without further modification.
  - AIDev (C57): over 456,000 agent PRs.
  - Ehsani et al. (C58): 33k agent PRs; 600 analyzed qualitatively for rejection patterns.
  - INFERENCE: PR review comments are another real source of post-hoc corrections, but these studies do not convert them into verifiers.
- All of Section 8: Q1 not applicable, Q2 not applicable. They only provide prevalence evidence.

---

## 9. Synthesis

### 9.1 Answers per item (Q1 = later corrections preserved as requirements in a reconstructed task or verifier; Q2 = measures verifier or reward fidelity)

| Work | Source of tasks | Q1 | Q2 |
|---|---|---|---|
| TellOnce v1/v2 (C1, C2) | real single-user transcripts (diagnostic); ClawArena, MemoryArena, SWE-Together (end-to-end) | No: cross-task rules only; task-specific requirements excluded | Partial: check validation on generated cases (98.3%), semantic checker 48 artifacts, simulator fidelity; final scorer not human-validated |
| SWE-Together (C27) | real sessions (11,260 → 109) | Yes (simulator plus gates and rubric) | Partial: reference patch 73/93, Intent Coverage, Turing test; no FA/FR |
| PersonaCodeBench (C25) | 5 existing benchmarks plus synthetic persona requirements | Partial: later-disclosed synthetic requirements | Yes, partial: expert review (κ 0.473; P 89.2 / R 74.5), 20.5% native-pass-but-persona-fail |
| FeatureLoop (C23) | authored from public issues | Yes, synthetic cumulative checks | Partial: cross-state checks, alternative and faulty probes; no rates reported |
| EvoCode-Bench (C22) | engineer-authored | Yes, synthetic (corrections and conflicts update tests) | Partial: reviewer audits; no rates |
| SR-Eval (C21) | synthetic decomposition of final requirements | Yes, synthetic | Partial: distinctiveness validation, ablation |
| CodeIF-Bench (C14) | MBPP and DevEval plus GPT-4o instructions | Yes, synthetic (CA, IFR) | No |
| FronTalk (C16) | GPT-4o intents on real websites | Yes, synthetic (forgetting rate) | Partial: evaluator vs human 80.2% (κ 58.9) |
| SWE-Shift (C24), SLUMP (C26) | synthetic | Yes, synthetic | Not stated (SWE-Shift); exposure audit (SLUMP) |
| CodeAssistBench (C28) | real GitHub issue threads | Yes, for LLM-judge criteria (clarifications included) | Partial: conditions 86.3% accurate, 65.7% complete; judge 65.92% |
| AfterVibe (C30) | real internal vibe-coding sessions | Yes, implicitly (spec includes corrections) | Partial: negative controls (pre-change 0.0% VC vs 58.0% flex) |
| RealClawBench (C29) | real OpenClaw sessions | Not described (rewrites "the original user message") | Yes, for the LLM auditor (FP done 4.2%) |
| ToM-SWE (C31) | SWE-bench Verified plus profiles from 453 real sessions | No | No |
| Ambig-SWE, Dialogue SWE-Bench, SWE-INTERACT (C11, C17, C18) | SWE-bench Verified, Pro, etc. | No (original verifier) | No |
| MINT, ConvCodeWorld, ColBench, When Benchmarks Talk, RECODE-H, Lost in Conversation (C6, C8, C10, C12, C13, C15) | static benchmarks or references | No (feedback reveals fixed ground truth) | No (some validate feedback realism) |
| InterCode, CodeFlowBench (C7, C9) | static datasets | No (no user feedback) | No |
| TiCoder (C43, C44) | MBPP and HumanEval | Partial (feedback becomes tests within a fresh task) | Partial (user study of code-evaluation correctness) |
| Empirical studies (C51-C58) | real logs | not applicable | not applicable |

### 9.2 Key cross-cutting pattern (INFERENCE)
1. **Fixed-verifier interactive benchmarks.** Feedback reveals information the verifier already has. Errors in feedback cannot cause false acceptance because the verifier is the ground truth.
2. **Synthetic evolving-requirement benchmarks.** Later requirements are authored together with their checks, so preservation is guaranteed by construction. Several validate discriminativeness (fail on the previous stage) and permissiveness (valid alternatives), but against synthetic references.
3. **Real-session benchmarks** (SWE-Together, RealClawBench, AfterVibe, CAB). Here, omission of later corrections is a real risk. Only CAB measures omission (completeness 65.7%), and none measures the resulting false acceptance on a controlled candidate set against human labels.

### 9.3 The three works closest to TraceContract, and the precise differences

**1. SWE-Together (C27): HIGH overlap.** It shares four things with us: tasks reconstructed from real user-agent sessions (including SWE-chat); later-introduced requirements kept in correctness scoring ("including requirements introduced during the interaction"); an explicit argument that execution-only scoring misses later requirements and rejects valid alternatives; and a task-generation agent with an audit step.

Differences:
- (a) It never compares an initial-request-only contract to a correction-aware one on the same tasks.
- (b) Its candidates are fresh agent runs under a reactive simulator. There is no fixed, shared held-out candidate set and no use of the session's own pre-correction code state as a negative.
- (c) It has no independent human labels of candidate acceptability, so no FA/FR. Validation is the reference patch passing 73/93, simulator Intent Coverage and a Turing test.
- (d) Its verifier is a rubric judge (Phase 1 may consult the reference patch) combined with deterministic gates, not evaluated per verifier type.
- (e) It has no predefined verifier-audit procedure whose effect is measured.

**2. PersonaCodeBench (C25): HIGH overlap on the measurement, LOW on the source.** It measures the quantity closest to ours: how often the native verifier accepts outputs that violate later-disclosed requirements ("179/874=20.5%"). It also validates its requirement judgments with blinded experts (71.0%, κ=0.473; accept/reject 77.2%; Satisfied precision 89.2%, recall 74.5%) and uses negative variants and controls for checkers.

Differences:
- (a) Its requirements are **synthetic persona obligations** with acceptance criteria authored before evaluation, not corrections mined from real sessions. Nothing is reconstructed or omitted by a reconstruction method.
- (b) Its 20.5% is "descriptive discrimination" on agent runs selected by contrastive screening, scored by an LLM-judge verifier. It is not FA against human ground truth.
- (c) It has no false-rejection measurement on valid alternative implementations, and no candidate design (pre-correction states, near-misses).
- (d) It does not compare reconstruction methods (initial-only, full-session LLM reconstruction, correction-aware) or audit procedures.

**3. FeatureLoop (C23): MEDIUM-HIGH overlap on verifier-audit design.** Its construction-time verifier validation is the closest to our audit procedure and candidate types. Cumulative checks must fail on the previous-stage reference and pass on all later ones (eq. 6). "valid alternative implementations and deliberately faulty variants" probe acceptance and failure detection. Test and Reference authors are separated by information boundaries, and human reviewers check that contracts are "permissive of different valid implementations". It also distinguishes requirements that need new user information (85 of 147).

Differences:
- (a) Its tasks are authored from public issues by agents and reviewers, not reconstructed from sessions. There is no omission of real corrections to study.
- (b) The probes are construction checks on "selected candidates", and no aggregate FA/FR rates are reported.
- (c) There are no independent human acceptability labels on a held-out candidate set, and no comparison of verifier variants with and without the audit.
- (d) Its "previous stage" is a reference checkpoint built by the Reference author, not an agent's real mistaken state.

**Next closest** (one line each):
- **AfterVibe**: real sessions, a specification including corrections, negative controls with pre-change code (flex tests accept 58.0%). No human labels, no correction ablation, and pre-change is the parent commit.
- **TellOnce**: corrections compiled into checks with fidelity-preserving, blind-labeled validation, plus v1's replay of the originating conflict. Its scope is future-task preferences and it excludes task requirements.
- **CodeAssistBench**: conversation-to-criteria completeness measured at 65.7%. Its verifier is an LLM judge on Q&A issues, with no FA/FR on candidates.
- **EvoCode-Bench and SR-Eval**: superseded-requirement test updates and previous-turn distinctiveness. Both are synthetic.

---

## 10. Novelty threats (what TraceContract must not claim)
1. "Reconstructing executable tasks from real coding-agent sessions while preserving later-introduced requirements" is done by SWE-Together, which also motivates it with the same argument (§2.3.1).
2. "Execution-only or initial-request verifiers accept solutions that violate later requirements" is already quantified descriptively by PersonaCodeBench (20.5%), with an expert-validated requirement verifier, though for synthetic persona requirements.
3. "Using the pre-change or previous-stage state as a negative to test the verifier" is done by SR-Eval (distinctiveness validation), FeatureLoop (eq. 6), AfterVibe (pre-change control: 0.0% VC vs 58.0% flex) and TellOnce v1 (sandbox replay of the originating correction-conflict pair).
4. "Valid-alternative probes to test against false rejection" appear in FeatureLoop (App. B.3.9) and the EvoCode-Bench reviewer protocol, and as an argument in SWE-Together.
5. "Converting user corrections into executable checks with an independent validation step" is done by TellOnce v2 (blind reviewer labels, all cases must match).
6. "Measuring requirement omission when extracting criteria from conversations" is done by CodeAssistBench (65.7% complete).
7. "Measuring LLM-verifier false positives against human labels on session-derived tasks" is done by RealClawBench App. F (FP done 4.2% vs 21.0%).
8. Multi-turn forgetting and regression of earlier requirements is well documented: CodeIF-Bench IFR, FronTalk forgetting rate, EvoCode-Bench stale superseded behavior 28.6%, SWE-INTERACT "forget requirements", SLUMP.

**What still appears open** (INFERENCE; to be re-checked before submission):
- (i) A controlled ablation of contract source (initial-only vs correction-aware) crossed with verifier audit (none vs predefined) on the **same real-session tasks**.
- (ii) A **shared, fixed held-out candidate set** per task combining three kinds of candidate. First, the agent's **actual pre-correction code state** from the session. Second, constructed near-misses. Third, valid alternative implementations.
- (iii) **Independent human adjudication** of every candidate, giving FA and FR with confidence intervals per verifier. Verifier types are existing repository tests, generated tests with and without audit, and a competent full-session LLM reconstruction baseline.
- (iv) A focus on corrections that change **this task's** requirements, which TellOnce deliberately ignores.

---

## 11. Design implications for TraceContract (INFERENCE)
1. **Position the contribution as measurement of reward fidelity**, not task reconstruction or multi-turn replay. Cite SWE-Together and PersonaCodeBench as the nearest construction and measurement precedents, and FeatureLoop, SR-Eval and EvoCode-Bench as verifier-construction precedents.
2. **Define the "predefined verifier-audit procedure" by combining known checks**, and state that our novelty is measuring their effect against human labels. The known checks are:
   - FeatureLoop and SR-Eval cross-state checks: new-requirement tests must fail on the pre-correction state and pass on the reference.
   - Valid-alternative acceptance.
   - Targeted faulty variants.
   - TellOnce v2's blind relabeling, where any disagreement means rejection.
   - EvoCode-Bench's assertion-to-requirement tracing and shortcut audit.
3. **Use TellOnce v2's admission taxonomy as a codebook seed, inverted.** "Task request" and "temporary constraint" corrections are in scope; durable cross-task preferences form a separate stratum or are excluded. Add EvoCode-Bench's extension/correction/conflict labels and SWE-chat's Expert Nitpicker vs Mind Changer split, so FA can be reported by correction type.
4. **Adopt TellOnce's fidelity rules for contract compilation**: preserve meaning, scope and exceptions, and never simplify a requirement to make it checkable. Use a four-valued check result where `unknown` counts as not accepted. Record "inactive or guidance-only" requirements explicitly, because they are a source of false acceptance.
5. **Measure contract completeness as a mediator.** Use CAB-style human completeness (they found 65.7%) and SWE-Together-style intent recall and precision of the reconstructed contract against the human-annotated requirement list. Then relate omissions to FA.
6. **Pre-correction negatives need care.** The agent's pre-correction state may fail for reasons unrelated to the correction. Human labels should record why each candidate is unacceptable (violates the correction, violates the original request, or both), so FA can be attributed to omitted corrections. AfterVibe's parent-commit control and SR-Eval's synthetic previous-turn reference are weaker substitutes we can cite as contrasts.
7. **Avoid simulator replay in the core measurement.** The sim2real literature (C36-C39) and SWE-Together's Intent Coverage of about 0.7 show that simulators drop about 30% of original intents. Freeze contracts and score fixed candidates instead.
8. **Report LLM-judge verifiers separately.** PersonaCodeBench's expert agreement (κ 0.473) and CAB's judge agreement (65.92%) suggest that correction-aware LLM-judge contracts can trade FA for FR. Our 2x2 should report both rates.
9. **For the initial-only baseline**, RealClawBench's rewrite of "the original user message" into a standalone instruction is a published, concrete recipe. SecureForge's full-session prompt (`swechat.md` 5.2) is a recipe for the competent full-session reconstruction baseline.
10. **Contrast with issue-derived benchmarks** (SWE-bench `hints_text`). There, later thread content tends to live in the verifier but not the prompt, which leads to false rejection. This frames why trace-derived tasks have the opposite failure mode.

---

## 12. Open questions
- TellOnce: are the 19 diagnostic tasks, the 29 checks or the 142 correction-conflict records released? I did not find them in either repo. Are the other two simulated-user profiles released (only `user_a` is in the harness)? Who labeled the 48 artifacts in D.3? Is the GPT-6 Luna preference scorer validated against humans?
- TellOnce v1 vs v2: why were the ClawArena splits and solvers changed? The v1 headline (2.0% OOD) is still the README's lead claim.
- SWE-Together: is there any human validation of the Phase 2 rubric judge, or per-goal labels, that could be reused as human ground truth for later-introduced requirements?
- PersonaCodeBench: what are the precision and recall of Unmet (rejection) judgments? The 89.2/74.5 figures are for Satisfied. How does the 20.5% change under expert labels?
- FeatureLoop: are the alternative and faulty-variant probe outcomes released, and how many candidates received probes?
- CAB: does condition completeness differ for conditions introduced in later comments compared with the original question? Not reported.
- Prevalence: in real sessions, what fraction of corrections change task requirements, as opposed to reporting bugs or context? The two estimates in hand are Anthropic's "To change requirements mid-task (5%)" of interruptions and SWE-chat's Mind Changer 6.7% of sessions. Neither is a human-coded estimate of requirement-changing post-turn corrections.

---

## 13. Not accessed and limitations of these notes
- github.com web pages are blocked by the proxy. I used shallow clones (TellOnce_exp, tellonce) and raw.githubusercontent.com files (READMEs, LICENSE first lines). `gh api` for these repos returned HTTP 403 ("not enabled for this session"), so repo creation dates and stars were not retrieved.
- Figures (bar values per model) in TellOnce v1 Figures 2 and 4-6 were not extracted; only numbers stated in the text are recorded.
- Abstract only: InterCode, Asuka-Bench, ICAE-Bench, SWE-Shift, SLUMP, SpecRover, nl2postcond, RECOVER, SimulatorArena, Lost in Simulation, Mind the Sim2Real Gap, Suh et al., HumanLM, UserBench, CollabLLM, ILF, Coffee-Gym, PRELUDE/CIPHER, MultiSessionCollab, ZORO, ContextCov, Hao et al., DevGPT, CodeChat, Watanabe et al., AIDev, Ehsani et al.
- Venues taken from arXiv comments or journal-ref fields only. "When Benchmarks Talk" in Findings of ACL 2025 comes from web search results and was not verified on the ACL Anthology.
- A "SpecBench / Buddy" PDF on a personal site appeared in search results. I could not verify it on arXiv and did not include it.
- SWE-chat itself was not re-read; I rely on `swechat.md`. The PGMem baseline (arXiv 2608.01708) and the ClawArena and MemoryArena benchmark papers were not read.
- No experiments were run. All "INFERENCE" items are my judgments.
