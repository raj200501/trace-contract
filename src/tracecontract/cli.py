"""Command-line interface: ``tracecontract <command> ...``.

Commands print JSON to stdout so that they can be scripted and recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .schemas import (
    Candidate, CandidateOrigin, Isolation, Label, LabelerKind, Split, TaskContract, TaskManifest, VerifierCondition,
    VerifierSpec, sha256_text,
)
from .store import dump, load

REPO = Path(__file__).resolve().parents[2]
CACHE = Path.home() / ".cache" / "tracecontract"
SNAPSHOTS = REPO / "snapshots"


def _out(obj) -> None:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _task(task_dir: str) -> tuple[Path, TaskManifest]:
    t = Path(task_dir).resolve()
    return t, load(t / "task.json", TaskManifest)


def _spec_path(tdir: Path, vid: str) -> Path:
    return tdir / "verifiers" / vid / "spec.json"


def _candidate(tdir: Path, m: TaskManifest, cid: str) -> Candidate:
    for p in m.candidates:
        c = load(tdir / p, Candidate)
        if c.candidate_id == cid:
            return c
    raise SystemExit(f"unknown candidate {cid}")


def cmd_snapshot(a) -> None:
    from .tasks import rebuild_snapshot, verify_snapshot

    tdir, m = _task(a.task)
    dest = rebuild_snapshot(m, SNAPSHOTS, CACHE)
    _out({"task_id": m.task_id, "snapshot_dir": str(dest), "manifest_matches": verify_snapshot(tdir, SNAPSHOTS)})


def cmd_lint(a) -> None:
    from .verifier import lint_process_separated

    issues = lint_process_separated(Path(a.test_dir))
    _out({"issues": [i.__dict__ for i in issues], "ok": not issues})
    sys.exit(0 if not issues else 1)


def cmd_build_verifier(a) -> None:
    """Build a verifier spec; record it only with a complete generation record (B1, the repository's tests, needs none)."""
    from .verifier import build_spec, generation_record, lint_process_separated, requirement_map_from_tests

    tdir, m = _task(a.task)
    vdir = tdir / "verifiers" / a.verifier_id
    tests = vdir / a.test_subdir
    iso = Isolation(a.isolation)
    cond = VerifierCondition(a.condition)
    sp = _spec_path(tdir, a.verifier_id)
    if not a.dry_run and sp.exists() and load(sp, VerifierSpec).frozen:
        raise SystemExit(f"build-verifier refused: {a.verifier_id} is frozen; build a new version under a new verifier id")
    run = dict(run_id=a.gen_run_id, config=a.config, prompt_sha256=a.prompt_sha256, started_at=a.started_at,
               ended_at=a.ended_at, wall_s=a.wall_s, tool_calls=a.tool_calls, run_record=a.run_record, turns=a.turns,
               tokens=a.tokens)
    need = cond != VerifierCondition.repo_tests  # B1 is the repository's own tests: no agent run wrote them
    gen, record = None, "not needed (repository tests)"
    if need or any(v is not None for v in run.values()):
        try:
            gen, record = generation_record(**run), "complete"
        except ValueError as exc:
            record = str(exc)
            if not a.dry_run:
                raise SystemExit(f"build-verifier refused, nothing recorded: {a.verifier_id}: {record}. A generated verifier "
                                 "needs the record of the run that wrote it; --dry-run builds and lints without recording") from None
    check_ids = None
    if a.check_ids:
        check_ids = json.loads(Path(a.check_ids).read_text())
    spec = build_spec(verifier_id=a.verifier_id, task_id=m.task_id, condition=cond,
                      test_dir=tests, task_dir=tdir, isolation=iso, contract_id=a.contract_id,
                      requirement_map=requirement_map_from_tests(tests) if iso == Isolation.process_separated else {},
                      generation=gen, check_ids=check_ids, require_generation=need and not a.dry_run)
    issues = lint_process_separated(tests) if iso == Isolation.process_separated else []
    rel = f"verifiers/{a.verifier_id}/spec.json"
    if not a.dry_run:
        dump(spec, sp)
        if a.sidecar:  # register beside the task, never in a frozen task.json (protocol §15.5)
            from .evaluate import EXTRA_VERIFIERS, extra_verifier_paths
            have = extra_verifier_paths(tdir)
            if rel not in have and rel not in m.verifiers:
                (tdir / EXTRA_VERIFIERS).write_text(json.dumps(
                    {"verifiers": have + [rel],
                     "note": "label-support verifiers added after the task's files were frozen; "
                             "evaluate includes them only with --with-extra-verifiers"}, indent=2) + "\n", encoding="utf-8")
        elif rel not in m.verifiers:
            dump(m.model_copy(update={"verifiers": m.verifiers + [rel]}), tdir / "task.json")
    _out({"spec": rel, "recorded": not a.dry_run, "generation_record": record, "n_checks": len(spec.checks),
          "unmapped_checks": [c.check_id for c in spec.checks if not c.requirement_ids], "lint": [i.__dict__ for i in issues]})


def _grader(tdir: Path, m: TaskManifest):
    from .sandbox.docker_runner import build_env_image, verify_candidate
    from .tasks import verify_snapshot

    if not verify_snapshot(tdir, SNAPSHOTS):
        raise SystemExit("base snapshot missing or modified; run `tracecontract snapshot` first")
    tag, _ = build_env_image(m.env_requirements, CACHE / "images")

    def grade(spec: VerifierSpec, cand: Candidate, repeats: int = 1):
        return verify_candidate(image=tag, base_dir=SNAPSHOTS / m.task_id, spec=spec, task_dir=tdir, candidate=cand,
                                run_id="adhoc", repeats=repeats, candidate_pythonpath=m.candidate_pythonpath,
                                repo_test_args=m.repo_test_args)
    return grade


def cmd_grade(a) -> None:
    tdir, m = _task(a.task)
    spec = load(_spec_path(tdir, a.verifier_id), VerifierSpec)
    res = _grader(tdir, m)(spec, _candidate(tdir, m, a.candidate_id), a.repeats)
    _out(res)


def cmd_audit(a) -> None:
    from .audit import run_audit

    tdir, m = _task(a.task)
    spec = load(_spec_path(tdir, a.verifier_id), VerifierSpec)
    contract = load(tdir / m.contracts[a.contract], TaskContract) if a.contract else None
    dev = [load(tdir / p, Candidate) for p in m.candidates]
    dev = [c for c in dev if c.split == Split.dev and (not a.only or c.candidate_id in a.only)]
    if a.audit_set:
        dev = [c for c in dev if c.candidate_id.startswith(m.task_id + "-noop") or c.origin.value == "reference"
               or a.audit_set in c.produced_by]
    rep = run_audit(spec, contract, dev, _grader(tdir, m), task_dir=tdir)
    if a.record is not None:
        rec = rep.to_record(iterations=a.record, dev_ids=[c.candidate_id for c in dev])
        dump(spec.model_copy(update={"audit": rec}), _spec_path(tdir, a.verifier_id))
    _out({"passed": rep.passed, "findings": [f.__dict__ for f in rep.findings], "runs": rep.runs,
          "dev_candidates": [c.candidate_id for c in dev]})


def cmd_add_candidate(a) -> None:
    from .controlled import candidate_from_state
    from .tasks import now

    tdir, m = _task(a.task)
    labels = []
    if a.label:
        labels.append(Label(value=a.label, violated_requirements=a.violates or [], labeler=a.labeler or "construction",
                            labeler_kind=LabelerKind(a.labeler_kind), timestamp=now(), note=a.note or ""))
    if a.state_dir:
        c = candidate_from_state(task_id=m.task_id, candidate_id=a.candidate_id, base=SNAPSHOTS / m.task_id,
                                 state=Path(a.state_dir), origin=CandidateOrigin(a.origin), split=Split(a.split),
                                 produced_by=a.produced_by, description=a.description or "", labels=labels)
    else:
        patch = Path(a.patch_file).read_text()
        c = Candidate(candidate_id=a.candidate_id, task_id=m.task_id, origin=CandidateOrigin(a.origin), split=Split(a.split),
                      patch=patch, patch_sha256=sha256_text(patch), produced_by=a.produced_by,
                      description=a.description or "", labels=labels)
    rel = f"candidates/{c.candidate_id}.json"
    dump(c, tdir / rel)
    if rel not in m.candidates:
        dump(m.model_copy(update={"candidates": m.candidates + [rel]}), tdir / "task.json")
    _out({"candidate": rel, "patch_sha256": c.patch_sha256, "patch_lines": c.patch.count("\n")})


def cmd_add_stratum_candidate(a) -> None:
    """Register a candidate of a candidate stratum from a state directory; never writes task.json (protocol §15.4)."""
    from .schemas import AttemptRecord
    from .strata import StratumError, attempt_record_problems, capture_patch, register_candidate
    from .tasks import verify_snapshot

    def refuse(why: str) -> SystemExit:
        return SystemExit(f"add-stratum-candidate refused, nothing written: {why}")

    tdir, m = _task(a.task)
    origin, state = CandidateOrigin(a.origin), Path(a.state_dir)
    if not state.is_dir():
        raise refuse(f"{state} is not a directory")
    if not verify_snapshot(tdir, SNAPSHOTS):
        raise refuse(f"the base snapshot of {m.task_id} is missing or modified; run `tracecontract snapshot {a.task}` first")
    if (origin == CandidateOrigin.fresh_attempt) != bool(a.attempt_record):
        raise refuse("a fresh_attempt candidate needs --attempt-record, and only a fresh attempt takes one")
    if not (a.produced_by or a.attempt_record):
        raise refuse("--produced-by is needed for a candidate without an attempt record")
    patch, policy = capture_patch(SNAPSHOTS / m.task_id, state)
    attempt = None
    try:
        if a.attempt_record:
            raw = json.loads(Path(a.attempt_record).read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise refuse(f"{a.attempt_record} does not hold a JSON object")
            attempt = AttemptRecord.model_validate({**raw, "patch_sha256": raw.get("patch_sha256", sha256_text(patch))})
            problems = attempt_record_problems(attempt)
            if problems:
                raise refuse(f"attempt record {a.attempt_record}: " + "; ".join(problems))
        c = Candidate(candidate_id=a.candidate_id, task_id=m.task_id, origin=origin, split=Split(a.split), patch=patch,
                      patch_sha256=sha256_text(patch), description=a.description or "", attempt=attempt,
                      produced_by=a.produced_by or f"fresh-attempt:{attempt.configuration}")
        own = {load(tdir / p, Candidate).candidate_id for p in m.candidates}
        rel, what = register_candidate(tdir, a.stratum, c, own_ids=own, description=a.stratum_description or "")
    except (StratumError, ValueError, OSError) as exc:  # a pydantic ValidationError is a ValueError
        raise refuse(str(exc)) from None
    _out({"candidate": rel, "stratum_manifest": f"strata/{a.stratum}.json", "registered": what, "patch_sha256": c.patch_sha256,
          "patch_lines": patch.count("\n"), "removed_protected_paths": policy.removed_protected,
          "rejected_by_the_grader": policy.errors, "attempt_id": attempt.attempt_id if attempt else None})


def cmd_freeze(a) -> None:
    from .verifier import freeze

    tdir, _ = _task(a.task)
    sp = _spec_path(tdir, a.verifier_id)
    spec = freeze(load(sp, VerifierSpec), tdir)
    dump(spec, sp)
    _out({"verifier_id": spec.verifier_id, "frozen": spec.frozen, "frozen_at": spec.frozen_at,
          "content_sha256": spec.content_sha256, "checks_sha256": spec.checks_sha256})


def cmd_validate_task(a) -> None:
    from .contract import acceptance_gate, validate_contract
    from .tasks import session_for_task, verify_snapshot
    from .verifier import checks_sha256, hash_test_dir, lint_process_separated

    tdir, m = _task(a.task)
    report: dict = {"task_id": m.task_id, "status": m.status}
    session = session_for_task(tdir, REPO)
    report["snapshot_matches"] = verify_snapshot(tdir, SNAPSHOTS) if (SNAPSHOTS / m.task_id).exists() else "not built"
    report["contracts"] = {}
    for variant, p in m.contracts.items():
        if not (tdir / p).exists():
            report["contracts"][variant] = {"status": "sealed or missing", "path": p}
            continue
        c = load(tdir / p, TaskContract)
        issues = validate_contract(c, session)
        ok, reasons = acceptance_gate(c, session)
        report["contracts"][variant] = {"errors": [i.__dict__ for i in issues if i.severity == "error"],
                                        "warnings": [i.__dict__ for i in issues if i.severity == "warning"],
                                        "accepted": ok, "gate_reasons": reasons}
    cands = [load(tdir / p, Candidate) for p in m.candidates]  # loading validates every patch hash
    if a.show_candidates:  # coordinator only: shows origins and proposals (annotation guide, D44)
        report["candidates"] = {}
        for c in cands:
            fl = c.final_label()
            report["candidates"][c.candidate_id] = {"origin": c.origin.value, "split": c.split.value,
                                                    "human_label": fl.value if fl else None,
                                                    "proposed_label": (c.proposed_label().value if c.proposed_label() else None)}
    else:
        report["candidates"] = {"n": len(cands), "patch_hashes_valid": True,
                                "note": "per-candidate origins and labels hidden; --show-candidates (coordinator only)"}
    report["verifiers"] = {}
    for p in m.verifiers:
        s = load(tdir / p, VerifierSpec)
        actual = hash_test_dir(tdir / s.test_dir)
        lint = lint_process_separated(tdir / s.test_dir) if s.isolation == Isolation.process_separated else []
        report["verifiers"][s.verifier_id] = {"condition": s.condition.value, "frozen": s.frozen,
                                              "hash_matches": actual == s.content_sha256,
                                              "checks_hash_matches": (None if s.checks_sha256 is None
                                                                      else checks_sha256(s) == s.checks_sha256),
                                              "n_checks": len(s.checks), "lint_issues": len(lint)}
    _out(report)


def cmd_accept_task(a) -> None:
    """Run the task acceptance gate; set the task's status to 'accepted' only if it passes (exit 1 otherwise)."""
    from .contract import task_gate

    tdir, m = _task(a.task)
    gate = task_gate(tdir, REPO)
    previous = gate.status
    if gate.passed and gate.status != "accepted" and not a.dry_run:
        dump(m.model_copy(update={"status": "accepted"}), tdir / "task.json")
        gate = task_gate(tdir, REPO)
    _out({**gate.to_dict(), "previous_status": previous, "dry_run": a.dry_run})
    sys.exit(0 if gate.passed else 1)


def cmd_ingest(a) -> None:
    from .ingest.claude_code import parse_claude_code_jsonl
    from .schemas import Population

    s = parse_claude_code_jsonl(a.transcript, population=Population(a.population), source=a.source)
    if a.out:
        dump(s, a.out)
    kinds: dict[str, int] = {}
    for e in s.events:
        kinds[e.kind.value] = kinds.get(e.kind.value, 0) + 1
    _out({"session_id": s.session_id, "events": len(s.events), "kinds": kinds, "trace_sha256": s.trace_sha256,
          "user_prompts": [p.event_id for p in s.user_prompts()]})


def cmd_triage(a) -> None:
    from .contract import propose_correction_events
    from .ingest.claude_code import parse_claude_code_jsonl
    from .schemas import Population

    s = parse_claude_code_jsonl(a.transcript, population=Population(a.population), source="cli")
    _out({"session_id": s.session_id, "correction_proposals": propose_correction_events(s),
          "note": "rule-based proposals (high recall); not ground truth"})


def cmd_schema_check(a) -> None:
    from . import schemas as S

    kinds = {"task.json": S.TaskManifest, "provenance.json": S.ProvenanceRecord, "snapshot.json": S.Snapshot,
             "spec.json": S.VerifierSpec}
    bad = 0
    for f in a.files:
        p = Path(f)
        cls = kinds.get(p.name) or (S.Candidate if p.parent.name == "candidates" else
                                    S.TaskContract if p.parent.name == "contracts" else None)
        if cls is None:
            print(f"SKIP {f}")
            continue
        try:
            load(p, cls)
            print(f"OK   {f} ({cls.__name__})")
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"FAIL {f}: {exc}")
    sys.exit(1 if bad else 0)


def cmd_make_contract(a) -> None:
    from .contract import acceptance_gate, render_instruction, requirements_from_proposals, validate_contract
    from .schemas import ContractVariant, TaskContract
    from .tasks import now, session_for_task

    tdir, m = _task(a.task)
    session = session_for_task(tdir, REPO)
    raw = json.loads(Path(a.proposals).read_text())
    props = raw["requirements"] if isinstance(raw, dict) else raw
    out = requirements_from_proposals(session, props, proposer=a.proposer)
    variant = ContractVariant(a.variant)
    c = TaskContract(contract_id=f"{m.task_id}-{variant.value}", task_id=m.task_id, session_id=session.session_id,
                     variant=variant, requirements=out.requirements, created_by=a.proposer, created_at=now(),
                     notes="; ".join(out.warnings))
    c = c.model_copy(update={"instruction": render_instruction(c)})
    rel = f"contracts/{variant.value}.json"
    dump(c, tdir / rel)
    dump(m.model_copy(update={"contracts": {**m.contracts, variant.value: rel}}), tdir / "task.json")
    issues = validate_contract(c, session)
    ok, reasons = acceptance_gate(c, session)
    _out({"contract": rel, "n_requirements": len(c.requirements), "n_active": len(c.active()),
          "rejected_proposals": out.rejected, "warnings": out.warnings,
          "errors": [i.__dict__ for i in issues if i.severity == "error"], "gate_accepted": ok, "gate_reasons": reasons})


def cmd_render_session(a) -> None:
    from .tasks import render_session, session_for_task

    tdir, _ = _task(a.task)
    text = render_session(session_for_task(tdir, REPO), first_prompt_only=a.first_prompt_only, include_tools=not a.no_tools)
    Path(a.out).write_text(text)
    _out({"out": a.out, "chars": len(text)})


def _sandbox_docker(m: TaskManifest, state: Path, argv: list[str], timeout: float) -> dict:
    import subprocess

    from .sandbox.docker_runner import build_env_image

    tag, _ = build_env_image(m.env_requirements, CACHE / "images")
    cmd = ["docker", "run", "--rm", "--init", "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--memory", "2g", "--pids-limit", "256", "--read-only", "--tmpfs", "/tmp:rw,size=256m",
           "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", f"PYTHONPATH={m.candidate_pythonpath}",
           "-v", f"{state.resolve()}:/work:ro", "-w", "/work", "--user", "1001:1001", tag, *argv]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"returncode": p.returncode, "stdout": p.stdout[-20000:], "stderr": p.stderr[-8000:]}
    except subprocess.TimeoutExpired:
        return {"returncode": None, "timed_out": True}


