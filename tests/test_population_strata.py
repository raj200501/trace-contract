"""Population strata and candidate strata in evaluation and analysis.

* The analysis refuses a run whose tasks come from more than one population (here a natural and
  a controlled fixture task) unless ``pool_populations`` (``--pool-populations``) is set; with it,
  each population is reported on its own rows and the output says that the tables pool them.
* A candidate stratum (``tasks/<id>/strata/<name>.json``) adds candidates to a task's pool for
  ``evaluate --strata`` without changing ``task.json`` or the task's candidate files; the run
  manifest records each graded candidate's stratum and file, and the analysis reports each
  stratum separately.
* The two natural sub-populations (``natural:pr-review``, ``natural:chat``) are populations of
  their own: a run that mixes them is refused or pooled with each reported separately.
* A symbolic link at ``strata/``, ``strata/<name>/`` or ``strata/<name>/candidates/`` is refused.
* ``tracecontract add-stratum-candidate`` captures a candidate from a state directory with the
  patch policy, writes the stratum's candidate file and manifest, keeps the attempt record of a
  fresh attempt, and never touches ``task.json``.
* A run with the default population (controlled) and no stratum keeps the earlier output format,
  so the frozen pilot regenerates byte for byte.

Synthetic fixtures only: the "natural" tasks are hand-written and only declare that population (no
natural data is read), and a stub replaces the Docker grader. One test regenerates the frozen
pilot's analysis from a temporary copy of its run records, reading the repository's tasks only.
These tests check code behaviour and are not research evidence.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import tracecontract.cli as cli
import tracecontract.evaluate as evaluate
from tracecontract.analysis import PILOT_LABELER, MixedPopulations, analyze
from tracecontract.schemas import (
    AttemptAudit, AttemptRecord, Candidate, CandidateOrigin, ContractVariant, EvidenceSpan, Fidelity, Label, LabelerKind,
    Outcome, Population, Requirement, RequirementKind, RequirementStatus, Snapshot, SnapshotSource, Split, TaskContract,
    TaskManifest, VerificationResult, VerifierCondition, sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, load, read_jsonl
from tracecontract.strata import StratumError, StratumManifest
from tracecontract.verifier import build_spec, freeze

REPO = Path(__file__).resolve().parents[1]
PILOT = REPO / "results" / "runs" / "pilot-v0.3.3"
NAT, CTL = "NAT-1", "CTL-1"
VERIFIERS = {"initial_plain": VerifierCondition.initial_plain, "full_audited": VerifierCondition.full_audited}
T0 = "2026-11-21T00:00:00+00:00"
# Candidate kind -> (origin, split, D19 proposal, violated requirements); ids are "<task id>-<kind>".
OWN = {"reference": (CandidateOrigin.reference, Split.dev, "valid", []),
       "pre": (CandidateOrigin.observed_pre_correction, Split.eval, "invalid", ["R-corr"]),
       "alt": (CandidateOrigin.valid_alternative, Split.eval, "valid", []),
       "nm": (CandidateOrigin.constructed_near_miss, Split.eval, "invalid", ["R-init"]),
       "noop-eval": (CandidateOrigin.noop, Split.eval, "invalid", [])}
FRESH = {"fresh-good": (CandidateOrigin.fresh_attempt, Split.eval, "valid", []),
         "fresh-bad": (CandidateOrigin.fresh_attempt, Split.eval, "invalid", ["R-corr"])}
SHA = "ab" * 32


def _attempt(cid: str, patch: str, *, passed: bool | None = True) -> AttemptRecord:
    """An attempt record of a fresh attempt; ``passed=None`` leaves it without an audit verdict."""
    audit = None if passed is None else AttemptAudit(profile="fresh-attempt:v1", passed=passed, audited_at=T0,
                                                     findings=[] if passed else ["read a file outside the workspace"])
    return AttemptRecord(attempt_id=f"att-{cid}", configuration="config-A", variant="u1", instruction_sha256=SHA,
                         started_at=T0, ended_at=T0, turns=3, tool_calls=7, ended="finished", patch_sha256=sha256_text(patch),
                         run_record="private-runs/fresh-v1/x.json", audit=audit)


def _passes(task_id: str, verifier_id: str, kind: str) -> bool:
    """Stub grading: the initial-only verifier accepts what the correction rules out; in NAT-1 the audited one misses a near miss."""
    if kind in ("reference", "alt", "fresh-good"):
        return True
    if verifier_id == "initial_plain":
        return kind in ("pre", "fresh-bad")
    return task_id == NAT and kind == "nm"


def _cand(path: Path, cid: str, task_id: str, origin: CandidateOrigin, split: Split, label: str, violated: list[str]) -> Candidate:
    patch = "" if origin == CandidateOrigin.noop else f"--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = 2  # {cid}\n"
    c = Candidate(candidate_id=cid, task_id=task_id, origin=origin, split=split, patch=patch, patch_sha256=sha256_text(patch),
                  produced_by="fixture", labels=[Label(value=label, violated_requirements=violated, labeler=PILOT_LABELER,
                                                       labeler_kind=LabelerKind.model, timestamp=T0)],
                  attempt=_attempt(cid, patch) if origin == CandidateOrigin.fresh_attempt else None)
    dump(c, path)
    return c


def _req(rid: str, kind: RequirementKind, event_id: str) -> Requirement:
    return Requirement(req_id=rid, statement=f"Statement of {rid}.", kind=kind, status=RequirementStatus.explicit,
                       introduced_at=event_id, evidence=[EvidenceSpan(event_id=event_id, start=0, end=1, quote="x")],
                       observable=f"check {rid}", proposer="fixture")


def _make_task(root: Path, tid: str, population: Population) -> Path:
    """A task laid out like the repository's under ``root``: tasks/<tid> with two frozen verifiers, and snapshots/<tid>."""
    td = root / "tasks" / tid
    first, later = f"{tid}-s/L000001.00", f"{tid}-s/L000005.00"
    dump(TaskContract(contract_id=f"{tid}-reference", task_id=tid, session_id=f"{tid}-s", variant=ContractVariant.reference,
                      created_by="fixture", created_at=T0,
                      requirements=[_req("R-init", RequirementKind.change, first), _req("R-corr", RequirementKind.invariant, later)]),
         td / "contracts" / "reference.json")
    for kind, spec in OWN.items():
        _cand(td / "candidates" / f"{tid}-{kind}.json", f"{tid}-{kind}", tid, *spec)
    base = root / "snapshots" / tid
    base.mkdir(parents=True)
    (base / "mod.py").write_text("X = 1\n")
    dump(Snapshot(snapshot_id=f"{tid}-base", task_id=tid, repo_url="https://example.invalid/fixture", base_commit="0" * 40,
                  fidelity=Fidelity.exact, file_manifest_sha256=manifest_sha256(manifest(base)), n_files=1), td / "snapshot.json")
    for vid, cond in VERIFIERS.items():
        tests = td / "verifiers" / vid / "tests"
        tests.mkdir(parents=True)
        (tests / "test_fixture.py").write_text("def test_value():\n    assert 1 + 1 == 2\n")
        dump(freeze(build_spec(verifier_id=vid, task_id=tid, condition=cond, test_dir=tests, task_dir=td), td),
             td / "verifiers" / vid / "spec.json")
    dump(TaskManifest(task_id=tid, family_id=tid, population=population, status="pending_review", provenance="provenance.json",
                      snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture", commit="0" * 40),
                      snapshot="snapshot.json", env_requirements=[], contracts={"reference": "contracts/reference.json"},
                      verifiers=[f"verifiers/{vid}/spec.json" for vid in VERIFIERS],
                      candidates=[f"candidates/{tid}-{kind}.json" for kind in OWN]),
         td / "task.json")
    return td


