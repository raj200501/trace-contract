# Fact check of `docs/research_brief.md`: 30 load-bearing statements

- **Scope.** The 30 factual statements that carry the novelty argument in the brief: every number cited for the closest works (SessionFarmer coverage and FPR/FNR, PersonaCodeBench 20.5%, AfterVibe 58.0%, ARE-bench ~69% vs 28.4–40.0%, CodeAssistBench 65.7%, SWE-Together 48/5,851 and 109 tasks, SWE-chat pushback rates, TiGanEval 56%), every verbatim quote attributed to SF Data's public pages and to the closest papers, and the date/version claims for the closest works.
- **Date of checks.** 2026-11-18 (UTC). The brief's access date is 2026-11-13; where a source changed in between, this is said.
- **Method.** Every source was fetched fresh. The research notes were not used as evidence.
  - arXiv metadata comes from the abs page's `citation_*` meta tags and the submission history. Full text comes from the arXiv HTML of the version named.
  - Quotes were checked by exact string match against the extracted page text. Whitespace was normalised only where HTML wraps lines; apostrophes and diacritics were kept as published.
  - Numbers were read from the tables. SWE-chat Figure 8 was rendered from its SVG and read from the printed values.
  - Other sources: HF API and dataset pages, PyPI JSON, GitHub through WebFetch and `raw.githubusercontent.com` (the session proxy blocks `github.com` for curl), and the ICML virtual page.
- **Downloads.** `/home/user/tc_review_dl/fact_check/` (untrusted copies, not committed).
- **Verdict counts.** 26 ok; 2 factual errors (medium); 1 citation error (low); 1 overclaim (low). No checked number was wrong. Every SF Data quote matches exactly.

## Corrections needed

1. **§3.2, "Why the argument does not fully hold", first bullet (line 395).** "Its Appendix D lists that analysis as future use" is wrong.
   - SessionFarmer's App. D ("Future Uses of SessionFarmer") lists agent-side analyses:
     - whether "the requirements missed by evaluated agents concentrate on those disclosed after the opening message";
     - pushback-turn comparisons;
     - opening-message variants "paired with a user simulator that answers from later turns";
     - RL environments.
   - It does not list building verifiers from the opening request or measuring their false acceptance.
   - The §2.1 row's wording ("App. D lists analysis of later-disclosed requirements as future work") is accurate, and should replace the §3.2 wording.
2. **§3.2, "Human ground truth" bullet (line 396).** "TestJack, ARE-bench, TraceDance and traj2envs have no human candidate labels" is wrong for TraceDance.
   - In TraceDance, two annotators rated pass/fail on 84 instances, "Each instance is paired with one evaluated LLM's response".
   - Judge-panel agreement with humans was 81.0%. Cohen's κ was 0.40 for the panel vs 0.31 between annotators (App. C.2).
   - The brief's own §2.1 TraceDance row reports this.
   - Fix: drop TraceDance from the list, or say its human labels cover 84 next-turn responses for judge validation, not code verifiers.
   - The other three names are correct:
     - TestJack: "Recall and precision in RQ2–RQ4 measure agreement with the per-trial audit rather than with a human-labeled ground truth."
     - ARE-bench: "Independent human annotations are the next step".
     - traj2envs: automatic trial matrix only.
3. **"Only CodeAssistBench" claims (line 201 §2.5 pattern; line 210 CAB row; line 420 §3.3 item 4).** CAB's numbers and quote are correct, but two qualifications are needed (overclaim, low).
   - CAB's 65.7% is the "Recall" column of its Table 7: the share of 210 issue × rater records judged to need no additional condition (34.3% needed one). It is not a per-requirement completeness rate.
   - SessionFarmer measures requirement coverage of statements written from real SWE-chat sessions against a reference ledger (26% / 54% / 75%). The brief cites this itself in §2.1 and §3.2.
   - "Only CodeAssistBench measures omission" is therefore too strong. "Only CodeAssistBench has measured [completeness] for real conversations" holds only through the qualifier "against a human reference", because SessionFarmer's ledger builder is not stated.
