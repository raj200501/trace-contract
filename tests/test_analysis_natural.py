"""The analysis of a natural PR-review run (plan WP-G; protocol §15.5, §15.6, §16, §17, §19; the natural-arm recipe, D64).

* The first prompt of a natural task is its session's first user prompt (the linked issue), not the smallest
  ``introduced_at``: a commit event's id sorts before the issue's, and a reply's before the review comment's.
* The source-evidence block: per family and condition, whether each pre-review state is accepted; the correction
  requirements; each pre-review state's D19 value and second-labeling label; a banner (source evidence, not a human
  label); and paired sign-flip comparisons only outside case-study mode.
* The independent labeler on natural tasks: a pass on a pre-review state is ambiguous; the agreement on the pre-review
  states is marked as existing before the labeler; a labeler whose status.json is not usable is left out and reported.
* B3 (diff_derived) is a secondary condition: its own tables, outside the primary null tally.
* Per-family flags (B1 unavailable, B1 equal to the D19 regression norm, the sample), the funnel S1 to S11 of both
  samples, reliability and cost, with their inputs hashed in meta.inputs and no thread text or local path written.
* Case-study mode (§19.6): below 10 accepted tasks in the committed index, per-family tables only, with no pooled rate,
  interval or p-value; with 10 or more, the full rules with sign-flip p-values. The run's families are checked against
  the index's S11 set.
* The duplicate representative is the pre-review state.
* The review's findings: S10's cost per accepted task counts time and fetches on one basis (every family S10 processed,
  rejected ones included), the HTML report builds from a case-study analysis (per-family tables only) and shows B3 apart
  with 10 or more families, the CLI refuses the pilot rules for a natural run with a message, the records are read at
  the run's code revision, and D64's decisions 10 (a view clustered by repository) and 14 (correction requirements are
  scored and active; a reference contract that does not observe the correction is said to).
* The frozen pilot and the recorded runs regenerate their analysis.md byte for byte.

Synthetic fixtures only: natural families laid out by tests/natural_task_layout.py under a scratch git repository's
``data/natural/`` (git-ignored there; the index and synthetic screening records are committed), each with a hand-written
reference contract, a pool with D19 and construction labels, and a hand-written run (manifest and results; nothing is
graded, no Docker). They check code behaviour and are not research evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest

from natural_task_layout import (
    AGENT_ONLY_MARKERS, BASE_TEST, COMMENT_TEXT, HUNK_TEXT, IMAGE, IMAGE_ID, ISSUE_TEXT, PR_TEXT, REFERENCE_TEST, REPLY_TEXT,
    T0, TEST_ARGS, NaturalTask, build_natural_task, git, init_git, write_index_row,
)
from tracecontract import analysis, cli
from tracecontract.analysis import (
    INDEPENDENT_LABELER, INDEX_CHECK_RULE, NATURAL_FETCH_LOG, NATURAL_FUNNEL, NATURAL_INDEX, NATURAL_S9, NATURAL_SIZE_THRESHOLD,
    NO_CORRECTION_REQUIREMENT, ORDER_RULE, PILOT_LABELER, SECONDARY_CONDITIONS, NaturalRunError, analyze, independent_label,
    natural_first_prompt, repository_root, to_markdown,
)
from tracecontract.report import build_report
from tracecontract.schemas import (
    AuditFindingEntry, AuditIteration, AuditRecord, AuditRevision, Candidate, CandidateOrigin, ContractVariant, EvidenceSpan,
    GenerationRecord, Isolation, Label, LabelerKind, Outcome, Population, Requirement, RequirementKind, RequirementStatus, Split,
    TaskContract, TaskManifest, VerificationResult, VerifierCondition, VerifierSpec, sha256_text,
)
from tracecontract.store import append_jsonl, dump, load, write_json
from tracecontract.verifier import build_spec

REPO = Path(__file__).resolve().parents[1]
HARNESS = "tc-harness/0.3.5"
RUN_ID = "natural-pr-v1"
REPEATS = 3  # the run's repeats per pair, as its manifest records them
T1 = "2026-11-21T11:30:00+00:00"  # the run's end, as its manifest records it
# verifier id -> condition; the reference checks and the labeler are label support (condition reference_check)
VERIFIERS = {"initial_plain": "initial_plain", "full_plain": "full_plain", "full_audited": "full_audited",
             "repo_tests": "repo_tests", "diff_derived": "diff_derived", "reference_check": "reference_check",
             INDEPENDENT_LABELER: "reference_check"}
# kind: (origin, construction value, violated requirement key or None)
POOL = {"eval-alt-1": (CandidateOrigin.valid_alternative, "valid", None),
        "eval-alt-2": (CandidateOrigin.valid_alternative, "valid", None),
        "eval-nm-1": (CandidateOrigin.constructed_near_miss, "invalid", "corr"),
        "eval-nm-2": (CandidateOrigin.constructed_near_miss, "invalid", "reply"),
        "eval-nm-3": (CandidateOrigin.constructed_near_miss, "invalid", "issue")}
REQ = {"issue": "R-issue", "corr": "R-corr", "reply": "R-reply", "commit": "R-commit"}
GRADED = ("reference", "noop-eval", "pre-review", *POOL)  # the eval split and the reference, as evaluate grades them
GEN = GenerationRecord(generator="config-A", run_id="wf_fixture/run", prompt_sha256="ab" * 32, created_at=T0,
                       budget={"started_at": T0, "ended_at": T0, "wall_s": 60.0, "turns": 10, "tool_calls": 20,
                               "run_record": "build-session:fixture.jsonl"})
STAGES = [("S1", "pull_request", 1000), ("S2", "pull_request", 500), ("S3", "review_comment", 400),
          ("S4", "review_comment", 300), ("S5", "review_comment", 200), ("S6", "review_comment", 150),
          ("S7", "review_comment", 120), ("S8", "review_comment", 100), ("S8'", "review_comment", 999),
          ("S8a", "review_comment", 80)]
# The construction world (build_world's ``construction``; D64, D70). The checks of each verifier of the recipe in family 0
# (its id is its condition here), and the reference checks'; B2 and C2 are graded too.
CONSTRUCTION_CHECKS = {"initial_plain": 3, "initial_audited": 4, "full_plain": 5, "full_audited": 6, "llm_freeform": 2,
                       "diff_derived": 3, "reference_check": 4}
CONSTRUCTION_GRADED = {"initial_audited": "initial_audited", "llm_freeform": "llm_freeform"}
# family number -> condition -> (revisions, passed, finding codes of the last iteration; None: a record without history)
AUDITS = {0: {"initial_audited": (2, True, []), "full_audited": (3, False, ["reference_not_passing"])},
          1: {"initial_audited": (0, True, []), "full_audited": (3, False, ["false_acceptance_dev", "uncovered_requirement"])},
          2: {"initial_audited": (1, False, None), "full_audited": (1, True, [])}}
B3_TAKEN_OUT = (2,)  # family 2: B3's selection kept no test, so the run grades no B3 for it
SECRET_FINDING = "test_secret_mod.py::test_never_copied failed"  # a finding message: never in the analysis
REFCHECK_STATUS_RECORDS = {0: {"status": "usable", "fix_rounds": 1, "reasons": [SECRET_FINDING]},
                           1: {"status": "unusable", "fix_rounds": 2, "reasons": [SECRET_FINDING]}}


def _patch(nt: NaturalTask, body: str) -> str:
    return f"--- a/fxnat/mod.py\n+++ b/fxnat/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = '{nt.task_id}-{body}'\n"


def _req(rid: str, event: str) -> Requirement:
    return Requirement(req_id=rid, statement=f"Statement of {rid}.", kind=RequirementKind.change,
                       status=RequirementStatus.explicit, introduced_at=event,
                       evidence=[EvidenceSpan(event_id=event, start=0, end=1, quote="x")], proposer="fixture")


def _d19(value: str, violated: list[str]) -> Label:
    return Label(value=value, violated_requirements=violated, labeler=PILOT_LABELER, labeler_kind=LabelerKind.model, timestamp=T0)


def d19_note(why: str) -> str:
    """A D19 label's note as scripts/propose_labels.py writes it: the reason, then its details (outcomes, failing checks)."""
    return why + " | " + json.dumps({"refcheck_outcome": "task_failure", "refcheck_failed": ["test_x.py::test_y"],
                                     "regression_outcome": "pass", "regression_failed": [], "repeats": 3})


def relabel_d19(nt: NaturalTask, kind: str, value: str, violated: list[str], note: str) -> None:
    """Give the candidate ``kind`` of ``nt`` (``eval-nm-1``, ``pre-review``, ...) the D19 proposal ``value`` with ``note``, in
    place of its D19 label, as scripts/propose_labels.py replaces it; its other labels are kept."""
    path = nt.task_dir / "candidates" / f"{nt.candidate_id(kind)}.json"
    c = load(path, Candidate)
    label = _d19(value, violated).model_copy(update={"note": note})
    dump(c.model_copy(update={"labels": [lb for lb in c.labels if lb.labeler != PILOT_LABELER] + [label]}), path)


def _outcome(i: int, vid: str, kind: str) -> str:
    """Stub outcomes. C1 (initial_plain) accepts what the correction rules out, C3 and C4 do not; B1 accepts everything
    but the reference's failures; B3 accepts the near miss of the comment. The reference checks pass the pre-review
    state in family 1, and the labeler passes it in family 0."""
    if kind == "reference":
        return "task_failure" if (vid, i) == ("initial_plain", 0) else "pass"  # C1 fails its reference in family 0
    if kind == "noop-eval":
        return "pass" if vid == "repo_tests" else "task_failure"
    if kind == "pre-review":
        if vid == "reference_check":
            return "pass" if i == 1 else "task_failure"
        if vid == INDEPENDENT_LABELER:
            return "pass" if i == 0 else "task_failure"
        return "pass" if vid in ("initial_plain", "repo_tests") else "task_failure"
    if kind.startswith("eval-alt"):
        return "task_failure" if (vid, kind, i % 2) == ("full_audited", "eval-alt-2", 0) else "pass"
    if vid in ("reference_check", INDEPENDENT_LABELER):
        return "task_failure"  # every near miss fails both label-support verifiers
    accepts = {"eval-nm-1": ("initial_plain", "repo_tests", "diff_derived"), "eval-nm-2": ("initial_plain", "full_plain", "repo_tests"),
               "eval-nm-3": ("repo_tests",)}[kind]
    return "pass" if vid in accepts else "task_failure"


