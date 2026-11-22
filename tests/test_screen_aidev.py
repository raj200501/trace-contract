"""AIDev screening funnel (decision log D47) on a tiny synthetic population written by the test itself.

Every row of the fixture targets one rule: the comment-to-PR join key, S4 (human, thread-starting,
not the PR author, no ``[bot]`` login), S5 (``.py`` path with a diff hunk), S6 (the head moved or the
comment is outdated), S7 (the reviewed commit is in that PR's ``pr_commits`` rows and a commit first
appears after it), S8/S8a, and the seeded S9 sample. It also covers the pseudonymiser and the login
and @handle check of ``scripts/scan_tracked_files.py``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
from pathlib import Path

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")
pytest.importorskip("duckdb")

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sa = _load("screen_aidev")
scan = _load("scan_tracked_files")

S, I, B, F = pa.string(), pa.int64(), pa.bool_(), pa.float64()
SCHEMAS = {  # column names and types of the AIDev v5 files
    "repository": {"id": I, "url": S, "license": S, "full_name": S, "is_forked": B, "language": S, "forks": I, "stars": I},
    "pull_request": {"id": I, "number": I, "title": S, "body": S, "agent": S, "user_id": I, "user": S, "state": S,
                     "created_at": S, "closed_at": S, "merged_at": S, "repo_id": I, "repo_url": S, "html_url": S},
    "pr_review_comments": {"id": I, "pull_request_review_id": I, "user": S, "user_type": S, "diff_hunk": S, "path": S,
                           "position": I, "original_position": I, "commit_id": S, "original_commit_id": S, "body": S,
                           "pull_request_url": S, "created_at": S, "updated_at": S, "in_reply_to_id": F},
    "pr_commits": {"sha": S, "pr_id": I, "author": S, "committer": S, "message": S},
    "related_issue": {"pr_id": I, "issue_id": I, "source": S},
    "issue": {"id": I, "number": I, "title": S, "body": S, "user": S, "state": S, "created_at": S, "closed_at": S,
              "html_url": S},
}
HUNK = "@@ -1,3 +1,3 @@\n class A:\n+    @property\n+    def x(self):"


def _repo(i, name, lic="MIT", lang="Python", fork=False):
    return {"id": i, "url": f"{API}org/{name}", "license": lic, "full_name": f"org/{name}", "is_forked": fork,
            "language": lang, "forks": 0, "stars": 1}


def _pr(i, number, repo, repo_id, agent, user):
    return {"id": i, "number": number, "title": f"Fix {repo} for fx-rev-1", "body": "agent-written body", "agent": agent,
            "user_id": i, "user": user, "state": "closed", "created_at": "2026-01-01T00:00:00Z", "repo_id": repo_id,
            "repo_url": f"{API}org/{repo}", "html_url": f"https://github.com/org/{repo}/pull/{number}"}


def _c(i, number, user, repo="good", path="pkg/a.py", hunk=HUNK, orig="c1", commit="c2", pos=3, opos=3, utype="User",
       reply=None, body="Please keep the old default."):
    return {"id": i, "pull_request_review_id": i, "user": user, "user_type": utype, "diff_hunk": hunk, "path": path,
            "position": pos, "original_position": opos, "commit_id": commit, "original_commit_id": orig, "body": body,
            "pull_request_url": f"{API}org/{repo}/pulls/{number}", "created_at": "2026-01-02T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z", "in_reply_to_id": reply}


MAIL = "fx-rev-1" + "@" + "example.org"  # built at run time, so the source holds no address
BODY_100 = f"@Copilot keep the default, as fx-rev-1 asked; cc @fx-other and https://github.com/fx-rev-3 ({MAIL})"
TABLES = {
    "repository": [_repo(1, "good"), _repo(2, "gpl", lic="GPL-3.0"), _repo(3, "fork", fork=True),
                   _repo(4, "js", lang="JavaScript")],
    "pull_request": [_pr(10, 1, "good", 1, "Copilot", "Copilot"), _pr(11, 2, "good", 1, "Claude_Code", "fx-author"),
                     _pr(12, 3, "gpl", 2, "OpenAI_Codex", "fx-bob"),
                     _pr(13, 4, "js", 4, "Devin", "devin-ai-integration[bot]"), _pr(14, 5, "fork", 3, "Cursor", "fx-carol"),
                     _pr(15, 6, "renamed", 1, "Google_Jules", "google-labs-jules[bot]"),  # URL not in repository.url
                     _pr(16, 7, "good", 1, "Copilot", "Copilot")],
    "pr_review_comments": [
        _c(100, 1, "fx-rev-1", body=BODY_100),                   # passes every stage (the head moved)
        _c(101, 1, "fx-rev-1", reply=100.0),                     # S4: a reply
        _c(102, 1, "copilot-pull-request-reviewer[bot]", utype="Bot"),  # S4: a bot
        _c(104, 1, "fx-helper[bot]"),                            # S4: a [bot] login typed as a user
        _c(115, 1, "Copilot", utype="Bot", reply=100.0),         # puts "Copilot" (no suffix) into the bot set
        _c(105, 1, "fx-rev-1", path="README.md"),                # S5: not a .py path
        _c(106, 1, "fx-rev-1", path="pkg/b.py", hunk=None),      # S5: no diff hunk
        _c(107, 1, "fx-rev-1", path="pkg/c.py", hunk=""),        # S5: empty diff hunk
        _c(108, 1, "fx-rev-1", commit="c1", pos=5, opos=5),      # S6: unchanged
        _c(109, 1, "fx-rev-1", commit="c1", pos=1, opos=7),      # S6: outdated (null position filled with 1)
        _c(120, 1, "fx-rev-1", commit="c1", pos=1, opos=1),      # S6: first line of the hunk, unchanged
        _c(116, 1, "fx-rev-3", path="pkg/d.py", orig="c2", commit="c4"),  # S8 without S8a: a human commit follows
        _c(110, 2, "FX-Author", orig="d1", commit="d3"),         # S4: the PR author, in another case
        _c(111, 2, "fx-rev-2", orig="d9", commit="d3"),          # S7: reviewed commit only in another PR's rows
        _c(112, 2, "fx-rev-2", orig="d3", commit="d3", pos=1, opos=4),  # S7: reviewed commit is the PR's last row
        _c(113, 2, "fx-rev-2", orig="d1", commit="d3"),          # S8' only (no issue); agent co-author trailer
        _c(114, 7, "fx-rev-1", orig="e1", commit="e2"),          # S8' only: the linked issue is bot-written
        _c(130, 3, "fx-rev-1", repo="gpl"),                      # S2: licence, so not in S3
        _c(140, 9, "fx-rev-1", repo="gone"),                     # no PR has this URL; its commit is in pr_commits
    ],
    "pr_commits": [  # file row order is the commit order
        {"sha": "c0", "pr_id": 10, "author": "Copilot", "committer": "web-flow", "message": "Initial plan"},
        {"sha": "d9", "pr_id": 10, "author": "Copilot", "committer": "web-flow", "message": "unrelated"},
        {"sha": "c1", "pr_id": 10, "author": "Copilot", "committer": "web-flow", "message": "implement"},
        {"sha": "c2", "pr_id": 10, "author": "Copilot", "committer": "web-flow",
         "message": "Address review\n\nCo-authored-by: fx-rev-1"},  # a human co-author is not an agent trailer
        {"sha": "c1", "pr_id": 10, "author": "Copilot", "committer": "web-flow", "message": "implement"},  # repeated row
        {"sha": "c3", "pr_id": 10, "author": "fx-rev-3", "committer": "fx-rev-3", "message": "manual tweak"},
        {"sha": "c4", "pr_id": 10, "author": "Copilot", "committer": "web-flow", "message": "final"},
        {"sha": "d1", "pr_id": 11, "author": "fx-author", "committer": "fx-author", "message": "start"},
        {"sha": "d2", "pr_id": 11, "author": "fx-author", "committer": "fx-author",
         "message": "fix\n\nCo-Authored-By: Claude"},
        {"sha": "d3", "pr_id": 11, "author": "fx-author", "committer": "fx-author", "message": "more"},
        {"sha": "e1", "pr_id": 16, "author": "Copilot", "committer": "web-flow", "message": "plan"},
        {"sha": "e2", "pr_id": 16, "author": "Copilot", "committer": "web-flow", "message": "done"},
    ],
    "related_issue": [{"pr_id": 10, "issue_id": 500, "source": "body"}, {"pr_id": 10, "issue_id": 501, "source": "timeline"},
                      {"pr_id": 16, "issue_id": 502, "source": "body"}],
    "issue": [{"id": 500, "number": 1, "title": "Add x", "body": "Please add x. @fx-rev-1 knows more.", "user": "fx-rev-1"},
              {"id": 501, "number": 2, "title": "CI", "body": "auto", "user": "github-actions[bot]"},
              {"id": 502, "number": 3, "title": "Plan", "body": "auto", "user": "Copilot"}],
}


@pytest.fixture
def population(tmp_path: Path) -> Path:
    d = tmp_path / "aidev"
    d.mkdir()
    for name, rows in TABLES.items():
        schema = pa.schema(list(SCHEMAS[name].items()))
        cols = {c: [r.get(c) for r in rows] for c in SCHEMAS[name]}
        pq.write_table(pa.table(cols, schema=schema), d / f"{name}.parquet")
    return d


def _stages(manifest: dict) -> dict:
    return {s["id"]: s for s in manifest["stages"]}


def _ids(con, table: str) -> set[int]:
    return {i for (i,) in con.execute(f"SELECT id FROM {table}").fetchall()}


def test_join_key_and_stage_rules(population):
    manifest, con = sa.screen(population)
    st = _stages(manifest)
    assert st["S1"]["count"] == 7 and st["S1"]["by_agent"]["Copilot"] == {"prs": 2}
    assert {p for (p,) in con.execute("SELECT pr_id FROM s2").fetchall()} == {10, 11, 16}  # licence, fork, language
    repo = manifest["checks"]["pr_to_repository"]
    assert (repo["matched_by_url"], repo["matched_by_repo_id"], repo["url_misses_that_pass_S2_by_repo_id"]) == (6, 7, 1)
    join = manifest["checks"]["comment_to_pr"]["all_comments"]
    assert (join["comments"], join["matched"], join["unmatched_pr_urls"]) == (19, 18, 1)
    assert join["unmatched_linkable_by_original_commit_sha"] == 1 and join["join_rows_beyond_one_per_comment"] == 0
    assert _ids(con, "s3") == {100, 101, 102, 104, 115, 105, 106, 107, 108, 109, 120, 116, 110, 111, 112, 113, 114}
    assert _ids(con, "s4") == {100, 105, 106, 107, 108, 109, 120, 116, 111, 112, 113, 114}
    assert st["S4"]["cumulative"] == {"user_type_user": 15, "and_thread_start": 14, "and_not_pr_author": 13}
    assert _ids(con, "s5") == {100, 108, 109, 120, 116, 111, 112, 113, 114}
    assert _ids(con, "s6") == {100, 109, 116, 111, 112, 113, 114}
    assert st["S6"]["branches"] == {"commit_id_differs": 5, "outdated_position": 2, "both": 0}
    assert _ids(con, "s7") == {100, 109, 116, 113, 114}
    later = dict(con.execute("SELECT id, later_sha FROM s7").fetchall())
    assert later == {100: "c2", 109: "c2", 116: "c3", 113: "d2", 114: "e2"}  # c3, not the repeated c1 row
    order = manifest["checks"]["commit_order"]
    assert (order["s6_commit_id_and_original_both_listed"], order["commit_id_after_original_in_row_order"]) == (4, 4)
    assert _ids(con, "s8") == {100, 109, 116}
    assert st["S8'"]["split"] == {"linked_non_bot_issue": 3, "linked_issue_without_non_bot_author": 1,
                                  "no_linked_issue": 1}
    assert _ids(con, "s8a") == {100, 109} and _ids(con, "s7a") == {100, 109, 113, 114}
    crit = st["S8a'"]["criteria"]
    assert (crit["bot_author"], crit["agent_trailer"]) == (3, 1)
    assert {p["label"]: p["comments"] for p in crit["trailer_patterns"]}["claude"] == 1
    assert st["S8a"]["criteria"]["agent_trailer"] == 0  # "Co-authored-by: <a person>" is not an agent trailer


def test_sample_rows_hold_ids_and_hashes_only(population, tmp_path):
    out, texts = tmp_path / "m.json", tmp_path / "work" / "texts.jsonl"
    assert sa.main(["--data", str(population), "--out", str(out), "--texts-out", str(texts)]) == 0
    m = json.loads(out.read_text())
    s = m["sample"]
    assert s["topped_up"] and s["pool_sizes"] == {"S8+S8a": 2, "S8-without-S8a": 1}
    assert [(r["comment_id"], r["pool"]) for r in s["rows"]] == [(100, "S8+S8a"), (109, "S8+S8a"), (116, "S8-without-S8a")]
    r100 = s["rows"][0]
    assert (r100["pr_id"], r100["repo_id"], r100["path"], r100["original_commit_id"], r100["commit_id"]) == \
        (10, 1, "pkg/a.py", "c1", "c2")
    assert (r100["later_commit_sha"], r100["issue_id"], r100["reviewer_is_issue_author"]) == ("c2", 500, True)
    assert r100["comment_body_sha256"] == hashlib.sha256(BODY_100.encode()).hexdigest()
    assert r100["issue_body_sha256"] == hashlib.sha256(b"Please add x. @fx-rev-1 knows more.").hexdigest()
    text = out.read_text()
    for secret in ("fx-rev-1", "fx-rev-3", "fx-author", "@", "keep the default", "Please add x"):
        assert secret not in text
    rows = [json.loads(x) for x in texts.read_text().splitlines()]
    t = rows[0]
    assert t["repo_url"] == "https://github.com/org/good" and t["path"] == "pkg/a.py"
    assert t["comment_body"] == "@agent keep the default, as reviewer asked; cc @user-1 and [profile link removed] " \
                                "([email removed])"
    assert t["issue_body"] == "Please add x. @reviewer knows more."
    assert "@property" in t["diff_hunk"] and t["pr_title"] == "Fix good for reviewer"
    assert all("fx-rev" not in json.dumps(r) for r in rows)
    out.write_text("")
    sa.main(["--data", str(population), "--out", str(out)])
    assert out.read_text() == text  # deterministic output


def test_texts_are_refused_inside_the_repository(population, tmp_path):
    with pytest.raises(SystemExit):
        sa.main(["--data", str(population), "--out", str(tmp_path / "m.json"),
                 "--texts-out", str(ROOT / "data" / "natural" / "texts.jsonl")])
    assert not (tmp_path / "m.json").exists()


def test_texts_are_refused_through_a_link_inside_the_repository(population, tmp_path, monkeypatch):
    """A --texts-out path inside the repository is refused even where a link there leads out of it (a data/natural
    linked from another checkout): resolving the link alone would let the texts through to the link's target."""
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    (repo / "data").mkdir(parents=True)
    outside.mkdir()
    (repo / "data" / "natural").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(sa, "R", repo)
    with pytest.raises(SystemExit):
        sa.main(["--data", str(population), "--out", str(tmp_path / "m.json"),
                 "--texts-out", str(repo / "data" / "natural" / "texts.jsonl")])
    assert not (tmp_path / "m.json").exists() and list(outside.iterdir()) == []
    assert not sa.inside_repository(outside / "texts.jsonl", repo)


