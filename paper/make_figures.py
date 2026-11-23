"""Generate the manuscript's figures from a recorded run, as vector PDFs drawn with TikZ.

Usage: python paper/make_figures.py results/runs/fresh-v1

Writes, for the fresh-agent stratum (restructure plan, part 6):
* paper/generated/figures/fresh_fa_fr_by_family.{pdf,tikz,json,tex} (Fig. 2, ``fig:fresh-fa`` and ``fig:fresh-fr``): false
  acceptance (top) and false rejection (bottom) per family and condition under D19, the per-family display of protocol
  §15.7. In the false-acceptance panels the filled marks are the correction violators accepted; a family without
  correction violators says so in its title, and its invalid units, which break only the regression norm, are hollow
  marks ("regression only"), so that its panel cannot read as the reverse of the finding. A condition that fails the
  family's reference solution is annotated in that family's panels. The independent labeler's view is in its table;
* paper/generated/figures/design_example.{pdf,tikz,json,tex} (Fig. 1, ``fig:design``): the design as a 2 x 2 of the
  contract conditions with the baselines and the attempts, and two worked examples, CS-04 and CS-01, whose excerpts are
  exact substrings of the controlled scenarios' turns (synthetic text written for the study) and whose numbers are the
  fresh-v1 macros (\\fv) as make_tables.py --fresh computes them;
* paper/evidence_ledger_figures.md: every plotted value, every number of a panel's text, title or caption, and every
  excerpt, with the file and field (or the \\fv key) it is read from.

Per figure, the .tikz file is the drawing (one TikZ picture, every coordinate written out), the .pdf is that drawing
compiled by pdflatex in a standalone document, the .json lists every plotted value or stated number with its source,
and the .tex is a figure environment (the PDF, a generated caption, the label) that main.tex inputs like a generated
table; it needs graphicx and prints an UNFILLED mark without it. Nothing is entered by hand. All labels are model
proposals (D19); no human labels exist.

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
import re
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
LABEL_W = 26.0  # column of row labels (C1 ... B1), left of the first panel; the legend names the conditions
GAP = 12.0  # between two panels
INSET = 8.0  # from a panel's edge to its 0 and 1 lines, so a marker at 0 or 1 is drawn whole, never clipped
ROW = 11.0  # row pitch
GROUP_GAP = 5.0  # added between the three groups of conditions
DOT, RING, HOLLOW, STROKE = 3.0, 1.5, 2.6, 1.0  # filled mark (6 pt) with a ring in the surface colour; hollow mark

# Colour encodes the contract source, in this fixed order (the first three slots of the categorical palette).
# Validated for this use (every pair, white surface): worst colour-vision-deficiency distance dE 9.2 (deuteranopia,
# OKLab x100), worst normal-vision distance 24.0. #1BAF7A has 2.82:1 contrast against white, below 3:1, so the figure
# never relies on colour alone: every row is labelled, the legend names the groups, and the tables give every value.
# Text is in neutral inks, never in a series colour.
GROUPS = [("tcinitial", "2A78D6", "initial-only contract: C1 plain, C2 audited", ("initial_plain", "initial_audited")),
          ("tcfull", "EB6834", "correction-aware contract: C3 plain, C4 audited", ("full_plain", "full_audited")),
          ("tcbase", "1BAF7A", "baselines: B2 session-LLM, B1 repository tests", ("llm_freeform", "repo_tests"))]
INKS = {"tctext": "0B0B0B", "tcmuted": "52514E", "tcgrid": "D7D6D1", "tcguide": "EFEEEA"}
FAFR = {"name": "fresh_fa_fr_by_family", "labels": ("fig:fresh-fa", "fig:fresh-fr")}
DESIGN = {"name": "design_example", "labels": ("fig:design",)}
# The worked examples of Fig. 1 (restructure plan, part 6): per family its excerpts, each an exact substring of the
# scenario's turn, chosen to hold no path or name of the study's machines.
EXAMPLES = (("CS-04", {"U1": "add a `step` option to more_itertools.consecutive_groups",
                       "U2": "step=0 should raise a ValueError rather than doing something weird"}),
            ("CS-01", {"U1": "I'd like it to drop a trailing \".0\" so those read \"3 MB\" and \"1 KiB\"",
                       "U2": "Please keep the default output exactly as it was before"}))


def f2(x: float) -> str:
    """A coordinate: two decimals, no negative zero, so the drawing is byte-stable."""
    s = f"{x:.2f}"
    return "0.00" if s == "-0.00" else s


def group_of(cond: str) -> tuple[str, str, str, tuple[str, ...]]:
    return next(g for g in GROUPS if cond in g[3])


def text_tex(s: str) -> str:
    """Quoted text for TeX, every character as itself: specials escaped, straight quotes and backquotes kept."""
    rep = {"\\": "\\textbackslash{}", "_": "\\_", "%": "\\%", "&": "\\&", "#": "\\#", "$": "\\$", "{": "\\{", "}": "\\}",
           "~": "\\textasciitilde{}", "^": "\\textasciicircum{}", '"': "\\textquotedbl{}", "`": "\\textasciigrave{}",
           "'": "\\textquotesingle{}"}
    return "".join(rep.get(ch, ch) for ch in s)


def fresh_values(run: Path) -> tuple[dict[str, str], dict[str, str]]:
    """The fresh-v1 macros as make_tables.py --fresh computes them (``\\fv{key}``), and each one's source."""
    F = mt.fresh_inputs(run)
    led = mt.SectionLedger("", "")
    nums = mt.Numbers("fv", led)
    mt.fresh_run_numbers(F, led, nums)
    mt.fresh_design_numbers(F, led, nums)
    with tempfile.TemporaryDirectory() as d:
        mt.fresh_tables(F, led, nums, Path(d))
    srcs = {}
    for line in led.sections["numbers"]:
        m = re.match(r"^- \[numbers\] \\fv\{([^}]*)\}.* <- `(.*)`$", line)
        if m:
            srcs[m.group(1)] = m.group(2)
    return nums.values, srcs


