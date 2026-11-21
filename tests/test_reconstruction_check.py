"""Reconstruction (leakage) check: population fixtures only.

Every session, base and state below is a synthetic fixture (``Population.fixture``) written
for these tests; none is research data. The workspace path ``/ws/fixture-repo`` is a string
in the fixture transcripts, not a real directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracecontract import cli
from tracecontract.ingest.claude_code import parse_claude_code_jsonl
from tracecontract.patches import diff_dirs
from tracecontract.reconstruction import bash_effects, check_reconstruction, check_task
from tracecontract.schemas import (
    Candidate, CandidateOrigin, Eligibility, Fidelity, Population, ProvenanceRecord, RedactionStatus, Snapshot,
    SnapshotSource, Split, TaskManifest, sha256_text,
)
from tracecontract.snapshot import leakage_check, manifest, manifest_sha256
from tracecontract.store import dump

WS = "/ws/fixture-repo"
OLD = "def f():\n    return 1\n"
NEW = "def f():\n    return 2\n"


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def _read_result(text: str) -> str:
    return "\n".join(f"{n}\t{line}" for n, line in enumerate(text.split("\n"), start=1))


def _session(tmp_path: Path, calls: list[tuple[str, dict, str, bool]], *, sid: str = "FX-session",
             prompts: tuple[str, ...] = ("Please make f return 2.",)):
    """A fixture transcript: the prompts, then one tool call and its result per entry of ``calls``."""
    rows = [{"type": "user", "sessionId": sid, "uuid": f"p{k}", "message": {"role": "user", "content": p}}
            for k, p in enumerate(prompts[:1])]
    for k, (tool, tool_input, result, is_error) in enumerate(calls):
        rows.append({"type": "assistant", "sessionId": sid, "uuid": f"a{k}", "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": f"t{k}", "name": tool, "input": tool_input}]}})
        rows.append({"type": "user", "sessionId": sid, "uuid": f"r{k}", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{k}", "content": result, "is_error": is_error}]}})
    for k, p in enumerate(prompts[1:], start=1):
        rows.append({"type": "user", "sessionId": sid, "uuid": f"p{k}", "message": {"role": "user", "content": p}})
    path = tmp_path / f"{sid}.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return parse_claude_code_jsonl(path, population=Population.fixture, source="fixture", scripted_turns=list(prompts))


def _edit(rel: str, old: str, new: str, *, replace_all: bool = False) -> tuple[str, dict, str, bool]:
    return ("Edit", {"file_path": f"{WS}/{rel}", "old_string": old, "new_string": new, "replace_all": replace_all},
            f"The file {WS}/{rel} has been updated successfully.", False)


def _run(tmp_path: Path, base_files: dict[str, str], final_files: dict[str, str], calls, *, recorded_start: bool = False, **kw):
    """Check a fixture session; ``recorded_start`` records the base's own manifest as the start-of-session manifest."""
    base = _tree(tmp_path / "base", base_files)
    final = _tree(tmp_path / "final", final_files)
    session = _session(tmp_path, calls)
    patch = diff_dirs(base, final)
    if recorded_start:
        kw["start_manifest"] = manifest_sha256(manifest(base))
    return base, patch, check_reconstruction(task_id="FX", session=session, base=base, workspace_root=WS,
                                             final_patch=patch, **kw)


def test_base_that_holds_the_solution_passes_the_old_check_and_fails_the_new_one(tmp_path):
    # The session read `return 1` and edited it to `return 2`, but the base already says `return 2`.
    calls = [("Read", {"file_path": f"{WS}/pkg/mod.py"}, _read_result(OLD), False), _edit("pkg/mod.py", "return 1", "return 2")]
    base, patch, rep = _run(tmp_path, {"pkg/mod.py": NEW, "README.md": "x\n"}, {"pkg/mod.py": NEW, "README.md": "x\n"}, calls)

    # The defect: called as tasks.compile_controlled_task calls it (no reference_base), the old
    # check compares the base with itself and passes.
    old = leakage_check(base, patch)
    assert old.passed and old.leaked_paths == []
    # Only an independent clean base, which compile_controlled_task does not pass, lets it see the leak.
    clean = _tree(tmp_path / "clean", {"pkg/mod.py": OLD, "README.md": "x\n"})
    assert not leakage_check(base, diff_dirs(clean, base), reference_base=clean).passed

    assert rep.passed is False and rep.status == "failed"
    a = rep.check("a_written_files_changed")
    assert a.status == "failed" and a.items[0]["path"] == "pkg/mod.py"
    b = rep.check("b_first_edit_strings")
    assert b.status == "failed"
    assert b.items[0]["old_occurrences"] == 0 and b.items[0]["new_occurrences_outside_old"] == 1
    assert "old_string does not occur in the base" in b.items[0]["reason"]
    c = rep.check("c_reads_match_base")
    assert c.status == "failed" and c.items[0]["mismatches"][0]["line"] == 2
    assert rep.check("f_replay_matches_states").status == "failed"


