"""Natural PR-review sessions from AIDev rows and a bare clone (src/tracecontract/ingest/github_pr.py; protocol §15.6).

* the session's events, their stable ids, kinds and authors: the issue (the initial request, by the user), the PR (by
  the agent, not user evidence), the PR's commits as the agent's actions, the comment's diff hunk (context) and the
  review comment and the same reviewer's later replies before the addressing commit (the correction);
* every text is pseudonymised: no login, @handle, e-mail address, person's profile account or model identifier
  remains, and the repository URL follows the {owner} rule;
* ``render_pr_thread`` for every reader of the session, behind its fixed banner, in the ``initial_only`` and
  ``full_session`` variants, with the comment and the replies labelled USER (tests/test_render_session.py has the
  rest);
* the bare clone: missing blobs are listed without fetching, fetched by id and logged, and the caps stop a fetch.

A synthetic world only (tests/natural_pr_world.py): fictional logins, git repositories made in a temporary
directory, fake AIDev tables. Not research evidence.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from natural_pr_world import MAIL_REV, MODEL_ID, build_world, forbidden
from tracecontract import natural_pr as npr
from tracecontract.contract import align_quote, validate_contract
from tracecontract.ingest.github_pr import (
    PR_THREAD_BANNER, AIDev, BareClone, CapExceeded, GitError, build_session, collect_thread, leftover_identifiers,
    make_pseudonymizer, render_pr_thread,
)
from tracecontract.schemas import (
    Author, ContractVariant, EventKind, Population, Requirement, RequirementKind, RequirementStatus, Session, TaskContract,
)

pytest.importorskip("duckdb")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return build_world(tmp_path_factory.mktemp("prworld"))


@pytest.fixture(scope="module")
def aidev(world):
    return AIDev(world.aidev, threads=1)


def _session(world, aidev, tid: str = "NP-01") -> tuple[Session, object]:
    fam = next(f for f in npr.load_families(world.qualifying) if f.task_id == tid)
    clone = BareClone(fam.bare_clone, repo_id=fam.repo_id, fetch_log=world.root / "fetch.jsonl")
    st = npr.resolve_states(fam, clone, [r["sha"] for r in aidev.pr_commits(fam.pr_id)])
    thread = collect_thread(aidev, clone, pr_id=fam.pr_id, comment_id=fam.comment_id, issue_id=fam.issue_id, base=st.base,
                            reviewed=st.reviewed, addressing=st.addressing, other_qualifying=fam.other_qualifying_comment_ids)
    ps, acts = make_pseudonymizer(thread, aidev.persons())
    url, _ = npr.masked_url(fam, aidev.persons())
    return build_session(thread, ps, repo_url=url, owner_masked=acts), ps


def test_events_have_stable_ids_kinds_and_authors(world, aidev):
    s, _ = _session(world, aidev)
    sh = world.shas
    sid = "aidev-pr-9001"
    assert s.session_id == sid and s.population == Population.natural_pr_review and s.source_revision == npr.AIDEV_REVISION
    assert [e.event_id for e in s.events] == [
        f"{sid}/issue", f"{sid}/pr", f"{sid}/commit/{sh['a1'][:12]}", f"{sid}/commit/{sh['a2'][:12]}", f"{sid}/review/8001/hunk",
        f"{sid}/review/8001", f"{sid}/reply/8102", f"{sid}/commit/{sh['a3'][:12]}"]
    kinds = [(e.kind, e.author) for e in s.events]
    assert kinds[0] == (EventKind.user_prompt, Author.human) and kinds[1] == (EventKind.assistant_text, Author.agent)
    assert kinds[4] == (EventKind.metadata, Author.tool) and kinds[5] == kinds[6] == (EventKind.user_prompt, Author.human)
    commits = [e for e in s.events if e.kind == EventKind.tool_call]
    assert all(e.tool_name == "git_commit" and e.author == Author.agent for e in commits)
    assert commits[-1].tool_input["sha"] == sh["a3"] and commits[-1].tool_input["parents"] == [sh["a2"]]
    ev = s.metadata["events"]
    assert ev["initial_request"] == f"{sid}/issue" and ev["correction"] == f"{sid}/review/8001"
    assert ev["reviewed_commit"].endswith(sh["a2"][:12]) and ev["addressing_commit"].endswith(sh["a3"][:12])
    assert set(s.metadata["not_user_evidence"]) == {f"{sid}/pr", f"{sid}/review/8001/hunk", *ev["commits"]}
    assert s.user_prompts()[0].event_id == f"{sid}/issue"  # the initial-only contract reads the first user prompt
    again, _ = _session(world, aidev)
    assert again.model_dump_json() == s.model_dump_json()  # stable ids and a stable trace checksum


def test_replies_are_the_reviewers_own_before_the_addressing_commit(world, aidev):
    s, _ = _session(world, aidev)
    assert s.metadata["aidev"]["reply_comment_ids"] == [8102]
    assert s.metadata["replies_excluded"] == {"other_authors": 1, "after_the_addressing_commit": 1}
    assert "late reply" not in s.model_dump_json() and "agreed" not in [e.text for e in s.events]


def test_every_text_is_pseudonymised(world, aidev):
    s, ps = _session(world, aidev)
    blob = s.model_dump_json().lower()
    assert not [x for x in forbidden() if x.lower() in blob]
    assert leftover_identifiers(s, ps) == []
    assert s.repo_url == "https://github.com/{owner}/{owner}-tools"  # the owner acts as an account in AIDev
    comment = s.event("aidev-pr-9001/review/8001").text
    assert comment.startswith("@user-") and "https://github.com/user-" in comment and "[email removed]" in comment
    assert "[model identifier removed]" in comment and "said so too" in comment and "Person" not in comment
    hunk = s.event("aidev-pr-9001/review/8001/hunk").text
    assert "+    return abs(a) + b" in hunk and "fx-author" not in hunk  # code kept, the login in it masked
    first = s.events[2].text
    assert "Co-authored-by: issue-author <[email removed]>" in first  # the trailer's login is the issue author
    counts = s.metadata["pseudonymisation"]["replacements"]
    assert counts["email"] >= 3 and counts["model_identifier"] >= 2 and counts["handle"] >= 2
    # An organisation keeps its name in the URL.
    s3, _ = _session(world, aidev, "NP-03")
    assert s3.repo_url == "https://github.com/fx-org/lib"


def test_leftover_identifiers_finds_what_a_pseudonymiser_missed(world, aidev):
    s, ps = _session(world, aidev)
    bad = s.model_copy(deep=True)
    bad.events[0].text += f" thanks fx-rev-1, write to {MAIL_REV} ({MODEL_ID})"
    found = leftover_identifiers(bad, ps)
    assert any("known login" in f for f in found) and any("e-mail" in f for f in found) and any("model" in f for f in found)
    assert all("fx-rev-1" not in f and MAIL_REV not in f for f in found)  # locations only


def test_the_agents_and_githubs_events_are_not_user_evidence(world, aidev):
    s, _ = _session(world, aidev)

    def req(event_id: str, quote: str) -> Requirement:
        span = align_quote(s, event_id, quote).span
        assert span is not None
        return Requirement(req_id="R1", statement="x", kind=RequirementKind.change, status=RequirementStatus.explicit,
                           introduced_at=event_id, evidence=[span], observable="a test", proposer="fixture")

    for eid, quote, flagged in (("aidev-pr-9001/pr", "Fix add for NP-01", True), ("aidev-pr-9001/issue", "Please fix add()", False),
                                ("aidev-pr-9001/review/8001", "this breaks negatives", False)):
        c = TaskContract(contract_id="c", task_id="NP-01", session_id=s.session_id, variant=ContractVariant.full_session,
                         requirements=[req(eid, quote)], created_by="fixture", created_at="2026-11-21T00:00:00+00:00")
        codes = {i.code for i in validate_contract(c, s)}
        assert ("non_user_evidence" in codes) == flagged, eid


def test_render_pr_thread_variants(world, aidev):
    s, _ = _session(world, aidev)
    first = render_pr_thread(s, "initial_only")
    full = render_pr_thread(s, ContractVariant.full_session)
    assert first.startswith(f"{PR_THREAD_BANNER}\n\n[aidev-pr-9001/issue] USER (linked issue: the initial request):\n"
                            "add() is wrong")
    assert first.count("\n[aidev-pr-9001/") == 1  # the issue alone
    assert "this breaks negatives" not in first and "Fix add for NP-01" not in first and "fxpkg/mod.py" not in first
    assert full.startswith(first.rstrip("\n"))
    for eid in ("aidev-pr-9001/review/8001/hunk", "aidev-pr-9001/review/8001", "aidev-pr-9001/reply/8102"):
        assert f"[{eid}]" in full
    assert ("[aidev-pr-9001/review/8001/hunk] DIFF HUNK under review in fxpkg/mod.py (GitHub's context for the comment; "
            "the agent's code, not the reviewer's words):\n```diff\n@@ -1,2 +1,3 @@") in full
    # The comment and the reply are the user's turns for the contract:v1 template ("as stated by the USER").
    assert ("\n[aidev-pr-9001/review/8001] USER (the reviewer: review comment on fxpkg/mod.py; the correction):\n"
            "@user-") in full
    assert ("\n[aidev-pr-9001/reply/8102] USER (the same reviewer: later reply in the same thread, before the addressing "
            "commit):\nAlso zero") in full
    assert "REVIEWER" not in full and "Fix add for NP-01" not in full and "/pr]" not in full and "/commit/" not in full
    assert full.index("review/8001]") < full.index("reply/8102]")
    with pytest.raises(ValueError):
        render_pr_thread(s, "reference")


def test_aidev_persons_and_bots(aidev):
    persons = aidev.persons()
    assert {"fx-rev-1", "fx-issuer", "fx-x", "fx-owner", "fx-stranger", "fx-author"} <= persons
    assert "fx-lint[bot]" not in persons and "fx-lint[bot]" in aidev.bots() and aidev.is_bot("fx-lint[bot]")
    assert [r["sha"] for r in aidev.pr_commits(9001)][0] == aidev.pr_commits(9001)[0]["sha"]


def _partial_clone(world, tmp_path) -> Path:
    src = world.root / "src" / "101"
    for k, v in (("uploadpack.allowFilter", "true"), ("uploadpack.allowAnySHA1InWant", "true")):
        subprocess.run(["git", "-C", str(src), "config", k, v], check=True)
    dest = tmp_path / "repos" / "201.git"
    dest.parent.mkdir(parents=True)
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none", f"file://{src}", str(dest)], check=True, env=env,
                   capture_output=True)
    return dest


def test_missing_blobs_are_listed_without_fetching_then_fetched_by_id_and_logged(world, tmp_path):
    dest = _partial_clone(world, tmp_path)
    log = tmp_path / "fetch.jsonl"
    clone = BareClone(dest, repo_id=201, fetch_log=log, allow_file_protocol=True, poll_s=0.05)
    base = world.shas["base101"]
    before = clone.size()
    missing = clone.missing(base)
    assert missing and clone.size() == before and not log.exists()  # listing fetches nothing
    lic = [o for m, t, o, p in clone.ls_tree(base) if p == "LICENSE"]
    assert clone.ensure(base, lic, label="licence") == 1
    text = clone.read(base, "LICENSE")
    assert text.startswith(b"MIT License") and clone.ensure(base, lic, label="again") == 0
    entries = [json.loads(ln) for ln in log.read_text().splitlines()]
    assert entries[0]["subcommand"] == "fetch" and entries[0]["repo_id"] == 201 and entries[0]["delta"] > 0
    assert entries[0]["label"] == "licence (1 blobs)" and entries[0]["killed"] is None
    assert "url" not in json.dumps(entries) and "fx-owner" not in json.dumps(entries)  # repository ids only
    # The default refuses a local remote: the promisor remote of a real clone is GitHub over HTTPS.
    with pytest.raises(GitError):
        BareClone(dest, repo_id=201, fetch_log=log).fetch_blobs(sorted(clone.missing(base))[:1], label="x")


def test_the_caps_stop_a_fetch(world, tmp_path):
    dest = _partial_clone(world, tmp_path)
    base = world.shas["base101"]
    small = BareClone(dest, repo_id=201, allow_file_protocol=True, repo_cap=10)
    with pytest.raises(CapExceeded, match="repository cap"):
        small.fetch_blobs(sorted(small.missing(base)), label="all")
    total = BareClone(dest, repo_id=201, allow_file_protocol=True, total_cap=1, repos_root=tmp_path / "repos")
    with pytest.raises(CapExceeded, match="total cap"):
        total.fetch_blobs(sorted(total.missing(base)), label="all")
    with pytest.raises(CapExceeded):
        BareClone(dest, repo_id=201, allow_fetch=False).blob(sorted(small.missing(base))[0])
    with pytest.raises(GitError):
        BareClone(tmp_path / "nowhere.git")
