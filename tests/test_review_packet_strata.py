"""The blinded review packet with candidate strata: the fresh attempts of protocol §15.4 (annotation guide v0.4).

* ``review-packet --strata NAME`` puts the held-out candidates of the stratum ``NAME`` of every task into the packet
  among the task's own: every fresh attempt that the analysis keeps, under ids from the same random pool, one id per
  distinct graded diff (shared with the task's own candidates too); the key records each one's stratum, file and patch
  sha256, and the fresh attempts it leaves out (no attempt record, no audit verdict, or a failed audit), with why.
* The packet is blinded as before: no candidate or attempt id, configuration, instruction variant, stratum name or
  description, attempt record, proposal or audit verdict, the README of a packet without strata and a template of the
  same form.
* A missing stratum, a broken stratum rule (a symbolic link, an id of the task's own) or a task without held-out
  candidates of its own refuses the packet before anything is written, also on the command line.
* ``merge-reviews`` appends the reviews to each stratum candidate's file in the stratum (only its ``labels`` change),
  never to ``task.json`` or the stratum manifest; the analysis of a run graded with ``--strata`` reads them as human
  labels. It refuses, before writing anything, when the stratum no longer lists the file, the file holds another
  patch, the stratum breaks its rules, or the packet was merged already.
* The origin guesses on the task's own candidates are scored as before; those on stratum candidates, which no guess
  names, are counted by configuration and instruction variant.

Synthetic fixtures only (tests/labeling_world.py, whose stratum fresh-v1 holds fresh attempts with attempt records; a
stub grader instead of Docker). These tests check code behaviour and are not research evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
from labeling_world import (
    STRATUM,
    T0,
    TASKS,
    exit_code,
    install,
    make_task,
    run_evaluation,
)

from tracecontract.analysis import _norm_patch, analyze
from tracecontract.review import PACKET_README, TEMPLATE, export_packet, merge_labels
from tracecontract.schemas import (
    AttemptRecord,
    Candidate,
    CandidateOrigin,
    Split,
    TaskManifest,
    sha256_text,
)
from tracecontract.store import dump, load
from tracecontract.strata import StratumError, StratumManifest

# The packet items of the world (tests/labeling_world.py) with strata: the task's own held-out candidates (no reference,
# no evaluation no-op) and the fresh attempts the analysis keeps; T1-fa-1 and T1-fa-5 have the same graded patch, and
# T2-fa-3's audit found a forbidden read.
OWN_ITEMS = {"T1": [["T1-alt"], ["T1-nm"], ["T1-pre"]], "T2": [["T2-alt"], ["T2-nm"], ["T2-pre"]]}
FRESH_ITEMS = {"T1": [["T1-fa-1", "T1-fa-5"], ["T1-fa-2"], ["T1-fa-3"], ["T1-fa-4"]], "T2": [["T2-fa-1"], ["T2-fa-2"], ["T2-fa-4"]]}
FORBIDDEN_READ = "the fresh-attempt audit found a read of forbidden material"
# The reviewers' labels by candidate (the members of one packet item get the same): some differ from D19's proposals.
HUMAN = {"T1-pre": ("invalid", ["R-corr"]), "T1-alt": ("valid", []), "T1-nm": ("invalid", ["R-init"]),
         "T1-fa-1": ("invalid", ["R-corr"]), "T1-fa-2": ("invalid", ["R-corr"]), "T1-fa-3": ("valid", []),
         "T1-fa-4": ("valid", []), "T2-pre": ("invalid", ["R-corr"]), "T2-alt": ("valid", []), "T2-nm": ("invalid", ["R-init"]),
         "T2-fa-1": ("valid", []), "T2-fa-2": ("invalid", ["R-corr"]), "T2-fa-4": ("valid", [])}
GUESS = {"R1": "pre-correction", "R2": "unsure"}


@pytest.fixture()
def world(tmp_path, monkeypatch) -> Path:
    """The scratch repository ``tmp_path/repo``; packets and keys are written next to it, outside it."""
    root = tmp_path / "repo"
    install(root, monkeypatch)
    for t in TASKS:
        make_task(root, t)
    return root


def _tasks(root: Path) -> list[Path]:
    return [root / "tasks" / t for t in TASKS]


def _export(root: Path, out: Path, key: Path, strata: tuple[str, ...] = (STRATUM,), seed: int = 1) -> dict:
    return export_packet(_tasks(root), out, key, snapshot_root=root / "snapshots", repo_root=root, seed=seed, strata=strata)


def _items(key: Path) -> dict[str, list[list[str]]]:
    """The key's packet items per task, as sorted lists of candidate ids."""
    return {t: sorted(sorted(c) for c in items.values()) for t, items in json.loads(key.read_text())["tasks"].items()}


