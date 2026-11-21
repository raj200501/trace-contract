"""The pre-flight of a run that grades candidate strata (``--strata``, ``--only-strata``, ``--with-extra-verifiers``).

* every stratum named loads as ``tracecontract evaluate`` loads it, its candidate ids are used once, and it has a
  candidate of the eval split;
* every graded stratum candidate (a no-op aside) has a D19 proposal or a human label;
* every fresh attempt of a stratum is of the eval split;
* every graded fresh attempt has an attempt record with an audit verdict, the audit report its record names (or
  ``data/fresh/<stratum>/audit_<task>.json``) lists its attempt, and the report leaves no attempt not audited; an
  attempt that the reviewed audit excludes is a note, and a verdict that disagrees with the report is a failure;
* the audit report lists its flagged attempts under ``excluded``, its manual review judges or excludes every flagged
  attempt (never both), and an attempt's own review verdict agrees with the report's lists and with its attempt record;
* the shadowing check covers every stratum candidate;
* with ``--with-extra-verifiers``, the sidecar adds a verifier that the run grades, its verifiers are frozen label-support
  verifiers with ids of their own, and the analysis' condition guard passes on the verifiers the run records; with
  ``--strata`` too, the run grades the independent labeler, frozen before the first graded fresh attempt started;
* with ``--only-strata``, the checks of the task's own held-out pool are notes; the other checks still fail, and so does
  the audit of a verifier's writer recorded among the generator audits (``refcheck``);
* without the new options, the pre-flight's output does not depend on the strata or the sidecar.

Synthetic fixtures (a temporary directory; population ``fixture``); Docker and git are not asked. Two tests read
the recorded fresh-v1 strata, audit reports and sidecars, read only. These tests check code behaviour and are not
research evidence.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from tracecontract.analysis import PILOT_LABELER
from tracecontract.schemas import (
    AttemptAudit, AttemptRecord, Candidate, CandidateOrigin, Label, LabelerKind, Population, SnapshotSource, Split,
    TaskManifest, VerifierCondition, VerifierSpec, sha256_text,
)
from tracecontract.store import dump, load, write_json
from tracecontract.strata import StratumError, StratumManifest, load_stratum
from tracecontract.tasks import verify_snapshot
from tracecontract.verifier import build_spec, freeze

R = Path(__file__).resolve().parents[1]
TID = "FX-ST"
STRATUM = "fresh-v1"
T0 = "2026-11-22T10:00:00+00:00"  # when every fixture attempt starts, unless a test says otherwise
FROZEN = "2026-11-22T09:00:00+00:00"  # when the fixture's verifiers were frozen (not the clock): before T0
REPORT = f"data/fresh/{STRATUM}/audit_{TID}.json"  # where the fixture's attempt records point, from the fixture's root
FAMILIES = ("CS-01", "CS-02", "CS-03", "CS-04")
FRESH_V1_CONDITIONS = ["initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform", "repo_tests",
                       "reference_check"]


def _preflight():
    spec = importlib.util.spec_from_file_location("preflight_final_run", R / "scripts" / "preflight_final_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def pf(monkeypatch):
    mod = _preflight()
    real = subprocess.run

    def run(cmd, *a, **k):  # the host is idle and the tree clean: only these two questions are answered here
        if list(cmd[:2]) in (["docker", "ps"], ["git", "status"]):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return real(cmd, *a, **k)

    monkeypatch.setattr(mod.subprocess, "run", run)
    return mod


# --- the fixture task ------------------------------------------------------------------------------------------------

def _patch(body: str) -> str:
    return f"diff --git a/mod.py b/mod.py\n--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = '{body}'\n"


def _add(path: str) -> str:
    return f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+x = 1\n"


def d19(value: str = "valid") -> Label:
    return Label(value=value, labeler=PILOT_LABELER, labeler_kind=LabelerKind.model, timestamp=T0)


def attempt_id(kind: str) -> str:
    """The attempt id of the fixture's fresh attempt ``kind``; it differs from the candidate id on purpose."""
    return f"att-{kind}"


def cand(kind: str, *, origin: CandidateOrigin = CandidateOrigin.fresh_attempt, split: Split = Split.eval,
         labels: list[Label] | None = None, patch: str | None = None, attempt: bool = True, audit: bool = True,
         passed: bool = True, record: str = REPORT, aid: str | None = None, started_at: str | None = T0) -> Candidate:
    """A stratum candidate ``FX-ST-<kind>``; a fresh attempt carries an attempt record whose audit points to ``record``."""
    patch = _patch(kind) if patch is None else patch
    rec = None
    if origin == CandidateOrigin.fresh_attempt and attempt:
        verdict = AttemptAudit(profile="fresh-attempt:v1", passed=passed, audited_at=T0, record=record) if audit else None
        rec = AttemptRecord(attempt_id=aid or attempt_id(kind), configuration="config-A", variant="u1", ended="finished",
                            started_at=started_at, patch_sha256=sha256_text(patch), audit=verdict)
    return Candidate(candidate_id=f"{TID}-{kind}", task_id=TID, origin=origin, split=split, patch=patch,
                     patch_sha256=sha256_text(patch), produced_by="fixture", labels=[d19()] if labels is None else labels,
                     attempt=rec)


def _verifier(td: Path, vid: str, condition: VerifierCondition, *, folder: str | None = None, frozen: bool = True,
              frozen_at: str | None = FROZEN) -> str:
    folder = folder or vid
    tests = td / "verifiers" / folder / "tests"
    tests.mkdir(parents=True)
    (tests / "test_fixture.py").write_text("def test_value():\n    assert 1 + 1 == 2\n")
    spec = build_spec(verifier_id=vid, task_id=td.name, condition=condition, test_dir=tests, task_dir=td)
    if frozen:  # frozen at the fixture's time, not the clock's (check_frozen does not read frozen_at)
        spec = freeze(spec, td).model_copy(update={"frozen_at": frozen_at})
    dump(spec, td / "verifiers" / folder / "spec.json")
    return f"verifiers/{folder}/spec.json"


def write_stratum(td: Path, cands: list[Candidate], name: str = STRATUM, *, listed: list[str] | None = None) -> None:
    rels = []
    for c in cands:
        rels.append(f"strata/{name}/candidates/{c.candidate_id}.json")
        dump(c, td / rels[-1])
    dump(StratumManifest(stratum=name, task_id=TID, description="fixture", candidates=rels if listed is None else listed),
         td / "strata" / f"{name}.json")


def make_task(root: Path, stratum: list[Candidate] | None = None, *,
              sidecar: dict[str, VerifierCondition] | None = None) -> Path:
    """Task FX-ST under ``root/tasks``: a reference and an evaluation no-op of its own, frozen verifiers for ``full_plain``
    and ``reference_check`` in task.json, the sidecar (by default the independent labeler under ``reference_check``) and
    the stratum fresh-v1 (by default two audited fresh attempts with D19 proposals)."""
    td = root / "tasks" / TID
    own = [Candidate(candidate_id=f"{TID}-reference", task_id=TID, origin=CandidateOrigin.reference, split=Split.dev,
                     patch=_patch("ref"), patch_sha256=sha256_text(_patch("ref")), produced_by="fixture"),
           Candidate(candidate_id=f"{TID}-noop-eval", task_id=TID, origin=CandidateOrigin.noop, split=Split.eval, patch="",
                     patch_sha256=sha256_text(""), produced_by="base snapshot")]
    for c in own:
        dump(c, td / "candidates" / f"{c.candidate_id}.json")
    specs = [_verifier(td, "full_plain", VerifierCondition.full_plain),
             _verifier(td, "reference_check", VerifierCondition.reference_check)]
    side = {"independent_label": VerifierCondition.reference_check} if sidecar is None else sidecar
    extra = [_verifier(td, vid, cond) for vid, cond in side.items()]
    (td / "verifiers_extra.json").write_text(json.dumps({"verifiers": extra}, indent=2) + "\n")
    dump(TaskManifest(task_id=TID, family_id=TID, population=Population.fixture, status="pending_review",
                      provenance="provenance.json", snapshot_source=SnapshotSource(repo_url="https://example.invalid/x",
                                                                                   commit="0" * 40),
                      env_requirements=[], verifiers=specs, candidates=[f"candidates/{c.candidate_id}.json" for c in own]),
         td / "task.json")
    write_stratum(td, [cand("a"), cand("b")] if stratum is None else stratum)
    return td


