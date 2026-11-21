"""The natural-agent audit profile (natural-agent:v1, fixed with the natural recipe) and the natural modes of the audit
scripts.

Every agent of the natural arm works in one workspace of its own under ``/home/user/nat_ws/<task>/``. The profile is the
fresh-attempt profile (everything outside that workspace is forbidden; tool inputs and outputs are scanned) with an
allowlist for the study CLI's ``lint-tests`` and ``check-proposals`` on the workspace's own files, a network rule and a
tool set. ``scripts/audit_eval_generators.py --task-dir --profile natural`` records each agent's audit with its own
workspace; ``scripts/strict_reaudit.py --tasks-root`` takes the workspace from that record, and its labeler profile is
parametrised by the task directory and the snapshot root. Every transcript, task, workspace and session location here
is synthetic (tests/natural_task_layout.py builds the task).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest
from natural_task_layout import TASK_ID, build_natural_task

from tracecontract.controlled import (
    FRESH_OUTSIDE,
    NATURAL_CLI_WHY,
    NATURAL_OUTSIDE,
    NATURAL_PROFILE,
    NATURAL_TOOLS_WHY,
    SESSION_DIRS,
    audit_fresh_attempt_transcript,
    audit_natural_agent_transcript,
)

REPO = "/home/user/trace-contract"
CLI = f"{REPO}/.venv/bin/tracecontract"
TASK = TASK_ID  # NP-90
WS = f"/home/user/nat_ws/{TASK}/testgen-initial"
SIBLING = f"/home/user/nat_ws/{TASK}/refcheck"
# Synthetic session locations: what begins each temporary directory, and the directory of records.
SESSION = ("/fixture/session-tmp-", "/fixture/session-records")
SESSION_FILE = "/fixture/session-tmp-0/demo/0b0f1c2e-3d4a-4b5c-8d6e-7f8091a2b3c4/scratchpad/notes.md"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _session(path: Path, calls: list[tuple[str, dict, str]]) -> Path:
    """A transcript in which each call (tool, input, output text) has a tool_use and a tool_result row."""
    rows = [{"type": "user", "uuid": "u0", "parentUuid": None, "sessionId": "s", "timestamp": "2026-01-01T00:00:00Z",
             "message": {"role": "user", "content": "go"}}]
    for i, (tool, ti, out) in enumerate(calls):
        ts = f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}"
        rows.append({"type": "assistant", "uuid": f"a{i}", "parentUuid": "u0", "sessionId": "s", "timestamp": ts + ".000Z",
                     "message": {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": tool, "input": ti}]}})
        rows.append({"type": "user", "uuid": f"r{i}", "parentUuid": f"a{i}", "sessionId": "s", "timestamp": ts + ".500Z",
                     "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": out}]}})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _audit(path: Path, ws: str = WS, **kw) -> tuple[list[dict], list[dict]]:
    return audit_natural_agent_transcript(path, task=TASK, workspace=ws, session_dirs=SESSION, **kw)


def _bash(cmd: str, out: str = "") -> tuple[str, dict, str]:
    return ("Bash", {"command": cmd}, out)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_natural_test", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- the profile: tool inputs

# Calls a natural agent makes in its own workspace: none may be flagged.
CLEAN = [
    ("Read", {"file_path": f"{WS}/contract.json"}, '{"variant": "initial_only"}'),
    _bash(f"cd {WS}/repo && git status --short && grep -rn add fxnat/", " M fxnat/mod.py\n"),
    ("Write", {"file_path": f"{WS}/tests/test_add.py", "content": "import requests\n\ndef test_add():\n    pass\n"}, "ok"),
    ("Edit", {"file_path": f"{WS}/scratch/notes.md", "old_string": "a", "new_string": "b"}, "updated"),
    ("Glob", {"pattern": "**/*.py", "path": f"{WS}/repo"}, f"{WS}/repo/fxnat/mod.py\n"),
    ("Grep", {"pattern": "def add", "path": f"{WS}/repo"}, f"{WS}/repo/fxnat/mod.py\n"),
    _bash(f"{WS}/run_python.sh -c 'import socket, urllib.request; print(1)'", "1\n"),  # the sandbox runs offline
    _bash(f"{WS}/run_tests.sh -q tests/test_mod.py", "tests/test_mod.py .\n/repo/tests/test_mod.py:3: ok\n"),
    _bash(f"cd {WS} && python3 -c \"import json; print(json.load(open('{WS}/contract.json'))['variant'])\"", "initial_only\n"),
    _bash("pip install --no-index --find-links /usr/share/wheels iniconfig"),
    _bash("ls /usr/lib/python3", "dist-packages\n"),
    # Common forms that the shared shell parser took for reads of the repository, or for network use:
    _bash(f"head -n 20 {WS}/repo/fxnat/mod.py"),  # an option's value is not a path
    _bash(f"sed -n '1,20p' {WS}/repo/fxnat/mod.py && sed -i 's/a + b/b + a/' {WS}/repo/fxnat/mod.py"),  # sed scripts
    _bash(f"grep -rn --include '*.py' 'fxnat/mod' {WS}/repo"),  # a grep pattern, an option's value
    _bash(f"jq . {WS}/contract.json"),  # jq's filter
    _bash(f"bash -c 'ls {WS}/repo' && sh -c 'cat {WS}/contract.json'", "fxnat\n{}"),  # a shell's command string
    _bash(f"cat > {WS}/scratch/notes.txt <<'EOF'\nimport socket would reach the network\nEOF\n"
          "python3 - <<'EOF2'\nprint(1)\nEOF2"),
    _bash("command -v curl", "/usr/bin/curl\n"),  # a lookup, not a call
    _bash("python3 -c 'from urllib.parse import quote; print(quote(\"a b\"))'", "a%20b\n"),
    _bash(f"cat {WS}/reference.diff", "--- a/fxnat/mod.py\n+++ b/fxnat/mod.py\n@@ -1 +1 @@\n"),  # the workspace's own diff
    _bash(f"git -C {WS}/repo diff", "diff --git a/fxnat/mod.py b/fxnat/mod.py\n"),
    ("StructuredOutput", {"tests": [f"{WS}/tests/test_add.py"]}, "ok"),
]
# The allowlisted CLI calls: the CLI by its absolute path, lint-tests or check-proposals, paths inside the workspace.
ALLOWLISTED = [
    _bash(f"{CLI} lint-tests {WS}/tests", '{"issues": [], "ok": true}'),
    _bash(f"{CLI} lint-tests {WS}/tests 2>&1; echo \"exit=$?\"", '{"issues": [], "ok": true}\nexit=0'),
    _bash(f"cd {WS} && {CLI} lint-tests tests > {WS}/scratch/lint.json", ""),
    _bash(f"T={WS}/tests; {CLI} lint-tests $T | head -40", ""),
    _bash(f"timeout 60 {CLI} check-proposals {WS}/session_events.json {WS}/proposals.json", '{"rejected_proposals": []}'),
    _bash(f"{CLI} check-proposals --variant initial_only {WS}/session_events.json {WS}/proposals.json >/dev/null 2>&1", ""),
    _bash(f"{CLI}  lint-tests {WS}/tests", '{"issues": [], "ok": true}'),  # spaced as the agent liked
    _bash(f"pushd {WS} && {CLI} lint-tests tests; popd", ""),
]
# CLI calls outside the allowlist: each is a hit (NATURAL_CLI_WHY).
NOT_ALLOWLISTED = [
    f"{CLI} lint-tests {SIBLING}/tests",                          # another agent's workspace
    f"{CLI} lint-tests {REPO}/data/natural/tasks/{TASK}/verifiers/reference_check/tests",
    f"{CLI} grade data/natural/tasks/{TASK} initial_plain {TASK}-reference",  # any other subcommand
    f"{CLI} snapshot {WS}/repo",                                  # even on the workspace's own files
    f"{CLI} add-candidate data/natural/tasks/{TASK} {TASK}-dev-alt-x --state-dir {WS}/repo",  # the host registers
    f"{CLI} check-proposals --proposer x {WS}/session_events.json {WS}/proposals.json",  # an option not on the list
    f"{CLI} lint-tests {WS}/tests > /tmp/lint.json",              # output outside the workspace
    f"cd {REPO} && .venv/bin/tracecontract lint-tests {WS}/tests",  # not by its absolute path
    f"tracecontract lint-tests {WS}/tests",
    f"{REPO}/.venv/bin/python -m tracecontract lint-tests {WS}/tests",
    f"{CLI} lint-tests tests",                                    # relative to the repository, where a call starts
]


def test_a_clean_natural_session_has_no_flag(tmp_path):
    hits, exposures = _audit(_session(tmp_path / "t.jsonl", CLEAN + ALLOWLISTED))
    assert hits == [] and exposures == [], (hits, exposures)


def test_each_allowlisted_cli_call_passes_alone(tmp_path):
    for i, call in enumerate(ALLOWLISTED):
        hits, exposures = _audit(_session(tmp_path / f"a{i}.jsonl", [call]))
        assert hits == [] and exposures == [], (call, hits)


def test_cli_calls_outside_the_allowlist_are_hits(tmp_path):
    for i, cmd in enumerate(NOT_ALLOWLISTED):
        hits, _ = _audit(_session(tmp_path / f"n{i}.jsonl", [_bash(cmd)]))
        assert NATURAL_CLI_WHY in {h["why"] for h in hits}, (cmd, hits)
    # The CLI's own path is reported once, as the CLI call, not again as a path named in the input.
    hits, _ = _audit(_session(tmp_path / "grade.jsonl", [_bash(NOT_ALLOWLISTED[2])]))
    assert [h["path"] for h in hits if h["path"] == CLI] == [CLI]
    assert ("held-out candidate named in a CLI command" not in {h["why"] for h in hits})  # the reference is not held out
    hits, _ = _audit(_session(tmp_path / "pre.jsonl", [_bash(f"{CLI} grade data/natural/tasks/{TASK} c1 {TASK}-pre-review")]))
    assert ("held-out candidate named in a CLI command", f"{TASK}-pre-review") in {(h["why"], h["path"]) for h in hits}


def test_the_cli_is_named_literally(tmp_path):
    """A variable for the CLI names the repository in its assignment: flagged, as every other path into the repository."""
    hits, _ = _audit(_session(tmp_path / "v.jsonl", [_bash(f"C={CLI}; $C lint-tests {WS}/tests")]))
    assert hits and all(h["why"] != NATURAL_CLI_WHY for h in hits)


# (tool, input, the network use reported as the hit's path)
NETWORK = [
    ("WebFetch", {"url": "https://example.org/fix", "prompt": "summarise"}, "https://example.org/fix"),
    ("WebSearch", {"query": "fxnat add none"}, "fxnat add none"),
    ("mcp__github__get_file_contents", {"owner": "o", "repo": "r", "path": "x.py"}, "mcp__github__get_file_contents"),
    ("Bash", {"command": "curl -sL https://example.org/x.patch -o /tmp/x.patch"}, "curl"),
    ("Bash", {"command": f"cd {WS} && wget -q https://example.org/x"}, "wget"),
    ("Bash", {"command": "nc -z example.org 443"}, "nc"),
    ("Bash", {"command": "ssh example.org ls"}, "ssh"),
    ("Bash", {"command": "gh pr view 12 --repo o/r"}, "gh"),
    ("Bash", {"command": f"cd {WS}/repo && git fetch origin pull/12/head"}, "git fetch"),
    ("Bash", {"command": f"git -C {WS}/repo clone https://example.org/r.git {WS}/scratch/r"}, "git clone"),
    ("Bash", {"command": f"cd {WS}/repo && git pull"}, "git pull"),
    ("Bash", {"command": "git ls-remote https://example.org/r.git"}, "git ls-remote"),
    ("Bash", {"command": f"cd {WS}/repo && git remote -v"}, "git remote"),
    ("Bash", {"command": "pip download fxnat==0.2"}, "pip download"),
    ("Bash", {"command": "pip install fxnat==0.2"}, "pip install"),
    ("Bash", {"command": "python3 -m pip install --user fxnat"}, "pip install"),
    ("Bash", {"command": "python3 -c 'import urllib.request as u; u.urlopen(\"https://example.org\")'"}, "urllib.request"),
    ("Bash", {"command": "python3 - <<'EOF'\nfrom http import client\nclient.HTTPSConnection('example.org')\nEOF"}, "http.client"),
    ("Bash", {"command": "python3 -c \"import os, socket; socket.create_connection(('example.org', 443))\""}, "socket"),
    ("Bash", {"command": "python3 -Ic 'import requests; requests.get(\"https://example.org\")'"}, "requests"),
    ("Bash", {"command": "python3 -c \"__import__('httpx').get('https://example.org')\""}, "httpx"),
    ("Bash", {"command": f"cat > {WS}/scratch/f.py <<'EOF'\nimport requests\nEOF\npython3 {WS}/scratch/f.py"}, "requests"),
    ("Bash", {"command": "bash -c 'curl -s https://example.org'"}, "curl"),
    ("Bash", {"command": "bash -lc 'wget -q https://example.org'"}, "wget"),
    ("Bash", {"command": "pip --cache-dir /tmp/pc install fxnat"}, "pip install"),
    ("Bash", {"command": "python3 -m http.server 8000"}, "http.server"),
    # Wrappers with their options' values, code on standard input, other package managers and container engines:
    ("Bash", {"command": "nice -n 10 curl -s https://example.org/x"}, "curl"),
    ("Bash", {"command": "nice -n 10 python3 -c 'import urllib.request as u; u.urlopen(\"https://example.org\")'"},
     "urllib.request"),
    ("Bash", {"command": "timeout -s KILL 10 curl -s https://example.org/x"}, "curl"),
    ("Bash", {"command": "ionice -c 3 wget -q https://example.org/x"}, "wget"),
    ("Bash", {"command": "env -u HTTPS_PROXY curl -s https://example.org/x"}, "curl"),
    ("Bash", {"command": "time -p curl -s https://example.org/x"}, "curl"),
    ("Bash", {"command": "python3 <<'EOF'\nimport socket\nsocket.create_connection(('example.org', 443))\nEOF"}, "socket"),
    ("Bash", {"command": "python3 -c 'from socket import *; create_connection((\"example.org\", 443))'"}, "socket"),
    ("Bash", {"command": "echo 'import socket' | python3"}, "socket"),
    ("Bash", {"command": "python3 <<< 'import requests'"}, "requests"),
    ("Bash", {"command": "bash <<'EOF'\ncurl -s https://example.org\nEOF"}, "curl"),
    ("Bash", {"command": "sh -s <<'EOF'\nwget -q https://example.org\nEOF"}, "wget"),
    ("Bash", {"command": "x=\"$(curl -s https://example.org)\"; echo \"$x\""}, "curl"),
    ("Bash", {"command": "# don't fetch anything here\ncurl -s https://example.org"}, "curl"),
    ("Bash", {"command": "find . -name '*.txt' -exec curl -T {} https://example.org \\;"}, "curl"),
    ("Bash", {"command": f"docker run --rm -v {WS}/repo:/repo -w /repo python:3.11 pip download fxnat"}, "docker run"),
    ("Bash", {"command": "docker pull python:3.11"}, "docker pull"),
    ("Bash", {"command": f"cd {WS}/repo && uv add requests"}, "uv add"),
    ("Bash", {"command": "pipx install httpie"}, "pipx install"),
    ("Bash", {"command": f"cd {WS}/scratch && npm install left-pad"}, "npm install"),
    ("Bash", {"command": "apt-get install -y curl"}, "apt-get install"),
    ("Bash", {"command": f"cd {WS}/repo && git submodule update --init"}, "git submodule update"),
    ("Bash", {"command": "node -e \"require('https').get('https://example.org')\""}, "node"),
]
# Scripts the agent wrote and then ran on the host, as the shell runs them: (calls, the network use reported)
SCRIPT_RUNS = [
    ([("Write", {"file_path": f"{WS}/scratch/get.sh", "content": "#!/bin/sh\ncurl -s https://example.org\n"}, "ok"),
      _bash(f"chmod +x {WS}/scratch/get.sh && {WS}/scratch/get.sh")], "curl"),
    ([("Write", {"file_path": f"{WS}/scratch/get.py", "content": "#!/usr/bin/env python3\nimport socket\n"}, "ok"),
      _bash(f"cd {WS}/scratch && chmod +x get.py && ./get.py")], "socket"),
    ([("Write", {"file_path": f"{WS}/scratch/s.py", "content": "import socket\n"}, "ok"), _bash(f"python3 < {WS}/scratch/s.py")],
     "socket"),
    ([("Write", {"file_path": f"{WS}/scratch/s.py", "content": "import socket\n"}, "ok"),
      _bash(f"cat {WS}/scratch/s.py | python3")], "socket"),
    ([("Write", {"file_path": f"{WS}/scratch/g.sh", "content": "wget -q https://example.org\n"}, "ok"),
      _bash(f"bash < {WS}/scratch/g.sh")], "wget"),
    ([_bash(f"echo 'import requests' > {WS}/scratch/e.py"), _bash(f"python3 {WS}/scratch/e.py")], "requests"),
    ([("Write", {"file_path": f"{WS}/scratch/helper.py", "content": "import httpx\n"}, "ok"),
      ("Write", {"file_path": f"{WS}/scratch/main.py", "content": "import helper\n"}, "ok"),
      _bash(f"cd {WS}/scratch && python3 main.py")], "httpx"),
    ([("Write", {"file_path": f"{WS}/scratch/s.py", "content": "import socket\n"}, "ok"),
      _bash(f"python3 -c \"exec(open('{WS}/scratch/s.py').read())\"")], "socket"),
]


def test_network_use_is_flagged(tmp_path):
    for i, (tool, ti, what) in enumerate(NETWORK):
        hits, _ = _audit(_session(tmp_path / f"w{i}.jsonl", [(tool, ti, "")]))
        net = [h for h in hits if h["why"].startswith("network: ")]
        assert [h["path"] for h in net] == [what], (ti, hits)


def test_scripts_the_agent_ran_however_the_shell_runs_them(tmp_path):
    for i, (calls, what) in enumerate(SCRIPT_RUNS):
        hits, _ = _audit(_session(tmp_path / f"s{i}.jsonl", calls))
        assert [h["path"] for h in hits if h["why"].startswith("network: ")] == [what], (calls[-1], hits)


def test_a_script_the_agent_wrote_is_read_when_it_runs(tmp_path):
    """A script written with the Write tool and run later on the host is scanned; written but not run, it is not."""
    write = ("Write", {"file_path": f"{WS}/scratch/get.py", "content": "import socket\nprint(socket.gethostname())\n"}, "ok")
    hits, _ = _audit(_session(tmp_path / "w.jsonl", [write]))
    assert hits == []
    hits, _ = _audit(_session(tmp_path / "r.jsonl", [write, _bash(f"cd {WS}/scratch && python3 get.py")]))
    assert [(h["path"], h["why"]) for h in hits] == [("socket", "network: host Python code that imports socket")]
    hits, _ = _audit(_session(tmp_path / "s.jsonl", [write, _bash(f"{WS}/run_python.sh {WS}/scratch/get.py")]))
    assert hits == []  # the sandbox runs it offline


# Reads outside the workspace: each is a hit.
OUTSIDE = [
    ("Read", {"file_path": f"{REPO}/data/natural/tasks/{TASK}/session.json"}),
    _bash(f"ls {REPO}/data/natural/tasks/{TASK}/candidates")[:2],
    _bash(f"cat {REPO}/data/natural/snapshots/{TASK}/fxnat/mod.py")[:2],
    ("Read", {"file_path": "/home/user/ext/aidev-v5/pr_review_comments.parquet"}),
    _bash("git -C /home/user/ext/clones/fxnat.git log -p")[:2],
    ("Read", {"file_path": f"{SIBLING}/tests/test_ref.py"}),
    _bash(f"ls /home/user/nat_ws/{TASK}")[:2],
    _bash("ls /home/user/nat_runrec")[:2],
    ("Read", {"file_path": SESSION_FILE}),
    ("Read", {"file_path": "/fixture/session-records/projects/demo/x.jsonl"}),
    ("Read", {"file_path": "/root/.config/gh/hosts.yml"}),
    _bash("cat README.md")[:2],  # the cwd of a subagent's Bash call is the repository
    ("Grep", {"pattern": "add"}),
    _bash("cat /tmp/notes.txt")[:2],
]


def test_reads_outside_the_workspace_are_hits(tmp_path):
    for i, (tool, ti) in enumerate(OUTSIDE):
        hits, _ = _audit(_session(tmp_path / f"o{i}.jsonl", [(tool, ti, "")]))
        assert hits, (tool, ti)
    hits, _ = _audit(_session(tmp_path / "tmp.jsonl", [_bash("cat /tmp/notes.txt")]))
    assert [h["why"] for h in hits] == [NATURAL_OUTSIDE]
    hits, _ = _audit(_session(tmp_path / "sd.jsonl", [("Read", {"file_path": SESSION_FILE}, "")]))
    assert [h["why"] for h in hits] == ["a Claude session directory"]


def test_a_relative_path_is_resolved_where_its_segment_runs(tmp_path):
    """Every Bash call starts in the repository root: the directory an earlier call ended in exempts no path named in a
    later call, inline code included (it is a conservative extra of the path scan only), and a cd later in the same
    command does not either."""
    cd = _bash(f"cd {WS}/repo && git status --short")
    for rel in ("tests/test_mod.py", "src/tracecontract/natural_pr.py", "docs/decision_log.md"):
        code = f"python3 -c \"print(open('{rel}').read())\""
        for i, calls in enumerate(([cd, _bash(code)], [_bash(f"{code}; cd {WS}/repo")])):
            hits, _ = _audit(_session(tmp_path / f"r{i}.jsonl", calls))
            assert (f"{REPO}/{rel}", "path named in the tool input: inside forbidden material") in {
                (h["path"], h["why"]) for h in hits}, (calls[-1], hits)
    hits, _ = _audit(_session(tmp_path / "ws.jsonl", [cd, _bash(f"cd {WS}/repo && {code}")]))
    assert hits == []  # after a cd in the same call it reads the workspace


# Reads that the shared shell parser did not see: each is a hit on the repository (the directory every call starts in).
HIDDEN_READS = ["ls", "ls -la", "tree", "du -sh", "git log", "git commit -am wip", "git checkout -- .",
                "nice -n 10 cat docs/x.md", "env -u X cat docs/x.md", "eval 'cat docs/x.md'", 'echo "$(cat docs/x.md)"',
                "cat < docs/x.md", "bash -c 'cat docs/x.md'", "while read l; do echo $l; done < docs/x.md",
                f"{REPO}/.venv/bin/python -c 'print(1)'", "mkdir -p docs/new && touch data/x"]


def test_reads_the_natural_shell_model_finds(tmp_path):
    for i, cmd in enumerate(HIDDEN_READS):
        hits, _ = _audit(_session(tmp_path / f"h{i}.jsonl", [_bash(f"cd {WS} && pwd"), _bash(cmd)]))
        assert any(h["path"] == REPO or h["path"].startswith(REPO + "/") for h in hits), (cmd, hits)


def test_tools_outside_the_tool_set_are_hits(tmp_path):
    for tool in ("Task", "TodoWrite", "ToolSearch", "MultiEdit", "NotebookEdit"):  # the recipe's set: no MultiEdit
        hits, _ = _audit(_session(tmp_path / f"{tool}.jsonl", [(tool, {"x": 1}, "")]))
        assert [(h["path"], h["why"]) for h in hits] == [(tool, NATURAL_TOOLS_WHY)]


# --------------------------------------------------------------------------- the profile: tool outputs


def test_tool_outputs_are_scanned(tmp_path):
    cases = [  # (call, flagged in the outputs)
        (_bash(f"cd {WS} && ls", f"{TASK}-pre-review.patch\n"), {(f"{TASK}-pre-review", "held-out candidate named in a tool output")}),
        (_bash(f"cd {WS} && ls", f"{TASK}-eval-nm-2\n"), {(f"{TASK}-eval-nm-2", "held-out candidate named in a tool output")}),
        (_bash(f"cd {WS} && cat manifest.json", f'"from": "{REPO}/data/natural/tasks/{TASK}/candidates/x.json"\n'),
         {(f"{REPO}/data/natural/tasks/{TASK}/candidates/x.json", "shown in a tool output: inside forbidden material")}),
        # the allowlisted CLI reports paths relative to its arguments, in the workspace: not exposures
        (_bash(f"{CLI} lint-tests {WS}/tests", '{"issues": [{"path": "sub/test_a.py", "line": 3}], "ok": false}'), set()),
        # an absolute path into the repository in its output still is one
        (_bash(f"{CLI} lint-tests {WS}/tests", f'  File "{REPO}/src/tracecontract/verifier.py", line 9\n'),
         {(f"{REPO}/src/tracecontract/verifier.py", "shown in a tool output: inside forbidden material")}),
        (_bash(f"{WS}/run_tests.sh -q", "tests/test_mod.py .\n/repo/fxnat/mod.py:2\n"), set()),
        (_bash(f"{WS}/run_tests.sh -q", f"{SESSION_FILE}\n"), {(SESSION_FILE, "shown in a tool output: a Claude session directory")}),
        # a command that named only the workspace's own files showed them: their relative paths are the workspace's
        (_bash(f"cat {WS}/reference.diff", "--- a/fxnat/mod.py\n+++ b/fxnat/mod.py\n"), set()),
        (_bash(f"git -C {WS}/repo diff", "diff --git a/fxnat/mod.py b/fxnat/mod.py\n"), set()),
        (_bash(f"cat {WS}/notes.md", "../../../trace-contract/docs/x.md\n"),  # unless they lead out of it
         {(f"{REPO}/docs/x.md", "shown in a tool output: inside forbidden material")}),
        (_bash(f"cat {WS}/notes.md", f"{REPO}/docs/x.md\n"),
         {(f"{REPO}/docs/x.md", "shown in a tool output: inside forbidden material")}),
    ]
    for i, (call, expect) in enumerate(cases):
        hits, exposures = _audit(_session(tmp_path / f"x{i}.jsonl", [call]))
        assert hits == [] and {(x["path"], x["why"]) for x in exposures} == expect, (call, hits, exposures)


# --------------------------------------------------------------------------- the profile's arguments and the other profiles


def test_the_workspace_must_be_a_dedicated_directory_outside_the_repository(tmp_path):
    t = _session(tmp_path / "t.jsonl", [])
    with pytest.raises(ValueError, match="dedicated directory"):
        _audit(t, ws="/nat")
    with pytest.raises(ValueError, match="outside the repository"):
        _audit(t, ws=f"{REPO}/scratch/ws")
    assert SESSION_DIRS == ("/tmp/claude-", "/root/.claude")  # the harness's locations, the default


def test_the_fresh_attempt_profile_is_unchanged(tmp_path):
    """The fresh-attempt profile allowlists no CLI call, has no network rule or tool set, and keeps its parser's words
    (the natural profile's refinements are its own); the CS fixtures of tests/test_generator_audit.py check the rest."""
    ws = "/srv/tc-attempts/CS-01-fresh-A-u1-1"
    t = _session(tmp_path / "f.jsonl", [_bash(f"{CLI} lint-tests {ws}/tests"), _bash("curl -s https://example.org"),
                                        ("TodoWrite", {"todos": []}, "")])
    hits, _ = audit_fresh_attempt_transcript(t, task="CS-01", workspace=ws)
    assert [(h["path"], h["why"]) for h in hits] == [(CLI, "path named in the tool input: inside forbidden material")]
    t = _session(tmp_path / "v.jsonl", [_bash(f"T={ws}/tests; ls $T")])
    assert [h["path"] for h in audit_fresh_attempt_transcript(t, task="CS-01", workspace=ws)[0]] == [f"{REPO}/T={ws}/tests"]
    assert _audit(t, ws=ws)[0] == []
    assert FRESH_OUTSIDE != NATURAL_OUTSIDE


# --------------------------------------------------------------------------- scripts/audit_eval_generators.py --profile natural


@pytest.fixture
def natural_task(tmp_path):
    """The synthetic natural task under <tmp>/repo/data/natural, and an agent workspace of it under <tmp>/nat_ws."""
    nt = build_natural_task(tmp_path / "repo", index=False)
    ws = tmp_path / "nat_ws" / TASK / "testgen-initial"
    ws.mkdir(parents=True)
    (ws / "manifest.json").write_text(json.dumps({"task_id": TASK, "role": "testgen-initial"}), encoding="utf-8")
    return nt, ws


def test_audit_eval_generators_natural_profile_records_the_workspace(natural_task, tmp_path):
    ag = _load("audit_eval_generators")
    nt, ws = natural_task
    t = _session(tmp_path / "agent-g.jsonl", [_bash(f"{CLI} lint-tests {ws}/tests"),
                                              ("Read", {"file_path": f"{REPO}/data/natural/tasks/{TASK}/session.json"}, ""),
                                              _bash(f"cd {ws} && ls", f"{TASK}-pre-review.patch\n")])
    assert ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{ws}"]) == 0
    out = json.loads((nt.task_dir / "labels" / "generator_audit.json").read_text())
    rec = out["testgen-initial"]
    assert (rec["transcript_sha256"], rec["own_workspace"], rec["profile"], rec["flagged"]) == (
        hashlib.sha256(t.read_bytes()).hexdigest(), str(ws), NATURAL_PROFILE, True)
    assert [h["path"] for h in rec["hits"]] == [f"{REPO}/data/natural/tasks/{TASK}/session.json"]
    assert [x["path"] for x in rec["exposures"]] == [f"{TASK}-pre-review"]
    assert out["_rules"]["profile"] == NATURAL_PROFILE
    # A written assessment survives a re-run of the same audit, and is dropped when the audit changes.
    rec["assessment"] = "read in the transcript: synthetic"
    (nt.task_dir / "labels" / "generator_audit.json").write_text(json.dumps(out), encoding="utf-8")
    ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{ws}"])
    assert json.loads((nt.task_dir / "labels" / "generator_audit.json").read_text())["testgen-initial"]["assessment"]
    _session(t, [_bash(f"{CLI} lint-tests {ws}/tests")])
    ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{ws}"])
    rec = json.loads((nt.task_dir / "labels" / "generator_audit.json").read_text())["testgen-initial"]
    assert "assessment" not in rec and rec["flagged"] is False


def test_audit_eval_generators_refuses_mismatched_profiles_and_workspaces(natural_task, tmp_path):
    ag = _load("audit_eval_generators")
    nt, ws = natural_task
    t = _session(tmp_path / "agent-g.jsonl", [])
    with pytest.raises(SystemExit, match="--profile natural"):
        ag.cli(["--task-dir", str(nt.task_dir), f"{t}:{ws}"])  # the controlled profile on a natural task
    cs = tmp_path / "repo" / "tasks" / "CS-90"
    cs.mkdir(parents=True)
    (cs / "task.json").write_text(json.dumps({"task_id": "CS-90", "population": "controlled"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="natural agents only"):
        ag.cli(["--task-dir", str(cs), "--profile", "natural", f"{t}:{ws}"])
    other = tmp_path / "nat_ws" / TASK / "refcheck"
    other.mkdir()
    (other / "manifest.json").write_text(json.dumps({"task_id": TASK, "role": "refcheck"}), encoding="utf-8")
    wrong = tmp_path / "nat_ws" / "NP-91" / "labeler"
    wrong.mkdir(parents=True)
    (wrong / "manifest.json").write_text(json.dumps({"task_id": "NP-91", "role": "labeler"}), encoding="utf-8")
    for bad, why in ((ws.parent, "several roles"), (wrong, "names task 'NP-91'"),
                     (ag.R / "tmp-ws", r"around\) the repository"), (nt.task_dir / "ws", r"around\) the task directory")):
        with pytest.raises(SystemExit, match=why):
            ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{bad}"])
    with pytest.raises(SystemExit, match="share the record"):
        ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{ws}", f"{t}:{tmp_path / 'b' / ws.name}"])
    # An attacker's group of workspaces of one role is its own workspace.
    group = tmp_path / "nat_ws" / TASK / "attack-initial"
    for k in (1, 2):
        (group / f"a{k}").mkdir(parents=True)
        (group / f"a{k}" / "manifest.json").write_text(json.dumps({"task_id": TASK, "role": "attack-initial"}), encoding="utf-8")
    assert ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{group}"]) == 0
    assert "attack-initial" in json.loads((nt.task_dir / "labels" / "generator_audit.json").read_text())


def test_audit_eval_generators_first_form_is_unchanged(tmp_path, monkeypatch):
    """The first form writes tasks/<task>/labels/generator_audit.json with the substring rule, as before."""
    ag = _load("audit_eval_generators")
    monkeypatch.setattr(ag, "R", tmp_path)
    own = "/home/user/gen_workspaces/CS-01/eval-nm"
    t = _session(tmp_path / "t.jsonl", [_bash(f"cat {own}/x.py"), _bash("cat tasks/CS-01/candidates/CS-01-eval-alt-1.json")])
    (tmp_path / "tasks" / "CS-01").mkdir(parents=True)
    (tmp_path / "tasks" / "CS-01" / "task.json").write_text(json.dumps({"task_id": "CS-01", "population": "controlled"}))
    assert ag.cli(["CS-01", f"{t}:{own}"]) == 0
    out = json.loads((tmp_path / "tasks" / "CS-01" / "labels" / "generator_audit.json").read_text())
    assert list(out) == ["eval-nm", "_rules"] and list(out["eval-nm"]) == ["transcript_sha256", "hits"]
    assert [h["match"] for h in out["eval-nm"]["hits"]] == ["tasks/CS-01/candidates"]
    assert out["_rules"] == {"forbidden_substrings": list(ag._controlled_forbidden("CS-01")),
                             "allowed": ["the agent's own exported workspace", "/root/.local/bin/"],
                             "scope": "tool inputs only (commands and file paths an agent passed to its tools); tool outputs "
                                      "are not inspected (decision log D37)", "script": "scripts/audit_eval_generators.py"}


def test_audit_eval_generators_first_form_refuses_natural_and_unknown_tasks(natural_task, tmp_path, monkeypatch):
    """The first form writes under tasks/, which git tracks: a natural family's records (excerpts of its agents' tool
    inputs) may not go there, and neither may those of a task that is not one."""
    ag = _load("audit_eval_generators")
    nt, ws = natural_task
    monkeypatch.setattr(ag, "R", nt.root)
    t = _session(tmp_path / "t.jsonl", [_bash(f"cat {REPO}/data/natural/tasks/{TASK}/session.json")])
    for task, why in ((TASK, "no task directory"), ("CS-77", "no task directory")):
        with pytest.raises(SystemExit, match=why):
            ag.cli([task, f"{t}:{ws}"])
    misplaced = nt.root / "tasks" / TASK  # a natural task under tasks/
    misplaced.mkdir(parents=True)
    (misplaced / "task.json").write_text((nt.task_dir / "task.json").read_text())
    with pytest.raises(SystemExit, match="--profile natural"):
        ag.cli([TASK, f"{t}:{ws}"])
    assert not (misplaced / "labels").exists() and not (nt.root / "tasks" / "CS-77").exists()


def test_audit_eval_generators_groups_and_records(natural_task, tmp_path):
    """Only an attacker's states make a group that is one workspace; a record that names another workspace is not
    replaced; and the rules written name no decision-log number."""
    ag = _load("audit_eval_generators")
    nt, ws = natural_task
    t = _session(tmp_path / "agent-g.jsonl", [])

    def workspace(path: Path, role: str) -> Path:
        path.mkdir(parents=True)
        (path / "manifest.json").write_text(json.dumps({"task_id": TASK, "role": role}), encoding="utf-8")
        return path

    mappers = tmp_path / "nat_ws" / TASK / "mappers"
    for k in (1, 2):
        workspace(mappers / f"mapper-{k}", "mapper")
    with pytest.raises(SystemExit, match="several agents of role 'mapper'"):
        ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{mappers}"])
    group = tmp_path / "nat_ws" / TASK / "attack-full"
    for k in (1, 2):
        workspace(group / f"a{k}", "attack-full")
    with pytest.raises(SystemExit, match="one state of the attacker's group"):
        ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{group / 'a1'}"])
    assert ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{group}"]) == 0
    other = workspace(tmp_path / "elsewhere" / TASK / ws.name, "testgen-initial")  # the same name, another workspace
    assert ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{ws}"]) == 0
    with pytest.raises(SystemExit, match="holds the audit of the workspace"):
        ag.cli(["--task-dir", str(nt.task_dir), "--profile", "natural", f"{t}:{other}"])
    out = json.loads((nt.task_dir / "labels" / "generator_audit.json").read_text())
    assert out[ws.name]["own_workspace"] == str(ws) and out["attack-full"]["own_workspace"] == str(group)
    assert not re.search(r"\bD\d+\b", json.dumps(out["_rules"]))  # the rules are named by the profile, natural-agent:v1


# --------------------------------------------------------------------------- scripts/strict_reaudit.py --tasks-root


@pytest.fixture
def reaudit(tmp_path, monkeypatch):
    """strict_reaudit pointed at a scratch checkout with the synthetic natural task and synthetic session locations."""
    from natural_task_layout import init_git

    sr = _load("strict_reaudit")
    root = tmp_path / "repo"
    nt = build_natural_task(root, index=False)
    init_git(root)  # .gitignore: data/natural/, as the study repository's
    monkeypatch.setattr(sr, "R", root)
    monkeypatch.setattr(sr, "SESSION_ROOTS", sr.SessionRoots(records=SESSION[1], tmp=SESSION[0]))
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    return sr, root, nt, tdir


def _record(nt, entries: dict) -> Path:
    p = nt.task_dir / "labels" / "generator_audit.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**entries, "_rules": {"profile": NATURAL_PROFILE}}), encoding="utf-8")
    return p


def test_reaudit_of_natural_records_uses_the_recorded_workspace(reaudit, tmp_path):
    sr, _, nt, tdir = reaudit
    scratch = SESSION_FILE.rsplit("/", 1)[0]
    t = _session(tdir / "agent-n1.jsonl", [_bash(f"{CLI} lint-tests {WS}/tests"), ("Read", {"file_path": f"{scratch}/plan.md"}, ""),
                                          _bash(f"cd {WS} && ls", f"{TASK}-eval-alt-1\n")])
    audit = _record(nt, {"testgen-initial": {"transcript_sha256": hashlib.sha256(t.read_bytes()).hexdigest(),
                                             "own_workspace": WS, "profile": NATURAL_PROFILE, "hits": [], "exposures": []}})
    report = tmp_path / "outputs.json"
    argv = ["--tasks-root", str(nt.tasks_root), "--transcripts", str(tdir), "--scratch", scratch, "--write", "--outputs", str(report)]
    assert sr.main(argv) == 0
    rec = json.loads(audit.read_text())["testgen-initial"]
    entry = rec["strict_reaudit"]["transcripts"]["main"]
    assert (entry["profile"], entry["own_workspace"]) == (NATURAL_PROFILE, WS)
    # A read of the build session's scratch directory is a hit for a natural agent, not attributed to a writer.
    assert [h["path"] for h in entry["hits"]] == ["<scratchpad>/plan.md"]
    assert [x["path"] for x in entry["exposures"]] == [f"{TASK}-eval-alt-1"]
    assert SESSION[0] not in audit.read_text() and SESSION[0] not in report.read_text()
    assert [x["path"] for x in json.loads(report.read_text())["transcripts"][TASK]["testgen-initial"]["main"]["output_exposures"]] == [
        f"{TASK}-eval-alt-1"]
    # A written assessment is kept while the re-audit finds the same.
    data = json.loads(audit.read_text())
    data["testgen-initial"]["strict_reaudit"]["assessment"] = "read in the transcript: synthetic"
    audit.write_text(json.dumps(data), encoding="utf-8")
    assert sr.main(argv) == 0
    assert json.loads(audit.read_text())["testgen-initial"]["strict_reaudit"]["assessment"]


def test_reaudit_takes_a_controlled_agents_workspace_from_its_record(tmp_path, monkeypatch):
    """A generator record that names its own workspace is audited in it, whatever the prompt names."""
    sr = _load("strict_reaudit")
    root, tdir = tmp_path / "repo", tmp_path / "transcripts"
    tdir.mkdir()
    own = "/home/user/gen_workspaces/CS-01/eval-alt-9"
    t = _session(tdir / "agent-c.jsonl", [_bash(f"cat {own}/repo/x.py")])
    audit = root / "tasks" / "CS-01" / "labels" / "generator_audit.json"
    audit.parent.mkdir(parents=True)
    sha = hashlib.sha256(t.read_bytes()).hexdigest()
    for workspace, n_hits in ((None, 1), (own, 0)):
        rec = {"transcript_sha256": sha, **({"own_workspace": workspace} if workspace else {})}
        audit.write_text(json.dumps({"eval-nm": rec}), encoding="utf-8")
        monkeypatch.setattr(sr, "R", root)
        assert sr.main(["--transcripts", str(tdir), "--scratch", "/fixture/scratch", "--write"]) == 0
        entry = json.loads(audit.read_text())["eval-nm"]["strict_reaudit"]["transcripts"]["main"]
        assert len(entry["hits"]) == n_hits and entry["own_workspace"] == (workspace or "/home/user/gen_workspaces/CS-01/eval-nm")


# --------------------------------------------------------------------------- the labeler profile, parametrised


LABELER_WS = f"/home/user/nat_ws/{TASK}/labeler"
TD = f"{REPO}/data/natural/tasks/{TASK}"


def _natural_layout(sr, ws: str | None = LABELER_WS):
    return sr.labeler_layout(TASK, task_dir=TD, snapshot_root=f"{REPO}/data/natural/snapshots", workspace=ws, natural=True)


def test_the_labeler_layout_of_a_natural_task(reaudit):
    sr, _, _, _ = reaudit
    lay = _natural_layout(sr)

    def cls(p: str, op: str = "read") -> tuple[str, str]:
        return sr.labeler_classify(p, TASK, op=op, families=(TASK,), layout=lay)

    assert cls(f"{LABELER_WS}/contract.json")[0] == "allowed"
    assert cls(f"{LABELER_WS}/repo/fxnat/mod.py")[0] == "allowed"
    assert cls(f"{LABELER_WS}/tests/test_a.py") == ("own", "its own tests directory")
    assert cls(f"{LABELER_WS}/scratch/n.md") == ("own", "its private scratch directory")
    assert cls(f"{TD}/contracts/reference.json") == ("allowed", "the reference contract")
    assert cls(f"{REPO}/data/natural/snapshots/{TASK}/fxnat/mod.py") == ("allowed", "the base snapshot")
    assert cls(f"{TD}/candidates/{TASK}-pre-review.json") == ("forbidden", "a candidate")
    assert cls(f"{TD}/candidates/{TASK}-reference.json")[1].startswith("the reference solution")
    assert cls(f"{TD}/verifiers/reference_check/tests/t.py") == ("forbidden", "a reference check")
    assert cls(f"{TD}/verifiers/diff_derived/tests/t.py") == ("forbidden", "a generated verifier")
    assert cls(f"{TD}/verifiers/independent_label/status.json")[0] == "forbidden"
    assert cls(f"{REPO}/data/natural/tasks/NP-91/verifiers/repo_tests/spec.json") == ("forbidden", "a generated verifier of another family")
    assert cls(f"{REPO}/tasks/CS-01/verifiers/reference_check/tests/t.py") == ("forbidden", "a reference check of another family")
    assert cls(f"{REPO}/data/natural/snapshots/NP-91/x.py") == ("outside", "another family's base snapshot")
    assert cls(f"{REPO}/data/natural/s10_work/{TASK}/round-0/x.py")[0] == "forbidden"
    assert cls(f"{TD}/session.json")[0] == "outside"
    assert cls(f"/home/user/nat_ws/{TASK}/refcheck/tests/t.py") == ("forbidden", "another agent's workspace")
    assert cls("/home/user/nat_ws/NP-91/labeler/tests/t.py") == ("forbidden", "another agent's workspace")
    assert cls("/home/user/nat_runrec/NP-90/rc-ref-1.json")[0] == "forbidden"
    assert cls(f"{TD}/verifiers", "list")[0] == "forbidden" and cls(f"/home/user/nat_ws/{TASK}", "list")[0] == "forbidden"
    # Without a recorded workspace, the task's tests directory is the writer's own and the workspace is outside.
    lay = _natural_layout(sr, None)
    assert sr.labeler_own(TASK, layout=lay) == f"{TD}/verifiers/independent_label/tests"
    assert sr.labeler_classify(f"{LABELER_WS}/contract.json", TASK, layout=lay)[0] == "outside"


def test_the_default_labeler_layout_is_the_controlled_one(reaudit):
    sr, _, _, _ = reaudit
    assert sr.labeler_own("CS-01") == f"{REPO}/tasks/CS-01/verifiers/independent_label/tests"
    assert [p for p, _ in sr.labeler_allowed("CS-01")] == [
        f"{REPO}/tasks/CS-01/contracts/reference.json", f"{REPO}/snapshots/CS-01",
        f"{REPO}/src/tracecontract/sandbox/harness/tc_sandbox.py", f"{REPO}/src/tracecontract/verifier.py",
        f"{REPO}/tests/fixtures/harbor_fx01/tasks/FX-01/verifiers/v1"]
    assert sr.labeler_classify(f"{REPO}/tasks/CS-01/verifiers/diff_derived/tests/t.py", "CS-01") == ("forbidden", "a generated verifier")
    assert sr.labeler_classify(f"{REPO}/data/natural/tasks/{TASK}/verifiers/x", "CS-01") == ("outside", "outside the allowed inputs")
    assert "diff_derived" in sr._GENERATED


def test_labeler_mode_with_a_natural_tasks_root(reaudit, tmp_path):
    sr, _, nt, tdir = reaudit
    ref_line = 'assert add(2, None) == 2, "the missing second argument counts as zero"'
    rc = nt.task_dir / "verifiers" / "reference_check" / "tests" / "test_ref.py"
    rc.parent.mkdir(parents=True)
    rc.write_text(f"def test_reference_missing_second():\n    {ref_line}\n", encoding="utf-8")
    (nt.task_dir / "contracts").mkdir()
    (nt.task_dir / "contracts" / "reference.json").write_text(json.dumps(
        {"contract_id": f"{TASK}-reference", "requirements": [{"req_id": "R-second", "statement": "add(2, None) == 2"}]}),
        encoding="utf-8")
    writer = _session(tdir / "agent-l1.jsonl", [
        ("Read", {"file_path": f"{LABELER_WS}/contract.json"}, '{"variant": "reference"}'),
        ("Write", {"file_path": f"{LABELER_WS}/tests/test_second.py", "content": "def test_second():\n    pass\n"}, "ok"),
        _bash(f"{CLI} lint-tests {LABELER_WS}/tests", '{"issues": [], "ok": true}'),
        ("Read", {"file_path": f"{TD}/candidates/{TASK}-pre-review.json"}, ""),
        _bash(f"cat /home/user/nat_ws/{TASK}/refcheck/tests/test_ref.py", f"    {ref_line}\n"),
    ])
    reviser = _session(tdir / "agent-l2.jsonl", [], )
    _record(nt, {"labeler": {"transcript_sha256": _sha(writer), "own_workspace": LABELER_WS, "profile": NATURAL_PROFILE}})
    rev_prompt = ("You are revising the independent labeler; these checks failed:\ntest_second.py::test_second\n"
                  f"(the coordinator graded {TASK}-pre-review: it passed)\n")
    rows = [json.loads(x) for x in reviser.read_text().splitlines()]
    rows[0]["message"]["content"] = rev_prompt
    reviser.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    report = tmp_path / "writer_audit.json"
    argv = ["--tasks-root", str(nt.tasks_root), "--labeler", f"{TASK}={_sha(writer)}", "--revision", f"{TASK}={reviser}",
            "--transcripts", str(tdir), "--report", str(report)]
    assert sr.main(argv) == 0
    rep = json.loads(report.read_text())
    w = rep["transcripts"][f"L-write-{TASK}"]
    assert w["own_workspace"] == LABELER_WS and w["own_checks"] == ["test_second.py::test_second"]
    assert [(h["path"], h["why"]) for h in w["hits"]] == [
        (f"{TD}/candidates/{TASK}-pre-review.json", "a candidate"),
        (f"/home/user/nat_ws/{TASK}/refcheck/tests/test_ref.py", "another agent's workspace")]
    assert [x["why"] for x in w["exposures"]] == ["shown in a tool output: text of a reference check"]
    assert w["exposures"][0]["path"] == f"data/natural/tasks/{TASK}/verifiers/reference_check/tests/test_ref.py"
    r = rep["transcripts"][f"L-revise-{TASK}"]
    assert r["own_workspace"] is None and "note" in r  # no record names the reviser's transcript
    assert f"{TASK}-pre-review" in {m for x in r["prompt"]["revision_input"]["grading_text"] for m in x["matched"]}
    assert r["prompt"]["revision_input"]["more_than_names"] and r["flagged"]
    assert rep["rules"]["allowed"][TASK][0] == {"path": f"data/natural/tasks/{TASK}/contracts/reference.json",
                                                "what": "the reference contract"}
    assert "natural" in rep["rules"] and rep["index"]["forbidden_files"] >= 1


def test_reports_on_natural_tasks_stay_out_of_git(reaudit, tmp_path):
    """A labeler report or an --outputs report that covers a natural task is refused where git would track it."""
    from natural_task_layout import init_git

    sr, root, nt, tdir = reaudit
    init_git(root)  # .gitignore: data/natural/
    t = _session(tdir / "agent-l1.jsonl", [])
    base = ["--tasks-root", str(nt.tasks_root), "--labeler", f"{TASK}={t}", "--transcripts", str(tdir)]
    with pytest.raises(SystemExit):
        sr.main([*base, "--report", str(root / "results" / "writer_audit.json")])
    assert not (root / "results").exists()
    assert sr.private_report_problem(root / "data" / "natural" / "writer_audit.json", root) is None
    assert sr.private_report_problem(tmp_path / "writer_audit.json", root) is None  # outside the repository
    assert sr.main([*base, "--report", str(root / "data" / "natural" / "writer_audit.json")]) == 0
    with pytest.raises(SystemExit):
        sr.main(["--tasks-root", str(nt.tasks_root), "--transcripts", str(tdir), "--scratch", "/fixture/scratch",
                 "--outputs", str(root / "outputs.json")])
    assert not (root / "outputs.json").exists()


def test_natural_reports_without_a_tasks_root_are_refused(reaudit, tmp_path):
    """Without --tasks-root, a natural family is neither audited in the controlled layout nor reported where git tracks
    it: the labeler mode refuses its ids, and the default mode guards --outputs and --write wherever its records lie."""
    sr, root, _, tdir = reaudit
    t = _session(tdir / "agent-l1.jsonl", [])
    target = root / "results" / "natural_writer_audit.json"
    target.parent.mkdir()
    with pytest.raises(SystemExit):  # the recorded D55/D58 command line, reused for a natural family
        sr.main(["--labeler", f"{TASK}={t}", "--transcripts", str(tdir), "--report", str(target)])
    assert not target.exists()
    with pytest.raises(SystemExit):  # the id says so even where no task directory does
        sr.main(["--labeler", f"NP-91={t}", "--transcripts", str(tdir), "--report", str(tmp_path / "w.json")])
    # A natural agent's record under tasks/ (a misplaced family): --outputs and --write into tracked files are refused.
    misplaced = root / "tasks" / "NP-91" / "labels" / "generator_audit.json"
    misplaced.parent.mkdir(parents=True)
    misplaced.write_text(json.dumps({"refcheck": {"transcript_sha256": _sha(t), "own_workspace": SIBLING,
                                                  "profile": NATURAL_PROFILE}}), encoding="utf-8")
    before = misplaced.read_bytes()
    base = ["--transcripts", str(tdir), "--scratch", "/fixture/scratch"]
    with pytest.raises(SystemExit):
        sr.main([*base, "--outputs", str(root / "outputs.json")])
    with pytest.raises(SystemExit):
        sr.main([*base, "--write"])
    assert not (root / "outputs.json").exists() and misplaced.read_bytes() == before
    assert sr.main([*base, "--outputs", str(tmp_path / "outputs.json")]) == 0  # outside the repository, no --write


def test_a_revision_in_its_own_workspace_may_be_told_the_writers_check_names(reaudit, tmp_path):
    """A natural writer and its revision work in workspaces of their own: the check names the writer wrote are collected
    in the writer's workspace, so a revision told only those bare names is not flagged."""
    sr, _, nt, tdir = reaudit
    (nt.task_dir / "contracts").mkdir()
    (nt.task_dir / "contracts" / "reference.json").write_text(json.dumps(
        {"contract_id": f"{TASK}-reference", "requirements": [{"req_id": "R-second", "statement": "add(2, None) == 2"}]}),
        encoding="utf-8")
    revision_ws = f"/home/user/nat_ws/{TASK}/labeler-revision"
    writer_prompt = "Write the independent labeler's tests for the reference contract."
    writer = _session(tdir / "agent-w.jsonl", [
        ("Read", {"file_path": f"{LABELER_WS}/contract.json"}, '{"variant": "reference"}'),
        ("Write", {"file_path": f"{LABELER_WS}/tests/test_second.py", "content": "def test_second():\n    pass\n"}, "ok")])
    reviser = _session(tdir / "agent-r.jsonl", [
        ("Read", {"file_path": f"{revision_ws}/tests/test_second.py"}, "def test_second():\n    pass\n"),
        ("Edit", {"file_path": f"{revision_ws}/tests/test_second.py", "old_string": "pass", "new_string": "assert True"}, "ok")])
    told = writer_prompt + "\nThese checks failed:\ntest_second.py::test_second\n"  # the bare name, nothing else
    for path, prompt in ((writer, writer_prompt), (reviser, told)):
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        rows[0]["message"]["content"] = prompt
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    records = {"labeler": {"transcript_sha256": _sha(writer), "own_workspace": LABELER_WS, "profile": NATURAL_PROFILE}}
    _record(nt, {**records, "labeler-revision": {"transcript_sha256": _sha(reviser), "own_workspace": revision_ws,
                                                 "profile": NATURAL_PROFILE}})
    rep = sr.audit_labelers([(TASK, str(writer))], [(TASK, str(reviser))], root=nt.root, transcripts=[writer, reviser],
                            tasks_root=nt.tasks_root)
    r = rep["transcripts"][f"L-revise-{TASK}"]
    assert r["own_workspace"] == revision_ws and "note" not in r
    assert r["prompt"]["revision_input"] == {"listed": ["test_second.py::test_second"], "kinds": {}, "unknown_names": [],
                                             "grading_text": [], "more_than_names": False}
    assert r["flagged"] is False, r
    # A name the writer did not write is still more than names; without the writer's record its names are unknown.
    rows = [json.loads(x) for x in reviser.read_text().splitlines()]
    rows[0]["message"]["content"] = writer_prompt + "\ntest_ref.py::test_reference_missing_second\n"
    reviser.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    _record(nt, {"labeler-revision": {"transcript_sha256": _sha(reviser), "own_workspace": revision_ws,
                                      "profile": NATURAL_PROFILE}})
    rep = sr.audit_labelers([(TASK, str(writer))], [(TASK, str(reviser))], root=nt.root, transcripts=[writer, reviser],
                            tasks_root=nt.tasks_root)
    r = rep["transcripts"][f"L-revise-{TASK}"]
    assert r["prompt"]["revision_input"]["unknown_names"] == ["test_ref.py::test_reference_missing_second"] and r["flagged"]
    assert "no record names the writer's transcript" in r["note"]
