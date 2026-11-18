"""Scan every file git would publish for credentials, session-local paths and e-mail addresses.

Usage: python scripts/scan_tracked_files.py [--private-markers <file.json>]

Scans tracked files plus untracked files that are not git-ignored (what the next
commit could add). Generic rules: credential formats, private-key headers, the
session-local paths of the build environment, and e-mail addresses not on the
allowlist below. ``--private-markers`` adds case-insensitive regexes from a JSON file
kept outside the repository (``{"forbidden": [...]}``, the format of the prompt
export's private redactions); their matches are reported by file, line and marker
number only, so the scan output repeats nothing private. Exit code 1 if anything is
found. Run before every push (decision log D40).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]

EMAIL = re.compile(r"[A-Za-z0-9._%+-]*[A-Za-z0-9]@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,6}\b")
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
    "markus@m-siemens.de": "upstream copyright notice in THIRD_PARTY_LICENSES/tinydb.txt (the MIT licence requires it)",
    "jane.doe@example.com": "synthetic address in a redaction test",
    "git@github.com": "SSH host name in a repository URL",
}


def files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=R,
                         capture_output=True, check=True).stdout
    return [R / p for p in out.decode().split("\0") if p]


def main(*args: str) -> int:
    private: list[re.Pattern] = []
    if args[:1] == ("--private-markers",):
        private = [re.compile(f, re.I) for f in json.loads(Path(args[1]).read_text(encoding="utf-8")).get("forbidden", [])]
    hits = 0
    for f in files():
        if not f.is_file():
            continue
        data = f.read_bytes()
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        rel = f.relative_to(R)
        for n, line in enumerate(text.splitlines(), 1):
            for name, pat in RULES:
                if pat.search(line):
                    print(f"{rel}:{n}: {name}")
                    hits += 1
            for m in EMAIL.finditer(line):
                if m.start() > 0 and line[m.start() - 1] == "\\":
                    continue  # an escape sequence such as "\n@pytest.mark..." in JSON text
                if m.group(0).lower() not in ALLOW:
                    print(f"{rel}:{n}: e-mail address {m.group(0)}")
                    hits += 1
            for i, pat in enumerate(private):
                if pat.search(line):
                    print(f"{rel}:{n}: private marker #{i}")
                    hits += 1
    print(f"scan: {hits} finding(s) in files git would publish" + ("" if private else " (no private markers given)"))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
