"""Typed schemas for TraceContract.

Every artifact the pipeline produces (sessions, contracts, snapshots, candidates,
verifiers, verification results, provenance records) is a pydantic model here so
that it can be validated, hashed, and stored as JSON.

Design rules encoded in these schemas:

* The data populations (``Population``: controlled, natural and its two sub-populations, fixture)
  are kept separate and never mixed silently.
* Requirements carry evidence spans that point at stable event IDs and must match
  the event text exactly (checked in ``tracecontract.contract``).
* Labels record who produced them (human / model / rule / construction / source evidence)
  so that model proposals are never mistaken for human ground truth.
* Verification outcomes are explicit; only ``Outcome.passed`` yields reward 1.0.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer, model_validator

SCHEMA_VERSION = "0.1.0"
# The configuration label of an agent run (a generation record's generator, an attempt record's
# configuration): config-A to config-Z, one capital letter (protocol v0.7 §15.4, §15.5).
CONFIG_LABEL = re.compile(r"config-[A-Z]")
_SHA256 = re.compile(r"[0-9a-f]{64}")


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
    """Where a session came from. These are reported separately, always.

    The two ungated natural sources are sub-populations of their own (protocol v0.8 §16.3), so
    a run that mixes them is refused or reported per population like any other mix
    (``analysis.MixedPopulations``, ``by_population``).
    """

    natural = "natural"  # naturally occurring sessions with real users (e.g. SWE-chat)
    controlled = "controlled"  # real agent runs with scripted user turns, made for this study
    fixture = "fixture"  # hand-written synthetic unit-test fixtures
    natural_pr_review = "natural:pr-review"  # agent pull requests; a reviewer's comment takes the place of the correction (AIDev)
    natural_chat = "natural:chat"  # agent sessions with real users from an ungated source (Trace Commons)

    @property
    def is_natural(self) -> bool:
        """True for ``natural`` and its sub-populations (``natural:<source>``)."""
        return self.value.split(":", 1)[0] == "natural"


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
    # A human review that settles a disagreement between reviewers (contract.human_decision).
    # Omitted from the JSON while false, so records written before the field existed
    # re-serialize byte for byte.
    adjudicated: bool = False

    @model_serializer(mode="wrap")
    def _omit_unadjudicated(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if not self.adjudicated:
            data.pop("adjudicated", None)
        return data


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
    reference = "reference"  # reference contract used for labels (human review required before acceptance)


class GenerationRecord(_Model):
    """The record of the agent run that wrote a generated artifact: a verifier's tests (``VerifierSpec.generation``),
    a contract's proposals (``TaskContract.generation``) or a constructed candidate (``Candidate.generation``).

    ``verifier.generation_record`` builds a complete one and ``verifier.generation_record_problems`` says what an
    incomplete one lacks (protocol v0.7 §15.4, §15.6: every generated artifact carries one)."""

    generator: str  # a configuration label (config-A, verifier.generation_record) for a new run; pilot records: "model:..."
    run_id: str
    prompt_sha256: str
    created_at: str
    budget: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


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
    # The record of the agent run that proposed the requirements (``make-contract --generation-record``; required for a
    # natural PR-review task, §15.6). Omitted from the JSON while None, so records written before the field existed
    # re-serialise byte for byte.
    generation: GenerationRecord | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_generation(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.generation is None:
            data.pop("generation", None)
        return data

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
    fresh_attempt = "fresh_attempt"  # final state of a fresh agent's attempt at the task (stratum fresh-v1; protocol §15.4)
    natural_pre_review = "natural_pre_review"  # natural PR-review task: the tree the reviewer commented on (§15.6)


# Candidates that D19 labels by its natural-candidate rule (reference checks and regression norm,
# sources 1 and 2), never by construction intent (protocol v0.7 §15.4, v0.8 §16.3).
NATURAL_ORIGINS = frozenset({CandidateOrigin.observed_pre_correction, CandidateOrigin.observed_other,
                             CandidateOrigin.fresh_attempt, CandidateOrigin.natural_pre_review})
# Candidates an agent constructs for the pool or the audit (dev attacks, valid alternatives, near misses): the ones whose
# generation record ``add-candidate --generation-record`` keeps (protocol §15.6: every generated artifact carries one).
CONSTRUCTED_ORIGINS = frozenset({CandidateOrigin.dev_attack, CandidateOrigin.valid_alternative,
                                 CandidateOrigin.constructed_near_miss})


class Split(str, Enum):
    dev = "dev"
    eval = "eval"


class LabelerKind(str, Enum):
    human = "human"
    model = "model"
    rule = "rule"
    construction = "construction"  # label implied by how the candidate was built (a proposal)
    # Natural PR-review task: the source's own evidence (the reviewer's request, the addressing commit and
    # the S9 agreement) labels the pre-review state; reported apart from D19, never a human label (§15.6).
    source_evidence = "source_evidence"


class Label(_Model):
    value: Literal["valid", "invalid", "ambiguous"]
    violated_requirements: list[str] = Field(default_factory=list)
    labeler: str
    labeler_kind: LabelerKind
    adjudicated: bool = False
    timestamp: str
    note: str = ""


class AttemptEnd(str, Enum):
    finished = "finished"
    gave_up = "gave_up"
    error = "error"


class AttemptAudit(_Model):
    """The fresh-attempt audit of one attempt's transcript, over tool inputs and tool outputs (protocol v0.8 §16.2)."""

    profile: str  # the audit profile, e.g. "fresh-attempt:v1"
    passed: bool  # False: the attempt read forbidden material, so it is excluded from every analysis
    findings: list[str] = Field(default_factory=list)
    audited_at: str
    record: str = ""  # pointer to the full audit record


