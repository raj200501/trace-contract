"""Isolated workspace for one generator or fresh agent (protocol v0.7 §15.4, v0.8 §16.2; decision log D44, D46, D47, D50).

Usage: python scripts/make_agent_workspace.py tasks/<id> --role <role> --root <dir> --name <name>
           [--instruction <file> | --variant u1|final] [--image <tag> [--pythonpath <path>] [--pytest-args <args>]
           [--no-smoke]] [--sealed <dir> ...] [--forbid <dir> ...] [--allow-outside-paths]

It creates the new directory ``<root>/<name>``, outside the repository, holding only what
the role may see (``ROLES``):

* ``repo/``: a copy (not a link) of the task's base snapshot, checked against the
  snapshot's recorded manifest first, made a fresh git repository with one base commit
  (fixed author, committer and date, so every workspace of a task has the same commit id).
  git runs with an allowlisted environment: no ``GIT_*`` variable of the caller (``GIT_DIR``,
  ``GIT_WORK_TREE``, ``GIT_INDEX_FILE`` ...) reaches it, only the fixed identity, date and
  configuration variables;
* ``instruction.md``: the ``--instruction`` file; for the fresh role, ``--variant`` instead builds
  the instruction of protocol §15.4 from the task's scripted turns: ``u1`` is U1, ``final`` is U1,
  the line ``Later in the session the user added:`` and U2. Each absolute path of the session's
  old workspace in U1 and U2 is replaced by the corresponding path of this workspace (§16.2,
  :func:`substitute_paths`): the old workspace itself, its repository checkout (and any path under
  it), ``run_tests.sh`` and ``run_python.sh``. Nothing else is changed, and every substitution is
  recorded. For a role that reads a contract, the instruction is rendered from that contract;
* for generator roles, only the inputs the role may read: the contract of its variant
  (``contract.json``: the active scored requirements with id, kind, statement, observable
  and the user turn that introduced them, as ``export-gen-workspace`` wrote it), the graded
  part of the reference diff (``reference.diff``, without the session agent's test files),
  and the rendered session (``session.txt``) or its first user request
  (``session_first_prompt.txt``);
* with ``--image``: ``run_tests.sh`` and ``run_python.sh``, the sandbox wrappers of the
  controlled sessions (``tracecontract.controlled.RUN_TESTS_SH`` and ``RUN_PYTHON_SH``), which run
  the working copy read-only and offline in that image. A ``--variant`` workspace needs them, as
  its instruction names them. :func:`check_wrappers` checks that each is that template rendered
  for this workspace, executable, and that its one command runs the code only in the Docker
  sandbox. Unless ``--no-smoke`` is given, the command line also runs both
  (:func:`smoke_wrappers`): Python runs in the image, ``/repo`` is the workspace's ``repo/``,
  read-only, with no network, and pytest answers;
* ``scratch/``: a private scratch directory (mode 0700) for the agent's notes and scripts,
  in place of any shared scratch directory;
* ``manifest.json``: the sha256 of every other file, by its path in the workspace
  (``repo/.git`` is represented by the base commit id), with the role and its inputs, the
  instruction's sha256 and, for a variant, the variant and the recorded substitutions.

Before the workspace is kept, :func:`check_workspace` checks it, and a failed check removes
it again: the top level holds only the role's entries; there is no symlink, hard link or
special file; ``repo/`` equals the snapshot and its git history is the one base commit; no
file equals a file of forbidden material, other than a file of the base snapshot itself: the
repository's ``tasks/``, ``results/``, ``docs/``, ``data/`` and ``paper/``, the sealed directory
(``--sealed``, default ``/home/user/.tc_sealed``), the third-party data under ``/home/user/ext``,
the build session's old workspaces (``/home/user/cs_workspaces``, ``/home/user/gen_workspaces``),
and every other workspace under the root (except the files this tool wrote there, as its
manifest records them). So nothing from ``tasks/*/verifiers``, ``tasks/*/candidates``,
``tasks/*/labels``, ``results/``, ``docs/``, ``data/controlled``, sealed material or another
agent's work is present; the reference diff is the only text derived from a candidate, for the
roles that read it. The root may not lie inside the repository, a sealed directory, the
third-party data, an old workspace, another workspace, a ``--forbid`` directory (such as the
build session's scratch directory) or a Claude session directory.

No text written into the workspace (the instruction, every role input, the wrappers and the
manifest) may name an absolute path outside the workspace (:func:`outside_paths`): the
controlled sessions' first prompts and transcripts name their own old workspace.
``--allow-outside-paths`` keeps such paths, but only if none of them exists, nor the directory
holding it below the top level (:func:`exists_near`); the old-workspace paths that a recorded
substitution names in the manifest must not exist either.

The manifest is printed as JSON, with the workspace's path; keep it with the private run
record. Model identifiers have no place in the workspace or the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracecontract.contract import render_instruction
from tracecontract.controlled import RUN_PYTHON_SH, RUN_TESTS_SH
from tracecontract.patches import filter_patch
from tracecontract.schemas import Candidate, CandidateOrigin, Snapshot, TaskContract, TaskManifest
from tracecontract.snapshot import manifest
from tracecontract.store import load
from tracecontract.tasks import render_session, session_for_task, verify_snapshot

REPO = Path(__file__).resolve().parents[1]
TOOL = "scripts/make_agent_workspace.py"
STUDY_HOME = Path("/home/user")  # the build environment's home, where the study's material lives
FORBIDDEN_DIRS = ("tasks", "results", "docs", "data", "paper")  # under the repository root
DEFAULT_SEALED = tuple(dict.fromkeys((STUDY_HOME / ".tc_sealed", Path.home() / ".tc_sealed")))
DEFAULT_EXTERNAL = (STUDY_HOME / "ext",)  # third-party data (decision log D47)
OLD_WORKSPACES = (STUDY_HOME / "cs_workspaces", STUDY_HOME / "gen_workspaces")  # sealed and removed (D50)
VARIANTS = ("u1", "final")
FINAL_JOINER = "Later in the session the user added:"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*")
_SHELL_SAFE = re.compile(r"[A-Za-z0-9._/-]+")
_PYTHONPATH = re.compile(r"[A-Za-z0-9._/:-]+")
_EMPTY = hashlib.sha256(b"").hexdigest()  # an empty file carries no material
_ABS_PATH = re.compile(r"(?<![\w.~:/-])/[\w.@%+=,-]+(?:/[\w.@%+=,-]+)*")
# Generic system locations that hold no study material: a path under one of them is not an outside path.
# The bare /tmp is not either, but a path under /tmp is (the build session's scratch directory is there).
_SYSTEM = ("/dev", "/proc", "/sys", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/etc")
_GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "dev",
            "GIT_AUTHOR_EMAIL": "dev@localhost", "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@localhost",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"}
# The caller's variables that git may see; every other variable, and every GIT_* variable, is dropped.
_ENV_PASS = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")
_PROBE = ("import os, socket, sys\n"
          "print('python', *sys.version_info[:2])\n"
          "try:\n    open('/repo/.tc_wrapper_probe', 'w')\n    print('repo writable')\n"
          "except OSError:\n    print('repo read-only')\n"
          "try:\n    socket.create_connection(('1.1.1.1', 53), timeout=3)\n    print('network')\n"
          "except OSError:\n    print('no network')\n"
          "print('entries', len(os.listdir('/repo')))\n")


@dataclass(frozen=True)
class Role:
    """What one role may read besides the base snapshot and its instruction."""

    contract: str | None = None  # the contract variant it reads
    reference_diff: bool = False  # the graded part of the reference diff
    session: str | None = None  # "full": the rendered session; "first_prompt": its first user request
    note: str = ""


ROLES: dict[str, Role] = {
    "fresh": Role(note="fresh-agent attempt (protocol §15.4, §16.2): the instruction only (--variant u1|final, or a file)"),
    "testgen-initial": Role("initial_only", True, note="C1/C2 test generator (§4)"),
    "testgen-full": Role("full_session", True, note="C3/C4 test generator (§4)"),
    "freeform": Role(None, True, "full", note="B2 test generator: the whole session (§4)"),
    "diff-derived": Role(None, True, "first_prompt", note="B3 test generator: the initial request and the reference diff (§15.6)"),
    "attack-initial": Role("initial_only", True, note="development attacks on the initial-only verifiers (audit:v1)"),
    "attack-full": Role("full_session", True, note="development attacks on the correction-aware verifiers (audit:v1)"),
    "alt-initial": Role("initial_only", note="development valid alternative from the initial-only contract"),
    "alt-full": Role("full_session", note="development valid alternative from the full-session contract"),
    "alternative": Role("reference", note="held-out valid alternative (§5): no reference diff"),
    "near-miss": Role("reference", True, note="held-out near miss (§5)"),
    "refcheck": Role("reference", True, note="reference-check writer (§5)"),
    "labeler": Role("reference", note="independent labeler (§15.5): no reference diff"),
}
_FILES = {"contract": "contract.json", "reference_diff": "reference.diff", "full": "session.txt",
          "first_prompt": "session_first_prompt.txt"}
_WRAPPERS = (("run_tests.sh", RUN_TESTS_SH), ("run_python.sh", RUN_PYTHON_SH))


class WorkspaceError(RuntimeError):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def git_env() -> dict[str, str]:
    """The environment of every git call: the allowlisted variables of the caller, then the fixed GIT_* ones."""
    return {**{k: os.environ[k] for k in _ENV_PASS if k in os.environ}, **_GIT_ENV}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env=git_env()).stdout


def _is_workspace(d: Path) -> bool:
    """Whether ``d`` is a workspace made by this tool (its manifest names the tool)."""
    try:
        return json.loads((d / "manifest.json").read_text(encoding="utf-8")).get("tool") == TOOL
    except (OSError, ValueError, AttributeError):
        return False


def outside_paths(text: str, ws: Path) -> list[str]:
    """The absolute paths that ``text`` names outside the workspace ``ws``, normalised.

    A path counts if its first component is a real top-level entry of this host, and it is neither the
    bare ``/`` or ``/tmp`` nor under a generic system location (``/usr``, ``/dev``, ``/proc`` ...). Tokens
    that are no path on this host do not count: the sandbox's ``/repo``, a closing tag such as
    ``</tool_use_error>``, a sed script, ``seek(0)/write``.
    """
    top = set(os.listdir("/"))
    out = set()
    for tok in _ABS_PATH.findall(text):
        p = os.path.normpath(tok.rstrip(".,:;"))
        first = p.lstrip("/").split("/", 1)[0]
        if not first or first not in top or p == "/tmp" or _inside(Path(p), ws) \
                or any(p == s or p.startswith(s + "/") for s in _SYSTEM):
            continue
        out.add(p)
    return sorted(out)


def exists_near(p: str) -> bool:
    """Whether a named outside path, or the directory holding it unless that is ``/`` or a top-level directory such
    as ``/tmp``, exists on this host: an agent pointed there would find what is beside it."""
    parent = os.path.dirname(p)
    return os.path.lexists(p) or (parent.count("/") > 1 and os.path.lexists(parent))


def old_workspace(m: TaskManifest, repo_root: Path) -> tuple[str, str]:
    """(old workspace, old repository checkout) of a controlled session: the workspace its scenario recorded."""
    scen = repo_root / "data" / m.population.value / "scenarios" / f"{m.task_id}.json"
    try:
        checkout = json.loads(scen.read_text(encoding="utf-8"))["workspace"]
    except (OSError, ValueError, KeyError, TypeError):
        raise WorkspaceError(f"{m.task_id}: no recorded session workspace in {scen}") from None
    if not isinstance(checkout, str) or not checkout.startswith("/"):
        raise WorkspaceError(f"{m.task_id}: the recorded session workspace is not an absolute path")
    checkout = os.path.normpath(checkout)
    return os.path.dirname(checkout), checkout


def substitute_paths(text: str, old_root: str, old_checkout: str, ws: Path) -> tuple[str, list[dict]]:
    """Protocol v0.8 §16.2: ``text`` with each absolute path of the old workspace replaced by the corresponding path of
    the attempt workspace ``ws``, and one record per distinct substitution (``from``, ``to`` relative to ``ws`` with
    ``.`` for ``ws`` itself, ``count``).

    The old workspace corresponds to ``ws``, its checkout (and any path under it) to ``ws/repo``, and its
    ``run_tests.sh`` and ``run_python.sh`` to those of ``ws``. Any other path under the old workspace has no
    corresponding path and is refused, and so is any trace of the old workspace the substitution could not place.
    """
    fixed = {old_root: ws, old_checkout: ws / "repo", f"{old_root}/run_tests.sh": ws / "run_tests.sh",
             f"{old_root}/run_python.sh": ws / "run_python.sh"}
    counts: dict[tuple[str, str], int] = {}

    def sub(m: re.Match[str]) -> str:
        tok = m.group(0)
        core = tok.rstrip(".,:;")
        p = os.path.normpath(core)
        if not (p == old_root or p.startswith(old_root + "/")):
            return tok
        if p in fixed:
            new = fixed[p]
        elif p.startswith(old_checkout + "/"):
            new = ws / "repo" / p[len(old_checkout) + 1:]
        else:
            raise WorkspaceError(f"{p} has no corresponding path in the attempt workspace (protocol §16.2)")
        counts[(core, os.path.relpath(new, ws))] = counts.get((core, os.path.relpath(new, ws)), 0) + 1
        return str(new) + tok[len(core):]

    out = _ABS_PATH.sub(sub, text)
    if old_root in out:
        raise WorkspaceError(f"the old workspace {old_root} is still named after the substitution")
    return out, [{"from": a, "to": b, "count": n} for (a, b), n in counts.items()]


def fresh_instruction(m: TaskManifest, variant: str, old_root: str, old_checkout: str, ws: Path) -> tuple[str, list[dict]]:
    """The §15.4 instruction ``variant`` (``u1``, or ``final`` = U1, the joining line and U2) with the §16.2
    substitutions, and their records by turn."""
    if variant not in VARIANTS:
        raise WorkspaceError(f"unknown variant {variant!r}; one of {list(VARIANTS)}")
    turns = m.scripted_turns[:1 if variant == "u1" else 2]
    if len(turns) < (1 if variant == "u1" else 2):
        raise WorkspaceError(f"{m.task_id} has no scripted turns for variant {variant}")
    texts, records = [], []
    for k, turn in enumerate(turns, 1):
        text, subs = substitute_paths(turn, old_root, old_checkout, ws)
        texts.append(text)
        records += [{"turn": f"U{k}", **s} for s in subs]
    body = texts[0] if variant == "u1" else f"{texts[0]}\n\n{FINAL_JOINER}\n\n{texts[1]}"
    return body + "\n", records


def _role_inputs(task_dir: Path, m: TaskManifest, role: Role, repo_root: Path) -> dict[str, str]:
    """The texts of the role's inputs, by file name in the workspace."""
    out: dict[str, str] = {}
    try:
        session = session_for_task(task_dir, repo_root) if role.contract or role.session else None
    except FileNotFoundError as exc:
        raise WorkspaceError(f"{m.task_id}: session transcript missing ({exc.filename})") from None
    if role.contract:
        rel = m.contracts.get(role.contract)
        if not rel or not (task_dir / rel).is_file():
            raise WorkspaceError(f"{m.task_id} has no {role.contract} contract (sealed or missing)")
        c = load(task_dir / rel, TaskContract)
        assert session is not None
        order = {p.event_id: i + 1 for i, p in enumerate(session.user_prompts())}
        reqs = [{"req_id": r.req_id, "kind": r.kind.value, "statement": r.statement, "observable": r.observable,
                 "introduced_in_user_turn": order.get(r.introduced_at)} for r in c.active() if r.scored]
        out[_FILES["contract"]] = json.dumps({"variant": c.variant.value, "requirements": reqs}, indent=2) + "\n"
        out["instruction.md"] = render_instruction(c)
    if role.reference_diff:
        ref = next((c for c in (load(task_dir / p, Candidate) for p in m.candidates) if c.origin == CandidateOrigin.reference),
                   None)
        if ref is None:
            raise WorkspaceError(f"{m.task_id} has no reference candidate")
        out[_FILES["reference_diff"]] = filter_patch(ref.patch)[0]
    if role.session:
        assert session is not None
        out[_FILES[role.session]] = render_session(session, first_prompt_only=role.session == "first_prompt")
    return out


