# Cluster notes: (A) TRACE disambiguation and failure-driven training; (B) alternative agent-trace data sources

- Access date for every source below: **2026-11-13 (UTC)**. Publication or version dates are recorded separately in the source tables.
- Labels: **VERIFIED** means the source states it. Every quoted string in this file was checked by whitespace-normalized exact match against the downloaded copy, with one stated exception: the OpenHands docs summary in §7.1. Two passes, 78/78 matched, scripts `<scratchpad>/tools/verify_quotes_td.py` and `verify_quotes_td2.py`. Absence claims (for example "TRACE does not cite EnvGen …") were checked by case-insensitive grep of the full text. **INFERENCE** marks my own reading, estimate or judgment.
- Local copies are untrusted data and are not part of the repo. They live under `<scratchpad>/dl/training_datasets/`, in the subfolders `trace/`, `arxiv/`, `hf/` (API JSON and cards), `hf/traj2envs/`, `repos/donate-trace`, `repos/traj2envs`, `pi/`, `devgpt/`, `dataclaw/` and `misc/`. Here `<scratchpad>` = `/tmp/claude-0/-home-user-trace-contract/3951c995-db7e-5b4e-a703-97e326bb42c5/scratchpad`.
- What was read, by rule:
  - **Dataset content: none.** For every dataset I read only the card (README), the HF API metadata, the datasets-server `/info` and `/statistics` aggregates, file trees and the HF commit/discussion listings. No session or trajectory file was opened.
  - **Three exceptions, all metadata-sized.** For `harness-hub/traj2envs-rl` I read `sources.json` (30.6 KB), `registry.json` (32.6 KB), `images.txt` and one `task.toml`. These are provenance and config files, not trajectories. For the pi session-format documentation I downloaded the npm tarball of `@mariozechner/pi-coding-agent` 0.73.1 (4.6 MB) and extracted only `docs/session-format.md` and `docs/sessions.md`.
  - **Code: two shallow clones.** `trace-commons-ai/donate-trace` and `huggingface/traj2envs` were cloned (read-only), and only their docs and source were read. Nothing was installed or executed from them.
- No git command was run inside `/home/user/trace-contract`. This step only created this notes file.
- Related cluster notes, cited where relevant and not repeated: `swechat.md` (SWE-chat, SWE-Together, SecureForge), `corrections.md` (TellOnce / TRACE-v1), `env_synthesis.md` (SWE task synthesis, including a short TRACE entry) and `trace2eval.md`.

---

## 0. Bottom line (short)

