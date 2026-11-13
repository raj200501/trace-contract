"""Propose labels for evaluation candidates (automated pilot only).

For each evaluation candidate of a task:

1. grade it with the independent ``reference_check`` verifier (written from the
   reference contract, validated only on the reference solution and the no-op);
2. run the base repository's own tests (regression norm): a test that passes on the
   reference but fails on the candidate is a regression;
3. combine with the construction intent recorded when the candidate was built.

Decision rule (pre-specified, docs/decision_log.md D19):
* construction says valid  + reference checks pass + no regression   -> valid
* construction says invalid + reference checks fail a check mapped to a
  violated requirement (or the regression check fails)               -> invalid
* naturally observed candidates (no construction label): invalid if any reference
  check or regression fails (violated = requirements of failing checks), else valid
* any disagreement                                                    -> ambiguous
  (excluded from FA/FR, queued for human review)

Proposed labels are appended with ``labeler_kind = model``; they never replace or
hide human labels. Usage: python scripts/propose_labels.py tasks/CS-01 [base test paths...]
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from tracecontract.cli import CACHE, SNAPSHOTS
from tracecontract.sandbox.docker_runner import aggregate, build_env_image, prepare_workspace, run_grader, verify_candidate
from tracecontract.schemas import (
    Candidate, CandidateOrigin, CheckSpec, Isolation, Label, LabelerKind, Outcome, Split, TaskManifest, VerifierCondition,
    VerifierSpec,
)
from tracecontract.store import dump, load, write_json

LABELER = "builder:refcheck+regression+construction:v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def regression_spec(tdir: Path, m: TaskManifest, overlay: Path, tag: str, ref: Candidate) -> VerifierSpec:
    """In-process spec over the BASE repository tests that pass on the reference."""
    ws, diags, err = prepare_workspace(SNAPSHOTS / m.task_id, ref.patch)
    assert ws is not None, diags
    raw, nonce = run_grader(tag, workspace=ws, mode=Isolation.in_process, overlay_dir=overlay,
                            repo_test_args=m.repo_test_args, candidate_pythonpath=m.candidate_pythonpath)
    shutil.rmtree(ws, ignore_errors=True)
    r = raw.results or {}
    assert r.get("nonce") == nonce and r.get("status") == "completed", r
    passing = sorted(t["nodeid"] for t in r.get("tests", []) if t["outcome"] == "passed")
    return VerifierSpec(verifier_id="regression_norm", task_id=m.task_id, condition=VerifierCondition.reference_check,
                        isolation=Isolation.in_process, test_dir=str(overlay.relative_to(tdir)),
                        checks=[CheckSpec(check_id=c) for c in passing], content_sha256="base-tests")


def main(task_dir: str, *base_test_paths: str) -> None:
    tdir = Path(task_dir).resolve()
    m = load(tdir / "task.json", TaskManifest)
    tag, _ = build_env_image(m.env_requirements, CACHE / "images")
    base = SNAPSHOTS / m.task_id
    cands = {load(tdir / p, Candidate).candidate_id: (p, load(tdir / p, Candidate)) for p in m.candidates}
    ref = next(c for _, c in cands.values() if c.origin == CandidateOrigin.reference)
    refcheck = load(tdir / "verifiers" / "reference_check" / "spec.json", VerifierSpec)
    # Base-test overlay (the repository's own tests at the BASE commit).
    overlay = tdir / "labels" / "base_tests_overlay"
    if overlay.exists():
        shutil.rmtree(overlay)
    for tp in base_test_paths:
        src = base / tp
        dst = overlay / tp
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    reg_spec = regression_spec(tdir, m, overlay, tag, ref) if base_test_paths else None
    req_of = {c.check_id: c.requirement_ids for c in refcheck.checks}
    log = {"task_id": m.task_id, "labeler": LABELER, "created_at": now(), "candidates": {}}
    for cid, (rel, c) in sorted(cands.items()):
        if c.split != Split.eval or c.origin == CandidateOrigin.noop:
            continue
        rc = verify_candidate(image=tag, base_dir=base, spec=refcheck, task_dir=tdir, candidate=c, run_id="labels",
                              candidate_pythonpath=m.candidate_pythonpath)
        failed_rc = [k.check_id for k in rc.checks if k.status != "passed"]
        violated_rc = sorted({r for f in failed_rc for r in req_of.get(f, [])})
        reg_fail = []
        if reg_spec is not None:
            rr = verify_candidate(image=tag, base_dir=base, spec=reg_spec, task_dir=tdir, candidate=c, run_id="labels",
                                  candidate_pythonpath=m.candidate_pythonpath, repo_test_args=m.repo_test_args)
            reg_fail = [k.check_id for k in rr.checks if k.status != "passed"]
            reg_outcome = rr.outcome.value
        else:
            reg_outcome = "not run"
        construction = next((lb for lb in c.labels if lb.labeler_kind == LabelerKind.construction), None)
        rc_ok = rc.outcome == Outcome.passed
        infra = rc.outcome not in (Outcome.passed, Outcome.task_failure)
        note = {"refcheck_outcome": rc.outcome.value, "refcheck_failed": failed_rc[:20], "regression_outcome": reg_outcome,
                "regression_failed": reg_fail[:20], "construction": construction.model_dump(mode="json") if construction else None}
        if infra:
            value, violated, why = "ambiguous", [], "reference checks did not produce a decision"
        elif construction is None:  # naturally observed
            if rc_ok and not reg_fail:
                value, violated, why = "valid", [], "natural candidate passes reference checks and regression norm"
            else:
                value = "invalid"
                violated = violated_rc + (["REGRESSION"] if reg_fail else [])
                why = "natural candidate fails reference checks and/or regression norm"
        elif construction.value == "valid":
            if rc_ok and not reg_fail:
                value, violated, why = "valid", [], "construction valid, confirmed by reference checks and regression norm"
            else:
                value, violated, why = "ambiguous", violated_rc + (["REGRESSION"] if reg_fail else []), "construction valid but checks fail"
        else:
            target = set(construction.violated_requirements)
            hit = bool(target & set(violated_rc)) or (bool(reg_fail) and "REGRESSION" in target)
            if not rc_ok and hit:
                value, violated, why = "invalid", sorted(target | set(violated_rc)), "construction invalid, confirmed on targeted requirement"
            elif not rc_ok or reg_fail:
                value, violated = "ambiguous", violated_rc + (["REGRESSION"] if reg_fail else [])
                why = "construction invalid but failing checks map to other requirements"
            else:
                value, violated, why = "ambiguous", [], "construction invalid but reference checks and regression norm pass"
        lab = Label(value=value, violated_requirements=violated, labeler=LABELER, labeler_kind=LabelerKind.model,
                    timestamp=now(), note=why + " | " + json.dumps(note)[:3000])
        c2 = c.model_copy(update={"labels": [lb for lb in c.labels if lb.labeler != LABELER] + [lab]})
        dump(c2, tdir / rel)
        log["candidates"][cid] = {"origin": c.origin.value, "proposed": value, "violated": violated, "why": why, **note}
        print(f"{cid:38s} {c.origin.value:24s} -> {value:9s} {violated} ({why})")
    write_json(log, tdir / "labels" / "proposed_labels.json")


if __name__ == "__main__":
    main(*sys.argv[1:])
