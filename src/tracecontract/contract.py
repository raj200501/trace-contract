"""Task-contract recovery, validation, and acceptance gating.

A *task contract* is the set of requirements a reconstructed task must enforce,
each linked to the session evidence that introduced it. Contracts are built from
*proposals* (rule-based heuristics, recorded model outputs, or human edits); this
module never treats a proposal as ground truth. It provides:

* :func:`align_quote` - turn a proposed quote into an exact, checkable span;
* :func:`requirements_from_proposals` - validate proposed requirements against
  the session and build :class:`Requirement` objects (rejecting unsupported ones);
* :func:`check_proposals` - the same with the natural PR-review rules, as ``tracecontract
  make-contract`` applies it and ``check-proposals`` repeats it without writing;
* :func:`derive_initial_only` - the information-loss baseline: keep only what the
  first user request supports;
* :func:`validate_contract` - structural / temporal / evidence checks;
* :func:`acceptance_gate` - what must hold before a contract can enter a benchmark
  (no unresolved conflicts, human review of uncertain requirements, observable
  checks for scored requirements, user evidence for explicit ones);
* :func:`task_gate` - the same for a whole task directory: its status, provenance
  eligibility and every contract (``tracecontract accept-task`` and ``evaluate``);
* :func:`render_instruction` - a task statement for agents, built only from
  active requirements (never from hidden tests or reference patches);
* :func:`propose_correction_events` - a transparent rule heuristic that flags user
  turns that look like corrections (proposal only).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .schemas import (
    ContractVariant,
    Eligibility,
    EventKind,
    EvidenceSpan,
    Population,
    ProvenanceRecord,
    Requirement,
    RequirementKind,
    RequirementStatus,
    Review,
    ReviewerKind,
    Session,
    TaskContract,
    TaskManifest,
)
from .store import load

# ---------------------------------------------------------------------------
# Evidence alignment
# ---------------------------------------------------------------------------


def _normalise_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace and normalise quotes; return mapping to original offsets."""
    out: list[str] = []
    mapping: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        c = unicodedata.normalize("NFKC", ch)
        c = {"‘": "'", "’": "'", "“": '"', "”": '"'}.get(c, c)
        if c.isspace():
            if prev_space:
                continue
            c = " "
            prev_space = True
        else:
            prev_space = False
        for cc in c:
            out.append(cc)
            mapping.append(i)
    return "".join(out), mapping


@dataclass
class Alignment:
    span: EvidenceSpan | None
    exact: bool
    occurrences: int
    reason: str = ""


def align_quote(session: Session, event_id: str, quote: str) -> Alignment:
    """Locate ``quote`` inside the text of ``event_id``.

    Exact substring matches are preferred; otherwise a whitespace/quote-normalised
    match is mapped back to original offsets. Returns ``span=None`` when the quote
    is not supported by the event text.
    """
    try:
        ev = session.event(event_id)
    except KeyError:
        return Alignment(None, False, 0, f"unknown event {event_id}")
    q = quote.strip()
    if not q:
        return Alignment(None, False, 0, "empty quote")
    text = ev.text
    n = text.count(q)
    if n:
        start = text.index(q)
        return Alignment(EvidenceSpan(event_id=event_id, start=start, end=start + len(q), quote=q), True, n)
    norm_text, mapping = _normalise_with_map(text)
    norm_q, _ = _normalise_with_map(q)
    norm_q = norm_q.strip()
    n = norm_text.count(norm_q) if norm_q else 0
    if not n:
        return Alignment(None, False, 0, "quote not found in event text")
    ns = norm_text.index(norm_q)
    start = mapping[ns]
    end = mapping[ns + len(norm_q) - 1] + 1
    return Alignment(
        EvidenceSpan(event_id=event_id, start=start, end=end, quote=text[start:end]), False, n, "normalised match"
    )


def span_is_valid(session: Session, span: EvidenceSpan) -> bool:
    try:
        ev = session.event(span.event_id)
    except KeyError:
        return False
    return ev.text[span.start : span.end] == span.quote


# ---------------------------------------------------------------------------
# Building requirements from proposals
# ---------------------------------------------------------------------------


@dataclass
class ProposalOutcome:
    requirements: list[Requirement]
    rejected: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Why a natural PR-review proposal is rejected when ``introduced_at`` names no user turn (``user_turns_only``). One