def write_report(root: Path, attempts: list[str], *, flagged: tuple[str, ...] = (), not_audited: tuple[str, ...] = (),
                 excluded_after_review: list[str] | None = None, judged_false_positive: list[str] | None = None,
                 reviews: dict[str, object] | None = None, path: str = REPORT, **fields) -> Path:
    """An audit report as ``scripts/strict_reaudit.py --fresh`` writes it; ``excluded_after_review`` adds a manual review,
    which judges every other flagged attempt a false positive unless ``judged_false_positive`` says otherwise; ``reviews``
    adds per-attempt reviews (``attempts[<id>].review.passed``); ``fields`` replace top-level keys."""
    rep = {"script": "scripts/strict_reaudit.py --fresh", "task_id": TID, "stratum": STRATUM,
           "attempts": {a: {"task_id": TID, "flagged": a in flagged, "hits": [], "exposures": []} for a in attempts},
           "excluded": [*flagged, *not_audited], "not_audited": list(not_audited), **fields}
    for a in not_audited:
        rep["attempts"][a] = {"task_id": TID, "error": "transcript not found", "flagged": True}
    if excluded_after_review is not None:
        judged = ([a for a in flagged if a not in excluded_after_review] if judged_false_positive is None
                  else judged_false_positive)
        rep["manual_review"] = {"flagged_by_script": list(flagged), "judged_false_positive": judged,
                                "excluded_after_review": excluded_after_review}
    for a, passed in (reviews or {}).items():
        rep["attempts"][a]["review"] = {"passed": passed, "judgment": "fixture", "reasons": []}
    return write_json(rep, root / path)


def edit_report(root: Path, change) -> None:
    """Rewrite the fixture's audit report with ``change(report)`` applied (it edits the report in place)."""
    rep = json.loads((root / REPORT).read_text())
    change(rep)
    write_json(rep, root / REPORT)


def _task(td: Path) -> tuple[TaskManifest, set[str]]:
    m = load(td / "task.json", TaskManifest)
    return m, {load(td / p, Candidate).candidate_id for p in m.candidates}


def _stratum(pf, td: Path, name: str = STRATUM):
    m, own = _task(td)
    loaded, problems = pf.strata_problems(td, m, [name], own)
    assert problems == [], problems
    return m, loaded[name]


def _lines(out: str, kind: str) -> list[str]:
    return [ln[len(kind) + 2:] for ln in out.splitlines() if ln.startswith(f"{kind}: ")]


# --- 1. the stratum loads as evaluate loads it and has a candidate it grades -----------------------------------------

def test_a_stratum_that_loads_and_has_a_graded_candidate_passes(pf, tmp_path):
    td = make_task(tmp_path)
    m, own = _task(td)
    loaded, problems = pf.strata_problems(td, m, [STRATUM, STRATUM], own)  # named twice: loaded once, as evaluate does
    assert problems == [] and list(loaded) == [STRATUM]
    assert [c.candidate_id for _, c in loaded[STRATUM].candidates] == ["FX-ST-a", "FX-ST-b"]


def _listed_twice(td: Path) -> None:
    sm = json.loads((td / "strata" / f"{STRATUM}.json").read_text())
    (td / "strata" / f"{STRATUM}.json").write_text(json.dumps({**sm, "candidates": sm["candidates"] * 2}))


def _of_another_task(td: Path) -> None:
    sm = json.loads((td / "strata" / f"{STRATUM}.json").read_text())
    (td / "strata" / f"{STRATUM}.json").write_text(json.dumps({**sm, "task_id": "FX-OTHER"}))


def _with_a_reference(td: Path) -> None:
    write_stratum(td, [cand("a"), cand("ref2", origin=CandidateOrigin.reference)])


def _with_an_own_id(td: Path) -> None:
    write_stratum(td, [cand("noop-eval", origin=CandidateOrigin.noop, patch="")])  # FX-ST-noop-eval is the task's own


def _missing_file(td: Path) -> None:
    (td / "strata" / STRATUM / "candidates" / "FX-ST-b.json").unlink()


STRATUM_REFUSALS = {  # case -> (how the fixture is broken, the strata named, what the failure says)
    "missing": (None, ["fresh-v2"], "FX-ST: stratum fresh-v2 does not load: FX-ST has no stratum 'fresh-v2'"),
    "invalid name": (None, ["task"], "FX-ST: stratum task does not load: invalid stratum name 'task'"),
    "another task": (_of_another_task, [STRATUM], "describes stratum 'fresh-v1' of task 'FX-OTHER'"),
    "listed twice": (_listed_twice, [STRATUM], "candidate id FX-ST-a is listed twice"),
    "reference": (_with_a_reference, [STRATUM], "FX-ST-ref2 is a reference solution"),
    "missing candidate file": (_missing_file, [STRATUM], "candidate file 'strata/fresh-v1/candidates/FX-ST-b.json' is missing"),
    "an id of the task's own": (_with_an_own_id, [STRATUM],
                                "FX-ST: stratum 'fresh-v1' of FX-ST: candidate id FX-ST-noop-eval is already used by the "
                                "task's own candidates"),
}


@pytest.mark.parametrize("case", list(STRATUM_REFUSALS))
def test_a_stratum_that_evaluate_would_refuse_fails(pf, tmp_path, case):
    breaks, names, expect = STRATUM_REFUSALS[case]
    td = make_task(tmp_path)
    if breaks is not None:
        breaks(td)
    m, own = _task(td)
    loaded, problems = pf.strata_problems(td, m, names, own)
    assert len(problems) == 1 and expect in problems[0], problems


def test_two_strata_cannot_share_a_candidate_id(pf, tmp_path):
    td = make_task(tmp_path)
    write_stratum(td, [cand("a")], name="fresh-v1b")
    m, own = _task(td)
    loaded, problems = pf.strata_problems(td, m, [STRATUM, "fresh-v1b"], own)
    assert sorted(loaded) == [STRATUM, "fresh-v1b"]
    assert problems == ["FX-ST: stratum 'fresh-v1b' of FX-ST: candidate id FX-ST-a is already used by stratum 'fresh-v1'"]
    assert pf.strata_problems(td, m, ["fresh-v1b"], own)[1] == []  # each alone loads


def test_a_stratum_needs_a_candidate_that_evaluate_grades(pf, tmp_path):
    td = make_task(tmp_path, [])
    m, own = _task(td)
    assert pf.strata_problems(td, m, [STRATUM], own)[1] == ["FX-ST: stratum fresh-v1 lists no candidate"]
    write_stratum(td, [cand("a", split=Split.dev), cand("b", split=Split.dev)])
    assert pf.strata_problems(td, m, [STRATUM], own)[1] == [
        "FX-ST: stratum fresh-v1 has no candidate of the eval split; evaluate grades none of its 2 candidate(s)"]
    write_stratum(td, [cand("a", split=Split.dev), cand("b")])
    assert pf.strata_problems(td, m, [STRATUM], own)[1] == []


# --- 2. every graded stratum candidate has a D19 proposal or a human label --------------------------------------------

def test_every_graded_stratum_candidate_needs_a_d19_proposal_or_a_human_label(pf, tmp_path):
    human = Label(value="invalid", violated_requirements=["R-1"], labeler="reviewer-1", labeler_kind=LabelerKind.human,
                  timestamp=T0)
    other = Label(value="valid", labeler="another-labeler:v1", labeler_kind=LabelerKind.model, timestamp=T0)
    td = make_task(tmp_path, [cand("d19"), cand("human", labels=[human]), cand("ambiguous", labels=[d19("ambiguous")]),
                              cand("none", labels=[]), cand("other", labels=[other]),
                              cand("noop", origin=CandidateOrigin.noop, patch="", labels=[]),  # a sanity check, as in the pool
                              cand("dev", split=Split.dev, labels=[])])  # not graded: evaluate grades the eval split
    m, st = _stratum(pf, td)
    hint = "(scripts/propose_labels.py tasks/FX-ST --stratum fresh-v1)"
    assert pf.stratum_label_problems(m, st) == [f"FX-ST: stratum fresh-v1: FX-ST-none has no D19 proposal {hint}",
                                                f"FX-ST: stratum fresh-v1: FX-ST-other has no D19 proposal {hint}"]
    write_stratum(td, [cand("d19"), cand("human", labels=[human])])
    assert pf.stratum_label_problems(*_stratum(pf, td)) == []


