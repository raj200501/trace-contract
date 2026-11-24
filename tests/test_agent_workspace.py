"""Isolated agent workspaces hold only what their role may see (scripts/make_agent_workspace.py, A6)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from natural_task_layout import (
    AGENT_ONLY_MARKERS, BASE_FILES, COMMENT_TEXT, HUNK_TEXT, ISSUE_TEXT, PR_TEXT, PRE_REVIEW_FILES, REFERENCE_FILES,
    REFERENCE_MOD, REPLY_TEXT, NaturalTask, build_natural_task,
)

from tracecontract.patches import diff_dirs, filter_patch
from tracecontract.schemas import (
    Candidate, CandidateOrigin, ContractVariant, EvidenceSpan, Fidelity, Population, Requirement, RequirementKind,
    RequirementStatus, Snapshot, SnapshotSource, Split, TaskContract, TaskManifest, sha256_text,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, load
from tracecontract.tasks import session_for_task, session_from_events
from tracecontract.verifier import hash_test_dir

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


# --------------------------------------------------------------------------- natural roles (protocol §15.5, §15.6, §19)
# The synthetic natural PR-review task of tests/natural_task_layout.py, built under data/natural/ of a scratch study
# repository, with what the natural arm adds before its workspaces are built: three contracts, development attacks and
# alternatives of both variants, two held-out candidates and the tests of six verifiers. Synthetic text only.

NAT_IMAGE = "tc-env:fixture"
NAT_VERIFIERS = ("initial_plain", "initial_audited", "full_plain", "full_audited", "reference_check", "independent_label")
# Markers planted in the natural study material: each may appear only in the workspaces _nat_markers names.
NAT_MARKERS = ("MARK-CONTRACT-initial_only", "MARK-CONTRACT-full_session", "MARK-CONTRACT-reference", "MARK-UNRESOLVED",
               "MARK-DEVATTACK-initial_only", "MARK-DEVATTACK-full_session", "MARK-DEVALT-initial_only",
               "MARK-DEVALT-full_session", "MARK-EVALALT", "MARK-EVALNM", "MARK-PROTECTED", "MARK-LABEL", "MARK-SEALED",
               "MARK-DOC", *(f"MARK-VERIFIER-{v}" for v in NAT_VERIFIERS))
_VTEST = ('from tc_sandbox import run_python\n\nCHECK_REQUIREMENTS = {{"test_add": ["R1"]}}\n\n\n'
          'def test_add():  # MARK-VERIFIER-{vid}\n    r = run_python("from fxnat.mod import add\\nresult = add(None, 2)")\n'
          '    assert r.value == 2\n')
_NAT_CANDIDATES = {  # kind -> (origin, split, produced_by, marker, also changes the test file)
    "dev-attack-initial_only-a1": (CandidateOrigin.dev_attack, Split.dev, "attack:v1:initial_only", "MARK-DEVATTACK-initial_only", True),
    "dev-attack-full_session-a1": (CandidateOrigin.dev_attack, Split.dev, "attack:v1:full_session", "MARK-DEVATTACK-full_session", True),
    "dev-alt-initial_only": (CandidateOrigin.valid_alternative, Split.dev, "altimpl:v1:initial_only:dev", "MARK-DEVALT-initial_only", False),
    "dev-alt-full_session": (CandidateOrigin.valid_alternative, Split.dev, "altimpl:v1:full_session:dev", "MARK-DEVALT-full_session", False),
    "eval-alt-1": (CandidateOrigin.valid_alternative, Split.eval, "altimpl:v1:reference:eval:1", "MARK-EVALALT", False),
    "eval-nm-1": (CandidateOrigin.constructed_near_miss, Split.eval, "nearmiss:v1:reference:eval", "MARK-EVALNM", True),
}
REVISER_DEV = {"initial_only": ("reference", "noop-dev", "dev-attack-initial_only-a1", "dev-alt-initial_only"),
               "full_session": ("reference", "noop-dev", "dev-attack-full_session-a1", "dev-alt-full_session")}
CHECKED = ("pre-review", "eval-alt-1", "eval-nm-1")
HARNESS_FILES = {"harness/tc_sandbox_api.py", "harness/lint_rules.py", "harness/example_tests/test_add.py"}


def _span(event_id: str, text: str, quote: str) -> EvidenceSpan:
    start = text.index(quote)
    return EvidenceSpan(event_id=event_id, start=start, end=start + len(quote), quote=quote)


def _nreq(rid: str, kind: RequirementKind, statement: str, spans: list[EvidenceSpan], introduced_at: str,
          status: RequirementStatus = RequirementStatus.explicit, **kw) -> Requirement:
    return Requirement(req_id=rid, statement=statement, kind=kind, status=status, introduced_at=introduced_at,
                       evidence=spans, observable=statement, proposer="fixture", **kw)


def _natural_contract(nt: NaturalTask, variant: ContractVariant) -> TaskContract:
    mark, issue, comment, reply = f"(MARK-CONTRACT-{variant.value})", nt.event("issue"), nt.event("comment"), nt.event("reply")
    reqs = [_nreq("R1", RequirementKind.change, f"add(None, 2) returns 2 {mark}",
                  [_span(issue, ISSUE_TEXT, "should treat a missing value as zero")], issue)]
    if variant != ContractVariant.initial_only:
        r2_spans = [_span(comment, COMMENT_TEXT, "treat a missing second argument as 0 too")]
        if variant == ContractVariant.reference:  # a quote from the hunk (not a user turn) that the mapper leaves out
            r2_spans.append(_span(nt.event("hunk"), HUNK_TEXT, "if a is None:"))
        reqs += [_nreq("R2", RequirementKind.change, f"add(2, None) returns 2 {mark}", r2_spans, comment),
                 _nreq("R3", RequirementKind.change, f"add(None, None) returns 0 {mark}",
                       [_span(reply, REPLY_TEXT, "add(None, None) should return 0")], reply)]
    if variant == ContractVariant.full_session:
        reqs.append(_nreq("R4", RequirementKind.constraint, "what else the reviewer wants (MARK-UNRESOLVED)", [], comment,
                          status=RequirementStatus.unresolved))
    if variant == ContractVariant.reference:
        reqs.append(_nreq("R4", RequirementKind.invariant, f"add(1, 2) == 3 still holds {mark}", [], issue,
                          status=RequirementStatus.inferred, rationale="the existing behaviour of add is kept"))
    return TaskContract(contract_id=f"{nt.task_id}-{variant.value}", task_id=nt.task_id, session_id=nt.session_id,
                        variant=variant, requirements=reqs, created_by="fixture", created_at="t")


def _nat_state_patch(base: Path, files: dict[str, str], scratch: Path) -> str:
    state = scratch / "state"
    shutil.copytree(base, state)
    for rel, text in files.items():
        _write(state / rel, text)
    patch = diff_dirs(base, state)
    shutil.rmtree(state)
    return patch


class _NatEnv:
    """The natural study: the task (``nt``), its sealed directory and the root of its workspaces (``/home/user/nat_ws/<task>``
    in the recipe)."""

    def __init__(self, tmp_path: Path):
        self.nt = nt = build_natural_task(tmp_path / "study")
        td = self.td = nt.task_dir
        contracts = {}
        for v in ContractVariant:
            dump(_natural_contract(nt, v), td / "contracts" / f"{v.value}.json")
            contracts[v.value] = f"contracts/{v.value}.json"
        new = []
        for kind, (origin, split, by, marker, test) in _NAT_CANDIDATES.items():
            files = {"fxnat/mod.py": REFERENCE_MOD.replace("b = 0", "b = 1" if origin == CandidateOrigin.dev_attack else "b = 0")
                     + f"# {marker}\n"}
            if test:
                files["tests/test_mod.py"] = BASE_FILES["tests/test_mod.py"] + "# MARK-PROTECTED\n"
            patch = _nat_state_patch(nt.snapshot_dir, files, tmp_path)
            c = Candidate(candidate_id=nt.candidate_id(kind), task_id=nt.task_id, origin=origin, split=split, patch=patch,
                          patch_sha256=sha256_text(patch), produced_by=by)
            dump(c, td / "candidates" / f"{c.candidate_id}.json")
            new.append(f"candidates/{c.candidate_id}.json")
        m = load(td / "task.json", TaskManifest)
        dump(m.model_copy(update={"contracts": contracts, "candidates": [*m.candidates, *new]}), td / "task.json")
        for vid in NAT_VERIFIERS:
            _write(td / "verifiers" / vid / "tests" / "test_v.py", _VTEST.format(vid=vid))
        _write(td / "labels" / "proposed_labels.json", '{"note": "MARK-LABEL"}\n')
        _write(nt.root / "docs" / "decision_log.md", "MARK-DOC\n")
        self.sealed = tmp_path / "sealed"
        _write(self.sealed / "reference" / f"{nt.task_id}.json", '{"note": "MARK-SEALED"}\n')
        self.ws_root = tmp_path / "nat_ws" / nt.task_id
        self.instr = _w(tmp_path / "instructions" / "fresh.md", "Treat a missing value as zero in add().\n")

    def cid(self, kind: str) -> str:
        return self.nt.candidate_id(kind)

    def args(self, role: str) -> dict:
        """The options the natural recipe gives each role (section 5 of the build plan)."""
        image = {"image": NAT_IMAGE}
        def tests(vid: str) -> Path:
            return self.td / "verifiers" / vid / "tests"

        return {
            "fresh": {"instruction": self.instr, **image},
            "contract-initial": {}, "contract-full": {}, "refcontract": {}, "mapper": {}, "labeler": {},
            "reviser-initial": {**image, "tests_from": tests("initial_audited"),
                                "dev_candidates": tuple(self.cid(k) for k in REVISER_DEV["initial_only"])},
            "reviser-full": {**image, "tests_from": tests("full_audited"),
                             "dev_candidates": tuple(self.cid(k) for k in REVISER_DEV["full_session"])},
            "refcheck-review": {**image, "tests_from": tests("reference_check")},
            "checker": {**image, "candidates": tuple(self.cid(k) for k in CHECKED)},
        }.get(role, image)

    def build(self, role: str, name: str | None = None, *, root: Path | None = None, **kw) -> tuple[dict, Path]:
        args = {"role": role, "name": name or role, "repo_root": self.nt.root, "sealed": (self.sealed,), "external": (),
                "old_workspaces": ()} | self.args(role) | kw
        root = root or self.ws_root
        return MAW.make_workspace(self.td, root, **args), root / args["name"]

    def expected_files(self, role: str) -> set[str]:
        repo = {f"repo/{p}" for p in BASE_FILES}
        wrap, contract = {"run_tests.sh", "run_python.sh"}, {"instruction.md", "contract.json"}
        generator = repo | contract | {"reference.diff"} | wrap
        files = {
            "fresh": repo | {"instruction.md"} | wrap,
            "testgen-initial": generator, "testgen-full": generator, "attack-initial": generator, "attack-full": generator,
            "refcheck": generator,
            "freeform": repo | {"session.txt", "reference.diff"} | wrap,
            "diff-derived": repo | {"session_first_prompt.txt", "reference.diff"} | wrap,
            "alt-initial": repo | contract | wrap, "alt-full": repo | contract | wrap, "alternative": repo | contract | wrap,
            "near-miss": repo | contract | {"reference.diff", "run_python.sh"},
            "labeler": repo | contract | HARNESS_FILES,
            "contract-initial": {"session_first_prompt.txt", "session_events.json"},
            "contract-full": {"session.txt", "session_events.json"},
            "refcontract": {"session.txt", "reference.diff", "addressing.diff", "session_events.json"},
            "reviser-initial": generator | {"tests/test_v.py"} | {f"devcands/{self.cid(k)}.patch" for k in REVISER_DEV["initial_only"]},
            "reviser-full": generator | {"tests/test_v.py"} | {f"devcands/{self.cid(k)}.patch" for k in REVISER_DEV["full_session"]},
            "refcheck-review": generator | {"tests/test_v.py"},
            "mapper": {f"contracts/{v.value}.json" for v in ContractVariant},
            "checker": generator | {f"candidates/candidate-{k}.patch" for k in range(1, len(CHECKED) + 1)},
        }[role]
        return files | {"manifest.json"}

    def heldout_ids(self) -> list[str]:
        return [c.candidate_id for c in (load(self.td / p, Candidate) for p in load(self.td / "task.json", TaskManifest).candidates)
                if c.split == Split.eval]


def _nat_markers(role: str) -> set[str]:
    """The planted markers that the workspace of ``role`` holds (every other one it must not hold)."""
    variant = {"testgen-initial": "initial_only", "attack-initial": "initial_only", "alt-initial": "initial_only",
               "reviser-initial": "initial_only", "testgen-full": "full_session", "attack-full": "full_session",
               "alt-full": "full_session", "reviser-full": "full_session", "alternative": "reference", "near-miss": "reference",
               "refcheck": "reference", "refcheck-review": "reference", "labeler": "reference", "checker": "reference"}
    extra = {"reviser-initial": {"MARK-DEVATTACK-initial_only", "MARK-DEVALT-initial_only", "MARK-VERIFIER-initial_audited"},
             "reviser-full": {"MARK-DEVATTACK-full_session", "MARK-DEVALT-full_session", "MARK-VERIFIER-full_audited"},
             "refcheck-review": {"MARK-VERIFIER-reference_check"}, "checker": {"MARK-EVALALT", "MARK-EVALNM"},
             "mapper": {*(f"MARK-CONTRACT-{v.value}" for v in ContractVariant), "MARK-UNRESOLVED"}}
    return ({f"MARK-CONTRACT-{variant[role]}"} if role in variant else set()) | extra.get(role, set())


def _nat_files(ws: Path) -> set[str]:
    return {p.relative_to(ws).as_posix() for p in ws.rglob("*") if p.is_file() and ".git" not in p.relative_to(ws).parts}


def _nat_text(ws: Path) -> str:
    """Every file of the workspace as text, and every object of its git repository, if it has one."""
    text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(ws.rglob("*"))
                   if p.is_file() and ".git" not in p.relative_to(ws).parts)
    if (ws / "repo" / ".git").is_dir():
        text += subprocess.run(["git", "-C", str(ws / "repo"), "cat-file", "--batch-all-objects", "--batch"],
                               capture_output=True, check=True).stdout.decode("utf-8", errors="replace")
    return text


def test_every_role_on_a_natural_task_holds_exactly_its_inputs(tmp_path):
    """Every role, controlled and natural, built as the natural recipe builds it: its exact file set, the planted markers
    it may hold and no other, and never the PR body or a commit message (in no file and no git object)."""
    env = _NatEnv(tmp_path)
    assert not (env.nt.root / "snapshots").exists()  # the base lies under data/natural/snapshots only (roots)
    session = session_for_task(env.td, env.nt.root)
    agent_texts = [e.text for e in session.events if e.event_id in MAW.agent_only_events(session)]
    assert len(agent_texts) == 4 and PR_TEXT in agent_texts  # the PR body and three commit messages
    recorded = load(env.td / "snapshot.json", Snapshot).file_manifest_sha256
    heldout = env.heldout_ids()
    assert sorted(heldout) == sorted(env.cid(k) for k in ("pre-review", "noop-eval", "eval-alt-1", "eval-nm-1"))
    for role in [*MAW.ROLES, *MAW.NATURAL_ROLES]:
        rec, ws = env.build(role)
        files = _nat_files(ws)
        assert files == env.expected_files(role), (role, sorted(files ^ env.expected_files(role)))
        r = MAW.role_for(role, Population.natural_pr_review)
        assert (ws / "scratch").is_dir() and (ws / "repo").is_dir() == r.repo, role
        text = _nat_text(ws)
        found = {mk for mk in NAT_MARKERS if mk in text}
        assert found == _nat_markers(role), (role, found)
        assert not [mk for mk in AGENT_ONLY_MARKERS if mk in text] and not [t for t in agent_texts if t in text], role
        thread, first = role in ("contract-full", "refcontract", "freeform"), role in ("contract-initial", "diff-derived")
        assert (ISSUE_TEXT in text) == (thread or first), role
        assert (COMMENT_TEXT in text) == (REPLY_TEXT in text) == (HUNK_TEXT in text) == thread, role
        assert rec["role"] == role and rec["files"] == {f: hashlib.sha256((ws / f).read_bytes()).hexdigest()
                                                        for f in files - {"manifest.json"}}
        assert rec["base"] == (None if not r.repo else {"snapshot_manifest_sha256": recorded, "commit": rec["base"]["commit"],
                                                        "n_files": len(BASE_FILES)})
        assert str(tmp_path) not in (ws / "manifest.json").read_text(), role  # paths are relative to the workspace
        named = [i for i in heldout for f in files if i in f or i in (ws / f).read_text(errors="replace")]
        assert not named, (role, named)  # no held-out candidate id in a file name, a text or the manifest
    near = json.loads((env.ws_root / "near-miss" / "manifest.json").read_text())
    assert near["wrappers"]["scripts"] == ["run_python.sh"]
    assert "scripts" not in json.loads((env.ws_root / "refcheck" / "manifest.json").read_text())["wrappers"]


def test_the_contract_workspaces_hold_the_events_their_texts_show(tmp_path):
    env = _NatEnv(tmp_path)
    ids = {k: env.nt.event(k) for k in ("issue", "hunk", "comment", "reply")}
    for role, variant, shown, text in [("contract-initial", "initial_only", ["issue"], "session_first_prompt.txt"),
                                       ("contract-full", "full_session", ["issue", "hunk", "comment", "reply"], "session.txt"),
                                       ("refcontract", "reference", ["issue", "hunk", "comment", "reply"], "session.txt")]:
        rec, ws = env.build(role)
        record = json.loads((ws / "session_events.json").read_text())
        assert record["variant"] == variant and [e["event_id"] for e in record["events"]] == [ids[k] for k in shown]
        assert record["render_sha256"] == sha256_text((ws / text).read_text())
        back = session_from_events((ws / "session_events.json").read_text())  # what check-proposals reads
        assert [e.event_id for e in back.events] == [ids[k] for k in shown]
        assert rec["inputs"]["session_events"] == variant and rec["inputs"]["instruction_from"] is None
        assert rec["wrappers"] is None and rec["base"] is None
    assert (env.ws_root / "contract-initial" / "session_first_prompt.txt").read_text().startswith("NOTICE: third-party text")


def test_the_addressing_diff_is_the_graded_change_from_the_pre_review_state_to_the_reference(tmp_path):
    env = _NatEnv(tmp_path)
    rec, ws = env.build("refcontract")
    pre, ref = tmp_path / "pre", tmp_path / "ref"
    for d, over in ((pre, PRE_REVIEW_FILES), (ref, REFERENCE_FILES)):
        for rel, text in {**BASE_FILES, **over}.items():
            _write(d / rel, text)
    expected = filter_patch(diff_dirs(pre, ref))[0]
    got = (ws / "addressing.diff").read_text()
    assert got == expected and "+    if b is None:" in got and "+    if a is None:" not in got and "test_mod.py" not in got
    pre_c, ref_c = (load(env.td / "candidates" / f"{env.cid(k)}.json", Candidate) for k in ("pre-review", "reference"))
    assert rec["inputs"]["addressing_diff"] == {  # the held-out pre-review state by origin and patch hash, not by id
        "from_origin": "natural_pre_review", "from_patch_sha256": pre_c.patch_sha256, "to": env.cid("reference"),
        "to_patch_sha256": ref_c.patch_sha256, "removed_protected": 1}
    assert (ws / "reference.diff").read_text() == filter_patch(load(env.td / "candidates" / f"{env.cid('reference')}.json",
                                                                    Candidate).patch)[0]


def test_revisers_get_their_tests_and_development_patches_and_the_checker_held_out_patches(tmp_path):
    env = _NatEnv(tmp_path)
    def cand(k: str) -> Candidate:
        return load(env.td / "candidates" / f"{env.cid(k)}.json", Candidate)

    rec, ws = env.build("reviser-initial")
    src = env.td / "verifiers" / "initial_audited" / "tests"
    assert (ws / "tests" / "test_v.py").read_bytes() == (src / "test_v.py").read_bytes()
    assert rec["inputs"]["tests"] == {"from": "verifiers/initial_audited/tests", "verifier": "initial_audited",
                                      "content_sha256": hash_test_dir(src), "n_files": 1}
    assert rec["inputs"]["dev_candidates"] == {env.cid(k): cand(k).patch_sha256 for k in REVISER_DEV["initial_only"]}
    for k in REVISER_DEV["initial_only"]:  # the graded part of each patch: no test file
        assert (ws / "devcands" / f"{env.cid(k)}.patch").read_text() == filter_patch(cand(k).patch)[0]
    assert (ws / "devcands" / f"{env.cid('reference')}.patch").read_text() == (ws / "reference.diff").read_text()
    assert (ws / "devcands" / f"{env.cid('noop-dev')}.patch").read_text() == ""
    rec, ws = env.build("checker")
    labels = MAW.checker_label_map(env.td, tuple(env.cid(k) for k in CHECKED))  # label -> id, for the host only
    assert sorted(labels) == [f"candidate-{k}" for k in (1, 2, 3)] and sorted(labels.values()) == sorted(env.cid(k) for k in CHECKED)
    by_label = {lab: load(env.td / "candidates" / f"{cid}.json", Candidate) for lab, cid in labels.items()}
    assert rec["inputs"]["candidates"] == {lab: c.patch_sha256 for lab, c in by_label.items()}  # no id in the record
    assert [lab for lab, _ in sorted(by_label.items(), key=lambda x: x[1].patch_sha256)] == sorted(labels)  # numbered by hash
    for lab, c in by_label.items():
        assert (ws / "candidates" / f"{lab}.patch").read_text() == filter_patch(c.patch)[0]
    assert "MARK-PROTECTED" in cand("eval-nm-1").patch and "MARK-PROTECTED" not in _nat_text(ws)


def test_revisers_and_checkers_refuse_what_they_may_not_see(tmp_path):
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    def rev(*ks: str) -> tuple[str, ...]:
        return tuple(env.cid(k) for k in ks)

    cases = [
        ("reviser-initial", {"dev_candidates": rev("reference", "pre-review")}, "held-out candidate"),
        ("reviser-initial", {"dev_candidates": rev("eval-nm-1")}, "held-out candidate"),
        ("reviser-full", {"dev_candidates": rev("noop-eval")}, "held-out candidate"),
        ("reviser-initial", {"dev_candidates": rev("dev-attack-full_session-a1")}, "not built for the initial_only contract"),
        ("reviser-full", {"dev_candidates": rev("dev-alt-initial_only")}, "not built for the full_session contract"),
        ("reviser-initial", {"dev_candidates": ("NP-90-nobody",)}, "has no candidate"),
        ("reviser-initial", {"dev_candidates": rev("reference", "reference")}, "named twice"),
        ("reviser-initial", {"dev_candidates": ()}, "needs --dev-candidates"),
        ("reviser-initial", {"tests_from": None}, "needs --tests-from"),
        ("reviser-initial", {"tests_from": env.td / "verifiers" / "initial_plain" / "tests"}, "initial_audited/tests"),
        ("reviser-full", {"tests_from": env.td / "verifiers" / "initial_audited" / "tests"}, "full_audited/tests"),
        ("refcheck-review", {"tests_from": env.td / "verifiers" / "independent_label" / "tests"}, "reference_check/tests"),
        ("checker", {"candidates": rev("reference")}, "development candidate"),
        ("checker", {"candidates": rev("eval-alt-1", "dev-attack-initial_only-a1")}, "development candidate"),
        ("checker", {"candidates": rev("noop-eval")}, "no-op"),
        ("checker", {"candidates": ()}, "needs --candidates"),
        ("checker", {"dev_candidates": rev("reference")}, "takes no --dev-candidates"),
        ("reviser-initial", {"candidates": rev("eval-alt-1")}, "takes no --candidates"),
        ("testgen-initial", {"tests_from": env.td / "verifiers" / "initial_plain" / "tests"}, "takes no --tests-from"),
        ("labeler", {"tests_from": env.td / "verifiers" / "reference_check" / "tests"}, "independent_label/tests"),
        ("contract-initial", {"image": NAT_IMAGE}, "runs no code"),
        ("mapper", {"image": NAT_IMAGE}, "runs no code"),
    ]
    for role, kw, msg in cases:
        with pytest.raises(E, match=msg):
            env.build(role, name="w", **kw)
        assert not (env.ws_root / "w").exists(), (role, kw)
    # a natural role on a controlled task, and a controlled task's roles unchanged by the natural rules
    repo, td, sealed, _ = _study(tmp_path / "controlled")
    for role in MAW.NATURAL_ROLES:
        with pytest.raises(E, match="natural PR-review tasks only"):
            MAW.make_workspace(td, tmp_path / "cws", role=role, name="w", repo_root=repo, sealed=(sealed,))
    with pytest.raises(E, match="takes no --tests-from"):  # a controlled labeler has no revision copy
        MAW.make_workspace(td, tmp_path / "cws", role="labeler", name="w", repo_root=repo, sealed=(sealed,),
                           tests_from=td / "verifiers" / "v1" / "tests")
    assert not (tmp_path / "cws").exists() or not any((tmp_path / "cws").iterdir())


def test_the_mapper_reads_the_three_contracts_only(tmp_path):
    env = _NatEnv(tmp_path)
    rec, ws = env.build("mapper")
    assert rec["inputs"]["contracts"] == ["initial_only", "full_session", "reference"]
    for v in ContractVariant:
        got = json.loads((ws / "contracts" / f"{v.value}.json").read_text())
        stored = load(env.td / "contracts" / f"{v.value}.json", TaskContract)
        assert (ws / "contracts" / f"{v.value}.json").read_bytes() != (env.td / "contracts" / f"{v.value}.json").read_bytes()
        assert got["variant"] == v.value and [r["req_id"] for r in got["requirements"]] == [r.req_id for r in stored.requirements]
        assert {k for r in got["requirements"] for k in r} == {
            "req_id", "kind", "status", "scored", "subjective", "statement", "observable", "supersedes", "superseded_by",
            "conflicts_with", "rationale", "introduced_in_user_turn", "evidence"}
    full = {r["req_id"]: r for r in json.loads((ws / "contracts" / "full_session.json").read_text())["requirements"]}
    assert full["R4"]["status"] == "unresolved" and [full[k]["introduced_in_user_turn"] for k in ("R1", "R2", "R3")] == [1, 2, 3]
    ref = {r["req_id"]: r for r in json.loads((ws / "contracts" / "reference.json").read_text())["requirements"]}
    assert ref["R2"]["evidence"] == [{"user_turn": 2, "quote": "treat a missing second argument as 0 too"}]  # no hunk quote
    assert ref["R4"]["status"] == "inferred" and ref["R4"]["rationale"]


def test_a_natural_labeler_gets_the_harness_docs_and_may_get_its_own_tests_for_its_revision(tmp_path):
    env = _NatEnv(tmp_path)
    rec, ws = env.build("labeler")
    api, lint = (ws / "harness" / "tc_sandbox_api.py").read_text(), (ws / "harness" / "lint_rules.py").read_text()
    assert "def run_python(snippet: str" in api and "class CallResult" in api and "def run_cmd(" in api
    assert "_WRAPPER = r'''" not in api and "def _spawn(" not in api  # the trusted internals are left out
    assert "def lint_process_separated(" in lint and "ALLOWED_IMPORTS = " in lint and "def generation_record(" not in lint
    harness = Path(MAW.HARNESS_MODULE).read_text()
    assert harness.split('"""', 2)[1] in api  # the module docstring, verbatim
    example = MAW.EXAMPLE_TESTS / "test_add.py"
    assert (ws / "harness" / "example_tests" / "test_add.py").read_bytes() == example.read_bytes()
    docs = rec["inputs"]["harness_docs"]
    assert set(docs["files"]) == HARNESS_FILES and docs["sources_sha256"]["example_tests"] == hash_test_dir(MAW.EXAMPLE_TESTS)
    assert rec["inputs"]["container_paths"] == ["/mnt/candidate"]  # a path of the grading container the lint rules name
    assert "/tmp/claude-" not in api + lint
    rec, ws = env.build("labeler", name="labeler-revision", tests_from=env.td / "verifiers" / "independent_label" / "tests")
    assert _nat_files(ws) == env.expected_files("labeler") | {"tests/test_v.py"}
    assert "MARK-VERIFIER-independent_label" in _nat_text(ws) and rec["inputs"]["tests"]["verifier"] == "independent_label"


