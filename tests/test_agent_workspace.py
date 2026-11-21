"""Isolated agent workspaces hold only what their role may see (scripts/make_agent_workspace.py, A6)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from tracecontract.schemas import (
    Candidate, CandidateOrigin, ContractVariant, EvidenceSpan, Fidelity, Population, Requirement, RequirementKind,
    RequirementStatus, Snapshot, SnapshotSource, Split, TaskContract, TaskManifest, sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump

R = Path(__file__).resolve().parents[1]
SID = "FX-02-session"
U1 = "Please fix add in calc.py MARK-U1."
U2 = "Actually, keep add(0, 0) == 0 as well MARK-U2."
# Markers planted in the study material that no workspace may hold.
FORBIDDEN_MARKERS = {"MARK-HELDOUT", "MARK-DEV", "MARK-VERIFIER", "MARK-LABEL", "MARK-RESULT", "MARK-DOC", "MARK-SCENARIO",
                     "MARK-PAPER", "MARK-SEALED", "MARK-REFTEST", "MARK-TASK"}
# Names of study directories; a workspace has none, apart from the base snapshot's own docs/.
FORBIDDEN_NAMES = {"tasks", "verifiers", "candidates", "labels", "results", "data", "paper", "sealed", ".tc_sealed"}


def _load():
    import sys

    spec = importlib.util.spec_from_file_location("make_agent_workspace", R / "scripts" / "make_agent_workspace.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look their module up there
    spec.loader.exec_module(mod)
    return mod


MAW = _load()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _w(path: Path, text: str) -> Path:
    _write(path, text)
    return path


def _patch(path: str, old: str, new: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n"


def _req(rid: str, kind: RequirementKind, statement: str, event: str, quote: str, text: str) -> Requirement:
    start = text.index(quote)
    return Requirement(req_id=rid, statement=statement, kind=kind, status=RequirementStatus.explicit, introduced_at=event,
                       evidence=[EvidenceSpan(event_id=event, start=start, end=start + len(quote), quote=quote)],
                       observable=statement, proposer="fixture")


def _study(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """A miniature study repository: task FX-02, its base snapshot and session, and planted forbidden material."""
    repo, sealed = tmp_path / "study", tmp_path / "sealed"
    snap = repo / "snapshots" / "FX-02"
    for rel, text in {"calc.py": "def add(a, b): return a - b\n", "tests/test_calc.py": "def test_add(): pass\n",
                      "docs/index.md": "# calc\n", "README.md": "calc\n"}.items():
        _write(snap / rel, text)
    rows = [{"type": "user", "uuid": "u1", "sessionId": SID, "timestamp": "2026-01-01T00:00:00Z", "message": {"role": "user", "content": U1}},
            {"type": "assistant", "uuid": "a1", "sessionId": SID, "timestamp": "2026-01-01T00:00:01Z",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}},
            {"type": "user", "uuid": "u2", "sessionId": SID, "timestamp": "2026-01-01T00:00:02Z", "message": {"role": "user", "content": U2}}]
    _write(repo / "data" / "fixtures" / "transcripts" / "FX-02.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
    td = repo / "tasks" / "FX-02"
    e1, e2 = f"{SID}/L000001.00", f"{SID}/L000003.00"
    contracts = {}
    for variant in ContractVariant:
        reqs = [_req("R1", RequirementKind.change, f"add returns a + b (MARK-CONTRACT-{variant.value})", e1, "fix add", U1)]
        if variant != ContractVariant.initial_only:
            reqs.append(_req("R2", RequirementKind.invariant, f"add(0, 0) == 0 (MARK-CONTRACT-{variant.value})", e2, "keep", U2))
        dump(TaskContract(contract_id=f"FX-02-{variant.value}", task_id="FX-02", session_id=SID, variant=variant,
                          requirements=reqs, created_by="fixture", created_at="t"), td / "contracts" / f"{variant.value}.json")
        contracts[variant.value] = f"contracts/{variant.value}.json"
    cands = {"FX-02-reference": (CandidateOrigin.reference, Split.eval,
                                 _patch("calc.py", "def add(a, b): return a - b", "def add(a, b): return a + b  # MARK-REFERENCE")
                                 + _patch("tests/test_calc.py", "def test_add(): pass", "def test_add(): assert 1  # MARK-REFTEST")),
             "FX-02-pre-correction": (CandidateOrigin.observed_pre_correction, Split.eval, _patch("calc.py", "x", "y  # MARK-HELDOUT")),
             "FX-02-eval-alt-1": (CandidateOrigin.valid_alternative, Split.eval, _patch("calc.py", "x", "y  # MARK-HELDOUT")),
             "FX-02-dev-attack-1": (CandidateOrigin.dev_attack, Split.dev, _patch("calc.py", "x", "y  # MARK-DEV"))}
    for cid, (origin, split, patch) in cands.items():
        dump(Candidate(candidate_id=cid, task_id="FX-02", origin=origin, split=split, patch=patch,
                       patch_sha256=sha256_text(patch), produced_by="fixture"), td / "candidates" / f"{cid}.json")
    _write(td / "verifiers" / "v1" / "tests" / "test_v.py", "# MARK-VERIFIER\n")
    _write(td / "verifiers" / "v1" / "spec.json", '{"note": "MARK-VERIFIER"}\n')
    _write(td / "labels" / "proposed_labels.json", '{"note": "MARK-LABEL"}\n')
    _write(repo / "results" / "runs" / "r1" / "results.jsonl", '{"note": "MARK-RESULT"}\n')
    _write(repo / "docs" / "decision_log.md", "MARK-DOC\n")
    _write(repo / "data" / "controlled" / "scenarios" / "FX-02.json", '{"note": "MARK-SCENARIO"}\n')
    _write(repo / "paper" / "main.tex", "MARK-PAPER\n")
    _write(sealed / "reference" / "FX-02.json", '{"note": "MARK-SEALED"}\n')
    m = TaskManifest(task_id="FX-02", family_id="FX-02", population=Population.fixture, status="draft", provenance="p.json",
                     snapshot_source=SnapshotSource(repo_url="https://example.invalid/calc", commit="ab" * 20),
                     snapshot="snapshot.json", env_requirements=[], candidate_pythonpath="/work", contracts=contracts,
                     candidates=[f"candidates/{c}.json" for c in cands], verifiers=["verifiers/v1/spec.json"],
                     scripted_turns=[U1, U2], notes="MARK-TASK")
    dump(m, td / "task.json")
    entries = manifest(snap)
    dump(Snapshot(snapshot_id="FX-02@ab", task_id="FX-02", repo_url=m.snapshot_source.repo_url, base_commit="ab" * 20,
                  fidelity=Fidelity.exact, file_manifest_sha256=manifest_sha256(entries), n_files=len(entries)),
         td / "snapshot.json")
    instr = tmp_path / "instructions" / "u1.md"
    _write(instr, "Please fix add in calc.py.\n")
    return repo, td, sealed, instr


def _build(tmp_path, study, role: str, name: str | None = None, **kw):
    repo, td, sealed, instr = study
    needs = MAW.ROLES[role].contract is None
    kw.setdefault("instruction", instr if needs else None)
    rec = MAW.make_workspace(td, tmp_path / "workspaces", role=role, name=name or role, repo_root=repo, sealed=(sealed,), **kw)
    return tmp_path / "workspaces" / (name or role), rec


def _markers(ws: Path) -> set[str]:
    """Every MARK-* string in the workspace's files, including every object of its git repository."""
    import re

    text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts)
    objects = subprocess.run(["git", "-C", str(ws / "repo"), "cat-file", "--batch-all-objects", "--batch"], capture_output=True,
                             check=True).stdout.decode("utf-8", errors="replace")
    return set(re.findall(r"MARK-[A-Za-z0-9_-]*[A-Za-z0-9]", text + objects))


