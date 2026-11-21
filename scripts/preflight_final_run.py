"""Pre-flight checks before a run: the final pilot run (protocol v0.3 §11) and every new run (v0.7 §15.3, v0.8 §16).

Fails (exit 1) unless, for every task given:
* every verifier spec is frozen and its tests still match the frozen content hash;
* the task has the full held-out pool (pre-correction state, 2 alternatives, 5 near
  misses) and every held-out candidate has a D19 proposal (or a human label);
* every constructed held-out candidate's generator transcript was audited, with no
  forbidden read left unassessed;
* no candidate's patch adds or modifies a top-level module or package named like a
  standard-library module that the grader's wrapper relies on (``ast``, ``unicodedata``,
  ``linecache``, ``tokenize``, ``traceback``, ``encodings``, ``json``, ``hmac``,
  ``hashlib``, ``os``, ``sys``), in the working tree or in an entry of the task's
  ``candidate_pythonpath`` (``tracecontract.shadowing``; decision log D36, D40, D44);
* the base snapshot exists and matches its recorded manifest;
* its base passed the reconstruction check: ``tasks/<id>/reconstruction_check.json`` has
  status ``passed`` and was recorded from the current transcript, base manifest and candidate
  patches (``tracecontract.reconstruction.recorded_check``; protocol v0.8 §16.5), with or
  without ``--pilot``;
* it was accepted through the task acceptance gate; with ``--pilot``, as for ``tracecontract
  evaluate``, a task that has not passed the gate is allowed (a warning), but a refused one (a
  rejected task or source, or a failed reconstruction check) is not;
* every condition named with ``--conditions`` has a verifier in the task (with
  ``--with-extra-verifiers``, a verifier of its ``verifiers_extra.json`` counts too);

and, for the run (every run started now is a new run under protocol v0.8):
* it grades every pair three times (``--repeats 3``; v0.7 §15.3, v0.8 §16.1);
* it uses ``tc-harness/0.3.5`` or a later harness (v0.8 §16.1): the version the grader
  (``tracecontract.sandbox.docker_runner``) would run now;
* its ``--run-id``, if given, names no recorded run (``results/runs/<id>`` is not changed);
* no other sandbox container is running and the git working tree is clean.

A run that grades candidate strata (``--strata NAME ...``; protocol v0.7 §15.4, v0.8 §16.2,
v0.10 §18.1) must also satisfy, for every task given and every stratum named:
* the stratum loads as evaluate loads it (``strata.load_strata``: its manifest
  ``tasks/<id>/strata/<name>.json`` and candidate files, with every candidate id used once, by
  the task's own candidates or by one of the strata named), and it lists a candidate of the
  eval split, the split evaluate grades;
* every graded stratum candidate (eval split; a no-op aside) has a D19 proposal (or a human
  label), as every held-out candidate must; ``scripts/propose_labels.py tasks/<id> --stratum
  <name>`` writes them into the stratum's candidate files;
* every stratum candidate that is a fresh attempt is of the eval split: protocol §15.4 captures
  every attempt with split eval, and evaluate would not grade one of another split;
* every graded stratum candidate that is a fresh attempt has an attempt record
  (``Candidate.attempt``) holding a fresh-attempt audit verdict, and was audited: the audit
  report of its family lists the attempt (by its attempt id) under ``attempts``, and the report
  leaves no attempt under ``not_audited`` (protocol §15.4, §16.2). The verdict must agree with
  the report, since the analysis excludes an attempt by its verdict
  (``analysis.attempt_exclusion``) and the primary analysis uses the reviewed verdicts (§18.1).
  An attempt that the reviewed audit excludes (``manual_review.excluded_after_review``; for a
  report without a manual review, its automated ``excluded`` list) and whose verdict is failed
  is a note, "excluded from the primary analysis", not a failure: evaluate still grades it and
  the analysis excludes it. Any other disagreement fails. Neither ``tracecontract.analysis`` nor
  ``tracecontract.strata`` looks an audit report up (the analysis reads one only when it is
  named with ``--sensitivity-exclusions``). Its path is recorded in each attempt record
  (``attempt.audit.record``, relative to the repository root; for fresh-v1,
  ``data/fresh/fresh-v1/audit_<task id>.json``, which the family's
  ``data/fresh/fresh-v1/attempts_<task id>.json`` also names), and the pre-flight checks the
  report that the attempt record names; for a record that names none, it takes
  ``data/fresh/<stratum>/audit_<task id>.json``;
* that audit report reviewed every flag (§16.2, §18.1): its ``excluded`` is a list (the attempts
  that the script flagged; for a report without a manual review, the list that excludes them), a
  manual review holds lists of attempt ids, and an attempt that the audit flagged
  (``attempts[*].flagged``, ``excluded`` or ``manual_review.flagged_by_script``) and that was
  audited is, with a manual review, judged a false positive (``judged_false_positive``) or
  excluded after review (``excluded_after_review``), not both, and without one, excluded. Where
  the report records an attempt's own review verdict (``attempts[*].review.passed``), it agrees
  with the list that excludes and with the attempt record's verdict;
* no stratum candidate's patch ships a top-level module named like a guarded standard-library
  module (the shadowing check above, for every candidate of the stratum).

With ``--with-extra-verifiers``, for every task given, its ``verifiers_extra.json`` adds a
verifier and the run grades one of them (``--conditions``, if given, names its condition);
every verifier that evaluate adds from it (``evaluate.extra_verifier_paths``) loads, is frozen
and still matches its frozen hashes (``check_frozen``, as for the task's verifiers), has an id
that no other verifier of the task has, and is a label-support verifier (condition
``reference_check``; D19, D55, protocol §15.5), never a verifier of an evaluated condition;
and the verifiers that the run records for the task (its own and the extra ones, of the
conditions given) pass the analysis' condition guard (``analysis._check_conditions``): a
label-support verifier is recorded under ``reference_check``, and no two verifiers of a task
share an evaluated condition. With ``--strata`` too, the run grades the independent labeler
(verifier ``independent_label``, whose verdicts on every attempt are the second labeling;
protocol §15.4, §15.5), and every extra verifier that it grades was frozen (``frozen_at``)
before the first of the strata's graded fresh attempts started (the earliest ``started_at`` of
their attempt records; §15.5 freezes the labeler before any fresh attempt exists). A graded
attempt whose record holds no start time fails, since nothing then shows that.

With ``--only-strata`` (which needs ``--strata``, as evaluate does), evaluate grades the
strata's candidates instead of the task's own, whose reference solution alone is still graded
(the sanity check). The checks of the task's held-out pool (the full pool, its D19 proposals,
the audits of the generators of its held-out candidates, the same-code duplicate record and the
duplicate warnings) are then notes rather than failures. An entry of
``labels/generator_audit.json`` is the audit of such a generator when it is named after held-out
candidates of the task (``eval-alt-1`` for ``<task id>-eval-alt-1``, ``eval-nm`` for
``<task id>-eval-nm-<n>``). Every other entry still fails, whatever the conditions, above all
``refcheck``: the audit of the writer of ``verifiers/reference_check``, the reference checks
from which every D19 proposal of the strata comes (source 1) and which the run grades again
under ``reference_check``. The run checks and the acceptance gate, reconstruction, snapshot,
verifier and shadowing checks still apply.

A note (``NOTE:``) never fails the pre-flight. Without ``--strata``, ``--only-strata`` and
``--with-extra-verifiers``, the pre-flight checks only what the first two lists name.

Pass the same ``--run-id``, ``--conditions``, ``--repeats``, ``--pilot``, ``--strata``,
``--only-strata`` and ``--with-extra-verifiers`` as to ``tracecontract evaluate``; without
``--repeats`` the check assumes evaluate's default, one repeat, and fails.

Held-out candidates whose graded patch equals a development candidate's or another
held-out candidate's are reported as warnings (decision log D37). Same-code duplicates
(comments and docstrings ignored) must match the record in ``labels/duplicates.json``
(written by ``scripts/find_duplicates.py``; decision log D40), so a new one cannot go
unrecorded.

Usage: python scripts/preflight_final_run.py tasks/CS-01 tasks/CS-02 ... [--run-id ID] [--conditions C ...]
       [--repeats 3] [--pilot] [--strata NAME ...] [--only-strata] [--with-extra-verifiers]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath

from tracecontract.analysis import (
    INDEPENDENT_LABELER, LABEL_SUPPORT_CONDITION, PILOT_LABELER, ConditionConflict, _check_conditions,
)
from tracecontract.contract import task_gate
from tracecontract.evaluate import EXTRA_VERIFIERS, extra_verifier_paths
from tracecontract.reconstruction import recorded_check
from tracecontract.schemas import Candidate, CandidateOrigin, Split, TaskManifest, VerifierSpec
from tracecontract.shadowing import shadowing_files
from tracecontract.store import load
from tracecontract.strata import Stratum, StratumError, load_strata, load_stratum
from tracecontract.verifier import check_frozen

R = Path(__file__).resolve().parents[1]
NEW_RUN_REPEATS = 3  # protocol v0.7 §15.3: every new pair is graded three times
MIN_HARNESS = "tc-harness/0.3.5"  # protocol v0.8 §16.1: new runs use 0.3.5 (0.3.4 is never used for a run)
# With --only-strata, what the checks of the task's own held-out pool report is a note: this run does not grade it.
NOT_GRADED = "with --only-strata the run does not grade the task's own candidates"
# The lists of attempt ids that a manual review of a fresh-attempt audit report holds (protocol §18.1).
REVIEW_LISTS = ("flagged_by_script", "judged_false_positive", "excluded_after_review")


def _harness_version(v: str | None) -> tuple[int, ...] | None:
    m = re.fullmatch(r"tc-harness/(\d+(?:\.\d+)*)", v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def run_problems(*, repeats: int, harness: str | None, run_id: str | None = None, runs_root: Path = R / "results" / "runs"
                 ) -> list[str]:
    """Problems with the parameters of a new run (protocol v0.7 §15.3, v0.8 §16.1)."""
    out = []
    if repeats != NEW_RUN_REPEATS:
        out.append(f"run: a new run grades every pair {NEW_RUN_REPEATS} times; pass --repeats {NEW_RUN_REPEATS} here and to "
                   f"`tracecontract evaluate` (got {repeats}; protocol v0.7 §15.3, v0.8 §16.1)")
    have, need = _harness_version(harness), _harness_version(MIN_HARNESS)
    if have is None or need is None or have < need:
        out.append(f"run: the grader's harness is {harness}; every new run uses {MIN_HARNESS} or later "
                   "(protocol v0.8 §16.1)")
    if run_id is not None and (runs_root / run_id).exists():
        out.append(f"run: results/runs/{run_id} already exists; a new run needs a new run id (recorded runs are not changed)")
    return out


def gate_problems(td: Path, m: TaskManifest, *, pilot: bool) -> list[str]:
    """The task acceptance gate as ``tracecontract evaluate`` applies it (a failed reconstruction check is reported apart)."""
    g = task_gate(td, R)
    refusals = [r for r in g.refusals if not r.startswith("reconstruction:")]
    if refusals:
        return [f"{m.task_id}: refused by the acceptance gate ({'; '.join(refusals)})"]
    others = [r for r in g.reasons if not r.startswith("reconstruction:")]
    if g.refusals or (g.status == "accepted" and not others):
        return []  # only the reconstruction check stands in the way: main reports it
    first = others[0] if others else "the gate passes, but the task was not accepted (tracecontract accept-task)"
    if pilot:
        print(f"WARN: {m.task_id}: not accepted through the acceptance gate (status {g.status!r}; {len(others)} reason(s), "
              f"first: {first}); checked as an automated pilot (--pilot)")
        return []
    return [f"{m.task_id}: not accepted through the acceptance gate (status {g.status!r}; {len(others)} reason(s), first: "
            f"{first}); pass --pilot here and to evaluate for an automated pilot"]


def _args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="preflight_final_run.py", description=__doc__.split("\n", 1)[0])
    ap.add_argument("tasks", nargs="+", help="task directories (tasks/<id>)")
    ap.add_argument("--run-id", help="the run id that evaluate will be given; it must be new")
    ap.add_argument("--conditions", nargs="*", help="the conditions that evaluate will be given")
    ap.add_argument("--repeats", type=int, default=1, help="the repeats that evaluate will be given (its default is 1)")
    ap.add_argument("--pilot", action="store_true", help="as for evaluate: tasks that have not passed the acceptance gate "
                    "are allowed as an automated pilot; refused tasks never are")
    ap.add_argument("--strata", nargs="+", metavar="NAME", help="as for evaluate: the candidate strata it will grade "
                    "(tasks/<id>/strata/<name>.json); each must load, be labelled and, for fresh attempts, be audited")
    ap.add_argument("--only-strata", action="store_true", help="as for evaluate (with --strata): the task's own candidates "
                    "are not graded, so the checks of its held-out pool are notes")
    ap.add_argument("--with-extra-verifiers", action="store_true", help="as for evaluate: the verifiers of each task's "
                    "verifiers_extra.json are graded too; it must add one, each must be a frozen label-support verifier "
                    "and, with --strata, the independent labeler must be among them, frozen before the first attempt")
    return ap.parse_args(argv)


def shadowing_problems(m: TaskManifest, cands: list[Candidate], *, stratum: str | None = None) -> list[str]:
    """One problem per candidate file that is a top-level module or package named like a guarded standard-library module."""
    where = f"{m.task_id}: " + (f"stratum {stratum}: " if stratum is not None else "")
    return [f"{where}{c.candidate_id} ships {path}, a top-level module named like the standard library's "
            f"`{mod}`; rejected before grading (tracecontract.shadowing)"
            for c in cands for path, mod in shadowing_files(c.patch, m.candidate_pythonpath)]


def has_d19_proposal(c: Candidate) -> bool:
    """A human label or the pre-specified D19 proposal (labeler ``PILOT_LABELER``), as the analysis labels candidates."""
    return c.final_label() is not None or any(lb.labeler == PILOT_LABELER for lb in c.labels)


def generates_held_out(ws: str, task_id: str, held: list[Candidate]) -> bool:
    """Whether the entry ``ws`` of ``labels/generator_audit.json`` audits the generator of held-out candidates of the
    task's own pool ``held``: it is named after them (the workspace of ``<task id>-<ws>`` or ``<task id>-<ws>-<n>``, as
    ``eval-alt-1`` and ``eval-nm``). The writer of a verifier, such as ``refcheck`` (the reference checks), generated no
    candidate, so its audit never is one (see the module docstring on ``--only-strata``)."""
    own = re.compile(re.escape(f"{task_id}-{ws}") + r"(?:-\d+)?")
    return any(own.fullmatch(c.candidate_id) for c in held)


def graded_candidates(st: Stratum) -> list[Candidate]:
    """The stratum candidates that evaluate grades: those of the eval split (its default ``--split``)."""
    return [c for _, c in st.candidates if c.split == Split.eval]


def strata_problems(td: Path, m: TaskManifest, names: list[str], own_ids: set[str]) -> tuple[dict[str, Stratum], list[str]]:
    """The strata ``names`` of a task that load, by name, and the problems: a stratum that does not load as evaluate loads
    it (``evaluate.select_strata``, ``strata.load_strata``), a candidate id used twice, a stratum with nothing to grade."""
    loaded: dict[str, Stratum] = {}
    problems: list[str] = []
    for name in dict.fromkeys(names):
        try:
            loaded[name] = load_stratum(td, name, m.task_id)
        except StratumError as exc:
            problems.append(f"{m.task_id}: stratum {name} does not load: {exc}")
    if loaded:
        try:  # each candidate id once: in the task's own candidates or in one of the strata (as evaluate refuses otherwise)
            load_strata(td, list(loaded), m.task_id, own_ids)
        except StratumError as exc:
            problems.append(f"{m.task_id}: {exc}")
    for name, st in loaded.items():
        if not st.candidates:
            problems.append(f"{m.task_id}: stratum {name} lists no candidate")
        elif not graded_candidates(st):
            problems.append(f"{m.task_id}: stratum {name} has no candidate of the eval split; evaluate grades none of its "
                            f"{len(st.candidates)} candidate(s)")
    return loaded, problems


def stratum_label_problems(m: TaskManifest, st: Stratum) -> list[str]:
    """Graded stratum candidates (a no-op aside) without a D19 proposal or a human label, as for the held-out pool."""
    return [f"{m.task_id}: stratum {st.name}: {c.candidate_id} has no D19 proposal "
            f"(scripts/propose_labels.py tasks/{m.task_id} --stratum {st.name})"
            for c in graded_candidates(st) if c.origin != CandidateOrigin.noop and not has_d19_proposal(c)]


def default_audit_report(stratum: str, task_id: str) -> str:
    """The audit report of a family's fresh attempts when an attempt record names none (relative to the repository root)."""
    return f"data/fresh/{stratum}/audit_{task_id}.json"