def _stratum_files(root: Path) -> list[Path]:
    return sorted((root / "tasks").glob(f"*/strata/{STRATUM}/candidates/*.json"))


def _records(root: Path) -> dict[Path, bytes]:
    """Every record a merge could write, and the ones it must never write (task.json, the stratum manifests)."""
    paths = [*sorted((root / "tasks").glob("*/candidates/*.json")), *_stratum_files(root),
             *sorted((root / "tasks").glob("*/contracts/reference.json")), *sorted((root / "tasks").glob("*/task.json")),
             *sorted((root / "tasks").glob("*/strata/*.json"))]
    return {p: p.read_bytes() for p in paths}


def _add_fresh(td: Path, kind: str, patch: str, *, record: bool = True, audit: bool = True, split: Split = Split.eval) -> None:
    """Register one more candidate of origin fresh_attempt in the task's stratum (its id ``<task>-<kind>``)."""
    cid = f"{td.name}-{kind}"
    rec = AttemptRecord.model_validate({**load(td / f"strata/{STRATUM}/candidates/{td.name}-fa-1.json", Candidate).attempt
                                        .model_dump(mode="json"), "attempt_id": f"att-{cid}", "patch_sha256": sha256_text(patch)})
    rel = f"strata/{STRATUM}/candidates/{cid}.json"
    dump(Candidate(candidate_id=cid, task_id=td.name, origin=CandidateOrigin.fresh_attempt, split=split, patch=patch,
                   patch_sha256=sha256_text(patch), produced_by="fresh-attempt:config-B",
                   attempt=(rec if audit else rec.model_copy(update={"audit": None})) if record else None), td / rel)
    sm = load(td / "strata" / f"{STRATUM}.json", StratumManifest)
    dump(sm.model_copy(update={"candidates": [*sm.candidates, rel]}), td / "strata" / f"{STRATUM}.json")


def _mark(root: Path) -> None:
    """Write tell-tale text into every stratum record field that the packet must not show."""
    for p in _stratum_files(root):
        c = load(p, Candidate)
        att = c.attempt.model_copy(update={"run_record": "RUNREC-SECRET", "audit": c.attempt.audit.model_copy(
            update={"findings": [*c.attempt.audit.findings, "AUDIT-SECRET"], "record": "AUDITREC-SECRET"})})
        dump(c.model_copy(update={"description": "DESC-SECRET", "attempt": att, "labels": [
            lb.model_copy(update={"note": "PROPOSAL-SECRET"}) for lb in c.labels]}), p)
    for t in TASKS:
        mp = root / "tasks" / t / "strata" / f"{STRATUM}.json"
        dump(load(mp, StratumManifest).model_copy(update={"description": "STRATUM-SECRET"}), mp)


def _review(out: Path, key: Path, task: str, rev: str) -> Path:
    """Reviewer ``rev``'s label file for ``task``: the labels of HUMAN (R1 calls T2-fa-4 ambiguous), one origin guess."""
    tmpl = json.loads((out / task / TEMPLATE).read_text())
    labels = {}
    for oid, cids in json.loads(key.read_text())["tasks"][task].items():
        value, viol = ("ambiguous", []) if (cids[0], rev) == ("T2-fa-4", "R1") else HUMAN[cids[0]]
        labels[oid] = {"value": value, "violated_requirements": viol, "origin_guess": GUESS[rev], "note": "the reason"}
    d = dict(tmpl, reviewer=rev, contract_reviews={r: {"decision": "accept", "note": ""} for r in tmpl["contract_reviews"]},
             labels=labels)
    f = out / task / f"labels_{rev}.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    return f


def _reviews(out: Path, key: Path) -> list[Path]:
    return [_review(out, key, t, rev) for t in TASKS for rev in ("R1", "R2")]