def test_seeded_sample_is_deterministic():
    ids = list(range(1000, 4000, 3))
    a = sa.draw_sample(ids, [])
    assert a == sa.draw_sample(list(reversed(ids)), []) == sa.draw_sample(ids, [])
    assert [i for i, _ in a] == sorted(random.Random(20261121).sample(sorted(ids), 150))
    assert {p for _, p in a} == {"S8+S8a"} and sa.draw_sample(ids, [], seed=1) != a
    small = sa.draw_sample(ids[:10], ids[10:])  # fewer than 60: topped up to 150 from S8 without S8a
    assert len(small) == 150 and sum(p == "S8-without-S8a" for _, p in small) == 140
    assert small == sa.draw_sample(ids[:10], list(reversed(ids[10:])))
    assert sa.draw_sample(ids[:70], ids[70:]) == [(i, "S8+S8a") for i in ids[:70]]  # 60 or more: no top-up


def test_pseudonymizer_labels_and_code():
    ps = sa.Pseudonymizer({"fx-rev-1": "reviewer", "fx-author": "pr-author"}, {"fx-x"}, frozenset({"lint-bot[bot]"}))
    text = ("@FX-REV-1 and @fx-author: ask @lint-bot, @devin-ai-integration[bot] and @fx-new; fx-x agreed.\n"
            "+    @property\n+    @pytest.mark.slow\n+    @dataclass(frozen=True)\n"
            "see https://github.com/fx-x, https://github.com/org/fx-author/pull/2 and " + MAIL)
    assert ps(text) == ("@reviewer and @pr-author: ask @bot-1, @agent and @user-1; user-2 agreed.\n"
                        "+    @property\n+    @pytest.mark.slow\n+    @dataclass(frozen=True)\n"
                        "see [profile link removed], https://github.com/org/pr-author/pull/2 and [email removed]")
    assert ps(None) is None


