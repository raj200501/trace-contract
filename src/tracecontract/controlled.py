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


@dataclass(frozen=True)
class _AuditProfile:
    """What one strict audit counts as forbidden (see :func:`audit_generator_transcript_strict`)."""

    forbidden: tuple[str, ...]  # a path inside one of these roots is forbidden material
    allowed: tuple[str, ...]  # checked first: never forbidden
    markers: tuple[tuple[str, str], ...]  # (substring, why): a path holding it is forbidden, even inside an allowed root
    v1_forbidden: tuple[str, ...]  # the first audit's substring rule
    v1_allowed: tuple[str, ...]
    outside: bool = False  # flag every host path a tool input reads that is outside `allowed` and the system locations
    sandbox: str | None = None  # the repository the sandbox wrappers mount at /repo: their outputs' paths refer to it
    # The rules of the natural-agent profile (audit_natural_agent_transcript); their defaults leave the other profiles as
    # they were.
    outside_why: str | None = None  # the reason given for a host path outside `allowed` (FRESH_OUTSIDE by default)
    workspace: str | None = None  # the agent's own workspace, where the allowlisted CLI calls may point
    cli: tuple[str, ...] = ()  # the study CLI's subcommands allowed on paths inside `workspace`; any other CLI call is a hit
    cli_binary: str | None = None  # the CLI as an allowlisted call must name it: its absolute path
    network: bool = False  # the network rule (:func:`_network_uses`)
    tools: frozenset[str] | None = None  # the tools the agent may call; a call of any other tool is a hit
    # The natural profile's reading of shell commands: its own shell model and path scan (_natural_shell, _natural_scan),
    # a word that still holds code characters (quotes, brackets, newlines, `;`, `|`, `&`, `<`, `>`) is not a path, the
    # literal paths of each segment are resolved from where it runs (_natural_literals), and the outputs of commands that
    # named workspace paths only refer to the workspace.
    refine_words: bool = False


_SEALED_MARKERS = (("scratchpad/sealed", "sealed material"), ("scratchpad/scenarios", "sealed material"),
                   ("scratchpad/reference", "sealed material"))
# The suffix of a task's held-out candidate ids: eval candidates, the controlled pre-correction state and the natural
# pre-review state.
_HELDOUT = r"(?:eval-[\w-]+|pre-correction|pre-review)"
# Generic system locations, which a fresh attempt may read; /repo is the sandbox's view of its own repository.
_FRESH_SYSTEM = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/etc", "/dev", "/proc", "/sys", "/repo")
_SANDBOX_WRAPPERS = ("run_tests.sh", "run_python.sh")
FRESH_OUTSIDE = "outside the attempt's workspace"


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
    ``docs/``, the task's other workspaces, sealed material, the third-party data under
    ``{home}/ext``, ``/root`` except tool binaries, and ``extra_forbidden`` (session-local
    directories, such as the builder's scratch directory, whose path must not be written
    into the repository). ``extra_allowed`` names directories a role was asked to write
    (the reference-check directory for its writer).

    By default the result is the list of hits in tool inputs, exactly as before tool outputs
    were scanned, so the recorded audits reproduce. With ``outputs=True`` the result is
    ``(hits, exposures)``: ``exposures`` lists what the tool outputs (listings, ``git status``
    output, error messages, file contents) showed the agent, reported apart from its reads:

    * a path inside forbidden material: an absolute path, or, in the output of a shell
      command, a relative path resolved from the directory the command ends in (from the
      repository root, and from the directory the previous call ended in). Relative paths in
      other tools' outputs are not resolved;
    * a held-out candidate id of the task (``<task>-eval-...``, ``<task>-pre-correction``,
      ``<task>-pre-review``), except the agent's own: the ids it registered with
      ``add-candidate`` (a shell variable in such an id stands for any suffix), whose candidate
      files are not reported either.

    The outputs of the write tools (Write, Edit) are skipped: they confirm the write of the
    path in the call's input. Each exposure carries the tool result's event id and time, the
    event id of the call that produced it (``call``) and the line of the output that showed
    it. A hit or an exposure is a lead for a manual reading, not a finding.
    """
    import os

    profile = _AuditProfile(
        forbidden=(f"{repo_root}/tasks/{task}/verifiers", f"{repo_root}/tasks/{task}/candidates", f"{repo_root}/results",
                   f"{repo_root}/data", f"{repo_root}/docs", f"{home}/cs_workspaces", f"{home}/gen_workspaces/{task}",
                   f"{home}/.tc_sealed", f"{home}/ext", "/root", *[os.path.normpath(x) for x in extra_forbidden]),
        allowed=(os.path.normpath(own), "/root/.local/bin", *[os.path.normpath(x) for x in extra_allowed]),
        markers=_SEALED_MARKERS,
        v1_forbidden=(f"tasks/{task}/verifiers", f"tasks/{task}/candidates", "trace-contract/results", "trace-contract/data",
                      "trace-contract/docs", "cs_workspaces", f"gen_workspaces/{task}/", ".tc_sealed", "scratchpad/sealed",
                      "scratchpad/scenarios", "scratchpad/reference", "/root/"),
        v1_allowed=(own.rstrip("/") + "/", own, "/root/.local/bin/", *extra_allowed,
                    *[os.path.relpath(x, repo_root) for x in extra_allowed]))
    hits, exposures = _strict_audit(path, profile, task=task, repo_root=repo_root, home=home, outputs=outputs)
    return (hits, exposures) if outputs else hits


def audit_fresh_attempt_transcript(path: Path, *, task: str, workspace: str, extra_forbidden: tuple[str, ...] = (),
                                   repo_root: str = "/home/user/trace-contract",
                                   home: str = "/home/user") -> tuple[list[dict], list[dict]]:
    """The fresh-attempt profile of the strict audit (protocol v0.8 §16.2): ``(hits, exposures)`` of one attempt.

    Everything outside the attempt's own ``workspace`` is forbidden. Tool inputs and tool outputs are both
    scanned with the machinery of :func:`audit_generator_transcript_strict` (resolved commands, literal paths,
    the first audit's substring rule, held-out candidate ids), with these forbidden roots:

    * the repository (``repo_root``), the cwd every Bash call of a subagent starts in: a relative path read
      without a ``cd`` into the workspace, ``git status`` or a Grep without a path reads the repository;
    * the study's home ``home``, which holds the sealed directory ``.tc_sealed``, the third-party data under
      ``ext`` and the build session's old workspaces (``cs_workspaces``, ``gen_workspaces``);
    * the other workspaces: everything in the directory that holds the attempt's workspace;
    * ``/root`` (except tool binaries) and every Claude session directory (``/tmp/claude-*``);
    * ``extra_forbidden``.

    Beyond those, every other host path that a tool input reads, lists, searches, runs or writes outside the
    workspace is flagged as ``outside the attempt's workspace``, except generic system locations (``/usr``,
    ``/bin``, ``/lib``, ``/etc``, ``/dev``, ``/proc``, ``/sys``) and the sandbox's ``/repo``. In tool outputs
    only forbidden roots count, as generic paths there come from the sandbox container; the outputs of the
    attempt's own wrappers (``run_tests.sh``, ``run_python.sh``) are container output, so a relative path in
    them refers to the workspace's ``repo/``, the container's ``/repo``. Per §16.2, an attempt with any hit or
    exposure is flagged, excluded from every analysis and reported.
    """
    import os

    ws = os.path.normpath(workspace)
    parent = os.path.dirname(ws)
    if parent.count("/") < 2:
        raise ValueError(f"the attempt workspace {ws} must lie in a dedicated directory of workspaces, not in {parent}")
    forbidden = (repo_root, home, parent, "/root", *[os.path.normpath(x) for x in extra_forbidden])
    profile = _AuditProfile(
        forbidden=tuple(dict.fromkeys(forbidden)), allowed=(ws, "/root/.local/bin"),
        markers=(*_SEALED_MARKERS, ("/tmp/claude-", "a Claude session directory")),
        v1_forbidden=(f"tasks/{task}/verifiers", f"tasks/{task}/candidates", "trace-contract/results", "trace-contract/data",
                      "trace-contract/docs", "cs_workspaces", "gen_workspaces/", ".tc_sealed", "scratchpad/sealed",
                      "scratchpad/scenarios", "scratchpad/reference", "/root/", repo_root, f"{home}/ext", "/tmp/claude-"),
        v1_allowed=(ws + "/", ws, "/root/.local/bin/"), outside=True, sandbox=os.path.join(ws, "repo"))
    return _strict_audit(path, profile, task=task, repo_root=repo_root, home=home, outputs=True)


# --------------------------------------------------------------------------- the natural-agent profile (natural-agent:v1)

NATURAL_PROFILE = "natural-agent:v1"
NATURAL_OUTSIDE = "outside the agent's own workspace"
NATURAL_CLI = ("lint-tests", "check-proposals")  # the subcommands a natural agent may run on its own files
NATURAL_CLI_WHY = ("a call of the study's CLI outside the allowlist (<repo>/.venv/bin/tracecontract lint-tests or "
                   "check-proposals, named by its absolute path, on paths inside the agent's own workspace)")
# The tools of a natural agent as the natural recipe fixes them (Read, Write, Edit, Glob, Grep and Bash), with the shell's
# companions for background commands (BashOutput, KillShell) and the harness's final report. A call of any other tool is
# a hit, MultiEdit and NotebookEdit included; WebFetch, WebSearch and MCP tools are network hits.
NATURAL_TOOLS = frozenset({"Read", "Write", "Edit", "Glob", "Grep", "Bash", "BashOutput", "KillShell", "KillBash",
                           "StructuredOutput", "SubagentHandback"})
NATURAL_TOOLS_WHY = "a tool outside the natural agents' tool set (Read, Write, Edit, Glob, Grep and the shell)"
# Where the harness keeps its session directories: what begins each temporary directory, and the directory of records.
SESSION_DIRS = ("/tmp/claude-", "/root/.claude")
_NET_TOOLS = {"WebFetch": "a WebFetch tool call", "WebSearch": "a WebSearch tool call"}
# Commands that reach the network whatever their arguments (downloaders, remote shells, DNS and ICMP tools, cloud CLIs,
# runners that fetch a package to run it).
_NET_COMMANDS = frozenset({"curl", "wget", "nc", "ncat", "netcat", "socat", "telnet", "ssh", "scp", "sftp", "ftp", "gh",
                           "aria2c", "axel", "lynx", "links", "w3m", "http", "https", "xh", "ping", "ping6", "traceroute",
                           "tracepath", "dig", "nslookup", "host", "whois", "rclone", "aws", "gcloud", "gsutil", "bq", "az",
                           "kubectl", "huggingface-cli", "easy_install", "uvx", "npx", "pnpx", "bunx"})
# Container engines: a container started directly has the default network; only the sandbox wrappers start containers
# with --network none.
_CONTAINER_ENGINES = frozenset({"docker", "podman", "nerdctl", "docker-compose", "buildah", "skopeo", "ctr", "crictl"})
_NET_GIT = frozenset({"clone", "fetch", "pull", "ls-remote", "remote", "push", "send-email", "svn"})
_NET_GIT_SUB = {"submodule": frozenset({"update", "add"}), "lfs": frozenset({"fetch", "pull", "push", "clone"})}
_NET_PIP = frozenset({"download", "index", "search"})  # pip subcommands that always use the index
_PIP_COMMANDS = frozenset({"install", "download", "uninstall", "freeze", "inspect", "list", "show", "check", "config",
                           "search", "cache", "index", "wheel", "hash", "completion", "debug", "help"})
_RPM_NET = frozenset({"install", "reinstall", "update", "upgrade", "download", "makecache", "search", "info",
                      "check-update"})
_APT_NET = frozenset({"install", "reinstall", "update", "upgrade", "dist-upgrade", "full-upgrade", "safe-upgrade",
                      "download", "source", "build-dep", "changelog"})
_CONDA_NET = frozenset({"install", "create", "update", "upgrade", "search", "env"})
# Package managers and version-control clients: the subcommands that download, resolve against an index or publish. A
# call with --offline is not counted.
_DOWNLOADERS: dict[str, frozenset[str]] = {
    "uv": frozenset({"add", "remove", "sync", "lock", "run", "tool", "python", "export", "tree", "init", "build",
                     "publish", "self"}),
    "pipx": frozenset({"install", "install-all", "inject", "upgrade", "upgrade-all", "upgrade-shared", "reinstall",
                       "reinstall-all", "run"}),
    "npm": frozenset({"install", "i", "in", "ins", "inst", "insta", "instal", "isnt", "isnta", "isntal", "isntall", "add",
                      "ci", "clean-install", "install-test", "it", "cit", "update", "up", "upgrade", "exec", "x", "view",
                      "v", "info", "show", "search", "s", "se", "find", "publish", "audit", "outdated", "login",
                      "adduser", "whoami", "ping", "doctor", "create", "dlx"}),
    "yarn": frozenset({"add", "install", "upgrade", "up", "dlx", "create", "info", "npm", "global", "outdated", "audit",
                       "publish"}),
    "pnpm": frozenset({"add", "install", "i", "update", "up", "upgrade", "dlx", "create", "outdated", "audit", "publish",
                       "fetch", "view", "info"}),
    "bun": frozenset({"add", "install", "i", "update", "upgrade", "x", "create", "outdated", "publish"}),
    "apt-get": _APT_NET, "apt": _APT_NET, "aptitude": _APT_NET,
    "yum": _RPM_NET, "dnf": _RPM_NET, "microdnf": _RPM_NET,
    "apk": frozenset({"add", "update", "upgrade", "fetch", "search"}),
    "brew": frozenset({"install", "reinstall", "update", "upgrade", "fetch", "search", "tap", "info"}),
    "conda": _CONDA_NET, "mamba": _CONDA_NET, "micromamba": _CONDA_NET,
    "poetry": frozenset({"install", "add", "update", "lock", "search", "self", "publish", "sync"}),
    "pdm": frozenset({"install", "add", "update", "lock", "sync", "search", "publish", "self"}),
    "pipenv": frozenset({"install", "update", "lock", "sync", "upgrade"}),
    "hatch": frozenset({"run", "env", "shell", "test", "build", "publish"}),
    "rye": frozenset({"sync", "add", "install", "fetch", "self", "lock"}),
    "gem": frozenset({"install", "fetch", "update", "search", "sources", "push"}),
    "cargo": frozenset({"install", "fetch", "update", "add", "search", "publish"}),
    "go": frozenset({"get", "install", "mod"}),
    "svn": frozenset({"checkout", "co", "export", "update", "up", "import", "commit", "ci", "switch", "sw", "list", "ls",
                      "log", "cat", "info"}),
    "hg": frozenset({"clone", "pull", "push", "incoming", "in", "outgoing", "out"}),
}
# Python modules that reach the network (a module, or one of its submodules). Plain ``import urllib`` counts too; other
# urllib submodules (urllib.parse) do not.
_NET_MODULES = ("urllib.request", "urllib.robotparser", "urllib3", "http.client", "http.server", "requests", "httpx",
                "socket", "socketserver", "aiohttp", "ftplib", "smtplib", "poplib", "imaplib", "nntplib", "telnetlib",
                "xmlrpc.client", "xmlrpc.server", "websocket", "websockets", "paramiko", "pycurl", "httplib2")
# Other interpreters: the options whose value is inline code, those that take another value (the rest of their cluster
# or the next word), and those whose value is the rest of their cluster only (perl -MModule); and their network code.
_INTERPRETERS = {"node": ("ep", "r", ""), "nodejs": ("ep", "r", ""), "perl": ("eE", "", "MmIxiDdC"),
                 "ruby": ("e", "rICE", "")}
_SCRIPT_NET = {
    "node": re.compile(r"""\brequire\s*\(\s*['"](?:node:)?(?:https?|http2|net|tls|dgram|dns|undici|axios|node-fetch)['"]"""
                       r"""|\bfrom\s+['"](?:node:)?(?:https?|http2|net|tls|dgram|dns|undici|axios|node-fetch)['"]"""
                       r"""|\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b"""),
    "perl": re.compile(r"\b(?:IO::Socket|LWP|HTTP::Tiny|Net::(?:HTTP|FTP|SMTP|Ping|DNS)|Socket|Mojo::UserAgent"
                       r"|WWW::Mechanize)\b"),
    "ruby": re.compile(r"""\brequire\s*\(?\s*['"](?:net/\w+|open-uri|socket|httparty|faraday|rest-client|httpclient)['"]"""
                       r"""|\bNet::HTTP\b|\b(?:TCP|UDP)Socket\b|\bURI\.open\b|\bOpenURI\b"""),
}
_PYTHON = re.compile(r"(?:python|pypy)(?:\d+(?:\.\d+)*)?")
_PIP = re.compile(r"pip(?:\d+(?:\.\d+)*)?")
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "mksh", "ash"})
_FROM_IMPORT = re.compile(r"\bfrom\s+([A-Za-z_][\w.]*)\s+import\s+\(?\s*([\w\s,*]+)")
_PLAIN_IMPORT = re.compile(r"\bimport\s+([A-Za-z_][\w.]*(?:\s+as\s+\w+)?(?:\s*,\s*[A-Za-z_][\w.]*(?:\s+as\s+\w+)?)*)")
_DYNAMIC_IMPORT = re.compile(r"(?:__import__|import_module)\(\s*['\"]([\w.]+)['\"]")
_CODE_CHARS = "\n\t'\"()[]{}<>|;&`"
_ASSIGNED = re.compile(r"[A-Za-z_]\w*=")
_VARIANTS = ("initial_only", "full_session", "reference")
_REMOTE = re.compile(r"(?:[\w.-]+@)?[\w.-]+::?(?!//)|rsync://")  # rsync's remote forms: host:path, host::module, rsync://
# A word that the path scan takes for a number, a range or an operator, not a path (an option's value: head -n 20, sed's
# 1,20p).
_NOT_A_PATH = re.compile(r"[-+]?\d[\d,.:]*[A-Za-z]?|\d?[<>&|;()]+\d?|-")
_HEREDOC_OPEN = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z_][\w.-]*))")
_REDIR_OP = re.compile(r"&>>?|<<<|<<-?|<>|<&|>>|>&|>\||<|>")
_FILE_REDIRS = frozenset({"<", ">", ">>", "&>", "&>>", ">|", "<>", ">&", "<&"})
# Wrappers: a command that runs the command after its own options. Per wrapper: the short options that take a value (the
# rest of their cluster, or the next word), the long ones, and the number of positional words before the command (the
# duration of timeout, the mask of taskset, the priority of chrt, the lock file of flock).
_WRAPPER_SPECS: dict[str, tuple[str, frozenset[str], int]] = {
    "env": ("uCS", frozenset({"--unset", "--chdir", "--split-string"}), 0),
    "nice": ("n", frozenset({"--adjustment"}), 0),
    "ionice": ("cnpPu", frozenset({"--class", "--classdata", "--pid", "--pgid", "--uid"}), 0),
    "timeout": ("sk", frozenset({"--signal", "--kill-after"}), 1),
    "sudo": ("ugCDhpRrtTU", frozenset({"--user", "--group", "--close-from", "--chdir", "--host", "--prompt", "--chroot",
                                       "--role", "--type", "--command-timeout", "--other-user"}), 0),
    "doas": ("uC", frozenset(), 0),
    "stdbuf": ("ioe", frozenset({"--input", "--output", "--error"}), 0),
    "xargs": ("adEILnPs", frozenset({"--arg-file", "--delimiter", "--eof", "--replace", "--max-lines", "--max-args",
                                      "--max-procs", "--max-chars", "--process-slot-var"}), 0),
    "time": ("of", frozenset({"--output", "--format"}), 0),
    "nohup": ("", frozenset(), 0), "command": ("", frozenset(), 0), "builtin": ("", frozenset(), 0),
    "exec": ("a", frozenset(), 0), "setsid": ("", frozenset(), 0), "unbuffer": ("", frozenset(), 0),
    "taskset": ("", frozenset(), 1), "chrt": ("", frozenset(), 1),
    "flock": ("wEc", frozenset({"--timeout", "--conflict-exit-code", "--command"}), 1),
    "watch": ("n", frozenset({"--interval"}), 0),
}
# The wrapper options whose value is a command: env -S splits it into words, flock -c runs it in a shell.
_COMMAND_OPTIONS = {("env", "-S"): "split", ("env", "--split-string"): "split", ("flock", "-c"): "shell",
                    ("flock", "--command"): "shell"}
