"""Deterministic screening funnel over the AIDev v5 tables (population natural:pr-review, decision log D47).

Usage: python -I scripts/screen_aidev.py --data <dir> [--out <manifest.json>] [--texts-out <file.jsonl>]

``--data`` is the directory with the AIDev v5 parquet files (``hao-li/AIDev`` at tag v5 =
b37f9fd1613cfec55886105bb76721918d015dc7): repository, pull_request, pr_review_comments,
pr_commits, related_issue and issue. They hold third-party personal data, so the script is
run with an isolated interpreter (``python -I``) and reads them with DuckDB only.

Stages, each counted by agent (``pull_request.agent``):

* S1  agent PRs: the AIDev-pop ``pull_request`` rows.
* S2  PRs whose repository (``repository.url = pull_request.repo_url``) has language Python, an
  SPDX licence in {MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause}, and is not a fork.
* S3  inline review comments on S2 PRs, joined by ``pull_request_url = repo_url || '/pulls/' || number``.
* S4  human (``user_type = 'User'``) thread-starting (``in_reply_to_id IS NULL``) comments, not by the
  PR's author account (case-insensitive) and not by a login ending in ``[bot]``.
* S5  on a path ending in ``.py``, with a non-empty ``diff_hunk``.
* S6  the commented code changed afterwards: ``commit_id`` differs from ``original_commit_id``, or
  ``position = 1`` and ``original_position > 1`` (AIDev filled GitHub's null position of outdated
  comments with 1).
* S7  the reviewed commit (``original_commit_id``) is among the PR's ``pr_commits`` rows, and a row
  of that PR with another SHA follows its first occurrence in file row order. ``pr_commits`` has no
  dates or parents, so "later" is a heuristic; ``checks.commit_order`` measures it.
* S8  a linked issue (``related_issue``) exists whose author is not a bot account. S8' drops this
  requirement: without a linked issue the initial request is the agent-written PR body.
* S8a the first later commit is agent-attributed: its author is a bot account, or its message has an
  agent co-author trailer (``AGENT_TRAILERS``). Applied to S8 and, for reference, to S8'.

A bot account is a login ending in ``[bot]`` or one that has ``user_type = 'Bot'`` on any review
comment. Stage S9 is a uniform random sample (``random.Random(SEED)``) of up to ``SAMPLE_SIZE``
comment ids from S8 ∩ S8a, sorted by id first. If that pool holds fewer than ``MIN_PRIMARY``
comments, the sample is topped up from S8 without S8a, with the same generator, and each row
records its pool.

The manifest (``--out``) holds counts, ids, SHAs, file paths and sha256 hashes of texts only: no
login, @handle, e-mail address or verbatim text. ``--texts-out`` writes the pseudonymised texts of
the sample for the next screening stage; it must lie outside the repository and never enters git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

import duckdb

R = Path(__file__).resolve().parents[1]
DEFAULT_OUT = R / "data" / "manifests" / "screening_natural_aidev.json"
TABLES = ("repository", "pull_request", "pr_review_comments", "pr_commits", "related_issue", "issue")
REVISION = "b37f9fd1613cfec55886105bb76721918d015dc7"
LICENSES = ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause")
SEED, SAMPLE_SIZE, MIN_PRIMARY, JOIN_SAMPLE = 20261121, 150, 60, 1000
API_REPOS = "https://api.github.com/repos/"
# Agent co-author trailers in a commit message (RE2 syntax, DuckDB ``regexp_matches``): label -> pattern.
_CO = r"(?im)^\s*co-authored-by:\s*"
AGENT_TRAILERS = {
    "claude": _CO + r"claude\b",
    "copilot": _CO + r"copilot\b",
    "codex": _CO + r"(?:openai[ -])?codex\b",
    "cursor": _CO + r"cursor(?:[ -]?agent)?\b",
    "devin": _CO + r"devin\b",
    "devin_service_account": _CO + r"[^\n]*cognition\.ai>",  # an account in the domain of Devin's maker
    "jules": _CO + r"(?:google-labs-)?jules\b",
}
# Handles that address a coding agent (lower case, without a ``[bot]`` suffix); pseudonymised as "agent".
AGENT_HANDLES = frozenset({"copilot", "copilot-swe-agent", "claude", "codex", "chatgpt-codex-connector", "cursor",
                           "cursoragent", "devin-ai-integration", "google-labs-jules", "jules"})


def connect(data: Path) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with one view per table; ``pr_commits`` carries its file row number."""
    con = duckdb.connect()
    for t in TABLES:
        f = (data / f"{t}.parquet").as_posix().replace("'", "''")
        extra = ", file_row_number = true" if t == "pr_commits" else ""
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{f}'{extra})")
    con.execute("""CREATE TEMP TABLE bots AS SELECT DISTINCT lower("user") AS login FROM pr_review_comments
                   WHERE user_type = 'Bot' AND "user" IS NOT NULL""")
    con.execute("CREATE TEMP MACRO is_bot(x) AS (lower(x) LIKE '%[bot]' OR lower(x) IN (SELECT login FROM bots))")
    return con


