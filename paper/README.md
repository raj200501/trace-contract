# Manuscript draft

`main.tex` is a working draft. Build with `latexmk -pdf main.tex` (or `make -C paper`).

Rules for this directory:

* Numbers in results sections come only from `generated/*.tex`, produced by
  `make_tables.py` from recorded runs; `evidence_ledger.md` links every number to
  its run id and analysis file.
* `references.bib` contains only entries verified against primary sources
  (date of check in the file header). Unverified related work stays as TODO text.
* Sections that depend on unrun experiments are visibly marked `UNFILLED`.
