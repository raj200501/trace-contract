"""Compile natural PR-review tasks from the S9 survivors (population ``natural:pr-review``; protocol §15.6, §16, §17).

:func:`compile_pr_task` turns one family of ``s9_qualifying.json`` (outside the repository) into
``data/natural/tasks/NP-<k>/`` (git-ignored, §17.4). ``NP-<k>`` follows the order of the S11 families in
that file (its ``prs`` list with ``s11_family`` true); the qualifying PRs beyond the cap of two per
repository follow as reserves, which take a rejected family's place (§17.3). The task directory holds:

* ``task.json``: population ``natural:pr-review``, status ``pending_review``; the base-test subset in
  ``repo_test_args``; the pinned closure is filled in by the S10 environment step (``natural_env``);
* ``provenance.json``: the provenance record with :class:`~tracecontract.schemas.PRProvenance`: AIDev's
  revision and ids, the repository URL under the ``{owner}`` rule, the licence read from the LICENSE file at
  the base and compared with AIDev's field, the permission basis, the base, reviewed, addressing and head
  SHAs, the merge state and fidelity, the trace checksum, the capture method, the redaction status, the S9
  triage, the eligibility and its reasons;
* ``snapshot.json`` and the base snapshot (``data/natural/snapshots/NP-<k>/``): a ``git archive`` of the base
  (blobs fetched by id within the caps), checked file by file against the base tree;
* ``candidates/``: the reference (the addressing commit's tree against the base), ``<id>-pre-review``
  (origin ``natural_pre_review``, split ``eval``: the tree at ``original_commit_id`` against the base, with
  its source-evidence label) and the no-op in both splits;
* ``reconstruction_check.json``: the PR reconstruction record (:data:`PR_METHOD`), which the acceptance gate
  accepts for this population (``reconstruction.recorded_check``): the commits are reachable, the base
  follows the rule of §15.6, the merge rule holds (fidelity exact, or approximate), the snapshot equals the
  base tree, and each candidate reproduces its commit's tree;
* ``session.json``: the pseudonymised session (``ingest.github_pr``);
* ``s10.json``: the S10 record: the closure plan, the base-test subset and the planned runs, filled in by
  the S10 Docker step.

A family that fails a check is rejected with a stage and a reason (``rejection.json``), never with an
exception: unreachable SHAs, a merge that touches the commented file, an unlicensed or non-permissive
LICENSE, a fetch over the caps, an empty base-test subset; the S10 environment step adds "environment too
large", "no resolvable closure" and base tests that fail to collect (:func:`reject_task`).
``plan_only`` computes the base, the fidelity, the licence check and the planned closure, fetching only the
blobs it reads, and writes nothing but the fetch log. :func:`run_s10_environment` is the S10 step that needs the
network and Docker (``natural_env``): closure, image, base tests, B1; a dry run returns its planned commands.

**Generated material is never deleted.** Once B1 is frozen (P0), or contracts, verifiers, held-out candidates or
labels are built for a task (§19.7), a re-run of S10 must not replace its directory: :func:`compile_pr_task` (and
``_build`` and :func:`write_rejection` within it) and :func:`run_s10_environment` refuse a task directory that holds
anything but S10's own material (:func:`generated_material` lists S10's own files, so an unknown one counts too), with
outcome ``refused``, which is not a rejection, and change nothing. :func:`pr_recheck` re-runs the PR reconstruction
check of a built task against its bare clone, holding each stored patch to its commit's whole tree and the session
file to the one the compiler rebuilds, and rewrites only ``reconstruction_check.json``.

:func:`write_natural_index` writes the committed index ``data/manifests/natural_tasks_index.json``: ids, SHAs,
licences, file hashes, counts and S10 outcomes, each row's sample (§19.3) and the sanitize-natural:v1 counts of
its session; no text. Directories of repository files or generated tests are one manifest hash and a file count.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from . import natural_env as env
from . import roots
from .ingest.github_pr import (
    AIDEV_DATASET, AIDEV_REVISION, AIDev, BareClone, CapExceeded, GitError, SourceProblem, build_session, collect_thread,
    leftover_identifiers, make_pseudonymizer,
)
from .ingest.pseudonymize_pr import mask_repo_url
from .ingest.repo_evidence import licence_from_text
from .ingest.sanitize_natural import SANITIZER_VERSION, sanitize_obj, sanitize_session
from .patches import PatchApplyError, apply_patch, split_sections
from .reconstruction import RECORD, RecordCheck
from .schemas import (
    Candidate, CandidateOrigin, Eligibility, Fidelity, Label, LabelerKind, Population, PRProvenance, ProvenanceRecord,
    RedactionStatus, Session, Snapshot, SnapshotSource, Split, TaskManifest, TriageCategory, TriageProposal, sha256_bytes,
    sha256_text,
)
from .snapshot import manifest, manifest_sha256
from .store import dump, load, write_json
from .tasks import PR_SESSION_FILE

REPO = Path(__file__).resolve().parents[2]
QUALIFYING = Path(os.environ.get("TC_AIDEV_QUALIFYING", "/home/user/ext/aidev-v5-work/s9_qualifying.json"))
AIDEV_DATA = Path(os.environ.get("TC_AIDEV_DATA", "/home/user/ext/aidev-v5"))
INDEX = REPO / "data" / "manifests" / "natural_tasks_index.json"
COMPILER = "natural_pr:v1"
PR_METHOD = "reconstruction:pr-git:v1"
STAGE = "S10"
PERMISSIVE = ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause")  # the S2 licences (§15.6)
REGULAR = ("100644", "100755")
PACKAGE_FILES = ("pyproject.toml", "setup.py", "setup.cfg")
LICENCE_FILE = re.compile(r"^(?:licen[cs]e|copying)(?:[-_.](?:md|txt|rst|mit|apache|bsd))?$", re.I)
S10_RECORD, REJECTION = "s10.json", "rejection.json"
OVERLAY = "verifiers/repo_tests/overlay/"  # B1's overlay: the repository's test files (natural_env.build_b1)
B1 = "repo_tests"  # the one verifier S10 builds (natural_env.build_b1)
# S10's own material (generated_material): anything else in a task directory is material S10 must not replace.
S10_FILES = ("task.json", "provenance.json", "snapshot.json", PR_SESSION_FILE, S10_RECORD, RECORD, REJECTION)  # at the top
S10_DIRS = ("candidates", "verifiers")
S10_STATES = ("pending_review", "rejected")  # the task status and provenance eligibility S10 sets (_build, reject_task)
# The four candidates S10 builds (<task id>-<name>.json) and the labelers of their labels, in order: the pre-review's
# source-evidence label and the no-ops' construction label (_build).
S10_CANDIDATES = {"reference": (), "pre-review": ("source-evidence:aidev-s9",), "noop-dev": ("construction",),
                  "noop-eval": ("construction",)}
B1_FILES = ("overlay", "selection.json", "check_ids.json", "spec.json")  # what natural_env.build_b1 writes in verifiers/repo_tests
# Fields of B1's spec that build_b1 leaves unset and later steps set: a freeze (freeze point F1 of P0: frozen, frozen_at and
# checks_sha256), a contract, a generation or an audit record, a new version.
B1_FROZEN = ("frozen", "frozen_at", "checks_sha256")
B1_LATER = ("contract_id", "generation", "audit")
EXTENSION_FROM = 26  # §19.3: the first sample's families and reserves are NP-01 to NP-25; the extension's start at NP-26
PR_COMPARED = ("session_sha256", "base_manifest_sha256", "reference_candidate", "reference_patch_sha256", "pre_review_candidate",
               "pre_review_patch_sha256", "base_commit", "reviewed_commit", "addressing_commit")
CHECK_TITLES = {
    "a_commits_reachable": "The reviewed and the addressing commits are in the clone, and the addressing commit descends from the reviewed one",
    "b_base_rule": "The base is the merge-base of the first commit's parent with the default branch (else that parent: approximate)",
    "c_merge_rule": "No merge between the base and the addressing commit changes the commented file (merges that do not: approximate)",
    "d_snapshot_equals_base_tree": "Every file of the snapshot is the base tree's blob, and the snapshot holds no other file",
    "e_candidates_reproduce_commits": "The reference and pre-review patches, applied to the snapshot, reproduce their commits' files",
    "f_no_stale_copies": "No .git directory; cache or backup copies of changed modules are listed (they are part of the base tree)",
}
_ARTIFACT = re.compile(r"(?:^|/)__pycache__/|\.py[co]$|\.orig$|\.rej$|~$|\.bak$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Reject(Exception):
    """A family fails a check of stage ``stage`` (S10): reported with its reason, never raised out of the compiler."""

    def __init__(self, reason: str, *, stage: str = STAGE, **details: Any) -> None:
        super().__init__(reason)
        self.reason, self.stage, self.details = reason, stage, details


class Refused(Exception):
    """A step would replace, delete or rewrite a task directory that holds more than S10's own material
    (:func:`generated_material`: material made after S10, or anything S10 does not write).

    It is refused and nothing is deleted. A refusal is not a rejection: the family keeps its task, its snapshot and its
    place in the index.
    """

    def __init__(self, task_dir: Path, found: list[str], *, step: str) -> None:
        shown = ", ".join(found[:6]) + (f" and {len(found) - 6} more" if len(found) > 6 else "")
        self.task_id, self.found, self.step = Path(task_dir).name, list(found), step
        self.reason = (f"{step} refused: {self.task_id} holds material beyond S10's own ({shown}); a task directory with "
                       "generated or unknown material is never replaced or deleted (§19.7). natural_pr.pr_recheck re-checks "
                       "its PR record without a rebuild")
        super().__init__(self.reason)


def _json_or_none(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _dumped(model: Session) -> bytes:
    """The bytes ``store.dump`` writes for ``model`` (the session file of a build)."""
    return (model.model_dump_json(indent=2) + "\n").encode("utf-8")


def generated_material(task_dir: str | Path) -> list[str]:
    """What a task directory holds beyond S10's own material, as task-relative names and ids (never a test file name).

    S10's own material is listed, and everything else counts, so that an output no rule names is kept too (fail safe):

    * at the top, the files of :data:`S10_FILES` (task.json, provenance.json, snapshot.json, session.json, s10.json, the
      reconstruction record, rejection.json) and the directories ``candidates/`` and ``verifiers/``;
    * in ``candidates/``, the four S10 candidates (:data:`S10_CANDIDATES`), each with exactly the labels S10 gives it;
    * in ``verifiers/``, B1 (``repo_tests/``) with only what ``natural_env.build_b1`` writes (:data:`B1_FILES`), and a spec
      on which no field of :data:`B1_FROZEN` or :data:`B1_LATER` is set and whose version is 1: a frozen B1 (P0's freeze
      point F1) is material made after S10;
    * in task.json, no contract, no verifier but B1, no candidate but the four, no scripted turn and no snapshot overlay,
      and a status S10 sets (:data:`S10_STATES`); in provenance.json, an eligibility S10 sets (a reviewer's ``eligible``
      is not).

    So ``contracts/``, ``labels/``, ``strata/``, ``verifiers_extra.json``, another verifier or candidate, a label added to
    an S10 candidate, a frozen B1, a reviewed eligibility and any unknown file or directory count. A file of S10's that
    cannot be read where its content is checked counts as well. Empty for a missing directory, a rejection record or an
    S10-only task.
    """
    td = Path(task_dir)
    if not td.is_dir():
        return []
    found: list[str] = []

    def name(p: Path) -> str:
        rel = p.relative_to(td).as_posix()
        return rel + "/" if p.is_dir() else rel

    def own(p: Path, *, directory: bool) -> bool:
        return not p.is_symlink() and (p.is_dir() if directory else p.is_file())

    found += [name(p) for p in sorted(td.iterdir())
              if not (p.name in S10_FILES and own(p, directory=False)) and not (p.name in S10_DIRS and own(p, directory=True))]
    cands = {f"{td.name}-{n}.json": labelers for n, labelers in S10_CANDIDATES.items()}
    cdir = td / "candidates"
    if own(cdir, directory=True):
        for c in sorted(cdir.iterdir()):
            if c.name not in cands or not own(c, directory=False):
                found.append(name(c))
                continue
            data = _json_or_none(c)
            labels = data.get("labels") if isinstance(data, dict) else None
            if not isinstance(labels, list):
                found.append(f"{name(c)}: unreadable")
            elif [lb.get("labeler") if isinstance(lb, dict) else None for lb in labels] != list(cands[c.name]):
                found.append(f"{name(c)}: a label added or changed after S10")
    vdir = td / "verifiers"
    if own(vdir, directory=True):
        for v in sorted(vdir.iterdir()):
            if v.name != B1 or not own(v, directory=True):
                found.append(name(v))
                continue
            found += [name(f) for f in sorted(v.iterdir()) if f.name not in B1_FILES or not own(f, directory=f.name == "overlay")]
            if not (v / "spec.json").is_file():
                continue
            spec = _json_or_none(v / "spec.json")
            if not isinstance(spec, dict):
                found.append(f"verifiers/{B1}/spec.json: unreadable")
                continue
            frozen = [k for k in B1_FROZEN if spec.get(k)]
            later = [k for k in B1_LATER if spec.get(k) is not None] + (["version"] if spec.get("version", 1) != 1 else [])
            if frozen:
                found.append(f"verifiers/{B1}/spec.json: B1 frozen ({', '.join(frozen)})")
            if later:
                found.append(f"verifiers/{B1}/spec.json: changed after S10 ({', '.join(later)})")
    if (td / "task.json").is_file():
        m = _json_or_none(td / "task.json")
        if not isinstance(m, dict):
            found.append("task.json: unreadable")
            m = {}
        found += [f"task.json: {k}" for k in ("contracts", "scripted_turns", "snapshot_overlays") if m.get(k)]
        found += [f"task.json: verifier {v}" for v in m.get("verifiers") or [] if v != f"verifiers/{B1}/spec.json"]
        found += [f"task.json: candidate {c}" for c in m.get("candidates") or []
                  if str(c).removeprefix("candidates/") not in cands]
        if m.get("status") not in (None, *S10_STATES):
            found.append(f"task.json: status {m.get('status')}")
    if (td / "provenance.json").is_file():
        prov = _json_or_none(td / "provenance.json")
        if not isinstance(prov, dict):
            found.append("provenance.json: unreadable")
        elif prov.get("eligibility") not in (None, *S10_STATES):
            found.append(f"provenance.json: eligibility {prov.get('eligibility')}")
    return sorted(dict.fromkeys(str(x) for x in found))


# --------------------------------------------------------------------------- families


@dataclass(frozen=True)
class Family:
    """One family of the S9 survivors (a PR and its earliest qualifying comment), in memory; its URL is masked before use."""

    task_id: str
    role: str  # "family" (an S11 family) or "reserve" (the next PR of a repository, §17.3)
    pr_id: int
    repo_id: int
    pr_number: int
    pr_created_at: str
    agent: str
    comment_id: int
    other_qualifying_comment_ids: tuple[int, ...]
    path: str
    reviewed_commit: str
    addressing_commit: str
    head_ref: str
    head_sha: str | None
    default_branch_ref: str | None
    first_commit: str
    issue_id: int | None
    issue_number: int | None
    licence_aidev: str | None
    repo_url: str
    bare_clone: Path
    rank_in_repository: int
    judges: tuple[dict[str, Any], ...] = ()


def load_families(path: str | Path = QUALIFYING) -> list[Family]:
    """The S11 families of ``s9_qualifying.json`` as NP-01 ... in the file's order, then the reserves (§17.3).

    A file whose PRs carry explicit ``task_id`` and ``role`` (``s9_qualifying_combined.json``, the families of both samples,
    §19.3) gives those instead: its PRs with a task id, in the order of their ids; a PR whose task id is null (no family is
    built for it) is left out."""
    q = json.loads(Path(path).read_text(encoding="utf-8"))
    comments = {int(c["comment_id"]): c for c in q["comments"]}
    explicit = any("task_id" in p for p in q["prs"])
    if explicit:
        order = sorted((p for p in q["prs"] if p.get("task_id")), key=lambda p: _num(str(p["task_id"])))
        if len({p["task_id"] for p in order}) != len(order):
            raise ValueError(f"{path}: a task id is given to more than one PR")
    else:
        order = [p for p in q["prs"] if p.get("s11_family")] + [p for p in q["prs"] if not p.get("s11_family")]
    out = []
    for k, p in enumerate(order, 1):
        c = comments[int(p["earliest_qualifying_comment_id"])]
        judges = tuple({x: (c.get(j) or {}).get(x) for x in ("request_type", "addressed", "testable_offline", "confidence")}
                       for j in ("judge_1", "judge_2"))
        out.append(Family(
            task_id=str(p["task_id"]) if explicit else f"NP-{k:02d}",
            role=str(p["role"]) if explicit else "family" if p.get("s11_family") else "reserve", pr_id=int(p["pr_id"]),
            repo_id=int(p["repo_id"]), pr_number=int(p["pr_number"]), pr_created_at=str(p["pr_created_at"]), agent=str(p["agent"]),
            comment_id=int(c["comment_id"]),
            other_qualifying_comment_ids=tuple(sorted(int(x) for x in p["qualifying_comment_ids"] if int(x) != int(c["comment_id"]))),
            path=c["path"], reviewed_commit=c["original_commit_id"], addressing_commit=c["later_commit_sha"],
            head_ref=c["pr_head_ref"], head_sha=c.get("pr_head_sha"), default_branch_ref=c.get("default_branch_ref"),
            first_commit=c["pr_commits_first_sha"], issue_id=c.get("issue_id"), issue_number=c.get("issue_number"),
            licence_aidev=c.get("license"), repo_url=c["repo_url"], bare_clone=Path(c["bare_clone"]),
            rank_in_repository=int(p.get("rank_in_repository_by_creation") or 0), judges=judges))
    return out


def find_family(families: list[Family], pr_id: int) -> Family:
    for f in families:
        if f.pr_id == int(pr_id):
            return f
    raise KeyError(f"PR {pr_id} is not a family or reserve of the S9 survivors")


def masked_url(fam: Family, persons: frozenset[str] | None) -> tuple[str, bool]:
    """The repository URL under the ``{owner}`` rule: the owner is masked when it acts as an account in AIDev."""
    owner = fam.repo_url.rstrip("/").split("/")[-2].lower()
    acts = bool(persons) and owner in persons
    return mask_repo_url(fam.repo_url, acts), acts


# --------------------------------------------------------------------------- the git checks of S10


@dataclass
class GitStates:
    base: str
    base_rule: str
    first: str
    parent: str
    reviewed: str
    addressing: str
    head: str | None
    default_tip: str | None
    merges: list[str]
    touching: list[str]
    base_date: str
    changed: list[tuple[str, str]]  # base -> addressing (repository paths)
    changed_reviewed: list[tuple[str, str]]  # base -> reviewed
    pr_commits: list[str]  # the PR's commits in the addressing commit's history (AIDev order)
    approximations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    items: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def fidelity(self) -> Fidelity:
        return Fidelity.approximate if self.approximations else Fidelity.exact

    @property
    def merge_state(self) -> str:
        return "merge_touches_the_commented_file" if self.touching else \
            "merges_not_touching_the_commented_file" if self.merges else "no_merges"


def resolve_states(fam: Family, clone: BareClone, pr_commits: list[str]) -> GitStates:
    """Reachability, the first commit, the base rule and the merge rule of §15.6 (commits and trees only)."""
    items: dict[str, list[dict[str, Any]]] = {"a": [], "b": [], "c": []}
    reviewed, addressing = clone.commit(fam.reviewed_commit), clone.commit(fam.addressing_commit)
    missing = [w for w, s in (("reviewed", reviewed), ("addressing", addressing)) if s is None]
    if missing:
        raise Reject(f"unreachable SHAs: the {' and the '.join(missing)} commit{'s are' if len(missing) > 1 else ' is'} not in "
                     "the clone", check="a_commits_reachable")
    items["a"] += [{"item": "reviewed commit in the clone", "status": "passed", "sha": reviewed},
                   {"item": "addressing commit in the clone", "status": "passed", "sha": addressing}]
    if not clone.is_ancestor(reviewed, addressing):
        raise Reject("the addressing commit does not descend from the reviewed commit", check="a_commits_reachable")
    items["a"].append({"item": "the addressing commit descends from the reviewed commit", "status": "passed"})
    at_reviewed = [e for e in clone.ls_tree(reviewed, [fam.path]) if e[3] == fam.path]
    if not at_reviewed or at_reviewed[0][1] != "blob":
        raise Reject("the commented file is not a file at the reviewed commit", check="a_commits_reachable")
    notes, approx = [], []
    head = clone.ref(fam.head_ref)
    if head is None:
        notes.append("the PR head ref is not in the clone")
    else:
        if fam.head_sha and head != fam.head_sha:
            notes.append("the PR head ref moved since S9")
        if not clone.is_ancestor(addressing, head):
            notes.append("the addressing commit is not in the PR head's history")
    history = set(clone.rev_list(addressing))
    pr_set = set(pr_commits)
    in_history = [c for c in pr_commits if c in history]
    meta = clone.meta(in_history)
    roots = [c for c in in_history if c in meta and not set(meta[c]["parents"]) & pr_set]
    first = fam.first_commit
    if first in roots and len(roots) == 1:
        items["b"].append({"item": "AIDev's first pr_commits row is the PR's only commit without a PR parent", "status": "passed",
                           "sha": first})
    elif len(roots) == 1:
        first = roots[0]
        approx.append("AIDev's first pr_commits row is not the PR's first commit; the first commit is the only PR commit "
                      "without a PR parent")
        items["b"].append({"item": "first commit from git", "status": "passed", "sha": first})
    elif first in roots:
        approx.append(f"{len(roots)} PR commits have no PR parent; the first commit is AIDev's first pr_commits row")
        items["b"].append({"item": "first commit: AIDev's first row, one of several roots", "status": "passed", "sha": first})
    else:
        raise Reject("the PR's first commit cannot be determined (AIDev's first row is not a root of the PR's commits)",
                     check="b_base_rule")
    parents = meta[first]["parents"]
    if not parents:
        raise Reject("the PR's first commit has no parent", check="b_base_rule")
    parent = parents[0]
    default_tip = clone.ref(fam.default_branch_ref) if fam.default_branch_ref else None
    mb = clone.merge_base(parent, default_tip) if default_tip else None
    if mb is not None:
        base, rule = mb, "merge_base"
        if mb != parent:
            approx.append("the first commit's parent is not on the default branch: the base is their merge-base, so the "
                          "candidate patches also hold the commits between the merge-base and that parent")
        items["b"].append({"item": "merge-base of the first commit's parent with the default branch", "status": "passed",
                           "sha": base, "equals_parent": mb == parent})
    else:
        base, rule = parent, "parent_of_first_commit"
        approx.append("the merge-base of the first commit's parent with the default branch cannot be determined"
                      + ("" if default_tip else " (no default branch in the clone)") + "; the base is that parent (§15.6)")
        items["b"].append({"item": "merge-base not determinable; the base is the first commit's parent", "status": "passed",
                           "sha": base})
    if not (clone.is_ancestor(base, reviewed) and clone.is_ancestor(base, addressing)):
        raise Reject("the base is not an ancestor of the reviewed and the addressing commits", check="b_base_rule")
    merges = clone.rev_list("--merges", addressing, f"^{base}")
    mmeta = clone.meta(merges)
    touching = [m for m in merges if clone.changed(mmeta[m]["parents"][0], m, [fam.path])]
    items["c"] += [{"item": "merge", "sha": m, "touches_the_commented_file": m in touching,
                    "status": "failed" if m in touching else "passed"} for m in merges]
    if touching:
        raise Reject("a merge between the base and the addressing commit changes the commented file (§15.6)",
                     base_commit=base, merges=merges, merges_touching=touching, check="c_merge_rule")
    if merges:
        approx.append(f"{len(merges)} merge commit(s) between the base and the addressing commit; none changes the commented file")
    base_date = clone.meta([base])[base]["committed_at"]
    return GitStates(base=base, base_rule=rule, first=first, parent=parent, reviewed=reviewed, addressing=addressing, head=head,
                     default_tip=default_tip, merges=merges, touching=touching, base_date=base_date,
                     changed=clone.changed(base, addressing), changed_reviewed=clone.changed(base, reviewed),
                     pr_commits=in_history, approximations=approx, notes=notes, items=items)


def snapshot_scope(clone: BareClone, st: GitStates, commented: str) -> str:
    """The workspace: the deepest package directory (pyproject.toml, setup.py or setup.cfg at the base) that holds the
    commented file and every Python file the PR changes; the repository root ("") when there is none."""
    names = [p for _, t, _, p in clone.ls_tree(st.base) if t == "blob"]
    roots = {str(PurePosixPath(n).parent) for n in names if "/" in n and PurePosixPath(n).name in PACKAGE_FILES}
    need = [commented, *(p for _, p in st.changed + st.changed_reviewed if p.endswith(".py"))]
    fits = [r for r in roots if all(p.startswith(r + "/") for p in need)]
    return max(fits, key=lambda r: (len(r.split("/")), r)) if fits else ""


def _rel(path: str, subdir: str) -> str | None:
    if not subdir:
        return path
    return path[len(subdir) + 1:] if path.startswith(subdir + "/") else None


def licence_check(clone: BareClone, base: str, subdir: str, aidev: str | None) -> dict[str, Any]:
    """The licence of the repository's LICENSE file at the base (and of the package's own, in a monorepo), against AIDev's field."""
    def files(d: str) -> list[str]:
        got = [p for m, t, _, p in clone.list_dir(base, d) if t == "blob" and m in REGULAR and LICENCE_FILE.match(PurePosixPath(p).name)]
        return sorted(got, key=lambda p: (PurePosixPath(p).name.lower() not in ("license", "licence"), len(p), p))

    root, pkg = files(""), files(subdir) if subdir else []
    texts = clone.read_many(base, root + pkg, label="licence")
    ident = {p: licence_from_text(texts[p].decode("utf-8", "replace")) if p in texts else None for p in root + pkg}
    rec: dict[str, Any] = {"files": [{"file": p.rsplit("/", 1)[-1], "where": "package" if p in pkg else "root", "spdx": ident[p],
                                      "sha256": sha256_bytes(texts[p]) if p in texts else None} for p in root + pkg],
                           "aidev": aidev, "rule": "the S2 licences: " + ", ".join(PERMISSIVE)}
    found = [ident[p] for p in root if ident[p]]
    rec["spdx"] = found[0] if found else None
    rec["sha256"] = next((r["sha256"] for r in rec["files"] if r["spdx"] == rec["spdx"] and r["where"] == "root"), None)
    rec["agrees"] = aidev in found if found else None
    if not root:
        raise Reject("unlicensed: no LICENSE file at the repository root at the base", licence=rec)
    if not found:
        raise Reject("the LICENSE file at the base is not identified as a permissive licence", licence=rec)
    bad = sorted({x for x in [*found, *(ident[p] for p in pkg if ident[p])] if x not in PERMISSIVE})
    if bad:
        raise Reject(f"non-permissive licence at the base: {', '.join(bad)}", licence=rec)
    rec["permissive"] = True
    return rec


