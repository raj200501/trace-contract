# Submission readiness

Updated 2026-11-25 (UTC), when the owner's open decisions were settled on the owner's instruction (D84). The check of
2026-11-23 ran at commit `2daa725`, after decision-log entry D81; a recheck on 2026-11-24 covers changes that D82
records: the review packet's candidate strata, the abstract's
rewrite and the new threat on optimisation pressure, and the documents brought up to date. Nothing has been uploaded
or submitted, and no endorser or anyone else has been contacted: each of these needs the repository owner's explicit
instruction. All labels in the study are model proposals; no human label exists. Numbers below come from the records
cited or from the commands of the checks, whose results are in the checklist and in the tables of results below it.

## Status: final draft, ready for the author's review and upload; not submitted

* **The manuscript** (`paper/main.tex`) is a complete draft, and every number in it is a generated macro with an
  evidence-ledger entry. Built from a clean copy of the tracked files (TeX Live 2023, `latexmk -pdf`), it has 77 pages:
  the main text on pages 1 to 23 (Section 10 begins and ends on page 23, where the references begin), and Appendices A
  to I from page 27. The log has no overfull box, no LaTeX warning and no undefined reference or citation, and Biber
  reports no warning. The PDF text has no TODO and no `UNFILLED` marker (D84 set the author line). D82 recorded 76
  pages, with the references from page 23, before the corrections that followed the reviews of `f3ae845`.
* **What the last independent review judged (D80).** A fresh verification of the D79 manuscript had two lenses.
  * The accuracy reviewer traced more than 40 numbers to their records and found none wrong.
  * The venue reviewer judged the paper honest and traceable, but not yet a credible preprint: no human author had
    reviewed it; the text did not say that the lead controlled contrast is largely fixed by the design; a sentence
    presented the natural case studies' non-discriminating outcomes as findings; related work lacked three
    literatures; and the main text read as a lab notebook.
  * A fix round followed, and a reviewer checked it; a second round fixed ten of that reviewer's eleven findings, and
    the eleventh is the owner's. That reviewer judged the paper "close to a credible preprint as a methods or
    negative-results note, fit for a workshop or an arXiv note but not a main track"; for a workshop, the main text (22
    pages at D80,
    about 23 now) would have to be cut to the venue's page limit.
  * Like every review so far, these were reviews by model agents (the paper's Section 9: models alone wrote the
    internal reviews). No human has reviewed the paper.
* **What remains before upload.** The author line, the licences, the repository link and the other owner decisions
  are settled (D84). Three things remain: reading the paper and its references against the records, since every
  check so far is by model agents; the endorsement for cs.SE, which is automatic only with an institutional address
  and a claimed arXiv paper in the domain and otherwise needs an endorser (arXiv check); and the upload itself, with
  the source package of the checklist. The endorsement and the upload need the owner's explicit instruction. No
  human label exists (gap 1), and the paper says so.
* **Found in the check of 2026-11-23, for the human review.** None of these changes a number.
  * Appendix H and protocol §15.4 say that every analysed fresh attempt is queued for the review packet, which at
    `2daa725` could not take them. `tracecontract review-packet --strata fresh-v1` now puts them in the packet, and
    `merge-reviews` merges their labels (D82; gap 1).
  * The paper linked no repository, while Section 10 described what "the repository" holds, and arXiv asks that
    links to code or data resolve to a public repository. Section 10 now gives the public repository's address and
    licences (D84).

## Evidence gaps, and what would close each

1. **No human labels.** The labels are the label rule D19's proposals and the verdicts of an independent labeler,
   which configuration B writes. They agree on 77 of the 79 graded fresh-attempt units (Cohen's kappa 0.94;
   `results/runs/fresh-v1/analysis.md`). Both are made by models. By the study's procedure, the reference checks
   behind D19 and the correction-aware verifiers C3 and C4 are written by models of the same model family, from the
   same reference diff, and from requirement lists that the mappers judge to cover the same requirements (paper
   §2.3), so their blind spots are likely correlated.
   * *The human-label path.* The fresh-v1 attempts are stratum candidates (`tasks/<id>/strata/fresh-v1.json`): no
     `task.json` lists them, and no `labels/review_queue.json` holds them.
     `tracecontract review-packet ... --strata fresh-v1` (`stratum_held_out` in `src/tracecontract/review.py`;
     annotation guide, section 2; D82) puts the 79 analysed attempts among each task's own held-out candidates,
     blinded as they are, and leaves out the excluded CS-02-fresh-A-final-1. On the recorded tasks such a packet holds
     110 items for 111 candidates, because two CS-04 pilot candidates have the same diff and share an id.
     `tracecontract merge-reviews` appends the attempts' labels to their files in the stratum. No human label exists
     yet. For the natural arm no packet is prepared (D64, decision 8).
   * *To close it:* two qualified human reviewers per task label from the blinded packet built with `--strata fresh-v1`,
     following `docs/annotation_guide.md` (v0.4); the labels are merged; and the paper reports them beside D19's and the
     labeler's, with their agreement. Human review alone cannot open the acceptance gate (D51): no command sets an
     `eligible` provenance record, and the condition contracts hold unresolved requirements by design. The gate keeps its
     rules (D84; below).
