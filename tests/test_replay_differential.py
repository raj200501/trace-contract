"""Differential tests: the reconstruction check and the transcript replay on the same sessions (D47, D51).

``tracecontract.reconstruction`` and ``tracecontract.ingest.replay`` replay a session's edits
independently, for different purposes; both now apply edits through one function
(``tracecontract.ingest.edit_tool``). Each fixture below is run through both. They must agree
wherever both claim to know a file's content, and on the cases a verification found them to
disagree: a deletion edit, curly quotes, an occurrence count, a restore that keeps a created
file, and the e-mail redaction of a sanitised controlled transcript.

Every session, base and state here is a synthetic fixture (population ``fixture``, or a
controlled-layout fixture written under ``tmp_path``); the workspace ``/ws/fixture-repo`` is a
string in the transcripts, not a real directory. None is research data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracecontract.ingest.claude_code import _redact_emails, parse_claude_code_jsonl
from tracecontract.ingest.edit_tool import apply_edit, apply_edits, edits_of, preserve_quote_style
from tracecontract.ingest.replay import compare_files, load_raw_extras, replay_controlled, replay_session
from tracecontract.patches import diff_dirs
from tracecontract.reconstruction import check_reconstruction
from tracecontract.schemas import Candidate, CandidateOrigin, Population, SnapshotSource, Split, TaskManifest, sha256_text
from tracecontract.snapshot import post_images
from tracecontract.store import dump

WS = "/ws/fixture-repo"
Call = tuple[str, dict, str, bool]  # tool, input, result text, is_error


def _tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    return root


def _jsonl(path: Path, calls: list[Call], sid: str = "FX-diff") -> Path:
    rows = [{"type": "user", "sessionId": sid, "uuid": "p0", "cwd": WS, "message": {"role": "user", "content": "Do it."}}]
    for k, (tool, inp, res, err) in enumerate(calls):
        rows.append({"type": "assistant", "sessionId": sid, "uuid": f"a{k}", "cwd": WS, "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": f"t{k}", "name": tool, "input": inp}]}})
        rows.append({"type": "user", "sessionId": sid, "uuid": f"r{k}", "cwd": WS, "message": {
            "role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{k}", "content": res, "is_error": err}]}})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _edit(rel: str, old: str, new: str, *, replace_all: bool = False) -> Call:
    return ("Edit", {"file_path": f"{WS}/{rel}", "old_string": old, "new_string": new, "replace_all": replace_all},
            f"The file {WS}/{rel} has been updated successfully.", False)


def _read(rel: str, text: str) -> Call:
    return ("Read", {"file_path": f"{WS}/{rel}"}, "\n".join(f"{n}\t{x}" for n, x in enumerate(text.split("\n"), 1)), False)


def _both(tmp_path: Path, base_files: dict[str, str], final_files: dict[str, str], calls: list[Call]):
    """Run both replays on one fixture: ``(reconstruction report, replay result, compare_files of the final state)``."""
    base = _tree(tmp_path / "base", base_files)
    final = _tree(tmp_path / "final", final_files)
    path = _jsonl(tmp_path / "s.jsonl", calls)
    session = parse_claude_code_jsonl(path, population=Population.fixture, source="fixture", scripted_turns=["Do it."])
    patch = diff_dirs(base, final)
    rep = check_reconstruction(task_id="FX", session=session, base=base, workspace_root=WS, final_patch=patch)
    res = replay_session(session, base=base, root=WS, extras=load_raw_extras(path))
    expected = {k: (None if v is None else v.decode("utf-8")) for k, v in post_images(patch, base).items()}
    return rep, res, compare_files(res, expected, base)


def _final_items(rep) -> dict[str, str]:
    return {i["path"]: i["status"] for i in rep.check("f_replay_matches_states").items
            if i.get("kind") == "state" and i.get("state") == "final"}


def _agree(rep, verdicts: dict[str, dict]) -> None:
    """Where both replays know a file's final content, they agree about it."""
    for path, status in _final_items(rep).items():
        v = verdicts.get(path)
        if v is None or v["status"] == "unknown" or status == "not_checkable":
            continue
        assert (status == "passed") == (v["verdict"] == "match"), (path, status, v)


