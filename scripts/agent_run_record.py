"""The generation record of an agent run, made from its transcript; or one record that combines several runs.

Usage:
  python scripts/agent_run_record.py TRANSCRIPT --config config-A --label LABEL [--workflow WF] [--session-dir DIR]
                                     [--unfinished]
  python scripts/agent_run_record.py --combine RECORD.json RECORD.json [RECORD.json ...]

Prints the record, a ``schemas.GenerationRecord``, as JSON on stdout: the file that ``build-verifier``,
``make-contract`` and ``add-candidate`` take as ``--generation-record``. The record is complete
(``verifier.generation_record_problems`` finds nothing) or nothing is printed and the exit status is 2.

One run. TRANSCRIPT is a subagent transcript of the build session, one JSON entry per line:
* ``run_id``: ``<workflow run id>/<label>``. The workflow run id is the name of the transcript's workflow
  directory (``wf_...``), or ``--workflow`` for an agent outside a workflow (for one inside, ``--workflow`` may only
  repeat its directory's name); the label is ``--label``;
* ``generator``: the configuration label ``--config`` (config-A to config-Z), never a model identifier;
* ``prompt_sha256``: the sha256 of the run's first prompt, the user entries before its first assistant message.
  For a workflow agent that is the computed task text the workflow script gave: the harness relays it in a user
  message under a fixed frame line, with every line indented by two spaces, and the hash is of that text without
  the frame and the indent, which is the template instantiation (the convention of the D55 records). For any other
  agent it is the first user message, verbatim;
* ``started_at`` and ``ended_at``: the earliest and latest entry times; ``wall_s``: the seconds between them. The
  notes give the longest interval between two consecutive entries, and a warning is printed when it exceeds 30
  minutes: wall_s then counts it (an agent resumed later holds two stretches of work in one transcript);
* ``turns``: the assistant messages (the transcript writes one entry per content block, so entries are counted
  once per message id); ``tool_calls``: the tool-use blocks;
* ``run_record``: ``build-session:<the transcript's path relative to the session directory>``, a session-relative
  pointer to the private record. The session directory is the transcript's nearest ancestor named by a session id,
  or ``--session-dir``;
* ``notes``: how the record was made, with the transcript's sha256.

No token count is recorded. Nothing the transcript or its ``.meta.json`` says about the model goes into the record:
those fields are read only to refuse a record whose run id, pointer or notes would hold a model name the
transcript records, or a part of one. A workflow agent for which the workflow's journal shows a start but no
result has not finished (or was stopped); it is refused unless ``--unfinished`` is given, and then the notes say so.

``--combine``: one record for runs made one after another for one artifact, all in one configuration (an audited
verifier: its generator, then its revisers, as the natural recipe's decision-log entry, planned as D61, asks). Each
RECORD is a complete record printed by this script. Turns, tool calls and wall time are summed; ``started_at`` is
the earliest start and ``ended_at`` the latest end; the run ids are joined with ``+`` and the pointers with ``;``, in
start order; ``prompt_sha256`` is that of the first run. The notes list every run with its own times, counts and
prompt hash, name the runs recorded with ``--unfinished``, and keep each run's own notes (its transcript's sha256
and the form of prompt hashed). Refused: runs that overlap in time, a run given twice (the same transcript), and
different runs that share a run id (the same ``--label`` in one workflow: record one again with another label).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tracecontract.schemas import CONFIG_LABEL, GenerationRecord
from tracecontract.verifier import generation_record, generation_record_problems

# The harness frame of a workflow agent's computed task: a fixed first line, then the text, each line indented.
TASK_FRAME = re.compile(r"\[Workflow harness [—-] computed task\]")
TASK_MARKER = "The computed task text follows:"
INDENT = "  "
WORKFLOW_DIR = re.compile(r"wf_[0-9A-Za-z][0-9A-Za-z-]*")
SESSION_DIR = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# Labels and workflow ids: no whitespace, and none of the separators of a run id ("/") or of a combined record
# ("+" for run ids, ";" for pointers).
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
POINTER_PREFIX = "build-session:"
TOOL_BLOCKS = ("tool_use", "server_tool_use", "mcp_tool_use")
UNFINISHED = "the workflow's journal records no result for this agent (recorded with --unfinished)"
GAP_WARNING_S = 1800.0  # a longer interval between two entries is reported: wall_s counts it


class RecordError(ValueError):
    """The transcript, or the records to combine, cannot give a complete generation record."""


# --------------------------------------------------------------------------- reading a transcript


def read_entries(path: Path) -> list[dict[str, Any]]:
    """The transcript's entries; a line that is not a JSON object is refused (the agent may still be writing)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RecordError(f"{path.name}: cannot be read ({exc.__class__.__name__})") from None
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            raise RecordError(f"{path.name}: line {n} is not JSON (is the agent still writing it?)") from None
        if not isinstance(entry, dict):
            raise RecordError(f"{path.name}: line {n} is not a JSON object")
        rows.append(entry)
    if not rows:
        raise RecordError(f"{path.name}: the transcript is empty")
    return rows