# --------------------------------------------------------------------------- snapshot and candidates


def git_oid(data: bytes, like: str) -> str:
    """The git blob id of ``data``, in the hash of ``like`` (SHA-1, or SHA-256 for 64 hex digits)."""
    h = hashlib.sha256() if len(like) == 64 else hashlib.sha1()  # noqa: S324 - git's object id, not a security hash
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def _extract(data: bytes, dest: Path, strip: str) -> None:
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        keep = []
        for m in tf.getmembers():
            if m.issym() or m.islnk() or not (m.isfile() or m.isdir()):
                continue
            name = m.name.rstrip("/")
            if strip:
                if name != strip and not name.startswith(strip + "/"):
                    continue
                name = name[len(strip) + 1:]
            p = PurePosixPath(name)
            if not name or p.is_absolute() or ".." in p.parts:
                if name:
                    raise SourceProblem("unsafe member in the archive of the base")
                continue
            m.name = name
            keep.append(m)
        dest.mkdir(parents=True, exist_ok=True)
        tf.extractall(dest, members=keep, filter="data")


def materialize_base(clone: BareClone, base: str, subdir: str, dest: Path) -> dict[str, Any]:
    """``git archive`` of the base (the workspace's directory), its blobs fetched by id first; checked against the tree.

    A monorepo package is archived as the subtree ``<base>:<subdir>``, not as the commit with a pathspec: on a blob-less
    partial clone, ``git archive <commit> <subdir>`` fetches every missing blob of the whole commit (git 2.43), far
    beyond the workspace and towards the caps of §15.6.
    """
    entries = clone.ls_tree(base, [subdir] if subdir else [])
    regular = {o for m, t, o, _ in entries if t == "blob" and m in REGULAR}
    fetched = clone.ensure(base, regular, label=f"base tree {base[:12]}")
    data = clone.run("archive", "--format=tar", f"{base}:{subdir}" if subdir else base, fetch=True, label="archive").stdout
    if dest.exists():
        shutil.rmtree(dest)
    _extract(data, dest, "")
    got = compare_base(clone, base, subdir, dest, entries=entries)
    return {**{k: v for k, v in got.items() if k not in ("git_dir", "artifacts")}, "blobs_fetched": fetched,
            "git_dir": got["git_dir"], "artifacts": got["artifacts"]}


