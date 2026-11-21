"""A synthetic world of two controlled task families for tests/test_independent_labeling.py and
tests/test_sensitivity_exclusions.py.

Each task (T1, T2) is laid out as the recorded tasks are: frozen verifiers for C1 (``initial_plain``) and C3
(``full_plain``) and D19's reference checks (``reference_check``) in ``task.json``, and an independent labeler
(``independent_label``, condition ``reference_check``) registered in the sidecar ``verifiers_extra.json`` (D55).
Its own candidates are the reference, a pre-correction state, a valid alternative, a near miss and an evaluation
no-op, each with a D19 proposal; its stratum ``fresh-v1`` holds fresh attempts with attempt records. A stub
replaces the Docker grader of ``tracecontract evaluate`` and returns the outcomes below, among them the labeler's
non-binary ones (timeout, unresolved, verifier error), under ``tc-harness/0.3.5``, so the reporting rules of a new
run apply. Synthetic data only; not research evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import tracecontract.cli as cli
import tracecontract.evaluate as evaluate_module
from tracecontract.analysis import PILOT_LABELER
from tracecontract.schemas import (
    AttemptAudit, AttemptRecord, Candidate, CandidateOrigin, ContractVariant, EvidenceSpan, Fidelity, Label, LabelerKind,
    Outcome, Population, Requirement, RequirementKind, RequirementStatus, Snapshot, SnapshotSource, Split, TaskContract,
    TaskManifest, VerificationResult, VerifierCondition, sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump
from tracecontract.strata import StratumManifest
from tracecontract.verifier import build_spec, freeze

T0 = "2026-11-22T10:00:00+00:00"
SHA = "ef" * 32
HARNESS = "tc-harness/0.3.5"
TASKS = ("T1", "T2")
STRATUM = "fresh-v1"
# Verifiers in task.json: the two evaluated conditions and D19's reference checks (label support).
IN_TASK = {"initial_plain": VerifierCondition.initial_plain, "full_plain": VerifierCondition.full_plain,
           "reference_check": VerifierCondition.reference_check}
# The task's own candidates: kind -> (origin, split, D19 proposal, violated requirements).
OWN = {"reference": (CandidateOrigin.reference, Split.dev, "valid", []),
       "pre": (CandidateOrigin.observed_pre_correction, Split.eval, "invalid", ["R-corr"]),
       "alt": (CandidateOrigin.valid_alternative, Split.eval, "valid", []),
       "nm": (CandidateOrigin.constructed_near_miss, Split.eval, "invalid", ["R-init"]),
       "noop-eval": (CandidateOrigin.noop, Split.eval, "invalid", [])}
# The fresh attempts of stratum fresh-v1: (task, kind) -> (D19 proposal, violated, configuration, variant,
# audit passed, patch body). The same body is the same graded patch.
FRESH = {("T1", "fa-1"): ("valid", [], "config-A", "u1", True, "T1-a"),
         ("T1", "fa-2"): ("invalid", ["R-corr"], "config-A", "u1", True, "T1-b"),
         ("T1", "fa-3"): ("valid", [], "config-B", "u1", True, "T1-c"),
         ("T1", "fa-4"): ("invalid", ["R-corr"], "config-B", "final", True, "T1-d"),
         ("T1", "fa-5"): ("valid", [], "config-A", "final", True, "T1-a"),  # the graded patch of T1-fa-1
         ("T2", "fa-1"): ("valid", [], "config-A", "u1", True, "T2-a"),
         ("T2", "fa-2"): ("invalid", ["R-corr"], "config-B", "u1", True, "T2-b"),
         ("T2", "fa-3"): ("invalid", ["R-corr"], "config-A", "final", False, "T2-c"),  # the audit found a forbidden read
         ("T2", "fa-4"): ("ambiguous", [], "config-B", "final", True, "T2-d")}
# The independent labeler's outcome on every candidate: (task, kind) -> outcome.
LABELER = {("T1", "reference"): "pass", ("T2", "reference"): "pass",
           ("T1", "noop-eval"): "task_failure", ("T2", "noop-eval"): "task_failure",
           ("T1", "pre"): "task_failure", ("T1", "alt"): "pass", ("T1", "nm"): "task_failure",
           ("T2", "pre"): "task_failure", ("T2", "alt"): "task_failure", ("T2", "nm"): "pass",
           ("T1", "fa-1"): "pass", ("T1", "fa-2"): "task_failure", ("T1", "fa-3"): "task_failure", ("T1", "fa-4"): "timeout",
           ("T1", "fa-5"): "pass", ("T2", "fa-1"): "unresolved", ("T2", "fa-2"): "task_failure", ("T2", "fa-3"): "pass",
           ("T2", "fa-4"): "verifier_error"}


def attempt_id(tid: str, kind: str) -> str:
    """The attempt id of a fresh attempt; it differs from the candidate id (``<task>-<kind>``) on purpose."""
    return f"fresh-v1-{tid}-{kind}"


def d19_label(tid: str, kind: str) -> str:
    return FRESH[(tid, kind)][0] if (tid, kind) in FRESH else OWN[kind][2]


def evaluated_outcome(verifier_id: str, kind: str) -> str:
    """Stub grading of the evaluated conditions: C1 rejects only the near miss, C3 accepts only what D19 labels valid."""
    if kind == "reference":
        return "pass"
    if kind == "noop-eval":
        return "task_failure"
    if verifier_id == "initial_plain":
        return "task_failure" if kind == "nm" else "pass"
    return "pass" if kind in ("alt", "fa-1", "fa-3", "fa-5") else "task_failure"


def _patch(body: str) -> str:
    return "" if not body else f"--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = '{body}'\n"


def _label(value: str, violated: list[str]) -> Label:
    return Label(value=value, violated_requirements=violated, labeler=PILOT_LABELER, labeler_kind=LabelerKind.model, timestamp=T0)


def _req(rid: str, kind: RequirementKind, event_id: str) -> Requirement:
    return Requirement(req_id=rid, statement=f"Statement of {rid}.", kind=kind, status=RequirementStatus.explicit,
                       introduced_at=event_id, evidence=[EvidenceSpan(event_id=event_id, start=0, end=1, quote="x")],
                       observable=f"check {rid}", proposer="fixture")


def _verifier(td: Path, vid: str, condition: VerifierCondition) -> str:
    tests = td / "verifiers" / vid / "tests"
    tests.mkdir(parents=True)
    (tests / "test_fixture.py").write_text("def test_value():\n    assert 1 + 1 == 2\n")
    dump(freeze(build_spec(verifier_id=vid, task_id=td.name, condition=condition, test_dir=tests, task_dir=td), td),
         td / "verifiers" / vid / "spec.json")
    return f"verifiers/{vid}/spec.json"


def make_task(root: Path, tid: str, *, sidecar: dict[str, VerifierCondition] | None = None) -> Path:
    """Task ``tid`` under ``root/tasks`` with its base snapshot under ``root/snapshots``.

    ``sidecar`` (``{verifier id: condition}``) is what ``verifiers_extra.json`` registers; by default the independent
    labeler under ``reference_check``, as the recorded tasks register it.
    """
    td = root / "tasks" / tid
    first, later = f"{tid}-s/L000001.00", f"{tid}-s/L000005.00"
    dump(TaskContract(contract_id=f"{tid}-reference", task_id=tid, session_id=f"{tid}-s", variant=ContractVariant.reference,
                      created_by="fixture", created_at=T0,
                      requirements=[_req("R-init", RequirementKind.change, first), _req("R-corr", RequirementKind.invariant, later)]),
         td / "contracts" / "reference.json")
    for kind, (origin, split, value, violated) in OWN.items():
        patch = _patch("" if origin == CandidateOrigin.noop else f"{tid}-{kind}")
        dump(Candidate(candidate_id=f"{tid}-{kind}", task_id=tid, origin=origin, split=split, patch=patch,
                       patch_sha256=sha256_text(patch), produced_by="fixture", labels=[_label(value, violated)]),
             td / "candidates" / f"{tid}-{kind}.json")
    base = root / "snapshots" / tid
    base.mkdir(parents=True)
    (base / "mod.py").write_text("X = 1\n")
    dump(Snapshot(snapshot_id=f"{tid}-base", task_id=tid, repo_url="https://example.invalid/fixture", base_commit="0" * 40,
                  fidelity=Fidelity.exact, file_manifest_sha256=manifest_sha256(manifest(base)), n_files=1), td / "snapshot.json")
    specs = [_verifier(td, vid, cond) for vid, cond in IN_TASK.items()]
    extra = [_verifier(td, vid, cond) for vid, cond in
             (sidecar if sidecar is not None else {"independent_label": VerifierCondition.reference_check}).items()]
    (td / "verifiers_extra.json").write_text(json.dumps({"verifiers": extra}, indent=2) + "\n")
    dump(TaskManifest(task_id=tid, family_id=tid, population=Population.controlled, status="pending_review",
                      provenance="provenance.json", snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture", commit="0" * 40),
                      snapshot="snapshot.json", env_requirements=[], contracts={"reference": "contracts/reference.json"},
                      verifiers=specs, candidates=[f"candidates/{tid}-{kind}.json" for kind in OWN]), td / "task.json")
    rels = []
    for (t, kind), (value, violated, config, variant, passed, body) in FRESH.items():
        if t != tid:
            continue
        patch = _patch(body)
        audit = AttemptAudit(profile="fresh-attempt:v1", passed=passed, audited_at=T0,
                             findings=[] if passed else ["read a file outside the workspace"])
        rec = AttemptRecord(attempt_id=attempt_id(tid, kind), configuration=config, variant=variant, instruction_sha256=SHA,
                            started_at=T0, ended_at=T0, turns=5, tool_calls=9, ended="finished", patch_sha256=sha256_text(patch),
                            run_record="private-runs/fresh-v1/x.json", audit=audit)
        rel = f"strata/{STRATUM}/candidates/{tid}-{kind}.json"
        dump(Candidate(candidate_id=f"{tid}-{kind}", task_id=tid, origin=CandidateOrigin.fresh_attempt, split=Split.eval, patch=patch,
                       patch_sha256=sha256_text(patch), produced_by=f"fresh-attempt:{config}", labels=[_label(value, violated)],
                       attempt=rec), td / rel)
        rels.append(rel)
    dump(StratumManifest(stratum=STRATUM, task_id=tid, description="fixture fresh attempts", candidates=rels),
         td / "strata" / f"{STRATUM}.json")
    return td


def install(root: Path, monkeypatch) -> list[tuple[str, str, str]]:
    """Point the CLI at ``root`` and replace the Docker grader by the stub; returns the (task, verifier, candidate) graded."""
    calls: list[tuple[str, str, str]] = []

    def stub(*, spec, task_dir, candidate, run_id, **_) -> VerificationResult:
        tid = spec.task_id
        kind = candidate.candidate_id[len(tid) + 1:]
        calls.append((tid, spec.verifier_id, candidate.candidate_id))
        if spec.verifier_id.startswith("independent_label"):
            oc = LABELER[(tid, kind)]
        elif spec.condition == VerifierCondition.reference_check:  # D19's reference checks, graded in the run
            oc = "pass" if d19_label(tid, kind) == "valid" else "task_failure"
        else:
            oc = evaluated_outcome(spec.verifier_id, kind)
        return VerificationResult(run_id=run_id, task_id=tid, verifier_id=spec.verifier_id, candidate_id=candidate.candidate_id,
                                  outcome=Outcome(oc), reward=1.0 if oc == "pass" else 0.0, started_at=T0, finished_at=T0,
                                  wall_s=0.0, harness_version=HARNESS)

    monkeypatch.setattr(evaluate_module, "verify_candidate", stub)
    monkeypatch.setattr(evaluate_module, "build_env_image", lambda reqs, cache: ("tc-fixture:0", "sha256:" + "0" * 64))
    monkeypatch.setattr(cli, "REPO", root)
    monkeypatch.setattr(cli, "SNAPSHOTS", root / "snapshots")
    monkeypatch.setattr(cli, "CACHE", root / "cache")
    return calls


def exit_code(argv: list[str]) -> int | str | None:
    """The CLI's exit code: 0 when it returns, else the SystemExit code (a message string exits with status 1)."""
    try:
        cli.main(argv)
    except SystemExit as exc:
        return exc.code
    return 0


def run_evaluation(root: Path, run_id: str = "r", *, extra_verifiers: bool = True, tasks: tuple[str, ...] = TASKS) -> Path:
    """``tracecontract evaluate`` of the tasks with stratum fresh-v1 (and, by default, the sidecar verifiers), as a pilot."""
    argv = ["evaluate", *(str(root / "tasks" / t) for t in tasks), "--run-id", run_id, "--pilot", "--strata", STRATUM]
    code = exit_code(argv + (["--with-extra-verifiers"] if extra_verifiers else []))
    assert code == 0, code
    return root / "results" / "runs" / run_id
