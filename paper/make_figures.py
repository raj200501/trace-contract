"""Generate the manuscript's figures from a recorded run, as vector PDFs drawn with TikZ.

Usage: python paper/make_figures.py results/runs/fresh-v1

Writes, for the fresh-agent stratum (the per-family display of protocol §15.7):
* paper/generated/figures/fresh_fa_by_family.{pdf,tikz,json,tex}: false acceptance per family and condition
  (``fig:fresh-fa``);
* paper/generated/figures/fresh_fr_by_family.{pdf,tikz,json,tex}: false rejection, the same layout (``fig:fresh-fr``);
* paper/evidence_ledger_figures.md: every plotted value and every number of a caption or panel title, with the file and
  field it is read from.

Per figure, the .tikz file is the drawing (one TikZ picture, every coordinate written out), the .pdf is that drawing
compiled by pdflatex in a standalone document, the .json lists every plotted value with its source field, and the .tex
is a figure environment (the PDF, a generated caption, the label) that main.tex inputs like a generated table; it needs
graphicx and prints an UNFILLED mark without it. Every value is read from the run's analysis.json; nothing is entered
by hand. All labels are model proposals (D19 and the independent labeler); no human labels exist.

Reproducibility: pdflatex runs with SOURCE_DATE_EPOCH and FORCE_SOURCE_DATE set, and the PDF omits dates, the trailer
ID and the pdfTeX banner, so its bytes depend only on the inputs and the TeX installation, whose pdfTeX and pgf versions
the ledger records. Needs pdflatex with TikZ, the standalone class and the Latin Modern fonts, which the manuscript's own
build needs anyway, and no Python package beyond the standard library.

Everything is written to a temporary directory first. Only when every output exists do they replace the files of
paper/generated/figures/ (a file there that this invocation did not write is deleted) and the ledger; ``--help``, a bad
argument or a failure while generating leaves every file as it was.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "paper" / "generated" / "figures"
LEDGER = ROOT / "paper" / "evidence_ledger_figures.md"

_spec = importlib.util.spec_from_file_location("make_tables", Path(__file__).with_name("make_tables.py"))
mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt)

# Geometry, in pt. The width is the manuscript's \linewidth (letter paper, 1 in margins: 6.5 in), so the PDF is
# included at its natural size and its text has the document's sizes (\scriptsize 8 pt, \footnotesize 9 pt).
WIDTH = 469.75
LABEL_W = 84.0  # column of row labels, left of the first panel (the widest label, "B2 full-session LLM", is 74.4 pt)
GAP = 12.0  # between two panels
INSET = 8.0  # from a panel's edge to its 0 and 1 lines, so a marker at 0 or 1 is drawn whole, never clipped
ROW = 13.0  # row pitch
GROUP_GAP = 6.0  # added between the three groups of conditions
DOT, RING = 3.0, 1.5  # D19 mark: a filled circle (6 pt) with a 1.5 pt ring in the surface colour
DIAMOND, STROKE, HALO = 6.0, 0.9, 2.4  # labeler mark: an open diamond (12 pt corner to corner) with a surface halo

# Colour encodes the contract source, in this fixed order (the first three slots of the categorical palette).
# Validated for this use (every pair, white surface): worst colour-vision-deficiency distance dE 9.2 (deuteranopia,
# OKLab x100), worst normal-vision distance 24.0. #1BAF7A has 2.82:1 contrast against white, below 3:1, so the figure
# never relies on colour alone: every row is labelled, the legend names the groups, and Table tab:fresh-family gives
# every value. Text is in neutral inks, never in a series colour.
GROUPS = [("tcinitial", "2A78D6", "initial-only contract (C1, C2)", ("initial_plain", "initial_audited")),
          ("tcfull", "EB6834", "correction-aware contract (C3, C4)", ("full_plain", "full_audited")),
          ("tcbase", "1BAF7A", "baselines (B2, B1)", ("llm_freeform", "repo_tests"))]
INKS = {"tctext": "0B0B0B", "tcmuted": "52514E", "tcgrid": "D7D6D1", "tcguide": "EFEEEA"}

FIGURES = [
    {"name": "fresh_fa_by_family", "label": "fig:fresh-fa", "metric": "fa", "key": "false_acceptance", "units": "invalid",
     "axis": "False acceptance (accepted / invalid units of the family)", "what": "false acceptance",
     "share": "the share of a family's invalid units that it accepts"},
    {"name": "fresh_fr_by_family", "label": "fig:fresh-fr", "metric": "fr", "key": "false_rejection", "units": "valid",
     "axis": "False rejection (rejected / valid units of the family)", "what": "false rejection",
     "share": "the share of a family's valid units that it rejects"},
]


def f2(x: float) -> str:
    """A coordinate: two decimals, no negative zero, so the drawing is byte-stable."""
    s = f"{x:.2f}"
    return "0.00" if s == "-0.00" else s


def group_of(cond: str) -> tuple[str, str, str, tuple[str, ...]]:
    return next(g for g in GROUPS if cond in g[3])


def read_points(a: dict, src: str, fig: dict) -> tuple[list[str], list[dict], dict]:
    """Every plotted value (condition x family x labeling) with its source field, and each family's denominators."""
    m = fig["metric"]
    fams = sorted(a["per_task"])
    if [c for c, _ in mt.ordered(a["per_family"])] != mt.ORDER:
        raise ValueError(f"{src}: per_family holds {sorted(a['per_family'])}, expected the six conditions of the protocol")
    pts, dens = [], {}
    for c in mt.ORDER:
        il = a["independent_labeling"]["conditions"][c]
        if il["primary"]["per_family"] != a["per_family"][c]:
            raise ValueError(f"{src}: per_family.{c} differs from independent_labeling.conditions.{c}.primary.per_family")
        pooled = {"D19": a["conditions"][c][fig["key"]], "labeler": il["independent_label"][fig["key"]]}
        for labels, per, base in (("D19", a["per_family"][c], f"per_family.{c}"),
                                  ("labeler", il["independent_label"]["per_family"],
                                   f"independent_labeling.conditions.{c}.independent_label.per_family")):
            if sum(per[t][f"{m}_num"] for t in fams) != pooled[labels]["num"] or \
                    sum(per[t][f"{m}_den"] for t in fams) != pooled[labels]["den"]:
                raise ValueError(f"{src}: {base}.*.{m}_num, {m}_den do not sum to the pooled {fig['key']}")
            for t in fams:
                num, den = per[t][f"{m}_num"], per[t][f"{m}_den"]
                if dens.setdefault((t, labels), den) != den:
                    raise ValueError(f"{src}: {t} has different {fig['units']} counts under different conditions ({labels})")
                pts.append({"condition": c, "short": mt.SHORT[c], "task": t, "labels": labels, "num": num, "den": den,
                            "value": None if not den else num / den, "field": f"{base}.{t}.{m}_num, .{m}_den"})
    return fams, pts, dens


