"""paper/make_tables.py --natural-run: the per-family tables of a natural run in case-study mode (protocol §19.6, §20.3).

The mode reads a natural run's analysis.json (and its manifest's run id) and writes six tables, the number macros
(``\\nrv{key}``) and a ledger in which every table cell names the analysis.json fields it is made from, with their values.
Checked here: every cell against those fields, and every row re-derived from analysis.json alone; every number of the
.tex files in the ledger; no number pooled over the families; every term a cell uses in place of a value defined in its
caption; the size rule on the run's own accepted tasks (protocol §20.3) and the refusal of an analysis outside case-study
mode (the run grades 10 or more accepted tasks of its own), of one made under the superseded rule and of a run that is not
natural; each check of what the tables take for granted; the privacy check, its digit runs and its agent product names;
and that only the mode's own outputs change, and none on an error. Added after the final review of the manuscript: the
gate's marker on the cells of the table of the pre-review states (as the false-acceptance table marks them), that table's
rows of each condition's outcome on the family's reference solution and no-op, the coverage table (the reference
contract's correction requirements, and its coverage by each recovered contract under each mapper with the correction
requirements left uncovered, the recovered requirements that contradict it and those each contract marks superseded),
and the per-family keys naming the conditions that reject (or accept) every candidate of a family and those that pass
its no-op.

Synthetic fixtures only: the natural worlds of tests/test_analysis_natural.py (natural families in a scratch repository
and a hand-written run, analysed with ``analysis.analyze``; nothing is graded), with model mappings of their recovered
contracts written here and, in one world, outcomes changed so that some conditions tell no candidate apart. The
generator's outputs (``GEN``, ``LEDGER``) point at a temporary directory, so no tracked file can change. They check code
behaviour and are not research evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
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
from test_analysis_natural import (
    RUN_ID,
    SECRET_FINDING,
    build_world,
    d19_note,
    relabel_d19,
)

from tracecontract.analysis import D19_NO_REASON, D19_REPEATS_DISAGREE, analyze
from tracecontract.store import write_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_tables_natural_run", ROOT / "paper" / "make_tables.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

TABLES = ("natural_run_fa_fr", "natural_run_source_evidence", "natural_run_labeler", "natural_run_construction",
          "natural_run_sanity", "natural_run_coverage")
# The fields of the run as a whole that an entry may name: its id, its families, those of its second labeling, the size rule;
# its manifest's times, code revision, repeats, pilot flag and invocations, and the harness versions of its results.
RUN_LEVEL = {"run_id", "natural.tasks", "independent_labeling.tasks", "meta.case_study.accepted_in_run",
             "meta.case_study.threshold", "started_at", "finished_at", "code_revision", "repeats", "pilot", "invocations",
             "meta.harness_versions"}
# Macros whose values are formatted from a field, not counted (a date or time of day of a manifest's time, a revision's first
# characters, a harness version, the run's family ids): their digits are not counts, so
# test_the_run_s_facts_come_from_its_manifest checks each value against its field exactly.
FORMATTED = {"run.date", "run.started", "run.finished", "run.revision", "run.harness", "run.families"}
# Blocks that hold numbers pooled over the families (absent in case-study mode, or pooled by construction).
POOLED = ("conditions", "comparisons", "natural.cost.totals", "natural.cost.per_accepted_task", "natural.cost.s10_every_family",
          "natural.reliability.run")
# Digits that are names, not numbers: protocol sections, decision-log entries, conditions and stages, families, audit:v1,
# and the held-out pool's candidates (eval-alt-1, eval-nm-3; D64).
LABELS = (r"\\S\d+(?:\.\d+)*", r"\bD\d+\b", r"\b[BCS]\d+a?\b", r"\bNP-\d+\b", r"audit:v\d+", r"decision \d+",
          r"\beval-(?:alt|nm)-\d+\b")
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


def _make(root: Path, construction: bool, prepare=None) -> Made:
    """A world of three families, analysed, and the mode's outputs; ``prepare(tasks)`` changes the world before the analysis."""
    run, tasks = build_world(root / "repo", 3, construction=construction)
    if prepare is not None:
        prepare(tasks)
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


# The model mappings of the recovered contracts (analysis.contract_coverage reads contracts/mapping_<variant>.json, and
# mapping2_<variant>.json for the second mapper): (family, mapper, variant) -> (map, contradicts). The reference contract
# holds R-issue and its correction requirements R-corr (the review comment) and R-reply (the reply); the recovered ones
# hold R0, R1, ... (tests/test_analysis_natural.py, _construct). NP-91's second mapper did not map its initial-only contract.
MAPPINGS: dict[tuple[str, int, str], tuple[dict, dict]] = {
    **{(t, m, "initial_only"): ({"R0": ["R-issue"]}, {}) for t in ("NP-90", "NP-91", "NP-92") for m in (1, 2)},
    **{(t, m, "full_session"): ({"R0": ["R-issue"], "R1": ["R-corr"]}, {}) for t in ("NP-90", "NP-92") for m in (1, 2)},
    **{("NP-91", m, "full_session"): ({"R0": ["R-issue"], "R1": ["R-corr"], "R2": ["R-reply"]}, {}) for m in (1, 2)},
    ("NP-90", 2, "full_session"): ({"R0": ["R-issue"], "R1": ["R-corr"]}, {"R1": ["R-corr"]}),  # mapped, but contradicted
    ("NP-92", 2, "initial_only"): ({"R0": ["R-issue"], "R1": ["R-corr"]}, {}),  # the first request implies the correction
}
del MAPPINGS[("NP-91", 2, "initial_only")]