def test_a_natural_near_miss_has_run_python_only(tmp_path):
    env = _NatEnv(tmp_path)
    rec, ws = env.build("near-miss")
    fmt = {"root": str(ws), "repo": str(ws / "repo"), "image": NAT_IMAGE, "pythonpath": "/repo", "extra": ""}
    assert not (ws / "run_tests.sh").exists() and MAW.check_wrappers(ws, fmt, ("run_python.sh",)) == []
    assert MAW.check_wrappers(ws, fmt) == ["run_tests.sh is missing"]
    assert rec["wrappers"] == {"image": NAT_IMAGE, "pythonpath": "/repo", "pytest_args": "", "scripts": ["run_python.sh"]}
    assert MAW.role_for("near-miss", Population.controlled).wrappers == "both"  # a controlled near miss keeps both


def _location(root: Path, *, repo_root: Path, sealed: tuple[Path, ...] = (), forbid: tuple[Path, ...] = (),
              sessions: tuple[Path, ...] | None = None) -> None:
    """The pure location check of a workspace ``root/w`` (it only reads: nothing is created, whatever it decides)."""
    MAW._check_location(root, root / "w", repo_root, sealed, (), (), forbid, **({} if sessions is None else {"sessions": sessions}))


def test_natural_workspace_roots_are_refused_in_the_repository_third_party_data_and_session_directories(tmp_path):
    """Roots at the host's real locations are checked by the pure location check, which creates nothing, so a regression
    cannot write a workspace there; roots under tmp_path are also refused end to end."""
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    real = [(MAW.REPO / "nat_ws_fixture", "inside \\(or around\\) the repository"),
            (Path("/home/user/ext/nat_ws_fixture"), "third-party data"),  # refused even without --external
            (Path("/tmp/claude-fixture-ws/NP-90"), "Claude session directory")]
    before = {p: p.exists() for p, _ in real}
    for root, msg in real:
        with pytest.raises(E, match=msg):
            _location(root, repo_root=env.nt.root)
    assert {p: p.exists() for p, _ in real} == before  # nothing was created
    for root, msg in [(env.nt.root / "data" / "natural" / "nat_ws", "the root .* inside \\(or around\\) the repository"),
                      (tmp_path, "around\\) the repository"),  # a root holding the study repository
                      (env.sealed / "ws", "sealed material")]:
        with pytest.raises(E, match=msg):
            env.build("contract-full", name="w", root=root)
        assert not (root / "w").exists(), root
    _, a = env.build("contract-full", name="a")
    with pytest.raises(E, match="inside another workspace"):
        env.build("contract-initial", name="w", root=a / "scratch")
    with pytest.raises(E, match="forbidden directory"):
        env.build("contract-initial", name="w", root=tmp_path / "scratchpad" / "ws", forbid=(tmp_path / "scratchpad",))
    assert not (tmp_path / "scratchpad").exists()


