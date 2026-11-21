"""Rule-based triage proposals, ``rule:v1``, and the natural-data screening rule (decision log D47).

A :class:`~tracecontract.schemas.TriageProposal` is a proposal, not ground truth. ``rule:v1``
reads transcript signals only:

* ``unsuitable_task``: no main-agent file change, only documentation, configuration, data or
  presentation files changed (a non-testable objective), or an operational objective
  (install, deploy, commit);
* ``environment_failure``: at least three error tool results with environment markers (command
  not found, permission denied, network, WSL, container, dubious git ownership, disk, timeout)
  that make up at least a tenth of the shell calls, or at least three sandbox messages;
* ``incomplete_evidence``: no recoverable base commit, reads of files absent from the
  snapshot, a session continued from an earlier conversation, or no tool results recorded;
* ``ambiguous_objective``: the contract leaves its objective unresolved (unresolved requirements
  at least half as many as the active ones, or no active change), or a first request of at most
  three words;
* ``apparent_model_failure``: the last test run failed, the user rejected a file edit, or the
  last user prompt reports that the result does not work.

When several fire, the first in this order is the category and every fired signal is a
reason; with none, the category is ``candidate``. Correction events come from the existing
correction-cue rule (:func:`tracecontract.contract.propose_correction_events`), applied after
IDE context blocks (``<ide_opened_file>``, ``<ide_selection>``) are set apart from user prompts.

:func:`screen_eligibility` is the natural-data screening rule: a session is ``rejected``, with
every reason that applies, when its format cannot be replayed, it is unsuitable or failed on
its environment, it has no recoverable base commit (and its replay is then unreconstructable),
no correction candidate or no identified code licence; a session whose base commit is a lead
that needs a network check is ``pending_review``; ``eligible`` needs a verified public base.
"""

from __future__ import annotations

import posixpath
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from .contract import propose_correction_events
from .schemas import (
    Eligibility,
    Event,
    EventKind,
    RequirementKind,
    RequirementStatus,
    Session,
    TaskContract,
    TriageCategory,
    TriageProposal,
)

METHOD = "rule:v1"
_IDE_CONTEXT = ("<ide_opened_file>", "<ide_selection>", "<ide_diagnostics>")
_CONTINUED = "This session is being continued from a previous conversation"
_NOT_RUN = "The user doesn't want to proceed with this tool use"
CODE_EXT = {".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
            ".cs", ".java", ".kt", ".kts", ".go", ".rs", ".rb", ".php", ".swift", ".scala", ".groovy", ".lua", ".sh", ".bash",
            ".ps1", ".psm1", ".bat", ".cmd", ".zig", ".odin", ".sql", ".svelte", ".vue", ".dart", ".m", ".mm", ".r", ".jl",
            ".ex", ".exs", ".erl", ".hs", ".ml", ".fs", ".clj", ".nim", ".cfm", ".cfml", ".cfc", ".asm", ".s", ".gradle",
            ".cmake", ".mk", ".v", ".sv", ".vhd", ".glsl", ".hlsl", ".wgsl", ".sol", ".pl", ".pm", ".tcl", ".f90", ".pas"}