def _map_contracts(tasks) -> None:
    """Write :data:`MAPPINGS` into the families' contracts, as the mappers of P7 write them."""
    for nt in tasks:
        for (t, m, variant), (mapping, contradicts) in MAPPINGS.items():
            if t == nt.task_id:
                write_json({"mapper": f"fixture:mapper:{m}", "mapper_kind": "model", "map": mapping,
                            "contradicts": contradicts},
                           nt.task_dir / "contracts" / f"{'mapping' if m == 1 else 'mapping2'}_{variant}.json")


def _rewrite_outcomes(tasks, change) -> None:
    """Change the outcomes of the world's run before its analysis: ``change(family, verifier, kind, outcome)`` gives each
    pair's outcome (``kind``: the candidate's id without its family's, as tests/test_analysis_natural.py's GRADED names it)."""
    results = tasks[0].root / "data" / "natural" / "runs" / RUN_ID / "results.jsonl"
    rows = [json.loads(x) for x in results.read_text().splitlines() if x.strip()]
    for r in rows:
        r["outcome"] = change(r["task_id"], r["verifier_id"], r["candidate_id"].removeprefix(r["task_id"] + "-"), r["outcome"])
        r["reward"] = 1.0 if r["outcome"] == "pass" else 0.0
    results.write_text("".join(json.dumps(r) + "\n" for r in rows))


# The world in which some conditions tell no candidate apart (:func:`_undiscriminating`): the conditions that reject every
# candidate of a family, its reference solution and its valid alternatives included.
REJECT_ALL = {"NP-90": ("initial_plain", "initial_audited", "full_plain"), "NP-91": ("full_plain",),
              "NP-92": ("initial_plain", "full_audited")}


def _undiscriminating(tasks) -> None:
    """The world of :func:`built` with these outcomes changed: the conditions of :data:`REJECT_ALL` pass nothing in their
    family (C3's reference in NP-91 is unresolved: repeats that disagree, a rejection); B3 passes every candidate of NP-91,
    the no-op included; B1 rejects NP-92's no-op; and B2's no-op of NP-90 ends in an environment failure. B1 still passes
    every candidate of NP-90 and NP-91, as the world gives it."""
    def change(t: str, vid: str, kind: str, outcome: str) -> str:
        if vid in REJECT_ALL.get(t, ()):
            return "unresolved" if (t, vid, kind) == ("NP-91", "full_plain", "reference") else (
                "task_failure" if outcome == "pass" else outcome)
        if (t, vid) == ("NP-91", "diff_derived"):
            return "pass"
        return {("NP-92", "repo_tests", "noop-eval"): "task_failure",
                ("NP-90", "llm_freeform", "noop-eval"): "environment_failure"}.get((t, vid, kind), outcome)

    _rewrite_outcomes(tasks, change)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Made:
    """Three families with their construction records (audits, B3 taken out in NP-92, the reference checks' status) and
    the model mappings of their recovered contracts (:data:`MAPPINGS`)."""
    return _make(tmp_path_factory.mktemp("built"), True, _map_contracts)


@pytest.fixture(scope="module")
def plain(tmp_path_factory) -> Made:
    """Three families with no construction record; the run grades neither C2 nor B2."""
    return _make(tmp_path_factory.mktemp("plain"), False)


@pytest.fixture(scope="module")
def undiscriminating(tmp_path_factory) -> Made:
    """The world of :func:`built` whose run has conditions that tell no candidate of a family apart (:func:`_undiscriminating`)."""
    return _make(tmp_path_factory.mktemp("undiscriminating"), True, lambda tasks: (_map_contracts(tasks),
                                                                                    _undiscriminating(tasks)))


@pytest.fixture(params=["built", "plain", "undiscriminating"])
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


def macro_key(e: dict) -> str:
    """The key of a ledger entry of the numbers section (``\\nrv{key} (what)``)."""
    return re.match(r"\\nrv\{([^}]+)\}", e["what"]).group(1)


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
    ledgered = {macro_key(e): e for e in led if e["table"] == "numbers"}
    assert macros and macros.keys() == ledgered.keys()
    assert len(tex.splitlines()) == len(macros) + 3  # three comment lines, then one definition per macro
    for key, value in macros.items():
        e = ledgered[key]
        assert e["value"] == value, key
        fs = check_fields(made, e, None)
        assert key in FORMATTED or numbers(value, fs) <= derivable(fs), (key, value, fs)
    assert {"run", "families", "accepted", "threshold", "c1.np90.fa", "c1.np90.fr", "se.c1.np90", "il.np90.status",
            "il.np90.pool.agree", "cost.np90.turns"} <= set(macros)
    assert (macros["run"], macros["families"], macros["accepted"], macros["threshold"]) == ("natural-pr-v1", "3", "3", "10")
    assert sorted(p.name for p in made.out.iterdir()) == sorted([*(f"{n}.tex" for n in TABLES), "numbers.tex"])


def test_nothing_is_pooled_over_the_families(made):
    texts = "\n".join(p.read_text() for p in made.out.iterdir())
    assert "\\%" not in texts and "$p" not in texts and "\\pm" not in texts  # no rate in percent, no p-value, no interval
    led = entries(made.ledger)
    shown = [e["value"] for e in led if e["table"] in (*TABLES, "numbers") and not e["what"].startswith("caption | ")
             and not (e["table"] == "numbers" and macro_key(e) in FORMATTED)]  # a revision's hex digits are no count
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

