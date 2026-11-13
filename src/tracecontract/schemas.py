"""Typed schemas for TraceContract.

Every artifact the pipeline produces (sessions, contracts, snapshots, candidates,
verifiers, verification results, provenance records) is a pydantic model here so
that it can be validated, hashed, and stored as JSON.

Design rules encoded in these schemas:

* Three data populations are kept separate (``Population``) and never mixed silently.
* Requirements carry evidence spans that point at stable event IDs and must match
  the event text exactly (checked in ``tracecontract.contract``).
* Labels record who produced them (human / model / rule / construction) so that
  model proposals are never mistaken for human ground truth.
* Verification outcomes are explicit; only ``Outcome.passed`` yields reward 1.0.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1.0"


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialisation used for content hashes."""
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# ---------------------------------------------------------------------------
# Sessions and events
# ---------------------------------------------------------------------------


class Population(str, Enum):
    """Where a session came from. These are reported separately, always."""

    natural = "natural"  # naturally occurring sessions with real users (e.g. SWE-chat)
    controlled = "controlled"  # real agent runs with scripted user turns, made for this study
    fixture = "fixture"  # hand-written synthetic unit-test fixtures


class EventKind(str, Enum):
    user_prompt = "user_prompt"  # text typed by the user (or scripted user, for controlled)
    system_injected = "system_injected"  # harness text delivered in the user role
    user_interrupt = "user_interrupt"
    assistant_text = "assistant_text"
    assistant_thinking = "assistant_thinking"
    tool_call = "tool_call"
    tool_result = "tool_result"
    metadata = "metadata"


class Author(str, Enum):
    human = "human"
    scripted_user = "scripted_user"  # controlled sessions: user turns written by the study
    agent = "agent"
    tool = "tool"
    harness = "harness"
    unknown = "unknown"


class SourceRef(_Model):
    """Pointer back into the raw source file an event was parsed from."""

    path: str
    line: int  # 1-based line number in a JSONL file (or record index)
    block: int = 0  # content-block index within that line
    native_id: str | None = None  # e.g. Claude Code entry uuid


class Event(_Model):
    event_id: str  # stable: "<session_id>/L<line>.<block>"
    session_id: str
    index: int  # 0-based order within the session
    kind: EventKind
    author: Author = Author.unknown
    timestamp: str | None = None
    text: str = ""
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_input: dict[str, Any] | None = None
    is_error: bool | None = None
    is_sidechain: bool = False
    source: SourceRef