# --------------------------------------------------------------------------- Fig. 2: false acceptance and false rejection

def fa_fr_points(a: dict, src: str, vals: dict[str, str]) -> tuple[list[str], list[dict], dict]:
    """Every plotted value with its source: per condition and family, the correction violators accepted (filled), the
    invalid units without a correction violation accepted (hollow, where a family has no correction violator), and the
    valid units rejected (the false-rejection block). Each family's counts of those units, for the panel titles."""
    fams = sorted(a["per_task"])
    if [c for c, _ in mt.ordered(a["per_family"])] != mt.ORDER:
        raise ValueError(f"{src}: per_family holds {sorted(a['per_family'])}, expected the six conditions of the protocol")
    pts, dens = [], {}
    for c in mt.ORDER:
        sh = mt.SHORT[c].lower()
        for t in fams:
            rows = a["per_task"][t][c]
            viol = [r for r in rows if r["label"] == "invalid" and r["negative_type"] == "correction_violating"]
            regr = [r for r in rows if r["label"] == "invalid" and r["negative_type"] != "correction_violating"]
            fr = a["per_family"][c][t]
            fields = {"violators": f"per_task.{t}.{c}[] (label invalid, negative_type correction_violating; outcome pass)",
                      "regression": f"per_task.{t}.{c}[] (label invalid, negative_type not correction_violating; outcome pass)"}
            for kind, sub, field in (("violators", viol, fields["violators"]), ("regression", regr, fields["regression"])):
                num, den = sum(r["outcome"] == "pass" for r in sub), len(sub)
                if dens.setdefault((t, kind), den) != den:
                    raise ValueError(f"{src}: {t} has different {kind} counts under different conditions")
                pts.append({"block": "fa", "kind": kind, "condition": c, "short": mt.SHORT[c], "task": t, "num": num,
                            "den": den, "value": None if not den else num / den, "field": field})
            if mt._frac(pts[-2]["num"], pts[-2]["den"]) != vals[f"cv.{sh}.{mt._fk(t)}"]:
                raise ValueError(f"{src}: {c} {t}: the violators accepted differ from \\fv{{cv.{sh}.{mt._fk(t)}}}")
            if dens.setdefault((t, "valid"), fr["fr_den"]) != fr["fr_den"]:
                raise ValueError(f"{src}: {t} has different valid counts under different conditions")
            pts.append({"block": "fr", "kind": "valid", "condition": c, "short": mt.SHORT[c], "task": t, "num": fr["fr_num"],
                        "den": fr["fr_den"], "value": None if not fr["fr_den"] else fr["fr_num"] / fr["fr_den"],
                        "field": f"per_family.{c}.{t}.fr_num, .fr_den"})
    for t in fams:
        if dens[(t, "violators")] and dens[(t, "regression")]:
            raise ValueError(f"{src}: {t} has correction violators and regression-only units; the panels show one kind each")
    return fams, pts, dens


