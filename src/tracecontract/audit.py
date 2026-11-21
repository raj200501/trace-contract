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

Records (decision log D62). Each audit run is one iteration of an audit loop. ``tracecontract audit`` prints its
iteration record (:func:`iteration_output`): its findings, its runs (every check that each candidate failed, in each
run of a candidate graded more than once), when it was graded, what it was graded with (the contract, the audit set,
the candidates) and the tests it graded (:func:`suite_snapshot`: the check list with a hash of each check function's
source and of the code it depends on, the module-level definitions and the files). That printed iteration record is
the only copy of an earlier iteration's tests, since a revision replaces the tests in place and ``build-verifier``
rebuilds the spec. ``tracecontract audit --record N --previous <the N + 1 iteration records of the loop>`` grades the
tests after revision N again and stores an :class:`~tracecontract.schemas.AuditRecord` that keeps every iteration with
every failing check (``history``), what each revision added, removed and changed (``revisions``,
:func:`revision_changes`), and human-readable findings that say what each revision changed, also when no finding
remains. The loop's records are checked against each other and against this run before anything is graded
(:func:`read_loop`). The runs of the reference are graded one at a time and combined as the grader combines the runs
of one grade with repeats (:func:`combine_runs`), since that grade returns the checks of its last run only. None of
this changes the procedure: the checks, the findings and their messages, and the pass rule are those above.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .schemas import (
    AuditCheck, AuditCodeChange, AuditFindingEntry, AuditIteration, AuditRecord, AuditRequirementChange, AuditRevision,
    AuditRun, Candidate, CandidateOrigin, Isolation, Outcome, Split, TaskContract, VerificationResult, VerifierSpec,
)
from .verifier import checks_sha256, hash_test_dir, lint_process_separated

PROCEDURE = "audit:v1"
REFERENCE_REPEATS = 3  # check 2: the runs of the reference
# A finding's message names at most this many failing checks; the runs, and a record's history, keep every one.
NAMED_IN_MESSAGE = 5
_NAMES_FAILED_CHECKS = ("reference_not_passing", "false_rejection_dev", "attack_caught_by_unrelated_check")
# The verifier that iteration 0 of an audited verifier grades a copy of (protocol §4: C2 starts from C1's tests and C4
# from C3's; decision log D24), by condition.
STARTS_FROM = {"initial_audited": "initial_plain", "full_audited": "full_plain"}


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

    def to_record(self, iterations: int, dev_ids: list[str], *, tests: SuiteSnapshot, loop: Sequence[IterationRecord],
                  graded_at: str | None = None) -> AuditRecord:
        """The audit's record as iteration ``iterations`` of its loop, the one after that many revisions.

        ``loop`` holds the loop's iteration records 0 to ``iterations`` (:func:`read_loop`): one before each revision,
        then the loop's own grade of the tests (``tests``, :func:`suite_snapshot`) that this run, graded at
        ``graded_at``, grades again. The record keeps every iteration (``history``: the loop's records before the last,
        then this run) and what each revision changed (``revisions``). Its ``findings`` are this run's
        (:func:`finding_lines`), then a line when this run's grade differs from the loop's grade of the same tests
        (:func:`regrade_line`), then one line per revision (:func:`revision_line`). Raises :class:`AuditRecordError`
        when ``loop`` does not hold one record per iteration."""
        if iterations < 0:
            raise AuditRecordError(f"the number of revisions cannot be negative ({iterations})")
        if len(loop) != iterations + 1:
            raise AuditRecordError(
                f"a record after {iterations} revision(s) needs the {iterations + 1} iteration records of its loop, "
                f"iteration 0 first; {len(loop)} given")
        findings = [AuditFindingEntry(**vars(f)) for f in self.findings]
        runs = [AuditRun.model_validate(r) for r in self.runs]
        rows = [(e.passed, e.graded_at, e.findings, e.runs, e.tests) for e in loop[:-1]]
        rows.append((self.passed, graded_at, findings, runs, tests))
        history = [_iteration(i, *row) for i, row in enumerate(rows)]
        revisions = [revision_changes(rows[i - 1][-1], rows[i][-1], i) for i in range(1, iterations + 1)]
        lines = finding_lines(findings, runs)
        regraded = regrade_line(loop[-1], self.passed, runs, iterations)
        lines += [regraded] if regraded else []
        lines += [revision_line(r, iterations, no_finding=not findings) for r in revisions]
        return AuditRecord(procedure=PROCEDURE, iterations=iterations, passed=self.passed, findings=lines,
                           dev_candidate_ids=dev_ids, history=history, revisions=revisions)


def _failed(res: VerificationResult) -> list[str]:
    return [k.check_id for k in res.checks if k.status != "passed"]


_RUN_0 = "[run 0] "