# reason for an unknown event and for an event that is not a user turn, so that check-proposals, which sees only the
# rendered events, rejects such a proposal as make-contract does on the whole session.
NOT_A_USER_TURN = ("introduced_at is not a user turn of this session (a natural PR-review requirement is introduced at "
                   "the linked issue, the review comment or one of the reviewer's replies)")


def requirements_from_proposals(session: Session, proposals: Iterable[dict[str, Any]], *, proposer: str,
                                user_turns_only: bool = False) -> ProposalOutcome:
    """Validate proposed requirements (e.g. recorded model output) against a session.

    Each proposal is a dict with keys ``req_id, statement, kind, status,
    introduced_at`` and optional ``evidence`` (list of ``{event_id, quote}``),
    ``rationale, supersedes, conflicts_with, observable, scored, subjective``.
    Proposals whose evidence cannot be aligned to user-prompt text are rejected
    (explicit) or downgraded to ``inferred`` only if they carry a rationale.

    ``user_turns_only`` (natural PR-review tasks, :func:`check_proposals`): a proposal whose
    ``introduced_at`` is not a user-prompt event (the issue, the review comment or a reply) is
    rejected (:data:`NOT_A_USER_TURN`); otherwise any event of the session is accepted there.
    """
    reqs: list[Requirement] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[str] = []
    ids = {e.event_id for e in session.events}
    user_turns = {e.event_id for e in session.events if e.kind == EventKind.user_prompt}
    seen: set[str] = set()
    for p in proposals:
        p = dict(p)
        if "req_id" not in p:
            for alias in ("id", "requirement_id"):
                if alias in p:
                    p["req_id"] = p.pop(alias)
                    break
        if not p.get("req_id"):
            rejected.append({"proposal": p, "reason": "missing req_id"})
            continue
        rid = str(p["req_id"])
        if rid in seen:
            rejected.append({"proposal": p, "reason": f"duplicate req_id {rid}"})
            continue
        seen.add(rid)
        if user_turns_only and p.get("introduced_at") not in user_turns:
            rejected.append({"proposal": p, "reason": NOT_A_USER_TURN})
            continue
        if p.get("introduced_at") not in ids:
            rejected.append({"proposal": p, "reason": "introduced_at is not an event of this session"})
            continue
        spans: list[EvidenceSpan] = []
        bad = []
        for ev in p.get("evidence", []) or []:
            al = align_quote(session, ev.get("event_id", ""), ev.get("quote", ""))
            if al.span is None:
                bad.append(f"{ev.get('event_id')}: {al.reason}")
                continue
            src = session.event(al.span.event_id)
            if src.kind != EventKind.user_prompt:
                warnings.append(f"{rid}: evidence from non-user event {src.event_id} ({src.kind.value})")
            if al.occurrences > 1:
                warnings.append(f"{rid}: quote occurs {al.occurrences}x in {src.event_id}; first occurrence used")
            spans.append(al.span)
        status = RequirementStatus(p.get("status", "explicit"))
        if bad:
            warnings.append(f"{rid}: unsupported evidence dropped: {bad}")
        if status == RequirementStatus.explicit and not spans:
            if p.get("rationale"):
                status = RequirementStatus.inferred
                warnings.append(f"{rid}: no valid evidence; downgraded explicit -> inferred")
            else:
                rejected.append({"proposal": p, "reason": "explicit requirement without supported evidence"})
                continue
        try:
            req = Requirement(
                req_id=rid,
                statement=str(p["statement"]).strip(),
                kind=RequirementKind(p.get("kind", "change")),
                status=status,
                introduced_at=p["introduced_at"],
                evidence=spans,
                rationale=str(p.get("rationale", "")),
                supersedes=list(p.get("supersedes", []) or []),
                superseded_by=p.get("superseded_by"),
                conflicts_with=list(p.get("conflicts_with", []) or []),
                observable=str(p.get("observable", "")),
                scored=bool(p.get("scored", True)) and not bool(p.get("subjective", False)),
                subjective=bool(p.get("subjective", False)),
                proposer=proposer,
            )
        except Exception as exc:  # pydantic validation error
            rejected.append({"proposal": p, "reason": f"invalid: {exc}"})
            continue
        reqs.append(req)
    reqs = link_supersession(reqs)
    return ProposalOutcome(reqs, rejected, warnings)