# --- 3. every graded fresh attempt has an attempt record and was audited ---------------------------------------------

def test_audited_attempts_that_the_report_lists_pass(pf, tmp_path):
    td = make_task(tmp_path, [cand("a"), cand("b"), cand("obs", origin=CandidateOrigin.observed_other)])
    write_report(tmp_path, [attempt_id("a"), attempt_id("b")], flagged=(attempt_id("b"),), excluded_after_review=[])
    # b was flagged and judged a false positive on review: it counts in the primary analysis (the sensitivity view drops it)
    assert pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path) == ([], [])


def test_an_attempt_record_without_a_report_pointer_is_checked_against_the_default_report(pf, tmp_path):
    assert pf.default_audit_report(STRATUM, TID) == REPORT
    td = make_task(tmp_path, [cand("a", record=""), cand("b", record="")])
    m, st = _stratum(pf, td)
    assert pf.attempt_audit_problems(m, st, repo_root=tmp_path) == (
        ["FX-ST: stratum fresh-v1: audit report data/fresh/fresh-v1/audit_FX-ST.json does not exist"], [])
    write_report(tmp_path, [attempt_id("a"), attempt_id("b")])
    assert pf.attempt_audit_problems(m, st, repo_root=tmp_path) == ([], [])


def test_an_attempt_that_the_reviewed_audit_excludes_is_a_note(pf, tmp_path):
    td = make_task(tmp_path, [cand("a"), cand("b", passed=False)])
    write_report(tmp_path, [attempt_id("a"), attempt_id("b")], flagged=(attempt_id("a"), attempt_id("b")),
                 excluded_after_review=[attempt_id("b")])
    assert pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path) == ([], [
        "FX-ST: stratum fresh-v1: FX-ST-b is excluded from the primary analysis: the reviewed audit excludes it (attempt "
        "att-b in manual_review.excluded_after_review of data/fresh/fresh-v1/audit_FX-ST.json); evaluate still grades it"])


def test_without_a_manual_review_the_automated_exclusions_stand(pf, tmp_path):
    td = make_task(tmp_path, [cand("a"), cand("b", passed=False)])
    write_report(tmp_path, [attempt_id("a"), attempt_id("b")], flagged=(attempt_id("b"),))
    problems, notes = pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path)
    assert problems == [] and notes == [
        "FX-ST: stratum fresh-v1: FX-ST-b is excluded from the primary analysis: the automated audit excludes it (attempt "
        "att-b in 'excluded' of data/fresh/fresh-v1/audit_FX-ST.json, which records no manual review); evaluate still "
        "grades it"]
    write_stratum(td, [cand("a"), cand("b", passed=True)])  # a flag passed without a recorded review
    problems, notes = pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path)
    assert notes == [] and problems == [
        "FX-ST: stratum fresh-v1: FX-ST-b: the automated audit excludes it (attempt att-b in 'excluded' of "
        "data/fresh/fresh-v1/audit_FX-ST.json, which records no manual review), but its attempt record's audit verdict is "
        "passed, so the analysis would count it"]


def _report_lists_a_only(root: Path) -> None:
    write_report(root, [attempt_id("a")])


def _report_without_excluded(root: Path) -> None:
    write_report(root, [attempt_id("a"), attempt_id("b")], flagged=(attempt_id("b"),))
    edit_report(root, lambda rep: rep.pop("excluded"))


AUDIT_FAILURES = {  # case -> (stratum candidates, how the report is written, what the failure says)
    "no attempt record": ([cand("a"), cand("b", attempt=False)], None,
                          "FX-ST-b is a fresh attempt without an attempt record (protocol §15.4)"),
    "no audit verdict": ([cand("a"), cand("b", audit=False)], None,
                         "FX-ST-b was not audited: its attempt record holds no fresh-attempt audit verdict"),
    "report missing": ([cand("a"), cand("b", record="data/fresh/fresh-v1/elsewhere.json")], None,
                       "audit report data/fresh/fresh-v1/elsewhere.json does not exist"),
    "outside the repository": ([cand("a"), cand("b", record="../audit.json")], None,
                               "audit report '../audit.json' is not a path relative to the repository root"),
    "absolute path": ([cand("a"), cand("b", record="/srv/audit.json")], None,
                      "audit report '/srv/audit.json' is not a path relative to the repository root"),
    "not listed": ([cand("a"), cand("b")], _report_lists_a_only,
                   "FX-ST-b: audit report data/fresh/fresh-v1/audit_FX-ST.json does not list its attempt att-b under attempts"),
    "not audited": ([cand("a"), cand("b")],
                    lambda root: write_report(root, [attempt_id("a")], not_audited=(attempt_id("b"),)),
                    "audit report data/fresh/fresh-v1/audit_FX-ST.json leaves attempt att-b not audited (not_audited"),
    "another attempt not audited": ([cand("a"), cand("b")],
                                    lambda root: write_report(root, [attempt_id("a"), attempt_id("b")],
                                                              not_audited=("att-unregistered",)),
                                    "leaves attempt att-unregistered not audited"),
    "another family's report": ([cand("a"), cand("b")],
                                lambda root: write_report(root, [attempt_id("a"), attempt_id("b")], task_id="FX-OTHER"),
                                "audit report data/fresh/fresh-v1/audit_FX-ST.json is the report of task 'FX-OTHER'"),
    "not a report": ([cand("a"), cand("b")], lambda root: write_json([attempt_id("a")], root / REPORT),
                     "is not an audit report of fresh attempts (no 'attempts' object)"),
    "excluded but passed": ([cand("a"), cand("b")],
                            lambda root: write_report(root, [attempt_id("a"), attempt_id("b")], flagged=(attempt_id("b"),),
                                                      excluded_after_review=[attempt_id("b")]),
                            "FX-ST-b: the reviewed audit excludes it (attempt att-b in manual_review.excluded_after_review "
                            "of data/fresh/fresh-v1/audit_FX-ST.json), but its attempt record's audit verdict is passed"),
    "failed but not excluded": ([cand("a"), cand("b", passed=False)],
                                lambda root: write_report(root, [attempt_id("a"), attempt_id("b")], flagged=(attempt_id("b"),),
                                                          excluded_after_review=[]),
                                "FX-ST-b: its attempt record's audit verdict is failed, but the reviewed audit does not "
                                "exclude it (attempt att-b is not in manual_review.excluded_after_review"),
    "one attempt in two candidates": ([cand("a"), cand("b", aid=attempt_id("a"))], None,
                                      "FX-ST-b: its attempt id att-a is also the attempt id of FX-ST-a"),
    # A report without a manual review excludes by its 'excluded' list: a missing list never means that nothing is
    # excluded (the flagged attempt att-b, whose verdict says passed, would be counted).
    "no 'excluded' and no manual review": ([cand("a"), cand("b")], _report_without_excluded,
                                           "audit report data/fresh/fresh-v1/audit_FX-ST.json: 'excluded' is not a list of "
                                           "attempt ids"),
    "'excluded' is not a list": ([cand("a"), cand("b")],
                                 lambda root: write_report(root, [attempt_id("a"), attempt_id("b")],
                                                           flagged=(attempt_id("b"),), excluded=attempt_id("b")),
                                 "'excluded' is not a list of attempt ids"),
    "not audited, with a manual review": ([cand("a"), cand("b")],
                                          lambda root: write_report(root, [attempt_id("a")], not_audited=(attempt_id("b"),),
                                                                    excluded_after_review=[]),
                                          "leaves attempt att-b not audited"),  # its flags are not also a review problem
}


@pytest.mark.parametrize("case", list(AUDIT_FAILURES))
def test_an_unaudited_or_inconsistent_fresh_attempt_fails(pf, tmp_path, case):
    stratum, report, expect = AUDIT_FAILURES[case]
    td = make_task(tmp_path, stratum)
    if report is None:
        write_report(tmp_path, [attempt_id("a"), attempt_id("b")])
    else:
        report(tmp_path)
    problems, notes = pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path)
    assert notes == [] and len(problems) == 1 and expect in problems[0], problems


