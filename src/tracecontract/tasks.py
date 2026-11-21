"""Compile sessions into task directories and (re)build their base snapshots.

Task directory layout (``tasks/<task_id>/``)::

    task.json                    TaskManifest
    provenance.json              ProvenanceRecord
    snapshot.json                Snapshot (manifest hash, fidelity; the pilot's records also hold the
                                 vacuous leakage check, D47, which new builds no longer record)
    reconstruction_check.json    the base checked against its own session (reconstruction.check_task)
    contracts/<variant>.json     TaskContract (reference, full_session, initial_only)
    candidates/<id>.json         Candidate (patch inline)
    verifiers/<id>/spec.json     VerifierSpec
    verifiers/<id>/tests/...     process-separated test files
    verifiers/repo_tests/overlay repository test files from the reference state (B1)

Base snapshots are rebuilt from the pinned source into ``snapshots/<task_id>``
(not committed); their manifest hash must match ``snapshot.json``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import requirements_from_proposals, validate_contract
from .controlled import audit_access, candidate_from_state
from .ingest.claude_code import parse_claude_code_jsonl
from .schemas import (
    Candidate,
    CandidateOrigin,
    ContractVariant,
    Eligibility,
    Event,
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
    SourceRef,
    Split,
    TaskContract,
    TaskManifest,
    canonical_json,
    sha256_text,
)
from .snapshot import build_snapshot, manifest, manifest_sha256
from .store import dump, load, write_json


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
    sanitization: dict | None = None,
) -> Path:
    """Compile one controlled session (protocol CS-v1) into ``tasks/<scenario_id>``.

    ``transcript`` must be the output of :func:`ingest.claude_code.sanitize_transcript` and
    ``sanitization`` the record it returned; it is kept in the provenance record.

    ``snapshot.json`` records no leakage check: as this build called it, the check compared the
    base with itself and passed even when the base held the solution (D47). Instead the build
    checks the base against the session's own record (:func:`reconstruction.check_task`) and
    writes ``reconstruction_check.json``; the acceptance gate and the pre-flight require it to
    pass (protocol v0.8 §16.5).
    """
    if not sanitization or sanitization.get("sanitized_sha256") != hashlib.sha256(Path(transcript).read_bytes()).hexdigest():
        raise ValueError("pass the sanitize_transcript record of this transcript (controlled transcripts are sanitised too)")
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

    # 4. Snapshot record. No leakage check: snapshot.leakage_check compared the base with itself, a
    # vacuous pass (D47). Step 8 checks the base against the session instead.
    snap = rec_snap.model_copy(update={"leakage_check": None, "file_manifest_sha256": rebuilt_hash,
                                       "environment": {"image": workspace_record["image"],
                                                       "image_id": workspace_record["image_id"],
                                                       "pins": workspace_record["env_pins"]}})
    dump(snap, tdir / "snapshot.json")

    # 5. Reference contract from the scenario's intended requirements (hashed and logged
    # locally before the session; not a formal preregistration).
    turn_ids = {k: find_turn(session, v) for k, v in scenario["turns"].items() if k.startswith("U")}
    props = []
    for p in reference_proposals:
        p = dict(p)
        p["introduced_at"] = turn_ids[p.pop("turn")]
        p["evidence"] = [{"event_id": turn_ids[e["turn"]], "quote": e["quote"]} for e in p.get("evidence", [])]
        props.append(p)
    out = requirements_from_proposals(session, props, proposer="study-design:hashed-scenario")
    if out.rejected:
        raise ValueError(f"reference proposals rejected: {out.rejected}")
    review = Review(reviewer="builder", reviewer_kind=ReviewerKind.model, decision="accept", timestamp=now(),
                    note="Drafted from the hashed scenario; awaiting human review.")
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
    prov = ProvenanceRecord(
        record_id=f"prov-{tid}", session_id=session.session_id, population=Population.controlled,
        source_url="controlled session (this study)", source_id=tid, source_revision=None,
        repo_url=scenario["repo_url"], base_commit=scenario["commit"],
        licenses={"code": scenario["code_license"], "transcript": "generated for this study"},
        permission_basis="Public repository under a permissive license; session generated by the study.",
        trace_sha256=session.trace_sha256, snapshot_manifest_sha256=rebuilt_hash,
        capture_method="Claude Code general-purpose subagent; scripted user turns (CS-v1); states captured between turns",
        redaction_status=RedactionStatus.redacted_by_us, task_family_id=m.family_id,
        eligibility=Eligibility.rejected if reasons else Eligibility.pending_review, rejection_reasons=reasons,
        accessed=now(),
        notes=json.dumps({"access_findings": [f.__dict__ for f in findings], "scenario_sha256": scenario.get("_sha256"),
                          "workspace_snapshot_manifest": rec_snap.file_manifest_sha256,
                          "transcript_sanitization": sanitization}),
    )
    dump(prov, tdir / "provenance.json")
    status = "rejected" if reasons else "pending_review"
    m = m.model_copy(update={"status": status})
    dump(m, tdir / "task.json")

    # 7. Keep the transcript with the task data (controlled data; generated by the study).
    tdest = tasks_root.parent / "data" / "controlled" / "transcripts" / f"{tid}.jsonl"
    tdest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(transcript, tdest)

    # 8. Reconstruction check: the base against the session's own record (protocol v0.8 §16.5). The
    # scenario is sealed outside the repository during the build, so its workspace is passed on.
    from .reconstruction import RECORD, check_task  # reconstruction imports this module

    rep = check_task(tdir, tasks_root.parent, snapshot_root, scenario_workspace=scenario.get("workspace"))
    write_json(rep.to_dict(), tdir / RECORD)
    return tdir


_TRANSCRIPT_DIRS = {Population.controlled: "data/controlled/transcripts", Population.fixture: "data/fixtures/transcripts",
                    Population.natural: "data/natural/transcripts"}
# A natural PR-review task keeps its pseudonymised session (a Session record, not a transcript) in its own directory,
# which lies under data/natural/ and is git-ignored (natural_pr.compile_pr_task; protocol v0.9 §17.4).
PR_SESSION_FILE = "session.json"


def _transcript_rel(m: TaskManifest) -> str:
    if m.population not in _TRANSCRIPT_DIRS:
        raise FileNotFoundError(f"population {m.population.value!r} keeps no session transcript in the repository")
    return f"{_TRANSCRIPT_DIRS[m.population]}/{m.task_id}.jsonl"


def transcript_path(task_dir: Path, repo_root: Path) -> Path:
    """Where a task's sanitised transcript is kept: ``data/<population>/transcripts/<id>.jsonl`` under ``repo_root``.

    Raises :class:`FileNotFoundError` for a population that keeps no transcript there.
    """
    return repo_root / _transcript_rel(load(task_dir / "task.json", TaskManifest))


def session_for_task(task_dir: Path, repo_root: Path) -> Session:
    m = load(task_dir / "task.json", TaskManifest)
    if m.population == Population.natural_pr_review:
        if not (task_dir / PR_SESSION_FILE).is_file():
            raise FileNotFoundError(f"{m.task_id}: no {PR_SESSION_FILE}")
        return load(task_dir / PR_SESSION_FILE, Session)
    pop, rel = m.population, _transcript_rel(m)
    return parse_claude_code_jsonl(repo_root / rel, population=pop, source=f"{pop.value}:tracecontract",
                                   relpath=rel, scripted_turns=m.scripted_turns)


# A natural PR-review session's source format (ingest.github_pr.SOURCE_FORMAT; a test checks that the two agree). Such a
# session is rendered as its thread, by ingest.github_pr.render_pr_thread, which this module imports only when needed.
PR_THREAD_FORMAT = "aidev_pr_thread_v1"
SESSION_EVENTS_FORMAT = "tracecontract/session-events/v1"


def render_session(session: Session, *, include_tools: bool = True, max_tool_chars: int = 600,
                   first_prompt_only: bool = False) -> str:
    """Plain-text rendering of a session for model-based reconstruction.

    User prompts and assistant text are kept verbatim with their event ids; tool
    calls are abbreviated. ``first_prompt_only`` renders only the first user request
    (the initial-request-only baseline input).

    A natural PR-review session (source format ``aidev_pr_thread_v1``) is rendered as its thread by
    :func:`ingest.github_pr.render_pr_thread`: the variant ``initial_only`` (the banner and the linked issue) for
    ``first_prompt_only``, else ``full_session`` (the banner, the issue, the comment's diff hunk, the review comment
    and the reviewer's later replies). It shows no tool call, so ``include_tools`` and ``max_tool_chars`` do not apply
    to it: never a commit message, and the PR body only in the full thread of a PR without a linked issue (in the
    issue's place, labelled AGENT), whose first-prompt render is refused (``ValueError``;
    :func:`ingest.github_pr.pr_thread_events` says why, and what else is refused).
    """
    if session.source_format == PR_THREAD_FORMAT:
        from .ingest.github_pr import render_pr_thread

        return render_pr_thread(session, ContractVariant.initial_only if first_prompt_only else ContractVariant.full_session)
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


def _shown_events(session: Session, first_prompt_only: bool, max_tool_chars: int = 600) -> list[dict[str, Any]]:
    """The events that :func:`render_session` shows of a session other than a PR thread, with its defaults, each with
    the text it shows: a tool call's or result's text truncated as rendered, and a tool call's tool name."""
    if first_prompt_only:
        p = session.user_prompts()[0]
        return [{"event_id": p.event_id, "kind": p.kind.value, "text": p.text}]
    out: list[dict[str, Any]] = []
    for ev in session.events:
        if ev.kind == EventKind.user_prompt or (ev.kind == EventKind.assistant_text and ev.text.strip()):
            out.append({"event_id": ev.event_id, "kind": ev.kind.value, "text": ev.text})
        elif ev.kind in (EventKind.tool_call, EventKind.tool_result):
            t = ev.text if len(ev.text) <= max_tool_chars else ev.text[:max_tool_chars] + " ...[truncated]"
            out.append({"event_id": ev.event_id, "kind": ev.kind.value, "text": t}
                       | ({"tool_name": ev.tool_name} if ev.kind == EventKind.tool_call else {}))
    return out


def render_session_events(session: Session, variant: str | ContractVariant) -> str:
    """The events that a contract variant's proposer sees in its session text, as JSON: ``session_events.json`` of the
    contract workspaces, which check-proposals reads back with :func:`session_from_events`.

    The session text is :func:`render_session`, with ``first_prompt_only`` for ``initial_only``; ``full_session`` and
    ``reference`` (whose drafter reads the whole thread) have the full render. Each event has its id, its kind and the
    text shown: for a PR thread, the event's text with its role in the thread (``initial_request``,
    ``correction_context``, ``correction`` or ``reply``); for any other session, the user prompts and assistant texts,
    and the tool calls (with the tool name) and results truncated as rendered. The record also names the session,
    its population and source format, the variant and the sha256 of the render (``render_sha256``), and for a PR
    thread it carries the banner (``notice``) and, for the full thread only, the commented path that the headers
    name. It holds nothing that the render does not show.
    """
    v = ContractVariant(variant)
    first = v == ContractVariant.initial_only
    data: dict[str, Any] = {"format": SESSION_EVENTS_FORMAT, "session_id": session.session_id,
                            "population": session.population.value, "source_format": session.source_format, "variant": v.value,
                            "render_sha256": sha256_text(render_session(session, first_prompt_only=first))}
    if session.source_format == PR_THREAD_FORMAT:
        from .ingest.github_pr import PR_THREAD_BANNER, pr_thread_events

        data["notice"] = PR_THREAD_BANNER
        if not first and session.metadata.get("commented_path"):
            data["commented_path"] = session.metadata["commented_path"]
        thread = pr_thread_events(session, ContractVariant.initial_only if first else ContractVariant.full_session)
        data["events"] = [{"event_id": ev.event_id, "kind": ev.kind.value, "role": role, "text": ev.text} for role, ev in thread]
    else:
        data["events"] = _shown_events(session, first)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def session_from_events(data: str | bytes | dict[str, Any], *, verify: bool = True) -> Session:
    """The session that a :func:`render_session_events` record describes (for check-proposals).

    It holds the rendered events only, in their order and indexed from 0, each with its id, kind and the text shown (a
    tool call with its tool name). For a PR thread, ``metadata["events"]`` maps the roles to the event ids as the
    whole session does (``initial_request``, ``correction_context``, ``correction``, ``replies``), and
    ``metadata["commented_path"]`` is the path the headers name. On it, ``contract.requirements_from_proposals`` and
    ``contract.validate_contract`` decide a proposal that names rendered events only as they do on the whole session;
    a quote from a truncated tool text can match only its shown part.

    ``verify`` (the default) refuses a record that is not exactly what :func:`render_session_events` gives for the
    session it describes (:func:`_check_record`), also when the render stays the same, as it does for an added event
    that no render shows, a reordered thread, a variant's record carrying another's events or another notice. It also
    refuses what neither the render nor that round trip shows: a thread event of another kind than its role's
    (``ingest.github_pr.PR_THREAD_ROLE_KINDS``; the headers come from the roles) and a population that does not go
    with the source format, on which check-proposals' natural rules depend. These checks compare the record with
    itself only: a record rewritten consistently (an event added with its role, its kind and a new ``render_sha256``)
    describes another session, which only the whole session, as make-contract reads it, tells apart. A record that is
    not one, or that is refused, raises :class:`ValueError`.
    """
    try:
        d = json.loads(data) if isinstance(data, (str, bytes)) else data
        if not isinstance(d, dict) or d.get("format") != SESSION_EVENTS_FORMAT:
            raise ValueError(f"not a {SESSION_EVENTS_FORMAT} record")
        sid = d["session_id"]
        events, roles, replies = [], {}, []
        for i, e in enumerate(d["events"]):
            events.append(Event(event_id=e["event_id"], session_id=sid, index=i, kind=EventKind(e["kind"]), text=e["text"],
                                tool_name=e.get("tool_name"), source=SourceRef(path="session_events.json", line=i + 1)))
            if e.get("role") == "reply":
                replies.append(e["event_id"])
            elif e.get("role"):
                roles[e["role"]] = e["event_id"]
        metadata: dict[str, Any] = {"events": {**roles, "replies": replies}} if roles or replies else {}
        if d.get("commented_path"):
            metadata["commented_path"] = d["commented_path"]
        session = Session(session_id=sid, population=Population(d["population"]), source="session-events",
                          source_format=d["source_format"], trace_sha256=sha256_text(canonical_json(d)), events=events,
                          metadata=metadata)
        if verify:
            _check_record(d, session)
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ValueError(f"not a complete {SESSION_EVENTS_FORMAT} record ({type(exc).__name__}: {exc})") from None
    return session


def _check_record(d: dict[str, Any], session: Session) -> None:
    """Refuse (:class:`ValueError`) a session-events record ``d`` that is not exactly what :func:`render_session_events`
    gives for ``session``, the session that :func:`session_from_events` read from it. In order:

    * the population goes with the source format: a PR thread is ``natural:pr-review``, and a ``natural:pr-review``
      session is a PR thread (``ingest.github_pr.build_session`` makes every one), since check-proposals applies the
      natural rules by population and a render does not show it;
    * the session renders: for a PR thread, each role's event has a kind that the ingester gives the role, and the
      first-prompt render has a linked issue (``ingest.github_pr.pr_thread_events``);
    * its render is the record's ``render_sha256``;
    * the record is the one :func:`render_session_events` gives for it, key for key: no event, role, key or variant
      that the render does not show, and the events in the order shown.

    The messages name the record's keys and the session's event ids, never a text.
    """
    changed = "it was changed, or not made by render_session_events"
    pr_thread = session.source_format == PR_THREAD_FORMAT
    if pr_thread != (session.population == Population.natural_pr_review):
        raise ValueError(f"the record's population {session.population.value} does not go with its source format "
                         f"{session.source_format} (a PR thread, {PR_THREAD_FORMAT}, is {Population.natural_pr_review.value}, "
                         f"and a {Population.natural_pr_review.value} session is a PR thread): {changed}")
    variant = ContractVariant(d["variant"])
    try:
        render = render_session(session, first_prompt_only=variant == ContractVariant.initial_only)
        again = json.loads(render_session_events(session, variant))
    except ValueError as exc:
        raise ValueError(f"the record's session does not render ({exc}): {changed}") from None
    if sha256_text(render) != d.get("render_sha256"):
        raise ValueError(f"the record does not reproduce its render (render_sha256): {changed}")
    if again != d:
        keys = sorted(k for k in set(d) | set(again) if d.get(k) != again.get(k))
        raise ValueError("the record is not what render_session_events gives for the session it describes (it differs "
                         f"in: {', '.join(keys)}): {changed}")