def cmd_sandbox_python(a) -> None:
    _, m = _task(a.task)
    _out(_sandbox_docker(m, Path(a.state_dir), ["python", *a.args], a.timeout))


def cmd_sandbox_pytest(a) -> None:
    _, m = _task(a.task)
    _out(_sandbox_docker(m, Path(a.state_dir), ["python", "-m", "pytest", "-p", "no:cacheprovider", *a.args], a.timeout))


def cmd_materialize(a) -> None:
    """Write a candidate's state (base snapshot + its graded patch) to a directory, e.g. for human review."""
    import shutil

    from .sandbox.docker_runner import prepare_workspace
    from .tasks import verify_snapshot

    tdir, m = _task(a.task)
    if not verify_snapshot(tdir, SNAPSHOTS):
        raise SystemExit(f"base snapshot missing or modified; run `tracecontract snapshot {a.task}` first")
    cand = _candidate(tdir, m, a.candidate_id)
    ws, diags, err = prepare_workspace(SNAPSHOTS / m.task_id, cand.patch)
    if ws is None:
        raise SystemExit(f"patch could not be applied: {err} {diags}")
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"{out} exists; choose a new directory")
    shutil.copytree(ws, out, symlinks=False)
    shutil.rmtree(ws, ignore_errors=True)
    out.chmod(0o755)  # the workspace copy is private; the sandbox user must be able to read it
    _out({"candidate_id": cand.candidate_id, "state_dir": str(out), "diagnostics": diags})