def test_the_packet_holds_the_analysed_stratum_candidates_among_the_tasks_own(world, tmp_path):
    out, key = tmp_path / "packet", tmp_path / "coordinator" / "key.json"
    res = _export(world, out, key)
    assert res == {"packet": str(out.resolve()), "key": str(key.resolve()), "items": 13, "candidates": 14,
                   "strata": {STRATUM: {"candidates": 8, "left_out": 1}}}
    assert _items(key) == {t: sorted(OWN_ITEMS[t] + FRESH_ITEMS[t]) for t in TASKS}
    k = json.loads(key.read_text())
    assert k["strata"] == [STRATUM]
    rec = k["stratum_candidates"]["T1"]["T1-fa-1"]
    c = load(world / "tasks" / "T1" / rec["file"], Candidate)
    assert rec == {"stratum": STRATUM, "file": f"strata/{STRATUM}/candidates/T1-fa-1.json", "patch_sha256": c.patch_sha256}
    assert sorted(k["stratum_candidates"]["T1"]) == ["T1-fa-1", "T1-fa-2", "T1-fa-3", "T1-fa-4", "T1-fa-5"]
    assert k["left_out"] == {"T1": {}, "T2": {"T2-fa-3": {"stratum": STRATUM, "reason": FORBIDDEN_READ}}}
    for oid, cids in k["tasks"]["T1"].items():  # each item: the graded diff and the base with it applied
        c = load(world / "tasks" / "T1" / (k["stratum_candidates"]["T1"][cids[0]]["file"] if cids[0] in k["stratum_candidates"]["T1"]
                                           else f"candidates/{cids[0]}.json"), Candidate)
        item = out / "T1" / "candidates" / oid
        assert (item / "changes.diff").read_text() == _norm_patch(c.patch) + "\n"
        assert (item / "state" / "mod.py").read_text() == c.patch.splitlines()[-1][1:] + "\n"
    # Without strata the packet and its key are what they were: the task's own held-out candidates only.
    out2, key2 = tmp_path / "packet-own", tmp_path / "key-own.json"
    assert _export(world, out2, key2, strata=())["items"] == 6
    assert _items(key2) == OWN_ITEMS
    assert set(json.loads(key2.read_text())) == {"seed", "created_at", "tasks", "packet_files_sha256"}


def test_stratum_candidates_are_blinded_as_the_tasks_own(world, tmp_path):
    _mark(world)
    out, key = tmp_path / "packet", tmp_path / "key.json"
    _export(world, out, key)
    files = sorted(p for p in out.rglob("*") if p.is_file())
    text = "\n".join(p.read_text(encoding="utf-8") for p in files) + "\n".join(str(p.relative_to(out)) for p in out.rglob("*"))
    for leak in ("-fa-", "fresh", "Fresh", "config", "u1", "final", "SECRET", "refcheck", "private-runs", "ef" * 32, T0[:10],
                 "outside the workspace", "attempt", "stratum", "strata", "T2-c'"):
        assert leak not in text, leak  # ids, configuration, variant, records, proposals, audits; T2-fa-3's patch body
    assert (out / "README.md").read_text() == PACKET_README  # the README of a packet without strata
    for t in TASKS:
        assert sorted(p.name for p in (out / t).iterdir()) == ["candidates", "label_template.json", "reference_contract.md",
                                                                 "session.txt"]
        ids = sorted(p.name for p in (out / t / "candidates").iterdir())
        assert all(re.fullmatch(r"C[0-9a-f]{6}", i) for i in ids) and ids == sorted(json.loads(key.read_text())["tasks"][t])
        tmpl = json.loads((out / t / TEMPLATE).read_text())
        assert list(tmpl["labels"]) == ids  # one entry per item, in the order of the random ids
        assert all(v == {"value": None, "violated_requirements": [], "origin_guess": None, "note": ""} for v in tmpl["labels"].values())


def test_identical_graded_diffs_share_one_id_across_the_task_and_the_stratum(world, tmp_path):
    td = world / "tasks" / "T1"
    _add_fresh(td, "fa-6", load(td / "candidates" / "T1-alt.json", Candidate).patch)  # the valid alternative's patch
    out, key = tmp_path / "packet", tmp_path / "key.json"
    _export(world, out, key)
    assert ["T1-alt", "T1-fa-6"] in _items(key)["T1"] and ["T1-fa-1", "T1-fa-5"] in _items(key)["T1"]
    assert len(_items(key)["T1"]) == 7  # 9 candidates, 7 distinct graded diffs