def _add_stratum(td: Path, name: str = "fresh", cands: dict | None = None, **fields) -> Path:
    """``strata/<name>.json`` listing ``cands`` (``{candidate id: (task id, origin, split, label, violated)}``)."""
    tid = td.name
    cands = cands if cands is not None else {f"{tid}-{k}": (tid, *v) for k, v in FRESH.items()}
    rels = []
    for cid, spec in cands.items():
        rel = f"strata/{name}/candidates/{cid}.json"
        _cand(td / rel, cid, *spec)
        rels.append(rel)
    path = td / "strata" / f"{name}.json"
    dump(StratumManifest(**{"stratum": name, "task_id": tid, "description": "fixture stratum", "candidates": rels, **fields}), path)
    return path


@pytest.fixture()
def graded(monkeypatch) -> list[tuple[str, str, str]]:
    """(task, verifier, candidate) of every pair the stub grader grades; the stub replaces Docker."""
    calls: list[tuple[str, str, str]] = []

    def stub(*, spec, task_dir, candidate, run_id, **_) -> VerificationResult:
        assert (task_dir / spec.test_dir / "test_fixture.py").is_file()  # graded by the task's own frozen verifier
        calls.append((task_dir.name, spec.verifier_id, candidate.candidate_id))
        ok = _passes(spec.task_id, spec.verifier_id, candidate.candidate_id[len(spec.task_id) + 1:])
        return VerificationResult(run_id=run_id, task_id=spec.task_id, verifier_id=spec.verifier_id,
                                  candidate_id=candidate.candidate_id, outcome=Outcome.passed if ok else Outcome.task_failure,
                                  reward=1.0 if ok else 0.0, started_at=T0, finished_at=T0, wall_s=0.0, harness_version="stub")

    monkeypatch.setattr(evaluate, "verify_candidate", stub)
    monkeypatch.setattr(evaluate, "build_env_image", lambda reqs, cache: ("tc-fixture:0", "sha256:" + "0" * 64))
    return calls