def combine_runs(results: Sequence[VerificationResult]) -> VerificationResult:
    """The runs of one candidate, each graded alone (repeats 1), combined as the grader combines the runs of one grade
    with repeats (``docker_runner.verify_candidate``): their outcome when they agree, else unresolved with the reason
    in the diagnostics; the checks of the last run; the patch's diagnostics once, then each run's, numbered by run."""
    if not results:
        raise ValueError("no run to combine")
    first, last = results[0], results[-1]
    outcomes = [r.outcome for r in results]
    diags = [d for d in first.diagnostics if not d.startswith(_RUN_0)]  # the patch's, which every run repeats
    for i, r in enumerate(results):
        diags += [f"[run {i}] {d[len(_RUN_0):]}" for d in r.diagnostics if d.startswith(_RUN_0)]
    outcome = outcomes[0]
    if len(set(outcomes)) > 1:
        outcome = Outcome.unresolved
        diags.append(f"repeated runs disagree: {[o.value for o in outcomes]}")
    return last.model_copy(update={"outcome": outcome, "reward": 1.0 if outcome == Outcome.passed else 0.0,
                                   "diagnostics": diags, "started_at": first.started_at,
                                   "wall_s": sum(r.wall_s for r in results), "log_sha256": None})


def run_audit(spec: VerifierSpec, contract: TaskContract | None, dev_candidates: list[Candidate], grade,
              *, task_dir: Path, reference_repeats: int = REFERENCE_REPEATS) -> AuditReport:
    """``grade(spec, candidate, repeats) -> VerificationResult`` is injected (Docker or fake).

    The reference is graded ``reference_repeats`` times, one run at a time, and its runs are combined as the grader
    combines repeated runs (:func:`combine_runs`), so that its outcome and the findings are those of one grade with
    that many repeats; its entry in the runs also keeps each run's outcome and failing checks (``repeats``), since a
    grade with repeats returns the checks of its last run only."""
    findings: list[AuditFinding] = []
    runs: list[dict] = []
    if reference_repeats < 1:
        raise ValueError(f"the reference is graded at least once, not {reference_repeats} times")
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
        each = [grade(spec, c, 1) for _ in range(repeats)]
        res = each[0] if repeats == 1 else combine_runs(each)
        run = {"candidate_id": c.candidate_id, "origin": c.origin.value, "outcome": res.outcome.value,
               "failed_checks": _failed(res)}
        if repeats > 1:
            run["repeats"] = [{"outcome": r.outcome.value, "failed_checks": _failed(r)} for r in each]
        runs.append(run)
        expect_pass = c.origin in (CandidateOrigin.reference, CandidateOrigin.valid_alternative)
        if expect_pass and res.outcome != Outcome.passed:
            code = "reference_not_passing" if c.origin == CandidateOrigin.reference else "false_rejection_dev"
            findings.append(AuditFinding(
                code, f"{c.candidate_id}: {res.outcome.value}; failed={runs[-1]['failed_checks'][:NAMED_IN_MESSAGE]}", c.candidate_id))
        if not expect_pass and res.outcome == Outcome.passed:
            findings.append(AuditFinding("false_acceptance_dev", f"{c.candidate_id} ({c.origin.value}) passed", c.candidate_id))
        if c.origin == CandidateOrigin.dev_attack and res.outcome != Outcome.passed:
            targeted = set(c.labels[-1].violated_requirements) if c.labels else set()
            failed = [k.check_id for k in res.checks if k.status != "passed"]
            hit = any(check_reqs.get(f, set()) & targeted for f in failed)
            if targeted and not hit:
                findings.append(AuditFinding("attack_caught_by_unrelated_check",
                                             f"{c.candidate_id} targeted {sorted(targeted)} but only failed "
                                             f"{failed[:NAMED_IN_MESSAGE]}", c.candidate_id))
        if res.outcome in (Outcome.verifier_error, Outcome.environment_failure, Outcome.timeout, Outcome.unresolved):
            findings.append(AuditFinding("infrastructure", f"{c.candidate_id}: {res.outcome.value}: {res.diagnostics[:3]}", c.candidate_id))
    blocking = {"reference_not_passing", "false_rejection_dev", "false_acceptance_dev", "uncovered_requirement", "infrastructure"}
    passed = not any(f.code in blocking or f.code.startswith("lint_") for f in findings)
    return AuditReport(passed, findings, runs)


# --------------------------------------------------------------------------- iteration records


class AuditRecordError(ValueError):
    """An audit record cannot be made complete from what was given; nothing is recorded."""


# How the hashes of a SuiteSnapshot are made. An iteration record of another scheme is not compared with this one's,
# since the same tests would hash otherwise; a change to suite_snapshot that changes any hash needs a new scheme.
SNAPSHOT_SCHEME = "suite-snapshot:v1"


class SuiteSnapshot(BaseModel):
    """The tests that one audit iteration graded: the ``tests`` of an iteration record (:func:`suite_snapshot`)."""

    model_config = ConfigDict(extra="forbid")

    scheme: str  # SNAPSHOT_SCHEME of the code that made it
    content_sha256: str  # verifier.hash_test_dir of the test files graded
    checks_sha256: str  # verifier.checks_sha256 of the spec's check list
    files: dict[str, str] = Field(default_factory=dict)  # path in the test dir -> sha256 of its bytes
    checks: list[AuditCheck] = Field(default_factory=list)
    # "<file>::<name>" -> sha256, for every module-level definition of a Python file of the tests other than a check
    # function and CHECK_REQUIREMENTS (whose content each check's requirement ids record)
    module_code: dict[str, str] = Field(default_factory=dict)