def test_scan_flags_sampled_logins_and_manifest_handles(population, tmp_path, capsys):
    manifest = tmp_path / "screening.json"
    manifest.write_text(json.dumps({"sample": {"rows": [{"comment_id": 100}, {"comment_id": 116}]}}))
    logins = scan.aidev_logins(population, manifest)
    assert logins == ["fx-rev-1", "fx-rev-3"]
    pats = scan.login_patterns(logins)
    assert scan.scan_text("thanks FX-REV-3!\nfx-rev-10 and xfx-rev-1 differ", "f.md", [], pats) == 1
    assert scan.scan_text('{"x": "cc @someone"}', "data/manifests/m.json", [], handles=True) == 1
    assert scan.scan_text('"https://registry.npmjs.org/@scope/pkg", "git@github.com"', "data/manifests/m.json", [],
                          handles=True) == 0
    assert scan.scan_text('{"x": "cc @someone"}', "data/manifests/m.json", []) == 0  # the default scan is unchanged
    out = capsys.readouterr().out
    assert "aidev login #1" in out and "fx-rev" not in out and "someone" not in out


def _write_population(d: Path, tables: dict) -> Path:
    d.mkdir(parents=True)
    for name, rows in tables.items():
        schema = pa.schema(list(SCHEMAS[name].items()))
        pq.write_table(pa.table({c: [r.get(c) for r in rows] for c in SCHEMAS[name]}, schema=schema), d / f"{name}.parquet")
    return d


