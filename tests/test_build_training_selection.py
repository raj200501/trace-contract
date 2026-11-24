"""The training-data selection (scripts/build_training_selection.py): its acceptance rule, its cell gate, the split of the
invalid attempts it admits by kind, its refusals, its standing and its determinism.

Synthetic fixtures only: two hand-written task families with fresh attempts, a hand-written run manifest and results
(no grading, no Docker) and fixture attempt records. They check code behaviour and are not research evidence. The last
tests read the repository's own config and the committed selection of fresh-v1, which must regenerate from its records.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import inspect
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tracecontract import analysis as tc_analysis
from tracecontract.analysis import analyze
from tracecontract.schemas import (
    AttemptAudit,
    AttemptRecord,
    Author,
    Candidate,
    CandidateOrigin,
    ContractVariant,
    Event,
    EventKind,
    EvidenceSpan,
    Label,
    LabelerKind,
    Outcome,
    Population,
    Requirement,
    RequirementKind,
    RequirementStatus,
    Session,
    SnapshotSource,
    SourceRef,
    Split,
    TaskContract,
    TaskManifest,
    VerificationResult,
    sha256_text,
)
from tracecontract.store import append_jsonl, dump, write_json
from tracecontract.strata import StratumManifest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "downstream" / "rft_selection_v0.1.json"
COMMITTED = ROOT / "results" / "analyses" / "fresh-v1-training-selection"


def _module():
    spec = importlib.util.spec_from_file_location("build_training_selection", ROOT / "scripts" / "build_training_selection.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


bts = _module()

T0 = "2026-11-22T10:00:00+00:00"
HARNESS = "tc-harness/0.3.5"
RUN = "syn-v1"
CONDS = ("initial_plain", "full_plain")
FAMILY = {"T1": "F1", "T2": "F2"}
EXCLUDED = "T1-fresh-B-final-2"
FIRST, CORRECTION = "L000001.00", "L000005.00"  # the events of the first request and of the correction
# (task, attempt, variant, configuration, D19 label, violated requirements, C1 outcome, C3 outcome, audit passed).
# R-init comes with the first request and R-corr with the correction, so a violator of R-corr is a correction violator.
ATTEMPTS = (
    ("T1", "A-u1-1", "u1", "config-A", "invalid", ["R-corr", "REGRESSION"], "pass", "task_failure", True),
    ("T1", "A-u1-2", "u1", "config-A", "invalid", ["REGRESSION"], "task_failure", "pass", True),
    ("T1", "B-u1-1", "u1", "config-B", "invalid", ["R-init"], "task_failure", "pass", True),
    ("T1", "A-final-1", "final", "config-A", "valid", [], "task_failure", "pass", True),
    ("T1", "B-final-1", "final", "config-B", "valid", [], "pass", "pass", True),
    ("T1", "B-final-2", "final", "config-B", "valid", [], "pass", "pass", False),
    ("T2", "A-u1-1", "u1", "config-A", "invalid", ["R-corr"], "pass", "pass", True),
    ("T2", "B-u1-1", "u1", "config-B", "ambiguous", [], "pass", "task_failure", True),
    ("T2", "A-final-1", "final", "config-A", "valid", [], "pass", "pass", True),
    ("T2", "B-final-1", "final", "config-B", "invalid", [], "task_failure", "pass", True),
)


def _patch(body: str) -> str:
    return f"--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = '{body}'\n"


def _label(value: str, violated: list[str], human: bool = False) -> Label:
    return Label(value=value, violated_requirements=violated, labeler="reviewer-1" if human else bts.PILOT_LABELER,
                 labeler_kind=LabelerKind.human if human else LabelerKind.model, timestamp=T0)


def _cand(tid: str, cid: str, origin: CandidateOrigin, labels: list[Label], attempt: AttemptRecord | None = None,
          body: str | None = None) -> Candidate:
    patch = "" if origin == CandidateOrigin.noop else _patch(body or cid)
    return Candidate(candidate_id=cid, task_id=tid, origin=origin, split=Split.eval if origin == CandidateOrigin.fresh_attempt
                     else Split.dev, patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture", labels=labels,
                     attempt=None if attempt is None else attempt.model_copy(update={"patch_sha256": sha256_text(patch)}))


def _attempt(cid: str, configuration: str, variant: str, passed: bool) -> AttemptRecord:
    audit = AttemptAudit(profile="fresh-attempt:v1", passed=passed, audited_at=T0,
                         findings=[] if passed else ["read a file outside the workspace"])
    return AttemptRecord(attempt_id=cid, configuration=configuration, variant=variant, started_at=T0, ended_at=T0,
                         turns=3, tool_calls=5, ended="finished", patch_sha256="0" * 64, audit=audit)


def _req(rid: str, kind: RequirementKind, event: str) -> Requirement:
    return Requirement(req_id=rid, statement=f"Statement of {rid}.", kind=kind, status=RequirementStatus.explicit,
                       introduced_at=event, evidence=[EvidenceSpan(event_id=event, start=0, end=1, quote="x")],
                       proposer="fixture")


def _session(tid: str) -> Session:
    sid = f"{tid}-s"
    events = [Event(event_id=f"{sid}/{e}", session_id=sid, index=i, kind=EventKind.user_prompt, author=Author.human,
                    text=text, source=SourceRef(path="fixture", line=i + 1))
              for i, (e, text) in enumerate(((FIRST, "the first request"), (CORRECTION, "the correction")))]
    return Session(session_id=sid, population=Population.natural_pr_review, source="fixture",
                   source_format="aidev_pr_thread_v1", trace_sha256=sha256_text("fixture thread"), events=events)


def _world(root: Path, *, outcome: dict | None = None, label: dict | None = None, human: dict | None = None,
           drop: frozenset = frozenset(), twice: frozenset = frozenset(), repeats: int = 3, shuffle: int | None = None,
           noop: dict | None = None, population: dict | None = None, sessions: bool = False, audit: bool | None = None,
           body: dict | None = None) -> tuple[Path, Path]:
    """Tasks T1 and T2 (families F1, F2) under ``root/tasks`` and the recorded run ``root/results/runs/syn-v1``.

    ``outcome`` overrides a pair's outcome (``{(candidate, condition): outcome}``; the references are ``T1-reference``
    and ``T2-reference``), ``label`` an attempt's D19 label (``{candidate: (value, violated)}``, value None for no
    label) and ``human`` adds a human label (the same form); ``drop`` leaves pairs out of the results, ``twice``
    records them twice, and ``shuffle`` shuffles the results' order with that seed. ``noop`` adds a graded no-op
    (``{task: {condition: outcome}}``, candidate ``<task>-noop``); ``population`` sets a task's population, and
    ``sessions`` writes a natural task's ``session.json``; ``audit`` overrides every attempt's audit verdict, and
    ``body`` an attempt's patch (``{candidate: text}``; attempts with one text share a patch)."""
    tasks = root / "tasks"
    run = root / "results" / "runs" / RUN
    run.mkdir(parents=True)
    manifest = {"run_id": RUN, "code_revision": "fixture", "repeats": repeats, "started_at": T0, "finished_at": T0,
                "tasks": []}
    results = []
    for tid, fam in FAMILY.items():
        td = tasks / tid
        pop = (population or {}).get(tid, Population.controlled)
        dump(TaskContract(contract_id=f"{tid}-reference", task_id=tid, session_id=f"{tid}-s", variant=ContractVariant.reference,
                          created_by="fixture", created_at=T0, requirements=[
                              _req("R-init", RequirementKind.change, f"{tid}-s/{FIRST}"),
                              _req("R-corr", RequirementKind.invariant, f"{tid}-s/{CORRECTION}")]),
             td / "contracts" / "reference.json")
        if sessions and pop == Population.natural_pr_review:
            dump(_session(tid), td / bts.SESSION_FILE)
        own = [_cand(tid, f"{tid}-reference", CandidateOrigin.reference, [])]
        if tid in (noop or {}):
            own.append(_cand(tid, f"{tid}-noop", CandidateOrigin.noop, []))
        for c in own:
            dump(c, td / "candidates" / f"{c.candidate_id}.json")
        dump(TaskManifest(task_id=tid, family_id=fam, population=pop, status="pending_review", provenance="provenance.json",
                          snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture", commit="0" * 40),
                          env_requirements=[], contracts={"reference": "contracts/reference.json"},
                          candidates=[f"candidates/{c.candidate_id}.json" for c in own]), td / "task.json")
        entry = {"task_id": tid, "family_id": fam, "verifiers": {v: {"condition": v} for v in CONDS},
                 "candidates": {c.candidate_id: {"origin": c.origin.value, "patch_sha256": c.patch_sha256} for c in own}}
        graded = {f"{tid}-reference": dict.fromkeys(CONDS, "pass")}
        if tid in (noop or {}):
            graded[f"{tid}-noop"] = noop[tid]
        rels = []
        for t, name, variant, configuration, value, violated, c1, c3, audited in ATTEMPTS:
            if t != tid:
                continue
            cid = f"{tid}-fresh-{name}"
            value, violated = (label or {}).get(cid, (value, violated))
            labels = [] if value is None else [_label(value, violated)]
            if cid in (human or {}):
                labels.append(_label(*human[cid], human=True))
            c = _cand(tid, cid, CandidateOrigin.fresh_attempt, labels,
                      _attempt(cid, configuration, variant, audited if audit is None else audit), (body or {}).get(cid))
            rel = f"strata/fresh-v1/candidates/{cid}.json"
            dump(c, td / rel)
            rels.append(rel)
            entry["candidates"][cid] = {"origin": "fresh_attempt", "patch_sha256": c.patch_sha256, "stratum": "fresh-v1",
                                        "path": rel}
            graded[cid] = {"initial_plain": c1, "full_plain": c3}
        sm = td / "strata" / "fresh-v1.json"
        dump(StratumManifest(stratum="fresh-v1", task_id=tid, candidates=rels), sm)
        entry["strata"] = {"fresh-v1": {"manifest": "strata/fresh-v1.json",
                                        "manifest_sha256": hashlib.sha256(sm.read_bytes()).hexdigest()}}
        manifest["tasks"].append(entry)
        for cid, outs in graded.items():
            for v in CONDS:
                if (cid, v) in drop or v not in outs:
                    continue
                oc = (outcome or {}).get((cid, v), outs[v])
                r = VerificationResult(run_id=RUN, task_id=tid, verifier_id=v, candidate_id=cid, outcome=Outcome(oc),
                                       reward=1.0 if oc == "pass" else 0.0, started_at=T0, finished_at=T0, wall_s=0.1,
                                       harness_version=HARNESS)
                results += [r, r] if (cid, v) in twice else [r]
    if shuffle is not None:
        random.Random(shuffle).shuffle(results)
    for r in results:
        append_jsonl(r, run / "results.jsonl")
    write_json(manifest, run / "manifest.json")
    return run, tasks