2. **Scale.** There are four controlled families, and no exact sign-flip test over them can go below p = 0.0625
   one-sided or 0.125 two-sided (`results/runs/fresh-v1/analysis.md`). Every controlled result is therefore
   descriptive, and the lead contrast is largely fixed by the design (D80). The natural run has six families of its
   own, fewer than 10, so nothing is pooled over them: they are case studies, reported per family (protocol §19.6,
   §20.3; D78).
   * *To close it:* a controlled expansion with more families, drawn by a fixed procedure, with a primary endpoint
     fixed in advance; the paper's discussion names the reference-gated C1–C3 difference in false acceptance. For the
     natural arm, runs with 10 or more accepted tasks.
3. **One model family; scenarios by the study's agent.** By the study's procedure, every model-written artifact comes
   from one model family of one provider, and configurations A and B are two tiers of it (paper §2.1, App. F). The
   fresh attempts' context also held the build session's task-list reminders and an environment block naming the study
   repository (protocol §18.2). The controlled sessions' user turns, the corrections included, were scripted by the
   study's agent, and each session was designed to contain a correction, so the feedback is synthetic and its frequency
   and content are not natural (paper §2.1; §8, item 7).
   * *To close it:* a second model family, at least for the verifier generators and the labeler (any spending needs
     the owner's approval), fresh attempts with a restricted tool set and no harness task lists (protocol §18.3),
     and, for the scripted corrections, natural corrections at scale (gap 4). Until then the limitation stays stated,
     as the paper states it (Sections 1, 2, 8 and 9; D80).
4. **The natural arm's limits.**
   * The screening was judged by models: 31 of 150 and 91 of 534 sampled comments qualify at S9 (D63, D66). No human
     has coded them.
   * S10 accepted 6 of the first sample's 22 families (D59). The extension's S10, for 19 families, was stopped and is
     to be redone (D66, D75).
   * At the first audit the natural reference fails 9 of the 12 audited verifiers, and five audits stay failing after
     three revisions (STATUS.md).
   * Read with the reference gate, the case studies say little about corrections (D80). C1 and C3 reject every
     candidate, their reference included, in NP-03, NP-05 and NP-18 (C4 too in NP-03, and C1 alone in NP-20), and the
     repository tests pass the unchanged base in NP-03, NP-05, NP-19 and NP-20. In NP-04 and NP-19 the
     correction-aware verifiers accept near misses that break a correction requirement.
   * The release holds only identifiers, hashes, counts and outcomes, so the natural arm cannot be re-graded from it
     (paper §10). Pull-request review comments do not count as user corrections for the claim (D47, D84), and
     SWE-chat stays unused, its terms not accepted (D4).
   * *To close them:* redo the extension's S10 and build its accepted families through P1 to P7 for `natural-pr-v2`
     (STATUS.md); have humans code the S9 screening; and keep families whose reference passes the verifiers that
     grade it, so that a rejection tells something about the candidate.
5. **No downstream training.** No model was trained, so nothing here measures what training on these environments
   does, and no verifier was used as a reward under optimisation (paper §8). `experiments/downstream_plan_v0.1-draft.md`
   is a draft plan, not run and not adopted: rejection-sampling fine-tuning and then RL, with C1 against C3 as the data
   filters and rewards behind a reference gate, matched budgets, held-out repositories and human labels as the judge.
   It also says why the present families cannot support the experiment. Its data step is tested
   (`scripts/build_training_selection.py`), and on `fresh-v1` it gives a post hoc illustration of what each verifier
   would admit, which measures no training value (D82).
   * *To close it:* the owner's approval of the spending and compute; a protocol version that adopts the plan; new
     correction-bearing families, split by repository; and the plan's stage-0 pool, graded with the no-op.

## Decisions of the owner

On 2026-11-25 the owner asked the build session to settle the open owner decisions, said that the work is the
owner's alone and gave the owner's Cornell address. D84 records each decision, and where the author's name comes
from; none is a review of the work by a person. In brief:

**Settled (D84)**
* The author line: Raj Kashikar, Cornell University (rsk239@cornell.edu). Section 9 names one author, who is
  responsible for the content; no competing-interests statement is added, and the author adds one if any applies.
* The licences: MIT for the code (`LICENSE`), CC BY 4.0 for the study's data, documentation and text
  (`LICENSE-DATA`), and third-party material under its own (`THIRD_PARTY_LICENSES/README.md`); CC BY 4.0 for the arXiv
  version; `CITATION.cff` for citations.
* The venue: an arXiv preprint, primary category cs.SE, cross-listed to cs.LG, at its present length.
* The models stay unnamed. The committed controlled transcripts keep the model identifier that 439 assistant entries
  carry in their `model` field (CS-01 114, CS-02 162, CS-03 62, CS-04 101; D79 gives 450, D83), since redacting it
  would change frozen inputs. The other places that name a model family or the agent tool stay as they are; the main
  ones are listed in `paper/README.md`.
* D79's defaults are adopted, the working-draft subtitle is removed and the date is fixed. The frozen pilot tables
  keep their captions (App. F). The claim is the paper's present statement of contribution, with D80's statement that
  the lead contrast is largely fixed by construction.
* The builder decisions that awaited review (D63, D64 with deviation (i), D69, D72, D73, D77 and D80's four) are
  adopted as recorded, without a review, and S10's rejections stand (D59). Pull-request review comments do not count as
  in-session user corrections for the claim; the natural arm stays case studies.
* The screening download records keep the repositories' URLs (D50, D63). The scan keeps its present scope (D66), and
  standard-library import lines are not idioms (D81). The third-party data outside the repository is kept.
* The acceptance gate keeps its rules (DOCU-23, D51) and keeps checking the condition contracts; provenance reviews go
  in a sidecar; `merge-reviews` may write into the frozen candidate, contract and stratum files, and the decision-log
  entry of a merge gives the new hashes.
* The git history is not rewritten: the frozen-input check, `--design` and the records' commit hashes depend on it,
  and a rewrite could not recall copies already fetched. Pushed commits keep the material that STATUS.md lists, the
  owner's context among it. The commit messages' co-author and session lines stay.
* The repository is public; Section 10 gives its address and licences.

**Still open (people, money or the owner's own act)**
* The author's review of the paper and of each reference before upload (the brief; every check so far is by model
  agents).
* Human labels (gap 1), the provenance reviews, and human coding of the S9 screening.
* Any spending: a second model family, human reviewers, `natural-pr-v2`, a controlled expansion and the
  downstream-training plan, which stays a draft (D82). SWE-chat's terms, if it is to be used (D4).
* Whether and when to submit, and the endorsement; nothing is uploaded or submitted without the owner's explicit
  instruction.

## Pre-posting checklist

Run from the repository root with the environment of README.md (`.venv`, and a TeX distribution with `latexmk` and
`biber`). Each regeneration must leave `git status` empty.

**Rebuild and check**
- [ ] Rebuild the base snapshots from their pinned commits (needs github.com):
      `for t in CS-01 CS-02 CS-03 CS-04; do .venv/bin/tracecontract snapshot tasks/$t; done`
- [ ] Regenerate the tables, numbers and figures (`paper/README.md`):

  ```bash
  .venv/bin/python paper/make_tables.py results/runs/pilot-v0.3.3 --compare results/runs/pilot-v0.3.2 results/runs/pilot-v0.3.1 results/runs/pilot-v0.3 results/runs/pilot-v0.2 results/runs/pilot-v0.2-h2
  .venv/bin/python paper/make_tables.py --fresh results/runs/fresh-v1 --regrade results/runs/pilot-v0.3.5-regrade --natural
  .venv/bin/python paper/make_tables.py --pilot-numbers results/runs/pilot-v0.3.3
  .venv/bin/python paper/make_tables.py --design
  .venv/bin/python paper/make_tables.py --natural-run results/runs/natural-pr-v1
  .venv/bin/python paper/make_figures.py results/runs/fresh-v1
  ```
- [ ] `.venv/bin/python scripts/verify_frozen_inputs.py`: the frozen pilot's inputs and outputs (it needs the
      snapshots).
- [ ] `.venv/bin/python scripts/check_abstract.py`: at most 1,900 characters with the macros expanded (arXiv's limit
      is 1,920). Its `--print` gives the text for arXiv's abstract field, which takes ASCII only.
- [ ] `.venv/bin/python paper/check_numbers.py`: no digit or count word outside a number macro, and no missing key.
- [ ] `.venv/bin/python -m pytest -q -m "not docker"` and `.venv/bin/python -m pytest -q -m docker`.
- [ ] From a clean copy of the tracked paper files, `cd paper && latexmk -pdf main.tex`. The log must have no overfull
      box, no LaTeX warning and no undefined reference or citation. The PDF text must have no `UNFILLED` marker, no
      TODO, and no model, provider or agent-product name.
- [ ] Before any push, the pre-push scan with the private markers and the natural checks, which must exit 0 (README.md;
      D44, D69): `.venv/bin/python -I scripts/scan_tracked_files.py --private-markers <file kept outside the
      repository> --aidev-logins <AIDev directory> --natural-texts data/natural/tasks`.

Results of the check of 2026-11-23 (22:44Z to 23:05Z, commit `2daa725`, in an isolated worktree of the repository):

| Step | Result |
| --- | --- |
| Base snapshots | 4 of 4 rebuilt, each matching its manifest |
| Pilot tables, `--fresh` with `--regrade`, `--pilot-numbers`, `--design`, `make_figures.py` | outputs byte for byte; `git status` empty |
| `--natural` and `--natural-run` | not rerun in this check; D80 records both reproducing their outputs byte for byte |
| `verify_frozen_inputs.py` | OK: 130 of 135 input hashes match, the other 5 being analysis code changed since the run (exempt, as the outputs regenerate identically); 4 of 4 snapshots. Without the snapshots it fails at its check (f) only |
| `check_abstract.py` | 1,900 of 1,900 characters; no non-ASCII character in the printed text (1,893 after the rewrite: below) |
| `check_numbers.py` | 22 files; 0 digits, 0 count words, 0 missing keys |
| The paper's tests (`test_check_numbers`, `test_check_abstract`, `test_make_tables`, `test_make_tables_fresh`, `test_natural_template`, `test_make_tables_pilot_design`, `test_make_figures`) | 111 passed |
| Full offline suite and Docker probes | not rerun: 1,354 offline tests passed at D81, and the Docker suite has 20 tests (STATUS.md; D80) |
| Build (TeX Live 2023, Biber 2.19) | as in Status; no overfull box (16 underfull); one TODO; the bibliography file in format 3.2 |
| PDF text | no model, provider or agent-product name found |
| Pre-push scan | not run: it needs the private markers and the natural data, which this check did not read |

Results of the recheck of 2026-11-24, in a scratch clone of `a8ec542` with this round's uncommitted changes applied
(the review packet's strata and their tests, the paper's sections and the documents), the base snapshots copied in,
no natural data and the Docker daemon down:

| Step | Result |
| --- | --- |
| `check_abstract.py` | 1,893 of 1,900 characters, leaving 7; no non-ASCII character in the printed text |
| `check_numbers.py` | 22 files; 0 digits, 0 count words, 0 missing keys |
| Build (TeX Live 2023, Biber 2.19) | 76 pages: Section 10 on page 22, the references from page 23, Appendix A from page 26; no overfull box (16 underfull), no LaTeX or Biber warning, nothing undefined; one TODO, no `UNFILLED` marker; no model, provider or agent-product name in the PDF text |
| Full offline suite | with the snapshots, 1,362 passed and 9 skipped for want of the natural data; without them, 1,348 passed and 14 more skipped. Pytest also skipped the Docker probe module at collection |
| The review packet's strata | `stratum_held_out()`, which `review-packet --strata fresh-v1` uses, keeps 20, 19, 20 and 20 attempts per task and leaves out CS-02-fresh-A-final-1; grouped by graded diff as the export groups them, 110 items for 111 candidates (read-only; no packet was written) |
| Docker probes and the pre-push scan | not run |

Final checks before the commit of D82 (2026-11-24), with every part of this round applied, the downstream plan
included, in the build checkout (which holds the natural data) and in a clone with the base snapshots copied in and
no natural data, with the Docker daemon up:

| Step | Result |
| --- | --- |
| Tests | 1,464 collected (1,444 offline, 20 Docker). Build checkout: all 1,444 offline and 20 Docker tests passed. Clone: 1,435 passed, and 9 skipped for want of the natural data |
| Generators | every `make_tables.py` mode and `make_figures.py` rewrote their outputs byte for byte (`git status` unchanged); `build_training_selection.py --check` regenerates its two files byte for byte |
| `verify_frozen_inputs.py` | OK: 0 frozen files changed; 130 of 135 input hashes, the other 5 being exempt analysis code; 4 of 4 snapshots; protocol and decision log append-only |
| `check_abstract.py`, `check_numbers.py` | 1,893 of 1,900 characters; 22 files, 0 findings |
| Build (TeX Live 2023, Biber 2.19) | 76 pages, the references from page 23; no overfull box, no LaTeX warning, nothing undefined; one TODO, the author line; no model, provider or agent-product name in the PDF text; the PDF's title field set |
| ruff 0.16.9 | no new finding in the changed Python files |
| Pre-push scan | 0 findings, exit code 0, in the working tree before the commit (private markers, the AIDev logins and the natural texts given); run again on the commit before the push |

Final checks before the commit of D83 (2026-11-24), with the corrections that followed the reviews of `f3ae845`
applied, in the build checkout and in a clone with the base snapshots copied in and no natural data, with the Docker
daemon up:

| Step | Result |
| --- | --- |
| Tests | 1,464 collected (1,444 offline, 20 Docker). Build checkout: all 1,444 offline and 20 Docker tests passed. Clone: 1,435 passed, and 9 skipped for want of the natural data |
| Generators | every `make_tables.py` mode and `make_figures.py` rewrote their outputs byte for byte (`git status` unchanged); `build_training_selection.py --check` regenerates its two files byte for byte |
| `verify_frozen_inputs.py` | OK: 0 frozen files changed; 130 of 135 input hashes, the other 5 being exempt analysis code; 4 of 4 snapshots; protocol and decision log append-only |
| `check_abstract.py`, `check_numbers.py` | 1,897 of 1,900 characters; 22 files, 0 findings |
| Build (TeX Live 2023, Biber 2.19) | 77 pages: Section 10 and the references from page 23, Appendix A from page 27; no overfull box, no LaTeX or Biber warning, nothing undefined; one TODO, the author line; no model, provider or agent-product name in the PDF text |
| ruff 0.16.9 | no new finding in the changed Python files |
| Pre-push scan | 0 findings, exit code 0, in the working tree before the commit (private markers, the AIDev logins and the natural texts given); run again on the commit before the push |

**The arXiv source package** (only on the owner's instruction; the arXiv check below gives each rule)
- [x] The author line: Raj Kashikar, Cornell University (D84). The author is the only author, so the consent is the
      submitter's own.
- [x] The working-draft subtitle removed, since arXiv expects complete final drafts; its disclosure is also in the
      title note and the abstract (D84).
- [x] `\date{\today}` replaced by a fixed date (November 25, 2026; D84).
- [ ] The bibliography for arXiv's default TeX Live 2025 (D84): upload `references.bib` and leave `main.bbl` out, so
      that arXiv runs Biber. The local `main.bbl` is in format 3.2 (TeX Live 2023, Biber 2.19), which TeX Live 2025
      does not support, and arXiv uses an uploaded `.bbl` that carries the main file's name instead of running Biber.
      Then check the compiled result.
- [ ] Only the files the build reads, as latexmk's `main.fls` lists them: `main.tex`, `sections/`, the generated `.tex`
      files with the two figure PDFs, and `references.bib` in place of the `main.bbl` that `main.fls` lists. No `aux`, `log` or `pdf` file of the main
      document, no ledger and no script. All 101 tracked names under `paper/` are within arXiv's character set, and
      none is hidden.
- [x] A link to the public repository in Section 10, with its licences (D84).
- [x] The arXiv licence: CC BY 4.0 (D84); it is irrevocable for each version.
- [ ] The abstract pasted from `check_abstract.py --print`.
- [ ] Endorsement checked for cs.SE (arXiv check): automatic endorsement needs both an institutional address and a
      claimed arXiv paper in the same domain; otherwise a personal endorsement.
- [ ] The owner's explicit instruction to submit.

**What the author must verify by hand**
- [ ] The author line (name, affiliation and address) on page 1, in `CITATION.cff` and in `pyproject.toml`, as the
      author wants it to appear (D84 records where the name comes from).
- [ ] The whole paper, read against the records: the scope of the lead contrast (largely fixed by the design), the
      post hoc reading and its families, the natural case studies read with the reference gate, and the statements
      that hold only by the study's procedure. Spot-check numbers against the evidence ledgers
      (`paper/evidence_ledger*.md`) and the run analyses.
- [ ] The AI-assistance statement (Section 9): what the agent produced, what the author did, and that the responsibility
      is the author's (the text says so since D84). Its sentence that no human has written, reviewed or adjudicated the
      scenarios, the reference contracts, the labels and the internal reviews must still be true at posting, or be
      revised.
- [ ] The references against their primary pages (`paper/references.bib` records the checks of 2026-11-18,
      2026-11-21 and 2026-11-23).
- [ ] Data rights and privacy: the controlled repositories' MIT licences, the natural repositories' MIT or Apache-2.0
      licences, AIDev's CC-BY-4.0 compilation licence, any removal request, SWE-chat's terms (not used), and that the
      paper prints no thread text, repository name, login or agent product of the natural data.
- [ ] Internal reviews: every review so far was by model agents (`docs/internal_review.md`, and the decision log from
      D40 on). Tick this only after a human review of the final version.
- [x] Before the repository is shared, the reader-facing documents brought to the current state: done with D82. At
      `2daa725` these still described the state before D53 to D81:
  * STATUS.md: "Not run" lists any natural-data task and any fresh-agent attempt or independent labeler; the
    fresh-agent tooling is "not used yet"; S10 "has no recorded result yet"; the re-grade "is in progress"; the draft
    "compiles to 29 pages"; and the test count is that of `a0542bb`;
  * README.md: "(no attempt exists yet)" for the fresh-agent stratum, and, under Limitations, "No natural result yet"
    and "No natural label, held-out pool or run exists yet";
  * `docs/data_card.md`: the natural PR-review row says that the contracts, other verifiers, held-out pools and D19
    labels are still to be built, and the card does not mention the fresh-v1 attempts;
  * `docs/ownership_and_defense.md`: "No natural task has been built", and of the fresh-agent checks, "none has run
    yet";
  * `results/runs/README.md`: the run table ends at `pilot-v0.3.3`, without `fresh-v1`, `pilot-v0.3.5-regrade` and
    `natural-pr-v1`.

## arXiv guidance re-checked on 2026-11-23

Sixteen pages were fetched on 2026-11-23 between 22:47:45Z and 22:47:48Z (UTC), each with a bounded GET (60 s, 5 MB)
into a temporary copy outside the repository, and every one returned HTTP 200. The 13 pages on info.arxiv.org all
report a Last-Modified time between 16:49:21 and 16:49:28 GMT on Tue, 10 Nov 2026, before both earlier checks: what
this check adds are rules those checks did not record, not changes since. The three blog posts are dated by their
bylines. No form was used, no account page was opened and no one was contacted. The download records
(`data/manifests/third_party_downloads.json`) list these pages, with an earlier arXiv check's 23 pages of the same
evening, as `pages-arxiv-help-2026-11-23`, and that check's partial clone of the help pages' sources as
`clone-arxiv-docs`; `pages-arxiv-help` covers the fetch of 2026-11-18.

Pages under https://info.arxiv.org/help/: `submit/`, `moderation/`, `endorsement.html`, `license/index.html`,
`policies/submission_agreement.html`, `ancillary_files.html`, `policies/format_requirements.html`,
`policies/content-types.html`, `prep.html`, `submit_tex.html`, `faq/texlive.html`, `policies/privacy_policy.html` and
`third_party_submission.html`. Blog posts: https://blog.arxiv.org/2026/01/21/attention-authors-updated-endorsement-policy/
(endorsement, 21 January 2026), https://blog.arxiv.org/2026/10/01/updated-rate-limit-policy/ (rate limits, 1 October
2026) and https://blog.arxiv.org/2025/10/31/attention-authors-updated-practice-for-review-articles-and-position-papers-in-arxiv-cs-category/
(CS review and position papers, 31 October 2025).

Each rule, with at most one quoted sentence, and where the draft stands:

* **Endorsement (in force since 21 January 2026; neither earlier record has it).** A first submission, or a first one
  in a new category, needs endorsement. An institutional e-mail address alone no longer qualifies. Automatic
  endorsement needs both an institutional address and authorship of an existing paper, claimed on arXiv, in the same
  endorsement domain; anyone else needs a personal endorsement from an established arXiv author in that domain.
  "arXiv staff cannot waive endorsement requirements or provide a personal endorsement for authors." (announcement).
  One positive endorsement per category suffices; the request e-mail carries a link to give to endorsers; e-mailing
  many potential endorsers at once, or one repeatedly, is inappropriate; and endorsers endorse only authors who
  submit their own work, not proxies (endorsement page). *Draft:* the route depends on the submitting author and the
  category, cs.SE (D84). The page names most high-level subject areas as endorsement domains, without listing cs
  among its examples. No endorser has been contacted.
* **Who submits.** Only registered authors submit, and "Authors are expected to self-submit." (submit page). A third
  party may submit only as a proxy that arXiv has approved in advance (third-party page; Submittal Agreement). The
  submitter must ensure that every author consents, and anonymous submissions are not accepted (metadata page).
  *Draft:* one author, Raj Kashikar (D84), who submits the work.
* **AI use.** Authors must "report in their work any significant use of sophisticated tools", text-to-text generative
  AI included, as their field reports methodology. The stated reason is that knowing which tools were used matters
  for evaluating and interpreting the work. Each author takes full responsibility for all content however it was
  generated, and AI tools are not listed as authors (moderation page; metadata page). *Draft:* Section 9 reports the
  agent's use and names no model (D84).
* **Moderation.** The moderation process is not peer review. Work must be self-contained, carefully prepared and
  neutral in tone, and may be declined for lacking originality, novelty or significance. "Submissions in need of
  significant review and revision may also be declined." (moderation page). Authors whose work was declined before
  face closer scrutiny. The rate-limit announcement reports a marked increase in dense, AI-written papers. *Draft:*
  not yet reviewed by its author; a 22-page main text at this check (about 23 pages since the corrections
  that followed the reviews of `f3ae845`, D83).
* **Content type.** Research articles are the primary content type, and "Articles should be complete final drafts."
  (content-types page). Proposals for future research, course projects and very short work are typically not
  accepted. Since 31 October 2025, review and position papers in CS need prior acceptance after peer review; the
  change concerns those two types only, and scientific research papers are not subject to it (CS announcement).
  *Draft:* a research article; the working-draft subtitle is removed (D84).
* **Format.** Among its requirements: a title and authors, complete references, single spacing, 10 to 14 point type,
  margins of at least 1 inch, and no line numbers, obstructing watermarks, highlighted text, margin notes or referee
  remarks. "Links to code or data sets must resolve to a publicly available repository" (format page). A submission
  that does not comply may be returned. *Draft:* 11 point with 1-inch margins and no line numbers; no TODO;
  Section 10 links the public repository (D84).
* **Source files.** TeX or PDFLaTeX source is preferred, and PDF made from TeX is not accepted. Figures must be
  included (PDF, JPEG or PNG under PDFLaTeX; arXiv converts none), and file names may use only
  `a-z A-Z 0-9 _ + - . , =`, case-sensitive (submit page). arXiv offers TeX Live 2023 and 2025, with 2025 the default
  (TeX Live page), and "For TeX Live 2025, only bbl format 3.3 is supported." (TeX submission page). A `.bbl` must
  carry the main file's name; without one, arXiv runs the backend that biblatex selects. Auxiliary and output files
  are left out, hidden files are deleted at announcement, and `\today` in `\date` is discouraged. *Draft:* two PDF
  figures (132 KB and 80 KB); every name within the set, and no hidden file; a format-3.2 `.bbl` from TeX Live 2023
  and Biber 2.19, which the upload replaces with `references.bib` (D84); a fixed date (D84).
* **Metadata.** Abstracts "longer than 1920 characters will not be accepted" (metadata page), and the metadata fields
  take ASCII only. *Draft:* 1,897 characters since D83's corrections (1,893 after the abstract's rewrite, D82), 3 under the gate's
  limit of 1,900, all ASCII.
