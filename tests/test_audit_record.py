"""Complete audit:v1 records (decision log D62): every failing check of every iteration, and what each revision changed.

Synthetic verifiers and a fake grader only; no Docker. The audit loop is run as the build session runs it (plan P3):
the plain verifier's tests are built, frozen and copied to the audited verifier, ``build-verifier``, ``audit`` (whose
printed JSON is the iteration record, saved as ``it<i>.json``), revise the tests in place, ``build-verifier`` and
``audit`` again, and finally ``audit --record N --previous it0.json ... it<N>.json``: every iteration record of the loop.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import textwrap
from datetime import datetime
from pathlib import Path

import pytest

from tracecontract import audit, cli
from tracecontract.schemas import (
    AuditIteration, AuditRecord, Candidate, CandidateOrigin, CheckResult, CheckSpec, ContractVariant, Isolation, Label,
    LabelerKind, Outcome, Population, Requirement, RequirementKind, RequirementStatus, SnapshotSource, Split, TaskContract,
    TaskManifest, VerificationResult, VerifierCondition, VerifierSpec, sha256_text,
)
from tracecontract.store import dump, load
from tracecontract.verifier import discover_checks, hash_test_dir, requirement_map_from_tests

REPO = Path(__file__).resolve().parents[1]
TID, VID, PLAIN, CONTRACT, T0 = "TX-01", "full_audited", "full_plain", "full_session", "2026-11-22T10:00:00+00:00"
GEN = ["--gen-run-id", "wf_fixture/revise", "--config", "config-A", "--prompt-sha256", "0" * 64, "--started-at", T0,
       "--ended-at", "2026-11-22T10:30:00+00:00", "--turns", "3", "--tool-calls", "5", "--wall-s", "60",
       "--run-record", "build-session:synthetic/revise.jsonl"]
REFUSED = "audit refused, nothing graded or recorded: "


# --------------------------------------------------------------------------- a synthetic task and its audit loop


def check(name: str, *asserts: str) -> str:
    return f"def {name}():\n" + "".join(f"    assert {a}\n" for a in asserts)


def suite(checks: list[str], reqs: dict[str, list[str]], helpers: str = "", doc: str = "Synthetic verifier tests.") -> str:
    """A lint-clean test file: the checks, their CHECK_REQUIREMENTS and a helper that goes through the sandbox."""
    return (f'"""{doc}"""\n\nfrom tc_sandbox import run_python\n\nCHECK_REQUIREMENTS = {json.dumps(reqs, indent=4)}\n\n\n'
            'def _value(expr):\n    return run_python("result = " + expr).value\n\n\n'
            + (helpers.strip() + "\n\n\n" if helpers else "") + "\n\n".join(checks))


class Grader:
    """A fake grader: a candidate fails the checks named for it in ``failing`` (by function name) and passes the rest;
    while ``runs`` holds a list for it, each run fails the next set of that list instead. A grade with repeats combines
    its runs as the real grader does (``docker_runner.verify_candidate``): one outcome when they agree, else unresolved,
    and the checks of its last run only."""

    def __init__(self) -> None:
        self.failing: dict[str, set[str]] = {}
        self.runs: dict[str, list[set[str]]] = {}
        self.calls: list[tuple[str, int]] = []

    def _run(self, spec: VerifierSpec, cand: Candidate) -> tuple[Outcome, list[CheckResult]]:
        key = cand.candidate_id.removeprefix(f"{TID}-")
        queue = self.runs.get(key)
        bad = queue.pop(0) if queue else self.failing.get(key, set())
        checks = [CheckResult(check_id=c.check_id, status="failed" if c.check_id.split("::")[-1] in bad else "passed")
                  for c in spec.checks]
        return (Outcome.task_failure if any(k.status != "passed" for k in checks) else Outcome.passed), checks

    def __call__(self, spec: VerifierSpec, cand: Candidate, repeats: int = 1) -> VerificationResult:
        self.calls.append((cand.candidate_id, repeats))
        runs = [self._run(spec, cand) for _ in range(repeats)]
        outcomes = [oc for oc, _ in runs]
        oc = outcomes[0] if len(set(outcomes)) == 1 else Outcome.unresolved
        diags = [] if len(set(outcomes)) == 1 else [f"repeated runs disagree: {[o.value for o in outcomes]}"]
        return VerificationResult(run_id="adhoc", task_id=TID, verifier_id=spec.verifier_id, candidate_id=cand.candidate_id,
                                  outcome=oc, reward=1.0 if oc == Outcome.passed else 0.0, checks=runs[-1][1],
                                  diagnostics=diags, started_at=T0, finished_at=T0, wall_s=0.1, harness_version="fake")


class World:
    def __init__(self, root: Path, capsys, monkeypatch) -> None:
        self.dir, self.td, self.capsys, self.grader = root, root / TID, capsys, Grader()
        self.tests = self.td / "verifiers" / VID / "tests"
        self.spec_path = self.td / "verifiers" / VID / "spec.json"
        self.saved: list[str] = []  # the loop's iteration records, iteration 0 first
        cands = [self._cand("reference", CandidateOrigin.reference), self._cand("noop-dev", CandidateOrigin.noop),
                 self._cand("dev-attack-full_session-a1", CandidateOrigin.dev_attack, violates=["R1"]),
                 self._cand("dev-alt-full_session", CandidateOrigin.valid_alternative)]
        for c in cands:
            dump(c, self.td / "candidates" / f"{c.candidate_id}.json")
        req = Requirement(req_id="R1", statement="a synthetic requirement", kind=RequirementKind.change,
                          status=RequirementStatus.inferred, rationale="fixture", introduced_at="e1", proposer="rule:v1")
        dump(TaskContract(contract_id=f"{TID}-{CONTRACT}", task_id=TID, session_id="s1", variant=ContractVariant.full_session,
                          requirements=[req], created_by="fixture", created_at=T0), self.td / "contracts" / f"{CONTRACT}.json")
        dump(TaskManifest(task_id=TID, family_id="fx", population=Population.fixture, status="draft",
                          provenance="provenance.json", env_requirements=[],
                          snapshot_source=SnapshotSource(repo_url="https://example.invalid/fx.git", commit="0" * 40),
                          contracts={CONTRACT: f"contracts/{CONTRACT}.json"},
                          candidates=[f"candidates/{c.candidate_id}.json" for c in cands]), self.td / "task.json")
        monkeypatch.setattr(cli, "_grader", lambda tdir, m, command="grade": self.grader)

    @staticmethod
    def _cand(kind: str, origin: CandidateOrigin, violates: list[str] | None = None) -> Candidate:
        labels = [Label(value="invalid", violated_requirements=violates, labeler="attack:v1",
                        labeler_kind=LabelerKind.construction, timestamp=T0)] if violates else []
        return Candidate(candidate_id=f"{TID}-{kind}", task_id=TID, origin=origin, split=Split.dev, patch="",
                         patch_sha256=sha256_text(""), produced_by="fixture", labels=labels)

    def run(self, *argv: str) -> tuple[int | str, object]:
        """``(exit code, printed JSON)`` of ``tracecontract <argv>``; a refusal's message is its code."""
        try:
            cli.main(list(argv))
            code: int | str = 0
        except SystemExit as exc:
            code = 0 if exc.code is None else exc.code
        out = self.capsys.readouterr().out
        return code, json.loads(out) if out.strip() else None

    @staticmethod
    def _write(tests: Path, text: str) -> None:
        tests.mkdir(parents=True, exist_ok=True)
        for p in tests.iterdir():
            p.unlink()
        (tests / "test_t.py").write_text(text, encoding="utf-8")

    def build(self, vid: str = VID) -> None:
        code, out = self.run("build-verifier", str(self.td), vid, "--condition", vid, "--contract-id", f"{TID}-{CONTRACT}",
                             *GEN)
        assert code == 0 and out["recorded"] and out["lint"] == [], out

    def start(self, text: str) -> None:
        """P2 and the start of P3: the plain verifier is built and frozen, and its tests are copied to the audited one."""
        self._write(self.td / "verifiers" / PLAIN / "tests", text)
        self.build(PLAIN)
        assert self.run("freeze", str(self.td), PLAIN)[0] == 0
        shutil.copytree(self.td / "verifiers" / PLAIN / "tests", self.tests)
        self.build()

    def revise(self, text: str) -> None:
        """A revision: the tests are replaced in place (``rm -r tests && cp -r <reviser>/tests tests``) and rebuilt."""
        self._write(self.tests, text)
        self.build()

    def audit(self, *extra: str, save: str | None = None, contract: bool = True) -> tuple[int | str, dict]:
        code, out = self.run("audit", str(self.td), VID, *(["--contract", CONTRACT] if contract else []), *extra)
        if save is not None and code == 0:
            (self.dir / save).write_text(json.dumps(out, indent=2), encoding="utf-8")
        return code, out

    def iterate(self) -> dict:
        """The loop's audit of the tests as they are now, saved as the next iteration record."""
        name = f"it{len(self.saved)}.json"
        code, out = self.audit(save=name)
        assert code == 0, code
        self.saved.append(str(self.dir / name))
        return out

    def record(self, revisions: int | None = None, *files: str) -> tuple[int | str, dict]:
        """``audit --record N --previous ...``: by default N is the loop's revisions and the files are all its records."""
        n = len(self.saved) - 1 if revisions is None else revisions
        return self.audit("--record", str(n), "--previous", *(files or self.saved))

    def spec_record(self) -> AuditRecord:
        return load(self.spec_path, VerifierSpec).audit