class AuditInputs(BaseModel):
    """What an audit iteration was graded with besides the tests: the contract (``--contract``: its variant and the
    sha256 of its file), the audit set (``--audit-set``), the candidates named with ``--only``, and the reference's
    repeats. Every iteration of one record is graded with the same."""

    model_config = ConfigDict(extra="forbid")

    contract: str | None = None
    contract_sha256: str | None = None
    audit_set: str | None = None
    only: list[str] | None = None
    reference_repeats: int


_INPUTS = {"contract": "contract (--contract)", "contract_sha256": "contract file", "audit_set": "audit set (--audit-set)",
           "only": "candidate selection (--only)", "reference_repeats": "number of reference runs"}


class IterationRecord(BaseModel):
    """What ``tracecontract audit`` prints for one iteration, as a later recording run reads it back."""

    model_config = ConfigDict(extra="ignore")  # e.g. the "record" that a recording run also prints

    procedure: str
    task_id: str
    verifier_id: str
    graded_at: str
    inputs: AuditInputs
    passed: bool
    findings: list[AuditFindingEntry]
    runs: list[AuditRun]
    dev_candidates: list[str]
    tests: SuiteSnapshot


def iteration_output(rep: AuditReport, *, task_id: str, verifier_id: str, dev_ids: list[str], tests: SuiteSnapshot,
                     inputs: AuditInputs, graded_at: str) -> dict:
    """The JSON that ``tracecontract audit`` prints for one iteration: the findings, the runs and the development
    candidates as before (a reviser is given that findings list; the runs of the reference also keep each of its runs),
    and the procedure, the task, the verifier, when it was graded, what it was graded with and the tests graded, which
    :func:`read_loop` needs when a later iteration is recorded."""
    return {"passed": rep.passed, "findings": [vars(f) for f in rep.findings], "runs": rep.runs, "dev_candidates": dev_ids,
            "procedure": PROCEDURE, "task_id": task_id, "verifier_id": verifier_id, "graded_at": graded_at,
            "inputs": inputs.model_dump(mode="json"), "tests": tests.model_dump(mode="json")}


def _content_sha256(files: dict[str, str]) -> str:
    """``verifier.hash_test_dir`` of a test dir that holds these files (path -> sha256 of the bytes): the paths in the
    order in which it walks them, each with the digest of its bytes."""
    h = hashlib.sha256()
    for rel in sorted(files, key=lambda r: r.split("/")):  # pathlib orders paths by their parts
        h.update(rel.encode() + b"\0")
        h.update(bytes.fromhex(files[rel]))
    return h.hexdigest()


def _when(text: str) -> datetime | None:
    """An ISO time with a time zone, else None."""
    try:
        t = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo is not None else None