* **Licence and rights.** The options are CC BY 4.0, CC BY-SA 4.0, CC BY-NC-SA 4.0, CC BY-NC-ND 4.0, the arXiv.org
  perpetual, non-exclusive licence 1.0, and CC Zero; another licence can be stated on the first page under the arXiv
  licence. "The license chosen is irrevocable and cannot be changed." (licence page). In the Submittal Agreement the
  submitter warrants original authorship, or proxy status approved by arXiv, the co-authors' consent, and that
  distribution violates no one's rights, privacy included; arXiv will not remove an announced article to comply with
  a journal's policy. *Draft:* CC BY 4.0 (D84); the privacy statements are in the hand checks.
* **Permanence.** Each version "of a paper (including rejected papers) is considered a permanent part of the
  scientific record and may not be removed." (privacy policy).
* **Rate limits.** "Each author may submit up to two new submissions per calendar month with a limit of three active
  submissions." (moderation page). Rejected submissions count toward the month; a submission deleted before its
  announcement does not (rate-limit announcement).
* **Ancillary files.** As recorded on 2026-11-18: limited facilities, for TeX or PDFLaTeX submissions only, and no TeX
  files in the ancillary directory. The code and data stay in the repository.

## Earlier arXiv checks (kept as recorded)

### arXiv guidance checked on 2026-11-13