def _marks(x: float, y: float, colour: str, kind: str) -> list[str]:
    """TikZ paths of one mark centred at (x, y): filled with a ring in the surface colour, or hollow."""
    if kind == "hollow":
        return [f"\\filldraw[fill=white,draw={colour},line width={STROKE}pt] ({f2(x)},{f2(y)}) circle[radius={HOLLOW}pt];"]
    return [f"\\fill[white] ({f2(x)},{f2(y)}) circle[radius={DOT + RING}pt];",
            f"\\fill[{colour}] ({f2(x)},{f2(y)}) circle[radius={DOT}pt];"]


def _extent(node_anchor: str, tag: str) -> str:
    """Write the x coordinate of a node anchor to the log, so that the layout can be checked after compiling."""
    return f"\\path ({node_anchor}); \\pgfgetlastxy{{\\tcx}}{{\\tcy}}\\typeout{{TC-EXTENT: {tag} \\tcx}}"


def _head(lines: list[str]) -> None:
    lines += [f"\\definecolor{{{k}}}{{HTML}}{{{v}}}" for k, v, _, _ in GROUPS]
    lines += [f"\\definecolor{{{k}}}{{HTML}}{{{v}}}" for k, v in INKS.items()]


def tikz_fa_fr(fams: list[str], pts: list[dict], dens: dict, failing: dict) -> tuple[str, list[tuple[str, str, float]]]:
    """The drawing, and the layout checks: (tag, "min" or "max", bound) for the x coordinate the log reports per tag."""
    n = len(fams)
    pw = (WIDTH - LABEL_W - (n - 1) * GAP) / n
    rel_y, y, prev = {}, 0.0, None
    for c in mt.ORDER:
        g = group_of(c)[0]
        if prev is not None:
            y -= ROW + (GROUP_GAP if g != prev else 0.0)
        rel_y[c], prev = y, g
    rows_h = -rel_y[mt.ORDER[-1]]
    checks: list[tuple[str, str, float]] = []
    lines = ["% Generated by `python paper/make_figures.py`; do not edit. Every value: paper/evidence_ledger_figures.md.",
             "\\begin{tikzpicture}[x=1pt,y=1pt,font=\\scriptsize,inner sep=0pt]"]
    _head(lines)
    # A block: panel titles (up to three lines, above TITLE), the rows, the tick labels and the axis label.
    title_h, axis_h = 34.0, 26.0
    block_h = title_h + ROW + 4 + rows_h + axis_h
    top, bottom = 46.0, -(26 + 2 * block_h)
    lines.append(f"\\path[use as bounding box] (0,{f2(bottom)}) rectangle ({f2(WIDTH)},{f2(top)});")
    # Legend: colour = contract source (two rows); shape = what the mark counts.
    for i, (col, _, text, _) in enumerate(GROUPS):
        if i == 1:
            lines.append(f"\\coordinate (K{i}) at ([xshift=10pt]G{i - 1}.east);")
        else:
            lines.append(f"\\coordinate (K{i}) at ({f2(LABEL_W + INSET - 3)},{f2(top - 7 - 12 * (i // 2))});")
        lines.append(f"\\fill[{col},rounded corners=1pt] ([yshift=-3pt]K{i}) rectangle ++(6pt,6pt);")
        lines.append(f"\\node[anchor=west,text=tctext] (G{i}) at ([xshift=9pt]K{i}) {{{text}}};")
        lines.append(_extent(f"G{i}.east", f"legend-colour-{i}-end"))
        checks.append((f"legend-colour-{i}-end", "max", WIDTH))
    ly = top - 31
    shapes = (("dot", DOT, "correction violators accepted (top); valid attempts rejected (bottom)"),
              ("hollow", HOLLOW, "regression only, in a family without correction violators"))
    for j, (shape, r, text) in enumerate(shapes):
        lines += [f"\\coordinate (M{j}) at ({f2(LABEL_W + INSET)},{f2(ly - 12 * j)});", f"\\begin{{scope}}[shift={{(M{j})}}]",
                  *_marks(0, 0, "tcmuted", shape), "\\end{scope}",
                  f"\\node[anchor=west,text=tctext] (S{j}) at ([xshift={r + 4}pt]M{j}) {{{text}}};"]
    lines.append(_extent("S1.east", "legend-shapes-end"))
    checks.append(("legend-shapes-end", "max", WIDTH))
    by = {(p["block"], p["kind"], p["condition"], p["task"]): p for p in pts}
    blocks = (("fa", "False acceptance (accepted / invalid attempts of the family)"),
              ("fr", "False rejection (rejected / valid attempts of the family)"))
    for b, (block, axis) in enumerate(blocks):
        y0 = -(26 + b * block_h)  # the block's top
        ytop = y0 - title_h  # the panels' top; the titles stand on it
        yrow0 = ytop - ROW / 2 - 2
        ys = {c: yrow0 + rel_y[c] for c in mt.ORDER}
        ybot = ys[mt.ORDER[-1]] - ROW / 2 - 2
        for i, c in enumerate(mt.ORDER):
            lines.append(f"\\node[anchor=east,text=tctext] (R{b}{i}) at ({f2(LABEL_W - 4)},{f2(ys[c])}) {{{mt.SHORT[c]}}};")
            lines.append(_extent(f"R{b}{i}.west", f"row-{b}-{i}"))
            checks.append((f"row-{b}-{i}", "min", 0.0))
        for k, t in enumerate(fams):
            x0 = LABEL_W + k * (pw + GAP)
            xa, xb = x0 + INSET, x0 + pw - INSET

            def xv(v: float, xa: float = xa, xb: float = xb) -> float:
                return xa + v * (xb - xa)

            if block == "fa":
                nv, nr = dens[(t, "violators")], dens[(t, "regression")]
                subs = [f"{nv} correction violators"] if nv else ["no correction violators", f"{nr} regression only"]
            else:
                subs = [f"{dens[(t, 'valid')]} valid attempts"]
            sub = "\\\\".join(f"{{\\scriptsize\\color{{tcmuted}}{s}}}" for s in subs)
            lines.append(f"% panel {block} {t}")
            lines.append(f"\\node[anchor=south,align=center,text=tctext,font=\\footnotesize] (T{b}{k}) at "
                         f"({f2((xa + xb) / 2)},{f2(ytop + 3)}) {{{mt.tex(t)}\\\\[1pt]{sub}}};")
            lines.append(_extent(f"T{b}{k}.west", f"title-{b}-{k}-west"))
            lines.append(_extent(f"T{b}{k}.east", f"title-{b}-{k}-east"))
            checks += [(f"title-{b}-{k}-west", "min", x0 - GAP / 2 + 1), (f"title-{b}-{k}-east", "max", x0 + pw + GAP / 2 - 1)]
            for c in mt.ORDER:
                lines.append(f"\\draw[tcguide,line width=0.4pt] ({f2(xa)},{f2(ys[c])}) -- ({f2(xb)},{f2(ys[c])});")
            for v, txt in ((0.0, "0"), (0.5, "0.5"), (1.0, "1")):
                lines.append(f"\\draw[tcgrid,line width=0.4pt] ({f2(xv(v))},{f2(ybot)}) -- ({f2(xv(v))},{f2(ytop)});")
                lines.append(f"\\node[anchor=north,text=tcmuted] at ({f2(xv(v))},{f2(ybot - 3)}) {{{txt}}};")
            lines.append(f"\\draw[tcmuted,line width=0.4pt] ({f2(xa - 2)},{f2(ybot)}) -- ({f2(xb + 2)},{f2(ybot)});")
            for i, c in enumerate(mt.ORDER):
                colour = group_of(c)[0]
                kinds = (("violators", "dot"), ("regression", "hollow")) if block == "fa" else (("valid", "dot"),)
                value = None
                for kind, shape in kinds:
                    p = by[(block, kind, c, t)]
                    if p["value"] is not None:
                        lines += _marks(xv(p["value"]), ys[c], colour, shape)
                        value = p["value"]
                if t in failing.get(c, ()) and value is not None:
                    right = value < 0.5
                    lines.append(f"\\node[anchor={'west' if right else 'east'},text=tcmuted,font=\\tiny\\itshape] (F{b}{k}{i}) "
                                 f"at ({f2(xv(value) + (DOT + 4 if right else -DOT - 4))},{f2(ys[c])}) {{fails its reference}};")
                    lines.append(_extent(f"F{b}{k}{i}.west", f"fail-{b}-{k}-{i}-west"))
                    lines.append(_extent(f"F{b}{k}{i}.east", f"fail-{b}-{k}-{i}-east"))
                    checks += [(f"fail-{b}-{k}-{i}-west", "min", xa - 2), (f"fail-{b}-{k}-{i}-east", "max", xb + 2)]
        x_first, x_last = LABEL_W + INSET, LABEL_W + (n - 1) * (pw + GAP) + pw - INSET
        lines.append(f"\\node[anchor=north,text=tctext,font=\\footnotesize] (X{b}) at ({f2((x_first + x_last) / 2)},"
                     f"{f2(ybot - 13)}) {{{axis}}};")
        lines.append(_extent(f"X{b}.east", f"axis-{b}-east"))
        checks.append((f"axis-{b}-east", "max", WIDTH))
    lines.append("\\end{tikzpicture}")
    return "\n".join(lines) + "\n", checks