# The options of the path scan's commands that take a value (short letters, long names); their values are not paths,
# except those of _PATH_OPTIONS. Aliases share a table.
_VALUE_OPTIONS: dict[str, tuple[str, frozenset[str]]] = {
    "head": ("nc", frozenset({"--lines", "--bytes"})),
    "tail": ("ncs", frozenset({"--lines", "--bytes", "--sleep-interval", "--pid", "--max-unchanged-stats"})),
    "grep": ("ABCDdefm", frozenset({"--after-context", "--before-context", "--context", "--devices", "--directories",
                                    "--regexp", "--file", "--max-count", "--include", "--exclude", "--exclude-dir",
                                    "--exclude-from", "--label", "--group-separator", "--binary-files"})),
    "rg": ("ABCEMdefgjmrtT", frozenset({"--after-context", "--before-context", "--context", "--encoding", "--max-columns",
                                        "--max-depth", "--regexp", "--file", "--glob", "--iglob", "--threads",
                                        "--max-count", "--replace", "--type", "--type-not", "--type-add", "--sort",
                                        "--sortr", "--pre", "--pre-glob", "--ignore-file", "--max-filesize",
                                        "--path-separator", "--colors", "--context-separator"})),
    "sed": ("efl", frozenset({"--expression", "--file", "--line-length"})),
    "awk": ("Ffv", frozenset({"--field-separator", "--file", "--assign"})),
    "cut": ("bcdf", frozenset({"--bytes", "--characters", "--delimiter", "--fields", "--output-delimiter"})),
    "sort": ("kSTto", frozenset({"--key", "--buffer-size", "--temporary-directory", "--field-separator", "--output",
                                 "--parallel", "--files0-from"})),
    "uniq": ("fsw", frozenset({"--skip-fields", "--skip-chars", "--check-chars"})),
    "diff": ("CFILUXx", frozenset({"--context", "--unified", "--show-function-line", "--ignore-matching-lines", "--label",
                                   "--exclude", "--exclude-from", "--from-file", "--to-file", "--width", "--tabsize",
                                   "--horizon-lines"})),
    "du": ("BdtX", frozenset({"--block-size", "--max-depth", "--threshold", "--exclude", "--exclude-from",
                              "--time-style", "--files0-from"})),
    "tree": ("ILPo", frozenset({"--filelimit", "--charset", "--timefmt", "--sort", "--fromfile"})),
    "ls": ("ITw", frozenset({"--ignore", "--hide", "--tabsize", "--width", "--sort", "--format", "--time",
                             "--time-style", "--block-size", "--quoting-style", "--indicator-style"})),
    "wc": ("", frozenset({"--files0-from"})),
    "nl": ("bdfhilnsvw", frozenset()),
    "xxd": ("cglos", frozenset()),
    "od": ("AjNStw", frozenset()),
    "jq": ("f", frozenset({"--from-file", "--indent"})),
    "cp": ("St", frozenset({"--suffix", "--target-directory"})),
    "mv": ("St", frozenset({"--suffix", "--target-directory"})),
    "tar": ("bCfFgHKLNTVX", frozenset({"--directory", "--file", "--files-from", "--exclude-from", "--exclude",
                                       "--blocking-factor", "--newer", "--label", "--listed-incremental", "--format",
                                       "--starting-file", "--transform", "--owner", "--group", "--mode", "--mtime"})),
    "base64": ("w", frozenset({"--wrap"})), "fold": ("w", frozenset({"--width"})),
    "column": ("cosN", frozenset({"--output-width", "--separator", "--output-separator", "--table-columns"})),
    "split": ("abCln", frozenset()), "cmp": ("in", frozenset({"--ignore-initial", "--bytes"})),
    "strings": ("nte", frozenset({"--bytes", "--radix", "--encoding"})), "hexdump": ("efns", frozenset()),
    "paste": ("d", frozenset({"--delimiters"})), "stat": ("c", frozenset({"--format", "--printf"})),
    "file": ("efFmP", frozenset({"--files-from", "--magic-file", "--exclude", "--separator", "--parameter"})),
    "realpath": ("", frozenset({"--relative-to", "--relative-base"})),
    "patch": ("BDFVYdgiopzr", frozenset({"--directory", "--input", "--output", "--reject-file", "--strip"})),
    "iconv": ("fto", frozenset({"--from-code", "--to-code", "--output"})),
    "shuf": ("ino", frozenset({"--head-count", "--input-range", "--output"})),
    "gzip": ("S", frozenset({"--suffix"})),
}
_PATH_OPTIONS: dict[str, tuple[str, frozenset[str]]] = {
    "grep": ("f", frozenset({"--file", "--exclude-from"})), "rg": ("f", frozenset({"--file", "--ignore-file"})),
    "sed": ("f", frozenset({"--file"})), "awk": ("f", frozenset({"--file"})), "jq": ("f", frozenset({"--from-file"})),
    "sort": ("To", frozenset({"--temporary-directory", "--output", "--files0-from"})),
    "diff": ("X", frozenset({"--exclude-from", "--from-file", "--to-file"})),
    "du": ("X", frozenset({"--exclude-from", "--files0-from"})), "tree": ("o", frozenset({"--fromfile"})),
    "cp": ("t", frozenset({"--target-directory"})), "mv": ("t", frozenset({"--target-directory"})),
    "tar": ("CfgKTX", frozenset({"--directory", "--file", "--files-from", "--exclude-from", "--listed-incremental",
                                 "--starting-file"})),
    "patch": ("dior", frozenset({"--directory", "--input", "--output", "--reject-file"})),
    "file": ("fm", frozenset({"--files-from", "--magic-file"})), "wc": ("", frozenset({"--files0-from"})),
    "shuf": ("o", frozenset({"--output"})), "iconv": ("o", frozenset({"--output"})),
    "realpath": ("", frozenset({"--relative-to", "--relative-base"})),
}
_OPTION_ALIASES = {"egrep": "grep", "fgrep": "grep", "gawk": "awk", "mawk": "awk", "gunzip": "gzip", "zcat": "gzip"}
_TWO_VALUES = {"jq": frozenset({"--arg", "--argjson", "--slurpfile", "--rawfile"})}  # options that take two words