def _decorate(nt: NaturalTask, i: int, *, commit_requirement: bool, no_issue_requirement: bool,
              duplicate_of_pre: bool, unscored_at_comment: bool = False, no_correction: bool = False,
              labeler_frozen_at: str | None = None) -> dict[str, Candidate]:
    """Add the reference contract, the pool, the D19 labels, the labeler and its status, and the regression-norm overlay
    to the layout's task ``nt`` (family number ``i``); return the graded candidates by kind. ``unscored_at_comment``: the
    reference contract also has an unscored requirement introduced at the review comment; ``no_correction``: none of its
    requirements is introduced at the comment or the reply (D64, decision 14); ``labeler_frozen_at``: the labeler's spec
    is frozen at that time."""
    td = nt.task_dir
    reqs = [] if no_issue_requirement else [_req(REQ["issue"], nt.event("issue"))]
    if not no_correction:
        reqs += [_req(REQ["corr"], nt.event("comment")), _req(REQ["reply"], nt.event("reply"))]
    if unscored_at_comment:
        reqs.append(_req("R-unscored", nt.event("comment")).model_copy(update={"scored": False}))
    if commit_requirement:  # a requirement anchored at a commit event: its id sorts before the issue's
        reqs.append(_req(REQ["commit"], nt.event("first")))
    contract = TaskContract(contract_id=f"{nt.task_id}-reference", task_id=nt.task_id, session_id=nt.session_id,
                            variant=ContractVariant.reference, requirements=reqs, created_by="fixture", created_at=T0,
                            generation=GEN.model_copy(update={"budget": {**GEN.budget, "turns": 5, "tool_calls": 7, "wall_s": 30.0}}))
    dump(contract, td / "contracts" / "reference.json")
    m = load(td / "task.json", TaskManifest)
    cands = {c.candidate_id.removeprefix(nt.task_id + "-"): c for c in (load(td / p, Candidate) for p in m.candidates)}
    pre = cands["pre-review"]
    pre_d19 = _d19("ambiguous", []) if i == 1 else _d19("invalid", [REQ["corr"]])  # family 1: the reference checks pass it
    cands["pre-review"] = pre.model_copy(update={"labels": [*pre.labels, pre_d19]})
    for kind, (origin, value, key) in POOL.items():
        violated = [REQ[key]] if key else []
        patch = pre.patch if duplicate_of_pre and kind == "eval-nm-1" else _patch(nt, kind)
        labels = [Label(value=value, violated_requirements=violated, labeler="construction:fixture",
                        labeler_kind=LabelerKind.construction, timestamp=T0), _d19(value, violated)]
        cands[kind] = Candidate(candidate_id=nt.candidate_id(kind), task_id=nt.task_id, origin=origin, split=Split.eval,
                                patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture", labels=labels,
                                generation=None if kind == "eval-nm-3" else GEN)
    for c in cands.values():
        dump(c, td / "candidates" / f"{c.candidate_id}.json")
    tests = td / "verifiers" / INDEPENDENT_LABELER / "tests"
    tests.mkdir(parents=True)
    (tests / "test_labeler.py").write_text("def test_labeler_case():\n    assert True\n", encoding="utf-8")
    spec = build_spec(verifier_id=INDEPENDENT_LABELER, task_id=nt.task_id, condition=VerifierCondition.reference_check,
                      test_dir=tests, task_dir=td, isolation=Isolation.process_separated,
                      check_ids=["test_labeler.py::test_labeler_case"],
                      generation=GEN.model_copy(update={"generator": "config-B"}))
    if labeler_frozen_at is not None:
        spec = spec.model_copy(update={"frozen": True, "frozen_at": labeler_frozen_at})
    dump(spec, td / "verifiers" / INDEPENDENT_LABELER / "spec.json")
    write_json({"verifiers": [f"verifiers/{INDEPENDENT_LABELER}/spec.json"]}, td / "verifiers_extra.json")
    status = "unusable" if i == 2 else "usable"
    write_json({"status": status, "round": 2 if i == 2 else 1, "reasons": ["synthetic fixture"]},
               td / "verifiers" / INDEPENDENT_LABELER / "status.json")
    norm = td / "labels" / "base_tests_overlay" / TEST_ARGS[-1]
    norm.parent.mkdir(parents=True)
    norm.write_text(REFERENCE_TEST if i == 1 else BASE_TEST, encoding="utf-8")  # family 1: B1 equals the regression norm
    if i == 0:  # family 0: B1 unavailable by S10
        s10 = json.loads((td / "s10.json").read_text(encoding="utf-8"))
        s10["b1"] = {"available": False, "n_checks": 0, "mode": "repo_tests (in_process)"}
        write_json(s10, td / "s10.json")
    dump(m.model_copy(update={"contracts": {"reference": "contracts/reference.json"},
                              "candidates": [f"candidates/{c.candidate_id}.json" for c in cands.values()]}), td / "task.json")
    return {k: cands[k] for k in GRADED}


def _audit_record(revisions: int, passed: bool, codes: list[str] | None) -> AuditRecord:
    """An audit:v1 record with ``revisions`` revisions; ``codes``: the finding codes of its last iteration, each with a
    message naming a check (never to be copied), or None for a record without history (as written before D62)."""
    if codes is None:
        return AuditRecord(procedure="audit:v1", iterations=revisions, passed=passed, findings=[f"lint_x: {SECRET_FINDING}"])
    history = [AuditIteration(iteration=k, passed=passed and k == revisions, content_sha256=f"{k:064x}", checks_sha256=f"{k:064x}",
                              findings=[AuditFindingEntry(code=c, message=SECRET_FINDING)
                                        for c in (codes if k == revisions else ["reference_not_passing"])])
               for k in range(revisions + 1)]
    return AuditRecord(procedure="audit:v1", iterations=revisions, passed=passed, findings=[f"{c}: {SECRET_FINDING}" for c in codes],
                       history=history, revisions=[AuditRevision(revision=k) for k in range(1, revisions + 1)])


def _construct(nt: NaturalTask, i: int, b3_taken_out: tuple[int, ...] = B3_TAKEN_OUT) -> None:
    """The construction records of family ``i`` (D64, D70), by ``k = i % 3``: every verifier of the recipe registered with
    its checks (family ``i`` has ``i`` more checks per verifier), the audit records of C2 and C4 (:data:`AUDITS`), B3 taken
    out by its selection for k in ``b3_taken_out`` (unavailable.json, its spec not registered), the reference checks' status
    record (:data:`REFCHECK_STATUS_RECORDS`; none for k = 2) and the two recovered contracts."""
    td = nt.task_dir
    m = load(td / "task.json", TaskManifest)
    registered = list(m.verifiers)
    k = i % 3
    for vid, n in CONSTRUCTION_CHECKS.items():
        tests = td / "verifiers" / vid / "tests"
        tests.mkdir(parents=True)
        names = [f"test_{vid}_{j}" for j in range(n + i)]
        (tests / f"test_{vid}.py").write_text("".join(f"def {x}():\n    assert True\n\n\n" for x in names), encoding="utf-8")
        spec = build_spec(verifier_id=vid, task_id=nt.task_id, condition=VerifierCondition(vid), test_dir=tests, task_dir=td,
                          check_ids=[f"test_{vid}.py::{x}" for x in names], generation=GEN)
        if vid in AUDITS[k]:
            spec = spec.model_copy(update={"audit": _audit_record(*AUDITS[k][vid])})
        dump(spec, td / "verifiers" / vid / "spec.json")
        if vid == "diff_derived" and k in b3_taken_out:  # as scripts/select_b3_tests.py leaves a B3 that kept no test
            write_json({"schema": "verifier-unavailable:v1", "condition": "diff_derived", "available": False,
                        "reason": "synthetic"}, td / "verifiers" / vid / "unavailable.json")
            continue
        registered.append(f"verifiers/{vid}/spec.json")
    if k in REFCHECK_STATUS_RECORDS:
        write_json(REFCHECK_STATUS_RECORDS[k], td / "verifiers" / "reference_check" / "status.json")
    contracts = dict(m.contracts)
    for variant, extra in (("initial_only", 0), ("full_session", 1)):
        reqs = [_req(f"R{j}", nt.event("issue")) for j in range(2 + extra + i)]
        reqs += [_req("R-unscored", nt.event("issue")).model_copy(update={"scored": False}),
                 _req("R-old", nt.event("issue")).model_copy(update={"status": RequirementStatus.superseded,
                                                                     "superseded_by": "R0"})]
        dump(TaskContract(contract_id=f"{nt.task_id}-{variant}", task_id=nt.task_id, session_id=nt.session_id,
                          variant=ContractVariant(variant), requirements=reqs, created_by="fixture", created_at=T0, generation=GEN),
             td / "contracts" / f"{variant}.json")
        contracts[variant] = f"contracts/{variant}.json"
    dump(m.model_copy(update={"verifiers": registered, "contracts": contracts}), td / "task.json")


