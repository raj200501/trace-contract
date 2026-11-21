"""Propose labels for evaluation candidates (automated pilot only).

For each evaluation candidate of a task, or with ``--stratum NAME`` of one of its candidate
strata (``tasks/<id>/strata/<name>.json``):

1. grade it with the independent ``reference_check`` verifier (written from the
   reference contract, validated only on the reference solution and the no-op);
2. run the base repository's own tests (regression norm): a test that passes on the
   reference but fails on the candidate is a regression;
3. combine with the construction intent recorded when the candidate was built.

Decision rule (pre-specified, docs/decision_log.md D19; :func:`d19`):
* construction says valid  + reference checks pass + no regression   -> valid
* construction says invalid + reference checks fail a check mapped to a
  violated requirement (a failing regression check alone is not enough) -> invalid
* natural candidates (no construction label, or an origin in ``schemas.NATURAL_ORIGINS``:
  observed states, fresh attempts and natural pre-review states, which are never labeled by
  construction intent; protocol v0.7 §15.4, v0.8 §16.3): invalid if any reference check or
  regression fails (violated = requirements of failing checks), else valid. A natural
  pre-review state that passes the reference checks is ambiguous instead: the correction is
  not observable by the checks (protocol §15.6)
* any disagreement                                                    -> ambiguous
  (excluded from FA/FR, queued for human review)
* a missing decision                                                  -> ambiguous
  (the reference checks give no outcome but pass or task failure; or the regression norm
  gives none and names no failing check, e.g. a timeout of the repository tests, while
  the reference checks pass: "no regression" is then not known)

The reference checks must be the frozen ones: a frozen spec whose test files or check list
changed since it was frozen is refused before anything is graded or written.

Proposed labels are appended with ``labeler_kind = model``; they never replace or
hide human labels, and nothing here writes ``task.json``. A task's own candidates get
their labels in their files under ``candidates/`` and the log in
``labels/proposed_labels.json``; the base test paths rebuild ``labels/base_tests_overlay``.
A stratum's candidates get their labels in their files under
``strata/<name>/candidates/`` and the log in ``strata/<name>/proposed_labels.json``; their
regression norm is the task's recorded overlay, read and never rewritten, so base test
paths are refused with ``--stratum`` and nothing under ``labels/`` is written.

Usage: python scripts/propose_labels.py tasks/CS-01 [base test paths...]
       python scripts/propose_labels.py tasks/CS-01 --stratum fresh-v1
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from tracecontract.cli import CACHE, SNAPSHOTS
from tracecontract.sandbox.docker_runner import aggregate, build_env_image, prepare_workspace, run_grader, verify_candidate
from tracecontract.schemas import (
    NATURAL_ORIGINS, Candidate, CandidateOrigin, CheckSpec, Isolation, Label, LabelerKind, Outcome, Split, TaskManifest,
    VerifierCondition, VerifierSpec,
)
from tracecontract.store import dump, load, write_json
from tracecontract.strata import load_stratum
from tracecontract.verifier import check_frozen

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


def d19(origin: CandidateOrigin, construction: Label | None, *, infra: bool, rc_ok: bool, violated_rc: list[str],
        reg_fail: list[str], reg_infra: bool = False) -> tuple[str, list[str], str]:
    """D19's proposal for one candidate: ``(value, violated requirements, why)`` (rule in the module docstring).

    ``infra``: the reference checks gave no decision; ``rc_ok``: they all passed; ``violated_rc``: the
    requirements of the failing reference checks; ``reg_fail``: the failing regression-norm checks;
    ``reg_infra``: the regression norm gave no decision (no pass, no task failure) and names no failing
    check, so whether a regression holds is not known. A missing decision makes the label ambiguous
    wherever it is needed: a candidate whose reference checks fail is invalid without it.
    """
    regression = ["REGRESSION"] if reg_fail else []
    if infra:
        return "ambiguous", [], "reference checks did not produce a decision"
    undecided = rc_ok and reg_infra and not reg_fail  # "no regression" would be needed, and is not known
    if construction is None or origin in NATURAL_ORIGINS:  # a natural candidate: never by construction intent
        if rc_ok and origin == CandidateOrigin.natural_pre_review:
            return ("ambiguous", regression, "natural pre-review state passes the reference checks: the correction is not "
                    "observable by the checks")
        if undecided:
            return "ambiguous", [], "natural candidate passes reference checks; the regression norm did not produce a decision"
        if rc_ok and not reg_fail:
            return "valid", [], "natural candidate passes reference checks and regression norm"
        return "invalid", violated_rc + regression, "natural candidate fails reference checks and/or regression norm"
    if construction.value == "valid":
        if undecided:
            return "ambiguous", [], "construction valid, reference checks pass; the regression norm did not produce a decision"
        if rc_ok and not reg_fail:
            return "valid", [], "construction valid, confirmed by reference checks and regression norm"
        return "ambiguous", violated_rc + regression, "construction valid but checks fail"
    target = set(construction.violated_requirements)
    hit = bool(target & set(violated_rc)) or (bool(reg_fail) and "REGRESSION" in target)
    if not rc_ok and hit:
        return "invalid", sorted(target | set(violated_rc)), "construction invalid, confirmed on targeted requirement"
    if not rc_ok or reg_fail:
        return "ambiguous", violated_rc + regression, "construction invalid but failing checks map to other requirements"
    if undecided:
        return "ambiguous", [], "construction invalid, reference checks pass; the regression norm did not produce a decision"
    return "ambiguous", [], "construction invalid but reference checks and regression norm pass"


def main(task_dir: str, *base_test_paths: str, stratum: str | None = None) -> None:
    tdir = Path(task_dir).resolve()
    m = load(tdir / "task.json", TaskManifest)
    if stratum is not None and base_test_paths:
        raise SystemExit("with --stratum the regression norm is the task's recorded base-test overlay "
                         "(labels/base_tests_overlay, read only); base test paths are not accepted")
    own = {load(tdir / p, Candidate).candidate_id: (p, load(tdir / p, Candidate)) for p in m.candidates}
    ref = next(c for _, c in own.values() if c.origin == CandidateOrigin.reference)
    if stratum is not None:  # checked (paths, ids, no links) before anything is graded or written
        cands = {c.candidate_id: (rel, c) for rel, c in load_stratum(tdir, stratum, m.task_id).candidates}
    else:
        cands = own
    refcheck = load(tdir / "verifiers" / "reference_check" / "spec.json", VerifierSpec)
    try:  # the frozen reference checks, unchanged since freezing; checked before anything is built, graded or written
        check_frozen(refcheck, tdir)
    except ValueError as exc:
        raise SystemExit(f"propose_labels refused: {exc}") from None
    tag, _ = build_env_image(m.env_requirements, CACHE / "images")
    base = SNAPSHOTS / m.task_id
    # Base-test overlay (the repository's own tests at the BASE commit).
    overlay = tdir / "labels" / "base_tests_overlay"
    if stratum is None:
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
    use_overlay = bool(base_test_paths) if stratum is None else overlay.is_dir()
    reg_spec = regression_spec(tdir, m, overlay, tag, ref) if use_overlay else None
    req_of = {c.check_id: c.requirement_ids for c in refcheck.checks}
    log = {"task_id": m.task_id, "labeler": LABELER, "created_at": now(), "candidates": {}}
    if stratum is not None:
        log.update(stratum=stratum, regression_overlay="labels/base_tests_overlay" if reg_spec else None)
    for cid, (rel, c) in sorted(cands.items()):
        if c.split != Split.eval or c.origin == CandidateOrigin.noop:
            continue
        rc = verify_candidate(image=tag, base_dir=base, spec=refcheck, task_dir=tdir, candidate=c, run_id="labels",
                              candidate_pythonpath=m.candidate_pythonpath)
        failed_rc = [k.check_id for k in rc.checks if k.status != "passed"]
        violated_rc = sorted({r for f in failed_rc for r in req_of.get(f, [])})
        reg_fail = []
        reg_infra = False
        if reg_spec is not None:
            rr = verify_candidate(image=tag, base_dir=base, spec=reg_spec, task_dir=tdir, candidate=c, run_id="labels",
                                  candidate_pythonpath=m.candidate_pythonpath, repo_test_args=m.repo_test_args)
            reg_fail = [k.check_id for k in rr.checks if k.status != "passed"]
            reg_outcome = rr.outcome.value
            # No decision: e.g. a timeout or an environment failure, which records no check at all.
            reg_infra = rr.outcome not in (Outcome.passed, Outcome.task_failure) and not reg_fail
        else:
            reg_outcome = "not run"
        construction = next((lb for lb in c.labels if lb.labeler_kind == LabelerKind.construction), None)
        rc_ok = rc.outcome == Outcome.passed
        infra = rc.outcome not in (Outcome.passed, Outcome.task_failure)
        note = {"refcheck_outcome": rc.outcome.value, "refcheck_failed": failed_rc[:20], "regression_outcome": reg_outcome,
                "regression_failed": reg_fail[:20], "construction": construction.model_dump(mode="json") if construction else None}
        value, violated, why = d19(c.origin, construction, infra=infra, rc_ok=rc_ok, violated_rc=violated_rc, reg_fail=reg_fail,
                                   reg_infra=reg_infra)
        lab = Label(value=value, violated_requirements=violated, labeler=LABELER, labeler_kind=LabelerKind.model,
                    timestamp=now(), note=why + " | " + json.dumps(note)[:3000])
        c2 = c.model_copy(update={"labels": [lb for lb in c.labels if lb.labeler != LABELER] + [lab]})
        dump(c2, tdir / rel)  # a stratum candidate stays in its stratum's file (rel is strata/<name>/candidates/...)
        log["candidates"][cid] = {"origin": c.origin.value, "proposed": value, "violated": violated, "why": why, **note}
        print(f"{cid:38s} {c.origin.value:24s} -> {value:9s} {violated} ({why})")
    log_path = tdir / "labels" / "proposed_labels.json" if stratum is None else tdir / "strata" / stratum / "proposed_labels.json"
    if log_path.is_symlink():
        raise SystemExit(f"{log_path} is a symbolic link; the label log is not written through it")
    write_json(log, log_path)


def cli(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("task_dir")
    ap.add_argument("base_test_paths", nargs="*", help="the base commit's test files or directories (the regression norm)")
    ap.add_argument("--stratum", metavar="NAME", help="label the candidates of this candidate stratum instead of the task's own")
    a = ap.parse_args(argv)
    main(a.task_dir, *a.base_test_paths, stratum=a.stratum)


if __name__ == "__main__":
    cli()
