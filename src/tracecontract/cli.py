"""Command-line interface: ``tracecontract <command> ...``.

Commands print JSON to stdout so that they can be scripted and recorded.

A task's base snapshot is looked up where its population keeps it (:func:`_snapshot_root`, which follows
``roots.snapshot_root``): ``snapshots/<id>`` for the controlled tasks, ``data/natural/snapshots/<id>`` for a
natural PR-review task, as its provenance records it. ``SNAPSHOTS`` stays for the scripts that import it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from . import roots
from .schemas import (
    CONSTRUCTED_ORIGINS, Candidate, CandidateOrigin, ContractVariant, GenerationRecord, Isolation, Label, LabelerKind,
    Population, Session, Split, TaskContract, TaskManifest, VerifierCondition, VerifierSpec, sha256_text,
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


def _snapshot_root(tdir: Path) -> Path:
    """The directory that holds the task's base snapshot (``<root>/<task id>``), as ``roots.snapshot_root`` decides it.

    A natural PR-review task: the root its provenance records (``data/natural/snapshots``) under the repository
    ``REPO``; any other task: ``SNAPSHOTS`` (``<repo>/snapshots``, which is ``roots.snapshot_root``'s answer for it).
    """
    if not roots.is_natural_pr(tdir):
        return SNAPSHOTS
    try:
        return roots.snapshot_root(tdir, repo=REPO)
    except roots.RootError as exc:
        raise SystemExit(f"{tdir.name}: {exc}") from None


def _rebuild_hint(tdir: Path, given: str | None = None) -> str:
    """How the task's base snapshot is (re)built; ``given`` is the task as the command line named it."""
    if roots.is_natural_pr(tdir):
        return "a natural PR-review task's base is built by `tracecontract compile-pr-task`"
    return f"run `tracecontract snapshot {given or tdir}` first"


# build-verifier's run flags, as the keys of a generation-record file in that form (``--generation-record``).
_RUN_FIELDS = ("run_id", "config", "prompt_sha256", "started_at", "ended_at", "wall_s", "tool_calls", "run_record", "turns",
               "tokens", "notes")


def _read_generation_record(path: str) -> tuple[GenerationRecord | None, list[str]]:
    """The generation record in ``path`` and what keeps it from being complete (``verifier.generation_record_problems``).

    The file holds one JSON object: a :class:`GenerationRecord` as ``build-verifier`` stores it in a spec
    (``generator``, ``run_id``, ``prompt_sha256``, ``created_at``, ``budget``, ``notes``), or the run fields of
    ``build-verifier``'s flags (``run_id``, ``config``, ``prompt_sha256``, ``started_at``, ``ended_at``, ``wall_s``,
    ``tool_calls``, ``run_record``, ``turns`` or ``tokens``, ``notes``).
    """
    from .verifier import generation_record, generation_record_problems

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [f"{path} is not a readable JSON file ({type(exc).__name__})"]
    if not isinstance(raw, dict):
        return None, [f"{path} does not hold a JSON object"]
    try:
        if "config" in raw and "generator" not in raw:  # the flags' form
            unknown = sorted(set(raw) - set(_RUN_FIELDS))
            if unknown:
                return None, [f"{path}: unknown keys {unknown} (the run fields are {', '.join(_RUN_FIELDS)})"]
            rec = generation_record(**{k: raw.get(k) for k in _RUN_FIELDS if k != "notes"}, notes=str(raw.get("notes") or ""))
        else:
            rec = GenerationRecord.model_validate(raw)
    except ValueError as exc:  # an incomplete record of the flags' form, or a pydantic ValidationError
        return None, [" ".join(str(exc).split())[:600] or type(exc).__name__]
    return rec, generation_record_problems(rec)


def _complete_generation_record(path: str | None, command: str, *, required_for: str | None = None) -> GenerationRecord | None:
    """The complete generation record in ``path``; ``None`` without one, unless ``required_for`` says why one is needed.

    An incomplete record, or a missing one where it is required, refuses the command before anything is written."""
    if path is None:
        if required_for:
            raise SystemExit(f"{command} refused, nothing written: {required_for} needs the generation record of the agent "
                             "run that made it (--generation-record FILE; protocol §15.6)")
        return None
    rec, problems = _read_generation_record(path)
    if rec is None or problems:
        raise SystemExit(f"{command} refused, nothing written: {path}: incomplete generation record: " + "; ".join(problems))
    return rec


def _spec_path(tdir: Path, vid: str) -> Path:
    return tdir / "verifiers" / vid / "spec.json"


def _candidate(tdir: Path, m: TaskManifest, cid: str) -> Candidate:
    for p in m.candidates:
        c = load(tdir / p, Candidate)
        if c.candidate_id == cid:
            return c
    raise SystemExit(f"unknown candidate {cid}")


def cmd_snapshot(a) -> None:
    """Rebuild a task's base snapshot from its pinned source; refused for a natural PR-review task, whose base comes from
    the PR's commits (``tracecontract compile-pr-task``)."""
    from .tasks import rebuild_snapshot, verify_snapshot

    tdir, m = _task(a.task)
    if m.population == Population.natural_pr_review:
        raise SystemExit(f"snapshot refused: {m.task_id} is a natural PR-review task; its base snapshot is built from the PR's "
                         f"commits into {_snapshot_root(tdir)} by `tracecontract compile-pr-task` (never from the pinned "
                         "source)")
    root = _snapshot_root(tdir)
    dest = rebuild_snapshot(m, root, CACHE)
    _out({"task_id": m.task_id, "snapshot_dir": str(dest), "manifest_matches": verify_snapshot(tdir, root)})


def cmd_lint(a) -> None:
    from .verifier import lint_process_separated

    issues = lint_process_separated(Path(a.test_dir))
    _out({"issues": [i.__dict__ for i in issues], "ok": not issues})
    sys.exit(0 if not issues else 1)


def cmd_build_verifier(a) -> None:
    """Build a verifier spec; record it only with a complete generation record (B1, the repository's tests, needs none).

    The record comes from the run flags (``--gen-run-id`` ...) or from ``--generation-record FILE``, never from both."""
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
    if a.generation_record and any(v is not None for v in run.values()):
        raise SystemExit("build-verifier refused, nothing recorded: give the generation record either as --generation-record "
                         "FILE or as the run flags (--gen-run-id ...), not both")
    need = cond != VerifierCondition.repo_tests  # B1 is the repository's own tests: no agent run wrote them
    gen, record = None, "not needed (repository tests)"
    refusal = (f"build-verifier refused, nothing recorded: {a.verifier_id}: {{}}. A generated verifier needs the record of "
               "the run that wrote it; --dry-run builds and lints without recording")
    if a.generation_record:
        loaded, problems = _read_generation_record(a.generation_record)
        if loaded is not None and not problems:
            gen, record = loaded, "complete"
        else:
            record = "incomplete generation record: " + "; ".join(problems)
            if not a.dry_run:
                raise SystemExit(refusal.format(record))
    elif need or any(v is not None for v in run.values()):
        try:
            gen, record = generation_record(**run), "complete"
        except ValueError as exc:
            record = str(exc)
            if not a.dry_run:
                raise SystemExit(refusal.format(record)) from None
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


def _image(tdir: Path, m: TaskManifest, command: str) -> str:
    """The tag of the image that the task is graded or run in.

    A natural PR-review task's image is only looked up, never built, and must have the id that its ``snapshot.json``
    records (``evaluate.find_image``), so no command grades it in a rebuilt image; any other task's image is built when
    it is missing (``docker_runner.build_env_image``), as before."""
    if m.population != Population.natural_pr_review:
        from .sandbox.docker_runner import build_env_image

        return build_env_image(m.env_requirements, CACHE / "images")[0]
    from . import evaluate
    from .schemas import Snapshot

    try:
        return evaluate.find_image(m, load(tdir / (m.snapshot or "snapshot.json"), Snapshot), CACHE / "images")[0]
    except evaluate.RunRefused as exc:
        raise SystemExit(f"{command} refused: {exc}") from None


def _grader(tdir: Path, m: TaskManifest, command: str = "grade"):
    from .sandbox.docker_runner import verify_candidate
    from .tasks import verify_snapshot

    root = _snapshot_root(tdir)
    if not (root / m.task_id).is_dir() or not verify_snapshot(tdir, root):
        raise SystemExit(f"base snapshot missing or modified at {root / m.task_id}; {_rebuild_hint(tdir)}")
    tag = _image(tdir, m, command)

    def grade(spec: VerifierSpec, cand: Candidate, repeats: int = 1):
        return verify_candidate(image=tag, base_dir=root / m.task_id, spec=spec, task_dir=tdir, candidate=cand,
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
    rep = run_audit(spec, contract, dev, _grader(tdir, m, "audit"), task_dir=tdir)
    if a.record is not None:
        rec = rep.to_record(iterations=a.record, dev_ids=[c.candidate_id for c in dev])
        dump(spec.model_copy(update={"audit": rec}), _spec_path(tdir, a.verifier_id))
    _out({"passed": rep.passed, "findings": [f.__dict__ for f in rep.findings], "runs": rep.runs,
          "dev_candidates": [c.candidate_id for c in dev]})


def cmd_add_candidate(a) -> None:
    """Register a candidate from a state directory (against the task's base snapshot) or a patch file.

    ``--generation-record FILE`` is kept with a constructed candidate (``CONSTRUCTED_ORIGINS``: dev attack, valid
    alternative, near miss); a natural PR-review task's constructed candidate is refused without a complete one.
    """
    from .controlled import candidate_from_state
    from .tasks import now

    tdir, m = _task(a.task)
    origin = CandidateOrigin(a.origin)
    if a.generation_record and origin not in CONSTRUCTED_ORIGINS:
        raise SystemExit(f"add-candidate refused, nothing written: a generation record is kept only with a constructed "
                         f"candidate ({', '.join(sorted(o.value for o in CONSTRUCTED_ORIGINS))}), not with origin {origin.value}")
    natural = m.population == Population.natural_pr_review
    gen = None
    if origin in CONSTRUCTED_ORIGINS:
        gen = _complete_generation_record(a.generation_record, "add-candidate", required_for=(
            f"a {origin.value} candidate of the natural PR-review task {m.task_id}" if natural else None))
    labels = []
    if a.label:
        labels.append(Label(value=a.label, violated_requirements=a.violates or [], labeler=a.labeler or "construction",
                            labeler_kind=LabelerKind(a.labeler_kind), timestamp=now(), note=a.note or ""))
    if a.state_dir:
        base = _snapshot_root(tdir) / m.task_id
        if not base.is_dir():
            raise SystemExit(f"add-candidate refused, nothing written: the base snapshot of {m.task_id} is not at {base}; "
                             f"{_rebuild_hint(tdir, a.task)}")
        c = candidate_from_state(task_id=m.task_id, candidate_id=a.candidate_id, base=base,
                                 state=Path(a.state_dir), origin=origin, split=Split(a.split),
                                 produced_by=a.produced_by, description=a.description or "", labels=labels)
    else:
        patch = Path(a.patch_file).read_text()
        c = Candidate(candidate_id=a.candidate_id, task_id=m.task_id, origin=origin, split=Split(a.split),
                      patch=patch, patch_sha256=sha256_text(patch), produced_by=a.produced_by,
                      description=a.description or "", labels=labels)
    if gen is not None:
        c = c.model_copy(update={"generation": gen})
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
    root = _snapshot_root(tdir)
    if not (root / m.task_id).is_dir() or not verify_snapshot(tdir, root):
        raise refuse(f"the base snapshot of {m.task_id} is missing or modified; {_rebuild_hint(tdir, a.task)}")
    if (origin == CandidateOrigin.fresh_attempt) != bool(a.attempt_record):
        raise refuse("a fresh_attempt candidate needs --attempt-record, and only a fresh attempt takes one")
    if not (a.produced_by or a.attempt_record):
        raise refuse("--produced-by is needed for a candidate without an attempt record")
    patch, policy = capture_patch(root / m.task_id, state)
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
    root = _snapshot_root(tdir)
    report["snapshot_matches"] = verify_snapshot(tdir, root) if (root / m.task_id).exists() else "not built"
    if m.population == Population.natural_pr_review:  # its S10 outcome, S11 and PR record, as the acceptance gate reads them
        from .contract import task_gate

        report["acceptance_gate"] = task_gate(tdir, REPO).to_dict()
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


def _proposals(path: str) -> list:
    raw = json.loads(Path(path).read_text())
    return raw["requirements"] if isinstance(raw, dict) else raw


def _rendered_session(session: Session, variant: ContractVariant, refuse: Callable[[str], SystemExit]) -> Session:
    """A natural PR-review session as the proposer of ``variant`` sees it: the events of its rendered thread
    (``tasks.render_session_events``), read back as a session (``tasks.session_from_events``).

    make-contract and check-proposals check a natural task's proposals on it, so they answer alike: a proposal that names
    an event the proposer was not shown (the PR body, a commit, for ``initial_only`` the review comment) is rejected by
    both. The events keep their ids, kinds, texts and order, so the contract validates on the whole session as on them.
    """
    from . import tasks

    render, read = getattr(tasks, "render_session_events", None), getattr(tasks, "session_from_events", None)
    if render is None or read is None:
        raise refuse("this tree has no tasks.render_session_events and tasks.session_from_events, so the events that a "
                     "natural PR-review proposer is shown cannot be built")
    try:
        return read(render(session, variant))
    except ValueError as exc:
        raise refuse(f"the {variant.value} thread of {session.session_id} cannot be rendered: {exc}") from None


def cmd_make_contract(a) -> None:
    """Validate recorded requirement proposals into a contract (``contract.check_proposals``) and record it.

    ``--generation-record FILE`` is stored in the contract; a natural PR-review task's contract is refused without a
    complete one. A natural PR-review task's proposals are checked on the events that the variant's proposer is shown,
    the rendered thread (:func:`_rendered_session`; the issue, and for ``full_session`` and ``reference`` the comment's
    hunk, the comment and the reviewer's replies): a proposal not introduced at one of its user turns is rejected, a
    quote from an event it does not show is unsupported, and the reference variant warns when no scored active
    requirement is introduced at a correction event. ``check-proposals`` prints the same rejections, warnings and errors
    without writing anything. Any other task's proposals are checked on its whole session, as before.
    """
    from .contract import acceptance_gate, check_proposals, render_instruction, validate_contract
    from .tasks import now, session_for_task

    def refuse(why: str) -> SystemExit:
        return SystemExit(f"make-contract refused, nothing written: {why}")

    tdir, m = _task(a.task)
    natural = m.population == Population.natural_pr_review
    variant = ContractVariant(a.variant)
    gen = _complete_generation_record(a.generation_record, "make-contract", required_for=(
        f"the {variant.value} contract of the natural PR-review task {m.task_id}" if natural else None))
    session = session_for_task(tdir, REPO)
    props = _proposals(a.proposals)
    shown = _rendered_session(session, variant, refuse) if natural else session  # what the proposer was shown
    out = check_proposals(shown, props, proposer=a.proposer, variant=variant, natural=natural)
    c = TaskContract(contract_id=f"{m.task_id}-{variant.value}", task_id=m.task_id, session_id=session.session_id,
                     variant=variant, requirements=out.requirements, created_by=a.proposer, created_at=now(),
                     notes="; ".join(out.warnings), generation=gen)
    c = c.model_copy(update={"instruction": render_instruction(c)})
    rel = f"contracts/{variant.value}.json"
    dump(c, tdir / rel)
    dump(m.model_copy(update={"contracts": {**m.contracts, variant.value: rel}}), tdir / "task.json")
    issues = validate_contract(c, shown)  # the errors check-proposals prints; the gate reads the whole session
    ok, reasons = acceptance_gate(c, session)
    _out({"contract": rel, "n_requirements": len(c.requirements), "n_active": len(c.active()),
          "rejected_proposals": out.rejected, "warnings": out.warnings,
          "errors": [i.__dict__ for i in issues if i.severity == "error"], "gate_accepted": ok, "gate_reasons": reasons})


def cmd_check_proposals(a) -> None:
    """Check requirement proposals as ``make-contract`` would, reading only the two files named; nothing is written.

    SESSION_EVENTS is a session-events record (``tasks.render_session_events``: the ``session_events.json`` of a
    contract workspace, which holds the events of the variant's rendered thread only, and names the variant) or a whole
    session record (a task's ``session.json``). The natural PR-review rules of ``contract.check_proposals`` apply when
    its population is ``natural:pr-review``, on the events the variant's proposer is shown, as make-contract checks
    them: a session-events record's own events and variant (a ``--variant`` that is not the record's own is refused), or
    a whole natural session rendered for ``--variant``, which it then needs (:func:`_rendered_session`). A session of
    another population is checked as given: a whole session record as make-contract checks it, a session-events record
    on the events its render shows (tool texts truncated as rendered). It prints the rejected proposals, the warnings
    and the contract's validation errors as make-contract does; exit 1 if a proposal is rejected or there is an error,
    else 0.
    """
    from .contract import check_proposals, correction_event_ids, validate_contract

    def refuse(why: str) -> SystemExit:
        return SystemExit(f"check-proposals: {why}")

    try:
        data = json.loads(Path(a.session_events).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise refuse(f"{a.session_events} is not a readable JSON file ({type(exc).__name__})") from None
    events_record = isinstance(data, dict) and "format" in data
    try:
        if events_record:  # a session-events record
            try:
                from .tasks import session_from_events
            except ImportError:
                raise refuse("this tree has no tasks.session_from_events, which reads a session-events record back") from None
            session = session_from_events(data)  # it checks the record, its variant included
        else:
            session = Session.model_validate(data)
    except ValueError as exc:  # a pydantic ValidationError is a ValueError
        raise refuse(f"{a.session_events} is neither a session-events record nor a session record: "
                     f"{' '.join(str(exc).split())[:600]}") from None
    try:
        props = _proposals(a.proposals)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise refuse(f"{a.proposals} holds no proposals (a JSON list, or an object with 'requirements'): "
                     f"{type(exc).__name__}") from None
    named = data["variant"] if events_record else a.variant
    if events_record and a.variant and a.variant != named:
        raise refuse(f"--variant {a.variant} is not the variant of the session-events record {a.session_events} ({named}), "
                     "which holds the events that the proposer of its own variant is shown")
    try:
        variant = ContractVariant(named) if named else None
    except ValueError:
        raise refuse(f"unknown contract variant {named!r}") from None
    natural = session.population == Population.natural_pr_review
    if natural and not events_record:  # a whole natural session: the events its variant's proposer is shown
        if variant is None:
            raise refuse(f"{a.session_events} is a whole natural PR-review session; give --variant, since make-contract checks "
                         "the proposals on the events of that variant's rendered thread")
        session = _rendered_session(session, variant, refuse)
    out = check_proposals(session, props, proposer=a.proposer, variant=variant, natural=natural)
    contract = TaskContract(contract_id="check-proposals", task_id="check-proposals", session_id=session.session_id,
                            variant=variant or ContractVariant.full_session, requirements=out.requirements,
                            created_by=a.proposer, created_at="1970-01-01T00:00:00+00:00")
    errors = [i.__dict__ for i in validate_contract(contract, session) if i.severity == "error"]
    _out({"rejected_proposals": out.rejected, "warnings": out.warnings, "errors": errors,
          "n_requirements": len(out.requirements), "n_active": len(contract.active()),
          "variant": variant.value if variant else None, "natural_pr_review_rules": natural,
          "correction_event_ids": correction_event_ids(session) if natural else [], "written": False})
    sys.exit(1 if out.rejected or errors else 0)


def _natural_out_problem(m: TaskManifest, out: Path) -> str | None:
    """Why a natural PR-review task's material (thread text, upstream code) may not be written to ``out``; ``None`` if it
    may, and always for another task. The ``--out`` guard of export-gen-workspace (``evaluate.private_location_problem``:
    not where a git work tree could commit it, under /home/user/ext or in a Claude session's directory, §17.4, D47), and
    ``out`` must not exist yet, so that nothing is overwritten."""
    if m.population != Population.natural_pr_review:
        return None
    from .evaluate import private_location_problem

    problem = private_location_problem(out, REPO)
    if problem is None and (out.exists() or out.is_symlink()):
        problem = f"{out} exists; a natural PR-review task's material is written only to a new path"
    return problem


def cmd_render_session(a) -> None:
    """Render a task's session as text to ``--out``. For a natural PR-review task (its pseudonymised thread) the out guard
    of :func:`_natural_out_problem` applies; nothing is written when it refuses."""
    from .tasks import render_session, session_for_task

    tdir, m = _task(a.task)
    problem = _natural_out_problem(m, Path(a.out))
    if problem:
        raise SystemExit(f"render-session refused, nothing written: {problem}")
    text = render_session(session_for_task(tdir, REPO), first_prompt_only=a.first_prompt_only, include_tools=not a.no_tools)
    Path(a.out).write_text(text)
    _out({"out": a.out, "chars": len(text)})


def _sandbox_docker(tdir: Path, m: TaskManifest, state: Path, argv: list[str], timeout: float, command: str) -> dict:
    import subprocess

    tag = _image(tdir, m, command)
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
    tdir, m = _task(a.task)
    _out(_sandbox_docker(tdir, m, Path(a.state_dir), ["python", *a.args], a.timeout, "sandbox-python"))


def cmd_sandbox_pytest(a) -> None:
    tdir, m = _task(a.task)
    _out(_sandbox_docker(tdir, m, Path(a.state_dir), ["python", "-m", "pytest", "-p", "no:cacheprovider", *a.args], a.timeout,
                         "sandbox-pytest"))


def cmd_materialize(a) -> None:
    """Write a candidate's state (base snapshot + its graded patch) to a new directory, e.g. for human review.

    For a natural PR-review task (upstream code) the out guard of :func:`_natural_out_problem` applies; nothing is
    written when it refuses."""
    import shutil

    from .sandbox.docker_runner import prepare_workspace
    from .tasks import verify_snapshot

    tdir, m = _task(a.task)
    out = Path(a.out)
    problem = _natural_out_problem(m, out)
    if problem:
        raise SystemExit(f"materialize refused, nothing written: {problem}")
    if out.exists():  # before the workspace is staged, so that a refusal leaves nothing behind
        raise SystemExit(f"{out} exists; choose a new directory")
    root = _snapshot_root(tdir)
    if not (root / m.task_id).is_dir() or not verify_snapshot(tdir, root):
        raise SystemExit(f"base snapshot missing or modified; {_rebuild_hint(tdir, a.task)}")
    cand = _candidate(tdir, m, a.candidate_id)
    ws, diags, err = prepare_workspace(root / m.task_id, cand.patch)
    if ws is None:
        raise SystemExit(f"patch could not be applied: {err} {diags}")
    shutil.copytree(ws, out, symlinks=False)
    shutil.rmtree(ws, ignore_errors=True)
    out.chmod(0o755)  # the workspace copy is private; the sandbox user must be able to read it
    _out({"candidate_id": cand.candidate_id, "state_dir": str(out), "diagnostics": diags})


def cmd_export_gen_workspace(a) -> None:
    """Isolated generation workspace: base snapshot copy + selected task material only.

    Refused, with nothing written: a natural PR-review task (its agents' workspaces are built by
    ``scripts/make_agent_workspace.py``, with the roles, isolation checks and manifest of the natural arm); an
    ``--out`` in a git work tree that does not ignore it (the repository, a linked work tree or a clone of it), under
    ``/home/user/ext`` or in a Claude session's directory (``evaluate.private_location_problem``); and an ``--out`` that
    exists and is not an empty directory. It never removes a directory it did not write: when writing fails, it removes
    only what it wrote, the parent directories it created included.

    This changes the earlier behaviour, which removed an existing ``--out`` and recreated it: the frozen controlled
    workflow templates (experiments/prompts/workflows/, e.g. the held-out near-miss step "this recreates the workspace
    from scratch" and the reference-check fixer's re-export) need a new or empty ``--out`` with this version.
    """
    import shutil

    from .contract import render_instruction
    from .evaluate import private_location_problem
    from .tasks import render_session, session_for_task

    def refuse(why: str) -> SystemExit:
        return SystemExit(f"export-gen-workspace refused, nothing written: {why}")

    tdir, m = _task(a.task)
    if m.population == Population.natural_pr_review:
        raise refuse(f"{m.task_id} is a natural PR-review task; build its agents' workspaces with scripts/make_agent_workspace.py")
    out = Path(a.out)
    problem = private_location_problem(out, REPO)
    if problem:
        raise refuse(problem)
    if out.is_symlink() or (out.exists() and not (out.is_dir() and not any(out.iterdir()))):
        raise refuse(f"{out} exists and is not an empty directory; choose a new one (a directory this command did not "
                     "write is never removed)")
    base = _snapshot_root(tdir) / m.task_id
    if not base.is_dir():
        raise refuse(f"the base snapshot of {m.task_id} is not built at {base}; run `tracecontract snapshot {a.task}` first")
    files: dict[str, str] = {}  # everything is read before anything is written
    if a.contract:
        if a.contract not in m.contracts:
            raise refuse(f"{m.task_id} has no {a.contract!r} contract")
        c = load(tdir / m.contracts[a.contract], TaskContract)
        order = {p.event_id: i + 1 for i, p in enumerate(session_for_task(tdir, REPO).user_prompts())}
        reqs = [{"req_id": r.req_id, "kind": r.kind.value, "statement": r.statement, "observable": r.observable,
                 "introduced_in_user_turn": order.get(r.introduced_at)}
                for r in c.active() if r.scored]
        files["contract.json"] = json.dumps({"variant": c.variant.value, "requirements": reqs}, indent=2) + "\n"
        files["instruction.md"] = render_instruction(c)
    if a.with_reference_patch:
        from .patches import filter_patch

        ref = next((load(tdir / p, Candidate) for p in m.candidates if "reference" in p), None)
        if ref is None:
            raise refuse(f"{m.task_id} has no reference candidate")
        # By default only the graded part of the reference diff: the session agent's test
        # files belong to the repository-test baseline (B1) and are left out (decision log
        # D37, D40). --with-reference-tests restores the full diff.
        files["reference.diff"] = ref.patch if a.with_reference_tests else filter_patch(ref.patch)[0]
    if a.with_session:
        files["session.txt"] = render_session(session_for_task(tdir, REPO))
    if a.with_first_prompt:
        files["session_first_prompt.txt"] = render_session(session_for_task(tdir, REPO), first_prompt_only=True)
    new_dirs = [d for d in (out.absolute(), *out.absolute().parents) if not d.exists()]  # what mkdir makes, deepest first
    out.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(base, out / "base", symlinks=False)
        for name, text in files.items():
            (out / name).write_text(text)
    except BaseException:  # remove what this call wrote, and nothing else (the directory was new or empty)
        if new_dirs:
            shutil.rmtree(out, ignore_errors=True)
            for d in new_dirs[1:]:  # the parent directories it created, while they are empty
                try:
                    d.rmdir()
                except OSError:
                    break
        else:
            for p in out.iterdir():
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
        raise
    _out({"workspace": str(out), "files": sorted(p.name for p in out.iterdir())})


def cmd_review_packet(a) -> None:
    """Blinded review packet for human labeling (annotation guide v0.4).

    The ``--out`` guard of ``export-gen-workspace`` applies, and every task must keep its base snapshot under the same
    root (``snapshots/``, or ``data/natural/snapshots`` for natural PR-review tasks); nothing is written otherwise."""
    from .evaluate import private_location_problem
    from .review import export_packet

    def refuse(why: str) -> SystemExit:
        return SystemExit(f"review-packet refused, nothing written: {why}")

    tdirs = [Path(t).resolve() for t in a.tasks]
    problem = private_location_problem(Path(a.out), REPO)
    if problem:
        raise refuse(problem)
    found = sorted({_snapshot_root(t) for t in tdirs})
    if len(found) != 1:
        raise refuse(f"the tasks keep their base snapshots under {len(found)} roots ({', '.join(map(str, found))}); "
                     "write one packet per root")
    _out(export_packet(tdirs, Path(a.out), Path(a.key), snapshot_root=found[0], repo_root=REPO, seed=a.seed))


def _tasks_root(a) -> Path:
    """``--tasks-root`` (default: the repository's ``tasks/``; ``data/natural/tasks`` for the natural arm)."""
    return Path(a.tasks_root).resolve() if a.tasks_root else REPO / "tasks"


def cmd_merge_reviews(a) -> None:
    """Merge reviewers' label files from a blinded packet into the candidate records."""
    from .review import merge_labels

    _out(merge_labels([Path(f) for f in a.label_files], Path(a.key), _tasks_root(a), min_reviewers=a.min_reviewers,
                      dry_run=a.dry_run))


def cmd_evaluate(a) -> None:
    """Grade the tasks' frozen verifiers into ``<--out-root>/<run id>`` (``evaluate.run_matrix``).

    Each task's base snapshot is looked up under its own root (:func:`_snapshot_root`). A run with a natural PR-review
    task must go to a git-ignored root such as ``data/natural/runs``; every refusal comes before anything is written.
    """
    from .evaluate import RunRefused, TaskRefused, run_matrix
    from .schemas import Split
    from .strata import StratumError

    tdirs = [Path(t).resolve() for t in a.tasks]
    snapshot_roots = {}
    for td in tdirs:
        snapshot_roots[_task(str(td))[1].task_id] = _snapshot_root(td)
    out_root = Path(a.out_root).resolve() if a.out_root else REPO / "results" / "runs"
    try:
        out = run_matrix(tdirs, run_id=a.run_id, out_root=out_root,
                         cache_dir=CACHE / "images", snapshot_root=snapshot_roots, split=Split(a.split),
                         conditions=a.conditions or None, repeats=a.repeats, require_frozen=not a.allow_unfrozen,
                         repo_root=REPO, pilot=a.pilot, strata=a.strata, only_strata=a.only_strata,
                         extra_verifiers=a.with_extra_verifiers)
    except TaskRefused as exc:  # nothing was written
        raise SystemExit(f"evaluate refused by the acceptance gate:\n{exc}") from None
    except StratumError as exc:  # nothing was written
        raise SystemExit(f"evaluate refused: {exc}") from None
    except RunRefused as exc:  # nothing was written
        raise SystemExit(f"evaluate refused, nothing written: {exc}") from None
    _out({"run_dir": str(out)})


def cmd_analyze(a) -> None:
    from .analysis import SENSITIVITY_JSON, SENSITIVITY_MD, ConditionConflict, MixedPopulations, SensitivityExclusionsError, analyze
    from .strata import StratumError

    run = Path(a.run_dir)
    exclusions = [Path(f) for f in a.sensitivity_exclusions or []]
    try:
        res = analyze(run, _tasks_root(a), allow_proposed=a.allow_proposed_labels, n_boot=a.n_boot,
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

    out = build_report(Path(a.run_dir), _tasks_root(a), REPO, Path(a.out))
    _out({"report": str(out)})


def _pr_reconstruction_check(a, tdir: Path) -> None:
    """``reconstruction-check`` of a natural PR-review task: the record compile-pr-task made, as the gate reads it.

    Its record comes from the PR's commits (``natural_pr.PR_METHOD``), not from a session transcript, so nothing is
    re-run and nothing is written: ``--write`` is refused, since the session method would overwrite the PR record.
    The exit code follows the gate (``natural_pr.recorded_pr_check``, as ``contract.task_gate`` reads it): 0 if the record
    counts, 1 if it is a current record of a failed check (the gate refuses the task), else 2 (no record, or a stale,
    malformed or other-method one: the gate gives a reason).
    """
    from .natural_pr import PR_METHOD, recorded_pr_check
    from .reconstruction import RECORD, RecordCheck

    if a.write:
        raise SystemExit(f"reconstruction-check refused, nothing written: {tdir.name} is a natural PR-review task; its "
                         f"{RECORD} is the PR reconstruction record ({PR_METHOD}) that `tracecontract compile-pr-task` "
                         "writes, and --write would replace it with the session method's")
    try:
        rc = recorded_pr_check(tdir, REPO)
    except Exception as exc:  # noqa: BLE001 - a malformed record (e.g. "checks": null) is reported, never a traceback
        rc = RecordCheck(None, [f"{RECORD} is malformed ({type(exc).__name__}); natural_pr.recorded_pr_check cannot read it"])
    checks: list[dict] = []
    method = None
    try:
        rec = json.loads((tdir / RECORD).read_text(encoding="utf-8"))
        method = rec.get("method")
        raw = rec.get("checks")
        if isinstance(raw, list):  # "checks": null or another non-list shows no checks
            checks = [{"check_id": c.get("check_id"), "status": c.get("status")} for c in raw if isinstance(c, dict)]
    except (OSError, ValueError, AttributeError):
        pass
    _out({"task_id": tdir.name, "record": RECORD, "method": method, "expected_method": PR_METHOD, "status": rc.status,
          "counts_for_the_gate": rc.ok, "failed": rc.failed, "problems": rc.problems, "checks": checks,
          "note": "natural PR-review task: the recorded PR reconstruction check is read; nothing is re-run or written"})
    sys.exit(0 if rc.ok else 1 if rc.failed else 2)


def cmd_reconstruction_check(a) -> None:
    """Check a task's base snapshot against its session (reconstruction:v2).

    Exit 1 if a check failed; else exit 2 if the report is incomplete (a check was unavailable or
    not checkable, or a changed file has no passed item in check b or c); exit 0 only if it passed.
    A natural PR-review task's recorded PR check is printed instead (:func:`_pr_reconstruction_check`).
    """
    from .reconstruction import RECORD, check_task
    from .store import write_json

    tdir = Path(a.task).resolve()
    if roots.is_natural_pr(tdir):
        _pr_reconstruction_check(a, tdir)
        return
    rep = check_task(tdir, REPO, _snapshot_root(tdir)).to_dict()
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
    g.add_argument("--generation-record", metavar="FILE", help="the whole record as JSON instead of the flags above: a "
                   "generation record as a spec stores it, or an object with the flags' run fields")
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
    p.add_argument("--generation-record", metavar="FILE", help="the generation record of the agent run that constructed "
                   "the candidate (JSON, as for build-verifier); kept with a dev attack, valid alternative or near miss, "
                   "and required for one of a natural PR-review task")
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
    p.add_argument("--proposer", required=True)
    p.add_argument("--generation-record", metavar="FILE", help="the generation record of the agent run that wrote the "
                   "proposals (JSON, as for build-verifier); stored in the contract, and required for a natural PR-review task")
    p.set_defaults(fn=cmd_make_contract)
    p = sub.add_parser("check-proposals", help="check requirement proposals as make-contract would (rejections, warnings, "
                       "errors); reads only the two files named and writes nothing; exit 1 if a proposal is rejected")
    p.add_argument("session_events", help="a session-events record (session_events.json of a contract workspace) or a "
                   "session record (a task's session.json)")
    p.add_argument("proposals", help="the proposals: a JSON list, or an object with 'requirements'")
    p.add_argument("--variant", choices=["initial_only", "full_session", "reference"],
                   help="the contract variant: a session-events record's own (the default; another is refused); required "
                   "for a whole natural PR-review session record, which is checked on that variant's rendered thread")
    p.add_argument("--proposer", default="check-proposals", help="proposer recorded on the checked requirements")
    p.set_defaults(fn=cmd_check_proposals)
    p = sub.add_parser("render-session", help="render a task's session as text for model-based reconstruction (a natural "
                       "PR-review thread only to a new file that no git work tree could commit)")
    p.add_argument("task"); p.add_argument("--out", required=True); p.add_argument("--first-prompt-only", action="store_true")
    p.add_argument("--no-tools", action="store_true"); p.set_defaults(fn=cmd_render_session)
    p = sub.add_parser("sandbox-python", help="run python against a candidate state dir in the task image (offline, unprivileged)")
    p.add_argument("task"); p.add_argument("state_dir"); p.add_argument("--timeout", type=float, default=120)
    p.add_argument("args", nargs=argparse.REMAINDER); p.set_defaults(fn=cmd_sandbox_python)
    p = sub.add_parser("sandbox-pytest", help="run pytest against a candidate state dir in the task image (offline, unprivileged)")
    p.add_argument("task"); p.add_argument("state_dir"); p.add_argument("--timeout", type=float, default=900)
    p.add_argument("args", nargs=argparse.REMAINDER); p.set_defaults(fn=cmd_sandbox_pytest)
    p = sub.add_parser("materialize", help="write a candidate's graded state (base + patch, protected paths removed) to a new "
                       "directory (for a natural PR-review task, one that no git work tree could commit)")
    p.add_argument("task"); p.add_argument("candidate_id"); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_materialize)
    p = sub.add_parser("export-gen-workspace", help="isolated workspace for a generation agent, in a new or empty --out "
                       "(an existing workspace is never removed or recreated; refused for natural PR-review tasks)")
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
    p.add_argument("--tasks-root", help="the directory holding the task directories (default: tasks/; data/natural/tasks "
                   "for the natural arm)")
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
    p.add_argument("--out-root", help="where the run directory <run id> is written (default: results/runs); a run with a "
                   "natural PR-review task needs a git-ignored root such as data/natural/runs")
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
    p.add_argument("--tasks-root", help="the directory holding the run's task directories (default: tasks/; "
                   "data/natural/tasks for a natural run)")
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("report", help="static HTML report for a run (from recorded artifacts only)")
    p.add_argument("run_dir"); p.add_argument("--out", required=True)
    p.add_argument("--tasks-root", help="the directory holding the run's task directories (default: tasks/; "
                   "data/natural/tasks for a natural run)")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("reconstruction-check", help="check a task's base snapshot against its session transcript and captured "
                       "states; for a natural PR-review task, print its recorded PR reconstruction check")
    p.add_argument("task"); p.add_argument("--write", action="store_true", help="write tasks/<id>/reconstruction_check.json "
                   "(refused for a natural PR-review task, whose record compile-pr-task writes)")
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
