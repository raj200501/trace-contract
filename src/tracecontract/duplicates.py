"""Held-out candidates that duplicate a development candidate or another held-out candidate.

Two levels (decision log D37, D40):

* **same graded patch**: identical patches after removing protected test/config paths
  and git ``index`` lines (computed by the analysis from the candidate files alone);
* **same code**: different patches that leave identical files once comments and
  docstrings are ignored. Python files are compared by their syntax tree without
  docstrings; other files by text. This needs the base snapshot.

``scripts/find_duplicates.py`` writes the same-code duplicates of each task to
``<task dir>/labels/duplicates.json``. The analysis reads that file (so analysis
output does not depend on whether snapshots are present), and the preflight check
recomputes it and fails if it differs. Reading a candidate here applies its patch to a
copy of the base snapshot, which ``roots.snapshot_root`` locates (``snapshots/<id>``, or
``data/natural/snapshots/<id>`` for a natural PR-review task); no candidate code is executed.

Held-out candidates are compared in the order of :func:`representative_order`: the natural
state first (the agent's own state before the user's correction, or a natural PR-review
task's pre-review state), then by id. The first of a group of same-code candidates is its
representative, and the later ones are listed as its duplicates, so a constructed candidate
(a near miss, say) that reproduces the pre-review state is the duplicate, never the state
itself. Every held-out candidate, the pre-review state included, is also compared with the
development candidates (dev attacks and dev alternatives).
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path

from . import roots
from .patches import filter_patch, split_sections
from .schemas import Candidate, CandidateOrigin, TaskManifest
from .store import load

# Held-out origins that represent a group of same-code candidates: the natural states, before any constructed candidate.
REPRESENTATIVE_FIRST = frozenset({CandidateOrigin.observed_pre_correction, CandidateOrigin.natural_pre_review})


def representative_order(c: Candidate) -> tuple[bool, str]:
    """Sort key of the held-out candidates: :data:`REPRESENTATIVE_FIRST` origins first, then by candidate id."""
    return c.origin not in REPRESENTATIVE_FIRST, c.candidate_id


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return tree


def canonical(path: str, data: bytes | None) -> str | None:
    """File content with comments and docstrings ignored (Python), else the text itself."""
    if data is None:
        return None
    if path.endswith(".py"):
        try:
            return ast.dump(_strip_docstrings(ast.parse(data)), include_attributes=False)
        except (SyntaxError, ValueError):
            pass
    return data.decode("utf-8", errors="replace")


def changed_paths(patch: str) -> set[str]:
    """Paths the graded (filtered) patch touches."""
    graded, _ = filter_patch(patch)
    out: set[str] = set()
    for sec in split_sections(graded):
        out.update(p for p in (sec.old_path, sec.new_path) if p)
    return out


def code_signatures(base_dir: Path, cands: list[Candidate]) -> dict[str, str | None]:
    """sha256 of the canonical content of every file any candidate touches, per candidate.

    Files are taken over the union of all candidates' changed paths, so two candidates
    get the same signature exactly when they leave the same code in every one of those
    files. ``None`` when a patch is rejected or does not apply.
    """
    from .sandbox.docker_runner import prepare_workspace

    union = sorted(set().union(*(changed_paths(c.patch) for c in cands if c.patch)))
    sig: dict[str, str | None] = {}
    for c in cands:
        ws, _diags, _err = prepare_workspace(base_dir, c.patch)
        if ws is None:
            sig[c.candidate_id] = None
            continue
        try:
            items = []
            for rel in union:
                f = ws / rel
                items.append([rel, canonical(rel, f.read_bytes() if f.is_file() else None)])
            sig[c.candidate_id] = hashlib.sha256(json.dumps(items).encode("utf-8")).hexdigest()
        finally:
            shutil.rmtree(ws, ignore_errors=True)
    return sig


def same_code_duplicates(task_dir: Path, snapshot_root: Path | None = None) -> dict:
    """Held-out candidates whose code equals a development candidate's or an earlier held-out candidate's
    (:func:`representative_order`).

    Only pairs whose graded patches differ are listed (identical patches are the
    analysis's ``same graded patch`` level). ``snapshot_root``: the directory holding the
    task's base snapshot (``<root>/<task id>``); by default the one ``roots.snapshot_root``
    names for the task.
    """
    from .analysis import _norm_patch

    if snapshot_root is None:
        snapshot_root = roots.snapshot_root(task_dir)
    m = load(task_dir / "task.json", TaskManifest)
    cands = [load(task_dir / p, Candidate) for p in m.candidates]
    cands = [c for c in cands if c.patch and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]
    sig = code_signatures(snapshot_root / m.task_id, cands)
    dev = [c for c in cands if c.split.value == "dev"]
    held = sorted((c for c in cands if c.split.value == "eval"), key=representative_order)
    out: dict = {}
    seen: list[Candidate] = []
    for c in held:
        hits: dict[str, list[str]] = {}
        if sig[c.candidate_id] is not None:
            for d in dev:
                if sig[d.candidate_id] == sig[c.candidate_id] and _norm_patch(d.patch) != _norm_patch(c.patch):
                    hits.setdefault("same_code_as_dev", []).append(d.candidate_id)
            for h in seen:
                if sig[h.candidate_id] == sig[c.candidate_id] and _norm_patch(h.patch) != _norm_patch(c.patch):
                    hits.setdefault("same_code_as_heldout", []).append(h.candidate_id)
        seen.append(c)
        if hits:
            out[c.candidate_id] = hits
    return {"task_id": m.task_id, "rule": "same code apart from comments and docstrings, different graded patch",
            "snapshot_manifest_sha256": json.loads((task_dir / (m.snapshot or "snapshot.json")).read_text()).get("file_manifest_sha256"),
            "duplicates": out}
