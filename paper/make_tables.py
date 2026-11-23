"""Generate LaTeX tables and the evidence ledgers from recorded runs.

Usage:
  python paper/make_tables.py results/runs/<final run> [--compare results/runs/<run> ...]
  python paper/make_tables.py --fresh results/runs/fresh-v1 [--regrade results/runs/pilot-v0.3.5-regrade] [--natural]
  python paper/make_tables.py --natural-run results/runs/natural-pr-v1

The first form (the construction pilot) writes paper/generated/*.tex and
paper/evidence_ledger.md. Every number printed in a table is listed in the ledger with
its source file and JSON path. Nothing is entered by hand: tables come from task
manifests, the controlled scenarios (hashed and logged locally before each session),
verifier specs, the run's analysis.json and the run-comparison files written by
scripts/compare_runs.py.

The second form writes the tables of the new runs, each mode into its own subdirectory
with its own ledger, and never touches the pilot's top-level tables or ledger:
* ``--fresh RUN``: the fresh-agent stratum (analysis.json, analysis_sensitivity.json,
  manifest.json and results.jsonl of the run; the attempt records under data/fresh/; the
  B1 check-origin files of the tasks) -> paper/generated/fresh/*.tex, the number macros
  paper/generated/fresh/numbers.tex and paper/evidence_ledger_fresh.md;
* ``--regrade RUN`` (with ``--fresh``): the reliability re-grade of the pilot (its
  compare_<run>.json, manifest.json and results.jsonl, and the compared run's) ->
  paper/generated/fresh/regrade_reliability.tex, in the same ledger;
* ``--natural``: the natural PR-review arm's screening funnel, its S10 table and the
  Trace Commons screen (the manifests under data/manifests/) -> paper/generated/natural/*.tex,
  paper/generated/natural/numbers.tex and paper/evidence_ledger_natural.md. Before anything
  is written, every natural output is checked to hold no URL, owner placeholder, digit run
  of 7 or more (an id), session-local path or agent product name;
* ``--natural-run RUN``: a natural run analysed in case-study mode (protocol §19.6, §20.3; the
  run's analysis.json, and its manifest.json for the run's id, times, code revision, repeats,
  pilot flag and invocations) -> four per-family tables in
  paper/generated/natural_run/ (false acceptance and false rejection per condition under D19,
  B3 apart; the pre-review states under the source-evidence label; the second labeling; the
  construction facts), the number macros paper/generated/natural_run/numbers.tex (``\\nrv{key}``:
  the tables' values, the run's facts ``run.*`` and, per family, D19's labels ``d19.<family>.*``
  with the reason category of each ambiguous candidate) and paper/evidence_ledger_natural_run.md.
  Each table cell is a ledger entry that names the analysis.json fields it is made from, with
  their values; every field belongs to one family, or to the run,
  so nothing is pooled over families. Every caption ends with the marker that points to the
  natural section's caveats (``NR_MARKER``). An analysis that is not a natural run's, or that is not
  in case-study mode (the run grades 10 or more accepted tasks of its own, protocol §20.3: each
  run is reported on its own; §15.7's pooled tables then apply), is refused. Its outputs get the
  natural arm's privacy check, which also reads the AIDev screening record
  (data/manifests/screening_natural_aidev.json) for the agent product names.
Both forms can be combined in one invocation.

The arguments are parsed and checked before anything is written: every run directory
must hold ``analysis.json`` and ``manifest.json``, and every ``--compare`` directory
``results.jsonl``. The tables and the ledgers are written to a temporary directory first.
Only when all of them have been written do they replace ``paper/generated/*.tex`` and
the ledger, and a top-level table that this invocation did not write is then deleted, so
a table whose inputs are missing cannot survive from an earlier run. The same holds for
each subdirectory a new-run mode writes. ``--help``, a mistyped directory or a failure
while generating leaves every file as it was; the subdirectory
``paper/generated/exploratory/`` (scripts/exploratory_reanalysis.py) is never touched.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "paper" / "generated"
LEDGER = ROOT / "paper" / "evidence_ledger.md"
# One name per concept (restructure plan, finding 13): initial-only (C1, C2), correction-aware (C3, C4), the session-LLM
# baseline (B2), repository tests (B1).
COND_TEX = {"initial_plain": "C1 initial-only, plain", "initial_audited": "C2 initial-only, audited",
            "full_plain": "C3 correction-aware, plain", "full_audited": "C4 correction-aware, audited",
            "llm_freeform": "B2 session-LLM baseline", "repo_tests": "B1 repository tests"}
# The construction pilot's own tables (paper/generated/*.tex and paper/evidence_ledger.md) are frozen at commit c5ede4c
# (scripts/verify_frozen_inputs.py, check e): they keep the names and captions they were frozen with, byte for byte.
PILOT_COND_TEX = {"initial_plain": "C1 initial, plain", "initial_audited": "C2 initial, audited", "full_plain": "C3 full, plain",
                  "full_audited": "C4 full, audited", "llm_freeform": "B2 full-session LLM", "repo_tests": "B1 repository tests"}
# The rows of a table that gives both labelings: D19's rule-based proposals and the independent labeler's verdicts.
RULE_ROW, LABELER_ROW = "rule (D19)", "second labeler"
# A wrapping column for the conditions' names in the tables that are tight on width (never the last column, whose row
# ends with \\, which \raggedright would take for a line break).
COND_P = "p{0.15\\linewidth}"


def cond_cell(cond: str) -> str:
    return "\\raggedright " + tex(COND_TEX.get(cond, cond))


ORDER = ["initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform", "repo_tests"]


def ordered(d: dict) -> list:
    """Items of a per-condition dict in the paper's canonical order (C1-C4, B2, B1)."""
    return [(k, d[k]) for k in ORDER if k in d] + [(k, v) for k, v in d.items() if k not in ORDER]


def tex(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")
            .replace("#", r"\#"))


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


class Ledger:
    def __init__(self, argv: list[str]) -> None:
        cmd = " ".join(["python", "paper/make_tables.py", *argv])
        self.lines = ["# Evidence ledger", "", "Every number in `paper/generated/*.tex` with its source file. Generated by "
                      f"`{cmd}`.", ""]

    def add(self, table: str, what: str, value, src: str) -> None:
        self.lines.append(f"- [{table}] {what} = {value} <- `{src}`")


def fmt_rate(rate, num, den, ci=None) -> str:
    if rate is None:
        return f"n/a (0/{den})"
    s = f"{rate:.2f} ({num}/{den})"
    if ci:
        s += f" [{ci[0]:.2f}, {ci[1]:.2f}]"
    return s


def table(caption: str, label: str, spec: str, header: str, rows: list[str], size: str = "\\small") -> str:
    return (f"\\begin{{table}}[t]\\centering{size}\n\\caption{{{caption}}}\\label{{{label}}}\n\\begin{{tabular}}{{{spec}}}\\toprule {header} \\\\\\midrule\n"
            + "\n".join(rows) + "\n\\bottomrule\\end{tabular}\\end{table}\n")


def tasks_and_scenarios(led: Ledger, out: Path) -> None:
    rows, srows = [], []
    for td in sorted((ROOT / "tasks").glob("*/task.json")):
        m = json.loads(td.read_text())
        repo = m["snapshot_source"]["repo_url"].split("github.com/")[-1]
        n_eval = 0
        for p in m["candidates"]:
            c = json.loads((td.parent / p).read_text())
            n_eval += c["split"] == "eval" and c["origin"] not in ("noop", "reference")
        rows.append(f"{tex(m['task_id'])} & {tex(m['population'])} & \\texttt{{{tex(repo)}}} & \\texttt{{{m['snapshot_source']['commit'][:7]}}} & "
                    f"{len(m['verifiers'])} & {n_eval} \\\\")
        led.add("tasks", f"{m['task_id']} verifiers / held-out candidates", f"{len(m['verifiers'])} / {n_eval}", rel(td))
        sc = ROOT / "data" / "controlled" / "scenarios" / f"{m['task_id']}.json"
        if sc.exists():
            s = json.loads(sc.read_text())
            ir = s["intended_requirements"]
            ir = ir if isinstance(ir, list) else ast.literal_eval(ir)
            u1 = [r for r in ir if r["turn"] == "U1"]
            u2 = [r for r in ir if r["turn"] != "U1"]
            cell = lambda rs: ", ".join(f"{tex(r['id'])}" + (" (superseded)" if r["final_status"] == "superseded" else "") for r in rs)  # noqa: E731
            srows.append(f"{tex(m['task_id'])} & \\texttt{{{tex(repo.split('/')[-1])}}} & {cell(u1)} & {cell(u2)} \\\\")
            led.add("scenarios", f"{m['task_id']} requirements U1/U2", f"{len(u1)}/{len(u2)}", rel(sc))
    (out / "tasks_table.tex").write_text(table(
        "Tasks (generated from task manifests). Held-out candidates exclude the reference solution and the no-op.", "tab:tasks",
        "lllllr", "Task & Population & Repository & Commit & Verifiers & Held-out", rows))
    (out / "scenario_table.tex").write_text(table(
        "Intended requirements of the controlled scenarios (hashed and logged locally before each session), by the user turn "
        "that introduced them (generated from \\texttt{data/controlled/scenarios}).", "tab:scenarios", "llp{0.33\\linewidth}p{0.33\\linewidth}",
        "Task & Library & Initial request ($U_1$) & Correction ($U_2$)", srows, size="\\footnotesize"))


def results(run: Path, led: Ledger, out: Path) -> None:
    a = json.loads((run / "analysis.json").read_text())
    run_id = json.loads((run / "manifest.json").read_text())["run_id"]
    src = rel(run / "analysis.json")
    pilot = "automated pilot" in a["meta"]["label_policy"]
    pre = ("\\textbf{Automated pilot: labels are rule-based proposals (D19), not human labels.} " if pilot else "")
    rows = []

    def cell(x: dict) -> str:
        star = "$^{*}$" if x.get("ci95_degenerate") else ""
        ex = "" if not x.get("exact95") else f" \\newline {{\\scriptsize exact [{x['exact95'][0]:.2f}, {x['exact95'][1]:.2f}]; macro {x['macro']:.2f}}}" \
            if x.get("macro") is not None else f" \\newline {{\\scriptsize exact [{x['exact95'][0]:.2f}, {x['exact95'][1]:.2f}]}}"
        return fmt_rate(x["rate"], x["num"], x["den"], x["ci95"]) + star + ex

    for c, d in ordered(a["conditions"]):
        fa, fr = d["false_acceptance"], d["false_rejection"]
        j = "n/a" if d.get("youden_j") is None else f"{d['youden_j']:+.2f}"
        tn = d["tasks_with_any_accepted_negative"]
        rows.append(f"{tex(PILOT_COND_TEX.get(c, c))} & {cell(fa)} & {cell(fr)} & {j} & {tn['num']}/{tn['den']} & "
                    f"{d['infrastructure']['num']}/{d['infrastructure']['den']} \\\\")
        for k, x in (("false_acceptance", fa), ("false_rejection", fr)):
            led.add("summary", f"{run_id} {c} {k} exact95 / macro / bootstrap degenerate", f"{x.get('exact95')} / {x.get('macro')} / {x.get('ci95_degenerate')}",
                    f"{src} conditions.{c}.{k}")
        for k in ("false_acceptance", "false_rejection"):
            v = d[k]
            led.add("summary", f"{run_id} {c} {k}", f"{v['rate']} ({v['num']}/{v['den']}) ci95={v['ci95']}", f"{src} conditions.{c}.{k}")
        led.add("summary", f"{run_id} {c} youden_j", d.get("youden_j"), f"{src} conditions.{c}.youden_j")
        led.add("summary", f"{run_id} {c} tasks_with_any_accepted_negative", f"{tn['num']}/{tn['den']}", f"{src} conditions.{c}")
        led.add("summary", f"{run_id} {c} infrastructure", f"{d['infrastructure']['num']}/{d['infrastructure']['den']}", f"{src} conditions.{c}")
    led.add("summary", f"{run_id} tasks / families (caption)", f"{a['n_tasks']} / {a['n_families']}", f"{src} n_tasks, n_families")
    (out / "results_summary.tex").write_text(table(
        f"Verifier reward fidelity on the held-out pool, run \\texttt{{{tex(run_id)}}} ({a['n_tasks']} tasks, {a['n_families']} families). " + pre +
        "Rates with (num/den) and 95\\% task-family bootstrap interval ($^{*}$: degenerate, every family has the same rate); "
        "below, the exact binomial interval (ignores clustering; reference scale only) and the macro rate (mean over families). "
        "Reference solution and no-op excluded; ambiguous candidates excluded. $J$ = (1$-$FR)$-$FA. "
        "Tasks w/ FA: families with at least one accepted invalid candidate. Infra: infrastructure outcomes.", "tab:summary",
        "lp{0.23\\linewidth}p{0.23\\linewidth}rrr",
        "Condition & False acceptance & False rejection & $J$ & Tasks w/ FA & Infra", rows, size="\\footnotesize"))

    crow = []
    for d in a["comparisons"]:
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]" + ("$^{*}$" if d.get("ci95_degenerate") else "")
        crow.append(f"{tex(PILOT_COND_TEX.get(d['a'], d['a']))} & {tex(PILOT_COND_TEX.get(d['b'], d['b']))} & {d['metric'].upper()} & {diff} & {ci} & "
                    f"{d['n_metric']} & {d['discordant']['a_accepts_b_rejects']}/{d['discordant']['a_rejects_b_accepts']} \\\\")
        led.add("comparisons", f"{run_id} {d['a']} - {d['b']} {d['metric']}", f"{d['difference']} ci95={d['ci95']} "
                f"degenerate={d.get('ci95_degenerate')} n={d['n_metric']} (pairs={d['n_common']}) discordant={d['discordant']}",
                f"{src} comparisons")
    (out / "results_comparisons.tex").write_text(table(
        f"Pre-specified paired comparisons on the same candidates, run \\texttt{{{tex(run_id)}}}" + (" (automated pilot)" if pilot else "") +
        ". n: labeled candidates for the metric (invalid for FA, valid for FR). $^{*}$: degenerate interval (every family has "
        "the same difference). Last column: A accepts \\& B rejects / A rejects \\& B accepts.", "tab:comparisons", "lllllrr",
        "A & B & Metric & A$-$B & 95\\% CI & n & discordant", crow, size="\\footnotesize"))

    # Accepted negatives by origin and type.
    nrows = []
    per_task = a["per_task"]
    for c, _ in ordered(a["conditions"]):
        def acc(pred):
            sub = [r for t in per_task.values() for r in t.get(c, []) if r["label"] == "invalid" and pred(r)]
            return sum(r["outcome"] == "pass" for r in sub), len(sub)
        pre_a, pre_n = acc(lambda r: r["origin"] == "observed_pre_correction")
        nm_a, nm_n = acc(lambda r: r["origin"] == "constructed_near_miss")
        cv_a, cv_n = acc(lambda r: r["negative_type"] == "correction_violating")
        iv_a, iv_n = acc(lambda r: r["negative_type"] == "initial_violating")
        nrows.append(f"{tex(PILOT_COND_TEX.get(c, c))} & {pre_a}/{pre_n} & {nm_a}/{nm_n} & {cv_a}/{cv_n} & {iv_a}/{iv_n} \\\\")
        led.add("negatives", f"{run_id} {c} accepted pre-correction/near-miss/correction-violating/initial-violating",
                f"{pre_a}/{pre_n}, {nm_a}/{nm_n}, {cv_a}/{cv_n}, {iv_a}/{iv_n}", f"{src} per_task")
    (out / "negatives_table.tex").write_text(table(
        "Accepted invalid candidates by origin and by negative type (accepted/total)" + (" (automated pilot)" if pilot else "") +
        ". Correction-violating: violates a reference requirement introduced after the first user request.", "tab:negatives",
        "lrrrr", "Condition & Pre-correction state & Near miss & Correction-violating & Initial-violating", nrows, size="\\footnotesize"))

    srows = []
    for c, s in ordered(a["sanity"]):
        r, n = s.get("reference", {}), s.get("noop", {})
        srows.append(f"{tex(PILOT_COND_TEX.get(c, c))} & {r.get('pass', '-')}/{r.get('n', '-')} & {n.get('pass', '-')}/{n.get('n', '-')} \\\\")
        led.add("sanity", f"{run_id} {c} reference/no-op passes", f"{r.get('pass')}/{r.get('n')}, {n.get('pass')}/{n.get('n')}", f"{src} sanity.{c}")
    (out / "sanity_table.tex").write_text(table(
        "Sanity checks (excluded from the rates): reference solution and no-op passes per condition.", "tab:sanity", "lrr",
        "Condition & Reference passes & No-op passes", srows, size="\\footnotesize"))

    if a.get("sensitivity_construction_labels"):
        xrows = []
        for c, d in ordered(a["sensitivity_construction_labels"]):
            def scell(k: str) -> str:
                star = "$^{*}$" if d.get(f"{k}_ci95_degenerate") else ""
                ex = d.get(f"{k}_exact95")
                return (fmt_rate(d[k], d[f"{k}_num"], d[f"{k}_den"], d[f"{k}_ci95"]) + star
                        + ("" if not ex else f" {{\\scriptsize exact [{ex[0]:.2f}, {ex[1]:.2f}]}}"))
            xrows.append(f"{tex(PILOT_COND_TEX.get(c, c))} & {scell('fa')} & {scell('fr')} \\\\")
            led.add("sensitivity", f"{run_id} {c} construction-label FA/FR",
                    f"{d['fa']} ({d['fa_num']}/{d['fa_den']}) ci95={d['fa_ci95']} exact95={d.get('fa_exact95')} degenerate={d.get('fa_ci95_degenerate')}, "
                    f"{d['fr']} ({d['fr_num']}/{d['fr_den']}) ci95={d['fr_ci95']} exact95={d.get('fr_exact95')} degenerate={d.get('fr_ci95_degenerate')}",
                    f"{src} sensitivity_construction_labels.{c}")
        (out / "sensitivity_table.tex").write_text(table(
            "\\textbf{Exploratory, not pre-specified (protocol v0.3):} rates when constructed candidates are labeled by construction "
            "intent (including those the pre-specified rule marked ambiguous). $^{*}$: degenerate interval; exact: binomial "
            "interval ignoring clustering.", "tab:sensitivity", "lll",
            "Condition & False acceptance & False rejection", xrows, size="\\footnotesize"))

    if a.get("near_miss_crosstab"):
        prow = []
        xt, ck, nd = a["near_miss_crosstab"], a.get("sensitivity_check_labels", {}), a.get("sensitivity_without_duplicates", {})
        for c, _ in ordered(xt):
            x = xt[c]
            k = ck.get(c, {})
            n = nd.get(c, {})
            prow.append(f"{tex(PILOT_COND_TEX.get(c, c))} & {x['confirmed_invalid']['accepted']}/{x['confirmed_invalid']['n']} & "
                        f"{x['ambiguous']['accepted']}/{x['ambiguous']['n']} & {k.get('fa_num', '-')}/{k.get('fa_den', '-')} & "
                        f"{k.get('fr_num', '-')}/{k.get('fr_den', '-')} & {n.get('fa_num', '-')}/{n.get('fa_den', '-')} & {n.get('fr_num', '-')}/{n.get('fr_den', '-')} \\\\")
            led.add("posthoc", f"{run_id} {c} near-miss accepted confirmed/ambiguous; check-label FA/FR; no-duplicate FA/FR",
                    f"{x['confirmed_invalid']}, {x['ambiguous']}; {k.get('fa_num')}/{k.get('fa_den')}, {k.get('fr_num')}/{k.get('fr_den')}; "
                    f"{n.get('fa_num')}/{n.get('fa_den')}, {n.get('fr_num')}/{n.get('fr_den')}", f"{src} near_miss_crosstab / sensitivity_check_labels / sensitivity_without_duplicates")
        b1 = a.get("b1_upstream_only")
        if b1:
            prow.append(f"B1 upstream tests only & -- & -- & -- & -- & {b1['fa_num']}/{b1['fa_den']} (all) & {b1['fr_num']}/{b1['fr_den']} (all) \\\\")
            led.add("posthoc", f"{run_id} B1 upstream-only FA/FR", f"{b1['fa_num']}/{b1['fa_den']}, {b1['fr_num']}/{b1['fr_den']}", f"{src} b1_upstream_only")
        n_dup = len(a.get("duplicates", {}))
        led.add("posthoc", f"{run_id} held-out candidates dropped as duplicates (caption)", n_dup, f"{src} duplicates")
        (out / "posthoc_table.tex").write_text(table(
            "\\textbf{Exploratory, post hoc (protocol v0.4; duplicates view widened in v0.5).} Near misses accepted among those "
            "the label rule confirmed invalid and among those it marked ambiguous; rates under the independent construction "
            f"checks' labels; rates without the {n_dup} held-out candidates that duplicate another candidate (same graded "
            "patch, or same code apart from comments and docstrings). Last row: B1 scored only on checks from the base "
            "commit's own tests (all candidates, primary labels).", "tab:posthoc", "lrrrrrr",
            "Condition & NM conf. & NM amb. & FA (checks) & FR (checks) & FA (no dup.) & FR (no dup.)", prow, size="\\footnotesize"))

    lrows = []
    for t, d in a.get("labels", {}).items():
        cn = d["counts"]
        lrows.append(f"{tex(t)} & {cn.get('valid', 0)} & {cn.get('invalid', 0)} & {cn.get('ambiguous', 0)} & {cn.get('unlabeled', 0)} & {len(d['review_queue'])} \\\\")
        led.add("labels", f"{t} valid/invalid/ambiguous/unlabeled/queued",
                f"{cn.get('valid', 0)}/{cn.get('invalid', 0)}/{cn.get('ambiguous', 0)}/{cn.get('unlabeled', 0)}/{len(d['review_queue'])}", f"{src} labels.{t}")
    if lrows:
        (out / "labels_table.tex").write_text(table(
            "Proposed labels of held-out candidates under rule D19 and the queue for human review (ambiguous, unlabeled, or "
            "disagreeing with the independent construction check).", "tab:labels", "lrrrrr",
            "Task & Valid & Invalid & Ambiguous & Unlabeled & Queued", lrows, size="\\footnotesize"))

    vrows = []
    for t, cv in a.get("coverage", {}).items():
        ag = a.get("mapping_agreement", {}).get(t, {})
        n_ref = len(cv.get("reference_scored", []))
        for v, d in cv.get("variants", {}).items():
            d2 = cv.get("variants_mapper2", {}).get(v)
            k = ag.get(v, {}).get("kappa")
            c2 = f"{d2['coverage']:.2f}" if d2 and d2.get("coverage") is not None else "--"
            cbc = len(d.get("covered_but_contradicted", []))
            vrows.append(f"{tex(t)} & {tex(v.replace('_', '-'))} & {d['coverage']:.2f} ({len(d['covered'])}/{n_ref}) & {cbc} & "
                         f"{len(d['unsupported'])}/{d['n_recovered_scored']} & {len(d['contradicting'])} & {c2} & {'--' if k is None else f'{k:.2f}'} \\\\")
            led.add("coverage", f"{t} {v} coverage/covered-but-contradicted/unsupported/contradicting/coverage2/kappa",
                    f"{d['coverage']} ({len(d['covered'])}/{n_ref}), {cbc}, {len(d['unsupported'])}/{d['n_recovered_scored']}, {len(d['contradicting'])}, "
                    f"{d2['coverage'] if d2 else None}, {k}", f"{src} coverage.{t} / mapping_agreement.{t}")
    if vrows:
        (out / "coverage_table.tex").write_text(table(
            "Recovered contracts against the reference contract (model mappings, proposals; one mapper-1 claim corrected by the "
            "builder, see text). Coverage: share of active scored reference requirements that a recovered requirement maps to "
            "without contradicting it. Contra.\\ cov.: covered requirements that another recovered requirement contradicts "
            "(reported, not subtracted).", "tab:coverage", "llrrrrrr",
            "Task & Contract & Coverage & Contra.\\ cov. & Unsupported & Contradicting & Coverage (mapper 2) & $\\kappa$", vrows, size="\\footnotesize"))

    # Compact outcome matrix (appendix).
    mrows = []
    conds = [c for c, _ in ordered(a["conditions"])]
    for t, cd in per_task.items():
        cands: dict = {}
        for c in conds:
            for r in cd.get(c, []):
                cands.setdefault(r["candidate"], {"origin": r["origin"], "label": r["label"]})[c] = r["outcome"]
        for cid, d in sorted(cands.items()):
            mark = lambda o: "\\checkmark" if o == "pass" else ("--" if o is None else "$\\times$")  # noqa: E731
            short = {"observed_pre_correction": "pre-corr.", "constructed_near_miss": "near miss", "valid_alternative": "alternative"}.get(d["origin"], d["origin"])
            mrows.append(f"{tex(cid)} & {short} & {tex(d['label'] or '--')} & " + " & ".join(mark(d.get(c)) for c in conds) + " \\\\")
    hdr = "Candidate & Origin & Label & " + " & ".join(tex(PILOT_COND_TEX.get(c, c).split(' ')[0]) for c in conds)
    (out / "outcome_matrix.tex").write_text(table(
        f"Outcome of every verifier on every held-out candidate, run \\texttt{{{tex(run_id)}}} (\\checkmark{{}} pass, $\\times$ any "
        "non-pass outcome).", "tab:matrix", "lll" + "c" * len(conds), hdr, mrows, size="\\scriptsize"))
    led.add("matrix", f"{run_id} outcome matrix rows", len(mrows), f"{src} per_task")


def comparisons(new_run: Path, old_runs: list[Path], led: Ledger, out: Path) -> None:
    rows = []
    for old in old_runs:
        p = new_run / f"compare_{old.name}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        if "pairs_same_verifier" not in d:
            raise SystemExit(f"{rel(p)} predates the changed-verifier split (D37); regenerate it with scripts/compare_runs.py")
        n = d["pairs_same_verifier"]
        rd, od = len(d["reward_discordant"]), len(d["outcome_discordant"])
        ch = d.get("changed_verifier_pairs", [])
        ch_same = sum((c["old"] == "pass") == (c["new"] == "pass") for c in ch)
        ch_txt = f"{ch_same}/{len(ch)}" if ch else "--"
        harness = sorted({json.loads(x).get("harness_version") or "?" for x in (old / "results.jsonl").read_text().split("\n") if x.strip()})
        h_txt = ", ".join(h.split("/")[-1] for h in harness)
        r_txt, o_txt = (f"{n - rd}/{n}", f"{n - od}/{n}") if n else ("--", "--")
        rows.append(f"\\texttt{{{tex(d['old_run'])}}} & {tex(h_txt)} & {n} & {r_txt} & {o_txt} & {ch_txt} \\\\")
        led.add("reliability", f"{d['old_run']} vs {d['new_run']}: harness, unchanged-verifier pairs, reward agreement, outcome agreement",
                f"{h_txt}, {n}, {r_txt}, {o_txt}", f"{rel(p)}; {rel(old / 'results.jsonl')} harness_version")
        if ch:
            led.add("reliability", f"{d['old_run']} vs {d['new_run']}: changed-verifier pairs with the same reward", ch_txt, rel(p))
    if rows:
        (out / "reliability_table.tex").write_text(table(
            f"Agreement of earlier runs with the final run \\texttt{{{tex(new_run.name)}}} on pairs graded in both. Reward agreement "
            "is pass vs non-pass; outcome agreement is the exact outcome. Both are computed on pairs whose verifier is unchanged "
            "(same version, test content and scored check list: the check-list hash where both run manifests record it, "
            "otherwise the number of scored checks). The last column covers pairs whose verifier changed between the runs "
            "(B1 re-selection, D31).", "tab:reliability", "llrrrr",
            "Earlier run & Harness & Pairs & Reward agr. & Outcome agr. & Changed verifier", rows, size="\\footnotesize"))


def verifiers(run: Path, led: Ledger, out: Path) -> None:
    """Verifier construction: checks per verifier, audit revisions, and the B1 checks the session agent added."""
    a = json.loads((run / "analysis.json").read_text())
    up = (a.get("b1_upstream_only") or {}).get("n_checks", {})
    rows = []
    for td in sorted((ROOT / "tasks").glob("*/task.json")):
        m = json.loads(td.read_text())
        specs = {}
        for p in m["verifiers"]:
            sp = json.loads((td.parent / p).read_text())
            specs[sp["condition"]] = (sp, td.parent / p)
        cells = []
        for cond in ("initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform", "repo_tests", "reference_check"):
            if cond not in specs:
                cells.append("--")
                continue
            sp, path = specs[cond]
            n = len(sp["checks"])
            txt = str(n)
            if cond in ("initial_audited", "full_audited") and sp.get("audit"):
                plain = specs.get(cond.replace("audited", "plain"), (None,))[0]
                same = plain is not None and plain["content_sha256"] == sp["content_sha256"]
                it, ok = sp["audit"]["iterations"], sp["audit"]["passed"]
                txt += f" ({it} rev.{'' if ok else ', not passed'}{'; = plain' if same else ''})"
                led.add("verifiers", f"{m['task_id']} {cond} checks / audit revisions / audit passed / identical to plain",
                        f"{n} / {it} / {ok} / {same}", rel(path))
            elif cond == "repo_tests" and m["task_id"] in up:
                txt += f" ({n - up[m['task_id']]} agent-added)"
                led.add("verifiers", f"{m['task_id']} repo_tests checks / agent-added checks", f"{n} / {n - up[m['task_id']]}",
                        f"{rel(path)}; {rel(run / 'analysis.json')} b1_upstream_only.n_checks")
            else:
                led.add("verifiers", f"{m['task_id']} {cond} checks", n, rel(path))
            cells.append(txt)
        rows.append(f"{tex(m['task_id'])} & " + " & ".join(cells) + " \\\\")
    (out / "verifiers_table.tex").write_text(table(
        "Verifiers per task (generated from \\texttt{tasks/*/verifiers/*/spec.json}): scored checks. Audited verifiers: audit "
        "revisions, whether the audit passed, and ``= plain'' when the audited tests are identical to the plain ones. B1: checks "
        "added to the repository's tests by the session agent (not in the base commit). Ref.: reference checks used for labels.",
        "tab:verifiers", "lccccccc", "Task & C1 & C2 & C3 & C4 & B2 & B1 & Ref.", rows, size="\\scriptsize"))


# ----------------------------------------------------------------------------------------------------------------------
# New runs (protocol v0.7 §15.7, v0.8 §16.6): the fresh-agent stratum (--fresh, --regrade) and the natural arm (--natural).
# Each mode writes its own subdirectory of paper/generated/ and its own ledger, with one section per table and a section
# "numbers" for the macros the prose uses (\fv{key}, \nat{key}). The pilot's outputs are never touched by these modes.
# ----------------------------------------------------------------------------------------------------------------------

SHORT = {"initial_plain": "C1", "initial_audited": "C2", "full_plain": "C3", "full_audited": "C4", "llm_freeform": "B2",
         "repo_tests": "B1"}
NO_HUMAN = "\\textbf{All labels are model proposals; no human labels exist.}"
FOUR_FAMILIES = "Four controlled families: descriptive, not inferential."
# The verifiers that support the labels (D19's reference checks, protocol §15.5's independent labeler), not conditions.
LABEL_SUPPORT = ("reference_check", "independent_label")
# The one caveat marker that every caption of fresh-v1's tables and figures ends with, in place of repeated caveat
# sentences (restructure plan, finding 20; the pilot's own tables are frozen and keep theirs); <n>: the run's families.
# Its symbol is a diamond, not the plan's dagger: the natural run's false-acceptance table marks with a dagger the cells
# the oracle-gated view drops, as the natural section (fixed before the run's analysis, D77) says, and one symbol is to
# mean one thing in the manuscript.
CONTROLLED_MARKER = ("$^{{\\diamond}}$Automated pilot; model-proposed labels, no human labels; {n} controlled families; "
                     "descriptive (\\S\\ref{{sec:intro}}).")


def controlled_marker(n_families: int, led, table: str, src: str) -> str:
    """The caption marker of the controlled arm, with its number of families as a caption value of ``table``."""
    led.add(table, "caption marker: controlled families", n_families, f"{src} n_families")
    return CONTROLLED_MARKER.format(n=n_families)


class SectionLedger:
    """A ledger grouped by table. Every entry is ``- [table] what = value <- `file field```."""

    def __init__(self, title: str, intro: str) -> None:
        self.head = [f"# {title}", "", intro, ""]
        self.sections: dict[str, list[str]] = {}

    def add(self, table: str, what: str, value, src: str) -> None:
        self.sections.setdefault(table, []).append(f"- [{table}] {what} = {value} <- `{src}`")

    def __len__(self) -> int:
        return sum(len(v) for v in self.sections.values())

    def text(self) -> str:
        out = list(self.head)
        order = sorted(self.sections, key=lambda k: (k != "inputs", k == "numbers"))  # stable: inputs, tables, numbers
        for name in order:
            out += [f"## {name}", "", *self.sections[name], ""]
        return "\n".join(out).rstrip("\n") + "\n"


