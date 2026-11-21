"""What a session's transcript shows about its repository: base commit, identity, licence (decision log D47).

* :func:`commit_evidence` reads git output in tool results (``git log``, ``rev-parse``,
  ``status``, commits the session made, ``toolUseResult.gitOperation``) and the harness's
  ``pr-link`` entries, and says whether the session's base commit could be pinned.
* :func:`licence_evidence` reads ``LICENSE``/``COPYING`` files and package manifests at the
  workspace root that the session read, wrote or printed, and maps them to SPDX identifiers.

A repository's identity leaves this module only as the sha256 of ``host/owner/name``: a URL
may be recorded only for a public repository identified with certainty, and publicness
cannot be checked offline. Redacted owners (``[USER]``, ``[HANDLE]``) never identify one.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schemas import Event, EventKind, Session, sha256_text
from .replay import EDIT_TOOLS, SHELL_TOOLS, PathMap, RawExtra, read_view
from .shell_writes import command_words, logical_lines, simple_commands

_SHA = r"[0-9a-f]{7,40}"
_LOG_LINE = re.compile(rf"^(?:commit )?({_SHA})\b", re.M)
_COMMIT_MADE = re.compile(rf"^\[[^\]\s]+(?: \(root-commit\))? ({_SHA})\] ", re.M)
_HEAD_AT = re.compile(rf"\bHEAD (?:detached at|is now at) ({_SHA})\b")
_REMOTE = re.compile(r"(?:https?://(?:[^@/\s]+@)?|git@)(github\.com|gitlab\.com|codeberg\.org|bitbucket\.org)[/:]"
                     r"([A-Za-z0-9_.\[\]-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?=[\s/)'\"#]|$)")
_REDACTED_OWNER = re.compile(r"^\[.*\]$|^(?:USER|HANDLE|NAME|REDACTED\w*)$", re.I)
_CLEAN = re.compile(r"nothing to commit, working tree clean|nothing added to commit")
_DIRTY = re.compile(r"Changes not staged for commit|Changes to be committed|Untracked files:")
_GH_REPO = re.compile(r'"nameWithOwner"\s*:\s*"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"')
_GH_PUBLIC = re.compile(r'"visibility"\s*:\s*"PUBLIC"')


@dataclass
class CommitEvidence:
    """Base-commit evidence of one session (SHAs, counts and a hash; no URLs, no names)."""

    head_shas: list[str] = field(default_factory=list)  # HEAD as git output showed it, before the first change
    head_after_change: list[str] = field(default_factory=list)  # HEAD observations after the first change
    clean_tree: bool | None = None  # git status before the first change: clean, dirty, or not shown
    commits_made: list[str] = field(default_factory=list)  # SHAs of commits the session created
    pr_links: int = 0  # distinct pull requests the session linked or created
    repo_identified: bool = False  # an unredacted host/owner/name in remote, fetch, push or PR output
    repo_sha256: str | None = None  # sha256 of "host/owner/name", lower case
    cwd_matches_repo: bool = False  # the workspace directory has the repository's name
    branch_named: bool = False  # a branch other than HEAD was recorded
    public_in_transcript: bool = False  # a GitHub API answer in the session called this repository PUBLIC

    @property
    def status(self) -> str:
        """``pinnable_unverified``: identified repository, HEAD before the first change, clean tree;
        ``linked_commit_unverified``: identified repository and a commit or PR the session made;
        ``commit_seen_repository_unidentified``, ``repository_identified_no_commit`` or ``none``.
        Offline nothing is ``recoverable``: publicness and the commit need a network check."""
        if self.repo_identified and self.head_shas and self.clean_tree:
            return "pinnable_unverified"
        if self.repo_identified and (self.commits_made or self.pr_links):
            return "linked_commit_unverified"
        if self.head_shas or self.commits_made or self.head_after_change:
            return "commit_seen_repository_unidentified" if not self.repo_identified else "repository_identified_no_commit"
        return "repository_identified_no_commit" if self.repo_identified else "none"

    def summary(self) -> dict[str, Any]:
        return {"status": self.status, "head_shas_before_change": self.head_shas[:3],
                "head_full_sha": any(len(s) == 40 for s in self.head_shas), "head_seen_after_change": len(self.head_after_change),
                "clean_tree_before_change": self.clean_tree, "commits_made": self.commits_made[:5],
                "pr_links": self.pr_links, "repository_identified": self.repo_identified,
                "repository_sha256": self.repo_sha256, "cwd_matches_repository": self.cwd_matches_repo,
                "branch_named": self.branch_named, "public_in_transcript": self.public_in_transcript,
                "public_verified": False}


def raw_entries(path: str | Path, entry_type: str) -> list[dict[str, Any]]:
    """Raw JSONL entries of one ``type`` (e.g. ``pr-link``), which the parser does not keep."""
    out = []
    for line in Path(path).read_bytes().decode("utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict) and e.get("type") == entry_type:
            out.append(e)
    return out


def _git_subcommands(cmd: str, shell: str) -> list[list[str]]:
    out = []
    for line, _bodies, _q in logical_lines(cmd):
        for words in simple_commands(line, shell != "PowerShell"):
            ws = command_words(words)
            if ws and posixpath.basename(ws[0]).lower() in ("git", "git.exe"):
                rest = ws[1:]
                while rest and rest[0].startswith("-"):
                    rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
                if rest:
                    out.append(rest)
    return out


def _plain_head_log(args: list[str]) -> bool:
    """``git log`` of HEAD itself (no other ref, no path filter, no --all)."""
    if args[0] != "log" or "--" in args or any(a in ("--all", "--branches", "--remotes", "--reverse") for a in args):
        return False
    refs = [a for a in args[1:] if not a.startswith("-") and not a.isdigit()]
    return all(r in ("HEAD", "HEAD~0") for r in refs)


def _first_change(session: Session, results: dict[str, Event]) -> int:
    for ev in session.events:
        if ev.kind == EventKind.tool_call and ev.tool_name in EDIT_TOOLS and not ev.is_sidechain:
            res = results.get(ev.tool_call_id or "")
            if res is not None and not res.is_error and "doesn't want to proceed" not in res.text:
                return ev.index
    return len(session.events)


def _identity(host: str, owner: str, name: str) -> str | None:
    if _REDACTED_OWNER.match(owner) or _REDACTED_OWNER.match(name):
        return None
    return f"{host.lower()}/{owner.lower()}/{name.lower()}"


def commit_evidence(session: Session, extras: dict[int, RawExtra], pr_links: list[dict[str, Any]] = (),
                    root: str | None = None) -> CommitEvidence:
    """Base-commit evidence from git output in tool results, ``gitOperation`` fields and ``pr-link`` entries."""
    ev_out = CommitEvidence()
    results = {e.tool_call_id: e for e in session.events if e.kind == EventKind.tool_result and e.tool_call_id}
    first = _first_change(session, results)
    identities: list[str] = []
    public: set[str] = set()
    prs: set[str] = set()
    for ev in session.events:
        if ev.kind != EventKind.tool_call or ev.tool_name not in SHELL_TOOLS or ev.is_sidechain:
            continue
        res = results.get(ev.tool_call_id or "")
        cmd = (ev.tool_input or {}).get("command")
        if res is None or not isinstance(cmd, str) or "doesn't want to proceed" in res.text:
            continue
        subs = _git_subcommands(cmd, str(ev.tool_name))
        n_cmds = sum(len(simple_commands(line, ev.tool_name != "PowerShell")) for line, _b, _q in logical_lines(cmd))
        before = ev.index < first
        out = res.text
        for args in subs:
            head = None
            if _plain_head_log(args) and not res.is_error:
                m = _LOG_LINE.search(out)
                head = m.group(1) if m else None
            elif args[:1] == ["rev-parse"] and "HEAD" in args:
                m = re.search(rf"^({_SHA})\s*$", out, re.M)
                head = m.group(1) if m else None
            elif args[:1] == ["status"] and before:
                short = any(a in ("--short", "-s") or a.startswith("--porcelain") for a in args)
                dirty: bool | None = None
                if short and n_cmds == 1:  # the output is the status alone
                    dirty = bool(out.strip()) and not out.strip().startswith("(Bash completed with no output)")
                elif not short and (_CLEAN.search(out) or _DIRTY.search(out)):
                    dirty = bool(_DIRTY.search(out))
                if dirty is not None:
                    ev_out.clean_tree = False if dirty else ev_out.clean_tree is not False
            if head:
                (ev_out.head_shas if before else ev_out.head_after_change).append(head)
            if args[:1] in (["remote"], ["fetch"], ["pull"], ["push"], ["clone"]):
                identities += [i for m in _REMOTE.finditer(out) if (i := _identity(*m.groups()))]
        if _GH_PUBLIC.search(out):
            public |= {i for m in _GH_REPO.finditer(out) if (i := _identity("github.com", *m.groups()))}
        if subs and (m := _HEAD_AT.search(out)):
            (ev_out.head_shas if before else ev_out.head_after_change).append(m.group(1))
        ev_out.commits_made += _COMMIT_MADE.findall(out) if any(a[:1] == ["commit"] for a in subs) else []
        tur = extras.get(res.source.line, RawExtra()).tool_use_result
        op = tur.get("gitOperation") if isinstance(tur, dict) else None
        if isinstance(op, dict):
            sha = (op.get("commit") or {}).get("sha") if isinstance(op.get("commit"), dict) else None
            if isinstance(sha, str) and re.fullmatch(_SHA, sha):
                ev_out.commits_made.append(sha)
            pr = op.get("pr") if isinstance(op.get("pr"), dict) else None
            if pr and isinstance(pr.get("url"), str):
                prs.add(pr["url"].rstrip("/").lower())
                identities += [i for m in _REMOTE.finditer(pr["url"]) if (i := _identity(*m.groups()))]
    for link in pr_links:
        url = str(link.get("prUrl") or "")
        prs.add(url.rstrip("/").lower())
        identities += [i for m in _REMOTE.finditer(url) if (i := _identity(*m.groups()))]
    ev_out.pr_links = len(prs - {""})
    ev_out.commits_made = list(dict.fromkeys(ev_out.commits_made))
    ev_out.head_shas = list(dict.fromkeys(ev_out.head_shas))
    if identities:
        top = max(set(identities), key=identities.count)
        ev_out.repo_identified, ev_out.repo_sha256 = True, sha256_text(top)
        ev_out.public_in_transcript = top in public
        name = top.rsplit("/", 1)[-1]
        cwd_name = posixpath.basename((root or "").rstrip("/")).lower()
        ev_out.cwd_matches_repo = bool(cwd_name) and cwd_name == name
    ev_out.branch_named = any(b and b != "HEAD" for b in session.metadata.get("git_branch", []))
    return ev_out


# ---------------------------------------------------------------------------
# Licences
# ---------------------------------------------------------------------------

_LICENCE_FILE = re.compile(r"^(?:licen[cs]e|copying|unlicense)(?:[-_.](?:md|txt|rst|mit|apache))?$", re.I)
_MANIFESTS = ("package.json", "pyproject.toml", "cargo.toml", "setup.cfg", "composer.json")
_SPDX = {s.lower(): s for s in (
    "MIT", "ISC", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later",
    "GPL-3.0-only", "GPL-3.0-or-later", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later", "Unlicense", "0BSD", "Zlib", "EUPL-1.2", "CC0-1.0", "BSL-1.0", "etalab-2.0")}
_SPDX.update({"gpl-2.0": "GPL-2.0-only", "gpl-3.0": "GPL-3.0-only", "lgpl-2.1": "LGPL-2.1-only",  # deprecated ids
              "lgpl-3.0": "LGPL-3.0-only", "agpl-3.0": "AGPL-3.0-only"})


def licence_from_text(text: str) -> str | None:
    """The SPDX identifier of a licence text's opening, or None."""
    t = " ".join(text.split())[:3000]
    later = bool(re.search(r"(?i)any later version", t))
    rules = [
        (r"(?i)GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL-3.0-or-later" if later else "AGPL-3.0-only"),
        (r"(?i)GNU LESSER GENERAL PUBLIC LICENSE\s+Version 3", "LGPL-3.0-or-later" if later else "LGPL-3.0-only"),
        (r"(?i)GNU LESSER GENERAL PUBLIC LICENSE\s+Version 2\.1", "LGPL-2.1-or-later" if later else "LGPL-2.1-only"),
        (r"(?i)GNU GENERAL PUBLIC LICENSE\s+Version 3", "GPL-3.0-or-later" if later else "GPL-3.0-only"),
        (r"(?i)GNU GENERAL PUBLIC LICENSE\s+Version 2", "GPL-2.0-or-later" if later else "GPL-2.0-only"),
        (r"(?i)Apache License,?\s+Version 2\.0", "Apache-2.0"),
        (r"(?i)Mozilla Public License,?\s+(?:Version|v\.?)\s*2\.0", "MPL-2.0"),
        (r"(?i)European Union Public Licen[cs]e", "EUPL-1.2"),
        (r"(?i)Licence Ouverte|Open Licen[cs]e.{0,20}Etalab", "etalab-2.0"),
        (r"(?i)This is free and unencumbered software released into the public domain", "Unlicense"),
        (r"(?i)^\s*ISC License|Permission to use, copy, modify, and/?or distribute this software for any purpose", "ISC"),
        (r"(?i)^\s*MIT License|Permission is hereby granted, free of charge, to any person", "MIT"),
        (r"(?i)Redistribution and use in source and binary forms.{0,600}Neither the name", "BSD-3-Clause"),
        (r"(?i)Redistribution and use in source and binary forms", "BSD-2-Clause"),
        (r"(?i)Boost Software License", "BSL-1.0"),
    ]
    return next((spdx for pat, spdx in rules if re.search(pat, t)), None)


