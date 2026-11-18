"""The strict re-audit of generator transcripts resolves paths instead of matching substrings (D44)."""

from __future__ import annotations

import json
from pathlib import Path

from tracecontract.controlled import audit_generator_transcript_strict

REPO = "/home/user/trace-contract"
OWN = "/home/user/gen_workspaces/CS-01/eval-nm"
SCRATCH = "/tmp/scratch-of-the-builder"

# (command or tool input, expected to be flagged)
CASES = [
    ({"command": "cat tasks/CS-01/verifiers/full_plain/tests/test_a.py"}, True),
    ({"command": ".venv/bin/tracecontract add-candidate tasks/CS-01 x --patch p.diff && cat tasks/CS-01/verifiers/c1/spec.json"}, True),
    ({"command": ".venv/bin/tracecontract add-candidate tasks/CS-01 x --patch tasks/CS-01/candidates/p.diff"}, False),
    ({"command": "cd tasks && grep -rn naturalsize ."}, True),
    ({"command": "grep -rn naturalsize src/ tests/"}, False),
    ({"command": "find . -path ./tasks -prune -o -path ./results -prune -o -path ./data -prune -o -path ./docs -prune -o -name '*.py' -print"}, False),
    ({"command": "find . -path ./tasks -prune -o -name '*.py' -print"}, True),  # results/, data/ and docs/ are searched
    ({"command": "W=/home/user/gen_workspaces/CS-01/eval-alt-1; cat $W/base/x.py"}, True),
    ({"command": f"cd {OWN} && cp -r base nm1 && cat nm1/src/humanize/filesize.py"}, False),
    # A path named only in a heredoc body is reported too (as a mention to assess), since such
    # bodies are often code that an interpreter runs.
    ({"command": "cat > /tmp/notes.txt <<'EOF'\nsee tasks/CS-01/verifiers/c1 and results/\nEOF"}, True),
    ({"command": f"ls {SCRATCH}"}, True),
    ({"file_path": f"{REPO}/docs/annotation_guide.md"}, True),
    ({"file_path": f"{OWN}/contract.json"}, False),
    ({"command": "ls -la ~/gen_workspaces/CS-01/"}, True),
    ({"command": "cat ~/gen_workspaces/CS-02/eval-nm/x.py"}, False),  # another task's workspace is not this task's material
]


