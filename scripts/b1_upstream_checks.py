"""Record which B1 checks come from the upstream repository's own tests.

B1 (repository tests at the reference state) uses the test files of the reference
state. For controlled tasks the reference is the session agent's final state, so some
B1 checks are tests the agent itself added. This script collects the test ids of the
BASE snapshot's test files in the sandbox (pytest --collect-only) and writes
``tasks/<id>/verifiers/repo_tests/upstream_check_ids.json``: the B1 check ids that
also exist at the base commit. The analysis uses it for an exploratory split of B1
(decision log D37). The frozen B1 verifier itself is not changed.

Usage: python scripts/b1_upstream_checks.py tasks/CS-01 [...]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tracecontract.cli import CACHE, SNAPSHOTS
from tracecontract.sandbox.docker_runner import build_env_image
from tracecontract.schemas import TaskManifest, VerifierSpec
from tracecontract.store import load


def junit_id(nodeid: str) -> str:
    """'tests/test_more.py::Cls::test_x[p]' -> 'tests.test_more.Cls::test_x[p]' (the grader's check ids)."""
    parts = nodeid.split("::")
    module = parts[0][:-3] if parts[0].endswith(".py") else parts[0]
    classname = ".".join([module.replace("/", ".")] + parts[1:-1])
    return f"{classname}::{parts[-1]}"


def collect(task_dir: Path) -> list[str]:
    m = load(task_dir / "task.json", TaskManifest)
    tag, _ = build_env_image(m.env_requirements, CACHE / "images")
    base = (SNAPSHOTS / m.task_id).resolve()
    cmd = ["docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--read-only", "--tmpfs", "/tmp:rw,size=256m", "-e", "PYTHONDONTWRITEBYTECODE=1",
           "-e", f"PYTHONPATH={m.candidate_pythonpath}", "-v", f"{base}:/work:ro", "-w", "/work", "--user", "1001:1001", tag,
           "python", "-m", "pytest", "-p", "no:cacheprovider", "--collect-only", "-q", *m.repo_test_args]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout
    return sorted(junit_id(line.strip()) for line in out.splitlines() if "::" in line and not line.startswith(" "))


def main(*task_dirs: str) -> None:
    for td in map(Path, task_dirs):
        spec = load(td / "verifiers" / "repo_tests" / "spec.json", VerifierSpec)
        upstream = set(collect(td))
        checks = [c.check_id for c in spec.checks]
        kept = sorted(c for c in checks if c in upstream)
        out = {"note": "B1 check ids that also exist in the base commit's own test files (collected with pytest "
                       "--collect-only on the base snapshot); the rest were added in the reference state.",
               "n_b1_checks": len(checks), "n_upstream": len(kept), "n_added_in_reference": len(checks) - len(kept),
               "upstream_check_ids": kept}
        (td / "verifiers" / "repo_tests" / "upstream_check_ids.json").write_text(json.dumps(out, indent=1) + "\n")
        print(td.name, {k: v for k, v in out.items() if k.startswith("n_")})


if __name__ == "__main__":
    main(*sys.argv[1:])