def test_non_unique_old_string_fails_the_first_edit_check(tmp_path):
    base_text = "x = 1\ny = 0\nx = 1\n"
    calls = [_edit("m.py", "x = 1\n", "x = 2\n")]
    _, _, rep = _run(tmp_path, {"m.py": base_text}, {"m.py": "x = 2\ny = 0\nx = 1\n"}, calls)
    b = rep.check("b_first_edit_strings")
    assert b.status == "failed" and b.items[0]["old_occurrences"] == 2
    assert "refuses a non-unique old_string" in b.items[0]["reason"]
    f = rep.check("f_replay_matches_states")
    assert any(i.get("kind") == "edit" and i["status"] == "failed" for i in f.items)
    assert rep.passed is False
    # With replace_all the same base is consistent.
    _, _, ok = _run(tmp_path / "all", {"m.py": base_text}, {"m.py": "x = 2\ny = 0\nx = 2\n"},
                    [_edit("m.py", "x = 1\n", "x = 2\n", replace_all=True)])
    assert ok.check("b_first_edit_strings").status == "passed" and ok.check("f_replay_matches_states").status == "passed"


def test_bash_only_edit_is_reported_as_not_checkable(tmp_path):
    calls = [("Bash", {"command": f"cd {WS} && sed -i 's/return 1/return 2/' pkg/mod.py"}, "", False)]
    _, _, rep = _run(tmp_path, {"pkg/mod.py": OLD}, {"pkg/mod.py": NEW}, calls)
    assert rep.check("a_written_files_changed").status == "not_checkable"
    assert rep.check("b_first_edit_strings").status == "not_checkable"
    f = rep.check("f_replay_matches_states")
    item = next(i for i in f.items if i.get("path") == "pkg/mod.py" and i.get("state") == "final")
    assert item["status"] == "not_checkable" and "sed -i" in item["reason"]
    assert rep.bash_effects == [{"event_id": "FX-session/L000002.00", "action": "write", "paths": ["pkg/mod.py"],
                                 "reason": "sed -i edits its files in place"}]
    assert rep.status == "incomplete" and rep.passed is None  # nothing failed, but nothing could be checked


def test_consistent_session_passes_and_a_revert_is_explained(tmp_path):
    files = {"pkg/mod.py": OLD, "README.md": "intro\n"}
    calls = [("Read", {"file_path": f"{WS}/pkg/mod.py"}, _read_result(OLD), False),
             ("Edit", {"file_path": f"{WS}/README.md", "old_string": "intro", "new_string": "intro (draft)"},
              "<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>", True),
             _edit("README.md", "intro", "intro (draft)"),
             _edit("pkg/mod.py", "return 1", "return 2"),
             ("Bash", {"command": f"cd {WS} && git checkout -- README.md && git status --short 2>&1 | head"}, "", False),
             ("Bash", {"command": f"cd {WS} && cat pkg/mod.py"}, NEW.rstrip("\n"), False)]
    _, _, rep = _run(tmp_path, files, {**files, "pkg/mod.py": NEW}, calls, recorded_start=True)
    assert rep.status == "passed" and rep.passed is True
    a = {i["path"]: i for i in rep.check("a_written_files_changed").items}
    assert a["pkg/mod.py"]["status"] == "passed"
    assert a["README.md"]["status"] == "explained" and "L000010.00" in a["README.md"]["reason"]  # the git checkout
    reads = rep.check("f_replay_matches_states").items
    assert any(i.get("source") == "Bash cat" and i["state"] == "replayed" and i["status"] == "passed" for i in reads)


def test_start_manifest_overlays_and_stale_copies(tmp_path):
    files = {"pkg/mod.py": OLD, "pkg/_version.py": "v = 1\n"}
    calls = [_edit("pkg/mod.py", "return 1", "return 2")]
    base, _, rep = _run(tmp_path, files, {**files, "pkg/mod.py": NEW}, calls)
    assert rep.check("d_start_manifest").status == "unavailable"  # no start manifest given
    entries = manifest(base)
    without = manifest_sha256([e for e in entries if e[0] != "pkg/_version.py"])
    session = _session(tmp_path, calls)
    patch = diff_dirs(base, _tree(tmp_path / "f2", {**files, "pkg/mod.py": NEW}))
    run = lambda **kw: check_reconstruction(task_id="FX", session=session, base=base, workspace_root=WS,  # noqa: E731
                                            final_patch=patch, **kw)
    assert run(start_manifest=manifest_sha256(entries)).check("d_start_manifest").status == "passed"
    d = run(start_manifest=without, overlays={"pkg/_version.py": "v = 1\n"}).check("d_start_manifest")
    assert d.status == "passed" and d.items[-1]["status"] == "explained" and d.approximations
    assert run(start_manifest="0" * 64).check("d_start_manifest").status == "failed"
    _tree(base, {"pkg/__pycache__/mod.cpython-312.pyc": "x", "pkg/mod.py.orig": OLD, "docs/notes.txt~": "n"})
    e = check_reconstruction(task_id="FX", session=session, base=base, workspace_root=WS,
                             final_patch=diff_dirs(base, _tree(tmp_path / "f3", {**files, "pkg/mod.py": NEW}))).check("e_no_stale_copies")
    assert e.status == "failed" and {i["path"] for i in e.items} == {"pkg/__pycache__/mod.cpython-312.pyc", "pkg/mod.py.orig"}


