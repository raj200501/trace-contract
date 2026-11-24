# Ownership and defense

Updated at commit `2daa725` (decision log through D81). The commands it reports were run for this update on 2026-11-23
and 2026-11-24 (UTC). Its passages on the review packet's candidate strata (§4 items 1 and 2, Q2, E1 and E11), on
`constraints.txt` (§2.3) and on the threat 'No optimisation pressure' (Q8) describe the changes that D82 records; their
commands ran on 2026-11-24 with those changes applied. Some passages were corrected afterwards, after read-only reviews
of commit `f3ae845` by model agents (D83); each cites the record it rests on. The previous
version (last committed in `4aecca0` on 2026-11-21; its licences read on 2026-11-18) predates the fresh-agent run, the
natural arm's construction and run, the manuscript's restructure and D79 to D81.

> **Reviewers who label candidates must not open this document before their labels are merged.** It states label
> proposals and verifier outcomes, and someone who has read it is not blind to them. The review packet's README tells
> reviewers not to open the repository's `docs/` folder, the annotation guide excepted (`src/tracecontract/review.py`;
> `docs/annotation_guide.md` v0.4).

This document separates what the repository borrows, what was produced with AI assistance, and what only the human
author(s) can decide or review. It then asks ten hard questions about the current results and system, with short
answers and pointers to the files, tests, decision-log entries and paper sections that bear on each, and gives
exercises for understanding and changing the core system. It claims no personal contribution for anyone.

**Where the numbers come from.** Each number names its record: a decision-log entry (`Dnn`), a file, or "ran" for a
command run for this update in an isolated worktree at `2daa725`, or for the strata passages in a scratch clone with the
change applied, or, for the passages corrected after the reviews of `f3ae845`, in a scratch copy of `f3ae845` with those
corrections applied (2026-11-24; D83), with the build environment's `.venv` (Python 3.13). Section 6 gives every such
command. The Docker
daemon was down during the checks at `2daa725`, so they graded nothing in Docker: where an exercise grades (the Docker
suite of E1, the grades of E5, and E12), this document gives the recorded outcome and says so. For D82 the build
session ran the 20 Docker tests with the daemon restarted (E1).

**Terms.** C1 and C2 are the verifiers built from the first request (the initial-only contract), plain and audited; C3
and C4 the correction-aware ones (the full-session contract); B1 the repository's tests at the reference state that
pass on the reference; B2 tests that a generator wrote from the whole transcript, with no contract; B3, natural arm
only, tests from the first request and the reference diff that fail on the base and pass on the reference. A `u1`
attempt got the first request only, a `final` attempt the first request and the correction. The reference is the
session's final state (natural arm: the pull request's addressing commit). D19 is the pre-specified label rule; its
regression norm is the base commit's tests that pass on the reference. The reference gate (the protocol's oracle-gated
view) keeps a verifier only where it passes its own reference.

## 1. What is being defended

* **Lead result: run `fresh-v1`** (D61, D62; `results/runs/fresh-v1/analysis.md`). 80 fresh agent attempts on the four
  controlled tasks, by two agent configurations, A and B, each attempt `u1` or `final`. After one exclusion by the
  reviewed audit, 79 distinct graded patches: 29 invalid and 50 valid under D19. Harness 0.3.5, every pair graded
  three times, no unresolved pair. 27 of the 40 `u1` attempts violate the correction; C1 and C2 accept 24 of them, and
  C3, C4, B2 and B1 accept none.
* **What the design fixes, and what it does not.** The contrast on the planned measure (protocol §15.4, estimand 3),
  C1 accepting 24 of the 27 correction violators and C3 none, is largely fixed by construction, and the paper says so
  (abstract, §1, §3; D80). C3's 2/29 false acceptance are CS-02's two regression-only attempts, which the design does
  not fix. Which families show a silent loss also follows largely from what each correction does: in CS-03 and CS-04,
  whose corrections only add requirements, C1 passes its reference yet accepts 14 of their 17 violators, against 0 for
  C3 (`paper/generated/fresh/numbers.tex`, keys `cv.silent.*`), while in CS-01, whose correction retracts a requirement
  C1 encodes, C1 fails its reference. Not fixed by it:
  * agents made the violators; no generator wrote them;
  * B1 rejects 34 of the 50 valid attempts, all through the 40 of its 2,219 checks that the session agent added (keys
    `b1.*` there; D62).
* **Nulls.** The audit removed no false acceptance and raised false rejection from 0/50 (C3) to 6/50 (C4). B2 matches
  C3 and C4 on false acceptance (2/29 each). With four families no exact sign-flip p-value can go below 0.0625
  one-sided, and none of the 14 planned comparisons reaches that floor (`analysis.md`).
* **Construction pilot `pilot-v0.3.3`**, a development study since protocol v0.7. Its re-grade under harness 0.3.5
  gives the same outcome on all 240 pairs (D54).
* **Natural case studies `natural-pr-v1`** (D76 to D78, D80): six pull-request review families, reported per family
  only. Read with the reference gate they say little about corrections (D80): C1 fails its own reference in five
  families and C3 in four (ran, E8).
* **Manuscript** (`paper/main.tex`): 77 pages, the main text ending on page 23, where the references start; no
  overfull box and no LaTeX warning in the log; one TODO, the author line (ran, E2). `paper/check_numbers.py` finds no
  number outside a macro in its 22 files (ran, E2).
* **No human label exists.** Every label is a model proposal, and every review so far is by model agents
  (`STATUS.md`; paper §9).

## 2. Borrowed components and their licences

### 2.1 Upstream code in the repository

| Component | Use | Licence |
| --- | --- | --- |
| humanize at `a95004512dde` (CS-01), tinydb at `edff96aeb261` (CS-02), inflection at `88eefaacf7d0` (CS-03), more-itertools at `ceafee8ce96f` (CS-04) | Base snapshots (rebuilt from the pinned commits, not stored), upstream test files in the overlays, the context lines of candidate patches, helpers copied into some verifier tests, excerpts in the controlled transcripts, and the diffs embedded in reports | MIT, each repository's own; licence files and the full list of paths in `THIRD_PARTY_LICENSES/` |

No code or thread text of the natural arm is in git. Its tasks, with their base snapshots, overlays, contracts,
generated tests, candidates and run records, stay under the git-ignored `data/natural/`; only ids, outcomes, counts and
hashes are committed (protocol §17.4; D64, decision 2; `THIRD_PARTY_LICENSES/README.md`).

### 2.2 Data

| Source | What the repository holds | Licence |
| --- | --- | --- |
| AIDev v5 (natural PR-review arm) | Extracted ids, commit SHAs, repository URLs (owners that act as accounts masked), SPDX licence values, the commented files' paths, counts, hashes and the model judges' verdicts, plus 120 model-written paraphrases. No verbatim comment, pull-request or issue text (D47) | CC-BY-4.0; revision and attribution in `THIRD_PARTY_LICENSES/README.md` |
| Trace Commons | Screening records only: all 30 sessions were rejected (`data/manifests/screening_natural.json`) | CC-BY-4.0 for the compilation (`docs/data_card.md`) |
| SWE-chat | Nothing: access is blocked on terms only the owner can accept (D4) | ODC-BY-1.0 for the database (`docs/data_card.md`) |
| Repositories of the natural arm | Their ids and URLs (in the fetch records), commit SHAs, licence identifiers, the commented files' paths, counts, outcomes and hashes; no code | Each its own; identifiers in `data/manifests/natural_tasks_index.json` (`THIRD_PARTY_LICENSES/README.md`) |

### 2.3 Python packages

`pyproject.toml` requires `pydantic>=2.7,<3` and offers two extras, `data` (`pyarrow>=16`, `duckdb>=1.0`) and `dev`
(`pytest>=8`, `pip>=24`), with the build backend `hatchling>=1.24`, so another install can resolve other versions.
Since D82, `constraints.txt` pins the versions below, and an install with `-c constraints.txt` reproduces them. The table gives every distribution installed in the build environment's `.venv` and the licence
each declares in its metadata (`License-Expression`, else the `License` field and licence classifiers; ran).

