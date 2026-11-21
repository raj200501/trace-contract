"""The natural PR-review task compiler and its S10 steps (natural_pr.py, natural_env.py; protocol §15.6, §16, §17).

* ``compile_pr_task`` builds task.json, provenance.json, the base snapshot, the candidates (reference, pre-review, no-op),
  the PR reconstruction record that the acceptance gate accepts, the pseudonymised session and the S10 record; or it
  rejects with a stage and a reason (a merge that touches the commented file, an unlicensed or non-permissive LICENSE,
  unreachable SHAs, an empty base-test subset), and never raises on a data problem; ``--plan-only`` writes nothing;
* the merge rule makes a task approximate when no merge touches the commented file;
* the committed index holds ids, SHAs, licences, file hashes and S10 outcomes, no text, and the rejection ledger gets
  one S10 row per rejected family (scripts/build_manifests.py);
* the S10 environment and base-test functions plan their commands without Docker or network, and with stubs they
  reject an environment over the cap, an unresolvable closure and base tests that fail to collect.

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
from tracecontract.patches import apply_patch, filter_patch
from tracecontract.reconstruction import RECORD, recorded_check
from tracecontract.sandbox.docker_runner import RawRun, _req_hash
from tracecontract.schemas import (
    Candidate, CandidateOrigin, Eligibility, LabelerKind, Population, ProvenanceRecord, Session, Snapshot, Split, TaskManifest,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import load

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
    gate = task_gate(td, w.root)
    assert not gate.refusals and gate.reasons == ["provenance: eligibility is 'pending_review'; a reviewer must find the source "
                                                  "eligible", "contract: the task has no reference contract"]
    rec = json.loads((td / RECORD).read_text())
    assert rec["method"] == npr.PR_METHOD and [c["status"] for c in rec["checks"]] == ["passed"] * 6
    # A changed session file makes the record stale; a current failed record refuses the task.
    (td / "session.json").write_text((td / "session.json").read_text() + "\n")
    stale = recorded_check(td, w.root)
    assert not stale.ok and not stale.failed and "session_sha256" in stale.problems[0]
    rec["inputs"]["session_sha256"] = npr.pr_current_inputs(td)["session_sha256"]
    rec.update(status="failed", passed=False)
    (td / RECORD).write_text(json.dumps(rec))
    assert recorded_check(td, w.root).failed and task_gate(td, w.root).refusals


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
