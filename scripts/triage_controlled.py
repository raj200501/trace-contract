"""Write ``rule:v1`` triage proposals into ``tasks/<id>/provenance.json`` (the triage field only; D47).

Usage: python scripts/triage_controlled.py [tasks/CS-01 ...]   (default: every tasks/CS-*)

For each controlled task: parse its transcript with the registered scripted turns, replay the
whole session onto the task's base snapshot (``snapshots/<id>``, for reads of files absent from
it), read the full-session contract (for unresolved requirements) and propose a triage; the
base commit is the task's pinned one. The provenance record is not a hashed input; only its
``triage`` field changes, and the script checks that the rest of the file is unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.ingest.replay import CONTROLLED_SANDBOXED, replay_session
from tracecontract.schemas import Population, ProvenanceRecord, TaskContract, TaskManifest, TriageProposal
from tracecontract.store import dump, load
from tracecontract.triage import collect_signals, propose_triage

R = Path(__file__).resolve().parents[1]


def triage_task(task_dir: Path, repo_root: Path = R, snapshot_root: Path | None = None) -> TriageProposal:
    m = load(task_dir / "task.json", TaskManifest)
    rel = f"data/controlled/transcripts/{m.task_id}.jsonl"
    session = parse_claude_code_jsonl(repo_root / rel, population=Population.controlled, source="controlled:tracecontract",
                                      relpath=rel, scripted_turns=m.scripted_turns)
    base = (snapshot_root or repo_root / "snapshots") / m.task_id
    if not base.is_dir():
        raise SystemExit(f"{m.task_id}: base snapshot missing; rebuild it with `tracecontract snapshot {task_dir}`")
    replay = replay_session(session, base=base, sandboxed_commands=CONTROLLED_SANDBOXED)
    contract = load(task_dir / m.contracts["full_session"], TaskContract) if "full_session" in m.contracts else None
    signals = collect_signals(session, changed_paths=replay.changed, absent_reads=replay.counts["read_absent_from_base"],
                              base_commit="pinned", contract=contract)
    return propose_triage(signals)


def write_triage(task_dir: Path, proposal: TriageProposal) -> None:
    path = task_dir / "provenance.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    rec = load(path, ProvenanceRecord).model_copy(update={"triage": proposal})
    dump(rec, path)
    after = json.loads(path.read_text(encoding="utf-8"))
    if {k: v for k, v in before.items() if k != "triage"} != {k: v for k, v in after.items() if k != "triage"}:
        raise SystemExit(f"{path}: fields other than triage changed")


def main(argv: list[str] | None = None) -> None:
    dirs = [Path(a) for a in (argv if argv is not None else sys.argv[1:])] or sorted((R / "tasks").glob("CS-*"))
    out = {}
    for d in dirs:
        proposal = triage_task(d.resolve())
        write_triage(d.resolve(), proposal)
        out[d.name] = {"category": proposal.category.value, "confidence": proposal.confidence,
                       "corrections": len(proposal.correction_event_ids)}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