def _wrapper_pythonpath(candidate_pythonpath: str) -> str:
    """The task's candidate PYTHONPATH with the grader's /work mount replaced by the wrappers' /repo mount."""
    return ":".join("/repo" + e[len("/work"):] if e == "/work" or e.startswith("/work/") else e
                    for e in candidate_pythonpath.split(":") if e)


def _walk(ws: Path):
    """Every path in the workspace except the inside of ``repo/.git``."""
    for dirpath, dirnames, filenames in os.walk(ws):
        d = Path(dirpath)
        if d == ws / "repo":
            dirnames[:] = [x for x in dirnames if x != ".git"]
        for n in dirnames + filenames:
            yield d / n


def _files(root: Path) -> Iterator[Path]:
    """Regular files under ``root`` (no symlinks), without the inside of git directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x != ".git"]
        for n in filenames:
            p = Path(dirpath) / n
            if p.is_file() and not p.is_symlink():
                yield p


@dataclass(frozen=True)
class Forbidden:
    """Where forbidden material lies: whole directories, and other workspaces (whose tool-written files may repeat)."""

    roots: tuple[Path, ...]
    workspaces: tuple[Path, ...] = ()

    def files(self) -> Iterator[tuple[Path, set[str]]]:
        """(file, hashes it may have without being forbidden) for every file of forbidden material."""
        for root in self.roots:
            if root.is_dir():
                yield from ((p, set()) for p in sorted(_files(root)))
        for d in self.workspaces:
            try:
                written = json.loads((d / "manifest.json").read_text(encoding="utf-8")).get("files", {})
            except (OSError, ValueError, AttributeError):
                written = {}
            for p in sorted(_files(d)):
                rel = p.relative_to(d).as_posix()
                yield p, {written[rel]} if rel in written else set()


def forbidden_for(repo_root: Path, sealed: tuple[Path, ...], *, external: tuple[Path, ...] = DEFAULT_EXTERNAL,
                  old_workspaces: tuple[Path, ...] = OLD_WORKSPACES, root: Path | None = None,
                  ws: Path | None = None) -> Forbidden:
    """The forbidden material of a workspace ``ws`` under ``root`` (see the module docstring)."""
    others = tuple(d for d in sorted(root.iterdir()) if d != ws and d.is_dir() and not d.is_symlink()) \
        if root is not None and root.is_dir() else ()
    return Forbidden(tuple(repo_root / d for d in FORBIDDEN_DIRS) + tuple(sealed) + tuple(external) + tuple(old_workspaces),
                     others)


def _forbidden_hashes(forbidden: Forbidden, allowed: set[str], sizes: set[int]) -> dict[str, str]:
    """sha256 -> one forbidden file with that content, for files of a size in ``sizes`` not also in the base snapshot.

    A file that vanishes while the material is walked (listed, then gone, or its directory gone, before it is read: a
    temporary file that a running S10 resolver renames under the git-ignored ``data/natural/s10_work``, for example) is
    skipped, since there is nothing left to read; every file still there is checked. No directory is left out of the
    walk: ``data/natural`` holds pseudonymised third-party text, and what the S10 work directory holds is not fixed.
    """
    out: dict[str, str] = {}
    for p, ok in forbidden.files():
        try:
            if p.stat().st_size not in sizes:
                continue
            h = _sha(p)
        except (FileNotFoundError, NotADirectoryError):  # it vanished after the listing
            continue
        if h not in allowed and h not in ok and h != _EMPTY:
            out.setdefault(h, str(p))
    return out


def _sandbox_problems(name: str, text: str, ws: Path) -> list[str]:
    """Problems with a wrapper's command: it must be one ``exec docker run`` of an offline, read-only container that
    mounts only the workspace's ``repo/``, read-only, at ``/repo``."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    logical, cur = [], ""
    for ln in lines:
        cur += ln[:-1] + " " if ln.endswith("\\") else ln
        if not ln.endswith("\\"):
            logical.append(cur)
            cur = ""
    if cur or len(logical) != 1:
        return [f"{name} must hold exactly one command"]
    try:
        words = shlex.split(logical[0])
    except ValueError:
        return [f"{name}: its command cannot be parsed"]
    problems = []
    if words[:3] != ["exec", "docker", "run"]:
        problems.append(f"{name} does not exec docker run")
    opts: list[tuple[str, str | None]] = []  # (flag, value) for every option, in either form
    for i, w in enumerate(words):
        if w.startswith("-"):
            flag, eq, value = w.partition("=")
            opts.append((flag, value if eq else (words[i + 1] if i + 1 < len(words) else None)))
    for flag, value in (("--network", "none"), ("--cap-drop", "ALL"), ("--security-opt", "no-new-privileges")):
        if (flag, value) not in opts:
            problems.append(f"{name}: no {flag} {value}")
    if any(f in ("--network", "--net") and v != "none" for f, v in opts):
        problems.append(f"{name}: a network other than none")
    if "--read-only" not in words:
        problems.append(f"{name}: the container is not read-only")
    banned = sorted({f for f, _ in opts if f in ("--privileged", "--pid", "--ipc", "--uts", "--userns", "--cgroupns",
                                                  "--cap-add", "--device", "--volumes-from", "--mount")})
    if banned:
        problems.append(f"{name}: {', '.join(banned)} not allowed")
    if [v for f, v in opts if f in ("-v", "--volume")] != [f"{ws / 'repo'}:/repo:ro"]:
        problems.append(f"{name}: it must mount only the workspace's repo/, read-only, at /repo")
    return problems


