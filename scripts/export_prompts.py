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

Natural export (build plan WP-H; protocol §17.4, decision log D47), run under ``python -I`` as it reads the AIDev
files::

    python -I scripts/export_prompts.py <session dir> --private-redactions <file.json> --natural
        --natural-texts data/natural/tasks --screening-texts <S9 texts.jsonl> --screening-texts <S9x texts.jsonl>
        --aidev-logins <AIDev dir> [--workflow GLOB ...] [--agent ID ...]

exports the natural arm's prompts: every workflow run whose name or run id matches a ``--workflow`` pattern (its
script, its arguments and the first message of each of its agents) and every standalone agent named by ``--agent``.
It writes only under ``experiments/prompts/natural/``: ``agent_prompts_natural.jsonl`` (one record per agent, with its
workflow run, if any), ``workflows/<name>__<run id>.js`` and ``workflows/<name>__<run id>.args.json``. An export adds
its records to those of earlier exports in ``agent_prompts_natural.jsonl`` (a record of an agent exported again is
replaced), so that runs can be exported in batches. It never rewrites ``agent_prompts.jsonl``, ``workflows/`` or the
README of the first export. Every text is redacted as above, and then guarded: a prompt, script or argument file that
holds what ``scripts/scan_tracked_files.py --aidev-logins --natural-texts --screening-texts`` would report at its place
in the export (an AIDev login of the S9 sample, the scan's login list, D66; a window of a natural thread or of any
sampled comment and its issue, built or not, or such a text too short for a window, matched whole down to the scan's
minimum; a natural repository's name or owner; a natural task's code line, of its patches, verifiers or base snapshot,
or check id; an @handle; a credential) is withheld, as the hash is withheld under
``_WITHHOLD``: its text and the hash of its original are left out, and the record says why, naming the kind of finding
only (:func:`finding_kind`). A natural prompt or script that any redaction changed keeps no hash of its original either.
The finished files, the earlier exports' records included, are scanned once more before anything is written. The guard
fails closed: it does not run, and nothing is written, without its inputs, with a natural task's file that cannot be
read, a base snapshot that a task records but that is missing or holds no code line, an earlier record file that
cannot be read, or an empty login list.
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import hashlib
import importlib.util
import io
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

R = Path(__file__).resolve().parents[1]
OUT = R / "experiments" / "prompts"
NATURAL_DIR = "natural"  # the natural export's directory under OUT
NATURAL_PROMPTS = "agent_prompts_natural.jsonl"

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
# Rules whose removal withholds the original's hash: the owner-message notes (the first two
# generic rules) and every owner-specific rule. A hash of the original would let anyone confirm
# a guess of the removed wording (decision log D46).
_WITHHOLD = {0, 1}
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
        _REDACTIONS.append((re.compile(p["pattern"], re.DOTALL if p.get("dotall") else 0), p["replacement"]))
    _FORBIDDEN.extend(re.compile(f, re.IGNORECASE) for f in d.get("forbidden", []))


def redact(text: str) -> tuple[str, bool]:
    """Return the redacted text and whether a rule that withholds the hash changed it.

    Those rules are the owner-message notes and the owner-specific rules. When one changed
    the text, the original's hash is withheld: the rest of the text is public, so a hash of
    the original would let anyone confirm a guess of the redacted wording.
    """
    private_hit = False
    for i, (pat, rep) in enumerate(_REDACTIONS):
        new = pat.sub(rep, text)
        private_hit |= (i >= _N_GENERIC or i in _WITHHOLD) and new != text
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
    if "--natural" in opts:
        main_natural(session_dir, *opts)
        return
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
        orig = ("withheld (a note about the owner's messages or personal information was removed)" if private_hit
                else hashlib.sha256(script.encode()).hexdigest())
        start = (datetime.fromtimestamp(d["startTime"] / 1000, UTC).isoformat(timespec="seconds")
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
        "Redacted before export: notes about the repository owner's messages, personal information (using "
        "owner-specific rules kept outside the repository), session ids, session-local paths and e-mail addresses. Where a "
        "note about the owner's messages or personal information was removed, the hash of the original is withheld "
        "(`prompt_sha256` is null; workflow headers say \"withheld\"), because it would let anyone confirm a guess of the "
        "removed wording. Exports pushed before 2026-11-18 (decision log D46) published those hashes. Workflow-run ids "
        "(`wf_...`) and agent ids are opaque harness identifiers; they are kept as provenance keys, for example in "
        "`tasks/*/labels/construction_checks.json` (`source`). "
        "The full transcripts are kept outside the repository (they contain harness internals); their hashes are recorded "
        "here and in `tasks/*/labels/generator_audit.json`.\n", encoding="utf-8")
    print(f"exported {n_wf} workflow scripts and {len(rows)} agent prompts to {OUT.relative_to(R)}")


