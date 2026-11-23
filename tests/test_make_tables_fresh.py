"""paper/make_tables.py --fresh: the keys and tables the manuscript's restructure adds (restructure plan, parts 5.1 and 6).

Each new \\fv key is checked against the records it is read from, recomputed here by code of the test's own: the run's
analysis.json and results.jsonl, the attempt records, the verifier specs, the contract mappings, the controlled
scenarios and the proposed labels; the values the plan expected (part 5.1) are asserted too. Also checked: the
behaviours table (Tab. 4), the primary per-family table split into false acceptance and false rejection with the rule's
rows only and the second labeler's view apart, the compact comparisons table, the one caveat marker of every caption,
and that no caption names a model, an agent tool or a model tier.

The recorded run results/runs/fresh-v1 is read, never written: the generator's outputs (``GEN``, ``LEDGER``) point at a
temporary directory. These tests check code behaviour on recorded data; all labels are model proposals.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results" / "runs" / "fresh-v1"
spec = importlib.util.spec_from_file_location("make_tables_fresh", ROOT / "paper" / "make_tables.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

FAMS = ("CS-01", "CS-02", "CS-03", "CS-04")
CONDS = ("initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform", "repo_tests")
SH = dict(zip(CONDS, ("c1", "c2", "c3", "c4", "b2", "b1")))
TIER = (r"\btiers?\b", r"\bdefault (?:agent )?model\b", r"\bsmallest (?:model|tier|agent)\b")  # model-tier wording
ENTRY = re.compile(r"^- \[(?P<table>[^\]]+)\] (?P<what>.+?) = (?P<value>.*) <- `(?P<src>[^`]*)`$")


def _fk(t: str) -> str:
    return t.lower().replace("-", "")


def macros(path: Path, prefix: str) -> dict[str, str]:
    return dict(re.findall(rf"^\\expandafter\\gdef\\csname {prefix}:([^\\]+)\\endcsname\{{(.*)\}}$", path.read_text(), re.MULTILINE))


@pytest.fixture(scope="module")
def made(tmp_path_factory) -> dict:
    paper = tmp_path_factory.mktemp("fresh") / "paper"
    (paper / "generated").mkdir(parents=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mt, "GEN", paper / "generated")
        mp.setattr(mt, "LEDGER", paper / "evidence_ledger.md")
        mt.main(["--fresh", str(RUN)])
    out = paper / "generated" / "fresh"
    a = json.loads((RUN / "analysis.json").read_text())
    rows = [json.loads(x) for x in (RUN / "results.jsonl").read_text().splitlines() if x.strip()]
    return {"out": out, "n": macros(out / "numbers.tex", "fv"), "ledger": (paper / "evidence_ledger_fresh.md").read_text(),
            "a": a, "rows": {(r["task_id"], r["verifier_id"], r["candidate_id"]): r for r in rows}}


def cells_of(row: str) -> list[str]:
    """A tabular row's cells, without the row's end (``\\\\``)."""
    return [x.strip() for x in re.sub(r"\\\\\s*$", "", row.strip()).split("&")]


def _units(a: dict) -> dict:
    """(task, candidate) -> (label, negative_type, {condition: outcome}), from per_task."""
    out: dict = {}
    for t in FAMS:
        for c in CONDS:
            for r in a["per_task"][t][c]:
                out.setdefault((t, r["candidate"]), (r["label"], r["negative_type"], {}))[2][c] = r["outcome"]
    return out


def test_the_design_counts_come_from_the_records(made):
    n, a = made["n"], made["a"]
    m = json.loads((RUN / "manifest.json").read_text())
    configs = {d["configuration"] for d in a["fresh_attempts"]["by_configuration_variant"].values()}
    assert (n["families"], n["families.w"]) == (str(len(a["per_task"])), "four") == ("4", "four")
    assert (n["run.configurations"], n["run.configurations.w"]) == (str(len(configs)), "two")
    assert (n["run.conditions"], n["run.conditions.w"]) == (str(len([c for c in m["conditions"] if c != "reference_check"])), "six")
    assert (n["run.repeats"], n["run.repeats.w"], n["attempts.excluded.w"]) == ("3", "three", "one")


def test_the_attempts_by_instruction_and_their_split(made):
    n, a = made["n"], made["a"]
    recs = [(t, x) for t in FAMS for x in json.loads((ROOT / "data" / "fresh" / "fresh-v1" / f"attempts_{t}.json").read_text())["attempts"]]
    units = _units(a)
    for var in ("u1", "final"):
        ids = [(t, x["id"]) for t, x in recs if x["variant"] == var and x["audit_passed"]]
        labels = Counter(units[k][0] for k in ids)
        assert n[f"{var}.attempts"] == str(len(ids))
        assert n[f"solve.{var}"] == f"{labels['valid']}/{len(ids)}" and n[f"{var}.invalid"] == f"{labels['invalid']}/{len(ids)}"
    assert (n["u1.invalid"], n["solve.final"]) == ("29/40", "39/39")  # the plan's expected values (part 5.1)
    assert int(n["u1.invalid.n"]) == int(n["cv.n"]) + int(n["unspec.n"])  # the text splits the first into the other two


def test_the_silent_loss_is_read_in_the_families_c1_s_reference_gate_keeps(made):
    n, a = made["n"], made["a"]
    units = _units(a)
    kept = [t for t in FAMS if t not in a["oracle_gated"]["conditions"]["initial_plain"]["dropped"]]
    viol = {t: [cid for (tt, cid), u in units.items() if tt == t and u[1] == "correction_violating"] for t in kept}
    silent = [t for t in kept if viol[t]]
    total = sum(len(viol[t]) for t in silent)
    assert n["cv.silent.families"] == ", ".join(silent) == "CS-03, CS-04"
    for c in CONDS:
        acc = sum(units[(t, cid)][2][c] == "pass" for t in silent for cid in viol[t])
        assert n[f"cv.silent.{SH[c]}"] == f"{acc}/{total}"
    assert [n[f"cv.silent.{k}"] for k in ("c1", "c2", "c3", "c4", "b2", "b1")] == ["14/17", "14/17"] + ["0/17"] * 4


def test_each_condition_on_each_family_s_reference(made):
    n, rows = made["n"], made["rows"]
    for t in FAMS:
        for c in CONDS:
            r = rows[(t, c, f"{t}-reference")]
            failed = sum(ch["status"] != "passed" for ch in r["checks"])
            assert n[f"ref.{SH[c]}.{_fk(t)}"] == ("passes" if r["outcome"] == "pass" else "fails")
            assert n[f"ref.{SH[c]}.{_fk(t)}.failed"] == str(failed)
    failing = {k for k, v in n.items() if re.fullmatch(r"ref\.[a-z0-9]+\.cs0\d", k) and v == "fails"}
    assert failing == {"ref.c1.cs01", "ref.c2.cs01"} and n["ref.c1.cs01.failed"] == n["ref.c2.cs01.failed"] == "12"


def _mapped(t: str, mapper: str, targets: set[str]) -> set[str]:
    spec_ = json.loads((ROOT / "tasks" / t / "verifiers" / "initial_plain" / "spec.json").read_text())
    mp = json.loads((ROOT / "tasks" / t / "contracts" / f"{mapper}.json").read_text())["map"]
    return {ch["check_id"] for ch in spec_["checks"] if {x for rid in ch["requirement_ids"] for x in mp.get(rid, [])} & targets}


def test_c1_s_checks_on_the_retracted_or_broken_requirement_under_both_mappers(made):
    n, rows = made["n"], made["rows"]
    on = {m: _mapped("CS-01", m, {"R-default-trim"}) for m in ("mapping_initial_only", "mapping2_initial_only")}
    failing = {ch["check_id"] for ch in rows[("CS-01", "initial_plain", "CS-01-reference")]["checks"] if ch["status"] != "passed"}
    assert n["c1.cs01.checks.superseded"] == str(len(on["mapping_initial_only"])) == "12"
    assert n["c1.cs01.checks.superseded.mapper2"] == str(len(on["mapping2_initial_only"])) == "12"
    assert on["mapping_initial_only"] == failing  # exactly those fail on the reference
    assert n["c1.cs01.checks.superseded.failed"] == "12" and n["c1.cs01.checks.other.failed"] == "0"
    for t, req in (("CS-03", "R-all-caps-input"), ("CS-04", "R-zero-step")):
        assert n[f"beh.{_fk(t)}.broken"] == req
        for mapper, key in (("mapping_initial_only", ""), ("mapping2_initial_only", ".mapper2")):
            assert n[f"c1.{_fk(t)}.checks.broken{key}"] == str(len(_mapped(t, mapper, {req}))) == "0"
    assert "c1.cs02.checks.broken" not in n  # no correction violator, no broken requirement


def test_the_violators_c1_rejects_and_the_requirements_of_their_failing_checks(made):
    n, a, rows = made["n"], made["a"], made["rows"]
    spec_ = json.loads((ROOT / "tasks" / "CS-03" / "verifiers" / "initial_plain" / "spec.json").read_text())
    req_of = {ch["check_id"]: ch["requirement_ids"] for ch in spec_["checks"]}
    rej = [r["candidate"] for r in a["per_task"]["CS-03"]["initial_plain"]
           if r["negative_type"] == "correction_violating" and r["outcome"] != "pass"]
    by_req = Counter(rid for cid in rej for rid in {x for ch in rows[("CS-03", "initial_plain", cid)]["checks"]
                                                   if ch["status"] != "passed" for x in req_of[ch["check_id"]]})
    assert n["c1.cs03.cv.rejected"] == str(len(rej)) == "3"
    assert {k.rsplit(".", 1)[1]: v for k, v in n.items() if k.startswith("c1.cs03.cv.rejected.")} == \
        {r.lower(): str(v) for r, v in by_req.items()} == {"r3": "2", "r4": "3"}


def test_the_violators_distinct_outcome_patterns_are_counted_within_each_family(made):
    """The correction violators' distinct patterns of pass and non-pass over the six conditions (the rows of the outcome
    matrix), per family and summed over the families with each pattern counted within its family: what the pooled
    counts of the violators rest on (the final verification's finding on their clustering)."""
    n, a = made["n"], made["a"]
    units = _units(a)
    pats = {t: {tuple(u[2][c] == "pass" for c in CONDS) for (tt, _), u in units.items()
                if tt == t and u[1] == "correction_violating"} for t in FAMS}
    for t in FAMS:
        if pats[t]:
            assert n[f"cv.patterns.{_fk(t)}"] == str(len(pats[t]))
        else:
            assert f"cv.patterns.{_fk(t)}" not in n  # a family without correction violators has no pattern
    assert n["cv.patterns"] == str(sum(len(p) for p in pats.values()))
    assert [n[k] for k in ("cv.patterns.cs01", "cv.patterns.cs03", "cv.patterns.cs04", "cv.patterns", "cv.patterns.w")] == \
        ["1", "2", "1", "4", "four"]


def test_what_each_correction_changed_comes_from_the_scenarios(made):
    n = made["n"]
    for t in FAMS:
        ir = json.loads((ROOT / "data" / "controlled" / "scenarios" / f"{t}.json").read_text())["intended_requirements"]
        assert n[f"corr.{_fk(t)}.superseded"] == str(sum(r["turn"] == "U1" and r["final_status"] == "superseded" for r in ir))
        assert n[f"corr.{_fk(t)}.added"] == str(sum(r["turn"] != "U1" for r in ir))
    assert [(n[f"corr.{_fk(t)}.superseded"], n[f"corr.{_fk(t)}.added"]) for t in FAMS] == [("1", "3"), ("0", "4"), ("0", "3"), ("0", "5")]


def test_what_the_invalid_units_broke_comes_from_the_proposed_labels(made):
    n, a = made["n"], made["a"]
    units = _units(a)
    for t in FAMS:
        labels = json.loads((ROOT / "tasks" / t / "strata" / "fresh-v1" / "proposed_labels.json").read_text())["candidates"]
        inv = [cid for (tt, cid), u in units.items() if tt == t and u[0] == "invalid"]
        cnt = Counter(req for cid in inv for req in labels[cid]["violated"])
        assert n[f"beh.{_fk(t)}.n"] == str(len(inv))
        assert {k.split(".", 2)[2]: v for k, v in n.items() if k.startswith(f"beh.{_fk(t)}.") and k.split(".", 2)[2] not in
                ("n", "broken")} == {r.lower(): str(c) for r, c in cnt.items()}
    assert (n["beh.cs01.n"], n["beh.cs01.r-custom-format-unchanged"], n["beh.cs02.regression"], n["beh.cs03.r-all-caps-input"],
            n["beh.cs04.r-zero-step"]) == ("10", "6", "2", "7", "10")


def test_the_checks_the_audit_added_and_the_false_rejections_through_them(made):
    n, a, rows = made["n"], made["a"], made["rows"]
    for t in FAMS:
        for plain, aud in (("initial_plain", "initial_audited"), ("full_plain", "full_audited")):
            ids = {c: {ch["check_id"] for ch in json.loads((ROOT / "tasks" / t / "verifiers" / c / "spec.json").read_text())["checks"]}
                   for c in (plain, aud)}
            added = ids[aud] - ids[plain]
            assert n[f"audit.{SH[aud]}.{_fk(t)}.added"] == str(len(added))
            fr = 0
            for r in a["per_task"][t][aud]:
                if r["label"] == "valid" and r["outcome"] != "pass":
                    bad = {ch["check_id"] for ch in rows[(t, aud, r["candidate"])]["checks"] if ch["status"] != "passed"}
                    fr += bool(bad) and bad <= added
            assert n[f"{SH[aud]}.{_fk(t)}.fr.added"] == str(fr)
    assert (n["audit.c4.cs03.added"], n["c4.cs03.fr.added"], n["audit.c4.cs03.revisions"]) == ("2", "6", "1")


def test_the_plain_and_the_audited_verifiers_check_counts_come_from_their_specs(made):
    """Section 2.2 gives the plain generators' range (C1, C3, B2) apart from the audited verifiers' (C2, C4), whose reviser
    may keep more tests than a generator is asked to write; the range over all five stays as well."""
    n = made["n"]
    count = {(t, c): len(json.loads((ROOT / "tasks" / t / "verifiers" / c / "spec.json").read_text())["checks"])
             for t in FAMS for c in CONDS if c != "repo_tests"}
    plain = [v for (t, c), v in count.items() if not c.endswith("_audited")]
    audited = [v for (t, c), v in count.items() if c.endswith("_audited")]
    assert (n["checks.plain.min"], n["checks.plain.max"]) == (str(min(plain)), str(max(plain))) == ("12", "14")
    assert (n["checks.audited.min"], n["checks.audited.max"]) == (str(min(audited)), str(max(audited))) == ("12", "15")
    assert (n["checks.generated.min"], n["checks.generated.max"]) == (str(min(plain + audited)), str(max(plain + audited)))
    assert n["audit.c4.cs03.revisions.w"] == "one"


def test_the_behaviours_table_has_a_row_per_family_and_every_cell_in_the_ledger(made):
    tex = (made["out"] / "fresh_behaviours.tex").read_text()
    assert "\\label{tab:fresh-behaviours}" in tex
    body = tex[tex.index("\\midrule") + len("\\midrule"):tex.index("\\bottomrule")]
    rows = [r for r in body.split("\\tabularnewline") if r.strip()]
    assert [r.split("&")[0].strip() for r in rows] == list(FAMS)
    entries = [m.groupdict() for line in made["ledger"].splitlines() if (m := ENTRY.match(line)) and m["table"] == "fresh_behaviours" and " | " in m["what"]]
    cells = {(e["what"].rsplit(" | ", 1)[1], e["what"].rsplit(" | ", 1)[0]): e["value"] for e in entries}
    for r in rows:
        fam, *texts = (x.replace(mt.NRTable.RAGGED, "").strip() for x in r.split("&"))
        assert texts == [mt.tex(cells[(fam, col)]) for col in [c for f, c in cells if f == fam]], fam
    n = made["n"]
    assert cells[("CS-04", "C1 accepts")] == n["cv.c1.cs04"] and cells[("CS-02", "C1 accepts")] == "--"
    assert cells[("CS-01", "C1 passes its reference")] == f"no ({n['ref.c1.cs01.failed']} of {n['checks.cs01.c1']} checks fail)"
    assert cells[("CS-01", "C1 checks on the retracted or broken requirement")] == "12 of 14 on the retracted R-default-trim"
    assert cells[("CS-03", "Base tests accept")] == n["b1.base.fa.cs03"]


def test_the_primary_per_family_table_is_split_and_holds_the_rule_s_rows_only(made):
    out, n = made["out"], made["n"]
    tex = (out / "fresh_per_family.tex").read_text()
    assert "\\label{tab:fresh-family}" in tex and "\\multicolumn{5}{c}{False acceptance" in tex and "{False rejection" in tex
    body = tex[tex.index("\\midrule\n") + len("\\midrule\n"):tex.index("\\bottomrule")].strip().splitlines()
    assert [r.split("&")[0].strip() for r in body] == [mt.COND_TEX[c] for c in CONDS]  # no row of the second labeler
    assert "labeler" not in "".join(body)
    for r, c in zip(body, CONDS):
        cells = cells_of(r)[1:]
        fa = [n[f"{SH[c]}.{_fk(t)}.fa"] for t in FAMS] + [n[f"{SH[c]}.fa"]]
        fr = [n[f"{SH[c]}.{_fk(t)}.fr"] for t in FAMS] + [n[f"{SH[c]}.fr"]]
        assert cells == fa + fr, c
    lab = (out / "fresh_per_family_labeler.tex").read_text()
    assert "\\label{tab:fresh-family-labeler}" in lab
    body = lab[lab.index("\\midrule\n") + len("\\midrule\n"):lab.index("\\bottomrule")].strip().splitlines()
    for r, c in zip(body, CONDS):
        cells = cells_of(r)[1:]
        assert cells == [n[f"il.{SH[c]}.{_fk(t)}.fa"] for t in FAMS] + [n[f"il.{SH[c]}.fa"]] + \
            [n[f"il.{SH[c]}.{_fk(t)}.fr"] for t in FAMS] + [n[f"il.{SH[c]}.fr"]], c


def test_the_compact_comparisons_table_and_the_full_one(made):
    out, n, a = made["out"], made["n"], made["a"]
    tex = (out / "fresh_comparisons.tex").read_text()
    assert "\\label{tab:fresh-comparisons}" in tex and "\\ref{tab:fresh-comparisons-full}" in tex
    rows = tex[tex.index("\\midrule\n") + len("\\midrule\n"):tex.index("\\bottomrule")].strip().splitlines()
    assert len(rows) == len(a["comparisons"]) == int(n["cmp.count"])
    for r, d in zip(rows, a["comparisons"]):
        k = f"cmp.{SH[d['a']]}-{SH[d['b']]}.{d['metric']}"
        assert cells_of(r) == [
            SH[d["a"]].upper(), SH[d["b"]].upper(), f"{d['metric'].upper()} ({n[k + '.n']})", n[k + ".diff"],
            f"{n[k + '.disc.ab']}/{n[k + '.disc.ba']}", n[k + ".p.greater"], n[k + ".p.two"], n[k + ".floor"]]
    full = (out / "fresh_comparisons_full.tex").read_text()
    assert "\\label{tab:fresh-comparisons-full}" in full and full.count("\\\\\n") >= len(a["comparisons"])
    # The compact caption has at most 60 words before the marker (restructure plan, finding 20), counted as for Fig. 2.
    cap = re.search(r"\\caption\{(.*)\}\\label\{tab:fresh-comparisons\}", tex, re.DOTALL).group(1)
    marker = mt.CONTROLLED_MARKER.format(n=4)
    assert cap.endswith(marker)
    words = re.sub(r"\\[A-Za-z]+(\{[^{}]*\})?|~", " ", cap[:-len(marker)]).split()
    assert len(words) <= 60, len(words)


def test_every_caption_carries_the_one_marker_and_names_no_model_agent_tool_or_tier(made):
    out = made["out"]
    marker = mt.CONTROLLED_MARKER.format(n=4)
    for p in sorted(out.glob("*.tex")):
        text = p.read_text()
        if p.name in ("numbers.tex", "fresh_attempt_costs.tex"):  # no caption with labels
            continue
        assert marker in text, p.name
        assert text.count("All labels are model proposals") == 0 and "Four controlled families" not in text, p.name
        mt._check_private(text, p.name, digit_runs=False)
        for pat in TIER:
            assert not re.search(pat, text, re.IGNORECASE), (p.name, pat)
    solve = (out / "fresh_solve_rates.tex").read_text()
    assert "different models of one model family of one provider" in solve
    names = "\n".join(p.read_text() for p in out.glob("*.tex"))
    assert "C3 correction-aware, plain" in names and "B2 session-LLM baseline" in names
    assert "full, plain" not in names and "full-session LLM" not in names
    # "graded patch" or "attempt", never "unit", for what is graded (restructure plan, finding 13); one symbol, one meaning:
    # the natural false-acceptance table's dagger marks the cells the oracle-gated view drops.
    captions = [m.group(1) for p in out.glob("*.tex") for m in re.finditer(r"\\caption\{(.*?)\}\\label", p.read_text(), re.DOTALL)]
    assert captions and not [c for c in captions if re.search(r"\bunits?\b", c)]
    assert "\\diamond" in marker and "dagger" not in marker


def test_every_new_key_is_a_ledger_entry_with_its_source(made):
    keys = {m.group(1) for m in re.finditer(r"^- \[numbers\] \\fv\{([^}]*)\}", made["ledger"], re.MULTILINE)}
    assert set(made["n"]) == keys
    new = ("families", "run.configurations", "run.conditions", "u1.invalid", "solve.final", "cv.silent.c1", "ref.c1.cs01",
           "ref.c1.cs01.failed", "c1.cs01.checks.superseded", "c1.cs03.checks.broken", "c1.cs04.checks.broken",
           "c1.cs03.cv.rejected", "corr.cs01.superseded", "corr.cs04.added", "beh.cs01.n", "audit.c4.cs03.added",
           "c4.cs03.fr.added", "checks.plain.min", "checks.plain.max", "checks.audited.min", "checks.audited.max",
           "audit.c4.cs03.revisions.w")
    assert set(new) <= keys
