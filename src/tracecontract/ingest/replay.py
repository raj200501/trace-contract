"""Transcript replay: rebuild a session's workspace states from its file edits (decision log D47).

:func:`replay_session` applies the main agent's ``Edit``, ``MultiEdit`` and ``Write`` calls, in
order, to a base tree, and checks every step against what the transcript itself shows:

* each ``old_string`` is present in the replayed file, and unique unless ``replace_all`` is set;
  edits are applied with the tool's own semantics (:mod:`tracecontract.ingest.edit_tool`, the
  same function :mod:`tracecontract.reconstruction` uses);
* the replayed file equals the tool result's ``toolUseResult.originalFile`` where the harness
  recorded it (natural Claude Code sessions; sanitised controlled transcripts drop the field);
* later ``Read`` results agree with the replayed state (``toolUseResult.file`` where present,
  else the numbered lines of the result text);
* no shell command wrote a replayed file (:mod:`tracecontract.ingest.shell_writes`): a write
  onto a replayed file loses it, except a ``cat > f <<'EOF'`` heredoc, a deletion, or a copy or
  move of a known file, which are replayed. A write to a directory, to the workspace root or
  to a glob loses every tracked and base file under it (a glob is expanded over those files);
* a full replay equals a linked commit tree when one is given.

Each touched file has a status: ``exact``; ``recovered`` (its content was recovered from a
full ``Read`` or an ``originalFile`` that followed content the replay could not know);
``approximate`` (it rests on an edit matched only after quote normalisation or with converted
line endings, an edit the user modified, or a heredoc the shell may expand); or ``unknown``.
The verdict is a :class:`~tracecontract.schemas.Fidelity`:

* ``exact``: a base tree was given, every edit applied cleanly, every check the transcript
  allows agreed, and no shell command or subagent may have written files unseen;
* ``approximate``: every replayed file has a known post-image, but some of it is recovered or
  approximate, or a shell command or subagent may have written files whose paths could not be
  placed at all;
* ``unreconstructable``: no base tree (the initial repository state is not in the session), a
  replayed file whose post-image is unknown (an edit on unknown content, a missing or
  ambiguous ``old_string``, a shell write onto it or onto its directory), or a difference from
  the commit tree.

Programs a command runs (build tools, test runners, scripts the session does not show) can
still write files unseen; only the ``originalFile`` and ``Read`` checks or a commit tree catch
that. Nothing from the transcript is executed; its text is data, never instructions.
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..schemas import Event, EventKind, Fidelity, Session
from .edit_tool import apply_edit as apply_edit  # re-exported: the one edit function of both replays
from .edit_tool import apply_edits, edits_of
from .shell_writes import COPIES, DELETIONS, ShellWrite, shell_writes

METHOD = "replay:v2"  # v2: the edit function shared with reconstruction.py; directory, root and glob writes; 'approximate'
EDIT_TOOLS = ("Edit", "MultiEdit", "Write")
SHELL_TOOLS = ("Bash", "PowerShell")
READ_ONLY_SUBAGENTS = ("Explore", "Plan")  # subagent types that cannot edit files
# The CS-v1 wrappers run repository code in a container with the workspace mounted read-only.
CONTROLLED_SANDBOXED = ("run_tests.sh", "run_python.sh")
_NOT_RUN = ("The user doesn't want to proceed with this tool use", "Permission for this action was denied")


class _U(Enum):
    UNKNOWN = "unknown"


UNKNOWN = _U.UNKNOWN  # content the replay does not know (no base tree, or lost after an unseen write)


# ---------------------------------------------------------------------------
# Raw fields that the parser does not keep
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawExtra:
    """Fields of one JSONL entry that :func:`~tracecontract.ingest.claude_code.parse_claude_code_jsonl` drops."""

    cwd: str | None = None
    tool_use_result: Any = None


def load_raw_extras(path: str | Path) -> dict[int, RawExtra]:
    """``cwd`` and ``toolUseResult`` by 1-based JSONL line (the line numbers of :class:`SourceRef`)."""
    out: dict[int, RawExtra] = {}
    for lineno, line in enumerate(Path(path).read_bytes().decode("utf-8", errors="replace").splitlines(), start=1):
        try:
            entry = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and (entry.get("cwd") or "toolUseResult" in entry):
            out[lineno] = RawExtra(cwd=entry.get("cwd") or None, tool_use_result=entry.get("toolUseResult"))
    return out


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DRIVE = re.compile(r"^([A-Za-z]):(?=/|$)")
_POSIX_DRIVE = re.compile(r"^/(?:mnt/)?([A-Za-z])(?=/|$)")  # MSYS (/d/x) and WSL (/mnt/d/x) spellings


def norm_path(p: str) -> str:
    """Forward slashes, a lower-case drive letter, ``.`` and ``..`` resolved."""
    q = _DRIVE.sub(lambda m: m.group(1).lower() + ":", p.strip().replace("\\", "/"))
    return posixpath.normpath(re.sub(r"(?<!^)/{2,}", "/", q)) if q else q


def _is_abs(p: str) -> bool:
    return p.startswith("/") or bool(_DRIVE.match(p))


@dataclass(frozen=True)
class PathMap:
    """Maps the session's paths to paths relative to the workspace root (case-folded on Windows)."""

    root: str

    @property
    def windows(self) -> bool:
        return bool(_DRIVE.match(self.root))

    def absolute(self, p: str, cwd: str | None = None) -> str:
        q = norm_path(p)
        if self.windows:
            q = _POSIX_DRIVE.sub(lambda m: m.group(1).lower() + ":", q)
        if not _is_abs(q):
            q = posixpath.normpath(posixpath.join(norm_path(cwd) if cwd else self.root, q))
        return q

    def rel(self, p: str, cwd: str | None = None) -> str | None:
        """The path relative to the root; None for the root itself and for paths outside it."""
        if not p.strip():
            return None
        q, root = self.absolute(p, cwd), self.root.rstrip("/")
        a, b = (q.lower(), root.lower()) if self.windows else (q, root)
        if not a.startswith(b + "/"):
            return None
        out = q[len(root) + 1:]
        return out.lower() if self.windows else out