def _time(value: Any, where: str) -> datetime:
    try:
        t = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        t = None
    if t is None or t.tzinfo is None:
        raise RecordError(f"{where}: {value!r} is not an ISO 8601 time with a time zone")
    return t


def entry_span(rows: list[dict[str, Any]]) -> tuple[str, str, float]:
    """The earliest and the latest entry time, as written, and the seconds between them."""
    times = [(_time(e["timestamp"], f"entry {n} timestamp"), e["timestamp"])
             for n, e in enumerate(rows, 1) if "timestamp" in e]
    if not times:
        raise RecordError("no entry has a timestamp")
    first = min(times, key=lambda t: t[0])
    last = max(times, key=lambda t: t[0])
    return first[1], last[1], round((last[0] - first[0]).total_seconds(), 3)


def longest_gap(rows: list[dict[str, Any]]) -> tuple[float, str, str]:
    """The longest interval between two consecutive entry times, in time order: its seconds and its two ends as
    written (0 and the first time twice for a transcript with one timestamp)."""
    times = sorted(((_time(e["timestamp"], f"entry {n} timestamp"), e["timestamp"])
                    for n, e in enumerate(rows, 1) if "timestamp" in e), key=lambda t: t[0])
    if not times:
        raise RecordError("no entry has a timestamp")
    best = (0.0, times[0][1], times[0][1])
    for (a, a_text), (b, b_text) in pairwise(times):
        if (b - a).total_seconds() > best[0]:
            best = (round((b - a).total_seconds(), 3), a_text, b_text)
    return best


def _content(entry: dict[str, Any]) -> Any:
    message = entry.get("message")
    return message.get("content") if isinstance(message, dict) else None


def _prompt_text(entry: dict[str, Any]) -> str | None:
    """The text of a user entry that is a prompt (not a tool result and not a harness meta entry), else None."""
    if entry.get("type") != "user" or entry.get("isMeta"):
        return None
    content = _content(entry)
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and all(isinstance(b, dict) and b.get("type") == "text" for b in content):
        return " ".join(str(b.get("text", "")) for b in content)
    return None


def computed_task(text: str) -> str:
    """The workflow script's text inside a computed-task frame: the lines after the marker, without their indent."""
    at = text.find(TASK_MARKER)
    if at < 0:
        raise RecordError("the first prompt has a computed-task frame line but no line introducing the task text")
    body = text[at + len(TASK_MARKER):]
    if body and not body.startswith("\n"):
        raise RecordError("the computed-task frame does not end its line before the task text")
    lines = []
    for n, line in enumerate(body[1:].split("\n"), 1):
        if line.startswith(INDENT):
            lines.append(line[len(INDENT):])
        elif line == "":
            lines.append(line)
        else:
            raise RecordError(f"line {n} of the computed task text is not indented as the harness indents every line")
    return "\n".join(lines)


def first_prompt(rows: list[dict[str, Any]]) -> tuple[str, str]:
    """The run's first prompt and what it is: the computed task of a workflow agent, or the first user message."""
    prompts = []
    for e in rows:
        if e.get("type") == "assistant":
            break
        text = _prompt_text(e)
        if text is not None:
            prompts.append(text)
    if not prompts:
        raise RecordError("no user prompt comes before the first assistant message")
    for text in prompts:
        if TASK_FRAME.match(text):
            return computed_task(text), "the workflow's computed task text, without the harness frame and indent"
    return prompts[0], "the first user message, verbatim"


