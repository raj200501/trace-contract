"""scripts/record_phase_end.py: one log line per phase end of a natural family, in the committed index's form (D65).

A synthetic natural task (tests/natural_task_layout.py) gets phase-end records: its task directory's files as
``natural_pr.file_hashes`` summarises them (B1's overlay and the generated tests are each one manifest hash and a file
count, so no repository path and no generated test's file name enters the log), its verifiers with their frozen state
(sidecars included), its contracts and its candidates. Phases come in order per task, and only natural PR-review tasks
are recorded. Synthetic data only; not research evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from natural_task_layout import build_natural_task

R = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location("record_phase_end", R / "scripts" / "record_phase_end.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["record_phase_end"] = mod
    spec.loader.exec_module(mod)
    return mod


rpe = _load_script()
NOW = "2026-11-21T19:00:00Z"


def _family(tmp_path: Path):
    nt = build_natural_task(tmp_path)
    td = nt.task_dir
    tests = td / "verifiers" / "initial_plain" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_generated_name_marker.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    spec = json.loads((td / "verifiers" / "repo_tests" / "spec.json").read_text(encoding="utf-8"))
    spec.update(verifier_id="independent_label", condition="reference_check", frozen=True, frozen_at="2026-11-21T18:00:00+00:00")
    (td / "verifiers" / "independent_label").mkdir()
    (td / "verifiers" / "independent_label" / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (td / "verifiers_extra.json").write_text(json.dumps({"verifiers": ["verifiers/independent_label/spec.json"]}), encoding="utf-8")
    return nt


def test_record_is_in_the_index_form_and_names_no_test_file(tmp_path):
    nt = _family(tmp_path)
    log = tmp_path / "phase_ends.jsonl"
    rec = rpe.append(nt.task_dir, "P1", log, now=NOW, repo=tmp_path)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0]) == rec
    assert (rec["schema"], rec["task_id"], rec["phase"], rec["recorded_at"]) == (rpe.SCHEMA, nt.task_id, "P1", NOW)
    assert rec["head"] is None  # the scratch root is not a git repository
    files = rec["files"]
    assert files["verifiers/initial_plain/tests/"]["n_files"] == 1
    assert files["verifiers/repo_tests/overlay/"]["n_files"] == 1
    assert "task.json" in files and "verifiers/repo_tests/spec.json" in files
    assert rec["state_sha256"] == hashlib.sha256(rpe._canonical(files)).hexdigest()
    text = lines[0]
    assert "test_generated_name_marker" not in text and "test_mod" not in text  # summarised, never named
    by_id = {v["verifier_id"]: v for v in rec["verifiers"]}
    assert by_id["repo_tests"]["sidecar"] is False and by_id["repo_tests"]["frozen"] is False
    assert by_id["independent_label"] == {"verifier_id": "independent_label", "condition": "reference_check", "frozen": True,
                                          "frozen_at": "2026-11-21T18:00:00+00:00",
                                          "content_sha256": by_id["repo_tests"]["content_sha256"], "sidecar": True}
    assert rec["contracts"] == {}
    assert len(rec["candidates"]) == 4
    assert {c["origin"] for c in rec["candidates"].values()} == {"reference", "natural_pre_review", "noop"}


def test_a_change_in_a_summarised_directory_changes_the_state(tmp_path):
    nt = _family(tmp_path)
    log = tmp_path / "phase_ends.jsonl"
    first = rpe.append(nt.task_dir, "P1", log, now=NOW, repo=tmp_path)
    (nt.task_dir / "verifiers" / "initial_plain" / "tests" / "test_generated_name_marker.py").write_text("x = 1\n", encoding="utf-8")
    second = rpe.append(nt.task_dir, "P2", log, now=NOW, repo=tmp_path)
    assert first["state_sha256"] != second["state_sha256"]
    assert first["files"]["task.json"] == second["files"]["task.json"]


def test_phases_come_in_order_per_task(tmp_path):
    nt = _family(tmp_path)
    log = tmp_path / "phase_ends.jsonl"
    rpe.append(nt.task_dir, "P1", log, now=NOW, repo=tmp_path)
    with pytest.raises(rpe.PhaseError, match="already records P1"):
        rpe.append(nt.task_dir, "P1", log, now=NOW, repo=tmp_path)
    rpe.append(nt.task_dir, "P3", log, now=NOW, repo=tmp_path)
    with pytest.raises(rpe.PhaseError, match="P2 does not come after"):
        rpe.append(nt.task_dir, "P2", log, now=NOW, repo=tmp_path)
    other = build_natural_task(tmp_path, "NP-91", index=False)
    rpe.append(other.task_dir, "P1", log, now=NOW, repo=tmp_path)  # another task's order is its own
    assert [json.loads(x)["phase"] for x in log.read_text(encoding="utf-8").splitlines()] == ["P1", "P3", "P1"]
    with pytest.raises(rpe.PhaseError, match="phase must be one of"):
        rpe.phase_record(nt.task_dir, "P8", now=NOW, repo=tmp_path)


def test_only_natural_tasks_and_cli_refusals(tmp_path, capsys):
    td = tmp_path / "CS-90"
    td.mkdir()
    (td / "task.json").write_text(json.dumps({"task_id": "CS-90", "population": "controlled"}), encoding="utf-8")
    log = tmp_path / "phase_ends.jsonl"
    with pytest.raises(rpe.PhaseError, match="not a natural PR-review task"):
        rpe.append(td, "P1", log, now=NOW, repo=tmp_path)
    assert not log.exists()
    assert rpe.main([str(td), "--phase", "P1", "--log", str(log)]) == 2
    assert "refused" in capsys.readouterr().err
    nt = _family(tmp_path)
    assert rpe.main([str(nt.task_dir), "--phase", "P2", "--log", str(log)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["phase"] == "P2" and printed["task_id"] == nt.task_id
    log.write_text("not json\n", encoding="utf-8")
    assert rpe.main([str(nt.task_dir), "--phase", "P3", "--log", str(log)]) == 2
