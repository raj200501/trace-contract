"""Export the prompts that produced the model-generated artifacts into the repository.

Sources (outside the repository, in the Claude Code session directory):
* workflow run records (``workflows/wf_*.json``): the exact script of every workflow
  run, which contains its agent prompt templates;
* standalone subagent transcripts (``subagents/agent-*.jsonl``): the first user
  message of each agent is its prompt.

Writes ``experiments/prompts/workflows/<name>__<run id>.js`` and
``experiments/prompts/agent_prompts.jsonl`` (one record per agent: id, sha256 of the
original prompt, redacted prompt). Redactions: quoted messages of the repository owner,
session-local paths and session ids. Prompts are data; they are not re-run here.

Usage: python scripts/export_prompts.py <claude project session dir>
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
OUT = R / "experiments" / "prompts"

_REDACTIONS = [
    (re.compile(r"Their message \"[^\"]*\"[^.]*\.(?: [^.]*\.)?"), "[note about an earlier owner message omitted]."),
    (re.compile(r"\"ok i cant accept[^\"]*\""), "\"[owner message omitted]\""),
    (re.compile(r"/tmp/claude-0/[^\s'\"`)]*"), "<scratchpad>"),
    (re.compile(r"/root/\.claude/projects/[^\s'\"`)]*"), "<session-dir>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<session-id>"),
    (re.compile(r"[A-Za-z0-9._%+-]*[A-Za-z0-9]@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "[EMAIL REDACTED]"),
]


def redact(text: str) -> str:
    for pat, rep in _REDACTIONS:
        text = pat.sub(rep, text)
    return text


def first_prompt(path: Path) -> str | None:
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "user":
                c = e.get("message", {}).get("content")
                return c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return None


def main(session_dir: str) -> None:
    sd = Path(session_dir)
    (OUT / "workflows").mkdir(parents=True, exist_ok=True)
    n_wf = 0
    for rec in sorted((sd / "workflows").glob("wf_*.json")):
        d = json.loads(rec.read_text())
        script = d.get("script")
        if not script:
            continue
        name = re.search(r"name:\s*'([^']+)'", script)
        fname = f"{name.group(1) if name else 'workflow'}__{d['runId']}.js"
        header = (f"// Exported by scripts/export_prompts.py from the workflow run record {d['runId']} "
                  f"(started {d.get('timestamp')}); sha256 of the original script: "
                  f"{hashlib.sha256(script.encode()).hexdigest()}. Redacted: owner messages, session paths/ids.\n")
        (OUT / "workflows" / fname).write_text(header + redact(script), encoding="utf-8")
        n_wf += 1
    rows = []
    for t in sorted((sd / "subagents").glob("agent-*.jsonl")):
        prompt = first_prompt(t)
        if prompt is None:
            continue
        rows.append({"agent_id": t.stem.removeprefix("agent-"), "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                     "transcript_sha256": hashlib.sha256(t.read_bytes()).hexdigest(), "prompt": redact(prompt)})
    (OUT / "agent_prompts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Prompts of the model-generated artifacts\n\n"
        "* `workflows/`: the exact script of every workflow run (contract recovery, verifier generation and audits, "
        "held-out generation and checks, brief verification, internal review, privacy fixes). Agent prompts are built from "
        "the templates in each script.\n"
        "* `agent_prompts.jsonl`: the prompt of every standalone agent (e.g. controlled-session agents, held-out generators "
        "for CS-03/CS-04, reference-check writers, mappers), with the sha256 of the original prompt and transcript.\n\n"
        "Redacted before export: quoted messages of the repository owner, session-local paths and ids, e-mail addresses. "
        "The full transcripts are kept outside the repository (they contain harness internals); their hashes are recorded "
        "here and in `tasks/*/labels/generator_audit.json`.\n", encoding="utf-8")
    print(f"exported {n_wf} workflow scripts and {len(rows)} agent prompts to {OUT.relative_to(R)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
