"""The CLI, evaluate, the acceptance gate and the schema for natural PR-review tasks (build plan WP-A).

* Every command that needs a task's base snapshot finds a natural task's under ``data/natural/snapshots``
  (``roots.snapshot_root``): grade, audit, ``add-candidate --state-dir``, ``add-stratum-candidate``, materialize,
  validate-task and evaluate; ``snapshot`` refuses a natural task, and ``reconstruction-check`` prints its PR record,
  exits as the gate reads that record and refuses ``--write``.
* ``evaluate`` writes a natural run only to a git-ignored directory of the repository (``--out-root``), refuses before
  writing anything (the gate, the snapshot, an image that is missing or whose id is not the recorded one, an out root that
  a git work tree could commit or that lies outside the repository), and records ``task_dir``. evaluate, grade, audit and
  the sandbox commands look a natural task's image up and never build it.
* No natural task's material goes where a git work tree could commit it, a linked work tree, another clone or a nested
  repository included: the out guard of export-gen-workspace, review-packet, render-session and materialize.
* ``--tasks-root`` for analyze, report and merge-reviews; the natural sub-populations are never pooled silently, also in
  a run that passes the natural rules of evaluate.
* ``--generation-record`` on build-verifier, make-contract and add-candidate, required for a natural task's contract
  and constructed candidates, and only a constructed candidate carries one. make-contract checks a natural task's
  proposals on the events that the variant's proposer is shown, and check-proposals repeats that from the two files it
  names, and opens no other.
* The gate refuses a natural task whose S10 outcome is not ``passed`` and names one that the committed index (the HEAD
  commit's) does not mark S11.

Synthetic tasks only (tests/natural_task_layout.py); Docker is replaced by stubs. Not research evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from natural_task_layout import (
    BASE_FILES, COMMENT_TEXT, IMAGE, IMAGE_ID, INDEX, REFERENCE_MOD, T0, NaturalTask, build_natural_task, git, init_git,
    use_layout, write_index_row,
)
from tracecontract import cli, evaluate, tasks
from tracecontract import contract as contract_mod
from tracecontract import natural_pr as npr
from tracecontract.analysis import PILOT_LABELER, MixedPopulations, analyze
from tracecontract.contract import NOT_A_USER_TURN, check_proposals, natural_gate_problems, requirements_from_proposals, task_gate
from tracecontract.evaluate import RunRefused, private_location_problem
from tracecontract.reconstruction import RECORD
from tracecontract.schemas import (
    Author, Candidate, CandidateOrigin, ContractVariant, Event, EventKind, Fidelity, GenerationRecord, Isolation, Label,
    LabelerKind, Population, Session, Snapshot, SnapshotSource, SourceRef, Split, TaskContract, TaskManifest,
    VerifierCondition, VerifierSpec, sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, load
from tracecontract.verifier import build_spec, freeze, generation_record

REPO = Path(__file__).resolve().parents[1]
# A Claude session's temporary directory and the third-party data, built from parts so that no tracked file names such
# a path; the tests only check that nothing is written there.
SESSION_TMP = Path("/tmp") / ("claude-" + "0")
EXT = Path("/home/user") / "ext"
SHA = "ab" * 32
RUN = {"run_id": "natural-test/contract-full", "config": "config-A", "prompt_sha256": SHA,
       "started_at": "2026-11-22T10:00:00+00:00", "ended_at": "2026-11-22T10:20:00+00:00", "wall_s": 1180.5,
       "tool_calls": 57, "turns": 31, "run_record": "private-runs/natural-test/contract-full.json"}


# --------------------------------------------------------------------------- helpers


def _run(capsys, argv: list[str]) -> tuple[int | str, object]:
    """``(exit code, printed JSON)``: 0 when the command returns; a refusal's message string is its code."""
    try:
        cli.main(argv)
        code: int | str = 0
    except SystemExit as exc:
        code = 0 if exc.code is None else exc.code
    out = capsys.readouterr().out
    try:
        return code, json.loads(out) if out.strip() else None
    except ValueError:
        return code, out


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): _sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}


def _gen_file(tmp: Path, form: str = "record", name: str = "gen.json", **over) -> Path:
    """A generation-record file: ``record`` (a GenerationRecord as a spec stores it) or ``flags`` (the run fields)."""
    run = {**RUN, **over}
    p = tmp / name
    if form == "record":
        p.write_text(generation_record(**run).model_dump_json(indent=2), encoding="utf-8")
    else:
        p.write_text(json.dumps(run), encoding="utf-8")
    return p


@pytest.fixture()
def layout(tmp_path, monkeypatch):
    """A scratch repository (a git repository that ignores data/natural/) with the accepted synthetic task NP-90."""
    root = tmp_path / "repo"
    root.mkdir()
    init_git(root)
    nt = build_natural_task(root)
    calls = use_layout(monkeypatch, root)
    return nt, calls


def _proposals(nt: NaturalTask) -> list[dict]:
    """Proposals for NP-90: accepted ones at the issue, the comment and the reply, and ones each rule rejects or warns of."""
    ev = nt.event
    return [
        {"req_id": "R1", "statement": "add(None, 2) returns 2.", "kind": "change", "status": "explicit",
         "introduced_at": ev("issue"), "evidence": [{"event_id": ev("issue"), "quote": "It should return 2"}],
         "observable": "add(None, 2) == 2"},
        {"req_id": "R2", "statement": "add(2, None) returns 2.", "kind": "change", "status": "explicit",
         "introduced_at": ev("comment"), "evidence": [{"event_id": ev("comment"), "quote": "treat a missing second argument as 0 too"}],
         "observable": "add(2, None) == 2"},
        {"req_id": "R3", "statement": "add(None, None) returns 0.", "kind": "change", "status": "explicit",
         "introduced_at": ev("reply"), "evidence": [{"event_id": ev("reply"), "quote": "add(None, None) should return 0"}],
         "observable": "add(None, None) == 0"},
        {"req_id": "R4", "statement": "From the agent's PR body.", "kind": "change", "status": "inferred", "rationale": "the PR says so",
         "introduced_at": ev("pr"), "observable": "x"},  # not a user turn: natural rule
        {"req_id": "R5", "statement": "From a commit message.", "kind": "change", "status": "inferred", "rationale": "the commit",
         "introduced_at": ev("addressing"), "observable": "x"},  # a commit event: natural rule
        {"req_id": "R6", "statement": "Unknown event.", "kind": "change", "status": "inferred", "rationale": "r",
         "introduced_at": f"{nt.session_id}/review/1", "observable": "x"},
        {"req_id": "R7", "statement": "A quote the issue does not hold.", "kind": "change", "status": "explicit",
         "introduced_at": ev("issue"), "evidence": [{"event_id": ev("issue"), "quote": "words that are not there"}],
         "observable": "x"},  # explicit without supported evidence: rejected
        {"req_id": "R8", "statement": "Quotes the hunk.", "kind": "invariant", "status": "explicit", "introduced_at": ev("comment"),
         "evidence": [{"event_id": ev("hunk"), "quote": "if a is None"}], "observable": "x"},  # non-user evidence: warning
        {"req_id": "R9", "statement": "Evidence after its introduction.", "kind": "change", "status": "explicit",
         "introduced_at": ev("issue"), "evidence": [{"event_id": ev("comment"), "quote": "add(2, None) still raises"}],
         "observable": "x"},  # an error of validate_contract
        {"req_id": "R1", "statement": "A duplicate id.", "kind": "change", "status": "explicit", "introduced_at": ev("issue"),
         "evidence": [{"event_id": ev("issue"), "quote": "It should return 2"}]},
    ]


def _write(path: Path, data) -> Path:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _events(nt: NaturalTask, variant: str, dest: Path) -> Path:
    """The session-events record of ``variant`` (``tasks.render_session_events``), as a contract workspace holds it."""
    dest.write_text(tasks.render_session_events(tasks.session_for_task(nt.task_dir, nt.root), variant), encoding="utf-8")
    return dest