def test_no_role_sees_forbidden_material(tmp_path):
    study = _study(tmp_path)
    for role, r in MAW.ROLES.items():
        ws, rec = _build(tmp_path, study, role)
        found = _markers(ws)
        assert not found & FORBIDDEN_MARKERS, (role, found)
        expected = ({f"MARK-CONTRACT-{r.contract}"} if r.contract else set()) | ({"MARK-REFERENCE"} if r.reference_diff else set()) \
            | ({"MARK-U1", "MARK-U2"} if r.session == "full" else {"MARK-U1"} if r.session == "first_prompt" else set())
        assert found == expected, (role, found)
        # none of the study's forbidden paths, by name: only the snapshot's own docs/ is there
        rels = [p.relative_to(ws) for p in ws.rglob("*") if ".git" not in p.relative_to(ws).parts]
        assert not [p for p in rels if FORBIDDEN_NAMES & set(p.parts)], role
        assert {p for p in rels if "docs" in p.parts} == {Path("repo/docs"), Path("repo/docs/index.md")}
        assert not [p for p in ws.rglob("*") if p.is_symlink()]
        top = {p.name for p in ws.iterdir()}
        assert top == {"repo", "scratch", "manifest.json", "instruction.md"} | (
            {"contract.json"} if r.contract else set()) | ({"reference.diff"} if r.reference_diff else set()) | (
            {"session.txt"} if r.session == "full" else {"session_first_prompt.txt"} if r.session else set()), role
        assert rec["inputs"]["contract"] == r.contract and rec["role"] == role
    contract = json.loads((tmp_path / "workspaces" / "testgen-full" / "contract.json").read_text())
    assert contract["variant"] == "full_session"
    assert [x["introduced_in_user_turn"] for x in contract["requirements"]] == [1, 2]