def _one(con, sql: str, params=()) -> tuple:
    return con.execute(sql, list(params)).fetchone()


def _agents(con) -> list[str]:
    return [a for (a,) in con.execute("SELECT DISTINCT agent FROM pull_request ORDER BY agent").fetchall()]


def _stage(con, sid: str, table: str, unit: str, rule: str, agents: list[str], **extra) -> dict:
    """Counts of one stage table: rows, PRs, repositories, and both by agent."""
    by = {a: {"prs": 0} if unit == "pull_request" else {"comments": 0, "prs": 0} for a in agents}
    for agent, n, prs in con.execute(f"SELECT agent, count(*), count(DISTINCT pr_id) FROM {table} GROUP BY agent").fetchall():
        by[agent] = {"prs": prs} if unit == "pull_request" else {"comments": n, "prs": prs}
    n, prs, repos = _one(con, f"SELECT count(*), count(DISTINCT pr_id), count(DISTINCT repo_id) FROM {table}")
    rec = {"id": sid, "unit": unit, "rule": rule, "count": n, "prs": prs, "repos": repos, "by_agent": by}
    rec.update(extra)
    return rec


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 6) if n else None


def build_funnel(con, agents: list[str] | None = None) -> tuple[list[dict], dict]:
    """Create the stage tables s1 ... s8 (and the S8a flags) and return (stages, checks)."""
    agents = agents if agents is not None else _agents(con)
    stages, checks = [], {}
    con.execute("""CREATE TEMP TABLE s1 AS SELECT id AS pr_id, agent, repo_id, repo_url, number, "user" AS pr_user
                   FROM pull_request""")
    stages.append(_stage(con, "S1", "s1", "pull_request", "AIDev-pop agent PRs (pull_request rows)", agents))

    lic = ", ".join(f"'{x}'" for x in LICENSES)
    con.execute("CREATE TEMP TABLE s1r AS SELECT s1.*, r.language, r.license, r.is_forked "
                "FROM s1 JOIN repository r ON r.url = s1.repo_url")
    con.execute(f"CREATE TEMP TABLE s2 AS SELECT pr_id, agent, repo_id, repo_url, number, pr_user FROM s1r "
                f"WHERE language = 'Python' AND license IN ({lic}) AND is_forked = false")
    steps = _one(con, f"""SELECT count(*), count(*) FILTER (WHERE language = 'Python'),
        count(*) FILTER (WHERE language = 'Python' AND license IN ({lic})) FROM s1r""")
    stages.append(_stage(con, "S2", "s2", "pull_request",
                         "repository (repository.url = pull_request.repo_url) has language Python, SPDX licence in "
                         f"{{{', '.join(LICENSES)}}}, is_forked false", agents,
                         cumulative={"repository_matched_by_url": steps[0], "and_python": steps[1],
                                     "and_licence": steps[2]}))
    checks["pr_to_repository"] = _pr_repo_check(con, lic)

    con.execute("""CREATE TEMP TABLE s3 AS SELECT c.id, c."user" AS c_user, c.user_type, c.in_reply_to_id, c.path,
        coalesce(c.diff_hunk, '') <> '' AS has_hunk, c.position, c.original_position, c.commit_id, c.original_commit_id,
        s2.pr_id, s2.agent, s2.repo_id, s2.pr_user
        FROM pr_review_comments c JOIN s2 ON c.pull_request_url = s2.repo_url || '/pulls/' || s2.number::VARCHAR""")
    stages.append(_stage(con, "S3", "s3", "review_comment",
                         "inline review comments on S2 PRs (pull_request_url = repo_url || '/pulls/' || number)", agents))
    checks["comment_to_pr"] = _comment_join_check(con)

    con.execute("""CREATE TEMP TABLE s4 AS SELECT * FROM s3 WHERE user_type = 'User' AND in_reply_to_id IS NULL
        AND lower(c_user) IS DISTINCT FROM lower(pr_user) AND NOT lower(c_user) LIKE '%[bot]'""")
    steps = _one(con, """SELECT count(*) FILTER (WHERE user_type = 'User'),
        count(*) FILTER (WHERE user_type = 'User' AND in_reply_to_id IS NULL),
        count(*) FILTER (WHERE user_type = 'User' AND in_reply_to_id IS NULL AND lower(c_user) IS DISTINCT FROM lower(pr_user))
        FROM s3""")
    stages.append(_stage(con, "S4", "s4", "review_comment",
                         "user_type = 'User', in_reply_to_id IS NULL, author is not the PR's author account "
                         "(case-insensitive) and does not end in [bot]", agents,
                         cumulative={"user_type_user": steps[0], "and_thread_start": steps[1],
                                     "and_not_pr_author": steps[2]}))

    con.execute("CREATE TEMP TABLE s5 AS SELECT * FROM s4 WHERE path LIKE '%.py' AND has_hunk")
    stages.append(_stage(con, "S5", "s5", "review_comment", "path ends in .py and diff_hunk is not empty", agents,
                         cumulative={"py_path": _one(con, "SELECT count(*) FROM s4 WHERE path LIKE '%.py'")[0]}))

    con.execute("""CREATE TEMP TABLE s6 AS SELECT * FROM s5 WHERE commit_id IS DISTINCT FROM original_commit_id
        OR (position = 1 AND original_position > 1)""")
    moved, outdated, both = _one(con, """SELECT count(*) FILTER (WHERE commit_id IS DISTINCT FROM original_commit_id),
        count(*) FILTER (WHERE position = 1 AND original_position > 1),
        count(*) FILTER (WHERE commit_id IS DISTINCT FROM original_commit_id AND position = 1 AND original_position > 1)
        FROM s6""")
    stages.append(_stage(con, "S6", "s6", "review_comment",
                         "commit_id differs from original_commit_id, or position = 1 and original_position > 1", agents,
                         branches={"commit_id_differs": moved, "outdated_position": outdated, "both": both}))

    # Each SHA of a PR sits at its first row: a repeated row of an earlier commit is not a later commit.
    con.execute("""CREATE TEMP TABLE pc AS SELECT pr_id, sha, file_row_number AS rn, author, message FROM pr_commits
                   WHERE pr_id IN (SELECT DISTINCT pr_id FROM s6)
                   QUALIFY row_number() OVER (PARTITION BY pr_id, sha ORDER BY file_row_number) = 1""")
    con.execute("""CREATE TEMP TABLE s7_orig AS SELECT s6.id, pc.rn AS orig_rn FROM s6
                   JOIN pc ON pc.pr_id = s6.pr_id AND pc.sha = s6.original_commit_id""")
    con.execute("""CREATE TEMP TABLE s7 AS WITH nxt AS (
            SELECT s6.id, min(pc.rn) AS later_rn FROM s6 JOIN s7_orig o ON o.id = s6.id
            JOIN pc ON pc.pr_id = s6.pr_id AND pc.rn > o.orig_rn GROUP BY s6.id)
        SELECT s6.*, pc.sha AS later_sha, pc.author AS later_author, pc.message AS later_message
        FROM s6 JOIN nxt ON nxt.id = s6.id JOIN pc ON pc.rn = nxt.later_rn""")
    stages.append(_stage(con, "S7", "s7", "review_comment",
                         "original_commit_id is among the PR's pr_commits rows and another commit of that PR first "
                         "appears after it in file row order (heuristic: pr_commits has no dates or parents)", agents,
                         cumulative={"original_commit_in_pr_commits": _one(con, "SELECT count(*) FROM s7_orig")[0]}))
    checks["commit_order"] = _commit_order_check(con)

    con.execute("""CREATE TEMP TABLE links AS SELECT r.pr_id, r.issue_id, r.source, i.id IS NOT NULL AS in_issue_table,
        i."user" AS issue_user FROM related_issue r LEFT JOIN issue i ON i.id = r.issue_id
        WHERE r.pr_id IN (SELECT pr_id FROM s7)""")
    con.execute("""CREATE TEMP TABLE pr_issue AS SELECT pr_id, issue_id, n_issues FROM (
        SELECT pr_id, issue_id, count(*) OVER (PARTITION BY pr_id) AS n_issues,
               row_number() OVER (PARTITION BY pr_id ORDER BY prefer, issue_id) AS k FROM (
            SELECT pr_id, issue_id, min(CASE WHEN source = 'body' THEN 0 ELSE 1 END) AS prefer FROM links
            WHERE in_issue_table AND issue_user IS NOT NULL AND NOT is_bot(issue_user) GROUP BY pr_id, issue_id))
        WHERE k = 1""")
    con.execute("CREATE TEMP TABLE s8 AS SELECT s7.*, p.issue_id, p.n_issues FROM s7 JOIN pr_issue p USING (pr_id)")
    linked, in_table = _one(con, """SELECT count(*) FILTER (WHERE pr_id IN (SELECT pr_id FROM links)),
        count(*) FILTER (WHERE pr_id IN (SELECT pr_id FROM links WHERE in_issue_table)) FROM s7""")
    no_body, several = _one(con, """SELECT count(*) FILTER (WHERE coalesce(i.body, '') = ''),
        count(*) FILTER (WHERE s8.n_issues > 1) FROM s8 JOIN issue i ON i.id = s8.issue_id""")
    stages.append(_stage(con, "S8", "s8", "review_comment",
                         "related_issue links the PR to an issue whose author is not a bot account", agents,
                         cumulative={"pr_has_related_issue": linked, "and_issue_in_issue_table": in_table},
                         primary_issue="the linked non-bot issue found in the PR body (source 'body') if any, else "
                                       "the lowest issue id",
                         primary_issue_without_body=no_body, comments_on_prs_with_several_non_bot_issues=several))
    stages.append(_stage(con, "S8'", "s7", "review_comment",
                         "S7 without the linked-issue requirement: the initial request may be only the agent-written "
                         "PR body, which is not user evidence", agents,
                         split={"linked_non_bot_issue": stages[-1]["count"],
                                "linked_issue_without_non_bot_author": linked - stages[-1]["count"],
                                "no_linked_issue": stages[-2]["count"] - linked}))

    flags = ", ".join(f"regexp_matches(coalesce(later_message, ''), '{p}') AS t_{k}" for k, p in AGENT_TRAILERS.items())
    agent_accounts = ", ".join(f"'{h}'" for h in sorted(AGENT_HANDLES))
    con.execute(f"""CREATE TEMP TABLE s7_flags AS SELECT id, coalesce(is_bot(later_author), false) AS bot_author,
        coalesce(is_bot(later_author) AND regexp_replace(lower(later_author), '\\[bot\\]$', '') IN ({agent_accounts}), false)
        AS agent_account, {flags} FROM s7""")
    trailer_any = " OR ".join(f"t_{k}" for k in AGENT_TRAILERS)
    con.execute(f"CREATE TEMP TABLE s7a AS SELECT s7.* FROM s7 JOIN s7_flags f USING (id) WHERE f.bot_author OR {trailer_any}")
    con.execute("CREATE TEMP TABLE s8a AS SELECT s8.* FROM s8 WHERE id IN (SELECT id FROM s7a)")
    patterns = _trailer_counts(con, trailer_any)
    rule = ("the first later commit is agent-attributed: author is a bot account (login ends in [bot] or has "
            "user_type 'Bot' on a review comment) or the message has an agent co-author trailer")
    stages.append(_stage(con, "S8a", "s8a", "review_comment", rule + " (applied to S8)", agents, criteria=patterns["S8"]))
    stages.append(_stage(con, "S8a'", "s7a", "review_comment", rule + " (applied to S8')", agents,
                         criteria=patterns["S8'"]))
    checks["bot_accounts"] = {"bot_type_logins_in_review_comments": _one(con, "SELECT count(*) FROM bots")[0],
                              "rule": "login ends in [bot] (case-insensitive) or has user_type 'Bot' on a review comment"}
    return stages, checks