def _controlled_task(root: Path, tid: str = "FX-41") -> Path:
    """A minimal non-natural task under ``root/tasks`` with its base under ``root/snapshots`` and a reference candidate."""
    td, base = root / "tasks" / tid, root / "snapshots" / tid
    base.mkdir(parents=True)
    (base / "mod.py").write_text("X = 1\n", encoding="utf-8")
    patch = "--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = 2\n"
    ref = Candidate(candidate_id=f"{tid}-reference", task_id=tid, origin=CandidateOrigin.reference, split=Split.dev, patch=patch,
                    patch_sha256=sha256_text(patch), produced_by="fixture")
    dump(ref, td / "candidates" / f"{ref.candidate_id}.json")
    dump(Snapshot(snapshot_id=f"{tid}-base", task_id=tid, repo_url="https://example.invalid/fixture", base_commit="0" * 40,
                  fidelity=Fidelity.exact, file_manifest_sha256=manifest_sha256(manifest(base)), n_files=1), td / "snapshot.json")
    dump(TaskManifest(task_id=tid, family_id=tid, population=Population.fixture, status="draft", provenance="provenance.json",
                      snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture", commit="0" * 40),
                      snapshot="snapshot.json", env_requirements=[], candidates=[f"candidates/{ref.candidate_id}.json"]),
         td / "task.json")
    return td


def _chat_task(root: Path, tid: str = "CH-1") -> Path:
    """A natural:chat task beside the layout's task in ``data/natural/tasks``: its base under ``root/snapshots`` (the root
    that ``roots.snapshot_root`` gives every population but natural:pr-review), a frozen repo_tests verifier, and held-out
    candidates with the pilot's proposed labels."""
    td, base = root / "data" / "natural" / "tasks" / tid, root / "snapshots" / tid
    base.mkdir(parents=True)
    (base / "mod.py").write_text("X = 1\n", encoding="utf-8")
    kinds = {"reference": (CandidateOrigin.reference, Split.dev, "valid"),
             "alt": (CandidateOrigin.valid_alternative, Split.eval, "valid"),
             "nm": (CandidateOrigin.constructed_near_miss, Split.eval, "invalid"),
             "noop-eval": (CandidateOrigin.noop, Split.eval, "invalid")}
    for kind, (origin, split, label) in kinds.items():
        cid = f"{tid}-{kind}"
        patch = "" if origin == CandidateOrigin.noop else f"--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = 2  # {cid}\n"
        dump(Candidate(candidate_id=cid, task_id=tid, origin=origin, split=split, patch=patch, patch_sha256=sha256_text(patch),
                       produced_by="fixture", labels=[Label(value=label, labeler=PILOT_LABELER, labeler_kind=LabelerKind.model,
                                                            timestamp=T0)]),
             td / "candidates" / f"{cid}.json")
    tests = td / "verifiers" / "repo_tests" / "overlay" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_mod.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    spec = build_spec(verifier_id="repo_tests", task_id=tid, condition=VerifierCondition.repo_tests, test_dir=tests.parent,
                      task_dir=td, isolation=Isolation.in_process, check_ids=["tests/test_mod.py::test_x"])
    dump(freeze(spec, td), td / "verifiers" / "repo_tests" / "spec.json")
    dump(Snapshot(snapshot_id=f"{tid}-base", task_id=tid, repo_url="https://example.invalid/fixture", base_commit="0" * 40,
                  fidelity=Fidelity.exact, file_manifest_sha256=manifest_sha256(manifest(base)), n_files=1), td / "snapshot.json")
    dump(TaskManifest(task_id=tid, family_id=tid, population=Population.natural_chat, status="pending_review",
                      provenance="provenance.json", snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture",
                                                                                   commit="0" * 40),
                      snapshot="snapshot.json", env_requirements=[], verifiers=["verifiers/repo_tests/spec.json"],
                      candidates=[f"candidates/{tid}-{kind}.json" for kind in kinds]),
         td / "task.json")
    return td


# --------------------------------------------------------------------------- snapshot roots


def test_every_snapshot_use_finds_the_natural_base(layout, capsys, tmp_path):
    nt, calls = layout
    td = str(nt.task_dir)
    assert cli._snapshot_root(nt.task_dir) == nt.snapshot_dir.parent and not (nt.root / "snapshots").exists()
    # grade and audit grade against data/natural/snapshots/<id>
    code, out = _run(capsys, ["grade", td, "repo_tests", nt.candidate_id("reference")])
    assert code == 0 and out["outcome"] == "pass"
    code, out = _run(capsys, ["audit", td, "repo_tests"])
    assert code == 0 and sorted(out["dev_candidates"]) == [nt.candidate_id("noop-dev"), nt.candidate_id("reference")]
    assert calls and {c["base_dir"] for c in calls} == {nt.snapshot_dir} and {c["image"] for c in calls} == {IMAGE}
    # materialize applies the graded patch to the natural base (the reference's test file is a protected path)
    out_dir = tmp_path / "materialized"
    code, out = _run(capsys, ["materialize", td, nt.candidate_id("reference"), "--out", str(out_dir)])
    assert code == 0 and (out_dir / "fxnat" / "mod.py").read_text() == REFERENCE_MOD
    assert (out_dir / "tests" / "test_mod.py").read_text() == BASE_FILES["tests/test_mod.py"]
    # validate-task checks the natural base and shows what the gate reads
    code, out = _run(capsys, ["validate-task", td])
    assert code == 0 and out["snapshot_matches"] is True and out["acceptance_gate"]["refused"] is False
    assert out["verifiers"]["repo_tests"]["hash_matches"] is True


def test_add_candidate_from_a_state_directory_diffs_against_the_natural_base(layout, capsys, tmp_path):
    nt, _ = layout
    state = tmp_path / "attack" / "repo"
    shutil.copytree(nt.snapshot_dir, state)
    (state / "fxnat" / "mod.py").write_text(BASE_FILES["fxnat/mod.py"].replace("return a + b", "return a + b + 1"))
    gen = _gen_file(tmp_path)
    cid = nt.candidate_id("dev-attack-full_session-a1")
    code, out = _run(capsys, ["add-candidate", str(nt.task_dir), cid, "--origin", "dev_attack", "--split", "dev", "--state-dir",
                              str(state), "--produced-by", "attack:v1:full_session", "--label", "invalid", "--violates", "R1",
                              "--labeler", "attack:v1", "--generation-record", str(gen)])
    assert code == 0, code
    c = load(nt.task_dir / out["candidate"], Candidate)
    assert c.patch.count("+++ b/") == 1 and "+    return a + b + 1" in c.patch  # one changed file: the base was the natural one
    assert c.generation == generation_record(**RUN)
    assert out["candidate"] in load(nt.task_dir / "task.json", TaskManifest).candidates


def test_add_stratum_candidate_uses_the_natural_base(layout, capsys, tmp_path):
    nt, _ = layout
    state = tmp_path / "state"
    shutil.copytree(nt.snapshot_dir, state)
    (state / "fxnat" / "mod.py").write_text(REFERENCE_MOD)
    code, out = _run(capsys, ["add-stratum-candidate", str(nt.task_dir), "probe", nt.candidate_id("probe-1"), "--origin",
                              "observed_other", "--state-dir", str(state), "--produced-by", "fixture"])
    assert code == 0, code
    assert out["patch_lines"] > 0 and out["registered"]


def test_snapshot_refuses_a_natural_task_and_reconstruction_check_reads_its_record(layout, capsys):
    nt, _ = layout
    before = _tree_hashes(nt.root / "data")
    code, _ = _run(capsys, ["snapshot", str(nt.task_dir)])
    assert isinstance(code, str) and "snapshot refused" in code and "compile-pr-task" in code
    rec = nt.task_dir / RECORD
    sha = _sha256(rec)
    code, _ = _run(capsys, ["reconstruction-check", str(nt.task_dir), "--write"])
    assert isinstance(code, str) and "refused, nothing written" in code and _sha256(rec) == sha
    code, out = _run(capsys, ["reconstruction-check", str(nt.task_dir)])
    assert code == 0 and out["counts_for_the_gate"] is True and out["method"] == "reconstruction:pr-git:v1"
    assert [c["status"] for c in out["checks"]] == ["passed"] * 6
    assert _tree_hashes(nt.root / "data") == before and not (nt.root / "snapshots").exists()
    # The exit code is the gate's reading of the record: a stale record (the session changed) is a reason, exit 2, also
    # when it records a failed check; only a current record of a failed check, which the gate refuses, exits 1.
    session = nt.task_dir / "session.json"
    session.write_text(session.read_text() + "\n")
    code, out = _run(capsys, ["reconstruction-check", str(nt.task_dir)])
    assert code == 2 and "session_sha256" in out["problems"][0]
    data = json.loads(rec.read_text())
    data.update(status="failed", passed=False)
    rec.write_text(json.dumps(data))
    code, out = _run(capsys, ["reconstruction-check", str(nt.task_dir)])
    assert code == 2 and out["status"] == "failed" and out["failed"] is False and out["counts_for_the_gate"] is False
    assert not task_gate(nt.task_dir, nt.root).refusals
    data["inputs"] = npr.pr_current_inputs(nt.task_dir)
    rec.write_text(json.dumps(data))
    sha = _sha256(rec)
    code, out = _run(capsys, ["reconstruction-check", str(nt.task_dir)])
    assert code == 1 and out["failed"] is True and _sha256(rec) == sha
    assert any(r.startswith("reconstruction:") for r in task_gate(nt.task_dir, nt.root).refusals)
    # A malformed record ("checks": null) is printed, never a traceback, and its exit code is still the gate's reading.
    data.update(status="passed", passed=True, checks=None)
    rec.write_text(json.dumps(data))
    code, out = _run(capsys, ["reconstruction-check", str(nt.task_dir)])
    assert code == 0 and out["checks"] == [] and out["counts_for_the_gate"] is True
    data.update(status="failed", passed=False)
    rec.write_text(json.dumps(data))
    code, out = _run(capsys, ["reconstruction-check", str(nt.task_dir)])
    assert isinstance(out, dict) and out["counts_for_the_gate"] is False and code == (1 if out["failed"] else 2)


