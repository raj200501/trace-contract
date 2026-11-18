# Cluster notes: industry problem statement (SF Data / San Francisco Data)

- Access date for every source below: **2026-11-13 (UTC)**. Publication/version dates are recorded separately.
- Scope: **the company's public essay**. Company statements are recorded only where the essay supports them. Nothing here describes or guesses at any private implementation.
- Privacy and rights revision (2026-11-18), after an internal review:
  - **Removed:** all material from company pages other than the essay (two pages and one API listing), the statements quoted from the homepage and from the site's shared-link image, the company's description of its team, and every mapping of this project onto that material. Section numbers are kept, so §2.7 and §2.8 are now empty.
  - **Quotations trimmed:** the essay carries "© 2026 San Francisco Data" and states no open licence. This note quotes only one sentence (V8) and one phrase (in V7), the wording the research brief relies on. Everything else is paraphrased.
- Retrieval: all pages were static HTML or XML and were fetched with `curl` (no JS rendering needed). Local copies (untrusted data, not part of the repo) are in `<scratchpad>/dl/sfdata/`, where `<scratchpad>` is the study's session scratchpad; see `data/manifests/third_party_downloads.json` (`web-sfdata`).
- Convention: **VERIFIED** = stated in the essay. The quoted sentence and phrase match the downloaded copy exactly; the paraphrases were checked against it. **INFERENCE** = my reading or judgment; the essay does not state it.

---

## 1. Sources

| # | Source | URL | Version / publication date (as shown) | Accessed | Full text read |
|---|---|---|---|---|---|
| S1 | SF Data homepage ("San Francisco Data") | https://www.sfdata.com/ | No date on page. Footer "© 2026 SF Data". HTTP `last-modified: Thu, 12 Nov 2026 15:30:09 GMT` (server header: deploy time, not necessarily a content date) | 2026-11-13 | yes; used only to check the list of essays (its statements were removed on 2026-11-18) |
| S2 | Essay "Production traces and the future of data", byline "Brandon Guo, Faiz Siddiqi" | https://www.sfdata.com/blog/production-traces/ | Byline date **October 1, 2026** (`<time datetime="2026-10-01">`). HTTP `last-modified: Wed, 11 Nov 2026 05:37:13 GMT` | 2026-11-13 | yes (about 1,280 words, 4 headed sections plus an untitled intro) |
| S3 | Site sitemap | https://www.sfdata.com/sitemap.xml | Undated. Lists exactly 2 URLs: `/` and `/blog/production-traces/` | 2026-11-13 | yes |

Integrity hashes of the downloaded copies (sha256):
- S1 `home.html`: `8278cb39868ce1380bffaadd489ca9ba3fa8f14c680c9d5f729d404463703b1b`
- S2 `production-traces.html`: `9c4e77480e2a57f06dffadf100379b7c171d2855b2a475a0a97a46d190dcc1be`
- S3 `sitemap.xml`: `64c6b8d57cbe9db14064b7b764aa154791a70a8c6ba06cf7030dad0c58548d27`

Other checks:
- **No other essays or blog posts found.** The homepage "Essays" list has one entry, and `sitemap.xml` lists only the homepage and this essay. `/blog/`, `/rss.xml`, `/feed.xml`, `/atom.xml`, `/llms.txt`, `/about/` and `/research/` all returned HTTP 404 on 2026-11-13. `robots.txt` = `Allow: /` plus a sitemap pointer.
- Two standard web searches (`"San Francisco Data" "production traces" RL environments`; `sfdata.com "Production traces and the future of data"`) returned **no** SF Data primary sources. The essay did not appear to be indexed by the search tool on the access date.

---

## 2. VERIFIED statements in the essay (S2)

Statement ids V3–V15 are shared with the research brief §1.2. Former V1–V2 were homepage statements and were removed on 2026-11-18. Section names are the essay's headings. Only V8 and one phrase of V7 are quoted.

### 2.1 Framing (untitled introduction)

