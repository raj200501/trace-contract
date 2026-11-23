"""Analysis of recorded evaluation runs (tables are generated from records only).

Inputs: ``results/runs/<run_id>/results.jsonl`` + ``manifest.json`` and the task
directories (candidate labels, reference contracts). Output:
``analysis.json`` and ``analysis.md`` in the run directory.

Label policy:
* primary: final human labels only (``Candidate.final_label``);
* ``allow_proposed=True`` (automated pilot): fall back to the latest proposed label
  (model / construction). Every table produced this way is marked as an automated
  pilot and must not be described as validated ground truth.

Populations and candidate strata:
* every row carries its task's population; a run whose tasks come from more than one
  population is refused (:class:`MixedPopulations`) unless ``pool_populations=True``
  (``--pool-populations``), which marks the pooled tables and reports each population on
  its own rows (``by_population``);
* every row carries its candidate's stratum (:mod:`tracecontract.strata`): ``task`` for
  the task's own candidates, else the stratum the run graded it in; candidate strata are
  pooled, and also reported one by one (``by_stratum``).

These keys appear only for a run with a population other than ``controlled`` or with a
stratum candidate, so runs recorded before them (pilot-v0.2 to pilot-v0.3.3) regenerate
byte for byte.

Reporting rules of new runs (protocol v0.7 §15.7, v0.8 §16.6), ``rules="v0.8"``. A run is new,
and gets them by default, when a result was graded with ``tc-harness/0.3.4`` or later (new runs
use 0.3.5, §16.1); the recorded pilot runs (harness 0.3.3 or earlier) keep the pre-specified
analysis, so ``pilot-v0.3.3`` regenerates byte for byte. Under these rules:

* each distinct graded patch of a task counts once (:func:`distinct_patch_rows`), in every count
  but the per-task outcome listing and the fresh attempts' solve rates;
* the per-family table is the primary display (``per_family``);
* every paired comparison carries exact sign-flip p-values over families with their attainable
  floors (:func:`metrics.paired_signflip`);
* cluster-bootstrap intervals move to an appendix and are marked as not inferential below 10
  families (``meta.bootstrap``);
* the oracle-gated view, which drops a verifier from a task whose reference it fails and reports
  the drop as lost yield, is secondary (``oracle_gated``).

Whatever the rules: a fresh attempt (origin ``fresh_attempt``) without an attempt record, without
an audit verdict, or whose fresh-attempt audit found a read of forbidden material is excluded from
every analysis (:func:`attempt_exclusion`); its exclusion and the attempts' solve rates by
configuration and variant are reported under ``fresh_attempts`` (§15.4). Source-evidence labels
(natural PR-review tasks) are reported under ``source_evidence``, apart from D19 (§15.6).

Label-support verifiers (condition ``reference_check``: the reference checks of D19 and the
independent labeler of §15.5) are never evaluated conditions. Their results never become rows of a
condition, and a run that records one of them under an evaluated condition, or two verifiers of a
task under one evaluated condition, is refused (:class:`ConditionConflict`). When the run graded the
independent labeler (verifier ``independent_label``), its verdicts are a second labeling
(``independent_labeling``, §15.4): valid if it passes, invalid on ``task_failure``, ambiguous on any
other outcome. FA and FR per condition are reported under the primary labels and under this labeling
side by side, with their per-family tables, together with the agreement between D19 and the labeler
and the fresh attempts' solve rates under each labeling. These keys appear only for a run that graded
the labeler, so the recorded runs regenerate byte for byte.

Sensitivity view (protocol v0.10 §18.1): ``sensitivity_exclusions`` (``--sensitivity-exclusions``)
names files that list fresh attempts to exclude as well (an audit report's ``excluded`` list, or a
JSON list of attempt ids). The main analysis is written as usual; ``analysis_sensitivity.json`` and
``analysis_sensitivity.md`` recompute every table with those attempts excluded too, and say so.

Natural PR-review tasks (population ``natural:pr-review``; protocol §15.5, §15.6, §17, §19; the natural-arm
recipe decisions of :data:`NATURAL_DECISION`). They may lie under any tasks root (``data/natural/tasks``); the
repository that holds the committed records is found from the manifest's ``task_dir`` entries, or given
(``repo_root``). In any run, the first prompt of such a task, against which a requirement counts as introduced
later (a correction-violating negative), is its session's first user prompt, the linked issue
(``contract.first_user_prompt``), not the smallest ``introduced_at``, which can be a commit event's id (other
populations keep that rule; a task without a readable session too, listed in ``meta.first_prompt_fallback``);
and the independent labeler's pass on a ``natural_pre_review`` state labels it ambiguous in the second
labeling, as D19's natural rule does (the correction is not observable by the checks).

A natural run is a run whose tasks are all natural PR-review tasks, as the arm's run is (§15.2; a run pooled
with another population gets none of the following). For a natural run:

* a task whose labeler the run graded and whose ``status.json`` does not record the status ``usable`` is
  left out of the second labeling and reported; the agreement with D19 on the pre-review states is marked
  as existing before the labeler was written (§15.5), apart from the pool, whose generation order is
  checked against the labeler's ``frozen_at`` (each candidate's ``generation.budget.started_at``);
* the source-evidence block (source evidence, not a human label) reports, per family and condition,
  whether each pre-review state is accepted; the correction requirements (the reference contract's
  scored active requirements introduced at the review comment or one of the reviewer's replies, as
  ``contract.correction_event_ids`` and the pre-flight read them; a family without one is said not to be
  observed by its reference contract, with no near miss targeting the correction: D64, decision 14); and
  each pre-review state's D19 value and second-labeling label;
* ``natural`` holds the per-family flags (B1 unavailable by ``s10.json``; B1 equal to the D19 regression
  norm, by the manifests of B1's overlay and ``labels/base_tests_overlay``; the family's sample; the near
  misses on the correction; the construction facts, :data:`CONSTRUCTION_RULE`: contract counts, checks per
  verifier, the audits of C2 and C4 in counts and codes, whether B3 is available, and the status record of the
  reference checks; and ``d19_rule``, the rule of the label block's ``d19`` key below), the funnel S1 to S11 of both
  samples with reasons, build and replay
  reliability, and cost and time per accepted task with the parts that are not recorded (S10's cost per
  accepted task counts its time and its fetches on one basis, every family S10 processed, rejected ones
  included; the run's families' own S10 time is given beside it); every
  file it reads is hashed in ``meta.inputs`` (a directory by its manifest hash, under a key ending in
  ``/``). No text of a thread, no local path and no file name under a verifier's tests is recorded;
* the per-task label block (``labels.<task>``) keeps every field and gains ``d19``: D19's proposals for the task's
  held-out candidates, every value counted, and the reason category of each candidate D19 labels ambiguous, derived from
  the reason that scripts/propose_labels.py writes at the head of the label's note (:data:`D19_RULE`).

The repository's records (the natural index and the screening records) are read as the run's code revision
holds them (``manifest.json`` ``code_revision``, the commit whose index the run's gate read), so a later commit
of the index changes neither the case-study decision nor the index check; a run whose manifest names no commit of
the repository is read at HEAD, and ``natural.records`` says so.

Under the reporting rules of new runs (every natural run is graded with tc-harness/0.3.5, §16.1):

* B3 (``diff_derived``) is a secondary condition (:data:`SECONDARY_CONDITIONS`): its rates, per-family
  table and comparisons are reported under ``secondary``, apart from the primary tables, and its
  comparisons stay out of the primary null tally;
* case-study mode (§19.6, §20.3): each natural run is reported on its own, so while the run grades fewer
  than :data:`NATURAL_SIZE_THRESHOLD` accepted tasks of its own (its families accepted, S11, in the
  natural index at the run's code revision; or the index cannot be read), the run's tasks are
  exploratory case studies: every table is per family, with no pooled rate, interval or p-value
  (``conditions`` is empty and so is ``comparisons``; no bootstrap), and a banner says so. The index's
  accepted tasks over both samples (``accepted_in_index``) decide nothing; only a combined report over
  both runs applies the threshold to their union (§20.3). With 10 or more, §15.6 and §15.7 apply in
  full, the source-evidence block also carries paired sign-flip comparisons, and one exploratory view
  clusters the families by repository (``repository_clustered``; D64, decision 10). Either way the
  run's families are checked against the accepted families of their samples in the index (§20.2:
  each run grades the accepted families of its sample).

A natural run analysed under the pilot rules (only a test run, whose grader records no tc-harness/0.3.4
or later) keeps the pilot tables; the pilot rules are refused for a natural run whose default is the
reporting rules of new runs (:class:`NaturalRunError`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Sequence

from .metrics import INFRA, ConditionSummary, Row, family_rates, paired_difference, paired_signflip, summarize
from .schemas import (
    CONSTRUCTED_ORIGINS, Candidate, CandidateOrigin, GenerationRecord, LabelerKind, Population, Snapshot, TaskContract,
    TaskManifest, VerificationResult, VerifierCondition, VerifierSpec,
)
from .store import jsonl_lines, load, read_jsonl, write_json
from .strata import TASK_STRATUM, StratumError, run_stratum_candidates

PILOT_LABELER = "builder:refcheck+regression+construction:v1"  # decision log D19
_CHECKS: dict[str, dict] = {}  # construction checks by candidate id (filled by build_rows for policy "check")
CONSTRUCTED = (CandidateOrigin.constructed_near_miss, CandidateOrigin.valid_alternative)
# The population of every run recorded before populations were reported; a run with another
# population, or with more than one, gets the population keys of the output.
DEFAULT_POPULATION = Population.controlled.value
# Reporting rules: the pre-specified analysis of the recorded runs, and the rules of new runs (§15.7, §16.6).
PILOT_RULES, NEW_RUN_RULES = "pilot", "v0.8"
REPORTING_RULES = (PILOT_RULES, NEW_RUN_RULES)
NEW_RUN_HARNESS = (0, 3, 4)  # 0.3.4 is never used for a run (§16.1); new runs use tc-harness/0.3.5 or later
_HARNESS = re.compile(r"tc-harness/(\d+)\.(\d+)\.(\d+)")
MIN_INFERENTIAL_FAMILIES = 10  # bootstrap intervals over fewer families are marked as not inferential (§15.7)
# The representative of candidates with the same graded patch: a natural state first, then a fresh attempt.
_REPRESENTATIVE_RANK = {CandidateOrigin.observed_pre_correction.value: 0, CandidateOrigin.natural_pre_review.value: 0,
                        CandidateOrigin.fresh_attempt.value: 1, CandidateOrigin.observed_other.value: 1}
# Label-support verifiers (D19, protocol §15.5, D55): the reference checks and the independent labeler. Their condition is
# never an evaluated one, so their results never become rows of a condition (build_rows).
LABEL_SUPPORT_CONDITION = VerifierCondition.reference_check.value
INDEPENDENT_LABELER = "independent_label"
LABEL_SUPPORT_VERIFIERS = ("reference_check", INDEPENDENT_LABELER)
# The sensitivity view of protocol §18.1, written beside the main analysis.
SENSITIVITY_JSON, SENSITIVITY_MD = "analysis_sensitivity.json", "analysis_sensitivity.md"
# The natural PR-review arm (protocol §15.6, §17, §19; see the module docstring).
NATURAL_PR = Population.natural_pr_review.value
NATURAL_DECISION = "D64"  # the decision-log entry of the natural-arm recipe (planned as D61), which fixes the rules below
# B3 is a secondary arm of the natural PR-review arm (§15.6): reported apart from the primary conditions of a natural run.
SECONDARY_CONDITIONS = ("diff_derived",)
NATURAL_SIZE_THRESHOLD = 10  # §15.6, §19.6: below this many accepted tasks over both samples, per-family case studies only
NATURAL_INDEX = "data/manifests/natural_tasks_index.json"  # the committed index (contract.NATURAL_INDEX), at the run's revision
NATURAL_FUNNEL = "data/manifests/screening_natural_aidev.json"  # stages S1 to S8a (D48)
NATURAL_S9 = {"first": "data/manifests/screening_natural_aidev_s9.json",  # the first S9 sample (D50)
              "extension": "data/manifests/screening_natural_aidev_s9x.json"}  # the S9 extension (§19.2)
NATURAL_FETCH_LOG = "data/natural/s10_fetch_log.jsonl"  # S10's fetches, by repository id (git-ignored, read in place)
FUNNEL_STAGES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S8a")
S10_RECORD = "s10.json"  # a natural family's S10 record (natural_pr.S10_RECORD)
S10_REJECTION = "rejection.json"  # all a family rejected during the build keeps (natural_pr.REJECTION; no start time)
LABELER_STATUS = "verifiers/independent_label/status.json"  # the labeler's usability record (§15.5)
REFCHECK_STATUS = "verifiers/reference_check/status.json"  # the reference checks' usability record, written at P5 (D64)
B3_UNAVAILABLE = "verifiers/*/unavailable.json"  # beside the tests of a B3 its selection took out (scripts/select_b3_tests.py)
B1_OVERLAY = "verifiers/repo_tests/overlay"  # B1: the base-test subset at the addressing commit (§17.2)
NORM_OVERLAY = "labels/base_tests_overlay"  # D19's regression norm: the subset at the base (scripts/propose_labels.py)
# Files of a natural task that the natural sections read, hashed in meta.inputs (directories by their manifest hash).
NATURAL_INPUTS = ("session.json", "snapshot.json", S10_RECORD, "reconstruction_check.json", "verifiers_extra.json",
                  "verifiers/*/spec.json", LABELER_STATUS, REFCHECK_STATUS, B3_UNAVAILABLE, "labels/proposed_labels.json")
NATURAL_CODE = ("contract.py", "tasks.py", "snapshot.py")  # the modules the natural sections run, hashed in meta.inputs
NATURAL_PRE_REVIEW = CandidateOrigin.natural_pre_review.value
# The candidates ranked first as the representative of held-out duplicates (post hoc, item 3): a natural state.
_STATE_FIRST = frozenset({CandidateOrigin.observed_pre_correction, CandidateOrigin.natural_pre_review})


class MixedPopulations(ValueError):
    """The run's tasks come from more than one population and pooling was not asked for (``--pool-populations``)."""


class ConditionConflict(ValueError):
    """A verifier would be scored as an evaluated condition it is not: refused before anything is written.

    A label-support verifier (the reference checks or the independent labeler) recorded under an evaluated
    condition, or two verifiers of one task recorded under the same evaluated condition, whose rows the
    analysis could not tell apart.
    """


class SensitivityExclusionsError(ValueError):
    """An exclusions file of the sensitivity view (``--sensitivity-exclusions``) cannot be used: refused before anything is written."""


class NaturalRunError(ValueError):
    """A natural PR-review run cannot be analysed as asked: the pilot rules were asked for a run whose default is the
    reporting rules of new runs (a natural run is reported under §15.7 and §19.6). Refused before anything is written."""


def candidate_label(c: Candidate, policy: str):
    """Label used for analysis under a label policy.

    * ``human``: adjudicated / latest human label only (primary analysis).
    * ``pilot``: human label if present, else the pre-specified automated proposal
      (rule D19, labeler ``PILOT_LABELER``); candidates without one are unlabeled.
    * ``construction`` (exploratory, not pre-specified): human label if present, else
      the construction label for constructed candidates and the D19 proposal for the
      others.
    * ``check`` (exploratory, post hoc): human label if present, else the independent
      construction check's assessed label (``labels/construction_checks.json``); unsure
      or unchecked candidates are unlabeled.
    """
    human = c.final_label()
    if human is not None or policy == "human":
        return human
    if policy == "check" and c.candidate_id in _CHECKS:
        assessed = _CHECKS[c.candidate_id].get("assessed_label")
        if assessed in ("valid", "invalid"):
            return SimpleNamespace(value=assessed, violated_requirements=_CHECKS[c.candidate_id].get("violated_requirements", []))
        return None
    if policy == "construction" and c.origin in CONSTRUCTED:
        cons = [lb for lb in c.labels if lb.labeler_kind == LabelerKind.construction]
        if cons:
            return cons[-1]
    pilot = [lb for lb in c.labels if lb.labeler == PILOT_LABELER]
    return pilot[-1] if pilot else None

COMPARISONS = [
    ("initial_plain", "full_plain", "information lost: initial-only vs correction-aware contract (plain tests)"),
    ("initial_audited", "full_audited", "information lost: initial-only vs correction-aware contract (audited tests)"),
    ("initial_plain", "initial_audited", "audit effect, initial-only contract"),
    ("full_plain", "full_audited", "audit effect, correction-aware contract"),
    ("llm_freeform", "full_audited", "full-session LLM baseline vs structured contract + audit"),
    ("llm_freeform", "full_plain", "full-session LLM baseline vs structured contract (plain)"),
    ("repo_tests", "full_audited", "repository tests vs structured contract + audit"),
]
# B3 (diff-derived, protocol §15.6), compared with the structured contract as B2 is. Computed only for a run
# that grades B3; kept apart from COMPARISONS, which scripts/exploratory_reanalysis.py applies to the pilot.
B3_COMPARISONS = [
    ("diff_derived", "full_audited", "diff-derived baseline (B3) vs structured contract + audit"),
    ("diff_derived", "full_plain", "diff-derived baseline (B3) vs structured contract (plain)"),
]
CONDITION_ORDER = ["initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform", "repo_tests",
                   "diff_derived"]
# The evaluated conditions, in order; a label-support verifier is never one of them (D19, protocol §15.5).
assert LABEL_SUPPORT_CONDITION not in CONDITION_ORDER


def _negative_type(c: Candidate, label, ref: TaskContract | None, first_prompt_id: str | None) -> str:
    if label is None or label.value != "invalid":
        return ""
    if c.origin == CandidateOrigin.noop:
        return "noop"
    if not label.violated_requirements or ref is None:
        return "unspecified"
    later = []
    for rid in label.violated_requirements:
        try:
            r = ref.by_id(rid)
        except KeyError:
            continue
        later.append(r.introduced_at != first_prompt_id)
    if not later:  # e.g. only REGRESSION: no reference requirement to classify by
        return "unspecified"
    return "correction_violating" if any(later) else "initial_violating"


def attempt_exclusion(c: Candidate) -> str | None:
    """Why the fresh attempt ``c`` is excluded from every analysis (protocol §15.4, §16.2); None if it is not.

    An attempt counts only once the fresh-attempt audit of its transcript has passed, which its
    attempt record says; one without a record or a verdict is excluded until it has one.
    """
    if c.origin != CandidateOrigin.fresh_attempt:
        return None
    if c.attempt is None:
        return "no attempt record"
    if c.attempt.audit is None:
        return "not audited: its attempt record holds no fresh-attempt audit verdict"
    if not c.attempt.audit.passed:
        return "the fresh-attempt audit found a read of forbidden material"
    return None


def reporting_rules(harness_versions) -> tuple[str, str]:
    """The reporting rules a run gets by default, and why: ``v0.8`` for a new run, ``pilot`` otherwise.

    A run is new when a result was graded with ``tc-harness/0.3.4`` or later (new runs use 0.3.5,
    protocol §16.1); every recorded pilot run was graded with 0.3.3 or earlier.
    """
    new = sorted(v for v in harness_versions
                 if (m := _HARNESS.fullmatch(v)) and tuple(int(x) for x in m.groups()) >= NEW_RUN_HARNESS)
    if new:
        return NEW_RUN_RULES, f"the run was graded with {', '.join(new)}, and new runs use tc-harness/0.3.5 or later (protocol §16.1)"
    return PILOT_RULES, "no result of the run was graded with tc-harness/0.3.4 or later, the harness of new runs"


def _check_conditions(task_id: str, verifiers: dict[str, dict]) -> None:
    """Refuse (:class:`ConditionConflict`) a task whose recorded verifiers would be scored as a condition they are not.

    A label-support verifier (:data:`LABEL_SUPPORT_VERIFIERS`) must be recorded under ``reference_check``, which is never
    an evaluated condition; and each evaluated condition may have one verifier per task, since a row is keyed by its
    condition and two verifiers of one condition would be counted as one.
    """
    for vid, v in sorted(verifiers.items()):
        if vid in LABEL_SUPPORT_VERIFIERS and v["condition"] != LABEL_SUPPORT_CONDITION:
            raise ConditionConflict(f"{task_id}: the label-support verifier {vid} is recorded under the evaluated condition "
                                    f"{v['condition']!r}, not {LABEL_SUPPORT_CONDITION!r}; label-support verifiers are never "
                                    "evaluated conditions (D19, protocol §15.5)")
    by_condition: dict[str, list[str]] = defaultdict(list)
    for vid, v in sorted(verifiers.items()):
        if v["condition"] != LABEL_SUPPORT_CONDITION:
            by_condition[v["condition"]].append(vid)
    shared = {c: vs for c, vs in sorted(by_condition.items()) if len(vs) > 1}
    if shared:
        raise ConditionConflict(f"{task_id}: " + "; ".join(f"verifiers {', '.join(vs)} are all recorded under the evaluated "
                                                           f"condition {c!r}" for c, vs in shared.items())
                                + "; each condition is scored once per candidate, so one task can have one verifier per condition")


def _natural_session(task_dir: Path, repo_root: Path):
    """A natural PR-review task's session (``tasks.session_for_task``: its ``session.json``); None when it cannot be read."""
    # tasks imports the controlled-session tooling; only natural tasks need it
    from .tasks import session_for_task

    try:
        return session_for_task(task_dir, repo_root)
    except (OSError, ValueError):
        return None


def natural_first_prompt(task_dir: Path, repo_root: Path) -> str | None:
    """The event id of a natural PR-review task's first prompt: its session's first user prompt, the linked issue
    (``contract.first_user_prompt``); None when the session cannot be read or has no user prompt. The smallest
    ``introduced_at`` would not do: a commit event's id sorts before the issue's, and a reply's before the comment's."""
    from .contract import first_user_prompt

    session = _natural_session(task_dir, repo_root)
    if session is None:
        return None
    try:
        return first_user_prompt(session).event_id
    except ValueError:
        return None


def build_rows(run_dir: Path, tasks_root: Path, *, allow_proposed: bool, policy: str | None = None,
               candidates: dict[tuple[str, str], Candidate] | None = None,
               excluded: dict[tuple[str, str], str] | None = None,
               also_exclude: dict[str, str] | None = None,
               support: dict[tuple[str, str], dict[str, str]] | None = None) -> tuple[list[Row], dict]:
    """The run's rows (one per result of a known candidate under an evaluated condition) and the analysis meta.

    Results of a fresh attempt that :func:`attempt_exclusion` excludes give no row; ``excluded``, if
    given, receives ``{(task, candidate): reason}`` for them, and ``candidates`` every candidate read.
    ``also_exclude`` (``{attempt id: reason}``; the sensitivity view, protocol §18.1) excludes the fresh
    attempts with those attempt ids as well, with that reason.

    Results of a label-support verifier (condition ``reference_check``, or a verifier id in
    :data:`LABEL_SUPPORT_VERIFIERS`) never give a row: ``support``, if given, receives their outcomes as
    ``{(task, candidate): {verifier id: outcome}}``, and the meta counts them (``label_support``). A run
    whose manifest would score a verifier as a condition it is not is refused (:func:`_check_conditions`).

    The first prompt that a negative's violated requirements are compared with (``negative_type``) is the
    smallest ``introduced_at`` of the task's reference contract, except for a natural PR-review task, where
    it is its session's first user prompt, the linked issue (:func:`natural_first_prompt`). A natural task whose
    session cannot be read keeps the smallest ``introduced_at``, and the meta lists it (``first_prompt_fallback``).
    """
    manifest = json.loads((run_dir / "manifest.json").read_text())
    results = read_jsonl(run_dir / "results.jsonl", VerificationResult)
    policy = policy or ("pilot" if allow_proposed else "human")
    meta: dict = {"label_policy": "proposed labels allowed (automated pilot)" if allow_proposed else "human labels only",
                  "label_rule": policy, "tasks": {},
                  "harness_versions": dict(Counter(r.harness_version for r in results))}
    cands: dict[tuple[str, str], Candidate] = {}
    stratum_of: dict[tuple[str, str], str] = {}  # stratum candidates only; the task's own are TASK_STRATUM
    fam: dict[str, str] = {}
    pop: dict[str, str] = {}
    refs: dict[str, TaskContract | None] = {}
    first: dict[str, str | None] = {}
    fallback: list[str] = []  # natural PR-review tasks whose session gives no first prompt
    conditions: dict[tuple[str, str], str] = {}
    if policy == "check":
        _CHECKS.clear()
        for t in manifest["tasks"]:
            cp = tasks_root / t["task_id"] / "labels" / "construction_checks.json"
            if cp.exists():
                _CHECKS.update(json.loads(cp.read_text()).get("checks", {}))
    for t in manifest["tasks"]:
        tid = t["task_id"]
        tdir = tasks_root / tid
        m = load(tdir / "task.json", TaskManifest)
        fam[tid] = m.family_id
        pop[tid] = m.population.value
        for p in m.candidates:
            c = load(tdir / p, Candidate)
            cands[(tid, c.candidate_id)] = c
        for cid, (name, _, c) in run_stratum_candidates(tdir, t).items():  # as the run recorded them
            if (tid, cid) in cands:
                raise StratumError(f"{tid}: candidate {cid} of stratum {name!r} has the id of one of the task's own candidates")
            cands[(tid, cid)] = c
            stratum_of[(tid, cid)] = name
        refp = tdir / m.contracts.get("reference", "contracts/reference.json")
        refs[tid] = load(refp, TaskContract) if refp.exists() else None
        first[tid] = None
        if m.population == Population.natural_pr_review:  # the linked issue, never a commit event's id (it sorts first)
            first[tid] = natural_first_prompt(tdir, tasks_root.parent)
            if first[tid] is None:
                fallback.append(tid)
        if first[tid] is None and refs[tid] is not None and refs[tid].requirements:
            intro = sorted({r.introduced_at for r in refs[tid].requirements})
            first[tid] = intro[0]
        _check_conditions(tid, t["verifiers"])
        for vid, v in t["verifiers"].items():
            conditions[(tid, vid)] = v["condition"]
    if candidates is not None:
        candidates.update(cands)
    rows: list[Row] = []
    kept_apart: Counter = Counter()  # results of label-support verifiers, by verifier id
    for r in results:
        c = cands.get((r.task_id, r.candidate_id))
        if c is None:
            continue
        why = attempt_exclusion(c)
        if why is None and also_exclude and c.attempt is not None and c.attempt.attempt_id in also_exclude:
            why = also_exclude[c.attempt.attempt_id]
        if why is not None:
            if excluded is not None:
                excluded[(r.task_id, r.candidate_id)] = why
            continue
        condition = conditions.get((r.task_id, r.verifier_id), r.verifier_id)
        if condition == LABEL_SUPPORT_CONDITION or r.verifier_id in LABEL_SUPPORT_VERIFIERS:  # never an evaluated condition
            kept_apart[r.verifier_id] += 1
            if support is not None:
                support.setdefault((r.task_id, r.candidate_id), {})[r.verifier_id] = r.outcome.value
            continue
        label = candidate_label(c, policy)
        rows.append(Row(task_id=r.task_id, family_id=fam[r.task_id], candidate_id=r.candidate_id,
                        condition=condition, outcome=r.outcome.value,
                        label=label.value if label else None, origin=c.origin.value,
                        negative_type=_negative_type(c, label, refs[r.task_id], first[r.task_id]),
                        population=pop[r.task_id], stratum=stratum_of.get((r.task_id, r.candidate_id), TASK_STRATUM)))
    meta["n_results"] = len(results)
    if fallback:  # only when a natural PR-review task's session cannot be read, so other runs keep their meta
        meta["first_prompt_fallback"] = {
            "tasks": fallback, "rule": "no readable session (session.json) gives these natural PR-review tasks' first user "
                                       "prompt, so the smallest introduced_at of the reference contract is used, as for other "
                                       "populations; a commit event's id can sort before the issue's"}
    if kept_apart:  # only for a run that graded a label-support verifier, so the recorded runs keep their meta
        meta["label_support"] = {"results": dict(sorted(kept_apart.items())),
                                 "rule": f"label-support verifiers (condition {LABEL_SUPPORT_CONDITION}: the reference checks "
                                         "and the independent labeler) are never evaluated conditions; their results are kept "
                                         "apart from the conditions' rows (D19, protocol §15.5)"}
    return rows, meta


def _populations(rows: list[Row]) -> dict[str, list[str]]:
    """The populations of the rows' tasks: ``{population: sorted task ids}``."""
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        out[r.population].add(r.task_id)
    return {p: sorted(ts) for p, ts in sorted(out.items())}


def _describe(populations: dict[str, list[str]]) -> str:
    return "; ".join(f"{p}: {', '.join(ts)}" for p, ts in populations.items())