def test_the_recorded_tasks_resolve_where_their_population_keeps_them():
    """Read-only: the controlled tasks use snapshots/, the accepted natural tasks data/natural/snapshots."""
    for td in sorted((REPO / "tasks").glob("CS-0*")):
        assert cli._snapshot_root(td) == cli.SNAPSHOTS
    for td in sorted((REPO / "data" / "natural" / "tasks").glob("NP-*")) if (REPO / "data" / "natural" / "tasks").is_dir() else []:
        if (td / "task.json").is_file():
            assert cli._snapshot_root(td) == (REPO / "data" / "natural" / "snapshots").resolve()


# --------------------------------------------------------------------------- evaluate and images


def test_evaluate_writes_a_natural_run_to_a_git_ignored_root(layout, capsys, monkeypatch):
    nt, calls = layout
    builds: list = []
    use_layout(monkeypatch, nt.root, calls, builds=builds)
    code, _ = _run(capsys, ["freeze", str(nt.task_dir), "repo_tests"])
    assert code == 0
    out_root = nt.root / "data" / "natural" / "runs"
    code, out = _run(capsys, ["evaluate", str(nt.task_dir), "--run-id", "natural-test", "--pilot", "--conditions", "repo_tests",
                              "--out-root", str(out_root)])
    assert code == 0, code
    run = out_root / "natural-test"
    assert Path(out["run_dir"]) == run
    m = json.loads((run / "manifest.json").read_text())
    entry = m["tasks"][0]
    assert entry["task_dir"] == "data/natural/tasks/NP-90" and entry["image"] == IMAGE and entry["image_id"] == IMAGE_ID
    assert set(entry["candidates"]) == {nt.candidate_id(k) for k in ("reference", "pre-review", "noop-eval")}
    assert {c["base_dir"] for c in calls} == {nt.snapshot_dir} and len(calls) == 3
    assert len((run / "results.jsonl").read_text().splitlines()) == 3
    assert not (nt.root / "results").exists()
    assert builds == []  # the recorded image was looked up, not built


