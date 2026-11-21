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
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Sequence

from .metrics import ConditionSummary, Row, family_rates, paired_difference, paired_signflip, summarize
from .schemas import (
    Candidate, CandidateOrigin, LabelerKind, Population, TaskContract, TaskManifest, VerificationResult, VerifierCondition,
)
from .store import load, read_jsonl, write_json
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
        if refs[tid] is not None and refs[tid].requirements:
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


INDEPENDENT_RULE = ("the independent labeler (verifier independent_label, condition reference_check; protocol §15.5) labels a "
                    "candidate valid if it passes, invalid if it fails with task_failure, and ambiguous on any other outcome "
                    "(unresolved, environment failure, verifier error or timeout, recorded as such); a candidate it did not grade "
                    "is unlabeled. Its verdicts are a second labeling (§15.4): a model proposal, as D19 is, never a human label. "
                    "The labeler is label support, never an evaluated condition")
_LABEL_VALUES = ("valid", "invalid", "ambiguous")


def independent_label(outcome: str | None) -> str | None:
    """The second labeling's label of a candidate from the independent labeler's outcome (protocol §15.4); None if not graded."""
    if outcome is None:
        return None
    return "valid" if outcome == "pass" else "invalid" if outcome == "task_failure" else "ambiguous"


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
                          with_strata: bool, label_rule: str, exclude_origins: tuple[str, ...]) -> dict | None:
    """The independent labeler's verdicts as a second labeling (protocol §15.4, §15.5); None if the run did not grade it.

    ``every`` holds the held-out candidates' rows (reference and no-op excluded) with their primary labels; they
    are counted as the primary analysis counts them (``prepare``; for a new run each distinct graded patch once,
    ``patch_key``). Reported: the labels, the labeler's sanity outcomes (reference, no-op), FA and FR per condition
    under both labelings side by side with the per-family tables (pooled, and per candidate stratum for a run with
    strata), and the agreement between D19's proposals and the labeling, per stratum. Agreement on a controlled
    task's own candidates is exploratory: they existed before the labeler was written (§15.5).
    """
    graded = {k: v[INDEPENDENT_LABELER] for k, v in support.items() if INDEPENDENT_LABELER in v}
    if not graded:
        return None
    heldout = sorted({(r.task_id, r.candidate_id) for r in every})
    second = {k: independent_label(graded.get(k)) for k in heldout}
    d19 = {k: _d19_value(cands[k]) for k in heldout}
    origin = {k: cands[k].origin.value for k in heldout}
    stratum = {(r.task_id, r.candidate_id): r.stratum for r in every}
    population = {r.task_id: r.population for r in rows}
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
    out: dict = {
        "rule": INDEPENDENT_RULE, "verifier": INDEPENDENT_LABELER,
        "primary_labels": ("human labels" if label_rule == "human" else
                           "D19's proposals, or a human label where one exists (the label rule of the primary analysis)"),
        "tasks": sorted({k[0] for k in graded}),
        "labels": {v: counts.get(v, 0) for v in (*_LABEL_VALUES, "not_graded")},
        "ambiguous_outcomes": dict(sorted(Counter(graded[k] for k in heldout if second[k] == "ambiguous").items())),
        "candidates": {f"{t}/{cid}": {"label": second[(t, cid)], "outcome": graded.get((t, cid)), "d19": d19[(t, cid)],
                                      **({"stratum": stratum[(t, cid)]} if with_strata else {})} for t, cid in heldout},
        "sanity": sanity,
        "conditions": _side_by_side(prepare(every), prepare(second_every), conds),
    }
    names = sorted({stratum[k] for k in heldout}, key=lambda s: (s != TASK_STRATUM, s))
    if with_strata:
        out["by_stratum"] = {s: {"tasks": sorted({k[0] for k in heldout if stratum[k] == s}),
                                 "conditions": _side_by_side(prepare([r for r in every if r.stratum == s]),
                                                             prepare([r for r in second_every if r.stratum == s]), conds)}
                             for s in names}
    groups = {}
    for s in names:
        ks = [k for k in heldout if stratum[k] == s]
        tasks = sorted({k[0] for k in ks})
        exploratory = s == TASK_STRATUM and any(population[t] == Population.controlled.value for t in tasks)
        groups[s] = {"tasks": tasks, "exploratory": exploratory,
                     **({"why_exploratory": "these are the task's own candidates of controlled families, which existed "
                                            "before the labeler was written (protocol §15.5)"} if exploratory else {}),
                     **_agreement(_label_units(ks, patch_key, origin), d19, second, graded)}
    out["agreement"] = {
        "rule": "D19's proposal (labeler builder:refcheck+regression+construction:v1) against the second labeling, "
                + ("each distinct graded patch once (a unit's label is its members' when they agree, else ambiguous)"
                   if patch_key else "each candidate once")
                + "; the 2x2 table holds the units both label valid or invalid, the cross-table every unit (none: no D19 "
                  "proposal, or not graded by the labeler); per candidate stratum (§15.4 estimand 4, §15.5)",
        "by_stratum": groups,
        **({"pooled": {"exploratory": any(g["exploratory"] for g in groups.values()),
                       **_agreement(_label_units(heldout, patch_key, origin), d19, second, graded)}} if len(names) > 1 else {}),
    }
    return out


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
            rules: str | None = None, sensitivity_exclusions: Sequence[Path] = ()) -> dict:
    """Analyse a recorded run; write ``analysis.json`` and ``analysis.md`` into its directory and return the analysis.

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
    sources, also = read_sensitivity_exclusions(sensitivity_exclusions, tasks_root.parent) if sensitivity_exclusions else ([], {})

    def compute(also_exclude: dict[str, str] | None) -> dict:
        return _analysis(run_dir, tasks_root, allow_proposed=allow_proposed, n_boot=n_boot, exclude_origins=exclude_origins,
                         pool_populations=pool_populations, rules=rules, also_exclude=also_exclude)

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
              pool_populations: bool, rules: str | None, also_exclude: dict[str, str] | None = None) -> dict:
    """The analysis of a recorded run (see :func:`analyze`), written nowhere.

    ``also_exclude`` (``{attempt id: reason}``) makes it the sensitivity view: those fresh attempts are excluded
    as well, from every table, and ``meta.sensitivity`` says which were excluded here, which the primary
    analysis excludes already, and which listed ids name no attempt of the run.
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
                                   exclude_origins)
    fresh = _fresh_attempts(rows, cands, excluded, conds,
                            None if second is None else {k: independent_label(v.get(INDEPENDENT_LABELER))
                                                         for k, v in support.items()})
    if fresh is not None:
        out["fresh_attempts"] = fresh
    source = _source_evidence(rows, cands, conds)
    if source is not None:
        out["source_evidence"] = source
    if second is not None:  # only for a run that graded the independent labeler
        out["independent_labeling"] = second
    by_name: dict[str, dict[str, list[Candidate]]] = {}  # {task: {stratum: candidates}}
    for t, f in kept_cands.items():
        for name, _, c in f.values():
            by_name.setdefault(t, {}).setdefault(name, []).append(c)
    out["labels"] = label_summary([tasks_root / t for t in tasks], strata=by_name)
    out["coverage"] = {t: contract_coverage(tasks_root / t) for t in tasks}
    out["mapping_agreement"] = {t: mapping_agreement(tasks_root / t) for t in tasks}
    out["meta"]["inputs"] = _input_hashes(run_dir, [tasks_root / t for t in tasks],
                                          [(tasks_root / t, rel) for t, f in stratum_cands.items() for _, rel, _ in f.values()],
                                          ("stats.py",) if new_rules else ())
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
                  extra_code: tuple[str, ...] = ()) -> dict:
    """Revision and file hashes of every input the analysis read (labels, contracts, mappings, checks) and of its code.

    ``stratum_files`` are the stratum candidates read, as ``(task_dir, file relative to it)``; with any,
    the hashes also cover them and ``strata.py``, which reads them (it reads nothing for a run without strata).
    ``extra_code`` names further modules that this analysis ran (``stats.py`` under the reporting rules of a new run).
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
    dup: dict = {}
    for t in sorted({r.task_id for r in rows}):
        m = load(tasks_root / t / "task.json", TaskManifest)
        cands = [load(tasks_root / t / p, Candidate) for p in m.candidates] + (stratum_cands or {}).get(t, [])
        dev = {_norm_patch(c.patch): c.candidate_id for c in cands if c.split.value == "dev" and c.patch}
        seen: dict[str, str] = {}
        for c in sorted(cands, key=lambda c: (c.origin != CandidateOrigin.observed_pre_correction, c.candidate_id)):
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
    out["duplicates"] = dup
    if dup:
        drows = [r for r in primary if r.candidate_id not in dup]
        out["sensitivity_without_duplicates"] = {}
        for c in conds:
            ss = summarize(drows, condition=c, n_boot=n_boot)
            out["sensitivity_without_duplicates"][c] = {"fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den,
                                                        "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den}
    # 4. B1 restricted to checks that exist in the base commit's own tests (not added by the agent).
    up: dict[str, set] = {}
    for t in sorted({r.task_id for r in rows}):
        f = tasks_root / t / "verifiers" / "repo_tests" / "upstream_check_ids.json"
        if f.exists():
            up[t] = set(json.loads(f.read_text())["upstream_check_ids"])
    if up:
        label_of = {(r.task_id, r.candidate_id): r for r in primary if r.condition == "repo_tests"}
        b1 = []
        for res in read_jsonl(run_dir / "results.jsonl", VerificationResult):
            key = (res.task_id, res.candidate_id)
            if res.verifier_id != "repo_tests" or key not in label_of or res.task_id not in up:
                continue
            ok = all(ch.status == "passed" for ch in res.checks if ch.check_id in up[res.task_id])
            r0 = label_of[key]
            b1.append(Row(task_id=r0.task_id, family_id=r0.family_id, candidate_id=r0.candidate_id, condition="repo_tests_upstream",
                          outcome="pass" if ok else "task_failure", label=r0.label, origin=r0.origin,
                          population=r0.population, stratum=r0.stratum))
        ss = summarize(b1, condition="repo_tests_upstream", n_boot=n_boot)
        out["b1_upstream_only"] = {"fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den,
                                   "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den,
                                   "n_checks": {t: len(v) for t, v in up.items()}}
    return out


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
                       scope: str = "same candidates, each distinct graded patch once") -> list[str]:
    """A table of paired comparisons with their exact sign-flip p-values and floors, and the null results stated with it."""
    lines = ["", heading, "",
             f"A - B is the pooled difference ({scope}); the p-values test the sum over families of the count differences "
             "(each candidate weighs the same) with an exact sign-flip test, which cannot go below its floor. p (A > B): "
             "the first-named condition errs more.", "",
             "| A | B | Metric | A - B | Per-family A - B | p (A > B) | p (A < B) | p two-sided | p two-sided, family means | "
             "Floor one-sided / two-sided | Families | A acc & B rej | A rej & B acc |",
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
        text += (f". With at most {max(d['signflip']['pooled']['k'] for d in tested)} families no two-sided p-value can go "
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


def _side_by_side_markdown(conditions: dict) -> list[str]:
    """FA and FR per condition under the primary labels and under the independent labeling, and the per-family table."""
    lines = ["| Condition | FA, primary | FA, independent | FR, primary | FR, independent | Excluded (unlabeled/ambiguous), "
             "primary / independent |", "| --- | --- | --- | --- | --- | --- |"]
    for c, d in conditions.items():
        (pfa, pfr), (ifa, ifr) = _rates_cell(d["primary"]), _rates_cell(d["independent_label"])
        lines.append(f"| {c} | {pfa} | {ifa} | {pfr} | {ifr} | {d['primary']['excluded_unlabeled_or_ambiguous']} / "
                     f"{d['independent_label']['excluded_unlabeled_or_ambiguous']} |")
    fams = sorted({f for d in conditions.values() for x in d.values() for f in x["per_family"]})
    head = ["Condition", "Labeling", *(f"{f} {m}" for f in fams for m in ("FA", "FR")), "All FA", "All FR"]
    lines += ["", "| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    for c, d in conditions.items():
        for name, key in (("primary", "primary"), ("independent", "independent_label")):
            pf, cells = d[key]["per_family"], []
            for f in fams:
                x = pf.get(f)
                cells += ["-", "-"] if x is None else [f"{x['fa_num']}/{x['fa_den']}", f"{x['fr_num']}/{x['fr_den']}"]
            lines.append(f"| {c} | {name} | " + " | ".join(cells) + " | " + " | ".join(_rates_cell(d[key])) + " |")
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
    return lines


def _independent_markdown(x: dict) -> list[str]:
    """The second labeling by the independent labeler (protocol §15.4, §15.5)."""
    lab, amb = x["labels"], x["ambiguous_outcomes"]
    sanity = "; ".join(f"{t} {o} {s['pass']}/{s['n']}" for t, d in x["sanity"].items() for o, s in d.items()) or "not graded"
    lines = ["", "## Independent labeler: a second labeling (protocol §15.4, §15.5)", "", _sentence(x["rule"]), "",
             f"Graded on {', '.join(x['tasks'])}. Held-out candidates: {lab['valid']} valid, {lab['invalid']} invalid, "
             f"{lab['ambiguous']} ambiguous" + (f" ({', '.join(f'{o} {n}' for o, n in amb.items())})" if amb else "")
             + f", {lab['not_graded']} not graded. The labeler passes on (sanity): {sanity}.", "",
             "### False acceptance and false rejection under each labeling", "",
             f"(numerator/denominator), counted as the primary analysis counts them; primary: {x['primary_labels']}; "
             "independent: the labeler's verdicts. Unlabeled and ambiguous candidates are excluded and counted.", ""]
    lines += _side_by_side_markdown(x["conditions"])
    for s, d in x.get("by_stratum", {}).items():
        lines += ["", f"### Stratum {s} (tasks: {', '.join(d['tasks'])})", ""] + _side_by_side_markdown(d["conditions"])
    ag = x["agreement"]
    lines += ["", "### Agreement between D19 and the independent labeler", "", _sentence(ag["rule"])]
    for s, g in ag["by_stratum"].items():
        lines += _agreement_markdown(f"Stratum {s} (tasks: {', '.join(g['tasks'])})", g)
    if "pooled" in ag:
        lines += _agreement_markdown("All strata pooled", ag["pooled"])
    return lines


def _source_markdown(s: dict) -> list[str]:
    lines = ["", "## Source-evidence labels (reported apart from D19)", "", _sentence(s["rule"]), "",
             "| Condition | Invalid by source evidence, accepted | Valid by source evidence, rejected |", "| --- | --- | --- |"]
    for c, d in s["conditions"].items():
        lines.append(f"| {c} | {d['invalid']['accepted']}/{d['invalid']['n']} | {d['valid']['rejected']}/{d['valid']['n']} |")
    return lines


def _oracle_markdown(o: dict) -> list[str]:
    lines = ["", "## Oracle-gated view (secondary)", "", _sentence(o["rule"]), "",
             "| Condition | Cells kept | Dropped | Lost yield (invalid / valid) | False acceptance | False rejection |",
             "| --- | --- | --- | --- | --- | --- |"]
    for c, d in o["conditions"].items():
        fa, fr = d["false_acceptance"], d["false_rejection"]
        dropped = "; ".join(f"{t}: {why}" for t, why in d["dropped"].items()) or "-"
        lines.append(f"| {c} | {d['cells_kept']}/{d['cells']} | {dropped} | {d['lost_yield']['invalid']} / {d['lost_yield']['valid']} | "
                     f"{_fmt(fa['rate'], fa['num'], fa['den'])} | {_fmt(fr['rate'], fr['num'], fr['den'])} |")
    if o["comparisons"]:
        lines += _signflip_markdown(o["comparisons"], "### Oracle-gated paired comparisons",
                                    "same candidates, on the tasks that both conditions keep")
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


def to_markdown(a: dict) -> str:
    new = "reporting_rules" in a["meta"]  # a new run: the reporting rules of protocol §15.7 (module docstring)
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
    if new:
        lines += _rules_markdown(a) + [""]
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
        lines += _independent_markdown(a["independent_labeling"])
    if new:
        lines += _oracle_markdown(a["oracle_gated"]) + _distinct_markdown(a["distinct_patches"])
    lines += ["", "## Accepted negatives by type", "", "| Condition | correction-violating | initial-violating | unspecified |", "| --- | --- | --- | --- |"]
    for c in a["conditions"]:
        bt = a["by_negative_type"].get(c, {})
        cell = lambda k: f"{bt[k]['accepted']}/{bt[k]['n']}" if k in bt else "-"  # noqa: E731
        lines.append(f"| {c} | {cell('correction_violating')} | {cell('initial_violating')} | {cell('unspecified')} |")
    lines += ["", "## Sanity checks (excluded from primary metrics)", "", "| Condition | reference passes | no-op passes |", "| --- | --- | --- |"]
    for c, s in a["sanity"].items():
        ref = s.get("reference", {})
        noop = s.get("noop", {})
        lines.append(f"| {c} | {ref.get('pass', '-')}/{ref.get('n', '-')} | {noop.get('pass', '-')}/{noop.get('n', '-')} |")
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
            lines.append(f"| {c} | {_fmt(d['fa'], d['fa_num'], d['fa_den'], sci('fa'))}{st('fa')} | {exs('fa')} | "
                         f"{_fmt(d['fr'], d['fr_num'], d['fr_den'], sci('fr'))}{st('fr')} | {exs('fr')} |")
    if a.get("near_miss_crosstab"):
        lines += ["", "## Post-hoc analyses after the internal review (exploratory, not pre-specified)", "",
                  "### Near misses accepted, by label status", "", "| Condition | D19-confirmed invalid | D19 ambiguous |", "| --- | --- | --- |"]
        for c, d in a["near_miss_crosstab"].items():
            lines.append(f"| {c} | {d['confirmed_invalid']['accepted']}/{d['confirmed_invalid']['n']} | {d['ambiguous']['accepted']}/{d['ambiguous']['n']} |")
    if a.get("sensitivity_check_labels"):
        lines += ["", "### Rates under the independent construction checks' labels", "",
                  "| Condition | False acceptance | False rejection |", "| --- | --- | --- |"]
        for c, d in a["sensitivity_check_labels"].items():
            lines.append(f"| {c} | {_fmt(d['fa'], d['fa_num'], d['fa_den'])} | {_fmt(d['fr'], d['fr_num'], d['fr_den'])} |")
    if a.get("duplicates"):
        lines += ["", "### Held-out candidates that duplicate another candidate (same graded patch, or same code apart from comments and docstrings)", ""]
        for cid, d in a["duplicates"].items():
            lines.append(f"* {cid}: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in d.items() if k != "task_id"))
        lines += ["", "| Condition | FA without duplicates | FR without duplicates |", "| --- | --- | --- |"]
        for c, d in a.get("sensitivity_without_duplicates", {}).items():
            lines.append(f"| {c} | {_fmt(d['fa'], d['fa_num'], d['fa_den'])} | {_fmt(d['fr'], d['fr_num'], d['fr_den'])} |")
    if a.get("b1_upstream_only"):
        d = a["b1_upstream_only"]
        lines += ["", "### B1 restricted to the base commit's own tests (checks added by the session agent removed)", "",
                  f"False acceptance {_fmt(d['fa'], d['fa_num'], d['fa_den'])}; false rejection {_fmt(d['fr'], d['fr_num'], d['fr_den'])}."]
    if a.get("labels"):
        lines += ["", "## Labels and human-review queue", "", "| Task | valid | invalid | ambiguous | unlabeled | queued for review |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for t, d in a["labels"].items():
            lines.append(_label_row(t, d))
            lines += [_label_row(f"{t} (stratum {s})", sd) for s, sd in d.get("strata", {}).items()]
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
    lines += ["", "## Per-task outcomes", ""]
    strat = bool(a.get("by_stratum"))  # a Stratum column only for a run with candidate strata
    for t, conds in a["per_task"].items():
        lines += [f"### {t}", "", f"| Candidate | {'Stratum | ' if strat else ''}Origin | Label | Negative type | " + " | ".join(conds) + " |",
                  f"| --- | {'--- | ' if strat else ''}--- | --- | --- | " + " | ".join("---" for _ in conds) + " |"]
        cands = {}
        for c, rs in conds.items():
            for r in rs:
                cands.setdefault(r["candidate"], {"origin": r["origin"], "label": r["label"], "nt": r["negative_type"],
                                                  "stratum": r.get("stratum", "")})[c] = r["outcome"]
        for cid, d in sorted(cands.items()):
            lines.append(f"| {cid} | {d['stratum'] + ' | ' if strat else ''}{d['origin']} | {d['label']} | {d['nt'] or '-'} | "
                         + " | ".join(d.get(c, "-") for c in conds) + " |")
        lines.append("")
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


def label_summary(task_dirs: list[Path], strata: dict[str, dict[str, list[Candidate]]] | None = None) -> dict:
    """Proposed-label counts per task and the queue of candidates needing human review.

    Queued: candidates the D19 rule marked ambiguous, candidates without a proposal,
    candidates whose independent construction check disagrees with the proposal
    (``labels/construction_checks.json``, advisory evidence only), and every fresh attempt
    without a final human label (protocol §15.4).

    ``strata`` (``{task_id: {stratum: candidates}}``) adds, under the task's ``strata`` key,
    the same summary for each stratum's candidates.
    """
    out: dict = {}
    for tdir in task_dirs:
        m = load(tdir / "task.json", TaskManifest)
        checks_p = tdir / "labels" / "construction_checks.json"
        checks = json.loads(checks_p.read_text()).get("checks", {}) if checks_p.exists() else {}
        out[m.task_id] = _label_pool([load(tdir / p, Candidate) for p in m.candidates], checks)
        if (strata or {}).get(m.task_id):
            out[m.task_id]["strata"] = {name: _label_pool(cs, checks) for name, cs in strata[m.task_id].items()}
    return out


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