def read_iteration_record(path: str | Path, *, task_id: str, verifier_id: str) -> IterationRecord:
    """The iteration record in ``path`` (:func:`iteration_output`), which must be one of ``verifier_id`` of ``task_id``.

    Raises :class:`AuditRecordError` for a file that is not one, among them an iteration record printed before records
    kept the tests graded (the results of the pilot's audits, ``results/audits/``) or by a version of
    :func:`suite_snapshot` that hashes otherwise, and one whose tests do not match their own hashes (an edited
    record): its check list must give its ``checks_sha256``, its files its ``content_sha256``."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditRecordError(f"{path} is not a readable JSON file ({type(exc).__name__})") from None
    if not isinstance(raw, dict):
        raise AuditRecordError(f"{path} does not hold a JSON object")
    if "tests" not in raw or "procedure" not in raw:
        raise AuditRecordError(f"{path} is not an iteration record that keeps the tests it graded (it has no "
                               f"{'tests' if 'tests' not in raw else 'procedure'}); it was printed before audit records kept "
                               "them, so what the next revision changed cannot be recorded")
    scheme = raw["tests"].get("scheme") if isinstance(raw["tests"], dict) else None
    if scheme != SNAPSHOT_SCHEME:
        raise AuditRecordError(f"{path} was printed by another version of the audit's snapshot of the tests "
                               f"({scheme or 'unversioned'}, not {SNAPSHOT_SCHEME}), whose hashes cannot be compared with "
                               "this run's; run the loop's audits with one version")
    try:
        rec = IterationRecord.model_validate(raw)
    except ValidationError as exc:
        raise AuditRecordError(f"{path} is not an iteration record: " + " ".join(str(exc).split())[:600]) from None
    if rec.procedure != PROCEDURE:
        raise AuditRecordError(f"{path} is a record of {rec.procedure}, not of {PROCEDURE}")
    if (rec.task_id, rec.verifier_id) != (task_id, verifier_id):
        raise AuditRecordError(f"{path} is an iteration record of {rec.task_id} {rec.verifier_id}, not of {task_id} {verifier_id}")
    if _when(rec.graded_at) is None:
        raise AuditRecordError(f"{path}: graded_at {rec.graded_at!r} is not an ISO time with a time zone")
    t = rec.tests
    if checks_sha256(SimpleNamespace(checks=t.checks)) != t.checks_sha256:
        raise AuditRecordError(f"{path}: its check list does not give its checks_sha256; the record was edited")
    try:
        content = _content_sha256(t.files)
    except ValueError:
        content = None
    if content != t.content_sha256:
        raise AuditRecordError(f"{path}: its files do not give its content_sha256; the record was edited")
    return rec


def read_loop(paths: Sequence[str | Path], *, task_id: str, verifier_id: str, revisions: int, tests: SuiteSnapshot,
              inputs: AuditInputs, dev_ids: list[str], graded_at: str,
              start: tuple[str, str] | None = None) -> list[IterationRecord]:
    """The iteration records of an audit loop that ended after ``revisions`` revisions, iteration 0 first, as a
    recording run graded at ``graded_at`` reads them (:func:`read_iteration_record` reads each).

    A loop audits its tests, and while they do not pass, revises them and audits them again: iteration i is the audit
    after revision i, and the recording run grades the tests of the last iteration again. So there are ``revisions +
    1`` records, of distinct files, graded one after another before this run, each with the inputs (``inputs``) and the
    candidates (``dev_ids``) of this run; every record but the last did not pass; the last graded the tests that this
    run grades (``tests``); and with ``start`` (``(verifier id, content sha256)``) the first graded a copy of that
    verifier's tests (:data:`STARTS_FROM`). Raises :class:`AuditRecordError` otherwise."""
    if len(paths) != revisions + 1:
        raise AuditRecordError(
            f"--record {revisions} records the iteration after {revisions} revision(s), so it needs the {revisions + 1} "
            f"iteration record(s) of its audit loop, iteration 0 first and the last of the tests this run grades "
            f"(--previous FILE ...: the JSON this command printed for each iteration); {len(paths)} given")
    files: dict[tuple[int, int], str | Path] = {}
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            continue  # read_iteration_record says why
        if (st.st_dev, st.st_ino) in files:
            raise AuditRecordError(f"{p} is given twice (also as {files[st.st_dev, st.st_ino]}); each iteration has its own "
                                   "record")
        files[st.st_dev, st.st_ino] = p
    loop = [read_iteration_record(p, task_id=task_id, verifier_id=verifier_id) for p in paths]
    for i, (p, r) in enumerate(zip(paths, loop)):
        differ = [k for k in AuditInputs.model_fields if getattr(r.inputs, k) != getattr(inputs, k)]
        if differ:
            k = differ[0]
            raise AuditRecordError(f"{p} (iteration {i}) was graded with another {_INPUTS[k]} than this run ("
                                   f"{getattr(r.inputs, k)!r} there, {getattr(inputs, k)!r} here); the iterations of one "
                                   "record are graded alike")
        if r.dev_candidates != dev_ids:
            odd = sorted(set(r.dev_candidates) ^ set(dev_ids))
            raise AuditRecordError(f"{p} (iteration {i}) graded other development candidates than this run"
                                   + (f" (not in both: {', '.join(odd)})" if odd else " (in another order)"))
    times = [_when(r.graded_at) for r in loop]
    for i in range(1, len(loop)):
        if times[i] == times[i - 1]:
            raise AuditRecordError(f"{paths[i]} was graded at the same time as {paths[i - 1]}, so one is a copy of the other")
        if times[i] < times[i - 1]:
            raise AuditRecordError(f"the iteration records are not in the order of the loop: {paths[i]} (given as iteration "
                                   f"{i}) was graded before {paths[i - 1]}; give them iteration 0 first")
    now = _when(graded_at)
    if now is None or times[-1] >= now:
        raise AuditRecordError(f"{paths[-1]} was graded at {loop[-1].graded_at}, not before this run ({graded_at})")
    for i, (p, r) in enumerate(zip(paths[:-1], loop[:-1])):
        if r.passed:
            raise AuditRecordError(f"{p} (iteration {i}) passed, and a revision follows only an audit that did not pass, "
                                   f"so the loop ended there, after {i} revision(s)")
    last = loop[-1].tests
    if (last.content_sha256, last.checks_sha256) != (tests.content_sha256, tests.checks_sha256):
        what = "other test files" if last.content_sha256 != tests.content_sha256 else "another check list"
        raise AuditRecordError(f"{paths[-1]}, the last iteration record, graded {what} than this run; the last record is "
                               "the loop's audit of the tests that are recorded")
    if start is not None and loop[0].tests.content_sha256 != start[1]:
        raise AuditRecordError(f"{paths[0]} (iteration 0) graded other tests than a copy of {start[0]}'s, which iteration 0 "
                               f"of {verifier_id} grades (protocol §4)")
    return loop


def _iteration(i: int, passed: bool, graded_at: str | None, findings: list[AuditFindingEntry], runs: list[AuditRun],
               tests: SuiteSnapshot) -> AuditIteration:
    return AuditIteration(iteration=i, passed=passed, graded_at=graded_at, content_sha256=tests.content_sha256,
                          checks_sha256=tests.checks_sha256, files=dict(tests.files), checks=list(tests.checks),
                          findings=list(findings), runs=list(runs))


# --------------------------------------------------------------------------- the tests an iteration grades


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lines(text: str) -> list[str]:
    """``text`` split into lines as the parser numbers them (``str.splitlines`` also splits at form feeds and others)."""
    return re.split(r"\r\n|\r|\n", text)


