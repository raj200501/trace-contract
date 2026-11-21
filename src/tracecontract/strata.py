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

A stratum's files lie in its task directory: ``strata/``, ``strata/<name>/``,
``strata/<name>/candidates/``, the manifest and every candidate file are refused if they are
symbolic links.

``tracecontract add-stratum-candidate`` registers a candidate (:func:`register_candidate`): it
captures the candidate from a state directory with the patch policy (:func:`capture_patch`),
writes the candidate file and the stratum manifest, and keeps a fresh attempt's attempt record in
the candidate (protocol v0.7 §15.4). It never writes ``task.json``.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .patches import PatchReport, diff_dirs, filter_patch
from .schemas import SCHEMA_VERSION, AttemptRecord, Candidate, CandidateOrigin, _Model, sha256_bytes
from .store import dump, load

TASK_STRATUM = "task"  # the task's own candidates, listed in its task.json
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
# Left out when a candidate is captured from a state directory: git metadata and caches (protocol §15.4).
CAPTURE_IGNORE = (".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis", "*.pyc", "*.pyo")


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


def _unlinked(task_dir: Path, *parts: str) -> Path:
    """``task_dir`` joined with ``parts``, refusing (``StratumError``) any of them that is a symbolic link (checked with lstat)."""
    path = task_dir
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise StratumError(f"{path.relative_to(task_dir).as_posix()} is a symbolic link; a stratum's directories and files "
                               "must lie in its task directory")
    return path


def _candidate_file(task_dir: Path, name: str, rel: str) -> Path:
    """``task_dir / rel``, if ``rel`` is a JSON file directly in ``strata/<name>/candidates/``, with no link on the way."""
    parts = PurePosixPath(rel).parts
    if "\\" in rel or len(parts) != 4 or parts[:3] != ("strata", name, "candidates") or not parts[3].endswith(".json"):
        raise StratumError(f"stratum {name!r}: candidate file {rel!r} is not strata/{name}/candidates/<file>.json")
    folder = _unlinked(task_dir, "strata", name, "candidates")  # strata/, strata/<name>/ and its candidates/ are real directories
    path = folder / parts[3]
    if not path.is_file() or path.is_symlink() or path.resolve().parent != folder.resolve():
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
    path = _unlinked(task_dir, "strata", f"{name}.json")
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


def capture_patch(base: Path, state: Path) -> tuple[str, PatchReport]:
    """The patch that turns the base snapshot ``base`` into the state directory ``state``, captured with the patch policy.

    Left out (protocol §15.4): ``.git`` and caches (``CAPTURE_IGNORE``), and the paths the patch
    policy removes before grading (``patches.DEFAULT_PROTECTED``: test files and test configuration),
    which the report lists under ``removed_protected``. A change that grading rejects (a binary file,
    a symbolic link, an unsafe path) stays in the patch and is listed under ``errors``: the candidate
    is then graded as a task failure, as the grader treats any rejected patch.
    """
    with tempfile.TemporaryDirectory(prefix="tc_capture_") as tmp:
        copies = []
        for src, dst in ((base, Path(tmp) / "base"), (state, Path(tmp) / "state")):
            shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns(*CAPTURE_IGNORE))
            copies.append(dst)
        raw = diff_dirs(*copies)
    return filter_patch(raw)


def attempt_record_problems(rec: AttemptRecord) -> list[str]:
    """What keeps an attempt record out of the repository: a session id or a session-local path in one of its texts.

    The schema checks the rest (configuration label, variant, sha256 forms, counts). Model identifiers
    are not searched for: they belong in the private run record that ``run_record`` points to.
    """
    from .verifier import holds_session_reference

    texts = [rec.attempt_id, rec.run_record]
    if rec.audit is not None:
        texts += [rec.audit.profile, rec.audit.record, *rec.audit.findings]
    return (["a field holds a session id or a session-local path (keep those in the private run or audit record)"]
            if any(holds_session_reference(t) for t in texts) else [])


def register_candidate(task_dir: Path, name: str, candidate: Candidate, *, own_ids: set[str],
                       description: str = "") -> tuple[str, str]:
    """Write ``candidate`` into the stratum ``name`` of the task in ``task_dir``; never ``task.json``.

    The candidate file is ``strata/<name>/candidates/<candidate id>.json``; the stratum manifest
    ``strata/<name>.json`` is created (with ``description``) or gets the file appended. The
    candidate must satisfy the stratum rules (:func:`load_stratum`) and its id may be used by no
    candidate of the task (``own_ids``) and of no other stratum of it. A candidate registered
    before may be registered again only with the same patch, origin and split: its file is
    rewritten (for example to add the audit verdict to its attempt record) and keeps its labels.
    Returns the candidate file relative to the task directory and what happened: ``created``
    (a new stratum), ``added`` or ``updated``.
    """
    check_name(name)
    task_id, cid = candidate.task_id, candidate.candidate_id
    if not cid.startswith(f"{task_id}-"):
        raise StratumError(f"candidate id {cid} does not start with '{task_id}-' (candidate ids must be unique across tasks)")
    if candidate.origin == CandidateOrigin.reference:
        raise StratumError(f"{cid} is a reference solution; the task's own reference is graded as the sanity check")
    if cid in own_ids:
        raise StratumError(f"candidate id {cid} is already used by the task's own candidates")
    strata_dir = _unlinked(task_dir, "strata")
    for other in sorted(strata_dir.glob("*.json")) if strata_dir.is_dir() else []:
        if other.stem != name and any(c.candidate_id == cid for _, c in load_stratum(task_dir, other.stem, task_id).candidates):
            raise StratumError(f"candidate id {cid} is already used by stratum {other.stem!r}")
    rel = f"strata/{name}/candidates/{cid}.json"
    manifest_path = _unlinked(task_dir, "strata", f"{name}.json")
    if manifest_path.exists():
        stratum = load_stratum(task_dir, name, task_id)
        listed = {c.candidate_id: (r, c) for r, c in stratum.candidates}
        sm = StratumManifest.model_validate_json(manifest_path.read_bytes())
    else:
        listed, sm = {}, StratumManifest(stratum=name, task_id=task_id, description=description, candidates=[])
    if cid in listed:
        old_rel, old = listed[cid]
        if (old_rel, old.patch_sha256, old.origin, old.split) != (rel, candidate.patch_sha256, candidate.origin, candidate.split):
            raise StratumError(f"stratum {name!r}: {cid} is registered with another patch, origin, split or file; "
                               "a registered candidate's patch never changes (register the new state under a new id)")
        candidate = candidate.model_copy(update={"labels": old.labels})
        what = "updated"
    else:
        what = "added" if manifest_path.exists() else "created"
    _unlinked(task_dir, "strata", name, "candidates")  # before anything is created: no link to follow
    (task_dir / "strata" / name / "candidates").mkdir(parents=True, exist_ok=True)
    folder = _unlinked(task_dir, "strata", name, "candidates")
    target = folder / f"{cid}.json"
    if target.is_symlink():
        raise StratumError(f"{rel} is a symbolic link; a stratum's directories and files must lie in its task directory")
    dump(candidate, target)
    if cid not in listed:
        dump(sm.model_copy(update={"candidates": [*sm.candidates, rel]}), manifest_path)
    load_stratum(task_dir, name, task_id)  # what was written satisfies the stratum rules
    return rel, what
