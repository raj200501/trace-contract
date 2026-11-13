# Cluster notes: industry problem statement (SF Data / San Francisco Data)

- Access date for every source below: **2026-11-13 (UTC)**. Publication/version dates are recorded separately.
- Scope: **public statements only**. Nothing here describes or guesses at any private implementation. Non-research content (business metrics, team background beyond research outputs, employment terms, application instructions) is intentionally not recorded.
- Retrieval: all pages were static HTML or JSON and were fetched with `curl` (no JS rendering needed). Local copies (untrusted data, not part of the repo) are in
  `<scratchpad>/dl/sfdata/`.
- Convention: **VERIFIED** = quoted verbatim from the source (checked by string match against the downloaded copy). **INFERENCE** = my reading or judgment; SF Data does not state it.

---

## 1. Sources

| # | Source | URL | Version / publication date (as shown) | Accessed | Full text read |
|---|---|---|---|---|---|
| S1 | SF Data homepage ("San Francisco Data") | https://www.sfdata.com/ | No date on page. Footer "© 2026 SF Data". HTTP `last-modified: Thu, 12 Nov 2026 15:30:09 GMT` (server header: deploy time, not necessarily a content date) | 2026-11-13 | yes |
| S2 | Essay "Production traces and the future of data", byline "Brandon Guo, Faiz Siddiqi" | https://www.sfdata.com/blog/production-traces/ | Byline date **October 1, 2026** (`<time datetime="2026-10-01">`). HTTP `last-modified: Wed, 11 Nov 2026 05:37:13 GMT` | 2026-11-13 | yes (about 1,280 words, 4 headed sections plus an untitled intro) |
| S3 | Research Engineer posting (Ashby) | https://jobs.ashbyhq.com/sfdata/98e1d652-80f5-4d9d-b3c2-54e8f74461bb | JSON-LD `datePosted: "2026-10-25"`; posting API `publishedAt: 2026-10-25T19:48:52.604+00:00`; `updatedAt` not provided | 2026-11-13 | yes (text taken from the JSON-LD embedded in the page; it is identical to the API `descriptionHtml`) |
| S4 | Ashby public posting API for the board | https://api.ashbyhq.com/posting-api/job-board/sfdata | Returned 2 listed postings (S3 and S5) | 2026-11-13 | yes |
| S5 | Engineering Intern posting (supplementary; returned by S4) | https://jobs.ashbyhq.com/sfdata/20f37c79-b892-46d9-98d9-3588ab45542c | API `publishedAt: 2026-11-11T23:17:11.512+00:00` | 2026-11-13 | yes, via API; only research-task wording recorded (section 2.8) |
| S6 | Site sitemap | https://www.sfdata.com/sitemap.xml | Undated. Lists exactly 2 URLs: `/` and `/blog/production-traces/` | 2026-11-13 | yes |
| S7 | Open Graph image (shared-link card) | https://www.sfdata.com/opengraph-image.png | Undated, 1200x630 PNG | 2026-11-13 | yes (image text read visually) |

Integrity hashes of the downloaded copies (sha256):
- S1 `home.html`: `8278cb39868ce1380bffaadd489ca9ba3fa8f14c680c9d5f729d404463703b1b`
- S2 `production-traces.html`: `9c4e77480e2a57f06dffadf100379b7c171d2855b2a475a0a97a46d190dcc1be`
- S3/S4 Research Engineer `descriptionPlain` (from API): `6e46eb681815e8aa3c9c3b463645c8751e5d4e608a9debd70fbba6965371b273`
- S6 `sitemap.xml`: `64c6b8d57cbe9db14064b7b764aa154791a70a8c6ba06cf7030dad0c58548d27`
- S7 `opengraph-image.png`: `6b1f8440788ca0c425b98002c3991e505d793068ab714ec791646287cd4ada96`
- (The S3 page HTML itself is not hash-stable: it embeds a per-request CSP nonce.)

Other checks:
- **No other blog posts found.** The homepage "Essays" list has one entry, and `sitemap.xml` lists only the homepage and this essay. `/blog/`, `/rss.xml`, `/feed.xml`, `/atom.xml`, `/llms.txt`, `/about/`, `/research/` and `/careers/` all returned HTTP 404 on 2026-11-13. `robots.txt` = `Allow: /` plus a sitemap pointer.
- Two standard web searches (`"San Francisco Data" "production traces" RL environments`; `sfdata.com "Production traces and the future of data"`) returned **no** SF Data primary sources. The essay did not appear to be indexed by the search tool on the access date.

---

## 2. VERIFIED public statements (quoted)

### 2.1 What they say they do