# --- 3b. the report reviewed every flag, and its per-attempt reviews agree (protocol §18.1) ------------------------------

AT = "FX-ST: stratum fresh-v1: audit report data/fresh/fresh-v1/audit_FX-ST.json"
NEITHER = ("but its manual review neither judges it a false positive nor excludes it (manual_review.judged_false_positive, "
           "excluded_after_review); protocol §18.1 reviews every flag by reading the transcript")
A_B = [attempt_id("a"), attempt_id("b")]
B = attempt_id("b")


def _flag_only_in(where: str):
    """A report whose manual review judges nothing, with att-b flagged in one place only."""
    def write(root: Path) -> None:
        write_report(root, A_B, excluded_after_review=[])

        def change(rep):
            {"attempts": lambda: rep["attempts"][B].update(flagged=True), "excluded": lambda: rep["excluded"].append(B),
             "script": lambda: rep["manual_review"]["flagged_by_script"].append(B)}[where]()
        edit_report(root, change)
    return write


REVIEW_FAILURES = {  # case -> (stratum candidates, how the report is written, every problem expected)
    "a flag that the review neither clears nor excludes": (
        [cand("a"), cand("b")], lambda root: write_report(root, A_B, flagged=(B,), excluded_after_review=[],
                                                          judged_false_positive=[]),
        [f"{AT}: attempt att-b was flagged (attempts.att-b.flagged, 'excluded', manual_review.flagged_by_script), {NEITHER}"]),
    "flagged in its attempt entry only": ([cand("a"), cand("b")], _flag_only_in("attempts"),
                                          [f"{AT}: attempt att-b was flagged (attempts.att-b.flagged), {NEITHER}"]),
    "flagged in 'excluded' only": ([cand("a"), cand("b")], _flag_only_in("excluded"),
                                   [f"{AT}: attempt att-b was flagged ('excluded'), {NEITHER}"]),
    "flagged by the script only": ([cand("a"), cand("b")], _flag_only_in("script"),
                                   [f"{AT}: attempt att-b was flagged (manual_review.flagged_by_script), {NEITHER}"]),
    "judged a false positive and excluded": (
        [cand("a"), cand("b", passed=False)],
        lambda root: write_report(root, A_B, flagged=(B,), excluded_after_review=[B], judged_false_positive=[B]),
        [f"{AT}: its manual review both judges attempt att-b a false positive and excludes it "
         "(manual_review.judged_false_positive and excluded_after_review)"]),
    "a flag of a report without a manual review that it does not exclude": (
        [cand("a"), cand("b")],
        lambda root: (write_report(root, A_B), edit_report(root, lambda rep: rep["attempts"][B].update(flagged=True))),
        [f"{AT}: attempt att-b was flagged (attempts.att-b.flagged), but the report neither excludes it ('excluded') nor "
         "records a manual review of its flags (protocol §16.2, §18.1)"]),
    "a passed review of an attempt that the review excludes": (
        [cand("a"), cand("b", passed=False)],
        lambda root: write_report(root, A_B, flagged=(B,), excluded_after_review=[B], reviews={B: True}),
        [f"{AT}: the review of attempt att-b says passed, but the reviewed audit excludes it "
         "(manual_review.excluded_after_review of data/fresh/fresh-v1/audit_FX-ST.json)",
         "FX-ST: stratum fresh-v1: FX-ST-b: its attempt record's audit verdict is failed, but the review of attempt att-b in "
         "audit report data/fresh/fresh-v1/audit_FX-ST.json says passed"]),
    "a failed review of a flag judged a false positive": (
        [cand("a"), cand("b")],
        lambda root: write_report(root, A_B, flagged=(B,), excluded_after_review=[], reviews={B: False}),
        [f"{AT}: the review of attempt att-b says failed, but the reviewed audit does not exclude it "
         "(manual_review.excluded_after_review of data/fresh/fresh-v1/audit_FX-ST.json)",
         "FX-ST: stratum fresh-v1: FX-ST-b: its attempt record's audit verdict is passed, but the review of attempt att-b in "
         "audit report data/fresh/fresh-v1/audit_FX-ST.json says failed"]),
    "a failed review of an attempt that nothing flagged": (
        [cand("a"), cand("b")], lambda root: write_report(root, A_B, excluded_after_review=[], reviews={attempt_id("a"): False}),
        [f"{AT}: the review of attempt att-a says failed, but the reviewed audit does not exclude it "
         "(manual_review.excluded_after_review of data/fresh/fresh-v1/audit_FX-ST.json)",
         "FX-ST: stratum fresh-v1: FX-ST-a: its attempt record's audit verdict is passed, but the review of attempt att-a in "
         "audit report data/fresh/fresh-v1/audit_FX-ST.json says failed"]),
    "a review that the attempt record contradicts": (  # the review agrees with the lists; the verdict does not
        [cand("a"), cand("b", passed=False)],
        lambda root: write_report(root, A_B, flagged=(B,), excluded_after_review=[], reviews={B: True}),
        ["FX-ST: stratum fresh-v1: FX-ST-b: its attempt record's audit verdict is failed, but the reviewed audit does not "
         "exclude it (attempt att-b is not in manual_review.excluded_after_review of data/fresh/fresh-v1/audit_FX-ST.json), "
         "so the analysis would exclude an attempt that the audit passed",
         "FX-ST: stratum fresh-v1: FX-ST-b: its attempt record's audit verdict is failed, but the review of attempt att-b in "
         "audit report data/fresh/fresh-v1/audit_FX-ST.json says passed"]),
    "a review verdict that is not true or false": (
        [cand("a"), cand("b")], lambda root: write_report(root, A_B, flagged=(B,), excluded_after_review=[], reviews={B: "yes"}),
        [f"{AT}: attempt att-b: its review.passed is not true or false"]),
}
NOT_A_REVIEW = (f"{AT}: manual_review is not a review of the flags: it must hold lists of attempt ids under flagged_by_script, "
                "judged_false_positive, excluded_after_review (excluded_after_review at least)")


def _not_a_review(change):
    """A report whose manual review ``change`` breaks: it is refused, and nothing else of it is read."""
    def write(root: Path) -> None:
        write_report(root, A_B, flagged=(B,), excluded_after_review=[])
        edit_report(root, change)
    return write


REVIEW_FAILURES.update({case: ([cand("a"), cand("b")], _not_a_review(change), [NOT_A_REVIEW]) for case, change in {
    "a manual review that is a list": lambda rep: rep.update(manual_review=[B]),
    "a manual review without excluded_after_review": lambda rep: rep["manual_review"].pop("excluded_after_review"),
    "a review list that is not a list": lambda rep: rep["manual_review"].update(judged_false_positive=B),
}.items()})


@pytest.mark.parametrize("case", list(REVIEW_FAILURES))
def test_a_report_that_did_not_review_every_flag_or_disagrees_with_itself_fails(pf, tmp_path, case):
    stratum, report, expect = REVIEW_FAILURES[case]
    td = make_task(tmp_path, stratum)
    report(tmp_path)
    problems, _ = pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path)
    assert problems == expect


def test_a_report_that_reviewed_every_flag_with_agreeing_reviews_passes(pf, tmp_path):
    """The recorded reports' form: a review per attempt, every flag judged or excluded; the excluded attempt is a note."""
    td = make_task(tmp_path, [cand("a"), cand("b", passed=False), cand("c")])
    write_report(tmp_path, [*A_B, attempt_id("c")], flagged=(attempt_id("a"), B), excluded_after_review=[B],
                 reviews={attempt_id("a"): True, B: False, attempt_id("c"): True})
    problems, notes = pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path)
    assert problems == [] and len(notes) == 1 and notes[0].startswith("FX-ST: stratum fresh-v1: FX-ST-b is excluded from the "
                                                                      "primary analysis: the reviewed audit excludes it")
    # Without a manual review, the automated list decides, and the reviews must agree with it.
    write_report(tmp_path, [*A_B, attempt_id("c")], flagged=(B,), reviews={B: False, attempt_id("c"): True})
    problems, notes = pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path)
    assert problems == [] and len(notes) == 1