def _screening(root: Path) -> None:
    """Synthetic screening records (ids and counts only), committed with the index."""
    write_json({"stages": [{"id": s, "unit": u, "count": n, "prs": n // 2, "repos": n // 10} for s, u, n in STAGES]},
               root / NATURAL_FUNNEL)
    write_json({"summary": {"comments": 150, "qualifying": 31, "excluded_judges_disagree": 2, "failed": 117,
                            "failed_by_reason": {"not_addressed": 6, "not_behaviour_change_or_defect": 92,
                                                 "commits_not_fetchable": 19},
                            "qualifying_distinct_prs": 25, "qualifying_distinct_repositories": 14,
                            "s11_families": {"families": 20}}}, root / NATURAL_S9["first"])
    write_json({"summary": {"comments": 534, "judged": 400, "qualifying": 91, "excluded_judges_disagree": 10, "failed": 433,
                            "failed_by_reason": {"fetch_over_the_caps": 65}, "qualifying_distinct_prs": 42,
                            "qualifying_distinct_repositories": 19}}, root / NATURAL_S9["extension"])


def build_world(root: Path, n: int, *, harness: str = HARNESS, extra_s11: tuple[str, ...] = (), not_s11: tuple[str, ...] = (),
                commit_requirement: bool = False, no_issue_requirement: bool = False, duplicate_of_pre: bool = False,
                unresolved: bool = True, code_revision: str | None = None, labeler_graded: bool = True,
                extra_rows: tuple[tuple[str, dict], ...] = (), unscored_at_comment: bool = False,
                no_correction: tuple[int, ...] = (), labeler_frozen_at: dict[int, str] | None = None,
                construction: bool = False, task_ids: tuple[str, ...] | None = None,
                b3_taken_out: tuple[int, ...] = B3_TAKEN_OUT) -> tuple[Path, list[NaturalTask]]:
    """``n`` accepted families NP-90 on (``task_ids``: these ids instead, in their order), their index rows (and ``extra_s11``
    accepted rows without a task, and ``extra_rows``: ``(task id, write_index_row's arguments)``), three rejected or unbuilt
    rows, the screening records and the fetch log; and the run natural-pr-v1 over the ``n`` families. The run's manifest
    records what ``evaluate`` records: the commit of those records as its code revision, as ``evaluate`` records HEAD
    (``code_revision`` names another), with its start, end, repeats, pilot flag and one invocation. ``labeler_graded``: the
    run grades the independent labeler. ``no_correction`` and ``labeler_frozen_at`` (by family number): see
    :func:`_decorate`. ``construction``: every family also gets the construction records of :func:`_construct` (B3 taken out
    where ``i % 3`` is in ``b3_taken_out``), and the run also grades C2 and B2, and no B3 where B3 was taken out."""
    ids = [f"NP-{90 + i:02d}" for i in range(n)] if task_ids is None else list(task_ids)
    if len(ids) != n:
        raise ValueError(f"{n} families, {len(ids)} task ids")
    root.mkdir(parents=True, exist_ok=True)
    init_git(root)
    tasks = [build_natural_task(root, tid, index=False) for tid in ids]
    graded = {nt.task_id: _decorate(nt, i, commit_requirement=commit_requirement, no_issue_requirement=no_issue_requirement,
                                    duplicate_of_pre=duplicate_of_pre, unscored_at_comment=unscored_at_comment,
                                    no_correction=i in no_correction,
                                    labeler_frozen_at=(labeler_frozen_at or {}).get(i)) for i, nt in enumerate(tasks)}
    if construction:
        for i, nt in enumerate(tasks):
            _construct(nt, i, b3_taken_out)
    for i, nt in enumerate(tasks):
        write_index_row(root, nt.task_id, s11=nt.task_id not in not_s11, commit=False, sample="first" if i < 6 else "extension",
                        repo_id=900 + i // 2)
    for tid in extra_s11:
        write_index_row(root, tid, s11=True, commit=False, sample="extension", repo_id=990)
    write_index_row(root, "NP-80", s11=False, outcome="rejected", commit=False, sample="first", repo_id=777,
                    s10={"outcome": "rejected", "reason": "base tests fail to collect: synthetic", "stage": "S10"})
    write_index_row(root, "NP-81", s11=False, outcome="rejected", commit=False, sample="first", repo_id=778,
                    s10={"outcome": "rejected", "reason": "no resolvable closure: synthetic", "stage": "S10"})
    write_index_row(root, "NP-82", s11=False, outcome="not built", commit=False, sample="first", role="reserve",
                    s10={"outcome": "not built"})
    for tid, row in extra_rows:
        write_index_row(root, tid, commit=False, **row)
    _screening(root)
    git(root, "add", "--", NATURAL_INDEX, NATURAL_FUNNEL, *NATURAL_S9.values())
    git(root, "commit", "-q", "--no-verify", "-m", "natural records (synthetic fixture)")
    revision = git(root, "rev-parse", "HEAD").stdout.decode("ascii").strip() if code_revision is None else code_revision
    log = root / NATURAL_FETCH_LOG
    log.write_text("".join(json.dumps(e) + "\n" for e in (
        {"stage": "S10", "repo_id": 900, "delta": 1000}, {"stage": "S10", "repo_id": 901, "delta": 2000},
        {"stage": "S9", "repo_id": 900, "delta": 5}, {"stage": "S10", "repo_id": 777, "delta": 300})), encoding="utf-8")
    run = root / "data" / "natural" / "runs" / RUN_ID
    run.mkdir(parents=True)
    manifest: dict = {"run_id": RUN_ID, "started_at": T0, "code_revision": revision, "split": "eval", "repeats": REPEATS,
                      "conditions": None, "tasks": [],
                      "invocations": [{"at": T0, "tasks": [nt.task_id for nt in tasks], "code_revision": revision, "pilot": True}],
                      "pilot": True, "extra_verifiers": True, "finished_at": T1}
    graded_by_all = {**VERIFIERS, **(CONSTRUCTION_GRADED if construction else {})}
    for i, nt in enumerate(tasks):
        cands = graded[nt.task_id]
        verifiers = {v: c for v, c in graded_by_all.items() if (labeler_graded or v != INDEPENDENT_LABELER)
                     and not (construction and v == "diff_derived" and i % 3 in b3_taken_out)}
        manifest["tasks"].append({
            "task_id": nt.task_id, "family_id": nt.task_id, "task_dir": f"data/natural/tasks/{nt.task_id}", "image": IMAGE,
            "image_id": IMAGE_ID if i != 3 else "sha256:" + "11" * 32,  # family 3: the run's image is another one
            "verifiers": {v: {"condition": c} for v, c in verifiers.items()},
            "candidates": {c.candidate_id: {"origin": c.origin.value, "patch_sha256": c.patch_sha256} for c in cands.values()}})
        for vid in verifiers:
            for kind, c in cands.items():
                oc = _outcome(i, vid, kind)
                if unresolved and (i, vid, kind) == (0, "full_plain", "eval-alt-1"):
                    oc = "unresolved"  # repeats that disagree, a rejection
                append_jsonl(VerificationResult(run_id=RUN_ID, task_id=nt.task_id, verifier_id=vid, candidate_id=c.candidate_id,
                                                outcome=Outcome(oc), reward=1.0 if oc == "pass" else 0.0, started_at=T0,
                                                finished_at=T0, wall_s=0.5, harness_version=harness), run / "results.jsonl")
    write_json(manifest, run / "manifest.json")
    return run, tasks


@dataclass(frozen=True)
class World:
    root: Path  # the scratch repository
    run: Path  # the run directory, data/natural/runs/natural-pr-v1
    tasks: list[NaturalTask]
    a: dict  # the analysis

    @property
    def md(self) -> str:
        return (self.run / "analysis.md").read_text()


def _analysed(root: Path, n: int) -> World:
    run, tasks = build_world(root, n)
    return World(root, run, tasks, analyze(run, root / "data" / "natural" / "tasks", allow_proposed=True, n_boot=50))


@pytest.fixture(scope="module")
def three(tmp_path_factory) -> World:
    """Three accepted families: case-study mode."""
    return _analysed(tmp_path_factory.mktemp("three") / "repo", 3)


@pytest.fixture(scope="module")
def ten(tmp_path_factory) -> World:
    """Ten accepted families: the full rules (§15.6, §15.7)."""
    return _analysed(tmp_path_factory.mktemp("ten") / "repo", 10)


def _keys(x) -> set[str]:
    """Every dict key anywhere in ``x``."""
    if isinstance(x, dict):
        return {k for k in x} | {k2 for k, v in x.items() for k2 in _keys(v)}
    if isinstance(x, list):
        return {k for v in x for k in _keys(v)}
    return set()


# --------------------------------------------------------------------------- case-study mode (§19.6)

# Keys that only pooled tables, intervals and tests carry (metrics.summarize, _pooled, paired comparisons, the bootstrap).
POOLED_KEYS = {"ci95", "exact95", "macro", "rate", "youden_j", "signflip", "p_greater", "p_two_sided", "floor_two_sided",
               "false_acceptance", "false_rejection", "bootstrap", "pooled", "difference", "per_task_rates"}


def test_three_families_are_case_studies_with_per_family_tables_only(three):
    run, a = three.run, three.a
    cs = a["meta"]["case_study"]
    assert cs["applies"] is True and cs["accepted_in_run"] == cs["accepted_in_index"] == 3
    assert cs["threshold"] == NATURAL_SIZE_THRESHOLD == 10
    assert cs["why"] == ("the run grades 3 accepted task(s) of its own (its families accepted, S11, in the committed index), "
                         "fewer than 10; each run is reported on its own (protocol §20.3)")
    assert a["conditions"] == {} and a["comparisons"] == [] and "bootstrap" not in a["meta"]
    assert not POOLED_KEYS & _keys(a), POOLED_KEYS & _keys(a)  # no pooled rate, interval or p-value anywhere
    assert json.loads((run / "analysis.json").read_text()) == a
    # The primary display is per family, under D19, each distinct graded patch once; B3 is apart.
    assert list(a["per_family"]) == ["initial_plain", "full_plain", "full_audited", "repo_tests"]
    assert set(a["per_family"]["initial_plain"]) == {"NP-90", "NP-91", "NP-92"}
    # NP-90: pre-review (invalid), nm-1, nm-2, nm-3 invalid: C1 accepts the pre-review, nm-1 and nm-2; no valid rejected.
    assert a["per_family"]["initial_plain"]["NP-90"] == {"fa_num": 3, "fa_den": 4, "fr_num": 0, "fr_den": 2}
    # NP-91: the pre-review state is D19 ambiguous (the reference checks pass it), so it is not counted.
    assert a["per_family"]["initial_plain"]["NP-91"] == {"fa_num": 2, "fa_den": 3, "fr_num": 0, "fr_den": 2}
    assert a["per_family"]["full_audited"]["NP-90"] == {"fa_num": 0, "fa_den": 4, "fr_num": 1, "fr_den": 2}
    assert list(a["secondary"]["per_family"]) == ["diff_derived"]
    assert a["sanity_per_family"]["initial_plain"]["NP-90"]["reference"] == {"pass": 0, "n": 1, "outcomes": {"task_failure": 1}}
    assert a["sanity_per_family"]["repo_tests"]["NP-91"]["noop"]["pass"] == 1
    assert a["by_negative_type_per_family"]["initial_plain"]["NP-90"]["correction_violating"] == {"accepted": 3, "n": 3}
    assert a["by_negative_type_per_family"]["initial_plain"]["NP-90"]["initial_violating"] == {"accepted": 0, "n": 1}
    og = a["oracle_gated"]["conditions"]["initial_plain"]
    assert og["dropped"] == {"NP-90": "does not pass its reference (task_failure)"} and og["cells_kept"] == 2
    assert og["lost_yield_per_family"] == {"NP-90": {"invalid": 4, "valid": 2}} and "NP-90" not in og["per_family"]
    md = (run / "analysis.md").read_text()
    assert md.startswith("# Analysis (proposed labels allowed (automated pilot))\n\n> **Exploratory case studies** (protocol "
                         "§19.6, §20.3): the run grades 3 accepted task(s) of its own")
    assert ("The run's 3 families are the 3 accepted families (S11) of its sample(s), first, in the committed index "
            "(data/manifests/natural_tasks_index.json at the run's code revision") in md
    for absent in ("All FA", "p (A > B)", "Null results", "Appendix: cluster-bootstrap", "Pooled false acceptance", "95%"):
        assert absent not in md, absent
    for present in ("## Primary display: false acceptance and false rejection per task family",
                    "## Secondary condition: B3 (diff-derived)", "## Source-evidence labels (reported apart from D19)",
                    "## Independent labeler: a second labeling, per task family", "## Funnel S1 to S11, both samples",
                    "## Build and replay reliability", "## Cost and time per accepted task", "## Per-task outcomes"):
        assert present in md, present
    assert "| initial_plain | 3/4 | 0/2 | 2/3 | 0/2 | 3/4 | 0/2 |" in md
    assert to_markdown(a) == md


def test_ten_families_get_the_full_rules_with_sign_flip_tests(ten):
    run, a = ten.run, ten.a
    cs = a["meta"]["case_study"]
    assert cs["applies"] is False and cs["accepted_in_run"] == cs["accepted_in_index"] == 10
    assert "§15.6 and §15.7 apply in full to the run (protocol §20.3)" in cs["why"]
    assert a["meta"]["reporting_rules"]["rules"] == "v0.8" and a["meta"]["bootstrap"]["inferential"] is True
    assert list(a["conditions"]) == ["initial_plain", "full_plain", "full_audited", "repo_tests"]
    c1c3 = next(d for d in a["comparisons"] if (d["a"], d["b"], d["metric"]) == ("initial_plain", "full_plain", "fa"))
    assert c1c3["signflip"]["pooled"]["k"] == 10 and c1c3["ci95_not_inferential"] is False
    # Source evidence: C1 accepts every family's pre-review state, C3 none: +1 in each of 10 families.
    se = a["source_evidence"]
    sf = next(d for d in se["comparisons"] if (d["a"], d["b"]) == ("initial_plain", "full_plain"))["signflip"]["pooled"]
    assert (sf["k"], Fraction(sf["p_greater"]).limit_denominator(4096), sf["p_two_sided"]) == (10, Fraction(1, 1024), 2 / 1024)
    assert se["conditions"]["initial_plain"]["invalid"] == {"accepted": 10, "n": 10}
    assert {d["metric"] for d in se["comparisons"]} == {"fa"}  # every source-evidence label is invalid
    md = (run / "analysis.md").read_text()
    assert "> **Natural PR-review arm** (protocol §15.6, §19.6, §20.3): the run grades 10 accepted tasks of its own" in md
    # One run over both samples is checked against the accepted families of both (§20.2 checks each run by its samples).
    assert a["natural"]["index"]["run_samples"] == ["first", "extension"] and a["natural"]["index"]["matches"] is True
    assert "### Paired comparisons under the source-evidence labels: exact sign-flip tests over task families" in md
    assert "## Appendix: cluster-bootstrap intervals" in md and "Secondary condition (B3):" in md


def test_b3_is_secondary_and_stays_out_of_the_primary_null_tally(ten):
    run, a = ten.run, ten.a
    assert SECONDARY_CONDITIONS == ("diff_derived",)
    assert a["meta"]["secondary_conditions"]["conditions"] == ["diff_derived"]
    assert "diff_derived" not in a["conditions"] and "diff_derived" not in a["per_family"]
    assert not [d for d in a["comparisons"] if "diff_derived" in (d["a"], d["b"])]
    sec = a["secondary"]
    assert list(sec["conditions"]) == list(sec["per_family"]) == ["diff_derived"]
    assert [(d["a"], d["b"], d["metric"]) for d in sec["comparisons"]] == [
        ("diff_derived", "full_audited", "fa"), ("diff_derived", "full_audited", "fr"),
        ("diff_derived", "full_plain", "fa"), ("diff_derived", "full_plain", "fr")]
    assert all("diff_derived" in (d["a"], d["b"]) for d in a["oracle_gated"]["secondary_comparisons"])
    assert not [d for d in a["oracle_gated"]["comparisons"] if "diff_derived" in (d["a"], d["b"])]
    assert not [d for d in a["source_evidence"]["comparisons"] if "diff_derived" in (d["a"], d["b"])]
    assert a["source_evidence"]["secondary_comparisons"]
    md = (run / "analysis.md").read_text()
    primary = md[md.index("## Paired comparisons: exact sign-flip"):md.index("## Secondary condition: B3")]
    tested = [d for d in a["comparisons"] if d["signflip"]["pooled"]["k"]]
    assert f"of {len(tested)} tested comparisons" in primary and "diff_derived" not in primary
    secondary = md[md.index("## Secondary condition: B3"):md.index("## Pooled false acceptance")]
    assert "### Secondary paired comparisons (B3)" in secondary and "**Null results.**" in secondary
    assert "| diff_derived |" not in md[md.index("## Pooled false acceptance"):md.index("## Source-evidence labels")]


# --------------------------------------------------------------------------- first prompt, source evidence, labeler


def test_the_first_prompt_is_the_issue_even_with_commit_anchored_requirements(tmp_path):
    run, tasks = build_world(tmp_path / "repo", 1, commit_requirement=True)
    nt = tasks[0]
    commit, issue = nt.event("first"), nt.event("issue")
    assert commit < issue  # the smallest introduced_at would name the commit event
    assert natural_first_prompt(nt.task_dir, tmp_path / "repo") == issue
    a = analyze(run, nt.tasks_root, allow_proposed=True, n_boot=50)
    rows = {r["candidate"]: r["negative_type"] for r in a["per_task"][nt.task_id]["initial_plain"]}
    assert rows[nt.candidate_id("eval-nm-3")] == "initial_violating"  # violates R-issue, introduced at the first prompt
    assert rows[nt.candidate_id("eval-nm-1")] == rows[nt.candidate_id("eval-nm-2")] == "correction_violating"
    assert "first_prompt_fallback" not in a["meta"]


def test_without_an_issue_requirement_the_reply_is_not_the_first_prompt(tmp_path):
    run, tasks = build_world(tmp_path / "repo", 1, no_issue_requirement=True)
    nt = tasks[0]
    assert nt.event("reply") < nt.event("comment")  # the smallest introduced_at would name the reply
    a = analyze(run, nt.tasks_root, allow_proposed=True, n_boot=50)
    rows = {r["candidate"]: r["negative_type"] for r in a["per_task"][nt.task_id]["full_plain"]}
    assert rows[nt.candidate_id("eval-nm-2")] == "correction_violating"  # violates R-reply, a later turn


def test_a_natural_task_without_a_session_falls_back_and_says_so(tmp_path):
    run, tasks = build_world(tmp_path / "repo", 1, commit_requirement=True)
    nt = tasks[0]
    (nt.task_dir / "session.json").unlink()
    a = analyze(run, nt.tasks_root, allow_proposed=True, n_boot=50)
    assert a["meta"]["first_prompt_fallback"]["tasks"] == [nt.task_id]
    assert a["natural"]["families"][nt.task_id]["session_readable"] is False
    assert a["natural"]["families"][nt.task_id]["correction_requirements"] == []
    assert "> **First prompt not read from the session** for NP-90" in (run / "analysis.md").read_text()


def test_the_source_evidence_block(three):
    run, a = three.run, three.a
    se = a["source_evidence"]
    assert se["banner"].startswith("source evidence, not a human label")
    assert "conditions" not in se and "comparisons" not in se and se["case_study"].startswith("per-family tables only")
    assert se["per_family"]["initial_plain"] == {f: {"invalid": {"accepted": 1, "n": 1}, "valid": {"rejected": 0, "n": 0}}
                                                 for f in ("NP-90", "NP-91", "NP-92")}
    assert se["per_family"]["full_plain"]["NP-90"]["invalid"] == {"accepted": 0, "n": 1}
    assert list(se["secondary_per_family"]) == ["diff_derived"]
    pre = se["pre_review"]
    assert list(pre) == ["NP-90/NP-90-pre-review", "NP-91/NP-91-pre-review", "NP-92/NP-92-pre-review"]
    # Whether the reference contract observes the correction (D64, decision 14): here it has two correction requirements.
    assert pre["NP-90/NP-90-pre-review"] == {
        "task_id": "NP-90", "family_id": "NP-90", "origin": "natural_pre_review", "source_evidence": "invalid",
        "source_labeler": "source-evidence:aidev-s9", "correction_requirements": ["R-corr", "R-reply"],
        "reference_observes_correction": True, "d19": "invalid",
        "independent_label": "ambiguous", "independent_label_left_out": False, "independent_label_outcome": "pass",
        "reference_checks_outcome": "task_failure",
        # each condition's outcome on it (so that a rejection that is no task failure can be named)
        "outcomes": {"diff_derived": "task_failure", "full_audited": "task_failure", "full_plain": "task_failure",
                     "initial_plain": "pass", "repo_tests": "pass"}}
    assert pre["NP-91/NP-91-pre-review"]["d19"] == "ambiguous" and pre["NP-91/NP-91-pre-review"]["reference_checks_outcome"] == "pass"
    assert pre["NP-92/NP-92-pre-review"]["independent_label"] is None and pre["NP-92/NP-92-pre-review"]["independent_label_left_out"]
    md = (run / "analysis.md").read_text()
    assert "> **Source evidence, not a human label: the reviewer's request" in md
    assert "| initial_plain | accepted | accepted | accepted |" in md and "| full_plain | rejected | rejected | rejected |" in md
    assert "| NP-90 | NP-90-pre-review | invalid | invalid | ambiguous (pass) | task_failure | R-corr, R-reply |" in md


def test_the_independent_labeler_on_natural_tasks(three):
    run, a = three.run, three.a
    assert independent_label("pass", "natural_pre_review") == "ambiguous" and independent_label("pass") == "valid"
    assert independent_label("task_failure", "natural_pre_review") == "invalid"
    x = a["independent_labeling"]
    assert x["tasks"] == ["NP-90", "NP-91"]  # NP-92's labeler is not usable
    assert x["left_out"] == {"NP-92": {"why": "verifiers/independent_label/status.json records the status 'unusable', not "
                                              "'usable' (protocol §15.5)",
                                       "outcomes": {"noop": {"task_failure": 1}, "reference": {"pass": 1}}}}
    assert x["candidates"]["NP-90/NP-90-pre-review"] == {"label": "ambiguous", "outcome": "pass", "d19": "invalid",
                                                         "origin": "natural_pre_review"}
    assert x["candidates"]["NP-92/NP-92-eval-alt-1"]["label"] is None  # left out: not graded
    assert "labels" not in x and x["labels_per_family"]["NP-92"] == {"valid": 0, "invalid": 0, "ambiguous": 0, "not_graded": 6}
    assert x["labels_per_family"]["NP-90"] == {"valid": 2, "invalid": 3, "ambiguous": 1, "not_graded": 0}
    assert "conditions" not in x and "by_stratum" not in x
    assert x["per_family"]["initial_plain"]["independent_label"]["NP-92"] == {"fa_num": 0, "fa_den": 0, "fr_num": 0, "fr_den": 0}
    assert x["per_family"]["initial_plain"]["primary"]["NP-92"]["fa_den"] == 4  # D19 still labels NP-92's pool
    g = x["agreement"]["per_family"]["NP-90"]["natural"]
    assert g["existed_before_labeler"]["n_units"] == 1 and "existed since S10" in g["existed_before_labeler"]["why"]
    assert g["generated_after_labeler"]["n_units"] == 5 and g["generated_after_labeler"]["agree"] == 5
    md = (run / "analysis.md").read_text()
    assert "* NP-92: verifiers/independent_label/status.json records the status 'unusable'" in md
    assert "* Pre-review states, which existed before the labeler was written: 1 unit(s)" in md


def test_the_labeler_rules_also_hold_outside_case_study_mode(ten):
    run, a = ten.run, ten.a
    x = a["independent_labeling"]
    assert "NP-92" in x["left_out"] and "NP-92" not in x["tasks"] and x["labels"]["ambiguous"] == 1
    g = x["agreement"]["by_stratum"]["task"]
    assert g["exploratory"] is False and g["natural"]["existed_before_labeler"]["n_units"] == 10
    after = g["natural"]["generated_after_labeler"]
    assert after["n_units"] == 50 and after["n_decided_by_both"] == 45  # NP-92's pool has no second label: "none"
    assert after["crosstab"]["valid"]["none"] == 2 and after["crosstab"]["invalid"]["none"] == 3
    md = (run / "analysis.md").read_text()
    assert "Left out of the second labeling (1; their labeler is not usable" in md


# --------------------------------------------------------------------------- flags, funnel, reliability, cost


def test_per_family_flags(three):
    a = three.a
    fams = a["natural"]["families"]
    assert list(fams) == ["NP-90", "NP-91", "NP-92"]
    assert fams["NP-90"]["b1"] == {"available": False, "n_checks": 0, "graded": True}
    assert fams["NP-91"]["b1"]["available"] is True
    eq = {t: f["b1_equals_regression_norm"] for t, f in fams.items()}
    assert eq["NP-91"]["equal"] is True and eq["NP-91"]["identical_files"] == eq["NP-91"]["b1_files"] == 1
    assert eq["NP-90"]["equal"] is False and eq["NP-90"]["identical_files"] == 0
    assert eq["NP-90"]["b1_overlay_manifest_sha256"] == eq["NP-91"]["norm_overlay_manifest_sha256"]
    assert {f["sample"] for f in fams.values()} == {"first"} and all(f["s11"] for f in fams.values())
    # The labeler's spec is not frozen in the fixture, so it records no frozen_at (the pool's order is then not shown).
    assert fams["NP-92"]["labeler"] == {"status": "unusable", "round": 2, "usable": False, "frozen_at": None}
    # The correction requirements are the scored active ones introduced at a correction event (D64, decision 14); an
    # unscored one there would be listed apart, and here there is none.
    assert fams["NP-90"]["correction_requirements"] == ["R-corr", "R-reply"] and fams["NP-90"]["unscored_at_correction_events"] == []
    assert fams["NP-90"]["reference_observes_correction"] is True and "correction_note" not in fams["NP-90"]
    assert fams["NP-90"]["near_misses_on_correction"] == {"near_misses": 3,
                                                         "on_correction": ["NP-90-eval-nm-1", "NP-90-eval-nm-2"]}
    assert fams["NP-90"]["b3"] == {"graded": True} and fams["NP-90"]["session_readable"] is True


def test_per_family_construction_facts(tmp_path):
    """D64, D70: each family's construction facts in ids, counts and codes: its contracts' counts (the reference
    contract's also at the correction), the checks of each registered verifier, the audits of C2 and C4 (passed,
    revisions, the codes of the last iteration's findings, never a message), whether B3 is available, and the reference
    checks' status record (its status and fix rounds, never its reasons); the records read are hashed in meta.inputs."""
    run, tasks = build_world(tmp_path / "repo", 3, construction=True)
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    nat = a["natural"]
    assert nat["construction_rule"] == analysis.CONSTRUCTION_RULE
    c0, c1, c2 = (nat["families"][t.task_id]["construction"] for t in tasks)
    assert c0["contracts"] == {"reference": {"requirements": 3, "active": 3, "scored_active": 3, "at_correction": 2},
                               "initial_only": {"requirements": 4, "active": 3, "scored_active": 2},
                               "full_session": {"requirements": 5, "active": 4, "scored_active": 3}}
    assert c1["contracts"]["initial_only"] == {"requirements": 5, "active": 4, "scored_active": 3}
    b1 = len(load(tasks[0].task_dir / "verifiers" / "repo_tests" / "spec.json", VerifierSpec).checks)
    assert c0["checks"] == {**CONSTRUCTION_CHECKS, "independent_label": 1, "repo_tests": b1}
    assert c1["checks"]["full_audited"] == CONSTRUCTION_CHECKS["full_audited"] + 1 and "diff_derived" not in c2["checks"]
    audit = {"verifier_id": "full_audited", "procedure": "audit:v1"}
    assert c0["audits"] == {"full_audited": {**audit, "passed": False, "revisions": 3, "last_finding_codes": ["reference_not_passing"]},
                            "initial_audited": {**audit, "verifier_id": "initial_audited", "passed": True, "revisions": 2,
                                                "last_finding_codes": []}}
    assert c1["audits"]["full_audited"]["last_finding_codes"] == ["false_acceptance_dev", "uncovered_requirement"]
    assert c2["audits"]["initial_audited"] == {**audit, "verifier_id": "initial_audited", "passed": False, "revisions": 1,
                                               "last_finding_codes": None}  # a record without history
    assert (c0["b3"], c1["b3"]) == ({"available": True, "checks": 3}, {"available": True, "checks": 4})
    assert c2["b3"] == {"available": False, "taken_out": True,
                        "why": "its per-test selection kept no test, so it was taken out (unavailable.json; protocol §15.6)"}
    assert nat["families"]["NP-92"]["b3"] == {"graded": False} and "NP-92" not in a["secondary"]["per_family"]["diff_derived"]
    assert c0["reference_checks"] == {"recorded": True, "status": "usable", "usable": True, "fix_rounds": 1}
    assert c1["reference_checks"] == {"recorded": True, "status": "unusable", "usable": False, "fix_rounds": 2}
    assert c2["reference_checks"] == {"recorded": False, "status": None, "usable": None, "fix_rounds": None,
                                      "why": "no readable verifiers/reference_check/status.json"}
    files = a["meta"]["inputs"]["files_sha256"]
    assert {"NP-90/verifiers/reference_check/status.json", "NP-92/verifiers/diff_derived/unavailable.json"} <= set(files)
    text = (run / "analysis.json").read_text() + (run / "analysis.md").read_text()
    assert SECRET_FINDING not in text and "test_never_copied" not in text
    # analysis.md shows the construction facts that its natural rule announces.
    md = (run / "analysis.md").read_text()
    assert "construction_rule" in nat["rule"] and "### Construction facts per family" in md
    assert (f"| NP-90 | 3, 3, 2 | 2, 3 | 3, 4, 5, 6, 2, {b1}, 3 | 4, 1 | 2 revision(s), passed | 3 revision(s), failed "
            "(reference_not_passing) | available | usable; fix rounds 1 |") in md
    assert (f"| NP-92 | 3, 3, 2 | 4, 5 | 5, 6, 7, 8, 4, {b1}, - | 6, 1 | 1 revision(s), failed (codes not recorded) | "
            "1 revision(s), passed | not available (its per-test selection kept no test, so it was taken out (unavailable.json; "
            "protocol §15.6)) | not recorded (no readable verifiers/reference_check/status.json) |") in md
    # A status other than usable or unusable is not copied, and a record is told from no record; fix rounds under another
    # key than fix_rounds (D64 fixes none) are not taken, and the analysis says so instead of dropping them silently.
    write_json({"status": "fine, " + SECRET_FINDING}, tasks[1].task_dir / "verifiers" / "reference_check" / "status.json")
    write_json({"status": "usable", "rounds": 2}, tasks[0].task_dir / "verifiers" / "reference_check" / "status.json")
    b = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    rec = "verifiers/reference_check/status.json"
    assert b["natural"]["families"]["NP-91"]["construction"]["reference_checks"] == {
        "recorded": True, "status": None, "usable": None, "fix_rounds": None,
        "why": f"{rec} records no status usable or unusable; {rec} records no fix rounds as an integer fix_rounds"}
    assert b["natural"]["families"]["NP-90"]["construction"]["reference_checks"] == {
        "recorded": True, "status": "usable", "usable": True, "fix_rounds": None,
        "why": f"{rec} records no fix rounds as an integer fix_rounds"}
    assert "test_never_copied" not in (run / "analysis.json").read_text()


def test_the_funnel_of_both_samples(three):
    run, a = three.run, three.a
    f = a["natural"]["funnel"]
    assert [s["stage"] for s in f["stages"]] == ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S8a"]  # S8' is a variant
    assert f["S9"]["first"]["qualifying"] == 31 and f["S9"]["first"]["families"] == 20
    assert f["S9"]["extension"]["judged"] == 400 and f["S9"]["extension"]["failed_by_reason"] == {"fetch_over_the_caps": 65}
    first = f["S10_S11"]["first"]
    assert first["outcomes"] == {"not built": 1, "passed": 3, "rejected": 2} and first["roles"] == {"family": 5, "reserve": 1}
    assert first["rejected_by_reason"] == {"base tests fail to collect": ["NP-80"], "no resolvable closure": ["NP-81"]}
    assert first["s11"] == ["NP-90", "NP-91", "NP-92"] and f["S11"] == {"accepted": 3, "by_sample": {"first": 3}}
    md = (run / "analysis.md").read_text()
    assert "| S8a | review_comment | 80 | 40 | 8 |" in md and "| S8' |" not in md
    assert "* S10, first, base tests fail to collect (1): NP-80" in md


def test_reliability_and_cost(three):
    a = three.a
    r = a["natural"]["reliability"]
    assert r["families"]["NP-90"]["image_id"]["match"] is True and r["families"]["NP-90"]["unresolved"] == 1
    # An unresolved pair is counted once, as unresolved, not also as an infrastructure outcome.
    assert r["run"] == {"pairs": 3 * 7 * 8, "unresolved": 1, "infrastructure": {}}
    assert r["families"]["NP-90"]["infrastructure"] == {}
    assert r["families"]["NP-91"]["sanity"]["reference"]["reference_check"] == {"pass": 1, "n": 1, "outcomes": {"pass": 1}}
    assert r["families"]["NP-90"]["reconstruction"]["status"] == "passed"
    c = a["natural"]["cost"]
    # Per family: the reference contract (5 turns), the labeler (10), and 4 of the 5 constructed candidates (10 each).
    assert c["families"]["NP-90"]["recorded"] == 6 and c["families"]["NP-90"]["artifacts"] == 7
    assert c["families"]["NP-90"]["unrecorded"] == ["candidate NP-90-eval-nm-3"]
    assert (c["families"]["NP-90"]["turns"], c["families"]["NP-90"]["tool_calls"]) == (55, 107)
    assert c["families"]["NP-90"]["by_generator"] == {"config-A": 5, "config-B": 1}
    assert c["families"]["NP-90"]["fetch_bytes"] == 1000 and c["families"]["NP-90"]["fetch_repository_shared_with"] == ["NP-91"]
    assert c["families"]["NP-92"]["fetch_bytes"] == 2000 and c["families"]["NP-90"]["grading_wall_s"] == 28.0
    assert c["totals"]["turns"] == 165 and c["per_accepted_task"]["turns"] == 55.0
    assert c["totals"]["fetch_bytes_of_the_run_repositories"] == 3000 and c["totals"]["fetch_bytes_all_s10"] == 3300
    assert c["unrecorded"] and all(isinstance(x, str) for x in c["unrecorded"])


def test_the_inputs_are_hashed_and_nothing_private_is_written(three):
    run, a = three.run, three.a
    files = a["meta"]["inputs"]["files_sha256"]
    for key in (NATURAL_INDEX, NATURAL_FUNNEL, *NATURAL_S9.values(), NATURAL_FETCH_LOG, "NP-90/s10.json", "NP-90/session.json",
                "NP-90/reconstruction_check.json", "NP-90/verifiers/independent_label/status.json",
                "NP-90/verifiers/repo_tests/overlay/", "NP-90/labels/base_tests_overlay/", "code/contract.py", "code/tasks.py"):
        assert key in files, key
    assert "code/stats.py" not in files  # case-study mode runs no sign-flip test
    assert not [k for k in files if "/tests/" in k or k.endswith(".py") and not k.startswith("code/")]  # no test file names
    text = (run / "analysis.json").read_text() + (run / "analysis.md").read_text()
    assert str(three.root) not in text and "/home/" not in text and "/tmp/" not in text
    for secret in (ISSUE_TEXT, COMMENT_TEXT, REPLY_TEXT, HUNK_TEXT, PR_TEXT, *AGENT_ONLY_MARKERS):
        assert secret[:24] not in text, secret[:24]


def test_the_run_families_are_checked_against_the_index(tmp_path):
    """§20.2: a run grades the accepted families of its sample, so its families are checked against the accepted families
    of the samples their rows name: NP-99 (first sample) is one the run leaves out, NP-98 (extension) is not the run's."""
    run, tasks = build_world(tmp_path / "repo", 2, extra_s11=("NP-98",), not_s11=("NP-91",),
                             extra_rows=(("NP-99", {"s11": True, "sample": "first", "repo_id": 991}),))
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    idx = a["natural"]["index"]
    assert (idx["s11"], idx["run_families"]) == (["NP-90", "NP-98", "NP-99"], ["NP-90", "NP-91"])
    assert (idx["run_samples"], idx["s11_of_run_samples"], idx["rule"]) == (["first"], ["NP-90", "NP-99"], INDEX_CHECK_RULE)
    assert (idx["run_families_not_s11"], idx["s11_not_in_run"], idx["matches"]) == (["NP-91"], ["NP-99"], False)
    md = (run / "analysis.md").read_text()
    # The index is read as the run's code revision holds it (the commit its acceptance gate read).
    rev = json.loads((run / "manifest.json").read_text())["code_revision"]
    assert idx["source"] == f"{NATURAL_INDEX} at the run's code revision {rev[:12]}"
    assert ("> **The run's families against the committed index** (data/manifests/natural_tasks_index.json at the run's "
            f"code revision {rev[:12]}): not accepted (S11) there: NP-91; accepted families of its sample(s) (first) that the "
            "run leaves out: NP-99. Each natural run grades the accepted families of its sample: natural-pr-v1 the first "
            "sample's, natural-pr-v2 the extension's (protocol §20.2).") in md
    # The size rule counts the run's own accepted tasks: NP-90 alone (NP-91 is not accepted; NP-98 and NP-99 are not graded).
    assert (a["meta"]["case_study"]["accepted_in_run"], a["meta"]["case_study"]["accepted_in_index"]) == (1, 3)
    html = build_report(run, tasks[0].tasks_root, tmp_path / "repo", tmp_path / "report.html").read_text()
    assert ("not accepted (S11) there: NP-91; accepted families of its sample(s) (first) that the run leaves out: NP-99. Each "
            "natural run grades the accepted families of its sample: natural-pr-v1 the first sample's, natural-pr-v2 the "
            "extension's (protocol §20.2).</div>") in html
    assert "grades every accepted family together" not in html + md


def test_each_run_is_reported_on_its_own(tmp_path):
    """§20.3: each run is reported on its own, so the size rule counts the run's own accepted tasks. Three families of the
    first sample, while the committed index counts 3 + 8 = 11 accepted tasks over both samples: case-study mode, and the
    extension's accepted families are not ones the run leaves out (§20.2)."""
    ext = tuple(f"NP-{60 + k}" for k in range(8))
    run, tasks = build_world(tmp_path / "repo", 3, extra_s11=ext)
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    cs, idx = a["meta"]["case_study"], a["natural"]["index"]
    assert (cs["applies"], cs["accepted_in_run"], cs["accepted_in_index"]) == (True, 3, 11)
    assert cs["why"].startswith("the run grades 3 accepted task(s) of its own") and cs["rule"] == analysis.CASE_STUDY_RULE
    assert a["conditions"] == {} and a["comparisons"] == [] and "bootstrap" not in a["meta"]
    assert not POOLED_KEYS & _keys(a), POOLED_KEYS & _keys(a)
    assert (idx["accepted"], idx["accepted_by_sample"]) == (11, {"first": 3, "extension": 8})
    assert (idx["run_samples"], idx["s11_not_in_run"], idx["matches"]) == (["first"], [], True)
    md = (run / "analysis.md").read_text()
    assert ("The run's 3 families are the 3 accepted families (S11) of its sample(s), first, in the committed index "
            f"({idx['source']}), which counts 11 over both samples (first 3, extension 8); each run grades the accepted "
            "families of its sample (protocol §20.2).") in md
    assert "The run's families against the committed index" not in md


def test_an_unreadable_committed_index_means_case_study_mode(tmp_path):
    run, tasks = build_world(tmp_path / "repo", 1)
    shutil.rmtree(tmp_path / "repo" / ".git")  # git can show nothing: the size rule cannot be shown to be met
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50, repo_root=tmp_path / "repo")
    assert a["meta"]["case_study"]["applies"] is True and "cannot be read" in a["meta"]["case_study"]["why"]
    assert a["natural"]["index"]["readable"] is False and a["conditions"] == {}


# --------------------------------------------------------------------------- rules, roots and the duplicate representative


def test_pilot_rules_are_refused_for_a_new_natural_run_and_kept_for_a_test_run(tmp_path):
    run, tasks = build_world(tmp_path / "new" / "repo", 1)
    with pytest.raises(NaturalRunError, match="the pilot rules were asked for a run with natural PR-review tasks"):
        analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50, rules="pilot")
    assert not (run / "analysis.json").exists()
    run, tasks = build_world(tmp_path / "stub" / "repo", 1, harness="stub")  # only a test run records no harness version
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    assert a["meta"]["case_study"]["applies"] is False and "pilot rules" in a["meta"]["case_study"]["why"]
    assert "diff_derived" in a["conditions"] and "secondary" not in a and a["natural"]["families"]


def test_the_repository_root_is_found_from_the_manifest(tmp_path):
    root = tmp_path / "repo"
    tasks_root = root / "data" / "natural" / "tasks"
    assert repository_root(tasks_root, {"tasks": [{"task_id": "NP-90", "task_dir": "data/natural/tasks/NP-90"}]}) == root.resolve()
    assert repository_root(tasks_root, {"tasks": [{"task_id": "NP-90"}]}) == root.resolve()  # data/natural/tasks: three up
    assert repository_root(root / "tasks", {"tasks": [{"task_id": "CS-01"}]}) == root.resolve()
    elsewhere = tmp_path / "copy" / "tasks"  # a manifest's task_dir that does not name the tasks root is not trusted
    assert repository_root(elsewhere, {"tasks": [{"task_id": "NP-90", "task_dir": "data/natural/tasks/NP-90"}]}) == \
        elsewhere.resolve().parent


def test_the_pre_review_state_represents_its_duplicates(tmp_path):
    run, tasks = build_world(tmp_path / "repo", 1, duplicate_of_pre=True)
    nt = tasks[0]
    a = analyze(run, nt.tasks_root, allow_proposed=True, n_boot=50)
    (g,) = a["distinct_patches"]["groups"]
    assert g["representative"] == nt.candidate_id("pre-review") and g["members"][1] == nt.candidate_id("eval-nm-1")
    # Post hoc: the near miss duplicates the pre-review state, not the other way round ('eval-nm-1' sorts first by id).
    assert a["duplicates"] == {nt.candidate_id("eval-nm-1"): {"task_id": nt.task_id,
                                                              "same_patch_as_heldout": nt.candidate_id("pre-review")}}


def test_a_run_pooled_with_another_population_gets_no_natural_sections(tmp_path, monkeypatch):
    run, tasks = build_world(tmp_path / "repo", 2)
    m = json.loads((run / "manifest.json").read_text())
    nt = tasks[1]
    task = load(nt.task_dir / "task.json", TaskManifest)
    dump(task.model_copy(update={"population": Population.natural_chat}), nt.task_dir / "task.json")
    write_json(m, run / "manifest.json")
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50, pool_populations=True)
    assert "natural" not in a and "case_study" not in a["meta"] and "diff_derived" in a["conditions"]
    assert set(a["by_population"]) == {"natural:chat", "natural:pr-review"}


# --------------------------------------------------------------------------- the review's findings (decision log D64 to D66)


def _at(seconds: int) -> str:
    return f"2026-11-21T10:{seconds // 60:02d}:{seconds % 60:02d}+00:00"


def test_s10_cost_counts_time_and_fetches_of_every_processed_family(tmp_path):
    """§15.6, cost and time per accepted task: S10's time and its fetches are counted on one basis, the S10 work of every
    family S10 processed (both samples, rejected ones included), per accepted task; the run's families' own S10 time is
    given beside it, and what is not counted is listed."""
    root = tmp_path / "repo"
    # NP-83: a family of the extension that S10 processed after the index was committed (its row says not built).
    run, tasks = build_world(root, 3, extra_rows=(("NP-83", {"s11": False, "outcome": "not built", "sample": "extension",
                                                            "repo_id": 779}),))
    tr = tasks[0].tasks_root
    for nt, secs in zip(tasks, (10, 20, 30)):
        rec = json.loads((nt.task_dir / "s10.json").read_text())
        write_json({**rec, "built_at": _at(0), "passed_at": _at(secs)}, nt.task_dir / "s10.json")
    for tid, rec in (("NP-80", {"outcome": "rejected", "built_at": _at(0), "rejected_at": _at(100)}),  # rejected after its build
                     ("NP-83", {"outcome": "rejected", "built_at": _at(0), "rejected_at": _at(5)}),  # the index records no outcome
                     ("NP-84", {"outcome": "built", "built_at": _at(0)})):  # no index row, and stopped before its end
        write_json({"schema": "tracecontract/natural-s10/v1", "task_id": tid, "stage": "S10", **rec}, tr / tid / "s10.json")
    write_json({"task_id": "NP-81", "stage": "S10", "reason": "synthetic", "at": _at(5)}, tr / "NP-81" / "rejection.json")
    (root / NATURAL_FETCH_LOG).write_text("".join(json.dumps(e) + "\n" for e in (
        {"stage": "S10", "repo_id": 900, "delta": 1000, "seconds": 1.5}, {"stage": "S10", "repo_id": 901, "delta": 2000, "seconds": 2.5},
        {"stage": "S9", "repo_id": 900, "delta": 5, "seconds": 9.0}, {"stage": "S10", "repo_id": 777, "delta": 300, "seconds": 0.5},
        {"stage": "S10", "repo_id": 779, "delta": 600})), encoding="utf-8")
    a = analyze(run, tr, allow_proposed=True, n_boot=50)
    c = a["natural"]["cost"]
    every = c["s10_every_family"]
    assert every["processed"] == ["NP-80", "NP-81", "NP-83", "NP-84", "NP-90", "NP-91", "NP-92"] and every["n_processed"] == 7
    assert every["families"] == {"NP-80": 100.0, "NP-83": 5.0, "NP-90": 10.0, "NP-91": 20.0, "NP-92": 30.0}
    assert every["not_built"] == ["NP-82"] and every["processed_not_in_index"] == ["NP-83", "NP-84"]
    assert sorted(every["not_recorded"]) == ["NP-81", "NP-84"]
    tot, per = c["totals"], c["per_accepted_task"]
    # Time and fetches on one basis, every processed family, per accepted task (3); the S9 fetch is not S10's.
    assert (tot["s10_seconds_every_family"], tot["fetch_bytes_all_s10"], tot["fetch_seconds_all_s10"]) == (165.0, 3900, 4.5)
    assert (per["s10_seconds_every_family"], per["fetch_bytes_all_s10"], per["fetch_seconds_all_s10"]) == (55.0, 1300.0, 1.5)
    # The run's families alone, beside it; no S10 figure is left without its basis in its name.
    assert (tot["s10_seconds_run_families"], per["s10_seconds_run_families"]) == (60.0, 20.0)
    assert (tot["fetch_bytes_of_the_run_repositories"], per["fetch_bytes_of_the_run_repositories"]) == (3000, 1000.0)
    assert "s10_seconds" not in tot and "s10_seconds" not in per and c["families"]["NP-91"]["s10_seconds"] == 20.0
    unrecorded = c["unrecorded"]
    assert ("the S10 time of NP-81, left out of the S10 time of every processed family: rejected during the build: its task "
            "directory keeps only rejection.json, which records the rejection's time and no start") in unrecorded
    assert ("the S10 time of NP-84, left out of the S10 time of every processed family: its s10.json records no end "
            "(outcome 'built')") in unrecorded
    assert "the time of 1 S10 fetch(es) of the log, which record no seconds (their bytes are counted)" in unrecorded
    assert {"NP-80/s10.json", "NP-81/rejection.json", "NP-83/s10.json", "NP-84/s10.json"} <= set(a["meta"]["inputs"]["files_sha256"])
    md = (run / "analysis.md").read_text()
    assert "| Every family S10 processed | 7 processed; a recorded time for 5 of them | 165.0 | 4.5 | 3900 | 55.0 | 1.5 | 1300.0 |" in md
    assert "| The run's families alone (their repositories' fetches) | 3 | 60.0 | - | 3000 | 20.0 | - | 1000.0 |" in md
    assert "Counted, with an S10 record under the tasks root but no S10 outcome in the committed index: NP-83, NP-84." in md
    assert "Not built by S10, so with no S10 work: NP-82." in md and "| Per accepted task | - | 55.0 |" in md


def test_the_report_of_a_case_study_run_shows_per_family_tables_only(three, tmp_path):
    """report.py on a case-study analysis (§19.6), which has no pooled key: the banner and per-family tables, nothing
    pooled; it builds without a refusal."""
    html = build_report(three.run, three.tasks[0].tasks_root, three.root, tmp_path / "report.html").read_text()
    summary = html[:html.index("<h2>Task NP-90</h2>")]
    for text in ("<b>Exploratory case studies</b> (protocol §19.6, §20.3): the run grades 3 accepted task(s) of its own",
                 "Primary display: false acceptance and false rejection per task family", "Secondary condition: B3 (diff-derived)",
                 "Sanity checks per family", "Source-evidence labels (reported apart from D19)",
                 "Independent labeler: a second labeling, per task family", "Left out of the second labeling (1;",
                 "Oracle-gated view per family (secondary)", "Distinct graded patches",
                 "Natural families: sample, B1 and correction requirements", "Cost and time per accepted task"):
        assert text in summary, text
    # C1 per family (NP-90, NP-91, NP-92), with no column that pools them.
    assert ("<tr><td>C1 initial-only, plain <span class='muted'>(initial_plain)</span></td><td>3/4</td><td>0/2</td><td>2/3</td>"
            "<td>0/2</td><td>3/4</td><td>0/2</td></tr>") in summary
    assert "<td>NP-90</td><td>NP-90-pre-review</td><td>invalid</td><td>invalid</td><td>ambiguous (pass)</td>" in summary
    for absent in ("Summary by verifier condition", "All FA", "95%", "p (A &gt; B)", "Null results", "Appendix: cluster-bootstrap",
                   "Reporting rules of a new run", "bootstrap]"):
        assert absent not in html, absent


def test_the_report_of_a_natural_run_of_ten_families_shows_b3_apart(ten, tmp_path):
    """With 10 or more accepted tasks the report follows the reporting rules of a new run, and B3, which the analysis keeps
    under ``secondary``, is shown apart from the primary conditions instead of being dropped."""
    html = build_report(ten.run, ten.tasks[0].tasks_root, ten.root, tmp_path / "report.html").read_text()
    for text in ("<b>Natural PR-review arm</b> (protocol §15.6, §19.6, §20.3)", "<b>Reporting rules of a new run</b>",
                 "Summary by verifier condition", "Secondary condition: B3 (diff-derived)", "Secondary paired comparisons (B3)",
                 "Oracle-gated secondary paired comparisons (B3)", "Paired comparisons under the source-evidence labels",
                 "Exploratory view clustered by repository (not pre-specified)", "Secondary condition (B3):",
                 "Appendix: cluster-bootstrap intervals", "Left out of the second labeling (1;"):
        assert text in html, text
    primary = html[html.index("Primary display"):html.index("<h3>Sanity checks</h3>")]
    assert "B3 diff-derived" not in primary and "diff_derived" not in primary  # B3 is in no primary table or comparison
    assert "<tr><td>B3 diff-derived <span class='muted'>(diff_derived)</span> <span class='muted'>(secondary)</span></td>" in html


def test_the_cli_refuses_the_pilot_rules_for_a_natural_run_and_writes_nothing(tmp_path, capsys):
    run, tasks = build_world(tmp_path / "repo", 1)
    with pytest.raises(SystemExit) as exc:  # the refusal's message, not a traceback
        cli.main(["analyze", str(run), "--tasks-root", str(tasks[0].tasks_root), "--allow-proposed-labels",
                  "--reporting-rules", "pilot"])
    assert str(exc.value.code).startswith("analyze refused: the pilot rules were asked for a run with natural PR-review tasks "
                                          "(NP-90)")
    assert not (run / "analysis.json").exists() and not (run / "analysis.md").exists()


def test_the_records_are_read_at_the_run_s_code_revision(tmp_path):
    """The case-study decision, the index check and the funnel read the natural index and the screening records as the
    run's code revision holds them, so a later commit of the index changes nothing; a run whose manifest names no commit
    of the repository is read at HEAD, and says so."""
    root = tmp_path / "repo"
    run, tasks = build_world(root, 3)
    rev = json.loads((run / "manifest.json").read_text())["code_revision"]
    at_run = git(root, "show", f"{rev}:{NATURAL_INDEX}").stdout
    for k in range(7):  # a later commit: 7 more accepted families of the run's sample, and NP-92 no longer accepted
        write_index_row(root, f"NP-{60 + k}", commit=False, sample="first", repo_id=960 + k)
    write_index_row(root, "NP-92", s11=False, commit=False, sample="first", repo_id=901)
    git(root, "add", "--", NATURAL_INDEX)
    git(root, "commit", "-q", "--no-verify", "-m", "later index (synthetic fixture)")
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    assert a["natural"]["records"]["basis"] == "run" and a["natural"]["records"]["revision"] == rev
    assert a["meta"]["case_study"]["applies"] is True
    assert (a["meta"]["case_study"]["accepted_in_run"], a["meta"]["case_study"]["accepted_in_index"]) == (3, 3)
    assert a["natural"]["index"]["s11"] == ["NP-90", "NP-91", "NP-92"] and a["natural"]["index"]["matches"] is True
    assert a["natural"]["funnel"]["S11"]["accepted"] == 3
    assert a["meta"]["inputs"]["files_sha256"][NATURAL_INDEX] == hashlib.sha256(at_run).hexdigest()
    assert "Records read at HEAD" not in (run / "analysis.md").read_text()
    # The +dirty mark of evaluate's code revision is dropped: the run's gate read the committed index.
    m = json.loads((run / "manifest.json").read_text())
    write_json({**m, "code_revision": rev + "+dirty"}, run / "manifest.json")
    assert analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)["natural"]["records"]["revision"] == rev
    # A code revision that is no commit of the repository: read at HEAD, which now counts 9 over the samples and 2 of
    # the run's, and said so.
    write_json({**m, "code_revision": "unknown"}, run / "manifest.json")
    b = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    assert b["natural"]["records"]["basis"] == "head" and b["meta"]["case_study"]["applies"] is True
    assert (b["meta"]["case_study"]["accepted_in_run"], b["meta"]["case_study"]["accepted_in_index"]) == (2, 9)
    assert b["natural"]["index"]["s11_not_in_run"] == [f"NP-{60 + k}" for k in range(7)]
    assert b["natural"]["index"]["run_families_not_s11"] == ["NP-92"]
    assert ("> **Records read at HEAD**: the run's code revision 'unknown' is not a commit of this repository, so the natural "
            "index and the screening records are read as the HEAD commit holds them") in (run / "analysis.md").read_text()