def caption_facts(a: dict, src: str, fams: list[str]) -> dict:
    """The numbers a caption states, each computed from the analysis with the field it comes from."""
    stratum = sorted({k for t in a["meta"]["strata"].values() for k in t})
    if len(stratum) != 1:
        raise ValueError(f"{src}: one candidate stratum expected, found {stratum}")
    violated = {(t, x["candidate"]): x["violated"] for t in fams for x in a["labels"][t]["strata"][stratum[0]]["candidates"]}
    il = a["independent_labeling"]["candidates"]
    units = {}
    for t in fams:
        for c in mt.ORDER:
            for r in a["per_task"][t][c]:
                units[(t, r["candidate"])] = (r["label"], r["negative_type"])
    regr = {}
    for t in fams:
        inv = [cid for (tt, cid), (lab, _) in units.items() if tt == t and lab == "invalid"]
        if inv and all(violated.get((t, cid)) == ["REGRESSION"] for cid in inv):
            regr[t] = {"n": len(inv), "labeler_valid": sum(il[f"{t}/{cid}"]["label"] == "valid" for cid in inv)}
    failing = {c: sorted(a["oracle_gated"]["conditions"][c]["dropped"]) for c in mt.ORDER}
    return {"n_units": a["distinct_patches"]["n_distinct"], "regression_only": regr, "failing_reference": failing,
            "stratum": stratum[0]}


