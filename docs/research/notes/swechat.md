# Cluster notes: SWE-chat as the primary candidate data source

- Access date for every source below: **2026-11-13 (UTC)**. Publication/version dates are recorded separately in the sources table.
- Conventions: **VERIFIED** = stated by the source (quotes were checked by exact string match, whitespace-normalized, against the downloaded copy; script `scratchpad/verify_quotes.py`, 67/68 candidate quotes matched, the one miss was re-quoted from the exact source lines). **INFERENCE** = my reading, estimate or judgment; the source does not state it.
- Local copies (untrusted data, not part of the repo) live under
  `<scratchpad>/dl/` (`swechat/`, `swechat_card/`, `swechat_tex/`, `swechat_repo/`, `entire_cli_src/`, `entire_docs/`, `entire_example/`, `swetogether_repo/`, `odcby/`).
- Gate respected: no SWE-chat data file was downloaded. The only SWE-chat request that touched a data file was a 4-byte range GET of `repositories.parquet`, which returned **HTTP 401** (gate confirmation). No mirror or derived copy was used to obtain gated content (see section 4 for what was and was not read).
- Process note: this step only created this notes file. No git command was run inside `/home/user/trace-contract`.

---

## 0. Bottom line (short)

1. **SWE-chat is the right primary source, but it is no longer an untouched source for "sessions -> executable tasks".** The SWE-chat v2 paper itself (section 5.2) reports that **SWE-Together** "converts SWE-chat sessions into executable multi-turn tasks", and **SecureForge** "distilled Python tasks from SWE-chat sessions". SWE-Together (Meta, arXiv 2606.29957) built 109 tasks (48 from SWE-chat v1) with a replaying user simulator, deterministic F2P/P2P gates plus an LLM rubric judge, and reference patches reconstructed by "tool_replay". It explicitly names our failure mode ("Execution-only scoring can also miss requirements introduced later in the interaction ... or reject valid alternative implementations") but, in the v1 text I read, it **does not measure** false acceptance / false rejection of verifiers against human-adjudicated candidate patches, and does not use pre-correction code states as negative candidates. That measurement is the remaining gap (INFERENCE, section 10).
2. **The pushback labels are useful filters but are not requirement labels.** `correction` merges "missing context", "misunderstanding", factual errors and "changing requirements/direction/scope". `non_pushback` explicitly includes "routine iteration" (example: "change the button color to blue"). Labels come from Qwen3.5-9B with 0.67 four-class accuracy (0.79 binary) against 100 author-made gold labels. Corrections are about 35-38% of Claude Code prompts by mode (Figure 8, values extracted from the TeX-source PDF).
3. **Exact pre-correction states look reconstructible for Claude Code sessions, from the raw transcripts.** Bounded inspection of one MIT repo's `entire/checkpoints/v1` branch shows that Claude Code `toolUseResult` records for `Edit`/`Write` carry `originalFile` and `structuredPatch` (structure only checked). Entire checkpoint metadata stores **no base commit**; the base must be inferred from the code commit carrying the `Entire-Checkpoint` trailer (parent commit), as SWE-chat's own replay method does. The parquet `conversations.content` is truncated to 10KB for tool results, so exact replay needs `tool_input_json` plus raw `transcripts/*.jsonl` (raw transcripts total about 33 GB).
4. **Expected yield is small (INFERENCE).** SWE-Together converted 48 of 5,851 SWE-chat v1 sessions (0.82%). Our narrower filter (Python + MIT/Apache/BSD + linked commit + exact replay + a correction that adds or overrides a testable requirement + offline tests) plausibly yields tens, not hundreds, of tasks from v2. That is enough for a pilot, but probably not for a large study without other languages or sources.

---

## 1. Sources

| # | Source | URL | Version / publication date | Accessed | Full text read |
|---|---|---|---|---|---|
| P1 | SWE-chat paper, arXiv abstract page | https://arxiv.org/abs/2604.20779 | v1 submitted Wed 22 Apr 2026 17:08:19 UTC (3,861 KB); **v2 Thu 1 Oct 2026 17:58:03 UTC (2,107 KB)** = latest on access date. Comments field: "Accepted at COLM 2026". Subjects cs.AI, cs.CY, cs.SE. Paper license: CC BY 4.0 (license link on abs page). DOI 10.48550/arXiv.2604.20779 | 2026-11-13 | yes |
| P2 | SWE-chat v2 full text (HTML) | https://arxiv.org/html/2604.20779v2 | v2 (1 Oct 2026). sha256 of HTML `a83dab4d...fce948c` | 2026-11-13 | yes, all sections and appendices |
| P3 | SWE-chat v1 full text (HTML), for v1 vs v2 differences | https://arxiv.org/html/2604.20779v1 | v1 (22 Apr 2026) | 2026-11-13 | partially (abstract, section 2, 4.4, ethics, annotation tables) |
| P4 | SWE-chat v2 TeX source (e-print) | https://arxiv.org/e-print/2604.20779v2 | tarball "last modified: Fri Oct 2 01:37:28 2026"; 2,157,785 bytes | 2026-11-13 | figure PDFs used to read figure values (`pdftotext`), `main.tex` grepped |
| P5 | SWE-chat dataset card (README) | https://huggingface.co/datasets/SALT-NLP/SWE-chat (card pre-downloaded at revision `202b071f18e03c79df5a7287565ce2ebc5ee7756`) | Card lists v1 released 2026-04-29 (commit `f66cca9`), v2 released 2026-10-02 (commit `df393df`). sha256 of README `9b7868e9...f5c926c` | 2026-11-13 | yes |
| P6 | HF API metadata for SALT-NLP/SWE-chat | https://huggingface.co/api/datasets/SALT-NLP/SWE-chat and `/tree/<rev>` listings | `sha 202b071f...`, `lastModified 2026-10-03T22:38:39Z`, `createdAt 2026-04-24T15:36:58Z` | 2026-11-13 | yes (metadata only) |
| P7 | HF dataset web page (gate text) | https://huggingface.co/datasets/SALT-NLP/SWE-chat | page shows "Total file size: 47 GB" | 2026-11-13 | gate text only |
| P8 | SWE-chat GitHub repo (analysis code) | https://github.com/SALT-NLP/SWE-chat (shallow clone) | HEAD `8465db2a234dffd02be2e118bf3437771963b095` (2026-10-01, "Add v2 analysis notebook and update documentation"); MIT, "Copyright (c) 2026 SALT" | 2026-11-13 | yes (README, `swechat.py`, notebook outputs) |
| P9 | SWE-chat website | https://www.swe-chat.com/ | "V2 snapshot: data through September 4, 2026" | 2026-11-13 | yes |
| P10 | ODC-BY 1.0 full text and summary | https://opendatacommons.org/licenses/by/1-0/ ; https://opendatacommons.org/licenses/by/summary/ | ODC-By v1.0 | 2026-11-13 | yes (sections 2-4) |
| E1 | Entire CLI source (MIT, "Copyright (c) 2026 Entire Inc.") | https://github.com/entireio/cli (shallow clone of `main`) | HEAD `ce16562b9b5a4d7bdb2d61e172f92934b788337d` (2026-11-12, changelog 0.13.3) | 2026-11-13 | docs `architecture/sessions-and-checkpoints.md`, `architecture/ref-checkpoint-backend.md`, `architecture/checkpoint-scenarios.md`, `security-and-privacy.md`, `KNOWN_LIMITATIONS.md`, `api/checkpoint/metadata.go`, `CHANGELOG.md` (targeted reads) |
| E2 | Entire docs: Session Storage page | https://docs.entire.io/guides/checkpoints/checkpoint-storage.md | page says it was verified against Entire CLI 0.10.2 | 2026-11-13 | yes |
| E3 | Entire docs: CLI checkpoints overview | https://docs.entire.io/cli/checkpoints.md | undated | 2026-11-13 | yes |
| E4 | Entire blog "Introducing Ref-Based Checkpoint Storage" | https://entire.io/blog/introducing-ref-based-checkpoint-storage.md | dated 2026-07-15 | 2026-11-13 | yes |
| E5 | Bounded inspection repo: nuttycc/LuminTime (MIT, "Copyright (c) 2026-present nuttycc") | https://github.com/nuttycc/LuminTime | checkpoint branch `entire/checkpoints/v1` tip `1d5f9af0001622a6cff6fef4dc2ba6b5b14ac36e` (committer date 2026-02-16T18:07:03+08:00); `main` at `01f9a6e0822e9e3011059b2fcfe2a8d8eef41a9e` per ls-remote | 2026-11-13 | structure only (section 6.5) |
| R1 | SWE-Together paper | https://arxiv.org/abs/2606.29957 ; https://arxiv.org/html/2606.29957v1 | v1 submitted Mon 29 Jun 2026 08:35:15 UTC (only version). The HTML body shows "date: September 30, 2026" (discrepancy with the arXiv v1 date; not resolved) | 2026-11-13 | yes (sections 1-5) |
| R2 | SWE-Together HF card | https://huggingface.co/datasets/yifannnwu/SWE-Together | created/modified 2026-07-07, Apache-2.0 | 2026-11-13 | yes (card + API metadata only) |
| R3 | SWE-Together GitHub repo (blobless shallow clone, sparse) | https://github.com/Togetherbench/SWE-Together | HEAD `e9ce8cfcbe2804a959799726f416e63686ea1824` (2026-10-14); Apache-2.0 | 2026-11-13 | README, run plan, file list; one task's metadata files (structure only, then deleted; section 5.1) |
| R4 | SecureForge paper | https://arxiv.org/abs/2605.08382 ; https://arxiv.org/html/2605.08382v1 | v1 Fri 8 May 2026 | 2026-11-13 | targeted (SWE-chat sections, appendix E, I.7) |
| R5 | SWE-INTERACT paper (Scale AI) | https://arxiv.org/abs/2606.30573 ; https://arxiv.org/html/2606.30573v1 | v1 Mon 29 Jun 2026 | 2026-11-13 | targeted (sections 2.1-2.4, SWE-chat mentions) |
| R6 | RealClawBench | https://arxiv.org/abs/2606.03889 | 2026-06-02 | 2026-11-13 | abstract only |
| R7 | Dialogue SWE-Bench | https://arxiv.org/abs/2606.13995 | 2026-06-12 | 2026-11-13 | abstract only |
| R8 | CooperBench paper (context for `CooperBench/swechat-coop`) | https://arxiv.org/abs/2601.13295 | Jan 2026 (per search result) | 2026-11-13 | **not read** (search-result snippet only) |
| H1-H14 | HF derived/mirror datasets (API + card only) | see section 4 | see section 4 | 2026-11-13 | cards only, no data files |

