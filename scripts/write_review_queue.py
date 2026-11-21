"""Write each task's human-review queue without any verifier outcome.

Usage: python scripts/write_review_queue.py tasks/CS-01 [...]
       python scripts/write_review_queue.py data/natural/tasks/NP-03 [...]
Writes <task dir>/labels/review_queue.json from the candidates' labels and the
independent construction checks only (no verifier results). It shows each candidate's
origin and proposed label, so reviewers open it only after their labels have been merged
(docs/annotation_guide.md section 2a); they label from the blinded review packet.

A candidate with a source-evidence label (a natural PR-review task's pre-review state,
protocol §15.6) also shows that label, under ``source_evidence``: the evidence of the
thread, reported apart from D19 and never a human label. A natural task's queue stays in
its task directory under ``data/natural/`` (git-ignored, §17.4).

No queue is written through a symbolic link (``labels/`` or ``labels/review_queue.json``,
which could lead into a tracked directory): every task is checked before anything is
written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tracecontract.analysis import label_summary
from tracecontract.schemas import Candidate, TaskManifest
from tracecontract.store import load


def source_evidence(task_dir: Path) -> dict[str, dict]:
    """The latest source-evidence label of each candidate that has one (natural PR-review tasks only)."""
    m = load(task_dir / "task.json", TaskManifest)
    out = {}
    for p in m.candidates:
        c = load(task_dir / p, Candidate)
        lb = c.source_evidence_label()
        if lb is not None:
            out[c.candidate_id] = {"value": lb.value, "violated_requirements": lb.violated_requirements, "labeler": lb.labeler,
                                   "note": "source evidence (the thread), reported apart from D19; not a human label"}
    return out


def main(*task_dirs: str) -> None:
    dirs = [Path(d) for d in task_dirs]
    for d in dirs:  # every task, before anything is written
        link = next((p for p in (d / "labels", d / "labels" / "review_queue.json") if p.is_symlink()), None)
        if link is not None:
            raise SystemExit(f"write_review_queue refused, nothing written: {link} is a symbolic link; the queue is not "
                             "written through it")
    summary = label_summary(dirs)
    for d in dirs:
        tid = json.loads((d / "task.json").read_text())["task_id"]
        out = {"task_id": tid, "note": "Generated from candidate labels and construction checks only; contains no verifier outcome.",
               **summary[tid]}
        evidence = source_evidence(d)
        for row in (*out["candidates"], *out["review_queue"]):
            if row["candidate"] in evidence:
                row["source_evidence"] = evidence[row["candidate"]]
        (d / "labels").mkdir(exist_ok=True)
        (d / "labels" / "review_queue.json").write_text(json.dumps(out, indent=2) + "\n")
        print(tid, "queued:", [x["candidate"] for x in out["review_queue"]])


if __name__ == "__main__":
    main(*sys.argv[1:])
