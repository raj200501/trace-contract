"""Offline pipeline tests (no Docker, no network, no model API).

Synthetic fixtures only: they test that recorded runs are analysed and reported
correctly, transcripts are sanitised, scripted turns are recognised and the
contamination audit works. They are not research evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

from tracecontract.analysis import analyze
from tracecontract.controlled import audit_access
from tracecontract.ingest.claude_code import parse_claude_code_jsonl, sanitize_transcript
from tracecontract.report import build_report
from tracecontract.schemas import (
    Candidate, CandidateOrigin, ContractVariant, EvidenceSpan, Label, LabelerKind, Outcome, Population, Requirement,
    RequirementKind, RequirementStatus, SnapshotSource, Split, TaskContract, TaskManifest, VerificationResult, sha256_text,
)
from tracecontract.store import append_jsonl, dump, write_json

FIX = Path(__file__).parent / "fixtures" / "claude_code_session.jsonl"


def test_sanitize_drops_internals_and_relabels(tmp_path):
    src = tmp_path / "raw.jsonl"
    entries = [
        {"type": "user", "sessionId": "parent", "agentId": "secret-agent", "isSidechain": True, "requestId": "req_1",
         "cwd": "/home/x", "uuid": "a", "timestamp": "t", "message": {"role": "user", "content": "Please add X."}},
        {"type": "attachment", "attachment": {"k": "v"}},
        {"type": "assistant", "isSidechain": True, "uuid": "b", "parentUuid": "a", "timestamp": "t", "requestId": "req_2",
         "message": {"role": "assistant", "model": "m", "content": [{"type": "text", "text": "ok"}],
                     "usage": {"input_tokens": 5, "output_tokens": 2, "server_tool_use": {"x": 1}}, "id": "msg_1"}},
    ]
    src.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    dst = tmp_path / "clean.jsonl"
    info = sanitize_transcript(src, dst, session_id="S-1")
    text = dst.read_text()
    for leaked in ("secret-agent", "req_1", "req_2", "/home/x", "msg_1", "attachment"):
        assert leaked not in text
    assert {json.loads(ln)["sessionId"] for ln in text.splitlines()} == {"S-1"}
    assert info["entries"] == 2 and info["dropped"] == {"attachment": 1}
    s = parse_claude_code_jsonl(dst, population=Population.controlled, source="t")
    assert s.session_id == "S-1" and len(s.user_prompts()) == 1
    usage = json.loads(text.splitlines()[1])["message"]["usage"]
    assert usage == {"input_tokens": 5, "output_tokens": 2}


def test_scripted_turn_inside_harness_wrapper(tmp_path):
    p = tmp_path / "t.jsonl"
    turn = "Actually, keep the default output unchanged."
    rows = [
        {"type": "user", "sessionId": "S", "uuid": "1", "message": {"role": "user", "content": "Do X."}},
        {"type": "user", "sessionId": "S", "uuid": "2", "isMeta": True,
         "message": {"role": "user", "content": f"The coordinator sent a message while you were working:\n{turn}\n\nAddress this."}},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    plain = parse_claude_code_jsonl(p, population=Population.controlled, source="t")
    assert len(plain.user_prompts()) == 1  # wrapped turn looks injected without the registry
    s = parse_claude_code_jsonl(p, population=Population.controlled, source="t", scripted_turns=["Do X.", turn])
    assert [e.text[:6] for e in s.user_prompts()] == ["Do X.", "The co"]


def test_access_audit_flags_study_locations():
    s = parse_claude_code_jsonl(FIX, population=Population.fixture, source="t")
    ev = next(e for e in s.events if e.tool_name == "Read")
    bad = ev.model_copy(update={"tool_input": {"file_path": "/home/user/trace-contract/data/controlled/scenarios/X.json"}})
    s2 = s.model_copy(update={"events": [bad if e.event_id == ev.event_id else e for e in s.events]})
    findings = audit_access(s2, ("/repo",))
    assert any(f.reason == "contamination" for f in findings)
    assert not [f for f in audit_access(s, ("/repo",)) if f.reason == "contamination"]


def _mk_task(root: Path, tid: str, fam: str) -> None:
    tdir = root / "tasks" / tid
    (tdir / "candidates").mkdir(parents=True)
    (tdir / "contracts").mkdir()
    sess_first, sess_later = f"{tid}-s/L000001.00", f"{tid}-s/L000005.00"
    ref = TaskContract(contract_id=f"{tid}-reference", task_id=tid, session_id=f"{tid}-s", variant=ContractVariant.reference,
                       created_by="t", created_at="t", requirements=[
                           Requirement(req_id="R-init", statement="s", kind=RequirementKind.change, status=RequirementStatus.explicit,
                                       introduced_at=sess_first, evidence=[EvidenceSpan(event_id=sess_first, start=0, end=1, quote="x")],
                                       proposer="t"),
                           Requirement(req_id="R-corr", statement="s", kind=RequirementKind.invariant, status=RequirementStatus.explicit,
                                       introduced_at=sess_later, evidence=[EvidenceSpan(event_id=sess_later, start=0, end=1, quote="y")],
                                       proposer="t")])
    dump(ref, tdir / "contracts" / "reference.json")

    def cand(cid, origin, label, violated=()):
        c = Candidate(candidate_id=cid, task_id=tid, origin=origin, split=Split.eval, patch="", patch_sha256=sha256_text(""),
                      produced_by="fixture",
                      labels=[Label(value=label, violated_requirements=list(violated), labeler="m", labeler_kind=LabelerKind.model, timestamp="t")])
        dump(c, tdir / "candidates" / f"{cid}.json")
        return f"candidates/{cid}.json"

    paths = [cand(f"{tid}-pre", CandidateOrigin.observed_pre_correction, "invalid", ["R-corr"]),
             cand(f"{tid}-alt", CandidateOrigin.valid_alternative, "valid"),
             cand(f"{tid}-nm", CandidateOrigin.constructed_near_miss, "invalid", ["R-init"])]
    m = TaskManifest(task_id=tid, family_id=fam, population=Population.fixture, status="draft", provenance="p.json",
                     snapshot_source=SnapshotSource(repo_url="https://example.invalid/r", commit="0" * 40),
                     env_requirements=[], contracts={"reference": "contracts/reference.json"}, candidates=paths)
    dump(m, tdir / "task.json")


def test_analysis_and_report_from_recorded_run(tmp_path):
    for tid, fam in (("T1", "F1"), ("T2", "F2")):
        _mk_task(tmp_path, tid, fam)
    run = tmp_path / "results" / "runs" / "r1"
    run.mkdir(parents=True)
    manifest = {"run_id": "r1", "started_at": "t", "code_revision": "x", "tasks": []}
    outcomes = {("initial_plain", "pre"): "pass", ("initial_plain", "alt"): "pass", ("initial_plain", "nm"): "task_failure",
                ("full_audited", "pre"): "task_failure", ("full_audited", "alt"): "pass", ("full_audited", "nm"): "verifier_error"}
    for tid in ("T1", "T2"):
        manifest["tasks"].append({"task_id": tid, "family_id": "F" + tid[1], "verifiers": {
            "initial_plain": {"condition": "initial_plain"}, "full_audited": {"condition": "full_audited"}}})
        for (vid, c), oc in outcomes.items():
            append_jsonl(VerificationResult(run_id="r1", task_id=tid, verifier_id=vid, candidate_id=f"{tid}-{c}", outcome=Outcome(oc),
                                            reward=1.0 if oc == "pass" else 0.0, started_at="s", finished_at="f", wall_s=0.1,
                                            harness_version="h"), run / "results.jsonl")
    write_json(manifest, run / "manifest.json")
    # Human-only policy: no human labels -> nothing labeled.
    a0 = analyze(run, tmp_path / "tasks", allow_proposed=False, n_boot=100)
    assert a0["conditions"]["initial_plain"]["false_acceptance"]["den"] == 0
    a = analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=200)
    ip, fa = a["conditions"]["initial_plain"], a["conditions"]["full_audited"]
    assert ip["false_acceptance"]["num"] == 2 and ip["false_acceptance"]["den"] == 4
    assert fa["false_acceptance"]["num"] == 0 and fa["infrastructure"]["num"] == 2
    assert a["by_negative_type"]["initial_plain"]["correction_violating"] == {"accepted": 2, "n": 2}
    md = (run / "analysis.md").read_text()
    assert "Automated pilot" in md and "initial_plain" in md
    out = build_report(run, tmp_path / "tasks", tmp_path, tmp_path / "report.html")
    html = out.read_text()
    assert "Automated pilot" in html and "T1-pre" in html and "<table>" in html