def caption_fa_fr(run_id: str, marker: str) -> str:
    """At most 60 words before the marker (restructure plan, part 6)."""
    return (f"False acceptance (top) and false rejection (bottom) per family and condition, run \\texttt{{{mt.tex(run_id)}}}, "
            "under rule D19's labels, each distinct graded patch once. Filled marks: correction violators accepted, or valid "
            "attempts rejected; hollow marks: a family's invalid attempts when it has no correction violators. Colour: the contract "
            "source. Counts: Tables~\\ref{tab:fresh-family} and~\\ref{tab:fresh-cv}. " + marker)


# --------------------------------------------------------------------------- Fig. 1: the design and two worked examples

def example_facts(vals: dict[str, str], srcs: dict[str, str], scen: dict[str, dict]) -> tuple[dict, list[tuple[str, str, str]]]:
    """The two examples' excerpts and statements, each built from the fresh-v1 macros it states; and the ledger entries
    (what, value, source) of every number and excerpt."""
    led: list[tuple[str, str, str]] = []

    def v(key: str) -> str:
        led.append((f"\\fv{{{key}}}", vals[key], srcs[key]))
        return vals[key]

    out = {}
    for t, quotes in EXAMPLES:
        fk = mt._fk(t)
        turns, ssrc = scen[t]
        for turn, q in quotes.items():
            if q not in turns[turn]:
                raise ValueError(f"{ssrc}: the excerpt {q[:40]!r}... is not a substring of turn {turn}")
            led.append((f"{t} excerpt of {turn}", q, f"{ssrc} turns.{turn} (exact substring)"))
        lines = [f"$U_1$: ``{text_tex(quotes['U1'])}''", f"$U_2$: ``{text_tex(quotes['U2'])}''"]
        passes = v(f"ref.c1.{fk}") == "passes"
        n1 = v(f"checks.{fk}.c1")
        if int(v(f"corr.{fk}.superseded")):  # the correction retracts a requirement of the first request
            sup, sup_failed, failed = v(f"c1.{fk}.checks.superseded"), v(f"c1.{fk}.checks.superseded.failed"), v(f"ref.c1.{fk}.failed")
            lines.append(f"C1 encodes the retracted request: {sup} of its {n1} checks map to it"
                         + (", and exactly those fail on the reference." if sup == sup_failed == failed else
                            f"; {failed} of its checks fail on the reference, {sup_failed} of them mapped to it."))
            lines.append(f"C1 accepts {v(f'cv.c1.{fk}')} violators and rejects {v(f'c1.{fk}.fr')} valid attempts; "
                         f"C3 accepts {v(f'cv.c3.{fk}')}.")
            title = f"{t}: loud inversion" if not passes else t
        else:
            broken = v(f"beh.{fk}.broken")
            lines.append(f"First-request attempts that break {broken}: {v(f'cv.{fk}')}.")
            lines.append(f"C1 {'passes' if passes else 'fails'} its reference, has {v(f'c1.{fk}.checks.broken')} of its {n1} "
                         f"checks on {broken}, and accepts {v(f'cv.c1.{fk}')} violators; C3 accepts {v(f'cv.c3.{fk}')}.")
            accepted = int(vals[f"cv.c1.{fk}"].split("/")[0])
            title = f"{t}: silent loss" if passes and accepted else t
        lines.append(f"A reference gate {'keeps' if passes else 'drops'} C1.")
        out[t] = {"title": title, "lines": lines}
    return out, led