def test_roots_around_claude_session_directories_are_refused(tmp_path, monkeypatch):
    """Not only inside: neither /tmp nor / (around /tmp/claude-*), nor the home directory (around ~/.claude), nor a
    directory holding a .claude directory, nor one around a configured session directory is a root."""
    E = MAW.WorkspaceError
    study = Path("/srv/no-such-study-fixture")  # the pure check compares paths: the study need not exist, nor lie under /tmp
    # The check also refuses every root around the checkout the script runs from (MAW.REPO). In a checkout under /tmp,
    # that rule would refuse /tmp first, so the checkout is put beside the study here: the refusals below are then the
    # session-directory rule's alone, wherever the checkout lies.
    monkeypatch.setattr(MAW, "REPO", study)
    for root in (Path("/tmp"), Path("/"), Path.home(), Path("/tmp/claude-fixture"), Path("/tmp/claude-fixture-x/deeper")):
        with pytest.raises(E, match="Claude session directory|the repository"):  # / is also around the repository
            _location(root, repo_root=study)
    with pytest.raises(E, match="Claude session directory"):
        _location(Path("/tmp"), repo_root=study)
    assert Path.home() / ".claude" in MAW.session_dirs()
    holder = tmp_path / "holder"
    (holder / ".claude").mkdir(parents=True)
    cfg = tmp_path / "cfg" / "claude-config"
    for root in (holder, holder / ".claude" / "ws", cfg, cfg.parent, tmp_path / "cfg" / "claude-config" / "x"):
        with pytest.raises(E, match="Claude session directory"):
            _location(root, repo_root=study, sessions=(cfg,))
    _location(tmp_path / "nat_ws" / "NP-90", repo_root=study, sessions=(cfg,))  # beside them: allowed
    _location(tmp_path / "cfg" / "other", repo_root=study, sessions=(cfg,))


