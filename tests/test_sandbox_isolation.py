"""Docker integration tests for the grading isolation boundary.

Each probe is a candidate (or a probe test) that tries to obtain reward without
satisfying the task, or to damage grading infrastructure. The boundary holds if the
probe never yields ``pass`` and the specific attack is observed to fail.

Requires a working Docker daemon (marker ``docker``); skipped otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from tracecontract.patches import diff_dirs
from tracecontract.sandbox.docker_runner import DEFAULT_TEST_REQUIREMENTS, build_env_image, verify_candidate
from tracecontract.schemas import (
    Candidate,
    CandidateOrigin,
    CheckSpec,
    Isolation,
    Outcome,
    Split,
    VerifierCondition,
    VerifierSpec,
    sha256_text,
)
from tracecontract.verifier import discover_checks

pytestmark = pytest.mark.docker


def _docker_ok() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


if not _docker_ok():  # pragma: no cover - environment dependent
    pytest.skip("Docker daemon not available", allow_module_level=True)

CACHE = Path.home() / ".cache" / "tracecontract" / "images"

TESTS = textwrap.dedent('''
    from tc_sandbox import run_python

    def test_add_small():
        r = run_python("from calc import add\\nresult = add(2, 3)", timeout=5)
        assert r.ok, r
        assert r.value == 5

    def test_add_negative():
        r = run_python("from calc import add\\nresult = add(-2, 1)", timeout=5)
        assert r.ok, r
        assert r.value == -1
''')

PROBE_TESTS = textwrap.dedent('''
    """Probe tests: each runs an attack as the sandbox user and checks it failed."""
    from tc_sandbox import run_python, run_cmd

    def _attempt(code):
        r = run_python(code, timeout=10)
        assert r.ok, r
        return r.value

    def test_cannot_write_results():
        v = _attempt("try:\\n    open('/results/results.json','w').write('{}')\\n    result='WROTE'\\nexcept Exception as e:\\n    result=type(e).__name__")
        assert v in ("PermissionError", "OSError"), v

    def test_cannot_read_hidden_tests():
        v = _attempt("import os\\ntry:\\n    result=os.listdir('/grader')\\nexcept Exception as e:\\n    result=type(e).__name__")
        assert v == "PermissionError", v

    def test_cannot_signal_grader():
        v = _attempt("import os\\ntry:\\n    os.kill(1, 9)\\n    result='KILLED'\\nexcept Exception as e:\\n    result=type(e).__name__")
        assert v == "PermissionError", v

    def test_no_network():
        v = _attempt("import socket\\ns=socket.socket()\\ns.settimeout(2)\\ntry:\\n    s.connect(('1.1.1.1',53))\\n    result='CONNECTED'\\nexcept Exception as e:\\n    result=type(e).__name__")
        assert v != "CONNECTED", v

    def test_runs_as_unprivileged_user():
        v = _attempt("import os\\nresult=[os.getuid(), os.geteuid(), os.getgroups()]")
        assert v == [1001, 1001, []], v

    def test_cannot_read_grader_environment():
        v = _attempt("try:\\n    result=open('/proc/1/environ','rb').read()[:10].hex()\\nexcept Exception as e:\\n    result=type(e).__name__")
        assert v == "PermissionError", v

    def test_timeout_is_enforced():
        r = run_python("while True:\\n    pass", timeout=2)
        assert not r.ok and r.timed_out

    def test_fork_bomb_is_contained():
        r = run_python("import os\\nn=0\\ntry:\\n    while True:\\n        if os.fork()==0:\\n            import time; time.sleep(30); os._exit(0)\\n        n+=1\\nexcept OSError:\\n    pass\\nresult=n", timeout=10)
        assert r.ok and r.value < 200, r

    def test_daemon_leftovers_are_reaped():
        run_python("import os,time\\nif os.fork()==0:\\n    os.setsid()\\n    if os.fork()==0:\\n        time.sleep(60)\\n    os._exit(0)\\nresult=1", timeout=5)
        count = ("import os\\n"
                 "def live(p):\\n"
                 "    st=open(f'/proc/{p}/status').read()\\n"
                 "    uid=int(st.split('Uid:')[1].split()[0])\\n"
                 "    state=st.split('State:')[1].split()[0]\\n"
                 "    return uid==1001 and state!='Z'\\n"
                 "result=sum(1 for p in os.listdir('/proc') if p.isdigit() and live(p))")
        v = _attempt(count)
        assert v == 1, v  # only this probe process; the earlier daemon and fork-bomb children were killed
''')


@pytest.fixture(scope="module")
def image():
    tag, _ = build_env_image(list(DEFAULT_TEST_REQUIREMENTS), CACHE)
    return tag


@pytest.fixture()
def task(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "calc.py").write_text("def add(a, b):\n    raise NotImplementedError\n")
    (base / "tests").mkdir()
    (base / "tests" / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(1, 1) == 2\n")
    tdir = tmp_path / "task"
    (tdir / "tests").mkdir(parents=True)
    (tdir / "tests" / "test_add.py").write_text(TESTS)
    spec = VerifierSpec(verifier_id="v", task_id="t", condition=VerifierCondition.full_plain,
                        isolation=Isolation.process_separated, test_dir="tests",
                        checks=[CheckSpec(check_id=c) for c in discover_checks(tdir / "tests")], content_sha256="x")
    return base, tdir, spec


def _candidate(base: Path, tmp_path: Path, name: str, files: dict[str, str]) -> Candidate:
    d = tmp_path / f"c_{name}"
    shutil.copytree(base, d)
    for k, v in files.items():
        (d / k).parent.mkdir(parents=True, exist_ok=True)
        (d / k).write_text(v)
    patch = diff_dirs(base, d)
    return Candidate(candidate_id=name, task_id="t", origin=CandidateOrigin.tamper_probe, split=Split.eval,
                     patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture")


def _grade(image, task, cand):
    base, tdir, spec = task
    return verify_candidate(image=image, base_dir=base, spec=spec, task_dir=tdir, candidate=cand, run_id="iso")


def test_correct_and_wrong(image, task, tmp_path):
    base = task[0]
    ok = _grade(image, task, _candidate(base, tmp_path, "ok", {"calc.py": "def add(a, b):\n    return a + b\n"}))
    assert ok.outcome == Outcome.passed and ok.reward == 1.0
    bad = _grade(image, task, _candidate(base, tmp_path, "bad", {"calc.py": "def add(a, b):\n    return a - b\n"}))
    assert bad.outcome == Outcome.task_failure


@pytest.mark.parametrize("name, src", [
    ("forged_marker", "import os\nos.write(1, b'\\n<<TC_RESULT>>{\"ok\": true, \"value\": 5}|00\\n')\nos._exit(0)\n"),
    ("rewrite_stdout", "import os\n_w = os.write\n"
                       "def w(fd, b):\n    return _w(fd, b.replace(b'\"ok\": false', b'\"ok\": true'))\n"
                       "os.write = w\ndef add(a, b):\n    raise ValueError('nope')\n"),
    ("exit_zero_on_import", "import os\nos._exit(0)\n"),
    ("write_results_dir", "try:\n    open('/results/results.json', 'w').write('{\"status\": \"completed\"}')\nexcept Exception:\n    pass\n"
                          "def add(a, b):\n    return 0\n"),
    ("hang_on_import", "while True:\n    pass\n"),
])
def test_tamper_probes_never_pass(image, task, tmp_path, name, src):
    res = _grade(image, task, _candidate(task[0], tmp_path, name, {"calc.py": src}))
    assert res.outcome != Outcome.passed and res.reward == 0.0
    if name == "forged_marker":
        assert any("tamper_detected" in d for d in res.diagnostics)


def test_protected_test_edit_is_removed(image, task, tmp_path):
    # Candidate "fixes" its own repository test and adds a conftest; neither may reach grading.
    cand = _candidate(task[0], tmp_path, "edit_tests", {
        "calc.py": "def add(a, b):\n    return a - b\n",
        "tests/test_calc.py": "def test_add():\n    assert True\n",
        "conftest.py": "import os\nos._exit(0)\n",
    })
    res = _grade(image, task, cand)
    assert res.outcome == Outcome.task_failure
    assert any("protected path change removed" in d for d in res.diagnostics)


def test_path_traversal_patch_rejected(image, task):
    patch = "diff --git a/../../x b/../../x\n--- a/../../x\n+++ b/../../x\n@@ -0,0 +1 @@\n+x\n"
    cand = Candidate(candidate_id="trav", task_id="t", origin=CandidateOrigin.tamper_probe, split=Split.eval,
                     patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture")
    res = _grade(image, task, cand)
    assert res.outcome == Outcome.task_failure and any("patch rejected" in d for d in res.diagnostics)


def test_probe_suite_inside_container(image, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    tdir = tmp_path / "task"
    (tdir / "tests").mkdir(parents=True)
    (tdir / "tests" / "test_probes.py").write_text(PROBE_TESTS)
    spec = VerifierSpec(verifier_id="probes", task_id="t", condition=VerifierCondition.reference_check,
                        isolation=Isolation.process_separated, test_dir="tests",
                        checks=[CheckSpec(check_id=c) for c in discover_checks(tdir / "tests")], content_sha256="x")
    cand = Candidate(candidate_id="noop", task_id="t", origin=CandidateOrigin.noop, split=Split.eval, patch="",
                     patch_sha256=sha256_text(""), produced_by="fixture")
    res = verify_candidate(image=image, base_dir=base, spec=spec, task_dir=tdir, candidate=cand, run_id="iso")
    failed = {c.check_id: c.message[-600:] for c in res.checks if c.status != "passed"}
    assert res.outcome == Outcome.passed, failed