def test_the_source_evidence_block_leaves_out_only_labelers_the_run_graded(tmp_path):
    """A pre-review state is marked as left out of the second labeling only when the run graded its labeler; NP-92's
    status.json says unusable, but this run does not grade the labeler."""
    run, tasks = build_world(tmp_path / "repo", 3, labeler_graded=False)
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    assert "independent_labeling" not in a
    pre = a["source_evidence"]["pre_review"]["NP-92/NP-92-pre-review"]
    assert (pre["independent_label"], pre["independent_label_left_out"], pre["independent_label_outcome"]) == (None, False, None)
    md = (run / "analysis.md").read_text()
    assert "| NP-92 | NP-92-pre-review | invalid | invalid | not graded | task_failure | R-corr, R-reply |" in md
    assert "left out (labeler not usable)" not in md


def test_an_unscored_requirement_at_a_correction_event_is_not_a_correction_requirement(tmp_path):
    """D64, decision 14 (as the pre-flight reads it): a correction requirement is scored and active."""
    run, tasks = build_world(tmp_path / "repo", 1, unscored_at_comment=True)
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    fam = a["natural"]["families"]["NP-90"]
    assert fam["correction_requirements"] == ["R-corr", "R-reply"] and fam["unscored_at_correction_events"] == ["R-unscored"]
    assert a["source_evidence"]["pre_review"]["NP-90/NP-90-pre-review"]["correction_requirements"] == ["R-corr", "R-reply"]
    assert "R-corr, R-reply (unscored at a correction event, not counted: R-unscored)" in (run / "analysis.md").read_text()