def _stratum_candidates(run_dir: Path, tasks_root: Path) -> dict[str, dict[str, tuple[str, str, Candidate]]]:
    """The stratum candidates the run graded, by task id (:func:`strata.run_stratum_candidates`); empty without strata."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    found = {t["task_id"]: run_stratum_candidates(tasks_root / t["task_id"], t) for t in manifest["tasks"]}
    return {tid: f for tid, f in found.items() if f}


def _condition_rates(s: ConditionSummary) -> dict:
    """FA, FR, infrastructure outcomes and exclusions of one condition summary, as the output records them."""
    return {"false_acceptance": {"rate": s.fa.value, "num": s.fa.num, "den": s.fa.den, "ci95": s.fa_ci, "macro": s.fa_macro,
                                 "exact95": s.fa_exact, "ci95_degenerate": s.fa_ci_degenerate},
            "false_rejection": {"rate": s.fr.value, "num": s.fr.num, "den": s.fr.den, "ci95": s.fr_ci, "macro": s.fr_macro,
                                "exact95": s.fr_exact, "ci95_degenerate": s.fr_ci_degenerate},
            "infrastructure": {"num": s.infra.num, "den": s.infra.den},
            "excluded_unlabeled_or_ambiguous": s.excluded_unlabeled}


def _by_group(primary: list[Row], conds: list[str], attr: str, n_boot: int,
              prepare: Callable[[list[Row]], list[Row]] = list) -> dict:
    """FA/FR by condition within each value of ``attr`` (``population`` or ``stratum``), on that group's rows only.

    ``prepare`` turns a group's rows into the rows counted (for a new run: each distinct graded patch once).
    """
    out: dict = {}
    for g in sorted({getattr(r, attr) for r in primary}, key=lambda g: (g != TASK_STRATUM, g)):
        sub = prepare([r for r in primary if getattr(r, attr) == g])
        out[g] = {"tasks": sorted({r.task_id for r in sub}), "n_families": len({r.family_id for r in sub}),
                  "conditions": {c: _condition_rates(summarize(sub, condition=c, n_boot=n_boot))
                                 for c in conds if any(r.condition == c for r in sub)}}
    return out


def _patch_key(c: Candidate) -> str:
    """sha256 of the candidate's patch as graded (protected paths and git index lines removed)."""
    return hashlib.sha256(_norm_patch(c.patch).encode("utf-8")).hexdigest()


def distinct_patch_rows(rows: list[Row], patch_key: dict[tuple[str, str], str]) -> tuple[list[Row], list[dict]]:
    """``rows`` with each distinct graded patch of a task counted once (protocol §15.4, §15.7), and the merged groups.

    Candidates of one task whose graded patches are the same (``patch_key``, by ``(task, candidate)``)
    form one unit, shown under its representative: a natural state first (a pre-correction or
    pre-review state, then a fresh attempt), else the first candidate id. The unit's label is its
    labeled members' label when they agree, else ``ambiguous`` (excluded from FA and FR); its outcome
    under a condition is its members' outcome when they agree, else ``unresolved``, which counts as a
    rejection (as for repeats that disagree, §15.3).
    """
    members: dict[tuple[str, str], dict[str, Row]] = {}  # (task, patch key) -> {candidate: one of its rows}
    for r in rows:
        members.setdefault((r.task_id, patch_key[(r.task_id, r.candidate_id)]), {}).setdefault(r.candidate_id, r)
    unit_of: dict[tuple[str, str], tuple[Row, str | None, str, int]] = {}  # (task, candidate) -> (head, label, type, size)
    groups = []
    for (tid, _), ms in members.items():
        order = sorted(ms.values(), key=lambda r: (_REPRESENTATIVE_RANK.get(r.origin, 2), r.candidate_id))
        labels = {r.label for r in order if r.label is not None}
        label = None if not labels else next(iter(labels)) if len(labels) == 1 else "ambiguous"
        types = {r.negative_type for r in order if r.label == "invalid"}
        nt = (next(iter(types)) if len(types) == 1 else "unspecified") if label == "invalid" else ""
        for r in order:
            unit_of[(tid, r.candidate_id)] = (order[0], label, nt, len(order))
        if len(order) > 1:
            groups.append({"task_id": tid, "representative": order[0].candidate_id, "members": [r.candidate_id for r in order],
                           "origins": [r.origin for r in order], "labels": [r.label for r in order],
                           "labels_agree": len(labels) <= 1, "label": label})
    units: dict[tuple[str, str, str], list[Row]] = {}  # (task, representative, condition) -> rows, in first-seen order
    for r in rows:
        units.setdefault((r.task_id, unit_of[(r.task_id, r.candidate_id)][0].candidate_id, r.condition), []).append(r)
    out: list[Row] = []
    differ: dict[tuple[str, str], list[str]] = defaultdict(list)
    for (tid, rep, cond), rs in units.items():
        head, label, nt, size = unit_of[(tid, rep)]
        if size == 1:
            out.append(rs[0])
            continue
        outcomes = {r.outcome for r in rs}
        if len(outcomes) > 1:
            differ[(tid, rep)].append(cond)
        out.append(replace(head, condition=cond, label=label, negative_type=nt,
                           outcome=next(iter(outcomes)) if len(outcomes) == 1 else "unresolved"))
    for g in groups:
        g["outcomes_differ"] = differ.get((g["task_id"], g["representative"]), [])
    return out, groups


def _count(num: int, den: int) -> dict:
    return {"num": num, "den": den, "rate": None if den == 0 else num / den}


def _pooled(per_family: dict[str, dict[str, int]]) -> dict:
    """Pooled FA and FR counts from :func:`metrics.family_rates`."""
    tot = {k: sum(d[k] for d in per_family.values()) for k in ("fa_num", "fa_den", "fr_num", "fr_den")}
    return {"false_acceptance": _count(tot["fa_num"], tot["fa_den"]), "false_rejection": _count(tot["fr_num"], tot["fr_den"])}


def _oracle_gated(rows: list[Row], primary: list[Row], conds: list[str]) -> dict:
    """The oracle-gated view (protocol §15.7; secondary): a verifier is dropped from a task whose reference it does not pass.

    A cell (task, condition) is kept only if the run graded the task's reference solution with that
    condition and it passed. The candidates of a dropped cell are the lost yield; the paired
    comparisons use the tasks both conditions keep.
    """
    ref: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        if r.origin == CandidateOrigin.reference.value:
            ref[(r.task_id, r.condition)].append(r.outcome)
    kept: dict[str, list[str]] = {}
    per: dict = {}
    for c in conds:
        sub = [r for r in primary if r.condition == c]
        cells = sorted({r.task_id for r in sub})
        kept[c] = [t for t in cells if ref.get((t, c)) and all(o == "pass" for o in ref[(t, c)])]
        keep = [r for r in sub if r.task_id in kept[c]]
        fam = family_rates(keep, condition=c)
        lost = [r for r in sub if r.task_id not in kept[c]]
        per[c] = {"cells": len(cells), "cells_kept": len(kept[c]),
                  "dropped": {t: "the reference was not graded" if not ref.get((t, c)) else
                              f"does not pass its reference ({', '.join(ref[(t, c)])})" for t in cells if t not in kept[c]},
                  "lost_yield": {v: sum(r.label == v for r in lost) for v in ("invalid", "valid")},
                  **_pooled(fam), "per_family": fam}
    comparisons = []
    for a, b, desc in COMPARISONS + B3_COMPARISONS:
        if a in kept and b in kept:
            both = [t for t in kept[a] if t in kept[b]]
            sub = [r for r in primary if r.task_id in both]
            for metric in ("fa", "fr"):
                d = paired_difference(sub, a, b, metric, n_boot=0)
                comparisons.append({"a": a, "b": b, "metric": metric, "description": desc, "tasks": both,
                                    "difference": d["difference"], "n_metric": d["n_metric"], "discordant": d["discordant"],
                                    **paired_signflip(sub, a, b, metric)})
    return {"rule": "a verifier x task cell is dropped when the verifier does not pass the task's reference solution in the "
                    "run's sanity grading; its held-out candidates are the lost yield (secondary view, protocol §15.7)",
            "conditions": per, "comparisons": comparisons}


def _d19_value(c: Candidate) -> str | None:
    """The value of the candidate's latest D19 proposal (labeler ``PILOT_LABELER``), whatever the label policy."""
    d19 = [lb for lb in c.labels if lb.labeler == PILOT_LABELER]
    return d19[-1].value if d19 else None


def _solve_status(label: str | None) -> str:
    """An attempt's solve status under a labeling: valid is solved, invalid not solved, anything else undecided."""
    return "solved" if label == "valid" else "not_solved" if label == "invalid" else "undecided"


def _fresh_attempts(rows: list[Row], cands: dict[tuple[str, str], Candidate], excluded: dict[tuple[str, str], str],
                    conds: list[str], independent: dict[tuple[str, str], str | None] | None = None) -> dict | None:
    """Solve rates of the fresh attempts by configuration and variant, and the excluded attempts (protocol §15.4, §16.6).

    An attempt is solved when D19's natural-candidate rule labels it valid: its reference checks pass
    and the regression norm holds. D19 ambiguous (no decision from the reference checks) or no D19
    proposal is undecided and counts as not solved. Every attempt counts, duplicates included; an
    excluded attempt counts nowhere. None for a run without fresh attempts.

    ``independent`` (``{(task, candidate): label}`` of the independent labeling, for a run that graded the
    labeler) adds each cell's solve rate under that labeling (``independent_label``): valid is solved,
    invalid not solved, ambiguous or not graded by the labeler undecided, counted as not solved.
    """
    seen = {(r.task_id, r.candidate_id): r for r in rows}
    attempts = sorted(k for k in seen if cands[k].origin == CandidateOrigin.fresh_attempt)
    if not attempts and not excluded:
        return None
    cells: dict[str, dict] = {}
    for k in attempts:
        rec = cands[k].attempt  # an attempt without a record is excluded
        cell = cells.setdefault(f"{rec.configuration}/{rec.variant}", {
            "configuration": rec.configuration, "variant": rec.variant, "attempts": 0, "solved": 0, "not_solved": 0,
            "undecided": 0, "ended": Counter(), "per_family": {}})
        status = _solve_status(_d19_value(cands[k]))
        cell["attempts"] += 1
        cell[status] += 1
        cell["ended"][rec.ended.value] += 1
        fam = cell["per_family"].setdefault(seen[k].family_id, {"attempts": 0, "solved": 0})
        fam["attempts"] += 1
        fam["solved"] += status == "solved"
        if independent is not None:
            second = _solve_status(independent.get(k))
            x = cell.setdefault("independent_label", {"solved": 0, "not_solved": 0, "undecided": 0, "per_family": {}})
            x[second] += 1
            xf = x["per_family"].setdefault(seen[k].family_id, {"attempts": 0, "solved": 0})
            xf["attempts"] += 1
            xf["solved"] += second == "solved"
    for cell in cells.values():
        cell["rate"] = cell["solved"] / cell["attempts"]
        cell["ended"] = dict(sorted(cell["ended"].items()))
        cell["per_family"] = dict(sorted(cell["per_family"].items()))
        if "independent_label" in cell:
            cell["independent_label"]["rate"] = cell["independent_label"]["solved"] / cell["attempts"]
            cell["independent_label"]["per_family"] = dict(sorted(cell["independent_label"]["per_family"].items()))
    # Estimand 3 of §15.4: u1 attempts that violate a correction requirement, and how C1 and C3 grade them.
    u1 = [k for k in attempts if cands[k].attempt.variant == "u1"]
    viol = [k for k in u1 if (seen[k].label, seen[k].negative_type) == ("invalid", "correction_violating")]
    outcome = {(r.task_id, r.candidate_id, r.condition): r.outcome for r in rows}
    graded = {c: {"accepted": sum(outcome.get((*k, c)) == "pass" for k in viol), "n": sum((*k, c) in outcome for k in viol)}
              for c in ("initial_plain", "full_plain") if c in conds}
    out = {"rule": "solved: D19's natural-candidate rule labels the attempt valid (reference checks and regression norm); "
                   "D19 ambiguous or no proposal: undecided, counted as not solved; every attempt counts, duplicates included; "
                   "excluded attempts count nowhere (protocol §15.4)",
           "n_attempts": len(attempts), "n_excluded": len(excluded), "by_configuration_variant": dict(sorted(cells.items())),
           "u1_correction_violating": {"attempts": len(u1), "correction_violating": len(viol),
                                       "share": len(viol) / len(u1) if u1 else None, "graded_by": graded},
           "excluded": [{"task_id": t, "candidate_id": cid, "reason": why,
                         "attempt_id": cands[(t, cid)].attempt.attempt_id if cands[(t, cid)].attempt else None}
                        for (t, cid), why in sorted(excluded.items())]}
    if independent is not None:  # only for a run that graded the independent labeler
        out["rule_independent_label"] = ("solved under the second labeling: the independent labeler passes the attempt (valid); "
                                         "task_failure: not solved; any other outcome (ambiguous) or not graded by the "
                                         "labeler: undecided, counted as not solved; every attempt counts, duplicates "
                                         "included (protocol §15.4, §15.5)")
    return out


def _source_evidence(rows: list[Row], cands: dict[tuple[str, str], Candidate], conds: list[str]) -> dict | None:
    """Acceptance by condition under the source-evidence labels (natural PR-review tasks), apart from D19 (§15.6)."""
    lab = {}
    for r in rows:
        k = (r.task_id, r.candidate_id)
        if k not in lab:
            lab[k] = cands[k].source_evidence_label()
    lab = {k: v for k, v in lab.items() if v is not None}
    if not lab:
        return None
    out: dict = {"rule": "labeler kind source_evidence: the reviewer's request, the addressing commit and the S9 agreement; "
                         "reported apart from D19 and never a human label (protocol §15.6)",
                 "candidates": {f"{t}/{cid}": {"label": v.value, "labeler": v.labeler} for (t, cid), v in sorted(lab.items())},
                 "conditions": {}}
    for c in conds:
        sub = [r for r in rows if r.condition == c and (r.task_id, r.candidate_id) in lab]
        inv = [r for r in sub if lab[(r.task_id, r.candidate_id)].value == "invalid"]
        val = [r for r in sub if lab[(r.task_id, r.candidate_id)].value == "valid"]
        out["conditions"][c] = {"invalid": {"accepted": sum(r.outcome == "pass" for r in inv), "n": len(inv)},
                                "valid": {"rejected": sum(r.outcome != "pass" for r in val), "n": len(val)},
                                "outcomes": {f"{r.task_id}/{r.candidate_id}": r.outcome for r in sub}}
    return out


def _source_rows(rows: list[Row], cands: dict[tuple[str, str], Candidate]) -> list[Row]:
    """The rows of the candidates with a source-evidence label, labelled by it (an invalid one violates the correction)."""
    out = []
    for r in rows:
        lb = cands[(r.task_id, r.candidate_id)].source_evidence_label()
        if lb is not None:
            out.append(replace(r, label=lb.value, negative_type="correction_violating" if lb.value == "invalid" else ""))
    return out


def _source_per_family(se_rows: list[Row], conds: list[str]) -> dict:
    """Per condition and family: the source-evidence-invalid candidates accepted, and the valid ones rejected."""
    out: dict = {}
    for c in conds:
        fams: dict[str, dict] = {}
        for r in (x for x in se_rows if x.condition == c):
            f = fams.setdefault(r.family_id, {"invalid": {"accepted": 0, "n": 0}, "valid": {"rejected": 0, "n": 0}})
            if r.label == "invalid":
                f["invalid"]["n"] += 1
                f["invalid"]["accepted"] += r.outcome == "pass"
            elif r.label == "valid":
                f["valid"]["n"] += 1
                f["valid"]["rejected"] += r.outcome != "pass"
        if fams:
            out[c] = dict(sorted(fams.items()))
    return out


def _source_comparisons(se_rows: list[Row], conds: list[str]) -> list[dict]:
    """Paired comparisons (COMPARISONS and B3's) under the source-evidence labels, with exact sign-flip p-values over
    families: FA, the acceptance of the pre-review states (and FR only if a source-evidence label is valid)."""
    metrics = ("fa", "fr") if any(r.label == "valid" for r in se_rows) else ("fa",)
    out = []
    for a, b, desc in COMPARISONS + B3_COMPARISONS:
        if a in conds and b in conds:
            for metric in metrics:
                d = paired_difference(se_rows, a, b, metric, n_boot=0)
                out.append({"a": a, "b": b, "metric": metric, "description": desc, "difference": d["difference"],
                            "n_metric": d["n_metric"], "discordant": d["discordant"], **paired_signflip(se_rows, a, b, metric)})
    return out


def _natural_source_evidence(base: dict | None, rows: list[Row], cands: dict[tuple[str, str], Candidate], conds: list[str],
                             secondary: tuple[str, ...], nat: dict, second: dict | None,
                             support: dict[tuple[str, str], dict[str, str]], *, new_rules: bool, case_study: bool) -> dict | None:
    """The source-evidence block of a natural PR-review run (protocol §15.6): source evidence, not a human label.

    Per family and condition, whether each pre-review state is accepted (``per_family``; B3 under
    ``secondary_per_family`` when it is secondary); for each pre-review state its correction requirements (and whether the
    reference contract observes the correction: D64, decision 14), its D19 value, its second-labeling label (None when
    the labeler did not grade it, or graded it and is left out: ``independent_label_left_out``, only for a labeler the
    run graded) and the run's reference-check outcome (``pre_review``). Outside case-study mode it also keeps the pooled
    counts (``conditions``) and, under the reporting rules of new runs, the paired sign-flip comparisons
    (``comparisons``; B3's under ``secondary_comparisons``)."""
    se_rows = _source_rows(rows, cands)
    if not se_rows:
        return base
    family = {r.task_id: r.family_id for r in rows}
    primary_c = [c for c in conds if c not in secondary]
    sec_c = [c for c in conds if c in secondary]
    labelled = (second or {}).get("candidates", {})
    left_out = set((second or {}).get("left_out", {}))  # the labelers the run graded and leaves out (not usable)
    pre: dict[str, dict] = {}
    for t, cid in sorted({(r.task_id, r.candidate_id) for r in se_rows}):
        c = cands[(t, cid)]
        lb = c.source_evidence_label()
        sup = support.get((t, cid), {})
        left = t in left_out
        flags = nat["families"].get(t, {})
        pre[f"{t}/{cid}"] = {"task_id": t, "family_id": family.get(t), "origin": c.origin.value,
                             "source_evidence": lb.value if lb else None, "source_labeler": lb.labeler if lb else None,
                             "correction_requirements": nat["corrections"].get(t, []),
                             "reference_observes_correction": flags.get("reference_observes_correction"), "d19": _d19_value(c),
                             "independent_label": None if left else labelled.get(f"{t}/{cid}", {}).get("label"),
                             "independent_label_left_out": left, "independent_label_outcome": sup.get(INDEPENDENT_LABELER),
                             "reference_checks_outcome": sup.get("reference_check"),
                             # each condition's outcome, so that a rejection by an infrastructure outcome or an unresolved
                             # pair (a rejection, §6, §15.3) can be told from a task failure
                             "outcomes": dict(sorted((r.condition, r.outcome) for r in se_rows
                                                     if (r.task_id, r.candidate_id) == (t, cid)))}
    out: dict = {"rule": (base or {}).get("rule"), "banner": SOURCE_EVIDENCE_BANNER,
                 "candidates": (base or {}).get("candidates", {}), "pre_review": pre,
                 "per_family": _source_per_family(se_rows, primary_c)}
    if sec_c:
        out["secondary_per_family"] = _source_per_family(se_rows, sec_c)
    if case_study:
        out["case_study"] = "per-family tables only: no pooled count, rate or p-value (protocol §19.6)"
        return out
    pooled = (base or {}).get("conditions", {})
    out["conditions"] = {c: v for c, v in pooled.items() if c not in secondary}
    if sec_c:
        out["secondary_conditions"] = {c: v for c, v in pooled.items() if c in secondary}
    if new_rules:
        comps = _source_comparisons(se_rows, conds)
        out["comparisons"] = [d for d in comps if d["a"] not in secondary and d["b"] not in secondary]
        if sec_c:
            out["secondary_comparisons"] = [d for d in comps if d["a"] in secondary or d["b"] in secondary]
    return out


INDEPENDENT_RULE = ("the independent labeler (verifier independent_label, condition reference_check; protocol §15.5) labels a "
                    "candidate valid if it passes, invalid if it fails with task_failure, and ambiguous on any other outcome "
                    "(unresolved, environment failure, verifier error or timeout, recorded as such); a candidate it did not grade "
                    "is unlabeled. Its verdicts are a second labeling (§15.4): a model proposal, as D19 is, never a human label. "
                    "The labeler is label support, never an evaluated condition")
_LABEL_VALUES = ("valid", "invalid", "ambiguous")


NATURAL_LABELER_RULE = (f"a pass on a natural pre-review state (origin {NATURAL_PRE_REVIEW}) is ambiguous, as D19's natural rule "
                        f"makes it: the correction is not observable by the checks ({NATURAL_DECISION}); the pre-review states "
                        "existed before the labeler was written, so the agreement on them is marked as such (§15.5); a task "
                        f"whose labeler the run graded and whose {LABELER_STATUS} does not record the status usable is left "
                        "out of the second labeling and reported")


def independent_label(outcome: str | None, origin: str | None = None) -> str | None:
    """The second labeling's label of a candidate from the independent labeler's outcome (protocol §15.4); None if not graded.

    A pass on a natural pre-review state (``origin`` ``natural_pre_review``) is ambiguous, not valid: as D19's natural rule
    says, the correction is then not observable by the checks (protocol §15.6; :data:`NATURAL_DECISION`)."""
    if outcome is None:
        return None
    if outcome == "pass":
        return "ambiguous" if origin == NATURAL_PRE_REVIEW else "valid"
    return "invalid" if outcome == "task_failure" else "ambiguous"


def _unit_value(values: list[str | None]) -> str | None:
    """A unit's label from its members' labels, as :func:`distinct_patch_rows` sets it: theirs if the labeled ones agree, else ambiguous."""
    found = {v for v in values if v is not None}
    return None if not found else next(iter(found)) if len(found) == 1 else "ambiguous"


def _label_units(keys: list[tuple[str, str]], patch_key: dict[tuple[str, str], str] | None,
                 origin: dict[tuple[str, str], str]) -> list[list[tuple[str, str]]]:
    """The units labels are counted in: each distinct graded patch of a task (``patch_key``, the rules of a new run), else
    each candidate. Each unit lists its members with its representative first, as :func:`distinct_patch_rows` orders them;
    the units are in the order of their task and representative."""
    groups: dict[tuple, list[tuple[str, str]]] = {}
    for k in sorted(keys):
        groups.setdefault((k[0], patch_key[k]) if patch_key else k, []).append(k)
    units = [sorted(ms, key=lambda k: (_REPRESENTATIVE_RANK.get(origin[k], 2), k[1])) for ms in groups.values()]
    return sorted(units, key=lambda ms: ms[0])


def _agreement(units: list[list[tuple[str, str]]], d19: dict[tuple[str, str], str | None],
               second: dict[tuple[str, str], str | None], outcome: dict[tuple[str, str], str]) -> dict:
    """Agreement of D19 and the independent labeling over ``units``: counts, the 2x2 table of the units both decide, and
    the full cross-table (``none``: no D19 proposal, or not graded by the labeler)."""
    table = {a: {b: 0 for b in ("valid", "invalid")} for a in ("valid", "invalid")}
    cross = {a: {b: 0 for b in (*_LABEL_VALUES, "none")} for a in (*_LABEL_VALUES, "none")}
    pairs, disagreements = [], []
    for members in units:
        a, b = _unit_value([d19[k] for k in members]), _unit_value([second[k] for k in members])
        cross[a or "none"][b or "none"] += 1
        if a in ("valid", "invalid") and b in ("valid", "invalid"):
            table[a][b] += 1
            pairs.append((a, b))
            if a != b:
                disagreements.append({"task_id": members[0][0], "representative": members[0][1],
                                      "members": [k[1] for k in members], "d19": a, "independent_label": b,
                                      "outcomes": [outcome.get(k) for k in members]})
    agree = sum(a == b for a, b in pairs)
    xa, xb = [int(a == "valid") for a, _ in pairs], [int(b == "valid") for _, b in pairs]
    return {"n_units": len(units), "n_decided_by_both": len(pairs), "agree": agree, "disagree": len(pairs) - agree,
            "agreement": agree / len(pairs) if pairs else None, "kappa": cohen_kappa(xa, xb),
            "kappa_degenerate": len(set(xa)) < 2 or len(set(xb)) < 2, "table": table, "crosstab": cross,
            "disagreements": disagreements}


def _labeling_rates(rows: list[Row], condition: str) -> dict:
    """Pooled FA and FR of one condition under the labels the rows carry, the excluded count and the per-family table."""
    fam = family_rates(rows, condition=condition)
    return {**_pooled(fam), "excluded_unlabeled_or_ambiguous":
            sum(r.label not in ("valid", "invalid") for r in rows if r.condition == condition), "per_family": fam}


def _side_by_side(primary_rows: list[Row], second_rows: list[Row], conds: list[str]) -> dict:
    """FA and FR per condition under the primary labels and under the second labeling, on the same (prepared) rows."""
    return {c: {"primary": _labeling_rates(primary_rows, c), "independent_label": _labeling_rates(second_rows, c)}
            for c in conds if any(r.condition == c for r in primary_rows)}


def _independent_labeling(rows: list[Row], every: list[Row], support: dict[tuple[str, str], dict[str, str]],
                          cands: dict[tuple[str, str], Candidate], conds: list[str],
                          prepare: Callable[[list[Row]], list[Row]], patch_key: dict[tuple[str, str], str] | None,
                          with_strata: bool, label_rule: str, exclude_origins: tuple[str, ...],
                          natural: dict | None = None) -> dict | None:
    """The independent labeler's verdicts as a second labeling (protocol §15.4, §15.5); None if the run did not grade it.

    ``every`` holds the held-out candidates' rows (reference and no-op excluded) with their primary labels; they
    are counted as the primary analysis counts them (``prepare``; for a new run each distinct graded patch once,
    ``patch_key``). Reported: the labels, the labeler's sanity outcomes (reference, no-op), FA and FR per condition
    under both labelings side by side with the per-family tables (pooled, and per candidate stratum for a run with
    strata), and the agreement between D19's proposals and the labeling, per stratum. Agreement on a controlled
    task's own candidates is exploratory: they existed before the labeler was written (§15.5).

    ``natural`` (a natural PR-review run, :func:`_natural_context`): a pass on a pre-review state is ambiguous
    (:func:`independent_label`); the tasks whose labeler is not usable (``left_out``) are left out and reported, with
    the labeler's outcomes on their reference and no-op; the agreement of each stratum with natural tasks is also
    given apart for the units holding a pre-review state, which existed before the labeler was written, and for the
    others, the pool generated after it was frozen; and in case-study mode (§19.6) every table is per family, with no
    pooled rate (``per_family`` and the agreement ``per_family`` replace ``conditions``, ``by_stratum`` and ``pooled``).
    """
    graded = {k: v[INDEPENDENT_LABELER] for k, v in support.items() if INDEPENDENT_LABELER in v}
    left_out = (natural or {}).get("left_out", {})
    left = {t: why for t, why in left_out.items() if any(k[0] == t for k in graded)}  # the labelers the run graded
    graded = {k: v for k, v in graded.items() if k[0] not in left}
    if not graded and not left:
        return None
    heldout = sorted({(r.task_id, r.candidate_id) for r in every})
    second = {k: independent_label(graded.get(k), cands[k].origin.value) for k in heldout}
    d19 = {k: _d19_value(cands[k]) for k in heldout}
    origin = {k: cands[k].origin.value for k in heldout}
    stratum = {(r.task_id, r.candidate_id): r.stratum for r in every}
    population = {r.task_id: r.population for r in rows}
    family = {r.task_id: r.family_id for r in rows}
    second_every = [replace(r, label=second[(r.task_id, r.candidate_id)], negative_type="") for r in every]
    counts = Counter(second[k] or "not_graded" for k in heldout)
    sanity: dict[str, dict] = {}
    for k, o in sorted(graded.items()):
        if cands[k].origin.value in exclude_origins:
            s = sanity.setdefault(k[0], {}).setdefault(cands[k].origin.value, {"pass": 0, "n": 0, "outcomes": Counter()})
            s["pass"] += o == "pass"
            s["n"] += 1
            s["outcomes"][o] += 1
    for s in (x for t in sanity.values() for x in t.values()):
        s["outcomes"] = dict(sorted(s["outcomes"].items()))
    per_family_only = bool(natural and natural["case_study"]["applies"])
    out: dict = {
        "rule": INDEPENDENT_RULE, "verifier": INDEPENDENT_LABELER,
        **({"natural_rule": NATURAL_LABELER_RULE} if natural else {}),
        "primary_labels": ("human labels" if label_rule == "human" else
                           "D19's proposals, or a human label where one exists (the label rule of the primary analysis)"),
        "tasks": sorted({k[0] for k in graded}),
    }
    if natural:
        out["left_out"] = {t: {"why": why, "outcomes": _left_out_outcomes(support, cands, t, exclude_origins)}
                           for t, why in sorted(left.items())}
    if per_family_only:
        out["labels_per_family"] = {f: {v: sum((second[k] or "not_graded") == v for k in heldout if family[k[0]] == f)
                                        for v in (*_LABEL_VALUES, "not_graded")} for f in sorted(set(family.values()))}
    else:
        out["labels"] = {v: counts.get(v, 0) for v in (*_LABEL_VALUES, "not_graded")}
    out.update({
        "ambiguous_outcomes": dict(sorted(Counter(graded[k] for k in heldout if second[k] == "ambiguous").items())),
        "candidates": {f"{t}/{cid}": {"label": second[(t, cid)], "outcome": graded.get((t, cid)), "d19": d19[(t, cid)],
                                      **({"origin": origin[(t, cid)]} if natural else {}),
                                      **({"stratum": stratum[(t, cid)]} if with_strata else {})} for t, cid in heldout},
        "sanity": sanity,
    })
    if per_family_only:
        out.pop("ambiguous_outcomes")  # counts over every family; each candidate's outcome is listed above
        pe, ps = prepare(every), prepare(second_every)
        out["per_family"] = {c: {"primary": family_rates(pe, condition=c), "independent_label": family_rates(ps, condition=c)}
                             for c in conds if any(r.condition == c for r in pe)}
    else:
        out["conditions"] = _side_by_side(prepare(every), prepare(second_every), conds)
    names = sorted({stratum[k] for k in heldout}, key=lambda s: (s != TASK_STRATUM, s))
    if with_strata and not per_family_only:
        out["by_stratum"] = {s: {"tasks": sorted({k[0] for k in heldout if stratum[k] == s}),
                                 "conditions": _side_by_side(prepare([r for r in every if r.stratum == s]),
                                                             prepare([r for r in second_every if r.stratum == s]), conds)}
                             for s in names}
    natural_tasks = set((natural or {}).get("tasks", ()))
    frozen_at = {t: f.get("labeler", {}).get("frozen_at") for t, f in (natural or {}).get("families", {}).items()}

    def natural_split(units: list[list[tuple[str, str]]]) -> dict:
        """The units holding a pre-review state (which existed before the labeler) and the others, apart; for the others,
        whether each member's generation started after its family's labeler was frozen (:func:`_generation_order`)."""
        pre = [u for u in units if any(origin[k] == NATURAL_PRE_REVIEW for k in u)]
        rest = [u for u in units if not any(origin[k] == NATURAL_PRE_REVIEW for k in u)]
        return {"existed_before_labeler": {
                    "why": "units holding a natural pre-review state: the tree the reviewer commented on, which has existed "
                           "since S10 and so before the labeler was written, although no labeler writer could read it "
                           f"(protocol §15.5; {NATURAL_DECISION})",
                    **_agreement(pre, d19, second, graded)},
                "generated_after_labeler": {
                    "why": "the other units: the held-out pool, which protocol §15.5 and §19.7 have generated after the "
                           "labeler was frozen; the order is checked here, each member's generation start against its "
                           "family's labeler's frozen_at",
                    **_agreement(rest, d19, second, graded),
                    "order": _generation_order([k for u in rest for k in u], cands, frozen_at)}}

    def group(ks: list[tuple[str, str]], tasks: list[str], exploratory: bool) -> dict:
        units = _label_units(ks, patch_key, origin)
        g = {"tasks": tasks, "exploratory": exploratory,
             **({"why_exploratory": "these are the task's own candidates of controlled families, which existed "
                                    "before the labeler was written (protocol §15.5)"} if exploratory else {}),
             **_agreement(units, d19, second, graded)}
        if natural_tasks & set(tasks):
            g["natural"] = natural_split(units)
        return g

    rule = ("D19's proposal (labeler builder:refcheck+regression+construction:v1) against the second labeling, "
            + ("each distinct graded patch once (a unit's label is its members' when they agree, else ambiguous)"
               if patch_key else "each candidate once")
            + "; the 2x2 table holds the units both label valid or invalid, the cross-table every unit (none: no D19 "
              "proposal, or not graded by the labeler); per candidate stratum (§15.4 estimand 4, §15.5)")
    if per_family_only:
        fams = sorted({family[k[0]] for k in heldout})
        out["agreement"] = {
            "rule": rule.replace("per candidate stratum", "per task family (case-study mode, §19.6: no pooled agreement)"),
            "per_family": {f: group([k for k in heldout if family[k[0]] == f],
                                    sorted({k[0] for k in heldout if family[k[0]] == f}), False) for f in fams}}
        return out
    groups = {}
    for s in names:
        ks = [k for k in heldout if stratum[k] == s]
        tasks = sorted({k[0] for k in ks})
        groups[s] = group(ks, tasks, s == TASK_STRATUM and any(population[t] == Population.controlled.value for t in tasks))
    out["agreement"] = {
        "rule": rule,
        "by_stratum": groups,
        **({"pooled": {"exploratory": any(g["exploratory"] for g in groups.values()),
                       **_agreement(_label_units(heldout, patch_key, origin), d19, second, graded)}} if len(names) > 1 else {}),
    }
    return out