def correction_event_ids(session: Session) -> list[str]:
    """A natural PR-review session's correction events: the review comment and the reviewer's later replies
    (``session.metadata["events"]["correction"]`` and ``["replies"]``, as ``ingest.github_pr.build_session`` records
    them); empty for any other session."""
    raw = session.metadata.get("events")
    ids: dict[str, Any] = raw if isinstance(raw, dict) else {}
    found = [ids.get("correction"), *(ids.get("replies") or [])]
    known = {e.event_id for e in session.events}
    return [e for e in found if isinstance(e, str) and e in known]


def check_proposals(session: Session, proposals: Iterable[dict[str, Any]], *, proposer: str,
                    variant: ContractVariant | None, natural: bool) -> ProposalOutcome:
    """The proposal check of ``tracecontract make-contract``, which ``check-proposals`` repeats without writing.

    :func:`requirements_from_proposals`, and for a natural PR-review task (``natural``):

    * a proposal whose ``introduced_at`` is not a user turn (the issue, the review comment or a reply)
      is rejected (:data:`NOT_A_USER_TURN`);
    * for the ``reference`` variant, a warning when no scored active requirement is introduced at a
      correction event (:func:`correction_event_ids`), since the reference contract would then not
      observe the correction (protocol §15.6).
    """
    out = requirements_from_proposals(session, proposals, proposer=proposer, user_turns_only=natural)
    if natural and variant == ContractVariant.reference:
        corrections = correction_event_ids(session)
        if not any(r.active and r.scored and r.introduced_at in corrections for r in out.requirements):
            out.warnings.append("reference: no scored active requirement is introduced at a correction event (the review "
                                f"comment or a reply: {', '.join(corrections) or 'none in this session'}), so the "
                                "reference contract does not observe the correction")
    return out


def link_supersession(reqs: list[Requirement]) -> list[Requirement]:
    """Make ``supersedes`` / ``superseded_by`` consistent and mark superseded reqs."""
    by_id = {r.req_id: r for r in reqs}
    updates: dict[str, dict[str, Any]] = {}
    for r in reqs:
        for old in r.supersedes:
            if old in by_id:
                updates.setdefault(old, {})["superseded_by"] = r.req_id
                updates[old]["status"] = RequirementStatus.superseded
    out = []
    for r in reqs:
        if r.req_id in updates:
            r = r.model_copy(update=updates[r.req_id])
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------


def first_user_prompt(session: Session):
    prompts = session.user_prompts()
    if not prompts:
        raise ValueError(f"session {session.session_id} has no user prompts")
    return prompts[0]


def derive_initial_only(contract: TaskContract, session: Session, *, contract_id: str, created_at: str) -> TaskContract:
    """Initial-request-only contract: requirements introduced in the first user prompt.

    Supersession links pointing at later requirements are removed, because the
    later information is by definition unavailable to this baseline. This models
    information lost during dataset construction, not agent capability.
    """
    first = first_user_prompt(session).event_id
    keep = []
    for r in contract.requirements:
        if r.introduced_at != first:
            continue
        r = r.model_copy(
            update={
                "status": RequirementStatus.explicit if r.evidence else RequirementStatus.inferred,
                "superseded_by": None,
                "supersedes": [],
                "conflicts_with": [c for c in r.conflicts_with if c in {x.req_id for x in contract.requirements if x.introduced_at == first}],
            }
        )
        if r.status == RequirementStatus.inferred and not r.rationale:
            r = r.model_copy(update={"rationale": "carried over from first request"})
        keep.append(r)
    return TaskContract(
        contract_id=contract_id,
        task_id=contract.task_id,
        session_id=contract.session_id,
        variant=ContractVariant.initial_only,
        requirements=keep,
        created_by=f"derive_initial_only({contract.contract_id})",
        created_at=created_at,
        notes="Derived baseline: only requirements introduced by the first user prompt.",
    )


# ---------------------------------------------------------------------------
# Validation and acceptance gate
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    code: str
    message: str