def test_a_family_whose_reference_contract_does_not_observe_the_correction(tmp_path):
    """D64, decision 14: the tables say that the reference contract does not observe the correction and that no near miss
    targets it."""
    run, tasks = build_world(tmp_path / "repo", 2, no_correction=(1,))
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    fam = a["natural"]["families"]["NP-91"]
    assert (fam["correction_requirements"], fam["reference_observes_correction"]) == ([], False)
    assert fam["correction_note"] == NO_CORRECTION_REQUIREMENT
    assert fam["near_misses_on_correction"] == {"near_misses": 3, "on_correction": []}
    assert a["natural"]["families"]["NP-90"]["reference_observes_correction"] is True
    assert a["source_evidence"]["pre_review"]["NP-91/NP-91-pre-review"]["reference_observes_correction"] is False
    md = (run / "analysis.md").read_text()
    none = "none: the reference contract does not observe the correction, and no near miss targets it"
    assert f"| NP-91 | NP-91-pre-review | invalid | ambiguous | invalid (task_failure) | pass | {none} |" in md
    assert f"* NP-91: {NO_CORRECTION_REQUIREMENT}." in md


def test_ten_families_get_one_exploratory_view_clustered_by_repository(ten, three):
    """D64, decision 10: with 10 or more accepted tasks one exploratory view clusters the families by repository (the
    fixture's families share a repository two by two); none in case-study mode."""
    v = ten.a["repository_clustered"]
    names = [f"NP-{90 + 2 * k}+NP-{91 + 2 * k}" for k in range(5)]
    assert v["exploratory"] is True and list(v["clusters"]) == names == v["shared"] and "no_repository_id" not in v
    assert v["clusters"]["NP-90+NP-91"] == ["NP-90", "NP-91"] and list(v["per_cluster"]) == list(ten.a["per_family"])
    c1c3 = next(d for d in v["comparisons"] if (d["a"], d["b"], d["metric"]) == ("initial_plain", "full_plain", "fa"))
    assert c1c3["signflip"]["pooled"]["k"] == 5 and not [d for d in v["comparisons"] if "diff_derived" in (d["a"], d["b"])]
    sf = next(d for d in v["source_evidence_comparisons"] if (d["a"], d["b"]) == ("initial_plain", "full_plain"))["signflip"]
    assert (sf["pooled"]["k"], Fraction(sf["pooled"]["p_greater"]).limit_denominator(4096)) == (5, Fraction(1, 32))
    md = ten.md
    assert "## Exploratory view clustered by repository (not pre-specified)" in md
    assert "### Paired comparisons over repositories (D19 labels): exact sign-flip tests" in md
    assert "repository_clustered" not in three.a and "clustered by repository" not in three.md


