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
        assert r.ok and r.value < 256, r  # bounded by RLIMIT_NPROC (256) of the per-container UID

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


ARENA_PROBE = textwrap.dedent('''
    from tc_sandbox import run_python

    SNIPPET = (
        "import threading\\n"
        "def work():\\n"
        "    x = [bytearray(4096) for _ in range(256)]\\n"
        "    del x\\n"
        "for _ in range(30):\\n"
        "    ts = [threading.Thread(target=work) for _ in range(32)]\\n"
        "    [t.start() for t in ts]\\n"
        "    [t.join() for t in ts]\\n"
        "ev = threading.Event()\\n"
        "n = 0\\n"
        "try:\\n"
        "    for _ in range(60):\\n"
        "        threading.Thread(target=ev.wait, daemon=True).start()\\n"
        "        n += 1\\n"
        "except RuntimeError:\\n"
        "    pass\\n"
        "ev.set()\\n"
        "result = n"
    )

    def test_threads_after_churn():
        r = run_python(SNIPPET, timeout=60)
        assert r.ok, r
        assert r.value == 60, r.value
''')


def test_thread_capacity_after_churn(image, tmp_path):
    """Regression (D30): malloc arenas must not exhaust the address-space cap.

    Under harness 0.2.0 this probe started 21 of 60 threads (VmSize at the 1.5 GiB
    RLIMIT_AS); with MALLOC_ARENA_MAX=2 all 60 start.
    """
    base = tmp_path / "base"
    base.mkdir()
    (base / "calc.py").write_text("x = 1\n")
    tdir = tmp_path / "task"
    (tdir / "tests").mkdir(parents=True)
    (tdir / "tests" / "test_arena.py").write_text(ARENA_PROBE)
    spec = VerifierSpec(verifier_id="arena", task_id="t", condition=VerifierCondition.reference_check,
                        isolation=Isolation.process_separated, test_dir="tests",
                        checks=[CheckSpec(check_id=c) for c in discover_checks(tdir / "tests")], content_sha256="x")
    cand = Candidate(candidate_id="noop", task_id="t", origin=CandidateOrigin.noop, split=Split.eval, patch="",
                     patch_sha256=sha256_text(""), produced_by="fixture")
    res = verify_candidate(image=image, base_dir=base, spec=spec, task_dir=tdir, candidate=cand, run_id="iso")
    assert res.outcome == Outcome.passed, [c.message[-400:] for c in res.checks]


FORGER = '''import atexit
import re
import sys


def add(a, b):
    raise NotImplementedError


def _forge():
    for arg in sys.argv:
        if arg.startswith("--junitxml="):
            path = arg.split("=", 1)[1]
            try:
                xml = open(path).read()
                xml = re.sub(r"<failure[^>]*>.*?</failure>", "", xml, flags=re.S)
                xml = re.sub(r'failures="[0-9]+"', 'failures="0"', xml)
                open(path, "w").write(xml)
            except OSError:
                pass


atexit.register(_forge)
'''


def test_in_process_repo_tests_report_is_forgeable_known_limitation(image, tmp_path):
    """Characterises a documented limitation of the B1 baseline (paper, reproducibility section).

    In repository-test mode pytest imports candidate code into the process that writes
    the report, so a deliberately adversarial candidate can rewrite that report. The
    process-separated verifiers are not affected. If this test starts failing, the
    limitation has been fixed: update the documentation.
    """
    base = tmp_path / "base"
    (base / "tests").mkdir(parents=True)
    (base / "calc.py").write_text("def add(a, b):\n    raise NotImplementedError\n")
    (base / "tests" / "__init__.py").write_text("")
    (base / "tests" / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 1) == 2\n")
    tdir = tmp_path / "task"
    (tdir / "overlay" / "tests").mkdir(parents=True)
    shutil.copyfile(base / "tests" / "test_calc.py", tdir / "overlay" / "tests" / "test_calc.py")
    spec = VerifierSpec(verifier_id="b1", task_id="t", condition=VerifierCondition.repo_tests, isolation=Isolation.in_process,
                        test_dir="overlay", checks=[CheckSpec(check_id="tests.test_calc::test_add")], content_sha256="x")

    def grade(files):
        cand = _candidate(base, tmp_path, "c" + str(len(files.get("calc.py", ""))), files)
        return verify_candidate(image=image, base_dir=base, spec=spec, task_dir=tdir, candidate=cand, run_id="iso",
                                repo_test_args=["tests"])

    honest_wrong = grade({"calc.py": "def add(a, b):\n    return a - b\n"})
    assert honest_wrong.outcome == Outcome.task_failure, honest_wrong
    forged = grade({"calc.py": FORGER})
    assert forged.outcome == Outcome.passed, (forged.outcome, forged.diagnostics)  # known limitation: forgery succeeds