def _config(root: Path, drop: tuple[str, ...] = (), **changes) -> Path:
    """The repository's config, pointed at the synthetic run, with ``changes`` applied and the keys ``drop`` removed."""
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg.update({"run": {"run_id": RUN, "dir": f"results/runs/{RUN}", "repeats": 3}, "conditions": list(CONDS)}, **changes)
    for key in drop:
        cfg.pop(key)
    p = root / "selection_config.json"
    p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return p


def _gate(noop_required: bool) -> dict:
    return {"reference": "pass", "noop": "task_failure", "noop_required": noop_required}


def _select(root: Path, run: Path, tasks: Path, *extra: str, config: Path | None = None, out: Path | None = None) -> int:
    return bts.main(["--config", str(config or _config(root)), "--run", str(run), "--tasks-root", str(tasks),
                     "--out", str(out or root / "out"), *extra])


def _manifest(out: Path) -> dict:
    return json.loads((out / bts.MANIFEST).read_text(encoding="utf-8"))


def _count(total: int, f1: int, f2: int) -> dict:
    return {"total": total, "per_family": {"F1": f1, "F2": f2}}


@pytest.fixture()
def selected(tmp_path) -> dict:
    run, tasks = _world(tmp_path)
    assert _select(tmp_path, run, tasks) == 0
    return _manifest(tmp_path / "out")


def _refused(capsys, code: int) -> str:
    assert code == 2
    err = capsys.readouterr().err
    assert "refused, nothing written" in err
    return err


def _edit_analysis(run: Path, edit) -> None:
    a = json.loads((run / "analysis.json").read_text(encoding="utf-8"))
    edit(a)
    (run / "analysis.json").write_text(json.dumps(a), encoding="utf-8")