def validate_contract(contract: TaskContract, session: Session) -> list[Issue]:
    issues: list[Issue] = []
    if contract.session_id != session.session_id:
        issues.append(Issue("error", "session_mismatch", "contract refers to another session"))
    order = {e.event_id: e.index for e in session.events}
    kinds = {e.event_id: e.kind for e in session.events}
    by_id = {r.req_id: r for r in contract.requirements}
    first = first_user_prompt(session).event_id if session.user_prompts() else None
    for r in contract.requirements:
        if r.introduced_at not in order:
            issues.append(Issue("error", "unknown_event", f"{r.req_id}: introduced_at {r.introduced_at} not in session"))
            continue
        for sp in r.evidence:
            if not span_is_valid(session, sp):
                issues.append(Issue("error", "bad_evidence", f"{r.req_id}: evidence span does not match event text"))
                continue
            if order[sp.event_id] > order[r.introduced_at]:
                issues.append(Issue("error", "evidence_after_introduction", f"{r.req_id}: evidence is later than introduced_at"))
            if r.status == RequirementStatus.explicit and kinds[sp.event_id] != EventKind.user_prompt:
                issues.append(Issue("warning", "non_user_evidence", f"{r.req_id}: explicit requirement quotes "
                                    f"{sp.event_id} ({kinds[sp.event_id].value}), not a user turn"))
        if r.superseded_by:
            new = by_id.get(r.superseded_by)
            if new is None:
                issues.append(Issue("error", "dangling_supersession", f"{r.req_id}: superseded_by {r.superseded_by} missing"))
            elif order.get(new.introduced_at, -1) < order[r.introduced_at]:
                issues.append(Issue("error", "supersession_order", f"{r.req_id} superseded by earlier requirement {new.req_id}"))
        for c in r.conflicts_with:
            if c not in by_id:
                issues.append(Issue("error", "dangling_conflict", f"{r.req_id}: conflicts_with {c} missing"))
        if contract.variant == ContractVariant.initial_only and first and r.introduced_at != first:
            issues.append(Issue("error", "initial_only_leak", f"{r.req_id}: initial-only contract uses later information"))
        if r.scored and r.active and not r.observable.strip():
            issues.append(Issue("warning", "no_observable", f"{r.req_id}: scored requirement lacks an observable check"))
    # Unresolved conflicts between two active requirements.
    for r in contract.active():
        for c in r.conflicts_with:
            other = by_id.get(c)
            if other is not None and other.active:
                issues.append(Issue("error", "active_conflict", f"{r.req_id} conflicts with active {c}"))
    return issues


# Issues that validate_contract reports as warnings, because a contract under construction may
# still have them, but that block acceptance: a scored requirement needs an observable check,
# and an explicit requirement must quote the user's own turns.
GATE_BLOCKING_WARNINGS = frozenset({"no_observable", "non_user_evidence"})


def _deciding_reviews(r: Requirement) -> list[Review]:
    """The human reviews that decide ``r``, in the order they were added.

    All of them, or, once there is an adjudicated review, the ones added after the latest
    adjudicated review (that review alone while there are none). A contract can change
    after review (an ``edit``), so later reviews decide again; this is where contract
    reviews differ from candidate labels, whose adjudicated label is final
    (``Candidate.final_label``).
    """
    human = [rv for rv in r.reviews if rv.reviewer_kind == ReviewerKind.human]
    adjudicated = [i for i, rv in enumerate(human) if rv.adjudicated]
    if adjudicated:
        return human[adjudicated[-1] + 1:] or [human[adjudicated[-1]]]
    return human


def human_decision(r: Requirement) -> str | None:
    """The human decision on ``r``, or ``None`` when there is no human review or the reviewers disagree.

    Only human reviews count; model and rule reviews are proposals. Each human reviewer's
    latest decision counts, and reviewers whose latest decisions differ leave ``r``
    without a decision until an adjudicated review settles it (:func:`_deciding_reviews`).
    """
    latest = {rv.reviewer: rv.decision for rv in _deciding_reviews(r)}  # each reviewer's latest decision
    return next(iter(latest.values())) if len(set(latest.values())) == 1 else None


