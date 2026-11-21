"""Transcript replay (decision log D47): edit semantics, the transcript checks, shell writes,
commit evidence, and the replays of the four controlled sessions.

Synthetic sessions here are fixtures (population fixture); they test code behaviour only.
The controlled replays need the base snapshots (``tracecontract snapshot``); they are skipped
when a snapshot is missing or does not match its recorded manifest hash.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.ingest.replay import (
    PathMap, apply_edit, compare_files, infer_root, load_raw_extras, replay_controlled, replay_session, second_user_prompt,
)
from tracecontract.ingest.repo_evidence import commit_evidence, raw_entries
from tracecontract.ingest.shell_writes import shell_writes
from tracecontract.schemas import Fidelity, Population
from tracecontract.tasks import verify_snapshot

R = Path(__file__).resolve().parents[1]
ROOT = "/w/repo"


class Transcript:
    """Builds a small Claude Code JSONL transcript with tool calls and their results."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.n = 0

    def user(self, text: str) -> "Transcript":
        self.rows.append({"type": "user", "sessionId": "S", "cwd": ROOT, "message": {"role": "user", "content": text}})
        return self

    def call(self, name: str, inp: dict, result: str = "ok", *, error: bool = False, tur: object = None) -> "Transcript":
        self.n += 1
        tid = f"t{self.n}"
        self.rows.append({"type": "assistant", "sessionId": "S", "cwd": ROOT, "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}})
        row = {"type": "user", "sessionId": "S", "cwd": ROOT, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tid, "content": result, "is_error": error}]}}
        if tur is not None:
            row["toolUseResult"] = tur
        self.rows.append(row)
        return self

    def edit(self, path: str, old: str, new: str, **kw) -> "Transcript":
        return self.call("Edit", {"file_path": f"{ROOT}/{path}", "old_string": old, "new_string": new, **kw},
                         f"The file {ROOT}/{path} has been updated successfully.")

    def write(self, tmp: Path):
        p = tmp / "t.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in self.rows) + "\n")
        return parse_claude_code_jsonl(p, population=Population.fixture, source="fixture"), load_raw_extras(p), p


def test_apply_edit_matches_the_edit_tool():
    assert apply_edit("a = 1\nb = 2\n", "a = 1", "a = 3") == ("a = 3\nb = 2\n", None)
    assert apply_edit("x\nx\n", "x", "y") == (None, "not_unique")
    assert apply_edit("x\nx\n", "x", "y", replace_all=True) == ("y\ny\n", None)
    assert apply_edit("abc", "zzz", "y") == (None, "absent")
    assert apply_edit(None, "", "new file\n") == ("new file\n", None)
    assert apply_edit("keep\ndrop\nkeep2\n", "drop", "") == ("keep\nkeep2\n", None)  # the line break goes too
    assert apply_edit("say \u201chi\u201d", 'say "hi"', 'say "yo"') == ('say "yo"', "quote_normalised")


def test_exact_replay_with_checks(tmp_path):
    base = {"pkg/a.py": "def f():\n    return 1\n"}
    t = (Transcript().user("Make f return 2.")
         .call("Read", {"file_path": f"{ROOT}/pkg/a.py"}, "1\tdef f():\n2\t    return 1\n")
         .edit("pkg/a.py", "return 1", "return 2")
         .call("Write", {"file_path": f"{ROOT}/pkg/b.py", "content": "B = 1\n"}, "File created successfully")
         .call("Read", {"file_path": f"{ROOT}/pkg/a.py"}, "1\tdef f():\n2\t    return 2\n")
         .call("Bash", {"command": f"cd {ROOT} && python -m pytest -q && git status"}, "1 passed"))
    s, ex, _ = t.write(tmp_path)
    r = replay_session(s, base=base, extras=ex)
    assert r.fidelity == Fidelity.exact and r.reasons == []
    assert r.files == {"pkg/a.py": "def f():\n    return 2\n", "pkg/b.py": "B = 1\n"}
    assert r.counts["read_checks"] == 2 and r.counts["read_matches"] == 2 and r.changed == ["pkg/a.py", "pkg/b.py"]
    verdicts = compare_files(r, {"pkg/a.py": "def f():\n    return 2\n", "pkg/b.py": "B = 1\n"}, base)
    assert {v["verdict"] for v in verdicts.values()} == {"match"}


def test_non_unique_old_string_is_unreconstructable(tmp_path):
    s, ex, _ = Transcript().user("Rename x.").edit("a.py", "x = 1", "x = 2").write(tmp_path)
    r = replay_session(s, base={"a.py": "x = 1\nx = 1\n"}, extras=ex)
    assert r.counts["old_string_not_unique"] == 1 and r.status["a.py"] == "unknown"
    assert r.fidelity == Fidelity.unreconstructable
    assert any("not unique" in x for x in r.reasons) and any("unknown post-image" in x for x in r.reasons)
    s2, ex2, _ = Transcript().user("Rename x.").edit("a.py", "x = 1", "x = 2", replace_all=True).write(tmp_path)
    assert replay_session(s2, base={"a.py": "x = 1\nx = 1\n"}, extras=ex2).files == {"a.py": "x = 2\nx = 2\n"}


