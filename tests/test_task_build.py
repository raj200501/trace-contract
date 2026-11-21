"""A new build records no vacuous leakage check and writes its reconstruction check (protocol v0.8 §16.5).

``tasks.compile_controlled_task`` is run on a synthetic two-turn session in ``tmp_path``, with the
snapshot fetch replaced by a fixture tree (no network, no git). The session, scenario, states and
base are fixtures written for this test, not research data; the workspace path is a string in
the transcript, not a real directory. The four pilot tasks' ``snapshot.json`` files are not
touched (they keep the vacuous record, D47).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tracecontract.tasks as tasks
from tracecontract.contract import task_gate
from tracecontract.ingest.claude_code import sanitize_transcript
from tracecontract.reconstruction import METHOD, RECORD, recorded_check
from tracecontract.snapshot import manifest, manifest_sha256

WS = "/ws/fixture-build"
TID = "FX-BUILD"
U1, U2 = "Please make f return 2.", "Thanks. Also make g return 3."
OLD = "def f():\n    return 1\n\n\ndef g():\n    return 0\n"
PRE = OLD.replace("return 1", "return 2")
FINAL = PRE.replace("return 0", "return 3")


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def _raw_transcript(path: Path) -> Path:
    numbered = "\n".join(f"{n}\t{x}" for n, x in enumerate(OLD.split("\n"), 1))
    done = "The file has been updated."
    steps = [("user", U1), ("Read", {"file_path": f"{WS}/m.py"}, numbered),
             ("Edit", {"file_path": f"{WS}/m.py", "old_string": "return 1", "new_string": "return 2"}, done),
             ("user", U2),
             ("Edit", {"file_path": f"{WS}/m.py", "old_string": "return 0", "new_string": "return 3"}, done)]
    rows, k = [], 0
    for step in steps:
        k += 1
        if step[0] == "user":
            rows.append({"type": "user", "uuid": f"u{k}", "message": {"role": "user", "content": step[1]}})
            continue
        tool, inp, res = step
        rows.append({"type": "assistant", "uuid": f"a{k}", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{k}", "name": tool, "input": inp}]}})
        rows.append({"type": "user", "uuid": f"r{k}", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{k}", "content": res}]}})
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _build(tmp_path: Path, monkeypatch, base_text: str) -> Path:
    """Compile the fixture session under ``tmp_path`` against a base whose ``m.py`` is ``base_text``."""
    root = tmp_path / "repo"
    fixture_base = _tree(tmp_path / "pinned", {"m.py": base_text, "README.md": "fixture\n"})

    def rebuild(m, snapshot_root, cache_dir):  # stands in for fetching the pinned commit
        dest = snapshot_root / m.task_id
        _tree(dest, {p: (fixture_base / p).read_text() for p, _ in manifest(fixture_base)})
        return dest

    monkeypatch.setattr(tasks, "rebuild_snapshot", rebuild)
    raw = _raw_transcript(tmp_path / "raw.jsonl")
    san = sanitize_transcript(raw, tmp_path / "sanitized.jsonl", session_id=f"{TID}-session")
    start = manifest_sha256(manifest(fixture_base))
    scenario = {"scenario_id": TID, "turns": {"U1": U1, "U2": U2}, "repo_url": "https://example.invalid/fixture",
                "commit": "0" * 40, "code_license": "MIT", "workspace": WS}
    proposals = [{"req_id": "R1", "turn": "U1", "kind": "change", "status": "explicit", "scored": True,
                  "statement": "f returns 2.", "evidence": [{"turn": "U1", "quote": "make f return 2"}],
                  "observable": "f() == 2"}]
    record = {"env_pins": [], "image": "fixture-image", "image_id": "sha256:" + "0" * 64,
              "snapshot": {"snapshot_id": TID, "task_id": TID, "repo_url": "https://example.invalid/fixture",
                           "base_commit": "0" * 40, "fidelity": "exact", "file_manifest_sha256": start, "n_files": 2}}
    states = {"after_U1": _tree(tmp_path / "after_U1", {"m.py": PRE, "README.md": "fixture\n"}),
              "final": _tree(tmp_path / "final", {"m.py": FINAL, "README.md": "fixture\n"})}
    return tasks.compile_controlled_task(
        scenario=scenario, reference_proposals=proposals, transcript=tmp_path / "sanitized.jsonl", sanitization=san,
        states=states, workspace_record=record, tasks_root=root / "tasks", snapshot_root=root / "snapshots",
        cache_dir=tmp_path / "cache", repo_test_args=[], candidate_pythonpath="/work", allowed_roots=(WS,))


def test_a_new_build_writes_its_reconstruction_check_and_no_leakage_pass(tmp_path, monkeypatch):
    tdir = _build(tmp_path, monkeypatch, OLD)
    snap = json.loads((tdir / "snapshot.json").read_text())
    assert snap["leakage_check"] is None  # not the vacuous 'passed: true' of the pilot's records
    rec = json.loads((tdir / RECORD).read_text())
    assert rec["method"] == METHOD and rec["status"] == "passed", [(c["check_id"], c["status"]) for c in rec["checks"]]
    assert rec["inputs"]["workspace_root_from"] == "scenario"
    assert [(f["path"], f["status"]) for f in rec["files"]] == [("m.py", "passed")]
    root = tmp_path / "repo"
    assert recorded_check(tdir, root).ok
    gate = task_gate(tdir, root)
    assert not gate.refusals and not [r for r in gate.reasons if r.startswith("reconstruction:")]
    prov = json.loads((tdir / "provenance.json").read_text())
    assert prov["eligibility"] == "pending_review" and not any(r.startswith("leakage") for r in prov["rejection_reasons"])


def test_a_build_whose_base_holds_the_solution_is_refused(tmp_path, monkeypatch):
    tdir = _build(tmp_path, monkeypatch, PRE)  # the base already makes f return 2
    rec = json.loads((tdir / RECORD).read_text())
    assert rec["status"] == "failed"
    gate = task_gate(tdir, tmp_path / "repo")
    assert gate.refusals and gate.refusals[0].startswith("reconstruction: the recorded check failed")


@pytest.mark.parametrize("task", ["CS-01", "CS-02", "CS-03", "CS-04"])
def test_the_pilot_snapshot_records_are_unchanged(task):
    """Read-only: the pilot's snapshot.json files keep the vacuous record (D47); only new builds omit it."""
    snap = json.loads((Path(__file__).resolve().parents[1] / "tasks" / task / "snapshot.json").read_text())
    assert snap["leakage_check"]["method"] == "post-image-equality" and snap["leakage_check"]["passed"] is True
