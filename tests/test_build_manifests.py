"""scripts/build_manifests.py: triage sidecars, funnels versus stage results, S9 failures in the ledger (D47, D51; §16.4).

Synthetic fixtures only, in a temporary repository layout.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

R = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_manifests", R / "scripts" / "build_manifests.py")
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)

PROPOSAL = {"category": "candidate", "method": "rule:v1", "confidence": "medium", "reasons": ["r"],
            "correction_event_ids": ["s/L000002.00"]}
FUNNEL = {"schema": "tracecontract/natural-screening-funnel/v1", "population": "natural:pr-review", "generator": "funnel.py",
          "source": {"revision": "b37f9fd1aaaa"},
          "stages": [{"id": "S1", "unit": "pull_request", "count": 9, "prs": 9},
                     {"id": "S8a", "unit": "review_comment", "count": 5, "prs": 3}],
          "sample": {"stage": "S9", "size": 5}}


def _row(cid: int, qualifies: bool, reason: str | None, **kw) -> dict:
    return {"comment_id": cid, "pr_id": 10 + cid, "repo_id": 7, "qualifies": qualifies, "failure_reason": reason,
            "commits_reachable": True, "requirement_paraphrase": "never copied", **kw}


S9 = {"schema": "tracecontract/natural-screening-s9/v1", "population": "natural:pr-review", "stage": "S9",
      "summary": {"comments": 5, "qualifying": 1, "failed": 3, "excluded_judges_disagree": 1},
      "rows": [_row(1, True, None), _row(2, False, "not_addressed"), _row(3, False, "judges_disagree"),
               _row(4, False, "commits_not_fetchable", commits_reachable=False),
               _row(5, False, "not_behaviour_change_or_defect", diff_commit=None)]}


def _repo(tmp_path: Path, *, sidecar: dict | None = None, extra: dict[str, dict] | None = None) -> Path:
    root = tmp_path / "repo"
    td = root / "tasks" / "FX-T"
    td.mkdir(parents=True)
    (td / "provenance.json").write_text(json.dumps({"record_id": "prov-FX-T", "population": "fixture", "source_id": "FX-T",
                                                    "eligibility": "pending_review", "rejection_reasons": [], "triage": None}))
    (td / "task.json").write_text(json.dumps({"status": "draft"}))
    if sidecar is not None:
        (td / "triage.json").write_text(json.dumps(sidecar))
    m = root / "data" / "manifests"
    m.mkdir(parents=True)
    for name, d in (extra or {}).items():
        (m / name).write_text(json.dumps(d))
    return root


def test_the_index_reads_the_triage_sidecar_and_never_needs_the_provenance_field(tmp_path):
    root = _repo(tmp_path, sidecar={"task_id": "FX-T", "provenance_record_id": "prov-FX-T", "triage": PROPOSAL})
    index, _ = bm.build(root)
    row = index["records"][0]
    assert row["triage"] == PROPOSAL and list(row)[list(row).index("rejection_reasons") + 1] == "triage"
    index2, _ = bm.build(_repo(tmp_path / "plain"))
    assert index2["records"][0]["triage"] is None  # no sidecar: the record's own field (null since D50)
    with pytest.raises(ValueError, match="sidecar names task"):
        bm.build(_repo(tmp_path / "wrong", sidecar={"task_id": "FX-U", "provenance_record_id": "prov-FX-T", "triage": PROPOSAL}))


def test_only_files_with_stages_are_funnels_and_s9_failures_enter_the_ledger(tmp_path):
    root = _repo(tmp_path, extra={"screening_natural_aidev.json": FUNNEL, "screening_natural_aidev_s9.json": S9})
    index, ledger = bm.build(root)
    s9 = [r for r in ledger["rejections"] if r.get("stage") == "S9"]
    assert [r["comment_id"] for r in s9] == [2, 4, 5]  # not the qualifying comment, not the disagreement
    assert s9[0] == {"source_id": "comment:2", "population": "natural:pr-review", "stage": "S9", "reasons": ["not_addressed"],
                     "comment_id": 2, "pr_id": 12, "repo_id": 7}
    assert s9[2]["reasons"] == [bm.NO_LATER_COMMIT, "not_behaviour_change_or_defect"]  # §16.4
    assert "never copied" not in json.dumps(ledger)  # ids, stages and reasons only
    note = ledger["note"]
    assert note.count("natural:pr-review (") == 1 and "None" not in note  # one clause per population, nothing garbled
    assert "5 review_comments on 3 PRs survive stage S8a" in note
    assert "of the 5 sampled for S9, 1 qualify, 3 fail (in this ledger with stage S9 and their reasons) and 1 are excluded" in note
    assert "natural:pr-review" not in index["yield_by_population"]  # the index lists screened sessions and tasks only
    # Without a stage result, the funnel's sample is described as pending.
    _, ledger2 = bm.build(_repo(tmp_path / "f", extra={"screening_natural_aidev.json": FUNNEL}))
    assert "its S9 sample of 5 has no result in this ledger yet" in ledger2["note"]


def test_a_file_that_is_neither_a_funnel_nor_a_stage_result_is_refused(tmp_path):
    with pytest.raises(ValueError, match="neither a screening funnel"):
        bm.build(_repo(tmp_path, extra={"screening_natural_other.json": {"population": "natural:pr-review", "rows": []}}))
    bad = {**S9, "summary": {**S9["summary"], "failed": 4}}
    with pytest.raises(ValueError, match="summary says failed = 4"):
        bm.build(_repo(tmp_path / "b", extra={"screening_natural_aidev_s9.json": bad}))


@pytest.mark.skipif(not (R / "data" / "manifests" / "screening_natural_aidev_s9.json").is_file(), reason="no S9 result")
def test_the_committed_manifests_regenerate():
    index, ledger = bm.build(R)
    assert json.loads((R / "data" / "manifests" / "provenance_index.json").read_text()) == index
    assert json.loads((R / "data" / "manifests" / "rejection_ledger.json").read_text()) == ledger
    s9 = json.loads((R / "data" / "manifests" / "screening_natural_aidev_s9.json").read_text())
    assert sum(r.get("stage") == "S9" for r in ledger["rejections"]) == s9["summary"]["failed"]