def _pr_repo_check(con, lic: str) -> dict:
    n, by_url, by_id, agree = _one(con, """SELECT count(*), count(r1.id), count(r2.id), count(*) FILTER (WHERE r1.id = r2.id)
        FROM pull_request p LEFT JOIN repository r1 ON r1.url = p.repo_url LEFT JOIN repository r2 ON r2.id = p.repo_id""")
    extra = _one(con, f"""SELECT count(*) FROM pull_request p JOIN repository r ON r.id = p.repo_id
        WHERE p.repo_url NOT IN (SELECT url FROM repository)
          AND r.language = 'Python' AND r.license IN ({lic}) AND r.is_forked = false""")[0]
    return {"prs": n, "matched_by_url": by_url, "matched_by_repo_id": by_id, "url_and_id_agree": agree,
            "url_misses_that_pass_S2_by_repo_id": extra,
            "note": "the funnel joins by URL as specified; repo_id is a cross-check"}


def _comment_join_check(con) -> dict:
    """Match rate of the URL join over all comments and on a seeded sample, with independent agreement checks."""
    con.execute("""CREATE TEMP TABLE cj AS SELECT c.id, c.pull_request_url, c.original_commit_id, c.commit_id, c.created_at,
        p.id AS pr_id, p.created_at AS pr_created FROM pr_review_comments c
        LEFT JOIN pull_request p ON c.pull_request_url = p.repo_url || '/pulls/' || p.number::VARCHAR""")
    n, matched, extra_rows, urls = _one(con, """SELECT count(DISTINCT id), count(DISTINCT id) FILTER (WHERE pr_id IS NOT NULL),
        count(*) - count(DISTINCT id), count(DISTINCT pull_request_url) FILTER (WHERE pr_id IS NULL) FROM cj""")
    linkable = _one(con, """SELECT count(DISTINCT u.id) FROM cj u JOIN pr_commits k ON k.sha = u.original_commit_id
        WHERE u.pr_id IS NULL""")[0]
    ids = [i for (i,) in con.execute("SELECT id FROM cj ORDER BY id").fetchall()]
    pick = sorted(random.Random(SEED).sample(ids, min(JOIN_SAMPLE, len(ids))))
    con.execute("CREATE TEMP TABLE cj_pick (id BIGINT)")
    con.executemany("INSERT INTO cj_pick VALUES (?)", [(i,) for i in pick])
    s_matched, s_commit, s_after = _one(con, """SELECT count(cj.pr_id),
        count(*) FILTER (WHERE cj.pr_id IS NOT NULL AND EXISTS (SELECT 1 FROM pr_commits k WHERE k.pr_id = cj.pr_id
                         AND k.sha IN (cj.original_commit_id, cj.commit_id))),
        count(*) FILTER (WHERE cj.pr_id IS NOT NULL AND cj.created_at >= cj.pr_created)
        FROM cj JOIN cj_pick USING (id)""")
    return {"key": "pr_review_comments.pull_request_url = pull_request.repo_url || '/pulls/' || pull_request.number",
            "all_comments": {"comments": n, "matched": matched, "match_rate": _rate(matched, n),
                             "join_rows_beyond_one_per_comment": extra_rows,
                             "unmatched_pr_urls": urls, "unmatched_linkable_by_original_commit_sha": linkable},
            "sample": {"seed": SEED, "size": len(pick), "matched": s_matched, "match_rate": _rate(s_matched, len(pick)),
                       "matched_with_commit_in_that_prs_pr_commits": s_commit,
                       "matched_created_at_not_before_pr": s_after}}