def report_form_problem(report: dict) -> str | None:
    """What keeps an audit report's lists from being read (None if nothing does): its ``excluded`` must be a list of
    attempt ids, also in a report without a manual review, where it is the list that excludes (an absent list never
    means that nothing is excluded); a manual review (``manual_review``) must hold the lists ``REVIEW_LISTS``, of which
    ``excluded_after_review`` must be there."""
    if not isinstance(report.get("excluded"), list):
        return ("'excluded' is not a list of attempt ids (the attempts that the audit flagged, which it excludes unless a "
                "manual review judged them; scripts/strict_reaudit.py --fresh writes it)")
    review = report.get("manual_review")
    if review is None:
        return None
    if not isinstance(review, dict) or "excluded_after_review" not in review \
            or not all(isinstance(review.get(k, []), list) for k in REVIEW_LISTS):
        return (f"manual_review is not a review of the flags: it must hold lists of attempt ids under "
                f"{', '.join(REVIEW_LISTS)} (excluded_after_review at least)")
    return None


def _excluded_by(report: dict, rel: str) -> tuple[set[str], str, str]:
    """The attempt ids that an audit report excludes, which audit excludes them and the list: the reviewed verdicts when it
    records a manual review (``manual_review.excluded_after_review``, protocol §18.1), else its automated ``excluded`` list
    (§16.2), which holds every attempt that the audit flagged. The report's lists were checked (:func:`report_form_problem`)."""
    review = report.get("manual_review")
    if review is not None:
        return ({str(x) for x in review["excluded_after_review"]}, "the reviewed audit",
                f"manual_review.excluded_after_review of {rel}")
    return ({str(x) for x in report["excluded"]}, "the automated audit", f"'excluded' of {rel}, which records no manual review")