def test_a_plain_group_directory_may_be_the_root(tmp_path):
    """One workspace per attack state, under a group directory: workspaces built beside the group may hold the files
    this tool wrote in the group's workspaces; what an agent wrote in the group, in its workspaces or in a workspace
    beside the group stays forbidden material."""
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    _, tg = env.build("testgen-initial")
    agent_file = _w(tg / "tests" / "test_gen.py", "# MARK-SIBLING: the generator's own tests\n")
    group = env.ws_root / "attack-initial"
    _, a1 = env.build("attack-initial", name="a1", root=group)
    env.build("attack-initial", name="a2", root=group)
    assert sorted(p.name for p in group.iterdir()) == ["a1", "a2"] and not MAW._is_workspace(group)
    _, alt = env.build("alt-initial")  # the same contract.json and instruction.md as a1 and a2
    assert (alt / "contract.json").read_bytes() == (a1 / "contract.json").read_bytes()
    notes = _w(a1 / "scratch" / "notes.md", "MARK-AGENT: an attack agent's notes\n")
    loose = _w(group / "plan.md", "MARK-AGENT: the attack agent's plan beside its states\n")
    for f in (notes, loose):
        with pytest.raises(E, match="equals forbidden material"):
            env.build("fresh", name="x", instruction=f)
    with pytest.raises(E, match=r"equals forbidden material \(.*/testgen-initial/tests/test_gen\.py"):
        env.build("attack-initial", name="a3", root=group, instruction=agent_file)
    with pytest.raises(E, match="inside another workspace"):
        env.build("attack-initial", name="a4", root=a1)
    assert sorted(p.name for p in group.iterdir()) == ["a1", "a2", "plan.md"] and not (env.ws_root / "x").exists()