| Package | Version | Declared licence | Use |
| --- | --- | --- | --- |
| pydantic | 2.14.3 | MIT | the only runtime dependency: typed schemas |
| pydantic_core, annotated-types, typing-inspection | 2.50.4, 0.8.0, 0.4.5 | MIT | pydantic's dependencies |
| typing_extensions | 4.16.0 | PSF-2.0 | pydantic's dependency |
| duckdb | 2.0.0 | MIT (classifier only) | `data` extra: the natural arm reads the AIDev v5 parquet files (`src/tracecontract/ingest/github_pr.py`, `scripts/screen_aidev.py`) |
| pyarrow | 26.0.1 | Apache-2.0 | `data` extra |
| pytest | 9.2.0 | MIT | `dev` extra: the test suite |
| iniconfig, packaging, pluggy, Pygments | 2.3.1, 26.3, 1.7.0, 2.21.0 | MIT; Apache-2.0 OR BSD-2-Clause; MIT; BSD-2-Clause | pytest's dependencies |
| pip | 26.3 | MIT | `dev` extra: image builds download wheels with `python -m pip` |
| hatchling | 1.33.0, the version that built the installed package (`Generator` in `.venv`'s `tracecontract-0.1.0.dist-info/WHEEL`) | MIT (License-Expression of its wheel) | build backend, used only at install time; not installed in `.venv` |

The package itself, `tracecontract` 0.1.0, declares no licence: `pyproject.toml` has no licence field (§4, item 19).

### 2.4 Grading images

What is pinned is the grading environment. Each image is built offline from pinned wheels on the base image
`python:3.12-slim@sha256:5e2bdb1b0d54…` (`BASE_IMAGE` in `src/tracecontract/sandbox/docker_runner.py`): the default
image from `DEFAULT_TEST_REQUIREMENTS` there, and each controlled task's image from `env_requirements` in its
`task.json`. The build runs with no network and installs exactly the pins of the image's `requirements.lock` with
`--no-index --no-deps` (`build_env_image`). The licences below were read from each wheel's `METADATA` in the
wheelhouses of the three images, default (key `137c25ab71f8dfe8`), CS-01 (`0b1591bd588d585e`) and CS-02 to CS-04
(`801a26fad4c5e101`). They were re-read for this update and agree with the previous version of this document (ran).

| Wheel | Images | Declared licence |
| --- | --- | --- |
| attrs 26.1.0 | all | MIT (License-Expression) |
| freezegun 1.5.5 | CS-01 | "Apache-2.0" (License field) |
| hypothesis 6.131.0 | all | MPL-2.0 (License-Expression) |
| iniconfig 2.3.1 | all | MIT (License-Expression) |
| packaging 26.3 | all | Apache-2.0 OR BSD-2-Clause (License-Expression) |
| pluggy 1.7.0 | all | "MIT" (License field; classifier OSI Approved :: MIT License) |
| Pygments 2.21.0 | CS-01, CS-02 to CS-04 | BSD-2-Clause (License-Expression) |
| pytest 8.3.5 | default | "MIT" (License field; classifier OSI Approved :: MIT License) |
| pytest 9.2.0 | CS-01, CS-02 to CS-04 | MIT (License-Expression) |
| python-dateutil 4.0.0 | CS-01 | BSD-3-Clause (License-Expression) |
| sortedcontainers 2.4.0 | all | "Apache 2.0" (License field; classifier OSI Approved :: Apache Software License) |
| tzdata 2026.6 | CS-01 | "Apache-2.0" (License field) |

The base image holds CPython and Debian packages under their own licences, which this document does not inventory.
The natural families' images are built from each repository's resolved dependency closure (17 to 144 pins; D59). They
stay local, nothing of them is committed, and their wheels' licences are not inventoried either.

### 2.5 Tools used but not redistributed

* **Harbor 0.25.0** (PyPI `harbor`; Apache-2.0 by its PyPI licence expression, `docs/research_brief.md`): the task
  package format of the exporter, and oracle and no-op validation of exported tasks (`results/harbor_validation/`).
* Docker, git, uv, and a TeX distribution with `latexmk` and `biber` (README, "Reproduce"). The repository records no
  licence for them.

### 2.6 Ideas and prior work

* From prior work: oracle and no-op checks, cheat trials and hacker/fixer loops (Terminal-Bench's task review),
  FAIL_TO_PASS and PASS_TO_PASS selection (the SWE-bench family), and a separate verifier with artifact transfer
  (Harbor). They shaped audit:v1 and B1, and `docs/research_brief.md` and `paper/sections/related.tex` cite them.
* Each component of the design has at least a partial precedent, notably SessionFarmer, SWE-Together and Trace2Eval
  (paper §6, "Positioning"). The claim is limited to their conjunction (D34, awaiting the owner's confirmation). D80
  added four references on overfitting in program repair, the test oracle problem and requirements change, each
  checked against the Crossref record of its DOI.

## 3. What was produced with AI assistance

Everything below was produced by an AI coding agent, the build session, and the subagents it launched. So far it has
been reviewed only by model agents (`STATUS.md`; D79, D80). The records name two agent configurations: A, the build
session's default model, and B, the smallest model tier the agent tool offers, two tiers of one model family of one
provider (D56, D80). This document names no model, as the paper names none; whether to name them is an owner decision
(§4, item 6).

* **Code.** The package, CLI, tests, scripts, report and Harbor exporter. Through D82 that includes:
  * the harnesses 0.3.1 to 0.3.5 and the exporter's fixes (D36, D40, D44, D51, D52);
  * the reconstruction check v2 (D52) and the frozen-input check (`scripts/verify_frozen_inputs.py`);
  * the strata and fresh-attempt tooling, and the sidecar registration of the labelers (D52, D55);
  * the natural compiler and its S10 fixes (D59);
  * the natural analysis (WP-G) and the privacy and publication tools (WP-H1; D69);
  * the pre-flight and label-gate rules (D73, D74);
  * the table, figure and number-checking code of `paper/` (D66, D79, D80);
  * the scanner's idiom rules (D72, D81);
  * the review packet's candidate strata (`src/tracecontract/review.py`, `src/tracecontract/cli.py`) and the downstream
    plan's data step (`scripts/build_training_selection.py`, `configs/downstream/rft_selection_v0.1.json`, output in
    `results/analyses/fresh-v1-training-selection/`) (D82).
* **Protocol and records.** Protocol v0.1 and its amendments v0.2 to v0.12, each hashed before the runs it governs (D15
  to D71); the decision log D1 to D83; the draft downstream-training plan (`experiments/downstream_plan_v0.1-draft.md`;
  not run, not adopted; D82); the annotation guide, data card, status and readiness documents, and this document.
* **Controlled sessions.** The study's agent, the same model as the session agent, wrote the scenarios, including the
  scripted user turns, the corrections and the intended requirements that define the labels, and their reference
  operationalisation (`STATUS.md`). Agents produced the sessions, the recovered contracts, every verifier, the
  development attacks, valid alternatives and near misses, the reference checks, the construction checks, both
  requirement mappers and every label proposal.
* **Fresh-agent run.** The 80 attempts, run by configurations A and B as subagents (D56, D57). Also by agents: the
  attempt audits and the reviewed readings of every flag (D57, D58, D62); the four independent labelers, written by
  configuration B and coordinated by configuration A (D55, D58); the label proposals (D58); and the run, its analysis,
  the independent recomputation and the error analysis (D61, D62).
* **Natural arm.** All by agents:
  * the S9 judges, two model judges per comment (D50, D63, D66), and the S10 build (D59);
  * the recipe and its fifteen templates (D64, D65);
  * every agent of phases P1 to P7: contract proposers, test generators, development attacks and alternatives, audit
    revisers, the reference-contract drafter, reference-check writers, reviewers and fixers, the independent labelers
    (configuration B), the held-out pool generators and the mappers (D70, D72, D75);
  * the audits of their transcripts (D75), the D19 labels (D76), and the run, its analysis and its publication (D76 to
    D78).
* **Manuscript.** Drafted, restructured and revised by agents (D66, D79, D80, D82, D83), including the bibliography
  checks of D80.
* **Reviews and verifications**, all by model agents:
  * the six-lens internal review, the dispositions review, the claims audit and the verifications of rounds 3 and 4
    (D36 to D46, D51);
  * the re-audit against the original specification (D47);
  * the two-lens reviews of D74 and D77, the three-lens reviews of D79, the accuracy and venue reviews of D80 and the
    check of its fix round, and the reviewer of D81;
  * D82's two reviewers (the round's parts, and the downstream plan), and the four-lens review of `f3ae845` with the
    check of its fix round (D83).
* **This update.** Written by an agent from read-only checks that model agents made after D81: a critical read of the
  whole repository, a clean-clone run of the README's commands and a re-check of the arXiv guidance. D82 records them.
  Some passages were then corrected after read-only reviews of `f3ae845` by model agents (D83).

Where the decision log records an instruction or decision of the owner, this document cites it as such: for example
the approval to use SWE-chat (D4), the request for the re-audit (D47), and the reply that the build session took as
approval of per-sample natural runs (D71). The records cited here attribute none of the work above to a person.

## 4. Decisions and reviews only the human author(s) can make

From `STATUS.md` ("Owner decisions pending" and "Blocked") and D79 to D83, with items 1, 4, 5 and 20 completed from
the checks behind this update. The records show none of them as taken; where the build applied a default, it is named
as one.

**Labels, the gate and the lead result**

1. **Human labels.** No human label exists. The procedure: two qualified reviewers per task work from the blinded packet
   (`tracecontract review-packet`) under `docs/annotation_guide.md` (v0.4); `tracecontract merge-reviews` merges their
   labels, and disagreements are adjudicated. With `--strata fresh-v1` the packet covers the lead result (D82).
   * `held_out()` in `src/tracecontract/review.py` reads `task.json` only: the pilot's 32 held-out candidates, 8 per
     task. `stratum_held_out()` adds the fresh attempts listed in `tasks/<id>/strata/fresh-v1.json` that the analysis
     keeps: 20, 19, 20 and 20 per task, 79 in all, with CS-02-fresh-A-final-1 left out for its failed audit (ran,
     E11). They are blinded as the task's own: ids from the same pool, one shuffled folder and one template per task.
     The packet then holds 110 items for 111 candidates, since two CS-04 pilot candidates have the same diff and
     share an id (ran, E11).
   * The run's analysis queues every analysed attempt for review (`results/runs/fresh-v1/analysis.md`, "Labels and
     human-review queue"), as protocol §15.4 and the paper's App. H say, and the packet's 79 are the same attempts
     (ran). No `tasks/*/labels/review_queue.json` mentions a fresh attempt.
   * `merge-reviews` appends a fresh attempt's labels to its file in the stratum
     (`tasks/<id>/strata/fresh-v1/candidates/`), whose hash fresh-v1's `analysis.json` records among its inputs; item 2
     holds the decision this needs.
   * The workload is the 79 fresh-attempt patches, the pilot's 32 candidates and the contract reviews. The natural arm
     has no packet (D64, decision 8); D19 queues four ambiguous natural candidates (D76).
2. **The acceptance gate.** Reviews alone cannot open it (`STATUS.md`, "Blocked"; D51).
   * No command sets a provenance record to `eligible`. Decide where the provenance review is recorded: a sidecar, since
     `provenance.json` is frozen (D47).
   * The gate checks the condition contracts, which hold unresolved requirements by design. Decide whether it checks
     them or only the reference contract.
   * `merge-reviews` writes into the frozen candidate and contract files, and into the fresh attempts' files in the
     stratum, whose hashes fresh-v1's `analysis.json` records among its inputs (80 attempt files). Decide whether it
     may, or whether it writes sidecars instead.
   * Confirm the gate's review rules: each reviewer's latest decision counts, and `edit` and `needs_discussion` block
     until a re-review accepts (DOCU-23; D51).
3. **A labeler and generators from a second model family**, and the budget for them (paper §7).

**The manuscript**

4. **The author line, and a full review of the text by its human authors** before any submission (D80), with the
   statements only they can make: authorship, AI use and competing interests. Section 9 says the work was "produced
   with an AI coding agent under instructions from the human authors"; only they can say what they instructed, wrote
   or checked. Every check of the bibliography so far is by model agents (D80; `STATUS.md`), so the authors' review
   includes opening each reference and confirming each sentence that cites it.
5. **The venue and the length.** The model reviewer that checked D80's round judged the paper close to a credible
   preprint as a methods or negative-results note, fit for a workshop or an arXiv note but not a main track; for a
   workshop the main text (22 pages at D80, about 23 now) would have to be cut to its page limit (D80, D83). For arXiv,
   the primary category, which
   decides the endorsement route (`docs/submission_readiness.md`).
6. **Naming the models.** Also the model identifier in the committed controlled transcripts, which 439 assistant
   entries carry in their `model` field (CS-01 114, CS-02 162, CS-03 62, CS-04 101; counted in
   `data/controlled/transcripts/*.jsonl`; D79 gives 450, D83): keep it as the raw session
   record, or redact it in a new sanitiser version with the hashes renewed (D79, D80). The decision covers every place
   where the repository names a model family or the agent tool; `paper/README.md` names the main ones, among them the
   decision log (the model family in D14 and D47), `STATUS.md`, `docs/data_card.md`, `data/controlled/README.md`,
   `data/manifests/provenance_index.json` and the commit messages' co-author and session lines; the generator and mapper
   ids under `tasks/*/`, the runs' `analysis.json` files and some scripts, modules and tests also name the agent tool.
7. **D79's defaults**: the title; the AI-assistance statement's "an AI coding agent", with no model named; D72 and D75
   reported by role and kind, without counts; costs per family only; future work without sizes; builder decisions
   disclosed as such; and the author line as a TODO and the working-draft subtitle until posting.
8. **The frozen pilot tables.** Whether they are re-frozen with the restructure's captions; until then they keep
   'reward fidelity', 'pre-specified' and 'full', which App. F explains (D79).
9. **The claim's wording.** D34 narrowed the claim to a conjunction, and D80 states the lead contrast as largely fixed
   by construction. Confirm or revise both, in a new decision-log entry (the log is append-only).

**Builder decisions awaiting review**

10. D63's defaults: first-sample families keep their corrections, and the download records list the fetched repositories
    by URL. D64's builder defaults, among them deviation (i) (decision 17). D69's privacy-tool defaults. D72: the build
    session's task titles reached the contexts of 42 natural generator runs and 13 host coordinators, and nothing was
    regenerated. D73's reading of when D19 runs. D77: the harness relayed a message of the owner into all 28 natural
    agent runs of P5, and nothing was regenerated. D80's four: the move of the natural detail to App. G, the model
    statement's wording, two template sentences changed where the records contradict them, and counting natural
    correction violators as the controlled tasks do.
11. **What S10 admits.** Seven rejections follow from path requirements outside the workspace, generated version modules
    and submodules, and three depend on pip's resolver and a 30-minute limit (D59).
12. **Whether pull-request review comments count as user corrections** for the claim (D47). D64, decision 1, reports
    them as a construct difference.

**Data, privacy and publication**

13. **SWE-chat.** Accept its terms and supply a working token; the saved one fails authentication (D4).
14. **Whether the screening download records keep the fetched repositories' URLs** before publication (D50, D63).
15. **The scan's open rules.** How it treats organisation accounts, before `--aidev-logins` loads both S9 samples (D66);
    and whether standard-library import lines count as idioms in its optional screening-texts mode (D81).
16. **Whether to delete the third-party session data and downloads** kept outside the repository
    (`data/manifests/third_party_downloads.json`).
17. **Git history.** Pushed commits still hold material that was later removed from the working tree, among it the
    exported research prompt, redaction rules and the build session's id; `STATUS.md` lists the commits
    (`docs/internal_review.md`, P1, P7, P9). A rewrite needs a force-push and cannot recall copies already fetched.
18. **The commit trailers.** Whether to keep the co-author and session lines that end every commit message.
19. **The licence of the repository and of released task data.** There is no `LICENSE` file, `pyproject.toml` declares
    none, and `README.md` says the owner has not chosen one (`THIRD_PARTY_LICENSES/README.md`).
20. **Whether, where and when the repository is made public.** The paper's §10 names no repository URL, commit or
    licence (`paper/sections/reproducibility.tex`).

**Spending and next steps**

21. **Any paid model, compute or annotation budget** (default zero). Uses: a second model family; human reviewers;
    `natural-pr-v2`, for which the extension's S10 is to be redone (D66, D71); and a controlled expansion (§7). A
    confirmatory run also needs the draft precision plan adopted by a later protocol version (D49).
22. **The downstream-training plan.** Whether to run it at all, and its open decisions O1 to O8 (plan section 11;
    D82); a later protocol version must adopt it before any part runs.
23. **Whether and when to submit anything** (`docs/submission_readiness.md`).

## 5. Ten hard questions a skeptical expert would ask

**Q1. Is the lead result fixed by construction?**
Largely, yes, and the paper says so (abstract, §1, §3; D80). Every correction violator breaks a requirement that only
the correction states. C1's contract lacks that requirement (in CS-01 it encodes the retracted request instead), C3's
covers it, and the reference checks behind the D19 labels were written from a reference contract that states it. So
24/27 against 0/27 mostly restates the design. Which families show a silent loss and which a loud inversion also follows
largely from what each correction does: C1 passes the reference wherever the correction only adds requirements (CS-02
to CS-04) and fails it in CS-01, whose correction retracts a requirement C1 encodes; and its generator, which saw the
reference diff, did not test the added requirement, as its template asks: it tests its contract and is told not to
over-fit that diff (Q3; paper §1, §3.1). Two things are not fixed by it:
* the violators are agent-made: 27 of the 40 `u1` attempts violate the correction, while with the correction every
  analysed attempt solves its task (19/19 for configuration A and 20/20 for B; D61). The attempts measure information
  lost when the correction is withheld, not an agent's skill (D61);
* B1 fails in the other direction (Q4).

The C3, C4 and B2 zeros on the 27 violators hold only for what the reference checks exercise. Those checks share a
model family with the correction-aware verifiers and cover the same requirements, so the zeros are partly agreement
between two renderings of one requirement list (abstract, §2.3; D80). Robustness:
* the second labeler agrees with D19 on 77 of 79 units (κ 0.94; Q2 says why that is not independence);
* the attempts' contexts held harness material, though no reference, verifier, candidate or label: an environment
  block naming the study repository and the build session's scratch directory, and the titles of the build session's
  task list in the attempts whose audit records them (the CS-04 audit records them in 16 of its 20; D57, D62; paper
  §2.1). Excluding all 26 automatically flagged attempts leaves C1 at 18/21 and C3 at 1/21 (D61).

*Look at:* `results/runs/fresh-v1/analysis.md`, `paper/sections/results_controlled.tex`,
`paper/generated/fresh/numbers.tex` (`cv.*`), `tasks/CS-0*/contracts/`, `tests/test_make_tables_fresh.py`; D61, D62,
D80; paper §2.3, §3.1, §3.4; exercises E3 and E4.

**Q2. Why trust model-proposed labels, and how would human labels arrive?**
Do not treat them as ground truth. For fresh attempts, D19 calls an attempt invalid if any frozen reference check or the
regression norm fails, and valid otherwise (D58). Configuration-A agents wrote the reference checks from the reference
contract (D55; paper §2.3), and only CS-02's went through a review-and-fix loop: the checks that label the silent-loss
attempts of CS-03 and CS-04 were never reviewed (D33; paper §8, item 2). A second labeling exists: per-family labelers
that configuration B wrote from the reference contract, the base snapshot, the harness API and the lint rules only,
frozen before any attempt existed (D55, D58). It agrees on 77 of 79 units. The two disagreements are CS-02 attempts
that D19 marks invalid only because a base test asserts on a private attribute they removed (D62). Both labelings
share the reference contract and one model family with the correction-aware verifiers, so their agreement is not
independence (D80). The scenarios that define the intended requirements were written by the same model as the session
agent (`STATUS.md`).
For the lead result, `review-packet --strata fresh-v1` puts the 79 analysed fresh-attempt patches among the pilot's
held-out candidates, blinded as they are, and `merge-reviews` writes their labels to the stratum's files (§4, item 1);
no reviewer has labelled them yet.
*Look at:* `scripts/propose_labels.py`, `tasks/*/verifiers/reference_check/`, `tasks/*/verifiers/independent_label/`,
`tasks/*/strata/fresh-v1.json`, `src/tracecontract/review.py`, `tests/test_review_packet.py`,
`tests/test_review_packet_strata.py`, `tests/test_independent_labeling.py`; D19, D33, D43, D55, D58, D62; paper §2.3, §8
(items 1 and 2), App. D.5, App. H; exercise E11.

**Q3. What does the reference gate catch, and what does it miss?**
The oracle-gated view drops a verifier-and-task cell when the verifier fails its task's reference solution (protocol
§15.7).
* It catches the loud inversion. In CS-01 the correction retracts part of the first request, and C1 encodes the
  retracted request. C1 fails the reference on 12 of its 14 checks (ran, E4), and its CS-01 cell holds 10 of its 24
  false acceptances and 10 of its 13 false rejections (D62). With the cell dropped, C1 stands at 14/19 and 3/40
  (`analysis.md`, "Oracle-gated view").