def _entry(a: dict, task: str, condition: str, candidate: str) -> dict:
    return next(e for e in a["per_task"][task][condition] if e["candidate"] == candidate)


# ---------------------------------------------------------------- the acceptance rule


def test_a_condition_admits_exactly_the_kept_attempts_the_run_recorded_as_pass(selected):
    c1 = ["T1-fresh-A-u1-1", "T1-fresh-B-final-1", "T2-fresh-A-final-1", "T2-fresh-A-u1-1", "T2-fresh-B-u1-1"]
    c3 = ["T1-fresh-A-final-1", "T1-fresh-A-u1-2", "T1-fresh-B-final-1", "T1-fresh-B-u1-1", "T2-fresh-A-final-1",
          "T2-fresh-A-u1-1", "T2-fresh-B-final-1"]
    for c, want in zip(CONDS, (c1, c3)):  # every reference passes, so the gate keeps every cell
        d = selected["conditions"][c]
        assert d["ungated"]["admitted"] == d["gated"]["admitted"] == want
        assert d["cells_dropped"] == [] and d["lost_to_the_gate"]["admitted"] == []
        # the rule itself: a recorded pass, and nothing else, admits
        assert want == sorted(k for k, a in selected["attempts"].items() if a["outcomes"][c] == "pass")
    # The references and the attempt that its audit excludes pass under both conditions, and neither is admitted.
    assert EXCLUDED not in selected["attempts"]
    assert selected["excluded"] == [{"task_id": "T1", "candidate_id": EXCLUDED, "attempt_id": EXCLUDED,
                                     "reason": "the fresh-attempt audit found a read of forbidden material"}]
    assert selected["not_selected"] == {"reference": 2}
    assert selected["acceptance_rule"] == {"admit_on": "pass", "repeats": "every", "other_outcomes": "rejected"}
    assert selected["run"]["repeats"] == 3 and selected["tasks"] == ["T1", "T2"]


@pytest.mark.parametrize("change", [
    {"acceptance_rule": {"admit_on": "pass", "repeats": "any", "other_outcomes": "rejected"}},
    {"acceptance_rule": {"admit_on": "reward", "repeats": "every", "other_outcomes": "rejected"}},
    {"acceptance_rule": {"admit_on": "pass", "repeats": "every", "other_outcomes": "admitted"}},
    {"refused_outcomes": ["environment_failure", "timeout", "verifier_error"]},
])
def test_a_config_that_states_another_acceptance_rule_is_refused(tmp_path, capsys, change):
    run, tasks = _world(tmp_path)
    err = _refused(capsys, _select(tmp_path, run, tasks, config=_config(tmp_path, **change)))
    assert ("acceptance rule" in err) if "acceptance_rule" in change else ("refused outcomes" in err)
    assert not (tmp_path / "out").exists()


def test_every_repeat_the_config_names_must_be_the_runs_number_of_repeats(tmp_path, capsys):
    run, tasks = _world(tmp_path, repeats=1)
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert "graded each pair 1 time(s), and the config states 3" in err


# ---------------------------------------------------------------- the cell gate


def test_a_cell_whose_verifier_fails_its_reference_is_dropped_and_its_admissions_are_lost_yield(tmp_path):
    run, tasks = _world(tmp_path, outcome={("T1-reference", "initial_plain"): "task_failure"})
    assert _select(tmp_path, run, tasks) == 0
    m = _manifest(tmp_path / "out")
    c1, c3 = (m["conditions"][c] for c in CONDS)
    assert c1["cells"]["T1"] == {"reference": ["task_failure"], "noop": [], "passes_reference": False,
                                 "fails_on_noop": None, "kept": False,
                                 "dropped": "does not pass its reference (task_failure)"}
    assert c1["cells"]["T2"]["kept"] and c1["cells_dropped"] == ["T1"] and c3["cells_dropped"] == []
    assert c1["ungated"]["admitted"] == ["T1-fresh-A-u1-1", "T1-fresh-B-final-1", "T2-fresh-A-final-1", "T2-fresh-A-u1-1",
                                         "T2-fresh-B-u1-1"]
    assert c1["gated"]["admitted"] == ["T2-fresh-A-final-1", "T2-fresh-A-u1-1", "T2-fresh-B-u1-1"]
    assert c1["lost_to_the_gate"]["admitted"] == ["T1-fresh-A-u1-1", "T1-fresh-B-final-1"]
    lost = c1["lost_to_the_gate"]["counts"]
    assert (lost["admitted"], lost["correction_violator"], lost["valid"]) == (_count(2, 2, 0), _count(1, 1, 0),
                                                                              _count(1, 1, 0))
    assert c1["gated"]["counts"]["admitted"] == _count(3, 0, 3)
    assert c3["gated"]["admitted"] == c3["ungated"]["admitted"]
    md = (tmp_path / "out" / bts.TABLE).read_text(encoding="utf-8")
    assert "Dropped cells: C1 drops T1 (does not pass its reference (task_failure))." in md
    assert "| C1 `initial_plain` | data filter `naive_control` | gated: 1 of 2 | 3 (0, 3) |" in md
    assert "| C1 `initial_plain` | descriptive | ungated: 2 of 2 | 5 (2, 3) |" in md


@pytest.mark.parametrize(("kw", "why"), [
    ({"outcome": {("T1-reference", "full_plain"): "unresolved"}}, "does not pass its reference (unresolved)"),
    ({"outcome": {("T1-reference", "full_plain"): "timeout"}}, "does not pass its reference (timeout)"),
    ({"drop": frozenset({("T1-reference", "full_plain")})}, "the reference was not graded"),
])
def test_a_reference_without_a_pass_drops_the_cell_and_never_refuses_the_run(tmp_path, kw, why):
    run, tasks = _world(tmp_path, **kw)
    assert _select(tmp_path, run, tasks) == 0
    c3 = _manifest(tmp_path / "out")["conditions"]["full_plain"]
    cell = c3["cells"]["T1"]
    assert (cell["dropped"], cell["passes_reference"], cell["kept"]) == (why, False, False) and c3["cells_dropped"] == ["T1"]
    assert all(a.startswith("T2-") for a in c3["gated"]["admitted"]) and len(c3["ungated"]["admitted"]) == 7


