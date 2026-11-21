"""The human-review acceptance gate and its enforcement (accept-task, evaluate).

* each human reviewer's latest decision counts; reviewers who disagree leave a
  requirement unaccepted until an adjudicated review is added;
* ``edit`` and ``needs_discussion`` are not acceptance until the requirement is re-reviewed;
* a scored requirement without an observable check, and an explicit requirement quoting a
  non-user event, are gate errors;
* ``accept-task`` sets ``accepted`` only when the task gate passes; ``evaluate`` refuses
  rejected tasks and needs ``--pilot`` for tasks that have not passed the gate.

Synthetic fixtures only (population = fixture), except one read-only check on copies of
the pilot tasks' records; they test code behaviour and are not research evidence.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import tracecontract.cli as cli
import tracecontract.evaluate as evaluate
from tracecontract.contract import acceptance_gate, align_quote, human_decision, task_gate, validate_contract
from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.schemas import (
    Candidate, CandidateOrigin, ContractVariant, Eligibility, Fidelity, Population, ProvenanceRecord, RedactionStatus,
    Requirement, RequirementKind, RequirementStatus, Review, ReviewerKind, Session, Snapshot, SnapshotSource, Split,
    TaskContract, TaskManifest, sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, load

FIX = Path(__file__).parent / "fixtures" / "claude_code_session.jsonl"
REPO = Path(__file__).resolve().parents[1]
TASK = "FX-GATE"


@pytest.fixture()
def session() -> Session:
    return parse_claude_code_jsonl(FIX, population=Population.fixture, source="fixture")


def _rv(reviewer: str, decision: str, *, kind: ReviewerKind = ReviewerKind.human, adjudicated: bool = False) -> Review:
    return Review(reviewer=reviewer, reviewer_kind=kind, decision=decision, timestamp="2026-11-21T00:00:00+00:00",
                  adjudicated=adjudicated)


def _explicit(session: Session, req_id: str, turn: int, quote: str, *, event_id: str | None = None,
              kind: RequirementKind = RequirementKind.change, **kw) -> Requirement:
    """An explicit requirement introduced by user turn ``turn``, quoting ``event_id`` (default: that turn)."""
    intro = session.user_prompts()[turn].event_id
    span = align_quote(session, event_id or intro, quote).span
    assert span is not None
    kw.setdefault("observable", f"check {req_id}")
    return Requirement(req_id=req_id, statement=f"Statement of {req_id}.", kind=kind, status=RequirementStatus.explicit,
                       introduced_at=intro, evidence=[span], proposer="fixture", **kw)


def _contract(session: Session, reqs: list[Requirement], variant: ContractVariant = ContractVariant.reference) -> TaskContract:
    return TaskContract(contract_id=f"{TASK}-{variant.value}", task_id=TASK, session_id=session.session_id, variant=variant,
                        requirements=reqs, created_by="fixture", created_at="2026-11-21T00:00:00+00:00")


def _gate(session: Session, reviews: list[Review], variant: ContractVariant = ContractVariant.reference):
    r = _explicit(session, "R1", 0, "add a `--verbose` flag", reviews=reviews)
    return acceptance_gate(_contract(session, [r], variant), session)


# ---------------------------------------------------------------------------
# Human reviews of a requirement
# ---------------------------------------------------------------------------


def test_reject_then_accept_by_two_reviewers_is_not_accepted(session):
    reviews = [_rv("human:R1", "reject"), _rv("human:R2", "accept")]  # the last review alone would read as acceptance
    ok, reasons = _gate(session, reviews)
    assert not ok and human_decision(_explicit(session, "R1", 0, "add a `--verbose` flag", reviews=reviews)) is None
    assert reasons == ["review_disagreement: reference requirement R1 (human reviewers disagree "
                       "(human:R1: reject, human:R2: accept); needs an adjudicated review)"]


def test_each_reviewers_latest_decision_counts(session):
    assert _gate(session, [_rv("human:R1", "reject"), _rv("human:R2", "accept"), _rv("human:R1", "accept")])[0]
    ok, reasons = _gate(session, [_rv("human:R1", "accept"), _rv("human:R2", "accept"), _rv("human:R2", "reject")])
    assert not ok and reasons[0].startswith("review_disagreement:")
    ok, reasons = _gate(session, [_rv("human:R1", "reject"), _rv("human:R2", "reject")])
    assert not ok and reasons[0].startswith("rejected_in_review:")
    # Model and rule reviews are proposals: they never accept, and never make a disagreement.
    assert not _gate(session, [_rv("builder", "accept", kind=ReviewerKind.model)])[0]
    assert _gate(session, [_rv("builder", "reject", kind=ReviewerKind.rule), _rv("human:R1", "accept")])[0]


def test_adjudicated_accept_is_accepted(session):
    split = [_rv("human:R1", "reject"), _rv("human:R2", "accept")]
    assert _gate(session, split + [_rv("human:R3", "accept", adjudicated=True)])[0]
    ok, reasons = _gate(session, split + [_rv("human:R3", "reject", adjudicated=True)])
    assert not ok and reasons[0].startswith("rejected_in_review:")
    # Reviews added after an adjudication decide again (the contract may have changed since).
    ok, reasons = _gate(session, split + [_rv("human:R3", "accept", adjudicated=True), _rv("human:R1", "reject")])
    assert not ok and reasons[0].startswith("rejected_in_review:")
    edit = split + [_rv("human:R3", "edit", adjudicated=True)]
    assert not _gate(session, edit)[0]
    assert _gate(session, edit + [_rv("human:R1", "accept"), _rv("human:R2", "accept")])[0]
    # Only a human review can adjudicate.
    assert not _gate(session, split + [_rv("builder", "accept", kind=ReviewerKind.model, adjudicated=True)])[0]


@pytest.mark.parametrize("decision", ["edit", "needs_discussion"])
def test_edit_or_discussion_is_not_accepted_until_re_reviewed(session, decision):
    ok, reasons = _gate(session, [_rv("human:R1", decision), _rv("human:R2", decision)])
    assert not ok and reasons == [f"needs_re_review: reference requirement R1 (the human decision is {decision!r}; "
                                  "the requirement must be re-reviewed)"]
    assert not _gate(session, [_rv("human:R1", "accept"), _rv("human:R2", decision)])[0]
    rereviewed = [_rv("human:R1", decision), _rv("human:R2", decision), _rv("human:R1", "accept"), _rv("human:R2", "accept")]
    assert _gate(session, rereviewed)[0]


def test_human_reviews_count_on_requirements_that_need_none(session):
    # An explicit full-session requirement needs no review, but a human rejection still blocks it.
    assert _gate(session, [], ContractVariant.full_session)[0]
    ok, reasons = _gate(session, [_rv("human:R1", "reject")], ContractVariant.full_session)
    assert not ok and reasons == ["rejected_in_review: requirement R1 (the human decision is 'reject')"]


def test_adjudicated_field_is_backward_compatible():
    # Records written before the field existed load and re-serialize byte for byte.
    for p in sorted(REPO.glob("tasks/CS-0*/contracts/reference.json")):
        raw = p.read_text(encoding="utf-8")
        c = TaskContract.model_validate_json(raw)
        assert c.model_dump_json(indent=2) + "\n" == raw
        assert all(not rv.adjudicated for r in c.requirements for rv in r.reviews)
    adj = _rv("human:R3", "accept", adjudicated=True)
    assert json.loads(adj.model_dump_json())["adjudicated"] is True
    assert Review.model_validate_json(adj.model_dump_json()) == adj
    assert "adjudicated" not in _rv("human:R1", "accept").model_dump_json()


# ---------------------------------------------------------------------------
# Gate errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("observable", ["", "   "])
def test_no_observable_is_a_gate_error(session, observable):
    accepted = [_rv("human:R1", "accept")]
    r = _explicit(session, "R1", 0, "add a `--verbose` flag", observable=observable, reviews=accepted)
    c = _contract(session, [r])
    assert [(i.severity, i.code) for i in validate_contract(c, session)] == [("warning", "no_observable")]
    ok, reasons = acceptance_gate(c, session)
    assert not ok and reasons == ["no_observable: R1: scored requirement lacks an observable check"]
    unscored = r.model_copy(update={"scored": False})
    assert acceptance_gate(_contract(session, [unscored]), session)[0]


def test_non_user_evidence_is_a_gate_error(session):
    assistant = next(e for e in session.events if e.kind.value == "assistant_text")
    # Introduced by the second user turn but quoting the assistant's earlier text.
    r = _explicit(session, "R1", 1, "look at the CLI", event_id=assistant.event_id, reviews=[_rv("human:R1", "accept")])
    c = _contract(session, [r])
    assert [(i.severity, i.code) for i in validate_contract(c, session)] == [("warning", "non_user_evidence")]
    ok, reasons = acceptance_gate(c, session)
    assert not ok and reasons == [f"non_user_evidence: R1: explicit requirement quotes {assistant.event_id} "
                                  "(assistant_text), not a user turn"]


# ---------------------------------------------------------------------------
# The task gate: accept-task and evaluate
# ---------------------------------------------------------------------------


def _make_task(root: Path, session: Session, *, status: str = "pending_review", eligibility: str = "eligible",
               reviews: list[Review] | None = None) -> Path:
    """A fixture task laid out like the repository under ``root``: tasks/, snapshots/ and its transcript in data/."""
    transcript = root / "data" / "fixtures" / "transcripts" / f"{TASK}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIX, transcript)
    base = root / "snapshots" / TASK
    base.mkdir(parents=True, exist_ok=True)
    (base / "cli.py").write_text("def main(argv):\n    return 0\n")
    td = root / "tasks" / TASK
    reviews = [_rv("human:R1", "accept"), _rv("human:R2", "accept")] if reviews is None else reviews
    reqs = [_explicit(session, "R1", 0, "add a `--verbose` flag", reviews=reviews),
            _explicit(session, "R2", 1, "don't change the default output", kind=RequirementKind.invariant, reviews=reviews)]
    dump(_contract(session, reqs), td / "contracts" / "reference.json")
    noop = Candidate(candidate_id=f"{TASK}-noop-eval", task_id=TASK, origin=CandidateOrigin.noop, split=Split.eval, patch="",
                     patch_sha256=sha256_text(""), produced_by="base snapshot")
    dump(noop, td / "candidates" / f"{noop.candidate_id}.json")
    dump(Snapshot(snapshot_id=f"{TASK}-base", task_id=TASK, repo_url="https://example.invalid/fixture", base_commit="0" * 40,
                  fidelity=Fidelity.exact, file_manifest_sha256=manifest_sha256(manifest(base)), n_files=1),
         td / "snapshot.json")
    dump(ProvenanceRecord(record_id=f"prov-{TASK}", session_id=session.session_id, population=Population.fixture,
                          source_url="synthetic fixture", source_id=TASK, permission_basis="synthetic fixture",
                          capture_method="hand-written fixture", redaction_status=RedactionStatus.redacted_by_us,
                          task_family_id=TASK, eligibility=Eligibility(eligibility), accessed="2026-11-21T00:00:00+00:00"),
         td / "provenance.json")
    dump(TaskManifest(task_id=TASK, family_id=TASK, population=Population.fixture, status=status, provenance="provenance.json",
                      snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture", commit="0" * 40),
                      snapshot="snapshot.json", env_requirements=[], contracts={"reference": "contracts/reference.json"},
                      candidates=[f"candidates/{noop.candidate_id}.json"]),
         td / "task.json")
    return td


@pytest.fixture()
def repo(tmp_path, monkeypatch) -> Path:
    """A scratch repository root for the CLI; no Docker image is built (the fixture task has no verifiers)."""
    monkeypatch.setattr(cli, "REPO", tmp_path)
    monkeypatch.setattr(cli, "SNAPSHOTS", tmp_path / "snapshots")
    monkeypatch.setattr(cli, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(evaluate, "build_env_image", lambda reqs, cache: ("tc-fixture:0", "sha256:" + "0" * 64))
    return tmp_path


def _exit_code(argv: list[str]) -> int | str | None:
    """The CLI's exit code: 0 when it returns, else the SystemExit code (a message string exits with status 1)."""
    try:
        cli.main(argv)
    except SystemExit as exc:
        return exc.code
    return 0