def check_wrappers(ws: Path, fmt: dict[str, str]) -> list[str]:
    """Problems with the sandbox wrappers: each must be the controlled sessions' template (``controlled.RUN_TESTS_SH``,
    ``RUN_PYTHON_SH``) rendered with ``fmt`` for this workspace, an executable regular file whose one command runs the
    code only in the Docker sandbox (:func:`_sandbox_problems`)."""
    problems = []
    for name, tpl in _WRAPPERS:
        p = ws / name
        if p.is_symlink() or not p.is_file():
            problems.append(f"{name} is missing")
            continue
        if not os.access(p, os.X_OK):
            problems.append(f"{name} is not executable")
        text = p.read_text(encoding="utf-8")
        if text != tpl.format(**fmt):
            problems.append(f"{name} is not the controlled sessions' wrapper rendered for this workspace")
        problems += _sandbox_problems(name, text, ws)
    return problems


def smoke_wrappers(ws: Path, timeout: int = 300) -> list[str]:
    """Run both wrappers (Docker): Python runs in the image, ``/repo`` is this workspace's ``repo/``, read-only, with no
    network, and ``run_tests.sh --version`` answers. Problems, or an empty list."""
    try:
        p = subprocess.run([str(ws / "run_python.sh"), "-c", _PROBE], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        q = subprocess.run([str(ws / "run_tests.sh"), "--version"], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"the wrappers did not run: {type(exc).__name__}: {exc}"]
    problems = []
    lines = p.stdout.splitlines()
    want = ["repo read-only", "no network", f"entries {len(os.listdir(ws / 'repo'))}"]
    if p.returncode != 0 or len(lines) != 4 or not lines[0].startswith("python 3 ") or lines[1:] != want:
        problems.append(f"run_python.sh: exit {p.returncode}, output {lines[:4]!r}, expected Python 3 and {want!r}; "
                        f"{p.stderr.strip()[-300:]}")
    if q.returncode != 0:
        problems.append(f"run_tests.sh --version: exit {q.returncode}; {(q.stderr or q.stdout).strip()[-300:]}")
    return problems


def check_workspace(ws: Path, *, expected: set[str], snapshot: Path, repo_root: Path, sealed: tuple[Path, ...],
                    forbidden: Forbidden | None = None, permitted: frozenset[str] = frozenset(),
                    wrappers: dict[str, str] | None = None) -> list[str]:
    """Problems with a built workspace (empty when it holds only what its role may see).

    ``forbidden`` defaults to the repository's study directories and ``sealed``; ``permitted`` are the outside
    paths its texts may name (each must not exist); ``wrappers`` is the rendering of the sandbox wrappers, if any.
    """
    forbidden = forbidden or Forbidden(tuple(repo_root / d for d in FORBIDDEN_DIRS) + tuple(sealed))
    problems = []
    top = {p.name for p in ws.iterdir()}
    if top != expected:
        problems.append(f"top level holds {sorted(top)}, expected {sorted(expected)}")
    for p in _walk(ws):
        st = p.lstat()
        if stat.S_ISLNK(st.st_mode):
            problems.append(f"symlink: {p.relative_to(ws)}")
        elif stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
            problems.append(f"hard link: {p.relative_to(ws)}")
        elif not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
            problems.append(f"special file: {p.relative_to(ws)}")
    base = sorted(manifest(snapshot))
    files = sorted((p.relative_to(ws / "repo").as_posix(), _sha(p)) for p in _walk(ws)
                   if p.is_file() and _inside(p, ws / "repo"))
    if files != base:
        problems.append("repo/ differs from the base snapshot")
    if (ws / "repo" / ".git").is_dir():
        if _git(ws / "repo", "rev-list", "--count", "HEAD").strip() != "1":
            problems.append("repo/ has more than its one base commit")
        tracked = sorted(x for x in _git(ws / "repo", "ls-files", "-z").split("\0") if x)
        if tracked != sorted(path for path, _ in base):
            problems.append("the base commit does not hold exactly the snapshot")
    else:
        problems.append("repo/ is not a git repository")
    own = [p for p in _walk(ws) if p.is_file() and not p.is_symlink() and not _inside(p, ws / "repo")]
    bad = _forbidden_hashes(forbidden, {h for _, h in base}, {p.stat().st_size for p in own})
    for p in own:
        if _sha(p) in bad:
            problems.append(f"{p.relative_to(ws)} equals forbidden material ({bad[_sha(p)]})")
    for p in own:
        named = outside_paths(p.read_text(encoding="utf-8", errors="replace"), ws)
        if [x for x in named if x not in permitted]:
            problems.append(f"{p.relative_to(ws)} names paths outside the workspace: {[x for x in named if x not in permitted]}")
        if [x for x in named if exists_near(x)]:
            problems.append(f"{p.relative_to(ws)} names outside paths that exist: {[x for x in named if exists_near(x)]}")
    if wrappers is not None:
        problems += check_wrappers(ws, wrappers)
    return problems


def make_workspace(task_dir: Path, root: Path, *, role: str, name: str, instruction: Path | None = None,
                   variant: str | None = None, repo_root: Path = REPO, snapshot_root: Path | None = None,
                   image: str | None = None, pythonpath: str | None = None, pytest_args: str = "",
                   sealed: tuple[Path, ...] = DEFAULT_SEALED, external: tuple[Path, ...] = DEFAULT_EXTERNAL,
                   old_workspaces: tuple[Path, ...] = OLD_WORKSPACES, forbid: tuple[Path, ...] = (),
                   allow_outside_paths: bool = False, smoke: bool = False) -> dict:
    """Build the workspace ``root/name`` for one agent in ``role``; return its manifest (see the module docstring)."""
    if role not in ROLES:
        raise WorkspaceError(f"unknown role {role!r}; one of {sorted(ROLES)}")
    if not _NAME.fullmatch(name):
        raise WorkspaceError(f"workspace name {name!r} must match {_NAME.pattern}")
    if variant is not None and (role != "fresh" or instruction is not None or image is None):
        raise WorkspaceError("--variant builds a fresh attempt's instruction: role fresh, no --instruction, and --image "
                             "for the wrappers that the instruction names")
    r = ROLES[role]
    task_dir, repo_root = task_dir.resolve(), repo_root.resolve()
    sealed = tuple(Path(s).resolve() for s in sealed if Path(s).is_dir())
    root = root.resolve()
    ws = root / name
    for no, why in [(repo_root, "the repository"), *((s, "sealed material") for s in sealed),
                    *((Path(e).resolve(), "third-party data") for e in external),
                    *((Path(o).resolve(), "an old workspace") for o in old_workspaces),
                    *((Path(f).resolve(), "a forbidden directory") for f in forbid)]:
        if _inside(ws, no) or _inside(no, ws):
            raise WorkspaceError(f"{ws} would lie inside (or around) {why} ({no})")
    if str(ws).startswith("/tmp/claude-") or ".claude" in ws.parts:
        raise WorkspaceError(f"{ws} would lie inside a Claude session directory")
    if any(_is_workspace(a) for a in ws.parents):
        raise WorkspaceError(f"{ws} would lie inside another workspace")
    if image is not None and (not _IMAGE.fullmatch(image) or not _SHELL_SAFE.fullmatch(str(ws))
                              or (pythonpath is not None and not _PYTHONPATH.fullmatch(pythonpath))):
        raise WorkspaceError("the wrappers need a plain image tag, PYTHONPATH and workspace path (no shell metacharacters)")
    m = load(task_dir / "task.json", TaskManifest)
    snapshot_root = (snapshot_root or repo_root / "snapshots").resolve()
    snapshot = snapshot_root / m.task_id
    if not snapshot.is_dir() or not verify_snapshot(task_dir, snapshot_root):
        raise WorkspaceError(f"base snapshot {snapshot} missing or different from its recorded manifest")
    odd = [p for p in snapshot.rglob("*") if p.is_symlink() or not (p.is_file() or p.is_dir())]
    if odd:
        raise WorkspaceError(f"base snapshot holds symlinks or special files: {[str(p) for p in odd[:5]]}")
    inputs = _role_inputs(task_dir, m, r, repo_root)
    subs: list[dict] = []
    if instruction is not None:
        inputs["instruction.md"] = instruction.read_text(encoding="utf-8")
    elif variant is not None:
        old_root, old_checkout = old_workspace(m, repo_root)
        inputs["instruction.md"], subs = fresh_instruction(m, variant, old_root, old_checkout, ws)
        alive = sorted({s["from"] for s in subs if exists_near(s["from"])})
        if alive:
            raise WorkspaceError(f"the session's old workspace still exists ({alive}); it must be sealed first (D50)")
    if not inputs.get("instruction.md", "").strip():
        raise WorkspaceError(f"role {role} needs an instruction (--instruction{' or --variant' if role == 'fresh' else ''})")
    named = {f: outside_paths(t, ws) for f, t in inputs.items()}
    outside = sorted({p for ps in named.values() for p in ps})
    where = "; ".join(f"{f}: {ps}" for f, ps in named.items() if ps)
    if outside and not allow_outside_paths:
        raise WorkspaceError(f"the workspace's texts name paths outside the workspace ({where}); --allow-outside-paths "
                             "keeps them if none exists")
    existing = [p for p in outside if exists_near(p)]
    if existing:
        raise WorkspaceError(f"the workspace's texts name outside paths that exist, or whose directory exists: {existing} "
                             f"({where})")
    root.mkdir(parents=True, exist_ok=True)
    forbidden = forbidden_for(repo_root, sealed, external=tuple(Path(e).resolve() for e in external),
                              old_workspaces=tuple(Path(o).resolve() for o in old_workspaces), root=root, ws=ws)
    try:
        ws.mkdir()
    except FileExistsError:
        raise WorkspaceError(f"{ws} exists; a workspace is always new") from None
    try:
        shutil.copytree(snapshot, ws / "repo", symlinks=True)
        _git(ws / "repo", "init", "-q", "--template=", "-b", "main")
        _git(ws / "repo", "add", "-A", "-f")
        _git(ws / "repo", "commit", "-q", "--no-verify", "-m", f"base: {m.snapshot_source.commit[:12]}")
        commit = _git(ws / "repo", "rev-parse", "HEAD").strip()
        for fname, text in inputs.items():
            (ws / fname).write_text(text, encoding="utf-8")
        fmt = None
        if image is not None:
            fmt = dict(root=str(ws), repo=str(ws / "repo"), image=image,
                       pythonpath=pythonpath or _wrapper_pythonpath(m.candidate_pythonpath),
                       extra=" ".join(shlex.quote(x) for x in shlex.split(pytest_args)))
            for fname, tpl in _WRAPPERS:
                (ws / fname).write_text(tpl.format(**fmt), encoding="utf-8")
                (ws / fname).chmod(0o755)
        (ws / "scratch").mkdir(mode=0o700)
        (ws / "scratch").chmod(0o700)
        smoked = None
        if smoke and fmt is not None:
            trouble = check_wrappers(ws, fmt) or smoke_wrappers(ws)
            if trouble:
                raise WorkspaceError("the sandbox wrappers do not work: " + "; ".join(trouble))
            smoked = "passed"
        ins: dict[str, Any] = {"contract": r.contract, "reference_diff": r.reference_diff, "session": r.session,
               "instruction_sha256": hashlib.sha256(inputs["instruction.md"].encode("utf-8")).hexdigest(),
               "instruction_from": "file" if instruction is not None else "variant" if variant else "contract"}
        if variant:
            ins |= {"variant": variant, "path_substitutions": subs}
        wrap = None if fmt is None else {"image": image, "pythonpath": fmt["pythonpath"], "pytest_args": fmt["extra"]}
        if wrap is not None and smoked:
            wrap["smoke"] = smoked
        rec = {
            "tool": TOOL, "task_id": m.task_id, "role": role, "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "inputs": ins,
            "base": {"snapshot_manifest_sha256": load(task_dir / (m.snapshot or "snapshot.json"), Snapshot).file_manifest_sha256,
                     "commit": commit, "n_files": len(manifest(snapshot))},
            "wrappers": wrap,
            "scratch": "scratch/",
            "files": {p.relative_to(ws).as_posix(): _sha(p) for p in sorted(_walk(ws)) if p.is_file()},
        }
        (ws / "manifest.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
        expected = {"repo", "scratch", "manifest.json", *inputs} | ({"run_tests.sh", "run_python.sh"} if image else set())
        permitted = frozenset(outside) | frozenset(s["from"] for s in subs)
        problems = check_workspace(ws, expected=expected, snapshot=snapshot, repo_root=repo_root, sealed=sealed,
                                   forbidden=forbidden, permitted=permitted, wrappers=fmt)
        if problems:
            raise WorkspaceError("workspace check failed: " + "; ".join(problems))
    except BaseException:
        shutil.rmtree(ws, ignore_errors=True)
        raise
    return rec


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="roles:\n" + "\n".join(f"  {k:16} {v.note}" for k, v in ROLES.items()))
    ap.add_argument("task")
    ap.add_argument("--role", required=True, choices=sorted(ROLES))
    ap.add_argument("--root", required=True, help="directory outside the repository that holds the workspaces")
    ap.add_argument("--name", required=True, help="the new workspace's directory name, e.g. CS-01-fresh-A-u1-1")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--instruction", help="instruction file (required for roles that read no contract, unless --variant)")
    src.add_argument("--variant", choices=VARIANTS, help="fresh role: build the §15.4 instruction u1 or final, with the "
                                                         "§16.2 path substitution (needs --image)")
    ap.add_argument("--image", help="write the sandbox wrappers for this image tag")
    ap.add_argument("--pythonpath", help="PYTHONPATH inside the wrappers' container (default: the task's, under /repo)")
    ap.add_argument("--pytest-args", default="", help="extra pytest arguments for run_tests.sh, e.g. '-o addopts='")
    ap.add_argument("--no-smoke", action="store_true", help="with --image: do not run the wrappers once in Docker")
    ap.add_argument("--sealed", action="append", help="sealed directory (repeatable; default /home/user/.tc_sealed)")
    ap.add_argument("--forbid", action="append", default=[], help="directory the root may not lie in (repeatable)")
    ap.add_argument("--allow-outside-paths", action="store_true",
                    help="keep absolute paths outside the workspace in its texts, if none of them exists")
    ap.add_argument("--repo-root", default=str(REPO), help="the study repository (default: this one)")
    ap.add_argument("--snapshots", help="directory of the base snapshots (default: <repo-root>/snapshots)")
    a = ap.parse_args(argv)
    try:
        rec = make_workspace(Path(a.task), Path(a.root), role=a.role, name=a.name,
                             instruction=Path(a.instruction) if a.instruction else None, variant=a.variant,
                             repo_root=Path(a.repo_root), snapshot_root=Path(a.snapshots) if a.snapshots else None,
                             image=a.image, pythonpath=a.pythonpath, pytest_args=a.pytest_args,
                             sealed=tuple(Path(s) for s in a.sealed) if a.sealed else DEFAULT_SEALED,
                             forbid=tuple(Path(f) for f in a.forbid), allow_outside_paths=a.allow_outside_paths,
                             smoke=a.image is not None and not a.no_smoke)
    except WorkspaceError as exc:
        print(f"make_agent_workspace: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"workspace": str(Path(a.root).resolve() / a.name), **rec}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
