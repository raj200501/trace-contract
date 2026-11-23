"""Stricter re-audit of the registered generator transcripts (decision log D44), of fresh attempts (§16.2), and of the
writers of the independent labelers (§15.5).

Usage: python scripts/strict_reaudit.py --transcripts <dir> [--transcripts <dir> ...]
                                        [--extra <transcript.jsonl> ...] --scratch <dir> [--write]
                                        [--outputs <report.json>] [--tasks-root <dir>]
       python scripts/strict_reaudit.py --fresh <attempts.json> --transcripts <dir> [--transcripts <dir> ...]
                                        --report <report.json> [--scratch <dir>]
       python scripts/strict_reaudit.py --labeler <task>=<transcript> [--labeler ...] [--revision <task>=<transcript> ...]
                                        --report <report.json> [--transcripts <dir> ...] [--scratch <dir>]
                                        [--tasks-root <dir>]

``--tasks-root`` names the directory of the task directories (default: the repository's ``tasks/``); the natural
PR-review tasks lie in ``data/natural/tasks`` (protocol §17.4). A report that covers a natural PR-review task
(``--report``, ``--outputs``) holds excerpts of its thread and of upstream code, so it is refused inside the repository
unless git ignores its path (:func:`private_report_problem`; ``data/natural/`` is ignored). A natural family is known by
its population or its id (``NP-xx``), wherever it lies: the labeler mode refuses one without ``--tasks-root`` (the
controlled layout would audit it against ``tasks/`` and ``snapshots/``), and the default mode applies the same guard to
``--outputs``, and to ``--write`` on each ``generator_audit.json`` that holds a natural agent's record.

**Labeler writers** (``--labeler``, ``--revision``; protocol §15.5, decision log D55). Each ``<transcript>`` is the
path of a writer's transcript, or its sha256, looked up among the ``agent-*.jsonl`` files under the ``--transcripts``
directories; ``--labeler`` names a first-round writer, ``--revision`` the single revision of the same family. A
writer may read only its family's reference contract, the base snapshot, the harness API (``tc_sandbox.py``), the
lint rules (``verifier.py``) and the synthetic example of the test format, and may write only its own
``verifiers/independent_label/tests/`` directory. :func:`audit_labeler_transcript` resolves every path of every tool
input (file tools, Grep and Glob paths and patterns, every shell command with its ``cd``, variables, heredocs, inline
code and relative paths, and the arguments of the study's CLI) and classifies it: its own directory, an allowed input,
a system location, the container's ``/tmp``, forbidden material (the reference solution, reference checks, any other
verifier, candidates, strata, labels, the mappings of generated verifiers, the controlled sessions' records under
``data/controlled``, ``results/``, the sealed directory, third-party data, the old workspaces and every Claude session
directory, and any recursive search or listing over them), documentation (judged by what it showed), or outside the
allowed inputs. Every tool output is scanned for paths in forbidden material, for candidate ids, and for the text of
forbidden files (:func:`labeler_index`: their distinctive lines and their test names), except text the agent wrote
itself first. The prompt is an input too: it is scanned for the text of forbidden files, and a revision's prompt must
carry nothing but the names of failing checks (:func:`revision_input`). The harness context (system prompt, reminders,
environment) is scanned for forbidden text. A transcript with a hit, an exposure, forbidden text in its prompt or
harness context, or a revision prompt that carries more than names is flagged; each flag is a lead for reading the
transcript, not a finding. The report (``--report``) holds per transcript its label, family, round, sha256, tool calls
by tool, hits and exposures, with session ids and session-local paths redacted. Where the Claude session directories
are is set in one place, :data:`SESSION_ROOTS` (:class:`SessionRoots`).

The profile is parametrised by the family's layout (:class:`LabelerLayout`). By default it is the controlled tasks' of
D55. With ``--tasks-root``, each family's task directory is ``<tasks root>/<task>`` and its base snapshot lies where
``tracecontract.roots.snapshot_dir`` puts it; the content index covers the families of that root. A natural PR-review
family's writer works in its own workspace, which the family's ``labels/generator_audit.json`` records for the
transcript (``own_workspace``, written by ``scripts/audit_eval_generators.py --task-dir ... --profile natural``): the
workspace's copies of its inputs are allowed, its ``tests/`` and ``scratch/`` are its own, and the other agents'
workspaces, the private run records (``/home/user/nat_runrec``) and the natural arm's build records under
``data/natural`` are forbidden too. Without such a record the task's ``verifiers/independent_label/tests/`` counts as
its own and the transcript carries a note. A revision works in a workspace of its own too: the check names it may be
told are those its writer wrote in the writer's workspace (from the writer's record).

**Fresh attempts** (``--fresh``, protocol v0.8 §16.2). ``<attempts.json>`` holds the attempt
records, a list (or ``{"attempts": [...]}``) of objects with ``attempt_id``, ``task_id``,
``workspace`` (the attempt's workspace, as ``scripts/make_agent_workspace.py`` printed it) and
``transcript_sha256``. Each attempt's transcript is found by its sha256 among the
``agent-*.jsonl`` files under the ``--transcripts`` directories and audited with the fresh-attempt
profile, :func:`tracecontract.controlled.audit_fresh_attempt_transcript`: everything outside the
attempt's own workspace is forbidden (the repository, the study's home with the sealed directory,
the third-party data under ``/home/user/ext`` and the old workspaces, the other workspaces beside
it, ``/root`` and every Claude session directory; ``--scratch`` adds the builder's scratch
directory), and tool inputs and tool outputs are both scanned. An attempt with any hit or exposure
is flagged: per §16.2 it is excluded from every analysis, and the report lists it under
``excluded``. An attempt whose transcript is not found cannot be audited; it is listed under
``not_audited`` and is excluded too, and the exit status is then 1. The report (``--report``,
outside ``tasks/``) holds per attempt its hits and exposures, with session ids, the scratch
directory and e-mail addresses redacted.

**Generator transcripts** (the default).

For every record in ``<tasks root>/*/labels/generator_audit.json`` it finds the transcript(s) the
record names by sha256 among the ``agent-*.jsonl`` files under the ``--transcripts``
directories, and runs two checks on each, and a third with ``--outputs``:

1. :func:`tracecontract.controlled.audit_generator_transcript_strict`, which resolves the
   paths in tool inputs instead of matching substrings. The agent's own workspace is the one
   its record names (``own_workspace``), else the ``--out`` directory of the
   ``export-gen-workspace`` command in its prompt; a writer of reference checks may also write
   the task's ``verifiers/reference_check``; and the builder's scratch directory
   (``--scratch``) counts as forbidden.
2. Reads of the shared scratch directory. The build session's subagents shared one scratch
   directory with the builder and with each other. Every transcript given (``--extra``
   adds the builder's own) contributes to an index of the scratch paths each agent wrote,
   with times. A read or execution of a scratch path by an audited agent is "own" when
   the agent made the last recorded write to that path (or, with no record of the path
   itself, to the directory holding it); a listing or a recursive read (``grep -r``,
   ``rg``, ``cp -r``, ``rsync``, ``tar``, the Grep tool's content mode) is "own" when no
   other agent wrote inside the directory before. Everything else is listed with the
   agent that wrote it last (``null`` when no write is on record, e.g. a file that inline
   code created). Every access to the scratch directory itself (listing, search, read, or
   inline code given its path) is listed separately. Paths that inline code builds at run
   time are not resolved.
3. With ``--outputs``: what the tool outputs (listings, ``git status`` output, error
   messages, file contents) showed the agent, the output scan of
   ``audit_generator_transcript_strict(..., outputs=True)``: paths inside forbidden
   material and held-out candidate ids other than the agent's own. Scratch paths among
   them are classified against the write index as reads are in check 2: a path the agent
   wrote last itself is counted as its own, and the others are listed with the agent that
   wrote them last. These exposures are printed apart from the reads and written, per task,
   role and transcript, to the ``--outputs`` file only. They never enter
   ``generator_audit.json``, so the recorded audits stay as they are.

A record of a natural agent (``profile`` ``natural-agent:v1``, written by
``scripts/audit_eval_generators.py --profile natural``) is re-audited with the natural-agent
profile instead, :func:`tracecontract.controlled.audit_natural_agent_transcript`, in the
workspace its record names. Everything outside that workspace is forbidden, the shared scratch
directory included, so checks 2 and 3 do not apply: its scratch accesses are hits, and its
entry holds the hits and the exposures, both of which flag it (with ``--outputs`` the
exposures are written to that report too).

Session ids and session-local paths are redacted in the output (decision log D21), and
e-mail addresses in the ``--outputs`` report and in the natural entries. With ``--write``
the results of checks 1 and 2 go into each record's ``strict_reaudit`` block; a manual
``assessment`` already there is kept when the hits and scratch findings are unchanged. Checks 1 and 2 do not inspect tool
outputs. The accesses they flag were assessed by reading the transcripts, tool outputs
included; for a file without a recorded writer, the writer was found by reading the
agent's tool inputs. The other assessments restate the classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from tracecontract.controlled import (
    _EXCLUSION_ARG, _LITERAL_PATH, _VAR, NATURAL_PROFILE, _command_words, _scan_command, _shell_segments, _split_unquoted,
    audit_fresh_attempt_transcript, audit_generator_transcript_strict, audit_natural_agent_transcript,
)
from tracecontract.ingest.claude_code import _redact_emails, parse_claude_code_jsonl
from tracecontract.roots import is_natural_pr, snapshot_dir, snapshot_root
from tracecontract.schemas import EventKind, Population
from tracecontract.store import jsonl_lines

R = Path(__file__).resolve().parents[1]
REPO, HOME = "/home/user/trace-contract", "/home/user"
_SESSION_ID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_OUT = re.compile(r"export-gen-workspace\s+\S+\s+--out\s+(\S+)")
_READERS = {"cat", "head", "tail", "less", "more", "sed", "awk", "grep", "egrep", "fgrep", "rg", "diff", "wc", "file",
            "stat", "nl", "sort", "uniq", "cut", "jq", "xxd", "od", "strings", "cmp", "md5sum", "sha256sum"}
_LISTERS = {"ls", "find", "tree", "du"}
_EXECS = {"python", "python3", "bash", "sh", "source", "."}


def _norm(p: str, cwd: str) -> str:
    if p.startswith("~"):
        p = HOME + p[1:]
    return os.path.normpath(p if p.startswith("/") else os.path.join(cwd, p))


def _ops(cmd: str, start: str):
    """(op, path, segment) for one shell command; op is write, read, search, list, exec or cd.

    ``search`` is a recursive read (``grep -r``, ``rg``, ``cp -r``, ``rsync``, ``tar``,
    ``diff -r``). A ``cd`` inside ``( ... )`` lasts until the closing parenthesis.
    """
    cwd, env, stack = start, {}, []
    for seg in _shell_segments(cmd):
        raw = seg.strip()
        if raw.startswith("("):
            stack.append(cwd)
        try:
            lex = shlex.shlex(raw.lstrip("({").rstrip(")}"), posix=True, punctuation_chars="<>&")
            lex.whitespace_split = True
            toks = list(lex)
        except ValueError:
            toks = raw.lstrip("({").rstrip(")}").split()
        # redirections first, then the command words (keywords, assignments and wrappers removed)
        words, i = [], 0
        while i < len(toks):
            t = toks[i]
            if re.fullmatch(r"(?:\d|&)?>>?\|?", t):
                if i + 1 < len(toks) and not toks[i + 1].startswith("&"):
                    yield "write", _norm(_expand(toks[i + 1], env).rstrip(')"\'`;,'), cwd), seg
                i += 2
            elif t == "<":
                if i + 1 < len(toks):
                    yield "read", _norm(_expand(toks[i + 1], env).rstrip(')"\'`;,'), cwd), seg
                i += 2
            elif t in ("<<", "<<-", "<<<"):
                i += 2
            elif t in ("&", "&&") or t.startswith("<<"):
                i += 1
            else:
                words.append(t)
                i += 1
        words = _command_words(" ".join(shlex.quote(w) for w in words), env) if words else []
        words = [w.rstrip(')"\'`;,') for w in words]
        if words:
            name = os.path.basename(words[0])
            opts = [t for t in words[1:] if t.startswith("-")]
            args = [t for t in words[1:] if t and not t.startswith("-")]
            short = "".join(t[1:] for t in opts if not t.startswith("--"))
            if name == "cd":
                if args and "$" not in args[0]:
                    cwd = _norm(args[0], cwd)
                    yield "cd", cwd, seg
            elif name in ("mkdir", "tee", "touch"):
                for a in args:
                    yield "write", _norm(a, cwd), seg
            elif name in ("cp", "mv", "rsync", "ln", "tar") and len(args) >= 2:
                deep = name in ("rsync", "tar") or "r" in short or "R" in short or "a" in short or "--recursive" in opts
                for a in (args[:-1] if name != "tar" else args[1:]):
                    yield ("search" if deep else "read"), _norm(a, cwd), seg
                yield "write", _norm(args[-1] if name != "tar" else args[0], cwd), seg
            elif name in _LISTERS:
                for a in (args[:1] if name == "find" else args) or ["."]:
                    yield "list", _norm(a, cwd), seg
            elif name in _EXECS:
                for a in args:
                    if "/" in a or a.endswith((".py", ".sh")):
                        yield "exec", _norm(a, cwd), seg
            elif name in _READERS:
                deep = (name == "rg" or (name in ("grep", "egrep", "fgrep") and ("r" in short or "R" in short or "--recursive" in opts))
                        or (name == "diff" and ("r" in short or "--recursive" in opts)))
                targets = args[1:] if name in ("grep", "egrep", "fgrep", "rg", "sed", "awk") else args
                for a in targets or (["."] if deep else []):
                    if "$" not in a:
                        yield ("search" if deep else "read"), _norm(a, cwd), seg
        if raw.endswith(")") and stack:
            cwd = stack.pop()


def _expand(t: str, env: dict) -> str:
    return _VAR.sub(lambda m: env.get(m.group(1) or m.group(2), m.group(0)), t)


def _tool_calls(path: Path):
    rows = [json.loads(line) for line in jsonl_lines(path.read_text(encoding="utf-8")) if line.strip()]
    for n, e in enumerate(rows, 1):
        c = e.get("message", {}).get("content")
        if e.get("type") == "assistant" and isinstance(c, list):
            for x in c:
                if isinstance(x, dict) and x.get("type") == "tool_use":
                    yield n, e.get("timestamp") or "", x.get("name"), x.get("input") or {}


def _scratch_ops(path: Path, scratch: str):
    inside = lambda p: p == scratch or p.startswith(scratch + "/")
    for n, ts, tool, ti in _tool_calls(path):
        ops = []
        if tool in ("Write", "Edit", "NotebookEdit"):
            ops.append(("write", _norm(ti.get("file_path") or ti.get("notebook_path") or "", REPO), tool))
        elif tool == "Read":
            ops.append(("read", _norm(ti.get("file_path", ""), REPO), tool))
        elif tool == "Grep":
            mode = ti.get("output_mode") or "files_with_matches"
            ops.append(("list" if mode == "files_with_matches" else "search", _norm(ti.get("path") or ".", REPO), tool))
        elif tool == "Glob":
            ops.append(("list", _norm(ti.get("path") or ".", REPO), tool))
        cmd = ti.get("command") if isinstance(ti.get("command"), str) else ""
        if cmd:
            ops += list(_ops(cmd, REPO))
            ops += [("read", m.group(0).rstrip(')"\'`;,'), "inline") for m in re.finditer(re.escape(scratch) + r"/[\w./-]+", cmd)]
        for op, p, seg in ops:
            if inside(p):
                yield {"line": n, "ts": ts, "op": op, "path": p, "seg": seg[:200]}


def _prompt_text(path: Path) -> str:
    out = []
    for line in jsonl_lines(path.read_text(encoding="utf-8"))[:6]:
        e = json.loads(line)
        if e.get("type") == "user":
            c = e["message"]["content"]
            out.append(c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict)))
    return "\n".join(out)


def _redact(x, scratch: str | None):
    if isinstance(x, str):
        return _SESSION_ID.sub("<session>", x.replace(scratch, "<scratchpad>") if scratch else x)
    if isinstance(x, list):
        return [_redact(v, scratch) for v in x]
    if isinstance(x, dict):
        return {k: _redact(v, scratch) for k, v in x.items()}
    return x


def _redact_output(x, scratch: str | None):
    """:func:`_redact`, and e-mail addresses too: tool outputs can show any text (e.g. ``git log``)."""
    x = _redact(x, scratch)
    if isinstance(x, str):
        return _redact_emails(x, {})
    if isinstance(x, list):
        return [_redact_output(v, scratch) for v in x]
    if isinstance(x, dict):
        return {k: _redact_output(v, scratch) for k, v in x.items()}
    return x


def classify_scratch(path: Path, scratch: str, writes: list[dict]) -> tuple[list, list, int]:
    """Classify one transcript's accesses to the shared scratch directory against the write index.

    Returns ``(root_accesses, not_attributed, n_own)``: accesses to the directory itself, the
    other accesses that are not the agent's own (with the agent that wrote last), and the
    number of own ones.
    """
    under = lambda p, d: p == d or p.startswith(d + "/")
    others, roots, n_own = [], [], 0
    for o in _scratch_ops(path, scratch):
        if o["op"] in ("write", "cd"):
            continue
        if o["path"] == scratch:  # the directory itself: a listing, search or read of everything in it
            roots.append({"line": o["line"], "ts": o["ts"], "op": o["op"], "text": o["seg"]})
            continue
        before = [w for w in writes if w["ts"] <= o["ts"] and w["path"] != scratch]
        exact = [w for w in before if under(w["path"], o["path"])]  # the path itself, or files inside it
        upper = [w for w in before if under(o["path"], w["path"]) and w["path"] != o["path"]]
        if o["op"] in ("list", "search"):
            # A listing or recursive read is the agent's own only if nobody else wrote inside the
            # directory before.
            foreign = [w for w in exact if w["agent"] != path.stem]
            last = foreign[-1] if foreign else None
            own_ok = not foreign and bool(exact or [w for w in upper if w["agent"] == path.stem])
        else:
            # A read is the agent's own if the agent wrote the file last (or, with no record of the
            # file itself, created the directory holding it last).
            last = (exact or upper or [None])[-1]
            own_ok = last is not None and last["agent"] == path.stem
        if own_ok:
            n_own += 1
        else:
            others.append({"line": o["line"], "ts": o["ts"], "op": o["op"], "path": o["path"], "text": o["seg"],
                           "last_written_by": last["agent"] if last else None,
                           "last_written_at": last["ts"] if last else None})
    return roots, others, n_own


def classify_scratch_outputs(exposures: list[dict], agent: str, scratch: str, writes: list[dict]) -> tuple[list, list, int]:
    """Split one transcript's tool-output exposures by the shared scratch directory and the write index.

    Returns ``(outside, not_attributed, n_own)``: the exposures outside the scratch directory, the
    scratch paths that the agent (``agent``, the transcript's stem) did not write last itself before
    the output, with the agent that did (``null`` for the directory itself or without a recorded
    write), and the number of scratch paths it did write last, as for reads in :func:`classify_scratch`.
    """
    under = lambda p, d: p == d or p.startswith(d + "/")
    outside, others, n_own = [], [], 0
    for x in exposures:
        if not under(x["path"], scratch):
            outside.append(x)
            continue
        before = [w for w in writes if w["ts"] <= (x.get("ts") or "") and w["path"] != scratch]
        exact = [w for w in before if under(w["path"], x["path"])]  # the path itself, or files inside it
        upper = [w for w in before if under(x["path"], w["path"]) and w["path"] != x["path"]]
        last = (exact or upper or [None])[-1] if x["path"] != scratch else None
        if last is not None and last["agent"] == agent:
            n_own += 1
        else:
            others.append({**x, "last_written_by": last["agent"] if last else None,
                           "last_written_at": last["ts"] if last else None})
    return outside, others, n_own


def _attempt_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("attempts") if isinstance(data, dict) else data
    if not isinstance(records, list):
        raise SystemExit(f"{path}: expected a list of attempt records (or {{'attempts': [...]}})")
    for r in records:
        missing = [k for k in ("attempt_id", "task_id", "workspace", "transcript_sha256") if not (isinstance(r, dict) and r.get(k))]
        if missing:
            raise SystemExit(f"{path}: an attempt record lacks {missing}")
    ids = [r["attempt_id"] for r in records]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{path}: attempt ids repeat")
    return records


def audit_fresh(records: list[dict], transcripts: list[Path], scratch: str | None) -> dict:
    """The fresh-attempt report of protocol §16.2 (see the module docstring)."""
    by_sha = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in transcripts}
    out: dict = {"script": "scripts/strict_reaudit.py --fresh",
                 "profile": "fresh attempt (protocol v0.8 §16.2): everything outside the attempt's own workspace is "
                            "forbidden; tool inputs and tool outputs are scanned; an attempt with a hit or an exposure "
                            "is excluded", "attempts": {}, "excluded": [], "not_audited": []}
    for r in records:
        p = by_sha.get(r["transcript_sha256"])
        if p is None:
            out["attempts"][r["attempt_id"]] = {"task_id": r["task_id"], "error": "transcript not found", "flagged": True}
            out["not_audited"].append(r["attempt_id"])
            out["excluded"].append(r["attempt_id"])
            continue
        hits, exposures = audit_fresh_attempt_transcript(p, task=r["task_id"], workspace=r["workspace"],
                                                         extra_forbidden=(scratch,) if scratch else ())
        flagged = bool(hits or exposures)
        out["attempts"][r["attempt_id"]] = {"task_id": r["task_id"], "workspace": r["workspace"],
                                            "transcript_sha256": r["transcript_sha256"], "flagged": flagged,
                                            "hits": hits, "exposures": exposures}
        if flagged:
            out["excluded"].append(r["attempt_id"])
    return _redact_output(out, scratch)


# --------------------------------------------------------------------------- labeler writers (protocol §15.5, D55)

LABELER_PROFILE = (
    "labeler writer (protocol §15.5, decision log D55): a writer may read only its family's reference contract, the base "
    "snapshot, the harness API (tc_sandbox.py), the lint rules (verifier.py) and the synthetic example of the test format, "
    "and may write only its own tests directory; every tool input and every tool output is scanned, and so are the prompt "
    "and the harness context; a revision may be told only the names of the failing checks")
_LABELER_SYSTEM = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/etc", "/dev", "/proc", "/sys", "/opt",
                   "/root/.local/bin")
_GENERATED = ("reference_check", "repo_tests", "initial_plain", "full_plain", "llm_freeform", "initial_audited", "full_audited",
              "diff_derived")
_AREAS = {"candidates": "a candidate", "strata": "a stratum candidate", "labels": "a label"}
_SESSION_WHY = "a Claude session directory (the build session's records)"
_EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_HANDBACK = {"SubagentHandback", "StructuredOutput"}  # the agent's final report: scanned for what it names, not an access
_FLAGGED_CATEGORIES = ("forbidden", "doc", "outside")
# A token that the shell parsers take for a path but is an option value, a sed range or a redirection operator.
_NOT_A_PATH = re.compile(r"[-+]?\d[\d,.:]*[A-Za-z]?|\d?[<>&|;()]+\d?")
_LINE_PREFIX = re.compile(r"^\s*\d+\t|^[\w./-]+:\d+[:-]|^\d+[:-]")  # Read's line numbers, grep -n's prefixes
_TEST_NAME = re.compile(r"(?<![\w-])test_\w+")
_CHECK_NAME = re.compile(r"[\w./-]+\.py::\w+(?:::\w+)?")
_LISTED = re.compile(r"(?:(?P<kind>[A-Za-z][\w ]*?):\s+)?(?P<name>[\w./-]+\.py::\w+(?:::\w+)?|R-[\w.-]+)")
_FRESH_ID = re.compile(r"(?<![\w-])(?:CS-\d\d|NP-\d{2,})-fresh-[AB]-(?:u1|final)-\d+\b")
_NATURAL_ID = re.compile(r"NP-\d{2,}")  # the id of a natural PR-review family (protocol §15.6)
# A candidate id of a controlled (CS-xx) or natural (NP-xx) family that only grading or forbidden material could show.
_GRADED_ID = re.compile(r"(?<![\w-])(?:CS-\d\d|NP-\d{2,})-(?:reference|noop-\w+|eval-[\w-]+|pre-correction|pre-review)\b")
# What grading output looks like, beyond the names of checks: messages, tracebacks, outcomes and counts.
_GRADING = re.compile(r"Traceback|\b\w+Error\b|\bassert\b|\bPASSED\b|\bFAILED\b|\btask_failure\b|\brepeats?\b|\boutcome\b|"
                      r"\bstdout\b|\bstderr\b|\bnotes\b|\b\d+ (?:checks? )?(?:passed|failed)\b")
_HEREDOC_FILE = re.compile(r"(?:cat|tee)\s*>{1,2}\s*['\"]?(\S+?)['\"]?\s*<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\2(?:\n|$)", re.S)
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


class SessionRoots(NamedTuple):
    """Where the Claude Code harness keeps the build session's own files. For the labeler profile every path there is a
    Claude session directory (forbidden, and so is a listing or search over one), and the report redacts them. The
    defaults are the harness's real locations; the tests point :data:`SESSION_ROOTS` at synthetic ones.

    ``records`` is the directory of the agents' records, with one directory per session,
    ``<records>/projects/<project>/<session id>`` (redacted as ``<session-dir>``), where the harness also saves the tool
    outputs too long to show (its "Full output saved to: ..." notices name them). ``tmp`` begins the name of each user's
    temporary directory, ``<tmp><uid>``, with one directory per session, ``<tmp><uid>/<project>/<session id>`` (redacted
    as ``<session-tmp>``), which holds the session's scratch directory, ``scratchpad`` (redacted as ``<scratchpad>``); a
    path that holds ``tmp`` anywhere is a session directory. ``uid`` is the user the sessions ran as, whose temporary
    directory a listing of its parent shows.
    """

    records: str = "/root/.claude"
    tmp: str = "/tmp/claude-"
    uid: str = "0"

    def session_dir(self) -> re.Pattern:
        """One session's directory of records."""
        return re.compile(re.escape(self.records) + r"/projects/[^/\s\"']+/" + _UUID)

    def session_tmp(self) -> re.Pattern:
        """One session's temporary directory, of any user."""
        return re.compile(re.escape(self.tmp) + r"\d+/[^/\s\"']+/" + _UUID)

    def scratch(self) -> re.Pattern:
        """One session's scratch directory."""
        return re.compile(self.session_tmp().pattern + "/scratchpad")


SESSION_ROOTS = SessionRoots()


def _inside(p: str, root: str) -> bool:
    return p == root or p.startswith(root.rstrip("/") + "/")


class LabelerLayout(NamedTuple):
    """Where the labeler profile finds one family's material, as the agent's tool inputs name it (under :data:`REPO`).

    The default (:func:`labeler_layout` without a task directory) is the controlled tasks' layout of D55: the task in
    ``tasks/<id>``, its base snapshot in ``snapshots/<id>``, and the writer writes the task's
    ``verifiers/independent_label/tests/``. A natural PR-review task (``natural``) lies in ``data/natural/tasks/<id>``
    with its base snapshot under ``data/natural/snapshots`` (:mod:`tracecontract.roots`), and its labeler writer works in
    a workspace of its own (``workspace``, from the agent's record in ``labels/generator_audit.json``): the workspace's
    copies of its inputs are allowed, its ``tests/`` and ``scratch/`` are its own, and the other agents' workspaces, the
    private run records and the natural arm's build records under ``data/natural`` are forbidden too.
    """

    task_dir: str  # the family's task directory
    snapshots: str  # the root of the base snapshots: the family's base snapshot is <snapshots>/<task>
    workspace: str | None = None  # the writer's own workspace (natural tasks)
    natural: bool = False
    repo: str = REPO

    @property
    def tasks(self) -> str:
        """The directory that holds the family's task directory."""
        return os.path.dirname(self.task_dir)

    @property
    def family_roots(self) -> tuple[str, ...]:
        """The directories of families: the family's own tasks directory and, for a natural task, ``tasks/`` too."""
        return tuple(dict.fromkeys((self.tasks, *((f"{self.repo}/tasks",) if self.natural else ()))))

    @property
    def snapshot_roots(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.snapshots, *((f"{self.repo}/snapshots",) if self.natural else ()))))

    @property
    def other_workspaces(self) -> tuple[str, ...]:
        """The directories that hold the other agents' workspaces: the one beside the writer's own and the one above."""
        if not self.workspace:
            return ()
        group = os.path.dirname(self.workspace)
        out = [group]
        if os.path.dirname(group) not in ("/", HOME) and os.path.dirname(group).count("/") >= 2:
            out.append(os.path.dirname(group))
        return tuple(out)