def test_a_controlled_run_records_its_task_dir_too(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    td = _controlled_task(root)
    builds: list = []
    use_layout(monkeypatch, root, builds=builds)
    code, _ = _run(capsys, ["evaluate", str(td), "--run-id", "r", "--pilot"])
    assert code == 0, code
    m = json.loads((root / "results" / "runs" / "r" / "manifest.json").read_text())
    assert m["tasks"][0]["task_dir"] == "tasks/FX-41"
    assert builds == [()]  # a controlled task's image is built when it is missing, as before


def _refused_run(capsys, nt: NaturalTask, *extra: str, out_root: Path | None = None, freeze: bool = True) -> str:
    if freeze and not load(nt.task_dir / "verifiers" / "repo_tests" / "spec.json", VerifierSpec).frozen:
        assert _run(capsys, ["freeze", str(nt.task_dir), "repo_tests"])[0] == 0
    out_root = out_root or nt.root / "data" / "natural" / "runs"
    code, _ = _run(capsys, ["evaluate", str(nt.task_dir), "--run-id", "refused", "--pilot", "--conditions", "repo_tests",
                            "--out-root", str(out_root), *extra])
    assert isinstance(code, str) and "refused" in code, code
    assert not out_root.exists() and not (nt.root / "results").exists()  # nothing written, not even the out root
    return code


def test_the_pilot_tasks_pass_the_checks_before_a_run(tmp_path, monkeypatch):
    """Read-only: CS-01..04 find their bases under snapshots/, their frozen verifiers (the sidecar labelers included) are
    unchanged, and the image ids their last recorded run used are the ids their snapshot.json records, so evaluate's
    image check refuses none of them."""
    run = REPO / "results" / "runs" / "pilot-v0.3.5-regrade" / "manifest.json"
    tasks_ = sorted((REPO / "tasks").glob("CS-0*"))
    if not (run.is_file() and tasks_ and (REPO / "snapshots" / "CS-01").is_dir()):
        pytest.skip("the pilot tasks, their snapshots or the recorded run are not in this checkout")
    used = {t["task_id"]: (t["image"], t["image_id"]) for t in json.loads(run.read_text())["tasks"]}
    by_reqs = {tuple(sorted(set(load(td / "task.json", TaskManifest).env_requirements))): used[td.name] for td in tasks_}
    monkeypatch.setattr(evaluate, "build_env_image", lambda reqs, cache: by_reqs[tuple(sorted(set(reqs)))])
    monkeypatch.setattr(evaluate, "local_image_id", lambda tag: pytest.fail("a controlled task's image is built as before"))
    roots_by_task = {td.name: cli._snapshot_root(td) for td in tasks_}
    assert set(roots_by_task.values()) == {cli.SNAPSHOTS}
    images = evaluate.check_inputs(tasks_, snapshot_root=roots_by_task, cache_dir=tmp_path / "cache", extra_verifiers=True)
    assert images == {td.name: used[td.name] for td in tasks_}


def test_a_refused_evaluate_leaves_no_directory(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    init_git(root)
    builds: list = []
    # The gate: S10 not passed.
    nt = build_natural_task(root, "NP-91", s10_outcome="built")
    use_layout(monkeypatch, root, builds=builds)
    assert "S10 outcome" in _refused_run(capsys, nt)
    # The snapshot: a modified base.
    nt = build_natural_task(root, "NP-92")
    (nt.snapshot_dir / "fxnat" / "mod.py").write_text("changed\n")
    assert "does not match its recorded manifest" in _refused_run(capsys, nt)
    # A verifier that is not frozen.
    nt = build_natural_task(root, "NP-93")
    assert "is not frozen" in _refused_run(capsys, nt, freeze=False)
    # The image: under the recorded tag another id than the recorded one (a rebuilt image), no such image on the host,
    # no id recorded, or another tag recorded than the task's pins give. A natural task's image is never built.
    nt = build_natural_task(root, "NP-94")
    use_layout(monkeypatch, root, local={IMAGE: "sha256:" + "1" * 64}, builds=builds)
    assert "snapshot.json records" in _refused_run(capsys, nt)
    use_layout(monkeypatch, root, local={IMAGE: None}, builds=builds)
    assert "is not on this host" in _refused_run(capsys, nt)
    use_layout(monkeypatch, root, builds=builds)
    nt = build_natural_task(root, "NP-95", image_id=None)
    assert "records no environment.image_id" in _refused_run(capsys, nt)
    nt = build_natural_task(root, "NP-97")
    snap = json.loads((nt.task_dir / "snapshot.json").read_text())
    snap["environment"]["image"] = "tc-env:" + "0" * 16
    (nt.task_dir / "snapshot.json").write_text(json.dumps(snap))
    assert "is not the one its S10 step recorded" in _refused_run(capsys, nt)
    assert builds == []
    # A tracked out root (inside the repository, not ignored), one outside the repository, and session or third-party
    # locations.
    nt = build_natural_task(root, "NP-96")
    assert "git does not ignore it" in _refused_run(capsys, nt, out_root=root / "results" / "runs")
    assert "outside the repository" in _refused_run(capsys, nt, out_root=tmp_path / "elsewhere" / "runs")
    assert "Claude session" in _refused_run(capsys, nt, out_root=SESSION_TMP / "tc-natural-test-never-written")


def test_a_natural_task_is_graded_only_in_its_recorded_image(layout, capsys, monkeypatch):
    """grade, audit and the sandbox commands look a natural task's image up and never build it (build_env_image would
    rebuild a pruned image and give the rebuilt one the recorded tag): a missing image refuses them, and so does an image
    under the recorded tag with another id than the recorded one. The tag is checked on the records first."""
    nt, calls = layout
    td = str(nt.task_dir)
    builds: list = []
    rebuilt = "sha256:" + "2" * 64
    commands = (["grade", td, "repo_tests", nt.candidate_id("reference")], ["audit", td, "repo_tests"],
                ["sandbox-python", td, str(nt.snapshot_dir), "-c", "pass"], ["sandbox-pytest", td, str(nt.snapshot_dir)])
    for local, why in (({IMAGE: None}, "is not on this host"), ({IMAGE: rebuilt}, f"has the id {rebuilt}")):
        use_layout(monkeypatch, nt.root, calls, local=local, builds=builds)
        for argv in commands:
            code, _ = _run(capsys, argv)
            assert isinstance(code, str) and code.startswith(f"{argv[0]} refused:") and why in code, (argv, code)
    assert builds == [] and calls == []
    looked_up: list[str] = []
    monkeypatch.setattr(evaluate, "local_image_id", lambda tag: looked_up.append(tag) or IMAGE_ID)
    snap = json.loads((nt.task_dir / "snapshot.json").read_text())
    snap["environment"]["image"] = "tc-env:" + "0" * 16
    (nt.task_dir / "snapshot.json").write_text(json.dumps(snap))
    code, _ = _run(capsys, commands[0])
    assert isinstance(code, str) and "is not the one its S10 step recorded" in code and looked_up == [] and calls == []


def test_the_out_location_rules(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git(root)
    assert private_location_problem(root / "data" / "natural" / "runs" / "r", root) is None
    assert private_location_problem(tmp_path / "elsewhere", root) is None  # outside every git work tree
    assert "does not ignore" in private_location_problem(root / "results" / "runs", root)
    assert "does not ignore" in private_location_problem(root, root)
    assert "third-party data" in private_location_problem(EXT / "workspaces" / "x", root)
    assert "Claude session" in private_location_problem(SESSION_TMP / "x", root)
    assert "Claude session" in private_location_problem(Path.home() / ".claude" / "projects" / "x", root)
    plain = tmp_path / "not-git"
    plain.mkdir()
    assert "does not ignore" in private_location_problem(plain / "data" / "natural" / "runs", plain)  # git cannot answer
    assert evaluate.git_ignored(root / "data" / "natural" / "x", root) and not evaluate.git_ignored(tmp_path / "x", root)
    # A natural run directory: only inside the repository.
    assert private_location_problem(root / "data" / "natural" / "runs" / "r", root, inside_repo=True) is None
    assert "outside the repository" in private_location_problem(tmp_path / "elsewhere", root, inside_repo=True)
    # Every git work tree that holds the path must ignore it: another repository, and one nested in an ignored directory.
    other = tmp_path / "other"
    other.mkdir()
    init_git(other)
    assert "git work tree" in private_location_problem(other / "results" / "x", root)
    assert private_location_problem(other / "data" / "natural" / "x", root) is None
    nested = root / "data" / "natural" / "nested"
    nested.mkdir(parents=True)
    init_git(nested)
    assert evaluate.git_ignored(nested / "out", root) and "git work tree" in private_location_problem(nested / "out", root)
    assert evaluate.git_work_trees(nested / "out") == [nested, root]


def test_a_natural_run_or_packet_in_a_linked_work_tree_is_refused(tmp_path, monkeypatch, capsys):
    """A linked work tree of the repository shares its history, so a path that it does not ignore is refused although it
    lies outside the repository: evaluate's run directory and review-packet's --out, also when typed from that work tree."""
    root = tmp_path / "repo"
    root.mkdir()
    init_git(root)
    (root / "results" / "runs").mkdir(parents=True)
    (root / "results" / "runs" / "README").write_text("tracked run records\n")
    git(root, "add", ".gitignore", "results")
    git(root, "commit", "-q", "--no-verify", "-m", "tracked results")
    nt = build_natural_task(root)
    use_layout(monkeypatch, root)
    wt = tmp_path / "analysis-wt"
    git(root, "worktree", "add", "-q", "--detach", str(wt))
    assert (wt / ".git").is_file() and (wt / "results" / "runs" / "README").is_file()
    runs = wt / "results" / "runs"
    assert "git work tree" in private_location_problem(runs / "natural-test", root)
    assert private_location_problem(wt / "data" / "natural" / "runs" / "x", root) is None  # ignored there
    assert "outside the repository" in private_location_problem(wt / "data" / "natural" / "runs" / "x", root, inside_repo=True)
    assert _run(capsys, ["freeze", str(nt.task_dir), "repo_tests"])[0] == 0
    monkeypatch.chdir(wt)
    for out_root in (str(runs), "results/runs"):
        code, _ = _run(capsys, ["evaluate", str(nt.task_dir), "--run-id", "natural-test", "--pilot", "--conditions",
                                "repo_tests", "--out-root", out_root])
        assert isinstance(code, str) and "refused, nothing written" in code and not (runs / "natural-test").exists(), code
    key = tmp_path / "key.json"
    code, _ = _run(capsys, ["review-packet", str(nt.task_dir), "--out", str(runs / "packet"), "--key", str(key), "--seed", "1"])
    assert isinstance(code, str) and "git work tree" in code and not (runs / "packet").exists() and not key.exists()
    assert sorted(p.name for p in runs.iterdir()) == ["README"]


def test_run_matrix_refuses_before_writing_and_takes_one_root_per_task(layout, tmp_path):
    nt, _ = layout
    kw = {"run_id": "r", "cache_dir": tmp_path / "cache", "repo_root": nt.root, "pilot": True, "conditions": ["repo_tests"],
          "require_frozen": False}
    with pytest.raises(RunRefused, match="no snapshot root given"):
        evaluate.run_matrix([nt.task_dir], out_root=nt.root / "data" / "natural" / "runs", snapshot_root={"other": tmp_path}, **kw)
    with pytest.raises(RunRefused, match="not built at"):
        evaluate.run_matrix([nt.task_dir], out_root=nt.root / "data" / "natural" / "runs", snapshot_root=tmp_path / "none", **kw)
    assert not (nt.root / "data" / "natural" / "runs").exists()
    out = evaluate.run_matrix([nt.task_dir], out_root=nt.root / "data" / "natural" / "runs",
                              snapshot_root={nt.task_id: nt.snapshot_dir.parent}, **kw)
    assert (out / "manifest.json").is_file()


def test_the_natural_sub_populations_are_never_pooled_silently(layout, capsys):
    """natural:pr-review (AIDev) and natural:chat (Trace Commons) are populations of their own (protocol v0.8 §16.3), also
    in a run that passes evaluate's natural rules: the gate (S10 passed, S11 in the committed index), the recorded image
    and a git-ignored run directory (tests/test_population_strata.py checks this on hand-written tasks that these rules
    now refuse)."""
    nt, _ = layout
    chat = _chat_task(nt.root)
    assert _run(capsys, ["freeze", str(nt.task_dir), "repo_tests"])[0] == 0
    code, out = _run(capsys, ["evaluate", str(nt.task_dir), str(chat), "--run-id", "r-subpops", "--pilot", "--conditions",
                              "repo_tests", "--out-root", str(nt.root / "data" / "natural" / "runs")])
    assert code == 0, code
    run = Path(out["run_dir"])
    with pytest.raises(MixedPopulations, match=r"2 populations \(natural:chat: CH-1; natural:pr-review: NP-90\)"):
        analyze(run, nt.tasks_root, allow_proposed=True, n_boot=50)
    code, _ = _run(capsys, ["analyze", str(run), "--tasks-root", str(nt.tasks_root), "--allow-proposed-labels"])
    assert isinstance(code, str) and "--pool-populations" in code and not (run / "analysis.json").exists()
    a = analyze(run, nt.tasks_root, allow_proposed=True, n_boot=50, pool_populations=True)
    assert {p: g["tasks"] for p, g in a["by_population"].items()} == {"natural:chat": ["CH-1"], "natural:pr-review": ["NP-90"]}


# --------------------------------------------------------------------------- tasks root, out guards


def test_analyze_report_and_merge_reviews_take_a_tasks_root(tmp_path, monkeypatch, capsys):
    from tracecontract import analysis, report, review

    seen: dict[str, Path] = {}

    def fake_analyze(run, tasks_root, **kw):
        seen["analyze"] = tasks_root
        return {"meta": {}, "conditions": {}}

    def fake_report(run, tasks_root, repo_root, out):
        seen["report"] = tasks_root
        return out

    def fake_merge(files, key, tasks_root, **kw):
        seen["merge"] = tasks_root
        return {}

    monkeypatch.setattr(analysis, "analyze", fake_analyze)
    monkeypatch.setattr(report, "build_report", fake_report)
    monkeypatch.setattr(review, "merge_labels", fake_merge)
    monkeypatch.setattr(cli, "REPO", tmp_path)
    nat = tmp_path / "data" / "natural" / "tasks"
    assert _run(capsys, ["analyze", str(tmp_path / "run"), "--tasks-root", str(nat)])[0] == 0
    assert _run(capsys, ["report", str(tmp_path / "run"), "--out", str(tmp_path / "r.html"), "--tasks-root", str(nat)])[0] == 0
    assert _run(capsys, ["merge-reviews", str(tmp_path / "l.json"), "--key", str(tmp_path / "k.json"), "--tasks-root", str(nat)])[0] == 0
    assert seen == {"analyze": nat.resolve(), "report": nat.resolve(), "merge": nat.resolve()}
    assert _run(capsys, ["analyze", str(tmp_path / "run")])[0] == 0 and seen["analyze"] == tmp_path / "tasks"  # the default


def test_export_gen_workspace_refuses_natural_tasks_and_unsafe_outs(layout, capsys, tmp_path, monkeypatch):
    nt, _ = layout
    code, _ = _run(capsys, ["export-gen-workspace", str(nt.task_dir), "--out", str(tmp_path / "ws-nat")])
    assert isinstance(code, str) and "make_agent_workspace" in code and not (tmp_path / "ws-nat").exists()
    td = _controlled_task(nt.root)
    for out, why in ((nt.root / "workspaces" / "w", "git does not ignore"), (EXT / "tc-ws-never-written", "third-party"),
                     (SESSION_TMP / "tc-ws-never-written", "Claude session")):
        code, _ = _run(capsys, ["export-gen-workspace", str(td), "--out", str(out), "--with-reference-patch"])
        assert isinstance(code, str) and why in code and not out.exists()
    # An existing directory that it did not write is refused and left as it was.
    existing = tmp_path / "theirs"
    (existing / "tests").mkdir(parents=True)
    (existing / "tests" / "test_x.py").write_text("agent's work\n")
    before = _tree_hashes(existing)
    code, _ = _run(capsys, ["export-gen-workspace", str(td), "--out", str(existing), "--with-reference-patch"])
    assert isinstance(code, str) and "not an empty directory" in code and _tree_hashes(existing) == before
    # A new directory (or an empty one) is written: the base and the graded part of the reference diff.
    for out in (tmp_path / "new-ws", tmp_path / "empty-ws"):
        if out.name == "empty-ws":
            out.mkdir()
        code, res = _run(capsys, ["export-gen-workspace", str(td), "--out", str(out), "--with-reference-patch"])
        assert code == 0 and res["files"] == ["base", "reference.diff"] and (out / "base" / "mod.py").read_text() == "X = 1\n"
    # A failure while writing removes only what this call wrote: a new --out with the parent directories it created, or
    # what it wrote into an empty --out, which stays (empty).
    real_copytree = shutil.copytree

    def copy_then_fail(src, dst, **kw):
        real_copytree(src, dst, **kw)
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", copy_then_fail)
    (tmp_path / "kept-parent").mkdir()
    deep = tmp_path / "kept-parent" / "new" / "a" / "ws"
    with pytest.raises(OSError):
        cli.main(["export-gen-workspace", str(td), "--out", str(deep)])
    assert (tmp_path / "kept-parent").is_dir() and not (tmp_path / "kept-parent" / "new").exists()
    empty = tmp_path / "empty-again"
    empty.mkdir()
    with pytest.raises(OSError):
        cli.main(["export-gen-workspace", str(td), "--out", str(empty), "--with-reference-patch"])
    assert empty.is_dir() and not any(empty.iterdir())


def test_review_packet_guards_its_out_and_one_snapshot_root(layout, capsys, tmp_path):
    nt, _ = layout
    td = _controlled_task(nt.root)
    key = tmp_path / "key.json"
    code, _ = _run(capsys, ["review-packet", str(nt.task_dir), "--out", str(nt.root / "packet"), "--key", str(key), "--seed", "1"])
    assert isinstance(code, str) and "git does not ignore" in code and not (nt.root / "packet").exists()
    code, _ = _run(capsys, ["review-packet", str(nt.task_dir), str(td), "--out", str(tmp_path / "packet"), "--key", str(key),
                            "--seed", "1"])
    assert isinstance(code, str) and "2 roots" in code and not (tmp_path / "packet").exists() and not key.exists()


def test_render_session_and_materialize_keep_a_natural_task_out_of_git(layout, capsys):
    """The thread text and the upstream code of a natural task never go where git could commit them, and a rendered
    thread never overwrites a file; a controlled task keeps the earlier rules."""
    nt, _ = layout
    td = str(nt.task_dir)
    tracked = nt.root / "docs" / "np90.txt"
    code, _ = _run(capsys, ["render-session", td, "--out", str(tracked)])
    assert isinstance(code, str) and "render-session refused, nothing written" in code and "git does not ignore" in code
    assert not tracked.exists()
    private = nt.root / "data" / "natural" / "renders" / "np90.txt"
    private.parent.mkdir(parents=True)
    code, _ = _run(capsys, ["render-session", td, "--out", str(private)])
    assert code == 0 and COMMENT_TEXT in private.read_text() and "FX-AGENT" not in private.read_text()
    before = _sha256(private)
    code, _ = _run(capsys, ["render-session", td, "--out", str(private), "--first-prompt-only"])
    assert isinstance(code, str) and "exists" in code and _sha256(private) == before
    state = nt.root / "tasks" / "np90-state"
    code, _ = _run(capsys, ["materialize", td, nt.candidate_id("reference"), "--out", str(state)])
    assert isinstance(code, str) and "materialize refused, nothing written" in code and not state.exists()
    ctl = _controlled_task(nt.root)
    code, _ = _run(capsys, ["materialize", str(ctl), "FX-41-reference", "--out", str(nt.root / "tasks" / "fx-state")])
    assert code == 0 and (nt.root / "tasks" / "fx-state" / "mod.py").read_text() == "X = 2\n"


# --------------------------------------------------------------------------- generation records


def test_generation_record_files_of_both_forms_round_trip(tmp_path):
    for form in ("record", "flags"):
        rec, problems = cli._read_generation_record(str(_gen_file(tmp_path, form, name=f"{form}.json")))
        assert problems == [] and rec == generation_record(**RUN)
    rec, problems = cli._read_generation_record(str(_gen_file(tmp_path, "flags", name="bad.json", config="claude-x")))
    assert rec is None and "configuration label" in problems[0]
    (tmp_path / "unknown.json").write_text(json.dumps({**RUN, "model": "x"}))
    assert "unknown keys" in cli._read_generation_record(str(tmp_path / "unknown.json"))[1][0]
    (tmp_path / "list.json").write_text("[]")
    assert "JSON object" in cli._read_generation_record(str(tmp_path / "list.json"))[1][0]
    incomplete = generation_record(**RUN).model_copy(update={"run_id": "unrecorded"})
    (tmp_path / "incomplete.json").write_text(incomplete.model_dump_json())
    rec, problems = cli._read_generation_record(str(tmp_path / "incomplete.json"))
    assert rec == incomplete and problems and problems[0].startswith("run id missing")


def test_contracts_and_candidates_keep_a_generation_record_and_omit_none():
    gen = generation_record(**RUN)
    c = TaskContract(contract_id="T-full_session", task_id="T", session_id="s", variant=ContractVariant.full_session,
                     requirements=[], created_by="model:config-A:contract:v1", created_at=RUN["ended_at"])
    assert "generation" not in c.model_dump_json() and "generation" not in c.model_dump(mode="json")
    with_gen = c.model_copy(update={"generation": gen})
    again = TaskContract.model_validate_json(with_gen.model_dump_json())
    assert again.generation == gen and again == with_gen
    patch = "--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-X = 1\n+X = 2\n"
    cand = Candidate(candidate_id="T-eval-nm-1", task_id="T", origin=CandidateOrigin.constructed_near_miss, split=Split.eval,
                     patch=patch, patch_sha256=sha256_text(patch), produced_by="nearmiss:v1")
    assert "generation" not in cand.model_dump_json()
    with_gen = cand.model_copy(update={"generation": gen})
    assert Candidate.model_validate_json(with_gen.model_dump_json()).generation == gen
    assert isinstance(gen, GenerationRecord)
    # Only a constructed candidate carries one, as only a fresh attempt carries an attempt record.
    for origin in (CandidateOrigin.noop, CandidateOrigin.reference, CandidateOrigin.natural_pre_review,
                   CandidateOrigin.fresh_attempt, CandidateOrigin.tamper_probe):
        raw = json.loads(with_gen.model_dump_json()) | {"origin": origin.value}
        with pytest.raises(ValueError, match="only a constructed candidate"):
            Candidate.model_validate(raw)


def test_make_contract_and_add_candidate_refuse_a_natural_task_without_a_complete_record(layout, capsys, tmp_path):
    nt, _ = layout
    props = _write(tmp_path / "proposals.json", {"requirements": _proposals(nt)[:3]})
    before = _tree_hashes(nt.task_dir)
    base = ["make-contract", str(nt.task_dir), "--variant", "full_session", "--proposals", str(props), "--proposer",
            "model:config-A:contract:v1"]
    bad = _gen_file(tmp_path, "flags", name="bad.json", wall_s=None)
    for extra in ([], ["--generation-record", str(bad)], ["--generation-record", str(tmp_path / "missing.json")]):
        code, _ = _run(capsys, base + extra)
        assert isinstance(code, str) and "make-contract refused, nothing written" in code
        assert _tree_hashes(nt.task_dir) == before
    code, out = _run(capsys, base + ["--generation-record", str(_gen_file(tmp_path))])
    assert code == 0 and out["contract"] == "contracts/full_session.json"
    c = load(nt.task_dir / "contracts" / "full_session.json", TaskContract)
    assert c.generation == generation_record(**RUN) and [r.req_id for r in c.requirements] == ["R1", "R2", "R3"]
    assert load(nt.task_dir / "task.json", TaskManifest).contracts == {"full_session": "contracts/full_session.json"}
    # add-candidate: a constructed candidate of a natural task needs one; a record is refused for other origins.
    patch = tmp_path / "p.diff"
    patch.write_text("")
    before = _tree_hashes(nt.task_dir)
    args = ["add-candidate", str(nt.task_dir), nt.candidate_id("eval-alt-1"), "--origin", "valid_alternative", "--split", "eval",
            "--patch-file", str(patch), "--produced-by", "altimpl:v1:reference:eval:1", "--label", "valid"]
    for extra in ([], ["--generation-record", str(bad)]):
        code, _ = _run(capsys, args + extra)
        assert isinstance(code, str) and "add-candidate refused, nothing written" in code and _tree_hashes(nt.task_dir) == before
    code, _ = _run(capsys, ["add-candidate", str(nt.task_dir), nt.candidate_id("probe"), "--origin", "tamper_probe", "--split",
                            "dev", "--patch-file", str(patch), "--produced-by", "x", "--generation-record", str(_gen_file(tmp_path))])
    assert isinstance(code, str) and "kept only with a constructed candidate" in code and _tree_hashes(nt.task_dir) == before
    code, out = _run(capsys, args + ["--generation-record", str(_gen_file(tmp_path, "flags", name="flags.json"))])
    assert code == 0 and load(nt.task_dir / out["candidate"], Candidate).generation == generation_record(**RUN)


def test_a_controlled_task_needs_no_record_but_keeps_a_given_one(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    td = _controlled_task(root)
    use_layout(monkeypatch, root)
    patch = tmp_path / "p.diff"
    patch.write_text("")
    code, out = _run(capsys, ["add-candidate", str(td), "FX-41-eval-nm-1", "--origin", "constructed_near_miss", "--split", "eval",
                              "--patch-file", str(patch), "--produced-by", "nearmiss:v1"])
    assert code == 0 and load(td / out["candidate"], Candidate).generation is None
    raw = (td / out["candidate"]).read_text()
    assert "generation" not in raw and "attempt" not in raw
    code, out = _run(capsys, ["add-candidate", str(td), "FX-41-eval-nm-2", "--origin", "constructed_near_miss", "--split", "eval",
                              "--patch-file", str(patch), "--produced-by", "nearmiss:v1", "--generation-record", str(_gen_file(tmp_path))])
    assert code == 0 and load(td / out["candidate"], Candidate).generation == generation_record(**RUN)


def test_build_verifier_takes_the_record_from_a_file(layout, capsys, tmp_path):
    nt, _ = layout
    tests = nt.task_dir / "verifiers" / "full_plain" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_a.py").write_text('from tc_sandbox import run_python\n\nCHECK_REQUIREMENTS = {"test_add": ["R1"]}\n\n\n'
                                     'def test_add():\n    r = run_python("import fxnat; result = fxnat.add(None, 2)")\n'
                                     '    assert r.ok and r.value == 2\n')
    base = ["build-verifier", str(nt.task_dir), "full_plain", "--condition", "full_plain"]
    spec = nt.task_dir / "verifiers" / "full_plain" / "spec.json"
    code, _ = _run(capsys, base + ["--generation-record", str(_gen_file(tmp_path, "flags", name="bad.json", turns=None, tokens=None))])
    assert isinstance(code, str) and "nothing recorded" in code and not spec.exists()
    code, _ = _run(capsys, base + ["--generation-record", str(_gen_file(tmp_path)), "--gen-run-id", "x"])
    assert isinstance(code, str) and "not both" in code and not spec.exists()
    code, out = _run(capsys, base + ["--generation-record", str(_gen_file(tmp_path))])
    assert code == 0 and out["generation_record"] == "complete"
    assert load(spec, VerifierSpec).generation == generation_record(**RUN)


# --------------------------------------------------------------------------- make-contract and check-proposals


def test_a_non_user_introduced_at_is_rejected_for_natural_tasks_only():
    ev = [Event(event_id=f"s/{i}", session_id="s", index=i, kind=k, author=Author.unknown, text=t, source=SourceRef(path="x", line=i))
          for i, (k, t) in enumerate([(EventKind.user_prompt, "Please add f."), (EventKind.assistant_text, "I added f and g.")])]
    s = Session(session_id="s", population=Population.fixture, source="fixture", source_format="fixture", trace_sha256=SHA,
                events=ev)
    prop = [{"req_id": "R1", "statement": "g exists.", "status": "inferred", "rationale": "the agent added it",
             "introduced_at": "s/1", "observable": "g()"}]
    assert [r.req_id for r in requirements_from_proposals(s, prop, proposer="x").requirements] == ["R1"]  # as before
    out = requirements_from_proposals(s, prop, proposer="x", user_turns_only=True)
    assert not out.requirements and out.rejected[0]["reason"] == NOT_A_USER_TURN
    out = check_proposals(s, prop, proposer="x", variant=ContractVariant.full_session, natural=False)
    assert [r.req_id for r in out.requirements] == ["R1"] and not out.rejected


def test_make_contract_rejects_non_user_events_and_warns_for_a_reference_without_the_correction(layout, capsys, tmp_path):
    nt, _ = layout
    gen = _gen_file(tmp_path)
    props = _write(tmp_path / "p.json", _proposals(nt))
    code, out = _run(capsys, ["make-contract", str(nt.task_dir), "--variant", "full_session", "--proposals", str(props),
                              "--proposer", "model:config-A:contract:v1", "--generation-record", str(gen)])
    assert code == 0
    reasons = {r["proposal"]["req_id"] + (":dup" if "duplicate" in r["reason"] else ""): r["reason"] for r in out["rejected_proposals"]}
    assert reasons == {"R4": NOT_A_USER_TURN, "R5": NOT_A_USER_TURN, "R6": NOT_A_USER_TURN,
                       "R7": "explicit requirement without supported evidence", "R1:dup": "duplicate req_id R1"}
    assert any(w.startswith("R8: evidence from non-user event") for w in out["warnings"])
    assert [e["code"] for e in out["errors"]] == ["evidence_after_introduction"]
    assert not any(w.startswith("reference:") for w in out["warnings"])
    # The reference variant warns when no scored active requirement is introduced at the comment or a reply.
    only_issue = _write(tmp_path / "issue.json", _proposals(nt)[:1])
    code, out = _run(capsys, ["make-contract", str(nt.task_dir), "--variant", "reference", "--proposals", str(only_issue),
                              "--proposer", "model:config-A:refcontract:v1", "--generation-record", str(gen)])
    warn = [w for w in out["warnings"] if w.startswith("reference:")]
    assert code == 0 and len(warn) == 1 and nt.event("comment") in warn[0] and nt.event("reply") in warn[0]
    assert warn[0] in load(nt.task_dir / "contracts" / "reference.json", TaskContract).notes
    code, out = _run(capsys, ["make-contract", str(nt.task_dir), "--variant", "reference", "--proposals", str(props),
                              "--proposer", "model:config-A:refcontract:v1", "--generation-record", str(gen)])
    assert code == 0 and not any(w.startswith("reference:") for w in out["warnings"])


def _same(a: dict, b: dict) -> None:
    for key in ("rejected_proposals", "warnings", "errors"):
        assert a[key] == b[key], key


def test_make_contract_checks_a_natural_task_on_the_events_its_proposer_saw(layout, capsys, tmp_path):
    """A proposal that names an event the variant's proposer was not shown is rejected by make-contract as by
    check-proposals: the review comment for initial_only, and a quote from the agent's PR body for every variant. The
    recorded contract validates on the whole session as on the events shown."""
    nt, _ = layout
    gen = _gen_file(tmp_path)
    ev = nt.event
    at_comment = _proposals(nt)[1]
    pr_quote = {"req_id": "R10", "statement": "A missing value counts as zero.", "kind": "change", "status": "explicit",
                "introduced_at": ev("comment"), "evidence": [{"event_id": ev("pr"), "quote": "Treat None as zero"}],
                "observable": "add(None, 1) == 1"}
    cases = {"initial_only": ([_proposals(nt)[0], at_comment], {"R2": NOT_A_USER_TURN}),
             "full_session": ([_proposals(nt)[0], at_comment, pr_quote], {"R10": "explicit requirement without supported evidence"}),
             "reference": ([_proposals(nt)[0], at_comment, pr_quote], {"R10": "explicit requirement without supported evidence"})}
    whole = tasks.session_for_task(nt.task_dir, nt.root)
    for variant, (props, rejected) in cases.items():
        p = _write(tmp_path / f"p-{variant}.json", props)
        code, made = _run(capsys, ["make-contract", str(nt.task_dir), "--variant", variant, "--proposals", str(p),
                                   "--proposer", "model:config-A:contract:v1", "--generation-record", str(gen)])
        assert code == 0, code
        assert {r["proposal"]["req_id"]: r["reason"] for r in made["rejected_proposals"]} == rejected, variant
        assert made["errors"] == [], variant  # no initial_only_leak: the comment's requirement was never recorded
        contract = load(nt.task_dir / "contracts" / f"{variant}.json", TaskContract)
        assert ev("pr") not in {sp.event_id for r in contract.requirements for sp in r.evidence}
        assert [i.__dict__ for i in contract_mod.validate_contract(contract, whole) if i.severity == "error"] == made["errors"]
        code, out = _run(capsys, ["check-proposals", str(_events(nt, variant, tmp_path / f"ev-{variant}.json")), str(p)])
        assert code == 1 and out["variant"] == variant
        _same(out, made)


def test_check_proposals_refuses_another_variant_than_the_records(layout, capsys, tmp_path):
    nt, _ = layout
    events = _events(nt, "initial_only", tmp_path / "ev.json")
    props = _write(tmp_path / "p.json", _proposals(nt)[:1])
    code, _ = _run(capsys, ["check-proposals", str(events), str(props), "--variant", "full_session"])
    assert isinstance(code, str) and "is not the variant of the session-events record" in code
    code, out = _run(capsys, ["check-proposals", str(events), str(props), "--variant", "initial_only"])
    assert code == 0 and out["variant"] == "initial_only"
    session = tmp_path / "session.json"
    shutil.copyfile(nt.task_dir / "session.json", session)
    code, _ = _run(capsys, ["check-proposals", str(session), str(props)])
    assert isinstance(code, str) and "give --variant" in code


def test_check_proposals_prints_what_make_contract_would_and_writes_nothing(layout, capsys, tmp_path):
    nt, _ = layout
    gen = _gen_file(tmp_path)
    work = tmp_path / "agent-ws"
    work.mkdir()
    props = _write(work / "proposals.json", {"requirements": _proposals(nt)})
    issue_only = _write(work / "issue_only.json", _proposals(nt)[:1])
    shutil.copyfile(nt.task_dir / "session.json", work / "session.json")
    made = {}
    for variant, p in (("full_session", props), ("reference", props), ("reference", issue_only), ("initial_only", props)):
        code, made[(variant, p.name)] = _run(capsys, ["make-contract", str(nt.task_dir), "--variant", variant, "--proposals", str(p),
                                                      "--proposer", "model:config-A:contract:v1", "--generation-record", str(gen)])
        assert code == 0
    before = _tree_hashes(tmp_path)
    # The whole session record (a task's session.json), with the variant given.
    for (variant, name), expected in made.items():
        code, out = _run(capsys, ["check-proposals", str(work / "session.json"), str(work / name), "--variant", variant])
        _same(out, expected)
        assert out["natural_pr_review_rules"] is True and out["written"] is False
        assert code == (1 if expected["rejected_proposals"] or expected["errors"] else 0)
    code, out = _run(capsys, ["check-proposals", str(work / "session.json"), str(issue_only), "--variant", "reference"])
    assert set(out["correction_event_ids"]) == {nt.event("comment"), nt.event("reply")}
    code, out = _run(capsys, ["check-proposals", str(work / "session.json"), str(issue_only), "--variant", "full_session"])
    assert code == 0 and out["rejected_proposals"] == [] and out["errors"] == []
    assert _tree_hashes(tmp_path) == before  # nothing written anywhere
    code, _ = _run(capsys, ["check-proposals", str(work / "missing.json"), str(props)])
    assert isinstance(code, str) and "not a readable JSON file" in code


def test_check_proposals_on_the_rendered_session_events(layout, capsys, tmp_path):
    """The session-events record of a contract workspace (tasks.render_session_events) gives make-contract's answer."""
    nt, _ = layout
    gen = _gen_file(tmp_path)
    props = _write(tmp_path / "proposals.json", _proposals(nt))
    issue_only = _write(tmp_path / "issue_only.json", _proposals(nt)[:1])
    for variant, p in (("full_session", props), ("reference", props), ("reference", issue_only), ("initial_only", issue_only),
                       ("initial_only", props)):
        events = _events(nt, variant, tmp_path / f"events-{variant}.json")
        assert "FX-AGENT" not in events.read_text()  # the PR body and the commit messages are not shown
        code, made = _run(capsys, ["make-contract", str(nt.task_dir), "--variant", variant, "--proposals", str(p), "--proposer",
                                   "model:config-A:contract:v1", "--generation-record", str(gen)])
        assert code == 0
        code, out = _run(capsys, ["check-proposals", str(events), str(p)])  # the variant is the record's own
        assert out["variant"] == variant
        _same(out, made)


def test_check_proposals_and_make_contract_without_the_rendering_of_the_thread(layout, capsys, tmp_path, monkeypatch):
    """A tree without tasks.session_from_events or tasks.render_session_events refuses with a message, not a traceback,
    and make-contract writes nothing."""
    nt, _ = layout
    events = _events(nt, "full_session", tmp_path / "ev.json")
    props = _write(tmp_path / "p.json", _proposals(nt)[:1])
    monkeypatch.delattr(tasks, "session_from_events")
    code, _ = _run(capsys, ["check-proposals", str(events), str(props)])
    assert isinstance(code, str) and code.startswith("check-proposals:") and "no tasks.session_from_events" in code
    monkeypatch.delattr(tasks, "render_session_events")
    before = _tree_hashes(nt.task_dir)
    code, _ = _run(capsys, ["make-contract", str(nt.task_dir), "--variant", "full_session", "--proposals", str(props),
                            "--proposer", "model:config-A:contract:v1", "--generation-record", str(_gen_file(tmp_path))])
    assert isinstance(code, str) and "make-contract refused, nothing written" in code and "render_session_events" in code
    assert _tree_hashes(nt.task_dir) == before


# The paths that an audit hook saw opened or listed while _ACCESS["paths"] is a list (sys.addaudithook cannot be removed,
# so the hook is installed once and records nothing otherwise).
_ACCESS: dict[str, list[str] | None] = {"paths": None}
_HOOK: list[bool] = []


def _record_access(event: str, args: tuple) -> None:
    paths = _ACCESS["paths"]
    if paths is not None and event in ("open", "os.listdir", "os.scandir") and args and isinstance(args[0], (str, bytes, os.PathLike)):
        paths.append(os.fsdecode(args[0]))


def test_check_proposals_opens_only_the_two_files_named(layout, capsys, tmp_path):
    """No file but the two named is opened or listed (Python's own module files apart), so check-proposals never reads
    the task directory, the repository or a sibling workspace."""
    nt, _ = layout
    ws = tmp_path / "contract-full"
    ws.mkdir()
    events = _events(nt, "full_session", ws / "session_events.json")
    props = _write(ws / "proposals.json", {"requirements": _proposals(nt)})
    if not _HOOK:
        sys.addaudithook(_record_access)
        _HOOK.append(True)
    _ACCESS["paths"] = []
    try:
        code, out = _run(capsys, ["check-proposals", str(events), str(props)])
    finally:
        seen, _ACCESS["paths"] = _ACCESS["paths"] or [], None
    assert code == 1 and isinstance(out, dict) and out["written"] is False
    modules = {Path(p).resolve() for p in sys.path if p}
    read = {Path(p).resolve() for p in seen if Path(p).suffix not in (".py", ".pyc", ".so") and Path(p).resolve() not in modules}
    assert read == {events.resolve(), props.resolve()}, sorted(map(str, read))


def test_check_proposals_applies_no_natural_rule_to_other_sessions(capsys, tmp_path):
    ev = [Event(event_id=f"s/{i}", session_id="s", index=i, kind=k, author=Author.unknown, text=t, source=SourceRef(path="x", line=i))
          for i, (k, t) in enumerate([(EventKind.user_prompt, "Please add f."), (EventKind.assistant_text, "I added f and g.")])]
    s = Session(session_id="s", population=Population.controlled, source="fixture", source_format="claude_code_jsonl",
                trace_sha256=SHA, events=ev)
    sp = tmp_path / "session.json"
    dump(s, sp)
    props = _write(tmp_path / "p.json", [{"req_id": "R1", "statement": "g exists.", "status": "inferred", "rationale": "r",
                                          "introduced_at": "s/1", "observable": "g()"}])
    code, out = _run(capsys, ["check-proposals", str(sp), str(props), "--variant", "reference"])
    assert code == 0 and out["natural_pr_review_rules"] is False and out["rejected_proposals"] == [] and out["warnings"] == []


# --------------------------------------------------------------------------- the acceptance gate


def test_the_gate_refuses_a_natural_task_that_did_not_pass_s10_and_names_one_not_s11(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git(root)
    ok = build_natural_task(root)
    g = task_gate(ok.task_dir, root)
    assert not g.refusals and not any(r.startswith(("s10:", "index:")) for r in g.reasons)
    built = build_natural_task(root, "NP-91", s10_outcome="built")
    g = task_gate(built.task_dir, root)
    assert g.refusals == [("s10: the S10 outcome recorded in s10.json is 'built', not 'passed'; only a family that passes S10 is "
                           "built and evaluated (§16.4)")]
    write_index_row(root, ok.task_id, s11=False)
    assert any(r.startswith("index: NP-90 is not S11") for r in task_gate(ok.task_dir, root).reasons)
    assert not task_gate(ok.task_dir, root).refusals
    unindexed = build_natural_task(root, "NP-92", index=False)
    assert "index: NP-92 has no row in the committed index (data/manifests/natural_tasks_index.json)" in task_gate(
        unindexed.task_dir, root).reasons
    (ok.task_dir / "s10.json").unlink()
    assert task_gate(ok.task_dir, root).refusals == ["s10: no readable s10.json, so the family has not passed S10 (§15.6, §16.4)"]


def test_the_gate_reads_the_index_of_the_head_commit(tmp_path):
    """The S11 reason follows the committed index, not the working tree's, which natural-index rewrites before it is
    committed; a working tree that gives the task another S11 value is named."""
    root = tmp_path / "repo"
    root.mkdir()
    init_git(root)
    nt = build_natural_task(root)  # its row is committed with s11 true

    def index_reasons(task: NaturalTask = nt, at: Path = root) -> list[str]:
        return [r for r in task_gate(task.task_dir, at).reasons if r.startswith("index:")]

    assert index_reasons() == []
    write_index_row(root, nt.task_id, s11=False, commit=False)  # regenerated, not committed: the committed row counts
    assert index_reasons() == [(f"index: the working tree's {INDEX.as_posix()} gives NP-90 s11 False, the committed one True; "
                                "commit the index or restore it (the gate follows the committed one)")]
    write_index_row(root, nt.task_id, s11=False)
    assert index_reasons() == [(f"index: NP-90 is not S11 in the committed index ({INDEX.as_posix()}); S11 means passing S10 "
                                "within the family cap (§16.4)")]
    write_index_row(root, nt.task_id, s11=True, commit=False)  # marked S11 in the working tree only
    reasons = index_reasons()
    assert len(reasons) == 2 and reasons[0].startswith("index: NP-90 is not S11 in the committed index")
    assert "gives NP-90 s11 True, the committed one False" in reasons[1]
    (root / INDEX).unlink()  # no working-tree index: the committed one alone
    assert len(index_reasons()) == 1
    plain = tmp_path / "plain"  # no git repository: no committed index
    plain.mkdir()
    other = build_natural_task(plain, "NP-93")
    assert index_reasons(other, plain) == [(f"index: no readable committed index ({INDEX.as_posix()} in the HEAD commit), so "
                                            "S11 cannot be checked")]
    assert not task_gate(other.task_dir, plain).refusals


def test_the_gate_rules_do_not_touch_other_populations(tmp_path):
    root = tmp_path / "repo"
    td = _controlled_task(root)
    g = task_gate(td, root)
    assert not any(r.startswith(("s10:", "index:")) for r in g.reasons + g.refusals)


def test_the_accepted_natural_tasks_pass_the_natural_rules():
    """Read-only: the six accepted families record S10 passed and are S11 in the committed index (D59)."""
    nat_tasks = REPO / "data" / "natural" / "tasks"
    accepted = [t for t in ("NP-03", "NP-04", "NP-05", "NP-18", "NP-19", "NP-20") if (nat_tasks / t / "task.json").is_file()]
    if not accepted:
        pytest.skip("the natural tasks are not in this checkout (data/natural/ is git-ignored)")
    for t in accepted:
        assert natural_gate_problems(nat_tasks / t, REPO, t) == ([], [])
    assert contract_mod.NATURAL_INDEX == "data/manifests/natural_tasks_index.json"
    assert COMMENT_TEXT  # the layout's texts are synthetic


def test_the_accepted_natural_sessions_render_for_every_contract_variant():
    """Read-only: make-contract checks an accepted family's proposals on the events its proposer is shown, so every
    variant of each of the six sessions renders, and the events shown keep the whole session's ids, kinds, texts and
    order (a contract made on them validates on the whole session alike). Only ids and counts are compared here."""
    nat_tasks = REPO / "data" / "natural" / "tasks"
    accepted = [t for t in ("NP-03", "NP-04", "NP-05", "NP-18", "NP-19", "NP-20") if (nat_tasks / t / "session.json").is_file()]
    if not accepted:
        pytest.skip("the natural tasks are not in this checkout (data/natural/ is git-ignored)")
    for t in accepted:
        whole = tasks.session_for_task(nat_tasks / t, REPO)
        by_id = {e.event_id: e for e in whole.events}
        for variant in ContractVariant:
            shown = cli._rendered_session(whole, variant, SystemExit).events
            assert all(by_id[e.event_id].text == e.text and by_id[e.event_id].kind == e.kind for e in shown), (t, variant)
            assert [by_id[e.event_id].index for e in shown] == sorted(by_id[e.event_id].index for e in shown), (t, variant)
            users = sum(e.kind == EventKind.user_prompt for e in shown)  # the issue; then the comment and any replies
            assert (users == 1) if variant == ContractVariant.initial_only else (users >= 2), (t, variant)
