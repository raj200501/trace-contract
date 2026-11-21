"""Triage proposals (rule:v1), the natural-data screening rule and its rejection path (decision log D47).

All sessions here are synthetic fixtures; they test code behaviour only, not research claims.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.ingest.repo_evidence import licence_evidence, licence_from_text
from tracecontract.ingest.replay import PathMap, load_raw_extras
from tracecontract.schemas import (
    ContractVariant, Eligibility, EvidenceSpan, Population, Requirement, RequirementKind, RequirementStatus, TaskContract,
    TriageCategory,
)
from tracecontract.triage import collect_signals, correction_candidates, propose_triage, screen_eligibility

R = Path(__file__).resolve().parents[1]
ROOT = "/w/repo"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, R / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def session_file(tmp: Path, steps: list[tuple], name: str = "s.jsonl", sid: str = "S") -> Path:
    """steps: ("user", text) or (tool, input, result[, is_error[, toolUseResult]])."""
    rows, n = [], 0
    for st in steps:
        if st[0] == "user":
            rows.append({"type": "user", "sessionId": sid, "cwd": ROOT, "message": {"role": "user", "content": st[1]}})
            continue
        n += 1
        tool, inp, result = st[0], st[1], st[2]
        rows.append({"type": "assistant", "sessionId": sid, "cwd": ROOT, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{n}", "name": tool, "input": inp}]}})
        row = {"type": "user", "sessionId": sid, "cwd": ROOT, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{n}", "content": result, "is_error": len(st) > 3 and st[3]}]}}
        if len(st) > 4:
            row["toolUseResult"] = st[4]
        rows.append(row)
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def triage_of(tmp: Path, steps: list[tuple], **kw):
    s = parse_claude_code_jsonl(session_file(tmp, steps), population=Population.fixture, source="fixture")
    sig = collect_signals(s, **kw)
    return sig, propose_triage(sig)


EDIT = ("Edit", {"file_path": f"{ROOT}/app.py", "old_string": "a", "new_string": "b"}, "updated")


def test_unsuitable_task_without_file_changes(tmp_path):
    sig, p = triage_of(tmp_path, [("user", "How does the scheduler pick the next task?"),
                                  ("Read", {"file_path": f"{ROOT}/sched.c"}, "1\tint x;")], base_commit="pinned")
    assert p.category == TriageCategory.unsuitable_task and p.confidence == "high" and p.method == "rule:v1"
    _, p2 = triage_of(tmp_path, [("user", "Make the footer purple please."),
                                 ("Edit", {"file_path": f"{ROOT}/style.css", "old_string": "a", "new_string": "b"}, "ok")],
                      base_commit="pinned")
    assert p2.category == TriageCategory.unsuitable_task and "presentation" in p2.reasons[0]


def test_environment_failure(tmp_path):
    bad = [("Bash", {"command": f"tool{i}"}, f"Exit code 127\n/bin/sh: tool{i}: command not found", True) for i in range(3)]
    sig, p = triage_of(tmp_path, [("user", "Build the project and fix it."), EDIT, *bad], base_commit="pinned")
    assert sig.environment_errors == 3 and sig.environment_markers == ["command_not_found"]
    assert p.category == TriageCategory.environment_failure


def test_incomplete_evidence(tmp_path):
    _, p = triage_of(tmp_path, [("user", "Add a flag to the CLI."), EDIT], base_commit="none")
    assert p.category == TriageCategory.incomplete_evidence and p.confidence == "high"
    _, p2 = triage_of(tmp_path, [("user", "Add a flag to the CLI."), EDIT], base_commit="pinned", absent_reads=2)
    assert p2.category == TriageCategory.incomplete_evidence and "absent from the snapshot" in p2.reasons[0]


def _contract(statuses: list[RequirementStatus]) -> TaskContract:
    reqs = []
    for i, st in enumerate(statuses):
        span = EvidenceSpan(event_id="S/L000001.00", start=0, end=1, quote="A")
        extra = {RequirementStatus.explicit: {"evidence": [span]}, RequirementStatus.inferred: {"rationale": "r"}}.get(st, {})
        reqs.append(Requirement(req_id=f"R{i}", statement="s", kind=RequirementKind.change, status=st,
                                introduced_at="S/L000001.00", proposer="rule:v1", scored=st != RequirementStatus.unresolved,
                                **extra))
    return TaskContract(contract_id="c", task_id="T", session_id="S", variant=ContractVariant.full_session, requirements=reqs,
                        created_by="fixture", created_at="2026-11-21T00:00:00Z")


def test_ambiguous_objective(tmp_path):
    steps = [("user", "Add a flag to the CLI."), EDIT]
    ambiguous = _contract([RequirementStatus.explicit, RequirementStatus.unresolved])
    _, p = triage_of(tmp_path, steps, base_commit="pinned", contract=ambiguous)
    assert p.category == TriageCategory.ambiguous_objective
    resolved = _contract([RequirementStatus.explicit] * 3 + [RequirementStatus.unresolved])
    _, p2 = triage_of(tmp_path, steps, base_commit="pinned", contract=resolved)
    assert p2.category == TriageCategory.candidate and any(r.startswith("note: 1 unresolved") for r in p2.reasons)
    _, p3 = triage_of(tmp_path, [("user", "fix it"), EDIT], base_commit="pinned")
    assert p3.category == TriageCategory.ambiguous_objective and p3.confidence == "low"


def test_apparent_model_failure(tmp_path):
    failing = ("Bash", {"command": "python -m pytest -q"}, "1 failed, 4 passed in 0.2s", True)
    sig, p = triage_of(tmp_path, [("user", "Add a flag to the CLI."), EDIT, failing], base_commit="pinned")
    assert sig.test_runner == "pytest" and sig.last_test == "failed" and p.category == TriageCategory.apparent_model_failure
    rejected = ("Edit", {"file_path": f"{ROOT}/app.py", "old_string": "b", "new_string": "c"},
                "The user doesn't want to proceed with this tool use. The tool use was rejected", True)
    _, p2 = triage_of(tmp_path, [("user", "Add a flag to the CLI."), EDIT, rejected], base_commit="pinned")
    assert p2.category == TriageCategory.apparent_model_failure and "rejected 1 file edit" in p2.reasons[0]
    _, p3 = triage_of(tmp_path, [("user", "Add a flag to the CLI."), EDIT, ("user", "It still doesn't work.")],
                      base_commit="pinned")
    assert p3.category == TriageCategory.apparent_model_failure


def test_candidate_priority_and_ide_context(tmp_path):
    steps = [("user", "Add a --verbose flag to the CLI."), EDIT,
             ("user", "<ide_opened_file>The user opened cli.py; don't mind it.</ide_opened_file>"),
             ("user", "Actually, keep the old default output."), EDIT,
             ("Bash", {"command": "pytest -q"}, "5 passed")]
    sig, p = triage_of(tmp_path, steps, base_commit="pinned")
    assert p.category == TriageCategory.candidate and len(p.correction_event_ids) == 1 and sig.ide_context_blocks == 1
    assert sig.last_test == "passed" and sig.user_prompts == 2
    # Several signals: the first category in rule order wins, every signal is a reason.
    _, both = triage_of(tmp_path, [("user", "Explain how the scheduler works.")], base_commit="none")
    assert both.category == TriageCategory.unsuitable_task and len(both.reasons) == 2


def test_screen_eligibility(tmp_path):
    sig, p = triage_of(tmp_path, [("user", "Add a flag."), EDIT, ("user", "Actually, keep the default.")],
                       base_commit="linked_commit_unverified")
    elig, reasons = screen_eligibility(sig, p, replay_fidelity="unreconstructable", licence="MIT")
    assert elig == Eligibility.pending_review and "network check" in reasons[0]
    elig2, reasons2 = screen_eligibility(sig, p, replay_fidelity="unreconstructable", licence=None, replay_supported=False)
    assert elig2 == Eligibility.rejected and len(reasons2) == 2


def test_licence_evidence(tmp_path):
    mit = "MIT License\n\nCopyright (c) 2026 Someone\n\nPermission is hereby granted, free of charge, to any person"
    p = session_file(tmp_path, [("user", "Add a LICENSE, MIT licensed please."),
                                ("Write", {"file_path": f"{ROOT}/LICENSE", "content": mit}, "File created successfully")])
    s = parse_claude_code_jsonl(p, population=Population.fixture, source="fixture")
    ev = licence_evidence(s, load_raw_extras(p), PathMap(ROOT))
    assert ev == {"spdx": "MIT", "evidence": "licence written in session", "claimed": "MIT"}
    assert licence_from_text("                Apache License\n          Version 2.0, January 2004") == "Apache-2.0"


def test_rejection_path_compiles_to_the_ledger(tmp_path):
    """A natural session without a recoverable base: rejected, Fidelity.unreconstructable, in the ledger."""
    data = tmp_path / "tc"
    path = session_file(data / "sessions" / "claude_code", [
        ("user", "Add input validation to the parser."),
        ("Edit", {"file_path": f"{ROOT}/parser.py", "old_string": "def parse(s):", "new_string": "def parse(s: str):"},
         "updated", False, {"originalFile": None}),
        ("user", "Actually, don't raise on empty input."),
        ("Edit", {"file_path": f"{ROOT}/parser.py", "old_string": "raise", "new_string": "return None"}, "updated"),
    ], name="0000-fixture.jsonl", sid="fixture-session")
    from tracecontract.schemas import sha256_bytes
    (data / "_download_record.json").write_text(json.dumps({"fetched_utc": "2026-11-21T00:00:00Z", "files": [
        {"path": "sessions/claude_code/0000-fixture.jsonl", "sha256": sha256_bytes(path.read_bytes()), "verified": True}]}))
    rows = _script("screen_trace_commons").screen(data)
    assert len(rows) == 1
    row = rows[0]
    assert row["population"] == "natural:chat" and row["eligibility"] == "rejected"
    assert row["screening"]["fidelity"] == "unreconstructable"
    assert row["screening"]["replay"]["reasons"][0].startswith("no base tree")
    assert "no recoverable base commit (none)" in row["rejection_reasons"]
    assert row["triage"]["category"] == "incomplete_evidence" and row["triage"]["correction_event_ids"] == ["L000004.00"]
    assert row["screening"]["download_record_match"] and row["screening"]["correction_candidates"] == 1
    assert row["repo_url"] is None and row["base_commit"] is None
    # build_manifests puts the rejected row in the ledger and the index, and describes the state.
    repo = tmp_path / "repo"
    (repo / "data" / "manifests").mkdir(parents=True)
    (repo / "tasks").mkdir()
    (repo / "data" / "manifests" / "screening_natural.json").write_text(json.dumps(rows))
    index, ledger = _script("build_manifests").build(repo)
    assert ledger["rejections"] == [{"source_id": "0000-fixture", "population": "natural:chat",
                                     "reasons": row["rejection_reasons"]}]
    assert index["yield_by_population"]["natural:chat"] == {"screened": 1, "rejected": 1, "not_accepted": 1}
    assert "natural:chat (screen-trace-commons:v1" in ledger["note"] and "1 rejected" in ledger["note"]


@pytest.mark.parametrize("tid", ["CS-01", "CS-02", "CS-03", "CS-04"])
def test_controlled_tasks_are_candidates(tid):
    if not (R / "snapshots" / tid).is_dir():
        pytest.skip("base snapshot missing (tracecontract snapshot)")
    p = _script("triage_controlled").triage_task(R / "tasks" / tid)
    assert p.category == TriageCategory.candidate and len(p.correction_event_ids) == 1


def test_correction_candidates_skip_ide_context(tmp_path):
    p = session_file(tmp_path, [("user", "Add X."),
                                ("user", "<ide_selection>The user selected: don't touch this</ide_selection>")])
    s = parse_claude_code_jsonl(p, population=Population.fixture, source="fixture")
    assert correction_candidates(s) == []


def _provenance(task_dir: Path, task_id: str = "FX-T") -> bytes:
    rec = {"schema_version": "x", "record_id": f"prov-{task_id}", "session_id": "s", "population": "fixture", "source_url": "u",
           "source_id": task_id, "permission_basis": "fixture", "capture_method": "fixture", "redaction_status": "none_needed",
           "task_family_id": task_id, "eligibility": "pending_review", "rejection_reasons": [], "triage": None,
           "accessed": "2026-11-21T00:00:00Z", "notes": ""}
    task_dir.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(rec, indent=2) + "\n").encode()
    (task_dir / "provenance.json").write_bytes(data)
    return data


def test_triage_sidecar_is_written_beside_the_frozen_provenance_record(tmp_path):
    from tracecontract.schemas import TriageProposal
    from tracecontract.triage import read_sidecar, render_sidecar, sidecar_record, write_sidecar

    td = tmp_path / "FX-T"
    frozen = _provenance(td)
    p = TriageProposal(category=TriageCategory.candidate, method="rule:v1", confidence="medium", reasons=["r"],
                       correction_event_ids=["s/L000003.00"])
    rec = sidecar_record("FX-T", "prov-FX-T", p, generator="fixture", inputs={"transcript_sha256": "ab"})
    assert write_sidecar(td, rec) is True
    assert (td / "triage.json").read_text() == render_sidecar(rec) and read_sidecar(td) == p
    mtime = (td / "triage.json").stat().st_mtime_ns
    assert write_sidecar(td, rec) is False and (td / "triage.json").stat().st_mtime_ns == mtime  # compared in memory first
    assert (td / "provenance.json").read_bytes() == frozen  # the frozen record is only read
    assert sorted(x.name for x in td.iterdir()) == ["provenance.json", "triage.json"]  # no temporary file is left
    # Refusals happen in memory, before anything is written.
    other = tmp_path / "FX-U"
    _provenance(other, "FX-U")
    for bad, msg in [(rec, "names task"),  # the record of FX-T in FX-U's directory
                     (sidecar_record("FX-U", "prov-other", p, generator="fixture", inputs={}), "provenance record"),
                     ({**sidecar_record("FX-U", "prov-FX-U", p, generator="fixture", inputs={}),
                       "triage": {**p.model_dump(mode="json"), "category": "not-a-category"}}, "category")]:
        with pytest.raises(ValueError, match=msg):
            write_sidecar(other, bad)
        assert not (other / "triage.json").exists()
    (other / "triage.json").write_text((td / "triage.json").read_text())  # FX-T's sidecar in FX-U's directory
    with pytest.raises(ValueError, match="names task"):
        read_sidecar(other)


def test_triage_script_writes_only_sidecars(tmp_path, monkeypatch):
    """scripts/triage_controlled.py --check writes nothing; a run writes triage.json and never the provenance record."""
    from tracecontract.schemas import TriageProposal

    mod = _script("triage_controlled")
    td = tmp_path / "tasks" / "FX-T"
    frozen = _provenance(td)
    (td / "task.json").write_text(json.dumps({"provenance": "provenance.json"}))
    p = TriageProposal(category=TriageCategory.candidate, method="rule:v1", confidence="low")
    monkeypatch.setattr(mod, "task_sidecar", lambda d: mod.sidecar_record(d.name, f"prov-{d.name}", p, generator=mod.GENERATOR,
                                                                         inputs={}))
    assert mod.main(["--check", str(td)]) == 1 and not (td / "triage.json").exists()
    assert mod.main([str(td)]) == 0 and (td / "triage.json").is_file()
    assert mod.main(["--check", str(td)]) == 0
    assert (td / "provenance.json").read_bytes() == frozen
