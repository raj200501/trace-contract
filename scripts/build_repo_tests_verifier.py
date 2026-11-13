"""Build baseline B1 (repository tests at the reference state) for a task.

The overlay is the reference state's copy of the given test paths. Expected checks
are the tests that pass on the reference candidate itself (standard
PASS-on-reference selection); tests that fail on the reference are recorded and
excluded. The verifier is ``in_process`` (candidate code is imported by pytest).

Usage: python scripts/build_repo_tests_verifier.py tasks/CS-01 /path/to/final_state tests
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from tracecontract.cli import CACHE, SNAPSHOTS
from tracecontract.sandbox.docker_runner import build_env_image, prepare_workspace, run_grader
from tracecontract.schemas import Candidate, Isolation, TaskManifest, VerifierCondition
from tracecontract.store import dump, load, write_json
from tracecontract.verifier import build_spec


def main(task_dir: str, final_state: str, *test_paths: str) -> None:
    tdir = Path(task_dir).resolve()
    m = load(tdir / "task.json", TaskManifest)
    vdir = tdir / "verifiers" / "repo_tests"
    overlay = vdir / "overlay"
    if overlay.exists():
        shutil.rmtree(overlay)
    for tp in test_paths:
        src = Path(final_state) / tp
        dst = overlay / tp
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    ref = next(load(tdir / p, Candidate) for p in m.candidates if p.endswith("-reference.json"))
    tag, _ = build_env_image(m.env_requirements, CACHE / "images")
    ws, diags, err = prepare_workspace(SNAPSHOTS / m.task_id, ref.patch)
    assert ws is not None, diags
    raw, nonce = run_grader(tag, workspace=ws, mode=Isolation.in_process, overlay_dir=overlay,
                            repo_test_args=m.repo_test_args, candidate_pythonpath=m.candidate_pythonpath)
    shutil.rmtree(ws, ignore_errors=True)
    r = raw.results or {}
    assert r.get("nonce") == nonce and r.get("status") == "completed", (r.get("status"), r.get("error"), raw.stderr[-500:])
    tests = r.get("tests", [])
    passing = sorted(t["nodeid"] for t in tests if t["outcome"] == "passed")
    failing = sorted(t["nodeid"] for t in tests if t["outcome"] != "passed")
    write_json({"passing_on_reference": passing, "excluded_not_passing_on_reference": failing,
                "collect_errors": r.get("collect_errors", [])}, vdir / "selection.json")
    ids_file = vdir / "check_ids.json"
    ids_file.write_text(json.dumps(passing))
    spec = build_spec(verifier_id="repo_tests", task_id=m.task_id, condition=VerifierCondition.repo_tests, test_dir=overlay,
                      task_dir=tdir, isolation=Isolation.in_process, check_ids=passing)
    dump(spec, vdir / "spec.json")
    rel = "verifiers/repo_tests/spec.json"
    if rel not in m.verifiers:
        dump(m.model_copy(update={"verifiers": m.verifiers + [rel]}), tdir / "task.json")
    print(json.dumps({"task": m.task_id, "n_checks": len(passing), "excluded": len(failing), "collect_errors": len(r.get("collect_errors", []))}))


if __name__ == "__main__":
    main(*sys.argv[1:])
