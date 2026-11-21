"""The natural PR-review task compiler and its S10 steps (natural_pr.py, natural_env.py; protocol §15.6, §16, §17).

* ``compile_pr_task`` builds task.json, provenance.json, the base snapshot, the candidates (reference, pre-review, no-op),
  the PR reconstruction record that the acceptance gate accepts, the pseudonymised session and the S10 record; or it
  rejects with a stage and a reason (a merge that touches the commented file, an unlicensed or non-permissive LICENSE,
  unreachable SHAs, an empty base-test subset), and never raises on a data problem; ``--plan-only`` writes nothing;
* the merge rule makes a task approximate when no merge touches the commented file;
* the committed index holds ids, SHAs, licences, file hashes and S10 outcomes, no text, and the rejection ledger gets
  one S10 row per rejected family (scripts/build_manifests.py);
* the S10 environment and base-test functions plan their commands without Docker or network, and with stubs they
  reject an environment over the cap, an unresolvable closure and base tests that fail to collect;
* a re-run of S10 over a task directory that holds more than S10's own material (contracts, labels, a frozen B1, verifiers
  other than B1, candidates beyond the four S10 ones, a reviewed eligibility, any file S10 does not write) is refused and
  deletes nothing, while an S10-only directory is rebuilt as before; the S10 environment step also refuses material that
  appears while it runs, before its next write;
* ``pr_recheck`` rewrites only the reconstruction record, holds each stored patch to its commit's whole tree, and never
  certifies a session file the compiler does not rebuild byte for byte;
* the index summarises generated tests and the label step's copies of repository tests, gives each row its sample
  (§19.3) and its session's sanitize-natural:v1 counts (the pass's own and the rules' over every stored string).

A synthetic world only (tests/natural_pr_world.py); Docker and the network are never used. Not research evidence.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from natural_pr_world import build_world, forbidden, written_text
from tracecontract import natural_env as env
from tracecontract import natural_pr as npr
from tracecontract.contract import task_gate
from tracecontract.ingest.github_pr import AIDev, BareClone
from tracecontract.ingest.sanitize_natural import sanitize_session
from tracecontract.patches import apply_patch, filter_patch, split_sections
from tracecontract.reconstruction import RECORD, recorded_check
from tracecontract.sandbox.docker_runner import RawRun, _req_hash
from tracecontract.schemas import (
    Candidate, CandidateOrigin, Eligibility, LabelerKind, Population, ProvenanceRecord, Session, Snapshot, Split, TaskManifest,
    VerifierSpec,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, load
from tracecontract.verifier import freeze

pytest.importorskip("duckdb")
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The world, its families, and the result of compiling every family once."""
    w = build_world(tmp_path_factory.mktemp("prtasks"))
    fams = npr.load_families(w.qualifying)
    aidev = AIDev(w.aidev, threads=1)
    results = {f.task_id: npr.compile_pr_task(f, w.out, aidev=aidev) for f in fams}
    return w, fams, aidev, results


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def test_families_follow_the_s11_order_then_the_reserves(built):
    w, fams, _, _ = built
    assert [(f.task_id, f.role, f.pr_id) for f in fams] == [
        ("NP-01", "family", 9001), ("NP-02", "family", 9003), ("NP-03", "family", 9002), ("NP-04", "family", 9005),
        ("NP-05", "family", 9006), ("NP-06", "family", 9008), ("NP-07", "family", 9007), ("NP-08", "reserve", 9004)]
    assert npr.find_family(fams, 9002).task_id == "NP-03"
    with pytest.raises(KeyError):
        npr.find_family(fams, 1)


def test_explicit_task_ids_are_used_and_the_first_samples_families_are_unchanged(built, tmp_path):
    w, fams, _, _ = built
    q = json.loads(w.qualifying.read_text())
    assert not any("task_id" in p for p in q["prs"]) and npr.load_families(w.qualifying) == fams  # the old file loads as before
    # The combined input of both samples (§19.3), with the PRs in another order: every PR names its task id and role; the first
    # sample's keep theirs, the new families are numbered from NP-26, then a reserve; a PR beyond the cap has no task id.
    ids = {f.pr_id: (f.task_id, f.role) for f in fams}
    prs = [{**p, "task_id": ids[p["pr_id"]][0], "role": ids[p["pr_id"]][1], "sample": "first"} for p in reversed(q["prs"])]
    c0, p0 = q["comments"][0], q["prs"][0]
    comments = [*q["comments"]]
    for pr_id, cids, tid, role in ((9103, [8203], None, "beyond_the_cap"), (9102, [8202], "NP-27", "reserve"),
                                   (9101, [8211, 8201], "NP-26", "family")):
        comments += [{**c0, "comment_id": cid, "pr_id": pr_id, "sample": "extension"} for cid in cids]
        prs.insert(0, {**p0, "pr_id": pr_id, "qualifying_comment_ids": cids, "earliest_qualifying_comment_id": min(cids),
                       "s11_family": role == "family", "task_id": tid, "role": role, "sample": "extension"})
    path = tmp_path / "s9_qualifying_combined.json"
    path.write_text(json.dumps({**q, "comments": comments, "prs": prs}, indent=1))
    loaded = npr.load_families(path)
    assert loaded[:len(fams)] == fams  # the first sample's families: the same ids, PRs, corrections and every other field
    new = [(f.task_id, f.role, f.pr_id, f.comment_id, f.other_qualifying_comment_ids) for f in loaded[len(fams):]]
    assert new == [("NP-26", "family", 9101, 8201, (8211,)), ("NP-27", "reserve", 9102, 8202, ())]
    assert npr.find_family(loaded, 9101).task_id == "NP-26" and 9103 not in {f.pr_id for f in loaded}
    prs[0]["task_id"] = "NP-27"  # a task id given twice is refused
    path.write_text(json.dumps({**q, "comments": comments, "prs": prs}, indent=1))
    with pytest.raises(ValueError, match="more than one PR"):
        npr.load_families(path)


def test_outcomes_of_every_family(built):
    _, _, _, res = built
    assert {t: r["outcome"] for t, r in res.items()} == {
        "NP-01": "built", "NP-02": "rejected", "NP-03": "built", "NP-04": "rejected", "NP-05": "rejected", "NP-06": "built",
        "NP-07": "rejected", "NP-08": "built"}
    reasons = {t: r.get("reason") for t, r in res.items() if r["outcome"] == "rejected"}
    assert reasons["NP-02"] == "a merge between the base and the addressing commit changes the commented file (§15.6)"
    assert reasons["NP-04"] == "non-permissive licence at the base: GPL-3.0-only"
    assert reasons["NP-05"] == "unlicensed: no LICENSE file at the repository root at the base"
    assert reasons["NP-07"].startswith("base tests: the base-test subset is empty")
    assert all(res[t]["stage"] == "S10" for t in reasons)
    assert res["NP-02"]["details"]["merges_touching"] == [built[0].shas["cm"]]


def test_a_clean_family_builds_every_record(built):
    w, _, _, res = built
    td = w.out / "NP-01"
    assert sorted(p.name for p in td.iterdir()) == ["candidates", "provenance.json", RECORD, "s10.json", "session.json",
                                                    "snapshot.json", "task.json"]
    m = load(td / "task.json", TaskManifest)
    assert m.population == Population.natural_pr_review and m.status == "pending_review" and m.family_id == "NP-01"
    assert m.snapshot_source.commit == w.shas["base101"] and m.snapshot_source.repo_url == "https://github.com/{owner}/{owner}-tools"
    assert m.repo_test_args == ["-o", "addopts=", "tests/test_mod.py"] and m.candidate_pythonpath == "/work"
    assert m.env_requirements == [] and m.contracts == {} and m.scripted_turns == []
    prov = load(td / "provenance.json", ProvenanceRecord)
    pr = prov.natural_pr
    assert prov.eligibility == Eligibility.pending_review and prov.source_revision == npr.AIDEV_REVISION
    assert prov.source_id == "aidev:pr:9001/comment:8001" and prov.repo_url == m.snapshot_source.repo_url
    assert prov.licenses == {"code": "MIT", "code_aidev": "MIT", "dataset": "CC-BY-4.0"} and "MIT" in prov.permission_basis
    assert (pr.base_commit, pr.reviewed_commit, pr.addressing_commit, pr.head_commit, pr.first_commit) == (
        w.shas["base101"], w.shas["a2"], w.shas["a3"], w.shas["a4"], w.shas["a1"])
    assert pr.base_rule == "merge_base" and pr.merge_state == "no_merges" and pr.licence_agrees is True
    assert pr.reply_comment_ids == [8102] and pr.issue_id == 7001 and pr.owner_masked is True
    assert prov.trace_sha256 == load(td / "session.json", Session).trace_sha256
    assert prov.triage.category.value == "candidate" and prov.triage.correction_event_ids == ["aidev-pr-9001/review/8001"]
    snap = load(td / "snapshot.json", Snapshot)
    base = w.out.parent / "snapshots" / "NP-01"
    assert manifest_sha256(manifest(base)) == snap.file_manifest_sha256 == prov.snapshot_manifest_sha256
    assert snap.fidelity.value == "approximate" and snap.leakage_check is None
    assert snap.approximations == ["the reference patch leaves out 1 file change(s) the grader cannot apply (binary file)"]
    s10 = json.loads((td / "s10.json").read_text())
    assert s10["outcome"] == "built" and s10["base_tests"]["subset"] == ["tests/test_mod.py"]
    assert s10["base_tests"]["planned_run"]["planned"] and s10["environment"] is None
    assert s10["closure_plan"]["requirements"] == ["fx-requests>=2", "pytest>=7", "hypothesis"]
    assert res["NP-01"]["reconstruction"] == "passed"


def test_candidates_reproduce_their_commits(built, tmp_path):
    w, _, _, _ = built
    td, base = w.out / "NP-01", w.out.parent / "snapshots" / "NP-01"
    cands = {c.candidate_id: c for c in (load(td / p, Candidate) for p in load(td / "task.json", TaskManifest).candidates)}
    assert set(cands) == {"NP-01-reference", "NP-01-pre-review", "NP-01-noop-dev", "NP-01-noop-eval"}
    ref, pre = cands["NP-01-reference"], cands["NP-01-pre-review"]
    assert (ref.origin, ref.split, pre.origin, pre.split) == (CandidateOrigin.reference, Split.dev,
                                                             CandidateOrigin.natural_pre_review, Split.eval)
    se = pre.source_evidence_label()
    assert se.value == "invalid" and se.labeler_kind == LabelerKind.source_evidence and pre.proposed_label() is None
    bare = w.repos / "101.git"
    for cand, commit in ((ref, w.shas["a3"]), (pre, w.shas["a2"])):
        ws, _ = apply_patch(base, cand.patch, tmp_path / cand.candidate_id)
        for rel in ("fxpkg/mod.py", "tests/test_mod.py"):
            assert (ws / rel).read_bytes() == _git(bare, "show", f"{commit}:{rel}")
    assert "data/logo.bin" not in ref.patch and "tests/test_mod.py" in ref.patch  # binary left out; tests kept (B1)
    assert filter_patch(ref.patch)[1].ok and "tests/test_mod.py" in filter_patch(ref.patch)[1].removed_protected


def test_the_gate_accepts_the_pr_reconstruction_record(built, tmp_path):
    w, _, _, _ = built
    td = tmp_path / "NP-01"
    shutil.copytree(w.out / "NP-01", td)
    rc = recorded_check(td, w.root)  # dispatches to natural_pr.recorded_pr_check for this population
    assert rc.ok and rc.status == "passed"
    gate = task_gate(td, w.root)  # the gate's other natural rules (S10 outcome, committed index) are not this test's subject
    assert not [r for r in gate.reasons if r.startswith("reconstruction")]
    assert {"provenance: eligibility is 'pending_review'; a reviewer must find the source eligible",
            "contract: the task has no reference contract"} <= set(gate.reasons)
    rec = json.loads((td / RECORD).read_text())
    assert rec["method"] == npr.PR_METHOD and [c["status"] for c in rec["checks"]] == ["passed"] * 6
    # A changed session file makes the record stale (the hint names the non-destructive re-check); a current failed record
    # refuses the task.
    (td / "session.json").write_text((td / "session.json").read_text() + "\n")
    stale = recorded_check(td, w.root)
    assert not stale.ok and not stale.failed and "session_sha256" in stale.problems[0]
    assert "natural_pr.pr_recheck" in stale.problems[0] and "compile-pr-task" not in stale.problems[0]
    rec["inputs"]["session_sha256"] = npr.pr_current_inputs(td)["session_sha256"]
    rec.update(status="failed", passed=False)
    (td / RECORD).write_text(json.dumps(rec))
    assert recorded_check(td, w.root).failed
    assert [r for r in task_gate(td, w.root).refusals if r.startswith("reconstruction")]