4. **Terminal Wrench vs hacker-fixer (line 183; §9.4 UNRESOLVED item 3).** The question "whether these are the same set" is answered by the primary source (citation error, low).
   - The hacker-fixer paper (arXiv 2606.08960, §2) says: "The audit yields 3,632 hack trajectories across 323 hackable environments (16% of tasks): 238 from SETA and 85 from the TerminalBench family (deduplicated across overlapping sub-sources). … We release this dataset as Terminal Wrench".
   - It also says: "The Terminal Wrench dataset is released at https://github.com/few-sh/terminal-wrench with dataset card https://arxiv.org/abs/2604.17596".
   - The dataset card's title says 331 environments, with the same 3,632 hack trajectories.
   - Remaining open point: only the 331 vs 323 count difference is not explained explicitly.

## The 30 statements

Brief line numbers refer to `docs/research_brief.md` as of 2026-11-18.

| # | Brief location | Statement checked | Verdict | Primary-source evidence (fetched 2026-11-18) |
|---|---|---|---|---|
| 1 | L11, L32, L119, L749 | SF Data essay identity: title "Production traces and the future of data"; byline Brandon Guo, Faiz Siddiqi; `<time datetime="2026-10-01">`; four section names; sitemap lists only two URLs; sha256 `9c4e7748…` | ok | Byline and `<time datetime="2026-10-01">October 1, 2026</time>` present verbatim; the four sections are present; `sitemap.xml` lists exactly `/` and `/blog/production-traces/`; sha256 `9c4e77480e2a…` is unchanged. Only change: HTTP `last-modified` is now Mon, 16 Nov 2026 15:58:22 GMT (deploy time; content byte-identical) |
| 2 | L42–43, L31 | V1 and V2 (homepage, intro); footer "© 2026 SF Data"; sha256 `8278cb39…` | ok | Both sentences match exactly; footer matches; sha256 `8278cb39868c…` unchanged. `last-modified` now Fri, 13 Nov 2026 18:20:01 GMT. A first request got a Vercel 403 ("mitigated: deny"); a retry returned 200 |
| 3 | L11, L49 | V8 "Preserving the initial prompt alone may produce a task that rewards precisely the behavior the user rejected." | ok | Exact match. The sentence is in "Turning traces into training data", in the paragraph beginning "The next problem is turning those sessions into reproducible tasks." |
| 4 | L44–48, L50–55 | V3–V7 and V9–V14 (13 sentence strings) with their section attributions | ok | All 13 strings match exactly, including the curly apostrophes in V7 and V14 and "naïve" in V10. Sections: V3–V4 "Why production traces matter"; V5–V12 "Turning traces into training data"; V13 "Building a market for production traces"; V14 "The future of data" |
| 5 | L104, L750, L614 | SessionFarmer: title, 8 authors (Lu, Zeng, Lan, Xu, Bao, Yan, Lin, Ren), arXiv 2611.02440, v1 2026-11-02 only, no venue, CC BY 4.0 | ok | Meta tags match. History has only [v1] Mon, 2 Nov 2026 03:02:59 UTC. The comment holds code and benchmark links only. License is CC BY 4.0; affiliation ByteDance |
| 6 | L104, L501 | Funnel "5,851 sessions and 13,406 checkpoints" → 2,708 clusters → 338 episodes → 242 tasks (61 repos, 14 languages); 375 sessions → 56 TypeScript tasks; ≈4.1% | ok | §3.5: "Starting from an initial pool of 5,851 sessions and 13,406 checkpoints in SWE-Chat, … 2,708 work clusters, … 338 qualified episodes and ultimately 242 verified tasks". Abstract: 61 repositories, 14 languages. "CropEnterprise is curated from 375 developer–agent sessions in the internal TypeScript repository … yielding 56 tasks". 242/5,851 = 4.14% |
| 7 | L104, L377 | Quotes: "consolidates all requirements that remain in effect at the end of the episode"; `superseded_requirements`; "87.6% of tasks rely on requirements added, clarified, or revised in later user turns" | ok | The first quote is in §3. `superseded_requirements` appears in the App. E output schema, and clauses cite `conversation:<event_id>`. The 87.6% quote is in §1 and is "across our reconstructed benchmarks" (CropChat and CropEnterprise). §4.3 operationalises it as "cite at least 1 user turn after the opening message" |
| 8 | L104, L378 | Full coverage 26% / 54% / 75% (first message / first session / full episode) on multi-session tasks; ledger builder not stated | ok | §4.3: "full coverage rises from 26% under First message and 54% under First session to 75% under Full episode on multi-session tasks, and from 49% to 78% on single-session tasks". n = 34 tasks with 516 ledger requirements (App. B.3). The ledger is only "an independent reference requirement ledger constructed from the full episode and gold patch", so UNRESOLVED item 5 stands. RQ1 reran statement authoring only; no tests were built from first-message statements |
| 9 | L104, L396, L403, L608 | Table 3 against "independent gpt-6-astra patch correctness labels" (30 tasks, 87 rollouts per solver); refinement cut FNR by 32–34 pp and raised FPR by 16.2–17.5 pp | ok | Table 3 values: see the note after this table. Caption: "Test suite verdicts evaluated against independent gpt-6-astra patch correctness labels on 30 CropChat tasks … (87 labeled rollouts per solver after excluding 3 uncertain patches)". §4.4 text: "cuts FNR by 34.0 and 32.0 percentage points … increases conditional false-positive rates by 16.2 and 17.5 points" |
| 10 | L395 (§3.2) | "Its Appendix D lists that analysis [initial-request verifiers and their acceptance of what the user rejected] as future use [re-checked]" | **factual_error (medium)** | See Correction 1. App. D lists agent-side analyses and RL use, but no verifier-level counterfactual |
| 11 | L105, L751, L949 | SWE-Together: 11 authors; v1 2026-06-29 is the only version; the HTML shows "date: September 30, 2026" | ok | Authors match (Wu, Zhao, Li, Lee, Zhu, Wu, Yu, Li, Zhang, Fan, Li). Only [v1] Mon, 29 Jun 2026 08:35:15 UTC. The HTML v1 front matter reads "date: September 30, 2026", so UNRESOLVED item 1 is real |
| 12 | L105, L383, L500 | "109 repository-level tasks from 11,260 recorded sessions": DataClaw 2,228→29, Pi-staging 2,397→23, Hyperswitch 784→9, SWE-chat 5,851→48; 0.82% | ok | Abstract quote matches; Table 1 matches cell for cell. 48/5,851 = 0.82%. The paper does not call the 5,851 "v1"; that matches the SWE-chat v1 snapshot (v1 abstract: "6,000 sessions"), so the label is a fair inference |
| 13 | L105, L383, L438, L612 | Quotes "Task correctness measures whether the agent’s final repository state satisfies the coding request, including requirements introduced during the interaction." and "Execution-only scoring can also miss requirements introduced later in the interaction ... or reject valid alternative implementations"; reference patch 73/93 at τ=0.85; Intent Coverage 0.68–0.72; Turing 46% (CI 40.5–51.6), 4 annotators, 312 judgments | ok | Both quotes are in §2. The ellipsis drops "fail to exercise behavior that depends on realistic repository context,". Other figures: "≈78% (73/93) at the τ=0.85 threshold"; six cohorts at 0.70–0.72 plus GPT-5.5 at 0.68; "46% (95% CI [40.5, 51.6]%)", four annotators, 312 judgments. §3.4's "drop about 30% of intents" is approximate: recall is 0.71–0.74 |
| 14 | L106, L752, L614 | Trace2Eval: 8 authors; v1 2026-11-04 only; 20,000 consented, desensitized sessions (June–July 2026) → 14,603 → 300 → 129; arXiv non-exclusive licence; repo name suggests ICLR | ok | Only [v1] Wed, 4 Nov 2026. App. A: "We begin with 20,000 desensitized sessions … between June and July 2026"; the ethics section describes explicit consent. 14,603, 300 and 129 match §3.1. Licence is nonexclusive-distrib. Repo is `anonymous.4open.science/r/TRACE2EVAL-ICLR`. "Preprint" was not found in the HTML (not checked in the PDF) |
| 15 | L106, L388, L603 | Quotes "Each query summary captures the user’s objective and explicit requirements from the interaction", "files created or downloaded as part of the recorded solution are excluded from the initial workspace", "Fragments or continuation requests whose essential context cannot be recovered."; κ Agent–GT 0.173 vs Human–GT 0.542; "Overall usability agreement of 93.0%, compared with 92.9% for humans"; 38/46; 0.9175; +10.05 pp | ok | All quotes match exactly (App. A.1, A.2, the exclusion rule, §4). Table 13 weighted macro mean: Human–GT κ 0.542, Agent–GT κ 0.173 (616 = 56 × 11 pairs). Also "82.6% workspace acceptance rate" (= 38/46) and "mean replay score of 0.9175". The +10.05 pp gain is in the abstract |
| 16 | L206, L829, L614 | PersonaCodeBench: 30 authors; v1 2026-11-03; 231 tasks from five sources incl. SWE-Together (9); 422 evolved requirements; MIT | ok | Thirty authors are listed. [v1] Tue, 3 Nov 2026 23:27:20 UTC. Source table: DeepSWE 64, SWE-bench-Live 45, SWE-Together 9, SWE-bench Pro 61 (the rest Terminal-bench 3); total 231 pairs and 422 evolved requirements. The repo LICENSE is MIT |
| 17 | L206, L385, L609 | "179/874=20.5% of complete native-test passes fail the recorded persona criteria"; "descriptive discrimination, not evidence that all 179 judgments are correct"; 148 judgments: 71.0% (κ 0.473), accept/reject 77.2%, "89.2% precision and 74.5% recall" | ok | App. D.3 has both quotes verbatim, over 1,962 run–task records. App. D.6: blinded review of 148 judgments by two SE experts; 71.0% agreement (κ 0.473); 77.2%; "Satisfied judgments achieve 89.2% precision and 74.5% recall" |
| 18 | L108, L387, L400, L754 | AfterVibe: v1 2026-07-10; 72 tasks over 7 days (122 → 81 → 72); requirements quote; Table 4 pre-change VC 0.0% vs flex 58.0%, wrong 1.4% vs 51.4%; pre-change = parent commit | ok | Authors Paltenghi, Chandra; only [v1] Fri, 10 Jul 2026. Requirements are "whatever is observable from the session (the developer’s prompts, corrections, and accepted behaviors)". Table 4: Pre-change n=69, VC 0.0%, Flex 58.0%; Wrong n=70, 1.4% / 51.4%. Pre-change is "before the task’s code was landed (the parent commit)"; 7-day window; 122 → 81 → 72 |
| 19 | L111, L386, L757 | ARE-bench: v1 2026-11-10; 27 authors; 75 tasks; 1,173 items; Table 8 69.33/69.33/69.78% vs 40.00/31.56/28.44%; quotes "Requirements raised only in later turns and personal preferences are excluded." and "Independent human annotations are the next step"; "any valid alternative passes"; κ 0.717 | ok | [v1] Tue, 10 Nov 2026; 27 authors; abstract: "about 69% … just 28.4% to 40.0%". Table 8 matches (DeepSeek 69.33→40.00, GLM 69.33→31.56, Kimi 69.78→28.44). The three quotes match. Cross-judge κ 0.717 |
| 20 | L166, L382, L396, L799 | VerifierBench: v1 2026-10-19, v2 2026-10-30; "must accept every valid solution and reject invalid ones"; 222 tasks; 45 excluded incl. all 37 Terminal-Bench; 4,993 cases (1,566 PASS / 3,427 FAIL); `overstrict_trap` 504; `base` 222; construction-label quote; 19 models, 10.6–62.1; 87.9–96.0%; Apache 2.0 | ok | History: [v1] Mon 19 Oct 2026, [v2] Fri 30 Oct 2026. All quotes match (abstract; App. C table; the construction-label quote is in §7, Conclusion). Counts match. Scope note: the 87.9–96.0% range is over the nine Pi-harness configurations "in the analyzed records", not all 19 models. App. B: "Original VerifierBench scripts and annotations use Apache 2.0" |
| 21 | L201, L210, L420 | CAB: "86.3% were judged accurate but only 65.7% complete" (663 conditions, 70 issues); judge 65.92% vs 78.28% (κ 0.68); v1 2025-07-14, v5 2026-01-15, NeurIPS 2025 D&B; Apache-2.0; "the only measurement of requirement omission …" | **overclaim (low)**; numbers ok | All numbers, the quote and the dates match. The repo LICENSE is Apache-2.0; the arXiv paper itself is CC BY-NC-ND 4.0. See Correction 3 for the unit of 65.7% and the "only" wording |
| 22 | L125, L455, L765 | SWE-chat paper: 6 authors; v1 2026-04-22; v2 2026-10-01; comment "Accepted at COLM 2026"; CC BY 4.0 | ok | History: [v1] Wed, 22 Apr 2026; [v2] Thu, 1 Oct 2026. Comment and licence match |
| 23 | L125, L494, L609 | Pushback labels: Qwen3.5-9B, accuracy 0.67 four-class and 0.79 binary vs 100 gold; IAA 90 items, κ 0.832; "caution against taking these labels at face value"; corrections ≈35–38% of Claude Code prompts (from a figure) | ok | App. F.2.4 uses Qwen/Qwen3.5-9B. Table 8: qwen-3.5-9b pushback 0.67, binary 0.79, N_gold 100. Table 6: pushback 90 items, 80/90, κ 0.832. The caveat quote matches. Figure 8 ("Turn-level oversight in Claude Code sessions") prints corrections as 36.6% (human-only), 35.0% (collaborative) and 38.2% (vibe coding) of turns, so 35–38% is right, and the values are printed rather than read off bars. Headline rates if needed: pushback 45.7% of turns, interruptions 4.5%, "users interrupt or push back on 50.2% of prompts" |
| 24 | L125, L456–472, L489–492, L603 | Dataset: revision `202b071f…`, lastModified 2026-10-03, `gated: auto`, `odc-by`, username + e-mail shared, gate text, removal and `user_id` quotes; 17,968 sessions, 707 repos, ~69% Claude Code, "This includes 47.7% of sessions", "licenses allow redistribution", abandonment quote; data through 2026-09-04 | ok, with one sub-claim **could not verify** | API: sha `202b071f18e0…`, lastModified 2026-10-03T22:38:39Z, gated `auto`, license `odc-by`. The page shows `gatedProfileSharing` with username and e-mail true, and the gate text and both card quotes verbatim. The card lists sessions 17,968 and repositories 707. Paper v2 confirms "∼69%" (68.8% "in the September version"), the 47.7% sentence (D.3, unambiguous commit-level attribution) and both other quotes. "Data through 2026-09-04" is not stated in v2 or on the card ("January to September, 2026") |
| 25 | L134, L777 | TiGanEval: v1 2026-10-13; "56% of the sampled trajectories have incomplete initial instructions"; 52.49% inferable; 100 SWE-chat trajectories; human-annotated; 53–67 points | ok | Only [v1] Tue, 13 Oct 2026; 7 authors. App. B has the quote verbatim and "52.49% could have been inferred", from 100 randomly sampled SWE-chat trajectories labelled by human annotators. The abstract rounds these to 56% and 52%. "lose 53 to 67 points" |
| 26 | L135, L502, L778 | Requirements After the First Edit: v1 2026-09-02; funnel quote "5,851 raw sessions → 3,553 eligible → approximately 2,060 clean-start reconstructible → 402 … → 921 canonical emergence events"; 437 units; precision 0.78; 93 of 100 | ok | Only [v1] Wed, 2 Sep 2026; 6 authors. The Figure 7 caption matches the quote verbatim. 437 stratified units; precision 0.78; "agrees with 93 of 100"; "approximately 58%". 402/2,060 = 19.5% |
| 27 | L107, L384, L753 | traj2envs: HEAD a09204ed 2026-11-05, v0.1.0, LICENSE added at HEAD; suite 2026-11-06, licence "other"; `build` "replays up to the second user message"; `extend` quote; `MINIMUM_MUTANT_KILL_RATE` 0.6 / 0.5 | ok | GitHub commits page: HEAD `a09204e` "add license", Nov 5, 2026 (still HEAD on 2026-11-18). `pyproject.toml` version 0.1.0. HF API: created and modified 2026-11-06, licence `other`. The `build` phrase is in `docs/how-envs-are-built.md` (code: `trajectory.replay(until_step=second_request)`). The `extend` docstring matches. Constants: `build.py` `MINIMUM_TESTS, MINIMUM_MUTANT_KILL_RATE = 6, 0.6`; `extend.py` `= 5, 0.5` |
| 28 | L396 (§3.2) | "TestJack, ARE-bench, TraceDance and traj2envs have no human candidate labels" | **factual_error (medium)** | See Correction 2. TraceDance (arXiv 2609.33295, [v1] Sun 27 Sep 2026) has human pass/fail labels on 84 evaluated LLM responses (κ 0.40 vs 0.31). The other three are correct |
| 29 | L167, L183, L951 | Hacker-fixer: v1 2026-06-08; "323 (16%) hackable by frontier models given only the task description"; benign pass 76.1% → 65.2%; first 49 environments checked by hand. Terminal Wrench: "whether these are the same set is UNRESOLVED" | **citation_error (low)**; hacker-fixer numbers ok | Only [v1] Mon, 8 Jun 2026; the quote is in the abstract (1,968 tasks); "76.1% → 65.2%"; "We manually verified the first 49 environments". The same-set question is answered by the paper (Correction 4) |
| 30 | L109, L113, L205, L207, L557, L755, L828, L830, §6 L614, §8 L710 | Other dates, versions and quotes for close works: REAP; TellOnce; FeatureLoop; TerminalWorld; RealClawBench; Terminal-Universe; Harbor 0.25.0; "closest works appeared on 2–10 Nov 2026" | ok | See the list after this table |

