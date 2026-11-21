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
build environment, and e-mail addresses not on the allowlist below. ``--private-markers``
adds case-insensitive regexes from a JSON file kept outside the repository
(``{"forbidden": [...]}``, the format of the prompt export's private redactions, which
also lists the build session id); their matches are reported by location and marker
number only, so the output repeats nothing private. Exit code 1 if anything is found.

``--aidev-logins <dir>`` adds the checks of the natural PR-review screening (decision log
D47). It reads the comment ids of the stage-S9 sample from
``data/manifests/screening_natural_aidev.json`` and loads their comment authors' logins
from ``<dir>/pr_review_comments.parquet`` at scan time, in memory only (needs DuckDB, the
``data`` extra; run the scan with ``python -I`` then, as the parquet files are third-party
data). Any of these logins, as a whole word in any case, is reported by location and login
number only. It also reports @handle patterns in files under ``data/manifests/``, except an
npm package scope in a registry URL.

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
# --aidev-logins: the screening manifest with the sampled comment ids, the files whose @handles are
# reported, and the one public form of @name allowed there (an npm package scope in a registry URL).
AIDEV_MANIFEST = R / "data" / "manifests" / "screening_natural_aidev.json"
HANDLE_SCOPE = "data/manifests/"
HANDLE = re.compile(r"(?<![A-Za-z0-9._%+-])@[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}(?:\[bot\])?")
NPM_SCOPE = re.compile(r"(?:registry\.npmjs\.org|npmjs\.com/package)/$")


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


def scan_text(text: str, where: str, private: list[re.Pattern], logins: list[tuple[str, re.Pattern]] | None = None,
              handles: bool = False) -> int:
    hits = 0
    logins = logins or []
    for n, line in enumerate(text.splitlines(), 1):
        for name, pat in RULES:
            if pat.search(line):
                print(f"{where}:{n}: {name}")
                hits += 1
        for addr in _emails(line):
            if addr.lower() not in ALLOW and not addr.lower().endswith(ALLOW_DOMAINS):
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
                if not NPM_SCOPE.search(line, 0, m.start()):
                    print(f"{where}:{n}: @handle")  # the handle itself is not repeated
                    hits += 1
    return hits


def login_patterns(logins: list[str]) -> list[tuple[str, re.Pattern]]:
    """(lower-case login, whole-word pattern in any case) per login; a login inside a longer login or identifier
    does not count. The plain substring test runs first, as it is much faster than the pattern."""
    return [(x.lower(), re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(x) + r"(?![A-Za-z0-9_-])", re.I)) for x in logins]


def aidev_logins(data_dir: str | Path, manifest: Path = AIDEV_MANIFEST) -> list[str]:
    """Comment-author logins of the sampled comments, read from the parquet file now and kept in memory only."""
    import duckdb  # the data extra; needed only with --aidev-logins

    ids = [r["comment_id"] for r in json.loads(manifest.read_text(encoding="utf-8"))["sample"]["rows"]]
    src = (Path(data_dir) / "pr_review_comments.parquet").as_posix().replace("'", "''")
    rows = duckdb.connect().execute(f"""SELECT DISTINCT "user" FROM read_parquet('{src}')
        WHERE id IN (SELECT unnest(?::BIGINT[])) AND "user" IS NOT NULL""", [ids]).fetchall()
    return sorted(u for (u,) in rows)


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
        hits += scan_text(data.decode("utf-8", errors="replace"), where, private, logins,
                          handles=aidev and path.startswith(HANDLE_SCOPE))
    for where, text in pushed_metadata("--all-history" in args):
        hits += scan_text(text, where, private, logins)
    scope = "the working tree and " + ("the whole history" if "--all-history" in args else "the commits a push would send") \
        + " (contents, paths, commit messages and author fields, tags)"
    extra = f"; {len(logins)} sampled AIDev comment-author login(s), @handles in {HANDLE_SCOPE}" if aidev else ""
    print(f"scan: {hits} finding(s) in {scope}" + ("" if private else " (no private markers given)") + extra)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