@pytest.fixture()
def world(tmp_path, capsys, monkeypatch) -> World:
    return World(tmp_path, capsys, monkeypatch)


def ids(*names: str) -> list[str]:
    return [f"test_t.py::{n}" for n in names]


def refused(code: int | str, why: str) -> bool:
    return isinstance(code, str) and code.startswith(REFUSED) and why in code


BASE = [check("test_a", '_value("1") == 1'), check("test_b", '_value("2") == 2'), check("test_c", '_value("3") == 3')]
BASE_REQS = {"test_a": ["R1"], "test_b": ["R2"], "test_c": ["R1"]}


# --------------------------------------------------------------------------- every failing check is kept


def test_a_twelve_check_failure_is_recorded_in_full(world):
    """CS-01's case (D62): the reference fails 12 of 14 checks, in the iteration before the revision and after it. The
    findings the revisers are given are the procedure's own, which name five; the record keeps all twelve of each
    iteration in a structured field and says in its findings that the message names five of them."""
    names = [f"test_c{k:02d}" for k in range(1, 15)]
    reqs = {n: ["R1"] if k < 12 else ["R2"] for k, n in enumerate(names)}
    world.start(suite([check(n, f'_value("{k}") == {k}') for k, n in enumerate(names)], reqs))
    failing = set(names[:12])
    world.grader.failing = {"reference": failing, "noop-dev": set(names), "dev-attack-full_session-a1": {"test_c01"}}
    it0 = world.iterate()
    assert not it0["passed"]
    (ref_finding,) = [f for f in it0["findings"] if f["code"] == "reference_not_passing"]
    assert set(ref_finding) == {"code", "message", "candidate_id", "requirement_id"}  # what a reviser is given, unchanged
    assert ref_finding["message"] == f"{TID}-reference: task_failure; failed={ids(*names[:5])}"
    assert {r["candidate_id"]: r["failed_checks"] for r in it0["runs"]}[f"{TID}-reference"] == ids(*names[:12])
    assert [c["check_id"] for c in it0["tests"]["checks"]] == ids(*names)
    contract_sha = hashlib.sha256((world.td / "contracts" / f"{CONTRACT}.json").read_bytes()).hexdigest()
    assert it0["inputs"] == {"contract": CONTRACT, "contract_sha256": contract_sha, "audit_set": None, "only": None,
                             "reference_repeats": 3}
    assert it0["tests"]["scheme"] == audit.SNAPSHOT_SCHEME and datetime.fromisoformat(it0["graded_at"]).tzinfo is not None
    # the reviser keeps the tests faithful and adds one check the reference passes (D27); the reference still fails 12
    world.revise(suite([check(n, f'_value("{k}") == {k}') for k, n in enumerate(names)] + [check("test_c15", '_value("15") == 15')],
                       {**reqs, "test_c15": ["R1"]}))
    world.iterate()
    code, out = world.record()
    assert code == 0, code
    rec = world.spec_record()
    assert rec == AuditRecord.model_validate(out["record"]) and rec.iterations == 1 and rec.passed is False
    for it in rec.history:
        (run,) = [r for r in it.runs if r.candidate_id == f"{TID}-reference"]
        assert run.outcome == "task_failure" and run.failed_checks == ids(*names[:12])
        assert [r.failed_checks for r in run.repeats] == [ids(*names[:12])] * 3
    assert [len(it.checks) for it in rec.history] == [14, 15]
    assert rec.findings == [
        (f"reference_not_passing: {TID}-reference: task_failure; failed={ids(*names[:5])} "
         "(5 of 12 failing checks named; the record's history lists all 12)"),
        ("revision_changed_checks: revision 1 of 1 changed the checks: checks added (1): test_t.py::test_c15 [R1]; "
         "files changed: test_t.py")]
    assert out["findings"] == [f.model_dump() for f in rec.history[1].findings]  # the printed findings stay the procedure's
    raw = json.loads(world.spec_path.read_text(encoding="utf-8"))["audit"]
    assert list(raw) == ["procedure", "iterations", "passed", "findings", "dev_candidate_ids", "history", "revisions"]
    assert [h["graded_at"] for h in raw["history"]] == [it0["graded_at"], out["graded_at"]]


