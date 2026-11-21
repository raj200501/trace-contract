"""Export a TraceContract task as a Harbor (pinned 0.25.0) task package.

Layout follows the Harbor 0.25.0 task schema (see docs/research/notes/harbor.md):

* ``task.toml`` - schema 1.4, separate verifier, only ``/app`` transferred as an
  artifact, TraceContract provenance (including the exporter and harness versions)
  under ``[metadata]``;
* ``instruction.md`` - rendered from the reference contract (consolidated final
  requirements; a static task, not a multi-turn benchmark);
* ``environment/`` - offline image: pinned wheelhouse, base snapshot at ``/app``,
  non-root ``agent`` user;
* ``tests/`` - bundled verifier image with the process-separated harness, the
  frozen verifier tests, and a copy of the base snapshot used to discard candidate
  edits to protected test paths; ``test.sh`` runs the grade script as root, which
  writes ``/logs/verifier/reward.json`` only after a complete grade;
* ``solution/`` - the oracle applies one candidate (``CANDIDATE`` env var, default
  ``reference``) from post-image overlays. Only the reference solution is packaged
  unless candidates are named explicitly, so held-out candidates are never exported
  by default; they never enter the agent environment or the verifier.

Since exporter ``tc-harbor-export/0.2.0``, a reward file planted by candidate code
cannot become the trial's reward. Harbor 0.25.0 runs ``chmod 777`` on
``/logs/verifier`` right before the test, and candidate code runs in the verifier
container as an unprivileged sandbox UID, so the grade script makes that directory
root-owned with mode 0700 before any candidate code runs. On every exit path,
including incomplete results, uncaught exceptions and a runner timeout, it kills
what the sandbox UID left behind and removes every ``reward.*`` entry it did not
write itself, so Harbor records a verifier error instead of a planted reward. Since
0.3.0, an entry that cannot be removed makes ``reward.json``, which Harbor reads
before ``reward.txt``, unparseable (0.2.0 renamed the directory away instead, which
fails on the bind mount Harbor uses for it), and the verifier image has no setuid or
setgid file, because Harbor sets neither ``no-new-privileges`` nor a capability drop
for the verifier container.

A task that the acceptance gate refuses (the refusals of
:func:`tracecontract.contract.task_gate`, for example a rejected status or a rejected
source) is not exported; ``allow_rejected_fixture`` exports one only if it is a fixture
(population ``fixture``). The verifier's test files must still match the hashes recorded
when it was frozen.

``network`` = ``intended`` writes ``no-network`` for agent and verifier phases
(an LLM agent run needs an allowlist override for its model endpoint).
``local-validation`` writes ``public`` because Harbor rejected ``no-network`` on the
host used for validation (decision log D20; only the rejection was observed, not its
cause); use it only for oracle/no-op runs of trusted candidates.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from .contract import render_instruction, task_gate
from .patches import DEFAULT_PROTECTED, apply_patch, split_sections
from .sandbox.docker_runner import BASE_IMAGE, HARNESS_SRC, HARNESS_VERSION, ensure_wheelhouse
from .schemas import Candidate, CandidateOrigin, TaskContract, TaskManifest, VerifierSpec
from .store import load
from .verifier import checks_sha256, hash_test_dir

# 0.1.0 was the unversioned exporter validated under harness 0.3.0-0.3.3 (decision log D20, D35, D39, D40,
# D45). 0.2.0: the grade script keeps candidate code from writing /logs/verifier and never leaves a reward it
# did not write; only the reference solution is packaged by default; rejected tasks are refused.
# 0.3.0 (validated with harness 0.3.5): every task that the acceptance gate refuses is refused, a rejected source
# included; a planted reward entry that cannot be removed makes reward.json unparseable, and tc_detail.json is
# still written and /logs/verifier released; the verifier image has no setuid or setgid file.
EXPORTER_VERSION = "tc-harbor-export/0.3.0"
REPO = Path(__file__).resolve().parents[2]  # the repository whose transcripts task_gate reads (as cli.REPO)
NETWORK_VARIANTS = ("intended", "local-validation")
RUNNER_TIMEOUT_MARGIN_SEC = 30  # the grade script's runner timeout is the verifier timeout minus this margin
_CANDIDATE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

GRADE_PY = r'''"""Harbor test entrypoint (runs as root in the separate verifier container).

