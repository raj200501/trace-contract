"""scripts/verify_frozen_inputs.py: hash classification, append-only check and analysis.json comparison.

Synthetic fixtures only (files in a temporary directory; the frozen-commit contents are
monkeypatched, so no git repository is created or changed).
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_frozen_inputs.py"
spec = importlib.util.spec_from_file_location("verify_frozen_inputs", SCRIPT)
vfi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vfi)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_input_hashes_separate_preexisting_from_new_differences(tmp_path, monkeypatch):
    (tmp_path / "src/tracecontract").mkdir(parents=True)
    (tmp_path / "tasks/CS-01").mkdir(parents=True)
    (tmp_path / "src/tracecontract/schemas.py").write_bytes(b"at the frozen commit\n")
    (tmp_path / "tasks/CS-01/task.json").write_bytes(b"{}\n")
    frozen = {"src/tracecontract/schemas.py": b"at the frozen commit\n", "tasks/CS-01/task.json": b"{}\n"}
    monkeypatch.setattr(vfi, "REPO", tmp_path)
    monkeypatch.setattr(vfi, "_at_rev", lambda rev, rel: frozen.get(rel))
    recorded = {"code/schemas.py": _sha(b"when the run was analysed\n"), "CS-01/task.json": _sha(b"{}\n")}
    f = vfi.Findings()
    # Analysis code may change after the run; (d) checks the outputs, so (a) only reports it.
    assert vfi.check_input_hashes(f, "REV", "results/runs/x", recorded) == {"code/schemas.py": "code-changed",
                                                                             "CS-01/task.json": "ok"}
    assert not f.new and not f.preexisting and len(f.info) == 1 and "code/schemas.py" in f.info[0]
    # A data input that was already off at the frozen commit is pre-existing, not new.
    (tmp_path / "tasks/CS-01/task.json").write_bytes(b'{"frozen": 1}\n')
    frozen["tasks/CS-01/task.json"] = b'{"frozen": 1}\n'
    f = vfi.Findings()
    assert vfi.check_input_hashes(f, "REV", "results/runs/x", recorded)["CS-01/task.json"] == "pre-existing"
    assert not f.new and len(f.preexisting) == 1
    frozen["tasks/CS-01/task.json"] = b"{}\n"
    (tmp_path / "tasks/CS-01/task.json").write_bytes(b'{"edited": true}\n')
    f = vfi.Findings()
    assert vfi.check_input_hashes(f, "REV", "results/runs/x", recorded)["CS-01/task.json"] == "new"
    assert len(f.new) == 1 and "CS-01/task.json" in f.new[0]


def test_append_only_files_and_analysis_comparison(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "experiments").mkdir()
    (tmp_path / "docs/decision_log.md").write_bytes(b"D1\nD2\nD3 appended\n")
    (tmp_path / "experiments/protocol.md").write_bytes(b"v0.6 rewritten\n")
    monkeypatch.setattr(vfi, "REPO", tmp_path)
    monkeypatch.setattr(vfi, "_at_rev", lambda rev, rel: {"docs/decision_log.md": b"D1\nD2\n",
                                                          "experiments/protocol.md": b"v0.6\n"}[rel])
    f = vfi.Findings()
    vfi.check_append_only(f, "REV")
    assert len(f.new) == 1 and "experiments/protocol.md" in f.new[0] and "line 1" in f.new[0]
    assert vfi._json_diff({"a": 1, "b": {"c": [1, 2]}}, {"a": 1, "b": {"c": [1, 3]}}) == ["b.c[1]"]
    old, new = b'{"meta": {"inputs": {"git_revision": "abc"}}}', b'{"meta": {"inputs": {"git_revision": null}}}'
    assert vfi._REVISION.sub(b"", old) == vfi._REVISION.sub(b"", new)
    assert vfi._input_path("code/analysis.py", "results/runs/x") == "src/tracecontract/analysis.py"
    assert vfi._input_path("manifest.json", "results/runs/x") == "results/runs/x/manifest.json"
    assert vfi._input_path("CS-02/contracts/reference.json", "results/runs/x") == "tasks/CS-02/contracts/reference.json"


def test_a_triage_only_change_to_a_provenance_record_is_a_frozen_change(monkeypatch):
    """(e) has no triage exemption: the proposals live in tasks/<id>/triage.json, not in the frozen record."""
    assert not hasattr(vfi, "_only_triage_changed")
    listing = {("ls-tree", "--name-only"): b"tasks/CS-01\ntasks/FX-01\n", ("ls-tree", "-d"): b"results/runs/pilot-v0.3.3\n",
               ("diff", "--name-status"): b"M\ttasks/CS-01/provenance.json\nA\ttasks/CS-01/labels/new.json\n",
               ("ls-files", "--others"): b"tasks/CS-01/candidates/untracked.json\n"}
    calls = []

    def fake_git(*args: str) -> bytes:
        calls.append(args)
        return listing[args[:2]]

    monkeypatch.setattr(vfi, "_git", fake_git)
    f = vfi.Findings()
    vfi.check_frozen_files(f, "REV")
    assert f.new == ["(e) tasks/CS-01/provenance.json: modified since REV"] and not f.info
    assert f.summary["e"] == "1 frozen file(s) changed, 2 new file(s) beside them"
    specs = calls[2][5:]
    assert "tasks/CS-01/provenance.json" in specs and not any(x.startswith("tasks/FX-01") for x in specs)
    assert not any("triage.json" in x for x in specs)  # the sidecar is not a frozen file


def test_docstring_states_the_code_change_exemption():
    doc = vfi.__doc__
    assert "exemption" in doc and "analysis code" in doc and "triage.json" in doc
    assert "code/schemas.py" not in doc  # analysis code is never counted as pre-existing