def infer_root(session: Session, *, base_files: Iterable[str] = ()) -> str | None:
    """The workspace root of the session's absolute file paths.

    With a base tree: the prefix under which the edited and read files exist in it. Otherwise
    the shortest recorded working directory that holds at least half of them, else their
    common directory.
    """
    paths = [norm_path(str(e.tool_input["file_path"])) for e in session.events
             if e.kind == EventKind.tool_call and e.tool_name in (*EDIT_TOOLS, "Read") and e.tool_input
             and isinstance(e.tool_input.get("file_path"), str)]
    paths = [p for p in paths if _is_abs(p)]
    files = set(base_files)
    votes: Counter[str] = Counter()
    for p in paths if files else []:
        parts = p.split("/")
        hit = next((k for k in range(1, len(parts)) if "/".join(parts[k:]) in files), None)
        if hit is not None:
            votes["/".join(parts[:hit])] += 1
    if votes:
        return votes.most_common(1)[0][0]
    for c in sorted({norm_path(c) for c in session.metadata.get("cwd", []) if c}, key=len):
        if not paths or 2 * sum(PathMap(c).rel(p) is not None for p in paths) >= len(paths):
            return c
    if not paths:
        return None
    common: list[str] = []
    for group in zip(*(posixpath.dirname(p).split("/") for p in paths), strict=False):
        if len({x.lower() for x in group}) != 1:
            break
        common.append(group[0])
    return "/".join(common) or None


# ---------------------------------------------------------------------------
# Base trees and edit semantics
# ---------------------------------------------------------------------------


class BaseTree:
    """Read access to a base tree: a directory, a mapping of relative paths to text, or nothing.

    ``redact`` is applied to every text read, so that a base can be compared with a sanitised
    transcript (``sanitize:v2`` replaced e-mail addresses in controlled transcripts).
    """

    def __init__(self, base: Path | Mapping[str, str] | None, redact: Callable[[str], str] | None = None):
        self.base, self.redact = base, redact
        self._files: set[str] | None = None

    @property
    def known(self) -> bool:
        return self.base is not None

    def get(self, rel: str) -> str | None | _U:
        if self.base is None:
            return UNKNOWN
        if not isinstance(self.base, Path):
            text = self.base.get(rel)
        else:
            f = self.base / rel
            if not f.is_file():
                return None
            try:
                text = f.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                return UNKNOWN  # binary content is not replayed
        return self.redact(text) if self.redact is not None and isinstance(text, str) else text

    def files(self) -> set[str]:
        """Relative paths of every file (computed once)."""
        if self._files is None:
            if self.base is None:
                self._files = set()
            elif not isinstance(self.base, Path):
                self._files = set(self.base)
            else:
                self._files = {p.relative_to(self.base).as_posix() for p in self.base.rglob("*")
                               if p.is_file() and ".git" not in p.relative_to(self.base).parts}
        return self._files


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    check: str  # a key of ReplayResult.counts
    ref: str  # event id
    path: str | None = None
    detail: str = ""