def test_scan_covers_every_person_connected_to_the_sampled_prs(tmp_path, capsys):
    """Issue authors, commit authors and committers, git author names and owners acting as accounts (D51)."""
    t = {k: list(v) for k, v in TABLES.items()}
    t["repository"] += [{**_repo(5, "tool"), "url": f"{API}fx-owner/tool"}, {**_repo(6, "lib"), "url": f"{API}fx-org/lib"}]
    t["pull_request"] += [{**_pr(18, 8, "tool", 5, "Copilot", "Copilot"), "repo_url": f"{API}fx-owner/tool"},
                          {**_pr(19, 9, "x", 4, "Devin", "fx-owner")},  # fx-owner acts as an account elsewhere
                          {**_pr(20, 10, "lib", 6, "Copilot", "Copilot"), "repo_url": f"{API}fx-org/lib"}]
    t["pr_review_comments"] += [{**_c(150, 8, "fx-rev-9"), "pull_request_url": f"{API}fx-owner/tool/pulls/8"},
                                {**_c(151, 10, "fx-rev-8"), "pull_request_url": f"{API}fx-org/lib/pulls/10"}]
    t["pr_commits"] += [{"sha": "f1", "pr_id": 10, "author": "Fx Name  Only", "committer": "fx-committer-only", "message": "m"}]
    t["related_issue"] += [{"pr_id": 10, "issue_id": 503, "source": "timeline"}]
    t["issue"] += [{"id": 503, "number": 4, "title": "Bug", "body": "it breaks", "user": "fx-issue-only"}]
    data = _write_population(tmp_path / "aidev", t)
    manifest = tmp_path / "screening.json"
    manifest.write_text(json.dumps({"sample": {"rows": [{"comment_id": 100}, {"comment_id": 150}, {"comment_id": 151}]}}))
    logins = scan.aidev_logins(data, manifest)
    assert logins == ["Fx Name Only", "fx-committer-only", "fx-issue-only", "fx-owner", "fx-rev-1", "fx-rev-3", "fx-rev-8",
                      "fx-rev-9"]  # no bot, agent, web committer or organisation (fx-org never acts as an account)
    pats = scan.login_patterns(logins)
    # The issue author of a sampled PR, who wrote no review comment, is reported.
    assert scan.scan_text("the bug was reported by FX-ISSUE-ONLY", "f.md", [], pats) == 1
    assert scan.scan_text("fx-issue-only-2 is another account; fx name\n only is cut by a line", "f.md", [], pats) == 0
    assert scan.scan_text("thanks to fx  name\tonly and fx-owner", "f.md", [], pats) == 2
    out = capsys.readouterr().out
    assert "fx-" not in out.lower() and out.count("aidev login #") == 3