class Numbers:
    """Number macros for the prose. ``numbers.tex`` stores each value as the control sequence ``\\csname <prefix>:<key>\\endcsname``
    (a colon, not an at sign, so that no stored name looks like an e-mail address to scripts/scan_tracked_files.py); main.tex
    defines the lookup ``\\<prefix>{key}``, which prints ``\\unfilled{missing number <key>}`` for a key that is not stored.
    Every value is also a ledger entry (section ``numbers``)."""

    KEY = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")

    def __init__(self, prefix: str, led: SectionLedger) -> None:
        self.prefix, self.led, self.values = prefix, led, {}

    def put(self, key: str, value, src: str, what: str = "") -> None:
        if not self.KEY.fullmatch(key):
            raise ValueError(f"number key {key!r}: lower-case letters and digits separated by '.' or '-' only")
        if key in self.values:
            raise ValueError(f"number key {key!r} is defined twice")
        v = str(value)
        if re.search(r"(?<!\\)[%#]", v) or v.count("{") != v.count("}"):
            raise ValueError(f"number key {key!r}: value {v!r} is not safe inside a macro")
        self.values[key] = v
        self.led.add("numbers", f"\\{self.prefix}{{{key}}}" + (f" ({what})" if what else ""), v, src)

    def put_count(self, key: str, n: int, src: str, what: str = "") -> None:
        """A count, and for zero to twenty also its word form ``<key>.w`` (four), for prose that writes it as a word."""
        if isinstance(n, bool) or not isinstance(n, int):
            raise TypeError(f"number key {key!r}: {n!r} is not a count")
        self.put(key, n, src, what)
        if 0 <= n < len(COUNT_WORDS):
            self.put(f"{key}.w", COUNT_WORDS[n], src, (what + "; " if what else "") + "in words")

    def tex(self, cmd: str) -> str:
        p = self.prefix
        lines = [f"% Generated by `{cmd}`; do not edit. Every value is listed in the ledger, section numbers.",
                 f"% Each value is stored as \\csname {p}:<key>\\endcsname. The lookup that main.tex defines:",
                 f"% \\newcommand{{\\{p}}}[1]{{\\ifcsname {p}:#1\\endcsname\\csname {p}:#1\\endcsname"
                 f"\\else\\unfilled{{missing number #1}}\\fi}}"]
        lines += [f"\\expandafter\\gdef\\csname {p}:{k}\\endcsname{{{v}}}" for k, v in sorted(self.values.items())]
        return "\n".join(lines) + "\n"


COUNT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
               "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty")


def _frac(num, den) -> str:
    return "n/a" if not den else f"{num}/{den}"