def test_only_graded_fresh_attempts_are_checked(pf, tmp_path):
    """A candidate of the dev split is not graded, and a stratum candidate of another origin has no attempt to audit."""
    td = make_task(tmp_path, [cand("a"), cand("dev", origin=CandidateOrigin.observed_other, split=Split.dev),
                              cand("natural", origin=CandidateOrigin.natural_pre_review)])
    write_report(tmp_path, [attempt_id("a")])
    assert pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path) == ([], [])


def test_a_fresh_attempt_outside_the_eval_split_fails(pf, tmp_path):
    """Protocol §15.4 captures every attempt with split eval, the split evaluate grades: an attempt registered in the dev
    split would drop out of grading silently. Its audit is not checked, as nothing grades it."""
    td = make_task(tmp_path, [cand("a"), cand("dev", split=Split.dev), cand("dev-no-record", split=Split.dev, attempt=False)])
    write_report(tmp_path, [attempt_id("a")])
    assert pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path) == ([
        "FX-ST: stratum fresh-v1: FX-ST-dev is a fresh attempt of the dev split, which evaluate does not grade (it grades the "
        "eval split); protocol §15.4 captures every attempt with split eval",
        "FX-ST: stratum fresh-v1: FX-ST-dev-no-record is a fresh attempt of the dev split, which evaluate does not grade (it "
        "grades the eval split); protocol §15.4 captures every attempt with split eval"], [])
    write_stratum(td, [cand("a"), cand("dev", split=Split.eval)])
    write_report(tmp_path, [attempt_id("a"), attempt_id("dev")])
    assert pf.attempt_audit_problems(*_stratum(pf, td), repo_root=tmp_path) == ([], [])


# --- 4. the shadowing check covers the stratum candidates ------------------------------------------------------------

def test_the_shadowing_check_covers_every_stratum_candidate(pf, tmp_path):
    td = make_task(tmp_path, [cand("ok"), cand("json", patch=_patch("x") + _add("json.py")),
                              cand("dev-os", split=Split.dev, patch=_add("os.py"))])
    m, st = _stratum(pf, td)
    assert pf.shadowing_problems(m, [c for _, c in st.candidates], stratum=STRATUM) == [
        "FX-ST: stratum fresh-v1: FX-ST-json ships json.py, a top-level module named like the standard library's `json`; "
        "rejected before grading (tracecontract.shadowing)",
        "FX-ST: stratum fresh-v1: FX-ST-dev-os ships os.py, a top-level module named like the standard library's `os`; "
        "rejected before grading (tracecontract.shadowing)"]
    assert pf.shadowing_problems(m, [c for _, c in st.candidates if c.candidate_id == "FX-ST-ok"], stratum=STRATUM) == []


# --- 5. --with-extra-verifiers: frozen label-support verifiers, and the analysis' condition guard ---------------------

def _extras(pf, td: Path, conditions: list[str] | None = None, **kw):
    m = load(td / "task.json", TaskManifest)
    return pf.extra_verifier_problems(td, m, [load(td / p, VerifierSpec) for p in m.verifiers], conditions, **kw)


def test_a_frozen_label_support_verifier_in_the_sidecar_passes(pf, tmp_path):
    td = make_task(tmp_path)
    for with_strata in (False, True):
        extras, problems = _extras(pf, td, FRESH_V1_CONDITIONS, with_strata=with_strata)
        assert [s.verifier_id for s in extras] == ["independent_label"] and problems == []
        assert _extras(pf, td, with_strata=with_strata)[1] == []  # no --conditions: every condition


def test_an_extra_verifier_must_be_frozen_and_unchanged(pf, tmp_path):
    td = make_task(tmp_path)
    spec = json.loads((td / "verifiers" / "independent_label" / "spec.json").read_text())
    (td / "verifiers" / "independent_label" / "spec.json").write_text(json.dumps({**spec, "frozen": False}))
    assert _extras(pf, td)[1] == ["FX-ST: extra verifier independent_label (verifiers_extra.json) not frozen"]
    (td / "verifiers" / "independent_label" / "spec.json").write_text(json.dumps(spec))
    test = td / "verifiers" / "independent_label" / "tests" / "test_fixture.py"
    test.write_text(test.read_text() + "\n# changed after freezing\n")
    assert _extras(pf, td)[1] == ["FX-ST: extra verifier independent_label (verifiers_extra.json) changed after freezing: "
                                  "independent_label: frozen verifier was modified; bump the version and rerun"]


def test_an_extra_verifier_is_never_an_evaluated_condition(pf, tmp_path):
    # A second verifier under full_plain: a sidecar condition that is not label support, and two verifiers of the task under
    # one evaluated condition, which the analysis refuses.
    td = make_task(tmp_path, sidecar={"full_plain_2": VerifierCondition.full_plain})
    assert _extras(pf, td, FRESH_V1_CONDITIONS)[1] == [
        "FX-ST: extra verifier full_plain_2 (verifiers_extra.json) has the condition 'full_plain'; verifiers_extra.json "
        "registers label-support verifiers only (condition 'reference_check'), never a verifier of an evaluated "
        "condition (D55, protocol §15.5)",
        "FX-ST: verifiers full_plain, full_plain_2 are all recorded under the evaluated condition 'full_plain'; each "
        "condition is scored once per candidate, so one task can have one verifier per condition (tracecontract analyze "
        "would refuse the run)"]
    # The guard follows --conditions, as evaluate records only the verifiers of the conditions given; the sidecar rule does
    # not. The run then grades no extra verifier, which fails too.
    problems = _extras(pf, td, ["initial_plain", "reference_check"])[1]
    assert len(problems) == 2 and "has the condition 'full_plain'" in problems[0]
    assert problems[1] == ("FX-ST: --conditions names no condition of the extra verifiers (full_plain_2); evaluate grades "
                           "none of them")


def test_the_label_support_verifiers_are_recorded_under_reference_check(pf, tmp_path):
    td = make_task(tmp_path, sidecar={"independent_label": VerifierCondition.initial_audited})
    problems = _extras(pf, td)[1]
    assert len(problems) == 2 and "has the condition 'initial_audited'" in problems[0]
    assert problems[1].startswith("FX-ST: the label-support verifier independent_label is recorded under the evaluated "
                                  "condition 'initial_audited', not 'reference_check'")


def test_an_extra_verifier_needs_an_id_of_its_own(pf, tmp_path):
    td = make_task(tmp_path, sidecar={})
    rel = _verifier(td, "reference_check", VerifierCondition.reference_check, folder="reference_check_2")
    (td / "verifiers_extra.json").write_text(json.dumps({"verifiers": [rel]}))
    assert _extras(pf, td)[1] == ["FX-ST: extra verifier reference_check (verifiers_extra.json): another verifier of the "
                                  "task has the id reference_check; a run records one verifier per id"]
    # A path that task.json lists already is not added again (evaluate.load_task), so it is not a second verifier; the
    # sidecar then adds none, which fails.
    (td / "verifiers_extra.json").write_text(json.dumps({"verifiers": ["verifiers/reference_check/spec.json"]}))
    assert _extras(pf, td)[1] == ["FX-ST: --with-extra-verifiers, but verifiers_extra.json registers no verifier; "
                                  "evaluate adds none"]


def test_an_unreadable_sidecar_or_a_missing_spec_fails(pf, tmp_path):
    td = make_task(tmp_path)
    (td / "verifiers_extra.json").write_text("{not json")
    problems = _extras(pf, td)[1]
    assert len(problems) == 1 and problems[0].startswith("FX-ST: verifiers_extra.json cannot be read: ")
    (td / "verifiers_extra.json").write_text(json.dumps({"verifiers": ["verifiers/nowhere/spec.json"]}))
    problems = _extras(pf, td)[1]
    assert len(problems) == 1 and problems[0].startswith(
        "FX-ST: extra verifier verifiers/nowhere/spec.json (verifiers_extra.json) does not load: ")


NO_EXTRA = "FX-ST: --with-extra-verifiers, but verifiers_extra.json registers no verifier; evaluate adds none"
NONE_GRADED = "FX-ST: --conditions names no condition of the extra verifiers (independent_label); evaluate grades none of them"
NO_LABELER = ("FX-ST: the run grades no independent labeler (verifier independent_label of verifiers_extra.json, condition "
              "'reference_check'); with --strata it grades every attempt, and its verdicts are the second labeling "
              "(protocol §15.4, §15.5)")