def _marks(x: float, y: float, colour: str, kind: str, alone: bool = True) -> list[str]:
    """TikZ paths of one mark centred at (x, y). A diamond is white-filled with a white halo, so a grid line never runs
    through it; a dot that sits alone has a white ring, a dot inside its own diamond needs none."""
    if kind == "diamond":
        d = DIAMOND
        pts = f"({f2(x)},{f2(y + d)}) -- ({f2(x + d)},{f2(y)}) -- ({f2(x)},{f2(y - d)}) -- ({f2(x - d)},{f2(y)}) -- cycle"
        return [f"\\filldraw[fill=white,draw=white,line width={HALO}pt,line join=miter] {pts};",
                f"\\draw[{colour},line width={STROKE}pt,line join=miter] {pts};"]
    out = [f"\\fill[white] ({f2(x)},{f2(y)}) circle[radius={DOT + RING}pt];"] if alone else []
    return out + [f"\\fill[{colour}] ({f2(x)},{f2(y)}) circle[radius={DOT}pt];"]


def _extent(node_anchor: str, tag: str) -> str:
    """Write the x coordinate of a node anchor to the log, so that the layout can be checked after compiling."""
    return f"\\path ({node_anchor}); \\pgfgetlastxy{{\\tcx}}{{\\tcy}}\\typeout{{TC-EXTENT: {tag} \\tcx}}"