def test_a_record_without_revisions_keeps_the_failing_checks(world):
    names = [f"test_c{k:02d}" for k in range(1, 15)]
    world.start(suite([check(n, f'_value("{k}") == {k}') for k, n in enumerate(names)], {n: ["R1"] for n in names}))
    world.grader.failing = {"reference": set(names[2:]), "noop-dev": set(names)}
    world.iterate()
    code, _ = world.record()
    rec = world.spec_record()
    assert code == 0 and rec.iterations == 0 and rec.revisions == [] and [h.iteration for h in rec.history] == [0]
    assert {r.candidate_id: r.failed_checks for r in rec.history[0].runs}[f"{TID}-reference"] == ids(*names[2:])
    assert rec.findings[0].endswith("(5 of 12 failing checks named; the record's history lists all 12)")
    assert rec.history[0].content_sha256 == load(world.spec_path, VerifierSpec).content_sha256


def test_every_run_of_the_reference_is_kept(world):
    """The reference is graded three times, and a grade with repeats returns the checks of its last run only, so the
    audit grades it one run at a time. A check that fails only in an earlier run is named in the record; the outcome
    and the findings are those of one grade with three repeats."""
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"noop-dev": {"test_a"}, "dev-attack-full_session-a1": {"test_a"}}
    world.grader.runs = {"reference": [{"test_b"}, set(), set()] * 2}  # test_b fails in the first run only, twice
    it0 = world.iterate()
    (ref,) = [r for r in it0["runs"] if r["origin"] == "reference"]
    assert ref == {"candidate_id": f"{TID}-reference", "origin": "reference", "outcome": "unresolved", "failed_checks": [],
                   "repeats": [{"outcome": "task_failure", "failed_checks": ids("test_b")},
                               {"outcome": "pass", "failed_checks": []}, {"outcome": "pass", "failed_checks": []}]}
    assert [(f["code"], f["message"]) for f in it0["findings"]] == [
        ("reference_not_passing", f"{TID}-reference: unresolved; failed=[]"),
        ("infrastructure", f"{TID}-reference: unresolved: " + str(["repeated runs disagree: ['task_failure', 'pass', 'pass']"]))]
    assert all(r == 1 for _, r in world.grader.calls)
    code, _ = world.record()
    rec = world.spec_record()
    assert code == 0 and rec.findings[0] == (
        f"reference_not_passing: {TID}-reference: unresolved; failed=[] (failing in an earlier run but not in the last: "
        "test_t.py::test_b; the record's history lists the failing checks of each run)")
    assert [r.failed_checks for r in rec.history[0].runs[0].repeats] == [ids("test_b"), [], []]
    # every run fails, each on other checks: one outcome, the last run's checks in the message, the others in the record
    world.grader.runs = {"reference": [{"test_a"}, {"test_a", "test_c"}, {"test_b"}] * 2}
    world.iterate()
    code, _ = world.record(0, world.saved[-1])
    rec = world.spec_record()
    assert code == 0 and rec.findings[0] == (
        f"reference_not_passing: {TID}-reference: task_failure; failed={ids('test_b')} (failing in an earlier run but not "
        "in the last: test_t.py::test_a, test_t.py::test_c; the record's history lists the failing checks of each run)")


@pytest.mark.parametrize("script", [
    [{}, {}, {}],
    [{"b": "failed"}, {}, {}],  # a check fails in the first run only
    [{"a": "failed"}, {"a": "failed", "b": "failed"}, {"b": "failed"}],  # every run fails, on other checks
    [{"tamper": True}, {}, {"a": "error"}],  # a run's own diagnostics, and a setup error
    "patch rejected",
])
def test_runs_graded_one_at_a_time_combine_as_the_grader_combines_repeats(tmp_path, monkeypatch, script):
    """The real ``verify_candidate`` (its container run replaced): three grades of one run each, combined by the audit,
    give the outcome, the checks and the diagnostics of one grade with three repeats."""
    from tracecontract.sandbox import docker_runner as dr

    spec = VerifierSpec(verifier_id="v", task_id="t", condition=VerifierCondition.full_audited,
                        isolation=Isolation.process_separated, test_dir="tests", checks=[CheckSpec(check_id="t.py::a"),
                                                                                         CheckSpec(check_id="t.py::b")],
                        content_sha256="x")
    cand = Candidate(candidate_id="t-reference", task_id="t", origin=CandidateOrigin.reference, split=Split.dev, patch="",
                     patch_sha256=sha256_text(""), produced_by="fixture")
    queue: list[dict] = []

    def prepare(base_dir, patch, protected):
        removed = ["protected path change removed before grading: setup.py"]
        if script == "patch rejected":
            return None, [*removed, "patch rejected: a binary file"], "patch_rejected"
        ws = tmp_path / f"ws{len(list(tmp_path.glob('ws*')))}"
        ws.mkdir()
        return ws, removed, None

    def run_grader(image, *, workspace, mode, tests_dir=None, overlay_dir=None, repo_test_args=None,
                   candidate_pythonpath="/work", limits=None, nonce=None):
        run, nonce = queue.pop(0), "0" * 32
        tests = [{"nodeid": c.check_id, "outcome": run.get(c.check_id.split("::")[-1], "passed")} for c in spec.checks]
        results = {"nonce": nonce, "status": "completed", "harness_version": dr.HARNESS_VERSION, "tests": tests,
                   "tamper_events": [{"kind": "write"}] if run.get("tamper") else []}
        return dr.RawRun(0, False, results, "", "", 0.1), nonce

    monkeypatch.setattr(dr, "prepare_workspace", prepare)
    monkeypatch.setattr(dr, "run_grader", run_grader)

    def grade(repeats: int) -> VerificationResult:
        return dr.verify_candidate(image="img", base_dir=tmp_path, spec=spec, task_dir=tmp_path, candidate=cand,
                                   run_id="adhoc", repeats=repeats)

    queue[:] = [] if script == "patch rejected" else list(script)
    once = grade(3)
    queue[:] = [] if script == "patch rejected" else list(script)
    each = audit.combine_runs([grade(1) for _ in range(3)])
    assert (each.outcome, each.checks, each.diagnostics) == (once.outcome, once.checks, once.diagnostics)
    assert queue == [] and once.diagnostics[0] == "protected path change removed before grading: setup.py"
    if script == [{"tamper": True}, {}, {"a": "error"}]:
        assert once.diagnostics[1:] == ["[run 0] tamper_detected: write", "[run 2] verifier setup error",
                                        "repeated runs disagree: ['pass', 'pass', 'verifier_error']"]


