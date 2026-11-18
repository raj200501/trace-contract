"""Blinded review packet (annotation guide v0.3, decision log D43): no origin leaks, merge needs two reviews."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import tracecontract.tasks as tasks_mod
from tracecontract.review import export_packet, merge_labels
from tracecontract.schemas import Candidate, CandidateOrigin, Split, TaskManifest
from tracecontract.store import dump, load

FX = Path(__file__).parent / "fixtures" / "harbor_fx01"


def _task(tmp_path: Path) -> Path:
    td = tmp_path / "tasks" / "FX-01"
    shutil.copytree(FX / "tasks" / "FX-01", td)
    ref = load(td / "candidates" / "FX-01-reference.json", Candidate)
    alt = ref.model_copy(update={"candidate_id": "FX-01-eval-alt-1", "origin": CandidateOrigin.valid_alternative,
                                 "split": Split.eval, "description": "independent alternative SECRET-NOTE"})
    dump(alt, td / "candidates" / "FX-01-eval-alt-1.json")
    m = load(td / "task.json", TaskManifest)
    dump(m.model_copy(update={"candidates": m.candidates + ["candidates/FX-01-eval-alt-1.json"]}), td / "task.json")
    return td


def test_packet_is_blind_and_merge_needs_two_complete_reviews(tmp_path, monkeypatch):
    td = _task(tmp_path)
    monkeypatch.setattr(tasks_mod, "verify_snapshot", lambda t, s: True)
    out, key = tmp_path / "packet", tmp_path / "coordinator" / "key.json"
    with pytest.raises(ValueError, match="outside the packet"):
        export_packet([td], out, out / "key.json", snapshot_root=FX / "snapshots", repo_root=tmp_path, seed=7)
    res = export_packet([td], out, key, snapshot_root=FX / "snapshots", repo_root=tmp_path, seed=7)
    assert res["candidates"] == 2
    text = "\n".join(p.read_text(errors="replace") for p in out.rglob("*") if p.is_file())
    for leak in ("FX-01-wrong", "FX-01-eval-alt-1", "constructed_near_miss", "valid_alternative", "SECRET-NOTE", "construction"):
        assert leak not in text, leak
    ids = json.loads(key.read_text())["tasks"]["FX-01"]
    assert sorted(ids.values()) == ["FX-01-eval-alt-1", "FX-01-wrong"]
    assert all((out / "FX-01" / "candidates" / oid / "state" / "calc.py").is_file() for oid in ids)

    tmpl = json.loads((out / "FX-01" / "labels_template.json").read_text())

    def write(rev: str, vals: dict[str, str]) -> Path:
        d = dict(tmpl, reviewer=rev)
        d["labels"] = {oid: {"value": vals[cid], "violated_requirements": ["R1"] if vals[cid] == "invalid" else [], "note": "n"}
                       for oid, cid in ids.items()}
        f = tmp_path / f"labels_{rev}.json"
        f.write_text(json.dumps(d))
        return f

    a = write("a", {"FX-01-wrong": "invalid", "FX-01-eval-alt-1": "valid"})
    with pytest.raises(ValueError, match="fewer than 2"):
        merge_labels([a], key, tmp_path / "tasks")
    b = write("b", {"FX-01-wrong": "invalid", "FX-01-eval-alt-1": "ambiguous"})
    rep = merge_labels([a, b], key, tmp_path / "tasks")
    assert rep["merged"] == 4
    assert [x["candidate"] for x in rep["disagreements"]["FX-01"]] == ["FX-01-eval-alt-1"]
    c = load(td / "candidates" / "FX-01-wrong.json", Candidate)
    assert [lb.labeler for lb in c.labels[-2:]] == ["human:a", "human:b"] and c.final_label().value == "invalid"