def test_rejection_reasons_under_a_step_prefix_keep_their_failure(tmp_path):
    """S10 writes "base tests: <failure>" for distinct failures, beside "base tests fail to collect": each is its own
    reason category in the funnel."""
    cat = analysis._reason_category
    assert cat("base tests: the base-test subset is empty (synthetic)") == "base tests: the base-test subset is empty"
    assert cat("base tests: the grader did not complete: synthetic") == "base tests: the grader did not complete"
    assert cat("base tests fail to collect: synthetic") == "base tests fail to collect"
    assert (cat("no resolvable closure: synthetic"), cat(None), cat(" ")) == ("no resolvable closure", "no reason recorded",
                                                                             "no reason recorded")
    run, tasks = build_world(tmp_path / "repo", 1, extra_rows=(("NP-83", {
        "s11": False, "outcome": "rejected", "sample": "first", "repo_id": 779,
        "s10": {"outcome": "rejected", "reason": "base tests: the base-test subset is empty (synthetic)", "stage": "S10"}}),))
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    assert a["natural"]["funnel"]["S10_S11"]["first"]["rejected_by_reason"] == {
        "base tests fail to collect": ["NP-80"], "base tests: the base-test subset is empty": ["NP-83"],
        "no resolvable closure": ["NP-81"]}
    assert "* S10, first, base tests: the base-test subset is empty (1): NP-83" in (run / "analysis.md").read_text()


