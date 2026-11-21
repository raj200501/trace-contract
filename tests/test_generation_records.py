"""Generation records: build-verifier records a generated verifier only with a complete record; freeze stamps it (A6)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tracecontract.cli import main
from tracecontract.schemas import GenerationRecord, Population, SnapshotSource, TaskManifest, VerifierCondition, VerifierSpec
from tracecontract.store import dump, load
from tracecontract.verifier import (
    GENERATION_RUN_KEYS, build_spec, check_frozen, checks_sha256, generation_record, generation_record_problems,
)

R = Path(__file__).resolve().parents[1]
SHA = "ab" * 32
RUN = dict(run_id="fresh-v1-CS-01-testgen-1", config="config-A", prompt_sha256=SHA, started_at="2026-11-22T10:00:00+00:00",
           ended_at="2026-11-22T10:20:00Z", wall_s=1180.5, tool_calls=57, turns=31, tokens=182345,
           run_record="private-runs/fresh-v1/CS-01-testgen-1.json")
TEST = textwrap.dedent('''
    from tc_sandbox import run_python

    CHECK_REQUIREMENTS = {"test_add": ["R1"]}


    def test_add():
        r = run_python("import calc; result = calc.add(2, 3)")
        assert r.ok and r.value == 5
''')


def test_a_complete_record_holds_the_run_but_no_model_identifier():
    for label in ("config-A", "config-B", "config-Z"):
        assert generation_record(**{**RUN, "config": label}).generator == label
    rec = generation_record(**RUN)
    assert rec.generator == "config-A" and rec.run_id == RUN["run_id"] and rec.prompt_sha256 == SHA
    assert rec.created_at == RUN["ended_at"]
    assert set(rec.budget) == set(GENERATION_RUN_KEYS)
    assert rec.budget["run_record"] == RUN["run_record"] and rec.budget["tool_calls"] == 57
    assert generation_record_problems(rec) == []
    # turns or tokens: either one is enough
    assert generation_record_problems(generation_record(**{**RUN, "tokens": None})) == []
    assert generation_record_problems(generation_record(**{**RUN, "turns": None})) == []


def test_each_missing_or_invalid_field_is_refused():
    cases = {
        "run_id": [None, "", "unrecorded", "two words"],
        # a configuration label is config-A to config-Z: one capital letter, so no name can be spelt in it
        "config": [None, "", "A", "model:x", "config-", "config A", "config-a", "config-AB", "config-vendor-model-name-v9",
                   "config-anything_goes-123", "config-A1"],
        "prompt_sha256": [None, "", "AB" * 32, "ab" * 31],
        "started_at": [None, "yesterday", "2026-11-22T10:00:00"],  # no time zone
        "ended_at": [None, "2026-11-22T09:00:00+00:00"],             # before the start
        "wall_s": [None, 0, -1.0, 7200.0],                             # longer than start to end
        "tool_calls": [None, -1, 2.5],
        "run_record": [None, "", "/root/" + ".claude/projects/x/agent-1.jsonl",  # built so the scan does not flag it
                       "runs/0b6f3a2e-1c2d-4e5f-8a9b-0c1d2e3f4a5b.json"],  # session-local path, session id
    }
    for field, values in cases.items():
        for v in values:
            with pytest.raises(ValueError, match="incomplete generation record"):
                generation_record(**{**RUN, field: v})
    with pytest.raises(ValueError, match="turns or tokens missing"):
        generation_record(**{**RUN, "turns": None, "tokens": None})
    rec = generation_record(**RUN)
    assert generation_record_problems(rec.model_copy(update={"budget": {**rec.budget, "model": "x"}})) == [
        "budget holds unknown keys ['model']"]
    assert generation_record_problems(None) == ["no generation record"]


def test_the_pilot_records_are_incomplete_and_stay_as_recorded():
    """The frozen specs of CS-01..04 carry the old fields ('unrecorded', no hash); they are read, never rewritten."""
    for p in sorted(R.glob("tasks/CS-0*/verifiers/*/spec.json")):
        before = p.read_bytes()
        s = load(p, VerifierSpec)
        if s.generation is not None:
            assert generation_record_problems(s.generation), p
        assert p.read_bytes() == before


def test_build_spec_can_require_the_record(tmp_path):
    task = tmp_path / "task"
    (task / "verifiers" / "v1" / "tests").mkdir(parents=True)
    (task / "verifiers" / "v1" / "tests" / "test_a.py").write_text(TEST)
    kw = dict(verifier_id="v1", task_id="t", condition=VerifierCondition.full_plain, test_dir=task / "verifiers" / "v1" / "tests",
              task_dir=task)
    assert build_spec(**kw).generation is None  # without the flag, as for the B1 scripts and older callers
    with pytest.raises(ValueError, match="no complete generation record"):
        build_spec(**kw, require_generation=True)
    with pytest.raises(ValueError, match="configuration label"):
        build_spec(**kw, require_generation=True,
                   generation=GenerationRecord(generator="model:x", run_id="r", prompt_sha256=SHA, created_at=RUN["ended_at"]))
    assert build_spec(**kw, require_generation=True, generation=generation_record(**RUN)).generation.generator == "config-A"


def _fixture_task(root: Path) -> Path:
    td = root / "FX-09"
    (td / "verifiers" / "full_plain" / "tests").mkdir(parents=True)
    (td / "verifiers" / "full_plain" / "tests" / "test_a.py").write_text(TEST)
    dump(TaskManifest(task_id="FX-09", family_id="FX-09", population=Population.fixture, status="draft", provenance="p.json",
                      snapshot_source=SnapshotSource(repo_url="https://example.invalid/x", commit="0" * 40),
                      env_requirements=[]), td / "task.json")
    return td


def _run_flags(**over) -> list[str]:
    run = {**RUN, **over}
    names = {"run_id": "--gen-run-id", "config": "--config", "prompt_sha256": "--prompt-sha256", "started_at": "--started-at",
             "ended_at": "--ended-at", "wall_s": "--wall-s", "tool_calls": "--tool-calls", "turns": "--turns",
             "tokens": "--tokens", "run_record": "--run-record"}
    return [x for k, v in run.items() if v is not None for x in (names[k], str(v))]


def test_build_verifier_refuses_to_record_without_a_complete_record(tmp_path, capsys):
    td = _fixture_task(tmp_path)
    manifest = (td / "task.json").read_bytes()
    spec = td / "verifiers" / "full_plain" / "spec.json"
    base = ["build-verifier", str(td), "full_plain", "--condition", "full_plain"]
    for flags in ([], _run_flags(config="claude-x"), _run_flags(wall_s=None), _run_flags(turns=None, tokens=None)):
        with pytest.raises(SystemExit, match="build-verifier refused, nothing recorded"):
            main(base + flags)
        assert not spec.exists() and (td / "task.json").read_bytes() == manifest
    # A dry run builds and lints, records nothing, and says what the record lacks.
    capsys.readouterr()
    main(base + ["--dry-run"])
    out = json.loads(capsys.readouterr().out)
    assert out["recorded"] is False and out["n_checks"] == 1 and not spec.exists()
    assert out["generation_record"].startswith("incomplete generation record: run id missing")
    # With the record of the run that wrote the tests, the spec is recorded and carries it.
    main(base + _run_flags())
    out = json.loads(capsys.readouterr().out)
    assert out["recorded"] is True and out["generation_record"] == "complete"
    s = load(spec, VerifierSpec)
    assert s.generation == generation_record(**RUN) and not s.frozen
    assert "verifiers/full_plain/spec.json" in load(td / "task.json", TaskManifest).verifiers


def test_repository_tests_need_no_record(tmp_path, capsys):
    td = _fixture_task(tmp_path)
    main(["build-verifier", str(td), "full_plain", "--condition", "repo_tests", "--isolation", "in_process"])
    out = json.loads(capsys.readouterr().out)
    assert out["recorded"] is True and out["generation_record"] == "not needed (repository tests)"
    assert load(td / "verifiers" / "full_plain" / "spec.json", VerifierSpec).generation is None


def test_freeze_writes_frozen_at_and_the_check_list_hash_and_build_verifier_keeps_off(tmp_path, capsys):
    td = _fixture_task(tmp_path)
    main(["build-verifier", str(td), "full_plain", "--condition", "full_plain", *_run_flags()])
    capsys.readouterr()
    main(["freeze", str(td), "full_plain"])
    out = json.loads(capsys.readouterr().out)
    sp = td / "verifiers" / "full_plain" / "spec.json"
    raw = json.loads(sp.read_text())
    assert raw["frozen"] is True and raw["frozen_at"] and raw["checks_sha256"]
    assert out["frozen_at"] == raw["frozen_at"] and out["checks_sha256"] == raw["checks_sha256"]
    s = load(sp, VerifierSpec)
    assert s.checks_sha256 == checks_sha256(s) and s.generation == generation_record(**RUN)
    check_frozen(s, td)
    frozen = sp.read_bytes()
    with pytest.raises(SystemExit, match="is frozen"):
        main(["build-verifier", str(td), "full_plain", "--condition", "full_plain", *_run_flags(run_id="another-run")])
    with pytest.raises(ValueError, match="already frozen"):
        main(["freeze", str(td), "full_plain"])
    assert sp.read_bytes() == frozen