def cmd_export_gen_workspace(a) -> None:
    """Isolated generation workspace: base snapshot copy + selected task material only."""
    import shutil

    from .contract import render_instruction
    from .tasks import render_session, session_for_task

    tdir, m = _task(a.task)
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(SNAPSHOTS / m.task_id, out / "base", symlinks=False)
    if a.contract:
        c = load(tdir / m.contracts[a.contract], TaskContract)
        order = {p.event_id: i + 1 for i, p in enumerate(session_for_task(tdir, REPO).user_prompts())}
        reqs = [{"req_id": r.req_id, "kind": r.kind.value, "statement": r.statement, "observable": r.observable,
                 "introduced_in_user_turn": order.get(r.introduced_at)}
                for r in c.active() if r.scored]
        (out / "contract.json").write_text(json.dumps({"variant": c.variant.value, "requirements": reqs}, indent=2) + "\n")
        (out / "instruction.md").write_text(render_instruction(c))
    if a.with_reference_patch:
        from .patches import filter_patch

        ref = next(load(tdir / p, Candidate) for p in m.candidates if "reference" in p)
        # By default only the graded part of the reference diff: the session agent's test
        # files belong to the repository-test baseline (B1) and are left out (decision log
        # D37, D40). --with-reference-tests restores the full diff.
        (out / "reference.diff").write_text(ref.patch if a.with_reference_tests else filter_patch(ref.patch)[0])
    if a.with_session:
        (out / "session.txt").write_text(render_session(session_for_task(tdir, REPO)))
    if a.with_first_prompt:
        (out / "session_first_prompt.txt").write_text(render_session(session_for_task(tdir, REPO), first_prompt_only=True))
    _out({"workspace": str(out), "files": sorted(p.name for p in out.iterdir())})