---

## 2. SWE-chat paper (arXiv 2604.20779)

### 2.1 Bibliographic facts (VERIFIED)
- Title (arXiv): "SWE-chat: Coding Agent Interactions From Real Users in the Wild".
- Authors: Joachim Baumann, Vishakh Padmakumar, Xiang Li, John Yang, Diyi Yang, Sanmi Koyejo (Diyi Yang and Sanmi Koyejo marked "Equal advising"). Affiliation line: Stanford University.
- Venue: arXiv comments say "Accepted at COLM 2026"; the dataset card and the GitHub README say "COLM 2026"; the bibtex gives booktitle "Third Conference on Language Modeling". I could **not** confirm acceptance on a COLM-run page (colmweb.org and OpenReview pages fetched without a matching listing; likely JS-rendered). All venue evidence is author-controlled.
- Citation-title discrepancy: the dataset card's bibtex title is "SWE-chat: Real-World AI Coding Sessions in the Wild", while the arXiv and GitHub titles are "SWE-chat: Coding Agent Interactions From Real Users in the Wild". Cite the arXiv title.
- The paper is CC BY 4.0, so short quotes with attribution are unproblematic.

### 2.2 Data collection and consent basis
- VERIFIED (section 2.1): "We build the dataset from public GitHub repositories whose developers have opted into Entire.io’s CLI checkpoint logging, which records coding agent session transcripts on a dedicated branch." "Each checkpoint is linked to a commit with line-level code authorship attribution."
- VERIFIED (Appendix D.1): "Our pipeline discovers Entire-enabled public repositories by querying the GitHub Code Search API and, for each repository, downloads all checkpoint directories from the metadata branch and parses the raw transcripts into structured tables."
- VERIFIED (Ethics statement): "All data in SWE-chat is collected from public GitHub repositories where developers have explicitly opted in to Entire CLI tracking and pushed session logs to public branches." "We only include repositories whose licenses allow redistribution." Also: images attached to prompts are not collected. PII is removed "following the WildChat data processing pipeline" with Presidio (spaCy transformer NER) and then TruffleHog for credentials. "The study procedure was reviewed and deemed exempt by the Stanford Institutional Review Board (IRB)."
- VERIFIED (footnote 1, section 2.2): "For our data analysis, we filter out any data that appears to be generated by automated bots." The analysis code (P8, `swechat.py`) excludes `dayhaysoos/nimbus` as machine-generated prompts.
- INFERENCE: the consent basis is opt-in to **public logging** (installing Entire and pushing checkpoint data to a public repo) plus a redistribution-compatible repo license. No separate research consent from session authors is described. Users may not anticipate that their prompts become a research dataset or a benchmark. For TraceContract's "authorized sessions" framing, SWE-chat counts as publicly released data under ODC-BY with an opt-out (removal) channel, **not** per-user research consent.
- VERIFIED (section 2.1 and Appendix A): selection bias. "Because SWE-chat captures only developers who actively opt into Entire’s public checkpoint logging, the dataset reflects an early-adopter population and may not generalize to all coding agent users; we discuss this and other limitations in Appendix A." And: "If the user abandons the agent’s output entirely, session logs are not committed and thus not captured by our data." About 16% of sessions come from `entireio/cli` (Appendix E.1.5: "At the time of writing, this repository contributes about 16% of all sessions in SWE-chat.").

### 2.3 Size and composition (VERIFIED unless marked)
- v2 (paper, Figure 1 caption and section 2.1): "As of September 2026", 11.6 million logged events, 700+ repositories, 229,000+ user prompts, 2 million tool calls, "more than 54,000 checkpoints", reasoning traces from "more than 6,600 sessions". GitHub README (P8): **17,819 sessions**, **707 repositories**, **229,909 user prompts**, **2,028,951 agent tool calls**. Notebook header: "v2 snapshot with data through September 4, 2026".
- Dataset card v2 row counts: repositories 707; checkpoints 54,918; sessions 17,968; session_logs 17,968; commits 62,333; conversations 11,607,572 (229,909 user prompts); subagent_tasks 546; conversations_subagents 8,673; skill_definitions 3,523; skill_invocations 12,243; context_events 80,958; raw transcripts 17,819; compact transcripts 3,760; subagent transcripts 83. Note: 17,968 session rows vs 17,819 raw transcripts and 17,819 sessions in the paper. INFERENCE: about 149 session rows have no raw transcript or no conversation rows.
- v1 (card version table): 5,851 sessions and 62,544 user prompts. The v1 abstract says "6,000 sessions, comprising more than 63,000 user prompts and 355,000 agent tool calls". Appendix B (v2): repositories grew "from 205 to 707"; Claude Code share fell "from 85% in the April version to 68.8% in the September version". Footnote 2 (v2): "~69%" of data from Claude Code.
- Users: 589 users; "78% of users contribute more than one session"; majority-persona consistency per user 74.5% (Appendix E.3).
- Agents (section 2.1): Claude Code, OpenAI Codex, OpenCode, Gemini CLI, Cursor, GitHub Copilot CLI, Pi, Factory Droid.
- Coding modes (section 3.2): human-only 25.0% of sessions, collaborative 33.9%, vibe coding (>99% agent-authored) 41.1%; on average 55.3% of committed lines are agent-written.
- Prompt intent shares (Figure 19a, read from the TeX-source figure PDF; the text gives some of these): other 31.5%, understand 18.2%, git 12.6%, debug 12.1%, create new code 12.1%, refactor 8.6%, test 4.0%, connect 1.1%.
- Tool calls (Table 5, all 1,996,558 calls; the README and notebook total is 2,028,951, computed with `exclude_repos=False`. INFERENCE: the gap is the excluded machine-generated repo): bash 313,837 (15.7%, includes `sed`), read 294,394 (14.7%), edit 279,413 (14.0%; Edit, MultiEdit, apply_patch), bash:file 245,291 (12.3%), git/gh 208,746 (10.5%), grep 154,160 (7.7%), bash:build 117,014 (5.9%), agent 113,675 (5.7%), write 46,106 (2.3%), mcp 27,327 (1.4%), other 106,067 (5.3%). INFERENCE: shell edits (for example `sed -i` or heredocs) sit inside the large bash share, so Edit/Write replay alone will miss some modifications.
- Appendix E.9: for code-writing prompts, "3.5% of tool calls create a new file from scratch" and "19% of tool calls edit an existing file".

### 2.4 Annotation scheme (VERIFIED from Table 2, Appendix C, F)
Table 2 lists two session-level and two prompt-level annotations, plus repository domain/audience.