CODE_NAMES = {"makefile", "cmakelists.txt", "dockerfile", "justfile", "rakefile", "build.gradle"}
PRESENTATION_EXT = {".css", ".scss", ".sass", ".less", ".html", ".htm", ".svg"}
TEST_RUNNERS = (
    ("pytest", r"\b(?:py\.test|pytest)\b|-m\s+pytest\b"), ("unittest", r"-m\s+unittest\b"), ("tox", r"\btox\b"),
    ("npm test", r"\b(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:-\S+\s+)*test\b"), ("bun test", r"\bbun\s+(?:run\s+)?test\b"),
    ("vitest", r"\bvitest\b"), ("jest", r"\bjest\b"), ("mocha", r"\bmocha\b"), ("node --test", r"\bnode\s+--test\b"),
    ("cargo test", r"\bcargo\s+test\b"), ("go test", r"\bgo\s+test\b"),
    ("make test", r"\bmake\s+(?:-\S+\s+)*(?:test|tests|check)\b"),
    ("ctest", r"\bctest\b"), ("dotnet test", r"\bdotnet\s+test\b"), ("gradle test", r"\bgradlew?(?:\.bat)?\s+(?:\S+\s+)*test\b"),
    ("mvn test", r"\bmvn\s+(?:\S+\s+)*test\b"), ("rspec", r"\brspec\b"), ("phpunit", r"\bphpunit\b"),
    ("deno test", r"\bdeno\s+test\b"), ("test script", r"(?:^|[\s/\\])(?:run_tests?|tests?)\.(?:sh|ps1|bat|py)\b|-mode\s+test\b"),
)
_FAILED = re.compile(r"\b[1-9]\d* (?:failed|errors?|failures?)\b|^FAILED\b|^FAIL\b|test result: FAILED|Tests?:\s+[1-9]\d* failed"
                     r"|^# fail [1-9]|\bAssertionError\b|\bfailures=[1-9]|\bBUILD FAILED\b", re.M)
_PASSED = re.compile(r"\b[1-9]\d* passed\b|test result: ok|^# fail 0\b|Tests?:\s+\d+ passed|^OK\b|\ball tests passed\b|^PASS\b"
                     r"|\bBUILD SUCCESSFUL\b|\b0 failures\b", re.M | re.I)
ENVIRONMENT_MARKERS = (
    ("command_not_found", r"command not found|^Exit code 127\b|is not recognized as (?:an internal or external command"
                          r"|the name of a cmdlet|a name of a cmdlet)|was not found; run without arguments to install"),
    ("permission", r"Permission denied|Operation not permitted|\bEACCES\b|\bEPERM\b|Access is denied"),
    ("network", r"Could not resolve host|Temporary failure in name resolution|Network is unreachable|ECONNREFUSED|ENOTFOUND"
                r"|getaddrinfo|Connection refused"),
    ("container", r"Cannot connect to the Docker daemon|docker: (?:command )?not found"),
    ("wsl", r"wsl: Failed to translate|WSL \(\d+[^)]*\) ERROR"),
    ("git_safety", r"detected dubious ownership"),
    ("disk", r"No space left on device"),
    ("timeout", r"Command timed out|timed out after"),
)
_SANDBOX = re.compile(r"(?i)\bsandbox\w*\b.{0,80}\b(?:denied|blocked|restrict\w*|not (?:allowed|permitted)|violation)"
                      r"|\b(?:denied|blocked)\b.{0,40}\bsandbox")
_FAILURE_REPORT = re.compile(
    r"(?i)\b(?:still (?:the )?same|still (?:not|isn'?t|doesn'?t|didn'?t|broken|failing|happening|there|showing)"
    r"|(?:does ?n[o']?t|did ?n[o']?t|is ?n[o']?t|not) (?:work|working|change|changed|fix|fixed|load|loading|start|starting"
    r"|render|rendering|show|showing)\b|nothing (?:changed|happens|happened)|no change\b|same (?:error|issue|problem)"
    r"|that'?s not what)")
_OPERATIONAL = re.compile(r"(?i)^\s*(?:npx\s+\S+\s+add|install|deploy|commit|push|clone|claude plugin|set up git)\b")