ORDER_RULE = ("a pool candidate counts as generated after the labeler was frozen when its generation started "
              "(generation.budget.started_at, with a time zone; for a combined record, the earliest start) after its family's "
              "labeler spec was frozen (frozen_at); the order is not shown for a candidate without that start, or whose "
              "family's labeler records no frozen_at (protocol §15.5, §19.7)")


def _time(raw: object) -> datetime | None:
    """``raw`` as a time with a time zone; None unless it is an ISO 8601 text with one."""
    try:
        t = datetime.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    return t if t is not None and t.tzinfo is not None else None


def _generation_start(c: Candidate) -> tuple[datetime | None, str | None]:
    """When the agent run that generated ``c`` started (``generation.budget.started_at``, as the pre-flight reads it), and
    why it is not known."""
    if c.generation is None:
        return None, "no generation record"
    t = _time(c.generation.budget.get("started_at"))
    return (t, None) if t is not None else (None, "its generation record holds no started_at with a time zone")


def _generation_order(members: list[tuple[str, str]], cands: dict[tuple[str, str], Candidate],
                      frozen_at: dict[str, str | None]) -> dict:
    """Whether each of ``members`` (``(task, candidate)``) was generated after its family's labeler was frozen
    (:data:`ORDER_RULE`): how many were, those that were not, and those whose order is not shown, with why."""
    after = 0
    not_after: list[str] = []
    not_shown: dict[str, str] = {}
    for k in sorted(members):
        name = f"{k[0]}/{k[1]}"
        at = _time(frozen_at.get(k[0]))
        start, why = _generation_start(cands[k])
        if at is None:
            not_shown[name] = "its family's labeler records no frozen_at"
        elif start is None:
            not_shown[name] = why or "no generation start"
        elif start > at:
            after += 1
        else:
            not_after.append(name)
    return {"rule": ORDER_RULE, "candidates": len(members), "after": after, "not_after": not_after, "not_shown": not_shown}


def _left_out_outcomes(support: dict[tuple[str, str], dict[str, str]], cands: dict[tuple[str, str], Candidate], task: str,
                       exclude_origins: tuple[str, ...]) -> dict[str, dict[str, int]]:
    """A left-out labeler's outcomes in the run on its task's reference and no-op (by origin), which say why it is unusable."""
    out: dict[str, Counter] = {}
    for k, v in sorted(support.items()):
        if k[0] == task and INDEPENDENT_LABELER in v and cands[k].origin.value in exclude_origins:
            out.setdefault(cands[k].origin.value, Counter())[v[INDEPENDENT_LABELER]] += 1
    return {o: dict(sorted(c.items())) for o, c in sorted(out.items())}


CASE_STUDY_RULE = ("protocol §20.3 (§19.6, §15.6): each natural run is reported on its own, so the size threshold counts the "
                   "run's own accepted tasks (its families accepted, S11, in the committed index), not the accepted tasks of "
                   f"both samples; with fewer than {NATURAL_SIZE_THRESHOLD}, the run's tasks are exploratory case studies, "
                   "reported in per-family tables only, with no pooled rate, interval or p-value; with "
                   f"{NATURAL_SIZE_THRESHOLD} or more, §15.6 and §15.7 apply in full to the run, and each task's sample is "
                   "reported. Only a combined report over both runs applies the threshold to their union")
INDEX_CHECK_RULE = ("protocol §20.2: each natural run grades the accepted families of its sample (natural-pr-v1 the first "
                    "sample's, natural-pr-v2 the extension's), so the run's families are checked against the accepted families "
                    "(S11 in the committed index) of the samples their index rows name; accepted families of another sample are "
                    "not the run's")
SECONDARY_RULE = ("B3 (diff_derived) is a secondary arm of the natural PR-review arm (protocol §15.6): its rates, per-family "
                  "table and paired comparisons are reported here, apart from the primary conditions, and its comparisons "
                  "stay out of the primary null tally")
SOURCE_EVIDENCE_BANNER = ("source evidence, not a human label: the reviewer's request, the addressing commit and the agreement of "
                          "both S9 judges label each pre-review state invalid with respect to the correction (protocol §15.6)")
NATURAL_RULE = ("natural PR-review arm (protocol §15.6, §17, §19): per family, its sample, whether B1 is available (s10.json) "
                "and whether its overlay equals D19's regression norm (labels/base_tests_overlay, by file), the correction "
                f"requirements (the reference contract's scored active requirements introduced at the review comment or one of "
                f"the reviewer's replies; {NATURAL_DECISION}, decision 14), the held-out near misses that name one in their "
                "construction label, and its construction facts (contract counts, checks per verifier, the audits of C2 and "
                "C4, whether B3 is available, the reference checks' status record; construction_rule); the funnel S1 to S11 "
                "of both samples with reasons; build and replay reliability; and cost and time per accepted task. Ids, "
                "outcomes, counts and hashes only")
# D19's reasons for an ambiguous proposal, as scripts/propose_labels.py writes them (its d19 and combine_repeats): it starts
# the note of each label with the reason (``<reason> | <details>``). Each fixed reason is its own category, and repeats that
# disagree are one category, whatever proposals the reason lists (labels.<task>.d19 of a natural run; D19_RULE).
D19_AMBIGUOUS_REASONS = (
    "reference checks did not produce a decision",
    "natural pre-review state passes the reference checks: the correction is not observable by the checks",
    "natural candidate passes reference checks; the regression norm did not produce a decision",
    "construction valid, reference checks pass; the regression norm did not produce a decision",
    "construction valid but checks fail",
    "construction invalid but failing checks map to other requirements",
    "construction invalid, reference checks pass; the regression norm did not produce a decision",
    "construction invalid but reference checks and regression norm pass",
)
D19_REPEATS_DISAGREE = "the repeats give different proposals: a missing decision"
D19_NO_REASON = "no reason recorded"
D19_UNRECOGNISED = "unrecognised reason"
_D19_REPEATS = re.compile(r"the \d+ repeats give different proposals \(.*\): a missing decision", re.DOTALL)
D19_RULE = (f"labels.<task>.d19, for a natural run only: D19's proposals (labeler {PILOT_LABELER}) for the task's held-out "
            "candidates, the reference and the no-op left out as in counts, with every value counted, zero included "
            "(unlabeled: no D19 proposal); and, for each candidate that D19 labels ambiguous, the category of its reason, "
            "read from the head of its label's note, where scripts/propose_labels.py writes the reason (its d19 and "
            "combine_repeats; decision log D19, D64): the reason itself where it is one of D19's fixed reasons for an "
            f"ambiguous label; '{D19_REPEATS_DISAGREE}' where the repeats disagree, whatever proposals the reason lists; "
            f"'{D19_NO_REASON}' for a note that holds none; and '{D19_UNRECOGNISED}' otherwise, with nothing of its text. "
            "Ids and categories only; the candidate files read are hashed in meta.inputs")
# What the cost block cannot count: no record of it exists in the repository or the task directories.
UNRECORDED_COST = (
    ("stages S1 to S9: the funnel queries, the S9 fetches and the S9 judges' agent runs (their records are kept outside "
     "the repository)"),
    ("S10 re-runs after compiler fixes (D59): s10.json keeps the times of the last build only, while the fetch log keeps "
     "every fetch"),
    ("the S10 compile step's time before built_at (resolving the commits, materialising the base and the candidates), "
     "apart from its fetches, whose seconds the log records: s10.json records no start of it"),
    "image builds and wheel downloads, apart from the wheelhouse bytes that s10.json records",
    "the host's own steps (D24): workspaces, builds, audits, freezing and labelling, apart from the run's grading time",
    ("agent runs that leave no generation record: the mappers, the optional construction checkers and any run before a "
     "re-run"),
)


def _task_order(task_id: str) -> tuple[int, str]:
    """Natural task ids in their number's order (NP-03 before NP-26 before NP-100); other ids after them."""
    m = re.fullmatch(r"NP-(\d+)", task_id)
    return (int(m.group(1)) if m else 10 ** 9, task_id)


def _sample_order(sample: str) -> tuple[int, str]:
    """The samples in their order: the first S9 sample, then the extension (§19.2), then anything else."""
    return ({"first": 0, "extension": 1}.get(sample, 2), sample)


def _json_file(path: Path) -> object:
    """The JSON value of ``path``; None when it is missing or not JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess | None:
    """``git -C repo_root <args>``, as ``contract.committed_text`` runs git (no ``GIT_*`` variable of the caller redirects
    it); None when git cannot be run."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, env=env, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _commit_id(repo_root: Path, rev: str) -> str | None:
    """The commit id that ``rev`` names in the repository at ``repo_root``; None when it names none."""
    p = _git(repo_root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    out = p.stdout.decode("ascii", "replace").strip() if p is not None and p.returncode == 0 else ""
    return out if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", out) else None


def _records_revision(repo_root: Path, manifest: dict) -> dict:
    """The commit whose repository records (the natural index, the screening records) a natural run's sections read: the
    run's code revision (``manifest.json`` ``code_revision``, HEAD when the run was made, as ``evaluate`` records it; a
    ``+dirty`` mark is dropped, since the run's gate read the committed index), so that a later commit of the index
    changes neither the case-study decision nor the index check; else, and said, HEAD at the time of the analysis."""
    raw = manifest.get("code_revision")
    rev = raw.split("+", 1)[0].strip() if isinstance(raw, str) else ""
    commit = _commit_id(repo_root, rev) if re.fullmatch(r"[0-9a-f]{7,64}", rev) else None
    if commit is not None:
        return {"revision": commit, "basis": "run", "source": f"the run's code revision {commit[:12]}",
                "rule": "read as the commit that the run's manifest records (code_revision) holds them, the records the "
                        "run's acceptance gate read; a later commit of the index changes nothing here"}
    why = ("the run's manifest records no code revision" if not isinstance(raw, str) or not raw else
           f"the run's code revision {raw!r} is not a commit of this repository")
    return {"revision": "HEAD", "basis": "head", "head_commit": _commit_id(repo_root, "HEAD"),
            "source": "the HEAD commit at the time of the analysis",
            "rule": f"read as HEAD holds them when the analysis runs, since {why}; a later commit of the index can change "
                    "this analysis", "why": why}


def _committed_json(repo_root: Path, rel: str, rev: str = "HEAD", source: str = "the HEAD commit"
                    ) -> tuple[object, str | None, str | None]:
    """A repository record as the commit ``rev`` holds it (``git show <rev>:./<rel>``; ``source`` names that commit in
    the reason): ``(value, sha256 of its text, why it cannot be read)``; the value is None when it cannot be read."""
    p = _git(repo_root, "show", f"{rev}:./{rel}")
    text = None
    if p is not None and p.returncode == 0:
        try:
            text = p.stdout.decode("utf-8")
        except UnicodeDecodeError:
            text = None
    if text is None:
        return None, None, f"git shows no such file at {source}"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        return json.loads(text), sha, None
    except ValueError:
        return None, sha, "it is not JSON"


def _index_rows(index: object) -> dict[str, dict]:
    rows = _dict(index).get("tasks")
    if not isinstance(rows, list):
        return {}
    return {r["task_id"]: r for r in rows if isinstance(r, dict) and isinstance(r.get("task_id"), str)}


def _row_sample(row: dict) -> str:
    """The S9 sample an index row names (``first`` or ``extension``), or ``unknown``."""
    return str(row.get("sample") or "unknown")


def repository_root(tasks_root: Path, manifest: dict) -> Path:
    """The repository that holds a run's tasks and records: from the first manifest entry whose repository-relative
    ``task_dir`` (``evaluate`` records one) names ``tasks_root/<task id>``; else the directory above ``tasks_root``, or
    three above it for ``data/natural/tasks``."""
    root = Path(tasks_root).resolve()
    for t in manifest.get("tasks", []):
        rel = t.get("task_dir")
        if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            continue
        parts, here = Path(rel).parts, (root / t["task_id"]).parts
        if len(here) > len(parts) and here[-len(parts):] == parts:
            return Path(*here[:-len(parts)])
    if root.parts[-3:] == ("data", "natural", "tasks"):
        return root.parents[2]
    return root.parent


def _natural_task_ids(manifest: dict, tasks_root: Path) -> list[str]:
    """The run's natural PR-review tasks, in their number's order."""
    found = []
    for t in manifest.get("tasks", []):
        if load(Path(tasks_root) / t["task_id"] / "task.json", TaskManifest).population == Population.natural_pr_review:
            found.append(t["task_id"])
    return sorted(found, key=_task_order)


def _case_study(index_ok: bool, why: str | None, accepted: int | None, in_run: int | None, new_rules: bool,
                source: str = "the HEAD commit") -> dict:
    """Whether case-study mode (§19.6, §20.3) applies to a natural run, and why: the size rule counts the run's own accepted
    tasks (``in_run``: its families accepted, S11, in the committed index), since each run is reported on its own;
    ``accepted``, the index's accepted tasks over both samples, is kept beside it and decides nothing (``source``: the
    commit the index was read at)."""
    out: dict = {"rule": CASE_STUDY_RULE, "threshold": NATURAL_SIZE_THRESHOLD, "accepted_in_run": in_run,
                 "accepted_in_index": accepted}
    if not new_rules:
        return {**out, "applies": False,
                "why": "the run is analysed under the pilot rules (no result graded with tc-harness/0.3.4 or later, which only a "
                       "test run of natural tasks records: every natural run is graded with tc-harness/0.3.5, §16.1), so its "
                       "tables are the pilot rules'"}
    if not index_ok:
        return {**out, "applies": True,
                "why": f"the committed index ({NATURAL_INDEX} at {source}) cannot be read ({why}), so nothing shows that the "
                       f"run grades {NATURAL_SIZE_THRESHOLD} accepted tasks"}
    if in_run is None or in_run < NATURAL_SIZE_THRESHOLD:
        return {**out, "applies": True,
                "why": f"the run grades {in_run} accepted task(s) of its own (its families accepted, S11, in the committed "
                       f"index), fewer than {NATURAL_SIZE_THRESHOLD}; each run is reported on its own (protocol §20.3)"}
    return {**out, "applies": False,
            "why": f"the run grades {in_run} accepted tasks of its own (its families accepted, S11, in the committed index), at "
                   f"least {NATURAL_SIZE_THRESHOLD}: §15.6 and §15.7 apply in full to the run (protocol §20.3)"}


def _overlay_manifest(path: Path) -> list[tuple[str, str]] | None:
    from .snapshot import manifest

    return manifest(path) if path.is_dir() else None


def _b1_against_norm(task_dir: Path) -> dict:
    """Whether B1 equals D19's regression norm: its overlay's files (the base-test subset at the addressing commit) against
    ``labels/base_tests_overlay`` (the subset at the base), file by file. Equal B1 and norm make a D19-labelled B1 false
    rejection uninformative (the build plan, section 7)."""
    from .snapshot import manifest_sha256

    b1, norm = _overlay_manifest(task_dir / B1_OVERLAY), _overlay_manifest(task_dir / NORM_OVERLAY)
    if b1 is None:
        return {"equal": None, "why": f"no B1 overlay ({B1_OVERLAY})"}
    if norm is None:
        return {"equal": None, "b1_files": len(b1),
                "why": f"no regression-norm overlay ({NORM_OVERLAY}): D19 has not labelled the task"}
    b1_files, norm_files = dict(b1), dict(norm)
    same = sum(norm_files.get(p) == h for p, h in b1_files.items())
    return {"equal": b1_files == norm_files, "identical_files": same, "b1_files": len(b1_files), "norm_files": len(norm_files),
            "b1_overlay_manifest_sha256": manifest_sha256(b1), "norm_overlay_manifest_sha256": manifest_sha256(norm)}


def _labeler_status(task_dir: Path) -> tuple[bool, str | None, dict]:
    """``(usable, why not, the record's status and round)`` of a natural task's labeler, from its ``status.json``."""
    rec = _json_file(task_dir / LABELER_STATUS)
    if not isinstance(rec, dict):
        return False, f"no readable {LABELER_STATUS}", {"status": None}
    status = rec.get("status")
    shown = {"status": status if isinstance(status, str) else None,
             **({"round": rec["round"]} if isinstance(rec.get("round"), int) else {})}
    if status != "usable":
        return False, f"{LABELER_STATUS} records the status {status!r}, not 'usable' (protocol §15.5)", shown
    return True, None, shown


def _registered_specs(task_dir: Path, m: TaskManifest) -> list[VerifierSpec]:
    """The verifier specs a task registers, in ``task.json`` and then in ``verifiers_extra.json`` (as ``evaluate`` adds
    them), each once; a spec that is missing or does not load is left out."""
    specs = []
    for rel in list(m.verifiers) + [x for x in _extra_verifiers(task_dir) if x not in m.verifiers]:
        if not (task_dir / rel).is_file():
            continue
        try:
            specs.append(load(task_dir / rel, VerifierSpec))
        except (OSError, ValueError):
            continue
    return specs


def _labeler_spec(task_dir: Path, m: TaskManifest) -> VerifierSpec | None:
    """The spec of a natural task's independent labeler (verifier ``independent_label``), registered in ``task.json`` or in
    ``verifiers_extra.json`` (as ``evaluate`` adds it); None when there is none, or it does not load."""
    return next((s for s in _registered_specs(task_dir, m) if s.verifier_id == INDEPENDENT_LABELER), None)


AUDITED_CONDITIONS = (VerifierCondition.initial_audited, VerifierCondition.full_audited)  # C2 and C4 (audit:v1, D27)
REFCHECK_STATUSES = ("usable", "unusable")  # D64: the only statuses the reference checks' status record may hold
_FINDING_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")  # an audit finding's code (audit.AuditFinding.code), never its message
CONSTRUCTION_RULE = (f"per family, from its task directory ({NATURAL_DECISION}; the counts of D70): each contract's "
                     "requirements, active ones and scored active ones (the reference contract's also at the correction: its "
                     "correction requirements); the checks of each registered verifier, by condition (the label-support "
                     "verifiers by id); the audit of C2 and C4 from each spec's audit record (whether it passed, its revisions, "
                     "the finding codes of its last iteration; never a finding's message); whether B3 is available (a "
                     f"registered B3 spec, else why not); and the reference checks' status record ({REFCHECK_STATUS}: whether "
                     "a readable record exists, its status, usable or unusable, and its fix rounds, an integer fix_rounds; "
                     "usable is null without a readable record holding one of the two statuses, fix_rounds is null without "
                     "that integer, and why says which). Ids, counts and codes only")


def _contract_counts(c: TaskContract) -> dict:
    active = c.active()
    return {"requirements": len(c.requirements), "active": len(active), "scored_active": sum(r.scored for r in active)}


def _audit_summary(spec: VerifierSpec) -> dict:
    """An audited verifier's audit record in ids, counts and codes (:data:`CONSTRUCTION_RULE`): the finding codes of its
    last iteration are None when the record keeps no history."""
    a = spec.audit
    codes = sorted({f.code for f in a.history[-1].findings if _FINDING_CODE.fullmatch(f.code)}) if a.history else None
    return {"verifier_id": spec.verifier_id, "procedure": a.procedure, "passed": a.passed, "revisions": a.iterations,
            "last_finding_codes": codes}


def _reference_checks_status(task_dir: Path) -> dict:
    """The reference checks' status record (:data:`REFCHECK_STATUS`), which the host writes when they are frozen at P5
    (D64): whether a readable record exists (``recorded``), its status (only usable or unusable is kept) and its fix rounds
    (an integer ``fix_rounds``; null otherwise, and ``why`` says so, since D64 fixes no key for them). Its reasons are free
    text and are not read."""
    rec = _json_file(task_dir / REFCHECK_STATUS)
    if not isinstance(rec, dict):
        return {"recorded": False, "status": None, "usable": None, "fix_rounds": None, "why": f"no readable {REFCHECK_STATUS}"}
    status = rec.get("status") if rec.get("status") in REFCHECK_STATUSES else None
    rounds = rec.get("fix_rounds")
    rounds = rounds if isinstance(rounds, int) and not isinstance(rounds, bool) else None
    why = ([f"{REFCHECK_STATUS} records no status usable or unusable"] if status is None else []) + (
        [f"{REFCHECK_STATUS} records no fix rounds as an integer fix_rounds"] if rounds is None else [])
    return {"recorded": True, "status": status, "usable": None if status is None else status == "usable", "fix_rounds": rounds,
            **({"why": "; ".join(why)} if why else {})}


def _construction(task_dir: Path, m: TaskManifest, ref: TaskContract | None, corrections: list[str]) -> dict:
    """A natural family's construction facts (:data:`CONSTRUCTION_RULE`)."""
    contracts: dict[str, dict] = {}
    for variant, rel in sorted(m.contracts.items()):
        if variant == "reference":
            if ref is not None:
                contracts[variant] = {**_contract_counts(ref), "at_correction": len(corrections)}
        elif (task_dir / rel).is_file():
            contracts[variant] = _contract_counts(load(task_dir / rel, TaskContract))
    specs = _registered_specs(task_dir, m)
    checks = {s.verifier_id if s.condition == VerifierCondition.reference_check else s.condition.value: len(s.checks)
              for s in specs}
    audits = {s.condition.value: _audit_summary(s) for s in specs if s.condition in AUDITED_CONDITIONS and s.audit is not None}
    b3 = [s for s in specs if s.condition == VerifierCondition.diff_derived]
    if b3:
        b3_block: dict = {"available": True, "checks": len(b3[0].checks)}
    else:
        taken_out = any(_dict(_json_file(p)).get("condition") == VerifierCondition.diff_derived.value
                        for p in sorted(task_dir.glob(B3_UNAVAILABLE)))
        b3_block = {"available": False, "taken_out": taken_out,
                    "why": ("its per-test selection kept no test, so it was taken out (unavailable.json; protocol §15.6)"
                            if taken_out else "no B3 verifier is registered")}
    return {"contracts": contracts, "checks": dict(sorted(checks.items())), "audits": dict(sorted(audits.items())),
            "b3": b3_block, "reference_checks": _reference_checks_status(task_dir)}


NO_CORRECTION_REQUIREMENT = ("the reference contract does not observe the correction: none of its scored active requirements "
                             "is introduced at the review comment or a reply, so no near miss targets the correction "
                             f"({NATURAL_DECISION}, decision 14)")


def _natural_context(tasks_root: Path, repo_root: Path, manifest: dict, natural_ids: list[str], new_rules: bool,
                     cands: dict[tuple[str, str], Candidate] | None = None) -> dict:
    """What the sections of a natural PR-review run read: the committed index at the run's code revision
    (:func:`_records_revision`; each family's S11 and sample, the case-study rule on the run's own accepted tasks, the
    run's families against the accepted families of their samples, :data:`INDEX_CHECK_RULE`) and, per natural task, its session's correction events, its reference contract's correction requirements (its
    scored active requirements introduced at the review comment or a reply, as ``contract.correction_event_ids`` and the
    pre-flight read them; D64, decision 14) and the near misses that name one (``cands``: the run's candidates), its S10
    record, its labeler's status and freezing time, and its overlays. ``inputs`` are the hashes of everything read, for
    ``meta.inputs``."""
    from .contract import correction_event_ids
    from .snapshot import manifest_sha256

    records = _records_revision(repo_root, manifest)
    index, index_sha, index_why = _committed_json(repo_root, NATURAL_INDEX, records["revision"], records["source"])
    index_rows = _index_rows(index)
    readable = index_sha is not None and isinstance(_dict(index).get("tasks"), list)
    why = index_why or (None if readable else "it lists no tasks")
    accepted = sorted((t for t, r in index_rows.items() if r.get("s11") is True), key=_task_order) if readable else []
    by_sample = Counter(_row_sample(index_rows[t]) for t in accepted)
    inputs: dict[str, str] = {NATURAL_INDEX: index_sha} if index_sha else {}
    entries = {t["task_id"]: t for t in manifest.get("tasks", [])}
    families: dict[str, dict] = {}
    left_out: dict[str, str] = {}
    corrections: dict[str, list[str]] = {}
    pool = cands or {}
    for tid in natural_ids:
        td = Path(tasks_root) / tid
        m = load(td / "task.json", TaskManifest)
        session = _natural_session(td, repo_root)
        events = correction_event_ids(session) if session is not None else []
        refp = td / m.contracts.get("reference", "contracts/reference.json")
        ref = load(refp, TaskContract) if refp.is_file() else None
        at_correction = [r for r in ref.active() if r.introduced_at in events] if ref is not None else []
        corrections[tid] = [r.req_id for r in at_correction if r.scored]  # D64 decision 14: scored and active
        near = sorted(c.candidate_id for (t, _), c in pool.items()  # the held-out near misses, as the pre-flight counts them
                      if t == tid and c.split.value == "eval" and c.origin == CandidateOrigin.constructed_near_miss)
        on = [cid for cid in near if set(corrections[tid]) & {rid for lb in pool[(tid, cid)].labels
                                                              if lb.labeler_kind == LabelerKind.construction
                                                              for rid in lb.violated_requirements}]
        s10 = _dict(_json_file(td / S10_RECORD))
        b1 = _dict(s10.get("b1"))
        usable, unusable_why, status = _labeler_status(td)
        if not usable:
            left_out[tid] = unusable_why or "not usable"
        spec = _labeler_spec(td, m)
        row = index_rows.get(tid)
        graded = sorted({v["condition"] for v in entries.get(tid, {}).get("verifiers", {}).values()})
        families[tid] = {
            "family_id": m.family_id, "sample": (row or {}).get("sample"), "s11": None if row is None else row.get("s11") is True,
            "session_readable": session is not None,
            "b1": {"available": b1.get("available") if isinstance(b1.get("available"), bool) else None,
                   "n_checks": b1.get("n_checks") if isinstance(b1.get("n_checks"), int) else None,
                   "graded": VerifierCondition.repo_tests.value in graded},
            "b1_equals_regression_norm": _b1_against_norm(td),
            "b3": {"graded": "diff_derived" in graded},
            "labeler": {**status, "usable": usable,
                        "frozen_at": spec.frozen_at if spec is not None and spec.frozen else None},
            "reference_contract": ref is not None,
            "correction_requirements": corrections[tid],
            "unscored_at_correction_events": [r.req_id for r in at_correction if not r.scored],
            "reference_observes_correction": None if ref is None else bool(corrections[tid]),
            "near_misses_on_correction": {"near_misses": len(near), "on_correction": on},
            **({"correction_note": NO_CORRECTION_REQUIREMENT} if ref is not None and not corrections[tid] else {}),
            "construction": _construction(td, m, ref, corrections[tid]),
        }
        for pat in NATURAL_INPUTS:
            for f in sorted(td.glob(pat)):
                if f.is_file():
                    inputs[f"{tid}/{f.relative_to(td).as_posix()}"] = _sha(f)
        for rel in (B1_OVERLAY, NORM_OVERLAY):
            entries_ = _overlay_manifest(td / rel)
            if entries_ is not None:  # a directory by its manifest hash (path in it and sha256 of each file), never by file
                inputs[f"{tid}/{rel}/"] = manifest_sha256(entries_)
    run_ids = set(natural_ids)
    # §20.2: each run grades the accepted families of its sample (natural-pr-v1 the first sample's, natural-pr-v2 the
    # extension's), so the run's families are checked against the accepted families of the samples their rows name.
    samples = sorted({_row_sample(index_rows[t]) for t in natural_ids if t in index_rows}, key=_sample_order) if readable else []
    of_samples = [t for t in accepted if _row_sample(index_rows[t]) in samples]
    in_run = [t for t in accepted if t in run_ids]  # the run's own accepted tasks, which the size rule counts (§20.3)
    check = {"source": f"{NATURAL_INDEX} at {records['source']}", "readable": readable, **({"why": why} if not readable else {}),
             "sha256": index_sha, "rows": len(index_rows) if readable else None,
             "accepted": len(accepted) if readable else None,
             "accepted_by_sample": dict(sorted(by_sample.items(), key=lambda kv: _sample_order(kv[0]))),
             "s11": accepted, "rule": INDEX_CHECK_RULE, "run_samples": samples, "s11_of_run_samples": of_samples,
             "run_families": list(natural_ids),
             "run_families_not_s11": sorted((t for t in natural_ids if t not in set(accepted)), key=_task_order) if readable else [],
             "s11_not_in_run": sorted((t for t in of_samples if t not in run_ids), key=_task_order)}
    check["matches"] = bool(readable and not check["run_families_not_s11"] and not check["s11_not_in_run"])
    return {"tasks": list(natural_ids), "index": check, "index_rows": index_rows if readable else {}, "records": records,
            "case_study": _case_study(readable, why, len(accepted) if readable else None, len(in_run) if readable else None,
                                      new_rules, records["source"]),
            "families": families, "left_out": left_out, "corrections": corrections, "inputs": inputs}


# Reason prefixes that name a step, not a failure: S10 writes "base tests: <failure>" for several distinct failures
# (natural_pr: the subset is empty; natural_env: the base could not be staged, the grader did not complete, the subset
# collects no test), beside "base tests fail to collect", so such a reason's category keeps its failure's clause.
_REASON_SCOPES = ("base tests",)


def _reason_category(reason: object) -> str:
    """A rejection reason's category: its text before the first colon (the index's reasons start with one), or, for a
    reason under a step's prefix (:data:`_REASON_SCOPES`), the prefix with the failure's clause (up to its next colon or
    parenthesis)."""
    if not isinstance(reason, str) or not reason.strip():
        return "no reason recorded"
    head, _, rest = reason.partition(":")
    head = head.strip()
    clause = re.split(r"[:(]", rest, maxsplit=1)[0].strip()
    return f"{head}: {clause}" if head in _REASON_SCOPES and clause else head


def _natural_funnel(repo_root: Path, index_rows: dict[str, dict], records: dict | None = None) -> tuple[dict, dict[str, str]]:
    """The funnel S1 to S11 of both samples, with reasons, from the repository's records as the run's code revision holds
    them (``records``, :func:`_records_revision`; HEAD without it): S1 to S8a (:data:`NATURAL_FUNNEL`), S9 per sample
    (:data:`NATURAL_S9`) and S10 and S11 per sample (the committed index). Returns the funnel and the hashes of the
    records read."""
    rev, source = (records["revision"], records["source"]) if records else ("HEAD", "the HEAD commit")
    hashes: dict[str, str] = {}
    data, sha, why = _committed_json(repo_root, NATURAL_FUNNEL, rev, source)
    if sha:
        hashes[NATURAL_FUNNEL] = sha
    stages = [{"stage": st["id"], "unit": st.get("unit"), "count": st.get("count"), "prs": st.get("prs"),
               "repositories": st.get("repos")}
              for st in (_dict(data).get("stages") or []) if isinstance(st, dict) and st.get("id") in FUNNEL_STAGES]
    funnel: dict = {"rule": "S1 to S8a: the deterministic screen (D48); S9: the model judges per sample (§15.6, §19.2); S10: "
                            "replayability per sample, with each rejection's reason (§15.6, §17); S11: accepted, that is "
                            "passing S10 within the family cap (§16.4); counts only, from the records named",
                    "records": {"S1-S8a": NATURAL_FUNNEL, "S9": dict(NATURAL_S9), "S10-S11": NATURAL_INDEX, "at": source}}
    funnel["stages"] = stages if stages else {"recorded": False, "why": why or f"{NATURAL_FUNNEL} lists no stages"}
    s9: dict[str, dict] = {}
    for sample, rel in NATURAL_S9.items():
        rec, sha, why = _committed_json(repo_root, rel, rev, source)
        if sha:
            hashes[rel] = sha
        summary = _dict(rec).get("summary")
        if not isinstance(summary, dict):
            s9[sample] = {"recorded": False, "why": why or f"{rel} holds no summary"}
            continue
        fams = _dict(summary.get("s11_families")).get("families")
        s9[sample] = {"recorded": True, "comments": summary.get("comments"), "judged": summary.get("judged"),
                      "qualifying": summary.get("qualifying"), "excluded_judges_disagree": summary.get("excluded_judges_disagree"),
                      "failed": summary.get("failed"), "failed_by_reason": dict(sorted(_dict(summary.get("failed_by_reason")).items())),
                      "qualifying_prs": summary.get("qualifying_distinct_prs"),
                      "qualifying_repositories": summary.get("qualifying_distinct_repositories"),
                      "families": fams if isinstance(fams, int) else None}
    funnel["S9"] = s9
    by_sample: dict[str, dict] = {}
    for tid in sorted(index_rows, key=_task_order):
        r = index_rows[tid]
        rec10 = _dict(r.get("s10"))
        outcome = rec10.get("outcome") if isinstance(rec10.get("outcome"), str) else "not recorded"
        d = by_sample.setdefault(str(r.get("sample") or "unknown"), {"rows": 0, "roles": Counter(), "outcomes": Counter(),
                                                                     "rejected": {}, "s11": []})
        d["rows"] += 1
        d["roles"][str(r.get("role") or "unknown")] += 1
        d["outcomes"][outcome] += 1
        if outcome == "rejected":
            d["rejected"][tid] = rec10.get("reason") if isinstance(rec10.get("reason"), str) else None
        if r.get("s11") is True:
            d["s11"].append(tid)
    for d in by_sample.values():
        d["roles"], d["outcomes"] = dict(sorted(d["roles"].items())), dict(sorted(d["outcomes"].items()))
        reasons: dict[str, list[str]] = {}
        for tid, reason in d["rejected"].items():
            reasons.setdefault(_reason_category(reason), []).append(tid)
        d["rejected_by_reason"] = dict(sorted(reasons.items()))
    funnel["S10_S11"] = dict(sorted(by_sample.items(), key=lambda kv: _sample_order(kv[0])))
    funnel["S11"] = {"accepted": sum(len(d["s11"]) for d in by_sample.values()),
                     "by_sample": {s: len(d["s11"]) for s, d in funnel["S10_S11"].items()}}
    return funnel, hashes


def _seconds(start: object, end: object) -> float | None:
    """Seconds from ``start`` to ``end`` (ISO 8601 times with a time zone); None unless both are."""
    a, b = _time(start), _time(end)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds(), 3)