# A node that a check id can name: a test function, or a class on the way to a test method.
_Node = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _start(node: ast.stmt) -> int:
    return min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])


def _source(lines: list[str], node: ast.stmt, skip: Sequence[ast.stmt] = ()) -> str:
    """The source of ``node`` from its first decorator to its last line, without the lines of the nodes in ``skip``."""
    drop = {n for s in skip for n in range(_start(s), (s.end_lineno or s.lineno) + 1)}
    return "\n".join(lines[n - 1] for n in range(_start(node), (node.end_lineno or node.lineno) + 1) if n not in drop)


def _called(node: ast.AST) -> str | None:
    """The name that a call or a decorator ends in: ``fixture`` for ``pytest.fixture(...)`` and for ``@fixture``."""
    f = node.func if isinstance(node, ast.Call) else node
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def _fixture(node: ast.stmt) -> tuple[bool, str | None] | None:
    """``(autouse, name=)`` of a function that a decorator makes a pytest fixture; None for any other node."""
    for d in getattr(node, "decorator_list", []) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else []:
        if _called(d) == "fixture":
            kw = {k.arg: k.value.value for k in getattr(d, "keywords", []) if isinstance(k.value, ast.Constant)}
            name = kw.get("name")
            return kw.get("autouse") is True, name if isinstance(name, str) else None
    return None


def _names(node: ast.AST, skip: Sequence[ast.AST] = ()) -> set[str]:
    """Every name that ``node`` mentions, outside the nodes in ``skip``: its parameters included (a pytest fixture is
    one), and the fixtures that ``usefixtures("name", ...)`` names."""
    out: set[str] = set()
    todo = [node]
    while todo:
        n = todo.pop()
        if any(n is s for s in skip):
            continue
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.Call) and _called(n) == "usefixtures":
            out.update(a.value for a in n.args if isinstance(a, ast.Constant) and isinstance(a.value, str))
        todo.extend(ast.iter_child_nodes(n))
    return out