def turns_and_tool_calls(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Assistant messages (entries counted once per message id) and tool-use blocks (once per block id)."""
    messages: set[Any] = set()
    calls: set[Any] = set()
    for n, e in enumerate(rows):
        if e.get("type") != "assistant":
            continue
        raw = e.get("message")
        message = raw if isinstance(raw, dict) else {}
        mid = message.get("id")
        messages.add(mid if isinstance(mid, str) and mid else ("entry", n))
        content = message.get("content")
        for k, block in enumerate(content if isinstance(content, list) else []):
            if isinstance(block, dict) and block.get("type") in TOOL_BLOCKS:
                bid = block.get("id")
                calls.add(bid if isinstance(bid, str) and bid else ("block", n, k))
    return len(messages), len(calls)


def model_words(rows: list[dict[str, Any]], meta: Path) -> set[str]:
    """Every model name that the transcript or its .meta.json records, and each part of one (4 or more characters,
    not only digits), in lower case. They are used only to refuse a record that would hold one."""
    names: list[str] = []

    def collect(d: Any) -> None:
        if isinstance(d, dict):
            names.extend(v for k, v in d.items() if "model" in str(k).lower() and isinstance(v, str))
    for e in rows:
        if e.get("type") == "assistant":
            collect(e)
            collect(e.get("message"))
    if meta.is_file():
        try:
            collect(json.loads(meta.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    words: set[str] = set()
    for name in names:
        low = name.strip().lower()
        if not low or low.startswith("<"):  # e.g. a placeholder for a message the harness made itself
            continue
        words.add(low)
        words |= {w for w in re.split(r"[^a-z0-9]+", low) if len(w) >= 4 and not w.isdigit()}
    return words


def workflow_of(path: Path) -> str | None:
    """The workflow run id: the name of the transcript's directory when it is a workflow directory (``wf_...``)."""
    name = path.resolve().parent.name
    return name if WORKFLOW_DIR.fullmatch(name) else None


def session_pointer(path: Path, session_dir: Path | None) -> str:
    """``build-session:`` and the transcript's path relative to the session directory."""
    p = path.resolve()
    if session_dir is None:
        found = next((a for a in p.parents if SESSION_DIR.fullmatch(a.name)), None)
        if found is None:
            raise RecordError("the transcript is not under a session directory (one named by the session id); "
                              "give --session-dir")
        session_dir = found
    try:
        rel = p.relative_to(session_dir.resolve())
    except ValueError:
        raise RecordError("the transcript is not inside the session directory") from None
    return POINTER_PREFIX + rel.as_posix()


def journal_state(path: Path) -> str | None:
    """``finished`` or ``unfinished`` by the workflow's journal next to the transcript; None without an entry."""
    journal = path.parent / "journal.jsonl"
    agent = path.stem.removeprefix("agent-")
    if not journal.is_file():
        return None
    started = finished = False
    for line in journal.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict) and e.get("agentId") == agent:
            started |= e.get("type") == "started"
            finished |= e.get("type") == "result"
    return "finished" if finished else "unfinished" if started else None


def _complete(**run: Any) -> GenerationRecord:
    try:
        return generation_record(**run)
    except ValueError as exc:
        raise RecordError(str(exc)) from None


def _refuse_model_words(rec: GenerationRecord, words: set[str]) -> None:
    for field, text in (("run id", rec.run_id), ("run-record pointer", str(rec.budget.get("run_record", ""))),
                        ("notes", rec.notes)):
        if any(w in text.lower() for w in words):
            raise RecordError(f"the record's {field} would hold a model name that the transcript records, or a part "
                              "of one; choose another label (or --workflow)")


