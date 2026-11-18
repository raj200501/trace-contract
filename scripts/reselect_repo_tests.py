"""Re-run B1's PASS-on-reference selection with the current harness (decision log D30).

The overlay (reference-state repository tests) is kept as it is; only the selection of
expected checks is recomputed by grading the reference candidate. Without ``--apply``
the script only reports differences from the frozen spec. With ``--apply`` it writes a
new selection and a new spec with ``version`` incremented (unfrozen; freeze it with
``tracecontract freeze``). The previous selection is kept as ``selection_v<N>.json``.

Usage: python scripts/reselect_repo_tests.py tasks/CS-04 [--apply]
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from tracecontract.cli import CACHE, SNAPSHOTS
from tracecontract.sandbox.docker_runner import HARNESS_VERSION, build_env_image, prepare_workspace, run_grader
from tracecontract.schemas import Candidate, Isolation, TaskManifest, VerifierCondition, VerifierSpec
from tracecontract.store import dump, load, write_json
from tracecontract.verifier import build_spec


def main(task_dir: str, *flags: str) -> None:
    apply = "--apply" in flags
    tdir = Path(task_dir).resolve()
    m = load(tdir / "task.json", TaskManifest)
    vdir = tdir / "verifiers" / "repo_tests"
    old = load(vdir / "spec.json", VerifierSpec)
    overlay = tdir / old.test_dir
    ref = next(load(tdir / p, Candidate) for p in m.candidates if p.endswith("-reference.json"))
    tag, _ = build_env_image(m.env_requirements, CACHE / "images")
    ws, diags, err = prepare_workspace(SNAPSHOTS / m.task_id, ref.patch)
    assert ws is not None, diags
    raw, nonce = run_grader(tag, workspace=ws, mode=Isolation.in_process, overlay_dir=overlay,
                            repo_test_args=m.repo_test_args, candidate_pythonpath=m.candidate_pythonpath)
    shutil.rmtree(ws, ignore_errors=True)
    r = raw.results or {}
    assert r.get("nonce") == nonce and r.get("status") == "completed", (r.get("status"), r.get("error"), raw.stderr[-500:])
    assert not r.get("timed_out"), "reference run timed out"
    tests = r.get("tests", [])
    passing = sorted(t["nodeid"] for t in tests if t["outcome"] == "passed")
    failing = sorted(t["nodeid"] for t in tests if t["outcome"] != "passed")
    old_ids = [c.check_id for c in old.checks]
    added, removed = sorted(set(passing) - set(old_ids)), sorted(set(old_ids) - set(passing))
    report = {"task": m.task_id, "harness": HARNESS_VERSION, "pytest_exit_code": r.get("pytest_exit_code"),
              "n_tests_reported": len(tests), "n_passing": len(passing), "n_failing": len(failing),
              "frozen_version": old.version, "frozen_n_checks": len(old_ids), "added": len(added), "removed": removed[:20],
              "failing": failing[:20], "identical": not added and not removed}
    print(json.dumps(report, indent=1))
    if not apply or report["identical"]:
        return
    prev = vdir / "selection.json"
    if prev.exists():
        shutil.copyfile(prev, vdir / f"selection_v{old.version}.json")
    write_json({"passing_on_reference": passing, "excluded_not_passing_on_reference": failing,
                "collect_errors": r.get("collect_errors", []), "harness_version": HARNESS_VERSION,
                "previous_version": {"version": old.version, "content_sha256": old.content_sha256, "n_checks": len(old_ids)}},
               vdir / "selection.json")
    (vdir / "check_ids.json").write_text(json.dumps(passing))
    spec = build_spec(verifier_id="repo_tests", task_id=m.task_id, condition=VerifierCondition.repo_tests, test_dir=overlay,
                      task_dir=tdir, isolation=Isolation.in_process, check_ids=passing)
    dump(spec.model_copy(update={"version": old.version + 1}), vdir / "spec.json")
    print(json.dumps({"written": str((vdir / "spec.json").relative_to(tdir)), "version": old.version + 1}))


if __name__ == "__main__":
    main(*sys.argv[1:])