def tikz_design(ex: dict) -> tuple[str, list[tuple[str, str, float]]]:
    styles = ("box/.style={draw=tcgrid,line width=0.6pt,rounded corners=2pt,inner sep=4pt,text=tctext,align=left},"
              "cond/.style={draw=#1,line width=0.9pt,rounded corners=2pt,inner sep=2pt,text=tctext,minimum width=34pt,"
              "minimum height=13pt,align=center},arr/.style={->,draw=tcmuted,line width=0.6pt}")
    lines = ["% Generated by `python paper/make_figures.py`; do not edit. Every value: paper/evidence_ledger_figures.md.",
             f"\\begin{{tikzpicture}}[x=1pt,y=1pt,font=\\scriptsize,inner sep=0pt,{styles}]"]
    _head(lines)
    checks: list[tuple[str, str, float]] = []
    lines.append(f"\\path (0,12) -- ({f2(WIDTH)},12);  % the width is the line's; the height follows the content")
    lines.append("\\node[anchor=north west,text=tctext,font=\\footnotesize\\bfseries] at (0,10) {(a) Design};")
    lines.append("\\node[box,anchor=north west,text width=104pt] (S) at (0,-6) {\\textbf{Session} (a real agent run; scripted "
                 "user turns)\\\\[2pt]$U_1$: the first request\\\\$\\downarrow$ the pre-correction state\\\\$U_2$: the "
                 "correction\\\\$\\downarrow$ the reference: the session agent's final state};")
    lines.append("\\node[anchor=north west,text=tctext] (VT) at (130,-6) {\\textbf{Verifiers}, all frozen before any attempt};")
    lines.append("\\node[anchor=south,text=tcmuted] at (236,-30) {plain};")
    lines.append("\\node[anchor=south,text=tcmuted] at (290,-30) {audited};")
    lines.append("\\node[anchor=east,text=tctext,align=right] at (214,-39) {initial-only contract\\\\from $U_1$};")
    lines.append("\\node[cond=tcinitial] (C1) at (236,-39) {C1};")
    lines.append("\\node[cond=tcinitial] (C2) at (290,-39) {C2};")
    lines.append("\\node[anchor=east,text=tctext,align=right] at (214,-60) {correction-aware contract\\\\from the whole session};")
    lines.append("\\node[cond=tcfull] (C3) at (236,-60) {C3};")
    lines.append("\\node[cond=tcfull] (C4) at (290,-60) {C4};")
    lines.append("\\node[cond=tcbase,anchor=west,align=left] (B2) at (130,-84) {B2 session-LLM baseline:\\\\tests written from the "
                 "whole session};")
    lines.append("\\node[cond=tcbase,anchor=west,align=left] (B1) at (130,-108) {B1 repository tests\\\\at the reference state};")
    lines.append(_extent("B2.east", "b2-east"))
    lines.append(_extent("VT.east", "verifiers-title-east"))
    checks += [("b2-east", "max", 330.0), ("verifiers-title-east", "max", 330.0)]
    lines.append("\\node[box,anchor=north west,text width=118pt] (A) at (342,-6) {\\textbf{Fresh attempts}, each in its own "
                 "workspace, given\\\\$U_1$ only (\\texttt{u1}) or $U_1$ and $U_2$ (\\texttt{final})\\\\[2pt]graded by every "
                 "verifier; labels by rule D19: the reference checks and the regression norm\\\\[2pt]FA: invalid attempts "
                 "accepted\\\\FR: valid attempts rejected};")
    lines.append(_extent("A.east", "attempts-east"))
    checks.append(("attempts-east", "max", WIDTH))
    lines.append("\\draw[arr] (S.east) -- ++(18,0);")
    lines.append("\\draw[arr] (A.west) -- ++(-10,0);")
    for k, (t, _) in enumerate(EXAMPLES):
        x = 0 if k == 0 else WIDTH / 2 + 4
        e = ex[t]
        body = "\\\\[1pt]".join(e["lines"])
        lines.append(f"\\node[box,anchor=north west,text width={f2(WIDTH / 2 - 14)}pt] (P{k}) at ({f2(x)},-128) "
                     f"{{\\textbf{{({'bc'[k]}) {e['title']}}}\\\\[2pt]{body}}};")
        lines.append(_extent(f"P{k}.east", f"panel-{k}-east"))
        checks.append((f"panel-{k}-east", "max", WIDTH if k else WIDTH / 2 - 2))
    lines.append("\\end{tikzpicture}")
    return "\n".join(lines) + "\n", checks