@dataclass
class ReplayResult:
    method: str
    fidelity: Fidelity
    reasons: list[str]
    root: str | None
    files: dict[str, str | None]  # final content of every touched path (None: absent)
    status: dict[str, str]  # per touched path (changed or recovered): exact | recovered | approximate | unknown
    findings: list[Finding]
    counts: Counter
    stop_ref: str | None = None
    base_known: bool = False
    changed: list[str] = field(default_factory=list)  # paths the session changed (edits, writes, shell)

    def summary(self) -> dict[str, Any]:
        """The verdict, its reasons and the counts: no paths and no content."""
        st = Counter(self.status.values())
        return {"method": self.method, "fidelity": self.fidelity.value, "reasons": list(self.reasons),
                "base_tree": self.base_known, "files_touched": len(self.status), "files_changed": len(self.changed),
                "files_exact": st["exact"], "files_recovered": st["recovered"], "files_approximate": st["approximate"],
                "files_unknown": st["unknown"], "counts": dict(sorted(self.counts.items()))}


def _outcome(res: Event | None) -> str:
    if res is None:
        return "missing"
    if any(x in res.text for x in _NOT_RUN):
        return "rejected"
    if res.is_error or res.text.lstrip().startswith("<tool_use_error>"):
        return "error"
    return "ok"


_NUMBERED = re.compile(r"^\s*(\d+)(?:\t|→)(.*)$")


def read_view(res: Event, tur: Any) -> tuple[int, list[str], bool] | None:
    """``(first line, lines shown, whole file shown)`` of a successful ``Read`` result."""
    f = tur.get("file") if isinstance(tur, dict) else None
    if isinstance(f, dict) and isinstance(f.get("content"), str):
        full = (f.get("startLine") or 1) == 1 and f.get("numLines") is not None and f.get("numLines") == f.get("totalLines")
        return int(f.get("startLine") or 1), f["content"].split("\n"), full
    shown: dict[int, str] = {}
    for ln in res.text.split("\n"):
        m = _NUMBERED.match(ln)
        if m and len(m.group(2)) < 2000:  # longer lines are truncated in the output
            shown[int(m.group(1))] = m.group(2)
    first = min(shown, default=0)
    if not shown or sorted(shown) != list(range(first, first + len(shown))):
        return None
    return first, [shown[k] for k in range(first, first + len(shown))], False


def _cd_target(cmd: str, cwd: str | None, paths: PathMap) -> str | None:
    """The working directory after a leading ``cd`` (Bash calls often start with one)."""
    m = re.match(r"^\s*(?:cd|Set-Location|sl|pushd)\s+(\"[^\"]+\"|'[^']+'|\S+)\s*(?:&&|;|\n|$)", cmd)
    target = m.group(1).strip("'\"") if m else ""
    if not target or "$" in target or target.startswith("~") or target == "-":
        return cwd
    return paths.absolute(target, cwd)


_VARIABLE = re.compile(r"[$%`]|^~")  # a target the shell expands from its environment: never placed
_GLOB = re.compile(r"[*?\[]")  # a target the shell expands over existing files: placed over the known ones
_TEMP_VARS = re.compile(r"^(?:\$(?:env:)?\{?(?:TEMP|TMP|TMPDIR)\b|%(?:TEMP|TMP)%)", re.I)
# Git commands that rewrite the work tree (shell_writes gives them no target): placed at the root.
_WORK_TREE = ("git reset", "git stash", "git checkout", "git apply", "git merge", "git pull", "git rebase",
              "git cherry-pick", "git revert", "git switch", "git am", "git clean")


@dataclass(frozen=True)
class _Target:
    """Where a shell write lands, relative to the workspace root."""

    kind: str  # file | dir (a directory or the root) | glob
    rel: str | None  # the file or directory; None for the root and for a glob
    files: tuple[str, ...]  # the tracked and base files it may cover
    certain: tuple[str, ...]  # those the shell certainly expands it to (all of them, unless a glob)


def _glob_pattern(pattern: str) -> str:
    return pattern.replace("[^", "[!")  # the shell's negated class, in fnmatch's spelling


def _shell_glob(path: str, pattern: str) -> bool:
    """Whether the shell (no globstar, no dotglob) expands ``pattern`` to ``path``: per path segment, no leading dot."""
    ps, qs = path.split("/"), _glob_pattern(pattern).split("/")
    return len(ps) == len(qs) and all(fnmatch.fnmatchcase(p, q) and (q.startswith(".") or not p.startswith("."))
                                      for p, q in zip(ps, qs, strict=True))