def compare_base(clone: BareClone, base: str, subdir: str, dest: Path, *,
                 entries: list[tuple[str, str, str, str]] | None = None) -> dict[str, Any]:
    """Compare a snapshot directory with the base tree, file by file by git blob id; nothing is fetched or written.

    The files the tree has and the directory lacks are ``missing``, the reverse ``extra``; symbolic links and submodules of
    the tree are counted (a snapshot does not materialise them).
    """
    entries = clone.ls_tree(base, [subdir] if subdir else []) if entries is None else entries
    regular = {p: (m, o) for m, t, o, p in entries if t == "blob" and m in REGULAR}
    links = sorted(p for m, t, _, p in entries if m == "120000")
    gitlinks = sorted(p for _, t, _, p in entries if t == "commit")
    want = {_rel(p, subdir): v for p, v in regular.items()}
    entries_now = manifest(dest)
    have = {rel for rel, _ in entries_now}
    mismatched = sorted(rel for rel, (_, oid) in want.items() if rel in have and git_oid((dest / rel).read_bytes(), oid) != oid)
    return {"n_files": len(entries_now), "manifest_sha256": manifest_sha256(entries_now), "symlinks": len(links),
            "gitlinks": len(gitlinks), "mismatched": mismatched, "missing": sorted(set(want) - have),
            "extra": sorted(have - set(want)), "git_dir": (dest / ".git").exists(),
            "artifacts": sorted(rel for rel in have if _ARTIFACT.search(rel))}


def candidate_patch(clone: BareClone, base: str, commit: str, subdir: str) -> tuple[str, list[dict[str, str]], list[dict[str, str]]]:
    """The diff of ``commit``'s tree against the base, in the workspace (``--relative``), as the grader applies it.

    Sections the patch policy refuses (binary files, symbolic links, submodules) and files that are not UTF-8 text are
    left out and returned, so that the candidate stays gradable; the caller records them as approximations.
    """
    scope = [subdir] if subdir else []
    raw = clone.raw_diff(base, commit, scope)
    clone.ensure(base, {r["old"] for r in raw if r["old_mode"] in REGULAR}, label=f"diff {base[:12]}")
    clone.ensure(commit, {r["new"] for r in raw if r["new_mode"] in REGULAR}, label=f"diff {commit[:12]}")
    args = ["diff", "--binary", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--full-index",
            "--diff-algorithm=myers", "--src-prefix=a/", "--dst-prefix=b/", *([f"--relative={subdir}"] if subdir else []),
            base, commit, "--", *scope]
    out = clone.run(*args, fetch=True, label="diff").stdout
    special = {_rel(r["path"], subdir): r for r in raw if r["old_mode"] in ("120000", "160000") or r["new_mode"] in ("120000", "160000")}
    kept, dropped = [], []
    for chunk in re.split(rb"(?m)^(?=diff --git )", out):
        if not chunk.strip():
            continue
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            m = re.match(rb"diff --git a/(.+?) b/", chunk)
            dropped.append({"path": m.group(1).decode("utf-8", "replace") if m else "?", "why": "not UTF-8 text"})
            continue
        secs = split_sections(text)
        sec = secs[0] if secs else None
        if sec is None:
            continue
        if sec.path in special:
            dropped.append({"path": sec.path, "why": "symbolic link or submodule"})
        elif sec.is_binary:
            dropped.append({"path": sec.path, "why": "binary file"})
        else:
            kept.append(text)
    patch = "".join(kept)
    if patch and not patch.endswith("\n"):
        patch += "\n"
    return patch, raw, dropped


def _tree_state(root: Path) -> dict[str, tuple[str, ...]]:
    """Every file and symbolic link under ``root`` by its relative path: a file's sha256 and executable bit, a link's target."""
    out: dict[str, tuple[str, ...]] = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            out[rel] = ("link", os.readlink(p))
        elif p.is_file():
            out[rel] = ("file", sha256_bytes(p.read_bytes()), "x" if p.stat().st_mode & 0o111 else "")
    return out


def verify_candidate(snapshot: Path, patch: str, raw: list[dict[str, str]], subdir: str, dropped: list[dict[str, str]]) -> dict[str, Any]:
    """Apply the patch to a copy of the snapshot and compare the whole result with the commit's tree.

    Every file the commit changes (``raw``, but the ``dropped`` ones the candidate leaves out) must be the commit's blob, or
    be gone if the commit deletes it; and no other file may differ from the snapshot (``extra_changes``: a file the patch
    adds, deletes or edits, or whose mode or link it changes, that the commit does not change or whose change is left
    out). So a stored patch is held to its commit's tree also where it differs from the patch the compiler makes
    (:func:`pr_recheck`).
    """
    skip = {d["path"] for d in dropped}
    allowed = {rel for rel in (_rel(r["path"], subdir) for r in raw) if rel is not None} - skip
    with tempfile.TemporaryDirectory(prefix="tc_np_verify_") as tmp:
        try:
            ws, _ = apply_patch(snapshot, patch, Path(tmp) / "ws")
        except (PatchApplyError, OSError) as exc:
            return {"status": "failed", "reason": f"the patch does not apply to the snapshot ({type(exc).__name__})"}
        bad = []
        for r in raw:
            rel = _rel(r["path"], subdir)
            if rel is None or rel in skip:
                continue
            f = ws / rel
            if r["status"].startswith("D"):
                if f.exists() or f.is_symlink():
                    bad.append(rel)
            elif r["new_mode"] in REGULAR and (not f.is_file() or git_oid(f.read_bytes(), r["new"]) != r["new"]):
                bad.append(rel)
        was, now = _tree_state(snapshot), _tree_state(ws)
        extra = sorted(p for p in set(was) | set(now) if was.get(p) != now.get(p) and p not in allowed)
    n = sum(1 for r in raw if _rel(r["path"], subdir) not in skip)
    reason = f"{len(bad)} of {n} changed file(s) differ from the commit" if bad else f"{n} changed file(s) reproduced"
    if extra:
        reason += f"; the patch also changes {len(extra)} other file(s), which the candidate must leave as at the base"
    return {"status": "failed" if bad or extra else "passed", "files": n, "mismatched": sorted(bad), "extra_changes": extra,
            "reason": reason}


# --------------------------------------------------------------------------- the reconstruction record


def _check(cid: str, status: str, reason: str, items: list[dict[str, Any]] | None = None, approximations: list[str] | None = None) -> dict[str, Any]:
    return {"check_id": cid, "title": CHECK_TITLES[cid], "status": status, "reason": reason, "items": items or [],
            "approximations": approximations or []}