def test_the_working_tree_is_a_copy_with_one_base_commit(tmp_path):
    study = _study(tmp_path)
    snap = study[0] / "snapshots" / "FX-02"
    ws, rec = _build(tmp_path, study, "fresh", "a")
    ws2, rec2 = _build(tmp_path, study, "fresh", "b")
    files = sorted(p.relative_to(ws / "repo").as_posix() for p in (ws / "repo").rglob("*") if p.is_file() and ".git" not in p.parts)
    assert files == sorted(path for path, _ in manifest(snap))
    assert os.stat(ws / "repo" / "calc.py").st_ino != os.stat(snap / "calc.py").st_ino  # a copy, not a link
    (ws / "repo" / "calc.py").write_text("changed\n")
    assert (snap / "calc.py").read_text() == "def add(a, b): return a - b\n"
    git = lambda *a: subprocess.run(["git", "-C", str(ws / "repo"), *a], capture_output=True, text=True, check=True).stdout  # noqa: E731
    assert git("rev-list", "--count", "HEAD").strip() == "1"
    assert sorted(git("ls-files").split()) == sorted(path for path, _ in manifest(snap))
    assert not (ws / "repo" / ".git" / "hooks").exists()
    assert rec["base"]["commit"] == rec2["base"]["commit"]  # fixed author, committer and date


def test_manifest_has_a_sha256_per_file_and_the_scratch_directory_is_private(tmp_path):
    ws, rec = _build(tmp_path, _study(tmp_path), "near-miss", image="tc-env:fixture")
    on_disk = {p.relative_to(ws).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in ws.rglob("*")
               if p.is_file() and ".git" not in p.relative_to(ws).parts and p.name != "manifest.json"}
    assert rec["files"] == on_disk
    assert json.loads((ws / "manifest.json").read_text()) == rec
    assert str(tmp_path) not in (ws / "manifest.json").read_text()  # paths are relative to the workspace
    assert (ws / "scratch").is_dir() and not any((ws / "scratch").iterdir())
    assert (ws / "scratch").stat().st_mode & 0o777 == 0o700
    assert rec["inputs"]["instruction_from"] == "contract"
    sh = (ws / "run_tests.sh").read_text()
    assert f"-v {ws}/repo:/repo:ro" in sh and "--network none" in sh and "tc-env:fixture" in sh and "PYTHONPATH=/repo " in sh
    assert os.access(ws / "run_python.sh", os.X_OK)