class _Replay:
    def __init__(self, base: BaseTree, paths: PathMap | None, extras: Mapping[int, RawExtra], sandboxed: tuple[str, ...]):
        self.base, self.paths, self.extras, self.sandboxed = base, paths, extras, sandboxed
        self.files: dict[str, str | None] = {}
        self.status: dict[str, str] = {}
        self.changed: set[str] = set()
        self.findings: list[Finding] = []
        self.counts: Counter = Counter()

    # -- state -------------------------------------------------------------
    def get(self, rel: str) -> str | None | _U:
        if self.status.get(rel) == "unknown":
            return UNKNOWN
        return self.files[rel] if rel in self.files else self.base.get(rel)

    def put(self, rel: str, text: str | None, status: str | None = None, change: bool = True) -> None:
        """Set a file's content; ``status`` None keeps the current one (exact for an untouched file)."""
        self.files[rel] = text
        self.status[rel] = status or (self.status.get(rel) if self.status.get(rel) != "unknown" else None) or "exact"
        if change:
            self.changed.add(rel)

    def lose(self, rel: str, change: bool = True) -> None:
        self.files.pop(rel, None)
        self.status[rel] = "unknown"
        if change:
            self.changed.add(rel)

    def note(self, check: str, ev: Event, rel: str | None = None, detail: str = "") -> None:
        self.counts[check] += 1
        self.findings.append(Finding(check, ev.event_id, rel, detail))

    def _extra(self, ev: Event | None) -> RawExtra:
        return self.extras.get(ev.source.line, RawExtra()) if ev is not None else RawExtra()

    def rel(self, ev: Event, key: str = "file_path") -> str | None:
        p = (ev.tool_input or {}).get(key)
        return self.paths.rel(p, self._extra(ev).cwd) if self.paths and isinstance(p, str) else None

    def known_files(self) -> set[str]:
        """Every tracked path (written, deleted, recovered or lost) and every base file."""
        return set(self.files) | set(self.status) | self.base.files()

    def under(self, rel: str) -> list[str]:
        """Tracked and base files below ``rel`` when it names a directory."""
        pre = rel.rstrip("/") + "/"
        return sorted(p for p in self.known_files() if p.startswith(pre))

    # -- steps -------------------------------------------------------------
    def edit(self, ev: Event, res: Event | None) -> None:
        self.counts["edit_calls"] += 1
        rel = self.rel(ev)
        outcome = _outcome(res)
        if rel is None or outcome != "ok":
            self.counts["edit_outside_root" if rel is None else f"edit_{outcome}"] += 1
            if rel is not None and outcome == "missing":
                self.note("no_tool_result", ev, rel)
                self.lose(rel)
            return
        tur = self._extra(res).tool_use_result
        tur = tur if isinstance(tur, dict) else {}
        orig, cur = tur.get("originalFile"), self.get(rel)
        if isinstance(orig, str):
            self.counts["original_file_checks"] += 1
            if cur is UNKNOWN:
                self.counts["recovered_from_original_file"] += 1
                self.put(rel, orig, "recovered", change=False)
            elif cur == orig:
                self.counts["original_file_matches"] += 1
            else:
                self.note("original_file_mismatch", ev, rel)
                self.put(rel, orig, "recovered", change=False)
            cur = orig
        approx = bool(tur.get("userModified"))
        if approx:
            self.note("user_modified", ev, rel)
        if ev.tool_name == "Write":
            content = (ev.tool_input or {}).get("content")
            if not isinstance(content, str):
                self.note("unreadable_input", ev, rel)
                self.lose(rel)
                return
            self.counts["writes_applied"] += 1
            self.put(rel, content, "approximate" if approx else "exact")
            return
        if cur is UNKNOWN:
            self.note("unknown_base", ev, rel)
            self.lose(rel)
            return
        out = apply_edits(cur, edits_of(str(ev.tool_name), ev.tool_input))  # the edit function reconstruction.py uses
        for note in out.notes:  # quote_normalised, line_endings_converted
            self.note(note, ev, rel)
        if out.text is None:
            why = out.problem
            self.note(f"old_string_{why}" if why in ("absent", "not_unique") else f"edit_{why}", ev, rel)
            self.lose(rel)
            return
        self.counts["edits_applied"] += 1
        self.put(rel, out.text, "approximate" if approx or out.notes else None)

    def read(self, ev: Event, res: Event | None) -> None:
        rel = self.rel(ev)
        if rel is None or res is None:
            return
        cur = self.get(rel)
        if _outcome(res) != "ok":
            if "does not exist" in res.text and isinstance(cur, str):
                self.note("read_missing_file", ev, rel)
                self.put(rel, None, "recovered", change=False)
            return
        view = read_view(res, self._extra(res).tool_use_result)
        if view is None:
            self.counts["read_unchecked"] += 1
            return
        start, lines, full = view
        if cur is UNKNOWN or cur is None:
            if cur is None:
                self.note("read_absent_from_base", ev, rel)
            if full:
                self.counts["recovered_from_read"] += 1
                self.put(rel, "\n".join(lines), "recovered", change=False)
            elif cur is None:
                self.lose(rel, change=False)
            else:
                self.counts["read_unchecked"] += 1
            return
        self.counts["read_checks"] += 1
        have = cur.replace("\r\n", "\n")
        if (have == "\n".join(lines)) if full else (have.split("\n")[start - 1:start - 1 + len(lines)] == lines):
            self.counts["read_matches"] += 1
            return
        self.note("read_mismatch", ev, rel, f"lines {start}-{start + len(lines) - 1}")
        if full:
            self.put(rel, "\n".join(lines), "recovered", change=False)
        else:
            self.lose(rel, change=False)

    def shell(self, ev: Event, res: Event | None) -> None:
        self.counts["shell_calls"] += 1
        cmd = (ev.tool_input or {}).get("command")
        if _outcome(res) == "rejected" or (res is not None and res.text.lstrip().startswith("<tool_use_error>")) \
                or not isinstance(cmd, str) or self.paths is None:
            return
        pm = self.paths
        cwd = _cd_target(cmd, self._extra(ev).cwd, pm)

        def content(p: str) -> str | None:
            r = pm.rel(p, cwd)
            v = self.get(r) if r else None
            return v if isinstance(v, str) else None

        def known(p: str) -> bool:
            r = pm.rel(p, cwd)
            return r is not None and isinstance(self.get(r), str)

        for w in shell_writes(cmd, shell=str(ev.tool_name), sandboxed=self.sandboxed, script=content, known=known):
            placed = self.place(w, cwd)
            if placed is None:
                self.note("shell_write_unresolved", ev, None, w.kind)
            elif isinstance(placed, _Target):
                self.apply_shell(ev, placed, w, cwd)
            else:  # "outside"
                self.counts["shell_write_outside_root"] += 1

    def place(self, w: ShellWrite, cwd: str | None) -> _Target | str | None:
        """Where a shell write lands, ``"outside"`` the root, or None if it cannot be placed at all.

        A target with a variable or ``~`` cannot be placed unless it certainly lies outside. A glob
        may cover every tracked and base file that ``fnmatch`` matches against the whole path (its
        ``*`` also matches ``/``); the shell certainly expands it to those it matches segment by
        segment, without a leading dot, or else leaves it as its literal path. A directory, or the
        root, covers every tracked and base file under it. A work-tree git command without a path
        (``reset --hard``, ``stash``, a branch switch, ...) covers the root.
        """
        pm, target = self.paths, w.target
        if pm is None:
            return None
        root = pm.root.rstrip("/")
        everything = tuple(sorted(self.known_files()))
        if target is None:
            if w.kind not in _WORK_TREE:
                return None
            outside = cwd is not None and pm.rel(cwd) is None and not self._same(cwd, root)
            return "outside" if outside else _Target("dir", None, everything, everything)
        if _VARIABLE.search(target):
            return "outside" if self._outside(target, cwd) else None
        if _GLOB.search(target):
            if self._outside(target, cwd):
                return "outside"
            fold = str.lower if pm.windows else str
            pat = fold(_glob_pattern(pm.absolute(target, cwd)))
            loose = tuple(p for p in everything if fnmatch.fnmatchcase(fold(f"{root}/{p}"), pat))
            certain = tuple(p for p in loose if _shell_glob(fold(f"{root}/{p}"), pat))
            literal = pm.rel(target, cwd)
            if not certain and literal in everything:
                certain = (literal,)
            return _Target("glob", None, tuple(sorted({*loose, *certain})), certain)
        rel = pm.rel(target, cwd)
        if rel is None:
            return _Target("dir", None, everything, everything) if self._same(pm.absolute(target, cwd), root) else "outside"
        below = tuple(self.under(rel))
        return _Target("dir", rel, below, below) if below else _Target("file", rel, (rel,), (rel,))

    def _same(self, a: str, b: str) -> bool:
        a, b = norm_path(a).rstrip("/"), norm_path(b).rstrip("/")
        return a.lower() == b.lower() if self.paths is not None and self.paths.windows else a == b

    def apply_shell(self, ev: Event, t: _Target, w: ShellWrite, cwd: str | None) -> None:
        if w.kind == "rmdir":
            return  # rmdir removes only empty directories (and fails on a file): no known file changes
        covered = t.files
        if w.kind in DELETIONS:
            for p in t.certain:
                if p in self.files or self.base.get(p) is not None or self.status.get(p):
                    self.counts["shell_deletes_replayed"] += 1
                    self.put(p, None)
            covered = tuple(p for p in t.files if p not in t.certain)  # a glob may also reach these: lost below
        elif t.kind == "file" and t.rel is not None:
            self.write_file(ev, t.rel, w, cwd)
            return
        elif t.kind == "dir" and w.kind in COPIES and w.source:  # cp or mv of one source into a directory
            dst = posixpath.join(t.rel or "", posixpath.basename(norm_path(w.source).rstrip("/")))
            if not self.under(dst):
                self.write_file(ev, dst, w, cwd)
                return
            covered = tuple(self.under(dst))  # a directory copied over a directory: any file under it may change
        if t.kind == "glob" and not t.files:
            self.counts["shell_write_glob_no_match"] += 1  # a glob that matches no known file: none of them changes
        for p in covered:  # a directory, the root or a glob: any file under it may have changed
            self.note("shell_write", ev, p, w.kind)
            self.lose(p)

    def _source(self, w: ShellWrite, cwd: str | None) -> tuple[str, str] | None:
        """``(rel, content)`` of the one known source file of a copy or move."""
        if w.kind not in COPIES or not w.source or self.paths is None:
            return None
        r = self.paths.rel(w.source, cwd)
        v = self.get(r) if r else None
        return (r, v) if r is not None and isinstance(v, str) else None

    def write_file(self, ev: Event, rel: str, w: ShellWrite, cwd: str | None) -> None:
        """A shell write onto one file: a heredoc and a copy of a known file are replayed, anything else loses it."""
        if w.content is not None:  # cat > f <<'EOF'
            prev = self.get(rel)
            if w.append and prev is UNKNOWN:
                self.note("shell_write", ev, rel, w.kind)
                self.lose(rel)
                return
            self.counts["heredoc_writes_replayed"] += 1
            if not w.exact:
                self.note("heredoc_may_expand", ev, rel)
            status = "approximate" if not w.exact else None if w.append else "exact"  # an append keeps the status
            self.put(rel, ((prev if isinstance(prev, str) else "") + w.content) if w.append else w.content, status)
            return
        src = self._source(w, cwd)
        if src is not None:
            self.counts["shell_copies_replayed"] += 1
            st = self.status.get(src[0])
            self.put(rel, src[1], st if st in ("recovered", "approximate") else "exact")
            return
        self.note("shell_write", ev, rel, w.kind)
        self.lose(rel)

    def _outside(self, target: str, cwd: str | None) -> bool:
        """Whether a target with a variable or glob certainly lies outside the root."""
        if _TEMP_VARS.match(target):
            return True
        head = re.split(r"[$%*?`\[]", target, maxsplit=1)[0]
        if not head or head.startswith("~") or not _is_abs(norm_path(head)) or self.paths is None:
            return False
        q, root = self.paths.absolute(head, cwd).lower().rstrip("/"), self.paths.root.lower().rstrip("/")
        return not (q + "/").startswith(root + "/") and not (root + "/").startswith(q + "/")

    def subagent(self, ev: Event) -> None:
        kind = (ev.tool_input or {}).get("subagent_type")
        if kind in READ_ONLY_SUBAGENTS:
            self.counts["subagents_read_only"] += 1
        else:
            self.note("subagent_unseen_edits", ev, None, str(kind or "general")[:40])