def pr_reconstruction(task_id: str, st: GitStates, snap: dict[str, Any], ref_v: dict[str, Any], pre_v: dict[str, Any],
                      inputs: dict[str, Any], approximations: list[str], *, recorded_manifest: str | None = None) -> dict[str, Any]:
    """The PR reconstruction record (:data:`PR_METHOD`), in the shape :func:`reconstruction.recorded_check` reads.

    ``recorded_manifest`` (a re-check, :func:`pr_recheck`): the manifest hash snapshot.json records, which the snapshot
    directory must also have for check d to pass.
    """
    d_bad = snap["mismatched"] + snap["missing"] + snap["extra"]
    stale_manifest = recorded_manifest is not None and recorded_manifest != snap["manifest_sha256"]
    checks = [
        _check("a_commits_reachable", "passed", "both commits are in the clone; the addressing commit descends from the reviewed one",
               st.items.get("a")),
        _check("b_base_rule", "passed", f"base by the rule {st.base_rule}", st.items.get("b"),
               [a for a in st.approximations if "merge commit" not in a]),
        _check("c_merge_rule", "failed" if st.touching else "passed",
               f"{len(st.merges)} merge(s) between the base and the addressing commit, {len(st.touching)} changing the commented file",
               st.items.get("c"), [a for a in st.approximations if "merge commit" in a]),
        _check("d_snapshot_equals_base_tree", "failed" if d_bad or snap["git_dir"] or stale_manifest else "passed",
               f"{snap['n_files']} file(s); {len(snap['mismatched'])} differ from their blob, {len(snap['missing'])} missing, "
               f"{len(snap['extra'])} extra" + ("; the directory's manifest is not the one snapshot.json records" if stale_manifest
                                                else ""),
               [{"symlinks_not_materialised": snap["symlinks"], "submodules_not_materialised": snap["gitlinks"],
                 **({"manifest_equals_snapshot_record": not stale_manifest} if recorded_manifest is not None else {})}]),
        _check("e_candidates_reproduce_commits", "passed" if ref_v["status"] == pre_v["status"] == "passed" else "failed",
               f"reference: {ref_v['reason']}; pre-review: {pre_v['reason']}",
               [{"candidate": "reference", **ref_v}, {"candidate": "pre-review", **pre_v}]),
        _check("f_no_stale_copies", "failed" if snap["git_dir"] else "passed",
               "no .git directory" + (f"; {len(snap['artifacts'])} cache or backup file(s) in the base tree itself"
                                      if snap["artifacts"] else ""), [{"artifacts_in_the_base_tree": len(snap["artifacts"])}]),
    ]
    states = {c["status"] for c in checks}
    status = "failed" if "failed" in states else "passed" if states == {"passed"} else "incomplete"
    return {"task_id": task_id, "method": PR_METHOD, "status": status, "passed": {"passed": True, "failed": False}.get(status),
            "fidelity": (Fidelity.approximate if approximations else Fidelity.exact).value, "approximations": approximations,
            "checks": checks, "inputs": inputs, "notes": st.notes, "files": []}


def pr_current_inputs(task_dir: Path) -> dict[str, Any]:
    """The inputs a PR reconstruction record must match: the session file, the base manifest, the candidates and the commits."""
    m = load(task_dir / "task.json", TaskManifest)
    snap = load(task_dir / (m.snapshot or "snapshot.json"), Snapshot)
    prov = load(task_dir / m.provenance, ProvenanceRecord)
    cands = []
    for p in m.candidates:
        try:
            cands.append(load(task_dir / p, Candidate))
        except Exception:  # noqa: BLE001 - as in reconstruction.current_inputs: a candidate that does not load is not used
            continue
    ref = next((c for c in cands if c.origin == CandidateOrigin.reference), None)
    pre = next((c for c in cands if c.origin == CandidateOrigin.natural_pre_review), None)
    sess = task_dir / PR_SESSION_FILE
    pr = prov.natural_pr
    return {"task_id": m.task_id, "session_sha256": sha256_bytes(sess.read_bytes()) if sess.is_file() else None,
            "base_manifest_sha256": snap.file_manifest_sha256,
            "reference_candidate": ref.candidate_id if ref else None, "reference_patch_sha256": sha256_text(ref.patch) if ref else None,
            "pre_review_candidate": pre.candidate_id if pre else None, "pre_review_patch_sha256": sha256_text(pre.patch) if pre else None,
            "base_commit": pr.base_commit if pr else None, "reviewed_commit": pr.reviewed_commit if pr else None,
            "addressing_commit": pr.addressing_commit if pr else None}


def recorded_pr_check(task_dir: Path, repo_root: Path | None = None) -> RecordCheck:
    """Whether a natural PR-review task's ``reconstruction_check.json`` counts for the gate (as ``recorded_check`` for sessions).

    It counts only if :data:`PR_METHOD` made it, its status is ``passed`` and its inputs (:data:`PR_COMPARED`) equal the
    current files. Nothing is re-run here; :func:`pr_recheck` re-runs the check against the bare clone and rewrites only the
    record (a rebuild with ``tracecontract compile-pr-task`` is refused once the task holds generated material).
    """
    task_dir = Path(task_dir)
    path, hint = task_dir / RECORD, f"re-check {task_dir.name} with natural_pr.pr_recheck, which rewrites only {RECORD}"
    if not path.is_file():
        return RecordCheck(None, [f"no {RECORD}: the base has not been checked against the PR's commits ({hint})"])
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
        now = pr_current_inputs(task_dir)
        recorded = rec.get("inputs") if isinstance(rec.get("inputs"), dict) else {}
    except Exception as exc:  # noqa: BLE001 - an unreadable record or task counts as no record
        return RecordCheck(None, [f"{RECORD} or the task's records are unreadable ({type(exc).__name__}); {hint}"])
    status, problems = rec.get("status"), []
    if rec.get("method") != PR_METHOD:
        problems.append(f"{RECORD} was made by {rec.get('method')!r}, not by {PR_METHOD} ({hint})")
    stale = (["task_id"] if rec.get("task_id") != now["task_id"] else []) + [k for k in PR_COMPARED if recorded.get(k) != now.get(k)]
    if stale:
        problems.append(f"{RECORD} was made from other files than the current ones ({', '.join(stale)} differ; {hint})")
    current = not problems
    if status != "passed" or rec.get("passed") is not True:
        bad = [f"{c.get('check_id')}: {c.get('status')}" for c in rec.get("checks", []) if isinstance(c, dict) and c.get("status") != "passed"]
        what = ("failed: the base or a candidate is not the PR's state" if status == "failed" else f"is {status!r}, not 'passed'")
        problems.append(f"the recorded check {what}" + (f" ({'; '.join(bad)})" if bad else ""))
    return RecordCheck(status if isinstance(status, str) else None, problems, failed=current and status == "failed")


# --------------------------------------------------------------------------- compiling one family


def _ids(fam: Family) -> dict[str, Any]:
    return {"task_id": fam.task_id, "role": fam.role, "pr_id": fam.pr_id, "repo_id": fam.repo_id, "comment_id": fam.comment_id}


def _data_errors() -> tuple[type[BaseException], ...]:
    errs: list[type[BaseException]] = [Reject, CapExceeded, GitError, SourceProblem, subprocess.TimeoutExpired, OSError, ValueError,
                                       KeyError, tarfile.TarError]
    try:
        import duckdb

        errs.append(duckdb.Error)
    except ImportError:  # pragma: no cover - DuckDB is in the data extra
        pass
    return tuple(errs)


def _as_rejection(exc: BaseException) -> tuple[str, str, dict[str, Any]]:
    if isinstance(exc, Reject):
        return exc.stage, exc.reason, exc.details
    if isinstance(exc, CapExceeded):
        return STAGE, f"fetch over the caps (§15.6): {exc}", {}
    if isinstance(exc, GitError):
        return STAGE, f"a git command failed: {exc}", {}
    if isinstance(exc, SourceProblem):
        return STAGE, f"source data: {exc}", {}
    return STAGE, f"data problem: {type(exc).__name__}", {}


def _closure(clone: BareClone, st: GitStates, subdir: str) -> dict[str, Any]:
    """The planned closure: the declarations at the base, and at the reviewed and addressing commits for PR-added packages."""
    def declared(commit: str) -> dict[str, Any]:
        names = [p for _, t, _, p in clone.ls_tree(commit, [subdir] if subdir else []) if t == "blob"]
        rel = {_rel(p, subdir): p for p in names}
        want = env.declaration_files([r for r in rel if r is not None])
        got = clone.read_many(commit, [rel[w] for w in want], label=f"declarations {commit[:12]}")
        texts = {w: got[rel[w]].decode("utf-8", "replace") for w in want if rel[w] in got}
        return env.declared_dependencies(texts)

    base_decl = declared(st.base)
    later = [declared(st.reviewed), declared(st.addressing)]
    changed_py = sorted({p for _, p in st.changed + st.changed_reviewed if p.endswith(".py") and _rel(p, subdir) is not None})
    code: dict[str, str] = {}
    for commit in (st.reviewed, st.addressing):
        for p, b in clone.read_many(commit, changed_py, label=f"changed code {commit[:12]}").items():
            code[f"{commit[:12]}:{p}"] = b.decode("utf-8", "replace")
    path_names = {}
    for pr in base_decl["path_requirements"]:
        target = os.path.normpath(str(PurePosixPath(subdir or ".", PurePosixPath(pr["from"]).parent, pr["path"])))
        if target.startswith("..") or os.path.isabs(target):
            path_names[pr["path"]] = None  # outside the repository
            continue
        prefix = "" if target == "." else target + "/"
        files = clone.read_many(st.base, [f"{prefix}{n}" for n in PACKAGE_FILES], label="path requirement")
        decl = env.declared_dependencies({k.rsplit("/", 1)[-1]: v.decode("utf-8", "replace") for k, v in files.items()})
        path_names[pr["path"]] = decl.get("project")
    return env.plan_closure(declared_base=base_decl, declared_later=later, changed_code=code, base_date=st.base_date,
                            path_names=path_names)


def _test_preview(clone: BareClone, st: GitStates, subdir: str, commented: str) -> dict[str, Any]:
    """What plan-only can say about the base-test subset without reading test files (the import analysis runs at build)."""
    names = [r for r in (_rel(p, subdir) for _, t, _, p in clone.ls_tree(st.base, [subdir] if subdir else []) if t == "blob") if r]
    tests = [n for n in names if env.is_test_file(n)]
    changed = [r for r in (_rel(p, subdir) for s, p in st.changed if s[:1] in "MDT") if r and env.is_test_file(r)]
    return {"test_files_at_base": len(tests), "changed_test_files_at_base": len(changed),
            "test_directory": next((d for d in ("tests", "test", "testing") if any(t.startswith(d + "/") for t in tests)), None),
            "note": "the subset (test files importing a changed module, and changed test files) is fixed when the task is built"}


def _session(fam: Family, aidev: AIDev, clone: BareClone, st: GitStates, url: str, acts: bool):
    thread = collect_thread(aidev, clone, pr_id=fam.pr_id, comment_id=fam.comment_id, issue_id=fam.issue_id, base=st.base,
                            reviewed=st.reviewed, addressing=st.addressing, other_qualifying=fam.other_qualifying_comment_ids)
    ps, _ = make_pseudonymizer(thread, aidev.persons())
    session = build_session(thread, ps, repo_url=url, owner_masked=acts)
    left = leftover_identifiers(session, ps)
    if left:
        raise Reject("pseudonymisation incomplete: " + "; ".join(left[:5]))
    return session


def _session_summary(session) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    for e in session.events:
        kinds[e.kind.value] = kinds.get(e.kind.value, 0) + 1
    md = session.metadata
    return {"session_id": session.session_id, "events": len(session.events), "by_kind": kinds,
            "replies": len(md["events"]["replies"]), "replies_excluded": md["replies_excluded"],
            "replacements": md["pseudonymisation"]["replacements"], "trace_sha256": session.trace_sha256,
            "sanitize_natural": sanitizer_counts(session)}


_PARTS = {"issue": "issue", "pr": "pr_body", "commit": "commits", "reply": "replies"}  # event id suffixes (ingest.github_pr)


def _event_part(event_id: str, kind: str) -> str:
    """The part of a PR thread an event is: issue, pr_body, commits, hunk, review_comment or replies (else its kind;
    :func:`sanitizer_counts` adds metadata and repo_url)."""
    suffix = event_id.split("/", 1)[1] if "/" in event_id else ""
    head = suffix.split("/", 1)[0]
    if head == "review":
        return "hunk" if suffix.endswith("/hunk") else "review_comment"
    return _PARTS.get(head, kind)


