"""Tests for transcript ingestion, evidence alignment, and contract logic.

All inputs here are synthetic fixtures (population = fixture); they test code
behaviour only and are not research evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tracecontract.contract import (
    acceptance_gate,
    align_quote,
    derive_initial_only,
    propose_correction_events,
    render_instruction,
    requirements_from_proposals,
    validate_contract,
)
from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.schemas import (
    Author,
    ContractVariant,
    EventKind,
    Population,
    Requirement,
    RequirementKind,
    RequirementStatus,
    Review,
    ReviewerKind,
    TaskContract,
)

FIX = Path(__file__).parent / "fixtures" / "claude_code_session.jsonl"


@pytest.fixture()
def session():
    return parse_claude_code_jsonl(FIX, population=Population.fixture, source="fixture")


def test_parse_kinds_and_ids(session):
    kinds = [e.kind for e in session.events]
    assert session.session_id == "fixture-0001"
    assert session.metadata["bad_lines"] == [13]
    assert EventKind.metadata in kinds  # summary entry
    prompts = session.user_prompts()
    assert [p.text[:20] for p in prompts] == ["Please add a `--verb", "Actually, don't chan"]
    assert all(p.author == Author.scripted_user for p in prompts)
    injected = [e for e in session.events if e.kind == EventKind.system_injected]
    assert len(injected) == 2  # isMeta reminder + slash command
    assert any(e.kind == EventKind.user_interrupt for e in session.events)
    calls = [e for e in session.events if e.kind == EventKind.tool_call]
    results = [e for e in session.events if e.kind == EventKind.tool_result]
    assert [c.tool_name for c in calls] == ["Read", "Edit"]
    assert results[1].text == "File updated."
    assert all("sidechain" not in e.text for e in session.events)
    ids = [e.event_id for e in session.events]
    assert len(ids) == len(set(ids))
    assert prompts[0].event_id == "fixture-0001/L000002.00"
    assert len(session.trace_sha256) == 64


def test_natural_population_marks_human(session):
    nat = parse_claude_code_jsonl(FIX, population=Population.natural, source="x")
    assert all(p.author == Author.human for p in nat.user_prompts())


def test_align_quote_exact_normalised_missing(session):
    p = session.user_prompts()[1]
    al = align_quote(session, p.event_id, "keep `-v` working as the short form")
    assert al.exact and al.span is not None
    assert p.text[al.span.start:al.span.end] == al.span.quote
    al2 = align_quote(session, p.event_id, "keep   `-v`\nworking as  the short form")
    assert not al2.exact and al2.span is not None
    assert p.text[al2.span.start:al2.span.end] == al2.span.quote
    assert align_quote(session, p.event_id, "not in the text").span is None
    assert align_quote(session, "nope", "x").span is None


def _props(session):
    p1, p2 = session.user_prompts()
    return [
        {"req_id": "R1", "statement": "Add a --verbose flag that prints each processed file.", "kind": "change",
         "status": "explicit", "introduced_at": p1.event_id,
         "evidence": [{"event_id": p1.event_id, "quote": "add a `--verbose` flag"}], "observable": "run with --verbose"},
        {"req_id": "R2", "statement": "Default output is unchanged.", "kind": "invariant", "status": "explicit",
         "introduced_at": p2.event_id, "evidence": [{"event_id": p2.event_id, "quote": "don't change the default output"}],
         "observable": "run without flags"},
        {"req_id": "R3", "statement": "-v is the short form of --verbose.", "kind": "change", "status": "explicit",
         "introduced_at": p2.event_id, "evidence": [{"event_id": p2.event_id, "quote": "keep `-v` working as the short form"}],
         "observable": "run with -v"},
        {"req_id": "R4", "statement": "Quiet mode prints nothing.", "kind": "invariant", "status": "explicit",
         "introduced_at": p2.event_id, "evidence": [{"event_id": p2.event_id, "quote": "this quote is invented"}],
         "observable": "run with -q"},
    ]


def test_requirements_from_proposals_rejects_unsupported(session):
    out = requirements_from_proposals(session, _props(session), proposer="fixture")
    assert [r.req_id for r in out.requirements] == ["R1", "R2", "R3"]
    assert out.rejected and out.rejected[0]["proposal"]["req_id"] == "R4"


def test_unsupported_with_rationale_downgrades(session):
    props = _props(session)
    props[3]["rationale"] = "User says quiet mode must still print nothing."
    out = requirements_from_proposals(session, props, proposer="fixture")
    r4 = next(r for r in out.requirements if r.req_id == "R4")
    assert r4.status == RequirementStatus.inferred and r4.evidence == []


def _contract(session, reqs, variant=ContractVariant.full_session):
    return TaskContract(contract_id="c1", task_id="t1", session_id=session.session_id, variant=variant,
                        requirements=reqs, created_by="fixture", created_at="2026-01-01T00:00:00Z")


def test_supersession_and_initial_only(session):
    props = _props(session)[:3]
    props.append({"req_id": "R0", "statement": "Verbose output replaces the default output.", "kind": "change",
                  "status": "explicit", "introduced_at": session.user_prompts()[0].event_id,
                  "evidence": [{"event_id": session.user_prompts()[0].event_id, "quote": "prints each file it processes"}]})
    props[1]["supersedes"] = ["R0"]
    out = requirements_from_proposals(session, props, proposer="fixture")
    c = _contract(session, out.requirements)
    r0 = c.by_id("R0")
    assert r0.status == RequirementStatus.superseded and r0.superseded_by == "R2"
    assert not [i for i in validate_contract(c, session) if i.severity == "error"]
    init = derive_initial_only(c, session, contract_id="c1-init", created_at="t")
    assert {r.req_id for r in init.requirements} == {"R1", "R0"}
    assert all(r.status == RequirementStatus.explicit for r in init.requirements)
    assert not [i for i in validate_contract(init, session) if i.severity == "error"]
    text = render_instruction(c)
    assert "Default output is unchanged." in text and "Verbose output replaces" not in text


def test_validate_catches_errors(session):
    out = requirements_from_proposals(session, _props(session)[:3], proposer="fixture")
    reqs = out.requirements
    # Tamper with evidence text -> bad_evidence.
    bad = reqs[0].model_copy(update={"evidence": [reqs[0].evidence[0].model_copy(update={"quote": "X" * len(reqs[0].evidence[0].quote)})]})
    # Superseded by an EARLIER requirement -> supersession_order.
    p1 = session.user_prompts()[0].event_id
    later = reqs[1].model_copy(update={"status": RequirementStatus.superseded, "superseded_by": "R1"})
    conflict = reqs[2].model_copy(update={"conflicts_with": ["R1"]})
    c = _contract(session, [bad, later, conflict])
    codes = {i.code for i in validate_contract(c, session)}
    assert {"bad_evidence", "supersession_order", "active_conflict"} <= codes
    leak = _contract(session, [reqs[0], reqs[1]], variant=ContractVariant.initial_only)
    assert "initial_only_leak" in {i.code for i in validate_contract(leak, session)}
    assert p1  # silence unused warnings


def test_acceptance_gate_requires_human_review(session):
    p2 = session.user_prompts()[1].event_id
    inferred = Requirement(req_id="R9", statement="Quiet mode prints nothing.", kind=RequirementKind.invariant,
                           status=RequirementStatus.inferred, introduced_at=p2, rationale="implied", observable="-q",
                           proposer="fixture")
    c = _contract(session, [inferred])
    ok, reasons = acceptance_gate(c, session)
    assert not ok and any("needs_human_review" in r for r in reasons)
    model_review = Review(reviewer="m", reviewer_kind=ReviewerKind.model, decision="accept", timestamp="t")
    c2 = _contract(session, [inferred.model_copy(update={"reviews": [model_review]})])
    assert not acceptance_gate(c2, session)[0]  # a model review is not enough
    human = Review(reviewer="R1", reviewer_kind=ReviewerKind.human, decision="accept", timestamp="t")
    c3 = _contract(session, [inferred.model_copy(update={"reviews": [model_review, human]})])
    assert acceptance_gate(c3, session)[0]
    unresolved = inferred.model_copy(update={"status": RequirementStatus.unresolved, "reviews": [human]})
    assert not acceptance_gate(_contract(session, [unresolved]), session)[0]


def test_requirement_schema_rules(session):
    p = session.user_prompts()[0].event_id
    with pytest.raises(ValueError):
        Requirement(req_id="x", statement="s", kind="change", status="explicit", introduced_at=p, proposer="f")
    with pytest.raises(ValueError):
        Requirement(req_id="x", statement="s", kind="change", status="inferred", introduced_at=p, proposer="f")
    with pytest.raises(ValueError):
        Requirement(req_id="x", statement="s", kind="change", status="superseded", introduced_at=p, proposer="f",
                    rationale="r")
    with pytest.raises(ValueError):
        Requirement(req_id="x", statement="s", kind="change", status="inferred", introduced_at=p, proposer="f",
                    rationale="r", subjective=True, scored=True)


def test_correction_heuristic(session):
    flagged = propose_correction_events(session)
    assert len(flagged) == 1
    eid, cues = flagged[0]
    assert eid == session.user_prompts()[1].event_id
    assert "actually" in cues and "don't" in cues