def second_user_prompt(session: Session) -> str | None:
    """Event id of the second user prompt (the first that can carry a correction), if any."""
    prompts = session.user_prompts()
    return prompts[1].event_id if len(prompts) > 1 else None


def replay_session(session: Session, *, base: Path | Mapping[str, str] | None = None, root: str | None = None,
                   extras: Mapping[int, RawExtra] | None = None, stop_before: str | None = None,
                   commit_tree: Path | Mapping[str, str] | None = None,
                   sandboxed_commands: tuple[str, ...] = (), redact: Callable[[str], str] | None = None) -> ReplayResult:
    """Replay the main agent's file edits onto ``base`` and check them against the transcript.

    ``extras`` are the raw fields from :func:`load_raw_extras`; ``stop_before`` is the event id at
    which to stop (e.g. :func:`second_user_prompt`); ``commit_tree`` is the tree that the full
    replay should equal; ``sandboxed_commands`` names commands that cannot write the workspace;
    ``redact`` is the sanitiser's redaction, applied to every base text (:class:`BaseTree`).
    Sidechain (subagent) events are skipped: only the main agent's calls are replayed.
    """
    tree = BaseTree(base, redact)
    root = root or infer_root(session, base_files=tree.files())
    paths = PathMap(norm_path(root)) if root else None
    r = _Replay(tree, paths, extras or {}, sandboxed_commands)
    events = [e for e in session.events if not e.is_sidechain]
    results = {e.tool_call_id: e for e in events if e.kind == EventKind.tool_result and e.tool_call_id}
    stop_ref = None
    for ev in events:
        if stop_before and ev.event_id == stop_before:
            stop_ref = ev.event_id
            break
        if ev.kind != EventKind.tool_call:
            continue
        res = results.get(ev.tool_call_id)
        if ev.tool_name in EDIT_TOOLS:
            r.edit(ev, res)
        elif ev.tool_name == "Read":
            r.read(ev, res)
        elif ev.tool_name in SHELL_TOOLS:
            r.shell(ev, res)
        elif ev.tool_name in ("Agent", "Task"):
            r.subagent(ev)
        elif ev.tool_name == "NotebookEdit" and _outcome(res) == "ok" and (rel := r.rel(ev, "notebook_path")):
            r.note("unsupported_tool", ev, rel, "NotebookEdit")
            r.lose(rel)
    if commit_tree is not None:
        _compare_commit(r, BaseTree(commit_tree), events[-1].event_id if events else "")
    fidelity, reasons = _verdict(r, paths)
    return ReplayResult(METHOD, fidelity, reasons, paths.root if paths else None, dict(r.files), dict(r.status),
                        r.findings, r.counts, stop_ref, tree.known, sorted(r.changed))