def sanitizer_counts(session: Session) -> dict[str, Any]:
    """What sanitize-natural:v1 (D47; §15.6: the issue and the correction are sanitised) replaces in the stored session.

    Two counts, kept apart:

    * ``pass``: the counts of the v1 pass itself, ``sanitize_session``, as an agent's sanitised copy of the session gets
      them. The pass renders a tool call's text from its tool input, so a commit event's message (its text) is dropped
      there, not counted;
    * ``counts`` and ``where``: the v1 rules applied to every stored string, by kind and by part of the thread: each
      event's text (a commit's message included) and tool input, the metadata and the repository URL. So a replacement
      the pass never makes, because the pass drops the string, is counted here.

    Only counts are kept; the session file is never rewritten, so the reconstruction record's session hash stays valid. A
    handle counted can be one of the pseudonymiser's own role labels.
    """
    total: Counter = Counter()
    where: dict[str, Counter] = {}

    def count(part: str, value: Any) -> None:
        c: Counter = Counter()
        sanitize_obj(value, c)
        if c:
            where.setdefault(part, Counter()).update(c)
            total.update(c)

    for e in session.events:
        part = _event_part(e.event_id, e.kind.value)
        count(part, e.text)
        if e.tool_input is not None:
            count(part, e.tool_input)
    count("metadata", session.metadata)
    if session.repo_url:
        count("repo_url", session.repo_url)
    return {"sanitizer": SANITIZER_VERSION, "pass": sanitize_session(session)[1], "counts": dict(sorted(total.items())),
            "where": {p: dict(sorted(c.items())) for p, c in sorted(where.items())}}


def compile_pr_task(family: Family, out_root: str | Path, *, plan_only: bool = False, aidev: AIDev | None = None,
                    aidev_data: str | Path = AIDEV_DATA, snapshot_root: str | Path | None = None,
                    fetch_log: str | Path | None = None, clone: BareClone | None = None) -> dict[str, Any]:
    """Build ``<out_root>/<task id>/`` for one family (see the module docstring), or with ``plan_only`` only plan it.

    Returns a JSON-able result with ``outcome`` ``planned``, ``built``, ``rejected`` (with ``stage`` and ``reason``) or
    ``refused``. It holds ids, SHAs, licence identifiers, counts and requirement specifiers; no text from the thread. A data
    problem becomes a rejection; only a programming error raises.

    A build is ``refused`` when the task directory holds more than S10's own material (:func:`generated_material`:
    contracts, labels, a frozen B1, verifiers other than B1, candidates beyond the four S10 ones, any file S10 does not
    write): nothing is fetched, written or deleted, neither the task directory nor its snapshot. The check is made again
    just before the directory would be replaced or rejected. A refusal is not a rejection; :func:`pr_recheck` re-checks
    the PR record of such a task.
    """
    out_root = Path(out_root)
    snapshot_root = Path(snapshot_root) if snapshot_root else out_root.parent / "snapshots"
    fetch_log = Path(fetch_log) if fetch_log else out_root.parent / "s10_fetch_log.jsonl"
    res: dict[str, Any] = {**_ids(family), "compiler": COMPILER, "plan_only": plan_only, "started_at": _now()}
    st: GitStates | None = None
    task_dir = out_root / family.task_id

    def refused(exc: Refused, fetches: list[dict[str, Any]]) -> dict[str, Any]:
        res.update({"outcome": "refused", "reason": exc.reason, "generated": exc.found, "fetches": fetches})
        return res

    found = [] if plan_only else generated_material(task_dir)
    if found:  # before anything is read, fetched, built or removed (neither the dataset nor the clone is opened)
        return refused(Refused(task_dir, found, step="compile-pr-task"), [])
    aidev = aidev or AIDev(aidev_data)  # a missing dataset is a setup error, raised: it is no family's rejection
    try:
        clone = clone or BareClone(family.bare_clone, repo_id=family.repo_id, fetch_log=fetch_log)
        pr_commits = [r["sha"] for r in aidev.pr_commits(family.pr_id)]
        st = resolve_states(family, clone, pr_commits)
        url, acts = masked_url(family, aidev.persons())
        subdir = snapshot_scope(clone, st, family.path)
        res.update({"base": {"commit": st.base, "rule": st.base_rule, "committed_at": st.base_date, "first_commit": st.first,
                             "default_branch_tip": st.default_tip},
                    "reviewed_commit": st.reviewed, "addressing_commit": st.addressing, "head_commit": st.head,
                    "fidelity": st.fidelity.value, "approximations": list(st.approximations), "merge_state": st.merge_state,
                    "merges": len(st.merges), "notes": list(st.notes),
                    "changes": {"files_base_to_addressing": len(st.changed), "files_base_to_reviewed": len(st.changed_reviewed)},
                    "scope": {"subdir": subdir, "monorepo_package": bool(subdir)}})
        lic = licence_check(clone, st.base, subdir, family.licence_aidev)
        res["licence"] = {k: lic[k] for k in ("spdx", "aidev", "agrees", "permissive")}
        res["closure"] = _closure(clone, st, subdir)
        if plan_only:
            res["tests"] = _test_preview(clone, st, subdir, family.path)
            res["session"] = _session_summary(_session(family, aidev, clone, st, url, acts))
            res.update({"outcome": "planned", "fetches": clone.fetches})
            return res
        built = _build(family, out_root, snapshot_root, clone, aidev, st, subdir, url, acts, lic, res["closure"])
        res.update(built)
        res.update({"outcome": "built", "fetches": clone.fetches})
        return res
    except Refused as exc:  # _build found generated material just before replacing the task directory
        return refused(exc, clone.fetches if clone else [])
    except _data_errors() as exc:
        stage, reason, details = _as_rejection(exc)
        res.update({"outcome": "rejected", "stage": stage, "reason": reason, "details": _safe(details),
                    "fetches": clone.fetches if clone else []})
        if st is not None:
            res.setdefault("base", {"commit": st.base, "rule": st.base_rule})
        if not plan_only:
            for partial in (out_root / f".{family.task_id}.partial", snapshot_root / f".{family.task_id}.partial"):
                shutil.rmtree(partial, ignore_errors=True)  # the compiler's own staging
            try:
                found = generated_material(task_dir)
                if found:  # the rejection would delete generated material: refused, the task and its snapshot are kept
                    raise Refused(task_dir, found, step="compile-pr-task")
                shutil.rmtree(snapshot_root / family.task_id, ignore_errors=True)  # a rejected task keeps no snapshot
                write_rejection(task_dir, family, stage, reason, _safe(details))
            except Refused as ref:
                for k in ("stage", "details"):
                    res.pop(k, None)
                refused(ref, clone.fetches if clone else [])["rejection_found"] = {"stage": stage, "reason": reason}
        return res


def _safe(details: dict[str, Any]) -> dict[str, Any]:
    """Only ids, SHAs, counts and categorical values of a rejection's details (the licence record has no text)."""
    keep = {}
    for k, v in details.items():
        if k in ("base_commit", "merges", "merges_touching", "licence", "wheel_less", "pins", "counts", "wheelhouse_bytes",
                 "pytest_exit_code", "timed_out"):
            keep[k] = v
    return keep


def write_rejection(task_dir: Path, fam: Family, stage: str, reason: str, details: dict[str, Any] | None = None) -> Path:
    """Replace ``task_dir`` with a directory holding only the family's rejection record.

    Raises :class:`Refused`, and changes nothing, when ``task_dir`` holds material made after S10 (:func:`generated_material`).
    """
    found = generated_material(task_dir)
    if found:
        raise Refused(task_dir, found, step="write_rejection")
    staging = task_dir.parent / f".{task_dir.name}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    write_json({"schema": "tracecontract/natural-rejection/v1", "compiler": COMPILER, **_ids(fam), "stage": stage, "reason": reason,
                "details": details or {}, "at": _now()}, staging / REJECTION)
    if task_dir.exists():
        shutil.rmtree(task_dir)
    staging.rename(task_dir)
    return task_dir / REJECTION


def _approximations(st: GitStates, subdir: str, snap: dict[str, Any], ref_drop: list[dict[str, str]],
                    pre_drop: list[dict[str, str]]) -> list[str]:
    """The task's approximations: the git states', then the workspace's, the snapshot's and the candidates' (in that order)."""
    out = list(st.approximations)
    if subdir:
        out.append("the workspace is the package directory of a monorepo, not the whole repository")
    if snap["symlinks"] or snap["gitlinks"]:
        out.append(f"{snap['symlinks']} symbolic link(s) and {snap['gitlinks']} submodule(s) of the base tree are not materialised")
    for what, dropped in (("reference", ref_drop), ("pre-review", pre_drop)):
        if dropped:
            out.append(f"the {what} patch leaves out {len(dropped)} file change(s) the grader cannot apply "
                       f"({', '.join(sorted({d['why'] for d in dropped}))})")
    outside = {p for _, p in st.changed + st.changed_reviewed if _rel(p, subdir) is None}
    if outside:
        out.append(f"{len(outside)} changed file(s) outside the workspace are left out of the candidates")
    return out