# --------------------------------------------------------------------------- what each revision changed


def test_a_revision_that_adds_two_checks_and_widens_one_is_recorded_as_such(world):
    """CS-03's case (D62): the audit passes after a revision that added checks, which the old record did not show."""
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"noop-dev": {"test_a", "test_b", "test_c"}}  # the attack slips past every check
    it0 = world.iterate()
    assert [f["code"] for f in it0["findings"]] == ["false_acceptance_dev"]
    widened_b = check("test_b", '_value("2") == 2', '_value("20") == 20', '_value("-2") == -2')
    world.revise(suite([BASE[0], widened_b, BASE[2], check("test_d", '_value("4") == 4'), check("test_e", '_value("5") == 5')],
                       {**BASE_REQS, "test_d": ["R1"], "test_e": ["R2"]}))
    world.grader.failing = {"noop-dev": {"test_a", "test_b", "test_c", "test_d", "test_e"},
                            "dev-attack-full_session-a1": {"test_d"}}
    world.iterate()
    code, out = world.record()
    assert code == 0 and out["passed"] and out["findings"] == []
    rec = world.spec_record()
    (rev,) = rec.revisions
    assert (rev.revision, rev.added, rev.removed, rev.changed, rev.changed_indirectly) == (1, ids("test_d", "test_e"), [],
                                                                                         ids("test_b"), [])
    assert [(c.check_id, c.before, c.after) for c in rev.requirement_map] == [("test_t.py::test_d", None, ["R1"]),
                                                                              ("test_t.py::test_e", None, ["R2"])]
    assert rev.module_code == [] and [(f.name, f.change) for f in rev.files] == [("test_t.py", "changed")]
    assert rec.passed and [h.passed for h in rec.history] == [False, True]
    assert [f.code for f in rec.history[0].findings] == ["false_acceptance_dev"] and rec.history[1].findings == []
    assert rec.findings == [
        ("revision_changed_checks: revision 1 of 1 changed the checks, although no finding remains: checks added (2): "
         "test_t.py::test_d [R1], test_t.py::test_e [R2]; checks changed (1): test_t.py::test_b; files changed: test_t.py")]
    before, after = ({c.check_id: c for c in h.checks} for h in rec.history)
    assert before["test_t.py::test_a"] == after["test_t.py::test_a"] and before["test_t.py::test_b"].sha256 != after[
        "test_t.py::test_b"].sha256
    assert load(world.spec_path, VerifierSpec).model_dump_json(indent=2) + "\n" == world.spec_path.read_text(encoding="utf-8")


def test_an_unchanged_revision_records_no_change(world):
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"reference": {"test_b"}, "noop-dev": {"test_a"}, "dev-attack-full_session-a1": {"test_a"}}
    it0 = world.iterate()
    assert [f["code"] for f in it0["findings"]] == ["reference_not_passing"]
    world.revise(suite(BASE, BASE_REQS))  # the reviser handed the tests back as they were
    world.grader.failing.pop("reference")  # and the reference now passes: the tests did not change, the grade did
    world.iterate()
    code, _ = world.record()
    assert code == 0
    rec = world.spec_record()
    (rev,) = rec.revisions
    assert rev.model_dump() == {"revision": 1, "added": [], "removed": [], "changed": [], "changed_indirectly": [],
                                "requirement_map": [], "module_code": [], "files": []}
    assert rec.history[0].content_sha256 == rec.history[1].content_sha256 and rec.history[0].checks == rec.history[1].checks
    assert rec.findings == ["revision_unchanged: revision 1 of 1 changed no test file and no check"]


def test_changes_through_module_level_code_a_requirement_map_and_a_removed_check(world):
    """A widened helper changes the checks that use it although their own source is unchanged; a remapped check and a
    removed one are recorded; a revision that changes only the docstring changes the tests but no check."""
    helpers = 'CASES = [1, 2]\n\n\ndef _all(values):\n    return [_value(str(v)) for v in values]\n'
    uses = check("test_u", "_all(CASES) == CASES")
    world.start(suite([*BASE, uses], {**BASE_REQS, "test_u": ["R3"]}, helpers=helpers))
    world.grader.failing = {"reference": {"test_c"}, "noop-dev": {"test_a"}}
    world.iterate()
    world.revise(suite([BASE[0], BASE[1], uses], {"test_a": ["R1"], "test_b": ["R2", "R3"], "test_u": ["R3"]},
                       helpers=helpers.replace("[1, 2]", "[1, 2, 30]")))
    world.iterate()
    world.revise(suite([BASE[0], BASE[1], uses], {"test_a": ["R1"], "test_b": ["R2", "R3"], "test_u": ["R3"]},
                       helpers=helpers.replace("[1, 2]", "[1, 2, 30]"), doc="Synthetic verifier tests, revised."))
    world.grader.failing = {"noop-dev": {"test_a"}, "dev-attack-full_session-a1": {"test_a"}}
    world.iterate()
    code, _ = world.record()
    assert code == 0
    rec = world.spec_record()
    first, second = rec.revisions
    assert (first.added, first.removed, first.changed, first.changed_indirectly) == ([], ids("test_c"), [], ids("test_u"))
    assert [(c.check_id, c.before, c.after) for c in first.requirement_map] == [("test_t.py::test_b", ["R2"], ["R2", "R3"]),
                                                                                ("test_t.py::test_c", ["R1"], None)]
    assert [(c.name, c.change) for c in first.module_code] == [("test_t.py::CASES", "changed")]
    assert second.module_code[0].name == "test_t.py::__doc__" and not any(
        (second.added, second.removed, second.changed, second.changed_indirectly, second.requirement_map))
    assert rec.findings == [
        ("revision_changed_checks: revision 1 of 2 changed the checks, although no finding remains: checks removed (1): "
         "test_t.py::test_c (was [R1]); checks changed through the module-level code they use (1): test_t.py::test_u; "
         "requirement map changed: test_t.py::test_b [R2] -> [R2, R3]; module-level code changed: test_t.py::CASES; "
         "files changed: test_t.py"),
        ("revision_changed_tests: revision 2 of 2 changed the test files but no check function and no code the checks are "
         "known to depend on, although no finding remains: module-level code changed: test_t.py::__doc__; files changed: "
         "test_t.py")]