def test_absent_old_string_and_failed_edits(tmp_path):
    t = (Transcript().user("Edit.")
         .call("Edit", {"file_path": f"{ROOT}/a.py", "old_string": "nope", "new_string": "x"},
               "<tool_use_error>String to replace not found in file.</tool_use_error>", error=True)
         .edit("a.py", "missing", "x"))
    s, ex, _ = t.write(tmp_path)
    r = replay_session(s, base={"a.py": "v = 1\n"}, extras=ex)
    assert r.counts["edit_error"] == 1  # a failed edit is not applied
    assert r.counts["old_string_absent"] == 1 and r.fidelity == Fidelity.unreconstructable


def test_bash_edit_is_detected_and_confirmed_by_a_read(tmp_path):
    t = (Transcript().user("Bump the version.")
         .call("Bash", {"command": f"cd {ROOT} && sed -i 's/1/2/' v.py && git diff --stat"}, " v.py | 2 +-")
         .call("Read", {"file_path": f"{ROOT}/v.py"}, "1\tVERSION = 2\n"))
    s, ex, _ = t.write(tmp_path)
    r = replay_session(s, base={"v.py": "VERSION = 1\n"}, extras=ex)
    assert [(f.check, f.path, f.detail) for f in r.findings][:1] == [("shell_write", "v.py", "sed -i")]
    assert r.status["v.py"] == "unknown" and r.fidelity == Fidelity.unreconstructable
    t2 = Transcript().user("x").call("Bash", {"command": "cd /w/repo && python3 - <<'EOF'\nimport pathlib\n"
                                              "pathlib.Path('v.py').write_text('VERSION = 3\\n')\nEOF"})
    r2 = replay_session(t2.write(tmp_path)[0], base={"v.py": "VERSION = 1\n"}, extras=t2.write(tmp_path)[1])
    assert r2.findings[0].check == "shell_write" and r2.findings[0].detail == "interpreter"


def test_heredoc_copy_and_delete_are_replayed(tmp_path):
    cmd = (f"cd {ROOT} && cat > gen.py <<'EOF'\nX = 1\nEOF\ncp gen.py copy.py && rm old.py && echo done > /tmp/log.txt")
    s, ex, _ = Transcript().user("x").call("Bash", {"command": cmd}).write(tmp_path)
    r = replay_session(s, base={"old.py": "gone\n"}, extras=ex)
    assert r.files == {"gen.py": "X = 1\n", "copy.py": "X = 1\n", "old.py": None}
    assert r.fidelity == Fidelity.exact and r.counts["shell_write_outside_root"] == 1


def test_original_file_is_checked_and_recovered(tmp_path):
    t = (Transcript().user("x")
         .call("Edit", {"file_path": f"{ROOT}/a.py", "old_string": "b", "new_string": "c"}, "updated",
               tur={"originalFile": "a\nb\n", "userModified": False})
         .call("Edit", {"file_path": f"{ROOT}/a.py", "old_string": "c", "new_string": "d"}, "updated",
               tur={"originalFile": "a\nc\nEXTRA\n"}))  # changed outside the replayed calls in between
    s, ex, _ = t.write(tmp_path)
    r = replay_session(s, base={"a.py": "a\nb\n"}, extras=ex)
    assert r.counts["original_file_checks"] == 2 and r.counts["original_file_matches"] == 1
    assert r.counts["original_file_mismatch"] == 1 and r.files["a.py"] == "a\nd\nEXTRA\n"
    assert r.fidelity == Fidelity.approximate and r.status["a.py"] == "recovered"
    # Without a base tree, originalFile recovers the file's content but not the repository.
    r2 = replay_session(s, extras=ex)
    assert r2.counts["recovered_from_original_file"] == 1 and r2.fidelity == Fidelity.unreconstructable
    assert r2.reasons[0].startswith("no base tree")


def test_read_mismatch_and_absent_file(tmp_path):
    t = (Transcript().user("x")
         .call("Read", {"file_path": f"{ROOT}/a.py"}, "1\tsomething else\n")
         .call("Read", {"file_path": f"{ROOT}/missing.py"}, "1\tx = 1\n"))
    s, ex, _ = t.write(tmp_path)
    r = replay_session(s, base={"a.py": "a = 1\n"}, extras=ex, root=ROOT)
    assert r.counts["read_mismatch"] == 1 and r.counts["read_absent_from_base"] == 1
    assert r.changed == [] and r.fidelity == Fidelity.unreconstructable


def test_commit_tree_comparison(tmp_path):
    s, ex, _ = Transcript().user("x").edit("a.py", "1", "2").write(tmp_path)
    base = {"a.py": "v = 1\n", "b.py": "w\n"}
    assert replay_session(s, base=base, extras=ex, commit_tree={"a.py": "v = 2\n", "b.py": "w\n"}).fidelity == Fidelity.exact
    bad = replay_session(s, base=base, extras=ex, commit_tree={"a.py": "v = 3\n", "b.py": "w\n"})
    assert bad.fidelity == Fidelity.unreconstructable and bad.counts["commit_tree_mismatches"] == 1