def _status(td: Path) -> str:
    return load(td / "task.json", TaskManifest).status


def test_accept_task_accepts_only_when_the_gate_passes(repo, session, capsys):
    td = _make_task(repo, session)
    assert _exit_code(["accept-task", str(td), "--dry-run"]) == 0 and _status(td) == "pending_review"
    capsys.readouterr()
    assert _exit_code(["accept-task", str(td)]) == 0 and _status(td) == "accepted"
    out = json.loads(capsys.readouterr().out)
    assert out["accepted"] and out["previous_status"] == "pending_review" and out["reasons"] == []
    assert task_gate(td, repo).accepted


@pytest.mark.parametrize("change, reason", [
    ({"reviews": [_rv("human:R1", "reject"), _rv("human:R2", "accept")]}, "review_disagreement"),
    ({"reviews": [_rv("human:R1", "edit"), _rv("human:R2", "edit")]}, "needs_re_review"),
    ({"reviews": []}, "needs_human_review"),
    ({"eligibility": "pending_review"}, "provenance: eligibility is 'pending_review'"),
    ({"status": "rejected"}, "status: the task is rejected"),
    ({"eligibility": "rejected"}, "provenance: the source is rejected"),
])
def test_accept_task_refuses_when_the_gate_fails(repo, session, capsys, change, reason):
    td = _make_task(repo, session, **change)
    before = (td / "task.json").read_bytes()
    assert _exit_code(["accept-task", str(td)]) == 1
    assert (td / "task.json").read_bytes() == before
    out = json.loads(capsys.readouterr().out)
    assert not out["passed"] and any(r.startswith(reason) or reason in r for r in out["reasons"])