- Paraphrase: training data written by paid expert contractors gets harder to scale as models overtake those experts. Even a very capable system will meet unfamiliar businesses, changing requirements and new problems. Products in which AI does real work gather evidence about those problems as production traces, so real economic activity can become the largest source of training data.

### 2.2 What a production trace is, and why traces rather than final artifacts ("Why production traces matter")

- **V3** (paraphrase): a production trace is the time-ordered record of an AI system doing a real task. What it contains varies by application: the user's request, the context the model had, the model's tool calls and later feedback. A trace keeps enough to see what was wanted and how the work proceeded.
- **V4** (paraphrase): a finished artifact alone often cannot close this gap. A final repository shows the assumptions someone settled on, but only the recorded interaction may explain why a reasonable-looking solution failed or why a seemingly minor requirement mattered. Recording that context lets training tasks be built around such decisions.
- **V15** (paraphrase): the supply of traces grows with AI use. As users bring new problems to an agentic product, it produces new sessions, and each deployment shows where the system fails. Stronger models are given larger tasks, so production data keeps moving toward the limit of what models can do.

### 2.3 The problems the essay names ("Turning traces into training data")

- **V5** (paraphrase): turning traces into high-quality training data that demonstrably improves models is presented as a hard, open research problem. Four problems follow.

**P1. Session selection**
- **V6** (paraphrase): the first problem is finding sessions with something to learn from. Many traces are repetitive, incomplete or too basic for frontier model development, and a failure may come from a broken environment rather than from a limitation of the model.

**P2. Reconstructing objectives and environments into reproducible tasks**
- **V7** (paraphrase with one quoted phrase): the next problem is making sessions into reproducible tasks. That requires recovering the user's explicit and implicit objectives, "including requirements introduced through later corrections", plus enough of the original environment that a different model could try the task.
- **V9** (paraphrase): a missing input, or a service that can no longer be reached, can leave a useful trace unusable unless it is augmented.
- **V8** (verbatim): "Preserving the initial prompt alone may produce a task that rewards precisely the behavior the user rejected." This is the TraceContract hypothesis, stated as a claim. The essay gives no measurement.

**P3. Trustworthy verification**
- **V10** (paraphrase): the final problem is evaluation. Existing tests can miss an important constraint, and a user's approval does not by itself show that the work is correct.
- **V11** (paraphrase): a verifier has to check what the user really needed and withstand attempts to game it. Otherwise further training can teach a model to pass the grader without getting better at the work.

**P4. Evidence of downstream training value**
- **V12** (paraphrase): the work is worth only as much as the capabilities it yields. The essay says internal post-training experiments are used to tell data that improves performance on new tasks from data that only adds volume. It gives no results.

### 2.4 Permissions, filtering and data rights ("Building a market for production traces")

- **V13** (paraphrase): sessions from production often include customer data and proprietary material, so permissions and filtering decide which tasks can be built. A source is valuable only if it can repeatedly be turned into training data under an agreement that allows this.

### 2.5 Initial domain focus ("The future of data")

- **V14** (paraphrase): coding agents produce most of today's economically valuable traces, and that is where the company starts. The stated long-term aim is a continuous link between deployed AI systems and the training of later models.

### 2.6 Market framing (context only)

- The essay's commercial argument (a market that connects companies producing traces with frontier labs, in which source companies keep their other advantages and share in the proceeds) is not research-relevant to TraceContract beyond §2.4 and is not summarised further.

### 2.7 and 2.8 (removed 2026-11-18)

- Removed in the privacy and rights revision: material from company pages other than the essay.

### 2.9 What the essay does NOT state (checked absences, as of 2026-11-13)