Table 3 values for row 9 (FPR / FNR / BAcc):

| Solver | Without refinement | SessionFarmer |
|---|---|---|
| terra | 8.1 / 68.0 / 61.9 | 24.3 / 34.0 / 70.8 |
| gpt-5.5 | 12.5 / 80.9 / 53.3 | 30.0 / 48.9 / 60.5 |

Row 30 details:
- **REAP.**
  - History: v1 2026-04-02, v2 04-03, v3 05-10, v4 2026-07-28. Comment "Accepted at ASE 2026 Industry Showcase".
  - The quote "we restrict to single-turn conversations in which a developer provides one prompt and the agent produces code changes without intermediate human feedback" is verbatim (§4).
  - The paper calls this a "deliberate case-study scope choice rather than pipeline-level constraint". "By design" is acceptable wording.
  - Other figures: 132 tasks; 87.00% (κ 0.74, n=100); 86.00% (κ 0.72, n=50); solve rates 42.9–58.2%.
- **TellOnce.**
  - v1 2026-06-11, titled "Getting Better at Working With You: Compiling User Corrections into Runtime Enforcement for Coding Agents". It expands TRACE as "Test-time Rule Acquisition and Compiled Enforcement".
  - v2 2026-10-25, titled "TellOnce: Correcting Coding Agents Once, Improving Their Future Actions"; 11 authors.
  - v2 §4.1: "Task-specific instructions are not stored as lasting rules".
