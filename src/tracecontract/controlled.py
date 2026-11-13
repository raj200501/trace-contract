"""Controlled-session utilities (protocol CS-v1, see docs/decision_log.md D5).

Controlled sessions are real agent runs on pinned public repositories with user
turns written by the study before the run. These helpers:

* capture workspace states between turns (``capture_state``);
* turn captured states into candidate patches (``candidate_from_state``);
* audit a transcript for access outside the agent's workspace, which would make the
  session contaminated (e.g. reading study files that contain the scripted
  correction or intended requirements) - ``audit_access``.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .patches import diff_dirs
from .schemas import Candidate, CandidateOrigin, EventKind, Label, Session, Split, sha256_text
from .snapshot import manifest, manifest_sha256

# Locations that hold study material; touching them contaminates a session.
STUDY_LOCATIONS = ("/home/user/trace-contract", "/tmp/claude-0", "scratchpad", "/root/.claude", "/home/user/ext",
                   "/home/user/harbor-framework", "/home/user/SWE-bench", "/home/user/R2E-Gym", "/home/user/ScalingIntelligence")
_PATH_RE = re.compile(r"(?<![\w.-])(/(?:[\w.@+-]+/)*[\w.@+-]+)")
_SYSTEM_PREFIXES = ("/usr", "/bin", "/sbin", "/lib", "/etc", "/dev", "/proc", "/sys", "/opt/node22", "/tmp", "/repo",
                    "/var/run/docker.sock")


def capture_state(workspace: Path, dest: Path, *, exclude: tuple[str, ...] = (".git",)) -> str:
    """Copy the workspace (without VCS metadata) and return its manifest hash."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(workspace, dest, symlinks=True, ignore=shutil.ignore_patterns(*exclude, "__pycache__", ".pytest_cache"))
    return manifest_sha256(manifest(dest))


def candidate_from_state(*, task_id: str, candidate_id: str, base: Path, state: Path, origin: CandidateOrigin,
                         split: Split, produced_by: str, description: str = "", labels: list[Label] | None = None) -> Candidate:
    patch = diff_dirs(base, state)
    return Candidate(candidate_id=candidate_id, task_id=task_id, origin=origin, split=split, patch=patch,
                     patch_sha256=sha256_text(patch), produced_by=produced_by, description=description, labels=labels or [])


@dataclass
class AccessFinding:
    event_id: str
    tool: str
    path: str
    reason: str


def _paths_in(ev) -> list[str]:
    paths: list[str] = []
    ti = ev.tool_input or {}
    for key in ("file_path", "path", "notebook_path"):
        v = ti.get(key)
        if isinstance(v, str):
            paths.append(v)
    if ev.tool_name in ("Bash", "BashOutput") and isinstance(ti.get("command"), str):
        paths += _PATH_RE.findall(ti["command"])
    if ev.tool_name in ("Glob", "Grep") and isinstance(ti.get("pattern"), str) and ti["pattern"].startswith("/"):
        paths.append(ti["pattern"])
    return paths


def audit_access(session: Session, allowed_roots: tuple[str, ...]) -> list[AccessFinding]:
    """Flag tool calls that reference locations outside ``allowed_roots``.

    * ``contamination``: the full tool input mentions a known study location (any
      field, any position) - the session must be rejected;
    * ``outside_workspace``: an absolute path under a real top-level directory that
      is neither in the workspace nor a standard system location - needs a human look.

    This is a conservative textual audit, not a sandbox.
    """
    import os

    top_level = set(os.listdir("/"))
    out: list[AccessFinding] = []
    for ev in session.events:
        if ev.kind != EventKind.tool_call:
            continue
        blob = json.dumps(ev.tool_input or {}, ensure_ascii=False)
        for loc in STUDY_LOCATIONS:
            if loc in blob:
                out.append(AccessFinding(ev.event_id, ev.tool_name or "?", loc, "contamination"))
        for p in _paths_in(ev):
            if any(p == r or p.startswith(r.rstrip("/") + "/") for r in allowed_roots):
                continue
            first = p.lstrip("/").split("/", 1)[0]
            if first not in top_level or p.startswith(_SYSTEM_PREFIXES) or any(loc in p for loc in STUDY_LOCATIONS):
                continue
            out.append(AccessFinding(ev.event_id, ev.tool_name or "?", p, "outside_workspace"))
    return out


