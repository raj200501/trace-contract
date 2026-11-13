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
4. **Novelty positioning** must survive the adversarial review in
   `docs/research_brief.md` (closest work: SWE-Together, Trace2Eval). The claim is
   limited to *measuring* reward fidelity, not to task reconstruction.
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

## AI-assistance disclosure (draft text for the human authors to adapt)

> Most of the software, the task-construction pipeline, the controlled sessions,
> the verifier and candidate generation, and the first draft of this manuscript
> were produced with substantial assistance from Anthropic's Claude models
> (via Claude Code). The human author(s) designed and reviewed [to be completed
> truthfully], performed the human annotation, and take full responsibility for
> the content.

The bracketed part must describe only what the human authors actually did.

## Checklist before any submission

- [ ] Human contract reviews and candidate labels recorded; agreement reported.
- [ ] Natural-session tasks included, or claims explicitly limited to controlled sessions.
- [ ] Adversarial internal review completed and its revisions applied.
- [ ] All numbers regenerated from recorded runs (`paper/make_tables.py`) and present in `paper/evidence_ledger.md`.
- [ ] Bibliography entries verified against primary pages (dates recorded).
- [ ] Data rights re-checked (SWE-chat terms, removal requests, repository licences).
- [ ] Repository licence chosen; dataset/task licence chosen.
- [ ] AI-use disclosure written and reviewed by the human authors.
- [ ] Endorsement status checked on arXiv's endorsement page.
- [ ] Explicit instruction from the repository owner to submit.