Exporter __EXPORTER_VERSION__. Candidate code runs only in tc_runner's sandbox children, as an
unprivileged UID drawn per run. Harbor 0.25.0 makes /logs/verifier mode 0777 right before the test,
so this script first makes it root-owned with mode 0700, before any candidate code runs. Whatever
happens afterwards (incomplete results, an uncaught exception, a runner timeout), the finally block
kills what the sandbox UID left behind and removes every reward.* entry this script did not write.
If one cannot be removed, reward.json, which Harbor reads before reward.txt, is overwritten with text
that is not JSON. Harbor then records a typed verifier error, never a planted reward.
"""
import grp, json, os, pwd, secrets, shutil, signal, stat, subprocess, sys, tempfile, time

EXPORTER = "__EXPORTER_VERSION__"
PROTECTED = __PROTECTED__
CAND, TESTS, OUT = "/app", "/tests", "/logs/verifier"
RUNNER_TIMEOUT = __TIMEOUT__
OURS = {}  # name -> (st_dev, st_ino, bytes) of every reward file this script wrote
INVALID_REWARD = b"no reward: a reward entry that the grade script did not write could not be removed\n"


def is_protected(rel):
    import fnmatch, posixpath
    name = posixpath.basename(rel)
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in PROTECTED)


def open_dir(path):
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def lock_out():
    """Make OUT root-owned with mode 0700, and its parent unwritable for group and others.

    Runs before any candidate code. The sandbox UID can then neither create entries in OUT nor
    rename OUT away and put a directory of its own in its place.
    """
    parent = os.path.dirname(OUT)
    os.makedirs(parent, exist_ok=True)
    fd = open_dir(parent)
    try:
        mode = stat.S_IMODE(os.fstat(fd).st_mode)
        if mode & 0o022:
            os.fchmod(fd, mode & ~0o022)
    finally:
        os.close(fd)
    try:
        os.mkdir(OUT, 0o700)
    except FileExistsError:
        pass
    fd = open_dir(OUT)  # refuses a symlink
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def release_out():
    """After grading: let the host side read OUT; it stays root-owned and unwritable for others."""
    fd = open_dir(OUT)
    try:
        os.fchmod(fd, 0o755)
    finally:
        os.close(fd)


def remove_entry(path):
    """Remove a file, link or directory without following links."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(st.st_mode):
        shutil.rmtree(path)
    else:
        os.unlink(path)


def write_out(name, obj, reward=False):
    """Create OUT/name afresh: never through a link or file someone else left there."""
    data = (json.dumps(obj) + "\n").encode("utf-8")
    path = os.path.join(OUT, name)
    remove_entry(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        st = os.fstat(fh.fileno())
    if reward:
        OURS[name] = (st.st_dev, st.st_ino, data)


def is_ours(name):
    """True only for the very file this script wrote under that name, with the bytes it wrote."""
    rec = OURS.get(name)
    path = os.path.join(OUT, name)
    try:
        if rec is None or not stat.S_ISREG(os.lstat(path).st_mode):
            return False
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as fh:
            st = os.fstat(fh.fileno())
            return (st.st_dev, st.st_ino) == rec[:2] and fh.read() == rec[2]
    except OSError:
        return False


def invalidate_reward():
    """Overwrite reward.json with text that is not JSON (Harbor reads it first: VerifierOutputParseError)."""
    path = os.path.join(OUT, "reward.json")
    try:
        remove_entry(path)
    except Exception:
        pass  # a file that cannot be removed is truncated and overwritten below
    OURS.pop("reward.json", None)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644)
    with os.fdopen(fd, "wb") as fh:
        fh.write(INVALID_REWARD)


def remove_foreign_rewards(detail):
    """Remove every reward.* entry in OUT that this script did not write, catching every error per entry.

    Harbor bind-mounts /logs/verifier, so OUT cannot be renamed away (0.2.0 tried, and the error escaped). If an
    entry cannot be removed, reward.json is invalidated instead; a failure to do so is recorded and raised.
    """
    try:
        names = sorted(os.listdir(OUT))
    except FileNotFoundError:
        return
    removed, kept = [], []
    for name in names:
        try:
            if name.startswith("reward.") and not is_ours(name):
                remove_entry(os.path.join(OUT, name))
                removed.append(name)
        except Exception:
            kept.append(name)
    if removed:
        detail["removed_reward_files"] = removed
    if kept:
        detail["unremovable_reward_files"] = kept
        try:
            invalidate_reward()
            detail["reward_invalidated"] = True
        except Exception as exc:
            detail["reward_invalidated"] = False
            detail["reward_invalidation_error"] = f"{type(exc).__name__}: {exc}"
            raise


