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

_SEGMENT = re.compile(r"&&|\|\||;|\||\n")
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
# Shell commands whose arguments are paths (read, list, search, copy or apply).
_PATH_CMDS = {"cat", "head", "tail", "less", "more", "sed", "awk", "grep", "egrep", "fgrep", "rg", "find", "ls", "tree", "du",
              "cp", "mv", "diff", "wc", "file", "stat", "python", "python3", "bash", "sh", "source", "git", "patch", "tar",
              "zcat", "xxd", "od", "strings", "nl", "sort", "uniq", "cut", "jq", "realpath", "readlink"}
_SEARCHERS = {"grep", "egrep", "fgrep", "rg"}


def _shell_segments(cmd: str) -> list[str]:
    """Command segments of a shell command line, without the bodies of heredocs."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        m = _HEREDOC.search(line)
        out += [x.strip() for x in _SEGMENT.split(line) if x.strip()]
        if m:  # skip the heredoc body up to its delimiter
            i += 1
            while i < len(lines) and lines[i].strip() != m.group(1):
                i += 1
        i += 1
    return out


_ASSIGN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _scan_command(cmd: str, start: str, norm) -> tuple[list, list, str]:
    """Paths that one shell command reads, lists or searches, for the strict audit.

    Returns ``(checks, unresolved, end_cwd)``: ``checks`` holds ``(path, recursive, text,
    pruned)`` tuples, ``unresolved`` the ``(token, text)`` roots of recursive searches that
    still hold a variable after the command's own assignments are substituted, and
    ``end_cwd`` the directory the command ends in.
    """
    import os
    import shlex

    cwd, env, checks, unresolved = start, {}, [], []

    def expand(t: str) -> str:
        return _VAR.sub(lambda m: env.get(m.group(1) or m.group(2), m.group(0)), t)

    for seg in _shell_segments(cmd):
        if "tracecontract add-candidate" in seg:
            continue
        m = _ASSIGN.match(seg)
        if m:
            try:
                val = shlex.split(m.group(2), posix=True)
            except ValueError:
                val = m.group(2).split()
            env[m.group(1)] = expand(val[0]) if len(val) == 1 else m.group(2)
            continue
        try:
            toks = shlex.split(seg, comments=False, posix=True)
        except ValueError:
            toks = seg.split()
        toks = [expand(t) for t in toks]
        if not toks:
            continue
        name = os.path.basename(toks[0])
        if name == "cd":
            if len(toks) > 1 and "$" not in toks[1]:
                cwd = norm(toks[1], cwd)
                checks.append((cwd, False, seg[:300], ()))
            continue
        if name not in _PATH_CMDS:
            continue
        args = [t for t in toks[1:] if not t.startswith("-")]
        recursive = name in ("find", "tree", "du", "rg") or (name in _SEARCHERS and any(
            t.startswith("-") and not t.startswith("--") and ("r" in t or "R" in t) for t in toks[1:])) or (
            name == "ls" and any(t.startswith("-") and "R" in t for t in toks[1:]))
        if name == "find":
            roots = [args[0]] if args and not args[0].startswith(("(", "!")) else ["."]
            pruned = tuple(norm(toks[i + 1], cwd) for i, t in enumerate(toks[:-1]) if t == "-path" and i + 2 < len(toks)
                           and "-prune" in toks[i + 2:i + 4])
            for r in roots:
                if "$" in r:
                    unresolved.append((r, seg[:300]))
                else:
                    checks.append((norm(r, cwd), True, seg[:300], pruned))
            continue
        if name in _SEARCHERS:
            paths = args[1:]  # the first non-option argument is the pattern
            if recursive and not paths:
                paths = ["."]
        else:
            paths = args
        for t in paths:
            if "$" in t:
                if recursive:
                    unresolved.append((t, seg[:300]))
                continue
            if name in ("python", "python3", "bash", "sh", "git") and "/" not in t:
                continue  # module names, subcommands and the like
            checks.append((norm(t, cwd), recursive, seg[:300], ()))
    return checks, unresolved, cwd


def audit_generator_transcript_strict(path: Path, *, task: str, own: str, extra_allowed: tuple[str, ...] = (),
                                      extra_forbidden: tuple[str, ...] = (), repo_root: str = "/home/user/trace-contract",
                                      home: str = "/home/user") -> list[dict]:
    """A stricter re-audit of a generator transcript's tool inputs (decision log D44).

    Unlike :func:`audit_generator_transcript`, which matches substrings, it resolves paths.
    Shell commands are split at ``&&``, ``||``, ``;``, ``|`` and newlines (heredoc bodies are
    data and skipped); variables assigned earlier in the same command are substituted;
    ``cd`` is followed within a command; and relative paths are resolved against the
    repository root, where every Bash call of a subagent starts, and also against the
    directory the previous call ended in (a conservative extra). A hit is a path inside
    forbidden material (the task's verifiers or candidates, ``results/``, ``data/``,
    ``docs/``, the task's other workspaces, sealed material, ``/root`` except tool
    binaries), a recursive search or listing (``grep -r``, ``rg``, ``find``, ``ls -R``,
    ``tree``, ``du``, the Grep and Glob tools) whose root contains forbidden material that
    it does not prune, or a recursive search whose root still holds a variable. Only the
    ``add-candidate`` segment of a command is exempt. ``extra_allowed`` names directories a
    role was asked to write (the reference-check directory for its writer);
    ``extra_forbidden`` adds session-local directories, such as the builder's scratch
    directory, whose path must not be written into the repository. Tool outputs are not
    inspected, and a hit is a lead for a manual reading, not a finding.
    """
    import os

    from .ingest.claude_code import parse_claude_code_jsonl
    from .schemas import Population

    forbidden = [f"{repo_root}/tasks/{task}/verifiers", f"{repo_root}/tasks/{task}/candidates", f"{repo_root}/results",
                 f"{repo_root}/data", f"{repo_root}/docs", f"{home}/cs_workspaces", f"{home}/gen_workspaces/{task}",
                 f"{home}/.tc_sealed", "/root", *[os.path.normpath(x) for x in extra_forbidden]]
    allowed = [os.path.normpath(own), "/root/.local/bin", *[os.path.normpath(x) for x in extra_allowed]]
    sealed_markers = ("scratchpad/sealed", "scratchpad/scenarios", "scratchpad/reference")

    def norm(p: str, cwd: str) -> str:
        if p.startswith("~"):
            p = home + p[1:]
        return os.path.normpath(p if p.startswith("/") else os.path.join(cwd, p))

    def inside(p: str, root: str) -> bool:
        return p == root or p.startswith(root.rstrip("/") + "/")

    def classify(p: str, recursive: bool, pruned: tuple[str, ...] = ()) -> str | None:
        if any(m in p for m in sealed_markers):
            return "sealed material"
        if any(inside(p, a) for a in allowed):
            return None
        for root in forbidden:
            if inside(p, root):
                return "inside forbidden material"
            if recursive and inside(root, p) and not any(inside(root, x) for x in pruned) \
                    and not any(inside(a, p) and inside(root, a) for a in allowed):
                return "recursive search over forbidden material"
        return None

    s = parse_claude_code_jsonl(path, population=Population.controlled, source="audit", include_sidechains=True)
    hits = []
    carried = repo_root
    for ev in s.events:
        if ev.kind != EventKind.tool_call:
            continue
        ti = ev.tool_input or {}
        checks: list[tuple[str, bool, str, tuple[str, ...]]] = []
        for k in ("file_path", "notebook_path"):
            if ti.get(k):
                checks.append((norm(str(ti[k]), repo_root), False, str(ti[k]), ()))
        if ev.tool_name in ("Grep", "Glob"):
            checks.append((norm(str(ti.get("path") or "."), repo_root), True, json.dumps(ti)[:300], ()))
        cmd = ti.get("command") if isinstance(ti.get("command"), str) else ""
        if cmd:
            # Every Bash call of a subagent starts in the repository root. As a conservative
            # extra, relative paths are also resolved from the directory an earlier call ended
            # in, in case a working directory carried over between calls.
            c1, u1, end = _scan_command(cmd, repo_root, norm)
            c2, u2, carried = _scan_command(cmd, carried, norm) if carried != repo_root else ([], [], end)
            checks += c1 + c2
            for tok, text in dict.fromkeys(u1 + u2):
                hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": tok, "why": "search rooted at an unresolved variable", "text": text})
        seen = set()
        for p, rec, text, pruned in checks:
            why = classify(p, rec, pruned)
            if why and (p, why) not in seen:
                seen.add((p, why))
                hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": p, "why": why, "text": text})
    return hits
