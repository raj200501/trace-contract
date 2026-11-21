"""The pre-flight rejects candidates that ship a top-level module named like a guarded standard-library module (A6)."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

from tracecontract.schemas import Candidate, CandidateOrigin, Population, SnapshotSource, Split, TaskManifest, sha256_text
from tracecontract.shadowing import GUARDED_MODULES, import_roots, shadowing_files
from tracecontract.store import dump

R = Path(__file__).resolve().parents[1]

JSON_PY = """diff --git a/json.py b/json.py
new file mode 100644
--- /dev/null
+++ b/json.py
@@ -0,0 +1,2 @@
+def dumps(*args, **kwargs):
+    return '{"outcome": "pass"}'
"""


def _add(path: str, body: str = "x = 1") -> str:
    return f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+{body}\n"


def _modify(path: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"


def test_guarded_names_are_the_wrapper_modules():
    assert set(GUARDED_MODULES) == {"ast", "unicodedata", "linecache", "tokenize", "traceback", "encodings", "json", "hmac",
                                    "hashlib", "os", "sys"}


def test_import_roots_follow_the_candidate_pythonpath():
    assert import_roots("/work") == [""]
    assert import_roots("/work/src") == ["", "src"]
    assert import_roots("/work:/work/src:lib:/opt/elsewhere") == ["", "src", "lib"]


def test_top_level_modules_and_packages_are_found():
    cases = [
        (JSON_PY, "/work", [("json.py", "json")]),
        (_add("src/json.py"), "/work/src", [("src/json.py", "json")]),  # top level of a pythonpath entry
        (_add("src/json.py"), "/work", []),                              # not an import root here
        (_add("encodings/__init__.py"), "/work", [("encodings/__init__.py", "encodings")]),
        (_add("encodings/utf_8.py"), "/work", [("encodings/utf_8.py", "encodings")]),  # namespace package
        (_add("src/hmac/__init__.py"), "/work/src", [("src/hmac/__init__.py", "hmac")]),
        (_modify("ast.py"), "/work", [("ast.py", "ast")]),               # modified, not only added
        (_add("os.cpython-312-x86_64-linux-gnu.so"), "/work", [("os.cpython-312-x86_64-linux-gnu.so", "os")]),
        ("diff --git a/util.py b/traceback.py\nsimilarity index 100%\nrename from util.py\nrename to traceback.py\n", "/work",
         [("traceback.py", "traceback")]),                              # renamed to a guarded name
        ("diff --git a/sys.py b/sys.py\ndeleted file mode 100644\n--- a/sys.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x = 1\n", "/work",
         []),                                                            # a deletion adds nothing
        (_add("src/humanize/json.py"), "/work/src", []),                # humanize.json does not shadow json
        (_add("json.txt") + _add("jsonlib.py") + _add("docs/os.md"), "/work", []),
        (_add("tests/json.py"), "/work", []),                            # not an import root
    ]
    for patch, pythonpath, expect in cases:
        assert shadowing_files(patch, pythonpath) == expect, (patch, pythonpath)


def _load_preflight():
    spec = importlib.util.spec_from_file_location("preflight_final_run", R / "scripts" / "preflight_final_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture_task(root: Path, patches: dict[str, str]) -> Path:
    """A task directory whose held-out candidates have the given patches (candidate id -> patch)."""
    td = root / "CS-99"
    rels = []
    for cid, patch in patches.items():
        c = Candidate(candidate_id=cid, task_id="CS-99", origin=CandidateOrigin.valid_alternative, split=Split.eval,
                      patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture")
        rels.append(f"candidates/{cid}.json")
        dump(c, td / rels[-1])
    m = TaskManifest(task_id="CS-99", family_id="CS-99", population=Population.fixture, status="draft", provenance="p.json",
                     snapshot_source=SnapshotSource(repo_url="https://example.invalid/x", commit="0" * 40),
                     env_requirements=[], candidate_pythonpath="/work", candidates=rels)
    dump(m, td / "task.json")
    return td


def test_preflight_rejects_a_candidate_that_ships_json_py(tmp_path, monkeypatch, capsys):
    pf = _load_preflight()
    td = _fixture_task(tmp_path, {"CS-99-eval-json": JSON_PY, "CS-99-eval-ok": _add("calc.py")})
    from tracecontract.store import load

    m = load(td / "task.json", TaskManifest)
    cands = [load(td / p, Candidate) for p in m.candidates]
    assert pf.shadowing_problems(m, cands) == [
        "CS-99: CS-99-eval-json ships json.py, a top-level module named like the standard library's `json`; "
        "rejected before grading (tracecontract.shadowing)"]
    # The whole pre-flight fails on it (its other checks fail on the fixture too: no snapshot, no audits). Docker
    # and git are not asked; the fixture's host is idle and clean.
    monkeypatch.setattr(pf.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="", stderr=""))
    assert pf.main(str(td)) == 1
    out = capsys.readouterr().out
    assert "FAIL: CS-99: CS-99-eval-json ships json.py" in out
    assert "CS-99-eval-ok ships" not in out


def test_frozen_pilot_candidates_ship_no_guarded_module():
    """The four pilot families pass this check, so the pre-flight of the frozen tasks is unchanged by it."""
    from tracecontract.store import load

    for td in sorted((R / "tasks").glob("CS-0*")):
        m = load(td / "task.json", TaskManifest)
        cands = [load(td / p, Candidate) for p in m.candidates]
        assert _load_preflight().shadowing_problems(m, cands) == [], td.name