CASES = {
    # An empty new_string also removes the line break the tool removes.
    "deletion": ({"a.py": "keep\ndrop\nkeep2\n"}, {"a.py": "keep\nkeep2\n"}, [_edit("a.py", "drop", "")]),
    # Only the occurrences followed by a line break lose it, as with the tool's replaceAll.
    "deletion_replace_all": ({"a.py": "x = 1\nprint(x)\nx"}, {"a.py": "print(x)\nx"},
                             [_edit("a.py", "x = 1", "", replace_all=True)]),
    # Curly quotes in the file, straight ones in old_string: the tool matches them and writes
    # new_string in the file's curly style.
    "curly_quotes": ({"a.py": "s = “hi”\n"}, {"a.py": "s = “yo”\n"}, [_edit("a.py", 's = "hi"', 's = "yo"')]),
    # 'aa' occurs once in 'aaa' as the tool (and str.count) counts it, so the edit is unique.
    "overlapping_count": ({"a.py": "x = 'aaa'\n"}, {"a.py": "x = 'ba'\n"}, [_edit("a.py", "aa", "b")]),
    "multi_edit": ({"a.py": "a = 1\nb = 2\n"}, {"a.py": "a = 10\nb = 20\n"},
                   [("MultiEdit", {"file_path": f"{WS}/a.py", "edits": [{"old_string": "a = 1", "new_string": "a = 10"},
                                                                         {"old_string": "b = 2", "new_string": "b = 20"}]},
                     "Applied 2 edits.", False)]),
    "write_then_edit": ({"a.py": "A = 1\n"}, {"a.py": "A = 1\n", "new.py": "N = 2\n"},
                        [("Write", {"file_path": f"{WS}/new.py", "content": "N = 1\n"}, "File created successfully at: x", False),
                         _edit("new.py", "N = 1", "N = 2")]),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_both_replays_reproduce_the_tools_edits(tmp_path, name):
    base, final, calls = CASES[name]
    rep, res, verdicts = _both(tmp_path, base, final, calls)
    _agree(rep, verdicts)
    assert rep.check("f_replay_matches_states").status == "passed", rep.check("f_replay_matches_states").items
    assert rep.check("b_first_edit_strings").status == "passed", rep.check("b_first_edit_strings").items
    assert rep.status == "passed" or rep.check("c_reads_match_base").status == "not_checkable"
    assert {v["verdict"] for v in verdicts.values()} == {"match"}, verdicts
    assert res.fidelity.value in ("exact", "approximate")


def test_normalised_matches_are_flagged_by_both(tmp_path):
    base, final, calls = CASES["curly_quotes"]
    rep, res, _ = _both(tmp_path, base, final, calls)
    assert rep.check("b_first_edit_strings").items[0]["quote_normalised"] is True
    assert any("quote_normalised" in a for a in rep.check("f_replay_matches_states").approximations)
    assert res.status["a.py"] == "approximate" and res.fidelity.value == "approximate"
    assert "1 edit(s) matched only after quote normalisation" in res.reasons
    # The file's own status and reason, not the wording for recovered content (no originalFile, no Read).
    assert not any("recovered from originalFile" in r for r in res.reasons)
    assert any("matched only after normalisation" in r for r in res.reasons)


def test_crlf_files_follow_the_tools_line_endings(tmp_path):
    """The tool matches LF line breaks in a CRLF file and writes CRLF back; both replays agree on the result.

    Checked through a later Read and a given expected state: a patch of a CRLF file made by
    ``patches.diff_dirs`` loses its CRs, so the captured-state comparison cannot be used here.
    """
    base = _tree(tmp_path / "base", {"a.py": "a = 1\r\nb = 2\r\n"})
    calls = [_edit("a.py", "a = 1\nb", "a = 3\nb"), _read("a.py", "a = 3\nb = 2\n")]
    path = _jsonl(tmp_path / "s.jsonl", calls)
    session = parse_claude_code_jsonl(path, population=Population.fixture, source="fixture", scripted_turns=["Do it."])
    rep = check_reconstruction(task_id="FX", session=session, base=base, workspace_root=WS, final_patch=None)
    assert rep.check("b_first_edit_strings").status == "passed"
    f = rep.check("f_replay_matches_states")
    assert [(i["kind"], i["status"]) for i in f.items] == [("read", "passed"), ("state", "not_checkable")]
    assert any("line_endings_converted" in a for a in f.approximations)
    res = replay_session(session, base=base, root=WS, extras=load_raw_extras(path))
    assert res.files == {"a.py": "a = 3\r\nb = 2\r\n"} and res.status["a.py"] == "approximate"
    assert res.counts["line_endings_converted"] == 1 and res.counts["read_matches"] == 1
    assert compare_files(res, {"a.py": "a = 3\r\nb = 2\r\n"}, base)["a.py"]["verdict"] == "match"


def test_a_refused_edit_is_flagged_by_both(tmp_path):
    calls = [_edit("a.py", "x = 1", "x = 2")]
    rep, res, verdicts = _both(tmp_path, {"a.py": "x = 1\nx = 1\n"}, {"a.py": "x = 2\nx = 1\n"}, calls)
    assert rep.status == "failed" and rep.check("b_first_edit_strings").items[0]["old_occurrences"] == 2
    assert res.counts["old_string_not_unique"] == 1 and res.status["a.py"] == "unknown"
    assert verdicts["a.py"]["verdict"] == "differs"


@pytest.mark.parametrize("command", ["git checkout -- .", "git stash", "git reset --hard"])
def test_restores_keep_the_files_the_session_created(tmp_path, command):
    # git resets tracked files only: new.py stays, a.py is back to the base.
    calls = [("Write", {"file_path": f"{WS}/new.py", "content": "N = 1\n"}, "File created successfully at: x", False),
             _edit("a.py", "A = 1", "A = 2"),
             ("Bash", {"command": f"cd {WS} && {command}"}, "ok", False),
             _read("new.py", "N = 1")]
    rep, res, verdicts = _both(tmp_path, {"a.py": "A = 1\n"}, {"a.py": "A = 1\n", "new.py": "N = 1\n"}, calls)
    assert _final_items(rep) == {"a.py": "passed", "new.py": "passed"}
    assert rep.check("f_replay_matches_states").status == "passed" and rep.check("c_reads_match_base").status != "failed"
    # The transcript replay does not model restores: it loses both files and claims nothing stale.
    assert res.status == {"a.py": "unknown", "new.py": "unknown"} and res.fidelity.value == "unreconstructable"
    _agree(rep, verdicts)


def test_both_apply_the_sanitisers_redaction(tmp_path):
    """A sanitised controlled transcript shows e-mail addresses redacted; both replays redact the base the same way."""
    base_text = "__author__ = 'Ann <ann@example.org>'\nA = 1\n"
    final_text = base_text.replace("A = 1", "A = 2")
    shown = _redact_emails(base_text, {})
    assert "[EMAIL REDACTED]" in shown
    calls = [_read("a.py", shown.rstrip("\n")), _edit("a.py", "A = 1", "A = 2")]
    rep, _, _ = _both(tmp_path, {"a.py": base_text}, {"a.py": final_text}, calls)
    assert {c.check_id: c.status for c in rep.checks if c.check_id[0] in "abcf"} == {
        "a_written_files_changed": "passed", "b_first_edit_strings": "passed", "c_reads_match_base": "passed",
        "f_replay_matches_states": "passed"}

    # replay_controlled on the same session, laid out as a controlled task under tmp_path.
    repo, tid = tmp_path / "repo", "FX-CTL"
    base = _tree(repo / "snapshots" / tid, {"a.py": base_text})
    pre = _tree(tmp_path / "pre", {"a.py": final_text})
    _jsonl(repo / "data" / "controlled" / "transcripts" / f"{tid}.jsonl", calls, sid=f"{tid}-session")
    patch = diff_dirs(base, pre)
    td = repo / "tasks" / tid
    dump(Candidate(candidate_id=f"{tid}-pre-correction", task_id=tid, origin=CandidateOrigin.observed_pre_correction,
                   split=Split.eval, patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture"),
         td / "candidates" / f"{tid}-pre-correction.json")
    dump(TaskManifest(task_id=tid, family_id=tid, population=Population.controlled, status="draft", provenance="provenance.json",
                      snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture", commit="0" * 40),
                      env_requirements=[], scripted_turns=["Do it."], candidates=[f"candidates/{tid}-pre-correction.json"]),
         td / "task.json")
    out = replay_controlled(td, repo, repo / "snapshots")
    assert out["replay"]["fidelity"] == "exact" and out["differs"] == [] and out["matches"] == ["a.py"]
    assert out["replay"]["counts"]["read_matches"] == 1


def test_the_shared_edit_function_follows_the_tool():
    assert apply_edit("aaa", "aa", "b") == ("ba", None)  # one occurrence as str.count counts
    assert apply_edit("x\nx", "x", "", replace_all=True) == ("x", None)  # only 'x\n' loses its line break
    assert apply_edit("  \n", "", "new\n") == ("new\n", None)  # an empty old_string fills a whitespace-only file
    assert apply_edit("x = 1\n", "", "y") == (None, "file_exists")
    # Only the quote kinds the file's text uses become curly; an apostrophe inside a word closes.
    assert preserve_quote_style('say "hi"', "say “hi”", 'say "it\'s"') == "say “it's”"
    assert preserve_quote_style("'a' b", "‘a’ b", "'c' (d) don't") == "‘c’ (d) don’t"
    assert preserve_quote_style("same", "same", '"x"') == '"x"'
    out = apply_edits("a\r\nb\r\n", [("a\nb", "c\nd", False), ("zzz", "y", False)])
    assert out.text is None and out.problem == "absent" and out.failed_at == 1
    assert edits_of("MultiEdit", {"edits": [{"old_string": "a", "new_string": "b"}, "junk"]}) == [("a", "b", False)]
    assert edits_of("Edit", {"old_string": "a", "new_string": "b", "replace_all": True}) == [("a", "b", True)]