def cmd_review_packet(a) -> None:
    """Blinded review packet for human labeling (annotation guide v0.4)."""
    from .review import export_packet

    _out(export_packet([Path(t).resolve() for t in a.tasks], Path(a.out), Path(a.key), snapshot_root=SNAPSHOTS,
                       repo_root=REPO, seed=a.seed))


def cmd_merge_reviews(a) -> None:
    """Merge reviewers' label files from a blinded packet into the candidate records."""
    from .review import merge_labels

    _out(merge_labels([Path(f) for f in a.label_files], Path(a.key), REPO / "tasks", min_reviewers=a.min_reviewers,
                      dry_run=a.dry_run))


def cmd_evaluate(a) -> None:
    from .evaluate import TaskRefused, run_matrix
    from .schemas import Split
    from .strata import StratumError

    try:
        out = run_matrix([Path(t).resolve() for t in a.tasks], run_id=a.run_id, out_root=REPO / "results" / "runs",
                         cache_dir=CACHE / "images", snapshot_root=SNAPSHOTS, split=Split(a.split),
                         conditions=a.conditions or None, repeats=a.repeats, require_frozen=not a.allow_unfrozen,
                         repo_root=REPO, pilot=a.pilot, strata=a.strata, only_strata=a.only_strata,
                         extra_verifiers=a.with_extra_verifiers)
    except TaskRefused as exc:  # nothing was written
        raise SystemExit(f"evaluate refused by the acceptance gate:\n{exc}") from None
    except StratumError as exc:  # nothing was written
        raise SystemExit(f"evaluate refused: {exc}") from None
    _out({"run_dir": str(out)})


