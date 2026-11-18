"""Unit tests for analysis helpers: label policies, coverage and mapper agreement."""

from __future__ import annotations

from types import SimpleNamespace

from tracecontract.analysis import PILOT_LABELER, _coverage_one, candidate_label, cohen_kappa
from tracecontract.schemas import Candidate, CandidateOrigin, Label, LabelerKind, Split, sha256_text


def _cand(origin: CandidateOrigin, labels: list[Label]) -> Candidate:
    return Candidate(candidate_id="c", task_id="t", origin=origin, split=Split.eval, patch="", patch_sha256=sha256_text(""),
                     produced_by="fixture", labels=labels)


def _lab(value: str, kind: LabelerKind, labeler: str, violated=()) -> Label:
    return Label(value=value, violated_requirements=list(violated), labeler=labeler, labeler_kind=kind, timestamp="2026-11-18T00:00:00+00:00")


def test_cohen_kappa():
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 0, 0]) == 0.5
    assert cohen_kappa([0, 0, 0], [0, 0, 0]) == 1.0  # degenerate: identical constant ratings
    assert cohen_kappa([], []) is None


def test_label_policies():
    cons = _lab("invalid", LabelerKind.construction, "nearmiss:v1", ["R-x"])
    d19 = _lab("ambiguous", LabelerKind.model, PILOT_LABELER)
    c = _cand(CandidateOrigin.constructed_near_miss, [cons, d19])
    assert candidate_label(c, "human") is None
    assert candidate_label(c, "pilot").value == "ambiguous"
    assert candidate_label(c, "construction").value == "invalid"
    # A construction label alone is never used by the pre-specified pilot policy.
    only_cons = _cand(CandidateOrigin.constructed_near_miss, [cons])
    assert candidate_label(only_cons, "pilot") is None
    # Natural candidates keep their D19 proposal under the construction policy.
    nat = _cand(CandidateOrigin.observed_pre_correction, [_lab("invalid", LabelerKind.model, PILOT_LABELER, ["R-y"])])
    assert candidate_label(nat, "construction").value == "invalid"
    # A human label overrides every proposal.
    human = _lab("valid", LabelerKind.human, "annotator-1")
    c2 = _cand(CandidateOrigin.constructed_near_miss, [cons, d19, human])
    assert candidate_label(c2, "pilot").value == "valid"
    assert candidate_label(c2, "construction").value == "valid"


def _req(rid: str, scored=True, status="explicit"):
    return SimpleNamespace(req_id=rid, scored=scored, status=SimpleNamespace(value=status))


def test_coverage_ignores_contradicted_mappings():
    reqs = [_req("R1"), _req("R2"), _req("R3")]
    contract = SimpleNamespace(active=lambda: reqs, requirements=reqs)
    mapping = {"map": {"R1": ["A"], "R2": ["B"], "R3": []}, "contradicts": {"R2": ["B"]}}
    d = _coverage_one(contract, mapping, {"A", "B", "C"})
    assert d["covered"] == ["A"]  # R2 maps to B but contradicts it
    assert d["missing"] == ["B", "C"]
    assert d["unsupported"] == ["R3"]
    assert d["contradicting"] == ["R2"]
    assert abs(d["coverage"] - 1 / 3) < 1e-9


def test_coverage_reports_covered_but_contradicted():
    reqs = [_req("R1"), _req("R2")]
    contract = SimpleNamespace(active=lambda: reqs, requirements=reqs)
    mapping = {"map": {"R1": ["A"], "R2": ["A"]}, "contradicts": {"R2": ["A"]}}
    d = _coverage_one(contract, mapping, {"A"})
    assert d["covered"] == ["A"]  # R1 covers A without contradicting it
    assert d["covered_but_contradicted"] == ["A"]  # ... while R2 contradicts it


def test_regression_only_negative_is_unspecified():
    from tracecontract.analysis import _negative_type

    ref = SimpleNamespace(by_id=lambda rid: (_ for _ in ()).throw(KeyError(rid)))
    lab = _lab("invalid", LabelerKind.model, PILOT_LABELER, ["REGRESSION"])
    c = _cand(CandidateOrigin.constructed_near_miss, [lab])
    assert _negative_type(c, lab, ref, "U1") == "unspecified"


def test_clopper_pearson_reference_values():
    from tracecontract.metrics import clopper_pearson

    lo, hi = clopper_pearson(0, 17)
    assert lo == 0.0 and abs(hi - 0.1951) < 1e-3
    lo, hi = clopper_pearson(2, 10)
    assert abs(lo - 0.0252) < 1e-3 and abs(hi - 0.5561) < 1e-3