def _review_verdict(entry) -> bool | str | None:
    """The verdict of an attempt's own review in an audit report (``attempts[<id>].review.passed``): True or False; None
    when the report records none; the text of the problem when it records one that is not true or false."""
    review = entry.get("review") if isinstance(entry, dict) else None
    if review is None:
        return None
    if not isinstance(review, dict):
        return "its review is not an object"
    if "passed" not in review:
        return None
    return review["passed"] if isinstance(review["passed"], bool) else "its review.passed is not true or false"


def _verdict(passed: bool) -> str:
    return "passed" if passed else "failed"


def review_problems(report: dict, rel: str, where: str) -> list[str]:
    """The problems of an audit report's review of its flags (protocol §16.2, §18.1: every flag is reviewed by reading the
    transcript; an attempt the review does not clear is excluded). The report's lists were checked
    (:func:`report_form_problem`).

    An attempt that the audit flagged (``attempts[<id>].flagged``, the report's ``excluded`` or
    ``manual_review.flagged_by_script``) and that was audited (it is not under ``not_audited``, which is reported apart)
    must be, with a manual review, judged a false positive or excluded after review, and not both; without one, it must
    be excluded. An attempt's own review verdict, where the report records one, must agree with the list that excludes
    (:func:`_excluded_by`).
    """
    problems: list[str] = []
    at = f"{where}: audit report {rel}"
    left = {str(x) for x in report.get("not_audited") or []}
    review = report.get("manual_review")
    excluded, by, src = _excluded_by(report, rel)
    flags: dict[str, list[str]] = {}  # attempt id -> where the report flags it, in the report's order
    for aid, entry in report["attempts"].items():
        if isinstance(entry, dict) and entry.get("flagged"):
            flags.setdefault(str(aid), []).append(f"attempts.{aid}.flagged")
    for name, listed in (("'excluded'", report["excluded"]),
                         ("manual_review.flagged_by_script", [] if review is None else review.get("flagged_by_script", []))):
        for aid in listed:
            flags.setdefault(str(aid), []).append(name)
    if review is not None:
        judged = {str(x) for x in review.get("judged_false_positive", [])}
        for aid, sources in flags.items():
            if aid not in left and aid not in judged | excluded:
                problems.append(f"{at}: attempt {aid} was flagged ({', '.join(sources)}), but its manual review neither "
                                "judges it a false positive nor excludes it (manual_review.judged_false_positive, "
                                "excluded_after_review); protocol §18.1 reviews every flag by reading the transcript")
        problems.extend(f"{at}: its manual review both judges attempt {aid} a false positive and excludes it "
                        "(manual_review.judged_false_positive and excluded_after_review)" for aid in sorted(judged & excluded))
    else:  # the automated list excludes every flagged attempt (§16.2)
        problems.extend(f"{at}: attempt {aid} was flagged ({', '.join(sources)}), but the report neither excludes it "
                        "('excluded') nor records a manual review of its flags (protocol §16.2, §18.1)"
                        for aid, sources in flags.items() if aid not in left and aid not in excluded)
    for aid, entry in report["attempts"].items():
        verdict = _review_verdict(entry)
        if verdict is None or str(aid) in left:
            continue
        if isinstance(verdict, str):
            problems.append(f"{at}: attempt {aid}: {verdict}")
        elif verdict == (str(aid) in excluded):
            problems.append(f"{at}: the review of attempt {aid} says {_verdict(verdict)}, but {by} "
                            f"{'excludes' if str(aid) in excluded else 'does not exclude'} it ({src})")
    return problems


