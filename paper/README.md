# Manuscript draft

`main.tex` is a working draft. Build it from this directory with `latexmk -pdf main.tex`
(needs `biber`). Regenerate the tables first with `make_tables.py` (see the top-level README).

Rules for this directory:

* Every number in `generated/*.tex` is produced by `make_tables.py` from recorded
  files (run analyses, run comparisons, task manifests, verifier specs, scenarios),
  and `evidence_ledger.md` lists it with its source file. Numbers in the text repeat
  table values or values recorded in the decision log, the verifier specs, the
  protocol, the harness configuration or the candidate label records
  (`tasks/*/candidates/*.json`). Numbers about related work are taken or computed
  from the cited works, as recorded in `docs/research_brief.md`.
* `references.bib` contains only entries verified against primary sources
  (date of check in the file header). Unverified related work stays as TODO text.
* Sections that depend on unrun experiments are visibly marked `UNFILLED`.

Tables and figures of the later runs (decision log D66):

* `make_tables.py` writes the pilot's tables to `generated/*.tex` and `evidence_ledger.md` (the top-level README's
  command, which `tests/test_make_tables.py` checks byte for byte). Its other modes write their own subdirectories and
  ledgers and leave the pilot's untouched:
  `.venv/bin/python paper/make_tables.py --fresh results/runs/fresh-v1 --regrade results/runs/pilot-v0.3.5-regrade --natural`
  writes `generated/fresh/` with `evidence_ledger_fresh.md` (fresh-v1 and the 0.3.5 re-grade) and `generated/natural/`
  with `evidence_ledger_natural.md` (the natural arm's funnel, S10 and the Trace Commons screen).
* `.venv/bin/python paper/make_figures.py results/runs/fresh-v1` draws the fresh-v1 figures with TikZ (no matplotlib)
  into `generated/figures/`, each with its source `.tikz`, a `.json` of every plotted value and its field, and
  `evidence_ledger_figures.md`.
* `generated/fresh/numbers.tex` and `generated/natural/numbers.tex` define number macros, used in the text as `\fv{key}`
  and `\nat{key}`; an undefined key prints as `UNFILLED`. Each value is in its ledger with its file and field.
* All labels behind these numbers are model proposals; no human labels exist. Natural-arm results are marked
  `UNFILLED` until the run `natural-pr-v1` exists.