def test_the_merge_rule_makes_a_task_approximate(built):
    w, _, _, res = built
    pr = load(w.out / "NP-03" / "provenance.json", ProvenanceRecord).natural_pr
    assert pr.merge_state == "merges_not_touching_the_commented_file" and pr.merges == [w.shas["bm"]]
    assert pr.fidelity.value == "approximate" and res["NP-03"]["fidelity"] == "approximate"
    assert any("merge commit" in a for a in pr.approximations)
    # The rejected family keeps only its rejection record, and no snapshot.
    td = w.out / "NP-02"
    assert [p.name for p in td.iterdir()] == ["rejection.json"] and not (w.out.parent / "snapshots" / "NP-02").exists()
    rej = json.loads((td / "rejection.json").read_text())
    assert rej["stage"] == "S10" and rej["pr_id"] == 9003 and rej["details"]["base_commit"] == w.shas["base101"]


def test_other_rejections_never_raise(built):
    w, fams, aidev, _ = built
    fam = npr.find_family(fams, 9001)
    for change, reason in (({"addressing_commit": "f" * 40}, "unreachable SHAs: the addressing commit is not in the clone"),
                           ({"reviewed_commit": "e" * 40, "addressing_commit": "f" * 40},
                            "unreachable SHAs: the reviewed and the addressing commits are not in the clone"),
                           ({"addressing_commit": w.shas["a1"]}, "the addressing commit does not descend from the reviewed commit"),
                           ({"path": "fxpkg/nowhere.py"}, "the commented file is not a file at the reviewed commit"),
                           ({"bare_clone": w.root / "missing.git"}, "a git command failed")):
        r = npr.compile_pr_task(dataclasses.replace(fam, **change), w.root / "other", aidev=aidev, plan_only=True)
        assert r["outcome"] == "rejected" and r["stage"] == "S10" and r["reason"].startswith(reason), (change, r["reason"])
    assert not (w.root / "other").exists()  # plan-only writes nothing


def test_without_a_default_branch_the_base_is_the_first_commits_parent(built):
    w, fams, aidev, _ = built
    fam = dataclasses.replace(npr.find_family(fams, 9001), default_branch_ref="refs/heads/gone")
    r = npr.compile_pr_task(fam, w.root / "plan", aidev=aidev, plan_only=True)
    assert r["outcome"] == "planned" and r["base"]["rule"] == "parent_of_first_commit" and r["fidelity"] == "approximate"
    assert r["base"]["commit"] == w.shas["base101"]


def test_plan_only_reports_base_fidelity_licence_and_closure(built, tmp_path):
    w, fams, aidev, _ = built
    out = tmp_path / "tasks"
    r = npr.compile_pr_task(npr.find_family(fams, 9001), out, aidev=aidev, plan_only=True)
    assert r["outcome"] == "planned" and not out.exists() and not (tmp_path / "snapshots").exists()
    assert r["base"]["commit"] == w.shas["base101"] and r["fidelity"] == "exact" and r["merge_state"] == "no_merges"
    assert r["licence"] == {"spdx": "MIT", "aidev": "MIT", "agrees": True, "permissive": True}
    c = r["closure"]
    assert c["requirements"] == ["fx-requests>=2", "pytest>=7", "hypothesis"] and c["uploaded_prior_to"] == "2025-02-01T10:00:00Z"
    cmd = c["commands"][0]
    assert "--only-binary=:all:" in cmd and cmd[cmd.index("--python-version") + 1] == "3.12" and "--dry-run" in cmd
    assert cmd[cmd.index("--uploaded-prior-to") + 1] == "2025-02-01T10:00:00Z" and "manylinux2014_x86_64" in cmd
    assert r["tests"]["test_directory"] == "tests" and r["session"]["events"] == 8
    assert not [x for x in forbidden() if x.lower() in json.dumps(r).lower()]  # the result holds no thread text or login


def test_the_monorepo_package_is_the_workspace(built):
    w, _, _, _ = built
    td, base = w.out / "NP-06", w.out.parent / "snapshots" / "NP-06"
    assert sorted(p.name for p in base.iterdir()) == ["fxpkg", "pyproject.toml", "tests"]  # packages/fxsub only
    m = load(td / "task.json", TaskManifest)
    ref = load(td / "candidates" / "NP-06-reference.json", Candidate)
    assert m.snapshot_source.subdir == "packages/fxsub" and "a/fxpkg/mod.py" in ref.patch and "packages/" not in ref.patch
    snap = load(td / "snapshot.json", Snapshot)
    assert "the workspace is the package directory of a monorepo, not the whole repository" in snap.approximations
    assert "1 changed file(s) outside the workspace are left out of the candidates" in snap.approximations


def _partial_clone(src: Path, dest: Path, home: Path) -> Path:
    """A blob-less partial clone of ``src`` (file protocol), as the S9 fetches made them from GitHub."""
    for k, v in (("uploadpack.allowFilter", "true"), ("uploadpack.allowAnySHA1InWant", "true")):
        subprocess.run(["git", "-C", str(src), "config", k, v], check=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "HOME": str(home), "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none", f"file://{src}", str(dest)], check=True, env=env,
                   capture_output=True)
    return dest


def test_the_base_of_a_monorepo_package_fetches_no_blob_outside_the_package(built, tmp_path):
    """On a blob-less partial clone the snapshot fetches the package's blobs only: ``git archive <commit> <subdir>``
    fetched every missing blob of the whole commit (found on real data, where a 90-file package fetched 44,648 blobs)."""
    w, _, _, _ = built
    dest = _partial_clone(w.root / "src" / "105", tmp_path / "repos" / "205.git", tmp_path)
    log = tmp_path / "fetch.jsonl"
    clone = BareClone(dest, repo_id=205, fetch_log=log, allow_file_protocol=True, poll_s=0.05)
    base = w.shas["base105"]
    tree = clone.ls_tree(base)
    inside = {o for m, t, o, p in tree if t == "blob" and p.startswith("packages/fxsub/")}
    outside = {o for m, t, o, p in tree if t == "blob" and not p.startswith("packages/fxsub/")} - inside
    assert inside and outside and (inside | outside) <= clone.missing(base)
    snap = npr.materialize_base(clone, base, "packages/fxsub", tmp_path / "snap")
    assert not (snap["mismatched"] or snap["missing"] or snap["extra"]) and snap["blobs_fetched"] == len(inside)
    assert outside <= clone.missing(base) and not inside & clone.missing(base)  # nothing outside the package is fetched
    assert [json.loads(ln)["label"] for ln in log.read_text().splitlines()] == [f"base tree {base[:12]} ({len(inside)} blobs)"]
    assert manifest_sha256(manifest(tmp_path / "snap")) == manifest_sha256(manifest(w.out.parent / "snapshots" / "NP-06"))


def test_nothing_written_holds_a_login_or_thread_identifier(built):
    w, _, _, _ = built
    text = written_text(w.out)
    assert not [x for x in forbidden() if x.lower() in text]


def test_rejecting_a_built_task_after_s10(built, tmp_path):
    w, _, _, _ = built
    td = tmp_path / "NP-03"
    shutil.copytree(w.out / "NP-03", td)
    npr.reject_task(td, "environment too large: the wheelhouse would hold 3.20 GB, over the 1.5 GB cap (§17.1)")
    m, prov = load(td / "task.json", TaskManifest), load(td / "provenance.json", ProvenanceRecord)
    assert m.status == "rejected" and prov.eligibility == Eligibility.rejected
    assert prov.rejection_reasons == ["S10: environment too large: the wheelhouse would hold 3.20 GB, over the 1.5 GB cap (§17.1)"]
    assert json.loads((td / "s10.json").read_text())["outcome"] == "rejected"
    assert task_gate(td, w.root).refusals
    row = npr.index_row(td, None)
    assert row["s10"]["outcome"] == "rejected" and row["status"] == "rejected"


def test_the_index_holds_no_text_and_hashes_the_files(built, tmp_path):
    w, fams, _, _ = built
    out = tmp_path / "natural_tasks_index.json"
    idx = npr.write_natural_index(w.out, out, families=fams)
    rows = {r["task_id"]: r for r in idx["tasks"]}
    assert idx["counts"] == {"built": 4, "rejected": 4, "s11": 0} and list(rows) == [f.task_id for f in fams]
    assert rows["NP-02"]["s10"] == {"outcome": "rejected", "stage": "S10",
                                    "reason": "a merge between the base and the addressing commit changes the commented file (§15.6)"}
    assert rows["NP-02"]["replaced_by"] == "NP-08"  # §17.3: the next PR of the repository takes its place
    r1 = rows["NP-01"]
    assert r1["commits"]["addressing"] == w.shas["a3"] and r1["licence"]["file_spdx"] == "MIT" and r1["fidelity"] == "approximate"
    assert r1["s10"]["outcome"] == "built" and r1["s10"]["environment"] == "pending" and r1["s10"]["b1"] == "pending"
    for rel, digest in r1["files"].items():
        assert hashlib.sha256((w.out / "NP-01" / rel).read_bytes()).hexdigest() == digest
    text = out.read_text().lower()
    assert not [x for x in forbidden() if x.lower() in text]
    assert "github.com" not in text and "fxpkg" not in text and "add() is wrong" not in text and "@" not in text
    # Families not built yet are listed as such.
    idx2 = npr.write_natural_index(tmp_path / "empty", tmp_path / "i2.json", families=fams)
    assert {r["s10"]["outcome"] for r in idx2["tasks"]} == {"not built"}