def test_a_graded_noop_that_a_verifier_passes_drops_its_cell(tmp_path):
    run, tasks = _world(tmp_path, noop={"T2": {"initial_plain": "pass", "full_plain": "task_failure"}})
    assert _select(tmp_path, run, tasks) == 0
    m = _manifest(tmp_path / "out")
    c1, c3 = (m["conditions"][c] for c in CONDS)
    assert c1["cells"]["T2"] == {"reference": ["pass"], "noop": ["pass"], "passes_reference": True, "fails_on_noop": False,
                                 "kept": False, "dropped": "does not fail on its no-op (pass)"}
    assert c3["cells"]["T2"] == {"reference": ["pass"], "noop": ["task_failure"], "passes_reference": True,
                                 "fails_on_noop": True, "kept": True}
    assert c1["cells_dropped"] == ["T2"] and c3["cells_dropped"] == [] and c1["cells"]["T1"]["fails_on_noop"] is None
    assert c1["gated"]["admitted"] == ["T1-fresh-A-u1-1", "T1-fresh-B-final-1"]
    assert m["not_selected"] == {"noop": 1, "reference": 2}
    md = (tmp_path / "out" / bts.TABLE).read_text(encoding="utf-8")
    assert "The run graded the no-op in 2 of the 4 cells." in md and "C1 drops T2 (does not fail on its no-op (pass))" in md


def test_a_required_noop_must_be_graded_in_every_cell(tmp_path, capsys):
    cfg = {"cell_gate": _gate(True)}
    run, tasks = _world(tmp_path / "none")
    err = _refused(capsys, _select(tmp_path / "none", run, tasks, config=_config(tmp_path / "none", **cfg)))
    assert ("the config requires a graded no-op in every cell (cell_gate.noop_required), and 4 cell(s) have none: "
            "T1 under initial_plain, T2 under initial_plain, T1 under full_plain, T2 under full_plain") in err
    run, tasks = _world(tmp_path / "some", noop={"T1": dict.fromkeys(CONDS, "task_failure")})
    err = _refused(capsys, _select(tmp_path / "some", run, tasks, config=_config(tmp_path / "some", **cfg)))
    assert "2 cell(s) have none: T2 under initial_plain, T2 under full_plain" in err
    run, tasks = _world(tmp_path / "all", noop={t: dict.fromkeys(CONDS, "task_failure") for t in FAMILY})
    assert _select(tmp_path / "all", run, tasks, config=_config(tmp_path / "all", **cfg)) == 0
    assert _manifest(tmp_path / "all" / "out")["cell_gate"] == _gate(True)


def test_the_gate_must_agree_with_the_oracle_gated_view_of_the_runs_analysis(tmp_path, capsys):
    run, tasks = _world(tmp_path, outcome={("T1-reference", "initial_plain"): "task_failure"})
    analyze(run, tasks, allow_proposed=True, n_boot=20)
    assert _select(tmp_path, run, tasks) == 0
    assert _manifest(tmp_path / "out")["consistency"]["oracle_gated_compared"] is True
    _edit_analysis(run, lambda a: a["oracle_gated"]["conditions"]["full_plain"]["dropped"].update(T2="edited"))
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert "under full_plain, analysis.json's oracle-gated view drops ['T2'], and the reference gate drops []" in err
    _edit_analysis(run, lambda a: a["oracle_gated"]["conditions"].pop("full_plain"))
    assert "analysis.json's oracle-gated view has no full_plain" in _refused(capsys, _select(tmp_path, run, tasks))
    _edit_analysis(run, lambda a: a["oracle_gated"]["conditions"]["initial_plain"].pop("dropped"))
    assert "analysis.json's oracle-gated view has no initial_plain" in _refused(capsys, _select(tmp_path, run, tasks))


# ---------------------------------------------------------------- the split by kind


def test_the_invalid_attempts_a_condition_admits_are_split_by_kind_per_family_and_in_total(selected):
    kinds = {k: (a["label"], a["kind"], a["negative_type"]) for k, a in selected["attempts"].items()}
    assert kinds["T1-fresh-A-u1-1"] == ("invalid", "correction_violator", "correction_violating")  # with REGRESSION too
    assert kinds["T1-fresh-A-u1-2"] == ("invalid", "regression_only", "unspecified")
    assert kinds["T1-fresh-B-u1-1"] == ("invalid", "other_invalid", "initial_violating")
    assert kinds["T2-fresh-B-final-1"] == ("invalid", "other_invalid", "unspecified")  # no requirement, no regression
    assert kinds["T2-fresh-B-u1-1"] == ("ambiguous", None, "")
    c1, c3 = (selected["conditions"][c]["gated"]["counts"] for c in CONDS)
    assert (c1["admitted"], c1["invalid"], c1["correction_violator"], c1["regression_only"], c1["other_invalid"],
            c1["valid"], c1["ambiguous"]) == (_count(5, 2, 3), _count(2, 1, 1), _count(2, 1, 1), _count(0, 0, 0),
                                              _count(0, 0, 0), _count(2, 1, 1), _count(1, 0, 1))
    assert (c3["admitted"], c3["invalid"], c3["correction_violator"], c3["regression_only"], c3["other_invalid"],
            c3["valid"], c3["ambiguous"]) == (_count(7, 4, 3), _count(4, 2, 2), _count(1, 0, 1), _count(1, 1, 0),
                                              _count(2, 1, 1), _count(3, 2, 1), _count(0, 0, 0))
    pool = selected["pool"]["counts"]
    assert (pool["attempts"], pool["invalid"]) == (_count(9, 5, 4), _count(5, 3, 2))
    blocks = [selected["pool"]] + [d[w] for d in selected["conditions"].values() for w in ("gated", "ungated")]
    for block in blocks:  # every total is the sum of its families' counts
        tallies = [block["counts"], *block["by_variant"].values(),
                   *(t for v in block["by_variant_and_configuration"].values() for t in v.values())]
        assert all(v["total"] == sum(v["per_family"].values()) for t in tallies for v in t.values())


