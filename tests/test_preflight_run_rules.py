"""The pre-flight's rules for new runs (protocol v0.7 §15.3, v0.8 §16.1, §16.5).

* a new run grades every pair three times and uses ``tc-harness/0.3.5`` or later;
* every task needs a passing, current reconstruction check, with or without ``--pilot``;
* the acceptance gate applies as in ``tracecontract evaluate``: ``--pilot`` allows tasks that
  have not passed it.

The fixture task is synthetic (population ``fixture``); the last test reads the four pilot
tasks' records without changing them (Docker and git are not asked).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from tracecontract.reconstruction import METHOD, RECORD, current_inputs
from tracecontract.schemas import Candidate, CandidateOrigin, Population, SnapshotSource, Split, TaskManifest, sha256_text
from tracecontract.store import dump, write_json
from tracecontract.tasks import verify_snapshot

R = Path(__file__).resolve().parents[1]


def _preflight():
    spec = importlib.util.spec_from_file_location("preflight_final_run", R / "scripts" / "preflight_final_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def pf(monkeypatch):
    mod = _preflight()
    real = subprocess.run

    def run(cmd, *a, **k):  # the host is idle and the tree clean: only these two questions are answered here
        if list(cmd[:2]) in (["docker", "ps"], ["git", "status"]):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return real(cmd, *a, **k)

    monkeypatch.setattr(mod.subprocess, "run", run)
    return mod


@pytest.mark.parametrize("repeats, harness, problems", [
    (3, "tc-harness/0.3.5", 0),
    (3, "tc-harness/0.3.10", 0),  # compared as numbers, not as text
    (3, "tc-harness/0.4", 0),
    (1, "tc-harness/0.3.5", 1),  # evaluate's default: one repeat
    (3, "tc-harness/0.3.4", 1),  # never used for a run (v0.8 §16.1)
    (3, "tc-harness/0.3.3", 1),
    (3, "something else", 1),
    (2, "tc-harness/0.3.4", 2),
])
def test_a_new_run_needs_three_repeats_and_harness_0_3_5(pf, repeats, harness, problems):
    out = pf.run_problems(repeats=repeats, harness=harness)
    assert len(out) == problems, out
    assert all(p.startswith("run: ") for p in out)


def test_a_new_run_needs_a_new_run_id(pf, tmp_path):
    (tmp_path / "pilot-x").mkdir()
    assert pf.run_problems(repeats=3, harness="tc-harness/0.3.5", run_id="new", runs_root=tmp_path) == []
    assert "already exists" in pf.run_problems(repeats=3, harness="tc-harness/0.3.5", run_id="pilot-x", runs_root=tmp_path)[0]


def _task(root: Path) -> Path:
    """A fixture task with no verifiers, no provenance record and no held-out pool."""
    td = root / "FX-PF"
    noop = Candidate(candidate_id="FX-PF-noop-eval", task_id="FX-PF", origin=CandidateOrigin.noop, split=Split.eval, patch="",
                     patch_sha256=sha256_text(""), produced_by="base snapshot")
    dump(noop, td / "candidates" / "noop.json")
    dump(TaskManifest(task_id="FX-PF", family_id="FX-PF", population=Population.fixture, status="pending_review",
                      provenance="provenance.json", snapshot_source=SnapshotSource(repo_url="https://example.invalid/x",
                                                                                     commit="0" * 40),
                      env_requirements=[], candidates=["candidates/noop.json"]), td / "task.json")
    (td / "snapshot.json").write_text(json.dumps({"snapshot_id": "FX-PF", "task_id": "FX-PF", "repo_url": "x",
                                                  "base_commit": "0" * 40, "fidelity": "exact",
                                                  "file_manifest_sha256": "0" * 64, "n_files": 0}))
    return td


def _fails(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith("FAIL: ")]


def test_the_reconstruction_check_is_required_with_or_without_pilot(pf, tmp_path, capsys):
    td = _task(tmp_path)
    for extra in ([], ["--pilot"]):
        assert pf.main(str(td), "--repeats", "3", *extra) == 1
        fails = _fails(capsys.readouterr().out)
        assert any(f.startswith("FAIL: FX-PF: reconstruction: no reconstruction_check.json") for f in fails), fails
    write_json({"task_id": "FX-PF", "method": METHOD, "status": "passed", "passed": True, "checks": [], "files": [],
                "inputs": current_inputs(td, R)}, td / RECORD)
    assert pf.main(str(td), "--repeats", "3", "--pilot") == 1  # the fixture still lacks its pool and snapshot
    assert not [f for f in _fails(capsys.readouterr().out) if "reconstruction" in f]


def test_pilot_allows_tasks_that_have_not_passed_the_gate(pf, tmp_path, capsys):
    td = _task(tmp_path)
    pf.main(str(td), "--repeats", "3")
    out = capsys.readouterr().out
    assert any("FX-PF: not accepted through the acceptance gate" in f and "pass --pilot" in f for f in _fails(out))
    pf.main(str(td), "--repeats", "3", "--pilot")
    out = capsys.readouterr().out
    assert not [f for f in _fails(out) if "acceptance gate" in f]
    assert "WARN: FX-PF: not accepted through the acceptance gate" in out and "automated pilot (--pilot)" in out
    # A rejected task is refused whatever the flags.
    m = json.loads((td / "task.json").read_text())
    (td / "task.json").write_text(json.dumps({**m, "status": "rejected"}))
    pf.main(str(td), "--repeats", "3", "--pilot")
    assert any("refused by the acceptance gate (status: the task is rejected)" in f for f in _fails(capsys.readouterr().out))


def test_conditions_must_have_a_verifier(pf, tmp_path, capsys):
    td = _task(tmp_path)
    pf.main(str(td), "--repeats", "3", "--pilot", "--conditions", "full_plain")
    assert any("no verifier for condition(s) ['full_plain']" in f for f in _fails(capsys.readouterr().out))


def test_the_documented_pilot_command_passes_on_the_pilot_tasks(pf, monkeypatch, capsys):
    """README's pre-flight and evaluate flags for the four pilot tasks, with three repeats and --pilot."""
    tasks = [R / "tasks" / t for t in ("CS-01", "CS-02", "CS-03", "CS-04")]
    if not all((R / "snapshots" / td.name).is_dir() and verify_snapshot(td, R / "snapshots") for td in tasks):
        pytest.skip("a base snapshot is missing or stale (tracecontract snapshot tasks/<id>)")
    import tracecontract.sandbox.docker_runner as docker_runner

    monkeypatch.setattr(docker_runner, "HARNESS_VERSION", "tc-harness/0.3.5")  # the version protocol v0.8 names
    argv = [*map(str, tasks), "--run-id", "preflight-test-run", "--conditions", "initial_plain", "initial_audited",
            "full_plain", "full_audited", "llm_freeform", "repo_tests"]
    assert pf.main(*argv, "--repeats", "3", "--pilot") == 0, _fails(capsys.readouterr().out)
    out = capsys.readouterr().out
    assert out.count("checked as an automated pilot (--pilot)") == 4
    # Without --repeats 3 (evaluate's default) or without --pilot, the same command fails.
    assert pf.main(*argv, "--pilot") == 1 and _fails(capsys.readouterr().out) == [
        "FAIL: run: a new run grades every pair 3 times; pass --repeats 3 here and to `tracecontract evaluate` "
        "(got 1; protocol v0.7 §15.3, v0.8 §16.1)"]
    assert pf.main(*argv, "--repeats", "3") == 1
    assert len([f for f in _fails(capsys.readouterr().out) if "not accepted through the acceptance gate" in f]) == 4
    monkeypatch.setattr(docker_runner, "HARNESS_VERSION", "tc-harness/0.3.4")
    assert pf.main(*argv, "--repeats", "3", "--pilot") == 1
    assert [f for f in _fails(capsys.readouterr().out) if "harness" in f] == [
        "FAIL: run: the grader's harness is tc-harness/0.3.4; every new run uses tc-harness/0.3.5 or later "
        "(protocol v0.8 §16.1)"]