JSON_SHADOW = '''"""Candidate-supplied json.py that forges every reported value (decision log D36)."""
import os as _os
import re as _re
import sys as _sys

_here = _os.path.dirname(_os.path.abspath(__file__))
_saved = _sys.path[:]
_sys.path[:] = [p for p in _sys.path if _os.path.abspath(p or ".") != _here]
_mod = _sys.modules.pop("json")
import json as _real  # noqa: E402  (the real stdlib json)
_sys.modules["json"] = _mod
_sys.path[:] = _saved
loads, JSONDecodeError = _real.loads, _real.JSONDecodeError


def dumps(obj, **kw):
    frame = _sys._getframe(1)
    snippet = frame.f_locals.get("snippet", "") if frame is not None else ""
    m = _re.search(r"add\\((-?\\d+),\\s*(-?\\d+)\\)", snippet)
    if m and isinstance(obj, dict) and "ok" in obj:
        obj = {"ok": True, "value": int(m.group(1)) + int(m.group(2))}
    return _real.dumps(obj, **kw)
'''


def test_stdlib_shadow_cannot_forge_results(image, task, tmp_path):
    """Regression (D36): a candidate json.py must not replace the wrapper's serialiser."""
    cand = _candidate(task[0], tmp_path, "json_shadow", {"calc.py": "def add(a, b):\n    return a - b\n",
                                                          "json.py": JSON_SHADOW})
    res = _grade(image, task, cand)
    assert res.outcome == Outcome.task_failure, (res.outcome, [c.message[-300:] for c in res.checks])


ENCODINGS_SHADOW = '''"""Candidate-supplied encodings package (decision log D40).

The interpreter imports ``encodings`` from sys.path while it starts, before the first
line of the wrapper runs. This one loads the real package, then puts a directory that
is not one of the candidate paths at the front of sys.path, so that the wrapper's
later ``import json`` finds the forging json.py stored there.
"""
import sys as _sys

_here = __file__.rsplit("/", 2)[0]
del _sys.modules["encodings"]
_saved = _sys.path[:]
_sys.path[:] = [p for p in _sys.path if p != _here]
import encodings as _real  # noqa: E402  (the stdlib package; registers the codec search)
_sys.path[:] = _saved
_sys.modules["encodings"] = _real
_sys.path.insert(0, _here + "/_tc_forge")
'''


def test_startup_encodings_shadow_cannot_forge_results(image, task, tmp_path):
    """Regression (D40): a candidate ``encodings`` package must not load when the child starts.

    Under harness 0.3.1 the candidate directory was on PYTHONPATH at interpreter start,
    so this candidate received reward 1.0 in this probe.
    """
    cand = _candidate(task[0], tmp_path, "encodings_shadow", {
        "calc.py": "def add(a, b):\n    return a - b\n",
        "encodings/__init__.py": ENCODINGS_SHADOW,
        "_tc_forge/json.py": JSON_SHADOW,
    })
    res = _grade(image, task, cand)
    assert res.outcome == Outcome.task_failure, (res.outcome, [c.message[-300:] for c in res.checks])


AST_SHADOW = '''"""Candidate-supplied ast.py (decision log D44).

Python 3.12's traceback imports ``ast`` lazily while it formats an exception. If the
grader's wrapper formats the snippet's exception with the candidate directories still
first on sys.path, this module loads inside the trusted reporting code and makes the
signed result say the call succeeded.
"""
import sys as _sys

_here = __file__.rsplit("/", 1)[0]
_saved = _sys.path[:]
_sys.path[:] = [p for p in _sys.path if p != _here]
del _sys.modules["ast"]
import ast as _real  # noqa: E402  (the stdlib module, so traceback keeps working)
_sys.path[:] = _saved
_sys.modules["ast"] = _real
import json as _json  # noqa: E402

_orig = _json.dumps


def _forge(obj, **kw):
    if isinstance(obj, dict) and "ok" in obj:
        obj = {"ok": True, "value": "FORGED"}
    return _orig(obj, **kw)


_json.dumps = _forge
'''

ERROR_PATH_PROBE = '''from tc_sandbox import run_python


def test_error_path_result_is_not_forged():
    r = run_python("result = 1 / 0", timeout=10)
    assert not r.ok and r.error_type == "ZeroDivisionError", r
'''