def test_the_sidecar_must_add_a_verifier_that_the_run_grades(pf, tmp_path):
    """--with-extra-verifiers declares that the run grades the sidecar's verifiers: one that adds none, or a run whose
    --conditions grade none of them, fails (they were notes)."""
    td = make_task(tmp_path)
    assert _extras(pf, td, ["full_plain"])[1] == [NONE_GRADED]
    (td / "verifiers_extra.json").unlink()
    assert _extras(pf, td)[1] == [NO_EXTRA]
    (td / "verifiers_extra.json").write_text(json.dumps({"verifiers": []}))
    assert _extras(pf, td)[1] == [NO_EXTRA]


def test_with_strata_the_run_grades_the_independent_labeler(pf, tmp_path):
    """Protocol §15.4, §15.5: every attempt is graded by the independent labeler (verifier independent_label), whose verdicts
    the analysis reports as the second labeling."""
    td = make_task(tmp_path)
    assert _extras(pf, td, FRESH_V1_CONDITIONS, with_strata=True)[1] == []
    assert _extras(pf, td, ["full_plain"], with_strata=True)[1] == [NONE_GRADED, NO_LABELER]
    other = make_task(tmp_path / "other", sidecar={"second_label": VerifierCondition.reference_check})
    assert _extras(pf, other, FRESH_V1_CONDITIONS)[1] == []  # without strata, another label-support verifier will do
    assert _extras(pf, other, FRESH_V1_CONDITIONS, with_strata=True)[1] == [NO_LABELER]
    (td / "verifiers_extra.json").unlink()
    assert _extras(pf, td, FRESH_V1_CONDITIONS, with_strata=True)[1] == [NO_EXTRA, NO_LABELER]


# --- 5b. with --strata, the extra verifiers were frozen before the first attempt they grade (protocol §15.5) ----------

def _frozen_before(pf, td: Path, conditions: list[str] | None = FRESH_V1_CONDITIONS) -> list[str]:
    m, st = _stratum(pf, td)
    extras = _extras(pf, td, conditions, with_strata=True)[0]
    return pf.frozen_before_attempts_problems(m, pf.graded_verifiers(extras, conditions), {STRATUM: st})


def test_the_extra_verifiers_were_frozen_before_the_first_attempt_started(pf, tmp_path):
    """The fixture's labeler is frozen at 09:00, an hour before its attempts start (T0); an attempt that started before
    (or at) that time fails."""
    td = make_task(tmp_path)
    assert _frozen_before(pf, td) == []
    write_stratum(td, [cand("a"), cand("b", started_at="2026-11-22T08:59:59.999Z")])
    assert _frozen_before(pf, td) == [
        "FX-ST: extra verifier independent_label (verifiers_extra.json) was frozen at 2026-11-22T09:00:00+00:00, not before "
        "the first fresh attempt it grades started (FX-ST-b of stratum fresh-v1, at 2026-11-22T08:59:59.999Z); protocol "
        "§15.5 freezes it before any fresh attempt exists"]
    write_stratum(td, [cand("a"), cand("b", started_at="2026-11-22T10:00:00+01:00")])  # 09:00Z, the same second: not before
    assert len(_frozen_before(pf, td)) == 1
    write_stratum(td, [cand("a"), cand("b", started_at="2026-11-22T09:00:01Z")])
    assert _frozen_before(pf, td) == []
    # Only the attempts that the extra verifiers grade count: not one of the dev split (which fails on its own), and none
    # when --conditions grades no extra verifier (which fails on its own too).
    write_stratum(td, [cand("a"), cand("dev", split=Split.dev, started_at="2026-11-01T00:00:00Z")])
    assert _frozen_before(pf, td) == []
    write_stratum(td, [cand("a", started_at="2026-11-01T00:00:00Z")])
    assert len(_frozen_before(pf, td)) == 1 and _frozen_before(pf, td, ["full_plain"]) == []


def test_an_attempt_without_a_start_time_or_a_verifier_without_a_freezing_time_fails(pf, tmp_path):
    td = make_task(tmp_path, [cand("a"), cand("b", started_at=None)])
    assert _frozen_before(pf, td) == [
        "FX-ST: stratum fresh-v1: FX-ST-b: its attempt record holds no start time (started_at), so nothing shows that the "
        "extra verifiers (independent_label) were frozen before it existed (protocol §15.5)"]
    write_stratum(td, [cand("a"), cand("b")])
    spec_path = td / "verifiers" / "independent_label" / "spec.json"
    spec = json.loads(spec_path.read_text())
    for frozen_at in (None, "2026-11-22T09:00:00"):  # none, or one without a time zone
        spec_path.write_text(json.dumps({**spec, "frozen_at": frozen_at}))
        assert _frozen_before(pf, td) == [
            f"FX-ST: extra verifier independent_label (verifiers_extra.json) records no time of freezing (frozen_at "
            f"{frozen_at!r}), so nothing shows that it was frozen before the fresh attempts it grades existed (protocol §15.5)"]


# --- the options of main ---------------------------------------------------------------------------------------------

def _broken(root: Path) -> Path:
    """The fixture task with every new check failing: a stratum candidate without a D19 proposal or audit report, a
    stratum candidate that ships json.py, a fresh attempt of the dev split, one that started before the sidecar's verifier
    was frozen and one without a start time, and a sidecar verifier that is not frozen and has an evaluated condition."""
    td = make_task(root, [cand("a", labels=[]), cand("b", patch=_add("json.py")), cand("dev", split=Split.dev),
                          cand("early", started_at="2000-01-01T00:00:00+00:00"), cand("no-start", started_at=None)])
    spec = json.loads((td / "verifiers" / "independent_label" / "spec.json").read_text())
    (td / "verifiers" / "independent_label" / "spec.json").write_text(json.dumps({**spec, "frozen": False,
                                                                                  "condition": "initial_plain"}))
    return td


def _with_an_alternative(td: Path) -> Path:
    """Add FX-ST-eval-alt-1, a held-out candidate of the task's own pool (a valid alternative, unlabelled), to its task.json."""
    noop = json.loads((td / "candidates" / "FX-ST-noop-eval.json").read_text())
    dump(Candidate(**{**noop, "candidate_id": "FX-ST-eval-alt-1", "origin": "valid_alternative", "patch": _patch("alt"),
                      "patch_sha256": sha256_text(_patch("alt"))}), td / "candidates" / "FX-ST-eval-alt-1.json")
    m = json.loads((td / "task.json").read_text())
    (td / "task.json").write_text(json.dumps({**m, "candidates": [*m["candidates"], "candidates/FX-ST-eval-alt-1.json"]}))
    return td


UNASSESSED = {"hits": [{"tool": "Bash", "match": "tasks/FX-ST/verifiers", "text": "ls tasks/FX-ST/verifiers"}]}


def write_generator_audit(td: Path, entries: dict) -> None:
    write_json({**entries, "_rules": {"script": "scripts/audit_eval_generators.py"}}, td / "labels" / "generator_audit.json")


def audit_failures(ws: str) -> list[str]:
    """What the generator audit loop reports for an entry ``UNASSESSED``: unassessed hits and no strict re-audit."""
    return [f"FX-ST: generator audit {ws} has unassessed hits",
            f"FX-ST: generator audit {ws} has no strict re-audit (scripts/strict_reaudit.py, D44)"]