def caption_design(run_id: str, marker: str) -> str:
    return ("The design (a), and two worked examples from the fresh-agent stratum, run "
            f"\\texttt{{{mt.tex(run_id)}}}, under rule D19's labels and read post hoc: (b) CS-04 and (c) CS-01, each with excerpts of its "
            "first request ($U_1$) and correction ($U_2$), quoted from the synthetic scenario files. Every number in the "
            "panels is a value of Tables~\\ref{tab:fresh-family}, \\ref{tab:fresh-behaviours} and~\\ref{tab:fresh-cv}. " + marker)


# --------------------------------------------------------------------------- output

def figure_env(name: str, labels: tuple[str, ...], cap: str) -> str:
    path = f"generated/figures/{name}.pdf"
    return ("% Generated by `python paper/make_figures.py`; do not edit. Every value: paper/evidence_ledger_figures.md.\n"
            "\\begin{figure}[t]\\centering\n"
            f"\\ifdefined\\includegraphics\\includegraphics[width=\\linewidth]{{{path}}}%\n"
            f"\\else\\unfilled{{figure {mt.tex(name)}: main.tex must load graphicx}}\\fi\n"
            f"\\caption{{{cap}}}" + "".join(f"\\label{{{lab}}}" for lab in labels) + "\n\\end{figure}\n")


