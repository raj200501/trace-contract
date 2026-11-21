"""Isolated workspace for one generator or fresh agent (protocol v0.7 §15.4; decision log D44, D46, D47).

Usage: python scripts/make_agent_workspace.py tasks/<id> --role <role> --root <dir> --name <name>
           [--instruction <file>] [--image <tag> [--pythonpath <path>] [--pytest-args <args>]]
           [--sealed <dir> ...] [--forbid <dir> ...] [--allow-outside-paths]

It creates the new directory ``<root>/<name>``, outside the repository, holding only what
the role may see (``ROLES``):

* ``repo/``: a copy (not a link) of the task's base snapshot, checked against the
  snapshot's recorded manifest first, made a fresh git repository with one base commit
  (fixed author, committer and date, so every workspace of a task has the same commit id);
* ``instruction.md``: the ``--instruction`` file or, for a role that reads a contract, the
  instruction rendered from that contract;
* for generator roles, only the inputs the role may read: the contract of its variant
  (``contract.json``: the active scored requirements with id, kind, statement, observable
  and the user turn that introduced them, as ``export-gen-workspace`` wrote it), the graded
  part of the reference diff (``reference.diff``, without the session agent's test files),
  and the rendered session (``session.txt``) or its first user request
  (``session_first_prompt.txt``);
* with ``--image``: ``run_tests.sh`` and ``run_python.sh``, the sandbox wrappers of the
  controlled sessions, which run the working copy read-only and offline in that image;
* ``scratch/``: a private scratch directory (mode 0700) for the agent's notes and scripts,
  in place of any shared scratch directory;
* ``manifest.json``: the sha256 of every other file, by its path in the workspace
  (``repo/.git`` is represented by the base commit id), with the role and its inputs.

Before the workspace is kept, :func:`check_workspace` checks it, and a failed check removes
it again: the top level holds only the role's entries; there is no symlink, hard link or
special file; ``repo/`` equals the snapshot and its git history is the one base commit; no
file equals a file under the repository's ``tasks/``, ``results/``, ``docs/``, ``data/`` or
``paper/`` or under a sealed directory (``--sealed``, default ``~/.tc_sealed``), other
than a file of the base snapshot itself. So nothing from ``tasks/*/verifiers``,
``tasks/*/candidates``, ``tasks/*/labels``, ``results/``, ``docs/``, ``data/controlled``
or sealed material is present; the reference diff is the only text derived from a
candidate, for the roles that read it. The root may not lie inside the repository, a
sealed directory, a ``--forbid`` directory (such as the build session's scratch
directory) or a Claude session directory. The instruction may not name an absolute path
outside the workspace (the controlled sessions' first prompts name their own old
workspace) unless ``--allow-outside-paths`` is given.

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tracecontract.contract import render_instruction
from tracecontract.controlled import RUN_PYTHON_SH, RUN_TESTS_SH
from tracecontract.patches import filter_patch
from tracecontract.schemas import Candidate, CandidateOrigin, Snapshot, TaskContract, TaskManifest
from tracecontract.snapshot import manifest
from tracecontract.store import load
from tracecontract.tasks import render_session, session_for_task, verify_snapshot

REPO = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = ("tasks", "results", "docs", "data", "paper")  # under the repository root
DEFAULT_SEALED = (Path.home() / ".tc_sealed",)
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*")
_SHELL_SAFE = re.compile(r"[A-Za-z0-9._/-]+")
_PYTHONPATH = re.compile(r"[A-Za-z0-9._/:-]+")
_EMPTY = hashlib.sha256(b"").hexdigest()  # an empty file carries no material
_ABS_PATH = re.compile(r"(?<![\w.~:/-])/[\w.@%+=,-]+(?:/[\w.@%+=,-]+)*")
_GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "dev",
            "GIT_AUTHOR_EMAIL": "dev@localhost", "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@localhost",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"}


@dataclass(frozen=True)
class Role:
    """What one role may read besides the base snapshot and its instruction."""

    contract: str | None = None  # the contract variant it reads
    reference_diff: bool = False  # the graded part of the reference diff
    session: str | None = None  # "full": the rendered session; "first_prompt": its first user request
    note: str = ""


ROLES: dict[str, Role] = {
    "fresh": Role(note="fresh-agent attempt (protocol §15.4): the instruction only"),
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


class WorkspaceError(RuntimeError):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, **_GIT_ENV}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


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


def _forbidden_hashes(repo_root: Path, sealed: tuple[Path, ...], allowed: set[str]) -> dict[str, str]:
    """sha256 -> one forbidden file with that content, for files not also in the base snapshot."""
    out: dict[str, str] = {}
    roots = [repo_root / d for d in FORBIDDEN_DIRS] + list(sealed)
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and not p.is_symlink():
                h = _sha(p)
                if h not in allowed and h != _EMPTY:
                    out.setdefault(h, str(p))
    return out


def check_workspace(ws: Path, *, expected: set[str], snapshot: Path, repo_root: Path, sealed: tuple[Path, ...]) -> list[str]:
    """Problems with a built workspace (empty when it holds only what its role may see)."""
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
    bad = _forbidden_hashes(repo_root, sealed, {h for _, h in base})
    for p in _walk(ws):
        if p.is_file() and _sha(p) in bad:
            problems.append(f"{p.relative_to(ws)} equals forbidden material ({bad[_sha(p)]})")
    return problems


def make_workspace(task_dir: Path, root: Path, *, role: str, name: str, instruction: Path | None = None,
                   repo_root: Path = REPO, snapshot_root: Path | None = None, image: str | None = None,
                   pythonpath: str | None = None, pytest_args: str = "", sealed: tuple[Path, ...] = DEFAULT_SEALED,
                   forbid: tuple[Path, ...] = (), allow_outside_paths: bool = False) -> dict:
    """Build the workspace ``root/name`` for one agent in ``role``; return its manifest (see the module docstring)."""
    if role not in ROLES:
        raise WorkspaceError(f"unknown role {role!r}; one of {sorted(ROLES)}")
    if not _NAME.fullmatch(name):
        raise WorkspaceError(f"workspace name {name!r} must match {_NAME.pattern}")
    r = ROLES[role]
    task_dir, repo_root = task_dir.resolve(), repo_root.resolve()
    sealed = tuple(Path(s).resolve() for s in sealed if Path(s).is_dir())
    root = root.resolve()
    ws = root / name
    for no, why in [(repo_root, "the repository"), *((s, "sealed material") for s in sealed),
                    *((Path(f).resolve(), "a forbidden directory") for f in forbid)]:
        if _inside(ws, no) or _inside(no, ws):
            raise WorkspaceError(f"{ws} would lie inside (or around) {why} ({no})")
    if str(ws).startswith("/tmp/claude-") or ".claude" in ws.parts:
        raise WorkspaceError(f"{ws} would lie inside a Claude session directory")
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
    if instruction is not None:
        inputs["instruction.md"] = instruction.read_text(encoding="utf-8")
    if not inputs.get("instruction.md", "").strip():
        raise WorkspaceError(f"role {role} needs an instruction (--instruction)")
    outside = sorted({p.rstrip(".,:;") for p in _ABS_PATH.findall(inputs["instruction.md"])
                      if not _inside(Path(os.path.normpath(p.rstrip(".,:;"))), ws)})
    if outside and not allow_outside_paths:
        raise WorkspaceError(f"the instruction names paths outside the workspace: {outside} (--allow-outside-paths keeps them)")
    root.mkdir(parents=True, exist_ok=True)
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
        if image is not None:
            fmt = dict(root=str(ws), repo=str(ws / "repo"), image=image,
                       pythonpath=pythonpath or _wrapper_pythonpath(m.candidate_pythonpath),
                       extra=" ".join(shlex.quote(x) for x in shlex.split(pytest_args)))
            for fname, tpl in (("run_tests.sh", RUN_TESTS_SH), ("run_python.sh", RUN_PYTHON_SH)):
                (ws / fname).write_text(tpl.format(**fmt))
                (ws / fname).chmod(0o755)
        (ws / "scratch").mkdir(mode=0o700)
        (ws / "scratch").chmod(0o700)
        rec = {
            "tool": "scripts/make_agent_workspace.py", "task_id": m.task_id, "role": role, "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "inputs": {"contract": r.contract, "reference_diff": r.reference_diff, "session": r.session,
                       "instruction_sha256": hashlib.sha256(inputs["instruction.md"].encode("utf-8")).hexdigest(),
                       "instruction_from": "file" if instruction is not None else "contract"},
            "base": {"snapshot_manifest_sha256": load(task_dir / (m.snapshot or "snapshot.json"), Snapshot).file_manifest_sha256,
                     "commit": commit, "n_files": len(manifest(snapshot))},
            "wrappers": None if image is None else {"image": image, "pythonpath": fmt["pythonpath"], "pytest_args": fmt["extra"]},
            "scratch": "scratch/",
            "files": {p.relative_to(ws).as_posix(): _sha(p) for p in sorted(_walk(ws)) if p.is_file()},
        }
        (ws / "manifest.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
        expected = {"repo", "scratch", "manifest.json", *inputs} | ({"run_tests.sh", "run_python.sh"} if image else set())
        problems = check_workspace(ws, expected=expected, snapshot=snapshot, repo_root=repo_root, sealed=sealed)
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
    ap.add_argument("--instruction", help="instruction file (required for roles that read no contract)")
    ap.add_argument("--image", help="write the sandbox wrappers for this image tag")
    ap.add_argument("--pythonpath", help="PYTHONPATH inside the wrappers' container (default: the task's, under /repo)")
    ap.add_argument("--pytest-args", default="", help="extra pytest arguments for run_tests.sh, e.g. '-o addopts='")
    ap.add_argument("--sealed", action="append", help="sealed directory (repeatable; default ~/.tc_sealed)")
    ap.add_argument("--forbid", action="append", default=[], help="directory the root may not lie in (repeatable)")
    ap.add_argument("--allow-outside-paths", action="store_true", help="keep absolute paths outside the workspace in the instruction")
    ap.add_argument("--repo-root", default=str(REPO), help="the study repository (default: this one)")
    ap.add_argument("--snapshots", help="directory of the base snapshots (default: <repo-root>/snapshots)")
    a = ap.parse_args(argv)
    try:
        rec = make_workspace(Path(a.task), Path(a.root), role=a.role, name=a.name,
                             instruction=Path(a.instruction) if a.instruction else None, repo_root=Path(a.repo_root),
                             snapshot_root=Path(a.snapshots) if a.snapshots else None, image=a.image,
                             pythonpath=a.pythonpath, pytest_args=a.pytest_args,
                             sealed=tuple(Path(s) for s in a.sealed) if a.sealed else DEFAULT_SEALED,
                             forbid=tuple(Path(f) for f in a.forbid), allow_outside_paths=a.allow_outside_paths)
    except WorkspaceError as exc:
        print(f"make_agent_workspace: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"workspace": str(Path(a.root).resolve() / a.name), **rec}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