def _commit_order_check(con) -> dict:
    """Measure the file-row-order heuristic where the data allow it."""
    both, after = _one(con, """SELECT count(*), count(*) FILTER (WHERE b.rn > a.rn) FROM s6
        JOIN pc a ON a.pr_id = s6.pr_id AND a.sha = s6.original_commit_id
        JOIN pc b ON b.pr_id = s6.pr_id AND b.sha = s6.commit_id
        WHERE s6.commit_id <> s6.original_commit_id""")
    live, last = _one(con, """WITH k AS (SELECT pr_id, sha, file_row_number AS rn FROM pr_commits
                                         WHERE pr_id IN (SELECT pr_id FROM s3)),
        lastrow AS (SELECT pr_id, arg_max(sha, rn) AS sha FROM k GROUP BY pr_id)
        SELECT count(*), count(*) FILTER (WHERE l.sha = s3.commit_id) FROM s3 JOIN lastrow l USING (pr_id)
        WHERE s3.position > 1 AND EXISTS (SELECT 1 FROM k WHERE k.pr_id = s3.pr_id AND k.sha = s3.commit_id)""")
    dup_rows, dup_prs = _one(con, """SELECT coalesce(sum(k - 1), 0), count(DISTINCT pr_id) FROM
        (SELECT pr_id, sha, count(*) AS k FROM pr_commits GROUP BY 1, 2 HAVING count(*) > 1)""")
    capped = _one(con, "SELECT count(*) FROM (SELECT pr_id FROM pr_commits GROUP BY 1 HAVING count(DISTINCT sha) >= 250)")[0]
    s7_capped = _one(con, """SELECT count(*) FROM s7 WHERE pr_id IN
        (SELECT pr_id FROM pc GROUP BY 1 HAVING count(DISTINCT sha) >= 250)""")[0]
    missing = _one(con, "SELECT count(*) FROM s6 WHERE id NOT IN (SELECT id FROM s7_orig)")[0]
    return {
        "heuristic": "a commit of the PR whose first pr_commits row comes after the reviewed commit's first row is later",
        "s6_commit_id_and_original_both_listed": both, "commit_id_after_original_in_row_order": after,
        "commit_id_after_original_rate": _rate(after, both),
        "s3_live_comments_with_listed_commit_id": live, "commit_id_is_prs_last_row": last,
        "commit_id_is_last_row_rate": _rate(last, live),
        "s6_original_commit_missing_from_pr_commits": missing,
        "s6_original_commit_missing_rate": _rate(missing, _one(con, "SELECT count(*) FROM s6")[0]),
        "duplicate_pr_sha_rows_beyond_first": int(dup_rows), "prs_with_duplicate_rows": dup_prs,
        "prs_at_250_commit_cap": capped, "s7_comments_in_capped_prs": s7_capped,
        "note": ("live comments are those with position > 1; GitHub moves their commit_id to the PR head, so the "
                 "share whose commit_id is the PR's last row estimates how often the last row is the head"),
    }


