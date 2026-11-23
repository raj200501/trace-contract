"""paper/make_tables.py --natural-run: the per-family tables of a natural run in case-study mode (protocol §19.6, §20.3).

The mode reads a natural run's analysis.json (and its manifest's run id) and writes four tables, the number macros
(``\\nrv{key}``) and a ledger in which every table cell names the analysis.json fields it is made from, with their values.
Checked here: every cell against those fields, and every row re-derived from analysis.json alone; every number of the
.tex files in the ledger; no number pooled over the families; every term a cell uses in place of a value defined in its
caption; the size rule on the run's own accepted tasks (protocol §20.3) and the refusal of an analysis outside case-study
mode (the run grades 10 or more accepted tasks of its own), of one made under the superseded rule and of a run that is not
natural; each check of what the tables take for granted; the privacy check, its digit runs and its agent product names;
and that only the mode's own outputs change, and none on an error.

Synthetic fixtures only: the natural worlds of tests/test_analysis_natural.py (natural families in a scratch repository
and a hand-written run, analysed with ``analysis.analyze``; nothing is graded). The generator's outputs (``GEN``,
``LEDGER``) point at a temporary directory, so no tracked file can change. They check code behaviour and are not
research evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest
from natural_task_layout import (
    AGENT_ONLY_MARKERS,
    COMMENT_TEXT,
    HUNK_TEXT,
    ISSUE_TEXT,
    PR_TEXT,
    REPLY_TEXT,
)
from test_analysis_natural import SECRET_FINDING, build_world

from tracecontract.analysis import analyze

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_tables_natural_run", ROOT / "paper" / "make_tables.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

TABLES = ("natural_run_fa_fr", "natural_run_source_evidence", "natural_run_labeler", "natural_run_construction")
# The fields of the run as a whole that an entry may name: its id, its families, those of its second labeling, the size rule.
RUN_LEVEL = {"run_id", "natural.tasks", "independent_labeling.tasks", "meta.case_study.accepted_in_run",
             "meta.case_study.threshold"}
# Blocks that hold numbers pooled over the families (absent in case-study mode, or pooled by construction).
POOLED = ("conditions", "comparisons", "natural.cost.totals", "natural.cost.per_accepted_task", "natural.cost.s10_every_family",
          "natural.reliability.run")
# Digits that are names, not numbers: protocol sections, decision-log entries, conditions and stages, families, audit:v1.
LABELS = (r"\\S\d+(?:\.\d+)*", r"\bD\d+\b", r"\b[BCS]\d+a?\b", r"\bNP-\d+\b", r"audit:v\d+", r"decision \d+")
ENTRY = re.compile(r"^- \[(?P<table>[^\]]+)\] (?P<what>.+?) = (?P<value>.*) <- `(?P<src>[^`]*)`$")
FIELD = re.compile(r"([A-Za-z0-9_/-]+(?:\.[A-Za-z0-9_/-]+)*)=")
ABSENT = object()
# The command documented in README.md (Reproduce) for the pilot's tables, as tests/test_make_tables.py runs it.
README_ARGS = ["results/runs/pilot-v0.3.3", "--compare", "results/runs/pilot-v0.3.2", "results/runs/pilot-v0.3.1",
               "results/runs/pilot-v0.3", "results/runs/pilot-v0.2", "results/runs/pilot-v0.2-h2"]


@dataclass(frozen=True)
class Made:
    root: Path  # the scratch directory of the world
    run: Path  # the run directory, data/natural/runs/natural-pr-v1
    a: dict  # analysis.json
    m: dict  # manifest.json
    out: Path  # the mode's tables: paper/generated/natural_run
    ledger: str  # paper/evidence_ledger_natural_run.md
    fams: list[str]

    @property
    def docs(self) -> dict[str, dict]:
        return {f"{self.run.name}/analysis.json": self.a, f"{self.run.name}/manifest.json": self.m}


def _make(root: Path, construction: bool) -> Made:
    run, tasks = build_world(root / "repo", 3, construction=construction)
    analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    paper = root / "paper"
    (paper / "generated").mkdir(parents=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mt, "GEN", paper / "generated")
        mp.setattr(mt, "LEDGER", paper / "evidence_ledger.md")
        mt.main(["--natural-run", str(run)])
    return Made(root, run, json.loads((run / "analysis.json").read_text()), json.loads((run / "manifest.json").read_text()),
                paper / "generated" / "natural_run", (paper / "evidence_ledger_natural_run.md").read_text(),
                [t.task_id for t in tasks])


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Made:
    """Three families with their construction records (audits, B3 taken out in NP-92, the reference checks' status)."""
    return _make(tmp_path_factory.mktemp("built"), True)


@pytest.fixture(scope="module")
def plain(tmp_path_factory) -> Made:
    """Three families with no construction record; the run grades neither C2 nor B2."""
    return _make(tmp_path_factory.mktemp("plain"), False)


@pytest.fixture(params=["built", "plain"])
def made(request) -> Made:
    return request.getfixturevalue(request.param)


@pytest.fixture
def outputs(tmp_path, monkeypatch) -> Path:
    """Stand-ins for paper/: the pilot's tables and ledger, the other modes' subdirectories and ledgers, an exploratory
    table, and a stale table and ledger of this mode."""
    paper = tmp_path / "paper"
    gen = paper / "generated"
    for sub in ("exploratory", "fresh", "natural", "natural_run"):
        (gen / sub).mkdir(parents=True)
    (gen / "results_summary.tex").write_text("a pilot table\n")
    (gen / "exploratory" / "per_family_table.tex").write_text("written by scripts/exploratory_reanalysis.py\n")
    (gen / "fresh" / "numbers.tex").write_text("fresh-v1's macros\n")
    (gen / "natural" / "numbers.tex").write_text("the screening's macros\n")
    (gen / "natural_run" / "stale.tex").write_text("a table that no current input produces\n")
    for name in ("evidence_ledger.md", "evidence_ledger_fresh.md", "evidence_ledger_natural.md", "evidence_ledger_natural_run.md"):
        (paper / name).write_text(f"{name} from an earlier invocation\n")
    monkeypatch.setattr(mt, "GEN", gen)
    monkeypatch.setattr(mt, "LEDGER", paper / "evidence_ledger.md")
    return paper


def _tree(d: Path) -> dict[str, str]:
    """Every file under ``d`` (hidden ones included) with its sha256."""
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


def _unchanged(paper: Path, before: dict[str, str]) -> None:
    assert _tree(paper) == before
    assert not list(paper.glob(".make_tables-*")), "the temporary directory was left behind"


# --------------------------------------------------------------------------- reading the outputs


def entries(ledger: str) -> list[dict]:
    """The ledger's entries: table, what, value and source."""
    out = []
    for line in ledger.splitlines():
        if line.startswith("- ["):
            m = ENTRY.match(line)
            assert m, line
            out.append(m.groupdict())
    return out


def fields(src: str) -> tuple[str, list[tuple[str, object]]]:
    """The file an entry's source names and its fields, ``(dot path, JSON value or ABSENT)``."""
    file, _, rest = src.partition(" ")
    out: list[tuple[str, object]] = []
    i, dec = 0, json.JSONDecoder()
    while i < len(rest):
        m = FIELD.match(rest, i)
        assert m, (src, i)
        i = m.end()
        if rest.startswith("absent", i):
            value, i = ABSENT, i + len("absent")
        else:
            value, i = dec.raw_decode(rest, i)
        out.append((m.group(1), value))
        if i < len(rest):
            assert rest.startswith("; ", i), src
            i += 2
    return file, out


def resolve(doc: dict, path: str) -> object:
    x: object = doc
    for k in path.split("."):
        if not isinstance(x, dict) or k not in x:
            return ABSENT
        x = x[k]
    return x


def parse_table(text: str) -> tuple[str, list[str], list[list[str]]]:
    """A generated table's caption, header cells and rows (each row's label first), without the layout commands."""
    caption = re.search(r"\\caption\{(.*)\}\\label\{", text, re.DOTALL).group(1)
    head, body = re.search(r"\\toprule (.*?) \\\\\\midrule\n(.*)\n\\bottomrule", text, re.DOTALL).groups()
    rows = []
    for line in body.split("\n"):
        line = re.sub(r" (?:\\\\|\\tabularnewline)(?:\\midrule)?$", "", line)
        cells = line.split(" & ")
        assert all(c.startswith(mt.NRTable.RAGGED) for c in cells), line  # every cell of these tables wraps
        rows.append([c.removeprefix(mt.NRTable.RAGGED) for c in cells])
    return caption, head.split(" & "), rows


def cells(made: Made | Path, name: str) -> dict[tuple[str, str], str]:
    """``{(row label, family): cell}`` of one table (of a world, or of the outputs in a directory)."""
    _, head, rows = parse_table(((made if isinstance(made, Path) else made.out) / f"{name}.tex").read_text())
    return {(r[0], f): c for r in rows for f, c in zip(head[1:], r[1:])}


def num(v: object) -> str:
    """A recorded count or time as a reader writes it: rounded, with thousands separators; n/a for null; -- when absent."""
    return "--" if v is ABSENT else "n/a" if v is None else f"{round(v):,}".replace(",", "{,}")


def words(code: str) -> str:
    return code.replace("_", " ")


def _mutated(built: Made, tmp_path: Path, mutate) -> Path:
    """A copy of the built world's run whose analysis.json ``mutate`` has changed."""
    copy = tmp_path / "mutated" / built.run.name
    shutil.copytree(built.run, copy)
    a = json.loads((copy / "analysis.json").read_text())
    mutate(a)
    (copy / "analysis.json").write_text(json.dumps(a))
    return copy


def numbers(text: str, fs: list[tuple[str, object]] = ()) -> set[str]:
    """The numbers a text states, beside names (:data:`LABELS`) and the strings of its fields (ids such as the run's)."""
    for _, v in fs:
        if isinstance(v, str):
            text = text.replace(v, " ")
    for pat in LABELS:
        text = re.sub(pat, " ", text)
    return set(re.findall(r"\d+", text.replace("{,}", "")))


def derivable(fs: list[tuple[str, object]]) -> set[str]:
    """The numbers that fields hold: their counts and times (rounded) and the lengths of their lists and maps."""
    out: set[str] = set()

    def walk(v: object) -> None:
        if v is ABSENT or v is None or isinstance(v, (bool, str)):
            return
        if isinstance(v, (int, float)):
            out.add(str(round(v)))
            return
        out.add(str(len(v)))
        for x in (v.values() if isinstance(v, dict) else v):
            walk(x)

    for _, v in fs:
        walk(v)
    return out


def check_fields(made: Made, e: dict, family: str | None) -> list[tuple[str, object]]:
    """An entry's fields hold the values it records, in the file it names; each belongs to ``family`` (any one family
    when None), or to the run; none lies in a pooled block."""
    file, fs = fields(e["src"])
    assert fs and file in made.docs, e
    owners_all = set()
    for path, v in fs:
        got = resolve(made.docs[file], path)
        assert (got is ABSENT) if v is ABSENT else got == v, (e["what"], path, got, v)
        assert not any(path == p or path.startswith(p + ".") for p in POOLED), (e["what"], path)
        owners = {f for f in made.fams for comp in path.split(".") if comp == f or comp.startswith(f + "/")}
        assert len(owners) == 1 or (not owners and path in RUN_LEVEL), (e["what"], path)
        owners_all |= owners
    assert owners_all <= ({family} if family else owners_all) and len(owners_all) <= 1, (e["what"], owners_all)
    return fs


# --------------------------------------------------------------------------- every cell, every number, nothing pooled


def test_every_cell_is_made_from_the_fields_its_ledger_entry_names(made):
    led = entries(made.ledger)
    for name in TABLES:
        _, head, rows = parse_table((made.out / f"{name}.tex").read_text())
        assert head[1:] == made.fams  # one column per family, in the run's order; no pooled column
        own = {e["what"]: e for e in led if e["table"] == name and not e["what"].startswith("caption | ")}
        seen = set()
        for label, *values in rows:
            assert len(values) == len(made.fams) and not numbers(label), (name, label)
            for fam, cell in zip(made.fams, values):
                e = own[f"{label} | {fam}"]
                seen.add(e["what"])
                assert e["value"] == cell, e
                fs = check_fields(made, e, fam)
                assert numbers(cell, fs) <= derivable(fs), (e["what"], cell, fs)
        assert seen == set(own), set(own) - seen  # no cell entry without its cell


def test_every_number_of_the_tex_files_is_in_the_ledger(made):
    led = entries(made.ledger)
    for name in TABLES:
        caption, _, _ = parse_table((made.out / f"{name}.tex").read_text())
        caps = [e for e in led if e["table"] == name and e["what"].startswith("caption | ")]
        for e in caps:
            assert all(p in RUN_LEVEL for p, _ in check_fields(made, e, None)), e
        text = caption
        for v in sorted((e["value"] for e in caps if not e["value"].isdigit()), key=len, reverse=True):
            text = text.replace(v, " ")
        assert numbers(text) <= {e["value"] for e in caps if e["value"].isdigit()}, name
    tex = (made.out / "numbers.tex").read_text()
    macros = dict(re.findall(r"^\\expandafter\\gdef\\csname nrv:([^\\]+)\\endcsname\{(.*)\}$", tex, re.MULTILINE))
    ledgered = {re.match(r"\\nrv\{([^}]+)\}", e["what"]).group(1): e for e in led if e["table"] == "numbers"}
    assert macros and macros.keys() == ledgered.keys()
    assert len(tex.splitlines()) == len(macros) + 3  # three comment lines, then one definition per macro
    for key, value in macros.items():
        e = ledgered[key]
        assert e["value"] == value, key
        fs = check_fields(made, e, None)
        assert numbers(value, fs) <= derivable(fs), (key, value, fs)
    assert {"run", "families", "accepted", "threshold", "c1.np90.fa", "c1.np90.fr", "se.c1.np90", "il.np90.status",
            "il.np90.pool.agree", "cost.np90.turns"} <= set(macros)
    assert (macros["run"], macros["families"], macros["accepted"], macros["threshold"]) == ("natural-pr-v1", "3", "3", "10")
    assert sorted(p.name for p in made.out.iterdir()) == sorted([*(f"{n}.tex" for n in TABLES), "numbers.tex"])


def test_nothing_is_pooled_over_the_families(made):
    texts = "\n".join(p.read_text() for p in made.out.iterdir())
    assert "\\%" not in texts and "$p" not in texts and "\\pm" not in texts  # no rate in percent, no p-value, no interval
    led = entries(made.ledger)
    shown = [e["value"] for e in led if e["table"] in (*TABLES, "numbers") and not e["what"].startswith("caption | ")]
    fractions = {x for v in shown for x in re.findall(r"\d+/\d+", v)}
    tokens = {x for v in shown for x in re.findall(r"\d+", v.replace("{,}", ""))}
    a = made.a
    views = {**a["per_family"], **a.get("secondary", {}).get("per_family", {})}
    per_family = {f"{d[m + '_num']}/{d[m + '_den']}" for pf in views.values() for d in pf.values() for m in ("fa", "fr")}
    for c, pf in views.items():  # each condition's FA and FR summed over the families appear nowhere
        for m in ("fa", "fr"):
            pooled = f"{sum(d[m + '_num'] for d in pf.values())}/{sum(d[m + '_den'] for d in pf.values())}"
            assert pooled in per_family or pooled not in fractions, (c, m, pooled)
    cost = a["natural"]["cost"]
    own = {str(round(f[k])) for f in cost["families"].values() for k in ("turns", "tool_calls", "wall_s", "grading_wall_s")}
    for block in ("totals", "per_accepted_task"):
        for k in ("turns", "tool_calls", "wall_s", "grading_wall_s"):
            v = str(round(cost[block][k]))
            assert v in own or v not in tokens, (block, k, v)


# --------------------------------------------------------------------------- what the cells say

ROW = {"initial_plain": "C1 initial, plain", "initial_audited": "C2 initial, audited", "full_plain": "C3 full, plain",
       "full_audited": "C4 full, audited", "llm_freeform": "B2 full-session LLM", "repo_tests": "B1 repository tests",
       "diff_derived": "B3 diff-derived (secondary)"}


def test_the_cells_follow_the_analysis(made):
    """The rates, the source evidence, the second labeling's counts and the cost, derived here from analysis.json alone."""
    a = made.a

    def frac(n: int, d: int) -> str:
        return f"{n}/{d}" if d else "n/a"

    t1, t2 = cells(made, "natural_run_fa_fr"), cells(made, "natural_run_source_evidence")
    t3, t4 = cells(made, "natural_run_labeler"), cells(made, "natural_run_construction")
    views = {**a["per_family"], **a.get("secondary", {}).get("per_family", {})}
    se = {**a["source_evidence"]["per_family"], **a["source_evidence"].get("secondary_per_family", {})}
    for c, row in ROW.items():
        if c not in views:
            assert not [r for r, _ in t1 if r == row] and not [r for r, _ in t2 if r == row], c
            continue
        for f in made.fams:
            d = views[c].get(f)
            dagger = "$^{\\dagger}$" if f in a["oracle_gated"]["conditions"][c]["dropped"] else ""
            want = "--" if d is None else f"{frac(d['fa_num'], d['fa_den'])} $\\cdot$ {frac(d['fr_num'], d['fr_den'])}{dagger}"
            assert t1[(row, f)] == want, (c, f)
            x = se.get(c, {}).get(f, {}).get("invalid")
            want = ("--" if not x or not x["n"] else ("accepted" if x["accepted"] else "rejected") if x["n"] == 1
                    else f"{x['accepted']}/{x['n']} accepted")
            (pre,) = [p for p in a["source_evidence"]["pre_review"].values() if p["family_id"] == f]
            if want == "rejected" and pre["outcomes"].get(c, "task_failure") != "task_failure":
                want += f" ({words(pre['outcomes'][c])})"
            assert t2[(row, f)] == want, (c, f)
    il = a["independent_labeling"]
    for f in made.fams:
        n = il["labels_per_family"][f]
        for v in ("valid", "invalid", "ambiguous"):
            assert t3[(f"Held-out candidates labelled {v}", f)] == str(n[v])
        assert t3[("Held-out candidates not graded", f)] == str(n["not_graded"])
        nat = il["agreement"]["per_family"][f]["natural"]
        for row, part in (("Agreement with D19, held-out pool", "generated_after_labeler"),
                          ("Agreement with D19, pre-review states", "existed_before_labeler")):
            g = nat[part]
            assert t3[(row, f)] == f"{g['agree']}/{g['n_decided_by_both']} ({g['n_units']})", (row, f)
        o = nat["generated_after_labeler"]["order"]
        assert t3[("Pool generated after the labeler was frozen", f)] == (
            f"{o['after']} of {o['candidates']}" + (f"; not after it {len(o['not_after'])}" if o["not_after"] else "")
            + (f"; not shown {len(o['not_shown'])}" if o["not_shown"] else ""))
        lab = a["natural"]["families"][f]["labeler"]
        assert t3[("Labeler status (round)", f)] == (("not recorded" if lab["status"] is None else lab["status"])
                                                      + (f" ({lab['round']})" if "round" in lab else ""))
        assert t3[("In the second labeling", f)] == ("left out" if f in il["left_out"] else "graded" if f in il["tasks"]
                                                      else "not graded")
        (pre,) = [x for x in a["source_evidence"]["pre_review"].values() if x["family_id"] == f]
        assert t2[("Its D19 label", f)] == (pre["d19"] or "none")
        assert t2[("Its second label (the labeler's outcome)", f)] == (
            "left out" if pre["independent_label_left_out"] else "not graded" if pre["independent_label_outcome"] is None
            else f"{pre['independent_label'] or 'none'} ({words(pre['independent_label_outcome'])})")
        assert t2[("The reference checks' outcome on it", f)] == (
            "not graded" if pre["reference_checks_outcome"] is None else words(pre["reference_checks_outcome"]))
        k = a["natural"]["cost"]["families"][f]
        assert t4[("Agent turns, tool calls", f)] == f"{k['turns']}, {k['tool_calls']}"
        assert t4[("Generated artifacts with a generation record", f)] == f"{k['recorded']} of {k['artifacts']}"
        assert t4[("Agent wall time (s)", f)] == num(k["wall_s"])
        assert t4[("Grading wall time (s)", f)] == num(k["grading_wall_s"])
        assert t4[("S10 build time (s)", f)] == num(k["s10_seconds"])
        construction_rows_follow_the_analysis(a, t4, f)
        rel = a["natural"]["reliability"]["families"][f]
        assert t1[("The run's pairs: graded, unresolved", f)] == f"{rel['pairs']}, {rel['unresolved']}"
        assert t1[("The run's pairs ending in an infrastructure outcome", f)] == (
            ", ".join(f"{n} {words(k)}" for k, n in rel["infrastructure"].items()) or "none")


def construction_rows_follow_the_analysis(a: dict, t4: dict[tuple[str, str], str], f: str) -> None:
    """The rows of the construction table of family ``f``, each derived here from analysis.json alone."""
    fam = a["natural"]["families"][f]
    con, rel = fam["construction"], a["natural"]["reliability"]["families"][f]
    assert t4[("Sample", f)] == (fam["sample"] or "--")
    ref = con["contracts"].get("reference", {})
    assert t4[("Reference contract: requirements, scored active, at the correction", f)] == ", ".join(
        num(ref.get(k, ABSENT)) for k in ("requirements", "scored_active", "at_correction"))
    assert t4[("Recovered contracts, scored active: initial-only, full-session", f)] == ", ".join(
        num(con["contracts"].get(v, {}).get("scored_active", ABSENT)) for v in ("initial_only", "full_session"))
    for row, ids in (("Checks: C1, C2, C3, C4", ("initial_plain", "initial_audited", "full_plain", "full_audited")),
                     ("Checks: B2, B1, B3", ("llm_freeform", "repo_tests", "diff_derived")),
                     ("Checks: reference checks, labeler", ("reference_check", "independent_label"))):
        assert t4[(row, f)] == ", ".join(num(con["checks"].get(c, ABSENT)) for c in ids), row
    for row, cond in (("C2 audit: revisions, result", "initial_audited"), ("C4 audit: revisions, result", "full_audited")):
        x = con["audits"].get(cond)
        codes = None if x is None else x["last_finding_codes"]
        want = ("--" if x is None else f"{x['revisions']}, passed" if x["passed"] else f"{x['revisions']}, failed"
                + (" (codes not recorded)" if codes is None else f" ({', '.join(words(c) for c in codes)})" if codes else ""))
        assert t4[(row, f)] == want, row
    b3 = con["b3"]
    assert t4[("B3", f)] == ("available" if b3["available"] else "taken out (no test kept)" if b3.get("taken_out")
                             else "not registered")
    b1 = fam["b1"]
    assert t4[("B1 by S10: available (checks)", f)] == (
        ("not recorded" if b1["available"] is None else "yes" if b1["available"] else "no")
        + ("" if b1["n_checks"] is None else f" ({b1['n_checks']})"))
    eq = fam["b1_equals_regression_norm"]
    word = ("not known" if eq["equal"] is None else "yes" if eq["equal"] else "in part" if eq["identical_files"] else "no")
    assert t4[("B1 equals D19's regression norm", f)] == (
        word if eq["equal"] is None else f"{word} ({eq['identical_files']} of {eq['b1_files']}; norm {eq['norm_files']})")
    rc = con["reference_checks"]
    assert t4[("Reference checks: status (fix rounds)", f)] == (
        "not recorded" if not rc["recorded"] else f"{rc['status'] or 'unrecognised status'} ("
        + ("fix rounds not recorded" if rc["fix_rounds"] is None else str(rc["fix_rounds"])) + ")")
    san = rel["sanity"]

    def passes(origin: str) -> str:
        x = san.get(origin, {}).get("reference_check", {})
        return f"{num(x.get('pass', ABSENT))}/{num(x.get('n', ABSENT))}"

    assert t4[("Reference checks in the run: reference, no-op passes", f)] == f"{passes('reference')}, {passes('noop')}"
    nm = fam["near_misses_on_correction"]
    assert t4[("Held-out near misses on the correction", f)] == f"{len(nm['on_correction'])} of {nm['near_misses']}"


def test_the_tables_of_a_run_with_its_construction_records(built):
    t1 = cells(built, "natural_run_fa_fr")
    assert [r for r, f in t1 if f == "NP-90"] == ["C1 initial, plain", "C2 initial, audited", "C3 full, plain", "C4 full, audited",
                                                   "B2 full-session LLM", "B1 repository tests", "B3 diff-derived (secondary)",
                                                   "The run's pairs: graded, unresolved",
                                                   "The run's pairs ending in an infrastructure outcome"]
    assert (t1[("The run's pairs: graded, unresolved", "NP-90")], t1[("The run's pairs ending in an infrastructure outcome",
                                                                      "NP-90")]) == ("72, 1", "none")
    # C1 fails its reference in NP-90, so the oracle-gated view drops the cell; B3 was taken out of NP-92.
    assert t1[("C1 initial, plain", "NP-90")] == "3/4 $\\cdot$ 0/2$^{\\dagger}$" and t1[("C1 initial, plain", "NP-91")] == "2/3 $\\cdot$ 0/2"
    assert t1[("C4 full, audited", "NP-90")] == "0/4 $\\cdot$ 1/2" and t1[("B3 diff-derived (secondary)", "NP-92")] == "--"
    t2 = cells(built, "natural_run_source_evidence")
    assert [t2[("C1 initial, plain", f)] for f in built.fams] == ["accepted"] * 3
    assert [t2[("C3 full, plain", f)] for f in built.fams] == ["rejected"] * 3 and t2[("B3 diff-derived (secondary)", "NP-92")] == "--"
    assert [t2[("Its D19 label", f)] for f in built.fams] == ["invalid", "ambiguous", "invalid"]
    assert [t2[("Its second label (the labeler's outcome)", f)] for f in built.fams] == [
        "ambiguous (pass)", "invalid (task failure)", "left out"]
    assert [t2[("The reference checks' outcome on it", f)] for f in built.fams] == ["task failure", "pass", "task failure"]
    t3 = cells(built, "natural_run_labeler")
    assert [t3[("Labeler status (round)", f)] for f in built.fams] == ["usable (1)", "usable (1)", "unusable (2)"]
    assert [t3[("In the second labeling", f)] for f in built.fams] == ["graded", "graded", "left out"]
    assert [t3[("Held-out candidates not graded", f)] for f in built.fams] == ["0", "0", "6"]
    assert t3[("Agreement with D19, pre-review states", "NP-90")] == "0/0 (1)"
    assert t3[("Agreement with D19, held-out pool", "NP-90")] == "5/5 (5)"
    assert t3[("Pool generated after the labeler was frozen", "NP-90")] == "0 of 5; not shown 5"  # no frozen_at in the fixture
    t4 = cells(built, "natural_run_construction")
    assert [t4[("C4 audit: revisions, result", f)] for f in built.fams] == [
        "3, failed (reference not passing)", "3, failed (false acceptance dev, uncovered requirement)", "1, passed"]
    assert [t4[("C2 audit: revisions, result", f)] for f in built.fams] == ["2, passed", "0, passed",
                                                                             "1, failed (codes not recorded)"]
    assert [t4[("B3", f)] for f in built.fams] == ["available", "available", "taken out (no test kept)"]
    assert [t4[("Reference checks: status (fix rounds)", f)] for f in built.fams] == ["usable (1)", "unusable (2)", "not recorded"]
    assert t4[("Reference contract: requirements, scored active, at the correction", "NP-90")] == "3, 3, 2"
    assert (t4[("Checks: C1, C2, C3, C4", "NP-90")], t4[("Checks: B2, B1, B3", "NP-92")]) == ("3, 4, 5, 6", "4, 2, --")
    assert t4[("Held-out near misses on the correction", "NP-90")] == "2 of 3"
    captions = [parse_table((built.out / f"{n}.tex").read_text())[0] for n in TABLES]
    for c in captions:
        assert "case-study mode" in c and "no pooled rate, no interval and no p-value" in c, c
        assert ("the run grades 3 accepted tasks of its own (its families accepted in the committed index), fewer than 10, "
                "and each run is reported on its own") in c and "\\texttt{natural-pr-v1}" in c
    assert "model-proposed labels" in captions[0] and "All labels are model proposals; no human labels exist." in captions[0]
    assert "Source evidence, not a human label" in captions[1] and "Not graded in this run" not in captions[0]


def test_the_tables_of_a_run_without_construction_records(plain):
    caption, _, _ = parse_table((plain.out / "natural_run_fa_fr.tex").read_text())
    assert caption.endswith("Not graded in this run: C2, B2.")
    t1 = cells(plain, "natural_run_fa_fr")
    assert {r for r, _ in t1} == {"C1 initial, plain", "C3 full, plain", "C4 full, audited", "B1 repository tests",
                                  "B3 diff-derived (secondary)", "The run's pairs: graded, unresolved",
                                  "The run's pairs ending in an infrastructure outcome"}
    t4 = cells(plain, "natural_run_construction")
    for f in plain.fams:
        assert (t4[("C2 audit: revisions, result", f)], t4[("B3", f)]) == ("--", "not registered")
        assert t4[("Reference checks: status (fix rounds)", f)] == "not recorded"
        assert t4[("Checks: C1, C2, C3, C4", f)] == "--, --, --, --"


def _rows_of(out: Path, name: str, label: str, fams: list[str]) -> list[str]:
    t = cells(out, name)
    return [t[(label, f)] for f in fams]


def test_the_cells_say_what_the_records_hold(outputs, built, tmp_path):
    """B1 that equals D19's regression norm in part says so (D64, decision 3); a reference-check status record that holds
    no usable or unusable status, or no integer fix rounds, says so, apart from a missing record; a rejection of a
    pre-review state that is no task failure names its outcome, and each family's infrastructure outcomes are given."""
    def mutate(a: dict) -> None:
        fams = a["natural"]["families"]
        fams["NP-90"]["b1_equals_regression_norm"] = {"equal": True, "identical_files": 2, "b1_files": 2, "norm_files": 2}
        fams["NP-91"]["b1_equals_regression_norm"] = {"equal": False, "identical_files": 2, "b1_files": 3, "norm_files": 4}
        fams["NP-92"]["b1_equals_regression_norm"] = {"equal": None, "why": "no B1 overlay"}
        fams["NP-90"]["construction"]["reference_checks"] = {"recorded": True, "status": None, "usable": None,
                                                             "fix_rounds": None}
        fams["NP-91"]["construction"]["reference_checks"] = {"recorded": True, "status": "usable", "usable": True,
                                                             "fix_rounds": None}
        a["source_evidence"]["pre_review"]["NP-91/NP-91-pre-review"]["outcomes"]["full_plain"] = "environment_failure"
        a["source_evidence"]["pre_review"]["NP-92/NP-92-pre-review"]["outcomes"]["full_plain"] = "unresolved"
        a["natural"]["reliability"]["families"]["NP-91"]["infrastructure"] = {"environment_failure": 1, "timeout": 2}

    mt.main(["--natural-run", str(_mutated(built, tmp_path, mutate))])
    out, fams = outputs / "generated" / "natural_run", built.fams
    assert _rows_of(out, "natural_run_construction", "B1 equals D19's regression norm", fams) == [
        "yes (2 of 2; norm 2)", "in part (2 of 3; norm 4)", "not known"]
    assert _rows_of(out, "natural_run_construction", "Reference checks: status (fix rounds)", fams) == [
        "unrecognised status (fix rounds not recorded)", "usable (fix rounds not recorded)", "not recorded"]
    assert _rows_of(out, "natural_run_source_evidence", "C3 full, plain", fams) == [
        "rejected", "rejected (environment failure)", "rejected (unresolved)"]
    assert _rows_of(out, "natural_run_fa_fr", "The run's pairs ending in an infrastructure outcome", fams) == [
        "none", "1 environment failure, 2 timeout", "none"]
    numbers_tex = (out / "numbers.tex").read_text()
    assert "\\csname nrv:b1.np91.norm\\endcsname{in part}" in numbers_tex
    assert "\\csname nrv:refchecks.np90.status\\endcsname{unrecognised status}" in numbers_tex
    fa_fr = parse_table((out / "natural_run_fa_fr.tex").read_text())[0]
    assert ("A rejection is any outcome other than a pass, so an infrastructure outcome (environment failure, verifier error "
            "or timeout) and an unresolved pair (repeats that disagree, protocol \\S15.3) count as rejections") in fa_fr
    source = parse_table((out / "natural_run_source_evidence.tex").read_text())[0]
    assert "one that is not a task failure" in source and "is named in brackets" in source


# The terms a cell can hold in place of a value; each one a table uses is defined in its caption, as "<term>: <meaning>".
TERMS = ("--", "n/a", "none", "not recorded", "not graded", "not known", "left out", "unrecognised status",
         "fix rounds not recorded", "codes not recorded")


def test_every_term_a_cell_uses_is_defined_in_its_caption(outputs, made, tmp_path):
    def mutate(a: dict) -> None:  # null values (n/a), a state with no D19 proposal (none) and no reference-check grade
        a["natural"]["cost"]["families"]["NP-90"]["turns"] = None
        a["natural"]["families"]["NP-91"]["labeler"]["status"] = None
        a["source_evidence"]["pre_review"]["NP-90/NP-90-pre-review"]["d19"] = None
        a["source_evidence"]["pre_review"]["NP-91/NP-91-pre-review"]["reference_checks_outcome"] = None

    mt.main(["--natural-run", str(_mutated(made, tmp_path, mutate))])
    out = outputs / "generated" / "natural_run"
    used_somewhere = set()
    for name in TABLES:
        caption, _, rows = parse_table((out / f"{name}.tex").read_text())
        used = {term for r in rows for c in r[1:] for term in TERMS if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", c)}
        used_somewhere |= used
        for term in used:
            assert f"{term}:" in caption, (name, term)
    assert {"--", "n/a", "none", "not recorded", "not graded", "left out"} <= used_somewhere


def test_an_index_the_analysis_could_not_read_is_said_in_the_captions(outputs, built, tmp_path):
    """Case-study mode also holds when the analysis could not read the committed index (accepted_in_run null)."""
    copy = tmp_path / "copy" / built.run.name
    shutil.copytree(built.run, copy)
    a = json.loads((copy / "analysis.json").read_text())
    a["meta"]["case_study"]["accepted_in_run"] = a["meta"]["case_study"]["accepted_in_index"] = None
    (copy / "analysis.json").write_text(json.dumps(a))
    mt.main(["--natural-run", str(copy)])
    out = outputs / "generated" / "natural_run"
    for name in TABLES:
        caption = parse_table((out / f"{name}.tex").read_text())[0]
        assert "the committed index cannot be read, so nothing shows that the run grades 10 accepted tasks" in caption, name
    assert ("- [natural_run_fa_fr] caption | the run's accepted tasks = not readable <- "
            "`natural-pr-v1/analysis.json meta.case_study.accepted_in_run=null`") in (outputs / "evidence_ledger_natural_run.md").read_text()
    assert "\\csname nrv:accepted\\endcsname{n/a}" in (out / "numbers.tex").read_text()


def test_each_run_is_reported_on_its_own(outputs, tmp_path):
    """Protocol §20.3: the size rule counts the run's own accepted tasks. Three families of the first sample, while the
    committed index counts 11 accepted tasks over both samples: the tables are written, and their captions and the macro
    give the run's 3, never the index's 11."""
    run, tasks = build_world(tmp_path / "own" / "repo", 3, extra_s11=tuple(f"NP-{60 + k}" for k in range(8)))
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    assert (a["meta"]["case_study"]["accepted_in_run"], a["meta"]["case_study"]["accepted_in_index"]) == (3, 11)
    mt.main(["--natural-run", str(run)])
    out = outputs / "generated" / "natural_run"
    for name in TABLES:
        caption = parse_table((out / f"{name}.tex").read_text())[0]
        assert "the run grades 3 accepted tasks of its own" in caption and "11" not in caption, name
    assert "\\csname nrv:accepted\\endcsname{3}" in (out / "numbers.tex").read_text()
    ledger = (outputs / "evidence_ledger_natural_run.md").read_text()
    assert "meta.case_study.accepted_in_run=3" in ledger and "accepted_in_index" not in ledger


def test_an_analysis_made_under_the_superseded_size_rule_is_refused(outputs, built, tmp_path):
    """An analysis whose size rule counted the committed index over both samples (no accepted_in_run, as analysis.py wrote
    before protocol §20.3 was implemented) is refused, and nothing is written."""
    copy = tmp_path / "old" / built.run.name
    shutil.copytree(built.run, copy)
    a = json.loads((copy / "analysis.json").read_text())
    del a["meta"]["case_study"]["accepted_in_run"]
    (copy / "analysis.json").write_text(json.dumps(a))
    before = _tree(outputs)
    with pytest.raises(SystemExit) as e:
        mt.main(["--natural-run", str(copy)])
    assert "meta.case_study has no accepted_in_run" in str(e.value.code) and "§20.3" in str(e.value.code)
    _unchanged(outputs, before)


# --------------------------------------------------------------------------- refusals, errors and the other outputs


def test_an_analysis_outside_case_study_mode_is_refused(outputs, tmp_path):
    run, tasks = build_world(tmp_path / "ten" / "repo", 10)
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    assert a["meta"]["case_study"]["applies"] is False
    before = _tree(outputs)
    with pytest.raises(SystemExit) as e:
        mt.main(["--natural-run", str(run)])
    assert "refused: the analysis is not in case-study mode" in str(e.value.code)
    assert "§15.6 and §15.7 apply in full" in str(e.value.code) and "not this mode's" in str(e.value.code)
    assert "the run grades 10 accepted tasks of its own" in str(e.value.code)
    _unchanged(outputs, before)


def _pop(d: dict, key: str) -> None:
    del d[key]


# What the tables take for granted, each broken in a copy of the built world's analysis: (mutation, error, message).
GUARDS = {
    "pooled conditions": (lambda a: a.update(conditions={"initial_plain": {}}), ValueError,
                          "case-study mode leaves conditions and comparisons empty, yet they hold pooled values"),
    "pooled comparisons": (lambda a: a.update(comparisons=[{"a": "initial_plain", "b": "full_plain"}]), ValueError,
                           "case-study mode leaves conditions and comparisons empty, yet they hold pooled values"),
    "a label policy with human labels": (lambda a: a["meta"].update(label_policy="human labels"), ValueError,
                                         "the captions say every label is a model proposal"),
    "a family of several tasks": (lambda a: a["natural"]["families"]["NP-91"].update(family_id="NP-90"), ValueError,
                                  "natural.families.NP-91.family_id is 'NP-90'"),
    "an unknown primary condition": (lambda a: a["per_family"].update(other_condition={}), ValueError,
                                     "expected C1-C4, B2 and B1, with B3 secondary"),
    "a primary condition among the secondary": (lambda a: a["secondary"]["per_family"].update(initial_plain={}), ValueError,
                                                "expected C1-C4, B2 and B1, with B3 secondary"),
    "a family outside the run": (lambda a: a["per_family"]["initial_plain"].update(
        {"NP-99": {"fa_num": 0, "fa_den": 1, "fr_num": 0, "fr_den": 1}}), ValueError, "which are not the run's families"),
    "a valid source-evidence label": (lambda a: a["source_evidence"]["per_family"]["full_plain"]["NP-90"]["valid"].update(n=1),
                                      ValueError, "a source-evidence label is invalid with respect to the correction"),
    "two pre-review states of a family": (lambda a: a["source_evidence"]["pre_review"].update(
        {"NP-90/NP-90-other": a["source_evidence"]["pre_review"]["NP-90/NP-90-pre-review"]}), ValueError,
        "source_evidence.pre_review holds 2 pre-review states of NP-90"),
    "no second labeling": (lambda a: _pop(a, "independent_labeling"), ValueError,
                           "the run did not grade the independent labeler"),
    "no oracle-gated view of a condition": (lambda a: _pop(a["oracle_gated"]["conditions"], "full_plain"), ValueError,
                                            "oracle_gated.conditions has no full_plain"),
    "no agreement of a family": (lambda a: _pop(a["independent_labeling"]["agreement"]["per_family"], "NP-92"), ValueError,
                                 ("independent_labeling.agreement.per_family.NP-92.natural.existed_before_labeler is not in "
                                  "the analysis")),
    "no generation order of a family's pool": (
        lambda a: _pop(a["independent_labeling"]["agreement"]["per_family"]["NP-91"]["natural"]["generated_after_labeler"],
                       "order"), ValueError, "does not record the pool's generation order"),
}


@pytest.mark.parametrize("case", sorted(GUARDS))
def test_what_the_tables_take_for_granted_is_checked(outputs, built, tmp_path, case):
    mutate, error, message = GUARDS[case]
    copy = _mutated(built, tmp_path, mutate)
    before = _tree(outputs)
    with pytest.raises(error, match=re.escape(message)):
        mt.main(["--natural-run", str(copy)])
    _unchanged(outputs, before)


def test_the_agent_name_check_applies(outputs, built, tmp_path):
    """An agent product name of the AIDev screening record (one that the generic model-name pattern does not catch) in a
    natural run's outputs is refused, and nothing is written. The name is read from the record, never written here."""
    record = json.loads((ROOT / mt.NATURAL_INPUTS["M0"]).read_text())

    def generic_only(name: str) -> bool:
        try:
            mt._check_private(f"a {name} b", "probe", digit_runs=False)
        except ValueError:
            return False
        return True

    names = [n for n in mt._agent_names(record) if n.isalnum() and generic_only(n)]
    assert names, "the screening record names no agent product that only the agent-name check catches"
    copy = tmp_path / "named" / built.run.name
    shutil.copytree(built.run, copy)
    m = json.loads((copy / "manifest.json").read_text())
    (copy / "manifest.json").write_text(json.dumps({**m, "run_id": f"natural-pr-{names[0]}"}))
    before = _tree(outputs)
    with pytest.raises(ValueError, match="refusing to write an agent product name"):
        mt.main(["--natural-run", str(copy)])
    _unchanged(outputs, before)


def test_the_screening_record_is_required_before_anything_is_written(outputs, built, tmp_path, monkeypatch, capsys):
    """Without the AIDev screening record no agent product name could be checked, so the mode stops while its arguments
    are read (exit status 2), as --natural does, and writes nothing."""
    monkeypatch.setattr(mt, "ROOT", tmp_path / "a checkout without the records")
    before = _tree(outputs)
    with pytest.raises(SystemExit) as e:
        mt.main(["--natural-run", str(built.run)])
    assert e.value.code == 2 and f"missing {mt.NATURAL_INPUTS['M0']}" in capsys.readouterr().err
    _unchanged(outputs, before)


def test_a_run_that_is_not_a_natural_run_is_refused(outputs):
    pilot = ROOT / "results" / "runs" / "pilot-v0.3.3"
    if not (pilot / "analysis.json").is_file():
        pytest.skip("the pilot run is not in this checkout")
    before = _tree(outputs)
    with pytest.raises(SystemExit) as e:
        mt.main(["--natural-run", str(pilot)])
    assert "is not the analysis of a natural PR-review run" in str(e.value.code)
    _unchanged(outputs, before)


def test_only_its_own_outputs_change(outputs, built):
    before = _tree(outputs)
    mt.main(["--natural-run", str(built.run)])
    after = _tree(outputs)

    def mine(k: str) -> bool:
        return k.startswith("generated/natural_run/") or k == "evidence_ledger_natural_run.md"

    assert {k: v for k, v in before.items() if not mine(k)} == {k: v for k, v in after.items() if not mine(k)}
    assert sorted(k for k in after if mine(k)) == sorted(["evidence_ledger_natural_run.md", "generated/natural_run/numbers.tex",
                                                          *(f"generated/natural_run/{n}.tex" for n in TABLES)])  # stale.tex is gone
    assert (outputs / "evidence_ledger_natural_run.md").read_text() == built.ledger
    assert not list(outputs.glob(".make_tables-*"))


def test_a_failure_changes_nothing(outputs, built, tmp_path):
    before = _tree(outputs)
    with pytest.raises(SystemExit) as e:  # no analysis.json: refused while the arguments are read
        mt.main(["--natural-run", str(tmp_path / "missing")])
    assert e.value.code == 2
    broken = tmp_path / "broken" / built.run.name
    shutil.copytree(built.run, broken)
    a = json.loads((broken / "analysis.json").read_text())
    del a["oracle_gated"]  # the first table fails after the run's numbers were put
    (broken / "analysis.json").write_text(json.dumps(a))
    with pytest.raises(KeyError):
        mt.main(["--natural-run", str(broken)])
    _unchanged(outputs, before)


def test_the_natural_privacy_check_applies(outputs, built, tmp_path):
    texts = built.ledger + "".join(p.read_text() for p in built.out.iterdir())
    assert str(built.root) not in texts and "/tmp/" not in texts and "/home/" not in texts  # the run is named by its name
    for secret in (ISSUE_TEXT, COMMENT_TEXT, REPLY_TEXT, HUNK_TEXT, PR_TEXT, *AGENT_ONLY_MARKERS, SECRET_FINDING):
        assert secret[:24] not in texts, secret[:24]
    copy = tmp_path / "copy" / built.run.name
    shutil.copytree(built.run, copy)
    m = json.loads((copy / "manifest.json").read_text())
    (copy / "manifest.json").write_text(json.dumps({**m, "run_id": "natural-pr-1234567"}))  # a digit run: an id
    before = _tree(outputs)
    with pytest.raises(ValueError, match="refusing to write a digit run of 7 or more"):
        mt.main(["--natural-run", str(copy)])
    _unchanged(outputs, before)


def test_the_pilot_tables_are_unchanged_beside_the_natural_run(outputs, built, monkeypatch):
    """With --natural-run beside the README's pilot command, the pilot's tables and ledger are still the tracked ones."""
    if sorted(p.parent.name for p in (ROOT / "tasks").glob("*/task.json")) != ["CS-01", "CS-02", "CS-03", "CS-04"]:
        pytest.skip("the pilot's tables cover every task directory; with tasks beyond the pilot's four they differ")
    monkeypatch.chdir(ROOT)
    mt.main([*README_ARGS, "--natural-run", str(built.run)])
    tracked = ROOT / "paper" / "generated"
    names = sorted(p.name for p in tracked.glob("*.tex"))
    assert sorted(p.name for p in mt.GEN.glob("*.tex")) == names
    for name in names:
        assert (mt.GEN / name).read_bytes() == (tracked / name).read_bytes(), name
    assert mt.LEDGER.read_bytes() == (ROOT / "paper" / "evidence_ledger.md").read_bytes()
    assert (outputs / "evidence_ledger_natural_run.md").read_text() == built.ledger