def tikz(fig: dict, fams: list[str], pts: list[dict], dens: dict) -> tuple[str, list[tuple[str, str, float]]]:
    """The drawing, and the layout checks: (tag, "min" or "max", bound) for the x coordinate the log reports per tag."""
    n = len(fams)
    pw = (WIDTH - LABEL_W - (n - 1) * GAP) / n
    ys, y, prev = {}, 0.0, None
    for c in mt.ORDER:
        g = group_of(c)[0]
        if prev is not None:
            y -= ROW + (GROUP_GAP if g != prev else 0.0)
        ys[c], prev = y, g
    ytop, ybot = ys[mt.ORDER[0]] + ROW / 2 + 2, ys[mt.ORDER[-1]] - ROW / 2 - 2
    ytitle, ylegend2, ylegend1 = ytop + 4, ytop + 35, ytop + 47
    bb_top, bb_bot = ylegend1 + 7, ybot - 28
    checks: list[tuple[str, str, float]] = []
    lines = ["% Generated by `python paper/make_figures.py`; do not edit. Every value: paper/evidence_ledger_figures.md.",
             "\\begin{tikzpicture}[x=1pt,y=1pt,font=\\scriptsize,inner sep=0pt]"]
    lines += [f"\\definecolor{{{k}}}{{HTML}}{{{v}}}" for k, v, _, _ in GROUPS]
    lines += [f"\\definecolor{{{k}}}{{HTML}}{{{v}}}" for k, v in INKS.items()]
    lines.append(f"\\path[use as bounding box] (0,{f2(bb_bot)}) rectangle ({f2(WIDTH)},{f2(bb_top)});")
    # Legend, two rows above the panels, aligned with the first panel: colour = contract source; shape = labeling.
    lines.append(f"\\coordinate (K0) at ({f2(LABEL_W + INSET - 3)},{f2(ylegend1)});")
    for i, (col, _, text, _) in enumerate(GROUPS):
        if i:
            lines.append(f"\\coordinate (K{i}) at ([xshift=12pt]G{i - 1}.east);")
        lines.append(f"\\fill[{col},rounded corners=1pt] ([yshift=-3pt]K{i}) rectangle ++(6pt,6pt);")
        lines.append(f"\\node[anchor=west,text=tctext] (G{i}) at ([xshift=9pt]K{i}) {{{text}}};")
    lines.append(_extent(f"G{len(GROUPS) - 1}.east", "legend-colours-end"))
    checks.append(("legend-colours-end", "max", WIDTH))
    lines.append(f"\\coordinate (M0) at ({f2(LABEL_W + INSET)},{f2(ylegend2)});")
    lines.append("\\begin{scope}[shift={(M0)}]")
    lines += _marks(0.0, 0.0, "tcmuted", "dot")
    lines.append("\\end{scope}")
    lines.append(f"\\node[anchor=west,text=tctext] (S0) at ([xshift={DOT + 4}pt]M0) {{D19 labels (primary)}};")
    lines.append(f"\\coordinate (M1) at ([xshift={12 + DIAMOND}pt]S0.east);")
    lines.append("\\begin{scope}[shift={(M1)}]")
    lines += _marks(0.0, 0.0, "tcmuted", "diamond")
    lines.append("\\end{scope}")
    lines.append(f"\\node[anchor=west,text=tctext] (S1) at ([xshift={DIAMOND + 3}pt]M1) {{independent labeler}};")
    lines.append(_extent("S1.east", "legend-shapes-end"))
    checks.append(("legend-shapes-end", "max", WIDTH))
    # Row labels.
    for i, c in enumerate(mt.ORDER):
        lines.append(f"\\node[anchor=east,text=tctext] (R{i}) at ({f2(LABEL_W - 6)},{f2(ys[c])}) {{{mt.tex(mt.COND_TEX[c])}}};")
        lines.append(_extent(f"R{i}.west", f"row-{i}"))
        checks.append((f"row-{i}", "min", 0.0))
    by = {(p["condition"], p["task"], p["labels"]): p for p in pts}
    for k, t in enumerate(fams):
        x0 = LABEL_W + k * (pw + GAP)
        xa, xb = x0 + INSET, x0 + pw - INSET

        def xv(v: float, xa: float = xa, xb: float = xb) -> float:
            return xa + v * (xb - xa)

        nd, nl = dens[(t, "D19")], dens[(t, "labeler")]
        ntxt = f"{nd} {fig['units']}" + ("" if nl == nd else f" (labeler: {nl})")
        lines.append(f"% panel {t}")
        lines.append(f"\\node[anchor=south,align=center,text=tctext,font=\\footnotesize] (T{k}) at ({f2((xa + xb) / 2)},{f2(ytitle)}) "
                     f"{{{mt.tex(t)}\\\\[1pt]{{\\scriptsize\\color{{tcmuted}}{ntxt}}}}};")
        lines.append(_extent(f"T{k}.west", f"title-{k}-west"))
        lines.append(_extent(f"T{k}.east", f"title-{k}-east"))
        checks += [(f"title-{k}-west", "min", x0 - GAP / 2 + 1), (f"title-{k}-east", "max", x0 + pw + GAP / 2 - 1)]
        for c in mt.ORDER:
            lines.append(f"\\draw[tcguide,line width=0.4pt] ({f2(xa)},{f2(ys[c])}) -- ({f2(xb)},{f2(ys[c])});")
        for v, txt in ((0.0, "0"), (0.5, "0.5"), (1.0, "1")):
            lines.append(f"\\draw[tcgrid,line width=0.4pt] ({f2(xv(v))},{f2(ybot)}) -- ({f2(xv(v))},{f2(ytop)});")
            lines.append(f"\\node[anchor=north,text=tcmuted] at ({f2(xv(v))},{f2(ybot - 3)}) {{{txt}}};")
        lines.append(f"\\draw[tcmuted,line width=0.4pt] ({f2(xa - 2)},{f2(ybot)}) -- ({f2(xb + 2)},{f2(ybot)});")
        for c in mt.ORDER:  # diamonds first, so a dot is never hidden under a diamond
            p = by[(c, t, "labeler")]
            if p["value"] is not None:
                lines += _marks(xv(p["value"]), ys[c], group_of(c)[0], "diamond")
        for c in mt.ORDER:
            p, q = by[(c, t, "D19")], by[(c, t, "labeler")]
            if p["value"] is not None:
                lines += _marks(xv(p["value"]), ys[c], group_of(c)[0], "dot", alone=q["value"] != p["value"])
    x_first, x_last = LABEL_W + INSET, LABEL_W + (n - 1) * (pw + GAP) + pw - INSET
    lines.append(f"\\node[anchor=north,text=tctext,font=\\footnotesize] (X) at ({f2((x_first + x_last) / 2)},{f2(ybot - 15)}) "
                 f"{{{fig['axis']}}};")
    lines.append(_extent("X.east", "axis-east"))
    checks.append(("axis-east", "max", WIDTH))
    lines.append("\\end{tikzpicture}")
    return "\n".join(lines) + "\n", checks