def _trailer_counts(con, trailer_any: str) -> dict:
    out = {}
    for name, table in (("S8", "s8"), ("S8'", "s7")):
        sel = ", ".join(f"count(*) FILTER (WHERE t_{k})" for k in AGENT_TRAILERS)
        row = _one(con, f"""SELECT count(*) FILTER (WHERE bot_author), count(*) FILTER (WHERE agent_account),
            count(*) FILTER (WHERE {trailer_any}), count(*) FILTER (WHERE bot_author AND ({trailer_any})), {sel}
            FROM s7_flags WHERE id IN (SELECT id FROM {table})""")
        out[name] = {"bot_author": row[0], "bot_author_is_an_agent_account": row[1],
                     "bot_author_is_another_bot": row[0] - row[1], "agent_trailer": row[2], "both": row[3],
                     "trailer_patterns": [{"label": k, "pattern": p, "comments": row[4 + i]}
                                          for i, (k, p) in enumerate(AGENT_TRAILERS.items())]}
    return out


def draw_sample(primary: list[int], fallback: list[int], seed: int = SEED, size: int = SAMPLE_SIZE,
                min_primary: int = MIN_PRIMARY) -> list[tuple[int, str]]:
    """Stage S9: (comment id, pool) pairs, sorted by id; deterministic for a given seed and pools."""
    rng = random.Random(seed)
    primary, fallback = sorted(primary), sorted(fallback)
    take = primary if len(primary) <= size else rng.sample(primary, size)
    out = [(i, "S8+S8a") for i in take]
    if len(primary) < min_primary:
        k = min(size - len(take), len(fallback))
        out += [(i, "S8-without-S8a") for i in (fallback if k == len(fallback) else rng.sample(fallback, k))]
    return sorted(out)