# ---------------------------------------------------------------------------------------------------------------------
# The natural export
# ---------------------------------------------------------------------------------------------------------------------

Check = Callable[[str, str], list[str]]


def _scan_module() -> Any:
    """``scripts/scan_tracked_files.py`` as a module: the pre-push scan, whose verdict the natural guard applies."""
    spec = importlib.util.spec_from_file_location("scan_tracked_files", Path(__file__).with_name("scan_tracked_files.py"))
    if spec is None or spec.loader is None:
        raise SystemExit("export_prompts: cannot load scripts/scan_tracked_files.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scan_check(scan: Any, natural: Any, logins: list[tuple[str, re.Pattern]]) -> Check:
    """``check(where, text)``: the kinds of finding that the scan (``scan_file`` with ``--aidev-logins`` and
    ``--natural-texts``) reports for ``text`` as the file ``where`` (a repository path), without their locations; an
    empty list when it reports nothing. Nothing is printed."""

    def check(where: str, text: str) -> list[str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            scan.scan_file(where, text.encode("utf-8"), [], logins, natural, aidev=True)
        return [ln.split(": ", 1)[-1] for ln in buf.getvalue().splitlines() if ln.strip()]

    return check


# How a withheld record names a scan finding: by its kind only. A login's number would name the person (the sorted
# login list can be rebuilt from public data, D47), and an address's hash would confirm a guess of it (D46); the
# finding "@handle" would be read as a handle by the next scan.
_KINDS = ((re.compile(r"aidev login #\d+"), "AIDev login"), (re.compile(r"@handle"), "handle"),
          (re.compile(r"e-mail address\b.*"), "e-mail address"), (re.compile(r"private marker #\d+"), "private marker"))


def finding_kind(finding: str) -> str:
    """The kind of a scan finding (``check``'s list) as a withheld record names it: no login's number, no handle, no
    address or hash of one, no marker's number; the natural findings keep their task or comment ids."""
    for pat, kind in _KINDS:
        if pat.fullmatch(finding):
            return kind
    return finding


def _withheld(found: list[str]) -> str:
    kinds = sorted({finding_kind(f) for f in found})
    return "withheld: it holds what scripts/scan_tracked_files.py reports there (" + "; ".join(kinds) + ")"


def _where(out: Path, path: Path) -> str:
    """The repository path at which the scan reads ``path`` of the export directory ``out``: the natural export lands in
    ``experiments/prompts/natural/``, wherever ``out`` is (a test exports elsewhere)."""
    return (Path("experiments") / "prompts" / NATURAL_DIR / path.relative_to(out)).as_posix()


def _natural_row(transcript: Path, run: str | None, check: Check, where: str) -> dict[str, Any] | None:
    prompt = first_prompt(transcript)
    if prompt is None:
        return None
    body, _private_hit = redact(prompt)
    first, last = span(transcript)
    row: dict[str, Any] = {"agent_id": transcript.stem.removeprefix("agent-"), "workflow_run": run,
                           "first_entry_at": first, "last_entry_at": last}
    found = check(where, body)
    # The original's hash only for a prompt that no rule changed: beside the redacted text, it would confirm a guess of
    # what any rule removed (an upstream author's address, D46), not only what the owner-specific rules remove.
    row["prompt_sha256"] = None if (found or body != prompt) else hashlib.sha256(prompt.encode()).hexdigest()
    row["transcript_sha256"] = hashlib.sha256(transcript.read_bytes()).hexdigest()
    if found:
        row["prompt"], row["withheld"] = None, _withheld(found)
    else:
        row["prompt"] = body
    return row


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("workflow_run") or ""), str(row["agent_id"])


def _earlier_rows(path: Path) -> list[dict[str, Any]]:
    """The agent records of earlier natural exports in ``path`` (none without the file). SystemExit, writing nothing, if
    the file cannot be read or a line is no such record: a record dropped unread would be lost without a word."""
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"export_prompts: {path.name} cannot be read ({exc.__class__.__name__}); nothing written") from None
    rows = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        if not isinstance(row, dict) or not isinstance(row.get("agent_id"), str):
            raise SystemExit(f"export_prompts: {path.name}:{n} is not an agent record of an earlier export; nothing written")
        rows.append(row)
    return rows