def licence_from_manifest(name: str, text: str) -> str | None:
    """The SPDX expression a package manifest declares (simple identifiers only)."""
    pats = {"package.json": r'"license"\s*:\s*"([^"]{1,60})"', "composer.json": r'"license"\s*:\s*"([^"]{1,60})"',
            "pyproject.toml": r'(?m)^\s*license\s*=\s*(?:\{\s*text\s*=\s*)?"([^"]{1,60})"',
            "cargo.toml": r'(?m)^\s*license\s*=\s*"([^"]{1,60})"', "setup.cfg": r"(?m)^\s*license\s*=\s*([^\s#]{1,60})"}
    m = re.search(pats[name], text)
    if not m:
        return None
    parts = re.split(r"\s+(OR|AND)\s+", m.group(1).strip().strip("()"))
    if any(p not in ("OR", "AND") and p.lower() not in _SPDX for p in parts):
        return None
    return " ".join(p if p in ("OR", "AND") else _SPDX[p.lower()] for p in parts)


_CLAIM = re.compile(r"(?i)\b(MIT|ISC|Apache(?:[ -]2(?:\.0)?)?|A?GPL(?:[ -]?v?[23](?:\.0)?)?|LGPL|BSD|MPL(?:[ -]2\.0)?"
                    r"|Unlicense)\b"
                    r"[^.\n]{0,25}\blicen[cs]")
