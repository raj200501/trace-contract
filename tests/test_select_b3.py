"""scripts/select_b3_tests.py: B3 keeps exactly the tests that pass on the reference and fail on the no-op.

A synthetic natural task holds a diff_derived verifier of eight tests in two files and the four S10 candidates. The
grade results are fixture JSONs in the form ``tracecontract grade`` prints, with check messages that must never be
copied into the selection record; some are made by ``docker_runner.verify_candidate`` itself, with the container
replaced, so that their diagnostics are those of real single and repeated grades.

When no test is kept, B3 is unavailable for the family and the verifier is taken out of the run: ``unavailable.json``
records it, ``task.json`` loses its entry and the spec is frozen where it lies, so build-verifier and freeze refuse it;
on any failure nothing changes, and a step killed part-way is finished by the same command. A selection beside
``unavailable.json`` is refused, and a dry run is refused wherever the run is. The pipeline tests then follow such a
family on: the whole pre-flight passes on a complete family and notes B3 as unavailable, before and after the ordinary
steps are tried on it (tests/test_preflight_natural.py's family), and evaluate grades every other verifier and no B3
for it, beside a family whose B3 keeps its test (tests/natural_task_layout.py, with Docker replaced by stubs). No
process starts here but git's: its ignore check, and in the pipeline tests the scratch repository's own git. Synthetic
data only; not research evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from natural_task_layout import NATURAL_TASKS, build_natural_task, init_git, use_layout
from tracecontract import cli
from tracecontract.analysis import analyze
from tracecontract.sandbox import docker_runner
from tracecontract.sandbox.docker_runner import HARNESS_VERSION
from tracecontract.schemas import (
    Candidate,
    CandidateOrigin,
    CheckResult,
    Outcome,
    Population,
    SnapshotSource,
    Split,
    TaskManifest,
    VerificationResult,
    VerifierCondition,
    VerifierSpec,
    sha256_text,
)
from tracecontract.store import dump, load, write_json
from tracecontract.verifier import (
    build_spec,
    discover_checks,
    generation_record,
    hash_test_dir,
    lint_process_separated,
    requirement_map_from_tests,
)

R = Path(__file__).resolve().parents[1]
T = "NP-99"
SECRET = "UPSTREAM-TRACEBACK-LINE"  # stands for check messages, which hold upstream code: never copied
BUILT = datetime(2026, 11, 20, tzinfo=UTC).timestamp()  # when the fixture's spec.json was written (its mtime)
B3 = textwrap.dedent('''\
    """B3 tests of a synthetic family."""
    import pytest
    from tc_sandbox import run_python

    CHECK_REQUIREMENTS = {
        "test_d1_new_flag": ["D1"],  # the flag that the reference adds
        "test_d2_old_behaviour": ["D2"],
        "test_d3_flaky": ["D3"],
        "test_d4_error_on_base": ["D4"],
    }


    def _code(expr):
        return f"import mod\\nresult = {expr}"


    def test_d1_new_flag():
        r = run_python(_code("mod.flag()"))
        assert r.ok and r.value is True


    # D2 already holds on the base
    @pytest.mark.slow
    def test_d2_old_behaviour():
        r = run_python(_code("mod.old()"))
        assert r.ok and r.value == 1


    def test_d3_flaky():
        r = run_python(_code("mod.sometimes()"))
        assert r.ok and r.value == 2


    def test_d4_error_on_base():
        r = run_python(_code("mod.raises_on_base()"))
        assert r.ok and r.value == 3
''')
B3_AFTER = textwrap.dedent('''\
    """B3 tests of a synthetic family."""
    import pytest
    from tc_sandbox import run_python

    CHECK_REQUIREMENTS = {
        "test_d1_new_flag": ["D1"],  # the flag that the reference adds
        "test_d4_error_on_base": ["D4"],
    }


    def _code(expr):
        return f"import mod\\nresult = {expr}"


    def test_d1_new_flag():
        r = run_python(_code("mod.flag()"))
        assert r.ok and r.value is True


    def test_d4_error_on_base():
        r = run_python(_code("mod.raises_on_base()"))
        assert r.ok and r.value == 3
''')
CLASSES = textwrap.dedent('''\
    from tc_sandbox import run_python

    CHECK_REQUIREMENTS = {"TestKept::test_k1": ["D5"], "TestKept::test_k2": ["D5"], "TestGone::test_g1": ["D6"], "test_top": ["D7"]}


    class TestKept:
        """One of its tests is kept."""

        def test_k1(self):
            r = run_python("result = 2 + 2")
            assert r.ok and r.value == 4

        def test_k2(self):
            r = run_python("result = 'a'.upper()")
            assert r.ok and r.value == "A"


    class TestGone:
        def test_g1(self):
            r = run_python("result = []")
            assert r.ok and r.value == []


    def test_top():
        r = run_python("result = len('abc')")
        assert r.ok and r.value == 3
''')
CLASSES_AFTER = textwrap.dedent('''\
    from tc_sandbox import run_python

    CHECK_REQUIREMENTS = {"TestKept::test_k1": ["D5"], "test_top": ["D7"]}


    class TestKept:
        """One of its tests is kept."""

        def test_k1(self):
            r = run_python("result = 2 + 2")
            assert r.ok and r.value == 4


    def test_top():
        r = run_python("result = len('abc')")
        assert r.ok and r.value == 3
''')
D1, D2, D3, D4 = (f"test_b3.py::test_d{i}_{n}" for i, n in
                  ((1, "new_flag"), (2, "old_behaviour"), (3, "flaky"), (4, "error_on_base")))
K1, K2, G1, TOP = ("test_classes.py::TestKept::test_k1", "test_classes.py::TestKept::test_k2",
                   "test_classes.py::TestGone::test_g1", "test_classes.py::test_top")
ALL = [D1, D2, D3, D4, K1, K2, G1, TOP]
REF = [{**dict.fromkeys(ALL, "passed"), K2: "skipped"},
       {**dict.fromkeys(ALL, "passed"), D3: "failed"},
       dict.fromkeys(ALL, "passed")]
NOOP = {D1: "failed", D2: "passed", D3: "failed", D4: "error", K1: "failed", K2: "failed", G1: "passed", TOP: "failed"}
KEPT = [D1, D4, K1, TOP]
NOOP_PASSES = dict.fromkeys(ALL, "passed")  # the development no-op passes every test: none is kept, B3 is unavailable
B1_SPEC, B3_SPEC = "verifiers/repo_tests/spec.json", "verifiers/diff_derived/spec.json"  # task.json's entries
_REAL_RUN = subprocess.run  # before any test replaces it


def _load():
    spec = importlib.util.spec_from_file_location("select_b3_tests", R / "scripts" / "select_b3_tests.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # its dataclasses resolve their annotations through the module
    spec.loader.exec_module(mod)
    return mod


sel = _load()


@pytest.fixture(autouse=True)
def no_containers(monkeypatch):
    real = subprocess.run

    def guarded(cmd, *a, **kw):
        if list(cmd[:1]) == ["git"] and "check-ignore" in cmd:
            return real(cmd, *a, **kw)
        raise AssertionError(f"no process may start in these tests: {list(cmd[:1])}")
    monkeypatch.setattr(subprocess, "run", guarded)


def _candidate(cid: str, origin: CandidateOrigin, split: Split, patch: str = "") -> Candidate:
    return Candidate(candidate_id=cid, task_id=T, origin=origin, split=split, patch=patch, patch_sha256=sha256_text(patch),
                     produced_by="fixture")


def _generation():
    """The generation record of the B3 generator's run (synthetic)."""
    return generation_record(run_id="wf_0a1b2c3d-4e5/diff-derived", config="config-A", prompt_sha256="ab" * 32,
                             started_at="2026-11-19T10:00:00Z", ended_at="2026-11-19T10:10:00Z", wall_s=600.0,
                             tool_calls=20, turns=12, run_record="build-session:subagents/workflows/x/agent-y.jsonl")