def audit_natural_agent_transcript(path: Path, *, task: str, workspace: str, extra_forbidden: tuple[str, ...] = (),
                                   repo_root: str = "/home/user/trace-contract", home: str = "/home/user",
                                   session_dirs: tuple[str, ...] = SESSION_DIRS) -> tuple[list[dict], list[dict]]:
    """The natural-agent profile of the strict audit (``natural-agent:v1``): ``(hits, exposures)`` of one natural agent.

    Every agent of the natural arm (contract proposers, test generators, attackers, revisers, reference-check writers and
    reviewers, labelers, held-out generators, mappers, checkers) works in one workspace of its own under
    ``/home/user/nat_ws/<task>/`` (an attacker's group of states counts as one). The profile is the fresh-attempt profile
    (:func:`audit_fresh_attempt_transcript`): everything outside ``workspace`` is forbidden (the repository, ``data/natural``
    with it, the study's home with the sealed directory, the third-party data under ``{home}/ext`` and the other
    workspaces, ``/root`` except tool binaries, every Claude session directory and ``extra_forbidden``), and tool inputs
    and tool outputs are both scanned. Held-out candidate ids include ``<task>-pre-review``. In addition:

    * **CLI allowlist.** The study's CLI may be run as ``<repo>/.venv/bin/tracecontract lint-tests|check-proposals
      <paths inside the workspace>``: the CLI named by its absolute path, one of the two subcommands, only paths inside
      the workspace (a relative path counts if it lands there from every directory the command may run in; a variable
      only if the command assigns it first), ``--variant <variant>`` for check-proposals, and redirections to the
      workspace or ``/dev/null``. Such a call is not a read of the repository, and the relative paths in its output refer
      to the workspace. Every other call of the CLI is a hit (:data:`NATURAL_CLI_WHY`), ``add-candidate`` included, since
      the host does every task-directory step.
    * **Network rule** (:func:`_network_uses`): WebFetch, WebSearch and MCP tool calls; and in shell commands curl, wget,
      nc, ssh, gh and the other commands of :data:`_NET_COMMANDS`; a container engine called directly (``docker run``,
      ``docker pull``: only the sandbox wrappers start containers offline); git clone, fetch, pull, push, ls-remote,
      remote, ``submodule update`` and ``lfs fetch``; pip download (and index, search), pip install or wheel without
      ``--no-index``; the downloading subcommands of other package managers (:data:`_DOWNLOADERS`: uv, pipx, npm,
      apt-get and others) without ``--offline``; and host code that uses the network: Python that imports urllib.request,
      http.client, requests, httpx, socket or a module of their kind (:data:`_NET_MODULES`), and node, perl or ruby code of
      that kind. The code is found wherever the shell gives it: inline (``-c``, ``-e``), in a heredoc or here-string, on
      standard input from a file (``< FILE``) or a pipe (``cat FILE |``, ``echo ... |``), or in a script the agent wrote
      (with the Write or Edit tools, a heredoc, ``echo``/``printf`` redirected, a copy), run by an interpreter or by its
      path (``./get.sh``, by its shebang), with the modules and files it imports or names that the agent wrote. ``bash
      -c`` strings, heredocs fed to a shell, ``eval``, ``find -exec`` and command substitutions are followed, and
      wrappers are taken apart with their options (``nice -n 10``, ``timeout -s KILL 10``, ``env -u VAR``, ``xargs``).
      Code given to the sandbox wrappers (``run_tests.sh``, ``run_python.sh``) runs offline and is not counted; code that
      builds a command at run time (``subprocess`` with a computed argument) is not followed.
    * **Tools.** A call of a tool outside :data:`NATURAL_TOOLS` (a task tool, an agent spawn, MultiEdit) is a hit.
    * **The shell model.** Shell commands are read by the profile's own parser (:func:`_natural_shell`): comments are
      dropped, each heredoc body belongs to the segment that opens it, redirections are told apart from words (``2>&1``,
      ``<<EOF``, ``< FILE``), ``cd``, ``pushd`` and ``popd`` are followed, and substitutions inside double quotes are
      segments of their own. The path scan (:func:`_natural_scan`) does not take inline code (``python3 -c``), a sed,
      awk or jq script, a grep pattern, an option's value (``head -n 20``) or a bare number for a path; follows ``bash
      -c`` strings; counts redirection targets, a command run by its path and every git command's repository; and a
      bare ``ls`` (``tree``, ``du``) lists the directory it runs in. A word that still holds code characters is not
      taken for a path either.
    * **Literal paths** (:func:`_natural_literals`): a path named in a shell command is resolved from the directory its
      segment runs in, as the call starts in the repository root (the directory an earlier call ended in, a
      conservative extra of the path scan, exempts nothing), from the sandbox's repository for the wrappers' arguments,
      and through ``bash -c`` strings; a relative path in a Grep or Glob pattern from the tool's path; a literal
      ``VAR=/path`` names the path after the ``=``.
    * **Tool outputs.** A relative path in the output of a command that named paths inside the workspace only, and
      had no hit, refers to the workspace's material (``cat <workspace>/reference.diff``, ``git -C <workspace>/repo
      diff``, a link in a README): it is an exposure only if it leads into forbidden material from each directory the
      command named. Other outputs are read as in the fresh-attempt profile.
    * **The first audit's substring rule** leaves out the allowlisted CLI calls of a command, however they are spaced.

    ``session_dirs`` names the harness's session directories (default :data:`SESSION_DIRS`): a path that holds one of
    them is a Claude session directory, wherever it is. Each hit or exposure is a lead for a written assessment, not a
    finding.
    """
    import os

    ws = os.path.normpath(workspace)
    parent = os.path.dirname(ws)
    if not ws.startswith("/") or parent.count("/") < 2:
        raise ValueError(f"the agent's workspace {ws} must be an absolute path in a dedicated directory of workspaces")
    repo = os.path.normpath(repo_root)
    if ws == repo or ws.startswith(repo + "/") or repo.startswith(ws + "/"):
        raise ValueError(f"the agent's workspace {ws} must lie outside the repository")
    forbidden = (repo, os.path.normpath(home), parent, "/root", *[os.path.normpath(x) for x in extra_forbidden])
    cli = f"{repo}/.venv/bin/tracecontract"
    profile = _AuditProfile(
        forbidden=tuple(dict.fromkeys(forbidden)), allowed=(ws, "/root/.local/bin"),
        markers=(*_SEALED_MARKERS, *((d, "a Claude session directory") for d in session_dirs)),
        v1_forbidden=(f"tasks/{task}/verifiers", f"tasks/{task}/candidates", "trace-contract/results", "trace-contract/data",
                      "trace-contract/docs", "cs_workspaces", "gen_workspaces/", ".tc_sealed", "scratchpad/sealed",
                      "scratchpad/scenarios", "scratchpad/reference", "/root/", repo, f"{home}/ext", *session_dirs,
                      "data/natural", "nat_ws/", "nat_runrec"),
        v1_allowed=(ws + "/", ws, "/root/.local/bin/", *(f"{cli} {c} " for c in NATURAL_CLI)), outside=True,
        sandbox=os.path.join(ws, "repo"), outside_why=NATURAL_OUTSIDE, workspace=ws, cli=NATURAL_CLI, cli_binary=cli,
        network=True, tools=NATURAL_TOOLS, refine_words=True)
    return _strict_audit(path, profile, task=task, repo_root=repo, home=home, outputs=True)


# ----------------------------------------------------------------------------------------- the natural profile's shell model


def _strip_bodies(cmd: str) -> tuple[str, list[tuple[int, str]]]:
    """``(text, heredocs)``: a shell command without its comments and heredoc bodies, and each heredoc as ``(position of
    its operator in text, body)``. Quotes, backslashes and arithmetic ``$((...))`` are respected; several heredocs may
    open on one line (their bodies follow in order); a here-string (``<<<``) is not a heredoc."""
    out: list[str] = []
    size = 0
    docs: list[tuple[int, str]] = []
    pending: list[tuple[int, str]] = []
    i, n, q = 0, len(cmd), None

    def emit(s: str) -> None:
        nonlocal size
        out.append(s)
        size += len(s)

    while i < n:
        c = cmd[i]
        if q is not None:
            if c == "\\" and q == '"' and i + 1 < n:
                emit(cmd[i:i + 2])
                i += 2
                continue
            emit(c)
            q = None if c == q else q
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            emit(cmd[i:i + 2])
            i += 2
            continue
        if c in "'\"":
            q = c
            emit(c)
            i += 1
            continue
        if c == "#" and (size == 0 or out[-1][-1] in " \t\n;&|()"):
            j = cmd.find("\n", i)
            i = n if j < 0 else j
            continue
        if cmd.startswith("$((", i):
            j = cmd.find("))", i)
            j = n if j < 0 else j + 2
            emit(cmd[i:j])
            i = j
            continue
        if cmd.startswith("<<", i) and not cmd.startswith("<<<", i) and (i == 0 or cmd[i - 1] != "<"):
            m = _HEREDOC_OPEN.match(cmd, i)
            if m:
                pending.append((size, next(g for g in m.groups()[1:] if g is not None)))
                emit(m.group(0))
                i = m.end()
                continue
        if c == "\n" and pending:
            emit(c)
            i += 1
            for pos, delim in pending:
                body: list[str] = []
                while i < n:
                    j = cmd.find("\n", i)
                    j = n if j < 0 else j
                    line, i = cmd[i:j], j + 1
                    if line.strip() == delim:
                        break
                    body.append(line)
                docs.append((pos, "\n".join(body)))
            pending = []
            continue
        emit(c)
        i += 1
    docs += [(pos, "") for pos, _ in pending]
    return "".join(out), docs


