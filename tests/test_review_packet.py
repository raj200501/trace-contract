"""Blinded review packet (annotation guide v0.3, decision log D43, D44).

Nothing in the packet names a candidate's id, origin or description; the session text
holds user turns only; identical diffs share one item; state directories are readable by
the sandbox user; merging needs two complete reviews, uses the documented glob, records
origin guesses, refuses a second merge, and leaves disagreements unresolved.
"""

from __future__ import annotations

import glob
import json
import shutil
import stat
from pathlib import Path

import pytest

import tracecontract.tasks as tasks_mod
from tracecontract.review import TEMPLATE, export_packet, merge_labels
from tracecontract.schemas import Candidate, CandidateOrigin, Split, TaskContract, TaskManifest
from tracecontract.store import dump, load

FX = Path(__file__).parent / "fixtures" / "harbor_fx01"


def _task(tmp_path: Path) -> Path:
    td = tmp_path / "tasks" / "FX-01"
    shutil.copytree(FX / "tasks" / "FX-01", td)
    ref = load(td / "candidates" / "FX-01-reference.json", Candidate)
    wrong = load(td / "candidates" / "FX-01-wrong.json", Candidate)
    alt = ref.model_copy(update={"candidate_id": "FX-01-eval-alt-1", "origin": CandidateOrigin.valid_alternative,
                                 "split": Split.eval, "description": "independent alternative SECRET-NOTE"})
    dup = wrong.model_copy(update={"candidate_id": "FX-01-eval-nm-9", "description": "same patch as FX-01-wrong"})
    dump(alt, td / "candidates" / "FX-01-eval-alt-1.json")
    dump(dup, td / "candidates" / "FX-01-eval-nm-9.json")
    m = load(td / "task.json", TaskManifest)
    dump(m.model_copy(update={"candidates": m.candidates + ["candidates/FX-01-eval-alt-1.json", "candidates/FX-01-eval-nm-9.json"]}),
         td / "task.json")
    return td