def attempt_audit_problems(m: TaskManifest, st: Stratum, *, repo_root: Path = R) -> tuple[list[str], list[str]]:
    """The problems and the notes of a stratum's fresh attempts: their split, their attempt records and their audit report
    (:func:`report_form_problem`, :func:`review_problems`).

    See the module docstring. ``repo_root`` is where the reports' paths start.
    """
    problems: list[str] = []
    notes: list[str] = []
    reports: dict[str, dict | None] = {}  # repository-relative path -> the report, or None when it cannot be used
    where = f"{m.task_id}: stratum {st.name}"

    def report(rel: str) -> dict | None:
        if rel in reports:
            return reports[rel]
        reports[rel] = None
        parts = PurePosixPath(rel).parts
        if "\\" in rel or not parts or PurePosixPath(rel).is_absolute() or ".." in parts:
            problems.append(f"{where}: audit report {rel!r} is not a path relative to the repository root")
            return None
        path = repo_root / rel
        if not path.is_file():
            problems.append(f"{where}: audit report {rel} does not exist")
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{where}: audit report {rel} cannot be read: {exc}")
            return None
        if not isinstance(data, dict) or not isinstance(data.get("attempts"), dict):
            problems.append(f"{where}: {rel} is not an audit report of fresh attempts (no 'attempts' object)")
            return None
        if data.get("task_id", m.task_id) != m.task_id or data.get("stratum", st.name) != st.name:
            problems.append(f"{where}: audit report {rel} is the report of task {data.get('task_id')!r}, stratum "
                            f"{data.get('stratum')!r}")
            return None
        left = data.get("not_audited") or []
        if not isinstance(left, list):
            problems.append(f"{where}: audit report {rel}: 'not_audited' is not a list of attempt ids")
            return None
        form = report_form_problem(data)
        if form is not None:
            problems.append(f"{where}: audit report {rel}: {form}")
            return None
        problems.extend(f"{where}: audit report {rel} leaves attempt {aid} not audited (not_audited; its transcript was not "
                        "audited)" for aid in left)
        problems.extend(review_problems(data, rel, where))
        reports[rel] = data
        return data

    owner: dict[str, str] = {}  # attempt id -> the candidate that holds it
    for _, c in st.candidates:
        if c.origin != CandidateOrigin.fresh_attempt:
            continue
        who = f"{where}: {c.candidate_id}"
        if c.split != Split.eval:
            problems.append(f"{who} is a fresh attempt of the {c.split.value} split, which evaluate does not grade (it grades "
                            "the eval split); protocol §15.4 captures every attempt with split eval")
            continue
        rec = c.attempt
        if rec is None:
            problems.append(f"{who} is a fresh attempt without an attempt record (protocol §15.4); the analysis would "
                            "exclude it")
            continue
        aid = rec.attempt_id
        if aid in owner:
            problems.append(f"{who}: its attempt id {aid} is also the attempt id of {owner[aid]}")
            continue
        owner[aid] = c.candidate_id
        verdict = rec.audit
        if verdict is None:
            problems.append(f"{who} was not audited: its attempt record holds no fresh-attempt audit verdict (protocol §16.2); "
                            "the analysis would exclude it")
        rel = verdict.record if verdict is not None and verdict.record else default_audit_report(st.name, m.task_id)
        data = report(rel)
        if data is None:
            continue
        entry = data["attempts"].get(aid)
        if entry is None:
            problems.append(f"{who}: audit report {rel} does not list its attempt {aid} under attempts")
            continue
        if aid in {str(x) for x in data.get("not_audited") or []}:
            continue  # reported with the report
        if isinstance(entry, dict) and entry.get("error"):
            problems.append(f"{who}: audit report {rel} holds no audit of attempt {aid} ({entry['error']})")
            continue
        if verdict is None:
            continue
        excluded, by, src = _excluded_by(data, rel)
        if aid in excluded and verdict.passed:
            problems.append(f"{who}: {by} excludes it (attempt {aid} in {src}), but its attempt record's audit verdict is "
                            "passed, so the analysis would count it")
        elif aid in excluded:
            notes.append(f"{who} is excluded from the primary analysis: {by} excludes it (attempt {aid} in {src}); evaluate "
                         "still grades it")
        elif not verdict.passed:
            problems.append(f"{who}: its attempt record's audit verdict is failed, but {by} does not exclude it (attempt {aid} "
                            f"is not in {src}), so the analysis would exclude an attempt that the audit passed")
        reviewed = _review_verdict(entry)
        if isinstance(reviewed, bool) and reviewed != verdict.passed:
            problems.append(f"{who}: its attempt record's audit verdict is {_verdict(verdict.passed)}, but the review of "
                            f"attempt {aid} in audit report {rel} says {_verdict(reviewed)}")
    return problems, notes