def test_checks_are_hashed_per_function(tmp_path):
    """Class methods and parametrised module-style ids (B1) are found; a class member that a method uses is module-level
    code of that method; an import of one more name changes no check; an id that names no function gets no hash."""
    td = tmp_path / "t"
    tests = td / "v" / "tests"
    tests.mkdir(parents=True)
    src = textwrap.dedent('''
        from tc_sandbox import run_python


        class TestK:
            LIMIT = 3

            def test_y(self):
                assert run_python("result = 1").value < self.LIMIT

            def test_z(self):
                assert run_python("result = 2").value == 2


        def test_x():
            assert run_python("result = 1").value == 1
        ''')
    (tests / "sub").mkdir()
    (tests / "sub" / "test_mod.py").write_text(src, encoding="utf-8")
    ids_ = ["sub.test_mod::test_x[1]", "sub.test_mod::test_x[a::b]", "sub/test_mod.py::TestK::test_y",
            "sub/test_mod.py::TestK::test_z", "missing.py::test_w", "sub.test_mod.TestK::test_z"]

    def snap() -> audit.SuiteSnapshot:
        spec = VerifierSpec(verifier_id="v", task_id="t", condition=VerifierCondition.repo_tests, isolation=Isolation.in_process,
                            test_dir="v/tests", checks=[CheckSpec(check_id=i) for i in ids_], content_sha256="x")
        return audit.suite_snapshot(spec, td)

    s0 = snap()
    by = {c.check_id: c for c in s0.checks}
    assert by[ids_[0]].sha256 == by[ids_[1]].sha256 is not None and by[ids_[4]].sha256 is None is by[ids_[4]].uses_sha256
    assert by[ids_[2]].sha256 != by[ids_[3]].sha256 and by[ids_[2]].uses_sha256 is not None
    assert by[ids_[5]] == by[ids_[3]].model_copy(update={"check_id": ids_[5]})  # unittest-style ids (B1) name the same method
    assert set(s0.module_code) == {"sub/test_mod.py::TestK", "sub/test_mod.py::run_python"}
    (tests / "sub" / "test_mod.py").write_text(src.replace("LIMIT = 3", "LIMIT = 4").replace(
        "import run_python", "import run_cmd, run_python"), encoding="utf-8")
    rev = audit.revision_changes(s0, snap(), 1)
    assert rev.changed == [] and rev.changed_indirectly == [ids_[2], ids_[3], ids_[5]]  # methods use their class's members
    assert [(c.name, c.change) for c in rev.module_code] == [("sub/test_mod.py::TestK", "changed"),
                                                             ("sub/test_mod.py::run_cmd", "added")]
    empty = audit.suite_snapshot(VerifierSpec(verifier_id="v", task_id="t", condition=VerifierCondition.repo_tests,
                                              isolation=Isolation.in_process, test_dir="nowhere", checks=[],
                                              content_sha256="x"), td)
    assert empty.files == {} and empty.checks == [] and empty.module_code == {}


def _snap(root: Path, files: dict[str, str]) -> audit.SuiteSnapshot:
    """The snapshot of a test dir holding ``files``, with the checks and requirement map that build-verifier finds."""
    tests = root / "v" / "tests"
    if tests.exists():
        shutil.rmtree(tests)
    for name, text in files.items():
        (tests / name).parent.mkdir(parents=True, exist_ok=True)
        (tests / name).write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    reqs = requirement_map_from_tests(tests)
    spec = VerifierSpec(verifier_id="v", task_id="t", condition=VerifierCondition.full_audited,
                        isolation=Isolation.process_separated, test_dir="v/tests", content_sha256="x",
                        checks=[CheckSpec(check_id=i, requirement_ids=reqs.get(i, [])) for i in discover_checks(tests)])
    return audit.suite_snapshot(spec, root)


PROBE = '''
    import json
    from pathlib import Path

    import pytest
    from tc_sandbox import run_python

    CHECK_REQUIREMENTS = {"test_a": ["R1"], "test_b": ["R2"]}

    EXPECTED = {"one": 1}
    CASES = [1]
    # extra


    def test_a(@ARGS):
        for v in EXPECTED.values():
            assert run_python(f"result = {v}").value == @EXPECT


    def test_b():
        for c in CASES:
            assert run_python(f"result = {c}").value == c
    '''


def probe(extra: str = "", args: str = "", expect: str = "v", decorator: str = "") -> str:
    text = PROBE.replace("    # extra", textwrap.indent(textwrap.dedent(extra).strip(), "    ") if extra else "")
    text = text.replace("@ARGS", args).replace("@EXPECT", expect)
    return text.replace("    def test_a(", f"    {decorator}\n    def test_a(") if decorator else text


FIXTURE = '''
    @pytest.fixture{options}
    def {name}():
        return {value}
    '''
CONFTEST = "import pytest\n\n\n@pytest.fixture\ndef expected():\n    return {value}\n"