class AttemptRecord(_Model):
    """One fresh-agent attempt (protocol v0.7 §15.4), kept with the candidate that its final state became.

    ``configuration`` is a configuration label, ``config-A`` to ``config-Z`` (``CONFIG_LABEL``); the
    private run record that ``run_record`` points to says which model the configuration was. Times,
    turns, tool calls, tokens and wall time are recorded where available. ``audit`` is the verdict of
    the fresh-attempt audit; the analysis excludes an attempt that has none or whose audit failed
    (``analysis.attempt_exclusion``).
    """

    attempt_id: str
    configuration: str
    variant: Literal["u1", "final"]  # the instruction variant: U1 alone, or U1 with U2 added
    instruction_sha256: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    wall_s: float | None = None
    turns: int | None = None
    tool_calls: int | None = None
    tokens: int | None = None
    ended: AttemptEnd  # how the attempt ended: finished, gave up or error
    patch_sha256: str  # sha256 of the candidate patch its final state became
    run_record: str = ""  # pointer to the private run record, kept outside the repository
    audit: AttemptAudit | None = None

    @model_validator(mode="after")
    def _check(self) -> "AttemptRecord":
        if not self.attempt_id.strip() or any(ch.isspace() for ch in self.attempt_id):
            raise ValueError("attempt record: the attempt id is empty or holds whitespace")
        if not CONFIG_LABEL.fullmatch(self.configuration):
            raise ValueError(f"attempt record {self.attempt_id}: the configuration label must be config-A to config-Z "
                             f"(got {self.configuration!r})")
        for name in ("patch_sha256", "instruction_sha256"):
            value = getattr(self, name)
            if value is not None and not _SHA256.fullmatch(value):
                raise ValueError(f"attempt record {self.attempt_id}: {name} is not 64 lowercase hex digits")
        for name in ("turns", "tool_calls", "tokens"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"attempt record {self.attempt_id}: {name} is negative")
        if self.wall_s is not None and self.wall_s <= 0:
            raise ValueError(f"attempt record {self.attempt_id}: the wall time is not positive")
        times = {}
        for name in ("started_at", "ended_at"):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                times[name] = datetime.fromisoformat(value)
            except ValueError:
                times[name] = None
            if times[name] is None or times[name].tzinfo is None:
                raise ValueError(f"attempt record {self.attempt_id}: {name} is not an ISO 8601 time with a time zone")
        if len(times) == 2 and times["ended_at"] < times["started_at"]:
            raise ValueError(f"attempt record {self.attempt_id}: it ends before it starts")
        return self


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
    # The attempt record of a fresh attempt (origin fresh_attempt only; protocol §15.4). Omitted from the
    # JSON while None, so records written before the field existed re-serialise byte for byte.
    attempt: AttemptRecord | None = None
    # The record of the agent run that constructed the candidate (``add-candidate --generation-record``; origins in
    # CONSTRUCTED_ORIGINS only, as an attempt record is a fresh attempt's only; required for them on a natural PR-review
    # task, §15.6). Omitted from the JSON while None.
    generation: GenerationRecord | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_records(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.attempt is None:
            data.pop("attempt", None)
        if self.generation is None:
            data.pop("generation", None)
        return data

    @model_validator(mode="after")
    def _hash(self) -> "Candidate":
        if sha256_text(self.patch) != self.patch_sha256:
            raise ValueError(f"{self.candidate_id}: patch_sha256 mismatch")
        if self.origin == CandidateOrigin.dev_attack and self.split != Split.dev:
            raise ValueError("dev_attack candidates must be in the dev split")
        if self.attempt is not None:
            if self.origin != CandidateOrigin.fresh_attempt:
                raise ValueError(f"{self.candidate_id}: only a fresh_attempt candidate carries an attempt record")
            if self.attempt.patch_sha256 != self.patch_sha256:
                raise ValueError(f"{self.candidate_id}: its attempt record holds another patch sha256 than the candidate")
        if self.generation is not None and self.origin not in CONSTRUCTED_ORIGINS:
            raise ValueError(f"{self.candidate_id}: only a constructed candidate "
                             f"({', '.join(sorted(o.value for o in CONSTRUCTED_ORIGINS))}) carries a generation record, "
                             f"not one of origin {self.origin.value}")
        return self

    def final_label(self) -> Label | None:
        """Adjudicated human label if present, else the latest human label, else None.

        Model / rule / construction labels are proposals and never returned here. When
        no label is adjudicated and the latest labels of different human reviewers
        disagree, on the value or on the violated requirements, the candidate has no final
        label until an adjudicated one is added (decision log D44, D46).
        """
        human = [lb for lb in self.labels if lb.labeler_kind == LabelerKind.human]
        adjudicated = [lb for lb in human if lb.adjudicated]
        if adjudicated:
            return adjudicated[-1]
        if self.human_disagreement():
            return None
        return human[-1] if human else None

    def human_disagreement(self) -> bool:
        """True when reviewers' latest human labels differ (value or violated requirements) and none is adjudicated."""
        human = [lb for lb in self.labels if lb.labeler_kind == LabelerKind.human]
        latest = {x.labeler: x for x in human}.values()  # each reviewer's latest label
        return not any(lb.adjudicated for lb in human) and len(
            {(lb.value, tuple(sorted(lb.violated_requirements))) for lb in latest}) > 1

    def proposed_label(self) -> Label | None:
        """The latest model, rule or construction proposal (never a human or a source-evidence label)."""
        proposals = [lb for lb in self.labels if lb.labeler_kind not in (LabelerKind.human, LabelerKind.source_evidence)]
        return proposals[-1] if proposals else None

    def source_evidence_label(self) -> Label | None:
        """The latest source-evidence label (natural PR-review tasks), which is reported apart from D19 (§15.6)."""
        found = [lb for lb in self.labels if lb.labeler_kind == LabelerKind.source_evidence]
        return found[-1] if found else None


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
    reference_check = "reference_check"  # independent model-written checks (label support only; not human-reviewed)
    diff_derived = "diff_derived"  # B3: tests from the initial request and the reference diff, no contract (§15.6)


class Isolation(str, Enum):
    process_separated = "process_separated"  # candidate code never runs in the grader process
    in_process = "in_process"  # candidate code imported by the test runner (tamperable)


class CheckSpec(_Model):
    check_id: str  # pytest node id relative to the verifier test dir
    requirement_ids: list[str] = Field(default_factory=list)


class AuditCheck(_Model):
    """A check of an audited verifier as one audit iteration graded it (``AuditIteration.checks``)."""

    check_id: str
    requirement_ids: list[str] = Field(default_factory=list)
    # sha256 of the check function's source in its test file, from its first decorator to its last line; None when
    # the check id names no function in the verifier's test files
    sha256: str | None = None
    # sha256 of the code the function depends on beyond its own source (``audit.suite_snapshot``): the module-level code
    # of its file that it uses by name, directly or through other module-level code (helpers, constants, imports, the
    # other members of its class, a module-level statement that changes a name it uses, a fixture it names, also through
    # usefixtures or a fixture's name=), the file's autouse fixtures, pytestmark and module-level setup functions, and
    # every conftest.py above its file; None when it depends on none. Data files and other modules are not followed.
    uses_sha256: str | None = None


class AuditRepeat(_Model):
    """One run of a development candidate that an audit iteration graded more than once (the reference)."""

    outcome: str
    failed_checks: list[str] = Field(default_factory=list)


class AuditRun(_Model):
    """One development candidate as one audit iteration graded it, with every check that did not pass."""

    candidate_id: str
    origin: str
    outcome: str  # graded more than once: one outcome when the runs agree, else unresolved (the grader's rule)
    failed_checks: list[str] = Field(default_factory=list)  # graded more than once: those of the last run
    repeats: list[AuditRepeat] = Field(default_factory=list)  # graded more than once: each run, in order


class AuditFindingEntry(_Model):
    """One finding of an audit iteration, as ``tracecontract audit`` prints it (``audit.AuditFinding``)."""

    code: str
    message: str
    candidate_id: str | None = None
    requirement_id: str | None = None


class AuditIteration(_Model):
    """One iteration of an audit: iteration 0 grades the tests it starts from, iteration i the tests after revision i."""

    iteration: int
    passed: bool
    graded_at: str | None = None  # when the iteration was graded (ISO time, UTC)
    content_sha256: str  # the test files graded (verifier.hash_test_dir)
    checks_sha256: str  # the scored check list graded: ids and requirement ids (verifier.checks_sha256)
    files: dict[str, str] = Field(default_factory=dict)  # every file of the tests: path in the test dir -> sha256
    checks: list[AuditCheck] = Field(default_factory=list)
    findings: list[AuditFindingEntry] = Field(default_factory=list)
    runs: list[AuditRun] = Field(default_factory=list)  # every failing check of every candidate graded, in each run


class AuditRequirementChange(_Model):
    """A check whose requirement ids differ between two iterations; None: the check is not one of that iteration's."""

    check_id: str
    before: list[str] | None = None
    after: list[str] | None = None


class AuditCodeChange(_Model):
    """A file of the tests, or a module-level definition in one (``<file>::<name>``), that a revision changed."""

    name: str
    change: Literal["added", "removed", "changed"]


class AuditRevision(_Model):
    """What revision i changed, against the tests of iteration i - 1. All lists empty: the revision changed nothing."""

    revision: int
    added: list[str] = Field(default_factory=list)  # check ids
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)  # checks whose function source changed (AuditCheck.sha256)
    # checks whose function source is unchanged but whose module-level code changed (AuditCheck.uses_sha256)
    changed_indirectly: list[str] = Field(default_factory=list)
    requirement_map: list[AuditRequirementChange] = Field(default_factory=list)  # added and removed checks included
    module_code: list[AuditCodeChange] = Field(default_factory=list)  # definitions other than the checks
    files: list[AuditCodeChange] = Field(default_factory=list)


