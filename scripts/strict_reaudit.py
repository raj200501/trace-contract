"""Stricter re-audit of the registered generator transcripts (decision log D44).

Usage: python scripts/strict_reaudit.py --transcripts <dir> [--transcripts <dir> ...]
                                        [--extra <transcript.jsonl> ...] --scratch <dir> [--write]

For every record in ``tasks/*/labels/generator_audit.json`` it finds the transcript(s) the
record names by sha256 among the ``agent-*.jsonl`` files under the ``--transcripts``
directories, and runs two checks on each:

1. :func:`tracecontract.controlled.audit_generator_transcript_strict`, which resolves the
   paths in tool inputs instead of matching substrings. The agent's own workspace is the
   ``--out`` directory of the ``export-gen-workspace`` command in its prompt; a writer of
   reference checks may also write the task's ``verifiers/reference_check``; and the
   builder's scratch directory (``--scratch``) counts as forbidden.
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

Session ids and session-local paths are redacted in the output (decision log D21). With
``--write`` the results go into each record's ``strict_reaudit`` block; a manual
``assessment`` already there is kept when the hits and scratch findings are unchanged.
Tool outputs are not inspected by the checks. The accesses they flag were assessed by
reading the transcripts, tool outputs included; for a file without a recorded writer, the
writer was found by reading the agent's tool inputs. The other assessments restate the
classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path

from tracecontract.controlled import _VAR, _command_words, _shell_segments, audit_generator_transcript_strict

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
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
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
    for line in path.read_text(encoding="utf-8").splitlines()[:6]:
        e = json.loads(line)
        if e.get("type") == "user":
            c = e["message"]["content"]
            out.append(c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict)))
    return "\n".join(out)


def _redact(x, scratch: str):
    if isinstance(x, str):
        return _SESSION_ID.sub("<session>", x.replace(scratch, "<scratchpad>"))
    if isinstance(x, list):
        return [_redact(v, scratch) for v in x]
    if isinstance(x, dict):
        return {k: _redact(v, scratch) for k, v in x.items()}
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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts", action="append", required=True)
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    scratch = os.path.normpath(a.scratch)
    files = sorted({p for d in a.transcripts for p in Path(d).rglob("agent-*.jsonl")}) + [Path(x) for x in a.extra]
    by_sha = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in files}
    writes = sorted(({**o, "agent": p.stem} for p in files for o in _scratch_ops(p, scratch) if o["op"] == "write"),
                    key=lambda o: o["ts"])
    under = lambda p, d: p == d or p.startswith(d + "/")
    for f in sorted(R.glob("tasks/*/labels/generator_audit.json")):
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
                    continue
                m = _OUT.search(_prompt_text(p))
                own = m.group(1) if m else f"{HOME}/gen_workspaces/{task}/{role}"
                extra = (f"{REPO}/tasks/{task}/verifiers/reference_check",) if role == "refcheck" else ()
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
            old = rec.get("strict_reaudit", {})
            new = {"script": "scripts/strict_reaudit.py", "transcripts": block}
            same = {k: {kk: vv for kk, vv in v.items() if kk != "assessment"} for k, v in old.get("transcripts", {}).items()} == block
            if same and old.get("assessment"):
                new["assessment"] = old["assessment"]
            rec["strict_reaudit"] = new
        if a.write:
            f.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
