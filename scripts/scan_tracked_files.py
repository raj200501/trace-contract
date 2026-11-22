"""Scan what a push would publish for credentials, session-local paths and e-mail addresses.

Usage: python scripts/scan_tracked_files.py [--private-markers <file.json>] [--all-history] [--aidev-logins <dir>]
                                             [--natural-texts <dir> [--screening-texts <file.jsonl> ...]]

Scans (1) the working tree: tracked files plus untracked files that are not git-ignored
(what the next commit could add), and (2) every file version in the commits that a push
would send: the commits in ``@{upstream}..HEAD`` (all commits if the branch has no
upstream), or in the whole history with ``--all-history`` (audit mode). A file removed
in a later commit is still published by a push of the commit that added it. It also scans
what a push publishes besides file contents: the file paths, the commit messages, author
and committer fields of the same commits, and the names and messages of tags and of the
current branch (decision log D46).

Generic rules: credential formats, private-key headers, the session-local paths of the
build environment, and e-mail addresses not on the allowlist below and not at a domain reserved
for documentation (RFC 2606, RFC 6761: ``example.com``, ``.test``, ``.invalid`` ...). ``--private-markers``
adds case-insensitive regexes from a JSON file kept outside the repository
(``{"forbidden": [...]}``, the format of the prompt export's private redactions, which
also lists the build session id); their matches are reported by location and marker
number only, so the output repeats nothing private. Exit code 1 if anything is found.

``--aidev-logins <dir>`` adds the checks of the natural PR-review screening (decision log
D47, D51). It reads the comment ids of the stage-S9 sample from
``data/manifests/screening_natural_aidev.json`` and loads, from the AIDev parquet files in
``<dir>`` at scan time and in memory only, every login connected to the PRs of those comments:
the authors of every review comment in those PRs, the PR authors, the authors of every issue
linked to them, the authors and committers of their commits, and the repository owners that act
as accounts in AIDev (the ``{owner}`` rule), plus the git author names in their commits that
contain a space. Bot and agent accounts and GitHub's web committer are left out: they are not
people, and the study's own text names them. This needs DuckDB (the ``data`` extra); run the
scan with ``python -I`` then, as the parquet files are third-party data. Any of these logins or
names, as a whole word or phrase in any case, is reported by location and number only. It also
reports @handle patterns in files under ``tasks/`` and ``data/``, except code (a decorator or
docstring tag, ``@name(``, ``@name.attr``, ``@name_x``, a template ``@NAME@``, a decorator line
in a Python file; :func:`tracecontract.ingest.pseudonymize_pr.is_code_at`), an npm package scope
in a registry URL, and the code words of ``HANDLE_ALLOW`` in the files it names. The logins of the
S9 extension's sample (protocol §19.2) are not loaded: that awaits the owner's decision on
organisation accounts (decision log D66).

``--natural-texts <dir>`` (``data/natural/tasks``) adds the checks for the natural arm's material
(protocol §17.4, decision log D47; build plan WP-H), with the matchers of
:mod:`tracecontract.natural_privacy`, over the same file versions and push metadata. It reads every
task directory under ``<dir>`` (accepted, rejected and half-built families of both samples, the
extension's included) and the tasks' base snapshots (``snapshots`` beside ``<dir>``), and stops with an
error, scanning nothing, if a task's file exists but cannot be read, if no directory under ``<dir>``
holds a ``task.json`` or ``session.json`` (a root one level too high or too low), or if a base snapshot
that a task's ``snapshot.json`` records is missing or holds no code line:

* thread text: a window of 60 characters or of 8 words of any session event's text (the issue, the PR
  body, the commit messages, the diff hunk, the review comment, the replies) or contract quote of a task in
  ``<dir>``, in any file, also inside a JSON string (even one inside another), an HTML page (with or
  without its tags), numbered lines, a percent-encoded URL, LaTeX markup (``\\texttt{...}``,
  ``\\verb|...|``, accent commands) or decomposed (NFD) letters. A window must hold 4 words with a letter and
  span two whitespace-separated tokens (a path, URL or hash alone is not one), or hold 20 characters of a
  script written without spaces. Cut out of the texts, so that no window spans them: Python traceback
  frames of the standard library and of installed packages that are not the task's own (its base snapshot
  holds neither the frame's file nor a directory of the frame's package), the header lines of a traceback,
  pytest's banners and pip's resolver errors, and every line that the repository held at
  ``PRE_NATURAL_REV``, before any natural task existed (an import block, a pytest summary line). A text
  (or a part of one between the cuts) too short for a window of words is matched whole: all its words in a
  row, whatever the whitespace, case, punctuation or escaping between them. The minimum is 3 words with a
  letter in two whitespace-separated tokens and 12 characters, or 8 characters of a script written without
  spaces; a shorter text ("Looks good") is too generic to tell apart;
* ``--screening-texts <file.jsonl>`` (repeatable; the S9 and S9x sample texts that ``scripts/screen_aidev.py
  --texts-out`` wrote outside the repository) adds the same checks for the texts of every sampled comment,
  built or not: the comment, its issue, its PR's title and its diff hunk. The files must hold every comment
  id of both screening manifests (``SCREENING_MANIFESTS``). Without them, the last line of the output says
  that the sampled comments that no natural task holds were not checked (the natural export guard and
  ``scripts/publish_natural_run.py`` require them);
* the natural tasks' repositories: the owner in the URL form ``/<owner>`` and the name in the forms that
  name a repository (``<owner>/<name>``, a URL path ``<host>/<account>/<name>``) in any file, and the name as
  a whole word in the natural arm's own files (:func:`bare_name_scope`: under ``NATURAL_SCOPES``, a path
  with a directory or file named for the natural arm or for a natural task, where natural material and
  natural run outputs are written, and the natural arm's records whose name does not say so,
  ``NATURAL_ARM_RECORDS``), or in any file if it holds a separator or a digit (``-``, ``_`` and ``.`` count
  as one). Other repository names are often ordinary words, so elsewhere (the controlled tasks, the first
  prompt export, the study's documents) only their repository forms are reported. Lines that are the
  record fields of ``NATURAL_RECORDS`` (the JSON member of that name) are not reported, neither for a
  repository's name nor for a base snapshot's line (a repository's URL);
* upstream code: the check ids of the natural tasks' verifiers (B1's upstream test names) in any file,
  and the lines of their candidates' patches and of their verifiers' files (B1's overlay) everywhere except
  the study's own code (:func:`study_code`) and the controlled tasks' material, where common idioms are
  expected. A line that the repository already held at ``PRE_NATURAL_REV`` (``from pathlib import Path``)
  is an idiom and is not used. The lines of every Python file of their base snapshots, whatever its size,
  are used too where they name something of their own (a word that at most one line of the repository at
  ``PRE_NATURAL_REV`` holds, :func:`tracecontract.natural_privacy.distinctive_line`), and are reported
  everywhere except the study's own code and the controlled arm's outputs (:func:`base_code_scope`). A file
  that cannot be read stops the scan; a file with a NUL byte holds no line of code, and the last line of
  the output counts such files;
* @handles are reported in ``results/`` and ``experiments/`` too, where (only there: ``tasks/`` and ``data/`` keep
  their rules) CSS at-rules of HTML and CSS files and template references (``NAME=@ref``) are code, and the natural
  prompts' own words for the forms they forbid (``@handles``) are allowed by ``HANDLE_ALLOW``; e-mail addresses are
  reported by the sha256 of the address.

Each finding names its location and the natural task (or screened comment), never the window, name,
code or address. Without ``--natural-texts`` the scan, its findings and its output are as before.

This is a manual step, not a git hook: the builder runs it with the private markers
before each push (decision log D44).
"""