ROW = {"initial_plain": "C1 initial-only, plain", "initial_audited": "C2 initial-only, audited", "full_plain": "C3 correction-aware, plain",
       "full_audited": "C4 correction-aware, audited", "llm_freeform": "B2 session-LLM baseline", "repo_tests": "B1 repository tests",
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
            # The cell of a verifier that does not pass the family's reference carries the gate's marker, as in Table 8.
            assert t2[(row, f)] == want + (dagger if want != "--" else ""), (c, f)
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
    assert t4[("Recovered contracts, scored active: initial-only, correction-aware", f)] == ", ".join(
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
    assert [r for r, f in t1 if f == "NP-90"] == ["C1 initial-only, plain", "C2 initial-only, audited", "C3 correction-aware, plain", "C4 correction-aware, audited",
                                                   "B2 session-LLM baseline", "B1 repository tests", "B3 diff-derived (secondary)",
                                                   "The run's pairs: graded, unresolved",
                                                   "The run's pairs ending in an infrastructure outcome"]
    assert (t1[("The run's pairs: graded, unresolved", "NP-90")], t1[("The run's pairs ending in an infrastructure outcome",
                                                                      "NP-90")]) == ("72, 1", "none")
    # C1 fails its reference in NP-90, so the oracle-gated view drops the cell; B3 was taken out of NP-92.
    assert t1[("C1 initial-only, plain", "NP-90")] == "3/4 $\\cdot$ 0/2$^{\\dagger}$" and t1[("C1 initial-only, plain", "NP-91")] == "2/3 $\\cdot$ 0/2"
    assert t1[("C4 correction-aware, audited", "NP-90")] == "0/4 $\\cdot$ 1/2" and t1[("B3 diff-derived (secondary)", "NP-92")] == "--"
    t2 = cells(built, "natural_run_source_evidence")
    # C1 fails its reference in NP-90, so its cell there carries the gate's marker, as in Table 8; its macro does not.
    assert [t2[("C1 initial-only, plain", f)] for f in built.fams] == ["accepted$^{\\dagger}$", "accepted", "accepted"]
    assert [macros_of(built.out)[f"se.c1.{f.lower().replace('-', '')}"] for f in built.fams] == ["accepted"] * 3
    assert [t2[("C3 correction-aware, plain", f)] for f in built.fams] == ["rejected"] * 3 and t2[("B3 diff-derived (secondary)", "NP-92")] == "--"
    assert [r for r, f in t2 if f == "NP-90"][7:] == [
        "Its D19 label", "Its second label (the labeler's outcome)", "The reference checks' outcome on it"]
    t5 = cells(built, "natural_run_sanity")
    assert [r for r, f in t5 if f == "NP-90"] == list(ROW.values())  # one row per condition, in the paper's order
    assert [t5[("C1 initial-only, plain", f)] for f in built.fams] == [f"{NO}, {NO}", *[f"{YES}, {NO}"] * 2]
    assert [t5[("B1 repository tests", f)] for f in built.fams] == [f"{YES}, {YES}"] * 3
    assert t5[("B3 diff-derived (secondary)", "NP-92")] == "--"
    assert [macros_of(built.out)[f"sanity.c1.np90.{k}"] for k in ("reference", "noop")] == ["rejected", "rejected"]
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


# --------------------------------------------------------------------------- the gate, the sanity grading and the coverage


YES, NO = "\\checkmark", "$\\times$"  # the marks of the sanity rows: accepted, rejected (as the outcome matrices mark them)


def fk_of(family: str) -> str:
    return family.lower().replace("-", "")


def sanity_word(x: dict | None) -> str:
    """A condition's outcome on a family's reference solution or its no-op, from its sanity block alone."""
    if not x or not x["n"]:
        return "not graded"
    if x["n"] != 1:
        return f"{x['pass']}/{x['n']} accepted"
    other = [words(o) for o in x["outcomes"] if o not in ("pass", "task_failure")]
    return "accepted" if x["pass"] else "rejected" + (f" ({', '.join(other)})" if other else "")


def mark(word: str) -> str:
    """A sanity row's cell part for an outcome in words (the macro's form)."""
    return YES if word == "accepted" else NO + word.removeprefix("rejected") if word.startswith("rejected") else word


def test_the_sanity_rows_follow_the_analysis(made):
    """The sanity table gives each condition's outcome on the family's reference solution and on its no-op, the unchanged
    base (sanity_per_family, which the rates leave out), each with its macro; -- where the run did not grade the
    condition for the family. The gate's marker on a condition's cell of Table 7 holds exactly where the condition does
    not pass the family's reference in every pair, so the two tables never disagree."""
    a, t2, t5, macros = (made.a, cells(made, "natural_run_source_evidence"), cells(made, "natural_run_sanity"),
                         macros_of(made.out))
    for c, row in ROW.items():
        if c not in a["sanity_per_family"]:
            assert not [r for r, _ in t5 if r == row] and not [r for r, _ in t2 if r == row], c
            continue
        for f in made.fams:
            keys = [f"sanity.{row.split()[0].lower()}.{fk_of(f)}.{k}" for k in ("reference", "noop")]
            s = a["sanity_per_family"][c].get(f)
            if s is None:
                assert t5[(row, f)] == "--" == t2[(row, f)] and not set(keys) & set(macros), (c, f)
                continue
            want = [sanity_word(s.get(k)) for k in ("reference", "noop")]
            assert t5[(row, f)] == ", ".join(mark(w) for w in want), (c, f)  # the cell in marks, the macros in words
            assert [macros.get(k, "not graded") for k in keys] == want, (c, f)
            passes = bool(s.get("reference")) and s["reference"]["pass"] == s["reference"]["n"]
            assert t2[(row, f)].endswith("$^{\\dagger}$") == (not passes), (c, f)
    caption = parse_table((made.out / "natural_run_sanity.tex").read_text())[0]
    assert ("each condition's outcome on the family's reference solution and on its no-op, the unchanged base, in the run, "
            "as reference, no-op: \\checkmark{} accepted, $\\times$ rejected") in caption
    assert "Tables~\\ref{tab:nr-source} and~\\ref{tab:nr-fa-fr} mark with $^{\\dagger}$ the cells it drops" in caption
    assert ("$^{\\dagger}$: the verifier does not pass the family's reference solution in the run, so the secondary "
            "oracle-gated view drops the cell, as in Table~\\ref{tab:nr-fa-fr}") in parse_table(
        (made.out / "natural_run_source_evidence.tex").read_text())[0]


def test_the_sanity_rows_name_what_the_run_records(undiscriminating):
    """An unresolved reference (repeats that disagree) and an infrastructure outcome on the no-op are rejections named in
    brackets; a condition that fails its reference carries the gate's marker on its cell of Table 7, an unresolved
    reference included, and its macro does not."""
    t2, t5, macros = (cells(undiscriminating, "natural_run_source_evidence"), cells(undiscriminating, "natural_run_sanity"),
                      macros_of(undiscriminating.out))
    assert t5[("C3 correction-aware, plain", "NP-91")] == f"{NO} (unresolved), {NO}"
    assert t5[("B2 session-LLM baseline", "NP-90")] == f"{YES}, {NO} (environment failure)"
    assert (macros["sanity.c3.np91.reference"], macros["sanity.b2.np90.noop"]) == ("rejected (unresolved)",
                                                                                 "rejected (environment failure)")
    assert [t5[("B1 repository tests", f)] for f in undiscriminating.fams] == [
        f"{YES}, {YES}", f"{YES}, {YES}", f"{YES}, {NO}"]
    marked = {(r, f) for (r, f), cell in t2.items() if cell.endswith("$^{\\dagger}$")}
    assert marked == {("C1 initial-only, plain", "NP-90"), ("C2 initial-only, audited", "NP-90"),
                      ("C3 correction-aware, plain", "NP-90"), ("C3 correction-aware, plain", "NP-91"),
                      ("C1 initial-only, plain", "NP-92"), ("C4 correction-aware, audited", "NP-92")}
    assert (t2[("C3 correction-aware, plain", "NP-91")], macros["se.c3.np91"], macros["og.c3.np91"]) == (
        "rejected$^{\\dagger}$", "rejected", "dropped")


def _req_sorted(ids) -> list[str]:
    return sorted(ids, key=lambda r: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", r)])


def test_the_coverage_rows_follow_the_analysis(made):
    """The coverage table, derived here from the analysis's coverage block and each family's correction requirements alone:
    the reference contract's correction requirements, and under each mapper the reference contract's scored active
    requirements that each recovered contract covers, of all, and the correction requirements it does not cover (those it
    does not cover, by the requirements it does), in the order of their numbers; each with its macro, and -- where the
    mapper did not map the contract."""
    a, t4, macros = made.a, cells(made, "natural_run_coverage"), macros_of(made.out)
    for f in made.fams:
        cov, corr = a["coverage"][f], a["natural"]["families"][f]["correction_requirements"]
        assert t4[("Correction requirements of the reference contract", f)] == macros[f"ref.{fk_of(f)}.correction.ids"] == (
            ", ".join(_req_sorted(corr)) or "none"), f
        for which, variants, m in (("first", "variants", "m1"), ("second", "variants_mapper2", "m2")):
            shares, uncovered = [], []
            for v, k in (("initial_only", "ini"), ("full_session", "full")):
                d = cov.get(variants, {}).get(v)
                if d is None:
                    shares.append("--")
                    uncovered.append("--")
                    assert not {f"{k}.{fk_of(f)}.cov.{m}", f"{k}.{fk_of(f)}.corr.missing.{m}"} & set(macros), (f, m, v)
                    continue
                shares.append(f"{len(d['covered'])}/{len(cov['reference_scored'])}")
                uncovered.append(", ".join(_req_sorted(set(corr) - set(d["covered"]))) or "none")
                assert (macros[f"{k}.{fk_of(f)}.cov.{m}"], macros[f"{k}.{fk_of(f)}.corr.missing.{m}"]) == (
                    shares[-1], uncovered[-1]), (f, m, v)
            assert t4[(f"Coverage, {which} mapper: initial-only, correction-aware", f)] == ", ".join(shares), (f, m)
            assert t4[(f"Correction requirements not covered, {which} mapper: initial-only; correction-aware", f)] == (
                "; ".join(uncovered)), (f, m)
        # The columns the controlled coverage table also gives: the recovered requirements that the mapper judges to
        # contradict the reference contract, of the contract's scored active ones, and those the contract marks superseded.
        for which, variants, m in (("first", "variants", "m1"), ("second", "variants_mapper2", "m2")):
            contra = []
            for v, k in (("initial_only", "ini"), ("full_session", "full")):
                d = cov.get(variants, {}).get(v)
                contra.append("--" if d is None else f"{len(d['contradicting'])}/{d['n_recovered_scored']}")
                assert macros.get(f"{k}.{fk_of(f)}.contra.{m}", "--") == contra[-1], (f, m, v)
            assert t4[(f"Contradicting the reference contract, {which} mapper: initial-only, correction-aware", f)] == (
                ", ".join(contra)), (f, m)
        sup = []
        for v, k in (("initial_only", "ini"), ("full_session", "full")):
            d = cov.get("variants", {}).get(v) or cov.get("variants_mapper2", {}).get(v)
            sup.append("--" if d is None else str(len(d["superseded_requirements"])))
            assert macros.get(f"{k}.{fk_of(f)}.superseded", "--") == sup[-1], (f, v)
        assert t4[("Marked superseded by the recovered contract: initial-only, correction-aware", f)] == ", ".join(sup), f


def test_the_coverage_rows_of_a_run_with_its_mappings(built, plain):
    """The mappings of :data:`MAPPINGS`: a correction requirement mapped but contradicted is not covered (NP-90, second
    mapper), an initial-only contract can cover one (NP-92, second mapper), a contract the mapper did not map is -- (NP-91),
    and a run without recovered contracts has no coverage. The ids sort by their numbers, as the run's R4 and R11 do."""
    t4 = cells(built, "natural_run_coverage")

    def row(label: str) -> list[str]:
        return [t4[(label, f)] for f in built.fams]

    assert row("Correction requirements of the reference contract") == ["R-corr, R-reply"] * 3
    assert row("Coverage, first mapper: initial-only, correction-aware") == ["1/3, 2/3", "1/3, 3/3", "1/3, 2/3"]
    assert row("Coverage, second mapper: initial-only, correction-aware") == ["1/3, 1/3", "--, 3/3", "2/3, 2/3"]
    assert row("Correction requirements not covered, first mapper: initial-only; correction-aware") == [
        "R-corr, R-reply; R-reply", "R-corr, R-reply; none", "R-corr, R-reply; R-reply"]
    assert row("Correction requirements not covered, second mapper: initial-only; correction-aware") == [
        "R-corr, R-reply; R-corr, R-reply", "--; none", "R-reply; R-reply"]
    # NP-90's second mapper judges its correction-aware R1 to contradict R-corr; every recovered contract of the world marks
    # R-old superseded (tests/test_analysis_natural.py, _construct), the same under both mappers.
    assert row("Contradicting the reference contract, first mapper: initial-only, correction-aware") == [
        "0/2, 0/3", "0/3, 0/4", "0/4, 0/5"]
    assert row("Contradicting the reference contract, second mapper: initial-only, correction-aware") == [
        "0/2, 1/3", "--, 0/4", "0/4, 0/5"]
    assert row("Marked superseded by the recovered contract: initial-only, correction-aware") == ["1, 1"] * 3
    assert [r for r, f in t4 if f == "NP-90"] == [
        "Correction requirements of the reference contract", "Coverage, first mapper: initial-only, correction-aware",
        "Coverage, second mapper: initial-only, correction-aware",
        "Correction requirements not covered, first mapper: initial-only; correction-aware",
        "Correction requirements not covered, second mapper: initial-only; correction-aware",
        "Contradicting the reference contract, first mapper: initial-only, correction-aware",
        "Contradicting the reference contract, second mapper: initial-only, correction-aware",
        "Marked superseded by the recovered contract: initial-only, correction-aware"]
    macros = macros_of(built.out)
    assert (macros["full.np90.cov.m2"], macros["full.np90.corr.missing.m2"], macros["ini.np92.corr.missing.m2"]) == (
        "1/3", "R-corr, R-reply", "R-reply")
    assert (macros["full.np90.contra.m2"], macros["full.np90.contra.m1"], macros["ini.np91.superseded"]) == ("1/3", "0/3", "1")
    assert "ini.np91.contra.m2" not in macros  # the second mapper did not map NP-91's initial-only contract
    text = (built.out / "natural_run_coverage.tex").read_text()
    caption = parse_table(text)[0]
    assert "\\label{tab:nr-coverage}" in text
    assert ("under each of the two model mappers, whose mappings are proposals: the reference contract's scored active "
            "requirements that a requirement of the recovered contract maps to without contradicting it, of all") in caption
    assert ("Contradicting: the recovered contract's scored active requirements that the mapper judges to contradict a "
            "requirement of the reference contract, of all its scored active requirements") in caption
    assert ("Marked superseded: the recovered contract's requirements whose status is superseded and which it does not "
            "mark unscored; they are not scored") in caption
    assert "--: not in the analysis (in the rows of a mapper: that mapper did not map that contract); none: no such" in caption
    t4 = cells(plain, "natural_run_coverage")
    for f in plain.fams:
        assert t4[("Coverage, first mapper: initial-only, correction-aware", f)] == "--, --"
        assert t4[("Correction requirements not covered, second mapper: initial-only; correction-aware", f)] == "--; --"
        assert t4[("Contradicting the reference contract, second mapper: initial-only, correction-aware", f)] == "--, --"
        assert t4[("Marked superseded by the recovered contract: initial-only, correction-aware", f)] == "--, --"
    # The construction facts fill their page (Table 44 at the run's records), so the coverage is a table of its own.
    assert not [r for r, _ in cells(built, "natural_run_construction") if "overage" in r or "not covered" in r]
    assert sorted(["R11", "R4", "R13", "R-corr", "R5"], key=mt._req_order) == ["R4", "R5", "R11", "R13", "R-corr"]


def test_the_conditions_that_tell_no_candidate_apart_follow_the_analysis(made):
    """nd.<family>.reject, nd.<family>.accept and noop.<family>.accepted, derived here from the per-task outcomes of the
    held-out candidates and the sanity grading alone, not from the outcome counts the generator reads: the conditions that
    graded the reference, the no-op and the held-out candidates and passed none of them (or every one), and those that pass
    the no-op, in the order of the conditions, as a sentence lists them."""
    a, macros, led = made.a, macros_of(made.out), numbers_entries(made.ledger)
    for f in made.fams:
        reject, accept, noop = [], [], []
        for c, row in ROW.items():
            s, held = a["sanity_per_family"].get(c, {}).get(f), a["per_task"][f].get(c, [])
            if not s and not held:
                continue
            outcomes = [r["outcome"] for r in held] + [o for k in ("reference", "noop") for o, n in
                                                       (s or {}).get(k, {}).get("outcomes", {}).items() for _ in range(n)]
            graded = bool(held) and all((s or {}).get(k, {}).get("n") for k in ("reference", "noop"))
            if graded and "pass" not in outcomes:
                reject.append(row.split()[0])
            if graded and set(outcomes) == {"pass"}:
                accept.append(row.split()[0])
            if (s or {}).get("noop") and s["noop"]["pass"] == s["noop"]["n"]:
                noop.append(row.split()[0])
        for key, names in (("nd.{}.reject", reject), ("nd.{}.accept", accept), ("noop.{}.accepted", noop)):
            want = "none" if not names else names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            assert macros[key.format(fk_of(f))] == want, (key, f)
            fs = check_fields(made, led[key.format(fk_of(f))], f)  # every field is the family's own
            assert {p.split(".")[0] for p, _ in fs} <= {"outcome_counts_per_family", "sanity_per_family"}, key


def test_the_conditions_that_tell_no_candidate_apart(undiscriminating, built):
    """In the world of :func:`_undiscriminating`, the conditions that reject every candidate of a family, its reference
    and its valid alternatives included (an unresolved pair is a rejection), and those that accept every one, the no-op
    included; in the built world, B1 accepts every candidate of every family and nothing rejects them all."""
    macros = macros_of(undiscriminating.out)
    assert [macros[f"nd.{fk}.reject"] for fk in ("np90", "np91", "np92")] == ["C1, C2 and C3", "C3", "C1 and C4"]
    assert [macros[f"nd.{fk}.accept"] for fk in ("np90", "np91", "np92")] == ["B1", "B1 and B3", "none"]
    assert [macros[f"noop.{fk}.accepted"] for fk in ("np90", "np91", "np92")] == ["B1", "B1 and B3", "none"]
    macros = macros_of(built.out)
    assert [(macros[f"nd.{fk}.reject"], macros[f"nd.{fk}.accept"], macros[f"noop.{fk}.accepted"])
            for fk in ("np90", "np91", "np92")] == [("none", "B1", "B1")] * 3
    assert (mt._listed([]), mt._listed(["C1"]), mt._listed(["C1", "C3"]), mt._listed(["C1", "C3", "C4"])) == (
        "none", "C1", "C1 and C3", "C1, C3 and C4")


def test_every_caption_points_to_the_natural_section_s_caveats(made):
    """The case studies' caveats are stated once, at the head of the natural section (paper/sections/natural.tex): every
    caption of this mode ends with its marker, the one the section's own table of caveats carries (moved unchanged to
    the template's part in Appendix G, paper/sections/app_natural_cases.tex; decision log D80), and names that section's
    label."""
    sections = ROOT / "paper" / "sections"
    template = (sections / "natural.tex").read_text()
    moved = (sections / "app_natural_cases.tex").read_text()
    assert mt.NR_MARKER == "$^{\\ddagger}$Natural case study; caveats in Section~\\ref{sec:natural-cases}."
    assert mt.NR_MARKER in " ".join(moved.split()) and "\\label{sec:natural-cases}" in template
    assert "\\paragraph{Caveats.}" in template  # the caveats themselves stay at the head of the natural section
    for name in TABLES:
        caption, _, _ = parse_table((made.out / f"{name}.tex").read_text())
        assert caption.endswith(" " + mt.NR_MARKER) and caption.count("ddagger") == 1, name


def test_the_tables_of_a_run_without_construction_records(plain):
    caption, _, _ = parse_table((plain.out / "natural_run_fa_fr.tex").read_text())
    assert caption.endswith("Not graded in this run: C2, B2. " + mt.NR_MARKER)
    t1 = cells(plain, "natural_run_fa_fr")
    assert {r for r, _ in t1} == {"C1 initial-only, plain", "C3 correction-aware, plain", "C4 correction-aware, audited", "B1 repository tests",
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
    assert _rows_of(out, "natural_run_source_evidence", "C3 correction-aware, plain", fams) == [
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


# --------------------------------------------------------------------------- the run's facts and D19's labels (run.*, d19.*)


def macros_of(out: Path) -> dict[str, str]:
    """The number macros of the mode's numbers.tex in ``out``, by key."""
    return dict(re.findall(r"^\\expandafter\\gdef\\csname nrv:([^\\]+)\\endcsname\{(.*)\}$", (out / "numbers.tex").read_text(),
                           re.MULTILINE))


def numbers_entries(ledger: str) -> dict[str, dict]:
    """The ledger's entries of the numbers section, by macro key."""
    return {macro_key(e): e for e in entries(ledger) if e["table"] == "numbers"}


def utc(t: str) -> datetime:
    return datetime.fromisoformat(t).astimezone(UTC)


def _with_records(built: Made, tmp_path: Path, name: str, manifest=None, analysis=None) -> Path:
    """A copy of the built world's run whose manifest.json ``manifest`` and analysis.json ``analysis`` have changed."""
    copy = tmp_path / name / built.run.name
    shutil.copytree(built.run, copy)
    for file, mutate in (("manifest.json", manifest), ("analysis.json", analysis)):
        if mutate is not None:
            doc = json.loads((copy / file).read_text())
            mutate(doc)
            (copy / file).write_text(json.dumps(doc))
    return copy


def test_the_run_s_facts_come_from_its_manifest_and_analysis(built):
    """run.*: the run's start date, start and end (UTC), the code revision of its invocations (first 7 characters), the
    harness versions of its results, its repeats, its pilot flag and its invocations, each from the manifest's or the
    analysis's field that its ledger entry names, with its value; and the run's families, in its order, from the analysis's
    natural.tasks (not the committed index's accepted families, which span both samples)."""
    macros, led, m, a = macros_of(built.out), numbers_entries(built.ledger), built.m, built.a
    assert macros["run.families"] == ", ".join(a["natural"]["tasks"]) == "NP-90, NP-91, NP-92"
    assert fields(led["run.families"]["src"]) == (f"{built.run.name}/analysis.json", [("natural.tasks", a["natural"]["tasks"])])
    start, end = utc(m["started_at"]), utc(m["finished_at"])
    assert macros["run.date"] == start.strftime("%Y-%m-%d") == "2026-11-21"
    assert (macros["run.started"], macros["run.finished"]) == (start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S"))
    assert macros["run.revision"] == m["code_revision"][:7] == m["invocations"][0]["code_revision"][:7]
    assert macros["run.harness"] == "0.3.5" and list(a["meta"]["harness_versions"]) == ["tc-harness/0.3.5"]
    assert (macros["run.repeats"], macros["run.pilot"], macros["run.invocations"]) == ("3", "set", "1")
    for key, cited in (("run.date", ["started_at"]), ("run.started", ["started_at"]), ("run.finished", ["finished_at"]),
                       ("run.revision", ["code_revision", "invocations"]), ("run.repeats", ["repeats"]), ("run.pilot", ["pilot"]),
                       ("run.invocations", ["invocations"])):
        file, fs = fields(led[key]["src"])
        assert (file, fs) == (f"{built.run.name}/manifest.json", [(p, m[p]) for p in cited]), key
    assert fields(led["run.harness"]["src"]) == (f"{built.run.name}/analysis.json",
                                                 [("meta.harness_versions", a["meta"]["harness_versions"])])


def test_the_run_s_facts_say_what_its_manifest_holds(outputs, built, tmp_path):
    """A start recorded in another time zone is given in UTC, and an end on a later day with its date; a revision with
    uncommitted changes says so, and each distinct revision of the invocations is named once, in their order; a pilot flag
    that is not set says so; each harness version is named once; and a field the manifest does not hold is not recorded."""
    first, last = "ab12cd3" + "f" * 33, "1234567" + "ef" * 16  # the run's own revisions; the last starts with a digit run

    def changed(m: dict) -> None:
        m.update(started_at="2026-11-23T06:14:36+02:00", finished_at="2026-11-24T01:02:03+00:00", pilot=False,
                 code_revision=last + "+dirty",
                 invocations=[{"at": "2026-11-23T04:14:36+00:00", "code_revision": first, "pilot": True, "tasks": built.fams},
                              {"at": "2026-11-23T04:15:05+00:00", "code_revision": last + "+dirty", "pilot": False,
                               "tasks": built.fams}])

    def versions(a: dict) -> None:
        a["meta"]["harness_versions"] = {"tc-harness/0.3.6": 2, "tc-harness/0.3.5": 10}

    mt.main(["--natural-run", str(_with_records(built, tmp_path, "changed", changed, versions))])
    macros = macros_of(outputs / "generated" / "natural_run")
    assert (macros["run.date"], macros["run.started"], macros["run.finished"]) == ("2026-11-23", "04:14:36", "2026-11-24 01:02:03")
    assert macros["run.revision"] == "ab12cd3, 1234567 (with uncommitted changes)"
    assert (macros["run.pilot"], macros["run.invocations"], macros["run.harness"]) == ("not set", "2", "0.3.5, 0.3.6")

    def dropped(m: dict) -> None:
        for k in ("started_at", "finished_at", "code_revision", "repeats", "pilot", "invocations"):
            del m[k]

    mt.main(["--natural-run", str(_with_records(built, tmp_path, "dropped", dropped))])
    macros = macros_of(outputs / "generated" / "natural_run")
    for key in ("run.date", "run.started", "run.finished", "run.revision", "run.repeats", "run.pilot", "run.invocations"):
        assert macros[key] == "not recorded", key
    assert "started_at=absent" in numbers_entries((outputs / "evidence_ledger_natural_run.md").read_text())["run.date"]["src"]


def test_the_digit_run_rule_skips_the_run_s_own_revisions_alone(outputs, built, tmp_path):
    """The run's code revisions name commits of the study's repository, so the privacy check's digit-run rule skips them,
    where each stands as a whole token; any other digit run of 7 or more, one that starts like a revision included, is
    still refused, and nothing is written."""
    assert mt._check_private("revision 1234567 and 1234567ab", "probe", digit_runs=True, exempt=("1234567", "1234567ab")) is None
    for text in ("revision 12345678", "revision 1234567 beside 7654321"):
        with pytest.raises(ValueError, match="refusing to write a digit run of 7 or more"):
            mt._check_private(text, "probe", digit_runs=True, exempt=("1234567",))
    rev = "1234567" + "ef" * 16 + "a"

    def own(m: dict) -> None:
        m.update(code_revision=rev, invocations=[{**m["invocations"][0], "code_revision": rev}])

    mt.main(["--natural-run", str(_with_records(built, tmp_path, "own", own))])
    assert macros_of(outputs / "generated" / "natural_run")["run.revision"] == "1234567"
    before = _tree(outputs)
    with pytest.raises(ValueError, match="refusing to write a digit run of 7 or more"):
        mt.main(["--natural-run", str(_with_records(built, tmp_path, "id", lambda m: (own(m), m.update(run_id="natural-pr-12345670"))))])
    _unchanged(outputs, before)


PASSES = "construction invalid but reference checks and regression norm pass"
PRE = "natural pre-review state passes the reference checks: the correction is not observable by the checks"


def _relabel(tasks) -> None:
    """D19's proposals with their reasons (as scripts/propose_labels.py writes them): two ambiguous candidates in NP-90, the
    pre-review state and a near miss whose repeats disagree in NP-91, none in NP-92."""
    relabel_d19(tasks[0], "eval-nm-1", "ambiguous", [], d19_note(PASSES))
    relabel_d19(tasks[0], "eval-alt-2", "ambiguous", ["REGRESSION"], d19_note("construction valid but checks fail"))
    relabel_d19(tasks[1], "pre-review", "ambiguous", [], d19_note(PRE))
    relabel_d19(tasks[1], "eval-nm-2", "ambiguous", [], d19_note(
        "the 3 repeats give different proposals (invalid ['R-reply']; ambiguous []; invalid ['R-reply']): a missing decision"))


@pytest.fixture(scope="module")
def relabelled(tmp_path_factory) -> Made:
    """Three families with their construction records whose D19 labels carry their reasons (:func:`_relabel`)."""
    return _make(tmp_path_factory.mktemp("relabelled"), True, _relabel)


def test_d19_s_labels_per_family_with_the_reason_of_each_ambiguous_candidate(relabelled):
    """d19.<family>.*: D19's labels of the family's held-out candidates, each value counted, and the candidates it labels
    ambiguous, named without the family's id, each with the category of D19's reason in brackets (some reasons hold a comma
    or a semicolon, so a bracket is what separates them); none where there is no such candidate. Each is put once, from the
    family's label block, which its ledger entry names."""
    made = relabelled
    macros, led, a = macros_of(made.out), numbers_entries(made.ledger), made.a
    for t in made.fams:
        fk, d19 = t.lower().replace("-", ""), a["labels"][t]["d19"]
        for v in ("valid", "invalid", "ambiguous", "unlabeled"):
            assert macros[f"d19.{fk}.{v}"] == str(d19[v])
            assert fields(led[f"d19.{fk}.{v}"]["src"]) == (f"{made.run.name}/analysis.json", [(f"labels.{t}.d19.{v}", d19[v])])
        for k in ("ids", "reasons"):
            assert fields(led[f"d19.{fk}.ambiguous.{k}"]["src"]) == (
                f"{made.run.name}/analysis.json", [(f"labels.{t}.d19.ambiguous_reasons", d19["ambiguous_reasons"])])
    assert [macros[f"d19.np90.{v}"] for v in ("valid", "invalid", "ambiguous", "unlabeled")] == ["1", "3", "2", "0"]
    assert macros["d19.np90.ambiguous.ids"] == "eval-alt-2, eval-nm-1"
    assert macros["d19.np90.ambiguous.reasons"] == f"eval-alt-2 (construction valid but checks fail), eval-nm-1 ({PASSES})"
    assert macros["d19.np91.ambiguous.ids"] == "eval-nm-2, pre-review"
    assert macros["d19.np91.ambiguous.reasons"] == f"eval-nm-2 ({D19_REPEATS_DISAGREE}), pre-review ({PRE})"
    assert (macros["d19.np92.ambiguous"], macros["d19.np92.ambiguous.ids"], macros["d19.np92.ambiguous.reasons"]) == (
        "0", "none", "none")
    assert "R-reply'" not in made.ledger + (made.out / "numbers.tex").read_text()  # a reason's list of proposals stays out


def test_an_ambiguous_candidate_without_a_reason_says_so(built):
    """The world as built gives its D19 labels no note: NP-91's pre-review state, which its reference checks pass, is
    ambiguous with no reason recorded."""
    macros = macros_of(built.out)
    assert (macros["d19.np91.ambiguous.ids"], macros["d19.np91.ambiguous.reasons"]) == ("pre-review", f"pre-review ({D19_NO_REASON})")


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
    # D19's labels with their reasons (analysis.D19_RULE): an analysis made before they were carried is refused, and they
    # must be the labels the analysis uses.
    "no D19 labels of a family": (lambda a: _pop(a["labels"]["NP-91"], "d19"), mt.Refused,
                                  "has no labels.NP-91.d19 (D19's labels of the family's held-out candidates"),
    "D19's counts that differ from the label block's": (
        lambda a: a["labels"]["NP-90"]["d19"].update(valid=9), ValueError,
        "labels.NP-90.d19 counts D19's proposals and labels.NP-90.counts the labels the analysis uses, and they differ"),
    "reasons of a candidate that is not ambiguous": (
        lambda a: a["labels"]["NP-91"]["d19"]["ambiguous_reasons"].update({"NP-91-eval-nm-1": "construction valid but checks fail"}),
        ValueError, "labels.NP-91.d19.ambiguous_reasons names ['NP-91-eval-nm-1', 'NP-91-pre-review']"),
    # The gate's marker and the sanity rows of Table 7 read the same grading of the reference; the conditions that tell no
    # candidate apart are read from outcome counts that must hold the sanity grading they count.
    "a gate that disagrees with the sanity grading": (
        lambda a: a["sanity_per_family"]["initial_plain"]["NP-90"].update(reference={"n": 1, "outcomes": {"pass": 1}, "pass": 1}),
        ValueError, ("oracle_gated.conditions.initial_plain.dropped and sanity_per_family.initial_plain.NP-90.reference "
                     "disagree on whether initial_plain passes NP-90's reference solution")),
    "outcome counts that leave out the sanity grading": (
        lambda a: a["outcome_counts_per_family"]["repo_tests"].update({"NP-90": {"pass": 1}}), ValueError,
        "outcome_counts_per_family.repo_tests.NP-90 counts fewer pass outcomes than the sanity grading of repo_tests in NP-90"),
    "outcome counts of an unknown condition": (
        lambda a: a["outcome_counts_per_family"].update(other_condition={}), ValueError,
        "expected conditions of C1-C4, B2, B1 and B3 only"),
    "the sanity grading of an unknown condition": (
        lambda a: a["sanity_per_family"].update(other_condition={}), ValueError,
        "expected conditions of C1-C4, B2, B1 and B3 only"),
    # A contract's superseded requirements are its own statuses, which both mappers' blocks read: they may not differ.
    "superseded requirements that differ by mapper": (
        lambda a: a["coverage"]["NP-92"]["variants_mapper2"]["full_session"].update(superseded_requirements=[]), ValueError,
        "coverage.NP-92: the mappers' superseded_requirements of the full_session contract differ"),
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
