# Trace2Eval deep read (arXiv 2611.06506)

Cluster: Trace2Eval deep read, for the TraceContract (working name) related-work review.
Access date for every source below: **2026-11-13 (UTC)**. Publication and version dates are recorded separately.
No commits were made as part of this research step.

Conventions in this file:
- "States:" or a quotation means the source says it. "Inference:" or "My check:" means it is my own reasoning or arithmetic, not a claim by the authors.
- Quotations are verbatim, at most 2 sentences, with the section they come from. LaTeX hats are written as W0^, E0^.
- Section numbers refer to arXiv v1 (the only version on 2026-11-13).

---

## 0. Bibliographic record (verified on the arXiv abstract page and PDF metadata)

| Field | Value | Where verified |
|---|---|---|
| Exact title | Trace2Eval: Contextualized Evaluation of Coding Agents from Real-World Traces | abs page, PDF metadata |
| Authors (8, in order) | Ji Shi, Lirong Jie, Lexiao Zou, Yaoming Zhu, Yifan Yang, Xuezhi Cao, Xunliang Cai, Miao Zhang | abs page, PDF p.1 |
| Affiliations | Harbin Institute of Technology, Shenzhen: Ji Shi, Lirong Jie, Lexiao Zou, Miao Zhang. "Independent Researcher": Yaoming Zhu, Yifan Yang, Xuezhi Cao, Xunliang Cai | HTML front matter, PDF p.1 |
| arXiv ID / DOI | arXiv:2611.06506; DOI 10.48550/arXiv.2611.06506 | abs page |
| Version history | v1 only: submitted Wed, 4 Nov 2026 13:36:50 UTC (7,335 KB). No v2 on 2026-11-13. | abs page "Submission history" |
| Subject | Software Engineering (cs.SE) | abs page |
| Licence of the paper | arXiv non-exclusive distribution licence 1.0 (http://arxiv.org/licenses/nonexclusive-distrib/1.0/) | abs page licence link |
| Venue | **None stated.** No journal reference and no comments field on the abs page. PDF running header says "Preprint". 42 pages. | abs page, PDF |
| Venue inference | Inference only: the supporting-material URL is `anonymous.4open.science/r/TRACE2EVAL-ICLR`, and the paper has ICLR-style "Ethics statement" and "Reproducibility statement" sections. This suggests an ICLR submission, which is unconfirmed. | footnote 1, Reproducibility statement |

Model roles the paper states (AI use statement, Appendix A.1, A.2, A.3.2, A.5.1):
- Claude Sonnet 4.6 labels traces and casts admission votes. Query summaries are written in the same labelling step (A.1.1: "We label these real user traces for coding relevance and summarize their user queries."), but the summarization model is not separately named. Inference: it is probably the same model.
- Claude Opus 4.6 runs the file-recovery agents (restorer, mocker, fetcher, validator). It also runs the environment-recovery, environment-tuning, launcher and replay-evaluation agents.
- GLM-5.3-Flash is the rubric judge "in the model comparison" / "for the model panel". The paper does **not** explicitly name the judge model used in the 56-artifact human-calibration study. It also does not name the models behind the static-analysis, runtime and task-classifier evidence agents.
- GLM-5.2 runs the diagnosis, design and review agents that write the revision feedback.
- Candidate harnesses are Claude Code and OpenHands, run "within Terminal-Bench" (§4.1) on "the Terminal-Bench 2.0 execution infrastructure" (A.4.5).

---

## 1. Sources consulted

| # | Source | URL | Kind | Version / pub date | Accessed | Full text read? | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Trace2Eval abs page | https://arxiv.org/abs/2611.06506 | arXiv abstract page | v1, 2026-11-04 | 2026-11-13 | n/a | metadata, abstract, history |
| 2 | Trace2Eval full text (HTML) | https://arxiv.org/html/2611.06506 | paper (LaTeXML HTML of v1) | v1, 2026-11-04 | 2026-11-13 | **Yes**, all sections and appendices A.1 to A.6, converted to text and read in full | Figures 3–5 and 9–12 are not rendered in the HTML |
| 3 | Trace2Eval PDF | https://arxiv.org/pdf/2611.06506 | paper PDF | v1, 42 pp. | 2026-11-13 | Text extracted; pp. 1, 2, 8, 9, 22, 27, 31 viewed as images for Figures 1, 3, 4, 5, 9, 10, 11 | numbers in Figure 11 read from p.31 |
| 4 | Anonymous supporting repo, README | https://anonymous.4open.science/r/TRACE2EVAL-ICLR (files via `https://anonymous.4open.science/api/repo/TRACE2EVAL-ICLR/file/README.md`) | supporting materials | not stated; no version or commit shown | 2026-11-13 | Yes | the web UI URL returned HTTP 401 `{"error":"not_connected"}` to curl because it is a JS app; the API file listing and file downloads returned HTTP 200 |
| 5 | Repo `rubric/score_anchors.md` (+ `.json`) | same API, `rubric/score_anchors.md` | rubric spec | not stated | 2026-11-13 | Yes | 11 dimensions; human and agent anchors |
| 6 | Repo `prompts/login_service/{README.md,r1.txt,r2.txt}` | same API | case prompts | not stated | 2026-11-13 | Yes | the only released task prompts (one case) |
| 7 | Repo `profiles/README.md` | same API | taxonomy documentation | not stated | 2026-11-13 | Yes | I did not download the CSV/MD distribution tables |
| 8 | Asuka-Bench (cited by Trace2Eval) | https://arxiv.org/abs/2606.05920 | arXiv abstract | v1, 2026-06-04; comments: "under review" | 2026-11-13 | **No**, abstract only | shares 3 authors with Trace2Eval |
| 9 | TerminalWorld (cited by Trace2Eval) | https://arxiv.org/abs/2605.22535 | arXiv abstract | v1 2026-05-21; v2 2026-11-04; comments: "Accepted at NeurIPS 2026 Evaluations and Datasets Track" | 2026-11-13 | **No**, abstract only | |
| 10 | BenchJack (cited by Trace2Eval) | https://arxiv.org/abs/2605.12673 | arXiv abstract | v1, 2026-05-12 | 2026-11-13 | **No**, abstract only | |
| 11 | WatchPoint (not cited by Trace2Eval; found in search) | https://arxiv.org/abs/2609.26204 | arXiv abstract | v1, 2026-08-10 | 2026-11-13 | **No**, abstract only | peripheral pointer |
| 12 | Third-party PoC `shimpeiws/spike-trace2eval` README | https://raw.githubusercontent.com/shimpeiws/spike-trace2eval/main/README.md | third-party repo README | `main` branch, commit not recorded | 2026-11-13 | README only | single-case PoC "inspired by" the paper; not a replication |
| 13 | Local Harbor README (read-only reference clone) | /home/user/harbor-framework/harbor/README.md (main@3bf4cb3) | official docs | main@3bf4cb3 | 2026-11-13 | README head only | states "Harbor is the official harness for Terminal-Bench-2.0" |

Searches: WebSearch (standard) for "Trace2Eval contextualized evaluation coding agents real-world traces" found nothing relevant. WebSearch (extended) for `"Trace2Eval" arXiv 2611.06506` found the arXiv pages and some third-party repos. One of them, `rfioly/trace2eval`, only shares the name and is an unrelated "production LLM traces to regression eval" tool. I found no official code repository, project page or OpenReview page.

---

## 2. One-paragraph summary (what the paper is)

Trace2Eval is a pipeline that turns sessions from an unnamed online coding-agent service into evaluation instances x = <q, W0^, E0^>. The service's users consented, and the sessions were desensitized. In x, q is an LLM-distilled user request, W0^ is the pre-interaction workspace recovered by LLM agents, and E0^ is a containerized approximation of the initial environment. Recovery is accepted through **trajectory equivalence**: the recorded tool calls are replayed, and an LLM agent scores whether each replayed output matches the recorded one. Candidate agents run q in the recovered context. A **generic 11-dimension rubric** scores the resulting artifact. An **agentic LLM judge** (GLM-5.3-Flash) applies the rubric using static source evidence plus runtime or rendered evidence. The judge's prompt anchors are "calibrated", meaning they are iteratively rewritten until the judge agrees better with an adjudicated human reference on calibration artifacts. The reported agreement uses "the same 56 generation artifacts". The benchmark has 129 tasks. The headline experiment uses judge-derived feedback to have 19 model-harness configurations revise their artifacts: rescored by the same judge, the mean gain is +10.05 pp, with a maximum of +19.28 pp. There are no training (SFT/RL) experiments, no executable per-task tests, no explicit handling of mid-session user corrections, and no released code or tasks.

---

## 3. Task source

**What kind of trajectories.** The trajectories are real user sessions with coding agents, taken from "online coding-agent traffic". They are not web-navigation, terminal-only or synthetic trajectories. Traces contain tool calls T_t = (u_t, i_t, o_t), meaning tool name, input and recorded output (§3.2).
- §3.1 states: "We collect 20,000 anonymized traces from online coding-agent traffic between June and July 2026 by randomly sampling approximately equal numbers per day, of which 14,603 are identified as code-related and form the population for our distribution analysis."
- The service and platform are **not named**. Table 18 says "Category names are translated from Chinese", and the login-service case prompts say "Chinese portions ... are translated into English" (repo `prompts/login_service/README.md`). Inference: the source is a Chinese-language coding-agent service. Usage-scenario categories include "Shopping – Group Buying", "Food & Drink – Takeout" and "Shopping – Flash / Instant Retail" (Table 18).
- Consent (Ethics statement) states that users "provide explicit consent through signed agreements or informed-consent forms". The data "are desensitized before use".
- The task domain is broad. The 171-category, six-axis taxonomy covers task type (x1: 10 categories, x2: 37), usage scenario (y: 46), technical domain (z1: 10, z2: 51) and user role (w: 17) (§A.6, Table 18).
- In the full traffic table, task-type labels are unassigned for 10,354 of 20,000 sessions (51.77%) on x1 and x2 (A.1.2).

**Selection funnel** (Table 3, A.1.1, A.1.3):
- About 20,000 collected sessions. Claude Sonnet 4.6 identifies coding requests, leaving 14,603 code-related traces (the coding population C).
- Algorithm 1, a distribution-aligned greedy selection with category quotas and a deficit score (Eq. 5), picks 300 candidates (S).
- A second greedy stage picks the final 129 tasks (B). It combines admission-rubric voting (five independent automated keep/remove votes; "At least three agreeing votes determine the initial keep-or-remove decision"; borderline cases go to human reviewers) with semantic deduplication and the same distribution constraints.
- Admission rubric (Table 4), quoted: "Retain: The objective, constraints, and task boundary can be recovered from the interaction. Exclude: Fragments or continuation requests whose essential context cannot be recovered." (Table 4, "Task clarity")
- The rubric also excludes "Trivial edits, pure information lookup, or setup-only requests", cases with "Missing private inputs", and tasks needing "Essential authenticated services, remote systems, or internal platforms" (Table 4).

**Distribution alignment vs SWE-bench** (A.1.4, Table 5, Table 6):
- The SWE-bench comparison set pools 1,531 instances: Verified 500 + Multilingual 300 + Pro public test 731.
- Total-variation distance to the coding population C is 0.0060–0.0232 for the 300 candidates and 0.2287–0.7877 for pooled SWE-bench, across the six axes (Table 6). These distances describe the 300 candidates **before** admission screening, not the final 129.
- Bug fixing is 67.4% of SWE-bench (1,032/1,531), 13.8% of labelled coding traffic (1,046/7,590) and 13.9% of labelled candidates (22/158) (A.1.4).

---

## 4. How tasks and environments are reconstructed

**The instance** (§1), quoted: "Given an anonymized interaction trace τ between a user and a coding agent, Trace2Eval reconstructs a benchmark instance x=<q,W0^,E0^>, where q is the user task distilled from the trace, W0^ is the recovered workspace before the recorded interaction, and E0^ is a containerized approximation of the user's initial execution environment." (§1 Introduction)

**The query q**
- The abstract says the system will "recover the original user query".
- Appendix A.1.1, quoted: "Each query summary captures the user's objective and explicit requirements from the interaction, providing a concise description for subsequent profile labeling and candidate selection." (A.1.1 "Identify coding requests and summarize user queries")
- The summaries are produced in the labelling step, which the paper attributes to Claude Sonnet 4.6 (A.1.1). The summarization model is not separately named. The summarization prompt is **not released**, and the paper reports no validation of q's fidelity. The only related check is the admission criterion "Task clarity" plus human review of borderline admissions (Table 4, A.1.1).
- Released example (repo `prompts/login_service/r1.txt`): the R1 task prompt is one consolidated instruction. It keeps the user's original path (`/mnt/workspace/projects/alita/alita-server`) and ends with the directive "Do not ask any intermediate questions during the development process. Complete the entire project directly." The same directive closes the R2 prompt. Inference from this single released case: candidate execution is one-shot and non-interactive, with no simulated user. Whether every task carries the directive is not stated.

**Workspace W0^** (A.2.1). Agents: restorer, then mocker (per file) and fetcher (per source), then validator, then human review, then a gap-filling agent.
- Quoted: "For files modified during the session, it preserves the observed earlier contents; files created or downloaded as part of the recorded solution are excluded from the initial workspace." (A.2.1 "Restore observed inputs ...")
- Missing contents are inferred under a preservation constraint, Eq. 7: f^ restricted to O_f equals f_obs. Inferred contents "are recorded as inferred rather than directly recovered" (A.2.1).
- §3.2, quoted: "The recovered workspace W0^ excludes artifacts introduced during the session and restores modified pre-existing files to their initial state. Environment recovery similarly separates pre-existing dependencies from changes made during execution." (§3.2)

**Environment E0^** (§3.2 Eq. 1; A.2.2)
- One recovery agent maintains two containers: the current replay state C_{E_t} and the evolving estimate of the initial state C_{E_0}^{(t)}.
- Temporal rule, quoted: "Successful use of a dependency before any installation supports its inclusion in E0^. An explicit later installation instead belongs to the inferred change ΔE_t^ at that step." (A.2.2)
- "Initial requirements are mapped to a supported Linux configuration and packaged into a container" (A.2.2). A launcher agent builds, cold-starts and repairs the container.

**Trajectory equivalence (replay)** (§3.2 Eqs. 2–3; A.2.2)
- Recorded tool calls are replayed in order in the cold-started E0^ with a copy of W0^.
- A replay-evaluation agent (LLM) scores each call: m_t = Judge_replay(u_t, i_t; a_t, o_t) in [0,1].
- ReplayScore is the mean of m_t over the scored calls. Low-scoring calls drive repair, with a replay budget of "typically three attempts", followed by human verification.
- Quoted: "Online traces provide tool observations rather than complete snapshots of the user's workspace and environment. A complete ground-truth state is therefore unavailable for direct comparison, so we assess recovery through the behavior of the reconstructed context." (§3.2)

**What is approximated or assumed**
- Unobserved file contents are LLM-inferred ("mocked").
- The user's OS and platform are mapped to a Linux container. Ten of 143 environment-calibration cases were excluded for unsupported platform or hardware (A.4.2).
- Tasks needing authenticated services or remote/internal systems are excluded at admission.
- Replay equivalence is judged by an LLM, and only over calls with "scored comparisons".
- Inference: equivalence on the recorded tool calls does not establish equivalence for the different actions a new candidate agent will take.

**Execution packaging** (A.4.5): "We package these inputs for the Terminal-Bench 2.0 execution infrastructure (Merrill et al., 2026), using our reconstructed tasks." The paper does not name Harbor. The local Harbor README (main@3bf4cb3) states "Harbor is the official harness for Terminal-Bench-2.0". Inference: Harbor was likely used, but this is unconfirmed.

---

## 5. Mid-trajectory user corrections, feedback, evolving requirements: keyword audit

I grepped the full HTML text (case-insensitive). Counts are hits in the whole document, including references and appendices:

| Term | Hits | What the hits refer to |
|---|---|---|
| correction | 3 | All refer to **recovery repairs** ("verify the corrections" in replay; "human review guiding further corrections" for files). None refer to user corrections. |
| feedback | 76 | Almost all are **rubric/judge-derived revision feedback** (R2), not user feedback. |
| multi-turn / multi turn | 0 | none |
| user turn | 0 | none |
| follow-up | 1 | "after the follow-up edits, the build succeeds" (a candidate agent's edits in A.5.3) |
| clarif | 1 | "clarifications introduced to address observed disagreements" (judge anchors, A.3.1) |
| revis | 58 | R2 revision protocol, human rubric revision, admission |
| requirement | 28 | "delivery requirements", "evidence requirements", the "Requirement implementation" dimension, and "explicit requirements from the interaction" (A.1.1) |
| intent | 2 | "tracks both evolution of user intent and model capability" (§1, at population level) and the Asuka-Bench reference title |
| constraint | 11 | distribution constraints, the preservation constraint (Eq. 7), "objective, constraints, and task boundary" (Table 4), and "Implementation-constraint compliance" (Table 7, 1.5% of rationales) |
| conversation | 1 | the "Conversational Text" taxonomy category only |
| underspecified | 2 | Property (4) in §1, and the Asuka-Bench title |

**Finding (high confidence).** Trace2Eval never discusses or models requirements that users introduce, change or retract **later in a session**, and it never measures whether the distilled q preserves them.
- The closest mechanism is the LLM query summary that "captures the user's objective and explicit requirements from the interaction" (A.1.1). This could incorporate later-stated requirements implicitly, but no procedure, prompt or validation for that is described.
- "Evolution of user intent" and "Dynamism" mean **re-sampling new traffic over time** (population-level drift), not within-session requirement change. Quoted: "...so the evaluation tracks both evolution of user intent and model capability." (§1 contributions)
- The admission rubric explicitly removes "Fragments or continuation requests whose essential context cannot be recovered" (Table 4). Inference: sessions where later turns depend on earlier context may be filtered out unless the summary can absorb that context. The paper does not quantify how many sessions were removed for this reason.
- The R2 "feedback" is machine-generated from the judge's rationales (GLM-5.2 diagnosis, design and review agents), not user corrections from the trace. Quoted: "The revision starts from its first-round artifact in the preserved task environment; reference implementations and adjudicated human scores are not supplied." (A.5.1)
- Intermediate agent states in the trace, which would include any pre-correction code, are **discarded** from W0^ because "files created or downloaded as part of the recorded solution are excluded". They are not used as negative examples.

---

## 6. Evaluator / verifier type

The evaluator is a **hybrid agentic LLM-as-judge** applying a **generic, task-independent 11-dimension rubric**. It does not use executable per-task tests, a reference patch or a per-task requirement checklist.
- The judge's input is "Request + artifact" (Figure 10, PDF p.27).
- A task-classifier agent "select[s] the task-specific rubric and execution setting". A static-analysis agent and a runtime agent ("browser, application, service, script, or desktop workflow") collect evidence. The runtime agent "can configure the execution environment but leaves the candidate's source unchanged". The judge then assigns a grade in {0,1,2} per dimension (A.3.2, Eq. 10).
- There are K = 3 independent rollouts. Per dimension, the aggregates are the mean μ, the rounded label a (round half to even) and self-consistency SC (Eqs. 11–13).
- The artifact score is the weighted mean over applicable dimensions (Eq. 14). The model score is the mean over tasks (Eq. 15).
- Dimensions and final weights (Table 8):
  - Accuracy (50%): requirement implementation 22.5 (static), code execution 20.0 (dynamic), data authenticity 7.5 (dynamic).
  - Code quality (35%): readability 7.5, robustness 10.0, complexity 5.0, repair cost 5.0, architecture 7.5 (all static).
  - User experience (15%): interface and interaction 7.5 (dynamic), information presentation 5.0 (dynamic), feature richness 2.5 (static).
- The requirement check is done by the judge from source evidence. Quoted: "Map every core requirement to its implementation location or identify its absence." (Table 9)
- Agent anchor for a score of 2 (repo `rubric/score_anchors.md`): "All core requirements have corresponding logic; minor nonessential omissions are allowed."
- The feature-richness anchor gives 0 when "Only the minimum requested capabilities are present" (repo anchors). The rubric therefore rewards additions beyond the request, although its weight is only 2.5%.
- Rationale for being reference-free, quoted: "Open-ended coding requests admit multiple valid implementations, so artifact quality must be judged against the user's needs rather than a unique reference solution." (A.3.1)
- Critique of tests, which is relevant to false acceptance by tests. Quoted: "Correctness tests then assess behavior encoded in their checks, while a delivered application can implement tested operations yet omit the controls needed to use them. Such an artifact may satisfy component-level checks without completing the user's workflow." (§1 Introduction)

---

## 7. What "calibrated" means and how calibration is done

"Calibrated" here means **iterative prompt/anchor engineering against human labels**. It is not probabilistic calibration: there are no confidence scores, reliability diagrams or ECE.
- Stage 1, human rubric. Human A and Human B independently grade the same calibration artifacts. Anchors are revised "until high agreement is reached". A third annotator then reviews both sets of scores and rationales together with the artifact and assigns the ground truth g_{i,d} (§3.3, A.3.1).
- Stage 2, judge anchors. Quoted: "Because its scores do not align sufficiently with the human reference, we refine the agent scoring points over multiple rounds while keeping the dimensions, weights, and human reference fixed. The resulting agent anchors specify evidence requirements and decision boundaries learned from these disagreements." (§3.3 "Rubric-level ground truth")
- Why the agent needs more detail, quoted: "Human annotators can use professional experience and task context to interpret broad anchors, including whether a defect is consequential or a design fits the project. The agent needs more detailed guidance on these judgments, with explicit evidence requirements, severity thresholds, and boundary cases." (A.3.1)
- Annotator qualifications (A.3.1): "All annotators hold a bachelor's degree in a computer-related discipline and have at least two years of software development experience." There are three annotator roles (Human A, Human B and the GT adjudicator). The number of distinct people is not otherwise stated.
- Calibration set: "the same 56 generation artifacts" (A.4.3); 616 artifact–dimension pairs (Table 13 text; 56 × 11 = 616). The source of these 56 artifacts is not stated: which tasks, which models, and whether they overlap the 129 tasks.
- **No held-out split is described.** Inference: the agreement in Table 13 and Figure 11 appears to be measured on the same 56 artifacts used to refine the agent anchors, so it is in-sample.
- Weights come from "expert judgments" (number of experts not stated). Rubric dimensions come from a "qualitative analysis of human annotations and the written reasons for preferring one coding output over another" (A.3.1, Table 7).
  - The source and size of that preference-rationale set are not stated.
  - My check: all 13 frequencies in Table 7 are consistent with a denominator of 65 reviewed rationales (or 130, 195, ...). For example, 58.5% = 38/65 and 1.5% = 1/65. This is an inference only.

---

## 8. Evaluator error versus humans: is there any false-positive / false-negative measurement?

**No FP/FN rates, confusion matrix, or false-acceptance / false-rejection analysis is reported.** The reported metrics are listed below.

1. Exact agreement with GT per dimension (Figure 11, PDF p.31; read from the bar labels; Human–GT is the average of the two annotators):

| Dimension | Human–GT % | Agent–GT % |
|---|---|---|
| Requirements | 87.5 | 76.8 |
| Execution | 86.6 | 60.7 |
| Data authenticity | 78.6 | 64.3 |
| Readability | 93.8 | 89.3 |
| Robustness | 78.6 | 82.1 |
| Complexity | 84.8 | 60.7 |
| Repair cost | 68.8 | 50.0 |
| Architecture | 90.2 | 94.6 |
| Interaction | 83.0 | 42.9 |
| Presentation | 76.8 | 58.9 |
| Extra features (feature richness) | 43.8 | 57.1 |

2. Cohen's κ, within-one agreement (W-1) and signed bias vs GT (Table 13). The weighted macro mean row reads:
   - H–H κ 0.341.
   - A–H κ 0.144.
   - Human–GT: κ 0.542, W-1 0.952, bias −0.06.
   - **Agent–GT: κ 0.173, W-1 0.975, bias +0.02.**
   Selected dimensions:
   - Requirement implementation: H–H κ 0.303; A–H κ 0.075; Agent–GT κ 0.188, bias −0.09.
   - Code execution: H–H κ 0.622; A–H κ 0.283; Agent–GT κ 0.287, **bias +0.16** (the judge is more lenient than GT).
   - Data authenticity: Agent–GT κ 0.248, bias +0.16.
   - Readability: H–H κ 0.000.
   - Robustness: H–H κ 0.074; Agent–GT κ 0.000, bias −0.18.
   - Feature richness: Agent–GT κ 0.135, bias −0.23.
   Signed bias is defined as the mean of a − g, "with a positive value indicating more generous automated grades" (A.3.2).
3. "Usability agreement" (zero vs non-zero grade), the closest thing to an accept/reject decision. Quoted: "Overall usability agreement of 93.0%, compared with 92.9% for humans, validates the judge agent's accuracy in identifying artifact usability and supports its use as a partial substitute for human assessment under the rubric, answering RQ2.2." (§4.3) The paper gives no per-dimension breakdown of usability agreement and no split into false accepts and false rejects.
4. Self-consistency across the 3 rollouts is defined but not reported numerically. The paper states: "A consistently repeated grade can still disagree with humans, so self-consistency does not replace human-reference calibration." (A.3.2)

Paper's own reading, quoted: "Agreement varies substantially across dimensions, with lower judge agent accuracy on several criteria requiring runtime or visual interpretation as well as some source-based criteria. These differences motivate complementing exact agreement with chance-corrected measures." (A.4.3)

My reading:
- Agent–GT κ (0.173) is far below Human–GT κ (0.542).
- The comparison also favours humans structurally. GT is produced by an adjudicator who sees Human A's and Human B's grades, so Human–GT agreement is partly built in.
- On "Code execution", the dimension closest to an executable verifier, the judge's exact agreement is 60.7% vs 86.6% for humans, with a lenient bias of +0.16. Inference: this is the kind of error TraceContract calls false acceptance, but Trace2Eval does not frame or measure it that way.

---

## 9. Independent validation (human labels, annotators, agreement), including recovery validation

**Recovery validation (RQ1).** These numbers come from **calibration sets drawn from the 14,603 coding traces**, not from the final 129 tasks. No per-task recovery or replay statistics are reported for the final 129.

| Measure | Value | Source |
|---|---|---|
| Agent–human agreement on whether file recovery is needed | 96/100 (96.0%, Wilson 95% CI [90.2, 98.4]) | Table 10 |
| Cases needing file recovery | 57 of 100 | A.4.1 |
| Workspace reconstruction accepted by human reviewers | 38/46 assessable (82.6%, CI [69.3, 90.9]) | Table 10 |
| Success excluding binary limitations | 38/43 (88.4%, CI [75.5, 94.9]) | Table 10 |
| Unsupported file generation | 0/41 (0.0%, CI [0.0, 8.6]) | Table 10 |
| Inclusion of solution-created files (leakage) | 1/41 (2.4%, CI [0.4, 12.6]) | Table 10 |
| Environments reconstructed and scored | 132/143 (92.3%); 10 excluded for platform or hardware, 1 incomplete | Table 11, A.4.2 |
| Mean replay score | 0.9175 (n=132) | Eq. 17, Table 11 |
| Replay score ≥ 0.8 | 119/132 (90.2%) | Eq. 17 |
| Replay before vs after refinement | 0.8192 → 0.9175 | A.4.2 |
| Single-shot / +Launcher / Full, Hard stratum | .0750 / .5303 / .8209 (Full − Launcher +.2906) | Table 12 (29 cases under +Launcher; 26 scored under Full) |
| Same, Medium stratum | .0000 / .8461 / .9165 (+.0704) | Table 12 |
| Same, Easy stratum | .0000 / .9874 / .9320 (−.0554) | Table 12 |

- The number of human recovery reviewers is not stated.
- The replay-evaluation agent's per-call scores m_t are **not validated against humans**.

**Judge validation.** Two independent annotators plus an adjudicator labelled 56 artifacts × 11 dimensions (§8 above).
- No human labels are reported for the 19 × 129 R1 or R2 model-panel artifacts.
- The feedback gains are therefore **judge-only** measurements.

**Third-party validation.** None found. The `shimpeiws/spike-trace2eval` README describes a single-case proof of concept "inspired by" Trace2Eval on the author's own coding-worker trace. It deliberately departs from the paper: "Do not summarize the full trace into a task." It does not replicate any Trace2Eval number.

---

## 10. Experiments: model panel, feedback revision, ablation, training

**Training: none.** There are no SFT, RL or reward-model training experiments. I found no hits for train / fine-tun / SFT / reinforcement / RL / reward / policy that refer to the authors' own experiments. The only "training" hits are the citation of a rubric survey and the taxonomy category "C.4 ML Training". The "improvement" is **inference-time artifact revision** guided by judge feedback.

**Panel.**
- 19 model-harness configurations: 9 under Claude Code and 10 under OpenHands. Gemini 3.6 Flash with Claude Code was excluded because the gateway does not support Gemini thought signatures (A.4.6).
- R1 is the initial artifact. R2 is the revision after rubric feedback, using the same model, harness and preserved environment (A.4.5, A.5.1).
- Paired bootstrap 95% CIs use 10,000 resamples (A.5.1). Visual reading of Figure 4: all 19 intervals appear above zero.

Table 1, Total (% of max), R1 → R2 (Δ pp):

| Harness | Model | R1 | R2 | Δ |
|---|---|---|---|---|
| Claude Code | DeepSeek-V4-Pro | 76.85 | 96.13 | +19.28 |
| Claude Code | GLM-5.2 | 80.96 | 94.13 | +13.17 |
| Claude Code | GLM-5.3 | 84.76 | 97.29 | +12.53 |
| Claude Code | GPT-5.5 | 78.10 | 89.88 | +11.78 |
| Claude Code | GPT-5.6 sol | 86.23 | 94.87 | +8.64 |
| Claude Code | Kimi-K3 | 78.93 | 88.07 | +9.14 |
| Claude Code | MiniMax-M3 | 76.64 | 91.57 | +14.93 |
| Claude Code | LongCat-2.0 | 82.65 | 92.04 | +9.39 |
| Claude Code | Fable 5 | 92.42 | 97.37 | +4.95 |
| OpenHands | DeepSeek-V4-Pro | 85.72 | 93.75 | +8.03 |
| OpenHands | Gemini 3.6 Flash | 82.89 | 91.76 | +8.87 |
| OpenHands | GLM-5.2 | 84.27 | 95.09 | +10.82 |
| OpenHands | GLM-5.3 | 84.90 | 90.41 | +5.51 |
| OpenHands | GPT-5.5 | 82.86 | 94.62 | +11.76 |
| OpenHands | GPT-5.6 sol | 87.46 | 95.89 | +8.43 |
| OpenHands | Kimi-K3 | 77.54 | 86.16 | +8.62 |
| OpenHands | MiniMax-M3 | 82.40 | 91.97 | +9.57 |
| OpenHands | LongCat-2.0 | 79.52 | 88.18 | +8.66 |
| OpenHands | Fable 5 | 88.98 | 95.91 | +6.93 |

- My check: the mean Δ over the 19 rows is 10.053, which matches the abstract's "10.05 percentage points". The Claude Code mean is 11.53 and the OpenHands mean is 8.72.
- Table 2, task-level outcomes per configuration (Improved / Same / Regressed out of 129):
  - Regressions range from 19 to 34 under Claude Code (14.7%–26.4% of tasks) and from 9 to 30 under OpenHands.
  - For example, Fable 5 under Claude Code: 71 / 24 / 34.
  - Table 2 lists only 9 OpenHands models; Gemini 3.6 Flash is missing although Table 1 includes it.
- Feedback ablation (A.4.7, Table 16). The unguided second pass (U2) "receives the original user request verbatim, without weaknesses, scoring rationales, or additional improvement instructions".
  - My computation over the 19 rows of Table 16: mean ΔU2 = +4.27 pp; mean R2 − U2 = +5.79 pp.
  - Largest R2 − U2: DeepSeek-V4-Pro under Claude Code, +13.50.
- Case study (A.5.3): GLM-5.2 under Claude Code on a Scala/Pekko JSON login endpoint goes from Total 46.97 to 98.49 (+51.52 pp).
  - This Total is an "unweighted mean of the eleven dimensions" (Table 17).
  - Code execution, interface and interaction, and information presentation each go from 0 to 2.
  - The R2 feedback (repo `r2.txt`) asked the model to "add a minimal login page" so the path could be screenshotted. The candidate added a Vue login form.
  - Inference: part of the gain comes from UX dimensions rewarding a front end that the original backend-only request did not ask for. The feedback text itself says "This page is only a demonstration of that path; do not let it overshadow the main task."

---

## 11. Released artifacts, licences, and link checks

- Supporting materials: https://anonymous.4open.science/r/TRACE2EVAL-ICLR.
  - The web UI returned HTTP 401 `not_connected` to curl (JS app). The API listing returned HTTP 200 and showed `.gitignore`, `README.md`, `profiles/` (taxonomy and online/SWE-bench distributions in CSV, MD and LaTeX), `prompts/login_service/` (r1/r2 in txt and tex, README) and `rubric/` (score_anchors in md, json and tex).
  - The README states: "This version contains the workflow documentation and the supporting specifications listed above. It does not include the executable pipeline or task workspaces."
  - **No LICENSE file** is in the listing, and no licence is stated for the materials.
- The Ethics statement says: "The public supplementary materials contain methodological documentation, rubric specifications, profile summaries, and selected case prompts; the full source-traffic collection is not included."
- **Not released:** the traces, the 129 tasks (q, W0^, E0^), the recovery and judge pipeline code, human labels (A, B, GT), model artifacts, and judge outputs. Only one case's prompts (login service) are public.
- Links that resolved on 2026-11-13: the arXiv abs, HTML and PDF pages; anonymous-repo API files `README.md`, `rubric/score_anchors.md`, `rubric/score_anchors.json`, `prompts/login_service/README.md`, `r1.txt`, `r2.txt`, `profiles/README.md` and `.gitignore` (all HTTP 200).
- I did not check the model-card links in Table 1 (Hugging Face and vendor documentation). They are not needed for this comparison.

---

## 12. Stated limitations (verbatim)

- "Although judge agents achieve agreement comparable to human annotators on several dimensions, human–agent agreement still leaves room for improvement. We are refining the judge agents to improve consistency with human assessments." (§5 Limitations)
- "In addition, the file and environment recovery workflow occasionally produces task packages that lack core files even after human verification. Such omissions can obstruct subsequent agent execution, highlighting the need for further checks on the completeness of recovered workspaces." (§5 Limitations)
- "The benchmark reflects a specific traffic population and expert-defined criteria, so its scores characterize artifact quality in that setting rather than universal user preferences or individual developer ability." (Ethics statement)
- "These calibration results support partial replacement of manual annotation with calibrated agent scoring. Because our evaluation centers on user experience, human review remains important for nuanced, context-dependent quality judgments." (A.4.4 "Overall agreement")

---

## 13. My critical observations (my analysis; not stated by the authors)

1. **The dimension-level Tables 14 and 15 look derived rather than measured.**
   - In all 38 rows (19 configurations × R1/R2), the within-group differences between dimensions are constant:
     - Exec = Req − 2.0 and Data = Req − 1.3 or −1.4.
     - Rob = Read − 2.2, Complex = Read − 0.4, Repair = Read − 1.8 and Arch = Read − 0.2 or −0.3. The only exceptions are near the 100 ceiling, for example GLM-5.3 and Fable 5 R2 under Claude Code.
     - Present = Interact + 1.6 and Richness = Interact + 2.8.
   - The **unweighted** mean of each group's dimensions reproduces the Table 1 group score within 0.05 in every row.
   - The **weighted** means that A.3.2 says are used ("Group summaries use the same weighted calculation...") deviate systematically. For example, UX comes out 0.42–0.51 lower than Table 1.
   - The paper does not explain this pattern. Treat the per-dimension breakdowns of model results as unreliable. The scripts I used are in the scratchpad: `/tmp/claude-0/-home-user-trace-contract/3951c995-db7e-5b4e-a703-97e326bb42c5/scratchpad/scripts/check_tables.py` and `.../scripts/cmp_t1.py`.
2. **The feedback evaluation is circular.**
   - The same judge (GLM-5.3-Flash) and rubric produce the R1 diagnoses, the GLM-5.2-written feedback derived from those diagnoses, and the R2 scores.
   - No human scored R2 artifacts. The +10.05 pp is therefore evidence that models can satisfy the judge's stated criticisms. It is not independent evidence of user-wanted improvement.
   - The unguided ablation controls for "another pass", but not for "teaching to the judge".
3. **Judge calibration is in-sample** (see §7). No held-out artifacts are described.
4. **The generic rubric can reward behaviour outside the request.** Feature richness scores 0 when only the requested capabilities exist. The UX dimensions reward rendered interfaces. The login-service case shows a front end added for a backend-endpoint request, with UX grades going from 0 to 2.
5. **RQ1 numbers do not describe the benchmark.** They come from calibration subsets (100 and 143 cases from the coding population), not from the 129 released-in-name tasks.
6. Minor issues: Table 2 omits Gemini 3.6 Flash under OpenHands. The paper does not name the judge model used in the human-calibration study.

---

## 14. Comparison with TraceContract

TraceContract's proposal, as given to me:
- Convert authorized coding-agent sessions into executable tasks.
- Preserve requirements introduced through later user corrections.
- Measure reward fidelity, meaning false acceptance and false rejection, of verifiers. The design is 2×2: {initial-request-only vs full-session correction-aware contract} × {ordinary generated tests vs tests with a predefined verifier-audit procedure}.
- Add existing repository tests and a full-session LLM reconstruction baseline.
- Score all verifiers on the same held-out candidate patches: pre-correction states, near-misses and valid alternatives. Labels come from independent human adjudication.

**What Trace2Eval already covers (do not claim as new):**
- Building executable, containerized coding tasks from real, consented user–coding-agent sessions. This includes recovering the pre-interaction workspace (excluding session-created files and restoring modified files) and the initial environment (temporal dependency inference).
- Validating reconstruction by replaying recorded tool calls ("trajectory equivalence"), plus human review, with acceptance statistics.
- Summarizing the session into a task request that, by its description, captures "the user's objective and explicit requirements from the interaction". This is an LLM, full-session-style reconstruction, roughly TraceContract's "competent full-session LLM reconstruction baseline".
- Arguing that tests can accept artifacts that do not complete the user's workflow, and that open-ended requests admit multiple valid implementations. These are the same motivations as false acceptance and false rejection.
- Checking an automated verifier against independent human labels: 2 annotators plus an adjudicator, κ, signed bias (leniency), and zero-vs-nonzero "usability agreement" that approximates accept/reject.
- A predefined, multi-agent evidence-collection procedure (static plus runtime) run before judging. This is loosely analogous to a predefined audit procedure, but it audits the artifact, not the verifier.
- Using verifier output as feedback, together with a control condition (unguided second pass).

**What is genuinely different in TraceContract:**
1. **Correction preservation as an explicit object of study.**
   - Trace2Eval has no notion of mid-session corrections. It never separates initial from later requirements and never measures what the summary drops.
   - It may filter out "continuation requests" at admission.
   - TraceContract's initial-only vs correction-aware contract contrast has no counterpart.
2. **Verifier type.**
   - Trace2Eval uses a generic-rubric LLM judge with no executable per-task tests.
   - TraceContract compares executable behavioural tests (generated vs audited) and existing repository tests against human labels.
3. **Error metric.**
   - Trace2Eval reports agreement statistics (exact, κ, W-1, bias, usability agreement) on graded dimensions.
   - TraceContract measures task-level false acceptance and false rejection against "what the user wanted", including corrections.
   - Trace2Eval reports no confusion matrix and no FA/FR.
4. **Candidate set.**
   - Trace2Eval's human-labelled set is 56 "generation artifacts". Their origin (tasks, models) is not stated, and they were not designed to probe verifier errors.
   - TraceContract uses a fixed, held-out candidate set designed to probe verifier errors: naturally observed pre-correction states, which Trace2Eval discards; constructed near-misses; and valid alternatives. Every verifier condition scores the same candidates.
5. **Valid alternatives are measured, not assumed.** Trace2Eval asserts that reference-free rubrics accommodate multiple valid implementations but never tests false rejection on known-valid alternatives.
6. **Held-out evaluation of the verifier.** Trace2Eval's judge agreement appears to be in-sample.
7. **Openness and reproducibility.**
   - Trace2Eval releases no pipeline, tasks, traces or labels. Its data comes from an unnamed, closed service, and its materials have no licence.
   - TraceContract aims to be a reproducible system on authorized sessions.
8. **Reward definition.** Trace2Eval's rubric encodes expert-weighted generic quality, which rewards extra features and UI. TraceContract's reward fidelity is relative to the individual user's (corrected) requirements.

**The strongest argument that TraceContract is already covered by Trace2Eval:**
1. Trace2Eval already does the hard part of "sessions → executable tasks" on real coding-agent traffic, with validated environment recovery.
2. Its q is already a full-session LLM reconstruction of the user's objective and "explicit requirements from the interaction". A competent summarizer would carry corrections into q, which makes the "correction-aware contract" arm the default behaviour of existing work.
3. It already validates its verifier against adjudicated human labels and quantifies leniency (signed bias) and accept-like decisions (usability agreement: judge 93.0% vs human 92.9%).
4. It already argues the test-vs-workflow false-acceptance problem and the multiple-valid-implementations problem.

On this reading, TraceContract would be "Trace2Eval with tests instead of a rubric judge plus an ablation". The novelty would reduce to:
- (a) swapping the verifier type, and
- (b) an ablation of an implicit property (whether q contains corrections).

**Rebuttal, i.e. why the argument does not fully hold, given what the paper actually reports:**
- Trace2Eval never measures whether q contains later corrections. It provides no initial-only control and never reports a verifier error caused by omitted requirements. Its "evolving intent" is population drift.
- Its human validation measures dimension-grade agreement on 56 artifacts (apparently in-sample; no held-out split is described), not acceptance errors on a held-out, adversarially designed candidate set with valid alternatives.
- It has no executable verifiers to audit.

TraceContract's contribution therefore has to be framed as **measuring** reward fidelity under correction omission, with executable verifiers, a verifier-audit procedure, and held-out human-labelled candidates. It must **not** be framed as trace reconstruction, environment recovery, or human-calibrated evaluation per se.

---

## 15. Design implications for TraceContract

1. Cite Trace2Eval as the closest prior work for trace → executable coding task from real sessions. Explicitly cede the following:
   - workspace recovery: exclude session-created files and restore modified files to their earlier observed state;
   - environment recovery: temporal dependency inference;
   - replay-based trajectory equivalence;
   - human-calibrated LLM judges.
2. Make the full-session LLM reconstruction baseline **Trace2Eval-like**: a single LLM summary of "objective and explicit requirements from the interaction", with no correction-specific extraction. TraceContract's correction-aware contract then has to beat a fair version of Trace2Eval's q. Report how often that summary drops or contradicts corrections.
3. Add a Trace2Eval-style generic-rubric judge as an extra verifier column if budget allows, or at least discuss it. Report Trace2Eval-compatible metrics (exact agreement, Cohen's κ, signed bias, zero-vs-nonzero agreement) **in addition to** FA and FR, so results can be compared.
4. Keep the verifier-calibration/audit development set strictly separate from the held-out evaluation candidates, avoiding Trace2Eval's apparent in-sample calibration. Do not evaluate improvements with the same verifier that generated the feedback.
5. Use the pre-correction code states that Trace2Eval discards from W0^ as naturally observed negative candidates. Watch for leakage: Trace2Eval found solution-created files in 1/41 workspaces.
6. Record admission and exclusion reasons. Trace2Eval's "continuation requests" exclusion could remove exactly the correction-bearing sessions. Report how many sessions are lost and why.
7. Specify interaction policy explicitly. Trace2Eval's released prompt forbids intermediate questions. Say whether TraceContract's contract represents clarifications and corrections as requirements, and whether candidates may ask questions.
8. For execution, Trace2Eval used Terminal-Bench 2.0 infrastructure with Claude Code and OpenHands. Packaging TraceContract tasks in Harbor/Terminal-Bench format, using the local `harbor-framework/harbor` and `terminal-bench` clones, would ease comparison. That Trace2Eval used Harbor specifically is inferred, not stated.
9. Validate the replay/equivalence judge, which Trace2Eval did not, if TraceContract uses any LLM-judged equivalence for environment acceptance.

---

## 16. Open questions (not answerable from the released materials)

1. What are the exact prompt and model used to construct q? Are later user turns and corrections merged, overridden or dropped?
2. What is the distribution of user turns per trace, and how many traces contain corrections?
3. How many of the 300 candidates were excluded as "continuation requests" or "fragments"?
4. Where do the 56 calibration artifacts come from (tasks, models)? Do they overlap the 129 tasks? Was any held-out evaluation done? Which judge LLM was used in calibration?
5. What are the source and size of the human preference rationales behind Table 7? My inference is n = 65 or a multiple.
6. Why do Tables 14 and 15 show constant within-group offsets? Were the dimension scores measured?
7. Were the per-call replay scores m_t validated against humans? How many of the 129 final tasks passed replay, and at what scores?
8. Will the tasks, pipeline, labels or traces ever be released, and under which licence? Is this an ICLR 2027 submission?
9. Is the R2 improvement confirmed by humans? No human evaluation of R1 or R2 panel artifacts is reported.
10. What does "three samples for each configuration" (A.4.6) refer to: three candidate runs or three scoring rollouts? Variability numbers are not reported.

---

## 17. Not accessed / not verified

- The anonymous-repo web UI page (HTTP 401 to curl). Content was retrieved through its file API instead. I did not download `profiles/*.csv`, `profiles/*.md` distribution tables or the LaTeX sources.
- No pipeline code, tasks, traces or human labels exist publicly, so no numbers could be re-derived from raw data.
- Figures 3, 4, 5, 9, 10, 11 and 12 are absent from the HTML. Figure 11 values and Figure 3–5 content were read visually from the PDF. The Figure 4 CI bounds are approximate visual readings.
- I found no OpenReview page and did not search further for one.
- Asuka-Bench, TerminalWorld, BenchJack and WatchPoint were read at **abstract level only** (see §18).
- I did not check the model-card links in Table 1.

---

## 18. Pointers from Trace2Eval's related work relevant to TraceContract (abstract-level only)

- **Asuka-Bench** (arXiv 2606.05920; v1 2026-06-04; comments "under review").
  - Authors include Yaoming Zhu, Xuezhi Cao and Xunliang Cai, all of whom are also Trace2Eval authors.
  - Abstract: "Users seldom write a full spec at the start; many requirements only become clear once they look at an intermediate result and react to it."
  - Design: 50 web tasks, 784 evaluation criteria and 2,402 expected outcomes. "a User LLM turns evaluation outcomes into natural-language feedback for the next round". UI-agent test cases run on the deployed site. 8 LLMs × 2 agent frameworks. The strongest model completes 52% of projects after three rounds.
  - Relevance: high for the "requirements emerge mid-session" framing, but its feedback is simulated by an LLM from evaluation outcomes. The abstract does not say whether its tasks come from real traces. Needs a deep read by the relevant cluster.
- **TerminalWorld** (arXiv 2605.22535; v1 2026-05-21, v2 2026-11-04; "Accepted at NeurIPS 2026 Evaluations and Datasets Track").
  - It "reverse-engineers high-fidelity evaluation tasks from 'in-the-wild' terminal recordings".
  - 80,870 recordings yield 1,530 validated tasks, plus a manually reviewed Verified subset of 200.
  - The best pass rate is 62.5%, with Pearson r = 0.20 against Terminal-Bench.
  - Trace2Eval describes it as using executable tests. Relevance: trace → executable-test tasks, terminal domain.
- **BenchJack** (arXiv 2605.12673; v1 2026-05-12).
  - An automated red-teaming and benchmark-audit system for reward hacking with an "Agent-Eval Checklist".
  - Covers 10 benchmarks and 219 flaws, and reduces the hackable-task ratio from near 100% to under 10% on four benchmarks.
  - Relevance: verifier-audit procedures and false acceptance.
- **WatchPoint** (arXiv 2609.26204; v1 2026-08-10; not cited by Trace2Eval).
  - A simulated-user system that runs diagnostic scripts against the live app to produce retry feedback on Web-Bench.
  - Recovers 57.6% of the tasks it diagnoses, vs 54.5% for human testers.
  - Relevance: low to medium. It concerns executable feedback, not trace reconstruction or verifier fidelity.