# The infrastructure outcomes of the reliability block: metrics.INFRA without unresolved, which the block counts apart.
INFRASTRUCTURE = frozenset(INFRA) - {"unresolved"}


def _natural_reliability(manifest: dict, tasks_root: Path, natural_ids: list[str], results: list[VerificationResult],
                         cands: dict[tuple[str, str], Candidate]) -> dict:
    """Build and replay reliability per family (§15.6): the S10 record, the reconstruction record, the image ids (the run's
    against snapshot.json and s10.json), the run's sanity grading of the reference and the no-op (every verifier, label
    support included), and the pairs whose repeats disagree (unresolved, §15.3) or that ended in an infrastructure
    outcome."""
    entries = {t["task_id"]: t for t in manifest.get("tasks", [])}
    fams: dict[str, dict] = {}
    n_pairs, n_unresolved = 0, 0
    infra_total: Counter = Counter()
    for tid in natural_ids:
        td = Path(tasks_root) / tid
        m = load(td / "task.json", TaskManifest)
        s10 = _dict(_json_file(td / S10_RECORD))
        env, run10 = _dict(s10.get("environment")), _dict(s10.get("base_test_run"))
        rec = _dict(_json_file(td / "reconstruction_check.json"))
        snap = load(td / (m.snapshot or "snapshot.json"), Snapshot) if (td / (m.snapshot or "snapshot.json")).is_file() else None
        ids = {"run": entries.get(tid, {}).get("image_id"), "snapshot": _dict(snap.environment if snap else None).get("image_id"),
               "s10": env.get("image_id")}
        mine = [r for r in results if r.task_id == tid]
        sanity: dict[str, dict] = {}
        for r in mine:
            c = cands.get((tid, r.candidate_id))
            if c is None or c.origin not in (CandidateOrigin.reference, CandidateOrigin.noop):
                continue
            s = sanity.setdefault(c.origin.value, {}).setdefault(r.verifier_id, {"pass": 0, "n": 0, "outcomes": Counter()})
            s["pass"] += r.outcome.value == "pass"
            s["n"] += 1
            s["outcomes"][r.outcome.value] += 1
        for d in sanity.values():
            for s in d.values():
                s["outcomes"] = dict(sorted(s["outcomes"].items()))
        infra = Counter(r.outcome.value for r in mine if r.outcome.value in INFRASTRUCTURE)
        unresolved = sum(r.outcome.value == "unresolved" for r in mine)
        n_pairs += len(mine)
        n_unresolved += unresolved
        infra_total.update(infra)
        fams[tid] = {
            "s10": {"outcome": s10.get("outcome"), "built_at": s10.get("built_at"), "passed_at": s10.get("passed_at"),
                    "base_tests": {k: run10.get(k) for k in ("passed", "timed_out", "elapsed_s", "harness_version")
                                   if k in run10} | ({"counts": dict(run10["counts"])} if isinstance(run10.get("counts"), dict) else {}),
                    "pins": len(env["pins"]) if isinstance(env.get("pins"), list) else None,
                    "sdist_builds": len(env["sdist_builds"]) if isinstance(env.get("sdist_builds"), list) else None,
                    "wheelhouse_bytes": env.get("wheelhouse_bytes") if isinstance(env.get("wheelhouse_bytes"), int) else None},
            "reconstruction": {"method": rec.get("method"), "status": rec.get("status"), "fidelity": rec.get("fidelity"),
                               "approximations": len(rec["approximations"]) if isinstance(rec.get("approximations"), list) else None},
            "image_id": {**ids, "match": ids["run"] is not None and len(set(ids.values())) == 1},
            "sanity": dict(sorted(sanity.items(), key=lambda kv: kv[0] != CandidateOrigin.reference.value)),
            "pairs": len(mine), "unresolved": unresolved, "infrastructure": dict(sorted(infra.items())),
        }
    return {"rule": "per family: the S10 record, the reconstruction record, the task image's id as the run, snapshot.json and "
                    "s10.json record it, the run's grading of the reference and the no-op by every verifier (label support "
                    "included), and the pairs whose three repeats disagree (unresolved, counted as a rejection, §15.3) or that "
                    "ended in an infrastructure outcome (environment failure, verifier error or timeout; an unresolved pair is "
                    "counted as unresolved only)",
            "families": fams, "run": {"pairs": n_pairs, "unresolved": n_unresolved,
                                      "infrastructure": dict(sorted(infra_total.items()))}}


def _extra_verifiers(task_dir: Path) -> list[str]:
    """The verifier specs of the task's sidecar ``verifiers_extra.json`` (as ``evaluate.extra_verifier_paths`` reads it)."""
    listed = _dict(_json_file(task_dir / "verifiers_extra.json")).get("verifiers")
    return [str(x) for x in listed] if isinstance(listed, list) else []


def _generation_summary(kind: str, artifact: str, rec: GenerationRecord | None) -> dict:
    budget = rec.budget if rec is not None else {}

    def num(key: str) -> int | float | None:
        v = budget.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    return {"kind": kind, "id": artifact, "recorded": rec is not None, "generator": rec.generator if rec else None,
            "turns": num("turns"), "tool_calls": num("tool_calls"), "wall_s": num("wall_s"), "tokens": num("tokens")}


def _s10_span(s10: dict) -> tuple[float | None, str | None]:
    """The seconds a family's S10 record covers, from ``built_at`` to its end (``passed_at``, or ``rejected_at`` for a
    family rejected after its build), and why there are none."""
    outcome = s10.get("outcome")
    end = {"passed": "passed_at", "rejected": "rejected_at"}.get(outcome) if isinstance(outcome, str) else None
    if end is None:
        return None, f"its {S10_RECORD} records no end (outcome {outcome!r})"
    secs = _seconds(s10.get("built_at"), s10.get(end))
    if secs is None:
        return None, f"its {S10_RECORD} records no built_at and {end} with a time zone"
    return secs, None


def _s10_records(tasks_root: Path) -> list[str]:
    """The task directories under ``tasks_root`` that hold an S10 record (``s10.json``, or the ``rejection.json`` of a family
    rejected during the build): every family S10 processed, whether or not the committed index records it yet."""
    root = Path(tasks_root)
    if not root.is_dir():
        return []
    return [d.name for d in root.iterdir() if d.is_dir() and ((d / S10_RECORD).is_file() or (d / S10_REJECTION).is_file())]


def _s10_every_family(tasks_root: Path, natural_ids: list[str], index_rows: dict[str, dict]) -> tuple[dict, dict[str, str]]:
    """S10's time over every family S10 processed, both samples, accepted and rejected (the basis of the fetch log, which
    records every S10 fetch): each family with an S10 record under the tasks root, every family the committed index
    records with an S10 outcome, and the run's families. The time is each ``s10.json``'s span (:func:`_s10_span`). Also
    the families whose time is not recorded, with why (one rejected during the build keeps only its rejection record,
    which holds no start time), those S10 did not build, and those processed whose row in the index records no S10
    outcome (or that have no row): their work is counted, as their fetches are. Returns the block and the hashes of the
    records read outside the run's tasks."""
    hashes: dict[str, str] = {}
    timed: dict[str, float] = {}
    not_recorded: dict[str, str] = {}
    not_built: list[str] = []
    processed: list[str] = []
    outside: list[str] = []
    for tid in sorted(set(index_rows) | set(natural_ids) | set(_s10_records(tasks_root)), key=_task_order):
        td = Path(tasks_root) / tid
        outcome = _dict(index_rows.get(tid, {}).get("s10")).get("outcome")
        recorded = (td / S10_RECORD).is_file() or (td / S10_REJECTION).is_file()
        if not recorded and outcome not in ("passed", "rejected") and tid not in natural_ids:
            not_built.append(tid)
            continue
        processed.append(tid)
        if recorded and outcome not in ("passed", "rejected"):
            outside.append(tid)
        if (td / S10_RECORD).is_file():
            if tid not in natural_ids:  # the run's own tasks are hashed with their other inputs (NATURAL_INPUTS)
                hashes[f"{tid}/{S10_RECORD}"] = _sha(td / S10_RECORD)
            secs, why = _s10_span(_dict(_json_file(td / S10_RECORD)))
            if secs is None:
                not_recorded[tid] = why or "no time"
            else:
                timed[tid] = secs
        elif (td / S10_REJECTION).is_file():
            hashes[f"{tid}/{S10_REJECTION}"] = _sha(td / S10_REJECTION)
            not_recorded[tid] = (f"rejected during the build: its task directory keeps only {S10_REJECTION}, which records "
                                 "the rejection's time and no start")
        else:
            not_recorded[tid] = f"no {S10_RECORD} under the tasks root"
    return ({"rule": S10_EVERY_FAMILY_RULE, "processed": processed, "n_processed": len(processed), "families": timed,
             "n_families": len(timed), "total_seconds": round(sum(timed.values()), 3) if timed else None,
             "not_recorded": not_recorded, "not_built": not_built, "processed_not_in_index": outside}, hashes)


S10_EVERY_FAMILY_RULE = ("every family S10 processed, both samples, accepted and rejected: a family with an S10 record "
                         f"({S10_RECORD}, or the {S10_REJECTION} of a family rejected during the build) under the tasks root, "
                         "or one the committed index records with an S10 outcome; its time runs from built_at to passed_at or "
                         "rejected_at. processed_not_in_index: families with an S10 record whose row in the committed index "
                         "records no S10 outcome (or that have no row), whose work is counted as their fetches are")


def _natural_cost(tasks_root: Path, repo_root: Path, natural_ids: list[str], index_rows: dict[str, dict],
                  results: list[VerificationResult]) -> tuple[dict, dict[str, str]]:
    """Cost and time per accepted task (§15.6): per family, the generation records of every generated artifact (contracts,
    verifiers other than B1, constructed candidates), the S10 record's times, the S10 fetch log's bytes of the family's
    repository and the run's grading time; their totals over the run's families, and each total divided by their number.
    S10's cost per accepted task counts time and fetches on one basis, every family S10 processed, both samples,
    rejected ones included (``s10_every_family``; every S10 fetch of the log, with its bytes and seconds), divided by
    the same number; the run's families' own S10 time is also given (``s10_seconds_run_families``). What no record
    counts is listed (``unrecorded``). Returns the block and the hashes of the fetch log and of the S10 records read
    outside the run's tasks."""
    hashes: dict[str, str] = {}
    log = Path(repo_root) / NATURAL_FETCH_LOG
    fetch: dict[int, int] = {}
    fetch_seconds, untimed_fetches = 0.0, 0
    fetch_ok = log.is_file()
    if fetch_ok:
        hashes[NATURAL_FETCH_LOG] = _sha(log)
        for line in jsonl_lines(log.read_text(encoding="utf-8")):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("stage") == "S10" and isinstance(e.get("repo_id"), int) and isinstance(e.get("delta"), int):
                fetch[e["repo_id"]] = fetch.get(e["repo_id"], 0) + e["delta"]
                secs = e.get("seconds")
                if isinstance(secs, (int, float)) and not isinstance(secs, bool):
                    fetch_seconds += secs
                else:
                    untimed_fetches += 1
    keys = ("turns", "tool_calls", "wall_s", "tokens")
    fams: dict[str, dict] = {}
    for tid in natural_ids:
        td = Path(tasks_root) / tid
        m = load(td / "task.json", TaskManifest)
        arts = []
        for variant, rel in sorted(m.contracts.items()):
            if (td / rel).is_file():
                arts.append(_generation_summary("contract", variant, load(td / rel, TaskContract).generation))
        for rel in list(m.verifiers) + [x for x in _extra_verifiers(td) if x not in m.verifiers]:
            if (td / rel).is_file():
                spec = load(td / rel, VerifierSpec)
                if spec.condition != VerifierCondition.repo_tests:  # B1 is the repository's own tests, not generated
                    arts.append(_generation_summary("verifier", spec.verifier_id, spec.generation))
        for rel in m.candidates:
            c = load(td / rel, Candidate)
            if c.origin in CONSTRUCTED_ORIGINS:
                arts.append(_generation_summary("candidate", c.candidate_id, c.generation))
        recorded = [a for a in arts if a["recorded"]]
        sums: dict[str, float | int | None] = {}
        for k in keys:
            vals = [a[k] for a in recorded]
            sums[k] = None if not recorded or any(v is None for v in vals) else round(sum(vals), 3)
        s10 = _dict(_json_file(td / S10_RECORD))
        repo_id = index_rows.get(tid, {}).get("repo_id")
        shared = sorted((t for t in natural_ids if t != tid and index_rows.get(t, {}).get("repo_id") == repo_id
                         and repo_id is not None), key=_task_order)
        fams[tid] = {
            "artifacts": len(arts), "recorded": len(recorded), "unrecorded": [f"{a['kind']} {a['id']}" for a in arts if not a["recorded"]],
            "by_generator": dict(sorted(Counter(a["generator"] for a in recorded).items())), **sums,
            "s10_seconds": _s10_span(s10)[0],
            "s10_base_tests_seconds": _dict(s10.get("base_test_run")).get("elapsed_s"),
            "fetch_bytes": fetch.get(repo_id) if fetch_ok and isinstance(repo_id, int) else None,
            **({"fetch_repository_shared_with": shared} if shared else {}),
            "grading_wall_s": round(sum(r.wall_s for r in results if r.task_id == tid), 3),
        }
    every, every_hashes = _s10_every_family(tasks_root, natural_ids, index_rows)
    hashes.update(every_hashes)
    n = len(natural_ids)
    totals: dict[str, float | int | None] = {}
    for k in (*keys, "grading_wall_s"):
        vals = [f[k] for f in fams.values()]
        totals[k] = None if not vals or any(v is None for v in vals) else round(sum(vals), 3)
    # S10, on one basis: every family S10 processed (its build time, and every S10 fetch with its bytes and seconds) ...
    totals["s10_seconds_every_family"] = every["total_seconds"]
    totals["fetch_bytes_all_s10"] = sum(fetch.values()) if fetch_ok else None
    totals["fetch_seconds_all_s10"] = round(fetch_seconds, 3) if fetch_ok else None
    # ... and the run's families alone: their own S10 time, and the fetches of their repositories.
    own = [f["s10_seconds"] for f in fams.values()]
    totals["s10_seconds_run_families"] = None if not own or any(v is None for v in own) else round(sum(own), 3)
    repos: set[int] = {r for r in (index_rows.get(t, {}).get("repo_id") for t in natural_ids) if isinstance(r, int)}
    totals["fetch_bytes_of_the_run_repositories"] = sum(fetch.get(r, 0) for r in repos) if fetch_ok else None
    per = {k: (None if v is None or not n else round(v / n, 3)) for k, v in totals.items()}
    untimed: dict[str, list[str]] = {}
    for tid, why in every["not_recorded"].items():
        untimed.setdefault(why, []).append(tid)
    return ({"rule": COST_RULE, "fetch_log": NATURAL_FETCH_LOG if fetch_ok else None, "families": fams, "n_families": n,
             "s10_every_family": every, "totals": totals, "per_accepted_task": per,
             "unrecorded": list(UNRECORDED_COST)
             + [f"the S10 time of {', '.join(ids)}, left out of the S10 time of every processed family: {why}"
                for why, ids in untimed.items()]
             + ([f"the time of {untimed_fetches} S10 fetch(es) of the log, which record no seconds (their bytes are counted)"]
                if untimed_fetches else [])
             + ([] if fetch_ok else [(f"the S10 fetch log ({NATURAL_FETCH_LOG}) is not in this checkout, so no S10 fetch "
                                      "is counted")])},
            hashes)


COST_RULE = ("per family: the generation records of its generated artifacts (contracts, verifiers other than B1, constructed "
             "candidates; a combined record sums its runs), its S10 record's time from built_at to passed_at and its base-test "
             "run, the S10 fetch log's bytes of the family's repository (a repository's fetches include those made for any "
             "family of it) and the run's grading time (the sum of each pair's wall time); the totals over the run's families, "
             "and each total divided by their number (per accepted task, when the run grades every accepted family of its "
             "sample: see the index check); a total is n/a when a family lacks the value. S10's cost per accepted task counts its time and its "
             "fetches on one basis, the S10 work of every family S10 processed, both samples, rejected families included "
             "(s10_every_family: the time from built_at to passed_at or rejected_at; every S10 fetch in the log, its bytes and "
             "seconds), divided by the same number; the run's families' own S10 time (s10_seconds_run_families) and their "
             "repositories' fetches are given beside it")


SENSITIVITY_RULE = ("protocol §18.1: the primary analysis (analysis.json, analysis.md) excludes the fresh attempts that the "
                    "reviewed audit verdicts exclude; this sensitivity analysis also excludes every attempt listed in the files "
                    "below (an audit report's 'excluded' list holds every attempt that the automated audit flagged, before the "
                    "manual review) and recomputes every table with them excluded. It is not the primary analysis")


def _source_name(path: Path, root: Path) -> str:
    """How an input file is named in the output: relative to the repository ``root`` if it lies in it, else by its name."""
    p = Path(path).resolve()
    try:
        return p.relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.name


def read_sensitivity_exclusions(paths: Sequence[Path], root: Path) -> tuple[list[dict], dict[str, str]]:
    """The fresh attempts that the sensitivity view (protocol §18.1) excludes as well, read from the files ``paths``.

    Each file is an audit report with an ``excluded`` list of attempt ids (the fresh-attempt audit's report, whose
    ``excluded`` list holds every attempt its automated pass flagged), or a JSON list of attempt ids. Returns the
    sources (file, sha256, kind, ids) and ``{attempt id: reason}``, the reason naming the files that list it. A file
    that cannot be read as JSON, has neither form, or lists something other than attempt ids (non-empty strings
    without whitespace) is refused (:class:`SensitivityExclusionsError`). A file inside the repository ``root`` is
    named relative to it, any other by its name, so no local path is recorded.
    """
    sources: list[dict] = []
    listed_in: dict[str, list[str]] = {}
    for path in paths:
        name = _source_name(Path(path), root)
        try:
            raw = Path(path).read_bytes()
            data = json.loads(raw)
        except (OSError, ValueError) as exc:
            raise SensitivityExclusionsError(f"{name}: cannot be read as JSON ({type(exc).__name__}: {exc})") from None
        if isinstance(data, list):
            ids, kind = data, "a JSON list of attempt ids"
        elif isinstance(data, dict) and isinstance(data.get("excluded"), list):
            ids, kind = data["excluded"], "an audit report ('excluded' list)"
        else:
            raise SensitivityExclusionsError(f"{name}: neither a JSON list of attempt ids nor an audit report with an "
                                             "'excluded' list of attempt ids")
        bad = [x for x in ids if not isinstance(x, str) or not x or any(ch.isspace() for ch in x)]
        if bad:
            raise SensitivityExclusionsError(f"{name}: {len(bad)} listed entr{'y is' if len(bad) == 1 else 'ies are'} not an "
                                             f"attempt id (a non-empty string without whitespace), e.g. {bad[0]!r}")
        ids = list(dict.fromkeys(ids))
        sources.append({"file": name, "sha256": hashlib.sha256(raw).hexdigest(), "kind": kind, "ids": ids})
        for x in ids:
            listed_in.setdefault(x, [])
            if name not in listed_in[x]:
                listed_in[x].append(name)
    return sources, {x: f"sensitivity analysis only (protocol §18.1): listed in {', '.join(fs)}" for x, fs in listed_in.items()}