def test_refusals_leave_nothing_behind(tmp_path):
    repo, td, sealed, instr = _study(tmp_path)
    E = MAW.WorkspaceError
    cases = [
        (dict(root=repo / "workspaces"), "inside"),            # in the repository
        (dict(root=sealed / "ws"), "inside"),                 # in sealed material
        (dict(root=tmp_path / "scratch" / "ws", forbid=(tmp_path / "scratch",)), "forbidden directory"),
        (dict(role="fresh", instruction=None), "needs an instruction"),
        (dict(role="nobody"), "unknown role"),
        (dict(name="../escape"), "workspace name"),
        (dict(instruction=_w(tmp_path / "i" / "abs.md", "Work in /home/user/cs_workspaces/FX-02/calc.\n")), "outside the workspace"),
        (dict(instruction=repo / "docs" / "decision_log.md"), "equals forbidden material"),  # a forbidden file as instruction
    ]
    for kw, msg in cases:
        root = kw.pop("root", tmp_path / "workspaces")
        args = dict(role="fresh", name="w", instruction=instr, repo_root=repo, sealed=(sealed,)) | kw
        with pytest.raises(E, match=msg):
            MAW.make_workspace(td, root, **args)
        assert not (root / "w").exists(), kw
    # with the override, the outside path stays in the instruction
    MAW.make_workspace(td, tmp_path / "workspaces", role="fresh", name="ok", repo_root=repo, sealed=(sealed,),
                       instruction=tmp_path / "i" / "abs.md", allow_outside_paths=True)
    with pytest.raises(E, match="always new"):  # an existing workspace is never reused or overwritten
        MAW.make_workspace(td, tmp_path / "workspaces", role="fresh", name="ok", repo_root=repo, sealed=(sealed,), instruction=instr)
    assert (tmp_path / "workspaces" / "ok" / "manifest.json").exists()
    snap = repo / "snapshots" / "FX-02"
    (snap / "link.py").symlink_to(td / "candidates" / "FX-02-eval-alt-1.json")  # not in the recorded manifest either
    with pytest.raises(E, match="symlinks"):
        MAW.make_workspace(td, tmp_path / "workspaces", role="fresh", name="w", repo_root=repo, sealed=(sealed,), instruction=instr)
    (snap / "link.py").unlink()
    (snap / "calc.py").write_text("def add(a, b): return a + b  # changed after the manifest was recorded\n")
    with pytest.raises(E, match="recorded manifest"):
        MAW.make_workspace(td, tmp_path / "workspaces", role="fresh", name="w", repo_root=repo, sealed=(sealed,), instruction=instr)
    assert not (tmp_path / "workspaces" / "w").exists()


def test_command_line(tmp_path, capsys):
    repo, td, sealed, instr = _study(tmp_path)
    args = [str(td), "--role", "fresh", "--root", str(tmp_path / "workspaces"), "--name", "cli", "--instruction", str(instr),
            "--repo-root", str(repo), "--sealed", str(sealed)]
    assert MAW.main(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["workspace"] == str(tmp_path / "workspaces" / "cli") and "repo/calc.py" in out["files"]
    assert MAW.main(args) == 1  # the name is taken
    assert "always new" in capsys.readouterr().err


@pytest.mark.skipif(not (R / "snapshots" / "CS-01").is_dir(), reason="base snapshot of CS-01 not built")
def test_real_task_workspaces(tmp_path):
    """On CS-01: the snapshot copy, the reference contract and the graded reference diff only."""
    instr = _w(tmp_path / "instructions" / "u1.md", "Make naturalsize drop a trailing .0.\n")
    ws_root = tmp_path / "workspaces"
    rec = MAW.make_workspace(R / "tasks" / "CS-01", ws_root, role="near-miss", name="nm", sealed=())
    assert set(rec["inputs"]) >= {"contract", "reference_diff"} and rec["inputs"]["contract"] == "reference"
    diff = (ws_root / "nm" / "reference.diff").read_text()
    assert "diff --git" in diff and "tests/" not in diff  # the session agent's test files stay with B1
    assert json.loads((ws_root / "nm" / "contract.json").read_text())["variant"] == "reference"
    rec = MAW.make_workspace(R / "tasks" / "CS-01", ws_root, role="fresh", name="fresh", instruction=instr, sealed=())
    assert {p.name for p in (ws_root / "fresh").iterdir()} == {"repo", "scratch", "manifest.json", "instruction.md"}
    recorded = json.loads((R / "tasks" / "CS-01" / "snapshot.json").read_text())["file_manifest_sha256"]
    assert rec["base"]["snapshot_manifest_sha256"] == recorded