def _split_ops(text: str) -> list[tuple[str, int, int]]:
    """``(operator, start, end)`` of each segment of a command without heredoc bodies (:func:`_strip_bodies`), split at
    unquoted ``&&``, ``||``, ``;``, ``|`` (and ``|&``), ``&``, newlines, ``$(``, ``<(``, ``>(`` and backticks, but not at the
    ``&`` or ``|`` of a redirection (``2>&1``, ``&>file``, ``>|file``) or inside ``$((...))``; the operator is the one
    before the segment (empty for the first)."""
    spans: list[tuple[str, int, int]] = []
    start, op, i, n, q = 0, "", 0, len(text), None
    while i < n:
        c = text[i]
        if q is not None:
            if c == "\\" and q == '"':
                i += 2
                continue
            q = None if c == q else q
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if c in "'\"":
            q = c
            i += 1
            continue
        if text.startswith("$((", i):
            j = text.find("))", i)
            i = n if j < 0 else j + 2
            continue
        two = text[i:i + 2]
        if two in ("&&", "||", "$(", "<(", ">(", "|&"):
            spans.append((op, start, i))
            op, i = ("|" if two == "|&" else two), i + 2
            start = i
            continue
        if c in "&|" and ((c == "&" and text[i + 1:i + 2] == ">") or (i > 0 and text[i - 1] in "<>")):
            i += 1
            continue
        if c in ";|&\n`":
            spans.append((op, start, i))
            op, i = c, i + 1
            start = i
            continue
        i += 1
    spans.append((op, start, n))
    return [(o, a, b) for o, a, b in spans if text[a:b].strip()]


def _quoted_substitutions(text: str) -> list[str]:
    """The commands of the substitutions (``$(...)``, backticks) inside the double-quoted strings of one segment, which
    :func:`_split_ops` leaves in place: the shell runs them too."""
    out: list[str] = []
    i, n, q = 0, len(text), None
    while i < n:
        c = text[i]
        if q == "'":
            q = None if c == "'" else q
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if q == '"' and text.startswith("$(", i) and not text.startswith("$((", i):
            depth, j, qq = 1, i + 2, None
            while j < n and depth:
                d = text[j]
                if d == "\\":
                    j += 2
                    continue
                if qq is not None:
                    qq = None if d == qq else qq
                elif d in "'\"":
                    qq = d
                elif d == "(":
                    depth += 1
                elif d == ")":
                    depth -= 1
                j += 1
            out.append(text[i + 2:j - 1] if depth == 0 else text[i + 2:j])
            i = j
            continue
        if q == '"' and c == "`":
            j = text.find("`", i + 1)
            j = n if j < 0 else j
            out.append(text[i + 1:j])
            i = j + 1
            continue
        if q is None and c in "'\"":
            q = c
        elif q == '"' and c == '"':
            q = None
        i += 1
    return out


@dataclass(frozen=True)
class _Seg:
    """One segment of a shell command (:func:`_natural_segments`)."""

    text: str  # without heredoc bodies and comments
    op: str  # the operator before it (:func:`_split_ops`)
    bodies: tuple[str, ...] = ()  # the bodies of the heredocs it opens, in order
    sub: bool = False  # a substitution inside a double-quoted string of the segment before


def _natural_segments(cmd: str, depth: int = 0) -> list[_Seg]:
    """The segments of a shell command (:func:`_strip_bodies`, :func:`_split_ops`), each with its heredoc bodies, and after
    each segment the segments of the substitutions inside its double-quoted strings (:func:`_quoted_substitutions`)."""
    text, docs = _strip_bodies(cmd)
    out: list[_Seg] = []
    for op, a, b in _split_ops(text):
        seg = _Seg(text[a:b].strip(), op, tuple(body for pos, body in docs if a <= pos < b))
        out.append(seg)
        if depth < 3:
            for inner in _quoted_substitutions(seg.text):
                out += [_Seg(s.text, s.op or "$(", s.bodies, True) for s in _natural_segments(inner, depth + 1)]
    return out


def _tokens(seg: str) -> list[tuple[str, bool]]:
    """The words of one segment as the shell splits them, quotes and backslashes removed, each with whether it is an
    unquoted redirection operator (``<``, ``>``, ``>>``, ``2>``, ``&>``, ``>&``, ``<<``, ``<<-``, ``<<<``, ...), which the
    shell takes apart from the words around it. Unbalanced quotes split at whitespace."""
    toks: list[tuple[str, bool]] = []
    cur: list[str] = []
    started = False
    i, n, q = 0, len(seg), None

    def flush() -> None:
        nonlocal cur, started
        if started:
            toks.append(("".join(cur), False))
        cur, started = [], False

    while i < n:
        c = seg[i]
        if q == "'":
            if c == "'":
                q = None
            else:
                cur.append(c)
            i += 1
            continue
        if q == '"':
            if c == "\\" and i + 1 < n and seg[i + 1] in '"\\$`\n':
                cur.append(seg[i + 1])
                i += 2
                continue
            if c == '"':
                q = None
            else:
                cur.append(c)
            i += 1
            continue
        if c in " \t\n":
            flush()
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            if seg[i + 1] != "\n":
                cur.append(seg[i + 1])
            started = True
            i += 2
            continue
        if c == "$" and seg[i + 1:i + 2] == "'":
            q, started = "'", True
            i += 2
            continue
        if c in "'\"":
            q, started = c, True
            i += 1
            continue
        if c in "<>" or (c == "&" and seg[i + 1:i + 2] == ">"):
            fd = "".join(cur) if started and "".join(cur).isdigit() else ""
            if fd:
                cur, started = [], False
            else:
                flush()
            m = _REDIR_OP.match(seg, i)
            if m is not None:
                toks.append((fd + m.group(0), True))
                i = m.end()
                continue
        cur.append(c)
        started = True
        i += 1
    if q is not None:
        return [(w, False) for w in seg.split()]
    flush()
    return toks


def _expand(t: str, env: dict) -> str:
    return _VAR.sub(lambda v: env.get(v.group(1) or v.group(2), v.group(0)), t)


def _strip_wrappers(words: list[str]) -> list[str]:
    """The words of a command without its wrappers (:data:`_WRAPPER_SPECS`), with their options, the options' values and
    their positional words: ``nice -n 10 curl`` is ``curl``. ``command -v``/``-V`` is a lookup and is kept; ``env -S`` and
    ``flock -c`` give their value as the command."""
    import os

    for _ in range(16):
        if not words or os.path.basename(words[0]) not in _WRAPPER_SPECS:
            return words
        w = os.path.basename(words[0])
        short, long_, npos = _WRAPPER_SPECS[w]
        rest = words[1:]
        if w == "command" and rest[:1] in (["-v"], ["-V"]):
            return words  # a lookup of the command's name, not a call
        i, command, how = 0, None, ""
        while i < len(rest) and command is None:
            t = rest[i]
            if t == "--":
                i += 1
                break
            if w in ("env", "sudo", "doas") and _ASSIGNED.match(t):
                i += 1  # VAR=VALUE, for the command
                continue
            if not t.startswith("-") or t == "-":
                break
            if t.startswith("--"):
                name, eq, val = t.partition("=")
                takes = name in long_
                value = val if eq else (rest[i + 1] if takes and i + 1 < len(rest) else "")
                i += 1 if eq or not takes else 2
                if (w, name) in _COMMAND_OPTIONS:
                    command, how = value, _COMMAND_OPTIONS[(w, name)]
                continue
            step = 1
            for j in range(1, len(t)):
                if t[j] in short:
                    value = t[j + 1:] or (rest[i + 1] if i + 1 < len(rest) else "")
                    step = 1 if t[j + 1:] else 2
                    if (w, "-" + t[j]) in _COMMAND_OPTIONS:
                        command, how = value, _COMMAND_OPTIONS[(w, "-" + t[j])]
                    break
            i += step
        rest = rest[i:]
        if command is not None:
            if how == "shell":
                return ["sh", "-c", command]
            words = [w, *(x for x, _ in _tokens(command)), *rest]  # env -S: the words of the string, then the rest
            continue
        if w == "flock" and len(rest) > 1 and rest[1] in ("-c", "--command"):
            return ["sh", "-c", rest[2] if len(rest) > 2 else ""]  # flock FILE -c COMMAND
        words = rest[npos:]
    return words


def _natural_words(seg: str, env: dict) -> tuple[list[str], list[tuple[str, str]]]:
    """``(words, redirections)`` of one segment: the words without leading keywords, declarations, assignments (recorded
    in ``env``), function heads and wrappers (:func:`_strip_wrappers`; ``time`` is one), with the variables that the
    command assigned before substituted; and the redirections apart, as ``(operator, target)`` without the file
    descriptor: ``2>&1`` is ``(">&", "1")``, a heredoc ``("<<", delimiter)``, a here-string ``("<<<", text)``."""
    toks = _tokens(seg.strip().lstrip("({").rstrip(")}").strip())
    words: list[str] = []
    redirs: list[tuple[str, str]] = []
    i = 0
    while i < len(toks):
        t, is_op = toks[i]
        if is_op:
            has = i + 1 < len(toks) and not toks[i + 1][1]
            redirs.append((t.lstrip("0123456789"), _expand(toks[i + 1][0], env) if has else ""))
            i += 2 if has else 1
            continue
        words.append(t)
        i += 1
    for _ in range(2):  # again after a function head: f() { cmd
        while words and words[0] in _KEYWORDS and words[0] != "time":
            words = words[1:]
        if words[:1] == ["function"] or (len(words) > 1 and words[0].endswith("()") and words[1] == "{"):
            words = words[2:]
        elif len(words) > 2 and words[1] == "()" and words[2] == "{":
            words = words[3:]
    if words and words[0] in ("export", "declare", "local", "readonly", "typeset"):
        words = [w for w in words[1:] if not w.startswith("-")]
    while words and _ASSIGN.match(words[0]):
        m = _ASSIGN.match(words[0])
        assert m is not None
        env[m.group(1)] = _expand(m.group(2), env)
        words = words[1:]
    return [_expand(w, env) for w in _strip_wrappers(words)], redirs


@dataclass(frozen=True)
class _ShellSeg:
    """One segment of a shell command as the natural profile reads it (:func:`_natural_shell`)."""

    text: str
    op: str
    bodies: tuple[str, ...]
    sub: bool
    words: tuple[str, ...]
    redirs: tuple[tuple[str, str], ...]
    dirs: tuple[str, ...]  # the directory it runs in, from each start


def _cd(words: list[str], cwd: str, pushed: list[str], norm) -> str:
    """The directory after one segment: ``cd DIR`` and ``pushd DIR`` change it (``pushd`` remembers the old one in
    ``pushed``), ``popd`` returns to the last one remembered; a target that holds a variable is not followed."""
    import os

    name = os.path.basename(words[0]) if words else ""
    args = [a for a in words[1:] if not a.startswith("-")]
    if name in ("cd", "pushd") and args and "$" not in args[0]:
        if name == "pushd":
            pushed.append(cwd)
        return norm(args[0], cwd)
    if name == "popd" and pushed:
        return pushed.pop()
    return cwd