def _r2(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _signed(x, nd: int = 2) -> str:
    """A signed number with a typographic sign that works in text and math; zero has no sign."""
    if x is None:
        return "n/a"
    s = f"{abs(x):.{nd}f}"
    if float(s) == 0:
        return s
    return ("\\ensuremath{+}" if x > 0 else "\\ensuremath{-}") + s


def _p(p) -> str:
    """An exact sign-flip p-value: these are multiples of 2^-k, so four significant digits print them exactly here."""
    return "n/a" if p is None else f"{p:.4g}"


def _int(n: int) -> str:
    """An integer with thousands separators that is safe in text and in math."""
    return f"{n:,}".replace(",", "{,}")


def _pct(x: float, nd: int = 1) -> str:
    return f"{100 * x:.{nd}f}\\%"


def _iv(ci, nd: int = 2) -> str:
    return "n/a" if not ci else f"[{ci[0]:.{nd}f}, {ci[1]:.{nd}f}]"


def _iv_signed(ci, nd: int = 2) -> str:
    """An interval of a difference, with typographic minus signs."""
    return "n/a" if not ci else f"[{_signed(ci[0], nd)}, {_signed(ci[1], nd)}]"


def _fk(task_id: str) -> str:
    """The key form of a family id in number macros: CS-01 -> cs01, NP-03 -> np03."""
    return task_id.lower().replace("-", "")


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval (95%) of k successes in n."""
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def _check_private(text: str, where: str, *, digit_runs: bool, names: tuple[str, ...] = (),
                   exempt: tuple[str, ...] = ()) -> None:
    """Refuse to write a URL, an owner placeholder, a session-local path, a model or agent-product name, or (natural
    outputs) a digit run of 7 or more, which would be a PR, comment, issue or repository id. ``exempt``: strings that the
    digit-run rule skips where each stands as a whole token (no letter or digit next to it): a natural run's own code
    revisions, which name commits of the study's repository, never a PR, comment, issue or repository of the data. Every
    other rule reads the whole text."""
    runs = text  # the text the digit-run rule reads
    for e in sorted(set(exempt), key=len, reverse=True):
        runs = re.sub(r"(?<![0-9A-Za-z])" + re.escape(e) + r"(?![0-9A-Za-z])", " ", runs)
    pats = [(r"https?:|github\.com|\{owner\}", "a URL or an owner placeholder", text),
            (r"/home/|/tmp/|/root/|scratchpad", "a session-local path", text),
            (r"\bclaude|\bopus\b|\bsonnet\b|\bhaiku\b|\bgemini\b|\bgpt-?\d", "a model or agent-product identifier", text)]
    if digit_runs:
        pats.append((r"\d{7,}", "a digit run of 7 or more (an id)", runs))
    pats += [(r"\b" + re.escape(n) + r"\b", "an agent product name", text) for n in names]
    for pat, why, where_text in pats:
        hit = re.search(pat, where_text, re.I)
        if hit:
            raise ValueError(f"{where}: refusing to write {why}: {hit.group(0)!r}")


def _fa_fr(d: dict) -> str:
    return f"{_frac(d['fa_num'], d['fa_den'])} $\\cdot$ {_frac(d['fr_num'], d['fr_den'])}"


# -- fresh-agent stratum ------------------------------------------------------------------------------------------------

def fresh_inputs(run: Path) -> dict:
    """Read a fresh-attempt run and the files its tables join with, and check what the captions take for granted."""
    a = json.loads((run / "analysis.json").read_text())
    s = json.loads((run / "analysis_sensitivity.json").read_text())
    m = json.loads((run / "manifest.json").read_text())
    rows = [json.loads(x) for x in (run / "results.jsonl").read_text().split("\n") if x.strip()]
    src = rel(run / "analysis.json")
    if "automated pilot" not in a["meta"]["label_policy"]:
        raise ValueError(f"{src}: label policy {a['meta']['label_policy']!r}; the captions say every label is a model proposal")
    for view, vsrc in ((a, src), (s, rel(run / "analysis_sensitivity.json"))):
        if [c for c, _ in ordered(view["conditions"])] != ORDER:
            raise ValueError(f"{vsrc}: conditions {sorted(view['conditions'])}, expected the six of the protocol")
    fams = sorted(a["per_task"])
    strata = sorted({k for t in a["meta"]["strata"].values() for k in t})
    if len(strata) != 1:
        raise ValueError(f"{src}: one candidate stratum expected, found {strata}")
    if a["distinct_patches"]["groups"] or s["distinct_patches"]["groups"]:
        raise ValueError(f"{src}: some units hold several attempts; the attempt-level tables assume one attempt per unit")
    att, att_src, up, up_src = {}, {}, {}, {}
    for t in fams:
        p = ROOT / "data" / "fresh" / strata[0] / f"attempts_{t}.json"
        f = json.loads(p.read_text())
        if f["task_id"] != t or f["stratum"] != strata[0]:
            raise ValueError(f"{rel(p)}: task {f['task_id']}, stratum {f['stratum']}; expected {t}, {strata[0]}")
        att[t], att_src[t] = f, rel(p)
        q = ROOT / "tasks" / t / "verifiers" / "repo_tests" / "upstream_check_ids.json"
        up[t], up_src[t] = json.loads(q.read_text()), rel(q)
    attempt = {x["id"]: dict(x, task_id=t) for t in fams for x in att[t]["attempts"]}
    return {"a": a, "s": s, "m": m, "rows": rows, "fams": fams, "stratum": strata[0], "att": att, "att_src": att_src,
            "attempt": attempt, "up": up, "up_src": up_src, "run_id": m["run_id"], "src": src,
            "ssrc": rel(run / "analysis_sensitivity.json"), "msrc": rel(run / "manifest.json"),
            "rsrc": rel(run / "results.jsonl")}


def _units(view: dict, fams: list[str]) -> dict[tuple[str, str], dict]:
    """The held-out units of a view by (task, candidate): label, negative type and the outcome under each condition."""
    out: dict = {}
    for t in fams:
        for c in ORDER:
            for r in view["per_task"][t][c]:
                u = out.setdefault((t, r["candidate"]), {"label": r["label"], "negative_type": r["negative_type"], "outcome": {}})
                if (u["label"], u["negative_type"]) != (r["label"], r["negative_type"]):
                    raise ValueError(f"per_task.{t}: {r['candidate']} has different labels under different conditions")
                u["outcome"][c] = r["outcome"]
    return out


def fresh_run_numbers(F: dict, led: SectionLedger, nums: Numbers) -> None:
    """Run-level numbers: pairs, repeats, outcomes, harness, revision, time, attempts, units, exclusions, review queue."""
    a, m, rows = F["a"], F["m"], F["rows"]
    src, msrc, rsrc = F["src"], F["msrc"], F["rsrc"]
    oc = Counter(r["outcome"] for r in rows)
    harness = sorted({r["harness_version"] for r in rows})
    if len(harness) != 1 or a["meta"]["harness_versions"] != {harness[0]: len(rows)}:
        raise ValueError(f"{rsrc}: harness versions {harness} do not match {src} meta.harness_versions")
    if a["meta"]["n_results"] != len(rows):
        raise ValueError(f"{src}: meta.n_results {a['meta']['n_results']} but {len(rows)} rows in {rsrc}")
    nums.put("run.pairs", _int(len(rows)), f"{rsrc} (rows; = {src} meta.n_results)", "graded pairs")
    nums.put_count("run.repeats", m["repeats"], f"{msrc} repeats")
    nums.put("run.pass", _int(oc["pass"]), f"{rsrc} outcome (count of pass)")
    nums.put("run.taskfailure", _int(oc["task_failure"]), f"{rsrc} outcome (count of task_failure)")
    nums.put("run.other", sum(v for k, v in oc.items() if k not in ("pass", "task_failure")),
             f"{rsrc} outcome (count of any other outcome: infrastructure, unresolved)", "infrastructure or unresolved outcomes")
    nums.put("run.unresolved", oc.get("unresolved", 0), f"{rsrc} outcome (count of unresolved)")
    nums.put("run.harness", harness[0].split("/")[-1], f"{rsrc} harness_version (one value in every row)")
    nums.put("run.revision", m["code_revision"][:7], f"{msrc} code_revision")
    nums.put("run.date", m["started_at"][:10], f"{msrc} started_at")
    nums.put("run.started", m["started_at"][11:19], f"{msrc} started_at", "UTC")
    nums.put("run.finished", m["finished_at"][11:19], f"{msrc} finished_at", "UTC")
    verifiers = Counter(r["verifier_id"] for r in rows)
    nums.put("run.verifiers", len(verifiers), f"{rsrc} verifier_id (distinct values)", "verifiers graded: six conditions, reference checks, independent labeler")
    per_v = sorted(set(verifiers.values()))
    if len(per_v) != 1:
        raise ValueError(f"{rsrc}: verifiers graded on different numbers of candidates: {dict(verifiers)}")
    nums.put("run.candidates", per_v[0], f"{rsrc} verifier_id (rows per verifier)", "candidates per verifier: the attempts and the references")
    n_att = sum(f["summary"]["attempts"] for f in F["att"].values())
    nums.put("attempts", n_att, "; ".join(f"{F['att_src'][t]} summary.attempts" for t in F["fams"]))
    fa = a["fresh_attempts"]
    nums.put_count("attempts.excluded", fa["n_excluded"], f"{src} fresh_attempts.n_excluded")
    if len(fa["excluded"]) != fa["n_excluded"]:
        raise ValueError(f"{src}: fresh_attempts.excluded does not list n_excluded attempts")
    for i, x in enumerate(fa["excluded"]):
        nums.put(f"excluded.{i + 1}", tex(x["candidate_id"]), f"{src} fresh_attempts.excluded[{i}].candidate_id", "excluded attempt")
    nums.put("units", a["distinct_patches"]["n_distinct"], f"{src} distinct_patches.n_distinct", "distinct graded patches")
    nums.put("units.heldout", a["distinct_patches"]["n_heldout"], f"{src} distinct_patches.n_heldout")
    dens = {(d["false_acceptance"]["den"], d["false_rejection"]["den"]) for d in a["conditions"].values()}
    if len(dens) != 1:
        raise ValueError(f"{src}: the conditions have different FA or FR denominators: {dens}")
    inv, val = dens.pop()
    nums.put("units.invalid", inv, f"{src} conditions.<every condition>.false_acceptance.den", "D19 invalid units")
    nums.put("units.valid", val, f"{src} conditions.<every condition>.false_rejection.den", "D19 valid units")
    lab = a["independent_labeling"]["labels"]
    nums.put("il.units.invalid", lab["invalid"], f"{src} independent_labeling.labels.invalid")
    nums.put("il.units.valid", lab["valid"], f"{src} independent_labeling.labels.valid")
    nums.put("il.units.ambiguous", lab["ambiguous"], f"{src} independent_labeling.labels.ambiguous")
    queued = sum(len(a["labels"][t]["strata"][F["stratum"]]["review_queue"]) for t in F["fams"])
    nums.put("queue", queued, f"{src} labels.<task>.strata.{F['stratum']}.review_queue (lengths summed)", "units queued for human review")
    flagged = {t: F["att"][t]["summary"]["flagged_by_the_audit_script"] for t in F["fams"]}
    for t in F["fams"]:
        nums.put(f"flagged.{_fk(t)}", flagged[t], f"{F['att_src'][t]} summary.flagged_by_the_audit_script")
    nums.put("flagged", sum(flagged.values()), "; ".join(f"{F['att_src'][t]} summary.flagged_by_the_audit_script" for t in F["fams"]))
    sens = F["s"]["meta"]["sensitivity"]
    ids = [x["candidate_id"] for x in sens["excluded_here"] + sens["already_excluded"]]
    if len(ids) != sum(flagged.values()):
        raise ValueError(f"{F['ssrc']}: meta.sensitivity excludes {len(ids)} attempts, the audit script flagged {sum(flagged.values())}")
    n_a = sum(F["attempt"][i]["configuration"] == "config-A" for i in ids)
    nums.put("flagged.configa", n_a, f"{F['ssrc']} meta.sensitivity.excluded_here, already_excluded (candidate ids) joined with "
             "attempts[].configuration of " + ", ".join(F["att_src"][t] for t in F["fams"]), "flagged attempts of configuration A")
    generated: dict[str, list[int]] = {"plain": [], "audited": []}  # scored checks: C1, C3, B2 (plain); C2, C4 (audited)
    for t in F["fams"]:
        for c in (*ORDER, "reference_check", "independent_label"):
            p = ROOT / "tasks" / t / "verifiers" / c / "spec.json"
            if p.exists():
                key = {"reference_check": "ref", "independent_label": "il"}.get(c, SHORT.get(c, c).lower())
                n = len(json.loads(p.read_text())["checks"])
                nums.put(f"checks.{_fk(t)}.{key}", n, f"{rel(p)} checks (count)")
                if c not in ("repo_tests", "reference_check", "independent_label"):
                    generated["audited" if c.endswith("_audited") else "plain"].append(n)
    how = "tasks/<task>/verifiers/{initial,full}_{plain,audited},llm_freeform/spec.json checks (count)"
    every = generated["plain"] + generated["audited"]
    nums.put("checks.generated.min", min(every), how + ", minimum", "scored checks of a generated verifier (C1-C4, B2)")
    nums.put("checks.generated.max", max(every), how + ", maximum")
    # The plain generators' output apart from the audited verifiers, whose reviser may keep more tests than a generator is
    # asked to write (the generate workflow's "Keep 6-16 tests"; \dv{design.revise.tests.*}).
    how = "tasks/<task>/verifiers/{initial_plain,full_plain,llm_freeform}/spec.json checks (count)"
    nums.put("checks.plain.min", min(generated["plain"]), how + ", minimum", "scored checks of a plain generated verifier (C1, C3, B2)")
    nums.put("checks.plain.max", max(generated["plain"]), how + ", maximum")
    how = "tasks/<task>/verifiers/{initial_audited,full_audited}/spec.json checks (count)"
    nums.put("checks.audited.min", min(generated["audited"]), how + ", minimum", "scored checks of an audited verifier (C2, C4)")
    nums.put("checks.audited.max", max(generated["audited"]), how + ", maximum")


def fresh_design_numbers(F: dict, led: SectionLedger, nums: Numbers) -> None:
    """The design's counts as the records hold them (restructure plan, part 5.1): families, configurations and conditions,
    and per instruction the attempts that D19 labels valid and invalid (estimand 1 of protocol §15.4)."""
    a, m, src, msrc = F["a"], F["m"], F["src"], F["msrc"]
    if a["n_families"] != len(F["fams"]):
        raise ValueError(f"{src}: n_families = {a['n_families']}, per_task holds {len(F['fams'])} families")
    nums.put_count("families", a["n_families"], f"{src} n_families", "controlled task families")
    bcv = a["fresh_attempts"]["by_configuration_variant"]
    cfgs = sorted({d["configuration"] for d in bcv.values()})
    nums.put_count("run.configurations", len(cfgs), f"{src} fresh_attempts.by_configuration_variant.*.configuration "
                   f"(distinct values: {', '.join(cfgs)})", "agent configurations")
    conds = [c for c in m["conditions"] if c not in LABEL_SUPPORT]
    if sorted(conds) != sorted(ORDER) or sorted(a["conditions"]) != sorted(ORDER):
        raise ValueError(f"{msrc}: conditions {m['conditions']}; expected the six of the protocol and the label support")
    nums.put_count("run.conditions", len(conds), f"{msrc} conditions, less the label-support verifiers "
                   f"({', '.join(c for c in m['conditions'] if c in LABEL_SUPPORT)})", "verifier conditions (C1-C4, B2, B1)")
    for var in sorted({d["variant"] for d in bcv.values()}):
        ds = {k: d for k, d in bcv.items() if d["variant"] == var}
        base = f"{src} fresh_attempts.by_configuration_variant.{{{','.join(sorted(ds))}}}"
        att, solved = sum(d["attempts"] for d in ds.values()), sum(d["solved"] for d in ds.values())
        invalid, undecided = sum(d["not_solved"] for d in ds.values()), sum(d["undecided"] for d in ds.values())
        if solved + invalid + undecided != att:
            raise ValueError(f"{base}: solved, not_solved and undecided do not add up to attempts")
        nums.put(f"solve.{var}", f"{solved}/{att}", f"{base}.solved, .attempts (summed)", f"{var} attempts D19 labels valid")
        nums.put(f"{var}.invalid", f"{invalid}/{att}", f"{base}.not_solved, .attempts (summed)", f"{var} attempts D19 labels invalid")
        nums.put(f"{var}.invalid.n", invalid, f"{base}.not_solved (summed)")
        nums.put(f"{var}.undecided", undecided, f"{base}.undecided (summed)", "neither valid nor invalid under D19")
        nums.put(f"{var}.attempts", att, f"{base}.attempts (summed)")


def _per_family_cells(F: dict, view: dict, vsrc: str, led: SectionLedger, nums: Numbers, name: str, p: str) -> dict:
    """Per condition, the per-family and pooled FA and FR cells under D19 and under the independent labeler, each a
    ledger entry and a macro (``<p><c>.<family>.<m>``, ``<p>il.<c>.<family>.<m>``, ``<p>il.<c>.<m>``)."""
    fams = F["fams"]
    il = view["independent_labeling"]["conditions"]
    out = {}
    for c in ORDER:
        sh = SHORT[c].lower()
        pf, lab = view["per_family"][c], il[c]["independent_label"]
        if il[c]["primary"]["per_family"] != pf:
            raise ValueError(f"{vsrc}: per_family.{c} differs from independent_labeling.conditions.{c}.primary.per_family")
        fa, fr = view["conditions"][c]["false_acceptance"], view["conditions"][c]["false_rejection"]
        for k, tot in (("fa_num", fa["num"]), ("fa_den", fa["den"]), ("fr_num", fr["num"]), ("fr_den", fr["den"])):
            if sum(pf[t][k] for t in fams) != tot:
                raise ValueError(f"{vsrc}: per_family.{c}.*.{k} does not sum to the pooled value {tot}")
        lfa, lfr = lab["false_acceptance"], lab["false_rejection"]
        cells = {"rule": {"fa": [], "fr": []}, "labeler": {"fa": [], "fr": []}}
        for t in fams:
            d, ll = pf[t], lab["per_family"][t]
            led.add(name, f"{c} {t} D19 FA; FR", f"{d['fa_num']}/{d['fa_den']}; {d['fr_num']}/{d['fr_den']}", f"{vsrc} per_family.{c}.{t}")
            led.add(name, f"{c} {t} labeler FA; FR", f"{ll['fa_num']}/{ll['fa_den']}; {ll['fr_num']}/{ll['fr_den']}",
                    f"{vsrc} independent_labeling.conditions.{c}.independent_label.per_family.{t}")
            for m in ("fa", "fr"):
                cells["rule"][m].append(_frac(d[f"{m}_num"], d[f"{m}_den"]))
                cells["labeler"][m].append(_frac(ll[f"{m}_num"], ll[f"{m}_den"]))
                nums.put(f"{p}{sh}.{_fk(t)}.{m}", _frac(d[f"{m}_num"], d[f"{m}_den"]), f"{vsrc} per_family.{c}.{t}.{m}_num, .{m}_den")
                nums.put(f"{p}il.{sh}.{_fk(t)}.{m}", _frac(ll[f"{m}_num"], ll[f"{m}_den"]),
                         f"{vsrc} independent_labeling.conditions.{c}.independent_label.per_family.{t}.{m}_num, .{m}_den")
        for m, x, y in (("fa", fa, lfa), ("fr", fr, lfr)):
            cells["rule"][m].append(_frac(x["num"], x["den"]))
            cells["labeler"][m].append(_frac(y["num"], y["den"]))
        led.add(name, f"{c} pooled D19 FA; FR", f"{fa['num']}/{fa['den']}; {fr['num']}/{fr['den']}",
                f"{vsrc} conditions.{c}.false_acceptance, .false_rejection (num, den)")
        led.add(name, f"{c} pooled labeler FA; FR", f"{lfa['num']}/{lfa['den']}; {lfr['num']}/{lfr['den']}",
                f"{vsrc} independent_labeling.conditions.{c}.independent_label.false_acceptance, .false_rejection (num, den)")
        for m, x in (("fa", lfa), ("fr", lfr)):
            key = "false_acceptance" if m == "fa" else "false_rejection"
            nums.put(f"{p}il.{sh}.{m}", _frac(x["num"], x["den"]), f"{vsrc} independent_labeling.conditions.{c}.independent_label.{key}.num, .den")
            nums.put(f"{p}il.{sh}.{m}.rate", _r2(x["rate"]), f"{vsrc} independent_labeling.conditions.{c}.independent_label.{key}.rate")
        out[c] = cells
    return out


def fresh_split_table(F: dict, cells: dict, which: str, caption: str, label: str) -> str:
    """One labeling's per-family table, split into a false-acceptance and a false-rejection column group (restructure plan,
    part 6): a row per condition; per group a column per family and the pooled value (num/den)."""
    fams, n = F["fams"], len(F["fams"]) + 1
    rows = [f"{tex(COND_TEX[c])} & " + " & ".join(cells[c][which]["fa"]) + " & " + " & ".join(cells[c][which]["fr"]) + " \\\\"
            for c in ORDER]
    head = (f" & \\multicolumn{{{n}}}{{c}}{{False acceptance (accepted/invalid)}} & \\multicolumn{{{n}}}{{c}}{{False rejection "
            f"(rejected/valid)}} \\\\\\cmidrule(lr){{2-{n + 1}}}\\cmidrule(lr){{{n + 2}-{2 * n + 1}}} Condition & "
            + " & ".join([*(tex(t) for t in fams), "Pooled"] * 2))
    return table(caption, label, "l" + "r" * (2 * n), head, rows, size="\\footnotesize\\setlength{\\tabcolsep}{4pt}")


def fresh_per_family_table(F: dict, view: dict, vsrc: str, led: SectionLedger, nums: Numbers, *, name: str, label: str,
                           p: str, caption: str) -> str:
    """Per-family FA · FR under D19 and under the independent labeler, per condition, and pooled, in one table (the
    sensitivity view's layout)."""
    cells = _per_family_cells(F, view, vsrc, led, nums, name, p)
    rows = []
    for c in ORDER:
        for which, text in (("rule", f"{tex(COND_TEX[c])} & {RULE_ROW}"), ("labeler", f" & {LABELER_ROW}")):
            x = cells[c][which]
            rows.append(f"{text} & " + " & ".join(f"{fa} $\\cdot$ {fr}" for fa, fr in zip(x["fa"], x["fr"])) + " \\\\"
                        + ("\\addlinespace" if which == "labeler" and c != ORDER[-1] else ""))
    return table(caption, label, "ll" + "c" * (len(F["fams"]) + 1),
                 "Condition & Labels & " + " & ".join(tex(t) for t in F["fams"]) + " & Pooled", rows, size="\\footnotesize")


def _req_key(req: str) -> str:
    """A requirement id as part of a macro key: R-zero-step -> r-zero-step, REGRESSION -> regression, R3 -> r3."""
    k = req.lower()
    if not Numbers.KEY.fullmatch(k):
        raise ValueError(f"requirement id {req!r} cannot be part of a number key")
    return k


def scenario_requirements(task: str) -> tuple[list[dict], str]:
    """The intended requirements of a controlled scenario (hashed and logged before its session), and the file."""
    p = ROOT / "data" / "controlled" / "scenarios" / f"{task}.json"
    ir = json.loads(p.read_text())["intended_requirements"]
    return (ir if isinstance(ir, list) else ast.literal_eval(ir)), rel(p)


def _spec(task: str, cond: str) -> tuple[dict, str]:
    p = ROOT / "tasks" / task / "verifiers" / cond / "spec.json"
    return json.loads(p.read_text()), rel(p)


def fresh_behaviours(F: dict, led: SectionLedger, nums: Numbers, out: Path, *, units: dict, viol: dict, unspec: list,
                     violated: dict, marker) -> None:
    """The behaviours behind the invalid first-request attempts, by family (restructure plan, parts 5.1 and 6, Tab. 4), as
    macros and a table: what the correction changed (``corr.*``), what the invalid units broke (``beh.*``), whether each
    condition passes the family's reference (``ref.<c>.<family>``), the violators that the initial-only verifier accepts
    where it passes its reference (``cv.silent.*``, the post hoc silent-loss reading of the oracle-gated view), C1's checks
    on the retracted or broken requirement under both model mappers, C1's rejected violators, and the checks the audit's
    revisions added. Cells that repeat a key put elsewhere (``cv.c1.<family>``, ``b1.base.fa.<family>``) read its value."""
    a, fams, src, rsrc = F["a"], F["fams"], F["src"], F["rsrc"]
    name = "fresh_behaviours"
    by_row = {(r["task_id"], r["verifier_id"], r["candidate_id"]): r for r in F["rows"]}
    og = a["oracle_gated"]["conditions"]
    n_cv = sum(len(v) for v in viol.values())
    u1_invalid = int(nums.values["u1.invalid.n"])
    if u1_invalid != n_cv + len(unspec) or any(F["attempt"][cid]["variant"] != "u1" for cid in unspec):
        raise ValueError(f"{src}: {u1_invalid} invalid u1 attempts, but {n_cv} correction violators and {len(unspec)} "
                         "regression-only u1 units; the text splits the first into the other two")
    cells: dict[str, list[tuple[str, str, str]]] = {t: [] for t in fams}  # per family: (column, cell, source)

    def cell(t: str, column: str, text: str, how: str) -> None:
        cells[t].append((column, text, how))
        led.add(name, f"{column} | {t}", text, how)

    for t in fams:
        fk = _fk(t)
        # What the correction changed: the scenario's intended requirements by the turn that introduced them.
        ir, ssrc = scenario_requirements(t)
        sup = [r["id"] for r in ir if r["turn"] == "U1" and r["final_status"] == "superseded"]
        add = [r["id"] for r in ir if r["turn"] != "U1"]
        ref_contract = json.loads((ROOT / "tasks" / t / "contracts" / "reference.json").read_text())
        if sorted(r["req_id"] for r in ref_contract["requirements"] if r["status"] == "superseded") != sorted(sup):
            raise ValueError(f"tasks/{t}/contracts/reference.json: its superseded requirements are not the scenario's {sup}")
        how = f"{ssrc} intended_requirements[] (turn, final_status)"
        nums.put(f"corr.{fk}.initial", sum(r["turn"] == "U1" for r in ir), how, "requirements of the first request")
        nums.put_count(f"corr.{fk}.superseded", len(sup), how, "first-request requirements the correction retracts")
        nums.put_count(f"corr.{fk}.added", len(add), how, "requirements the correction adds")
        cell(t, "Correction", f"adds {len(add)}, retracts {len(sup) or 'none'}", how)
        # What the family's invalid units broke (each distinct graded patch once).
        inv = sorted(cid for (tt, cid), u in units.items() if tt == t and u["label"] == "invalid")
        plp = f"tasks/{t}/strata/{F['stratum']}/proposed_labels.json"
        recorded = json.loads((ROOT / plp).read_text())["candidates"]
        for cid in inv:
            if recorded[cid]["proposed"] != "invalid" or sorted(recorded[cid]["violated"]) != sorted(violated[cid]):
                raise ValueError(f"{plp}: {cid} is {recorded[cid]['proposed']} and violates {recorded[cid]['violated']}, the "
                                 f"analysis labels it invalid and says {violated[cid]}")
        cnt = Counter(req for cid in inv for req in violated[cid])
        how = f"{src} labels.{t}.strata.{F['stratum']}.candidates[].violated of the family's invalid units (per_task labels)"
        nums.put(f"beh.{fk}.n", len(inv), how, "the family's invalid units")
        for req, n in sorted(cnt.items()):
            nums.put(f"beh.{fk}.{_req_key(req)}", n, how, f"invalid units that violate {req}")
        nums.put(f"unspec.{fk}.n", sum(cid in unspec for cid in inv), how, "invalid units whose only violation is REGRESSION")
        broken = sorted(set.intersection(*(set(violated[cid]) for cid in viol[t])) & set(add)) if viol[t] else []
        nums.put(f"beh.{fk}.broken", ", ".join(broken) or "none", how + "; the correction's requirements every violator breaks")
        groups: dict[int, list[str]] = {}
        for req, n in cnt.items():
            groups.setdefault(n, []).append(req)
        cell(t, "Invalid u1 attempts: what they break", (f"{len(inv)}: " + "; ".join(
            ", ".join(sorted(groups[n])) + f" ({n})" for n in sorted(groups, reverse=True))) if inv else "none", how)
        # The reference solution under each condition.
        for c in ORDER:
            r = by_row.get((t, c, f"{t}-reference"))
            if r is None:
                raise ValueError(f"{rsrc}: no {c} row for {t}-reference")
            failed = [ch["check_id"] for ch in r["checks"] if ch["status"] != "passed"]
            passes = r["outcome"] == "pass"
            if passes == (t in og[c]["dropped"]):
                raise ValueError(f"{rsrc}: {c} on {t}-reference is {r['outcome']}, which {src} oracle_gated does not reflect")
            rhow = f"{rsrc} row ({t}, {c}, {t}-reference): outcome, checks[].status"
            nums.put(f"ref.{SHORT[c].lower()}.{fk}", "passes" if passes else "fails", rhow, "the condition on the family's reference")
            nums.put(f"ref.{SHORT[c].lower()}.{fk}.failed", len(failed), rhow, "checks that fail on the reference")
        c1, c1src = _spec(t, "initial_plain")
        n1 = len(c1["checks"])
        c1ref = nums.values[f"ref.c1.{fk}"]
        cell(t, "C1 passes its reference", "yes" if c1ref == "passes" else
             f"no ({nums.values[f'ref.c1.{fk}.failed']} of {n1} checks fail)", f"{rsrc} row ({t}, initial_plain, {t}-reference)")
        # C1's checks on the retracted requirement (where the correction retracted one) or on the requirements every
        # violator breaks, through the initial-only contract's mapping to the reference contract, under each mapper.
        counts = {}
        for kind, targets in (("superseded", sup), ("broken", broken)):
            if not targets:
                continue
            for mapper, mk in (("mapping_initial_only", ""), ("mapping2_initial_only", ".mapper2")):
                mp = json.loads((ROOT / "tasks" / t / "contracts" / f"{mapper}.json").read_text())["map"]
                k = sum(bool({x for rid in ch["requirement_ids"] for x in mp.get(rid, [])} & set(targets)) for ch in c1["checks"])
                counts[(kind, mk)] = k
                nums.put(f"c1.{fk}.checks.{kind}{mk}", k, f"{c1src} checks[].requirement_ids through tasks/{t}/contracts/"
                         f"{mapper}.json map, onto {', '.join(targets)}", f"C1 checks on the {kind} requirement(s)")
                if kind == "superseded" and not mk:  # which of them fail on the reference ("exactly those fail")
                    ref_failed = {ch["check_id"] for ch in by_row[(t, "initial_plain", f"{t}-reference")]["checks"]
                                  if ch["status"] != "passed"}
                    on = {ch["check_id"] for ch in c1["checks"] if {x for rid in ch["requirement_ids"] for x in mp.get(rid, [])}
                          & set(targets)}
                    nums.put(f"c1.{fk}.checks.superseded.failed", len(on & ref_failed), f"{c1src}; {mapper}.json map; {rsrc} "
                             f"row ({t}, initial_plain, {t}-reference) checks[].status", "of them, checks that fail on the reference")
                    nums.put(f"c1.{fk}.checks.other.failed", len(ref_failed - on), f"{c1src}; {mapper}.json map; {rsrc} row "
                             f"({t}, initial_plain, {t}-reference) checks[].status", "checks on other requirements that fail on it")
        kind = "superseded" if sup else "broken" if broken else None
        if kind:
            k1, k2 = counts[(kind, "")], counts[(kind, ".mapper2")]
            text = (f"{k1} of {n1}" + ("" if k1 == k2 else f" (mapper 2: {k2})") + (" on the retracted " if sup else " on ")
                    + ", ".join(sup if sup else broken))
        else:
            text = "--"
        cell(t, "C1 checks on the retracted or broken requirement", text,
             f"{c1src} checks[].requirement_ids; tasks/{t}/contracts/mapping_initial_only.json, mapping2_initial_only.json map")
        # The violators C1 rejects, and the requirements of its contract whose checks they fail.
        rej = [cid for cid in viol[t] if units[(t, cid)]["outcome"]["initial_plain"] != "pass"]
        if viol[t]:
            req_of = {ch["check_id"]: ch["requirement_ids"] for ch in c1["checks"]}
            how = f"{rsrc} rows ({t}, initial_plain, <violator>) checks[].status; {c1src} checks[].requirement_ids"
            nums.put(f"c1.{fk}.cv.rejected", len(rej), how, "correction violators C1 rejects")
            by_req: Counter = Counter()
            for cid in rej:
                bad = [ch["check_id"] for ch in by_row[(t, "initial_plain", cid)]["checks"] if ch["status"] != "passed"]
                by_req.update({rid for b in bad for rid in req_of.get(b, [])})
            for rid, n in sorted(by_req.items()):
                nums.put(f"c1.{fk}.cv.rejected.{_req_key(rid)}", n, how, f"rejected violators failing a check of C1's {rid}")
        for c in ("initial_plain", "full_plain"):
            cell(t, f"{SHORT[c]} accepts", nums.values[f"cv.{SHORT[c].lower()}.{fk}"] if viol[t] else "--",
                 f"\\fv{{cv.{SHORT[c].lower()}.{fk}}}")
        cell(t, "Base tests accept", nums.values[f"b1.base.fa.{fk}"], f"\\fv{{b1.base.fa.{fk}}}")
        cell(t, "Regression only", nums.values[f"unspec.{fk}.n"], f"\\fv{{unspec.{fk}.n}}")
        # The audit's revisions: the checks each audited verifier adds to its plain counterpart, and the false rejections
        # whose failing checks are all such added checks.
        for plain, aud in (("initial_plain", "initial_audited"), ("full_plain", "full_audited")):
            sp, ssp = _spec(t, plain)
            sa, ssa = _spec(t, aud)
            sh = SHORT[aud].lower()
            pid, aid = {ch["check_id"] for ch in sp["checks"]}, {ch["check_id"] for ch in sa["checks"]}
            added = aid - pid
            how = f"{ssa} checks[].check_id, audit; {ssp} checks[].check_id, content_sha256"
            nums.put(f"audit.{sh}.{fk}.added", len(added), how, "checks the audited verifier has and its plain one lacks")
            nums.put(f"audit.{sh}.{fk}.removed", len(pid - aid), how, "checks the plain verifier has and the audited one lacks")
            nums.put_count(f"audit.{sh}.{fk}.revisions", (sa.get("audit") or {}).get("iterations", 0), how, "audit revisions")
            nums.put(f"audit.{sh}.{fk}.passed", "passed" if (sa.get("audit") or {}).get("passed") else "not passed", how)
            nums.put(f"audit.{sh}.{fk}.identical", "identical" if sa["content_sha256"] == sp["content_sha256"] else "revised", how,
                     "the audited tests against the plain ones")
            fr_added = 0
            for (tt, cid), u in units.items():
                if tt != t or u["label"] != "valid" or u["outcome"][aud] == "pass":
                    continue
                bad = {ch["check_id"] for ch in by_row[(t, aud, cid)]["checks"] if ch["status"] != "passed"}
                fr_added += bool(bad) and bad <= added
            nums.put(f"{sh}.{fk}.fr.added", fr_added, f"{rsrc} rows ({t}, {aud}, <valid unit>) checks[].status; {how}",
                     "false rejections whose failing checks are all checks the audit's revision added")
    # The post hoc silent-loss reading of the secondary oracle-gated view (protocol §15.7): the violators in the families
    # whose reference the initial-only verifier C1 passes, and how many of them each condition accepts.
    kept = [t for t in fams if t not in og["initial_plain"]["dropped"]]
    silent = [t for t in kept if viol[t]]
    n_silent = sum(len(viol[t]) for t in silent)
    how = (f"{src} oracle_gated.conditions.initial_plain.dropped (the families C1 keeps: {', '.join(kept)}); per_task "
           "(negative_type, outcome) of their correction violators")
    nums.put("cv.silent.n", n_silent, how, "correction violators where C1 passes its reference")
    nums.put("cv.silent.families", ", ".join(tex(t) for t in silent) or "none", how)
    for c in ORDER:
        acc = sum(units[(t, cid)]["outcome"][c] == "pass" for t in silent for cid in viol[t])
        nums.put(f"cv.silent.{SHORT[c].lower()}", _frac(acc, n_silent), how, f"of them, accepted by {SHORT[c]}")
    columns = [col for col, _, _ in cells[fams[0]]]
    rag = NRTable.RAGGED
    rows = [f"{tex(t)} & " + " & ".join(rag + tex(text) for _, text, _ in cells[t]) + " \\tabularnewline" for t in fams]
    widths = (0.09, 0.2, 0.11, 0.12, 0.075, 0.075, 0.075, 0.09)  # with the family column and the separations, within the line
    # Ragged-right columns (array's \arraybackslash keeps \\ the row's end), so that no header or requirement id is
    # hyphenated in a narrow column; the body's cells carry their own \raggedright as well.
    spec = "l" + "".join(f">{{\\raggedright\\arraybackslash}}p{{{w}\\linewidth}}" for w in widths)
    # The header; the ledger names each column as written in the code.
    head = "Family & " + " & ".join(tex(col).replace("u1", "\\texttt{u1}") for col in columns)
    (out / "fresh_behaviours.tex").write_text(table(
        f"What the invalid first-request (\\texttt{{u1}}) attempts of run \\texttt{{{tex(F['run_id'])}}} did, by family, a post hoc "
        "reading under rule D19's labels: what the correction changed (the scenario files), which requirements the invalid "
        "attempts break (with counts), whether C1 passes the family's reference, how many of C1's checks map to the retracted "
        "requirement or to those every violator breaks (both model mappers), how many correction violators C1 and C3 accept "
        "(--: the family has none), how many invalid attempts the base-commit tests alone accept, and the invalid attempts "
        "whose only violated requirement is the regression norm (Regression only). " + marker(name), "tab:fresh-behaviours",
        spec, head, rows,
        size="\\scriptsize\\setlength{\\tabcolsep}{2pt}"))


def fresh_tables(F: dict, led: SectionLedger, nums: Numbers, out: Path) -> None:
    a, s, fams, run_id = F["a"], F["s"], F["fams"], F["run_id"]
    src, ssrc, rsrc = F["src"], F["ssrc"], F["rsrc"]
    run_tt = f"\\texttt{{{tex(run_id)}}}"
    excl = [x["candidate_id"] for x in a["fresh_attempts"]["excluded"]]
    excl_txt = ", ".join(f"\\texttt{{{tex(x)}}}" for x in excl) or "none"
    n_units, lab = a["distinct_patches"]["n_distinct"], a["independent_labeling"]["labels"]
    inv, val = a["conditions"]["initial_plain"]["false_acceptance"]["den"], a["conditions"]["initial_plain"]["false_rejection"]["den"]
    for k in ("invalid", "valid"):
        dens = {x["independent_label"]["false_acceptance" if k == "invalid" else "false_rejection"]["den"]
                for x in a["independent_labeling"]["conditions"].values()}
        if dens != {lab[k]}:
            raise ValueError(f"{src}: independent_labeling.labels.{k} = {lab[k]} but the labeler's denominators are {dens}")

    def marker(table_: str) -> str:
        return controlled_marker(a["n_families"], led, table_, src)

    # (a) per family, the primary display (rule D19's labels), split into FA and FR; the second labeler's view apart
    cells = _per_family_cells(F, a, src, led, nums, "fresh_per_family", "")
    man, rows_ = F["m"], F["rows"]
    unresolved = sum(r["outcome"] == "unresolved" for r in rows_)
    led.add("fresh_per_family", "caption: harness; repeats; graded pairs; unresolved; units; invalid; valid",
            f"{rows_[0]['harness_version']}; {man['repeats']}; {len(rows_)}; {unresolved}; {n_units}; {inv}; {val}",
            f"{rsrc} harness_version, outcome (rows); {F['msrc']} repeats; {src} distinct_patches.n_distinct, conditions.*.false_acceptance.den, "
            ".false_rejection.den")
    (out / "fresh_per_family.tex").write_text(fresh_split_table(
        F, cells, "rule", label="tab:fresh-family",
        caption=f"Per-family false acceptance and false rejection on the fresh-agent stratum, the primary display (protocol "
                f"\\S15.7), under rule D19's labels: {inv} invalid and {val} valid attempts, each distinct graded patch once "
                f"({n_units} graded patches; excluded by the reviewed audit: {excl_txt}). Run {run_tt} graded every pair "
                f"{man['repeats']} times under harness {tex(rows_[0]['harness_version'].split('/')[-1])} ({_int(len(rows_))} pairs, "
                f"{unresolved} unresolved). n/a: the family has no attempt of that kind. The second labeler's view: "
                f"Table~\\ref{{tab:fresh-family-labeler}}. " + marker("fresh_per_family")))
    (out / "fresh_per_family_labeler.tex").write_text(fresh_split_table(
        F, cells, "labeler", label="tab:fresh-family-labeler",
        caption=f"Per-family false acceptance and false rejection on the fresh-agent stratum, run {run_tt}, under the second "
                f"labeler: the independent labeler's verdicts (protocol \\S15.5; {lab['invalid']} invalid, {lab['valid']} valid "
                f"attempts), which never change D19's labels. The labeler has no regression part. n/a: the family has no attempt of "
                f"that kind under this labeling. Rule D19's view: Table~\\ref{{tab:fresh-family}}. " + marker("fresh_per_family_labeler")))

    # (a2) pooled rates
    rows = []
    for c in ORDER:
        d, sh = a["conditions"][c], SHORT[c].lower()
        cells = []
        for m, key in (("fa", "false_acceptance"), ("fr", "false_rejection")):
            x = d[key]
            cells += [fmt_rate(x["rate"], x["num"], x["den"]), _iv(x["exact95"]), _r2(x["macro"])]
            led.add("fresh_pooled", f"{c} {key} rate (num/den), exact95, macro",
                    f"{x['rate']} ({x['num']}/{x['den']}), {x['exact95']}, {x['macro']}", f"{src} conditions.{c}.{key}")
            nums.put(f"{sh}.{m}", _frac(x["num"], x["den"]), f"{src} conditions.{c}.{key}.num, .den")
            nums.put(f"{sh}.{m}.rate", _r2(x["rate"]), f"{src} conditions.{c}.{key}.rate")
            nums.put(f"{sh}.{m}.exact", _iv(x["exact95"]), f"{src} conditions.{c}.{key}.exact95")
            nums.put(f"{sh}.{m}.macro", _r2(x["macro"]), f"{src} conditions.{c}.{key}.macro")
        tn, infra = d["tasks_with_any_accepted_negative"], d["infrastructure"]
        rows.append(f"{cond_cell(c)} & " + " & ".join(cells) + f" & {_signed(d['youden_j'])} & {tn['num']}/{tn['den']} & "
                    f"{infra['num']}/{infra['den']} \\\\")
        led.add("fresh_pooled", f"{c} youden_j; families with an accepted negative; infrastructure",
                f"{d['youden_j']}; {tn['num']}/{tn['den']}; {infra['num']}/{infra['den']}",
                f"{src} conditions.{c}.youden_j, .tasks_with_any_accepted_negative, .infrastructure")
        nums.put(f"{sh}.j", _signed(d["youden_j"]), f"{src} conditions.{c}.youden_j")
        nums.put(f"{sh}.famfa", f"{tn['num']}/{tn['den']}", f"{src} conditions.{c}.tasks_with_any_accepted_negative.num, .den")
        nums.put(f"{sh}.infra", f"{infra['num']}/{infra['den']}", f"{src} conditions.{c}.infrastructure.num, .den")
    (out / "fresh_pooled.tex").write_text(table(
        f"Pooled rates on the fresh-agent stratum, run {run_tt}, rule D19's labels, each distinct graded patch once. Rate "
        "(num/den), the exact binomial 95\\% interval (it ignores clustering by family; reference scale only) and the macro rate "
        "(mean of the per-family rates). $J$ = (1$-$FR)$-$FA. Fam.\\ w/ FA: families with at least one accepted invalid attempt. "
        f"Infra: infrastructure outcomes. Cluster-bootstrap intervals are reported separately and are not inferential with "
        f"{a['n_families']} families. " + marker("fresh_pooled"), "tab:fresh-pooled", COND_P + "rrrrrrrrr",
        "Condition & FA & exact 95\\% & macro & FR & exact 95\\% & macro & $J$ & Fam.\\ w/ FA & Infra", rows,
        size="\\scriptsize\\setlength{\\tabcolsep}{3.5pt}"))

    # (a3) the paired comparisons planned in protocol §15.7: a compact table for the main text, the full one for the appendix
    rows, compact, floors1, floors2, ptwo = [], [], set(), set(), []
    for i, d in enumerate(a["comparisons"]):
        sp, fm = d["signflip"]["pooled"], d["signflip"]["family_mean"]
        floors1.add(sp["floor_one_sided"])
        floors2.add(sp["floor_two_sided"])
        ptwo.append(sp["p_two_sided"])
        disc = d["discordant"]
        pfd = [_signed(d["per_family_difference"].get(t)) for t in fams]
        rows.append(f"{SHORT[d['a']]} & {SHORT[d['b']]} & {d['metric'].upper()} ({d['n_metric']}) & {_signed(d['difference'])} & "
                    + " & ".join(pfd) + f" & {disc['a_accepts_b_rejects']}/{disc['a_rejects_b_accepts']} & {_p(sp['p_greater'])} & "
                    f"{_p(sp['p_less'])} & {_p(sp['p_two_sided'])} & {_p(fm['p_two_sided'])} & {_p(sp['conditional_floor_one_sided'])} \\\\")
        compact.append(f"{SHORT[d['a']]} & {SHORT[d['b']]} & {d['metric'].upper()} ({d['n_metric']}) & {_signed(d['difference'])} & "
                       f"{disc['a_accepts_b_rejects']}/{disc['a_rejects_b_accepts']} & {_p(sp['p_greater'])} & {_p(sp['p_two_sided'])} & "
                       f"{_p(sp['conditional_floor_one_sided'])} \\\\")
        led.add("fresh_comparisons", f"comparisons[{i}] {d['a']} - {d['b']} {d['metric']}: difference, n, per-family differences, "
                "discordant, pooled p_greater / p_less / p_two_sided / conditional floor, family-mean p_two_sided",
                f"{d['difference']}, {d['n_metric']}, {d['per_family_difference']}, {disc}, {sp['p_greater']} / {sp['p_less']} / "
                f"{sp['p_two_sided']} / {sp['conditional_floor_one_sided']}, {fm['p_two_sided']}",
                f"{src} comparisons[{i}] (difference, n_metric, per_family_difference, discordant, signflip.pooled, signflip.family_mean)")
        k = f"cmp.{SHORT[d['a']].lower()}-{SHORT[d['b']].lower()}.{d['metric']}"
        base = f"{src} comparisons[{i}]"
        nums.put(f"{k}.diff", _signed(d["difference"]), f"{base}.difference")
        nums.put(f"{k}.n", d["n_metric"], f"{base}.n_metric")
        nums.put(f"{k}.disc.ab", disc["a_accepts_b_rejects"], f"{base}.discordant.a_accepts_b_rejects", "A accepts, B rejects")
        nums.put(f"{k}.disc.ba", disc["a_rejects_b_accepts"], f"{base}.discordant.a_rejects_b_accepts", "A rejects, B accepts")
        nums.put(f"{k}.p.greater", _p(sp["p_greater"]), f"{base}.signflip.pooled.p_greater")
        nums.put(f"{k}.p.less", _p(sp["p_less"]), f"{base}.signflip.pooled.p_less")
        nums.put(f"{k}.p.two", _p(sp["p_two_sided"]), f"{base}.signflip.pooled.p_two_sided")
        nums.put(f"{k}.floor", _p(sp["conditional_floor_one_sided"]), f"{base}.signflip.pooled.conditional_floor_one_sided")
        nums.put(f"{k}.fm.p.two", _p(fm["p_two_sided"]), f"{base}.signflip.family_mean.p_two_sided")
        nums.put(f"{k}.fm.p.greater", _p(fm["p_greater"]), f"{base}.signflip.family_mean.p_greater")
        for t in fams:
            nums.put(f"{k}.{_fk(t)}", _signed(d["per_family_difference"].get(t)), f"{base}.per_family_difference.{t}")
    if len(floors1) != 1 or len(floors2) != 1:
        raise ValueError(f"{src}: the comparisons have different unconditional floors {floors1}, {floors2}; the caption states one")
    f1, f2 = floors1.pop(), floors2.pop()
    nums.put("cmp.count", len(a["comparisons"]), f"{src} comparisons (count)")
    nums.put("cmp.floor.one", _p(f1), f"{src} comparisons[*].signflip.pooled.floor_one_sided (one value)")
    nums.put("cmp.floor.two", _p(f2), f"{src} comparisons[*].signflip.pooled.floor_two_sided (one value)")
    nums.put("cmp.min.p.two", _p(min(ptwo)), f"{src} comparisons[*].signflip.pooled.p_two_sided (minimum)")
    led.add("fresh_comparisons", "unconditional floors one-sided / two-sided (caption); smallest two-sided p (caption)",
            f"{f1} / {f2}; {min(ptwo)}", f"{src} comparisons[*].signflip.pooled.floor_one_sided, .floor_two_sided, .p_two_sided")
    (out / "fresh_comparisons.tex").write_text(table(
        # At most 60 words before the marker (restructure plan, finding 20; tests/test_make_tables_fresh.py).
        f"The {len(a['comparisons'])} planned comparisons (protocol \\S15.7), run {run_tt}, rule D19's labels. A$-$B: pooled "
        "difference over invalid (FA) or valid (FR) attempts; Disc.: A accepts \\& B rejects / the reverse; exact sign-flip $p$ "
        f"over {a['n_families']} families ($p_{{>}}$: one-sided, A$>$B; 2-s.: two-sided), never below {_p(f1)} one-sided or "
        f"{_p(f2)} two-sided; Floor: the one-sided bound given families with zero difference. Full: "
        "Table~\\ref{tab:fresh-comparisons-full}. " + marker("fresh_comparisons"),
        "tab:fresh-comparisons", "lllrrrrr", "A & B & Metric (n) & A$-$B & Disc. & $p_{>}$ & $p$ 2-s. & Floor", compact,
        size="\\footnotesize"))
    (out / "fresh_comparisons_full.tex").write_text(table(
        f"The {len(a['comparisons'])} paired comparisons planned before grading (protocol \\S15.7) on the same attempts, run "
        f"{run_tt}, rule D19's labels, in full. "
        "Metric (n): FA over the invalid or FR over the valid attempts. A$-$B: pooled difference; then the per-family differences. "
        "Disc.: A accepts \\& B rejects / A rejects \\& B accepts. $p$: exact sign-flip randomization p-values over the "
        f"{a['n_families']} families, on the pooled statistic ($>$: A$>$B, $<$: A$<$B, both one-sided; 2-s.: two-sided) and, "
        f"last but one, two-sided on the family-mean statistic. With {a['n_families']} families no one-sided $p$ below {_p(f1)} "
        f"and no two-sided $p$ below {_p(f2)} can occur; Floor: the smallest one-sided $p$ attainable given the families whose "
        f"difference is zero. The smallest two-sided $p$ here is {_p(min(ptwo))}. Short names: C1, C2 initial-only and C3, C4 "
        "correction-aware contracts (plain or audited), B2 the session-LLM baseline, B1 repository tests. "
        + marker("fresh_comparisons_full"), "tab:fresh-comparisons-full",
        "lllr" + "r" * len(fams) + "rrrrrr",
        "A & B & Metric (n) & A$-$B & " + " & ".join(tex(t) for t in fams) + " & Disc. & $p_{>}$ & $p_{<}$ & $p$ 2-s. & "
        "$p$ 2-s.\\ (mean) & Floor", rows, size="\\scriptsize\\setlength{\\tabcolsep}{4pt}"))

    # (b) correction-violating u1 attempts
    units = _units(a, fams)
    att = F["attempt"]
    u1 = {t: [x for x in F["att"][t]["attempts"] if x["variant"] == "u1" and x["audit_passed"]] for t in fams}
    cv_rec = a["fresh_attempts"]["u1_correction_violating"]
    if sum(len(v) for v in u1.values()) != cv_rec["attempts"]:
        raise ValueError(f"{src}: fresh_attempts.u1_correction_violating.attempts = {cv_rec['attempts']}, the attempt records hold "
                         f"{sum(len(v) for v in u1.values())} u1 attempts that passed the audit")
    viol = {t: sorted(cid for (tt, cid), u in units.items() if tt == t and u["negative_type"] == "correction_violating") for t in fams}
    for t in fams:
        for cid in viol[t]:
            if att[cid]["variant"] != "u1":
                raise ValueError(f"{cid}: a correction-violating unit that is not a u1 attempt")
    if sum(len(v) for v in viol.values()) != cv_rec["correction_violating"]:
        raise ValueError(f"{src}: per_task holds {sum(len(v) for v in viol.values())} correction-violating units, "
                         f"fresh_attempts.u1_correction_violating.correction_violating = {cv_rec['correction_violating']}")
    unspec = sorted(cid for (t, cid), u in units.items() if u["label"] == "invalid" and u["negative_type"] != "correction_violating")
    violated = {x["candidate"]: x["violated"] for t in fams for x in a["labels"][t]["strata"][F["stratum"]]["candidates"]}
    for cid in unspec:
        if violated.get(cid) != ["REGRESSION"]:
            raise ValueError(f"{src}: {cid} is invalid without a correction requirement, but labels...violated = {violated.get(cid)}; "
                             "the table calls these units regression-only")
    nt = {u["negative_type"] for u in units.values() if u["label"] == "invalid" and u["negative_type"] != "correction_violating"}
    first = ["Correction-violating \\texttt{u1} attempts"]
    for t in fams:
        first.append(f"{len(viol[t])}/{len(u1[t])}")
        led.add("fresh_correction_violating", f"{t} correction-violating u1 attempts / u1 attempts", f"{len(viol[t])}/{len(u1[t])}",
                f"{src} per_task.{t}.*[].negative_type = correction_violating; {F['att_src'][t]} attempts[].variant = u1, audit_passed")
        nums.put(f"cv.{_fk(t)}", f"{len(viol[t])}/{len(u1[t])}", f"{src} per_task.{t}.*[].negative_type; {F['att_src'][t]} attempts[].variant")
        nums.put(f"cv.{_fk(t)}.n", len(viol[t]), f"{src} per_task.{t}.*[].negative_type = correction_violating (count)")
    first.append(f"{cv_rec['correction_violating']}/{cv_rec['attempts']}")
    first.append(str(len(unspec)))
    led.add("fresh_correction_violating", "pooled correction-violating u1 attempts / u1 attempts; share",
            f"{cv_rec['correction_violating']}/{cv_rec['attempts']}; {cv_rec['share']}",
            f"{src} fresh_attempts.u1_correction_violating.correction_violating, .attempts, .share")
    led.add("fresh_correction_violating", f"invalid units without a violated correction requirement (negative types {sorted(nt)}): "
            "count; their violated requirements", f"{len(unspec)}: {', '.join(unspec)}; {['REGRESSION']}",
            f"{src} per_task.*.*[].label, .negative_type; labels.<task>.strata.{F['stratum']}.candidates[].violated")
    nums.put("cv", f"{cv_rec['correction_violating']}/{cv_rec['attempts']}",
             f"{src} fresh_attempts.u1_correction_violating.correction_violating, .attempts")
    nums.put("cv.n", cv_rec["correction_violating"], f"{src} fresh_attempts.u1_correction_violating.correction_violating")
    nums.put("cv.attempts", cv_rec["attempts"], f"{src} fresh_attempts.u1_correction_violating.attempts")
    nums.put("cv.share", f"{cv_rec['share']:.3f}", f"{src} fresh_attempts.u1_correction_violating.share")
    nums.put("unspec.n", len(unspec), f"{src} per_task.*.*[] (invalid, negative_type not correction_violating; count)",
             "invalid units with REGRESSION as their only violated requirement")
    rows = [" & ".join(first) + " \\\\\\midrule"]
    for c in ORDER:
        sh, cells = SHORT[c].lower(), [tex(COND_TEX[c])]
        for t in fams:
            acc = sum(units[(t, cid)]["outcome"][c] == "pass" for cid in viol[t])
            cells.append(f"{acc}/{len(viol[t])}" if viol[t] else "--")
            nums.put(f"cv.{sh}.{_fk(t)}", _frac(acc, len(viol[t])), f"{src} per_task.{t}.{c}[] (correction_violating; outcome pass / all)")
        bn = a["by_negative_type"][c]
        cvb, usb = bn["correction_violating"], bn.get("unspecified", {"accepted": 0, "n": 0})
        tot = sum(sum(units[(t, cid)]["outcome"][c] == "pass" for cid in viol[t]) for t in fams)
        if (tot, sum(len(v) for v in viol.values())) != (cvb["accepted"], cvb["n"]):
            raise ValueError(f"{src}: by_negative_type.{c}.correction_violating = {cvb}, per_task gives {tot} accepted")
        if usb["n"] != len(unspec):
            raise ValueError(f"{src}: by_negative_type.{c}.unspecified.n = {usb['n']}, per_task gives {len(unspec)}")
        cells += [f"{cvb['accepted']}/{cvb['n']}", f"{usb['accepted']}/{usb['n']}"]
        rows.append(" & ".join(cells) + " \\\\")
        led.add("fresh_correction_violating", f"{c} accepted correction-violating per family; pooled; accepted regression-only",
                ", ".join(c2 for c2 in cells[1:len(fams) + 1]) + f"; {cvb['accepted']}/{cvb['n']}; {usb['accepted']}/{usb['n']}",
                f"{src} per_task.<task>.{c}[] (negative_type, outcome); by_negative_type.{c}.correction_violating, .unspecified")
        nums.put(f"cv.{sh}", f"{cvb['accepted']}/{cvb['n']}", f"{src} by_negative_type.{c}.correction_violating.accepted, .n")
        nums.put(f"cv.{sh}.accepted", cvb["accepted"], f"{src} by_negative_type.{c}.correction_violating.accepted")
        nums.put(f"unspec.{sh}", f"{usb['accepted']}/{usb['n']}", f"{src} by_negative_type.{c}.unspecified.accepted, .n")
    (out / "fresh_correction_violating.tex").write_text(table(
        f"\\texttt{{u1}} attempts (given the first user request only) that violate a requirement the reference contract introduces "
        f"after it, by family, and how many of them each condition accepts (accepted/violating), run {run_tt}, rule D19's labels. "
        "Last column: the invalid attempts whose only violated requirement is the regression norm (accepted/total); they violate "
        "no correction requirement. " + marker("fresh_correction_violating"), "tab:fresh-cv", "l" + "r" * (len(fams) + 2),
        " & " + " & ".join(tex(t) for t in fams) + " & Pooled & Regression only", rows, size="\\footnotesize"))

    # (c) solve rates by configuration and variant
    rows = []
    bcv = a["fresh_attempts"]["by_configuration_variant"]
    for key in sorted(bcv):
        d = bcv[key]
        cfg, var = d["configuration"].replace("config-", ""), d["variant"]
        recs = [x for t in fams for x in F["att"][t]["attempts"] if x["configuration"] == d["configuration"] and x["variant"] == var
                and x["audit_passed"]]
        if len(recs) != d["attempts"]:
            raise ValueError(f"{src}: fresh_attempts.by_configuration_variant.{key}.attempts = {d['attempts']}, the attempt records "
                             f"hold {len(recs)}")
        ended = [d["ended"].get(k, 0) for k in ("finished", "gave_up", "error")]
        if sum(ended) != d["attempts"]:
            raise ValueError(f"{src}: fresh_attempts.by_configuration_variant.{key}.ended has a value other than finished, gave_up, error")
        dl = d["independent_label"]
        rows.append(f"{cfg} & \\texttt{{{tex(var)}}} & {RULE_ROW} & {d['solved']}/{d['attempts']} & " +
                    " & ".join(f"{d['per_family'][t]['solved']}/{d['per_family'][t]['attempts']}" for t in fams) +
                    f" & {'/'.join(map(str, ended))} \\\\")
        rows.append(f" & & {LABELER_ROW} & " + f"{dl['solved']}/{d['attempts']} & " +
                    " & ".join(f"{dl['per_family'][t]['solved']}/{dl['per_family'][t]['attempts']}" for t in fams) + " & \\\\" +
                    ("" if key == sorted(bcv)[-1] else "\\addlinespace"))
        base = f"{src} fresh_attempts.by_configuration_variant.{key}"
        led.add("fresh_solve_rates", f"{key} D19 solved/attempts; per family; ended finished/gave_up/error",
                f"{d['solved']}/{d['attempts']}; {[(t, d['per_family'][t]['solved'], d['per_family'][t]['attempts']) for t in fams]}; "
                f"{'/'.join(map(str, ended))}", f"{base} (solved, attempts, per_family, ended; an absent key of ended is 0)")
        led.add("fresh_solve_rates", f"{key} labeler solved/attempts; per family",
                f"{dl['solved']}/{d['attempts']}; {[(t, dl['per_family'][t]['solved'], dl['per_family'][t]['attempts']) for t in fams]}",
                f"{base}.independent_label (solved, per_family)")
        k = f"solve.{cfg.lower()}.{var}"
        nums.put(k, f"{d['solved']}/{d['attempts']}", f"{base}.solved, .attempts")
        nums.put(f"{k}.rate", _r2(d["rate"]), f"{base}.rate")
        nums.put(f"il.{k}", f"{dl['solved']}/{d['attempts']}", f"{base}.independent_label.solved; {base}.attempts")
        nums.put(f"{k}.finished", d["ended"].get("finished", 0), f"{base}.ended.finished")
        for t in fams:
            nums.put(f"{k}.{_fk(t)}", f"{d['per_family'][t]['solved']}/{d['per_family'][t]['attempts']}",
                     f"{base}.per_family.{t}.solved, .attempts")
    for var in sorted({d["variant"] for d in bcv.values()}):
        for t in fams:
            sv = sum(d["per_family"][t]["solved"] for d in bcv.values() if d["variant"] == var)
            n = sum(d["per_family"][t]["attempts"] for d in bcv.values() if d["variant"] == var)
            nums.put(f"solve.{var}.{_fk(t)}", f"{sv}/{n}", f"{src} fresh_attempts.by_configuration_variant.*/{var}.per_family.{t} "
                     "(summed over the configurations)")
    (out / "fresh_solve_rates.tex").write_text(table(
        f"Solve rates of the fresh attempts (protocol \\S15.4, estimand 1), run {run_tt}: solved/attempts per configuration "
        "(configurations A and B use different models of one model family of one provider, with the same template, tools and "
        "budget) and instruction (\\texttt{u1}: the first user request only; \\texttt{final}: with the correction added), pooled "
        f"and per family. {RULE_ROW}: solved when D19 labels the attempt valid (reference checks and regression norm); "
        f"{LABELER_ROW}: when the independent labeler passes it. Every analysed attempt counts; the excluded one ({excl_txt}) counts "
        "nowhere. Ended: finished/gave up/error. The \\texttt{u1}--\\texttt{final} contrast measures the information in the "
        "instruction, not the agents' capability. " + marker("fresh_solve_rates"),
        "tab:fresh-solve", "lll" + "r" * (len(fams) + 2),
        "Config. & Instruction & Labels & Solved & " + " & ".join(tex(t) for t in fams) + " & Ended", rows, size="\\footnotesize"))

    # (d) the sensitivity view (every flagged attempt excluded)
    sm = s["meta"]["sensitivity"]
    here, already = len(sm["excluded_here"]), len(sm["already_excluded"])
    s_units, s_lab = s["distinct_patches"]["n_distinct"], s["independent_labeling"]["labels"]
    s_inv, s_val = s["conditions"]["initial_plain"]["false_acceptance"]["den"], s["conditions"]["initial_plain"]["false_rejection"]["den"]
    s_cv, s_ag = s["fresh_attempts"]["u1_correction_violating"], s["independent_labeling"]["agreement"]["by_stratum"][F["stratum"]]
    g = s_cv["graded_by"]
    nums.put("sens.excluded.here", here, f"{ssrc} meta.sensitivity.excluded_here (count)", "excluded beyond the primary analysis")
    nums.put("sens.excluded.already", already, f"{ssrc} meta.sensitivity.already_excluded (count)")
    nums.put("sens.excluded", here + already, f"{ssrc} meta.sensitivity.excluded_here, already_excluded (counts summed)")
    nums.put("sens.units", s_units, f"{ssrc} distinct_patches.n_distinct")
    nums.put("sens.units.invalid", s_inv, f"{ssrc} conditions.initial_plain.false_acceptance.den")
    nums.put("sens.units.valid", s_val, f"{ssrc} conditions.initial_plain.false_rejection.den")
    nums.put("sens.cv", f"{s_cv['correction_violating']}/{s_cv['attempts']}", f"{ssrc} fresh_attempts.u1_correction_violating.correction_violating, .attempts")
    for c in ("initial_plain", "full_plain"):
        nums.put(f"sens.cv.{SHORT[c].lower()}", f"{g[c]['accepted']}/{g[c]['n']}", f"{ssrc} fresh_attempts.u1_correction_violating.graded_by.{c}")
    nums.put("sens.agree", f"{s_ag['agree']}/{s_ag['n_units']}", f"{ssrc} independent_labeling.agreement.by_stratum.{F['stratum']}.agree, .n_units")
    nums.put("sens.kappa", _r2(s_ag["kappa"]), f"{ssrc} independent_labeling.agreement.by_stratum.{F['stratum']}.kappa")
    for c in ORDER:
        sh, d = SHORT[c].lower(), s["conditions"][c]
        for m, key in (("fa", "false_acceptance"), ("fr", "false_rejection")):
            nums.put(f"sens.{sh}.{m}", _frac(d[key]["num"], d[key]["den"]), f"{ssrc} conditions.{c}.{key}.num, .den")
            nums.put(f"sens.{sh}.{m}.rate", _r2(d[key]["rate"]), f"{ssrc} conditions.{c}.{key}.rate")
        nums.put(f"sens.{sh}.j", _signed(d["youden_j"]), f"{ssrc} conditions.{c}.youden_j")
    led.add("fresh_sensitivity", "caption: excluded here / already; units (invalid, valid); labeler invalid / valid; correction-violating "
            "u1 attempts; C1, C3 accept; agreement; kappa",
            f"{here} / {already}; {s_units} ({s_inv}, {s_val}); {s_lab['invalid']} / {s_lab['valid']}; "
            f"{s_cv['correction_violating']}/{s_cv['attempts']}; {g['initial_plain']['accepted']}/{g['initial_plain']['n']}, "
            f"{g['full_plain']['accepted']}/{g['full_plain']['n']}; {s_ag['agree']}/{s_ag['n_units']}; {s_ag['kappa']}",
            f"{ssrc} meta.sensitivity; distinct_patches.n_distinct; conditions.initial_plain (dens); independent_labeling.labels; "
            "fresh_attempts.u1_correction_violating; independent_labeling.agreement.by_stratum")
    (out / "fresh_sensitivity.tex").write_text(fresh_per_family_table(
        F, s, ssrc, led, nums, name="fresh_sensitivity", label="tab:fresh-sensitivity", p="sens.",
        caption=f"Sensitivity view of run {run_tt} (protocol \\S18.1): every attempt the automated audit flagged is excluded "
                f"({here} beyond the primary analysis, plus the {already} excluded there), leaving {s_units} graded patches (D19: {s_inv} "
                f"invalid, {s_val} valid; labeler: {s_lab['invalid']} invalid, {s_lab['valid']} valid). Cells as in the per-family "
                f"table: accepted/invalid $\\cdot$ rejected/valid. Correction-violating \\texttt{{u1}} attempts: "
                f"{s_cv['correction_violating']}/{s_cv['attempts']}; C1 accepts {g['initial_plain']['accepted']}/{g['initial_plain']['n']}, "
                f"C3 {g['full_plain']['accepted']}/{g['full_plain']['n']}. D19 and the labeler agree on {s_ag['agree']}/{s_ag['n_units']} "
                f"graded patches ($\\kappa$ = {_r2(s_ag['kappa'])}, model--model agreement). " + marker("fresh_sensitivity")))

    # (d2) the oracle-gated view (secondary)
    og = a["oracle_gated"]
    rows = []
    for c in ORDER:
        d, sh, ref = og["conditions"][c], SHORT[c].lower(), a["sanity"][c]["reference"]
        dropped = ", ".join(tex(t) for t in sorted(d["dropped"])) or "--"
        rows.append(f"{tex(COND_TEX[c])} & {ref['pass']}/{ref['n']} & {d['cells_kept']}/{d['cells']} & {dropped} & "
                    f"{d['lost_yield']['invalid']}/{d['lost_yield']['valid']} & {fmt_rate(d['false_acceptance']['rate'], d['false_acceptance']['num'], d['false_acceptance']['den'])} & "
                    f"{fmt_rate(d['false_rejection']['rate'], d['false_rejection']['num'], d['false_rejection']['den'])} \\\\")
        led.add("fresh_oracle_gated", f"{c} reference passes; cells kept; dropped; lost yield invalid/valid; FA; FR",
                f"{ref['pass']}/{ref['n']}; {d['cells_kept']}/{d['cells']}; {sorted(d['dropped'])}; {d['lost_yield']['invalid']}/"
                f"{d['lost_yield']['valid']}; {d['false_acceptance']['num']}/{d['false_acceptance']['den']}; "
                f"{d['false_rejection']['num']}/{d['false_rejection']['den']}",
                f"{src} sanity.{c}.reference; oracle_gated.conditions.{c} (cells_kept, cells, dropped, lost_yield, false_acceptance, false_rejection)")
        nums.put(f"ref.{sh}", f"{ref['pass']}/{ref['n']}", f"{src} sanity.{c}.reference.pass, .n", "reference solutions passed")
        nums.put(f"og.{sh}.fa", _frac(d["false_acceptance"]["num"], d["false_acceptance"]["den"]), f"{src} oracle_gated.conditions.{c}.false_acceptance.num, .den")
        nums.put(f"og.{sh}.fr", _frac(d["false_rejection"]["num"], d["false_rejection"]["den"]), f"{src} oracle_gated.conditions.{c}.false_rejection.num, .den")
        nums.put(f"og.{sh}.fa.rate", _r2(d["false_acceptance"]["rate"]), f"{src} oracle_gated.conditions.{c}.false_acceptance.rate")
        nums.put(f"og.{sh}.fr.rate", _r2(d["false_rejection"]["rate"]), f"{src} oracle_gated.conditions.{c}.false_rejection.rate")
        nums.put(f"og.{sh}.lost.invalid", d["lost_yield"]["invalid"], f"{src} oracle_gated.conditions.{c}.lost_yield.invalid")
        nums.put(f"og.{sh}.lost.valid", d["lost_yield"]["valid"], f"{src} oracle_gated.conditions.{c}.lost_yield.valid")
        nums.put(f"og.{sh}.kept", f"{d['cells_kept']}/{d['cells']}", f"{src} oracle_gated.conditions.{c}.cells_kept, .cells")
    gl = []
    for i, d in enumerate(og["comparisons"]):
        if (d["a"], d["b"]) != ("initial_plain", "full_plain"):
            continue
        sp, k = d["signflip"]["pooled"], f"og.cmp.c1-c3.{d['metric']}"
        gl.append(f"{d['metric'].upper()} {_signed(d['difference'])} (disc.\\ {d['discordant']['a_accepts_b_rejects']}/"
                  f"{d['discordant']['a_rejects_b_accepts']}, $p_{{>}}$ = {_p(sp['p_greater'])}, floor {_p(sp['conditional_floor_one_sided'])}, "
                  f"{sp['k']} families)")
        led.add("fresh_oracle_gated", f"gated comparisons[{i}] C1 - C3 {d['metric']}: difference; discordant; p_greater; conditional floor; k",
                f"{d['difference']}; {d['discordant']}; {sp['p_greater']}; {sp['conditional_floor_one_sided']}; {sp['k']}",
                f"{src} oracle_gated.comparisons[{i}]")
        nums.put(f"{k}.diff", _signed(d["difference"]), f"{src} oracle_gated.comparisons[{i}].difference")
        nums.put(f"{k}.p.greater", _p(sp["p_greater"]), f"{src} oracle_gated.comparisons[{i}].signflip.pooled.p_greater")
        nums.put(f"{k}.floor", _p(sp["conditional_floor_one_sided"]), f"{src} oracle_gated.comparisons[{i}].signflip.pooled.conditional_floor_one_sided")
        nums.put(f"{k}.k", sp["k"], f"{src} oracle_gated.comparisons[{i}].signflip.pooled.k", "families kept")
    (out / "fresh_oracle_gated.tex").write_text(table(
        f"Oracle-gated view of run {run_tt} (secondary, protocol \\S15.7): a verifier's cell of a family is dropped when the "
        "verifier does not pass that family's reference solution, and the dropped cell's attempts are the lost yield (invalid/valid). "
        "Rule D19's labels. Gated C1$-$C3: " + "; ".join(gl) + ". " + marker("fresh_oracle_gated"), "tab:fresh-oracle", "lrrlrll",
        "Condition & Ref.\\ passes & Cells kept & Dropped & Lost yield & FA & FR", rows, size="\\footnotesize"))

    # (g) B1 split by the origin of its checks
    up_ids = {t: set(F["up"][t]["upstream_check_ids"]) for t in fams}
    for t in fams:
        u = F["up"][t]
        if len(up_ids[t]) != u["n_upstream"] or u["n_upstream"] + u["n_added_in_reference"] != u["n_b1_checks"]:
            raise ValueError(f"{F['up_src'][t]}: n_upstream, n_added_in_reference and n_b1_checks do not add up")
        if a["b1_upstream_only"]["n_checks"][t] != u["n_upstream"]:
            raise ValueError(f"{src}: b1_upstream_only.n_checks.{t} differs from {F['up_src'][t]} n_upstream")
    b1rows = {(r["task_id"], r["candidate_id"]): r for r in F["rows"] if r["verifier_id"] == "repo_tests"}

    def b1_split(view: dict, vsrc: str) -> dict:
        us = _units(view, fams)
        res = {t: {"fa_all": [0, 0], "fa_up": [0, 0], "fr_all": [0, 0], "fr_up": [0, 0], "fr_added": 0, "fr_upcheck": 0,
                   "fr_nocheck": 0, "u1_up_rej": [0, 0]} for t in fams}
        for (t, cid), u in us.items():
            r = b1rows[(t, cid)]
            if r["outcome"] != u["outcome"]["repo_tests"]:
                raise ValueError(f"{rsrc}: {cid} repo_tests outcome {r['outcome']} differs from {vsrc} per_task")
            bad = [ch["check_id"] for ch in r["checks"] if ch["status"] != "passed"]
            up_ok = not any(x in up_ids[t] for x in bad)  # the rule of analysis.py's b1_upstream_only
            acc = r["outcome"] == "pass"
            d = res[t]
            if u["label"] == "invalid":
                d["fa_all"][0] += acc
                d["fa_all"][1] += 1
                d["fa_up"][0] += up_ok
                d["fa_up"][1] += 1
            elif u["label"] == "valid":
                d["fr_all"][0] += not acc
                d["fr_all"][1] += 1
                d["fr_up"][0] += not up_ok
                d["fr_up"][1] += 1
                if not acc:
                    if any(x not in up_ids[t] for x in bad):
                        d["fr_added"] += 1
                    if any(x in up_ids[t] for x in bad):
                        d["fr_upcheck"] += 1
                    if not bad:
                        d["fr_nocheck"] += 1
            if F["attempt"][cid]["variant"] == "u1":
                d["u1_up_rej"][0] += not up_ok
                d["u1_up_rej"][1] += 1
        rec = view["b1_upstream_only"]
        tot = lambda k, i: sum(res[t][k][i] for t in fams)  # noqa: E731
        if (tot("fa_up", 0), tot("fa_up", 1), tot("fr_up", 0), tot("fr_up", 1)) != (rec["fa_num"], rec["fa_den"], rec["fr_num"], rec["fr_den"]):
            raise ValueError(f"the B1 split recomputed from {rsrc} does not reproduce {vsrc} b1_upstream_only")
        cfa, cfr = view["conditions"]["repo_tests"]["false_acceptance"], view["conditions"]["repo_tests"]["false_rejection"]
        if (tot("fa_all", 0), tot("fa_all", 1), tot("fr_all", 0), tot("fr_all", 1)) != (cfa["num"], cfa["den"], cfr["num"], cfr["den"]):
            raise ValueError(f"the B1 rates recomputed from {rsrc} do not reproduce {vsrc} conditions.repo_tests")
        return res

    res = b1_split(a, src)
    b1_split(s, ssrc)  # the sensitivity view must reproduce its own b1_upstream_only too
    rec, srec = a["b1_upstream_only"], s["b1_upstream_only"]
    tot = lambda r, k, i: sum(r[t][k][i] for t in fams)  # noqa: E731
    lines = []

    def line(text: str, cells: list[str], pooled: str, what: str, how: str, key: str | None = None) -> None:
        lines.append(f"{text} & " + " & ".join(cells) + f" & {pooled} \\\\")
        led.add("fresh_b1_split", what, ", ".join(cells) + f"; pooled {pooled}", how)
        if key:
            for t, cv in zip(fams, cells):
                nums.put(f"{key}.{_fk(t)}", cv, how)
            nums.put(key, pooled, how)

    n_all = [F["up"][t]["n_b1_checks"] for t in fams]
    n_up = [F["up"][t]["n_upstream"] for t in fams]
    n_add = [F["up"][t]["n_added_in_reference"] for t in fams]
    usrc = "tasks/<task>/verifiers/repo_tests/upstream_check_ids.json"
    line("B1 checks", [_int(x) for x in n_all], _int(sum(n_all)), "B1 checks per family", f"{usrc} n_b1_checks", "b1.checks")
    line("\\quad from the base commit's tests", [_int(x) for x in n_up], _int(sum(n_up)), "base-commit checks per family",
         f"{usrc} n_upstream (= {src} b1_upstream_only.n_checks)", "b1.checks.base")
    line("\\quad added by the session agent", [_int(x) for x in n_add], _int(sum(n_add)), "agent-added checks per family",
         f"{usrc} n_added_in_reference", "b1.checks.added")
    lines[-1] += "\\midrule"
    how_rj = (f"computed from {rsrc} (repo_tests rows: outcome; checks[].check_id, .status != passed) joined with {src} per_task "
              f"labels and {usrc} upstream_check_ids")
    line("FA, all checks", [_frac(*res[t]["fa_all"]) for t in fams], _frac(tot(res, "fa_all", 0), tot(res, "fa_all", 1)),
         "B1 FA (all checks) per family", how_rj, "b1.all.fa")
    line("FA, base-commit checks only", [_frac(*res[t]["fa_up"]) for t in fams], _frac(rec["fa_num"], rec["fa_den"]),
         "B1 FA (base-commit checks only) per family; pooled", how_rj + f"; pooled = {src} b1_upstream_only.fa_num, .fa_den", "b1.base.fa")
    line("FR, all checks", [_frac(*res[t]["fr_all"]) for t in fams], _frac(tot(res, "fr_all", 0), tot(res, "fr_all", 1)),
         "B1 FR (all checks) per family", how_rj, "b1.all.fr")
    line("FR, base-commit checks only", [_frac(*res[t]["fr_up"]) for t in fams], _frac(rec["fr_num"], rec["fr_den"]),
         "B1 FR (base-commit checks only) per family; pooled", how_rj + f"; pooled = {src} b1_upstream_only.fr_num, .fr_den", "b1.base.fr")
    lines[-1] += "\\midrule"
    line("False rejections failing an agent-added check", [str(res[t]["fr_added"]) for t in fams], str(sum(res[t]["fr_added"] for t in fams)),
         "B1 false rejections with a failing agent-added check", how_rj, "b1.fr.added")
    line("False rejections failing a base-commit check", [str(res[t]["fr_upcheck"]) for t in fams], str(sum(res[t]["fr_upcheck"] for t in fams)),
         "B1 false rejections with a failing base-commit check", how_rj, "b1.fr.base")
    line("\\texttt{u1} attempts rejected by base-commit checks", [_frac(*res[t]["u1_up_rej"]) for t in fams],
         _frac(tot(res, "u1_up_rej", 0), tot(res, "u1_up_rej", 1)), "u1 attempts rejected by the base-commit checks alone",
         how_rj + "; variant from " + ", ".join(F["att_src"][t] for t in fams) + " attempts[].variant", "b1.u1.base.rejected")
    nocheck = sum(res[t]["fr_nocheck"] for t in fams)
    led.add("fresh_b1_split", "B1 false rejections with no failing check recorded (must be 0 for the origin rows to be complete)", nocheck, how_rj)
    if nocheck:
        raise ValueError(f"{rsrc}: {nocheck} B1 false rejections record no failing check; the origin rows would be incomplete")
    led.add("fresh_b1_split", "sensitivity view: B1 FA; FR (base-commit checks only), pooled",
            f"{srec['fa_num']}/{srec['fa_den']}; {srec['fr_num']}/{srec['fr_den']}", f"{ssrc} b1_upstream_only")
    nums.put("sens.b1.base.fa", _frac(srec["fa_num"], srec["fa_den"]), f"{ssrc} b1_upstream_only.fa_num, .fa_den")
    nums.put("sens.b1.base.fr", _frac(srec["fr_num"], srec["fr_den"]), f"{ssrc} b1_upstream_only.fr_num, .fr_den")
    nums.put("b1.base.fa.rate", _r2(rec["fa"]), f"{src} b1_upstream_only.fa")
    (out / "fresh_b1_split.tex").write_text(table(
        f"Repository tests (B1) split by the origin of their checks, run {run_tt}, rule D19's labels. The B1 suite is the "
        "reference state's tests; ``base-commit checks'' exist in the base commit's own tests, the others were added by the session "
        "agent. ``Base-commit checks only'' scores an attempt on those checks alone (post hoc, as in the pilot). Under D19 the "
        "base commit's tests are the regression norm, so that view cannot reject a valid attempt (by construction). Origin rows: "
        "valid attempts that B1 rejects and that fail "
        f"at least one check of that origin. Sensitivity view (every flagged attempt excluded): FA {srec['fa_num']}/{srec['fa_den']}, "
        f"FR {srec['fr_num']}/{srec['fr_den']} on base-commit checks only. " + marker("fresh_b1_split"), "tab:fresh-b1", "l" + "r" * (len(fams) + 1),
        " & " + " & ".join(tex(t) for t in fams) + " & Pooled", lines, size="\\footnotesize"))

    # (h) attempt cost and time
    rows = []
    budget_max = max(x["wall_s"] for t in fams for x in F["att"][t]["attempts"])
    for key in sorted(bcv):
        d = bcv[key]
        cfg, var = d["configuration"], d["variant"]
        xs = [x for t in fams for x in F["att"][t]["attempts"] if x["configuration"] == cfg and x["variant"] == var and x["audit_passed"]]
        w = [x["wall_s"] for x in xs]
        med = lambda k: statistics.median(x[k] for x in xs)  # noqa: E731
        cells = [str(len(xs)), f"{statistics.median(w):.0f}", f"{min(w):.0f}--{max(w):.0f}", f"{med('turns'):g}", f"{med('tool_calls'):g}",
                 f"{med('tokens') / 1e6:.2f}"]
        rows.append(f"{cfg.replace('config-', '')} & \\texttt{{{tex(var)}}} & " + " & ".join(cells) + " \\\\")
        how = (", ".join(F["att_src"][t] for t in fams) + f" attempts[] with configuration {cfg}, variant {var}, audit_passed true: "
               "count; median, min, max of wall_s; median of turns, tool_calls, tokens")
        led.add("fresh_attempt_costs", f"{cfg}/{var} n; wall_s median, min, max; turns, tool_calls, tokens median",
                f"{len(xs)}; {statistics.median(w)}, {min(w)}, {max(w)}; {med('turns')}, {med('tool_calls')}, {med('tokens')}", how)
        k = f"cost.{cfg.replace('config-', '').lower()}.{var}"
        nums.put(f"{k}.n", len(xs), how)
        nums.put(f"{k}.wall", f"{statistics.median(w):.0f}", how, "median wall time, s")
        nums.put(f"{k}.wall.min", f"{min(w):.0f}", how)
        nums.put(f"{k}.wall.max", f"{max(w):.0f}", how)
        nums.put(f"{k}.turns", f"{med('turns'):g}", how)
        nums.put(f"{k}.tools", f"{med('tool_calls'):g}", how)
        nums.put(f"{k}.tokens", f"{med('tokens') / 1e6:.2f}", how, "median tokens, millions")
    all_src = ", ".join(F["att_src"][t] for t in fams) + " attempts[].wall_s (maximum over every attempt)"
    nums.put("cost.wall.max", f"{budget_max:.0f}", all_src, "longest attempt, s")
    led.add("fresh_attempt_costs", "longest wall time over every attempt, excluded one included (caption)", budget_max, all_src)
    (out / "fresh_attempt_costs.tex").write_text(table(
        f"Time and size of the fresh attempts, run {run_tt}, per configuration and instruction (the attempts that count, i.e.\\ "
        "without the excluded one): number of attempts, wall time (median and range, seconds), and the medians of turns, tool calls and "
        "tokens. Tokens sum the input, cache-creation, cache-read and output tokens of every response, so they are not a cost; no money "
        f"cost was recorded, and verifier generation cost was not recorded. The longest attempt took {budget_max:.0f} s.",
        "tab:fresh-costs", "llrrrrrr", "Config. & Instruction & n & Wall (s) & Range (s) & Turns & Tool calls & Tokens (M)", rows,
        size="\\footnotesize"))

    # (i) agreement of D19 and the independent labeler
    ag = a["independent_labeling"]["agreement"]["by_stratum"][F["stratum"]]
    rows = []
    for d19 in ("valid", "invalid"):
        rows.append(f"D19 {d19} & {ag['table'][d19]['valid']} & {ag['table'][d19]['invalid']} & {s_ag['table'][d19]['valid']} & "
                    f"{s_ag['table'][d19]['invalid']} \\\\")
        for vw, x, xs in (("primary", ag, src), ("sensitivity", s_ag, ssrc)):
            for lb in ("valid", "invalid"):
                nums.put(f"{'' if vw == 'primary' else 'sens.'}agree.{d19}.{lb}", x["table"][d19][lb],
                         f"{xs} independent_labeling.agreement.by_stratum.{F['stratum']}.table.{d19}.{lb}", f"D19 {d19}, labeler {lb}")
    rows[-1] += "\\midrule"
    rows.append(f"Agreement & \\multicolumn{{2}}{{c}}{{{ag['agree']}/{ag['n_units']} ({_r2(ag['agreement'])})}} & "
                f"\\multicolumn{{2}}{{c}}{{{s_ag['agree']}/{s_ag['n_units']} ({_r2(s_ag['agreement'])})}} \\\\")
    rows.append(f"Cohen's $\\kappa$ & \\multicolumn{{2}}{{c}}{{{_r2(ag['kappa'])}}} & \\multicolumn{{2}}{{c}}{{{_r2(s_ag['kappa'])}}} \\\\")
    for vw, x, xs in (("fresh_agreement primary", ag, src), ("fresh_agreement sensitivity", s_ag, ssrc)):
        led.add("fresh_agreement", f"{vw}: table D19 x labeler; agree/n_units; agreement; kappa; disagreements",
                f"{x['table']}; {x['agree']}/{x['n_units']}; {x['agreement']}; {x['kappa']}; "
                f"{[dd['representative'] for dd in x['disagreements']]}",
                f"{xs} independent_labeling.agreement.by_stratum.{F['stratum']} (table, agree, n_units, agreement, kappa, disagreements)")
    nums.put("agree", f"{ag['agree']}/{ag['n_units']}", f"{src} independent_labeling.agreement.by_stratum.{F['stratum']}.agree, .n_units")
    nums.put("agree.n", ag["agree"], f"{src} independent_labeling.agreement.by_stratum.{F['stratum']}.agree")
    nums.put("agree.rate", _r2(ag["agreement"]), f"{src} independent_labeling.agreement.by_stratum.{F['stratum']}.agreement")
    nums.put("kappa", _r2(ag["kappa"]), f"{src} independent_labeling.agreement.by_stratum.{F['stratum']}.kappa")
    nums.put("disagree", ag["disagree"], f"{src} independent_labeling.agreement.by_stratum.{F['stratum']}.disagree")
    for i, dd in enumerate(ag["disagreements"]):
        nums.put(f"disagree.{i + 1}", tex(dd["representative"]),
                 f"{src} independent_labeling.agreement.by_stratum.{F['stratum']}.disagreements[{i}].representative")
    ils = a["independent_labeling"]["sanity"]
    refs = [ils[t]["reference"] for t in fams]
    nums.put("il.ref", f"{sum(r['pass'] for r in refs)}/{sum(r['n'] for r in refs)}",
             f"{src} independent_labeling.sanity.<task>.reference.pass, .n (summed)", "references the labeler passes")
    (out / "fresh_agreement.tex").write_text(table(
        f"D19 against the independent labeler on the graded patches of run {run_tt}, each distinct graded patch once: the primary view and the "
        f"sensitivity view (every flagged attempt excluded). Both labelings are model proposals, so this is agreement between two model "
        f"labelings, not reviewer agreement; no human labels exist. The labeler has no regression part, so the disagreements on attempts "
        "that D19 labels invalid through the regression norm alone are structural. " + marker("fresh_agreement"), "tab:fresh-agree", "lrrrr",
        f" & \\multicolumn{{2}}{{c}}{{Primary ({ag['n_units']} graded patches)}} & \\multicolumn{{2}}{{c}}{{Sensitivity ({s_ag['n_units']} graded patches)}} \\\\"
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5} & labeler valid & labeler invalid & labeler valid & labeler invalid", rows,
        size="\\footnotesize"))

    # (j) the outcome matrix (longtable)
    il_lab = a["independent_labeling"]["candidates"]
    mark = lambda o: "\\checkmark" if o == "pass" else ("--" if o is None else "$\\times$")  # noqa: E731
    ntype = {"correction_violating": "corr.", "unspecified": "regr.", "": "--"}
    hdr = "Attempt & Cfg. & Instr. & D19 & Type & Lab. & " + " & ".join(SHORT[c] for c in ORDER)
    body = []
    for t in fams:
        for cid in sorted(cid for (tt, cid) in units if tt == t):
            u, x = units[(t, cid)], att[cid]
            ilv = il_lab[f"{t}/{cid}"]["label"]
            body.append(f"\\texttt{{{tex(cid)}}} & {x['configuration'].replace('config-', '')} & {tex(x['variant'])} & {tex(u['label'])} & "
                        f"{ntype.get(u['negative_type'], tex(u['negative_type']))} & {tex(ilv)} & " + " & ".join(mark(u['outcome'][c]) for c in ORDER) + " \\\\")
    exrows = []
    for cid in excl:
        x = att[cid]
        outs = {r["verifier_id"]: r["outcome"] for r in F["rows"] if r["candidate_id"] == cid}
        exrows.append(f"\\texttt{{{tex(cid)}}} & {x['configuration'].replace('config-', '')} & {tex(x['variant'])} & "
                      "\\multicolumn{3}{l}{excluded (reviewed audit)} & " + " & ".join(mark(outs.get(c)) for c in ORDER) + " \\\\")
        led.add("fresh_outcome_matrix", f"excluded attempt {cid}: outcomes (graded, counted nowhere)", {c: outs.get(c) for c in ORDER},
                f"{rsrc} rows of {cid}; {src} fresh_attempts.excluded")
    led.add("fresh_outcome_matrix", "unit rows", len(body), f"{src} per_task; independent_labeling.candidates; attempts[] of "
            + ", ".join(F["att_src"][t] for t in fams))
    ncol = 6 + len(ORDER)
    (out / "fresh_outcome_matrix.tex").write_text(
        "\\begingroup\\scriptsize\n\\begin{longtable}{lllllc" + "c" * len(ORDER) + "}\n"
        f"\\caption{{Outcome of every condition on every attempt of run {run_tt} (\\checkmark{{}} pass, $\\times$ any non-pass outcome). "
        "Cfg.: configuration; Instr.: instruction; D19: the primary label; Type: corr.\\ correction-violating, regr.\\ invalid through "
        f"the regression norm only; Lab.: the independent labeler's verdict. The excluded attempt is listed last; it was "
        "graded and counts in no rate. " + marker("fresh_outcome_matrix") + "}\\label{tab:fresh-matrix}\\\\\n"
        f"\\toprule {hdr} \\\\\\midrule\n\\endfirsthead\n\\toprule {hdr} \\\\\\midrule\n\\endhead\n"
        f"\\midrule\\multicolumn{{{ncol}}}{{r}}{{continued}} \\\\\n\\endfoot\n\\bottomrule\n\\endlastfoot\n"
        + "\n".join(body) + "\n\\midrule\n" + "\n".join(exrows) + "\n\\end{longtable}\n\\endgroup\n")

    # (k) cluster-bootstrap intervals, not inferential
    bmeta = a["meta"]["bootstrap"]
    if bmeta["inferential"]:
        raise ValueError(f"{src}: meta.bootstrap.inferential is true; the caption says the intervals are not inferential")
    star = lambda x: "$^{*}$" if x.get("ci95_degenerate") else ""  # noqa: E731
    rows = []
    for c in ORDER:
        d = a["conditions"][c]
        cells = []
        for key in ("false_acceptance", "false_rejection"):
            x = d[key]
            cells.append(_iv(x["ci95"]) + star(x))
            led.add("fresh_bootstrap", f"{c} {key} ci95; degenerate", f"{x['ci95']}; {x.get('ci95_degenerate')}", f"{src} conditions.{c}.{key}.ci95, .ci95_degenerate")
        rows.append(f"{tex(COND_TEX[c])} & " + " & ".join(cells) + " \\\\")
    rows[-1] += "\\midrule"
    rows.append("Paired difference A$-$B & FA & FR \\\\\\midrule")
    pairs: dict = {}
    for i, d in enumerate(a["comparisons"]):
        pairs.setdefault((d["a"], d["b"]), {})[d["metric"]] = (i, d)
        led.add("fresh_bootstrap", f"comparisons[{i}] {d['a']} - {d['b']} {d['metric']} ci95; degenerate", f"{d['ci95']}; {d.get('ci95_degenerate')}",
                f"{src} comparisons[{i}].ci95, .ci95_degenerate")
    for (ca, cb), ms in pairs.items():
        cells = [(_iv_signed(ms[m][1]["ci95"]) + star(ms[m][1])) if m in ms else "--" for m in ("fa", "fr")]
        rows.append(f"{SHORT[ca]}$-${SHORT[cb]} & " + " & ".join(cells) + " \\\\")
    led.add("fresh_bootstrap", "families; inferential (caption)", f"{bmeta['n_families']}; {bmeta['inferential']}", f"{src} meta.bootstrap")
    (out / "fresh_bootstrap.tex").write_text(table(
        f"\\textbf{{Not inferential.}} Cluster-bootstrap 95\\% intervals over the {bmeta['n_families']} task families of run {run_tt} "
        "(fewer than 10 families, protocol \\S15.7), for the pooled rates (top) and the paired differences (bottom), D19 labels; "
        "$^{*}$: degenerate, every resample gives the same value. " + marker("fresh_bootstrap"), "tab:fresh-boot", "lll",
        "Pooled rate & FA & FR", rows, size="\\footnotesize"))

    # (l) the behaviours behind the violators, by family (restructure plan, part 6, Tab. 4), from the keys put above
    fresh_behaviours(F, led, nums, out, units=units, viol=viol, unspec=unspec, violated=violated, marker=marker)


