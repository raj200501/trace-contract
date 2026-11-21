"""Reconstruction (leakage) check: is the base snapshot the state the session started from?

``snapshot.leakage_check``, as :func:`tasks.compile_controlled_task` calls it, gets no
``reference_base``, so it compares the base with itself: a changed file would be flagged
only if its post-image differed from the base and equalled it at once. As called, it can
flag only a ``.git`` directory, and it passes when the base already holds the solution.
This module checks the base against what the session itself recorded, using only material
in the repository:

* the sanitised transcript (``data/<population>/transcripts/<id>.jsonl``): Edit, MultiEdit
  and Write calls with their results; file contents returned by Read, by Grep ``-n`` and by
  plain ``cat``, ``cat -n``, ``sed -n 'A,Bp'`` and ``head -n`` commands; and the Bash
  commands, classified conservatively for writes (:func:`bash_effects`);
* the captured states, as candidate patches (``<id>-pre-correction``, ``<id>-reference``);
* the base snapshot (``snapshots/<id>``), used only if its manifest equals ``snapshot.json``;
* the start-of-session manifest that :func:`controlled.prepare_workspace` recorded
  (``provenance.json`` notes: ``workspace_snapshot_manifest``), workspace records the
  session printed, and the overlays in ``task.json``.

Checks (each has a status, ``passed``, ``failed``, ``not_checkable`` or ``unavailable``, and
reasons; a data problem never raises):

a. every file the session wrote through Edit, MultiEdit or Write differs between the base
   and the final state, or the replay explains why it does not (a revert);
b. at each file's first edit, and at its first edit after a restore to the base,
   ``old_string`` occurs in the base as the Edit tool requires (once, unless
   ``replace_all``) and ``new_string`` does not occur outside it; a Write's "created" or
   "updated" result agrees with the file's absence or presence in the base;
c. file contents the session saw while a file was in its base state equal the base;
d. the rebuilt base manifest equals the start-of-session manifest after overlays;
e. the base holds no ``.git``, ``__pycache__``, ``.pyc``/``.pyo``, ``.orig``, ``.rej``, ``*~``
   or ``*.bak`` copy of a changed module;
f. (additional) replaying the session's writes on the base reproduces the captured
   pre-correction and final states, the session's later reads and the Edit tool's own
   error messages, and every file those states change was written by the session.

The result is also rolled up per changed file (``Report.files``): every file that the
reference or pre-correction patch changes, or that the session edited through Edit, MultiEdit
or Write, needs at least one passed item in check (b) or (c), that is, the session's own record
attests its base content. Otherwise the report is ``incomplete`` and names the file, even when
every check passed on other files: a leaked file can hide behind items that are only
``not_checkable``.

Edits are replayed with the Edit tool's semantics, through the same function as
:mod:`tracecontract.ingest.replay` (:mod:`tracecontract.ingest.edit_tool`). A Bash command that
may write files the replay cannot follow makes those files ``not_checkable`` from then on;
``git checkout``/``restore`` of paths, ``git stash`` and ``git reset --hard`` reset only files
present in the base, and keep the files the session created, as git does. Commands run through
the study's sandbox wrappers (``run_tests.sh``, ``run_python.sh``) mount the repository read-only
and write nothing in it. Transcripts were sanitised (``sanitize:v2`` replaced e-mail addresses),
so every comparison applies the same redaction to the base and to the captured states.

:func:`recorded_check` compares a task's ``reconstruction_check.json`` with the current files,
for the acceptance gate and the pre-flight (protocol v0.8 §16.5).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .ingest.claude_code import _redact_emails  # the sanitizer's own redaction (sanitize:v2)
from .ingest.edit_tool import actual_old_string, apply_edits, edits_of, preserve_quote_style
from .schemas import Candidate, CandidateOrigin, EventKind, Session, Snapshot, TaskManifest, sha256_bytes, sha256_text
from .snapshot import manifest, manifest_sha256, post_images

# v2: the roll-up per changed file, the edit function shared with ingest/replay.py, restores
# that keep the session's own files, here-strings (v1 records do not count for the gate)
METHOD = "reconstruction:v2"
RECORD = "reconstruction_check.json"  # tasks/<id>/reconstruction_check.json
PASSED, FAILED, NOT_CHECKABLE, UNAVAILABLE, EXPLAINED = "passed", "failed", "not_checkable", "unavailable", "explained"
TITLES = {
    "a_written_files_changed": "Files written through Edit/MultiEdit/Write differ between base and final state, or are explained",
    "b_first_edit_strings": "At each first edit from the base, old_string is in the base and new_string is not",
    "c_reads_match_base": "File contents the session saw while a file was in its base state equal the base",
    "d_start_manifest": "The rebuilt base manifest equals the start-of-session manifest after overlays",
    "e_no_stale_copies": "No .git, __pycache__, .pyc, .orig, .rej or backup copy of a changed module in the base",
    "f_replay_matches_states": "Replaying the session's writes on the base reproduces the captured states (additional)",
}
VACUOUS_NOTE = ("tasks.compile_controlled_task calls leakage_check(base, ref.patch) without reference_base, so the "
                "snapshot and the reference base are the same directory: a changed file would have to differ from the "
                "base and equal it at once. As recorded, the check can flag only a .git directory, which a git archive "
                "export does not have; it passes even when the base already holds the solution.")
_BASH_OUTPUT_LIMIT = 29_000  # Bash results near the tool's output limit may be truncated
_LONG_LINE = 2000  # the Read tool truncates longer lines


# --------------------------------------------------------------------------- results


@dataclass
class Check:
    check_id: str
    status: str
    reason: str
    items: list[dict] = field(default_factory=list)
    approximations: list[str] = field(default_factory=list)
    title: str = ""

    def __post_init__(self) -> None:
        self.title = self.title or TITLES.get(self.check_id, self.check_id)


@dataclass
class Report:
    task_id: str
    status: str  # passed | failed | incomplete
    passed: bool | None  # None: nothing failed, but not every check could run or not every changed file is attested
    checks: list[Check]
    inputs: dict = field(default_factory=dict)
    bash_effects: list[dict] = field(default_factory=list)
    legacy_leakage_check: dict | None = None
    notes: list[str] = field(default_factory=list)
    method: str = METHOD
    files: list[dict] = field(default_factory=list)  # the roll-up per changed file (_file_rollup)

    def check(self, check_id: str) -> Check:
        return next(c for c in self.checks if c.check_id == check_id)

    def to_dict(self) -> dict:
        return asdict(self)


def _rollup(check_id: str, items: list[dict], empty: str, approximations: list[str] | None = None) -> Check:
    """A check's status from its items: failed if any failed, else passed if any passed or was explained."""
    n = Counter(i["status"] for i in items)
    if n[FAILED]:
        status, reason = FAILED, f"{n[FAILED]} of {len(items)} item(s) failed"
    elif n[PASSED] or n[EXPLAINED]:
        status = PASSED
        reason = f"{n[PASSED] + n[EXPLAINED]} item(s) passed" + (f" ({n[EXPLAINED]} explained)" if n[EXPLAINED] else "")
        reason += f"; {n[NOT_CHECKABLE]} not checkable" if n[NOT_CHECKABLE] else ""
    else:
        status, reason = NOT_CHECKABLE, empty if not items else f"none of {len(items)} item(s) could be checked"
    return Check(check_id, status, reason, items, approximations or [])


def _report(task_id: str, checks: list[Check], files: list[dict] | None = None, notes: list[str] | None = None,
            **kw) -> Report:
    """``failed`` if a check failed; ``passed`` if every check passed and every changed file is attested; else ``incomplete``."""
    files, notes = files or [], list(notes or [])
    states = {c.status for c in checks}
    unattested = [f["path"] for f in files if f["status"] != PASSED]
    status = "failed" if FAILED in states else "passed" if states == {PASSED} and not unattested else "incomplete"
    if unattested and status != "failed":
        notes.append(f"incomplete: {len(unattested)} changed file(s) have no passed item in check b or c, so the "
                     f"session's record does not attest their base content: {', '.join(unattested)}")
    return Report(task_id=task_id, status=status, passed={"failed": False, "passed": True}.get(status), checks=checks,
                  files=files, notes=notes, **kw)


def unavailable_report(task_id: str, reason: str, **kw) -> Report:
    return _report(task_id, [Check(cid, UNAVAILABLE, reason) for cid in TITLES], **kw)


# --------------------------------------------------------------------------- text helpers


def _redact(text: str) -> str:
    return _redact_emails(text, {})


def _decode(data: bytes) -> str:
    return _redact(data.decode("utf-8", errors="surrogateescape"))


def _rel(path: str, ws: str) -> str | None:
    """``path`` relative to the workspace root ``ws`` ('.' for the root itself), or None outside it."""
    p = os.path.normpath(path) if path else ""
    if p == ws:
        return "."
    return p[len(ws) + 1:] if p.startswith(ws + "/") else None


def _occurrences(text: str, sub: str, *, overlapping: bool = True) -> list[int]:
    """Start offsets of every occurrence of ``sub``; non-overlapping ones are those ``str.count`` counts."""
    out, i = [], text.find(sub) if sub else -1
    while i >= 0:
        out.append(i)
        i = text.find(sub, i + (1 if overlapping else len(sub)))
    return out