STANDALONE = r"""\documentclass[11pt,border=0pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{amssymb}
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
        description="Draw the figures of a fresh-attempt run (TikZ, compiled with pdflatex) into paper/generated/figures/ "
                    "and write paper/evidence_ledger_figures.md. The outputs are replaced only after every figure has been "
                    "written; on any error every file is left as it was.")
    ap.add_argument("run", metavar="RUN_DIR", help="fresh-attempt run with analysis.json and manifest.json, e.g. results/runs/fresh-v1")
    a = ap.parse_args(argv)
    missing = [f for f in ("analysis.json", "analysis_sensitivity.json", "manifest.json", "results.jsonl")
               if not (Path(a.run) / f).is_file()]
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
                           "Every value plotted in `paper/generated/figures/*.pdf` and every number and excerpt of their panels, "
                           "titles and captions, with the file and field (or the fresh-v1 macro) it is read from. Generated by "
                           f"`{cmd}`; nothing is entered by hand. All labels are model proposals (D19); no human labels exist.")
    led.add("inputs", f"{src} sha256", sha, src)
    led.add("inputs", "run (manifest run_id); SOURCE_DATE_EPOCH (manifest finished_at)", f"{man['run_id']}; {epoch}",
            f"{msrc} run_id, finished_at")
    vals, srcs = fresh_values(run)
    FIG.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".make_figures-", dir=LEDGER.parent))
    try:
        out = tmp / "figures"
        out.mkdir()
        renderer = None
        # Fig. 2: false acceptance and false rejection per family.
        name = FAFR["name"]
        fams, pts, dens = fa_fr_points(an, src, vals)
        failing = {c: sorted(an["oracle_gated"]["conditions"][c]["dropped"]) for c in mt.ORDER}
        for p in pts:
            led.add(name, f"{p['block'].upper()} {p['kind']} {p['short']} {p['task']}",
                    f"{p['num']}/{p['den']}" + ("" if p["value"] is None else f" = {p['value']:.3f}") +
                    (" (not plotted: no unit)" if p["value"] is None else ""), f"{src} {p['field']}")
        for (t, kind), den in sorted(dens.items()):
            led.add(name, f"panel {t} title: {kind} units", den, f"{src} per_task.{t}.<every condition>[] (label, negative_type)"
                    if kind != "valid" else f"{src} per_family.<every condition>.{t}.fr_den")
        for c, ts in failing.items():
            if ts:
                led.add(name, f"annotation: {mt.SHORT[c]} fails the reference solution of", ", ".join(ts),
                        f"{src} oracle_gated.conditions.{c}.dropped")
        mark = mt.controlled_marker(an["n_families"], led, name, src)
        draw, checks = tikz_fa_fr(fams, pts, dens, failing)
        (out / f"{name}.tikz").write_text(draw)
        renderer = compile_pdf(out, name, epoch, checks)
        cap = caption_fa_fr(man["run_id"], mark)
        if len(re.sub(r"\\[A-Za-z]+(\{[^{}]*\})?|~", " ", cap[:cap.index(mark)]).split()) > 60:
            raise ValueError(f"{name}: the caption has more than 60 words before its marker")
        (out / f"{name}.tex").write_text(figure_env(name, FAFR["labels"], cap))
        (out / f"{name}.json").write_text(json.dumps(
            {"figure": name, "labels": list(FAFR["labels"]), "generated_by": cmd, "run_id": man["run_id"], "source": src,
             "source_sha256": sha, "labeling": "D19 (model proposals); no human labels", "families": fams,
             "conditions": [mt.SHORT[c] for c in mt.ORDER],
             "panels": [{"task": t, "violators": dens[(t, "violators")], "regression_only": dens[(t, "regression")],
                         "valid": dens[(t, "valid")]} for t in fams],
             "fails_reference": {mt.SHORT[c]: ts for c, ts in failing.items() if ts},
             "points": [{k: p[k] for k in ("block", "kind", "condition", "short", "task", "num", "den", "field")} |
                        {"value": None if p["value"] is None else round(p["value"], 6), "plotted": p["value"] is not None}
                        for p in pts]}, indent=1) + "\n")
        # Fig. 1: the design and the two worked examples.
        name = DESIGN["name"]
        scen = {}
        for t, _ in EXAMPLES:
            p = ROOT / "data" / "controlled" / "scenarios" / f"{t}.json"
            scen[t] = (json.loads(p.read_text())["turns"], mt.rel(p))
        ex, facts = example_facts(vals, srcs, scen)
        for what, value, how in facts:
            led.add(name, what, value, how)
        mark = mt.controlled_marker(an["n_families"], led, name, src)
        draw, checks = tikz_design(ex)
        (out / f"{name}.tikz").write_text(draw)
        renderer = compile_pdf(out, name, epoch, checks)
        (out / f"{name}.tex").write_text(figure_env(name, DESIGN["labels"], caption_design(man["run_id"], mark)))
        (out / f"{name}.json").write_text(json.dumps(
            {"figure": name, "labels": list(DESIGN["labels"]), "generated_by": cmd, "run_id": man["run_id"], "source": src,
             "source_sha256": sha, "examples": {t: {"title": e["title"]} for t, e in ex.items()},
             "stated": [{"what": w, "value": v, "source": h} for w, v, h in facts]}, indent=1) + "\n")
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