| Annotation | Level / input | Labels | Model used (Appendix F.2) | Human IAA (N=90, 2 annotators) | Chosen model vs gold (N=100, Table 8) |
|---|---|---|---|---|---|
| `prompt_pushback` | prompt. Input: "Full conversation transcript preceding the prompt." | correction, rejection, failure_report, non_pushback | Qwen/Qwen3.5-9B (temperature 0.7, top_p 0.8, top_k 20, presence_penalty 1.5) | 80/90 (88.9%), Cohen kappa 0.832. Binary: 85/90 (94.4%), kappa 0.888 | qwen-3.5-9b acc 0.67 (binary 0.79). Best was gpt-5.4: 0.74 (binary 0.83) |
| `user_persona` | session. Input: "Chronological summary of session events with descriptions (conversations & tool calls)." | Expert Nitpicker, Vague Requester, Mind Changer, Other | gpt-5.4-2026-03-05, reasoning_effort low | 71/90 (78.9%), kappa 0.662 | gpt-5.4 acc 0.69 |
| `session_success` | session (0-100). Input: full conversation, tool-call summary, commit info | integer 0-100 (stored as string) | claude-sonnet-4-6 | Spearman 0.757, ICC(2,1) 0.503 | claude-sonnet-4-6 ICC(2,1) 0.60 (best in Table 8) |
| `prompt_intent` | prompt. Input: "Raw prompt text without context." | create new code, refactor, debug, understand, connect, git, test, other | Qwen/Qwen3.5-27B | 68/90 (75.6%), kappa 0.709 | qwen-3.5-27b acc 0.76 |

- Pushback definitions (Appendix F.2.4 prompt, VERIFIED):
  - "correction - The user redirects the agent by providing missing context, correcting a misunderstanding, pointing out factual errors, or changing requirements/direction/scope mid-task."
  - rejection = explicit reject/revert/refuse "without providing a specific correction".
  - failure_report = "the agent's output does not work: bugs, errors, test failures, or broken behavior".
  - "non_pushback - The prompt moves the session forward normally: a new task, building on agent output, asking a question, or routine iteration." Its examples include "change the button color to blue" and "good, also add unit tests".
  - Scope (Table 2): "Classifies non-interruption prompts into pushback categories: correction, rejection, failure report, or non-pushback." Hard interruptions are counted separately.
- Model choice (Appendix F.1): "The only exception is the prompt pushback task, where we defer to the second-best-performing model, since qwen-3.5-9b offers a much better cost-performance trade-off than gpt-5.4-2026-03-05."
- Codebook process (Appendix F.1): "First, two annotators iteratively refined the codebook until they agreed on all labels for 10 data points." Then 90 items were labeled independently for IAA, and disagreements were adjudicated into 100 gold labels. "All annotators are authors of this paper."
- Persona definitions (Appendix F.2.2, VERIFIED): "an Expert Nitpicker corrects HOW the model executes a stable goal; a Mind Changer revises WHAT the goal is." The prompt forces Mind Changer when `distinct_goals` has more than one entry and `goal_changed` is true.
- Session success rubric (Appendix F.2.5): five dimensions (goal completion, final session state, agent efficiency, code and commit quality, user experience), with score bands 90-100 down to 0-9. Table 2 rationale: "Enables identification of failure patterns, helpful as a training signal for reward modeling."
- Caveat (Appendix A, VERIFIED): "We caution against taking these labels at face value and recommend further validation before using them in downstream analyses."
- Discrepancy: Table 6 lists 7 categories for prompt intent, while the label set has 8.
- INFERENCE for TraceContract: (a) `correction` does not separate requirement additions or overrides from context corrections and fact fixes, and requirement additions can also sit in `non_pushback`. Neither label can stand in for "later correction adds or overrides a requirement"; we need our own codebook and human adjudication. (b) With 0.67 four-class accuracy, filtering on `correction` alone will both miss and mislabel candidates. Use it to enrich a sample, not to define a population. (c) Expert Nitpicker (refines HOW) and Mind Changer (revises WHAT) map to two different correction kinds in our design (constraint additions vs goal overrides).

### 2.5 Reported correction and pushback rates (meaning)
- VERIFIED (section 4.4, Claude Code only): "Overall, users push back after roughly 46% of prompts, regardless of coding mode." "Taken together, users interrupt or push back on 50.2% of prompts." The introduction gives "interrupting agents in 4.5% of turns" and "pushing back against agent outputs in 45.7% of turns". Claude Code asks for clarification in 3.0-3.2% of turns, and users interrupt in 3.5-5.2%.
- Figure 8 values (extracted with `pdftotext -bbox` from `figures/oversight_modes_by_coding_mode.pdf` in the TeX source; bar assignment inferred from x-positions and checked by sums of 99.9-100.0%):

| Claude Code turns | Human-only | Collaborative | Vibe coding |
|---|---|---|---|
| Uninterrupted, no pushback | 46.3% | 49.0% | 46.8% |
| Agent asks for clarification | 3.2% | 2.9% | 3.0% |
| User interrupts | 5.2% | 4.7% | 3.5% |
| User pushback total | 45.3% | 43.4% | 46.6% |
| of which correction | 36.6% | 35.0% | 38.2% |
| of which failure report | 7.2% | 7.1% | 7.0% |
| of which rejection | 1.6% | 1.3% | 1.4% |

- What the numbers mean (INFERENCE): they are shares of **Claude Code user prompts labeled by Qwen3.5-9B**, so they are LLM estimates, not human counts. "Correction" covers much more than requirement changes. The headline "50%" in the abstract combines soft pushback and hard interruptions. The v1 paper reported 39% pushback ("Overall, users push back after 39% of turns"); v1 and v2 differ in data and possibly pipeline.
- Persona distribution (Figure 24, read from `figures/annotation_user_persona.pdf`): Expert Nitpicker 39.2%, Vague Requester 32.7%, Other 21.4%, Mind Changer 6.7% of annotated sessions. Section 3.3: Expert Nitpicker reaches 36.7% even in vibe coding; Mind Changer is 4.6% in vibe coding vs 8.0% in other modes.
- Session success (section 4.1 and footnotes 4-5): 87.5% of sessions score 50 or more. The observed mean is 73.2, and would fall to 65.9 / 58.6 / 51.2 if 10/20/30% more sessions were abandoned and scored 0. 88 of 100 human-annotated sessions have a mean human score of 50 or more, with a mean of 78.3. The authors manually inspected the 50 lowest-scored sessions (scores 2-15).

### 2.6 Linking sessions to commits and code states
- VERIFIED (Appendix D.2): attribution comes from the Entire CLI ("computes code attribution at commit time using temporary checkpoints on shadow branches"). For code survival they "analyze three states for all changed files: the base version (parent commit), the agent actions (sequential tool calls), and the committed version." "We reconstruct agentic changes by replaying every file-modifying tool call (e.g., write, edit) in chronological order." Line diffs use `difflib.SequenceMatcher`, with per-line provenance tags base/agent. Caveat: "Note that concurrent changes, where the human and the agent modify the same file simultaneously, may cause the transcript to reflect inconsistent file states and attributions."
- VERIFIED (Appendix D.3): "To combine session-level statistics with commit-level results, we restrict the analyses in Table 3 and Figure 29 to sessions where the commit-level lines can be unambiguously attributed." "This includes 47.7% of sessions."
- VERIFIED (Appendix A): in a manual audit of 100 sampled deletions of agent-authored code, 92 did not reappear in any form, 4 reappeared with few changes, and 4 showed some similarity.
- Numbers (Table 3, all modes excluding human-only): coding efficiency 59.4% (agent lines survived / cumulative agent lines produced) and code survival rate 65.4%. Vibe coding: 65.0% / 69.9%. Collaborative: 55.9% / 62.6%. Section 4.2 adds that agent self-overwrites "typically occur when the user pushes back and instructs the agent to reimplement something before committing."
- INFERENCE: SWE-chat has already implemented, though not released, a "base = parent commit + chronological replay of file-modifying tool calls" reconstruction. That is exactly the mechanism we need for pre-correction states. The 47.7% unambiguous-attribution figure is the best published proxy for "a clean session-to-commit mapping exists".