class AuditRecord(_Model):
    procedure: str  # e.g. "audit:v1"
    iterations: int
    passed: bool
    findings: list[str] = Field(default_factory=list)
    dev_candidate_ids: list[str] = Field(default_factory=list)
    # Every iteration of the audit, 0 to ``iterations``, with every failing check, and what each revision changed
    # (``tracecontract audit --record N --previous ...``; decision log D62). Omitted from the JSON while empty, so
    # records written before the fields existed re-serialise byte for byte.
    history: list[AuditIteration] = Field(default_factory=list)
    revisions: list[AuditRevision] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_empty_history(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if not self.history:
            data.pop("history", None)
        if not self.revisions:
            data.pop("revisions", None)
        return data

    @model_validator(mode="after")
    def _check_history(self) -> "AuditRecord":
        if not (self.history or self.revisions):
            return self
        if [h.iteration for h in self.history] != list(range(self.iterations + 1)):
            raise ValueError(f"audit record: the history must hold iterations 0 to {self.iterations}, in order")
        if [r.revision for r in self.revisions] != list(range(1, self.iterations + 1)):
            raise ValueError(f"audit record: the revisions must be 1 to {self.iterations}, in order")
        if self.history[-1].passed != self.passed:
            raise ValueError("audit record: passed differs from the last iteration's")
        if any(h.passed for h in self.history[:-1]):
            raise ValueError("audit record: only the last iteration may pass, since a revision follows only an audit "
                             "that did not pass")
        times = [h.graded_at for h in self.history]
        if all(times):
            try:
                at = [datetime.fromisoformat(t) for t in times]
                ordered = all(a < b for a, b in zip(at, at[1:]))
            except (TypeError, ValueError):  # not an ISO time, or one without a time zone beside one with
                ordered = False
            if not ordered:
                raise ValueError("audit record: the iterations must have been graded one after another, in order")
        return self


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
    # Hash of the scored check list (ids and requirement maps), recorded at freezing so
    # that a changed selection (e.g. B1 re-selection, decision log D31) is detectable.
    checks_sha256: str | None = None
    frozen_at: str | None = None
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
    # Legacy value, no longer assigned: controlled transcripts can still contain third-party
    # personal data from the repository (author names in metadata, changelog credits), so
    # they are sanitised like any other transcript (decision log D38, D40).
    not_needed_controlled = "not_needed_controlled"
    pending = "pending"


class PRProvenance(_Model):
    """The source of a natural PR-review task (population ``natural:pr-review``; protocol §15.6, §17).

    Ids, SHAs and categorical values only: no login, URL or text. ``reviewed_commit`` is the comment's
    ``original_commit_id`` (the pre-review state), ``addressing_commit`` the PR's first later commit that
    changes the commented file (the reference), and ``base_commit`` the merge-base of the first commit's
    parent with the default branch (``base_rule`` ``merge_base``), or that parent when the merge-base cannot
    be determined (``parent_of_first_commit``, approximate). ``merge_state`` applies the merge rule of §15.6.
    """

    dataset: str
    revision: str  # the dataset revision (AIDev v5: the tag's commit)
    pr_id: int
    pr_number: int
    repo_id: int
    agent: str  # AIDev's agent field: a product name, never a model identifier
    comment_id: int  # the correction: the PR's earliest qualifying review comment (S9)
    other_qualifying_comment_ids: list[int] = Field(default_factory=list)
    reply_comment_ids: list[int] = Field(default_factory=list)  # the reviewer's later replies in the thread, before the addressing commit
    issue_id: int | None = None  # the linked issue: the initial request
    issue_number: int | None = None
    base_commit: str
    base_rule: Literal["merge_base", "parent_of_first_commit"]
    first_commit: str  # the PR's first commit: AIDev's first pr_commits row, confirmed with git
    reviewed_commit: str
    addressing_commit: str
    head_commit: str | None = None  # the PR head (refs/pull/<n>/head) in the clone
    default_branch_tip: str | None = None
    merge_state: Literal["no_merges", "merges_not_touching_the_commented_file", "merge_touches_the_commented_file"]
    merges: list[str] = Field(default_factory=list)  # merge commits between the base and the addressing commit
    merges_touching_the_commented_file: list[str] = Field(default_factory=list)
    fidelity: Fidelity
    approximations: list[str] = Field(default_factory=list)
    licence_file_spdx: str | None = None  # identified from the repository's LICENSE file at the base
    licence_file_sha256: str | None = None
    licence_aidev: str | None = None  # AIDev's repository.license field
    licence_agrees: bool | None = None
    snapshot_subdir: str = ""  # the package directory of a monorepo that forms the workspace ("" = the repository root)
    owner_masked: bool = False  # the repository URL's owner is masked under the {owner} rule


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
    # Natural PR-review tasks only (protocol §15.6, §17). Omitted from the JSON while None, so records written
    # before the field existed re-serialise byte for byte.
    natural_pr: PRProvenance | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_natural_pr(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if self.natural_pr is None:
            data.pop("natural_pr", None)
        return data


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
    snapshot_overlays: dict[str, str] = Field(default_factory=dict)  # generated build artefacts (approximations)
    env_requirements: list[str]  # fully pinned, transitively closed requirement list
    candidate_pythonpath: str = "/work"
    repo_test_args: list[str] = Field(default_factory=list)
    scripted_turns: list[str] = Field(default_factory=list)  # controlled sessions: registered user turns
    contracts: dict[str, str] = Field(default_factory=dict)  # variant -> path
    verifiers: list[str] = Field(default_factory=list)  # paths of VerifierSpec JSON files
    candidates: list[str] = Field(default_factory=list)  # paths of Candidate JSON files
    notes: str = ""
