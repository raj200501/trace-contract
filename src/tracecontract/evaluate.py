"""Evaluation matrix: every applicable verifier x every evaluation candidate.

Each run writes to ``results/runs/<run_id>/``:

* ``manifest.json`` - run id, timestamps, code revision, image ids, verifier
  content hashes, candidate patch hashes, configuration;
* ``results.jsonl`` - one :class:`VerificationResult` per (verifier, candidate).

Runs are append-only. Re-running with the same run id resumes (completed pairs are
skipped); a changed frozen verifier aborts the run (bump the version instead).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .sandbox.docker_runner import Limits, build_env_image, verify_candidate
from .schemas import Candidate, Split, TaskManifest, VerificationResult, VerifierSpec
from .store import append_jsonl, load, read_jsonl, write_json
from .verifier import check_frozen


def code_revision(repo_root: Path) -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root, capture_output=True, text=True).stdout.strip()
        return rev + ("+dirty" if dirty else "")
    except subprocess.CalledProcessError:
        return "unknown"


def load_task(task_dir: Path) -> tuple[TaskManifest, list[VerifierSpec], list[Candidate]]:
    m = load(task_dir / "task.json", TaskManifest)
    specs = [load(task_dir / p, VerifierSpec) for p in m.verifiers]
    cands = [load(task_dir / p, Candidate) for p in m.candidates]
    return m, specs, cands


def run_matrix(task_dirs: list[Path], *, run_id: str, out_root: Path, cache_dir: Path, snapshot_root: Path,
               split: Split = Split.eval, conditions: list[str] | None = None, repeats: int = 1,
               limits: Limits | None = None, require_frozen: bool = True, repo_root: Path | None = None) -> Path:
    out = out_root / run_id
    out.mkdir(parents=True, exist_ok=True)
    res_path = out / "results.jsonl"
    done = {(r.verifier_id, r.candidate_id) for r in read_jsonl(res_path, VerificationResult)}
    import json as _json

    prior = _json.loads((out / "manifest.json").read_text()) if (out / "manifest.json").exists() else None
    manifest = {
        "run_id": run_id,
        "started_at": prior["started_at"] if prior else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_revision": code_revision(repo_root or Path.cwd()),
        "split": split.value,
        "repeats": repeats,
        "conditions": conditions,
        "limits": (limits or Limits()).__dict__,
        "tasks": [t for t in (prior or {}).get("tasks", []) if t["task_id"] not in {d.name for d in task_dirs}],
        "invocations": (prior or {}).get("invocations", []) + [{"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                               "tasks": [d.name for d in task_dirs],
                                                               "code_revision": code_revision(repo_root or Path.cwd())}],
    }
    for td in task_dirs:
        m, specs, cands = load_task(td)
        base = snapshot_root / m.task_id
        if not base.is_dir():
            raise FileNotFoundError(f"snapshot for {m.task_id} not built at {base} (run `tracecontract snapshot`)")
        tag, image_id = build_env_image(m.env_requirements, cache_dir)
        entry = {"task_id": m.task_id, "family_id": m.family_id, "image": tag, "image_id": image_id,
                 "verifiers": {}, "candidates": {}}
        for s in specs:
            if conditions and s.condition.value not in conditions:
                continue
            if require_frozen and not s.frozen:
                raise ValueError(f"{s.verifier_id} is not frozen; freeze verifiers before final evaluation")
            check_frozen(s, td)
            entry["verifiers"][s.verifier_id] = {"condition": s.condition.value, "content_sha256": s.content_sha256, "version": s.version}
        eval_cands = [c for c in cands if c.split == split]
        for c in eval_cands:
            entry["candidates"][c.candidate_id] = {"origin": c.origin.value, "patch_sha256": c.patch_sha256}
        manifest["tasks"].append(entry)
        write_json(manifest, out / "manifest.json")
        for s in specs:
            if s.verifier_id not in entry["verifiers"]:
                continue
            for c in eval_cands:
                if (s.verifier_id, c.candidate_id) in done:
                    continue
                res = verify_candidate(
                    image=tag, base_dir=base, spec=s, task_dir=td, candidate=c, run_id=run_id, repeats=repeats,
                    candidate_pythonpath=m.candidate_pythonpath, repo_test_args=m.repo_test_args, limits=limits,
                )
                append_jsonl(res, res_path)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(manifest, out / "manifest.json")
    return out