def graded_verifiers(specs: list[VerifierSpec], conditions: list[str] | None) -> list[VerifierSpec]:
    """The verifiers of ``specs`` that evaluate grades (and records): those of the conditions given (None or empty: all)."""
    return [s for s in specs if not conditions or s.condition.value in conditions]


def extra_verifier_problems(td: Path, m: TaskManifest, specs: list[VerifierSpec], conditions: list[str] | None, *,
                            with_strata: bool = False) -> tuple[list[VerifierSpec], list[str]]:
    """With ``--with-extra-verifiers``: the verifiers that evaluate adds from ``verifiers_extra.json``, and the problems.

    ``specs`` are the task's own verifiers (``task.json``), ``conditions`` the conditions given (None or empty: all) and
    ``with_strata`` whether the run grades candidate strata (``--strata``), every attempt of which the independent labeler
    grades.
    """
    problems: list[str] = []
    try:  # as evaluate.load_task adds them: those that task.json does not list already
        paths = [p for p in extra_verifier_paths(td) if p not in m.verifiers]
    except Exception as exc:  # noqa: BLE001 - an unreadable sidecar is reported, not raised
        return [], [f"{m.task_id}: {EXTRA_VERIFIERS} cannot be read: {exc}"]
    if not paths:
        problems.append(f"{m.task_id}: --with-extra-verifiers, but {EXTRA_VERIFIERS} registers no verifier; evaluate adds none")
    extras: list[VerifierSpec] = []
    for p in paths:
        try:
            extras.append(load(td / p, VerifierSpec))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{m.task_id}: extra verifier {p} ({EXTRA_VERIFIERS}) does not load: {exc}")
    ids = Counter(s.verifier_id for s in [*specs, *extras])
    for s in extras:
        what = f"{m.task_id}: extra verifier {s.verifier_id} ({EXTRA_VERIFIERS})"
        if ids[s.verifier_id] > 1:
            problems.append(f"{what}: another verifier of the task has the id {s.verifier_id}; a run records one verifier per id")
        if s.condition.value != LABEL_SUPPORT_CONDITION:
            problems.append(f"{what} has the condition {s.condition.value!r}; {EXTRA_VERIFIERS} registers label-support "
                            f"verifiers only (condition {LABEL_SUPPORT_CONDITION!r}), never a verifier of an evaluated "
                            "condition (D55, protocol §15.5)")
        if not s.frozen:
            problems.append(f"{what} not frozen")
            continue
        try:
            check_frozen(s, td)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{what} changed after freezing: {exc}")
    # The verifiers the run records for the task (evaluate keeps those of the conditions given), under the analysis' guard.
    recorded = graded_verifiers([*specs, *extras], conditions)
    try:
        _check_conditions(m.task_id, {s.verifier_id: {"condition": s.condition.value} for s in recorded})
    except ConditionConflict as exc:
        problems.append(f"{exc} (tracecontract analyze would refuse the run)")
    if extras and not graded_verifiers(extras, conditions):
        problems.append(f"{m.task_id}: --conditions names no condition of the extra verifiers "
                        f"({', '.join(s.verifier_id for s in extras)}); evaluate grades none of them")
    if with_strata and not any(s.verifier_id == INDEPENDENT_LABELER for s in recorded):
        problems.append(f"{m.task_id}: the run grades no independent labeler (verifier {INDEPENDENT_LABELER} of "
                        f"{EXTRA_VERIFIERS}, condition {LABEL_SUPPORT_CONDITION!r}); with --strata it grades every attempt, "
                        "and its verdicts are the second labeling (protocol §15.4, §15.5)")
    return extras, problems


