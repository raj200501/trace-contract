"""Candidate strata: extra candidates for a task, kept beside its frozen records.

A stratum manifest ``tasks/<id>/strata/<name>.json`` (:class:`StratumManifest`) lists candidate
files stored under ``tasks/<id>/strata/<name>/candidates/``. New candidates for a frozen task are
added this way, so the task's ``task.json`` and its existing candidate files never change.

``tracecontract evaluate --strata <name>`` grades a stratum's candidates with the task's verifiers,
in addition to the task's own candidates or, with ``--only-strata``, instead of them. The run
manifest records, for every stratum candidate it graded, its stratum and its file; the analysis
reads them back from there (:func:`run_stratum_candidates`), so a stratum is analysed as graded.

A stratum cannot hold a reference solution (the task's own reference is the sanity check). Its
candidate ids start with ``<task_id>-``, as every task's do, so they are unique across tasks
(grading logs are named by verifier and candidate id), and they must differ from the task's own
and from those of every other stratum selected with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .schemas import SCHEMA_VERSION, Candidate, CandidateOrigin, _Model, sha256_bytes
from .store import load

TASK_STRATUM = "task"  # the task's own candidates, listed in its task.json
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class StratumError(ValueError):
    """A stratum is missing or invalid, or conflicts with its task or with the run that recorded it."""


class StratumManifest(_Model):
    schema_version: str = SCHEMA_VERSION
    stratum: str  # the file name without ``.json``
    task_id: str
    description: str = ""
    candidates: list[str]  # candidate files relative to the task directory: strata/<stratum>/candidates/<file>.json


@dataclass(frozen=True)
class Stratum:
    name: str
    manifest_sha256: str
    candidates: list[tuple[str, Candidate]]  # (file relative to the task directory, candidate), in manifest order

    def record(self) -> dict:
        """The stratum's entry in a run manifest."""
        return {"manifest": f"strata/{self.name}.json", "manifest_sha256": self.manifest_sha256}


def check_name(name: str) -> str:
    """``name`` if it can name a stratum (and a file): letters, digits, ``.``, ``_``, ``-``; never ``task``."""
    if name == TASK_STRATUM or not _NAME.fullmatch(name):
        raise StratumError(f"invalid stratum name {name!r}: up to 64 letters, digits, '.', '_' or '-', starting with a "
                           f"letter or digit, and not {TASK_STRATUM!r} (the name of the task's own candidates)")
    return name


def _candidate_file(task_dir: Path, name: str, rel: str) -> Path:
    """``task_dir / rel``, if ``rel`` is a JSON file directly in ``strata/<name>/candidates/`` (no link out of it)."""
    parts = PurePosixPath(rel).parts
    if "\\" in rel or len(parts) != 4 or parts[:3] != ("strata", name, "candidates") or not parts[3].endswith(".json"):
        raise StratumError(f"stratum {name!r}: candidate file {rel!r} is not strata/{name}/candidates/<file>.json")
    path = task_dir / rel
    if not path.is_file() or path.resolve().parent != (task_dir / "strata" / name / "candidates").resolve():
        raise StratumError(f"stratum {name!r}: candidate file {rel!r} is missing or links out of strata/{name}/candidates/")
    return path


def _load_candidate(task_dir: Path, name: str, rel: str) -> Candidate:
    path = _candidate_file(task_dir, name, rel)
    try:
        return load(path, Candidate)  # validates the patch hash
    except ValueError as exc:
        raise StratumError(f"stratum {name!r}: {rel}: {exc}") from None


def load_stratum(task_dir: Path, name: str, task_id: str) -> Stratum:
    """Load and check the stratum ``name`` of the task in ``task_dir`` (``strata/<name>.json``)."""
    check_name(name)
    path = task_dir / "strata" / f"{name}.json"
    if not path.is_file():
        raise StratumError(f"{task_id} has no stratum {name!r} (no strata/{name}.json in its task directory)")
    raw = path.read_bytes()
    try:
        sm = StratumManifest.model_validate_json(raw)
    except ValueError as exc:
        raise StratumError(f"{task_id}: strata/{name}.json: {exc}") from None
    if (sm.stratum, sm.task_id) != (name, task_id):
        raise StratumError(f"strata/{name}.json describes stratum {sm.stratum!r} of task {sm.task_id!r}, not {name!r} of {task_id!r}")
    out: list[tuple[str, Candidate]] = []
    seen: set[str] = set()
    for rel in sm.candidates:
        c = _load_candidate(task_dir, name, rel)
        if c.task_id != task_id:
            raise StratumError(f"stratum {name!r}: {rel} is a candidate of task {c.task_id!r}, not {task_id!r}")
        if not c.candidate_id.startswith(f"{task_id}-"):
            raise StratumError(f"stratum {name!r}: candidate id {c.candidate_id} does not start with '{task_id}-' "
                               "(candidate ids must be unique across tasks)")
        if c.origin == CandidateOrigin.reference:
            raise StratumError(f"stratum {name!r}: {c.candidate_id} is a reference solution; the task's own reference "
                               "is graded as the sanity check")
        if c.candidate_id in seen:
            raise StratumError(f"stratum {name!r}: candidate id {c.candidate_id} is listed twice")
        seen.add(c.candidate_id)
        out.append((rel, c))
    return Stratum(name=name, manifest_sha256=sha256_bytes(raw), candidates=out)


def load_strata(task_dir: Path, names: list[str], task_id: str, own_ids: set[str]) -> dict[str, Stratum]:
    """The strata ``names`` of a task, by name; a candidate id may be used only once, by the task or by one stratum."""
    out: dict[str, Stratum] = {}
    owner = {cid: TASK_STRATUM for cid in own_ids}
    for name in dict.fromkeys(names):
        st = load_stratum(task_dir, name, task_id)
        for _, c in st.candidates:
            if c.candidate_id in owner:
                other = owner[c.candidate_id]
                raise StratumError(f"stratum {name!r} of {task_id}: candidate id {c.candidate_id} is already used by "
                                   + ("the task's own candidates" if other == TASK_STRATUM else f"stratum {other!r}"))
            owner[c.candidate_id] = name
        out[name] = st
    return out


def run_stratum_candidates(task_dir: Path, task_entry: dict) -> dict[str, tuple[str, str, Candidate]]:
    """The stratum candidates a run graded for one task: ``{candidate_id: (stratum, file, candidate)}``.

    Read from the task's entry in the run manifest (candidates recorded with a ``stratum``), so the files
    the run graded are the ones analysed; each must still hold the patch that was graded. Empty for a
    run without strata.
    """
    out: dict[str, tuple[str, str, Candidate]] = {}
    for cid, rec in task_entry.get("candidates", {}).items():
        name = rec.get("stratum")
        if name is None:
            continue
        c = _load_candidate(task_dir, check_name(name), rec["path"])
        if c.candidate_id != cid or c.patch_sha256 != rec["patch_sha256"]:
            raise StratumError(f"{task_entry['task_id']}: {rec['path']} no longer holds the candidate {cid} that the run "
                               f"graded (patch sha256 {rec['patch_sha256'][:12]})")
        out[cid] = (name, rec["path"], c)
    return out