def run_record(path: Path, *, config: str, label: str, workflow: str | None = None, session_dir: Path | None = None,
               unfinished: bool = False, warn: Callable[[str], None] | None = None) -> GenerationRecord:
    """The complete generation record of the run in transcript ``path`` (``RecordError`` otherwise); ``warn`` is
    told of an interval longer than ``GAP_WARNING_S`` between two consecutive entries."""
    if not CONFIG_LABEL.fullmatch(config or ""):
        raise RecordError(f"--config must be a configuration label, config-A to config-Z (got {config!r})")
    if not NAME.fullmatch(label or ""):
        raise RecordError(f"--label {label!r}: letters, digits and . _ : - only (no whitespace, '/', '+' or ';')")
    inferred = workflow_of(path)
    if workflow and inferred and workflow != inferred:
        raise RecordError(f"--workflow {workflow!r} is not the transcript's workflow directory {inferred!r}")
    wf = workflow or inferred
    if wf is None:
        raise RecordError("the transcript is not in a workflow directory (wf_...); give --workflow")
    if not NAME.fullmatch(wf):
        raise RecordError(f"--workflow {wf!r}: letters, digits and . _ : - only (no whitespace, '/', '+' or ';')")
    rows = read_entries(path)
    state = journal_state(path)
    if state == "unfinished" and not unfinished:
        raise RecordError("the workflow's journal records the agent's start but no result: it is still running or was "
                          "stopped; give --unfinished to record it as it is")
    started, ended, wall = entry_span(rows)
    gap, gap_from, gap_to = longest_gap(rows)
    prompt, prompt_form = first_prompt(rows)
    turns, calls = turns_and_tool_calls(rows)
    notes = (f"made by scripts/agent_run_record.py from the agent's transcript "
             f"(sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}): started_at and ended_at are its first and "
             "last entry times and wall_s the seconds between them; turns counts its assistant messages and tool_calls "
             f"its tool-use blocks; prompt_sha256 is the sha256 of {prompt_form}; no token count; the longest interval "
             f"between two consecutive entries is {gap} s")
    if gap > GAP_WARNING_S:
        notes += f" (from {gap_from} to {gap_to}), which wall_s counts"
        if warn is not None:
            warn(f"the transcript has an interval of {gap} s between two entries (from {gap_from} to {gap_to}): "
                 "wall_s counts it; if the agent was resumed later, its record holds two stretches of work")
    if state == "unfinished":
        notes += "; " + UNFINISHED
    rec = _complete(run_id=f"{wf}/{label}", config=config, prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    started_at=started, ended_at=ended, wall_s=wall, tool_calls=calls, turns=turns,
                    run_record=session_pointer(path, session_dir), notes=notes)
    _refuse_model_words(rec, model_words(rows, path.with_name(path.stem + ".meta.json")))
    return rec


# --------------------------------------------------------------------------- combining records


def load_record(path: Path) -> GenerationRecord:
    try:
        rec = GenerationRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise RecordError(f"{path.name}: not a generation record printed by this script "
                          f"({exc.__class__.__name__}); --combine takes records, not transcripts") from None
    problems = generation_record_problems(rec)
    if problems:
        raise RecordError(f"{path.name}: incomplete generation record: " + "; ".join(problems))
    return rec