def _time(value: str | None) -> datetime | None:
    """An ISO 8601 time with a time zone, or None (absent, or not such a time)."""
    try:
        t = datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
    return t if t is not None and t.tzinfo is not None else None


def frozen_before_attempts_problems(m: TaskManifest, extras: list[VerifierSpec], strata: dict[str, Stratum]) -> list[str]:
    """With ``--strata`` and ``--with-extra-verifiers``: each extra verifier ``extras`` that the run grades must have been
    frozen before the first of the strata's graded fresh attempts started (protocol §15.5: the labeler is frozen before
    any fresh attempt exists). The start times are those of the attempt records; a graded attempt whose record holds none
    fails, since nothing then shows that the verifiers were frozen before it existed. An extra verifier that is not
    frozen is reported by :func:`extra_verifier_problems`."""
    frozen = [s for s in extras if s.frozen]
    attempts = [(st.name, c) for st in strata.values() for c in graded_candidates(st)
                if c.origin == CandidateOrigin.fresh_attempt and c.attempt is not None]
    if not frozen or not attempts:
        return []
    problems: list[str] = []
    starts = []
    ids = ", ".join(s.verifier_id for s in frozen)
    for name, c in attempts:
        t = _time(c.attempt.started_at)
        if t is None:  # the schema allows no other start time than one with a time zone
            problems.append(f"{m.task_id}: stratum {name}: {c.candidate_id}: its attempt record holds no start time "
                            f"(started_at), so nothing shows that the extra verifiers ({ids}) were frozen before it existed "
                            "(protocol §15.5)")
        else:
            starts.append((t, c.attempt.started_at, name, c.candidate_id))
    first = min(starts, key=lambda x: x[0]) if starts else None
    for s in frozen:
        what = f"{m.task_id}: extra verifier {s.verifier_id} ({EXTRA_VERIFIERS})"
        at = _time(s.frozen_at)
        if at is None:
            problems.append(f"{what} records no time of freezing (frozen_at {s.frozen_at!r}), so nothing shows that it was "
                            "frozen before the fresh attempts it grades existed (protocol §15.5)")
        elif first is not None and at >= first[0]:
            problems.append(f"{what} was frozen at {s.frozen_at}, not before the first fresh attempt it grades started "
                            f"({first[3]} of stratum {first[2]}, at {first[1]}); protocol §15.5 freezes it before any "
                            "fresh attempt exists")
    return problems


