"""Pre-flight checks before the final pilot run (protocol v0.3 §11).

Fails (exit 1) unless, for every task given:
* every verifier spec is frozen and its tests still match the frozen content hash;
* the task has the full held-out pool (pre-correction state, 2 alternatives, 5 near
  misses) and every held-out candidate has a D19 proposal (or a human label);
* every constructed held-out candidate's generator transcript was audited, with no
  forbidden read left unassessed;
* no other sandbox container is running and the git working tree is clean.

Usage: python scripts/preflight_final_run.py tasks/CS-01 tasks/CS-02 ...
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tracecontract.analysis import PILOT_LABELER
from tracecontract.schemas import Candidate, CandidateOrigin, TaskManifest, VerifierSpec
from tracecontract.store import load
from tracecontract.verifier import check_frozen

R = Path(__file__).resolve().parents[1]


def main(*task_dirs: str) -> int:
    problems: list[str] = []
    for td in map(Path, task_dirs):
        m = load(td / "task.json", TaskManifest)
        for p in m.verifiers:
            s = load(td / p, VerifierSpec)
            if not s.frozen:
                problems.append(f"{m.task_id}: verifier {s.verifier_id} not frozen")
                continue
            try:
                check_frozen(s, td)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{m.task_id}: verifier {s.verifier_id} changed after freezing: {exc}")
        cands = [load(td / p, Candidate) for p in m.candidates]
        held = [c for c in cands if c.split.value == "eval" and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]
        by_origin = {o: sum(c.origin == o for c in held) for o in CandidateOrigin}
        if by_origin[CandidateOrigin.observed_pre_correction] != 1 or by_origin[CandidateOrigin.valid_alternative] != 2 \
                or by_origin[CandidateOrigin.constructed_near_miss] != 5:
            problems.append(f"{m.task_id}: incomplete held-out pool {({k.value: v for k, v in by_origin.items() if v})}")
        for c in held:
            if c.final_label() is None and not any(lb.labeler == PILOT_LABELER for lb in c.labels):
                problems.append(f"{m.task_id}: {c.candidate_id} has no D19 proposal")
        audit_p = td / "labels" / "generator_audit.json"
        audit = json.loads(audit_p.read_text()) if audit_p.exists() else {}
        for ws, rec in audit.items():
            if rec.get("hits") and not rec.get("assessment"):
                problems.append(f"{m.task_id}: generator audit {ws} has unassessed hits")
        needed = {"eval-alt-1", "eval-alt-2", "eval-nm"}
        missing = sorted(needed - set(audit))
        if missing:
            problems.append(f"{m.task_id}: generator audits missing for {missing}")
    running = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout.split()
    if running:
        problems.append(f"{len(running)} container(s) running; the final run needs an idle host")
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=R, capture_output=True, text=True).stdout.strip()
    if dirty:
        problems.append("git working tree not clean")
    for p in problems:
        print("FAIL:", p)
    print("preflight:", "ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