@dataclass
class TriageSignals:
    """Counts and flags that ``rule:v1`` reads (no transcript text)."""

    user_prompts: int = 0
    ide_context_blocks: int = 0
    correction_event_ids: list[str] = field(default_factory=list)
    shell_calls: int = 0
    tool_results: int = 0
    tool_errors: int = 0
    environment_errors: int = 0
    environment_markers: list[str] = field(default_factory=list)
    sandbox_messages: int = 0
    user_rejections: int = 0
    rejected_edits: int = 0
    final_prompt_reports_failure: bool = False
    file_changes: int = 0
    code_files_changed: int = 0
    presentation_files_changed: int = 0
    other_files_changed: int = 0
    test_runs: int = 0
    test_runner: str | None = None
    last_test: str | None = None  # passed | failed | unknown
    absent_reads: int = 0
    base_commit: str = "none"  # pinned (a task snapshot) or a CommitEvidence status
    unresolved_requirements: list[str] = field(default_factory=list)
    active_requirements: int = 0
    active_changes: int = 0
    short_first_prompt: bool = False
    operational_objective: bool = False
    continued_session: bool = False
    tool_results_recorded: bool = True

    def summary(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("correction_event_ids")
        d["correction_candidates"] = len(self.correction_event_ids)
        return d


def is_ide_context(ev: Event) -> bool:
    return ev.kind == EventKind.user_prompt and ev.text.lstrip().startswith(_IDE_CONTEXT)


def without_ide_context(session: Session) -> Session:
    """The session with IDE context blocks classified as harness-injected text, not user prompts."""
    events = [e.model_copy(update={"kind": EventKind.system_injected}) if is_ide_context(e) else e for e in session.events]
    return session.model_copy(update={"events": events})


def correction_candidates(session: Session) -> list[str]:
    """Event ids flagged by the existing correction-cue rule, IDE context blocks set apart."""
    return [eid for eid, _cues in propose_correction_events(without_ide_context(session))]


def file_kind(path: str) -> str:
    name = posixpath.basename(path).lower()
    ext = posixpath.splitext(name)[1]
    if name in CODE_NAMES or ext in CODE_EXT:
        return "code"
    return "presentation" if ext in PRESENTATION_EXT else "other"


def runner_of(command: str) -> str | None:
    """The test runner a shell command invokes, as a label (``pytest``, ``npm test`` ...), or None."""
    return next((label for label, pat in TEST_RUNNERS if re.search(pat, command, re.I)), None)


def run_outcome(res: Event | None) -> str:
    """``failed``, ``passed`` or ``unknown`` for a test run's result."""
    if res is None:
        return "unknown"
    if _FAILED.search(res.text) or (res.is_error and not _PASSED.search(res.text)):
        return "failed"
    return "passed" if _PASSED.search(res.text) else "unknown"


def collect_signals(session: Session, *, changed_paths: list[str] | None = None, absent_reads: int = 0,
                    base_commit: str = "none", contract: TaskContract | None = None) -> TriageSignals:
    """``rule:v1`` signals of one session.

    ``changed_paths``: paths the session changed (a replay's ``changed``); without them, the
    paths of successful edit calls. Code, presentation and other files are counted over the
    edit calls' paths, or over ``changed_paths`` when there are no edit calls. ``absent_reads``:
    reads of files absent from the snapshot (a replay's ``read_absent_from_base``).
    ``base_commit``: ``pinned`` or a commit-evidence status.
    """
    s = TriageSignals(base_commit=base_commit, absent_reads=absent_reads)
    clean = without_ide_context(session)
    prompts = clean.user_prompts()
    s.user_prompts = len(prompts)
    s.ide_context_blocks = sum(is_ide_context(e) for e in session.events)
    s.correction_event_ids = correction_candidates(session)
    if prompts:
        s.short_first_prompt = len(prompts[0].text.split()) <= 3
        s.operational_objective = bool(_OPERATIONAL.match(prompts[0].text))
        s.final_prompt_reports_failure = len(prompts) > 1 and bool(_FAILURE_REPORT.search(prompts[-1].text))
    s.continued_session = any(e.kind in (EventKind.system_injected, EventKind.metadata) and e.text.lstrip().startswith(_CONTINUED)
                              for e in session.events[:5])
    results = {e.tool_call_id: e for e in session.events if e.kind == EventKind.tool_result and e.tool_call_id}
    s.tool_results = len(results)
    calls = [e for e in session.events if e.kind == EventKind.tool_call and not e.is_sidechain]
    s.tool_results_recorded = bool(results) or not calls
    markers: Counter = Counter()
    edited: list[str] = []
    for ev in calls:
        res = results.get(ev.tool_call_id or "")
        ti = ev.tool_input or {}
        if ti.get("dangerouslyDisableSandbox"):
            s.sandbox_messages += 1
        if res is None:
            continue
        if _NOT_RUN in res.text:
            s.user_rejections += 1
            s.rejected_edits += int(ev.tool_name in ("Edit", "MultiEdit", "Write"))
            continue
        if _SANDBOX.search(res.text):
            s.sandbox_messages += 1
        if res.is_error:
            s.tool_errors += 1
            hit = [label for label, pat in ENVIRONMENT_MARKERS if re.search(pat, res.text, re.M)]
            if hit and ev.tool_name in ("Bash", "PowerShell"):
                s.environment_errors += 1
                markers.update(hit)
        elif ev.tool_name in ("Edit", "MultiEdit", "Write") and isinstance(ti.get("file_path"), str):
            edited.append(str(ti["file_path"]).replace("\\", "/"))
        if ev.tool_name in ("Bash", "PowerShell"):
            s.shell_calls += 1
            runner = runner_of(str(ti.get("command", "")))
            if runner:
                s.test_runs += 1
                s.test_runner, s.last_test = runner, run_outcome(res)
    s.environment_markers = sorted(markers)
    paths = changed_paths if changed_paths is not None else sorted(set(edited))
    # What the objective changes is read from the edit calls: a shell restore (git checkout) of a
    # generated file is not a code change. Without edit calls, every changed path counts.
    kinds = Counter(file_kind(p) for p in (sorted(set(edited)) or paths))
    s.file_changes = len(paths)
    s.code_files_changed, s.presentation_files_changed = kinds["code"], kinds["presentation"]
    s.other_files_changed = kinds["other"]
    if contract is not None:
        active = contract.active()
        s.unresolved_requirements = [r.req_id for r in contract.requirements if r.status == RequirementStatus.unresolved]
        s.active_requirements = len(active)
        s.active_changes = sum(r.kind == RequirementKind.change for r in active)
    return s


_LEADS = ("pinnable_unverified", "linked_commit_unverified")


def propose_triage(s: TriageSignals) -> TriageProposal:
    """The ``rule:v1`` proposal for one session's signals."""
    fired: list[tuple[TriageCategory, str, str]] = []

    def fire(cat: TriageCategory, conf: str, reason: str) -> None:
        fired.append((cat, conf, f"{cat.value}: {reason}"))

    if s.file_changes == 0:
        fire(TriageCategory.unsuitable_task, "high", "no file changed by the main agent")
    elif s.code_files_changed == 0:
        what = "presentation" if s.presentation_files_changed and not s.other_files_changed else \
            "documentation, configuration or data"
        fire(TriageCategory.unsuitable_task, "medium", f"only {what} files changed (non-testable objective)")
    if s.operational_objective:
        fire(TriageCategory.unsuitable_task, "medium", "the first request is an operation (install, deploy, commit)")
    if s.environment_errors >= 3 and s.environment_errors * 10 >= s.shell_calls:
        fire(TriageCategory.environment_failure, "medium", f"{s.environment_errors} error result(s) with environment markers "
             f"({', '.join(s.environment_markers)}) in {s.shell_calls} shell call(s)")
    if s.sandbox_messages >= 3:
        fire(TriageCategory.environment_failure, "medium", f"{s.sandbox_messages} sandbox message(s)")
    if s.base_commit in _LEADS:
        fire(TriageCategory.incomplete_evidence, "low", f"base commit not verified offline ({s.base_commit})")
    elif s.base_commit != "pinned":
        fire(TriageCategory.incomplete_evidence, "high", f"no recoverable base commit ({s.base_commit})")
    if s.absent_reads:
        fire(TriageCategory.incomplete_evidence, "medium", f"{s.absent_reads} read(s) of files absent from the snapshot")
    if s.continued_session:
        fire(TriageCategory.incomplete_evidence, "medium", "continued from an earlier conversation that is not in the file")
    if not s.tool_results_recorded:
        fire(TriageCategory.incomplete_evidence, "medium", "no tool results recorded")
    if s.unresolved_requirements and (2 * len(s.unresolved_requirements) >= max(1, s.active_requirements)
                                      or s.active_changes == 0):
        fire(TriageCategory.ambiguous_objective, "medium", f"{len(s.unresolved_requirements)} unresolved of "
             f"{s.active_requirements} active contract requirement(s)")
    if s.short_first_prompt:
        fire(TriageCategory.ambiguous_objective, "low", "the first request has at most three words")
    if s.last_test == "failed":
        fire(TriageCategory.apparent_model_failure, "medium", f"the last test run ({s.test_runner}) failed")
    if s.rejected_edits:
        fire(TriageCategory.apparent_model_failure, "low", f"the user rejected {s.rejected_edits} file edit(s)")
    if s.final_prompt_reports_failure:
        fire(TriageCategory.apparent_model_failure, "low", "the last user prompt reports that the result does not work")
    notes = []
    if s.unresolved_requirements and not any(c == TriageCategory.ambiguous_objective for c, _, _ in fired):
        notes.append(f"note: {len(s.unresolved_requirements)} unresolved, unscored contract requirement(s) "
                     f"({', '.join(s.unresolved_requirements)}); the objective itself is resolved")
    order = [TriageCategory.unsuitable_task, TriageCategory.environment_failure, TriageCategory.incomplete_evidence,
             TriageCategory.ambiguous_objective, TriageCategory.apparent_model_failure]
    for cat in order:
        hits = [(c, conf) for c, conf, _ in fired if c == cat]
        if hits:
            conf = "high" if any(x == "high" for _, x in hits) else ("medium" if any(x == "medium" for _, x in hits) else "low")
            return TriageProposal(category=cat, method=METHOD, confidence=conf,  # type: ignore[arg-type]
                                  reasons=[r for _, _, r in fired] + notes, correction_event_ids=s.correction_event_ids)
    conf = "medium" if s.correction_event_ids else "low"
    reasons = [f"candidate: {len(s.correction_event_ids)} correction candidate(s) under the cue rule"] + notes
    return TriageProposal(category=TriageCategory.candidate, method=METHOD, confidence=conf,  # type: ignore[arg-type]
                          reasons=reasons, correction_event_ids=s.correction_event_ids)


def screen_eligibility(s: TriageSignals, proposal: TriageProposal, *, replay_fidelity: str | None, licence: str | None,
                       replay_supported: bool = True) -> tuple[Eligibility, list[str]]:
    """The natural-data screening rule (D47): ``rejected`` with every reason that applies;
    ``pending_review`` when only offline checks are missing; ``eligible`` needs a verified,
    public base commit and so is never reached offline."""
    reasons = []
    if not replay_supported:
        reasons.append("format: transcript replay supports Claude Code sessions only")
    reasons += [r for r in proposal.reasons if r.startswith(("unsuitable_task:", "environment_failure:"))]
    lead = s.base_commit in _LEADS
    if not lead and s.base_commit != "pinned":
        reasons.append(f"no recoverable base commit ({s.base_commit})")
    if replay_fidelity == "unreconstructable" and not lead and s.base_commit != "pinned":
        reasons.append("replay: unreconstructable without a base tree")
    if not s.correction_event_ids:
        reasons.append("no correction candidate under the correction-cue rule")
    if not licence:
        reasons.append("no code licence identified")
    if reasons:
        return Eligibility.rejected, reasons
    return Eligibility.pending_review, ["pending: the base commit and the repository's publicness need a network check"
                                        if lead else "pending: human review"]