_CLAIM_IDS = {"mit": "MIT", "isc": "ISC", "apache": "Apache-2.0", "bsd": "BSD-3-Clause", "mpl": "MPL-2.0",
              "unlicense": "Unlicense", "lgpl": "LGPL-3.0-only", "gpl": "GPL-3.0-only", "agpl": "AGPL-3.0-only"}


def licence_evidence(session: Session, extras: dict[int, RawExtra], paths: PathMap | None) -> dict[str, str | None]:
    """``{"spdx", "evidence", "claimed"}``: the root licence the transcript shows, how, and any licence
    the user only claimed in chat (a claim is not a licence)."""
    found: tuple[str, str] | None = None
    missing = False
    results = {e.tool_call_id: e for e in session.events if e.kind == EventKind.tool_result and e.tool_call_id}
    for ev in session.events:
        if ev.kind != EventKind.tool_call or ev.is_sidechain:
            continue
        ti, res = ev.tool_input or {}, results.get(ev.tool_call_id or "")
        rel = paths.rel(str(ti.get("file_path", "")), (extras.get(ev.source.line) or RawExtra()).cwd) \
            if paths and isinstance(ti.get("file_path"), str) else None
        base = posixpath.basename(rel or "")
        at_root = rel is not None and "/" not in rel
        text, how = None, None
        if at_root and ev.tool_name == "Write" and isinstance(ti.get("content"), str):
            text, how = ti["content"], "written in session"
        elif at_root and ev.tool_name == "Read" and res is not None and not res.is_error:
            view = read_view(res, (extras.get(res.source.line) or RawExtra()).tool_use_result)
            text, how = ("\n".join(view[1]) if view else None), "file read"
        if text and _LICENCE_FILE.match(base):
            spdx = licence_from_text(text)
            if spdx and not (found and found[1] == "licence written in session" and how == "file read"):
                found = (spdx, f"licence {how}")
        elif text and base.lower() in _MANIFESTS:
            spdx = licence_from_manifest(base.lower(), text)
            found = found or ((spdx, f"manifest {how}") if spdx else None)
        cmd = ti.get("command")
        if ev.tool_name in SHELL_TOOLS and isinstance(cmd, str) and res is not None and \
                re.search(r"(?i)\b(?:cat|head|type|get-content|gc|more|less)\b[^|;&\n]*\b(?:LICEN[CS]E|COPYING)", cmd):
            spdx = licence_from_text(res.text)
            found = (spdx, "licence printed by a shell command") if spdx else found
            missing = missing or bool(re.search(r"(?i)no such file|cannot find|no licen[cs]e", res.text)) and not spdx
    claims = [m.group(1).lower().split()[0].split("-")[0].rstrip("v0123456789.") for p in session.user_prompts()
              for m in _CLAIM.finditer(p.text)]
    claimed = next((_CLAIM_IDS[c] for c in claims if c in _CLAIM_IDS), None)
    if found:
        return {"spdx": found[0], "evidence": found[1], "claimed": claimed}
    return {"spdx": None, "evidence": "no licence file found" if missing else None, "claimed": claimed}