def test_the_oracle_gated_b3_comparisons_are_rendered_apart(ten):
    md = ten.md
    og = md[md.index("## Oracle-gated view (secondary)"):md.index("## Distinct graded patches")]
    primary = og[og.index("### Oracle-gated paired comparisons"):og.index("### Oracle-gated secondary paired comparisons (B3)")]
    secondary = og[og.index("### Oracle-gated secondary paired comparisons (B3)"):]
    assert ten.a["oracle_gated"]["secondary_comparisons"] and "| diff_derived |" not in primary
    assert "| diff_derived | full_audited | FA |" in secondary and "secondary, outside the primary null tally" in secondary


def test_the_pool_is_checked_to_be_generated_after_the_labeler_was_frozen(tmp_path):
    """The agreement on the held-out pool is said to be on candidates generated after the labeler was frozen only as far
    as their generation records show it: each start against the labeler's frozen_at."""
    run, tasks = build_world(tmp_path / "repo", 2, labeler_frozen_at={0: "2026-11-21T09:00:00+00:00",
                                                                       1: "2026-11-21T11:00:00+00:00"})  # the pool starts at 10:00
    a = analyze(run, tasks[0].tasks_root, allow_proposed=True, n_boot=50)
    assert a["natural"]["families"]["NP-90"]["labeler"]["frozen_at"] == "2026-11-21T09:00:00+00:00"
    per = a["independent_labeling"]["agreement"]["per_family"]
    assert per["NP-90"]["natural"]["generated_after_labeler"]["order"] == {
        "rule": ORDER_RULE, "candidates": 5, "after": 4, "not_after": [],
        "not_shown": {"NP-90/NP-90-eval-nm-3": "no generation record"}}
    order = per["NP-91"]["natural"]["generated_after_labeler"]["order"]
    assert (order["after"], order["not_after"]) == (0, [f"NP-91/NP-91-{k}" for k in ("eval-alt-1", "eval-alt-2", "eval-nm-1",
                                                                                      "eval-nm-2")])
    md = (run / "analysis.md").read_text()
    assert ("Generated after the labeler was frozen: 4 of 5 candidate(s); not shown for NP-90/NP-90-eval-nm-3 (no generation "
            "record).") in md
    assert "Generated after the labeler was frozen: 0 of 5 candidate(s); not after it: NP-91/NP-91-eval-alt-1, " in md