def _compare_commit(r: _Replay, commit: BaseTree, ref: str) -> None:
    """Compare the full replayed tree (base plus replayed files) with a commit tree."""
    for p in sorted(commit.files() | r.base.files() | set(r.status)):
        have = r.get(p)
        if have is UNKNOWN:
            continue
        r.counts["commit_tree_checks"] += 1
        if have != commit.get(p):
            r.counts["commit_tree_mismatches"] += 1
            r.findings.append(Finding("commit_tree_mismatch", ref, p))


# (count key, reason text, makes the replay unreconstructable on its own)
_REASONS = (
    ("unknown_base", "edit(s) on content the transcript does not show", False),
    ("old_string_absent", "edit(s) whose old_string is absent from the replayed file", False),
    ("old_string_not_unique", "edit(s) whose old_string is not unique in the replayed file", False),
    ("edit_file_missing", "edit(s) of a file the replay does not have", False),
    ("edit_file_exists", "edit(s) that create a file the replay already has", False),
    ("shell_write", "shell write(s) onto replayed or base files", False),
    ("read_mismatch", "Read result(s) that disagree with the replayed state", False),
    ("read_absent_from_base", "Read(s) of files the replayed tree does not have (absent from the base)", False),
    ("read_missing_file", "Read(s) that report a replayed file missing", False),
    ("no_tool_result", "edit call(s) without a tool result", False),
    ("unsupported_tool", "notebook edit(s) not replayed", False),
    ("original_file_mismatch", "originalFile value(s) that disagree with the replayed file", False),
    ("shell_write_unresolved", "shell write(s) whose target could not be resolved", False),
    ("subagent_unseen_edits", "subagent call(s) whose edits are not in the transcript", False),
    ("quote_normalised", "edit(s) matched only after quote normalisation", False),
    ("line_endings_converted", "edit(s) with converted line endings", False),
    ("user_modified", "edit(s) the user modified before accepting", False),
    ("heredoc_may_expand", "heredoc write(s) whose content the shell may expand", False),
    ("commit_tree_mismatches", "file(s) that differ from the linked commit tree", True),
)