Sources: https://info.arxiv.org/help/submit/ and https://info.arxiv.org/help/moderation/
(read on 2026-11-13; the pages show no last-updated date; the moderation page
links a rate-limit announcement dated 2026-10-01). Linked pages for endorsement,
licences and ancillary files must be re-read at submission time.

* **Endorsement:** new users or users submitting to a new category "may be
  required to find endorsements" (submit page; details on the endorsement page).
* **Licence:** authors grant arXiv an "irrevocable license to distribute the work";
  the licence options are on a separate page (not yet reviewed).
* **Formats:** (La)TeX/PDFLaTeX source preferred; "We do not accept dvi, PS, or PDF
  created from TeX/LaTeX source." Figures must be included, not linked. File names
  are restricted to letters, digits and `_ + - . , =`.
* **Moderation is not peer review.** Moderators check scholarly interest,
  originality and substantive research content, careful presentation, and rights
  to submit; research proposals and course projects may be declined.
* **AI use:** authors must report "any significant use of sophisticated tools",
  including text-to-text generative AI; authors are responsible for all content
  however generated; "generative AI language tools should not be listed as an
  author."
* **Rate limits:** up to two new submissions per calendar month and three active
  submissions (per the moderation page).
* **Data/code:** limited facilities for ancillary files; the repository should be
  the primary artifact.