def labeler_layout(task: str, repo: str = REPO, *, task_dir: str | None = None, snapshot_root: str | None = None,
                   workspace: str | None = None, natural: bool = False) -> LabelerLayout:
    """The layout of one family for the labeler profile (:class:`LabelerLayout`); without ``task_dir`` and
    ``snapshot_root``, the controlled tasks' (``<repo>/tasks/<task>``, ``<repo>/snapshots``)."""
    return LabelerLayout(task_dir=os.path.normpath(task_dir or f"{repo}/tasks/{task}"),
                         snapshots=os.path.normpath(snapshot_root or f"{repo}/snapshots"),
                         workspace=os.path.normpath(workspace) if workspace else None, natural=natural, repo=repo)


def labeler_allowed(task: str, repo: str = REPO, *, layout: LabelerLayout | None = None) -> tuple[tuple[str, str], ...]:
    """The inputs a labeler writer of ``task`` may read (protocol §15.5, D55), each with what it is."""
    lay = layout or labeler_layout(task, repo)
    out: tuple[tuple[str, str], ...] = (
        (f"{lay.task_dir}/contracts/reference.json", "the reference contract"),
        (f"{lay.snapshots}/{task}", "the base snapshot"),
        (f"{repo}/src/tracecontract/sandbox/harness/tc_sandbox.py", "the harness API"),
        (f"{repo}/src/tracecontract/verifier.py", "the lint rules"),
        (f"{repo}/tests/fixtures/harbor_fx01/tasks/FX-01/verifiers/v1", "the synthetic example of the test format"))
    if lay.workspace:
        out += ((lay.workspace, ("its workspace's copies of its inputs (the reference contract, the base snapshot and the "
                                 "harness docs)")),)
    return out