### 2.7 Benchmarks, RL and downstream use (VERIFIED)
- Section 5.1: "SWE-chat enables the construction of benchmarks grounded in actual developer workflows [60]." The example given is evaluating "whether an agent proposes appropriate next actions given real conversation context". The section also proposes training user simulators on real trajectories. Table 2 calls session success a possible "training signal for reward modeling". No RL environment is built in the paper.
- Section 5.2: "The SWE-Together benchmark [53] converts SWE-chat sessions into executable multi-turn tasks paired with an anchored user simulator, and the SWE-INTERACT benchmark [42] similarly grounds its user simulator in SWE-chat interactions." "For example, SecureForge [25] distilled Python tasks from SWE-chat sessions to show that prompt-based security hardening transfers to unseen developer prompts." Also cited: SLEIGHT-Bench [34] (monitor calibration baseline), Transluce Docent Team [49] (monitor evasion in 1.9% and overselling of task success in 1.8% of sessions), Hitzig et al. [20] (expertise).
- Bibliography (P2): [53] Wu et al. 2026, arXiv:2606.29957; [42] Raghavendra et al. 2026, arXiv:2606.30573; [25] Liu et al. 2026, arXiv:2605.08382; [34] Najt et al. 2026, arXiv:2605.16626; [60] Zhou et al. 2026, "Mind the sim2real gap in user simulation for agentic tasks", arXiv:2603.11245.

### 2.8 Other v2 facts relevant to us
- Security (section 4.3, Table 4): Semgrep on pre/post-commit snapshots gives introduced findings of 0.47 per 1K lines (vibe), 0.12 (human-only), 0.15 (collaborative). INFERENCE: this shows the authors could materialize pre- and post-commit repository snapshots for analyzed commits.
- Low-success example (Appendix C.1, Figure 9): an agent edits the wrong parameter twice despite corrections, and no commit is made. INFERENCE: sessions with no commit exist in the data (they can still be checkpointed via other paths), but they lack a final accepted state.

---

## 3. Dataset card and HF metadata (P5-P7)

### 3.1 Revision, gate, sizes
- VERIFIED (HF API): `sha 202b071f18e03c79df5a7287565ce2ebc5ee7756`, `lastModified 2026-10-03T22:38:39.000Z`, `createdAt 2026-04-24T15:36:58.000Z`, `gated: "auto"`, `gatedProfileSharing {"username": true, "email": true}`, `private: false`, downloads 15,694, likes 167 (counts as of the access date), `usedStorage` 35,795,337,323 bytes. HF commit history (`/api/datasets/.../commits/main`) and datasets-server (`/size`, `/info`) returned **401**, so they are gated too.
- VERIFIED (web page): "You need to agree to share your Hugging Face information to access this dataset". "This repository is publicly accessible, but you have to accept the conditions to access its files and content." The conditions text itself requires login and was **not retrieved**.
- Measured file sizes (HF tree API at the pinned revision; LFS sizes):

| File | Bytes |
|---|---|
| conversations.parquet | 6,424,352,043 |
| commits.parquet | 5,102,596,005 |
| session_logs.parquet | 43,720,308 |
| sessions.parquet | 36,562,091 |
| checkpoints.parquet | 25,471,283 |
| conversations_subagents.parquet | 18,682,699 |
| skill_definitions.parquet | 16,632,141 |
| context_events.parquet | 5,134,608 |
| skill_invocations.parquet | 1,257,672 |
| repositories.parquet | 900,468 |
| subagent_tasks.parquet | 213,250 |
| top-level total (incl. README/.gitattributes) | 11,675,620,003 |
| `transcripts/` (10,000 files) | 15,750,011,060 (median 616,237; p90 3,840,422; max 61,091,645) |
| `transcripts1/` (7,819 files) | 17,475,985,790 (median 641,256; p90 4,765,618; max 52,428,692) |
| `transcripts_compact/` (3,760 files) | 2,024,511,418 |
| `transcripts_subagent/` (83 files) | 63,215,369 |

  INFERENCE: the "~12.8GB" figure in the task brief roughly matches the parquet tables (11.7 GB), not the whole repository. HF shows 47 GB in total, consistent with my sum of about 47 GB. Raw transcripts are split across `transcripts/` and an undocumented `transcripts1/` directory (the card documents only `transcripts/`), so use `session_logs.transcript_path` rather than building paths.

### 3.2 License: ODC-BY 1.0 (P10)
- Card YAML `license: odc-by`; the card's version table gives no other license.
- What ODC-BY permits (summary page, VERIFIED): "To share: To copy, distribute and use the database." "To create: To produce works from the database." "To adapt: To modify, transform and build upon the database." Full text 3.1 says the grant includes commercial use.
- What it requires: attribution for any public use of the database or works produced from it, plus keeping notices intact. Full text 4.2: anyone who publicly conveys the Database or a Derivative Database must do so under ODC-BY, include the license or its URI, and keep notices. Section 4.3 (VERIFIED): "Creating and Using a Produced Work does not require the notice in Section 4.2." However, publicly using a Produced Work requires a notice that content came from the database and is available under ODC-BY (example: "Contains information from DATABASE NAME which is made available under the ODC Attribution License.").
- Database vs contents (section 2.4, VERIFIED): "this License does not cover any rights (other than Database Rights or in contract) in individual Contents contained in the Database." INFERENCE: user prompts (authored by developers), agent outputs, and repository code inside transcripts keep their own rights status. Code stays under each repository's license, and redistributing verbatim prompts or transcripts in a derived benchmark relies on those rights, not on ODC-BY. The funes cards state the same view: "SWE-chat only includes repositories whose licenses allow redistribution; their code in these sessions stays under those licenses."
- INFERENCE: the HF gate (accept conditions, share username and email) is an access condition that sits on top of ODC-BY. Ungated mirrors (section 4) may be license-compatible but bypass the gate. Per our rules we must not use them.

### 3.3 PII and secret redaction
- VERIFIED (card): "We redacted personally identifiable information in all user prompts, assistant responses, subagent prose/task descriptions, and released skills using Microsoft Presidio (named-entity detection) and TruffleHog (secret detection)."
- INFERENCE: tool inputs and tool results (file contents, Bash output) are not listed as Presidio-redacted. Entire's own write-time secret redaction (section 6.4) applies to everything it stores, but its PII pass is opt-in. A derived card (H6, EunsuKim memory stores) reports that notes reconstructed from tool traffic still contain host names, IP addresses, SSH invocations and "in at least one case a plaintext password." Any derived TraceContract artifact needs its own secret and PII scan.
- INFERENCE: Entire's `REDACTED` substitutions inside transcripts can change code literals inside `tool_input_json` and `originalFile`. Replayed code may then differ from the committed code, so we need a replay-vs-commit equality check.

