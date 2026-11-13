"""Audit evaluation-side generation transcripts for forbidden reads (held-out integrity).

Usage: python scripts/audit_eval_generators.py CS-04 <transcript.jsonl>:<own workspace dir> [...]
Writes/updates tasks/<task>/labels/generator_audit.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tracecontract.controlled import audit_generator_transcript

R = Path(__file__).resolve().parents[1]


def main(task: str, *items: str) -> None:
    forbidden = (f"tasks/{task}/verifiers", f"tasks/{task}/candidates", "trace-contract/results", "trace-contract/data",
                 "trace-contract/docs", "cs_workspaces", f"gen_workspaces/{task}/", ".tc_sealed", "scratchpad/sealed",
                 "scratchpad/scenarios", "scratchpad/reference", "/root/")
    out_path = R / "tasks" / task / "labels" / "generator_audit.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    for item in items:
        transcript, own = item.split(":", 1)
        hits = audit_generator_transcript(Path(transcript), forbidden=forbidden, allowed=(own, "/root/.local/bin/"))
        name = Path(own).name
        out[name] = {"transcript_sha256": __import__("hashlib").sha256(Path(transcript).read_bytes()).hexdigest(), "hits": hits}
        print(name, "hits:", len(hits))
        for h in hits[:8]:
            print("   ", h["tool"], h["match"], "|", h["text"][:160])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
