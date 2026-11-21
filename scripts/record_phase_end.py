"""The record of a natural family's phase end (decision log D64, "Order per family and freeze points"; D65).

Usage: python scripts/record_phase_end.py <task dir> --phase P1|P2|P3|P4|P5|P6|P7 [--log <file>]

Appends one JSON line to the log (default ``data/manifests/natural_phase_ends.jsonl``) and prints it:

* ``task_id``, ``phase``, ``recorded_at`` (UTC) and ``head``, the repository commit at that time;
* ``files``: the family's task directory in the committed index's form (``tracecontract.natural_pr.file_hashes``):
  each file the index lists by name with its sha256, and each directory the index summarises (B1's overlay, the
  generated tests, any other subdirectory) as one manifest hash and a file count; ``state_sha256`` is the sha256 of
  that object's canonical JSON;
* ``verifiers``: each verifier of ``task.json`` and of ``verifiers_extra.json``, with its condition, whether it is
  frozen, its ``frozen_at`` and its content sha256; ``contracts``: the contract ids by variant; ``candidates``: each
  candidate's origin, split and patch sha256.

Ids, hashes, counts and times only: no thread text, no repository path, no generated test's file name (D64 decision
2). D64 has each phase end with an index commit, and the commit times are the order record. While the committed
index is being rewritten by the S10 step of the S9 extension, the commit at a phase end is of this log (D65): the
builder commits the log alone after each phase of each family, before that family's next phase starts.

Refused: a directory that is not a natural PR-review task, and a phase that does not come after the last phase the
log records for the task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tracecontract import roots
from tracecontract.natural_pr import file_hashes

R = Path(__file__).resolve().parents[1]
LOG = R / "data" / "manifests" / "natural_phase_ends.jsonl"
SCHEMA = "tracecontract/natural-phase-end/v1"
PHASES = ("P1", "P2", "P3", "P4", "P5", "P6", "P7")


class PhaseError(ValueError):
    pass


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _head(repo: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def _verifier(task_dir: Path, rel: str, extra: bool) -> dict[str, Any]:
    spec = _json(task_dir / rel)
    return {"verifier_id": spec.get("verifier_id"), "condition": spec.get("condition"), "frozen": bool(spec.get("frozen")),
            "frozen_at": spec.get("frozen_at"), "content_sha256": spec.get("content_sha256"), "sidecar": extra}


def last_phase(log: Path, task_id: str) -> str | None:
    """The last phase the log records for the task, or None."""
    if not log.is_file():
        return None
    last = None
    for n, line in enumerate(log.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PhaseError(f"{log.name} line {n} is not JSON: {exc}") from exc
        if rec.get("task_id") == task_id:
            last = rec.get("phase")
    return last


def phase_record(task_dir: Path, phase: str, *, now: str | None = None, repo: Path = R) -> dict[str, Any]:
    """The record of the task's phase end (see the module docstring)."""
    if phase not in PHASES:
        raise PhaseError(f"phase must be one of {', '.join(PHASES)}: {phase!r}")
    if not roots.is_natural_pr(task_dir):
        raise PhaseError(f"{task_dir.name} is not a natural PR-review task (population {roots.population(task_dir)!r})")
    m = _json(task_dir / "task.json")
    files = file_hashes(task_dir)
    verifiers = [_verifier(task_dir, rel, False) for rel in m.get("verifiers") or []]
    extra = task_dir / "verifiers_extra.json"
    if extra.is_file():
        verifiers += [_verifier(task_dir, rel, True) for rel in _json(extra).get("verifiers") or []]
    contracts = {}
    for variant, rel in sorted((m.get("contracts") or {}).items()):
        contracts[variant] = _json(task_dir / rel).get("contract_id")
    candidates = {}
    for rel in m.get("candidates") or []:
        c = _json(task_dir / rel)
        candidates[c.get("candidate_id")] = {"origin": c.get("origin"), "split": c.get("split"), "patch_sha256": c.get("patch_sha256")}
    return {"schema": SCHEMA, "task_id": m.get("task_id") or task_dir.name, "phase": phase,
            "recorded_at": now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "head": _head(repo),
            "state_sha256": hashlib.sha256(_canonical(files)).hexdigest(), "files": files, "verifiers": verifiers,
            "contracts": contracts, "candidates": dict(sorted(candidates.items()))}


def append(task_dir: Path, phase: str, log: Path = LOG, *, now: str | None = None, repo: Path = R) -> dict[str, Any]:
    """Check the phase order, then append the record to the log."""
    rec = phase_record(task_dir, phase, now=now, repo=repo)
    last = last_phase(log, rec["task_id"])
    if last is not None and (last not in PHASES or PHASES.index(phase) <= PHASES.index(last)):
        raise PhaseError(f"{rec['task_id']}: the log already records {last}; {phase} does not come after it")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(_canonical(rec).decode("utf-8") + "\n")
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("task_dir", type=Path)
    ap.add_argument("--phase", required=True, choices=PHASES)
    ap.add_argument("--log", type=Path, default=LOG)
    a = ap.parse_args(argv)
    try:
        rec = append(a.task_dir.resolve(), a.phase, a.log)
    except (PhaseError, OSError, json.JSONDecodeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