def combine(records: list[GenerationRecord]) -> GenerationRecord:
    """One record for runs made one after another in one configuration (``RecordError`` otherwise)."""
    if len(records) < 2:
        raise RecordError("--combine needs the records of two or more runs")
    for rec in records:
        problems = generation_record_problems(rec)
        if problems:
            raise RecordError(f"{rec.run_id}: incomplete generation record: " + "; ".join(problems))
        missing = [k for k in ("turns", "tool_calls") if k not in rec.budget]
        if missing:
            raise RecordError(f"{rec.run_id}: the record has no {' or '.join(missing)}")
    configs = sorted({r.generator for r in records})
    if len(configs) > 1:
        raise RecordError(f"the runs are of different configurations ({', '.join(configs)}); a record names one")
    runs: list[tuple[str, str]] = []  # (run id, pointer) of every run, a combined record's included
    for rec in records:
        ids, pointers = rec.run_id.split("+"), str(rec.budget["run_record"]).split(";")
        if len(ids) != len(pointers):
            raise RecordError(f"{rec.run_id}: its run ids and run-record pointers do not pair up")
        runs += zip(ids, pointers)
    if len({p for _, p in runs}) != len(runs):
        raise RecordError("a run is given twice (the same transcript)")
    ids = [i for i, _ in runs]
    shared = sorted({i for i in ids if ids.count(i) > 1})
    if shared:
        raise RecordError(f"different runs share the run id {', '.join(shared)}: they were recorded with the same "
                          "--label in one workflow; record one of them again with another --label")
    order = sorted(records, key=lambda r: (_time(r.budget["started_at"], r.run_id), _time(r.budget["ended_at"], r.run_id)))
    for a, b in pairwise(order):
        if _time(b.budget["started_at"], b.run_id) < _time(a.budget["ended_at"], a.run_id):
            raise RecordError(f"{b.run_id} starts before {a.run_id} ends: a combined record is for runs made one after "
                              "another (a generator, then its revisers)")
    end = max(order, key=lambda r: _time(r.budget["ended_at"], r.run_id)).budget["ended_at"]
    tokens = sum(r.budget["tokens"] for r in order) if all("tokens" in r.budget for r in order) else None
    listed = "; ".join(
        f"[{i}] {r.run_id}: {r.budget['started_at']} to {r.budget['ended_at']}, {r.budget['turns']} turns, "
        f"{r.budget['tool_calls']} tool calls, {r.budget['wall_s']} s, prompt sha256 {r.prompt_sha256}"
        for i, r in enumerate(order, 1))
    unfinished = [f"[{i}] {r.run_id}" for i, r in enumerate(order, 1) if "recorded with --unfinished" in r.notes.lower()]
    notes = (f"combined by scripts/agent_run_record.py --combine from the records of {len(order)} runs made one after "
             f"another, in start order: {listed}. turns, tool_calls and wall_s are their sums; started_at is the "
             "earliest start and ended_at the latest end; prompt_sha256 is the first run's. "
             + (f"Recorded with --unfinished (no result in the workflow's journal): {', '.join(unfinished)}. "
                if unfinished else "")
             + "Each run's own notes: " + " | ".join(f"[{i}] {r.notes}" for i, r in enumerate(order, 1)))
    return _complete(run_id="+".join(r.run_id for r in order), config=configs[0], prompt_sha256=order[0].prompt_sha256,
                     started_at=order[0].budget["started_at"], ended_at=end,
                     wall_s=round(sum(r.budget["wall_s"] for r in order), 3),
                     tool_calls=sum(r.budget["tool_calls"] for r in order), turns=sum(r.budget["turns"] for r in order),
                     tokens=tokens, run_record=";".join(r.budget["run_record"] for r in order), notes=notes)


# --------------------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent_run_record.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("transcript", nargs="?", help="the agent's transcript (one JSON entry per line)")
    ap.add_argument("--config", help="configuration label of the run, config-A to config-Z")
    ap.add_argument("--label", help="the run's label; the run id is <workflow run id>/<label>")
    ap.add_argument("--workflow", help="workflow run id, for a transcript outside a workflow directory")
    ap.add_argument("--session-dir", type=Path, help="the session directory, when no ancestor is named by a session id")
    ap.add_argument("--unfinished", action="store_true", help="record a workflow agent whose journal has no result")
    ap.add_argument("--combine", nargs="+", type=Path, metavar="RECORD", help="combine the records of runs made one "
                    "after another (a generator, then its revisers) into one record")
    a = ap.parse_args(argv)
    try:
        if a.combine:
            if a.transcript or a.config or a.label or a.workflow or a.session_dir or a.unfinished:
                raise RecordError("--combine takes only records; their configuration and run ids come from them")
            rec = combine([load_record(p) for p in a.combine])
        else:
            if not a.transcript or not a.config or not a.label:
                raise RecordError("give a transcript, --config and --label (or --combine with records)")
            rec = run_record(Path(a.transcript), config=a.config, label=a.label, workflow=a.workflow,
                             session_dir=a.session_dir, unfinished=a.unfinished,
                             warn=lambda m: print(f"agent_run_record: warning: {m}", file=sys.stderr))
    except RecordError as exc:
        print(f"agent_run_record: refused, nothing printed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(rec.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
