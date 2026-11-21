"""D19 label proposals (scripts/propose_labels.py) for natural candidates and for candidate strata.

* fresh_attempt and natural_pre_review are labeled by D19's natural-candidate rule (reference checks and
  regression norm), never by construction intent; a pre-review state that passes the reference checks
  is ambiguous (protocol v0.7 §15.4, §15.6; v0.8 §16.3). The rule for the pilot's origins is unchanged.
* ``--stratum NAME`` labels a stratum's candidates in their own files and logs to
  ``strata/<name>/proposed_labels.json``; task.json, the task's candidates and labels/ are never written.

Synthetic fixtures and a stubbed grader (no Docker); not research evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tracecontract.schemas import (
    AttemptAudit, AttemptRecord, Candidate, CandidateOrigin, CheckResult, CheckSpec, Isolation, Label, LabelerKind, Outcome,
    Population, SnapshotSource, Split, TaskManifest, VerificationResult, VerifierCondition, VerifierSpec, sha256_text,
)
from tracecontract.store import dump, load
from tracecontract.strata import StratumError, StratumManifest

ROOT = Path(__file__).resolve().parents[1]
T0 = "2026-11-22T10:00:00+00:00"


def _module():
    spec = importlib.util.spec_from_file_location("propose_labels", ROOT / "scripts" / "propose_labels.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pl = _module()
CONS_INVALID = Label(value="invalid", violated_requirements=["R2"], labeler="nearmiss:v1", labeler_kind=LabelerKind.construction, timestamp=T0)
CONS_VALID = Label(value="valid", labeler="altimpl:v1", labeler_kind=LabelerKind.construction, timestamp=T0)


def test_natural_origins_use_the_natural_rule_whatever_their_construction_label():
    for origin in (CandidateOrigin.fresh_attempt, CandidateOrigin.observed_pre_correction, CandidateOrigin.observed_other):
        for cons in (None, CONS_INVALID, CONS_VALID):  # a construction label on a natural candidate is ignored
            assert pl.d19(origin, cons, infra=False, rc_ok=True, violated_rc=[], reg_fail=[])[0] == "valid"
            assert pl.d19(origin, cons, infra=False, rc_ok=False, violated_rc=["R1"], reg_fail=["t::x"])[:2] == ("invalid", ["R1", "REGRESSION"])
    # A pre-review state that passes the reference checks: the correction is not observable by them (§15.6).
    value, violated, why = pl.d19(CandidateOrigin.natural_pre_review, None, infra=False, rc_ok=True, violated_rc=[], reg_fail=[])
    assert (value, violated) == ("ambiguous", []) and "not observable" in why
    assert pl.d19(CandidateOrigin.natural_pre_review, None, infra=False, rc_ok=False, violated_rc=["R2"], reg_fail=[])[:2] == ("invalid", ["R2"])
    assert pl.d19(CandidateOrigin.fresh_attempt, None, infra=True, rc_ok=False, violated_rc=[], reg_fail=[])[0] == "ambiguous"


def test_the_rule_for_constructed_candidates_is_unchanged():
    nm = CandidateOrigin.constructed_near_miss
    assert pl.d19(nm, CONS_INVALID, infra=False, rc_ok=False, violated_rc=["R2"], reg_fail=[])[:2] == ("invalid", ["R2"])
    assert pl.d19(nm, CONS_INVALID, infra=False, rc_ok=False, violated_rc=["R1"], reg_fail=[])[:2] == ("ambiguous", ["R1"])
    assert pl.d19(nm, CONS_INVALID, infra=False, rc_ok=True, violated_rc=[], reg_fail=[])[:2] == ("ambiguous", [])
    alt = CandidateOrigin.valid_alternative
    assert pl.d19(alt, CONS_VALID, infra=False, rc_ok=True, violated_rc=[], reg_fail=[])[0] == "valid"
    assert pl.d19(alt, CONS_VALID, infra=False, rc_ok=True, violated_rc=[], reg_fail=["t::x"])[:2] == ("ambiguous", ["REGRESSION"])
    assert pl.d19(alt, None, infra=False, rc_ok=True, violated_rc=[], reg_fail=[])[0] == "valid"  # no construction label: natural


def _cand(td: Path, rel: str, cid: str, origin: CandidateOrigin, split: Split = Split.eval, attempt: bool = False) -> Candidate:
    patch = f"--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-X = 1\n+X = '{cid}'\n"
    rec = AttemptRecord(attempt_id=f"att-{cid}", configuration="config-B", variant="final", ended="finished",
                        patch_sha256=sha256_text(patch), audit=AttemptAudit(profile="fresh-attempt:v1", passed=True, audited_at=T0)) if attempt else None
    c = Candidate(candidate_id=cid, task_id="FX-1", origin=origin, split=split, patch=patch, patch_sha256=sha256_text(patch),
                  produced_by="fixture", attempt=rec)
    dump(c, td / rel)
    return c


@pytest.fixture()
def task(tmp_path, monkeypatch) -> Path:
    td = tmp_path / "FX-1"
    own = {"candidates/FX-1-reference.json": ("FX-1-reference", CandidateOrigin.reference, Split.dev),
           "candidates/FX-1-pre.json": ("FX-1-pre", CandidateOrigin.observed_pre_correction, Split.eval)}
    for rel, (cid, origin, split) in own.items():
        _cand(td, rel, cid, origin, split)
    dump(TaskManifest(task_id="FX-1", family_id="FX-1", population=Population.fixture, status="draft", provenance="p.json",
                      snapshot_source=SnapshotSource(repo_url="https://example.invalid/x", commit="0" * 40), env_requirements=[],
                      candidates=list(own)), td / "task.json")
    dump(VerifierSpec(verifier_id="reference_check", task_id="FX-1", condition=VerifierCondition.reference_check,
                      isolation=Isolation.process_separated, test_dir="verifiers/reference_check/tests", content_sha256="x",
                      checks=[CheckSpec(check_id="test_r.py::test_corr", requirement_ids=["R2"])]),
         td / "verifiers" / "reference_check" / "spec.json")
    rels = []
    for cid, origin, attempt in (("FX-1-fa-1", CandidateOrigin.fresh_attempt, True), ("FX-1-fa-2", CandidateOrigin.fresh_attempt, True),
                                 ("FX-1-pr", CandidateOrigin.natural_pre_review, False)):
        rel = f"strata/s1/candidates/{cid}.json"
        _cand(td, rel, cid, origin, attempt=attempt)
        rels.append(rel)
    dump(StratumManifest(stratum="s1", task_id="FX-1", candidates=rels), td / "strata" / "s1.json")

    def verify(*, spec, candidate, **_):  # the reference checks fail only on FX-1-fa-2
        ok = candidate.candidate_id != "FX-1-fa-2"
        return VerificationResult(run_id="labels", task_id="FX-1", verifier_id=spec.verifier_id, candidate_id=candidate.candidate_id,
                                  outcome=Outcome.passed if ok else Outcome.task_failure, reward=1.0 if ok else 0.0,
                                  checks=[CheckResult(check_id="test_r.py::test_corr", status="passed" if ok else "failed")],
                                  started_at=T0, finished_at=T0, wall_s=0.1, harness_version="stub")

    monkeypatch.setattr(pl, "verify_candidate", verify)
    monkeypatch.setattr(pl, "build_env_image", lambda reqs, cache: ("tc-fixture:0", "sha256:" + "0" * 64))
    return td


def _hashes(td: Path) -> dict[str, str]:
    return {str(p.relative_to(td)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(td.rglob("*")) if p.is_file() and "strata" not in p.parts}


def test_a_stratum_is_labeled_in_its_own_files(task):
    before = _hashes(task)  # task.json, the task's own candidates, the verifier spec
    pl.main(str(task), stratum="s1")
    assert _hashes(task) == before and not (task / "labels").exists()
    labels = {cid: load(task / "strata" / "s1" / "candidates" / f"{cid}.json", Candidate).labels[-1]
              for cid in ("FX-1-fa-1", "FX-1-fa-2", "FX-1-pr")}
    assert {cid: (lb.value, lb.violated_requirements, lb.labeler) for cid, lb in labels.items()} == {
        "FX-1-fa-1": ("valid", [], pl.LABELER), "FX-1-fa-2": ("invalid", ["R2"], pl.LABELER), "FX-1-pr": ("ambiguous", [], pl.LABELER)}
    c = load(task / "strata" / "s1" / "candidates" / "FX-1-fa-1.json", Candidate)
    assert c.attempt is not None and c.attempt.attempt_id == "att-FX-1-fa-1"  # the attempt record is kept
    log = json.loads((task / "strata" / "s1" / "proposed_labels.json").read_text())
    assert (log["stratum"], log["regression_overlay"], sorted(log["candidates"])) == ("s1", None, ["FX-1-fa-1", "FX-1-fa-2", "FX-1-pr"])
    # Labeling again replaces the earlier proposal instead of adding another.
    pl.main(str(task), stratum="s1")
    assert len(load(task / "strata" / "s1" / "candidates" / "FX-1-fa-1.json", Candidate).labels) == 1


def test_a_stratum_takes_no_base_test_paths_and_must_be_valid(task):
    with pytest.raises(SystemExit, match="base test paths are not accepted"):
        pl.main(str(task), "tests", stratum="s1")
    with pytest.raises(StratumError, match="has no stratum 'other'"):
        pl.main(str(task), stratum="other")
    assert not (task / "strata" / "s1" / "proposed_labels.json").exists()
