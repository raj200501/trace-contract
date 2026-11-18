# Submission readiness

Status: **not ready.** The draft compiles, but compiling is not readiness. Nothing
has been uploaded or submitted, and no endorser has been contacted; doing either
requires the repository owner's explicit instruction.

## Evidence gaps (blocking)

1. **No human labels or contract reviews.** Every result so far is an automated
   pilot with model/construction labels. The paper's central claims need
   human-adjudicated labels, with a second reviewer on an overlap subset and
   agreement statistics (protocol §5, §9).
2. **No natural sessions.** All tasks are controlled sessions with scripted
   corrections. Natural SWE-chat tasks are blocked on the dataset's access terms
   (decision log D4). Without them, external-validity claims must be limited to
   controlled sessions.
3. **Too few independent task families** for any inferential claim. The pilot is
   descriptive; a confirmatory study needs a v1.0 protocol frozen after the pilot.
4. **Novelty positioning** is narrowed but not yet confirmed by the owner (decision
   log D34). The verified brief (`docs/research_brief.md`) finds partial precedents
   for every component, notably SessionFarmer, SWE-Together and Trace2Eval. The
   claim is limited to their combination: initial-only vs correction-aware verifiers
   from one frozen procedure, one held-out pool anchored on the session's own
   pre-correction states (its other candidates generated after the verifiers were
   frozen; departures in decision log D37, D40, D41), and independent human labels. The third element does not
   exist yet, so the claim cannot be made in a submission until it does. It is not a
   claim about task reconstruction.
5. **Single model family** for all generated artifacts. A second model family for
   at least the verifier generators, or an explicit limitation, is needed.
6. **Licence of this repository** is undecided (owner decision).

## arXiv guidance checked on 2026-11-13

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

## arXiv guidance re-checked on 2026-11-18

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

## AI-assistance disclosure (draft text for the human authors to adapt)

> The software, the controlled-session scenarios and protocol, the controlled
> sessions, every generated artifact (contracts, verifiers, candidates, label
> proposals, checks and mappings), the analyses, the internal reviews and the first
> draft of this manuscript were produced by Anthropic's Claude models (via Claude
> Code), working largely autonomously under the owner's standing instructions. The
> human author(s) [describe truthfully what they designed and reviewed, and any
> human annotation they performed, once it exists] and take full responsibility for
> the content.

The bracketed part must describe only what the human authors actually did.

## Checklist before any submission

- [ ] Human contract reviews and candidate labels recorded; agreement reported.
- [ ] Natural-session tasks included, or claims explicitly limited to controlled sessions.
- [ ] Adversarial internal review by model agents: run on `pilot-v0.3` (six lenses; the skeptic stage was stopped before every finding was checked), followed by a dispositions review and a final claims audit on `pilot-v0.3.1` (decision log D40); findings and dispositions in `docs/internal_review.md`. Tick only after a review of the final version, including human review, once human labels exist.
- [ ] All numbers regenerated from recorded runs (`paper/make_tables.py`) and present in `paper/evidence_ledger.md`.
- [ ] Bibliography entries verified against primary pages (dates recorded).
- [ ] Data rights re-checked (SWE-chat terms, removal requests, repository licences).
- [ ] Repository licence chosen; dataset/task licence chosen.
- [ ] AI-use disclosure written and reviewed by the human authors.
- [ ] Endorsement status checked on arXiv's endorsement page.
- [ ] Explicit instruction from the repository owner to submit.
