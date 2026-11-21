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
from typing import Literal, overload

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

_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
# Shell commands whose arguments are paths (read, list, search, copy, archive or apply).
_PATH_CMDS = {"cat", "head", "tail", "less", "more", "sed", "awk", "grep", "egrep", "fgrep", "rg", "find", "ls", "tree", "du",
              "cp", "mv", "diff", "wc", "file", "stat", "python", "python3", "bash", "sh", "source", ".", "git", "patch", "tar",
              "zcat", "xxd", "od", "strings", "nl", "sort", "uniq", "cut", "jq", "realpath", "readlink", "rsync", "base64",
              "zip", "unzip", "gzip", "gunzip", "md5sum", "sha256sum", "sha1sum", "cmp", "comm", "paste", "tac", "hexdump",
              "iconv", "perl", "node", "ruby", "tr", "column", "fold", "rev", "split", "shuf", "look"}
_SEARCHERS = {"grep", "egrep", "fgrep", "rg"}
_KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "{", "(", "time", "done", "fi"}
_WRAPPERS = {"env", "timeout", "sudo", "nice", "nohup", "stdbuf", "command", "exec", "xargs", "builtin", "ionice"}
_GIT_LISTING = {"status", "ls-files", "ls-tree", "grep", "diff", "show", "blame", "archive", "stash", "log", "whatchanged"}
_EXCLUSION_ARG = re.compile(r"(?:-i?path|-wholename|--exclude(?:-dir)?|--ignore(?:-dir)?)(?:=|\s+)\S+")
_LITERAL_PATH = re.compile(r"(?<![\w$}{])(?:~|\.\.?)?/?(?:[\w.@%+=,-]+/)+[\w.@%+=,*?-]*")
_ANY_VAR = re.compile(r"\$\{\w+\}|\$[A-Za-z_]\w*|\$[0-9]")  # a shell variable or positional parameter
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}  # their output confirms the write of their input path