@pytest.mark.parametrize("case, before, after, changed", [
    ("a statement that widens a list a check uses",
     {"test_t.py": probe("CASES.extend([2])")}, {"test_t.py": probe("CASES.extend([2, 3, 4])")}, ["test_b"]),
    ("an assignment to an item of a dict a check uses",
     {"test_t.py": probe('EXPECTED["two"] = 2')}, {"test_t.py": probe('EXPECTED["two"] = 3')}, ["test_a"]),
    ("a module-level loop that fills a list a check uses",
     {"test_t.py": probe("for k in range(2):\n    CASES.append(k)")},
     {"test_t.py": probe("for k in range(3):\n    CASES.append(k)")}, ["test_b"]),
    ("an autouse fixture",
     {"test_t.py": probe(FIXTURE.format(options="(autouse=True)", name="_env", value=1))},
     {"test_t.py": probe(FIXTURE.format(options="(autouse=True)", name="_env", value=2))}, ["test_a", "test_b"]),
    ("a module-level mark that is added",
     {"test_t.py": probe()}, {"test_t.py": probe('pytestmark = pytest.mark.skip(reason="later")')}, ["test_a", "test_b"]),
    ("a module-level setup function",
     {"test_t.py": probe("def setup_module():\n    CASES.sort()")},
     {"test_t.py": probe("def setup_module():\n    CASES.clear()")}, ["test_a", "test_b"]),
    ("a fixture named by usefixtures",
     {"test_t.py": probe(FIXTURE.format(options="", name="prepared", value=1), decorator='@pytest.mark.usefixtures("prepared")')},
     {"test_t.py": probe(FIXTURE.format(options="", name="prepared", value=5), decorator='@pytest.mark.usefixtures("prepared")')},
     ["test_a"]),
    ("a fixture requested by its name=",
     {"test_t.py": probe(FIXTURE.format(options='(name="expected")', name="_expected", value=1), args="expected",
                         expect="expected")},
     {"test_t.py": probe(FIXTURE.format(options='(name="expected")', name="_expected", value=2), args="expected",
                         expect="expected")}, ["test_a"]),
    ("a conftest.py fixture",
     {"test_t.py": probe(args="expected", expect="expected"), "conftest.py": CONFTEST.format(value=1)},
     {"test_t.py": probe(args="expected", expect="expected"), "conftest.py": CONFTEST.format(value=2)},
     ["test_a", "test_b"]),
])
def test_code_a_check_depends_on_without_naming_it_in_its_body(tmp_path, case, before, after, changed):
    """The code that changes what a check verifies although the check's function and the names it uses are unchanged:
    module-level statements that change those names, autouse fixtures, marks and setup functions, fixtures named by
    usefixtures or name=, and conftest.py. Each change is a change of the checks it applies to."""
    rev = audit.revision_changes(_snap(tmp_path, before), _snap(tmp_path, after), 1)
    assert (rev.changed, rev.changed_indirectly) == ([], ids(*changed)), case
    assert audit.revision_line(rev, 1, no_finding=False).startswith("revision_changed_checks: revision 1 of 1 changed the "
                                                                    "checks: checks changed through the module-level code")


def test_a_conftest_applies_to_the_checks_below_it(tmp_path):
    files = {"a/test_x.py": probe(), "b/test_y.py": probe(), "b/conftest.py": CONFTEST.format(value=1)}
    rev = audit.revision_changes(_snap(tmp_path, files), _snap(tmp_path, {**files, "b/conftest.py": CONFTEST.format(value=2)}), 1)
    assert rev.changed_indirectly == ["b/test_y.py::test_a", "b/test_y.py::test_b"]


def test_a_changed_data_file_is_not_called_no_change_of_the_checks(tmp_path):
    """A data file that a check reads is not followed; the line for a revision that changed only it does not say that no
    check changed, only that no check function and no code the checks are known to depend on did."""
    text = probe("CASES = json.loads((Path(__file__).parent / 'cases.json').read_text())")
    rev = audit.revision_changes(_snap(tmp_path, {"test_t.py": text, "cases.json": "[1]"}),
                                 _snap(tmp_path, {"test_t.py": text, "cases.json": "[1, 2]"}), 1)
    assert (rev.changed, rev.changed_indirectly, rev.module_code) == ([], [], [])
    assert audit.revision_line(rev, 1, no_finding=True) == (
        "revision_changed_tests: revision 1 of 1 changed the test files but no check function and no code the checks are "
        "known to depend on, although no finding remains: files changed: cases.json")


def test_the_snapshot_scheme_pins_its_hashes(tmp_path):
    """Records of one scheme are compared hash for hash, so a change to how suite_snapshot hashes the same tests (as a
    fix to it would make) must come with a new SNAPSHOT_SCHEME, which refuses the records of the old one: this digest
    of a fixed snapshot changes with any such change."""
    fixture = textwrap.dedent(FIXTURE.format(options="(autouse=True)", name="_env", value=1))
    snap = _snap(tmp_path, {"test_t.py": probe(fixture + "\nCASES.extend([2])"), "conftest.py": CONFTEST.format(value=1),
                            "cases.json": "[1]"})
    assert (snap.scheme, hashlib.sha256(snap.model_dump_json().encode()).hexdigest()) == (
        "suite-snapshot:v1", "e809d716b3e2910b999c6278a45c228274674b3f70eab22959f25329ada40251")


def test_names_bound_inside_a_statement_are_not_module_level(tmp_path):
    """The variables of a comprehension, and the names a nested function binds, are not module-level names: a check
    that only shares a local name with one of them does not use the statement (TABLE and its variables k and v). Nor
    does a block that defines a helper change the names that the helper's body uses, which runs only when called."""
    table = ('TABLE = {k: v for k, v in [("a", 1)]}\ntry:\n    def helper():\n        k = run_python("result = 0").value\n'
             '        return k\nexcept ImportError:\n    pass')
    text = probe(table).replace("for v in EXPECTED.values()", 'for v in [TABLE["a"]]').replace(
        "for c in CASES:", "for k in range(2):").replace('f"result = {c}").value == c', 'f"result = {k}").value == k')
    s0 = _snap(tmp_path, {"test_t.py": text})
    assert not any(k.endswith(("::k", "::v")) for k in s0.module_code), sorted(s0.module_code)
    rev = audit.revision_changes(s0, _snap(tmp_path, {"test_t.py": text.replace('("a", 1)', '("a", 1), ("b", 2)')}), 1)
    assert rev.changed_indirectly == ids("test_a") and [(c.name, c.change) for c in rev.module_code] == [
        ("test_t.py::TABLE", "changed")]
    rev = audit.revision_changes(s0, _snap(tmp_path, {"test_t.py": text.replace("result = 0", "result = 1")}), 1)
    assert rev.changed_indirectly == [] and len(rev.module_code) == 2  # the try block, removed and added under a new key


# --------------------------------------------------------------------------- the iteration records of the loop


def loop_of_two(world: World) -> list[str]:
    """Iteration 0 grades BASE; revision 1 adds test_d; revision 2 hands the tests back unchanged."""
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"noop-dev": {"test_a", "test_b", "test_c"}}  # the attack passes: false_acceptance_dev
    world.iterate()
    with_d = suite([*BASE, check("test_d", '_value("4") == 4')], {**BASE_REQS, "test_d": ["R1"]})
    world.revise(with_d)
    world.grader.failing["noop-dev"] |= {"test_d"}
    world.iterate()
    world.revise(with_d)
    world.iterate()
    return list(world.saved)