def analyze(run_dir: Path, tasks_root: Path, *, allow_proposed: bool = False, n_boot: int = 2000,
            exclude_origins: tuple[str, ...] = ("reference", "noop"), pool_populations: bool = False,
            rules: str | None = None, sensitivity_exclusions: Sequence[Path] = (), repo_root: Path | None = None) -> dict:
    """Analyse a recorded run; write ``analysis.json`` and ``analysis.md`` into its directory and return the analysis.

    ``tasks_root`` holds the run's task directories (``tasks/``, or ``data/natural/tasks`` for the natural arm).
    ``repo_root``: the repository whose records the analysis reads (the natural index and screening records, as the
    run's code revision holds them, else as its HEAD commit does: :func:`_records_revision`; the S10 fetch log); by
    default :func:`repository_root` finds it from the run's manifest.

    ``rules``: ``pilot`` (the pre-specified analysis of the recorded runs) or ``v0.8`` (the reporting
    rules of new runs; see the module docstring). By default :func:`reporting_rules` picks them from
    the harness versions of the run's results.

    ``sensitivity_exclusions`` (files read by :func:`read_sensitivity_exclusions`; protocol §18.1): the main
    analysis is written as usual, and so are ``analysis_sensitivity.json`` and ``analysis_sensitivity.md``,
    which recompute every table with the fresh attempts those files list excluded as well. Both analyses
    are computed before anything is written, so a refusal writes neither.
    """
    if rules is not None and rules not in REPORTING_RULES:
        raise ValueError(f"unknown reporting rules {rules!r}; expected one of {', '.join(REPORTING_RULES)}")
    tasks_root = Path(tasks_root)
    root = Path(repo_root) if repo_root is not None else repository_root(
        tasks_root, json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8")))
    sources, also = read_sensitivity_exclusions(sensitivity_exclusions, root) if sensitivity_exclusions else ([], {})

    def compute(also_exclude: dict[str, str] | None) -> dict:
        return _analysis(run_dir, tasks_root, allow_proposed=allow_proposed, n_boot=n_boot, exclude_origins=exclude_origins,
                         pool_populations=pool_populations, rules=rules, also_exclude=also_exclude, repo_root=root)

    out = compute(None)
    sens = compute(also) if sensitivity_exclusions else None
    write_json(out, run_dir / "analysis.json")
    (run_dir / "analysis.md").write_text(to_markdown(out), encoding="utf-8")
    if sens is not None:
        sens["meta"]["sensitivity"].update(rule=SENSITIVITY_RULE, primary_analysis="analysis.json",
                                           primary_analysis_sha256=_sha(run_dir / "analysis.json"), sources=sources)
        write_json(sens, run_dir / SENSITIVITY_JSON)
        (run_dir / SENSITIVITY_MD).write_text(to_markdown(sens), encoding="utf-8")
    return out


def _analysis(run_dir: Path, tasks_root: Path, *, allow_proposed: bool, n_boot: int, exclude_origins: tuple[str, ...],
              pool_populations: bool, rules: str | None, also_exclude: dict[str, str] | None = None,
              repo_root: Path | None = None) -> dict:
    """The analysis of a recorded run (see :func:`analyze`), written nowhere.

    ``also_exclude`` (``{attempt id: reason}``) makes it the sensitivity view: those fresh attempts are excluded
    as well, from every table, and ``meta.sensitivity`` says which were excluded here, which the primary
    analysis excludes already, and which listed ids name no attempt of the run.

    A run with a natural PR-review task also gets the natural sections (module docstring), and in case-study mode
    (§19.6) the per-family analysis of :func:`_case_study_analysis` instead of the pooled tables.
    """
    cands: dict[tuple[str, str], Candidate] = {}
    excluded: dict[tuple[str, str], str] = {}
    support: dict[tuple[str, str], dict[str, str]] = {}
    rows, meta = build_rows(run_dir, tasks_root, allow_proposed=allow_proposed, candidates=cands, excluded=excluded,
                            also_exclude=also_exclude, support=support)
    if also_exclude is not None:
        matched: set[str] = set()
        here: list[dict] = []
        before: list[dict] = []
        for (t, cid), why in sorted(excluded.items()):
            rec = cands[(t, cid)].attempt
            if rec is None or rec.attempt_id not in also_exclude:
                continue
            matched.add(rec.attempt_id)
            entry = {"task_id": t, "candidate_id": cid, "attempt_id": rec.attempt_id}
            if why == also_exclude[rec.attempt_id]:
                here.append(entry)
            else:
                before.append({**entry, "reason": why})
        meta["sensitivity"] = {"excluded_here": here, "already_excluded": before,
                               "not_in_run": sorted(set(also_exclude) - matched)}
    populations = _populations(rows)
    if len(populations) > 1 and not pool_populations:  # refused before anything is written
        raise MixedPopulations(f"the run mixes {len(populations)} populations ({_describe(populations)}), and populations are "
                               "never pooled silently: pass pool_populations (--pool-populations) to pool them and report "
                               "each population separately, or evaluate each population in a run of its own")
    default_rules, basis = reporting_rules(meta["harness_versions"])
    if rules is not None and rules != default_rules:
        basis = f"asked for; by default this run would get the {default_rules} rules, since {basis}"
    new_rules = (rules or default_rules) == NEW_RUN_RULES
    manifest = json.loads((run_dir / "manifest.json").read_text())
    natural_ids = _natural_task_ids(manifest, tasks_root)
    if len(natural_ids) != len(manifest.get("tasks", [])):  # the natural arm's run grades natural PR-review tasks alone (§15.2)
        natural_ids = []
    if natural_ids and not new_rules and default_rules == NEW_RUN_RULES:  # refused before anything is written
        raise NaturalRunError(f"the pilot rules were asked for a run with natural PR-review tasks ({', '.join(natural_ids)}) that "
                              "was graded with tc-harness/0.3.4 or later; the pilot rules are the pre-specified analysis of the "
                              "recorded pilot runs, and a natural run is reported under §15.7 and §19.6")
    root = Path(repo_root) if repo_root is not None else repository_root(tasks_root, manifest)
    nat = _natural_context(tasks_root, root, manifest, natural_ids, new_rules, cands) if natural_ids else None
    # B3 is secondary in a natural run under the reporting rules of new runs (§15.6); elsewhere it is reported as before.
    secondary = SECONDARY_CONDITIONS if nat is not None and new_rules else ()
    # The reference solution is development data for every generator (it is shown to
    # them) and the no-op is a sanity check; both are reported separately and excluded
    # from the primary FA/FR (pre-specified in experiments/protocol.md).
    every = [r for r in rows if r.origin not in exclude_origins]  # every held-out candidate's rows
    keys = {k: _patch_key(cands[k]) for k in {(r.task_id, r.candidate_id) for r in every}} if new_rules else {}
    prepare: Callable[[list[Row]], list[Row]] = (lambda rs: distinct_patch_rows(rs, keys)[0]) if new_rules else list
    primary = prepare(every)  # the rows counted: for a new run, each distinct graded patch once
    # The evaluated conditions only: a label-support verifier is never one (its results are not rows, build_rows).
    conds = [c for c in CONDITION_ORDER if c != LABEL_SUPPORT_CONDITION and any(r.condition == c for r in rows)]
    tasks = sorted({r.task_id for r in rows})
    # Population and stratum keys only where they say something (see the module docstring).
    with_populations = any(p != DEFAULT_POPULATION for p in populations)
    found = {t: f for t, f in _stratum_candidates(run_dir, tasks_root).items() if t in tasks}
    with_strata = any(r.stratum != TASK_STRATUM for r in rows) or any((t, cid) in excluded for t, f in found.items() for cid in f)
    if nat is not None and nat["case_study"]["applies"]:  # §19.6: per-family tables only, built from the rows
        return _case_study_analysis(
            run_dir, tasks_root, root, meta=meta, basis=basis, rows=rows, every=every, primary=primary, conds=conds,
            prepare=prepare, keys=keys, cands=cands, excluded=excluded, support=support, exclude_origins=exclude_origins,
            allow_proposed=allow_proposed, also_exclude=also_exclude, nat=nat, tasks=tasks, populations=populations,
            with_populations=with_populations, with_strata=with_strata, found=found, manifest=manifest)
    out: dict = {"meta": meta, "conditions": {}, "comparisons": [], "sanity": {}, "by_negative_type": {},
                 "outcome_counts": {}, "per_task": {}}
    for c in conds:
        s = summarize(primary, condition=c, n_boot=n_boot)
        sx = summarize(primary, condition=c, exclude_infra=True, n_boot=n_boot)
        out["conditions"][c] = {
            **_condition_rates(s),
            "per_task_rates": {t: {"fa_num": v["fa"].num, "fa_den": v["fa"].den, "fr_num": v["fr"].num, "fr_den": v["fr"].den}
                               for t, v in s.per_task.items()},
            "sensitivity_excluding_infra": {"fa": sx.fa.value, "fa_den": sx.fa.den, "fr": sx.fr.value, "fr_den": sx.fr.den},
        }
        fa_v, fr_v = s.fa.value, s.fr.value
        out["conditions"][c]["youden_j"] = None if fa_v is None or fr_v is None else (1 - fr_v) - fa_v
        if new_rules:  # the intervals above resample this condition's families
            out["conditions"][c]["ci95_not_inferential"] = (
                len({r.family_id for r in primary if r.condition == c}) < MIN_INFERENTIAL_FAMILIES)
        tasks_c = sorted({r.task_id for r in primary if r.condition == c})
        any_neg = [any(r.outcome == "pass" for r in primary if r.condition == c and r.task_id == t and r.label == "invalid")
                   for t in tasks_c if any(r.label == "invalid" for r in primary if r.condition == c and r.task_id == t)]
        out["conditions"][c]["tasks_with_any_accepted_negative"] = {"num": sum(any_neg), "den": len(any_neg)}
        out["outcome_counts"][c] = dict(Counter(r.outcome for r in rows if r.condition == c))
        for nt in ("correction_violating", "initial_violating", "unspecified"):
            sub = [r for r in primary if r.condition == c and r.negative_type == nt]
            if sub:
                acc = sum(r.outcome == "pass" for r in sub)
                out["by_negative_type"].setdefault(c, {})[nt] = {"accepted": acc, "n": len(sub)}
        sanity = {}
        for origin in exclude_origins:
            sub = [r for r in rows if r.condition == c and r.origin == origin]
            if sub:
                sanity[origin] = {"pass": sum(r.outcome == "pass" for r in sub), "n": len(sub),
                                  "outcomes": dict(Counter(r.outcome for r in sub))}
        out["sanity"][c] = sanity
    for a, b, desc in COMPARISONS + B3_COMPARISONS:
        if a in conds and b in conds:
            for metric in ("fa", "fr"):
                d = paired_difference(primary, a, b, metric, n_boot=n_boot)
                d["description"] = desc
                if new_rules:
                    d.update(paired_signflip(primary, a, b, metric))
                    d["ci95_not_inferential"] = d["n_families"] < MIN_INFERENTIAL_FAMILIES
                out["comparisons"].append(d)
    for t in tasks:
        out["per_task"][t] = {}
        for c in conds:
            sub = [r for r in every if r.task_id == t and r.condition == c]
            out["per_task"][t][c] = [{"candidate": r.candidate_id, "origin": r.origin, "label": r.label,
                                      "negative_type": r.negative_type, "outcome": r.outcome,
                                      **({"stratum": r.stratum} if with_strata else {})} for r in sub]
    out["n_tasks"] = len(tasks)
    out["n_families"] = len({r.family_id for r in rows})
    if with_populations:
        out["meta"]["populations"] = populations
    if len(populations) > 1:
        out["meta"]["population_pooling"] = (f"pooled across {len(populations)} populations ({_describe(populations)}) "
                                             "with --pool-populations; by_population reports each population separately")
        out["by_population"] = _by_group(every, conds, "population", n_boot, prepare)
    stratum_cands = found if with_strata else {}
    if with_strata:
        manifest = json.loads((run_dir / "manifest.json").read_text())
        out["meta"]["strata"] = {t["task_id"]: t["strata"] for t in manifest["tasks"] if t.get("strata") and t["task_id"] in tasks}
        out["by_stratum"] = _by_group(every, conds, "stratum", n_boot, prepare)
    if allow_proposed:
        # Exploratory (not pre-specified): constructed candidates labeled by construction intent.
        srows, _ = build_rows(run_dir, tasks_root, allow_proposed=True, policy="construction", also_exclude=also_exclude)
        sprim = prepare([r for r in srows if r.origin not in exclude_origins])
        out["sensitivity_construction_labels"] = {}
        for c in conds:
            ss = summarize(sprim, condition=c, n_boot=n_boot)
            out["sensitivity_construction_labels"][c] = {
                "fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den, "fa_ci95": ss.fa_ci,
                "fa_exact95": ss.fa_exact, "fa_ci95_degenerate": ss.fa_ci_degenerate,
                "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den, "fr_ci95": ss.fr_ci,
                "fr_exact95": ss.fr_exact, "fr_ci95_degenerate": ss.fr_ci_degenerate}
    kept_cands = {t: {cid: v for cid, v in f.items() if (t, cid) not in excluded} for t, f in stratum_cands.items()}
    if allow_proposed:
        out.update(_post_hoc(run_dir, tasks_root, rows, primary, conds, n_boot, exclude_origins,
                             {t: [c for _, _, c in f.values()] for t, f in kept_cands.items()}, prepare, also_exclude))
    if new_rules:
        out["meta"]["reporting_rules"] = {"rules": NEW_RUN_RULES, "basis": basis,
                                          "protocol": "experiments/protocol.md v0.7 §15.7 and v0.8 §16.6"}
        out["meta"]["bootstrap"] = {"n_families": out["n_families"],
                                    "inferential": out["n_families"] >= MIN_INFERENTIAL_FAMILIES,
                                    "rule": f"cluster-bootstrap intervals over fewer than {MIN_INFERENTIAL_FAMILIES} task families "
                                            "are not inferential; they are reported in an appendix (protocol §15.7)"}
        out["per_family"] = {c: family_rates(primary, condition=c) for c in conds}
        out["distinct_patches"] = {"rule": "held-out candidates of a task with the same graded patch count once; the "
                                           "representative is the natural state, else the first id (protocol §15.4, §15.7)",
                                   "n_heldout": len({(r.task_id, r.candidate_id) for r in every}),
                                   "n_distinct": len({(r.task_id, r.candidate_id) for r in primary}),
                                   "groups": distinct_patch_rows(every, keys)[1]}
        out["sensitivity_every_candidate"] = {c: _pooled(family_rates(every, condition=c)) for c in conds}
        out["oracle_gated"] = _oracle_gated(rows, primary, conds)
    second = _independent_labeling(rows, every, support, cands, conds, prepare, keys, with_strata, meta["label_rule"],
                                   exclude_origins, natural=nat)
    fresh = _fresh_attempts(rows, cands, excluded, conds,
                            None if second is None else {k: independent_label(v.get(INDEPENDENT_LABELER))
                                                         for k, v in support.items()})
    if fresh is not None:
        out["fresh_attempts"] = fresh
    source = _source_evidence(rows, cands, conds)
    if nat is not None:
        source = _natural_source_evidence(source, rows, cands, conds, secondary, nat, second, support, new_rules=new_rules,
                                          case_study=False)
    if source is not None:
        out["source_evidence"] = source
    if second is not None:  # only for a run that graded the independent labeler
        out["independent_labeling"] = second
    by_name: dict[str, dict[str, list[Candidate]]] = {}  # {task: {stratum: candidates}}
    for t, f in kept_cands.items():
        for name, _, c in f.values():
            by_name.setdefault(t, {}).setdefault(name, []).append(c)
    out["labels"] = label_summary([tasks_root / t for t in tasks], strata=by_name, natural=nat is not None)
    out["coverage"] = {t: contract_coverage(tasks_root / t) for t in tasks}
    out["mapping_agreement"] = {t: mapping_agreement(tasks_root / t) for t in tasks}
    natural_inputs: dict[str, str] = {}
    if nat is not None:  # only for a run with a natural PR-review task, so the recorded runs keep their output
        out["meta"]["case_study"] = nat["case_study"]
        if secondary:
            out["meta"]["secondary_conditions"] = {"conditions": list(secondary), "rule": SECONDARY_RULE}
            _split_secondary(out, secondary)
        if new_rules:  # with 10 or more accepted tasks (case-study mode returned above): D64, decision 10
            out["repository_clustered"] = _repository_clustered(primary, rows, cands, conds, secondary, nat)
        out["natural"], natural_inputs = _natural_block(run_dir, tasks_root, root, manifest, nat, cands)
    out["meta"]["inputs"] = _input_hashes(run_dir, [tasks_root / t for t in tasks],
                                          [(tasks_root / t, rel) for t, f in stratum_cands.items() for _, rel, _ in f.values()],
                                          (("stats.py",) if new_rules else ()) + (NATURAL_CODE if nat is not None else ()),
                                          extra_files=natural_inputs)
    return out


def _split_secondary(out: dict, secondary: tuple[str, ...]) -> None:
    """Move the secondary conditions' (B3's) pooled rates, per-family table and comparisons from the primary tables of
    ``out`` to ``out["secondary"]``, so they stay out of the primary display and its null tally (§15.6); the oracle-gated
    view's B3 comparisons likewise go to its ``secondary_comparisons``."""
    sec = [c for c in out["conditions"] if c in secondary]
    if not sec:
        return

    def is_sec(d: dict) -> bool:
        return d["a"] in secondary or d["b"] in secondary

    out["secondary"] = {"rule": SECONDARY_RULE, "conditions": {c: out["conditions"].pop(c) for c in sec},
                        "per_family": {c: out["per_family"].pop(c) for c in sec if c in out.get("per_family", {})},
                        "comparisons": [d for d in out["comparisons"] if is_sec(d)]}
    out["comparisons"] = [d for d in out["comparisons"] if not is_sec(d)]
    og = out.get("oracle_gated")
    if og:
        og["secondary_comparisons"] = [d for d in og["comparisons"] if is_sec(d)]
        og["comparisons"] = [d for d in og["comparisons"] if not is_sec(d)]


REPOSITORY_RULE = (f"exploratory, not pre-specified ({NATURAL_DECISION}, decision 10): the sign-flip tests over task families treat "
                   "the families of one repository as independent; here the families of each repository (the repository ids of "
                   "the committed index, which are not shown: a cluster is named by its families) form one cluster, and the "
                   "primary paired comparisons are tested over clusters, under D19 and under the source-evidence labels, each "
                   "distinct graded patch once. B3 is left out (secondary). Reported only outside case-study mode (§19.6), with "
                   f"{NATURAL_SIZE_THRESHOLD} or more accepted tasks")


def _repository_clusters(nat: dict) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """The natural run's families grouped by repository (``repo_id`` of the committed index): each task's cluster, each
    cluster's tasks (a cluster is named by its tasks, joined by ``+``, in their order), and the tasks without a
    repository id in the index (each its own cluster)."""
    by_repo: dict[int, list[str]] = defaultdict(list)
    alone: list[str] = []
    for t in nat["tasks"]:
        rid = nat["index_rows"].get(t, {}).get("repo_id")
        if isinstance(rid, int) and not isinstance(rid, bool):
            by_repo[rid].append(t)
        else:
            alone.append(t)
    groups = sorted([sorted(ts, key=_task_order) for ts in by_repo.values()] + [[t] for t in alone],
                    key=lambda g: _task_order(g[0]))
    clusters = {"+".join(g): g for g in groups}
    return {t: name for name, g in clusters.items() for t in g}, clusters, sorted(alone, key=_task_order)


def _repository_clustered(primary: list[Row], rows: list[Row], cands: dict[tuple[str, str], Candidate], conds: list[str],
                          secondary: tuple[str, ...], nat: dict) -> dict:
    """The exploratory view clustered by repository (:data:`REPOSITORY_RULE`): per cluster, FA and FR under D19 (each
    distinct graded patch once); the primary paired comparisons (:data:`COMPARISONS`) with exact sign-flip p-values over
    clusters, under D19 and under the source-evidence labels."""
    of, clusters, alone = _repository_clusters(nat)
    prim = [c for c in conds if c not in secondary]

    def regroup(rs: list[Row]) -> list[Row]:
        return [replace(r, family_id=of.get(r.task_id, r.family_id)) for r in rs]

    crows, se = regroup(primary), regroup(_source_rows(rows, cands))
    comparisons = []
    for a, b, desc in COMPARISONS:
        if a in prim and b in prim:
            for metric in ("fa", "fr"):
                d = paired_difference(crows, a, b, metric, n_boot=0)
                comparisons.append({"a": a, "b": b, "metric": metric, "description": desc, "difference": d["difference"],
                                    "n_metric": d["n_metric"], "discordant": d["discordant"], **paired_signflip(crows, a, b, metric)})
    return {"rule": REPOSITORY_RULE, "exploratory": True, "clusters": clusters,
            "shared": [name for name, g in clusters.items() if len(g) > 1],
            **({"no_repository_id": alone} if alone else {}),
            "per_cluster": {c: family_rates(crows, condition=c) for c in prim},
            "comparisons": comparisons,
            "source_evidence_comparisons": _source_comparisons(se, prim) if se else []}


def _natural_block(run_dir: Path, tasks_root: Path, repo_root: Path, manifest: dict, nat: dict,
                   cands: dict[tuple[str, str], Candidate]) -> tuple[dict, dict[str, str]]:
    """The ``natural`` section of a natural PR-review run and the hashes of the records it read (for ``meta.inputs``):
    the index check, the per-family flags, the funnel, reliability and cost."""
    results = read_jsonl(run_dir / "results.jsonl", VerificationResult)
    funnel, funnel_inputs = _natural_funnel(repo_root, nat["index_rows"], nat["records"])
    cost, cost_inputs = _natural_cost(tasks_root, repo_root, nat["tasks"], nat["index_rows"], results)
    block = {"rule": NATURAL_RULE, "construction_rule": CONSTRUCTION_RULE, "d19_rule": D19_RULE, "decision": NATURAL_DECISION,
             "tasks": nat["tasks"], "records": nat["records"], "index": nat["index"], "families": nat["families"], "funnel": funnel,
             "reliability": _natural_reliability(manifest, tasks_root, nat["tasks"], results, cands), "cost": cost}
    return block, {**nat["inputs"], **funnel_inputs, **cost_inputs}


CASE_STUDY_OMITTED = ("every pooled rate with its exact and bootstrap intervals (conditions is empty), every paired comparison "
                      "with its p-values (comparisons is empty), the bootstrap appendix, and every pooled sensitivity table; "
                      "each is given per family instead")


def _per_family_counts(rows: list[Row], conds: list[str], key: Callable[[Row], str | None]) -> dict:
    """``{condition: {family: {key: count}}}`` over ``rows`` (rows whose key is None are left out)."""
    out: dict = {}
    for c in conds:
        fams: dict[str, Counter] = {}
        for r in rows:
            if r.condition == c and (k := key(r)) is not None:
                fams.setdefault(r.family_id, Counter())[k] += 1
        out[c] = {f: dict(sorted(n.items())) for f, n in sorted(fams.items())}
    return out


def _oracle_gated_per_family(rows: list[Row], primary: list[Row], conds: list[str]) -> dict:
    """The oracle-gated view (protocol §15.7; secondary) in case-study mode: per condition, the cells kept and dropped and,
    per family, the lost yield and FA and FR on the cells kept; nothing pooled, no comparison."""
    ref: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        if r.origin == CandidateOrigin.reference.value:
            ref[(r.task_id, r.condition)].append(r.outcome)
    per: dict = {}
    for c in conds:
        sub = [r for r in primary if r.condition == c]
        cells = sorted({r.task_id for r in sub})
        kept = [t for t in cells if ref.get((t, c)) and all(o == "pass" for o in ref[(t, c)])]
        lost: dict[str, dict[str, int]] = {}
        for r in sub:
            if r.task_id not in kept:
                d = lost.setdefault(r.family_id, {"invalid": 0, "valid": 0})
                if r.label in d:
                    d[r.label] += 1
        per[c] = {"cells": len(cells), "cells_kept": len(kept),
                  "dropped": {t: "the reference was not graded" if not ref.get((t, c)) else
                              f"does not pass its reference ({', '.join(ref[(t, c)])})" for t in cells if t not in kept},
                  "lost_yield_per_family": dict(sorted(lost.items())),
                  "per_family": family_rates([r for r in sub if r.task_id in kept], condition=c)}
    return {"rule": "a verifier x task cell is dropped when the verifier does not pass the task's reference solution in the "
                    "run's sanity grading; its held-out candidates are the lost yield (secondary view, protocol §15.7); per "
                    "family only (case-study mode, §19.6)",
            "conditions": per}


def _post_hoc_per_family(run_dir: Path, tasks_root: Path, rows: list[Row], primary: list[Row], conds: list[str],
                         exclude_origins: tuple[str, ...], stratum_cands: dict[str, list[Candidate]] | None,
                         prepare: Callable[[list[Row]], list[Row]], also_exclude: dict[str, str] | None) -> dict:
    """The exploratory post-hoc analyses of :func:`_post_hoc` in case-study mode: per family, never pooled."""
    out: dict = {}
    nm = [r for r in primary if r.origin == CandidateOrigin.constructed_near_miss.value]
    out["near_miss_per_family"] = {
        c: {f: {k: {"accepted": sum(r.outcome == "pass" for r in fr if r.label == lab), "n": sum(r.label == lab for r in fr)}
                for k, lab in (("confirmed_invalid", "invalid"), ("ambiguous", "ambiguous"))}
            for f in sorted({r.family_id for r in nm if r.condition == c})
            for fr in [[r for r in nm if r.condition == c and r.family_id == f]]}
        for c in conds}
    crows, _ = build_rows(run_dir, tasks_root, allow_proposed=True, policy="check", also_exclude=also_exclude)
    cprim = prepare([r for r in crows if r.origin not in exclude_origins])
    out["sensitivity_check_labels_per_family"] = {c: family_rates(cprim, condition=c) for c in conds}
    dup = _duplicates(tasks_root, sorted({r.task_id for r in rows}), stratum_cands)
    out["duplicates"] = dup
    if dup:
        drows = [r for r in primary if r.candidate_id not in dup]
        out["sensitivity_without_duplicates_per_family"] = {c: family_rates(drows, condition=c) for c in conds}
    up, b1 = _b1_upstream_rows(run_dir, tasks_root, rows, primary)
    if up:
        out["b1_upstream_only_per_family"] = {"per_family": family_rates(b1, condition="repo_tests_upstream"),
                                              "n_checks": {t: len(v) for t, v in up.items()}}
    return out


def _case_study_analysis(run_dir: Path, tasks_root: Path, repo_root: Path, *, meta: dict, basis: str, rows: list[Row],
                         every: list[Row], primary: list[Row], conds: list[str], prepare: Callable[[list[Row]], list[Row]],
                         keys: dict[tuple[str, str], str], cands: dict[tuple[str, str], Candidate],
                         excluded: dict[tuple[str, str], str], support: dict[tuple[str, str], dict[str, str]],
                         exclude_origins: tuple[str, ...], allow_proposed: bool, also_exclude: dict[str, str] | None,
                         nat: dict, tasks: list[str], populations: dict[str, list[str]], with_populations: bool,
                         with_strata: bool, found: dict, manifest: dict) -> dict:
    """The analysis of a natural PR-review run in case-study mode (protocol §19.6): the tasks are exploratory case
    studies, so every table is per family, with no pooled rate, interval or p-value (:data:`CASE_STUDY_OMITTED`).

    Each distinct graded patch counts once, as under the reporting rules of new runs (§15.7). Kept: the per-family FA and
    FR under D19 (``per_family``, the primary conditions; B3 under ``secondary``), and per family the negatives accepted by
    type, the sanity grading, the outcome counts, the per-task outcomes, the distinct patches, the oracle-gated view, the
    sensitivity tables, the source evidence, the second labeling, the labels, the contract coverage and the natural
    sections. ``conditions`` and ``comparisons`` are empty, so a reader of the pooled keys finds no pooled number."""
    secondary = SECONDARY_CONDITIONS
    primary_c = [c for c in conds if c not in secondary]
    sec_c = [c for c in conds if c in secondary]
    meta["reporting_rules"] = {"rules": NEW_RUN_RULES, "basis": basis,
                               "protocol": "experiments/protocol.md v0.7 §15.7 and v0.8 §16.6, in case-study mode (v0.11 §19.6, "
                                           "v0.12 §20.3)"}
    meta["case_study"] = {**nat["case_study"], "omitted": CASE_STUDY_OMITTED}
    meta["secondary_conditions"] = {"conditions": list(secondary), "rule": SECONDARY_RULE}
    out: dict = {"meta": meta, "conditions": {}, "comparisons": []}
    out["per_family"] = {c: family_rates(primary, condition=c) for c in primary_c}
    if sec_c:
        out["secondary"] = {"rule": SECONDARY_RULE, "per_family": {c: family_rates(primary, condition=c) for c in sec_c}}
    out["by_negative_type_per_family"] = {
        c: {f: {nt: {"accepted": n.get(f"{nt}/pass", 0), "n": sum(v for k, v in n.items() if k.startswith(nt + "/"))}
                for nt in ("correction_violating", "initial_violating", "unspecified")
                if any(k.startswith(nt + "/") for k in n)}
            for f, n in fams.items()}
        for c, fams in _per_family_counts([r for r in primary if r.negative_type], conds,
                                          lambda r: f"{r.negative_type}/{'pass' if r.outcome == 'pass' else 'reject'}").items()}
    out["sanity_per_family"] = {
        c: {f: {o: {"pass": n.get(f"{o}/pass", 0), "n": sum(v for k, v in n.items() if k.startswith(o + "/")),
                    "outcomes": {k.split("/", 1)[1]: v for k, v in n.items() if k.startswith(o + "/")}}
                for o in exclude_origins if any(k.startswith(o + "/") for k in n)}
            for f, n in fams.items()}
        for c, fams in _per_family_counts([r for r in rows if r.origin in exclude_origins], conds,
                                          lambda r: f"{r.origin}/{r.outcome}").items()}
    out["outcome_counts_per_family"] = _per_family_counts(rows, conds, lambda r: r.outcome)
    out["per_task"] = {t: {c: [{"candidate": r.candidate_id, "origin": r.origin, "label": r.label,
                                "negative_type": r.negative_type, "outcome": r.outcome,
                                **({"stratum": r.stratum} if with_strata else {})}
                               for r in every if r.task_id == t and r.condition == c] for c in conds} for t in tasks}
    out["n_tasks"] = len(tasks)
    out["n_families"] = len({r.family_id for r in rows})
    if with_populations:
        out["meta"]["populations"] = populations
    if len(populations) > 1:
        out["meta"]["population_pooling"] = (f"{len(populations)} populations ({_describe(populations)}) with "
                                             "--pool-populations; in case-study mode nothing is pooled, so each family is "
                                             "reported on its own")
        out["by_population"] = {p: {"tasks": ts, "n_families": len({r.family_id for r in rows if r.task_id in ts})}
                                for p, ts in populations.items()}
    stratum_cands = found if with_strata else {}
    if with_strata:
        out["meta"]["strata"] = {t["task_id"]: t["strata"] for t in manifest["tasks"] if t.get("strata") and t["task_id"] in tasks}
    out["distinct_patches"] = {"rule": "held-out candidates of a task with the same graded patch count once; the "
                                       "representative is the natural state, else the first id (protocol §15.4, §15.7)",
                               "n_heldout": len({(r.task_id, r.candidate_id) for r in every}),
                               "n_distinct": len({(r.task_id, r.candidate_id) for r in primary}),
                               "groups": distinct_patch_rows(every, keys)[1]}
    out["sensitivity_every_candidate_per_family"] = {c: family_rates(every, condition=c) for c in conds}
    out["oracle_gated"] = _oracle_gated_per_family(rows, primary, conds)
    kept_cands = {t: {cid: v for cid, v in f.items() if (t, cid) not in excluded} for t, f in stratum_cands.items()}
    if allow_proposed:
        srows, _ = build_rows(run_dir, tasks_root, allow_proposed=True, policy="construction", also_exclude=also_exclude)
        sprim = prepare([r for r in srows if r.origin not in exclude_origins])
        out["sensitivity_construction_labels_per_family"] = {c: family_rates(sprim, condition=c) for c in conds}
        out.update(_post_hoc_per_family(run_dir, tasks_root, rows, primary, conds, exclude_origins,
                                        {t: [c for _, _, c in f.values()] for t, f in kept_cands.items()}, prepare,
                                        also_exclude))
    if excluded:  # fresh attempts excluded by their audit (a natural task has no strata, so none is expected)
        out["excluded"] = [{"task_id": t, "candidate_id": cid, "reason": why} for (t, cid), why in sorted(excluded.items())]
    second = _independent_labeling(rows, every, support, cands, conds, prepare, keys, with_strata, meta["label_rule"],
                                   exclude_origins, natural=nat)
    source = _natural_source_evidence(_source_evidence(rows, cands, conds), rows, cands, conds, secondary, nat, second,
                                      support, new_rules=True, case_study=True)
    if source is not None:
        out["source_evidence"] = source
    if second is not None:
        out["independent_labeling"] = second
    by_name: dict[str, dict[str, list[Candidate]]] = {}
    for t, f in kept_cands.items():
        for name, _, c in f.values():
            by_name.setdefault(t, {}).setdefault(name, []).append(c)
    out["labels"] = label_summary([tasks_root / t for t in tasks], strata=by_name, natural=True)
    out["coverage"] = {t: contract_coverage(tasks_root / t) for t in tasks}
    out["mapping_agreement"] = {t: mapping_agreement(tasks_root / t) for t in tasks}
    out["natural"], natural_inputs = _natural_block(run_dir, tasks_root, repo_root, manifest, nat, cands)
    out["meta"]["inputs"] = _input_hashes(run_dir, [tasks_root / t for t in tasks],
                                          [(tasks_root / t, rel) for t, f in stratum_cands.items() for _, rel, _ in f.values()],
                                          NATURAL_CODE, extra_files=natural_inputs)
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_revision(cwd: Path) -> str | None:
    """HEAD, with ``+dirty`` when tracked files differ from it (as in evaluate.code_revision)."""
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True).stdout.strip() or None
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd,
                               capture_output=True, text=True).stdout.strip()
    except OSError:
        return None
    return None if rev is None else rev + ("+dirty" if dirty else "")


