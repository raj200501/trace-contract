"""paper/make_tables.py --pilot-numbers (``\\plv``) and --design (``\\dv``): the number namespaces the restructured text
needs for the construction pilot and for the design's constants and the protocol's history (restructure plan, part 5.2).

--pilot-numbers: each key against the frozen run's records, recomputed here, and the values the plan expected; no pilot
table is written or changed; a run without its exploratory re-analysis is refused. --design: every constant of
paper/design_constants.json is checked against its source before anything is written, and a constant whose quote,
pattern, count or recorded field disagrees with its value is refused; the protocol's versions are recomputed from git
objects and byte prefixes and must be the hashes the decision log records; the amendments table holds no number of its
own. main.tex defines both lookups as it defines \\fv.

The recorded runs, the protocol, the decision log and the scenario files are read, never written: the generator's
outputs (``GEN``, ``LEDGER``) point at a temporary directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "results" / "runs" / "pilot-v0.3.3"
spec = importlib.util.spec_from_file_location("make_tables_pilot_design", ROOT / "paper" / "make_tables.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)
cspec = importlib.util.spec_from_file_location("check_numbers_pd", ROOT / "paper" / "check_numbers.py")
cn = importlib.util.module_from_spec(cspec)
cspec.loader.exec_module(cn)

FAMS = ("CS-01", "CS-02", "CS-03", "CS-04")
SH = {"initial_plain": "c1", "initial_audited": "c2", "full_plain": "c3", "full_audited": "c4", "llm_freeform": "b2",
      "repo_tests": "b1"}


def macros(path: Path, prefix: str) -> dict[str, str]:
    return dict(re.findall(rf"^\\expandafter\\gdef\\csname {prefix}:([^\\]+)\\endcsname\{{(.*)\}}$", path.read_text(), re.MULTILINE))


def _tree(d: Path) -> dict[str, str]:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


def _generate(tmp: Path, args: list[str], design: Path | None = None) -> Path:
    paper = tmp / "paper"
    (paper / "generated").mkdir(parents=True)
    (paper / "generated" / "results_summary.tex").write_text("a pilot table that these modes must not touch\n")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mt, "GEN", paper / "generated")
        mp.setattr(mt, "LEDGER", paper / "evidence_ledger.md")
        if design is not None:
            mp.setattr(mt, "DESIGN", design)
        mt.main(args)
    return paper


# --------------------------------------------------------------------------- --pilot-numbers

@pytest.fixture(scope="module")
def pilot(tmp_path_factory) -> dict:
    paper = _generate(tmp_path_factory.mktemp("pilot"), ["--pilot-numbers", str(PILOT)])
    return {"paper": paper, "n": macros(paper / "generated" / "pilot" / "numbers.tex", "plv"),
            "ledger": (paper / "evidence_ledger_pilot.md").read_text(), "a": json.loads((PILOT / "analysis.json").read_text())}


def test_pilot_numbers_write_their_own_file_and_ledger_and_change_no_pilot_table(pilot):
    paper = pilot["paper"]
    assert _tree(paper / "generated") == {"results_summary.tex": hashlib.sha256(
        b"a pilot table that these modes must not touch\n").hexdigest(), "pilot/numbers.tex": _tree(paper / "generated")["pilot/numbers.tex"]}
    assert not (paper / "evidence_ledger.md").exists()
    keys = {m.group(1) for m in re.finditer(r"^- \[numbers\] \\plv\{([^}]*)\}", pilot["ledger"], re.MULTILINE)}
    assert keys == set(pilot["n"])


def test_pilot_numbers_are_the_records_values(pilot):
    n, a = pilot["n"], pilot["a"]
    cn_ = Counter()
    for d in a["labels"].values():
        cn_.update(d["counts"])
    assert (n["labels.invalid"], n["labels.valid"], n["labels.ambiguous"], n["heldout"]) == \
        (str(cn_["invalid"]), str(cn_["valid"]), str(cn_["ambiguous"]), str(sum(cn_.values())))
    for c, sh in SH.items():
        fa, fr = a["conditions"][c]["false_acceptance"], a["conditions"][c]["false_rejection"]
        assert (n[f"{sh}.fa"], n[f"{sh}.fr"]) == (f"{fa['num']}/{fa['den']}", f"{fr['num']}/{fr['den']}")
        x = a["near_miss_crosstab"][c]
        assert n[f"nm.conf.{sh}"] == f"{x['confirmed_invalid']['accepted']}/{x['confirmed_invalid']['n']}"
        v = a["sensitivity_construction_labels"][c]
        assert n[f"intent.{sh}.fa"] == f"{v['fa_num']}/{v['fa_den']}"
    # The near misses whose label records more than one violated requirement (the held-out pool's description).
    multi = [len(c["violated"]) for d in a["labels"].values() for c in d["candidates"]
             if c["origin"] == "constructed_near_miss" and len(c["violated"]) > 1]
    assert (n["nm.multi.n"], n["nm.multi.min"], n["nm.multi.max"]) == (str(len(multi)), str(min(multi)), str(max(multi)))
    # The values the plan expected (part 5.2).
    expected = {"labels.invalid": "17", "labels.valid": "10", "labels.ambiguous": "5", "c1.fa": "6/17", "c3.fa": "0/17",
                "b2.fa": "1/17", "b1.fa": "5/17", "c1.fr": "2/10", "b1.fr": "4/10", "b1.fr.added": "4", "b1.base.fa": "13/17",
                "nm.n": "20", "nm.confirmed": "15", "nm.ambiguous": "5", "nm.conf.c3": "0/15", "nm.amb.c3": "3/5",
                "nm.conf.c4": "0/15", "nm.amb.c4": "3/5", "intent.c3.fa": "3/22", "intent.c4.fa": "3/22", "intent.b2.fa": "5/22",
                "checks.c3.fa": "6/25", "signflip.c1-c3.fa.p1": "0.125", "signflip.c1-c3.fa.p2": "0.25",
                "signflip.c1-c3.fa.floor": "0.125", "tost.min": "0.0625", "audit.changed": "1/32", "c3.fa.exact.upper": "0.20",
                "kappa.min": "0.92", "kappa.max": "1.00", "queue": "8", "checks.results": "24{,}880", "rel.v0.2.both": "108",
                "rel.v0.2.same": "99", "rel.v0.2.changed.agree": "8/9", "plan.families": "60", "plan.delta": "0.20",
                "plan.power.k30": "0.45", "audit.identical": "4", "audit.verifiers": "8", "b1.checks.added.min": "6",
                "b1.checks.added.max": "12", "b1.fa.macro": "0.38", "c1.fa.macro": "0.37", "nodup.c1.fa": "4/14",
                "nm.multi.n": "5", "nm.multi.min": "2", "nm.multi.max": "6"}
    assert {k: n[k] for k in expected} == expected


def test_pilot_b1_false_rejections_by_the_origin_of_their_checks(pilot):
    n, a = pilot["n"], pilot["a"]
    rows = [json.loads(x) for x in (PILOT / "results.jsonl").read_text().splitlines() if x.strip()]
    labels = {(t, r["candidate"]): r["label"] for t in FAMS for r in a["per_task"][t]["repo_tests"]}
    added = base = 0
    for r in rows:
        if r["verifier_id"] == "repo_tests" and labels.get((r["task_id"], r["candidate_id"])) == "valid" and r["outcome"] != "pass":
            up = set(json.loads((ROOT / "tasks" / r["task_id"] / "verifiers" / "repo_tests" / "upstream_check_ids.json")
                                .read_text())["upstream_check_ids"])
            bad = [c["check_id"] for c in r["checks"] if c["status"] != "passed"]
            added += any(x not in up for x in bad)
            base += any(x in up for x in bad)
    assert (n["b1.fr.added"], n["b1.fr.base"]) == (str(added), str(base))


def test_pilot_numbers_refuse_a_run_without_its_exploratory_reanalysis(tmp_path):
    run = tmp_path / "runs" / "pilot-copy"
    run.mkdir(parents=True)
    for f in ("analysis.json", "manifest.json", "results.jsonl"):
        shutil.copy2(PILOT / f, run / f)
    with pytest.raises(ValueError, match="exploratory"):
        _generate(tmp_path / "out", ["--pilot-numbers", str(run)])
    assert not list((tmp_path / "out" / "paper").glob("evidence_ledger_*.md"))
    assert not (tmp_path / "out" / "paper" / "generated" / "pilot").exists()


# --------------------------------------------------------------------------- --design

@pytest.fixture(scope="module")
def design(tmp_path_factory) -> dict:
    paper = _generate(tmp_path_factory.mktemp("design"), ["--design"])
    out = paper / "generated" / "design"
    return {"paper": paper, "out": out, "n": macros(out / "numbers.tex", "dv"),
            "ledger": (paper / "evidence_ledger_design.md").read_text()}


def test_design_writes_its_numbers_and_the_amendments_table_only(design):
    assert sorted(p.name for p in design["out"].iterdir()) == ["amendments_table.tex", "numbers.tex"]
    assert sorted(p.name for p in (design["paper"] / "generated").iterdir()) == ["design", "results_summary.tex"]
    keys = {m.group(1) for m in re.finditer(r"^- \[numbers\] \\dv\{([^}]*)\}", design["ledger"], re.MULTILINE)}
    assert keys == set(design["n"])
    constants = json.loads(mt.DESIGN.read_text())["constants"]
    assert {c["key"] for c in constants} <= keys
    for c in constants:  # the value as printed, its checks named in its ledger entry
        assert design["n"][c["key"]] == (mt._int(int(c["value"])) if re.fullmatch(r"\d{4,}", str(c["value"])) else str(c["value"]))


def test_design_values_are_the_plan_s(design):
    n = design["n"]
    expected = {"design.k": "5", "design.attempt.minutes": "35", "design.tests.min": "6", "design.tests.max": "14",
                "design.revise.tests.max": "16", "design.audit.revisions": "3", "design.audit.attacks": "4",
                "design.audit.alternatives": "1", "design.signflip.assignments": "16", "design.scenarios.span": "8",
                "harness.cpus": "2", "harness.memory": "4", "harness.pids": "512", "harness.as": "1.5", "harness.fsize": "64",
                "harness.nproc": "256", "screen.s9.repo": "300", "screen.s9.total": "5", "screen.s10.wheelhouse": "1.5",
                "screen.s10.minutes": "10", "natural.pool.alternatives": "2", "natural.pool.nearmisses": "3",
                "natural.d19.repeats": "3", "natural.templates": "15", "natural.templates.time": "17:42:36",
                "protocol.amendments": "11", "protocol.v0.12.hash": "cc53d24f", "protocol.v0.12.time": "23:34:57",
                "protocol.v0.12.date": "2026-11-22", "protocol.v0.12.entry": "D71", "fresh.labelers.first": "08:30:39",
                "fresh.labelers.last": "08:47:55", "fresh.attempts.after.v0.10.ended": "7",
                "fresh.attempts.after.v0.10.started": "3", "design.bootstrap.resamples": "2{,}000",
                # the appendices' counts that no run analysis holds (restructure plan, part 3)
                "audit.message.named": "5", "annotation.reviewers": "2", "fresh.reminders.cs04": "16",
                "fresh.attempts.family": "20", "screen.s9.judges": "2", "screen.s9.rejudged.qualify": "3",
                "screen.s10.resolver.minutes": "30", "pilot.specs.hashed": "28", "pilot.pool.nearmisses": "5"}
    assert {k: n[k] for k in expected} == expected
    assert not any(k.startswith("future.") for k in n)  # future work is stated without sizes (the owner's default)
    assert len([k for k in n if k.startswith("rw.")]) <= 3  # at most three numbers of related work


def test_every_protocol_version_s_hash_is_recomputed_and_logged(design):
    n, log = design["n"], (ROOT / "docs" / "decision_log.md").read_text()
    cur = (ROOT / "experiments" / "protocol.md").read_bytes()
    versions = json.loads(mt.DESIGN.read_text())["protocol"]["versions"]
    assert [v["version"] for v in versions] == [f"0.{i}" for i in range(1, 13)]
    for v in versions:
        if "commit" in v:
            body = subprocess.run(["git", "-C", str(ROOT), "show", f"{v['commit']}:experiments/protocol.md"], capture_output=True,
                                  check=True).stdout
        elif "before_section" in v:
            body = cur[:cur.index(f"\n## {v['before_section']}. ".encode())]
        else:
            body = cur
        sha = hashlib.sha256(body).hexdigest()
        entry = re.search(rf"^### {v['entry']}\. .*?(?=^### D\d+\. |\Z)", log, re.MULTILINE | re.DOTALL).group(0)
        assert sha in entry and v["hashed_at"] in entry, v["version"]
        assert n[f"protocol.v{v['version']}.hash"] == sha[:8]


@pytest.mark.parametrize("change, message", [
    ({"key": "design.k", "value": 6}, "does not state the value"),  # the quote does not hold the new value
    ({"key": "design.k", "checks": [{"source": "experiments/protocol.md", "quote": "k = 6 per family"}]}, "does not occur"),
    ({"key": "harness.pids", "value": 256}, "gives '512'"),  # a code pattern gives another value
    ({"key": "natural.templates", "value": 14}, "files match"),  # a count of files
    ({"key": "fresh.labelers.first", "value": "08:30:40"}, "gives '08:30:39'"),  # a field of recorded JSON files
])
def test_a_constant_that_disagrees_with_its_source_is_refused(tmp_path, change, message):
    doc = json.loads(mt.DESIGN.read_text())
    c = next(x for x in doc["constants"] if x["key"] == change["key"])
    c.update({k: v for k, v in change.items() if k != "key"})
    path = tmp_path / "design_constants.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match=re.escape(message)):
        _generate(tmp_path, ["--design"], design=path)
    assert not (tmp_path / "paper" / "generated" / "design").exists()
    assert not (tmp_path / "paper" / "evidence_ledger_design.md").exists()


def test_a_protocol_version_the_decision_log_does_not_record_is_refused(tmp_path, monkeypatch):
    doc = json.loads(mt.DESIGN.read_text())
    doc["protocol"]["versions"][6]["before_section"] = 17  # a prefix whose hash D48 does not hold
    path = tmp_path / "design_constants.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="is not in D48"):
        _generate(tmp_path, ["--design"], design=path)


def test_without_the_repository_s_history_the_mode_fails_closed(tmp_path, monkeypatch):
    def no_git(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 128, b"", b"fatal: not a git repository")

    monkeypatch.setattr(mt.subprocess, "run", no_git)
    with pytest.raises(ValueError, match="history is needed"):
        _generate(tmp_path, ["--design"])


def test_the_amendments_table_holds_no_number_of_its_own_and_every_macro_is_generated(design):
    tex = (design["out"] / "amendments_table.tex").read_text()
    assert "\\label{tab:amendments}" in tex and "\\begin{longtable}" in tex
    body = tex[tex.index("\\endlastfoot\n") + len("\\endlastfoot\n"):tex.index("\\end{longtable}")].strip().splitlines()
    assert [r.split("&")[0].split("\\newline")[0].split(" (")[0] for r in body] == [f"v0.{i}" for i in range(1, 13)]
    caption = tex[tex.index("\\caption{"):tex.index("\\label")]
    assert cn.findings(body and "\n".join(body), "amendments") == []  # every number of a row is a macro or an identifier
    assert [f.token for f in cn.findings(caption, "caption")] == ["8"]  # the caption's "first 8 hex digits"
    numbers = cn.load_numbers()
    numbers["dv"] = design["n"]
    assert [str(f) for f in cn.findings("\n".join(body), "amendments", numbers) if f.kind == "missing key"] == []


def test_the_design_ledger_quotes_no_agent_product_name(design):
    names = mt._agent_names(json.loads((ROOT / mt.NATURAL_INPUTS["M0"]).read_text()))
    mt._check_private(design["ledger"], "evidence_ledger_design.md", digit_runs=False, names=names)


def test_main_tex_defines_the_plv_and_dv_lookups_and_inputs_their_numbers():
    main = (ROOT / "paper" / "main.tex").read_text()
    for p, sub in (("plv", "pilot"), ("dv", "design")):
        assert (f"\\newcommand{{\\{p}}}[1]{{\\ifcsname {p}:#1\\endcsname\\csname {p}:#1\\endcsname\\else"
                f"\\unfilled{{missing number #1}}\\fi}}") in main
        assert f"\\IfFileExists{{generated/{sub}/numbers.tex}}{{\\input{{generated/{sub}/numbers.tex}}}}{{}}" in main
        lookup = (ROOT / "paper" / "generated" / sub / "numbers.tex").read_text().splitlines()[2]
        assert lookup.removeprefix("% ") in main