### 3.4 Data removal policy (VERIFIED)
- "If you would like your data removed from SWE-chat, or if you encounter content that is illegal, you may request deletion." The request goes to the contact email on the card (the first author's Stanford address) with `repo_id`, `session_id`, or `turn_id` values and a reason.
- INFERENCE: TraceContract should pin a revision, keep `(repo_id, session_id)` provenance for every derived task, and re-check new releases for removed sessions so removals propagate.

### 3.5 Fields that matter for task reconstruction (VERIFIED from card)
- `repositories.license_type`: "Usable-license classification from the curated license registry". Card note on `checkpoints_repo`: "Only code repos get a row here, so a checkpoints-only repository never appears in this table and never contributes a `license_type`." The registry's values and categories are **not documented** on the card. INFERENCE: since inclusion requires a redistribution-compatible license, copyleft licenses (GPL/AGPL) may be included. Filter on `repo_github_metadata.license.spdx_id` (full GitHub `/repos` response) in addition to `license_type`.
- `checkpoints.commit_link_status`: `linked`, `not_found`, `search_failed`, or `not_searched`. "`not_found` means no linking commit was reachable in the successfully fetched code/PR history; it does not mean the checkpoint made no code changes." Related fields: `checkpoint_backend` (`git-branch` / `git-refs`), `checkpoint_id_format` (hex / ulid), `checkpoint_version` (e.g. `branch-v1`), `imported` (commit-less), `cp_commit_tree_hash`, and `session_file_paths`.
- `sessions.commit_tree_hash`: "Git tree hash the session was recorded against, when present." Other session fields: `branch`, `files_touched`, `prompt_attributions` (per-prompt user/agent lines added/removed, `user_added_per_file`), `first_write_position`, `kind` (empty for normal; e.g. `agent_review`, `imported`), `compact_transcript_delta_only`, `checkpoint_transcript_start`, `user_persona`, and `session_success`.
- `commits`: `patch` (full unified diff), `files_changed`, `numstat`, `agent_changes` (agent file-modification tool calls with `session_id`, `change_position`, `timestamp`), `file_attribution` (`agent_only` / `human_only` / `mixed` per file), `is_agent_author`, and `status` (`ok` / `commit_not_found` / `commit_search_failed`; non-ok rows have NULL `commit_sha`).
- `conversations`: `tool_input_json` ("Full tool input parameters for tool_use rows"), `file_path`, `command`, `turn_type`, `prompt_pushback`, `prompt_intent`, `is_continuation`, and `queue_op_subtype` (including `user_prompt_discarded`, a queued message removed without delivery). `content` is "truncated to 10KB for tool_result".
- Transcripts: "Prefer `transcripts/` for analysis — it is the agent's own complete record; the compact form is derived and lossy (no system turns or reasoning, and parallel tool results may be missing)."
- Stability: "`turn_id` is unique within a release, but not stable across releases." Join on `session_id` across releases. Dedup: "We deduplicate on `session_id`, keeping the record with the highest `output_tokens` (most complete)."

---

## 4. Derived and mirror datasets on HF (public API metadata and cards only; no data files)

Found via `https://huggingface.co/api/datasets?search=` with swe-chat, swechat, swe_chat, swe-together, swe-interact, and secureforge. Unrelated hits: `Suzhen/SWE-Review-Chat` (PR code-review conversations, Apache-2.0, arXiv 2607.13196) and `swechatelangana/chandamama-kathalu` (Telugu stories).

| # | Dataset (created / modified) | License; gated | What the card says | Executable tasks? |
|---|---|---|---|---|
| H1 | `cfahlgren1/SWE-chat` (2026-04-28 / 2026-09-25) | odc-by; **not gated** | VERIFIED: "This is a copy of [SALT-NLP/SWE-chat](https://huggingface.co/datasets/SALT-NLP/SWE-chat) with a `traces` config added as the default, so the Hub's dataset viewer renders sessions as agent traces." v1 counts (205 repos, 5,851 sessions). Slimmed traces: "Claude Code `progress`, `file-history-snapshot`, and `queue-operation` lines and the `toolUseResult` field are removed" | No. **Ungated mirror of gated content: do not use** |
| H2 | `rguan72/swe_chat_transcripts` (2026-04-30 / 2026-05-02) | none stated | YAML only: 25 claude_code + 25 codex_cli rows with features such as `request_body_first_user_message`, `read_only_agent`, `task_seed` | No (no card text) |
| H3 | `CooperBench/swechat-coop` (2026-05-25) | none; no README (404) | File list only: 200 dirs `coop/<owner>_<repo>_task/<id>/f1_f2/` with `agent1.patch`, `agent2.patch`, `agent1_traj.json`, `agent2_traj.json`, `conversation.json`, `eval.json`, plus `config.json` and `summary.json` | **Possibly** (INFERENCE: CooperBench-style two-agent feature tasks on SWE-chat repos). Content not inspected; open question |
| H4 | `alex-remedios/swe-chat-auto-mode` (2026-08-10) | odc-by | Benign monitor false-positive corpus (eval-50 / eval-250 sessions; every context `expected: ALLOW`). VERIFIED: "Upstream is access-gated (auto-approved); this derivative is a re-shaped subset of it." Also: "All sessions are Claude Code (SWE-chat's Codex rows carry no tool calls, and OpenCode's lowercase tool names miss Claude's case-sensitive gates, so both were cut)." | No |
| H5 | `agu18dec/chive-swechat-qwen3.6-27b` (2026-10-12) | odc-by | CHIVE pipeline: real sessions cut at decision points, 30 next-turn samples from Qwen3.6-27B. "The history is the original agent's (off-policy); only the next turn is Qwen's." Card says "**Nothing is executed.**" 567 investigated incidents | No (off-policy next-turn, LLM-judged) |
| H6 | `EunsuKim/swe-chat-memory-stores` (2026-10-13) | odc-by | Reconstructs Claude Code memory files from Read/Write/Edit tool traffic in 5,851 v1 transcripts. Notes that an `Edit` input is "an `old_string`/`new_string` pair — a diff, never a snapshot". Content notice about a plaintext password | No, but a method precedent for file-state reconstruction |
| H7-H9 | `huggingface/funes-swe-chat-pt`, `-pt-e5`, `-zh-e5` (2026-10-22..25) | odc-by | Chunked and embedded sessions (Lance), for example 153 sessions from 7 repos (pt) at revision `202b071f`, and 527 sessions (zh) at `df393df`. VERIFIED: "OpenCode sessions carry tool calls without their results, as in the source." | No |
| H10 | `amkdg/swe-chat-Embeddings` (2026-06-20 / 06-24) | odc-by | 5,830 conversations into 8,663 embedding vectors | No |
| H11 | `yifannnwu/SWE-Together` (2026-07-07) | apache-2.0 | 109 task metadata rows. VERIFIED: "SWE-Together reconstructs the multi-turn loop from real user–agent coding sessions, replaying each with a reactive **user simulator** that asks questions, adds requirements, and pushes back — preserving the original user's intent." Fields include `oracle_intents`, `reference_patch`, `fail_to_pass`, `pass_to_pass`, `completeness_goals`, and `test_manifest` | **Yes, direct threat** (section 5.1) |
| H12 | `verda-research/kimicode_swetogether_traces` (2026-07-13 / 09-01) | apache-2.0 | kimi-code agent traces on SWE-Together tasks (inference-serving workload, no grades) | No (consumer of H11) |
| H13 | `sweinteract/sweinteract` (2026-04-29) | mit | 125 SWE-bench-style issue/PR tasks (dev_python 70, live_python 30, live_multilang 25) | Yes, but **not** from SWE-chat. Its relation to the SWE-INTERACT paper (75 tasks) is unclear |

- INFERENCE: two sets of SWE-chat-derived **executable** tasks exist publicly: SWE-Together (H11 + R3) and possibly CooperBench/swechat-coop (H3, unverified). Note also that the SWE-Together GitHub repo ships per-task `original_session.json` and `oracle_session.jsonl` files (file names seen in the tree), i.e. session content redistributed outside the HF gate. I did not open those files. TraceContract must not use them as a route to SWE-chat content.

---

## 5. Downstream works that convert SWE-chat sessions into tasks (primary sources)

### 5.1 SWE-Together (Wu et al., Meta; arXiv 2606.29957 v1, 29 Jun 2026) — HIGH overlap
- VERIFIED (abstract): "To make real interactions verifiable, we curate 109 repository-level tasks from 11,260 recorded sessions, selecting sessions with recoverable repository states, clear user goals, and observable outcomes."
- Sources (Table 1): DataClaw 2,228 raw sessions -> 29 tasks; Pi-staging 2,397 -> 23; Hyperswitch 784 -> 9; **SWE-chat 5,851 -> 48**. Total 109/11,260 = 0.97%. INFERENCE: 5,851 is SWE-chat v1, and the SWE-chat yield is 48/5,851 = 0.82%.
- Pipeline (section 2.1): deterministic eligibility filter (multiple genuine user messages, concrete agent edits, public and mature repo; "We additionally filter out sessions in which the final change was primarily authored by the human user."), then LLM viability screening ("The viability screen does not evaluate correctness."), then sandboxed task construction by a task-generation agent (clone at pinned commit, find test commands, write tests, build the simulator prompt, audit).
- Verifier (section 2.3): "Task correctness measures whether the agent’s final repository state satisfies the coding request, including requirements introduced during the interaction." Deterministic verifier plus a two-phase agentic rubric judge: "The Phase 1 rubric may consult the original reference patch to identify the behavior of the recorded solution, but the resulting goals are behavioral and are reused unchanged across agents." Weighted goals; pass threshold judge score of at least 0.85.
- The motivation matches ours (section 2.3.1, VERIFIED): "Execution-only scoring can also miss requirements introduced later in the interaction, fail to exercise behavior that depends on realistic repository context, or reject valid alternative implementations."
- Validation reported: the reference patch scores mean judge 0.90 and passes 73/93 (about 78%) of the tasks that have an extractable reference patch (16 of 109 have none). Simulator Intent Coverage is 0.68-0.72 across cohorts. Human Turing test of the simulator: 46% pass rate (95% CI [40.5, 51.6]%), 4 annotators, 312 judgments. **Not found in the v1 text:** human validation of the rubric judge or gates against labeled candidate patches, or false-acceptance / false-rejection rates.
- Task format (R3 file list, Harbor-based): per task `instruction.md` (first user message), `task.toml`, `environment/Dockerfile`, `tests/test.sh`, `tests/test_manifest.yaml` (weighted `F2P` gates, both grep-style "structural" and behavioral, plus `P2P_REGRESSION`), `canonical_goals.json` (goal tiers include `core`, `important`, `anti_gaming`), `oracle_intents.json` (`intent_id`, `source_turn`, `intent_kind`, `text`, `verbatim_excerpt`, `extractor_model`), `reference_patch.json`, `user_simulation_prompt.md`, `original_session.json`, and `oracle_session.jsonl`. Inspecting the metadata of one task (`rudel-task-d1ddb8`; its `_source` field reads `unknown`, so it may not be SWE-chat-derived) showed `commit_sha: null`, `_reconstruction: "tool_replay"`, `_fidelity: "exact"`, `_n_mutating_ops: 5`, `_base_commit` set, and AI reviewers (`subagent-batch-ai`, `round2-batch-ai`). Its task README documents that a later user message specified the desired behavior, and that two behavioral F2P gates (0.25 weight each) check it. Downloaded task files were deleted after recording this structure; no session content is copied here.
- INFERENCE (overlap): SWE-Together already (i) reconstructs tasks from SWE-chat sessions, (ii) preserves later-introduced requirements, through the simulator and in the gates and rubric, (iii) reconstructs reference patches by tool replay when no commit is linked, and (iv) argues that execution-only verifiers miss later requirements. It does not, as far as the text shows: (a) compare initial-request-only vs correction-aware contracts on the same candidates, (b) use pre-correction agent states or near-misses as negative candidates, (c) report verifier false acceptance or false rejection against independent human labels, or (d) test a predefined verifier-audit procedure. TraceContract must position itself as **measurement of reward fidelity**, not as task reconstruction or multi-turn replay.

### 5.2 SecureForge (Liu et al., arXiv 2605.08382 v1, 8 May 2026; includes Baumann, J. Yang, D. Yang) — MEDIUM overlap
- VERIFIED (section 4, "Out-of-Distribution In-the-Wild Security"): "Since our evaluation rolls out models in a zero-shot setting, we collapse multi-turn tasks into self-contained prompts using Claude Sonnet 4.6." "Filtering for user-coding agent interactions based on Python code yields 203 realistic task descriptions." "We manually validated each for reasonable descriptions of the users’ intent."
- Appendix I.7 prompt: preserve every user-stated detail, resolve short replies using agent context, carry forward standing constraints from prior commits, and never leak agent code or invent requirements. INFERENCE: this is a published "full-session correction-aware LLM reconstruction" prompt, and a good template or baseline for our competent full-session reconstruction condition.
- Verification there is security-focused (Semgrep CWE findings plus LLM-generated pytest tests for the synthetic tasks; test provenance for the SWE-chat tasks not established in my read). Appendix E Table 1: 203 tasks; 22 (11%) with at least one introduced finding.

### 5.3 SWE-INTERACT (Raghavendra et al., Scale AI; arXiv 2606.30573 v1, 29 Jun 2026) — LOW-MEDIUM overlap
- VERIFIED: "We adopt 25 tasks from each of three frontier SWE benchmarks (75 total): SWE-bench Pro, SWE Atlas (Refactoring), and DeepSWE [4, 12, 7]." The persona is grounded in SWE-chat: "We first analyzed thousands of real user messages from SWE-chat [3]." It is modeled on Expert Nitpicker in vibe-coding mode. The simulator reveals requirements progressively, and scoring uses the original task verifiers (Harbor). Tasks are not reconstructed from SWE-chat sessions.

### 5.4 Adjacent, not SWE-chat-based (abstracts only)
- RealClawBench (arXiv 2606.03889, 2026-06-02): 281 executable tasks from real OpenClaw sessions with "reconstructed execution environments and deterministic verifiable scorers". Its abstract does not mention SWE-chat. Medium overlap for "sessions -> executable tasks"; should be covered by another cluster.
- Dialogue SWE-Bench (arXiv 2606.13995, 2026-06-12): persona-grounded user simulator for dialogue-driven SWE tasks. Its abstract does not mention SWE-chat.

---

## 6. Entire.io checkpoint format (E1-E5)

### 6.1 Timeline (VERIFIED, `CHANGELOG.md` in entireio/cli @ce16562)
- 0.4.2: 2026-02-10. The SWE-chat paper (E.1.5) dates Entire's public launch to February 10, 2026.
- 0.8.42: 2026-07-08. Ref-based storage ships as opt-in (blog E4, dated 2026-07-15).
- 0.10.0: 2026-08-12. VERIFIED (E2): "Ref-based storage first shipped as an opt-in option in Entire CLI 0.8.42 and became the default in 0.10.0, where `entire enable` writes it during a first-time setup and no longer asks you to choose."
- 0.11.5: 2026-10-14 (after the v2 data cutoff of 2026-09-04). Shadow branches are no longer written, and "Line attribution is removed". VERIFIED: "Checkpoint metadata no longer carries `initial_attribution` or `combined_attribution`". INFERENCE: future SWE-chat releases may lack Entire-computed attribution for new sessions.
- 0.13.3: 2026-11-12 (current).

### 6.2 Storage model (VERIFIED, E1 docs and E2)
- VERIFIED: "A **Checkpoint** is the permanent record of a session's work, linked to a code commit by its `Entire-Checkpoint` trailer." The trailer is added to the code commit message by the prepare-commit-msg hook, for example `Entire-Checkpoint: a3b2c4d5e6f7`.
- VERIFIED: "Work in progress between commits is not written to git at all; it lives in session state and the session's local metadata directory:" (`.git/entire-sessions/<id>.json` holds `BaseCommit`, `FilesTouched`, and touched-file blob hashes; `.entire/metadata/<id>/` holds the local `full.jsonl` and `prompt.txt`). **None of this is pushed.**
- Backends:
  - `git-branch` (legacy, and the default before 0.10.0): branch `entire/checkpoints/v1`, checkpoint subtree at `<id[:2]>/<id[2:]>/`, 12-hex IDs.
  - `git-refs`: `refs/entire/checkpoints/<shard>/<id>`, where shard is the **last two** characters of the ID, ULID IDs (26 chars). Each ref points at a commit whose tree root is the checkpoint.
  - Both backends use the same checkpoint tree: root `metadata.json` (CheckpointSummary), per-session folders `0/`, `1/`, ... with `metadata.json`, `full.jsonl` (sanitized and redacted transcript, chunked when large), `transcript.jsonl` (compact, newer CLIs; skipped above 50MB), `prompt.txt`, `content_hash.txt`, and optionally `tasks/<tool-use-id>/` (subagent transcripts plus `task.json`).
  - Older CLIs also wrote `context.md` (seen in E5).
- Separate checkpoint repo: `strategy_options.checkpoint_remote` (for example, entireio/cli pushes to `entireio/cli-checkpoints` with `primary: git-refs`, from its `.entire/settings.json`). The SWE-chat card reflects this through `checkpoints_repo` and `source_repo_id`.
- `full.jsonl` "holds the whole session up to this checkpoint". `checkpoint_transcript_start` marks where this checkpoint's slice begins. Several sessions can share a checkpoint, and one session can span several checkpoints.
- Visibility: "If your repository is **public**, this data is visible to the entire internet."

### 6.3 What is (not) stored about the base state (VERIFIED from `api/checkpoint/metadata.go` and E5)
- Persisted `Metadata` / `CheckpointSummary` fields include `cli_version`, `checkpoint_id`, `session_id`, `strategy`, `created_at`, `branch`, `files_touched`, `agent`, `model`, `turn_id`, `checkpoint_transcript_start`, `token_usage`, `redaction` counts, `summary`, `kind`, `linked_commits` (attach), and legacy `initial_attribution` / `prompt_attributions`.
- **No base-commit field is persisted.** `BaseCommit` exists only in local session state. `commit_sha` is import-only; the Go comment reads "CommitSHA anchors an imported checkpoint to an existing commit; empty for" / "non-imported checkpoints, which link via the Entire-Checkpoint trailer." (two source lines, `metadata.go` L441-442).
- INFERENCE: the session's starting repository state must be inferred as the parent of the linked code commit (what SWE-chat's D.2 uses), possibly corrected by `commit_tree_hash` when present. This is exact only when (a) the session started on that parent with a clean tree, (b) the agent's edits all landed in that one commit, and (c) no human edits intervened, or they are known via `prompt_attributions` / `file_attribution`. Multi-commit sessions and multi-session checkpoints break (b) (Entire scenarios 3-5: granular agent commits, user splitting commits, `git add -p` partial staging with content-aware carry-forward).

