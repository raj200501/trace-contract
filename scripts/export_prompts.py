"""Export the prompts that produced the model-generated artifacts into the repository.

Sources (outside the repository, in the Claude Code session directory):
* workflow run records (``workflows/wf_*.json``): the exact script of every workflow
  run, which contains its agent prompt templates;
* standalone subagent transcripts (``subagents/agent-*.jsonl``): the first user
  message of each agent is its prompt.

Writes ``experiments/prompts/workflows/<name>__<run id>.js`` and
``experiments/prompts/agent_prompts.jsonl`` (one record per agent: id, sha256 of the
original prompt, redacted prompt). Redactions: notes about the repository owner's
messages, session-local paths, session ids and e-mail addresses, plus owner-specific
redactions read from a file kept outside the repository (``--private-redactions``). Every
text is redacted before anything is written, and the export writes nothing if a forbidden
marker survives anywhere. Prompts are data; they are not re-run.

Usage: python scripts/export_prompts.py <claude project session dir> --private-redactions <file.json>
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
OUT = R / "experiments" / "prompts"

_REDACTIONS = [
    (re.compile(r"Their message \"[^\"]*\"[^.]*\.(?: [^.]*\.)?"), "[note about an earlier owner message omitted]."),
    (re.compile(r"Their latest message asks for this work to continue;[^.]*\."), "[note about an earlier owner message omitted]."),
    (re.compile(r"/tmp/claude-0/[^\s'\"`)]*"), "<scratchpad>"),
    (re.compile(r"/root/\.claude/projects/[^\s'\"`)]*"), "<session-dir>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<session-id>"),
    (re.compile(r"[A-Za-z0-9._%+-]*[A-Za-z0-9]@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "[EMAIL REDACTED]"),
]
# Session-local paths must never survive redaction.
_FORBIDDEN = [re.compile(r"/tmp/claude-0/-|/root/\.claude/projects/")]
_N_GENERIC = len(_REDACTIONS)  # rules after this index are owner-specific (load_private)
# Workflow runs that are not exported, with the reason (stated in the README).
_NOT_EXPORTED = {"tracecontract-privacy-fixes": "its prompts concern the repository owner's personal information"}
# Standalone agents whose output was not used (decision log D40): started on 2026-11-13, stopped at the
# D30 pause after only inspection commands; they registered nothing and were not audited.
_STOPPED = "stopped on 2026-11-13 (D30 pause) after inspection commands only; registered nothing; not audited; output not used"
_AGENT_NOTES: dict[str, str] = {
    "a7fad0c19846b4437": "CS-02 held-out generation attempt: " + _STOPPED,
    "a40e11a8ab99ae735": "CS-02 held-out generation attempt: " + _STOPPED,
    "aa6f59286e0aae774": "CS-02 held-out generation attempt: " + _STOPPED,
    "a18443e118afd6931": "CS-02 reference-check attempt: " + _STOPPED,
    "a8360e790e2186abc": "CS-01 near-miss attempt: " + _STOPPED,
    "ad15c639ae0764a36": "CS-01 near-miss attempt: " + _STOPPED,
    "af91f45e0c716a5a2": "CS-02 requirement-mapping attempt: " + _STOPPED,
}


def load_private(path: str) -> None:
    """Add owner-specific redactions and forbidden markers from a JSON file kept outside the repository.

    Format: {"patterns": [{"pattern": regex, "replacement": text, "dotall": bool}], "forbidden": [regex, ...]}.
    The patterns describe the owner's personal information, so they are not part of this public script.
    """
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    for p in d.get("patterns", []):
        _REDACTIONS.append((re.compile(p["pattern"], re.S if p.get("dotall") else 0), p["replacement"]))
    _FORBIDDEN.extend(re.compile(f, re.I) for f in d.get("forbidden", []))


def redact(text: str) -> tuple[str, bool]:
    """Return the redacted text and whether an owner-specific rule changed it.

    When one did, the original's hash is withheld: the rest of the text is public, so a
    hash of the original would let anyone confirm a guess of the redacted wording.
    """
    private_hit = False
    for i, (pat, rep) in enumerate(_REDACTIONS):
        new = pat.sub(rep, text)
        private_hit |= i >= _N_GENERIC and new != text
        text = new
    left = sorted({m.group(0).lower() for f in _FORBIDDEN for m in f.finditer(text)})
    if left:
        raise SystemExit(f"export_prompts: redaction incomplete ({len(left)} forbidden marker(s) survived); nothing written")
    return text, private_hit


def span(path: Path) -> tuple[str | None, str | None]:
    """Timestamps of the first and last transcript entries."""
    ts = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                t = json.loads(line).get("timestamp")
            except (json.JSONDecodeError, AttributeError):
                continue
            if isinstance(t, str):
                ts.append(t)
    return (min(ts), max(ts)) if ts else (None, None)


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


def main(session_dir: str, *opts: str) -> None:
    if len(opts) != 2 or opts[0] != "--private-redactions":
        raise SystemExit("usage: export_prompts.py <session dir> --private-redactions <file.json> "
                         "(owner-specific redactions, kept outside the repository, are required)")
    load_private(opts[1])
    sd = Path(session_dir)
    (OUT / "workflows").mkdir(parents=True, exist_ok=True)
    n_wf = 0
    names: set[str] = set()
    pending: dict[Path, str] = {}  # nothing is written until every text has passed redaction
    for rec in sorted((sd / "workflows").glob("wf_*.json")):
        d = json.loads(rec.read_text())
        script = d.get("script")
        if not script:
            continue
        name = re.search(r"name:\s*'([^']+)'", script)
        if name and name.group(1) in _NOT_EXPORTED:
            continue
        fname = f"{name.group(1) if name else 'workflow'}__{d['runId']}.js"
        body, private_hit = redact(script)
        orig = ("withheld (owner-specific redaction applied)" if private_hit
                else hashlib.sha256(script.encode()).hexdigest())
        start = (datetime.fromtimestamp(d["startTime"] / 1000, timezone.utc).isoformat(timespec="seconds")
                 if d.get("startTime") else "unrecorded")
        header = (f"// Exported by scripts/export_prompts.py from the workflow run record {d['runId']} "
                  f"(started {start}, finished {d.get('timestamp')}, status {d.get('status', 'unrecorded')}); "
                  f"sha256 of the original script: {orig}; "
                  f"sha256 of this export: {hashlib.sha256(body.encode()).hexdigest()}. "
                  "Redacted: owner messages and personal information, session paths/ids.\n")
        pending[OUT / "workflows" / fname] = header + body
        names.add(name.group(1) if name else "workflow")
        n_wf += 1
    rows = []
    for t in sorted((sd / "subagents").glob("agent-*.jsonl")):
        prompt = first_prompt(t)
        if prompt is None:
            continue
        body, private_hit = redact(prompt)
        first, last = span(t)
        aid = t.stem.removeprefix("agent-")
        rows.append({"agent_id": aid, "first_entry_at": first, "last_entry_at": last,
                     **({"note": _AGENT_NOTES[aid]} if aid in _AGENT_NOTES else {}),
                     "prompt_sha256": None if private_hit else hashlib.sha256(prompt.encode()).hexdigest(),
                     "transcript_sha256": hashlib.sha256(t.read_bytes()).hexdigest(), "prompt": body})
    pending[OUT / "agent_prompts.jsonl"] = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    for path, text in pending.items():
        path.write_text(text, encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Prompts of the model-generated artifacts\n\n"
        "* `workflows/`: the script of every workflow run ("
        + ", ".join(f"`{n}`" for n in sorted(names))
        + "), redacted as described below. Agent prompts are built from the templates in each script. Each header gives "
        "the run's start and finish time and status, the hash of the export and, where no owner-specific rule applied, the "
        "hash of the original script. Not exported: "
        + "; ".join(f"`{k}` ({v})" for k, v in _NOT_EXPORTED.items())
        + ". Its changes are in the git history and summarised in `docs/internal_review.md`.\n"
        "* `agent_prompts.jsonl`: the prompt of every standalone agent (e.g. controlled-session agents, held-out generators "
        "for CS-03/CS-04, reference-check writers, mappers), with the time of its first and last transcript entry and the "
        "sha256 of the original prompt and transcript. A `note` marks agents whose output was not used.\n\n"
        "Redacted before export: notes about the repository owner's messages and personal information (using "
        "owner-specific rules kept outside the repository), session ids, session-local paths and e-mail addresses. Where an "
        "owner-specific rule changed a prompt, the hash of the original is withheld (`prompt_sha256` is null; workflow "
        "headers say \"withheld\"), because it would let anyone confirm a guess of the removed wording. Workflow-run ids "
        "(`wf_...`) and agent ids are opaque harness identifiers; they are kept as provenance keys, for example in "
        "`tasks/*/labels/construction_checks.json` (`source`). "
        "The full transcripts are kept outside the repository (they contain harness internals); their hashes are recorded "
        "here and in `tasks/*/labels/generator_audit.json`.\n", encoding="utf-8")
    print(f"exported {n_wf} workflow scripts and {len(rows)} agent prompts to {OUT.relative_to(R)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