def _natural_shell(cmd: str, starts: list[str], norm) -> tuple[list[_ShellSeg], list[str]]:
    """``(segments, ends)`` of a shell command for the natural profile: each segment (:func:`_natural_segments`) with its
    words and redirections (:func:`_natural_words`; variables assigned earlier in the command substituted) and the
    directory it runs in from each of ``starts``, following ``cd``, ``pushd`` and ``popd`` (inside ``( ... )`` until the
    closing parenthesis; a substitution runs where its segment does); and the directory the command ends in from each
    start."""
    segs = _natural_segments(cmd)
    env: dict[str, str] = {}
    parsed = [_natural_words(s.text, env) for s in segs]
    dirs: list[list[str]] = [[] for _ in segs]
    ends: list[str] = []
    for start in starts:
        cwd, stack, pushed, sub_cwd = start, list[str](), list[str](), None
        for k, s in enumerate(segs):
            w = parsed[k][0]
            if s.sub:
                sub_cwd = _cd(w, cwd if sub_cwd is None else sub_cwd, [], norm)
                dirs[k].append(sub_cwd)
                continue
            sub_cwd = None
            if s.text.startswith("("):
                stack.append(cwd)
            cwd = _cd(w, cwd, pushed, norm)
            dirs[k].append(cwd)
            if s.text.endswith(")") and stack:
                cwd = stack.pop()
        ends.append(cwd)
    return [_ShellSeg(s.text, s.op, s.bodies, s.sub, tuple(parsed[k][0]), tuple(parsed[k][1]), tuple(dirs[k]))
            for k, s in enumerate(segs)], ends


def _shell_program(words: list[str]) -> tuple[str | None, str | None, list[str]]:
    """``(command string, script, arguments)`` of a shell call: with ``-c`` (alone or in a cluster such as ``-lc``) the
    first word after the options is the command string; without it the first word is the script; with neither (or with
    ``-s``) the shell reads its commands from its standard input: ``(None, None, ...)``."""
    i, cflag, sflag = 1, False, False
    while i < len(words):
        t = words[i]
        if t == "--":
            i += 1
            break
        if t in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            i += 2
            continue
        if t.startswith(("-", "+")) and len(t) > 1:
            takes = False
            if not t.startswith("--"):
                cflag = cflag or "c" in t[1:]
                sflag = sflag or "s" in t[1:]
                takes = "o" in t[1:] or "O" in t[1:]  # -euo pipefail: the option's name is the next word
            i += 2 if takes else 1
            continue
        break
    rest = words[i:]
    if cflag:
        return (rest[0] if rest else ""), None, rest[1:]
    if sflag or not rest:
        return None, None, rest
    return None, rest[0], rest[1:]


def _interpreter_call(name: str, words: list[str]) -> tuple[list[str], str | None, str | None, bool, list[str]]:
    """``(inline code, module, script, reads its program from standard input, arguments)`` of an interpreter call: Python
    (``-c CODE``, ``-m MODULE``, ``-``, or no program), node (``-e``, ``-p``, ``--eval``, ``--print``), perl (``-e``,
    ``-E``) or ruby (``-e``)."""
    python = bool(_PYTHON.fullmatch(name))
    code_o, value_o, attached_o = ("c", "WX", "") if python else _INTERPRETERS.get(name, ("e", "", ""))
    mod_o = "m" if python else ""
    codes: list[str] = []
    i = 1
    while i < len(words):
        t = words[i]
        if t == "-":
            return codes, None, None, True, words[i + 1:]
        if t == "--":
            i += 1
            break
        if t.startswith("--"):
            opt, eq, val = t.partition("=")
            if not python and opt in ("--eval", "--print"):
                codes.append(val if eq else (words[i + 1] if i + 1 < len(words) else ""))
                i += 1 if eq else 2
                continue
            i += 2 if not eq and opt in ("--check-hash-based-pycs", "--require", "--import", "--input-type") else 1
            continue
        if t.startswith("-") and len(t) > 1:
            step = 1
            for j in range(1, len(t)):
                ch = t[j]
                if j == 1 and ch in attached_o:
                    break  # its value is the rest of the cluster
                if ch in code_o or ch in mod_o or ch in value_o:
                    val = t[j + 1:] or (words[i + 1] if i + 1 < len(words) else "")
                    step = 1 if t[j + 1:] else 2
                    if ch in mod_o:
                        return codes, val, None, False, words[i + step:]
                    if ch in code_o:
                        codes.append(val)
                        if python:  # -c ends Python's options: the rest are its arguments
                            return codes, None, None, False, words[i + step:]
                    break
            i += step
            continue
        break
    rest = words[i:]
    if codes:
        return codes, None, None, False, rest
    if not rest:
        return [], None, None, True, []
    return [], None, rest[0], False, rest[1:]


def _command_options(name: str, args: list[str]) -> tuple[list[str], list[str], str, list[str]]:
    """``(positional words, path values, short options, long options)`` of one call of ``name`` in the path scan: the
    values of the options that take one (:data:`_VALUE_OPTIONS`) are not positional, and those of :data:`_PATH_OPTIONS`
    are paths."""
    base = _OPTION_ALIASES.get(name, name)
    short_v, long_v = _VALUE_OPTIONS.get(base, ("", frozenset()))
    short_p, long_p = _PATH_OPTIONS.get(base, ("", frozenset()))
    two = _TWO_VALUES.get(base, frozenset())
    positional: list[str] = []
    paths: list[str] = []
    short: list[str] = []
    longs: list[str] = []
    i = 0
    while i < len(args):
        t = args[i]
        if t == "--":
            positional += args[i + 1:]
            break
        if t.startswith("--"):
            opt, eq, val = t.partition("=")
            longs.append(opt)
            if opt in two:
                if opt in ("--slurpfile", "--rawfile") and i + 2 < len(args):
                    paths.append(args[i + 2])
                i += 3
                continue
            if not eq and opt in long_v:
                val = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            if (eq or opt in long_v) and opt in long_p:
                paths.append(val)
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            for j in range(1, len(t)):
                short.append(t[j])
                if t[j] in short_v:
                    val = t[j + 1:]
                    if not val:
                        val = args[i + 1] if i + 1 < len(args) else ""
                        i += 1
                    if t[j] in short_p:
                        paths.append(val)
                    break
            i += 1
            continue
        positional.append(t)
        i += 1
    return positional, paths, "".join(short), longs


def _path_arguments(name: str, positional: list[str], short: str, longs: list[str]) -> list[str]:
    """The positional words of a path-scan command that are paths: not a grep or rg pattern, a sed, awk or jq script, an
    awk assignment or tr's character sets."""
    base = _OPTION_ALIASES.get(name, name)
    if base in ("grep", "rg"):
        given = "e" in short or "f" in short or any(o in longs for o in ("--regexp", "--file", "--files", "--type-list"))
        return positional if given else positional[1:]
    if base in ("sed", "jq"):
        given = "e" in short or "f" in short or any(o in longs for o in ("--expression", "--file", "--from-file"))
        return positional if given else positional[1:]
    if base == "awk":
        rest = positional if ("f" in short or "--file" in longs) else positional[1:]
        return [t for t in rest if not _ASSIGNED.match(t)]
    if base == "tr":
        return []
    return positional


def _natural_scan(cmd: str, start: str, norm, depth: int = 0) -> tuple[list, list, str]:
    """:func:`_scan_command` for the natural profile, on its shell model (:func:`_natural_shell`): ``(checks, unresolved,
    end_cwd)`` of one shell command started in ``start``.

    As :func:`_scan_command`, with these refinements: the options' values (:data:`_VALUE_OPTIONS`), a grep or rg pattern,
    a sed, awk or jq script, inline code (``python3 -c``, ``-m`` modules), tr's sets and bare numbers or ranges are not
    paths, and option values that are paths (``grep -f FILE``) are; a shell's ``-c`` string is scanned as a command where
    the shell runs; redirection targets (``< FILE``, ``> FILE``) are accesses; a command run by its path (a script, a
    wrapper, an interpreter) is one; every git command reads its repository (``git log`` and ``git commit`` included,
    not ``clone`` or ``init``); and ``ls``, ``tree`` and ``du`` without a path list the directory they run in."""
    import os

    segs, ends = _natural_shell(cmd, [start], norm)
    checks: list = []
    unresolved: list = []
    at: list[str] = ["", ""]  # the directory and text of the segment being scanned

    def add(tok: str, recursive: bool, pruned: tuple[str, ...] = ()) -> None:
        cwd, text = at
        if "$" in tok:
            if recursive:  # with the directory of the literal part before the variable
                head = tok.split("$", 1)[0]
                unresolved.append((tok, text[:300], norm(os.path.dirname(head) or ".", cwd)))
            return
        checks.append((norm(tok, cwd), recursive, text[:300], pruned))

    for sg in segs:
        cwd, text = sg.dirs[0], sg.text
        at[:] = [cwd, text]
        for op, target in sg.redirs:
            if op in _FILE_REDIRS and target and target != "-" and not (op in (">&", "<&") and target.isdigit()):
                add(target, False)
        w = list(sg.words)
        if not w:
            continue
        name = os.path.basename(w[0])
        if name in ("cd", "pushd"):
            args = [a for a in w[1:] if not a.startswith("-")]
            if args and "$" not in args[0]:
                checks.append((cwd, False, text[:300], ()))  # the directory it changes to
            continue
        if name == "tracecontract":
            continue  # the study's CLI: the CLI allowlist judges it
        if "/" in w[0]:
            add(w[0], False)  # a command run by its path
        if name == "for":
            for t in w[3:] if len(w) > 3 and w[2] == "in" else []:
                add(t, False)
            continue
        if name in _SHELLS:
            code, script, rest = _shell_program(w)
            if code is not None and depth < 3:
                c, u, _ = _natural_scan(code, cwd, norm, depth + 1)
                checks += c
                unresolved += u
            for t in ([script] if script else []) + [a for a in rest if "/" in a]:
                add(t, False)
            continue
        if name == "eval":
            if depth < 3:
                c, u, _ = _natural_scan(" ".join(w[1:]), cwd, norm, depth + 1)
                checks += c
                unresolved += u
            continue
        if name in ("source", "."):
            for t in [a for a in w[1:] if not a.startswith("-")][:1]:
                add(t, False)
            continue
        if _PYTHON.fullmatch(name) or name in _INTERPRETERS:
            _, _, script, _, rest = _interpreter_call(name, w)
            for t in ([script] if script else []) + [a for a in rest if "/" in a]:
                add(t, False)
            continue
        if name not in _PATH_CMDS:
            continue
        if name == "find":
            roots = []
            for t in w[1:]:
                if t.startswith(("-", "(", "!", ")", ",")):
                    break
                roots.append(t)
            pruned = tuple(norm(w[i + 1], cwd) for i, t in enumerate(w[:-1]) if t == "-path" and i + 2 < len(w)
                           and "-prune" in w[i + 2:i + 4])
            for r in roots or ["."]:
                add(r, True, pruned)
            continue
        if name == "git":
            rest, gcwd = w[1:], cwd
            while rest and rest[0].startswith("-"):
                opt, eq, val = rest[0].partition("=")
                if opt in ("-C", "--git-dir", "--work-tree") and (eq or len(rest) > 1):
                    gcwd = norm(val if eq else rest[1], gcwd)
                    rest = rest[1:] if eq else rest[2:]
                elif opt in ("-c", "--namespace", "--super-prefix", "--config-env", "--exec-path") and not eq and len(rest) > 1:
                    rest = rest[2:]
                else:
                    rest = rest[1:]
            if not rest:
                continue
            sub, rest = rest[0], rest[1:]
            if sub in _GIT_LISTING:
                specs = list(rest[rest.index("--") + 1:]) if "--" in rest else [
                    t for t in rest if not t.startswith("-") and ("/" in t or "." in t)]
                specs = [t.split(":", 1)[1] if ":" in t and sub == "show" else t for t in specs]
                if sub == "log" and not any(o in rest for o in ("-p", "--patch", "--stat", "--name-only", "--name-status")):
                    checks.append((gcwd, False, text[:300], ()))  # the repository's history
                    continue
                for t in specs or ["."]:
                    checks.append((norm(t or ".", gcwd), True, text[:300], ()))
            elif sub not in ("clone", "init", "help", "version", "--version"):
                checks.append((gcwd, False, text[:300], ()))  # any other git command works on the repository
            continue
        positional, path_values, short, longs = _command_options(name, w[1:])
        recursive = (name in ("tree", "du", "rg", "rsync", "tar", "zip")
                     or (name in _SEARCHERS and ("r" in short or "R" in short or "--recursive" in longs
                                                 or "--dereference-recursive" in longs))
                     or (name == "ls" and ("R" in short or "--recursive" in longs))
                     or (name == "cp" and ("r" in short or "R" in short or "a" in short or "--recursive" in longs
                                           or "--archive" in longs))
                     or (name == "diff" and ("r" in short or "--recursive" in longs)))
        paths = [t for t in _path_arguments(name, positional, short, longs) if not _NOT_A_PATH.fullmatch(t)]
        if not paths and (name in ("ls", "tree", "du") or (name in _SEARCHERS and recursive)):
            paths = ["."]  # the directory it runs in
        for t in paths:
            add(t, recursive)
        for t in path_values:
            if t and not _NOT_A_PATH.fullmatch(t):
                add(t, False)
    return checks, unresolved, ends[0]


