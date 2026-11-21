"""The labeler-writer profile of the strict re-audit (protocol §15.5, decision log D55).

A writer of an independent labeler may read only its family's reference contract, the base snapshot, the harness API,
the lint rules and a synthetic example of the test format, and write only its own tests directory. The profile scans
every tool input and output, the prompt and the harness context; a revision may be told only the names of failing
checks. The transcripts here are synthetic, over a small checkout with forbidden material of one family, and so are the
harness's session locations (the script's SESSION_ROOTS; its defaults are checked at the end).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

REPO = "/home/user/trace-contract"
TASK = "CS-01"
OWN = f"{REPO}/tasks/{TASK}/verifiers/independent_label/tests"
# Synthetic session locations, which the world fixture installs as the script's SESSION_ROOTS: a directory of agent
# records, and what begins the name of each user's temporary directory.
RECORDS, TMP = "/fixture/session-records", "/fixture/session-tmp-"
SID = "0b0f1c2e-3d4a-4b5c-8d6e-7f8091a2b3c4"
SESSION_DIR = f"{RECORDS}/projects/demo/{SID}"  # one session's records, where the harness saves long tool outputs
SCRATCH = f"{TMP}0/demo/{SID}/scratchpad"  # that session's scratch directory, in the temporary directory of user 0
PROMPT = f"You are the independent labeler for task {TASK}. Read only the reference contract and the base snapshot."
# Text that only forbidden files hold.
REF_LINE = 'assert naturalsize(3000000, strip_trailing_zero=True) == "3 MB", "the reference trims"'
CAND_LINE = "if strip_trailing_zero and text.endswith('.0 MB'):  # the candidate's own trimming"
LABEL_LINE = "rationale: keeps the trailing zero when asked to drop it (violates R-opt-in)"
EDIT_LINE = "def naturalsize(value, binary=False, gnu=False, strip_trailing_zero=False):"
FILES = {
    "tasks/CS-01/task.json": "{}",
    "tasks/CS-01/contracts/reference.json": json.dumps({"contract_id": "CS-01-reference", "requirements": [
        {"req_id": "R-opt-in", "statement": "naturalsize(3000000, strip_trailing_zero=True) == '3 MB'"},
        {"req_id": "R-keep-meaningful", "statement": "naturalsize(3000, binary=True) == '2.9 KiB'"}]}, indent=2),
    "tasks/CS-01/contracts/mapping_full_session.json": json.dumps({"test_full.py::test_full_trims": ["R-opt-in"]}),
    "snapshots/CS-01/src/humanize/filesize.py": "def naturalsize(value, binary=False, gnu=False):\n"
                                                "    return format_the_size_for_humans(value, binary, gnu)\n",
    "src/tracecontract/sandbox/harness/tc_sandbox.py": "def run_python(code):\n    return execute_in_the_sandbox(code)\n",
    "src/tracecontract/verifier.py": f'_SESSION_LOCAL = ("{TMP}", "{RECORDS}/")  # paths a record may not name\n',
    "tests/fixtures/harbor_fx01/tasks/FX-01/verifiers/v1/tests/test_add.py": "from tc_sandbox import run_python\n",
    "tasks/CS-01/verifiers/reference_check/tests/test_ref.py": f"def test_reference_trims_megabytes():\n    {REF_LINE}\n",
    "tasks/CS-01/verifiers/full_plain/tests/test_full.py": "def test_full_trims():\n    check_the_generated_verifier(1, 2)\n",
    "tasks/CS-01/candidates/CS-01-eval-alt-1.json": json.dumps({"candidate_id": "CS-01-eval-alt-1",
                                                                 "patch": f"--- a/f.py\n+++ b/f.py\n+    {CAND_LINE}\n"}),
    "tasks/CS-01/candidates/CS-01-reference.json": json.dumps({"candidate_id": "CS-01-reference", "patch": f"+{EDIT_LINE}\n"}),
    "tasks/CS-01/labels/proposed_labels.json": json.dumps({"CS-01-eval-alt-1": {"label": "fail", "note": LABEL_LINE}}),
    "data/controlled/transcripts/CS-01.jsonl": json.dumps({"message": {"content": f"Edit: {EDIT_LINE}"}}) + "\n",
}


def _load():
    spec = importlib.util.spec_from_file_location("strict_reaudit_labeler", Path(__file__).resolve().parents[1] / "scripts" / "strict_reaudit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def world(tmp_path, monkeypatch):
    """The script pointed at a small checkout and at the synthetic session locations, with the index of its forbidden
    material."""
    sr = _load()
    root = tmp_path / "repo"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    sr.R = root
    monkeypatch.setattr(sr, "SESSION_ROOTS", sr.SessionRoots(records=RECORDS, tmp=TMP))
    return sr, root, sr.labeler_index(root)


def _session(path: Path, calls: list[tuple[str, dict, str]], *, prompt: str = PROMPT, attachments: tuple = (),
             label: str | None = None) -> Path:
    """A transcript: the prompt, harness attachments, then a tool_use and a tool_result row for each (tool, input, output)."""
    rows = [{"type": "user", "uuid": "u0", "parentUuid": None, "sessionId": SID, "timestamp": "2026-01-01T00:00:00Z",
             "message": {"role": "user", "content": prompt}}]
    rows += [{"type": "attachment", "uuid": f"x{i}", "sessionId": SID, "timestamp": "2026-01-01T00:00:00Z", "attachment": a}
             for i, a in enumerate(attachments)]
    for i, (tool, ti, out) in enumerate(calls):
        ts = f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}"
        rows.append({"type": "assistant", "uuid": f"a{i}", "parentUuid": "u0", "sessionId": SID, "timestamp": ts + ".000Z",
                     "message": {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": tool, "input": ti}]}})
        rows.append({"type": "user", "uuid": f"r{i}", "parentUuid": f"a{i}", "sessionId": SID, "timestamp": ts + ".500Z",
                     "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": out,
                                                              "is_error": out.startswith("Permission for this action")}]}})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    if label:
        path.with_name(path.stem + ".meta.json").write_text(json.dumps({"description": label}), encoding="utf-8")
    return path


def _audit(sr, index, path: Path, **kw) -> dict:
    return sr.audit_labeler_transcript(path, task=TASK, index=index, families=(TASK,), **kw)


# --------------------------------------------------------------------------- tool inputs


ALLOWED_CALLS = [
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/contracts/reference.json"}, '{"contract_id": "CS-01-reference"}'),
    ("Bash", {"command": f"cd {REPO}/snapshots/{TASK} && sed -n 1,30p src/humanize/filesize.py | head -c 1500 2>&1"},
     "def naturalsize(value, binary=False, gnu=False):\n"),
    ("Bash", {"command": f"find {REPO}/snapshots/{TASK} -type f | head -100"}, f"{REPO}/snapshots/{TASK}/src/humanize/filesize.py\n"),
    ("Read", {"file_path": f"{REPO}/src/tracecontract/sandbox/harness/tc_sandbox.py"}, "     1\tdef run_python(code):\n"),
    ("Read", {"file_path": f"{REPO}/src/tracecontract/verifier.py"},  # its text names session directories: not an exposure
     f'     1\t_SESSION_LOCAL = ("{TMP}", "{RECORDS}/")  # paths a record may not name\n'),
    ("Bash", {"command": f"cat {REPO}/tests/fixtures/harbor_fx01/tasks/FX-01/verifiers/v1/tests/test_add.py"},
     "from tc_sandbox import run_python\n"),
    ("Bash", {"command": f"mkdir -p {OWN} && cat > {OWN}/test_trim.py <<'EOF'\nfrom tc_sandbox import run_python\n"
                         "CHECK_REQUIREMENTS = {'test_opt_in': ['R-opt-in']}\ndef test_opt_in():\n    pass\nEOF"}, ""),
    ("Write", {"file_path": f"{OWN}/test_keep.py", "content": "def test_keep():\n    pass\n"}, "File created successfully"),
    ("Bash", {"command": f"{REPO}/.venv/bin/tracecontract lint-tests {OWN}; echo \"exit=$?\""}, '{"issues": [], "ok": true}\nexit=0'),
    ("Bash", {"command": f"cd /tmp && {REPO}/.venv/bin/python3 -I -c \"\nimport sys; sys.path.insert(0, '{OWN}')\nprint(1)\""}, "1"),
    ("Bash", {"command": f"ls -la {OWN}/ 2>&1"}, "test_keep.py\ntest_trim.py\n"),
    ("SubagentHandback", {"message": f"Wrote {OWN}/test_trim.py, from snapshots/{TASK}/src/humanize/filesize.py"},
     '{"success":true}'),
]


def test_allowed_reads_and_own_writes_are_not_flagged(world, tmp_path):
    sr, _, index = world
    rec = _audit(sr, index, _session(tmp_path / "agent-ok.jsonl", ALLOWED_CALLS))
    assert rec["hits"] == [] and rec["exposures"] == [] and not rec["flagged"], (rec["hits"], rec["exposures"])
    assert set(rec["accesses"]) <= {"allowed", "own", "system", "tmp"} and rec["accesses"]["allowed"] >= 5
    assert rec["tool_calls"] == {"Bash": 7, "Read": 3, "SubagentHandback": 1, "Write": 1} and rec["tool_calls_total"] == 12
    assert rec["own_checks"] == ["test_keep.py::test_keep", "test_trim.py::test_opt_in"]


# (tool, input, the category and reason of the hit)
FORBIDDEN_READS = [
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/verifiers/reference_check/tests/test_ref.py"}, "forbidden", "a reference check"),
    ("Bash", {"command": f"cat {REPO}/tasks/{TASK}/candidates/CS-01-eval-alt-1.json"}, "forbidden", "a candidate"),
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/candidates/CS-01-reference.json"}, "forbidden",
     "the reference solution (the reference candidate and its patch)"),
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/labels/proposed_labels.json"}, "forbidden", "a label"),
    ("Bash", {"command": "head -c 2000 data/controlled/transcripts/CS-01.jsonl"}, "forbidden",
     "the controlled sessions' records (their transcripts hold the reference edits)"),
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/verifiers/full_plain/tests/test_full.py"}, "forbidden", "a generated verifier"),
    ("Read", {"file_path": f"{REPO}/tasks/CS-02/verifiers/independent_label/tests/test_x.py"}, "forbidden",
     "a generated verifier of another family"),
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/strata/fresh-v1/candidates/CS-01-fresh-A-u1-1.json"}, "forbidden",
     "a stratum candidate"),
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/contracts/mapping_full_session.json"}, "forbidden",
     "a mapping of a generated verifier's checks"),
    ("Read", {"file_path": f"{REPO}/results/runs/pilot-v0.3.3/verdicts.json"}, "forbidden", "verdicts (results/)"),
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/verifiers/independent_label/status.json"}, "forbidden",
     "the coordinator's grading status of the labeler"),
    ("Read", {"file_path": f"{SCRATCH}/labelers/CS-01/grade_reference.json"}, "forbidden",
     "a Claude session directory (the build session's records)"),
    ("Read", {"file_path": "/home/user/.tc_sealed/archive/x.json"}, "forbidden", "sealed material"),
    ("Grep", {"pattern": "strip_trailing_zero"}, "forbidden", "recursive search over forbidden material (a reference check)"),
    ("Glob", {"pattern": f"tasks/{TASK}/verifiers/**/*.py"}, "forbidden",
     "a listing of a directory that holds forbidden material (a reference check)"),
    ("Read", {"file_path": f"{REPO}/docs/annotation_guide.md"}, "doc", "documentation or paper text (judged by what it showed)"),
    ("Read", {"file_path": f"{REPO}/README.md"}, "doc", "documentation or paper text (judged by what it showed)"),
    ("Read", {"file_path": f"{REPO}/tasks/{TASK}/contracts/full_session.json"}, "outside", "another contract"),
    ("Read", {"file_path": f"{REPO}/snapshots/CS-02/tinydb/storages.py"}, "outside", "another family's base snapshot"),
    ("Read", {"file_path": f"{REPO}/src/tracecontract/schemas.py"}, "outside", "outside the allowed inputs"),
    ("Bash", {"command": "cat /tmp/tc-grade-x/work/src/humanize/filesize.py"}, "tmp", "the container's temporary directory"),
]


def test_forbidden_reads_are_hits(world, tmp_path):
    sr, _, index = world
    for i, (tool, ti, cat, why) in enumerate(FORBIDDEN_READS):
        rec = _audit(sr, index, _session(tmp_path / f"agent-f{i}.jsonl", [(tool, ti, "")]))
        assert [(h["category"], h["why"]) for h in rec["hits"]] == [(cat, why)], (ti, rec["hits"])
        assert rec["flagged"]


# Forbidden paths hidden in shell commands: each must be flagged.
HIDDEN = [
    f"cd {REPO}/tasks/{TASK} && cat verifiers/reference_check/tests/test_ref.py",
    f"(cd {REPO}/tasks/{TASK}/verifiers && grep -rn trailing .)",
    "python3 -c \"print(open('tasks/CS-01/candidates/CS-01-eval-alt-1.json').read())\"",
    "X=tasks/CS-01/labels; cat $X/proposed_labels.json",
    f"python3 - <<'EOF'\nimport json\nprint(open('{REPO}/data/controlled/transcripts/CS-01.jsonl').read())\nEOF",
    "sed -n 1,20p tasks/CS-01/verifiers/reference_check/tests/test_ref.py",
    "find . -name '*.py' | head",
    f"ls {REPO}/tasks/{TASK}/verifiers",
    "for f in tasks/CS-01/candidates/*.json; do head -c 200 $f; done",
    f"{REPO}/.venv/bin/tracecontract grade tasks/{TASK} independent_label CS-01-eval-alt-1",
    f"cat {OWN}/../../reference_check/tests/test_ref.py",
    "ls ~/gen_workspaces/CS-01",
    "git -C /home/user/trace-contract show HEAD:tasks/CS-01/candidates/CS-01-eval-alt-1.json",
]
# Shell forms that touch only allowed inputs or the writer's own files: none may be flagged.
CONTROLS = [
    f"cd {REPO}/snapshots/{TASK} && grep -n \"def naturalsize\" -A 75 src/humanize/filesize.py 2>/dev/null",
    f"cat > {OWN}/test_a.py <<'EOF'\nimport json\nEOF",
    f"cd /tmp && PYTHONPATH={REPO}/src/tracecontract/sandbox/harness python3 -I -c \"import sys; sys.path.insert(0, '{OWN}')\"",
    f"date -u +%Y-%m-%dT%H:%M:%SZ; ls -la {OWN} 2>&1; echo ---",
    f".venv/bin/tracecontract lint-tests {OWN}; echo \"exit=$?\"",
]


def test_forbidden_paths_hidden_in_shell_commands(world, tmp_path):
    sr, _, index = world
    for i, cmd in enumerate(HIDDEN):
        rec = _audit(sr, index, _session(tmp_path / f"agent-h{i}.jsonl", [("Bash", {"command": cmd}, "")]))
        assert any(h["category"] == "forbidden" for h in rec["hits"]), (cmd, rec["hits"])
    for i, cmd in enumerate(CONTROLS):
        rec = _audit(sr, index, _session(tmp_path / f"agent-c{i}.jsonl", [("Bash", {"command": cmd}, "")]))
        assert rec["hits"] == [], (cmd, rec["hits"])
    rec = _audit(sr, index, _session(tmp_path / "agent-id.jsonl", [("Bash", {"command": "python3 -c \"x = 'CS-01-eval-alt-1'\""}, "")]))
    assert [(h["op"], h["why"]) for h in rec["hits"]] == [("named", "named in the tool input: a candidate id")]
    rec = _audit(sr, index, _session(tmp_path / "agent-cli.jsonl", [("Bash", {"command": HIDDEN[9]}, "")]))
    assert {(h["op"], h["why"]) for h in rec["hits"]} == {
        ("cli", "a CLI call other than lint-tests"), ("candidate", "a candidate named in a CLI call"),
        ("search", "recursive search over forbidden material (a reference check)")}  # the CLI may read the whole task


def test_a_call_the_permission_system_denied_is_marked(world, tmp_path):
    sr, _, index = world
    denied = "Permission for this action was denied by the Claude Code auto mode classifier."
    rec = _audit(sr, index, _session(tmp_path / "agent-d.jsonl", [("Bash", {"command": "grep -rn lint_tests ."}, denied)]))
    assert [(h["why"], h.get("denied")) for h in rec["hits"]] == [
        ("recursive search over forbidden material (a reference check)", True)]
    assert rec["denied_calls"] == 1


# --------------------------------------------------------------------------- tool outputs


def test_forbidden_text_in_a_tool_output_is_an_exposure(world, tmp_path):
    sr, _, index = world
    helper = [("Bash", {"command": f"{REPO}/.venv/bin/tracecontract lint-tests {OWN}"}, out) for out in (
        f"  {REF_LINE}\n",                                    # code of a reference check
        f"+    {CAND_LINE}\n",                                # a candidate's patch line
        f"{LABEL_LINE}\n",                                    # a label's text
        "collected test_reference_trims_megabytes\n",         # the name of a reference check's test
        "graded CS-01-eval-alt-1: fail\n",                    # a candidate id
        f"see {REPO}/tasks/{TASK}/verifiers/reference_check/tests/test_ref.py\n",  # a forbidden path
        f"Output too large. Full output saved to: {SESSION_DIR}/tool-results/b1.txt",  # the harness's notice
    )]
    rec = _audit(sr, index, _session(tmp_path / "agent-o.jsonl", helper))
    got = [(x["path"], x["why"]) for x in rec["exposures"]]
    assert got == [
        ("tasks/CS-01/verifiers/reference_check/tests/test_ref.py", "shown in a tool output: text of a reference check"),
        ("tasks/CS-01/candidates/CS-01-eval-alt-1.json", "shown in a tool output: text of a candidate"),
        ("tasks/CS-01/labels/proposed_labels.json", "shown in a tool output: text of a label"),
        ("test_reference_trims_megabytes", "shown in a tool output: the name of a test in a reference check "
                                           "(tasks/CS-01/verifiers/reference_check/tests/test_ref.py)"),
        ("CS-01-eval-alt-1", "shown in a tool output: a candidate id"),
        (f"{REPO}/tasks/{TASK}/verifiers/reference_check/tests/test_ref.py", "shown in a tool output: a reference check"),
        (f"{SESSION_DIR}/tool-results/b1.txt",
         "shown in a tool output: a Claude session directory (the build session's records)"),
    ], got
    assert rec["exposures"][0]["call"].endswith("/L000002.00") and rec["exposures"][0]["tool"] == "Bash"
    assert rec["hits"] == [] and rec["flagged"]  # the call itself is allowed: only its outputs are exposures
    # A file the agent wrote in /tmp is flagged once, as a write outside its directory, not again when it reads it back.
    calls = [("Write", {"file_path": "/tmp/helper.py", "content": "print(1)\n"}, "ok"), ("Bash", {"command": "python3 /tmp/helper.py"}, "1")]
    rec = _audit(sr, index, _session(tmp_path / "agent-tmp.jsonl", calls))
    assert [(h["op"], h["why"]) for h in rec["hits"]] == [
        ("write", "a write outside its own tests directory: the container's temporary directory")]


def test_text_the_agent_wrote_first_is_its_own(world, tmp_path):
    """Text the writer wrote itself is not an exposure when an output shows it again, but it is listed as a coincidence."""
    sr, _, index = world
    calls = [("Write", {"file_path": f"{OWN}/test_mb.py", "content": f"def test_mb():\n    {REF_LINE}\n"}, "File created"),
             ("Bash", {"command": f"cat {OWN}/test_mb.py"}, f"def test_mb():\n    {REF_LINE}\n")]
    rec = _audit(sr, index, _session(tmp_path / "agent-own.jsonl", calls))
    assert rec["exposures"] == [] and not rec["flagged"]
    assert [x["also_in"] for x in rec["own_text_also_in_forbidden_material"]["lines"]] == [
        ["tasks/CS-01/verifiers/reference_check/tests/test_ref.py"]]
    # The same output before the agent wrote the text is an exposure.
    rec = _audit(sr, index, _session(tmp_path / "agent-first.jsonl", calls[::-1]))
    assert [x["why"] for x in rec["exposures"]] == ["shown in a tool output: text of a reference check"]


# --------------------------------------------------------------------------- prompts and harness context


def test_a_prompt_that_quotes_forbidden_material_is_flagged(world, tmp_path):
    sr, _, index = world
    rec = _audit(sr, index, _session(tmp_path / "agent-p.jsonl", [], prompt=PROMPT + f"\nFor example:\n    {REF_LINE}\n"))
    assert [x["why"] for x in rec["prompt"]["forbidden_content"]] == ["in the prompt: text of a reference check"]
    assert rec["flagged"]
    clean = _audit(sr, index, _session(tmp_path / "agent-q.jsonl", [], prompt=PROMPT + "\nDo not read tasks/CS-01/candidates/."))
    assert clean["prompt"]["forbidden_content"] == [] and not clean["flagged"]
    assert [x["category"] for x in clean["prompt"]["paths_named"]] == ["forbidden"]  # named as forbidden: not a flag


def test_harness_context_is_scanned(world, tmp_path):
    sr, _, index = world
    env = {"type": "environment", "snapshot": {"workingDirectory": REPO, "scratchpadDirectory": SCRATCH}}
    rec = _audit(sr, index, _session(tmp_path / "agent-e.jsonl", [], attachments=(env,)))
    assert [x["where"] for x in rec["harness_context"]["forbidden_paths_named"]] == ["environment"] and not rec["flagged"]
    note = {"type": "task_reminder", "content": [{"subject": "status", "description": f"x\n    {REF_LINE}\n"}]}
    rec = _audit(sr, index, _session(tmp_path / "agent-n.jsonl", [], attachments=(note,)))
    assert [x["why"] for x in rec["harness_context"]["forbidden_content"]] == [
        "in the harness context (task_reminder): text of a reference check"] and rec["flagged"]


REVISE_HEAD = (f"You are revising the independent labeler for task {TASK}; this is your single revision.\n"
               "These are the names of the checks that failed. You get names only, no messages:\n")
REVISE_TAIL = "Revise the tests so that the checks test the reference contract faithfully, and run lint-tests until clean.\n"


def test_a_revision_prompt_may_carry_only_failing_check_names(world, tmp_path):
    sr, _, index = world
    writer = _session(tmp_path / "agent-w.jsonl", [
        ("Write", {"file_path": f"{OWN}/test_a.py", "content": "def test_one():\n    pass\n\ndef test_two():\n    pass\n"}, "ok")])
    cases = [  # (the list between the head and the tail, more than names, what the check records)
        ("test_a.py::test_one\ntest_a.py::test_two\n", False, {}),
        ("passes on unchanged base: test_a.py::test_one\n", True, {"kinds": {"test_a.py::test_one": "passes on unchanged base"}}),
        ("test_a.py::test_one\nE   AssertionError: assert '3.0 MB' == '3 MB'\n", True, {"grading": ["AssertionError", "assert"]}),
        ("(none listed; check the build notes: CS-01-reference passed, 3 repeats)\n", True,
         {"grading": ["CS-01-reference", "notes", "repeats"]}),
        ("test_a.py::test_three\n", True, {"unknown_names": ["test_a.py::test_three"]}),
        ("uncovered requirement: R-unknown\n", True, {"unknown_names": ["R-unknown"]}),
    ]
    for i, (listed, more, expect) in enumerate(cases):
        rev = _session(tmp_path / f"agent-r{i}.jsonl", [], prompt=REVISE_HEAD + listed + REVISE_TAIL)
        rec = _audit(sr, index, rev, round_no=2, writer=writer, requirements={"R-opt-in", "R-keep-meaningful"})
        got = rec["prompt"]["revision_input"]
        assert got["more_than_names"] is more and rec["flagged"] is more, (listed, got)
        if "kinds" in expect:
            assert got["kinds"] == expect["kinds"]
        if "unknown_names" in expect:
            assert got["unknown_names"] == expect["unknown_names"]
        if "grading" in expect:
            assert set(expect["grading"]) <= {m for x in got["grading_text"] for m in x["matched"]}, got
    # The writer's own check names in a revision prompt are not forbidden text, even when a forbidden verifier has a test
    # of the same name (the reviser reads them as its own).
    rec = _audit(sr, index, _session(tmp_path / "agent-r9.jsonl", [], prompt=REVISE_HEAD + "test_a.py::test_one\n" + REVISE_TAIL),
                 round_no=2, writer=writer, requirements=set())
    assert rec["prompt"]["forbidden_content"] == [] and rec["prompt"]["revision_input"]["listed"] == ["test_a.py::test_one"]


# --------------------------------------------------------------------------- the command line


def test_cli_reports_labelers_by_sha256_and_label(world, tmp_path):
    sr, root, _ = world
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    ok = _session(tdir / "agent-a1.jsonl", ALLOWED_CALLS, label="L-write-CS-01",
                  attachments=({"type": "environment", "snapshot": {"scratchpadDirectory": SCRATCH}},))
    bad = _session(tdir / "agent-a2.jsonl", [FORBIDDEN_READS[0][:2] + ("",),
                                             ("Bash", {"command": "ls"}, f"saved to {SESSION_DIR}/tool-results/x.txt")],
                   label="L-revise-CS-01", prompt=REVISE_HEAD + "fails on reference: test_trim.py::test_opt_in\n" + REVISE_TAIL)
    sha = hashlib.sha256(ok.read_bytes()).hexdigest()
    report = tmp_path / "writer_audit.json"
    argv = ["--labeler", f"CS-01={sha}", "--revision", f"CS-01={bad}", "--transcripts", str(tdir), "--scratch", SCRATCH,
            "--report", str(report)]
    assert sr.main(argv) == 0
    rep = json.loads(report.read_text())
    assert list(rep["transcripts"]) == ["L-write-CS-01", "L-revise-CS-01"] and rep["flagged"] == ["L-revise-CS-01"]
    w, r = rep["transcripts"]["L-write-CS-01"], rep["transcripts"]["L-revise-CS-01"]
    assert (w["round"], w["task_id"], w["transcript_sha256"], w["flagged"]) == (1, "CS-01", sha, False)
    assert r["round"] == 2 and r["prompt"]["revision_input"]["kinds"] == {"test_trim.py::test_opt_in": "fails on reference"}
    assert r["prompt"]["revision_input"]["unknown_names"] == []  # the writer's check, found in its transcript
    assert rep["families"] == {"CS-01": {"transcripts": ["L-write-CS-01", "L-revise-CS-01"], "flagged": ["L-revise-CS-01"]}}
    text = report.read_text()
    assert SID not in text and TMP not in text and RECORDS not in text
    assert "<session-dir>/tool-results/x.txt" in text and "<scratchpad>" in text
    assert rep["rules"]["allowed"]["CS-01"][0] == {"path": "tasks/CS-01/contracts/reference.json", "what": "the reference contract"}
    assert sr.main(["--labeler", "CS-01=" + "0" * 64, "--transcripts", str(tdir), "--report", str(report)]) == 1
    assert json.loads(report.read_text())["not_audited"] == ["L-write-CS-01"]
    with pytest.raises(SystemExit):
        sr.main(["--labeler", f"CS-01={ok}"])  # no --report
    with pytest.raises(SystemExit):
        sr.main(["--labeler", "CS-01", "--report", str(report)])  # no transcript


def test_other_modes_still_require_transcripts(world):
    sr, _, _ = world
    for argv in ([], ["--scratch", SCRATCH], ["--fresh", "attempts.json", "--report", "r.json"]):
        with pytest.raises(SystemExit) as e:
            sr.main(argv)
        assert e.value.code == 2


# --------------------------------------------------------------------------- the session locations

SESSION_WHY = "a Claude session directory (the build session's records)"
LISTING_WHY = f"a listing of a directory that holds forbidden material ({SESSION_WHY})"


def test_every_session_rule_takes_its_locations_from_session_roots(world):
    sr, _, _ = world
    assert sr.labeler_classify(f"{SESSION_DIR}/subagents/agent-a1.jsonl", TASK) == ("forbidden", SESSION_WHY)
    assert sr.labeler_classify(f"{TMP}1000/demo", TASK) == ("forbidden", SESSION_WHY)  # any user's temporary directory
    assert sr.labeler_classify("/fixture", TASK, op="list") == ("forbidden", LISTING_WHY)
    assert sr._redact_labeler(f"{SCRATCH}/a.txt {TMP}0/demo/{SID}/b.txt {SESSION_DIR}/c.txt", None) == (
        "<scratchpad>/a.txt <session-tmp>/b.txt <session-dir>/c.txt")
    # Nothing else in the profile knows the harness's locations: with other roots, the default ones are ordinary paths.
    assert sr.labeler_classify("/root/.claude", TASK) == ("outside", "outside the allowed inputs")
    assert sr.labeler_classify("/tmp/claude-0", TASK) == ("tmp", "the container's temporary directory")
    assert sr.labeler_classify("/root", TASK, op="list") == ("outside", "outside the allowed inputs")


def test_the_default_session_roots_are_the_harness_locations():
    """Unpatched, the profile knows the harness's own directory of records and its temporary directories."""
    sr = _load()
    assert sr.SESSION_ROOTS == sr.SessionRoots()
    assert sr.SESSION_ROOTS._asdict() == {"records": "/root/.claude", "tmp": "/tmp/claude-", "uid": "0"}
    for p in ("/root/.claude", "/tmp/claude-0", "/tmp/claude-1000"):
        assert sr.labeler_classify(p, TASK) == ("forbidden", SESSION_WHY), p
    for p in ("/root", "/tmp"):  # a listing of either shows a session directory
        assert sr.labeler_classify(p, TASK, op="list") == ("forbidden", LISTING_WHY), p