def pids_of(uid):
    """Live (non-zombie) processes that have uid as real, effective, saved or filesystem UID."""
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/status", encoding="utf-8") as fh:
                fields = dict(line.split(":", 1) for line in fh if ":" in line)
        except OSError:
            continue
        if fields.get("State", "").split()[:1] in (["Z"], ["X"]):
            continue
        if str(uid) in fields.get("Uid", "").split():
            pids.append(int(entry))
    return pids


def reap(uid):
    """SIGKILL what the sandbox UID left behind; a runner timeout kills tc_runner, not its sandbox children."""
    seen = set()
    for _ in range(100):
        pids = pids_of(uid)
        if not pids:
            break
        seen.update(pids)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.05)
    return len(seen)


def draw_uid():
    """A sandbox UID drawn per run (decision log D29), unused in this container.

    Per-user kernel limits are shared by every process of a UID on the host, so concurrent trials must
    not share one. The UID has no account, no process, and owns no directory on the path to OUT.
    """
    taken = {os.lstat(p).st_uid for p in ("/", os.path.dirname(OUT), OUT)}
    while True:
        uid = 20000 + secrets.randbelow(40000)
        if uid in taken or pids_of(uid):
            continue
        try:
            pwd.getpwuid(uid)
            continue
        except KeyError:
            pass
        try:
            grp.getgrgid(uid)
            continue
        except KeyError:
            return uid