def _sed_safe(script: str) -> bool:
    """Whether a sed script holds only commands that read, write and run no file: substitutions and transliterations
    (without the ``w`` or ``e`` flag), line commands (``p``, ``d``, ``q``, ``=``, ...), labels and branches, with their
    addresses; not ``r``, ``R``, ``w``, ``W``, ``e`` or text commands."""
    i, n = 0, len(script)
    while i < n:
        c = script[i]
        if c in " \t\n;{}!0123456789$,~+":
            i += 1
            continue
        if c == "/" or (c == "\\" and i + 1 < n):  # a regular-expression address: /re/ or \cREc
            d, j = ("/", i + 1) if c == "/" else (script[i + 1], i + 2)
            while j < n and script[j] != d:
                j += 2 if script[j] == "\\" else 1
            i = j + 1
            while i < n and script[i] in "IM":
                i += 1
            continue
        if c in "sy":
            d = script[i + 1:i + 2]
            if not d or d.isalnum() or d in "\\\n ":
                return False
            j, parts = i + 2, 0
            while j < n and parts < 2:
                if script[j] == "\\":
                    j += 2
                    continue
                parts += script[j] == d
                j += 1
            while j < n and script[j] in "gIipmM0123456789":
                j += 1
            if j < n and script[j] in "we":
                return False
            i = j
            continue
        if c in ":btT":  # a label, a branch to one
            j = i + 1
            while j < n and script[j] not in ";\n}":
                j += 1
            i = j
            continue
        if c in "pdDqQ=nNgGhHxlzP":
            i += 1
            continue
        return False
    return True


def _left_to_the_path_scan(words: list[str]) -> bool:
    """Whether the literal scan leaves a segment to the path scan, which reads its files and leaves its pattern or
    script out: a call of grep (egrep, fgrep) or rg, whose pattern is never a path, or of sed whose scripts are
    :func:`_sed_safe`."""
    import os

    name = _OPTION_ALIASES.get(os.path.basename(words[0]), os.path.basename(words[0])) if words else ""
    if name in ("grep", "rg"):
        return True
    if name != "sed":
        return False
    scripts: list[str] = []
    positional: list[str] = []
    i, given = 1, False
    while i < len(words):
        t = words[i]
        if t == "--":
            positional += words[i + 1:]
            break
        if t.startswith("--"):
            opt, eq, val = t.partition("=")
            if opt == "--file":
                return False  # a script file: its commands are not known
            if opt == "--expression":
                given = True
                scripts.append(val if eq else (words[i + 1] if i + 1 < len(words) else ""))
            i += 2 if not eq and opt in ("--expression", "--line-length") else 1
            continue
        if t.startswith("-") and len(t) > 1:  # a cluster of -n, -E, -s, -i[SUFFIX], -e SCRIPT, -f FILE, -l N
            step = 1
            for j in range(1, len(t)):
                if t[j] == "f":
                    return False
                if t[j] == "e":
                    given = True
                    scripts.append(t[j + 1:] or (words[i + 1] if i + 1 < len(words) else ""))
                    step = 1 if t[j + 1:] else 2
                    break
                if t[j] == "l":
                    step = 1 if t[j + 1:] else 2
                    break
                if t[j] == "i":
                    break  # the rest of the cluster is the backup suffix
            i += step
            continue
        positional.append(t)
        i += 1
    if not given:
        scripts = positional[:1]
    return all(_sed_safe(x) for x in scripts)


def _literal_tokens(text: str, base: str, start: str, norm) -> list[tuple[str, str]]:
    """``(resolved path, context)`` of each path-like token of ``text``: an absolute one as it is, a relative one from
    ``base``; ``VAR=/path`` names the path after the ``=``."""
    out = []
    for m in _LITERAL_PATH.finditer(text):
        tok = m.group(0).rstrip(".,:;")
        if _ASSIGNED.match(tok):
            tok = tok.split("=", 1)[1]
        if tok:
            out.append((norm(tok, start if tok.startswith(("/", "~")) else base), text[max(0, m.start() - 80): m.end() + 80]))
    return out


def _command_literals(cmd: str, start: str, norm, sandbox: str | None, skip, depth: int = 0) -> list[tuple[str, str]]:
    """The literal paths of a shell command (:func:`_literal_tokens`) for the natural profile: each segment's text and
    heredoc bodies (a substitution's too), resolved from the directory the segment runs in when the call starts in
    ``start``, from ``sandbox`` (the repository the wrappers mount at ``/repo``) for a call of the sandbox wrappers; a
    shell's ``-c`` string and ``eval``'s are followed as commands. Segments that ``skip`` names are left out, and so are
    those the path scan reads fully (:func:`_left_to_the_path_scan`)."""
    import os

    out: list[tuple[str, str]] = []
    segs, _ = _natural_shell(cmd, [start], norm)
    for sg in segs:
        w = list(sg.words)
        if skip(sg.text) or _left_to_the_path_scan(w):
            continue
        name = os.path.basename(w[0]) if w else ""
        base = sandbox if sandbox and name in _SANDBOX_WRAPPERS else sg.dirs[0]
        inner = _shell_program(w)[0] if name in _SHELLS else (" ".join(w[1:]) if name == "eval" else None)
        if inner is not None and depth < 3:
            out += _command_literals(inner, sg.dirs[0], norm, sandbox, skip, depth + 1)
            texts = [" ".join(x for x in w if x != inner), *sg.bodies]
        else:
            texts = [sg.text, *sg.bodies]
        for text in texts:
            out += _literal_tokens(_EXCLUSION_ARG.sub(" ", text), base, start, norm)
    return out


def _natural_literals(tool: str, ti: dict, cmd: str, start: str, norm, sandbox: str | None, skip) -> list[tuple[str, str]]:
    """The literal paths of one tool input for the natural profile: the path fields (a relative path in a Grep or Glob
    pattern from the tool's path, any other from ``start``, where the harness resolves it) and the shell command
    (:func:`_command_literals`)."""
    out: list[tuple[str, str]] = []
    for k in ("file_path", "path", "pattern", "notebook_path", "glob"):
        if ti.get(k):
            base = norm(str(ti.get("path") or "."), start) if tool in ("Grep", "Glob") and k in ("pattern", "glob") else start
            out += _literal_tokens(str(ti[k]), base, start, norm)
    return out + (_command_literals(cmd, start, norm, sandbox, skip) if cmd else [])


def _is_cli_call(words: list[str]) -> bool:
    """Whether a segment's words run the study's CLI (``tracecontract ...`` or ``python -m tracecontract ...``)."""
    import os

    if not words:
        return False
    if os.path.basename(words[0]) == "tracecontract":
        return True
    if _PYTHON.fullmatch(os.path.basename(words[0])):
        for i, w in enumerate(words[1:-1], 1):
            if w == "-m":
                return words[i + 1].split(".")[0] == "tracecontract"
    return False


def _cli_allowed(words: list[str], redirs: tuple[tuple[str, str], ...], dirs: list[str], profile: _AuditProfile,
                 norm) -> bool:
    """Whether one CLI call is on the natural profile's allowlist (see :func:`audit_natural_agent_transcript`)."""
    import os

    ws = profile.workspace
    if ws is None or os.path.normpath(words[0]) != profile.cli_binary or len(words) < 3 or words[1] not in profile.cli:
        return False

    def inside_ws(t: str) -> bool:
        return "$" not in t and all(norm(t, d) == ws or norm(t, d).startswith(ws + "/") for d in dirs)

    for op, target in redirs:
        if op in ("<<", "<<-", "<<<") or target in ("/dev/null", "-") or (op in (">&", "<&") and target.isdigit()):
            continue
        if not inside_ws(target):
            return False
    rest, i, n_paths = words[2:], 0, 0
    while i < len(rest):
        t = rest[i]
        if words[1] == "check-proposals" and t == "--variant" and i + 1 < len(rest) and rest[i + 1] in _VARIANTS:
            i += 2
            continue
        if words[1] == "check-proposals" and t.startswith("--variant=") and t.split("=", 1)[1] in _VARIANTS:
            i += 1
            continue
        if t.startswith("-") or not inside_ws(t):
            return False
        n_paths += 1
        i += 1
    return n_paths > 0


# --------------------------------------------------------------------------------------------- the natural network rule


def _written_texts(t: str, dirs: list[str], written: dict[str, str], norm) -> list[str]:
    """The text the agent wrote to the file ``t`` (resolved from each directory in ``dirs``), if any."""
    return [written[p] for p in dict.fromkeys(norm(t, d) for d in dirs) if p in written]


def _echo_text(words: list[str]) -> str:
    """What ``echo`` or ``printf`` prints, roughly: its arguments, with ``\\n`` as a newline."""
    args = words[1:]
    while args and words[0].endswith("echo") and re.fullmatch(r"-[neE]+", args[0]):
        args = args[1:]
    return " ".join(args).replace("\\n", "\n")


def _emitted(sg: _ShellSeg, written: dict[str, str], norm) -> list[str]:
    """What a pipeline segment writes to the next one, where the audit can know it: the files that cat (head, tail, ...)
    shows that the agent wrote, its heredoc bodies and here-strings, and the text of echo or printf."""
    import os

    w = list(sg.words)
    name = os.path.basename(w[0]) if w else ""
    if name in ("echo", "printf"):
        return [_echo_text(w)]
    if name not in ("cat", "head", "tail", "tac", "more", "less", ""):
        return []
    texts = [t for a in w[1:] if not a.startswith("-") for t in _written_texts(a, list(sg.dirs), written, norm)]
    texts += [t for op, tgt in sg.redirs if op == "<" for t in _written_texts(tgt, list(sg.dirs), written, norm)]
    return texts + list(sg.bodies) + [t for op, t in sg.redirs if op == "<<<"]