def caption(fig: dict, run_id: str, facts: dict, dens: dict, fams: list[str]) -> str:
    parts = [f"{fig['what'].capitalize()} per family on the fresh-agent stratum (run \\texttt{{{mt.tex(run_id)}}}, an automated "
             f"study), the per-family display of protocol \\S15.7: for each condition, {fig['share']}, under D19 (filled circles) and under the "
             "independent labeler, a second labeling (open diamonds; a circle inside a diamond: both labelings give the same "
             f"value). Each distinct graded patch counts once ({facts['n_units']} units); under each family: its {fig['units']} "
             f"units under D19, and under the labeler where that differs. {mt.NO_HUMAN} {mt.FOUR_FAMILIES}"]
    for t, r in sorted(facts["regression_only"].items()):
        n, k = r["n"], r["labeler_valid"]
        them = ("it" if n == 1 else "both" if n == 2 else "all of them") if k == n else f"{k} of them"
        parts.append(f"In {mt.tex(t)} the {n} invalid unit{'' if n == 1 else 's'} under D19 violate{'s' if n == 1 else ''} only the "
                     f"regression norm; the labeler, which has no regression part, labels {them} valid"
                     + (f", so {mt.tex(t)} has no labeler mark." if fig["metric"] == "fa" and dens[(t, "labeler")] == 0 else "."))
    fail = {}
    for c, ts in facts["failing_reference"].items():
        for t in ts:
            fail.setdefault(t, []).append(mt.SHORT[c])
    for t, cs in sorted(fail.items()):
        who = " and ".join(cs) if len(cs) <= 2 else ", ".join(cs[:-1]) + " and " + cs[-1]
        parts.append(f"{who} do{'es' if len(cs) == 1 else ''} not pass {mt.tex(t)}'s reference solution.")
    parts.append("Colour: the contract source; counts: Table~\\ref{tab:fresh-family}.")
    return " ".join(parts)


def figure_env(fig: dict, cap: str) -> str:
    path = f"generated/figures/{fig['name']}.pdf"
    return ("% Generated by `python paper/make_figures.py`; do not edit. Every value: paper/evidence_ledger_figures.md.\n"
            "\\begin{figure}[t]\\centering\n"
            f"\\ifdefined\\includegraphics\\includegraphics[width=\\linewidth]{{{path}}}%\n"
            f"\\else\\unfilled{{figure {mt.tex(fig['name'])}: main.tex must load graphicx}}\\fi\n"
            f"\\caption{{{cap}}}\\label{{{fig['label']}}}\n\\end{{figure}}\n")


STANDALONE = r"""\documentclass[11pt,border=0pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{tikz}
\pdfinfoomitdate=1
\pdftrailerid{}
\pdfsuppressptexinfo=-1
\begin{document}
\typeout{TC-PGF-VERSION: \pgfversion}%
\input{NAME.tikz}%
\end{document}
"""