def sample_rows(con, picked: list[tuple[int, str]]) -> list[dict]:
    con.execute("CREATE OR REPLACE TEMP TABLE pick (id BIGINT, pool VARCHAR)")
    con.executemany("INSERT INTO pick VALUES (?, ?)", picked)
    rows = con.execute("""SELECT s.id, p.pool, s.pr_id, s.repo_id, s.agent, s.path, s.original_commit_id, s.commit_id,
            s.later_sha, s.issue_id, s.n_issues, sha256(c.body), sha256(i.body),
            lower(c."user") = lower(i."user"), lower(s.pr_user) = lower(i."user")
        FROM pick p JOIN s8 s USING (id) JOIN pr_review_comments c ON c.id = s.id JOIN issue i ON i.id = s.issue_id
        ORDER BY s.id""").fetchall()
    keys = ("comment_id", "pool", "pr_id", "repo_id", "agent", "path", "original_commit_id", "commit_id",
            "later_commit_sha", "issue_id", "linked_non_bot_issues", "comment_body_sha256", "issue_body_sha256",
            "reviewer_is_issue_author", "pr_author_is_issue_author")
    return [dict(zip(keys, r)) for r in rows]


def _owner_pattern(owner: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9-]){re.escape(owner)}(?![a-z0-9-])", re.I)


def mask_owners_in_paths(con, rows: list[dict]) -> dict:
    """A path segment may name the repository owner (a package directory). It is kept when the owner never acts
    as an account in AIDev (no PR, review comment, issue or commit), as an organisation cannot; otherwise the
    name is replaced by ``{owner}`` in the manifest (the texts file keeps the real path)."""
    hits: dict[str, list[dict]] = {}
    for r in rows:
        owner = _one(con, "SELECT lower(split_part(url, '/', 5)) FROM repository WHERE id = ?", (r["repo_id"],))[0]
        if owner and _owner_pattern(owner).search(r["path"]):
            hits.setdefault(owner, []).append(r)
    actors: set[str] = set()
    if hits:
        actors = {x for (x,) in con.execute("""SELECT login FROM (SELECT unnest(?::VARCHAR[]) AS login) WHERE login IN (
            SELECT lower("user") FROM pull_request UNION SELECT lower("user") FROM pr_review_comments
            UNION SELECT lower("user") FROM issue UNION SELECT lower(author) FROM pr_commits
            UNION SELECT lower(committer) FROM pr_commits)""", [sorted(hits)]).fetchall()}
    for owner in actors:
        for r in hits[owner]:
            r["path"] = _owner_pattern(owner).sub("{owner}", r["path"])
            r["path_owner_masked"] = True
    return {"rows_whose_path_names_the_repository_owner": sum(map(len, hits.values())), "distinct_owners": len(hits),
            "owners_acting_as_an_account": len(actors), "rows_masked": sum(len(hits[o]) for o in actors),
            "rule": "the owner's name in a path is kept when the owner never authored a PR, review comment, issue or "
                    "commit in AIDev (an organisation), else replaced by {owner}"}


# ---------------------------------------------------------------- pseudonymised texts (outside the repository)

_LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}(?:\[bot\])?"
_EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
_PROFILE = (r"https?://(?:www\.)?github\.com/(?:sponsors/)?[A-Za-z0-9-]+(?:\[bot\])?/?(?=$|[\s)\]>\"'.,;:!?])"
            r"|https?://api\.github\.com/users/[^\s)\]>\"']+|https?://avatars\.githubusercontent\.com/[^\s)\]>\"']+")
# Python decorators and docstring tags: an @word that is one of these, or that is followed by "(" or
# ".name", is code (``@property``, ``@pytest.mark``, ``@dataclass(...)``), not a handle.
CODE_AT = frozenset({"property", "staticmethod", "classmethod", "abstractmethod", "dataclass", "override", "overload",
                     "cached_property", "contextmanager", "asynccontextmanager", "final", "total_ordering",
                     "singledispatch", "unique", "fixture", "computed_field", "login_required", "csrf_exempt",
                     "shared_task", "task", "tool", "njit", "jit", "lru_cache", "cache", "param", "return", "returns",
                     "rtype", "type", "raise", "raises", "see", "since", "note", "todo", "deprecated", "example"})