@pytest.fixture()
def repo(tmp_path, monkeypatch, graded) -> Path:
    """A scratch repository root for the CLI (tasks/, snapshots/, results/runs/)."""
    monkeypatch.setattr(cli, "REPO", tmp_path)
    monkeypatch.setattr(cli, "SNAPSHOTS", tmp_path / "snapshots")
    monkeypatch.setattr(cli, "CACHE", tmp_path / "cache")
    return tmp_path


def _exit_code(argv: list[str]) -> int | str | None:
    """The CLI's exit code: 0 when it returns, else the SystemExit code (a message string exits with status 1)."""
    try:
        cli.main(argv)
    except SystemExit as exc:
        return exc.code
    return 0


def _evaluate(repo: Path, tasks: list[Path], run_id: str, *extra: str) -> Path:
    assert _exit_code(["evaluate", *map(str, tasks), "--run-id", run_id, "--pilot", *extra]) == 0
    return repo / "results" / "runs" / run_id


def _rate(d: dict, cond: str, metric: str) -> tuple[int, int]:
    x = d["conditions"][cond][metric]
    return x["num"], x["den"]


def _hashes(td: Path) -> dict[str, str]:
    """sha256 of task.json and of every file in candidates/: the records a stratum never changes."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [td / "task.json", *sorted((td / "candidates").iterdir())]}


# ---------------------------------------------------------------------------
# Population strata
# ---------------------------------------------------------------------------


def test_analysis_refuses_a_run_that_mixes_populations(repo):
    run = _evaluate(repo, [_make_task(repo, NAT, Population.natural), _make_task(repo, CTL, Population.controlled)], "r-mixed")
    with pytest.raises(MixedPopulations, match=r"2 populations \(controlled: CTL-1; natural: NAT-1\)"):
        analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)
    code = _exit_code(["analyze", str(run), "--allow-proposed-labels"])
    assert code not in (0, None) and "--pool-populations" in str(code)
    assert not (run / "analysis.json").exists() and not (run / "analysis.md").exists()  # refused before anything was written


def test_pooled_populations_are_also_reported_separately(repo, capsys):
    run = _evaluate(repo, [_make_task(repo, NAT, Population.natural), _make_task(repo, CTL, Population.controlled)], "r-pooled")
    capsys.readouterr()
    assert _exit_code(["analyze", str(run), "--allow-proposed-labels", "--pool-populations", "--n-boot", "50"]) == 0
    assert "pooled across 2 populations" in json.loads(capsys.readouterr().out)["population_pooling"]
    a = json.loads((run / "analysis.json").read_text())
    assert a["meta"]["populations"] == {"controlled": [CTL], "natural": [NAT]}
    assert "--pool-populations" in a["meta"]["population_pooling"]
    # The main tables pool both tasks; by_population has each population's rows and families only.
    assert _rate(a, "initial_plain", "false_acceptance") == (2, 4) and _rate(a, "full_audited", "false_acceptance") == (1, 4)
    nat, ctl = a["by_population"]["natural"], a["by_population"]["controlled"]
    assert (nat["tasks"], ctl["tasks"], nat["n_families"], ctl["n_families"]) == ([NAT], [CTL], 1, 1)
    assert _rate(nat, "full_audited", "false_acceptance") == (1, 2) and _rate(ctl, "full_audited", "false_acceptance") == (0, 2)
    assert _rate(nat, "initial_plain", "false_acceptance") == _rate(ctl, "initial_plain", "false_acceptance") == (1, 2)
    assert _rate(nat, "full_audited", "false_rejection") == _rate(ctl, "full_audited", "false_rejection") == (0, 1)
    md = (run / "analysis.md").read_text()
    assert "> **Populations pooled** (`--pool-populations`). This run mixes 2 populations (controlled: CTL-1; natural: NAT-1)." in md
    assert f"### natural (tasks: {NAT}; families: 1)" in md and f"### controlled (tasks: {CTL}; families: 1)" in md
    assert md.index("## False acceptance") < md.index("## By population") < md.index("## Accepted negatives by type")


def test_a_single_population_is_never_refused(repo):
    run = _evaluate(repo, [_make_task(repo, NAT, Population.natural)], "r-natural")
    a = analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)
    assert a["meta"]["populations"] == {"natural": [NAT]}  # named, since it is not the default population
    assert "population_pooling" not in a["meta"] and "by_population" not in a
    assert f"Population: natural: {NAT}." in (run / "analysis.md").read_text()


def test_the_natural_sub_populations_are_never_pooled_silently(repo, monkeypatch):
    """natural:pr-review (AIDev) and natural:chat (Trace Commons) are populations of their own (protocol v0.8 §16.3)."""
    tasks = [_make_task(repo, "PR-1", Population.natural_pr_review), _make_task(repo, "CH-1", Population.natural_chat)]
    # A natural:pr-review task enters a run only once its family has passed S10 (the acceptance gate refuses it otherwise),
    # and its run records go only to a git-ignored directory of the repository (§17.4): data/natural/runs here.
    from natural_task_layout import init_git

    (tasks[0] / "s10.json").write_text(json.dumps({"schema": "tracecontract/natural-s10/v1", "task_id": "PR-1", "stage": "S10",
                                                   "outcome": "passed"}), encoding="utf-8")
    init_git(repo)
    # ... and is graded only in the image its S10 step recorded (never rebuilt): record one, and let this host have it.
    image_id = "sha256:" + "1" * 64
    snap = json.loads((tasks[0] / "snapshot.json").read_text())
    snap["environment"] = {"image": evaluate.env_image_tag([]), "image_id": image_id}
    (tasks[0] / "snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setattr(evaluate, "local_image_id", lambda tag: image_id)
    out_root = repo / "data" / "natural" / "runs"
    assert _exit_code(["evaluate", *map(str, tasks), "--run-id", "r-subpops", "--pilot", "--out-root", str(out_root)]) == 0
    run = out_root / "r-subpops"
    with pytest.raises(MixedPopulations, match=r"2 populations \(natural:chat: CH-1; natural:pr-review: PR-1\)"):
        analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)
    a = analyze(run, repo / "tasks", allow_proposed=True, n_boot=50, pool_populations=True)
    assert {p: g["tasks"] for p, g in a["by_population"].items()} == {"natural:chat": ["CH-1"], "natural:pr-review": ["PR-1"]}


# ---------------------------------------------------------------------------
# Candidate strata
# ---------------------------------------------------------------------------


def test_a_stratum_grades_extra_candidates_and_never_changes_the_task(repo, graded):
    td = _make_task(repo, CTL, Population.controlled)
    stratum_file = _add_stratum(td)
    before = _hashes(td)
    run = _evaluate(repo, [td], "r-strata", "--strata", "fresh")
    assert _hashes(td) == before  # task.json and the task's candidate files keep their hashes
    own, fresh = [f"{CTL}-{k}" for k in OWN], [f"{CTL}-{k}" for k in FRESH]
    assert sorted((v, c) for _, v, c in graded) == sorted((v, c) for v in VERIFIERS for c in own + fresh)
    assert sorted((r.verifier_id, r.candidate_id) for r in read_jsonl(run / "results.jsonl", VerificationResult)) == \
        sorted((v, c) for v in VERIFIERS for c in own + fresh)
    m = json.loads((run / "manifest.json").read_text())
    entry = m["tasks"][0]
    assert entry["strata"] == {"fresh": {"manifest": "strata/fresh.json",
                                         "manifest_sha256": hashlib.sha256(stratum_file.read_bytes()).hexdigest()}}
    assert entry["candidates"][f"{CTL}-fresh-bad"] == {"origin": "fresh_attempt", "stratum": "fresh",
                                                        "path": f"strata/fresh/candidates/{CTL}-fresh-bad.json",
                                                        "patch_sha256": load(td / entry["candidates"][f"{CTL}-fresh-bad"]["path"],
                                                                             Candidate).patch_sha256}
    assert set(entry["candidates"][f"{CTL}-pre"]) == {"origin", "patch_sha256"}  # the task's own keep the earlier record
    assert (m["invocations"][-1]["strata"], m["invocations"][-1]["only_strata"]) == (["fresh"], False)

    a = analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)
    assert list(a["by_stratum"]) == ["task", "fresh"]
    own_s, fresh_s = a["by_stratum"]["task"], a["by_stratum"]["fresh"]
    assert _rate(own_s, "initial_plain", "false_acceptance") == (1, 2) and _rate(fresh_s, "initial_plain", "false_acceptance") == (1, 1)
    assert _rate(fresh_s, "full_audited", "false_acceptance") == (0, 1) and _rate(fresh_s, "full_audited", "false_rejection") == (0, 1)
    assert _rate(a, "initial_plain", "false_acceptance") == (2, 3)  # the main tables pool the strata
    rows = {r["candidate"]: r for r in a["per_task"][CTL]["initial_plain"]}
    assert (rows[f"{CTL}-fresh-bad"]["stratum"], rows[f"{CTL}-pre"]["stratum"]) == ("fresh", "task")
    assert a["meta"]["strata"] == {CTL: entry["strata"]}
    assert "populations" not in a["meta"] and "by_population" not in a  # one population, the default one
    files = a["meta"]["inputs"]["files_sha256"]
    assert f"{CTL}/strata/fresh/candidates/{CTL}-fresh-good.json" in files and "code/strata.py" in files
    assert [x["candidate"] for x in a["labels"][CTL]["strata"]["fresh"]["candidates"]] == sorted(fresh)
    md = (run / "analysis.md").read_text()
    assert "## By candidate stratum" in md and "| Candidate | Stratum | Origin |" in md
    assert f"| {CTL}-fresh-bad | fresh | fresh_attempt | invalid | correction_violating | pass | task_failure |" in md
    # Every fresh attempt is queued for human review (protocol §15.4); their solve rates are reported.
    assert f"| {CTL} (stratum fresh) | 1 | 1 | 0 | 0 | {CTL}-fresh-bad, {CTL}-fresh-good |" in md
    assert a["fresh_attempts"]["by_configuration_variant"]["config-A/u1"]["solved"] == 1
    assert a["fresh_attempts"]["n_excluded"] == 0


def test_only_strata_grades_the_strata_and_the_reference(repo, graded):
    td = _make_task(repo, CTL, Population.controlled)
    _add_stratum(td)
    run = _evaluate(repo, [td], "r-only", "--strata", "fresh", "--only-strata")
    assert sorted({c for _, _, c in graded}) == sorted([f"{CTL}-reference", *(f"{CTL}-{k}" for k in FRESH)])
    assert json.loads((run / "manifest.json").read_text())["invocations"][-1]["only_strata"] is True
    a = analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)
    assert list(a["by_stratum"]) == ["fresh"]  # the reference is the sanity check, not part of the pool
    assert a["sanity"]["full_audited"]["reference"] == {"pass": 1, "n": 1, "outcomes": {"pass": 1}}


GOOD = FRESH["fresh-good"]
STRATA = ["--strata", "fresh"]
# case: (stratum to add, as _add_stratum keyword arguments, or None for none; evaluate arguments; refusal)
INVALID = {
    "no such stratum": ({}, ["--strata", "other"], f"{CTL} has no stratum 'other'"),
    "path-like name": (None, ["--strata", "../fresh"], "invalid stratum name '../fresh'"),
    "reserved name": (None, ["--strata", "task"], "invalid stratum name 'task'"),
    "file outside the stratum": ({"cands": {}, "candidates": [f"candidates/{CTL}-alt.json"]}, STRATA,
                                 "is not strata/fresh/candidates/<file>.json"),
    "id of an own candidate": ({"cands": {f"{CTL}-pre": (CTL, *GOOD)}}, STRATA, "already used by the task's own candidates"),
    "reference solution": ({"cands": {f"{CTL}-ref2": (CTL, CandidateOrigin.reference, Split.dev, "valid", [])}}, STRATA,
                           "is a reference solution"),
    "manifest of another task": ({"task_id": NAT}, STRATA, f"describes stratum 'fresh' of task '{NAT}'"),
    "candidate of another task": ({"cands": {f"{CTL}-x": (NAT, *GOOD)}}, STRATA, f"is a candidate of task '{NAT}'"),
    "id without the task prefix": ({"cands": {"fresh-1": (CTL, *GOOD)}}, STRATA, f"does not start with '{CTL}-'"),
    "--only-strata alone": (None, ["--only-strata"], "needs at least one stratum"),
}


@pytest.mark.parametrize("case", list(INVALID))
def test_invalid_strata_are_refused_before_anything_is_written(repo, graded, case):
    td = _make_task(repo, CTL, Population.controlled)
    stratum, extra, message = INVALID[case]
    if stratum is not None:
        _add_stratum(td, **stratum)
    code = _exit_code(["evaluate", str(td), "--run-id", "r-bad", "--pilot", *extra])
    assert code not in (0, None) and message in str(code)
    assert not (repo / "results" / "runs" / "r-bad").exists() and not graded


def test_a_candidate_file_that_links_out_of_its_stratum_is_refused(repo, graded):
    td = _make_task(repo, CTL, Population.controlled)
    outside = _cand(td / "elsewhere" / f"{CTL}-out.json", f"{CTL}-out", CTL, *GOOD)
    link = td / "strata" / "fresh" / "candidates" / f"{outside.candidate_id}.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(td / "elsewhere" / f"{CTL}-out.json")
    _add_stratum(td, cands={}, candidates=[f"strata/fresh/candidates/{outside.candidate_id}.json"])
    code = _exit_code(["evaluate", str(td), "--run-id", "r-link", "--pilot", *STRATA])
    assert code not in (0, None) and "links out of strata/fresh/candidates/" in str(code)
    assert not (repo / "results" / "runs" / "r-link").exists() and not graded


def test_a_resumed_run_keeps_its_strata_and_refuses_a_changed_candidate(repo, graded):
    td = _make_task(repo, CTL, Population.controlled)
    _add_stratum(td)
    run = _evaluate(repo, [td], "r-resume", "--strata", "fresh")
    n = len(graded)
    _evaluate(repo, [td], "r-resume")  # resumed without --strata: nothing is graded again and the stratum stays recorded
    assert len(graded) == n
    entry = json.loads((run / "manifest.json").read_text())["tasks"][0]
    assert entry["candidates"][f"{CTL}-fresh-bad"]["stratum"] == "fresh" and list(entry["strata"]) == ["fresh"]
    assert _rate(analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)["by_stratum"]["fresh"],
                 "initial_plain", "false_acceptance") == (1, 1)
    # A stratum candidate whose patch changed after the run graded it is refused on resume and in the analysis.
    path = td / "strata" / "fresh" / "candidates" / f"{CTL}-fresh-bad.json"
    c = load(path, Candidate)
    patch = c.patch + "+# changed\n"
    dump(c.model_copy(update={"patch": patch, "patch_sha256": sha256_text(patch),
                              "attempt": c.attempt.model_copy(update={"patch_sha256": sha256_text(patch)})}), path)
    before = (run / "manifest.json").read_bytes()
    code = _exit_code(["evaluate", str(td), "--run-id", "r-resume", "--pilot", "--strata", "fresh"])
    assert code not in (0, None) and "is not the one this run recorded" in str(code)
    assert (run / "manifest.json").read_bytes() == before and len(graded) == n
    code = _exit_code(["analyze", str(run), "--allow-proposed-labels", "--n-boot", "50"])
    assert code not in (0, None) and "no longer holds the candidate" in str(code)
    with pytest.raises(StratumError, match=f"no longer holds the candidate {CTL}-fresh-bad"):
        analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)


@pytest.mark.parametrize("level", ["strata", "strata/fresh", "strata/fresh/candidates", "strata/fresh.json"])
def test_a_symlinked_stratum_directory_or_manifest_is_refused(repo, graded, level):
    """A link at any level would let candidate files from outside the task directory load (verification of round 4)."""
    td = _make_task(repo, CTL, Population.controlled)
    _add_stratum(td)
    real, elsewhere = td / level, repo / "elsewhere" / level
    elsewhere.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(real), str(elsewhere))
    real.symlink_to(elsewhere)
    code = _exit_code(["evaluate", str(td), "--run-id", "r-link-dir", "--pilot", *STRATA])
    assert code not in (0, None) and f"{level} is a symbolic link" in str(code)
    assert not (repo / "results" / "runs" / "r-link-dir").exists() and not graded


def _state(repo: Path, tid: str, name: str = "state", value: str = "3") -> Path:
    """A final workspace state: the base snapshot with mod.py changed, plus git metadata, caches and a test file."""
    st = repo / "attempts" / name
    shutil.copytree(repo / "snapshots" / tid, st)
    (st / "mod.py").write_text(f"X = {value}\n")
    (st / ".git").mkdir()
    (st / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (st / "__pycache__").mkdir()
    (st / "__pycache__" / "mod.cpython-313.pyc").write_bytes(b"\x00\x01")
    (st / "stray.pyc").write_bytes(b"\x00")
    (st / ".pytest_cache").mkdir()
    (st / ".pytest_cache" / "README.md").write_text("cache\n")
    (st / "tests").mkdir()
    (st / "tests" / "test_mod.py").write_text("def test_x():\n    assert True\n")
    return st


def _attempt_file(repo: Path, name: str = "attempt.json", **over) -> Path:
    rec = {"attempt_id": "fresh-v1-CTL-1-A-u1-1", "configuration": "config-A", "variant": "u1", "instruction_sha256": SHA,
           "started_at": T0, "ended_at": T0, "turns": 12, "tool_calls": 40, "tokens": 50000, "ended": "finished",
           "run_record": "private-runs/fresh-v1/CTL-1-A-u1-1.json"}
    path = repo / "attempts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**rec, **over}))
    return path


def _register(td: Path, st: Path, cid: str, *extra: str, stratum: str = "fresh-v1") -> int | str | None:
    return _exit_code(["add-stratum-candidate", str(td), stratum, cid, "--state-dir", str(st), *extra])


def test_add_stratum_candidate_captures_the_state_and_never_touches_task_json(repo, capsys):
    td = _make_task(repo, CTL, Population.controlled)
    before = _hashes(td)
    st = _state(repo, CTL)
    capsys.readouterr()
    code = _register(td, st, f"{CTL}-fa-1", "--origin", "fresh_attempt", "--attempt-record", str(_attempt_file(repo)),
                     "--stratum-description", "fresh-agent attempts (protocol §15.4)")
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    rel = f"strata/fresh-v1/candidates/{CTL}-fa-1.json"
    assert (out["candidate"], out["registered"], out["attempt_id"]) == (rel, "created", "fresh-v1-CTL-1-A-u1-1")
    assert out["removed_protected_paths"] == ["tests/test_mod.py"] and out["rejected_by_the_grader"] == []
    assert _hashes(td) == before  # task.json and the task's own candidate files keep their hashes
    c = load(td / rel, Candidate)
    assert (c.origin, c.split, c.produced_by, c.labels) == (CandidateOrigin.fresh_attempt, Split.eval, "fresh-attempt:config-A", [])
    assert c.patch.count("diff --git") == 1 and "+X = 3" in c.patch  # .git, caches and the protected test file left out
    for left_out in (".git", "pyc", "pytest_cache", "test_mod"):
        assert left_out not in c.patch
    assert c.attempt.attempt_id == "fresh-v1-CTL-1-A-u1-1" and c.attempt.patch_sha256 == c.patch_sha256
    sm = load(td / "strata" / "fresh-v1.json", StratumManifest)
    assert (sm.stratum, sm.task_id, sm.description, sm.candidates) == ("fresh-v1", CTL, "fresh-agent attempts (protocol §15.4)", [rel])
    # Registered again with the audit verdict: the record is replaced, the labels kept, the manifest unchanged.
    labeled = c.model_copy(update={"labels": [Label(value="valid", labeler=PILOT_LABELER, labeler_kind=LabelerKind.model, timestamp=T0)]})
    dump(labeled, td / rel)
    manifest = (td / "strata" / "fresh-v1.json").read_bytes()
    audit = {"profile": "fresh-attempt:v1", "passed": True, "audited_at": T0}
    assert _register(td, st, f"{CTL}-fa-1", "--origin", "fresh_attempt",
                     "--attempt-record", str(_attempt_file(repo, "audited.json", audit=audit))) == 0
    assert json.loads(capsys.readouterr().out)["registered"] == "updated"
    again = load(td / rel, Candidate)
    assert again.attempt.audit.passed is True and again.labels == labeled.labels
    assert (td / "strata" / "fresh-v1.json").read_bytes() == manifest and _hashes(td) == before
    # A second attempt is appended; the stratum is graded like any other.
    assert _register(td, _state(repo, CTL, "second", "4"), f"{CTL}-fa-2", "--origin", "fresh_attempt",
                     "--attempt-record", str(_attempt_file(repo, "second.json", attempt_id="fresh-v1-CTL-1-A-u1-2", audit=audit))) == 0
    assert json.loads(capsys.readouterr().out)["registered"] == "added"
    assert load(td / "strata" / "fresh-v1.json", StratumManifest).candidates == [rel, f"strata/fresh-v1/candidates/{CTL}-fa-2.json"]
    run = _evaluate(repo, [td], "r-registered", "--strata", "fresh-v1", "--only-strata")
    a = analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)
    assert a["fresh_attempts"]["n_attempts"] == 2 and a["fresh_attempts"]["by_configuration_variant"]["config-A/u1"]["solved"] == 1


REGISTER_REFUSALS = {  # case: (candidate id, arguments, attempt-record changes or None for no record, refusal)
    "an attempt without a record": (f"{CTL}-fa-1", ["--origin", "fresh_attempt"], None, "needs --attempt-record"),
    "a record for another origin": (f"{CTL}-pr-1", ["--origin", "natural_pre_review", "--produced-by", "x"], {},
                                    "only a fresh attempt takes one"),
    "no producer without a record": (f"{CTL}-pr-1", ["--origin", "natural_pre_review"], None, "--produced-by is needed"),
    "a configuration label that is not config-A to config-Z": (f"{CTL}-fa-1", ["--origin", "fresh_attempt"],
                                                                {"configuration": "config-vendor-model"}, "config-A to config-Z"),
    "a session-local path": (f"{CTL}-fa-1", ["--origin", "fresh_attempt"], {"run_record": "/tmp/" + "claude-0/runs/x.json"},
                             "session-local path"),
    "a session id": (f"{CTL}-fa-1", ["--origin", "fresh_attempt"],
                     {"audit": {"profile": "p", "passed": False, "audited_at": T0, "findings": ["0b6f3a2e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"]}},
                     "session id"),
    "another patch in the record": (f"{CTL}-fa-1", ["--origin", "fresh_attempt"], {"patch_sha256": "0" * 64}, "another patch sha256"),
    "the id of an own candidate": (f"{CTL}-pre", ["--origin", "fresh_attempt"], {}, "already used by the task's own candidates"),
    "an id without the task prefix": ("fa-1", ["--origin", "fresh_attempt"], {}, f"does not start with '{CTL}-'"),
    "a constructed origin": (f"{CTL}-nm-9", ["--origin", "constructed_near_miss", "--produced-by", "x"], None, "invalid choice"),
}


@pytest.mark.parametrize("case", list(REGISTER_REFUSALS))
def test_add_stratum_candidate_refusals_write_nothing(repo, capsys, case):
    td = _make_task(repo, CTL, Population.controlled)
    before = _hashes(td)
    cid, args, record, message = REGISTER_REFUSALS[case]
    extra = [] if record is None else ["--attempt-record", str(_attempt_file(repo, **record))]
    code = _register(td, _state(repo, CTL), cid, *args, *extra)
    assert code not in (0, None) and (message in str(code) or message in capsys.readouterr().err)
    assert not (td / "strata").exists() and _hashes(td) == before


def test_add_stratum_candidate_keeps_a_registered_patch_and_refuses_links(repo):
    td = _make_task(repo, CTL, Population.controlled)
    record = ["--origin", "fresh_attempt", "--attempt-record", str(_attempt_file(repo))]
    assert _register(td, _state(repo, CTL), f"{CTL}-fa-1", *record) == 0
    files = {p: p.read_bytes() for p in (td / "strata").rglob("*") if p.is_file()}
    code = _register(td, _state(repo, CTL, "changed", "5"), f"{CTL}-fa-1", *record)
    assert code not in (0, None) and "a registered candidate's patch never changes" in str(code)
    assert {p: p.read_bytes() for p in (td / "strata").rglob("*") if p.is_file()} == files
    _add_stratum(td, "other", {f"{CTL}-o-1": (CTL, *GOOD)})
    code = _register(td, _state(repo, CTL, "again"), f"{CTL}-o-1", *record)
    assert code not in (0, None) and "already used by stratum 'other'" in str(code)
    # A candidates directory that links out of the task: nothing is written through the link.
    elsewhere = repo / "elsewhere"
    elsewhere.mkdir()
    (td / "strata" / "linked").mkdir()
    (td / "strata" / "linked" / "candidates").symlink_to(elsewhere)
    code = _register(td, _state(repo, CTL, "linked"), f"{CTL}-fa-9", *record, stratum="linked")
    assert code not in (0, None) and "strata/linked/candidates is a symbolic link" in str(code)
    assert not any(elsewhere.iterdir()) and not (td / "strata" / "linked.json").exists()


def test_excluded_attempts_count_nowhere_but_are_reported(repo, graded):
    td = _make_task(repo, CTL, Population.controlled)
    cands = {f"{CTL}-{k}": (CTL, *v) for k, v in FRESH.items()}
    path = _add_stratum(td, cands=cands)
    for cid, passed in ((f"{CTL}-fresh-good", None), (f"{CTL}-fresh-bad", False)):  # not audited; audit failed
        f = td / "strata" / "fresh" / "candidates" / f"{cid}.json"
        c = load(f, Candidate)
        dump(c.model_copy(update={"attempt": _attempt(cid, c.patch, passed=passed)}), f)
    assert path.is_file()
    run = _evaluate(repo, [td], "r-excluded", "--strata", "fresh")
    a = analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)
    f = a["fresh_attempts"]
    assert (f["n_attempts"], f["n_excluded"], f["by_configuration_variant"]) == (0, 2, {})
    assert {x["candidate_id"]: x["reason"].split(":")[0] for x in f["excluded"]} == {
        f"{CTL}-fresh-bad": "the fresh-attempt audit found a read of forbidden material", f"{CTL}-fresh-good": "not audited"}
    listed = {r["candidate"] for rs in a["per_task"][CTL].values() for r in rs}
    assert not listed & set(cands) and "fresh" not in a["by_stratum"] and "strata" not in a["labels"][CTL]
    assert _rate(a, "initial_plain", "false_acceptance") == (1, 2)  # the task's own candidates only
    assert f"{CTL}/strata/fresh/candidates/{CTL}-fresh-bad.json" in a["meta"]["inputs"]["files_sha256"]  # read, so hashed


# ---------------------------------------------------------------------------
# Runs without strata, of the default population, keep the earlier format
# ---------------------------------------------------------------------------


def test_a_default_run_keeps_the_earlier_format(repo):
    run = _evaluate(repo, [_make_task(repo, CTL, Population.controlled)], "r-default")
    a = analyze(run, repo / "tasks", allow_proposed=True, n_boot=50)
    assert not {"by_population", "by_stratum"} & set(a) and not {"populations", "population_pooling", "strata"} & set(a["meta"])
    assert all(set(r) == {"candidate", "origin", "label", "negative_type", "outcome"} for rs in a["per_task"][CTL].values() for r in rs)
    assert "strata" not in a["labels"][CTL] and "code/strata.py" not in a["meta"]["inputs"]["files_sha256"]
    entry = json.loads((run / "manifest.json").read_text())["tasks"][0]
    assert "strata" not in entry and all(set(c) == {"origin", "patch_sha256"} for c in entry["candidates"].values())
    md = (run / "analysis.md").read_text().lower()
    assert "population" not in md and "stratum" not in md


@pytest.mark.skipif(not (PILOT / "analysis.json").is_file(), reason="the frozen pilot run is not in this checkout")
def test_the_frozen_pilot_analysis_regenerates_byte_for_byte(tmp_path):
    """pilot-v0.3.3 (controlled, no strata) keeps its outputs; analysis.json differs only in the revision and code hashes."""
    copy = tmp_path / PILOT.name
    copy.mkdir()
    for name in ("manifest.json", "results.jsonl"):
        shutil.copyfile(PILOT / name, copy / name)
    analyze(copy, REPO / "tasks", allow_proposed=True)
    assert (copy / "analysis.md").read_bytes() == (PILOT / "analysis.md").read_bytes()
    new, old = (json.loads((d / "analysis.json").read_text()) for d in (copy, PILOT))
    codes = []
    for a in (new, old):
        inputs = a["meta"]["inputs"]
        inputs["git_revision"] = None
        codes.append(sorted(k for k in inputs["files_sha256"] if k.startswith("code/")))
        inputs["files_sha256"] = {k: v for k, v in inputs["files_sha256"].items() if not k.startswith("code/")}
    assert new == old and codes[0] == codes[1]