def test_counts_are_given_by_variant_and_by_variant_and_configuration(selected):
    c3 = selected["conditions"]["full_plain"]["gated"]
    assert c3["by_variant"]["u1"]["invalid"] == _count(3, 2, 1)
    both = c3["by_variant_and_configuration"]
    assert (both["u1"]["config-A"]["admitted"], both["u1"]["config-B"]["admitted"]) == (_count(2, 1, 1), _count(1, 1, 0))
    assert (both["u1"]["config-A"]["invalid"], both["u1"]["config-B"]["invalid"]) == (_count(2, 1, 1), _count(1, 1, 0))
    assert (both["final"]["config-A"]["admitted"], both["final"]["config-B"]["admitted"]) == (_count(2, 1, 1),
                                                                                             _count(2, 1, 1))
    assert both["final"]["config-B"]["invalid"] == _count(1, 0, 1)  # T2 B-final-1; T1 B-final-1 is valid
    pool = selected["pool"]["by_variant_and_configuration"]
    assert sum(pool[v][g]["attempts"]["total"] for v in pool for g in pool[v]) == 9
    assert pool["final"]["config-B"]["attempts"] == _count(2, 1, 1)  # T1's B-final-2 is excluded


def test_the_table_gives_each_familys_count_beside_the_total_and_no_rate(tmp_path, selected):
    md = (tmp_path / "out" / bts.TABLE).read_text(encoding="utf-8")
    tag = bts.STANDINGS["post hoc"][0]
    assert f"**{tag[0].upper() + tag[1:]}.**" in md and "trains, samples and downloads no model" in md
    rows = [line for line in md.splitlines() if line.startswith("| C3 `full_plain`")]
    assert rows[:2] == [("| C3 `full_plain` | data filter `correction_aware` | gated: 2 of 2 | 7 (4, 3) | 4 (2, 2) | 1 (0, 1) "
                         "| 1 (1, 0) | 2 (1, 1) | 3 (2, 1) | 0 (0, 0) |"),
                        ("| C3 `full_plain` | descriptive | ungated: 2 of 2 | 7 (4, 3) | 4 (2, 2) | 1 (0, 1) | 1 (1, 0) "
                         "| 2 (1, 1) | 3 (2, 1) | 0 (0, 0) |")]
    assert "| `u1`, `config-A`: attempts | `u1`, `config-A`: invalid |" in md
    assert "The run graded no no-op of these tasks" in md and "No cell is dropped." in md
    assert "%" not in md

    def floats(x):
        return isinstance(x, float) or (isinstance(x, dict) and any(floats(v) for v in x.values())) or (
            isinstance(x, list) and any(floats(v) for v in x))

    assert not floats(selected)  # counts only: no rate, pooled or not


# ---------------------------------------------------------------- labels


def test_a_human_label_takes_the_place_of_the_proposal_and_is_counted(tmp_path):
    run, tasks = _world(tmp_path, human={"T2-fresh-B-u1-1": ("invalid", ["R-corr"])})
    assert _select(tmp_path, run, tasks) == 0
    m = _manifest(tmp_path / "out")
    a = m["attempts"]["T2-fresh-B-u1-1"]
    assert (a["label"], a["kind"], a["human_label"]) == ("invalid", "correction_violator", True)
    assert m["label_source"]["attempts_with_a_human_label"] == 1
    assert sum(x["human_label"] for x in m["attempts"].values()) == 1
    assert m["conditions"]["initial_plain"]["gated"]["counts"]["correction_violator"] == _count(3, 1, 2)
    md = (tmp_path / "out" / bts.TABLE).read_text(encoding="utf-8")
    assert "Labels: human labels for 1 attempt(s), else rule D19's proposals" in md


# ---------------------------------------------------------------- refusals


def test_a_run_without_labels_is_refused(tmp_path, capsys):
    run, tasks = _world(tmp_path)
    err = _refused(capsys, _select(tmp_path, run, tasks,
                                   config=_config(tmp_path, label_source={"policy": "human", "labeler": None})))
    assert "no attempt has a label under the label source (policy human, human labels only): a run without labels" in err
    assert not (tmp_path / "out").exists()


def test_an_attempt_without_a_label_is_named_and_refused(tmp_path, capsys):
    run, tasks = _world(tmp_path, label={"T2-fresh-A-final-1": (None, [])})
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert "1 of the 9 attempts have no label under the label source (policy pilot): T2-fresh-A-final-1" in err


def test_an_unresolved_outcome_is_refused_and_leaves_the_last_output_in_place(tmp_path, capsys):
    run, tasks = _world(tmp_path / "good")
    out = tmp_path / "out"
    assert _select(tmp_path / "good", run, tasks, out=out) == 0
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    run, tasks = _world(tmp_path / "bad", outcome={("T1-fresh-A-final-1", "full_plain"): "unresolved"})
    capsys.readouterr()
    err = _refused(capsys, _select(tmp_path / "bad", run, tasks, out=out))
    assert "1 selected pair(s) unresolved (its repeats disagree), so no verdict to select on: T1-fresh-A-final-1 under full_plain" in err
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


@pytest.mark.parametrize(("kw", "what"), [
    ({"outcome": {("T2-fresh-A-u1-1", "initial_plain"): "timeout"}}, "an infrastructure outcome"),
    ({"outcome": {("T2-fresh-A-u1-1", "initial_plain"): "environment_failure"}}, "an infrastructure outcome"),
    ({"drop": frozenset({("T2-fresh-A-u1-1", "initial_plain")})}, "missing"),
    ({"twice": frozenset({("T2-fresh-A-u1-1", "initial_plain")})}, "recorded more than once"),
])
def test_a_selected_pair_without_one_verdict_is_refused(tmp_path, capsys, kw, what):
    run, tasks = _world(tmp_path, **kw)
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert f"1 selected pair(s) {what}" in err and "T2-fresh-A-u1-1 under initial_plain" in err


def test_the_pairs_of_an_excluded_attempt_do_not_refuse_the_run(tmp_path):
    run, tasks = _world(tmp_path, outcome={(EXCLUDED, "full_plain"): "timeout", (EXCLUDED, "initial_plain"): "unresolved"})
    assert _select(tmp_path, run, tasks) == 0