def test_a_text_that_names_an_event_no_reader_is_shown_is_refused(tmp_path, monkeypatch):
    env = _NatEnv(tmp_path)
    session = session_for_task(env.td, env.nt.root)
    assert MAW.agent_only_events(session) == sorted([env.nt.event("pr"), *(env.nt.event(k) for k in ("first", "reviewed",
                                                                                                    "addressing"))])
    repo, td, _, _ = _study(tmp_path / "controlled")
    assert MAW.agent_only_events(session_for_task(td, repo)) == []
    real = MAW.render_session
    monkeypatch.setattr(MAW, "render_session",
                        lambda s, **kw: real(s, **kw) + f"\n[{env.nt.event('addressing')}] AGENT (commit):\nleaked\n")
    with pytest.raises(MAW.WorkspaceError, match="no reader of the thread is shown"):
        env.build("contract-full")
    assert not (env.ws_root / "contract-full").exists()


def test_copied_tests_may_name_paths_of_the_grading_container_only(tmp_path):
    env = _NatEnv(tmp_path)
    tests = env.td / "verifiers" / "reference_check" / "tests"
    _write(tests / "test_tmp.py", "STORE = '/tmp/tc_fixture_case/data.txt'\n")
    rec, _ = env.build("refcheck-review")
    assert rec["inputs"]["container_paths"] == ["/tmp/tc_fixture_case/data.txt"] and rec["inputs"]["tests"]["n_files"] == 2
    for bad, msg in ((str(tmp_path / "study"), "name outside paths that exist"),
                     ("/tmp/claude-fixture/x", "name a Claude session directory")):
        _write(tests / "test_tmp.py", f"STORE = '{bad}/data.txt'\n")
        with pytest.raises(MAW.WorkspaceError, match=msg):
            env.build("refcheck-review", name="r2")
        assert not (env.ws_root / "r2").exists()
    (tests / "test_tmp.py").unlink()
    (tests / "link.py").symlink_to(tests / "test_v.py")
    with pytest.raises(MAW.WorkspaceError, match="symlink"):
        env.build("refcheck-review", name="r3")


