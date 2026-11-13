"""Trusted grader entrypoint, executed as root inside the task container.

Invoked by the host as ``python3 -I /grader/harness/tc_runner.py ...``. Steps:

1. Copy the approved candidate workspace (``/mnt/candidate``, read-only mount) to
   ``/work`` and hand it to the sandbox user, before any candidate code runs.
2. Create the sandbox HOME once (see ``tc_sandbox.prepare_sandbox_home``).
3. Run the verifier:
   * ``process_separated`` - pytest runs in THIS (root) process over the hidden
     tests in ``/grader/tests``; tests reach candidate code only through
     ``tc_sandbox.run_python`` / ``run_cmd`` child processes;
   * ``repo_tests`` - the repository's own pytest suite runs as the sandbox user
     inside ``/work`` (candidate code is imported by the test process, so this
     mode is marked ``in_process`` / tamperable).
4. Write ``/results/results.json`` atomically (``/results`` is root-only).

The host never trusts the container exit code alone: it recomputes the outcome
from this file and checks the run nonce, so missing or stale results cannot
become a passing reward.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import time
import traceback
import xml.etree.ElementTree as ET

HARNESS_VERSION = "tc-harness/0.1.0"
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))


def _copy_tree(src: str, dst: str) -> int:
    """Copy src -> dst as root without following symlinks (rejects symlinks)."""
    n = 0
    for root, dirs, files in os.walk(src, followlinks=False):
        rel = os.path.relpath(root, src)
        target_root = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_root, mode=0o755, exist_ok=True)
        for d in dirs:
            if os.path.islink(os.path.join(root, d)):
                raise RuntimeError(f"symlink directory in candidate files: {os.path.join(rel, d)}")
        for f in files:
            s = os.path.join(root, f)
            st = os.lstat(s)
            if stat.S_ISLNK(st.st_mode):
                raise RuntimeError(f"symlink in candidate files: {os.path.join(rel, f)}")
            if not stat.S_ISREG(st.st_mode):
                continue
            t = os.path.join(target_root, f)
            if os.path.lexists(t):
                os.unlink(t)
            shutil.copyfile(s, t, follow_symlinks=False)
            os.chmod(t, (st.st_mode & 0o755) | 0o644)
            n += 1
    return n


def _hand_over(dst: str, uid: int, gid: int) -> None:
    """chown the copied tree to the sandbox user. Runs before any candidate code."""
    for root, dirs, files in os.walk(dst, topdown=False, followlinks=False):
        for name in files + dirs:
            os.lchown(os.path.join(root, name), uid, gid)
    os.lchown(dst, uid, gid)


class _Collector:
    def __init__(self) -> None:
        self.tests: dict[str, dict] = {}
        self.collect_errors: list[dict] = []

    def pytest_collectreport(self, report):  # noqa: D401 - pytest hook
        if report.failed:
            self.collect_errors.append({"nodeid": report.nodeid, "longrepr": str(report.longrepr)[-4000:]})

    def pytest_runtest_logreport(self, report):
        e = self.tests.setdefault(report.nodeid, {"nodeid": report.nodeid, "outcome": None, "duration": 0.0, "longrepr": ""})
        e["duration"] += float(getattr(report, "duration", 0.0) or 0.0)
        if report.when == "setup":
            if report.failed:
                e["outcome"], e["longrepr"] = "error", str(report.longrepr)[-4000:]
            elif report.skipped:
                e["outcome"] = "skipped"
        elif report.when == "call":
            if report.passed:
                e["outcome"] = "passed" if e["outcome"] is None else e["outcome"]
            elif report.failed:
                e["outcome"], e["longrepr"] = "failed", str(report.longrepr)[-4000:]
            elif report.skipped:
                e["outcome"] = "skipped"
        elif report.when == "teardown" and report.failed and e["outcome"] == "passed":
            e["outcome"], e["longrepr"] = "error", str(report.longrepr)[-4000:]


def run_process_separated(tests_dir: str) -> dict:
    import pytest  # imported in the trusted process; never sees candidate modules

    sys.path.insert(0, HARNESS_DIR)
    import tc_sandbox  # noqa: E402

    col = _Collector()
    args = [
        "-q", "-p", "no:cacheprovider", "--rootdir", tests_dir, "--import-mode=importlib",
        "-o", "addopts=", "-o", "python_files=test_*.py", tests_dir,
    ]
    t0 = time.time()
    code = pytest.main(args, plugins=[col])
    return {
        "pytest_exit_code": int(code),
        "tests": list(col.tests.values()),
        "collect_errors": col.collect_errors,
        "tamper_events": list(tc_sandbox.TAMPER_EVENTS),
        "elapsed_s": time.time() - t0,
    }


def _parse_junit(path: str) -> list[dict]:
    tree = ET.parse(path)
    out = []
    for tc in tree.iter("testcase"):
        cls = tc.get("classname", "")
        name = tc.get("name", "")
        nodeid = f"{cls}::{name}" if cls else name
        outcome = "passed"
        msg = ""
        for child in tc:
            if child.tag == "failure":
                outcome, msg = "failed", (child.get("message") or "")[:2000]
            elif child.tag == "error":
                outcome, msg = "error", (child.get("message") or "")[:2000]
            elif child.tag == "skipped":
                outcome, msg = "skipped", (child.get("message") or "")[:2000]
        out.append({"nodeid": nodeid, "outcome": outcome, "duration": float(tc.get("time", 0) or 0), "longrepr": msg})
    return out


def run_repo_tests(test_args: list[str], timeout: float) -> dict:
    sys.path.insert(0, HARNESS_DIR)
    import tc_sandbox  # noqa: E402

    # Root-owned, write+search-only directory: the sandbox user can create the report
    # but cannot list the directory; root reads it back only if it is a regular file.
    import secrets as _secrets

    junit_dir = f"/tmp/tc-junit-{_secrets.token_hex(8)}"
    os.mkdir(junit_dir)
    os.chmod(junit_dir, 0o733)
    junit = os.path.join(junit_dir, "junit.xml")
    argv = [tc_sandbox.PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}", *test_args]
    t0 = time.time()
    res = tc_sandbox.run_cmd(argv, timeout=timeout)
    out = {
        "pytest_exit_code": res.returncode,
        "timed_out": res.timed_out,
        "stdout_tail": res.stdout[-4000:],
        "stderr_tail": res.stderr[-4000:],
        "elapsed_s": time.time() - t0,
        "tests": [],
        "collect_errors": [],
        "tamper_events": [],
    }
    try:
        st = os.lstat(junit)
        if stat.S_ISREG(st.st_mode):
            out["tests"] = _parse_junit(junit)
        else:
            out["collect_errors"].append({"nodeid": "<junit>", "longrepr": "junit report is not a regular file"})
    except FileNotFoundError:
        out["collect_errors"].append({"nodeid": "<junit>", "longrepr": "no junit report produced"})
    except ET.ParseError as exc:
        out["collect_errors"].append({"nodeid": "<junit>", "longrepr": f"unparseable junit report: {exc}"})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["process_separated", "repo_tests"], required=True)
    ap.add_argument("--tests-dir", default="/grader/tests")
    ap.add_argument("--candidate", default="/mnt/candidate")
    ap.add_argument("--workdir", default="/work")
    ap.add_argument("--results", default="/results")
    ap.add_argument("--overlay", default="/grader/overlay", help="files copied over the candidate (repo_tests mode)")
    ap.add_argument("--repo-test-timeout", type=float, default=600.0)
    ap.add_argument("repo_test_args", nargs="*")
    a = ap.parse_args(argv)

    nonce = os.environ.get("TC_RUN_NONCE", "")
    uid = int(os.environ.get("TC_SANDBOX_UID", "1001"))
    gid = int(os.environ.get("TC_SANDBOX_GID", "1001"))
    result: dict = {"harness_version": HARNESS_VERSION, "nonce": nonce, "mode": a.mode, "status": "started"}
    try:
        if os.geteuid() != 0:
            raise RuntimeError("grader must run as root inside the container")
        # All copying happens as root while /work is still root-owned; ownership is
        # handed to the sandbox user afterwards, before any candidate code runs.
        result["n_candidate_files"] = _copy_tree(a.candidate, a.workdir)
        if a.mode == "repo_tests" and os.path.isdir(a.overlay):
            result["n_overlay_files"] = _copy_tree(a.overlay, a.workdir)
        _hand_over(a.workdir, uid, gid)
        sys.path.insert(0, HARNESS_DIR)
        import tc_sandbox  # noqa: E402

        tc_sandbox.prepare_sandbox_home()
        if a.mode == "process_separated":
            result.update(run_process_separated(a.tests_dir))
        else:
            result.update(run_repo_tests(a.repo_test_args, a.repo_test_timeout))
        result["status"] = "completed"
    except Exception as exc:  # noqa: BLE001 - report harness failures as data
        result["status"] = "harness_error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()[-4000:]
    tmp = os.path.join(a.results, ".results.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(result, fh, sort_keys=True)
    os.replace(tmp, os.path.join(a.results, "results.json"))
    return 0 if result["status"] == "completed" else 3


if __name__ == "__main__":
    sys.exit(main())