class Session(_Model):
    schema_version: str = SCHEMA_VERSION
    session_id: str
    population: Population
    source: str  # e.g. "swe-chat", "controlled:tracecontract", "fixture"
    source_revision: str | None = None
    source_format: str  # e.g. "claude_code_jsonl"
    agent: str | None = None
    repo_url: str | None = None
    trace_sha256: str  # sha256 of the raw transcript bytes
    events: list[Event]
    metadata: dict[str, Any] = Field(default_factory=dict)

    def event(self, event_id: str) -> Event:
        for ev in self.events:
            if ev.event_id == event_id:
                return ev
        raise KeyError(event_id)

    def user_prompts(self) -> list[Event]:
        return [e for e in self.events if e.kind == EventKind.user_prompt]

    @model_validator(mode="after")
    def _check_ids(self) -> "Session":
        ids = [e.event_id for e in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate event_id in session")
        if [e.index for e in self.events] != list(range(len(self.events))):
            raise ValueError("event indices must be 0..n-1 in order")
        for e in self.events:
            if e.session_id != self.session_id:
                raise ValueError(f"event {e.event_id} belongs to another session")
        return self


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------


class TriageCategory(str, Enum):
    candidate = "candidate"  # plausibly convertible into a task
    apparent_model_failure = "apparent_model_failure"
    environment_failure = "environment_failure"
    incomplete_evidence = "incomplete_evidence"
    ambiguous_objective = "ambiguous_objective"
    unsuitable_task = "unsuitable_task"


class TriageProposal(_Model):
    """A rule- or model-produced triage proposal. Not ground truth."""

    category: TriageCategory
    method: str  # e.g. "rule:v1"
    confidence: Literal["low", "medium", "high"]
    reasons: list[str] = Field(default_factory=list)
    correction_event_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Requirements and contracts
# ---------------------------------------------------------------------------


class EvidenceSpan(_Model):
    event_id: str
    start: int
    end: int
    quote: str  # must equal event.text[start:end]

    @model_validator(mode="after")
    def _check_span(self) -> "EvidenceSpan":
        if self.start < 0 or self.end <= self.start:
            raise ValueError("evidence span must have 0 <= start < end")
        if len(self.quote) != self.end - self.start:
            raise ValueError("quote length does not match span")
        return self


class RequirementKind(str, Enum):
    change = "change"  # behaviour the user wants added or modified
    invariant = "invariant"  # behaviour that must be preserved (compatibility, data, inputs)
    constraint = "constraint"  # dependency / interface / environment constraint
    non_goal = "non_goal"  # explicitly out of scope


class RequirementStatus(str, Enum):
    explicit = "explicit"  # directly stated in the session
    inferred = "inferred"  # implied by the session; needs human review before acceptance
    superseded = "superseded"  # replaced by a later requirement
    unresolved = "unresolved"  # ambiguous or contradictory with no resolution in the session


class ReviewerKind(str, Enum):
    human = "human"
    model = "model"
    rule = "rule"


class Review(_Model):
    reviewer: str  # pseudonymous id, e.g. "R1", or a method id
    reviewer_kind: ReviewerKind
    decision: Literal["accept", "reject", "edit", "needs_discussion"]
    timestamp: str
    note: str = ""


class Requirement(_Model):
    req_id: str
    statement: str
    kind: RequirementKind
    status: RequirementStatus
    introduced_at: str  # event_id of the user turn that introduced it
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    rationale: str = ""  # required for inferred requirements
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    conflicts_with: list[str] = Field(default_factory=list)
    observable: str = ""  # how a verifier can observe it
    scored: bool = True
    subjective: bool = False  # exploratory criterion; never scored
    proposer: str  # "rule:v1", "model:<id>", "human:R1"
    reviews: list[Review] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Requirement":
        if self.status == RequirementStatus.explicit and not self.evidence:
            raise ValueError(f"{self.req_id}: explicit requirement needs evidence")
        if self.status == RequirementStatus.inferred and not self.rationale:
            raise ValueError(f"{self.req_id}: inferred requirement needs a rationale")
        if self.status == RequirementStatus.superseded and not self.superseded_by:
            raise ValueError(f"{self.req_id}: superseded requirement needs superseded_by")
        if self.subjective and self.scored:
            raise ValueError(f"{self.req_id}: subjective requirements cannot be scored")
        return self

    @property
    def active(self) -> bool:
        return self.status in (RequirementStatus.explicit, RequirementStatus.inferred)


class ContractVariant(str, Enum):
    initial_only = "initial_only"  # requirements from the first user request only
    full_session = "full_session"  # correction-aware, structured, evidence-linked
    reference = "reference"  # human-reviewed contract used for labels


class TaskContract(_Model):
    schema_version: str = SCHEMA_VERSION
    contract_id: str
    task_id: str
    session_id: str
    variant: ContractVariant
    requirements: list[Requirement]
    instruction: str = ""  # natural-language task statement rendered from active requirements
    created_by: str
    created_at: str
    notes: str = ""

    def active(self) -> list[Requirement]:
        return [r for r in self.requirements if r.active]

    def by_id(self, req_id: str) -> Requirement:
        for r in self.requirements:
            if r.req_id == req_id:
                return r
        raise KeyError(req_id)

    @model_validator(mode="after")
    def _unique(self) -> "TaskContract":
        ids = [r.req_id for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate req_id")
        return self


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class Fidelity(str, Enum):
    exact = "exact"
    approximate = "approximate"
    unreconstructable = "unreconstructable"


class LeakageCheck(_Model):
    checked_paths: list[str]
    leaked_paths: list[str]
    passed: bool
    method: str = "post-image-equality"


class Snapshot(_Model):
    schema_version: str = SCHEMA_VERSION
    snapshot_id: str
    task_id: str
    repo_url: str
    base_commit: str
    fidelity: Fidelity
    approximations: list[str] = Field(default_factory=list)
    file_manifest_sha256: str
    n_files: int
    environment: dict[str, Any] = Field(default_factory=dict)  # image, python, deps lock
    leakage_check: LeakageCheck | None = None


# ---------------------------------------------------------------------------
# Candidates and labels
# ---------------------------------------------------------------------------


class CandidateOrigin(str, Enum):
    reference = "reference"  # accepted final solution of the source session
    observed_pre_correction = "observed_pre_correction"  # agent state the user corrected
    observed_other = "observed_other"
    constructed_near_miss = "constructed_near_miss"
    valid_alternative = "valid_alternative"
    noop = "noop"
    incomplete = "incomplete"
    dev_attack = "dev_attack"  # audit-time attacks; development split only
    tamper_probe = "tamper_probe"  # grading-isolation probes


class Split(str, Enum):
    dev = "dev"
    eval = "eval"


class LabelerKind(str, Enum):
    human = "human"
    model = "model"
    rule = "rule"
    construction = "construction"  # label implied by how the candidate was built (a proposal)


class Label(_Model):
    value: Literal["valid", "invalid", "ambiguous"]
    violated_requirements: list[str] = Field(default_factory=list)
    labeler: str
    labeler_kind: LabelerKind
    adjudicated: bool = False
    timestamp: str
    note: str = ""


class Candidate(_Model):
    schema_version: str = SCHEMA_VERSION
    candidate_id: str
    task_id: str
    origin: CandidateOrigin
    split: Split
    patch: str  # unified diff against the base snapshot ("" for no-op)
    patch_sha256: str
    produced_by: str
    description: str = ""
    labels: list[Label] = Field(default_factory=list)

    @model_validator(mode="after")
    def _hash(self) -> "Candidate":
        if sha256_text(self.patch) != self.patch_sha256:
            raise ValueError(f"{self.candidate_id}: patch_sha256 mismatch")
        if self.origin == CandidateOrigin.dev_attack and self.split != Split.dev:
            raise ValueError("dev_attack candidates must be in the dev split")
        return self

    def final_label(self) -> Label | None:
        """Adjudicated human label if present, else the latest human label, else None.

        Model / rule / construction labels are proposals and never returned here.
        """
        human = [lb for lb in self.labels if lb.labeler_kind == LabelerKind.human]
        adjudicated = [lb for lb in human if lb.adjudicated]
        if adjudicated:
            return adjudicated[-1]
        return human[-1] if human else None

    def proposed_label(self) -> Label | None:
        return self.labels[-1] if self.labels else None


# ---------------------------------------------------------------------------
# Verifiers and outcomes
# ---------------------------------------------------------------------------


class VerifierCondition(str, Enum):
    initial_plain = "initial_plain"  # C1: initial-request contract, generated tests
    initial_audited = "initial_audited"  # C2: initial-request contract, audited tests
    full_plain = "full_plain"  # C3: correction-aware contract, generated tests
    full_audited = "full_audited"  # C4: correction-aware contract, audited tests
    repo_tests = "repo_tests"  # B1: the repository's own test suite
    llm_freeform = "llm_freeform"  # B2: full-session LLM reconstruction without contract machinery
    reference_check = "reference_check"  # independent human-reviewed checks (label support only)


class Isolation(str, Enum):
    process_separated = "process_separated"  # candidate code never runs in the grader process
    in_process = "in_process"  # candidate code imported by the test runner (tamperable)


class GenerationRecord(_Model):
    generator: str  # e.g. "model:claude-...-via-claude-code-subagent" or "human:R1"
    run_id: str
    prompt_sha256: str
    created_at: str
    budget: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class CheckSpec(_Model):
    check_id: str  # pytest node id relative to the verifier test dir
    requirement_ids: list[str] = Field(default_factory=list)


class AuditRecord(_Model):
    procedure: str  # e.g. "audit:v1"
    iterations: int
    passed: bool
    findings: list[str] = Field(default_factory=list)
    dev_candidate_ids: list[str] = Field(default_factory=list)


class VerifierSpec(_Model):
    schema_version: str = SCHEMA_VERSION
    verifier_id: str
    task_id: str
    condition: VerifierCondition
    contract_id: str | None = None
    isolation: Isolation
    test_dir: str  # directory (relative to the task dir) holding the test files
    checks: list[CheckSpec]
    content_sha256: str  # hash of the test files (see verifier.hash_test_dir)
    generation: GenerationRecord | None = None
    audit: AuditRecord | None = None
    frozen: bool = False
    version: int = 1


class Outcome(str, Enum):
    passed = "pass"
    task_failure = "task_failure"
    environment_failure = "environment_failure"
    verifier_error = "verifier_error"
    timeout = "timeout"
    unresolved = "unresolved"


class CheckResult(_Model):
    check_id: str
    status: Literal["passed", "failed", "error", "skipped", "missing"]
    duration_s: float | None = None
    message: str = ""


class VerificationResult(_Model):
    schema_version: str = SCHEMA_VERSION
    run_id: str
    task_id: str
    verifier_id: str
    candidate_id: str
    outcome: Outcome
    reward: float
    checks: list[CheckResult] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    started_at: str
    finished_at: str
    wall_s: float
    harness_version: str
    log_sha256: str | None = None

    @model_validator(mode="after")
    def _reward(self) -> "VerificationResult":
        expected = 1.0 if self.outcome == Outcome.passed else 0.0
        if self.reward != expected:
            raise ValueError("reward must be 1.0 iff outcome == pass")
        return self


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class Eligibility(str, Enum):
    eligible = "eligible"
    rejected = "rejected"
    pending_review = "pending_review"


class RedactionStatus(str, Enum):
    source_redacted = "source_redacted"  # redacted upstream (e.g. SWE-chat Presidio/TruffleHog)
    redacted_by_us = "redacted_by_us"
    not_needed_controlled = "not_needed_controlled"  # no third-party personal data by construction
    pending = "pending"


class ProvenanceRecord(_Model):
    schema_version: str = SCHEMA_VERSION
    record_id: str
    session_id: str
    population: Population
    source_url: str
    source_id: str
    source_revision: str | None = None
    repo_url: str | None = None
    base_commit: str | None = None
    licenses: dict[str, str] = Field(default_factory=dict)  # e.g. {"code": "MIT", "dataset": "ODC-BY-1.0"}
    permission_basis: str
    trace_sha256: str | None = None
    snapshot_manifest_sha256: str | None = None
    capture_method: str
    redaction_status: RedactionStatus
    task_family_id: str
    eligibility: Eligibility
    rejection_reasons: list[str] = Field(default_factory=list)
    triage: TriageProposal | None = None
    accessed: str
    notes: str = ""


# ---------------------------------------------------------------------------
# Task manifest
# ---------------------------------------------------------------------------


class SnapshotSource(_Model):
    """How to rebuild the initial state: a pinned git revision of a public repo."""

    repo_url: str
    commit: str
    subdir: str = ""  # optional sub-directory of the repo that forms the workspace


class TaskManifest(_Model):
    schema_version: str = SCHEMA_VERSION
    task_id: str
    family_id: str  # independent unit of analysis (source session / task family)
    population: Population
    status: Literal["draft", "pending_review", "accepted", "rejected"]
    provenance: str  # path (relative to task dir) of the ProvenanceRecord JSON
    snapshot_source: SnapshotSource
    snapshot: str | None = None  # path of the Snapshot JSON once built
    env_requirements: list[str]  # fully pinned, transitively closed requirement list
    candidate_pythonpath: str = "/work"
    repo_test_args: list[str] = Field(default_factory=list)
    contracts: dict[str, str] = Field(default_factory=dict)  # variant -> path
    verifiers: list[str] = Field(default_factory=list)  # paths of VerifierSpec JSON files
    candidates: list[str] = Field(default_factory=list)  # paths of Candidate JSON files
    notes: str = ""