def compile_pdf(tmp: Path, name: str, epoch: int, checks: list[tuple[str, str, float]]) -> dict:
    """Compile NAME.tikz into NAME.pdf in ``tmp``, check the layout against the extents the log reports (a label that
    would overflow its space or the page fails here), and return the renderer versions read from the log."""
    (tmp / f"{name}_standalone.tex").write_text(STANDALONE.replace("NAME", name))
    env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch), FORCE_SOURCE_DATE="1")
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", f"{name}_standalone.tex"],
                       cwd=tmp, env=env, capture_output=True, text=True, timeout=300, check=False)
    log = (tmp / f"{name}_standalone.log").read_text(errors="replace") if (tmp / f"{name}_standalone.log").exists() else ""
    if r.returncode != 0 or not (tmp / f"{name}_standalone.pdf").exists():
        tail = "\n".join((log or r.stdout).splitlines()[-25:])
        raise RuntimeError(f"pdflatex failed on {name}.tikz:\n{tail}")
    if "Overfull" in log:
        raise RuntimeError(f"pdflatex reports an overfull box in {name}: a label does not fit")
    ext = {}
    for x in log.splitlines():
        if x.startswith("TC-EXTENT: "):
            tag, val = x[len("TC-EXTENT: "):].split()
            ext[tag] = float(val.removesuffix("pt"))
    for tag, kind, bound in checks:
        if tag not in ext:
            raise RuntimeError(f"{name}: the log reports no extent for {tag}")
        if (kind == "min" and ext[tag] < bound) or (kind == "max" and ext[tag] > bound):
            raise RuntimeError(f"{name}: {tag} at x = {ext[tag]:.1f} pt is outside its bound {kind} {bound:.1f} pt; a label "
                               "does not fit its space")
    os.replace(tmp / f"{name}_standalone.pdf", tmp / f"{name}.pdf")
    first = log.splitlines()[0] if log else ""
    engine = first.split("(preloaded")[0].replace("This is ", "").strip()
    pgf = next((x.split(":", 1)[1].strip() for x in log.splitlines() if x.startswith("TC-PGF-VERSION:")), "unknown")
    for p in tmp.glob(f"{name}_standalone.*"):
        p.unlink()
    return {"engine": engine, "pgf": pgf}


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="paper/make_figures.py",
        description="Draw the per-family figures of a fresh-attempt run (TikZ, compiled with pdflatex) into "
                    "paper/generated/figures/ and write paper/evidence_ledger_figures.md. The outputs are replaced only after "
                    "every figure has been written; on any error every file is left as it was.")
    ap.add_argument("run", metavar="RUN_DIR", help="fresh-attempt run with analysis.json and manifest.json, e.g. results/runs/fresh-v1")
    a = ap.parse_args(argv)
    missing = [f for f in ("analysis.json", "manifest.json") if not (Path(a.run) / f).is_file()]
    if missing:
        ap.error(f"{a.run}: no {' or '.join(missing)}")
    if shutil.which("pdflatex") is None:
        ap.error("pdflatex is not on PATH (a TeX distribution with TikZ and the standalone class is needed)")
    return a