* It misses the silent loss. In CS-03 and CS-04 the correction only adds requirements. C1 has no check for them, passes
  both references, and accepts 14 of the 17 violators, against 0 for C3 (`cv.silent.*`). A verifier that passes the
  reference accepts one valid solution; that says nothing about requirements it never tests.
* It misses verifiers that accept everything. B1 passes the unchanged base in NP-03, NP-05, NP-19 and NP-20 (ran, E8),
  which a no-op gate would catch. The fresh run graded no no-op (`analysis.md`, "Sanity checks").
* The audit weakens it. audit:v1 requires the reference to pass, so the natural revisers loosened checks toward the
  reference (D70), and C2 passes all six natural references (ran, E8). Passing the gate then says less.

*Look at:* `src/tracecontract/analysis.py`, `tests/test_new_run_reporting.py`, `tests/test_analysis_natural.py`; the
sanity and oracle-gated sections of both runs' `analysis.md`; D62, D70, D80; paper §3.1, §7 ("The reference gate");
exercises E4, E5 and E8.

**Q4. The audit removed no false acceptance, a transcript-only generator matched the contracts, and the repository's
tests reject 34 of 50 valid attempts. What do the machinery and the baselines add?**
Less than the design hoped, and the paper reports each result as it came out (abstract, §3.2, §3.3).
* **The audit.** On the fresh attempts C2 equals C1 on every outcome, and C4 equals C3 on false acceptance. C4's 6 extra
  false rejections, all in CS-03, come from 2 checks that its single revision added: they fix the answers of edge cases
  the contract leaves open, and the audit record does not show that they were added (D62). In the pilot, four of the
  eight audited verifiers are identical to the plain ones, and on the other four the audit changed one outcome of 32
  (`STATUS.md`). In the natural arm the revisers pulled checks toward the reference (D70): C2 accepts more invalid
  candidates than C1 in NP-03, NP-05 and NP-20 (1/3 against 0/3) and fewer in NP-19 (1/4 against 2/4), and rejects
  fewer valid ones in NP-05, NP-18 and NP-20 (0/2 against 2/2; `results/runs/natural-pr-v1/analysis.md`). Its attacks
  come from the verifier's own contract, so it cannot add a requirement that the contract lacks (paper §2.2).
