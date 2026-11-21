"""Scan what a push would publish for credentials, session-local paths and e-mail addresses.

Usage: python scripts/scan_tracked_files.py [--private-markers <file.json>] [--all-history] [--aidev-logins <dir>]

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
in a registry URL, and the code words of ``HANDLE_ALLOW`` in the files it names.

This is a manual step, not a git hook: the builder runs it with the private markers
before each push (decision log D44).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

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
# --aidev-logins: the screening manifest with the sampled comment ids, the files whose @handles are
# reported, and the public forms of @name allowed there (code; an npm package scope in a registry URL).
AIDEV_MANIFEST = R / "data" / "manifests" / "screening_natural_aidev.json"
AIDEV_TABLES = ("pull_request", "pr_review_comments", "pr_commits", "related_issue", "issue")
HANDLE_SCOPES = ("tasks/", "data/")
HANDLE = re.compile(r"(?<![A-Za-z0-9._%+-])@[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}(?:\[bot\])?")
NPM_SCOPE = re.compile(r"(?:registry\.npmjs\.org|npmjs\.com/package)/$")
# Code words written as @word that no general rule recognises: (path prefix, word) -> why it may stay.
HANDLE_ALLOW = {
    ("tasks/CS-04/", "consumer"): "the more_itertools.consumer decorator, named in a comment of the upstream tests/test_more.py",
}


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


def _code_handle(line: str, m: re.Match, *, decorators: bool, allow: frozenset[str]) -> bool:
    """An @word that is code or a public form, not a handle."""
    from tracecontract.ingest.pseudonymize_pr import in_decorator_position, is_code_at

    return (is_code_at(line, m.start(), m.end()) or m.group(0)[1:].lower() in allow
            or (decorators and in_decorator_position(line, m.start())) or bool(NPM_SCOPE.search(line, 0, m.start())))


def handle_scope(path: str) -> tuple[bool, frozenset[str]]:
    """Whether @handles are reported in ``path``, and the code words allowed there."""
    return path.startswith(HANDLE_SCOPES), frozenset(w for (prefix, w) in HANDLE_ALLOW if path.startswith(prefix))


def scan_text(text: str, where: str, private: list[re.Pattern], logins: list[tuple[str, re.Pattern]] | None = None,
              handles: bool = False, *, decorators: bool = False, allow: frozenset[str] = frozenset()) -> int:
    """Report and count the findings in ``text``; ``decorators``: a Python file, whose decorator lines are code."""
    hits = 0
    logins = logins or []
    for n, line in enumerate(text.splitlines(), 1):
        for name, pat in RULES:
            if pat.search(line):
                print(f"{where}:{n}: {name}")
                hits += 1
        for addr in _emails(line):
            if addr.lower() not in ALLOW and not addr.lower().endswith(ALLOW_DOMAINS) and not _reserved(addr):
                print(f"{where}:{n}: e-mail address {addr}")
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
                if not _code_handle(line, m, decorators=decorators, allow=allow):
                    print(f"{where}:{n}: @handle")  # the handle itself is not repeated
                    hits += 1
    return hits


def login_patterns(logins: list[str]) -> list[tuple[str, re.Pattern]]:
    """(lower-case prefilter, whole-word pattern in any case) per login or name; a login inside a longer login or
    identifier does not count, and the words of a name may be separated by any whitespace. The plain substring test
    of the prefilter (the login, or a name's first word) runs first, as it is much faster than the pattern."""
    out = []
    for x in logins:
        words = x.split()
        body = r"\s+".join(map(re.escape, words))
        out.append((words[0].lower(), re.compile(r"(?<![A-Za-z0-9_-])" + body + r"(?![A-Za-z0-9_-])", re.I)))
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
                        capture_output=True, text=True)
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


def main(*args: str) -> int:
    private: list[re.Pattern] = []
    if "--private-markers" in args:
        f = args[args.index("--private-markers") + 1]
        private = [re.compile(x, re.I) for x in json.loads(Path(f).read_text(encoding="utf-8")).get("forbidden", [])]
    aidev = "--aidev-logins" in args
    logins = login_patterns(aidev_logins(args[args.index("--aidev-logins") + 1])) if aidev else []
    hits = 0
    files = working_tree() + pushed_blobs("--all-history" in args)
    for where, data in files:
        path = where.split(" (blob ")[0]
        hits += scan_text(path, f"{where} [path]", private, logins)
        if b"\0" in data:
            continue
        in_scope, allow = handle_scope(path)
        hits += scan_text(data.decode("utf-8", errors="replace"), where, private, logins, handles=aidev and in_scope,
                          decorators=path.endswith((".py", ".pyi")), allow=allow)
    for where, text in pushed_metadata("--all-history" in args):
        hits += scan_text(text, where, private, logins)
    scope = "the working tree and " + ("the whole history" if "--all-history" in args else "the commits a push would send") \
        + " (contents, paths, commit messages and author fields, tags)"
    extra = (f"; {len(logins)} AIDev login(s) and name(s) connected to the sampled PRs, @handles in "
             f"{' and '.join(HANDLE_SCOPES)}") if aidev else ""
    print(f"scan: {hits} finding(s) in {scope}" + ("" if private else " (no private markers given)") + extra)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