def test_the_record_takes_every_iteration_record_of_its_loop_in_order(world):
    """The loop leaves N + 1 records, and the record takes all of them, iteration 0 first; a list that is shifted,
    repeats a record, is out of order or drops iteration 0 is refused before anything is graded (review finding: the
    revisions were computed between the wrong snapshots)."""
    it0, it1, it2 = loop_of_two(world)
    copy = str(world.dir / "copy.json")
    shutil.copy(it1, copy)
    before, calls = world.spec_path.read_bytes(), len(world.grader.calls)
    for n, files, why in [
        (2, [it1, it2], "needs the 3 iteration record(s) of its audit loop, iteration 0 first"),  # files 1..N
        (2, [it0, it1], "2 given"),  # the N earlier records only
        (2, [it0, it1, it1], f"{it1} is given twice"),
        (2, [it0, it1, copy], f"{copy} was graded at the same time as {it1}, so one is a copy of the other"),
        (2, [it1, it0, it2], f"not in the order of the loop: {it0} (given as iteration 1) was graded before {it1}"),
        (1, [it1, it2], f"{it1} (iteration 0) graded other tests than a copy of {PLAIN}'s"),  # iteration 0 dropped
    ]:
        code, _ = world.record(n, *files)
        assert refused(code, why), (n, files, code)
    assert world.spec_path.read_bytes() == before and len(world.grader.calls) == calls
    code, _ = world.record()
    assert code == 0, code
    rec = world.spec_record()
    assert [(r.revision, r.added) for r in rec.revisions] == [(1, ids("test_d")), (2, [])]
    assert rec.findings == [
        f"false_acceptance_dev: {TID}-dev-attack-full_session-a1 (dev_attack) passed",
        ("revision_changed_checks: revision 1 of 2 changed the checks: checks added (1): test_t.py::test_d [R1]; files "
         "changed: test_t.py"),
        "revision_unchanged: revision 2 of 2 changed no test file and no check"]
    assert [h.graded_at for h in rec.history[:2]] == [json.loads(Path(p).read_text())["graded_at"] for p in (it0, it1)]


def test_an_iteration_that_passed_is_the_last_of_its_loop(world):
    """A revision follows only an audit that did not pass: a loop record before the last that passed is refused, and so
    is a record of revised tests whose iteration 0 is not the plain verifier's copy."""
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"noop-dev": {"test_a"}, "dev-attack-full_session-a1": {"test_a"}}
    assert world.iterate()["passed"]
    world.revise(suite([*BASE, check("test_d", '_value("4") == 4')], {**BASE_REQS, "test_d": ["R1"]}))
    world.iterate()
    code, _ = world.record()
    assert refused(code, f"{world.saved[0]} (iteration 0) passed, and a revision follows only an audit that did not pass")
    code, _ = world.record(0, world.saved[1])
    assert refused(code, f"{world.saved[1]} (iteration 0) graded other tests than a copy of {PLAIN}'s")
    code, _ = world.record(0, world.saved[0])
    assert refused(code, f"{world.saved[0]}, the last iteration record, graded other test files than this run")
    (world.td / "verifiers" / PLAIN / "spec.json").unlink()
    code, _ = world.record()
    assert refused(code, f"{VID} starts from a copy of {PLAIN}'s tests (protocol §4), and the task has no {PLAIN} spec")


def test_an_iteration_record_must_be_intact_and_graded_alike(world):
    """An earlier record's tests are checked against their own hashes and their scheme, and its inputs against this
    run's: an edited check list, edited files, another version of the snapshot, another candidate set, another audit
    set and a record graded without the contract are refused (review finding: taken on trust)."""
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"noop-dev": {"test_a"}}
    it0 = world.iterate()
    tests = it0["tests"]
    edited = {
        "checks": {**it0, "tests": {**tests, "checks": [c for c in tests["checks"] if not c["check_id"].endswith("test_c")]}},
        "files": {**it0, "tests": {**tests, "files": {**tests["files"], "data.json": "0" * 64}}},
        "scheme": {**it0, "tests": {**tests, "scheme": "suite-snapshot:v0"}},
        "unversioned": {**it0, "tests": {k: v for k, v in tests.items() if k != "scheme"}},
        "time": {**it0, "graded_at": "2026-11-22 10:00:00"},
    }
    whys = {"checks": "its check list does not give its checks_sha256; the record was edited",
            "files": "its files do not give its content_sha256; the record was edited",
            "scheme": "printed by another version of the audit's snapshot of the tests (suite-snapshot:v0, not "
                      f"{audit.SNAPSHOT_SCHEME})",
            "unversioned": "(unversioned, not", "time": "is not an ISO time with a time zone"}
    for name, rec in edited.items():
        p = world.dir / f"{name}.json"
        p.write_text(json.dumps(rec), encoding="utf-8")
        code, _ = world.record(0, str(p))
        assert refused(code, f"{p}") and whys[name] in code, (name, code)
    for name, extra, contract, why in [
        ("only", ["--only", f"{TID}-reference"], True, "was graded with another candidate selection (--only) than this run"),
        ("set", ["--audit-set", "fixture"], True, "with another audit set (--audit-set) than this run ('fixture' there, None here)"),
        ("nocontract", [], False, "with another contract (--contract) than this run (None there, 'full_session' here)"),
    ]:
        assert world.audit(*extra, save=f"{name}.json", contract=contract)[0] == 0
        code, _ = world.record(0, str(world.dir / f"{name}.json"))
        assert refused(code, why), (name, code)
    code, _ = world.audit("--only", f"{TID}-reference", "--record", "0", "--previous", str(world.dir / "only.json"))
    assert code == 0 and [h.runs[0].candidate_id for h in world.spec_record().history] == [f"{TID}-reference"]


def test_content_hash_of_a_record_is_that_of_its_files(tmp_path):
    """An iteration record's content_sha256 is recomputed from its files, in the order in which hash_test_dir walks a
    directory (by path parts, which is not the order of the path strings)."""
    tests = tmp_path / "v" / "tests"
    for name in ("a-c/test_x.py", "a/b.txt", "a.b", "A.py", "conftest.py", "_x/y/z.json"):
        (tests / name).parent.mkdir(parents=True, exist_ok=True)
        (tests / name).write_text(name, encoding="utf-8")
    spec = VerifierSpec(verifier_id="v", task_id="t", condition=VerifierCondition.full_audited,
                        isolation=Isolation.process_separated, test_dir="v/tests", checks=[], content_sha256="x")
    snap = audit.suite_snapshot(spec, tmp_path)
    assert snap.content_sha256 == hash_test_dir(tests) == audit._content_sha256(snap.files)
    assert sorted(snap.files) != sorted(snap.files, key=lambda r: r.split("/"))  # the two orders differ here