def test_fresh_attempts_the_analysis_excludes_are_left_out(world, tmp_path):
    td = world / "tasks" / "T1"
    _add_fresh(td, "fa-7", "--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = 'T1-g'\n", record=False)
    _add_fresh(td, "fa-8", "--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = 'T1-h'\n", audit=False)
    _add_fresh(td, "fa-9", "--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = 'T1-i'\n", split=Split.dev)  # not held out
    out, key = tmp_path / "packet", tmp_path / "key.json"
    res = _export(world, out, key)
    assert res["strata"] == {STRATUM: {"candidates": 8, "left_out": 3}}
    assert _items(key) == {t: sorted(OWN_ITEMS[t] + FRESH_ITEMS[t]) for t in TASKS}
    assert json.loads(key.read_text())["left_out"] == {
        "T1": {"T1-fa-7": {"stratum": STRATUM, "reason": "no attempt record"},
               "T1-fa-8": {"stratum": STRATUM, "reason": "not audited: its attempt record holds no fresh-attempt audit verdict"}},
        "T2": {"T2-fa-3": {"stratum": STRATUM, "reason": FORBIDDEN_READ}}}
    text = "\n".join(p.read_text() for p in out.rglob("*") if p.is_file())
    for body in ("T1-g", "T1-h", "T1-i", "T2-c"):
        assert body not in text, body


def _no_own_held_out(root: Path) -> None:
    td = root / "tasks" / "T1"
    m = load(td / "task.json", TaskManifest)
    dump(m.model_copy(update={"candidates": ["candidates/T1-reference.json", "candidates/T1-noop-eval.json"]}), td / "task.json")


def _symlinked_candidates(root: Path) -> None:
    folder = root / "tasks" / "T1" / "strata" / STRATUM / "candidates"
    shutil.move(str(folder), str(root / "elsewhere"))
    folder.symlink_to(root / "elsewhere", target_is_directory=True)


def _own_id_in_stratum(root: Path) -> None:
    _add_fresh(root / "tasks" / "T1", "pre", "--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = 'T1-j'\n")


@pytest.mark.parametrize("change, strata, message", [
    (None, ("other",), "T1 has no stratum 'other'"),
    (None, ("../fresh-v1",), "invalid stratum name"),
    (_symlinked_candidates, (STRATUM,), "is a symbolic link"),
    (_own_id_in_stratum, (STRATUM,), "already used by the task's own candidates"),
    (_no_own_held_out, (STRATUM,), "has no held-out candidate of its own"),
])
def test_a_packet_with_strata_is_refused_before_anything_is_written(world, tmp_path, capsys, change, strata, message):
    if change is not None:
        change(world)
    out, key = tmp_path / "packet", tmp_path / "key.json"
    with pytest.raises(StratumError, match=re.escape(message)):
        _export(world, out, key, strata=strata)
    assert not out.exists() and not key.exists()
    code = exit_code(["review-packet", *map(str, _tasks(world)), "--out", str(out), "--key", str(key), "--seed", "1",
                      "--strata", *strata])
    assert isinstance(code, str) and code.startswith("review-packet refused, nothing written: ") and message in code
    assert not out.exists() and not key.exists()


