# Manuscript draft

`main.tex` is a working draft. Build it from this directory with `latexmk -pdf main.tex`
(needs `biber`). Regenerate the tables first with `make_tables.py` (see the top-level README).

Rules for this directory:

* Every number in `generated/*.tex` is produced by `make_tables.py` from recorded
  files (run analyses, run comparisons, task manifests, verifier specs, scenarios),
  and `evidence_ledger.md` lists it with its source file. Numbers in the text repeat
  table values or values recorded in the decision log, the verifier specs, the
  protocol or the harness configuration.
* `references.bib` contains only entries verified against primary sources
  (date of check in the file header). Unverified related work stays as TODO text.
* Sections that depend on unrun experiments are visibly marked `UNFILLED`.
