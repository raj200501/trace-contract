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
    from .verifier import build_spec, lint_process_separated, requirement_map_from_tests
    from .schemas import GenerationRecord

    tdir, m = _task(a.task)
    vdir = tdir / "verifiers" / a.verifier_id
    tests = vdir / a.test_subdir
    iso = Isolation(a.isolation)
    gen = None
    if a.generator:
        gen = GenerationRecord(generator=a.generator, run_id=a.gen_run_id or "unrecorded",
                               prompt_sha256=a.prompt_sha256 or "", created_at=a.created_at or "")
    check_ids = None
    if a.check_ids:
        check_ids = json.loads(Path(a.check_ids).read_text())
    spec = build_spec(verifier_id=a.verifier_id, task_id=m.task_id, condition=VerifierCondition(a.condition),
                      test_dir=tests, task_dir=tdir, isolation=iso, contract_id=a.contract_id,
                      requirement_map=requirement_map_from_tests(tests) if iso == Isolation.process_separated else {},
                      generation=gen, check_ids=check_ids)
    issues = lint_process_separated(tests) if iso == Isolation.process_separated else []
    dump(spec, _spec_path(tdir, a.verifier_id))
    rel = f"verifiers/{a.verifier_id}/spec.json"
    if rel not in m.verifiers:
        dump(m.model_copy(update={"verifiers": m.verifiers + [rel]}), tdir / "task.json")
    _out({"spec": rel, "n_checks": len(spec.checks), "unmapped_checks": [c.check_id for c in spec.checks if not c.requirement_ids],
          "lint": [i.__dict__ for i in issues]})


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


def cmd_freeze(a) -> None:
    from .verifier import freeze

    tdir, _ = _task(a.task)
    sp = _spec_path(tdir, a.verifier_id)
    spec = freeze(load(sp, VerifierSpec), tdir)
    dump(spec, sp)
    _out({"verifier_id": spec.verifier_id, "frozen": spec.frozen, "content_sha256": spec.content_sha256})


def cmd_validate_task(a) -> None:
    from .contract import acceptance_gate, validate_contract
    from .tasks import session_for_task, verify_snapshot
    from .verifier import hash_test_dir, lint_process_separated

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
    report["candidates"] = {}
    for p in m.candidates:
        c = load(tdir / p, Candidate)  # validates the patch hash
        fl = c.final_label()
        report["candidates"][c.candidate_id] = {"origin": c.origin.value, "split": c.split.value,
                                                "human_label": fl.value if fl else None,
                                                "proposed_label": (c.proposed_label().value if c.proposed_label() else None)}
    report["verifiers"] = {}
    for p in m.verifiers:
        s = load(tdir / p, VerifierSpec)
        actual = hash_test_dir(tdir / s.test_dir)
        lint = lint_process_separated(tdir / s.test_dir) if s.isolation == Isolation.process_separated else []
        report["verifiers"][s.verifier_id] = {"condition": s.condition.value, "frozen": s.frozen,
                                              "hash_matches": actual == s.content_sha256, "n_checks": len(s.checks),
                                              "lint_issues": len(lint)}
    _out(report)


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
        ref = next(load(tdir / p, Candidate) for p in m.candidates if "reference" in p)
        (out / "reference.diff").write_text(ref.patch)
    if a.with_session:
        (out / "session.txt").write_text(render_session(session_for_task(tdir, REPO)))
    if a.with_first_prompt:
        (out / "session_first_prompt.txt").write_text(render_session(session_for_task(tdir, REPO), first_prompt_only=True))
    _out({"workspace": str(out), "files": sorted(p.name for p in out.iterdir())})


def cmd_evaluate(a) -> None:
    from .evaluate import run_matrix
    from .schemas import Split

    out = run_matrix([Path(t).resolve() for t in a.tasks], run_id=a.run_id, out_root=REPO / "results" / "runs",
                     cache_dir=CACHE / "images", snapshot_root=SNAPSHOTS, split=Split(a.split),
                     conditions=a.conditions or None, repeats=a.repeats, require_frozen=not a.allow_unfrozen, repo_root=REPO)
    _out({"run_dir": str(out)})


def cmd_analyze(a) -> None:
    from .analysis import analyze

    res = analyze(Path(a.run_dir), REPO / "tasks", allow_proposed=a.allow_proposed_labels, n_boot=a.n_boot)
    _out({"analysis": str(Path(a.run_dir) / "analysis.json"), "markdown": str(Path(a.run_dir) / "analysis.md"),
          "conditions": {c: {"fa": d["false_acceptance"]["rate"], "fr": d["false_rejection"]["rate"]} for c, d in res["conditions"].items()}})


def cmd_report(a) -> None:
    from .report import build_report

    out = build_report(Path(a.run_dir), REPO / "tasks", REPO, Path(a.out))
    _out({"report": str(out)})


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
    p.add_argument("--contract-id"); p.add_argument("--generator"); p.add_argument("--gen-run-id")
    p.add_argument("--prompt-sha256"); p.add_argument("--created-at"); p.add_argument("--check-ids")
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
    p = sub.add_parser("freeze", help="freeze a verifier before final evaluation")
    p.add_argument("task"); p.add_argument("verifier_id"); p.set_defaults(fn=cmd_freeze)
    p = sub.add_parser("validate-task", help="validate a task directory (contracts, candidates, verifiers, snapshot)")
    p.add_argument("task"); p.set_defaults(fn=cmd_validate_task)
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
    p = sub.add_parser("export-gen-workspace", help="isolated workspace for a generation agent")
    p.add_argument("task"); p.add_argument("--out", required=True); p.add_argument("--contract")
    p.add_argument("--with-reference-patch", action="store_true"); p.add_argument("--with-session", action="store_true")
    p.add_argument("--with-first-prompt", action="store_true"); p.set_defaults(fn=cmd_export_gen_workspace)

    p = sub.add_parser("evaluate", help="score every frozen verifier on every evaluation candidate (sandboxed)")
    p.add_argument("tasks", nargs="+"); p.add_argument("--run-id", required=True); p.add_argument("--split", default="eval")
    p.add_argument("--conditions", nargs="*"); p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--allow-unfrozen", action="store_true"); p.set_defaults(fn=cmd_evaluate)
    p = sub.add_parser("analyze", help="compute FA/FR, paired comparisons and tables for a run")
    p.add_argument("run_dir"); p.add_argument("--allow-proposed-labels", action="store_true", help="automated pilot only")
    p.add_argument("--n-boot", type=int, default=2000); p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("report", help="static HTML report for a run (from recorded artifacts only)")
    p.add_argument("run_dir"); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_report)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