def world(root: Path, files: dict[str, str] | None = None, **spec_update) -> Path:
    """A natural task with the four S10 candidates and a built, unfrozen diff_derived verifier, registered in task.json
    after B1 as build-verifier registers it; returns its tests dir. Its spec.json was written at ``BUILT``, before every
    grade of these tests."""
    td = root / "tasks" / T
    tests = td / "verifiers" / "diff_derived" / "tests"
    tests.mkdir(parents=True)
    for name, text in (files or {"test_b3.py": B3, "test_classes.py": CLASSES}).items():
        (tests / name).write_text(text, encoding="utf-8")
    patch = "diff --git a/mod.py b/mod.py\n--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-x = 0\n+x = 1\n"
    cands = [_candidate(f"{T}-reference", CandidateOrigin.reference, Split.dev, patch),
             _candidate(f"{T}-pre-review", CandidateOrigin.natural_pre_review, Split.eval, patch.replace("1\n", "2\n")),
             _candidate(f"{T}-noop-dev", CandidateOrigin.noop, Split.dev),
             _candidate(f"{T}-noop-eval", CandidateOrigin.noop, Split.eval)]
    for c in cands:
        dump(c, td / "candidates" / f"{c.candidate_id}.json")
    dump(TaskManifest(task_id=T, family_id=T, population=Population.natural_pr_review, status="pending_review",
                      provenance="provenance.json", snapshot_source=SnapshotSource(repo_url="https://example.invalid/x",
                                                                                   commit="0" * 40),
                      env_requirements=[], verifiers=[B1_SPEC, B3_SPEC],
                      candidates=[f"candidates/{c.candidate_id}.json" for c in cands]), td / "task.json")
    spec = build_spec(verifier_id="diff_derived", task_id=T, condition=VerifierCondition.diff_derived, test_dir=tests,
                      task_dir=td, requirement_map=requirement_map_from_tests(tests), generation=_generation(),
                      require_generation=True)
    path = td / "verifiers" / "diff_derived" / "spec.json"
    dump(spec.model_copy(update=spec_update), path)
    os.utime(path, (BUILT, BUILT))
    return tests


def _outcome(statuses: dict[str, str]) -> Outcome:  # as docker_runner.aggregate decides
    values = set(statuses.values())
    if not statuses or values & {"missing", "error"} or ("skipped" in values and "failed" not in values):
        return Outcome.verifier_error
    return Outcome.task_failure if "failed" in values else Outcome.passed