- S1 (homepage intro): "San Francisco Data turns production traces into RL environments. As models surpass human intelligence, we believe the best training data comes from where models fail on real work, not from tasks built to break them."
- S1 (homepage intro): "We partner with companies whose agents are pushed past their limits and turn those failures into training environments to continuously push the frontier."
- S3 (posting, first paragraph): "San Francisco Data turns production traces into training environments for frontier models."
- S3 (page meta description): "Build frontier training environments, benchmarks, and evaluation infrastructure from real production agent traces."
- S7 (Open Graph image tagline, read from the image): "The marketplace for proprietary AI data".
- S2 (intro): "In this way, the economy itself can become the largest source of training data for advanced AI."
- S1, company self-description (homepage section "Careers"), fragment: "co-authored benchmarks like TerminalBench, and built environments and evals for 20+ frontier labs." (This is the company's own claim. I did not verify it.)

### 2.2 What a "production trace" is, and why traces rather than final artifacts (S2, section "Why production traces matter")

- "We define a production trace as the chronology of AI working on a real task. Depending on the application, it includes the user’s request, the context available to the model, its tool calls, and subsequent feedback."
- "Traces preserve enough information to understand both the intended outcome and the path taken toward it."
- "Having only a finished artifact often leaves this gap impossible to reconstruct."
- "While a static repository shows the assumptions someone ultimately settled on, the surrounding interaction may explain why an apparently reasonable solution failed or why a requirement that looked minor was essential."
- "When that context is recorded, it gives us a way to build training tasks around decisions that would otherwise be impossible to reverse engineer."
- Supply argument: "An agentic product generates new sessions as users work on new problems. Each deployment creates opportunities to observe where the system fails."
- "Our belief is that production data will keep moving toward the boundary of what models can accomplish, because people will keep asking useful systems to do more."
- Motivation (S2 intro): "Contractor-generated training data starts to look like a race to the bottom." Also: "Yet even a system with superhuman abilities will encounter unfamiliar businesses, changing requirements, and problems it has never seen."

### 2.3 The problems they name (S2, section "Turning traces into training data")

Framing: "Turning traces into high quality training data that verifiably improves models is a challenging and open research problem."

**P1. Session selection**
- "The first problem is identifying sessions that contain something worth learning."
- "Many production traces will be repetitive, incomplete, or too basic to contain content valuable enough for frontier model development. A failed attempt may reveal a broken environment rather than a model limitation."

**P2. Reconstructing objectives and environments into reproducible tasks**
- "The next problem is turning those sessions into reproducible tasks."
- "This requires recovering the user’s explicit and implicit objectives, including requirements introduced through later corrections, and enough of the original environment for another model to attempt the work."
- "A missing input or unavailable service can make an otherwise valuable trace unusable without further augmentation."
- **"Preserving the initial prompt alone may produce a task that rewards precisely the behavior the user rejected."** (This is the TraceContract hypothesis, stated as a claim. The essay gives no measurement.)

**P3. Trustworthy verification**
- "The final problem is evaluation."
- "Existing tests may overlook an important constraint, and naïve user approval is not always evidence of correctness."
- "A verifier must capture the behavior the user actually needed and resist attempts to exploit the evaluation. Otherwise, additional training can make a model better at passing the grader without improving its ability to do the work."

**P4. Evidence of downstream training value**
- "The value of this work ultimately depends on the capabilities it produces."
- "Internal post-training experiments help establish which data improves performance on new tasks and which merely add volume."

### 2.4 Permissions, filtering and data rights (S2, section "Building a market for production traces")

- "Production sessions often contain customer information and proprietary material so permissions and appropriate filtering inform which tasks we can construct."
- "A valuable stream is one we can repeatedly turn into useful training data under an agreement that supports that work."

### 2.5 Initial domain focus (S2, section "The future of data")

- "The majority of economically valuable traces generated today come from coding agents, and that’s where we are beginning."
- Long-term framing: "Our long-term vision is to build a continuous connection between AI deployed across the economy and the training processes that determine what AI can do next."

### 2.6 Market framing (S2, brief; included for context only)

- "Properly diffusing this value requires a market."
- "We often describe our ambition as a Glencore for production traces." (The word "Glencore" links to Wikipedia.) Also: "Raw traces are not training assets any more than crude oil is jet fuel."
- The essay argues that source companies keep advantages beyond their data and can share in the proceeds when frontier labs train on their traces. Paraphrased here; it is not research-relevant to TraceContract beyond 2.4.

### 2.7 Research Engineer posting (S3): research work and capabilities named

Only research-related content is recorded (headings "What you'll do" and "What we're looking for").

What you'll do:
- "Create new frontier training environments and task formats from production agent traces."
- "Analyze agent failures and run experiments to measure training value, working directly with frontier researchers on new benchmarks and task formats."
- "Build core infrastructure for automated creation, quality control, and evaluation of training environments at scale."

Research capabilities asked for:
- "Published agent benchmarks or experience scaling synthetic data or post-training pipelines."
- "Strong engineering ability: you can turn a research idea into a working system and produce results others can reproduce."
- "Good experimental judgment: you can distinguish model failures from problems in the data, environment, or evaluation."

### 2.8 Supplementary (S5, second posting returned by the API): research-task wording only

S5's research bullets largely repeat S3. Two phrasings add detail:
- "Develop tools to generate, test, and evaluate training tasks, helping improve the quality and reliability of our environments"
- "Analyze agent behavior and failure cases, and run experiments on new benchmarks and task formats"

### 2.9 What the public sources do NOT state (checked absences, as of 2026-11-13)

- No method, algorithm, prompt, schema or **task format** is described for reconstruction or verification. The phrase "task formats" is used in S3 but not defined.
- No definition of "implicit objectives", and no procedure for detecting "requirements introduced through later corrections".
- No verifier type (unit tests, LLM judge, rubric, etc.) and no audit procedure is specified.
- No quantitative results: no false-acceptance or false-rejection rates, no counts of sessions or tasks, no post-training results. The essay mentions "Internal post-training experiments" but reports no results.
- No public code, dataset, benchmark or paper. The sitemap lists only the homepage and the essay. The essay page carries "© 2026 San Francisco Data", and no open license is stated.
- **False rejection of valid alternatives is not named explicitly.** The verification paragraph names missed constraints, unreliable user approval and exploitation (the false-acceptance side). The phrase "capture the behavior the user actually needed" could be read as also covering over-strict verifiers, but the essay does not say so. (This is a reading of the text, so treat it as interpretive.)
- The essay does not label its authors as founders. The task brief calls it "the founders' essay". The meta description reads "...on production traces and the company we are building at San Francisco Data."

---

## 3. INFERENCES: which research outputs would be relevant to the stated problems

Everything in this section is my judgment. None of it is an SF Data statement or a claim about SF Data's internal methods.

### 3.1 Mapping from SF Data's stated problems to the TraceContract design

| SF Data stated problem (verified quote, section 2) | TraceContract component | Coverage in current plan (inference) |
|---|---|---|
| P2: "Preserving the initial prompt alone may produce a task that rewards precisely the behavior the user rejected." | 2x2 factor A: initial-request-only contract vs full-session correction-aware contract. Naturally observed pre-correction code states as candidates | **Directly targeted.** TraceContract would turn this claim into a measured false-acceptance rate on "the behavior the user rejected" (the pre-correction state) |
| P2: "requirements introduced through later corrections" / "explicit and implicit objectives" | Correction-aware contract extraction; competent full-session LLM reconstruction baseline | Directly targeted. The LLM baseline tests whether a careful reconstruction already recovers corrections without a dedicated method |
| P3: "Existing tests may overlook an important constraint" | Existing repository tests as a verifier baseline | Directly targeted |
| P3: "naïve user approval is not always evidence of correctness" | Independent human-adjudicated labels (not user approval) as ground truth | Targeted. Possible extension: report agreement between in-session user approval signals and adjudicated labels |
| P3: "resist attempts to exploit the evaluation" | 2x2 factor B: verifier-audit procedure; constructed near-misses | Partly. Near-misses probe under-specification but are not adversarial exploits. Exploit-style candidates (hard-coding expected outputs, special-casing tested inputs, editing tests) would address this phrase more directly |
| P3: "better at passing the grader without improving its ability to do the work" | Reward fidelity (verifier score vs adjudicated acceptability) | Partly. Fidelity on held-out patches is a precondition; it is not a training-time measurement |
| P4: "Internal post-training experiments help establish which data improves performance on new tasks..." | Not in the current 2x2 | **Not covered.** State it as a limitation, or add a cheap proxy (see 3.2) |
| P1: "A failed attempt may reveal a broken environment rather than a model limitation." / S3: "distinguish model failures from problems in the data, environment, or evaluation" | Session selection and environment reconstruction steps (not a factor in the 2x2) | Partly. An environment-validity gate and a failure-attribution label in adjudication would speak to this |
| P2: "A missing input or unavailable service can make an otherwise valuable trace unusable..." | Executable task reconstruction | Partly. Reporting attrition (sessions dropped and why) would speak to this |
| 2.4: "permissions and appropriate filtering inform which tasks we can construct" | "Authorized coding-agent sessions" premise | Covered in premise. Possible extension: measure whether redaction removes correction content the contract needs |
| 2.5: coding agents first | Coding-agent sessions | Aligned |
| S3: "produce results others can reproduce" | Open, reproducible research system | Aligned |

### 3.2 Research outputs that would be relevant to these stated problems (inference)

1. **A measured false-acceptance rate** for initial-request-only verifiers on naturally observed rejected states, with CIs, against adjudicated labels. This turns the essay's central claim from an assertion into a number, and none of the public SF Data sources contains such a number.
2. **A paired false-rejection rate on valid alternative implementations.** The essay's verification paragraph emphasizes the false-acceptance side. A two-sided measurement shows whether correction-aware or audited verifiers buy precision at the cost of rejecting acceptable solutions.
3. **An ablation of the verifier-audit procedure** (factor B) with its human or compute cost per task. This relates to S3's "quality control ... of training environments at scale" (automation cost matters at scale).
4. **A comparison against existing repository tests and a competent full-session LLM reconstruction.** These answer the essay's "Existing tests may overlook an important constraint" and give a realistic baseline for whether a dedicated method is needed.
5. **Failure attribution and attrition accounting**: how many candidate sessions fail because of environment, data or reconstruction problems versus genuine model or agent mistakes. This relates to P1 and to the S3 phrase "distinguish model failures from problems in the data, environment, or evaluation."
6. **A downstream-value proxy**, for example best-of-n reranking or rejection sampling where each verifier picks among candidate patches and the adjudicated acceptability of the picks is measured. This is a cheap step toward P4 without RL training. A small RL or fine-tuning experiment would be stronger but is outside the current plan.
7. **Exploit-style candidates** in the held-out pool (tests edited, hard-coded expected values, special-cased inputs). These would test the "resist attempts to exploit the evaluation" requirement explicitly.
8. **A public, documented task format** (for example one compatible with the locally cloned Terminal-Bench/Harbor references) plus released code and labels, so results are reproducible (S3: "produce results others can reproduce"). This is not a claim about what format SF Data uses; their format is not public.

### 3.3 Novelty implications (inference)

- The **problem framing is not new**. As of 2026-10-01, SF Data's public essay states nearly verbatim that initial-prompt-only reconstruction "may produce a task that rewards precisely the behavior the user rejected." It also states that verifiers must "capture the behavior the user actually needed and resist attempts to exploit the evaluation." TraceContract should cite this as an industry statement of the problem and should not claim to have identified it.
- The public SF Data sources contain **no method, data, labels or measurements**, so they do not pre-empt an empirical contribution. Whether academic prior work does is for the other clusters to establish. SF Data's mention of "Internal post-training experiments" means unpublished internal evidence may exist, so TraceContract can claim at most a *public* measurement.
- The homepage's "not from tasks built to break them" contrasts naturally occurring failures with constructed difficulty. This supports making **naturally observed pre-correction states the primary candidate class** in TraceContract, with constructed near-misses reported separately.

---

## 4. Could not access / limitations

- **web.archive.org** was unreachable from this environment: curl got a connection reset through the proxy (the proxy log shows the tunnel closed with code 1006), and WebFetch refused the host. I therefore could **not** check whether the essay text changed between the byline date (2026-10-01) and the `last-modified` header (2026-11-11), or whether the homepage changed before its 2026-11-12 deploy. All quotes are from the versions served on 2026-11-13.
- X/Twitter `@sfdata` (named only in page meta tags) was **not attempted**: it is out of scope and needs login/JS.
- Web search did not surface any other SF Data primary source. A secondary industry post ("Your traces aren't training data yet...", dltHub, https://dlthub.com/blog/your-traces-aren-t-training-data-yet-here-s-the-pipeline-that-makes-them) came up in the search results. It is **not read** and out of this cluster's scope.
- The team-background claim on the homepage (TerminalBench co-authorship, "environments and evals for 20+ frontier labs") was not independently verified.

---

## 5. Related-work row (for the synthesis table)

- **Name:** SF Data, "Production traces and the future of data" (industry essay), with the homepage and Research Engineer posting
- **Citation:** Guo, B., & Siddiqi, F. (2026, October 1). *Production traces and the future of data*. San Francisco Data (company essay). https://www.sfdata.com/blog/production-traces/ (accessed 2026-11-13)
- **Task source:** production traces from partner companies' AI products ("the chronology of AI working on a real task"), with coding agents as the stated initial focus. No public dataset.
- **Reconstruction assumptions:** stated as requirements, not as a method. Recover explicit and implicit objectives, including later corrections, and enough of the original environment. Missing inputs or services may need "further augmentation". Permissions and filtering limit which tasks can be constructed.
- **User corrections:** central. "Preserving the initial prompt alone may produce a task that rewards precisely the behavior the user rejected." Not measured.
- **Verifier type:** not stated. Requirements: capture the needed behavior, resist exploitation. Existing tests can miss constraints, and naive user approval is not evidence of correctness.
- **Independent validation:** not stated (no public labels or adjudication).
- **Training experiments:** "Internal post-training experiments" are mentioned, with no public results.
- **Artifacts and license:** none public. Pages are "© 2026", and no open license is stated.
- **Overlap: medium.** Problem framing overlaps almost completely; there is no overlap in method, data or empirical results.