def _tool_view(text: str, old: str) -> str:
    """The content the Edit tool matches ``old`` against: a CRLF file read with LF line breaks (edit_tool.apply_edits)."""
    return text.replace("\r\n", "\n") if "\r\n" in text and "\r" not in old else text


def _compare_lines(expected: str | None, lines: dict[int, str]) -> list[dict]:
    """Mismatches of observed ``{line number: text}`` against ``expected`` (split at newlines)."""
    exp = [] if expected is None else expected.split("\n")
    bad = []
    for n, got in sorted(lines.items()):
        want = exp[n - 1] if 1 <= n <= len(exp) else None
        if want is not None and (got == want or got == want.rstrip("\r")
                                 or (len(want) > _LONG_LINE and want.startswith(got[: _LONG_LINE - 100]))):
            continue
        bad.append({"line": n, "expected": None if want is None else want[:120], "observed": got[:120]})
    return bad


def _span(lines: dict[int, str]) -> str:
    return f"{min(lines)}-{max(lines)}" if lines else ""


# --------------------------------------------------------------------------- Bash commands


@dataclass
class BashEffect:
    """What one Bash command may have done to workspace files.

    ``action``: ``restore`` (the base files under the paths reset to the base, e.g. ``git checkout
    -- p``; files the session created are kept, as git keeps untracked files), ``write`` (paths now
    unknown), ``write_any`` (targets unknown: every file becomes unknown) or ``head_moved``
    (``git add``/``commit``: later restores no longer give the base). Paths are
    workspace-relative; ``.`` or a directory covers the files below it.
    """

    event_id: str
    action: str
    paths: list[str]
    reason: str


@dataclass
class _Cmd:
    words: list[str]
    writes_to: list[str]
    heredocs: list[str]
    piped_in: bool = False