def test_controlled_roles_keep_their_manifest_on_controlled_tasks(tmp_path):
    """The natural rules leave a controlled task's workspaces as they were: the same inputs record and wrappers record."""
    study = _study(tmp_path)
    for role in MAW.ROLES:
        rec = _build(tmp_path, study, role, image="tc-env:fixture")[1]
        assert set(rec["inputs"]) == {"contract", "reference_diff", "session", "instruction_sha256", "instruction_from"}, role
        assert set(rec["wrappers"]) == {"image", "pythonpath", "pytest_args"} and set(rec["base"]) == {
            "snapshot_manifest_sha256", "commit", "n_files"}, role
        assert MAW.role_for(role, Population.fixture) == MAW.ROLES[role]


def test_command_line_natural_roles(tmp_path, capsys):
    env = _NatEnv(tmp_path)
    args = [str(env.td), "--role", "reviser-initial", "--root", str(env.ws_root), "--name", "rev", "--repo-root",
            str(env.nt.root), "--sealed", str(env.sealed), "--image", NAT_IMAGE, "--no-smoke", "--tests-from",
            str(env.td / "verifiers" / "initial_audited" / "tests"), "--dev-candidates",
            *(env.cid(k) for k in REVISER_DEV["initial_only"])]
    assert MAW.main(args) == 0  # no --snapshots: data/natural/snapshots, from the task's provenance
    out = json.loads(capsys.readouterr().out)
    assert out["workspace"] == str(env.ws_root / "rev") and set(out["inputs"]["dev_candidates"]) == {
        env.cid(k) for k in REVISER_DEV["initial_only"]}
    assert MAW.main([*args[:6], "rev2", *args[7:-4], env.cid("pre-review")]) == 1
    assert "held-out candidate" in capsys.readouterr().err
    checker = [str(env.td), "--role", "checker", "--root", str(env.ws_root), "--name", "chk", "--repo-root", str(env.nt.root),
               "--sealed", str(env.sealed), "--candidates", *(env.cid(k) for k in CHECKED)]
    assert MAW.main(checker) == 0
    out = json.loads(capsys.readouterr().out)
    labels = out.pop("candidate_labels")  # printed for the host; the workspace's manifest does not hold it
    assert sorted(labels.values()) == sorted(env.cid(k) for k in CHECKED) and set(labels) == set(out["inputs"]["candidates"])
    assert out == {"workspace": str(env.ws_root / "chk"), **json.loads((env.ws_root / "chk" / "manifest.json").read_text())}


def test_a_later_workspace_may_hold_what_an_earlier_agent_copied_of_its_own_inputs(tmp_path):
    """Workspaces are built phase by phase, after earlier agents ran: an agent's copy of a file it was given (anywhere in
    its workspace) is not its work, so a workspace built later may be given the same file; the agent's work stays
    forbidden material."""
    env = _NatEnv(tmp_path)
    _, tg = env.build("testgen-initial")
    shutil.copy(tg / "reference.diff", tg / "scratch" / "ref.diff")
    shutil.copy(tg / "contract.json", tg / "repo" / "contract-copy.json")
    _, rv = env.build("reviser-initial")
    assert (rv / "reference.diff").read_bytes() == (tg / "scratch" / "ref.diff").read_bytes()
    assert (rv / "contract.json").read_bytes() == (tg / "repo" / "contract-copy.json").read_bytes()
    own = _w(tg / "scratch" / "own.md", "MARK-AGENT: the generator's own notes\n")
    with pytest.raises(MAW.WorkspaceError, match=r"equals forbidden material \(.*/testgen-initial/scratch/own\.md"):
        env.build("fresh", name="x", instruction=own)


# --------------------------------------------------------------------------- review of the natural roles (WP-C findings)

