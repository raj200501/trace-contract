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
        import tc_sandbox
        v = _attempt("import os\\nresult=[os.getuid(), os.geteuid(), os.getgroups()]")
        uid = tc_sandbox.SANDBOX_UID
        assert 20000 <= uid < 60000, uid  # per-container UID, never root or a shared fixed UID
        assert v == [uid, uid, []], v

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
                 "    return uid==os.getuid() and state!='Z'\\n"
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


THREAD_PROBE = textwrap.dedent('''
    from tc_sandbox import run_python

    SNIPPET = (
        "import threading\\n"
        "ev = threading.Event()\\n"
        "n = 0\\n"
        "try:\\n"
        "    for _ in range(40):\\n"
        "        threading.Thread(target=ev.wait, daemon=True).start()\\n"
        "        n += 1\\n"
        "except RuntimeError:\\n"
        "    pass\\n"
        "ev.set()\\n"
        "result = n"
    )

    def test_threads_start():
        r = run_python(SNIPPET, timeout=20)
        assert r.ok, r
        print("THREADS_STARTED", r.value)
        # 10 threads: far more than the 4 that remained under a UID shared with a
        # container holding 60 threads (RLIMIT_NPROC 64) before harness 0.2.0.
        assert r.value >= 10, r.value
''')


def test_limits_not_shared_with_other_containers(image, tmp_path):
    """Regression (D29): per-UID kernel limits must not couple concurrent containers.

    Another container holds 60 threads as UID 1001 (the fixed UID used before
    harness 0.2.0, and the UID of the interactive sandbox wrappers). The graded
    candidate must still be able to start at least 10 threads.
    """
    holder = "tc-holder-" + tmp_path.name[-8:]
    subprocess.run(["docker", "run", "-d", "--rm", "--network", "none", "--name", holder, "--user", "1001:1001", image,
                    "python3", "-c", "import threading,time\nts=[threading.Thread(target=time.sleep,args=(60,)) for _ in range(60)]\n"
                    "[t.start() for t in ts]\n[t.join() for t in ts]"], check=True, capture_output=True)
    try:
        base = tmp_path / "base"
        base.mkdir()
        (base / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        tdir = tmp_path / "task"
        (tdir / "tests").mkdir(parents=True)
        (tdir / "tests" / "test_threads.py").write_text(THREAD_PROBE)
        spec = VerifierSpec(verifier_id="threads", task_id="t", condition=VerifierCondition.reference_check,
                            isolation=Isolation.process_separated, test_dir="tests",
                            checks=[CheckSpec(check_id=c) for c in discover_checks(tdir / "tests")], content_sha256="x")
        cand = Candidate(candidate_id="noop", task_id="t", origin=CandidateOrigin.noop, split=Split.eval, patch="",
                         patch_sha256=sha256_text(""), produced_by="fixture")
        res = verify_candidate(image=image, base_dir=base, spec=spec, task_dir=tdir, candidate=cand, run_id="iso")
        assert res.outcome == Outcome.passed, [c.message[-400:] for c in res.checks]
    finally:
        subprocess.run(["docker", "kill", holder], capture_output=True)


def test_sandbox_uids_are_distinct_and_unused(image, monkeypatch):
    """Two live allocations never share a UID, and a UID with a running process is skipped."""
    from tracecontract.sandbox import docker_runner as dr

    holder_uid = 23456
    holder = f"tc-uidholder-{holder_uid}"
    subprocess.run(["docker", "run", "-d", "--rm", "--network", "none", "--name", holder, "--user", f"{holder_uid}:{holder_uid}",
                    image, "sleep", "60"], check=True, capture_output=True)
    try:
        picks = iter([holder_uid, 30001, 30001, 30002])

        class FakeRandom:
            def randrange(self, a, b):
                return next(picks)

        monkeypatch.setattr(dr.secrets, "SystemRandom", lambda: FakeRandom())
        with dr.sandbox_uid() as u1:
            with dr.sandbox_uid() as u2:
                assert (u1, u2) == (30001, 30002)
    finally:
        subprocess.run(["docker", "kill", holder], capture_output=True)
