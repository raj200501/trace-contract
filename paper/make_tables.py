"""Generate LaTeX tables and the evidence ledger from recorded runs.

Usage: python paper/make_tables.py results/runs/<run_id> [more run dirs...]

Writes paper/generated/{tasks_table,results_summary,results_comparisons}.tex and
paper/evidence_ledger.md. Every number printed in a table is listed in the ledger
with its run id, source file and JSON path. Nothing is entered by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "paper" / "generated"


def tex(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")
            .replace("#", r"\#"))


def fmt_rate(d: dict) -> str:
    if d.get("rate") is None:
        return f"n/a (0/{d.get('den', 0)})"
    s = f"{d['rate']:.2f} ({d['num']}/{d['den']})"
    if d.get("ci95"):
        s += f" [{d['ci95'][0]:.2f}, {d['ci95'][1]:.2f}]"
    return s


def main(run_dirs: list[str]) -> None:
    GEN.mkdir(parents=True, exist_ok=True)
    ledger = ["# Evidence ledger", "", "Every number in `paper/generated/*.tex` with its source. Regenerate with "
              "`python paper/make_tables.py <run dirs>`.", ""]
    # Task table from manifests.
    rows = []
    for td in sorted((ROOT / "tasks").glob("*/task.json")):
        m = json.loads(td.read_text())
        rows.append(f"{tex(m['task_id'])} & {tex(m['population'])} & \\texttt{{{tex(m['snapshot_source']['repo_url'].split('github.com/')[-1])}}} & "
                    f"\\texttt{{{m['snapshot_source']['commit'][:7]}}} & {tex(m['status'])} \\\\")
        ledger.append(f"- task table: `{m['task_id']}` from `tasks/{m['task_id']}/task.json`")
    (GEN / "tasks_table.tex").write_text(
        "\\begin{table}[t]\\centering\\small\n\\caption{Tasks (generated from task manifests).}\\label{tab:tasks}\n"
        "\\begin{tabular}{lllll}\\toprule Task & Population & Repository & Commit & Status \\\\\\midrule\n"
        + "\n".join(rows) + "\n\\bottomrule\\end{tabular}\\end{table}\n")
    summary_parts, comp_parts = [], []
    for rd in run_dirs:
        rd = Path(rd)
        a = json.loads((rd / "analysis.json").read_text())
        run_id = json.loads((rd / "manifest.json").read_text())["run_id"]
        pilot = "automated pilot" in a["meta"]["label_policy"]
        cap = (f"Verifier reward fidelity, run \\texttt{{{tex(run_id)}}} ({a['n_tasks']} tasks, {a['n_families']} families). "
               + ("\\textbf{Automated pilot: labels are model/construction proposals.} " if pilot else "")
               + "Rates with (num/den) and 95\\% task-family bootstrap interval where computable.")
        body = []
        for c, d in a["conditions"].items():
            fa, fr = d["false_acceptance"], d["false_rejection"]
            body.append(f"{tex(c)} & {fmt_rate(fa)} & {fmt_rate(fr)} & {d['infrastructure']['num']}/{d['infrastructure']['den']} \\\\")
            for k, v in (("false_acceptance", fa), ("false_rejection", fr)):
                ledger.append(f"- `{run_id}` {c} {k} = {v.get('rate')} ({v.get('num')}/{v.get('den')}), ci95={v.get('ci95')} "
                              f"<- `{rd.relative_to(ROOT) if rd.is_relative_to(ROOT) else rd}/analysis.json` conditions.{c}.{k}")
        summary_parts.append(
            f"\\begin{{table}}[t]\\centering\\small\n\\caption{{{cap}}}\\label{{tab:summary-{tex(run_id)}}}\n"
            "\\begin{tabular}{llll}\\toprule Condition & False acceptance & False rejection & Infra \\\\\\midrule\n"
            + "\n".join(body) + "\n\\bottomrule\\end{tabular}\\end{table}\n")
        cbody = []
        for d in a["comparisons"]:
            diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
            ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]"
            cbody.append(f"{tex(d['a'])} & {tex(d['b'])} & {d['metric'].upper()} & {diff} & {ci} & {d['n_common']} & "
                         f"{d['discordant']['a_accepts_b_rejects']}/{d['discordant']['a_rejects_b_accepts']} \\\\")
            ledger.append(f"- `{run_id}` {d['a']} - {d['b']} {d['metric']} = {d['difference']} ci95={d['ci95']} n={d['n_common']} "
                          f"<- `analysis.json` comparisons")
        comp_parts.append(
            f"\\begin{{table}}[t]\\centering\\small\n\\caption{{Paired comparisons on the same candidates, run \\texttt{{{tex(run_id)}}}"
            + (" (automated pilot)" if pilot else "") + ". Last column: A accepts \\& B rejects / A rejects \\& B accepts.}\n"
            "\\begin{tabular}{lllllll}\\toprule A & B & Metric & A$-$B & 95\\% CI & n & discordant \\\\\\midrule\n"
            + "\n".join(cbody) + "\n\\bottomrule\\end{tabular}\\end{table}\n")
    (GEN / "results_summary.tex").write_text("\n".join(summary_parts))
    (GEN / "results_comparisons.tex").write_text("\n".join(comp_parts))
    (ROOT / "paper" / "evidence_ledger.md").write_text("\n".join(ledger) + "\n")
    print(f"wrote {len(summary_parts)} summary table(s), {len(comp_parts)} comparison table(s), ledger with {len(ledger) - 4} entries")


if __name__ == "__main__":
    main(sys.argv[1:])