def test_reviews_of_stratum_candidates_are_appended_to_their_stratum_files(world, tmp_path):
    out, key = tmp_path / "packet", tmp_path / "key.json"
    _export(world, out, key)
    before = _records(world)
    rep = merge_labels(_reviews(out, key), key, world / "tasks")
    assert (rep["merged_labels"], rep["merged_contract_reviews"]) == (28, 8)  # 14 candidates and 4 requirements, 2 reviewers
    assert rep["disagreements"] == {"T2": [{"candidates": ["T2-fa-4"], "labels": {"R1": ["ambiguous", []], "R2": ["valid", []]}}]}
    changed = {p for p, b in before.items() if p.read_bytes() != b}
    fresh = [p for p in _stratum_files(world) if p.stem != "T2-fa-3"]
    assert changed == {*fresh, *(world / "tasks" / t / "candidates" / f"{t}-{k}.json" for t in TASKS for k in ("pre", "alt", "nm")),
                       *(world / "tasks" / t / "contracts" / "reference.json" for t in TASKS)}  # never task.json or a manifest
    tag = f"[blinded packet {hashlib.sha256(key.read_bytes()).hexdigest()[:12]}]"
    for p in fresh:
        old, new = json.loads(before[p]), json.loads(p.read_text())
        assert {k: v for k, v in new.items() if k != "labels"} == {k: v for k, v in old.items() if k != "labels"}
        assert new["labels"][:len(old["labels"])] == old["labels"]  # the proposals stay
        added = new["labels"][len(old["labels"]):]
        value, viol = HUMAN["T1-fa-1" if p.stem == "T1-fa-5" else p.stem]
        assert [(x["labeler"], x["labeler_kind"], x["adjudicated"]) for x in added] == [("human:R1", "human", False),
                                                                                        ("human:R2", "human", False)]
        assert all(x["note"].endswith(f"[origin guess: {GUESS[x['labeler'][6:]]}] {tag}") for x in added)
        if p.stem != "T2-fa-4":
            assert all((x["value"], x["violated_requirements"]) == (value, viol) for x in added)
    c = load(world / "tasks" / "T2" / "strata" / STRATUM / "candidates" / "T2-fa-4.json", Candidate)
    assert c.human_disagreement() and c.final_label() is None  # unresolved until adjudicated
    assert load(fresh[0], Candidate).final_label().labeler == "human:R2"
    with pytest.raises(ValueError, match="merged already"):
        merge_labels(_reviews(out, key), key, world / "tasks")
    for p, b in before.items():  # with only the stratum files holding this packet's labels, the merge still refuses
        if p not in fresh:
            p.write_bytes(b)
    with pytest.raises(ValueError, match=r"T1/T1-fa-\d: labels from this packet were merged already"):
        merge_labels(_reviews(out, key), key, world / "tasks")


def test_the_analysis_reads_the_merged_labels_of_the_stratum(world, tmp_path):
    run = run_evaluation(world)  # graded with --strata fresh-v1: the run manifest records each stratum candidate's file
    a = analyze(run, world / "tasks", n_boot=50)  # human labels only
    assert a["meta"]["label_policy"] == "human labels only"
    assert {r["label"] for t in TASKS for r in a["per_task"][t]["initial_plain"] if r["stratum"] == STRATUM} == {None}
    assert sorted(x["candidate"] for x in a["labels"]["T1"]["strata"][STRATUM]["review_queue"]) == [
        "T1-fa-1", "T1-fa-2", "T1-fa-3", "T1-fa-4", "T1-fa-5"]  # every analysed fresh attempt is queued (§15.4)
    out, key = tmp_path / "packet", tmp_path / "key.json"
    _export(world, out, key)
    merge_labels(_reviews(out, key), key, world / "tasks")
    a = analyze(run, world / "tasks", n_boot=50)
    rows = {r["candidate"]: r for t in TASKS for r in a["per_task"][t]["initial_plain"]}
    for cid, (value, _) in HUMAN.items():
        assert rows[cid]["label"] == (None if cid == "T2-fa-4" else value), cid  # T2-fa-4 awaits adjudication
    assert rows["T1-fa-5"]["label"] == "invalid"  # T1-fa-1's packet item; D19 proposed valid for both, the reviewers did not
    assert a["labels"]["T1"]["strata"][STRATUM]["review_queue"] == []
    assert [(x["candidate"], x["reason"]) for x in a["labels"]["T2"]["strata"][STRATUM]["review_queue"]] == [
        ("T2-fa-4", "human reviewers disagree; adjudication needed")]
    fa = a["by_stratum"][STRATUM]["conditions"]["initial_plain"]["false_acceptance"]
    assert (fa["num"], fa["den"]) == (3, 3)  # C1 accepts every fresh attempt; R1 and R2 call three distinct patches invalid


