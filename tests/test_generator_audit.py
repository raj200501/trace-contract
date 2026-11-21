"""The strict re-audit of generator transcripts resolves paths instead of matching substrings (D44)."""

from __future__ import annotations

import hashlib
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


# --------------------------------------------------------------------------- tool outputs (A6)


def _session(path: Path, calls: list[tuple[str, dict, str]]) -> None:
    """A transcript in which each call (tool, input, output text) has a tool_use and a tool_result row."""
    rows = [{"type": "user", "uuid": "u0", "parentUuid": None, "sessionId": "s", "timestamp": "2026-01-01T00:00:00Z",
             "message": {"role": "user", "content": "go"}}]
    for i, (tool, ti, out) in enumerate(calls):
        ts = f"2026-01-01T00:00:{i + 1:02d}"
        rows.append({"type": "assistant", "uuid": f"a{i}", "parentUuid": "u0", "sessionId": "s", "timestamp": ts + ".000Z",
                     "message": {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": tool, "input": ti}]}})
        rows.append({"type": "user", "uuid": f"r{i}", "parentUuid": f"a{i}", "sessionId": "s", "timestamp": ts + ".500Z",
                     "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": out,
                                                              "is_error": out.startswith("cat:")}]}})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _exposed(path: Path, **kw) -> set[tuple[str, str]]:
    reads, exposures = audit_generator_transcript_strict(path, task="CS-01", own=OWN, outputs=True, **kw)
    assert reads == audit_generator_transcript_strict(path, task="CS-01", own=OWN, **kw)  # reads do not change
    return {(x["path"].removeprefix(REPO + "/"), x["why"]) for x in exposures}


def test_tool_outputs_are_reported_apart_from_reads(tmp_path):
    t = tmp_path / "t.jsonl"
    _session(t, [
        ("Bash", {"command": "git status --short"}, " M src/humanize/filesize.py\n?? tasks/CS-01/candidates/CS-01-eval-alt-1.json\n"),
        ("Bash", {"command": f"ls {OWN}"}, "nm1\nnm2\nreference.diff\n"),
        ("Read", {"file_path": f"{OWN}/notes.txt"}, f"     1\tsee {REPO}/tasks/CS-01/verifiers/full_plain/tests/test_a.py\n"),
        ("Bash", {"command": "cat x.py"}, f"cat: {REPO}/results/runs/pilot-v0.3.3/x: No such file or directory"),
    ])
    reads, exposures = audit_generator_transcript_strict(t, task="CS-01", own=OWN, outputs=True)
    assert [h["path"] for h in reads] == [REPO]  # the git listing over the repository is a read; the outputs are not
    assert {(x["path"].removeprefix(REPO + "/"), x["why"]) for x in exposures} == {
        ("tasks/CS-01/candidates/CS-01-eval-alt-1.json", "shown in a tool output: inside forbidden material"),
        ("CS-01-eval-alt-1", "held-out candidate named in a tool output"),
        ("tasks/CS-01/verifiers/full_plain/tests/test_a.py", "shown in a tool output: inside forbidden material"),
        ("results/runs/pilot-v0.3.3/x", "shown in a tool output: inside forbidden material"),
    }
    first = next(x for x in exposures if x["path"] == "CS-01-eval-alt-1")
    assert first["text"] == "?? tasks/CS-01/candidates/CS-01-eval-alt-1.json"  # the output line that showed it
    assert first["call"].endswith("/L000002.00") and first["event_id"].endswith("/L000003.00") and first["tool"] == "Bash"
    assert first["ts"] == "2026-01-01T00:00:01.500Z"


def test_own_candidates_and_own_writes_are_not_exposures(tmp_path):
    t = tmp_path / "t.jsonl"
    _session(t, [
        ("Bash", {"command": ".venv/bin/tracecontract add-candidate tasks/CS-01 CS-01-eval-nm-1 --patch nm1.diff"},
         '{"candidate": "candidates/CS-01-eval-nm-1.json", "patch_lines": 12}'),
        # a shell function registers ids built from a variable: they are the agent's own too
        ("Bash", {"command": 'reg() {\n  .venv/bin/tracecontract add-candidate tasks/CS-01 "CS-01-eval-pre-$1" --patch x\n}\nreg 2'},
         "=== CS-01-eval-pre-2"),
        ("Bash", {"command": "git status --short"},
         "?? tasks/CS-01/candidates/CS-01-eval-nm-1.json\n?? tasks/CS-01/candidates/CS-01-eval-alt-2.json\n"),
        ("Write", {"file_path": f"{SCRATCH}/check.py", "content": "x"}, f"File created successfully at: {SCRATCH}/check.py"),
    ])
    assert _exposed(t, extra_forbidden=(SCRATCH,)) == {
        ("tasks/CS-01/candidates/CS-01-eval-alt-2.json", "shown in a tool output: inside forbidden material"),
        ("CS-01-eval-alt-2", "held-out candidate named in a tool output"),
    }