def copy_candidate(ws):
    """Copy /app into the workspace; protected paths come from the base snapshot, never from the candidate."""
    removed = []
    for root, dirs, files in os.walk(CAND, followlinks=False):
        rel_root = os.path.relpath(root, CAND)
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__") and not os.path.islink(os.path.join(root, d))]
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.normpath(os.path.join(rel_root, f))
            if os.path.islink(src) or not os.path.isfile(src):
                continue
            if is_protected(rel):
                removed.append(rel)
                continue
            dst = os.path.join(ws, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    base = os.path.join(TESTS, "base")
    for root, dirs, files in os.walk(base):
        for f in files:
            rel = os.path.normpath(os.path.join(os.path.relpath(root, base), f))
            if is_protected(rel):
                dst = os.path.join(ws, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(os.path.join(root, f), dst)
    return removed


def grade(detail, uid):
    """Run the harness; return 0 after writing reward.json, 3 when no reward may be written."""
    ws = tempfile.mkdtemp(prefix="tc_ws_")
    os.chmod(ws, 0o700)
    detail["removed_protected"] = copy_candidate(ws)
    res_dir = tempfile.mkdtemp(prefix="tc_res_")
    os.chmod(res_dir, 0o700)
    nonce = secrets.token_hex(16)
    work = tempfile.mkdtemp(prefix="tc_work_")
    os.chmod(work, 0o755)
    env = dict(os.environ, TC_RUN_NONCE=nonce, TC_SANDBOX_UID=str(uid), TC_SANDBOX_GID=str(uid), TC_WORKDIR=work,
               TC_CANDIDATE_PYTHONPATH=__PYTHONPATH__.replace("{work}", work), PYTHONDONTWRITEBYTECODE="1")
    try:
        proc = subprocess.run([sys.executable, "-I", os.path.join(TESTS, "harness", "tc_runner.py"),
                               "--mode", "process_separated", "--tests-dir", os.path.join(TESTS, "verifier_tests"),
                               "--candidate", ws, "--workdir", work, "--results", res_dir],
                              env=env, capture_output=True, text=True, timeout=RUNNER_TIMEOUT)
    except subprocess.TimeoutExpired:
        detail["error"] = f"grader timed out after {RUNNER_TIMEOUT} s"
        return 3  # no reward file -> Harbor records a typed verifier error, never a reward
    detail["runner_exit_code"] = proc.returncode
    with open(os.path.join(TESTS, "expected_checks.json"), encoding="utf-8") as fh:
        expected = json.load(fh)
    try:
        with open(os.path.join(res_dir, "results.json"), encoding="utf-8") as fh:
            r = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        r = None
    if not isinstance(r, dict) or r.get("nonce") != nonce or r.get("status") != "completed":
        detail["error"] = "grader did not complete" if not isinstance(r, dict) else r.get("error", "nonce/status mismatch")
        return 3
    detail["harness_version"] = r.get("harness_version")
    got = {t["nodeid"]: t["outcome"] for t in r.get("tests", [])}
    checks = {c["check_id"]: got.get(c["check_id"], "missing") for c in expected}
    detail["checks"] = checks
    detail["tamper_events"] = r.get("tamper_events", [])
    problems = sorted({f"{v} checks" for v in checks.values() if v in ("missing", "error", "skipped")})
    if r.get("collect_errors"):
        problems.append("collection errors")
        detail["collect_errors"] = [{"nodeid": e.get("nodeid"), "longrepr": str(e.get("longrepr", ""))[-1500:]}
                                    for e in r["collect_errors"]]
    if set(got) - set(checks):
        problems.append(f"unexpected tests {sorted(set(got) - set(checks))}")
    if problems:
        detail["error"] = "incomplete grade: " + ", ".join(problems)
        return 3
    rewards = {"reward": 1.0 if all(v == "passed" for v in checks.values()) else 0.0}
    for c in expected:
        for rid in c.get("requirement_ids", []):
            ok = checks[c["check_id"]] == "passed"
            rewards[rid] = min(rewards.get(rid, 1.0), 1.0 if ok else 0.0)
    write_out("reward.json", rewards, reward=True)
    return 0


def finish(detail, uid, locked):
    """Every exit path ends here: no sandbox process survives, every reward.* entry this script did not write is
    removed or shadowed by an unparseable reward.json, and tc_detail.json is written and OUT released regardless."""
    try:
        if uid is not None:
            n = reap(uid)
            if n:
                detail["reaped_sandbox_processes"] = n
    finally:
        try:
            remove_foreign_rewards(detail)
        finally:
            if locked:
                try:
                    write_out("tc_detail.json", detail)
                finally:
                    release_out()


def main():
    detail, uid, locked = {"exporter": EXPORTER}, None, False
    try:
        lock_out()  # before any candidate code runs
        locked = True
        for name in os.listdir(OUT):
            if name.startswith("reward."):
                remove_entry(os.path.join(OUT, name))
        uid = draw_uid()
        return grade(detail, uid)
    except Exception as exc:
        detail["error"] = f"grade script failed: {type(exc).__name__}: {exc}"
        raise
    finally:
        finish(detail, uid, locked)


if __name__ == "__main__":
    sys.exit(main())
'''


def render_grade_script(protected: tuple[str, ...], candidate_pythonpath: str, runner_timeout_sec: int) -> str:
    """The grade script with its placeholders filled in."""
    if runner_timeout_sec <= 0:
        raise ValueError("the runner timeout must be positive")
    return (GRADE_PY.replace("__EXPORTER_VERSION__", EXPORTER_VERSION)
            .replace("__PROTECTED__", repr(tuple(protected)))
            .replace("__PYTHONPATH__", repr(candidate_pythonpath.replace("/work", "{work}")))
            .replace("__TIMEOUT__", str(int(runner_timeout_sec))))


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _check_verifier(spec: VerifierSpec, task_dir: Path, verifier_id: str) -> None:
    if spec.isolation.value != "process_separated":
        raise ValueError("only process-separated verifiers can be exported")
    if not spec.frozen:
        raise ValueError(f"verifier {verifier_id} is not frozen")
    # task.toml records the frozen hash, so the exported tests must be the frozen ones.
    if hash_test_dir(task_dir / spec.test_dir) != spec.content_sha256:
        raise ValueError(f"verifier {verifier_id}: test files differ from the frozen hash")
    if spec.checks_sha256 is not None and checks_sha256(spec) != spec.checks_sha256:
        raise ValueError(f"verifier {verifier_id}: scored check list differs from the frozen hash")


def _select_candidates(task_dir: Path, m: TaskManifest, candidates: list[str] | None) -> list[tuple[str, Candidate]]:
    """The reference solution plus the explicitly named candidates, as (solution name, candidate)."""
    cands = [load(task_dir / p, Candidate) for p in m.candidates]
    refs = [c for c in cands if c.origin == CandidateOrigin.reference]
    if len(refs) != 1:
        raise ValueError(f"task {m.task_id} needs exactly one reference candidate, found {len(refs)}")
    wanted = set(candidates or ())
    unknown = sorted(wanted - {c.candidate_id for c in cands})
    if unknown:
        raise ValueError(f"unknown candidates for task {m.task_id}: {unknown}")
    chosen = [("reference", refs[0])]
    for c in cands:
        if c.candidate_id in wanted and c.origin != CandidateOrigin.reference:
            if not _CANDIDATE_NAME.fullmatch(c.candidate_id) or c.candidate_id == "reference":
                raise ValueError(f"candidate id {c.candidate_id!r} cannot name a solution directory")
            chosen.append((c.candidate_id, c))
    return chosen


def export_task(task_dir: Path, verifier_id: str, out: Path, *, snapshot_root: Path, cache_dir: Path,
                candidates: list[str] | None = None, network: str = "intended", timeout_sec: float = 900.0,
                allow_rejected_fixture: bool = False, repo_root: Path | None = None) -> Path:
    """Write the Harbor task package for one verifier of a task to ``out`` (replacing it).

    ``candidates`` names the candidates packaged besides the reference solution; ``None`` packages the
    reference solution only. A task that the acceptance gate refuses (the refusals of :func:`task_gate`,
    which reads the task's records under ``repo_root``, by default this repository; for example a rejected
    status or a rejected source) is refused unless it is a fixture and ``allow_rejected_fixture`` is set.
    The gate's other reasons (pending review, for example) do not keep a task from being exported.
    """
    task_dir = task_dir.resolve()
    m = load(task_dir / "task.json", TaskManifest)
    refusals = task_gate(task_dir, repo_root or REPO).refusals
    if refusals and not (allow_rejected_fixture and m.population.value == "fixture"):
        raise ValueError(f"task {m.task_id} is refused by the acceptance gate and is not exported ({'; '.join(refusals)})"
                         + ("" if m.population.value == "fixture" else "; only a fixture can be exported when rejected"))
    if network not in NETWORK_VARIANTS:
        raise ValueError(f"network must be one of {NETWORK_VARIANTS}, not {network!r}")
    if timeout_sec <= RUNNER_TIMEOUT_MARGIN_SEC:
        raise ValueError(f"timeout_sec must exceed {RUNNER_TIMEOUT_MARGIN_SEC} s")
    spec = load(task_dir / "verifiers" / verifier_id / "spec.json", VerifierSpec)
    _check_verifier(spec, task_dir, verifier_id)
    chosen = _select_candidates(task_dir, m, candidates)
    cpath = task_dir / m.contracts.get("reference", m.contracts.get("full_session", ""))
    contract = load(cpath, TaskContract)
    base = snapshot_root / m.task_id
    if out.exists():
        shutil.rmtree(out)
    (out / "environment").mkdir(parents=True)
    (out / "tests").mkdir()
    (out / "solution" / "candidates").mkdir(parents=True)

    wh = ensure_wheelhouse(sorted(set(m.env_requirements)), cache_dir / "images")
    lock = "\n".join(sorted(set(m.env_requirements))) + "\n"
    install = ("COPY wheelhouse /tmp/wheelhouse\nCOPY requirements.lock /tmp/requirements.lock\n"
               "RUN pip install --no-cache-dir --disable-pip-version-check --no-index --no-deps --find-links /tmp/wheelhouse "
               "-r /tmp/requirements.lock && rm -rf /tmp/wheelhouse\n")
    for d in ("environment", "tests"):
        shutil.copytree(wh, out / d / "wheelhouse", ignore=shutil.ignore_patterns(".complete"))
        (out / d / "requirements.lock").write_text(lock)

    # Agent environment: base snapshot at /app, non-root agent user.
    shutil.copytree(base, out / "environment" / "app")
    (out / "environment" / "Dockerfile").write_text(
        f"FROM {BASE_IMAGE}\n{install}RUN useradd --create-home --uid 1000 agent\nWORKDIR /app\nCOPY app/ /app/\n"
        "RUN chown -R agent:agent /app\n")

    # Verifier image: harness, frozen tests, base copy (protected paths), expected checks.
    shutil.copytree(HARNESS_SRC, out / "tests" / "harness", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(task_dir / spec.test_dir, out / "tests" / "verifier_tests", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(base, out / "tests" / "base")
    (out / "tests" / "expected_checks.json").write_text(json.dumps([c.model_dump(mode="json") for c in spec.checks], indent=1))
    grade = render_grade_script(DEFAULT_PROTECTED, m.candidate_pythonpath, int(timeout_sec - RUNNER_TIMEOUT_MARGIN_SEC))
    (out / "tests" / "tc_harbor_grade.py").write_text(grade)
    (out / "tests" / "test.sh").write_text("#!/bin/sh\nexec python3 -I /tests/tc_harbor_grade.py\n")
    # Harbor sets neither no-new-privileges nor a capability drop for the verifier container, so the last step strips
    # every setuid and setgid bit (the base image has chage, chfn, chsh, expiry, gpasswd, mount, newgrp, passwd, su,
    # umount and unix_chkpwd), so the sandbox UID finds no such program through which to gain privileges.
    (out / "tests" / "Dockerfile").write_text(
        f"FROM {BASE_IMAGE}\n{install}RUN useradd --uid 1001 --user-group --no-create-home --shell /usr/sbin/nologin sandbox\n"
        "COPY . /tests/\nRUN rm -rf /tests/wheelhouse && chmod -R go-rwx /tests && chmod 755 /tests/test.sh\n"
        "RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} +\n")

    # Oracle: candidate post-image overlays selected by $CANDIDATE.
    for name, c in chosen:
        with tempfile.TemporaryDirectory() as tmp:
            ws, _ = apply_patch(base, c.patch, Path(tmp) / "ws")
            odir = out / "solution" / "candidates" / name
            odir.mkdir(parents=True)
            deleted = []
            for sec in split_sections(c.patch):
                if sec.new_path is None and sec.old_path:
                    deleted.append(sec.old_path)
                    continue
                src = ws / sec.path
                if src.is_file():
                    (odir / sec.path).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, odir / sec.path)
            (out / "solution" / "candidates" / f"{name}.deleted").write_text("\n".join(deleted) + ("\n" if deleted else ""))
    (out / "solution" / "solve.sh").write_text(
        "#!/bin/sh\nset -eu\nC=\"${CANDIDATE:-reference}\"\nD=/solution/candidates/$C\n[ -d \"$D\" ] || { echo \"unknown candidate $C\"; exit 2; }\n"
        "cp -R \"$D\"/. /app/\nwhile IFS= read -r f; do [ -n \"$f\" ] && rm -f \"/app/$f\"; done < \"/solution/candidates/$C.deleted\"\n")

    (out / "instruction.md").write_text(
        "You are working in a Python repository checked out at /app.\n\n" + render_instruction(contract)
        + "\nKeep all changes inside /app. Do not modify the repository's existing tests to make them pass.\n")
    net = "no-network" if network == "intended" else "public"
    reqs = ",\n".join(
        "  { id = %s, kind = %s, introduced_at = %s, scored = %s }" % (_toml_str(r.req_id), _toml_str(r.kind.value),
                                                                       _toml_str(r.introduced_at), str(r.scored).lower())
        for r in contract.active())
    (out / "task.toml").write_text(f"""schema_version = "1.4"
source = "tracecontract"
artifacts = [{{ source = "/app", destination = "candidate", exclude = [".git", "__pycache__"] }}]

[task]
name = {_toml_str('tracecontract/' + m.task_id.lower())}
version = {_toml_str(EXPORTER_VERSION.split('/', 1)[1])}
description = {_toml_str(f'TraceContract task {m.task_id} ({m.population.value} population), verifier {verifier_id}')}

[metadata]
tracecontract_task_id = {_toml_str(m.task_id)}
tracecontract_family_id = {_toml_str(m.family_id)}
tracecontract_population = {_toml_str(m.population.value)}
tracecontract_status = {_toml_str(m.status)}
tracecontract_repo_url = {_toml_str(m.snapshot_source.repo_url)}
tracecontract_base_commit = {_toml_str(m.snapshot_source.commit)}
tracecontract_verifier_id = {_toml_str(verifier_id)}
tracecontract_verifier_condition = {_toml_str(spec.condition.value)}
tracecontract_verifier_sha256 = {_toml_str(spec.content_sha256)}
tracecontract_contract_id = {_toml_str(contract.contract_id)}
tracecontract_network_variant = {_toml_str(network)}
tracecontract_exporter_version = {_toml_str(EXPORTER_VERSION)}
tracecontract_harness_version = {_toml_str(HARNESS_VERSION)}
tracecontract_requirements = [
{reqs}
]

[verifier]
timeout_sec = {timeout_sec}
environment_mode = "separate"

[verifier.environment]
network_mode = "{net}"
cpus = 2
memory_mb = 4096

[agent]
timeout_sec = 3600.0
user = "agent"

[environment]
network_mode = "{net}"
cpus = 2
memory_mb = 4096
build_timeout_sec = 900.0
""")
    return out
