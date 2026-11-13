"""Task-contract recovery, validation, and acceptance gating.

A *task contract* is the set of requirements a reconstructed task must enforce,
each linked to the session evidence that introduced it. Contracts are built from
*proposals* (rule-based heuristics, recorded model outputs, or human edits); this
module never treats a proposal as ground truth. It provides:

* :func:`align_quote` - turn a proposed quote into an exact, checkable span;
* :func:`requirements_from_proposals` - validate proposed requirements against
  the session and build :class:`Requirement` objects (rejecting unsupported ones);
* :func:`derive_initial_only` - the information-loss baseline: keep only what the
  first user request supports;
* :func:`validate_contract` - structural / temporal / evidence checks;
* :func:`acceptance_gate` - what must hold before a contract can enter a benchmark
  (no unresolved conflicts, human review of uncertain requirements, observable
  checks for scored requirements);
* :func:`render_instruction` - a task statement for agents, built only from
  active requirements (never from hidden tests or reference patches);
* :func:`propose_correction_events` - a transparent rule heuristic that flags user
  turns that look like corrections (proposal only).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from .schemas import (
    ContractVariant,
    EventKind,
    EvidenceSpan,
    Requirement,
    RequirementKind,
    RequirementStatus,
    ReviewerKind,
    Session,
    TaskContract,
)

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


def requirements_from_proposals(session: Session, proposals: Iterable[dict[str, Any]], *, proposer: str) -> ProposalOutcome:
    """Validate proposed requirements (e.g. recorded model output) against a session.

    Each proposal is a dict with keys ``req_id, statement, kind, status,
    introduced_at`` and optional ``evidence`` (list of ``{event_id, quote}``),
    ``rationale, supersedes, conflicts_with, observable, scored, subjective``.
    Proposals whose evidence cannot be aligned to user-prompt text are rejected
    (explicit) or downgraded to ``inferred`` only if they carry a rationale.
    """
    reqs: list[Requirement] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[str] = []
    ids = {e.event_id for e in session.events}
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
    by_id = {r.req_id: r for r in contract.requirements}
    first = first_user_prompt(session).event_id if session.user_prompts() else None
    for r in contract.requirements:
        if r.introduced_at not in order:
            issues.append(Issue("error", "unknown_event", f"{r.req_id}: introduced_at {r.introduced_at} not in session"))
            continue
        for sp in r.evidence:
            if not span_is_valid(session, sp):
                issues.append(Issue("error", "bad_evidence", f"{r.req_id}: evidence span does not match event text"))
            elif order.get(sp.event_id, -1) > order[r.introduced_at]:
                issues.append(Issue("error", "evidence_after_introduction", f"{r.req_id}: evidence is later than introduced_at"))
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
        if r.scored and r.active and not r.observable:
            issues.append(Issue("warning", "no_observable", f"{r.req_id}: scored requirement lacks an observable check"))
    # Unresolved conflicts between two active requirements.
    for r in contract.active():
        for c in r.conflicts_with:
            other = by_id.get(c)
            if other is not None and other.active:
                issues.append(Issue("error", "active_conflict", f"{r.req_id} conflicts with active {c}"))
    return issues


def _human_accepted(r: Requirement) -> bool:
    human = [rv for rv in r.reviews if rv.reviewer_kind == ReviewerKind.human]
    return bool(human) and human[-1].decision in ("accept", "edit")


def acceptance_gate(contract: TaskContract, session: Session) -> tuple[bool, list[str]]:
    """Benchmark acceptance: structural validity + human review of uncertain items.

    * no validation errors;
    * no ``unresolved`` requirement remains (it must be resolved or dropped);
    * every ``inferred`` requirement that is scored has a human accept/edit review;
    * for the reference contract, every scored requirement has a human review.
    """
    reasons = [f"{i.code}: {i.message}" for i in validate_contract(contract, session) if i.severity == "error"]
    for r in contract.requirements:
        if r.status == RequirementStatus.unresolved:
            reasons.append(f"unresolved: {r.req_id} must be resolved or removed")
        if r.status == RequirementStatus.inferred and r.scored and not _human_accepted(r):
            reasons.append(f"needs_human_review: inferred {r.req_id}")
        if contract.variant == ContractVariant.reference and r.active and r.scored and not _human_accepted(r):
            reasons.append(f"needs_human_review: reference requirement {r.req_id}")
    return (not reasons), reasons


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
