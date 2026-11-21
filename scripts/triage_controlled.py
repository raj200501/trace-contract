"""Write the ``rule:v1`` triage proposal of each controlled task into its sidecar ``tasks/<id>/triage.json`` (D47, D50).

Usage: python scripts/triage_controlled.py [--check] [tasks/CS-01 ...]   (default: every tasks/CS-*)

For each controlled task: parse its transcript with the registered scripted turns, replay the
whole session onto the task's base snapshot (``snapshots/<id>``, for reads of files absent from
it), read the full-session contract (for unresolved requirements) and propose a triage; the
base commit is the task's pinned one. The proposal goes into the sidecar together with the paths
and sha256 of its inputs (:func:`tracecontract.triage.write_sidecar`). The frozen provenance
record ``tasks/<id>/provenance.json`` is only read: commit ``577860c`` had written these
proposals into its ``triage`` field, and D50 restored the four records.

Every sidecar is rendered and compared in memory first; a file is written only if its text
changes. With ``--check`` nothing is written, and the exit status is 1 if a sidecar is missing
or would change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.ingest.replay import CONTROLLED_SANDBOXED, replay_session
from tracecontract.schemas import Population, ProvenanceRecord, TaskContract, TaskManifest, TriageProposal, sha256_bytes
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import load
from tracecontract.triage import SIDECAR, collect_signals, propose_triage, render_sidecar, sidecar_record, write_sidecar

R = Path(__file__).resolve().parents[1]
GENERATOR = "scripts/triage_controlled.py"


def _inputs(task_dir: Path, repo_root: Path, snapshot_root: Path | None = None) -> tuple[TaskManifest, dict[str, str]]:
    m = load(task_dir / "task.json", TaskManifest)
    rel = f"data/controlled/transcripts/{m.task_id}.jsonl"
    base = (snapshot_root or repo_root / "snapshots") / m.task_id
    out = {"transcript": rel, "transcript_sha256": sha256_bytes((repo_root / rel).read_bytes())}
    if base.is_dir():
        out["base_snapshot_manifest_sha256"] = manifest_sha256(manifest(base))
    if "full_session" in m.contracts:
        out["contract"] = m.contracts["full_session"]
        out["contract_sha256"] = sha256_bytes((task_dir / m.contracts["full_session"]).read_bytes())
    return m, out


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


def _provenance_file(task_dir: Path) -> str:
    """The task's provenance record, relative to its directory (as task.json names it)."""
    return json.loads((task_dir / "task.json").read_text(encoding="utf-8")).get("provenance") or "provenance.json"


def task_sidecar(task_dir: Path, repo_root: Path = R, snapshot_root: Path | None = None) -> dict:
    """The sidecar record of one task (nothing is written)."""
    proposal = triage_task(task_dir, repo_root, snapshot_root)
    m, inputs = _inputs(task_dir, repo_root, snapshot_root)
    prov = load(task_dir / _provenance_file(task_dir), ProvenanceRecord)
    return sidecar_record(m.task_id, prov.record_id, proposal, generator=GENERATOR, inputs=inputs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("tasks", nargs="*", help="task directories (default: every tasks/CS-*)")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if a sidecar is missing or would change")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])
    dirs = [Path(t).resolve() for t in a.tasks] or sorted((R / "tasks").glob("CS-*"))
    out, stale = {}, []
    for d in dirs:
        rec = task_sidecar(d)
        path = d / SIDECAR
        if a.check:
            changed = not path.is_file() or path.read_text(encoding="utf-8") != render_sidecar(rec)
            if changed:
                stale.append(d.name)
        else:
            changed = write_sidecar(d, rec, _provenance_file(d))
        p = rec["triage"]
        out[d.name] = {"category": p["category"], "confidence": p["confidence"],
                       "corrections": len(p["correction_event_ids"]), "sidecar": "changed" if changed else "unchanged"}
    print(json.dumps(out))
    if stale:
        print(f"triage_controlled: sidecar missing or out of date: {', '.join(stale)}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