### 6.4 Write-time redaction by Entire (VERIFIED, `security-and-privacy.md`)
- Seven always-on or configurable secret passes (entropy above 4.5, Betterleaks/goredact, provider token shapes, credentialed URIs, DB connection strings, shell-stdin secrets, credential values), plus optional custom and PII passes: "Detected secrets are replaced with `REDACTED` before the data is ever written to a git object." System prompts and instruction-file bodies are blanked in stored Claude Code, Codex and Pi transcripts.
- "Older Entire versions instead wrote local **shadow branches** (`entire/<commit>-<worktree>`) at turn end, whose code-file snapshots were raw, unredacted blobs of your working tree." These were local and not pushed (INFERENCE from "local").

### 6.5 Bounded inspection (one repo): nuttycc/LuminTime (MIT)
- Procedure: `git ls-remote` (82 refs; `refs/heads/entire/checkpoints/v1` present), then `git fetch --depth 1 --filter=blob:none` of that branch only, then `--refetch --filter=blob:limit=1m`. A size check lazily fetched the 3 larger blobs. Total `.git` 2.2 MB, into `scratchpad/dl/entire_example/repo`. No transcript text was copied; only structural field names below.
- Checkpoint branch tip `1d5f9af0001622a6cff6fef4dc2ba6b5b14ac36e`. The commit message carries trailers `Checkpoint: <id>` and `Entire-Session: <uuid>` (values not recorded).
- Tree: 8 checkpoints, 88 files, 16 session folders (one checkpoint holds 8 sessions). Per session: `metadata.json`, `full.jsonl` (130,776 to 2,284,609 bytes), `prompt.txt`, `context.md`, `content_hash.txt` (`sha256:<64 hex>`). CLI version 0.4.2, strategy `manual-commit`, agent `Claude Code`.
- Root `metadata.json` keys: `cli_version, checkpoint_id, strategy, branch, checkpoints_count, files_touched[], sessions[{metadata, transcript, context, content_hash, prompt}], token_usage{input_tokens, cache_creation_tokens, cache_read_tokens, output_tokens, api_call_count}`.
- Session `metadata.json` keys: `cli_version, checkpoint_id, session_id, strategy, created_at, branch, checkpoints_count, files_touched[], agent, token_usage{...}, initial_attribution{calculated_at, agent_lines, human_added, human_modified, human_removed, total_committed, agent_percentage}`. **No base commit, tree hash, or commit SHA.**
- `full.jsonl` (Claude Code native JSONL). Line types: `file-history-snapshot`, `progress`, `user`, `assistant`, `system`. Content blocks: `text`, `thinking`, `tool_use`, `tool_result`.
  - Tool inputs: Edit `{file_path, old_string, new_string, replace_all}`; Write `{file_path, content}`; Read `{file_path, offset, limit}`; Bash `{command, description, timeout}`.
  - **`toolUseResult` for Edit: `{filePath, oldString, newString, originalFile, replaceAll, structuredPatch, userModified}`. For Write: `{type, filePath, content, originalFile, structuredPatch}`.** Read: `{type, file{filePath, content, numLines, startLine, totalLines}}`. `structuredPatch` hunks: `{oldStart, oldLines, newStart, newLines, lines}`.
  - `file-history-snapshot.snapshot`: `{messageId, timestamp, trackedFileBackups{<path>: {backupFileName, version, backupTime}}}`. Backup contents are **not** in the transcript.