def _verdict(r: _Replay, paths: PathMap | None) -> tuple[Fidelity, list[str]]:
    hard: list[str] = []
    if paths is None:
        hard.append("no workspace root: the session's file paths could not be placed")
    if not r.base.known:
        hard.append("no base tree: the initial repository state is not in the session")
    st = Counter(r.status.values())
    if st["unknown"]:
        hard.append(f"{st['unknown']} replayed file(s) with an unknown post-image")
    soft = [f"{r.counts[k]} {text}" for k, text, _ in _REASONS if r.counts.get(k)]
    hard += [f"{r.counts[k]} {text}" for k, text, fatal in _REASONS if fatal and r.counts.get(k)]
    if st["recovered"]:
        soft.append(f"{st['recovered']} file(s) rest on content recovered from originalFile or a full Read")
    if st["approximate"]:
        soft.append(f"{st['approximate']} file(s) rest on an edit matched only after normalisation (quotes, line "
                    "endings), an edit the user modified, or a heredoc the shell may expand")
    if hard:
        return Fidelity.unreconstructable, list(dict.fromkeys(hard + soft))
    return (Fidelity.approximate, soft) if soft else (Fidelity.exact, [])


def compare_files(result: ReplayResult, expected: Mapping[str, str | None], base: Path | Mapping[str, str] | None = None,
                  redact: Callable[[str], str] | None = None) -> dict[str, dict[str, str]]:
    """Compare replayed post-images with expected ones (a captured state, a candidate's post-images).

    One entry per path in either set: ``verdict`` (match or differs), the replay ``status`` and,
    for a difference, a ``reason`` that names the findings on that path. ``redact`` is applied to
    the base texts, as in :func:`replay_session`; ``expected`` must already be redacted the same way.
    """
    tree = BaseTree(base, redact)
    out: dict[str, dict[str, str]] = {}
    for p in sorted(set(expected) | set(result.status)):
        want = expected[p] if p in expected else tree.get(p)
        if p in result.status:
            have = UNKNOWN if result.status[p] == "unknown" else result.files.get(p)
        else:
            have = tree.get(p)
        status = result.status.get(p, "base")
        if have is not UNKNOWN and have == want:
            out[p] = {"verdict": "match", "status": status}
            continue
        why = [f"{f.check} at {f.ref.rsplit('/', 1)[-1]}" + (f" ({f.detail})" if f.detail else "")
               for f in result.findings if f.path == p]
        if have is UNKNOWN:
            why.insert(0, "post-image unknown to the replay")
        elif p not in result.status:
            why.insert(0, "changed in the expected state, but no replayed step touches it")
        out[p] = {"verdict": "differs", "status": status, "reason": "; ".join(why) or "content differs"}
    return out