* **B2** has 2/29 false acceptance, as C3 and C4 do, and 2/50 false rejection; in the pilot it accepts 1/17 against
  C3's 0/17 (`STATUS.md`). Four families can show neither a difference nor equivalence.
* **B1** is the suite a task builder gets without writing tests, and its result is a warning about such suites rather
  than a strawman. All 34 false rejections come from the 40 checks, of 2,219, that the session agent added
  (`b1.checks.*`; D62). The base commit's own tests reject no valid attempt, and alone they accept 17 of the 29
  invalid ones (`analysis.md`, "B1 restricted"); under D19 they cannot reject a valid attempt, since they are the
  regression norm. B1 imports candidate code into its reporting process, so a hostile candidate can forge its report
  (D42). In the natural arm it equals the regression norm in three families and in part a fourth (D64, decision 3),
  and it passes the unchanged base in four (ran, E8).

What is left: one frozen procedure that builds initial-only and correction-aware verifiers, scored on one held-out pool
anchored on agent-made states; contracts whose requirements carry their status, turn and evidence quotes, so a miss can
be traced to a missing requirement (the coverage tables); and two negative findings, that an audit against attacks
from the same model family can fit a verifier to the reference's incidental behaviour, and that it cannot add a
missing requirement. Stronger baselines tied to practice are named and not run: a first-request suite gated on the
pre-correction state, a full-session task statement with test refinement, and an LLM judge (§7).
*Look at:* `src/tracecontract/audit.py` (`run_audit`), `tests/test_audit_record.py`,
`tasks/CS-03/verifiers/full_audited/` against `tasks/CS-03/verifiers/full_plain/`, `tasks/*/verifiers/repo_tests/`,
`tests/test_sandbox_isolation.py::test_in_process_repo_tests_report_is_forgeable_known_limitation`, the paired
comparisons in `analysis.md`; D24, D27, D37, D42, D62, D70; paper §3.2, §3.3, §4, §7; exercise E7.

