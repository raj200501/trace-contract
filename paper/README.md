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
* The natural run (protocol §20): once `results/runs/natural-pr-v1` exists (as `scripts/publish_natural_run.py` publishes
  it), `.venv/bin/python paper/make_tables.py --natural-run results/runs/natural-pr-v1` writes `generated/natural_run/`
  with `evidence_ledger_natural_run.md`, and the macros `\nrv{key}` in `generated/natural_run/numbers.tex` (`main.tex`
  defines `\nrv` as it defines `\fv` and `\nat`, and inputs that file where it exists). Its rules:
  * It reads the run's `analysis.json` and `manifest.json` (the run's id, times, code revision, repeats, pilot flag and
    invocations), and for its privacy check the agent product names of the AIDev screening record
    (`data/manifests/screening_natural_aidev.json`); nothing else. An analysis that is
    not a natural run's, or that is not in case-study mode, is refused. Each run is reported on its own (§20.3), so the
    size rule counts the run's own accepted tasks, never the committed index's over both samples: with 10 or more, §15.6
    and §15.7 apply in full, and their pooled tables are not this mode's. An analysis made before that rule (with no
    `meta.case_study.accepted_in_run`) is refused too.
  * Four per-family tables: false acceptance and false rejection per condition under D19 (C1 to C4, B2, B1, and B3 apart
    as the secondary arm; a cell the oracle-gated view drops is marked); which conditions accept each family's pre-review
    state under the source-evidence label, with its D19 and second labels; the second labeling (the labeler's status, the
    labels, the agreement with D19, apart for the pre-review states and the pool); and the construction facts (contract
    counts, checks per verifier, the audits of C2 and C4, B3, B1, the reference checks' status record, cost).
  * Besides the tables' values, the macros give the run's facts (`run.date`, `run.started`, `run.finished` in UTC,
    `run.revision`, `run.harness`, `run.repeats`, `run.pilot`, `run.invocations`, and `run.families`, the run's own
    families from the analysis's `natural.tasks`) and, per family, D19's labels of its held-out candidates
    (`d19.<family>.valid`, `.invalid`, `.ambiguous`, `.unlabeled`, and `.ambiguous.ids` and `.ambiguous.reasons`: each
    ambiguous candidate with the category of D19's reason in brackets, which `tracecontract analyze` carries into the
    run's label block, `labels.<task>.d19`). An analysis without that block is refused.
  * Nothing is pooled over the families: no pooled rate, interval or p-value, and no total.
  * Every caption ends with the marker "‡ Natural case study; caveats in Section~\ref{sec:natural-cases}": the caveats
    are stated once, at the head of the natural section.
  * Every table cell is a ledger entry `<row> | <family> = <cell>` that names the `analysis.json` fields it is made from,
    each as `<dot path>=<JSON value>`; each field belongs to one family, or to the run. The numbers in the captions and
    the macros are entries too. `tests/test_make_tables_natural_run.py` checks every cell against its fields.
  * Its outputs get the natural arm's privacy check, as `--natural`'s do; its digit-run rule skips the run's own code
    revisions, which are commits of this repository.
* `sections/natural.tex` is the template of the natural case-study section, fixed before any analysis of the run: every
  value in it is a `\nrv` or `\nat` macro, and it prints `UNFILLED` until `--natural-run` has run. `main.tex` does not input
  it yet, and it points to no other section or appendix yet. `tests/test_natural_template.py` checks that every key it
  uses is generated, that it compiles with `main.tex`'s preamble, its wording, the disclosures its records require, and
  that every decision-log entry it cites is logged (its header declares D77 as pending: the build session logs it with the
  template, as the next entry, and removes that line). Its fixed sentences state construction facts that the analysis
  also computes; the test's `PREMISES` lists them, and `test_the_run_s_own_numbers_bear_out_the_template_s_premises` runs
  on `generated/natural_run/numbers.tex` once the run is published: a premise that fails means the sentence is rewritten
  from the records. The closing paragraph keeps one visible `UNFILLED` marker, the integration slot, which the sentences
  that name families by their cells replace after `--natural-run`.
* All labels behind these numbers are model proposals; no human labels exist. Natural-arm results are marked
  `UNFILLED` until the run `natural-pr-v1` exists.