def main(*argv: str) -> int:
    a = _args(list(argv))
    names = list(dict.fromkeys(a.strata or []))
    problems: list[str] = []
    if a.only_strata and not names:
        problems.append("--only-strata needs at least one stratum (--strata NAME); evaluate refuses it without one")

    def note(msg: str) -> None:
        print(f"NOTE: {msg}")

    def pool_problem(msg: str) -> None:  # a problem of the task's own held-out pool: a note when the run does not grade it
        if a.only_strata:
            note(f"{msg} ({NOT_GRADED})")
        else:
            problems.append(msg)

    def pool_warning(msg: str) -> None:
        if a.only_strata:
            note(f"{msg} ({NOT_GRADED})")
        else:
            print(f"WARN: {msg}")

    for td in map(Path, a.tasks):
        m = load(td / "task.json", TaskManifest)
        specs = [load(td / p, VerifierSpec) for p in m.verifiers]
        extras, extra_problems = (extra_verifier_problems(td, m, specs, a.conditions, with_strata=bool(names))
                                  if a.with_extra_verifiers else ([], []))
        missing_conditions = sorted(set(a.conditions or []) - {s.condition.value for s in [*specs, *extras]})
        if missing_conditions:
            problems.append(f"{m.task_id}: no verifier for condition(s) {missing_conditions}")
        problems += [f"{m.task_id}: reconstruction: {p}" for p in recorded_check(td, R).problems]
        problems += gate_problems(td, m, pilot=a.pilot)
        for s in specs:
            if not s.frozen:
                problems.append(f"{m.task_id}: verifier {s.verifier_id} not frozen")
                continue
            try:
                check_frozen(s, td)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{m.task_id}: verifier {s.verifier_id} changed after freezing: {exc}")
        problems += extra_problems
        cands = [load(td / p, Candidate) for p in m.candidates]
        problems += shadowing_problems(m, cands)
        held = [c for c in cands if c.split.value == "eval" and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]
        by_origin = {o: sum(c.origin == o for c in held) for o in CandidateOrigin}
        if by_origin[CandidateOrigin.observed_pre_correction] != 1 or by_origin[CandidateOrigin.valid_alternative] != 2 \
                or by_origin[CandidateOrigin.constructed_near_miss] != 5:
            pool_problem(f"{m.task_id}: incomplete held-out pool {({k.value: v for k, v in by_origin.items() if v})}")
        for c in held:
            if not has_d19_proposal(c):
                pool_problem(f"{m.task_id}: {c.candidate_id} has no D19 proposal")
        from tracecontract.cli import SNAPSHOTS
        from tracecontract.tasks import verify_snapshot

        if not (SNAPSHOTS / m.task_id).is_dir():
            problems.append(f"{m.task_id}: base snapshot not built (run `tracecontract snapshot tasks/{m.task_id}`)")
        elif not verify_snapshot(td, SNAPSHOTS):
            problems.append(f"{m.task_id}: base snapshot does not match its recorded manifest")
        from tracecontract.analysis import _norm_patch

        dev = {_norm_patch(c.patch): c.candidate_id for c in cands if c.split.value == "dev" and c.patch}
        seen: dict[str, str] = {}
        for c in held:
            if not c.patch:
                continue
            k = _norm_patch(c.patch)
            if k in dev:
                pool_warning(f"{m.task_id}: held-out {c.candidate_id} has the same graded patch as development candidate "
                             f"{dev[k]}")
            if k in seen:
                pool_warning(f"{m.task_id}: held-out {c.candidate_id} has the same graded patch as held-out candidate "
                             f"{seen[k]}")
            seen.setdefault(k, c.candidate_id)
        if (SNAPSHOTS / m.task_id).is_dir():
            from tracecontract.duplicates import same_code_duplicates

            rec = same_code_duplicates(td, SNAPSHOTS)
            dp = td / "labels" / "duplicates.json"
            if not dp.exists() or json.loads(dp.read_text()) != rec:
                pool_problem(f"{m.task_id}: same-code duplicates differ from labels/duplicates.json "
                             f"(run scripts/find_duplicates.py and disclose): {rec['duplicates']}")
            for cid, hits in rec["duplicates"].items():
                pool_warning(f"{m.task_id}: held-out {cid} has the same code (comments and docstrings ignored) as {hits}")
        audit_p = td / "labels" / "generator_audit.json"
        audit = json.loads(audit_p.read_text()) if audit_p.exists() else {}
        for ws, rec in audit.items():
            if ws == "_rules":
                continue
            # Only the audit of a generator of the task's own held-out candidates is a problem of the pool: the audit of a
            # verifier's writer (refcheck: the reference checks, D19's source 1) fails whatever the run grades.
            audit_problem = pool_problem if generates_held_out(ws, m.task_id, held) else problems.append
            if rec.get("hits") and not rec.get("assessment"):
                audit_problem(f"{m.task_id}: generator audit {ws} has unassessed hits")
            strict = rec.get("strict_reaudit")
            if not strict:
                audit_problem(f"{m.task_id}: generator audit {ws} has no strict re-audit (scripts/strict_reaudit.py, D44)")
            elif not strict.get("assessment") or any("error" in t for t in strict.get("transcripts", {}).values()):
                audit_problem(f"{m.task_id}: strict re-audit of {ws} is unassessed or lacks a transcript")
        needed = {"eval-alt-1", "eval-alt-2", "eval-nm"}
        missing = sorted(needed - set(audit))
        if missing:
            pool_problem(f"{m.task_id}: generator audits missing for {missing}")
        if names:  # the candidate strata the run grades (protocol v0.7 §15.4, v0.8 §16.2, v0.10 §18.1)
            loaded, stratum_problems = strata_problems(td, m, names, {c.candidate_id for c in cands})
            problems += stratum_problems
            for st in loaded.values():
                problems += stratum_label_problems(m, st)
                attempt_problems, attempt_notes = attempt_audit_problems(m, st, repo_root=R)
                problems += attempt_problems
                for n in attempt_notes:
                    note(n)
                problems += shadowing_problems(m, [c for _, c in st.candidates], stratum=st.name)
            problems += frozen_before_attempts_problems(m, graded_verifiers(extras, a.conditions), loaded)
    from tracecontract.sandbox.docker_runner import HARNESS_VERSION

    problems += run_problems(repeats=a.repeats, harness=HARNESS_VERSION, run_id=a.run_id)
    running = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout.split()
    if running:
        problems.append(f"{len(running)} container(s) running; a run needs an idle host")
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=R, capture_output=True, text=True).stdout.strip()
    if dirty:
        problems.append("git working tree not clean")
    for p in problems:
        print("FAIL:", p)
    print("preflight:", "ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