@pytest.mark.parametrize(("edit", "says"), [
    (lambda a: _entry(a, "T1", "full_plain", "T1-fresh-A-u1-2").update(label="valid"),
     "T1-fresh-A-u1-2 under full_plain: label 'valid' in analysis.json, 'invalid' in the records"),
    (lambda a: _entry(a, "T1", "full_plain", "T1-fresh-A-u1-2").update(outcome="task_failure"),
     "T1-fresh-A-u1-2 under full_plain: outcome 'task_failure' in analysis.json, 'pass' in the records"),
    (lambda a: _entry(a, "T2", "initial_plain", "T2-fresh-A-u1-1").update(origin="constructed_near_miss"),
     "T2-fresh-A-u1-1 under initial_plain: origin 'constructed_near_miss' in analysis.json, 'fresh_attempt' in the records"),
    (lambda a: a["per_task"]["T2"]["initial_plain"].remove(_entry(a, "T2", "initial_plain", "T2-fresh-A-u1-1")),
     "T2-fresh-A-u1-1 under initial_plain is not in analysis.json's per-task listing"),
    (lambda a: a["fresh_attempts"].update(excluded=[]),
     "analysis.json excludes the attempts [], and the analysis' rule excludes [('T1', 'T1-fresh-B-final-2')] now"),
    (lambda a: a.update(per_task=["not", "a", "listing"]), "holds no per-task listing in the form the analysis writes"),
])
def test_a_disagreement_with_the_runs_analysis_is_refused(tmp_path, capsys, edit, says):
    run, tasks = _world(tmp_path)
    analyze(run, tasks, allow_proposed=True, n_boot=20)
    assert _select(tmp_path, run, tasks) == 0
    m = _manifest(tmp_path / "out")
    assert m["consistency"] == {"analysis_json": "matches", "analysis_label_rule": "pilot",
                                "compared_fields": ["origin", "outcome", "label", "negative_type"], "compared_pairs": 18,
                                "excluded_attempts_compared": True, "oracle_gated_compared": True}
    assert "run/analysis.json" in m["inputs_sha256"]
    _edit_analysis(run, edit)
    assert says in _refused(capsys, _select(tmp_path, run, tasks))


def test_an_analysis_json_that_cannot_be_read_is_refused(tmp_path, capsys):
    run, tasks = _world(tmp_path)
    (run / "analysis.json").write_text("{not json", encoding="utf-8")
    assert "the run's analysis.json cannot be read" in _refused(capsys, _select(tmp_path, run, tasks))


@pytest.mark.parametrize(("change", "drop", "says"), [
    ({"conditions": ["initial_plain", "reference_check"]}, (), "is not an evaluated condition"),
    ({"conditions": ["initial_plain", "full_plain", "full_plain"]}, (), "the config names a condition more than once"),
    ({"conditions": "initial_plain"}, (), "the config's conditions must be a non-empty list of condition names"),
    ({"data_filters": {"naive_control": "initial_plain", "correction_aware": "full_audited"}}, (), "is not one of the config's"),
    ({"data_filters": {}}, (), "the config's data_filters must map each role to a condition"),
    ({"label_source": {"policy": "pilot", "labeler": "someone-else"}}, (), "policy pilot reads rule D19's proposals"),
    ({"label_source": {"policy": "human", "labeler": "x"}}, (), "policy human reads human labels only, so its labeler must be null"),
    ({"label_source": {"policy": "check", "labeler": None}}, (), "is not one of the analysis' primary label rules"),
    ({"label_source": "pilot"}, (), "the config's label_source must be {policy, labeler}"),
    ({"label_source": {"policy": "pilot", "labeler": bts.PILOT_LABELER, "and": 1}}, (),
     "the config's label_source must be {policy, labeler}"),
    ({"candidates": "constructed_near_miss"}, (), "selects fresh attempts"),
    ({"run": {"run_id": "other-run", "dir": "results/runs/other-run", "repeats": 3}}, (), "the config is for 'other-run'"),
    ({"run": {"run_id": RUN, "dir": f"results/runs/{RUN}", "repeats": 0}}, (), "the config's run must be {run_id, dir, repeats}"),
    ({"schema": "tracecontract/downstream-selection-config/9.9"}, (), "the config's schema is"),
    ({"standing": "afterwards"}, (), "the config's standing 'afterwards' is not one of 'post hoc', 'pre-specified'"),
    ({"standing": ["post hoc"]}, (), "the config's standing ['post hoc'] is not one of"),
    ({"status": " "}, (), "the config's status must be a non-empty string"),
    ({"cell_gate": {"reference": "pass", "noop": "pass", "noop_required": False}}, (), "the config's cell_gate must be"),
    ({"cell_gate": {"reference": "pass", "noop": "task_failure", "noop_required": "no"}}, (), "the config's cell_gate must be"),
    ({"cell_gate": {"reference": "pass", "noop": "task_failure"}}, (), "the config's cell_gate must be"),
    ({"extra": 1}, (), "the config has keys this script does not read: extra"),
    ({}, ("cell_gate", "standing"), "the config lacks cell_gate, standing"),
])
def test_a_config_this_script_does_not_implement_is_refused(tmp_path, capsys, change, drop, says):
    run, tasks = _world(tmp_path)
    assert says in _refused(capsys, _select(tmp_path, run, tasks, config=_config(tmp_path, drop, **change)))
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(("text", "says"), [("{not json", "cannot be read as JSON"), ("[]", "is not a JSON object")])
def test_a_config_that_is_not_a_json_object_is_refused(tmp_path, capsys, text, says):
    run, tasks = _world(tmp_path)
    (tmp_path / "bad.json").write_text(text, encoding="utf-8")
    assert says in _refused(capsys, _select(tmp_path, run, tasks, config=tmp_path / "bad.json"))


def test_a_run_whose_manifest_lacks_what_the_config_names_is_refused(tmp_path, capsys):
    run, tasks = _world(tmp_path)
    cfg = _config(tmp_path, conditions=[*CONDS, "llm_freeform"])
    err = _refused(capsys, _select(tmp_path, run, tasks, config=cfg))
    assert "T1: the run graded no verifier under the condition llm_freeform" in err
    assert "T2: the run graded no verifier under the condition llm_freeform" in err
    m = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    write_json({**m, "tasks": []}, run / "manifest.json")
    assert "the run's manifest names no task" in _refused(capsys, _select(tmp_path, run, tasks))
    (run / "manifest.json").unlink()
    assert "the run's manifest.json cannot be read" in _refused(capsys, _select(tmp_path, run, tasks))


def test_a_run_that_the_analysis_cannot_read_is_refused(tmp_path, capsys):
    run, tasks = _world(tmp_path)
    m = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    m["tasks"][0]["verifiers"]["another_c1"] = {"condition": "initial_plain"}  # two verifiers of T1 under C1
    write_json(m, run / "manifest.json")
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert "cannot be read as the analysis reads them (ConditionConflict" in err