def sanitized(text: str) -> str:
    """The ``sanitize:v2`` redaction of a controlled transcript (e-mail addresses replaced), for base and captured texts."""
    from .claude_code import _redact_emails  # the sanitiser's own function

    return _redact_emails(text, {})


def replay_controlled(task_dir: Path, repo_root: Path, snapshot_root: Path) -> dict[str, Any]:
    """Replay a controlled session up to its second user prompt and compare the result with the
    post-images of the task's pre-correction candidate (decision log D47).

    The transcript was sanitised (``sanitize:v2``), so the base and the post-images get the same
    redaction (:func:`sanitized`), as in :mod:`tracecontract.reconstruction`. Returns the replay
    summary and one :func:`compare_files` entry per file.
    """
    from ..schemas import Candidate, Population, TaskManifest
    from ..snapshot import post_images
    from ..store import load
    from .claude_code import parse_claude_code_jsonl

    m = load(task_dir / "task.json", TaskManifest)
    rel = f"data/controlled/transcripts/{m.task_id}.jsonl"
    session = parse_claude_code_jsonl(repo_root / rel, population=Population.controlled, source="controlled:tracecontract",
                                      relpath=rel, scripted_turns=m.scripted_turns)
    base = snapshot_root / m.task_id
    res = replay_session(session, base=base, stop_before=second_user_prompt(session),
                         sandboxed_commands=CONTROLLED_SANDBOXED, redact=sanitized)
    cand = load(task_dir / "candidates" / f"{m.task_id}-pre-correction.json", Candidate)
    expected = {p: (None if b is None else sanitized(b.decode("utf-8", errors="surrogateescape")))
                for p, b in post_images(cand.patch, base).items()}
    files = compare_files(res, expected, base, sanitized)
    return {"task_id": m.task_id, "candidate_id": cand.candidate_id, "stop_ref": res.stop_ref, "replay": res.summary(),
            "files": files, "matches": sorted(p for p, v in files.items() if v["verdict"] == "match"),
            "differs": sorted(p for p, v in files.items() if v["verdict"] == "differs")}
