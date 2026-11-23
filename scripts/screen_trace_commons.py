"""Screen the Trace Commons sessions (population ``natural:chat``) for task construction (decision log D47).

Usage (third-party data, so an isolated interpreter)::

    .venv/bin/python -I scripts/screen_trace_commons.py [DATA_DIR] [--out data/manifests/screening_natural.json]

``DATA_DIR`` (default ``/home/user/ext/trace-commons-112ebd4d``) holds the dataset's
``_download_record.json`` and ``sessions/**``. Every session file is screened; its row records
counts and ids only:

* the file id and sha256 (checked against the download record), the session id;
* user prompts, IDE context blocks, and correction candidates under the existing correction-cue
  rule (event refs relative to the session id), over the part before the donation workflow
  with IDE context blocks set apart, and over the whole file as the parser classifies it;
* whether ``toolUseResult.originalFile`` is present, and the replay verdict
  (:mod:`tracecontract.ingest.replay`, no base tree: none is in the dataset);
* base-commit evidence from git output and ``pr-link`` entries: SHAs, counts and the sha256 of the
  repository's ``host/owner/name``, never a URL. ``repo_url`` stays null even where a GitHub API
  answer in the transcript called the repository public (``public_in_transcript``): publicness
  is not verified now, offline;
* the SPDX licence and the test runner where the transcript shows them;
* the ``rule:v1`` triage proposal, the screening eligibility and its reasons;
* redaction counts of ``sanitize-natural:v1``, the copy any agent would be given.

Sessions that end with the dataset's donation workflow are screened up to its start (the
tail's length is recorded); only the repository evidence reads the whole file, since that
workflow prints remotes and licences. The deterministic analysis reads the raw files (the
replay needs their paths); only counts leave it. No string taken from session content in a
row exceeds 40 characters. Rows of other populations already in ``--out`` are kept.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from tracecontract.contract import propose_correction_events
from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.ingest.replay import PathMap, infer_root, load_raw_extras, replay_session
from tracecontract.store import jsonl_lines
from tracecontract.ingest.repo_evidence import commit_evidence, licence_evidence, raw_entries
from tracecontract.ingest.sanitize_natural import SANITIZER_VERSION, sanitize_session
from tracecontract.schemas import (
    Author, Event, EventKind, Population, ProvenanceRecord, RedactionStatus, Session, SourceRef, sha256_bytes,
)
from tracecontract.triage import METHOD as TRIAGE_METHOD
from tracecontract.triage import collect_signals, propose_triage, screen_eligibility

R = Path(__file__).resolve().parents[1]
DATA = Path("/home/user/ext/trace-commons-112ebd4d")
DATASET = "trace-commons/agent-traces"
REVISION = "112ebd4d03ce852b00e935d523107c3d0c9a65bf"
POPULATION = "natural:chat"
METHOD = "screen-trace-commons:v1"
_DONATION = re.compile(r"donate-trace|trace-commons-web|\bscrub\.py\b", re.I)
_SHA_LIKE = re.compile(r"^[0-9a-f]{7,64}$")


# ---------------------------------------------------------------------------
# Formats other than Claude Code (no edit tool results: screened, not replayed)
# ---------------------------------------------------------------------------


def _event(sid: str, rel: str, line: int, block: int, index: int, **kw: Any) -> Event:
    return Event(event_id=f"{sid}/L{line:06d}.{block:02d}", session_id=sid, index=index,
                 source=SourceRef(path=rel, line=line, block=block), **kw)


def load_cursor(path: Path) -> Session:
    """A Cursor agent JSONL file (``role`` user/assistant, ``tool_use`` blocks, no tool results)."""
    raw = path.read_bytes()
    sid, rel, events = path.stem, f"sessions/cursor/{path.name}", []
    for lineno, line in enumerate(jsonl_lines(raw.decode("utf-8", errors="replace")), start=1):
        try:
            entry = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get("role") not in ("user", "assistant"):
            continue
        blocks = (entry.get("message") or {}).get("content") or []
        for bi, b in enumerate(blocks if isinstance(blocks, list) else []):
            if not isinstance(b, dict):
                continue
            user = entry["role"] == "user"
            if b.get("type") == "text":
                events.append(_event(sid, rel, lineno, bi, len(events), text=str(b.get("text", "")),
                                     kind=EventKind.user_prompt if user else EventKind.assistant_text,
                                     author=Author.human if user else Author.agent))
            elif b.get("type") == "tool_use":
                tin = b.get("input") if isinstance(b.get("input"), dict) else {}
                events.append(_event(sid, rel, lineno, bi, len(events), kind=EventKind.tool_call, author=Author.agent,
                                     tool_name=str(b.get("name")), tool_input=tin, text=json.dumps(tin, sort_keys=True)))
    return Session(session_id=sid, population=Population.natural, source="trace-commons", source_revision=REVISION,
                   source_format="cursor_jsonl", agent="Cursor", trace_sha256=sha256_bytes(raw), events=events)


def load_opencode(path: Path) -> Session:
    """An opencode session export (``info`` and ``messages`` with ``parts``)."""
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8", errors="replace"))
    sid = str((doc.get("info") or {}).get("id") or path.stem)
    rel, events = f"sessions/opencode/{path.name}", []
    for mi, msg in enumerate(doc.get("messages") or [], start=1):
        user = (msg.get("info") or {}).get("role") == "user"
        for pi, part in enumerate(msg.get("parts") or []):
            kind = part.get("type")
            if kind == "text":
                events.append(_event(sid, rel, mi, pi, len(events), text=str(part.get("text", "")),
                                     kind=EventKind.user_prompt if user else EventKind.assistant_text,
                                     author=Author.human if user else Author.agent))
            elif kind == "tool":
                state = part.get("state") or {}
                tin = state.get("input") if isinstance(state.get("input"), dict) else {}
                call = str(part.get("callID") or f"call-{mi}-{pi}")
                events.append(_event(sid, rel, mi, pi, len(events), kind=EventKind.tool_call, author=Author.agent,
                                     tool_name=str(part.get("tool")), tool_call_id=call, tool_input=tin,
                                     text=json.dumps(tin, sort_keys=True)))
                events.append(_event(sid, rel, mi, pi + 100, len(events), kind=EventKind.tool_result, author=Author.tool,
                                     tool_call_id=call, text=str(state.get("output", "")),
                                     is_error=state.get("status") == "error"))
    return Session(session_id=sid, population=Population.natural, source="trace-commons", source_revision=REVISION,
                   source_format="opencode_json", agent="opencode", trace_sha256=sha256_bytes(raw), events=events)


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------


def task_part(session: Session) -> tuple[Session, int]:
    """The session before the donation workflow (its skill text or commands), and the tail's length."""
    for ev in session.events:
        blob = json.dumps(ev.tool_input) if ev.kind == EventKind.tool_call else ev.text
        if ev.kind in (EventKind.system_injected, EventKind.user_prompt, EventKind.tool_call) and _DONATION.search(blob):
            return session.model_copy(update={"events": session.events[:ev.index]}), len(session.events) - ev.index
    return session, 0