def _input_hashes(run_dir: Path, task_dirs: list[Path], stratum_files: list[tuple[Path, str]] | None = None,
                  extra_code: tuple[str, ...] = (), extra_files: dict[str, str] | None = None) -> dict:
    """Revision and file hashes of every input the analysis read (labels, contracts, mappings, checks) and of its code.

    ``stratum_files`` are the stratum candidates read, as ``(task_dir, file relative to it)``; with any,
    the hashes also cover them and ``strata.py``, which reads them (it reads nothing for a run without strata).
    ``extra_code`` names further modules that this analysis ran (``stats.py`` under the reporting rules of a new run).
    ``extra_files`` (``{key: sha256}``) are the other inputs of a natural run's sections (:func:`_natural_context`,
    :func:`_natural_block`): its tasks' further files, its overlays by manifest hash (a key ending in ``/``), and the
    repository's records (the natural index and the screening records as the run's code revision holds them, the fetch
    log, the S10 records of the families outside the run).
    """
    rev = _git_revision(run_dir)
    files: dict[str, str] = {"results.jsonl": _sha(run_dir / "results.jsonl"), "manifest.json": _sha(run_dir / "manifest.json")}
    pkg = Path(__file__).resolve().parent
    code = ("analysis.py", "metrics.py", "schemas.py", "store.py", "patches.py") + (("strata.py",) if stratum_files else ())
    for name in code + extra_code:
        files[f"code/{name}"] = _sha(pkg / name)
    for td in task_dirs:
        for pat in ("task.json", "candidates/*.json", "contracts/*.json", "labels/construction_checks.json",
                    "labels/duplicates.json", "verifiers/repo_tests/upstream_check_ids.json"):
            for f in sorted(td.glob(pat)):
                files[f"{td.name}/{f.relative_to(td)}"] = _sha(f)
    for td, rel in stratum_files or []:
        files[f"{td.name}/{rel}"] = _sha(td / rel)
    for key, sha in (extra_files or {}).items():
        files.setdefault(key, sha)
    return {"git_revision": rev, "files_sha256": files}


_INDEX = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+.*$", re.M)


def _norm_patch(patch: str) -> str:
    """The patch as graded (protected test/config paths removed), without git index lines."""
    from .patches import filter_patch

    graded, _ = filter_patch(patch)
    return _INDEX.sub("", graded).strip()


def _post_hoc(run_dir: Path, tasks_root: Path, rows: list[Row], primary: list[Row], conds: list[str], n_boot: int,
              exclude_origins: tuple[str, ...], stratum_cands: dict[str, list[Candidate]] | None = None,
              prepare: Callable[[list[Row]], list[Row]] = list, also_exclude: dict[str, str] | None = None) -> dict:
    """Exploratory analyses added after the internal review (protocol v0.4; never primary).

    ``stratum_cands`` (by task id) are the stratum candidates the run graded; the duplicate check covers them too.
    ``prepare`` turns rows into the rows counted (for a new run: each distinct graded patch once).
    ``also_exclude`` (the sensitivity view) excludes those fresh attempts here as well (:func:`build_rows`).
    """
    out: dict = {}
    # 1. Near-miss acceptance by D19 status (confirmed invalid vs ambiguous).
    xt: dict = {}
    for c in conds:
        nm = [r for r in primary if r.condition == c and r.origin == "constructed_near_miss"]  # never a reference or no-op
        xt[c] = {k: {"accepted": sum(r.outcome == "pass" for r in nm if r.label == lab), "n": sum(r.label == lab for r in nm)}
                 for k, lab in (("confirmed_invalid", "invalid"), ("ambiguous", "ambiguous"))}
    out["near_miss_crosstab"] = xt
    # 2. Rates under the independent construction checks' assessed labels.
    crows, _ = build_rows(run_dir, tasks_root, allow_proposed=True, policy="check", also_exclude=also_exclude)
    cprim = prepare([r for r in crows if r.origin not in exclude_origins])
    out["sensitivity_check_labels"] = {}
    for c in conds:
        ss = summarize(cprim, condition=c, n_boot=n_boot)
        out["sensitivity_check_labels"][c] = {"fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den,
                                              "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den}
    # 3. Held-out candidates duplicating a development candidate or another held-out candidate.
    dup = _duplicates(tasks_root, sorted({r.task_id for r in rows}), stratum_cands)
    out["duplicates"] = dup
    if dup:
        drows = [r for r in primary if r.candidate_id not in dup]
        out["sensitivity_without_duplicates"] = {}
        for c in conds:
            ss = summarize(drows, condition=c, n_boot=n_boot)
            out["sensitivity_without_duplicates"][c] = {"fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den,
                                                        "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den}
    # 4. B1 restricted to checks that exist in the base commit's own tests (not added by the agent).
    up, b1 = _b1_upstream_rows(run_dir, tasks_root, rows, primary)
    if up:
        ss = summarize(b1, condition="repo_tests_upstream", n_boot=n_boot)
        out["b1_upstream_only"] = {"fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den,
                                   "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den,
                                   "n_checks": {t: len(v) for t, v in up.items()}}
    return out


def _duplicates(tasks_root: Path, task_ids: list[str], stratum_cands: dict[str, list[Candidate]] | None = None) -> dict:
    """Held-out candidates (post hoc, item 3) whose graded patch is a development candidate's or an earlier held-out one's
    (a natural state ranked first: the pre-correction or pre-review state, then by id), and those that
    ``labels/duplicates.json`` records as the same code apart from comments and docstrings (D40)."""
    dup: dict = {}
    for t in task_ids:
        m = load(tasks_root / t / "task.json", TaskManifest)
        cands = [load(tasks_root / t / p, Candidate) for p in m.candidates] + (stratum_cands or {}).get(t, [])
        dev = {_norm_patch(c.patch): c.candidate_id for c in cands if c.split.value == "dev" and c.patch}
        seen: dict[str, str] = {}
        for c in sorted(cands, key=lambda c: (c.origin not in _STATE_FIRST, c.candidate_id)):  # a natural state first
            if c.split.value != "eval" or c.origin in (CandidateOrigin.noop, CandidateOrigin.reference) or not c.patch:
                continue
            k = _norm_patch(c.patch)
            hits = {}
            if k in dev:
                hits["same_patch_as_dev"] = dev[k]
            if k in seen:
                hits["same_patch_as_heldout"] = seen[k]
            else:
                seen[k] = c.candidate_id
            if hits:
                dup[c.candidate_id] = {"task_id": t, **hits}
        # Same code apart from comments and docstrings (recorded by scripts/find_duplicates.py, D40).
        dp = tasks_root / t / "labels" / "duplicates.json"
        if dp.exists():
            for cid, hits in json.loads(dp.read_text()).get("duplicates", {}).items():
                dup.setdefault(cid, {"task_id": t}).update({k: ", ".join(v) for k, v in hits.items()})
    return dup


def _b1_upstream_rows(run_dir: Path, tasks_root: Path, rows: list[Row], primary: list[Row]) -> tuple[dict[str, set], list[Row]]:
    """B1 restricted to the checks in the base commit's own tests (``upstream_check_ids.json``; post hoc, item 4): the
    upstream check ids by task, and a row per B1 result (condition ``repo_tests_upstream``) with the primary label."""
    up: dict[str, set] = {}
    for t in sorted({r.task_id for r in rows}):
        f = tasks_root / t / "verifiers" / "repo_tests" / "upstream_check_ids.json"
        if f.exists():
            up[t] = set(json.loads(f.read_text())["upstream_check_ids"])
    b1: list[Row] = []
    if up:
        label_of = {(r.task_id, r.candidate_id): r for r in primary if r.condition == "repo_tests"}
        for res in read_jsonl(run_dir / "results.jsonl", VerificationResult):
            key = (res.task_id, res.candidate_id)
            if res.verifier_id != "repo_tests" or key not in label_of or res.task_id not in up:
                continue
            ok = all(ch.status == "passed" for ch in res.checks if ch.check_id in up[res.task_id])
            r0 = label_of[key]
            b1.append(Row(task_id=r0.task_id, family_id=r0.family_id, candidate_id=r0.candidate_id, condition="repo_tests_upstream",
                          outcome="pass" if ok else "task_failure", label=r0.label, origin=r0.origin,
                          population=r0.population, stratum=r0.stratum))
    return up, b1


def _fmt(rate, num, den, ci=None) -> str:
    if rate is None:
        return f"n/a (0/{den})"
    s = f"{rate:.2f} ({num}/{den})"
    if ci:
        s += f" [{ci[0]:.2f}, {ci[1]:.2f}]"
    return s


def _exact(x: dict) -> str:
    return "n/a" if not x.get("exact95") else f"[{x['exact95'][0]:.2f}, {x['exact95'][1]:.2f}]"


def _p(x) -> str:
    return "n/a" if x is None else f"{x:.3g}"


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] + ("" if text.endswith(".") else ".")


def _group_markdown(title: str, intro: str, groups: dict, with_ci: bool = True) -> list[str]:
    """One FA/FR table per group (a population or a candidate stratum), each on its own rows.

    Without ``with_ci`` (a new run: its intervals are in the appendix) the rates carry no bootstrap interval.
    """
    lines = ["", f"## {title}", "", intro]
    for g, d in groups.items():
        lines += ["", f"### {g} (tasks: {', '.join(d['tasks'])}; families: {d['n_families']})", "",
                  "| Condition | False acceptance | FA exact 95% | False rejection | FR exact 95% | Infra outcomes | Excluded (unlabeled/ambiguous) |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for c, x in d["conditions"].items():
            fa, fr = x["false_acceptance"], x["false_rejection"]
            star = lambda y: "*" if with_ci and y.get("ci95_degenerate") else ""  # noqa: E731
            ci = lambda y: y["ci95"] if with_ci else None  # noqa: E731
            lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], ci(fa))}{star(fa)} | {_exact(fa)} | "
                         f"{_fmt(fr['rate'], fr['num'], fr['den'], ci(fr))}{star(fr)} | {_exact(fr)} | "
                         f"{x['infrastructure']['num']}/{x['infrastructure']['den']} | {x['excluded_unlabeled_or_ambiguous']} |")
    return lines


def _label_row(name: str, d: dict) -> str:
    q = ", ".join(x["candidate"] for x in d["review_queue"]) or "-"
    return (f"| {name} | {d['counts'].get('valid', 0)} | {d['counts'].get('invalid', 0)} | {d['counts'].get('ambiguous', 0)} | "
            f"{d['counts'].get('unlabeled', 0)} | {q} |")


def _rules_markdown(a: dict) -> list[str]:
    """The banner, primary per-family table and exact paired comparisons of a new run (protocol §15.7)."""
    rr, bs, dp = a["meta"]["reporting_rules"], a["meta"]["bootstrap"], a["distinct_patches"]
    boot = ("" if bs["inferential"] else
            f", marked as not inferential ({bs['n_families']} task families, fewer than {MIN_INFERENTIAL_FAMILIES})")
    lines = [f"> **Reporting rules of a new run** (protocol §15.7, §16.6): {rr['basis']}. Each distinct graded patch counts once "
             f"({dp['n_distinct']} distinct among {dp['n_heldout']} held-out candidates). The per-family table is the primary "
             "display, every paired comparison carries exact sign-flip p-values over task families with their attainable floors, "
             f"and the cluster-bootstrap intervals are in the appendix{boot}.", ""]
    fams = sorted({f for d in a["per_family"].values() for f in d})
    lines += ["## Primary display: false acceptance and false rejection per task family", "",
              "(numerator/denominator) per task family, each distinct graded patch once; the reference solution and the no-op "
              "are excluded (see the sanity checks). The last two columns pool the families.", "",
              "| Condition | " + " | ".join(f"{f} FA | {f} FR" for f in fams) + " | All FA | All FR |",
              "| --- | " + " | ".join("--- | ---" for _ in fams) + " | --- | --- |"]
    for c, pf in a["per_family"].items():
        cells = []
        for f in fams:
            x = pf.get(f)
            cells += ["-", "-"] if x is None else [f"{x['fa_num']}/{x['fa_den']}", f"{x['fr_num']}/{x['fr_den']}"]
        fa, fr = a["conditions"][c]["false_acceptance"], a["conditions"][c]["false_rejection"]
        lines.append(f"| {c} | " + " | ".join(cells) + f" | {_fmt(fa['rate'], fa['num'], fa['den'])} | "
                     f"{_fmt(fr['rate'], fr['num'], fr['den'])} |")
    lines += _signflip_markdown(a["comparisons"])
    return lines


def _signflip_markdown(comparisons: list[dict], heading: str = "## Paired comparisons: exact sign-flip tests over task families",
                       scope: str = "same candidates, each distinct graded patch once",
                       unit: tuple[str, str] = ("family", "families")) -> list[str]:
    """A table of paired comparisons with their exact sign-flip p-values and floors, and the null results stated with it.

    ``unit``: what the tests flip, singular and plural (task families; repositories in the view clustered by repository)."""
    one, many = unit
    lines = ["", heading, "",
             f"A - B is the pooled difference ({scope}); the p-values test the sum over {many} of the count differences "
             "(each candidate weighs the same) with an exact sign-flip test, which cannot go below its floor. p (A > B): "
             "the first-named condition errs more.", "",
             f"| A | B | Metric | A - B | Per-{one} A - B | p (A > B) | p (A < B) | p two-sided | p two-sided, {one} means | "
             f"Floor one-sided / two-sided | {many.capitalize()} | A acc & B rej | A rej & B acc |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for d in comparisons:
        sf, sm = d["signflip"]["pooled"], d["signflip"]["family_mean"]
        per = ", ".join(f"{f} {(x['a_num'] - x['b_num']) / x['den']:+.2f}" for f, x in d["per_family_counts"].items()
                        if x["den"]) or "-"
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        disc = d.get("discordant")
        lines.append(f"| {d['a']} | {d['b']} | {d['metric'].upper()} | {diff} | {per} | {_p(sf['p_greater'])} | {_p(sf['p_less'])} | "
                     f"{_p(sf['p_two_sided'])} | {_p(sm['p_two_sided'])} | {_p(sf['floor_one_sided'])} / {_p(sf['floor_two_sided'])} | "
                     f"{sf['k']} | " + (f"{disc['a_accepts_b_rejects']} | {disc['a_rejects_b_accepts']} |" if disc else "- | - |"))
    tested = [d for d in comparisons if d["signflip"]["pooled"]["k"]]
    null = [d for d in tested if d["signflip"]["pooled"]["p_two_sided"] >= 0.05]
    text = (f"**Null results.** {len(null)} of {len(tested)} tested comparisons have a two-sided exact p-value of 0.05 or more"
            + (": " + "; ".join(f"{d['a']} vs {d['b']} {d['metric'].upper()}" for d in null) if null else ""))
    floors = [d["signflip"]["pooled"]["floor_two_sided"] for d in tested]
    if floors and min(floors) >= 0.05:
        text += (f". With at most {max(d['signflip']['pooled']['k'] for d in tested)} {many} no two-sided p-value can go "
                 f"below {min(floors):.3g}, so none can reach 0.05")
    untested = len(comparisons) - len(tested)
    return lines + ["", text + (f"; {untested} comparison(s) have no labeled candidate to test." if untested else ".")]


def _fresh_markdown(f: dict, sensitivity: bool = False) -> list[str]:
    """The fresh attempts' section; ``sensitivity``: of the sensitivity view, whose exclusions hold for it alone."""
    lines = ["", "## Fresh-agent attempts: solve rates and audit exclusions", "", _sentence(f["rule"]), "",
             "| Configuration | Variant | Attempts | Solved | Not solved | Undecided | Solve rate | Finished / gave up / error | "
             "Per family (solved/attempts) |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for d in f["by_configuration_variant"].values():
        e = d["ended"]
        per = ", ".join(f"{fam} {x['solved']}/{x['attempts']}" for fam, x in d["per_family"].items())
        lines.append(f"| {d['configuration']} | {d['variant']} | {d['attempts']} | {d['solved']} | {d['not_solved']} | "
                     f"{d['undecided']} | {d['rate']:.2f} | {e.get('finished', 0)} / {e.get('gave_up', 0)} / {e.get('error', 0)} | {per} |")
    if "rule_independent_label" in f:  # the run graded the independent labeler
        lines += ["", "### Solve rates under each labeling", "", _sentence(f["rule_independent_label"]), "",
                  "| Configuration | Variant | Attempts | Solved, D19 | Solve rate, D19 | Solved, independent | "
                  "Not solved, independent | Undecided, independent | Solve rate, independent | Per family, independent "
                  "(solved/attempts) |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for d in f["by_configuration_variant"].values():
            x = d["independent_label"]
            per = ", ".join(f"{fam} {y['solved']}/{y['attempts']}" for fam, y in x["per_family"].items())
            lines.append(f"| {d['configuration']} | {d['variant']} | {d['attempts']} | {d['solved']} | {d['rate']:.2f} | "
                         f"{x['solved']} | {x['not_solved']} | {x['undecided']} | {x['rate']:.2f} | {per} |")
    u = f["u1_correction_violating"]
    graded = "; ".join(f"{c} accepts {x['accepted']}/{x['n']}" for c, x in u["graded_by"].items())
    lines += ["", f"u1 attempts that violate a correction requirement: {u['correction_violating']}/{u['attempts']}"
              + (f" ({graded})" if graded and u["correction_violating"] else "") + "."]
    if f["excluded"]:
        lines += ["", f"Excluded from {'this sensitivity analysis' if sensitivity else 'every analysis'} ({len(f['excluded'])}):", ""]
        lines += [f"* {x['candidate_id']} ({x['task_id']}, attempt {x['attempt_id'] or '-'}): {x['reason']}" for x in f["excluded"]]
    else:
        lines += ["", "No attempt is excluded."]
    return lines


def _sensitivity_markdown(s: dict) -> list[str]:
    """The banner of the sensitivity view (protocol §18.1), at the top of ``analysis_sensitivity.md``."""
    srcs = "; ".join(f"`{x['file']}` ({x['kind']}, {len(x['ids'])} id(s), sha256 {x['sha256'][:12]})" for x in s["sources"])
    lines = [f"> **Sensitivity analysis, not the primary analysis** (protocol §18.1). Every table below is recomputed with "
             f"{len(s['excluded_here'])} more fresh attempt(s) excluded: those listed in {srcs or 'no file'}. The primary analysis, "
             f"which uses the reviewed audit verdicts, is `{s['primary_analysis'].replace('.json', '.md')}` "
             f"(`{s['primary_analysis']}`, sha256 {s['primary_analysis_sha256'][:12]}).", ">"]
    here = ", ".join(f"{x['candidate_id']} ({x['task_id']})" for x in s["excluded_here"]) or "none"
    lines.append(f"> Excluded here as well ({len(s['excluded_here'])}): {here}.")
    if s["already_excluded"]:
        lines += [">", f"> Listed, and excluded by the primary analysis already ({len(s['already_excluded'])}): "
                  + "; ".join(f"{x['candidate_id']} ({x['reason']})" for x in s["already_excluded"]) + "."]
    if s["not_in_run"]:
        lines += [">", f"> **Listed but not an attempt of this run** ({len(s['not_in_run'])}): {', '.join(s['not_in_run'])}."]
    return lines + [""]


def _rates_cell(x: dict) -> tuple[str, str]:
    fa, fr = x["false_acceptance"], x["false_rejection"]
    return _fmt(fa["rate"], fa["num"], fa["den"]), _fmt(fr["rate"], fr["num"], fr["den"])


def _plain(c: str) -> str:
    return c


def _condition_namer(a: dict) -> Callable[[str], str]:
    """How a table row names a condition: a natural run's secondary conditions (B3) are marked as such; else as it is."""
    secondary = tuple(a["meta"].get("secondary_conditions", {}).get("conditions", ()))
    return (lambda c: f"{c} (secondary)" if c in secondary else c) if secondary else _plain


def _side_by_side_markdown(conditions: dict, name: Callable[[str], str] = _plain) -> list[str]:
    """FA and FR per condition under the primary labels and under the independent labeling, and the per-family table."""
    lines = ["| Condition | FA, primary | FA, independent | FR, primary | FR, independent | Excluded (unlabeled/ambiguous), "
             "primary / independent |", "| --- | --- | --- | --- | --- | --- |"]
    for c, d in conditions.items():
        (pfa, pfr), (ifa, ifr) = _rates_cell(d["primary"]), _rates_cell(d["independent_label"])
        lines.append(f"| {name(c)} | {pfa} | {ifa} | {pfr} | {ifr} | {d['primary']['excluded_unlabeled_or_ambiguous']} / "
                     f"{d['independent_label']['excluded_unlabeled_or_ambiguous']} |")
    fams = sorted({f for d in conditions.values() for x in d.values() for f in x["per_family"]})
    head = ["Condition", "Labeling", *(f"{f} {m}" for f in fams for m in ("FA", "FR")), "All FA", "All FR"]
    lines += ["", "| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    for c, d in conditions.items():
        for labeling, key in (("primary", "primary"), ("independent", "independent_label")):
            pf, cells = d[key]["per_family"], []
            for f in fams:
                x = pf.get(f)
                cells += ["-", "-"] if x is None else [f"{x['fa_num']}/{x['fa_den']}", f"{x['fr_num']}/{x['fr_den']}"]
            lines.append(f"| {name(c)} | {labeling} | " + " | ".join(cells) + " | " + " | ".join(_rates_cell(d[key])) + " |")
    return lines


def _agreement_markdown(title: str, g: dict) -> list[str]:
    """One stratum's (or the pooled) agreement between D19 and the independent labeling: counts, the 2x2 table, the rest."""
    note = f" **Exploratory:** {g['why_exploratory']}." if g.get("why_exploratory") else (
        " Includes exploratory units (see the task stratum)." if g.get("exploratory") else "")
    kappa = "n/a" if g["kappa"] is None else f"{g['kappa']:.2f}" + (" (degenerate: one labeling uses one value only)"
                                                                       if g["kappa_degenerate"] else "")
    rate = "n/a" if g["agreement"] is None else f"{g['agreement']:.2f}"
    lines = ["", f"**{title}**: {g['n_units']} unit(s); both decide {g['n_decided_by_both']}: agree {g['agree']}, "
                 f"disagree {g['disagree']} (agreement {rate}, Cohen's kappa {kappa}).{note}", "",
             "| D19 \\ independent | valid | invalid |", "| --- | --- | --- |"]
    lines += [f"| {a} | {g['table'][a]['valid']} | {g['table'][a]['invalid']} |" for a in ("valid", "invalid")]
    cross = g["crosstab"]
    rest = [f"D19 {a}, independent {b}: {n}" for a, row in cross.items() for b, n in row.items()
            if n and not (a in ("valid", "invalid") and b in ("valid", "invalid"))]
    lines += ["", "Outside the 2x2 table (none: no D19 proposal, or not graded by the labeler): " + ("; ".join(rest) or "none") + "."]
    if g["disagreements"]:
        lines += [""] + [f"* {x['representative']} ({x['task_id']}{', with ' + ', '.join(x['members'][1:]) if len(x['members']) > 1 else ''}): "
                         f"D19 {x['d19']}, independent {x['independent_label']} (outcome {', '.join(o or '-' for o in x['outcomes'])})"
                         for x in g["disagreements"]]
    if g.get("natural"):  # a natural task's units: the pre-review states apart from the pool (§15.5)
        lines += _natural_agreement_lines(g["natural"], why=not g.get("why_given"))
    return lines


def _independent_markdown(x: dict, name: Callable[[str], str] = _plain) -> list[str]:
    """The second labeling by the independent labeler (protocol §15.4, §15.5)."""
    lab, amb = x["labels"], x["ambiguous_outcomes"]
    sanity = "; ".join(f"{t} {o} {s['pass']}/{s['n']}" for t, d in x["sanity"].items() for o, s in d.items()) or "not graded"
    lines = ["", "## Independent labeler: a second labeling (protocol §15.4, §15.5)", "", _sentence(x["rule"]), ""]
    if x.get("natural_rule"):
        lines += [_sentence(x["natural_rule"]), ""]
    lines += [f"Graded on {', '.join(x['tasks']) or 'no task'}. Held-out candidates: {lab['valid']} valid, {lab['invalid']} invalid, "
             f"{lab['ambiguous']} ambiguous" + (f" ({', '.join(f'{o} {n}' for o, n in amb.items())})" if amb else "")
             + f", {lab['not_graded']} not graded. The labeler passes on (sanity): {sanity}."]
    lines += _left_out_lines(x)
    lines += ["", "### False acceptance and false rejection under each labeling", "",
             f"(numerator/denominator), counted as the primary analysis counts them; primary: {x['primary_labels']}; "
             "independent: the labeler's verdicts. Unlabeled and ambiguous candidates are excluded and counted.", ""]
    lines += _side_by_side_markdown(x["conditions"], name)
    for s, d in x.get("by_stratum", {}).items():
        lines += ["", f"### Stratum {s} (tasks: {', '.join(d['tasks'])})", ""] + _side_by_side_markdown(d["conditions"], name)
    ag = x["agreement"]
    lines += ["", "### Agreement between D19 and the independent labeler", "", _sentence(ag["rule"])]
    for s, g in ag["by_stratum"].items():
        lines += _agreement_markdown(f"Stratum {s} (tasks: {', '.join(g['tasks'])})", g)
    if "pooled" in ag:
        lines += _agreement_markdown("All strata pooled", ag["pooled"])
    return lines


def _source_markdown(s: dict) -> list[str]:
    if "banner" in s:  # a natural run's block (_natural_source_evidence)
        return _natural_source_markdown(s, case_study=False)
    lines = ["", "## Source-evidence labels (reported apart from D19)", "", _sentence(s["rule"]), "",
             "| Condition | Invalid by source evidence, accepted | Valid by source evidence, rejected |", "| --- | --- | --- |"]
    for c, d in s["conditions"].items():
        lines.append(f"| {c} | {d['invalid']['accepted']}/{d['invalid']['n']} | {d['valid']['rejected']}/{d['valid']['n']} |")
    return lines


def _oracle_markdown(o: dict, name: Callable[[str], str] = _plain) -> list[str]:
    lines = ["", "## Oracle-gated view (secondary)", "", _sentence(o["rule"]), "",
             "| Condition | Cells kept | Dropped | Lost yield (invalid / valid) | False acceptance | False rejection |",
             "| --- | --- | --- | --- | --- | --- |"]
    for c, d in o["conditions"].items():
        fa, fr = d["false_acceptance"], d["false_rejection"]
        dropped = "; ".join(f"{t}: {why}" for t, why in d["dropped"].items()) or "-"
        lines.append(f"| {name(c)} | {d['cells_kept']}/{d['cells']} | {dropped} | {d['lost_yield']['invalid']} / {d['lost_yield']['valid']} | "
                     f"{_fmt(fa['rate'], fa['num'], fa['den'])} | {_fmt(fr['rate'], fr['num'], fr['den'])} |")
    if o["comparisons"]:
        lines += _signflip_markdown(o["comparisons"], "### Oracle-gated paired comparisons",
                                    "same candidates, on the tasks that both conditions keep")
    if o.get("secondary_comparisons"):  # B3 in a natural run: secondary, outside the primary null tally
        lines += _signflip_markdown(o["secondary_comparisons"], "### Oracle-gated secondary paired comparisons (B3)",
                                    "same candidates, on the tasks that both conditions keep; secondary, outside the primary "
                                    "null tally")
    return lines


def _distinct_markdown(d: dict) -> list[str]:
    lines = ["", "## Distinct graded patches", "",
             f"{d['n_distinct']} distinct graded patches among {d['n_heldout']} held-out candidates: {d['rule']}."]
    if d["groups"]:
        lines.append("")
    for g in d["groups"]:
        notes = [f"label {g['label'] or 'none'}"] + ([] if g["labels_agree"] else ["the members' labels disagree"])
        if g["outcomes_differ"]:
            notes.append(f"outcomes differ under {', '.join(g['outcomes_differ'])} (counted as unresolved)")
        lines.append(f"* {g['task_id']}: {', '.join(g['members'])} count once, as {g['representative']} ({'; '.join(notes)})")
    return lines


def _bootstrap_appendix(a: dict) -> list[str]:
    """The cluster-bootstrap intervals of a new run, marked as not inferential below 10 families (protocol §15.7)."""
    bs = a["meta"]["bootstrap"]
    mark = "" if bs["inferential"] else (f" They are not inferential: the run has {bs['n_families']} task families, fewer than "
                                         f"{MIN_INFERENTIAL_FAMILIES}.")
    star = lambda y: "*" if y.get("ci95_degenerate") else ""  # noqa: E731
    lines = ["", "## Appendix: cluster-bootstrap intervals", "",
             f"95% percentile intervals of a bootstrap that resamples task families (each distinct graded patch once).{mark} "
             "Intervals marked * are degenerate (every family has the same rate or difference).", "",
             "| Condition | False acceptance [95% bootstrap] | False rejection [95% bootstrap] |", "| --- | --- | --- |"]
    for c, d in a["conditions"].items():
        fa, fr = d["false_acceptance"], d["false_rejection"]
        lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], fa['ci95'])}{star(fa)} | "
                     f"{_fmt(fr['rate'], fr['num'], fr['den'], fr['ci95'])}{star(fr)} |")
    lines += ["", "| A | B | Metric | A - B | 95% bootstrap | Families |", "| --- | --- | --- | --- | --- | --- |"]
    for d in a["comparisons"]:
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]" + ("*" if d.get("ci95_degenerate") else "")
        lines.append(f"| {d['a']} | {d['b']} | {d['metric'].upper()} | {diff} | {ci} | {d['n_families']} |")
    if a.get("secondary"):  # B3 in a natural run: its own intervals, apart from the primary conditions
        sec = a["secondary"]
        lines += ["", "Secondary condition (B3):", "",
                  "| Condition | False acceptance [95% bootstrap] | False rejection [95% bootstrap] |", "| --- | --- | --- |"]
        for c, d in sec["conditions"].items():
            fa, fr = d["false_acceptance"], d["false_rejection"]
            lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], fa['ci95'])}{star(fa)} | "
                         f"{_fmt(fr['rate'], fr['num'], fr['den'], fr['ci95'])}{star(fr)} |")
        if sec["comparisons"]:
            lines += ["", "| A | B | Metric | A - B | 95% bootstrap | Families |", "| --- | --- | --- | --- | --- | --- |"]
            for d in sec["comparisons"]:
                diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
                ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]" + ("*" if d.get("ci95_degenerate") else "")
                lines.append(f"| {d['a']} | {d['b']} | {d['metric'].upper()} | {diff} | {ci} | {d['n_families']} |")
    for title, key in (("By population", "by_population"), ("By candidate stratum", "by_stratum")):
        for g, gd in a.get(key, {}).items():
            note = "" if gd["n_families"] >= MIN_INFERENTIAL_FAMILIES else "; not inferential"
            lines += ["", f"{title}, {g} ({gd['n_families']} families{note}):", "",
                      "| Condition | False acceptance [95% bootstrap] | False rejection [95% bootstrap] |", "| --- | --- | --- |"]
            for c, x in gd["conditions"].items():
                fa, fr = x["false_acceptance"], x["false_rejection"]
                lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], fa['ci95'])}{star(fa)} | "
                             f"{_fmt(fr['rate'], fr['num'], fr['den'], fr['ci95'])}{star(fr)} |")
    return lines