**Q5. What can four families support statistically?**
Description only.
* Candidates of one family share its session, contracts and verifiers, so the family is the unit. With four families
  the exact sign-flip test's attainable floor is 0.0625 one-sided and 0.125 two-sided, and none of the 14 planned
  comparisons reaches it. C1 against C3 on false acceptance has a one-sided p of 0.125, because CS-02 differs in the
  other direction (`analysis.md`, "Paired comparisons").
* The cluster-bootstrap intervals are in an appendix, marked as not inferential below 10 families (protocol §15.7,
  §16.6).
* `fresh-v1` reuses the pilot's four families and frozen verifiers, so it adds candidates, not families, and it was
  designed after the pilot's results were known (paper §8, item 5). The natural run is six case studies with no pooled
  rate.

A confirmatory study needs more families drawn by a fixed procedure and a primary endpoint fixed in advance; the paper
proposes the reference-gated C1 to C3 difference in false acceptance (§7). It also needs the draft precision plan
adopted by a protocol version (D49).
*Look at:* `src/tracecontract/stats.py`, `tests/test_stats.py`, `tests/test_new_run_reporting.py`; protocol §15.7,
§16.6; D49, D61; paper §2.4, §8 (items 4 and 5), App. A.

**Q6. Why do the natural verifiers fail their own references?**
In `natural-pr-v1`, C1 fails the reference in five of the six families, C3 in four and C4 in two (ran, E8). A natural
reference is the code of the pull request's addressing commit, while the contracts are recovered from the review
thread, and the developer's change does not always do what the contract says the reviewer asked for.
* The P2 generators of NP-03, NP-18 and NP-19 said so before any grade: a content type is left unconverted, a
  requirement's wording is not met, or the fix does not take effect in the task's environment (D70).
* NP-03's reference-check writer found that the reference cannot meet three observables of the reference contract (D72).
* At the first audit the reference fails 9 of the 12 audited verifiers. audit:v1 then holds the reference valid and
  settles each disagreement in its favour (D70).
* Only NP-20 has a record that reads like CS-01's retraction: its correction-aware contract marks a requirement
  superseded, and no other family's contract does (`paper/generated/natural_run/numbers.tex`, keys
  `full.*.superseded`). D70 gives no reason for C1's drop there, so a retraction is a reading, not a recorded fact
  (paper §7).

The case studies therefore say little about corrections (D80):
* C1 and C3 reject every candidate in NP-03, NP-05 and NP-18 (C4 too in NP-03, C1 alone in NP-20);
* B1 passes the unchanged base in four families;
* in NP-04 and NP-19 the correction-aware verifiers accept near misses that break a correction requirement
  (`STATUS.md`).

All six reference-check suites are usable. The second labeler is unusable in NP-03 and NP-19, so those two families
have no second labeling (D72, D75).
*Look at:* `results/runs/natural-pr-v1/analysis.md`, `paper/sections/natural.tex`,
`paper/sections/app_natural_cases.tex`, `tests/test_analysis_natural.py`, `tests/test_natural_template.py`; D64, D70,
D72, D75, D80; paper §5, §7, App. G;
exercise E8.

**Q7. How does grading stop a candidate from forging its reward, and what can a candidate still do?**
Grading is process-separated, with trusted aggregation (D3):
* hidden tests run in a trusted grader;
* candidate code runs as an unprivileged UID unique to its container, with no network, and can neither read the tests
  nor write the results (D3, D29);
* each call's result carries an HMAC, and the host recomputes every outcome, so a missing, stale or unparseable result
  becomes a verifier error, never a pass.

Every real forgery path found so far was closed with a regression probe:
* a module that shadows the standard library (D36);
* an `encodings` package loaded at interpreter start (D40);
* an `ast.py` loaded on the error path (harness 0.3.3, D44);
* failures while a result is formatted or encoded (harness 0.3.5: 17 probe checks fail under 0.3.4; D52);
* in the Harbor export, a world-writable reward directory. Two probes whose candidate code writes its own reward file
  received 1.0 under the earlier exporter. Since `tc-harbor-export/0.2.0` the grade script makes that directory
  root-owned before candidate code runs and removes every reward file it did not write (`harbor_export.py`; D51, D52).

What a candidate can still do:
* within one call, the code that the snippet runs controls what that call reports, and it can detect that it is being
  graded. Every test therefore asserts on a returned value, and the lint flags a test that asserts only on success
  (`ok_only` in `src/tracecontract/verifier.py`; D3, D36, D40); no test can rule out behaviour that differs under test
  (paper App. C);
* a candidate's `__repr__` or `__str__` that runs while a result is formatted can still end or stall that call
  (`STATUS.md`), which ends in a rejection, not a pass;
* B1 can be forged (Q4).

The runs that the harness fixes superseded agree with the final pilot on all 240 pairs (D45), and so does the 0.3.5
re-grade (D54): no recorded outcome changed when a path was closed. No candidate patch in the pool ships a module named
`ast` or `unicodedata` (D44). The Docker probes were not re-run in the checks at `2daa725`; the build session ran
them for D82 (E1).
*Look at:* `src/tracecontract/sandbox/harness/tc_sandbox.py`, `src/tracecontract/sandbox/docker_runner.py`,
`tests/test_sandbox_isolation.py`, `src/tracecontract/harbor_export.py`, `scripts/harbor_validate.sh`,
`results/harbor_validation/`; D29 to D31, D36, D40, D44, D51, D52; paper App. C, §8 ("B1's exploit surface");
exercises E1 and E12.

**Q8. What would a verifier's behaviour under optimisation pressure need that this study did not test?**
Nothing here measures it. Every graded candidate is an agent's honest attempt, a state captured from a session, or a
constructed alternative or near miss written to satisfy or to break a requirement. No verifier was used as a reward
and no training ran (paper §1; §8, "No optimisation pressure"; App. F). The nearest things to selection are that the
pilot's near-miss generators ran B1's tests before registering their near misses (D37), and that the valid alternatives
ran the repository's tests while they were built, which in NP-03, NP-05 and NP-20 are B1's own files (D64, decision 3;
paper App. G.1); B1's outcomes on those candidates are therefore not blind to construction. What the study does
measure is each verifier as a binary reward on honest patches: on the 79 fresh-attempt patches, pooled, Youden's J
is −0.09 for C1 and C2, +0.93 for C3, +0.81 for C4, +0.89 for B2 and +0.32 for B1 (`analysis.md`, pooled table;
descriptive). An optimiser does not sample honest patches; it
searches for what a verifier accepts, so what matters is whether any invalid behaviour passes at all, not how often
honest attempts hit one. A test of that would need, at least:
* candidates found by search against each frozen verifier (best-of-n selection or a trained policy), graded by every
  condition. C1's silent loss is the kind of blind spot such a search finds first: it passes its reference and accepts
  14 of the 17 CS-03 and CS-04 violators (Q3);
* labels outside the optimiser's reach and independent of what it optimises. The reference checks share a model
  family, the reference diff and the requirement lists with C3 and C4 (Q2), so a blind spot they share would pass both;
  the paper names human labels and a labeler from another model family (§7);
* a grader built for adversaries. B1 can be forged and is unsuitable as a reward for adversarial policies (D42; paper
  App. C, §9). The process-separated verifiers keep the in-call limit of Q7, and a missing or failed result is never a
  pass, which keeps a crash or a stall from earning reward;
* adversarial search at construction that can reach outside the contract. audit:v1's development attacks are written
  from the verifier's own contract, each to violate a requirement (paper §2.2), so they cannot expose a requirement
  the contract lacks (Q4);