def test_stop_before_second_prompt_and_subagents(tmp_path):
    t = (Transcript().user("First.").edit("a.py", "1", "2").user("Actually, no.")
         .edit("a.py", "2", "3").call("Agent", {"subagent_type": "general-purpose", "prompt": "p"}))
    s, ex, _ = t.write(tmp_path)
    stop = second_user_prompt(s)
    assert replay_session(s, base={"a.py": "1"}, extras=ex, stop_before=stop).files == {"a.py": "2"}
    full = replay_session(s, base={"a.py": "1"}, extras=ex)
    assert full.files == {"a.py": "3"} and full.counts["subagent_unseen_edits"] == 1 and full.fidelity == Fidelity.approximate


def test_windows_paths_and_root_inference(tmp_path):
    pm = PathMap("d:/Proj")
    assert pm.rel("D:\\Proj\\src\\A.c") == "src/a.c" and pm.rel("/d/proj/src/a.c") == "src/a.c"
    assert pm.rel("/mnt/d/Proj/x.h") == "x.h" and pm.rel("C:\\other\\x.c") is None
    s, _, _ = Transcript().user("x").edit("src/m.py", "a", "b").write(tmp_path)
    assert infer_root(s, base_files={"src/m.py"}) == ROOT


@pytest.mark.parametrize("cmd,shell,want", [
    ("echo hi > out.txt 2>&1", "Bash", [("redirect", "out.txt")]),
    ("tee -a log.txt < x", "Bash", [("tee", "log.txt")]),
    ("sed -i 's/a/b/' f.py", "Bash", [("sed -i", "f.py")]),
    ("mv a.py b.py", "Bash", [("mv", "b.py"), ("mv source", "a.py")]),
    ("python -c \"open('d.json', 'w').write('{}')\"", "Bash", [("interpreter", "d.json")]),
    ("git checkout -- a.py", "Bash", [("git checkout", "a.py")]),
    ("git apply fix.patch", "Bash", [("git apply", None)]),
    ("Set-Content -Path a.txt -Value x", "PowerShell", [("set-content", "a.txt")]),
    ("git status && git diff --stat && git log --oneline -3", "Bash", []),
    ("ruff format --check . && black --version && cat f.py | grep x", "Bash", []),
    ("./run_python.sh - <<'EOF'\nopen('/repo/a.py', 'w')\nEOF", "Bash", []),  # a read-only sandbox wrapper
])
def test_shell_writes(cmd, shell, want):
    got = shell_writes(cmd, shell=shell, sandboxed=("run_python.sh",))
    assert [(w.kind, w.target) for w in got] == want


def test_commit_evidence_from_git_output(tmp_path):
    t = (Transcript().user("x")
         .call("Bash", {"command": "git status"}, "On branch main\nnothing to commit, working tree clean")
         .call("Bash", {"command": "git log --oneline -3"}, "abc1234 Fix\n0123456 Start")
         .call("Bash", {"command": "git remote -v"}, "origin\thttps://github.com/[USER]/proj.git (fetch)")
         .edit("a.py", "1", "2")
         .call("Bash", {"command": "git commit -am 'x'"}, "[main 89abcde] x\n 1 file changed"))
    s, ex, p = t.write(tmp_path)
    ev = commit_evidence(s, ex, raw_entries(p, "pr-link"), root=ROOT)
    assert ev.head_shas == ["abc1234"] and ev.clean_tree is True and ev.commits_made == ["89abcde"]
    assert not ev.repo_identified and ev.status == "commit_seen_repository_unidentified"  # a redacted owner
    t.call("Bash", {"command": "git fetch origin"}, "From https://github.com/octo-org/proj\n * branch main")
    ev2 = commit_evidence(*t.write(tmp_path)[:2], root=ROOT)
    assert ev2.repo_identified and ev2.status == "pinnable_unverified" and ev2.cwd_matches_repo is False
    assert ev2.repo_sha256 and "octo" not in json.dumps(ev2.summary())  # only a hash of the identity


CONTROLLED = ("CS-01", "CS-02", "CS-03", "CS-04")


@pytest.mark.parametrize("tid", CONTROLLED)
def test_controlled_replay_reproduces_the_pre_correction_state(tid):
    snap = R / "snapshots"
    if not (snap / tid).is_dir() or not verify_snapshot(R / "tasks" / tid, snap):
        pytest.skip(f"base snapshot of {tid} missing or stale (tracecontract snapshot tasks/{tid})")
    out = replay_controlled(R / "tasks" / tid, R, snap)
    if tid == "CS-01":
        # A python heredoc (L000067) rewrote tests/test_filesize.py; the replay cannot know the result.
        assert out["differs"] == ["tests/test_filesize.py"] and len(out["matches"]) == 3
        assert "shell_write at L000067.00 (interpreter)" in out["files"]["tests/test_filesize.py"]["reason"]
        assert out["replay"]["fidelity"] == "unreconstructable"
    else:
        assert out["differs"] == [] and out["replay"]["fidelity"] == "exact"
        assert all(v["status"] == "exact" for v in out["files"].values())