def _v(x) -> str:
    """A table cell: ``-`` for a missing value, yes or no for a truth value."""
    if isinstance(x, bool):
        return "yes" if x else "no"
    return "-" if x is None or x == "" else str(x)


def _families_of(by_condition: dict) -> list[str]:
    return sorted({f for d in by_condition.values() for f in d}, key=_task_order)


def _family_rates_lines(per_family: dict, suffix: Callable[[str], str] = _plain) -> list[str]:
    """One row per condition, an FA and an FR column (numerator/denominator) per family; no column pools the families."""
    fams = _families_of(per_family)
    lines = ["| Condition | " + " | ".join(f"{f} FA | {f} FR" for f in fams) + " |",
             "| --- | " + " | ".join("--- | ---" for _ in fams) + " |"]
    for c, pf in per_family.items():
        cells = []
        for f in fams:
            x = pf.get(f)
            cells += ["-", "-"] if x is None else [f"{x['fa_num']}/{x['fa_den']}", f"{x['fr_num']}/{x['fr_den']}"]
        lines.append(f"| {suffix(c)} | " + " | ".join(cells) + " |")
    return lines


def _natural_banner(a: dict) -> list[str]:
    """The banner of a natural run: case-study mode or not (§19.6), and its families against the committed index."""
    nat, cs = a["natural"], a["meta"].get("case_study", {})
    if cs.get("applies"):
        lines = [(f"> **Exploratory case studies** (protocol §19.6, §20.3): {cs['why']}. Every table below is per task family: "
                  "no pooled rate, interval or p-value is reported, and the tasks are exploratory case studies."), ""]
    else:
        lines = [f"> **Natural PR-review arm** (protocol §15.6, §19.6, §20.3): {cs.get('why', 'not recorded')}.", ""]
    idx, rec = nat["index"], nat.get("records", {})
    if rec.get("basis") == "head":  # the run's manifest names no commit of the repository
        lines += [(f"> **Records read at HEAD**: {rec['why']}, so the natural index and the screening records are read as the "
                   "HEAD commit holds them when the analysis runs, and a later commit of the index can change this analysis."),
                  ""]
    by_sample = ", ".join(f"{k} {n}" for k, n in idx.get("accepted_by_sample", {}).items()) or "none"
    samples = ", ".join(idx.get("run_samples", [])) or "none"
    if idx["matches"]:
        lines += [(f"The run's {len(idx['run_families'])} families are the {len(idx['s11_of_run_samples'])} accepted families "
                   f"(S11) of its sample(s), {samples}, in the committed index ({idx['source']}), which counts {idx['accepted']} "
                   f"over both samples ({by_sample}); each run grades the accepted families of its sample (protocol §20.2)."), ""]
    else:
        parts = []
        if not idx["readable"]:
            parts.append(f"the committed index cannot be read ({idx.get('why')})")
        if idx["run_families_not_s11"]:
            parts.append("not accepted (S11) there: " + ", ".join(idx["run_families_not_s11"]))
        if idx["s11_not_in_run"]:
            parts.append(f"accepted families of its sample(s) ({samples}) that the run leaves out: " + ", ".join(idx["s11_not_in_run"]))
        lines += [(f"> **The run's families against the committed index** ({idx['source']}): " + "; ".join(parts)
                   + ". Each natural run grades the accepted families of its sample: natural-pr-v1 the first sample's, "
                     "natural-pr-v2 the extension's (protocol §20.2)."), ""]
    return lines


def _secondary_markdown(sec: dict, case_study: bool) -> list[str]:
    """B3, the secondary condition of a natural run (§15.6): its own tables, and its comparisons with their own null tally."""
    lines = ["", "## Secondary condition: B3 (diff-derived)", "", _sentence(sec["rule"]), "",
             "(numerator/denominator) per task family, each distinct graded patch once; the reference solution and the no-op "
             "are excluded." + ("" if case_study else " The last two columns pool the families."), ""]
    if case_study:
        return lines + _family_rates_lines(sec["per_family"])
    fams = _families_of(sec["per_family"])
    lines += ["| Condition | " + " | ".join(f"{f} FA | {f} FR" for f in fams) + " | All FA | All FR |",
              "| --- | " + " | ".join("--- | ---" for _ in fams) + " | --- | --- |"]
    for c, pf in sec["per_family"].items():
        cells = []
        for f in fams:
            x = pf.get(f)
            cells += ["-", "-"] if x is None else [f"{x['fa_num']}/{x['fa_den']}", f"{x['fr_num']}/{x['fr_den']}"]
        d = sec["conditions"].get(c, {})
        fa, fr = d.get("false_acceptance"), d.get("false_rejection")
        pooled = [_fmt(fa["rate"], fa["num"], fa["den"]), _fmt(fr["rate"], fr["num"], fr["den"])] if fa and fr else ["-", "-"]
        lines.append(f"| {c} | " + " | ".join(cells) + " | " + " | ".join(pooled) + " |")
    if sec.get("comparisons"):
        lines += _signflip_markdown(sec["comparisons"], "### Secondary paired comparisons (B3): exact sign-flip tests over task "
                                    "families", "same candidates, each distinct graded patch once; secondary, outside the "
                                    "primary null tally")
    return lines


def _correction_cell(ids: list[str], observes: bool | None) -> str:
    """A family's correction requirements in a table cell; with none, what that means (D64, decision 14)."""
    if ids:
        return ", ".join(ids)
    if observes is None:
        return "none known (no reference contract)"
    return "none: the reference contract does not observe the correction, and no near miss targets it"


def _natural_source_markdown(s: dict, case_study: bool) -> list[str]:
    """The source-evidence block of a natural run: banner, per-family acceptance, the pre-review states, and outside
    case-study mode the pooled counts and the paired sign-flip comparisons."""
    lines = ["", "## Source-evidence labels (reported apart from D19)", "", f"> **{_sentence(s['banner'])}**", ""]
    if s.get("rule"):
        lines += [_sentence(s["rule"]), ""]
    rows = {**s.get("per_family", {}), **{f"{c} (secondary)": v for c, v in s.get("secondary_per_family", {}).items()}}
    fams = _families_of(rows)
    lines += [("Pre-review states accepted, per task family and condition (invalid by source evidence; accepted is a false "
               "acceptance under this labeling):"), "",
              "| Condition | " + " | ".join(fams) + " |", "| --- | " + " | ".join("---" for _ in fams) + " |"]
    for c, pf in rows.items():
        cells = []
        for f in fams:
            x = pf.get(f, {}).get("invalid")
            cells.append("-" if not x or not x["n"] else ("accepted" if x["accepted"] else "rejected") if x["n"] == 1
                         else f"{x['accepted']}/{x['n']} accepted")
        lines.append(f"| {c} | " + " | ".join(cells) + " |")
    lines += ["", ("| Family | Candidate | Source evidence | D19 | Independent labeler (outcome) | Reference checks in the run | "
                   "Correction requirements |"), "| --- | --- | --- | --- | --- | --- | --- |"]
    for key, x in s.get("pre_review", {}).items():
        second = ("left out (labeler not usable)" if x["independent_label_left_out"] else
                  "not graded" if x["independent_label_outcome"] is None else
                  f"{_v(x['independent_label'])} ({_v(x['independent_label_outcome'])})")
        lines.append(f"| {_v(x['family_id'])} | {key.split('/', 1)[1]} | {_v(x['source_evidence'])} | {_v(x['d19'])} | {second} | "
                     f"{_v(x['reference_checks_outcome'])} | "
                     f"{_correction_cell(x['correction_requirements'], x.get('reference_observes_correction'))} |")
    if case_study or "conditions" not in s:
        return lines
    lines += ["", "| Condition | Invalid by source evidence, accepted | Valid by source evidence, rejected |", "| --- | --- | --- |"]
    pooled = {**s["conditions"], **{f"{c} (secondary)": d for c, d in s.get("secondary_conditions", {}).items()}}
    for c, d in pooled.items():
        lines.append(f"| {c} | {d['invalid']['accepted']}/{d['invalid']['n']} | {d['valid']['rejected']}/{d['valid']['n']} |")
    if s.get("comparisons"):
        lines += _signflip_markdown(s["comparisons"], "### Paired comparisons under the source-evidence labels: exact sign-flip "
                                    "tests over task families", "the pre-review states, each once")
    if s.get("secondary_comparisons"):
        lines += _signflip_markdown(s["secondary_comparisons"], "### Secondary paired comparisons (B3) under the source-evidence "
                                    "labels", "the pre-review states, each once; secondary, outside the primary null tally")
    return lines


def _natural_agreement_lines(g: dict, why: bool = True) -> list[str]:
    """The agreement of a stratum or family with natural tasks, apart for the pre-review states and for the pool; with
    ``why``, each part says what it holds (a case-study table of families says it once, :func:`_natural_agreement_why`)."""
    lines = []
    for key, title in (("existed_before_labeler", "Pre-review states, which existed before the labeler was written"),
                       ("generated_after_labeler", "The held-out pool")):
        x = g[key]
        rate = "n/a" if x["agreement"] is None else f"{x['agreement']:.2f}"
        lines += ["", (f"* {title}: {x['n_units']} unit(s); both decide {x['n_decided_by_both']}: agree {x['agree']}, "
                       f"disagree {x['disagree']} (agreement {rate})." + (f" {_order_sentence(x['order'])}" if "order" in x else "")
                       + (f" {_sentence(x['why'])}" if why else ""))]
    return lines


def _order_sentence(o: dict) -> str:
    """Whether the pool's candidates were generated after the labeler was frozen, as :func:`_generation_order` found."""
    text = f"Generated after the labeler was frozen: {o['after']} of {o['candidates']} candidate(s)"
    if o["not_after"]:
        text += f"; not after it: {', '.join(o['not_after'])}"
    if o["not_shown"]:
        reasons: dict[str, list[str]] = {}
        for name, why in o["not_shown"].items():
            reasons.setdefault(why, []).append(name)
        text += "; not shown for " + "; ".join(f"{', '.join(ns)} ({why})" for why, ns in reasons.items())
    return text + "."


def _natural_agreement_why(groups: dict) -> list[str]:
    g = next((x["natural"] for x in groups.values() if x.get("natural")), None)
    if g is None:
        return []
    return ["", (f"Each family's units are also given apart. {_sentence(g['existed_before_labeler']['why'])} "
                 f"{_sentence(g['generated_after_labeler']['why'])}")]


def _left_out_lines(x: dict) -> list[str]:
    if not x.get("left_out"):
        return []
    lines = ["", f"Left out of the second labeling ({len(x['left_out'])}; their labeler is not usable, protocol §15.5):", ""]
    for t, d in x["left_out"].items():
        seen = "; ".join(f"{o} {', '.join(f'{k} {n}' for k, n in c.items())}" for o, c in d["outcomes"].items()) or "not graded"
        lines.append(f"* {t}: {d['why']} (the run's outcomes of its labeler: {seen})")
    return lines