def labeler_own(task: str, repo: str = REPO, *, layout: LabelerLayout | None = None) -> str:
    """The one directory a labeler writer of ``task`` may write (and read back): the task's
    ``verifiers/independent_label/tests``, or a natural writer's ``<workspace>/tests``."""
    lay = layout or labeler_layout(task, repo)
    return f"{lay.workspace}/tests" if lay.workspace else f"{lay.task_dir}/verifiers/independent_label/tests"


def _labeler_family(p: str, task: str, lay: LabelerLayout) -> tuple[str, str] | None:
    """(category, why) of a path in a family's task directory (or deeper), or None."""
    for troot in lay.family_roots:
        if not _inside(p, troot) or p == troot:
            continue
        parts = os.path.relpath(p, troot).split("/")
        if len(parts) < 2:
            continue
        fam, area = parts[0], parts[1]
        mine = fam == task and troot == lay.tasks
        other = "" if mine else " of another family"
        if area == "candidates" and len(parts) > 2 and parts[2] == f"{fam}-reference.json":
            return "forbidden", "the reference solution (the reference candidate and its patch)" + other
        if area == "verifiers" and len(parts) > 2:
            if parts[2] == "reference_check":
                return "forbidden", "a reference check" + other
            if parts[2] == "independent_label" and mine:
                if parts[3:4] == ["status.json"]:
                    return "forbidden", "the coordinator's grading status of the labeler"
                return "outside", "the coordinator's record of the labeler (its spec)"
            return "forbidden", "a generated verifier" + other
        if area in _AREAS:
            return "forbidden", _AREAS[area] + other
        if area == "contracts" and len(parts) > 2 and parts[2].startswith("mapping"):
            return "forbidden", "a mapping of a generated verifier's checks" + other
        if area == "contracts":
            return "outside", ("the contracts directory" if len(parts) == 2 else "another contract") + other
        if area == "verifiers":
            return "outside", "the verifiers directory" + other
        return "outside", "task metadata (it lists the verifiers and candidates)" + other
    return None


_NATURAL_BUILD_WHY = "the natural arm's build records (S10 work trees with the reference state, the fetch log, run records)"
_OTHER_WORKSPACE_WHY = "another agent's workspace"
_RUN_RECORDS_WHY = "the natural agents' private run records (they hold grading output)"


def _labeler_direct(p: str, task: str, repo: str, home: str, extra: tuple[str, ...],
                    layout: LabelerLayout | None = None) -> tuple[str, str]:
    """(category, why) of the path ``p`` itself; see :func:`labeler_classify`."""
    lay = layout or labeler_layout(task, repo)
    if SESSION_ROOTS.tmp in p or _inside(p, SESSION_ROOTS.records) or any(_inside(p, x) for x in extra):
        return "forbidden", _SESSION_WHY
    if any(m in p for m in ("scratchpad/sealed", "scratchpad/scenarios", "scratchpad/reference")):
        return "forbidden", "sealed material"
    if _inside(p, labeler_own(task, repo, layout=lay)):
        return "own", "its own tests directory"
    if lay.workspace and _inside(p, f"{lay.workspace}/scratch"):
        return "own", "its private scratch directory"
    for root, why in labeler_allowed(task, repo, layout=lay):
        if _inside(p, root):
            return "allowed", why
    if _inside(p, repo):
        fam = _labeler_family(p, task, lay)
        if fam is not None:
            return fam
        parts = os.path.relpath(p, repo).split("/")
        if parts[:2] == ["data", "controlled"]:
            return "forbidden", "the controlled sessions' records (their transcripts hold the reference edits)"
        if parts[0] == "results":
            return "forbidden", "verdicts (results/)"
        if any(_inside(p, r) and p != r for r in lay.snapshot_roots):
            return "outside", "another family's base snapshot"
        if lay.natural and parts[:2] == ["data", "natural"] and not any(
                _inside(p, r) for r in (*lay.family_roots, *lay.snapshot_roots)):
            return "forbidden", _NATURAL_BUILD_WHY
        if parts[0] in ("docs", "paper", "experiments") or parts in (["README.md"], ["STATUS.md"]):
            return "doc", "documentation or paper text (judged by what it showed)"
        if parts[0] == ".venv":
            return "system", "the study's virtual environment (interpreter and CLI)"
        return "outside", "outside the allowed inputs"
    if _inside(p, f"{home}/.tc_sealed"):
        return "forbidden", "sealed material"
    if _inside(p, f"{home}/ext"):
        return "forbidden", "third-party data"
    if any(_inside(p, f"{home}/{d}") for d in ("cs_workspaces", "gen_workspaces", "fresh_ws")):
        return "forbidden", "a workspace of the controlled sessions, the generators or the fresh attempts"
    if any(_inside(p, w) for w in lay.other_workspaces):
        return "forbidden", _OTHER_WORKSPACE_WHY
    if lay.natural and _inside(p, f"{home}/nat_runrec"):
        return "forbidden", _RUN_RECORDS_WHY
    if any(_inside(p, s) for s in _LABELER_SYSTEM):
        return "system", "a system location"
    if _inside(p, "/tmp"):
        return "tmp", "the container's temporary directory"
    return "outside", "outside the allowed inputs"


