"""The identifiers of protocol v0.8 §16.3 in the schema, the attempt record, and the pilot's records unchanged.

* Candidate origins ``fresh_attempt`` and ``natural_pre_review`` (natural candidates for D19), the
  labeler kind ``source_evidence``, the condition ``diff_derived`` (B3) and the sub-populations
  ``natural:pr-review`` and ``natural:chat``.
* A fresh attempt's attempt record on its candidate, checked against the candidate and omitted
  from the JSON while empty.
* Every record of the four pilot tasks re-serialises byte for byte.

Synthetic records apart from the read-only pass over tasks/CS-0*; not research evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tracecontract.schemas import (
    CONFIG_LABEL, NATURAL_ORIGINS, AttemptAudit, AttemptRecord, Candidate, CandidateOrigin, Label, LabelerKind, Population,
    ProvenanceRecord, Snapshot, Split, TaskContract, TaskManifest, VerifierCondition, VerifierSpec, sha256_text,
)

ROOT = Path(__file__).resolve().parents[1]
T0 = "2026-11-22T10:00:00+00:00"
PATCH = "--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-X = 1\n+X = 2\n"


def _record(**over) -> dict:
    rec = {"attempt_id": "fresh-v1-CS-01-A-u1-1", "configuration": "config-A", "variant": "u1", "ended": "finished",
           "patch_sha256": sha256_text(PATCH), "instruction_sha256": "ef" * 32, "turns": 4, "tool_calls": 11}
    return {**rec, **over}


def _candidate(origin: CandidateOrigin = CandidateOrigin.fresh_attempt, **attempt) -> Candidate:
    return Candidate(candidate_id="CS-01-fa-1", task_id="CS-01", origin=origin, split=Split.eval, patch=PATCH,
                     patch_sha256=sha256_text(PATCH), produced_by="fresh-attempt:config-A",
                     attempt=AttemptRecord.model_validate(_record(**attempt)) if attempt is not None else None)


def test_the_identifiers_of_section_16_3():
    assert CandidateOrigin("fresh_attempt") is CandidateOrigin.fresh_attempt
    assert CandidateOrigin("natural_pre_review") is CandidateOrigin.natural_pre_review
    assert LabelerKind("source_evidence") is LabelerKind.source_evidence
    assert VerifierCondition("diff_derived") is VerifierCondition.diff_derived
    assert Population("natural:pr-review") is Population.natural_pr_review and Population("natural:chat") is Population.natural_chat
    assert all(p.is_natural for p in (Population.natural, Population.natural_pr_review, Population.natural_chat))
    assert not Population.controlled.is_natural and not Population.fixture.is_natural
    assert {CandidateOrigin.fresh_attempt, CandidateOrigin.natural_pre_review, CandidateOrigin.observed_pre_correction} <= NATURAL_ORIGINS
    assert not NATURAL_ORIGINS & {CandidateOrigin.constructed_near_miss, CandidateOrigin.valid_alternative,
                                  CandidateOrigin.reference, CandidateOrigin.noop, CandidateOrigin.dev_attack}


def test_an_attempt_record_is_checked_and_kept_with_its_candidate():
    c = _candidate()
    assert c.attempt.configuration == "config-A" and c.attempt.audit is None
    again = Candidate.model_validate_json(c.model_dump_json())
    assert again == c and again.attempt.patch_sha256 == c.patch_sha256
    with pytest.raises(ValueError, match="another patch sha256"):
        _candidate(patch_sha256="0" * 64)
    with pytest.raises(ValueError, match="only a fresh_attempt candidate carries an attempt record"):
        _candidate(CandidateOrigin.valid_alternative)
    for bad in ({"configuration": "config-vendor-model-v9"}, {"configuration": "config-a"}, {"configuration": "A"},
                {"variant": "u2"}, {"ended": "timeout"}, {"patch_sha256": "AB" * 32}, {"instruction_sha256": "x"},
                {"attempt_id": "two words"}, {"turns": -1}, {"wall_s": 0}, {"started_at": "2026-11-22T10:00:00"},
                {"started_at": "yesterday"}, {"started_at": T0, "ended_at": "2026-11-22T09:00:00+00:00"}):
        with pytest.raises(ValueError):
            AttemptRecord.model_validate(_record(**bad))
    audited = AttemptRecord.model_validate(_record(audit={"profile": "fresh-attempt:v1", "passed": False, "audited_at": T0,
                                                          "findings": ["read the repository's README"]}))
    assert audited.audit == AttemptAudit(profile="fresh-attempt:v1", passed=False, audited_at=T0, findings=["read the repository's README"])
    assert CONFIG_LABEL.fullmatch("config-B") and not CONFIG_LABEL.fullmatch("config-anything_goes-123")


def test_an_empty_attempt_record_is_omitted_from_the_json():
    c = Candidate(candidate_id="CS-01-alt", task_id="CS-01", origin=CandidateOrigin.valid_alternative, split=Split.eval,
                  patch=PATCH, patch_sha256=sha256_text(PATCH), produced_by="x")
    assert "attempt" not in c.model_dump_json() and "attempt" not in c.model_dump(mode="json")
    assert "attempt" in _candidate().model_dump(mode="json")


def test_source_evidence_labels_are_not_proposals():
    se = Label(value="invalid", violated_requirements=["R2"], labeler="source-evidence:v1", labeler_kind=LabelerKind.source_evidence,
               timestamp=T0)
    d19 = Label(value="ambiguous", labeler="builder:refcheck+regression+construction:v1", labeler_kind=LabelerKind.model, timestamp=T0)
    c = Candidate(candidate_id="NAT-1-pre", task_id="NAT-1", origin=CandidateOrigin.natural_pre_review, split=Split.eval, patch=PATCH,
                  patch_sha256=sha256_text(PATCH), produced_by="x", labels=[d19, se])
    assert c.proposed_label() == d19 and c.source_evidence_label() == se and c.final_label() is None


KINDS = {"task.json": TaskManifest, "provenance.json": ProvenanceRecord, "snapshot.json": Snapshot, "spec.json": VerifierSpec}


@pytest.mark.skipif(not (ROOT / "tasks" / "CS-01" / "task.json").is_file(), reason="the pilot tasks are not in this checkout")
def test_the_pilot_records_reserialise_byte_for_byte():
    n = 0
    for f in sorted(ROOT.glob("tasks/CS-0*/**/*.json")):
        cls = KINDS.get(f.name) or (Candidate if f.parent.name == "candidates" else
                                    TaskContract if f.parent.name == "contracts" and not f.name.startswith("mapping") else None)
        if cls is None or "labels" in f.parts:
            continue
        raw = f.read_text(encoding="utf-8")
        assert cls.model_validate_json(raw).model_dump_json(indent=2) + "\n" == raw, f
        n += 1
    assert n >= 130  # 4 tasks: manifests, provenance, snapshots, candidates, contracts and verifier specs
