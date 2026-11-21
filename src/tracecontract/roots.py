"""Where a task's base snapshot and the records of its runs live, by population.

Controlled tasks (``tasks/CS-xx``) keep their base snapshots in ``<repo>/snapshots/<id>``. Natural
PR-review tasks are built under the git-ignored ``data/natural/`` (protocol §17.4):

* tasks in ``data/natural/tasks/<id>``;
* base snapshots in ``data/natural/snapshots/<id>``. The compiler records this root, relative to the
  repository, in the task's provenance notes as ``snapshot_root`` (``natural_pr._build``);
* run records in ``data/natural/runs/<run>``.

Every command and script that needs a task's base snapshot asks :func:`snapshot_root`, so a natural task
is never looked for under ``snapshots/`` and a controlled task never under ``data/natural``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SNAPSHOTS = REPO / "snapshots"
NATURAL = REPO / "data" / "natural"
NATURAL_TASKS = NATURAL / "tasks"
NATURAL_SNAPSHOTS = NATURAL / "snapshots"
NATURAL_RUNS = NATURAL / "runs"
NATURAL_PR = "natural:pr-review"


class RootError(ValueError):
    """A task's recorded snapshot root is unusable (absolute, outside the repository, or inside ``tasks/``)."""


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def population(task_dir: str | Path) -> str | None:
    """The population recorded in the task's ``task.json`` (None when the file is missing or unreadable)."""
    pop = _json(Path(task_dir) / "task.json").get("population")
    return pop if isinstance(pop, str) else None


def is_natural_pr(task_dir: str | Path) -> bool:
    return population(task_dir) == NATURAL_PR


def _notes(task_dir: Path) -> dict[str, Any]:
    notes = _json(task_dir / "provenance.json").get("notes")
    if isinstance(notes, str):  # provenance notes are stored as a JSON string
        try:
            notes = json.loads(notes)
        except ValueError:
            return {}
    return notes if isinstance(notes, dict) else {}


def snapshot_root(task_dir: str | Path, *, repo: str | Path = REPO) -> Path:
    """The directory that holds the task's base snapshot (``<root>/<task id>``).

    * natural:pr-review: ``<repo>/<snapshot_root>`` from the provenance notes; without that field, the
      ``snapshots`` directory next to the task's tasks directory (``data/natural/snapshots`` for
      ``data/natural/tasks/<id>``);
    * every other population: ``<repo>/snapshots``.

    A recorded root that is absolute, leaves the repository or lies under ``tasks/`` is refused.
    """
    repo = Path(repo).resolve()
    td = Path(task_dir)
    if not is_natural_pr(td):
        return repo / "snapshots"
    rel = _notes(td).get("snapshot_root")
    if rel:
        if not isinstance(rel, str) or Path(rel).is_absolute():
            raise RootError(f"{td.name}: snapshot_root {rel!r} must be a path relative to the repository")
        root = (repo / rel).resolve()
        if root != repo and repo not in root.parents:
            raise RootError(f"{td.name}: snapshot_root {rel!r} leaves the repository")
    else:
        root = td.resolve().parent.parent / "snapshots"
    tasks = (repo / "tasks").resolve()
    if root == tasks or tasks in root.parents:
        raise RootError(f"{td.name}: snapshot_root {root} lies under tasks/")
    return root


def snapshot_dir(task_dir: str | Path, *, repo: str | Path = REPO) -> Path:
    """The task's base snapshot directory: ``snapshot_root(task_dir) / <task id>``."""
    return snapshot_root(task_dir, repo=repo) / Path(task_dir).name
