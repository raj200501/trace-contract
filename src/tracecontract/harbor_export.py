"""Export a TraceContract task as a Harbor (pinned 0.25.0) task package.

Layout follows the Harbor 0.25.0 task schema (see docs/research/notes/harbor.md):

* ``task.toml`` - schema 1.4, separate verifier, only ``/app`` transferred as an
  artifact, TraceContract provenance under ``[metadata]``;
* ``instruction.md`` - rendered from the reference contract (consolidated final
  requirements; a static task, not a multi-turn benchmark);
* ``environment/`` - offline image: pinned wheelhouse, base snapshot at ``/app``,
  non-root ``agent`` user;
* ``tests/`` - bundled verifier image with the process-separated harness, the
  frozen verifier tests, and a copy of the base snapshot used to discard candidate
  edits to protected test paths; ``test.sh`` writes ``/logs/verifier/reward.json``
  as root after grading;
* ``solution/`` - the oracle applies one candidate (``CANDIDATE`` env var, default
  ``reference``) from post-image overlays, so held-out candidates never enter the
  agent environment or the verifier.

``network`` = ``intended`` writes ``no-network`` for agent and verifier phases
(an LLM agent run needs an allowlist override for its model endpoint).
``local-validation`` writes ``public`` because Harbor rejects ``no-network`` on hosts
without nftables egress control (observed here); use it only for oracle/no-op runs
of trusted candidates.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .contract import render_instruction
from .patches import apply_patch, split_sections
from .sandbox.docker_runner import BASE_IMAGE, HARNESS_SRC, ensure_wheelhouse
from .schemas import Candidate, TaskContract, TaskManifest, VerifierSpec
from .store import load

GRADE_PY = r'''"""Harbor test entrypoint (runs as root in the separate verifier container)."""
import json, os, secrets, shutil, subprocess, sys, tempfile

PROTECTED = __PROTECTED__
CAND, BASE, OUT = "/app", "/tests/base", "/logs/verifier"

def is_protected(rel):
    import fnmatch, posixpath
    name = posixpath.basename(rel)
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in PROTECTED)

def main():
    os.makedirs(OUT, exist_ok=True)
    for f in ("reward.txt", "reward.json"):
        try:
            os.unlink(os.path.join(OUT, f))
        except FileNotFoundError:
            pass
    ws = tempfile.mkdtemp(prefix="tc_ws_")
    os.chmod(ws, 0o700)
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
    # Protected paths come from the base snapshot, never from the candidate.
    for root, dirs, files in os.walk(BASE):
        for f in files:
            rel = os.path.normpath(os.path.join(os.path.relpath(root, BASE), f))
            if is_protected(rel):
                dst = os.path.join(ws, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(os.path.join(root, f), dst)
    res_dir = tempfile.mkdtemp(prefix="tc_res_")
    os.chmod(res_dir, 0o700)
    nonce = secrets.token_hex(16)
    work = tempfile.mkdtemp(prefix="tc_work_")
    os.chmod(work, 0o755)
    env = dict(os.environ, TC_RUN_NONCE=nonce, TC_SANDBOX_UID="1001", TC_SANDBOX_GID="1001", TC_WORKDIR=work,
               TC_CANDIDATE_PYTHONPATH=__PYTHONPATH__.replace("{work}", work), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-I", "/tests/harness/tc_runner.py", "--mode", "process_separated",
                           "--tests-dir", "/tests/verifier_tests", "--candidate", ws, "--workdir", work, "--results", res_dir],
                          env=env, capture_output=True, text=True, timeout=__TIMEOUT__)
    expected = json.load(open("/tests/expected_checks.json"))
    reward, detail = 0.0, {"removed_protected": removed}
    try:
        r = json.load(open(os.path.join(res_dir, "results.json")))
    except (FileNotFoundError, json.JSONDecodeError):
        r = None
    if r is None or r.get("nonce") != nonce or r.get("status") != "completed":
        detail["error"] = "grader did not complete" if r is None else r.get("error", "nonce/status mismatch")
        json.dump(detail, open(os.path.join(OUT, "tc_detail.json"), "w"))
        sys.exit(3)  # no reward file -> Harbor records a typed verifier error, never a reward
    got = {t["nodeid"]: t["outcome"] for t in r.get("tests", [])}
    checks = {c["check_id"]: got.get(c["check_id"], "missing") for c in expected}
    detail["checks"] = checks
    detail["tamper_events"] = r.get("tamper_events", [])
    if any(v in ("missing", "error", "skipped") for v in checks.values()) or r.get("collect_errors") or set(got) - set(checks):
        json.dump(detail, open(os.path.join(OUT, "tc_detail.json"), "w"))
        sys.exit(3)
    reward = 1.0 if all(v == "passed" for v in checks.values()) else 0.0
    rewards = {"reward": reward}
    for c in expected:
        for rid in c.get("requirement_ids", []):
            ok = checks[c["check_id"]] == "passed"
            rewards[rid] = min(rewards.get(rid, 1.0), 1.0 if ok else 0.0)
    json.dump(detail, open(os.path.join(OUT, "tc_detail.json"), "w"))
    json.dump(rewards, open(os.path.join(OUT, "reward.json"), "w"))

if __name__ == "__main__":
    main()
'''


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def export_task(task_dir: Path, verifier_id: str, out: Path, *, snapshot_root: Path, cache_dir: Path,
                candidates: list[str] | None = None, network: str = "intended", timeout_sec: float = 900.0) -> Path:
    task_dir = task_dir.resolve()
    m = load(task_dir / "task.json", TaskManifest)
    spec = load(task_dir / "verifiers" / verifier_id / "spec.json", VerifierSpec)
    if spec.isolation.value != "process_separated":
        raise ValueError("only process-separated verifiers can be exported")
    if not spec.frozen:
        raise ValueError(f"verifier {verifier_id} is not frozen")
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
    from .patches import DEFAULT_PROTECTED

    grade = (GRADE_PY.replace("__PROTECTED__", repr(tuple(DEFAULT_PROTECTED)))
             .replace("__PYTHONPATH__", repr(m.candidate_pythonpath.replace("/work", "{work}")))
             .replace("__TIMEOUT__", str(int(timeout_sec - 30))))
    (out / "tests" / "tc_harbor_grade.py").write_text(grade)
    (out / "tests" / "test.sh").write_text("#!/bin/sh\nexec python3 -I /tests/tc_harbor_grade.py\n")
    (out / "tests" / "Dockerfile").write_text(
        f"FROM {BASE_IMAGE}\n{install}RUN useradd --uid 1001 --user-group --no-create-home --shell /usr/sbin/nologin sandbox\n"
        "COPY . /tests/\nRUN rm -rf /tests/wheelhouse && chmod -R go-rwx /tests && chmod 755 /tests/test.sh\n")

    # Oracle: candidate post-image overlays selected by $CANDIDATE.
    cands = [load(task_dir / p, Candidate) for p in m.candidates]
    chosen = [c for c in cands if candidates is None or c.candidate_id in candidates or c.origin.value == "reference"]
    for c in chosen:
        name = "reference" if c.origin.value == "reference" else c.candidate_id
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
version = "0.1.0"
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