def regrade_table(regrade: Path, led: SectionLedger, nums: Numbers, out: Path) -> None:
    """The reliability re-grade of the pilot under a later harness (protocol §15.3, §16.1): one column per run."""
    m = json.loads((regrade / "manifest.json").read_text())
    comps = sorted(regrade.glob("compare_*.json"))
    if not comps:
        raise ValueError(f"{rel(regrade)}: no compare_<run>.json (scripts/compare_runs.py)")
    cols: list[dict[str, str]] = []

    def run_col(run_dir: Path, run_id: str, agree: tuple[str, str] | None) -> None:
        mm = json.loads((run_dir / "manifest.json").read_text())
        rr = [json.loads(x) for x in (run_dir / "results.jsonl").read_text().split("\n") if x.strip()]
        oc = Counter(r["outcome"] for r in rr)
        hv = sorted({r["harness_version"].split("/")[-1] for r in rr})
        other = sum(v for k, v in oc.items() if k not in ("pass", "task_failure"))
        unres = oc.get("unresolved", 0) if mm["repeats"] > 1 else "n/a"
        cols.append({"run": f"\\texttt{{{tex(run_id)}}}", "harness": ", ".join(hv), "repeats": str(mm["repeats"]),
                     "date": mm["started_at"][:10], "time": f"{mm['started_at'][11:19]}--{mm['finished_at'][11:19]}",
                     "revision": f"\\texttt{{{mm['code_revision'][:7]}}}", "pairs": str(len(rr)),
                     "outcomes": f"{oc['pass']}/{oc['task_failure']}/{other}", "unresolved": str(unres),
                     "reward": agree[0] if agree else "--", "outcome": agree[1] if agree else "--"})
        led.add("regrade_reliability", f"{run_id}: harness; repeats; graded; revision; pairs; pass/task_failure/other; unresolved",
                f"{hv}; {mm['repeats']}; {mm['started_at']} to {mm['finished_at']}; {mm['code_revision'][:7]}; {len(rr)}; "
                f"{oc['pass']}/{oc['task_failure']}/{other}; {unres}",
                f"{rel(run_dir / 'manifest.json')} repeats, started_at, finished_at, code_revision; {rel(run_dir / 'results.jsonl')} "
                "(rows; outcome; harness_version)")
        k = "rg" if run_dir == regrade else f"rg.{_fk(run_id).replace('.', '')}"
        nums.put(f"{k}.pairs", len(rr), f"{rel(run_dir / 'results.jsonl')} (rows)")
        nums.put(f"{k}.pass", oc["pass"], f"{rel(run_dir / 'results.jsonl')} outcome (count of pass)")
        nums.put(f"{k}.taskfailure", oc["task_failure"], f"{rel(run_dir / 'results.jsonl')} outcome (count of task_failure)")
        nums.put(f"{k}.repeats", mm["repeats"], f"{rel(run_dir / 'manifest.json')} repeats")
        nums.put(f"{k}.harness", ", ".join(hv), f"{rel(run_dir / 'results.jsonl')} harness_version")
        nums.put(f"{k}.revision", mm["code_revision"][:7], f"{rel(run_dir / 'manifest.json')} code_revision")
        nums.put(f"{k}.date", mm["started_at"][:10], f"{rel(run_dir / 'manifest.json')} started_at")
        nums.put(f"{k}.started", mm["started_at"][11:19], f"{rel(run_dir / 'manifest.json')} started_at", "UTC")
        nums.put(f"{k}.finished", mm["finished_at"][11:19], f"{rel(run_dir / 'manifest.json')} finished_at", "UTC")
        if run_dir == regrade:
            nums.put("rg.unresolved", unres, f"{rel(run_dir / 'results.jsonl')} outcome (count of unresolved)")

    run_col(regrade, m["run_id"], None)
    crit = set()
    for p in comps:
        d = json.loads(p.read_text())
        if d["new_run"] != m["run_id"]:
            raise ValueError(f"{rel(p)}: new_run {d['new_run']}, expected {m['run_id']}")
        old = regrade.parent / d["old_run"]
        n = d["pairs_same_verifier"]
        if n != d["pairs_in_both"] or d["pairs_changed_verifier"] or d["only_in_old"] or d["only_in_new"]:
            raise ValueError(f"{rel(p)}: the table assumes every pair graded in both runs with an unchanged verifier")
        rd, od = len(d["reward_discordant"]), len(d["outcome_discordant"])
        crit |= set(d["check_list_criterion"])
        run_col(old, d["old_run"], (f"{n - rd}/{n}", f"{n - od}/{n}"))
        led.add("regrade_reliability", f"{d['old_run']} vs {d['new_run']}: pairs; reward agreement; outcome agreement; criterion",
                f"{n}; {n - rd}/{n}; {n - od}/{n}; {d['check_list_criterion']}",
                f"{rel(p)} pairs_same_verifier, reward_discordant, outcome_discordant, check_list_criterion")
        k = f"rg.vs.{_fk(d['old_run']).replace('.', '')}"
        nums.put(f"{k}.reward", f"{n - rd}/{n}", f"{rel(p)} pairs_same_verifier, reward_discordant (count)")
        nums.put(f"{k}.outcome", f"{n - od}/{n}", f"{rel(p)} pairs_same_verifier, outcome_discordant (count)")
    lines = [("Harness", "harness"), ("Repeats per pair", "repeats"), ("Graded on (UTC)", "date"), ("\\quad from--to", "time"),
             ("Code revision", "revision"), ("Pairs graded", "pairs"), ("Outcomes: pass/task failure/other", "outcomes"),
             ("Pairs whose repeats disagree", "unresolved"), ("Reward agreement with the re-grade", "reward"),
             ("Outcome agreement with the re-grade", "outcome")]
    rows = [f"{text} & " + " & ".join(c[key] for c in cols) + " \\\\" for text, key in lines]
    (out / "regrade_reliability.tex").write_text(table(
        f"Reliability re-grade of the construction pilot (protocol \\S15.3, \\S16.1): run \\texttt{{{tex(m['run_id'])}}} against the "
        "run it re-grades, on the pairs graded in both with an unchanged verifier (" + ", ".join(sorted(tex(c) for c in crit)) +
        "). Pairs whose repeats disagree: n/a for a run graded once. Reward agreement is pass vs non-pass, outcome agreement the "
        "exact outcome. A reliability run, not a new pilot result.", "tab:regrade", "l" + "l" * len(cols),
        " & " + " & ".join(c["run"] for c in cols), rows, size="\\footnotesize"))