- **FeatureLoop.** v1 2026-10-26, v2 2026-10-29; 61 tasks, 34 repos, five languages; best model 72.1%.
- **TerminalWorld.** v1 2026-05-21, v2 2026-11-04; comment "Accepted at NeurIPS 2026 Evaluations and Datasets Track".
- **RealClawBench.**
  - Versions: v1 2026-06-02, v3 2026-08-28. There is also a v2 dated 2026-06-05 that the brief omits; this is harmless.
  - The quote "request rewriting turns the original user message into a standalone instruction" matches.
  - Table 11: κ 0.748; false-positive "done" rate 0.042 vs 0.210; 281 cases.
- **Terminal-Universe.** v1 2026-09-03.
- **Harbor 0.25.0 (PyPI).** Wheel uploaded 2026-10-25T20:27:25Z; requires Python ≥3.12; license expression Apache-2.0.
- **§6 and §8 dates.** SessionFarmer 11-02, PersonaCodeBench 11-03, Trace2Eval 11-04 and ARE-bench 11-10 all match their v1 dates.

## Additional observations (not counted among the 30)

- **SessionFarmer artifacts are still not public on 2026-11-18.** github.com/bytedance/SessionFarmer returns 404 through WebFetch, and its raw README returns 404. The HF API for ByteDance/SessionFarmer-CropChat returns 401. The residual risk in §3.2 stands.
- **VibeSWEBench.** The ICML 2026 virtual-page abstract matches the brief:
  - "converts authentic human–agent failure sessions into independent single-turn tasks while preserving human-authored corrective signals";
  - 109 tasks; "human-validated test suites with no LLM-as-a-judge component"; best 20.87%.
  - A web search on 2026-11-18 found no arXiv version, so the full text is still unread.
