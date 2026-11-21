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
NPROC_LIMIT = int(os.environ.get("TC_SANDBOX_NPROC", "256"))  # per container UID (D29); below --pids-limit 512
OUTPUT_TAIL = 200_000
MARKER = "<<TC_RESULT>>"
# The trusted conversion of a result that json.dumps cannot encode keeps this many levels of nesting (0.3.5).
ENCODE_MAX_DEPTH = 100
# The longest result message that run_python can read back: its marker line, MARKER + message + "|" + MAC + "\n",
# must fit in the last OUTPUT_TAIL bytes of the child's output (run_python finds the marker even at their start).
MAX_PAYLOAD = OUTPUT_TAIL - len(MARKER + "|" + "0" * 64 + "\n")

# Calls that detected tampering are recorded here and reported by the runner.
TAMPER_EVENTS: list[dict[str, Any]] = []

# The child is started with ``-s -S -P`` (no user site, no automatic ``site``, no
# script directory on sys.path) and WITHOUT ``PYTHONPATH``: the interpreter imports
# modules such as ``encodings`` from sys.path while it starts, before the wrapper's
# first line runs, so no candidate directory may be on sys.path at that point
# (decision log D40; harness 0.3.1 still exported PYTHONPATH at start-up). The wrapper
# also removes any candidate directory from sys.path, enables site-packages, imports
# the trusted modules it needs, and only then puts the candidate's directories on
# sys.path and restores ``PYTHONPATH`` in ``os.environ`` (for subprocesses that the
# snippet starts). A candidate file named like a stdlib module (``json.py``,
# ``encodings/``), or a ``sitecustomize.py``/``usercustomize.py`` written at runtime,
# can therefore not replace the code that serialises and signs the result before the
# snippet runs (decision log D36, D40). The modules that ``traceback`` imports lazily
# while it formats an exception (``ast``, ``unicodedata``) are imported with the trusted
# ones, and as soon as the snippet returns or raises, the wrapper puts the trusted
# import path back (sys.path, sys.meta_path, importer cache) before it formats, serialises
# or signs anything, so the wrapper itself does not import from a candidate directory
# (decision log D44; harness 0.3.2 did). Methods that candidate objects define still run
# while the result is formatted and encoded: ``__repr__`` of a value that JSON cannot
# represent, ``__str__`` of an exception, a metaclass's ``__name__`` for ``error_type``,
# ``items()`` or ``__iter__`` of a dict or list subclass and the keys' comparisons while
# ``json.dumps`` encodes and sorts, and a module's ``__getattr__`` or ``__dir__`` for
# traceback suggestions. They run without the candidate directories on ``sys.path``, so
# one that imports a candidate module fails, and a package-relative import inside one can
# still load candidate code (decision log D46).
#
# What harness 0.3.5 guarantees (protocol v0.8 §16.1; 0.3.4 claimed this but caught only
# failures of repr(), str() and traceback formatting, D51): an exception raised while the
# result is formatted or encoded never turns a successful call into a failed one, never
# changes ``error_type`` and never leaves the call without a result.
# * A failing ``__repr__`` or ``__str__`` becomes a placeholder naming the type (since
#   0.3.4). Placeholders read the type's name as an exact str, with type's own
#   ``__name__`` descriptor and ``str.__str__``, so formatting one runs no candidate code.
# * A result that ``json.dumps`` cannot encode (keys of mixed or non-string types, a cycle,
#   deep nesting, a subclass whose methods raise, an int beyond the digit limit) is
#   converted by ``_tc_plain``. It reads only exact built-in types, with unbound methods,
#   and so calls no candidate method. Keys become strings, and a dict whose keys collide as
#   strings becomes a list of [key, value] pairs. A cycle, a container nested more than
#   ENCODE_MAX_DEPTH levels deep and every other value become placeholders naming the type.
# * If that fails too, or the message would be longer than MAX_PAYLOAD (the output that
#   run_python reads back), a last-resort message keeps ``ok`` and ``error_type`` and
#   replaces the value or the error message by a placeholder.
# * A ``sys.stdout`` that the snippet closed or replaced is flushed inside a try, so it
#   cannot keep the signed message from being written to file descriptor 1.
# Limits: candidate code that runs while the result is formatted or written, or a thread or
# process the snippet started, can still end the call (no result) or stall it (a timeout);
# encoding a very large result counts towards the call's timeout; a process that has
# exhausted its memory limit may report a MemoryError or no result; and a failed call
# whose type name alone is longer than MAX_PAYLOAD loses its result, a failure either way.
# Code that the snippet runs, directly or through candidate modules it imports, runs in
# the same process and can still change what that call reports (the documented residual
# risk).
_WRAPPER = r'''
import sys as _tc_sys
_tc_cand = %(cand_paths)r
_tc_sys.path[:] = [p for p in _tc_sys.path if p not in _tc_cand and p not in ("", ".")]
import site as _tc_site
_tc_site.main()
import os as _tc_os, json as _tc_json, hmac as _tc_hmac, hashlib as _tc_hashlib, traceback as _tc_traceback
import ast as _tc_ast, unicodedata as _tc_unicodedata, linecache as _tc_linecache, tokenize as _tc_tokenize
_tc_trusted_path = list(_tc_sys.path)
_tc_trusted_meta_path = list(_tc_sys.meta_path)
_tc_sys.path[0:0] = %(late_paths)r
_tc_pp = %(pythonpath)r
if _tc_pp is not None:
    _tc_os.environ["PYTHONPATH"] = _tc_pp
del _tc_pp
def _tc_trust():
    # New list objects: a value the snippet returns that refers to the old lists is left as it was.
    _tc_sys.path = list(_tc_trusted_path)
    _tc_sys.meta_path = list(_tc_trusted_meta_path)
    _tc_sys.path_importer_cache.clear()
_tc_type_name = type.__dict__["__name__"].__get__
def _tc_tname(o):
    # The name of o's type as an exact str: type's own descriptor, and str.__str__, which copies
    # a str subclass without calling its methods. No candidate method runs (0.3.5).
    try:
        return str.__str__(_tc_type_name(type(o)))
    except BaseException:  # noqa: BLE001
        return "object"
def _tc_ename(e):
    # error_type as 0.3.3 reports it (a metaclass may define __name__), as an exact str (0.3.5).
    try:
        return str.__str__(type(e).__name__)
    except BaseException:  # noqa: BLE001
        return _tc_tname(e)
def _tc_default(o):
    # Formatting can run candidate code (a __repr__) after the trusted path is restored;
    # a failure there becomes a placeholder and never changes the outcome (0.3.4).
    try:
        return repr(o)
    except BaseException:  # noqa: BLE001
        return "<unformattable %%s>" %% _tc_tname(o)
def _tc_text(fn, fallback):
    try:
        return fn()
    except BaseException:  # noqa: BLE001
        return fallback
def _tc_plain(o, depth, path):
    # Trusted conversion of a result that json.dumps cannot encode (0.3.5): only exact built-in
    # types are read, with unbound methods, so no candidate method runs. Anything else, a cycle
    # (path holds the ids of the containers above o) or a container too deeply nested becomes a
    # placeholder naming the type.
    t = type(o)
    if o is None or t is bool or t is str or t is float:
        return o
    if t is int:
        try:
            int.__repr__(o)  # beyond the interpreter's digit limit an int cannot be written
            return o
        except BaseException:  # noqa: BLE001
            return "<unformattable int>"
    if t is not list and t is not tuple and t is not dict:
        return "<unformattable %%s>" %% _tc_tname(o)
    if depth >= %(max_depth)d:
        return "<too deep %%s>" %% _tc_tname(o)
    if id(o) in path:
        return "<cycle %%s>" %% _tc_tname(o)
    path.add(id(o))
    try:
        if t is not dict:
            return [_tc_plain(x, depth + 1, path) for x in o]
        pairs = [[_tc_plain(k, depth + 1, path), _tc_plain(v, depth + 1, path)] for k, v in dict.items(o)]
        keys = [k if type(k) is str else _tc_json.dumps(k) for k, _ in pairs]
        if len(set(keys)) < len(keys):
            return pairs  # keys that are equal as strings: [key, value] pairs, in the dict's order
        return dict(zip(keys, [v for _, v in pairs]))
    finally:
        path.discard(id(o))
def _tc_last(res, why):
    # Last resort (0.3.5): ok and error_type exactly as they are, the rest a short placeholder.
    if res["ok"] is True:
        return _tc_json.dumps({"ok": True, "value": "<%%s %%s>" %% (why, _tc_tname(res["value"])[:200])})
    return _tc_json.dumps({"error": "<%%s error message>" %% why, "error_type": res["error_type"], "ok": False},
                          sort_keys=True)
def _tc_payload(res):
    # As in 0.3.3 when json.dumps can encode res; otherwise res converted by _tc_plain; otherwise,
    # or when the message would not fit in the output run_python reads back, the last resort.
    try:
        text = _tc_json.dumps(res, default=_tc_default, sort_keys=True)
    except BaseException:  # noqa: BLE001
        try:
            text = _tc_json.dumps({k: _tc_plain(v, 0, set()) for k, v in res.items()}, sort_keys=True)
        except BaseException:  # noqa: BLE001
            return _tc_last(res, "unencodable")
    if len(text) > %(max_payload)d:
        return _tc_last(res, "too large")
    return text
def _tc_main():
    key = _tc_os.read(%(keyfd)d, 64)
    _tc_os.close(%(keyfd)d)
    marker = %(marker)r
    snippet = %(snippet)r
    ns = {"__name__": "__tc_snippet__"}
    try:
        exec(compile(snippet, "<tc-snippet>", "exec"), ns)
        _tc_trust()
        res = {"ok": True, "value": ns.get("result")}
    except BaseException as e:  # noqa: BLE001 - report every failure as data
        _tc_trust()
        et = _tc_ename(e)
        res = {"ok": False, "error_type": et,
               "error": _tc_text(lambda: str(e)[:4000], "<unformattable %%s>" %% et),
               "traceback": _tc_text(lambda: _tc_traceback.format_exc()[-4000:], "<traceback unavailable>")}
    payload = _tc_payload(res)
    mac = _tc_hmac.new(key, payload.encode("utf-8"), _tc_hashlib.sha256).hexdigest()
    _tc_text(lambda: _tc_sys.stdout.flush(), None)  # a stdout that the snippet closed or replaced
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
        # glibc reserves a 64 MiB malloc arena per thread (up to 8 x CPUs) and never
        # releases it; under RLIMIT_AS that capped candidate code at ~21 threads and made
        # long threaded test sessions stall nondeterministically (decision log D30).
        "MALLOC_ARENA_MAX": "2",
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
           env: dict[str, str], pass_fds: tuple[int, ...] = ()) -> tuple[int | None, str, str, bool]:
    """Start ``argv`` as the sandbox user with exactly the environment ``env``."""
    _check_sandbox_home()
    out_f = tempfile.TemporaryFile()
    err_f = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=out_f,
        stderr=err_f,
        cwd=cwd or WORKDIR,
        env=env,
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


def _in_workdir(entry: str) -> str:
    """A PYTHONPATH entry as the child's interpreter resolves it (relative to WORKDIR; empty = WORKDIR)."""
    return os.path.normpath(os.path.join(WORKDIR, entry)) if entry else WORKDIR


def run_python(snippet: str, *, timeout: float = 20.0, env: dict[str, str] | None = None) -> CallResult:
    """Execute ``snippet`` as the sandbox user; the snippet should assign ``result``.

    The value of ``result`` is returned in :attr:`CallResult.value`, JSON-serialised as in
    0.3.3 (a value that JSON cannot represent is given as its ``repr``). A result that
    cannot be encoded that way is converted by trusted code or replaced by a placeholder
    naming the type (see the comment above ``_WRAPPER``). Exceptions inside the snippet are
    returned as ``ok=False`` with the exception type and message.
    """
    key = secrets.token_bytes(32)
    r, w = os.pipe()
    os.write(w, key)
    os.close(w)
    cand_paths = [_in_workdir(x) for x in CANDIDATE_PYTHONPATH.split(os.pathsep) if x]
    child_env = _sandbox_env(env)
    # PYTHONPATH is withheld from the interpreter's start-up and restored by the wrapper
    # (D40). Its entries are resolved against the child's working directory, as the
    # interpreter would resolve them, so the snippet sees the same sys.path and os.environ
    # as when PYTHONPATH was read at start-up.
    pythonpath = child_env.pop("PYTHONPATH", None)
    pp_entries = [_in_workdir(x) for x in pythonpath.split(os.pathsep)] if pythonpath else []
    late_paths = cand_paths + [x for x in pp_entries if x not in cand_paths]
    code = _WRAPPER % {"marker": MARKER, "snippet": snippet, "keyfd": r, "cand_paths": cand_paths,
                       "late_paths": late_paths, "pythonpath": pythonpath, "max_depth": ENCODE_MAX_DEPTH,
                       "max_payload": MAX_PAYLOAD}
    fd, path = tempfile.mkstemp(prefix="tc_call_", suffix=".py", dir="/tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(code)
    os.chmod(path, 0o644)
    try:
        rc, stdout, stderr, timed_out = _spawn([PYTHON, "-s", "-S", "-P", path], timeout=timeout, input_bytes=None, cwd=None,
                                               env=child_env, pass_fds=(r,))
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
    """Run a command (e.g. a CLI entry point) as the sandbox user.

    The command starts with ``PYTHONPATH`` set to the candidate directories, so a
    Python command imports candidate code from its first line; nothing it reports is
    authenticated. The repository-test baseline (B1) uses this and is in-process.
    """
    rc, stdout, stderr, timed_out = _spawn(
        list(argv), timeout=timeout, input_bytes=None if input_text is None else input_text.encode("utf-8"),
        cwd=cwd, env=_sandbox_env(env),
    )
    return CmdResult(rc, stdout, stderr, timed_out)