- INFERENCE: for Claude Code sessions, raw transcripts carry the full pre-edit file (`originalFile`) at each Edit/Write, and Read results carry file contents. Pre-correction states can therefore be reconstructed and **cross-checked** for exactness without relying only on the git base. Evidence that SWE-chat raw transcripts keep `toolUseResult`: H1's card says its slim copy removed the `toolUseResult` field (this is a mirror card, not a primary statement). Must verify once access is granted.

---

## 7. Feasibility assessment (mostly INFERENCE; known numbers marked)

### 7.1 Funnel for "replayable Python tasks with a requirement-changing correction"
| Filter | Evidence | Expected pass rate |
|---|---|---|
| Repo public and still reachable | All public at collection (VERIFIED); some may be deleted or force-pushed since | High (most), measure with `git ls-remote` |
| MIT / Apache-2.0 / BSD license | Inclusion requires a redistribution-compatible license (VERIFIED). Category split unknown | Unknown; measure via `license_type` and SPDX |
| Python as primary language | Not published. `entireio/cli` (Go) is about 16% of sessions | Unknown; plausibly a minority (INFERENCE) |
| Agent writes code | Human-only sessions are 25.0% (VERIFIED) | about 75% |
| Clean session-to-commit mapping | 47.7% of sessions have unambiguous commit-level attribution (VERIFIED, D.3); `commit_link_status` split unknown | about 40-50% |
| Exact replay possible (Claude Code, no shell edits to the affected files, no concurrent human edits) | Claude Code about 69% of sessions; `toolUseResult.originalFile` present in the format (E5); Codex rows lack tool calls and OpenCode lacks tool results (H4, H9) | Claude Code subset; shell-edit and human-edit losses unknown |
| A later user prompt adds or overrides a **testable** requirement after agent code exists | Corrections are about 35-38% of Claude Code prompts (LLM labels); requirement-adding share unknown | Most multi-turn coding sessions have at least one correction; testable requirement-adding ones are fewer |
| Tests runnable offline after an environment build | Depends on repo; SWE-Together built Docker environments for 109 tasks | Unknown; often the binding constraint |
| Empirical anchor | SWE-Together: SWE-chat v1 48/5,851 (0.82%) with LLM screening, all languages (VERIFIED) | — |

- INFERENCE (rough planning estimate, not a measurement): applying a SWE-Together-like viability rate (about 0.8%) to v2's 17,968 sessions gives about 150 viable sessions in all languages. A Python share of 20-30% and a 50-80% share with a genuinely requirement-adding, testable correction would leave about **15-35 candidate tasks from v2**. A pilot (10-30 tasks) is feasible. A larger study likely needs TypeScript/Go or other sources (DataClaw, Pi), relaxed criteria, or later releases. The first step of the sampling plan measures these rates directly.

### 7.2 Main rejection reasons (expected)
1. Non-permissive or missing license, or a fork. Repo deleted, private, or history rewritten, so the linked commit is unreachable.
2. `commit_link_status != linked`, imported checkpoints (`imported`), review or investigate `kind`, multi-commit sessions, or multi-session checkpoints. The base state is then ambiguous.
3. Agent harness without replayable edits (Codex rows without tool calls, OpenCode without results), compacted-only transcripts, or `compact_transcript_delta_only`.
4. Modifications made via Bash (`sed -i`, heredocs, generated scripts), notebook edits, or binary files. Concurrent human edits (`prompt_attributions.user_lines_*` > 0 on affected files; `file_attribution` `mixed` / `human_only`).
5. Entire `REDACTED` substitutions or SWE-chat truncation changing code, so replay does not equal the commit.
6. The correction is not requirement-bearing (process: "commit/push/run tests"; failure reports without a new requirement; style-only), or it concerns UI or visual behavior that cannot be tested offline.
7. The environment needs network services, GPUs, databases, secrets, or private packages; no test infrastructure; very large monorepos.
8. Overrepresentation: `entireio/cli` (about 16% of sessions) and other dominant repos, so cap the number of sessions per repo.
9. Selection bias: abandoned sessions are not committed, so negative outcomes are under-represented (VERIFIED, Appendix A).

---

## 8. Bounded sampling plan once access is granted (INFERENCE / proposal)