def _bm():
    spec = importlib.util.spec_from_file_location("build_manifests_np", REPO / "scripts" / "build_manifests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_s10_rejections_enter_the_ledger(built, tmp_path):
    w, fams, _, _ = built
    root = tmp_path / "repo"
    (root / "tasks").mkdir(parents=True)
    npr.write_natural_index(w.out, root / "data" / "manifests" / "natural_tasks_index.json", families=fams)
    bm = _bm()
    index, ledger = bm.build(root)
    s10 = [r for r in ledger["rejections"] if r.get("stage") == "S10"]
    assert [r["task_id"] for r in s10] == ["NP-02", "NP-04", "NP-05", "NP-07"]
    assert s10[0] == {"source_id": "pr:9003", "population": "natural:pr-review", "stage": "S10",
                      "reasons": ["a merge between the base and the addressing commit changes the commented file (§15.6)"],
                      "comment_id": 8003, "pr_id": 9003, "repo_id": 101, "task_id": "NP-02", "replaced_by": "NP-08"}
    assert "of the 8 families and reserves of S10 in natural_tasks_index.json, 4 are rejected" in ledger["note"]
    assert "natural:pr-review" not in index["yield_by_population"]
    # Without the index, the committed manifests regenerate as they are.
    if (REPO / "data" / "manifests" / "screening_natural_aidev_s9.json").is_file() and not (REPO / "data" / "manifests" / bm.NATURAL_INDEX).exists():
        i2, l2 = bm.build(REPO)
        assert json.loads((REPO / "data" / "manifests" / "rejection_ledger.json").read_text()) == l2
        assert json.loads((REPO / "data" / "manifests" / "provenance_index.json").read_text()) == i2


@pytest.mark.skipif(not (REPO / "tasks" / "CS-01" / "provenance.json").is_file(), reason="the pilot tasks are not in this checkout")
def test_the_pilot_provenance_records_reserialise_byte_for_byte():
    """The new optional field (schemas.ProvenanceRecord.natural_pr) is omitted while unset."""
    for f in sorted(REPO.glob("tasks/CS-0*/provenance.json")):
        raw = f.read_text(encoding="utf-8")
        rec = ProvenanceRecord.model_validate_json(raw)
        assert rec.natural_pr is None and rec.model_dump_json(indent=2) + "\n" == raw
        assert "natural_pr" not in rec.model_dump(mode="json")


# --------------------------------------------------------------------------- natural_env


def test_declared_dependencies_and_the_planned_closure():
    pyproject = ("[project]\nname = \"p\"\ndependencies = [\"a>=1\", \"b @ git+https://example.invalid/b.git\"]\n"
                 "[project.optional-dependencies]\ntest = [\"pytest>=7\", \"t1\"]\ndocs = [\"sphinx\"]\n"
                 "[dependency-groups]\ndev = [\"d1\", {include-group = \"lint\"}]\nlint = [\"ruff\"]\n")
    poetry = ("[tool.poetry]\nname = \"q\"\n[tool.poetry.dependencies]\npython = \"^3.9\"\nc = \"^1.2.3\"\nd = \"~0.4\"\n"
              "e = {version = \"^0.2.0\", optional = true}\n[tool.poetry.group.test.dependencies]\npytest-mock = \"*\"\n")
    setup_py = "REQ = ['x>=1']\nsetup(name='r', install_requires=REQ + ['y'], extras_require={'test': ['z']})\n"
    reqs = "-r base.txt\n-e ../sibling\nw==1.0  # pinned\n--index-url https://example.invalid\npkg @ https://example.invalid/p.whl\n"
    d = env.declared_dependencies({"pyproject.toml": pyproject})
    assert d["runtime"] == ["a>=1"] and d["test"] == ["pytest>=7", "t1"] and d["test_sets"] == ["extra:test"]
    assert d["url_requirements"] == ["b"] and "group:dev" in d["other_sets"]
    p = env.declared_dependencies({"pyproject.toml": poetry})
    assert p["runtime"] == ["c>=1.2.3,<2", "d>=0.4,<0.5"] and p["test"] == ["pytest-mock"] and p["project"] == "q"
    s = env.declared_dependencies({"setup.py": setup_py, "requirements.txt": reqs, "requirements-dev.txt": "dv\n"})
    assert s["runtime"] == ["w==1.0", "x>=1", "y"] and s["test"] == ["z"] and s["project"] == "r"
    assert s["path_requirements"] == [{"from": "requirements.txt", "path": "../sibling"}] and s["url_requirements"] == ["pkg"]
    assert env.declaration_files(["setup.py", "a/setup.py", "requirements/dev.txt", "docs/x/requirements.txt", "requirements.txt"]) == [
        "requirements.txt", "requirements/dev.txt", "setup.py"]
    plan = env.plan_closure(declared_base=d, declared_later=[{"runtime": ["a>=1", "newpkg>=2", "PyYAML"], "test": []}],
                            changed_code={"m.py": "import newpkg\nfrom os import path\n"}, base_date="2025-01-05T14:01:09-08:00",
                            path_names={"../sibling": "sibling-pkg"})
    assert plan["pr_added"] == ["newpkg>=2"] and plan["pr_added_not_imported"] == ["PyYAML"]
    assert plan["requirements"] == ["a>=1", "pytest>=7", "t1", "newpkg>=2", "sibling-pkg", "hypothesis"]
    assert plan["uploaded_prior_to"] == "2025-01-05T22:01:09Z" and plan["path_only"] == ["sibling-pkg"]
    assert env.imports_distribution("PyYAML", {"yaml"}) and not env.imports_distribution("pyyaml", {"os"})


class _Proc:
    def __init__(self, rc: int, stderr: str = "") -> None:
        self.returncode, self.stderr, self.stdout = rc, stderr, ""


def _report(path: Path, items: list[tuple[str, str, str]]) -> None:
    path.write_text(json.dumps({"install": [{"metadata": {"name": n, "version": v},
                                             "download_info": {"url": f"https://files.example.invalid/{f}",
                                                               "archive_info": {"hashes": {"sha256": "ab" * 32}}}}
                                            for n, v, f in items]}))


def test_resolve_closure_pins_and_checks_the_cap(tmp_path):
    plan = {"requirements": ["a>=1", "big"], "uploaded_prior_to": "2025-01-01T00:00:00Z", "path_only": []}
    dry = env.resolve_closure(plan, tmp_path / "w0", dry_run=True)
    assert dry["planned"] and dry["commands"][0][-2:] == ["a>=1", "big"]

    def run_ok(cmd, **kw):
        _report(Path(cmd[cmd.index("--report") + 1]), [("a", "1.2", "a-1.2-py3-none-any.whl"), ("Big", "2.0", "big-2.0-cp312.whl")])
        return _Proc(0)

    sizes = {"a": 1000, "big": 2_000_000_000}
    fetch = lambda n, v: {"urls": [{"filename": f"{n}-{v}-py3-none-any.whl" if n == "a" else "big-2.0-cp312.whl", "size": sizes[n]}]}  # noqa: E731
    over = env.resolve_closure(plan, tmp_path / "w1", run=run_ok, fetch_json=fetch)
    assert over["rejected"] and over["reason"].startswith("environment too large") and over["pins"] == ["a==1.2", "big==2.0"]
    sizes["big"] = 5_000
    ok = env.resolve_closure(plan, tmp_path / "w2", run=run_ok, fetch_json=fetch)
    assert "rejected" not in ok and ok["wheelhouse_bytes"] == 6_000 and ok["files"][0]["sha256"] == "ab" * 32
    fail = env.resolve_closure(plan, tmp_path / "w3", run=lambda c, **k: _Proc(1, "ERROR: No matching distribution found for Big_Thing"))
    assert fail["rejected"] and fail["reason"].startswith("no resolvable closure") and fail["wheel_less"] == ["big-thing"]
    # A requirement mapped from a local path, with no release in the index, is dropped once and recorded.
    calls = []

    def run_path(cmd, **kw):
        calls.append(cmd)
        if "sibling-pkg" in cmd:
            return _Proc(1, "No matching distribution found for sibling-pkg")
        return run_ok(cmd)

    plan2 = {"requirements": ["a>=1", "sibling-pkg"], "uploaded_prior_to": None, "path_only": ["sibling-pkg"]}
    got = env.resolve_closure(plan2, tmp_path / "w4", run=run_path, fetch_json=fetch)
    assert len(calls) == 2 and got["dropped_path_requirements"] == ["sibling-pkg"] and "rejected" not in got


def _sdist(path: Path, files: dict[str, str]) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"pkg-1.0/{name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def test_pure_python_sdists_and_their_sandboxed_build(tmp_path):
    pure = _sdist(tmp_path / "pure-1.0.tar.gz", {"setup.py": "from setuptools import setup\nsetup(name='pure')\n", "pure/__init__.py": ""})
    native = _sdist(tmp_path / "native-1.0.tar.gz", {"setup.py": "setup(ext_modules=[Extension('x', ['x.c'])])\n", "x.c": "int x;"})
    rusty = _sdist(tmp_path / "rusty-1.0.tar.gz", {"pyproject.toml": "[build-system]\nbuild-backend = \"maturin\"\n", "src/lib.rs": ""})
    assert env.is_pure_python_sdist(pure) == (True, [])
    ok, why = env.is_pure_python_sdist(native)
    assert not ok and "setup.py declares extension modules" in why and "native source or build file: x.c" in why
    assert not env.is_pure_python_sdist(rusty)[0]
    plan = env.build_sdist_wheel(pure, tmp_path / "wheels", tmp_path / "out", dry_run=True)
    assert plan["planned"] and plan["command"][:5] == ["docker", "run", "--rm", "--network", "none"] and "--no-index" in plan["command"]
    assert env.build_sdist_wheel(native, tmp_path / "wheels", tmp_path / "out", dry_run=True)["rejected"]


def _out_mount(cmd: list[str]) -> Path:
    return Path(next(a for a in cmd if a.endswith(":/out:rw")).rsplit(":", 2)[0])


def test_the_sandboxed_sdist_build_writes_only_into_a_private_directory_of_its_user(tmp_path):
    """Found on real data: ``/out`` was the root-owned directory of built wheels, which the container's user cannot write
    (``Permission denied``), so no sdist could build; a shared directory would also expose the earlier wheels."""
    (tmp_path / "in").mkdir()
    sd = _sdist(tmp_path / "in" / "pure-1.0.tar.gz", {"setup.py": "from setuptools import setup\nsetup(name='pure')\n"})
    out = tmp_path / "work" / "built-wheels"
    out.mkdir(parents=True)
    (out / "zz-9.0-py3-none-any.whl").write_bytes(b"earlier")
    seen: dict = {}

    def run(cmd, **kw):
        mount = _out_mount(cmd)
        st = mount.stat()
        seen.update(mount=mount, uid=st.st_uid, mode=st.st_mode & 0o777, user=cmd[cmd.index("--user") + 1],
                    empty=not any(mount.iterdir()), network=cmd[cmd.index("--network") + 1])
        (mount / "pure-1.0-py3-none-any.whl").write_bytes(b"wheel")
        return _Proc(0)

    got = env.build_sdist_wheel(sd, tmp_path / "wheels", out, run=run)
    assert got["wheel"] == "pure-1.0-py3-none-any.whl" and got["wheel_sha256"] == hashlib.sha256(b"wheel").hexdigest()
    assert seen["mount"] != out and seen["empty"] and seen["network"] == "none" and not seen["mount"].exists()
    assert seen["user"] == f"{env.SDIST_BUILD_UID}:{env.SDIST_BUILD_UID}"
    assert (seen["uid"], seen["mode"]) == (env.SDIST_BUILD_UID, 0o700) if os.geteuid() == 0 else seen["mode"] == 0o777
    assert (out / "pure-1.0-py3-none-any.whl").read_bytes() == b"wheel" and (out / "zz-9.0-py3-none-any.whl").read_bytes() == b"earlier"

    def run_link(cmd, **kw):  # a build that leaves a symbolic link instead of a wheel
        (_out_mount(cmd) / "pure-1.1-py3-none-any.whl").symlink_to(out / "zz-9.0-py3-none-any.whl")
        return _Proc(0)

    def run_two(cmd, **kw):  # a build that leaves more than the one wheel
        for n in ("pure-1.1-py3-none-any.whl", "other-1.0-py3-none-any.whl"):
            (_out_mount(cmd) / n).write_bytes(b"w")
        return _Proc(0)

    for bad in (run_link, run_two):
        rej = env.build_sdist_wheel(sd, tmp_path / "wheels", out, run=bad)
        assert rej["rejected"] and "did not build into a wheel" in rej["reason"]
    assert sorted(p.name for p in out.iterdir()) == ["pure-1.0-py3-none-any.whl", "zz-9.0-py3-none-any.whl"]
    assert sorted(p.name for p in out.parent.iterdir()) == ["built-wheels"]  # no build directory is left behind


def test_build_image_fills_the_wheelhouse_build_env_image_reads(tmp_path):
    pins = ["b==2", "a==1"]
    dry = env.build_image(pins, tmp_path, dry_run=True)
    assert dry["wheelhouse"] == str(tmp_path / f"wheelhouse-{_req_hash(sorted(pins))}") and "--only-binary=:all:" in dry["commands"][0]

    def run(cmd, **kw):
        d = Path(cmd[cmd.index("-d") + 1])
        (d / "a-1-py3-none-any.whl").write_bytes(b"x" * 10)
        return _Proc(0)

    got = env.build_image(pins, tmp_path, run=run, build=lambda reqs, cache: ("tc-env:x", "sha256:" + "0" * 64))
    assert got["image"] == "tc-env:x" and (Path(dry["wheelhouse"]) / ".complete").read_text() == "a==1\nb==2\n"


def _runner(tests: list[dict], **extra):
    def run(image, *, workspace, mode, overlay_dir, repo_test_args, candidate_pythonpath, limits=None):
        assert workspace.is_dir() and mode.value == "in_process"
        return RawRun(0, False, {"nonce": "n", "status": "completed", "tests": tests, "pytest_exit_code": 0, **extra}, "", "", 1.0), "n"
    return run


def test_select_and_run_the_base_tests(built, tmp_path):
    w, _, _, _ = built
    base = w.out.parent / "snapshots" / "NP-01"
    sel = env.select_base_tests(base, changed=[("M", "fxpkg/mod.py"), ("M", "tests/test_mod.py"), ("A", "data/logo.bin")],
                                commented_path="fxpkg/mod.py")
    assert sel["subset"] == ["tests/test_mod.py"] and sel["by_import"] == {"tests/test_mod.py": ["fxpkg.mod"]}
    pkg = env.select_base_tests(base, changed=[("M", "fxpkg/__init__.py")], commented_path="fxpkg/__init__.py")
    assert pkg["subset"] == ["tests/test_mod.py", "tests/test_other.py"]  # importing fxpkg.x runs fxpkg/__init__.py
    fallback = env.select_base_tests(base, changed=[("M", "pyproject.toml")], commented_path="fxpkg/mod.py")
    assert fallback["subset"] == ["tests"] and "test directory" in fallback["rule"]
    args = env.repo_test_args(sel["subset"])
    assert env.run_base_tests(base, None, args=args, pythonpath="/work", dry_run=True)["repo_test_timeout_s"] == 600
    good = env.run_base_tests(base, "img", args=args, pythonpath="/work",
                              runner=_runner([{"nodeid": "tests/test_mod.py::test_add", "outcome": "passed"},
                                              {"nodeid": "tests/test_mod.py::test_skip", "outcome": "skipped"}]))
    assert good["passed"] and good["counts"] == {"passed": 1, "failed": 0, "error": 0, "skipped": 1}
    broken = env.run_base_tests(base, "img", args=args, pythonpath="/work", runner=_runner(
        [{"nodeid": "tests.test_mod", "outcome": "error", "longrepr": "collection failure"}], pytest_exit_code=2))
    assert broken["rejected"] and broken["reason"] == "base tests fail to collect"
    slow = env.run_base_tests(base, "img", args=args, pythonpath="/work", runner=_runner([], timed_out=True))
    assert slow["reason"] == "base tests do not run to completion within 10 minutes"
    empty = env.run_base_tests(base, "img", args=args, pythonpath="/work", runner=_runner([], pytest_exit_code=5))
    assert empty["reason"] == "base tests: the subset collects no test"


def test_the_test_directory_of_the_changed_package_can_have_another_name(tmp_path):
    """Found on real data: a repository whose tests live in ``selftests/`` (run with ``python -m unittest discover``) was
    rejected because "the changed package has no test directory": the fallback of §17.2 knew only tests, test and testing."""
    snap = tmp_path / "snap"
    for rel, text in {"pkg/__init__.py": "", "pkg/tools/fio.py": "X = 1\n", "selftests/__init__.py": "",
                      "selftests/test_core.py": "import pkg\n", "examples/testsuites/test_vm.py": "import pkg\n"}.items():
        (snap / rel).parent.mkdir(parents=True, exist_ok=True)
        (snap / rel).write_text(text)
    pick = lambda: env.select_base_tests(snap, changed=[("M", "pkg/tools/fio.py")], commented_path="pkg/tools/fio.py")  # noqa: E731
    sel = pick()
    assert sel["by_import"] == {} and sel["subset"] == ["selftests"] and not sel["empty"]
    assert sel["rule"] == "the test directory of the changed package (no test file imports a changed module)"
    (snap / "pkg" / "unittests").mkdir()
    (snap / "pkg" / "unittests" / "test_fio.py").write_text("import pkg\n")
    assert pick()["subset"] == ["selftests"]  # the root first, as for the conventional names
    (snap / "tests").mkdir()
    (snap / "tests" / "test_x.py").write_text("import pkg\n")
    assert pick()["subset"] == ["tests"]  # the conventional names come first
    shutil.rmtree(snap / "tests")
    shutil.rmtree(snap / "selftests")
    assert pick()["subset"] == ["pkg/unittests"]  # in the changed package
    shutil.rmtree(snap / "pkg" / "unittests")
    assert pick()["empty"]  # "testsuites" is not a test directory of the package


def test_b1_is_selected_at_the_addressing_commit(built, tmp_path):
    w, _, _, _ = built
    td = tmp_path / "NP-01"
    shutil.copytree(w.out / "NP-01", td)
    base = w.out.parent / "snapshots" / "NP-01"
    plan = env.build_b1(td, base, None, subset=["tests/test_mod.py"], pythonpath="/work", dry_run=True)
    assert plan["planned"] and plan["overlay"] == ["tests/test_mod.py"] and not (td / "verifiers").exists()
    got = env.build_b1(td, base, "img", subset=["tests/test_mod.py"], pythonpath="/work", runner=_runner(
        [{"nodeid": "tests/test_mod.py::test_add", "outcome": "passed"}, {"nodeid": "tests/test_mod.py::test_negative", "outcome": "passed"}]))
    assert got["available"] and got["n_checks"] == 2
    overlay = td / "verifiers" / "repo_tests" / "overlay" / "tests" / "test_mod.py"
    assert "test_negative" in overlay.read_text()  # the addressing commit's version of the test file
    m = load(td / "task.json", TaskManifest)
    assert m.verifiers == ["verifiers/repo_tests/spec.json"] and m.repo_test_args == ["-o", "addopts=", "tests/test_mod.py"]
    none = env.build_b1(td, base, "img", subset=["tests/test_mod.py"], pythonpath="/work",
                        runner=_runner([{"nodeid": "tests/test_mod.py::test_add", "outcome": "failed"}]))
    assert none["available"] is False and "B1 unavailable" in none["reason"]


def test_the_index_names_no_repository_path_of_b1s_overlay(built, tmp_path):
    """Found on real data: the index listed every file of a task by its path, and B1's overlay holds the repository's own
    test files under their repository paths. The overlay is one manifest hash and a count in the index."""
    w, _, _, _ = built
    td = tmp_path / "tasks" / "NP-01"
    shutil.copytree(w.out / "NP-01", td)
    base = w.out.parent / "snapshots" / "NP-01"
    env.build_b1(td, base, "img", subset=["tests/test_mod.py"], pythonpath="/work",
                 runner=_runner([{"nodeid": "tests/test_mod.py::test_add", "outcome": "passed"}]))
    overlay = td / "verifiers" / "repo_tests" / "overlay"
    assert (overlay / "tests" / "test_mod.py").is_file()
    out = tmp_path / "idx.json"
    row = npr.write_natural_index(tmp_path / "tasks", out)["tasks"][0]
    assert npr.OVERLAY == "verifiers/repo_tests/overlay/" and "test_mod" not in out.read_text()
    assert row["files"][npr.OVERLAY] == {"manifest_sha256": manifest_sha256(manifest(overlay)), "n_files": 1}
    assert not [k for k in row["files"] if k.startswith(npr.OVERLAY) and k != npr.OVERLAY]
    assert row["files"]["verifiers/repo_tests/spec.json"] == hashlib.sha256((td / "verifiers/repo_tests/spec.json").read_bytes()).hexdigest()


def _pypi(releases: dict[str, list[dict]]):
    return lambda name, version=None: {"releases": releases, "urls": []}


def test_fetch_sdist_takes_the_newest_release_before_the_base_date(tmp_path):
    data = b"sdist bytes"
    sha = hashlib.sha256(data).hexdigest()

    def f(ver: str, when: str, **kw) -> dict:
        return {"packagetype": "sdist", "filename": f"x-{ver}.tar.gz", "url": f"https://files.example.invalid/x-{ver}.tar.gz",
                "upload_time_iso_8601": when, "digests": {"sha256": sha}, **kw}

    releases = {"1.0": [f("1.0", "2024-01-01T00:00:00Z")], "1.1": [f("1.1", "2024-06-01T00:00:00Z")],
                "1.2": [f("1.2", "2025-06-01T00:00:00Z")], "1.1.1": [f("1.1.1", "2024-07-01T00:00:00Z", yanked=True)],
                "2.0rc1": [f("2.0rc1", "2024-08-01T00:00:00Z")]}
    got = env.fetch_sdist("x>=1.0", "2025-01-01T00:00:00Z", tmp_path, fetch_json=_pypi(releases),
                          download=lambda url, dest: dest.write_bytes(data))
    assert got["version"] == "1.1" and got["sha256"] == sha and (tmp_path / "x-1.1.tar.gz").is_file()
    assert env.fetch_sdist("x<1.0", None, tmp_path, fetch_json=_pypi(releases), download=lambda u, d: d.write_bytes(data)) is None
    bad = env.fetch_sdist("x", "2025-01-01T00:00:00Z", tmp_path / "b", fetch_json=_pypi(releases), download=lambda u, d: d.write_bytes(b"x"))
    assert bad is None and not (tmp_path / "b" / "x-1.1.tar.gz").exists()  # a digest mismatch is refused


def test_wheel_less_pure_python_requirements_are_built_in_the_sandbox(tmp_path):
    (tmp_path / "src").mkdir()
    sd = _sdist(tmp_path / "src" / "pure-1.0.tar.gz", {"pyproject.toml": "[build-system]\nrequires = [\"flit_core>=3\"]\n",
                                                        "pure/__init__.py": ""})
    data = sd.read_bytes()
    releases = {"1.0": [{"packagetype": "sdist", "filename": "pure-1.0.tar.gz", "url": "https://files.example.invalid/pure-1.0.tar.gz",
                         "upload_time_iso_8601": "2024-01-01T00:00:00Z", "digests": {"sha256": hashlib.sha256(data).hexdigest()}}]}
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        if "--report" in cmd:
            if "--find-links" not in cmd:
                return _Proc(1, "ERROR: No matching distribution found for pure")
            _report(Path(cmd[cmd.index("--report") + 1]), [("pure", "1.0", "pure-1.0-py3-none-any.whl")])
            return _Proc(0)
        if cmd[:2] == ["docker", "run"]:
            out = Path(next(a for a in cmd if a.endswith(":/out:rw")).split(":")[0])
            (out / "pure-1.0-py3-none-any.whl").write_bytes(b"wheel")
            return _Proc(0)
        return _Proc(0)  # the build backend's wheels

    plan = {"requirements": ["pure>=1"], "uploaded_prior_to": "2025-01-01T00:00:00Z", "path_only": []}
    got = env.resolve_with_sdists(plan, tmp_path / "w", run=run, fetch_json=lambda n, v=None: {"releases": releases, "urls": []},
                                  download=lambda url, dest: dest.write_bytes(data))
    assert got["pins"] == ["pure==1.0"] and got["sdist_builds"][0]["wheel"] == "pure-1.0-py3-none-any.whl"
    assert got["sdist_builds"][0]["build_requires"] == ["flit_core>=3"] and got["sdist_builds"][0]["sdist_sha256"]
    docker = next(c for c in seen if c[:2] == ["docker", "run"])
    assert docker[docker.index("--network") + 1] == "none"
    native = env.resolve_with_sdists(plan, tmp_path / "w2", run=lambda c, **k: _Proc(1, "No matching distribution found for pure"),
                                     fetch_json=lambda n, v=None: {"releases": {}, "urls": []})
    assert native["rejected"] and "no sdist released before the base date" in native["reason"]


def test_the_sdist_satisfies_every_declaration_of_a_wheel_less_requirement(tmp_path):
    """Found on real data: a closure declared ``k-api==2.15.0`` (requirements.txt) and ``k-api>=2.15.0,<3`` (setup.py);
    the sdist was chosen for the last declaration alone (2.16.0), so the resolver could never accept its wheel."""
    reqs = ["k-api==2.15.0", "k-api>=2.15.0,<3", "x>=1", "x<0.5; sys_platform == 'win32'", "kfp==2.15.0"]
    assert env.sdist_requirement("k-api", reqs) == "k-api<3,==2.15.0,>=2.15.0"
    assert env.sdist_requirement("x", reqs) == "x>=1"  # a declaration for another platform does not count
    assert env.sdist_requirement("k-server", reqs, "k-server==2.15.0") == "k-server==2.15.0"  # a transitive one, as pip reports it
    err = ("ERROR: Could not find a version that satisfies the requirement k-api==2.15.0 (from versions: none)\n"
           "ERROR: No matching distribution found for k-api==2.15.0\n")
    assert env.unsatisfied_requirements(err) == {"k-api": "k-api==2.15.0"} and env.wheel_less(err) == ["k-api"]
    (tmp_path / "src").mkdir()
    data = {v: _sdist(tmp_path / "src" / f"k-api-{v}.tar.gz", {"setup.py": "from setuptools import setup\nsetup(name='k-api')\n"}
                      ).read_bytes() for v in ("2.15.0", "2.16.0")}
    releases = {v: [{"packagetype": "sdist", "filename": f"k-api-{v}.tar.gz", "url": f"https://files.example.invalid/k-api-{v}.tar.gz",
                     "upload_time_iso_8601": when, "digests": {"sha256": hashlib.sha256(data[v]).hexdigest()}}]
                for v, when in (("2.15.0", "2024-01-01T00:00:00Z"), ("2.16.0", "2024-06-01T00:00:00Z"))}

    def run(cmd, **kw):
        if "--report" in cmd:
            links = Path(cmd[cmd.index("--find-links") + 1]) if "--find-links" in cmd else None
            if links is None or not (links / "k_api-2.15.0-py3-none-any.whl").is_file():
                return _Proc(1, err)
            _report(Path(cmd[cmd.index("--report") + 1]), [("k-api", "2.15.0", "k_api-2.15.0-py3-none-any.whl")])
            return _Proc(0)
        if cmd[:2] == ["docker", "run"]:
            version = cmd[-1].rsplit("-", 1)[1].removesuffix(".tar.gz")
            (_out_mount(cmd) / f"k_api-{version}-py3-none-any.whl").write_bytes(b"wheel")
        return _Proc(0)

    plan = {"requirements": ["k-api==2.15.0", "k-api>=2.15.0,<3"], "uploaded_prior_to": "2025-01-01T00:00:00Z", "path_only": []}
    got = env.resolve_with_sdists(plan, tmp_path / "w", run=run, fetch_json=lambda n, v=None: {"releases": releases, "urls": []},
                                  download=lambda url, dest: dest.write_bytes(data[url.rsplit("-", 1)[1].removesuffix(".tar.gz")]))
    assert "rejected" not in got and got["pins"] == ["k-api==2.15.0"]
    b = got["sdist_builds"][0]
    assert (b["version"], b["sdist"], b["requirement"]) == ("2.15.0", "k-api-2.15.0.tar.gz", "k-api<3,==2.15.0,>=2.15.0")


def test_every_round_of_sdist_builds_is_followed_by_a_resolution(tmp_path):
    """Found on real data: three sdist-only requirements, found one per round (the last a transitive one, which pip reports
    as ``name (from parent)``), were all built, but the third build was never resolved: max_rounds=3 ended the loop."""
    err = "ERROR: Could not find a version that satisfies the requirement u (from d) (from versions: none)\n"
    assert env.unsatisfied_requirements(err) == {"u": "u"}
    assert env.unsatisfied_requirements(err.replace("u (from d)", "u>=0.1 (from d)")) == {"u": "u>=0.1"}
    order = ["a", "d", "u"]
    (tmp_path / "src").mkdir()
    data = {n: _sdist(tmp_path / "src" / f"{n}-1.0.tar.gz", {"setup.py": "from setuptools import setup\n"}).read_bytes() for n in order}
    releases = {n: {"1.0": [{"packagetype": "sdist", "filename": f"{n}-1.0.tar.gz", "url": f"https://files.example.invalid/{n}-1.0.tar.gz",
                             "upload_time_iso_8601": "2024-01-01T00:00:00Z", "digests": {"sha256": hashlib.sha256(data[n]).hexdigest()}}]}
                for n in order}

    def run(cmd, **kw):
        if "--report" in cmd:
            links = Path(cmd[cmd.index("--find-links") + 1]) if "--find-links" in cmd else None
            have = {p.name.split("-")[0] for p in links.glob("*.whl")} if links else set()
            for n in order:
                if n not in have:
                    via = "" if n == "a" else " (from d)" if n == "u" else " (from a)"
                    return _Proc(1, f"ERROR: Could not find a version that satisfies the requirement {n}{via} (from versions: none)\n"
                                    f"ERROR: No matching distribution found for {n}{via}\n")
            _report(Path(cmd[cmd.index("--report") + 1]), [(n, "1.0", f"{n}-1.0-py3-none-any.whl") for n in order])
            return _Proc(0)
        if cmd[:2] == ["docker", "run"]:
            n = cmd[-1].removeprefix("/in/").split("-")[0]
            (_out_mount(cmd) / f"{n}-1.0-py3-none-any.whl").write_bytes(b"wheel")
        return _Proc(0)

    plan = {"requirements": ["a"], "uploaded_prior_to": "2025-01-01T00:00:00Z", "path_only": []}
    fetch = lambda n, v=None: {"releases": releases[n], "urls": []}  # noqa: E731
    dl = lambda url, dest: dest.write_bytes(data[url.rsplit("/", 1)[1].split("-")[0]])  # noqa: E731
    got = env.resolve_with_sdists(plan, tmp_path / "w", run=run, fetch_json=fetch, download=dl)
    assert "rejected" not in got and got["pins"] == ["a==1.0", "d==1.0", "u==1.0"]
    assert [b["name"] for b in got["sdist_builds"]] == order
    few = env.resolve_with_sdists(plan, tmp_path / "w2", run=run, fetch_json=fetch, download=dl, max_rounds=2)
    assert few["rejected"] and few["reason"] == "no resolvable closure after 2 rounds of sdist builds"
    assert [b["name"] for b in few["sdist_builds"]] == ["a", "d"] and few["wheel_less"] == ["u"]


def test_the_resolver_runs_on_a_python_312_interpreter(tmp_path, monkeypatch):
    """Found on real data: pip's ``--python-version 3.12`` changes only wheel tags and Requires-Python; markers were evaluated
    for the study's Python 3.13, so a closure lost ``pendulum; python_version < "3.13"`` and its base tests could not import
    it. pip's resolver runs on a Python 3.12 interpreter, which a real resolution checks first."""
    cmd = env.resolver_command(["a"], report="r.json", uploaded_prior_to=None)
    assert cmd[0] == env.RESOLVER_PYTHON and cmd[1:4] == ["-m", "pip", "install"]
    assert env.resolver_command(["a"], report="r.json", uploaded_prior_to=None, python="/x/python")[0] == "/x/python"

    def interp(version: str, helps: bool = True):
        def run(cmd, **kw):
            p = _Proc(0)
            p.stdout = f"{version} 26.3\n" if "-c" in cmd else ("  --uploaded-prior-to <datetime>" if helps else "")
            return p
        return run

    assert env.check_resolver_python("/x/python", run=interp("3.12.3")) == {
        "interpreter": "/x/python", "python": "3.12.3", "pip": "26.3", "markers": "evaluated for Python 3.12.3"}
    with pytest.raises(RuntimeError, match="is not Python 3.12"):
        env.check_resolver_python("/x/python", run=interp("3.13.5"))
    with pytest.raises(RuntimeError, match="no --uploaded-prior-to"):
        env.check_resolver_python("/x/python", run=interp("3.12.3", helps=False))
    # A real resolution (subprocess.run) refuses to run on an interpreter that is not there; a stub run skips the check.
    monkeypatch.setattr(env, "RESOLVER_PYTHON", str(tmp_path / "missing" / "python"))
    plan = {"requirements": ["a"], "uploaded_prior_to": None, "path_only": []}
    with pytest.raises(RuntimeError, match="no resolver interpreter"):
        env.resolve_closure(plan, tmp_path / "w")
    stub = env.resolve_closure(plan, tmp_path / "w2", run=lambda c, **k: _Proc(1, "ERROR: No matching distribution found for a"))
    assert stub["rejected"] and stub["commands"][0][0] == str(tmp_path / "missing" / "python") and stub["resolver"] is None


def test_a_resolver_that_runs_out_of_time_is_a_rejection(tmp_path):
    """Found on real data: pip's backtracking resolver ran for many minutes on a closure of 99 requirements; a timeout
    raised subprocess.TimeoutExpired out of the S10 step instead of rejecting the family."""
    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    plan = {"requirements": ["a", "b"], "uploaded_prior_to": None, "path_only": []}
    for got in (env.resolve_closure(plan, tmp_path / "w", run=slow), env.resolve_with_sdists(plan, tmp_path / "w2", run=slow)):
        assert got["rejected"] and got["timed_out"] is True and got["stage"] == "S10"
        assert got["reason"] == f"no resolvable closure: pip's resolver did not finish within {env.RESOLVER_TIMEOUT_S // 60} minutes"
    # The retry without a local path requirement is covered too.
    calls = []

    def first_fails_then_slow(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 1:
            return _Proc(1, "ERROR: No matching distribution found for sib")
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    plan2 = {"requirements": ["a", "sib"], "uploaded_prior_to": None, "path_only": ["sib"]}
    got = env.resolve_closure(plan2, tmp_path / "w3", run=first_fails_then_slow)
    assert got["timed_out"] and len(calls) == 2 and "sib" not in calls[1]


def test_a_killed_resolver_leaves_no_temporary_files(tmp_path):
    """Found on real data: pip's resolver, killed at the timeout after 30 minutes of backtracking, left 975,916 temporary
    directories (about 9 GB) in /tmp. Its TMPDIR is a directory of the work directory, removed after every run."""
    seen = []

    def slow(cmd, **kw):
        tmp = Path(kw["env"]["TMPDIR"])
        seen.append(tmp)
        assert tmp.is_dir() and tmp.is_relative_to(tmp_path)
        (tmp / "pip-unpack-x").mkdir()
        (tmp / "pip-unpack-x" / "a-1.0-py3-none-any.whl").write_bytes(b"w")
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    plan = {"requirements": ["a"], "uploaded_prior_to": None, "path_only": []}
    assert env.resolve_closure(plan, tmp_path / "w", run=slow)["timed_out"]
    assert seen == [tmp_path / "w" / "pip-tmp"] and not seen[0].exists()

    def ok(cmd, **kw):
        (Path(kw["env"]["TMPDIR"]) / "pip-metadata-y").mkdir()
        _report(Path(cmd[cmd.index("--report") + 1]), [("a", "1.0", "a-1.0-py3-none-any.whl")])
        return _Proc(0)

    got = env.resolve_closure(plan, tmp_path / "w2", run=ok, fetch_json=lambda n, v=None: {"urls": []})
    assert got["pins"] == ["a==1.0"] and not (tmp_path / "w2" / "pip-tmp").exists()


def test_a_real_s10_step_checks_and_records_the_resolver_whatever_run_wraps(built, tmp_path, monkeypatch):
    """Found on real data: a logging wrapper around ``run`` (not subprocess.run itself) skipped the resolver check, and the
    S10 records said nothing of the interpreter that evaluated the markers. A step that builds a real image checks it."""
    w, _, _, _ = built
    td = tmp_path / "tasks" / "NP-01"
    shutil.copytree(w.out / "NP-01", td)
    rec = {"interpreter": "/x/python", "python": "3.12.3", "pip": "26.3", "markers": "evaluated for Python 3.12.3"}
    checked = []
    monkeypatch.setattr(env, "check_resolver_python", lambda *a, **k: checked.append(1) or rec)
    monkeypatch.setattr(env, "build_image", lambda pins, cache, **kw: {"image": "tc-env:np01", "image_id": "sha256:" + "2" * 64,
                                                                        "wheelhouse": str(cache), "wheelhouse_bytes": 1})

    def run(cmd, **kw):  # a wrapper, as a logging driver passes
        if "--report" in cmd:
            _report(Path(cmd[cmd.index("--report") + 1]), [("pytest", "8.0", "pytest-8.0-py3-none-any.whl")])
        return _Proc(0)

    got = npr.run_s10_environment(td, w.out.parent / "snapshots", tmp_path / "work", tmp_path / "cache", dry_run=False, run=run,
                                  fetch_json=lambda n, v=None: {"urls": []},
                                  runner=_runner([{"nodeid": "tests/test_mod.py::test_add", "outcome": "passed"}]))
    assert got["outcome"] == "passed" and got["environment"]["resolver"] == rec and checked == [1]
    # A rejection at the environment step records it too.
    td2 = tmp_path / "tasks2" / "NP-01"
    shutil.copytree(w.out / "NP-01", td2)
    rej = npr.run_s10_environment(td2, w.out.parent / "snapshots", tmp_path / "work2", tmp_path / "cache", dry_run=False,
                                  run=lambda c, **k: _Proc(1, "ERROR: ResolutionTooDeep"), fetch_json=lambda n, v=None: {"urls": []})
    assert rej["outcome"] == "rejected" and rej["environment"]["resolver"] == rec


def test_the_s10_environment_step(built, tmp_path):
    w, _, _, _ = built
    td = tmp_path / "tasks" / "NP-01"
    shutil.copytree(w.out / "NP-01", td)
    snaps = w.out.parent / "snapshots"
    plan = npr.run_s10_environment(td, snaps, tmp_path / "work", tmp_path / "cache")
    assert plan["planned"] and plan["base_tests"]["repo_test_args"] == ["-o", "addopts=", "tests/test_mod.py"]
    assert plan["b1"]["planned"] and json.loads((td / "s10.json").read_text())["environment"] is None  # nothing changed

    def run(cmd, **kw):
        if "--report" in cmd:
            _report(Path(cmd[cmd.index("--report") + 1]), [("fx-requests", "2.1", "fx_requests-2.1-py3-none-any.whl"),
                                                           ("pytest", "8.0", "pytest-8.0-py3-none-any.whl")])
        elif "download" in cmd:
            d = Path(cmd[cmd.index("-d") + 1])
            (d / "fx_requests-2.1-py3-none-any.whl").write_bytes(b"w")
        return _Proc(0)

    sizes = lambda n, v=None: {"urls": [{"filename": f"{n.replace('-', '_')}-{v}-py3-none-any.whl", "size": 10}]}  # noqa: E731
    tests = [{"nodeid": "tests/test_mod.py::test_add", "outcome": "passed"}]
    got = npr.run_s10_environment(td, snaps, tmp_path / "work", tmp_path / "cache", dry_run=False, run=run, fetch_json=sizes,
                                  runner=_runner(tests), build=lambda reqs, cache: ("tc-env:np01", "sha256:" + "1" * 64))
    assert got["outcome"] == "passed" and got["environment"]["pins"] == ["fx-requests==2.1", "pytest==8.0"]
    assert got["base_test_run"]["counts"]["passed"] == 1 and got["b1"]["available"]
    m = load(td / "task.json", TaskManifest)
    assert m.env_requirements == ["fx-requests==2.1", "pytest==8.0"] and m.verifiers == ["verifiers/repo_tests/spec.json"]
    assert load(td / "snapshot.json", Snapshot).environment["image"] == "tc-env:np01"
    assert recorded_check(td, w.root).ok  # the environment step changes no input of the reconstruction record
    row = npr.write_natural_index(tmp_path / "tasks", tmp_path / "idx.json")["tasks"][0]
    assert row["s10"]["outcome"] == "passed" and row["s10"]["environment"] == "pinned" and row["s10"]["b1"] == "available"
    assert row["s11"] is False  # no family list given: the role is unknown, so it is not counted as S11 here
    # Base tests that fail to collect reject the task.
    td2 = tmp_path / "tasks2" / "NP-01"
    shutil.copytree(w.out / "NP-01", td2)
    broken = [{"nodeid": "tests.test_mod", "outcome": "error", "longrepr": "collection failure"}]
    rej = npr.run_s10_environment(td2, snaps, tmp_path / "work2", tmp_path / "cache", dry_run=False, run=run, fetch_json=sizes,
                                  runner=_runner(broken, pytest_exit_code=2), build=lambda reqs, cache: ("tc-env:np01", "sha256:" + "1" * 64))
    assert rej["outcome"] == "rejected" and rej["reason"] == "base tests fail to collect"
    assert load(td2 / "task.json", TaskManifest).status == "rejected" and (td2 / "rejection.json").is_file()


# --------------------------------------------------------------------------- generated material, re-check, index privacy

PLANTED_TEST = "test_fx_planted_generated_name.py"  # a generated test's file name (generators name files after the code)
BASE_TEST = "tests/test_mod.py"  # a repository test path, as propose_labels copies it into labels/base_tests_overlay/


def _tree(root: Path) -> dict[str, str]:
    """The sha256 of every file under ``root``, by its relative path."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*"))
            if p.is_file()}


def _layout(built, tmp_path: Path, tid: str = "NP-01") -> tuple[Path, Path, Path]:
    """A copy of one built task and its base snapshot in ``tmp_path/data/natural/{tasks,snapshots}``, as S10 left them."""
    w = built[0]
    out = tmp_path / "data" / "natural" / "tasks"
    shutil.copytree(w.out / tid, out / tid)
    shutil.copytree(w.out.parent / "snapshots" / tid, out.parent / "snapshots" / tid)
    return out, out / tid, out.parent / "snapshots" / tid


def _with_b1(built, td: Path) -> None:
    """B1 as the S10 environment step builds it (a stub runner; no Docker)."""
    env.build_b1(td, built[0].out.parent / "snapshots" / td.name, "img", subset=[BASE_TEST], pythonpath="/work",
                 runner=_runner([{"nodeid": "tests/test_mod.py::test_add", "outcome": "passed"}]))


def _generate(td: Path, *kinds: str) -> None:
    """Synthetic material made after S10 (no real contract, test or label)."""
    tid = td.name
    for kind in kinds:
        if kind == "contracts":
            (td / "contracts").mkdir(exist_ok=True)
            (td / "contracts" / "initial_only.json").write_text('{"synthetic": true}\n')
        elif kind == "verifier":
            (td / "verifiers" / "initial_plain" / "tests").mkdir(parents=True, exist_ok=True)
            (td / "verifiers" / "initial_plain" / "spec.json").write_text('{"synthetic": true}\n')
            (td / "verifiers" / "initial_plain" / "tests" / PLANTED_TEST).write_text("def test_x():\n    assert True\n")
        elif kind == "labels":
            overlay = td / "labels" / "base_tests_overlay" / BASE_TEST
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_text("def test_add():\n    pass\n")
            (td / "labels" / "proposed_labels.json").write_text('{"synthetic": true}\n')
        elif kind == "extra":
            (td / "verifiers_extra.json").write_text('{"verifiers": []}\n')
        elif kind == "candidate":
            shutil.copyfile(td / "candidates" / f"{tid}-noop-eval.json", td / "candidates" / f"{tid}-eval-alt-1.json")
        elif kind == "strata":
            (td / "strata").mkdir(exist_ok=True)
            (td / "strata" / "x.json").write_text("{}\n")
        elif kind == "label":
            p = td / "candidates" / f"{tid}-pre-review.json"
            c = json.loads(p.read_text())
            c["labels"].append({**c["labels"][0], "labeler": "d19:propose_labels", "labeler_kind": "proposed"})
            p.write_text(json.dumps(c, indent=2) + "\n")
        elif kind == "registered":
            m = json.loads((td / "task.json").read_text())
            m["contracts"] = {"initial_only": "contracts/initial_only.json"}
            (td / "task.json").write_text(json.dumps(m, indent=2) + "\n")
        elif kind == "frozen":  # P0: `tracecontract freeze $TD repo_tests` (freeze point F1)
            sp = td / "verifiers" / "repo_tests" / "spec.json"
            dump(freeze(load(sp, VerifierSpec), td), sp)
        elif kind == "b1-file":  # a file in B1's directory that build_b1 does not write
            (td / "verifiers" / "repo_tests" / "status.json").write_text('{"synthetic": true}\n')
        elif kind == "b1-record":  # a record set on B1's spec after S10 (build_b1 sets none)
            sp = td / "verifiers" / "repo_tests" / "spec.json"
            spec = json.loads(sp.read_text())
            spec["generation"] = {"synthetic": True}
            sp.write_text(json.dumps(spec, indent=2) + "\n")
        elif kind == "unlisted":  # outputs no rule names (a later work package's): S10's own names are listed instead
            (td / "review").mkdir(exist_ok=True)
            (td / "review" / "packet.json").write_text("{}\n")
            (td / "generation_records.json").write_text("{}\n")
        elif kind == "note":
            (td / "stale-note.txt").write_text("left by hand\n")
        elif kind == "unreadable":
            (td / "candidates" / f"{tid}-noop-dev.json").write_text("{")
        elif kind == "reviewed":  # a reviewer found the source eligible, and the task was accepted (S10 sets neither)
            for rel, key, value in (("provenance.json", "eligibility", "eligible"), ("task.json", "status", "accepted")):
                data = json.loads((td / rel).read_text())
                data[key] = value
                (td / rel).write_text(json.dumps(data, indent=2) + "\n")
        else:
            raise AssertionError(kind)


class _Untouchable:
    """A clone or dataset that must not be used: any attribute access fails the test."""

    def __getattr__(self, name: str):
        raise AssertionError(f"{name} was used, though the step should have been refused before any work")


@pytest.mark.parametrize("kinds, expect", [
    (("contracts",), ["contracts/"]),
    (("labels",), ["labels/"]),
    (("extra",), ["verifiers_extra.json"]),
    (("verifier",), ["verifiers/initial_plain/"]),
    (("candidate",), ["candidates/NP-01-eval-alt-1.json"]),
    (("strata",), ["strata/"]),
    (("label",), ["candidates/NP-01-pre-review.json: a label added or changed after S10"]),
    (("registered",), ["task.json: contracts"]),
    (("frozen",), ["verifiers/repo_tests/spec.json: B1 frozen (frozen, frozen_at, checks_sha256)"]),
    (("b1-file",), ["verifiers/repo_tests/status.json"]),
    (("b1-record",), ["verifiers/repo_tests/spec.json: changed after S10 (generation)"]),
    (("unlisted",), ["generation_records.json", "review/"]),
    (("note",), ["stale-note.txt"]),
    (("unreadable",), ["candidates/NP-01-noop-dev.json: unreadable"]),
    (("reviewed",), ["provenance.json: eligibility eligible", "task.json: status accepted"]),
])
def test_a_rerun_over_generated_material_is_refused_and_deletes_nothing(built, tmp_path, kinds, expect):
    _, fams, _, _ = built
    out, td, snap = _layout(built, tmp_path)
    _with_b1(built, td)
    assert npr.generated_material(td) == []  # B1 and the four S10 candidates are S10's own material
    _generate(td, *kinds)
    assert npr.generated_material(td) == expect
    before = _tree(tmp_path)
    fam = npr.find_family(fams, 9001)
    res = npr.compile_pr_task(fam, out, aidev=_Untouchable(), clone=_Untouchable())  # refused before anything is read
    assert res["outcome"] == "refused" and res["generated"] == expect and res["fetches"] == []
    assert "refused" in res["reason"] and "never replaced or deleted" in res["reason"] and "pr_recheck" in res["reason"]
    assert "stage" not in res  # a refusal is not a rejection
    assert _tree(tmp_path) == before  # neither the task directory nor its snapshot changed
    # The S10 environment step refuses it too, dry run or not, and changes nothing.
    for dry in (True, False):
        got = npr.run_s10_environment(td, snap.parent, tmp_path / "work", tmp_path / "cache", dry_run=dry, run=_Untouchable(),
                                      runner=_Untouchable(), build=_Untouchable())
        assert got["outcome"] == "refused" and got["generated"] == expect
    assert _tree(tmp_path) == before
    # A rejection record is never written over it either.
    with pytest.raises(npr.Refused):
        npr.write_rejection(td, fam, "S10", "synthetic reason")
    assert _tree(tmp_path) == before


def test_generated_material_found_late_is_refused_too(built, tmp_path, monkeypatch):
    """The check runs again just before the task directory would be replaced (a build) or deleted (a rejection), so material
    that appears while a family compiles is kept as well; only the compiler's own staging is removed."""
    _, fams, aidev, _ = built
    out, td, snap = _layout(built, tmp_path)
    _generate(td, "contracts", "verifier")
    before = _tree(tmp_path)
    real = npr.generated_material
    calls: list[Path] = []

    def late(task_dir):  # the material "appears" after the first check
        calls.append(Path(task_dir))
        return [] if len(calls) == 1 else real(task_dir)

    monkeypatch.setattr(npr, "generated_material", late)
    fam = npr.find_family(fams, 9001)
    built_now = npr.compile_pr_task(fam, out, aidev=aidev)  # a build that would replace the directory
    assert built_now["outcome"] == "refused" and built_now["generated"] == ["contracts/", "verifiers/initial_plain/"]
    assert _tree(tmp_path) == before and not list(out.parent.rglob(".*.partial"))
    calls.clear()
    rejected_now = npr.compile_pr_task(dataclasses.replace(fam, path="fxpkg/nowhere.py"), out, aidev=aidev)  # a rejection
    assert rejected_now["outcome"] == "refused" and rejected_now["rejection_found"] == {
        "stage": "S10", "reason": "the commented file is not a file at the reviewed commit"}
    assert "details" not in rejected_now and "stage" not in rejected_now
    assert _tree(tmp_path) == before and (snap / "pyproject.toml").is_file()  # the snapshot is kept


def test_a_rerun_over_an_s10_only_directory_rebuilds_as_before(built, tmp_path):
    _, fams, aidev, _ = built
    out, td, snap = _layout(built, tmp_path)
    _with_b1(built, td)
    assert npr.generated_material(td) == []  # S10's own files only, an unfrozen B1 included
    old = {p: (td / p).read_bytes() for p in ("snapshot.json", "provenance.json", RECORD)}
    fam = npr.find_family(fams, 9001)
    res = npr.compile_pr_task(fam, out, aidev=aidev)
    assert res["outcome"] == "built" and res["reconstruction"] == "passed"
    assert sorted(p.name for p in td.iterdir()) == ["candidates", "provenance.json", RECORD, "s10.json", "session.json",
                                                    "snapshot.json", "task.json"]  # replaced whole: B1 is gone (S10 rebuilds it)
    assert (td / "snapshot.json").read_bytes() == old["snapshot.json"] and (td / RECORD).read_bytes() == old[RECORD]
    assert json.loads((td / "provenance.json").read_text())["natural_pr"] == json.loads(old["provenance.json"])["natural_pr"]
    assert manifest_sha256(manifest(snap)) == load(td / "snapshot.json", Snapshot).file_manifest_sha256
    assert res["session"]["sanitize_natural"]["sanitizer"] == "sanitize-natural:v1"
    # A rejection over an S10-only directory still leaves only the rejection record and no snapshot.
    rej = npr.compile_pr_task(dataclasses.replace(fam, path="fxpkg/nowhere.py"), out, aidev=aidev)
    assert rej["outcome"] == "rejected" and [p.name for p in td.iterdir()] == ["rejection.json"] and not snap.exists()


def _recheck(built, td: Path, snap: Path, fam=None, **kw):
    _, fams, aidev, _ = built
    return npr.pr_recheck(td, fam or npr.find_family(fams, 9001), aidev=aidev, snapshot_root=snap.parent, **kw)


def test_pr_recheck_rewrites_only_the_reconstruction_record(built, tmp_path):
    _, td, snap = _layout(built, tmp_path)
    _with_b1(built, td)
    _generate(td, "contracts", "verifier", "labels", "candidate")  # a task in the middle of generation
    old = json.loads((td / RECORD).read_text())
    old_sha = hashlib.sha256((td / RECORD).read_bytes()).hexdigest()
    before = _tree(tmp_path)
    res = _recheck(built, td, snap)
    assert res["outcome"] == "rechecked" and res["status"] == "passed" and res["previous_status"] == "passed"
    assert res["inputs_changed"] == [] and set(res["checks"].values()) == {"passed"}
    after = _tree(tmp_path)
    assert {k for k in before if before[k] != after.get(k)} == {f"data/natural/tasks/NP-01/{RECORD}"}
    assert set(after) == set(before)  # no file added (the record is replaced in one step) and none removed
    new = json.loads((td / RECORD).read_text())
    assert new["recheck"]["previous_sha256"] == old_sha and new["recheck"]["approximations_as_recorded"] is True
    assert new["inputs"] == old["inputs"] and (new["fidelity"], new["approximations"]) == (old["fidelity"], old["approximations"])
    assert [(c["check_id"], c["status"], c["reason"]) for c in new["checks"]] == [
        (c["check_id"], c["status"], c["reason"]) for c in old["checks"]]  # the same checks, re-run, as at build
    e = {i["candidate"]: i for i in new["checks"][4]["items"]}
    assert e["reference"]["equals_recompiled_patch"] and e["pre-review"]["equals_recompiled_patch"]
    assert e["reference"]["extra_changes"] == e["pre-review"]["extra_changes"] == []
    assert new["checks"][3]["items"][0]["manifest_equals_snapshot_record"] is True
    assert new["recheck"]["session_rebuilt"] is True  # the session was rebuilt from the thread, byte for byte
    assert recorded_check(td, built[0].root).ok


def test_pr_recheck_records_the_current_files_and_fails_what_no_longer_holds(built, tmp_path):
    w = built[0]
    _, td, snap = _layout(built, tmp_path)
    # A stale record becomes current again when the changed file still reproduces the PR's state: here the reference
    # patch with its file sections in the other order (another text, the same tree). The record names the input that
    # changed and that the stored patch is not the one the compiler makes now; the session is rebuilt and is the same.
    p = td / "candidates" / "NP-01-reference.json"
    c = json.loads(p.read_text())
    c["patch"] = "".join(s.text for s in reversed(split_sections(c["patch"])))
    c["patch_sha256"] = hashlib.sha256(c["patch"].encode()).hexdigest()
    p.write_text(json.dumps(c, indent=2) + "\n")
    assert not recorded_check(td, w.root).ok
    res = _recheck(built, td, snap)
    assert res["status"] == "passed" and res["inputs_changed"] == ["reference_patch_sha256"] and recorded_check(td, w.root).ok
    rec = json.loads((td / RECORD).read_text())
    e = {i["candidate"]: i for i in rec["checks"][4]["items"]}
    assert e["reference"]["equals_recompiled_patch"] is False and e["reference"]["extra_changes"] == []
    assert rec["recheck"]["session_rebuilt"] is True
    # A changed file of the base snapshot fails check d; the record is current and failed, so the gate refuses the task.
    f = snap / "fxpkg" / "mod.py"
    f.write_text(f.read_text() + "# changed\n")
    res = _recheck(built, td, snap)
    assert res["status"] == "failed" and res["checks"]["d_snapshot_equals_base_tree"] == "failed"
    d = json.loads((td / RECORD).read_text())["checks"][3]
    assert "1 differ from their blob" in d["reason"] and d["items"][0]["manifest_equals_snapshot_record"] is False
    rc = recorded_check(td, w.root)
    assert rc.failed and [r for r in task_gate(td, w.root).refusals if r.startswith("reconstruction")]
    shutil.rmtree(snap)
    shutil.copytree(w.out.parent / "snapshots" / "NP-01", snap)
    # A pre-review patch that no longer reproduces its commit (here: the reference's patch) fails check e.
    p = td / "candidates" / "NP-01-pre-review.json"
    c = json.loads(p.read_text())
    c["patch"] = json.loads((td / "candidates" / "NP-01-reference.json").read_text())["patch"]
    c["patch_sha256"] = hashlib.sha256(c["patch"].encode()).hexdigest()
    p.write_text(json.dumps(c, indent=2) + "\n")
    res = _recheck(built, td, snap)
    assert res["status"] == "failed" and res["checks"]["e_candidates_reproduce_commits"] == "failed"
    assert res["inputs_changed"] == ["pre_review_patch_sha256"]
    e = {i["candidate"]: i for i in json.loads((td / RECORD).read_text())["checks"][4]["items"]}
    assert e["pre-review"]["status"] == "failed" and e["pre-review"]["equals_recompiled_patch"] is False
    assert e["pre-review"]["mismatched"] == ["fxpkg/mod.py"] and e["pre-review"]["extra_changes"] == ["tests/test_mod.py"]
    assert e["reference"]["status"] == "passed"


def test_pr_recheck_fails_a_git_rule_that_no_longer_holds(built, tmp_path):
    w, fams, _, _ = built
    _, td, snap = _layout(built, tmp_path)
    fam = npr.find_family(fams, 9001)
    # The addressing commit no longer descends from the reviewed one: check a fails, the later checks do not run.
    res = _recheck(built, td, snap, dataclasses.replace(fam, addressing_commit=w.shas["a1"]))
    assert res["status"] == "failed" and res["checks"] == {
        "a_commits_reachable": "failed", "b_base_rule": "not_checked", "c_merge_rule": "not_checked",
        "d_snapshot_equals_base_tree": "not_checked", "e_candidates_reproduce_commits": "not_checked",
        "f_no_stale_copies": "not_checked"}
    assert recorded_check(td, w.root).failed
    # Nothing was recomputed beyond check a: the approximations (copied from snapshot.json) and the session are not
    # said to be checked.
    rc = json.loads((td / RECORD).read_text())["recheck"]
    assert rc["approximations_as_recorded"] is None and rc["session_rebuilt"] is None
    # The rules hold but give another reviewed commit than the task records.
    res = _recheck(built, td, snap, dataclasses.replace(fam, reviewed_commit=w.shas["a1"]))
    rec = json.loads((td / RECORD).read_text())
    assert res["status"] == "failed" and rec["checks"][0]["reason"] == (
        "the PR's commits now give another reviewed commit than the task records")
    assert rec["recheck"]["approximations_as_recorded"] is None and rec["recheck"]["session_rebuilt"] is None
    # Back to the family's own commits: passed again.
    assert _recheck(built, td, snap)["status"] == "passed" and recorded_check(td, w.root).ok


def test_pr_recheck_writes_nothing_when_it_cannot_check(built, tmp_path):
    w, fams, aidev, _ = built
    _, td, snap = _layout(built, tmp_path)
    before = _tree(tmp_path)
    other = npr.find_family(fams, 9002)  # another family's PR
    for res in (_recheck(built, td, snap, other),
                npr.pr_recheck(td, npr.find_family(fams, 9001), aidev=aidev, snapshot_root=tmp_path / "nowhere"),
                _recheck(built, td, snap, dataclasses.replace(npr.find_family(fams, 9001), bare_clone=w.root / "missing.git")),
                npr.pr_recheck(tmp_path / "not-a-task", aidev=aidev)):
        assert res["outcome"] == "not rechecked" and res["reason"], res
    assert _tree(tmp_path) == before


# Synthetic sections appended to a stored candidate patch (paths of the fixture's repository 101).
PLANTED_FILE = ("diff --git a/fxpkg/planted.py b/fxpkg/planted.py\nnew file mode 100644\n--- /dev/null\n+++ b/fxpkg/planted.py\n"
                "@@ -0,0 +1 @@\n+X = 1\n")
DELETED_FILE = ("diff --git a/fxpkg/__init__.py b/fxpkg/__init__.py\ndeleted file mode 100644\n--- a/fxpkg/__init__.py\n"
                "+++ /dev/null\n@@ -1 +0,0 @@\n-from .mod import add\n")
EDITED_FILE = ("diff --git a/fxpkg/other.py b/fxpkg/other.py\n--- a/fxpkg/other.py\n+++ b/fxpkg/other.py\n@@ -1,2 +1,2 @@\n"
               " def unrelated():\n-    return 1\n+    return 5\n")


@pytest.mark.parametrize("cand, section, path", [
    ("reference", PLANTED_FILE, "fxpkg/planted.py"),  # probe A: a file the addressing commit does not add
    ("pre-review", DELETED_FILE, "fxpkg/__init__.py"),  # probe A': a file the reviewed commit does not delete
    ("reference", EDITED_FILE, "fxpkg/other.py"),  # a file the addressing commit does not change
])
def test_pr_recheck_fails_a_stored_patch_that_changes_files_its_commit_does_not(built, tmp_path, cand, section, path):
    """Check e compares the whole tree the stored patch makes with the commit's: every file the commit changes must be the
    commit's, and no other file may differ from the base. Only the commit's own files were compared before, so a stored
    patch that also added, deleted or edited another file was certified."""
    w = built[0]
    _, td, snap = _layout(built, tmp_path)
    p = td / "candidates" / f"NP-01-{cand}.json"
    c = json.loads(p.read_text())
    c["patch"] += section
    c["patch_sha256"] = hashlib.sha256(c["patch"].encode()).hexdigest()
    p.write_text(json.dumps(c, indent=2) + "\n")
    assert not recorded_check(td, w.root).ok  # stale first
    res = _recheck(built, td, snap)
    assert res["outcome"] == "rechecked" and res["status"] == "failed"
    assert res["checks"]["e_candidates_reproduce_commits"] == "failed"
    rec = json.loads((td / RECORD).read_text())
    e = {i["candidate"]: i for i in rec["checks"][4]["items"]}
    assert e[cand]["status"] == "failed" and e[cand]["mismatched"] == [] and e[cand]["extra_changes"] == [path]
    assert e[cand]["equals_recompiled_patch"] is False and "the patch also changes 1 other file" in e[cand]["reason"]
    other = e["pre-review" if cand == "reference" else "reference"]
    assert other["status"] == "passed" and other["extra_changes"] == []
    assert recorded_check(td, w.root).failed  # current and failed: the gate refuses the task
    assert [r for r in task_gate(td, w.root).refusals if r.startswith("reconstruction")]


def test_pr_recheck_never_certifies_a_session_the_compiler_does_not_make(built, tmp_path):
    """Probe B: a session.json changed after the build is not made current by a re-check. The session is rebuilt from the
    thread in memory and must equal the file byte for byte; otherwise nothing is written and the record stays stale, so
    the gate keeps failing the task. Before, the re-check copied the new file's hash into a passing record."""
    w = built[0]
    _, td, snap = _layout(built, tmp_path)
    path = td / "session.json"
    raw = path.read_bytes()
    sess = json.loads(raw)
    (corr,) = [e for e in sess["events"] if e["event_id"] == sess["metadata"]["events"]["correction"]]
    corr["text"] = "A synthetic correction that no reviewer wrote."
    for changed in ((json.dumps(sess, indent=2) + "\n").encode(), raw + b"\n"):  # the correction replaced; a byte appended
        path.write_bytes(changed)
        record = (td / RECORD).read_bytes()
        assert not recorded_check(td, w.root).ok
        res = _recheck(built, td, snap)
        assert res["outcome"] == "not rechecked" and "session.json is not the session" in res["reason"]
        assert res["session"] == {"file_sha256": hashlib.sha256(changed).hexdigest(),
                                  "rebuilt_sha256": hashlib.sha256(raw).hexdigest()}
        assert (td / RECORD).read_bytes() == record and not recorded_check(td, w.root).ok  # left stale
        assert [r for r in task_gate(td, w.root).reasons if r.startswith("reconstruction")]
    path.write_bytes(raw)  # the compiler's own session again
    res = _recheck(built, td, snap)
    assert res["status"] == "passed" and res["inputs_changed"] == [] and recorded_check(td, w.root).ok


def test_the_s10_environment_step_refuses_material_that_appears_while_it_runs(built, tmp_path):
    """Probe F: the check runs again before every write of the step, and between B1's grading run and B1's records, so
    material made while the resolver, the image build or a grading run is under way is kept: the step is refused there and
    writes nothing more. Before, the step ended ``passed`` and its stale copy of task.json dropped the registration."""
    w = built[0]
    snaps = w.out.parent / "snapshots"
    def sizes(name, version=None):
        return {"urls": [{"filename": f"{name}-{version}-py3-none-any.whl", "size": 10}]}

    def stub_build(reqs, cache):
        return "tc-env:np01", "sha256:" + "1" * 64

    passing = _runner([{"nodeid": "tests/test_mod.py::test_add", "outcome": "passed"}])
    for when in ("resolver", "resolver that fails", "base tests", "B1 grading"):
        td = tmp_path / when.replace(" ", "-") / "tasks" / "NP-01"
        shutil.copytree(w.out / "NP-01", td)
        before = _tree(td)
        grading: list[int] = []

        def run(cmd, td=td, when=when, **kw):
            if "--report" in cmd:
                if when.startswith("resolver"):
                    _generate(td, "contracts", "registered")  # registered while the resolver runs
                    if when == "resolver that fails":
                        return _Proc(1, "ERROR: ResolutionTooDeep")
                _report(Path(cmd[cmd.index("--report") + 1]), [("pytest", "8.0", "pytest-8.0-py3-none-any.whl")])
            return _Proc(0)

        def runner(image, td=td, when=when, grading=grading, **kw):
            grading.append(1)
            if (when, len(grading)) in (("base tests", 1), ("B1 grading", 2)):
                _generate(td, "contracts", "registered")
            return passing(image, **kw)

        got = npr.run_s10_environment(td, snaps, tmp_path / "work" / when.replace(" ", "-"), tmp_path / "cache", dry_run=False,
                                      run=run, fetch_json=sizes, runner=runner, build=stub_build)
        assert got["outcome"] == "refused" and got["generated"] == ["contracts/", "task.json: contracts"], (when, got)
        m = load(td / "task.json", TaskManifest)
        assert m.contracts == {"initial_only": "contracts/initial_only.json"} and m.status == "pending_review", when
        assert not (td / "rejection.json").exists() and not (td / "verifiers" / "repo_tests" / "spec.json").exists()
        s10 = json.loads((td / "s10.json").read_text())
        assert s10["outcome"] == "built" and s10["base_test_run"] is None and s10["b1"] is None, when
        if when.startswith("resolver"):  # refused before the environment record: nothing of the task was rewritten
            after = _tree(td)
            assert {k for k in before if before[k] != after.get(k)} == {"task.json"}, when  # the registration only
            assert set(after) - set(before) == {"contracts/initial_only.json"}, when
        else:  # the environment record was written before the material appeared; the pins survive with the registration
            assert s10["environment"]["pins"] == ["pytest==8.0"] and m.env_requirements == ["pytest==8.0"], when


def test_the_index_summarises_generated_tests_and_base_test_copies(built, tmp_path):
    out, td, _ = _layout(built, tmp_path)
    _with_b1(built, td)
    _generate(td, "contracts", "verifier", "labels", "candidate", "extra")
    path = tmp_path / "idx.json"
    row = npr.write_natural_index(out, path)["tasks"][0]
    text = path.read_text()
    assert PLANTED_TEST not in text and "test_mod" not in text and BASE_TEST not in text and "fxpkg" not in text
    files = row["files"]
    for key, d in (("verifiers/initial_plain/tests/", td / "verifiers/initial_plain/tests"),
                   ("labels/base_tests_overlay/", td / "labels/base_tests_overlay"), (npr.OVERLAY, td / npr.OVERLAY)):
        assert files[key] == {"manifest_sha256": manifest_sha256(manifest(d)), "n_files": 1}
    for key in ("contracts/initial_only.json", "labels/proposed_labels.json", "candidates/NP-01-eval-alt-1.json",
                "verifiers/initial_plain/spec.json", "verifiers_extra.json", "verifiers/repo_tests/spec.json"):
        assert files[key] == hashlib.sha256((td / key).read_bytes()).hexdigest()
    assert not [k for k in files if "/tests/" in k and not k.endswith("/tests/")]
    # A changed generated test changes the row, though its name is not in it.
    (td / "verifiers/initial_plain/tests" / PLANTED_TEST).write_text("def test_x():\n    assert 1\n")
    again = npr.write_natural_index(out, tmp_path / "idx2.json")["tasks"][0]["files"]
    assert again["verifiers/initial_plain/tests/"] != files["verifiers/initial_plain/tests/"]
    assert {k: v for k, v in again.items() if k != "verifiers/initial_plain/tests/"} == {
        k: v for k, v in files.items() if k != "verifiers/initial_plain/tests/"}
    assert npr.summary_dir("notes/x/y.md") == "notes/" and npr.summary_dir("candidates/x/y.json") == "candidates/x/"
    assert npr.summary_dir("task.json") is None and npr.summary_dir("verifiers/v/status.json") is None


def test_the_index_rows_of_s10_only_tasks_keep_their_file_hashes(built, tmp_path):
    """The rows of tasks whose files did not change are as before, apart from the new fields: every file by its path, and
    only B1's overlay summarised."""
    _, td, _ = _layout(built, tmp_path)
    _with_b1(built, td)
    legacy: dict = {}
    overlay = []
    for p in sorted(td.rglob("*")):
        if p.is_file():
            rel, digest = p.relative_to(td).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()
            if rel.startswith(npr.OVERLAY):
                overlay.append((rel[len(npr.OVERLAY):], digest))
            else:
                legacy[rel] = digest
    legacy[npr.OVERLAY] = {"manifest_sha256": manifest_sha256(overlay), "n_files": len(overlay)}
    assert npr.file_hashes(td) == legacy


def test_the_index_header_rows_samples_and_sanitizer_counts(built, tmp_path):
    w, fams, _, _ = built
    out, td, _ = _layout(built, tmp_path)
    # Plant what the sanitiser replaces: a handle in the issue and an IP address in a commit message (both built at run
    # time). The fixture's pseudonymised session already has handle-like role labels, which the sanitiser counts too.
    from natural_pr_world import AT

    session_path = td / "session.json"
    baseline = npr.sanitizer_counts(load(session_path, Session))
    handle, ip = AT + "fx-planted", ".".join(str(n) for n in (203, 0, 113, 7))
    sess = json.loads(session_path.read_text())
    for e in sess["events"]:
        if e["event_id"].endswith("/issue"):
            e["text"] += " cc " + handle
        if "/commit/" in e["event_id"]:
            e["text"] += " see " + ip
            break
    sess["repo_url"] = sess["repo_url"].replace("https://github.com/", f"https://{ip}/")  # an IP in the masked URL too
    session_path.write_text(json.dumps(sess, indent=2) + "\n")
    shutil.copytree(w.out / "NP-07", out / "NP-26")  # a rejection-only directory standing in for an extension family
    raw = session_path.read_bytes()
    idx = npr.write_natural_index(out, tmp_path / "idx.json", families=fams)
    assert session_path.read_bytes() == raw  # the session file is never rewritten
    rows = {r["task_id"]: r for r in idx["tasks"]}
    got = rows["NP-01"]["sanitize_natural"]
    assert got["sanitizer"] == "sanitize-natural:v1" and "commits" not in baseline["where"]
    assert got["counts"] == {**baseline["counts"], "handles": baseline["counts"].get("handles", 0) + 1, "ips": 2}
    assert got["where"] == {**baseline["where"], "commits": {"ips": 1}, "repo_url": {"ips": 1},
                            "issue": {"handles": baseline["where"].get("issue", {}).get("handles", 0) + 1}}
    # The pass itself (sanitize_session) is counted apart: it renders a commit event's text from its tool input, so the
    # address in the commit message is not among its counts (found on real data: a handle in one family's commit message).
    passed = sanitize_session(load(session_path, Session))[1]
    assert got["pass"] == passed == {**baseline["pass"], "handles": baseline["pass"].get("handles", 0) + 1, "ips": 1}
    note = idx["fields"]["sanitize_natural"]
    assert all(f"{part}," in note or f"{part};" in note or f"{part})" in note for part in got["where"])  # each part is named
    assert "sanitize_session" in note and "pass" in note
    assert [r["task_id"] for r in idx["tasks"] if "sanitize_natural" in r] == ["NP-01"]  # only built tasks have a session
    assert {t: r["sample"] for t, r in rows.items()} == {**{f.task_id: "first" for f in fams}, "NP-26": "extension"}
    assert (npr.sample_of("NP-25"), npr.sample_of("NP-26"), npr.sample_of("CS-01")) == ("first", "extension", None)
    assert idx["s11_by_sample"] == {"first": 0, "extension": 0} and idx["counts"]["s11"] == 0
    assert idx["decision_log"] == [f"D{n}" for n in range(47, 61)] and "§19" in idx["protocol"]
    src = idx["source"]
    assert (src["licence"], src["url"], src["changes"]) == (
        "CC-BY-4.0", f"https://huggingface.co/datasets/{npr.AIDEV_DATASET}", "ids, SHAs, counts and hashes extracted; no text")
    assert "CC BY 4.0" in src["attribution"] and src["revision"] == npr.AIDEV_REVISION
    assert "third_party_downloads.json" in idx["privacy"] and "public GitHub ids" in idx["privacy"]
    text = (tmp_path / "idx.json").read_text().lower()
    assert handle not in text and ip not in text and AT not in text and "github.com" not in text
    assert not [x for x in forbidden() if x.lower() in text]