def _labeler_anchors(task: str, families: tuple[str, ...], repo: str, home: str, extra: tuple[str, ...],
                     layout: LabelerLayout | None = None) -> list:
    """Forbidden roots, for deciding whether a recursive search or a listing covers forbidden material."""
    lay = layout or labeler_layout(task, repo)
    out = []
    for f in dict.fromkeys((task, *families)):
        o = "" if f == task else " of another family"
        t = f"{lay.tasks}/{f}"
        out += [(f"{t}/verifiers/{v}", ("a reference check" if v == "reference_check" else "a generated verifier") + o)
                for v in _GENERATED]
        out.append((f"{t}/verifiers/independent_label/status.json", "the coordinator's grading status of the labeler")
                   if f == task else (f"{t}/verifiers/independent_label", "a generated verifier" + o))
        out += [(f"{t}/{a}", why + o) for a, why in _AREAS.items()]
        out.append((f"{t}/contracts/mapping_full_session.json", "a mapping of a generated verifier's checks" + o))
    out += [(f"{repo}/data/controlled", "the controlled sessions' records"), (f"{repo}/results", "verdicts (results/)"),
            (f"{home}/.tc_sealed", "sealed material"), (f"{home}/ext", "third-party data"),
            *[(f"{home}/{d}", "a workspace of the controlled sessions, the generators or the fresh attempts")
              for d in ("cs_workspaces", "gen_workspaces", "fresh_ws")],
            (SESSION_ROOTS.records, _SESSION_WHY), (SESSION_ROOTS.tmp + SESSION_ROOTS.uid, _SESSION_WHY),
            *[(x, _SESSION_WHY) for x in extra]]
    if lay.natural:
        out += [(f"{repo}/data/natural/s10_work", _NATURAL_BUILD_WHY), (f"{repo}/data/natural/runs", _NATURAL_BUILD_WHY),
                (f"{home}/nat_runrec", _RUN_RECORDS_WHY), *[(w, _OTHER_WORKSPACE_WHY) for w in lay.other_workspaces]]
    return out


def labeler_classify(p: str, task: str, *, op: str = "read", families: tuple[str, ...] = (), repo: str = REPO,
                     home: str = HOME, extra_forbidden: tuple[str, ...] = (), pruned: tuple[str, ...] = (),
                     layout: LabelerLayout | None = None) -> tuple[str, str]:
    """``(category, why)`` of one resolved path that a labeler writer of ``task`` reads, lists, searches, runs or writes.

    Categories: ``own`` (its tests directory), ``allowed`` (:func:`labeler_allowed`), ``system`` (system locations, the
    study's virtual environment), ``tmp`` (the container's temporary directory, outside the Claude session directories),
    ``forbidden`` (the reference solution, a reference check, any other verifier, the coordinator's grading status of the
    labeler, candidates, strata, labels, the mappings of generated verifiers, ``data/controlled``, ``results/``, sealed
    material, third-party data, the old workspaces and every Claude session directory), ``doc`` (``docs/``, ``paper/``,
    ``experiments/``, ``README.md``, ``STATUS.md``: judged by what the read showed) and ``outside`` (everything else). A
    search (``op="search"``) or a listing (``op="list"``) whose root holds forbidden material that it does not prune is
    forbidden too. ``layout`` places the family's material (:class:`LabelerLayout`; by default the controlled tasks').
    """
    extra = tuple(os.path.normpath(x) for x in extra_forbidden)
    cat, why = _labeler_direct(p, task, repo, home, extra, layout)
    if op in ("search", "list") and cat != "forbidden":
        held = [w for a, w in _labeler_anchors(task, families, repo, home, extra, layout)
                if _inside(a, p) and a != p and not any(_inside(a, x) for x in pruned)]
        if held:
            lead = "recursive search over forbidden material" if op == "search" else "a listing of a directory that holds forbidden material"
            return "forbidden", f"{lead} ({held[0]})"
    return cat, why


def _segments_cwd(cmd: str, start: str):
    """``(segment, words, cwd)`` for each segment of a shell command, following ``cd`` (inside ``( ... )`` until its end)."""
    cwd, env, stack = start, {}, []
    for seg in _shell_segments(cmd):
        raw = seg.strip()
        if raw.startswith("("):
            stack.append(cwd)
        words = _command_words(raw, env)
        if words and os.path.basename(words[0]) == "cd" and len(words) > 1 and "$" not in words[1]:
            cwd = _norm(words[1], cwd)
        yield raw, words, cwd
        if raw.endswith(")") and stack:
            cwd = stack.pop()


def _labeler_shell(cmd: str, starts: list[str], candidate: re.Pattern) -> tuple[list, list, list, list]:
    """The accesses of one shell command: ``(ops, unresolved, bases, ends)``.

    ``ops`` holds ``(op, path, text, pruned)`` (``op``: read, search, list, exec or write), from both shell parsers of
    the strict audit (:func:`_ops` and ``controlled._scan_command``), started in each directory of ``starts``; the
    study's CLI may read anything under a path it is given (a search). ``unresolved`` holds the recursive searches
    rooted at a variable, ``bases`` the directories the command may run in (its starts and every ``cd`` target), and
    ``ends`` those it may end in. Tokens that are option values, sed ranges, redirection operators, inline code, or the
    script of a sed or awk call are not taken for paths. A CLI call other than ``lint-tests`` and a candidate id given
    to the CLI are returned as ops ``cli`` and ``candidate``.
    """
    ops, unresolved, bases, ends, scripts = [], [], list(starts), [], set()
    for s in starts:
        for raw, words, cwd in _segments_cwd(cmd, s):
            bases.append(cwd)
            name = os.path.basename(words[0]) if words else ""
            args = [w for w in words[1:] if not w.startswith("-")]
            if name in ("sed", "awk", "gawk") and args:
                scripts.add(_norm(args[0], cwd))
            if name == "tracecontract":
                if words[1:2] != ["lint-tests"]:
                    ops.append(("cli", " ".join(words[:2]), raw[:300], ()))
                for w in words[2:]:
                    if candidate.fullmatch(w):
                        ops.append(("candidate", w, raw[:300], ()))
                    elif not w.startswith("-") and "/" in w and "$" not in w:
                        ops.append(("search", _norm(w, cwd), raw[:300], ()))  # it may read anything under it
        cds = set()
        for op, p, seg in _ops(cmd, s):
            if op == "cd":
                cds.add(p)
            else:
                ops.append((op, p, seg.strip()[:300], ()))
        checks, unres, end = _scan_command(cmd, s, _norm)
        ops += [("search" if rec else "read", p, text, pruned) for p, rec, text, pruned in checks if rec or p not in cds]
        unresolved += unres
        ends.append(end)
    noise = lambda p: (p in scripts or bool(_NOT_A_PATH.fullmatch(os.path.basename(p)))  # noqa: E731
                       or any(c in p for c in "\n\t '\"()<>|;&"))
    kept, seen = [], set()
    listed = {p for op, p, _, _ in ops if op in ("list", "search")}
    for op, p, text, pruned in ops:
        if op in ("cli", "candidate") or not (noise(p) or (op == "read" and p in listed)):
            if (op, p) not in seen:
                seen.add((op, p))
                kept.append((op, p, text, pruned))
    return kept, list(dict.fromkeys(unresolved)), list(dict.fromkeys(bases)), list(dict.fromkeys(ends))


def _norm_line(line: str) -> str:
    """A line as the content scans compare it: stripped, without a diff marker, Read's line number or grep's prefix."""
    s = _LINE_PREFIX.sub("", line, count=1).strip()
    if s[:1] in ("+", "-") and not s.startswith(("+++", "---")):
        s = s[1:].strip()
    return s


def _distinctive(s: str) -> bool:
    """A line long enough to identify its file: 24 characters with a word of three letters, and more than one token
    (a bare path or id is left to the path and id rules)."""
    return len(s) >= 24 and re.search(r"[A-Za-z]{3}", s) is not None and re.search(r"[\s()=:,\[\]{}]", s) is not None


def _json_strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, list):
        for v in x:
            yield from _json_strings(v)
    elif isinstance(x, dict):
        for v in x.values():
            yield from _json_strings(v)