- No method, algorithm, prompt, schema or task format is described for reconstruction or verification.
- No definition of the user's implicit objectives, and no procedure for detecting requirements introduced through later corrections.
- No verifier type (unit tests, LLM judge, rubric, etc.) and no audit procedure is specified.
- No quantitative results: no false-acceptance or false-rejection rates, no counts of sessions or tasks, no post-training results. The essay mentions internal post-training experiments but reports no results.
- No public code, dataset, benchmark or paper. The sitemap lists only the homepage and the essay. The essay page carries "© 2026 San Francisco Data", and no open license is stated.
- **False rejection of valid alternatives is not named explicitly.** The verification paragraph names missed constraints, unreliable user approval and exploitation (the false-acceptance side). Its requirement that a verifier check what the user really needed (V11) could be read as also covering over-strict verifiers, but the essay does not say so. (This is a reading of the text, so treat it as interpretive.)

---

## 3. INFERENCES: how the essay's stated problems relate to the TraceContract design

Everything in this section is my judgment. It positions this research against a public problem statement. None of it is an SF Data statement or a claim about SF Data's internal methods. Rows and items that were based on material other than the essay were removed on 2026-11-18.

### 3.1 Mapping from the essay's stated problems to the TraceContract design

| Problem stated in the essay (§2) | TraceContract component | Coverage in current plan (inference) |
|---|---|---|
| P2, V8: keeping only the initial prompt may reward the behaviour the user rejected | 2x2 factor A: initial-request-only contract vs full-session correction-aware contract. Naturally observed pre-correction code states as candidates | **Directly targeted.** TraceContract would turn this claim into a measured false-acceptance rate on the behaviour the user rejected (the pre-correction state) |
| P2, V7: requirements introduced through later corrections; explicit and implicit objectives | Correction-aware contract extraction; competent full-session LLM reconstruction baseline | Directly targeted. The LLM baseline tests whether a careful reconstruction already recovers corrections without a dedicated method |
| P3, V10 (first half): existing tests can miss a constraint | Existing repository tests as a verifier baseline | Directly targeted |
| P3, V10 (second half): user approval is not evidence of correctness | Independent human-adjudicated labels (not user approval) as ground truth | Targeted. Possible extension: report agreement between in-session user approval signals and adjudicated labels |
| P3, V11: the verifier must withstand gaming | 2x2 factor B: verifier-audit procedure; constructed near-misses | Partly. Near-misses probe under-specification but are not adversarial exploits. Exploit-style candidates (hard-coding expected outputs, special-casing tested inputs, editing tests) would address this more directly |
| P3, V11: training can improve grader-passing without improving the work | Reward fidelity (verifier score vs adjudicated acceptability) | Partly. Fidelity on held-out patches is a precondition; it is not a training-time measurement |
| P4, V12: training value | Not in the current 2x2 | **Not covered.** State it as a limitation, or add a cheap proxy (see 3.2) |
| P1, V6: a failure may come from a broken environment | Session selection and environment reconstruction steps (not a factor in the 2x2) | Partly. An environment-validity gate and a failure-attribution label in adjudication would speak to this |
| P2, V9: a missing input or service can make a trace unusable | Executable task reconstruction | Partly. Reporting attrition (sessions dropped and why) would speak to this |
| §2.4, V13: permissions and filtering limit which tasks can be built | "Authorized coding-agent sessions" premise | Covered in premise. Possible extension: measure whether redaction removes correction content the contract needs |
| §2.5, V14: coding agents first | Coding-agent sessions | Same domain |
| §2.2, V15: deployments show where systems fail | Candidate origins | Supports making naturally observed pre-correction states the primary negative class, with constructed near-misses reported separately |

### 3.2 Extensions suggested by the essay's problem list (inference)

