"""In-container helper for process-separated verifier tests.

This module is imported ONLY by the trusted grader process (root, inside the task
container). Verifier tests must interact with candidate code exclusively through
:func:`run_python` and :func:`run_cmd`, which execute candidate code in a child
process running as the unprivileged sandbox user. Consequently:

* candidate code never executes inside the grader process;
* the sandbox user cannot read the hidden tests (/grader is root-only) or write the
  results directory (/results is root-only);
* each call has its own timeout and resource limits;
* every result returned from a ``run_python`` call is authenticated with a
  per-call HMAC key passed over an inherited pipe, so generic tampering with the
  child's stdout (for example rewriting failure flags) is detected and reported.

Residual risk (documented): code running inside the child controls what that child
reports. A targeted attack that introspects the wrapper to steal the per-call key
could forge results for that call. Verifier tests therefore must assert on concrete
values returned by candidate code, never only on the absence of an exception.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import resource
import secrets
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

SANDBOX_UID = int(os.environ.get("TC_SANDBOX_UID", "1001"))
SANDBOX_GID = int(os.environ.get("TC_SANDBOX_GID", "1001"))
WORKDIR = os.environ.get("TC_WORKDIR", "/work")
CANDIDATE_PYTHONPATH = os.environ.get("TC_CANDIDATE_PYTHONPATH", WORKDIR)
PYTHON = os.environ.get("TC_SANDBOX_PYTHON", "/usr/local/bin/python3")
MEM_LIMIT = int(os.environ.get("TC_SANDBOX_MEM_BYTES", str(1536 * 1024 * 1024)))
FSIZE_LIMIT = int(os.environ.get("TC_SANDBOX_FSIZE_BYTES", str(64 * 1024 * 1024)))
NPROC_LIMIT = int(os.environ.get("TC_SANDBOX_NPROC", "64"))
OUTPUT_TAIL = 200_000
MARKER = "<<TC_RESULT>>"

# Calls that detected tampering are recorded here and reported by the runner.
TAMPER_EVENTS: list[dict[str, Any]] = []

_WRAPPER = r'''
import os as _tc_os, sys as _tc_sys, json as _tc_json, hmac as _tc_hmac, hashlib as _tc_hashlib
def _tc_main():
    key = _tc_os.read(%(keyfd)d, 64)
    _tc_os.close(%(keyfd)d)
    marker = %(marker)r
    snippet = %(snippet)r
    ns = {"__name__": "__tc_snippet__"}
    try:
        exec(compile(snippet, "<tc-snippet>", "exec"), ns)
        res = {"ok": True, "value": ns.get("result")}
    except BaseException as e:  # noqa: BLE001 - report every failure as data
        import traceback
        res = {"ok": False, "error_type": type(e).__name__, "error": str(e)[:4000],
               "traceback": traceback.format_exc()[-4000:]}
    try:
        payload = _tc_json.dumps(res, default=repr, sort_keys=True)
    except Exception as e:  # noqa: BLE001
        payload = _tc_json.dumps({"ok": False, "error_type": "SerializationError", "error": repr(e)})
    mac = _tc_hmac.new(key, payload.encode("utf-8"), _tc_hashlib.sha256).hexdigest()
    _tc_sys.stdout.flush()
    _tc_os.write(1, ("\n" + marker + payload + "|" + mac + "\n").encode("utf-8"))
_tc_main()
'''


@dataclass
class CallResult:
    ok: bool
    value: Any = None
    error_type: str | None = None
    error: str | None = None
    traceback: str | None = None
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    timed_out: bool = False
    tampered: bool = False
    notes: list[str] = field(default_factory=list)

    def __repr__(self) -> str:  # concise failure messages in pytest output
        if self.ok:
            return f"CallResult(ok=True, value={self.value!r})"
        return (
            f"CallResult(ok=False, error_type={self.error_type!r}, error={self.error!r}, "
            f"timed_out={self.timed_out}, tampered={self.tampered}, stderr_tail={self.stderr[-800:]!r})"
        )


def _limits(cpu_seconds: int):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))
        resource.setrlimit(resource.RLIMIT_FSIZE, (FSIZE_LIMIT, FSIZE_LIMIT))
        resource.setrlimit(resource.RLIMIT_NPROC, (NPROC_LIMIT, NPROC_LIMIT))

    return apply


def _sandbox_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": SANDBOX_HOME,
        "USER": "sandbox",  # the per-run sandbox UID has no passwd entry
        "LOGNAME": "sandbox",
        "PYTHONPATH": CANDIDATE_PYTHONPATH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
    }
    if extra:
        env.update(extra)
    return env


SANDBOX_HOME = "/tmp/sandbox-home"


def prepare_sandbox_home() -> None:
    """Create the sandbox HOME once, before any candidate code has run.

    Called by the runner at start-up. Root never chowns paths under /tmp after
    candidate code may have run, because the sandbox user could have replaced
    them with symlinks into root-only locations.
    """
    os.mkdir(SANDBOX_HOME, 0o700)
    os.chown(SANDBOX_HOME, SANDBOX_UID, SANDBOX_GID)


def _check_sandbox_home() -> None:
    st = os.lstat(SANDBOX_HOME)  # never follow symlinks
    import stat as _stat
    if not _stat.S_ISDIR(st.st_mode) or st.st_uid != SANDBOX_UID:
        raise RuntimeError("sandbox home is not a sandbox-owned directory (possible tampering)")


def reap_sandbox_processes() -> int:
    """SIGKILL every process owned by the sandbox user (e.g. daemonised leftovers)."""
    killed = 0
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/status", encoding="utf-8") as fh:
                uid_line = next((ln for ln in fh if ln.startswith("Uid:")), "")
            if uid_line and int(uid_line.split()[1]) == SANDBOX_UID:
                os.kill(int(entry), signal.SIGKILL)
                killed += 1
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
    return killed


def _spawn(argv: list[str], *, timeout: float, input_bytes: bytes | None, cwd: str | None,
           env: dict[str, str] | None, pass_fds: tuple[int, ...] = ()) -> tuple[int | None, str, str, bool]:
    _check_sandbox_home()
    out_f = tempfile.TemporaryFile()
    err_f = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=out_f,
        stderr=err_f,
        cwd=cwd or WORKDIR,
        env=_sandbox_env(env),
        user=SANDBOX_UID,
        group=SANDBOX_GID,
        extra_groups=[],
        start_new_session=True,
        preexec_fn=_limits(int(timeout) + 2),
        pass_fds=pass_fds,
        close_fds=True,
    )
    timed_out = False
    try:
        proc.communicate(input=input_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        # Kill the whole process group (the child may have spawned others).
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        reap_sandbox_processes()
    out_f.seek(0, os.SEEK_END)
    size = out_f.tell()
    out_f.seek(max(0, size - OUTPUT_TAIL))
    stdout = out_f.read().decode("utf-8", errors="replace")
    err_f.seek(0, os.SEEK_END)
    size = err_f.tell()
    err_f.seek(max(0, size - OUTPUT_TAIL))
    stderr = err_f.read().decode("utf-8", errors="replace")
    out_f.close()
    err_f.close()
    return (None if timed_out else proc.returncode), stdout, stderr, timed_out


def run_python(snippet: str, *, timeout: float = 20.0, env: dict[str, str] | None = None) -> CallResult:
    """Execute ``snippet`` as the sandbox user; the snippet should assign ``result``.

    The value of ``result`` (JSON-serialised, falling back to ``repr``) is returned
    in :attr:`CallResult.value`. Exceptions inside the snippet are returned as
    ``ok=False`` with the exception type and message.
    """
    key = secrets.token_bytes(32)
    r, w = os.pipe()
    os.write(w, key)
    os.close(w)
    code = _WRAPPER % {"marker": MARKER, "snippet": snippet, "keyfd": r}
    fd, path = tempfile.mkstemp(prefix="tc_call_", suffix=".py", dir="/tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(code)
    os.chmod(path, 0o644)
    try:
        rc, stdout, stderr, timed_out = _spawn([PYTHON, path], timeout=timeout, input_bytes=None, cwd=None, env=env, pass_fds=(r,))
    finally:
        os.close(r)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    if timed_out:
        return CallResult(ok=False, error_type="Timeout", error=f"exceeded {timeout}s", stdout=stdout, stderr=stderr, timed_out=True)
    lines = [ln for ln in stdout.splitlines() if ln.startswith(MARKER)]
    if not lines:
        return CallResult(ok=False, error_type="NoResult", error="sandbox produced no result (crashed or exited early)",
                          stdout=stdout, stderr=stderr, returncode=rc)
    last = lines[-1][len(MARKER):]
    payload, sep, mac = last.rpartition("|")
    expected = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not sep or not hmac.compare_digest(mac.strip(), expected):
        TAMPER_EVENTS.append({"kind": "result_mac_mismatch", "snippet_sha256": hashlib.sha256(snippet.encode()).hexdigest()})
        return CallResult(ok=False, error_type="Tampered", error="result authentication failed",
                          stdout=stdout, stderr=stderr, returncode=rc, tampered=True)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return CallResult(ok=False, error_type="BadResult", error="unparseable result", stdout=stdout, stderr=stderr, returncode=rc)
    return CallResult(
        ok=bool(data.get("ok")),
        value=data.get("value"),
        error_type=data.get("error_type"),
        error=data.get("error"),
        traceback=data.get("traceback"),
        stdout=stdout,
        stderr=stderr,
        returncode=rc,
    )


@dataclass
class CmdResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


def run_cmd(argv: list[str], *, timeout: float = 30.0, input_text: str | None = None, cwd: str | None = None,
            env: dict[str, str] | None = None) -> CmdResult:
    """Run a command (e.g. a CLI entry point) as the sandbox user."""
    rc, stdout, stderr, timed_out = _spawn(
        list(argv), timeout=timeout, input_bytes=None if input_text is None else input_text.encode("utf-8"),
        cwd=cwd, env=env,
    )
    return CmdResult(rc, stdout, stderr, timed_out)