# -- the construction pilot's numbers for the prose (--pilot-numbers; restructure plan, parts 5.2 and 5.4) ---------------
# Macros \plv{key} for the text of the pilot section and its appendix: the frozen run's analysis, its comparison files
# (scripts/compare_runs.py), its results, the B1 check-origin files of the tasks, the verifier specs, and the exploratory
# re-analysis and planning simulation of D49. No pilot table is written or changed.

def pilot_inputs(run: Path) -> dict:
    """Read the frozen pilot run and the records its numbers join with; the exploratory re-analysis is the directory
    results/analyses/<run>-exploratory that scripts/exploratory_reanalysis.py writes."""
    run = run.resolve()
    exp = ROOT / "results" / "analyses" / f"{run.name}-exploratory"
    for p in (run / "analysis.json", run / "manifest.json", run / "results.jsonl", exp / "analysis.json",
              exp / "planning_simulation.json"):
        if not p.is_file():
            raise ValueError(f"--pilot-numbers: {rel(p)} does not exist")
    a = json.loads((run / "analysis.json").read_text())
    if "automated pilot" not in a["meta"]["label_policy"]:
        raise ValueError(f"{rel(run / 'analysis.json')}: label policy {a['meta']['label_policy']!r}; the text calls every label a "
                         "model proposal")
    e = json.loads((exp / "analysis.json").read_text())
    if e["meta"]["run_id"] != json.loads((run / "manifest.json").read_text())["run_id"]:
        raise ValueError(f"{rel(exp / 'analysis.json')}: the exploratory re-analysis is not of {run.name}")
    return {"a": a, "m": json.loads((run / "manifest.json").read_text()), "run": run,
            "rows": [json.loads(x) for x in (run / "results.jsonl").read_text().split("\n") if x.strip()],
            "e": e, "plan": json.loads((exp / "planning_simulation.json").read_text()),
            "compares": [(p, json.loads(p.read_text())) for p in sorted(run.glob("compare_*.json"))],
            "src": rel(run / "analysis.json"), "msrc": rel(run / "manifest.json"), "rsrc": rel(run / "results.jsonl"),
            "esrc": rel(exp / "analysis.json"), "psrc": rel(exp / "planning_simulation.json")}


def pilot_numbers(P: dict, led: SectionLedger, nums: Numbers) -> None:
    a, m, rows, e, plan = P["a"], P["m"], P["rows"], P["e"], P["plan"]
    src, msrc, rsrc, esrc, psrc = P["src"], P["msrc"], P["rsrc"], P["esrc"], P["psrc"]
    for p in (src, msrc, rsrc, esrc, psrc):
        led.add("inputs", f"{p} sha256", hashlib.sha256((ROOT / p).read_bytes()).hexdigest(), p)
    fams = sorted(a["per_task"])
    conds = [c for c, _ in ordered(a["conditions"])]
    if conds != ORDER or a["n_families"] != len(fams):
        raise ValueError(f"{src}: conditions {conds} and {a['n_families']} families; expected the six conditions of the protocol")
    # The run.
    oc = Counter(r["outcome"] for r in rows)
    harness = sorted({r["harness_version"] for r in rows})
    if len(harness) != 1 or a["meta"]["n_results"] != len(rows):
        raise ValueError(f"{rsrc}: harness versions {harness}, {len(rows)} rows against meta.n_results {a['meta']['n_results']}")
    nums.put("run", tex(m["run_id"]), f"{msrc} run_id")
    nums.put("run.pairs", _int(len(rows)), f"{rsrc} (rows; = {src} meta.n_results)", "graded pairs")
    nums.put("run.harness", harness[0].split("/")[-1], f"{rsrc} harness_version (one value in every row)")
    nums.put("run.revision", m["code_revision"][:7], f"{msrc} code_revision")
    nums.put("run.date", m["started_at"][:10], f"{msrc} started_at")
    nums.put("run.started", m["started_at"][11:19], f"{msrc} started_at", "UTC")
    nums.put("run.finished", m["finished_at"][11:19], f"{msrc} finished_at", "UTC")
    nums.put_count("run.repeats", m["repeats"], f"{msrc} repeats")
    nums.put("run.infrastructure", sum(v for k, v in oc.items() if k not in ("pass", "task_failure")),
             f"{rsrc} outcome (count of any outcome but pass and task_failure)", "infrastructure or unresolved outcomes")
    nums.put_count("run.families", len(fams), f"{src} n_families")
    nums.put_count("run.conditions", len(conds), f"{src} conditions (count)")
    per_pair = Counter((r["task_id"], r["verifier_id"]) for r in rows)
    if len(set(per_pair.values())) != 1:
        raise ValueError(f"{rsrc}: the verifiers of the families grade different numbers of candidates")
    nums.put_count("run.candidates", next(iter(per_pair.values())), f"{rsrc} rows per (task_id, verifier_id)",
                   "candidates per family: the held-out pool, the reference and the no-op")
    nums.put("checks.results", _int(sum(len(r["checks"]) for r in rows)), f"{rsrc} checks[] (summed over the rows)",
             "check results of the run")
    # Labels and the review queue.
    cn = {k: sum(d["counts"].get(k, 0) for d in a["labels"].values()) for k in ("valid", "invalid", "ambiguous", "unlabeled")}
    for k, v in cn.items():
        nums.put_count(f"labels.{k}", v, f"{src} labels.<task>.counts.{k} (summed)", f"held-out candidates labeled {k} by D19")
    nums.put_count("heldout", sum(cn.values()), f"{src} labels.<task>.counts (summed)", "held-out candidates")
    queued = sum(len(d["review_queue"]) for d in a["labels"].values())
    nums.put_count("queue", queued, f"{src} labels.<task>.review_queue (lengths summed)", "candidates queued for human review")
    nums.put_count("queue.disputed", queued - cn["ambiguous"] - cn["unlabeled"], f"{src} labels.<task>.review_queue, .counts",
             "queued candidates with a label the independent construction check disputes")
    # Rates per condition, pooled and per family; comparisons.
    for c in ORDER:
        d, sh = a["conditions"][c], SHORT[c].lower()
        for mk, key in (("fa", "false_acceptance"), ("fr", "false_rejection")):
            x = d[key]
            nums.put(f"{sh}.{mk}", _frac(x["num"], x["den"]), f"{src} conditions.{c}.{key}.num, .den")
            nums.put(f"{sh}.{mk}.rate", _r2(x["rate"]), f"{src} conditions.{c}.{key}.rate")
            nums.put(f"{sh}.{mk}.macro", _r2(x["macro"]), f"{src} conditions.{c}.{key}.macro", "mean of the per-family rates")
            nums.put(f"{sh}.{mk}.exact.upper", _r2((x.get("exact95") or [None, None])[1]), f"{src} conditions.{c}.{key}.exact95[1]",
                     "upper bound of the exact binomial 95% interval")
        nums.put(f"{sh}.j", _signed(d["youden_j"]), f"{src} conditions.{c}.youden_j")
        tn = d["tasks_with_any_accepted_negative"]
        nums.put(f"{sh}.famfa", f"{tn['num']}/{tn['den']}", f"{src} conditions.{c}.tasks_with_any_accepted_negative")
        for t in fams:
            rs = a["per_task"][t][c]
            for mk, lab, acc in (("fa", "invalid", True), ("fr", "valid", False)):
                sub = [r for r in rs if r["label"] == lab]
                k = sum((r["outcome"] == "pass") == acc for r in sub)
                nums.put(f"{sh}.{_fk(t)}.{mk}", _frac(k, len(sub)), f"{src} per_task.{t}.{c}[] (label {lab}; outcome)")
            for name, origin, lab in (("nm", "constructed_near_miss", "invalid"), ("nm.amb", "constructed_near_miss", "ambiguous"),
                                      ("pre", "observed_pre_correction", None)):
                sub = [r for r in rs if r["origin"] == origin and (lab is None or r["label"] == lab)]
                if sub:
                    nums.put(f"{name}.{_fk(t)}.{sh}", _frac(sum(r["outcome"] == "pass" for r in sub), len(sub)),
                             f"{src} per_task.{t}.{c}[] (origin {origin}" + (f", label {lab}" if lab else "") + "; outcome pass)")
        bn = a["by_negative_type"][c]
        nums.put(f"cv.{sh}", f"{bn['correction_violating']['accepted']}/{bn['correction_violating']['n']}",
                 f"{src} by_negative_type.{c}.correction_violating", "correction-violating invalid candidates accepted")
        pre = [r for t in fams for r in a["per_task"][t][c] if r["origin"] == "observed_pre_correction" and r["label"] == "invalid"]
        nums.put(f"pre.{sh}", _frac(sum(r["outcome"] == "pass" for r in pre), len(pre)),
                 f"{src} per_task.*.{c}[] (origin observed_pre_correction, label invalid; outcome pass)",
                 "invalid pre-correction states accepted")
    bnt = a["by_negative_type"]["initial_plain"]
    nums.put_count("neg.cv.n", bnt["correction_violating"]["n"], f"{src} by_negative_type.initial_plain.correction_violating.n",
             "invalid candidates that violate a correction requirement")
    nums.put_count("neg.iv.n", bnt.get("initial_violating", {"n": 0})["n"], f"{src} by_negative_type.initial_plain.initial_violating.n",
             "invalid candidates that violate first-request requirements only")
    nums.put_count("pre.invalid", sum(r["origin"] == "observed_pre_correction" and r["label"] == "invalid"
                                for t in fams for r in a["per_task"][t]["initial_plain"]),
             f"{src} per_task.*.initial_plain[] (origin observed_pre_correction, label invalid)", "invalid pre-correction states")
    for i, d in enumerate(a["comparisons"]):
        k, base = f"cmp.{SHORT[d['a']].lower()}-{SHORT[d['b']].lower()}.{d['metric']}", f"{src} comparisons[{i}]"
        nums.put(f"{k}.diff", _signed(d["difference"]), f"{base}.difference")
        nums.put(f"{k}.n", d["n_metric"], f"{base}.n_metric")
        nums.put(f"{k}.disc.ab", d["discordant"]["a_accepts_b_rejects"], f"{base}.discordant.a_accepts_b_rejects")
        nums.put(f"{k}.disc.ba", d["discordant"]["a_rejects_b_accepts"], f"{base}.discordant.a_rejects_b_accepts")
    # Exploratory views of the run (protocol v0.3 to v0.5): near misses by label status, construction-intent labels, the
    # independent construction checks' labels, and the pool without duplicates.
    xt = a["near_miss_crosstab"]
    n_conf, n_amb = xt["initial_plain"]["confirmed_invalid"]["n"], xt["initial_plain"]["ambiguous"]["n"]
    nums.put_count("nm.n", n_conf + n_amb, f"{src} near_miss_crosstab.initial_plain (confirmed_invalid.n + ambiguous.n)", "invalid-by-construction near misses")
    nums.put_count("nm.confirmed", n_conf, f"{src} near_miss_crosstab.initial_plain.confirmed_invalid.n", "confirmed invalid by D19")
    nums.put_count("nm.ambiguous", n_amb, f"{src} near_miss_crosstab.initial_plain.ambiguous.n", "left ambiguous by D19")
    # The near misses whose D19 label records more than one violated requirement (the held-out pool's description).
    multi = [len(c["violated"]) for d in a["labels"].values() for c in d["candidates"]
             if c["origin"] == "constructed_near_miss" and len(c["violated"]) > 1]
    if not multi:
        raise ValueError(f"{src}: no near miss's label records more than one violated requirement")
    how = f"{src} labels.<task>.candidates[] (origin constructed_near_miss; violated, counted)"
    nums.put_count("nm.multi.n", len(multi), how, "near misses whose D19 label records more than one violated requirement")
    nums.put("nm.multi.min", min(multi), how, "the fewest violated requirements among them")
    nums.put("nm.multi.max", max(multi), how, "the most violated requirements among them")
    for c in ORDER:
        sh, x = SHORT[c].lower(), xt[c]
        nums.put(f"nm.conf.{sh}", f"{x['confirmed_invalid']['accepted']}/{x['confirmed_invalid']['n']}", f"{src} near_miss_crosstab.{c}.confirmed_invalid")
        nums.put(f"nm.amb.{sh}", f"{x['ambiguous']['accepted']}/{x['ambiguous']['n']}", f"{src} near_miss_crosstab.{c}.ambiguous")
        for name, view in (("intent", "sensitivity_construction_labels"), ("checks", "sensitivity_check_labels"),
                           ("nodup", "sensitivity_without_duplicates")):
            v = a[view][c]
            for mk in ("fa", "fr"):
                nums.put(f"{name}.{sh}.{mk}", _frac(v[f"{mk}_num"], v[f"{mk}_den"]), f"{src} {view}.{c}.{mk}_num, .{mk}_den")
    nums.put_count("duplicates", len(a["duplicates"]), f"{src} duplicates (count)", "held-out candidates that duplicate another")
    # B1 by the origin of its checks.
    b1 = a["b1_upstream_only"]
    nums.put("b1.base.fa", _frac(b1["fa_num"], b1["fa_den"]), f"{src} b1_upstream_only.fa_num, .fa_den")
    nums.put("b1.base.fr", _frac(b1["fr_num"], b1["fr_den"]), f"{src} b1_upstream_only.fr_num, .fr_den")
    added, fr_added, fr_base = [], 0, 0
    labels = {(t, r["candidate"]): r["label"] for t in fams for r in a["per_task"][t]["repo_tests"]}
    for t in fams:
        up_path = ROOT / "tasks" / t / "verifiers" / "repo_tests" / "upstream_check_ids.json"
        up = set(json.loads(up_path.read_text())["upstream_check_ids"])
        if len(up) != b1["n_checks"][t]:
            raise ValueError(f"{rel(up_path)}: {len(up)} upstream checks, {src} b1_upstream_only.n_checks.{t} = {b1['n_checks'][t]}")
        spec, _ = _spec(t, "repo_tests")
        added.append(len(spec["checks"]) - len(up))
        for r in rows:
            if r["task_id"] == t and r["verifier_id"] == "repo_tests" and labels.get((t, r["candidate_id"])) == "valid" \
                    and r["outcome"] != "pass":
                bad = [ch["check_id"] for ch in r["checks"] if ch["status"] != "passed"]
                fr_added += any(x not in up for x in bad)
                fr_base += any(x in up for x in bad)
    how = (f"{rsrc} (repo_tests rows of valid candidates: outcome; checks[].status) and tasks/<task>/verifiers/repo_tests/"
           "upstream_check_ids.json; labels from per_task")
    nums.put_count("b1.fr.added", fr_added, how, "B1 false rejections failing a check the session agent added")
    nums.put_count("b1.fr.base", fr_base, how, "B1 false rejections failing a check of the base commit's tests")
    nums.put("b1.checks.added.min", min(added), "tasks/<task>/verifiers/repo_tests/spec.json checks (count) less "
             "upstream_check_ids.json (count), minimum over the families", "checks the session agent added")
    nums.put("b1.checks.added.max", max(added), "the same, maximum over the families")
    # The audit: audited verifiers identical to their plain counterparts, and the held-out outcomes it changed.
    n_aud, same, outcomes, changed = 0, 0, 0, 0
    for t in fams:
        for plain, aud in (("initial_plain", "initial_audited"), ("full_plain", "full_audited")):
            sp, _ = _spec(t, plain)
            sa, _ = _spec(t, aud)
            n_aud += 1
            if sa["content_sha256"] == sp["content_sha256"]:
                same += 1
                continue
            po = {r["candidate"]: r["outcome"] == "pass" for r in a["per_task"][t][plain]}
            ao = {r["candidate"]: r["outcome"] == "pass" for r in a["per_task"][t][aud]}
            if po.keys() != ao.keys():
                raise ValueError(f"{src}: per_task.{t}: {plain} and {aud} graded different held-out candidates")
            outcomes += len(ao)
            changed += sum(po[cid] != ao[cid] for cid in ao)
    how = f"tasks/<task>/verifiers/<plain|audited>/spec.json content_sha256; {src} per_task.<task>.<condition>[].outcome"
    nums.put_count("audit.verifiers", n_aud, how, "audited verifiers (C2, C4)")
    nums.put_count("audit.identical", same, how, "audited verifiers identical to their plain counterparts")
    nums.put_count("audit.revised", n_aud - same, how, "audited verifiers the audit revised")
    nums.put("audit.outcomes", outcomes, how, "held-out outcomes of the revised verifiers")
    nums.put("audit.changed", _frac(changed, outcomes), how, "held-out outcomes the audit changed, of those")
    nums.put_count("audit.changed.n", changed, how)
    # Contract recovery and the mappers' agreement.
    kap = [d["kappa"] for x in a["mapping_agreement"].values() for d in x.values() if d.get("kappa") is not None]
    nums.put("kappa.min", _r2(min(kap)), f"{src} mapping_agreement.<task>.<contract>.kappa (minimum)", "agreement of the two model mappers")
    nums.put("kappa.max", _r2(max(kap)), f"{src} mapping_agreement.<task>.<contract>.kappa (maximum)")
    for v in ("initial_only", "full_session"):
        covs = [a["coverage"][t]["variants"][v]["coverage"] for t in fams]
        vk = v.split("_")[0]
        nums.put(f"coverage.{vk}.min", _r2(min(covs)), f"{src} coverage.<task>.variants.{v}.coverage (minimum)")
        nums.put(f"coverage.{vk}.max", _r2(max(covs)), f"{src} coverage.<task>.variants.{v}.coverage (maximum)")
        for t in fams:
            d, n_ref = a["coverage"][t]["variants"][v], len(a["coverage"][t]["reference_scored"])
            base = f"{src} coverage.{t}.variants.{v}"
            nums.put(f"cov.{_fk(t)}.{vk}", _r2(d["coverage"]), f"{base}.coverage")
            nums.put(f"cov.{_fk(t)}.{vk}.covered", f"{len(d['covered'])}/{n_ref}", f"{base}.covered; coverage.{t}.reference_scored")
            nums.put(f"cov.{_fk(t)}.{vk}.missing", len(d["missing"]), f"{base}.missing (count)")
            nums.put(f"cov.{_fk(t)}.{vk}.contradicting", len(d["contradicting"]), f"{base}.contradicting (count)")
            nums.put(f"cov.{_fk(t)}.{vk}.scored", d["n_recovered_scored"], f"{base}.n_recovered_scored")
    # Harness reliability: the superseded runs against this one (scripts/compare_runs.py).
    for p, d in P["compares"]:
        if d["new_run"] != m["run_id"]:
            raise ValueError(f"{rel(p)}: new_run {d['new_run']}, expected {m['run_id']}")
        k, n = f"rel.{d['old_run'].removeprefix('pilot-')}", d["pairs_same_verifier"]
        ch = d.get("changed_verifier_pairs", [])
        ch_same = sum((c["old"] == "pass") == (c["new"] == "pass") for c in ch)
        nums.put(f"{k}.both", d["pairs_in_both"], f"{rel(p)} pairs_in_both", "pairs graded in both runs")
        nums.put(f"{k}.same", n, f"{rel(p)} pairs_same_verifier", "of them, with an unchanged verifier")
        nums.put(f"{k}.changed", d["pairs_changed_verifier"], f"{rel(p)} pairs_changed_verifier")
        nums.put(f"{k}.reward", _frac(n - len(d["reward_discordant"]), n), f"{rel(p)} pairs_same_verifier, reward_discordant (count)")
        nums.put(f"{k}.outcome", _frac(n - len(d["outcome_discordant"]), n), f"{rel(p)} pairs_same_verifier, outcome_discordant (count)")
        nums.put(f"{k}.changed.agree", _frac(ch_same, len(ch)), f"{rel(p)} changed_verifier_pairs[] (old, new: pass or not)",
                 "changed-verifier pairs with the same reward")
    # D49: the exploratory sign-flip tests, the B2 equivalence tests and the draft precision plan.
    for name, d in e["paired_comparisons"]["comparisons"].items():
        ca, cb = name.split("_vs_")
        for mk in ("fa", "fr"):
            x, k = d[mk], f"signflip.{SHORT[ca].lower()}-{SHORT[cb].lower()}.{mk}"
            sp, base = x["signflip"]["pooled"], f"{esrc} paired_comparisons.comparisons.{name}.{mk}"
            nums.put(f"{k}.diff", _signed(x["pooled_difference"]), f"{base}.pooled_difference")
            nums.put(f"{k}.p1", _p(sp["p_greater"]), f"{base}.signflip.pooled.p_greater", "one-sided p, A > B")
            nums.put(f"{k}.p2", _p(sp["p_two_sided"]), f"{base}.signflip.pooled.p_two_sided")
            nums.put(f"{k}.floor", _p(sp["conditional_floor_one_sided"]), f"{base}.signflip.pooled.conditional_floor_one_sided")
    eq = e["b2_equivalence"]
    tost = [y["tost"][stat]["p_tost"] for x in eq["comparisons"].values() for lab in x.values() for y in lab.values()
            for stat in ("pooled", "family_mean")]
    nums.put("tost.min", _p(min(tost)), f"{esrc} b2_equivalence.comparisons.*.*.*.tost.{{pooled,family_mean}}.p_tost (minimum)",
             "the smallest equivalence-test p")
    nums.put("tost.margin", _r2(eq["margin"]), f"{esrc} b2_equivalence.margin")
    nums.put("tost.alpha", _p(eq["alpha_one_sided"]), f"{esrc} b2_equivalence.alpha_one_sided")
    # D49's scenario of the draft precision plan: one natural negative per family, a difference of 20 points, the middle
    # between-family spread; the power at 30 families, the natural arm's family cap.
    fc, neg, delta, tau = plan["family_counts"], "n_neg=1", "delta=20pp", "tau=mid"
    cell, base = fc["min_families"][neg][delta][tau], f"{psrc} family_counts"
    nums.put("plan.families", cell["power80"], f"{base}.min_families.{neg}.{delta}.{tau}.power80",
             "families with one natural negative each for 80% power")
    nums.put("plan.delta", f"{int(re.fullmatch(r'delta=(\d+)pp', delta).group(1)) / 100:.2f}",
             f"{base}.min_families: the scenario key {delta}", "the false-acceptance difference planned for")
    nums.put("plan.power.k30", _r2(fc["power"][neg][delta][tau]["K=30"]), f"{base}.power.{neg}.{delta}.{tau}.K=30",
             "power with 30 families")
    nums.put("plan.alpha", _p(fc["alpha_one_sided"]), f"{base}.alpha_one_sided")


# -- the design's constants and the protocol's history (--design; restructure plan, parts 3 and 5.2) ---------------------
# paper/design_constants.json lists each constant with its value and the checks that tie the value to its source: a quote
# that must occur in the cited file and hold the value, a pattern of the code whose captured value gives it, a count of
# files, or a field of recorded JSON files reduced to one value. The protocol's versions are recomputed from the git
# objects of their commits (v0.1 to v0.5) or from byte prefixes of the current protocol (v0.6 on), and each hash and hash
# time must be the one the decision log records. Nothing is written if a check fails.

DESIGN = ROOT / "paper" / "design_constants.json"
DESIGN_DIR = "design"  # paper/generated/design/ and paper/evidence_ledger_design.md
HASH_DIGITS = 8  # the hex digits of a protocol version's sha256 that the text and the amendments table show
_NUMBER_WORD = {w: i for i, w in enumerate(COUNT_WORDS)} | {"thirty": 30, "forty": 40, "fifty": 50, "hundred": 100}
_COMPUTE = {
    "int": lambda g: str(int(float(g))),
    "mib_to_gib": lambda g: f"{int(g) / 1024:g}",
    "alpha_percent": lambda g: f"{round((1 - float(g)) * 100, 6):g}",  # a significance level alpha as a confidence level
    "as_is": lambda g: g,
}


def _norm_ws(s: str) -> str:
    return " ".join(s.split())


def _numbers_in(text: str) -> set:
    """The numbers a text states, in digits (with thousands separators) or in words, as exact decimals."""
    from decimal import Decimal
    out = {Decimal(x.replace(",", "")) for x in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", text)}
    out |= {Decimal(_NUMBER_WORD[w.lower()]) for w in re.findall(r"[A-Za-z]+", text) if w.lower() in _NUMBER_WORD}
    return out


def _states(value: str, quote: str) -> bool:
    """Whether ``quote`` states ``value``: the same number (``2000`` in "2,000", ``3`` in "three"), or else the value's
    text as a whole token."""
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(value) in _numbers_in(quote)
    except InvalidOperation:  # a date or a time: not part of a longer number (2026-11-21T17:42:36Z states both)
        return re.search(r"(?<![0-9:.])" + re.escape(value) + r"(?![0-9:])", quote) is not None


def _iso(v: str) -> datetime:
    t = datetime.fromisoformat(v)  # Python 3.11 on reads a trailing Z
    return t.astimezone(UTC) if t.tzinfo else t.replace(tzinfo=UTC)


def _json_values(doc: object, path: str) -> list:
    """The values at a dot path, where ``[*]`` takes every item of a list (``attempts[*].ended_at``)."""
    cur = [doc]
    for part in path.split("."):
        name, star = (part[:-3], True) if part.endswith("[*]") else (part, False)
        nxt = []
        for x in cur:
            if not isinstance(x, dict) or name not in x:
                raise KeyError(path)
            v = x[name]
            nxt += (v if isinstance(v, list) else [v]) if star else [v]
        cur = nxt
    return cur


class Design:
    """paper/design_constants.json, read and checked. ``protocol``: the versions with their recomputed hashes."""

    def __init__(self, path: Path) -> None:
        self.path, self.doc = path, json.loads(path.read_text())
        self.src = rel(path)
        self.protocol: dict[str, dict] = {}

    def _source_text(self, source: str) -> str:
        p = ROOT / source
        if not p.is_file():
            raise ValueError(f"{self.src}: source {source} does not exist")
        return p.read_text(encoding="utf-8")

    def check(self, c: dict, ck: dict) -> str:
        """Check one constant against one of its checks; returns how the value was found, for the ledger."""
        key, value, source = c["key"], str(c["value"]), ck["source"]
        if "quote" in ck:
            q = _norm_ws(ck["quote"])
            if q not in _norm_ws(self._source_text(source)):
                raise ValueError(f"{self.src}: {key}: the quote {q[:60]!r} does not occur in {source}")
            if not _states(value, q):
                raise ValueError(f"{self.src}: {key}: its quote does not state the value {value!r}")
            return f'{source}: "{q}"'
        if "regex" in ck:
            hits = re.findall(ck["regex"], self._source_text(source))
            if len(hits) != 1:
                raise ValueError(f"{self.src}: {key}: the pattern matches {len(hits)} times in {source}, not once")
            got = _COMPUTE[ck.get("compute", "as_is")](hits[0])
            if got != value:
                raise ValueError(f"{self.src}: {key} = {value!r}, but {source} gives {got!r}")
            return f"{source}: /{ck['regex']}/ -> {hits[0]}" + (f" ({ck['compute']})" if ck.get("compute") else "")
        if "count" in ck:
            files = sorted(p for p in ROOT.glob(ck["count"]) if p.is_file())
            if str(len(files)) != value:
                raise ValueError(f"{self.src}: {key} = {value!r}, but {len(files)} files match {ck['count']}")
            return f"{ck['count']} (files counted: {len(files)})"
        if "json" in ck:
            files = sorted(ROOT.glob(source))
            if not files:
                raise ValueError(f"{self.src}: {key}: no file matches {source}")
            vals = [v for p in files for v in _json_values(json.loads(p.read_text()), ck["json"])]
            got = self._reduce(key, vals, ck.get("reduce", "one"), ck.get("format", "str"))
            if got != value:
                raise ValueError(f"{self.src}: {key} = {value!r}, but {source} {ck['json']} gives {got!r}")
            return f"{source} {ck['json']} ({ck.get('reduce', 'one')}, {len(files)} file(s))"
        raise ValueError(f"{self.src}: {key}: a check needs one of quote, regex, count or json")

    def _reduce(self, key: str, vals: list, how: str, fmt: str) -> str:
        if how.startswith(("count_after:", "count_before:")):
            ref = how.split(":", 1)[1]
            t = _iso(self.protocol[ref.removeprefix("@protocol.v")]["hashed_at"]) if ref.startswith("@protocol.v") else _iso(ref)
            after = how.startswith("count_after:")
            return str(sum((_iso(v) > t) if after else (_iso(v) < t) for v in vals))
        if how == "pow2":
            if len(set(vals)) != 1:
                raise ValueError(f"{self.src}: {key}: the field holds {sorted(set(vals))}, not one value")
            return str(2 ** int(vals[0]))
        if how == "span_minutes":
            ts = sorted(_iso(v) for v in vals)
            return str(round((ts[-1] - ts[0]).total_seconds() / 60))
        if how in ("min", "max"):
            v = (min if how == "min" else max)(vals, key=lambda x: _iso(x) if fmt.startswith(("time", "date")) else x)
        elif how == "one":
            if len(set(map(str, vals))) != 1:
                raise ValueError(f"{self.src}: {key}: the field holds {sorted(set(map(str, vals)))}, not one value")
            v = vals[0]
        else:
            raise ValueError(f"{self.src}: {key}: unknown reduction {how!r}")
        if fmt == "time":
            return _iso(v).strftime("%H:%M:%S")
        if fmt == "time.1":  # to the tenth of a second, rounded
            t = _iso(v) + timedelta(microseconds=50000)
            return t.strftime("%H:%M:%S") + f".{t.microsecond // 100000}"
        if fmt == "date":
            return _iso(v).strftime("%Y-%m-%d")
        if fmt == "int":
            return str(int(float(v)))
        if fmt == "gib":  # a container memory limit as Docker writes it ("4g")
            if not re.fullmatch(r"\d+g", str(v)):
                raise ValueError(f"{self.src}: {key}: {v!r} is not a memory size in GiB")
            return str(v)[:-1]
        return str(v)

    def protocol_versions(self) -> list[dict]:
        """Recompute every version's sha256 (v0.1 to v0.5 from the git objects of their commits, which fails closed without
        the repository's history; v0.6 on from the current file's byte prefix that ends one byte before the next section's
        heading, the last from the whole file) and check it and its hash time against the decision log."""
        P = self.doc["protocol"]
        cur = (ROOT / P["file"]).read_bytes()
        log = (ROOT / P["log"]).read_text(encoding="utf-8")
        out = []
        for v in P["versions"]:
            if "commit" in v:
                r = subprocess.run(["git", "-C", str(ROOT), "show", f"{v['commit']}:{P['file']}"], capture_output=True, check=False)
                if r.returncode != 0:
                    raise ValueError(f"{self.src}: protocol v{v['version']}: no git object of {P['file']} at {v['commit']} "
                                     "(the repository's history is needed; nothing is written)")
                body, how = r.stdout, f"git show {v['commit']}:{P['file']}"
            elif "before_section" in v:
                m = re.search(rb"^## " + str(v["before_section"]).encode() + rb"\. ", cur, re.MULTILINE)
                if not m:
                    raise ValueError(f"{self.src}: protocol v{v['version']}: no section {v['before_section']} in {P['file']}")
                body, how = cur[:m.start() - 1], f"{P['file']}, bytes before the heading of section {v['before_section']} (less one)"
            else:
                body, how = cur, f"{P['file']} (the whole file)"
            sha = hashlib.sha256(body).hexdigest()
            m = re.search(rf"^### {re.escape(v['entry'])}\. .*?(?=^### D\d+\. |\Z)", log, re.MULTILINE | re.DOTALL)
            if not m:
                raise ValueError(f"{self.src}: protocol v{v['version']}: no entry {v['entry']} in {P['log']}")
            if sha not in m.group(0):
                raise ValueError(f"{self.src}: protocol v{v['version']}: sha256 {sha[:12]}... is not in {v['entry']} of {P['log']}")
            if v["hashed_at"] not in m.group(0):
                raise ValueError(f"{self.src}: protocol v{v['version']}: hash time {v['hashed_at']} is not in {v['entry']}")
            rec = dict(v, sha256=sha, how=how)
            self.protocol[v["version"]] = rec
            out.append(rec)
        return out


def _design_text_ok(text: str, where: str) -> None:
    """An authored table cell holds no number of its own: only macros and identifiers (paper/check_numbers.py's rule)."""
    spec = importlib.util.spec_from_file_location("check_numbers", Path(__file__).with_name("check_numbers.py"))
    cn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cn)
    bad = cn.findings(text, where)
    if bad:
        raise ValueError(f"{where}: a number outside a macro: {', '.join(f.token for f in bad)}")