def _build(fam: Family, out_root: Path, snapshot_root: Path, clone: BareClone, aidev: AIDev, st: GitStates, subdir: str, url: str,
           acts: bool, lic: dict[str, Any], closure: dict[str, Any]) -> dict[str, Any]:
    tid = fam.task_id
    session = _session(fam, aidev, clone, st, url, acts)
    snap_dir = snapshot_root / tid
    snap_stage = snapshot_root / f".{tid}.partial"
    snap = materialize_base(clone, st.base, subdir, snap_stage)
    ref_patch, ref_raw, ref_drop = candidate_patch(clone, st.base, st.addressing, subdir)
    pre_patch, pre_raw, pre_drop = candidate_patch(clone, st.base, st.reviewed, subdir)
    if not ref_patch.strip():
        raise Reject("the reference patch is empty in the workspace")
    approximations = _approximations(st, subdir, snap, ref_drop, pre_drop)
    commented_rel = _rel(fam.path, subdir)
    if commented_rel is None or commented_rel in {d["path"] for d in ref_drop + pre_drop}:
        raise Reject("the commented file is not part of the gradable workspace")
    ref_v = verify_candidate(snap_stage, ref_patch, ref_raw, subdir, ref_drop)
    pre_v = verify_candidate(snap_stage, pre_patch, pre_raw, subdir, pre_drop)
    changed_rel = [(s, r) for s, r in ((s, _rel(p, subdir)) for s, p in st.changed) if r is not None]
    tests = env.select_base_tests(snap_stage, changed=changed_rel, commented_path=commented_rel)
    if tests["empty"]:
        raise Reject("base tests: the base-test subset is empty (no test file imports a changed module, the PR changes no "
                     "test file present at the base, and the changed package has no test directory) (§17.2)")
    pythonpath = env.candidate_pythonpath(snap_stage)
    now = _now()
    # Candidates.
    cands = [
        Candidate(candidate_id=f"{tid}-reference", task_id=tid, origin=CandidateOrigin.reference, split=Split.dev, patch=ref_patch,
                  patch_sha256=sha256_text(ref_patch), produced_by=f"git:{st.addressing}",
                  description="The tree at the addressing commit (the PR's first later commit that changes the commented file), "
                              "against the base" + (f"; {len(ref_drop)} ungradable file change(s) left out" if ref_drop else "")),
        Candidate(candidate_id=f"{tid}-pre-review", task_id=tid, origin=CandidateOrigin.natural_pre_review, split=Split.eval,
                  patch=pre_patch, patch_sha256=sha256_text(pre_patch), produced_by=f"git:{st.reviewed}",
                  description="The tree the reviewer commented on (original_commit_id), against the base",
                  labels=[Label(value="invalid", labeler="source-evidence:aidev-s9", labeler_kind=LabelerKind.source_evidence,
                                timestamp=now, note="the reviewer's request (the correction event), the addressing commit and the "
                                "agreement of both S9 judges; requirement ids follow from the reference contract (§15.6)")]),
    ]
    for split in (Split.dev, Split.eval):
        cands.append(Candidate(candidate_id=f"{tid}-noop-{split.value}", task_id=tid, origin=CandidateOrigin.noop, split=split,
                               patch="", patch_sha256=sha256_text(""), produced_by="base snapshot",
                               description="No-op: the unchanged base snapshot.",
                               labels=[Label(value="invalid", labeler="construction", labeler_kind=LabelerKind.construction,
                                             timestamp=now, note="no change made")]))
    staging = out_root / f".{tid}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "candidates").mkdir(parents=True)
    for c in cands:
        dump(c, staging / "candidates" / f"{c.candidate_id}.json")
    dump(session, staging / PR_SESSION_FILE)
    fidelity = Fidelity.approximate if approximations else Fidelity.exact
    dump(Snapshot(snapshot_id=f"{tid}@{st.base[:12]}", task_id=tid, repo_url=url, base_commit=st.base, fidelity=fidelity,
                  approximations=approximations, file_manifest_sha256=snap["manifest_sha256"], n_files=snap["n_files"]),
         staging / "snapshot.json")
    j = [x for x in fam.judges if x]
    rank = {"low": 0, "medium": 1, "high": 2}
    conf = min((x.get("confidence") for x in j if x.get("confidence") in rank), key=rank.get, default="low")
    triage = TriageProposal(category=TriageCategory.candidate, method="aidev-s9:two-judges", confidence=conf,
                            reasons=[f"S9: both judges: {', '.join(sorted({str(x.get('request_type')) for x in j}))}; addressed yes; "
                                     "testable offline yes (model proposals, queued for human coding)"],
                            correction_event_ids=[session.metadata["events"]["correction"]])
    prov_pr = PRProvenance(
        dataset=AIDEV_DATASET, revision=AIDEV_REVISION, pr_id=fam.pr_id, pr_number=fam.pr_number, repo_id=fam.repo_id,
        agent=fam.agent, comment_id=fam.comment_id, other_qualifying_comment_ids=list(fam.other_qualifying_comment_ids),
        reply_comment_ids=session.metadata["aidev"]["reply_comment_ids"], issue_id=fam.issue_id, issue_number=fam.issue_number,
        base_commit=st.base, base_rule=st.base_rule, first_commit=st.first, reviewed_commit=st.reviewed,
        addressing_commit=st.addressing, head_commit=st.head, default_branch_tip=st.default_tip, merge_state=st.merge_state,
        merges=st.merges, merges_touching_the_commented_file=st.touching, fidelity=st.fidelity, approximations=approximations,
        licence_file_spdx=lic["spdx"], licence_file_sha256=lic["sha256"], licence_aidev=lic["aidev"], licence_agrees=lic["agrees"],
        snapshot_subdir=subdir, owner_masked=acts)
    prov = ProvenanceRecord(
        record_id=f"prov-{tid}", session_id=session.session_id, population=Population.natural_pr_review,
        source_url=f"https://huggingface.co/datasets/{AIDEV_DATASET}", source_id=f"aidev:pr:{fam.pr_id}/comment:{fam.comment_id}",
        source_revision=AIDEV_REVISION, repo_url=url, base_commit=st.base,
        licenses={"code": lic["spdx"], "code_aidev": str(lic["aidev"]), "dataset": "CC-BY-4.0"},
        permission_basis=(f"Public GitHub repository whose LICENSE file at the base is {lic['spdx']} (a permissive licence of S2; "
                          f"AIDev's field {'agrees' if lic['agrees'] else 'differs'}); AIDev v5 is a CC-BY-4.0 compilation in which "
                          "each repository keeps its own licence (D47). The pseudonymised thread stays outside git (§17.4); "
                          "publishing texts derived from it is the owner's decision."),
        trace_sha256=session.trace_sha256, snapshot_manifest_sha256=snap["manifest_sha256"],
        capture_method=("AIDev v5 rows (pull_request, pr_review_comments, pr_commits, issue) read with DuckDB; commits, trees and "
                        "blobs from the repository's bare partial clone with git plumbing (blobs fetched by id within the caps); "
                        "texts pseudonymised by ingest/pseudonymize_pr.py"),
        redaction_status=RedactionStatus.redacted_by_us, task_family_id=tid, eligibility=Eligibility.pending_review,
        triage=triage, accessed=now, natural_pr=prov_pr,
        notes=json.dumps({"compiler": COMPILER, "repo_url_masked": acts, "snapshot_root": "data/natural/snapshots"}))
    dump(prov, staging / "provenance.json")
    m = TaskManifest(task_id=tid, family_id=tid, population=Population.natural_pr_review, status="pending_review",
                     provenance="provenance.json", snapshot_source=SnapshotSource(repo_url=url, commit=st.base, subdir=subdir),
                     snapshot="snapshot.json", env_requirements=[], candidate_pythonpath=pythonpath,
                     repo_test_args=env.repo_test_args(tests["subset"]), candidates=[f"candidates/{c.candidate_id}.json" for c in cands],
                     notes="natural PR-review task (§15.6, §17); the pinned closure, the base-test run and B1 come from the S10 "
                           "environment step")
    dump(m, staging / "task.json")
    inputs = {"task_id": tid, "session_sha256": sha256_bytes((staging / PR_SESSION_FILE).read_bytes()),
              "base_manifest_sha256": snap["manifest_sha256"], "reference_candidate": cands[0].candidate_id,
              "reference_patch_sha256": cands[0].patch_sha256, "pre_review_candidate": cands[1].candidate_id,
              "pre_review_patch_sha256": cands[1].patch_sha256, "base_commit": st.base, "reviewed_commit": st.reviewed,
              "addressing_commit": st.addressing}
    rec = pr_reconstruction(tid, st, snap, ref_v, pre_v, inputs, approximations)
    write_json(rec, staging / RECORD)
    if rec["status"] != "passed":
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(snap_stage, ignore_errors=True)
        raise Reject("the reconstruction check failed: " + "; ".join(f"{c['check_id']}: {c['reason']}" for c in rec["checks"]
                                                                       if c["status"] != "passed"))
    s10 = {"schema": "tracecontract/natural-s10/v1", "task_id": tid, "stage": STAGE, "compiler": COMPILER, "built_at": now,
           "outcome": "built", "next": "the S10 environment step (natural_env): resolve and pin the closure, build the image, run "
                                       "the base tests, select B1",
           "closure_plan": closure,
           "base_tests": {**{k: tests[k] for k in ("subset", "rule", "changed_test_files", "n_test_files_at_base", "import_roots")},
                          "n_by_import": len(tests["by_import"]),
                          "planned_run": env.run_base_tests(snap_stage, None, args=env.repo_test_args(tests["subset"]),
                                                            pythonpath=pythonpath, dry_run=True)},
           "environment": None, "base_test_run": None, "b1": None}
    write_json(s10, staging / S10_RECORD)
    # Publish the snapshot and the task directory (each replaced whole), unless the task directory now holds material
    # made after S10: then only the compiler's own staging is removed (compile_pr_task reports the refusal).
    task_dir = out_root / tid
    found = generated_material(task_dir)
    if found:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(snap_stage, ignore_errors=True)
        raise Refused(task_dir, found, step="compile-pr-task")
    if snap_dir.exists():
        shutil.rmtree(snap_dir)
    snap_stage.rename(snap_dir)
    if task_dir.exists():
        shutil.rmtree(task_dir)
    staging.rename(task_dir)
    files = {p.relative_to(task_dir).as_posix(): sha256_bytes(p.read_bytes()) for p in sorted(task_dir.rglob("*")) if p.is_file()}
    return {"task_dir": str(task_dir), "snapshot_dir": str(snap_dir), "fidelity": fidelity.value, "approximations": approximations,
            "reconstruction": rec["status"], "base_tests": {"subset": len(tests["subset"]), "rule": tests["rule"]},
            "candidates": {c.candidate_id: c.patch_sha256 for c in cands}, "session": _session_summary(session),
            "snapshot": {k: snap[k] for k in ("n_files", "manifest_sha256", "blobs_fetched", "symlinks", "gitlinks")}, "files": files}


# --------------------------------------------------------------------------- re-checking a built task


def _failed_record(task_id: str, failing: str, reason: str, inputs: dict[str, Any], snap_rec: Snapshot,
                   notes: list[str] | None = None) -> dict[str, Any]:
    """A PR reconstruction record whose check ``failing`` fails: the checks before it passed (the git rules run in the order
    a, b, c), the later ones did not run."""
    order = list(CHECK_TITLES)
    at = order.index(failing if failing in CHECK_TITLES else order[0])
    checks = []
    for i, cid in enumerate(order):
        if i < at:
            checks.append(_check(cid, "passed", f"passed before {order[at]} failed"))
        elif i == at:
            checks.append(_check(cid, "failed", reason))
        else:
            checks.append(_check(cid, "not_checked", f"not checked: {order[at]} failed"))
    return {"task_id": task_id, "method": PR_METHOD, "status": "failed", "passed": False, "fidelity": snap_rec.fidelity.value,
            "approximations": list(snap_rec.approximations), "checks": checks, "inputs": inputs, "notes": list(notes or []),
            "files": []}


