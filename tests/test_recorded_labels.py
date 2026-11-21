"""The recorded D19 labels of CS-01 to CS-04 and of their fresh-v1 strata, reproduced by the code paths that made them.

* The pilot's labels came from ``scripts/propose_labels.py tasks/<id> <base test paths>`` (2026-11-18): the base test paths
  rebuild ``labels/base_tests_overlay`` from the base snapshot, and the task's own held-out candidates are labelled.
* The fresh-v1 labels came from ``scripts/propose_labels.py tasks/<id> --stratum fresh-v1`` (D58): the regression norm is
  the recorded overlay, read and never rewritten, and the stratum's candidates are labelled in their own files.

Each path runs here on a scratch copy of the task, with the default of one repeat, and with stubs in place of Docker:
the image build, the in-process run of the base tests on the reference, and the grader, which gives each candidate the
outcomes and failing checks that its recorded log entry holds. The labels, the label notes, the logs and the overlay must
come out as recorded, apart from the times; the base tests on the reference and every regression-norm grade must be given
the recorded overlay's files (rebuilt outside the task for the pilot path, read in place for the stratum path); and every
grade must be on the base snapshot that ``roots.snapshot_root`` names. Nothing is graded and nothing under ``tasks/`` is
written. The review queues
(``scripts/write_review_queue.py``) and, where the base snapshots are present, the same-code duplicates
(``scripts/find_duplicates.py``) are regenerated the same way.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tracecontract.schemas import CheckResult, Outcome, TaskManifest, VerificationResult, VerifierSpec
from tracecontract.store import load

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("CS-01", "CS-02", "CS-03", "CS-04")
LOG_KEYS = {"task_id", "labeler", "created_at", "candidates"}
STRATUM = "fresh-v1"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(f"recorded_{name}", ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pl = _script("propose_labels")


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*"))
            if p.is_file()}


def _base_test_paths(m: TaskManifest) -> list[str]:
    """The base test paths the pilot labelled with: the task's repository-test arguments without pytest's options."""
    args, out, skip = list(m.repo_test_args or []), [], False
    for a in args:
        if skip:
            skip = False
        elif a == "-o":
            skip = True
        elif not a.startswith("-"):
            out.append(a)
    return out


def _stub(monkeypatch, td: Path, log: dict, repo: Path) -> dict[str, list]:
    """Replace Docker by the recorded outcomes of ``log`` (a proposed_labels.json) and point the snapshot root at ``repo``.

    Recorded: each image build; each run of the base tests on the reference (the overlay's path and its files at the time);
    each grade (verifier, candidate, base snapshot); and the files of the overlay each regression-norm grade was given."""
    calls: dict[str, list] = {"build": [], "reference_runs": [], "grades": [], "regression_overlays": []}
    ws = repo.parent / "ws"
    entries = log["candidates"]
    regression_ids = sorted({x for e in entries.values() for x in e["regression_failed"]} | {"tests::stub_passing"})

    def build_env_image(reqs, cache):
        calls["build"].append(list(reqs))
        return "tc-fixture:0", "sha256:" + "0" * 64

    def prepare_workspace(base, patch, *a, **k):
        ws.mkdir(exist_ok=True)
        return ws, [], None

    def run_grader(tag, *, workspace, mode, overlay_dir, **_):  # the base tests on the reference, in process
        calls["reference_runs"].append((Path(overlay_dir), _tree(Path(overlay_dir))))
        tests = [{"nodeid": n, "outcome": "passed"} for n in regression_ids]
        return SimpleNamespace(results={"nonce": "n0", "status": "completed", "tests": tests}, timed_out=False), "n0"

    def verify_candidate(*, spec: VerifierSpec, candidate, base_dir, task_dir, **_):
        e = entries[candidate.candidate_id]
        calls["grades"].append((spec.verifier_id, candidate.candidate_id, Path(base_dir)))
        if spec.verifier_id == "reference_check":
            outcome, failed = e["refcheck_outcome"], set(e["refcheck_failed"])
        else:
            assert spec.verifier_id == "regression_norm" and [c.check_id for c in spec.checks] == regression_ids
            calls["regression_overlays"].append(_tree(Path(task_dir) / spec.test_dir))
            outcome, failed = e["regression_outcome"], set(e["regression_failed"])
        ids = [c.check_id for c in spec.checks]
        assert failed <= set(ids), (candidate.candidate_id, sorted(failed - set(ids)))
        checks = [CheckResult(check_id=c, status="failed" if c in failed else "passed") for c in ids]
        return VerificationResult(run_id="labels", task_id=spec.task_id, verifier_id=spec.verifier_id,
                                  candidate_id=candidate.candidate_id, outcome=Outcome(outcome), reward=float(outcome == "pass"), checks=checks,
                                  started_at="t", finished_at="t", wall_s=0.0, harness_version="stub")

    for name, fn in (("build_env_image", build_env_image), ("prepare_workspace", prepare_workspace),
                     ("run_grader", run_grader), ("verify_candidate", verify_candidate)):
        monkeypatch.setattr(pl, name, fn)
    monkeypatch.setattr(pl, "REPO", repo)
    return calls


def _same_record(new: Path, recorded: Path) -> None:
    """A candidate file as recorded, apart from the time of its D19 proposal (its last label)."""
    a, b = json.loads(new.read_text()), json.loads(recorded.read_text())
    assert a["labels"][-1]["labeler"] == pl.LABELER and b["labels"][-1]["labeler"] == pl.LABELER
    a["labels"][-1]["timestamp"] = b["labels"][-1]["timestamp"]
    assert a == b, new.name


def _same_log(new: dict, recorded: dict) -> None:
    assert set(new) == set(recorded)
    assert {k: v for k, v in new.items() if k != "created_at"} == {k: v for k, v in recorded.items() if k != "created_at"}


@pytest.mark.parametrize("tid", TASKS)
def test_the_pilot_labels_are_reproduced_by_the_base_test_path_run(tid, tmp_path, monkeypatch):
    src = ROOT / "tasks" / tid
    recorded_log = json.loads((src / "labels" / "proposed_labels.json").read_text())
    assert set(recorded_log) == LOG_KEYS
    td = tmp_path / "tasks" / tid
    shutil.copytree(src, td)
    m = load(td / "task.json", TaskManifest)
    paths = _base_test_paths(m)
    # The base snapshot holds the base commit's test files, which the recorded overlay is a copy of.
    repo = tmp_path / "repo"
    shutil.copytree(src / "labels" / "base_tests_overlay", repo / "snapshots" / tid)
    shutil.rmtree(td / "labels" / "base_tests_overlay")  # rebuilt from the base test paths
    before = _tree(td)
    calls = _stub(monkeypatch, td, recorded_log, repo)
    pl.main(str(td), *paths)
    _same_log(json.loads((td / "labels" / "proposed_labels.json").read_text()), recorded_log)
    for cid in recorded_log["candidates"]:
        _same_record(td / "candidates" / f"{cid}.json", src / "candidates" / f"{cid}.json")
    assert _tree(td / "labels" / "base_tests_overlay") == _tree(src / "labels" / "base_tests_overlay")
    after = _tree(td)
    changed = {k for k in after if before.get(k) != after[k]}
    assert changed == {f"candidates/{cid}.json" for cid in recorded_log["candidates"]} | {"labels/proposed_labels.json"} | {
        f"labels/base_tests_overlay/{k}" for k in _tree(src / "labels" / "base_tests_overlay")}
    # One image, one run of the base tests on the reference (one repeat), two grades per held-out candidate, on the
    # base snapshot that roots.snapshot_root names for a controlled task. The reference run and the regression-norm grades
    # were given the recorded overlay's files, rebuilt outside the task and put in place after the last grade.
    recorded_overlay = _tree(src / "labels" / "base_tests_overlay")
    assert len(calls["build"]) == 1 and [files for _, files in calls["reference_runs"]] == [recorded_overlay]
    assert all(td not in path.parents for path, _ in calls["reference_runs"])
    assert calls["regression_overlays"] == [recorded_overlay] * len(recorded_log["candidates"])
    assert len(calls["grades"]) == 2 * len(recorded_log["candidates"])
    assert {g[2] for g in calls["grades"]} == {repo / "snapshots" / tid}


@pytest.mark.parametrize("tid", TASKS)
def test_the_fresh_v1_labels_are_reproduced_by_the_stratum_run(tid, tmp_path, monkeypatch):
    src = ROOT / "tasks" / tid
    recorded_log = json.loads((src / "strata" / STRATUM / "proposed_labels.json").read_text())
    assert set(recorded_log) == LOG_KEYS | {"stratum", "regression_overlay"}
    td = tmp_path / "tasks" / tid
    shutil.copytree(src, td)
    before = _tree(td)
    repo = tmp_path / "repo"
    calls = _stub(monkeypatch, td, recorded_log, repo)
    pl.main(str(td), stratum=STRATUM)
    _same_log(json.loads((td / "strata" / STRATUM / "proposed_labels.json").read_text()), recorded_log)
    for cid in recorded_log["candidates"]:
        _same_record(td / "strata" / STRATUM / "candidates" / f"{cid}.json", src / "strata" / STRATUM / "candidates" / f"{cid}.json")
    after = _tree(td)
    changed = {k for k in after if before.get(k) != after[k]}
    assert changed == {f"strata/{STRATUM}/candidates/{cid}.json" for cid in recorded_log["candidates"]} | {
        f"strata/{STRATUM}/proposed_labels.json"}  # the overlay, task.json and the task's own candidates are untouched
    # The regression norm is the recorded overlay, read where it is; every grade is on the base snapshot that
    # roots.snapshot_root names for a controlled task.
    recorded_overlay = _tree(src / "labels" / "base_tests_overlay")
    assert calls["reference_runs"] == [(td / "labels" / "base_tests_overlay", recorded_overlay)]
    assert calls["regression_overlays"] == [recorded_overlay] * len(recorded_log["candidates"])
    assert len(calls["grades"]) == 2 * len(recorded_log["candidates"])
    assert {g[2] for g in calls["grades"]} == {repo / "snapshots" / tid}


def test_the_review_queues_are_reproduced(tmp_path):
    wrq = _script("write_review_queue")
    copies = []
    for tid in TASKS:
        shutil.copytree(ROOT / "tasks" / tid, tmp_path / tid)
        copies.append(tmp_path / tid)
    wrq.main(*map(str, copies))
    for tid in TASKS:
        assert (tmp_path / tid / "labels" / "review_queue.json").read_bytes() == (
            ROOT / "tasks" / tid / "labels" / "review_queue.json").read_bytes(), tid


@pytest.mark.skipif(not all((ROOT / "snapshots" / t).is_dir() for t in TASKS), reason="base snapshots not built here")
def test_the_same_code_duplicates_are_reproduced(tmp_path):
    from tracecontract.duplicates import same_code_duplicates

    fd = _script("find_duplicates")
    for tid in TASKS:
        rec = same_code_duplicates(ROOT / "tasks" / tid)  # the snapshot root roots.snapshot_root names: snapshots/
        text = json.dumps(rec, indent=2, sort_keys=True) + "\n"
        assert text == (ROOT / "tasks" / tid / "labels" / "duplicates.json").read_text(), tid
    assert fd.main(*(str(ROOT / "tasks" / t) for t in TASKS), "--check") == 0  # --check writes nothing