def test_error_path_lazy_import_cannot_forge_results(image, tmp_path):
    """Regression (D44): a candidate ast.py must not load while the wrapper formats an exception.

    The snippet imports no candidate code. Under harness 0.3.2 the forged result
    (ok=True) was reported with a valid signature.
    """
    base = tmp_path / "base"
    base.mkdir()
    (base / "calc.py").write_text("x = 1\n")
    tdir = tmp_path / "task"
    (tdir / "tests").mkdir(parents=True)
    (tdir / "tests" / "test_errpath.py").write_text(ERROR_PATH_PROBE)
    spec = VerifierSpec(verifier_id="errpath", task_id="t", condition=VerifierCondition.reference_check,
                        isolation=Isolation.process_separated, test_dir="tests",
                        checks=[CheckSpec(check_id=c) for c in discover_checks(tdir / "tests")], content_sha256="x")
    cand = _candidate(base, tmp_path, "ast_shadow", {"ast.py": AST_SHADOW})
    res = verify_candidate(image=image, base_dir=base, spec=spec, task_dir=tdir, candidate=cand, run_id="iso")
    assert res.outcome == Outcome.passed, [c.message[-500:] for c in res.checks]


def test_runtime_startup_hooks_not_loaded(image, tmp_path):
    """Regression (D36, D40): hooks and packages written to /work, HOME or /tmp at runtime never load in later calls."""
    base = tmp_path / "base"
    base.mkdir()
    (base / "calc.py").write_text("x = 1\n")
    tdir = tmp_path / "task"
    (tdir / "tests").mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent / "fixtures" / "sandbox_probes" / "startup_probe.py", tdir / "tests" / "test_startup.py")
    spec = VerifierSpec(verifier_id="startup", task_id="t", condition=VerifierCondition.reference_check,
                        isolation=Isolation.process_separated, test_dir="tests",
                        checks=[CheckSpec(check_id=c) for c in discover_checks(tdir / "tests")], content_sha256="x")
    cand = Candidate(candidate_id="noop", task_id="t", origin=CandidateOrigin.noop, split=Split.eval, patch="",
                     patch_sha256=sha256_text(""), produced_by="fixture")
    res = verify_candidate(image=image, base_dir=base, spec=spec, task_dir=tdir, candidate=cand, run_id="iso")
    assert res.outcome == Outcome.passed, [c.message[-500:] for c in res.checks]


FORMAT_PROBE = '''from tc_sandbox import run_python


def test_value_whose_repr_imports_a_candidate_module():
    r = run_python("from fmtmod import Box\\nresult = Box()", timeout=10)
    assert r.ok, r
    assert r.value == "<unformattable Box>", r


def test_exception_whose_str_imports_a_candidate_module():
    r = run_python("from fmtmod import Boom\\nraise Boom()", timeout=10)
    assert not r.ok and r.error_type == "Boom", r
    assert r.error == "<unformattable Boom>", r
'''

FMT_MODULE = '''class Box:
    def __repr__(self):
        import fmthelper  # a candidate module, not importable once the trusted path is restored
        return fmthelper.label(self)


class Boom(Exception):
    def __str__(self):
        import fmthelper
        return fmthelper.label(self)
'''


def test_formatting_failure_never_changes_the_outcome(image, tmp_path):
    """Harness 0.3.4 (protocol v0.7 §15.3, D46): formatting runs after the trusted path is
    restored, so a candidate __repr__ or __str__ that imports a candidate module fails.
    The failure must become a placeholder; under 0.3.3 the successful call was reported
    as a SerializationError."""
    base = tmp_path / "base"
    base.mkdir()
    (base / "calc.py").write_text("x = 1\n")
    tdir = tmp_path / "task"
    (tdir / "tests").mkdir(parents=True)
    (tdir / "tests" / "test_fmt.py").write_text(FORMAT_PROBE)
    spec = VerifierSpec(verifier_id="fmt", task_id="t", condition=VerifierCondition.reference_check,
                        isolation=Isolation.process_separated, test_dir="tests",
                        checks=[CheckSpec(check_id=c) for c in discover_checks(tdir / "tests")], content_sha256="x")
    cand = _candidate(base, tmp_path, "fmt", {"fmtmod.py": FMT_MODULE, "fmthelper.py": "def label(o):\n    return 'ok'\n"})
    res = verify_candidate(image=image, base_dir=base, spec=spec, task_dir=tdir, candidate=cand, run_id="iso")
    assert res.outcome == Outcome.passed, [c.message[-500:] for c in res.checks]