@pytest.mark.parametrize("command,expected", [
    (f"cd {WS} && ./run_tests.sh -q 2>&1 | tail -5", []),
    (f"{WS}/../run_python.sh - <<'EOF'\nopen('/repo/x.py', 'w').write('x')\nEOF", []),
    (f"cd {WS} && python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('pkg/mod.py')\np.write_text('y')\nEOF\ngit diff --stat",
     [("write", ["pkg/mod.py"])]),
    (f"cd {WS} && echo hi > notes.txt && awk 'length > 88' pkg/mod.py", [("write", ["notes.txt"])]),
    (f"cd {WS} && git checkout -- pkg/mod.py README.md", [("restore", ["README.md", "pkg/mod.py"])]),
    (f"cd {WS} && for py in python3 /usr/bin/python3; do \"$py\" -c 'import sys; print(sys.version)'; done", []),
    (f"cd {WS} && ruff format --no-cache --check . && black -q --check --diff - < pkg/mod.py && mypy --cache-dir=/dev/null pkg", []),
    (f"cd {WS} && ruff format pkg/mod.py", [("write", [".ruff_cache"]), ("write", ["pkg/mod.py"])]),
    (f"cd {WS} && frobnicate pkg", [("write_any", [])]),
    ("sed -i 's/a/b/' pkg/mod.py", [("write_any", [])]),  # relative target, working directory unknown
    (f"cd {WS} && git stash", [("restore", ["."])]),
])
def test_bash_effects(command, expected):
    got = [(e.action, e.paths) for e in bash_effects(command, WS, known_files={"pkg/mod.py", "README.md"})]
    assert got == expected


def test_cli_writes_the_report_from_repository_material(tmp_path, monkeypatch):
    repo, tid = tmp_path / "repo", "FX-01"
    base = _tree(repo / "snapshots" / tid, {"pkg/mod.py": OLD})
    final = _tree(tmp_path / "final", {"pkg/mod.py": NEW})
    tdir = repo / "tasks" / tid
    prompts = ("Please make f return 2.", "Thanks. Also keep the module docstring.")
    session = _session(tmp_path, [("Read", {"file_path": f"{WS}/pkg/mod.py"}, _read_result(OLD), False),
                                  _edit("pkg/mod.py", "return 1", "return 2")], sid=f"{tid}-session", prompts=prompts)
    (repo / "data" / "fixtures" / "transcripts").mkdir(parents=True)
    (tmp_path / f"{tid}-session.jsonl").rename(repo / "data" / "fixtures" / "transcripts" / f"{tid}.jsonl")
    entries = manifest(base)
    patch = diff_dirs(base, final)
    dump(Candidate(candidate_id=f"{tid}-reference", task_id=tid, origin=CandidateOrigin.reference, split=Split.dev,
                   patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture"), tdir / "candidates" / "ref.json")
    dump(Snapshot(snapshot_id=tid, task_id=tid, repo_url="https://example.invalid/fixture", base_commit="0" * 40,
                  fidelity=Fidelity.exact, file_manifest_sha256=manifest_sha256(entries), n_files=len(entries)),
         tdir / "snapshot.json")
    dump(ProvenanceRecord(record_id="p", session_id=session.session_id, population=Population.fixture, source_url="fixture",
                          source_id=tid, permission_basis="fixture", trace_sha256=session.trace_sha256,
                          snapshot_manifest_sha256=manifest_sha256(entries), capture_method="fixture",
                          redaction_status=RedactionStatus.redacted_by_us, task_family_id=tid,
                          eligibility=Eligibility.pending_review, accessed="2026-01-01",
                          notes=json.dumps({"workspace_snapshot_manifest": manifest_sha256(entries)})), tdir / "provenance.json")
    dump(TaskManifest(task_id=tid, family_id=tid, population=Population.fixture, status="draft", provenance="provenance.json",
                      snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture", commit="0" * 40),
                      snapshot="snapshot.json", env_requirements=[], scripted_turns=list(prompts),
                      candidates=["candidates/ref.json"]), tdir / "task.json")
    rep = check_task(tdir, repo, repo / "snapshots")
    assert rep.status == "passed", [(c.check_id, c.status, c.reason) for c in rep.checks]
    assert rep.inputs["workspace_root_from"] == "inferred from tool paths"
    monkeypatch.setattr(cli, "REPO", repo)
    monkeypatch.setattr(cli, "SNAPSHOTS", repo / "snapshots")
    with pytest.raises(SystemExit) as ex:
        cli.main(["reconstruction-check", str(tdir), "--write"])
    assert ex.value.code == 0
    written = json.loads((tdir / "reconstruction_check.json").read_text())
    assert written == json.loads(json.dumps(rep.to_dict())) and written["passed"] is True
    # A data problem is reported, never raised.
    (repo / "snapshots" / tid / "pkg" / "mod.py").write_text("changed\n")
    assert check_task(tdir, repo, repo / "snapshots").check("a_written_files_changed").status == "unavailable"