def test_without_the_new_options_the_output_does_not_depend_on_strata_or_the_sidecar(pf, tmp_path, capsys):
    """Without --strata, --only-strata and --with-extra-verifiers the output is the pre-flight's before them (HEAD
    4a6e98f): no stratum, sidecar, audit report or freezing time is read, and every problem of a generator audit is a
    failure, in the order of labels/generator_audit.json, the writer of the reference checks (refcheck) included."""
    good, bad = make_task(tmp_path / "good"), _broken(tmp_path / "bad")
    write_report(tmp_path / "good", [attempt_id("a"), attempt_id("b")])
    write_report(tmp_path / "bad", [attempt_id("a")], flagged=(attempt_id("a"),), excluded_after_review=[],
                 judged_false_positive=[], reviews={attempt_id("a"): "yes"}, excluded="att-a")
    for td in (good, bad):
        write_generator_audit(_with_an_alternative(td), {"eval-alt-1": UNASSESSED, "refcheck": UNASSESSED})
    for extra in ([], ["--repeats", "3", "--pilot", "--conditions", "full_plain", "reference_check"]):
        outs = []
        for td in (good, bad):
            code = pf.main(str(td), *extra)
            outs.append((code, capsys.readouterr().out))
        assert outs[0] == outs[1] and outs[0][0] == 1  # the fixture lacks its pool, snapshot and reconstruction record
        assert not _lines(outs[0][1], "NOTE") and "stratum" not in outs[0][1] and "extra verifier" not in outs[0][1]
        assert [f for f in _lines(outs[0][1], "FAIL") if "generator audit" in f] == [
            *audit_failures("eval-alt-1"), *audit_failures("refcheck"),
            "FX-ST: generator audits missing for ['eval-alt-2', 'eval-nm']"]


def test_each_new_option_adds_its_checks_to_main(pf, tmp_path, capsys):
    td = _broken(tmp_path)
    pf.main(str(td), "--repeats", "3", "--pilot", "--strata", STRATUM)
    fails = _lines(capsys.readouterr().out, "FAIL")
    assert "FX-ST: stratum fresh-v1: FX-ST-a has no D19 proposal (scripts/propose_labels.py tasks/FX-ST --stratum fresh-v1)" \
        in fails
    assert "FX-ST: stratum fresh-v1: audit report data/fresh/fresh-v1/audit_FX-ST.json does not exist" in fails
    assert any(f.startswith("FX-ST: stratum fresh-v1: FX-ST-b ships json.py") for f in fails)
    assert not [f for f in fails if "extra verifier" in f]
    assert "FX-ST: stratum fresh-v1: FX-ST-dev is a fresh attempt of the dev split, which evaluate does not grade (it " \
           "grades the eval split); protocol §15.4 captures every attempt with split eval" in fails
    pf.main(str(td), "--repeats", "3", "--pilot", "--with-extra-verifiers")
    fails = _lines(capsys.readouterr().out, "FAIL")
    assert "FX-ST: extra verifier independent_label (verifiers_extra.json) not frozen" in fails
    assert any(f.startswith("FX-ST: the label-support verifier independent_label is recorded under the evaluated condition")
               for f in fails)
    assert not [f for f in fails if "stratum" in f]


def test_main_with_strata_checks_the_independent_labeler_and_when_it_was_frozen(pf, tmp_path, monkeypatch, capsys):
    """With --strata and --with-extra-verifiers: the run grades the independent labeler, and each extra verifier it grades
    was frozen before the first fresh attempt started; neither is asked without --strata."""
    td = make_task(tmp_path, [cand("a", started_at="2026-11-22T08:00:00+00:00"), cand("b")],
                   sidecar={"second_label": VerifierCondition.reference_check})
    write_report(tmp_path, A_B)
    monkeypatch.setattr(pf, "R", tmp_path)
    pf.main(str(td), "--repeats", "3", "--pilot", "--strata", STRATUM, "--with-extra-verifiers")
    fails = _lines(capsys.readouterr().out, "FAIL")
    assert NO_LABELER in fails
    assert "FX-ST: extra verifier second_label (verifiers_extra.json) was frozen at 2026-11-22T09:00:00+00:00, not before " \
           "the first fresh attempt it grades started (FX-ST-a of stratum fresh-v1, at 2026-11-22T08:00:00+00:00); protocol " \
           "§15.5 freezes it before any fresh attempt exists" in fails
    pf.main(str(td), "--repeats", "3", "--pilot", "--with-extra-verifiers")
    assert not [f for f in _lines(capsys.readouterr().out, "FAIL") if "independent labeler" in f or "was frozen at" in f]
    (td / "verifiers_extra.json").unlink()
    pf.main(str(td), "--repeats", "3", "--pilot", "--strata", STRATUM, "--with-extra-verifiers")
    fails = _lines(capsys.readouterr().out, "FAIL")
    assert NO_EXTRA in fails and NO_LABELER in fails


def test_main_reports_an_excluded_attempt_as_a_note(pf, tmp_path, monkeypatch, capsys):
    td = make_task(tmp_path, [cand("a"), cand("b", passed=False)])
    write_report(tmp_path, [attempt_id("a"), attempt_id("b")], flagged=(attempt_id("b"),),
                 excluded_after_review=[attempt_id("b")])
    monkeypatch.setattr(pf, "R", tmp_path)  # the fixture's root: where its attempt records' report paths start
    pf.main(str(td), "--repeats", "3", "--pilot", "--strata", STRATUM, "--with-extra-verifiers")
    out = capsys.readouterr().out
    assert _lines(out, "NOTE") == ["FX-ST: stratum fresh-v1: FX-ST-b is excluded from the primary analysis: the reviewed "
                                   "audit excludes it (attempt att-b in manual_review.excluded_after_review of "
                                   "data/fresh/fresh-v1/audit_FX-ST.json); evaluate still grades it"]
    assert not [f for f in _lines(out, "FAIL") if "stratum" in f or "extra verifier" in f]


def test_only_strata_needs_a_stratum(pf, tmp_path, capsys):
    td = make_task(tmp_path)
    assert pf.main(str(td), "--repeats", "3", "--pilot", "--only-strata") == 1
    assert "--only-strata needs at least one stratum (--strata NAME); evaluate refuses it without one" in \
        _lines(capsys.readouterr().out, "FAIL")


def test_only_strata_makes_the_held_out_pool_checks_notes(pf, tmp_path, monkeypatch, capsys):
    """The fixture's own pool is incomplete, unlabelled and has no generator audits: failures with --strata, notes with
    --only-strata; the run, gate, reconstruction, snapshot and verifier checks fail either way."""
    td = _with_an_alternative(make_task(tmp_path))
    spec = json.loads((td / "verifiers" / "full_plain" / "spec.json").read_text())
    (td / "verifiers" / "full_plain" / "spec.json").write_text(json.dumps({**spec, "frozen": False}))
    write_report(tmp_path, [attempt_id("a"), attempt_id("b")])
    monkeypatch.setattr(pf, "R", tmp_path)
    pool = ["FX-ST: incomplete held-out pool {'valid_alternative': 1}", "FX-ST: FX-ST-eval-alt-1 has no D19 proposal",
            "FX-ST: generator audits missing for ['eval-alt-1', 'eval-alt-2', 'eval-nm']"]
    still = ["FX-ST: no verifier for condition(s) ['diff_derived']", "FX-ST: verifier full_plain not frozen",
             "FX-ST: base snapshot not built (run `tracecontract snapshot tasks/FX-ST`)",
             "run: a new run grades every pair 3 times; pass --repeats 3 here and to `tracecontract evaluate` (got 1; "
             "protocol v0.7 §15.3, v0.8 §16.1)"]
    argv = [str(td), "--strata", STRATUM, "--conditions", "full_plain", "diff_derived"]
    assert pf.main(*argv) == 1
    out = capsys.readouterr().out
    fails = _lines(out, "FAIL")
    assert set(pool + still) <= set(fails) and not _lines(out, "NOTE")
    assert any(f.startswith("FX-ST: reconstruction: no reconstruction_check.json") for f in fails)
    assert any(f.startswith("FX-ST: not accepted through the acceptance gate") for f in fails)
    assert pf.main(*argv, "--only-strata") == 1
    out = capsys.readouterr().out
    fails = _lines(out, "FAIL")
    assert not set(pool) & set(fails) and set(still) <= set(fails)
    assert any(f.startswith("FX-ST: reconstruction: no reconstruction_check.json") for f in fails)
    assert any(f.startswith("FX-ST: not accepted through the acceptance gate") for f in fails)
    assert _lines(out, "NOTE") == [f"{p} (with --only-strata the run does not grade the task's own candidates)" for p in pool]