def design_numbers(D: Design, led: SectionLedger, nums: Numbers, out: Path) -> None:
    led.add("inputs", f"{D.src} sha256", hashlib.sha256(D.path.read_bytes()).hexdigest(), D.src)
    versions = D.protocol_versions()  # first: the counts may refer to a version's hash time
    for c in D.doc["constants"]:
        hows = [D.check(c, ck) for ck in c["checks"]]
        value = str(c["value"])
        shown = _int(int(value)) if re.fullmatch(r"\d{4,}", value) else value
        what = c["what"] + (f"; unit {c['unit']}" if c.get("unit") else "")
        if c.get("words") and re.fullmatch(r"\d+", value):
            nums.put_count(c["key"], int(value), " | ".join(hows), what)
        else:
            nums.put(c["key"], shown, " | ".join(hows), what)
    # The protocol's history: per version its section, hash, date, time and entry; and the amendments table.
    nums.put_count("protocol.versions", len(versions), f"{D.src} protocol.versions (count)", "protocol versions")
    nums.put_count("protocol.amendments", len(versions) - 1, f"{D.src} protocol.versions (count, less v0.1)",
                   "amendments after v0.1")
    rows = []
    for v in versions:
        k, t = f"protocol.v{v['version']}", _iso(v["hashed_at"])
        log = f"{D.doc['protocol']['log']} ({v['entry']})"
        nums.put(f"{k}.hash", v["sha256"][:HASH_DIGITS], f"{v['how']}: sha256 {v['sha256']}, as {log} records it",
                 f"first {HASH_DIGITS} hex digits")
        nums.put(f"{k}.date", t.strftime("%Y-%m-%d"), f"{log}: {v['hashed_at']}", "UTC")
        nums.put(f"{k}.time", t.strftime("%H:%M:%S"), f"{log}: {v['hashed_at']}", "UTC")
        nums.put(f"{k}.entry", v["entry"], f"{log}")
        if v.get("section"):
            nums.put(f"{k}.section", v["section"], f"{D.doc['protocol']['file']} heading of section {v['section']}")
        for col in ("fixes", "before", "after"):
            _design_text_ok(v[col], f"{D.src} protocol v{v['version']} {col}")
        sec = f" (\\S{v['section']})" if v.get("section") else ""
        rows.append(f"v{v['version']}{sec}\\newline \\dv{{{k}.date}}\\newline \\dv{{{k}.time}}\\newline "
                    f"\\texttt{{\\dv{{{k}.hash}}}}, \\dv{{{k}.entry}} & {v['fixes']} & {v['before']} & {v['after']} \\\\")
        led.add("amendments", f"v{v['version']}: section; sha256; hashed at; entry", f"{v.get('section') or '--'}; {v['sha256']}; "
                f"{v['hashed_at']}; {v['entry']}", f"{v['how']}; {log}")
    led.add("amendments", "caption: hex digits shown of each hash", HASH_DIGITS, "paper/make_tables.py HASH_DIGITS")
    head = "Version & What it fixes & Fixed before & After"
    (out / "amendments_table.tex").write_text(  # a longtable: the twelve rows need more than a page
        "\\begingroup\\scriptsize\n\\begin{longtable}{@{}p{0.12\\linewidth}p{0.36\\linewidth}p{0.21\\linewidth}"
        "p{0.21\\linewidth}@{}}\n"
        "\\caption{The protocol's versions (\\texttt{experiments/protocol.md}), each hashed and timestamped locally (UTC; the "
        f"first {HASH_DIGITS} hex digits of its sha256, recomputed from the git object of its commit or from a byte prefix of "
        "the current file, as the decision-log entry named records it). Fixed before: what did not exist yet when the version "
        "was hashed; after: the relevant data that existed then.}\\label{tab:amendments}\\\\\n"
        f"\\toprule {head} \\\\\\midrule\n\\endfirsthead\n\\toprule {head} \\\\\\midrule\n\\endhead\n"
        "\\midrule\\multicolumn{4}{r}{continued} \\\\\n\\endfoot\n\\bottomrule\n\\endlastfoot\n"
        + "\n".join(rows) + "\n\\end{longtable}\n\\endgroup\n")


# -- natural PR-review arm and the Trace Commons screen -----------------------------------------------------------------

NATURAL_INPUTS = {"M0": "data/manifests/screening_natural_aidev.json", "M9": "data/manifests/screening_natural_aidev_s9.json",
                  "M9x": "data/manifests/screening_natural_aidev_s9x.json", "NI": "data/manifests/natural_tasks_index.json",
                  "RL": "data/manifests/rejection_ledger.json", "TC": "data/manifests/screening_natural.json"}
STAGE_TEXT = {"S1": "Agent-authored pull requests (AIDev v5)",
              "S2": "Python repository; MIT, Apache-2.0 or BSD licence; not a fork",
              "S3": "Inline review comments on these PRs",
              "S4": "Written by a person, starts a thread, not by the PR's author",
              "S5": "On a \\texttt{.py} file, with a diff hunk",
              "S6": "Commented code changed afterwards (a proxy)",
              "S7": "Reviewed commit in the PR's commit list; a later commit exists",
              "S8": "PR linked to an issue written by a person",
              "S8a": "First later commit attributed to an agent"}
# (key in summary.failed_by_reason, row text, macro key)
S9_REASONS = [("fetch_over_the_caps", "repository over the fetch cap", "cap"), ("commits_not_fetchable", "commits not fetchable", "fetch"),
              ("no_later_commit_changes_the_commented_file", "no later commit changes the commented file", "nolater"),
              ("addressing_commit_not_agent_attributed", "addressing commit not agent-attributed", "agent"),
              ("not_behaviour_change_or_defect", "not a behaviour change or defect", "behaviour"),
              ("not_addressed", "not addressed by the later commit", "addressed"),
              ("not_testable_offline", "not testable offline", "offline")]
# (category, prefix of the recorded reason, macro key)
S10_REASONS = [("base tests fail to collect", "base tests fail to collect", "collect"),
               ("no resolvable dependency closure", "no resolvable closure", "closure"),
               ("environment too large", "environment too large", "toolarge"),
               ("empty base-test subset", "base tests: the base-test subset is empty", "emptysubset"),
               ("fetch over the repository cap", "fetch over the caps", "fetchcap"),
               ("merge rule", "a merge between the base and the addressing commit", "merge")]
# The S10 table's shorter form of a category (the funnel prints the category itself).
S10_SHORT = {"no resolvable dependency closure": "no dependency closure", "fetch over the repository cap": "fetch over the cap"}
TC_REASONS = [("no recoverable base commit", "no recoverable base commit", "basecommit"),
              ("replay: unreconstructable without a base tree", "replay: unreconstructable", "replay"),
              ("no code licence identified", "no code licence identified", "licence"),
              ("no correction candidate under the correction-cue rule", "no correction candidate", "correction"),
              ("unsuitable task", "unsuitable_task", "unsuitable"), ("unsupported transcript format", "format:", "format"),
              ("environment failure", "environment_failure", "environment")]
# The S9 extension has no S10 outcome: its S10 step was stopped at a usage limit, and its families are to be built again
# for natural-pr-v2 (decision log D66, D75; protocol §20.2). The tables say so instead of marking a cell as pending.
EXT_S10 = ("not run: the extension's S10 step was stopped at a usage limit, and its families are to be built again for "
           "\\texttt{natural-pr-v2} (decision log D66, D75; protocol \\S20.2)")


def _category(reason: str, table_: list[tuple[str, str, str]], where: str) -> str:
    hits = [cat for cat, prefix, _ in table_ if reason.startswith(prefix)]
    if len(hits) != 1:
        raise ValueError(f"{where}: reason {reason[:60]!r}... matches {len(hits)} categories; extend the category list")
    return hits[0]


def _agent_names(m0: dict) -> tuple[str, ...]:
    """The agent product names of the AIDev screening record (its stages' ``by_agent`` keys, with their parts of five
    letters or more), which no natural output may hold (:func:`_check_private`)."""
    names = set()
    for st in m0["stages"]:
        for k in st.get("by_agent", {}):
            names |= {k, k.replace("_", " ")} | {part for part in k.split("_") if len(part) >= 5}
    return tuple(sorted(names))


def natural_inputs() -> dict:
    N = {k: json.loads((ROOT / p).read_text()) for k, p in NATURAL_INPUTS.items()}
    N["sha256"] = {k: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for k, p in NATURAL_INPUTS.items()}
    N["agent_names"] = _agent_names(N["M0"])
    return N


def natural_tables(N: dict, led: SectionLedger, nums: Numbers, out: Path) -> None:
    src = NATURAL_INPUTS
    for k, p in src.items():
        led.add("inputs", f"{p} sha256", N["sha256"][k], p)
    # (e) the funnel
    stages = {st["id"]: st for st in N["M0"]["stages"]}
    missing = [s for s in (*STAGE_TEXT, "S8'", "S8a'") if s not in stages]
    if missing:
        raise ValueError(f"{src['M0']}: stages {missing} missing")
    rows1 = []
    for sid, text in STAGE_TEXT.items():
        st = stages[sid]
        comments = _int(st["count"]) if st["unit"] == "review_comment" else "--"
        if st["unit"] == "pull_request" and st["count"] != st["prs"]:
            raise ValueError(f"{src['M0']}: stage {sid} counts PRs but count != prs")
        rows1.append(f"{sid} & {text} & {comments} & {_int(st['prs'])} & {_int(st['repos'])} \\\\")
        led.add("natural_funnel", f"{sid} comments / PRs / repositories", f"{st['count'] if st['unit'] == 'review_comment' else '--'} / "
                f"{st['prs']} / {st['repos']}", f"{src['M0']} stages[id={sid}] (unit, count, prs, repos)")
        k = f"aidev.{sid.lower()}"
        if st["unit"] == "review_comment":
            nums.put(f"{k}.comments", _int(st["count"]), f"{src['M0']} stages[id={sid}].count")
        nums.put(f"{k}.prs", _int(st["prs"]), f"{src['M0']} stages[id={sid}].prs")
        nums.put(f"{k}.repos", _int(st["repos"]), f"{src['M0']} stages[id={sid}].repos")
    for sid, key in (("S8'", "s8p"), ("S8a'", "s8ap")):
        nums.put(f"aidev.{key}.comments", _int(stages[sid]["count"]), f"{src['M0']} stages[id={sid}].count",
                 "without the linked-issue requirement")
        led.add("natural_funnel", f"{sid} comments (without the linked-issue requirement; caption)", stages[sid]["count"],
                f"{src['M0']} stages[id={sid}].count")
    # The S8a comments of the agent product with the most of them (restructure plan, part 5.2); no product is named.
    per_agent = [v["comments"] for v in stages["S8a"]["by_agent"].values()]
    if sum(per_agent) != stages["S8a"]["count"]:
        raise ValueError(f"{src['M0']}: stages[id=S8a].by_agent.*.comments do not sum to its count")
    nums.put("aidev.s8a.topagent", _int(max(per_agent)), f"{src['M0']} stages[id=S8a].by_agent.<agent>.comments (the largest "
             f"of its {len(per_agent)} values; they sum to stages[id=S8a].count)", "S8a comments of the agent product with the most")
    ck = N["M0"]["checks"]
    nums.put("aidev.check.join", _pct(ck["comment_to_pr"]["all_comments"]["match_rate"], 2),
             f"{src['M0']} checks.comment_to_pr.all_comments.match_rate", "comments joined to their PR")
    nums.put("aidev.check.order", _int(ck["commit_order"]["commit_id_after_original_in_row_order"]),
             f"{src['M0']} checks.commit_order.commit_id_after_original_in_row_order")
    nums.put("aidev.check.order.of", _int(ck["commit_order"]["s6_commit_id_and_original_both_listed"]),
             f"{src['M0']} checks.commit_order.s6_commit_id_and_original_both_listed")
    nums.put("aidev.check.missing", _pct(ck["commit_order"]["s6_original_commit_missing_rate"]),
             f"{src['M0']} checks.commit_order.s6_original_commit_missing_rate", "S6 comments whose reviewed commit is missing")

    samples = (("first", N["M9"], src["M9"]), ("ext", N["M9x"], src["M9x"]))
    rows2 = []

    def row(text: str, cells: list[str], what: str, how: list[str], key: str | None = None, values: list | None = None) -> None:
        rows2.append(f"{text} & " + " & ".join(cells) + " \\\\")
        led.add("natural_funnel", what, " | ".join(cells), " | ".join(how))
        if key:
            for (name, _, _), v, h in zip(samples, values if values is not None else cells, how):
                if v is not None:
                    nums.put(f"s9.{name}.{key}", v, h)

    S = {name: m["summary"] for name, m, _ in samples}
    for name, m, p in samples:
        s = S[name]
        if s["comments"] != s["qualifying"] + s["excluded_judges_disagree"] + s["failed"]:
            raise ValueError(f"{p}: comments != qualifying + excluded + failed")
        if sum(s["failed_by_reason"].values()) != s["failed"]:
            raise ValueError(f"{p}: summary.failed_by_reason does not sum to summary.failed")
        if len(m["rows"]) != s["comments"]:
            raise ValueError(f"{p}: {len(m['rows'])} rows, summary.comments = {s['comments']}")
    judged = {n: S[n]["agreement"]["request_type_collapsed"]["n"] for n in S}
    if S["ext"]["judged"] != judged["ext"] or S["ext"]["comments"] - S["ext"]["failed_before_judging"] != judged["ext"]:
        raise ValueError(f"{src['M9x']}: summary.judged, failed_before_judging and the agreement population disagree")
    overcap = {}
    for name, _, p in samples:
        s = S[name]
        overcap[name] = s["comments"] - s["commits_reachable"] - s["by_fetch_status"]["clone_failed"]
    if overcap["first"] != S["first"]["by_fetch_status"]["over_cap"] or overcap["ext"] != S["ext"]["failed_by_reason"]["fetch_over_the_caps"]:
        raise ValueError("the comments without reachable commits do not split into clone refusals and over-cap repositories")
    hw = lambda f: [f"{p} summary.{f}" for _, _, p in samples]  # noqa: E731
    row("Comments screened", [_int(S[n]["comments"]) for n in S], "comments screened", hw("comments"), "comments")
    row("\\quad commits reachable (diff computable)", [_int(S[n]["commits_reachable"]) for n in S], "commits reachable",
        hw("commits_reachable"), "reachable")
    row("\\quad clone refused by the session's proxy", [_int(S[n]["by_fetch_status"]["clone_failed"]) for n in S], "clone refused",
        hw("by_fetch_status.clone_failed"), "refused")
    row("\\quad repository over the fetch cap", [_int(overcap[n]) for n in S], "over the cap, commits not reachable",
        [f"{src['M9']} summary.by_fetch_status.over_cap", f"{src['M9x']} summary.failed_by_reason.fetch_over_the_caps "
         "(= comments - commits_reachable - clone_failed)"], "overcap")
    row("Judged by both judges", [_int(judged[n]) for n in S], "judged by both judges",
        hw("agreement.request_type_collapsed.n"), "judged")
    row("\\quad on a non-empty diff", [_int(S[n]["by_diff_status"]["ok"]) for n in S], "judged on a non-empty diff",
        hw("by_diff_status.ok"), "judged.diff")
    row("Failed before judging", [_int(S[n]["comments"] - judged[n]) for n in S], "failed before judging",
        [f"{src['M9']} summary.comments - agreement.request_type_collapsed.n", f"{src['M9x']} summary.failed_before_judging"],
        "failedbefore")
    q = {n: S[n]["qualifying"] for n in S}
    cells, vals = [], []
    for n in S:
        lo, hi = wilson(q[n], S[n]["comments"])
        cells.append(f"{q[n]} ({_pct(q[n] / S[n]['comments'])}; {_pct(lo)}--{_pct(hi)})")
        vals.append(q[n])
        nums.put(f"s9.{n}.rate", _pct(q[n] / S[n]["comments"]), f"{src['M9' if n == 'first' else 'M9x']} summary.qualifying / summary.comments")
        nums.put(f"s9.{n}.wilson", f"{_pct(lo)}--{_pct(hi)}", f"Wilson 95% computed from {src['M9' if n == 'first' else 'M9x']} "
                 "summary.qualifying, summary.comments")
    rec = S["ext"]["qualifying_rate"]["of_extension_comments"]
    lo, hi = wilson(rec["k"], rec["n"])
    if (round(lo, 4), round(hi, 4)) != tuple(rec["wilson_95"]) or abs(rec["rate"] - q["ext"] / S["ext"]["comments"]) > 5e-5:
        raise ValueError(f"{src['M9x']}: the recorded qualifying_rate does not match the Wilson interval computed here")
    row("Qualifying (share of screened; Wilson 95\\%)", cells, "qualifying (share of screened; Wilson 95%)", hw("qualifying, comments"),
        "qualifying", vals)
    cells = []
    for n in S:
        k, nn = q[n], S[n]["commits_reachable"]
        lo, hi = wilson(k, nn)
        cells.append(f"{_pct(k / nn)} ({_pct(lo)}--{_pct(hi)})")
        nums.put(f"s9.{n}.rate.reachable", _pct(k / nn), f"{src['M9' if n == 'first' else 'M9x']} summary.qualifying / summary.commits_reachable")
        nums.put(f"s9.{n}.wilson.reachable", f"{_pct(lo)}--{_pct(hi)}", f"Wilson 95% computed from "
                 f"{src['M9' if n == 'first' else 'M9x']} summary.qualifying, summary.commits_reachable")
    row("\\quad share of comments with reachable commits", cells, "qualifying, share of comments with reachable commits (Wilson 95%)",
        hw("qualifying, commits_reachable"))
    jr = S["ext"]["qualifying_rate"]["of_judged_comments"]
    if jr["n"] != judged["ext"] or jr["k"] != q["ext"]:
        raise ValueError(f"{src['M9x']}: qualifying_rate.of_judged_comments does not match summary")
    nums.put("s9.ext.rate.judged", _pct(jr["rate"]), f"{src['M9x']} summary.qualifying_rate.of_judged_comments.rate")
    nums.put("s9.ext.wilson.judged", f"{_pct(jr['wilson_95'][0])}--{_pct(jr['wilson_95'][1])}",
             f"{src['M9x']} summary.qualifying_rate.of_judged_comments.wilson_95")
    led.add("natural_funnel", "extension: qualifying share of the judged comments, Wilson 95% (caption)",
            f"{jr['k']}/{jr['n']} = {jr['rate']}, {jr['wilson_95']}", f"{src['M9x']} summary.qualifying_rate.of_judged_comments")
    row("Excluded: the judges disagree", [str(S[n]["excluded_judges_disagree"]) for n in S], "excluded, judges disagree",
        hw("excluded_judges_disagree"), "disagree")
    row("Failed (one primary reason each)", [_int(S[n]["failed"]) for n in S], "failed", hw("failed"), "failed")
    for key, text, mk in S9_REASONS:
        vals = [S[n]["failed_by_reason"].get(key) for n in S]
        row(f"\\quad {text}", ["--" if v is None else _int(v) for v in vals], f"failed: {key}",
            hw(f"failed_by_reason.{key}"), f"fail.{mk}", [None if v is None else _int(v) for v in vals])
    row("Qualifying PRs / repositories", [f"{S[n]['qualifying_distinct_prs']} / {S[n]['qualifying_distinct_repositories']}" for n in S],
        "qualifying distinct PRs / repositories", hw("qualifying_distinct_prs, qualifying_distinct_repositories"))
    for n in S:
        nums.put(f"s9.{n}.prs", S[n]["qualifying_distinct_prs"], f"{src['M9' if n == 'first' else 'M9x']} summary.qualifying_distinct_prs")
        nums.put(f"s9.{n}.repos", S[n]["qualifying_distinct_repositories"],
                 f"{src['M9' if n == 'first' else 'M9x']} summary.qualifying_distinct_repositories")
    kap = {}
    for n in S:
        ag = S[n]["agreement"]
        kap[n] = [ag[k]["kappa"] for k in ("request_type_collapsed", "addressed", "testable_offline")]
        for k, kk in zip(("behaviour", "addressed", "testable"), kap[n]):
            nums.put(f"s9.{n}.kappa.{k}", _r2(kk), f"{src['M9' if n == 'first' else 'M9x']} summary.agreement."
                     f"{dict(behaviour='request_type_collapsed', addressed='addressed', testable='testable_offline')[k]}.kappa")
    row("Judge $\\kappa$: behaviour or defect; addressed; testable offline",
        ["; ".join(_r2(x) for x in kap[n]) + f" (n = {judged[n]})" for n in S], "judge kappas (behaviour or defect; addressed; testable offline)",
        hw("agreement.request_type_collapsed.kappa, addressed.kappa, testable_offline.kappa"))
    sec = S["first"]["agreement"]["secondary"]["commits_reachable_only"]
    sk = [sec[k]["kappa"] for k in ("request_type_collapsed", "addressed", "testable_offline")]
    for k, kk in zip(("behaviour", "addressed", "testable"), sk):
        nums.put(f"s9.first.kappa.reachable.{k}", _r2(kk), f"{src['M9']} summary.agreement.secondary.commits_reachable_only."
                 f"{dict(behaviour='request_type_collapsed', addressed='addressed', testable='testable_offline')[k]}.kappa")
    led.add("natural_funnel", "first sample: judge kappas over the comments with reachable commits (caption)",
            f"{sk} (n = {sec['n']})", f"{src['M9']} summary.agreement.secondary.commits_reachable_only")
    rows2[-1] += "\\midrule"

    ni = N["NI"]
    tasks = ni["tasks"]
    by = {n: [t for t in tasks if t["sample"] == ("first" if n == "first" else "extension")] for n in S}
    fam = {n: sum(t["role"] == "family" for t in by[n]) for n in S}
    res = {n: sum(t["role"] == "reserve" for t in by[n]) for n in S}
    if fam["first"] != N["M9"]["summary"]["s11_families"]["families"] or fam["ext"] != N["M9x"]["summary"]["s11_families"]["families"] \
            or res["ext"] != N["M9x"]["summary"]["s11_families"]["reserves"]:
        raise ValueError(f"{src['NI']} families and reserves disagree with the S9 manifests' s11_families")
    row("Families + reserves (at most 2 per repository)", [f"{fam[n]} + {res[n]}" for n in S], "families + reserves",
        [f"{src['NI']} tasks[].sample, .role (count; = {src['M9']} summary.s11_families.families)",
         f"{src['NI']} tasks[].sample, .role (count; = {src['M9x']} summary.s11_families.families, .reserves)"])
    for n in S:
        nums.put(f"fam.{n}", fam[n], f"{src['NI']} tasks[] with sample {'first' if n == 'first' else 'extension'}, role family (count)")
        nums.put(f"fam.{n}.reserves", res[n], f"{src['NI']} tasks[] with sample {'first' if n == 'first' else 'extension'}, role reserve (count)")
    first = by["first"]
    processed = [t for t in first if (t.get("s10") or {}).get("outcome") in ("passed", "rejected")]
    passed = [t for t in processed if t["s10"]["outcome"] == "passed"]
    rejected = [t for t in processed if t["s10"]["outcome"] == "rejected"]
    if any((t.get("s10") or {}).get("outcome") in ("passed", "rejected") for t in by["ext"]):
        raise ValueError(f"{src['NI']}: an extension family has an S10 outcome; the funnel prints S10 of the extension as not run")
    cats = Counter(_category(t["s10"]["reason"], S10_REASONS, f"{src['NI']} tasks[{t['task_id']}].s10.reason") for t in rejected)
    row("S10 processed / passed / rejected", [f"{len(processed)} / {len(passed)} / {len(rejected)}",
                                              "not run"],
        "S10 processed / passed / rejected (first sample)", [f"{src['NI']} tasks[] (sample first).s10.outcome", "not run (D66, D75)"])
    nums.put("s10.first.processed", len(processed), f"{src['NI']} tasks[] (sample first) with s10.outcome passed or rejected (count)")
    nums.put("s10.first.passed", len(passed), f"{src['NI']} tasks[] (sample first) with s10.outcome passed (count)")
    nums.put("s10.first.rejected", len(rejected), f"{src['NI']} tasks[] (sample first) with s10.outcome rejected (count)")
    nums.put("s10.first.yield", _pct(len(passed) / S["first"]["comments"]), f"{src['NI']} s10 passed (count) / {src['M9']} summary.comments")
    for cat, _, mk in S10_REASONS:
        row(f"\\quad rejected: {cat}", [str(cats.get(cat, 0)), "--"], f"S10 rejected (first sample): {cat}",
            [f"{src['NI']} tasks[] (sample first, s10.outcome rejected).s10.reason, by category", "not run (D66, D75)"])
        nums.put(f"s10.first.reject.{mk}", cats.get(cat, 0), f"{src['NI']} tasks[] (sample first).s10.reason (category {cat!r}, count)")
    s11 = ni["s11_by_sample"]
    if s11["first"] != len(passed) or sum(t["s11"] for t in first) != len(passed):
        raise ValueError(f"{src['NI']}: s11_by_sample.first and the passed first-sample tasks disagree")
    row("S11 accepted for building", [str(s11["first"]), "--"], "S11 accepted (first sample)",
        [f"{src['NI']} s11_by_sample.first", "not run (D66, D75)"])
    nums.put("s11.first", s11["first"], f"{src['NI']} s11_by_sample.first")
    nums.put("s11.ids", ", ".join(t["task_id"] for t in passed), f"{src['NI']} tasks[] with s11 true (task_id)")
    exact = sum(t["fidelity"] == "exact" for t in passed)
    nums.put("s11.exact", exact, f"{src['NI']} tasks[] (s11).fidelity = exact (count)")
    nums.put("s11.approximate", len(passed) - exact, f"{src['NI']} tasks[] (s11).fidelity = approximate (count)")
    pins = [t["s10"]["pins"] for t in passed]
    nums.put("s11.pins.min", min(pins), f"{src['NI']} tasks[] (s11).s10.pins (minimum)")
    nums.put("s11.pins.max", max(pins), f"{src['NI']} tasks[] (s11).s10.pins (maximum)")
    lic = Counter(t["licence"]["aidev"] for t in passed)
    for k, v in sorted(lic.items()):
        nums.put(f"lic.{k.lower().replace('-', '').replace('.', '')}", v, f"{src['NI']} tasks[] (s11).licence.aidev = {k} (count)")
    nums.put("lic.agree", f"{sum(t['licence']['agrees'] for t in passed)}/{len(passed)}", f"{src['NI']} tasks[] (s11).licence.agrees (count)")
    nums.put("ni.rows", len(tasks), f"{src['NI']} tasks (count)")
    for k, v in sorted(ni["counts"].items()):
        nums.put(f"ni.{k.replace(' ', '')}", v, f"{src['NI']} counts.{k}")
    # Cross-checks with the rejection ledger (every reason, multi-valued).
    rl = N["RL"]["rejections"]
    ids = {n: {r["comment_id"] for r in m["rows"]} for n, m, _ in samples}
    s9rows = [r for r in rl if r.get("population") == "natural:pr-review" and r.get("stage") == "S9"]
    for n in S:
        rr = [r for r in s9rows if r.get("comment_id") in ids[n]]
        if len(rr) != S[n]["failed"]:
            raise ValueError(f"{src['RL']}: {len(rr)} S9 rows of the {n} sample, its manifest says {S[n]['failed']} failed")
        led.add("natural_funnel", f"rejection ledger cross-check, {n} sample: S9 rows; every reason (multi-valued)",
                f"{len(rr)}; {dict(sorted(Counter(x for r in rr for x in r['reasons']).items()))}",
                f"{src['RL']} rejections[] (population natural:pr-review, stage S9, comment_id in the sample)")
    s10rows = [r for r in rl if r.get("population") == "natural:pr-review" and r.get("stage") == "S10"]
    if sorted(r["task_id"] for r in s10rows) != sorted(t["task_id"] for t in rejected):
        raise ValueError(f"{src['RL']}: the S10 rows do not list the rejected tasks of {src['NI']}")
    led.add("natural_funnel", "rejection ledger cross-check: S10 rows", len(s10rows), f"{src['RL']} rejections[] (stage S10)")
    (out / "natural_funnel.tex").write_text(
        "\\begin{table}[t]\\centering\\footnotesize\n"
        "\\caption{Screening funnel of the natural PR-review arm (AIDev v5). Top: the deterministic stages S1--S8a; S1 and S2 count "
        "PRs. Without the linked-issue requirement of S8, " + _int(stages["S8'"]["count"]) + " comments would pass S8 and " +
        _int(stages["S8a'"]["count"]) + " would pass S8a. Bottom: S9 for the first sample (a random sample of the S8a comments) and for the "
        "extension (every other S8a comment, decided after the first sample's S10 yield was known, protocol \\S19), then families, "
        "S10 (replayability) and S11; the extension's S10 step was stopped at a usage limit, so its S10 and S11 were not run "
        "(decision log D66, D75). \\textbf{The S9 verdicts are model proposals of two judges, not human coding.} In the first "
        "sample the comments without reachable commits were judged without a diff and failed as not fetchable; in the extension they "
        "failed before judging. Extension, share of the judged comments: " + f"{_pct(jr['rate'])} ({_pct(jr['wilson_95'][0])}--"
        f"{_pct(jr['wilson_95'][1])}). First sample, judge $\\kappa$ over the {sec['n']} comments with reachable commits: "
        + "; ".join(_r2(x) for x in sk) + ". The S9 shares are model-judged screening yields, not prevalence.}\\label{tab:natural-funnel}\n"
        "\\begin{tabular}{llrrr}\\toprule Stage & Rule & Comments & PRs & Repositories \\\\\\midrule\n" + "\n".join(rows1) +
        "\n\\bottomrule\\end{tabular}\n\n\\medskip\n"
        "\\begin{tabular}{p{0.42\\linewidth}p{0.22\\linewidth}p{0.22\\linewidth}}\\toprule S9 to S11 & First sample & Extension "
        "\\\\\\midrule\n" + "\n".join(rows2) + "\n\\bottomrule\\end{tabular}\\end{table}\n")

    # (e2) S10 per family of the first sample
    rows = []
    for t in first:
        s10 = t.get("s10") or {}
        bt = s10.get("base_tests")
        out_ = s10.get("outcome", "not built")
        reason = _category(s10["reason"], S10_REASONS, f"{src['NI']} tasks[{t['task_id']}].s10.reason") if out_ == "rejected" else "--"
        reason = S10_SHORT.get(reason, reason)
        fid = t.get("fidelity") or "--"
        if fid == "approximate":
            fid = f"approx.\\ ({t['approximations']})"
        licence = t.get("licence") or {}
        lic_txt = "--" if not licence else tex(licence["aidev"]) + ("" if licence["agrees"] else "$^{\\dagger}$")
        cells = [tex(t["task_id"]), tex(t["role"]), fid, lic_txt, "--" if s10.get("pins") is None else str(s10["pins"]),
                 "--" if s10.get("base_test_subset") is None else str(s10["base_test_subset"]),
                 "--" if not bt else f"{bt['passed']}/{bt['failed']}/{bt['skipped']}/{bt['error']}",
                 "yes" if s10.get("b1") == "available" else "--", tex(out_), reason, "yes" if t["s11"] else "--"]
        rows.append(" & ".join(cells) + " \\\\")
        led.add("natural_s10", f"{t['task_id']}: role; fidelity (approximations); licence (agrees); pins; subset files; base tests "
                "passed/failed/skipped/error; B1; S10 outcome; reason category; S11", "; ".join(cells[1:]),
                f"{src['NI']} tasks[{t['task_id']}] (role, fidelity, approximations, licence, s10.pins, s10.base_test_subset, "
                "s10.base_tests, s10.b1, s10.outcome, s10.reason, s11)")
    n_ext = len(by["ext"])
    ext_ids = sorted(t["task_id"] for t in by["ext"])
    (out / "natural_s10.tex").write_text(table(
        f"Stage S10 (replayability) of the first sample's {fam['first']} families and {res['first']} reserves, from the committed task "
        "index. Fidelity: exact, or approximate with the number of approximations. Licence: the source repository's licence in AIDev; "
        "$^{\\dagger}$: the LICENSE file at the base disagrees. Pins: the pinned dependency closure. Subset: test files in the base-test "
        "subset; base tests at the base: passed/failed/skipped/error. B1: the repository-test verifier is available. Reason: the S10 "
        "rejection category of the funnel table (no dependency closure: no resolvable dependency closure; fetch over the cap: fetch "
        "over the repository cap). Reserves are built "
        f"only to replace a rejected family of their repository. The {n_ext} families and reserves of the S9 extension "
        f"({tex(ext_ids[0])} to {tex(ext_ids[-1])}) have no S10 outcome, {EXT_S10}.", "tab:natural-s10", "llllrrrlllc",
        "Task & Role & Fidelity & Licence & Pins & Subset & Base tests & B1 & S10 & Reason & S11", rows,
        size="\\scriptsize\\setlength{\\tabcolsep}{4pt}"))
    nums.put("ni.ext.rows", n_ext, f"{src['NI']} tasks[] with sample extension (count)")
    nums.put("ni.ext.first", tex(ext_ids[0]), f"{src['NI']} tasks[] with sample extension (first task_id)")
    nums.put("ni.ext.last", tex(ext_ids[-1]), f"{src['NI']} tasks[] with sample extension (last task_id)")

    # (e3) the Trace Commons screen
    tc = N["TC"]
    tcr = [r for r in N["RL"]["rejections"] if r.get("population") == "natural:chat"]
    by_id = {r["source_id"]: r for r in tc}
    if len(tcr) != len(tc) or any(by_id.get(r["source_id"], {}).get("rejection_reasons") != r["reasons"] for r in tcr):
        raise ValueError(f"{src['RL']} natural:chat rows and {src['TC']} rejection_reasons disagree")
    elig = Counter(r["eligibility"] for r in tc)
    cat_sessions: Counter = Counter()
    detail: dict[str, Counter] = {}
    for r in tc:
        seen = set()
        for x in r["rejection_reasons"]:
            cat = _category(x, TC_REASONS, f"{src['TC']} {r['record_id']}")
            if cat in ("no recoverable base commit", "unsuitable task"):
                det = x.split("(", 1)[1].rstrip(")") if cat == "no recoverable base commit" else x.split(":", 1)[1].strip()
                detail.setdefault(cat, Counter())[det] += 1
            seen.add(cat)
        cat_sessions.update(seen)
    rows = []
    for cat, _, mk in TC_REASONS:
        rows.append(f"{tex(cat)} & {cat_sessions.get(cat, 0)} \\\\")
        led.add("trace_commons", f"sessions with a reason of category {cat!r}", cat_sessions.get(cat, 0),
                f"{src['TC']} [].rejection_reasons (= {src['RL']} natural:chat rows reasons), by category, each session once")
        nums.put(f"tc.{mk}", cat_sessions.get(cat, 0), f"{src['TC']} [].rejection_reasons (category {cat!r}, sessions)")
        for det, v in sorted(detail.get(cat, {}).items(), key=lambda kv: (-kv[1], kv[0])):
            shown = f"\\texttt{{{tex(det)}}}" if cat == "no recoverable base commit" else tex(det)
            rows.append(f"\\quad {shown} & {v} \\\\")
            led.add("trace_commons", f"{cat}: {det}", v, f"{src['TC']} [].rejection_reasons")
    nums.put("tc.screened", len(tc), f"{src['TC']} (records)")
    nums.put("tc.rejected", elig.get("rejected", 0), f"{src['TC']} [].eligibility = rejected (count)")
    led.add("trace_commons", "sessions screened; eligibility", f"{len(tc)}; {dict(elig)}", f"{src['TC']} [].eligibility")
    (out / "trace_commons.tex").write_text(table(
        f"The Trace Commons screen (population natural:chat): {len(tc)} donated sessions screened, {elig.get('rejected', 0)} rejected, "
        f"{elig.get('eligible', 0)} eligible. Reasons are multi-valued; each session counts once per category. Indented rows: "
        "sessions per recorded detail; a session can carry several details of one category, so these rows can sum to more than "
        "the category. No task was built from this source.", "tab:trace-commons", "lr", "Rejection reason & Sessions", rows,
        size="\\footnotesize"))