def export_natural(session_dir: Path, *, workflows: list[str], agents: list[str], check: Check,
                   out: Path | None = None) -> dict[str, int]:
    """The natural export (see the module docstring) into ``out`` (``experiments/prompts/natural``); returns counts
    (``kept``: the earlier exports' agent records that this export keeps as they were)."""
    out = out if out is not None else OUT / NATURAL_DIR
    sd = Path(session_dir)
    prompts_file = out / NATURAL_PROMPTS
    pending: dict[Path, str] = {}  # nothing is written until every text has passed redaction and the guard
    rows: list[dict[str, Any]] = []
    counts = {"workflows": 0, "agents": 0, "withheld": 0, "kept": 0}
    for rec in sorted((sd / "workflows").glob("wf_*.json")):
        d = json.loads(rec.read_text(encoding="utf-8"))
        script = d.get("script") or ""
        m = re.search(r"name:\s*'([^']+)'", script)
        name = d.get("workflowName") or (m.group(1) if m else "workflow")
        run = d.get("runId") or rec.stem
        if name in _NOT_EXPORTED or not any(fnmatch.fnmatchcase(name, g) or fnmatch.fnmatchcase(run, g) for g in workflows):
            continue
        stem = f"{name}__{run}"
        js, args_file = out / "workflows" / f"{stem}.js", out / "workflows" / f"{stem}.args.json"
        body, private_hit = redact(script)
        found = check(_where(out, js), body)
        orig = ("withheld (a note about the owner's messages or personal information was removed)" if private_hit
                else "withheld (the natural guard)" if found
                else "withheld (a redaction changed it)" if body != script else hashlib.sha256(script.encode()).hexdigest())
        start = (datetime.fromtimestamp(d["startTime"] / 1000, UTC).isoformat(timespec="seconds")
                 if d.get("startTime") else "unrecorded")
        header = (f"// Exported by scripts/export_prompts.py --natural from the workflow run record {run} "
                  f"(started {start}, finished {d.get('timestamp')}, status {d.get('status', 'unrecorded')}); "
                  f"sha256 of the original script: {orig}; "
                  + (f"script {_withheld(found)}" if found else f"sha256 of this export: {hashlib.sha256(body.encode()).hexdigest()}")
                  + ("; arguments in " + args_file.name if "args" in d else "; no arguments recorded")
                  + ". Redacted: owner messages and personal information, session paths/ids.\n")
        pending[js] = header + ("" if found else body)
        counts["withheld"] += bool(found)
        if "args" in d:
            text = json.dumps(d["args"], indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            a_body, _ = redact(text)
            a_found = check(_where(out, args_file), a_body)
            pending[args_file] = (json.dumps({"run_id": run, "args": None, "withheld": _withheld(a_found)}, indent=2) + "\n"
                                  if a_found else a_body)
            counts["withheld"] += bool(a_found)
        counts["workflows"] += 1
        for t in sorted((sd / "subagents" / "workflows" / run).glob("agent-*.jsonl")):
            row = _natural_row(t, run, check, _where(out, prompts_file))
            if row is not None:
                rows.append(row)
    for aid in agents:
        t = sd / "subagents" / f"agent-{aid}.jsonl"
        if not t.is_file():
            raise SystemExit(f"export_prompts: no standalone agent {aid} in {sd / 'subagents'}; nothing written")
        row = _natural_row(t, None, check, _where(out, prompts_file))
        if row is not None:
            rows.append(row)
    counts["agents"] = len(rows)
    counts["withheld"] += sum("withheld" in r for r in rows)
    merged = {_row_key(r): r for r in _earlier_rows(prompts_file)}  # an earlier export's records stay ...
    counts["kept"] = len(merged.keys() - {_row_key(r) for r in rows})
    merged.update((_row_key(r), r) for r in rows)  # ... unless this export gives the agent's record again
    pending[prompts_file] = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged.values())
    first_export = {OUT / "agent_prompts.jsonl", OUT / "README.md"}
    if any(p in first_export or (OUT / "workflows") in p.parents for p in pending):
        raise SystemExit("export_prompts: the natural export never writes the first export's files; nothing written")
    for path, text in pending.items():  # the finished files, as the scan will read them
        found = check(_where(out, path), text)
        if found:
            raise SystemExit(f"export_prompts: {_where(out, path)} would hold what the scan reports ({len(found)} finding(s)); "
                             "nothing written")
    for path, text in pending.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return counts


