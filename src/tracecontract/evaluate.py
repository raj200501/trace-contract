"""Evaluation matrix: every applicable verifier x every evaluation candidate.

Each run writes to ``results/runs/<run_id>/``:

* ``manifest.json`` - run id, timestamps, code revision, image ids, verifier
  content hashes, candidate patch hashes, configuration;
* ``results.jsonl`` - one :class:`VerificationResult` per (verifier, candidate).

Runs are append-only. Re-running with the same run id resumes (completed pairs are
skipped); a changed frozen verifier aborts the run (bump the version instead).

Every task goes through the task acceptance gate (:func:`gate_tasks`) before anything
is written: a rejected task is always refused, and a task that has not been accepted
through the gate is evaluated only with ``pilot=True`` (``--pilot``), which the
manifest records together with each task's gate result.

Candidate strata (:mod:`tracecontract.strata`): ``strata=[...]`` (``--strata``) also grades
the candidates listed in ``tasks/<id>/strata/<name>.json``, and with ``only_strata``
(``--only-strata``) grades them instead of the task's own candidates; the reference solution
is graded as the sanity check either way. Strata never change ``task.json`` or the task's
candidate files. The manifest records each task's strata (file and sha256) and, for every
stratum candidate, its stratum and file (``tasks[].candidates[<id>].stratum`` and ``.path``).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .contract import task_gate
from .sandbox.docker_runner import Limits, build_env_image, verify_candidate
from .schemas import Candidate, CandidateOrigin, Snapshot, Split, TaskManifest, VerificationResult, VerifierSpec
from .store import append_jsonl, load, read_jsonl, write_json
from .strata import Stratum, StratumError, load_strata
from .verifier import check_frozen


def code_revision(repo_root: Path) -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root, capture_output=True, text=True).stdout.strip()
        return rev + ("+dirty" if dirty else "")
    except subprocess.CalledProcessError:
        return "unknown"


EXTRA_VERIFIERS = "verifiers_extra.json"


def extra_verifier_paths(task_dir: Path) -> list[str]:
    """Verifier specs registered in the task's sidecar ``verifiers_extra.json``, not in ``task.json``.

    Label-support verifiers added after a task's files were frozen (for example the
    independent labeler, protocol §15.5) are registered here, so the frozen ``task.json``
    is never changed. Evaluations include them only when asked to.
    """
    p = task_dir / EXTRA_VERIFIERS
    if not p.is_file():
        return []
    import json as _json
    data = _json.loads(p.read_text(encoding="utf-8"))
    return [str(x) for x in data.get("verifiers", [])]


def load_task(task_dir: Path, *, extra: bool = False) -> tuple[TaskManifest, list[VerifierSpec], list[Candidate]]:
    m = load(task_dir / "task.json", TaskManifest)
    paths = list(m.verifiers) + ([x for x in extra_verifier_paths(task_dir) if x not in m.verifiers] if extra else [])
    specs = [load(task_dir / p, VerifierSpec) for p in paths]
    cands = [load(task_dir / p, Candidate) for p in m.candidates]
    return m, specs, cands


class TaskRefused(ValueError):
    """The acceptance gate keeps a task out of the run (:func:`gate_tasks`)."""


def gate_tasks(task_dirs: list[Path], *, repo_root: Path, pilot: bool) -> dict[str, dict]:
    """Run the task acceptance gate on every task and return each result; raise :class:`TaskRefused` if any is refused.

    A task whose status or provenance is ``rejected`` is always refused. A task that is not
    accepted (status ``accepted`` and the gate still passing) is refused unless ``pilot``
    is set, so evaluating unaccepted tasks, as the automated pilot does, has to be asked for.
    """
    gates: dict[str, dict] = {}
    refused: list[str] = []
    for td in task_dirs:
        g = task_gate(td, repo_root)
        gates[g.task_id] = g.to_dict()
        if g.refusals:
            refused.append(f"{g.task_id}: refused ({'; '.join(g.refusals)})")
        elif not g.accepted and not pilot:
            first = g.reasons[0] if g.reasons else "the gate passes but the task was not accepted (tracecontract accept-task)"
            refused.append(f"{g.task_id}: not accepted (status {g.status!r}; {len(g.reasons)} gate reason(s), first: "
                           f"{first}); pass --pilot to evaluate it as an automated pilot")
    if refused:
        raise TaskRefused("\n".join(refused))
    return gates


def select_strata(task_dirs: list[Path], names: list[str], *, only_strata: bool = False,
                  prior: dict | None = None) -> dict[str, dict[str, Stratum]]:
    """The strata ``names`` of every task, by task id; raise :class:`StratumError` if one is missing or invalid.

    Every task must have every stratum (:func:`strata.load_strata`). In a resumed run (``prior`` is
    its manifest), a stratum candidate the run already recorded must keep its stratum and its patch,
    because its graded pairs are not graded again.
    """
    if only_strata and not names:
        raise StratumError("only_strata (--only-strata) needs at least one stratum (--strata NAME)")
    recorded = {t["task_id"]: t.get("candidates", {}) for t in (prior or {}).get("tasks", [])}
    out: dict[str, dict[str, Stratum]] = {}
    for td in task_dirs:
        m = load(td / "task.json", TaskManifest)
        if not names:
            out[m.task_id] = {}
            continue
        own = {load(td / p, Candidate).candidate_id for p in m.candidates}
        out[m.task_id] = load_strata(td, names, m.task_id, own)
        for st in out[m.task_id].values():
            for _, c in st.candidates:
                was = recorded.get(m.task_id, {}).get(c.candidate_id)
                if was is not None and (was.get("stratum"), was.get("patch_sha256")) != (st.name, c.patch_sha256):
                    raise StratumError(f"{m.task_id}: candidate {c.candidate_id} of stratum {st.name!r} is not the one this "
                                       "run recorded (another stratum or patch); use a new run id")
    return out


def run_matrix(task_dirs: list[Path], *, run_id: str, out_root: Path, cache_dir: Path, snapshot_root: Path,
               split: Split = Split.eval, conditions: list[str] | None = None, repeats: int = 1,
               limits: Limits | None = None, require_frozen: bool = True, repo_root: Path | None = None,
               include_reference: bool = True, pilot: bool = False, strata: list[str] | None = None,
               only_strata: bool = False, extra_verifiers: bool = False) -> Path:
    root = repo_root or Path.cwd()
    gates = gate_tasks(task_dirs, repo_root=root, pilot=pilot)  # before anything is written
    out = out_root / run_id
    import json as _json

    prior = _json.loads((out / "manifest.json").read_text()) if (out / "manifest.json").exists() else None
    names = list(dict.fromkeys(strata or []))
    selected = select_strata(task_dirs, names, only_strata=only_strata, prior=prior)  # before anything is written
    out.mkdir(parents=True, exist_ok=True)
    res_path = out / "results.jsonl"
    # Keyed by task as well: a stratum candidate's id is unique only within its task.
    done = {(r.task_id, r.verifier_id, r.candidate_id) for r in read_jsonl(res_path, VerificationResult)}
    invocation = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tasks": [d.name for d in task_dirs],
                  "code_revision": code_revision(root), "pilot": pilot}
    if names:
        invocation.update(strata=names, only_strata=only_strata)
    invocations = (prior or {}).get("invocations", []) + [invocation]
    prior_entries = {t["task_id"]: t for t in (prior or {}).get("tasks", [])}
    manifest = {
        "run_id": run_id,
        "started_at": prior["started_at"] if prior else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_revision": code_revision(root),
        "split": split.value,
        "repeats": repeats,
        "conditions": conditions,
        "limits": (limits or Limits()).__dict__,
        "tasks": [t for t in (prior or {}).get("tasks", []) if t["task_id"] not in {d.name for d in task_dirs}],
        "invocations": invocations,
        # Whether any invocation evaluated tasks without requiring the acceptance gate; one
        # recorded before the gate was enforced (no "pilot" key) counts as such.
        "pilot": any(inv.get("pilot", True) for inv in invocations),
    }
    if extra_verifiers:  # label-support verifiers from verifiers_extra.json were included
        manifest["extra_verifiers"] = True
    from .tasks import verify_snapshot

    # Check every task's snapshot and frozen verifiers before grading anything, so a run
    # cannot stop part-way on a missing or modified input.
    for td in task_dirs:
        m, specs, _ = load_task(td, extra=extra_verifiers)
        base = snapshot_root / m.task_id
        if not base.is_dir():
            raise FileNotFoundError(f"snapshot for {m.task_id} not built at {base} (run `tracecontract snapshot`)")
        if not verify_snapshot(td, snapshot_root):
            raise ValueError(f"snapshot for {m.task_id} at {base} does not match its recorded manifest (run `tracecontract snapshot`)")
        for s in specs:
            if conditions and s.condition.value not in conditions:
                continue
            if require_frozen and not s.frozen:
                raise ValueError(f"{s.verifier_id} is not frozen; freeze verifiers before final evaluation")
            check_frozen(s, td)
    for td in task_dirs:
        m, specs, cands = load_task(td, extra=extra_verifiers)
        base = snapshot_root / m.task_id
        snap = load(td / (m.snapshot or "snapshot.json"), Snapshot)
        tag, image_id = build_env_image(m.env_requirements, cache_dir)
        entry = {"task_id": m.task_id, "family_id": m.family_id, "image": tag, "image_id": image_id,
                 "snapshot_manifest_sha256": snap.file_manifest_sha256, "acceptance_gate": gates[m.task_id],
                 "verifiers": {}, "candidates": {}}
        for s in specs:
            if conditions and s.condition.value not in conditions:
                continue
            if require_frozen and not s.frozen:
                raise ValueError(f"{s.verifier_id} is not frozen; freeze verifiers before final evaluation")
            check_frozen(s, td)
            entry["verifiers"][s.verifier_id] = {"condition": s.condition.value, "content_sha256": s.content_sha256,
                                                 "checks_sha256": s.checks_sha256, "n_checks": len(s.checks), "version": s.version}
        # Held-out candidates of the requested split, plus the reference solution as a
        # sanity check (protocol section 5: graded by every verifier, excluded from FA/FR);
        # with only_strata the task's own candidates are left out, except the reference.
        eval_cands = [c for c in cands if (c.split == split and not only_strata)
                      or (include_reference and c.origin == CandidateOrigin.reference)]
        for c in eval_cands:
            entry["candidates"][c.candidate_id] = {"origin": c.origin.value, "patch_sha256": c.patch_sha256}
        for st in selected[m.task_id].values():
            for rel, c in st.candidates:
                if c.split == split:
                    eval_cands.append(c)
                    entry["candidates"][c.candidate_id] = {"origin": c.origin.value, "patch_sha256": c.patch_sha256,
                                                           "stratum": st.name, "path": rel}
        # Stratum candidates that an earlier invocation of this run graded stay recorded, so the
        # analysis still finds their results.
        prev = prior_entries.get(m.task_id, {})
        for cid, rec in prev.get("candidates", {}).items():
            if "stratum" in rec:
                entry["candidates"].setdefault(cid, rec)
        strata_records = {**prev.get("strata", {}), **{n: st.record() for n, st in selected[m.task_id].items()}}
        if strata_records:
            entry["strata"] = strata_records
        manifest["tasks"].append(entry)
        write_json(manifest, out / "manifest.json")
        for s in specs:
            if s.verifier_id not in entry["verifiers"]:
                continue
            for c in eval_cands:
                if (s.task_id, s.verifier_id, c.candidate_id) in done:
                    continue
                res = verify_candidate(
                    image=tag, base_dir=base, spec=s, task_dir=td, candidate=c, run_id=run_id, repeats=repeats,
                    candidate_pythonpath=m.candidate_pythonpath, repo_test_args=m.repo_test_args, limits=limits,
                    log_dir=out / "logs",
                )
                append_jsonl(res, res_path)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(manifest, out / "manifest.json")
    return out