- **SWE-chat headline rates.** If a single "pushback rate" is cited anywhere, use the paper's own figures: 45.7% of turns (≈46% of prompts), and "interrupt or push back on 50.2% of prompts" (abstract: "50% of all turns").
- **SWE-Together HF dataset.** `yifannnwu/SWE-Together` is Apache-2.0 and ungated, as the brief says.
- **CAB and PersonaCodeBench licences.** The repo licences are Apache-2.0 and MIT respectively, as the brief says.
- **Rajan (arXiv 2606.16062).** The numbers used in §3.4 and §6 match: "65 of 105 decisive LLM-generated tests as failing on the gold patch itself, a 61.9% per-augmentation defect rate"; 28.5% (14/49) and 25.0%.
- **Protocol version drift.** `experiments/protocol.md` now reads "v0.3", while the brief cites protocol v0.2 throughout. This is project-record drift, outside this fact check, but the brief's [P §n] pointers should be re-validated against v0.3.
- **GitHub access from this session.** Direct `curl` and `gh` access to github.com is blocked by the session proxy. GitHub facts were checked through WebFetch and `raw.githubusercontent.com`.

## Sources (all accessed 2026-11-18)

- **SF Data:**
  - https://www.sfdata.com/
  - https://www.sfdata.com/blog/production-traces/
  - https://www.sfdata.com/sitemap.xml