def cmd_analyze(a) -> None:
    from .analysis import SENSITIVITY_JSON, SENSITIVITY_MD, ConditionConflict, MixedPopulations, SensitivityExclusionsError, analyze
    from .strata import StratumError

    run = Path(a.run_dir)
    exclusions = [Path(f) for f in a.sensitivity_exclusions or []]
    try:
        res = analyze(run, REPO / "tasks", allow_proposed=a.allow_proposed_labels, n_boot=a.n_boot,
                      pool_populations=a.pool_populations, rules=None if a.reporting_rules == "auto" else a.reporting_rules,
                      sensitivity_exclusions=exclusions)
    except (MixedPopulations, StratumError, ConditionConflict, SensitivityExclusionsError) as exc:  # nothing was written
        raise SystemExit(f"analyze refused: {exc}") from None
    pooled = {"population_pooling": res["meta"]["population_pooling"]} if "population_pooling" in res["meta"] else {}
    rules = res["meta"].get("reporting_rules", {"rules": "pilot"})
    sens = {}
    if exclusions:  # the sensitivity view of protocol §18.1, written beside the main analysis
        s = json.loads((run / SENSITIVITY_JSON).read_text(encoding="utf-8"))["meta"]["sensitivity"]
        sens = {"sensitivity": {"analysis": str(run / SENSITIVITY_JSON), "markdown": str(run / SENSITIVITY_MD),
                                "also_excluded": len(s["excluded_here"]), "not_in_run": s["not_in_run"]}}
    _out({"analysis": str(run / "analysis.json"), "markdown": str(run / "analysis.md"),
          "conditions": {c: {"fa": d["false_acceptance"]["rate"], "fr": d["false_rejection"]["rate"]} for c, d in res["conditions"].items()},
          "reporting_rules": rules["rules"], **pooled, **sens})