def main(argv: list[str]) -> None:
    a = parse_args(argv)  # --help and argument errors exit here, before anything is written
    run = Path(a.run)
    an = json.loads((run / "analysis.json").read_text())
    man = json.loads((run / "manifest.json").read_text())
    src = mt.rel((run / "analysis.json").resolve())
    msrc = mt.rel((run / "manifest.json").resolve())
    sha = hashlib.sha256((run / "analysis.json").read_bytes()).hexdigest()
    cmd = " ".join(["python", "paper/make_figures.py", mt.rel(run.resolve())])
    epoch = int(datetime.fromisoformat(man["finished_at"].replace("Z", "+00:00")).timestamp())
    led = mt.SectionLedger("Evidence ledger (figures)",
                           "Every value plotted in `paper/generated/figures/*.pdf` and every number in their captions and panel "
                           "titles, with the file and field it is read from. Generated by "
                           f"`{cmd}`; nothing is entered by hand. All labels are model proposals (D19 and the independent "
                           "labeler); no human labels exist.")
    led.add("inputs", f"{src} sha256", sha, src)
    led.add("inputs", "run (manifest run_id); SOURCE_DATE_EPOCH (manifest finished_at)", f"{man['run_id']}; {epoch}",
            f"{msrc} run_id, finished_at")
    FIG.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".make_figures-", dir=LEDGER.parent))
    try:
        out = tmp / "figures"
        out.mkdir()
        renderer = None
        for fig in FIGURES:
            name, m = fig["name"], fig["metric"]
            fams, pts, dens = read_points(an, src, fig)
            facts = caption_facts(an, src, fams)
            for p in pts:
                led.add(name, f"{p['short']} {p['task']} {p['labels']} {fig['what']}",
                        f"{p['num']}/{p['den']}" + ("" if p["value"] is None else f" = {p['value']:.3f}") +
                        (" (not plotted: no unit)" if p["value"] is None else ""), f"{src} {p['field']}")
            for (t, labels), den in sorted(dens.items()):
                led.add(name, f"panel {t} subtitle: {fig['units']} units under {labels}", den,
                        f"{src} per_family.<every condition>.{t}.{m}_den" if labels == "D19" else
                        f"{src} independent_labeling.conditions.<every condition>.independent_label.per_family.{t}.{m}_den")
            led.add(name, "caption: units (each distinct graded patch once)", facts["n_units"], f"{src} distinct_patches.n_distinct")
            for t, r in sorted(facts["regression_only"].items()):
                led.add(name, f"caption: {t} invalid units under D19 whose only violated requirement is REGRESSION; of them "
                        "labelled valid by the labeler", f"{r['n']}; {r['labeler_valid']}",
                        f"{src} per_task.{t}.*[].label; labels.{t}.strata.{facts['stratum']}.candidates[].violated; "
                        f"independent_labeling.candidates[{t}/*].label")
            for c, ts in facts["failing_reference"].items():
                if ts:
                    led.add(name, f"caption: {mt.SHORT[c]} does not pass the reference solution of", ", ".join(ts),
                            f"{src} oracle_gated.conditions.{c}.dropped")
            draw, checks = tikz(fig, fams, pts, dens)
            (out / f"{name}.tikz").write_text(draw)
            renderer = compile_pdf(out, name, epoch, checks)
            cap = caption(fig, man["run_id"], facts, dens, fams)
            (out / f"{name}.tex").write_text(figure_env(fig, cap))
            record = {"figure": name, "label": fig["label"], "generated_by": cmd, "run_id": man["run_id"], "source": src,
                      "source_sha256": sha, "metric": fig["key"], "labels": "model proposals (D19, independent labeler); no human labels",
                      "families": fams, "conditions": [mt.SHORT[c] for c in mt.ORDER],
                      "panels": [{"task": t, "n_d19": dens[(t, "D19")], "n_labeler": dens[(t, "labeler")]} for t in fams],
                      "points": [{k: p[k] for k in ("condition", "short", "task", "labels", "num", "den", "field")} |
                                 {"value": None if p["value"] is None else round(p["value"], 6), "plotted": p["value"] is not None}
                                 for p in pts]}
            (out / f"{name}.json").write_text(json.dumps(record, indent=1) + "\n")
        led.add("inputs", "renderer: pdfTeX (first line of the log); pgf (\\pgfversion)", f"{renderer['engine']}; {renderer['pgf']}",
                "pdflatex log of the standalone compile")
        for f in sorted(out.iterdir()):
            if f.suffix != ".pdf":
                mt._check_private(f.read_text(), f"figures/{f.name}", digit_runs=False)
        text = led.text()
        mt._check_private(text, LEDGER.name, digit_runs=False)
        (tmp / LEDGER.name).write_text(text)
        n = mt._replace_subdir(out, FIG, tmp / LEDGER.name, LEDGER)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {n} files to {mt.rel(FIG)}; {mt.rel(LEDGER)} with {len(led)} entries")


if __name__ == "__main__":
    main(sys.argv[1:])