@pytest.mark.parametrize("task", ["CS-01", "CS-02", "CS-03", "CS-04"])
def test_accept_task_refuses_the_pilot_tasks(tmp_path, capsys, task):
    """No human review exists for the pilot tasks; checked on copies of their records, never on the originals."""
    src, td = REPO / "tasks" / task, tmp_path / "tasks" / task
    td.mkdir(parents=True)
    for name in ("task.json", "provenance.json"):
        shutil.copyfile(src / name, td / name)
    shutil.copytree(src / "contracts", td / "contracts")
    before = (td / "task.json").read_bytes()
    assert _exit_code(["accept-task", str(td)]) == 1  # the transcripts are read from the repository
    assert (td / "task.json").read_bytes() == before
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "pending_review" and not out["refused"]
    assert any(r.startswith("contract reference: needs_human_review:") for r in out["reasons"])


def test_evaluate_refuses_a_rejected_task(repo, session):
    td = _make_task(repo, session, status="rejected")
    for extra in ([], ["--pilot"]):
        code = _exit_code(["evaluate", str(td), "--run-id", "r-rejected", *extra])
        assert code not in (0, None) and "refused (status: the task is rejected)" in str(code)
    assert not (repo / "results" / "runs" / "r-rejected").exists()  # refused before anything was written
    td = _make_task(repo / "other", session, eligibility="rejected")
    with pytest.raises(evaluate.TaskRefused, match="the source is rejected"):
        evaluate.run_matrix([td], run_id="r", out_root=repo / "runs", cache_dir=repo / "cache",
                            snapshot_root=repo / "other" / "snapshots", repo_root=repo / "other", pilot=True)
    assert not (repo / "runs").exists()