@pytest.mark.parametrize("where", ["run", "tasks", "results/runs"])
def test_it_never_writes_into_a_run_directory_or_the_tasks_root(tmp_path, capsys, where):
    run, tasks = _world(tmp_path)
    out = {"run": run / "selection", "tasks": tasks / "selection",
           "results/runs": bts.ROOT / "results" / "runs" / "zz-selection-test-never-written"}[where]
    try:
        assert "never writes" in _refused(capsys, _select(tmp_path, run, tasks, out=out))
        assert not out.exists()
    finally:
        if where == "results/runs" and out.exists():
            shutil.rmtree(out)


def test_a_task_without_its_reference_contract_is_refused(tmp_path, capsys):
    run, tasks = _world(tmp_path)
    (tasks / "T1" / "contracts" / "reference.json").unlink()
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert "no reference contract for T1: the kinds of invalid attempt cannot be told apart" in err


def test_a_run_that_mixes_populations_is_refused(tmp_path, capsys):
    run, tasks = _world(tmp_path, population={"T2": Population.natural_pr_review})
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert "the run mixes the populations controlled, natural:pr-review, which are never pooled silently" in err


def test_a_run_without_a_kept_attempt_is_refused(tmp_path, capsys):
    run, tasks = _world(tmp_path, audit=False)
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert "the run holds no fresh attempt (origin fresh_attempt) that the analysis keeps" in err


def test_rows_that_disagree_with_the_label_rule_are_refused(tmp_path, capsys, monkeypatch):
    run, tasks = _world(tmp_path)
    real = bts.build_rows

    def built(*args, **kwargs):
        rows, meta = real(*args, **kwargs)
        return [dataclasses.replace(r, label="valid") if (r.candidate_id, r.condition) == ("T1-fresh-A-u1-2", "full_plain")
                else r for r in rows], meta

    monkeypatch.setattr(bts, "build_rows", built)
    err = _refused(capsys, _select(tmp_path, run, tasks))
    assert "T1-fresh-A-u1-2: its rows disagree on its label or negative type" in err


# ---------------------------------------------------------------- standing


def test_the_standing_and_the_status_come_from_the_config(tmp_path):
    status = "The data step of a synthetic pool, configured before the pool was graded."
    run, tasks = _world(tmp_path)
    assert _select(tmp_path, run, tasks, config=_config(tmp_path, standing="pre-specified", status=status)) == 0
    m = _manifest(tmp_path / "out")
    assert (m["standing"], m["status"]) == ("pre-specified", status)
    assert m["tag"].startswith("pre-specified, as its configuration states: built from the records of syn-v1 under a "
                               "configuration fixed before the run was graded")
    md = (tmp_path / "out" / bts.TABLE).read_text(encoding="utf-8")
    assert md.count(status) == 1 and "**Pre-specified, as its configuration states.**" in md
    assert "post hoc" not in md.lower() and "after the run was graded and analysed" not in md


# ---------------------------------------------------------------- natural PR-review tasks


def test_a_natural_tasks_session_and_the_modules_that_read_it_are_hashed(tmp_path):
    run, tasks = _world(tmp_path, population=dict.fromkeys(FAMILY, Population.natural_pr_review), sessions=True)
    assert _select(tmp_path, run, tasks) == 0
    m = _manifest(tmp_path / "out")
    assert m["run"]["population"] == "natural:pr-review"
    for t in FAMILY:
        assert m["inputs_sha256"][f"tasks/{t}/session.json"] == hashlib.sha256(
            (tasks / t / "session.json").read_bytes()).hexdigest()
    pkg = ROOT / "src" / "tracecontract"
    natural = m["code_revision"]["selection_files_sha256"]
    assert natural == {"scripts/build_training_selection.py": hashlib.sha256(
        (ROOT / "scripts" / "build_training_selection.py").read_bytes()).hexdigest(),
        **{f"src/tracecontract/{n}": hashlib.sha256((pkg / n).read_bytes()).hexdigest() for n in bts._package_files(True)}}
    # The first prompt comes from the session; here it is the event R-init was introduced at, so the kinds are unchanged.
    assert m["attempts"]["T1-fresh-A-u1-1"]["kind"] == "correction_violator"
    assert m["attempts"]["T1-fresh-B-u1-1"]["kind"] == "other_invalid"
    controlled = _world(tmp_path / "controlled")
    assert _select(tmp_path / "controlled", *controlled) == 0
    code = _manifest(tmp_path / "controlled" / "out")["code_revision"]["selection_files_sha256"]
    assert set(code) == {"scripts/build_training_selection.py", *(f"src/tracecontract/{n}" for n in bts._package_files(False))}
    assert {"src/tracecontract/tasks.py", "src/tracecontract/contract.py"} <= set(natural) - set(code)
    assert not any("session.json" in k for k in _manifest(tmp_path / "controlled" / "out")["inputs_sha256"])


def test_the_hashed_package_files_are_those_the_analysis_and_its_natural_reading_load():
    plain, natural = bts._package_files(False), bts._package_files(True)
    # importing the analysis loads the modules it imports (strata imports patches; metrics imports stats)
    assert {"__init__.py", "analysis.py", "metrics.py", "patches.py", "schemas.py", "stats.py", "store.py",
            "strata.py"} <= set(plain)
    assert set(plain) < set(natural) and {"tasks.py", "contract.py"} <= set(natural) - set(plain)
    # NATURAL_ENTRY are the modules that the analysis imports to read a natural task's session
    assert "from .tasks import session_for_task" in inspect.getsource(tc_analysis._natural_session)
    assert "from .contract import first_user_prompt" in inspect.getsource(tc_analysis.natural_first_prompt)
    assert bts.NATURAL_ENTRY == ("tracecontract.tasks", "tracecontract.contract")
    # the same files as a fresh interpreter of the test's own environment loads, whatever this process imported
    probe = ("import json, sys\n"
             "import tracecontract.analysis\n"
             "base = {m.__file__ for k, m in list(sys.modules.items()) if k.split('.')[0] == 'tracecontract'}\n"
             "import tracecontract.tasks, tracecontract.contract\n"
             "every = {m.__file__ for k, m in list(sys.modules.items()) if k.split('.')[0] == 'tracecontract'}\n"
             "print(json.dumps([sorted(base), sorted(every)]))\n")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run([sys.executable, "-B", "-c", probe], env=env, capture_output=True, text=True, check=True).stdout
    pkg = (ROOT / "src" / "tracecontract").resolve()
    seen = [tuple(sorted(Path(f).resolve().relative_to(pkg).as_posix() for f in files)) for files in json.loads(out)]
    assert seen == [plain, natural]
    from tracecontract.tasks import PR_SESSION_FILE

    assert bts.SESSION_FILE == PR_SESSION_FILE


