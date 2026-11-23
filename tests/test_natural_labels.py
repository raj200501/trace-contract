"""D19 labels, duplicates and the review packet of a natural PR-review task (plan WP-F; protocol §15.6, §17.2, §19.7, §20.2;
D64, D73).

On a synthetic accepted family (``tests/natural_task_layout.py``: NP-90, whose task and base snapshot lie under a scratch
repository's ``data/natural/``), given frozen synthetic reference checks and a small pool, with stubs in place of Docker:

* ``scripts/propose_labels.py``: D19 is the first step of the run of the family's sample (D73), so it waits until building
  has stopped for the family's own sample, the ``sample`` of its row in the committed index (§20.2: a first-sample family
  does not wait for the extension; a task without a row, or whose row names neither sample, is refused, and so is every
  task while another row names neither sample, or while a family that S9 lists for the sample is pending under a row of
  the other sample or of none), and until the committed phase-end log holds the phases P1 to P7, in order, of the family
  and of every accepted family of its sample (D65, D73; lines of other tasks do not count, the working tree's log is not
  read, and a log that cannot be read or holds a line of another form refuses); it grades only frozen
  reference checks; the regression norm is ``s10.json`` ``base_tests.subset`` (the default; any other base test paths
  are refused before anything is looked up, graded or written); the paths and the overlay's manifest hash are logged; the
  base snapshot is the one ``roots.snapshot_root`` names for the task id, and is checked; the image is looked up, never
  built; three repeats by default and no other count; repeats whose proposals differ are a missing decision, so ambiguous;
  the pre-review state is ambiguous when the reference checks pass and invalid when they fail; the overlay is built and
  graded outside the task and put in place only once every label is known, so a refusal on the way leaves the task as it
  was; nothing is written through a symbolic link;
* ``scripts/find_duplicates.py``: the base snapshot under ``data/natural/snapshots``, and the pre-review state ranked first
  as the representative of same-code candidates, also against a dev attack; an unusable snapshot root and a linked record
  are refused;
* ``tracecontract.review``: the pre-review state is scored as the pre-correction origin class; a packet inside the repository
  is refused; a natural packet's session text holds the issue, the comment and the reply only, and its README names the
  natural task argument of ``sandbox-python``;
* ``scripts/write_review_queue.py`` and ``scripts/record_construction_checks.py --tasks-root`` on the natural task, never
  through a symbolic link.

The family's index row (of the first sample) is committed in the scratch repository with S9 complete for both samples, so
building has stopped there, and so is the phase-end log with the family's phases P1 to P7. Synthetic data only; nothing is
graded, and nothing under the study repository is written.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from natural_task_layout import (
    AGENT_ONLY_MARKERS, BASE_TEST, COMMENT_TEXT, HUNK_TEXT, IMAGE, IMAGE_ID, INDEX, ISSUE_TEXT, PHASE_ENDS, PHASES,
    PRE_REVIEW_MOD, REFERENCE_MOD, REPLY_TEXT, T0, TEST_ARGS, NaturalTask, build_natural_task, commit_index, git, init_git,
    local_image_stub, phase_end_line, phase_ends, write_index_row, write_phase_ends,
)
from tracecontract import evaluate, roots
from tracecontract import natural_pr as npr
from tracecontract.patches import diff_dirs
from tracecontract.review import TEMPLATE, export_packet, merge_labels, origin_class, packet_location_problem
from tracecontract.schemas import (
    Candidate, CandidateOrigin, CheckResult, ContractVariant, EvidenceSpan, Label, LabelerKind, Outcome, Requirement,
    RequirementKind, RequirementStatus, Split, TaskContract, TaskManifest, VerificationResult, VerifierCondition, VerifierSpec,
    sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, load
from tracecontract.verifier import build_spec, freeze

ROOT = Path(__file__).resolve().parents[1]
SUBSET = TEST_ARGS[-1]  # the layout's s10.json base_tests.subset: one repository test file
ISSUE_CHECK = "test_reference_check.py::test_issue_case"
CORRECTION_CHECK = "test_reference_check.py::test_correction_case"
REFCHECK_TESTS = "def test_issue_case():\n    assert True\n\n\ndef test_correction_case():\n    assert True\n"
BASE_TEST_ID = "tests/test_mod.py::test_add"
ALT_MOD = REFERENCE_MOD.replace("    if a is None:\n        a = 0\n    if b is None:\n        b = 0\n    return a + b\n",
                                "    return (0 if a is None else a) + (0 if b is None else b)\n")
NM_MOD = PRE_REVIEW_MOD.replace("    return a + b\n", "    return a + b  # the second argument is left as it was\n", 1)
ATTACK_MOD = PRE_REVIEW_MOD.replace("def add(a, b):\n", 'def add(a, b):\n    """Add two numbers."""\n', 1)


def _script(name: str):
    spec = importlib.util.spec_from_file_location(f"natural_{name}", ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pl = _script("propose_labels")
pfl = _script("preflight_final_run")  # whose rules propose_labels applies
fd = _script("find_duplicates")
wrq = _script("write_review_queue")
rcc = _script("record_construction_checks")


OVERLAY = "labels/base_tests_overlay"
OVERLAY_TREE = {SUBSET: hashlib.sha256(BASE_TEST.encode()).hexdigest()}  # the subset's file as the BASE commit has it


def _tree(root: Path) -> dict[str, str]:
    """sha256 of every file under ``root`` by its path there (the scratch repository's own ``.git`` left out)."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(root).parts}


def _index(nt: NaturalTask, **fields) -> None:
    """Set top-level fields of the scratch repository's natural index (``s9_complete``, say) and commit it."""
    index = json.loads(nt.index.read_text(encoding="utf-8"))
    index.update(fields)
    nt.index.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    commit_index(nt.root)


def _set_snapshot_root(nt: NaturalTask, rel: str) -> None:
    """Record ``rel`` as the task's snapshot root in its provenance notes (what ``roots.snapshot_root`` reads)."""
    prov = json.loads((nt.task_dir / "provenance.json").read_text(encoding="utf-8"))
    prov["notes"] = json.dumps({**json.loads(prov["notes"]), "snapshot_root": rel})
    (nt.task_dir / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")


def _patch(nt: NaturalTask, files: dict[str, str]) -> str:
    state = nt.root / ".scratch-state"
    shutil.copytree(nt.snapshot_dir, state)
    for rel, text in files.items():
        (state / rel).write_text(text, encoding="utf-8")
    patch = diff_dirs(nt.snapshot_dir, state)
    shutil.rmtree(state)
    return patch


def _add_candidate(nt: NaturalTask, kind: str, origin: CandidateOrigin, split: Split, mod: str, label: Label) -> str:
    cid = nt.candidate_id(kind)
    patch = _patch(nt, {"fxnat/mod.py": mod})
    dump(Candidate(candidate_id=cid, task_id=nt.task_id, origin=origin, split=split, patch=patch, patch_sha256=sha256_text(patch),
                   produced_by="synthetic fixture", description="synthetic", labels=[label]), nt.task_dir / "candidates" / f"{cid}.json")
    m = load(nt.task_dir / "task.json", TaskManifest)
    dump(m.model_copy(update={"candidates": [*m.candidates, f"candidates/{cid}.json"]}), nt.task_dir / "task.json")
    return cid


def _construction(value: str, violated: list[str] | None = None, labeler: str = "nearmiss:v1") -> Label:
    return Label(value=value, violated_requirements=violated or [], labeler=labeler, labeler_kind=LabelerKind.construction,
                 timestamp=T0)


@pytest.fixture()
def nat(tmp_path) -> NaturalTask:
    """NP-90 with frozen reference checks (one check per requirement: R1 the issue, R2 the correction), a valid alternative
    and a near miss (held out), and a dev attack; the near miss and the dev attack have the pre-review state's code. The
    scratch repository is a git repository whose committed index has the family's row (S10 passed, S11, of the first
    sample) and S9 complete for both samples, so building has stopped (protocol §19.5, §20.2), and whose committed
    phase-end log holds the family's phases P1 to P7 (decision log D65, D73)."""
    root = tmp_path / "repo"
    root.mkdir()
    init_git(root)
    nt = build_natural_task(root)  # the index row, committed
    write_index_row(root, nt.task_id, sample="first")  # a family of the first sample (natural-pr-v1, §20.2)
    _index(nt, s9_complete={"first": {"screened": 150, "families": [nt.task_id]},  # the pre-flight's S9 record
                            "extension": {"screened": 534, "families": []}})
    write_phase_ends(root, phase_ends(nt.task_id))  # the end of each of its phases, committed (D65)
    td = nt.task_dir
    tests = td / "verifiers" / "reference_check" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_reference_check.py").write_text(REFCHECK_TESTS, encoding="utf-8")
    dump(freeze(build_spec(verifier_id="reference_check", task_id=nt.task_id, condition=VerifierCondition.reference_check,
                           test_dir=tests, task_dir=td, requirement_map={ISSUE_CHECK: ["R1"], CORRECTION_CHECK: ["R2"]}), td),
         td / "verifiers" / "reference_check" / "spec.json")
    _add_candidate(nt, "eval-alt-1", CandidateOrigin.valid_alternative, Split.eval, ALT_MOD, _construction("valid", labeler="altimpl:v1"))
    _add_candidate(nt, "eval-nm-1", CandidateOrigin.constructed_near_miss, Split.eval, NM_MOD, _construction("invalid", ["R2"]))
    _add_candidate(nt, "dev-attack-full_session-a1", CandidateOrigin.dev_attack, Split.dev, ATTACK_MOD,
                   _construction("invalid", ["R2"], labeler="attack:v1"))
    return nt


class Docker:
    """The stubs of propose_labels' Docker calls, and what they were asked.

    ``plans[(verifier id, candidate id)]`` gives each call in turn its failing checks (``set()``: all pass; ``"timeout"``:
    no decision); a pair without a plan passes. ``reference_runs`` gives each run of the base tests on the reference the
    node ids that pass, and ``reference_result`` more keys of its results (``{"timed_out": True}``: it timed out);
    ``stage_error`` makes the reference patch fail to stage. Recorded: ``staged``, the base each staging was given;
    ``overlays``, the overlay's files (path and sha256) that each run of the base tests and each regression-norm grade was
    given; ``labels_seen``, whether the task's ``labels/`` existed at each run and grade.
    """

    def __init__(self, monkeypatch, nt: NaturalTask, *, image_id: str = IMAGE_ID):
        self.plans: dict[tuple[str, str], list] = {}
        self.reference_runs: list[list[str]] = [[BASE_TEST_ID]]
        self.reference_result: dict = {}
        self.stage_error: str | None = None
        self.grades: list[tuple[str, str, Path]] = []
        self.staged: list[Path] = []
        self.overlays: list[dict[str, str]] = []
        self.labels_seen: set[bool] = set()
        self.lookups: list[str] = []
        self.runs = 0
        self._count: Counter = Counter()
        lookup = local_image_stub({IMAGE: image_id})

        def local_image_id(tag):
            self.lookups.append(tag)
            return lookup(tag)

        def build_env_image(*a, **k):
            raise AssertionError("a natural PR-review task's image is looked up, never built")

        def prepare_workspace(base, patch, *a, **k):
            self.staged.append(Path(base))
            if self.stage_error:
                return None, [self.stage_error], "patch_apply_failed"
            ws = nt.root.parent / "ws"
            ws.mkdir(exist_ok=True)
            return ws, [], None

        def run_grader(tag, *, workspace, mode, overlay_dir, **_):
            assert tag == IMAGE
            self.overlays.append(_tree(Path(overlay_dir)))
            self.labels_seen.add((nt.task_dir / "labels").exists())
            passing = self.reference_runs[self.runs % len(self.reference_runs)]
            self.runs += 1
            tests = [{"nodeid": n, "outcome": "passed"} for n in passing] + [{"nodeid": "tests/test_mod.py::x", "outcome": "failed"}]
            results = {"nonce": "n0", "status": "completed", "tests": tests, **self.reference_result}
            return SimpleNamespace(results=results, timed_out=False), "n0"

        def verify_candidate(*, image, spec, candidate, base_dir, task_dir, **_):
            key = (spec.verifier_id, candidate.candidate_id)
            plan = self.plans.get(key, [set()])
            failed = plan[self._count[key] % len(plan)]
            self._count[key] += 1
            self.grades.append((spec.verifier_id, candidate.candidate_id, Path(base_dir)))
            self.labels_seen.add((nt.task_dir / "labels").exists())
            if spec.verifier_id == "regression_norm":
                self.overlays.append(_tree(Path(task_dir) / spec.test_dir))
            if failed == "timeout":
                outcome, checks = Outcome.timeout, []
            else:
                outcome = Outcome.task_failure if failed else Outcome.passed
                checks = [CheckResult(check_id=c.check_id, status="failed" if c.check_id in failed else "passed") for c in spec.checks]
            return VerificationResult(run_id="labels", task_id=spec.task_id, verifier_id=spec.verifier_id,
                                      candidate_id=candidate.candidate_id, outcome=outcome, reward=float(outcome == Outcome.passed),
                                      checks=checks, started_at=T0, finished_at=T0, wall_s=0.0, harness_version="stub")

        monkeypatch.setattr(evaluate, "local_image_id", local_image_id)
        for name, fn in (("build_env_image", build_env_image), ("prepare_workspace", prepare_workspace),
                         ("run_grader", run_grader), ("verify_candidate", verify_candidate)):
            monkeypatch.setattr(pl, name, fn)
        monkeypatch.setattr(pl, "REPO", nt.root)


def _label(nt: NaturalTask, kind: str) -> Label:
    c = load(nt.task_dir / "candidates" / f"{nt.candidate_id(kind)}.json", Candidate)
    assert c.labels[-1].labeler == pl.LABELER and c.labels[-1].labeler_kind == LabelerKind.model
    return c.labels[-1]


def _log(nt: NaturalTask) -> dict:
    return json.loads((nt.task_dir / "labels" / "proposed_labels.json").read_text())


# --------------------------------------------------------------------------- propose_labels


def test_the_pre_review_state_is_ambiguous_when_the_reference_checks_pass(nat, monkeypatch):
    docker = Docker(monkeypatch, nat)
    docker.plans[("reference_check", nat.candidate_id("eval-nm-1"))] = [{CORRECTION_CHECK}]
    pl.main(str(nat.task_dir))
    value, violated = _label(nat, "pre-review").value, _label(nat, "pre-review").violated_requirements
    assert (value, violated) == ("ambiguous", []) and "not observable by the checks" in _label(nat, "pre-review").note
    assert (_label(nat, "eval-alt-1").value, _label(nat, "eval-nm-1").value) == ("valid", "invalid")
    assert _label(nat, "eval-nm-1").violated_requirements == ["R2"]
    pre = load(nat.task_dir / "candidates" / f"{nat.candidate_id('pre-review')}.json", Candidate)
    assert [lb.labeler_kind for lb in pre.labels] == [LabelerKind.source_evidence, LabelerKind.model]  # the evidence is kept
    entry = _log(nat)["candidates"][nat.candidate_id("pre-review")]
    assert (entry["refcheck_outcome"], entry["refcheck_failed"]) == ("pass", [])  # the checks' verdict on the state is logged
    # Three repeats (D64): each held-out candidate's reference checks and regression norm graded three times, on the base
    # snapshot that roots.snapshot_root names (data/natural/snapshots), and the base tests run three times on the reference.
    held = {nat.candidate_id(k) for k in ("pre-review", "eval-alt-1", "eval-nm-1")}
    assert Counter((v, c) for v, c, _ in docker.grades) == {(v, c): 3 for v in ("reference_check", "regression_norm") for c in held}
    assert {b for _, _, b in docker.grades} == {nat.root / "data" / "natural" / "snapshots" / nat.task_id}
    assert docker.runs == 3 and docker.lookups == [IMAGE]
    assert nat.candidate_id("noop-eval") not in _log(nat)["candidates"] and nat.candidate_id("reference") not in _log(nat)["candidates"]


def test_the_pre_review_state_is_invalid_when_a_reference_check_fails(nat, monkeypatch):
    docker = Docker(monkeypatch, nat)
    docker.plans[("reference_check", nat.candidate_id("pre-review"))] = [{CORRECTION_CHECK}]
    pl.main(str(nat.task_dir))
    assert (_label(nat, "pre-review").value, _label(nat, "pre-review").violated_requirements) == ("invalid", ["R2"])
    entry = _log(nat)["candidates"][nat.candidate_id("pre-review")]
    assert (entry["refcheck_outcome"], entry["refcheck_failed"], entry["repeats_agree"]) == ("task_failure", [CORRECTION_CHECK], True)
    assert [r["proposed"] for r in entry["repeat_results"]] == ["invalid"] * 3


def test_the_regression_norm_is_the_s10_subset_and_is_logged(nat, monkeypatch):
    Docker(monkeypatch, nat)
    pl.main(str(nat.task_dir))
    overlay = nat.task_dir / "labels" / "base_tests_overlay"
    # The subset's files as the BASE commit has them, not as the reference does (B1's overlay).
    assert _tree(overlay) == OVERLAY_TREE
    log = _log(nat)
    assert log["population"] == "natural:pr-review" and log["repeats"] == pl.NATURAL_REPEATS == 3
    # The rule cites the natural recipe's entry, D64 (planned as D61, which is the fresh-v1 run).
    assert log["rule"] == "D19, natural PR-review task (protocol §15.6; repeats: D64)"
    norm = log["regression_norm"]
    assert norm["base_test_paths"] == [SUBSET] and norm["source"] == pl.NATURAL_NORM_SOURCE
    assert norm["overlay"] == "labels/base_tests_overlay" and norm["overlay_n_files"] == 1
    assert norm["overlay_manifest_sha256"] == manifest_sha256(manifest(overlay))
    # The same hash the committed index gives the overlay directory (natural_pr.file_hashes summarises it).
    assert npr.file_hashes(nat.task_dir)["labels/base_tests_overlay/"] == {"manifest_sha256": norm["overlay_manifest_sha256"],
                                                                         "n_files": 1}
    assert (norm["reference_runs"], norm["n_checks"], norm["n_not_passing_in_every_reference_run"]) == (3, 1, 0)
    spec = load(nat.task_dir / "verifiers" / "reference_check" / "spec.json", pl.VerifierSpec)
    assert log["reference_check"] == {"verifier_id": "reference_check", "content_sha256": spec.content_sha256,
                                      "checks_sha256": spec.checks_sha256, "frozen_at": spec.frozen_at}
    snap = json.loads((nat.task_dir / "snapshot.json").read_text())
    assert log["base_snapshot_manifest_sha256"] == snap["file_manifest_sha256"] and log["image"] == {"tag": IMAGE, "id": IMAGE_ID}
    # The subset named on the command line is the same norm.
    pl.main(str(nat.task_dir), SUBSET)
    assert _log(nat)["regression_norm"]["base_test_paths"] == [SUBSET]


@pytest.mark.parametrize("paths", [("tests/test_other.py",), (SUBSET, "tests/test_other.py"), ("tests",), ("../x.py",)])
def test_other_base_test_paths_are_refused_before_anything_happens(nat, monkeypatch, paths):
    docker = Docker(monkeypatch, nat)
    before = _tree(nat.root)
    with pytest.raises(SystemExit, match="other base test paths are refused"):
        pl.main(str(nat.task_dir), *paths)
    assert _tree(nat.root) == before and docker.grades == [] and docker.lookups == [] and docker.runs == 0


def test_a_natural_task_is_graded_three_times_only(nat, monkeypatch):
    docker = Docker(monkeypatch, nat)
    before = _tree(nat.root)
    for n in (1, 2, 5):
        with pytest.raises(SystemExit, match=r"grades it 3 times \(D64\)"):
            pl.main(str(nat.task_dir), repeats=n)
    with pytest.raises(SystemExit, match="must be at least 1"):
        pl.main(str(nat.task_dir), repeats=0)
    assert _tree(nat.root) == before and docker.grades == []
    pl.main(str(nat.task_dir), repeats=3)
    assert _log(nat)["repeats"] == 3


def test_repeats_that_disagree_are_a_missing_decision(nat, monkeypatch):
    docker = Docker(monkeypatch, nat)
    alt, nm, pre = (nat.candidate_id(k) for k in ("eval-alt-1", "eval-nm-1", "pre-review"))
    docker.plans[("reference_check", alt)] = [set(), {CORRECTION_CHECK}, set()]  # one flaky reference check
    docker.plans[("reference_check", nm)] = [{CORRECTION_CHECK}]
    docker.plans[("regression_norm", nm)] = [set(), {BASE_TEST_ID}, set()]  # a regression in one repeat only: still invalid R2
    docker.plans[("reference_check", pre)] = [{CORRECTION_CHECK}, {CORRECTION_CHECK}, "timeout"]
    pl.main(str(nat.task_dir))
    lab = _label(nat, "eval-alt-1")
    assert (lab.value, lab.violated_requirements) == ("ambiguous", []) and "a missing decision" in lab.note
    assert "the 3 repeats give different proposals (valid []; ambiguous ['R2']; valid [])" in lab.note
    assert (_label(nat, "eval-nm-1").value, _label(nat, "eval-nm-1").violated_requirements) == ("invalid", ["R2"])
    assert _label(nat, "pre-review").value == "ambiguous"
    log = _log(nat)["candidates"]
    assert (log[alt]["refcheck_outcome"], log[alt]["repeats_agree"]) == ("unresolved", False)
    assert [r["refcheck_outcome"] for r in log[alt]["repeat_results"]] == ["pass", "task_failure", "pass"]
    assert (log[nm]["regression_outcome"], log[nm]["regression_failed"], log[nm]["repeats_agree"]) == ("unresolved", [BASE_TEST_ID], True)
    assert [r["refcheck_outcome"] for r in log[pre]["repeat_results"]] == ["task_failure", "task_failure", "timeout"]


def test_the_regression_norm_keeps_the_base_tests_that_pass_on_the_reference_in_every_run(nat, monkeypatch):
    docker = Docker(monkeypatch, nat)
    flaky = "tests/test_mod.py::test_sometimes"
    docker.reference_runs = [[BASE_TEST_ID, flaky], [BASE_TEST_ID], [BASE_TEST_ID, flaky]]
    pl.main(str(nat.task_dir))
    norm = _log(nat)["regression_norm"]
    assert (norm["n_checks"], norm["n_not_passing_in_every_reference_run"], norm["not_passing_in_every_reference_run"]) == (
        1, 1, [flaky])


def test_the_base_snapshot_and_the_image_are_checked_before_anything_is_written(nat, monkeypatch):
    docker = Docker(monkeypatch, nat, image_id="sha256:" + "ab" * 32)
    before = _tree(nat.root)
    with pytest.raises(SystemExit, match="snapshot.json records"):  # another image under the recorded tag
        pl.main(str(nat.task_dir))
    assert _tree(nat.root) == before and docker.grades == [] and docker.lookups == [IMAGE]
    docker = Docker(monkeypatch, nat)
    # A natural task's base is never looked for under snapshots/: an intact copy there changes nothing.
    shutil.copytree(nat.snapshot_dir, nat.root / "snapshots" / nat.task_id)
    (nat.snapshot_dir / "fxnat" / "mod.py").write_text("changed\n", encoding="utf-8")
    before = _tree(nat.root)
    with pytest.raises(SystemExit, match="base snapshot missing or modified.*compile-pr-task"):
        pl.main(str(nat.task_dir))
    assert _tree(nat.root) == before and docker.grades == [] and docker.lookups == []


def test_a_natural_task_has_no_strata_and_needs_its_s10_subset(nat, monkeypatch):
    docker = Docker(monkeypatch, nat)
    with pytest.raises(SystemExit, match="no candidate strata"):
        pl.main(str(nat.task_dir), stratum="fresh-v1")
    s10 = json.loads((nat.task_dir / "s10.json").read_text())
    s10["base_tests"]["subset"] = []
    (nat.task_dir / "s10.json").write_text(json.dumps(s10), encoding="utf-8")
    with pytest.raises(SystemExit, match=r"records no base-test subset \(base_tests.subset\)"):
        pl.main(str(nat.task_dir))
    (nat.task_dir / "s10.json").unlink()
    with pytest.raises(SystemExit, match="records no base-test subset"):
        pl.main(str(nat.task_dir))
    assert docker.grades == [] and not (nat.task_dir / "labels").exists()


# --------------------------------------------------------------------------- when D19 may run (§20.2; D65, D73)

FIRST_DONE = {"screened": 150, "families": ["NP-90"]}  # S9 complete for the first sample, NP-90 its only family
EXTENSION_DONE = {"screened": 534, "families": []}
INDEX_AT = r"the committed index \(data/manifests/natural_tasks_index.json in the HEAD commit\)"
LOG_AT = r"the committed phase-end log \(data/manifests/natural_phase_ends.jsonl in the HEAD commit\)"


def _row(task_id: str = "NP-90", *, sample: object = "first", s11: bool = True, outcome: str = "passed",
         role: str = "family") -> dict:
    """A row of the natural index, in the layout's form, with its sample."""
    return {"task_id": task_id, "role": role, "s10": {"outcome": outcome, "stage": "S10"}, "s11": s11, "sample": sample}


def _gate_tree(nt: NaturalTask) -> dict[str, str]:
    """The scratch repository's files, but the two committed records that the tests of the gate rewrite."""
    return {k: v for k, v in _tree(nt.root).items() if k not in (INDEX.as_posix(), PHASE_ENDS.as_posix())}


def _refused(nt: NaturalTask, docker: Docker, match: str) -> None:
    """propose_labels refuses the task, with a message that matches ``match``, before anything is looked up, graded or
    written."""
    before = _gate_tree(nt)
    with pytest.raises(SystemExit, match=r"^propose_labels refused, nothing written: " + match):
        pl.main(str(nt.task_dir))
    assert _gate_tree(nt) == before
    assert docker.grades == [] and docker.lookups == [] and docker.runs == 0 and not (nt.task_dir / "labels").exists()


def _labelled(nt: NaturalTask, docker: Docker) -> None:
    """propose_labels labels the task's held-out candidates (the gate let D19 run)."""
    pl.main(str(nt.task_dir))
    assert docker.grades and _log(nt)["candidates"].keys() == {nt.candidate_id(k) for k in ("pre-review", "eval-alt-1",
                                                                                             "eval-nm-1")}


def test_d19_waits_until_building_has_stopped_for_the_family_s_sample(nat, monkeypatch):
    """§20.2 as D73 reads it: D19 is the first step of the family's run, so it waits until building has stopped for the
    family's own sample by the committed index (the pre-flight's rule), and is refused before anything is looked up,
    graded or written until then."""
    docker = Docker(monkeypatch, nat)
    _index(nat, s9_complete={"extension": EXTENSION_DONE})  # S9 is not recorded as complete for the first sample
    _refused(nat, docker, r"NP-90: natural: building has not stopped for the first sample by the committed index: .*S9 is "
                          r"not recorded as complete for the first sample")
    # A family of the first sample in a repository with an open place has no S10 outcome yet.
    _index(nat, tasks=[_row(), _row("NP-91", s11=False, outcome="not built")],
           s9_complete={"first": {"screened": 150, "families": ["NP-90", "NP-91"]}, "extension": EXTENSION_DONE})
    _refused(nat, docker, r"NP-90: natural: building has not stopped for the first sample by the committed index: .*1 "
                          r"family of the first sample in a repository with an open place has no S10 outcome \(NP-91\)")
    nat.index.write_text("not an index\n", encoding="utf-8")
    commit_index(nat.root)
    _refused(nat, docker, rf"NP-90: natural: {INDEX_AT} cannot be read \(it is not JSON\), so nothing shows that building "
                          r"has stopped or which families are accepted \(protocol §16.4, §19.5, §20.2\)$")
    # Rules that cannot be applied show nothing either (fail closed).
    monkeypatch.setattr(pl, "PREFLIGHT", nat.root / "no_such_preflight.py")
    _refused(nat, docker, r"NP-90: the pre-flight's rules for when D19 may run \(no_such_preflight.py: building has stopped "
                          r"for the task's sample, and the committed phase-end log holds the phases P1 to P7 of every family "
                          r"of its run\) could not be applied \(.*\), so nothing shows that D19 may run \(protocol §20.2; "
                          r"decision log D65, D73\)$")


def test_a_first_sample_family_is_labelled_while_the_extension_is_still_being_built(nat, monkeypatch):
    """§20.2: the first sample's families are graded in natural-pr-v1 without waiting for the extension. Its S9 record is
    absent or partial and its families are pending or accepted, so §19.5's rule for both samples has not stopped building;
    the first sample's has, and D19 runs on NP-90."""
    docker = Docker(monkeypatch, nat)
    rows = [_row(), _row("NP-91", sample="extension", s11=False, outcome="not built"),
            _row("NP-92", sample="extension", s11=False, outcome="built", role="reserve"), _row("NP-93", sample="extension")]
    for extension in ({}, {"extension": {"screened": 200, "families": ["NP-91", "NP-92", "NP-93"]}}):
        _index(nat, tasks=rows, s9_complete={"first": FIRST_DONE, **extension})
        index, why = pfl.committed_index(nat.root)
        assert pfl.building_problems(index, why)[0].startswith(  # §19.5 over both samples
            "natural: building has not stopped by the committed index: it counts 2 accepted task(s) of both samples")
        _labelled(nat, docker)


def test_a_family_of_the_extension_waits_for_the_extension(nat, monkeypatch):
    """The rule is the one of the family's own sample: NP-90 recorded as a family of the extension waits until building
    has stopped for the extension, while the first sample's building has stopped."""
    docker = Docker(monkeypatch, nat)
    _index(nat, tasks=[_row(sample="extension"), _row("NP-91", sample="extension", s11=False, outcome="not built")],
           s9_complete={"first": {"screened": 150, "families": []},
                        "extension": {"screened": 534, "families": ["NP-90", "NP-91"]}})
    _refused(nat, docker, r"NP-90: natural: building has not stopped for the extension by the committed index: .*1 family "
                          r"of the extension in a repository with an open place has no S10 outcome \(NP-91\)")


@pytest.mark.parametrize("sample", ["extension", None, "absent"])
def test_a_family_that_s9_lists_for_the_first_sample_keeps_building_open_whatever_its_row_names(nat, monkeypatch, sample):
    """Fail closed (§20.2, D73): NP-91 is a family of the first sample by the S9 record, in a repository with an open place
    and without an S10 outcome, so building has not stopped for the first sample and D19 is refused on NP-90, as §19.5's
    rule over both samples refuses it, though NP-91's committed row names the extension or no sample, which a rule that
    read only the rows naming the first sample would pass over. A row that names no sample is also reported as the
    pre-flight reports it for a run."""
    docker = Docker(monkeypatch, nat)
    row = _row("NP-91", sample=sample, s11=False, outcome="not built")
    if sample == "absent":
        del row["sample"]
    _index(nat, tasks=[_row(), row],
           s9_complete={"first": {"screened": 150, "families": ["NP-90", "NP-91"]}, "extension": EXTENSION_DONE})
    stop = (r"NP-90: natural: building has not stopped for the first sample by the committed index: protocol §20\.2 grades "
            r"its accepted families in natural-pr-v1 once S9 is complete for it and every family and reserve of it has been "
            r"processed; 1 of the first sample's families and reserves \(s9_complete\.first\.families\) have a row in the "
            r"index that names the other sample or neither \(NP-91\)")
    end = r"\. No natural verifier is graded on a held-out candidate of a family before that family's run \(§20\.2\)"
    if sample == "extension":
        _refused(nat, docker, stop + end + "$")
    else:
        _refused(nat, docker, stop + r"; 1 family whose row names neither sample, in a repository with an open place, has "
                                     r"no S10 outcome \(NP-91\), and nothing shows that it is not of the first sample"
                                     + end + r"; natural: 1 row of the committed index \(NP-91\) names neither sample "
                                     r"\('first' or 'extension'\), so nothing shows which run grades it \(protocol §20\.2 "
                                     r"grades the natural arm in two runs, .*\)$")


def test_another_row_that_names_no_sample_refuses_d19_as_it_refuses_the_run(nat, monkeypatch):
    """As the pre-flight refuses a natural run (``sample_problems``): NP-91, accepted and processed, is in no S9 record and
    its row names no sample, so it could be an accepted family of the first sample that natural-pr-v1 grades with NP-90,
    whose phase ends D19 would then not ask for (D73)."""
    docker = Docker(monkeypatch, nat)
    row = _row("NP-91")
    del row["sample"]
    _index(nat, tasks=[_row(), row])
    _refused(nat, docker, r"NP-90: natural: 1 row of the committed index \(NP-91\) names neither sample \('first' or "
                          r"'extension'\), so nothing shows which run grades it \(protocol §20\.2 grades the natural arm in "
                          r"two runs, .*\)$")


@pytest.mark.parametrize("sample, other, run", [("first", "extension", "natural-pr-v1"),
                                                ("extension", "first", "natural-pr-v2")])
def test_d19_waits_for_the_phase_ends_of_every_accepted_family_of_its_sample(nat, monkeypatch, sample, other, run):
    """D73: the run of a sample grades its accepted families together, and D19 is the run's first step, so D19 on any of
    them waits until each has ended its seven phases: NP-90's own lines are not enough while NP-91, accepted in the same
    sample, lacks P7, or while the log cannot be read. A family of the other sample (NP-93), or one of the same sample
    that is not accepted (NP-92, rejected at S10), does not hold NP-90 back."""
    docker = Docker(monkeypatch, nat)
    sizes = {"first": 150, "extension": 534}
    _index(nat, tasks=[_row(sample=sample), _row("NP-91", sample=sample),
                       _row("NP-92", sample=sample, s11=False, outcome="rejected"), _row("NP-93", sample=other)],
           s9_complete={sample: {"screened": sizes[sample], "families": ["NP-90", "NP-91", "NP-92"]},
                        other: {"screened": sizes[other], "families": ["NP-93"]}})
    write_phase_ends(nat.root, [*phase_ends(nat.task_id), *phase_ends("NP-91", PHASES[:6])])
    _refused(nat, docker, rf"NP-90: NP-91, which {run} grades with it \(D19 is the first step of that run, decision log "
                          rf"D73\): {LOG_AT} has no line for its phase P7; D19 and the run grade a natural family once its "
                          r"phases P1 to P7 have ended, each recorded with scripts/record_phase_end.py and committed "
                          r"\(decision log D65, D73\)$")
    write_phase_ends(nat.root, [*phase_ends(nat.task_id), *phase_ends("NP-91"), "{not json"])
    _refused(nat, docker, rf"NP-90: natural: {LOG_AT} cannot be read \(its line 15 is not JSON\), so nothing shows that "
                          r"NP-90, NP-91 ended the phases P1 to P7 in order; ")
    write_phase_ends(nat.root, [*phase_ends(nat.task_id), *phase_ends("NP-91")])  # NP-92 and NP-93 have no line
    _labelled(nat, docker)


@pytest.mark.parametrize("sample", ["absent", None, "second", ["first"]])
def test_a_task_whose_committed_row_names_no_sample_is_refused(nat, monkeypatch, sample):
    """Fail closed (D73): with no sample, nothing shows which run grades the family, or whether building has stopped for
    its sample, though here it has stopped for both samples."""
    docker = Docker(monkeypatch, nat)
    row = _row(sample=sample)
    if sample == "absent":
        del row["sample"]
    _index(nat, tasks=[row])  # the fixture's S9 record: both samples complete, NP-90 the first sample's only family
    said = "it records no sample" if sample == "absent" else f"its sample is {re.escape(json.dumps(sample))}"
    _refused(nat, docker, rf"NP-90: its row in {INDEX_AT} names neither sample \({said}; the samples are 'first' and "
                          r"'extension'\), so nothing shows which run grades it, or whether building has stopped for its "
                          r"sample \(protocol §20.2; decision log D73\)$")


def test_a_family_that_is_not_accepted_is_refused(nat, monkeypatch):
    """A run grades only accepted (S11) families (§16.4, §20.2), so D19, the first step of its run (D73), is refused for a
    family whose committed row is not S11, though building has stopped and its seven phase ends are committed."""
    docker = Docker(monkeypatch, nat)
    _index(nat, tasks=[_row(s11=False)])
    _refused(nat, docker, rf"NP-90: it is not S11 in {INDEX_AT}: a run grades only accepted families, so D19 has no run "
                          r"to be the first step of \(protocol §16.4, §20.2; decision log D73\)$")


def test_a_task_without_a_row_in_the_committed_index_is_refused(nat, monkeypatch):
    """Building has stopped for both samples by the committed index, whose only family is NP-91 (rejected at S10), but
    NP-90 has no row there, so nothing shows its sample (D73). A row in the working tree's index is not read."""
    docker = Docker(monkeypatch, nat)
    _index(nat, tasks=[_row("NP-91", s11=False, outcome="rejected")],
           s9_complete={"first": {"screened": 150, "families": ["NP-91"]}, "extension": EXTENSION_DONE})
    no_row = (rf"NP-90: {INDEX_AT} has no row for it, so nothing shows its sample, which run grades it, or whether "
              r"building has stopped for that sample \(protocol §20.2; decision log D73\)$")
    _refused(nat, docker, no_row)
    write_index_row(nat.root, nat.task_id, sample="first", commit=False)  # in the working tree only
    _refused(nat, docker, no_row)


@pytest.mark.parametrize("case", ["no P7", "no P3", "no line", "out of order", "twice", "recorded earlier"])
def test_d19_waits_for_the_family_s_phase_ends(nat, monkeypatch, case):
    """D65, D73: the committed phase-end log holds a line for each of the family's phases P1 to P7, in order: each phase
    once, after the phase before it, and recorded no earlier than it."""
    docker = Docker(monkeypatch, nat)
    tid = nat.task_id
    missing = rf"NP-90: {LOG_AT} has no line for its phase{{}}; D19 and the run grade a natural family once its phases P1 to " \
              r"P7 have ended, each recorded with scripts/record_phase_end.py and committed \(decision log D65, D73\)$"
    disorder = rf"NP-90: its lines in {LOG_AT} are not in the order of its phases \({{}}\); in order, each phase comes " \
               r"once, after the phase before it, and is recorded no earlier than it \(the pre-flight's reading of decision " \
               r"log D73; scripts/record_phase_end.py refuses to append a line that breaks it, D65\)$"
    if case in ("no P7", "no P3"):
        lines = phase_ends(tid, tuple(p for p in PHASES if p != case[-2:]))
        match = missing.format(f" {case[-2:]}")
    elif case == "no line":
        lines = phase_ends("NP-91")
        match = missing.format("s P1, P2, P3, P4, P5, P6, P7")
    else:
        order = {"out of order": ("P1", "P2", "P4", "P3", "P5", "P6", "P7"), "twice": ("P1", "P2", "P2", *PHASES[2:]),
                 "recorded earlier": PHASES}[case]
        lines = phase_ends(tid, order)
        if case == "recorded earlier":  # P5 recorded before P4 (04:00), though after it in the log
            lines[4]["recorded_at"] = "2026-11-22T03:30:00Z"
        shown = ", ".join(f"{x['phase']} at {x['recorded_at']}" for x in lines)
        match = disorder.format(re.escape(shown))
    write_phase_ends(nat.root, lines)
    _refused(nat, docker, match)


def test_lines_of_other_tasks_do_not_count(nat, monkeypatch):
    """Another family's P7 line does not stand in for NP-90's, and another family's lines between NP-90's (as when
    families run side by side) do not break NP-90's order."""
    docker = Docker(monkeypatch, nat)
    write_phase_ends(nat.root, [*phase_ends(nat.task_id, PHASES[:6]), *phase_ends("NP-91")])
    _refused(nat, docker, rf"NP-90: {LOG_AT} has no line for its phase P7; ")
    mine, theirs = phase_ends(nat.task_id), phase_ends("NP-91", day="2026-11-21")
    write_phase_ends(nat.root, [x for pair in zip(theirs, mine, strict=True) for x in pair])
    _labelled(nat, docker)


def test_only_the_committed_phase_end_log_is_read(nat, monkeypatch, tmp_path):
    """The log as the HEAD commit holds it, read as the index is (contract.committed_text): the working tree's log, to
    which record_phase_end.py appends before the builder commits it, is not read, and neither GIT_DIR nor GIT_WORK_TREE of
    the caller redirects git to another repository."""
    docker = Docker(monkeypatch, nat)
    write_phase_ends(nat.root, phase_ends(nat.task_id, PHASES[:6]))  # committed without P7
    write_phase_ends(nat.root, phase_ends(nat.task_id), commit=False)  # P7 in the working tree only
    no_p7 = rf"NP-90: {LOG_AT} has no line for its phase P7; "
    _refused(nat, docker, no_p7)
    other = tmp_path / "other"  # a repository whose HEAD commit holds the whole log, and a natural index with NP-90's row
    other.mkdir()
    init_git(other)
    write_phase_ends(other, phase_ends(nat.task_id))
    shutil.copytree(nat.index.parent, other / INDEX.parent, dirs_exist_ok=True)
    git(other, "add", "--", INDEX.as_posix())
    git(other, "commit", "-q", "--no-verify", "-m", "natural index (synthetic fixture)")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    _refused(nat, docker, no_p7)
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    write_phase_ends(nat.root, phase_ends(nat.task_id))  # P7 committed
    (nat.root / PHASE_ENDS).write_text("not a phase-end log\n", encoding="utf-8")  # the working tree's log: not read
    _labelled(nat, docker)


@pytest.mark.parametrize("case, why", [
    ("not committed", r"git gives no text for it from the HEAD commit: .*its HEAD commit does not hold the file"),
    ("not JSON", r"its line 3 is not JSON"),
    ("not an object", r"its line 2 is not a JSON object"),
    ("another schema", (r'its line 1 is not a record of tracecontract/natural-phase-end/v1 \(its schema is '
                        r'"tracecontract/natural-phase-end/v0"\)')),
    ("no task", r"its line 4 names no task \(its task_id is null\)"),
    ("phase P8", r'its line 7 records the phase "P8", not one of P1, P2, P3, P4, P5, P6, P7'),
    ("no time zone", r'its line 5 records no time with a time zone \(its recorded_at is "2026-11-22T05:00:00"\)'),
    ("another task's line", r'its line 8 records the phase "P0", not one of P1'),
])
def test_an_unreadable_or_malformed_committed_phase_end_log_refuses(nat, monkeypatch, case, why):
    """Fail closed: a log that git does not give from the HEAD commit, or that holds one line that is not a phase-end
    record (of any task), shows nothing, even though NP-90's seven lines are there."""
    docker = Docker(monkeypatch, nat)
    lines: list = phase_ends(nat.task_id)
    if case == "not committed":
        git(nat.root, "rm", "-q", "--", PHASE_ENDS.as_posix())
        git(nat.root, "commit", "-q", "--no-verify", "-m", "no phase-end log (synthetic fixture)")
        write_phase_ends(nat.root, lines, commit=False)  # the whole log, in the working tree only
    else:
        if case == "not JSON":
            lines.insert(2, '{"schema": "tracecontract/natural-phase-end/v1", "task_id": "NP-90",')
        elif case == "not an object":
            lines.insert(1, json.dumps(["NP-90", "P1"]))
        elif case == "another schema":
            lines[0]["schema"] = "tracecontract/natural-phase-end/v0"
        elif case == "no task":
            lines[3]["task_id"] = None
        elif case == "phase P8":
            lines[6]["phase"] = "P8"
        elif case == "no time zone":
            lines[4]["recorded_at"] = "2026-11-22T05:00:00"
        else:
            lines.append(phase_end_line("NP-91", "P0", "2026-11-22T08:00:00Z"))
        write_phase_ends(nat.root, lines)
    _refused(nat, docker, rf"NP-90: natural: {LOG_AT} cannot be read \({why}.*\), so nothing shows that NP-90 ended the "
                          r"phases P1 to P7 in order; D19 and the run of a natural family need them \(decision log D65, "
                          r"D73\)$")


def test_every_problem_of_the_gate_is_reported(nat, monkeypatch):
    """Building has not stopped for the first sample and the phase-end log lacks P7: one refusal names both."""
    docker = Docker(monkeypatch, nat)
    _index(nat, s9_complete={"extension": EXTENSION_DONE})
    write_phase_ends(nat.root, phase_ends(nat.task_id, PHASES[:6]))
    _refused(nat, docker, r"NP-90: natural: building has not stopped for the first sample by the committed index: .*; "
                          rf"{LOG_AT} has no line for its phase P7; ")


def test_a_natural_task_is_labelled_with_frozen_reference_checks_only(nat, monkeypatch):
    """The labels are tied to the reference checks frozen before the pool (§19.7, plan F6/F8): reference checks that were
    never frozen, or a frozen spec that records no time of freezing, are refused before anything is looked up."""
    docker = Docker(monkeypatch, nat)
    path = nat.task_dir / "verifiers" / "reference_check" / "spec.json"
    frozen = load(path, VerifierSpec)
    for spec in (frozen.model_copy(update={"frozen": False, "frozen_at": None, "checks_sha256": None}),
                 frozen.model_copy(update={"frozen_at": None})):
        dump(spec, path)
        before = _tree(nat.root)
        with pytest.raises(SystemExit, match=r"NP-90: the reference checks \(reference_check\) are not frozen"):
            pl.main(str(nat.task_dir))
        assert _tree(nat.root) == before and docker.grades == [] and docker.lookups == [] and docker.runs == 0


@pytest.mark.parametrize("failure", ["timed out", "not staged"])
def test_a_refusal_while_the_regression_norm_is_built_leaves_the_task_as_it_was(nat, monkeypatch, failure):
    """The overlay is built outside the task: a refusal on the reference (its patch cannot be staged, or the base tests do
    not complete on it) leaves no labels/ and no overlay behind, as its message says."""
    docker = Docker(monkeypatch, nat)
    if failure == "timed out":
        docker.reference_result = {"timed_out": True}
        match = r"nothing written: the base tests did not complete on the reference \(run 1 of 3: status 'completed', timed out\)"
    else:
        docker.stage_error = "patch failed to apply: synthetic"
        match = "nothing written: the reference patch could not be staged on the base snapshot"
    before = _tree(nat.root)
    with pytest.raises(SystemExit, match=match):
        pl.main(str(nat.task_dir))
    assert _tree(nat.root) == before and not (nat.task_dir / "labels").exists() and docker.grades == []


def test_the_overlay_graded_is_put_in_place_once_every_label_is_known(nat, monkeypatch):
    docker = Docker(monkeypatch, nat)
    pl.main(str(nat.task_dir))
    # Each run of the base tests on the reference and each regression-norm grade was given the subset's base files, while
    # the task had no labels/ yet: the overlay, the labels and the log are written after the last grade.
    assert docker.runs == 3 and len(docker.overlays) == 3 + 3 * 3 and all(o == OVERLAY_TREE for o in docker.overlays)
    assert docker.labels_seen == {False}
    assert _tree(nat.task_dir / OVERLAY) == OVERLAY_TREE
    # A second run replaces the overlay the same way, from the base, after its grades.
    (nat.task_dir / OVERLAY / "tests" / "stale.py").write_text("stale\n", encoding="utf-8")
    pl.main(str(nat.task_dir))
    assert _tree(nat.task_dir / OVERLAY) == OVERLAY_TREE and all(o == OVERLAY_TREE for o in docker.overlays)


def test_the_base_graded_is_the_base_checked(nat, monkeypatch):
    """A task directory not named after its task id (a copy, say) is graded on the base snapshot of its task id, the one
    that verify_snapshot checks, never on a directory named after the copy."""
    docker = Docker(monkeypatch, nat)
    copy = nat.tasks_root / f"{nat.task_id}-copy"
    shutil.copytree(nat.task_dir, copy)
    other = nat.snapshot_dir.with_name(copy.name)
    shutil.copytree(nat.snapshot_dir, other)
    (other / "fxnat" / "mod.py").write_text("changed\n", encoding="utf-8")
    pl.main(str(copy))
    assert {b for _, _, b in docker.grades} == {nat.snapshot_dir} and set(docker.staged) == {nat.snapshot_dir}
    # The checked base is the task id's: modified, it is refused, though an intact snapshot is named after the copy.
    shutil.rmtree(other)
    shutil.copytree(nat.snapshot_dir, other)
    (nat.snapshot_dir / "fxnat" / "mod.py").write_text("changed\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="base snapshot missing or modified"):
        pl.main(str(copy))


def test_an_unusable_snapshot_root_is_refused_before_anything_happens(nat, monkeypatch):
    docker = Docker(monkeypatch, nat)
    for rel, why in (("../outside", "leaves the repository"), ("/abs/snapshots", "must be a path relative to the repository"),
                     ("tasks/x", "lies under tasks/")):
        _set_snapshot_root(nat, rel)
        before = _tree(nat.root)
        with pytest.raises(SystemExit, match=f"propose_labels refused, nothing written: NP-90: .*{why}"):
            pl.main(str(nat.task_dir))
        assert _tree(nat.root) == before and docker.grades == [] and docker.lookups == []


def test_no_label_is_written_through_a_symbolic_link(nat, monkeypatch, tmp_path):
    docker = Docker(monkeypatch, nat)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (nat.task_dir / "labels").symlink_to(elsewhere, target_is_directory=True)  # labels/ itself
    with pytest.raises(SystemExit, match=r"labels is a symbolic link"):
        pl.main(str(nat.task_dir))
    assert list(elsewhere.iterdir()) == []
    (nat.task_dir / "labels").unlink()
    (nat.task_dir / "labels").mkdir()
    (nat.task_dir / OVERLAY).symlink_to(elsewhere, target_is_directory=True)  # the overlay
    with pytest.raises(SystemExit, match=r"base_tests_overlay is a symbolic link"):
        pl.main(str(nat.task_dir))
    assert list(elsewhere.iterdir()) == [] and docker.grades == [] and docker.lookups == []
    assert sorted(p.name for p in (nat.task_dir / "labels").iterdir()) == ["base_tests_overlay"]


def test_combine_repeats():
    one = ("invalid", ["R2"], "natural candidate fails reference checks and/or regression norm")
    assert pl.combine_repeats([one]) == one and pl.combine_repeats([one, one, one]) == one
    other = ("invalid", ["R1"], one[2])
    value, violated, why = pl.combine_repeats([one, other, one])
    assert (value, violated) == ("ambiguous", []) and why.startswith("the 3 repeats give different proposals")
    amb = ("ambiguous", [], "reference checks did not produce a decision")
    assert pl.combine_repeats([amb, ("ambiguous", [], "another reason")])[0] == "ambiguous"


# --------------------------------------------------------------------------- duplicates


def test_the_pre_review_state_is_the_representative_of_its_duplicates(nat, monkeypatch):
    monkeypatch.setattr(fd, "REPO", nat.root)
    assert fd.main(str(nat.task_dir)) == 0
    rec = json.loads((nat.task_dir / "labels" / "duplicates.json").read_text())
    pre, nm, attack = (nat.candidate_id(k) for k in ("pre-review", "eval-nm-1", "dev-attack-full_session-a1"))
    # The near miss sorts before the pre-review state by id, but the state ranks first: the near miss is its duplicate.
    assert rec["duplicates"] == {pre: {"same_code_as_dev": [attack]}, nm: {"same_code_as_dev": [attack], "same_code_as_heldout": [pre]}}
    assert rec["snapshot_manifest_sha256"] == json.loads((nat.task_dir / "snapshot.json").read_text())["file_manifest_sha256"]
    assert fd.main(str(nat.task_dir), "--check") == 0
    from tracecontract.duplicates import representative_order

    held = [load(nat.task_dir / "candidates" / f"{c}.json", Candidate) for c in (nm, pre)]
    assert [c.candidate_id for c in sorted(held, key=representative_order)] == [pre, nm]


def test_find_duplicates_reads_the_natural_snapshot_root(nat, monkeypatch, capsys):
    monkeypatch.setattr(fd, "REPO", nat.root)
    shutil.copytree(nat.root / "data" / "natural" / "snapshots", nat.root / "snapshots")  # never read for a natural task
    (nat.snapshot_dir / "fxnat" / "mod.py").write_text("changed\n", encoding="utf-8")
    assert fd.main(str(nat.task_dir)) == 1
    assert "compile-pr-task" in capsys.readouterr().out and not (nat.task_dir / "labels" / "duplicates.json").exists()


def test_find_duplicates_refuses_an_unusable_snapshot_root(nat, monkeypatch, capsys):
    monkeypatch.setattr(fd, "REPO", nat.root)
    _set_snapshot_root(nat, "../outside")
    assert fd.main(str(nat.task_dir)) == 1
    assert "snapshot_root '../outside' leaves the repository" in capsys.readouterr().out
    assert not (nat.task_dir / "labels").exists()


def test_find_duplicates_writes_no_record_through_a_symbolic_link(nat, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(fd, "REPO", nat.root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (nat.task_dir / "labels").mkdir()
    (nat.task_dir / "labels" / "duplicates.json").symlink_to(elsewhere / "duplicates.json")  # the record
    assert fd.main(str(nat.task_dir)) == 1
    assert "duplicates.json is a symbolic link" in capsys.readouterr().out
    (nat.task_dir / "labels" / "duplicates.json").unlink()
    (nat.task_dir / "labels").rmdir()
    (nat.task_dir / "labels").symlink_to(elsewhere, target_is_directory=True)  # the directory that holds it
    assert fd.main(str(nat.task_dir)) == 1
    assert "labels is a symbolic link" in capsys.readouterr().out
    assert list(elsewhere.iterdir()) == []


# --------------------------------------------------------------------------- review packet


def _reference_contract(nt: NaturalTask) -> None:
    ev = {"R1": (nt.event("issue"), ISSUE_TEXT), "R2": (nt.event("comment"), COMMENT_TEXT)}
    reqs = [Requirement(req_id=r, statement=f"synthetic requirement {r}", kind=RequirementKind.change,
                        status=RequirementStatus.explicit, introduced_at=eid,
                        evidence=[EvidenceSpan(event_id=eid, start=0, end=12, quote=text[:12])], proposer="fixture")
            for r, (eid, text) in ev.items()]
    dump(TaskContract(contract_id=f"{nt.task_id}-reference", task_id=nt.task_id, session_id=nt.session_id,
                      variant=ContractVariant.reference, requirements=reqs, created_by="fixture", created_at=T0),
         nt.task_dir / "contracts" / "reference.json")
    m = load(nt.task_dir / "task.json", TaskManifest)
    dump(m.model_copy(update={"contracts": {"reference": "contracts/reference.json"}}), nt.task_dir / "task.json")


def test_a_natural_packet_is_blind_and_scores_the_pre_review_state_as_pre_correction(nat, tmp_path):
    _reference_contract(nat)
    snapshots = nat.root / "data" / "natural" / "snapshots"
    out, key = tmp_path / "packet", tmp_path / "coordinator" / "key.json"
    res = export_packet([nat.task_dir], out, key, snapshot_root=snapshots, repo_root=nat.root, seed=3)
    assert res["items"] == 3 and res["candidates"] == 3  # the pre-review state, the alternative and the near miss
    session = (out / nat.task_id / "session.txt").read_text()
    assert ISSUE_TEXT in session and COMMENT_TEXT in session and REPLY_TEXT in session
    for leak in (*AGENT_ONLY_MARKERS, HUNK_TEXT):  # neither the agent's texts nor the reviewed code
        assert leak not in session
    text = "\n".join(p.read_text(errors="replace") for p in out.rglob("*") if p.is_file())
    for leak in ("natural_pre_review", "pre-review", "eval-nm", "eval-alt", "constructed_near_miss", "valid_alternative"):
        assert leak not in text, leak
    readme = (out / "README.md").read_text()
    assert "Tasks from public pull-request threads" in readme
    # These tasks are not under tasks/: the README gives the task argument that sandbox-python takes for them.
    assert "    tracecontract sandbox-python data/natural/tasks/<task> <packet>/<task>/candidates/<id>/state -c '...'\n" in readme
    items = json.loads(key.read_text())["tasks"][nat.task_id]
    pre_id = next(o for o, cids in items.items() if nat.candidate_id("pre-review") in cids)
    tmpl = json.loads((out / nat.task_id / TEMPLATE).read_text())
    files = []
    for rev in ("R1", "R2"):
        d = dict(tmpl, reviewer=rev, contract_reviews={r: {"decision": "accept", "note": ""} for r in tmpl["contract_reviews"]})
        d["labels"] = {oid: {"value": "invalid" if oid == pre_id else "valid", "violated_requirements": ["R2"] if oid == pre_id else [],
                             "origin_guess": "pre-correction" if oid == pre_id else "unsure", "note": "n"} for oid in tmpl["labels"]}
        f = out / nat.task_id / f"labels_{rev}.json"
        f.write_text(json.dumps(d))
        files.append(f)
    rep = merge_labels(files, key, nat.tasks_root, dry_run=True)
    assert rep["origin_guesses"] == {"R1": {"correct": 1, "wrong": 0, "unsure": 2}, "R2": {"correct": 1, "wrong": 0, "unsure": 2}}
    assert origin_class(CandidateOrigin.natural_pre_review) == origin_class(CandidateOrigin.observed_pre_correction) == "pre-correction"
    assert origin_class(CandidateOrigin.fresh_attempt) == "other"


def test_a_packet_inside_the_repository_is_refused(nat, tmp_path, monkeypatch):
    _reference_contract(nat)
    snapshots = nat.root / "data" / "natural" / "snapshots"
    before = _tree(nat.root)
    for out in (nat.root / "data" / "natural" / "packet", nat.root / "packet", nat.root):  # git-ignored or not
        with pytest.raises(ValueError, match="lies inside the repository"):
            export_packet([nat.task_dir], out, tmp_path / "key.json", snapshot_root=snapshots, repo_root=nat.root, seed=1)
    assert _tree(nat.root) == before and not (tmp_path / "key.json").exists()
    # The study repository too, whatever repository the packet is read from; and through a link that leads into it.
    study = tmp_path / "study"
    study.mkdir()
    monkeypatch.setattr(roots, "REPO", study)
    assert "lies inside the repository" in packet_location_problem(study / "data" / "natural" / "p", nat.root)
    (tmp_path / "link").symlink_to(study, target_is_directory=True)
    assert "lies inside the repository" in packet_location_problem(tmp_path / "link" / "p", nat.root)
    assert packet_location_problem(tmp_path / "elsewhere", nat.root) is None
    # A path spelled through the repository is judged where it leads: ".." out of it is outside, ".." within it inside.
    assert packet_location_problem(nat.root / ".." / "elsewhere", nat.root) is None
    assert "lies inside the repository" in packet_location_problem(nat.root / "data" / ".." / "p", nat.root)
    assert "lies inside the repository" in packet_location_problem(Path(os.path.relpath(nat.root / "p")), nat.root)


def test_a_natural_packet_needs_the_reference_contract_and_the_natural_snapshot(nat, tmp_path):
    snapshots = nat.root / "data" / "natural" / "snapshots"
    with pytest.raises(ValueError, match="no reference contract"):
        export_packet([nat.task_dir], tmp_path / "p1", tmp_path / "k1.json", snapshot_root=snapshots, repo_root=nat.root, seed=1)
    _reference_contract(nat)
    with pytest.raises(ValueError, match="base snapshot missing or modified.*compile-pr-task"):
        export_packet([nat.task_dir], tmp_path / "p2", tmp_path / "k2.json", snapshot_root=nat.root / "snapshots",
                      repo_root=nat.root, seed=1)
    assert not any((tmp_path / p).exists() for p in ("p1", "p2", "k1.json", "k2.json"))


# --------------------------------------------------------------------------- review queue and construction checks


def test_the_review_queue_of_a_natural_task_shows_the_source_evidence(nat, monkeypatch):
    Docker(monkeypatch, nat)
    pl.main(str(nat.task_dir))
    wrq.main(str(nat.task_dir))
    q = json.loads((nat.task_dir / "labels" / "review_queue.json").read_text())
    pre = nat.candidate_id("pre-review")
    row = next(r for r in q["review_queue"] if r["candidate"] == pre)
    assert (row["proposed"], row["reason"]) == ("ambiguous", "ambiguous under D19")
    assert row["source_evidence"]["value"] == "invalid" and "not a human label" in row["source_evidence"]["note"]
    assert {r["candidate"] for r in q["candidates"] if "source_evidence" in r} == {pre}


def _check_journal(nt: NaturalTask, tmp_path: Path) -> Path:
    """A held-out workflow run's transcript directory whose checker checked the pre-review state and the pool."""
    wf = tmp_path / "wf_check"
    wf.mkdir()
    checks = [{"candidate_id": nt.candidate_id("pre-review"), "verdict": "confirmed", "violated_requirements": ["R2"],
               "claimed": "invalid", "evidence": "synthetic"},
              {"candidate_id": nt.candidate_id("eval-alt-1"), "verdict": "confirmed", "claimed": "valid"},
              {"candidate_id": nt.candidate_id("eval-nm-1"), "verdict": "not_confirmed", "violated_requirements": []}]
    rows = [{"type": "started", "agentId": "a1", "label": f"check:{nt.task_id}"},
            {"type": "result", "agentId": "a1", "result": json.dumps({"checks": checks})}]
    (wf / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return wf


def test_the_review_queue_and_the_construction_checks_are_not_written_through_a_link(nat, tmp_path):
    wf, elsewhere = _check_journal(nat, tmp_path), tmp_path / "elsewhere"
    elsewhere.mkdir()
    (nat.task_dir / "labels").symlink_to(elsewhere, target_is_directory=True)  # labels/ itself
    with pytest.raises(SystemExit, match=r"write_review_queue refused, nothing written: .*labels is a symbolic link"):
        wrq.main(str(nat.task_dir))
    with pytest.raises(SystemExit, match=r"record_construction_checks refused, nothing written: .*labels is a symbolic link"):
        rcc.cli([str(wf), "--tasks-root", str(nat.tasks_root)])
    assert list(elsewhere.iterdir()) == []
    (nat.task_dir / "labels").unlink()
    (nat.task_dir / "labels").mkdir()
    for name in ("review_queue.json", "construction_checks.json"):  # the records
        (nat.task_dir / "labels" / name).symlink_to(elsewhere / name)
    with pytest.raises(SystemExit, match=r"review_queue.json is a symbolic link"):
        wrq.main(str(nat.task_dir))
    with pytest.raises(SystemExit, match=r"construction_checks.json is a symbolic link"):
        rcc.cli([str(wf), "--tasks-root", str(nat.tasks_root)])
    assert list(elsewhere.iterdir()) == []


def test_construction_checks_are_recorded_under_the_given_tasks_root(nat, tmp_path):
    wf = _check_journal(nat, tmp_path)
    # The default root is the repository's tasks/, which holds no natural task: refused, nothing written.
    with pytest.raises(SystemExit, match="has no file under .*--tasks-root data/natural/tasks"):
        rcc.main(str(wf))
    assert not (ROOT / "tasks" / nat.task_id).exists()
    rcc.cli([str(wf), "--tasks-root", str(nat.tasks_root)])
    rec = json.loads((nat.task_dir / "labels" / "construction_checks.json").read_text())["checks"]
    assert {cid: (r["assessed_label"], r["matches_claim"]) for cid, r in rec.items()} == {
        nat.candidate_id("pre-review"): ("invalid", "yes"), nat.candidate_id("eval-alt-1"): ("valid", "yes"),
        nat.candidate_id("eval-nm-1"): ("valid", "no")}
    assert all(r["source"] == "wf_check/a1" for r in rec.values())