1. **ScalingIntelligence/TRACE is about training, not reward fidelity.**
   - **What it is.** TRACE (Kang, Suresh, Saad-Falcon, Mirhoseini; arXiv 2604.05336; v1 2026-04-07, v2 2026-07-02) mines capability deficits by contrasting successful and failed rollouts. It generates one synthetic environment per deficit, trains one LoRA per environment with GRPO, and composes the LoRAs with a token-level MoE gate.
   - **Verification.** Its only verifier checks are self-tests and difficulty calibration:
     - target test fails before the oracle and passes after it;
     - 8 or more regression guards pass;
     - smoke pass rate ≤ 0.5.
     It has no false-acceptance or false-rejection measurement, no human labels and no user corrections. Its SWE prompt asserts "No reward hacking, no LLM judge".
   - **Reward design.** In the released SWE reward, an applied single-edit patch that leaves the bug in place still scores **0.6** (INFERENCE from code, §2.4).
   - **Disclosed vs inspected.** The repo openly says that Phase 5 training is a stub and that its helper files are missing. My code reading found further discrepancies, and the repo, paper and model card do not reconcile them (§2.7):
     - the paper says capability mining used a disjoint SWE-smith split, but the released scripts and LoRA card mine SWE-bench Verified failures;
     - the paper's evaluation settings differ from the released config;
     - one released eval script scores "pass" as Jaccard ≥ 0.95 against the gold patch instead of running tests;
     - three different Qwen3.6 baselines appear (52.8% implied by the prompt's counts / 58.2% model card / 68.0% paper).
2. **Name collisions are real. Disambiguate in every citation.**
   - There are at least six distinct 2025–2026 "TRACE" acronyms in agents, RL and code, plus several older TRACE works (§3). Two of the new ones are directly adjacent to us:
     - **TRACE = Truncated Reasoning AUC Evaluation** (implicit reward-hacking detection, ICLR 2026 Oral per arXiv comments);
     - **TRACE = Test-time Rule Acquisition and Compiled Enforcement**, which compiles user corrections into runtime checks. It is arXiv 2606.13174 v1, renamed **TellOnce** in v2.
   - Even the ScalingIntelligence LoRA card expands TRACE differently from its own paper.
   - **Our working name "TraceContract" collides with an existing published tool**: *TraceContract: A Scala DSL for Trace Analysis* (Barringer & Havelund, FM 2011, LNCS, pp. 57–72, DOI 10.1007/978-3-642-21437-0_7; Crossref-verified).
3. **Failure-driven / capability-targeted environment generation is a crowded, established line.**
   - The prior work predates TRACE: EnvGen 2024, WebRL 2024, LLMs-as-Instructors 2024, DataEnvGym 2024, TDG 2023, AutoDetect 2024 and SwS 2025.
   - Contemporaneous work: SENTINEL, Agent-World, Socratic-SWE, Environment Evolution, Self-play SWE-RL and BugPilot (§4).
   - None of these measures whether the generated verifiers reward what a *user* wanted.
4. **New, high-relevance neighbour: `huggingface/traj2envs`** (Apache-2.0, HEAD 2026-11-05, §6).
   - It converts agent trajectories (ATIF) into Harbor tasks by replaying file states.
   - An LLM writes hidden tests.
   - A fixed **trial matrix** of negatives must score 0: do nothing, tamper with the check, stub, empty workspace, delete project. Tests must also reach a **mutant kill rate** of at least 0.5–0.6.
   - Its `extend` family starts from the project "at the end of request k" and implements "request k+1". This is structurally our *pre-correction state*.
   - Its `build` family uses only the first request.
   - The published suite (`harness-hub/traj2envs-rl`, 270 tasks) is built almost entirely from **distillation traces with generated prompts** (242/267 from `TeichAI/Ox-Alpha-Pi-Traces`). It has no human labels and no FA/FR measurement.
5. **Trace Commons** (`trace-commons/agent-traces`) is small and has clean intent, but its rights rest on one certification.
   - **Content and terms:**
     - 30 merged sessions (28 Claude Code, 1 Cursor, 1 opencode), last data change 2026-06-18, 8 open PRs unmerged;
     - CC-BY-4.0 for the *compilation only*;
     - raw native session files, scrubbed in place.
   - **Rights to embedded material** rest on the **contributor's certification**. The card says maintainers "do not and cannot verify the provenance or license of everything inside every trace", and reusers must check the licenses of contained code.
   - **No commit or remote metadata is added.** Native Claude Code fields (`cwd`, `gitBranch`) survive with the username scrubbed.
   - **Base states are not recorded.**
6. **Top 3 alternatives to SWE-chat for TraceContract** (§8):
   1. **AIDev-pop (`hao-li/AIDev` v5)**:
      - agent-authored PRs with human review comments that carry `commit_id` / `original_commit_id` (exact pre-correction states) and follow-up commits;
      - 361,296 PRs and 291,248 inline review comments;
      - CC-BY-4.0 compilation; repository content keeps its own licenses.
   2. **pi-share-hf per-project session datasets** (`badlogicgames/pi-mono`, `thomasmustier/*`, aggregated in `MaxDevv/real-pi-coding-agent-traces-sessions`, 1,291 sessions):
      - real chat corrections on named public repos, with tree-structured branches;
      - the base commit must be inferred from timestamps;
      - licenses vary;
      - SWE-Together already used about 2,397 "Pi-staging" sessions to build 23 tasks.
   3. **Trace Commons**: the cleanest provenance among chat-session datasets, but pilot-scale only.

   Runner-ups:
   - **DataClaw datasets.** They are larger and SWE-Together used them (2,228 sessions → 29 tasks). But they have no repo URL or commit and no open-source-only rule, and the tool calls itself a "performance art project" aimed at provider anti-distillation policies.
   - **OpenHands feedback** (275 sessions, MIT, 2024).

---

## 1. Sources

### 1.1 Cluster A (TRACE, disambiguation, failure-driven training)

| # | Source | URL | Version / publication date | Full text read |
|---|---|---|---|---|
| A1 | TRACE paper, abs page | https://arxiv.org/abs/2604.05336 | v1 Tue 7 Apr 2026 02:22:44 UTC (1,102 KB); **v2 Thu 2 Jul 2026 22:12:42 UTC (5,402 KB)**; cs.AI; comments: none | yes (abstract) |
| A2 | TRACE v2 full text (HTML) | https://arxiv.org/html/2604.05336 (served v2) | v2 (2 Jul 2026); page says "License: CC BY 4.0" | **yes, all sections and appendices A–K** |
| A3 | TRACE v1 abstract | https://arxiv.org/abs/2604.05336v1 | v1 (7 Apr 2026) | abstract only |
| A4 | TRACE blog | https://scalingintelligence.stanford.edu/blogs/trace/ | undated (corresponds to v1 content) | WebFetch summary only |
| A5 | TRACE code (local clone) | `/home/user/ScalingIntelligence/TRACE` (github.com/ScalingIntelligence/TRACE) | `main@d2db230` (2026-07-12, "Update README.md"); MIT, "Copyright (c) 2026 Scaling Intelligence Lab" | yes: README, prompts (general, swebench, tau-bench excerpts), configs, `pipeline/*`, SWE reference-run scripts, game class, `moe_gate/README.md`, train headers |
| A6 | TRACE LoRA model card | https://huggingface.co/ScalingIntelligence/qwen3.6-trace-semantic-logic-precision-v1 | created 2026-06-10T11:38:11Z, sha `bd472a99…`; tag `license:apache-2.0`; subfolders `iter_30/50/100/130` | yes (card) |
| A7 | Other TRACE-named papers (arXiv abs pages) | see §3 | see §3 | abstracts only |
| A8 | TellOnce / TRACE-v1 HTML v2 | https://arxiv.org/html/2606.13174v2 | v2 25 Oct 2026 | targeted (§3.1, §4.2, App. A.1, D.3); full analysis in `corrections.md` |
| A9 | TraceContract (FM 2011) Crossref record | https://api.crossref.org/works/10.1007/978-3-642-21437-0_7 | 2011 | metadata only (dblp blocked by bot wall) |
| A10 | Failure-driven survey papers (arXiv abs pages) | see §4 | see §4 | abstracts only |

### 1.2 Cluster B (datasets and tools)

| # | Source | URL | Version / date | Read |
|---|---|---|---|---|
| B1 | Trace Commons card + API | https://huggingface.co/datasets/trace-commons/agent-traces | sha `112ebd4d03ce852b00e935d523107c3d0c9a65bf`; created 2026-06-11T18:57:20Z; lastModified 2026-06-18T06:23:00Z; README sha256 `0fa43995…e036e7f` | card, API, `/info`, `/statistics`, file tree, 49 commits, 49 discussions |
| B2 | Trace Commons website | https://trace-commons-web.hf.space/ | undated | text only |
| B3 | `donate-trace` skill (clone) | https://github.com/trace-commons-ai/donate-trace | HEAD `5eb9bcd1` (2026-06-16, "Shift publishability burden to the contributor (inform, don't gatekeep)"); **no LICENSE file** | SKILL.md, references/*, scrub.py header/grep |
| B4 | traj2envs (clone) | https://github.com/huggingface/traj2envs | HEAD `a09204ed` (2026-11-05, "add license"); Apache-2.0; pyproject v0.1.0 | README, docs/how-envs-are-built.md, families/extend.py (head), mutants.py, gate.py |
| B5 | traj2envs-rl suite | https://huggingface.co/datasets/harness-hub/traj2envs-rl | sha `191a751b…`; created/modified 2026-11-06; `license: other` | card, `/info`, `/statistics`, sources.json, registry.json, images.txt, one task.toml |
| B6 | AIDev card + schema | https://huggingface.co/datasets/hao-li/AIDev | v5 ("AIDev-7.6M, cutoff date of March 31, 2026"); lastModified 2026-10-21; CC-BY-4.0 | card, `/info` |
| B7 | AIDev papers | https://arxiv.org/abs/2507.15003 (20 Jul 2025); https://arxiv.org/abs/2602.09185 (9 Feb 2026) | as dated | 2602.09185 HTML (targeted); 2507.15003 abstract |
| B8 | pi-share-hf README | https://raw.githubusercontent.com/badlogic/pi-share-hf/main/README.md | undated (fetched main) | yes |
| B9 | pi session format docs (npm) | https://registry.npmjs.org/@mariozechner/pi-coding-agent/-/pi-coding-agent-0.73.1.tgz | v0.73.1 ("latest"); npm license MIT; repo `badlogic/pi-mono` | `docs/session-format.md` (grep), `docs/sessions.md` (not read in full) |
| B10 | pi datasets | `badlogicgames/pi-mono`, `thomasmustier/pi-mono-sessions`, `thomasmustier/pi-for-excel-sessions`, `woxQAQ/pi-web`, `aaaaliou/pi-synthetic`, `julien-c/pi-sessions`, `MaxDevv/real-pi-coding-agent-traces-sessions` | see §7 | cards + API |
| B11 | DataClaw README | https://raw.githubusercontent.com/banodoco/dataclaw/main/README.md | undated (main); MIT | yes |
| B12 | DataClaw datasets | `peteromallet/dataclaw-peteromallet`, `misterkerns/my-personal-claude-code-data`, `alexshengzhili/dataclaw-harbor-candidates` | see §7 | cards + API |
| B13 | OpenHands feedback card | https://huggingface.co/datasets/OpenHands/openhands-feedback | created 2024-12-06; modified 2024-12-14; MIT | card + API |
| B14 | OpenHands feedback docs | https://docs.openhands.dev/modules/usage/feedback (redirect from docs.all-hands.dev) | undated | WebFetch summary |
| B15 | DevGPT | https://arxiv.org/abs/2309.03914 (v2 14 Feb 2024; MSR 2024 Mining Challenge); README https://raw.githubusercontent.com/NAIST-SE/DevGPT/main/README.md; Zenodo https://zenodo.org/api/records/10086809 | Zenodo publication_date 2023-11-09; license cc-by-4.0; `DevGPT.zip` 681,551,967 bytes | abstract, README, Zenodo metadata |
| B16 | Synthetic trajectory datasets | `nebius/SWE-agent-trajectories`, `nebius/SWE-rebench-openhands-trajectories`, `SWE-Gym/OpenHands-Sampled-Trajectories`, `SWE-Gym/OpenHands-SFT-Trajectories`, `SWE-bench/SWE-smith-trajectories`, `R2E-Gym/R2EGym-SFT-Trajectories`, `nvidia/SWE-Zero-openhands-trajectories`, `nvidia/SWE-Hero-openhands-trajectories`, `neulab/agent-data-collection`, `open-thoughts/AgentTrove` | see §7 | cards + API |
| B17 | Other session-like datasets | `crispwisp/wisp-claude-code-sessions`, `Mike0021/codex-sessions`, `cfahlgren1/codex-sessions`, `cfahlgren1/agent-sessions-list`, `nlile/misc-merged-claude-code-traces-v1`, `lewtun/ml-intern-sessions`, `archit11/claude_traces_hs`, `armand0e/claude-fable-5-claude-code`, `TeichAI/Ox-Alpha-Pi-Traces`, `TeichAI/DeepSeek-v4-Pro-Agent`, `netpreme/coding_agent_traces`, `thoughtworks/agentic-coding-trajectories`, `mondk/agentic-coding-traces`, `PotatoHD/agent-coding-traces-public` | see §7 | cards + API |
| B18 | Human-AI conversation datasets | `allenai/WildChat-4.8M`, `allenai/WildChat-1M`, `lmsys/lmsys-chat-1m` (gated; README 401), `DJRHails/sharetrawl` (gated manual; README 401), `Suzhen/SWE-Review-Chat`, `copilot-arena/editbench` | see §7 | cards/API metadata |
| B19 | SWE-Together v1 HTML | https://arxiv.org/html/2606.29957v1 | v1 29 Jun 2026 | targeted (§2.1, Table 1, references); full analysis in `swechat.md` §5.1 |
| B20 | HF tag counts | `https://huggingface.co/api/datasets?filter=<tag>&limit=1000` | as of access | counts only |

---

## 2. (A) ScalingIntelligence/TRACE in detail

### 2.1 Bibliographic facts and naming (VERIFIED)
- **Title and authors.** Title (arXiv): "TRACE: Capability-Targeted Agentic Training". Authors: Hangoo Kang, Tarun Suresh, Jon Saad-Falcon, Azalia Mirhoseini. Kang and Suresh are equal contribution. Affiliation: Stanford University.
- **Acronym, three expansions.**
  - Paper and README: "Turning Recurrent Agent failures into Capability-targeted training Environments".
  - The released HF LoRA card expands it differently: "(Test-time Reinforcement Learning Adaptation via Capability Environments)".
  - The README citation key is `kang2026tracecapabilitytargetedagentictraining`.
- **Versions.**
  - **v1 (7 Apr 2026).** τ²-bench and ToolSandbox only. Abstract claims: +14.1 points on τ²-bench and "+7 perfect scores on ToolSandbox"; "+7.4 points and +4 perfect scores" over the strongest baseline; "+9.2 and +7.4 points" over GRPO and GEPA at equal rollouts; "routing to the relevant adapter at inference".
  - **v2 (2 Jul 2026).** Adds SWE-bench Verified, the MoE composition and the Qwen3.6-27B backbone.
  - The blog page matches v1: it has no SWE-bench and reports a 47.0% τ²-bench pass rate at 5,120 rollouts (WebFetch summary).
- **v2 abstract (VERIFIED, HTML):** "TRACE contrasts successful and failed trajectories to automatically identify lacking capabilities, synthesizes a targeted training environment for each that rewards whether the capability was exercised, trains a LoRA adapter via RL on each synthetic environment, and then trains a mixture-of-experts (MoE) model over the capability adapters."

### 2.2 Failure analysis (what is mined, and from what)

**Paper (§3.3, VERIFIED):**
- **Discovery.** An LLM analysis agent induces a fixed dictionary of candidate capabilities from successful and failed trajectories.
- **Labeling.** Every (trajectory, capability) pair is labeled `NA` / `PRESENT` / `LACKING`.
- **Statistics.**
  - ER⁺(c) and ER⁻(c) are the rates of LACKING among applicable success and failure trajectories.
  - Contrastive gap Δ(c) = ER⁻ − ER⁺.
  - Coverage Cov(c) is the fraction of all failures labeled LACKING.
  - Keep c if Δ ≥ δ = 0.20 and Cov ≥ ρ = 0.10.
  - Labeling is repeated, with a fixed dictionary, across runs. Code default: K = 8 of N = 10 runs (`pipeline/aggregate_capabilities.py`).
- **Cost.** "one analysis pass takes approximately 5 minutes".
- Quote (§3.3): "This contrastive criterion is more robust than analyzing failures alone: it filters out capabilities with uniformly low success rates, which often reflect task ambiguity or annotation noise rather than a trainable deficit, and it excludes capabilities that occasionally fail but do not meaningfully distinguish successful from unsuccessful trajectories."
- **Results (§4.3).** On τ²-Bench, "structured data reasoning, multi-step task completion, and precondition verification are recovered in all 10 runs, while tool-calling precision appears in 8 of 10."

**Released SWE reference code (`swebench/qwen3.6_self_trace/phase2_capability_mining.py`, VERIFIED by reading code):**
- **A different, non-contrastive 3-stage pipeline:**
  1. free-form 1–2 sentence root cause per **unresolved** instance, written by comparing the model patch with the **gold patch**;
  2. clustering into 4–6 categories;
  3. single-label re-classification with `guided_choice`.
- It loads `princeton-nlp/SWE-bench_Verified` split `test`.
- Resolved trajectories are not used in this script, so there is no Δ.

**SWE prompt (`prompts/swebench/capability_selection.md`, VERIFIED):**
- It lists the reference categories with their coverage of unresolved instances:

  | Category | Coverage |
  |---|---|
  | `semantic-logic-precision` | 61.0% |
  | `deep-call-graph-traversal` | 16.3% |
  | `diff-context-precision` | 8.1% |
  | `multi-site-consistency` | 8.1% |
  | `structural-refactor-awareness` | 6.5% |

- It gives the baseline counts "264 resolved, 123 unresolved, 73 empty patches, 13 grader errors".
- INFERENCE: the counts sum to 473. 264/500 = 52.8%.

### 2.3 How targeted synthetic environments are generated (VERIFIED)

**Tool-use variant (τ² / ToolSandbox; paper §3.3, App. E, App. K; `prompts/general/environment_generation.md`):**
- **Generator.** An LLM "generation agent" writes a Python `GameEnv` (`reset(seed)`, `step`, `observe`, `legal_actions`) whose seeded generator builds:
  - synthetic user profiles and DB records;
  - a ground-truth solution;
  - an LLM user simulator.
- **Interface.** The target environment's tool schemas, state and policy constraints are preserved.
- **Reward example (structured data reasoning, App. K.1):**
  - DB-state hash comparison against a replay of the gold action;
  - a communication check that the required values appear in agent messages;
  - 1.0 for both, **0.3 for the correct DB state only**, 0 otherwise.
  - Quote (§3.3): "The reward is computed by comparing the final database state against the ground truth using hash-based consistency checks and by verifying that the agent communicates the correct final result."
- **Reward-design advice (App. E):**
  - multi-level rewards with a multiplicative core plus an additive floor;
  - target a base success of about 30–60%;
  - reward std above 0.2;
  - more than 60% of groups informative.
- **Calibration and audit.**
  - Calibration (`pipeline/calibrate_environment.py`) checks the reward distribution and group variance.
  - A "transfer sanity check" asks the agent to read 3–5 successful rollouts. Quote: "Is the model exercising the target capability, or is it succeeding via some shortcut the synthetic env accidentally allows?"
  - INFERENCE: this is an informal, unstructured verifier audit by the same agent that built the environment. There are no labels or rates.

**SWE-bench variant (`prompts/swebench/environment_generation.md`, phase 3/4 scripts):**
- **Scenario contents:**
  - a stdlib-only 300–600 LOC module;
  - 10+ pytest tests;
  - a `target_test`, an oracle `SEARCH/REPLACE` and a `pr_description` ("symptom only; no fix hint");
  - a `naive_fix_description` ("describes the WRONG fix a shallow solver would attempt");
  - a `hint_body`.
- **Leakage rule.** Library identifiers are banned (django, sympy, …).
- **Self-test:**
  - the target test fails before the fix;
  - 8 or more other tests pass (phase 4 code: at least 7);
  - the oracle applies verbatim;
  - after the oracle the target passes and no pre-passing test breaks.
- **Smoke and mutation.** N = 10 base-model rollouts at T = 1.0. Accept if the pass rate is ≤ 0.5. Otherwise apply up to 5 mutation rounds that keep the bug and disguise the surface code (strategies A call-graph extension, B decoy/misdirection, C class-hierarchy wrap).
- **Budget.** 20 candidates per invocation, target 10 accepted per capability, at most 60 attempts.
- Quote (SWE prompt, §"Three ways"): "No reward hacking, no LLM judge — the test either passes or it doesn't."

### 2.4 Reward actually used in released SWE training code (VERIFIED code; INFERENCE noted)

**What the code states (VERIFIED):**
- `capability_semantic_logic_precision_game.py` docstring: "Reward = 0.4*target_passes + 0.4*no_regression + 0.1*minimal_edit + 0.1*format_fidelity".
- Reward is 0 if the edit fails to apply.
- `minimal_edit = 1/n_edits`.
- `no_regression` is the fraction of pre-passing tests that still pass.

**What follows from the formula (INFERENCE):**
- **A parseable, applicable one-block edit that does not fix the bug and breaks nothing earns 0.6.**
- A correct fix split across 2 blocks earns 0.95. So the reward ranks "touch nothing important" above zero and penalizes multi-site fixes. That is a concrete instance of partial-credit reward misalignment that our verifier audit should measure (reward given to do-nothing or near-miss patches).

**Hint fallback (VERIFIED code; INFERENCE about the effect):**
- `reset()` uses `hint_body = scenario.hint_body or scenario.naive_fix_description`.
- It appends this as "expert guidance" for a fraction `TRACE_SLP_HINT_RATIO` (default 0.40) of seeds.
- INFERENCE: when `hint_body` is empty, the *wrong-fix* description would be shown as guidance. The template itself lives in a missing file (`capability_regression_safe_edit_game.py`), so this is unverified.

### 2.5 Training adapters and composition (VERIFIED)

**Per-capability LoRA:**
- One LoRA per capability, trained with GRPO with the base frozen (paper §3.4, App. A).
- Groups whose rollouts all get the same reward are discarded. Quote (App. A): "Groups in which all K rollouts receive identical rewards are discarded, since they provide no learning signal."
- Hyperparameters (§4.1): AdamW lr 1e-5; at most 40 iterations per capability; rollout temperature 1.0; 4–8 A100-80GB GPUs.
- Size (App. D): each LoRA is about 1.6B parameters (5.3% of Qwen3-30B-A3B).

**MoE composition (§3.5):**
- Per-block linear gates over a stacked adapter bank, trained with token-level CE plus a load-balancing loss (λ_LB = 0.05).
- The gates total 491,760 parameters. Top-1 routing is used at inference.

**Repo implementation (`moe_gate/`):**
- `per_layer` (default) and `global` routing scopes.
- SFT warm-start (`train/train_router_sft.py`), gate-only warm-start, and gate-only GRPO (`train/grpo_gater.py`).
- `configs/moe_gate.yaml` lists 5 SWE adapter slots plus a "no adapter" base slot.

**Consolidation alternatives (App. C, τ², Qwen3-30B-A3B):**

| Method | τ² overall |
|---|---|
| CORE-TSV merge | 39.6 |
| On-policy distillation | 37.8 |
| SFT on synthetic successes | 37.8 |
| Multi-capability GRPO | 40.9 |
| Best single adapter | 40.3 |
| TRACE MoE | 48.2 |

Quote (App. C): "Only Multi-Capability GRPO (40.9%) marginally outperforms the best single adapter (40.3%), whereas MoE significantly outperforms it."

**Released adapter (A6):**
- Only `semantic-logic-precision` for Qwen3.6-27B: rank-16 LoRA on `q,k,v,o`, group size 8, 130 iterations, "`--kl-coef 0.0`".
- Card quote: "Training data is **2 single-turn scenarios** — a narrow slice of the target capability."

### 2.6 Experiments and reported results (VERIFIED, paper v2)

**Benchmarks:**
- τ²-Bench: 50 Airline + 114 Retail.
- SWE-bench Verified: 500.
- ToolSandBox: 129, in App. B.

**Evaluation settings.** Quote (§4.1): "Unless specified otherwise, we evaluate all models with greedy decoding (temperature 0.0 ) for deterministic head-to-head comparison, a maximum context length of 32,000 tokens, and a maximum of 50 interaction steps per episode."

**Baselines:**
- GRPO on the target environment;
- AWM, Agent World Model (arXiv 2602.10090);
- ADP, Agent Data Protocol SFT (arXiv 2510.24702);
- SWE-RL;
- GEPA, given TRACE's capabilities as prompt text.

**Table 1, τ²-Bench pass rate (%):**

| Backbone | Base | GRPO on target | ADP | AWM | GEPA | Single-cap GRPO | TRACE |
|---|---|---|---|---|---|---|---|
| Qwen3-30B-A3B (overall) | 32.9 | 37.8 | 32.3 | 38.4 | 39.6 | 40.3 | **48.2** |
| Qwen3.6-27B (overall) | 50.0 | 53.7 | 51.2 | — | 53.0 | 55.4 | **59.1** |

**Table 2, SWE-bench Verified Pass@1 (%):**

| Backbone | Base | ADP | GEPA | SWE-RL | Single-cap GRPO | TRACE |
|---|---|---|---|---|---|---|
| Qwen3-30B-A3B | 26.0 | 30.2 | 31.0 | 32.6 | 36.6 | **41.0** |
| Qwen3.6-27B | 68.0 | 68.4 | 69.6 | 70.4 | 71.0 | **73.2** |

**ToolSandBox (App. B, Table 3):**

| Method | Perfect (of 129) | Mean similarity |
|---|---|---|
| Base | 19 | 0.411 |
| ADP | 19 | 0.422 |
| GRPO | 22 | 0.519 |
| AWM | 20 | 0.504 |
| GEPA | 22 | 0.520 |
| Single-cap GRPO | 22 | 0.514 |
| TRACE | 26 | 0.560 |

**Stochastic decoding (App. G: T = 0.7, 3 seeds, mean ± 95% CI):**

| Method | τ² overall (%) | ToolSandBox pass rate (%) | ToolSandBox mean sim. |
|---|---|---|---|
| Base | 32.1 ± 1.8 | 14.2 ± 2.2 | 0.40 ± 0.03 |
| GRPO | 36.4 ± 3.2 | 16.3 ± 1.9 | 0.51 ± 0.02 |
| GEPA | 38.0 ± 1.7 | 16.8 ± 1.1 | 0.52 ± 0.01 |
| TRACE | **46.1 ± 3.2** | **21.2 ± 2.2** | **0.56 ± 0.02** |

**Rollout scaling (§4.4):**
- TRACE goes from 32.9 to 48.2 at 5,120 rollouts.
- GRPO dips to 35.4 at 3,840 rollouts and stalls at 37.8.
- GEPA plateaus at 39.6.

**Transfer from τ² to ToolSandBox (App. H):**

| Method | Perfect (of 129) | Mean sim. |
|---|---|---|
| GRPO | 19 | 0.430 |
| TRACE | 20 | 0.482 |

**Internal inconsistencies (VERIFIED by comparison):**
- The SWE-RL margin is +8.4 in the abstract (32.6 → 41.0) but "+9 points" in the conclusion.
- The README says τ² 32.9 → **48.3** (+15.4) "from paper", while the paper says 48.2 (+15.3).

### 2.7 Released artifacts, reproducibility gaps and discrepancies

**Gaps the repo states itself:**
- **Missing helper file.** `capability_regression_safe_edit_game.py` (parser, apply logic, pytest runner, prompt templates) is missing. The game class imports it.
- **Missing scenario file.** `scenarios_v4_all.json` is missing.
- **Phase 5 is a stub.** The SWE README says `phase5_training.py` "is not a turnkey public trainer launcher yet." Quote: "Until those pieces are restored, use Phases 1-4 as the environment-generation reference and treat Phase 5 as a description of the internal training handoff."

**Release coverage (VERIFIED by listing; INFERENCE about consequence):**
- There are no τ²-Bench or ToolSandbox environment files: only prompts, and only the SWE game is registered.
- So the headline τ² results cannot be reproduced from released environments.

**Capability mining split:**
- Paper (§4.1): "all methods, including TRACE's capability discovery and synthetic environment generation, train on the disjoint SWE-smith (Yang et al., 2025) split."
- The released code (`phase2_capability_mining.py`) instead mines SWE-bench Verified `test` failures against gold patches.
- The LoRA card agrees with the code: "Qwen3.6 itself read the 123 failed SWE-bench Verified trajectories from its own baseline run and proposed a 5-category taxonomy of its weaknesses."
- No repo file mentions SWE-smith.
- INFERENCE: either the reported numbers came from a different pipeline than the one released, or the paper's statement is inaccurate. Not resolved; ask the authors before citing either version.

**Evaluation path:**

| Script / source | What it does |
|---|---|
| `eval_iter_on_8gpu.sh` | mini-swe-agent, step_limit 150, T = 0.7, 128k context, plus the official swebench harness on Modal. This is test-based, but its settings differ from the paper's stated greedy decoding, 32k context and 50 steps. |
| `phase6_final_eval.py` | Gold-file localization, a single-turn SEARCH/REPLACE at T = 0, and `passed = sum(1 for r in rows if r.get("jaccard", 0) >= 0.95)` over added-line sets versus the gold patch. This is **not test execution**. |
| README usage line | `phase6_final_eval.py --checkpoint iter_130` |
| `phase6_final_eval.py` itself | Hardcodes `iter_15` and has no argument parsing. |

**Baselines and numbers across artifacts:**

| Artifact | Qwen3.6-27B baseline | Note |
|---|---|---|
| Paper | 68.0% | |
| LoRA card | **58.2%** ("phase 1, untrained") | LoRA results "pending" |
| Prompt counts | 52.8% if over 500 | INFERENCE from the counts in §2.2 |

**Other count and naming mismatches:**
- Capability count: the paper says 3 SWE environments; 2 phase-3 generators are released; the MoE config lists 5 adapter names; only 1 adapter is on HF.
- Hardware: the paper says A100s; the repo says H100s.
- License: the code is MIT, but the HF LoRA is tagged Apache-2.0.

### 2.8 What TRACE contributes to TraceContract (INFERENCE)
- **A possible baseline task source and a cautionary example.** Its self-test gate (target fails before the oracle and passes after; regression guards pass) is the "ordinary generated behavioral tests + oracle" bar our audit should exceed.
- **Its synthetic scenarios carry an explicit `naive_fix_description`, a natural near-miss.** That field is used as a hint, never as an audit negative.
- **It is not a correction or reward-fidelity work.** It has no user corrections, no human labels and no FA/FR. Low overlap with our measurement question; medium overlap only on "trajectory analysis → environments".

---

## 3. TRACE (and trace-named) disambiguation table (all VERIFIED on arXiv abs pages unless noted)

| Name / acronym | Authors | Date (arXiv versions) | Link | One-line description |
|---|---|---|---|---|
| **TRACE**: Turning Recurrent Agent failures into Capability-targeted training Environments ("Capability-Targeted Agentic Training") | H. Kang, T. Suresh, J. Saad-Falcon, A. Mirhoseini | v1 2026-04-07; v2 2026-07-02 | arxiv.org/abs/2604.05336 | Failure-contrastive capability mining → per-capability synthetic envs → GRPO LoRAs → MoE (this note §2). HF LoRA card calls it "Test-time Reinforcement Learning Adaptation via Capability Environments" |
| **TRACE**: Test-time Rule Acquisition and Compiled Enforcement → renamed **TellOnce** | Y. Zhou, K. Guo, H. Zhuang, X. Wang, Y. Huang, Z. Liang, P.-Y. Chen, T. Gao, N. Moniz, N. V. Chawla, X. Zhang | v1 2026-06-11 ("Getting Better at Working With You: Compiling User Corrections into Runtime Enforcement for Coding Agents"); v2 2026-10-25 ("TellOnce: Correcting Coding Agents Once, Improving Their Future Actions") | arxiv.org/abs/2606.13174 | Mines user corrections from coding-agent chats into atomic rules plus runtime checks for *future* tasks (see `corrections.md`). v1 quote: "We introduce Test-time Rule Acquisition and Compiled Enforcement (TRACE), a drop-in skill-layer pipeline for coding-agent runtimes that mines user corrections, rewrites them as atomic rules, and compiles them into runtime checks that must pass before an agent completes future tasks." |
| **TRACE**: Truncated Reasoning AUC Evaluation | X. Wang, N. Joshi, B. Plank, R. Angell, H. He | v1 2025-10-01 … v4 2026-03-02; comments "ICLR 2026 Oral Presentation" | arxiv.org/abs/2510.01367 | Detects implicit reward hacking by truncating the CoT and measuring how early the expected reward saturates: "To detect implicit reward hacking, we propose TRACE (Truncated Reasoning AUC Evaluation)." Directly relevant to reward-fidelity framing |
| **TRACE**: Trajectory-based Validated-by-Reproducing Agent-benchmark Complexity Evolution | D. Guo, T. Zhou, D. Liu, C. Qian, Q. Ren, S. Shao, Z. Fan, Y. R. Fung, K. Wang, L. Zhang, J. Shao | v1 2025-10-01; v3 2026-03-24 (comments: "work in progress") | arxiv.org/abs/2510.00415 | Evolves existing benchmark tasks (GAIA, AIME-2024) into harder ones with validate-by-reproduce trajectories. Paper title: "Towards Self-Evolving Benchmarks: Synthesizing Agent Trajectories via Test-Time Exploration under Validate-by-Reproduce Paradigm" |
| **TRACE**: Trajectory Reasoning through Adaptive Cross-Step Evidence Aggregation | V. Mittapalli, S. J. Dani, S. S. Pilli, S. Ansu, M. Teymoorianfard, F. Dernoncourt, H. Chen, Y. Wang, R. A. Rossi, N. K. Ahmed | 2026-06-05 | arxiv.org/abs/2606.07054 | Triage-Inspect-Judge monitor for sabotage in long agent trajectories (SHADE-Arena; F1 0.713, recall 0.844) |
| **TRACE** (trustworthy agentic AI engineering framework) | S. Zabolotnii | 2026-05-05 | arxiv.org/abs/2605.03838 | Metrology-grounded reference architecture for operationally critical domains |
| **TRACE**: continual-learning benchmark for LLMs | X. Wang, Y. Zhang, T. Chen, S. Gao, S. Jin, X. Yang, Z. Xi, R. Zheng, Y. Zou, T. Gui, Q. Zhang, X. Huang | 2023-10-10 | arxiv.org/abs/2310.06762 | 8-dataset continual-learning benchmark (includes code generation) plus the RCL method |
| **TRACE**: Temporal Grounding Video LLM via Causal Event Modeling | Y. Guo, J. Liu, M. Li, Q. Liu, X. Chen, X. Tang | v1 2024-10-08; v3 2025-03-03; ICLR 2025 | arxiv.org/abs/2410.05643 | Video LLM for temporal grounding |
| **TRACE** the Evidence (RAG reasoning chains) | J. Fang, Z. Meng, C. Macdonald | 2024-06-17 | arxiv.org/abs/2406.11460 | KG-triple reasoning chains for multi-hop RAG |
| **TRACE**: TRansformer-based Attribution using Contrastive Embeddings | C. Wang, X. Lu, S.-K. Ng, B. K. H. Low | 2024-07-06 | arxiv.org/abs/2407.04981 | Source attribution for LLM outputs |
| **Trace** (Microsoft library; "Trace is the Next AutoDiff") | C.-A. Cheng, A. Nie, A. Swaminathan | v1 2024-06-23; v2 2024-11-01 | arxiv.org/abs/2406.16218 | OPTO setup plus the `Trace` Python library and the OptoPrime optimizer; execution traces as "gradients" |
| **TRACED**: Execution-aware Pre-training for Source Code | Y. Ding, B. Steenhoek, K. Pei, G. Kaiser, W. Le, B. Ray | 2023-06-13; ICSE 2024 | arxiv.org/abs/2306.07487 | Code LMs pre-trained with execution traces |
| **TraceRL** (TraDo models) | Y. Wang, L. Yang, B. Li, Y. Tian, K. Shen, M. Wang | 2025-09-08 | arxiv.org/abs/2509.06949 | Trajectory-aware RL for diffusion LMs |
| **TraceCoder** | J. Huang, W. Ye, W. Sun, J. Zhang, M. Zhang, Y. Liu | 2026-02-06 | arxiv.org/abs/2602.06875 | Runtime-trace-driven multi-agent debugging of LLM code |
| **CodeTracer** / CodeTraceBench | H. Li, Y. Yao, L. Zhu, R. Feng, … , J. Liu (16 authors) | v1 2026-04-13; v3 2026-04-15 | arxiv.org/abs/2604.11641 | Hierarchical trace trees and failure-onset localization for code agents |
| **TRAIL** (Trace Reasoning and Agentic Issue Localization) | D. Deshpande, V. Gangal, H. Mehta, J. Krishnan, A. Kannappan, R. Qian | v1 2025-05-13; v3 2025-06-23 | arxiv.org/abs/2505.08638 | 148 human-annotated agent traces with an error taxonomy |
| **Trace2Eval** | J. Shi, L. Jie, L. Zou, Y. Zhu, Y. Yang, X. Cao, X. Cai, M. Zhang | 2026-11-04 | arxiv.org/abs/2611.06506 | Real coding-agent traces → contextualized, rubric-judged evaluation (see `trace2eval.md`) |
| **Trace Commons** (dataset) | trace-commons org (single maintainer account in commit log) | 2026-06-11 → 2026-06-18 | huggingface.co/datasets/trace-commons/agent-traces | Donated coding-agent sessions (§5) |
| **traj2envs** (tool) / traj2envs-rl (suite) | Hugging Face repo; last commit by Younes Belkada (git log) | HEAD 2026-11-05; suite 2026-11-06 | github.com/huggingface/traj2envs ; huggingface.co/datasets/harness-hub/traj2envs-rl | Trajectories → validated Harbor RL tasks (§6) |
| **TraceContract** (name collision with our working name) | H. Barringer, K. Havelund | 2011; FM 2011, LNCS, pp. 57–72; DOI 10.1007/978-3-642-21437-0_7 (Crossref) | doi.org/10.1007/978-3-642-21437-0_7 | Scala internal DSL for trace analysis / runtime verification. Search snippets (not primary) mention a later system, Daut |

- INFERENCE (citation hygiene):
  - Always cite TRACE with first author and arXiv ID, e.g. "TRACE (Kang et al., 2026, arXiv:2604.05336)".
  - Never write bare "TRACE".
  - For 2606.13174, cite the version: "TRACE (v1)" or "TellOnce (v2)".
- Package names (VERIFIED by HTTP 404 on 2026-11-13): `tracecontract`, `trace-contract` and `trace_contract` are unused on both PyPI and npm. The name still collides with the FM 2011 tool in the literature. Consider a different public name, or disambiguate explicitly.

---

## 4. Survey: failure-driven / capability-targeted environment and data generation (verified on arXiv abs pages)

| Work | Authors (first + et al.) / date | arXiv | Mechanism (from abstract) | Code/SWE? | Measures verifier fidelity? |
|---|---|---|---|---|---|
| Targeted Data Generation (TDG) | Z. He, M. T. Ribeiro, F. Khani; 2023-05-28; ACL 2023 | 2305.17804 | Finds challenging subgroups, generates data for them with LLMs and a human in the loop, and estimates benefit and harm | No (NLP classification) | No |
| EnvGen | A. Zala, J. Cho, H. Lin, J. Yoon, M. Bansal; v1 2024-03-18, v2 2024-07-12; COLM 2024 | 2403.12014 | LLM generates and **adapts environment configs toward skills the agent is weak at**, using agent performance feedback | No (Crafter, Heist) | No |
| AutoDetect | J. Cheng et al.; v1 2024-06-24, v2 2024-12-10; EMNLP 2024 Findings | 2406.16714 | Examiner, Questioner and Assessor agents expose weaknesses; the weaknesses guide improvement data | Partly (includes coding) | No |
| LLMs-as-Instructors | J. Ying et al.; 2024-06-29 | 2407.00497 | An instructor LLM analyzes a target model's errors, including contrastively against correct answers ("Learning from Error by Contrast"), and tailors training data | Includes coding benchmarks | No |
| DataEnvGym | Z. Khan, E. Stengel-Eskin, J. Cho, M. Bansal; v1 2024-10-08, v3 2025-03-13; ICLR 2025 Spotlight | 2410.06215 | Teacher environments in which data-generation agents get student feedback ("errors or weak skills") | Includes code tasks | No |
| WebRL | Z. Qi et al.; v1 2024-11-04, v3 2025-01-27; ICLR 2025 | 2411.02337 | Self-evolving curriculum: "a self-evolving curriculum that generates new tasks from unsuccessful attempts" | No (web) | No (uses an ORM) |
| EEF (Exploring Expert Failures) | L.-C. Lan et al.; v1 2025-04-17 (withdrawn), v2 2025-04-18 | 2504.13145 | Mines useful actions from failed expert trajectories for agent tuning | No (WebShop) | No |
| Self-Challenging LM Agents | Y. Zhou, S. Levine, J. Weston, X. Li, S. Sukhbaatar; 2025-06-02 | 2506.01716 | Agent generates "Code-as-Task" tasks with a verification function plus solution and **failure cases as tests** | Tool use | Indirect: failure cases filter tasks; no human labels |
| SwS | X. Liang et al.; 2025-06-10 | 2506.08989 | Weakness-driven problem synthesis: problems the model consistently fails during RL seed new problems | Math | No |
| Where LLM Agents Fail… (AgentDebug) | K. Zhu et al.; 2025-09-29 | 2509.25370 | Error taxonomy, AgentErrorBench and root-cause feedback | No | No |
| Agent Learning via Early Experience | K. Zhang et al.; v1 2025-10-09, v3 2026-05-24; ICML 2026 | 2510.08558 | Learns from the agent's own suboptimal actions (world modeling, self-reflection) | Mixed | No |
| BugPilot | A. Sonwane et al.; v1 2025-10-22, v2 2025-10-28 | 2510.19898 | SWE agents add features that unintentionally break tests, yielding realistic bugs | **SWE** | No |
| RLVE | Z. Zeng et al.; v1 2025-11-10, v2 2026-06-06; ICML 2026 | 2511.07317 | 400 verifiable environments that adapt difficulty to the policy | Reasoning | No |
| Self-play SWE-RL (SSR) | Y. Wei et al.; v1 2025-12-21, v3 2026-06-02; ICML 2026 | 2512.18552 | One agent injects and repairs bugs, each specified by a test patch | **SWE** | No |
| Agent World Model (AWM) | Z. Wang et al.; v1 2026-02-10, v3 2026-05-22; ICML 2026 | 2602.10090 | 1,000 fully synthetic DB-backed environments; *not* failure-targeted (TRACE's foil) | Tool use | No |
| **TRACE** | Kang et al.; 2026-04-07 / 07-02 | 2604.05336 | §2 | τ², ToolSandbox, **SWE** | No (self-test plus calibration only) |
| Agent-World | G. Dong et al.; 2026-04-20 ("Working in progress") | 2604.18292 | Self-evolving arena that "automatically identifies capability gaps through dynamic task synthesis" | MCP tools | No |
| Socratic-SWE | C. Xiao et al.; 2026-06-05 (under review) | 2606.07412 | Distills the solver's historical traces into skills summarizing recurring failures, then generates **targeted repair tasks in real repositories** with execution-based validation. Quote: "Existing synthetic data methods typically create tasks through fixed mutation or bug-injection procedures, making the resulting distributions largely independent of the agent's own weaknesses and training progress." | **SWE** (50.40% Verified after 3 iterations) | No |
| SENTINEL | Z. Wang et al.; 2026-06-11 | 2606.12908 | Controller–Proposer–Solver: "turns the Solver's rollout failures into targeted training tasks" | τ² Retail (Qwen3-4B Pass^1 66.4 → 74.9) | No |
| Environment Evolution for Terminal Agents | Z. Fan et al.; 2026-09-03 | 2609.04128 | Off-policy difficulty evolution (contrasted with on-policy "co-evolution methods" that "synthesize environments near the model's learnable frontier based on weaknesses exposed during rollouts") | Terminal-Bench 2.1 (+14.4 / +18.0 pp) | No |

- TRACE's own related work (§2) cites none of TDG, EnvGen, AutoDetect, LLMs-as-Instructors, DataEnvGym, WebRL or SwS. It frames prior synthetic-environment work only as untargeted. Quote: "While effective for general capabilities (Yang et al., 2025; Fang et al., 2025b), these approaches overlook model-specific failures." INFERENCE: the "failure-targeted environment" idea is not new with TRACE.
- INFERENCE (for TraceContract): no work in this table measures false acceptance or false rejection of its generated verifiers against independent labels. The closest checks are:
  - Self-Challenging's failure cases;
  - TRACE's transfer sanity check;
  - mutation/hacking checks in synthesis pipelines (see `env_synthesis.md`).

  This leaves the reward-fidelity measurement gap intact. These works do motivate why the gap matters: environments generated from failures are exactly where verifier shortcuts get trained in.

---

## 5. (B) Trace Commons in detail (`trace-commons/agent-traces`)

### 5.1 Size and structure (VERIFIED from API, datasets-server and tree)

**Sessions:**
- 30 parquet rows (one per session).
- `harness` frequencies: `claude_code` 28, plus 2 nulls. INFERENCE: the 2 nulls are the Cursor and opencode files.
- Raw files: 28 under `sessions/claude_code/` (one named `comparia-voting-fields-anon.jsonl`), 1 `sessions/cursor/*.jsonl`, 1 `sessions/opencode/*.json`.
- `sessions/codex` and `sessions/pi` hold only `.gitkeep`.

**Sizes:**
- Raw session files total 57,228,063 bytes; the largest is 13,701,935 bytes (LFS).
- Parquet download size is 70,202,603 bytes; dataset_size 70,588,534; HF `usedStorage` 206,956,583.

**Columns:** `harness`, `session_id`, `prompt`, `messages` (Json list), `tools`, `metadata` (Json), `sent_at`, `num_user_messages`, `num_tool_calls`, `trace` (Json list) and `file_path`.

**Statistics (datasets-server):**

| Column | Mean | Median | Max | Other |
|---|---|---|---|---|
| `num_user_messages` | 13.77 | 10 | 75 | 13 of 30 rows are in the [0, 8) bin |
| `num_tool_calls` | — | 118.5 | 447 | |
| `messages` length | — | 248.5 | 994 | |

- INFERENCE: median 10 user messages suggests multi-turn sessions in which follow-ups and corrections are plausible. Whether `num_user_messages` counts only human turns or also Claude Code `type:user` tool-result entries is not documented. Unverified without opening data.

**Growth and maintenance:**
- 49 commits; 49 discussions: 31 merged PRs, 8 open PRs, 8 closed PRs, 2 open discussions.
- The open PRs date 2026-06-29 to 2026-08-29 and include Codex and opencode donations. None merged after 2026-06-18.
- The org overview shows `numUsers: 1`.
- INFERENCE: a small, single-maintainer project whose intake appears to have stalled.

**Ecosystem bias.** The card says it is not representative. Quote: "Not a complete or representative sample of agent usage — it is a voluntary, opt-in commons and will be biased toward contributors who choose to donate."

### 5.2 Collection, anonymization (VERIFIED)
- Quote: "Every trace here was donated **only from a public, open-source repository**, was **anonymized on the contributor's own machine before upload**, and was **reviewed by the contributor** before it was submitted as a pull request."
- Format quote: "Every session is preserved as its agent's **raw, unmodified session file** (only anonymized, never reshaped), organized by which agent (harness) produced it:"
- **Card vs current skill.**
  - The card's skill description says it "Confirms the session's project is a public, open-source repository — and refuses otherwise."
  - The **current** skill (HEAD 2026-06-16, commit "Shift publishability burden to the contributor (inform, don't gatekeep)") says: "You are not the gatekeeper; the contributor certifies."
  - INFERENCE: the open-source-only rule is now enforced by contributor certification, not by a skill-level refusal.
- **Scrubbing.**
  - `scrub.py` covers home paths and usernames (including Claude Code dash-encoded project slugs), many secret formats, emails and RFC1918 IPs. TruffleHog runs server-side and flags donations for maintainer review rather than auto-rejecting them.
  - A human/agent review pass looks for names, companies and internal URLs.
  - Quote: "Do not assume this data is free of personal information."
- **Fields kept vs removed.** Quote (`scrub.py`): "The script walks the parsed JSON of each session line and rewrites string values in place, so it works regardless of where in the structure a string sits." INFERENCE: fields are rewritten, not dropped. So native Claude Code fields survive, such as `cwd`, `gitBranch` and, if present, `toolUseResult`.
  - Per `swechat.md` §6.5, `toolUseResult` for Edit/Write carries `originalFile` and `structuredPatch` in native Claude Code transcripts.
  - Whether Trace Commons files contain them was not checked (data not opened).

### 5.3 License and rights to embedded material (VERIFIED quotes)
- The compilation is CC-BY-4.0: "You may use, share, and build on it (including for training) with attribution to Trace Commons."
- Rights basis: "Traces are accepted on the basis of the **contributor's certification**: by donating, a contributor certifies that the session is not private or confidential and that they have the right to publish it publicly under this license."
- Maintainer role: "That certification — not maintainer vetting — is what traces rest on; we do not and cannot verify the provenance or license of everything inside every trace."
- Reuser duty: "**If you reuse this data, you are responsible for checking that your use complies with the licenses of any code or content contained in the traces.**"
- Contributors are also responsible for complying with their coding-agent provider's terms (card, §License). GDPR erasure applies, takedown runs through the Community tab, and the data is "not certified anonymous" (§Privacy).
- The `donate-trace` repo has **no LICENSE file**. Its code license is unstated.

### 5.4 Initial states / commits (VERIFIED absence + INFERENCE)
- **No commit SHA or remote URL is added.** The anonymous donation payload is `{"harness","filename","consent","trace"}` (`references/publishing.md`). The attributed path uploads the file directly.
- **What Claude Code itself records.** The skill's Claude Code reference lists `cwd` (with the username scrubbed to `USER`) and `gitBranch`. Quote: "top-level `gitBranch` — branch name (may encode a feature/client name)".
- **Commits and branch names (INFERENCE).**
  - Commit hashes appear only if the agent printed them in tool output, for example `git log`.
  - Repo identity must be inferred from the `cwd` folder name, remote URLs in tool output, or prose.
  - Free-text review may redact handles inside GitHub URLs, which makes repo identification harder.
- **Replayability (INFERENCE):** low to medium.
  - Edited-file pre-states may be recoverable from native tool results.
  - Untouched files and the base commit are not recorded.
  - Base reconstruction would need timestamp-to-commit matching on the public repo.

---

## 6. traj2envs (trajectory → Harbor RL tasks): the closest engineering neighbour (VERIFIED from code/docs unless noted)

### 6.1 The tool (`huggingface/traj2envs`, Apache-2.0)

**Purpose and input.**
- `pyproject.toml` description: "Turn ATIF agent trajectories into validated Harbor RL tasks" (the README's first line says the same with links). ATIF is Harbor's "Agent Trajectory Interchange Format" (local Harbor clone, `packages/rewardkit/CLAUDE.md`).
- `traj2envs convert` imports raw Claude Code, Codex and pi session logs, including `hf://datasets/...`.
- Expected yield. Quote: "Trace datasets mostly hold one-shot "build X" sessions: expect a few percent of sessions to yield a" (sentence continues "`repair` or `build` candidate").

**State reconstruction.** `Trajectory.replay` applies `Write`/`Edit`/`MultiEdit`/full `Read`/`apply_patch`/heredocs to a virtual filesystem. Every shell run gets `files_before`. An edit that cannot be reconstructed marks the file *lost*.

**Families:**

| Family | Found in the trajectory | Start state and reference | Reward |
|---|---|---|---|
| `repair` | a check that failed, then passed after edits | start = files at the failure; fix = the agent's | 1/0 |
| `build` | first-request Python project with a passing last check | "replays up to the second user message", i.e. **initial-request-only** | fraction of hidden tests |
| `extend` | a later request that changed a Python project and ended with passing checks | "The task starts from the files at the end of request k (dependencies installed) and gives the agent request k+1." The instruction lists "Earlier requests (already implemented)" plus the next request | fraction of new tests; 0 if any existing test fails |
| `qa` | a fact the agent computed from HF data | — | exact or numeric match |

**Tests are LLM-written.** Quote: "The LLM (`claude-opus-5-5`, override with `TRAJ2ENVS_MODEL`) only proposes questions, contracts and tests."

**Verifier validation (a predefined audit, but with trivial negatives):**
- **Trial matrix.** Run in the task's own image, offline. The listed trials must score full reward or 0 exactly:

  | Family | Must score full reward | Must score 0 |
  |---|---|---|
  | `repair` | original fix (twice) | do nothing; tamper with the check |
  | `build` | reference | stub; empty workspace |
  | `extend` | original implementation (twice) | do nothing; delete the project |

- **`build` and `extend` test filtering.** Tests must pass on the reference twice and fail on the stub or start state. They must kill enough AST **mutants**:
  - up to 16 single-point AST mutants (default `count=16`): comparison, arithmetic, boolean, int constant +1, `return None`. In `extend` they are made only from changed Python files, and the kill-rate check is skipped when the rate is `None`;
  - `MINIMUM_MUTANT_KILL_RATE` 0.6 for `build` (at least 6 tests) and 0.5 for `extend` (at least 5 new tests).
  - Quote: "Kept tests must catch most mutants of the changed code."
- **`gate.py`.** If `atif-scan` is installed, trajectories with findings such as `tamper.reward_write`, `tamper.test_files` or `access.benchmark_material_received` are dropped.

### 6.2 The published suite (`harness-hub/traj2envs-rl`, `license: other`)

**Size and families (VERIFIED):** 270 tasks: `build` 253, `repair` 11, `extend` 6.

**Sources (VERIFIED, `sources.json`): 267 trace files from 7 datasets:**

| Source dataset | Files |
|---|---|
| `TeichAI/Ox-Alpha-Pi-Traces` | 242 |
| `choucsan/mimo-claude-code-traces-1k` | 9 |
| `TeichAI/DeepSeek-v4-Pro-Agent` | 7 |
| `AletheiaResearch/GPT-5.5-Codex` | 5 |
| `AletheiaResearch/GLM-5.2-Agent` | 2 |
| `armand0e/kimi-k2.6-claude-code-traces` | 1 |
| `lewtun/ml-intern-sessions` | 1 |

- The TeichAI cards open with "This dataset was generated using [teich]" (the `teich` tool). The Ox-Alpha card lists topic distributions of prompts. The DeepSeek card states "All assistant responses were generated by **deepseek/deepseek-v4-pro**." INFERENCE: almost all sources are distillation-style generated sessions, not real user sessions with corrections.

**Task statistics (datasets-server):**
- `hidden_tests` 8–23.
- `mutant_kill_rate` 0.6–1.0, with 11 nulls.
- Difficulty: easy 179, medium 61, hard 30.
- `gate`: "skipped (--no-scan)" for all 270.

**Example `task.toml`:**
- `tests_written_by = "mistralai/Mistral-Large-4-1T-A52B:openrouter"`;
- solve rate measured with `terminus-2:LiquidAI/LFM2.5-24B-A2B` over 2 attempts;
- Docker image pinned at `docker.io/ybelkada/t2envs@sha256:…`;
- `allow_internet = false`.

**No paper and no web hits.** I found no paper or web page describing traj2envs (WebSearch, standard mode, no hits).

### 6.3 Overlap with TraceContract (INFERENCE)

**What it already does:**
- (i) Session → executable task with exact replayed file states.
- (ii) A later-request task starting from the pre-request state. When request k+1 is a correction, `extend` is our pre-correction setup, and its calibration *requires* new tests to fail on that state.
- (iii) A predefined automated verifier audit: trial matrix plus mutation kill rate.
- (iv) An initial-request-only variant (`build`).

**What it lacks:**
- (a) Human-adjudicated labels, so no FA/FR.
- (b) A comparison of initial-only vs correction-aware contracts on the *same* candidates.
- (c) Valid alternative implementations as positives. Only the original implementation is a positive.
- (d) Naturally observed near-misses beyond AST mutants.
- (e) Real-user sessions in the released suite.

**Consequence.** TraceContract should cite traj2envs and position its trial matrix and mutant kill rate as a *baseline audit*. A key hypothesis to test: high mutant kill rate does not imply low correction-omission FA.

---

## 7. Other agent-trace and developer-AI datasets (cards and metadata only)

Legend:
- **Origin**: N = naturally occurring, S = synthetic/model-generated.
- **Users**: are real human users present?
- **Corr.**: are later user corrections present (unlabeled unless noted)?
- **State**: code states / commit links.
- **Replay**: replayability for building repo tasks.

All rows are VERIFIED from cards/API unless marked "(I)" for inference.

| Dataset (created / modified) | Origin | Users | Corr. | State | License / terms | Size | Replay |
|---|---|---|---|---|---|---|---|
| **SWE-chat** `SALT-NLP/SWE-chat` (reference; see `swechat.md`) | N | yes | yes; pushback labels | Entire checkpoints → commits | ODC-BY; gated | v2 ~18k sessions | medium-high |
| **Trace Commons** `trace-commons/agent-traces` (2026-06-11 / 06-18) | N (donated; OSS certified) | yes | likely, multi-turn, unlabeled (I) | no commits; `cwd` and `gitBranch` kept | CC-BY-4.0 compilation; embedded content keeps own licenses; reuser must check | 30 sessions | low-medium (I) |
| **AIDev** `hao-li/AIDev` v5 (2025-07-25 / 2026-10-21) | N (mined from GitHub) | yes (PR authors, reviewers) | yes, as PR review comments plus follow-up commits (paper Fig. 1) | **exact**: `pr_commits.sha`; review comments carry `commit_id`, `original_commit_id`, `diff_hunk`; patches | CC-BY-4.0; "**Each source repository retains its original copyright and license**"; `repository.license` field | 7,685,281 PRs (all); AIDev-pop 361,296 PRs / 25,402 repos / 291,248 inline review comments / 541,831 reviews / 1,718,829 commits | high (public repos) (I) |
| **pi-share-hf datasets**, e.g. `badlogicgames/pi-mono` (2026-04-06) | N | yes (project author) | yes; tree-structured sessions with `branch_summary` entries | header has `cwd` and `timestamp` only; source repo named on card; no commit | `license: other` (no text); others vary: `thomasmustier/*` MIT, `julien-c/pi-sessions` CC-BY-4.0 | 629 files | medium: base inferred by time (I) |
| `MaxDevv/real-pi-coding-agent-traces-sessions` (2026-07-19) | N (aggregate of 21 pi datasets) | yes | yes | per-session provenance in `manifest.jsonl` | `license: other`; per-session source license | 1,291 sessions, 192,309 messages, ~194M tokens, 2025-12-01 → 2026-06-18 | medium (I) |
| **DataClaw** datasets (49 tagged), e.g. `peteromallet/dataclaw-peteromallet` (2026-02-24) | N | yes | yes | `project`, `git_branch`, timestamps; tool inputs and outputs; no repo URL or commit | MIT (per dataset); **no open-source-only rule**; README: "**This is a performance art project.**" | 549 sessions / 14 projects | low-medium (I) |
| `OpenHands/openhands-feedback` (2024-12-06 / 12-14) | N | yes | yes, plus a thumbs-up/down label | not stated | MIT ("like OpenHands itself"); public-shared only; opt-out before release | 275 examples, ~310 MB | unknown |
| **DevGPT** (Zenodo 2023-11-09; MSR 2024) | N (shared ChatGPT links) | yes | multi-turn | linked artifacts with `CommitSha` (code-file mentions), commits, PRs, issues; not the state at chat time | CC-BY-4.0 (Zenodo) | 29,778 prompts/responses; 19,106 code snippets; 6 weekly snapshots 2023-07-27 → 08-31 | low (I) |
| `nebius/SWE-agent-trajectories` (2024-12) | S (agent runs on real issues) | no | no | `instance_id` → SWE-bench-extra; `generated_patch`; `eval_logs`; `target` | CC-BY-4.0 + per-repo licenses + Llama 3.1 notice | 80,036 trajectories (13,389 resolved) | high |
| `nebius/SWE-rebench-openhands-trajectories` (2025-09 / 12-27) | S | no | no | `instance_id` → SWE-rebench images; `model_patch`; `resolved`; **`gen_tests_correct`, `pred_passes_gen_test`** | CC-BY-4.0 | 67,074 trajectories (32,161 successful); 1,823 repos | high |
| `SWE-Gym/OpenHands-Sampled-Trajectories` / `-SFT-` | S | no | no | `instance_id`, `resolved` | Sampled: no license tag; SFT: MIT | 6,055 trajectories (491 resolved) (from the nebius comparison table); SFT 491 | high |
| `SWE-bench/SWE-smith-trajectories` | S (synthetic tasks) | no | no | `instance_id`, `patch`, `resolved` | MIT | splits: tool 24,100 / xml 26,076 / ticks 25,826 | high |
| `R2E-Gym/R2EGym-SFT-Trajectories` | S | no | no | messages only | no license tag | 3,231 | medium |
| `nvidia/SWE-Zero-` / `SWE-Hero-openhands-trajectories` (2026-04/05) | S (Qwen3-Coder-480B) | no | no | `instance_id`, `repo`, `license`, `model_patch` | CC-BY-4.0; permissive repos only | 318,115 trajectories / 118,092 issues; 34,269 / 11,766 | high |
| `neulab/agent-data-collection` (ADP) | mostly S | no | no | varies | per-subset LICENSE | 23 subsets | varies |
| `open-thoughts/AgentTrove` (2026-04/05) | S (teacher traces via Harbor) | no | no | `task_id`, `reward` | Apache-2.0 | 1,696,847 rows / 219 sources | varies |
| `harness-hub/traj2envs-rl` (2026-11-06) | derived from S traces | no | no (6 `extend` tasks) | `environment/before/`, hidden tests, pinned images | `other` | 270 tasks | high |
| `crispwisp/wisp-claude-code-sessions` (2026-06/07) | N (one user, voice-driven) | yes | likely | raw Claude Code with `cwd`, `gitBranch` | MIT; public handle retained | 106 files | low (system/dotfile work) (I) |
| `Mike0021/codex-sessions` (2026-07-08) | "autonomous coding sessions" | unclear | unclear | Codex schema | no license tag | 27 sessions | low |
| `cfahlgren1/codex-sessions` (2026-03-27) | N (raw Codex rollouts) | yes (I) | unknown | raw | `other` | 5 files | low |
| `nlile/misc-merged-claude-code-traces-v1` (2025-12-16) | mixed (merge of 10 sources) | partly | unknown | some `gitdiff` (Hyperswitch) | no license tag | 32,133 conversations | low |
| `lewtun/ml-intern-sessions` (2026-05 / 09) | N (ML Intern CLI runs) | yes | unknown | Claude-Code-style events | `other`; card: "**WARNING: no comprehensive redaction or human review has been performed for this dataset.**" | 577 files | low |
| Distillation trace sets (`armand0e/*`, `TeichAI/*`, `AletheiaResearch/*`, `choucsan/*`) | S (generated prompts / harvested model outputs) | no or unclear | no | raw harness logs | MIT or unstated | 10²–10³ sessions each | low |
| `allenai/WildChat-4.8M` (2025-08) | N | yes | yes | none | ODC-BY | 3,199,860 conversations (non-toxic version) | none |
| `DJRHails/sharetrawl` (2026-06 / 11-12) | N (web-published chatbot shares) | yes | yes | none | **CC-BY-NC-4.0**; gated manual | 15,343 files | none |
| `Suzhen/SWE-Review-Chat` (2026-07 / 08) | N (PR review threads) | yes (human, bot, LLM, AI-agent reviewers) | yes (review) | PR URL, inline comments with diff context; no commit SHAs in the card field list | Apache-2.0 | ~1M PR conversations / 207 projects | medium (I) |
| `copilot-arena/editbench` (2025-06 / 2026-05) | N (real in-IDE edit instructions) | yes | no (single instruction) | `original_code`, `highlighted_code`, tests | Apache-2.0; card: "Models should NOT be trained on this dataset, as it is specifically designed to test model capabilities" | 156 tasks (143 Py, 13 JS) | high (but test-only) |

### 7.1 Per-dataset notes that matter

**AIDev:**
- The paper's Figure 1 caption (2602.09185) is exactly our correction structure. Quote: "The Coding Agent (GitHub Copilot) authored a pull request, received feedback from a human reviewer, and addressed the comment in a follow-up commit."
- Paper v1 (cutoff 2025-08-01): 932,791 PRs; curated 33,596 PRs / 2,807 repos with 28,875 reviews, 19,450 inline review comments and 88,576 commits.
- v5 on HF (cutoff 2026-03-31) is much larger (above).
- Known v3/v4 issue: per-PR sub-resources were truncated at 30 items. Fixed in v5 (October 2026). Re-fetched threads may include comments posted after the cutoff.
- AIDev identifies Claude Code PRs by body signatures such as "Co-Authored-By: Claude" or "Generated with Claude Code".
- INFERENCE: some SWE-chat repos may overlap with AIDev's Claude Code PRs, but the artifacts differ (PR review loop vs chat).

**pi ecosystem:**
- The session format docs say entries "form a tree structure via `id`/`parentId` fields, enabling in-place branching without creating new files". `branch_summary` entries record abandoned paths (`docs/session-format.md`). INFERENCE: abandoned branches plus later turns give correction signals and rejected attempts natively.
- Header example: `{"type":"session","version":3,"id":"uuid","timestamp":…,"cwd":…}`. There is no git commit field.
- `pi-share-hf` keeps sessions per OSS project and runs an LLM review whether a session is "about the target OSS project", plus TruffleHog (any finding blocks the session).
- `aaaaliou/pi-synthetic` is a repo *named* "pi-synthetic" (`git@github.com:aliou/pi-synthetic.git`). It is not synthetic data.
- `thomasmustier/pi-mono-sessions` holds 150 sessions on `earendil-works/pi` (MIT). Sessions added in October 2026 got a stricter full model read plus a human spot check.
- `badlogicgames/pi-mono`: quote "This dataset contains redacted coding agent session traces collected while working on https://github.com/badlogic/pi-mono.git."
- SWE-Together already used this ecosystem. Quote (§2.1): "Four upstream sources contribute to the evaluated suite: DataClaw (DataClaw Community, 2026), Pi-staging (Zechner, 2026), Hyperswitch (Archit11, 2026), and SWE-chat (Baumann et al., 2026), summarized in Table 1."
  - Table 1 yields (my arithmetic):

    | Source | Sessions → tasks | Yield |
    |---|---|---|
    | Pi-staging (29 datasets) | 2,397 → 23 | 0.96% |
    | DataClaw (32 datasets) | 2,228 → 29 | 1.30% |
    | Hyperswitch | 784 → 9 | 1.15% |
    | SWE-chat | 5,851 → 48 | 0.82% |

**DataClaw:**
- It exports "Model name, git branch, timestamps", user/assistant messages, thinking, and tool inputs and outputs.
- It asks the user which projects to exclude. It does **not** restrict to open-source projects.
- `misterkerns/my-personal-claude-code-data` and `peteromallet/dataclaw-peteromallet` report identical stats: 549 sessions, 14 projects, 15.1B input and 4.6M output tokens, last updated 2026-02-24. INFERENCE: one is likely a re-upload of the other, which raises a provenance concern.
- Tag counts on 2026-11-13: `dataclaw` 49 datasets, `pi-share-hf` 37, `agent-traces` 835, `claude-code` 249, `codex` 98.

**OpenHands feedback:**
- Docs (WebFetch summary only; wording not checked against a downloaded copy): public data is distributed under the MIT License; releases happen at milestones such as 1,000 examples; there is an email-based opt-out.
- The card's citation still points to `all-hands/openhands-feedback`.
- No update since 2024-12.

**nebius SWE-rebench-openhands-trajectories:**
- Quote: "To our knowledge, no other publicly available agent trajectory dataset includes evaluation of agent-generated tests."
- INFERENCE: rows with `pred_passes_gen_test > 0` and `resolved = 0` give a **free, large-scale estimate of false acceptance by agent-written tests**. This is useful as a pilot analysis before any human labeling.

---

## 8. Ranking: top 3 alternatives to SWE-chat for TraceContract (INFERENCE, with criteria)

Criteria, in order:
1. real user plus a later correction that adds or changes a requirement;
2. exact or recoverable code states at the correction point (pre-correction negative) and after (accepted);
3. rights: license and terms allow deriving and releasing tasks;
4. replayability: public repo, buildable offline, Python preferred;
5. scale for a pilot (10–30 tasks) and beyond;
6. independence from SWE-Together's sources.

1. **AIDev-pop (`hao-li/AIDev` v5).**
   - **Why.** Human review comments are natural corrections. Each inline comment pins the reviewed commit (`original_commit_id`), so the pre-correction state is exact. Follow-up commits and the merged state give the accepted target. Repos are public, with license metadata for filtering. The scale is very large (291,248 inline review comments). SWE-Together did not use it.
   - **Caveats.**
     - It is not a chat session: the private user–agent prompts behind Codex, Claude Code and Cursor PRs are absent. The "initial request" is the PR body or linked issue.
     - Not every review comment changes a requirement (style, nits). Not every follow-up is by the agent.
     - Environment building is SWE-bench-like work.
     - Consent basis is public GitHub posting plus CC-BY-4.0 compilation, not donation.
   - **Best fit.** Copilot-coding-agent PRs: the issue is assigned to the agent, and the reviewer's `@copilot` comment leads to an agent commit.
2. **pi-share-hf per-project datasets.** Start with `badlogicgames/pi-mono` (626 sessions) and `thomasmustier/*` (MIT), and use `MaxDevv`'s manifest for provenance.
   - **Why.** Real chat-native corrections on a named public repo, explicitly donated by the session author with an OSS-scope LLM review. The tree structure records abandoned branches.
   - **Caveats.**
     - No commit in the header: the base must be matched by timestamp to public history, which is risky if the working tree was dirty.
     - TypeScript-heavy.
     - License varies: `other` with no text for the largest set.
     - Already mined by SWE-Together ("Pi-staging", 23 tasks), which reduces novelty of task construction (not of measurement).
3. **Trace Commons.**
   - **Why.** Raw native session files (Claude Code, Cursor, opencode); explicit open-source-only contributor certification; CC-BY-4.0 compilation; GDPR takedown path. It is the cleanest rights story among chat-session sources and a good format and pilot test bed.
   - **Caveats.**
     - 30 sessions, with intake apparently stalled since June 2026.
     - No commits.
     - Embedded-code licenses must be checked by us.
     - Single maintainer.
   - **Runner-ups:**
     - DataClaw datasets. Bigger, and SWE-Together got 29 tasks from them, but there is no repo URL or commit, no OSS-only rule, the "performance art" framing raises provider-terms risk, and at least one dataset looks like a re-upload.
     - OpenHands feedback. 275 sessions, MIT, with thumbs labels useful for stratified sampling, but 2024-era and the state is unknown.
     - For **negative candidates, not sessions**: `nebius/SWE-rebench-openhands-trajectories`, which is replayable and has agent-test FA signals.

---

## 9. Design implications for TraceContract (INFERENCE)

1. **Add an AIDev arm.** Define:
   - initial contract = PR body or linked issue;
   - full contract = that plus requirement-changing review comments;
   - negative candidate = `original_commit_id` state;
   - positive candidates = the follow-up or merged state, and valid alternatives drawn from independent implementations.

   This gives exact naturally observed pre-correction states at scale and complements chat-based SWE-chat tasks.
2. **Adopt traj2envs's trial matrix and mutant-kill thresholds as the minimum automated audit**, and report them alongside human-label FA/FR:
   - repair: do nothing / tamper with the check;
   - build: stub / empty workspace;
   - extend: do nothing / delete project;
   - mutant kill ≥ 0.5–0.6.

   Pre-register the hypothesis that mutation score and trial-matrix pass do not predict correction-omission false acceptance.
3. **Include partial-credit trivial-patch probes in the audit.** Record the reward that a "do nothing but valid edit" patch gets. TRACE's released SWE reward would give it 0.6.
4. **Treat TRACE's `naive_fix_description` idea as a cheap near-miss generator.** Ask an LLM for the plausible wrong fix, then implement it. Validate these near-misses against human labels instead of trusting them.
5. **Run a pilot FA estimate before human labeling** using nebius `pred_passes_gen_test` vs `resolved`: agent-written tests accepting unresolved patches. This bounds how often ordinary generated tests falsely accept.
6. **Provenance manifest per task:**
   - source dataset, revision SHA and file hash;
   - repo URL and license (MIT/Apache/BSD filter);
   - the basis of rights (contributor certification, public GitHub, or ODC-BY gate).

   Do not redistribute raw session text. Release derived tasks with attribution (CC-BY / ODC-BY obligations). Avoid ungated mirrors of gated data and distillation trace sets with unclear provider terms.
7. **Naming.** Rename or explicitly disambiguate "TraceContract" (FM 2011 tool), and never cite "TRACE" without an arXiv ID (§3).

---

## 10. Novelty threats (what prior work already covers)

| Threat | Overlap | What it already covers | What it lacks |
|---|---|---|---|
| **traj2envs** (HF, Nov 2026) | high, engineering | trace → Harbor tasks with replayed states; initial-request-only (`build`) and later-request (`extend`) variants; a predefined automatic verifier audit (trial matrix, mutant kill) | human labels, FA/FR, valid alternatives, correction-aware vs initial-only comparison on the same candidates |
| **SWE-Together** | high | real sessions → tasks with later requirements in gates and rubric (see `swechat.md`) | FA/FR against human labels |
| **TellOnce / TRACE-v1** | medium | corrections → checks, with FP/FN on generated probes (`corrections.md`) | future-task scope |
| **TRACE (Kang et al.)**, Socratic-SWE, SENTINEL, Agent-World | low-medium | failure-driven environment synthesis, including SWE (TRACE, Socratic-SWE) | measurement of the verifiers they train on |
| **TRACE (Truncated Reasoning AUC)** | low-medium, conceptual | detecting reward hacking from the policy side | — |
| AIDev-derived empirical studies (e.g. review-theme taxonomies; AIDev card lists ≥15 papers) | low | analyze review comments | build no verifiers (I) |

---

## 11. Open questions
1. Which pipeline produced TRACE's 73.2% Qwen3.6-27B result?
   - Which harness and decoding were used: `eval_iter_on_8gpu.sh` or the paper's greedy, 32k, 50-step setting?
   - Were capabilities mined on SWE-smith (paper) or on SWE-bench Verified (released code and LoRA card)?
2. Do Trace Commons Claude Code files retain `toolUseResult.originalFile` / `structuredPatch`, which would give exact pre-edit file states? This needs a sanctioned look at 1–2 files.
3. What fraction of AIDev-pop review comments are requirement-changing, are followed by an agent commit that addresses them, sit in Python repos with runnable tests, and come from permissively licensed repos? This needs a metadata-only funnel on `pr_review_comments`, `pr_commits` and `repository.license`.
4. Under what license is `badlogicgames/pi-mono` (card `license: other`, no text) offered? And which 29 pi datasets form SWE-Together's "Pi-staging"?
5. Does traj2envs have a paper, a description of `atif-scan`, or plans to publish `extend` tasks from real-user sessions?
6. Is `misterkerns/my-personal-claude-code-data` a re-upload of `peteromallet/dataclaw-peteromallet`? The stats are identical, but the content was not compared.

## 12. Could not access / limitations
- **Blocked or unavailable:**
  - github.com web pages are blocked by the proxy. The GitHub REST API returned HTTP 403 ("not enabled for this session").
  - dblp served a bot-check page, so TraceContract was verified via Crossref.
  - `DJRHails/sharetrawl` and `lmsys/lmsys-chat-1m` READMEs are gated (HTTP 401); only API metadata and the gate text were read.
- **Read only partly:**
  - TRACE v1 full text not read (abstract only).
  - TRACE blog read only as a WebFetch summary (undated).
  - OpenHands feedback docs read only as a WebFetch summary.
  - TellOnce: targeted sections only.
  - SWE-Together: §2.1 / Table 1 / references only (rest in `swechat.md`).
- **Not opened by rule:** no dataset session or trajectory content. So I did not verify:
  - correction prevalence in Trace Commons or pi sessions;
  - whether DataClaw tool outputs are complete;
  - OpenHands `extras` contents.
- **Not found:** a paper for traj2envs. The SWE-Gym sampled-trajectories card has no prose.
- **Not checked:** the `harness-hub/traj2envs-rl` task contents beyond one `task.toml`. Tests and instructions were not read.

## 13. Related-work rows (for the synthesis table)
See the structured summary returned with this step. The rows cover:
- TRACE (Kang et al.);
- traj2envs plus traj2envs-rl;
- Trace Commons;
- AIDev;
- pi-share-hf / real pi traces;
- DataClaw;
- OpenHands feedback;
- DevGPT;
- nebius SWE-rebench-openhands trajectories;
- Socratic-SWE;
- SENTINEL;
- EnvGen;
- TRACE (Truncated Reasoning AUC Evaluation).
