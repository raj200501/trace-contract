"""Compile sessions into task directories and (re)build their base snapshots.

Task directory layout (``tasks/<task_id>/``)::

    task.json                    TaskManifest
    provenance.json              ProvenanceRecord
    snapshot.json                Snapshot (manifest hash, fidelity, leakage check)
    contracts/<variant>.json     TaskContract (reference, full_session, initial_only)
    candidates/<id>.json         Candidate (patch inline)
    verifiers/<id>/spec.json     VerifierSpec
    verifiers/<id>/tests/...     process-separated test files
    verifiers/repo_tests/overlay repository test files from the reference state (B1)

Base snapshots are rebuilt from the pinned source into ``snapshots/<task_id>``
(not committed); their manifest hash must match ``snapshot.json``.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .contract import requirements_from_proposals, validate_contract
from .controlled import audit_access, candidate_from_state
from .ingest.claude_code import parse_claude_code_jsonl
from .schemas import (
    Candidate,
    CandidateOrigin,
    ContractVariant,
    Eligibility,
    EventKind,
    Label,
    LabelerKind,
    Population,
    ProvenanceRecord,
    RedactionStatus,
    Review,
    ReviewerKind,
    Session,
    Snapshot,
    SnapshotSource,
    Split,
    TaskContract,
    TaskManifest,
    sha256_text,
)
from .snapshot import build_snapshot, leakage_check, manifest, manifest_sha256
from .store import dump, load


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_turn(session: Session, text: str) -> str:
    """Event id of the user prompt carrying scripted turn ``text`` (exact or contained)."""
    want = text.strip()
    for ev in session.user_prompts():
        if ev.text.strip() == want or want in ev.text:
            return ev.event_id
    raise KeyError("scripted turn not found among user prompts")


def rebuild_snapshot(manifest_: TaskManifest, snapshot_root: Path, cache_dir: Path) -> Path:
    dest = snapshot_root / manifest_.task_id
    build_snapshot(manifest_.task_id, manifest_.snapshot_source, dest, cache_dir / "git")
    for rel, content in manifest_.snapshot_overlays.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return dest


def verify_snapshot(task_dir: Path, snapshot_root: Path) -> bool:
    m = load(task_dir / "task.json", TaskManifest)
    snap = load(task_dir / (m.snapshot or "snapshot.json"), Snapshot)
    return manifest_sha256(manifest(snapshot_root / m.task_id)) == snap.file_manifest_sha256


def compile_controlled_task(
    *,
    scenario: dict,
    reference_proposals: list[dict],
    transcript: Path,
    states: dict[str, Path],
    workspace_record: dict,
    tasks_root: Path,
    snapshot_root: Path,
    cache_dir: Path,
    repo_test_args: list[str],
    candidate_pythonpath: str,
    allowed_roots: tuple[str, ...],
    overlays: dict[str, str] | None = None,
) -> Path:
    """Compile one controlled session (protocol CS-v1) into ``tasks/<scenario_id>``."""
    tid = scenario["scenario_id"]
    tdir = tasks_root / tid
    (tdir / "contracts").mkdir(parents=True, exist_ok=True)
    (tdir / "candidates").mkdir(parents=True, exist_ok=True)

    # 1. Transcript -> session; contamination audit.
    turns = [v for k, v in scenario["turns"].items() if k.startswith("U")]
    session = parse_claude_code_jsonl(transcript, population=Population.controlled, source="controlled:tracecontract",
                                      relpath=f"data/controlled/transcripts/{tid}.jsonl", scripted_turns=turns)
    findings = audit_access(session, allowed_roots)
    contaminated = [f for f in findings if f.reason == "contamination"]

    # 2. Base snapshot (rebuilt from the pinned source + recorded overlays).
    src = SnapshotSource(repo_url=scenario["repo_url"], commit=scenario["commit"])
    m = TaskManifest(
        task_id=tid, family_id=f"{tid}", population=Population.controlled, status="draft", provenance="provenance.json",
        snapshot_source=src, snapshot="snapshot.json", snapshot_overlays=overlays or {},
        env_requirements=workspace_record["env_pins"], candidate_pythonpath=candidate_pythonpath,
        repo_test_args=repo_test_args, scripted_turns=turns,
    )
    base = rebuild_snapshot(m, snapshot_root, cache_dir)
    rec_snap = Snapshot.model_validate(workspace_record["snapshot"])
    rebuilt_hash = manifest_sha256(manifest(base))

    # 3. Candidates from captured states.
    cands: list[Candidate] = []
    final = states["final"]
    ref = candidate_from_state(task_id=tid, candidate_id=f"{tid}-reference", base=base, state=final,
                               origin=CandidateOrigin.reference, split=Split.dev,
                               produced_by=f"session:{session.session_id}@final",
                               description="Final state of the controlled session after all user turns.")
    cands.append(ref)
    if "after_U1" in states:
        cands.append(candidate_from_state(
            task_id=tid, candidate_id=f"{tid}-pre-correction", base=base, state=states["after_U1"],
            origin=CandidateOrigin.observed_pre_correction, split=Split.eval,
            produced_by=f"session:{session.session_id}@after_U1",
            description="Agent state after the initial request, before the scripted correction (naturally observed)."))
    for split in (Split.dev, Split.eval):
        cands.append(Candidate(candidate_id=f"{tid}-noop-{split.value}", task_id=tid, origin=CandidateOrigin.noop,
                               split=split, patch="", patch_sha256=sha256_text(""), produced_by="base snapshot",
                               description="No-op: the unchanged base snapshot.",
                               labels=[Label(value="invalid", labeler="construction", labeler_kind=LabelerKind.construction,
                                             timestamp=now(), note="no change made")]))
    for c in cands:
        dump(c, tdir / "candidates" / f"{c.candidate_id}.json")
    m = m.model_copy(update={"candidates": [f"candidates/{c.candidate_id}.json" for c in cands]})

    # 4. Leakage check (base must not already contain the final solution).
    leak = leakage_check(base, ref.patch)
    snap = rec_snap.model_copy(update={"leakage_check": leak, "file_manifest_sha256": rebuilt_hash,
                                       "environment": {"image": workspace_record["image"],
                                                       "image_id": workspace_record["image_id"],
                                                       "pins": workspace_record["env_pins"]}})
    dump(snap, tdir / "snapshot.json")

    # 5. Reference contract from the pre-registered intended requirements.
    turn_ids = {k: find_turn(session, v) for k, v in scenario["turns"].items() if k.startswith("U")}
    props = []
    for p in reference_proposals:
        p = dict(p)
        p["introduced_at"] = turn_ids[p.pop("turn")]
        p["evidence"] = [{"event_id": turn_ids[e["turn"]], "quote": e["quote"]} for e in p.get("evidence", [])]
        props.append(p)
    out = requirements_from_proposals(session, props, proposer="study-design:pre-registered")
    if out.rejected:
        raise ValueError(f"reference proposals rejected: {out.rejected}")
    review = Review(reviewer="builder", reviewer_kind=ReviewerKind.model, decision="accept", timestamp=now(),
                    note="Drafted from the pre-registered scenario; awaiting human review.")
    reqs = [r.model_copy(update={"reviews": [review]}) for r in out.requirements]
    ref_contract = TaskContract(contract_id=f"{tid}-reference", task_id=tid, session_id=session.session_id,
                                variant=ContractVariant.reference, requirements=reqs, created_by="study-design",
                                created_at=now(), notes="; ".join(out.warnings))
    errors = [i for i in validate_contract(ref_contract, session) if i.severity == "error"]
    if errors:
        raise ValueError(f"reference contract invalid: {errors}")
    dump(ref_contract, tdir / "contracts" / "reference.json")
    m = m.model_copy(update={"contracts": {"reference": "contracts/reference.json"}})

    # 6. Provenance.
    reasons = [f"contamination: {f.tool} {f.path}" for f in contaminated]
    if not leak.passed:
        reasons.append(f"leakage: {leak.leaked_paths}")
    prov = ProvenanceRecord(
        record_id=f"prov-{tid}", session_id=session.session_id, population=Population.controlled,
        source_url="controlled session (this study)", source_id=tid, source_revision=None,
        repo_url=scenario["repo_url"], base_commit=scenario["commit"],
        licenses={"code": scenario["code_license"], "transcript": "generated for this study"},
        permission_basis="Public repository under a permissive license; session generated by the study.",
        trace_sha256=session.trace_sha256, snapshot_manifest_sha256=rebuilt_hash,
        capture_method="Claude Code general-purpose subagent; scripted user turns (CS-v1); states captured between turns",
        redaction_status=RedactionStatus.not_needed_controlled, task_family_id=m.family_id,
        eligibility=Eligibility.rejected if reasons else Eligibility.pending_review, rejection_reasons=reasons,
        accessed=now(),
        notes=json.dumps({"access_findings": [f.__dict__ for f in findings], "scenario_sha256": scenario.get("_sha256"),
                          "workspace_snapshot_manifest": rec_snap.file_manifest_sha256}),
    )
    dump(prov, tdir / "provenance.json")
    status = "rejected" if reasons else "pending_review"
    m = m.model_copy(update={"status": status})
    dump(m, tdir / "task.json")

    # 7. Keep the transcript with the task data (controlled data; generated by the study).
    tdest = tasks_root.parent / "data" / "controlled" / "transcripts" / f"{tid}.jsonl"
    tdest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(transcript, tdest)
    return tdir


def session_for_task(task_dir: Path, repo_root: Path) -> Session:
    m = load(task_dir / "task.json", TaskManifest)
    pop = m.population
    path = repo_root / "data" / ("controlled" if pop == Population.controlled else "fixtures") / "transcripts" / f"{m.task_id}.jsonl"
    return parse_claude_code_jsonl(path, population=pop, source="controlled:tracecontract",
                                   relpath=f"data/controlled/transcripts/{m.task_id}.jsonl", scripted_turns=m.scripted_turns)


def render_session(session: Session, *, include_tools: bool = True, max_tool_chars: int = 600,
                   first_prompt_only: bool = False) -> str:
    """Plain-text rendering of a session for model-based reconstruction.

    User prompts and assistant text are kept verbatim with their event ids; tool
    calls are abbreviated. ``first_prompt_only`` renders only the first user request
    (the initial-request-only baseline input).
    """
    lines = []
    prompts = session.user_prompts()
    if first_prompt_only:
        p = prompts[0]
        return f"[{p.event_id}] USER:\n{p.text}\n"
    for ev in session.events:
        if ev.kind == EventKind.user_prompt:
            lines.append(f"[{ev.event_id}] USER:\n{ev.text}\n")
        elif ev.kind == EventKind.assistant_text and ev.text.strip():
            lines.append(f"[{ev.event_id}] ASSISTANT:\n{ev.text}\n")
        elif include_tools and ev.kind == EventKind.tool_call:
            t = ev.text if len(ev.text) <= max_tool_chars else ev.text[:max_tool_chars] + " ...[truncated]"
            lines.append(f"[{ev.event_id}] TOOL CALL {ev.tool_name}: {t}")
        elif include_tools and ev.kind == EventKind.tool_result:
            t = ev.text if len(ev.text) <= max_tool_chars else ev.text[:max_tool_chars] + " ...[truncated]"
            lines.append(f"[{ev.event_id}] TOOL RESULT: {t}")
    return "\n".join(lines)
