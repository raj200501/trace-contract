"""paper/make_figures.py: Fig. 2 (false acceptance and false rejection per family in one figure) and Fig. 1 (the design
and two worked examples), restructure plan, part 6.

Checked on the recorded run results/runs/fresh-v1 (read only; the outputs go to a temporary directory): the files one
invocation writes, and that it deletes the files it did not write; every plotted value against the run's analysis and
the fresh-v1 macros; that a family without correction violators says so and shows its regression-only units as hollow
marks, so that its panel cannot read as the reverse of the finding; that the conditions that fail a family's reference
are annotated there and nowhere else; that no labeler mark is drawn; the caption's length and labels; that the worked
examples quote the scenario files exactly and state only numbers that are fresh-v1 macros; the privacy check; and that
the PDFs' bytes are reproducible. Needs pdflatex with TikZ; skipped without it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results" / "runs" / "fresh-v1"
spec = importlib.util.spec_from_file_location("make_figures", ROOT / "paper" / "make_figures.py")
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)
mt = mf.mt
cspec = importlib.util.spec_from_file_location("check_numbers_figures", ROOT / "paper" / "check_numbers.py")
cn = importlib.util.module_from_spec(cspec)
cspec.loader.exec_module(cn)

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is not installed")
NAMES = ("design_example", "fresh_fa_fr_by_family")


def _draw(tmp: Path) -> tuple[Path, str]:
    fig, ledger = tmp / "generated" / "figures", tmp / "evidence_ledger_figures.md"
    fig.mkdir(parents=True)
    (fig / "fresh_fa_by_family.tex").write_text("a figure of an earlier invocation\n")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mf, "FIG", fig)
        mp.setattr(mf, "LEDGER", ledger)
        mf.main([str(RUN)])
    return fig, ledger.read_text()


@pytest.fixture(scope="module")
def drawn(tmp_path_factory) -> dict:
    fig, ledger = _draw(tmp_path_factory.mktemp("figures"))
    vals, _ = mf.fresh_values(RUN)
    return {"fig": fig, "ledger": ledger, "vals": vals, "a": json.loads((RUN / "analysis.json").read_text())}


def test_one_invocation_writes_both_figures_and_deletes_what_it_did_not_write(drawn):
    assert sorted(p.name for p in drawn["fig"].iterdir()) == sorted(f"{n}.{s}" for n in NAMES for s in ("json", "pdf", "tex", "tikz"))
    for p in drawn["fig"].iterdir():
        if p.suffix != ".pdf":
            mt._check_private(p.read_text(), p.name, digit_runs=False)
    mt._check_private(drawn["ledger"], "ledger", digit_runs=False)


def test_fig2_plots_the_violators_accepted_the_regression_only_units_and_the_false_rejections(drawn):
    rec = json.loads((drawn["fig"] / "fresh_fa_fr_by_family.json").read_text())
    a, vals = drawn["a"], drawn["vals"]
    assert rec["labels"] == ["fig:fresh-fa", "fig:fresh-fr"]
    panels = {p["task"]: p for p in rec["panels"]}
    assert (panels["CS-02"]["violators"], panels["CS-02"]["regression_only"]) == (0, 2)
    assert all(panels[t]["regression_only"] == 0 and panels[t]["violators"] > 0 for t in ("CS-01", "CS-03", "CS-04"))
    for p in rec["points"]:
        sh, fk = p["short"].lower(), mt._fk(p["task"])
        if p["kind"] == "violators" and p["den"]:
            assert f"{p['num']}/{p['den']}" == vals[f"cv.{sh}.{fk}"], p
        if p["kind"] == "valid":
            d = a["per_family"][p["condition"]][p["task"]]
            assert (p["num"], p["den"]) == (d["fr_num"], d["fr_den"]) and f"{p['num']}/{p['den']}" == vals[f"{sh}.{fk}.fr"]
        assert p["plotted"] == bool(p["den"])
        assert (f"- [fresh_fa_fr_by_family] {p['block'].upper()} {p['kind']} {p['short']} {p['task']} = {p['num']}/{p['den']}"
                in drawn["ledger"]), p


def test_fig2_s_family_without_violators_cannot_read_as_the_reverse_of_the_finding(drawn):
    tikz = (drawn["fig"] / "fresh_fa_fr_by_family.tikz").read_text()
    panels = dict(re.findall(r"^% panel (\w+ CS-\d+)\n(.*?)(?=^% panel |\\node\[anchor=north,text=tctext,font=\\footnotesize\] \(X)",
                             tikz, re.MULTILINE | re.DOTALL))
    hollow = {k: v.count("\\filldraw[fill=white") for k, v in panels.items()}
    assert hollow == {k: (6 if k == "fa CS-02" else 0) for k in panels}  # every condition, as a hollow mark, there only
    assert "no correction violators" in panels["fa CS-02"] and "2 regression only" in panels["fa CS-02"]
    filled = {k: len(re.findall(r"\\fill\[tc(?:initial|full|base)\]", v)) for k, v in panels.items()}
    assert filled["fa CS-02"] == 0 and all(n == 6 for k, n in filled.items() if k != "fa CS-02")
    assert "line join=miter" not in tikz  # no labeler diamonds: the labeler's view is in its table


def test_fig2_annotates_the_conditions_that_fail_a_family_s_reference(drawn):
    tikz = (drawn["fig"] / "fresh_fa_fr_by_family.tikz").read_text()
    failing = {(mt.SHORT[c], t) for c, d in drawn["a"]["oracle_gated"]["conditions"].items() for t in d["dropped"]}
    assert failing == {("C1", "CS-01"), ("C2", "CS-01")}
    assert tikz.count("{fails its reference}") == 2 * len(failing)  # in the false-acceptance and false-rejection panels


def test_fig2_s_caption_and_labels(drawn):
    tex = (drawn["fig"] / "fresh_fa_fr_by_family.tex").read_text()
    cap = re.search(r"\\caption\{(.*)\}\\label\{fig:fresh-fa\}\\label\{fig:fresh-fr\}", tex, re.DOTALL).group(1)
    marker = mt.CONTROLLED_MARKER.format(n=4)
    assert cap.endswith(marker)
    words = re.sub(r"\\[A-Za-z]+(\{[^{}]*\})?|~", " ", cap[:-len(marker)]).split()
    assert len(words) <= 60, len(words)
    assert tex.count("\\begin{figure}") == 1
    tikz = (drawn["fig"] / "fresh_fa_fr_by_family.tikz").read_text()
    for text in (cap, tikz):  # "attempt" or "graded patch" for what is graded, never "unit" (restructure plan, finding 13)
        assert not re.search(r"\bunits?\b", text)


def test_fig1_quotes_the_scenarios_and_states_only_fresh_v1_values(drawn):
    rec = json.loads((drawn["fig"] / "design_example.json").read_text())
    vals = drawn["vals"]
    stated = {s["what"]: s["value"] for s in rec["stated"]}
    for t in ("CS-01", "CS-04"):
        turns = json.loads((ROOT / "data" / "controlled" / "scenarios" / f"{t}.json").read_text())["turns"]
        for turn in ("U1", "U2"):
            assert stated[f"{t} excerpt of {turn}"] in turns[turn]
    for what, value in stated.items():
        if what.startswith("\\fv{"):
            assert vals[what[4:-1]] == value, what
    tikz = (drawn["fig"] / "design_example.tikz").read_text()
    panels = re.findall(r"\(P\d\) at .*?\{\\textbf\{\((?:b|c)\) (.*?)\};$", tikz, re.MULTILINE)
    assert len(panels) == 2
    numbers = {v for w, v in stated.items() if w.startswith("\\fv{")}
    for text in panels:
        body = "\\\\".join(x for x in text.split("\\\\") if "$U_" not in x)  # the excerpts are quoted text
        for tok in re.findall(r"\d+(?:/\d+)?", cn.reduce(body)):  # identifiers (C3, CS-04, D19) and lengths aside
            assert tok in numbers or tok in {v.split("/")[0] for v in numbers}, (tok, body)
    assert rec["examples"] == {"CS-04": {"title": "CS-04: silent loss"}, "CS-01": {"title": "CS-01: loud inversion"}}
    tex = (drawn["fig"] / "design_example.tex").read_text()
    assert "\\label{fig:design}" in tex and tex.rstrip().endswith("\\end{figure}")
    # Panel (a) says what the text says: a real agent run with scripted user turns, a correction-aware contract from the
    # whole session, and FA and FR over attempts; the caption cites the tables in their order.
    assert "a real agent run; scripted" in tikz and "correction-aware contract\\\\from the whole session" in tikz
    assert "synthetic;" not in tikz and not re.search(r"\bunits?\b", tikz)
    assert "Tables~\\ref{tab:fresh-family}, \\ref{tab:fresh-behaviours} and~\\ref{tab:fresh-cv}" in tex


def test_the_pdfs_are_reproducible(drawn, tmp_path):
    fig, _ = _draw(tmp_path)
    for n in NAMES:
        assert hashlib.sha256((fig / f"{n}.pdf").read_bytes()).digest() == \
            hashlib.sha256((drawn["fig"] / f"{n}.pdf").read_bytes()).digest(), n