def test_only_strata_keeps_the_audit_of_a_verifier_writer_a_failure(pf, tmp_path, monkeypatch, capsys):
    """labels/generator_audit.json also records refcheck, the audit of the writer of verifiers/reference_check: the
    reference checks that the run still grades (reference_check is among the conditions) and from which every D19 proposal
    of the strata comes (source 1). With --only-strata its problems, and those of any other entry that generated no
    held-out candidate of the task, still fail; only those of the generator of the task's own held-out candidates
    (eval-alt-1, for FX-ST-eval-alt-1) are notes."""
    td = _with_an_alternative(make_task(tmp_path))
    no_transcript = {"strict_reaudit": {"assessment": "", "transcripts": {"writer": {"error": "transcript not found"}}}}
    write_generator_audit(td, {"eval-alt-1": UNASSESSED, "refcheck": UNASSESSED, "labeler": no_transcript})
    write_report(tmp_path, A_B)
    monkeypatch.setattr(pf, "R", tmp_path)
    writers = [*audit_failures("refcheck"), "FX-ST: strict re-audit of labeler is unassessed or lacks a transcript"]
    argv = [str(td), "--repeats", "3", "--pilot", "--strata", STRATUM, "--conditions", "full_plain", "reference_check"]
    pf.main(*argv)
    fails = _lines(capsys.readouterr().out, "FAIL")
    assert set(audit_failures("eval-alt-1") + writers) <= set(fails)
    pf.main(*argv, "--only-strata")
    out = capsys.readouterr().out
    fails, notes = _lines(out, "FAIL"), _lines(out, "NOTE")
    assert set(writers) <= set(fails) and not set(audit_failures("eval-alt-1")) & set(fails)
    assert [n for n in notes if "generator audit" in n] == [f"{p} ({pf.NOT_GRADED})" for p in [
        *audit_failures("eval-alt-1"), "FX-ST: generator audits missing for ['eval-alt-2', 'eval-nm']"]]
    assert not [n for n in notes if "refcheck" in n or "labeler" in n]


def test_which_generator_audits_audit_a_generator_of_the_held_out_pool(pf):
    """An entry is named after the held-out candidates its generator wrote: <task>-<entry> or <task>-<entry>-<n>."""
    held = [cand(k, origin=o) for k, o in (("eval-alt-1", CandidateOrigin.valid_alternative),
                                           ("eval-nm-3", CandidateOrigin.constructed_near_miss),
                                           ("pre-correction", CandidateOrigin.observed_pre_correction))]
    assert [ws for ws in ("eval-alt-1", "eval-nm", "eval-alt-2", "refcheck", "eval", "alt-1", "eval-nm-3-x")
            if pf.generates_held_out(ws, TID, held)] == ["eval-alt-1", "eval-nm"]
    assert not pf.generates_held_out("eval-alt-1", "FX-OTHER", held)


def test_only_strata_keeps_the_shadowing_check_of_the_task_s_own_candidates(pf, tmp_path, capsys):
    """The reference is still graded (the sanity check), so a candidate of the task that shadows a module still fails."""
    td = make_task(tmp_path)
    ref = json.loads((td / "candidates" / "FX-ST-reference.json").read_text())
    patch = _patch("ref") + _add("hashlib.py")
    (td / "candidates" / "FX-ST-reference.json").write_text(json.dumps({**ref, "patch": patch,
                                                                       "patch_sha256": sha256_text(patch)}))
    pf.main(str(td), "--repeats", "3", "--pilot", "--strata", STRATUM, "--only-strata")
    assert any(f.startswith("FX-ST: FX-ST-reference ships hashlib.py") for f in _lines(capsys.readouterr().out, "FAIL"))


# --- the recorded fresh-v1 strata (read only) ------------------------------------------------------------------------

def _recorded_strata() -> list[Path]:
    tasks = [R / "tasks" / t for t in FAMILIES]
    if not all((td / "strata" / f"{STRATUM}.json").is_file() for td in tasks):
        pytest.skip("the fresh-v1 strata are not in this checkout")
    return tasks


def test_the_recorded_fresh_v1_strata_load_and_are_audited(pf):
    """Read only: the four strata load, every attempt is of the eval split, audited and listed by its family's report,
    which leaves none not audited, reviewed every flag (each judged a false positive or excluded) and records per-attempt
    reviews that agree with it and with the attempt records; the notes are exactly the attempts that each reviewed audit
    excludes; no stratum candidate shadows a module; each sidecar holds the frozen independent labeler under
    reference_check, frozen (08:30 to 08:47Z, D55) before the family's first attempt started (08:58Z, D57); and of the
    generator audits, only refcheck is not one of a generator of the task's held-out candidates."""
    for td in _recorded_strata():
        m, own = _task(td)
        loaded, problems = pf.strata_problems(td, m, [STRATUM], own)
        assert problems == [] and len(loaded[STRATUM].candidates) == 20, (td.name, problems)
        st = loaded[STRATUM]
        assert {c.split for _, c in st.candidates} == {Split.eval}
        problems, notes = pf.attempt_audit_problems(m, st, repo_root=R)
        report = json.loads((R / pf.default_audit_report(STRATUM, m.task_id)).read_text())
        assert {c.attempt.audit.record for _, c in st.candidates} == {pf.default_audit_report(STRATUM, m.task_id)}
        excluded = report["manual_review"]["excluded_after_review"]
        assert problems == [] and len(notes) == len(excluded), (td.name, problems, notes)
        assert all(f" {aid} is excluded from the primary analysis: the reviewed audit excludes it" in n
                   for aid, n in zip(sorted(excluded), sorted(notes))), notes
        assert pf.review_problems(report, pf.default_audit_report(STRATUM, m.task_id), td.name) == []
        assert all(isinstance(e["review"]["passed"], bool) for e in report["attempts"].values())  # the reviews were checked
        assert pf.shadowing_problems(m, [c for _, c in st.candidates], stratum=STRATUM) == []
        extras, problems = _extras(pf, td, FRESH_V1_CONDITIONS, with_strata=True)
        assert [s.verifier_id for s in extras] == ["independent_label"] and problems == [], (td.name, problems)
        assert pf.frozen_before_attempts_problems(m, extras, loaded) == []
        first = min(datetime.fromisoformat(c.attempt.started_at) for _, c in st.candidates)
        assert datetime.fromisoformat(extras[0].frozen_at) < first < datetime.fromisoformat("2026-11-21T08:59:00+00:00")
        audit = json.loads((td / "labels" / "generator_audit.json").read_text())
        held = [load(td / p, Candidate) for p in m.candidates]
        held = [c for c in held if c.split == Split.eval and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]
        assert [ws for ws in audit if ws != "_rules" and not pf.generates_held_out(ws, m.task_id, held)] == ["refcheck"]


def test_the_fresh_v1_command_passes_on_the_recorded_tasks_once_labelled(pf, monkeypatch, capsys):
    """The pre-flight of the fresh-v1 run, with its options, passes on the recorded tasks once every stratum candidate has
    its D19 proposal (Docker and git are not asked, and the run id is a test's)."""
    tasks = _recorded_strata()
    if not all((R / "snapshots" / td.name).is_dir() and verify_snapshot(td, R / "snapshots") for td in tasks):
        pytest.skip("a base snapshot is missing or stale (tracecontract snapshot tasks/<id>)")
    try:
        pending = [c.candidate_id for td in tasks for _, c in load_stratum(td, STRATUM, td.name).candidates
                   if not pf.has_d19_proposal(c)]
    except StratumError as exc:  # a candidate file being written by scripts/propose_labels.py
        pytest.skip(f"a fresh-v1 stratum cannot be read now: {exc}")
    if pending:
        pytest.skip(f"{len(pending)} fresh-v1 candidate(s) have no D19 proposal yet (scripts/propose_labels.py --stratum)")
    import tracecontract.sandbox.docker_runner as docker_runner

    monkeypatch.setattr(docker_runner, "HARNESS_VERSION", "tc-harness/0.3.5")
    argv = [*map(str, tasks), "--run-id", "preflight-test-run", "--strata", STRATUM, "--only-strata", "--conditions",
            *FRESH_V1_CONDITIONS, "--with-extra-verifiers", "--repeats", "3", "--pilot"]
    assert pf.main(*argv) == 0, _lines(capsys.readouterr().out, "FAIL")
    notes = _lines(capsys.readouterr().out, "NOTE")
    excluded = [aid for td in tasks for aid in json.loads((R / pf.default_audit_report(STRATUM, td.name)).read_text())
                ["manual_review"]["excluded_after_review"]]
    assert len([n for n in notes if "is excluded from the primary analysis" in n]) == len(excluded)