class Pseudonymizer:
    """Replace logins and @handles by role labels; remove e-mail addresses and links to user profiles.

    ``roles`` maps known logins to fixed labels (reviewer, pr-author, issue-author, repo-owner, agent);
    ``others`` are further participants' logins, labelled user-1, user-2, ... on first appearance, as
    are unknown @handles; bot accounts (``bots``) become bot-1, ...; agent handles become "agent". One
    left-to-right pass, so a label is never replaced again.
    """

    def __init__(self, roles: dict[str, str], others: set[str] | frozenset[str] = frozenset(),
                 bots: frozenset[str] = frozenset()):
        self.roles = {k.lower(): v for k, v in roles.items() if k}
        self.others = {o.lower() for o in others if o} - set(self.roles)
        self.bots = bots
        self.counts: dict[str, int] = {}
        names = sorted(set(self.roles) | self.others, key=len, reverse=True)
        known = r"|(?<![A-Za-z0-9_@-])(?P<known>" + "|".join(map(re.escape, names)) + r")(?![A-Za-z0-9_-])" if names else ""
        self._re = re.compile(rf"(?P<email>{_EMAIL})|(?P<profile>{_PROFILE})|(?<![A-Za-z0-9._%+/-])@(?P<handle>{_LOGIN})"
                              + known, re.I)

    def label(self, login: str) -> str:
        h = login.lower()
        if h not in self.roles:
            base = h.removesuffix("[bot]")
            if base in AGENT_HANDLES:
                self.roles[h] = "agent"
            else:
                kind = "bot" if h in self.bots or base + "[bot]" in self.bots else "user"
                self.roles[h] = f"{kind}-{sum(v.startswith(kind + '-') for v in self.roles.values()) + 1}"
        return self.roles[h]

    def _count(self, what: str) -> None:
        self.counts[what] = self.counts.get(what, 0) + 1

    def _sub(self, m: re.Match) -> str:
        if m.group("email"):
            self._count("email")
            return "[email removed]"
        if m.group("profile"):
            self._count("profile_link")
            return "[profile link removed]"
        if m.group("handle"):
            name = m.group("handle")
            if name.lower() not in self.roles and name.lower() not in self.others:
                after = m.string[m.end():m.end() + 2]
                if name.lower() in CODE_AT or after[:1] == "(" or (after[:1] == "." and after[1:2].isidentifier()):
                    return m.group(0)
            self._count("handle")
            return "@" + self.label(name)
        self._count("login")
        return self.label(m.group("known"))

    def __call__(self, text: str | None) -> str | None:
        return None if text is None else self._re.sub(self._sub, text)


def text_rows(con, rows: list[dict]) -> list[dict]:
    """Pseudonymised texts of the sample: comment body, diff hunk, PR title, issue title and body.

    The repository URL and the file path are kept verbatim (the next stage fetches the repository). Labels:
    reviewer, pr-author (or agent, when a bot account opened the PR), issue-author, repo-owner, agent, and
    user-N / bot-N for the PR's other participants and for unknown handles.
    """
    bots = frozenset(b for (b,) in con.execute("SELECT login FROM bots").fetchall())
    con.execute("""CREATE OR REPLACE TEMP TABLE pick_txt AS SELECT p.id, c."user" AS c_user, c.body, c.diff_hunk,
            c.pull_request_url, pr.repo_url, pr."user" AS pr_user, coalesce(is_bot(pr."user"), false) AS pr_bot,
            pr.title, i."user" AS i_user, i.title AS i_title, i.body AS i_body, s.pr_id, s.path
        FROM pick p JOIN s8 s USING (id) JOIN pr_review_comments c ON c.id = p.id
        JOIN pull_request pr ON pr.id = s.pr_id JOIN issue i ON i.id = s.issue_id""")
    texts = {r[0]: r[1:] for r in con.execute("SELECT * FROM pick_txt").fetchall()}
    people: dict[int, set[str]] = {}
    for pr_id, x in con.execute("""SELECT DISTINCT pr_id, x FROM (
            SELECT t.pr_id, c."user" AS x FROM (SELECT DISTINCT pr_id, pull_request_url FROM pick_txt) t
                JOIN pr_review_comments c ON c.pull_request_url = t.pull_request_url
            UNION ALL SELECT pr_id, author FROM pr_commits WHERE pr_id IN (SELECT pr_id FROM pick_txt)
            UNION ALL SELECT pr_id, committer FROM pr_commits WHERE pr_id IN (SELECT pr_id FROM pick_txt)
            UNION ALL SELECT r.pr_id, i."user" FROM related_issue r JOIN issue i ON i.id = r.issue_id
                WHERE r.pr_id IN (SELECT pr_id FROM pick_txt))
        WHERE x IS NOT NULL AND NOT contains(x, ' ') AND NOT is_bot(x) AND lower(x) <> 'web-flow'""").fetchall():
        people.setdefault(pr_id, set()).add(x)
    out = []
    for r in rows:
        c_user, body, hunk, _, url, pr_user, pr_bot, title, i_user, i_title, i_body, pr_id, path = texts[r["comment_id"]]
        full_name = url.removeprefix(API_REPOS)
        roles = {c_user: "reviewer"}
        for login, label in ((pr_user, "agent" if pr_bot else "pr-author"), (i_user, "issue-author"),
                             (full_name.split("/")[0], "repo-owner")):
            if login and login.lower() not in {k.lower() for k in roles}:
                roles[login] = label
        others = {x for x in people.get(pr_id, ()) if x.lower().removesuffix("[bot]") not in AGENT_HANDLES}
        ps = Pseudonymizer(roles, others, bots)
        fields = {k: ps(v) for k, v in (("comment_body", body), ("diff_hunk", hunk), ("pr_title", title),
                                        ("issue_title", i_title), ("issue_body", i_body))}
        out.append({"comment_id": r["comment_id"], "pool": r["pool"], "pr_id": pr_id, "repo_id": r["repo_id"],
                    "agent": r["agent"], "repo_url": "https://github.com/" + full_name, "path": path,
                    "original_commit_id": r["original_commit_id"], "commit_id": r["commit_id"],
                    "later_commit_sha": r["later_commit_sha"], "issue_id": r["issue_id"], **fields,
                    "comment_body_sha256": r["comment_body_sha256"], "issue_body_sha256": r["issue_body_sha256"],
                    "reviewer_is_issue_author": r["reviewer_is_issue_author"],
                    "pr_author_is_issue_author": r["pr_author_is_issue_author"],
                    "pr_author_role": "agent" if pr_bot else "pr-author",
                    "replacements": dict(sorted(ps.counts.items()))})
    return out