def _note_writes(tool: str, ti: dict, cmd: str, starts: list[str], written: dict[str, str], norm) -> None:
    """Record the text of the files a tool call writes, by resolved path, so that a script the agent runs later can be
    read: the file tools, and in a shell command (each segment from the directories it runs in) heredocs and here-strings
    written by ``cat`` or ``tee`` or a bare redirection, ``echo``/``printf`` redirected, ``cat`` of files the agent wrote,
    what a pipe gives ``tee``, and copies (``cp``, ``mv``) of files the agent wrote."""
    import os

    fp = ti.get("file_path") or ti.get("notebook_path")
    if tool == "Write" and isinstance(fp, str):
        written[norm(fp, starts[0])] = str(ti.get("content", ""))
    elif tool in ("Edit", "MultiEdit", "NotebookEdit") and isinstance(fp, str):
        new = [str(ti.get("new_string", "")), str(ti.get("new_source", ""))]
        new += [str(e.get("new_string", "")) for e in ti.get("edits") or [] if isinstance(e, dict)]
        p = norm(fp, starts[0])
        written[p] = written.get(p, "") + "\n" + "\n".join(new)
    if not cmd:
        return
    segs, _ = _natural_shell(cmd, starts, norm)
    prev: dict[bool, _ShellSeg] = {}
    for sg in segs:
        w = list(sg.words)
        name = os.path.basename(w[0]) if w else ""
        before = prev.get(sg.sub)
        prev[sg.sub] = sg
        outs = [(op, t) for op, t in sg.redirs if op in (">", ">>", "&>", "&>>", ">|") and t and "$" not in t]
        if name == "tee":
            append = "-a" in w or "--append" in w
            outs += [(">>" if append else ">", a) for a in w[1:] if not a.startswith("-") and "$" not in a]
        text: str | None = None
        if name in ("cat", "tee", ""):
            parts = [*sg.bodies, *(t for op, t in sg.redirs if op == "<<<")]
            if name == "cat":
                parts += [t for a in w[1:] if not a.startswith("-") for t in _written_texts(a, list(sg.dirs), written, norm)]
            if sg.op == "|" and before is not None:
                parts += _emitted(before, written, norm)
            text = "\n".join(parts)
        elif name in ("echo", "printf"):
            text = _echo_text(w)
        if text is not None:
            for op, target in outs:
                for d in dict.fromkeys(sg.dirs):
                    p = norm(target, d)
                    written[p] = written.get(p, "") + "\n" + text if op in (">>", "&>>") else text
        args = [a for a in w[1:] if not a.startswith("-")]
        if name in ("cp", "mv") and len(args) >= 2:
            for d in dict.fromkeys(sg.dirs):
                for src in args[:-1]:
                    found = _written_texts(src, [d], written, norm)
                    if found:
                        dst = norm(args[-1], d)
                        written[dst] = written[os.path.join(dst, os.path.basename(src))] = found[0]


def _imports(code: str) -> list[str]:
    """The modules that Python ``code`` imports: statically (``from X import Y`` gives ``X`` and ``X.Y``), or by
    ``__import__``/``import_module`` with a literal name."""
    mods: list[str] = []
    for m in _FROM_IMPORT.finditer(code):
        names = [n.split()[0] for n in m.group(2).split(",") if n.split()]
        mods += [m.group(1), *(f"{m.group(1)}.{n}" for n in names if n != "*")]
    for m in _PLAIN_IMPORT.finditer(code):
        mods += [n.split()[0] for n in m.group(1).split(",") if n.split()]
    mods += _DYNAMIC_IMPORT.findall(code)
    return list(dict.fromkeys(mods))


def _net_module(name: str) -> bool:
    return name == "urllib" or any(name == n or name.startswith(n + ".") for n in _NET_MODULES)


def _net_imports(code: str) -> list[str]:
    """The modules that ``code`` imports (:func:`_imports`) that reach the network (:data:`_NET_MODULES`); ``from urllib
    import parse`` does not count, ``import urllib`` does."""
    plain = {n.split()[0] for m in _PLAIN_IMPORT.finditer(code) for n in m.group(1).split(",") if n.split()}
    return [x for x in _imports(code) if _net_module(x) and (x != "urllib" or x in plain)]


def _python_net(codes: list[str], dirs: list[str], written: dict[str, str], norm, depth: int = 0) -> list[str]:
    """The network modules that host Python ``codes`` import (:func:`_net_imports`), following what the agent wrote that
    the code imports (a module beside it, ``import helper`` of a written ``helper.py``) or names (``exec(open(...))``)."""
    found: list[str] = []
    for code in codes:
        found += _net_imports(code)
        if depth >= 3:
            continue
        more: list[str] = []
        for mod in _imports(code):
            rel = mod.replace(".", "/")
            more += [t for p in (f"{rel}.py", f"{rel}/__init__.py") for t in _written_texts(p, dirs, written, norm)]
        for m in _LITERAL_PATH.finditer(code):
            more += _written_texts(m.group(0).rstrip(".,:;"), dirs, written, norm)
        for m in re.finditer(r"['\"]([\w.-]+\.py)['\"]", code):
            more += _written_texts(m.group(1), dirs, written, norm)
        found += _python_net([t for t in dict.fromkeys(more) if t not in codes], dirs, written, norm, depth + 1)
    return list(dict.fromkeys(found))


def _pip_args(words: list[str]) -> list[str] | None:
    """The arguments of a pip call (``pip ...``, ``python -m pip ...``, ``uv pip ...``), or None for another command."""
    import os

    name = os.path.basename(words[0])
    if _PIP.fullmatch(name):
        return words[1:]
    if name == "uv" and words[1:2] == ["pip"]:
        return words[2:]
    if _PYTHON.fullmatch(name):
        for i, w in enumerate(words[1:-1], 1):
            if w == "-m":
                return words[i + 2:] if words[i + 1] == "pip" else None
            if not w.startswith("-"):
                return None
    return None


def _downloader_use(name: str, words: list[str]) -> str | None:
    """``"<manager> <subcommand>"`` when a package manager or version-control client (:data:`_DOWNLOADERS`) is called with
    a subcommand that reaches the network, without ``--offline``; the subcommand is the first word after the options,
    or the next one when an option may have taken it as its value."""
    subs = _DOWNLOADERS.get(name)
    if subs is None or any(w in ("--offline", "--version", "-V", "--help", "-h") for w in words[1:]):
        return None
    cands: list[str] = []
    after_option = False
    for t in words[1:]:
        if t.startswith("-"):
            after_option = "=" not in t
            continue
        cands.append(t)
        if not after_option or len(cands) == 2:
            break
        after_option = False
    sub = next((c for c in cands if c in subs), None)
    if sub is None and name == "yarn" and not cands:
        sub = "install"  # yarn alone installs
    return f"{name} {sub}" if sub else None


def _find_exec(words: list[str]) -> list[list[str]]:
    """The commands that ``find -exec`` (``-execdir``, ``-ok``, ``-okdir``) runs."""
    groups, i = [], 0
    while i < len(words):
        if words[i] in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            while j < len(words) and words[j] not in (";", "+"):
                j += 1
            groups.append(_strip_wrappers(words[i + 1:j]))
            i = j + 1
        else:
            i += 1
    return [g for g in groups if g]


def _network_uses(tool: str, ti: dict, cmd: str, dirs: list[str], written: dict[str, str], norm,
                  depth: int = 0) -> list[tuple[str, str, str]]:
    """The network rule of the natural-agent profile: ``(what, why, text)`` for each network use in one tool call.

    WebFetch, WebSearch and MCP tool calls; and each segment of a shell command (:func:`_natural_shell`, started in each
    of ``dirs``) that uses the network (:func:`_command_network`), with what a pipe gives it. The rule looks at the
    command each segment runs, so code given to the sandbox wrappers (``run_tests.sh``, ``run_python.sh``), which run it
    with ``--network none``, is not counted. ``written`` holds the text of the files the agent wrote (:func:`_note_writes`).
    """
    out: list[tuple[str, str, str]] = []
    if depth == 0:
        if tool in _NET_TOOLS:
            out.append((str(ti.get("url") or ti.get("query") or tool), "network: " + _NET_TOOLS[tool], json.dumps(ti)[:300]))
        elif tool.startswith("mcp__"):
            out.append((tool, "network: an MCP tool call (an external service)", json.dumps(ti)[:300]))
    if not cmd:
        return out
    segs, _ = _natural_shell(cmd, dirs, norm)
    prev: dict[bool, _ShellSeg] = {}
    for sg in segs:
        before = prev.get(sg.sub)
        piped = _emitted(before, written, norm) if sg.op == "|" and before is not None else []
        prev[sg.sub] = sg
        out += _command_network(list(sg.words), sg.redirs, sg.bodies, piped, list(sg.dirs), sg.text[:300], written, norm,
                                depth)
    return out


def _command_network(words: list[str], redirs: tuple[tuple[str, str], ...], bodies: tuple[str, ...], piped: list[str],
                     dirs: list[str], text: str, written: dict[str, str], norm, depth: int) -> list[tuple[str, str, str]]:
    """The network uses of one command (its words, redirections, heredoc bodies, what a pipe gives it, the directories it
    runs in): see :func:`audit_natural_agent_transcript`."""
    import os

    if not words:
        return []
    name = os.path.basename(words[0])

    def use(what: str, why: str) -> list[tuple[str, str, str]]:
        return [(what, "network: " + why, text)]

    def stdin() -> list[str]:  # what the command reads on its standard input
        out = list(bodies)
        for op, target in redirs:
            if op == "<<<":
                out.append(target)
            elif op in ("<", "<>"):
                out += _written_texts(target, dirs, written, norm)
        return out + piped

    def shell_texts(texts: list[str]) -> list[tuple[str, str, str]]:
        return [u for t in texts for u in _network_uses("", {}, t, dirs, written, norm, depth + 1)] if depth < 3 else []

    def py_uses(codes: list[str], extra: list[str]) -> list[tuple[str, str, str]]:
        return [u for mod in _python_net(codes, [*dirs, *extra], written, norm)
                for u in use(mod, f"host Python code that imports {mod}")]

    def other(kind: str, codes: list[str]) -> list[tuple[str, str, str]]:
        hit = any(_SCRIPT_NET[kind].search(c) for c in [*codes, " ".join(words)])
        return use(name, f"host {kind} code that uses the network") if hit else []

    if name in _NET_COMMANDS:
        return use(name, name)
    if name in _CONTAINER_ENGINES:
        what = " ".join([name, *[w for w in words[1:] if not w.startswith("-")][:1]])
        return use(what, f"{what} (a container engine called directly: only the sandbox wrappers start containers "
                         "with --network none)")
    if name == "rsync" and any(_REMOTE.match(w) for w in words[1:] if not w.startswith("-")):
        return use("rsync", "rsync to or from a remote host")
    if name == "openssl" and words[1:2] in (["s_client"], ["s_time"]):
        return use(f"openssl {words[1]}", f"openssl {words[1]}")
    if name == "git":
        rest = words[1:]
        while rest and rest[0].startswith("-"):
            rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
        if rest and rest[0] in _NET_GIT:
            return use(f"git {rest[0]}", f"git {rest[0]}")
        if rest and rest[0] in _NET_GIT_SUB and rest[1:2] and rest[1] in _NET_GIT_SUB[rest[0]]:
            return use(f"git {rest[0]} {rest[1]}", f"git {rest[0]} {rest[1]}")
        if rest[:1] == ["archive"] and any(w.startswith("--remote") for w in rest):
            return use("git archive --remote", "git archive --remote")
        return []
    pip = _pip_args(words)
    if pip is not None:
        sub = next((w for w in pip if w in _PIP_COMMANDS), "")  # after any global option and its value
        if sub in _NET_PIP:
            return use(f"pip {sub}", f"pip {sub}")
        if sub in ("install", "wheel") and "--no-index" not in pip and "--offline" not in pip:  # uv pip: --offline
            return use(f"pip {sub}", f"pip {sub} without --no-index")
        return []
    dl = _downloader_use(name, words)
    if dl is not None:
        return use(dl, dl)
    if name in _SHELLS:
        code, script, _ = _shell_program(words)
        if code is not None:
            return shell_texts([code])
        return shell_texts(_written_texts(script, dirs, written, norm) if script else stdin())
    if name in ("source", "."):
        script = next((w for w in words[1:] if not w.startswith("-")), None)
        return shell_texts(_written_texts(script, dirs, written, norm) if script else [])
    if name == "eval":
        return shell_texts([" ".join(words[1:])])
    if name == "find" and depth < 3:
        return [u for g in _find_exec(words) for u in _command_network(g, (), (), [], dirs, text, written, norm, depth + 1)]
    if _PYTHON.fullmatch(name):
        codes, module, script, from_stdin, _ = _interpreter_call(name, words)
        found = use(module, f"python -m {module}") if module is not None and (_net_module(module) or module == "http") else []
        extra: list[str] = []
        if script:
            codes = codes + _written_texts(script, dirs, written, norm)
            extra = [os.path.dirname(norm(script, d)) for d in dirs]
        if from_stdin:
            codes = codes + stdin()
        return found + py_uses(codes, extra)
    if name in _INTERPRETERS:
        codes, _, script, from_stdin, _ = _interpreter_call(name, words)
        if script:
            codes = codes + _written_texts(script, dirs, written, norm)
        if from_stdin:
            codes = codes + stdin()
        return other("node" if name == "nodejs" else name, codes)
    if "/" in words[0] and depth < 3:  # a script the agent wrote, run by its path: by its shebang
        runs: list[tuple[str, str, str]] = []
        for body in _written_texts(words[0], dirs, written, norm):
            first = body.lstrip().split("\n", 1)[0] if body.lstrip().startswith("#!") else ""
            kind = next((k for k in ("python", "node", "perl", "ruby") if k in first), "")
            if kind == "python":
                runs += py_uses([body], [os.path.dirname(norm(words[0], d)) for d in dirs])
            elif kind:
                runs += other(kind, [body])
            else:
                runs += shell_texts([body])
        return runs
    return []