def test_a_regrade_that_differs_from_the_loop_is_recorded(world):
    """The record run grades the tests of the last iteration again; when its grade differs from the loop's, the record
    says so, since it keeps only its own grade of that iteration."""
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"reference": {"test_b"}, "noop-dev": {"test_a"}, "dev-attack-full_session-a1": {"test_a"}}
    world.iterate()
    world.revise(suite(BASE, BASE_REQS))
    world.grader.failing.pop("reference")
    assert world.iterate()["passed"]
    world.grader.failing["reference"] = {"test_c"}  # the same tests, graded again: the reference fails now
    code, _ = world.record()
    rec = world.spec_record()
    assert code == 0 and not rec.passed and [h.passed for h in rec.history] == [False, False]
    failed = "task_failure [test_t.py::test_c]"
    assert rec.findings == [
        f"reference_not_passing: {TID}-reference: task_failure; failed={ids('test_c')}",
        ("regrade_differs: this run graded the tests of iteration 1 again and differs from the loop's grade of them: "
         f"passed true in the loop, false now; {TID}-reference: pass [] (runs: pass [], pass [], pass []) in the loop, "
         f"{failed} (runs: {failed}, {failed}, {failed}) now"),
        "revision_unchanged: revision 1 of 1 changed no test file and no check"]


# --------------------------------------------------------------------------- refusals: nothing graded, nothing written


def test_a_record_is_refused_without_the_records_of_its_loop(world):
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"noop-dev": {"test_a"}}
    it0 = world.iterate()
    assert set(it0) >= {"passed", "findings", "runs", "dev_candidates", "procedure", "task_id", "verifier_id", "graded_at",
                        "inputs", "tests"}
    before, calls = world.spec_path.read_bytes(), len(world.grader.calls)
    prior = world.saved[0]
    old = world.dir / "old.json"  # a pilot iteration record (results/audits/): no tests, no procedure
    old.write_text(json.dumps({k: it0[k] for k in ("passed", "findings", "runs", "dev_candidates")}), encoding="utf-8")
    other = world.dir / "other.json"
    other.write_text(json.dumps({**it0, "verifier_id": "initial_audited"}), encoding="utf-8")
    cases = [(["--record", "1"], "needs the 2 iteration record(s) of its audit loop"),
             (["--record", "0"], "needs the 1 iteration record(s)"),
             (["--record", "2", "--previous", prior], "1 given"),
             (["--previous", prior], "read only with --record N"),
             (["--record", "-1"], "not -1"),
             (["--record", "0", "--previous", str(old)], "printed before audit records kept them"),
             (["--record", "0", "--previous", str(other)], f"of {TID} initial_audited, not of {TID} {VID}"),
             (["--record", "0", "--previous", str(world.dir / "absent.json")], "not a readable JSON file")]
    for argv, why in cases:
        code, _ = world.audit(*argv)
        assert refused(code, why), (argv, code)
    (world.tests / "test_t.py").write_text(suite(BASE[:2], BASE_REQS), encoding="utf-8")  # edited, but not rebuilt
    code, _ = world.record(0, prior)
    assert refused(code, "changed since its spec was built")
    assert world.spec_path.read_bytes() == before and len(world.grader.calls) == calls
    bad = world.dir / "bad.json"
    bad.write_text(json.dumps({**it0, "runs": "none"}), encoding="utf-8")
    with pytest.raises(audit.AuditRecordError, match="not an iteration record"):
        audit.read_iteration_record(bad, task_id=TID, verifier_id=VID)


def test_a_frozen_verifier_keeps_its_record(world):
    world.start(suite(BASE, BASE_REQS))
    world.grader.failing = {"noop-dev": {"test_a"}}
    world.iterate()
    assert world.record()[0] == 0
    assert world.run("freeze", str(world.td), VID)[0] == 0
    frozen = world.spec_path.read_bytes()
    code, _ = world.record()
    assert refused(code, "is frozen") and world.spec_path.read_bytes() == frozen
    assert world.audit()[0] == 0 and world.spec_path.read_bytes() == frozen  # an unrecorded audit still runs


# --------------------------------------------------------------------------- the schema


def test_recorded_specs_load_and_reserialise_byte_for_byte():
    """The new fields are optional and omitted while empty: every recorded spec, the pilot's audited ones included,
    re-serialises unchanged, and an audit record written the old way serialises as before."""
    paths = sorted(REPO.glob("tasks/*/verifiers/*/spec.json")) + sorted(REPO.glob("data/natural/tasks/*/verifiers/*/spec.json"))
    assert len([p for p in paths if p.parts[-5] == "tasks" and p.parts[-4].startswith("CS-")]) >= 32
    audited = 0
    for p in paths:
        raw = p.read_text(encoding="utf-8")
        spec = VerifierSpec.model_validate_json(raw)
        assert spec.model_dump_json(indent=2) + "\n" == raw, p
        if spec.audit is not None:
            audited += 1
            assert spec.audit.history == [] and spec.audit.revisions == []
    assert audited >= 8
    plain = AuditRecord(procedure="audit:v1", iterations=2, passed=True)
    assert list(json.loads(plain.model_dump_json())) == ["procedure", "iterations", "passed", "findings", "dev_candidate_ids"]


def test_an_audit_record_with_a_history_must_be_consistent():
    it = AuditIteration(iteration=0, passed=True, content_sha256="a" * 64, checks_sha256="b" * 64)
    assert AuditRecord(procedure="audit:v1", iterations=0, passed=True, history=[it]).history == [it]
    failed = it.model_copy(update={"passed": False, "graded_at": "2026-11-22T10:00:00+00:00"})
    later = it.model_copy(update={"iteration": 1, "graded_at": "2026-11-22T11:00:00+00:00"})
    rev = {"revision": 1}
    assert AuditRecord.model_validate({"procedure": "audit:v1", "iterations": 1, "passed": True, "history": [failed, later],
                                       "revisions": [rev]}).passed
    for kw, why in (({"iterations": 1, "history": [it]}, "iterations 0 to 1"),
                    ({"iterations": 0, "history": [it.model_copy(update={"iteration": 1})]}, "iterations 0 to 0"),
                    ({"iterations": 0, "passed": False, "history": [it]}, "passed differs"),
                    ({"iterations": 1, "history": [it, later], "revisions": [rev]}, "only the last iteration may pass"),
                    ({"iterations": 1, "history": [failed.model_copy(update={"graded_at": later.graded_at}),
                                                   later.model_copy(update={"graded_at": failed.graded_at})],
                      "revisions": [rev]}, "graded one after another")):
        with pytest.raises(ValueError, match=why):
            AuditRecord.model_validate({"procedure": "audit:v1", "passed": True, **kw})