def test_handles_are_checked_in_tasks_and_data_except_code(capsys):
    assert scan.handle_scope("tasks/CS-01/candidates/x.json") == (True, frozenset())
    assert scan.handle_scope("data/controlled/transcripts/CS-01.jsonl")[0] and not scan.handle_scope("docs/x.md")[0]
    assert scan.handle_scope("tasks/CS-04/labels/base_tests_overlay/tests/test_more.py")[1] == frozenset({"consumer"})
    code = ('@pytest.mark.parametrize("x", [1])\n@freeze_time("2020-02-02")\n@overload\n``@NAME@`` and @KILL_AT_SYNC@\n'
            '"https://registry.npmjs.org/@scope/pkg"\n+@pytest.mark.slow')
    assert scan.scan_text(code, "tasks/CS-01/x.json", [], handles=True) == 0
    assert scan.scan_text("    @mydecorator\n    def f(): pass", "tasks/x/t.py", [], handles=True, decorators=True) == 0
    assert scan.scan_text("    @mydecorator\n", "tasks/x/m.json", [], handles=True) == 1  # not a Python file
    assert scan.scan_text("# without @consumer, it raises", "t.py", [], handles=True, decorators=True,
                          allow=frozenset({"consumer"})) == 0
    assert scan.scan_text("# without @consumer, it raises", "t.py", [], handles=True, decorators=True) == 1
    assert scan.scan_text('{"note": "thanks @fx-someone"}', "data/x.json", [], handles=True) == 1
    assert "fx-someone" not in capsys.readouterr().out


def test_addresses_at_reserved_domains_are_not_findings(capsys):
    at = "@"
    for addr in (f"ann{at}example.org", f"x{at}mail.example.com", f"y{at}host.test", f"z{at}a.invalid"):
        assert scan.scan_text(f"from {addr}", "t.py", []) == 0, addr
    for addr in (f"ann{at}notexample.org", f"ann{at}example.org.evil.io"):  # an exact domain, not a suffix of a word
        assert scan.scan_text(f"from {addr}", "t.py", []) == 1, addr
    capsys.readouterr()