def cmd_report(a) -> None:
    from .report import build_report

    out = build_report(Path(a.run_dir), REPO / "tasks", REPO, Path(a.out))
    _out({"report": str(out)})


def cmd_reconstruction_check(a) -> None:
    """Check a task's base snapshot against its session (reconstruction:v2).

    Exit 1 if a check failed; else exit 2 if the report is incomplete (a check was unavailable or
    not checkable, or a changed file has no passed item in check b or c); exit 0 only if it passed.
    """
    from .reconstruction import RECORD, check_task
    from .store import write_json

    tdir = Path(a.task).resolve()
    rep = check_task(tdir, REPO, SNAPSHOTS).to_dict()
    if a.write:
        write_json(rep, tdir / RECORD)
    _out(rep)
    unavailable = any(c["status"] == "unavailable" for c in rep["checks"])
    sys.exit(1 if rep["status"] == "failed" else 2 if rep["status"] == "incomplete" or unavailable else 0)


def cmd_compile_pr_task(a) -> None:
    """Compile one natural PR-review family into ``<out>/NP-<k>/`` (or only plan it); exit 1 if it is rejected (§15.6, §17)."""
    from . import natural_pr as npr

    try:
        fam = npr.find_family(npr.load_families(Path(a.qualifying) if a.qualifying else npr.QUALIFYING), a.pr_id)
    except (KeyError, OSError, ValueError) as exc:
        raise SystemExit(f"compile-pr-task: {exc}") from None
    res = npr.compile_pr_task(fam, Path(a.out), plan_only=a.plan_only, aidev_data=Path(a.aidev_data) if a.aidev_data else npr.AIDEV_DATA,
                              snapshot_root=Path(a.snapshots) if a.snapshots else None,
                              fetch_log=Path(a.fetch_log) if a.fetch_log else None)
    _out(res)
    sys.exit(1 if res["outcome"] == "rejected" else 0)


