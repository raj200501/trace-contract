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


def _study(tmp_path: Path, u1: str = U1, u2: str = U2, old_checkout: str | None = None) -> tuple[Path, Path, Path, Path]:
    """A miniature study repository: task FX-02, its base snapshot and session, and planted forbidden material.

    ``old_checkout``: the session's recorded workspace (the scenario's ``workspace``), for the fresh variants.
    """
    repo, sealed = tmp_path / "study", tmp_path / "sealed"
    snap = repo / "snapshots" / "FX-02"
    for rel, text in {"calc.py": "def add(a, b): return a - b\n", "tests/test_calc.py": "def test_add(): pass\n",
                      "docs/index.md": "# calc\n", "README.md": "calc\n"}.items():
        _write(snap / rel, text)
    rows = [{"type": "user", "uuid": "u1", "sessionId": SID, "timestamp": "2026-01-01T00:00:00Z", "message": {"role": "user", "content": u1}},
            {"type": "assistant", "uuid": "a1", "sessionId": SID, "timestamp": "2026-01-01T00:00:01Z",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}},
            {"type": "user", "uuid": "u2", "sessionId": SID, "timestamp": "2026-01-01T00:00:02Z", "message": {"role": "user", "content": u2}}]
    _write(repo / "data" / "fixtures" / "transcripts" / "FX-02.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
    td = repo / "tasks" / "FX-02"
    e1, e2 = f"{SID}/L000001.00", f"{SID}/L000003.00"
    contracts = {}
    for variant in ContractVariant:
        reqs = [_req("R1", RequirementKind.change, f"add returns a + b (MARK-CONTRACT-{variant.value})", e1, "fix add", u1)]
        if variant != ContractVariant.initial_only:
            reqs.append(_req("R2", RequirementKind.invariant, f"add(0, 0) == 0 (MARK-CONTRACT-{variant.value})", e2, "keep", u2))
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
    if old_checkout is not None:  # where an operator tool finds the session's old workspace (never in a workspace)
        _write(repo / "data" / "fixture" / "scenarios" / "FX-02.json", json.dumps({"workspace": old_checkout,
                                                                                    "note": "MARK-SCENARIO"}) + "\n")
    _write(repo / "paper" / "main.tex", "MARK-PAPER\n")
    _write(sealed / "reference" / "FX-02.json", '{"note": "MARK-SEALED"}\n')
    m = TaskManifest(task_id="FX-02", family_id="FX-02", population=Population.fixture, status="draft", provenance="p.json",
                     snapshot_source=SnapshotSource(repo_url="https://example.invalid/calc", commit="ab" * 20),
                     snapshot="snapshot.json", env_requirements=[], candidate_pythonpath="/work", contracts=contracts,
                     candidates=[f"candidates/{c}.json" for c in cands], verifiers=["verifiers/v1/spec.json"],
                     scripted_turns=[u1, u2], notes="MARK-TASK")
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


# --------------------------------------------------------------------------- round-4 fixes (D51, protocol §16.2)

def _mk(tmp_path, study, *, name="w", root=None, **kw):
    repo, td, sealed, instr = study
    args = dict(role="fresh", name=name, repo_root=repo, sealed=(sealed,), external=(), old_workspaces=())
    if "variant" not in kw:
        args["instruction"] = instr
    return MAW.make_workspace(td, root or tmp_path / "workspaces", **(args | kw))


def test_every_text_written_is_checked_for_outside_paths(tmp_path):
    old = tmp_path / "old" / "FX-02" / "calc"
    study = _study(tmp_path, u2=f"Actually, keep add(0, 0) == 0 as well MARK-U2; see {old}/calc.py.")
    E = MAW.WorkspaceError
    with pytest.raises(E, match=r"session\.txt: \[.*old/FX-02/calc/calc\.py"):  # a session text, not only instruction.md
        _mk(tmp_path, study, role="freeform")
    rec = _mk(tmp_path, study, role="freeform", name="ok", allow_outside_paths=True)  # the path does not exist
    assert rec["role"] == "freeform"
    old.mkdir(parents=True)
    with pytest.raises(E, match="that exist"):  # --allow-outside-paths is refused once a named path (or its directory) exists
        _mk(tmp_path, study, role="freeform", name="w2", allow_outside_paths=True)
    assert not (tmp_path / "workspaces" / "w2").exists()
    assert MAW.exists_near(str(old / "calc.py")) and not MAW.exists_near("/tmp/no-such-dir-fx/x") \
        and not MAW.exists_near("/tmp/no-such-file-fx")
    # What is not a path on this host does not count: the sandbox's /repo, system locations, tags and sed scripts.
    text = "</tool_use_error> seek(0)/write/truncate sed -n '/^def /p' /repo/x.py /usr/bin/python3 /dev/null /tmp"
    assert MAW.outside_paths(text, tmp_path / "ws") == []
    assert MAW.outside_paths(f"{tmp_path}/ws/repo and {tmp_path}/other", tmp_path / "ws") == [str(tmp_path / "other")]


def test_git_ignores_the_callers_git_variables(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    (other / "keep.txt").write_text("keep\n")
    run = lambda *a: subprocess.run(["git", "-C", str(other), *a], capture_output=True, text=True, check=True,  # noqa: E731
                                    env={"PATH": os.environ["PATH"], **MAW._GIT_ENV}).stdout
    run("init", "-q")
    run("add", "-A")
    run("commit", "-q", "-m", "other")
    head, index = run("rev-parse", "HEAD"), (other / ".git" / "index").read_bytes()
    for k, v in {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other), "GIT_INDEX_FILE": str(other / ".git" / "index"),
                 "GIT_OBJECT_DIRECTORY": str(other / ".git" / "objects"), "GIT_CONFIG_PARAMETERS": "'core.bare=true'"}.items():
        monkeypatch.setenv(k, v)
    assert not {k for k in MAW.git_env() if k.startswith("GIT_")} - set(MAW._GIT_ENV)
    study = _study(tmp_path)
    rec = _mk(tmp_path, study)
    ws = tmp_path / "workspaces" / "w"
    assert (ws / "repo" / ".git").is_dir() and rec["base"]["commit"]
    monkeypatch.delenv("GIT_DIR")
    assert run("rev-parse", "HEAD") == head and (other / ".git" / "index").read_bytes() == index  # the other repository


def test_forbidden_material_includes_sealed_external_and_other_workspaces(tmp_path):
    assert Path("/home/user/.tc_sealed") in MAW.DEFAULT_SEALED and MAW.DEFAULT_EXTERNAL == (Path("/home/user/ext"),)
    assert set(MAW.OLD_WORKSPACES) == {Path("/home/user/cs_workspaces"), Path("/home/user/gen_workspaces")}
    study = _study(tmp_path)
    E = MAW.WorkspaceError
    ext, old = tmp_path / "ext", tmp_path / "old_ws"
    for d, marker in ((ext, "MARK-EXT"), (old, "MARK-OLDWS")):
        _write(d / "x" / "file.txt", f"{marker}\n")
        with pytest.raises(E, match="equals forbidden material"):
            _mk(tmp_path, study, instruction=d / "x" / "file.txt", external=(ext,), old_workspaces=(old,))
        with pytest.raises(E, match="inside"):  # nor may a workspace lie there
            _mk(tmp_path, study, root=d / "ws", external=(ext,), old_workspaces=(old,))
    a = tmp_path / "workspaces" / "a"
    _mk(tmp_path, study, name="a")
    _write(a / "scratch" / "notes.md", "MARK-SIBLING: the other agent's notes\n")
    with pytest.raises(E, match=r"equals forbidden material \(.*/workspaces/a/scratch/notes\.md"):
        _mk(tmp_path, study, name="b", instruction=a / "scratch" / "notes.md")
    _mk(tmp_path, study, name="c", instruction=a / "instruction.md")  # a file the tool wrote there may repeat
    with pytest.raises(E, match="inside another workspace"):
        _mk(tmp_path, study, root=a / "scratch")
    assert sorted(p.name for p in (tmp_path / "workspaces").iterdir()) == ["a", "c"]


def _vanishing(monkeypatch, *, before_stat: dict[Path, object], before_read: tuple[Path, ...] = ()) -> None:
    """Make files of forbidden material vanish while it is walked, as a running S10 resolver's temporary files do: each
    path of ``before_stat`` is listed by the walk and then removed by its callable before it is stat'ed; each path of
    ``before_read`` is removed after it was stat'ed, before it is read."""
    files, sha = MAW.Forbidden.files, MAW._sha

    def walk(self):
        for p, ok in files(self):
            if p in before_stat:
                before_stat[p]()
            yield p, ok

    def read(p):
        if p in before_read:
            p.unlink()
        return sha(p)

    monkeypatch.setattr(MAW.Forbidden, "files", walk)
    monkeypatch.setattr(MAW, "_sha", read)


def test_a_file_that_vanishes_while_forbidden_material_is_walked_is_skipped(tmp_path, monkeypatch):
    """The walk covers the whole of data/, the git-ignored data/natural/s10_work included (its content is not fixed, and
    data/natural holds pseudonymised third-party text). A file there that is listed and then gone, or whose directory is
    gone or became a file, before it is read is skipped; every file still there is checked."""
    import shutil

    text = "pseudonymised third-party text\n"
    data = tmp_path / "data"
    kept = _w(data / "natural" / "tasks" / "NP-01" / "thread.txt", text)
    work = data / "natural" / "s10_work" / "NP-01"
    in_work = _w(work / "round-0" / "copy.txt", text.upper())  # same size: the work directory is still walked
    gone = _w(work / "round-0" / "cache" / "tmp-1", "x" * len(text))
    gone_dir = _w(work / "round-1" / "cache" / "tmp-2", "y" * len(text))
    became_file = _w(work / "round-2" / "tmp-3", "z" * len(text))
    read_gone = _w(work / "round-0" / "report.json.tmp", "w" * len(text))

    def to_file():
        shutil.rmtree(work / "round-2")
        (work / "round-2").write_text("now a file\n")

    _vanishing(monkeypatch, before_stat={gone: gone.unlink, gone_dir: lambda: shutil.rmtree(work / "round-1"),
                                         became_file: to_file}, before_read=(read_gone,))
    bad = MAW._forbidden_hashes(MAW.Forbidden((data,)), set(), {len(text)})
    assert sorted(bad.values()) == sorted([str(kept), str(in_work)])
    assert not gone.exists() and not read_gone.exists() and (work / "round-2").is_file()


def test_a_workspace_is_built_and_checked_while_a_resolver_writes_under_data(tmp_path, monkeypatch):
    """End to end: the S10 resolver's temporary files under the study's data/natural/s10_work vanish during the check, the
    workspace is built, and a workspace file that equals material there is still refused."""
    repo, td, sealed, instr = _study(tmp_path)
    work = repo / "data" / "natural" / "s10_work" / "NP-01" / "round-0"
    size = instr.stat().st_size
    tmp = [_w(work / "cache" / f"tmp-{k}", str(k) * size) for k in range(3)]
    _vanishing(monkeypatch, before_stat={tmp[0]: tmp[0].unlink, tmp[1]: tmp[1].unlink}, before_read=(tmp[2],))
    rec = MAW.make_workspace(td, tmp_path / "workspaces", role="fresh", name="w", repo_root=repo, sealed=(sealed,),
                             instruction=instr, external=(), old_workspaces=())
    assert rec["role"] == "fresh" and not any(p.exists() for p in tmp)
    copied = _w(work / "report.json", "MARK-NATURAL: a copy of study material\n")
    with pytest.raises(MAW.WorkspaceError, match=r"equals forbidden material \(.*/data/natural/s10_work/NP-01/round-0/report"):
        MAW.make_workspace(td, tmp_path / "workspaces", role="fresh", name="w2", repo_root=repo, sealed=(sealed,),
                           instruction=copied, external=(), old_workspaces=())
    assert not (tmp_path / "workspaces" / "w2").exists()


def _old_session(tmp_path: Path) -> tuple[Path, str, str]:
    old = tmp_path / "old_ws" / "FX-02"
    u1 = (f"Please fix add in calc.py MARK-U1.\n\nThe repo is checked out (as a git working copy) at {old}/calc. Use the "
          f"wrappers {old}/run_tests.sh [pytest args] (e.g. run_tests.sh -q tests) and {old}/run_python.sh -c '...'. "
          f"Please keep all your work inside {old}.")
    return old, u1, U2


def test_fresh_variants_substitute_the_old_workspace_paths(tmp_path):
    old, u1, u2 = _old_session(tmp_path)
    study = _study(tmp_path, u1=u1, u2=u2, old_checkout=f"{old}/calc")
    rec = _mk(tmp_path, study, name="CS-fresh-u1", variant="u1", image="tc-env:fixture")
    ws = tmp_path / "workspaces" / "CS-fresh-u1"
    text = (ws / "instruction.md").read_text()
    assert text == (u1.replace(f"{old}/calc", f"{ws}/repo").replace(f"{old}/run_tests.sh", f"{ws}/run_tests.sh")
                    .replace(f"{old}/run_python.sh", f"{ws}/run_python.sh").replace(f"inside {old}.", f"inside {ws}.") + "\n")
    assert str(old) not in text and MAW.outside_paths(text, ws) == []
    ins = rec["inputs"]
    assert ins["instruction_from"] == "variant" and ins["variant"] == "u1"
    assert ins["instruction_sha256"] == hashlib.sha256((ws / "instruction.md").read_bytes()).hexdigest()
    assert ins["path_substitutions"] == [{"turn": "U1", "from": f"{old}/calc", "to": "repo", "count": 1},
                                         {"turn": "U1", "from": f"{old}/run_tests.sh", "to": "run_tests.sh", "count": 1},
                                         {"turn": "U1", "from": f"{old}/run_python.sh", "to": "run_python.sh", "count": 1},
                                         {"turn": "U1", "from": str(old), "to": ".", "count": 1}]
    assert MAW.check_wrappers(ws, dict(root=str(ws), repo=str(ws / "repo"), image="tc-env:fixture", pythonpath="/repo",
                                       extra="")) == []
    rec = _mk(tmp_path, study, name="CS-fresh-final", variant="final", image="tc-env:fixture")
    ws2 = tmp_path / "workspaces" / "CS-fresh-final"
    first, rest = (ws2 / "instruction.md").read_text().split(f"\n\n{MAW.FINAL_JOINER}\n\n")
    assert rest == u2 + "\n" and f"{ws2}/repo" in first and str(old) not in first and rec["inputs"]["variant"] == "final"
    # The other runs never saw the old paths in an instruction, and the record only names them.
    assert json.loads((ws2 / "manifest.json").read_text())["inputs"]["path_substitutions"][0]["from"] == f"{old}/calc"


def test_fresh_variants_refuse_what_the_substitution_cannot_place(tmp_path):
    old, u1, u2 = _old_session(tmp_path)
    E = MAW.WorkspaceError
    study = _study(tmp_path, u1=u1 + f" Notes are in {old}/notes.txt.", u2=u2, old_checkout=f"{old}/calc")
    with pytest.raises(E, match="no corresponding path"):
        _mk(tmp_path, study, variant="u1", image="tc-env:fixture")
    study = _study(tmp_path / "s2", u1=u1, u2=u2, old_checkout=f"{old}/calc")
    for kw, msg in [(dict(variant="u1"), "--image"), (dict(variant="u1", image="t:x", role="near-miss"), "role fresh"),
                    (dict(variant="u1", image="t:x", instruction=study[3]), "no --instruction"),
                    (dict(variant="u2", image="t:x"), "unknown variant")]:
        with pytest.raises(E, match=msg):
            _mk(tmp_path, study, **kw)
    old.mkdir(parents=True)  # the old workspace was not sealed
    with pytest.raises(E, match="old workspace still exists"):
        _mk(tmp_path, study, variant="u1", image="tc-env:fixture")
    assert not (tmp_path / "workspaces").exists() or not any((tmp_path / "workspaces").iterdir())


def test_wrappers_must_run_code_only_in_the_sandbox(tmp_path):
    ws = tmp_path / "ws"
    fmt = dict(root=str(ws), repo=str(ws / "repo"), image="tc-env:x", pythonpath="/repo", extra="")
    ws.mkdir()
    for name, tpl in MAW._WRAPPERS:
        (ws / name).write_text(tpl.format(**fmt))
        (ws / name).chmod(0o755)
    assert MAW.check_wrappers(ws, fmt) == []
    good = (ws / "run_tests.sh").read_text()
    for bad, msg in [(good.replace("--network none", "--network host"), "network"),
                     (good.replace(f"-v {ws}/repo:/repo:ro", f"-v {ws}/repo:/repo:ro -v /:/host"), "mount only"),
                     (good.replace("--read-only ", ""), "read-only"),
                     (good.replace("exec docker run", "exec python -m pytest; docker run"), "does not exec docker run"),
                     (good + "python -m pytest \"$@\"\n", "exactly one command"),
                     (good.replace("--cap-drop ALL", "--cap-drop ALL --privileged"), "--privileged")]:
        (ws / "run_tests.sh").write_text(bad)
        problems = MAW.check_wrappers(ws, fmt)
        assert any(msg in p for p in problems) and any("not the controlled sessions' wrapper" in p for p in problems), msg
    (ws / "run_tests.sh").write_text(good)
    (ws / "run_tests.sh").chmod(0o644)
    assert MAW.check_wrappers(ws, fmt) == ["run_tests.sh is not executable"]


def test_command_line_variant(tmp_path, capsys):
    old, u1, u2 = _old_session(tmp_path)
    repo, td, sealed, _ = _study(tmp_path, u1=u1, u2=u2, old_checkout=f"{old}/calc")
    args = [str(td), "--role", "fresh", "--root", str(tmp_path / "workspaces"), "--name", "v", "--variant", "final",
            "--repo-root", str(repo), "--sealed", str(sealed)]
    assert MAW.main(args) == 1 and "--image" in capsys.readouterr().err
    assert MAW.main(args + ["--image", "tc-env:fixture", "--no-smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["inputs"]["variant"] == "final"
    with pytest.raises(SystemExit):
        MAW.main(args + ["--instruction", str(tmp_path / "x.md")])


def _local_env_image() -> str | None:
    try:
        out = subprocess.run(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}", "tc-env"], capture_output=True,
                             text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    tags = sorted(t for t in out.stdout.split() if t.startswith("tc-env:")) if out.returncode == 0 else []
    return tags[0] if tags else None


@pytest.mark.docker
def test_wrappers_work_in_the_docker_sandbox(tmp_path):
    image = _local_env_image()
    if image is None:
        pytest.skip("no local tc-env image")
    old, u1, u2 = _old_session(tmp_path)
    study = _study(tmp_path, u1=u1, u2=u2, old_checkout=f"{old}/calc")
    rec = _mk(tmp_path, study, name="smoke", variant="u1", image=image, smoke=True)
    assert rec["wrappers"]["smoke"] == "passed"
    ws = tmp_path / "workspaces" / "smoke"
    p = subprocess.run([str(ws / "run_python.sh"), "-c", "import calc; print(calc.add(2, 3))"], capture_output=True, text=True,
                       timeout=300)
    assert p.returncode == 0 and p.stdout.strip() == "-1"  # the base snapshot's code, run in the container
    with pytest.raises(MAW.WorkspaceError, match="do not work"):
        _mk(tmp_path, study, name="noimage", variant="u1", image="tc-env:does-not-exist-fixture", smoke=True)
    assert not (tmp_path / "workspaces" / "noimage").exists()