- **arXiv abs and HTML pages:**
  - SessionFarmer: https://arxiv.org/abs/2611.02440 (HTML v1)
  - SWE-Together: https://arxiv.org/abs/2606.29957 (HTML v1)
  - Trace2Eval: https://arxiv.org/abs/2611.06506 (HTML v1)
  - PersonaCodeBench: https://arxiv.org/abs/2611.05739 (HTML v1)
  - AfterVibe: https://arxiv.org/abs/2607.09900 (HTML v1)
  - ARE-bench: https://arxiv.org/abs/2611.14364 (HTML v1)
  - VerifierBench: https://arxiv.org/abs/2610.28679 (HTML v2)
  - CodeAssistBench: https://arxiv.org/abs/2507.10646 (HTML v5)
  - SWE-chat: https://arxiv.org/abs/2604.20779 (abs v1 and v2; HTML v2; Figure 8 SVG at https://arxiv.org/html/2604.20779v2/oversight_modes_by_coding_mode.svg)
  - TiGanEval: https://arxiv.org/abs/2610.17757 (HTML v1)
  - Requirements After the First Edit: https://arxiv.org/abs/2609.03028 (HTML v1)
  - REAP: https://arxiv.org/abs/2604.01527 (HTML v4)
  - TellOnce: https://arxiv.org/abs/2606.13174 (abs v1; HTML v2)
  - FeatureLoop: https://arxiv.org/abs/2610.35488
  - Hacker-fixer: https://arxiv.org/abs/2606.08960 (HTML v1)
  - Terminal Wrench: https://arxiv.org/abs/2604.17596
  - TraceDance: https://arxiv.org/abs/2609.33295 (HTML v1)
  - TestJack: https://arxiv.org/abs/2610.10619 (HTML v1)
  - TerminalWorld: https://arxiv.org/abs/2605.22535
  - RealClawBench: https://arxiv.org/abs/2606.03889 (HTML v3)
  - Terminal-Universe: https://arxiv.org/abs/2609.04148
  - Rajan: https://arxiv.org/abs/2606.16062 (HTML v1)
- **Hugging Face:**
  - https://huggingface.co/datasets/SALT-NLP/SWE-chat and https://huggingface.co/api/datasets/SALT-NLP/SWE-chat
  - https://huggingface.co/api/datasets/harness-hub/traj2envs-rl
  - https://huggingface.co/api/datasets/yifannnwu/SWE-Together
  - https://huggingface.co/api/datasets/ByteDance/SessionFarmer-CropChat (401)
- **GitHub:**
  - https://github.com/huggingface/traj2envs/commits/main
  - `raw.githubusercontent.com` files of huggingface/traj2envs at `a09204ed`: `README.md`, `pyproject.toml`, `traj2envs/families/build.py`, `traj2envs/families/extend.py`, `docs/how-envs-are-built.md`
  - amazon-science/CodeAssistBench `LICENSE`
  - MatrAIx-ai/PersonaCodeBench `LICENSE`
  - bytedance/SessionFarmer (404)
- **Other:**
  - https://pypi.org/pypi/harbor/0.25.0/json
  - https://icml.cc/virtual/2026/82740