def test_evaluate_without_pilot_refuses_a_pending_review_task(repo, session):
    td = _make_task(repo, session)  # would pass the gate, but nobody has accepted it
    code = _exit_code(["evaluate", str(td), "--run-id", "r-pending"])
    assert code not in (0, None) and "pass --pilot" in str(code)
    assert not (repo / "results" / "runs" / "r-pending").exists()
    with pytest.raises(evaluate.TaskRefused):  # the API default is not a pilot either
        evaluate.run_matrix([td], run_id="r-pending", out_root=repo / "results" / "runs", cache_dir=repo / "cache",
                            snapshot_root=repo / "snapshots", repo_root=repo)
    assert _exit_code(["evaluate", str(td), "--run-id", "r-pilot", "--pilot"]) == 0
    m = json.loads((repo / "results" / "runs" / "r-pilot" / "manifest.json").read_text())
    assert m["pilot"] is True and m["invocations"][-1]["pilot"] is True
    gate = m["tasks"][0]["acceptance_gate"]
    assert gate["status"] == "pending_review" and gate["passed"] and not gate["accepted"]


def test_evaluate_accepted_task_without_pilot_and_rechecks_the_gate(repo, session):
    td = _make_task(repo, session)
    assert _exit_code(["accept-task", str(td)]) == 0
    assert _exit_code(["evaluate", str(td), "--run-id", "r-accepted"]) == 0
    m = json.loads((repo / "results" / "runs" / "r-accepted" / "manifest.json").read_text())
    assert m["pilot"] is False and m["tasks"][0]["acceptance_gate"]["accepted"] is True
    # A review added after acceptance takes the task out of the gate, although its status still says accepted.
    ref = load(td / "contracts" / "reference.json", TaskContract)
    ref.requirements[0].reviews.append(_rv("human:R2", "reject"))
    dump(ref, td / "contracts" / "reference.json")
    assert _status(td) == "accepted"
    code = _exit_code(["evaluate", str(td), "--run-id", "r-stale"])
    assert code not in (0, None) and "review_disagreement" in str(code)
    assert not (repo / "results" / "runs" / "r-stale").exists()


def test_resumed_run_recorded_before_the_gate_counts_as_pilot(repo, session):
    td = _make_task(repo, session, status="accepted")
    run = repo / "results" / "runs" / "r-old"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"run_id": "r-old", "started_at": "2026-11-18T00:00:00+00:00", "tasks": [],
                                                   "invocations": [{"at": "2026-11-18T00:00:00+00:00", "tasks": [TASK]}]}))
    assert _exit_code(["evaluate", str(td), "--run-id", "r-old"]) == 0
    m = json.loads((run / "manifest.json").read_text())
    assert m["invocations"][-1]["pilot"] is False and m["pilot"] is True
