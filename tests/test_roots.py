"""Unit tests: where a task's base snapshot lives (tracecontract.roots). Synthetic fixtures only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracecontract import roots


def _task(base: Path, tid: str, population: str, notes: object | None = None) -> Path:
    td = base / tid
    td.mkdir(parents=True)
    (td / "task.json").write_text(json.dumps({"task_id": tid, "population": population}), encoding="utf-8")
    if notes is not None:
        (td / "provenance.json").write_text(json.dumps({"notes": notes}), encoding="utf-8")
    return td


def test_a_controlled_task_uses_the_repository_snapshots(tmp_path):
    td = _task(tmp_path / "tasks", "CS-09", "controlled", json.dumps({"snapshot_root": "data/natural/snapshots"}))
    assert roots.snapshot_root(td, repo=tmp_path) == tmp_path.resolve() / "snapshots"
    assert roots.snapshot_dir(td, repo=tmp_path) == tmp_path.resolve() / "snapshots" / "CS-09"


def test_a_natural_task_uses_its_recorded_root(tmp_path):
    td = _task(tmp_path / "data/natural/tasks", "NP-90", roots.NATURAL_PR,
               json.dumps({"compiler": "natural_pr:v1", "snapshot_root": "data/natural/snapshots"}))
    assert roots.is_natural_pr(td)
    assert roots.snapshot_root(td, repo=tmp_path) == (tmp_path / "data/natural/snapshots").resolve()
    assert roots.snapshot_dir(td, repo=tmp_path).name == "NP-90"


def test_notes_may_be_an_object_as_well_as_a_json_string(tmp_path):
    td = _task(tmp_path / "data/natural/tasks", "NP-91", roots.NATURAL_PR, {"snapshot_root": "data/natural/snapshots"})
    assert roots.snapshot_root(td, repo=tmp_path) == (tmp_path / "data/natural/snapshots").resolve()


def test_without_the_field_the_root_is_next_to_the_tasks_directory(tmp_path):
    td = _task(tmp_path / "data/natural/tasks", "NP-92", roots.NATURAL_PR, json.dumps({"compiler": "natural_pr:v1"}))
    assert roots.snapshot_root(td, repo=tmp_path) == (tmp_path / "data/natural/snapshots").resolve()
    td2 = _task(tmp_path / "data/natural/tasks", "NP-93", roots.NATURAL_PR)  # no provenance file at all
    assert roots.snapshot_root(td2, repo=tmp_path) == (tmp_path / "data/natural/snapshots").resolve()


@pytest.mark.parametrize("bad", ["/abs/snapshots", "../outside", "tasks", "tasks/NP-94/snap"])
def test_an_unusable_recorded_root_is_refused(tmp_path, bad):
    td = _task(tmp_path / "data/natural/tasks", "NP-94", roots.NATURAL_PR, json.dumps({"snapshot_root": bad}))
    with pytest.raises(roots.RootError):
        roots.snapshot_root(td, repo=tmp_path)


def test_a_task_without_task_json_is_not_natural(tmp_path):
    (tmp_path / "tasks" / "X").mkdir(parents=True)
    assert roots.population(tmp_path / "tasks" / "X") is None
    assert roots.snapshot_root(tmp_path / "tasks" / "X", repo=tmp_path) == tmp_path.resolve() / "snapshots"


def test_the_recorded_tasks_resolve_as_they_are_stored():
    """Read-only: the four controlled tasks resolve to snapshots/; any natural task present resolves to data/natural."""
    for td in sorted((roots.REPO / "tasks").glob("CS-*")):
        assert roots.snapshot_dir(td) == roots.REPO / "snapshots" / td.name
    for td in sorted(roots.NATURAL_TASKS.glob("NP-*")) if roots.NATURAL_TASKS.is_dir() else []:
        if (td / "task.json").exists():
            assert roots.snapshot_root(td) == roots.NATURAL_SNAPSHOTS.resolve()