def _recheck_record(task_dir: Path, m: TaskManifest, snap_rec: Snapshot, st: GitStates, clone: BareClone, snap_dir: Path,
                    subdir: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """The record of :func:`pr_reconstruction` for the task's current snapshot directory and stored candidate patches."""
    snap = compare_base(clone, st.base, subdir, snap_dir)
    cands: dict[CandidateOrigin, Candidate] = {}
    for p in m.candidates:
        try:
            c: Candidate | None = load(task_dir / p, Candidate)
        except Exception:  # noqa: BLE001 - as in pr_current_inputs: a candidate that does not load is not used
            c = None
        if c is not None:
            cands.setdefault(c.origin, c)  # the first of each origin, as pr_current_inputs takes it
    verdicts: dict[str, dict[str, Any]] = {}
    drops: dict[str, list[dict[str, str]]] = {}
    for what, origin, commit in (("reference", CandidateOrigin.reference, st.addressing),
                                 ("pre-review", CandidateOrigin.natural_pre_review, st.reviewed)):
        patch, raw, drops[what] = candidate_patch(clone, st.base, commit, subdir)
        cand = cands.get(origin)
        if cand is None:
            verdicts[what] = {"status": "failed", "reason": f"the task has no {what} candidate"}
            continue
        verdicts[what] = {**verify_candidate(snap_dir, cand.patch, raw, subdir, drops[what]),
                          "equals_recompiled_patch": sha256_text(cand.patch) == sha256_text(patch)}
    approximations = _approximations(st, subdir, snap, drops["reference"], drops["pre-review"])
    return pr_reconstruction(m.task_id, st, snap, verdicts["reference"], verdicts["pre-review"], inputs, approximations,
                             recorded_manifest=snap_rec.file_manifest_sha256)


def pr_recheck(task_dir: str | Path, family: Family | None = None, *, qualifying: str | Path = QUALIFYING,
               aidev: AIDev | None = None, aidev_data: str | Path = AIDEV_DATA, snapshot_root: str | Path | None = None,
               fetch_log: str | Path | None = None, clone: BareClone | None = None) -> dict[str, Any]:
    """Re-run the PR reconstruction check of a built task against its bare clone; rewrite only ``reconstruction_check.json``.

    Non-destructive: no other file of the task and nothing of its base snapshot is written (git may fetch blobs a diff needs
    into the clone, within the caps, as at build). The checks of :func:`pr_reconstruction` run on the current files:

    * the git rules of §15.6 are applied again to the family's commits, and must give the task's base, reviewed and
      addressing commits;
    * the snapshot directory is compared with the base tree file by file (it is not rebuilt), and its manifest with the one
      snapshot.json records;
    * the stored reference and pre-review patches, applied to a copy of the snapshot, must reproduce their commits' whole
      trees (:func:`verify_candidate`: every file the commit changes is the commit's, and no other file differs from the
      base); each verdict also says whether the stored patch equals the one the compiler makes now, which a stored patch
      need not, since the tree is what is checked.

    A rule that now fails gives a failed record, which the gate refuses, never an exception. The session is not one of the
    checks, but the record's inputs bind it: before a record is written from the current states, the session is rebuilt
    from the thread in memory (as the build made it), and a ``session.json`` that differs from it by a byte is not
    certified: nothing is written (``not rechecked``, with both sha256), so a record made stale by a changed session stays
    stale. The record's inputs are the current files; its ``recheck`` entry holds the previous record's sha256 and status,
    the inputs that changed since, whether the session was rebuilt byte for byte and whether the recomputed approximations
    are snapshot.json's (both None when a git rule failed and nothing beyond it was recomputed).

    ``family`` defaults to the task's family in ``qualifying`` (by its PR id), ``snapshot_root`` to
    :func:`roots.snapshot_root`. Returns ``outcome`` ``rechecked`` (with the record's status), or ``not rechecked`` with a
    reason, writing nothing, when the task, its family, its snapshot or its clone cannot be read, or its session is not the
    one the compiler builds.
    """
    task_dir = Path(task_dir)
    out: dict[str, Any] = {"task_id": task_dir.name, "method": PR_METHOD, "started_at": _now()}

    def skip(reason: str) -> dict[str, Any]:
        out.update({"outcome": "not rechecked", "reason": reason, "fetches": clone.fetches if clone else []})
        return out

    try:
        m = load(task_dir / "task.json", TaskManifest)
        prov = load(task_dir / m.provenance, ProvenanceRecord)
        snap_rec = load(task_dir / (m.snapshot or "snapshot.json"), Snapshot)
        before = pr_current_inputs(task_dir)
    except Exception as exc:  # noqa: BLE001 - an unreadable task is not re-checked
        return skip(f"the task's records are unreadable ({type(exc).__name__})")
    pr = prov.natural_pr
    if m.population != Population.natural_pr_review or pr is None:
        return skip("not a natural PR-review task")
    try:
        fam = family or find_family(load_families(qualifying), pr.pr_id)
    except (KeyError, OSError, ValueError) as exc:
        return skip(f"the task's family is not among the S9 survivors ({type(exc).__name__})")
    if (fam.task_id, fam.pr_id, fam.repo_id, fam.comment_id) != (m.task_id, pr.pr_id, pr.repo_id, pr.comment_id):
        return skip("the family is not this task's: its task id, PR, repository or comment differs")
    try:
        snap_dir = Path(snapshot_root) / m.task_id if snapshot_root else roots.snapshot_dir(task_dir)
    except roots.RootError as exc:
        return skip(str(exc))
    if not snap_dir.is_dir():
        return skip("the task's base snapshot directory is missing")
    aidev = aidev or AIDev(aidev_data)  # a missing dataset is a setup error, raised: it says nothing about the task
    recomputed = False  # whether the checks beyond the git rules ran (else the record is _failed_record's)
    try:
        clone = clone or BareClone(fam.bare_clone, repo_id=fam.repo_id,
                                   fetch_log=Path(fetch_log) if fetch_log else task_dir.parent.parent / "s10_fetch_log.jsonl")
        pr_commits = [r["sha"] for r in aidev.pr_commits(fam.pr_id)]
        try:
            st = resolve_states(fam, clone, pr_commits)
        except Reject as exc:  # a git rule fails now
            rec = _failed_record(m.task_id, str(exc.details.get("check") or ""), exc.reason, before, snap_rec)
        else:
            moved = [w for w, now, was in (("base", st.base, pr.base_commit), ("reviewed", st.reviewed, pr.reviewed_commit),
                                           ("addressing", st.addressing, pr.addressing_commit)) if now != was]
            if moved:
                rec = _failed_record(m.task_id, "b_base_rule" if moved == ["base"] else "a_commits_reachable",
                                     f"the PR's commits now give another {' and '.join(moved)} commit than the task records",
                                     before, snap_rec, st.notes)
            else:
                url, acts = masked_url(fam, aidev.persons())
                made = _dumped(_session(fam, aidev, clone, st, url, acts))
                sess = task_dir / PR_SESSION_FILE
                have = sess.read_bytes() if sess.is_file() else None
                if have != made:
                    out["session"] = {"file_sha256": sha256_bytes(have) if have is not None else None,
                                      "rebuilt_sha256": sha256_bytes(made)}
                    return skip(f"{PR_SESSION_FILE} is not the session the compiler builds from the thread now (its sha256 "
                                "differs from the rebuilt one): a re-check does not certify it, and the record is left as it "
                                "is")
                rec = _recheck_record(task_dir, m, snap_rec, st, clone, snap_dir, pr.snapshot_subdir, before)
                recomputed = True
    except _data_errors() as exc:
        return skip(_as_rejection(exc)[1])
    try:
        after = pr_current_inputs(task_dir)
    except Exception as exc:  # noqa: BLE001
        return skip(f"the task's records became unreadable during the re-check ({type(exc).__name__})")
    if after != before:
        return skip("the task's files changed during the re-check")
    path = task_dir / RECORD
    prev_bytes = path.read_bytes() if path.is_file() else None
    loaded = _json_or_none(path) if prev_bytes is not None else None
    prev: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
    was = prev.get("inputs")
    prev_inputs: dict[str, Any] = was if isinstance(was, dict) else {}
    rec["recheck"] = {"by": "natural_pr.pr_recheck", "at": _now(),
                      "previous_sha256": sha256_bytes(prev_bytes) if prev_bytes is not None else None,
                      "previous_status": prev.get("status"),
                      "inputs_changed": [k for k in ("task_id", *PR_COMPARED) if prev_inputs.get(k) != before.get(k)],
                      "session_rebuilt": True if recomputed else None,
                      "approximations_as_recorded": rec["approximations"] == list(snap_rec.approximations) if recomputed else None}
    tmp = task_dir.parent / f".{task_dir.name}.{RECORD}.partial"  # outside the task directory; replaced in one step
    write_json(rec, tmp)
    os.replace(tmp, path)
    out.update({"outcome": "rechecked", "status": rec["status"], "previous_status": prev.get("status"), "record": str(path),
                "checks": {c["check_id"]: c["status"] for c in rec["checks"]}, "inputs_changed": rec["recheck"]["inputs_changed"],
                "fetches": clone.fetches})
    return out


# --------------------------------------------------------------------------- later S10 failures and the index


def reject_task(task_dir: Path, reason: str, *, stage: str = STAGE, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record an S10 failure found after the build (environment too large, no resolvable closure, base tests that fail to
    collect): the task's status and eligibility become ``rejected``, and the S10 record says why."""
    m = load(task_dir / "task.json", TaskManifest)
    prov = load(task_dir / m.provenance, ProvenanceRecord)
    dump(prov.model_copy(update={"eligibility": Eligibility.rejected, "rejection_reasons": [*prov.rejection_reasons, f"{stage}: {reason}"]}),
         task_dir / m.provenance)
    dump(m.model_copy(update={"status": "rejected"}), task_dir / "task.json")
    s10_path = task_dir / S10_RECORD
    s10 = json.loads(s10_path.read_text(encoding="utf-8")) if s10_path.is_file() else {"task_id": m.task_id, "stage": stage}
    s10.update({"outcome": "rejected", "stage": stage, "reason": reason, "rejected_at": _now(), "rejection_details": details or {}})
    write_json(s10, s10_path)
    pr = prov.natural_pr
    write_json({"schema": "tracecontract/natural-rejection/v1", "compiler": COMPILER, "task_id": m.task_id,
                "pr_id": pr.pr_id if pr else None, "repo_id": pr.repo_id if pr else None, "comment_id": pr.comment_id if pr else None,
                "stage": stage, "reason": reason, "details": details or {}, "at": _now(), "after_build": True}, task_dir / REJECTION)
    return s10


def run_s10_environment(task_dir: str | Path, snapshot_root: str | Path, workdir: str | Path, cache_dir: str | Path, *,
                        dry_run: bool = True, run: Any = subprocess.run, fetch_json: Any = None, download: Any = None,
                        runner: Any = None, build: Any = None) -> dict[str, Any]:
    """The S10 step that needs the network and Docker, for one built task (§17): resolve and pin the closure (wheels only,
    pure-Python sdists built in the sandbox), build the image, run the base-test subset at the base offline within 10
    minutes, and select B1 at the addressing commit. Each result goes into ``s10.json``; a failure rejects the task with
    its reason (:func:`reject_task`). ``dry_run`` (the default) returns the planned commands and calls and changes nothing.

    A task that holds more than S10's own material (:func:`generated_material`: a frozen B1, contracts, verifiers,
    candidates, labels, any file S10 does not write) is refused (outcome ``refused``, nothing changed): the step would
    rebuild B1, the image and the task's records under the material made from them. The check runs again before each write (the environment record, a rejection, B1, the final record) and between B1's
    grading run and B1's records, so material made while the resolver, the image build or a grading run is under way is
    kept too: the step is refused there (``refused_at``) and writes nothing more; task.json is read again just before it is
    updated.
    """
    task_dir, snapshot_root, workdir, cache_dir = Path(task_dir), Path(snapshot_root), Path(workdir), Path(cache_dir)

    def refused(found: list[str], at: str) -> dict[str, Any]:
        return {"outcome": "refused", "task_id": task_dir.name, "generated": found, "refused_at": at,
                "reason": Refused(task_dir, found, step="the S10 environment step").reason}

    def late(at: str) -> dict[str, Any] | None:
        found = generated_material(task_dir)
        return refused(found, at) if found else None

    early = late("start")
    if early:
        return early
    m = load(task_dir / "task.json", TaskManifest)
    s10 = json.loads((task_dir / S10_RECORD).read_text(encoding="utf-8"))
    plan, base = s10["closure_plan"], snapshot_root / m.task_id
    subset = s10["base_tests"]["subset"]
    args = env.repo_test_args(subset)
    if dry_run:
        return {"planned": True, "task_id": m.task_id, "closure": env.resolve_closure(plan, workdir / "resolve", dry_run=True),
                "image": env.build_image(["<the pinned closure>"], cache_dir, dry_run=True),
                "base_tests": env.run_base_tests(base, None, args=args, pythonpath=m.candidate_pythonpath, dry_run=True),
                "b1": env.build_b1(task_dir, base, None, subset=subset, pythonpath=m.candidate_pythonpath, dry_run=True)}

    def fail(step: str, rec: dict[str, Any]) -> dict[str, Any]:
        stop = late(f"before the {step} rejection")
        if stop:
            return stop
        s10[step] = {k: v for k, v in rec.items() if k not in ("stderr_tail",)}
        write_json(s10, task_dir / S10_RECORD)
        return reject_task(task_dir, rec["reason"], details=_safe(rec))

    # A real step (one that builds a real image) checks the resolver interpreter itself, whatever ``run`` wraps: pip must
    # evaluate environment markers for Python 3.12 (natural_env.RESOLVER_PYTHON). A step with a stub build records none.
    resolver = env.check_resolver_python() if build is None else None
    closure = env.resolve_with_sdists(plan, workdir, run=run, fetch_json=fetch_json or env.pypi_json, download=download or env._download)
    closure["resolver"] = closure.get("resolver") or resolver
    if closure.get("rejected"):
        return fail("environment", closure)
    local = workdir / "built-wheels" if closure.get("sdist_builds") else None
    image = env.build_image(closure["pins"], cache_dir, local_wheels=local, run=run, build=build)
    if image.get("rejected"):
        return fail("environment", image)
    stop = late("before the environment record")
    if stop:
        return stop
    s10["environment"] = {"pins": closure["pins"], "files": closure["files"], "wheelhouse_bytes": image.get("wheelhouse_bytes"),
                          "index_bytes": closure.get("wheelhouse_bytes"), "unknown_sizes": closure.get("unknown_sizes", []),
                          "uploaded_prior_to": closure.get("uploaded_prior_to"), "sdist_builds": closure.get("sdist_builds", []),
                          "dropped_path_requirements": closure.get("dropped_path_requirements", []),
                          "resolver": closure.get("resolver"),
                          "image": image["image"], "image_id": image["image_id"], "commands": closure.get("commands", [])}
    m = load(task_dir / "task.json", TaskManifest)  # read again: the copy read at the start may be stale after the build
    dump(m.model_copy(update={"env_requirements": closure["pins"]}), task_dir / "task.json")
    snap = load(task_dir / (m.snapshot or "snapshot.json"), Snapshot)
    dump(snap.model_copy(update={"environment": {"image": image["image"], "image_id": image["image_id"], "pins": closure["pins"]}}),
         task_dir / (m.snapshot or "snapshot.json"))
    write_json(s10, task_dir / S10_RECORD)
    base_run = env.run_base_tests(base, image["image"], args=args, pythonpath=m.candidate_pythonpath, runner=runner)
    if base_run.get("rejected"):
        return fail("base_test_run", base_run)
    stop = late("before B1")
    if stop:
        return stop
    from .sandbox.docker_runner import run_grader

    def b1_run(*a: Any, **kw: Any) -> Any:
        # build_b1 rewrites B1's spec and task.json from a copy it reads before this grading run: check in between.
        got = (runner or run_grader)(*a, **kw)
        found = generated_material(task_dir)
        if found:
            raise Refused(task_dir, found, step="the S10 environment step")
        return got

    s10["base_test_run"] = base_run
    try:
        s10["b1"] = env.build_b1(task_dir, base, image["image"], subset=subset, pythonpath=m.candidate_pythonpath, runner=b1_run)
    except Refused as exc:
        return refused(exc.found, "after B1's grading run, before B1's records")
    stop = late("before the S10 record")
    if stop:
        return stop
    s10.update({"outcome": "passed", "passed_at": _now()})
    write_json(s10, task_dir / S10_RECORD)
    return s10


# The committed index's header (write_natural_index).
DECISION_LOG = [f"D{n}" for n in range(47, 61)]  # D47 to D60: the natural arm's entries up to protocol v0.11
SOURCE = {
    "dataset": AIDEV_DATASET, "revision": AIDEV_REVISION, "url": f"https://huggingface.co/datasets/{AIDEV_DATASET}",
    "licence": "CC-BY-4.0", "licence_url": "https://creativecommons.org/licenses/by/4.0/",
    "attribution": (f"AIDev v5: the Hugging Face dataset {AIDEV_DATASET} at tag v5, released with Li, Zhang and Hassan, "
                    "arXiv:2507.15003 and arXiv:2602.09185; licensed under CC BY 4.0"),
    "changes": "ids, SHAs, counts and hashes extracted; no text",
    "repositories": ("each source repository keeps its own licence (per row: licence, identified from its LICENSE file at the "
                     "base); no repository code or text is in this index"),
}
PRIVACY = ("ids, SHAs, licence identifiers, sha256 hashes, counts and outcomes only: no thread text, login, handle or e-mail "
           "address; no source repository's name, URL or file path; no local path. The PR, review comment, issue and repository "
           "ids are public GitHub ids, as AIDev v5 publishes them; the fetched repositories are recorded in "
           "data/manifests/third_party_downloads.json, not here. File keys are the study's own file names, and each directory of "
           "repository files or generated tests (B1's overlay, verifiers/<id>/tests/, labels/base_tests_overlay/) is one manifest "
           "hash and a file count. The tasks are under data/natural/ (git-ignored, §17.4)")
SAMPLE_RULE = ("first: NP-01 to NP-25, the families and reserves of the first S9 sample; extension: from NP-26 on, the families "
               "of the S9 extension (§19.2, §19.3). The size rule of §19.6 counts the S11 tasks of both samples together")
FIELDS = {
    "files": ("sha256 of each task file by its task-relative path; a key ending in / is a directory, given as the manifest hash "
              "(path within the directory and sha256 of each file) and the number of its files"),
    "sanitize_natural": ("what sanitize-natural:v1 replaces in the stored session.json, as counts only. pass: by kind, the "
                         "counts of the v1 pass itself (sanitize_session), as an agent's sanitised copy gets them; the pass "
                         "renders a commit event's text from its tool input, so a commit message is dropped there, not "
                         "counted. counts and where: the v1 rules applied to every stored string (each event's text, a "
                         "commit message included, and tool input, the metadata and the repository URL), by kind and by "
                         "part of the thread (issue, pr_body, commits, hunk, review_comment, replies, metadata, repo_url; "
                         "an event of another form: its kind). session.json is never rewritten, and a handle counted can be "
                         "one of the pseudonymiser's own role labels"),
}


def _num(task_id: str) -> int:
    m = re.match(r"NP-(\d+)$", task_id)
    return int(m.group(1)) if m else 10 ** 6


# Where the index lists files by name: <dir>/<file>, and verifiers/<id>/<file> (summary_dir).
_LISTED_DEPTH = {"candidates": 2, "contracts": 2, "labels": 2, "verifiers": 3}


def summary_dir(rel: str) -> str | None:
    """The directory under which the index summarises a task file (``rel``, task-relative), or None when it lists the file.

    Listed by name: the task's own files at the top, in ``candidates/``, ``contracts/`` and ``labels/``, and in
    ``verifiers/<id>/``: names the study chose (ids, spec.json, status.json, selection.json). Every other directory is
    summarised: B1's overlay (:data:`OVERLAY`) and ``labels/base_tests_overlay/`` hold the repository's test files under
    their repository paths, ``verifiers/<id>/tests/`` the generated tests, whose file names follow the project's code; any
    other subdirectory, and any unknown top-level directory, is summarised too.
    """
    parts = rel.split("/")
    if len(parts) == 1:
        return None
    depth = _LISTED_DEPTH.get(parts[0])
    if depth is None:
        return parts[0] + "/"
    return None if len(parts) <= depth else "/".join(parts[:depth]) + "/"


def file_hashes(task_dir: Path) -> dict[str, Any]:
    """The sha256 of every file of a task directory, by its path there, except in the directories :func:`summary_dir` names.

    Each of those is one entry, its path with a trailing ``/``: the manifest hash of its files (path within the directory
    and sha256, as ``snapshot.manifest`` lists them) and their count. So no repository path and no generated test's file
    name enters the committed index, while any change to such a file still changes the row.
    """
    files: dict[str, Any] = {}
    groups: dict[str, list[tuple[str, str]]] = {}
    for p in sorted(task_dir.rglob("*")):
        if p.is_file():
            rel, digest = p.relative_to(task_dir).as_posix(), sha256_bytes(p.read_bytes())
            group = summary_dir(rel)
            if group is None:
                files[rel] = digest
            else:
                groups.setdefault(group, []).append((rel[len(group):], digest))
    for group, entries in groups.items():
        files[group] = {"manifest_sha256": manifest_sha256(entries), "n_files": len(entries)}
    return files


def sample_of(task_id: str | None) -> str | None:
    """The S9 sample a family comes from (§19.3): ``first`` for NP-01 to NP-25 (the first sample's families and reserves),
    ``extension`` from NP-26 on (the families of the S9 extension, §19.2); None for an id of another form."""
    n = _num(task_id or "")
    return None if n >= 10 ** 6 else "first" if n < EXTENSION_FROM else "extension"


def index_row(task_dir: Path | None, fam: Family | None) -> dict[str, Any]:
    """One family's row of the committed index: ids, SHAs, licence identifiers, file hashes, the sample, the S10 outcome and the
    sanitize-natural:v1 counts of its session; no text."""
    row: dict[str, Any] = _ids(fam) if fam else {"task_id": task_dir.name if task_dir else None}
    if fam:
        row["agent"] = fam.agent
    row["sample"] = sample_of(row["task_id"])
    if task_dir is None or not task_dir.is_dir() or not any(task_dir.iterdir()):
        row["s10"] = {"outcome": "not built"}
        return row
    files = file_hashes(task_dir)
    rej = json.loads((task_dir / REJECTION).read_text(encoding="utf-8")) if (task_dir / REJECTION).is_file() else None
    if not (task_dir / "task.json").is_file():
        row.update({k: rej.get(k) for k in ("pr_id", "repo_id", "comment_id") if rej and rej.get(k) is not None})
        row["s10"] = {"outcome": "rejected", "stage": (rej or {}).get("stage", STAGE), "reason": (rej or {}).get("reason")}
        row["files"] = files
        return row
    m = load(task_dir / "task.json", TaskManifest)
    prov = load(task_dir / m.provenance, ProvenanceRecord)
    snap = load(task_dir / (m.snapshot or "snapshot.json"), Snapshot)
    s10 = json.loads((task_dir / S10_RECORD).read_text(encoding="utf-8")) if (task_dir / S10_RECORD).is_file() else {}
    rec = json.loads((task_dir / RECORD).read_text(encoding="utf-8")) if (task_dir / RECORD).is_file() else {}
    pr = prov.natural_pr
    if pr:
        row.update({"pr_id": pr.pr_id, "repo_id": pr.repo_id, "comment_id": pr.comment_id, "issue_id": pr.issue_id,
                    "commits": {"base": pr.base_commit, "first": pr.first_commit, "reviewed": pr.reviewed_commit,
                                "addressing": pr.addressing_commit, "head": pr.head_commit, "default_branch_tip": pr.default_branch_tip},
                    "base_rule": pr.base_rule, "merge_state": pr.merge_state, "merges": len(pr.merges),
                    "licence": {"file_spdx": pr.licence_file_spdx, "aidev": pr.licence_aidev, "agrees": pr.licence_agrees,
                                "file_sha256": pr.licence_file_sha256},
                    "monorepo_package": bool(pr.snapshot_subdir)})
    cands = {}
    for p in m.candidates:
        c = load(task_dir / p, Candidate)
        cands[c.candidate_id] = {"origin": c.origin.value, "split": c.split.value, "patch_sha256": c.patch_sha256}
    base = s10.get("base_test_run") or {}
    sess = task_dir / PR_SESSION_FILE
    row["sanitize_natural"] = sanitizer_counts(load(sess, Session)) if sess.is_file() else None
    row.update({"status": m.status, "eligibility": prov.eligibility.value, "fidelity": snap.fidelity.value,
                "approximations": len(snap.approximations), "snapshot_manifest_sha256": snap.file_manifest_sha256, "n_files": snap.n_files,
                "trace_sha256": prov.trace_sha256, "candidates": cands,
                "reconstruction": {"method": rec.get("method"), "status": rec.get("status")},
                "s10": {"outcome": s10.get("outcome", "built"), "stage": STAGE, "reason": s10.get("reason"),
                        "environment": "pinned" if s10.get("environment") else "pending",
                        "pins": len((s10.get("environment") or {}).get("pins", [])) or None,
                        "base_tests": base.get("counts"), "base_test_subset": len((s10.get("base_tests") or {}).get("subset", [])),
                        "b1": ("available" if (s10.get("b1") or {}).get("available") else "unavailable") if s10.get("b1") else "pending"},
                "files": files})
    return row


def write_natural_index(tasks_root: str | Path, out: str | Path = INDEX, *, families: list[Family] | None = None) -> dict[str, Any]:
    """Write the committed index of the natural PR-review tasks (``data/manifests/natural_tasks_index.json``)."""
    tasks_root = Path(tasks_root)
    known = {f.task_id: f for f in families or []}
    dirs = {d.name: d for d in tasks_root.glob("NP-*") if d.is_dir()} if tasks_root.is_dir() else {}
    rows = [index_row(dirs.get(t), known.get(t)) for t in sorted(set(known) | set(dirs), key=_num)]
    rejected = {r["task_id"] for r in rows if r["s10"]["outcome"] == "rejected"}
    for r in rows:  # §17.3: a rejected family's place goes to the next reserve of its repository that is not rejected
        if r["task_id"] in rejected and r.get("role") == "family":
            nxt = [f for f in families or [] if f.role == "reserve" and f.repo_id == r.get("repo_id") and f.task_id not in rejected]
            taken = {x.get("replaced_by") for x in rows}
            nxt = [f for f in sorted(nxt, key=lambda f: f.rank_in_repository) if f.task_id not in taken]
            if nxt:
                r["replaced_by"] = nxt[0].task_id
    takers = {r.get("replaced_by") for r in rows} - {None}
    for r in rows:  # S11 (§16.4): passes S10 and is within the family cap (a family, or a reserve that takes a rejected family's place)
        r["s11"] = r["s10"]["outcome"] == "passed" and (r.get("role") == "family" or r["task_id"] in takers)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["s10"]["outcome"]] = counts.get(r["s10"]["outcome"], 0) + 1
    counts["s11"] = sum(r["s11"] for r in rows)
    by_sample = {k: sum(bool(r["s11"]) for r in rows if r.get("sample") == k) for k in ("first", "extension")}
    index = {"schema": "tracecontract/natural-tasks-index/v1", "population": "natural:pr-review", "stratum": "natural-pr-v1",
             "protocol": "experiments/protocol.md §15.6, §16.4, §17, §19", "decision_log": DECISION_LOG, "source": SOURCE,
             "privacy": PRIVACY, "storage": "data/natural/tasks/<task id>/ and data/natural/snapshots/<task id>/",
             "compiler": COMPILER, "sample_rule": SAMPLE_RULE, "fields": FIELDS, "counts": dict(sorted(counts.items())),
             "s11_by_sample": by_sample, "tasks": rows}
    write_json(index, Path(out))
    return index


__all__ = ["COMPILER", "Family", "INDEX", "PR_METHOD", "Refused", "Reject", "compile_pr_task", "find_family", "generated_material",
           "load_families", "pr_recheck", "recorded_pr_check", "reject_task", "run_s10_environment", "sample_of",
           "sanitizer_counts", "summary_dir", "write_natural_index"]