# -- a natural run in case-study mode (protocol §19.6, §20.3) ----------------------------------------------------------
# Every cell of these tables is a ledger entry "<row> | <family> = <cell>" whose source names the analysis.json fields it
# is made from, each as "<dot path>=<its JSON value>" ("absent" for a field the analysis does not hold), so that a reader
# can check each cell against its fields. Every field names one family: nothing is pooled over the families.

NR_CONDITIONS = [*ORDER, "diff_derived"]  # C1-C4, B2, B1 in the paper's order, then B3, the natural arm's secondary arm
NR_SECONDARY = ("diff_derived",)  # protocol §15.6: B3 is reported apart from the primary conditions
NR_SHORT = {**SHORT, "diff_derived": "B3"}
NR_TEX = {**COND_TEX, "diff_derived": "B3 diff-derived (secondary)"}
NR_DIR = "natural_run"  # paper/generated/natural_run/ and paper/evidence_ledger_natural_run.md
# The end of every natural-run caption: the case studies' caveats are stated once, at the head of the natural section
# (paper/sections/natural.tex, whose own table carries the same marker; restructure plan, part 7).
NR_MARKER = "$^{\\ddagger}$Natural case study; caveats in Section~\\ref{sec:natural-cases}."
ABSENT = object()  # a field the analysis does not hold (written "absent" in the ledger)


class Refused(SystemExit):
    """An analysis that --natural-run does not report: not a natural run's, not in case-study mode (protocol §19.6,
    §20.3), or made before §20.3's size rule was implemented. Raised before any output is replaced, so every file is left
    as it was; the message says why (exit status 1)."""


def _shown(p: Path) -> str:
    """How the outputs name a run directory: relative to the repository if it lies in it, else by its name alone, so
    that no local path is written."""
    p = p.resolve()
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name


def _get(doc: dict, path: str) -> object:
    """The value at a dot path of ``doc`` (keys hold no dot), or :data:`ABSENT`."""
    x: object = doc
    for k in path.split("."):
        if not isinstance(x, dict) or k not in x:
            return ABSENT
        x = x[k]
    return x


def _jv(v: object) -> str:
    return "absent" if v is ABSENT else json.dumps(v, sort_keys=True, ensure_ascii=False)


def _num(v: object) -> str:
    """A recorded count or time in a cell: an integer with thousands separators (a time rounded to the second); n/a for
    a value recorded as null; -- for a field the analysis does not hold."""
    if v is ABSENT:
        return "--"
    if v is None:
        return "n/a"
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError(f"not a count or a time: {v!r}")
    return _int(round(v))


def _words(code: str) -> str:
    return tex(code.replace("_", " "))


class NRTable:
    """One table of the natural run: rows of one cell per family, each cell a ledger entry with its fields. A ``ragged``
    table has wrapping columns (:func:`_nr_columns`): each cell starts with :data:`RAGGED` (``\\raggedright``, and
    ``\\hspace{0pt}`` so that its first word can be hyphenated), so each row ends with ``\\tabularnewline`` (``\\\\`` would
    end a line of the cell's paragraph); the ledger holds the cell's text without it."""

    RAGGED = "\\raggedright\\hspace{0pt}"

    def __init__(self, R: dict, led: SectionLedger, nums: Numbers, name: str, ragged: bool = False) -> None:
        self.R, self.led, self.nums, self.name, self.ragged, self.rows = R, led, nums, name, ragged, []

    def fields(self, *paths: str) -> list[tuple[str, object]]:
        return [(p, _get(self.R["a"], p)) for p in paths]

    def src(self, fields: list[tuple[str, object]], file: str | None = None) -> str:
        return f"{file or self.R['src']} " + "; ".join(f"{p}={_jv(v)}" for p, v in fields)

    def row(self, label: str, cells: list[tuple[str, list]], last_of_group: bool = False) -> None:
        """A row: its label and, per family in the run's order, its cell text and the fields it is made from."""
        for t, (text, fields) in zip(self.R["fams"], cells):
            self.led.add(self.name, f"{label} | {t}", text, self.src(fields))
        r = self.RAGGED if self.ragged else ""
        self.rows.append(" & ".join(r + x for x in (label, *(text for text, _ in cells)))
                         + (" \\tabularnewline" if self.ragged else " \\\\") + ("\\midrule" if last_of_group else ""))

    def put(self, key: str, value: object, fields: list[tuple[str, object]], what: str = "") -> None:
        self.nums.put(key, value, self.src(fields), what)

    def caption_value(self, what: str, value: object, fields: list[tuple[str, object]], file: str | None = None) -> str:
        """A number or id that a caption states, as a ledger entry ``caption | <what>``; returns it as the caption shows it."""
        self.led.add(self.name, f"caption | {what}", value, self.src(fields, file))
        return str(value)


def natural_run_inputs(run: Path) -> dict:
    """Read a natural run's analysis.json and its manifest.json (the run's id, times, code revision, repeats, pilot flag and
    invocations) and check what the tables take for granted. Refused (:class:`Refused`): an analysis that is not a natural
    run's; one whose size rule counted the committed index over both samples, as analyses made before protocol §20.3 was
    implemented do (no ``meta.case_study.accepted_in_run``); one outside case-study mode, whose tables are §15.7's (pooled
    rates, intervals, sign-flip p-values) and not this mode's; and one with no ``labels.<task>.d19`` for a family (D19's
    labels with the reason category of each ambiguous candidate, analysis.D19_RULE), which analyses made before it was
    carried lack. D19's counts must equal the label block's own (``labels.<task>.counts``), since the tables say that each
    label is D19's proposal. ``own_revisions``: the run's and its invocations' code revisions, which name commits of the
    study's repository, for the privacy check's digit-run rule (:func:`_check_private`)."""
    shown = _shown(run)
    src, msrc = f"{shown}/analysis.json", f"{shown}/manifest.json"
    raw, mraw = (run / "analysis.json").read_bytes(), (run / "manifest.json").read_bytes()
    a, m = json.loads(raw), json.loads(mraw)
    meta = a.get("meta") if isinstance(a.get("meta"), dict) else {}
    cs, nat = meta.get("case_study"), a.get("natural")
    if not isinstance(nat, dict) or not isinstance(cs, dict):
        raise Refused(f"--natural-run {shown}: refused: {src} is not the analysis of a natural PR-review run (it has no natural "
                      "block and no meta.case_study); this mode writes the case-study tables of a natural run only")
    if "accepted_in_run" not in cs:
        raise Refused(f"--natural-run {shown}: refused: {src} applies the size rule to the committed index's accepted tasks over "
                      "both samples (meta.case_study has no accepted_in_run), the rule that protocol §20.3 replaced: each run is "
                      "reported on its own. Analyse the run again (`tracecontract analyze`)")
    if cs.get("applies") is not True:
        raise Refused(f"--natural-run {shown}: refused: the analysis is not in case-study mode ({cs.get('why')}). Outside it "
                      f"(the run grades {cs.get('threshold')} or more accepted tasks of its own, protocol §20.3) protocol §15.6 "
                      "and §15.7 apply in full, with pooled rates, intervals and sign-flip p-values; that mode's tables are not "
                      "this mode's, which writes the per-family case-study tables of §19.6 only")
    if a.get("conditions") or a.get("comparisons"):
        raise ValueError(f"{src}: case-study mode leaves conditions and comparisons empty, yet they hold pooled values")
    if "automated pilot" not in meta.get("label_policy", ""):
        raise ValueError(f"{src}: label policy {meta.get('label_policy')!r}; the captions say every label is a model proposal")
    fams = list(nat["tasks"])
    for t in fams:
        if nat["families"][t]["family_id"] != t:
            raise ValueError(f"{src}: natural.families.{t}.family_id is {nat['families'][t]['family_id']!r}; the tables name "
                             "each family by its task, one task per family")
    prim, sec = a["per_family"], (a.get("secondary") or {}).get("per_family", {})
    if set(prim) - set(ORDER) or set(sec) - set(NR_SECONDARY):
        raise ValueError(f"{src}: primary conditions {sorted(prim)} and secondary {sorted(sec)}; expected C1-C4, B2 and B1, "
                         "with B3 secondary")
    for c, pf in (*prim.items(), *sec.items()):
        if set(pf) - set(fams):
            raise ValueError(f"{src}: per-family rates of {c} for {sorted(set(pf) - set(fams))}, which are not the run's families")
    labels = a.get("labels") if isinstance(a.get("labels"), dict) else {}
    for t in fams:
        block = labels.get(t) if isinstance(labels.get(t), dict) else {}
        d19 = block.get("d19")
        if not isinstance(d19, dict) or not isinstance(d19.get("ambiguous_reasons"), dict):
            raise Refused(f"--natural-run {shown}: refused: {src} has no labels.{t}.d19 (D19's labels of the family's held-out "
                          "candidates, with the reason category of each ambiguous one), which `tracecontract analyze` writes "
                          "for a natural run (analysis.D19_RULE). Analyse the run again (`tracecontract analyze`)")
        counts = block.get("counts") if isinstance(block.get("counts"), dict) else {}
        proposals = {v: d19.get(v) for v in ("valid", "invalid", "ambiguous", "unlabeled")}
        if any(counts.get(v, 0) != n for v, n in proposals.items()):
            raise ValueError(f"{src}: labels.{t}.d19 counts D19's proposals and labels.{t}.counts the labels the analysis uses, "
                             f"and they differ ({proposals} against {counts}): a label other than D19's is in use, and the "
                             "tables say each is D19's model proposal")
        ambiguous = sorted(r.get("candidate") for r in block.get("candidates", []) if r.get("proposed") == "ambiguous")
        if sorted(d19["ambiguous_reasons"]) != ambiguous:
            raise ValueError(f"{src}: labels.{t}.d19.ambiguous_reasons names {sorted(d19['ambiguous_reasons'])}, while the "
                             f"family's label rows label {ambiguous} ambiguous")
    # The study repository's commits that the run's manifest names (the run's and each invocation's code revision): the
    # privacy check's digit-run rule skips them (_check_private), and nothing else.
    invocations = m.get("invocations") if isinstance(m.get("invocations"), list) else []
    revisions = [m.get("code_revision"), *(x.get("code_revision") for x in invocations if isinstance(x, dict))]
    own = tuple(sorted({form for r in revisions if isinstance(r, str) and r.removesuffix("+dirty")
                        for form in (r, r.removesuffix("+dirty"), r.removesuffix("+dirty")[:7])}))
    return {"a": a, "m": m, "fams": fams, "run_id": m["run_id"], "src": src, "msrc": msrc, "own_revisions": own,
            "sha256": {src: hashlib.sha256(raw).hexdigest(), msrc: hashlib.sha256(mraw).hexdigest()}}


def _nr_case_study(T: NRTable) -> str:
    """The case-study sentence of every caption, with the size rule's numbers as ledger entries: the run's own accepted
    tasks (protocol §20.3: each run is reported on its own), never the committed index's count over both samples."""
    cs = T.R["a"]["meta"]["case_study"]
    thr = T.caption_value("size threshold", _num(cs["threshold"]), T.fields("meta.case_study.threshold"))
    run = T.caption_value("run", tex(T.R["run_id"]), [("run_id", T.R["run_id"])], T.R["msrc"])
    if cs.get("accepted_in_run") is None:  # the analysis could not read the committed index (meta.case_study.why)
        T.led.add(T.name, "caption | the run's accepted tasks", "not readable", T.src(T.fields("meta.case_study.accepted_in_run")))
        size = f"the committed index cannot be read, so nothing shows that the run grades {thr} accepted tasks"
    else:
        acc = T.caption_value("the run's accepted tasks", _num(cs["accepted_in_run"]), T.fields("meta.case_study.accepted_in_run"))
        size = (f"the run grades {acc} accepted tasks of its own (its families accepted in the committed index), fewer than "
                f"{thr}, and each run is reported on its own")
    return (f"Run \\texttt{{{run}}} in case-study mode, as exploratory case studies (protocol \\S19.6, \\S20.3): {size}, so "
            "every number is per family. Nothing is pooled over the families: no pooled rate, no interval and no p-value.")


def _nr_columns(fams: list[str], first: float = 0.25, sep: float = 0.027) -> str:
    """A label column and one wrapping column per family (plain p columns: main.tex loads no array package), together no
    wider than the line; ``sep``: the column separation per column as a share of the line (2 x 6pt, the default, is
    about 0.027 of a 6.5in line; 2 x 4pt about 0.018, 2 x 3pt about 0.013)."""
    w = min(0.15, (1 - first - sep * (len(fams) + 1)) / len(fams))
    return f"p{{{first}\\linewidth}}" + f"p{{{w:.3f}\\linewidth}}" * len(fams)


def _nr_layout(fams: list[str], small: bool = False) -> tuple[str, str]:
    """The size command and column spec of a natural-run table: up to six families (natural-pr-v1 has six) in the given
    size, more (case-study mode allows up to nine) in the smallest, so that a word of a cell still fits its column."""
    if len(fams) > 6:
        return "\\scriptsize\\setlength{\\tabcolsep}{3pt}", _nr_columns(fams, 0.18, 0.013)
    if small:
        return "\\scriptsize\\setlength{\\tabcolsep}{4pt}", _nr_columns(fams, 0.2, 0.018)
    return "\\footnotesize", _nr_columns(fams)


def natural_run_fa_fr_table(R: dict, led: SectionLedger, nums: Numbers, out: Path) -> None:
    """(1) False acceptance and false rejection per family and condition under D19, B3 apart; the oracle-gated view's
    drops are marked."""
    a, fams = R["a"], R["fams"]
    T = NRTable(R, led, nums, "natural_run_fa_fr", ragged=True)
    prim, sec = a["per_family"], (a.get("secondary") or {}).get("per_family", {})
    og = a["oracle_gated"]["conditions"]
    graded = [c for c in NR_CONDITIONS if c in prim or c in sec]
    for i, c in enumerate(graded):
        base, sh = ("secondary.per_family" if c in NR_SECONDARY else "per_family"), NR_SHORT[c].lower()
        if c not in og:
            raise ValueError(f"{R['src']}: oracle_gated.conditions has no {c}")
        cells = []
        for t in fams:
            if _get(a, f"{base}.{c}.{t}") is ABSENT:
                cells.append(("--", T.fields(f"{base}.{c}.{t}")))
                continue
            fs = T.fields(*(f"{base}.{c}.{t}.{k}" for k in ("fa_num", "fa_den", "fr_num", "fr_den")),
                          f"oracle_gated.conditions.{c}.dropped.{t}")
            fa_num, fa_den, fr_num, fr_den, dropped = (v for _, v in fs)
            text = f"{_frac(fa_num, fa_den)} $\\cdot$ {_frac(fr_num, fr_den)}" + ("" if dropped is ABSENT else "$^{\\dagger}$")
            T.put(f"{sh}.{_fk(t)}.fa", _frac(fa_num, fa_den), fs[:2], "accepted/invalid under D19")
            T.put(f"{sh}.{_fk(t)}.fr", _frac(fr_num, fr_den), fs[2:4], "rejected/valid under D19")
            T.put(f"og.{sh}.{_fk(t)}", "kept" if dropped is ABSENT else "dropped", fs[4:], "the oracle-gated view")
            cells.append((text, fs))
        primary_ends = c not in NR_SECONDARY and i + 1 < len(graded) and graded[i + 1] in NR_SECONDARY
        T.row(tex(NR_TEX[c]), cells, last_of_group=primary_ends or i + 1 == len(graded))
    _nr_pairs_rows(T)
    absent = [NR_SHORT[c] for c in NR_CONDITIONS if c not in graded]
    caption = (f"False acceptance $\\cdot$ false rejection per family and condition, as accepted/invalid $\\cdot$ "
               "rejected/valid, under D19's model-proposed labels, each distinct graded patch once; the reference solution and "
               "the no-op are excluded. A rejection is any outcome other than a pass, so an infrastructure outcome "
               "(environment failure, verifier error or timeout) and an unresolved pair (repeats that disagree, protocol "
               "\\S15.3) count as rejections. Below the conditions: the family's pairs graded in the run (every verifier and "
               "candidate, label support included), those unresolved, and those that ended in an infrastructure outcome. "
               f"{NO_HUMAN} {_nr_case_study(T)} B3 (diff-derived) is a secondary arm (protocol \\S15.6). n/a: "
               "the family has no unit of that kind under D19. --: the run did not grade the condition for the family, or the "
               "analysis does not hold the value. none: no such pair. "
               "$^{\\dagger}$: the verifier does not pass the family's reference solution in the run, so the secondary "
               "oracle-gated view (protocol \\S15.7) drops the cell and counts its units as lost yield."
               + (f" Not graded in this run: {', '.join(absent)}." if absent else "") + " " + NR_MARKER)
    # Sized as the fresh-v1 tables are; a cell wraps only when it does not fit (six families of two-digit counts fit).
    size, spec = _nr_layout(fams, small=True)
    head = "Condition & " + " & ".join(tex(t) for t in fams)
    (out / "natural_run_fa_fr.tex").write_text(table(caption, "tab:nr-fa-fr", spec, head, T.rows, size=size))


def _nr_pairs_rows(T: NRTable) -> None:
    """Each family's pairs in the run (every verifier and candidate graded, label support included): how many, how many
    are unresolved and how many ended in an infrastructure outcome, by outcome; a rejection in the tables either way."""
    graded, infra = [], []
    for t in T.R["fams"]:
        fk, p = _fk(t), f"natural.reliability.families.{t}"
        fs = T.fields(f"{p}.pairs", f"{p}.unresolved")
        T.put(f"pairs.{fk}", _num(fs[0][1]), fs[:1], "the family's graded pairs in the run")
        T.put(f"pairs.{fk}.unresolved", _num(fs[1][1]), fs[1:], "pairs whose repeats disagree (unresolved, a rejection)")
        graded.append((", ".join(_num(v) for _, v in fs), fs))
        fs = T.fields(f"{p}.infrastructure")
        v = fs[0][1]
        text = "--" if v is ABSENT else ", ".join(f"{_num(n)} {_words(k)}" for k, n in v.items()) or "none"
        if v is not ABSENT:
            T.put(f"pairs.{fk}.infrastructure", text, fs, "pairs that ended in an infrastructure outcome (a rejection)")
        infra.append((text, fs))
    T.row("The run's pairs: graded, unresolved", graded)
    T.row("The run's pairs ending in an infrastructure outcome", infra)


def natural_run_source_table(R: dict, led: SectionLedger, nums: Numbers, out: Path) -> None:
    """(2) Which conditions accept each family's pre-review state under the source-evidence label, and that state's
    other labels."""
    a, fams = R["a"], R["fams"]
    se = a["source_evidence"]
    T = NRTable(R, led, nums, "natural_run_source_evidence", ragged=True)
    pre: dict[str, str] = {}
    for t in fams:
        keys = [k for k, x in se["pre_review"].items() if x["family_id"] == t]
        if len(keys) != 1:
            raise ValueError(f"{R['src']}: source_evidence.pre_review holds {len(keys)} pre-review states of {t}; the table "
                             "shows one per family")
        pre[t] = keys[0]
    views = {**{c: "source_evidence.per_family" for c in se["per_family"]},
             **{c: "source_evidence.secondary_per_family" for c in se.get("secondary_per_family", {})}}
    for c, base in views.items():
        for t, d in _get(a, f"{base}.{c}").items():
            if d["valid"]["n"]:
                raise ValueError(f"{R['src']}: {base}.{c}.{t}.valid.n = {d['valid']['n']}; a source-evidence label is invalid "
                                 "with respect to the correction (protocol §15.6)")
    graded = [c for c in NR_CONDITIONS if c in views]
    for i, c in enumerate(graded):
        base, sh, cells = views[c], NR_SHORT[c].lower(), []
        for t in fams:
            if _get(a, f"{base}.{c}.{t}") is ABSENT:
                cells.append(("--", T.fields(f"{base}.{c}.{t}")))
                continue
            fs = T.fields(f"{base}.{c}.{t}.invalid.accepted", f"{base}.{c}.{t}.invalid.n",
                          f"source_evidence.pre_review.{pre[t]}.outcomes.{c}")
            acc, n, outcome = (v for _, v in fs)
            text = "--" if not n else ("accepted" if acc else "rejected") if n == 1 else f"{acc}/{n} accepted"
            if text == "rejected" and isinstance(outcome, str) and outcome != "task_failure":
                text += f" ({_words(outcome)})"  # an infrastructure outcome or an unresolved pair, a rejection (§6, §15.3)
            if n:
                T.put(f"se.{sh}.{_fk(t)}", text, fs, "the pre-review state under the source-evidence label")
            cells.append((text, fs))
        last = i + 1 == len(graded) or (c not in NR_SECONDARY and graded[i + 1] in NR_SECONDARY)
        T.row(tex(NR_TEX[c]), cells, last_of_group=last)
    cells_d19, cells_il, cells_ref = [], [], []
    for t in fams:
        p = f"source_evidence.pre_review.{pre[t]}"
        fs = T.fields(f"{p}.d19")
        d19 = fs[0][1]
        cells_d19.append(("none" if d19 in (None, ABSENT) else tex(d19), fs))
        T.put(f"pre.{_fk(t)}.d19", cells_d19[-1][0], fs, "D19's label of the pre-review state")
        fs = T.fields(f"{p}.independent_label", f"{p}.independent_label_outcome", f"{p}.independent_label_left_out")
        label, outcome, left = (v for _, v in fs)
        text = ("left out" if left is True else "not graded" if outcome in (None, ABSENT) else
                f"{tex(label) if isinstance(label, str) else 'none'} ({_words(outcome)})")
        cells_il.append((text, fs))
        T.put(f"pre.{_fk(t)}.il", text, fs, "the second labeling of the pre-review state (the labeler's outcome)")
        fs = T.fields(f"{p}.reference_checks_outcome")
        out_ = fs[0][1]
        cells_ref.append(("not graded" if out_ in (None, ABSENT) else _words(out_), fs))
        T.put(f"pre.{_fk(t)}.refchecks", cells_ref[-1][0], fs, "the reference checks' outcome on the pre-review state")
    T.row("Its D19 label", cells_d19)
    T.row("Its second label (the labeler's outcome)", cells_il)
    T.row("The reference checks' outcome on it", cells_ref)
    caption = ("Acceptance of each family's pre-review state, the tree the reviewer commented on before the correction, by "
               "condition, under the source-evidence label: invalid with respect to the correction, on the strength of the "
               "reviewer's request, the addressing commit and the agreement of both S9 judges (protocol \\S15.6), so an "
               "accepted state is a false acceptance under this labeling. \\textbf{Source evidence, not a human label}, reported "
               "apart from D19; D19's labels and the second labeling are model proposals, and no human labels exist. "
               f"{_nr_case_study(T)} Below the conditions: the same state's D19 label (ambiguous where its reference "
               "checks pass it, \\S15.6), its label in the second labeling with the independent labeler's outcome (a pass on a "
               "pre-review state is ambiguous, decision log D64; left out: the family's labeler is not usable), and the "
               "reference checks' outcome on it in the run. A rejection is any outcome other than a pass: one that is not a "
               "task failure (an infrastructure outcome, or an unresolved pair whose repeats disagree, protocol \\S15.3) is "
               "named in brackets. Terms: --: the run did not grade the condition for the family; not graded: the run did not "
               "grade the state with that verifier; none: no label (no D19 proposal, or no label in the second labeling). "
               + NR_MARKER)
    size, spec = _nr_layout(fams)
    head = "Condition & " + " & ".join(tex(t) for t in fams)
    (out / "natural_run_source_evidence.tex").write_text(table(caption, "tab:nr-source", spec, head, T.rows, size=size))


def natural_run_labeler_table(R: dict, led: SectionLedger, nums: Numbers, out: Path) -> None:
    """(3) The second labeling per family: the labeler's status, the labels, and the agreement with D19 apart for the
    pre-review states and the held-out pool, with the pool's generation order."""
    a, fams = R["a"], R["fams"]
    if "independent_labeling" not in a:
        raise ValueError(f"{R['src']}: the run did not grade the independent labeler, whose second labeling protocol §15.6 "
                         "reports")
    T = NRTable(R, led, nums, "natural_run_labeler", ragged=True)
    rows: dict[str, list] = {k: [] for k in ("status", "second", "valid", "invalid", "ambiguous", "not_graded", "pre", "pool",
                                             "order")}
    for t in fams:
        fk, fam = _fk(t), f"natural.families.{t}.labeler"
        fs = T.fields(f"{fam}.status", f"{fam}.round", f"{fam}.usable")
        status, rnd, _ = (v for _, v in fs)
        text = ("not recorded" if status in (None, ABSENT) else tex(status)) + ("" if rnd is ABSENT else f" ({_num(rnd)})")
        rows["status"].append((text, fs))
        T.put(f"il.{fk}.status", "not recorded" if status in (None, ABSENT) else tex(status), fs[:1], "the labeler's status record")
        if rnd is not ABSENT:
            T.put(f"il.{fk}.round", _num(rnd), fs[1:2], "the labeler's round: one as written, two after its revision")
        fs = T.fields("independent_labeling.tasks", f"independent_labeling.left_out.{t}.why")
        text = "left out" if fs[1][1] is not ABSENT else "graded" if t in fs[0][1] else "not graded"
        rows["second"].append((text, fs))
        T.put(f"il.{fk}.second", text, fs, "in the second labeling")
        for v in ("valid", "invalid", "ambiguous", "not_graded"):
            fs = T.fields(f"independent_labeling.labels_per_family.{t}.{v}")
            rows[v].append((_num(fs[0][1]), fs))
            T.put(f"il.{fk}.{v.replace('_', '')}", _num(fs[0][1]), fs, f"held-out candidates labelled {v.replace('_', ' ')}")
        g = f"independent_labeling.agreement.per_family.{t}.natural"
        for part in ("existed_before_labeler", "generated_after_labeler"):
            if _get(a, f"{g}.{part}") is ABSENT:
                raise ValueError(f"{R['src']}: {g}.{part} is not in the analysis; the table shows the agreement of every "
                                 "family, apart for the pre-review states and the held-out pool")
        for key, part in (("pre", "existed_before_labeler"), ("pool", "generated_after_labeler")):
            fs = T.fields(f"{g}.{part}.agree", f"{g}.{part}.n_decided_by_both", f"{g}.{part}.n_units")
            agree, both, units = (v for _, v in fs)
            rows[key].append((f"{_num(agree)}/{_num(both)} ({_num(units)})", fs))
            T.put(f"il.{fk}.{key}.agree", _num(agree), fs[:1], "units D19 and the labeler label alike")
            T.put(f"il.{fk}.{key}.decided", _num(both), fs[1:2], "units both label valid or invalid")
            T.put(f"il.{fk}.{key}.units", _num(units), fs[2:], "distinct graded patches")
        o = f"{g}.generated_after_labeler.order"
        fs = T.fields(f"{o}.after", f"{o}.candidates", f"{o}.not_after", f"{o}.not_shown")
        after, cands, not_after, not_shown = (v for _, v in fs)
        if any(v is ABSENT for v in (after, cands, not_after, not_shown)):
            raise ValueError(f"{R['src']}: {o} does not record the pool's generation order (after, candidates, not_after, "
                             "not_shown)")
        text = (f"{_num(after)} of {_num(cands)}" + (f"; not after it {len(not_after)}" if not_after else "")
                + (f"; not shown {len(not_shown)}" if not_shown else ""))
        rows["order"].append((text, fs))
        T.put(f"il.{fk}.pool.after", _num(after), fs[:1], "pool candidates generated after the labeler was frozen")
        T.put(f"il.{fk}.pool.candidates", _num(cands), fs[1:2], "pool candidates")
    T.row("Labeler status (round)", rows["status"])
    T.row("In the second labeling", rows["second"], last_of_group=True)
    for v in ("valid", "invalid", "ambiguous"):
        T.row(f"Held-out candidates labelled {v}", rows[v])
    T.row("Held-out candidates not graded", rows["not_graded"], last_of_group=True)
    T.row("Agreement with D19, pre-review states", rows["pre"])
    T.row("Agreement with D19, held-out pool", rows["pool"])
    T.row("Pool generated after the labeler was frozen", rows["order"])
    caption = ("The second labeling per family: the independent labeler (protocol \\S15.5), a model proposal like D19. "
               "\\textbf{Both labelings are model proposals; no human labels exist.} Status: "
               "the labeler's status record, with its round (one as written, two after its one revision); a labeler that is not "
               "usable is left out of the second labeling and reported. Labels: the family's held-out candidates under the "
               "second labeling (not graded: left out, or not graded by the labeler). Agreement with D19, each distinct graded "
               "patch once: agree/both decide (units), where both decide a unit both label valid or invalid; apart for the "
               "pre-review states, which existed before the labeler was written, and for the held-out pool. The pool's order: "
               "how many of its candidates the generation records show to have been generated after the labeler was frozen, "
               "of all, with those not after it and those whose order is not shown (no frozen time, or no generation start). "
               "Terms: not recorded: no status record; graded: in the second labeling; left out: its labeler is not usable; "
               "--: not in the analysis; n/a: recorded as null. " + _nr_case_study(T)
               + " No agreement is pooled over the families. " + NR_MARKER)
    size, spec = _nr_layout(fams)
    head = "Second labeling & " + " & ".join(tex(t) for t in fams)
    (out / "natural_run_labeler.tex").write_text(table(caption, "tab:nr-labeler", spec, head, T.rows, size=size))


def _audit_cell(revisions: object, passed: object, codes: object) -> str:
    if revisions is ABSENT:
        return "--"
    if passed is True:
        return f"{_num(revisions)}, passed"
    named = "codes not recorded" if codes is None else ", ".join(_words(c) for c in codes)
    return f"{_num(revisions)}, failed" + (f" ({named})" if named else "")