def _review_problem(r: Requirement) -> tuple[str, str] | None:
    """``(code, detail)`` saying why the human reviews of ``r`` do not accept it; ``None`` when they do.

    ``edit`` and ``needs_discussion`` are not acceptance: the requirement counts as accepted
    only once it has been re-reviewed (a later review by the same reviewer, or an
    adjudicated one) and accepted.
    """
    latest = {rv.reviewer: rv.decision for rv in _deciding_reviews(r)}
    if not latest:
        return "needs_human_review", "no human review"
    if len(set(latest.values())) > 1:
        who = ", ".join(f"{k}: {v}" for k, v in sorted(latest.items()))
        return "review_disagreement", f"human reviewers disagree ({who}); needs an adjudicated review"
    decision = next(iter(latest.values()))
    if decision == "accept":
        return None
    if decision == "reject":
        return "rejected_in_review", "the human decision is 'reject'"
    return "needs_re_review", f"the human decision is {decision!r}; the requirement must be re-reviewed"


def acceptance_gate(contract: TaskContract, session: Session) -> tuple[bool, list[str]]:
    """Benchmark acceptance of one contract: structural validity + human review of uncertain items.

    * no validation error, and no ``no_observable`` (a scored requirement without an
      observable check) or ``non_user_evidence`` (an explicit requirement quoting an event
      that is not a user turn) issue;
    * no ``unresolved`` requirement remains (it must be resolved or dropped);
    * every scored ``inferred`` requirement, and in the reference contract every active
      scored requirement, is accepted by human review (:func:`human_decision`): reviewers
      who disagree need an adjudicated review, and ``edit`` or ``needs_discussion`` counts
      only once the requirement has been re-reviewed and accepted;
    * no other active scored requirement has human reviews that do not accept it.
    """
    reasons = [f"{i.code}: {i.message}" for i in validate_contract(contract, session)
               if i.severity == "error" or i.code in GATE_BLOCKING_WARNINGS]
    reference = contract.variant == ContractVariant.reference
    for r in contract.requirements:
        if r.status == RequirementStatus.unresolved:
            reasons.append(f"unresolved: {r.req_id} must be resolved or removed")
        if not (r.active and r.scored):
            continue
        inferred = r.status == RequirementStatus.inferred
        if not (inferred or reference or any(rv.reviewer_kind == ReviewerKind.human for rv in r.reviews)):
            continue
        problem = _review_problem(r)
        if problem is not None:
            what = "inferred" if inferred else "reference requirement" if reference else "requirement"
            reasons.append(f"{problem[0]}: {what} {r.req_id} ({problem[1]})")
    return (not reasons), reasons


@dataclass
class TaskGate:
    """The acceptance gate of one task directory (:func:`task_gate`)."""

    task_id: str
    status: str  # TaskManifest.status
    eligibility: str | None  # provenance eligibility; None when the record is missing
    refusals: list[str] = field(default_factory=list)  # rejected task or source: never evaluated or exported
    reasons: list[str] = field(default_factory=list)  # every reason the gate fails, refusals first

    @property
    def passed(self) -> bool:
        return not self.reasons

    @property
    def accepted(self) -> bool:
        """The gate passes and the task was accepted through it (``tracecontract accept-task``)."""
        return self.passed and self.status == "accepted"

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "status": self.status, "provenance_eligibility": self.eligibility,
                "passed": self.passed, "accepted": self.accepted, "refused": bool(self.refusals),
                "reasons": list(self.reasons)}