def test_packet_is_blind_and_merge_is_guarded(tmp_path, monkeypatch):
    td = _task(tmp_path)
    monkeypatch.setattr(tasks_mod, "verify_snapshot", lambda t, s: True)
    out, key = tmp_path / "packet", tmp_path / "coordinator" / "key.json"
    with pytest.raises(ValueError, match="outside the packet"):
        export_packet([td], out, out / "key.json", snapshot_root=FX / "snapshots", repo_root=tmp_path, seed=7)
    res = export_packet([td], out, key, snapshot_root=FX / "snapshots", repo_root=tmp_path, seed=7)
    assert res == {"packet": str(out.resolve()), "key": str(key.resolve()), "items": 2, "candidates": 3}
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="exists"):
        export_packet([td], tmp_path / "packet2", key, snapshot_root=FX / "snapshots", repo_root=tmp_path, seed=8)
    text = "\n".join(p.read_text(errors="replace") for p in out.rglob("*") if p.is_file())
    for leak in ("FX-01-wrong", "FX-01-eval", "constructed_near_miss", "valid_alternative", "SECRET-NOTE", "same patch as"):
        assert leak not in text, leak
    items = json.loads(key.read_text())["tasks"]["FX-01"]
    assert sorted(sorted(v) for v in items.values()) == [["FX-01-eval-alt-1"], ["FX-01-eval-nm-9", "FX-01-wrong"]]
    for oid in items:
        state = out / "FX-01" / "candidates" / oid / "state"
        assert (state / "calc.py").is_file() and stat.S_IMODE(state.stat().st_mode) == 0o755

    tmpl = json.loads((out / "FX-01" / TEMPLATE).read_text())
    assert set(tmpl["contract_reviews"]) == {r.req_id for r in load(td / "contracts" / "reference.json", TaskContract).requirements}
    wrong_id = next(o for o, c in items.items() if "FX-01-wrong" in c)
    alt_id = next(o for o, c in items.items() if "FX-01-eval-alt-1" in c)

    def write(rev: str, alt_value: str, decision: str = "accept", reviewer: str | None = None) -> Path:
        d = dict(tmpl, reviewer=reviewer or rev)
        d["contract_reviews"] = {rid: {"decision": decision, "note": "n"} for rid in tmpl["contract_reviews"]}
        d["labels"] = {wrong_id: {"value": "invalid", "violated_requirements": ["R1"], "origin_guess": "near-miss", "note": "n"},
                       alt_id: {"value": alt_value, "violated_requirements": [], "origin_guess": "unsure", "note": "unclear"}}
        f = out / "FX-01" / f"labels_{rev}.json"
        f.write_text(json.dumps(d))
        return f

    a = write("R1", "valid")
    with pytest.raises(ValueError, match="fewer than 2"):
        merge_labels([a], key, tmp_path / "tasks")
    with pytest.raises(ValueError, match="pseudonymous"):
        merge_labels([write("R9", "valid", reviewer="Jane Doe"), a], key, tmp_path / "tasks")
    (out / "FX-01" / "labels_R9.json").unlink()
    write("R2", "ambiguous", decision="edit")
    documented = [Path(p) for p in sorted(glob.glob(str(out / "*" / "labels_*.json")))]  # the guide's glob
    assert [p.name for p in documented] == ["labels_R1.json", "labels_R2.json"]
    rep = merge_labels(documented, key, tmp_path / "tasks")
    assert rep["merged_labels"] == 6 and rep["merged_contract_reviews"] == 2
    assert rep["disagreements"]["FX-01"][0]["candidates"] == ["FX-01-eval-alt-1"]
    assert rep["origin_guesses"]["R1"] == {"correct": 2, "wrong": 0, "unsure": 1}
    for cid in ("FX-01-wrong", "FX-01-eval-nm-9"):  # one packet item, both candidates labeled
        c = load(td / "candidates" / f"{cid}.json", Candidate)
        assert c.final_label().value == "invalid" and not c.human_disagreement()
    alt = load(td / "candidates" / "FX-01-eval-alt-1.json", Candidate)
    assert alt.human_disagreement() and alt.final_label() is None  # unresolved until adjudicated
    r1 = load(td / "contracts" / "reference.json", TaskContract).requirements[0]
    assert [(rv.reviewer, rv.decision) for rv in r1.reviews[-2:]] == [("human:R1", "accept"), ("human:R2", "edit")]
    with pytest.raises(ValueError, match="merged already"):
        merge_labels(documented, key, tmp_path / "tasks")
    with pytest.raises(ValueError, match="empty template"):
        merge_labels([out / "FX-01" / TEMPLATE], key, tmp_path / "tasks")


def test_merge_rejects_unscored_or_inconsistent_labels(tmp_path, monkeypatch):
    td = _task(tmp_path)
    monkeypatch.setattr(tasks_mod, "verify_snapshot", lambda t, s: True)
    out, key = tmp_path / "packet", tmp_path / "key.json"
    export_packet([td], out, key, snapshot_root=FX / "snapshots", repo_root=tmp_path, seed=1)
    tmpl = json.loads((out / "FX-01" / TEMPLATE).read_text())
    base = dict(tmpl, reviewer="R1", contract_reviews={r: {"decision": "accept", "note": ""} for r in tmpl["contract_reviews"]})
    bad_cases = [
        ({"value": "invalid", "violated_requirements": ["R-unknown"], "origin_guess": "unsure", "note": ""}, "active scored"),
        ({"value": "valid", "violated_requirements": ["R1"], "origin_guess": "unsure", "note": ""}, "must not list"),
        ({"value": "ambiguous", "violated_requirements": [], "origin_guess": "unsure", "note": " "}, "needs a note"),
        ({"value": "valid", "violated_requirements": [], "origin_guess": "maybe", "note": ""}, "origin_guess"),
    ]
    for lb, msg in bad_cases:
        d = dict(base, labels={oid: lb for oid in tmpl["labels"]})
        f = tmp_path / "labels_R1.json"
        f.write_text(json.dumps(d))
        with pytest.raises(ValueError, match=msg):
            merge_labels([f], key, tmp_path / "tasks", min_reviewers=1)