* more tasks and attempts: four families and k = 5 attempts per family, configuration and variant cannot show the
  absence of an exploit (D56; paper §8, items 4 and 5).

`experiments/downstream_plan_v0.1-draft.md` drafts an experiment of this kind (C1 and C3 as data filters, then as RL
rewards behind the cell gate, human labels as the judge, and a stop rule that, for each condition, reads only the
reference checks of the requirements its own contract covers and stops stage 2 for both conditions when the reward
rises while their pass rate falls, its §7); it is not run and not adopted (D82, D83).

*Look at:* `paper/sections/app_grading.tex` ("Known exploit surface"), `paper/sections/threats.tex` ("No optimisation
pressure"), `paper/sections/ethics.tex` ("Misuse"), `src/tracecontract/verifier.py` (`ok_only`),
`src/tracecontract/audit.py`, `tests/test_sandbox_isolation.py`; D3, D37, D42, D56, D62; exercises E7 and E12.

**Q9. How does the privacy scan avoid false positives without hiding leaks?**
`scripts/scan_tracked_files.py` is a manual step before each push, not a git hook (D44). It reads the working tree and
every file version in the commits a push would send, and looks for:
* credentials, session-local paths, e-mail addresses and private markers (D44);
* the 119 logins and names tied to the first S9 sample, and handles written with a leading at sign under `tasks/` and
  `data/` (D48, D52, D66);
* with `--natural-texts`, the natural tasks' own texts (D69). Texts are matched by windows of 60 characters or of 8
  words. A text with no usable window of words is matched whole if it reaches the minimum: 3 words, with a letter in at
  least two tokens, and 12 characters; or 8 characters of a script without spaces (a builder default; D69).

False positives come from text that natural repositories share with the study's own code, such as imports and call
heads. The idiom rule handles them (D72, extended to the screened comments' short texts in D81). It leaves a text out
only if a line of the pre-natural corpus holds it, with word boundaries. That corpus is the repository at `c5ede4c`,
before any natural task existed, so finding such a text in a tracked file tells nothing about a screened comment.
Still looked for:
* a text with a word of its own, a different case or punctuation, or a window of words;
* a text with any copy that is not an idiom;
* every text of a natural task, which is all that the push gate looks for (D81).

No finding is suppressed by a private list: a suppression option was drafted and withdrawn (D66). The three D81 tests
fail when the rule is switched off, and also when it is applied to every label (ran, E10). On the real data the gate
scan exits 0, and with the screening texts the findings fell from 223 to 1 (D81). Known gaps:
* a repository name that is also an ordinary word is not reported in `docs/`, `paper/`, `src/` or commit messages
  (D69);
* the scan does not know the repositories of NP-07, NP-08 and NP-12, or of screened comments never built (D69);
* the login check covers the first sample only (D66);
* one finding of the optional screening-texts mode remains: a standard-library import line of the study's own code
  (D81).

*Look at:* `src/tracecontract/natural_privacy.py` (`TextWindows`, `CodeLines`, `_held_within`),
`scripts/publish_natural_run.py`, `tests/test_scan_natural.py`; D44, D66, D69, D72, D78, D81; paper §9 ("Natural data
and privacy"), App. B; exercise E10.

**Q10. How would this scale to thousands of traces?**
Not as built. The records show where the cost lies.
* **Yield.** S10 accepted 6 of the 22 built first-sample families: 6 tasks from 150 sampled comments (4.0%; D59). The
  rejections were collection failures, unresolvable or oversized dependency closures, an empty test subset, a fetch cap
  and the merge rule. The accepted tasks lean toward small repositories with plain test setups (D59).
* **Agent cost.** Each natural family has 26 generated artifacts with a generation record. On average an accepted
  natural task took 947.7 agent turns, 1,178.0 tool calls and 32,404.9 s of agent wall time
  (`results/runs/natural-pr-v1/analysis.md`, "Cost and time per accepted task"). Round 5, which ran phases P1 to P4
  for the six families and also finished D69's analysis and privacy packages, used about 37.2M reported agent tokens
  since the reset; per family, P1 took about 0.6M, P2 2.3M to 3.3M, P3 0.7M to 2.8M and P4 about 0.4M to 0.5M (D70;
  `STATUS.md`, "Done in round 5"). The cost of generating the
  controlled verifiers was not recorded (paper §3.4; D42).
* **Audits.** The agents' transcripts are audited and their flags read by hand: 26 of the 80 fresh attempts were
  flagged automatically (D61), and the natural audits found 578 hits in 163 records, each assessed in writing (D75).
  Those transcripts stay outside the repository, identified by hash, so a third party cannot re-check the audits
  (paper §10).
* **Labels.** The latest planning estimate, from assumed times and not measurements, is the draft precision plan's
  (`experiments/precision_plan_v1.0-draft.md` §9; D49): with two reviewers per task and adjudication, 20.5 / 38.9 /
  78.2 person-hours for the pilot's 31-item packet and 4.1 / 7.8 / 15.6 hours per confirmatory family with 6 items. The
  research brief's earlier figure, 1.5 to 3 annotator-hours per task family (`docs/research_brief.md` §7.2), is lower.
  With the fresh attempts the packet holds 110 items (D82), which §9 did not size. Model labels share a model family
  and a reference contract with what they score (Q2).
* **Grading** is the cheap part: on average 2,598.9 s of summed pair wall time per accepted natural task (same table).
  Before per-container UIDs, outcomes could depend on unrelated concurrent load; since harness 0.2.0 they cannot in
  that way (D29), which parallel grading would need.

Untested proposals for scale:
* environment replay as a cached service with a measured acceptance rate;
* the reference gate and a no-op gate as cheap filters for broken verifiers, knowing that neither catches a silent
  loss (Q3);
* labels from a second model family, with human labels on a stratified sample to measure their agreement;
* clustering by repository once a population has 10 or more tasks (D64, decision 10).

*Look at:* `src/tracecontract/natural_pr.py`, `tests/test_compile_pr_task.py`,
`data/manifests/natural_tasks_index.json`, the build, replay and cost sections of
`results/runs/natural-pr-v1/analysis.md`; D59, D63, D66, D70, D75; paper §10, App. G.

## 6. Exercises to understand and modify the core system

Run these from the repository root, with `.venv` made as the README's "Reproduce" section says and
`PYTHONDONTWRITEBYTECODE=1` set. Exercises that change code or records (E7, E9, E10, E12 and every "To modify" step)
are for a scratch clone or a branch; the others only read records, write to git-ignored paths or outside the
repository, or rewrite tracked files with identical bytes (E2). Afterwards `git status` and
`.venv/bin/python scripts/verify_frozen_inputs.py` show whether anything frozen changed. With the four snapshots built
(E5), the latter reports OK on this commit: 0 frozen files changed, 130 of 135 input hashes matching (the other 5 are
analysis code, exempt) and 4 of 4 snapshots matching (ran). `<scratch>` stands for a new directory outside the
repository. Every command below was run for this update, except where an exercise says it was not.

**E1. Run the tests.**
`.venv/bin/python -m pytest -q -m "not docker"`, then `.venv/bin/python -m pytest -q -m docker`.
Observe (ran on 2026-11-24 with this round's 90 new tests, D82: 17 in `tests/test_review_packet_strata.py` and 73 in
`tests/test_build_training_selection.py`; in a checkout without the git-ignored `data/natural/`, with the Docker daemon
up):
* with the base snapshots built (E5): 1,435 passed and 9 skipped, each naming the natural data it needs;
* without them: 1,421 passed and 23 skipped (14 name the snapshot to build);
* with the daemon down, pytest skips the Docker probe module at collection, which adds one skip and leaves 1 deselected
  test instead of 20.

At `2daa725` (1,354 offline tests), with the daemon down, the same commands gave 1,345 passed with the snapshots, in
about 4 minutes, and 1,331 without them.

The Docker suite's 20 tests passed on 2026-11-24 in the build checkout with this round's changes (D82), as they did on
2026-11-23 at `2daa725` and at `a0542bb` (D52). In the build checkout, which holds the natural data, all 1,444
offline tests passed (D82).
Then read `tests/test_sandbox_isolation.py`. Most probes try to break the grading boundary, and each regression probe
names in its docstring the decision-log entry of the defect it guards (D29, D30, D36, D40, D44, D46, D51).

**E2. Trace a number from the paper to its record, and build the paper.**
`grep -n 'cv.silent.c1' paper/sections/*.tex paper/generated/fresh/numbers.tex paper/evidence_ledger_fresh.md`, then
`.venv/bin/python paper/check_numbers.py`.
Observe:
* `\fv{cv.silent.c1}` appears in the abstract, the introduction and Section 3; `numbers.tex` defines it as 14/17; the
  ledger names the field of `results/runs/fresh-v1/analysis.json` it comes from;
* the checker prints `22 file(s); 0 digits, 0 count words, 0 missing keys; OK`;
* in a scratch copy of `paper/` (`git archive HEAD paper | tar -x -C <scratch>`), append "The run graded 79 patches
  with three verifiers." to `paper/sections/pilot.tex` and run the copy's checker: it reports `digit: 79` and
  `count word: three` and exits 1.

Next, run `.venv/bin/python paper/make_tables.py --fresh results/runs/fresh-v1 --regrade
results/runs/pilot-v0.3.5-regrade --natural` and `cd paper && latexmk -pdf main.tex`. Observe "wrote 17 files to
paper/generated/fresh" (1,358 ledger
entries) and "wrote 4 files to paper/generated/natural" (217). The generator rewrites tracked files with identical
bytes, and the build's outputs are git-ignored, so `git status` stays empty. The build (run in a scratch copy on
2026-11-24, after the corrections that followed the reviews of `f3ae845`) gives a 77-page PDF in about 10 s: Section
10 begins on page 23, where the references start, and App. A on page 27; the log has no overfull box and no LaTeX
warning, and the PDF's text has one TODO, the author line.

**E3. Re-derive the lead analysis from the recorded results, without grading.**
`cp -r results/runs/fresh-v1 <scratch>/fresh-v1`, then
`.venv/bin/tracecontract analyze <scratch>/fresh-v1 --allow-proposed-labels`, then
`cmp results/runs/fresh-v1/analysis.md <scratch>/fresh-v1/analysis.md`.
Observe:
* the analysis takes about 3 s, and `analysis.md` is byte-identical;
* `analysis.json` differs only in the hashes of three analysis files changed since the run (`analysis.py`,
  `schemas.py`, `store.py`) and in the git revision, which is null for a copy outside any git work tree.

To regenerate the report as well, start from a second copy and give the analysis the four audits' exclusions:

```bash
cp -r results/runs/fresh-v1 <scratch>/fresh-v1-full
.venv/bin/tracecontract analyze <scratch>/fresh-v1-full --allow-proposed-labels $(for t in CS-01 CS-02 CS-03 CS-04; do echo --sensitivity-exclusions data/fresh/fresh-v1/audit_$t.json; done)
.venv/bin/tracecontract report <scratch>/fresh-v1-full --out <scratch>/fresh-v1-full/report.html
cmp results/runs/fresh-v1/report.html <scratch>/fresh-v1-full/report.html
```

Observe that `analysis.md` and `report.html` are byte-identical, in about 6 s for the two commands. Then read the
primary per-family table, the "Oracle-gated view" and "B1 restricted to the base commit's own tests".

**E4. See the loud inversion and the silent loss in the recorded per-check output.**

```bash
.venv/bin/python - <<'EOF'
import json
for line in open("results/runs/fresh-v1/results.jsonl"):
    r = json.loads(line)
    if r["verifier_id"] == "initial_plain" and r["candidate_id"].endswith("-reference"):
        bad = [c["check_id"] for c in r["checks"] if c["status"] != "passed"]
        print(r["task_id"], r["outcome"], f"{len(bad)} of {len(r['checks'])} checks fail")
EOF
```

Observe: CS-01 `task_failure` with 12 of 14 checks failing, and CS-02 to CS-04 `pass` with none failing.

Then open `tasks/CS-04/contracts/initial_only.json` and `full_session.json`. The initial-only contract marks zero and
negative steps unresolved and unscored (R5). The full-session contract has the requirements that the correction turn
introduces, among them negative steps, `step=0` raising, `ordering` kept as the second positional parameter and lazy
groups. In the CS-04 table of `analysis.md`, C1 passes all ten `u1` attempts and C3 rejects all ten. The violators
break R-zero-step, and none of C1's 12 checks maps to it under either mapper (`paper/generated/fresh/numbers.tex`, keys
`beh.cs04.broken` and `c1.cs04.checks.broken`).

