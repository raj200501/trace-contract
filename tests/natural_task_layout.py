"""A synthetic natural PR-review task laid out as an accepted family of the natural arm (S10 passed, S11 in the committed
index), for the tests of the natural arm's commands and scripts. Synthetic data only; not research evidence.

:func:`build_natural_task` writes, under a scratch repository root ``<root>``, what ``natural_pr.compile_pr_task`` and the
S10 environment step (``natural_pr.run_s10_environment``) leave for an accepted family:

* ``data/natural/tasks/<id>/``:
  * ``task.json``: population ``natural:pr-review``, status ``pending_review``, no contract, the pinned closure in
    ``env_requirements`` and the base-test subset in ``repo_test_args``;
  * ``provenance.json``: eligibility ``pending_review``, the PR record (:class:`~tracecontract.schemas.PRProvenance`) and
    the notes field ``snapshot_root: data/natural/snapshots`` that ``roots.snapshot_root`` reads;
  * ``snapshot.json``: the base manifest's hash and the S10 step's ``environment`` (image tag, image id, pins);
  * ``session.json``: a pseudonymised PR thread in the shape of ``ingest.github_pr.build_session``: the linked issue, the
    agent's PR body, the PR's commits, the review comment's diff hunk, the review comment and one reply of the reviewer
    before the addressing commit, with ``metadata.events`` naming each;
  * ``candidates/``: the reference (dev), the pre-review state (origin ``natural_pre_review``, eval, with its
    source-evidence label) and the no-op in both splits, as the compiler makes them;
  * ``reconstruction_check.json``: the PR reconstruction record (``natural_pr.PR_METHOD``, status passed), made from the
    current files with ``natural_pr.pr_current_inputs``, so ``natural_pr.recorded_pr_check`` accepts it;
  * ``s10.json``: outcome ``passed`` (or the outcome asked for);
  * ``verifiers/repo_tests/``: B1, the repository's test file at the addressing commit (in_process, not frozen);
* ``data/natural/snapshots/<id>/``: the base snapshot;
* ``data/manifests/natural_tasks_index.json``: the index with the task's row (``s11`` true, or as asked), committed when
  ``<root>`` is a git repository (:func:`init_git`), since the acceptance gate reads the index of the HEAD commit.

:func:`write_phase_ends` writes and commits ``data/manifests/natural_phase_ends.jsonl``, the phase-end log (the order
record of decision log D65): one line per family and phase (:func:`phase_end_line`), in the form
``scripts/record_phase_end.py`` writes, with its state's hashes left out, since the rules that read the log (the
pre-flight's ``phase_end_problems``, decision log D73) read only the schema, task id, phase and time.

The files are written directly, not compiled (as tests/natural_pr_world.py does), so no DuckDB is needed, and a git
repository only for the rules that ask git (the committed index, the git-ignored run directory). Every text is synthetic
and holds no login, handle, e-mail address or model identifier. The agent-only texts (the PR body and the commit messages)
carry :data:`AGENT_ONLY_MARKERS`, so a test can check that no reader of the thread sees them. :func:`use_layout` points the
CLI at ``<root>`` and replaces Docker by stubs: the image build, the local image lookup and the grader.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tracecontract import natural_pr as npr
from tracecontract.ingest.github_pr import AIDEV_DATASET, AIDEV_REVISION, COMMIT_TOOL, NOT_USER_EVIDENCE, SOURCE_FORMAT
from tracecontract.patches import diff_dirs
from tracecontract.reconstruction import RECORD
from tracecontract.sandbox.docker_runner import _req_hash
from tracecontract.schemas import (
    Author, Candidate, CandidateOrigin, Eligibility, Event, EventKind, Fidelity, Isolation, Label, LabelerKind, Outcome,
    Population, PRProvenance, ProvenanceRecord, RedactionStatus, Session, Snapshot, SnapshotSource, SourceRef, Split,
    TaskManifest, VerificationResult, VerifierCondition, sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, write_json
from tracecontract.verifier import build_spec

T0 = "2026-11-21T10:00:00+00:00"
TASK_ID = "NP-90"
NATURAL_TASKS = Path("data/natural/tasks")
NATURAL_SNAPSHOTS = Path("data/natural/snapshots")
INDEX = Path("data/manifests/natural_tasks_index.json")
PHASE_ENDS = Path("data/manifests/natural_phase_ends.jsonl")  # scripts/record_phase_end.py's LOG, SCHEMA and PHASES
PHASE_END_SCHEMA = "tracecontract/natural-phase-end/v1"
PHASES = ("P1", "P2", "P3", "P4", "P5", "P6", "P7")
PINS = ["iniconfig==2.0.0", "packaging==24.2", "pluggy==1.5.0", "pytest==8.3.4"]
IMAGE = f"tc-env:{_req_hash(sorted(set(PINS)))}"  # as docker_runner.build_env_image names it
IMAGE_ID = "sha256:" + "9e" * 32
TEST_ARGS = ["-o", "addopts=", "tests/test_mod.py"]

# The agent-only texts: shown to no reader of the thread (render_pr_thread shows the issue, hunk, comment and replies).
PR_BODY_MARKER = "FX-AGENT-PR-BODY"
COMMIT_MARKER = "FX-AGENT-COMMIT-MESSAGE"
AGENT_ONLY_MARKERS = (PR_BODY_MARKER, COMMIT_MARKER)

ISSUE_TEXT = ("add() should treat a missing value as zero\n\n"
              "Calling add(None, 2) raises a TypeError. It should return 2, as if the missing value were 0.")
PR_TEXT = f"Treat None as zero in add()\n\n{PR_BODY_MARKER}: the agent's own description of its change."
COMMENT_TEXT = "This handles a missing first argument only. add(2, None) still raises; treat a missing second argument as 0 too."
REPLY_TEXT = "And add(None, None) should return 0."
HUNK_TEXT = "@@ -1,2 +1,4 @@\n def add(a, b):\n+    if a is None:\n+        a = 0\n     return a + b"

BASE_MOD = "def add(a, b):\n    return a + b\n\n\ndef neg(a):\n    return -a\n"
PRE_REVIEW_MOD = "def add(a, b):\n    if a is None:\n        a = 0\n    return a + b\n\n\ndef neg(a):\n    return -a\n"
REFERENCE_MOD = ("def add(a, b):\n    if a is None:\n        a = 0\n    if b is None:\n        b = 0\n    return a + b\n\n\n"
                 "def neg(a):\n    return -a\n")
BASE_TEST = "from fxnat.mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
REFERENCE_TEST = BASE_TEST + "\n\ndef test_missing_values():\n    assert add(None, 2) == 2 and add(2, None) == 2\n"
BASE_FILES = {
    "LICENSE": "MIT License\n\nCopyright (c) 2025 the fixture authors\n\nPermission is hereby granted, free of charge, to any "
               "person obtaining a copy of this software, to deal in the Software without restriction.\n",
    "pyproject.toml": "[project]\nname = \"fxnat\"\nversion = \"0.1\"\n\n[project.optional-dependencies]\ntest = [\"pytest\"]\n",
    "fxnat/__init__.py": "from .mod import add\n",
    "fxnat/mod.py": BASE_MOD,
    "tests/test_mod.py": BASE_TEST,
}
PRE_REVIEW_FILES = {"fxnat/mod.py": PRE_REVIEW_MOD}
REFERENCE_FILES = {"fxnat/mod.py": REFERENCE_MOD, "tests/test_mod.py": REFERENCE_TEST}
B1_CHECKS = ["tests/test_mod.py::test_add", "tests/test_mod.py::test_missing_values"]


def _sha(name: str, task_id: str) -> str:
    return hashlib.sha1(f"{task_id}/{name}".encode()).hexdigest()


@dataclass(frozen=True)
class NaturalTask:
    """One synthetic task of the layout (:func:`build_natural_task`)."""

    root: Path  # the scratch repository root (cli.REPO in a test)
    task_id: str
    number: int  # the task's number, from which its ids are made

    @property
    def task_dir(self) -> Path:
        return self.root / NATURAL_TASKS / self.task_id

    @property
    def snapshot_dir(self) -> Path:
        return self.root / NATURAL_SNAPSHOTS / self.task_id

    @property
    def tasks_root(self) -> Path:
        return self.root / NATURAL_TASKS

    @property
    def index(self) -> Path:
        return self.root / INDEX

    @property
    def session_id(self) -> str:
        return f"aidev-pr-{self.pr_id}"

    @property
    def pr_id(self) -> int:
        return 9000 + self.number

    @property
    def comment_id(self) -> int:
        return 8000 + 2 * self.number

    @property
    def reply_id(self) -> int:
        return 8001 + 2 * self.number

    def sha(self, name: str) -> str:
        """The (fictional) commit SHA of ``name``: base, first, reviewed, addressing or head."""
        return _sha(name, self.task_id)

    def event(self, which: str) -> str:
        """The event id of ``which``: issue, pr, hunk, comment, reply, or a commit (first, reviewed, addressing)."""
        sid = self.session_id
        return {"issue": f"{sid}/issue", "pr": f"{sid}/pr", "hunk": f"{sid}/review/{self.comment_id}/hunk",
                "comment": f"{sid}/review/{self.comment_id}", "reply": f"{sid}/reply/{self.reply_id}"}.get(
            which, f"{sid}/commit/{self.sha(which)[:12]}")

    def candidate_id(self, kind: str) -> str:
        return f"{self.task_id}-{kind}"


def _tree(dest: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return dest


def _state_patch(base: Path, overrides: dict[str, str], scratch: Path) -> str:
    state = scratch / "state"
    shutil.copytree(base, state)
    _tree(state, overrides)
    patch = diff_dirs(base, state)
    shutil.rmtree(state)
    return patch


def _session(nt: NaturalTask) -> Session:
    sid, rev8 = nt.session_id, AIDEV_REVISION[:8]
    events: list[Event] = []

    def add(suffix: str, kind: EventKind, author: Author, text: str, table: str, native: str, **kw: Any) -> str:
        eid = f"{sid}/{suffix}"
        events.append(Event(event_id=eid, session_id=sid, index=len(events), kind=kind, author=author, timestamp=T0, text=text,
                            source=SourceRef(path=f"{AIDEV_DATASET}@{rev8}/{table}.parquet", line=len(events) + 1,
                                             native_id=native), **kw))
        return eid

    def commit(name: str, message: str) -> str:
        sha = nt.sha(name)
        return add(f"commit/{sha[:12]}", EventKind.tool_call, Author.agent, message, "pr_commits", sha, tool_name=COMMIT_TOOL,
                   tool_input={"sha": sha, "parents": [], "files": ["fxnat/mod.py"], "agent_attributed": True})

    issue = add("issue", EventKind.user_prompt, Author.human, ISSUE_TEXT, "issue", str(7000 + nt.number))
    pr = add("pr", EventKind.assistant_text, Author.agent, PR_TEXT, "pull_request", str(nt.pr_id))
    first = commit("first", f"Initial plan\n\n{COMMIT_MARKER} 1")
    reviewed = commit("reviewed", f"Treat a missing first argument as zero\n\n{COMMIT_MARKER} 2")
    hunk = add(f"review/{nt.comment_id}/hunk", EventKind.metadata, Author.tool, HUNK_TEXT, "pr_review_comments",
               f"{nt.comment_id}:diff_hunk")
    comment = add(f"review/{nt.comment_id}", EventKind.user_prompt, Author.human, COMMENT_TEXT, "pr_review_comments",
                  str(nt.comment_id))
    reply = add(f"reply/{nt.reply_id}", EventKind.user_prompt, Author.human, REPLY_TEXT, "pr_review_comments", str(nt.reply_id))
    addressing = commit("addressing", f"Treat missing arguments as zero\n\n{COMMIT_MARKER} 3")
    metadata = {
        "aidev": {"dataset": AIDEV_DATASET, "revision": AIDEV_REVISION, "pr_id": nt.pr_id, "pr_number": nt.number,
                  "repo_id": 900 + nt.number, "comment_id": nt.comment_id, "issue_id": 7000 + nt.number,
                  "issue_number": 100 + nt.number, "reply_comment_ids": [nt.reply_id], "other_qualifying_comment_ids": []},
        "events": {"replies": [reply], "commits": [first, reviewed, addressing], "initial_request": issue,
                   "agent_description": pr, "reviewed_commit": reviewed, "addressing_commit": addressing,
                   "correction_context": hunk, "correction": comment},
        "not_user_evidence": {pr: NOT_USER_EVIDENCE["pr"], first: NOT_USER_EVIDENCE["commit"],
                              reviewed: NOT_USER_EVIDENCE["commit"], hunk: NOT_USER_EVIDENCE["hunk"],
                              addressing: NOT_USER_EVIDENCE["commit"]},
        "commented_path": "fxnat/mod.py",
        "comment_anchor": {"original_position": 2, "position": 1, "original_commit_id": nt.sha("reviewed"),
                           "commit_id": nt.sha("head")},
        "reviewed_commit": nt.sha("reviewed"), "addressing_commit": nt.sha("addressing"), "replies_excluded": {},
        "pseudonymisation": {"method": "synthetic fixture", "owner_masked": True, "replacements": {}},
        "event_order": "issue; PR; commits through the reviewed commit; hunk and comment; replies; the addressing commit",
    }
    return Session(session_id=sid, population=Population.natural_pr_review, source=AIDEV_DATASET, source_revision=AIDEV_REVISION,
                   source_format=SOURCE_FORMAT, agent="FixtureAgent", repo_url="https://github.com/{owner}/fxnat",
                   trace_sha256=sha256_text(f"synthetic thread {nt.task_id}"), events=events, metadata=metadata)


def _candidates(nt: NaturalTask, base: Path, scratch: Path) -> list[Candidate]:
    ref_patch = _state_patch(base, REFERENCE_FILES, scratch)
    pre_patch = _state_patch(base, PRE_REVIEW_FILES, scratch)
    se = Label(value="invalid", labeler="source-evidence:aidev-s9", labeler_kind=LabelerKind.source_evidence, timestamp=T0,
               note="the reviewer's request, the addressing commit and the agreement of both S9 judges (synthetic)")
    noop_label = Label(value="invalid", labeler="construction", labeler_kind=LabelerKind.construction, timestamp=T0,
                       note="no change made")
    cands = [
        Candidate(candidate_id=nt.candidate_id("reference"), task_id=nt.task_id, origin=CandidateOrigin.reference, split=Split.dev,
                  patch=ref_patch, patch_sha256=sha256_text(ref_patch), produced_by=f"git:{nt.sha('addressing')}",
                  description="The tree at the addressing commit, against the base"),
        Candidate(candidate_id=nt.candidate_id("pre-review"), task_id=nt.task_id, origin=CandidateOrigin.natural_pre_review,
                  split=Split.eval, patch=pre_patch, patch_sha256=sha256_text(pre_patch), produced_by=f"git:{nt.sha('reviewed')}",
                  description="The tree the reviewer commented on, against the base", labels=[se]),
    ]
    for split in (Split.dev, Split.eval):
        cands.append(Candidate(candidate_id=nt.candidate_id(f"noop-{split.value}"), task_id=nt.task_id, origin=CandidateOrigin.noop,
                               split=split, patch="", patch_sha256=sha256_text(""), produced_by="base snapshot",
                               description="No-op: the unchanged base snapshot.", labels=[noop_label]))
    return cands


def _provenance(nt: NaturalTask, session: Session, base_manifest: str) -> ProvenanceRecord:
    pr = PRProvenance(dataset=AIDEV_DATASET, revision=AIDEV_REVISION, pr_id=nt.pr_id, pr_number=nt.number, repo_id=900 + nt.number,
                      agent="FixtureAgent", comment_id=nt.comment_id, reply_comment_ids=[nt.reply_id], issue_id=7000 + nt.number,
                      issue_number=100 + nt.number, base_commit=nt.sha("base"), base_rule="merge_base",
                      first_commit=nt.sha("first"), reviewed_commit=nt.sha("reviewed"), addressing_commit=nt.sha("addressing"),
                      head_commit=nt.sha("head"), default_branch_tip=nt.sha("tip"), merge_state="no_merges",
                      fidelity=Fidelity.exact, licence_file_spdx="MIT", licence_file_sha256=sha256_text(BASE_FILES["LICENSE"]),
                      licence_aidev="MIT", licence_agrees=True, owner_masked=True)
    return ProvenanceRecord(
        record_id=f"prov-{nt.task_id}", session_id=session.session_id, population=Population.natural_pr_review,
        source_url=f"https://huggingface.co/datasets/{AIDEV_DATASET}", source_id=f"aidev:pr:{nt.pr_id}/comment:{nt.comment_id}",
        source_revision=AIDEV_REVISION, repo_url=session.repo_url, base_commit=nt.sha("base"),
        licenses={"code": "MIT", "code_aidev": "MIT", "dataset": "CC-BY-4.0"}, permission_basis="synthetic fixture",
        trace_sha256=session.trace_sha256, snapshot_manifest_sha256=base_manifest, capture_method="synthetic fixture",
        redaction_status=RedactionStatus.redacted_by_us, task_family_id=nt.task_id, eligibility=Eligibility.pending_review,
        accessed=T0, natural_pr=pr,
        notes=json.dumps({"compiler": npr.COMPILER, "repo_url_masked": True, "snapshot_root": NATURAL_SNAPSHOTS.as_posix()}))


def _pr_record(nt: NaturalTask) -> dict[str, Any]:
    """The PR reconstruction record that compile-pr-task writes for a family whose six checks pass, from the current files."""
    checks = [{"check_id": cid, "title": title, "status": "passed", "reason": "synthetic fixture", "items": [],
               "approximations": []} for cid, title in npr.CHECK_TITLES.items()]
    return {"task_id": nt.task_id, "method": npr.PR_METHOD, "status": "passed", "passed": True, "fidelity": "exact",
            "approximations": [], "checks": checks, "inputs": npr.pr_current_inputs(nt.task_dir), "notes": [], "files": []}


def write_index_row(root: Path, task_id: str, *, s11: bool = True, outcome: str = "passed", commit: bool = True,
                    **extra: Any) -> Path:
    """Add or replace the task's row in the index under ``root`` (``data/manifests/natural_tasks_index.json``), and with
    ``commit`` commit it when ``root`` is a git repository (:func:`commit_index`)."""
    path = root / INDEX
    index = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "schema": "tracecontract/natural-tasks-index/v1", "population": "natural:pr-review", "stratum": "natural-pr-v1",
        "compiler": npr.COMPILER, "tasks": []}
    rows = [r for r in index["tasks"] if r.get("task_id") != task_id]
    rows.append({"task_id": task_id, "role": "family", "s10": {"outcome": outcome, "stage": "S10"}, "s11": s11, **extra})
    index["tasks"] = sorted(rows, key=lambda r: r["task_id"])
    counts: dict[str, int] = {}
    for r in index["tasks"]:
        counts[r["s10"]["outcome"]] = counts.get(r["s10"]["outcome"], 0) + 1
    index["counts"] = {**dict(sorted(counts.items())), "s11": sum(bool(r.get("s11")) for r in index["tasks"])}
    write_json(index, path)
    if commit and (root / ".git").exists():
        commit_index(root)
    return path


def write_s10(nt: NaturalTask, outcome: str = "passed") -> None:
    s10 = {"schema": "tracecontract/natural-s10/v1", "task_id": nt.task_id, "stage": "S10", "compiler": npr.COMPILER,
           "built_at": T0, "outcome": outcome,
           "base_tests": {"subset": [TEST_ARGS[-1]], "rule": "synthetic fixture", "changed_test_files": [TEST_ARGS[-1]]},
           "environment": {"pins": PINS, "image": IMAGE, "image_id": IMAGE_ID} if outcome == "passed" else None,
           "b1": {"available": True, "n_checks": len(B1_CHECKS), "mode": "repo_tests (in_process)"} if outcome == "passed" else None}
    if outcome == "passed":
        s10["passed_at"] = T0
    write_json(s10, nt.task_dir / npr.S10_RECORD)


def build_natural_task(root: Path, task_id: str = TASK_ID, *, s10_outcome: str = "passed", s11: bool = True,
                       index: bool = True, image_id: str | None = IMAGE_ID, b1: bool = True) -> NaturalTask:
    """Write one synthetic natural PR-review task under ``root`` (see the module docstring); return its paths and ids.

    ``s10_outcome``: what ``s10.json`` records (``passed``; ``built`` is a family the S10 environment step has not run on).
    ``s11`` and ``index``: the task's row in the committed index (none without ``index``). ``image_id``: the id that
    ``snapshot.json`` records for the image (``None``: none recorded). ``b1``: write B1 (``verifiers/repo_tests``).
    """
    number = int(task_id.rsplit("-", 1)[-1])
    nt = NaturalTask(root=Path(root), task_id=task_id, number=number)
    td, base = nt.task_dir, _tree(nt.snapshot_dir, BASE_FILES)
    scratch = root / f".scratch-{task_id}"
    scratch.mkdir(parents=True)
    cands = _candidates(nt, base, scratch)
    shutil.rmtree(scratch)
    for c in cands:
        dump(c, td / "candidates" / f"{c.candidate_id}.json")
    session = _session(nt)
    dump(session, td / "session.json")
    base_manifest = manifest_sha256(manifest(base))
    environment = {"image": IMAGE, "pins": PINS, **({"image_id": image_id} if image_id else {})}
    dump(Snapshot(snapshot_id=f"{task_id}@{nt.sha('base')[:12]}", task_id=task_id, repo_url=session.repo_url or "",
                  base_commit=nt.sha("base"), fidelity=Fidelity.exact, file_manifest_sha256=base_manifest,
                  n_files=len(BASE_FILES), environment=environment), td / "snapshot.json")
    dump(_provenance(nt, session, base_manifest), td / "provenance.json")
    verifiers = []
    if b1:  # the repository's test file as the reference has it (natural_env.build_b1)
        overlay = _tree(td / "verifiers" / "repo_tests" / "overlay", {TEST_ARGS[-1]: REFERENCE_TEST})
        (td / "verifiers" / "repo_tests" / "check_ids.json").write_text(json.dumps(B1_CHECKS), encoding="utf-8")
        dump(build_spec(verifier_id="repo_tests", task_id=task_id, condition=VerifierCondition.repo_tests, test_dir=overlay,
                        task_dir=td, isolation=Isolation.in_process, check_ids=B1_CHECKS),
             td / "verifiers" / "repo_tests" / "spec.json")
        verifiers.append("verifiers/repo_tests/spec.json")
    dump(TaskManifest(task_id=task_id, family_id=task_id, population=Population.natural_pr_review, status="pending_review",
                      provenance="provenance.json", snapshot_source=SnapshotSource(repo_url=session.repo_url or "",
                                                                                   commit=nt.sha("base")),
                      snapshot="snapshot.json", env_requirements=PINS, candidate_pythonpath="/work", repo_test_args=TEST_ARGS,
                      verifiers=verifiers, candidates=[f"candidates/{c.candidate_id}.json" for c in cands],
                      notes="synthetic natural PR-review task (tests/natural_task_layout.py)"), td / "task.json")
    write_json(_pr_record(nt), td / RECORD)
    write_s10(nt, s10_outcome)
    if index:
        write_index_row(root, task_id, s11=s11, outcome=s10_outcome)
    return nt


def git_env() -> dict[str, str]:
    """The environment of the fixture's git commands: none of the caller's ``GIT_*`` variables, no global or system
    configuration."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"GIT_CONFIG_GLOBAL": os.devnull,
                                                                                "GIT_CONFIG_NOSYSTEM": "1"}


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run ``git -C root <args>`` with :func:`git_env` and a synthetic committer (a name, no e-mail address)."""
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=fixture", "-c", "user.email=", *args], check=True,
                          capture_output=True, env=git_env())


def init_git(root: Path) -> None:
    """Make ``root`` a git repository whose ``.gitignore`` ignores ``data/natural/``, as the study repository's does."""
    (root / ".gitignore").write_text("data/natural/\n/snapshots/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True, env=git_env())


def commit_file(root: Path, rel: Path, message: str) -> None:
    """Commit the file ``rel`` under ``root`` (nothing else) in the git repository at ``root``, if it changed."""
    git(root, "add", "--", rel.as_posix())
    staged = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--quiet", "--", rel.as_posix()],
                            capture_output=True, env=git_env(), check=False)
    if staged.returncode:
        git(root, "commit", "-q", "--no-verify", "-m", message, "--", rel.as_posix())