def _text_of(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _lines_of(p: Path) -> set[str]:
    """The normalised lines of a file, and, for JSON, those of every string in it (candidate patches, labels)."""
    raw = _text_of(p)
    if raw is None:
        return set()
    texts = [raw]
    if p.suffix in (".json", ".jsonl"):
        for chunk in (jsonl_lines(raw) if p.suffix == ".jsonl" else [raw]):
            try:
                texts += list(_json_strings(json.loads(chunk))) if chunk.strip() else []
            except ValueError:
                pass
    return {_norm_line(x) for t in texts for x in t.splitlines()}


def labeler_index(root: Path, families: tuple[str, ...] | None = None, *, tasks_root: Path | None = None) -> dict:
    """Fingerprints of the forbidden material in the checkout at ``root``, for the content scans of the labeler profile.

    * ``lines``: the distinctive lines (at least 24 characters, with a word of three letters, compared as
      :func:`_norm_line` normalises them) of the forbidden files, each with the repository-relative files that hold it,
      except lines that also occur in an allowed input of any family (the reference contracts, the base snapshots, the
      harness API, the lint rules and the synthetic example);
    * ``names``: the test functions defined in forbidden verifiers, except names that occur in an allowed input;
    * ``candidates``: the candidate ids, except those that occur in an allowed input (a contract id equals the id of the
      reference candidate);
    * ``allowed_lines``: the normalised lines of the allowed inputs (a path in such a line of a tool output is part of
      an allowed input, not an exposure).

    Forbidden files: every verifier directory of every family (the labelers' tests included: one family's labeler is
    forbidden for another, and a writer's own lines are told apart when the transcript is scanned), the candidates, the
    labels, the mappings of the contracts, and ``data/controlled``. ``results/`` and the strata are covered by the path
    rules only.

    The families are the task directories under ``tasks_root`` (by default ``<root>/tasks``); with ``tasks_root``, each
    family's base snapshot is where :func:`tracecontract.roots.snapshot_dir` puts it (``data/natural/snapshots/<id>`` for
    a natural PR-review task).
    """
    root = Path(root) if tasks_root is None else Path(root).resolve()
    troot = Path(tasks_root).resolve() if tasks_root is not None else root / "tasks"
    fams = families if families is not None else tuple(sorted(p.parent.name for p in troot.glob("*/task.json")))
    allowed_files: list[Path] = []
    for f in fams:
        allowed_files += [troot / f / "contracts" / "reference.json"]
        snap = root / "snapshots" / f if tasks_root is None else snapshot_dir(troot / f, repo=root)
        allowed_files += [p for p in snap.rglob("*") if p.is_file()]
    allowed_files += [root / "src/tracecontract/sandbox/harness/tc_sandbox.py", root / "src/tracecontract/verifier.py"]
    allowed_files += [p for p in (root / "tests/fixtures/harbor_fx01/tasks/FX-01/verifiers/v1").rglob("*") if p.is_file()]
    # The candidate ids an allowed input names. An id matches only as a whole run of [\w-] characters, so one pass of the
    # combined pattern over each file finds every id that a search of the files' concatenation would.
    all_cands = sorted({p.stem for f in fams for p in (troot / f / "candidates").glob("*.json")})
    cand_re = re.compile(rf"(?<![\w-])(?:{'|'.join(map(re.escape, sorted(all_cands, key=len, reverse=True)))})(?![\w-])")
    allowed_lines: set[str] = set()
    allowed_names: set[str] = set()
    allowed_cands: set[str] = set()
    for p in allowed_files:
        if p.is_file():
            allowed_lines |= _lines_of(p)
            text = _text_of(p) or ""
            allowed_names.update(_TEST_NAME.findall(text))
            if all_cands:
                allowed_cands.update(m.group(0) for m in cand_re.finditer(text))
    forbidden_files: list[Path] = []
    for f in fams:
        t = troot / f
        forbidden_files += [p for p in (t / "verifiers").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        forbidden_files += [p for d in ("candidates", "labels") for p in (t / d).rglob("*") if p.is_file()]
        forbidden_files += sorted((t / "contracts").glob("mapping*.json"))
    forbidden_files += [p for p in (root / "data" / "controlled").rglob("*") if p.is_file()]
    lines: dict[str, list[str]] = {}
    names: dict[str, list[str]] = {}
    for p in forbidden_files:
        rel = p.relative_to(root).as_posix()
        for s in _lines_of(p):
            if _distinctive(s) and s not in allowed_lines:
                lines.setdefault(s, []).append(rel)
        raw = _text_of(p) or ""
        found = re.findall(r"def (test_\w+)", raw) if p.suffix == ".py" else [m.split("::")[-1] for m in _CHECK_NAME.findall(raw)]
        for n in found:
            if n not in allowed_names:
                names.setdefault(n, []).append(rel)
    cands = [c for c in all_cands if c not in allowed_cands]
    return {"families": list(fams), "lines": {k: sorted(set(v)) for k, v in lines.items()},
            "names": {k: sorted(set(v)) for k, v in names.items()}, "candidates": cands,
            "files": len(forbidden_files), "allowed_lines": allowed_lines}


def _sources(srcs: list[str], task: str, names: bool = False, task_rel: str | None = None) -> list[str]:
    """The forbidden files among ``srcs`` (repository-relative) for a writer of ``task``, most relevant first: its family
    before others, then reference checks, other verifiers, candidates, labels and the controlled sessions' records. The
    writer's own tests are not forbidden, and for test names neither is the coordinator's spec of its labeler, which
    lists them. ``task_rel`` is the task directory relative to the checkout (by default ``tasks/<task>``)."""
    tr = task_rel or f"tasks/{task}"
    own = f"{tr}/verifiers/independent_label/" + ("" if names else "tests/")
    rank = lambda x: (not x.startswith(f"{tr}/"), next((i for i, k in enumerate(  # noqa: E731
        ("/verifiers/reference_check/", "/verifiers/", "/candidates/", "/labels/", "data/controlled/")) if k in x), 5), x)
    return sorted((x for x in srcs if not x.startswith(own)), key=rank)


def _candidate_re(index: dict) -> re.Pattern:
    ids = sorted(index.get("candidates", []), key=len, reverse=True)
    alts = "|".join(map(re.escape, ids))
    return re.compile(rf"(?<![\w-])(?:{alts})(?![\w-])|{_FRESH_ID.pattern}" if alts else _FRESH_ID.pattern)


def _content_findings(text: str, index: dict, own_lines: set[str], own_names: set[str], task: str,
                      cand: re.Pattern, layout: LabelerLayout | None = None) -> list[tuple[str, str, int]]:
    """Forbidden text in ``text``: ``(what, why, offset)`` for each distinctive line of a forbidden file, test name of a
    forbidden verifier and candidate id it holds, except what the agent's own text (``own_lines``, ``own_names``) or the
    own tests directory of ``task`` also holds."""
    lay = layout or labeler_layout(task, REPO)
    tr = os.path.relpath(lay.task_dir, REPO)
    what = lambda rel: _labeler_direct(f"{REPO}/{rel}", task, REPO, HOME, (), lay)[1]  # noqa: E731
    out, seen, pos = [], set(), 0
    for line in text.splitlines(keepends=True):
        s = _norm_line(line)
        srcs = _sources(index["lines"].get(s, []), task, task_rel=tr) if s not in own_lines else []
        if srcs and srcs[0] not in seen:
            seen.add(srcs[0])
            out.append((srcs[0], "text of " + what(srcs[0]), pos))
        pos += len(line)
    for m in _TEST_NAME.finditer(text):
        n = m.group(0)
        srcs = _sources(index["names"].get(n, []), task, names=True, task_rel=tr)
        if srcs and n not in own_names and n not in seen:
            seen.add(n)
            out.append((n, f"the name of a test in {what(srcs[0])} ({srcs[0]})", m.start()))
    for m in cand.finditer(text):
        if m.group(0) not in own_names and m.group(0) not in seen:
            seen.add(m.group(0))
            out.append((m.group(0), "a candidate id", m.start()))
    return out


def _excerpt(text: str, at: int, width: int = 150) -> str:
    """The line of ``text`` that holds offset ``at``, cut to ``width`` characters on either side of it."""
    a = max(text.rfind("\n", 0, at) + 1, at - width)
    b = text.find("\n", at)
    return text[a:min(len(text) if b < 0 else b, at + width)]


def _own_text(ti: dict) -> str:
    """Every string of a tool input: what the agent wrote itself."""
    return "\n".join(_json_strings(ti))


def _written_checks(path: Path, own: str) -> set[str]:
    """The check ids (``file.py::test_x``) of the test files that a transcript wrote into its tests directory ``own``."""
    found: set[str] = set()

    def add(target: str, body: str) -> None:
        p = _norm(target, REPO)
        if _inside(p, own) and p.endswith(".py"):
            found.update(f"{os.path.relpath(p, own)}::{n}" for n in re.findall(r"^\s*def (test_\w+)", body, re.M))

    for _, _, tool, ti in _tool_calls(path):
        if tool == "Write":
            add(str(ti.get("file_path", "")), str(ti.get("content", "")))
        elif tool == "Edit":
            add(str(ti.get("file_path", "")), str(ti.get("new_string", "")))
        elif tool == "MultiEdit":
            add(str(ti.get("file_path", "")), "\n".join(str(e.get("new_string", "")) for e in ti.get("edits") or []))
        elif tool == "Bash" and isinstance(ti.get("command"), str):
            for m in _HEREDOC_FILE.finditer(ti["command"]):
                add(m.group(1), m.group(3))
    return found


def revision_input(prompt: str, writer_prompt: str, *, checks: set[str] | None, requirements: set[str]) -> dict:
    """What a revision's prompt told the reviser beyond the writer's own prompt (protocol §15.5: names of failing checks only).

    The lines of ``prompt`` that the writer's prompt does not hold are split into listed items (``[<kind>: ]<check id or
    requirement id>``, one per line) and instruction lines. ``more_than_names`` is set when an item carries a kind (what
    the check failed on), names a check that is not among ``checks`` (the writer's own, when known) or a requirement that
    is not in the contract, or when an instruction line holds grading text (a check name, a candidate id, a message, a
    traceback, an outcome, a count of passing or failing checks, or the coordinator's notes).
    """
    known = {x.strip() for x in writer_prompt.splitlines()}
    items, kinds, unknown, grading = [], {}, [], []
    for line in prompt.splitlines():
        s = line.strip()
        if not s or s in known:
            continue
        m = _LISTED.fullmatch(s)
        if m:
            name = m.group("name")
            items.append(name)
            if m.group("kind"):
                kinds[name] = m.group("kind")
            if (name.startswith("R-") and name not in requirements) or (not name.startswith("R-") and checks is not None
                                                                         and name not in checks):
                unknown.append(name)
            continue
        hits = [x.group(0) for x in _GRADING.finditer(s)] + _CHECK_NAME.findall(s) + _TEST_NAME.findall(s)
        hits += _FRESH_ID.findall(s) + _GRADED_ID.findall(s)
        if hits:
            grading.append({"line": s[:300], "matched": sorted(set(hits))})
    return {"listed": items, "kinds": kinds, "unknown_names": unknown, "grading_text": grading,
            "more_than_names": bool(kinds or unknown or grading)}


def _user_texts(rows: list[dict]) -> tuple[list[str], list[str]]:
    """``(prompts, reminders)``: the user-role texts that are not tool results, apart from harness reminders."""
    prompts, reminders = [], []
    for e in rows:
        if e.get("type") != "user":
            continue
        c = e.get("message", {}).get("content")
        blocks = [c] if isinstance(c, str) else [x.get("text", "") for x in c or [] if isinstance(x, dict) and x.get("type") == "text"]
        for b in blocks:
            (reminders if b.lstrip().startswith("<system-reminder>") else prompts).append(b)
    return prompts, reminders


def audit_labeler_transcript(path: Path, *, task: str, index: dict, round_no: int = 1, writer: Path | None = None,
                             families: tuple[str, ...] = (), requirements: set[str] | None = None, repo: str = REPO,
                             home: str = HOME, extra_forbidden: tuple[str, ...] = (),
                             layout: LabelerLayout | None = None, writer_own: str | None = None) -> dict:
    """The labeler-writer profile of the strict audit for one transcript (protocol §15.5, D55; see the module docstring).

    ``index`` is :func:`labeler_index` of the checkout. ``writer`` is, for a revision (``round_no`` 2), the transcript of
    the same family's first round: its tool inputs count as the reviser's own text, the check ids it wrote (in its own
    tests directory, ``writer_own``; by default the revision's) are the names the revision may be told, and its prompt is
    the baseline of :func:`revision_input`. A natural writer and its revision work in workspaces of their own, so
    ``writer_own`` is the writer's ``<workspace>/tests``. The result holds the tool calls
    by tool, the prompt check, the hits in tool inputs (every access that is forbidden, documentation or outside the
    allowed inputs, reads and listings of ``/tmp`` other than of files the agent wrote there, writes outside the agent's
    own directory, CLI calls other than ``lint-tests``, searches rooted at an unresolved variable, tools other than the
    file tools and the shell, and forbidden material, documentation or a candidate id named anywhere in a tool input or
    in the final report), the exposures in tool outputs, the harness context, the counts of accesses by category, and,
    as leads for the review, the agent's own text that also occurs in forbidden material. ``layout`` places the family's
    material and the writer's own directory (:class:`LabelerLayout`; by default the controlled tasks' layout); for a
    natural task the result also names the writer's workspace (``own_workspace``).
    """
    rows = [json.loads(line) for line in jsonl_lines(path.read_text(encoding="utf-8")) if line.strip()]
    prompts, reminders = _user_texts(rows)
    prompt = prompts[0] if prompts else ""
    cand = _candidate_re(index)
    lay = layout or labeler_layout(task, repo)
    own_dir = labeler_own(task, repo, layout=lay)
    cls = lambda p, op="read", pruned=(): labeler_classify(p, task, op=op, families=families, repo=repo, home=home,  # noqa: E731
                                                           extra_forbidden=extra_forbidden, pruned=pruned, layout=lay)
    own_lines: set[str] = set()
    own_names: set[str] = set()

    def own_add(text: str) -> None:
        own_lines.update(_norm_line(x) for x in text.splitlines())
        own_names.update(_TEST_NAME.findall(text))

    writer_prompt, checks = "", None
    if writer is not None:
        wrows = [json.loads(line) for line in jsonl_lines(writer.read_text(encoding="utf-8")) if line.strip()]
        writer_prompt = (_user_texts(wrows)[0] or [""])[0]
        checks = _written_checks(writer, writer_own or own_dir)
        for _, _, _, ti in _tool_calls(writer):
            own_add(_own_text(ti))
        own_names.update(c.split("::")[-1] for c in checks)
    # The prompt: forbidden text in it, the paths it names, and for a revision what it told beyond names.
    findings = _content_findings("\n".join(prompts), index, set(), own_names, task, cand, lay)
    named = []
    for m in _LITERAL_PATH.finditer("\n".join(prompts)):
        tok = m.group(0).rstrip(".,:;")
        p = _norm(tok, repo)
        c, why = cls(p)
        if c in _FLAGGED_CATEGORIES and not any(x["path"] == p for x in named):
            named.append({"path": p, "category": c, "why": why})
    prompt_block: dict = {"sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "chars": len(prompt),
                          "later_prompts": len(prompts) - 1, "forbidden_content": [
                              {"what": w, "why": "in the prompt: " + why, "text": _excerpt("\n".join(prompts), at)}
                              for w, why, at in findings],
                          "paths_named": named}
    if round_no > 1:
        prompt_block["revision_input"] = revision_input(prompt, writer_prompt, checks=checks, requirements=requirements or set())
    for t in prompts:
        own_add(t)
    # The harness context: the system prompt, reminders, environment and other attachments the agent was given.
    harness: dict = {"attachments": {}, "reminders": len(reminders), "forbidden_content": [], "forbidden_paths_named": []}
    ctx: list[tuple[str, str]] = [("reminder", r) for r in reminders]
    for e in rows:
        if e.get("type") == "attachment":
            kind = str((e.get("attachment") or {}).get("type"))
            harness["attachments"][kind] = harness["attachments"].get(kind, 0) + 1
            ctx += [(kind, s) for s in _json_strings(e.get("attachment"))]
    for kind, s in ctx:
        for w, why, at in _content_findings(s, index, own_lines, own_names, task, cand, lay):
            harness["forbidden_content"].append({"what": w, "why": f"in the harness context ({kind}): {why}", "text": _excerpt(s, at)})
        for m in _LITERAL_PATH.finditer(s):
            p = _norm(m.group(0).rstrip(".,:;"), repo)
            c, why = cls(p) if m.group(0).startswith(("/", "~")) else ("", "")
            if c == "forbidden" and not any(x["path"] == p for x in harness["forbidden_paths_named"]):
                harness["forbidden_paths_named"].append({"path": p, "where": kind, "why": why, "text": _excerpt(s, m.start())})
    # Tool inputs, in order; each tool result is scanned when it comes, against the agent's own text up to then.
    s = parse_claude_code_jsonl(path, population=Population.controlled, source="audit", include_sidechains=True)
    results = {ev.tool_call_id: ev for ev in s.events if ev.kind == EventKind.tool_result}
    counts: dict[str, int] = {}
    accesses: dict[str, int] = {}
    hits: list[dict] = []
    exposures: list[dict] = []
    calls: dict = {}
    written: list[str] = []  # paths the agent wrote: reading back its own file in /tmp is not flagged again
    carried = repo
    for ev in s.events:
        if ev.kind == EventKind.tool_result:
            tool, call_id, ends = calls.get(ev.tool_call_id, (None, None, []))
            if tool in _EDIT_TOOLS or tool in _HANDBACK or not ev.text:
                continue  # it only confirms the write of its input path, or the delivery of the final report
            found: dict = {}
            for m in _LITERAL_PATH.finditer(ev.text):
                end = ev.text.find("\n", m.end())
                line = ev.text[ev.text.rfind("\n", 0, m.start()) + 1:len(ev.text) if end < 0 else end]
                if _norm_line(line) in index.get("allowed_lines", ()):
                    continue  # a path in a line of an allowed input (the lint rules name the session directories)
                tok = m.group(0).rstrip(".,:;")
                for p in [_norm(tok, repo)] if tok.startswith(("/", "~")) else [_norm(tok, e) for e in ends]:
                    c, why = cls(p)
                    if c == "forbidden":
                        found.setdefault((p, "shown in a tool output: " + why), m.start())
                        break
            for w, why, at in _content_findings(ev.text, index, own_lines, own_names, task, cand, lay):
                found.setdefault((w, "shown in a tool output: " + why), at)
            for (p, why), at in found.items():
                exposures.append({"event_id": ev.event_id, "ts": ev.timestamp, "call": call_id, "tool": tool, "path": p,
                                  "why": why, "text": _excerpt(ev.text, at)})
            continue
        if ev.kind != EventKind.tool_call:
            continue
        tool, ti = ev.tool_name or "", ev.tool_input or {}
        counts[tool] = counts.get(tool, 0) + 1
        res = results.get(ev.tool_call_id)
        denied = bool(res is not None and "Permission for this action was denied" in (res.text or "")[:300])
        ops: list[tuple[str, str, str, tuple]] = []
        bases, ends, unresolved = [repo, carried], [], []
        cmd = ti.get("command") if tool == "Bash" and isinstance(ti.get("command"), str) else ""
        if tool == "Read" and ti.get("file_path"):
            ops.append(("read", _norm(str(ti["file_path"]), repo), str(ti["file_path"]), ()))
        elif tool in _EDIT_TOOLS and (ti.get("file_path") or ti.get("notebook_path")):
            fp = str(ti.get("file_path") or ti.get("notebook_path"))
            ops.append(("write", _norm(fp, repo), fp, ()))
        elif tool == "Grep":
            ops.append(("search", _norm(str(ti.get("path") or "."), repo), json.dumps(ti)[:300], ()))
        elif tool == "Glob":
            # The listing's root: the path joined with the pattern's leading components that hold no wildcard.
            pattern, static = str(ti.get("pattern") or ""), []
            for part in pattern.split("/"):
                if any(ch in part for ch in "*?[{"):
                    break
                static.append(part)
            root = "/" + "/".join(static[1:]) if pattern.startswith("/") else os.path.join(str(ti.get("path") or "."), *static)
            ops.append(("list", _norm(root, repo), json.dumps(ti)[:300], ()))
        elif cmd:
            starts = list(dict.fromkeys([repo, carried]))
            ops, unresolved, bases, ends = _labeler_shell(cmd, starts, cand)
            carried = ends[-1] if carried != repo and len(ends) > 1 else ends[0]
        elif tool not in _HANDBACK:
            hits.append({"event_id": ev.event_id, "ts": ev.timestamp, "tool": tool, "op": "tool", "path": tool,
                         "category": "outside", "why": "a tool other than the file tools and the shell", "text": json.dumps(ti)[:300],
                         **({"denied": True} if denied else {})})
        calls[ev.tool_call_id] = (tool, ev.event_id, ends)
        seen = set()
        for op, p, text, pruned in ops:
            if op == "cli":
                hits.append({"event_id": ev.event_id, "ts": ev.timestamp, "tool": tool, "op": op, "path": p, "category": "outside",
                             "why": "a CLI call other than lint-tests", "text": text, **({"denied": True} if denied else {})})
                continue
            if op == "candidate":
                hits.append({"event_id": ev.event_id, "ts": ev.timestamp, "tool": tool, "op": op, "path": p, "category": "forbidden",
                             "why": "a candidate named in a CLI call", "text": text, **({"denied": True} if denied else {})})
                continue
            c, why = cls(p, op, pruned)
            accesses[c] = accesses.get(c, 0) + 1
            if op == "write":
                written.append(p)
            flag = (c in _FLAGGED_CATEGORIES or (op == "write" and c not in ("own", "system"))
                    or (c == "tmp" and op in ("read", "list", "search") and not any(_inside(p, w) for w in written)))
            if flag and (p, op) not in seen:
                seen.add((p, op))
                if op == "write" and c not in _FLAGGED_CATEGORIES:
                    why = "a write outside its own tests directory: " + why
                hits.append({"event_id": ev.event_id, "ts": ev.timestamp, "tool": tool, "op": op, "path": p, "category": c,
                             "why": why, "text": text, **({"denied": True} if denied else {})})
        for tok, text, head in unresolved:
            if cls(head, "search")[0] == "forbidden" or cls(head)[0] in _FLAGGED_CATEGORIES:
                hits.append({"event_id": ev.event_id, "ts": ev.timestamp, "tool": tool, "op": "search", "path": tok,
                             "category": "forbidden", "why": "search rooted at an unresolved variable", "text": text,
                             **({"denied": True} if denied else {})})
        # Forbidden material or documentation named anywhere in the input (heredoc bodies, inline code, written content,
        # the final report): a fail-safe for what the parsers cannot see. A relative path counts only if it lands there
        # from every directory the command may run in.
        texts = [_EXCLUSION_ARG.sub(" ", "\n".join(_split_unquoted(cmd)))] if cmd else []
        texts += [str(v) for k, v in ti.items() if k != "command" and isinstance(v, str)]
        texts += [str(e.get("new_string", "")) for e in ti.get("edits") or [] if isinstance(e, dict)]
        for text in texts:
            for m in _LITERAL_PATH.finditer(text):
                tok = m.group(0).rstrip(".,:;")
                tok = tok.split("=", 1)[1] if re.match(r"[A-Za-z_]\w*=", tok) else tok  # VAR=/path
                resolved = [_norm(tok, repo)] if tok.startswith(("/", "~")) else [_norm(tok, b) for b in bases]
                verdicts = [cls(r) for r in resolved]
                if all(v[0] in ("forbidden", "doc") for v in verdicts):
                    p, (c, why) = resolved[0], verdicts[0]
                    if not any(h["event_id"] == ev.event_id and (_inside(p, h["path"]) or _inside(h["path"], p)) for h in hits):
                        hits.append({"event_id": ev.event_id, "ts": ev.timestamp, "tool": tool, "op": "named", "path": p,
                                     "category": c, "why": "named in the tool input: " + why,
                                     "text": text[max(0, m.start() - 80): m.end() + 80], **({"denied": True} if denied else {})})
            # A candidate id typed anywhere (a writer can only know one from forbidden material).
            for m in cand.finditer(text):
                if not any(h["event_id"] == ev.event_id and m.group(0) in h["path"] for h in hits):  # not in a flagged path
                    hits.append({"event_id": ev.event_id, "ts": ev.timestamp, "tool": tool, "op": "named", "path": m.group(0),
                                 "category": "forbidden", "why": "named in the tool input: a candidate id",
                                 "text": text[max(0, m.start() - 80): m.end() + 80], **({"denied": True} if denied else {})})
        own_add(_own_text(ti))
    flagged = bool(hits or exposures or prompt_block["forbidden_content"] or harness["forbidden_content"]
                   or prompt_block.get("revision_input", {}).get("more_than_names"))
    # Leads for the review, not flags: what the agent wrote itself that is also in forbidden material (the output scan
    # leaves text the agent wrote first aside).
    own_writing = "\n".join(_own_text(ti) for _, _, tool, ti in _tool_calls(path) if tool in _EDIT_TOOLS or tool == "Bash")
    coincide = {"lines": [], "test_names": []}
    tr = os.path.relpath(lay.task_dir, REPO)
    for line in dict.fromkeys(_norm_line(x) for x in own_writing.splitlines()):
        srcs = _sources(index["lines"].get(line, []), task, task_rel=tr)
        if srcs:
            coincide["lines"].append({"line": line[:150], "also_in": srcs[:3], "files": len(srcs)})
    for n in sorted({c.split("::")[-1] for c in _written_checks(path, own_dir)}):
        srcs = _sources(index["names"].get(n, []), task, names=True, task_rel=tr)
        if srcs:
            coincide["test_names"].append({"name": n, "also_in": srcs[:3], "files": len(srcs)})
    out = {"task_id": task, "round": round_no, "transcript_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
           "tool_calls": dict(sorted(counts.items())), "tool_calls_total": sum(counts.values()),
           "denied_calls": sum(1 for ev in s.events if ev.kind == EventKind.tool_result
                               and "Permission for this action was denied" in (ev.text or "")[:300]),
           "own_checks": sorted(_written_checks(path, own_dir)), "prompt": prompt_block,
           "accesses": dict(sorted(accesses.items())), "hits": hits, "exposures": exposures, "harness_context": harness,
           "own_text_also_in_forbidden_material": coincide, "flagged": flagged}
    if lay.natural:
        out = {**dict(list(out.items())[:2]), "own_workspace": lay.workspace, **dict(list(out.items())[2:])}
    return out


def _redact_labeler(x, scratch: str | None):
    """:func:`_redact_output`, after the session's directories are replaced by ``<scratchpad>``, ``<session-tmp>`` and
    ``<session-dir>`` (the build session's scratch directory, its temporary directory, its directory of agent records,
    where :data:`SESSION_ROOTS` puts them)."""
    if isinstance(x, str):
        x = x.replace(scratch, "<scratchpad>") if scratch else x
        x = SESSION_ROOTS.scratch().sub("<scratchpad>", x)
        x = SESSION_ROOTS.session_dir().sub("<session-dir>", SESSION_ROOTS.session_tmp().sub("<session-tmp>", x))
        return _redact_output(x, None)
    if isinstance(x, list):
        return [_redact_labeler(v, scratch) for v in x]
    if isinstance(x, dict):
        return {k: _redact_labeler(v, scratch) for k, v in x.items()}
    return x


def _labeler_label(p: Path, task: str, round_no: int) -> str:
    """The agent's label from the ``.meta.json`` beside its transcript (only that field is read), or a default."""
    meta = p.with_name(p.stem + ".meta.json")
    try:
        label = json.loads(meta.read_text(encoding="utf-8")).get("description")
    except (OSError, ValueError, AttributeError):
        label = None
    return str(label) if label else f"L-{'write' if round_no == 1 else 'revise'}-{task}"


def recorded_workspace(task_dir: Path, sha256: str) -> str | None:
    """The own workspace that the task's ``labels/generator_audit.json`` records for the agent whose transcript has this
    sha256 (``own_workspace``, as ``scripts/audit_eval_generators.py --task-dir`` writes it), or None."""
    try:
        data = json.loads((Path(task_dir) / "labels" / "generator_audit.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for role, rec in data.items() if isinstance(data, dict) else ():
        if role == "_rules" or not isinstance(rec, dict) or not isinstance(rec.get("own_workspace"), str):
            continue
        many = rec.get("transcripts_sha256")
        shas = [rec.get("transcript_sha256"), rec.get("writer_transcript_sha256"), *(many.values() if isinstance(many, dict) else ())]
        if sha256 in shas:
            return rec["own_workspace"]
    return None


def _task_layout(root: Path, tasks_root: Path, task: str, workspace: str | None = None) -> LabelerLayout:
    """The layout of the family ``task`` under ``tasks_root`` in the checkout at ``root``, as the agent saw it (under
    :data:`REPO`): its task directory, its snapshot root (:func:`tracecontract.roots.snapshot_root`) and, for a natural
    PR-review task, the writer's own ``workspace``."""
    td = Path(tasks_root) / task
    base = Path(root).resolve()
    rel_td = os.path.relpath(td.resolve(), base)
    rel_snap = os.path.relpath(snapshot_root(td, repo=base).resolve(), base)
    if rel_td.startswith("..") or rel_snap.startswith(".."):
        raise SystemExit(f"{td}: the task directory and its snapshot root must lie in the checkout {base}")
    natural = is_natural_pr(td)
    return labeler_layout(task, REPO, task_dir=f"{REPO}/{rel_td}", snapshot_root=f"{REPO}/{rel_snap}",
                          workspace=workspace if natural else None, natural=natural)


def _shown(p: str) -> str:
    """A path of the rules as the report shows it: relative to the repository when inside it."""
    return os.path.relpath(p, REPO) if _inside(p, REPO) else p


def audit_labelers(writers: list[tuple[str, str]], revisions: list[tuple[str, str]], *, root: Path,
                   transcripts: list[Path], scratch: str | None = None, tasks_root: Path | None = None) -> dict:
    """The labeler-writer report (see the module docstring): ``writers`` and ``revisions`` are ``(task, path or sha256)``.

    ``tasks_root`` is the directory of the families' task directories (by default ``<root>/tasks``); a natural PR-review
    family's writer is audited in its own workspace, which the family's ``labels/generator_audit.json`` records for its
    transcript (:func:`recorded_workspace`)."""
    by_sha = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in transcripts}
    troot = Path(tasks_root).resolve() if tasks_root is not None else None
    index = labeler_index(root) if troot is None else labeler_index(root, tasks_root=troot)
    fams = tuple(index["families"])
    extra = (os.path.normpath(scratch),) if scratch else ()

    def find(ref: str) -> Path | None:
        if re.fullmatch(r"[0-9a-f]{64}", ref):
            return by_sha.get(ref)
        return Path(ref) if Path(ref).is_file() else None

    tasks = list(dict.fromkeys(t for t, _ in writers + revisions))
    layouts = {t: None if troot is None else _task_layout(root, troot, t) for t in tasks}
    out: dict = {"script": "scripts/strict_reaudit.py --labeler", "profile": LABELER_PROFILE,
                 "rules": {
                     "allowed": {t: [{"path": _shown(p), "what": w} for p, w in labeler_allowed(t, layout=layouts[t])]
                                 for t in tasks},
                     "own": "tasks/<task>/verifiers/independent_label/tests/ (written and read back)",
                     "system": "system locations, the study's virtual environment, and /tmp outside the Claude session "
                               "directories (its reads and listings are flagged)",
                     "forbidden": "the reference solution (the reference candidate and its patch); the reference checks; every "
                                  "other verifier, of any family, and the coordinator's grading status of the labeler; "
                                  "candidates and strata; labels; the mappings of generated verifiers; data/controlled (the "
                                  "controlled sessions' records); results/; the sealed directory; third-party data; the old "
                                  "workspaces; every Claude session directory; and any search or listing over them",
                     "doc": "docs/, paper/, experiments/, README.md and STATUS.md: judged by what each read showed",
                     "outside": "every other path; judged by what each read showed",
                     "outputs": "paths in forbidden material, candidate ids, and the text of forbidden files (distinctive lines "
                                "and test names, from labeler_index) shown in a tool output, except text the agent wrote first",
                     "prompt": "the prompt is scanned for the text of forbidden files; a revision's prompt may carry nothing but "
                               "the names of the failing checks"},
                 "index": {"forbidden_files": index["files"], "distinctive_lines": len(index["lines"]),
                           "test_names": len(index["names"]), "candidate_ids": len(index["candidates"])},
                 "transcripts": {}, "families": {}, "flagged": [], "not_audited": []}
    if any(lay is not None and lay.natural for lay in layouts.values()):
        out["rules"]["natural"] = (
            "a natural PR-review family lies in data/natural/tasks/<task>, its base snapshot in data/natural/snapshots; its "
            "writer works in its own workspace (own_workspace, from the agent's record in labels/generator_audit.json), "
            "whose copies of its inputs are allowed and whose tests/ and scratch/ are its own; the other agents' "
            "workspaces (beside and above the own one), the private run records and the natural arm's build records "
            "under data/natural are forbidden too; without a recorded workspace, the task's "
            "verifiers/independent_label/tests/ counts as its own and the workspace is outside the allowed inputs")
    first: dict[str, Path] = {}
    for task, ref in writers:
        p = find(ref)
        if p is not None:
            first.setdefault(task, p)
    for round_no, group in ((1, writers), (2, revisions)):
        for task, ref in group:
            p = find(ref)
            label = _labeler_label(p, task, round_no) if p is not None else f"L-{'write' if round_no == 1 else 'revise'}-{task}"
            while label in out["transcripts"]:
                label += "'"
            fam = out["families"].setdefault(task, {"transcripts": [], "flagged": []})
            fam["transcripts"].append(label)
            if p is None:
                out["transcripts"][label] = {"task_id": task, "round": round_no, "error": "transcript not found", "flagged": True}
                out["not_audited"].append(label)
                fam["flagged"].append(label)
                out["flagged"].append(label)
                continue
            contract = (troot or root / "tasks") / task / "contracts" / "reference.json"
            try:
                reqs = {r["req_id"] for r in json.loads(contract.read_text(encoding="utf-8")).get("requirements", [])}
            except (OSError, ValueError, KeyError, TypeError):
                reqs = set()
            lay = layouts[task]
            ws = None
            writer = first.get(task) if round_no > 1 else None
            writer_own, notes = None, []
            if troot is not None and lay is not None and lay.natural:
                ws = recorded_workspace(troot / task, hashlib.sha256(p.read_bytes()).hexdigest())
                lay = _task_layout(root, troot, task, ws)
                if ws is None:
                    notes.append("no record in labels/generator_audit.json names this transcript, so its workspace is "
                                 "unknown: audited with the task's verifiers/independent_label/tests/ as its own")
                if writer is not None:
                    # The writer worked in a workspace of its own: the check names it wrote are collected there.
                    wws = recorded_workspace(troot / task, hashlib.sha256(writer.read_bytes()).hexdigest())
                    writer_own = labeler_own(task, layout=_task_layout(root, troot, task, wws))
                    if wws is None:
                        notes.append("no record names the writer's transcript, so the check names it wrote were looked "
                                     "for in the task's verifiers/independent_label/tests/")
            rec = audit_labeler_transcript(p, task=task, index=index, round_no=round_no, writer=writer, families=fams,
                                           requirements=reqs, extra_forbidden=extra, layout=lay, writer_own=writer_own)
            if notes:
                rec["note"] = "; ".join(notes)
            out["transcripts"][label] = rec
            if rec["flagged"]:
                fam["flagged"].append(label)
                out["flagged"].append(label)
    return _redact_labeler(out, scratch)


def private_report_problem(path: str | Path, repo: Path | None = None) -> str | None:
    """Why a report on natural PR-review tasks may not be written to ``path``, or None. Such a report holds excerpts of
    the tasks' threads and of upstream code (tool inputs and outputs), which stay out of git (protocol §17.4, decision
    log D47): it goes outside the repository, or inside it only where git ignores it (``data/natural/``)."""
    root = (repo or R).resolve()
    target = Path(path).resolve()
    if target != root and root not in target.parents:
        return None
    ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--no-index", str(target)], capture_output=True,
                             check=False)
    if ignored.returncode == 0:
        return None
    return (f"{path}: a report on natural PR-review tasks holds thread text and upstream code; write it outside the "
            "repository or under a git-ignored directory such as data/natural/")


def _natural_tasks(tasks_root: Path | None, tasks: list[str] | None = None) -> list[str]:
    """The natural PR-review tasks among ``tasks`` (by default every task under the tasks root): a task whose directory
    under ``tasks_root`` (by default the repository's ``tasks/``) or under ``data/natural/tasks`` is a natural PR-review
    task, or whose id is a natural family's (``NP-xx``), wherever it lies."""
    roots = [Path(tasks_root) if tasks_root is not None else R / "tasks", R / "data" / "natural" / "tasks"]
    names = tasks if tasks is not None else sorted(p.parent.name for p in roots[0].glob("*/task.json"))
    return [t for t in dict.fromkeys(names) if _NATURAL_ID.fullmatch(t) or any(is_natural_pr(r / t) for r in roots)]


def _natural_records(path: Path) -> bool:
    """Whether a ``labels/generator_audit.json`` holds a record of a natural agent (``profile`` natural-agent:v1)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and any(isinstance(r, dict) and r.get("profile") == NATURAL_PROFILE for r in data.values())


def _natural_reaudit(p: Path, task: str, role: str, sub: str, rec: dict, scratch: str, report: dict | None) -> dict:
    """The strict re-audit of a natural agent's record (``profile`` natural-agent:v1): the natural-agent profile
    (:func:`tracecontract.controlled.audit_natural_agent_transcript`) in the agent's own workspace, as its record names it,
    with the build session's scratch directory forbidden. Every access outside the workspace is a hit, the shared scratch
    directory's included (natural agents have a private scratch directory in their workspace), so no scratch access is
    attributed to its writer; the exposures are part of the entry, since the profile counts them as flags. With
    ``report``, they also go to the ``--outputs`` report."""
    own = rec.get("own_workspace")
    if not isinstance(own, str) or not own:
        print(f"{task} {role} {sub}: the record names no own workspace")
        return {"error": "the record names no own workspace"}
    try:
        hits, exposures = audit_natural_agent_transcript(p, task=task, workspace=own, extra_forbidden=(scratch,),
                                                         session_dirs=(SESSION_ROOTS.tmp, SESSION_ROOTS.records))
    except ValueError as exc:
        print(f"{task} {role} {sub}: {exc}")
        return {"error": str(exc)}
    agent = p.stem.removeprefix("agent-")
    entry = _redact_labeler({"agent": agent, "profile": NATURAL_PROFILE, "own_workspace": own, "hits": hits,
                             "exposures": exposures}, scratch)
    if report is not None:
        report.setdefault(task, {}).setdefault(role, {})[sub] = _redact_labeler(
            {"agent": agent, "profile": NATURAL_PROFILE, "own_workspace": own, "output_exposures": exposures}, scratch)
    print(f"{task} {role} {sub}: {len(hits)} hit(s), {len(exposures)} exposure(s) ({NATURAL_PROFILE})")
    for h in entry["hits"]:
        print("    hit:", h["why"], "|", str(h["text"])[:150])
    for x in entry["exposures"]:
        print("    output:", x["why"], "|", str(x["text"])[:150])
    return entry


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts", action="append")
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--scratch", help="the builder's scratch directory (required for generator transcripts)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--outputs", metavar="FILE", help="also scan tool outputs and write what they showed each agent to FILE "
                    "(JSON), apart from its reads; generator_audit.json never receives them")
    ap.add_argument("--fresh", metavar="ATTEMPTS", help="audit fresh attempts (protocol §16.2) from these attempt records")
    ap.add_argument("--report", metavar="FILE", help="with --fresh, --labeler or --revision: where the report goes (JSON)")
    ap.add_argument("--labeler", metavar="TASK_ID=TRANSCRIPT", action="append", default=[],
                    help="audit the first-round writer of TASK_ID's independent labeler (protocol §15.5); TRANSCRIPT is a "
                         "path or the sha256 of an agent-*.jsonl file under --transcripts (repeatable)")
    ap.add_argument("--revision", metavar="TASK_ID=TRANSCRIPT", action="append", default=[],
                    help="audit the single revision of TASK_ID's independent labeler, as --labeler (repeatable)")
    ap.add_argument("--tasks-root", metavar="DIR", type=Path,
                    help="the directory of the task directories (default: tasks/ of the repository; data/natural/tasks for "
                         "the natural PR-review tasks); for generator transcripts and --labeler/--revision")
    a = ap.parse_args(argv)
    if a.tasks_root is not None and not a.tasks_root.is_dir():
        ap.error(f"--tasks-root {a.tasks_root} is not a directory")
    if a.labeler or a.revision:
        if not a.report or a.write or a.outputs or a.extra or a.fresh:
            ap.error("--labeler and --revision take --report and optionally --transcripts, --scratch and --tasks-root")
        pairs = []
        for spec in (*a.labeler, *a.revision):
            task, sep, ref = spec.partition("=")
            if not sep or not task or not ref:
                ap.error(f"expected TASK_ID=TRANSCRIPT, got {spec!r}")
            pairs.append((task, ref))
        natural = _natural_tasks(a.tasks_root, [t for t, _ in pairs])
        if natural and a.tasks_root is None:
            # The controlled layout would look for them under tasks/ and snapshots/ and count their workspaces as outside.
            ap.error(f"{', '.join(natural)}: natural PR-review task(s); give --tasks-root data/natural/tasks")
        if natural:
            problem = private_report_problem(a.report)
            if problem:
                ap.error(problem)
        files = sorted({p for d in a.transcripts or [] for p in Path(d).rglob("agent-*.jsonl")})
        rep = audit_labelers(pairs[:len(a.labeler)], pairs[len(a.labeler):], root=R, transcripts=files,
                             scratch=os.path.normpath(a.scratch) if a.scratch else None, tasks_root=a.tasks_root)
        Path(a.report).write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        for label, rec in rep["transcripts"].items():
            if "error" in rec:
                print(f"{label}: {rec['error']}")
                continue
            extra = rec["prompt"].get("revision_input", {})
            print(f"{label} ({rec['task_id']}, round {rec['round']}): {rec['tool_calls_total']} tool call(s), "
                  f"{len(rec['hits'])} hit(s), {len(rec['exposures'])} exposure(s), "
                  f"{len(rec['prompt']['forbidden_content'])} forbidden text(s) in the prompt, "
                  f"{len(rec['harness_context']['forbidden_content'])} in the harness context"
                  + ("; the revision's prompt carries more than names" if extra.get("more_than_names") else "")
                  + ("; flagged" if rec["flagged"] else ""))
        print(f"labeler writers: {len(rep['transcripts'])} audited or listed, {len(rep['flagged'])} flagged, "
              f"{len(rep['not_audited'])} not audited")
        return 1 if rep["not_audited"] else 0
    if not a.transcripts:
        ap.error("the following arguments are required: --transcripts")
    if a.fresh:
        if not a.report or a.write or a.outputs or a.extra or a.tasks_root:
            ap.error("--fresh takes --transcripts, --report and optionally --scratch")
        files = sorted({p for d in a.transcripts for p in Path(d).rglob("agent-*.jsonl")})
        fresh = audit_fresh(_attempt_records(Path(a.fresh)), files, os.path.normpath(a.scratch) if a.scratch else None)
        Path(a.report).write_text(json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
        for aid, rec in fresh["attempts"].items():
            print(f"{aid}: " + (rec["error"] if "error" in rec else
                                f"{len(rec['hits'])} hit(s), {len(rec['exposures'])} exposure(s)"
                                + ("; excluded" if rec["flagged"] else "")))
        print(f"fresh attempts: {len(fresh['attempts'])} audited or listed, {len(fresh['excluded'])} excluded, "
              f"{len(fresh['not_audited'])} not audited")
        return 1 if fresh["not_audited"] else 0
    if not a.scratch:
        ap.error("--scratch is required for generator transcripts")
    tasks_root = a.tasks_root if a.tasks_root is not None else R / "tasks"
    audit_files = sorted(tasks_root.glob("*/labels/generator_audit.json"))
    natural_files = [f for f in audit_files if _natural_tasks(tasks_root, [f.parent.parent.name]) or _natural_records(f)]
    if a.outputs and (natural_files or _natural_tasks(a.tasks_root)):
        problem = private_report_problem(a.outputs)
        if problem:
            ap.error(problem)
    for f in natural_files if a.write else []:  # their records hold excerpts of natural agents' tool inputs
        problem = private_report_problem(f)
        if problem:
            ap.error(f"--write: {problem}")
    scratch = os.path.normpath(a.scratch)
    report: dict = {}
    files = sorted({p for d in a.transcripts for p in Path(d).rglob("agent-*.jsonl")}) + [Path(x) for x in a.extra]
    by_sha = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in files}
    writes = sorted(({**o, "agent": p.stem} for p in files for o in _scratch_ops(p, scratch) if o["op"] == "write"),
                    key=lambda o: o["ts"])
    under = lambda p, d: p == d or p.startswith(d + "/")
    for f in audit_files:
        task, data = f.parent.parent.name, json.loads(f.read_text(encoding="utf-8"))
        for role, rec in data.items():
            if role == "_rules":
                continue
            shas = rec.get("transcripts_sha256") or ({"main": rec["transcript_sha256"]} if rec.get("transcript_sha256")
                                                     else {"writer": rec["writer_transcript_sha256"]})
            block = {}
            for sub, sha in shas.items():
                p = by_sha.get(sha)
                if p is None:
                    print(f"{task} {role} {sub}: transcript {sha[:12]} not found")
                    block[sub] = {"error": "transcript not found"}
                    if a.outputs:
                        report.setdefault(task, {}).setdefault(role, {})[sub] = {"error": "transcript not found"}
                    continue
                m = _OUT.search(_prompt_text(p))
                own = rec.get("own_workspace") or (m.group(1) if m else f"{HOME}/gen_workspaces/{task}/{role}")
                if rec.get("profile") == NATURAL_PROFILE:
                    block[sub] = _natural_reaudit(p, task, role, sub, rec, scratch, report if a.outputs else None)
                    continue
                extra = (f"{REPO}/tasks/{task}/verifiers/reference_check",) if role == "refcheck" else ()
                if a.outputs:
                    hits, exposures = audit_generator_transcript_strict(p, task=task, own=own, extra_allowed=extra,
                                                                        extra_forbidden=(scratch,), outputs=True)
                    outside, foreign, n_own_out = classify_scratch_outputs(exposures, p.stem, scratch, writes)
                    report.setdefault(task, {}).setdefault(role, {})[sub] = _redact_output(
                        {"agent": p.stem.removeprefix("agent-"), "own_workspace": own, "extra_allowed": list(extra),
                         "output_exposures": outside, "output_scratch_not_attributed_to_the_agent": foreign,
                         "output_scratch_own": n_own_out}, scratch)
                else:
                    hits = audit_generator_transcript_strict(p, task=task, own=own, extra_allowed=extra, extra_forbidden=(scratch,))
                hits = [h for h in hits if not under(h["path"], scratch)]  # scratch accesses are classified below
                roots, others, n_own = classify_scratch(p, scratch, writes)
                entry = {"agent": p.stem.removeprefix("agent-"), "own_workspace": own, "extra_allowed": list(extra),
                         "hits": hits, "scratch_root_accesses": roots, "scratch_reads_not_attributed_to_the_agent": others,
                         "scratch_reads_of_own_files": n_own}
                block[sub] = _redact(entry, scratch)
                print(f"{task} {role} {sub}: {len(hits)} hit(s), {len(roots)} access(es) to the scratch directory itself, "
                      f"{len(others)} scratch read(s) not attributed to the agent, {n_own} own")
                for h in hits:
                    print("    hit:", h["why"], "|", _redact(h["text"], scratch)[:150])
                for r in roots:
                    print("    scratch directory:", r["op"], r["ts"], _redact(r["text"], scratch)[:120])
                for o in others:
                    print("    scratch:", o["op"], _redact(o["path"], scratch), "| last written by", o["last_written_by"], o.get("last_written_at", ""))
                if a.outputs:
                    shown = report[task][role][sub]
                    print(f"{task} {role} {sub}: tool outputs (not reads): {len(shown['output_exposures'])} exposure(s) outside "
                          f"the scratch directory, {len(shown['output_scratch_not_attributed_to_the_agent'])} scratch path(s) "
                          f"not attributed to the agent, {shown['output_scratch_own']} own")
                    for x in shown["output_exposures"]:
                        print("    output:", x["why"], "|", x["text"][:150])
                    for x in shown["output_scratch_not_attributed_to_the_agent"]:
                        print("    output, scratch:", x["path"], "| last written by", x["last_written_by"], x["last_written_at"] or "")
            old = rec.get("strict_reaudit", {})
            new = {"script": "scripts/strict_reaudit.py", "transcripts": block}
            same = {k: {kk: vv for kk, vv in v.items() if kk != "assessment"} for k, v in old.get("transcripts", {}).items()} == block
            if same and old.get("assessment"):
                new["assessment"] = old["assessment"]
            rec["strict_reaudit"] = new
        if a.write:
            f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if a.outputs:
        out = {"script": "scripts/strict_reaudit.py --outputs",
               "scope": "tool outputs only: paths inside forbidden material and held-out candidate ids other than the "
                        "agent's own that a tool output showed the agent; reads are in generator_audit.json",
               "transcripts": report}
        Path(a.outputs).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