def _strip_heredocs(cmd: str) -> str:
    """The command text with heredoc bodies removed (they are data, or code fed to an interpreter)."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        out.append(lines[i])
        m = _HEREDOC.search(lines[i])
        if m:
            i += 1
            while i < len(lines) and lines[i].strip() != m.group(1):
                i += 1
        i += 1
    return "\n".join(out)


def _split_unquoted(text: str) -> list[str]:
    """Split at unquoted ``&&``, ``||``, ``;``, ``|``, ``&``, newlines, ``$(`` and backticks."""
    segs, cur, i, q = [], [], 0, None
    while i < len(text):
        c = text[i]
        if q:
            cur.append(c)
            if c == "\\" and q == '"' and i + 1 < len(text):
                cur.append(text[i + 1])
                i += 2
                continue
            if c == q:
                q = None
            i += 1
            continue
        if c == "\\" and i + 1 < len(text):
            cur += [c, text[i + 1]]
            i += 2
            continue
        if c in "'\"":
            q = c
            cur.append(c)
            i += 1
            continue
        if text[i:i + 2] in ("&&", "||", "$("):
            segs.append("".join(cur))
            cur = []
            i += 2
            continue
        if c in ";|&\n`":
            segs.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    segs.append("".join(cur))
    return [x.strip() for x in segs if x.strip()]


def _shell_segments(cmd: str) -> list[str]:
    """Command segments of a shell command line, without the bodies of heredocs."""
    return _split_unquoted(_strip_heredocs(cmd))


_ASSIGN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _command_words(seg: str, env: dict) -> list[str]:
    """The words of one segment, without leading keywords, assignments (recorded in ``env``) and wrappers."""
    import os
    import shlex

    seg = seg.strip().lstrip("({").rstrip(")}").strip()
    try:
        toks = shlex.split(seg, comments=False, posix=True)
    except ValueError:
        toks = seg.split()
    while toks and toks[0] in _KEYWORDS:
        toks = toks[1:]
    if toks and toks[0] in ("export", "declare", "local", "readonly", "typeset"):
        toks = [t for t in toks[1:] if not t.startswith("-")]
    while toks and _ASSIGN.match(toks[0]):
        m = _ASSIGN.match(toks[0])
        env[m.group(1)] = _VAR.sub(lambda v: env.get(v.group(1) or v.group(2), v.group(0)), m.group(2))
        toks = toks[1:]
    while toks and os.path.basename(toks[0]) in _WRAPPERS:
        w, toks = os.path.basename(toks[0]), toks[1:]
        while toks and (toks[0].startswith("-") or (w == "env" and "=" in toks[0])):
            toks = toks[1:]
        if w == "timeout" and toks:
            toks = toks[1:]  # the duration
    return [_VAR.sub(lambda v: env.get(v.group(1) or v.group(2), v.group(0)), t) for t in toks]


def _scan_command(cmd: str, start: str, norm) -> tuple[list, list, str]:
    """Paths that one shell command reads, lists or searches, for the strict audit.

    Returns ``(checks, unresolved, end_cwd)``: ``checks`` holds ``(path, recursive, text,
    pruned)`` tuples, ``unresolved`` the ``(token, text, directory)`` roots of recursive
    searches that still hold a variable after the command's own assignments are
    substituted (with the directory of the literal part before the variable), and
    ``end_cwd`` the directory the command ends in. A ``cd`` inside ``( ... )`` lasts until
    the closing parenthesis.
    """
    import os

    state = {"cwd": start}
    env: dict = {}
    checks: list = []
    unresolved: list = []
    stack: list = []

    def add(tok: str, recursive: bool, seg: str, pruned=()) -> None:
        if "$" in tok:
            if recursive:  # with the directory of the literal part before the variable
                head = tok.split("$", 1)[0]
                unresolved.append((tok, seg[:300], norm(os.path.dirname(head) or ".", state["cwd"])))
            return
        checks.append((norm(tok, state["cwd"]), recursive, seg[:300], pruned))

    def process(seg: str) -> None:
        cwd = state["cwd"]
        toks = _command_words(seg, env)
        if not toks:
            return
        name = os.path.basename(toks[0])
        if name == "tracecontract" and len(toks) > 1 and toks[1] == "add-candidate":
            return  # the registration command writes the agent's own candidate
        if name == "cd":
            if len(toks) > 1 and "$" not in toks[1]:
                state["cwd"] = norm(toks[1], cwd)
                checks.append((state["cwd"], False, seg[:300], ()))
            return
        if name == "for":
            for t in toks[3:] if len(toks) > 3 and toks[2] == "in" else []:
                add(t, False, seg)
            return
        if name not in _PATH_CMDS:
            return
        opts = [t for t in toks[1:] if t.startswith("-")]
        args = [t for t in toks[1:] if not t.startswith("-")]
        short = "".join(t[1:] for t in opts if not t.startswith("--"))
        recursive = (name in ("find", "tree", "du", "rg", "rsync", "tar", "zip")
                     or (name in _SEARCHERS and ("r" in short or "R" in short or "--recursive" in opts
                                                 or "--dereference-recursive" in opts))
                     or (name == "ls" and ("R" in short or "--recursive" in opts))
                     or (name == "cp" and ("r" in short or "R" in short or "a" in short or "--recursive" in opts
                                           or "--archive" in opts))
                     or (name == "diff" and ("r" in short or "--recursive" in opts)))
        if name == "find":
            roots = []
            for t in toks[1:]:
                if t.startswith(("-", "(", "!", ")", ",")):
                    break
                roots.append(t)
            pruned = tuple(norm(toks[i + 1], cwd) for i, t in enumerate(toks[:-1]) if t == "-path" and i + 2 < len(toks)
                           and "-prune" in toks[i + 2:i + 4])
            for r in roots or ["."]:
                add(r, True, seg, pruned)
            return
        if name == "git":
            rest, gcwd = toks[1:], cwd
            while rest and rest[0].startswith("-"):
                if rest[0] == "-C" and len(rest) > 1:
                    gcwd = norm(rest[1], cwd)
                    rest = rest[2:]
                else:
                    rest = rest[1:]
            if not rest or rest[0] not in _GIT_LISTING:
                return
            sub, rest = rest[0], rest[1:]
            if "--" in rest:
                specs = list(rest[rest.index("--") + 1:])
            else:
                specs = [t for t in rest if not t.startswith("-") and ("/" in t or "." in t)]
            specs = [t.split(":", 1)[1] if ":" in t and sub == "show" else t for t in specs]
            if sub == "log" and not any(o in rest for o in ("-p", "--patch", "--stat", "--name-only", "--name-status")):
                return  # commit subjects only
            for t in specs or ["."]:
                checks.append((norm(t or ".", gcwd), True, seg[:300], ()))
            return
        if name in _SEARCHERS:
            paths = args[1:]  # the first non-option argument is the pattern
            if recursive and not paths:
                paths = ["."]
        else:
            paths = args
        for t in paths:
            if name in ("python", "python3", "bash", "sh", "perl", "node", "ruby") and "/" not in t:
                continue  # module names, inline code and the like
            add(t, recursive, seg)

    for seg in _shell_segments(cmd):
        raw = seg.strip()
        if raw.startswith("("):
            stack.append(state["cwd"])
        process(raw)
        if raw.endswith(")") and stack:
            state["cwd"] = stack.pop()
    return checks, unresolved, state["cwd"]


@overload
def audit_generator_transcript_strict(path: Path, *, task: str, own: str, extra_allowed: tuple[str, ...] = ...,
                                      extra_forbidden: tuple[str, ...] = ..., repo_root: str = ..., home: str = ...,
                                      outputs: Literal[False] = ...) -> list[dict]: ...


@overload
def audit_generator_transcript_strict(path: Path, *, task: str, own: str, extra_allowed: tuple[str, ...] = ...,
                                      extra_forbidden: tuple[str, ...] = ..., repo_root: str = ..., home: str = ...,
                                      outputs: Literal[True]) -> tuple[list[dict], list[dict]]: ...


def audit_generator_transcript_strict(path: Path, *, task: str, own: str, extra_allowed: tuple[str, ...] = (),
                                      extra_forbidden: tuple[str, ...] = (), repo_root: str = "/home/user/trace-contract",
                                      home: str = "/home/user", outputs: bool = False):
    """A stricter re-audit of a generator transcript's tool inputs and, with ``outputs``, its tool outputs (D44, D46).

    It combines three checks, so that it flags at least what the first audit flags:

    * **Resolved commands.** Shell commands are split at unquoted ``&&``, ``||``, ``;``,
      ``|``, ``&``, newlines, ``$(`` and backticks, with heredoc bodies set aside. Leading
      keywords (``do``, ``then``, ``(``), assignments (``VAR=x cmd``) and wrappers (``env``,
      ``timeout``, ``xargs``, ``sudo``) are removed; variables assigned earlier in the same
      command are substituted; ``cd`` is followed, within ``( ... )`` only until the closing
      parenthesis; relative paths are resolved against the repository root, where every
      Bash call of a subagent starts, and also against the directory the previous call
      ended in (a conservative extra). Reads of a path inside forbidden material are
      flagged, and so are recursive searches, listings, copies and archives (``grep -r``,
      ``--recursive``, ``rg``, every ``find`` root, ``ls -R``, ``tree``, ``du``, ``cp -r``,
      ``rsync``, ``tar``, ``diff -r``, the Grep and Glob tools, and git listings such as
      ``git status``, ``git diff`` or ``git show REV:path``) whose root contains forbidden
      material that they do not prune, and recursive searches whose root still holds a
      variable.
    * **Literal paths.** Every path-like token anywhere in the tool input (heredoc bodies,
      inline code, quoted arguments, search patterns) is resolved and flagged if it lies in
      forbidden material, except the arguments of exclusion options (``-path``,
      ``--exclude``) and of the command that registers the agent's own candidate. A held-out
      candidate id named in another CLI command is flagged too.
    * **The first audit's substring rule** (:func:`audit_generator_transcript`).

    Forbidden material: the task's verifiers or candidates, ``results/``, ``data/``,
    ``docs/``, the task's other workspaces, sealed material, ``/root`` except tool binaries,
    and ``extra_forbidden`` (session-local directories, such as the builder's scratch
    directory, whose path must not be written into the repository). ``extra_allowed`` names
    directories a role was asked to write (the reference-check directory for its writer).

    By default the result is the list of hits in tool inputs, exactly as before tool outputs
    were scanned, so the recorded audits reproduce. With ``outputs=True`` the result is
    ``(hits, exposures)``: ``exposures`` lists what the tool outputs (listings, ``git status``
    output, error messages, file contents) showed the agent, reported apart from its reads:

    * a path inside forbidden material: an absolute path, or, in the output of a shell
      command, a relative path resolved from the directory the command ends in (from the
      repository root, and from the directory the previous call ended in). Relative paths in
      other tools' outputs are not resolved;
    * a held-out candidate id of the task (``<task>-eval-...``, ``<task>-pre-correction``),
      except the agent's own: the ids it registered with ``add-candidate`` (a shell variable
      in such an id stands for any suffix), whose candidate files are not reported either.

    The outputs of the write tools (Write, Edit) are skipped: they confirm the write of the
    path in the call's input. Each exposure carries the tool result's event id and time, the
    event id of the call that produced it (``call``) and the line of the output that showed
    it. A hit or an exposure is a lead for a manual reading, not a finding.
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
    calls: dict = {}  # tool_call_id -> (tool, call event id, directories a shell command may end in)
    own_ids: set = set()  # patterns of the candidate ids the agent registered itself
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
            c2, u2, carried_next = _scan_command(cmd, carried, norm) if carried != repo_root else ([], [], end)
            checks += c1 + c2
            for tok, text, head in dict.fromkeys(u1 + u2):
                # Only if the directory before the variable holds forbidden material (a variable
                # with ".." in its value is not considered).
                if classify(head, True):
                    hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": tok,
                                 "why": "search rooted at an unresolved variable", "text": text})
        # Literal paths anywhere in the tool input (heredoc bodies, inline code, quoted
        # arguments, search patterns), resolved but not followed: a fail-safe for what the
        # command parser cannot see.
        def registers(seg: str) -> bool:
            w = _command_words(seg, {})
            return bool(w) and os.path.basename(w[0]) == "tracecontract" and w[1:2] == ["add-candidate"]

        texts = [str(ti[k]) for k in ("file_path", "path", "pattern", "notebook_path", "glob") if ti.get(k)]
        if cmd:  # every segment, heredoc bodies included, except the registration of the agent's own candidate
            body = "\n".join(seg for seg in _split_unquoted(cmd) if not registers(seg))
            # A path given to an exclusion option names what the command avoids (find -path ... -prune).
            texts.append(_EXCLUSION_ARG.sub(" ", body))
        # Directories the command may run in: the start, the carried one and every cd target.
        bases = [repo_root, carried]
        for seg in _shell_segments(cmd) if cmd else []:
            w = _command_words(seg, {})
            if w and w[0] == "cd" and len(w) > 1 and "$" not in w[1]:
                bases.append(norm(w[1], bases[-1]))
        bases = list(dict.fromkeys(bases))
        literal = []
        for text in texts:
            for m in _LITERAL_PATH.finditer(text):
                tok = m.group(0).rstrip(".,:;")
                ctx = text[max(0, m.start() - 80): m.end() + 80]
                if tok.startswith(("/", "~")):
                    literal.append((norm(tok, repo_root), ctx))
                else:
                    # A relative path counts only if it lands in forbidden material from every
                    # directory the command may run in.
                    resolved = [norm(tok, b) for b in bases]
                    if all(classify(r, False) for r in resolved):
                        literal.append((resolved[0], ctx))
        calls[ev.tool_call_id] = (ev.tool_name, ev.event_id, list(dict.fromkeys([end, carried_next])) if cmd else [])
        if cmd:
            carried = carried_next
        seen = set()
        for p, rec, text, pruned in checks:
            why = classify(p, rec, pruned)
            if why and (p, why) not in seen:
                seen.add((p, why))
                hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": p, "why": why, "text": text})
        for p, text in literal:
            why = classify(p, False)
            if why and not any(h["event_id"] == ev.event_id and h["path"] == p for h in hits):
                hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": p, "why": "path named in the tool input: " + why,
                             "text": text})
        # A held-out candidate named in a CLI command other than the registration of the agent's own candidate.
        for seg in _shell_segments(cmd) if cmd else []:
            words = _command_words(seg, {})
            if words and os.path.basename(words[0]) == "tracecontract" and words[1:2] != ["add-candidate"]:
                for w in words[1:]:
                    if re.fullmatch(rf"{re.escape(task)}-(?:eval-[\w-]+|pre-correction)", w):
                        hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": w,
                                     "why": "held-out candidate named in a CLI command", "text": seg[:300]})
            elif words and os.path.basename(words[0]) == "tracecontract":
                # A variable in the registered id (a loop or a shell function) stands for any suffix.
                own_ids.update(r"[\w-]+".join(map(re.escape, _ANY_VAR.split(w))) for w in words[2:]
                               if re.fullmatch(rf"{re.escape(task)}-(?:eval-[\w-]+|pre-correction)", _ANY_VAR.sub("0", w)))
    # The first audit's substring rule, so that this audit flags everything that one does.
    v1 = audit_generator_transcript(path, forbidden=(f"tasks/{task}/verifiers", f"tasks/{task}/candidates", "trace-contract/results",
                                                     "trace-contract/data", "trace-contract/docs", "cs_workspaces",
                                                     f"gen_workspaces/{task}/", ".tc_sealed", "scratchpad/sealed",
                                                     "scratchpad/scenarios", "scratchpad/reference", "/root/"),
                                    allowed=(own.rstrip("/") + "/", own, "/root/.local/bin/",
                                             *extra_allowed, *[os.path.relpath(x, repo_root) for x in extra_allowed]))
    for h in v1:
        if not any(x["event_id"] == h["event_id"] for x in hits):
            hits.append({"event_id": h["event_id"], "tool": h["tool"], "path": h["match"], "why": "substring match (first audit's rule)",
                         "text": h["text"]})
    if not outputs:
        return hits
    # What the tool outputs showed the agent, reported apart from its reads.
    heldout = re.compile(rf"(?<![\w-]){re.escape(task)}-(?:eval-[\w-]+|pre-correction)")
    own_re = re.compile("|".join(sorted(own_ids)) or r"(?!)")
    candidates = f"{repo_root}/tasks/{task}/candidates/"
    exposures: list[dict] = []
    for ev in s.events:
        if ev.kind != EventKind.tool_result or not ev.text:
            continue
        tool, call_id, ends = calls.get(ev.tool_call_id, (None, None, []))
        if tool in _WRITE_TOOLS:
            continue  # it only confirms the write of the path in its input, which the reads above cover
        found: dict = {}  # (path or id, why) -> its first match in the output
        for m in _LITERAL_PATH.finditer(ev.text):
            tok = m.group(0).rstrip(".,:;")
            for p in [norm(tok, repo_root)] if tok.startswith(("/", "~")) else [norm(tok, e) for e in ends]:
                why = classify(p, False)
                if why and not (p.startswith(candidates) and own_re.fullmatch(p[len(candidates):].removesuffix(".json"))):
                    found.setdefault((p, "shown in a tool output: " + why), m)
                    break
        for m in heldout.finditer(ev.text):
            if not own_re.fullmatch(m.group(0).rstrip("-")):
                found.setdefault((m.group(0).rstrip("-"), "held-out candidate named in a tool output"), m)
        for (p, why), m in found.items():
            exposures.append({"event_id": ev.event_id, "ts": ev.timestamp, "call": call_id, "tool": tool, "path": p,
                              "why": why, "text": _output_line(ev.text, m)})
    return hits, exposures


def _output_line(text: str, m: re.Match, width: int = 150) -> str:
    """The line of a tool output that holds a match, cut to ``width`` characters on either side of it."""
    a = max(text.rfind("\n", 0, m.start()) + 1, m.start() - width)
    b = text.find("\n", m.end())
    return text[a:min(len(text) if b < 0 else b, m.end() + width)]