### arXiv guidance re-checked on 2026-11-18

Pages re-fetched on 2026-11-18. No page shows a last-updated date.
* https://info.arxiv.org/help/submit/
* https://info.arxiv.org/help/moderation/
* https://info.arxiv.org/help/endorsement.html
* https://info.arxiv.org/help/license/index.html
* https://info.arxiv.org/help/ancillary_files.html

No material change from 2026-11-13. The pages that were not yet reviewed then
state the following:

* **Endorsement:** "arXiv requires that users be endorsed before submitting their
  first paper to arXiv or a new category." Endorsers "must have authored a certain
  number of papers within the endorsement domain". First-time submitters "are
  encouraged to associate an institutional email address if they have one". An
  endorsement is requested by sending an endorser a "six-character alphanumeric
  endorsement code". No endorser has been or will be contacted without the owner's
  instruction.
* **Licences offered:** CC BY 4.0, CC BY-SA 4.0, CC BY-NC-SA 4.0, CC BY-NC-ND 4.0,
  the arXiv.org perpetual, non-exclusive licence 1.0, and CC0 1.0. "The license
  chosen for each version is irrevocable." This is an owner decision.
* **Ancillary files:** "There are limited facilities for including ancillary files";
  the feature "is not supported with PDF submissions"; TeX files must not go in the
  ancillary directory. The code and data stay in the repository.
