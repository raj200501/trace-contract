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
:func:`write_natural_index` writes the committed index ``data/manifests/natural_tasks_index.json``: ids, SHAs,
licences, file hashes and S10 outcomes, no text.
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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from . import natural_env as env
from .ingest.github_pr import (
    AIDEV_DATASET, AIDEV_REVISION, AIDev, BareClone, CapExceeded, GitError, SourceProblem, build_session, collect_thread,
    leftover_identifiers, make_pseudonymizer,
)
from .ingest.pseudonymize_pr import mask_repo_url
from .ingest.repo_evidence import licence_from_text
from .patches import PatchApplyError, apply_patch, split_sections
from .reconstruction import RECORD, RecordCheck
from .schemas import (
    Candidate, CandidateOrigin, Eligibility, Fidelity, Label, LabelerKind, Population, PRProvenance, ProvenanceRecord,
    RedactionStatus, Snapshot, SnapshotSource, Split, TaskManifest, TriageCategory, TriageProposal, sha256_bytes, sha256_text,
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
    """The S11 families of ``s9_qualifying.json`` as NP-01 ... in the file's order, then the reserves (§17.3)."""
    q = json.loads(Path(path).read_text(encoding="utf-8"))
    comments = {int(c["comment_id"]): c for c in q["comments"]}
    order = [p for p in q["prs"] if p.get("s11_family")] + [p for p in q["prs"] if not p.get("s11_family")]
    out = []
    for k, p in enumerate(order, 1):
        c = comments[int(p["earliest_qualifying_comment_id"])]
        judges = tuple({x: (c.get(j) or {}).get(x) for x in ("request_type", "addressed", "testable_offline", "confidence")}
                       for j in ("judge_1", "judge_2"))
        out.append(Family(
            task_id=f"NP-{k:02d}", role="family" if p.get("s11_family") else "reserve", pr_id=int(p["pr_id"]),
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
        raise Reject(f"unreachable SHAs: the {' and the '.join(missing)} commit{'s are' if len(missing) > 1 else ' is'} not in the clone")
    items["a"] += [{"item": "reviewed commit in the clone", "status": "passed", "sha": reviewed},
                   {"item": "addressing commit in the clone", "status": "passed", "sha": addressing}]
    if not clone.is_ancestor(reviewed, addressing):
        raise Reject("the addressing commit does not descend from the reviewed commit")
    items["a"].append({"item": "the addressing commit descends from the reviewed commit", "status": "passed"})
    at_reviewed = [e for e in clone.ls_tree(reviewed, [fam.path]) if e[3] == fam.path]
    if not at_reviewed or at_reviewed[0][1] != "blob":
        raise Reject("the commented file is not a file at the reviewed commit")
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
        raise Reject("the PR's first commit cannot be determined (AIDev's first row is not a root of the PR's commits)")
    parents = meta[first]["parents"]
    if not parents:
        raise Reject("the PR's first commit has no parent")
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
        raise Reject("the base is not an ancestor of the reviewed and the addressing commits")
    merges = clone.rev_list("--merges", addressing, f"^{base}")
    mmeta = clone.meta(merges)
    touching = [m for m in merges if clone.changed(mmeta[m]["parents"][0], m, [fam.path])]
    items["c"] += [{"item": "merge", "sha": m, "touches_the_commented_file": m in touching,
                    "status": "failed" if m in touching else "passed"} for m in merges]
    if touching:
        raise Reject("a merge between the base and the addressing commit changes the commented file (§15.6)",
                     base_commit=base, merges=merges, merges_touching=touching)
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
    """``git archive`` of the base (the workspace's directory), its blobs fetched by id first; checked against the tree."""
    entries = clone.ls_tree(base, [subdir] if subdir else [])
    regular = {p: (m, o) for m, t, o, p in entries if t == "blob" and m in REGULAR}
    links = sorted(p for m, t, _, p in entries if m == "120000")
    gitlinks = sorted(p for _, t, _, p in entries if t == "commit")
    fetched = clone.ensure(base, {o for _, o in regular.values()}, label=f"base tree {base[:12]}")
    data = clone.run("archive", "--format=tar", base, *([subdir] if subdir else []), fetch=True, label="archive").stdout
    if dest.exists():
        shutil.rmtree(dest)
    _extract(data, dest, subdir)
    want = {_rel(p, subdir): v for p, v in regular.items()}
    entries_now = manifest(dest)
    have = {rel for rel, _ in entries_now}
    mismatched = sorted(rel for rel, (_, oid) in want.items() if rel in have and git_oid((dest / rel).read_bytes(), oid) != oid)
    return {"n_files": len(entries_now), "manifest_sha256": manifest_sha256(entries_now), "symlinks": len(links),
            "gitlinks": len(gitlinks), "mismatched": mismatched, "missing": sorted(set(want) - have),
            "extra": sorted(have - set(want)), "blobs_fetched": fetched, "git_dir": (dest / ".git").exists(),
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


def verify_candidate(snapshot: Path, patch: str, raw: list[dict[str, str]], subdir: str, dropped: list[dict[str, str]]) -> dict[str, Any]:
    """Apply the patch to a copy of the snapshot and compare every changed file with the commit's blob."""
    skip = {d["path"] for d in dropped}
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
                if f.exists():
                    bad.append(rel)
            elif r["new_mode"] in REGULAR and (not f.is_file() or git_oid(f.read_bytes(), r["new"]) != r["new"]):
                bad.append(rel)
    n = sum(1 for r in raw if _rel(r["path"], subdir) not in skip)
    return {"status": "failed" if bad else "passed", "files": n, "mismatched": sorted(bad),
            "reason": f"{len(bad)} of {n} changed file(s) differ from the commit" if bad else f"{n} changed file(s) reproduced"}


# --------------------------------------------------------------------------- the reconstruction record


def _check(cid: str, status: str, reason: str, items: list[dict[str, Any]] | None = None, approximations: list[str] | None = None) -> dict[str, Any]:
    return {"check_id": cid, "title": CHECK_TITLES[cid], "status": status, "reason": reason, "items": items or [],
            "approximations": approximations or []}


def pr_reconstruction(task_id: str, st: GitStates, snap: dict[str, Any], ref_v: dict[str, Any], pre_v: dict[str, Any],
                      inputs: dict[str, Any], approximations: list[str]) -> dict[str, Any]:
    """The PR reconstruction record (:data:`PR_METHOD`), in the shape :func:`reconstruction.recorded_check` reads."""
    d_bad = snap["mismatched"] + snap["missing"] + snap["extra"]
    checks = [
        _check("a_commits_reachable", "passed", "both commits are in the clone; the addressing commit descends from the reviewed one",
               st.items.get("a")),
        _check("b_base_rule", "passed", f"base by the rule {st.base_rule}", st.items.get("b"),
               [a for a in st.approximations if "merge commit" not in a]),
        _check("c_merge_rule", "failed" if st.touching else "passed",
               f"{len(st.merges)} merge(s) between the base and the addressing commit, {len(st.touching)} changing the commented file",
               st.items.get("c"), [a for a in st.approximations if "merge commit" in a]),
        _check("d_snapshot_equals_base_tree", "failed" if d_bad or snap["git_dir"] else "passed",
               f"{snap['n_files']} file(s); {len(snap['mismatched'])} differ from their blob, {len(snap['missing'])} missing, "
               f"{len(snap['extra'])} extra", [{"symlinks_not_materialised": snap["symlinks"], "submodules_not_materialised": snap["gitlinks"]}]),
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
    current files. Nothing is re-run; ``tracecontract compile-pr-task`` rebuilds the task and the record.
    """
    task_dir = Path(task_dir)
    path, hint = task_dir / RECORD, f"rebuild {task_dir.name} with `tracecontract compile-pr-task`"
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
            "replacements": md["pseudonymisation"]["replacements"], "trace_sha256": session.trace_sha256}


def compile_pr_task(family: Family, out_root: str | Path, *, plan_only: bool = False, aidev: AIDev | None = None,
                    aidev_data: str | Path = AIDEV_DATA, snapshot_root: str | Path | None = None,
                    fetch_log: str | Path | None = None, clone: BareClone | None = None) -> dict[str, Any]:
    """Build ``<out_root>/<task id>/`` for one family (see the module docstring), or with ``plan_only`` only plan it.

    Returns a JSON-able result with ``outcome`` ``planned``, ``built`` or ``rejected`` (with ``stage`` and ``reason``). It
    holds ids, SHAs, licence identifiers, counts and requirement specifiers; no text from the thread. A data problem
    becomes a rejection; only a programming error raises.
    """
    out_root = Path(out_root)
    snapshot_root = Path(snapshot_root) if snapshot_root else out_root.parent / "snapshots"
    fetch_log = Path(fetch_log) if fetch_log else out_root.parent / "s10_fetch_log.jsonl"
    res: dict[str, Any] = {**_ids(family), "compiler": COMPILER, "plan_only": plan_only, "started_at": _now()}
    st: GitStates | None = None
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
    except _data_errors() as exc:
        stage, reason, details = _as_rejection(exc)
        res.update({"outcome": "rejected", "stage": stage, "reason": reason, "details": _safe(details),
                    "fetches": clone.fetches if clone else []})
        if st is not None:
            res.setdefault("base", {"commit": st.base, "rule": st.base_rule})
        if not plan_only:
            for partial in (out_root / f".{family.task_id}.partial", snapshot_root / f".{family.task_id}.partial",
                            snapshot_root / family.task_id):  # a rejected task keeps no snapshot
                shutil.rmtree(partial, ignore_errors=True)
            write_rejection(out_root / family.task_id, family, stage, reason, _safe(details))
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
    """Replace ``task_dir`` with a directory holding only the family's rejection record."""
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


def _build(fam: Family, out_root: Path, snapshot_root: Path, clone: BareClone, aidev: AIDev, st: GitStates, subdir: str, url: str,
           acts: bool, lic: dict[str, Any], closure: dict[str, Any]) -> dict[str, Any]:
    tid = fam.task_id
    session = _session(fam, aidev, clone, st, url, acts)
    snap_dir = snapshot_root / tid
    snap_stage = snapshot_root / f".{tid}.partial"
    snap = materialize_base(clone, st.base, subdir, snap_stage)
    approximations = list(st.approximations)
    if subdir:
        approximations.append("the workspace is the package directory of a monorepo, not the whole repository")
    if snap["symlinks"] or snap["gitlinks"]:
        approximations.append(f"{snap['symlinks']} symbolic link(s) and {snap['gitlinks']} submodule(s) of the base tree are "
                              "not materialised")
    ref_patch, ref_raw, ref_drop = candidate_patch(clone, st.base, st.addressing, subdir)
    pre_patch, pre_raw, pre_drop = candidate_patch(clone, st.base, st.reviewed, subdir)
    if not ref_patch.strip():
        raise Reject("the reference patch is empty in the workspace")
    for what, dropped in (("reference", ref_drop), ("pre-review", pre_drop)):
        if dropped:
            approximations.append(f"the {what} patch leaves out {len(dropped)} file change(s) the grader cannot apply "
                                  f"({', '.join(sorted({d['why'] for d in dropped}))})")
    outside = {p for _, p in st.changed + st.changed_reviewed if _rel(p, subdir) is None}
    if outside:
        approximations.append(f"{len(outside)} changed file(s) outside the workspace are left out of the candidates")
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
    # Publish the snapshot and the task directory (each replaced whole).
    if snap_dir.exists():
        shutil.rmtree(snap_dir)
    snap_stage.rename(snap_dir)
    task_dir = out_root / tid
    if task_dir.exists():
        shutil.rmtree(task_dir)
    staging.rename(task_dir)
    files = {p.relative_to(task_dir).as_posix(): sha256_bytes(p.read_bytes()) for p in sorted(task_dir.rglob("*")) if p.is_file()}
    return {"task_dir": str(task_dir), "snapshot_dir": str(snap_dir), "fidelity": fidelity.value, "approximations": approximations,
            "reconstruction": rec["status"], "base_tests": {"subset": len(tests["subset"]), "rule": tests["rule"]},
            "candidates": {c.candidate_id: c.patch_sha256 for c in cands}, "session": _session_summary(session),
            "snapshot": {k: snap[k] for k in ("n_files", "manifest_sha256", "blobs_fetched", "symlinks", "gitlinks")}, "files": files}


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
    """
    task_dir, snapshot_root, workdir, cache_dir = Path(task_dir), Path(snapshot_root), Path(workdir), Path(cache_dir)
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
        s10[step] = {k: v for k, v in rec.items() if k not in ("stderr_tail",)}
        write_json(s10, task_dir / S10_RECORD)
        return reject_task(task_dir, rec["reason"], details=_safe(rec))

    closure = env.resolve_with_sdists(plan, workdir, run=run, fetch_json=fetch_json or env.pypi_json, download=download or env._download)
    if closure.get("rejected"):
        return fail("environment", closure)
    local = workdir / "built-wheels" if closure.get("sdist_builds") else None
    image = env.build_image(closure["pins"], cache_dir, local_wheels=local, run=run, build=build)
    if image.get("rejected"):
        return fail("environment", image)
    s10["environment"] = {"pins": closure["pins"], "files": closure["files"], "wheelhouse_bytes": image.get("wheelhouse_bytes"),
                          "index_bytes": closure.get("wheelhouse_bytes"), "unknown_sizes": closure.get("unknown_sizes", []),
                          "uploaded_prior_to": closure.get("uploaded_prior_to"), "sdist_builds": closure.get("sdist_builds", []),
                          "dropped_path_requirements": closure.get("dropped_path_requirements", []),
                          "image": image["image"], "image_id": image["image_id"], "commands": closure.get("commands", [])}
    dump(m.model_copy(update={"env_requirements": closure["pins"]}), task_dir / "task.json")
    snap = load(task_dir / (m.snapshot or "snapshot.json"), Snapshot)
    dump(snap.model_copy(update={"environment": {"image": image["image"], "image_id": image["image_id"], "pins": closure["pins"]}}),
         task_dir / (m.snapshot or "snapshot.json"))
    write_json(s10, task_dir / S10_RECORD)
    base_run = env.run_base_tests(base, image["image"], args=args, pythonpath=m.candidate_pythonpath, runner=runner)
    if base_run.get("rejected"):
        return fail("base_test_run", base_run)
    s10["base_test_run"] = base_run
    s10["b1"] = env.build_b1(task_dir, base, image["image"], subset=subset, pythonpath=m.candidate_pythonpath, runner=runner)
    s10.update({"outcome": "passed", "passed_at": _now()})
    write_json(s10, task_dir / S10_RECORD)
    return s10


def _num(task_id: str) -> int:
    m = re.match(r"NP-(\d+)$", task_id)
    return int(m.group(1)) if m else 10 ** 6


def index_row(task_dir: Path | None, fam: Family | None) -> dict[str, Any]:
    """One family's row of the committed index: ids, SHAs, licence identifiers, file hashes and the S10 outcome; no text."""
    row: dict[str, Any] = _ids(fam) if fam else {"task_id": task_dir.name if task_dir else None}
    if fam:
        row["agent"] = fam.agent
    if task_dir is None or not task_dir.is_dir() or not any(task_dir.iterdir()):
        row["s10"] = {"outcome": "not built"}
        return row
    files = {p.relative_to(task_dir).as_posix(): sha256_bytes(p.read_bytes()) for p in sorted(task_dir.rglob("*")) if p.is_file()}
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
    index = {"schema": "tracecontract/natural-tasks-index/v1", "population": "natural:pr-review", "stratum": "natural-pr-v1",
             "protocol": "experiments/protocol.md §15.6, §16.4, §17", "decision_log": ["D47", "D50", "D53"],
             "source": {"dataset": AIDEV_DATASET, "revision": AIDEV_REVISION},
             "privacy": "ids, SHAs, licence identifiers, sha256 file hashes, counts and S10 outcomes only: no login, handle, e-mail "
                        "address, URL, repository name, path or text; the tasks are under data/natural/ (git-ignored, §17.4)",
             "storage": "data/natural/tasks/<task id>/ and data/natural/snapshots/<task id>/", "compiler": COMPILER,
             "counts": dict(sorted(counts.items())), "tasks": rows}
    write_json(index, Path(out))
    return index


__all__ = ["COMPILER", "Family", "INDEX", "PR_METHOD", "Reject", "compile_pr_task", "find_family", "load_families",
           "recorded_pr_check", "reject_task", "run_s10_environment", "write_natural_index"]
