"""Audit evaluation-side generation transcripts for forbidden reads (held-out integrity).

Usage: python scripts/audit_eval_generators.py CS-04 <transcript.jsonl>:<own workspace dir> [...]
Writes/updates tasks/<task>/labels/generator_audit.json.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from tracecontract.controlled import audit_generator_transcript

R = Path(__file__).resolve().parents[1]
_SESSION_ID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_SCRATCHPAD = re.compile(r"/tmp/claude-0/[^/\s'\"`]+/[^/\s'\"`]+/scratchpad")


def _redact(x):
    """Session ids and session-local scratchpad paths are not published (decision log D21)."""
    if isinstance(x, str):
        return _SCRATCHPAD.sub("<scratchpad>", _SESSION_ID.sub("<session>", x))
    if isinstance(x, list):
        return [_redact(v) for v in x]
    if isinstance(x, dict):
        return {k: _redact(v) for k, v in x.items()}
    return x


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
        out[name] = {"transcript_sha256": __import__("hashlib").sha256(Path(transcript).read_bytes()).hexdigest(), "hits": _redact(hits)}
        print(name, "hits:", len(hits))
        for h in hits[:8]:
            print("   ", h["tool"], h["match"], "|", h["text"][:160])
    out["_rules"] = {"forbidden_substrings": list(forbidden), "allowed": ["the agent's own exported workspace", "/root/.local/bin/"],
                     "scope": "tool inputs only (commands and file paths an agent passed to its tools); tool outputs are "
                              "not inspected (decision log D37)", "script": "scripts/audit_eval_generators.py"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