def natural_run_construction_table(R: dict, led: SectionLedger, nums: Numbers, out: Path) -> None:
    """(4) Per-family construction facts from the analysis's flags, construction, reliability and cost blocks."""
    fams = R["fams"]
    T = NRTable(R, led, nums, "natural_run_construction", ragged=True)
    lines: list[tuple[str, list, bool]] = []

    def line(label: str, make, last_of_group: bool = False) -> None:
        """A row whose cell for family ``t`` is ``make(t, fk) -> (text, fields)``; ``make`` puts the row's macros."""
        lines.append((label, [make(t, _fk(t)) for t in fams], last_of_group))

    fam = "natural.families.{t}"
    con = fam + ".construction"
    cost = "natural.cost.families.{t}"

    def sample(t, fk):
        fs = T.fields(fam.format(t=t) + ".sample")
        text = "--" if fs[0][1] in (None, ABSENT) else tex(fs[0][1])
        T.put(f"sample.{fk}", text, fs, "the family's S9 sample")
        return text, fs

    def reference(t, fk):
        p = con.format(t=t) + ".contracts.reference"
        fs = T.fields(f"{p}.requirements", f"{p}.scored_active", f"{p}.at_correction")
        for (path, v), k in zip(fs, ("requirements", "scored", "correction")):
            if v is not ABSENT:
                T.put(f"ref.{fk}.{k}", _num(v), [(path, v)], "the reference contract's requirements")
        return ", ".join(_num(v) for _, v in fs), fs

    def recovered(t, fk):
        p = con.format(t=t) + ".contracts"
        fs = T.fields(f"{p}.initial_only.scored_active", f"{p}.full_session.scored_active")
        for (path, v), k in zip(fs, ("ini", "full")):
            if v is not ABSENT:
                T.put(f"{k}.{fk}.scored", _num(v), [(path, v)], "scored active requirements of the recovered contract")
        return ", ".join(_num(v) for _, v in fs), fs

    def checks(conds: list[str]):
        def make(t, fk):
            p = con.format(t=t) + ".checks"
            fs = T.fields(*(f"{p}.{c}" for c in conds))
            for (path, v), c in zip(fs, conds):
                if v is not ABSENT:
                    k = {"reference_check": "ref", "independent_label": "il"}.get(c) or NR_SHORT[c].lower()
                    T.put(f"checks.{k}.{fk}", _num(v), [(path, v)], f"scored checks of {c}")
            return ", ".join(_num(v) for _, v in fs), fs
        return make

    def audit(cond: str, short: str):
        def make(t, fk):
            p = con.format(t=t) + f".audits.{cond}"
            fs = T.fields(f"{p}.revisions", f"{p}.passed", f"{p}.last_finding_codes")
            revisions, passed, codes = (v for _, v in fs)
            if revisions is not ABSENT:
                T.put(f"audit.{short}.{fk}.revisions", _num(revisions), fs[:1], f"revisions of {short.upper()}'s audit")
                T.put(f"audit.{short}.{fk}.result", "passed" if passed is True else "failed", fs[1:2], "audit:v1")
            return _audit_cell(revisions, passed, codes), fs
        return make

    def b3(t, fk):
        p = con.format(t=t) + ".b3"
        fs = T.fields(f"{p}.available", f"{p}.taken_out")
        available, taken_out = (v for _, v in fs)
        text = ("--" if available is ABSENT else "available" if available is True else
                "taken out (no test kept)" if taken_out is True else "not registered")
        T.put(f"b3.{fk}.available", "--" if available is ABSENT else "yes" if available is True else "no", fs[:1], "B3")
        return text, fs

    def b1(t, fk):
        p = fam.format(t=t) + ".b1"
        fs = T.fields(f"{p}.available", f"{p}.n_checks")
        available, n = (v for _, v in fs)
        word = "not recorded" if available in (None, ABSENT) else "yes" if available else "no"
        T.put(f"b1.{fk}.available", word, fs[:1], "B1 by S10")
        if n not in (None, ABSENT):
            T.put(f"b1.{fk}.checks", _num(n), fs[1:], "B1's checks by S10")
        return word + ("" if n in (None, ABSENT) else f" ({_num(n)})"), fs

    def b1_norm(t, fk):
        p = fam.format(t=t) + ".b1_equals_regression_norm"
        fs = T.fields(f"{p}.equal", f"{p}.identical_files", f"{p}.b1_files", f"{p}.norm_files")
        equal, same, b1_files, norm_files = (v for _, v in fs)
        word = ("not known" if equal in (None, ABSENT) else "yes" if equal else
                "in part" if isinstance(same, int) and same > 0 else "no")
        T.put(f"b1.{fk}.norm", word, fs[:2], "B1 equals D19's regression norm: yes, in part or no")
        if word in ("yes", "in part", "no") and same is not ABSENT:  # D64 decision 3: the files B1 shares with the norm
            T.put(f"b1.{fk}.norm.files", f"{_num(same)} of {_num(b1_files)}", fs[1:3], "B1's files identical to the norm's")
            return f"{word} ({_num(same)} of {_num(b1_files)}; norm {_num(norm_files)})", fs
        return word, fs

    def refchecks(t, fk):
        p = con.format(t=t) + ".reference_checks"
        fs = T.fields(f"{p}.recorded", f"{p}.status", f"{p}.fix_rounds")
        recorded, status, rounds = (v for _, v in fs)
        if recorded is not True:  # no readable status record (or an analysis that does not say)
            word, text = "not recorded", "not recorded"
        else:  # a record whose status is neither usable nor unusable, or whose fix rounds are no integer, says so
            word = "unrecognised status" if status in (None, ABSENT) else tex(status)
            text = f"{word} ({'fix rounds not recorded' if rounds in (None, ABSENT) else _num(rounds)})"
        T.put(f"refchecks.{fk}.status", word, fs[:2], "the reference checks' status record")
        if recorded is True and rounds not in (None, ABSENT):
            T.put(f"refchecks.{fk}.rounds", _num(rounds), fs[2:], "fix rounds of the reference checks")
        return text, fs

    def refchecks_run(t, fk):
        p = f"natural.reliability.families.{t}.sanity"
        fs = T.fields(*(f"{p}.{o}.reference_check.{k}" for o in ("reference", "noop") for k in ("pass", "n")))
        rp, rn, np_, nn = (v for _, v in fs)
        text = f"{_num(rp)}/{_num(rn)}, {_num(np_)}/{_num(nn)}"
        T.put(f"refchecks.{fk}.run.reference", f"{_num(rp)}/{_num(rn)}", fs[:2], "the reference passes (the run's grading)")
        T.put(f"refchecks.{fk}.run.noop", f"{_num(np_)}/{_num(nn)}", fs[2:], "the no-op passes (the run's grading)")
        return text, fs

    def near_misses(t, fk):
        p = fam.format(t=t) + ".near_misses_on_correction"
        fs = T.fields(f"{p}.on_correction", f"{p}.near_misses")
        on, n = (v for _, v in fs)
        text = "--" if on is ABSENT else f"{len(on)} of {_num(n)}"
        if on is not ABSENT:
            T.put(f"nm.{fk}.correction", _int(len(on)), fs[:1], "held-out near misses that target a correction requirement")
            T.put(f"nm.{fk}.all", _num(n), fs[1:], "held-out near misses")
        return text, fs

    def artifacts(t, fk):
        p = cost.format(t=t)
        fs = T.fields(f"{p}.recorded", f"{p}.artifacts")
        rec, n = (v for _, v in fs)
        T.put(f"cost.{fk}.recorded", _num(rec), fs[:1], "generated artifacts with a generation record")
        T.put(f"cost.{fk}.artifacts", _num(n), fs[1:], "generated artifacts")
        return f"{_num(rec)} of {_num(n)}", fs

    def cost_of(keys: list[tuple[str, str]], what: str):
        def make(t, fk):
            fs = T.fields(*(f"{cost.format(t=t)}.{k}" for k, _ in keys))
            for (path, v), (_, mk) in zip(fs, keys):
                T.put(f"cost.{fk}.{mk}", _num(v), [(path, v)], what)
            return ", ".join(_num(v) for _, v in fs), fs
        return make


    line("Sample", sample)
    line("Reference contract: requirements, scored active, at the correction", reference)
    line("Recovered contracts, scored active: initial-only, correction-aware", recovered, True)
    line("Checks: C1, C2, C3, C4", checks(["initial_plain", "initial_audited", "full_plain", "full_audited"]))
    line("Checks: B2, B1, B3", checks(["llm_freeform", "repo_tests", "diff_derived"]))
    line("Checks: reference checks, labeler", checks(["reference_check", "independent_label"]), True)
    line("C2 audit: revisions, result", audit("initial_audited", "c2"))
    line("C4 audit: revisions, result", audit("full_audited", "c4"))
    line("B3", b3)
    line("B1 by S10: available (checks)", b1)
    line("B1 equals D19's regression norm", b1_norm, True)
    line("Reference checks: status (fix rounds)", refchecks)
    line("Reference checks in the run: reference, no-op passes", refchecks_run)
    line("Held-out near misses on the correction", near_misses, True)
    line("Generated artifacts with a generation record", artifacts)
    line("Agent turns, tool calls", cost_of([("turns", "turns"), ("tool_calls", "toolcalls")], "agent turns and tool calls"))
    line("Agent wall time (s)", cost_of([("wall_s", "wall")], "agent wall time (s)"))
    line("Grading wall time (s)", cost_of([("grading_wall_s", "grading")], "the run's grading time (s)"))
    line("S10 build time (s)", cost_of([("s10_seconds", "s10")], "S10 build time (s)"))
    for label, cells, last in lines:
        T.row(tex(label), cells, last_of_group=last)
    caption = ("Construction facts per family (decision log D64, D70), from the analysis's per-family flags, construction, "
               "reliability and cost blocks. Contracts: requirements, scored active ones and those introduced at the correction "
               "(the review comment or a reply; with none, the reference contract does not observe the correction, D64 "
               "decision 14). Checks: the scored checks of each registered verifier. Audits (audit:v1, D27): revisions and the "
               "result, with the codes of the last iteration's findings when it failed. B3: available, taken out (its per-test "
               "selection kept no test) or not registered. B1 by S10: available, with its checks. B1 equals D19's regression "
               "norm: yes, "
               "in part or no, with B1's files that are the norm's, of B1's, and the norm's count; where they are equal, wholly "
               "or in part, a D19-labelled false rejection of B1 is uninformative to that extent (D64, decision 3). Reference "
               "checks: the status record written when they were frozen, with its fix rounds, and their passes on the "
               "reference and the no-op in the run. Cost: the generation records of the family's generated artifacts, the "
               "run's grading time and the S10 build time. Terms: --: not in the analysis; n/a: recorded as null; not "
               "recorded: no record of it (codes not recorded: an audit record without its iterations; fix rounds not "
               "recorded: no integer for them); unrecognised status: a record with neither status; not known: no "
               "regression-norm overlay. " + _nr_case_study(T) + " No total is given. " + NR_MARKER)
    size, spec = _nr_layout(fams, small=True)
    head = "Fact & " + " & ".join(tex(t) for t in fams)
    (out / "natural_run_construction.tex").write_text(table(caption, "tab:nr-construction", spec, head, T.rows, size=size))


NOT_RECORDED = "not recorded"  # a macro whose field the manifest or the analysis does not hold, or holds in no usable form


def _utc(v: object) -> datetime | None:
    """``v`` as a time in UTC, when it is an ISO 8601 text with a time zone (as evaluate records the run's times)."""
    try:
        t = datetime.fromisoformat(v) if isinstance(v, str) else None
    except ValueError:
        return None
    return t.astimezone(UTC) if t is not None and t.tzinfo is not None else None


def _revision(rev: object) -> str | None:
    """A code revision as the paper names it: its first 7 characters, said to have had uncommitted changes where evaluate
    recorded ``+dirty`` (tracked files that differed from the commit); None for no revision."""
    if not isinstance(rev, str) or not rev.removesuffix("+dirty"):
        return None
    return rev.removesuffix("+dirty")[:7] + (" (with uncommitted changes)" if rev.endswith("+dirty") else "")


def _candidate_name(cid: str, task: str) -> str:
    """A family's candidate as the paper names it beside the family: without the family's id in front (``<task>-eval-nm-1``
    is eval-nm-1, as the recipe names the pool, D64)."""
    rest = cid[len(task) + 1:] if cid.startswith(task + "-") else ""
    return rest or cid


def natural_run_numbers(R: dict, led: SectionLedger, nums: Numbers) -> None:
    """The run's facts from its manifest (its times, code revision, repeats, pilot flag and invocations) and from its analysis
    (the harness versions of its results), and per family D19's labels of its held-out candidates with the reason category
    of each ambiguous one (``labels.<task>.d19``; analysis.D19_RULE): each a macro with its ledger entry, each put once."""
    m, msrc = R["m"], R["msrc"]
    T = NRTable(R, led, nums, "numbers")

    def mfields(*keys: str) -> list[tuple[str, object]]:
        return [(k, _get(m, k)) for k in keys]

    def mput(key: str, value: str, fs: list[tuple[str, object]], what: str) -> None:
        nums.put(key, value, T.src(fs, msrc), what)

    fs = mfields("started_at")
    start = _utc(fs[0][1])
    mput("run.date", NOT_RECORDED if start is None else start.strftime("%Y-%m-%d"), fs, "the run's start date, UTC")
    mput("run.started", NOT_RECORDED if start is None else start.strftime("%H:%M:%S"), fs,
         "the run's start, UTC, as its manifest records it: that of its first invocation")
    fs = mfields("finished_at")
    end = _utc(fs[0][1])
    same_day = start is not None and end is not None and end.date() == start.date()
    mput("run.finished", NOT_RECORDED if end is None else end.strftime("%H:%M:%S" if same_day else "%Y-%m-%d %H:%M:%S"), fs,
         "the run's end, UTC, with its date where that is not the start's")
    invocations = _get(m, "invocations")
    listed = invocations if isinstance(invocations, list) else []
    fs = mfields("code_revision", *(("invocations",) if isinstance(invocations, list) else ()))
    revisions = [*(x.get("code_revision") for x in listed if isinstance(x, dict)), fs[0][1]]  # in the invocations' order
    shown = list(dict.fromkeys(r for r in map(_revision, revisions) if r))
    mput("run.revision", ", ".join(shown) or NOT_RECORDED, fs,
         "the code revision of the run's invocations, first 7 characters, each distinct one once")
    fs = mfields("repeats")
    rep = fs[0][1]
    mput("run.repeats", _num(rep) if isinstance(rep, int) and not isinstance(rep, bool) else NOT_RECORDED, fs,
         "repeats per graded pair")
    fs = mfields("pilot")
    mput("run.pilot", "set" if fs[0][1] is True else "not set" if fs[0][1] is False else NOT_RECORDED, fs,
         "the manifest's pilot flag: an invocation graded the tasks without requiring the acceptance gate")
    fs = mfields("invocations")
    mput("run.invocations", _int(len(invocations)) if isinstance(invocations, list) else NOT_RECORDED, fs,
         "the run's invocations, as its manifest records them")
    fs = T.fields("meta.harness_versions")
    hv = fs[0][1]
    versions = sorted({str(k).split("/")[-1] for k in hv}) if isinstance(hv, dict) else []
    nums.put("run.harness", ", ".join(tex(v) for v in versions) or NOT_RECORDED, T.src(fs),
             "the harness versions of the run's results, each once")
    for t in R["fams"]:
        fk, p = _fk(t), f"labels.{t}.d19"
        for v, what in (("valid", "labels valid"), ("invalid", "labels invalid"), ("ambiguous", "labels ambiguous"),
                        ("unlabeled", "leaves without a proposal")):
            fs = T.fields(f"{p}.{v}")
            T.put(f"d19.{fk}.{v}", _num(fs[0][1]), fs, f"the family's held-out candidates D19 {what}")
        fs = T.fields(f"{p}.ambiguous_reasons")
        reasons = fs[0][1]
        names = {cid: tex(_candidate_name(cid, t)) for cid in reasons}
        T.put(f"d19.{fk}.ambiguous.ids", ", ".join(names.values()) or "none", fs,
              "the candidates D19 labels ambiguous, without the family's id in front; none: no such candidate")
        # Each candidate with its reason in brackets, as analysis.md writes them: some of D19's reasons hold a comma or a
        # semicolon, and the text around the macro separates its own items with semicolons.
        T.put(f"d19.{fk}.ambiguous.reasons", ", ".join(f"{names[c]} ({tex(why)})" for c, why in reasons.items()) or "none",
              fs, "each candidate D19 labels ambiguous, with the category of D19's reason in brackets; none: no such candidate")


def natural_run_tables(R: dict, led: SectionLedger, nums: Numbers, out: Path) -> None:
    for name, sha in R["sha256"].items():
        led.add("inputs", f"{name} sha256", sha, name)
    T = NRTable(R, led, nums, "numbers")
    nums.put("run", tex(R["run_id"]), T.src([("run_id", R["run_id"])], R["msrc"]))
    nums.put("families", _int(len(R["fams"])), T.src(T.fields("natural.tasks")), "the run's families (count)")
    nums.put("run.families", ", ".join(tex(t) for t in R["fams"]), T.src(T.fields("natural.tasks")),
             "the run's families, in its order")
    nums.put("accepted", _num(R["a"]["meta"]["case_study"]["accepted_in_run"]),
             T.src(T.fields("meta.case_study.accepted_in_run")), "the run's own accepted tasks (the size rule, protocol §20.3)")
    nums.put("threshold", _num(R["a"]["meta"]["case_study"]["threshold"]), T.src(T.fields("meta.case_study.threshold")),
             "the size threshold of protocol §19.6")
    natural_run_numbers(R, led, nums)
    natural_run_fa_fr_table(R, led, nums, out)
    natural_run_source_table(R, led, nums, out)
    natural_run_labeler_table(R, led, nums, out)
    natural_run_construction_table(R, led, nums, out)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse and check the arguments; nothing is read beyond the directories' listings, and nothing is written."""
    ap = argparse.ArgumentParser(
        prog="paper/make_tables.py",
        description="Generate paper/generated/*.tex and paper/evidence_ledger.md from recorded runs (the construction pilot), "
                    "and, with --fresh, --regrade, --natural and --natural-run, the tables of the new runs in "
                    "paper/generated/fresh/, paper/generated/natural/ and paper/generated/natural_run/ with their own ledgers. "
                    "The outputs are replaced only after every table has been written; on any error every file is left as it "
                    "was.")
    ap.add_argument("runs", nargs="*", metavar="RUN_DIR",
                    help="pilot run directory with analysis.json and manifest.json, e.g. results/runs/pilot-v0.3.3 (optional "
                         "only when --fresh, --natural or --natural-run is given)")
    ap.add_argument("--compare", nargs="+", default=[], metavar="OLD_RUN_DIR",
                    help="earlier run directories (with results.jsonl) for the reliability table; it uses the "
                         "compare_<run>.json files that scripts/compare_runs.py wrote into the run directory")
    ap.add_argument("--fresh", metavar="RUN_DIR",
                    help="fresh-attempt run (analysis.json, analysis_sensitivity.json, manifest.json, results.jsonl), e.g. "
                         "results/runs/fresh-v1: writes paper/generated/fresh/ and paper/evidence_ledger_fresh.md")
    ap.add_argument("--regrade", metavar="RUN_DIR",
                    help="with --fresh: a reliability re-grade of the pilot (manifest.json, results.jsonl, compare_<run>.json), "
                         "e.g. results/runs/pilot-v0.3.5-regrade: adds paper/generated/fresh/regrade_reliability.tex")
    ap.add_argument("--natural", action="store_true",
                    help="the natural arm's screening tables from data/manifests/: writes paper/generated/natural/ and "
                         "paper/evidence_ledger_natural.md")
    ap.add_argument("--natural-run", metavar="RUN_DIR",
                    help="a natural run analysed in case-study mode (analysis.json, manifest.json), e.g. "
                         "results/runs/natural-pr-v1: writes the per-family tables to paper/generated/natural_run/ and "
                         "paper/evidence_ledger_natural_run.md; an analysis outside case-study mode is refused")
    ap.add_argument("--pilot-numbers", metavar="RUN_DIR",
                    help="the construction pilot's numbers for the text (\\plv{key}) from the frozen run (analysis.json, "
                         "manifest.json, results.jsonl, compare_<run>.json) and its exploratory re-analysis "
                         "(results/analyses/<run>-exploratory/), e.g. results/runs/pilot-v0.3.3: writes "
                         "paper/generated/pilot/numbers.tex and paper/evidence_ledger_pilot.md; no pilot table changes")
    ap.add_argument("--design", action="store_true",
                    help="the design's constants and the protocol's history (\\dv{key}) from paper/design_constants.json, "
                         "each checked against its source: writes paper/generated/design/ (numbers.tex, the amendments "
                         "table) and paper/evidence_ledger_design.md")
    a = ap.parse_args(argv)
    if not (a.runs or a.fresh or a.natural or a.natural_run or a.pilot_numbers or a.design):
        ap.error("give a pilot RUN_DIR, --fresh RUN_DIR, --natural, --natural-run RUN_DIR, --pilot-numbers RUN_DIR or --design")
    if a.compare and not a.runs:
        ap.error("--compare needs a pilot RUN_DIR")
    for rd in a.runs:
        missing = [f for f in ("analysis.json", "manifest.json") if not (Path(rd) / f).is_file()]
        if missing:
            ap.error(f"{rd}: no {' or '.join(missing)}; a run directory needs both (run `tracecontract analyze` first)")
    for od in a.compare:
        if not (Path(od) / "results.jsonl").is_file():
            ap.error(f"--compare {od}: no results.jsonl; not a run directory")
    if a.regrade and not a.fresh:
        ap.error("--regrade writes into paper/generated/fresh/ and its ledger, so it needs --fresh")
    if a.fresh:
        missing = [f for f in ("analysis.json", "analysis_sensitivity.json", "manifest.json", "results.jsonl")
                   if not (Path(a.fresh) / f).is_file()]
        if missing:
            ap.error(f"--fresh {a.fresh}: no {', '.join(missing)}")
    if a.regrade:
        missing = [f for f in ("manifest.json", "results.jsonl") if not (Path(a.regrade) / f).is_file()]
        if missing or not list(Path(a.regrade).glob("compare_*.json")):
            ap.error(f"--regrade {a.regrade}: needs manifest.json, results.jsonl and a compare_<run>.json")
    if a.natural:
        missing = [p for p in NATURAL_INPUTS.values() if not (ROOT / p).is_file()]
        if missing:
            ap.error(f"--natural: missing {', '.join(missing)}")
    if a.natural_run:
        missing = [f for f in ("analysis.json", "manifest.json") if not (Path(a.natural_run) / f).is_file()]
        if missing:
            ap.error(f"--natural-run {a.natural_run}: no {' or '.join(missing)} (run `tracecontract analyze` on the natural run "
                     "first)")
        if not (ROOT / NATURAL_INPUTS["M0"]).is_file():  # the privacy check's agent product names (fails closed)
            ap.error(f"--natural-run: missing {NATURAL_INPUTS['M0']}, whose agent product names the privacy check of the "
                     "natural outputs refuses")
    if a.pilot_numbers:
        missing = [f for f in ("analysis.json", "manifest.json", "results.jsonl") if not (Path(a.pilot_numbers) / f).is_file()]
        if missing:
            ap.error(f"--pilot-numbers {a.pilot_numbers}: no {', '.join(missing)}")
    if a.design:
        missing = [p for p in (DESIGN, ROOT / NATURAL_INPUTS["M0"]) if not p.is_file()]
        if missing:
            ap.error(f"--design: missing {', '.join(rel(p) for p in missing)} (the constants; the agent product names of the "
                     "privacy check)")
    return a


def _replace_outputs(tmp_gen: Path, tmp_ledger: Path) -> int:
    """Move the new tables and ledger into place; delete the top-level tables this invocation did not write."""
    new = {p.name: p for p in tmp_gen.glob("*.tex")}
    GEN.mkdir(parents=True, exist_ok=True)
    for old in GEN.glob("*.tex"):
        if old.name not in new:
            old.unlink()  # every table is regenerated; none may survive from an earlier invocation
    for name, p in sorted(new.items()):
        os.replace(p, GEN / name)
    os.replace(tmp_ledger, LEDGER)
    return len(new)


def _replace_subdir(tmp_sub: Path, dest: Path, tmp_ledger: Path, ledger: Path) -> int:
    """Move a new-run mode's outputs into its own subdirectory and its ledger into place; delete the files of that
    subdirectory this invocation did not write. Nothing outside the subdirectory and the ledger is touched."""
    new = {p.name: p for p in tmp_sub.iterdir() if p.is_file()}
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.iterdir():
        if old.is_file() and old.name not in new:
            old.unlink()
    for name, p in sorted(new.items()):
        os.replace(p, dest / name)
    os.replace(tmp_ledger, ledger)
    return len(new)


def _cmd(parts: list[str]) -> str:
    return " ".join(["python", "paper/make_tables.py", *parts])


def main(argv: list[str]) -> None:
    a = parse_args(argv)  # --help and argument errors exit here, before anything is written
    new_modes = bool(a.fresh or a.natural or a.natural_run or a.pilot_numbers or a.design)
    # The pilot ledger names the pilot command only, so that adding a new-run mode never changes it.
    pilot_argv = argv if not new_modes else [*a.runs, *(["--compare", *a.compare] if a.compare else [])]
    led = Ledger(pilot_argv)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    # The temporary directory sits next to the outputs, so os.replace never crosses a file system.
    tmp = Path(tempfile.mkdtemp(prefix=".make_tables-", dir=LEDGER.parent))
    done = []
    try:
        if a.runs:
            out = tmp / "generated"
            out.mkdir()
            olds = [Path(x) for x in a.compare]
            tasks_and_scenarios(led, out)
            for rd in a.runs:
                results(Path(rd), led, out)
                verifiers(Path(rd), led, out)
                comparisons(Path(rd), olds, led, out)
            (tmp / "evidence_ledger.md").write_text("\n".join(led.lines) + "\n")
        subs = []
        if a.fresh:
            cmd = _cmd(["--fresh", rel(Path(a.fresh).resolve()), *(["--regrade", rel(Path(a.regrade).resolve())] if a.regrade else [])])
            fled = SectionLedger("Evidence ledger (fresh-agent stratum and the pilot's re-grade)",
                                 "Every number in `paper/generated/fresh/*.tex` (the tables and the number macros of `numbers.tex`, "
                                 "used in the text as `\\fv{key}`), with the file and field it is read from or computed from. "
                                 f"Generated by `{cmd}`; nothing is entered by hand. All labels are model proposals (D19 and the "
                                 "independent labeler); no human labels exist.")
            fnums = Numbers("fv", fled)
            fout = tmp / "fresh"
            fout.mkdir()
            F = fresh_inputs(Path(a.fresh))
            fresh_run_numbers(F, fled, fnums)
            fresh_design_numbers(F, fled, fnums)
            fresh_tables(F, fled, fnums, fout)
            if a.regrade:
                regrade_table(Path(a.regrade), fled, fnums, fout)
            (fout / "numbers.tex").write_text(fnums.tex(cmd))
            (tmp / "evidence_ledger_fresh.md").write_text(fled.text())
            subs.append(("fresh", fout, len(fled)))
        if a.natural:
            cmd = _cmd(["--natural"])
            nled = SectionLedger("Evidence ledger (natural arm: screening, S10 and the Trace Commons screen)",
                                 "Every number in `paper/generated/natural/*.tex` (the tables and the number macros of `numbers.tex`, "
                                 "used in the text as `\\nat{key}`), with the file and field it is read from or computed from. "
                                 f"Generated by `{cmd}`; nothing is entered by hand. The S9 verdicts are model proposals, not human "
                                 "coding. The natural run's per-family tables and numbers have their own ledger, evidence_ledger_natural_run.md.")
            nnums = Numbers("nat", nled)
            nout = tmp / "natural"
            nout.mkdir()
            N = natural_inputs()
            natural_tables(N, nled, nnums, nout)
            (nout / "numbers.tex").write_text(nnums.tex(cmd))
            (tmp / "evidence_ledger_natural.md").write_text(nled.text())
            subs.append(("natural", nout, len(nled)))
        if a.natural_run:
            run = Path(a.natural_run)
            cmd = _cmd(["--natural-run", _shown(run)])
            rled = SectionLedger("Evidence ledger (natural run: per-family case-study tables)",
                                 f"Every number in `paper/generated/{NR_DIR}/*.tex` (the tables and the number macros of "
                                 "`numbers.tex`, used in the text as `\\nrv{key}`), with the file and fields it is read from. "
                                 f"Generated by `{cmd}`; nothing is entered by hand. A table cell's entry is `<row> | <family> "
                                 "= <cell>`; a caption's is `caption | <what> = <value>`. Each entry names the fields of its file "
                                 "as `<dot path>=<JSON value>`, and `absent` for a field the analysis does not hold. Every field "
                                 "belongs to one family, or to the run (its id, its families, the families of its second "
                                 "labeling, the size rule; its manifest's times, code revision, repeats, pilot flag and "
                                 "invocations, and the harness versions of its results): the run is in case-study mode "
                                 "(protocol §19.6, §20.3), so nothing is pooled over the families. The labels are D19's "
                                 "model proposals, the independent labeler's verdicts and the source-evidence labels; no human "
                                 "labels exist.")
            rnums = Numbers("nrv", rled)
            rout = tmp / NR_DIR
            rout.mkdir()
            R = natural_run_inputs(run)
            natural_run_tables(R, rled, rnums, rout)
            (rout / "numbers.tex").write_text(rnums.tex(cmd))
            (tmp / f"evidence_ledger_{NR_DIR}.md").write_text(rled.text())
            subs.append((NR_DIR, rout, len(rled)))
        if a.pilot_numbers:
            cmd = _cmd(["--pilot-numbers", rel(Path(a.pilot_numbers).resolve())])
            pled = SectionLedger("Evidence ledger (construction pilot: numbers for the text)",
                                 "Every number macro of `paper/generated/pilot/numbers.tex` (used in the text as `\\plv{key}`), "
                                 "with the file and field it is read from or computed from: the frozen pilot run, its "
                                 "comparison files, the B1 check-origin files and verifier specs of the tasks, and the "
                                 f"exploratory re-analysis and planning simulation of D49. Generated by `{cmd}`; nothing is "
                                 "entered by hand, and no pilot table is written. All labels are model proposals (D19); no "
                                 "human labels exist. The exploratory numbers are post hoc.")
            pnums = Numbers("plv", pled)
            pout = tmp / "pilot"
            pout.mkdir()
            pilot_numbers(pilot_inputs(Path(a.pilot_numbers)), pled, pnums)
            (pout / "numbers.tex").write_text(pnums.tex(cmd))
            (tmp / "evidence_ledger_pilot.md").write_text(pled.text())
            subs.append(("pilot", pout, len(pled)))
        if a.design:
            cmd = _cmd(["--design"])
            dled = SectionLedger("Evidence ledger (the design's constants and the protocol's history)",
                                 f"Every number macro of `paper/generated/{DESIGN_DIR}/numbers.tex` (used in the text as "
                                 "`\\dv{key}`) and every value of its amendments table, with the check that ties it to its "
                                 f"source: a quote of the cited file, a pattern of the code, a count of files, a field of "
                                 f"recorded JSON files, or a recomputed hash. Generated by `{cmd}` from "
                                 f"`{rel(DESIGN)}`; a value whose check fails is never written.")
            dnums = Numbers("dv", dled)
            dout = tmp / DESIGN_DIR
            dout.mkdir()
            design_numbers(Design(DESIGN), dled, dnums, dout)
            (dout / "numbers.tex").write_text(dnums.tex(cmd))
            (tmp / f"evidence_ledger_{DESIGN_DIR}.md").write_text(dled.text())
            subs.append((DESIGN_DIR, dout, len(dled)))
        # Privacy: nothing a new-run mode writes may hold a URL, an owner placeholder, a session-local path or a model or
        # agent-product name; natural outputs (the arm's screening and a natural run) may not hold a digit run of 7 or more
        # (an id) either. The ledger's input hashes are exempt from the digit rule only.
        agent_names: tuple[str, ...] = ()
        if a.natural:
            agent_names = N["agent_names"]
        elif a.natural_run or a.design:  # fails closed: without the screening record no agent product name could be checked
            agent_names = _agent_names(json.loads((ROOT / NATURAL_INPUTS["M0"]).read_text()))
        for name, sub, _ in subs:
            natural = name in ("natural", NR_DIR)
            # The design's ledger quotes the protocol and the decision log, which name the natural arm's sources.
            names = agent_names if natural or name == DESIGN_DIR else ()
            # A natural run's own code revisions (the study repository's commits) are no id of the data (_check_private).
            exempt = R["own_revisions"] if name == NR_DIR else ()
            for f in sorted(sub.iterdir()):
                _check_private(f.read_text(), f"{name}/{f.name}", digit_runs=natural, names=names, exempt=exempt)
            text = (tmp / f"evidence_ledger_{name}.md").read_text()
            _check_private(text, f"evidence_ledger_{name}.md", digit_runs=False, names=names)
            if natural:
                _check_private("\n".join(x for x in text.splitlines() if not x.startswith("- [inputs]")),
                               f"evidence_ledger_{name}.md", digit_runs=True, names=names, exempt=exempt)
        # Every output has been written: replace them.
        if a.runs:
            n = _replace_outputs(out, tmp / "evidence_ledger.md")
            done.append(f"wrote {n} tables to {rel(GEN)}; ledger with {len(led.lines) - 4} entries")
        for name, sub, n_led in subs:
            ledger = LEDGER.parent / f"evidence_ledger_{name}.md"
            n = _replace_subdir(sub, GEN / name, tmp / f"evidence_ledger_{name}.md", ledger)
            done.append(f"wrote {n} files to {rel(GEN / name)}; {rel(ledger)} with {n_led} entries")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n".join(done))


if __name__ == "__main__":
    main(sys.argv[1:])