def commit_index(root: Path) -> None:
    """Commit the index under ``root`` (nothing else) in the git repository at ``root``, if it changed."""
    commit_file(root, INDEX, "natural index (synthetic fixture)")


def phase_end_line(task_id: str, phase: str, recorded_at: str, **fields: Any) -> dict[str, Any]:
    """One line of the phase-end log as ``scripts/record_phase_end.py`` writes it, without the state's hashes (the
    ``files``, ``verifiers``, ``contracts`` and ``candidates`` it summarises), then ``fields``."""
    return {"schema": PHASE_END_SCHEMA, "task_id": task_id, "phase": phase, "recorded_at": recorded_at, "head": None,
            **fields}


def phase_ends(task_id: str, phases: tuple[str, ...] = PHASES, *, day: str = "2026-11-22") -> list[dict[str, Any]]:
    """The lines of ``phases`` of a task, in the order given, the n-th recorded at the n-th hour of ``day`` (UTC)."""
    return [phase_end_line(task_id, p, f"{day}T{n:02d}:00:00Z") for n, p in enumerate(phases, 1)]


def write_phase_ends(root: Path, lines: list[dict[str, Any] | str], *, commit: bool = True) -> Path:
    """Write the phase-end log under ``root`` (``data/manifests/natural_phase_ends.jsonl``): each line a record, as one
    line of JSON, or a string, written as it is; then, with ``commit``, commit it (nothing else) when ``root`` is a git
    repository."""
    path = root / PHASE_ENDS
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join((x if isinstance(x, str) else json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
                   + "\n" for x in lines)
    path.write_text(text, encoding="utf-8")
    if commit and (root / ".git").exists():
        commit_file(root, PHASE_ENDS, "natural phase ends (synthetic fixture)")
    return path


def image_stub(images: dict[tuple[str, ...], tuple[str, str]] | None = None, builds: list | None = None):
    """A stand-in for ``docker_runner.build_env_image``: the layout's image (tag and recorded id) for its pins, unless
    ``images`` maps the sorted pins to another ``(tag, id)``; any other requirement list gets a fixture image. Each call's
    sorted pins are appended to ``builds``, if given."""
    known = {tuple(sorted(set(PINS))): (IMAGE, IMAGE_ID), **(images or {})}

    def build_env_image(reqs, cache_dir, **_):
        if builds is not None:
            builds.append(tuple(sorted(set(reqs))))
        return known.get(tuple(sorted(set(reqs))), ("tc-fixture:0", "sha256:" + "0" * 64))
    return build_env_image


def local_image_stub(local: dict[str, str | None] | None = None):
    """A stand-in for ``evaluate.local_image_id``: the id of the layout's image for its tag, unless ``local`` maps a tag to
    another id or to ``None`` (no such image on the host)."""
    known: dict[str, str | None] = {IMAGE: IMAGE_ID, **(local or {})}

    def local_image_id(tag):
        return known.get(tag)
    return local_image_id


def grader_stub(calls: list[dict[str, Any]], outcome: Outcome = Outcome.passed):
    """A stand-in for ``docker_runner.verify_candidate`` that records each call (its base_dir among them) and returns
    ``outcome``."""

    def verify_candidate(*, image, base_dir, spec, task_dir, candidate, run_id, repeats=1, **kw):
        calls.append({"image": image, "base_dir": Path(base_dir), "task_dir": Path(task_dir), "verifier_id": spec.verifier_id,
                      "candidate_id": candidate.candidate_id, "repeats": repeats})
        return VerificationResult(run_id=run_id, task_id=spec.task_id, verifier_id=spec.verifier_id,
                                  candidate_id=candidate.candidate_id, outcome=outcome,
                                  reward=1.0 if outcome == Outcome.passed else 0.0, started_at=T0, finished_at=T0, wall_s=0.0,
                                  harness_version="stub")
    return verify_candidate


def use_layout(monkeypatch, root: Path, calls: list[dict[str, Any]] | None = None, *,
               images: dict[tuple[str, ...], tuple[str, str]] | None = None, local: dict[str, str | None] | None = None,
               builds: list | None = None) -> list[dict[str, Any]]:
    """Point the CLI at the scratch repository ``root`` (``cli.REPO``, ``SNAPSHOTS``, ``CACHE``) and replace Docker: the
    image build (:func:`image_stub`, which appends to ``builds``) and the grader (:func:`grader_stub`) of ``evaluate`` and
    ``docker_runner``, and the local image lookup of ``evaluate`` (:func:`local_image_stub`). Returns the list the grader
    stub appends its calls to."""
    from tracecontract import cli, evaluate
    from tracecontract.sandbox import docker_runner

    calls = [] if calls is None else calls
    monkeypatch.setattr(cli, "REPO", Path(root))
    monkeypatch.setattr(cli, "SNAPSHOTS", Path(root) / "snapshots")
    monkeypatch.setattr(cli, "CACHE", Path(root) / "cache")
    for mod in (evaluate, docker_runner):
        monkeypatch.setattr(mod, "build_env_image", image_stub(images, builds))
        monkeypatch.setattr(mod, "verify_candidate", grader_stub(calls))
    monkeypatch.setattr(evaluate, "local_image_id", local_image_stub(local))
    return calls