def _independent_case_markdown(x: dict, name: Callable[[str], str] = _plain) -> list[str]:
    """The second labeling in case-study mode (§19.6): per family only."""
    sanity = "; ".join(f"{t} {o} {s['pass']}/{s['n']}" for t, d in x["sanity"].items() for o, s in d.items()) or "not graded"
    lines = ["", "## Independent labeler: a second labeling, per task family (protocol §15.4, §15.5)", "", _sentence(x["rule"]),
             "", _sentence(x["natural_rule"]), "",
             f"Graded on {', '.join(x['tasks']) or 'no task'}. The labeler passes on (sanity): {sanity}."]
    lines += _left_out_lines(x)
    lines += ["", "| Family | valid | invalid | ambiguous | not graded |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {f} | {d['valid']} | {d['invalid']} | {d['ambiguous']} | {d['not_graded']} |"
              for f, d in x["labels_per_family"].items()]
    fams = _families_of({c: {**d["primary"], **d["independent_label"]} for c, d in x["per_family"].items()})
    head = ["Condition", "Labeling", *(f"{f} {m}" for f in fams for m in ("FA", "FR"))]
    lines += ["", "### False acceptance and false rejection per family under each labeling", "",
              (f"(numerator/denominator), counted as the primary analysis counts them; primary: {x['primary_labels']}; "
               "independent: the labeler's verdicts. No column pools the families."), "",
              "| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    for c, d in x["per_family"].items():
        for labeling, key in (("primary", "primary"), ("independent", "independent_label")):
            cells = []
            for f in fams:
                y = d[key].get(f)
                cells += ["-", "-"] if y is None else [f"{y['fa_num']}/{y['fa_den']}", f"{y['fr_num']}/{y['fr_den']}"]
            lines.append(f"| {name(c)} | {labeling} | " + " | ".join(cells) + " |")
    ag = x["agreement"]
    lines += ["", "### Agreement between D19 and the independent labeler, per family", "", _sentence(ag["rule"])]
    lines += _natural_agreement_why(ag["per_family"])
    for f, g in ag["per_family"].items():
        lines += _agreement_markdown(f"Family {f}", {**g, "why_given": True})
    return lines


def _natural_flags_markdown(nat: dict) -> list[str]:
    lines = ["", "## Natural families: sample, B1 and correction requirements", "", _sentence(nat["rule"]), "",
             ("| Family | Sample | S11 | Session | B1 available (S10) | B1 graded | B1 = D19 regression norm | B3 graded | Labeler | "
              "Correction requirements | Near misses on the correction |"),
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    notes = []
    for t, f in nat["families"].items():
        eq = f["b1_equals_regression_norm"]
        same = (f"not known ({eq['why']})" if eq["equal"] is None else
                f"{'yes' if eq['equal'] else 'no'} ({eq['identical_files']} of {eq['b1_files']} B1 files identical; norm "
                f"{eq['norm_files']} files)")
        lab = f["labeler"]
        labeler = ("usable" if lab["usable"] else f"not usable ({_v(lab.get('status'))})") + (
            f", round {lab['round']}" if "round" in lab else "")
        corr = _correction_cell(f["correction_requirements"], f["reference_observes_correction"])
        if f["unscored_at_correction_events"]:
            corr += f" (unscored at a correction event, not counted: {', '.join(f['unscored_at_correction_events'])})"
        nm = f["near_misses_on_correction"]
        on = f"{len(nm['on_correction'])} of {nm['near_misses']}" + (f" ({', '.join(nm['on_correction'])})" if nm["on_correction"] else "")
        lines.append(f"| {t} | {_v(f['sample'])} | {_v(f['s11'])} | {'readable' if f['session_readable'] else 'not readable'} | "
                     f"{_v(f['b1']['available'])} | {'yes' if f['b1']['graded'] else 'no'} | {same} | "
                     f"{'yes' if f['b3']['graded'] else 'no'} | {labeler} | {corr} | {on} |")
        if f.get("correction_note"):
            notes.append(f"* {t}: {f['correction_note']}.")
    return lines + ([""] + notes if notes else []) + _natural_construction_markdown(nat)


def _audit_markdown(x: dict | None) -> str:
    if x is None:
        return "-"
    codes = x["last_finding_codes"]
    named = "codes not recorded" if codes is None else ", ".join(codes)
    return f"{x['revisions']} revision(s), " + ("passed" if x["passed"] else "failed" + (f" ({named})" if named else ""))


def _natural_construction_markdown(nat: dict) -> list[str]:
    """Each family's construction facts (:data:`CONSTRUCTION_RULE`), which the natural rule above announces."""
    fams = {t: f["construction"] for t, f in nat["families"].items() if "construction" in f}
    if not fams:
        return []
    lines = ["", "### Construction facts per family", "", _sentence(nat.get("construction_rule", CONSTRUCTION_RULE)), "",
             ("| Family | Reference contract: requirements, scored active, at the correction | Recovered contracts, scored "
              "active: initial-only, full-session | Checks: C1, C2, C3, C4, B2, B1, B3 | Checks: reference checks, labeler | "
              "C2 audit | C4 audit | B3 | Reference checks' status record |"),
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for t, c in fams.items():
        ref, con, n = c["contracts"].get("reference"), c["contracts"], c["checks"]
        rc = c["reference_checks"]
        status = (f"{_v(rc.get('status'))}; fix rounds {_v(rc.get('fix_rounds'))}" if rc.get("recorded") else "not recorded")
        lines.append(" | ".join([
            f"| {t}",
            "none" if ref is None else f"{ref['requirements']}, {ref['scored_active']}, {ref['at_correction']}",
            ", ".join(_v(con.get(v, {}).get("scored_active")) for v in ("initial_only", "full_session")),
            ", ".join(_v(n.get(k)) for k in ("initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform",
                                              "repo_tests", "diff_derived")),
            ", ".join(_v(n.get(k)) for k in ("reference_check", INDEPENDENT_LABELER)),
            _audit_markdown(c["audits"].get(VerifierCondition.initial_audited.value)),
            _audit_markdown(c["audits"].get(VerifierCondition.full_audited.value)),
            "available" if c["b3"]["available"] else f"not available ({c['b3']['why']})",
            status + (f" ({rc['why']})" if rc.get("why") else "") + " |"]))
    return lines


def _funnel_markdown(f: dict) -> list[str]:
    lines = ["", "## Funnel S1 to S11, both samples", "", _sentence(f["rule"]), ""]
    if isinstance(f["stages"], list):
        lines += ["| Stage | Unit | Count | PRs | Repositories |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {st['stage']} | {_v(st['unit'])} | {_v(st['count'])} | {_v(st['prs'])} | {_v(st['repositories'])} |"
                  for st in f["stages"]]
    else:
        lines.append(f"S1 to S8a: not recorded ({f['stages']['why']}).")
    lines += ["", ("| S9 sample | Comments | Judged | Qualifying | Excluded (judges disagree) | Failed | Qualifying PRs | "
                   "Qualifying repositories | Families |"), "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    reasons = []
    for sample, d in f["S9"].items():
        if not d["recorded"]:
            lines.append(f"| {sample} | not recorded ({d['why']}) | - | - | - | - | - | - | - |")
            continue
        lines.append(f"| {sample} | {_v(d['comments'])} | {_v(d['judged'])} | {_v(d['qualifying'])} | "
                     f"{_v(d['excluded_judges_disagree'])} | {_v(d['failed'])} | {_v(d['qualifying_prs'])} | "
                     f"{_v(d['qualifying_repositories'])} | {_v(d['families'])} |")
        if d["failed_by_reason"]:
            reasons.append(f"* S9, {sample}: " + "; ".join(f"{k.replace('_', ' ')} {n}" for k, n in d["failed_by_reason"].items()))
    lines += ["", "| S10 sample | Index rows | Roles | S10 outcomes | S11 (accepted) |", "| --- | --- | --- | --- | --- |"]
    for sample, d in f["S10_S11"].items():
        roles = ", ".join(f"{k} {n}" for k, n in d["roles"].items())
        outcomes = ", ".join(f"{k} {n}" for k, n in d["outcomes"].items())
        lines.append(f"| {sample} | {d['rows']} | {roles} | {outcomes} | {len(d['s11'])}: {', '.join(d['s11']) or 'none'} |")
        reasons += [f"* S10, {sample}, {cat} ({len(ids)}): {', '.join(ids)}" for cat, ids in d["rejected_by_reason"].items()]
    lines += ["", f"S11: {f['S11']['accepted']} accepted task(s) over both samples ("
              + (", ".join(f"{k} {n}" for k, n in f["S11"]["by_sample"].items()) or "none") + ")."]
    if reasons:
        lines += ["", "Reasons:", ""] + reasons
    return lines


def _reliability_markdown(r: dict) -> list[str]:
    lines = ["", "## Build and replay reliability", "", _sentence(r["rule"]), "",
             ("| Family | S10 | Base tests: passed / failed / error / skipped | Reconstruction | Image id: run = snapshot = S10 | "
              "Reference passes (every verifier) | No-op passes | Pairs | Unresolved | Infrastructure |"),
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for t, d in r["families"].items():
        bt = d["s10"]["base_tests"].get("counts") or {}
        counts = " / ".join(_v(bt.get(k)) for k in ("passed", "failed", "error", "skipped")) if bt else "-"
        if d["s10"]["base_tests"].get("timed_out"):
            counts += " (timed out)"
        rec = d["reconstruction"]
        sane = {o: (f"{sum(x['pass'] for x in v.values())}/{sum(x['n'] for x in v.values())}" if v else "-")
                for o, v in (("reference", d["sanity"].get("reference", {})), ("noop", d["sanity"].get("noop", {})))}
        infra = ", ".join(f"{k} {n}" for k, n in d["infrastructure"].items()) or "none"
        lines.append(f"| {t} | {_v(d['s10']['outcome'])} | {counts} | {_v(rec['status'])} ({_v(rec['fidelity'])}) | "
                     f"{'yes' if d['image_id']['match'] else 'no'} | {sane['reference']} | {sane['noop']} | {d['pairs']} | "
                     f"{d['unresolved']} | {infra} |")
    run = r["run"]
    infra = ", ".join(f"{k} {n}" for k, n in run["infrastructure"].items()) or "none"
    return lines + ["", (f"The run: {run['pairs']} pairs; {run['unresolved']} unresolved (repeats that disagree, counted as "
                         f"rejections, protocol §15.3); infrastructure outcomes: {infra}.")]


def _cost_markdown(c: dict) -> list[str]:
    def num(x) -> str:
        return "n/a" if x is None else (f"{x:.1f}" if isinstance(x, float) else str(x))

    lines = ["", "## Cost and time per accepted task", "", _sentence(c["rule"]), "",
             ("| Family | Generated artifacts with a record | Turns | Tool calls | Agent wall time (s) | Tokens | "
              "Grading wall time (s) | S10 (s) | S10 fetch bytes of its repository | Without a record |"),
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for t, f in c["families"].items():
        shared = f" (shared with {', '.join(f['fetch_repository_shared_with'])})" if f.get("fetch_repository_shared_with") else ""
        lines.append(f"| {t} | {f['recorded']}/{f['artifacts']} | {num(f['turns'])} | {num(f['tool_calls'])} | {num(f['wall_s'])} | "
                     f"{num(f['tokens'])} | {num(f['grading_wall_s'])} | {num(f['s10_seconds'])} | {num(f['fetch_bytes'])}{shared} | "
                     f"{', '.join(f['unrecorded']) or 'none'} |")
    tot, per = c["totals"], c["per_accepted_task"]
    lines.append(f"| All {c['n_families']} families | - | {num(tot['turns'])} | {num(tot['tool_calls'])} | {num(tot['wall_s'])} | "
                 f"{num(tot['tokens'])} | {num(tot['grading_wall_s'])} | {num(tot['s10_seconds_run_families'])} | "
                 f"{num(tot['fetch_bytes_of_the_run_repositories'])} | - |")
    lines.append(f"| Per accepted task | - | {num(per['turns'])} | {num(per['tool_calls'])} | {num(per['wall_s'])} | "
                 f"{num(per['tokens'])} | {num(per['grading_wall_s'])} | see S10 below | see S10 below | - |")
    every = c.get("s10_every_family", {})
    timed = (f"{every.get('n_processed', 0)} processed; a recorded time for {every.get('n_families', 0)} of them"
             if every.get("n_processed") is not None else "-")
    lines += ["", ("S10 per accepted task, its time and its fetches counted on one basis: the S10 work of every family S10 "
                   "processed, both samples, rejected families included, divided by the run's families. The run's families "
                   "alone are given below it."), "",
              ("| S10 work | Families | Build time (s) | Fetches (s) | Fetch bytes | Build time per accepted task (s) | "
               "Fetches per accepted task (s) | Fetch bytes per accepted task |"), "| --- | --- | --- | --- | --- | --- | --- | --- |",
              (f"| Every family S10 processed | {timed} | {num(tot['s10_seconds_every_family'])} | "
               f"{num(tot['fetch_seconds_all_s10'])} | {num(tot['fetch_bytes_all_s10'])} | "
               f"{num(per['s10_seconds_every_family'])} | {num(per['fetch_seconds_all_s10'])} | {num(per['fetch_bytes_all_s10'])} |"),
              (f"| The run's families alone (their repositories' fetches) | {c['n_families']} | "
               f"{num(tot['s10_seconds_run_families'])} | - | {num(tot['fetch_bytes_of_the_run_repositories'])} | "
               f"{num(per['s10_seconds_run_families'])} | - | {num(per['fetch_bytes_of_the_run_repositories'])} |")]
    if every.get("processed_not_in_index"):
        lines += ["", ("Counted, with an S10 record under the tasks root but no S10 outcome in the committed index: "
                       + ", ".join(every["processed_not_in_index"]) + ".")]
    if every.get("not_built"):
        lines += ["", f"Not built by S10, so with no S10 work: {', '.join(every['not_built'])}."]
    lines += ["", "Not recorded, so not counted:", ""]
    return lines + [f"* {x}" for x in c["unrecorded"]]


def _repository_markdown(v: dict) -> list[str]:
    """The exploratory view clustered by repository (D64, decision 10)."""
    names = list(v["clusters"])
    shared = ", ".join(v["shared"]) or "none (every family has a repository of its own, so the clusters are the families)"
    alone = (f" Without a repository id in the index, each its own cluster: {', '.join(v['no_repository_id'])}."
             if v.get("no_repository_id") else "")
    lines = ["", "## Exploratory view clustered by repository (not pre-specified)", "", _sentence(v["rule"]), "",
             f"{len(names)} cluster(s); the families of one repository: {shared}.{alone}", "",
             ("(numerator/denominator) per repository cluster under D19, each distinct graded patch once; the reference "
              "solution and the no-op are excluded."), "",
             "| Condition | " + " | ".join(f"{n} FA | {n} FR" for n in names) + " |",
             "| --- | " + " | ".join("--- | ---" for _ in names) + " |"]
    for c, pc in v["per_cluster"].items():
        cells = []
        for n in names:
            x = pc.get(n)
            cells += ["-", "-"] if x is None else [f"{x['fa_num']}/{x['fa_den']}", f"{x['fr_num']}/{x['fr_den']}"]
        lines.append(f"| {c} | " + " | ".join(cells) + " |")
    unit = ("repository", "repositories")
    if v["comparisons"]:
        lines += _signflip_markdown(v["comparisons"], "### Paired comparisons over repositories (D19 labels): exact sign-flip "
                                    "tests", "same candidates, each distinct graded patch once; exploratory", unit)
    if v["source_evidence_comparisons"]:
        lines += _signflip_markdown(v["source_evidence_comparisons"], "### Paired comparisons over repositories under the "
                                    "source-evidence labels", "the pre-review states, each once; exploratory", unit)
    return lines


def _natural_sections_markdown(nat: dict) -> list[str]:
    return (_natural_flags_markdown(nat) + _funnel_markdown(nat["funnel"]) + _reliability_markdown(nat["reliability"])
            + _cost_markdown(nat["cost"]))


def _per_family_sanity_lines(sanity: dict, name: Callable[[str], str] = _plain) -> list[str]:
    fams = _families_of(sanity)
    lines = ["| Condition | " + " | ".join(f"{f} reference | {f} no-op" for f in fams) + " |",
             "| --- | " + " | ".join("--- | ---" for _ in fams) + " |"]
    for c, d in sanity.items():
        cells = []
        for f in fams:
            for o in ("reference", "noop"):
                x = d.get(f, {}).get(o)
                cells.append("-" if not x else f"{x['pass']}/{x['n']}")
        lines.append(f"| {name(c)} | " + " | ".join(cells) + " |")
    return lines


def _case_study_markdown(a: dict) -> str:
    """The analysis of a natural run in case-study mode (§19.6): per-family tables only."""
    meta, nat, name = a["meta"], a["natural"], _condition_namer(a)
    lines = [f"# Analysis ({meta['label_policy']})", ""] + _natural_banner(a)
    lines += [f"Tasks: {a['n_tasks']} | independent task families: {a['n_families']} | results: {meta['n_results']}", ""]
    if "automated pilot" in meta["label_policy"]:
        lines += ["> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth.", ""]
    pops = meta.get("populations")
    if pops:
        lines += [f"Population: {_describe(pops)}.", ""]
    if meta.get("first_prompt_fallback"):
        fb = meta["first_prompt_fallback"]
        lines += [f"> **First prompt not read from the session** for {', '.join(fb['tasks'])}: {fb['rule']}.", ""]
    sec = ", ".join(meta.get("secondary_conditions", {}).get("conditions", []))
    lines += ["## Primary display: false acceptance and false rejection per task family", "",
              ("(numerator/denominator) per task family under D19, each distinct graded patch once; the reference solution and "
               f"the no-op are excluded (see the sanity checks), and so is the secondary condition ({sec or 'none'}). No column "
               "pools the families (case-study mode, §19.6)."), ""]
    lines += _family_rates_lines(a["per_family"])
    if a.get("secondary"):
        lines += _secondary_markdown(a["secondary"], case_study=True)
    if a.get("source_evidence"):
        lines += _natural_source_markdown(a["source_evidence"], case_study=True)
    if a.get("independent_labeling"):
        lines += _independent_case_markdown(a["independent_labeling"], name)
    lines += ["", "## Sanity checks per family (excluded from FA and FR)", "",
              "Passes of the reference solution and of the no-op (the run's grading, numerator/denominator).", ""]
    lines += _per_family_sanity_lines(a["sanity_per_family"], name)
    lines += _distinct_markdown(a["distinct_patches"])
    og = a["oracle_gated"]
    lines += ["", "## Oracle-gated view per family (secondary)", "", _sentence(og["rule"]), "",
              "| Condition | Cells kept | Dropped | Lost yield per family (invalid / valid) |", "| --- | --- | --- | --- |"]
    for c, d in og["conditions"].items():
        dropped = "; ".join(f"{t}: {why}" for t, why in d["dropped"].items()) or "-"
        lost = ", ".join(f"{f} {x['invalid']} / {x['valid']}" for f, x in d["lost_yield_per_family"].items()) or "-"
        lines.append(f"| {name(c)} | {d['cells_kept']}/{d['cells']} | {dropped} | {lost} |")
    lines += ["", "False acceptance and false rejection on the cells kept:", ""]
    lines += _family_rates_lines({c: d["per_family"] for c, d in og["conditions"].items()}, name)
    lines += ["", "## Accepted negatives by type, per family", "",
              "| Condition | Family | correction-violating | initial-violating | unspecified |", "| --- | --- | --- | --- | --- |"]
    for c, fams in a["by_negative_type_per_family"].items():
        for f, bt in fams.items():
            cells = [f"{bt[k]['accepted']}/{bt[k]['n']}" if k in bt else "-"
                     for k in ("correction_violating", "initial_violating", "unspecified")]
            lines.append(f"| {name(c)} | {f} | " + " | ".join(cells) + " |")
    for key, title in (("sensitivity_every_candidate_per_family", "Every held-out candidate (duplicates included, for comparison)"),
                       ("sensitivity_construction_labels_per_family",
                        "Exploratory sensitivity: construction-intent labels (not pre-specified)"),
                       ("sensitivity_check_labels_per_family", "Post hoc: the independent construction checks' labels"),
                       ("sensitivity_without_duplicates_per_family", "Post hoc: without held-out duplicates")):
        if a.get(key):
            lines += ["", f"## {title}, per family", ""] + _family_rates_lines(a[key], name)
    if a.get("near_miss_per_family"):
        lines += ["", "## Post hoc: near misses accepted, by D19 status, per family", "",
                  "| Condition | Family | D19-confirmed invalid | D19 ambiguous |", "| --- | --- | --- | --- |"]
        for c, fams in a["near_miss_per_family"].items():
            for f, d in fams.items():
                lines.append(f"| {name(c)} | {f} | {d['confirmed_invalid']['accepted']}/{d['confirmed_invalid']['n']} | "
                             f"{d['ambiguous']['accepted']}/{d['ambiguous']['n']} |")
    if a.get("duplicates"):
        lines += ["", "## Held-out candidates that duplicate another candidate", ""]
        lines += [f"* {cid}: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in d.items() if k != "task_id")
                  for cid, d in a["duplicates"].items()]
    if a.get("b1_upstream_only_per_family"):
        lines += ["", "## Post hoc: B1 restricted to the base commit's own tests, per family", ""]
        lines += _family_rates_lines({"repo_tests_upstream": a["b1_upstream_only_per_family"]["per_family"]})
    lines += _natural_sections_markdown(nat)
    lines += _labels_markdown(a) + _coverage_markdown(a)
    lines += _per_task_markdown(a, any("stratum" in r for t in a["per_task"].values() for rs in t.values() for r in rs))
    return "\n".join(lines) + "\n"


def _labels_markdown(a: dict) -> list[str]:
    """The labels and human-review queue per task (and stratum)."""
    lines: list[str] = []
    if a.get("labels"):
        lines += ["", "## Labels and human-review queue", "", "| Task | valid | invalid | ambiguous | unlabeled | queued for review |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for t, d in a["labels"].items():
            lines.append(_label_row(t, d))
            lines += [_label_row(f"{t} (stratum {s})", sd) for s, sd in d.get("strata", {}).items()]
        d19 = {t: d["d19"] for t, d in a["labels"].items() if "d19" in d}  # a natural run only (D19_RULE)
        if d19:
            lines += ["", ("D19's proposals per task (valid, invalid, ambiguous, unlabeled), with the reason category of each "
                           "candidate D19 labels ambiguous (natural.d19_rule):"), ""]
            lines += [f"* {t}: {x['valid']}, {x['invalid']}, {x['ambiguous']}, {x['unlabeled']}; ambiguous: "
                      + ("; ".join(f"{cid} ({why})" for cid, why in x["ambiguous_reasons"].items()) or "none")
                      for t, x in d19.items()]
    return lines


def _coverage_markdown(a: dict) -> list[str]:
    """Contract recovery per task and variant (model mappings)."""
    lines: list[str] = []
    if a.get("coverage"):
        lines += ["", "## Contract recovery (model mappings, proposals)", "",
                  "| Task | Variant | Coverage of active reference requirements (mapper 1) | Covered but contradicted | Unsupported | Contradicting | Coverage (mapper 2) | Mapping agreement (kappa) |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for t, cov in a["coverage"].items():
            ag = a.get("mapping_agreement", {}).get(t, {})
            for v, d in cov.get("variants", {}).items():
                d2 = cov.get("variants_mapper2", {}).get(v)
                k = ag.get(v, {}).get("kappa")
                lines.append(f"| {t} | {v} | {_fmt(d['coverage'], len(d['covered']), len(cov['reference_scored']))} | "
                             f"{', '.join(d.get('covered_but_contradicted', [])) or '-'} | "
                             f"{len(d['unsupported'])}/{d['n_recovered_scored']} | {len(d['contradicting'])} | "
                             f"{_fmt(d2['coverage'], len(d2['covered']), len(cov['reference_scored'])) if d2 else '-'} | "
                             f"{'n/a' if k is None else f'{k:.2f}'} |")
    return lines


def _per_task_markdown(a: dict, strat: bool) -> list[str]:
    """Each task's held-out candidates with their origin, label, negative type and outcome under each condition."""
    lines = ["", "## Per-task outcomes", ""]
    for t, conds in a["per_task"].items():
        lines += [f"### {t}", "", f"| Candidate | {'Stratum | ' if strat else ''}Origin | Label | Negative type | " + " | ".join(conds) + " |",
                  f"| --- | {'--- | ' if strat else ''}--- | --- | --- | " + " | ".join("---" for _ in conds) + " |"]
        cands: dict[str, dict] = {}
        for c, rs in conds.items():
            for r in rs:
                cands.setdefault(r["candidate"], {"origin": r["origin"], "label": r["label"], "nt": r["negative_type"],
                                                  "stratum": r.get("stratum", "")})[c] = r["outcome"]
        for cid, d in sorted(cands.items()):
            lines.append(f"| {cid} | {d['stratum'] + ' | ' if strat else ''}{d['origin']} | {d['label']} | {d['nt'] or '-'} | "
                         + " | ".join(d.get(c, "-") for c in conds) + " |")
        lines.append("")
    return lines


def to_markdown(a: dict) -> str:
    if a["meta"].get("case_study", {}).get("applies"):  # a natural run in case-study mode (§19.6): per family only
        return _case_study_markdown(a)
    new = "reporting_rules" in a["meta"]  # a new run: the reporting rules of protocol §15.7 (module docstring)
    name = _condition_namer(a)  # marks a natural run's secondary condition (B3); names any other run's as they are
    sens = a["meta"].get("sensitivity")  # the sensitivity view (protocol §18.1), said first
    lines = [f"# {'Sensitivity analysis' if sens else 'Analysis'} ({a['meta']['label_policy']})", ""]
    if sens:
        lines += _sensitivity_markdown(sens)
    lines += [f"Tasks: {a['n_tasks']} | independent task families: {a['n_families']} | results: {a['meta']['n_results']}", ""]
    if "automated pilot" in a["meta"]["label_policy"]:
        lines += ["> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth. "
                  "With this few task families the intervals are not meaningful evidence of an effect.", ""]
    pops = a["meta"].get("populations")
    if pops and len(pops) > 1:
        lines += [f"> **Populations pooled** (`--pool-populations`). This run mixes {len(pops)} populations "
                  f"({_describe(pops)}). The tables below pool them; each population is reported separately "
                  "under \"By population\".", ""]
    elif pops:
        lines += [f"Population: {_describe(pops)}.", ""]
    if a.get("natural"):
        lines += _natural_banner(a)
    if a["meta"].get("first_prompt_fallback"):
        fb = a["meta"]["first_prompt_fallback"]
        lines += [f"> **First prompt not read from the session** for {', '.join(fb['tasks'])}: {fb['rule']}.", ""]
    if new:
        lines += _rules_markdown(a) + [""]
        if a.get("secondary"):
            lines += _secondary_markdown(a["secondary"], case_study=False) + [""]
        lines += ["## Pooled false acceptance / false rejection by condition", "",
                  "Pooled rates with (numerator/denominator), each distinct graded patch once; reference solution and no-op are "
                  "excluded (see sanity table). The exact (Clopper-Pearson) interval ignores clustering and is given only as a "
                  "reference scale; the cluster-bootstrap intervals are in the appendix.", ""]
    else:
        lines += ["## False acceptance / false rejection by condition", "",
                  "Rates with (numerator/denominator) and 95% cluster-bootstrap interval over task families where computable. "
                  "Reference solution and no-op are excluded (see sanity table).", "",
                  "Intervals marked * are degenerate (every family has the same rate, so resampling families cannot vary them); "
                  "the exact (Clopper-Pearson) interval ignores clustering and is given only as a reference scale.", ""]
    lines += ["| Condition | False acceptance | FA exact 95% | FA macro | False rejection | FR exact 95% | FR macro | Youden's J | Tasks with an accepted negative | Infra outcomes | Excluded (unlabeled/ambiguous) |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c, d in a["conditions"].items():
        fa, fr = d["false_acceptance"], d["false_rejection"]
        j = "n/a" if d.get("youden_j") is None else f"{d['youden_j']:+.2f}"
        tn = d.get("tasks_with_any_accepted_negative", {"num": 0, "den": 0})
        ex = lambda x: "n/a" if not x.get("exact95") else f"[{x['exact95'][0]:.2f}, {x['exact95'][1]:.2f}]"  # noqa: E731
        mac = lambda x: "n/a" if x.get("macro") is None else f"{x['macro']:.2f}"  # noqa: E731
        star = lambda x: "*" if not new and x.get("ci95_degenerate") else ""  # noqa: E731
        ci = lambda x: None if new else x["ci95"]  # noqa: E731
        lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], ci(fa))}{star(fa)} | {ex(fa)} | {mac(fa)} | "
                     f"{_fmt(fr['rate'], fr['num'], fr['den'], ci(fr))}{star(fr)} | {ex(fr)} | {mac(fr)} | {j} | "
                     f"{tn['num']}/{tn['den']} | {d['infrastructure']['num']}/{d['infrastructure']['den']} | {d['excluded_unlabeled_or_ambiguous']} |")
    degenerate = "" if new else " Intervals marked * are degenerate."
    if a.get("by_population"):
        lines += _group_markdown("By population", "Each population on its own rows, with its own task families "
                                 "(reference solution and no-op excluded). The tables above pool the populations." + degenerate,
                                 a["by_population"], with_ci=not new)
    if a.get("by_stratum"):
        lines += _group_markdown("By candidate stratum", f"`{TASK_STRATUM}` is the task's own candidates (task.json); every "
                                 "other stratum's candidates are listed in tasks/<id>/strata/<name>.json (reference solution "
                                 "and no-op excluded). The tables above pool the strata." + degenerate,
                                 a["by_stratum"], with_ci=not new)
    if a.get("fresh_attempts"):
        lines += _fresh_markdown(a["fresh_attempts"], sensitivity=bool(sens))
    if a.get("source_evidence"):
        lines += _source_markdown(a["source_evidence"])
    if a.get("independent_labeling"):
        lines += _independent_markdown(a["independent_labeling"], name)
    if new:
        lines += _oracle_markdown(a["oracle_gated"], name) + _distinct_markdown(a["distinct_patches"])
    if a.get("repository_clustered"):  # a natural run with 10 or more accepted tasks (D64, decision 10)
        lines += _repository_markdown(a["repository_clustered"])
    if a.get("natural"):
        lines += _natural_sections_markdown(a["natural"])
    lines += ["", "## Accepted negatives by type", "", "| Condition | correction-violating | initial-violating | unspecified |", "| --- | --- | --- | --- |"]
    for c in a["conditions"]:
        bt = a["by_negative_type"].get(c, {})
        cell = lambda k: f"{bt[k]['accepted']}/{bt[k]['n']}" if k in bt else "-"  # noqa: E731
        lines.append(f"| {c} | {cell('correction_violating')} | {cell('initial_violating')} | {cell('unspecified')} |")
    lines += ["", "## Sanity checks (excluded from primary metrics)", "", "| Condition | reference passes | no-op passes |", "| --- | --- | --- |"]
    for c, s in a["sanity"].items():
        ref = s.get("reference", {})
        noop = s.get("noop", {})
        lines.append(f"| {name(c)} | {ref.get('pass', '-')}/{ref.get('n', '-')} | {noop.get('pass', '-')}/{noop.get('n', '-')} |")
    if not new:  # a new run shows these in its primary display and the appendix
        lines += ["", "## Per-family rates behind the macro rates", "",
                  "| Condition | " + " | ".join(f"{t} FA | {t} FR" for t in sorted(a["per_task"])) + " |",
                  "| --- | " + " | ".join("--- | ---" for _ in a["per_task"]) + " |"]
        for c, d in a["conditions"].items():
            pt = d.get("per_task_rates", {})
            cells = []
            for t in sorted(a["per_task"]):
                x = pt.get(t)
                cells += ["-", "-"] if x is None else [f"{x['fa_num']}/{x['fa_den']}", f"{x['fr_num']}/{x['fr_den']}"]
            lines.append(f"| {c} | " + " | ".join(cells) + " |")
        lines += ["", "## Paired comparisons (same candidates)", "",
                  "Intervals marked * are degenerate (every family has the same difference).", "",
                  "| A | B | Metric | A - B | 95% CI | n labeled for metric | families | A acc & B rej | A rej & B acc |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for d in a["comparisons"]:
            diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
            ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]" + ("*" if d.get("ci95_degenerate") else "")
            lines.append(f"| {d['a']} | {d['b']} | {d['metric'].upper()} | {diff} | {ci} | {d.get('n_metric', d['n_common'])} | {d['n_families']} | "
                         f"{d['discordant']['a_accepts_b_rejects']} | {d['discordant']['a_rejects_b_accepts']} |")
    if a.get("sensitivity_construction_labels"):
        lines += ["", "## Exploratory sensitivity: construction-intent labels (protocol v0.3; not pre-specified)", "",
                  "Constructed candidates labeled by how they were built (near miss = invalid, alternative = valid), "
                  "including those the D19 rule marked ambiguous; the observed pre-correction state keeps its D19 label." + degenerate,
                  "", "| Condition | False acceptance | FA exact 95% | False rejection | FR exact 95% |", "| --- | --- | --- | --- | --- |"]
        for c, d in a["sensitivity_construction_labels"].items():
            st = lambda k: "*" if not new and d.get(f"{k}_ci95_degenerate") else ""  # noqa: E731
            exs = lambda k: "n/a" if not d.get(f"{k}_exact95") else f"[{d[k + '_exact95'][0]:.2f}, {d[k + '_exact95'][1]:.2f}]"  # noqa: E731
            sci = lambda k: None if new else d[f"{k}_ci95"]  # noqa: E731
            lines.append(f"| {name(c)} | {_fmt(d['fa'], d['fa_num'], d['fa_den'], sci('fa'))}{st('fa')} | {exs('fa')} | "
                         f"{_fmt(d['fr'], d['fr_num'], d['fr_den'], sci('fr'))}{st('fr')} | {exs('fr')} |")
    if a.get("near_miss_crosstab"):
        lines += ["", "## Post-hoc analyses after the internal review (exploratory, not pre-specified)", "",
                  "### Near misses accepted, by label status", "", "| Condition | D19-confirmed invalid | D19 ambiguous |", "| --- | --- | --- |"]
        for c, d in a["near_miss_crosstab"].items():
            lines.append(f"| {name(c)} | {d['confirmed_invalid']['accepted']}/{d['confirmed_invalid']['n']} | {d['ambiguous']['accepted']}/{d['ambiguous']['n']} |")
    if a.get("sensitivity_check_labels"):
        lines += ["", "### Rates under the independent construction checks' labels", "",
                  "| Condition | False acceptance | False rejection |", "| --- | --- | --- |"]
        for c, d in a["sensitivity_check_labels"].items():
            lines.append(f"| {name(c)} | {_fmt(d['fa'], d['fa_num'], d['fa_den'])} | {_fmt(d['fr'], d['fr_num'], d['fr_den'])} |")
    if a.get("duplicates"):
        lines += ["", "### Held-out candidates that duplicate another candidate (same graded patch, or same code apart from comments and docstrings)", ""]
        for cid, d in a["duplicates"].items():
            lines.append(f"* {cid}: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in d.items() if k != "task_id"))
        lines += ["", "| Condition | FA without duplicates | FR without duplicates |", "| --- | --- | --- |"]
        for c, d in a.get("sensitivity_without_duplicates", {}).items():
            lines.append(f"| {name(c)} | {_fmt(d['fa'], d['fa_num'], d['fa_den'])} | {_fmt(d['fr'], d['fr_num'], d['fr_den'])} |")
    if a.get("b1_upstream_only"):
        d = a["b1_upstream_only"]
        lines += ["", "### B1 restricted to the base commit's own tests (checks added by the session agent removed)", "",
                  f"False acceptance {_fmt(d['fa'], d['fa_num'], d['fa_den'])}; false rejection {_fmt(d['fr'], d['fr_num'], d['fr_den'])}."]
    lines += _labels_markdown(a) + _coverage_markdown(a)
    lines += _per_task_markdown(a, bool(a.get("by_stratum")))  # a Stratum column only for a run with candidate strata
    if new:
        lines += _bootstrap_appendix(a)[1:] + [""]
    return "\n".join(lines) + "\n"


def _coverage_one(c: TaskContract, mapping: dict, ref_scored: set[str]) -> dict:
    rec = {r.req_id for r in c.active() if r.scored}
    contra = {rid: set(mapping.get("contradicts", {}).get(rid, [])) for rid in rec}
    # A recovered requirement covers a reference requirement it maps to, unless its
    # test would reject solutions satisfying that requirement (a contradiction).
    covered = {x for rid in rec for x in mapping["map"].get(rid, []) if x not in contra[rid]} & ref_scored
    unsupported = sorted(rid for rid in rec if not set(mapping["map"].get(rid, [])) & ref_scored)
    contradicting = sorted(rid for rid in rec if contra[rid] & ref_scored)
    # Covered by one recovered requirement but contradicted by another one (reported, not subtracted).
    contradicted_anywhere = {x for rid in rec for x in contra[rid]}
    covered_but_contradicted = sorted(covered & contradicted_anywhere)
    return {"mapper_kind": mapping.get("mapper_kind"), "mapper": mapping.get("mapper"),
            "coverage": len(covered) / len(ref_scored) if ref_scored else None,
            "covered": sorted(covered), "missing": sorted(ref_scored - covered),
            "n_recovered_scored": len(rec), "unsupported": unsupported,
            "unsupported_rate": (len(unsupported) / len(rec)) if rec else None,
            "contradicting": contradicting, "covered_but_contradicted": covered_but_contradicted,
            "superseded_requirements": sorted(r.req_id for r in c.requirements if r.status.value == "superseded" and r.scored)}


def contract_coverage(task_dir: Path) -> dict:
    """Requirement coverage / unsupported / contradicting rates of recovered contracts.

    Reads ``contracts/mapping_<variant>.json`` (mapper 1) and, when present,
    ``contracts/mapping2_<variant>.json`` (an independent second mapper):
    ``{"mapper": ..., "mapper_kind": "human"|"model", "map": {recovered_id: [reference_ids]},
    "contradicts": {recovered_id: [reference_ids]}}``. Model mappings are proposals.
    """
    m = load(task_dir / "task.json", TaskManifest)
    out: dict = {"task_id": m.task_id, "variants": {}, "variants_mapper2": {}}
    if "reference" not in m.contracts or not (task_dir / m.contracts["reference"]).exists():
        out["reference_scored"] = []
        return out
    ref = load(task_dir / m.contracts["reference"], TaskContract)
    ref_scored = {r.req_id for r in ref.active() if r.scored}
    out["reference_scored"] = sorted(ref_scored)
    for variant in ("initial_only", "full_session"):
        if variant not in m.contracts:
            continue
        c = load(task_dir / m.contracts[variant], TaskContract)
        for prefix, key in (("mapping_", "variants"), ("mapping2_", "variants_mapper2")):
            mp = task_dir / "contracts" / f"{prefix}{variant}.json"
            if mp.exists():
                out[key][variant] = _coverage_one(c, json.loads(mp.read_text()), ref_scored)
    return out


def cohen_kappa(a: list[int], b: list[int]) -> float | None:
    """Cohen's kappa for two binary raters over the same units."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1:
        return 1.0 if po == 1 else None
    return (po - pe) / (1 - pe)


def mapping_agreement(task_dir: Path) -> dict:
    """Agreement of the two independent mappers over (recovered, reference) requirement pairs."""
    m = load(task_dir / "task.json", TaskManifest)
    out: dict = {}
    if "reference" not in m.contracts or not (task_dir / m.contracts["reference"]).exists():
        return out
    ref = load(task_dir / m.contracts["reference"], TaskContract)
    ref_ids = sorted(r.req_id for r in ref.requirements)  # include superseded: mappers may map to them
    for variant in ("initial_only", "full_session"):
        p1, p2 = task_dir / "contracts" / f"mapping_{variant}.json", task_dir / "contracts" / f"mapping2_{variant}.json"
        if variant not in m.contracts or not (p1.exists() and p2.exists()):
            continue
        c = load(task_dir / m.contracts[variant], TaskContract)
        rec = sorted(r.req_id for r in c.active() if r.scored)
        m1, m2 = json.loads(p1.read_text()), json.loads(p2.read_text())
        res = {}
        for field in ("map", "contradicts"):
            a = [int(x in m1.get(field, {}).get(rid, [])) for rid in rec for x in ref_ids]
            b = [int(x in m2.get(field, {}).get(rid, [])) for rid in rec for x in ref_ids]
            res[field] = {"units": len(a), "agreement": (sum(x == y for x, y in zip(a, b)) / len(a)) if a else None,
                          "kappa": cohen_kappa(a, b),
                          "disagreements": [f"{rid}->{x}" for rid in rec for x in ref_ids
                                            if (x in m1.get(field, {}).get(rid, [])) != (x in m2.get(field, {}).get(rid, []))]}
        out[variant] = {"kappa": res["map"]["kappa"], "agreement": res["map"]["agreement"], "units": res["map"]["units"],
                        "map": res["map"], "contradicts": res["contradicts"]}
    return out


def label_summary(task_dirs: list[Path], strata: dict[str, dict[str, list[Candidate]]] | None = None, *,
                  natural: bool = False) -> dict:
    """Proposed-label counts per task and the queue of candidates needing human review.

    Queued: candidates the D19 rule marked ambiguous, candidates without a proposal,
    candidates whose independent construction check disagrees with the proposal
    (``labels/construction_checks.json``, advisory evidence only), and every fresh attempt
    without a final human label (protocol §15.4).

    ``strata`` (``{task_id: {stratum: candidates}}``) adds, under the task's ``strata`` key,
    the same summary for each stratum's candidates.

    ``natural`` (a natural run only, so the recorded runs keep their output) adds, under the
    task's ``d19`` key, D19's proposals and the reason category of each candidate D19 labels
    ambiguous (:data:`D19_RULE`).
    """
    out: dict = {}
    for tdir in task_dirs:
        m = load(tdir / "task.json", TaskManifest)
        checks_p = tdir / "labels" / "construction_checks.json"
        checks = json.loads(checks_p.read_text()).get("checks", {}) if checks_p.exists() else {}
        cands = [load(tdir / p, Candidate) for p in m.candidates]
        out[m.task_id] = _label_pool(cands, checks)
        if (strata or {}).get(m.task_id):
            out[m.task_id]["strata"] = {name: _label_pool(cs, checks) for name, cs in strata[m.task_id].items()}
        if natural:
            out[m.task_id]["d19"] = _d19_labels(cands)
    return out


def d19_reason_category(note: object) -> str:
    """The category of D19's reason for an ambiguous proposal (:data:`D19_RULE`), from the note of its label, whose head
    (up to the first ``" | "``) is the reason as scripts/propose_labels.py writes it."""
    if not isinstance(note, str) or not note.strip():
        return D19_NO_REASON
    reason = note.split(" | ", 1)[0].strip()
    if reason in D19_AMBIGUOUS_REASONS:
        return reason
    if _D19_REPEATS.fullmatch(reason):
        return D19_REPEATS_DISAGREE
    return D19_UNRECOGNISED


def _d19_labels(cands: list[Candidate]) -> dict:
    """D19's proposals for one task's held-out candidates (no reference, no no-op), each value counted, zero included, and
    the reason category of each candidate it labels ambiguous, by candidate id (:data:`D19_RULE`)."""
    counts = dict.fromkeys(("valid", "invalid", "ambiguous", "unlabeled"), 0)
    reasons: dict[str, str] = {}
    for c in cands:
        if c.split.value != "eval" or c.origin in (CandidateOrigin.noop, CandidateOrigin.reference):
            continue
        d19 = [lb for lb in c.labels if lb.labeler == PILOT_LABELER]  # the proposal candidate_label takes: the last one
        if not d19:
            counts["unlabeled"] += 1
            continue
        counts[d19[-1].value] += 1
        if d19[-1].value == "ambiguous":
            reasons[c.candidate_id] = d19_reason_category(d19[-1].note)
    return {**counts, "ambiguous_reasons": dict(sorted(reasons.items()))}


def _label_pool(cands: list[Candidate], checks: dict) -> dict:
    """Label counts, label rows and review queue of one pool of candidates (held-out ones; no reference, no no-op)."""
    counts: Counter = Counter()
    queue, rows = [], []
    for c in cands:
        if c.split.value != "eval" or c.origin in (CandidateOrigin.noop, CandidateOrigin.reference):
            continue
        lb = candidate_label(c, "pilot")
        value = lb.value if lb else "unlabeled"
        counts[value] += 1
        chk = checks.get(c.candidate_id)
        row = {"candidate": c.candidate_id, "origin": c.origin.value, "proposed": value,
               "violated": lb.violated_requirements if lb else []}
        rows.append(row)
        assessed = chk.get("assessed_label") if chk else None
        row["check_assessed"] = assessed
        disagree = value in ("valid", "invalid") and assessed in ("valid", "invalid") and assessed != value
        if c.human_disagreement():
            queue.append({**row, "reason": "human reviewers disagree; adjudication needed"})
        elif value in ("ambiguous", "unlabeled") or disagree:
            queue.append({**row, "reason": "ambiguous under D19" if value == "ambiguous" else
                          ("no proposal" if value == "unlabeled" else "construction check disagrees with proposal")})
        elif c.origin == CandidateOrigin.fresh_attempt and c.final_label() is None:
            queue.append({**row, "reason": "fresh attempt: every attempt is queued for human review (protocol §15.4)"})
    return {"counts": dict(counts), "candidates": rows, "review_queue": queue}