@pytest.mark.parametrize("change, message", [
    ("patch", "holds another patch than the packet showed for T1-fa-2"),
    ("unlisted", "no longer lists strata/fresh-v1/candidates/T1-fa-3.json"),
    # The same candidate id and patch, listed under another file name: the key's file is the one the packet showed.
    ("moved", "no longer lists strata/fresh-v1/candidates/T1-fa-3.json"),
    ("symlink", "is a symbolic link"),
])
def test_the_merge_refuses_a_stratum_changed_since_the_packet(world, tmp_path, change, message):
    out, key = tmp_path / "packet", tmp_path / "key.json"
    _export(world, out, key)
    files = _reviews(out, key)
    td = world / "tasks" / "T1"
    if change == "patch":
        p = td / "strata" / STRATUM / "candidates" / "T1-fa-2.json"
        c = load(p, Candidate)
        patch = c.patch.replace("T1-b", "T1-z")
        dump(c.model_copy(update={"patch": patch, "patch_sha256": sha256_text(patch),
                                  "attempt": c.attempt.model_copy(update={"patch_sha256": sha256_text(patch)})}), p)
    elif change == "unlisted":
        sm = load(td / "strata" / f"{STRATUM}.json", StratumManifest)
        dump(sm.model_copy(update={"candidates": [r for r in sm.candidates if not r.endswith("/T1-fa-3.json")]}),
             td / "strata" / f"{STRATUM}.json")
    elif change == "moved":
        old, new = f"strata/{STRATUM}/candidates/T1-fa-3.json", f"strata/{STRATUM}/candidates/T1-fa-3-moved.json"
        (td / old).rename(td / new)
        sm = load(td / "strata" / f"{STRATUM}.json", StratumManifest)
        dump(sm.model_copy(update={"candidates": [new if r == old else r for r in sm.candidates]}),
             td / "strata" / f"{STRATUM}.json")
        assert load(td / new, Candidate).candidate_id == "T1-fa-3"  # the stratum still lists the candidate, elsewhere
    else:
        _symlinked_candidates(world)
    before = _records(world)
    for dry in (True, False):
        with pytest.raises(ValueError, match=re.escape(message)):
            merge_labels(files, key, world / "tasks", dry_run=dry)
    assert _records(world) == before


def test_origin_guesses_on_stratum_candidates_are_counted_not_scored(world, tmp_path):
    out, key = tmp_path / "packet", tmp_path / "key.json"
    _export(world, out, key)
    rep = merge_labels(_reviews(out, key), key, world / "tasks", dry_run=True)
    # The task's own: R1 guesses pre-correction everywhere, right for T1-pre and T2-pre only; R2 is always unsure.
    assert rep["origin_guesses"] == {"R1": {"correct": 2, "wrong": 4, "unsure": 0}, "R2": {"correct": 0, "wrong": 0, "unsure": 6}}
    zero = dict.fromkeys(("pre-correction", "alternative", "near-miss", "unsure"), 0)
    # The 8 fresh attempts in the packet by configuration and variant: T1-fa-1, T1-fa-2, T2-fa-1 are config-A/u1; T1-fa-5
    # config-A/final; T1-fa-3, T2-fa-2 config-B/u1; T1-fa-4, T2-fa-4 config-B/final (tests/labeling_world.py).
    counts = {"config-A/final": 1, "config-A/u1": 3, "config-B/final": 2, "config-B/u1": 2}
    assert rep["stratum_origin_guesses"] == {STRATUM: {
        rev: {g: {**zero, GUESS[rev]: n} for g, n in counts.items()} for rev in ("R1", "R2")}}
    # A packet without strata reports what it did.
    out2, key2 = tmp_path / "packet-own", tmp_path / "key-own.json"
    _export(world, out2, key2, strata=())
    assert "stratum_origin_guesses" not in merge_labels(_reviews(out2, key2), key2, world / "tasks", dry_run=True)


def test_the_command_line_builds_and_merges_a_packet_with_a_stratum(world, tmp_path, capsys):
    out, key = tmp_path / "packet", tmp_path / "key.json"
    capsys.readouterr()
    assert exit_code(["review-packet", *map(str, _tasks(world)), "--out", str(out), "--key", str(key), "--seed", "2",
                      "--strata", STRATUM]) == 0
    res = json.loads(capsys.readouterr().out)
    assert (res["items"], res["candidates"], res["strata"]) == (13, 14, {STRATUM: {"candidates": 8, "left_out": 1}})
    assert _items(key) == {t: sorted(OWN_ITEMS[t] + FRESH_ITEMS[t]) for t in TASKS}
    assert exit_code(["merge-reviews", *map(str, _reviews(out, key)), "--key", str(key)]) == 0
    assert json.loads(capsys.readouterr().out)["merged_labels"] == 28
    c = load(world / "tasks" / "T1" / "strata" / STRATUM / "candidates" / "T1-fa-4.json", Candidate)
    assert (c.final_label().value, c.proposed_label().value) == ("valid", "invalid")