**E5. Rebuild the bases, check them against the session, and grade live (the grades need Docker).**
`for t in CS-01 CS-02 CS-03 CS-04; do .venv/bin/tracecontract snapshot tasks/$t; done`; then
`.venv/bin/tracecontract reconstruction-check tasks/CS-01; echo $?`; then
`.venv/bin/tracecontract grade tasks/CS-01 initial_plain CS-01-reference`, followed by the same command with
`initial_plain CS-01-pre-correction` and with `full_audited CS-01-pre-correction`.
Observe:
* every snapshot reports `"manifest_matches": true` (ran; rebuilt here from the local fetch cache, while an empty cache
  fetches the pinned commit from GitHub);
* the reconstruction check exits 0, and its output equals the committed `tasks/<id>/reconstruction_check.json` (ran
  for each of the four tasks);
* the three grades were not run for this update, because the Docker daemon was down. The recorded outcomes, which the
  command below prints, are: C1 on the reference `task_failure`, 12 of its 14 checks failed; C1 accepts the
  pre-correction state, with all 14 checks passed; C4 rejects it, with all 14 failed. Each holds under harness 0.3.3
  (`pilot-v0.3.3`) and 0.3.5 (`pilot-v0.3.5-regrade`), and the first also in `fresh-v1`.

```bash
.venv/bin/python - <<'EOF'
import json
want = {("initial_plain", "CS-01-reference"), ("initial_plain", "CS-01-pre-correction"), ("full_audited", "CS-01-pre-correction")}
for run in ("pilot-v0.3.3", "pilot-v0.3.5-regrade"):
    for line in open(f"results/runs/{run}/results.jsonl"):
        r = json.loads(line)
        if (r["verifier_id"], r["candidate_id"]) in want:
            ok = sum(c["status"] == "passed" for c in r["checks"])
            print(run, r["verifier_id"], r["candidate_id"], r["outcome"], f"{ok}/{len(r['checks'])} passed", r["harness_version"])
EOF
```

**E6. Run the acceptance gate.**
`.venv/bin/tracecontract accept-task tasks/CS-01 --dry-run; echo $?`
Observe: exit 1 and `"passed": false`, with 11 reasons:
* the provenance record is `pending_review`;
* four reference requirements have no human review;
* the initial-only and full-session contracts hold unresolved requirements and unreviewed inferred ones.

Nothing is changed. This is why every run so far carries `--pilot`.

**E7. Make the audit's mapped-attack rule blocking (scratch clone).**
audit:v1 asks each development attack to fail a check mapped to the requirement it targets, but an attack that fails
only other checks is a finding that does not fail the audit (`run_audit` in `src/tracecontract/audit.py`; paper §2.2).
`run_audit` takes the grader as an argument, so the rule can be exercised without Docker, with the helpers of
`tests/test_patches_verifier_metrics.py`:

```bash
.venv/bin/python - <<'EOF'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "tests")
import test_patches_verifier_metrics as T
from tracecontract.audit import run_audit
from tracecontract.schemas import CandidateOrigin, CheckResult, CheckSpec, Outcome, VerificationResult

task = Path(tempfile.mkdtemp())
T._tree(task / "tests", {"test_a.py": T.GOOD_TEST})
spec = T._spec().model_copy(update={"checks": [CheckSpec(check_id="test_a.py::t1", requirement_ids=["R1"]),
                                               CheckSpec(check_id="test_a.py::t2", requirement_ids=["R2"])]})
failing = {"ref": [], "noop": ["test_a.py::t1", "test_a.py::t2"], "atk": ["test_a.py::t2"], "alt": []}

def grade(s, c, repeats):
    bad = failing[c.candidate_id]
    return VerificationResult(run_id="r", task_id="t", verifier_id="v", candidate_id=c.candidate_id,
                              outcome=Outcome.task_failure if bad else Outcome.passed, reward=0.0 if bad else 1.0,
                              started_at="s", finished_at="f", wall_s=0, harness_version="h",
                              checks=[CheckResult(check_id=k.check_id, status="failed" if k.check_id in bad else "passed")
                                      for k in s.checks])

dev = [T._cand("ref", CandidateOrigin.reference), T._cand("noop", CandidateOrigin.noop),
       T._cand("atk", CandidateOrigin.dev_attack, violated=["R1"]), T._cand("alt", CandidateOrigin.valid_alternative)]
rep = run_audit(spec, None, dev, grade, task_dir=task)
print("audit passed:", rep.passed)
for f in rep.findings:
    print(" ", f.code, "|", f.message)
EOF
```