0. **Access and compliance.** Accept the HF gate with a project account (username and email are shared with the authors). Use a read-only token from environment secrets, never in code. Pin `revision=202b071f18e03c79df5a7287565ce2ebc5ee7756` (or the release commit `df393df`) and record it in every derived artifact. Keep the ODC-BY notice and SWE-chat citation. Keep a removal-propagation list keyed by `(repo_id, session_id)`. Do not fetch `cfahlgren1/SWE-chat`, SWE-Together `original_session.json`, or other derived copies.
1. **Read parquet footers first (a few MB).** DuckDB (`INSTALL httpfs; CREATE SECRET (TYPE huggingface, TOKEN ...)`, then `parquet_metadata('hf://datasets/SALT-NLP/SWE-chat@<rev>/conversations.parquet')`) or pyarrow with `huggingface_hub.HfFileSystem`. This gives per-column compressed sizes and per-row-group `session_id` min/max, which tells whether session-filtered range reads can skip row groups. (The DuckDB `hf://` secret and `@revision` syntax must be verified on the installed version.)
2. **Small tables in full (about 107 MB):** `repositories.parquet` (0.9 MB), `sessions.parquet` (36.6 MB), `checkpoints.parquet` (25.5 MB). For `session_logs.parquet` (43.7 MB), take only `session_id, transcript_path, compact_transcript_path` (skip `context_md`, `session_metadata_raw`).
3. **Repository filter:** `is_fork = false`; `license_type` plus `repo_github_metadata->license->spdx_id IN ('MIT','Apache-2.0','BSD-2-Clause','BSD-3-Clause')`; `repo_github_metadata->language = 'Python'`, or `.py` share of `files_touched`; exclude `dayhaysoos/nimbus`; cap `entireio/cli`. Check reachability with `git ls-remote`.
4. **Session filter (from sessions + checkpoints):** `agent = 'Claude Code'`; `kind = ''`; `prompt_count >= 2`; `action_count > 0`; `first_write_position` not null; `.py` in `files_touched`; canonical checkpoint with `commit_link_status = 'linked'` and `commit_count = 1`; single-session checkpoint (`session_count = 1`); `compact_transcript_delta_only = false`. Prefer `prompt_attributions` showing no user lines on target files. Enrich (do not restrict) with `user_persona IN ('Expert Nitpicker','Mind Changer')`. Expect a few hundred to low thousands of candidates (to be measured).
5. **Column-pruned scan of `conversations.parquet` (6.4 GB file; read only small columns):** `session_id, turn_number, conversation_turn_number, turn_type, timestamp, is_continuation, prompt_pushback, prompt_intent, tool_name, file_path, char_count, queue_op_subtype`, restricted to candidate sessions. Estimated transfer is hundreds of MB, not GB (INFERENCE; confirm with footer sizes from step 1). Pick correction candidates: `turn_type = 'user_prompt'`, not a continuation, not a discarded queue op, `prompt_pushback = 'correction'` **plus a random sample of `non_pushback` prompts** (requirement additions hide there), positioned after at least one agent `Edit/Write/MultiEdit/NotebookEdit` on a `.py` file and followed by further agent edits.
6. **Second pass for shortlisted sessions only:** `content` of user prompts and assistant responses around the candidate correction, and `tool_input_json` of all file-modifying tool calls. Run an LLM pre-screen into three classes: adds or overrides a testable behavioral requirement / bug report / process, style, or other. Then two-annotator human adjudication with a codebook (adapt SWE-chat F.2.4 and persona definitions; report kappa).
7. **Raw transcripts, per session (budget: at most 200 sessions and 1 GB; skip files over 20 MB):** download `session_logs.transcript_path` files (median about 0.6 MB, p90 about 4 MB) to recover `toolUseResult.originalFile` and `structuredPatch`, and to segment with `checkpoint_transcript_start`.
8. **`commits.parquet` (5.1 GB, mostly `patch`):** first read `checkpoint_pk, commit_sha, repo_id, commit_index, num_commits, author_date, files_changed_count, total_additions, total_deletions, status, is_agent_author, file_attribution`. Fetch `patch`, or better, clone the repo and diff locally, only for selected commits.
9. **Pre-correction state reconstruction (per selected correction at turn `t_c`):**
   - Base `B` = parent of the linked commit `C`, cross-checked with `commit_tree_hash` / `cp_commit_tree_hash` when present.
   - Replay, in order, all main-agent file-modifying tool calls with `turn_number < t_c` (Edit: unique `old_string` -> `new_string`, honoring `replace_all`; Write: full content; MultiEdit: sequential edits; Codex `apply_patch` if Codex is ever included; subagent edits via `conversations_subagents` or `tasks/`).
   - Exactness checks: (a) each Edit's `old_string` exists exactly once (unless `replace_all`); (b) the replayed pre-edit file equals `toolUseResult.originalFile`; (c) every later Read result agrees; (d) the full replay to the session end equals `C`'s tree on the touched files (allowing documented human edits); (e) no Bash command touched the affected files (regex for `sed -i`, `>`, `tee`, `mv`, `cp`, `git checkout/restore/stash/apply`, `python -c ... open(...,'w')`).
   - Output: `S_pre` = pre-correction state (a naturally observed mistake candidate), `S_post` = committed state (the user-accepted reference, possibly with human edits; label its provenance), and the correction text as the requirement delta.
10. **Stop rules and bookkeeping:** log every rejection reason (section 7.2) with counts for the paper's data-flow figure. Stop at the first 30 adjudicated tasks for the pilot. Store only hashes and IDs of SWE-chat content in the public repo, not transcript text.

---

## 9. Design implications for TraceContract (INFERENCE)
- Position against SWE-Together: the contribution is **verifier reward fidelity under omitted corrections** (false acceptance and false rejection against independent human labels on shared held-out candidates), not reconstruction or replay. Use SWE-Together's design (oracle intents, F2P gates, rubric judge) as a strong "competent full-session" baseline family, and possibly as a source of cross-dataset candidates (respecting licenses and the gate issue).
- The user's own later correction gives natural evidence that `S_pre` was unacceptable, at least on the corrected aspect. This is a natural near-miss that SWE-chat sessions supply directly.
- Do not use `prompt_pushback` as ground truth. Build a requirement-delta codebook covering constraint addition, goal override, clarification of ambiguity, fact or context fix, bug report, and process or style. Validate with two humans. Measure how often `correction` vs `non_pushback` contain real requirement deltas, which is itself a small reportable finding.
- Restrict v1 of the pipeline to Claude Code (exact `originalFile` evidence) and single-commit, single-session checkpoints. Report exactness checks per task.
- Licensing: keep repo code under repo licenses; follow ODC-BY 4.3 notices for produced works; avoid redistributing verbatim user prompts unless needed (paraphrase the contract and keep the original only as a hashed pointer); implement removal propagation.
- Re-scan all derived files (tests, contracts, snapshots) for secrets and PII; SWE-chat redaction does not cover tool content.
- Expect a small N. Pre-register a pilot size, and plan to add a second language or source if the Python yield is under about 20.

## 10. Novelty threats
1. **SWE-Together** (arXiv 2606.29957; HF `yifannnwu/SWE-Together`; GitHub `Togetherbench/SWE-Together`): sessions (including 48 SWE-chat ones) become executable tasks, with later requirements preserved via simulator, gates and rubric, tool-replay reference patches, and an explicit argument that execution-only verifiers miss later requirements. HIGH.
2. **SecureForge** (arXiv 2605.08382): SWE-chat multi-turn sessions collapsed by an LLM into 203 single-turn Python task descriptions that preserve every user-stated detail (a correction-aware reconstruction), manually validated for intent. MEDIUM (for the reconstruction baseline).
3. **CooperBench/swechat-coop** (HF, no card): apparently executable two-agent tasks on SWE-chat repos. Unverified. MEDIUM until inspected through public metadata or paper.
4. **SWE-INTERACT** (arXiv 2606.30573): progressive requirement reveal with a SWE-chat-grounded persona, on existing benchmark tasks. LOW-MEDIUM.
5. SWE-chat itself (§5.1/5.2) advertises benchmark construction and reward modeling from sessions. LOW as a direct threat, but it frames the space.
6. Adjacent (other clusters): RealClawBench (real sessions to 281 executable tasks with deterministic scorers), Dialogue SWE-Bench.

## 11. Open questions
- Exact `license_type` registry values, and the share of MIT/Apache/BSD repos and of Python repos (needs gated access).
- `commit_link_status` distribution, and the share of single-commit, single-session checkpoints in v2.
- Whether SWE-chat raw transcripts keep `toolUseResult.originalFile` unredacted (Presidio or other processing), and how often Entire `REDACTED` tokens touch code.
- What CooperBench/swechat-coop contains and whether it has a paper. What the gate's conditions text says.
- Whether SWE-Together v2 (if any) adds human validation of its judge or false-acceptance analysis. The internal "September 30, 2026" date line suggests a revision exists outside arXiv.
- What fraction of `non_pushback` prompts carry requirement additions (SWE-chat's own examples suggest a non-trivial fraction).
- Whether the authors would share their unreleased replay code (D.2) or the license registry.

## 12. Could not access / limitations
- SWE-chat data files and HF commit history: gated (401), by design. Gate conditions text not visible without login.
- COLM acceptance: not independently confirmed (pages not listing or JS-rendered).
- Figure values (Figures 8, 19, 24) were read from TeX-source PDFs with `pdftotext`. Bar-to-label assignment was inferred from coordinates and checked by sums, not stated in the text. Headless Chrome and ImageMagick SVG rendering failed in this sandbox.
- SWE-Together: read v1 HTML and one task's metadata only. Did not read `original_session.json` or `oracle_session.jsonl` (deliberately). Did not run the benchmark.
- SecureForge and SWE-INTERACT: targeted sections only. CooperBench paper not read. RealClawBench and Dialogue SWE-Bench: abstracts only.
- Entire: read docs and code at one commit (ce16562). The LuminTime inspection used CLI 0.4.2 data (Feb 2026); newer layouts (`transcript.jsonl`, `tasks/`, ULID refs) were read from docs and code, not from data.

## 13. Related-work rows (for the synthesis table)
See the structured summary returned to the orchestrator. The rows cover SWE-chat, SWE-Together, SecureForge, SWE-INTERACT, CooperBench/swechat-coop, alex-remedios/swe-chat-auto-mode, CHIVE x SWE-chat, and RealClawBench (abstract only).