from __future__ import annotations

import functools
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tracecontract.natural_privacy import NaturalMaterial

R = Path(__file__).resolve().parents[1]

EMAIL = re.compile(r"[A-Za-z0-9._%+-]*[A-Za-z0-9]@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
RULES = [
    # Split so that this rule's own source does not match it.
    ("session-local path", re.compile("/tmp/claude-0/" + "-home|/root/" + r"\.claude/projects/")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("API key (sk-)", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
# Public strings that look like e-mail addresses, each with the reason it may stay.
ALLOW = {
    "markus@m-siemens.de": "upstream copyright notice in THIRD_PARTY_LICENSES/tinydb.txt, embedded in the HTML reports "
                           "(the MIT licence requires the notice)",
    "jane.doe@example.com": "synthetic address in a redaction test",
    "git@github.com": "SSH host name in a repository URL",
    "noreply@anthropic.com": "co-author trailer that the session's attribution rules add to every commit message",
}
# Allowed by domain: the git author's GitHub no-reply address in commit metadata.
ALLOW_DOMAINS = ("users.noreply.github.com",)
# Domains reserved for documentation and testing (RFC 2606, RFC 6761): no address there belongs to anyone.
RESERVED_DOMAINS = ("example.com", "example.org", "example.net", "example", "invalid", "test", "localhost")


def _reserved(addr: str) -> bool:
    domain = addr.rsplit("@", 1)[1].lower()
    return any(domain == d or domain.endswith("." + d) for d in RESERVED_DOMAINS)
# --aidev-logins: the screening manifest with the sampled comment ids, the files whose @handles are reported, and the
# public forms of @name allowed there (code; an npm package scope in a registry URL).
AIDEV_MANIFEST = R / "data" / "manifests" / "screening_natural_aidev.json"
AIDEV_TABLES = ("pull_request", "pr_review_comments", "pr_commits", "related_issue", "issue")
# --screening-texts: the manifests whose sampled comments the screening texts must all hold (the S9 sample and its
# extension, protocol §19.2). Only the S9 sample's logins are loaded by --aidev-logins (D66).
SCREENING_MANIFESTS = (AIDEV_MANIFEST, R / "data" / "manifests" / "screening_natural_aidev_s9x.json")
HANDLE_SCOPES = ("tasks/", "data/")
HANDLE = re.compile(r"(?<![A-Za-z0-9._%+-])@[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}(?:\[bot\])?")
NPM_SCOPE = re.compile(r"(?:registry\.npmjs\.org|npmjs\.com/package)/$")
# Code words written as @word that no general rule recognises: (path prefix, word) -> why it may stay.
HANDLE_ALLOW = {
    ("tasks/CS-04/", "consumer"): "the more_itertools.consumer decorator, named in a comment of the upstream tests/test_more.py",
    ("experiments/prompts/workflows/tracecontract-brief-verification__wf_7df3c712-ef2.js", "misc"):
        "the BibTeX entry type @misc, named in a prompt that asks for BibTeX entries",
    **{("experiments/prompts/natural/", w): "the natural workflows' own privacy rules name the forms they forbid "
                                           "(\"no logins, @handles or e-mail addresses\"): a word, not a handle"
       for w in ("handle", "handles", "mention", "mentions")},
}
# --natural-texts: the further @handle scopes, where the files whose @-rules are CSS and the template references
# NAME=@ref (the natural templates) are code; tasks/ and data/ keep the rules above.
NATURAL_HANDLE_SCOPES = ("results/", "experiments/")
CSS_FILES = (".html", ".htm", ".css", ".svg")
CSS_AT_RULES = frozenset({"media", "import", "font-face", "keyframes", "supports", "page", "charset", "namespace", "layer",
                          "container", "property", "counter-style", "font-feature-values", "font-palette-values",
                          "starting-style", "scope", "document", "viewport"})
# --natural-texts: where a natural repository's name counts as a whole word: the natural arm's own files under the
# directories where natural material and natural run outputs are written (bare_name_scope), and the JSON members that
# name natural repositories by design, per file, with the reason.
NATURAL_SCOPES = ("tasks/", "data/", "results/", "experiments/")
# A directory or file named for the natural arm ("natural" as a word of its name: data/natural/, results/runs/natural-*,
# experiments/prompts/natural/, natural_tasks_index.json, screening_natural_aidev.json) or for a natural task (NP-03).
NATURAL_NAME = re.compile(r"(?:^|[^a-z])natural(?:$|[^a-z])|^np-\d+$")
# The natural arm's records whose name does not say so: the rejection ledger holds the S9 and S10 rows of the natural
# comments and families. The licence record (third_party_downloads.json) is not one of them: it names every natural
# repository by design (its url lines, NATURAL_RECORDS), so a bare name there says nothing that its URLs do not.
NATURAL_ARM_RECORDS = ("data/manifests/rejection_ledger.json",)
NATURAL_RECORDS = {
    "data/manifests/third_party_downloads.json": ("url", ("the record of the repositories fetched for the natural arm "
                                                          "names each by its URL, as the licence record requires (D50)")),
    "data/manifests/screening_natural_aidev.json": ("path", ("the S9 sample records each comment's file path (D48), "
                                                             "whose directories often bear the repository's or owner's name")),
}
# --natural-texts: where a natural task's code lines are not reported: the study's own code and the controlled tasks'
# material, which hold common idioms that upstream code shares (check ids are reported there too). The study's own code
# is its code directories (CODE_EXEMPT), and its code files elsewhere (CODE_FILES: the paper's table and figure scripts,
# the unfinished packages kept as patches). PRE_NATURAL_REV is the frozen revision of scripts/verify_frozen_inputs.py,
# from before any natural task existed (D47): a line that the repository held then is an idiom, not a natural
# repository's code.
CODE_EXEMPT = ("src/", "scripts/", "tests/", "tasks/CS-", "data/controlled/")
CODE_FILES = (("paper/", ".py"), ("docs/wip/", ".patch"))
PRE_NATURAL_REV = "c5ede4c"
# --natural-texts: where, besides the study's own code, a line of a natural task's base snapshot is not reported: the
# controlled arm's outputs (its runs' records and reports, the fresh-agent round's records, the harness validation),
# which show the controlled tasks' code and the study's tools at work, with lines that a natural repository's code
# shares (a library's traceback frame, a call of the same API). A natural run's outputs (results/runs/natural-*) are
# not among them.
CONTROLLED_OUTPUTS = ("results/runs/", "results/harbor_validation/", "data/fresh/")


def _emails(line: str):
    for m in EMAIL.finditer(line):
        addr = m.group(0)
        if m.start() > 0 and line[m.start() - 1] == "\\":
            addr = addr[1:]  # an escape sequence such as "\nalice@..." in JSON text: drop the escape letter
            if not EMAIL.fullmatch(addr):
                continue
        if addr.split("@", 1)[1].lower().startswith("pytest."):
            continue  # a decorator such as "x@pytest.mark.parametrize", not an address
        yield addr


def _code_handle(line: str, m: re.Match, *, decorators: bool, allow: frozenset[str], css: bool = False,
                 assignments: bool = False) -> bool:
    """An @word that is code or a public form, not a handle. ``css``: a CSS at-rule (an HTML or CSS file);
    ``assignments``: a template reference ``NAME=@ref``."""
    from tracecontract.ingest.pseudonymize_pr import in_decorator_position, is_code_at

    at = m.start()
    return (is_code_at(line, at, m.end()) or m.group(0)[1:].lower() in allow
            or (decorators and in_decorator_position(line, at)) or bool(NPM_SCOPE.search(line, 0, at))
            or (css and m.group(0)[1:].lower() in CSS_AT_RULES)
            or (assignments and at >= 2 and line[at - 1] == "=" and (line[at - 2].isalnum() or line[at - 2] == "_")))


def handle_scope(path: str, *, natural: bool = False) -> tuple[bool, frozenset[str]]:
    """Whether @handles are reported in ``path`` (with ``natural``, also under ``NATURAL_HANDLE_SCOPES``), and the code
    words allowed there."""
    scopes = HANDLE_SCOPES + (NATURAL_HANDLE_SCOPES if natural else ())
    return path.startswith(scopes), frozenset(w for (prefix, w) in HANDLE_ALLOW if path.startswith(prefix))


def email_hash(addr: str) -> str:
    """How a finding names an e-mail address under --natural-texts: the start of the sha256 of the address, lower-cased."""
    return hashlib.sha256(addr.lower().encode("utf-8")).hexdigest()[:16]


def scan_text(text: str, where: str, private: list[re.Pattern], logins: list[tuple[str, re.Pattern]] | None = None,
              handles: bool = False, *, decorators: bool = False, allow: frozenset[str] = frozenset(),
              hash_emails: bool = False, css: bool = False, assignments: bool = False) -> int:
    """Report and count the findings in ``text``; ``decorators``: a Python file, whose decorator lines are code.

    ``hash_emails``, ``css`` and ``assignments`` are the refinements of --natural-texts: an e-mail address is named by
    :func:`email_hash`; a CSS at-rule and a template reference ``NAME=@ref`` are code (:func:`_code_handle`)."""
    hits = 0
    logins = logins or []
    for n, line in enumerate(text.splitlines(), 1):
        for name, pat in RULES:
            if pat.search(line):
                print(f"{where}:{n}: {name}")
                hits += 1
        for addr in _emails(line):
            if addr.lower() not in ALLOW and not addr.lower().endswith(ALLOW_DOMAINS) and not _reserved(addr):
                print(f"{where}:{n}: e-mail address " + (f"(sha256 {email_hash(addr)})" if hash_emails else addr))
                hits += 1
        for i, pat in enumerate(private):
            if pat.search(line):
                print(f"{where}:{n}: private marker #{i}")
                hits += 1
        low = line.lower() if logins else ""
        for i, (login, pat) in enumerate(logins):
            if login in low and pat.search(line):
                print(f"{where}:{n}: aidev login #{i}")
                hits += 1
        if handles:
            for m in HANDLE.finditer(line):
                if not _code_handle(line, m, decorators=decorators, allow=allow, css=css, assignments=assignments):
                    print(f"{where}:{n}: @handle")  # the handle itself is not repeated
                    hits += 1
    return hits


def bare_name_scope(path: str) -> bool:
    """Whether a natural repository's name counts as a whole word in ``path``: a path under ``NATURAL_SCOPES`` with a
    directory or file named for the natural arm or for a natural task (``NATURAL_NAME``), or one of the natural arm's
    records whose name does not say so (``NATURAL_ARM_RECORDS``)."""
    return path in NATURAL_ARM_RECORDS or (
        path.startswith(NATURAL_SCOPES) and any(NATURAL_NAME.search(part.lower()) for part in path.split("/")))


def study_code(path: str) -> bool:
    """Whether ``path`` is the study's own code or the controlled tasks' material, where a natural task's code lines are
    not reported (``CODE_EXEMPT``, ``CODE_FILES``)."""
    return path.startswith(CODE_EXEMPT) or any(path.startswith(d) and path.endswith(s) for d, s in CODE_FILES)


def base_code_scope(path: str | None) -> bool:
    """Whether a line of a natural task's base snapshot is reported in ``path`` (None: commit metadata): everywhere but
    the study's own code (:func:`study_code`) and the controlled arm's outputs (``CONTROLLED_OUTPUTS``), a natural
    run's outputs excepted."""
    if path is None:
        return True
    return not study_code(path) and not (path.startswith(CONTROLLED_OUTPUTS) and not bare_name_scope(path))


def sampled_comment_ids(manifests: Sequence[Path] | None = None) -> list[int]:
    """The sampled comment ids that the screening manifests record (default ``SCREENING_MANIFESTS``): the S9 funnel
    manifest's ``sample.rows`` and the extension manifest's ``rows``, in order, each once."""
    out: dict[int, None] = {}
    for m in SCREENING_MANIFESTS if manifests is None else manifests:
        d = json.loads(Path(m).read_text(encoding="utf-8"))
        sample = d.get("sample") if isinstance(d.get("sample"), dict) else {}
        rows = sample["rows"] if "rows" in sample else d["rows"]
        out.update((int(r["comment_id"]), None) for r in rows)
    return list(out)


@functools.lru_cache(maxsize=4)
def pre_natural_lines(rev: str = PRE_NATURAL_REV) -> frozenset[str] | None:
    """The lines of the repository at ``rev`` (:func:`tracecontract.natural_privacy.generic_lines`), read with ``git
    archive`` once per process; None if git cannot read ``rev`` (a clone without that commit)."""
    from tracecontract.natural_privacy import generic_lines

    try:
        tar = subprocess.run(["git", "archive", "--format=tar", rev], cwd=R, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    texts = []
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        for member in tf:
            f = tf.extractfile(member) if member.isfile() else None
            data = f.read() if f is not None else b""
            if data and b"\0" not in data:
                texts.append(data.decode("utf-8", errors="replace"))
    return generic_lines(texts)


def natural_material(tasks_root: str | Path, screening: Iterable[str | Path] = (), *,
                     manifests: Sequence[Path] | None = None, distinctive_base: bool = True) -> NaturalMaterial:
    """The windows, short texts, repositories, code lines and check ids of every task directory under ``tasks_root``
    (relative to the repository or absolute), with those of the screening text files ``screening``; the lines that the
    repository held at ``PRE_NATURAL_REV`` are cut out of the texts and are no code line; ``distinctive_base``: only the
    base snapshots' lines that name something of their own are looked for (the scan's rule). With ``screening``, the files
    must hold every comment id of ``manifests`` (default ``SCREENING_MANIFESTS``). The checks fail closed:
    FileNotFoundError without a task directory or when no directory holds a task; ValueError on a task file or
    screening text file that cannot be read, on a base snapshot that a task records but that is missing or holds no code
    line, and on screening texts that lack a sampled comment; each message names the option."""
    from tracecontract.natural_privacy import MaterialError, NaturalMaterial

    root = Path(tasks_root)
    files = [Path(p) if Path(p).is_absolute() else R / p for p in screening]
    try:
        nm = NaturalMaterial.load(root if root.is_absolute() else R / root, screening=files,
                                  generic=pre_natural_lines() or frozenset(), distinctive_base=distinctive_base)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"--natural-texts: {exc}") from None
    except MaterialError as exc:
        raise ValueError(f"--natural-texts: {exc}") from None
    except ValueError as exc:
        raise ValueError(f"--screening-texts: {exc}") from None
    if files:
        manifests = SCREENING_MANIFESTS if manifests is None else manifests
        missing = [c for c in sampled_comment_ids(manifests) if c not in nm.screened]
        if missing:
            raise ValueError(f"--screening-texts: the texts lack {len(missing)} sampled comment(s) of "
                             f"{', '.join(Path(m).name for m in manifests)}; give the texts of every sample")
    return nm


def _record_line(line: str, key: str) -> bool:
    """``line`` is the JSON member ``"<key>": "<string>"`` alone (a record field of ``NATURAL_RECORDS``)."""
    return re.fullmatch(rf'\s*"{re.escape(key)}"\s*:\s*"(?:[^"\\]|\\.)*"\s*,?\s*', line) is not None


def scan_natural(text: str, where: str, path: str | None, natural: NaturalMaterial) -> int:
    """Report and count the natural material in ``text`` (--natural-texts): windows and short texts of the natural
    texts, the natural repositories' owners and names, and the natural tasks' code lines (of their patches and
    verifiers, and of their base snapshots) and check ids. ``path`` (None for commit metadata) decides whether a bare
    repository name counts (:func:`bare_name_scope`), which lines are records (``NATURAL_RECORDS``, where neither a
    repository's name nor a base snapshot's line is reported) and whether code lines are reported (:func:`study_code`,
    :func:`base_code_scope`). One finding per line and kind (a line of a patch is not reported again as its base
    snapshot's); the window, name, owner or code is not repeated."""
    from tracecontract.natural_privacy import line_number, text_views

    hits = 0
    reported: set[tuple[int, str]] = set()
    lines: list[str] | None = None
    views = text_views(text)

    def report_line(n: int, what: str) -> None:
        nonlocal hits
        if (n, what) not in reported:
            reported.add((n, what))
            print(f"{where}:{n}: {what}")
            hits += 1

    def report(offset: int, what: str) -> None:
        report_line(line_number(text, offset), what)

    windows: dict[tuple[int, str], bool] = {}  # (line, natural text's source) -> whether a window, not a whole text
    for offset, kind, source in natural.windows.find(text, views):
        key = (line_number(text, offset), source)
        windows[key] = windows.get(key, False) or kind != "whole"
    for (n, source), window in sorted(windows.items()):  # one finding per line and source
        report_line(n, f"natural {'text window' if window else 'short text'} ({source})")
    record = NATURAL_RECORDS.get(path or "")
    for offset, kind, repo in natural.repos.find(text, bare=path is not None and bare_name_scope(path)):
        if record is not None:
            lines = text.splitlines() if lines is None else lines
            if _record_line(lines[line_number(text, offset) - 1], record[0]):
                continue
        what = "natural repository owner in a URL" if kind == "owner" else "natural repository name"
        report(offset, f"{what} ({', '.join(repo.task_ids)})")
    for offset, task in natural.check_ids.find(text, views):
        report(offset, f"check id of a natural task ({task})")
    code: set[tuple[int, str]] = set()  # (line, task): a patch's line is often its base snapshot's line too
    if path is None or not study_code(path):
        for offset, task in natural.code.find(text, views):
            code.add((line_number(text, offset), task))
            report(offset, f"code line of a natural task ({task})")
    if base_code_scope(path):
        for offset, task in natural.base_code.find(text, views):
            n = line_number(text, offset)
            if (n, task) in code:
                continue
            if record is not None:  # a record field that names the repository by design (its URL) is no code of it
                lines = text.splitlines() if lines is None else lines
                if _record_line(lines[n - 1], record[0]):
                    continue
            report_line(n, f"code line of a natural task's base snapshot ({task})")
    return hits


def scan_file(where: str, data: bytes, private: list[re.Pattern], logins: list[tuple[str, re.Pattern]],
              natural: NaturalMaterial | None = None, *, aidev: bool = False) -> int:
    """Report and count the findings in one file version at ``where`` (a repository path, or a path and a blob id): its
    path, then its text unless it is binary. ``aidev``: --aidev-logins was given; ``natural``: --natural-texts."""
    path = where.split(" (blob ")[0]
    ext = natural is not None
    hits = scan_text(path, f"{where} [path]", private, logins, hash_emails=ext)
    if natural is not None:
        hits += scan_natural(path, f"{where} [path]", path, natural)
    if b"\0" in data:
        return hits
    in_scope, allow = handle_scope(path, natural=ext)
    added = ext and path.startswith(NATURAL_HANDLE_SCOPES)  # the scopes --natural-texts adds, with their code forms
    text = data.decode("utf-8", errors="replace")
    hits += scan_text(text, where, private, logins, handles=(aidev or ext) and in_scope,
                      decorators=path.endswith((".py", ".pyi")), allow=allow, hash_emails=ext,
                      css=added and path.endswith(CSS_FILES), assignments=added)
    if natural is not None:
        hits += scan_natural(text, where, path, natural)
    return hits


def login_patterns(logins: list[str]) -> list[tuple[str, re.Pattern]]:
    """(lower-case prefilter, whole-word pattern in any case) per login or name; a login inside a longer login or
    identifier does not count, and the words of a name may be separated by any whitespace. The plain substring test
    of the prefilter (the login, or a name's first word) runs first, as it is much faster than the pattern."""
    out = []
    for x in logins:
        words = x.split()
        body = r"\s+".join(map(re.escape, words))
        out.append((words[0].lower(), re.compile(r"(?<![A-Za-z0-9_-])" + body + r"(?![A-Za-z0-9_-])", re.IGNORECASE)))
    return out


def aidev_logins(data_dir: str | Path, manifest: Path = AIDEV_MANIFEST) -> list[str]:
    """Every login and git author name connected to the PRs of the sampled comments (see the module docstring),
    read from the parquet files now and kept in memory only; one spelling per login or name, sorted."""
    import duckdb  # the data extra; needed only with --aidev-logins

    from tracecontract.ingest.pseudonymize_pr import AGENT_HANDLES

    ids = [r["comment_id"] for r in json.loads(manifest.read_text(encoding="utf-8"))["sample"]["rows"]]
    con = duckdb.connect()
    for t in AIDEV_TABLES:
        src = (Path(data_dir) / f"{t}.parquet").as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{src}')")
    bots = {b for (b,) in con.execute("""SELECT DISTINCT lower("user") FROM pr_review_comments
                                         WHERE user_type = 'Bot' AND "user" IS NOT NULL""").fetchall()}
    con.execute("""CREATE TEMP TABLE prs AS SELECT DISTINCT p.id AS pr_id, p."user" AS pr_user, p.repo_url, p.number
        FROM pr_review_comments c JOIN pull_request p ON c.pull_request_url = p.repo_url || '/pulls/' || p.number::VARCHAR
        WHERE c.id IN (SELECT unnest(?::BIGINT[]))""", [ids])
    rows = con.execute("""SELECT x FROM (
            SELECT c."user" AS x FROM pr_review_comments c
                JOIN prs ON c.pull_request_url = prs.repo_url || '/pulls/' || prs.number::VARCHAR
            UNION SELECT pr_user FROM prs
            UNION SELECT i."user" FROM related_issue r JOIN issue i ON i.id = r.issue_id WHERE r.pr_id IN (SELECT pr_id FROM prs)
            UNION SELECT author FROM pr_commits WHERE pr_id IN (SELECT pr_id FROM prs)
            UNION SELECT committer FROM pr_commits WHERE pr_id IN (SELECT pr_id FROM prs)
            UNION SELECT owner FROM (SELECT DISTINCT split_part(repo_url, '/', 5) AS owner FROM prs)
                WHERE lower(owner) IN (SELECT lower("user") FROM pull_request UNION SELECT lower("user") FROM pr_review_comments
                                       UNION SELECT lower("user") FROM issue UNION SELECT lower(author) FROM pr_commits
                                       UNION SELECT lower(committer) FROM pr_commits))
        WHERE x IS NOT NULL AND trim(x) <> ''""").fetchall()
    out: dict[str, str] = {}
    for (x,) in rows:
        key = " ".join(x.split()).lower()
        if key.endswith("[bot]") or key in bots or key.removesuffix("[bot]") in AGENT_HANDLES or key == "web-flow":
            continue
        out.setdefault(key, " ".join(x.split()))
    return sorted(out.values(), key=str.lower)


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=R, capture_output=True, check=True).stdout


def working_tree() -> list[tuple[str, bytes]]:
    out = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    files = []
    for p in out.decode().split("\0"):
        f = R / p
        if p and f.is_file():
            files.append((p, f.read_bytes()))
    return files


def pushed_blobs(all_history: bool) -> list[tuple[str, bytes]]:
    rng = _push_range(all_history)
    seen, out = set(), []
    for line in _git("rev-list", "--objects", *rng).decode().splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2 or parts[0] in seen:
            continue
        sha, path = parts
        if _git("cat-file", "-t", sha).strip() != b"blob":
            continue
        seen.add(sha)
        out.append((f"{path} (blob {sha[:10]})", _git("cat-file", "blob", sha)))
    return out


def _push_range(all_history: bool) -> list[str]:
    if all_history:
        return ["--all"]
    up = subprocess.run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=R,
                        capture_output=True, text=True, check=False)
    return [f"{up.stdout.strip()}..HEAD"] if up.returncode == 0 and up.stdout.strip() else ["HEAD"]


def pushed_metadata(all_history: bool) -> list[tuple[str, str]]:
    """Commit messages and author/committer fields of the pushed commits, tag names and messages, the branch name."""
    out = []
    log = _git("log", "--format=%H%x00%an <%ae>%n%cn <%ce>%n%B%x01", *_push_range(all_history)).decode("utf-8", errors="replace")
    for rec in log.split("\x01"):
        if "\x00" in rec:
            sha, text = rec.strip().split("\x00", 1)
            out.append((f"commit {sha[:10]} [message and author fields]", text))
    tags = _git("for-each-ref", "--format=%(refname)%0a%(contents)", "refs/tags").decode("utf-8", errors="replace")
    if tags.strip():
        out.append(("tags [names and messages]", tags))
    out.append(("current branch [name]", _git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()))
    return out


def load_private(path: str | Path) -> list[re.Pattern]:
    """The private markers of ``--private-markers`` (``{"forbidden": [regex, ...]}``), case-insensitive."""
    return [re.compile(x, re.IGNORECASE) for x in json.loads(Path(path).read_text(encoding="utf-8")).get("forbidden", [])]


def _option(args: tuple[str, ...], name: str) -> str:
    i = args.index(name)
    if i + 1 >= len(args) or args[i + 1].startswith("--"):
        raise SystemExit(f"scan_tracked_files: {name} needs a value")
    return args[i + 1]


def _options(args: tuple[str, ...], name: str) -> list[str]:
    """The values of every occurrence of a repeatable option."""
    out = []
    for i, a in enumerate(args):
        if a == name:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit(f"scan_tracked_files: {name} needs a value")
            out.append(args[i + 1])
    return out


def scan_repository(private: list[re.Pattern], logins: list[tuple[str, re.Pattern]], natural: NaturalMaterial | None,
                    *, aidev: bool, all_history: bool) -> int:
    """Report and count the findings in the working tree, the file versions a push would send (the whole history with
    ``all_history``) and the push metadata (see the module docstring)."""
    hits = 0
    for where, data in working_tree() + pushed_blobs(all_history):
        hits += scan_file(where, data, private, logins, natural, aidev=aidev)
    for where, text in pushed_metadata(all_history):
        hits += scan_text(text, where, private, logins, hash_emails=natural is not None)
        if natural is not None:
            hits += scan_natural(text, where, None, natural)
    return hits


def natural_summary(natural: NaturalMaterial) -> str:
    """What the natural checks read, for the scan's last line."""
    w = natural.windows
    return (f"natural texts of {len(natural.task_ids)} task(s) and {len(natural.screened)} screened comment(s) "
            f"({w.n_texts} text(s), {w.n_char_windows} character and {w.n_word_windows} word window(s), {w.n_whole} short "
            f"text(s) matched whole), {len(natural.repos.repos)} natural repositories, {natural.code.n_needles} code "
            f"line(s) of patches and verifiers, {natural.base_code.n_needles} code line(s) of "
            f"{len(natural.base_snapshots)} base snapshot(s) and {natural.check_ids.n_needles} check id(s)"
            + (f" ({len(natural.binary)} binary file(s) not read as code)" if natural.binary else "")
            + ("" if natural.screened else " (no screening texts given: the sampled comments that no natural task holds "
                                           "were not checked)"))


def main(*args: str) -> int:
    private: list[re.Pattern] = []
    if "--private-markers" in args:
        private = load_private(_option(args, "--private-markers"))
    screening = _options(args, "--screening-texts")
    if screening and "--natural-texts" not in args:
        raise SystemExit("scan_tracked_files: --screening-texts needs --natural-texts")
    aidev = "--aidev-logins" in args
    logins = login_patterns(aidev_logins(_option(args, "--aidev-logins"))) if aidev else []
    natural = None
    if "--natural-texts" in args:
        try:
            natural = natural_material(_option(args, "--natural-texts"), screening)
        except (FileNotFoundError, ValueError) as exc:  # fail closed: nothing is scanned against less than the tasks hold
            raise SystemExit(f"scan_tracked_files: {exc}") from None
    hits = scan_repository(private, logins, natural, aidev=aidev, all_history="--all-history" in args)
    scope = "the working tree and " + ("the whole history" if "--all-history" in args else "the commits a push would send") \
        + " (contents, paths, commit messages and author fields, tags)"
    extra = (f"; {len(logins)} AIDev login(s) and name(s) connected to the sampled PRs, @handles in "
             f"{' and '.join(HANDLE_SCOPES)}") if aidev and natural is None else ""
    if aidev and natural is not None:
        extra = f"; {len(logins)} AIDev login(s) and name(s) connected to the sampled PRs"
    if natural is not None:
        extra += f"; {natural_summary(natural)}, @handles in {', '.join(HANDLE_SCOPES + NATURAL_HANDLE_SCOPES)}"
    print(f"scan: {hits} finding(s) in {scope}" + ("" if private else " (no private markers given)") + extra)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