def _strict_audit(path: Path, profile: _AuditProfile, *, task: str, repo_root: str, home: str,
                  outputs: bool) -> tuple[list[dict], list[dict]]:
    """The strict audit of one transcript under ``profile``: (hits in tool inputs, exposures in tool outputs)."""
    import os

    from .ingest.claude_code import parse_claude_code_jsonl
    from .schemas import Population

    forbidden, allowed = list(profile.forbidden), list(profile.allowed)

    def norm(p: str, cwd: str) -> str:
        if p.startswith("~"):
            p = home + p[1:]
        return os.path.normpath(p if p.startswith("/") else os.path.join(cwd, p))

    def inside(p: str, root: str) -> bool:
        return p == root or p.startswith(root.rstrip("/") + "/")

    def classify(p: str, recursive: bool, pruned: tuple[str, ...] = (), host: bool = False) -> str | None:
        for marker, why in profile.markers:
            if marker in p:
                return why
        if any(inside(p, a) for a in allowed):
            return None
        for root in forbidden:
            if inside(p, root):
                return "inside forbidden material"
            if recursive and inside(root, p) and not any(inside(root, x) for x in pruned) \
                    and not any(inside(a, p) and inside(root, a) for a in allowed):
                return "recursive search over forbidden material"
        if host and profile.outside and not any(inside(p, s) for s in _FRESH_SYSTEM):
            return profile.outside_why or FRESH_OUTSIDE
        return None

    s = parse_claude_code_jsonl(path, population=Population.controlled, source="audit", include_sidechains=True)
    hits: list[dict] = []
    carried = repo_root
    calls: dict = {}  # tool_call_id -> (tool, call event id, directories a shell command may end in)
    own_ids: set = set()  # patterns of the candidate ids the agent registered itself
    written: dict[str, str] = {}  # the network rule: the text of the files the agent wrote, by path
    scrubbed: dict[str, tuple[str, str]] = {}  # the natural profile: event id -> (command, without its allowlisted calls)
    named_only: dict = {}  # the natural profile: tool_call_id -> the directories of a command that named workspace paths only
    natural = profile.refine_words  # the natural profile reads shell commands with its own model (_natural_shell)
    for ev in s.events:
        if ev.kind != EventKind.tool_call:
            continue
        ti = ev.tool_input or {}
        first_hit = len(hits)
        checks: list[tuple[str, bool, str, tuple[str, ...]]] = []
        for k in ("file_path", "notebook_path"):
            if ti.get(k):
                checks.append((norm(str(ti[k]), repo_root), False, str(ti[k]), ()))
        if ev.tool_name in ("Grep", "Glob"):
            checks.append((norm(str(ti.get("path") or "."), repo_root), True, json.dumps(ti)[:300], ()))
        cmd: str = ti["command"] if isinstance(ti.get("command"), str) else ""
        if cmd:
            # Every Bash call of a subagent starts in the repository root. As a conservative
            # extra, relative paths are also resolved from the directory an earlier call ended
            # in, in case a working directory carried over between calls.
            scan = _natural_scan if natural else _scan_command
            c1, u1, end = scan(cmd, repo_root, norm)
            c2, u2, carried_next = scan(cmd, carried, norm) if carried != repo_root else ([], [], end)
            checks += [c for c in c1 + c2 if not (natural and any(ch in c[0] for ch in _CODE_CHARS))]
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

        # The natural profile's CLI allowlist: each call of the study's CLI, allowlisted or not. An allowlisted call
        # names the CLI in the repository but reads nothing there, so its segment is left out of the literal scan.
        starts = list(dict.fromkeys([repo_root, carried]))  # where the command may start
        shell = _natural_shell(cmd, starts, norm)[0] if cmd and natural else []
        cli_calls = [(sg.text, list(sg.words), _cli_allowed(list(sg.words), sg.redirs, list(sg.dirs), profile, norm))
                     for sg in shell if profile.cli and _is_cli_call(list(sg.words))]
        allowlisted = {seg for seg, _, ok in cli_calls if ok} - {seg for seg, _, ok in cli_calls if not ok}
        if natural:
            # Each segment's paths from the directory it runs in, as the call starts in the repository root
            # (_natural_literals): the carried directory, a conservative extra of the path scan, exempts nothing.
            words_by_seg = [list(sg.words) for sg in shell]
            sandbox = profile.sandbox if any(w and os.path.basename(w[0]) in _SANDBOX_WRAPPERS for w in words_by_seg) else None
            literal = _natural_literals(ev.tool_name or "", ti, cmd, repo_root, norm, profile.sandbox,
                                        lambda t, done=frozenset(allowlisted): registers(t) or t in done)
        else:
            texts = [str(ti[k]) for k in ("file_path", "path", "pattern", "notebook_path", "glob") if ti.get(k)]
            if cmd:  # every segment, heredoc bodies included, except the registration of the agent's own candidate
                body = "\n".join(seg for seg in _split_unquoted(cmd) if not registers(seg))
                # A path given to an exclusion option names what the command avoids (find -path ... -prune).
                texts.append(_EXCLUSION_ARG.sub(" ", body))
            # Directories the command may run in: the start, the carried one and every cd target, and for a call of
            # the sandbox wrappers the repository they mount at /repo (their arguments are paths in the container).
            bases = [repo_root, carried]
            words_by_seg = [_command_words(seg, {}) for seg in _shell_segments(cmd)] if cmd else []
            for w in words_by_seg:
                if w and w[0] == "cd" and len(w) > 1 and "$" not in w[1]:
                    bases.append(norm(w[1], bases[-1]))
            sandbox = profile.sandbox if any(w and os.path.basename(w[0]) in _SANDBOX_WRAPPERS for w in words_by_seg) else None
            if sandbox is not None:
                bases.append(sandbox)
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
        ends = list(dict.fromkeys([end, carried_next])) if cmd else []
        if sandbox is not None:
            ends = [sandbox]  # the output of the sandbox: its relative paths are under /repo, the workspace's repo/
        elif allowlisted and profile.workspace:
            ends = [profile.workspace]  # an allowlisted CLI call reports paths relative to its arguments, in the workspace
        calls[ev.tool_call_id] = (ev.tool_name, ev.event_id, ends)
        if cmd:
            carried = carried_next
        seen = set()
        for p, rec, text, pruned in checks:
            why = classify(p, rec, pruned, host=True)
            if why and (p, why) not in seen:
                seen.add((p, why))
                hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": p, "why": why, "text": text})
        for seg, w, ok in cli_calls:
            if not ok:  # before the literal paths, which then do not repeat the CLI's own path
                hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": norm(w[0], repo_root) if "/" in w[0] else w[0],
                             "why": NATURAL_CLI_WHY, "text": seg[:300]})
        for p, text in literal:
            why = classify(p, False)
            if why and not any(h["event_id"] == ev.event_id and h["path"] == p for h in hits):
                hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": p, "why": "path named in the tool input: " + why,
                             "text": text})
        ws = profile.workspace
        if natural and cmd and ws and sandbox is None and not allowlisted and len(hits) == first_hit:
            # A command that named paths inside the workspace only (and system locations), with no hit, showed the
            # workspace's own material: a relative path in its output (cat <ws>/reference.diff, a link in a README)
            # refers to it, and is an exposure only if it leads into forbidden material from each directory it named.
            named = [c[0] for c in checks] + [p for p, _ in literal]
            if any(inside(p, ws) for p in named) and all(inside(p, ws) or any(inside(p, x) for x in _FRESH_SYSTEM)
                                                         for p in named):
                named_only[ev.tool_call_id] = list(dict.fromkeys(  # the directory holding a named path first
                    d for p in named if inside(p, ws) for d in (os.path.dirname(p), p) if inside(d, ws)))
        # A held-out candidate named in a CLI command other than the registration of the agent's own candidate.
        seg_words = ([(sg.text, list(sg.words)) for sg in shell] if natural
                     else [(seg, _command_words(seg, {})) for seg in (_shell_segments(cmd) if cmd else [])])
        for seg, words in seg_words:
            if words and os.path.basename(words[0]) == "tracecontract" and words[1:2] != ["add-candidate"]:
                for word in words[1:]:
                    if re.fullmatch(rf"{re.escape(task)}-{_HELDOUT}", word):
                        hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": word,
                                     "why": "held-out candidate named in a CLI command", "text": seg[:300]})
            elif words and os.path.basename(words[0]) == "tracecontract":
                # A variable in the registered id (a loop or a shell function) stands for any suffix.
                own_ids.update(r"[\w-]+".join(map(re.escape, _ANY_VAR.split(word))) for word in words[2:]
                               if re.fullmatch(rf"{re.escape(task)}-{_HELDOUT}", _ANY_VAR.sub("0", word)))
        if natural and allowlisted:  # for the first audit's substring rule below
            rest = cmd
            for seg in sorted(allowlisted, key=len, reverse=True):
                rest = rest.replace(seg, " ")
            scrubbed[ev.event_id] = (cmd[:300], rest)
        # The natural profile's network rule and tool set. The files a call writes are noted first, so that a script
        # written and run in one command is read.
        tool = ev.tool_name or ""
        if profile.network:
            _note_writes(tool, ti, cmd or "", starts, written, norm)
            for what, why, text in _network_uses(tool, ti, cmd or "", starts, written, norm):
                hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": what, "why": why, "text": text})
        if profile.tools is not None and tool not in profile.tools and tool not in _NET_TOOLS and not tool.startswith("mcp__"):
            hits.append({"event_id": ev.event_id, "tool": ev.tool_name, "path": tool, "why": NATURAL_TOOLS_WHY,
                         "text": json.dumps(ti)[:300]})
    # The first audit's substring rule, so that this audit flags everything that one does.
    for h in audit_generator_transcript(path, forbidden=profile.v1_forbidden, allowed=profile.v1_allowed):
        if any(x["event_id"] == h["event_id"] for x in hits):
            continue
        if h["event_id"] in scrubbed and h["text"] == scrubbed[h["event_id"]][0]:
            # The natural profile: a match that only the command's allowlisted CLI calls hold, however spaced, is not one.
            rest = scrubbed[h["event_id"]][1]
            for a in profile.v1_allowed:
                rest = rest.replace(a, "")
            if not any(bad in rest for bad in profile.v1_forbidden):
                continue
        hits.append({"event_id": h["event_id"], "tool": h["tool"], "path": h["match"], "why": "substring match (first audit's rule)",
                     "text": h["text"]})
    if not outputs:
        return hits, []
    # What the tool outputs showed the agent, reported apart from its reads.
    heldout = re.compile(rf"(?<![\w-]){re.escape(task)}-{_HELDOUT}")
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
        named_dirs = named_only.get(ev.tool_call_id)
        for m in _LITERAL_PATH.finditer(ev.text):
            tok = m.group(0).rstrip(".,:;")
            if named_dirs is not None and not tok.startswith(("/", "~")):
                resolved = [norm(tok, b) for b in named_dirs]
                if all(classify(r, False) for r in resolved):
                    found.setdefault((resolved[0], "shown in a tool output: " + str(classify(resolved[0], False))), m)
                continue
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