def task_gate(task_dir: Path, repo_root: Path) -> TaskGate:
    """The acceptance gate of a whole task: what must hold before it enters a benchmark.

    * neither its status nor its provenance eligibility is ``rejected``; a rejected task is
      refused outright (:attr:`TaskGate.refusals`), whatever the flags;
    * its provenance record exists and is ``eligible`` (a reviewer has checked the source's
      permission basis, licence and redaction; nothing here sets it);
    * it has a reference contract, and every contract it lists exists and passes
      :func:`acceptance_gate` against the task's session (read from ``repo_root``);
    * its base passed the reconstruction check: ``tasks/<id>/reconstruction_check.json`` has
      status ``passed`` and was recorded from the current transcript, base manifest and candidate
      patches (:func:`reconstruction.recorded_check`; protocol v0.8 §16.5). A current record whose
      check failed refuses the task: its base may already hold the solution;
    * a natural PR-review task (:func:`natural_gate_problems`) is refused unless its ``s10.json``
      records the S10 outcome ``passed``, and its row in the committed index
      (:data:`NATURAL_INDEX` in the HEAD commit) must say S11 (§16.4).

    ``tracecontract accept-task`` sets the status to ``accepted`` only when the gate passes,
    and ``tracecontract evaluate`` runs it again, so a task whose records changed after it
    was accepted no longer counts as accepted.
    """
    from .reconstruction import recorded_check  # reconstruction imports tasks, which imports this module
    from .tasks import session_for_task  # tasks imports this module

    m = load(task_dir / "task.json", TaskManifest)
    refusals: list[str] = []
    reasons: list[str] = []
    eligibility = None
    if m.status == "rejected":
        refusals.append("status: the task is rejected")
    if not (task_dir / m.provenance).is_file():
        reasons.append(f"provenance: no record at {m.provenance}")
    else:
        prov = load(task_dir / m.provenance, ProvenanceRecord)
        eligibility = prov.eligibility.value
        if prov.eligibility == Eligibility.rejected:
            refusals.append("provenance: the source is rejected (see its rejection_reasons)")
        elif prov.eligibility != Eligibility.eligible:
            reasons.append(f"provenance: eligibility is {eligibility!r}; a reviewer must find the source eligible")
    if "reference" not in m.contracts:
        reasons.append("contract: the task has no reference contract")
    try:
        session: Session | None = session_for_task(task_dir, repo_root)
    except FileNotFoundError:
        session = None
        reasons.append("session: transcript not found, so the contracts cannot be checked")
    for variant, rel in m.contracts.items():
        if not (task_dir / rel).is_file():
            reasons.append(f"contract {variant}: {rel} missing (sealed or not built)")
        elif session is not None:
            reasons += [f"contract {variant}: {w}" for w in acceptance_gate(load(task_dir / rel, TaskContract), session)[1]]
    rc = recorded_check(task_dir, repo_root)
    (refusals if rc.failed else reasons).extend(f"reconstruction: {p}" for p in rc.problems)
    if m.population == Population.natural_pr_review:
        nat_refusals, nat_reasons = natural_gate_problems(task_dir, repo_root, m.task_id)
        refusals += nat_refusals
        reasons += nat_reasons
    return TaskGate(task_id=m.task_id, status=m.status, eligibility=eligibility, refusals=refusals,
                    reasons=refusals + reasons)


# A natural PR-review task's S10 record, in its task directory (natural_pr.S10_RECORD), and the committed index of
# the natural PR-review tasks, relative to the repository root (natural_pr.INDEX).
S10_RECORD = "s10.json"
NATURAL_INDEX = "data/manifests/natural_tasks_index.json"


def committed_text(repo_root: Path, rel: str) -> str | None:
    """The text of the file ``rel`` (relative to ``repo_root``) as the HEAD commit of the repository at ``repo_root`` holds
    it (``git show HEAD:./<rel>``); ``None`` when git cannot say (no repository, no commit, or the file is not in it).

    No ``GIT_*`` variable of the caller (a hook's ``GIT_DIR``, for example) redirects the command."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        p = subprocess.run(["git", "-C", str(repo_root), "show", f"HEAD:./{rel}"], capture_output=True, env=env, timeout=60,
                           check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    try:
        return p.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _index_rows(text: str | None) -> dict[str, dict[str, Any]] | None:
    """The index's rows by task id; ``None`` for no text or a text that is not an index."""
    try:
        index = json.loads(text) if text is not None else None
    except ValueError:
        return None
    rows = index.get("tasks") if isinstance(index, dict) else None
    if not isinstance(rows, list):
        return None
    return {r["task_id"]: r for r in rows if isinstance(r, dict) and isinstance(r.get("task_id"), str)}