1. **A measured false-acceptance rate** for initial-request-only verifiers on naturally observed rejected states, with CIs, against adjudicated labels (V8). This turns the essay's central claim from an assertion into a number; the essay contains no such number.
2. **A paired false-rejection rate on valid alternative implementations.** The essay's verification paragraph emphasizes the false-acceptance side. A two-sided measurement shows whether correction-aware or audited verifiers buy precision at the cost of rejecting acceptable solutions.
3. **An ablation of the verifier-audit procedure** (factor B) with its human or compute cost per task (V11). Cost matters for any pipeline that audits verifiers at scale.
4. **A comparison against existing repository tests and a competent full-session LLM reconstruction** (V10, V7). These give a realistic baseline for whether a dedicated method is needed.
5. **Failure attribution and attrition accounting** (V6, V9): how many candidate sessions fail because of environment, data or reconstruction problems versus genuine model or agent mistakes.
6. **A downstream-value proxy** (V12), for example best-of-n reranking or rejection sampling where each verifier picks among candidate patches and the adjudicated acceptability of the picks is measured. This is a cheap step toward P4 without RL training. A small RL or fine-tuning experiment would be stronger but is outside the current plan.
7. **Exploit-style candidates** in the held-out pool (tests edited, hard-coded expected values, special-cased inputs). These would test the requirement that verifiers withstand gaming (V11) explicitly.

(Item 8 of the earlier version was removed on 2026-11-18; it was based on material other than the essay.)

### 3.3 Novelty implications (inference)

- The **problem framing is not new**. As of 2026-10-01, the essay states that keeping only the initial prompt "may produce a task that rewards precisely the behavior the user rejected" (V8), and that verifiers must check what the user actually needed and withstand gaming (V11). TraceContract should cite it as an industry statement of the problem and should not claim to have identified it.
- The essay contains **no method, data, labels or measurements**, so it does not pre-empt an empirical contribution. Whether academic prior work does is for the other clusters to establish. Its mention of internal post-training experiments means unpublished internal evidence may exist, so TraceContract can claim at most a *public* measurement.
- The essay's supply argument (V15) treats failures observed in real deployments as the data source and contrasts it with expert-written data (§2.1). This supports making **naturally observed pre-correction states the primary candidate class** in TraceContract, with constructed near-misses reported separately. (Until 2026-11-18 this point rested on a homepage statement.)

---

## 4. Could not access / limitations

- **web.archive.org** was unreachable from this environment: curl got a connection reset through the proxy (the proxy log shows the tunnel closed with code 1006), and WebFetch refused the host. I therefore could **not** check whether the essay text changed between the byline date (2026-10-01) and the `last-modified` header (2026-11-11), or whether the homepage changed before its 2026-11-12 deploy. All statements are from the versions served on 2026-11-13.
- The company's X/Twitter account (named only in page meta tags) was **not attempted**: it is out of scope and needs login/JS.
- Web search did not surface any other SF Data primary source. A secondary industry post ("Your traces aren't training data yet...", dltHub, https://dlthub.com/blog/your-traces-aren-t-training-data-yet-here-s-the-pipeline-that-makes-them) came up in the search results. It is **not read** and out of this cluster's scope.

---

## 5. Related-work row (for the synthesis table)

- **Name:** SF Data, "Production traces and the future of data" (industry essay)
- **Citation:** Guo, B., & Siddiqi, F. (2026, October 1). *Production traces and the future of data*. San Francisco Data (company essay). https://www.sfdata.com/blog/production-traces/ (accessed 2026-11-13)
- **Task source:** production traces from partner companies' AI products (the time-ordered record of AI working on a real task, V3), with coding agents as the stated initial focus. No public dataset.
- **Reconstruction assumptions:** stated as requirements, not as a method. Recover explicit and implicit objectives, including later corrections, and enough of the original environment. Missing inputs or services may need augmentation. Permissions and filtering limit which tasks can be constructed.
- **User corrections:** central (V8, quoted in §2.3). Not measured.
- **Verifier type:** not stated. Requirements: check what the user needed, withstand gaming. Existing tests can miss constraints, and naive user approval is not evidence of correctness.
- **Independent validation:** not stated (no public labels or adjudication).
- **Training experiments:** internal post-training experiments are mentioned, with no public results.
- **Artifacts and license:** none public. Pages are "© 2026", and no open license is stated.
- **Overlap: medium.** Problem framing overlaps almost completely; there is no overlap in method, data or empirical results.
