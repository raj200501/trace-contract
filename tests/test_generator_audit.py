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
    ({"command": "cat > /tmp/notes.txt <<'EOF'\nsee tasks/CS-01/verifiers/c1 and results/\nEOF"}, False),  # heredoc body is data
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
