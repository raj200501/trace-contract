"""Write each task's human-review queue without any verifier outcome.

Usage: python scripts/write_review_queue.py tasks/CS-01 [...]
Writes tasks/<id>/labels/review_queue.json from the candidates' labels and the
independent construction checks only (no verifier results). It shows each candidate's
origin and proposed label, so reviewers open it only after their labels have been merged
(docs/annotation_guide.md section 2a); they label from the blinded review packet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tracecontract.analysis import label_summary


def main(*task_dirs: str) -> None:
    dirs = [Path(d) for d in task_dirs]
    summary = label_summary(dirs)
    for d in dirs:
        tid = json.loads((d / "task.json").read_text())["task_id"]
        out = {"task_id": tid, "note": "Generated from candidate labels and construction checks only; contains no verifier outcome.",
               **summary[tid]}
        (d / "labels").mkdir(exist_ok=True)
        (d / "labels" / "review_queue.json").write_text(json.dumps(out, indent=2) + "\n")
        print(tid, "queued:", [x["candidate"] for x in out["review_queue"]])


if __name__ == "__main__":
    main(*sys.argv[1:])
