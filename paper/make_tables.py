"""Generate LaTeX tables and the evidence ledger from recorded runs.

Usage: python paper/make_tables.py results/runs/<final run> [--compare results/runs/<run> ...]

Writes paper/generated/*.tex and paper/evidence_ledger.md. Every number printed in a
table is listed in the ledger with its source file and JSON path. Nothing is entered
by hand: tables come from task manifests, registered scenarios, the run's
analysis.json and the run-comparison files written by scripts/compare_runs.py.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "paper" / "generated"
COND_TEX = {"initial_plain": "C1 initial, plain", "initial_audited": "C2 initial, audited", "full_plain": "C3 full, plain",
            "full_audited": "C4 full, audited", "llm_freeform": "B2 full-session LLM", "repo_tests": "B1 repository tests"}


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
    def __init__(self) -> None:
        self.lines = ["# Evidence ledger", "", "Every number in `paper/generated/*.tex` with its source. Regenerate with "
                      "`python paper/make_tables.py <final run dir> [--compare <run dir> ...]`.", ""]

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


def tasks_and_scenarios(led: Ledger) -> None:
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
    (GEN / "tasks_table.tex").write_text(table(
        "Tasks (generated from task manifests). Held-out candidates exclude the reference solution and the no-op.", "tab:tasks",
        "lllllr", "Task & Population & Repository & Commit & Verifiers & Held-out", rows))
    (GEN / "scenario_table.tex").write_text(table(
        "Intended requirements of the registered controlled scenarios, by the user turn that introduced them "
        "(generated from \\texttt{data/controlled/scenarios}).", "tab:scenarios", "llp{0.33\\linewidth}p{0.33\\linewidth}",
        "Task & Library & Initial request ($U_1$) & Correction ($U_2$)", srows, size="\\footnotesize"))


def results(run: Path, led: Ledger) -> None:
    a = json.loads((run / "analysis.json").read_text())
    run_id = json.loads((run / "manifest.json").read_text())["run_id"]
    src = rel(run / "analysis.json")
    pilot = "automated pilot" in a["meta"]["label_policy"]
    pre = ("\\textbf{Automated pilot: labels are rule-based proposals (D19), not human labels.} " if pilot else "")
    rows = []
    for c, d in ordered(a["conditions"]):
        fa, fr = d["false_acceptance"], d["false_rejection"]
        j = "n/a" if d.get("youden_j") is None else f"{d['youden_j']:+.2f}"
        tn = d["tasks_with_any_accepted_negative"]
        rows.append(f"{tex(COND_TEX.get(c, c))} & {fmt_rate(fa['rate'], fa['num'], fa['den'], fa['ci95'])} & "
                    f"{fmt_rate(fr['rate'], fr['num'], fr['den'], fr['ci95'])} & {j} & {tn['num']}/{tn['den']} & "
                    f"{d['infrastructure']['num']}/{d['infrastructure']['den']} \\\\")
        for k in ("false_acceptance", "false_rejection"):
            v = d[k]
            led.add("summary", f"{run_id} {c} {k}", f"{v['rate']} ({v['num']}/{v['den']}) ci95={v['ci95']}", f"{src} conditions.{c}.{k}")
        led.add("summary", f"{run_id} {c} youden_j", d.get("youden_j"), f"{src} conditions.{c}.youden_j")
        led.add("summary", f"{run_id} {c} tasks_with_any_accepted_negative", f"{tn['num']}/{tn['den']}", f"{src} conditions.{c}")
        led.add("summary", f"{run_id} {c} infrastructure", f"{d['infrastructure']['num']}/{d['infrastructure']['den']}", f"{src} conditions.{c}")
    (GEN / "results_summary.tex").write_text(table(
        f"Verifier reward fidelity on the held-out pool, run \\texttt{{{tex(run_id)}}} ({a['n_tasks']} tasks, {a['n_families']} families). " + pre +
        "Rates with (num/den) and 95\\% task-family bootstrap interval. Reference solution and no-op excluded; ambiguous "
        "candidates excluded. $J$ = (1$-$FR)$-$FA.", "tab:summary", "lllrrr",
        "Condition & False acceptance & False rejection & $J$ & Tasks w/ accepted neg. & Infra", rows, size="\\footnotesize"))

    crow = []
    for d in a["comparisons"]:
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]"
        crow.append(f"{tex(COND_TEX.get(d['a'], d['a']))} & {tex(COND_TEX.get(d['b'], d['b']))} & {d['metric'].upper()} & {diff} & {ci} & "
                    f"{d['n_common']} & {d['discordant']['a_accepts_b_rejects']}/{d['discordant']['a_rejects_b_accepts']} \\\\")
        led.add("comparisons", f"{run_id} {d['a']} - {d['b']} {d['metric']}", f"{d['difference']} ci95={d['ci95']} n={d['n_common']} "
                f"discordant={d['discordant']}", f"{src} comparisons")
    (GEN / "results_comparisons.tex").write_text(table(
        f"Pre-specified paired comparisons on the same candidates, run \\texttt{{{tex(run_id)}}}" + (" (automated pilot)" if pilot else "") +
        ". Last column: A accepts \\& B rejects / A rejects \\& B accepts.", "tab:comparisons", "lllllrr",
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
        nrows.append(f"{tex(COND_TEX.get(c, c))} & {pre_a}/{pre_n} & {nm_a}/{nm_n} & {cv_a}/{cv_n} & {iv_a}/{iv_n} \\\\")
        led.add("negatives", f"{run_id} {c} accepted pre-correction/near-miss/correction-violating/initial-violating",
                f"{pre_a}/{pre_n}, {nm_a}/{nm_n}, {cv_a}/{cv_n}, {iv_a}/{iv_n}", f"{src} per_task")
    (GEN / "negatives_table.tex").write_text(table(
        "Accepted invalid candidates by origin and by negative type (accepted/total)" + (" (automated pilot)" if pilot else "") +
        ". Correction-violating: violates a reference requirement introduced after the first user request.", "tab:negatives",
        "lrrrr", "Condition & Pre-correction state & Near miss & Correction-violating & Initial-violating", nrows, size="\\footnotesize"))

    srows = []
    for c, s in ordered(a["sanity"]):
        r, n = s.get("reference", {}), s.get("noop", {})
        srows.append(f"{tex(COND_TEX.get(c, c))} & {r.get('pass', '-')}/{r.get('n', '-')} & {n.get('pass', '-')}/{n.get('n', '-')} \\\\")
        led.add("sanity", f"{run_id} {c} reference/no-op passes", f"{r.get('pass')}/{r.get('n')}, {n.get('pass')}/{n.get('n')}", f"{src} sanity.{c}")
    (GEN / "sanity_table.tex").write_text(table(
        "Sanity checks (excluded from the rates): reference solution and no-op passes per condition.", "tab:sanity", "lrr",
        "Condition & Reference passes & No-op passes", srows, size="\\footnotesize"))

    if a.get("sensitivity_construction_labels"):
        xrows = []
        for c, d in ordered(a["sensitivity_construction_labels"]):
            xrows.append(f"{tex(COND_TEX.get(c, c))} & {fmt_rate(d['fa'], d['fa_num'], d['fa_den'], d['fa_ci95'])} & "
                         f"{fmt_rate(d['fr'], d['fr_num'], d['fr_den'], d['fr_ci95'])} \\\\")
            led.add("sensitivity", f"{run_id} {c} construction-label FA/FR", f"{d['fa']} ({d['fa_num']}/{d['fa_den']}), {d['fr']} ({d['fr_num']}/{d['fr_den']})",
                    f"{src} sensitivity_construction_labels.{c}")
        (GEN / "sensitivity_table.tex").write_text(table(
            "\\textbf{Exploratory, not pre-specified:} rates when constructed candidates are labeled by construction intent "
            "(including those the pre-specified rule marked ambiguous).", "tab:sensitivity", "lll",
            "Condition & False acceptance & False rejection", xrows, size="\\footnotesize"))

    lrows = []
    for t, d in a.get("labels", {}).items():
        cn = d["counts"]
        lrows.append(f"{tex(t)} & {cn.get('valid', 0)} & {cn.get('invalid', 0)} & {cn.get('ambiguous', 0)} & {cn.get('unlabeled', 0)} & {len(d['review_queue'])} \\\\")
        led.add("labels", f"{t} valid/invalid/ambiguous/unlabeled/queued",
                f"{cn.get('valid', 0)}/{cn.get('invalid', 0)}/{cn.get('ambiguous', 0)}/{cn.get('unlabeled', 0)}/{len(d['review_queue'])}", f"{src} labels.{t}")
    if lrows:
        (GEN / "labels_table.tex").write_text(table(
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
            vrows.append(f"{tex(t)} & {tex(v.replace('_', '-'))} & {d['coverage']:.2f} ({len(d['covered'])}/{n_ref}) & "
                         f"{len(d['unsupported'])}/{d['n_recovered_scored']} & {len(d['contradicting'])} & {c2} & {'--' if k is None else f'{k:.2f}'} \\\\")
            led.add("coverage", f"{t} {v} coverage/unsupported/contradicting/coverage2/kappa",
                    f"{d['coverage']} ({len(d['covered'])}/{n_ref}), {len(d['unsupported'])}/{d['n_recovered_scored']}, {len(d['contradicting'])}, "
                    f"{d2['coverage'] if d2 else None}, {k}", f"{src} coverage.{t} / mapping_agreement.{t}")
    if vrows:
        (GEN / "coverage_table.tex").write_text(table(
            "Recovered contracts against the reference contract (model mappings, proposals). Coverage: share of active scored "
            "reference requirements that a recovered requirement maps to without contradicting it.", "tab:coverage", "llrrrrr",
            "Task & Contract & Coverage & Unsupported & Contradicting & Coverage (mapper 2) & $\\kappa$", vrows, size="\\footnotesize"))

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
    hdr = "Candidate & Origin & Label & " + " & ".join(tex(COND_TEX.get(c, c).split(' ')[0]) for c in conds)
    (GEN / "outcome_matrix.tex").write_text(table(
        f"Outcome of every verifier on every held-out candidate, run \\texttt{{{tex(run_id)}}} (\\checkmark{{}} pass, $\\times$ any "
        "non-pass outcome).", "tab:matrix", "lll" + "c" * len(conds), hdr, mrows, size="\\scriptsize"))
    led.add("matrix", f"{run_id} outcome matrix rows", len(mrows), f"{src} per_task")


def comparisons(new_run: Path, old_runs: list[Path], led: Ledger) -> None:
    rows = []
    for old in old_runs:
        p = new_run / f"compare_{old.name}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        n = d["pairs_in_both"]
        rd, od = len(d["reward_discordant"]), len(d["outcome_discordant"])
        rows.append(f"\\texttt{{{tex(d['old_run'])}}} & {n} & {n - rd}/{n} & {n - od}/{n} \\\\")
        led.add("reliability", f"{d['old_run']} vs {d['new_run']} reward/outcome agreement", f"{n - rd}/{n}, {n - od}/{n}", rel(p))
    if rows:
        (GEN / "reliability_table.tex").write_text(table(
            f"Agreement of superseded runs with the final run \\texttt{{{tex(new_run.name)}}} on pairs graded in both "
            "(pass vs non-pass; exact outcome). Superseded runs used earlier harness versions (D29--D31).", "tab:reliability", "lrrr",
            "Superseded run & Pairs & Reward agreement & Outcome agreement", rows, size="\\footnotesize"))


def main(argv: list[str]) -> None:
    GEN.mkdir(parents=True, exist_ok=True)
    olds: list[Path] = []
    if "--compare" in argv:
        i = argv.index("--compare")
        olds = [Path(x) for x in argv[i + 1:]]
        argv = argv[:i]
    led = Ledger()
    tasks_and_scenarios(led)
    for rd in argv:
        results(Path(rd), led)
        comparisons(Path(rd), olds, led)
    (ROOT / "paper" / "evidence_ledger.md").write_text("\n".join(led.lines) + "\n")
    print(f"wrote tables to {rel(GEN)}; ledger with {len(led.lines) - 4} entries")


if __name__ == "__main__":
    main(sys.argv[1:])
