"""Predefined verifier-audit procedure (``audit:v1``).

The audit uses ONLY development-split candidates. Held-out evaluation candidates
and their labels never enter this module. Checks:

1. static lint of process-separated tests (``verifier.lint_process_separated``);
2. the reference solution passes on every one of ``reference_repeats`` runs
   (flakiness check);
3. the no-op candidate (base snapshot) does not pass;
4. every development attack does not pass, and fails at least one check mapped
   to a requirement it targets (requirement-level sensitivity);
5. every development valid alternative passes (false-rejection check);
6. every scored requirement of the contract is mapped to at least one check.

The audit returns machine-readable findings. Revising tests in response to the
findings is done by the generator (recorded separately); the procedure itself
never edits tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .schemas import AuditRecord, Candidate, CandidateOrigin, Isolation, Outcome, Split, TaskContract, VerifierSpec
from .verifier import lint_process_separated

PROCEDURE = "audit:v1"


@dataclass
class AuditFinding:
    code: str
    message: str
    candidate_id: str | None = None
    requirement_id: str | None = None


@dataclass
class AuditReport:
    passed: bool
    findings: list[AuditFinding] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)

    def to_record(self, iterations: int, dev_ids: list[str]) -> AuditRecord:
        return AuditRecord(procedure=PROCEDURE, iterations=iterations, passed=self.passed,
                           findings=[f"{f.code}: {f.message}" for f in self.findings], dev_candidate_ids=dev_ids)


def run_audit(spec: VerifierSpec, contract: TaskContract | None, dev_candidates: list[Candidate], grade,
              *, task_dir: Path, reference_repeats: int = 3) -> AuditReport:
    """``grade(spec, candidate, repeats) -> VerificationResult`` is injected (Docker or fake)."""
    findings: list[AuditFinding] = []
    runs: list[dict] = []
    for c in dev_candidates:
        if c.split != Split.dev:
            raise ValueError(f"audit received non-dev candidate {c.candidate_id}; evaluation data must stay held out")
    if spec.isolation == Isolation.process_separated:
        for i in lint_process_separated(task_dir / spec.test_dir):
            findings.append(AuditFinding("lint_" + i.code, f"{i.file}:{i.line} {i.message}"))
    check_reqs = {c.check_id: set(c.requirement_ids) for c in spec.checks}
    if contract is not None:
        mapped = set().union(*check_reqs.values()) if check_reqs else set()
        for r in contract.active():
            if r.scored and r.req_id not in mapped:
                findings.append(AuditFinding("uncovered_requirement", f"no check is mapped to {r.req_id}", requirement_id=r.req_id))
    for c in dev_candidates:
        repeats = reference_repeats if c.origin == CandidateOrigin.reference else 1
        res = grade(spec, c, repeats)
        runs.append({"candidate_id": c.candidate_id, "origin": c.origin.value, "outcome": res.outcome.value,
                     "failed_checks": [k.check_id for k in res.checks if k.status != "passed"]})
        expect_pass = c.origin in (CandidateOrigin.reference, CandidateOrigin.valid_alternative)
        if expect_pass and res.outcome != Outcome.passed:
            code = "reference_not_passing" if c.origin == CandidateOrigin.reference else "false_rejection_dev"
            findings.append(AuditFinding(code, f"{c.candidate_id}: {res.outcome.value}; failed={runs[-1]['failed_checks'][:5]}", c.candidate_id))
        if not expect_pass and res.outcome == Outcome.passed:
            findings.append(AuditFinding("false_acceptance_dev", f"{c.candidate_id} ({c.origin.value}) passed", c.candidate_id))
        if c.origin == CandidateOrigin.dev_attack and res.outcome != Outcome.passed:
            targeted = set(c.labels[-1].violated_requirements) if c.labels else set()
            failed = [k.check_id for k in res.checks if k.status != "passed"]
            hit = any(check_reqs.get(f, set()) & targeted for f in failed)
            if targeted and not hit:
                findings.append(AuditFinding("attack_caught_by_unrelated_check",
                                             f"{c.candidate_id} targeted {sorted(targeted)} but only failed {failed[:5]}", c.candidate_id))
        if res.outcome in (Outcome.verifier_error, Outcome.environment_failure, Outcome.timeout, Outcome.unresolved):
            findings.append(AuditFinding("infrastructure", f"{c.candidate_id}: {res.outcome.value}: {res.diagnostics[:3]}", c.candidate_id))
    blocking = {"reference_not_passing", "false_rejection_dev", "false_acceptance_dev", "uncovered_requirement", "infrastructure"}
    passed = not any(f.code in blocking or f.code.startswith("lint_") for f in findings)
    return AuditReport(passed, findings, runs)