def load_scenario(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


RUN_TESTS_SH = """#!/bin/sh
# Run the repository's tests (any pytest arguments) in an isolated, offline Docker
# container. The working copy is mounted read-only; nothing is installed.
# Usage: {root}/run_tests.sh [pytest args...]
exec docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges \\
  --memory 2g --pids-limit 256 --read-only --tmpfs /tmp:rw,size=256m \\
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH={pythonpath} \\
  -v {repo}:/repo:ro -w /repo \\
  {image} python -m pytest -p no:cacheprovider {extra} "$@"
"""

RUN_PYTHON_SH = """#!/bin/sh
# Run Python (e.g. -c '...') against the working copy in the same isolated container.
# Usage: {root}/run_python.sh -c 'import ...'
exec docker run --rm -i --network none --cap-drop ALL --security-opt no-new-privileges \\
  --memory 2g --pids-limit 256 --read-only --tmpfs /tmp:rw,size=256m \\
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH={pythonpath} \\
  -v {repo}:/repo:ro -w /repo \\
  {image} python "$@"
"""


def prepare_workspace(scenario: dict, *, env_specs: list[str], cache_dir: Path, pythonpath: str = "/repo",
                      extra_pytest_args: str = "", overlays: dict[str, str] | None = None,
                      baseline_args: list[str] | None = None) -> dict:
    """Build a controlled-session workspace for ``scenario`` (protocol CS-v1).

    Returns a record with the snapshot, pinned environment, image, and the baseline
    test result (run inside the sandbox). ``overlays`` are generated build artefacts
    added to the snapshot; they are recorded as approximations.
    """
    import subprocess

    from .sandbox.docker_runner import build_env_image, resolve_pins
    from .schemas import Fidelity, SnapshotSource
    from .snapshot import build_snapshot

    ws_repo = Path(scenario["workspace"])
    root = ws_repo.parent
    root.mkdir(parents=True, exist_ok=True)
    src = SnapshotSource(repo_url=scenario["repo_url"], commit=scenario["commit"])
    snap = build_snapshot(scenario["scenario_id"], src, ws_repo, cache_dir / "git")
    approximations = list(snap.approximations)
    for rel, content in (overlays or {}).items():
        p = ws_repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        approximations.append(f"generated build artefact added: {rel}")
    if approximations:
        snap = snap.model_copy(update={"approximations": approximations, "fidelity": Fidelity.approximate})
    git = lambda *a: subprocess.run(["git", *a], cwd=ws_repo, check=True, capture_output=True, text=True)  # noqa: E731
    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=dev", "-c", "user.email=dev@localhost", "commit", "-q", "-m", f"base: {scenario['commit'][:12]}")
    pins = resolve_pins(env_specs, cache_dir / "resolve")
    tag, image_id = build_env_image(pins, cache_dir / "images")
    fmt = dict(root=str(root), repo=str(ws_repo), image=tag, pythonpath=pythonpath, extra=extra_pytest_args)
    (root / "run_tests.sh").write_text(RUN_TESTS_SH.format(**fmt))
    (root / "run_python.sh").write_text(RUN_PYTHON_SH.format(**fmt))
    for s in ("run_tests.sh", "run_python.sh"):
        (root / s).chmod(0o755)
    (root / ".image").write_text(tag + "\n")
    base = subprocess.run([str(root / "run_tests.sh"), "-q", *(baseline_args or [])], capture_output=True, text=True, timeout=1800)
    record = {
        "scenario_id": scenario["scenario_id"],
        "snapshot": snap.model_dump(mode="json"),
        "env_specs": env_specs,
        "env_pins": pins,
        "image": tag,
        "image_id": image_id,
        "pythonpath": pythonpath,
        "extra_pytest_args": extra_pytest_args,
        "baseline_args": baseline_args or [],
        "baseline_exit_code": base.returncode,
        "baseline_tail": base.stdout.strip().splitlines()[-3:],
    }
    (root / "workspace_record.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def audit_generator_transcript(path: Path, *, forbidden: tuple[str, ...], allowed: tuple[str, ...] = ()) -> list[dict]:
    """Scan a generation agent's transcript for reads of forbidden locations.

    ``forbidden`` / ``allowed`` are substrings matched against file paths, search
    patterns and shell commands in tool calls. A hit inside an ``allowed`` substring
    is ignored (e.g. the reference-check writer may touch its own verifier dir).
    Writes performed through the CLI (``add-candidate``) are not reads and are
    ignored when the command starts with the CLI.
    """
    from .ingest.claude_code import parse_claude_code_jsonl
    from .schemas import Population

    s = parse_claude_code_jsonl(path, population=Population.controlled, source="audit", include_sidechains=True)
    hits = []
    for ev in s.events:
        if ev.kind != EventKind.tool_call:
            continue
        ti = ev.tool_input or {}
        fields = [str(ti.get(k)) for k in ("file_path", "path", "pattern", "notebook_path") if ti.get(k)]
        cmd = ti.get("command") if isinstance(ti.get("command"), str) else ""
        if cmd:
            fields.append(cmd)
        for f in fields:
            g = f
            for a in allowed:
                g = g.replace(a, "")
            for bad in forbidden:
                if bad in g:
                    if f is cmd and cmd.strip().startswith((".venv/bin/tracecontract add-candidate", "/home/user/trace-contract/.venv/bin/tracecontract add-candidate")):
                        continue
                    hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "match": bad, "text": f[:300]})
    return hits
