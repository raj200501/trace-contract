"""Audit evaluation-side generation transcripts for forbidden reads (held-out integrity).

Usage: python scripts/audit_eval_generators.py CS-04 <transcript.jsonl>:<own workspace dir> [...]
       python scripts/audit_eval_generators.py --task-dir <task dir> [--profile controlled|natural]
           <transcript.jsonl>:<own workspace dir> [...]

The first form writes/updates tasks/<task>/labels/generator_audit.json with the first audit's substring rule over the
tool inputs (decision log D37): one record per agent, named after its workspace, with the transcript's sha256 and the
hits. It audits a controlled task under tasks/ only: a task id without tasks/<task>/task.json, or a natural PR-review
task (whose records must stay out of git, protocol §17.4), is refused.

``--task-dir`` names the task directory instead, wherever it lies (a natural PR-review task is built under the
git-ignored data/natural/tasks/<id>, protocol §17.4), writes/updates <task dir>/labels/generator_audit.json, and records
each agent's own workspace in its record (``own_workspace``), where ``scripts/strict_reaudit.py`` takes it from.
``--profile`` picks the audit:

* ``controlled`` (the default): the substring rule of the first form;
* ``natural``: the natural-agent profile, ``tracecontract.controlled.audit_natural_agent_transcript``
  (``natural-agent:v1``, fixed with the natural recipe in the decision log): everything outside the agent's own
  workspace is forbidden, with the study CLI's allowlist (``<repo>/.venv/bin/tracecontract lint-tests|check-proposals``
  on paths inside the workspace), the network rule and the tool set; tool inputs and tool outputs are both scanned. A record holds the transcript's sha256,
  the own workspace, the profile, the hits (tool inputs), the exposures (tool outputs) and ``flagged`` (any hit or
  exposure). A record whose transcript, workspace, hits and exposures are unchanged keeps its written ``assessment``
  and its ``strict_reaudit`` block; any other change drops them, since they assessed another audit.

A natural PR-review task is audited with the natural profile only, and the natural profile audits natural PR-review
tasks only. A natural agent's workspace must lie outside the repository; when it still exists, it is checked to be
one built for the task (its ``manifest.json``, as ``scripts/make_agent_workspace.py`` wrote it, names the task), or the
group of an attacker's states (workspaces of one attack role, which one agent works in: :data:`GROUP_ROLES`); a single
state of such a group, or a directory that holds the workspaces of several agents, is refused. A record is named after
its workspace; a record that names another workspace is not replaced (audit that one in a call of its own, or remove
its record first). Session ids, session-local paths and e-mail addresses are not written (decision log D21).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from tracecontract.controlled import (
    NATURAL_PROFILE,
    audit_generator_transcript,
    audit_natural_agent_transcript,
)
from tracecontract.ingest.claude_code import _redact_emails
from tracecontract.roots import is_natural_pr

R = Path(__file__).resolve().parents[1]
_SESSION_ID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_SCRATCHPAD = re.compile(r"/tmp/claude-0/[^/\s'\"`]+/[^/\s'\"`]+/scratchpad")
# A session's temporary directory and its directory of records (the natural records redact both).
_SESSION_TMP = re.compile(r"/tmp/claude-\d+/[^/\s'\"`]+/(?:<session>|[0-9a-f-]{36})")
_SESSION_RECORDS = re.compile(r"/root/\.claude/projects/[^/\s'\"`]+(?:/(?:<session>|[0-9a-f-]{36}))?")
NATURAL_RULES = {
    "profile": NATURAL_PROFILE,
    "script": "scripts/audit_eval_generators.py --profile natural",
    "forbidden": "everything outside the agent's own workspace (own_workspace): the repository, data/natural with it; the "
                 "study's home, with the sealed directory, the third-party data under /home/user/ext, the other "
                 "workspaces and the private run records; /root except tool binaries; every Claude session directory",
    "allowed": "the agent's own workspace, system locations, the sandbox's /repo, and the study CLI as "
               "<repo>/.venv/bin/tracecontract lint-tests|check-proposals on paths inside the workspace",
    "network": "WebFetch, WebSearch and MCP tool calls; curl, wget, nc, ssh, gh and tools of their kind; a container "
               "engine called directly (docker run, docker pull); git clone, fetch, pull, push, ls-remote, remote, "
               "submodule update and lfs fetch; pip download, index and search; pip install or wheel without --no-index; "
               "the downloading subcommands of other package managers (uv, pipx, npm, apt-get and others) without "
               "--offline; host code that uses the network (Python that imports urllib.request, http.client, requests, "
               "httpx, socket or a module of their kind; node, perl or ruby of that kind), given inline, in a heredoc or "
               "here-string, on standard input, or in a script the agent wrote and ran; wrappers (nice, timeout, env, "
               "xargs) are seen through, and bash -c strings, heredocs fed to a shell, eval and find -exec followed (the "
               "sandbox wrappers run offline and are not counted)",
    "tools": "Read, Write, Edit, Glob, Grep and the shell; any other tool is a hit",
    "scope": "tool inputs (hits) and tool outputs (exposures); every hit and exposure is a lead, assessed in writing",
}
# The roles whose agent works in a group of workspaces, one per state it writes (the attackers' a1..a4): the group is
# that agent's own workspace. Several agents of one role (eval-nm-1..3, mapper-1 and mapper-2) each have their own.
GROUP_ROLES = frozenset({"attack-initial", "attack-full"})


def _redact(x):
    """Session ids and session-local scratchpad paths are not published (decision log D21)."""
    if isinstance(x, str):
        return _SCRATCHPAD.sub("<scratchpad>", _SESSION_ID.sub("<session>", x))
    if isinstance(x, list):
        return [_redact(v) for v in x]
    if isinstance(x, dict):
        return {k: _redact(v) for k, v in x.items()}
    return x


def _redact_natural(x):
    """:func:`_redact`, the session's temporary directory and directory of records, and e-mail addresses (tool outputs
    can show any text)."""
    if isinstance(x, str):
        x = _redact(x)
        x = _SESSION_RECORDS.sub("<session-dir>", _SESSION_TMP.sub("<session-tmp>", x))
        return _redact_emails(x, {})
    if isinstance(x, list):
        return [_redact_natural(v) for v in x]
    if isinstance(x, dict):
        return {k: _redact_natural(v) for k, v in x.items()}
    return x


def _controlled_forbidden(task: str) -> tuple[str, ...]:
    return (f"tasks/{task}/verifiers", f"tasks/{task}/candidates", "trace-contract/results", "trace-contract/data",
            "trace-contract/docs", "cs_workspaces", f"gen_workspaces/{task}/", ".tc_sealed", "scratchpad/sealed",
            "scratchpad/scenarios", "scratchpad/reference", "/root/")


def _controlled_rules(forbidden: tuple[str, ...]) -> dict:
    return {"forbidden_substrings": list(forbidden), "allowed": ["the agent's own exported workspace", "/root/.local/bin/"],
            "scope": "tool inputs only (commands and file paths an agent passed to its tools); tool outputs are "
                     "not inspected (decision log D37)", "script": "scripts/audit_eval_generators.py"}


def main(task: str, *items: str) -> None:
    td = R / "tasks" / task
    if not (td / "task.json").is_file():
        raise SystemExit(f"{task}: no task directory tasks/{task} (task.json); the first form audits a controlled task "
                         "under tasks/, --task-dir <task dir> any other")
    if is_natural_pr(td):
        raise SystemExit(f"{task} is a natural PR-review task: audit its agents with --task-dir <task dir> --profile natural")
    forbidden = _controlled_forbidden(task)
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
    out["_rules"] = _controlled_rules(forbidden)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")


def _task_id(task_dir: Path) -> str:
    try:
        tid = json.loads((task_dir / "task.json").read_text(encoding="utf-8")).get("task_id")
    except (OSError, ValueError, AttributeError):
        tid = None
    return tid if isinstance(tid, str) and tid else task_dir.name


def workspace_problem(ws: Path, task: str, task_dir: Path, repo: Path = R) -> str | None:
    """Why ``ws`` cannot be a natural agent's own workspace for ``task``, or None.

    It must be an absolute path outside the repository and the task directory. If it exists, it must be a workspace
    built for the task (its ``manifest.json`` names the task) or a plain group of such workspaces of one role, as the
    attackers' states are; a directory that holds the workspaces of several roles would make them all the agent's own."""
    if not ws.is_absolute():
        return f"{ws}: a workspace is named by its absolute path"
    real, repo, td = ws.resolve(), repo.resolve(), task_dir.resolve()
    for root, what in ((repo, "the repository"), (td, "the task directory")):
        if real == root or root in real.parents or real in root.parents:
            return f"{ws} lies inside (or around) {what}"
    if not real.exists():
        return None  # sealed after the run (as D50 sealed the local workspaces): the record names it as it was
    if not real.is_dir():
        return f"{ws} is not a directory"

    def manifest(d: Path) -> dict | None:
        try:
            m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return m if isinstance(m, dict) else None

    def members(d: Path) -> list[dict]:
        return [m for m in (manifest(e) for e in sorted(d.iterdir()) if e.is_dir()) if m is not None] if d.is_dir() else []

    own = manifest(real)
    if own is not None:
        if own.get("task_id") != task:
            return f"{ws}: its manifest.json names task {own.get('task_id')!r}, not {task}"
        group = members(real.parent) if manifest(real.parent) is None else []
        if own.get("role") in GROUP_ROLES and group and {m.get("role") for m in group} == {own.get("role")}:
            return (f"{ws} is one state of the attacker's group {real.parent}: the attacker works in the whole group; "
                    "name the group directory")
        return None
    inner = members(real)
    if not inner:
        return f"{ws} is neither a workspace (no manifest.json) nor a group of workspaces"
    if {m.get("task_id") for m in inner} != {task}:
        return f"{ws}: the workspaces in it are not all of task {task}"
    roles = {m.get("role") for m in inner}
    if len(roles) != 1:
        return f"{ws} holds the workspaces of several roles; name the agent's own workspace"
    if not roles <= GROUP_ROLES:
        return (f"{ws} holds the workspaces of several agents of role {next(iter(roles))!r}, each its own; name the "
                "agent's own workspace")
    return None


def _items(items: list[str]) -> list[tuple[Path, Path]]:
    out = []
    for item in items:
        transcript, sep, own = item.rpartition(":")
        if not sep or not transcript or not own:
            raise SystemExit(f"expected TRANSCRIPT:WORKSPACE, got {item!r}")
        if not Path(transcript).is_file():
            raise SystemExit(f"{transcript}: no such transcript")
        out.append((Path(transcript), Path(own)))
    names = [ws.name for _, ws in out]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise SystemExit(f"two transcripts would share the record of workspace {dup}: audit them in separate calls")
    return out


def audit_task(task_dir: Path, items: list[tuple[Path, Path]], *, profile: str = "controlled") -> dict:
    """Audit ``items`` (transcript, own workspace) of the task at ``task_dir`` and write <task dir>/labels/generator_audit.json
    (see the module docstring); return what was written."""
    task = _task_id(task_dir)
    natural_task = is_natural_pr(task_dir)
    if natural_task and profile != "natural":
        raise SystemExit(f"{task} is a natural PR-review task: audit its agents with --profile natural")
    if profile == "natural" and not natural_task:
        raise SystemExit(f"{task} is not a natural PR-review task: the natural profile audits natural agents only")
    out_path = task_dir / "labels" / "generator_audit.json"
    out: dict[str, Any] = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    forbidden = _controlled_forbidden(task)
    for _, own in items:
        prev = out.get(own.name)
        named = prev.get("own_workspace") if isinstance(prev, dict) else None
        if isinstance(named, str) and Path(named) != own:
            raise SystemExit(f"the record {own.name!r} of {task} holds the audit of the workspace {named}, not {own}: audit "
                             "it apart, or remove that record first")
    for transcript, own in items:
        sha = hashlib.sha256(transcript.read_bytes()).hexdigest()
        name = own.name
        if profile == "natural":
            problem = workspace_problem(own, task, task_dir)
            if problem:
                raise SystemExit(problem)
            try:
                hits, exposures = audit_natural_agent_transcript(transcript, task=task, workspace=str(own))
            except ValueError as exc:  # the profile's own checks of the workspace
                raise SystemExit(str(exc)) from None
            rec: dict[str, Any] = _redact_natural({"transcript_sha256": sha, "own_workspace": str(own), "profile": NATURAL_PROFILE,
                                                   "hits": hits, "exposures": exposures, "flagged": bool(hits or exposures)})
            prev = out.get(name)
            old: dict[str, Any] = prev if isinstance(prev, dict) else {}
            if {k: old.get(k) for k in rec} == rec:  # the same audit: its written assessments still apply
                rec.update({k: old[k] for k in ("assessment", "strict_reaudit") if k in old})
            print(name, "hits:", len(hits), "exposures:", len(exposures))
            for h in rec["hits"][:8]:
                print("   ", h["tool"], h["path"], "|", h["why"], "|", str(h["text"])[:120])
            for x in rec["exposures"][:8]:
                print("    output:", x["tool"], x["path"], "|", x["why"])
        else:
            found = audit_generator_transcript(transcript, forbidden=forbidden, allowed=(str(own), "/root/.local/bin/"))
            rec = {"transcript_sha256": sha, "own_workspace": str(own), "hits": _redact(found)}
            print(name, "hits:", len(found))
            for h in found[:8]:
                print("   ", h["tool"], h["match"], "|", h["text"][:160])
        out[name] = rec
    out["_rules"] = NATURAL_RULES if profile == "natural" else _controlled_rules(forbidden)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def cli(argv: list[str]) -> int:
    if argv and not argv[0].startswith("-"):  # the first form: a task id under tasks/
        main(*argv)
        return 0
    ap = argparse.ArgumentParser(prog="audit_eval_generators.py", description="Audit generation transcripts for forbidden "
                                 "reads (see the module docstring).")
    ap.add_argument("--task-dir", required=True, type=Path, help="the task directory (tasks/<id>, data/natural/tasks/<id>)")
    ap.add_argument("--profile", choices=("controlled", "natural"), default="controlled",
                    help="controlled: the first audit's substring rule; natural: natural-agent:v1")
    ap.add_argument("items", nargs="+", metavar="TRANSCRIPT:WORKSPACE", help="an agent's transcript and its own workspace")
    a = ap.parse_args(argv)
    if not (a.task_dir / "task.json").is_file():
        ap.error(f"{a.task_dir} is not a task directory (no task.json)")
    audit_task(a.task_dir, _items(a.items), profile=a.profile)
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