# ---------------------------------------------------------------- inputs and main

def file_records(data: Path, con) -> dict:
    rec_path = data / "_download_record.json"
    expected = {}
    if rec_path.exists():
        expected = {f["path"]: f["sha256"] for f in json.loads(rec_path.read_text(encoding="utf-8")).get("files", [])}
    out = {}
    for t in TABLES:
        h = hashlib.sha256()
        with open(data / f"{t}.parquet", "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        name = f"{t}.parquet"
        out[name] = {"sha256": h.hexdigest(), "rows": _one(con, f"SELECT count(*) FROM {t}")[0],
                     "matches_download_record": expected.get(name) == h.hexdigest() if expected else None}
    return out


def screen(data: Path) -> tuple[dict, duckdb.DuckDBPyConnection]:
    con = connect(data)
    stages, checks = build_funnel(con)
    primary = [i for (i,) in con.execute("SELECT id FROM s8a ORDER BY id").fetchall()]
    fallback = [i for (i,) in con.execute("SELECT id FROM s8 WHERE id NOT IN (SELECT id FROM s8a) ORDER BY id").fetchall()]
    picked = draw_sample(primary, fallback)
    rows = sample_rows(con, picked)
    owners = mask_owners_in_paths(con, rows)
    manifest = {
        "schema": "tracecontract/natural-screening-funnel/v1",
        "population": "natural:pr-review",
        "decision_log": "D47",
        "generator": "scripts/screen_aidev.py",
        "source": {"dataset": "hao-li/AIDev", "revision": REVISION,
                   "licence": "CC-BY-4.0 compilation; each source repository keeps its own licence",
                   "files": file_records(data, con)},
        "privacy": "counts, ids, SHAs, file paths and sha256 hashes of texts only: no login, mention handle, e-mail "
                   "address or verbatim text",
        "stages": stages,
        "checks": checks,
        "sample": {"stage": "S9", "seed": SEED, "size_limit": SAMPLE_SIZE, "min_primary": MIN_PRIMARY,
                   "rule": "comment ids of S8 and S8a sorted by id; random.Random(seed).sample(ids, size_limit) if more "
                           "survive, else all; if fewer than min_primary survive, topped up from S8 without S8a with "
                           "the same generator",
                   "pool_sizes": {"S8+S8a": len(primary), "S8-without-S8a": len(fallback)},
                   "topped_up": len(primary) < MIN_PRIMARY, "size": len(rows),
                   "by_agent": {a: sum(r["agent"] == a for r in rows) for a in sorted({s["agent"] for s in rows})},
                   "hashes": "sha256 of the UTF-8 comment body and issue body",
                   "path_owner_check": owners,
                   "rows": rows},
    }
    return manifest, con


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--texts-out", type=Path)
    a = ap.parse_args(argv)
    if a.texts_out is not None and a.texts_out.resolve().is_relative_to(R):
        ap.error("--texts-out must lie outside the repository: it holds third-party text")
    manifest, con = screen(a.data)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for s in manifest["stages"]:
        print(f"{s['id']:5} {s['count']:>8} {s['unit']}s, {s['prs']} PRs, {s['repos']} repositories")
    print(f"S9    {manifest['sample']['size']} sampled (pools {manifest['sample']['pool_sizes']})")
    if a.texts_out is not None:
        a.texts_out.parent.mkdir(parents=True, exist_ok=True)
        rows = text_rows(con, manifest["sample"]["rows"])
        a.texts_out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(f"texts: {len(rows)} pseudonymised rows written outside the repository")
    return 0


if __name__ == "__main__":
    sys.exit(main())