def cmd_natural_index(a) -> None:
    """Write the committed index of the natural PR-review tasks: ids, SHAs, licences, file hashes and S10 outcomes; no text."""
    from . import natural_pr as npr

    q = Path(a.qualifying) if a.qualifying else npr.QUALIFYING
    idx = npr.write_natural_index(Path(a.tasks), Path(a.out) if a.out else npr.INDEX,
                                  families=npr.load_families(q) if q.is_file() else None)
    _out({"index": str(Path(a.out) if a.out else npr.INDEX), "tasks": len(idx["tasks"]), "counts": idx["counts"]})


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="tracecontract")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("snapshot", help="rebuild a task's base snapshot from its pinned source")
    p.add_argument("task"); p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("lint-tests", help="lint process-separated verifier tests")
    p.add_argument("test_dir"); p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("build-verifier", help="build/refresh a verifier spec from its test directory")
    p.add_argument("task"); p.add_argument("verifier_id"); p.add_argument("--condition", required=True)
    p.add_argument("--isolation", default="process_separated"); p.add_argument("--test-subdir", default="tests")
    p.add_argument("--contract-id"); p.add_argument("--check-ids")
    p.add_argument("--dry-run", action="store_true", help="build and lint only; record nothing (no generation record needed)")
    p.add_argument("--sidecar", action="store_true",
                   help="register the verifier in verifiers_extra.json instead of task.json (for tasks whose files are frozen)")
    g = p.add_argument_group("generation record (required to record a generated verifier; never a model identifier)")
    g.add_argument("--gen-run-id", help="run id of the agent run that wrote the tests")
    g.add_argument("--config", help="configuration label of that run, e.g. config-A")
    g.add_argument("--prompt-sha256", help="sha256 of the prompt the run was given")
    g.add_argument("--started-at"); g.add_argument("--ended-at", help="ISO 8601 times with a time zone")
    g.add_argument("--turns", type=int); g.add_argument("--tokens", type=int, help="turns or tokens (or both)")
    g.add_argument("--tool-calls", type=int); g.add_argument("--wall-s", type=float, help="wall time in seconds")
    g.add_argument("--run-record", help="pointer to the private run record, kept outside the repository")
    p.set_defaults(fn=cmd_build_verifier)
    p = sub.add_parser("grade", help="grade one candidate with one verifier (sandboxed)")
    p.add_argument("task"); p.add_argument("verifier_id"); p.add_argument("candidate_id")
    p.add_argument("--repeats", type=int, default=1); p.set_defaults(fn=cmd_grade)
    p = sub.add_parser("audit", help="run audit:v1 on a verifier with development candidates only")
    p.add_argument("task"); p.add_argument("verifier_id"); p.add_argument("--contract")
    p.add_argument("--only", nargs="*"); p.add_argument("--audit-set", help="only dev candidates whose produced_by contains this tag")
    p.add_argument("--record", type=int, help="store the audit result in the spec with this number of revision iterations")
    p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("add-candidate", help="register a candidate from a state directory or a patch file")
    p.add_argument("task"); p.add_argument("candidate_id"); p.add_argument("--origin", required=True)
    p.add_argument("--split", required=True); p.add_argument("--produced-by", required=True)
    p.add_argument("--state-dir"); p.add_argument("--patch-file"); p.add_argument("--description")
    p.add_argument("--label", choices=["valid", "invalid", "ambiguous"]); p.add_argument("--violates", nargs="*")
    p.add_argument("--labeler"); p.add_argument("--labeler-kind", default="construction"); p.add_argument("--note")
    p.set_defaults(fn=cmd_add_candidate)
    from .schemas import NATURAL_ORIGINS

    p = sub.add_parser("add-stratum-candidate", help="register a candidate of a candidate stratum from a state directory "
                       "(strata/<stratum>/candidates/ and strata/<stratum>.json); task.json is never changed")
    p.add_argument("task"); p.add_argument("stratum"); p.add_argument("candidate_id")
    p.add_argument("--state-dir", required=True, help="the final state to capture, e.g. an attempt workspace's repo/ "
                   "(.git, caches and the paths the patch policy removes before grading are left out)")
    p.add_argument("--origin", required=True, choices=sorted(o.value for o in NATURAL_ORIGINS),
                   help="a natural origin: D19 labels these by its natural-candidate rule, so no construction label is needed")
    p.add_argument("--attempt-record", metavar="FILE", help="JSON attempt record (schemas.AttemptRecord), required for and "
                   "only for fresh_attempt; patch_sha256 may be left out, it is the captured patch's")
    p.add_argument("--split", default="eval", choices=[x.value for x in Split])
    p.add_argument("--produced-by", help="who produced the state (default for an attempt: fresh-attempt:<configuration>)")
    p.add_argument("--description"); p.add_argument("--stratum-description", help="description of a new stratum manifest")
    p.set_defaults(fn=cmd_add_stratum_candidate)
    p = sub.add_parser("freeze", help="freeze a verifier before final evaluation")
    p.add_argument("task"); p.add_argument("verifier_id"); p.set_defaults(fn=cmd_freeze)
    p = sub.add_parser("validate-task", help="validate a task directory (contracts, candidates, verifiers, snapshot)")
    p.add_argument("task")
    p.add_argument("--show-candidates", action="store_true",
                   help="list each candidate's origin and labels (coordinator only; reviewers must not see them)")
    p.set_defaults(fn=cmd_validate_task)
    p = sub.add_parser("accept-task", help="run the task acceptance gate; set the status to 'accepted' only if it passes")
    p.add_argument("task"); p.add_argument("--dry-run", action="store_true", help="report the gate; never change the task")
    p.set_defaults(fn=cmd_accept_task)
    p = sub.add_parser("ingest", help="parse a Claude Code JSONL transcript")
    p.add_argument("transcript"); p.add_argument("--population", default="fixture"); p.add_argument("--source", default="cli")
    p.add_argument("--out"); p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("triage", help="rule-based correction proposals for a transcript")
    p.add_argument("transcript"); p.add_argument("--population", default="fixture"); p.set_defaults(fn=cmd_triage)
    p = sub.add_parser("schema-check", help="validate JSON artifacts against their schemas")
    p.add_argument("files", nargs="+"); p.set_defaults(fn=cmd_schema_check)

    p = sub.add_parser("make-contract", help="validate recorded requirement proposals into a contract")
    p.add_argument("task"); p.add_argument("--variant", required=True); p.add_argument("--proposals", required=True)
    p.add_argument("--proposer", required=True); p.set_defaults(fn=cmd_make_contract)
    p = sub.add_parser("render-session", help="render a task's session as text for model-based reconstruction")
    p.add_argument("task"); p.add_argument("--out", required=True); p.add_argument("--first-prompt-only", action="store_true")
    p.add_argument("--no-tools", action="store_true"); p.set_defaults(fn=cmd_render_session)
    p = sub.add_parser("sandbox-python", help="run python against a candidate state dir in the task image (offline, unprivileged)")
    p.add_argument("task"); p.add_argument("state_dir"); p.add_argument("--timeout", type=float, default=120)
    p.add_argument("args", nargs=argparse.REMAINDER); p.set_defaults(fn=cmd_sandbox_python)
    p = sub.add_parser("sandbox-pytest", help="run pytest against a candidate state dir in the task image (offline, unprivileged)")
    p.add_argument("task"); p.add_argument("state_dir"); p.add_argument("--timeout", type=float, default=900)
    p.add_argument("args", nargs=argparse.REMAINDER); p.set_defaults(fn=cmd_sandbox_pytest)
    p = sub.add_parser("materialize", help="write a candidate's graded state (base + patch, protected paths removed) to a new directory")
    p.add_argument("task"); p.add_argument("candidate_id"); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_materialize)
    p = sub.add_parser("export-gen-workspace", help="isolated workspace for a generation agent")
    p.add_argument("task"); p.add_argument("--out", required=True); p.add_argument("--contract")
    p.add_argument("--with-reference-patch", action="store_true"); p.add_argument("--with-session", action="store_true")
    p.add_argument("--with-reference-tests", action="store_true",
                   help="with --with-reference-patch: keep the reference's test-file hunks (B1 material; off by default)")
    p.add_argument("--with-first-prompt", action="store_true"); p.set_defaults(fn=cmd_export_gen_workspace)

    p = sub.add_parser("review-packet", help="blinded packet of held-out candidates for human reviewers (opaque ids; key kept apart)")
    p.add_argument("tasks", nargs="+"); p.add_argument("--out", required=True); p.add_argument("--key", required=True)
    p.add_argument("--seed", type=int, required=True); p.set_defaults(fn=cmd_review_packet)
    p = sub.add_parser("merge-reviews", help="append reviewers' blinded labels to the candidate records as human labels")
    p.add_argument("label_files", nargs="+"); p.add_argument("--key", required=True)
    p.add_argument("--min-reviewers", type=int, default=2); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_merge_reviews)

    p = sub.add_parser("evaluate", help="score every frozen verifier on every evaluation candidate (sandboxed)")
    p.add_argument("tasks", nargs="+"); p.add_argument("--run-id", required=True); p.add_argument("--split", default="eval")
    p.add_argument("--conditions", nargs="*", metavar="CONDITION", choices=[c.value for c in VerifierCondition],
                   help="only verifiers of these conditions, e.g. initial_plain ... repo_tests, diff_derived (B3)")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--allow-unfrozen", action="store_true")
    p.add_argument("--pilot", action="store_true", help="automated pilot only: also evaluate tasks that have not passed the "
                   "acceptance gate (recorded in the run manifest); rejected tasks are always refused")
    p.add_argument("--strata", nargs="+", metavar="NAME", help="also grade the candidates of these candidate strata "
                   "(tasks/<id>/strata/<name>.json); task.json and the task's candidate files are never changed")
    p.add_argument("--with-extra-verifiers", action="store_true",
                   help="also grade the label-support verifiers registered in each task's verifiers_extra.json")
    p.add_argument("--only-strata", action="store_true", help="with --strata: grade the strata's candidates instead of the "
                   "task's own (the task's reference solution is still graded as the sanity check)")
    p.set_defaults(fn=cmd_evaluate)
    p = sub.add_parser("analyze", help="compute FA/FR, paired comparisons and tables for a run")
    p.add_argument("run_dir"); p.add_argument("--allow-proposed-labels", action="store_true", help="automated pilot only")
    p.add_argument("--n-boot", type=int, default=2000)
    p.add_argument("--pool-populations", action="store_true", help="analyse a run whose tasks come from more than one "
                   "population (controlled, natural:pr-review, natural:chat, natural, fixture): the pooled tables are marked "
                   "and each population is also reported separately; without it such a run is refused")
    p.add_argument("--reporting-rules", choices=["auto", "pilot", "v0.8"], default="auto",
                   help="pilot: the pre-specified analysis of the recorded runs; v0.8: the reporting rules of new runs "
                   "(protocol §15.7, §16.6: per-family table, exact sign-flip p-values, distinct patches, oracle-gated view, "
                   "bootstrap appendix); auto (default): v0.8 for a run graded with tc-harness/0.3.4 or later")
    p.add_argument("--sensitivity-exclusions", action="append", metavar="FILE",
                   help="sensitivity view (protocol §18.1), repeatable: FILE is an audit report with an 'excluded' list of "
                   "attempt ids, or a JSON list of attempt ids. The main analysis is written as usual, and "
                   "analysis_sensitivity.json and analysis_sensitivity.md recompute every table with those attempts excluded too")
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("report", help="static HTML report for a run (from recorded artifacts only)")
    p.add_argument("run_dir"); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_report)
    p = sub.add_parser("reconstruction-check", help="check a task's base snapshot against its session transcript and captured states")
    p.add_argument("task"); p.add_argument("--write", action="store_true", help="write tasks/<id>/reconstruction_check.json")
    p.set_defaults(fn=cmd_reconstruction_check)
    p = sub.add_parser("compile-pr-task", help="compile a natural PR-review family (an AIDev S9 survivor) into <out>/NP-<k>/ "
                       "(git-ignored); exit 1 if it is rejected at S10")
    p.add_argument("pr_id", type=int); p.add_argument("--out", default=str(REPO / "data" / "natural" / "tasks"))
    p.add_argument("--plan-only", action="store_true", help="plan only: base, fidelity, licence check and planned closure; "
                   "nothing is built or written but the fetch log (blobs it reads are fetched within the caps)")
    p.add_argument("--qualifying", help="s9_qualifying.json (default: the S9 record outside the repository)")
    p.add_argument("--aidev-data", help="directory of the AIDev v5 parquet files")
    p.add_argument("--snapshots", help="base snapshots (default: <out>/../snapshots)")
    p.add_argument("--fetch-log", help="fetch log, JSON lines (default: <out>/../s10_fetch_log.jsonl)")
    p.set_defaults(fn=cmd_compile_pr_task)
    p = sub.add_parser("natural-index", help="write the committed index of the natural PR-review tasks (no text)")
    p.add_argument("--tasks", default=str(REPO / "data" / "natural" / "tasks"))
    p.add_argument("--out", help="default: data/manifests/natural_tasks_index.json")
    p.add_argument("--qualifying", help="s9_qualifying.json, for the families not built yet")
    p.set_defaults(fn=cmd_natural_index)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