def grade(path: Path, candidate: str, statuses: dict[str, str], *, n: int = 0, task: str = T, **update) -> Path:
    """A grade result as ``tracecontract grade`` prints it (of task ``task``'s diff_derived verifier)."""
    checks = [CheckResult(check_id=c, status=s, duration_s=0.1, message="" if s == "passed" else f"{SECRET} {c}")
              for c, s in statuses.items()]
    outcome = update.pop("outcome", _outcome(statuses))
    res = VerificationResult(run_id="adhoc", task_id=task, verifier_id="diff_derived", candidate_id=candidate,
                             outcome=outcome, reward=1.0 if outcome == Outcome.passed else 0.0, checks=checks,
                             diagnostics=update.pop("diagnostics", [f"[run 0] {SECRET}"]),
                             started_at=f"2026-11-22T11:0{n}:00+00:00", finished_at=f"2026-11-22T11:0{n}:30+00:00",
                             wall_s=30.0 + n, harness_version=HARNESS_VERSION, log_sha256=hashlib.sha256(
                                 f"log {n}".encode()).hexdigest())
    path.write_text(json.dumps(res.model_copy(update=update).model_dump(mode="json"), indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def real_grade(monkeypatch, tmp_path: Path, tests: Path, candidate: str, runs: list, *, name: str) -> Path:
    """A grade made as ``tracecontract grade --repeats len(runs)`` makes it: ``docker_runner.verify_candidate`` with
    the container replaced. Each run is the statuses the trusted runner reports, "timeout" (the container exceeded
    its limit) or "no results" (it was killed before writing them)."""
    td = tests.parents[2]
    todo = list(runs)

    def prepare_workspace(base_dir, patch, protected):
        return Path(tempfile.mkdtemp(dir=tmp_path)), [], None  # verify_candidate removes it

    def run_grader(image, **kw):
        nonce, run, k = "0" * 32, todo.pop(0), len(runs) - len(todo)
        out = f"grade {name} run {k}\n{SECRET}"
        if run == "timeout":
            return docker_runner.RawRun(None, True, None, out, "", 900.0), nonce
        if run == "no results":
            return docker_runner.RawRun(137, False, None, out, "", 3.0), nonce
        reported = [{"nodeid": c, "outcome": s, "duration": 0.1, "longrepr": "" if s == "passed" else SECRET}
                    for c, s in run.items()]
        results = {"nonce": nonce, "status": "completed", "harness_version": HARNESS_VERSION, "tests": reported,
                   "collect_errors": [], "tamper_events": []}
        return docker_runner.RawRun(0, False, results, out, "", 2.0), nonce

    monkeypatch.setattr(docker_runner, "prepare_workspace", prepare_workspace)
    monkeypatch.setattr(docker_runner, "run_grader", run_grader)
    res = docker_runner.verify_candidate(image="tc-env:0123456789abcdef", base_dir=tmp_path,
                                         spec=load(tests.parent / "spec.json", VerifierSpec), task_dir=td,
                                         candidate=load(td / "candidates" / f"{candidate}.json", Candidate),
                                         run_id="adhoc", repeats=len(runs))
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(res.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
    return path


def grades(root: Path, ref=REF, noop=NOOP) -> list[str]:
    files = [str(grade(root / f"b3-ref-{n}.json", f"{T}-reference", st, n=n)) for n, st in enumerate(ref, 1)]
    return ["--reference", *files, "--noop", str(grade(root / "b3-noop.json", f"{T}-noop-dev", noop, n=5))]


def run(capsys, *argv) -> tuple[int, dict | None, str]:
    code = sel.main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, (json.loads(out.out) if out.out.strip() else None), out.err


def _state(tests: Path) -> tuple[str, bool]:
    return hash_test_dir(tests), (tests.parent / "selection.json").exists()


def _files(task_dir: Path) -> dict[str, bytes]:
    """Every file of the task directory, by its path there: what a refused or undone step must leave as it was."""
    return {p.relative_to(task_dir).as_posix(): p.read_bytes() for p in sorted(task_dir.rglob("*")) if p.is_file()}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- selection


def test_the_kept_tests_are_exactly_those_that_pass_on_the_reference_and_fail_on_the_noop(tmp_path, capsys):
    tests = world(tmp_path)
    before = hash_test_dir(tests)
    mapping = requirement_map_from_tests(tests)
    task_bytes = (tests.parents[2] / "task.json").read_bytes()
    code, summary, _ = run(capsys, tests, *grades(tmp_path))
    assert code == 0 and summary["kept"] == 4 and summary["removed"] == 4 and summary["b3_available"] is True
    assert summary["withdrawn"] is False and summary["resumed"] is False
    assert (tests.parents[2] / "task.json").read_bytes() == task_bytes  # the verifier stays registered, as it was
    assert discover_checks(tests) == KEPT
    # removed: the functions with their decorators, attached comments and blank lines, an emptied class, their keys;
    # everything else stays as written (the comment inside the requirement dict included)
    assert (tests / "test_b3.py").read_text() == B3_AFTER
    assert (tests / "test_classes.py").read_text() == CLASSES_AFTER
    assert requirement_map_from_tests(tests) == {c: mapping[c] for c in KEPT}
    assert lint_process_separated(tests) == []
    record = json.loads((tests.parent / "selection.json").read_text())
    assert record["schema"] == "b3-selection:v2"
    assert record["kept"] == KEPT and record["removed"] == [D2, D3, K2, G1]
    assert record["applied"] is True and record["b3_available"] is True and record["grades_without_statuses"] == []
    assert record["withdrawn"] is False and record["unavailable_record"] is None and record["next"] == sel.NEXT_KEPT
    assert record["tests_sha256_before"] == before and record["tests_sha256_after"] == hash_test_dir(tests)
    assert (record["reference_candidate"], record["noop_candidate"]) == (f"{T}-reference", f"{T}-noop-dev")
    why = {r["check_id"]: r["why"] for r in record["tests"]}
    assert why[D2] == why[G1] == ["not failed (or error) on the development no-op"]
    assert why[D3] == why[K2] == ["not passed in every reference grade"] and why[D4] == []
    rows = {r["check_id"]: r for r in record["tests"]}
    assert rows[K2]["reference"] == ["skipped", "passed", "passed"] and rows[D4]["noop"] == "error"
    assert [g["role"] for g in record["grades"]] == ["reference"] * 3 + ["noop"]
    assert all(len(g["file_sha256"]) == 64 for g in record["grades"])
    assert SECRET not in json.dumps(record)  # no check message or diagnostic is copied
    # The record cites no decision-log number: the rule is stated in full, and the entry that fixes the recipe may be
    # numbered otherwise.
    assert "D61" not in json.dumps(record) and "decision" not in record["rule"]
    # Nothing is left beside the spec but the record: the edits went through temporary files and renames.
    assert sorted(p.name for p in tests.parent.iterdir()) == ["selection.json", "spec.json", "tests"]
    # The host then rebuilds the spec: it holds the kept checks with their requirement ids.
    td = tests.parents[2]
    old = load(tests.parent / "spec.json", VerifierSpec)
    new = build_spec(verifier_id="diff_derived", task_id=T, condition=VerifierCondition.diff_derived, test_dir=tests,
                     task_dir=td, requirement_map=requirement_map_from_tests(tests), generation=old.generation)
    assert [c.check_id for c in new.checks] == KEPT
    assert {c.check_id: c.requirement_ids for c in new.checks} == {c.check_id: c.requirement_ids for c in old.checks
                                                                  if c.check_id in KEPT}
    # A second selection is refused: the record exists (and the spec no longer matches the tests).
    code, _, err = run(capsys, tests, *grades(tmp_path))
    assert code == 2 and "already made" in err


def test_without_a_kept_test_b3_is_unavailable_and_the_verifier_is_taken_out_of_the_run(tmp_path, capsys):
    tests = world(tmp_path)
    vdir, td = tests.parent, tests.parents[2]
    before = hash_test_dir(tests)
    spec_bytes, task_bytes = (vdir / "spec.json").read_bytes(), (td / "task.json").read_bytes()
    code, summary, err = run(capsys, tests, *grades(tmp_path, noop=NOOP_PASSES))
    assert code == 3 and summary["kept"] == 0 and summary["b3_available"] is False and summary["applied"] is False
    assert summary["withdrawn"] is True and summary["resumed"] is False
    assert "B3 is unavailable" in err and "diff_derived was taken out of the run" in err
    assert "build-verifier and freeze refuse it" in err and "nothing is left to do for B3" in err
    # The tests stay as they were, so that no verifier without checks is made. task.json lost its entry and nothing else
    # (written as build-verifier writes it), and no temporary file is left.
    assert hash_test_dir(tests) == before
    assert sorted(p.name for p in vdir.iterdir()) == ["selection.json", "spec.json", "tests", "unavailable.json"]
    old = TaskManifest.model_validate_json(task_bytes)
    assert old.verifiers == [B1_SPEC, B3_SPEC]
    rest = old.model_copy(update={"verifiers": [B1_SPEC]})
    assert (td / "task.json").read_text() == rest.model_dump_json(indent=2) + "\n"
    assert sorted(p.name for p in td.iterdir()) == ["candidates", "task.json", "verifiers"]
    # The selection record, which the pre-flight reads: b3_available false.
    selection = json.loads((vdir / "selection.json").read_text())
    assert selection["schema"] == "b3-selection:v2"
    assert selection["kept"] == [] and selection["removed"] == ALL and selection["condition"] == "diff_derived"
    assert selection["b3_available"] is False and selection["applied"] is False and selection["withdrawn"] is True
    assert selection["unavailable_record"] == "verifiers/diff_derived/unavailable.json"
    assert selection["next"] == sel.NEXT_UNAVAILABLE and "D61" not in selection["next"]
    # The spec stays where every spec is, frozen as `tracecontract freeze` freezes it, at the selection's time, with the
    # generator's generation record: its cost is found where every verifier's is (verifiers/*/spec.json).
    graded, frozen = VerifierSpec.model_validate_json(spec_bytes), load(vdir / "spec.json", VerifierSpec)
    assert frozen.frozen is True and frozen.frozen_at == selection["selected_at"] and frozen.checks_sha256 is not None
    assert frozen.model_copy(update={"frozen": False, "frozen_at": None, "checks_sha256": None}) == graded
    assert frozen.generation is not None and frozen.generation.run_id == "wf_0a1b2c3d-4e5/diff-derived"
    assert vdir / "spec.json" in td.glob("verifiers/*/spec.json")
    # unavailable.json: why, the sha256 of the selection's inputs, the time and what was taken out.
    rec = json.loads((vdir / "unavailable.json").read_text())
    assert {k: rec[k] for k in ("schema", "task_id", "verifier_id", "condition", "available", "rule", "recorded_by")} == {
        "schema": "verifier-unavailable:v1", "task_id": T, "verifier_id": "diff_derived", "condition": "diff_derived",
        "available": False, "rule": sel.RULE, "recorded_by": "scripts/select_b3_tests.py"}
    assert rec["reason"] == ("the B3 selection keeps no test: of the 8 diff-derived tests, 2 did not pass in every "
                             "reference grade and 8 did not fail (or error) on the development no-op")
    assert rec["recorded_at"] == selection["selected_at"]
    assert rec["selection"] == {"record": "verifiers/diff_derived/selection.json",
                                "sha256": _sha((vdir / "selection.json").read_bytes())}
    assert rec["inputs"] == {"grades": [{k: g[k] for k in ("role", "n", "file_sha256")} for g in selection["grades"]],
                             "tests_dir": "verifiers/diff_derived/tests", "tests_sha256": before,
                             "spec_sha256": _sha(spec_bytes), "task_json_sha256": _sha(task_bytes)}
    assert rec["taken_out"] == {"task_json_entries": [B3_SPEC], "task_json_sha256_after": _sha((td / "task.json").read_bytes()),
                                "spec": B3_SPEC, "spec_frozen_at": selection["selected_at"],
                                "spec_sha256_after": _sha((vdir / "spec.json").read_bytes())}
    assert SECRET not in json.dumps(rec) + json.dumps(selection)  # no check message or diagnostic is copied
    assert "D61" not in json.dumps(rec) and "decision" not in rec["reason"]
    # The ordinary steps cannot bring the verifier back (the reviewer's case): build-verifier and freeze refuse it, as a
    # frozen verifier, and leave every file as it was.
    files = _files(td)
    gen = tmp_path / "gen.json"
    gen.write_text(_generation().model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(SystemExit, match="build-verifier refused: diff_derived is frozen"):
        cli.main(["build-verifier", str(td), "diff_derived", "--condition", "diff_derived", "--generation-record", str(gen)])
    with pytest.raises(ValueError, match="already frozen"):
        cli.main(["freeze", str(td), "diff_derived"])
    capsys.readouterr()
    assert _files(td) == files
    # A second selection, or its dry run, is refused: B3 was taken out of the run.
    for dry in ((), ("--dry-run",)):
        code, _, err = run(capsys, tests, *grades(tmp_path, noop=NOOP_PASSES), *dry)
        assert code == 2 and "B3 was already taken out of the run" in err and "nothing is left to select" in err
    assert _files(td) == files
    # frozen against the script's advice while still registered: refused, and the message says what is wrong
    dump(old, td / "task.json")
    code, _, err = run(capsys, tests, *grades(tmp_path, noop=NOOP_PASSES))
    assert code == 2 and f"task.json registers {B3_SPEC} and that spec is frozen" in err


def test_a_dry_run_without_a_kept_test_takes_nothing_out(tmp_path, capsys):
    tests = world(tmp_path)
    td = tests.parents[2]
    files, written = _files(td), (tests.parent / "spec.json").stat().st_mtime_ns
    code, summary, err = run(capsys, tests, *grades(tmp_path, noop=NOOP_PASSES), "--dry-run")
    assert code == 3 and summary["dry_run"] is True and summary["b3_available"] is False and summary["withdrawn"] is False
    assert summary["next"] == sel.NEXT_UNAVAILABLE_DRY_RUN and "without --dry-run, diff_derived is taken out" in err
    assert _files(td) == files and (tests.parent / "spec.json").stat().st_mtime_ns == written


def test_when_every_test_qualifies_nothing_is_edited(tmp_path, capsys):
    tests = world(tmp_path)
    before = (tests / "test_b3.py").read_bytes(), (tests / "test_classes.py").read_bytes()
    code, summary, _ = run(capsys, tests, *grades(tmp_path, ref=[dict.fromkeys(ALL, "passed")] * 3,
                                                  noop=dict.fromkeys(ALL, "failed")))
    assert code == 0 and summary["removed"] == 0
    assert ((tests / "test_b3.py").read_bytes(), (tests / "test_classes.py").read_bytes()) == before


def test_a_dry_run_writes_nothing(tmp_path, capsys):
    tests = world(tmp_path)
    state = _state(tests)
    code, summary, _ = run(capsys, tests, *grades(tmp_path), "--dry-run")
    assert code == 0 and summary["dry_run"] is True and summary["applied"] is False
    assert [r["check_id"] for r in summary["tests"] if r["kept"]] == KEPT
    assert _state(tests) == state


def test_entries_sharing_lines_make_the_dict_be_rewritten_from_its_kept_entries(tmp_path, capsys):
    shared = B3.replace('    "test_d2_old_behaviour": ["D2"],\n    "test_d3_flaky": ["D3"],\n',
                        '    "test_d2_old_behaviour": ["D2"], "test_d3_flaky": ["D3"],\n')
    tests = world(tmp_path, {"test_b3.py": shared, "test_classes.py": CLASSES})
    code, _, _ = run(capsys, tests, *grades(tmp_path))
    assert code == 0
    text = (tests / "test_b3.py").read_text()
    assert 'CHECK_REQUIREMENTS = {\n    "test_d1_new_flag": ["D1"],\n    "test_d4_error_on_base": ["D4"],\n}\n' in text
    assert text.split("CHECK_REQUIREMENTS")[0] == B3_AFTER.split("CHECK_REQUIREMENTS")[0]
    assert requirement_map_from_tests(tests) == {D1: ["D1"], D4: ["D4"], K1: ["D5"], TOP: ["D7"]}


def test_an_entry_whose_comma_is_on_the_next_line_makes_the_dict_be_rewritten(tmp_path, capsys):
    """Removing that entry's line would leave a lone comma, which does not parse: the dict is rewritten instead."""
    shifted = B3.replace('    "test_d2_old_behaviour": ["D2"],\n', '    "test_d2_old_behaviour": ["D2"]\n    ,\n')
    tests = world(tmp_path, {"test_b3.py": shifted, "test_classes.py": CLASSES})
    code, _, err = run(capsys, tests, *grades(tmp_path))
    assert code == 0, err
    text = (tests / "test_b3.py").read_text()
    assert 'CHECK_REQUIREMENTS = {\n    "test_d1_new_flag": ["D1"],\n    "test_d4_error_on_base": ["D4"],\n}\n' in text
    assert requirement_map_from_tests(tests) == {D1: ["D1"], D4: ["D4"], K1: ["D5"], TOP: ["D7"]}


def test_a_string_between_tests_is_never_cut(tmp_path, capsys):
    """A line that looks like a comment but closes a string above a removed test stays."""
    tricky = B3.replace("\n\n# D2 already holds on the base\n", '\n\nNOTE = """\n# not a comment"""\n')
    tests = world(tmp_path, {"test_b3.py": tricky, "test_classes.py": CLASSES})
    assert run(capsys, tests, *grades(tmp_path))[0] == 0
    assert 'NOTE = """\n# not a comment"""\n' in (tests / "test_b3.py").read_text()


# --------------------------------------------------------------------------- writing


def test_a_failed_write_puts_every_file_back_and_leaves_no_record(tmp_path, capsys, monkeypatch):
    """The disk fills while the second test file is written: the first is put back, no record is left, and a later
    selection works."""
    tests = world(tmp_path)
    before = {p.name: p.read_bytes() for p in tests.iterdir()}
    real, calls = sel._replace, []

    def full_disk(path, data, scratch):
        calls.append(path.name)
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        real(path, data, scratch)
    monkeypatch.setattr(sel, "_replace", full_disk, raising=False)
    code, out, err = run(capsys, tests, *grades(tmp_path))
    assert code == 2 and out is None, err
    assert "writing failed (OSError" in err and "put back as it was" in err and "no selection record was written" in err
    assert calls == ["test_b3.py", "test_classes.py", "test_b3.py"]  # written, failed, put back
    assert {p.name: p.read_bytes() for p in tests.iterdir()} == before
    assert sorted(p.name for p in tests.parent.iterdir()) == ["spec.json", "tests"]  # no record, no temporary file
    monkeypatch.setattr(sel, "_replace", real)
    assert run(capsys, tests, *grades(tmp_path))[0] == 0


def test_written_tests_that_do_not_hash_as_checked_are_put_back(tmp_path, capsys, monkeypatch):
    """A file appears in the tests while they are written (a concurrent change): the edited files are put back and no
    record is written; the change itself is not undone, so a later run refuses the changed tests."""
    tests = world(tmp_path)
    before = {name: (tests / name).read_bytes() for name in ("test_b3.py", "test_classes.py")}
    real = sel._replace

    def concurrent(path, data, scratch):
        real(path, data, scratch)
        (tests / "test_other.py").write_text("x = 1\n")
    monkeypatch.setattr(sel, "_replace", concurrent, raising=False)
    code, out, err = run(capsys, tests, *grades(tmp_path))
    assert code == 2 and out is None and "do not hash as they did" in err and "put back as it was" in err
    assert {name: (tests / name).read_bytes() for name in before} == before
    assert not (tests.parent / "selection.json").exists()
    monkeypatch.setattr(sel, "_replace", real)
    assert "changed since the spec was built" in run(capsys, tests, *grades(tmp_path))[2]


def test_a_failed_withdrawal_puts_task_json_and_the_spec_back_and_leaves_no_record(tmp_path, capsys, monkeypatch):
    """The disk fills while the second record, task.json or the frozen spec is written: task.json and spec.json are as
    they were (the spec with its times, which date its build for the grades), neither record nor a temporary file is
    left, and a later selection with the same grades takes the verifier out."""
    real = {"_claim": sel._claim, "_replace": sel._replace}

    def full_disk_at(name: str):
        """The writer of ``name`` (``_claim`` for a record, ``_replace`` for task.json and the spec), failing there."""
        attr = "_claim" if name == "unavailable.json" else "_replace"

        def fake(path, *rest):
            if path.name == name:
                raise OSError(28, "No space left on device")
            real[attr](path, *rest)
        return attr, fake

    for name in ("unavailable.json", "task.json", "spec.json"):
        tests = world(tmp_path / name)
        td, spec = tests.parents[2], tests.parent / "spec.json"
        files, written = _files(td), spec.stat().st_mtime_ns
        attr, fake = full_disk_at(name)
        monkeypatch.setattr(sel, attr, fake)
        code, out, err = run(capsys, tests, *grades(tmp_path / name, noop=NOOP_PASSES))
        assert code == 2 and out is None, err
        assert "writing failed (OSError" in err and "task.json and spec.json are as they were" in err, err
        assert "no record was written" in err
        assert _files(td) == files and spec.stat().st_mtime_ns == written, name
        assert not [p for p in td.rglob(".b3_select_*")], name  # no temporary file is left
        monkeypatch.setattr(sel, attr, real[attr])
        assert run(capsys, tests, *grades(tmp_path / name, noop=NOOP_PASSES))[0] == 3
        assert load(spec, VerifierSpec).frozen and (tests.parent / "unavailable.json").is_file()
        assert load(td / "task.json", TaskManifest).verifiers == [B1_SPEC]


def test_a_withdrawal_whose_files_changed_meanwhile_takes_nothing_out(tmp_path):
    """task.json, the spec or the tests changed between the reading and the writing (a concurrent change): nothing is
    taken out and no record is left; the change itself stays."""
    changes = {
        "task.json": lambda td, tests: (td / "task.json").write_text(
            (td / "task.json").read_text(encoding="utf-8") + "\n", encoding="utf-8"),
        "spec.json": lambda td, tests: (tests.parent / "spec.json").write_text(
            (tests.parent / "spec.json").read_text(encoding="utf-8") + "\n", encoding="utf-8"),
        "the tests": lambda td, tests: (tests / "test_new.py").write_text("x = 1\n", encoding="utf-8"),
    }
    for n, (what, change) in enumerate(changes.items()):
        tests = world(tmp_path / str(n))
        td, target = tests.parents[2], tests.parent / "selection.json"
        v = sel.load_verifier(tests)
        w = sel.plan_withdrawal(v, target, target, "2026-11-22T12:00:00+00:00")
        change(td, tests)
        files = _files(td)
        with pytest.raises(sel.WrittenError, match="changed while the selection ran.*as they were; no record was written"):
            sel.withdraw(v, w, target, "{}\n", "{}\n")
        assert _files(td) == files, what


def test_an_interrupted_withdrawal_is_finished_by_running_the_same_command_again(tmp_path, capsys):
    """A withdrawal killed part-way (records written; task.json not yet rewritten, or the spec not yet frozen) is not
    refused as a selection already made: the same command finishes it, ending byte for byte where an uninterrupted step
    ends, and its dry run says so and writes nothing. Other grades cannot finish it."""
    tests = world(tmp_path)
    vdir, td = tests.parent, tests.parents[2]
    args = grades(tmp_path, noop=NOOP_PASSES)
    task_bytes, spec_bytes = (td / "task.json").read_bytes(), (vdir / "spec.json").read_bytes()
    assert run(capsys, tests, *args)[0] == 3
    done = _files(td)

    def interrupted(*, registered: bool, unavailable: bool) -> None:
        """The state of a step killed after its records (or the first of them), before the spec was frozen: task.json
        as it was (``registered``) or rewritten, and the spec as graded, never rewritten before the last step."""
        (td / "task.json").write_bytes(task_bytes if registered else done["task.json"])
        (vdir / "spec.json").write_bytes(spec_bytes)
        os.utime(vdir / "spec.json", (BUILT, BUILT))
        if not unavailable:
            (vdir / "unavailable.json").unlink()

    for k, state in enumerate([dict(registered=True, unavailable=False), dict(registered=True, unavailable=True),
                               dict(registered=False, unavailable=True)]):
        interrupted(**state)
        before = _files(td)
        # still registered and unfrozen, or unregistered and unfrozen: not what the records say yet
        assert load(vdir / "spec.json", VerifierSpec).frozen is False
        assert (B3_SPEC in load(td / "task.json", TaskManifest).verifiers) is state["registered"]
        code, summary, err = run(capsys, tests, *args, "--dry-run")
        assert code == 3 and summary["resumed"] is True and summary["withdrawn"] is False, err
        assert "stopped part-way" in err and _files(td) == before, k
        code, summary, err = run(capsys, tests, *args)
        assert code == 3 and summary["resumed"] is True and summary["withdrawn"] is True, err
        assert "finished the withdrawal" in err
        assert _files(td) == done, k  # the records, task.json and the frozen spec, as the uninterrupted step left them
    # Other grades (here also keeping no test) cannot finish another selection's withdrawal: refused, nothing changes.
    interrupted(registered=True, unavailable=True)
    before = _files(td)
    (tmp_path / "other").mkdir()
    other = grades(tmp_path / "other", ref=[dict.fromkeys(ALL, "passed")] * 3, noop={**NOOP_PASSES, D1: "skipped"})
    code, _, err = run(capsys, tests, *other)
    assert code == 2 and "refused, nothing written" in err and "records another selection" in err
    assert "run the command that began it again, with the same grade files" in err
    assert _files(td) == before
    # Grades that keep tests are refused beside those records: they would contradict them.
    (tmp_path / "keeps").mkdir()
    code, _, err = run(capsys, tests, *grades(tmp_path / "keeps"))
    assert code == 2 and "would contradict it" in err and _files(td) == before


def test_the_record_goes_beside_the_spec_or_outside_every_verifiers_directory_and_git(tmp_path, capsys):
    tests = world(tmp_path)
    args = grades(tmp_path)
    other = tests.parents[1] / "full_plain" / "tests"
    other.mkdir(parents=True)
    content = hash_test_dir(other)
    for out in (other / "selection.json", tests / "selection.json", other.parent / "selection.json"):
        assert "verifiers directory" in _refused(capsys, tests, *args, "--out", out)
    assert hash_test_dir(other) == content and not list(other.parent.rglob("selection.json"))
    tracked = R / "results" / "b3-selection-should-not-exist.json"  # results/ is tracked: git does not ignore it
    assert "in the repository where git" in _refused(capsys, tests, *args, "--out", tracked)
    assert not tracked.exists()
    ignored = R / "data" / "natural" / "tasks" / T / "verifiers" / "diff_derived" / "selection.json"
    assert sel.record_location_problem(ignored, ignored) is None  # only checked, never written
    elsewhere = tmp_path / "runrec" / "b3-selection.json"
    assert run(capsys, tests, *args, "--out", elsewhere)[0] == 0 and elsewhere.is_file()


# --------------------------------------------------------------------------- refusals


def _refused(capsys, tests: Path, *argv) -> str:
    state = _state(tests)
    code, out, err = run(capsys, tests, *argv)
    assert code == 2 and out is None and "refused, nothing written" in err, (code, out, err)
    assert _state(tests) == state
    return err


def test_a_grade_without_check_statuses_is_refused_unless_accepted(tmp_path, capsys, monkeypatch):
    """A reference grade that timed out says nothing about any test: it is refused and nothing is written, so a later
    run with three good grades selects. Accepted with the flag, it lets no test pass, and the record names it."""
    tests = world(tmp_path / "a")
    args = grades(tmp_path / "a")
    timed_out = real_grade(monkeypatch, tmp_path, tests, f"{T}-reference", ["timeout"], name="timeout")
    assert json.loads(timed_out.read_text())["checks"] == []
    err = _refused(capsys, tests, "--reference", args[1], timed_out, args[3], "--noop", args[5])
    assert "no check statuses in reference grade 2 (timeout)" in err and sel.ACCEPT_WITHOUT_STATUSES in err
    assert run(capsys, tests, *args)[0] == 0
    tests = world(tmp_path / "b")
    args = grades(tmp_path / "b")
    killed = real_grade(monkeypatch, tmp_path, tests, f"{T}-noop-dev", ["no results"], name="killed")
    code, summary, err = run(capsys, tests, *args[:4], "--noop", killed, sel.ACCEPT_WITHOUT_STATUSES)
    assert code == 3 and summary["kept"] == 0 and summary["b3_available"] is False and summary["withdrawn"] is True
    assert "noop grade 1 has no check statuses" in err and "nothing is left to do for B3" in err
    record = json.loads((tests.parent / "selection.json").read_text())
    assert record["grades_without_statuses"] == ["noop grade 1"] and record["grades"][3]["n_statuses"] == 0
    assert json.loads((tests.parent / "unavailable.json").read_text())["reason"].endswith(
        f"; noop grade 1 had no check statuses ({sel.ACCEPT_WITHOUT_STATUSES}), so no test passed its part of the rule")
    # an environment failure is refused even then: grade again
    tests = world(tmp_path / "c")
    args = grades(tmp_path / "c")
    env = grade(tmp_path / "env.json", f"{T}-reference", {}, n=7, outcome=Outcome.environment_failure)
    assert "environment failure" in _refused(capsys, tests, "--reference", env, *args[2:4], "--noop", args[5],
                                              sel.ACCEPT_WITHOUT_STATUSES)


def test_repeated_grades_are_refused_when_they_show_it(tmp_path, capsys, monkeypatch):
    tests = world(tmp_path)
    args = grades(tmp_path)
    rest = [*args[2:4], "--noop", args[5]]
    # `grade --repeats 3` whose runs time out: a diagnostic per run
    timeouts = real_grade(monkeypatch, tmp_path, tests, f"{T}-reference", ["timeout"] * 3, name="rep-timeout")
    assert "repeated runs" in _refused(capsys, tests, "--reference", timeouts, *rest)
    # runs that disagree: unresolved
    flaky = real_grade(monkeypatch, tmp_path, tests, f"{T}-reference", [REF[2], REF[1], REF[2]], name="rep-flaky")
    assert json.loads(flaky.read_text())["outcome"] == "unresolved"
    assert "repeated runs" in _refused(capsys, tests, "--reference", flaky, *rest)
    # Runs that agree and add no diagnostic (task failures here) cannot be told from a single grade: the statuses
    # used are those of the last run, which is itself one single run of the reference.
    agree = real_grade(monkeypatch, tmp_path, tests, f"{T}-reference", [REF[1], {**REF[1], D1: "failed"}, REF[1]],
                       name="rep-agree")
    assert json.loads(agree.read_text())["diagnostics"] == []
    code, summary, _ = run(capsys, tests, "--reference", agree, *rest, "--dry-run")
    assert code == 0 and {r["check_id"]: r["reference"] for r in summary["tests"]}[D1] == ["passed"] * 3
    # a real single grade passes the checks
    single = real_grade(monkeypatch, tmp_path, tests, f"{T}-reference", [REF[0]], name="single")
    assert run(capsys, tests, "--reference", single, *rest, "--dry-run")[0] == 0


def test_a_grade_saved_again_or_older_than_the_spec_is_refused(tmp_path, capsys):
    tests = world(tmp_path)
    args = grades(tmp_path)
    again = tmp_path / "b3-ref-1-saved-again.json"
    again.write_text(json.dumps(json.loads(Path(args[1]).read_text())), encoding="utf-8")
    assert again.read_bytes() != Path(args[1]).read_bytes()
    assert "given twice" in _refused(capsys, tests, "--reference", args[1], again, args[3], "--noop", args[5])
    old = grade(tmp_path / "old.json", f"{T}-reference", REF[0], n=8, started_at="2026-11-19T23:59:59+00:00")
    assert "earlier build" in _refused(capsys, tests, "--reference", old, *args[2:4], "--noop", args[5])
    # the spec written again after the grades (a rebuild): every grade is of an earlier build
    later = datetime(2026, 11, 22, 12, tzinfo=UTC).timestamp()
    os.utime(tests.parent / "spec.json", (later, later))
    assert "earlier build" in _refused(capsys, tests, *args)


def test_kept_code_that_refers_to_a_removed_test_is_refused(tmp_path, capsys):
    """Kept code that calls, aliases or names a removed test would fail (NameError) or be skipped at the confirming
    grade, after the tests were rewritten: refused, nothing written."""
    calls = 'def test_d1_new_flag():\n    test_d2_old_behaviour()\n'
    cases = {
        "a call": B3.replace("def test_d1_new_flag():\n", calls),
        "a use at module level": B3 + "\n\ntest_d3_flaky.__doc__ = 'flaky'\n",
        "a dependency marker": B3.replace("def test_d1_new_flag():\n", '@pytest.mark.dependency(depends=['
                                          '"test_d2_old_behaviour"])\ndef test_d1_new_flag():\n'),
    }
    for n, (case, text) in enumerate(cases.items()):
        tests = world(tmp_path / str(n), {"test_b3.py": text, "test_classes.py": CLASSES})
        err = _refused(capsys, tests, *grades(tmp_path / str(n)))
        assert "refers to removed tests" in err and "test_b3.py: test_d" in err, case
    method = CLASSES.replace('    def test_k1(self):\n', '    def test_k1(self):\n        self.test_k2()\n')
    tests = world(tmp_path / "m", {"test_b3.py": B3, "test_classes.py": method})
    assert "test_classes.py: test_k2" in _refused(capsys, tests, *grades(tmp_path / "m"))
    # an emptied class named elsewhere in its file
    alias = CLASSES + "\n\nGONE = TestGone\n"
    tests = world(tmp_path / "c", {"test_b3.py": B3, "test_classes.py": alias})
    assert "test_classes.py: TestGone" in _refused(capsys, tests, *grades(tmp_path / "c"))


def test_grades_that_are_not_three_single_development_grades_are_refused(tmp_path, capsys):
    tests = world(tmp_path)
    args = grades(tmp_path)
    ref1, noop = args[1], args[5]
    assert "given twice" in _refused(capsys, tests, "--reference", ref1, ref1, ref1, "--noop", noop)
    held_out = grade(tmp_path / "noop-eval.json", f"{T}-noop-eval", NOOP, n=6)
    assert "development no-op" in _refused(capsys, tests, *args[:4], "--noop", held_out)
    pre = [grade(tmp_path / f"pre-{k}.json", f"{T}-pre-review", REF[2], n=k) for k in (1, 2, 3)]
    assert "development reference" in _refused(capsys, tests, "--reference", *pre, "--noop", noop)
    with pytest.raises(SystemExit):  # two reference grades
        sel.main([str(tests), "--reference", args[1], args[2], "--noop", noop])
    capsys.readouterr()
    cases = {
        "repeated runs": {"outcome": Outcome.unresolved},
        "repeated runs ": {"diagnostics": ["[run 0] a", "[run 1] b"]},
        "environment failure": {"outcome": Outcome.environment_failure, "checks": []},
        "is of": {"verifier_id": "full_plain"},
        "graded under": {"harness_version": "tc-harness/0.3.4"},
    }
    for want, update in cases.items():
        bad = grade(tmp_path / "bad.json", f"{T}-reference", REF[0], n=8, **update)
        assert want.strip() in _refused(capsys, tests, "--reference", bad, *args[2:4], "--noop", noop), want
    other = grade(tmp_path / "other.json", f"{T}-reference", {**REF[0], "test_b3.py::test_gone": "passed"}, n=9)
    assert "other checks" in _refused(capsys, tests, "--reference", other, *args[2:4], "--noop", noop)
    mixed = grade(tmp_path / "mixed.json", f"{T}-noop-dev", REF[0], n=4)
    assert "different candidates" in _refused(capsys, tests, "--reference", mixed, *args[2:4], "--noop", noop)


def test_a_verifier_that_is_not_an_unfrozen_b3_built_from_these_tests_is_refused(tmp_path, capsys):
    for n, (update, want) in enumerate([({"frozen": True}, "frozen"),
                                        ({"condition": VerifierCondition.llm_freeform}, "diff_derived"),
                                        ({"content_sha256": "0" * 64}, "changed since the spec was built")]):
        tests = world(tmp_path / str(n), **update)
        assert want in _refused(capsys, tests, *grades(tmp_path / str(n)))
    tests = world(tmp_path / "edited")
    (tests / "test_b3.py").write_text(B3 + "\n# edited after the spec was built\n")
    assert "changed since" in _refused(capsys, tests, *grades(tmp_path / "edited"))
    loose = tmp_path / "loose" / "tests"
    loose.mkdir(parents=True)
    assert "must be <task>/verifiers" in _refused(capsys, loose, *grades(tmp_path / "loose"))


def _refused_whole(capsys, tests: Path, *argv) -> str:
    """As :func:`_refused`, with every file of the task as it was (task.json and spec.json above all)."""
    files = _files(tests.parents[2])
    err = _refused(capsys, tests, *argv)
    assert _files(tests.parents[2]) == files
    return err


def test_taking_b3_out_of_the_run_is_refused_where_it_cannot_be_done(tmp_path, capsys):
    """Refused before anything is written, when no test is kept, and so is its dry run, which never promises what the
    run refuses: a record elsewhere than beside the spec, where the pre-flight reads it; an unavailable.json there
    without the selection it belongs to; and a verifier that verifiers_extra.json registers, which the run grades
    whatever task.json says."""
    for dry in ((), ("--dry-run",)):
        root = tmp_path / ("dry" if dry else "run")
        tests = world(root / "out")
        elsewhere = root / "runrec" / "b3-selection.json"
        err = _refused_whole(capsys, tests, *grades(root / "out", noop=NOOP_PASSES), "--out", elsewhere, *dry)
        assert "goes in its default place" in err and "run again without --out" in err and not elsewhere.exists()
        tests = world(root / "again")
        (tests.parent / "unavailable.json").write_text("{}\n", encoding="utf-8")
        err = _refused_whole(capsys, tests, *grades(root / "again", noop=NOOP_PASSES), *dry)
        assert "unavailable.json exists beside the tests without selection.json" in err
        tests = world(root / "sidecar")
        write_json({"verifiers": [B3_SPEC]}, tests.parents[2] / "verifiers_extra.json")
        err = _refused_whole(capsys, tests, *grades(root / "sidecar", noop=NOOP_PASSES), *dry)
        assert f"verifiers_extra.json registers {B3_SPEC}" in err


def test_a_selection_beside_an_unavailable_record_is_refused(tmp_path, capsys):
    """After a withdrawal, the spec rebuilt from the same tests (by hand: build-verifier refuses the frozen spec), the
    selection record deleted and the tests graded again: a selection that keeps tests, or its dry run, is refused, and
    so is one that keeps none, since either would contradict unavailable.json (the reviewer's case)."""
    tests = world(tmp_path)
    vdir, td = tests.parent, tests.parents[2]
    assert run(capsys, tests, *grades(tmp_path, noop=NOOP_PASSES))[0] == 3
    dump(build_spec(verifier_id="diff_derived", task_id=T, condition=VerifierCondition.diff_derived, test_dir=tests,
                    task_dir=td, requirement_map=requirement_map_from_tests(tests), generation=_generation()),
         vdir / "spec.json")
    os.utime(vdir / "spec.json", (BUILT, BUILT))
    (vdir / "selection.json").unlink()
    (tmp_path / "again").mkdir()
    for dry in ((), ("--dry-run",)):
        err = _refused_whole(capsys, tests, *grades(tmp_path / "again"), *dry)
        assert "unavailable.json beside the tests records B3 as unavailable" in err and "would contradict it" in err
        err = _refused_whole(capsys, tests, *grades(tmp_path / "again", noop=NOOP_PASSES), *dry)
        assert "unavailable.json exists beside the tests without selection.json" in err
    assert sorted(p.name for p in vdir.iterdir()) == ["spec.json", "tests", "unavailable.json"]


def test_a_result_that_cannot_be_edited_or_does_not_lint_clean_is_refused(tmp_path, capsys):
    not_literal = B3.replace("CHECK_REQUIREMENTS = {", "CHECK_REQUIREMENTS = dict(**{").replace('["D4"],\n}', '["D4"],\n})')
    tests = world(tmp_path / "a", {"test_b3.py": not_literal, "test_classes.py": CLASSES})
    assert "not a dict literal" in _refused(capsys, tests, *grades(tmp_path / "a"))
    unlinted = B3.replace("    r = run_python(_code(\"mod.flag()\"))\n    assert r.ok and r.value is True\n",
                          "    r = run_python(_code(\"mod.flag()\"))\n    assert r.ok\n")
    tests = world(tmp_path / "b", {"test_b3.py": unlinted, "test_classes.py": CLASSES})
    assert "do not lint clean" in _refused(capsys, tests, *grades(tmp_path / "b"))


# --------------------------------------------------------------------------- the rest of the pipeline

# The B3 test of a family of tests/natural_task_layout.py: a missing second argument counts as zero.
B3_NATURAL = textwrap.dedent('''\
    """B3 test of a synthetic natural family."""
    from tc_sandbox import run_python

    CHECK_REQUIREMENTS = {"test_second_missing_value": ["D1"]}


    def test_second_missing_value():
        r = run_python("from fxnat.mod import add\\nresult = add(2, None)")
        assert r.ok and r.value == 2
''')


@pytest.fixture()
def scratch_git(monkeypatch):
    """For the pipeline tests: git answers in the scratch repository (init, commit, show, check-ignore, rev-parse), the
    host is idle and its tree clean (``docker ps`` and ``git status`` answer nothing, as in the pre-flight's own tests),
    and no other process starts (Docker is replaced by stubs)."""

    def guarded(cmd, *a, **kw):
        if list(cmd[:2]) in (["docker", "ps"], ["git", "status"]):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if list(cmd[:1]) == ["git"]:
            return _REAL_RUN(cmd, *a, **kw)
        raise AssertionError(f"no process but git may start in these tests: {list(cmd[:1])}")
    monkeypatch.setattr(subprocess, "run", guarded)


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _b3_grades(root: Path, task: str, check: str, noop: str) -> list[str]:
    """The selection's grades of ``task``'s one B3 test ``check``: passed in three single grades of the reference, and
    ``noop`` in a single grade of the development no-op."""
    root.mkdir(parents=True, exist_ok=True)
    refs = [str(grade(root / f"{task}-ref-{n}.json", f"{task}-reference", {check: "passed"}, n=n, task=task))
            for n in (1, 2, 3)]
    return ["--reference", *refs, "--noop",
            str(grade(root / f"{task}-noop.json", f"{task}-noop-dev", {check: noop}, n=5, task=task))]


def _main(capsys, entry, *argv) -> int | str:
    """``entry(argv)`` (a script's or the CLI's main) and its exit code; what it prints is read and dropped."""
    try:
        code = entry([str(a) for a in argv])
    except SystemExit as exc:
        code = exc.code
    capsys.readouterr()
    return 0 if code is None else code


def test_the_whole_pre_flight_passes_and_notes_b3_as_unavailable(tmp_path, tmp_path_factory, capsys, scratch_git):
    """The complete family of the pre-flight's own tests (tests/test_preflight_natural.py), whose B3 is, as the
    selection finds it, built from its tests and not frozen: the pre-flight fails on that verifier. Once the selection
    keeps no test, the whole pre-flight passes with one note: B3 is unavailable for the family. The ordinary steps that
    follow a selection that keeps tests, build-verifier and freeze, are then refused and change nothing, so the
    pre-flight still notes B3 as unavailable (before, they put a frozen B3 of the rejected tests back into task.json, and
    the pre-flight passed with no note)."""
    family = _module("preflight_natural_world", R / "tests" / "test_preflight_natural.py")
    pf = _module("preflight_final_run", R / "scripts" / "preflight_final_run.py")
    pf.R = tmp_path  # the scratch repository, as the pre-flight's own tests set it
    td = family.build(tmp_path)
    tid, tests = family.TID, td / "verifiers" / "diff_derived" / "tests"
    dump(build_spec(verifier_id="diff_derived", task_id=tid, condition=VerifierCondition.diff_derived, test_dir=tests,
                    task_dir=td, requirement_map=requirement_map_from_tests(tests), generation=_generation()),
         tests.parent / "spec.json")
    os.utime(tests.parent / "spec.json", (BUILT, BUILT))

    def preflight() -> tuple[int, list[str], list[str]]:
        code = pf.main(str(td), *family.RUN)
        lines = capsys.readouterr().out.splitlines()
        fails, notes = ([ln[len(kind) + 2:] for ln in lines if ln.startswith(f"{kind}: ")] for kind in ("FAIL", "NOTE"))
        return code, fails, notes

    code, fails, _ = preflight()
    assert code == 1 and f"{tid}: verifier diff_derived not frozen" in fails
    (check,) = discover_checks(tests)
    runrec = tmp_path_factory.mktemp("runrec")
    assert _main(capsys, sel.main, tests, *_b3_grades(runrec, tid, check, "passed")) == 3
    code, fails, notes = preflight()
    assert (code, fails) == (0, []) and len(notes) == 1, (fails, notes)
    unavailable_note = (f"{tid}: B3 (diff_derived) is unavailable for this family: its test selection kept no test "
                        "(verifiers/diff_derived/selection.json, b3_available false")
    assert notes[0].startswith(unavailable_note)
    files = {p: p.read_bytes() for p in sorted(td.rglob("*")) if p.is_file()}
    gen = runrec / "diff-derived.json"
    gen.write_text(_generation().model_dump_json(indent=2), encoding="utf-8")
    refused = _main(capsys, cli.main, "build-verifier", td, "diff_derived", "--condition", "diff_derived",
                    "--generation-record", gen)
    assert isinstance(refused, str) and "diff_derived is frozen" in refused
    with pytest.raises(ValueError, match="already frozen"):
        cli.main(["freeze", str(td), "diff_derived"])
    capsys.readouterr()
    assert {p: p.read_bytes() for p in sorted(td.rglob("*")) if p.is_file()} == files
    code, fails, notes = preflight()
    assert (code, fails) == (0, []) and len(notes) == 1 and notes[0].startswith(unavailable_note), (fails, notes)


def test_after_b3_is_taken_out_the_run_grades_no_b3_for_the_family_and_the_analysis_runs(tmp_path, capsys, monkeypatch,
                                                                                         scratch_git):
    """One run of two accepted families with B3 among its conditions: NP-90, whose B3 selection kept no test, and NP-91,
    whose B3 kept its test and was frozen. Before the selection, evaluate refuses the run on the unfrozen B3 in
    task.json; after it, evaluate refuses nothing, grades B1 and no B3 for NP-90 (its B3 is frozen where it lies but
    registered nowhere), and records the verifiers it graded; the analysis of the run has B3 rows for NP-91.

    What says that NP-90's B3 is unavailable, rather than missing for another reason, is the family's records beside
    its tests (selection.json, unavailable.json), which the pre-flight reads. evaluate's manifest and the analysis do not
    read them yet: reporting B3 as unavailable there is left to those modules (outside this script), so nothing here
    takes NP-90's missing B3 rows for that report."""
    root, runrec = tmp_path / "repo", tmp_path / "runrec"
    root.mkdir()
    init_git(root)
    gone, kept = build_natural_task(root, "NP-90"), build_natural_task(root, "NP-91")
    calls = use_layout(monkeypatch, root)
    runrec.mkdir()
    gen = runrec / "diff-derived.json"
    gen.write_text(_generation().model_dump_json(indent=2), encoding="utf-8")
    for nt in (gone, kept):
        assert _main(capsys, cli.main, "freeze", nt.task_dir, "repo_tests") == 0
        tests = nt.task_dir / "verifiers" / "diff_derived" / "tests"
        tests.mkdir(parents=True)
        (tests / "test_b3.py").write_text(B3_NATURAL, encoding="utf-8")
        assert _main(capsys, cli.main, "build-verifier", nt.task_dir, "diff_derived", "--condition", "diff_derived",
                     "--generation-record", gen) == 0
        assert load(nt.task_dir / "task.json", TaskManifest).verifiers == [B1_SPEC, B3_SPEC]
        os.utime(tests.parent / "spec.json", (BUILT, BUILT))
    out_root = root / "data" / "natural" / "runs"
    evaluate = ["evaluate", gone.task_dir, kept.task_dir, "--run-id", "natural-test", "--pilot", "--conditions",
                "repo_tests", "diff_derived", "--out-root", out_root]
    refused = _main(capsys, cli.main, *evaluate)
    assert isinstance(refused, str) and "diff_derived is not frozen" in refused and not out_root.exists()
    for nt, noop in ((gone, "passed"), (kept, "failed")):
        tests = nt.task_dir / "verifiers" / "diff_derived" / "tests"
        (check,) = discover_checks(tests)
        assert _main(capsys, sel.main, tests, *_b3_grades(runrec, nt.task_id, check, noop)) == (3 if nt is gone else 0)
    assert _main(capsys, cli.main, "freeze", kept.task_dir, "diff_derived") == 0
    assert load(gone.task_dir / "task.json", TaskManifest).verifiers == [B1_SPEC]
    assert _main(capsys, cli.main, *evaluate) == 0
    run_dir = out_root / "natural-test"
    m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["conditions"] == ["repo_tests", "diff_derived"]
    assert {t["task_id"]: sorted(t["verifiers"]) for t in m["tasks"]} == {"NP-90": ["repo_tests"],
                                                                          "NP-91": ["diff_derived", "repo_tests"]}
    assert sorted({(c["task_dir"].name, c["verifier_id"]) for c in calls}) == [
        ("NP-90", "repo_tests"), ("NP-91", "diff_derived"), ("NP-91", "repo_tests")]
    # NP-90's records, which say why the run has no B3 verdict for it
    vdir = gone.task_dir / "verifiers" / "diff_derived"
    selection, unavailable = (json.loads((vdir / name).read_text(encoding="utf-8"))
                              for name in ("selection.json", "unavailable.json"))
    assert selection["b3_available"] is False and selection["withdrawn"] is True and unavailable["available"] is False
    assert load(vdir / "spec.json", VerifierSpec).frozen and unavailable["taken_out"]["task_json_entries"] == [B3_SPEC]
    a = analyze(run_dir, root / NATURAL_TASKS, allow_proposed=True, n_boot=50)
    assert list(a["conditions"]) == ["repo_tests", "diff_derived"]
    assert a["per_task"]["NP-90"]["repo_tests"] and a["per_task"]["NP-91"]["diff_derived"]
    assert (run_dir / "analysis.md").is_file()