def _short(value: str) -> str:
    """A string taken from session content: at most 40 characters, or the row is refused."""
    if len(value) > 40:
        raise ValueError("a content-derived string exceeds 40 characters")
    return value


def _ref(event_id: str) -> str:
    return _short(event_id.rsplit("/", 1)[-1])


def screen_file(path: Path, harness: str, *, download: dict[str, str], accessed: str) -> dict[str, Any]:
    """The screening row of one session file."""
    raw = path.read_bytes()
    sha = sha256_bytes(raw)
    rel = f"sessions/{harness}/{path.name}"
    if harness == "claude_code":
        session = parse_claude_code_jsonl(path, population=Population.natural, source="trace-commons",
                                          source_revision=REVISION, relpath=rel)
        extras, prs = load_raw_extras(path), raw_entries(path, "pr-link")
    else:
        session = load_cursor(path) if harness == "cursor" else load_opencode(path)
        extras, prs = {}, []
    part, tail = task_part(session)
    replay = replay_session(part, extras=extras) if harness == "claude_code" else None
    root = replay.root if replay else infer_root(part)
    # The repository evidence reads the whole file: the donation workflow prints remotes and licences.
    commit = commit_evidence(session, extras, prs, root=root)
    licence = licence_evidence(session, extras, PathMap(root) if root else None)
    signals = collect_signals(part, changed_paths=replay.changed if replay else None,
                              absent_reads=replay.counts["read_absent_from_base"] if replay else 0, base_commit=commit.status)
    proposal = propose_triage(signals)
    fidelity = replay.fidelity.value if replay else "unreconstructable"
    eligibility, reasons = screen_eligibility(signals, proposal, replay_fidelity=fidelity, licence=licence["spdx"],
                                              replay_supported=replay is not None)
    _clean, redactions = sanitize_session(session)
    original_files = sum(isinstance(x.tool_use_result, dict) and isinstance(x.tool_use_result.get("originalFile"), str)
                         for x in extras.values())
    record_id = f"tc-{sha[:12]}"
    proposal = proposal.model_copy(update={"correction_event_ids": [_ref(e) for e in proposal.correction_event_ids]})
    rec = ProvenanceRecord(
        record_id=record_id, session_id=_short(session.session_id), population=Population.natural,
        source_url=f"https://huggingface.co/datasets/{DATASET}", source_id=_short(path.stem), source_revision=REVISION,
        repo_url=None, base_commit=None, licenses={"dataset": "CC-BY-4.0", "code": licence["spdx"] or "NOASSERTION"},
        permission_basis="CC-BY-4.0 compilation; contributor certification; embedded code keeps its own licence",
        trace_sha256=sha, capture_method=f"Trace Commons donation (donate-trace skill), raw {harness} session file",
        redaction_status=RedactionStatus.source_redacted, task_family_id=record_id, eligibility=eligibility,
        rejection_reasons=reasons if eligibility.value == "rejected" else [], triage=proposal, accessed=accessed,
        notes="; ".join(reasons) if eligibility.value != "rejected" else "")
    row = rec.model_dump(mode="json")
    row["population"] = POPULATION
    replay_summary = replay.summary() if replay else {
        "method": "replay:v1", "fidelity": "unreconstructable", "base_tree": False,
        "reasons": [f"format: {harness} sessions record no Edit or Write tool results to replay"]}
    sig = signals.summary()
    row["screening"] = {
        "method": METHOD, "triage_method": TRIAGE_METHOD, "harness": harness, "file_id": _short(path.stem),
        "file_sha256": sha, "download_record_match": download.get(rel) == sha,
        "events": len(session.events), "donation_tail_events": tail,
        "user_prompts": sig["user_prompts"], "ide_context_blocks": sig["ide_context_blocks"],
        "correction_candidates": sig["correction_candidates"], "correction_refs": proposal.correction_event_ids,
        # The same counts over the whole file with the parser's classification and the cue rule unchanged.
        "user_prompts_in_file": len(session.user_prompts()),
        "correction_candidates_in_file": len(propose_correction_events(session)),
        "original_file_present": original_files > 0, "original_file_values": original_files,
        "fidelity": fidelity, "replay": replay_summary, "base_commit": _commit_row(commit.summary()),
        "licence": licence, "test_environment": {"runner": signals.test_runner, "runs": signals.test_runs,
                                                  "last_outcome": signals.last_test},
        "signals": {k: v for k, v in sig.items() if k not in ("user_prompts", "ide_context_blocks", "correction_candidates")},
        "agent_text_sanitizer": SANITIZER_VERSION, "redactions": redactions,
    }
    return row