def test_the_natural_near_miss_wrapper_restriction_is_not_claimed_as_enforced():
    """run_python.sh runs any Python in the image (it execs ``python "$@"``), so ``run_python.sh -m pytest`` runs the
    repository's tests: a run_python.sh-only workspace offers no test runner but prevents nothing, and the documentation
    says so and leaves the showing to the audit of the transcript."""
    from tracecontract.controlled import RUN_PYTHON_SH

    assert RUN_PYTHON_SH.rstrip().endswith('python "$@"')
    doc = " ".join((MAW.__doc__ or "").split())
    assert "do not run the repository's tests" not in doc
    assert "This is not enforced: ``run_python.sh -m pytest`` runs the repository's tests on the agent's state" in doc
    assert "it prevents nothing" in doc and "the audit of its transcript" in doc
    note = MAW.ROLES["near-miss"].note
    assert "not enforced" in note and "pytest" in note and "audit" in note


def test_an_instruction_that_names_or_holds_an_agent_only_event_is_refused(tmp_path, monkeypatch):
    """The texts no reader is shown (the PR body, the commit messages) are checked in every text written, the
    --instruction file included, and for every role of a natural task (the fresh role reads no session for its inputs):
    their event ids, and their texts (whole, or a line of MIN_LEAK characters or more) in a prose text. Short generic
    lines and what the thread shows do not count."""
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    nt = env.nt
    text = {e.event_id: e.text for e in session_for_task(env.td, nt.root).events}
    reviewed = text[nt.event("reviewed")]  # a commit message on two lines
    scenario = f"[{nt.event('addressing')}] and [{nt.event('pr')}]:\n\n{PR_TEXT}\n"  # ids and the whole PR body
    cases = [("contract-full", f"See [{nt.event('reviewed')}] first.\n", "names events that no reader of the thread is shown"),
             ("testgen-initial", f"Read {nt.event('pr')}.\n", "names events that no reader"),
             ("contract-full", scenario, "names events that no reader"),
             ("testgen-initial", scenario, "holds the text of events that no reader"),
             ("fresh", PR_TEXT + "\n", "holds the text of events that no reader"),
             ("contract-initial", f"Context: {reviewed}\n", "holds the text"),  # the whole commit message
             ("testgen-full", "Background.\n" + PR_TEXT.splitlines()[-1] + "\n", "holds the text")]  # one long line
    for k, (role, instruction, msg) in enumerate(cases):
        with pytest.raises(E, match=msg):
            env.build(role, name="w", instruction=_w(tmp_path / "instr" / f"{k}.md", instruction))
        assert not (env.ws_root / "w").exists(), (role, instruction)
    with pytest.raises(E, match=f"instruction.md holds the text of events .*{nt.event('pr')}"):
        env.build("contract-full", name="w", instruction=_w(tmp_path / "instr" / "s.md", scenario))
    assert "\n" in reviewed and len(" ".join(reviewed.split())) >= MAW.MIN_LEAK
    # what the thread shows, and an agent-only line too short to be distinctive, are no leak
    first_commit = text[nt.event("first")].splitlines()[0]
    assert len(first_commit) < MAW.MIN_LEAK
    rec, _ = env.build("contract-full", name="ok", instruction=_w(tmp_path / "instr" / "ok.md",
                                                                 f"{ISSUE_TEXT}\n\n{COMMENT_TEXT}\n\n{first_commit}\n"))
    assert rec["inputs"]["instruction_from"] == "file"
    # a session record that would carry an agent-only text (JSON-escaped, with no id) is refused too
    from tracecontract import tasks

    real = tasks.render_session_events

    def leaky(session, variant):
        data = json.loads(real(session, variant))
        data["events"][0]["text"] += '\n"' + PR_TEXT + '"'
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    monkeypatch.setattr(tasks, "render_session_events", leaky)
    with pytest.raises(E, match="session_events.json holds the text of events"):
        env.build("contract-full", name="w2")
    assert not (env.ws_root / "w2").exists()


def test_sibling_groups_and_task_roots_are_scanned_whatever_else_exists(tmp_path):
    """The agent work beside a group root is forbidden material even when the group's parent holds groups only (no plain
    workspace), and so is the agent work in a sibling task root beside a task root; a directory beside the root that
    holds no workspace (the host's instruction files) is not part of the workspace tree."""
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    _, a1 = env.build("attack-initial", name="a1", root=env.ws_root / "attack-initial")
    assert [p.name for p in env.ws_root.iterdir()] == ["attack-initial"]  # groups only
    work = _w(a1 / "scratch" / "attack.py", "# MARK-AGENT: the attack agent's own work\n")
    loose = _w(env.ws_root / "attack-initial" / "plan.md", "MARK-AGENT: the attack agent's plan beside its states\n")
    for f, where in ((work, "attack-initial/a1/scratch/attack.py"), (loose, "attack-initial/plan.md")):
        with pytest.raises(E, match=rf"equals forbidden material \(.*/{where}"):
            env.build("attack-full", name="b1", root=env.ws_root / "attack-full", instruction=f)
        assert not (env.ws_root / "attack-full").exists()  # and the group directory it made is gone again
    other_task = tmp_path / "nat_ws" / "NP-91"  # a sibling task root (any workspace there is another agent's)
    _, o = env.build("testgen-initial", name="testgen-initial", root=other_task)
    theirs = _w(o / "tests" / "test_theirs.py", "# MARK-AGENT: another family's generator\n")
    with pytest.raises(E, match=r"equals forbidden material \(.*/NP-91/testgen-initial/tests/test_theirs\.py"):
        env.build("fresh", name="x", instruction=theirs)
    host = _w(tmp_path / "nat_ws" / "instructions" / "fresh.md", "Treat a missing value as zero, please.\n")
    rec, _ = env.build("fresh", name="x", instruction=host)
    assert rec["inputs"]["instruction_from"] == "file"


def test_copies_may_name_existing_paths_only_with_the_override(tmp_path):
    """A generator that wrote its own workspace's path into a test does not stall the reviser builds: with
    --allow-existing-paths-in-copies the copies are kept byte for byte and the existing paths listed. Paths in or around
    the repository, the third-party data or a Claude session directory are never kept."""
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    _, tg = env.build("testgen-initial")
    tests = env.td / "verifiers" / "reference_check" / "tests"
    own = tg / "repo" / "fxnat" / "mod.py"
    _write(tests / "test_path.py", f"# checked against {own}\n")
    with pytest.raises(E, match="name outside paths that exist") as refused:
        env.build("refcheck-review", name="r1")
    assert not (env.ws_root / "r1").exists()
    rec, ws = env.build("refcheck-review", name="r2", allow_existing_paths_in_copies=True)
    assert rec["inputs"]["existing_container_paths"] == [str(own)] and rec["inputs"]["container_paths"] == [str(own)]
    assert (ws / "tests" / "test_path.py").read_bytes() == (tests / "test_path.py").read_bytes()
    assert "--allow-existing-paths-in-copies keeps such paths" in str(refused.value)  # the refusal names the way on
    ext = tmp_path / "ext"
    _write(ext / "repo.git" / "HEAD", "ref\n")
    for bad, msg in ((env.td / "task.json", "keeps none of these"), (ext / "repo.git" / "HEAD", "keeps none of these"),
                     (Path("/tmp/claude-fixture/x/y.txt"), "Claude session directory")):
        _write(tests / "test_path.py", f"# see {bad}\n")
        with pytest.raises(E, match=msg):
            env.build("refcheck-review", name="r3", allow_existing_paths_in_copies=True, external=(ext,))
        assert not (env.ws_root / "r3").exists()
    (tests / "test_path.py").unlink()