# --------------------------------------------------------------------------- D19's reason for each ambiguous candidate


def propose_labels_module():
    """scripts/propose_labels.py as a module: it loads without Docker, and its grader is not called here."""
    spec = importlib.util.spec_from_file_location("propose_labels_d19_reasons", REPO / "scripts" / "propose_labels.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_each_reason_d19_gives_an_ambiguous_label_is_a_category():
    """The reasons that scripts/propose_labels.py's d19 gives an ambiguous proposal, over every input, are exactly the
    analysis's fixed reasons, and each is its own category, read from the head of the label's note; repeats that disagree
    (combine_repeats) are one category whatever proposals they list; a note with no reason, or with a reason D19 does not
    give, gets a category that holds nothing of its text."""
    pl = propose_labels_module()
    targeted = Label(value="invalid", violated_requirements=["R1"], labeler="nearmiss:v1",
                     labeler_kind=LabelerKind.construction, timestamp=T0)
    built_valid = Label(value="valid", labeler="altimpl:v1", labeler_kind=LabelerKind.construction, timestamp=T0)
    reasons = set()
    for origin in CandidateOrigin:
        for construction in (None, built_valid, targeted):
            for infra, rc_ok in ((True, False), (False, True), (False, False)):
                for violated_rc in ([], ["R1"], ["R2"]):
                    for reg_fail in ([], ["tests/test_mod.py::test_add"]):
                        for reg_infra in (False, True):
                            value, _, why = pl.d19(origin, construction, infra=infra, rc_ok=rc_ok, violated_rc=violated_rc,
                                                   reg_fail=reg_fail, reg_infra=reg_infra)
                            if value == "ambiguous":
                                reasons.add(why)
    assert reasons == set(analysis.D19_AMBIGUOUS_REASONS)
    for why in reasons:
        assert analysis.d19_reason_category(d19_note(why)) == why
        assert analysis.d19_reason_category(why) == why  # a note that holds the reason alone
    for proposals in ([("invalid", ["R1"], "a"), ("ambiguous", [], "b"), ("invalid", ["R1"], "a")],
                      [("valid", [], "c"), ("invalid", ["R2", "REGRESSION"], "d"), ("valid", [], "c")]):
        value, violated, why = pl.combine_repeats(proposals)
        assert (value, violated) == ("ambiguous", []) and analysis.d19_reason_category(d19_note(why)) == analysis.D19_REPEATS_DISAGREE
    assert analysis.d19_reason_category("") == analysis.d19_reason_category(None) == analysis.D19_NO_REASON
    for other in (SECRET_FINDING, d19_note("construction valid, confirmed by reference checks and regression norm")):
        assert analysis.d19_reason_category(other) == analysis.D19_UNRECOGNISED  # never its text, nor a reason of no ambiguity


def test_the_label_block_carries_d19_s_reason_for_each_ambiguous_candidate(tmp_path):
    """A natural run's per-family label block keeps every field and gains d19: D19's proposals of the held-out candidates,
    each value counted, zero included, and the reason category of each ambiguous candidate, read from its D19 label's
    note (the candidate files, hashed in meta.inputs); analysis.md lists them. Nothing of a note but its category is
    written."""
    run, tasks = build_world(tmp_path / "repo", 3)
    pl = propose_labels_module()
    repeats = pl.combine_repeats([("invalid", ["R-corr"], "x"), ("ambiguous", [], "y"), ("invalid", ["R-corr"], "x")])[2]
    pre = "natural pre-review state passes the reference checks: the correction is not observable by the checks"
    passes = "construction invalid but reference checks and regression norm pass"
    relabel_d19(tasks[0], "eval-nm-1", "ambiguous", [], d19_note(passes))
    relabel_d19(tasks[0], "eval-alt-2", "ambiguous", ["REGRESSION"], d19_note("construction valid but checks fail"))
    relabel_d19(tasks[1], "pre-review", "ambiguous", [], d19_note(pre))  # the world's reference checks pass it
    relabel_d19(tasks[1], "eval-nm-2", "ambiguous", [], d19_note(repeats))
    relabel_d19(tasks[2], "eval-nm-3", "ambiguous", [], SECRET_FINDING + " | {}")  # a note that names no reason of D19
    relabel_d19(tasks[2], "eval-nm-1", "ambiguous", [], "")
    tr = tasks[0].tasks_root
    a = analyze(run, tr, allow_proposed=True, n_boot=50)
    labels = a["labels"]
    plain = analysis.label_summary([tr / nt.task_id for nt in tasks])  # as for a run that is not natural
    for nt in tasks:  # every field of the block is kept as it was
        assert {k: v for k, v in labels[nt.task_id].items() if k != "d19"} == plain[nt.task_id] and "d19" not in plain[nt.task_id]
        counts, d19 = labels[nt.task_id]["counts"], labels[nt.task_id]["d19"]
        assert {v: counts.get(v, 0) for v in ("valid", "invalid", "ambiguous", "unlabeled")} == {
            v: d19[v] for v in ("valid", "invalid", "ambiguous", "unlabeled")}
    assert labels["NP-90"]["d19"] == {"valid": 1, "invalid": 3, "ambiguous": 2, "unlabeled": 0, "ambiguous_reasons": {
        "NP-90-eval-alt-2": "construction valid but checks fail", "NP-90-eval-nm-1": passes}}
    assert labels["NP-91"]["d19"]["ambiguous_reasons"] == {"NP-91-eval-nm-2": analysis.D19_REPEATS_DISAGREE,
                                                           "NP-91-pre-review": pre}
    assert labels["NP-92"]["d19"] == {"valid": 2, "invalid": 2, "ambiguous": 2, "unlabeled": 0, "ambiguous_reasons": {
        "NP-92-eval-nm-1": analysis.D19_NO_REASON, "NP-92-eval-nm-3": analysis.D19_UNRECOGNISED}}
    assert a["natural"]["d19_rule"] == analysis.D19_RULE
    files = a["meta"]["inputs"]["files_sha256"]
    for nt, kind in ((tasks[0], "eval-nm-1"), (tasks[1], "pre-review"), (tasks[2], "eval-nm-3")):
        path = nt.task_dir / "candidates" / f"{nt.candidate_id(kind)}.json"
        assert files[f"{nt.task_id}/candidates/{nt.candidate_id(kind)}.json"] == hashlib.sha256(path.read_bytes()).hexdigest()
    text = (run / "analysis.json").read_text() + (run / "analysis.md").read_text()
    for secret in ("test_never_copied", "test_x.py", "refcheck_failed", "R-corr'"):  # the notes' details stay out
        assert secret not in text, secret
    md = (run / "analysis.md").read_text()
    assert (f"* NP-90: 1, 3, 2, 0; ambiguous: NP-90-eval-alt-2 (construction valid but checks fail); NP-90-eval-nm-1 "
            f"({passes})") in md
    assert f"* NP-92: 2, 2, 2, 0; ambiguous: NP-92-eval-nm-1 ({analysis.D19_NO_REASON}); NP-92-eval-nm-3 " in md
    assert to_markdown(a) == md


def test_the_label_block_of_a_natural_run_outside_case_study_mode_has_d19_s_labels_too(ten):
    assert all(set(d["d19"]) == {"valid", "invalid", "ambiguous", "unlabeled", "ambiguous_reasons"}
               for d in ten.a["labels"].values())
    assert ten.a["labels"]["NP-91"]["d19"]["ambiguous_reasons"] == {"NP-91-pre-review": analysis.D19_NO_REASON}
    assert ten.a["natural"]["d19_rule"] == analysis.D19_RULE


# --------------------------------------------------------------------------- the recorded runs


@pytest.mark.parametrize("run_id", ["pilot-v0.3.3", "pilot-v0.3.5-regrade", "fresh-v1"])
def test_the_recorded_runs_regenerate_their_analysis_md(tmp_path, run_id):
    """Read only: each recorded run's manifest and results are copied, analysed in the copy, and analysis.md compared."""
    src = REPO / "results" / "runs" / run_id
    if not (src / "analysis.md").is_file():
        pytest.skip(f"{run_id} is not in this checkout")
    copy = tmp_path / run_id
    copy.mkdir()
    for name in ("manifest.json", "results.jsonl"):
        shutil.copy2(src / name, copy / name)
    a = analyze(copy, REPO / "tasks", allow_proposed=True)
    assert (copy / "analysis.md").read_bytes() == (src / "analysis.md").read_bytes()
    assert "natural" not in a and "case_study" not in a["meta"] and "secondary" not in a
    recorded = json.loads((src / "analysis.json").read_text())
    for x in (a, recorded):
        x["meta"]["inputs"].pop("git_revision")
        x["meta"]["inputs"]["files_sha256"] = {k: v for k, v in x["meta"]["inputs"]["files_sha256"].items() if not k.startswith("code/")}
    assert json.loads(json.dumps(a)) == recorded


def test_the_module_exports_what_the_cli_reads():
    """cmd_analyze prints each pooled condition's rates; in case-study mode ``conditions`` is empty, so it prints none."""
    # The natural-arm recipe is decision log D64 (planned as D61, which is the fresh-v1 run).
    assert analysis.NATURAL_PR == "natural:pr-review" and analysis.NATURAL_DECISION == "D64"