_PUNCT = set("();<>|&")
_REDIRECTS = {">", ">>", ">|", "&>", "&>>", "<>", ">&", "<", "<<", "<<-", "<<<", "<&"}
_HEREDOC_START = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([^\s'\";&|<>()]+)\2")  # not a here-string (<<<)
_SANDBOX = {"run_tests.sh", "run_python.sh"}  # docker run ... -v <repo>:/repo:ro (controlled.RUN_TESTS_SH)
_KEYWORDS = {"{", "}", "!", "do", "then", "else", "elif", "if", "while", "until", "time", "done", "fi", "esac", "function"}
_LOOP_HEADERS = {"for", "case", "select"}
_WRAPPERS = {"env", "timeout", "nice", "nohup", "stdbuf", "exec", "builtin", "ionice", "sudo", "command", "xargs"}
_READ_ONLY = {
    "cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "ls", "tree", "du", "df", "wc", "file", "stat",
    "diff", "cmp", "comm", "cut", "tr", "nl", "tac", "rev", "column", "fold", "paste", "fmt", "expand", "base64", "xxd",
    "od", "hexdump", "strings", "md5sum", "sha1sum", "sha256sum", "sha512sum", "cksum", "jq", "realpath", "readlink",
    "basename", "dirname", "pwd", "which", "type", "whoami", "id", "uname", "date", "printenv", "echo", "printf", "true",
    "false", "test", "[", "[[", "sleep", "seq", "expr", "bc", "awk", "gawk", "mawk", "mktemp", "mkdir", "rmdir", "chmod",
    "chown", "export", "local", "declare", "readonly", "typeset", "unset", "set", "shopt", "alias", "read", "exit",
    "return", "break", "continue", "wait", "trap", ":", "pyright", "flake8", "pycodestyle", "pyflakes", "pylint", "hash",
}
_FILE_WRITERS = {"tee", "touch", "truncate", "rm", "unlink", "mv", "cp", "ln", "install", "rsync", "shred", "split"}
_GIT_READ_ONLY = {"status", "log", "diff", "show", "ls-files", "ls-tree", "rev-parse", "blame", "grep", "cat-file",
                  "describe", "shortlog", "reflog", "help", "version", "whatchanged", "name-rev", "merge-base",
                  "for-each-ref", "count-objects", "rev-list", "show-ref", "var", "check-ignore", "check-attr", "fetch",
                  "diff-files", "diff-index", "diff-tree", "range-diff", "annotate", "branch", "tag", "remote", "config"}
_PY_WRITE = re.compile(r"\.write_(?:text|bytes)\(|\bopen\([^)]*?['\"][rbt]*[wax+][rbt+]*['\"]|\.(?:unlink|rename|touch|rmdir)\("
                       r"|\bos\.(?:remove|unlink|rename|replace|rmdir|truncate)\(|\bshutil\.(?:move|copy\w*|rmtree)\("
                       r"|\bsubprocess\b|\bos\.system\(")
_PY_DYNAMIC = re.compile(r"\b(?:glob|rglob|os\.walk|listdir|scandir|iterdir)\b")
_PY_READ_ONLY_MODULES = {"json.tool", "tokenize", "pydoc", "this", "platform", "sysconfig", "site"}
_VAR = re.compile(r"\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)")


def _normalize(cmd: str) -> tuple[str, list[str]]:
    """The command without heredoc bodies, comments and line continuations, unquoted newlines as ``;``.

    Returns that text and the heredoc bodies, in the order of their ``<<`` operators.
    """
    out: list[str] = []
    bodies: list[str] = []
    pending: list[tuple[str, bool]] = []
    i, q, n = 0, None, len(cmd)
    while i < n:
        c = cmd[i]
        if q:
            out.append(c)
            if c == "\\" and q == '"' and i + 1 < n:
                out.append(cmd[i + 1])
                i += 2
                continue
            q = None if c == q else q
            i += 1
        elif c == "\\" and i + 1 < n:
            out += [] if cmd[i + 1] == "\n" else [c, cmd[i + 1]]
            i += 2
        elif c in "'\"":
            q = c
            out.append(c)
            i += 1
        elif c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|("):
            while i < n and cmd[i] != "\n":
                i += 1
        elif (cmd.startswith("<<", i) and not cmd.startswith("<<<", i) and (i == 0 or cmd[i - 1] != "<")
              and _HEREDOC_START.match(cmd, i)):  # the second '<' of a here-string '<<<' starts no heredoc
            m = _HEREDOC_START.match(cmd, i)
            pending.append((m.group(3), bool(m.group(1))))
            out.append(f" << {m.group(3)} ")
            i = m.end()
        elif c == "\n":
            out.append(" ; ")
            i += 1
            for delim, tabs in pending:
                body = []
                while i < n:
                    j = cmd.find("\n", i)
                    j = n if j < 0 else j
                    line, i = cmd[i:j], j + 1
                    if (line.lstrip("\t") if tabs else line) == delim:
                        break
                    body.append(line)
                bodies.append("\n".join(body))
            pending = []
        else:
            out.append(c)
            i += 1
    bodies += ["" for _ in pending]  # a heredoc on the last line has no body
    return "".join(out), bodies


def _simple_commands(cmd: str) -> list[_Cmd] | None:
    """The simple commands of a shell command line, or None if it cannot be tokenized."""
    text, bodies = _normalize(cmd)
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        toks = list(lex)
    except ValueError:
        return None
    feed = iter(bodies)
    cmds: list[_Cmd] = []
    cur = _Cmd([], [], [])
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in _REDIRECTS:
            target = toks[i + 1] if i + 1 < len(toks) else ""
            if t in ("<<", "<<-"):
                cur.heredocs.append(next(feed, ""))
            elif t == "<<<":
                cur.heredocs.append(target)
            elif not t.startswith("<") and not (t == ">&" and (target.isdigit() or target == "-")):
                cur.writes_to.append(target)
            if t.startswith(">") and cur.words and cur.words[-1] in ("1", "2"):
                cur.words.pop()  # the file descriptor of "2>"
            i += 2
        elif t and set(t) <= _PUNCT:
            if cur.words or cur.writes_to or cur.heredocs:
                cmds.append(cur)
            cur = _Cmd([], [], [], piped_in="|" in t and "||" not in t)
            i += 1
        else:
            cur.words.append(t)
            i += 1
    if cur.words or cur.writes_to or cur.heredocs:
        cmds.append(cur)
    return cmds


class _Shell:
    """Follows one Bash command line: its working directory and the effects of each simple command."""

    def __init__(self, ws: str, event_id: str, known: set[str]) -> None:
        self.ws, self.eid, self.known = ws, event_id, known
        self.cwd: str | None = None  # a subagent's Bash call starts outside the workspace; unknown until `cd`
        self.vars: dict[str, list[str]] = {}  # loop variables and literal assignments, for substitution
        self.effects: list[BashEffect] = []

    def add(self, action: str, paths: list[str], reason: str) -> None:
        self.effects.append(BashEffect(self.eid, action, sorted(set(paths)), reason))

    def target(self, tok: str) -> tuple[str, str | None]:
        """('inside', rel), ('outside', None) or ('unknown', None) for a path token."""
        if not tok or "$" in tok or "`" in tok:
            return "unknown", None
        if tok.startswith(("~", "/dev/", "/proc/")):
            return "outside", None
        if not tok.startswith("/"):
            if self.cwd is None:
                return "unknown", None
            tok = os.path.join(self.cwd, tok)
        rel = _rel(tok, self.ws)
        return ("inside", rel) if rel is not None else ("outside", None)

    def is_known_path(self, rel: str | None) -> bool:
        return rel is not None and (rel == "." or rel in self.known or any(k.startswith(rel.rstrip("/") + "/") for k in self.known))

    def write(self, toks: list[str], reason: str, *, default_cwd: bool = False) -> None:
        """Record a write of the files named by ``toks`` (globs expanded over the known files)."""
        rels: list[str] = []
        for tok in toks or (["."] if default_cwd else []):
            where, rel = self.target(tok)
            if where == "unknown":
                self.add("write_any", [], f"{reason}; target {tok!r} cannot be resolved")
                return
            if where == "inside" and rel is not None:
                rels += [k for k in self.known if fnmatch.fnmatchcase(k, rel)] if any(ch in rel for ch in "*?[") else [rel]
        if rels:
            self.add("write", rels, reason)

    def run(self, cmd: str) -> None:
        parsed = _simple_commands(cmd)
        if parsed is None:
            self.add("write_any", [], "the command could not be tokenized")
            return
        for c in parsed:
            for tgt in c.writes_to:
                for (t,) in self.expand_vars([tgt]):
                    self.write([t], f"output redirection to {t!r}")
            self.simple(c)

    def expand_vars(self, words: list[str]) -> list[list[str]]:
        """``words`` once per value of the (single) known variable they use; unknown variables stay."""
        used = {m.group(1) or m.group(2) for w in words for m in _VAR.finditer(w)} & set(self.vars)
        if len(used) != 1:
            return [words]
        name = used.pop()
        return [[_VAR.sub(lambda m: v if (m.group(1) or m.group(2)) == name else m.group(0), w) for w in words]
                for v in self.vars[name]]

    def simple(self, c: _Cmd) -> None:
        words = list(c.words)
        while words and words[0] in _KEYWORDS:
            words = words[1:]
        if len(words) > 2 and words[0] == "for" and words[2] == "in":
            self.vars[words[1]] = [w for w in words[3:] if "$" not in w and "`" not in w]
            return  # the loop header lists words; the body follows as later commands
        if words and words[0] in _LOOP_HEADERS:
            return
        if words and all(re.match(r"^[A-Za-z_]\w*=", w) for w in words):
            for w in words:  # a shell variable assignment
                k, v = w.split("=", 1)
                self.vars.pop(k, None)
                if v and "$" not in v and "`" not in v:
                    self.vars[k] = [v]
            return
        while words and re.match(r"^[A-Za-z_]\w*=", words[0]):
            words = words[1:]  # an environment assignment for this command only
        variants = self.expand_vars(words)
        if len(variants) > 1 or variants[0] != words:
            for v in variants:
                self.simple(_Cmd(v, [], c.heredocs, c.piped_in))
            return
        stdin_args = False
        while words and os.path.basename(words[0]) in _WRAPPERS:
            w, words = os.path.basename(words[0]), words[1:]
            if w == "command" and words[:1] in (["-v"], ["-V"]):
                return
            stdin_args = stdin_args or w == "xargs"
            while words and (words[0].startswith("-") or (w == "env" and "=" in words[0])):
                words = words[1:]
            if w == "timeout" and words:
                words = words[1:]  # the duration
        if not words:
            return
        name, args = os.path.basename(words[0]), words[1:]
        if name in _SANDBOX or (name not in ("rm", "cp", "mv") and {"--version", "--help"} & set(args[:2])):
            return
        handlers = {"cd": self.cd, "pushd": self.cd, "git": self.git, "sh": self.shell, "bash": self.shell,
                    "zsh": self.shell, "dash": self.shell, "sed": self.sed, "perl": self.sed, "mypy": self.mypy,
                    "ruff": self.ruff, "black": self.formatter, "isort": self.formatter, "pyupgrade": self.formatter,
                    "autopep8": self.formatter, "yapf": self.formatter, "autoflake": self.formatter,
                    "docformatter": self.formatter, "find": self.find, "sort": self.sort, "uniq": self.uniq}
        if name in handlers:
            handlers[name](name, args, c)
        elif re.fullmatch(r"python[0-9.]*", name):
            self.python(name, args, c)
        elif name in _FILE_WRITERS or name == "patch":
            ops = [a for a in args if not a.startswith("-")]
            if stdin_args or (name == "patch" and not ops):
                self.add("write_any", [], f"{name} writes files named on its input")
            else:
                self.write(ops, f"{name} writes its file arguments")
        elif name == "dd":
            self.write([a[3:] for a in args if a.startswith("of=")], "dd of=")
        elif name in ("pip", "pip3", "uv") and args[:1] in (["list"], ["show"], ["freeze"], ["check"]):
            return
        elif name not in _READ_ONLY:
            self.add("write_any", [], f"unrecognised command {name!r}: may write")

    def cd(self, name: str, args: list[str], c: _Cmd | None = None) -> None:
        dest = next((a for a in args if not a.startswith("-")), None)
        if dest is None or "$" in dest:
            self.cwd = None
        elif dest.startswith("/"):
            self.cwd = os.path.normpath(dest)
        else:
            self.cwd = None if self.cwd is None else os.path.normpath(os.path.join(self.cwd, dest))

    def shell(self, name: str, args: list[str], c: _Cmd) -> None:
        code = args[args.index("-c") + 1] if "-c" in args[:-1] else None
        if code is None and c.heredocs and not [a for a in args if not a.startswith("-")]:
            code = "\n".join(c.heredocs)
        if code is None:
            self.add("write_any", [], f"{name} runs a script or input that cannot be inspected")
            return
        inner = _Shell(self.ws, self.eid, self.known)
        inner.cwd = self.cwd
        inner.run(code)
        self.effects += inner.effects

    def sed(self, name: str, args: list[str], c: _Cmd) -> None:
        if not any(a == "--in-place" or re.fullmatch(r"-[a-zA-Z]*i\S*", a) for a in args):
            return
        files = [a for a in args if not a.startswith("-")]
        if not any(a in ("-e", "-f") or a.startswith("--expression") for a in args):
            files = files[1:]  # the first operand is the script
        self.write(files, f"{name} -i edits its files in place")

    def mypy(self, name: str, args: list[str], c: _Cmd) -> None:
        if not any(a.startswith("--cache-dir") for a in args):
            self.write([".mypy_cache"], "mypy writes .mypy_cache")

    def ruff(self, name: str, args: list[str], c: _Cmd) -> None:
        if "--no-cache" not in args and not any(a.startswith("--cache-dir") for a in args):
            self.write([".ruff_cache"], "ruff writes .ruff_cache")
        ops = [a for a in args if not a.startswith("-")]
        sub, ops = (ops[0], ops[1:]) if ops else ("", [])
        writes = ((sub == "format" and not {"--check", "--diff"} & set(args))
                  or (sub == "check" and bool({"--fix", "--unsafe-fixes"} & set(args)) and "--no-fix" not in args))
        if writes:
            self.write(ops, f"ruff {sub} rewrites files", default_cwd=True)

    def formatter(self, name: str, args: list[str], c: _Cmd) -> None:
        ops = [a for a in args if not a.startswith("-")]
        if name in ("black", "isort", "pyupgrade"):
            writes = not {"--check", "--diff", "--check-only", "-c"} & set(args) and ops != ["-"]
        else:
            writes = bool({"-i", "--in-place"} & set(args))
        if writes:
            self.write(ops, f"{name} rewrites files", default_cwd=True)

    def find(self, name: str, args: list[str], c: _Cmd) -> None:
        if "-delete" in args:
            self.add("write_any", [], "find -delete")
        for flag in ("-exec", "-execdir", "-ok", "-okdir"):
            if flag in args[:-1] and os.path.basename(args[args.index(flag) + 1]) not in _READ_ONLY:
                self.add("write_any", [], f"find {flag} {args[args.index(flag) + 1]}")

    def sort(self, name: str, args: list[str], c: _Cmd) -> None:
        out = [a.split("=", 1)[1] for a in args if a.startswith("--output=")]
        out += [args[args.index("-o") + 1]] if "-o" in args[:-1] else []
        if out:
            self.write(out, "sort -o")

    def uniq(self, name: str, args: list[str], c: _Cmd) -> None:
        ops = [a for a in args if not a.startswith("-")]
        if len(ops) > 1:
            self.write(ops[1:], "uniq writes its output file")

    def python(self, name: str, args: list[str], c: _Cmd) -> None:
        if "-m" in args:
            mod = args[args.index("-m") + 1] if "-m" in args[:-1] else ""
            if mod not in _PY_READ_ONLY_MODULES:
                self.add("write_any", [], f"{name} -m {mod} on the host: may write")
            return
        if "-c" in args:
            code = args[args.index("-c") + 1] if "-c" in args[:-1] else ""
        elif c.heredocs and (not args or args[0] == "-"):
            code = "\n".join(c.heredocs)
        else:
            self.add("write_any", [], f"{name} runs a script or piped code that cannot be inspected")
            return
        if not _PY_WRITE.search(code):
            return
        if _PY_DYNAMIC.search(code):
            self.add("write_any", [], f"{name} code on the host writes files chosen at run time")
            return
        rels = [rel for where, rel in (self.target(lit) for lit in re.findall(r"['\"]([^'\"\n]{1,300})['\"]", code))
                if where == "inside" and rel != "." and self.is_known_path(rel)]
        if rels:
            self.add("write", [r for r in rels if r], f"{name} code on the host writes files it names")
        else:
            self.add("write_any", [], f"{name} code on the host may write files it does not name")

    def git(self, name: str, args: list[str], c: _Cmd) -> None:
        saved, rest = self.cwd, list(args)
        while rest and rest[0].startswith("-"):
            if rest[0] in ("-C", "-c") and len(rest) > 1:
                if rest[0] == "-C":
                    self.cd("cd", [rest[1]])
                rest = rest[2:]
            else:
                rest = rest[1:]
        try:
            self._git(rest)
        finally:
            self.cwd = saved

    def _git(self, rest: list[str]) -> None:
        sub, rest = (rest[0], rest[1:]) if rest else ("", [])
        opts = set(rest)
        if sub in _GIT_READ_ONLY:
            return
        if sub == "stash":
            op = rest[0] if rest and not rest[0].startswith("-") else "push"
            if op in ("list", "show", "drop", "clear"):
                return
            if op in ("push", "save") and not {"-u", "--include-untracked", "-a", "--all"} & opts:
                self.add("restore", ["."], "git stash resets tracked files to HEAD")
            else:
                self.add("write_any", [], f"git stash {op}")
        elif sub == "reset":
            if {"--hard", "--keep", "--merge"} & opts:
                if [a for a in rest if not a.startswith("-")] in ([], ["HEAD"]):
                    self.add("restore", ["."], "git reset --hard resets tracked files to HEAD")
                else:
                    self.add("write_any", [], "git reset --hard to another revision")
            # a soft or mixed reset changes only the index
        elif sub in ("add", "commit"):
            self.add("head_moved", [], f"git {sub}: later restores no longer give the base")
        elif sub in ("checkout", "restore"):
            self._git_restore(sub, rest)
        elif sub in ("rm", "mv"):
            if not (sub == "rm" and "--cached" in opts):
                self.write([a for a in rest if not a.startswith("-")], f"git {sub}")
        elif sub != "init":
            self.add("write_any", [], f"git {sub or '(no subcommand)'}: may write")

    def _git_restore(self, sub: str, rest: list[str]) -> None:
        if "--" in rest:
            before, ops = rest[: rest.index("--")], rest[rest.index("--") + 1:]
        else:
            before, ops = [a for a in rest if a.startswith("-")], [a for a in rest if not a.startswith("-")]
        opts = {a for a in before if a.startswith("-")}
        source = [a for a in before if not a.startswith("-")] + [a.split("=", 1)[1] for a in opts if a.startswith("--source=")]
        if sub == "restore" and {"--staged", "-S"} & opts and not {"--worktree", "-W"} & opts:
            return  # only the index
        resolved = [self.target(a) for a in ops]
        if not ops or not all(w == "inside" and self.is_known_path(r) for w, r in resolved):
            self.add("write_any", [], f"git {sub} {' '.join(rest)[:60]}: switches revision or names unknown paths")
            return
        rels = [r for _, r in resolved if r]
        if source in ([], ["HEAD"]) and not {"-p", "--patch", "-m", "--merge"} & opts:
            self.add("restore", rels, f"git {sub} resets the named paths to HEAD")
        else:
            self.add("write", rels, f"git {sub} from {source or 'a partial patch'}")


def bash_effects(command: str, workspace_root: str, *, event_id: str = "", known_files: set[str] | None = None) -> list[BashEffect]:
    """Effects of one Bash command on files in the workspace, in order (a conservative heuristic)."""
    sh = _Shell(workspace_root.rstrip("/"), event_id, known_files or set())
    sh.run(command)
    return sh.effects


# --------------------------------------------------------------------------- file contents in the transcript


def _read_tool_lines(text: str) -> dict[int, str]:
    """``{line: text}`` of a Read result (``N<TAB>line`` or ``N→line``)."""
    return {int(m.group(1)): m.group(2) for m in (re.match(r"^\s*(\d+)(?:\t|→)(.*)$", ln) for ln in text.split("\n")) if m}


def _grep_lines(tool_input: dict, text: str, ws: str, known: set[str]) -> dict[str, dict[int, str]]:
    """``{rel: {line: text}}`` from a Grep content result with line numbers (``path:N:line``, or ``N:line`` for one file)."""
    if not tool_input.get("-n") or tool_input.get("output_mode") != "content":
        return {}
    one = _rel(str(tool_input.get("path") or ""), ws)
    one = one if one in known else None
    out: dict[str, dict[int, str]] = {}
    for ln in text.split("\n"):
        m = re.match(r"^(/[^\n]*?):(\d+):(.*)$", ln)
        if m and one is None:
            rel = _rel(m.group(1), ws)
            if rel and rel != ".":
                out.setdefault(rel, {})[int(m.group(2))] = m.group(3)
        elif one is not None and (m := re.match(r"^(\d+)[:-](.*)$", ln)):
            out.setdefault(one, {})[int(m.group(1))] = m.group(2)
    return out


def _bash_read(command: str, output: str, ws: str) -> tuple[str, str, dict[int, str] | None, str | None] | None:
    """``(rel, form, numbered lines, whole text)`` for ``[cd D &&] cat|cat -n|sed -n 'A[,B]p'|head -n N FILE``."""
    cmds = _simple_commands(command)
    if not cmds or len(output) >= _BASH_OUTPUT_LIMIT:
        return None
    sh = _Shell(ws, "", set())
    for c in cmds[:-1]:
        if c.writes_to or c.heredocs or c.words[:1] != ["cd"]:
            return None
        sh.cd("cd", c.words[1:])
    last = cmds[-1]
    if last.writes_to or last.heredocs or last.piped_in or not last.words:
        return None
    name, args, lines = os.path.basename(last.words[0]), last.words[1:], output.split("\n")
    numbered: dict[int, str] | None = None
    whole: str | None = None
    if name == "cat" and len(args) == 1 and not args[0].startswith("-"):
        whole = output
    elif name == "cat" and len(args) == 2 and args[0] == "-n":
        numbered = {int(m.group(1)): m.group(2) for m in (re.match(r"^\s*(\d+)\t(.*)$", x) for x in lines) if m}
    elif name == "sed" and len(args) == 3 and args[0] == "-n" and re.fullmatch(r"\d+(,\d+)?p", args[1]):
        start = int(args[1].rstrip("p").split(",")[0])
        numbered = {start + k: x for k, x in enumerate(lines)}
    elif name == "head" and len(args) in (2, 3) and re.fullmatch(r"-n|-\d+", args[0]):
        numbered = {1 + k: x for k, x in enumerate(lines)}
    else:
        return None
    where, rel = sh.target(args[-1])
    if where != "inside" or not rel or rel == ".":
        return None
    form = "cat" if whole is not None else name + (" -n" if name in ("cat", "sed") else "")
    return rel, form, numbered, whole


# --------------------------------------------------------------------------- replay


@dataclass
class _File:
    text: str | None  # the content if known (None: absent)
    known: bool = True
    why: str = ""  # why the content is unknown
    cause: str = ""  # "bash" or "anomaly"
    base_state: bool = True  # the content is the base: never written, or restored and not written since
    restored_at: str = ""


@dataclass
class _Step:
    index: int
    event_id: str
    tool: str
    input: dict
    result: str | None
    error: bool


def _steps(session: Session) -> list[_Step]:
    results = {e.tool_call_id: e for e in session.events if e.kind == EventKind.tool_result and e.tool_call_id}
    out = []
    for e in session.events:
        if e.kind != EventKind.tool_call:
            continue
        r = results.get(e.tool_call_id) if e.tool_call_id else None
        text = None if r is None else r.text
        err = r is not None and (bool(r.is_error) or r.text.lstrip().startswith("<tool_use_error>"))
        out.append(_Step(e.index, e.event_id, e.tool_name or "?", e.tool_input or {}, text, err))
    return out


def _under(paths: list[str], files) -> list[str]:
    """The files at or below any of ``paths`` ('.' is the workspace root)."""
    return sorted({f for f in files for p in paths if p == "." or f == p or f.startswith(p.rstrip("/") + "/")})


_PROBLEMS = {"file_missing": "the file does not exist", "file_exists": "old_string is empty but the file is not",
             "absent": "old_string does not occur", "not_unique": "old_string is not unique"}


class _Replay:
    """Replays a session's file writes on the base and collects the items of checks (b), (c) and (f)."""

    def __init__(self, base: Path, ws: str, base_files: set[str], watch: set[str]) -> None:
        self.base, self.ws, self.base_files, self.watch = base, ws, base_files, watch
        self.files: dict[str, _File] = {}  # every file written so far (by a tool or by Bash)
        self.all_unknown = ""  # set by a Bash write with unknown targets
        self.head_is_base = True
        self.tool_writers: dict[str, list[str]] = {}
        self.bash_writers: dict[str, list[str]] = {}
        self.first_writes: list[dict] = []  # (b)
        self.base_reads: list[dict] = []  # (c)
        self.replay_items: list[dict] = []  # (f)
        self.effects: list[BashEffect] = []
        self.seen_lines: dict[str, set[int]] = {}  # matched base lines of watched files
        self.listed_in: dict[str, list[str]] = {}  # tool results that list a watched file
        self.manifests_shown: list[tuple[str, str]] = []
        self.approximations: list[str] = []  # edits that matched only with normalised quotes or line endings
        self._cache: dict[str, str | None] = {}

    def base_text(self, rel: str) -> str | None:
        if rel not in self._cache:
            p = self.base / rel
            self._cache[rel] = _decode(p.read_bytes()) if rel in self.base_files and p.is_file() else None
        return self._cache[rel]

    def known_files(self) -> set[str]:
        return self.base_files | set(self.files)

    def current(self, rel: str) -> _File:
        """The file's state now, without recording it as written."""
        if rel in self.files:
            return self.files[rel]
        if self.all_unknown:
            return _File(None, known=False, why=self.all_unknown, cause="bash", base_state=False)
        return _File(self.base_text(rel))

    def touch(self, rel: str) -> _File:
        self.files[rel] = self.current(rel)
        return self.files[rel]

    def unknown(self, f: _File, why: str, cause: str) -> None:
        f.text, f.known, f.why, f.cause, f.base_state, f.restored_at = None, False, why, cause, False, ""

    def snapshot(self) -> dict[str, _File]:
        return {k: _File(**asdict(v)) for k, v in self.files.items()}

    def step(self, s: _Step) -> None:
        if s.result:
            self.scan_result(s)
        if s.tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
            self.write_call(s)
        elif s.tool == "Bash":
            self.bash(s)
        elif s.tool == "Read" and not s.error and s.result is not None:
            rel = _rel(str(s.input.get("file_path", "")), self.ws)
            lines = _read_tool_lines(s.result)
            if rel and rel != "." and lines:
                self.observe(s, rel, "Read", lines, None)
        elif s.tool == "Grep" and not s.error and s.result is not None:
            for rel, lines in _grep_lines(s.input, s.result, self.ws, self.known_files()).items():
                self.observe(s, rel, "Grep", lines, None)

    def scan_result(self, s: _Step) -> None:
        """Workspace records and listings of watched files that a tool result shows."""
        for h in re.findall(r'"file_manifest_sha256":\s*"([0-9a-f]{64})"', s.result or ""):
            self.manifests_shown.append((s.event_id, h))
        for rel in self.watch:
            names = (rel, f"{self.ws}/{rel}", f"./{rel}")
            if any(x.strip() in names or x.strip().endswith(tuple(f" {n}" for n in names)) for x in (s.result or "").split("\n")):
                self.listed_in.setdefault(rel, []).append(s.event_id)

    def write_call(self, s: _Step) -> None:
        rel = _rel(str(s.input.get("file_path") or s.input.get("notebook_path") or ""), self.ws)
        if not rel or rel == ".":
            return
        if s.error:
            self.failed_edit(s, rel)
            return
        f = self.touch(rel)
        first = rel not in self.tool_writers or (f.known and f.base_state and bool(f.restored_at))
        self.tool_writers.setdefault(rel, []).append(s.event_id)
        if s.result is None:
            self.unknown(f, f"{s.event_id}: no result is recorded, so whether the call applied is unknown", "bash")
        elif s.tool == "NotebookEdit":
            self.unknown(f, f"{s.event_id}: NotebookEdit is not replayed", "bash")
        elif s.tool == "Write":
            if first:
                self.first_write_item(s, rel, f)
            f.text, f.known, f.why, f.cause, f.base_state, f.restored_at = _redact(str(s.input.get("content", ""))), True, "", "", False, ""
        else:
            edits = edits_of(s.tool, s.input)
            if first and edits:
                self.first_edit_item(s, rel, f, edits[0])
            self.apply_edits(s, rel, f, edits)

    def apply_edits(self, s: _Step, rel: str, f: _File, edits: list[tuple[str, str, bool]]) -> None:
        if not f.known:
            return
        out = apply_edits(f.text, edits)  # the edit function ingest/replay.py uses
        if out.notes:
            self.approximations.append(f"{s.event_id}: {rel}: " + ", ".join(dict.fromkeys(out.notes))
                                       + " (the replay follows the Edit tool; see tracecontract.ingest.edit_tool)")
        if out.text is None:
            k = out.failed_at or 0
            problem = _PROBLEMS.get(str(out.problem), str(out.problem))
            where = f" (edit {k + 1} of {len(edits)})" if len(edits) > 1 else ""
            self.replay_items.append({"kind": "edit", "event_id": s.event_id, "path": rel, "status": FAILED,
                                      "reason": f"the tool applied this edit, but in the replayed content {problem}{where}"})
            self.unknown(f, f"{s.event_id}: {problem}", "anomaly")
            return
        f.text, f.base_state, f.restored_at = out.text, False, ""

    def failed_edit(self, s: _Step, rel: str) -> None:
        """A failed Edit whose error message describes the file must agree with the replayed content."""
        f = self.current(rel)
        if s.tool != "Edit" or not s.result or not f.known or f.text is None:
            return
        old = str(s.input.get("old_string", ""))
        view = _tool_view(f.text, old)
        actual = actual_old_string(view, old) if old else None
        n = view.count(actual) if actual else 0  # the tool counts matches as str.count does (its split count)
        m = re.search(r"Found (\d+) matches of the string to replace", s.result)
        claim = ("not found", n == 0) if "String to replace not found" in s.result else \
            (f"{m.group(1)} matches", n == int(m.group(1))) if m else None
        if claim:
            self.replay_items.append({"kind": "tool_error", "event_id": s.event_id, "path": rel,
                                      "status": PASSED if claim[1] else FAILED,
                                      "reason": f"the tool reported old_string {claim[0]}; the replayed content has {n} occurrence(s)"})

    def first_edit_item(self, s: _Step, rel: str, f: _File, edit: tuple[str, str, bool]) -> None:
        old, new, replace_all = edit
        item: dict = {"path": rel, "event_id": s.event_id, "tool": s.tool, "replace_all": replace_all,
                      "from": f"restore at {f.restored_at}" if f.restored_at else "session start"}
        if not f.known or not f.base_state:
            item.update(status=NOT_CHECKABLE, reason=f"the file was not in its base state before this edit ({f.why or 'written earlier'})")
        elif f.text is None:
            item.update(status=FAILED if old else PASSED,
                        reason="the file is absent from the base" + ("; an edit with a non-empty old_string needs it" if old
                                                                     else "; an empty old_string creates it"))
        else:
            # As the tool matches: a CRLF file read with LF breaks, quotes normalised if need be (edit_tool).
            view = _tool_view(f.text, old)
            actual = actual_old_string(view, old) if old else None
            written = preserve_quote_style(old, actual, new) if actual is not None else new
            olds = _occurrences(view, actual, overlapping=False) if actual else []  # as str.count counts them
            spans = [(i, i + len(actual or "")) for i in olds]
            news = [i for i in _occurrences(view, written)
                    if not any(a <= i and i + len(written) <= b for a, b in spans)] if written else []
            item.update(old_occurrences=len(olds), new_occurrences_outside_old=len(news))
            if actual is not None and actual != old:
                item["quote_normalised"] = True
            problems = []
            if not old and view.strip():
                problems.append("old_string is empty but the file exists in the base")
            elif old and actual is None:
                problems.append("old_string does not occur in the base")
            elif len(olds) > 1 and not replace_all:
                problems.append(f"old_string occurs {len(olds)} times in the base; the Edit tool refuses a non-unique "
                                "old_string unless replace_all is set, so the session did not edit this base")
            if news:
                problems.append(f"new_string already occurs {len(news)} time(s) in the base outside old_string")
            ok = ("an empty old_string fills a file that holds only whitespace" if not old else
                  "old_string occurs as the Edit tool requires and new_string does not occur" + (" (deletion)" if not new else "")
                  + (" (quotes normalised, as the tool matches them)" if item.get("quote_normalised") else ""))
            item.update(status=FAILED if problems else PASSED, reason="; ".join(problems) or ok)
        self.first_writes.append(item)

    def first_write_item(self, s: _Step, rel: str, f: _File) -> None:
        item: dict = {"path": rel, "event_id": s.event_id, "tool": "Write",
                      "from": f"restore at {f.restored_at}" if f.restored_at else "session start"}
        res = s.result or ""
        created, updated = "created successfully" in res, ("has been updated" in res or "updated successfully" in res)
        if not f.known or not f.base_state:
            item.update(status=NOT_CHECKABLE, reason=f"the file was not in its base state before this write ({f.why or 'written earlier'})")
        elif created == updated:
            item.update(status=NOT_CHECKABLE, reason="a Write has no old_string, and its result does not say whether the file existed")
        else:
            verb, ok = ("created", f.text is None) if created else ("updated", f.text is not None)
            item.update(status=PASSED if ok else FAILED,
                        reason=f"the tool {verb} the file, and the base " + ({True: "lacks it", False: "has it"}[created] if ok
                                                                              else {True: "already has it", False: "lacks it"}[created]))
        self.first_writes.append(item)

    def bash(self, s: _Step) -> None:
        cmd = str(s.input.get("command", ""))
        effects = bash_effects(cmd, self.ws, event_id=s.event_id, known_files=self.known_files())
        if s.error or s.result is None:  # a failed or unrecorded command may have stopped before a restore
            effects = [BashEffect(e.event_id, "write", e.paths, e.reason + "; the command failed or has no result, so "
                                  "whether it ran is unknown") if e.action == "restore" else e for e in effects]
        for e in effects:
            self.effects.append(e)
            if e.action == "head_moved":
                self.head_is_base = False
            elif e.action == "write_any":
                self.all_unknown = f"{s.event_id}: {e.reason}"
                for f in self.files.values():
                    self.unknown(f, self.all_unknown, "bash")
            elif e.action == "restore" and self.head_is_base:
                for rel in _under(e.paths, self.files):  # a file never written still has its base content
                    if rel not in self.base_files:
                        continue  # git resets tracked files only: a file the session created stays as it is
                    f = self.files[rel]
                    f.text, f.known, f.why, f.cause, f.base_state, f.restored_at = self.base_text(rel), True, "", "", True, s.event_id
            else:
                known = self.known_files()
                for rel in _under(e.paths, known) + [p for p in e.paths if p != "." and not _under([p], known)]:
                    self.bash_writers.setdefault(rel, []).append(s.event_id)
                    self.unknown(self.touch(rel), f"{s.event_id}: {e.reason}", "bash")
        if not s.error and s.result is not None:
            got = _bash_read(cmd, s.result, self.ws)
            if got:
                self.observe(s, got[0], f"Bash {got[1]}", got[2], got[3])

    def observe(self, s: _Step, rel: str, source: str, lines: dict[int, str] | None, whole: str | None) -> None:
        f = self.current(rel)
        written = rel in self.tool_writers or rel in self.bash_writers
        item: dict = {"path": rel, "event_id": s.event_id, "source": source}
        if not f.known:
            item.update(status=NOT_CHECKABLE, reason=f"the file's content at this point is unknown ({f.why})")
            (self.replay_items if written else self.base_reads).append({**item, "kind": "read"} if written else item)
            return
        if whole is not None and f.text is not None and whole.rstrip("\n") == f.text.rstrip("\n"):
            lines, bad = None, []
            item.update(lines="all", lines_compared=f.text.rstrip("\n").count("\n") + 1)
        else:
            lines = lines if lines is not None else {k + 1: x for k, x in enumerate((whole or "").rstrip("\n").split("\n"))}
            bad = _compare_lines(f.text, lines)
            item.update(lines=_span(lines), lines_compared=len(lines))
        state = "base" if f.base_state else "replayed"
        item.update(state=state, n_mismatches=len(bad), mismatches=bad[:3], status=FAILED if bad else PASSED,
                    reason=f"differs from the {state} content" if bad else f"matches the {state} content")
        if f.base_state:
            self.base_reads.append(item)
            if rel in self.watch and not bad:
                n_all = (f.text or "").count("\n") + 1
                self.seen_lines.setdefault(rel, set()).update(range(1, n_all + 1) if lines is None else lines)
        else:
            self.replay_items.append({**item, "kind": "read"})


# --------------------------------------------------------------------------- the checks


def _post(patch: str | None, base: Path) -> dict[str, str | None] | None:
    """Redacted post-images (None if deleted) of the files a patch changes."""
    if patch is None:
        return None
    return {k: (None if v is None else _decode(v)) for k, v in post_images(patch, base).items()} if patch.strip() else {}


def _check_written(rp: _Replay, final: dict[str, str | None] | None, end: dict[str, _File]) -> Check:
    cid = "a_written_files_changed"
    if final is None:
        return Check(cid, UNAVAILABLE, "no captured final state (reference candidate) to compare with")
    items = []
    for rel in sorted(rp.tool_writers):
        base_t = rp.base_text(rel)
        f = end[rel]
        item: dict = {"path": rel, "written_by": rp.tool_writers[rel]}
        if final.get(rel, base_t) != base_t:
            item.update(status=PASSED, reason="differs between the base and the final state")
        elif f.known and f.text == base_t:
            how = f"the Bash command at {f.restored_at} restored it to the base" if f.restored_at else "its own edits cancel out"
            item.update(status=EXPLAINED, reason=f"the final state equals the base: {how}")
        elif f.known:
            item.update(status=FAILED, reason="the replay gives content other than the base, but the final state equals the base")
        elif f.cause == "bash":
            item.update(status=NOT_CHECKABLE, reason=f"the final state equals the base, and the replay cannot follow a Bash write ({f.why})")
        else:
            item.update(status=FAILED, reason=f"the final state equals the base, and the replay does not explain it ({f.why})")
        items.append(item)
    return _rollup(cid, items, "no file was written through Edit, MultiEdit or Write")


def _check_states(rp: _Replay, states: list[tuple[str, dict[str, str | None] | None, dict[str, _File], str]]) -> Check:
    """Replayed versus captured states, with the replay items gathered on the way."""
    items = list(rp.replay_items)
    for label, changed, snap, all_unknown in states:
        if changed is None:
            items.append({"kind": "state", "state": label, "status": NOT_CHECKABLE, "reason": f"no captured {label} state"})
            continue
        for rel in sorted(set(changed) | set(snap)):
            want = changed.get(rel, rp.base_text(rel))
            f = snap.get(rel)
            item: dict = {"kind": "state", "state": label, "path": rel}
            if f is None:
                ok = all_unknown != ""
                item.update(status=NOT_CHECKABLE if ok else FAILED,
                            reason=f"unknown after {all_unknown}" if ok else
                            f"the captured {label} state changes this file, but no tool call of the session before then wrote it")
            elif not f.known:
                item.update(status=FAILED if f.cause == "anomaly" else NOT_CHECKABLE, reason=f"the replay cannot follow it ({f.why})")
            else:
                ok = f.text == want
                item.update(status=PASSED if ok else FAILED,
                            reason=f"the replay {'reproduces' if ok else 'differs from'} the captured {label} content")
            items.append(item)
    return _rollup("f_replay_matches_states", items, "nothing to replay", list(rp.approximations))


def _file_rollup(rp: _Replay, captured: dict[str, dict[str, str | None] | None]) -> list[dict]:
    """Per changed file: the passed items of checks (b) and (c) that attest its base content.

    A changed file is one that the reference (final) or pre-correction patch changes, or that the
    session edited through Edit, MultiEdit or Write. Its status is ``passed`` if at least one item
    of (b) or (c) on it passed, ``failed`` if one failed and none passed, else ``not_checkable``.
    """
    why: dict[str, list[str]] = {}
    for label, key in (("reference patch", "final"), ("pre-correction patch", "pre-correction")):
        for rel in captured.get(key) or {}:
            why.setdefault(rel, []).append(label)
    for rel in rp.tool_writers:
        why.setdefault(rel, []).append("edited by the session")
    out = []
    for rel in sorted(why):
        mine = [("b", i) for i in rp.first_writes if i.get("path") == rel]
        mine += [("c", i) for i in rp.base_reads if i.get("path") == rel]
        ok = [{"check": c, "event_id": i["event_id"], "reason": i["reason"]} for c, i in mine if i["status"] == PASSED]
        bad = [i for _, i in mine if i["status"] == FAILED]
        status = PASSED if ok else FAILED if bad else NOT_CHECKABLE
        reason = (f"{len(ok)} passed item(s) in check b or c attest its base content" if ok else
                  f"{len(bad)} item(s) in check b or c failed" if bad else
                  "no item of check b or c on it passed: the session's record does not attest its base content"
                  + (f" ({len(mine)} not checkable)" if mine else ""))
        out.append({"path": rel, "changed_by": why[rel], "status": status, "reason": reason, "evidence": ok[:5],
                    "n_evidence": len(ok)})
    return out


def _check_start_manifest(entries: list[tuple[str, str]], start: str | None, source: str, overlays: dict[str, str],
                          rp: _Replay) -> Check:
    cid = "d_start_manifest"
    rebuilt = manifest_sha256(entries)
    items: list[dict] = []
    for eid, h in dict.fromkeys(rp.manifests_shown):
        agrees = start is None or h == start
        items.append({"source": f"workspace record printed at {eid}", "manifest_sha256": h, "status": PASSED if agrees else FAILED,
                      "reason": "agrees with the recorded start-of-session manifest" if agrees else
                      "differs from the recorded start-of-session manifest"})
    if start is None and rp.manifests_shown:
        start, source = rp.manifests_shown[0][1], f"workspace record printed at {rp.manifests_shown[0][0]}"
    if start is None:
        return Check(cid, UNAVAILABLE, "no start-of-session manifest was recorded: the provenance notes carry no "
                                       "workspace_snapshot_manifest and the session printed no workspace record")
    without = manifest_sha256([e for e in entries if e[0] not in overlays])
    item: dict = {"source": source, "start_manifest_sha256": start, "rebuilt_manifest_sha256": rebuilt,
                  "rebuilt_without_overlays_sha256": without, "overlays": sorted(overlays)}
    approx: list[str] = []
    if start == rebuilt:
        item.update(status=PASSED, reason="the rebuilt base equals the start-of-session manifest"
                    + (", overlays included" if overlays else ""))
    elif overlays and start == without:
        item.update(status=EXPLAINED, reason="the recorded start-of-session manifest covers the tree before the overlays were "
                                             "written; the rebuilt base without the overlay files equals it exactly")
        approx.append("controlled.prepare_workspace records the manifest that build_snapshot computes before it writes the "
                      "overlays, so no start-of-session hash covers the overlay content (" + ", ".join(sorted(overlays))
                      + "); task.json holds that content as read from the workspace when the task was compiled.")
        evidence = {}
        for rel, content in sorted(overlays.items()):
            n_lines = content.rstrip("\n").count("\n") + 1
            seen = sorted(x for x in rp.seen_lines.get(rel, set()) if x <= n_lines)
            obs = [o["event_id"] for o in rp.base_reads if o["path"] == rel and o["status"] == PASSED]
            evidence[rel] = {"listed_in": rp.listed_in.get(rel, []), "content_seen_in": obs, "lines_seen": seen,
                             "n_lines": n_lines}
            approx.append(f"{rel}: listed in {len(rp.listed_in.get(rel, []))} tool result(s); the session saw "
                          f"{len(seen)} of its {n_lines} line(s) ({', '.join(map(str, seen)) or 'none'}), matching the overlay; "
                          "the rest of its content is not attested by the session.")
        item["overlay_evidence"] = evidence
    else:
        item.update(status=FAILED, reason="the rebuilt base differs from the start-of-session manifest"
                    + (" with and without the overlays" if overlays else ""))
    items.append(item)
    chk = _rollup(cid, items, "", approx)
    if chk.status == PASSED and approx:
        chk.reason += "; the overlay content is recorded as an approximation"
    return chk


_ARTIFACT = re.compile(r"(?:^|/)__pycache__/|\.py[co]$|\.orig$|\.rej$|~$|\.bak$|(?:^|/)\.git(?:/|$)")


def _artifact_of(rel: str) -> set[str]:
    """Paths of the modules an artifact may be a copy of."""
    p = PurePosixPath(rel)
    if p.parent.name == "__pycache__" or p.suffix in (".pyc", ".pyo"):
        parent = p.parent.parent if p.parent.name == "__pycache__" else p.parent
        return {str(parent / (p.name.split(".")[0] + ".py"))}
    name = p.name.rstrip("~")
    for suf in (".orig", ".rej", ".bak"):
        name = name.removesuffix(suf)
    return {str(p.parent / name), str(p.parent / (name + ".py"))}


def _check_artifacts(base_files: set[str], changed: set[str]) -> Check:
    items, other = [], []
    for rel in sorted(f for f in base_files if _ARTIFACT.search(f)):
        if ".git" in PurePosixPath(rel).parts:
            items.append({"path": rel, "status": FAILED, "reason": "a .git directory can hold later history, the solution included"})
        elif _artifact_of(rel) & changed:
            items.append({"path": rel, "of": sorted(_artifact_of(rel) & changed)[0], "status": FAILED,
                          "reason": "a compiled, backup or reject copy of a changed module"})
        else:
            other.append(rel)
    if not items:
        items.append({"status": PASSED, "changed_modules": sorted(changed), "other_artifacts": other[:20],
                      "reason": "no such copy of a changed module" + (f"; {len(other)} other artifact(s) listed" if other else "")})
    return _rollup("e_no_stale_copies", items, "")


def check_reconstruction(*, task_id: str, session: Session, base: Path, workspace_root: str, final_patch: str | None,
                         pre_patch: str | None = None, boundary_event_id: str | None = None,
                         start_manifest: str | None = None, start_manifest_source: str = "",
                         overlays: dict[str, str] | None = None, legacy_leakage_check: dict | None = None,
                         inputs: dict | None = None) -> Report:
    """Run checks (a) to (f) for one session against its base snapshot directory.

    ``boundary_event_id`` is the user turn before which the pre-correction state was captured.
    """
    overlays = overlays or {}
    ws = os.path.normpath(workspace_root)
    kw: dict[str, Any] = {"inputs": inputs or {}, "legacy_leakage_check": legacy_leakage_check}
    try:
        entries = manifest(base)
    except OSError as exc:
        return unavailable_report(task_id, f"the base snapshot is unreadable: {exc}", **kw)
    base_files = {p for p, _ in entries}
    notes: list[str] = []
    captured: dict[str, dict[str, str | None] | None] = {}
    for label, patch in (("final", final_patch), ("pre-correction", pre_patch)):
        try:
            captured[label] = _post(patch, base)
        except Exception as exc:  # noqa: BLE001 - a patch that does not apply is a data problem, reported
            captured[label] = None
            notes.append(f"the {label} patch does not apply to the base: {exc}")
    rp = _Replay(base, ws, base_files, set(overlays))
    boundary = next((e.index for e in session.events if e.event_id == boundary_event_id), None)
    pre_snap: tuple[dict[str, _File], str] | None = None
    try:
        for s in _steps(session):
            if boundary is not None and pre_snap is None and s.index > boundary:
                pre_snap = (rp.snapshot(), rp.all_unknown)
            rp.step(s)
    except Exception as exc:  # noqa: BLE001 - a data problem: the replay-based checks become unavailable
        why = f"the replay stopped: {type(exc).__name__}: {exc}"
        checks = [Check(cid, UNAVAILABLE, why) for cid in ("a_written_files_changed", "b_first_edit_strings", "c_reads_match_base")]
        checks += [_check_start_manifest(entries, start_manifest, start_manifest_source, overlays, rp),
                   _check_artifacts(base_files, set(captured["final"] or {}) | set(captured["pre-correction"] or {})),
                   Check("f_replay_matches_states", UNAVAILABLE, why)]
        return _report(task_id, checks, notes=notes, **kw)
    if boundary is not None and pre_snap is None:
        pre_snap = (rp.snapshot(), rp.all_unknown)
    end = rp.snapshot()
    states = [("final", captured["final"], end, rp.all_unknown)]
    if pre_patch is not None or boundary is not None:
        snap, unknown = pre_snap if pre_snap else ({}, "")
        states.insert(0, ("pre-correction", captured["pre-correction"] if pre_snap else None, snap, unknown))
    changed = set(rp.tool_writers) | set(captured["final"] or {}) | set(captured["pre-correction"] or {})
    checks = [
        _check_written(rp, captured["final"], end),
        _rollup("b_first_edit_strings", rp.first_writes, "no Edit, MultiEdit or Write call to check"),
        _rollup("c_reads_match_base", rp.base_reads, "the transcript shows no file content seen while the file was in its base state"),
        _check_start_manifest(entries, start_manifest, start_manifest_source, overlays, rp),
        _check_artifacts(base_files, changed),
        _check_states(rp, states),
    ]
    if rp.all_unknown:
        notes.append(f"every file is unknown after {rp.all_unknown}")
    effects = [{**asdict(e), "reason": e.reason.replace(ws, "<workspace>")} for e in rp.effects]
    return _report(task_id, checks, files=_file_rollup(rp, captured), bash_effects=effects,
                   notes=[n.replace(ws, "<workspace>") for n in notes], **kw)


# --------------------------------------------------------------------------- task directories


def _infer_workspace(session: Session, base_files: set[str]) -> str | None:
    """The directory that tool paths share with the base: ``/w/src/m.py`` names ``src/m.py`` in ``/w``."""
    votes: Counter = Counter()
    for e in session.events:
        parts = str((e.tool_input or {}).get("file_path") or "").split("/") if e.kind == EventKind.tool_call else []
        for k in range(1, len(parts)):
            if "/".join(parts[k:]) in base_files:
                votes["/".join(parts[:k])] += 1
                break
    return votes.most_common(1)[0][0] if votes else None


def check_task(task_dir: Path, repo_root: Path, snapshot_root: Path, *, scenario_workspace: str | None = None) -> Report:
    """Check a task directory with repository material only (see the module docstring).

    ``scenario_workspace`` is the scenario's workspace path, for a build that runs the check while
    the scenario is sealed outside the repository; otherwise it is read from the scenario file, or
    inferred from the session's tool paths.
    """
    from .schemas import ProvenanceRecord
    from .store import load
    from .tasks import find_turn, session_for_task

    task_dir = Path(task_dir)
    tid = task_dir.name
    try:
        m = load(task_dir / "task.json", TaskManifest)
        tid = m.task_id
        snap = load(task_dir / (m.snapshot or "snapshot.json"), Snapshot)
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return unavailable_report(tid, f"task.json or snapshot.json is unreadable: {exc}")
    legacy = {"recorded": snap.leakage_check.model_dump(mode="json") if snap.leakage_check else None, "note": VACUOUS_NOTE}
    base = Path(snapshot_root) / m.task_id
    if not base.is_dir():
        return unavailable_report(tid, f"the base snapshot is not built (run `tracecontract snapshot tasks/{tid}`)",
                                  legacy_leakage_check=legacy)
    try:
        entries = manifest(base)
    except OSError as exc:
        return unavailable_report(tid, f"the base snapshot is unreadable: {exc}", legacy_leakage_check=legacy)
    rebuilt = manifest_sha256(entries)
    if rebuilt != snap.file_manifest_sha256:
        return unavailable_report(tid, f"the base snapshot's manifest {rebuilt[:12]} differs from snapshot.json's "
                                       f"{snap.file_manifest_sha256[:12]}; rebuild it", legacy_leakage_check=legacy)
    try:
        session = session_for_task(task_dir, repo_root)
    except Exception as exc:  # noqa: BLE001
        return unavailable_report(tid, f"the transcript is unreadable: {exc}", legacy_leakage_check=legacy)
    cands = []
    for p in m.candidates:
        try:
            cands.append(load(task_dir / p, Candidate))
        except Exception:  # noqa: BLE001 - a candidate that does not load is not used here
            continue
    ref = next((c for c in cands if c.origin == CandidateOrigin.reference), None)
    pre = next((c for c in cands if c.origin == CandidateOrigin.observed_pre_correction), None)
    boundary = None
    if len(m.scripted_turns) > 1:
        try:
            boundary = find_turn(session, m.scripted_turns[1])
        except KeyError:
            boundary = None
    ws, ws_source = scenario_workspace, "scenario" if scenario_workspace else "inferred from tool paths"
    scen = repo_root / "data" / m.population.value / "scenarios" / f"{tid}.json"
    try:
        if ws is None and scen.is_file():
            ws = json.loads(scen.read_text(encoding="utf-8")).get("workspace")
            ws_source = "scenario" if ws else ws_source
    except (OSError, ValueError, AttributeError):
        ws = None
    ws = ws or _infer_workspace(session, {p for p, _ in entries})
    start, source, trace_ok = None, "", None
    try:
        prov = load(task_dir / m.provenance, ProvenanceRecord)
        trace_ok = prov.trace_sha256 == session.trace_sha256
        notes = json.loads(prov.notes) if prov.notes.strip().startswith("{") else {}
        start = notes.get("workspace_snapshot_manifest")
        source = "provenance.json notes: workspace_snapshot_manifest" if start else ""
    except Exception:  # noqa: BLE001 - no provenance record: no recorded start manifest
        pass
    inputs = {"transcript_sha256": session.trace_sha256, "transcript_matches_provenance": trace_ok,
              "base_manifest_sha256": rebuilt, "base_n_files": len(entries), "workspace_root_from": ws_source,
              **_candidate_inputs(ref, pre), "correction_turn_event": boundary}
    if ws is None:
        return unavailable_report(tid, "the workspace root is unknown (no scenario file, and no tool path names a base file)",
                                  inputs=inputs, legacy_leakage_check=legacy)
    rep = check_reconstruction(task_id=tid, session=session, base=base, workspace_root=ws,
                               final_patch=ref.patch if ref else None, pre_patch=pre.patch if pre else None,
                               boundary_event_id=boundary, start_manifest=start, start_manifest_source=source,
                               overlays=dict(m.snapshot_overlays), legacy_leakage_check=legacy, inputs=inputs)
    if snap.n_files != len(entries):
        rep.notes.append(f"snapshot.json gives n_files {snap.n_files}, but the rebuilt base it hashes has {len(entries)} files"
                         + ("; n_files counts the tree before the overlays" if
                            snap.n_files == len([e for e in entries if e[0] not in m.snapshot_overlays]) else ""))
    return rep


# --------------------------------------------------------------------------- the recorded check


# Inputs of a record that must equal the current files for the record to count (recorded_check).
COMPARED_INPUTS = ("transcript_sha256", "base_manifest_sha256", "reference_candidate", "reference_patch_sha256",
                   "pre_correction_candidate", "pre_correction_patch_sha256")


def _candidate_inputs(ref: Candidate | None, pre: Candidate | None) -> dict:
    """Ids of the reference and pre-correction candidates, and the sha256 of each patch (recomputed from its text)."""
    return {"reference_candidate": ref.candidate_id if ref else None,
            "reference_patch_sha256": sha256_text(ref.patch) if ref else None,
            "pre_correction_candidate": pre.candidate_id if pre else None,
            "pre_correction_patch_sha256": sha256_text(pre.patch) if pre else None}


def current_inputs(task_dir: Path, repo_root: Path) -> dict:
    """The :data:`COMPARED_INPUTS` a check of the task would record now, from the current files (no snapshot needed).

    The transcript's sha256 (None if it is missing), the base manifest that ``snapshot.json``
    records (which :func:`check_task` requires the built base to have), and the reference and
    pre-correction candidates of ``task.json``.
    """
    from .store import load
    from .tasks import transcript_path  # as in check_task

    m = load(Path(task_dir) / "task.json", TaskManifest)
    snap = load(Path(task_dir) / (m.snapshot or "snapshot.json"), Snapshot)
    cands = []
    for p in m.candidates:
        try:
            cands.append(load(Path(task_dir) / p, Candidate))
        except Exception:  # noqa: BLE001 - as in check_task: a candidate that does not load is not used
            continue
    ref = next((c for c in cands if c.origin == CandidateOrigin.reference), None)
    pre = next((c for c in cands if c.origin == CandidateOrigin.observed_pre_correction), None)
    try:
        tp: Path | None = transcript_path(Path(task_dir), repo_root)
    except FileNotFoundError:  # a population that keeps no transcript in the repository
        tp = None
    return {"task_id": m.task_id, "transcript_sha256": sha256_bytes(tp.read_bytes()) if tp and tp.is_file() else None,
            "base_manifest_sha256": snap.file_manifest_sha256, **_candidate_inputs(ref, pre)}


@dataclass
class RecordCheck:
    """A task's recorded reconstruction check, compared with the current files (:func:`recorded_check`)."""

    status: str | None  # the record's status (passed | failed | incomplete); None without a readable record
    problems: list[str] = field(default_factory=list)  # why the record does not count; empty if it does
    failed: bool = False  # the record is current and failed: the base may already hold the solution

    @property
    def ok(self) -> bool:
        return not self.problems


def recorded_check(task_dir: Path, repo_root: Path) -> RecordCheck:
    """Whether ``tasks/<id>/reconstruction_check.json`` counts (protocol v0.8 §16.5).

    It counts only if it was made by this method (:data:`METHOD`), its status is ``passed``, and
    its recorded inputs (:data:`COMPARED_INPUTS`: the transcript, the base manifest and the
    candidate patches) equal the current ones. Nothing is re-run and no snapshot is needed;
    ``tracecontract reconstruction-check <task> --write`` makes or refreshes the record.
    """
    task_dir = Path(task_dir)
    path, hint = task_dir / RECORD, f"run `tracecontract reconstruction-check tasks/{task_dir.name} --write`"
    if not path.is_file():
        return RecordCheck(None, [f"no {RECORD}: the base has not been checked against its session ({hint})"])
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
        now = current_inputs(task_dir, repo_root)
        recorded = rec.get("inputs") if isinstance(rec.get("inputs"), dict) else {}
    except Exception as exc:  # noqa: BLE001 - an unreadable record or task counts as no record
        return RecordCheck(None, [f"{RECORD} or the task's records are unreadable ({type(exc).__name__}: {exc}); {hint}"])
    status, problems = rec.get("status"), []
    if rec.get("method") != METHOD:
        problems.append(f"{RECORD} was made by {rec.get('method')!r}, not by {METHOD} ({hint})")
    stale = (["task_id"] if rec.get("task_id") != now["task_id"] else []) + [
        k for k in COMPARED_INPUTS if recorded.get(k) != now.get(k)]
    if stale:
        problems.append(f"{RECORD} was made from other files than the current ones ({', '.join(stale)} differ; {hint})")
    current = not problems
    if status != "passed" or rec.get("passed") is not True:
        checks = rec.get("checks") if isinstance(rec.get("checks"), list) else []
        bad = [f"{c.get('check_id')}: {c.get('status')}" for c in checks if isinstance(c, dict) and c.get("status") != PASSED]
        files = rec.get("files") if isinstance(rec.get("files"), list) else []
        unattested = [str(f.get("path")) for f in files if isinstance(f, dict) and f.get("status") != PASSED]
        detail = "; ".join(bad + ([f"changed file(s) not attested: {', '.join(unattested)}"] if unattested else []))
        what = ("failed: the base may not be the state the session started from, and may already hold the solution"
                if status == "failed" else f"is {status!r}, not 'passed'")
        problems.append(f"the recorded check {what}" + (f" ({detail})" if detail else ""))
    return RecordCheck(status if isinstance(status, str) else None, problems, failed=current and status == "failed")