* **Unchanged:**
  * the generative-AI policy: report "any significant use of sophisticated tools",
    including text-to-text generative AI, and such tools "should not be listed as
    an author";
  * the submission rate: "up to two new submissions per calendar month with a limit
    of three active submissions";
  * the format rule: "We do not accept dvi, PS, or PDF created from TeX/LaTeX
    source".

### What the check of 2026-11-23 found in these records

Each quoted phrase above still appears on its page, except two wordings noted below. What the records lack are rules
that were already in force at both checks:
* the endorsement policy of 21 January 2026 (above). The record of 2026-11-18 quotes only the encouragement to
  associate an institutional e-mail address, which reads as if such an address were enough;
* the format requirements, among them a public repository for linked code and data; the rule that articles be
  complete final drafts; the `.bbl` format of TeX Live 2025; the note on `\today`; the abstract's limit of 1,920
  characters and the ASCII-only metadata; the submitter's duties (self-submission, every author's consent); the
  permanence of every version, rejected ones included; and that rejected submissions count toward the rate limit.

The two wordings: the record of 2026-11-13 ends its last generative-AI quote with a full stop where the page goes on
after a semicolon, and the record of 2026-11-18 quotes "The license chosen for each version is irrevocable." as a
sentence, while the page has these words inside a longer sentence. The licence page calls the public-domain option
"CC Zero"; CC0 1.0 Universal is the dedication that applies to all metadata.
