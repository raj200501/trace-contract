"""A synthetic natural PR-review world for tests/test_github_pr_ingest.py and tests/test_compile_pr_task.py.

Tiny git repositories made in a temporary directory, each cloned bare under ``repos/<repo id>.git`` (as the S9
fetches laid them out), fake AIDev v5 tables written as parquet files with DuckDB, and an ``s9_qualifying.json``
in the S9 record's shape. Every login is fictional (``fx-...``); e-mail addresses and model identifiers are built
at run time from parts, so that no tracked file holds one. Not research evidence.

PRs (NP numbers follow the order of the S11 families, then the reserves):

* NP-01, repository 101 (owner ``fx-owner``, who acts as an account): the clean case. Commits: a first commit, the
  reviewed commit, the addressing commit (which also adds a binary file) and a later head commit. The reviewer has
  one reply before the addressing commit and one after; another participant replies too.
* NP-02, repository 101: the default branch is merged into the PR, and the merge changes the commented file.
* NP-03, repository 102 (an organisation): a merge of the default branch that does not touch the commented file.
* NP-04, repository 103: a GPL licence. NP-05, repository 104: no LICENSE file.
* NP-06, repository 105: a monorepo; the commented package lives in ``packages/fxsub``.
* NP-07, repository 107: no test at all (the base-test subset is empty).
* NP-08, repository 101: a reserve (the next PR of repository 101).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

AT = "@"
MAIL_REV = "fx-rev-1" + AT + "example.org"
MAIL_ISSUE = "fx.issuer" + AT + "mail.example.net"
NOREPLY = "12345+fx-issuer" + AT + "users.noreply.github.com"
MODEL_ID = "g" + "pt-9z-turbo"
MIT = ("MIT License\n\nCopyright (c) 2025 the fixture authors\n\nPermission is hereby granted, free of charge, to any person "
       "obtaining a copy of this software and associated documentation files, to deal in the Software without restriction.\n")
GPL = "                    GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007\n\n Copyright (C) 2007\n"
LOGINS = ("fx-rev-1", "fx-author", "fx-issuer", "fx-x", "fx-stranger", "fx-owner", "fx-lint")
NAMES = ("Fx Person Name", "Fx Other Person")


def _env(home: Path, when: str, who: tuple[str, str] = ("Fx Person Name", "fx.person" + AT + "example.org")) -> dict[str, str]:
    return {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "HOME": str(home), "PATH": os.environ["PATH"],
            "GIT_AUTHOR_NAME": who[0], "GIT_AUTHOR_EMAIL": who[1], "GIT_COMMITTER_NAME": who[0], "GIT_COMMITTER_EMAIL": who[1],
            "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}


AGENT = ("copilot-swe-agent[bot]", "198982749+Copilot" + AT + "users.noreply.github.com")


class Repo:
    """A working repository with helpers to commit files and merges at given times."""

    def __init__(self, path: Path, home: Path) -> None:
        self.path, self.home = path, home
        path.mkdir(parents=True)
        self.git("init", "-q", "-b", "main", when="2025-01-01T00:00:00+00:00")

    def git(self, *args: str, when: str = "2025-01-01T00:00:00+00:00", who: tuple[str, str] | None = None) -> str:
        env = _env(self.home, when, who) if who else _env(self.home, when)
        return subprocess.run(["git", *args], cwd=self.path, env=env, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, files: dict[str, str | bytes | None], msg: str, when: str, who: tuple[str, str] | None = None) -> str:
        for rel, content in files.items():
            p = self.path / rel
            if content is None:
                p.unlink()
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content if isinstance(content, bytes) else content.encode())
        self.git("add", "-A", when=when)
        self.git("commit", "-q", "--allow-empty", "-m", msg, when=when, who=who)
        return self.git("rev-parse", "HEAD")

    def branch(self, name: str, at: str) -> None:
        self.git("checkout", "-q", "-b", name, at)

    def checkout(self, name: str) -> None:
        self.git("checkout", "-q", name)

    def merge(self, other: str, msg: str, when: str) -> str:
        self.git("merge", "-q", "--no-ff", "-m", msg, other, when=when, who=AGENT)
        return self.git("rev-parse", "HEAD")


MOD = "def add(a, b):\n    {add}\n\n\ndef neg(a):\n    {neg}\n"
BASE_FILES = {
    "pyproject.toml": "[project]\nname = \"fxpkg\"\nversion = \"0.1\"\ndependencies = [\"fx-requests>=2\"]\n\n"
                      "[project.optional-dependencies]\ntest = [\"pytest>=7\"]\ndocs = [\"fx-sphinx\"]\n",
    "fxpkg/__init__.py": "from .mod import add\n",
    "fxpkg/mod.py": MOD.format(add="return a + b", neg="return -a"),
    "fxpkg/other.py": "def unrelated():\n    return 1\n",
    "tests/test_mod.py": "from fxpkg.mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    "tests/test_other.py": "from fxpkg import other\n\n\ndef test_other():\n    assert other.unrelated() == 1\n",
}

HUNK = "@@ -1,2 +1,3 @@\n def add(a, b):\n-    return a + b\n+    # fx-author was here\n+    return abs(a) + b\n"


@dataclass
class PRSpec:
    pr_id: int
    number: int
    repo_id: int
    path: str
    commits: list[str]  # PR commits in order (AIDev file order)
    reviewed: str
    addressing: str
    head: str
    issue_id: int
    s11: bool = True
    rank: int = 1
    replies: list[dict] = field(default_factory=list)


@dataclass
class World:
    root: Path
    aidev: Path
    repos: Path
    qualifying: Path
    out: Path
    specs: dict[str, PRSpec]
    shas: dict[str, str]


def _repo_url(full: str) -> str:
    return "https://github.com/" + full


def build_world(tmp: Path) -> World:
    home = tmp / "home"
    home.mkdir()
    repos = tmp / "ext" / "repos"
    repos.mkdir(parents=True)
    shas: dict[str, str] = {}
    specs: dict[str, PRSpec] = {}
    full_names = {101: "fx-owner/fx-owner-tools", 102: "fx-org/lib", 103: "fx-org/gpl", 104: "fx-org/nolicence",
                  105: "fx-org/mono", 107: "fx-org/notests"}

    # Repository 101: NP-01, NP-02 (merge touches the commented file), NP-08 (reserve).
    r = Repo(tmp / "src" / "101", home)
    base = r.commit({**BASE_FILES, "LICENSE": MIT}, "base", "2025-02-01T10:00:00+00:00")
    r.branch("pr1", base)
    a1 = r.commit({"fxpkg/mod.py": MOD.format(add="return a + b", neg="return -a") + "\n\ndef sub(a, b):\n    return a - b\n"},
                  f"Initial plan\n\nCo-authored-by: fx-issuer <{NOREPLY}>", "2025-02-02T10:00:00+00:00",
                  who=("Fx Person Name", "fx.person" + AT + "example.org"))
    a2 = r.commit({"fxpkg/mod.py": MOD.format(add="return abs(a) + b", neg="return -a") + "\n\ndef sub(a, b):\n    return a - b\n"},
                  "Make add tolerant", "2025-02-02T11:00:00+00:00", who=AGENT)
    a3 = r.commit({"fxpkg/mod.py": MOD.format(add="return a + b", neg="return -a") + "\n\ndef sub(a, b):\n    return a - b\n",
                   "tests/test_mod.py": BASE_FILES["tests/test_mod.py"] + "\n\ndef test_negative():\n    assert add(-1, 2) == 1\n",
                   "data/logo.bin": bytes(range(256)) * 4},
                  f"Address review: keep the sign\n\nCo-authored-by: fx-issuer <{NOREPLY}>", "2025-02-03T12:00:00+00:00", who=AGENT)
    a4 = r.commit({"README.md": "fxpkg\n"}, "Add a readme", "2025-02-04T09:00:00+00:00", who=AGENT)
    r.checkout("main")
    m1 = r.commit({"fxpkg/mod.py": MOD.format(add="return a + b", neg="return 0 - a")}, "Simplify neg", "2025-02-05T09:00:00+00:00")
    r.branch("pr3", base)
    c1 = r.commit({"fxpkg/mod.py": MOD.format(add="return b + a", neg="return -a")}, "Swap operands", "2025-02-05T10:00:00+00:00",
                  who=AGENT)
    cm = r.merge("main", "Merge branch 'main' into pr3", "2025-02-05T11:00:00+00:00")
    c2 = r.commit({"fxpkg/mod.py": MOD.format(add="return a + b + 0", neg="return 0 - a")}, "Address review",
                  "2025-02-05T12:00:00+00:00", who=AGENT)
    r.checkout("main")
    r.branch("pr4", m1)
    d1 = r.commit({"fxpkg/other.py": "def unrelated():\n    return 2\n"}, "Change other", "2025-02-06T10:00:00+00:00", who=AGENT)
    d2 = r.commit({"fxpkg/other.py": "def unrelated():\n    return 4\n"}, "Address review", "2025-02-06T11:00:00+00:00", who=AGENT)
    for name, sha in (("pr1", a4), ("pr3", c2), ("pr4", d2)):
        r.git("update-ref", f"refs/pull/{name[2:]}/head", sha)
    r.checkout("main")
    shas.update(base101=base, a1=a1, a2=a2, a3=a3, a4=a4, m1=m1, c1=c1, cm=cm, c2=c2, d1=d1, d2=d2)
    specs["NP-01"] = PRSpec(9001, 1, 101, "fxpkg/mod.py", [a1, a2, a3, a4], a2, a3, a4, 7001, rank=1,
                            replies=[{"id": 8102, "user": "fx-rev-1", "at": "2025-02-02T20:00:00Z",
                                      "body": "Also zero, thanks fx-x; ping @fx-author"},
                                     {"id": 8103, "user": "fx-x", "at": "2025-02-02T21:00:00Z", "body": "agreed"},
                                     {"id": 8104, "user": "fx-rev-1", "at": "2025-02-05T00:00:00Z", "body": "late reply"}])
    specs["NP-02"] = PRSpec(9003, 3, 101, "fxpkg/mod.py", [c1, cm, c2], c1, c2, c2, 7003, rank=2)
    specs["NP-08"] = PRSpec(9004, 4, 101, "fxpkg/other.py", [d1, d2], d1, d2, d2, 7004, s11=False, rank=3)

    # Repository 102: NP-03, a merge of the default branch that does not touch the commented file.
    r = Repo(tmp / "src" / "102", home)
    base = r.commit({**BASE_FILES, "LICENSE": MIT}, "base", "2025-03-01T10:00:00+00:00")
    r.branch("pr2", base)
    b1 = r.commit({"fxpkg/other.py": "def unrelated():\n    return 3\n"}, "Change other", "2025-03-02T10:00:00+00:00", who=AGENT)
    r.checkout("main")
    r.commit({"fxpkg/mod.py": MOD.format(add="return a + b", neg="return 0 - a")}, "Main changes mod", "2025-03-02T11:00:00+00:00")
    r.checkout("pr2")
    bm = r.merge("main", "Merge branch 'main' into pr2", "2025-03-02T12:00:00+00:00")
    b2 = r.commit({"fxpkg/other.py": "def unrelated():\n    return 1\n"}, "Address review", "2025-03-02T13:00:00+00:00", who=AGENT)
    r.git("update-ref", "refs/pull/2/head", b2)
    r.checkout("main")
    shas.update(base102=base, b1=b1, bm=bm, b2=b2)
    specs["NP-03"] = PRSpec(9002, 2, 102, "fxpkg/other.py", [b1, bm, b2], b1, b2, b2, 7002)

    # Repositories 103 (GPL), 104 (no LICENSE), 107 (no tests): one PR each.
    for rid, extra, drop, pid, num in ((103, {"LICENSE": GPL}, (), 9005, 5), (104, {}, (), 9006, 6),
                                       (107, {"LICENSE": MIT}, ("tests/test_mod.py", "tests/test_other.py"), 9007, 7)):
        r = Repo(tmp / "src" / str(rid), home)
        files = {k: v for k, v in {**BASE_FILES, **extra}.items() if k not in drop}
        base = r.commit(files, "base", "2025-04-01T10:00:00+00:00")
        r.branch("pr", base)
        x1 = r.commit({"fxpkg/mod.py": MOD.format(add="return abs(a) + b", neg="return -a")}, "Change add",
                      "2025-04-02T10:00:00+00:00", who=AGENT)
        x2 = r.commit({"fxpkg/mod.py": MOD.format(add="return a + b + 0", neg="return -a")}, "Address review",
                      "2025-04-02T11:00:00+00:00", who=AGENT)
        r.git("update-ref", f"refs/pull/{num}/head", x2)
        r.checkout("main")
        shas.update({f"base{rid}": base, f"x1_{rid}": x1, f"x2_{rid}": x2})
        specs[{103: "NP-04", 104: "NP-05", 107: "NP-07"}[rid]] = PRSpec(pid, num, rid, "fxpkg/mod.py", [x1, x2], x1, x2, x2, 7000 + num)

    # Repository 105: a monorepo with the package in packages/fxsub.
    r = Repo(tmp / "src" / "105", home)
    mono = {"LICENSE": MIT, "README.md": "mono\n", "tools/build.py": "print('x')\n",
            **{f"packages/fxsub/{k}": v for k, v in BASE_FILES.items()}}
    base = r.commit(mono, "base", "2025-05-01T10:00:00+00:00")
    r.branch("pr", base)
    g1 = r.commit({"packages/fxsub/fxpkg/mod.py": MOD.format(add="return abs(a) + b", neg="return -a"), "CHANGELOG.md": "x\n"},
                  "Change add", "2025-05-02T10:00:00+00:00", who=AGENT)
    g2 = r.commit({"packages/fxsub/fxpkg/mod.py": MOD.format(add="return a + b + 0", neg="return -a")}, "Address review",
                  "2025-05-02T11:00:00+00:00", who=AGENT)
    r.git("update-ref", "refs/pull/8/head", g2)
    r.checkout("main")
    shas.update(base105=base, g1=g1, g2=g2)
    specs["NP-06"] = PRSpec(9008, 8, 105, "packages/fxsub/fxpkg/mod.py", [g1, g2], g1, g2, g2, 7008)

    for rid in (101, 102, 103, 104, 105, 107):
        subprocess.run(["git", "clone", "-q", "--bare", str(tmp / "src" / str(rid)), str(repos / f"{rid}.git")], check=True,
                       capture_output=True, env=_env(home, "2025-01-01T00:00:00+00:00"))
        subprocess.run(["git", "-C", str(repos / f"{rid}.git"), "fetch", "-q", "origin", "+refs/pull/*:refs/pull/*"], check=True,
                       capture_output=True, env=_env(home, "2025-01-01T00:00:00+00:00"))

    aidev = tmp / "ext" / "aidev"
    _write_aidev(aidev, specs, full_names)
    qualifying = tmp / "ext" / "work" / "s9_qualifying.json"
    _write_qualifying(qualifying, specs, full_names, repos)
    return World(root=tmp, aidev=aidev, repos=repos, qualifying=qualifying, out=tmp / "data" / "natural" / "tasks",
                 specs=specs, shas=shas)


ORDER = ("NP-01", "NP-02", "NP-03", "NP-04", "NP-05", "NP-06", "NP-07", "NP-08")


def _write_aidev(d: Path, specs: dict[str, PRSpec], full_names: dict[int, str]) -> None:
    import duckdb

    d.mkdir(parents=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE repository (id BIGINT, url VARCHAR, license VARCHAR, full_name VARCHAR, is_forked BOOLEAN, "
                "language VARCHAR, forks BIGINT, stars BIGINT)")
    con.execute("CREATE TABLE pull_request (id BIGINT, number BIGINT, title VARCHAR, body VARCHAR, agent VARCHAR, user_id BIGINT, "
                "\"user\" VARCHAR, state VARCHAR, created_at VARCHAR, closed_at VARCHAR, merged_at VARCHAR, repo_id BIGINT, "
                "repo_url VARCHAR, html_url VARCHAR)")
    con.execute("CREATE TABLE pr_review_comments (id BIGINT, pull_request_review_id BIGINT, \"user\" VARCHAR, user_type VARCHAR, "
                "diff_hunk VARCHAR, path VARCHAR, position BIGINT, original_position BIGINT, commit_id VARCHAR, "
                "original_commit_id VARCHAR, body VARCHAR, pull_request_url VARCHAR, created_at VARCHAR, updated_at VARCHAR, "
                "in_reply_to_id DOUBLE)")
    con.execute("CREATE TABLE pr_commits (sha VARCHAR, pr_id BIGINT, author VARCHAR, committer VARCHAR, message VARCHAR)")
    con.execute("CREATE TABLE related_issue (pr_id BIGINT, issue_id BIGINT, source VARCHAR)")
    con.execute("CREATE TABLE issue (id BIGINT, number BIGINT, title VARCHAR, body VARCHAR, \"user\" VARCHAR, state VARCHAR, "
                "created_at VARCHAR, closed_at VARCHAR, html_url VARCHAR)")
    for rid, full in full_names.items():
        lic = {103: "GPL-3.0", 104: "MIT"}.get(rid, "MIT")
        con.execute("INSERT INTO repository VALUES (?, ?, ?, ?, false, 'Python', 1, 1)",
                    [rid, f"https://api.github.com/repos/{full}", lic, full])
    for tid in ORDER:
        s = specs[tid]
        full = full_names[s.repo_id]
        api = f"https://api.github.com/repos/{full}"
        con.execute("INSERT INTO pull_request VALUES (?, ?, ?, ?, 'Copilot', 1, 'Copilot', 'closed', ?, NULL, NULL, ?, ?, ?)",
                    [s.pr_id, s.number, f"Fix add for {tid}", f"Fixes #{s.number}. Requested by @fx-issuer, mail {MAIL_ISSUE}",
                     "2025-02-02T09:00:00Z", s.repo_id, api, f"https://github.com/{full}/pull/{s.number}"])
        cid = 8000 + s.number
        url = f"{api}/pulls/{s.number}"
        con.execute("INSERT INTO pr_review_comments VALUES (?, 1, 'fx-rev-1', 'User', ?, ?, 1, 2, ?, ?, ?, ?, ?, ?, NULL)",
                    [cid, HUNK, s.path, s.head, s.reviewed,
                     f"@fx-author this breaks negatives; see https://github.com/fx-stranger/tools/issues/3, mail {MAIL_REV}, "
                     f"and {MODEL_ID} agreed." + (" Fx  Person Name said so too." if tid == "NP-01" else ""), url,
                     "2025-02-02T12:00:00Z", "2025-02-02T12:00:00Z"])
        con.execute("INSERT INTO pr_review_comments VALUES (?, 2, 'fx-lint[bot]', 'Bot', ?, ?, 1, 2, ?, ?, 'lint ok', ?, ?, ?, NULL)",
                    [cid + 500, HUNK, s.path, s.head, s.reviewed, url, "2025-02-02T12:30:00Z", "2025-02-02T12:30:00Z"])
        for rep in s.replies:
            con.execute("INSERT INTO pr_review_comments VALUES (?, 3, ?, 'User', ?, ?, 1, 2, ?, ?, ?, ?, ?, ?, ?)",
                        [rep["id"], rep["user"], HUNK, s.path, s.head, s.reviewed, rep["body"], url, rep["at"], rep["at"], float(cid)])
        for sha in s.commits:
            msg = subprocess.run(["git", "log", "-1", "--format=%B", sha], cwd=d.parent / "repos" / f"{s.repo_id}.git",
                                 capture_output=True, text=True, check=True).stdout.strip()
            con.execute("INSERT INTO pr_commits VALUES (?, ?, 'Copilot', 'fx-author', ?)", [sha, s.pr_id, msg])
        con.execute("INSERT INTO related_issue VALUES (?, ?, 'body')", [s.pr_id, s.issue_id])
        con.execute("INSERT INTO issue VALUES (?, ?, ?, ?, 'fx-issuer', 'closed', '2025-01-20T10:00:00Z', NULL, ?)",
                    [s.issue_id, 100 + s.number, "add() is wrong for negative numbers",
                     f"Please fix add(). cc @fx-rev-1, contact {MAIL_ISSUE}. Tried {MODEL_ID}.",
                     f"https://github.com/{full}/issues/{100 + s.number}"])
    # The owner of repository 101 acts as an account in AIDev (an issue of another PR): the {owner} rule masks it.
    con.execute("INSERT INTO issue VALUES (7999, 1, 'other', 'other', 'fx-owner', 'open', '2025-01-01T00:00:00Z', NULL, 'x')")
    # A person in AIDev who takes no part in these PRs: a link to their account is masked all the same (D51).
    con.execute("INSERT INTO issue VALUES (7998, 2, 'other', 'other', 'fx-stranger', 'open', '2025-01-01T00:00:00Z', NULL, 'x')")
    for t in ("repository", "pull_request", "pr_review_comments", "pr_commits", "related_issue", "issue"):
        con.execute(f"COPY {t} TO '{(d / f'{t}.parquet').as_posix()}' (FORMAT PARQUET)")


def _write_qualifying(path: Path, specs: dict[str, PRSpec], full_names: dict[int, str], repos: Path) -> None:
    comments, prs = [], []
    judge = {"request_type": "defect_report", "addressed": "yes", "testable_offline": "yes", "confidence": "medium"}
    for tid in ORDER:
        s = specs[tid]
        cid = 8000 + s.number
        comments.append({"comment_id": cid, "pr_id": s.pr_id, "repo_id": s.repo_id, "agent": "Copilot",
                         "repo_url": _repo_url(full_names[s.repo_id]), "license": "GPL-3.0" if s.repo_id == 103 else "MIT",
                         "bare_clone": str(repos / f"{s.repo_id}.git"), "default_branch_ref": "refs/heads/main",
                         "pr_number": s.number, "pr_created_at": f"2025-02-0{s.number}T09:00:00Z",
                         "pr_head_ref": f"refs/pull/{s.number}/head", "pr_head_sha": s.head, "pr_commits_first_sha": s.commits[0],
                         "path": s.path, "original_commit_id": s.reviewed, "later_commit_sha": s.addressing,
                         "issue_id": s.issue_id, "issue_number": 100 + s.number, "judge_1": judge, "judge_2": judge})
        prs.append({"pr_id": s.pr_id, "repo_id": s.repo_id, "pr_number": s.number, "pr_created_at": f"2025-02-0{s.number}T09:00:00Z",
                    "agent": "Copilot", "qualifying_comment_ids": [cid], "earliest_qualifying_comment_id": cid,
                    "rank_in_repository_by_creation": s.rank, "s11_family": s.s11})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "tracecontract/s9-qualifying/v1", "comments": comments, "prs": prs}, indent=1))


def written_text(root: Path) -> str:
    """Every file under ``root`` as text (lower case), for the privacy checks."""
    return "\n".join(p.read_bytes().decode("utf-8", "replace").lower() for p in sorted(root.rglob("*")) if p.is_file())


def forbidden() -> list[str]:
    return [*LOGINS, *(n.lower() for n in NAMES), MAIL_REV, MAIL_ISSUE, NOREPLY.lower(), MODEL_ID]