def main_natural(session_dir: str, *opts: str) -> None:
    ap = argparse.ArgumentParser(prog="export_prompts.py <session dir> --natural",
                                 description="the natural export (see the module docstring)")
    ap.add_argument("--natural", action="store_true", required=True)
    ap.add_argument("--private-redactions", required=True, help="owner-specific redactions, kept outside the repository")
    ap.add_argument("--natural-texts", required=True, help="the natural tasks (data/natural/tasks)")
    ap.add_argument("--screening-texts", action="append", required=True, metavar="FILE",
                    help="the screening texts of every sampled comment (S9 and S9x; the scan's --screening-texts)")
    ap.add_argument("--aidev-logins", required=True, help="the AIDev files (the scan's --aidev-logins)")
    ap.add_argument("--workflow", action="append", default=[], help="a workflow name or run id pattern (fnmatch)")
    ap.add_argument("--agent", action="append", default=[], help="a standalone agent id")
    a = ap.parse_args(opts)
    if not a.workflow and not a.agent:
        raise SystemExit("export_prompts --natural: name the natural workflow runs (--workflow) or agents (--agent)")
    load_private(a.private_redactions)
    scan = _scan_module()
    try:
        natural = scan.natural_material(a.natural_texts, a.screening_texts)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"export_prompts --natural: {exc}") from None
    logins = scan.login_patterns(scan.aidev_logins(a.aidev_logins))
    if not logins:  # the AIDev files gave no login for the sampled PRs: the login check would be off
        raise SystemExit(f"export_prompts --natural: {a.aidev_logins} gave no AIDev login for the sampled PRs; nothing written")
    counts = export_natural(Path(session_dir), workflows=a.workflow, agents=a.agent, check=scan_check(scan, natural, logins))
    dest = OUT / NATURAL_DIR
    print(f"exported {counts['workflows']} natural workflow run(s) and {counts['agents']} agent prompt(s) to "
          f"{dest.relative_to(R) if dest.is_relative_to(R) else dest} ({counts['withheld']} text(s) withheld by the "
          f"natural guard; {counts['kept']} agent record(s) of earlier exports kept)")


if __name__ == "__main__":
    main(*sys.argv[1:])