# ---------------------------------------------------------------- determinism


def test_the_output_is_a_function_of_the_inputs_bytes(tmp_path, capsys):
    run, tasks = _world(tmp_path / "a")
    assert _select(tmp_path / "a", run, tasks) == 0
    first = {p.name: p.read_bytes() for p in (tmp_path / "a" / "out").iterdir()}
    assert sorted(first) == [bts.TABLE, bts.MANIFEST]
    assert _select(tmp_path / "a", run, tasks) == 0  # again, in place
    assert {p.name: p.read_bytes() for p in (tmp_path / "a" / "out").iterdir()} == first
    # The same files elsewhere, under another working directory: the same bytes (no local path, clock or revision).
    shutil.copytree(tmp_path / "a" / "results", tmp_path / "b" / "deeper" / "results")
    shutil.copytree(tmp_path / "a" / "tasks", tmp_path / "b" / "deeper" / "tasks")
    b = tmp_path / "b" / "deeper"
    assert _select(b, b / "results" / "runs" / RUN, b / "tasks") == 0
    assert {p.name: p.read_bytes() for p in (b / "out").iterdir()} == first
    # --check rebuilds and compares without writing; one changed byte fails it.
    capsys.readouterr()
    assert _select(b, b / "results" / "runs" / RUN, b / "tasks", "--check") == 0
    assert "regenerates byte for byte" in capsys.readouterr().out
    table = b / "out" / bts.TABLE
    table.write_bytes(table.read_bytes().replace(b"7 (4, 3)", b"7 (3, 4)"))
    assert _select(b, b / "results" / "runs" / RUN, b / "tasks", "--check") == 1
    assert table.read_bytes() != first[bts.TABLE]


def test_the_order_of_the_results_changes_nothing_but_their_hash(tmp_path):
    outs = []
    for seed in (None, 7):
        root = tmp_path / str(seed)
        run, tasks = _world(root, shuffle=seed)
        assert _select(root, run, tasks) == 0
        m = _manifest(root / "out")
        m["inputs_sha256"].pop("run/results.jsonl")
        outs.append((m, (root / "out" / bts.TABLE).read_bytes()))
    assert outs[0] == outs[1]


def test_attempts_that_share_a_graded_patch_count_once_as_distinct_patches(tmp_path):
    shared = dict.fromkeys(("T1-fresh-A-final-1", "T1-fresh-B-final-1"), "T1-final-shared")
    run, tasks = _world(tmp_path, body=shared)
    assert _select(tmp_path, run, tasks) == 0
    m = _manifest(tmp_path / "out")
    assert m["attempts"]["T1-fresh-A-final-1"]["graded_patch_sha256"] == m["attempts"]["T1-fresh-B-final-1"]["graded_patch_sha256"]
    assert (m["pool"]["counts"]["attempts"]["total"], m["pool"]["distinct_graded_patches"]) == (9, 8)
    c1, c3 = (m["conditions"][c]["gated"] for c in CONDS)
    assert (c1["counts"]["admitted"]["total"], c1["distinct_graded_patches"]) == (5, 5)  # C1 admits B-final-1 alone
    assert (c3["counts"]["admitted"]["total"], c3["distinct_graded_patches"]) == (7, 6)
    md = (tmp_path / "out" / bts.TABLE).read_text(encoding="utf-8")
    assert md.endswith("Distinct graded patches among the attempts counted: pool 8 of 9; C1 gated 5 of 5; C1 ungated 5 of 5; "
                       "C3 gated 6 of 7; C3 ungated 6 of 7.\n")


# ---------------------------------------------------------------- the repository's config and committed selection


def test_the_repositorys_config_names_c1_and_c3_as_the_data_filters():
    cfg, meta = bts.read_config(CONFIG)
    assert cfg["data_filters"] == {"naive_control": "initial_plain", "correction_aware": "full_plain"}
    assert cfg["acceptance_rule"] == bts.ACCEPTANCE_RULE and cfg["run"] == {"run_id": "fresh-v1",
                                                                           "dir": "results/runs/fresh-v1", "repeats": 3}
    assert cfg["standing"] == "post hoc" and cfg["cell_gate"] == _gate(False)  # fresh-v1 graded no no-op
    assert "applied post hoc to the recorded run fresh-v1" in cfg["status"]
    assert meta["file"] == "configs/downstream/rft_selection_v0.1.json"


def test_the_committed_fresh_v1_selection_regenerates_from_its_records(tmp_path):
    """A tripwire: it fails when the script, its config or any input it hashes changes (the run's records and
    analysis.json, the task files and stratum candidates of CS-01 to CS-04); the committed files are then regenerated."""
    assert bts.main(["--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / bts.TABLE).read_bytes() == (COMMITTED / bts.TABLE).read_bytes()
    new, old = _manifest(tmp_path / "out"), _manifest(COMMITTED)
    # Analysis code may change after the selection was written (as verify_frozen_inputs.py allows for the analysis);
    # everything else, the hashes of the inputs included, must be the same.
    assert set(new["code_revision"]["selection_files_sha256"]) == set(old["code_revision"]["selection_files_sha256"])
    new["code_revision"].pop("selection_files_sha256")
    old["code_revision"].pop("selection_files_sha256")
    assert new == old
    c1, c3 = (new["conditions"][c] for c in ("initial_plain", "full_plain"))
    assert (new["pool"]["counts"]["attempts"]["total"], len(new["excluded"])) == (79, 1)
    assert (c1["cells_dropped"], c3["cells_dropped"]) == (["CS-01"], [])
    for d, gated, ungated in ((c1, (51, 14, 0), (61, 24, 0)), (c3, (52, 0, 2), (52, 0, 2))):
        for which, want in (("gated", gated), ("ungated", ungated)):
            k = d[which]["counts"]
            assert (k["admitted"]["total"], k["correction_violator"]["total"], k["regression_only"]["total"]) == want
