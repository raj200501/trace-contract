"""Host-side sandbox runner and trusted outcome aggregation.

The host process is the trusted party. For every (verifier, candidate) pair it:

1. filters the candidate patch through the path policy (``tracecontract.patches``)
   and applies it to a fresh copy of the base snapshot;
2. stages a root-only grader directory (harness + hidden tests) and a root-only
   results directory;
3. runs the grader container with ``--network none``, all capabilities dropped
   except those needed to switch to the sandbox user and kill its processes,
   ``no-new-privileges``, a read-only root filesystem, tmpfs scratch space, and
   CPU / memory / PID limits - no privileged mode and no Docker socket. Candidate
   code runs as a sandbox UID allocated for this container alone (per-user kernel
   limits such as RLIMIT_NPROC are shared by every process of a UID on the host,
   so a fixed UID would couple concurrent runs; decision log D29);
4. recomputes the outcome from ``results.json`` (checking the per-run nonce) in
   :func:`aggregate`. The container exit code is never trusted on its own.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..patches import DEFAULT_PROTECTED, PatchApplyError, apply_patch, filter_patch
from ..schemas import (
    Candidate,
    CheckResult,
    Isolation,
    Outcome,
    VerificationResult,
    VerifierSpec,
)

HARNESS_SRC = Path(__file__).parent / "harness"
HARNESS_VERSION = "tc-harness/0.2.0"
BASE_IMAGE = "python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
DEFAULT_TEST_REQUIREMENTS = (
    "pytest==8.3.5", "hypothesis==6.131.0", "attrs==26.1.0", "iniconfig==2.3.1",
    "packaging==26.3", "pluggy==1.7.0", "sortedcontainers==2.4.0",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SANDBOX_UID_RANGE = (20000, 60000)
_UID_LOCK_DIR = Path(tempfile.gettempdir()) / "tc-sandbox-uids"


def _uid_in_use(uid: int) -> bool:
    """True if any process visible to this host process runs with this real UID."""
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/status", encoding="ascii", errors="replace") as fh:
                for line in fh:
                    if line.startswith("Uid:"):
                        if int(line.split()[1]) == uid:
                            return True
                        break
        except OSError:
            continue
    return False


@contextmanager
def sandbox_uid() -> Iterator[int]:
    """Allocate a sandbox UID used by exactly one grading container on this host.

    The UID is held through an exclusive lock file for the lifetime of the
    container and is never one that a visible process already uses. It has no
    passwd entry; the sandbox environment sets HOME, USER and LOGNAME.
    """
    _UID_LOCK_DIR.mkdir(mode=0o700, exist_ok=True)
    rng = secrets.SystemRandom()
    for _ in range(1000):
        uid = rng.randrange(*SANDBOX_UID_RANGE)
        fd = os.open(_UID_LOCK_DIR / f"{uid}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            continue
        try:
            if _uid_in_use(uid):
                continue
            yield uid
            return
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    raise RuntimeError("could not allocate a free sandbox uid")


@dataclass
class Limits:
    cpus: float = 2.0
    memory: str = "4g"
    pids: int = 512
    wall_s: float = 900.0
    tmp_size: str = "512m"
    work_size: str = "1g"


@dataclass
class RawRun:
    exit_code: int | None
    timed_out: bool
    results: dict[str, Any] | None
    stdout: str
    stderr: str
    wall_s: float
    docker_error: str | None = None
    patch_diagnostics: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def _req_hash(reqs: tuple[str, ...] | list[str], extra: str = "") -> str:
    return hashlib.sha256(("\n".join(sorted(reqs)) + "\n" + extra + "\n" + BASE_IMAGE).encode()).hexdigest()[:16]


def ensure_wheelhouse(reqs: list[str], cache_dir: Path) -> Path:
    """Download pinned wheels on the host (where the proxy CA is trusted)."""
    key = _req_hash(reqs)
    wh = cache_dir / f"wheelhouse-{key}"
    if (wh / ".complete").exists():
        return wh
    wh.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python3", "-m", "pip", "download", "-q", "--only-binary=:all:", "--no-deps",
        "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_17_x86_64", "--platform", "any",
        "--python-version", "3.12", "--implementation", "cp", "-d", str(wh), *reqs,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=900)
    (wh / ".complete").write_text("\n".join(sorted(reqs)) + "\n")
    return wh


def build_env_image(reqs: list[str], cache_dir: Path, *, tag_prefix: str = "tc-env") -> tuple[str, str]:
    """Build (offline) an image with the pinned requirements. Returns (tag, image_id).

    Requirements must be a fully pinned, transitively closed list (``--no-deps``
    is used both for download and install, so nothing unpinned can slip in).
    """
    reqs = sorted(set(reqs))
    key = _req_hash(reqs)
    tag = f"{tag_prefix}:{key}"
    probe = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", tag], capture_output=True, text=True)
    if probe.returncode == 0:
        return tag, probe.stdout.strip()
    wh = ensure_wheelhouse(reqs, cache_dir)
    with tempfile.TemporaryDirectory(prefix="tc_build_") as ctx:
        ctxp = Path(ctx)
        shutil.copytree(wh, ctxp / "wheelhouse")
        (ctxp / "requirements.lock").write_text("\n".join(reqs) + "\n")
        (ctxp / "Dockerfile").write_text(
            f"FROM {BASE_IMAGE}\n"
            "COPY wheelhouse /tmp/wheelhouse\n"
            "COPY requirements.lock /tmp/requirements.lock\n"
            "RUN pip install --no-cache-dir --disable-pip-version-check --no-index --no-deps "
            "--find-links /tmp/wheelhouse -r /tmp/requirements.lock && rm -rf /tmp/wheelhouse\n"
            "RUN useradd --uid 1001 --user-group --no-create-home --shell /usr/sbin/nologin sandbox\n"
            "LABEL org.tracecontract.requirements-hash=" + key + "\n"
        )
        proc = subprocess.run(["docker", "build", "--network", "none", "-q", "-t", tag, str(ctxp)],
                              capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"image build failed: {proc.stderr[-2000:]}")
    image_id = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", tag],
                              capture_output=True, text=True, check=True).stdout.strip()
    return tag, image_id


# ---------------------------------------------------------------------------
# Running the grader
# ---------------------------------------------------------------------------


def _stage_private_dir(prefix: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    os.chmod(d, 0o700)
    return d


def prepare_workspace(base_dir: Path, patch: str, protected: tuple[str, ...] = DEFAULT_PROTECTED) -> tuple[Path | None, list[str], str | None]:
    """Filter + apply a candidate patch. Returns (workspace, diagnostics, error)."""
    approved, rep = filter_patch(patch, protected)
    diags = [f"protected path change removed before grading: {p}" for p in rep.removed_protected]
    if not rep.ok:
        return None, diags + [f"patch rejected: {e}" for e in rep.errors], "patch_rejected"
    try:
        ws, log = apply_patch(base_dir, approved)
    except PatchApplyError as exc:
        return None, diags + [f"patch failed to apply: {exc}"], "patch_apply_failed"
    os.chmod(ws, 0o700)
    return ws, diags, None


def run_grader(
    image: str,
    *,
    workspace: Path,
    mode: Isolation,
    tests_dir: Path | None = None,
    overlay_dir: Path | None = None,
    repo_test_args: list[str] | None = None,
    candidate_pythonpath: str = "/work",
    limits: Limits | None = None,
    nonce: str | None = None,
) -> tuple[RawRun, str]:
    """Run one grading container. Returns (raw_run, nonce)."""
    limits = limits or Limits()
    nonce = nonce or secrets.token_hex(16)
    grader = _stage_private_dir("tc_grader_")
    results = _stage_private_dir("tc_results_")
    name = f"tc-grade-{nonce[:12]}"
    try:
        shutil.copytree(HARNESS_SRC, grader / "harness", ignore=shutil.ignore_patterns("__pycache__"))
        if tests_dir is not None:
            shutil.copytree(tests_dir, grader / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        else:
            (grader / "tests").mkdir()
        if overlay_dir is not None:
            shutil.copytree(overlay_dir, grader / "overlay", symlinks=False)
        runner_mode = "process_separated" if mode == Isolation.process_separated else "repo_tests"
        with sandbox_uid() as uid:
            return _run_container(image, name, grader, results, workspace, nonce, uid, runner_mode,
                                  repo_test_args, candidate_pythonpath, limits)
    finally:
        shutil.rmtree(grader, ignore_errors=True)
        shutil.rmtree(results, ignore_errors=True)


def _run_container(image: str, name: str, grader: Path, results: Path, workspace: Path, nonce: str, uid: int,
                   runner_mode: str, repo_test_args: list[str] | None, candidate_pythonpath: str,
                   limits: Limits) -> tuple[RawRun, str]:
    """One ``docker run`` of the grader with the given sandbox UID (see :func:`sandbox_uid`)."""
    cmd = [
        "docker", "run", "--rm", "--init", "--name", name,
        "--network", "none",
        "--cpus", str(limits.cpus), "--memory", limits.memory, "--memory-swap", limits.memory,
        "--pids-limit", str(limits.pids),
        "--cap-drop", "ALL", "--cap-add", "SETUID", "--cap-add", "SETGID", "--cap-add", "KILL", "--cap-add", "CHOWN",
        "--security-opt", "no-new-privileges",
        "--read-only",
        "--tmpfs", f"/tmp:rw,exec,nosuid,nodev,size={limits.tmp_size},mode=1777",
        "--tmpfs", f"/work:rw,exec,nosuid,nodev,size={limits.work_size},mode=0755",
        "-v", f"{grader}:/grader:ro",
        "-v", f"{workspace}:/mnt/candidate:ro",
        "-v", f"{results}:/results:rw",
        "-e", f"TC_RUN_NONCE={nonce}",
        "-e", f"TC_SANDBOX_UID={uid}", "-e", f"TC_SANDBOX_GID={uid}",
        "-e", f"TC_CANDIDATE_PYTHONPATH={candidate_pythonpath}",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-w", "/grader",
        image,
        "python3", "-I", "/grader/harness/tc_runner.py", "--mode", runner_mode,
    ]
    if runner_mode == "repo_tests":
        cmd += ["--", *(repo_test_args or [])]
    t0 = time.time()
    timed_out = False
    docker_error = None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=limits.wall_s)
        exit_code, out, err = proc.returncode, proc.stdout, proc.stderr
        if exit_code in (125, 126, 127):
            docker_error = f"docker run failed ({exit_code}): {err[-1500:]}"
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        out = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        subprocess.run(["docker", "kill", name], capture_output=True)
    wall = time.time() - t0
    res_path = results / "results.json"
    data = None
    if res_path.is_file() and not res_path.is_symlink():
        try:
            data = json.loads(res_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"status": "unparseable"}
    return RawRun(exit_code, timed_out, data, out[-20000:], err[-20000:], wall, docker_error), nonce


# ---------------------------------------------------------------------------
# Trusted aggregation
# ---------------------------------------------------------------------------


def aggregate(raw: RawRun, spec: VerifierSpec, nonce: str) -> tuple[Outcome, list[CheckResult], list[str]]:
    """Recompute the outcome from raw container output. Never trusts exit codes alone."""
    diags: list[str] = list(raw.patch_diagnostics)
    if raw.timed_out:
        return Outcome.timeout, [], diags + ["container exceeded the wall-clock limit"]
    if raw.docker_error:
        return Outcome.environment_failure, [], diags + [raw.docker_error]
    r = raw.results
    if r is None:
        return Outcome.verifier_error, [], diags + ["no results file was produced"]
    if r.get("nonce") != nonce:
        return Outcome.verifier_error, [], diags + ["stale or foreign results file (nonce mismatch)"]
    if r.get("status") != "completed":
        return Outcome.verifier_error, [], diags + [f"grader did not complete: {r.get('status')} {r.get('error', '')}".strip()]
    if r.get("harness_version") != HARNESS_VERSION:
        diags.append(f"harness version mismatch: {r.get('harness_version')}")
    for t in r.get("tamper_events", []):
        diags.append(f"tamper_detected: {t.get('kind')}")
    in_process = spec.isolation == Isolation.in_process
    if in_process and r.get("timed_out"):
        return Outcome.timeout, [], diags + [f"repository tests exceeded the time limit ({r.get('elapsed_s', 0):.0f} s)"]
    if r.get("collect_errors") and not in_process:
        return Outcome.verifier_error, [], diags + [f"collection error: {c['nodeid']}" for c in r["collect_errors"]]
    reported = {t["nodeid"]: t for t in r.get("tests", [])}
    checks: list[CheckResult] = []
    any_missing = any_setup_error = any_failed = any_skipped = False
    for c in spec.checks:
        t = reported.get(c.check_id)
        if t is None:
            checks.append(CheckResult(check_id=c.check_id, status="missing"))
            any_missing = True
            continue
        st = t.get("outcome") or "error"
        if st == "error" and in_process:
            st = "failed"  # in repo-test mode, errors are usually caused by candidate code
        checks.append(CheckResult(check_id=c.check_id, status=st, duration_s=t.get("duration"), message=(t.get("longrepr") or "")[-1500:]))
        any_setup_error |= st == "error"
        any_failed |= st == "failed"
        any_skipped |= st == "skipped"
    unexpected = sorted(set(reported) - {c.check_id for c in spec.checks})
    if unexpected and not in_process:
        return Outcome.verifier_error, checks, diags + [f"unexpected tests not in verifier spec: {unexpected[:10]}"]
    if any_missing:
        if in_process and r.get("collect_errors"):
            # Candidate broke import/collection of repository tests.
            return Outcome.task_failure, checks, diags + ["repository tests failed to collect"]
        return Outcome.verifier_error, checks, diags + ["expected checks missing from results"]
    if any_setup_error:
        return Outcome.verifier_error, checks, diags + ["verifier setup error"]
    if any_skipped and not any_failed:
        return Outcome.verifier_error, checks, diags + ["a scored check was skipped"]
    if any_failed:
        return Outcome.task_failure, checks, diags
    return Outcome.passed, checks, diags


def verify_candidate(
    *,
    image: str,
    base_dir: Path,
    spec: VerifierSpec,
    task_dir: Path,
    candidate: Candidate,
    run_id: str,
    repeats: int = 1,
    candidate_pythonpath: str = "/work",
    repo_test_args: list[str] | None = None,
    limits: Limits | None = None,
    protected: tuple[str, ...] = DEFAULT_PROTECTED,
) -> VerificationResult:
    """Grade one candidate with one verifier; repeated runs that disagree -> unresolved."""
    started = _now()
    t0 = time.time()
    ws, pdiags, perr = prepare_workspace(base_dir, candidate.patch, protected)
    if ws is None:
        outcome = Outcome.task_failure if perr == "patch_rejected" else Outcome.environment_failure
        return VerificationResult(
            run_id=run_id, task_id=spec.task_id, verifier_id=spec.verifier_id, candidate_id=candidate.candidate_id,
            outcome=outcome, reward=0.0, diagnostics=pdiags, started_at=started, finished_at=_now(),
            wall_s=time.time() - t0, harness_version=HARNESS_VERSION,
        )
    try:
        outcomes = []
        last_checks: list[CheckResult] = []
        all_diags: list[str] = list(pdiags)
        logs = []
        for i in range(repeats):
            tests_dir = (task_dir / spec.test_dir) if spec.isolation == Isolation.process_separated else None
            overlay = (task_dir / spec.test_dir) if spec.isolation == Isolation.in_process else None
            raw, nonce = run_grader(
                image, workspace=ws, mode=spec.isolation, tests_dir=tests_dir, overlay_dir=overlay,
                repo_test_args=repo_test_args, candidate_pythonpath=candidate_pythonpath, limits=limits,
            )
            raw.patch_diagnostics = pdiags
            oc, checks, diags = aggregate(raw, spec, nonce)
            outcomes.append(oc)
            last_checks = checks
            all_diags += [f"[run {i}] {d}" for d in diags if d not in pdiags]
            logs.append(raw.stdout + "\n--stderr--\n" + raw.stderr)
        distinct = set(outcomes)
        if len(distinct) == 1:
            outcome = outcomes[0]
        else:
            outcome = Outcome.unresolved
            all_diags.append(f"repeated runs disagree: {[o.value for o in outcomes]}")
        log_sha = hashlib.sha256("\n=====\n".join(logs).encode()).hexdigest()
        return VerificationResult(
            run_id=run_id, task_id=spec.task_id, verifier_id=spec.verifier_id, candidate_id=candidate.candidate_id,
            outcome=outcome, reward=1.0 if outcome == Outcome.passed else 0.0, checks=last_checks,
            diagnostics=all_diags, started_at=started, finished_at=_now(), wall_s=time.time() - t0,
            harness_version=HARNESS_VERSION, log_sha256=log_sha,
        )
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def resolve_pins(specs: list[str], cache_dir: Path) -> list[str]:
    """Resolve requirement specifiers to a pinned, transitively closed wheel list.

    Uses ``pip download`` (wheels only, so no build code runs on the host) and reads
    the resulting wheel filenames.
    """
    import re as _re

    key = hashlib.sha256("\n".join(sorted(specs)).encode()).hexdigest()[:16]
    d = cache_dir / f"resolve-{key}"
    if not (d / ".complete").exists():
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["python3", "-m", "pip", "download", "-q", "--only-binary=:all:", "--platform", "manylinux2014_x86_64",
             "--platform", "manylinux_2_17_x86_64", "--platform", "any", "--python-version", "3.12",
             "--implementation", "cp", "-d", str(d), *specs],
            check=True, capture_output=True, text=True, timeout=900,
        )
        (d / ".complete").write_text("ok\n")
    pins = set()
    for w in d.glob("*.whl"):
        m = _re.match(r"^([A-Za-z0-9_.]+?)-(\d[^-]*)-", w.name)
        if m:
            pins.add(f"{m.group(1).replace('_', '-').lower()}=={m.group(2)}")
    return sorted(pins)