def _commit_row(summary: dict[str, Any]) -> dict[str, Any]:
    for key in ("head_shas_before_change", "commits_made"):
        summary[key] = [_short(s) for s in summary[key] if _SHA_LIKE.match(s)]
    return summary


def screen(data: Path) -> list[dict[str, Any]]:
    record = json.loads((data / "_download_record.json").read_text(encoding="utf-8"))
    download = {f["path"]: f["sha256"] for f in record.get("files", []) if f.get("verified")}
    accessed = str(record.get("fetched_utc"))
    rows = []
    for path in sorted((data / "sessions").glob("*/*")):
        if path.is_file() and path.suffix in (".jsonl", ".json"):
            rows.append(screen_file(path, path.parent.name, download=download, accessed=accessed))
    return rows


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data", nargs="?", type=Path, default=DATA)
    ap.add_argument("--out", type=Path, default=R / "data" / "manifests" / "screening_natural.json")
    a = ap.parse_args(argv)
    rows = screen(a.data)
    kept = []
    if a.out.exists():
        kept = [r for r in json.loads(a.out.read_text(encoding="utf-8")) if r.get("population") != POPULATION]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(kept + rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["eligibility"]] = counts.get(r["eligibility"], 0) + 1
    json.dump({"screened": len(rows), "eligibility": counts, "out": str(a.out.relative_to(R)) if a.out.is_relative_to(R)
               else a.out.name}, sys.stdout)
    print()


if __name__ == "__main__":
    main()