def test_a_refused_build_removes_the_directories_it_created(tmp_path):
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    env.build("testgen-initial")
    doc = env.nt.root / "docs" / "decision_log.md"  # forbidden material: refused after the workspace was built
    with pytest.raises(E, match="equals forbidden material"):
        env.build("fresh", name="x", root=env.ws_root / "attack-new" / "deeper", instruction=doc)
    assert not (env.ws_root / "attack-new").exists() and (env.ws_root / "testgen-initial").is_dir()
    (env.ws_root / "kept").mkdir()  # a directory that existed before the build stays
    with pytest.raises(E, match="equals forbidden material"):
        env.build("fresh", name="x", root=env.ws_root / "kept", instruction=doc)
    assert (env.ws_root / "kept").is_dir() and not any((env.ws_root / "kept").iterdir())
    fresh_root = tmp_path / "elsewhere" / "ws"  # nothing existed: everything made is removed again
    with pytest.raises(E, match="equals forbidden material"):
        env.build("fresh", name="x", root=fresh_root, instruction=doc)
    assert not (tmp_path / "elsewhere").exists()


def test_a_reviser_sees_exactly_the_audit_set_of_its_variant(tmp_path, monkeypatch, capsys):
    """Whatever a development candidate's origin, a reviser of a variant may see it only if the audit set v1:<variant>
    holds it, and the audit set is the one ``tracecontract audit --audit-set`` grades."""
    import argparse
    from types import SimpleNamespace

    from tracecontract import audit, cli

    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    patch = load(env.td / "candidates" / f"{env.cid('dev-attack-full_session-a1')}.json", Candidate).patch
    nm = Candidate(candidate_id=env.cid("dev-nm-full_session"), task_id=env.nt.task_id, origin=CandidateOrigin.constructed_near_miss,
                   split=Split.dev, patch=patch, patch_sha256=sha256_text(patch), produced_by="nearmiss:v1:full_session:dev")
    dump(nm, env.td / "candidates" / f"{nm.candidate_id}.json")
    m = load(env.td / "task.json", TaskManifest)
    dump(m.model_copy(update={"candidates": [*m.candidates, f"candidates/{nm.candidate_id}.json"]}), env.td / "task.json")
    with pytest.raises(E, match="not built for the initial_only contract.*audit set v1:initial_only"):
        env.build("reviser-initial", name="w", dev_candidates=(env.cid("reference"), nm.candidate_id))
    assert not (env.ws_root / "w").exists()
    rec, _ = env.build("reviser-full", name="ok", dev_candidates=(env.cid("reference"), nm.candidate_id))
    assert set(rec["inputs"]["dev_candidates"]) == {env.cid("reference"), nm.candidate_id}
    seen: list[str] = []

    def fake_audit(spec, contract, dev, grade, **kw):
        seen[:] = [c.candidate_id for c in dev]
        return SimpleNamespace(passed=True, findings=[], runs=0)

    monkeypatch.setattr(cli, "_grader", lambda *a, **k: None)
    monkeypatch.setattr(audit, "run_audit", fake_audit)
    m = load(env.td / "task.json", TaskManifest)
    dev = [c for c in (load(env.td / p, Candidate) for p in m.candidates) if c.split == Split.dev]
    for variant in ("initial_only", "full_session"):
        cli.cmd_audit(argparse.Namespace(task=str(env.td), verifier_id="repo_tests", contract=None, only=None,
                                         audit_set=f"v1:{variant}", record=None))
        capsys.readouterr()
        accepted = []
        for c in dev:
            try:
                MAW.candidate_patches(env.td, m, (c.candidate_id,), "dev", variant)
                accepted.append(c.candidate_id)
            except E:
                pass
        assert sorted(accepted) == sorted(seen) and len(seen) >= 3, variant
        assert (nm.candidate_id in seen) == (variant == "full_session")


def test_run_python_only_narrows_the_wrappers(tmp_path):
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    rec, ws = env.build("testgen-initial", run_python_only=True)
    fmt = {"root": str(ws), "repo": str(ws / "repo"), "image": NAT_IMAGE, "pythonpath": "/repo", "extra": ""}
    assert not (ws / "run_tests.sh").exists() and MAW.check_wrappers(ws, fmt, ("run_python.sh",)) == []
    assert rec["wrappers"]["scripts"] == ["run_python.sh"] and _nat_files(ws) == env.expected_files("testgen-initial") - {
        "run_tests.sh"}
    with pytest.raises(E, match="--run-python-only"):
        env.build("testgen-initial", name="w", image=None, run_python_only=True)
    old, u1, u2 = _old_session(tmp_path)
    study = _study(tmp_path / "c", u1=u1, u2=u2, old_checkout=f"{old}/calc")
    with pytest.raises(E, match="--run-python-only"):  # the fresh instruction names both wrappers
        _mk(tmp_path, study, name="v", variant="u1", image="tc-env:fixture", run_python_only=True)
    rec = _mk(tmp_path, study, name="f", image="tc-env:fixture", run_python_only=True)
    assert rec["wrappers"]["scripts"] == ["run_python.sh"]
    assert not (tmp_path / "workspaces" / "v").exists()


def test_no_workspace_of_a_natural_task_names_a_held_out_candidate(tmp_path):
    """A held-out id (an eval candidate of the task) is refused in any text of a natural task's workspace, the host's
    instruction included; the checker's patches carry neutral labels. Controlled tasks build as before."""
    env = _NatEnv(tmp_path)
    E = MAW.WorkspaceError
    for k, (role, cid) in enumerate((("testgen-initial", "eval-nm-1"), ("contract-full", "pre-review"), ("fresh", "eval-alt-1"))):
        with pytest.raises(E, match=f"instruction.md names held-out candidates of NP-90: \\['{env.cid(cid)}'\\]"):
            env.build(role, name="w", instruction=_w(tmp_path / "instr" / f"{k}.md", f"Never read {env.cid(cid)}.\n"))
        assert not (env.ws_root / "w").exists()
    _, ws = env.build("checker")
    assert not [i for i in env.heldout_ids() if i in _nat_text(ws) or any(i in f for f in _nat_files(ws))]
    repo, td, sealed, instr = _study(tmp_path / "c")
    _write(instr, "Do not read FX-02-eval-alt-1.\n")  # a controlled task: no such check, as before
    assert MAW.make_workspace(td, tmp_path / "c" / "ws", role="fresh", name="f", repo_root=repo, sealed=(sealed,),
                              instruction=instr)["role"] == "fresh"