def test_relative_paths_in_outputs_resolve_from_where_the_command_ends(tmp_path):
    cases = [
        ("Bash", {"command": f"cd {OWN}/base && find . -name '*.md'"}, "./README.md\n./docs/index.md\n", set()),
        ("Bash", {"command": "cd tasks/CS-01 && ls -R"}, "./verifiers/full_plain/tests:\ntest_a.py\n",
         {("tasks/CS-01/verifiers/full_plain/tests", "shown in a tool output: inside forbidden material")}),
        ("Bash", {"command": "cat README.md"}, "Labels: see docs/annotation_guide.md.\n",
         {("docs/annotation_guide.md", "shown in a tool output: inside forbidden material")}),
        # relative paths in other tools' outputs (file contents) are not resolved; absolute ones are
        ("Read", {"file_path": f"{REPO}/README.md"}, "     1\tsee docs/annotation_guide.md\n", set()),
        ("Glob", {"pattern": "*.py", "path": OWN}, f"{OWN}/nm1/x.py\n{REPO}/data/controlled/transcripts/CS-01.jsonl\n",
         {("data/controlled/transcripts/CS-01.jsonl", "shown in a tool output: inside forbidden material")}),
        ("Bash", {"command": "ls"}, "listing of /tmp/x/scratchpad/sealed/y\n",
         {("/tmp/x/scratchpad/sealed/y", "shown in a tool output: sealed material")}),
    ]
    for i, (tool, ti, out, expect) in enumerate(cases):
        t = tmp_path / f"o{i}.jsonl"
        _session(t, [(tool, ti, out)])
        assert _exposed(t) == expect, (ti, out)


def test_reaudit_writes_output_exposures_apart_and_leaves_the_audit_record_unchanged(tmp_path):
    sr = _load_strict_reaudit()
    root, tdir = tmp_path / "repo", tmp_path / "transcripts"
    tdir.mkdir()
    b = tdir / "agent-B.jsonl"
    _session(b, [("Bash", {"command": f"echo y > {SCRATCH}/shared/b.txt"}, ""),
                 ("Bash", {"command": f"ls {SCRATCH}/shared"}, f"{SCRATCH}/shared/a.txt\n{SCRATCH}/shared/b.txt\n"),
                 ("Bash", {"command": "git status --short"}, "?? tasks/CS-01/candidates/CS-01-eval-alt-1.json\n")])
    a = tdir / "agent-A.jsonl"
    _transcript(a, [{"command": f"mkdir -p {SCRATCH}/shared && echo x > {SCRATCH}/shared/a.txt"}])
    a.write_text(a.read_text().replace("2026-01-01T00:00:", "2025-12-31T23:00:"))  # A wrote before B
    audit = root / "tasks" / "CS-01" / "labels" / "generator_audit.json"
    audit.parent.mkdir(parents=True)
    audit.write_text(json.dumps({"eval-nm": {"transcript_sha256": hashlib.sha256(b.read_bytes()).hexdigest()}}))
    sr.R = root
    assert sr.main(["--transcripts", str(tdir), "--scratch", SCRATCH, "--write"]) == 0
    recorded = audit.read_bytes()
    report = tmp_path / "outputs.json"
    assert sr.main(["--transcripts", str(tdir), "--scratch", SCRATCH, "--write", "--outputs", str(report)]) == 0
    assert audit.read_bytes() == recorded  # the output scan never enters the audit record
    entry = json.loads(report.read_text())["transcripts"]["CS-01"]["eval-nm"]["main"]
    assert {x["path"] for x in entry["output_exposures"]} == {f"{REPO}/tasks/CS-01/candidates/CS-01-eval-alt-1.json",
                                                              "CS-01-eval-alt-1"}
    assert [(x["path"], x["last_written_by"]) for x in entry["output_scratch_not_attributed_to_the_agent"]] == [
        ("<scratchpad>/shared/a.txt", "agent-A")]  # redacted, attributed to its writer
    assert entry["output_scratch_own"] == 1  # b.txt, written by the agent itself
    assert SCRATCH not in report.read_text()