def _transcript(path: Path, inputs: list[dict]) -> None:
    rows = [{"type": "user", "uuid": "u0", "parentUuid": None, "sessionId": "s", "timestamp": "2026-01-01T00:00:00Z",
             "message": {"role": "user", "content": "go"}}]
    for i, ti in enumerate(inputs):
        tool = "Read" if "file_path" in ti else "Bash"
        rows.append({"type": "assistant", "uuid": f"a{i}", "parentUuid": "u0", "sessionId": "s",
                     "timestamp": f"2026-01-01T00:00:{i + 1:02d}Z",
                     "message": {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": tool, "input": ti}]}})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _flagged_lines(path: Path) -> set[int]:
    hits = audit_generator_transcript_strict(path, task="CS-01", own=OWN, extra_forbidden=(SCRATCH,))
    return {int(h["event_id"].split("/L")[1].split(".")[0]) for h in hits}


def test_strict_audit_resolves_paths(tmp_path):
    for i, (ti, expect) in enumerate(CASES):
        t = tmp_path / f"t{i}.jsonl"  # one call per transcript: a cd in one case must not carry into the next
        _transcript(t, [ti])
        assert bool(_flagged_lines(t)) == expect, (ti, expect)


def test_strict_audit_follows_a_carried_working_directory(tmp_path):
    t = tmp_path / "t.jsonl"
    _transcript(t, [{"command": f"cd {REPO}/tasks/CS-01"}, {"command": "cat verifiers/c1/spec.json"},
                    {"command": "cat README.md"}])
    # The task directory itself is not forbidden; the second read is flagged in case the cd carried over.
    assert _flagged_lines(t) == {3}


def test_unresolved_search_root_is_reported(tmp_path):
    t = tmp_path / "t.jsonl"
    _transcript(t, [{"command": "find $SOMEWHERE -name '*.py'"}])
    hits = audit_generator_transcript_strict(t, task="CS-01", own=OWN)
    assert [h["why"] for h in hits] == ["search rooted at an unresolved variable"]


# Shell forms that the first version of the strict parser missed (decision log D46): each must
# be flagged, and the controls at the end must not be.
SHELL_FORMS = [
    ('grep -nE "naturalsize|binary" tasks/CS-01/candidates/CS-01-eval-alt-1.json', True),
    ("LC_ALL=C cat tasks/CS-01/candidates/CS-01-eval-alt-1.json", True),
    ("(cd tasks/CS-01/verifiers && cat full_plain/tests/test_a.py)", True),
    ("(cd /home/user/trace-contract/tasks/CS-01 && cat candidates/x.json)", True),
    ("for f in tasks/CS-01/candidates/*.json; do cat $f; done", True),
    ("X=$(cat tasks/CS-01/candidates/x.json)", True),
    ("echo `cat tasks/CS-01/candidates/x.json`", True),
    ("python3 -c \"print(open('/home/user/trace-contract/tasks/CS-01/candidates/CS-01-eval-alt-1.json').read())\"", True),
    ("python3 - <<'EOF'\nprint(open('tasks/CS-01/candidates/CS-01-eval-alt-1.json').read())\nEOF", True),
    ("git show HEAD:tasks/CS-01/candidates/x.json", True),
    ("rsync -a tasks/CS-01/candidates/ /tmp/c/", True),
    ("base64 tasks/CS-01/candidates/x.json", True),
    ("grep --recursive foo tasks/", True),
    ("find src tasks -name x", True),
    ("timeout 60 cat tasks/CS-01/verifiers/x/spec.json", True),
    ("env A=1 cat tasks/CS-01/candidates/x.json", True),
    ("git status --short", True),
    ("cd /home/user/trace-contract && git diff --stat", True),
    (".venv/bin/tracecontract grade tasks/CS-01 full_plain CS-01-eval-alt-1", True),
    ("cat tasks/CS-01/verifiers/x  # tracecontract add-candidate", True),
    (".venv/bin/tracecontract add-candidate tasks/CS-01 CS-01-eval-nm-1 --patch /home/user/gen_workspaces/CS-01/eval-nm/nm1.diff", False),
    ("cat README.md && git log --oneline -5", False),
    ("cd /home/user/gen_workspaces/CS-01/eval-nm && grep -rn naturalsize .", False),
    ("(cd /home/user/gen_workspaces/CS-01/eval-nm/nm1 && git apply ../reference.diff)", False),
    ("cd /home/user/gen_workspaces/CS-01/eval-nm && for k in 1 2; do (cd nm$k && git apply ../reference.diff); done", False),
    ("git diff --stat -- src/", False),
]


def test_strict_audit_covers_shell_forms(tmp_path):
    for i, (cmd, expect) in enumerate(SHELL_FORMS):
        t = tmp_path / f"s{i}.jsonl"
        _transcript(t, [{"command": cmd}])
        assert bool(_flagged_lines(t)) == expect, (cmd, expect)


def _load_strict_reaudit():
    import importlib.util

    spec = importlib.util.spec_from_file_location("strict_reaudit", Path(__file__).resolve().parents[1] / "scripts" / "strict_reaudit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scratch_reads_are_attributed_to_their_writer(tmp_path):
    """Searches of the shared scratch directory, and reads of another agent's files there, are reported (D46)."""
    sr = _load_strict_reaudit()
    a, b = tmp_path / "agent-A.jsonl", tmp_path / "agent-B.jsonl"
    _transcript(a, [{"command": f"mkdir -p {SCRATCH}/shared && echo x > {SCRATCH}/shared/a.txt"}])
    rows_b = [
        {"command": f"echo y > {SCRATCH}/shared/b.txt"},
        {"command": f"cat {SCRATCH}/shared/b.txt"},                      # own
        {"command": f"cat {SCRATCH}/shared/a.txt"},                      # A's file
        {"command": f"grep -rn x {SCRATCH}/shared"},                     # recursive read over A's file
        {"command": f"S={SCRATCH}; grep -rn x $S"},                      # search of the directory itself
        {"command": f"python3 - \"{SCRATCH}\" <<'EOF'\nprint(1)\nEOF"},   # inline code given the directory
    ]
    _transcript(b, rows_b)
    # B's calls come after A's: shift B's timestamps by an hour
    b.write_text(b.read_text().replace("2026-01-01T00:", "2026-01-01T01:"))
    writes = sorted(({**o, "agent": p.stem} for p in (a, b) for o in sr._scratch_ops(p, SCRATCH) if o["op"] == "write"),
                    key=lambda o: o["ts"])
    roots, others, n_own = sr.classify_scratch(b, SCRATCH, writes)
    assert sorted(r["op"] for r in roots) == ["exec", "search"]
    assert {(o["op"], o["path"].rsplit("/", 1)[-1], o["last_written_by"]) for o in others} >= {
        ("read", "a.txt", "agent-A"), ("search", "shared", "agent-A")}
    assert n_own >= 1