def natural_gate_problems(task_dir: Path, repo_root: Path, task_id: str) -> tuple[list[str], list[str]]:
    """``(refusals, reasons)`` that :func:`task_gate` adds for a natural PR-review task.

    * Refused unless ``s10.json`` records the S10 outcome ``passed``: a family that was only built,
      or that S10 rejected, is never evaluated (§15.6, §16.4).
    * A reason unless the task's row in the committed index is S11: it passes S10 and is within the
      family cap (§16.4). The committed index is ``data/manifests/natural_tasks_index.json`` as the
      repository's HEAD commit holds it (:func:`committed_text`), not the file in the working tree,
      which ``tracecontract natural-index`` rewrites before it is committed.
    * A reason too when the working tree's index gives the task another S11 value than the committed
      one: the index was changed and not committed, and the gate follows the committed one.
    """
    refusals: list[str] = []
    reasons: list[str] = []
    try:
        s10 = json.loads((task_dir / S10_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        refusals.append(f"s10: no readable {S10_RECORD}, so the family has not passed S10 (§15.6, §16.4)")
    else:
        outcome = s10.get("outcome") if isinstance(s10, dict) else None
        if outcome != "passed":
            refusals.append(f"s10: the S10 outcome recorded in {S10_RECORD} is {outcome!r}, not 'passed'; only a family "
                            "that passes S10 is built and evaluated (§16.4)")
    committed = _index_rows(committed_text(repo_root, NATURAL_INDEX))
    if committed is None:
        reasons.append(f"index: no readable committed index ({NATURAL_INDEX} in the HEAD commit), so S11 cannot be checked")
        return refusals, reasons
    row = committed.get(task_id)
    if row is None:
        reasons.append(f"index: {task_id} has no row in the committed index ({NATURAL_INDEX})")
    elif row.get("s11") is not True:
        reasons.append(f"index: {task_id} is not S11 in the committed index ({NATURAL_INDEX}); S11 means passing S10 "
                       "within the family cap (§16.4)")
    try:
        working = _index_rows((repo_root / NATURAL_INDEX).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        working = None
    if working is not None:
        now, then = (working.get(task_id) or {}).get("s11") is True, (row or {}).get("s11") is True
        if now != then:
            reasons.append(f"index: the working tree's {NATURAL_INDEX} gives {task_id} s11 {now}, the committed one {then}; "
                           "commit the index or restore it (the gate follows the committed one)")
    return refusals, reasons


# ---------------------------------------------------------------------------
# Instruction rendering
# ---------------------------------------------------------------------------


def render_instruction(contract: TaskContract, *, preamble: str = "") -> str:
    """Render an agent-facing instruction from the active requirements only."""
    lines = []
    if preamble:
        lines += [preamble.strip(), ""]
    changes = [r for r in contract.active() if r.kind == RequirementKind.change]
    keeps = [r for r in contract.active() if r.kind == RequirementKind.invariant]
    cons = [r for r in contract.active() if r.kind == RequirementKind.constraint]
    nons = [r for r in contract.active() if r.kind == RequirementKind.non_goal]
    if changes:
        lines.append("Make the following changes:")
        lines += [f"- {r.statement}" for r in changes]
    if keeps:
        lines += ["", "The following existing behaviour must be preserved:"]
        lines += [f"- {r.statement}" for r in keeps]
    if cons:
        lines += ["", "Constraints:"]
        lines += [f"- {r.statement}" for r in cons]
    if nons:
        lines += ["", "Out of scope:"]
        lines += [f"- {r.statement}" for r in nons]
    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Rule heuristic for correction detection (proposal only)
# ---------------------------------------------------------------------------

_CORRECTION_CUES = [
    r"\bactually\b",
    r"\binstead\b",
    r"\bdon'?t\b",
    r"\bdo not\b",
    r"^\s*no[,.!\s]",
    r"\bwait\b",
    r"\bkeep\b",
    r"\bstill (?:need|work|support)",
    r"\bmust(?:n'?t| not)?\b",
    r"\bshould(?:n'?t| not)\b",
    r"\brevert\b",
    r"\bundo\b",
    r"\brather than\b",
    r"\bbroke\b|\bbroken\b|\bbreaks\b",
    r"\bbackward[s]? compat",
    r"\bthat'?s not what\b",
    r"\bwrong\b",
]
_CUE_RE = re.compile("|".join(_CORRECTION_CUES), re.IGNORECASE | re.MULTILINE)


def propose_correction_events(session: Session) -> list[tuple[str, list[str]]]:
    """Flag later user prompts that contain correction cues.

    Returns ``(event_id, matched_cues)`` pairs. This is a transparent, high-recall
    heuristic used for triage; it is not a correctness judgment.
    """
    out = []
    for ev in session.user_prompts()[1:]:
        cues = sorted({m.group(0).strip().lower() for m in _CUE_RE.finditer(ev.text)})
        if cues:
            out.append((ev.event_id, cues))
    return out