_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _in_scope(node: ast.AST) -> list[ast.AST]:
    """The children of ``node`` that run in the scope that ``node`` is in. The body of a function, a lambda or a class,
    and a comprehension but for its first iterable, are scopes of their own; decorators, default values, base classes
    and class keywords are not."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = node.args
        return [*getattr(node, "decorator_list", []), *a.defaults, *(d for d in a.kw_defaults if d is not None)]
    if isinstance(node, ast.ClassDef):
        return [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]
    if isinstance(node, _COMPREHENSIONS):
        return [node.generators[0].iter]
    return list(ast.iter_child_nodes(node))


def _names_at_import(node: ast.AST) -> set[str]:
    """The names that a module-level statement mentions in the code that runs when the module is imported: not in the
    body of a function or a lambda, which runs when it is called."""
    out: set[str] = set()
    todo = [node]
    while todo:
        n = todo.pop()
        if isinstance(n, ast.Name):
            out.add(n.id)
        todo.extend(_in_scope(n) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
                    else ast.iter_child_nodes(n))
    return out


def _walrus(comp: ast.AST) -> set[str]:
    """The names that an assignment expression in a comprehension binds in the scope around it (PEP 572)."""
    out: set[str] = set()
    todo = list(ast.iter_child_nodes(comp))
    while todo:
        n = todo.pop()
        if isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
        if not isinstance(n, _SCOPES):
            todo.extend(ast.iter_child_nodes(n))
    return out


def _bound(node: ast.AST) -> set[str]:
    """The names that a module-level statement binds in the module: at any depth of it (an ``if`` or ``try`` block's
    too), but not inside a function, a lambda, a class body or a comprehension, whose names are their own."""
    out: set[str] = set()
    todo = [node]
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update(a.asname or a.name.split(".")[0] for a in n.names if a.name != "*")
        elif isinstance(n, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.MatchMapping) and n.rest:
            out.add(n.rest)
        elif isinstance(n, _COMPREHENSIONS):
            out |= _walrus(n)
        todo.extend(_in_scope(n))
    return out


def _is_requirement_map(node: ast.AST) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
    return any(isinstance(t, ast.Name) and t.id == "CHECK_REQUIREMENTS" for t in targets)


# Module-level names that pytest applies to every test of a module, which a test need not name: its marks and its
# module-level setup and teardown functions (an autouse fixture is another such definition).
_IMPLICIT = frozenset({"pytestmark", "pytest_generate_tests", "setup_module", "teardown_module", "setUpModule",
                       "tearDownModule", "setup_function", "teardown_function"})


@dataclass
class _Definition:
    digest: str
    names: set[str]  # the names under which a check that uses one finds it (see _definitions)
    uses: set[str]


def _definitions(lines: list[str], tree: ast.Module, checks: list[_Node]) -> dict[str, _Definition]:
    """The module-level definitions of a file other than its check functions and CHECK_REQUIREMENTS, by key.

    A function, a class (without its check methods) or an imported name is keyed by what it binds, and so is an
    assignment of plain names (each name of it); the module docstring is ``__doc__``, and any other statement
    ``<Kind sha256[:12]>``. A name defined twice has the digest of both definitions. A check that uses a name finds
    the definitions that bind it, a fixture also under its ``name=``, and one of those other statements
    (``CASES.extend(...)``, ``EXPECTED["k"] = v``, an ``if`` or ``for`` block) also under every module-level name it
    mentions in the code that runs at import (:func:`_names_at_import`), whose value it may change."""
    defs: dict[str, _Definition] = {}
    check_names = {n.name for n in checks if any(n is m for m in tree.body)}

    def add(name: str, text: str, names: set[str], uses: set[str]) -> None:
        d = defs.get(name)
        if d is None:
            defs[name] = _Definition(_sha(text), set(names), set(uses))
        else:
            d.digest, d.names, d.uses = _sha(d.digest + "\0" + _sha(text)), d.names | names, d.uses | uses

    statements: list[tuple[str, ast.stmt]] = []
    for i, node in enumerate(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in check_names:
            continue  # a check (or a definition of its name that the check replaces)
        if _is_requirement_map(node):
            continue
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            add("__doc__", _source(lines, node), set(), set())
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:  # one definition per imported name, so importing one more name changes no other
                bound = a.asname or (a.name.split(".")[0] if isinstance(node, ast.Import) else a.name)
                head = "import " if isinstance(node, ast.Import) else f"from {'.' * node.level}{node.module or ''} import "
                add(bound, head + a.name + (f" as {a.asname}" if a.asname else ""), {bound}, set())
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inside = {id(n) for n in ast.walk(node)} if isinstance(node, ast.ClassDef) else set()
            skip = [c for c in checks if id(c) in inside]  # a class's check methods, at any depth, are checks of their own
            alias = (_fixture(node) or (False, None))[1]
            add(node.name, _source(lines, node, skip), {node.name} | ({alias} if alias else set()), _names(node, skip))
        else:
            text, binds, uses = _source(lines, node), _bound(node), _names(node)
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and binds:
                for name in sorted(binds):
                    add(name, text, {name}, uses)
            else:
                key = f"<{type(node).__name__} {_sha(text)[:12]}>"
                add(key, text, binds, uses)
                statements.append((key, node))
    module_names = set().union(*(d.names for d in defs.values()))
    for key, node in statements:
        defs[key].names |= _names_at_import(node) & module_names
    return defs


def _locate(check_id: str, trees: dict[str, tuple[list[str], ast.Module]]) -> tuple[str, list[_Node]] | None:
    """The file of a check and its node path (classes, then the function), for a pytest node id ``file.py::[Class::]test``
    or one of the module forms that B1's ids take, ``pkg.module::test[params]`` and ``pkg.module.Class::test``; None when
    the id names no function of the test files where it points (a test method that a class inherits is not looked up)."""
    parts = check_id.split("[", 1)[0].split("::")  # parameters may hold anything, "::" included
    if len(parts) < 2:
        return None
    head, classes = parts[0], []
    if head.endswith(".py"):
        rel = head
    else:  # the longest dotted prefix that is a file of the tests; the rest are classes
        dotted = head.split(".")
        k = next((k for k in range(len(dotted), 0, -1) if "/".join(dotted[:k]) + ".py" in trees), 0)
        rel, classes = "/".join(dotted[:k]) + ".py", dotted[k:]
    if rel not in trees:
        return None
    names = [*classes, *parts[1:]]
    body: list[ast.stmt] = trees[rel][1].body
    chain: list[_Node] = []
    for k, name in enumerate(names):
        last = k == len(names) - 1  # a function last, classes before it
        found = [n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name
                 and isinstance(n, ast.ClassDef) != last]
        if not found:
            return None
        chain.append(found[-1])  # the definition that pytest collects
        body = getattr(found[-1], "body", [])
    return rel, chain


def _uses_digest(uses: set[str], defs: dict[str, _Definition], by_name: dict[str, list[str]],
                 files: Sequence[tuple[str, str]] = ()) -> str | None:
    """The digest of the definitions that the names ``uses`` reach, transitively, and of the ``(path, sha256)`` of
    ``files``; None when there is neither."""
    seen: set[str] = set()
    todo = [k for name in uses for k in by_name.get(name, ())]
    while todo:
        k = todo.pop()
        if k not in seen:
            seen.add(k)
            todo.extend(k2 for name in defs[k].uses for k2 in by_name.get(name, ()))
    items = sorted([[k, defs[k].digest] for k in seen] + [[f"file:{p}", d] for p, d in files])
    return _sha(json.dumps(items, separators=(",", ":"))) if items else None


def _conftests(rel: str, files: dict[str, str]) -> list[tuple[str, str]]:
    """The ``(path, sha256)`` of the conftest.py files among ``files`` that pytest applies to the test file ``rel``:
    those in its directory and above it."""
    return [(p, digest) for p, digest in files.items()
            if (p == "conftest.py" or p.endswith("/conftest.py")) and rel.startswith(p[: -len("conftest.py")])]


def suite_snapshot(spec: VerifierSpec, task_dir: Path) -> SuiteSnapshot:
    """The tests of ``spec`` as an audit iteration grades them: the files in ``task_dir / spec.test_dir`` and the
    spec's checks.

    Each check gets the sha256 of its function's source and of the code it depends on beyond it (``uses_sha256``): the
    module-level code of its file that the function uses, transitively (a name it mentions, a fixture it requests or
    names in ``usefixtures``, a check method's classes; :func:`_definitions`), the file's autouse fixtures, marks and
    module-level setup functions (:data:`_IMPLICIT`), which pytest applies to every test of the file, and every
    conftest.py in the check's directory or above it, by its bytes. Data files and other modules that a check reads or
    imports are not followed: their changes show only as changed files. A check id that names no function of the files
    gets neither hash. Every other module-level definition of a Python file is hashed by key (:func:`_definitions`),
    and every file by its bytes. A file that does not parse is hashed but not read."""
    test_dir = task_dir / spec.test_dir
    files: dict[str, str] = {}
    trees: dict[str, tuple[list[str], ast.Module]] = {}
    if test_dir.is_dir():
        for p in sorted(test_dir.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            rel, data = p.relative_to(test_dir).as_posix(), p.read_bytes()
            files[rel] = hashlib.sha256(data).hexdigest()
            if rel.endswith(".py"):
                try:
                    text = data.decode("utf-8")
                    trees[rel] = (_lines(text), ast.parse(text, filename=rel))
                except (UnicodeDecodeError, SyntaxError, ValueError):
                    pass
    located = {c.check_id: _locate(c.check_id, trees) for c in spec.checks}
    module: dict[str, tuple[dict[str, _Definition], dict[str, list[str]], set[str]]] = {}
    for rel, (lines, tree) in trees.items():
        defs = _definitions(lines, tree, [loc[1][-1] for loc in located.values() if loc and loc[0] == rel])
        by_name: dict[str, list[str]] = {}
        for key, d in defs.items():
            for name in d.names:
                by_name.setdefault(name, []).append(key)
        autouse = {n.name for n in tree.body if (_fixture(n) or (False, None))[0]}
        module[rel] = (defs, by_name, set(_IMPLICIT) | autouse)
    conftests = {p: d for p, d in sorted(files.items()) if p == "conftest.py" or p.endswith("/conftest.py")}
    above: dict[str, list[tuple[str, str]]] = {}
    checks = []
    for c in spec.checks:
        loc = located[c.check_id]
        if loc is None:
            checks.append(AuditCheck(check_id=c.check_id, requirement_ids=list(c.requirement_ids)))
            continue
        rel, chain = loc
        defs, by_name, implicit = module[rel]
        if rel not in above:
            above[rel] = _conftests(rel, conftests)
        uses = _names(chain[-1]) | {n.name for n in chain[:-1]} | implicit  # a method uses its classes' other members
        checks.append(AuditCheck(check_id=c.check_id, requirement_ids=list(c.requirement_ids),
                                 sha256=_sha(_source(trees[rel][0], chain[-1])),
                                 uses_sha256=_uses_digest(uses, defs, by_name, above[rel])))
    code = {f"{rel}::{key}": d.digest for rel, (defs, _, _) in module.items() for key, d in defs.items()}
    return SuiteSnapshot(scheme=SNAPSHOT_SCHEME, content_sha256=hash_test_dir(test_dir), checks_sha256=checks_sha256(spec),
                         files=files, checks=checks, module_code=dict(sorted(code.items())))


# --------------------------------------------------------------------------- revisions


def _changes(before: dict[str, str], after: dict[str, str]) -> list[AuditCodeChange]:
    return [AuditCodeChange(name=k, change="added" if k not in before else "removed" if k not in after else "changed")
            for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]


def revision_changes(before: SuiteSnapshot, after: SuiteSnapshot, revision: int) -> AuditRevision:
    """What a revision changed, from the tests of the iteration before it (``before``) to those after it (``after``).

    A check is added or removed by its id, changed when its function's source changed, and changed indirectly when only
    the code it depends on beyond it changed (``AuditCheck.uses_sha256``: the module-level code it uses, its file's
    autouse fixtures and marks, conftest.py); the requirement map lists every check whose requirement ids differ (an
    added or removed check's included, with ``None`` on the side that lacks it)."""
    old = {c.check_id: c for c in before.checks}
    new = {c.check_id: c for c in after.checks}
    kept = [k for k in new if k in old]
    changed = [k for k in kept if new[k].sha256 != old[k].sha256]
    reqs = []
    for k in [*new, *(k for k in old if k not in new)]:
        was = old[k].requirement_ids if k in old else None
        now = new[k].requirement_ids if k in new else None
        if was is None or now is None or sorted(was) != sorted(now):
            reqs.append(AuditRequirementChange(check_id=k, before=was, after=now))
    return AuditRevision(
        revision=revision, added=[k for k in new if k not in old], removed=[k for k in old if k not in new], changed=changed,
        changed_indirectly=[k for k in kept if k not in changed and new[k].uses_sha256 != old[k].uses_sha256],
        requirement_map=reqs, module_code=_changes(before.module_code, after.module_code),
        files=_changes(before.files, after.files))


def changes_checks(rev: AuditRevision) -> bool:
    """True when the revision added, removed or changed a check, or changed the requirement map."""
    return bool(rev.added or rev.removed or rev.changed or rev.changed_indirectly or rev.requirement_map)


def changes_nothing(rev: AuditRevision) -> bool:
    return not (changes_checks(rev) or rev.module_code or rev.files)


# --------------------------------------------------------------------------- human-readable findings


def _earlier_only(run: AuditRun) -> list[str]:
    """The checks that failed in an earlier run of a candidate graded more than once but not in its last run, whose
    failing checks a finding's message names."""
    last, out = set(run.failed_checks), []
    for rep in run.repeats[:-1]:
        out += [k for k in rep.failed_checks if k not in last and k not in out]
    return out


def finding_lines(findings: Sequence[AuditFindingEntry], runs: Sequence[AuditRun]) -> list[str]:
    """The findings as ``"<code>: <message>"``. A message that names only the first failing checks
    (:data:`NAMED_IN_MESSAGE`) says how many failed in all, all of which the record's history lists; one that names the
    failing checks of the last run of a candidate graded more than once also names those that failed only in an
    earlier run."""
    by_id = {r.candidate_id: r for r in runs}
    out = []
    for f in findings:
        line = f"{f.code}: {f.message}"
        run = by_id.get(f.candidate_id or "") if f.code in _NAMES_FAILED_CHECKS else None
        if run is not None:
            n = len(run.failed_checks)
            if n > NAMED_IN_MESSAGE:
                line += f" ({NAMED_IN_MESSAGE} of {n} failing checks named; the record's history lists all {n})"
            earlier = _earlier_only(run)
            if earlier:
                line += (f" (failing in an earlier run but not in the last: {', '.join(earlier)}; the record's history "
                         "lists the failing checks of each run)")
        out.append(line)
    return out


def _reqs(ids: list[str] | None) -> str:
    return "[" + ", ".join(ids or []) + "]"


def _grade(run: AuditRun | None) -> str:
    if run is None:
        return "not graded"
    each = " (runs: " + ", ".join(f"{r.outcome} {_reqs(r.failed_checks)}" for r in run.repeats) + ")" if run.repeats else ""
    return f"{run.outcome} {_reqs(run.failed_checks)}{each}"


def regrade_line(loop_last: IterationRecord, passed: bool, runs: Sequence[AuditRun], iteration: int) -> str | None:
    """A line when this run's grade of the tests of iteration ``iteration`` differs from the loop's grade of the same
    tests (``loop_last``, which the record keeps no other way), naming every candidate graded otherwise; None when the
    two grades agree."""
    theirs = {r.candidate_id: r for r in loop_last.runs}
    differ = [r for r in runs if theirs.get(r.candidate_id) != r]
    if loop_last.passed == passed and not differ:
        return None
    parts = [f"passed {str(loop_last.passed).lower()} in the loop, {str(passed).lower()} now"]
    parts += [f"{r.candidate_id}: {_grade(theirs.get(r.candidate_id))} in the loop, {_grade(r)} now" for r in differ]
    return (f"regrade_differs: this run graded the tests of iteration {iteration} again and differs from the loop's grade "
            "of them: " + "; ".join(parts))


def revision_line(rev: AuditRevision, of: int, *, no_finding: bool) -> str:
    """One human-readable line for what revision ``rev`` (of ``of``) changed; ``no_finding``: the last iteration has no
    finding, which the line then says, so that a record without findings still shows that the checks changed."""
    head = f"revision {rev.revision} of {of}"
    if changes_nothing(rev):
        return f"revision_unchanged: {head} changed no test file and no check"
    after = {c.check_id: c.after for c in rev.requirement_map}
    before = {c.check_id: c.before for c in rev.requirement_map}
    parts = []
    if rev.added:
        parts.append(f"checks added ({len(rev.added)}): " + ", ".join(f"{k} {_reqs(after.get(k))}" for k in rev.added))
    if rev.removed:
        parts.append(f"checks removed ({len(rev.removed)}): "
                     + ", ".join(f"{k} (was {_reqs(before.get(k))})" for k in rev.removed))
    if rev.changed:
        parts.append(f"checks changed ({len(rev.changed)}): " + ", ".join(rev.changed))
    if rev.changed_indirectly:
        parts.append(f"checks changed through the module-level code they use ({len(rev.changed_indirectly)}): "
                     + ", ".join(rev.changed_indirectly))
    remapped = [c for c in rev.requirement_map if c.before is not None and c.after is not None]
    if remapped:
        parts.append("requirement map changed: "
                     + ", ".join(f"{c.check_id} {_reqs(c.before)} -> {_reqs(c.after)}" for c in remapped))
    for label, items in (("module-level code", rev.module_code), ("files", rev.files)):
        for kind in ("added", "removed", "changed"):
            names = [c.name for c in items if c.change == kind]
            if names:
                parts.append(f"{label} {kind}: " + ", ".join(names))
    clause = ", although no finding remains" if no_finding else ""
    if changes_checks(rev):
        return f"revision_changed_checks: {head} changed the checks{clause}: " + "; ".join(parts)
    # The check functions and the code they are known to depend on (suite_snapshot) are unchanged; a data file or
    # another module that a check reads can still have changed what it verifies, and is among the files listed.
    return (f"revision_changed_tests: {head} changed the test files but no check function and no code the checks are "
            f"known to depend on{clause}: " + "; ".join(parts))