Observe: `audit passed: True`, with the one finding `attack_caught_by_unrelated_check | atk targeted ['R1'] but only
failed ['test_a.py::t2']`: the attack breaks R1, yet only an R2 check catches it.
To modify: add `"attack_caught_by_unrelated_check"` to the `blocking` set at the end of `run_audit` and rerun. The audit
now fails. `.venv/bin/python -m pytest -q tests/test_patches_verifier_metrics.py tests/test_audit_record.py` still
passes (64 tests), so no test pins the rule either way: add one. The recorded audits ran under the committed rule
(`PROCEDURE = "audit:v1"`); a changed rule is a new procedure, and its effect on the recorded verifiers is unknown until
their audits are re-run, which grades in Docker.

**E8. Apply the reference gate and a no-op gate to the natural run.**

```bash
.venv/bin/python - <<'EOF'
import json
rows = [json.loads(line) for line in open("results/runs/natural-pr-v1/results_public.jsonl")]
for v in sorted({r["verifier_id"] for r in rows}):
    mine = [r for r in rows if r["verifier_id"] == v]
    ref = [r["task_id"] for r in mine if r["candidate_id"].endswith("-reference") and r["outcome"] != "pass"]
    noop = [r["task_id"] for r in mine if r["candidate_id"].endswith("-noop-eval") and r["outcome"] == "pass"]
    print(f"{v:18} fails its reference: {', '.join(ref) or 'none'}; passes the no-op: {', '.join(noop) or 'none'}")
EOF
```

Observe:
* `initial_plain` fails its reference in NP-03, NP-05, NP-18, NP-19 and NP-20, `full_plain` in NP-03, NP-05, NP-18 and
  NP-19, and `full_audited` in NP-03 and NP-19;
* `independent_label` fails its reference in NP-03 and NP-19, the two families where it is unusable;
* `repo_tests` passes the no-op in NP-03, NP-05, NP-19 and NP-20;
* `initial_audited`, `llm_freeform`, `diff_derived` and `reference_check` fail no reference and pass no no-op.

To modify: add the no-op gate to `src/tracecontract/analysis.py` as an exploratory view beside the oracle-gated view,
with a test. On this run it would drop exactly the four B1 cells above; `fresh-v1` graded no no-op.

**E9. Simulate a changed base and watch the reconstruction check catch it (scratch clone, snapshots built).**
First run `sed -i '1s/.*/"""Bits and bytes related humanization (changed in the base)."""/'
snapshots/CS-01/src/humanize/filesize.py`, then `.venv/bin/tracecontract reconstruction-check tasks/CS-01; echo $?`.
Observe exit 2, incomplete: every check is unavailable, because the snapshot's manifest no longer matches
`snapshot.json` ("rebuild it").

Then re-record the manifest, as a build from a changed base would:

```bash
.venv/bin/python -c "import json; from pathlib import Path; from tracecontract.tasks import manifest, manifest_sha256; p = Path('tasks/CS-01/snapshot.json'); s = json.loads(p.read_text()); s['file_manifest_sha256'] = manifest_sha256(manifest(Path('snapshots/CS-01'))); p.write_text(json.dumps(s, indent=2) + '\n')"
.venv/bin/tracecontract reconstruction-check tasks/CS-01; echo $?
```

Observe exit 1, failed. Check c (reads match the base) fails on `src/humanize/filesize.py` with "differs from the base
content", because the session read the original first line while the file was in its base state, and check d (the
start-of-session manifest) fails too. To restore, run `git checkout tasks/CS-01/snapshot.json` and
`tracecontract snapshot tasks/CS-01`, which rebuilds the snapshot with `"manifest_matches": true`; the check then
exits 0 again.

**E10. Break the scanner's idiom rule and watch its tests catch it (scratch clone).**
`.venv/bin/python -m pytest -q tests/test_scan_natural.py -k screened` selects the three synthetic tests of D81, which
pass.
* In `TextWindows.__init__` (`src/tracecontract/natural_privacy.py`), replace `if generic and idiom_labels:` with
  `if False:` and rerun. All three fail.
* Restore it. Then apply the rule to every label instead: change the `if` to `if generic:` and drop both
  `label in idiom_labels` conditions. All three fail again, while the file's other tests pass (35 passed, 1 skipped
  for the natural data).

Both directions are guarded. Leaving out too little reports idioms as findings, as in D78. Leaving out too much hides a
natural task's own text, which the gate must report.

**E11. Put the fresh attempts into the review packet, and break the merge's file check (§4 item 1).**
`.venv/bin/python -c "from pathlib import Path; from tracecontract.review import held_out, stratum_held_out; print({t: (len(held_out(Path('tasks') / t)), len(stratum_held_out(Path('tasks') / t, ['fresh-v1'])[0])) for t in ['CS-01', 'CS-02', 'CS-03', 'CS-04']})"`
Observe `{'CS-01': (8, 20), 'CS-02': (8, 19), 'CS-03': (8, 20), 'CS-04': (8, 20)}`: each task's 8 held-out candidates
of its own and the fresh attempts that `--strata fresh-v1` adds, 79 in all, the 79 that the analysis queues for review
(ran). For CS-02, the second value that `stratum_held_out()` returns names the attempt left out,
CS-02-fresh-A-final-1, with the reason "the fresh-attempt audit found a read of forbidden material" (ran).

`tracecontract review-packet <the four tasks> --strata fresh-v1 --out <dir> --key <file> --seed <n>` refuses, before
writing anything, an output directory inside the repository or another git work tree that does not ignore it, in an
agent tool's session directories, or in the third-party data directory (`private_location_problem` in
`src/tracecontract/evaluate.py`). Observe exit 1 and "review-packet refused, nothing written" for a directory in the
checkout and for one in the session scratch directory (ran). Given a directory outside all of them, it writes the
packet and prints its counts; that export was not run for this update, whose commands ran in a session scratch
directory. Grouped as the export groups them, one item per distinct graded diff (ran, read-only), the four tasks give
28, 27, 28 and 27 items: 110 items for 111 candidates, since two CS-04 pilot candidates have the same diff.

To modify, in a scratch clone: `merge_labels` (`src/tracecontract/review.py`) finds each stratum candidate's file as
the key recorded it, and refuses when the stratum no longer lists that file. Replace
`if found is None or found[0] != rec["file"]:` with `if found is None:` and run
`.venv/bin/python -m pytest -q tests/test_review_packet_strata.py`. Observe 1 failed and 16 passed: the case `moved`,
in which the stratum lists the same candidate and patch under another file name, is no longer refused (ran). Restore
the line.

**E12. Try to forge a result (needs Docker; not run for this update).**
Read `test_stdlib_shadow_cannot_forge_results`, `test_startup_encodings_shadow_cannot_forge_results` and
`test_error_path_lazy_import_cannot_forge_results` in `tests/test_sandbox_isolation.py`. Then write a probe of your own,
for example one that changes `/work` between two `run_python` calls, and run it with
`.venv/bin/python -m pytest -q -m docker tests/test_sandbox_isolation.py -k <name>`.
Observe whether the forged value reaches the host's outcome. If it does, you have found a defect. Handle it as D36, D40
and D44 did: a fix, a regression probe, a new harness version and a re-run.

The Harbor version of this exercise was not re-run either: it needs a Harbor 0.25.0 CLI in a separate environment
(`CONTROL_REV=c5ede4c HARBOR=/path/to/harbor scripts/harbor_validate.sh`; the script's header says how to install it).
The recorded outputs (`results/harbor_validation/tc-harbor-export-0.3.0/`; D52) are oracle 1.0, a wrong candidate 0.0,
the no-op 0.0, and no reward on either planted-reward probe. The control run with the exporter of `c5ede4c` gives 1.0
on both probes.
