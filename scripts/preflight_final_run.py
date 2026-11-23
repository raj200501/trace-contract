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
* the base snapshot exists and matches its recorded manifest (under the root that
  ``tracecontract.roots.snapshot_root`` gives the task: ``snapshots/`` for a controlled task);
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
* its ``--run-id``, if given, names no recorded run (``results/runs/<id>`` is not changed), nor one
  under ``data/natural/runs`` (``roots.NATURAL_RUNS``, where evaluate writes a natural run);
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

A natural PR-review task (population ``natural:pr-review``, built under the git-ignored
``data/natural/``; protocol §15.5, §15.6, §16.4, §17, §19, §20) is checked as above, with these
differences and additions:
* its base snapshot is looked up where ``roots.snapshot_root`` puts it (``data/natural/snapshots``,
  the root its provenance notes record);
* its held-out pool is the pre-review state (origin ``natural_pre_review``), 2 valid alternatives
  and 3 near misses, and nothing else (§15.6);
* its S10 record (``s10.json``) has the outcome ``passed``, and its row in the committed index
  (``data/manifests/natural_tasks_index.json`` as the HEAD commit holds it) has ``s11`` true (§16.4).
  The acceptance gate's own reasons on these two (``s10:``, ``index:``) are then not repeated;
* the pre-review state carries its source-evidence label, invalid (§15.6);
* at least 2 of the 3 near misses name, in a construction label, a scored active requirement of the
  reference contract that is introduced at a correction event: the review comment or one of the
  reviewer's later replies (``session.json`` ``metadata.events.correction`` and ``.replies``, as
  ``contract.correction_event_ids`` reads them; §15.6);
* each of its valid alternatives and near misses carries a complete generation record
  (``verifier.generation_record_problems``; §15.6), and every verifier of the task, those of
  ``task.json`` and of ``verifiers_extra.json`` (the reference checks and the independent labeler
  included), was frozen (``frozen_at``) before the first of them was generated: the earliest
  ``generation.budget.started_at`` of their generation records (§15.5, §19.7). A pool candidate whose
  record holds no start time fails;
* the run grades the independent labeler (§15.5, §15.6): with ``--with-extra-verifiers`` (unless
  ``task.json`` itself lists it) and a ``--conditions`` that names its condition. Its ``status.json``
  (beside its spec) records the labeler's round, 1 as written or 2 after its one revision (§15.5,
  §19.8); any other round fails. One whose ``status.json`` does not say ``usable`` (whatever else it
  says, or says nothing), or that has none, is a note: the second labeling leaves it out;
* B1 (``repo_tests``) or B3 (``diff_derived``) named with ``--conditions`` and absent from the task is a
  note, not a missing condition, when the family's record shows it unavailable: ``s10.json``
  ``b1.available`` false (§17.2), or a B3 selection record (``verifiers/<id>/selection.json``,
  ``scripts/select_b3_tests.py``) with ``b3_available`` false. Without such a record it fails. A B3
  verifier left unfrozen in ``task.json`` after a selection that kept no test fails as not frozen, with
  a hint that it must be kept out of the run;
* ``labels/generator_audit.json`` audits every agent of the natural recipe (decision log D64;
  ``NATURAL_AUDIT_ROLES``, entries named after the agents' workspaces): the contract proposers, the generators, the revisers
  of the audited verifiers (``revise-initial-<i>`` and ``revise-full-<i>``, as many as the verifier's
  audit record counts revisions), the reference-contract drafter, the reference-check writer and at
  least one reviewer (``refcheck-review-<r>``), the labeler writer and, when its ``status.json``
  records round 2, its revision (``labeler-revision``), the five pool generators and the two mappers
  (``mapper-1``, ``mapper-2``). Every entry was made with the natural-agent profile (``profile``
  ``natural-agent:v1``: ``scripts/audit_eval_generators.py --profile natural``, which
  ``scripts/strict_reaudit.py`` re-audits with the same profile), and every entry that the audit
  flags (its ``hits``, in tool inputs, its ``exposures``, in tool outputs, or ``flagged``) has a
  written ``assessment``;

and, for a run with a natural PR-review task (protocol §20.2, decision log D71: the arm has two runs, one
per sample, in place of §19.7's one run):
* its run id is one of the two (``--run-id``, which a natural run needs; :data:`NATURAL_RUN_SAMPLES`):
  ``natural-pr-v1`` grades the accepted (``s11``) families of the first sample, the rows of the committed
  index whose ``sample`` is ``first`` (the S9 sample of §15.6), and ``natural-pr-v2`` those of the
  extension, whose ``sample`` is ``extension`` (§19.2, §19.3). Any other run id is refused, and
  ``run_problems`` checks that the one given is new;
* it grades every accepted family of its sample, no family of the other sample (so it never mixes the
  two samples; under a run id that names neither run, a mix fails too) and no task of another
  population (§15.2). A row of the committed index that names neither sample fails, since nothing then
  shows which run grades it;
* building has stopped for its sample by the committed index. The index's S9 record, ``s9_complete``,
  gives for each sample the number of its comments that S9 has screened (``screened``: the whole
  sample, 150 comments for the first, §15.6, and 534 for the extension, §19.2) and the task ids of the
  families and reserves formed from it (``families``; §15.6, §17.3, §19.3), each of which must have a
  row in the index; a bare ``true`` shows neither. A family or reserve has been processed when it has
  an S10 outcome (``passed`` or ``rejected``) or its repository has no open place: 2 accepted families,
  counted over both samples, since §15.6's cap applies to both together (§19.3).
  * ``natural-pr-v1``: S9 is complete for the first sample, and every family and reserve of the first
    sample has been processed (the rule of §19.5 restricted to the first sample, §20.2);
  * ``natural-pr-v2``: the index counts 30 accepted tasks in all (both samples), or S9 is complete for
    the extension and every family and reserve of the extension has been processed (§20.2).

  ``tracecontract natural-index`` writes the S9 record when its input files can be read, and leaves it
  out otherwise (``natural_pr.s9_record``). For a run id that names neither run, building is checked as
  §19.5 reads for both samples together (30 accepted, or both samples complete with every family
  processed): :func:`building_problems` without a sample, the rule that ``scripts/propose_labels.py``
  applies before it proposes any D19 label.

The checks of a natural task's pool (its composition, labels, near-miss targets, generation records
and freezing order, and the audits of its pool generators) are notes with ``--only-strata``, as the
pool checks above.

A note (``NOTE:``) never fails the pre-flight. Without ``--strata``, ``--only-strata`` and
``--with-extra-verifiers``, the pre-flight checks only what the first two lists name (for a
controlled task).

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
       python scripts/preflight_final_run.py data/natural/tasks/NP-03 ... --run-id natural-pr-v1|natural-pr-v2 --repeats 3
       --pilot --with-extra-verifiers --conditions C ...
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
from typing import Any, NamedTuple

from tracecontract import roots
from tracecontract.analysis import (
    INDEPENDENT_LABELER,
    LABEL_SUPPORT_CONDITION,
    PILOT_LABELER,
    ConditionConflict,
    _check_conditions,
)
from tracecontract.contract import (
    NATURAL_INDEX,
    S10_RECORD,
    committed_text,
    correction_event_ids,
    task_gate,
)
from tracecontract.evaluate import EXTRA_VERIFIERS, extra_verifier_paths
from tracecontract.reconstruction import recorded_check
from tracecontract.schemas import (
    Candidate,
    CandidateOrigin,
    ContractVariant,
    LabelerKind,
    Population,
    Session,
    Split,
    TaskContract,
    TaskManifest,
    VerifierCondition,
    VerifierSpec,
)
from tracecontract.shadowing import shadowing_files
from tracecontract.store import load
from tracecontract.strata import Stratum, StratumError, load_strata, load_stratum
from tracecontract.verifier import check_frozen, generation_record_problems

R = Path(__file__).resolve().parents[1]
NEW_RUN_REPEATS = 3  # protocol v0.7 §15.3: every new pair is graded three times
MIN_HARNESS = "tc-harness/0.3.5"  # protocol v0.8 §16.1: new runs use 0.3.5 (0.3.4 is never used for a run)
# With --only-strata, what the checks of the task's own held-out pool report is a note: this run does not grade it.
NOT_GRADED = "with --only-strata the run does not grade the task's own candidates"
# The lists of attempt ids that a manual review of a fresh-attempt audit report holds (protocol §18.1).
REVIEW_LISTS = ("flagged_by_script", "judged_false_positive", "excluded_after_review")

# --- natural PR-review tasks (protocol §15.5, §15.6, §16.4, §17, §19) --------------------------------------------------
# A family's held-out pool, by origin: the pre-review state, 2 valid alternatives and 3 near misses, nothing else (§15.6).
NATURAL_POOL = {CandidateOrigin.natural_pre_review: 1, CandidateOrigin.valid_alternative: 2,
                CandidateOrigin.constructed_near_miss: 3}
CORRECTION_NEAR_MISSES = 2  # §15.6: at least two of the three near misses target the correction
# NATURAL_INDEX (the committed index of the natural tasks, natural_pr.INDEX) and S10_RECORD (a family's S10 record, in
# its task directory, natural_pr.S10_RECORD) are the acceptance gate's (tracecontract.contract), read the same way here.
SESSION_FILE = "session.json"  # a natural PR-review task's session (tasks.PR_SESSION_FILE)
# §20.2 (D71): the arm's two runs, by the sample whose accepted families each grades (the committed index's "sample").
NATURAL_RUN_SAMPLES = {"natural-pr-v1": "first", "natural-pr-v2": "extension"}
SAMPLE_NAMES = {"first": "the first sample", "extension": "the extension"}
NATURAL_RUNS_REL = roots.NATURAL_RUNS.relative_to(roots.REPO)  # data/natural/runs, where evaluate writes a natural run
STOP_ACCEPTED = 30  # §19.5, §20.2: building stops at 30 accepted tasks in all (both samples) ...
# ... or when every family has been processed: of both samples (§19.5), of the first (natural-pr-v1) or of the extension
# (natural-pr-v2; §20.2). S9 has then screened every comment of the sample (the S9 sample of §15.6, D47: 150 of the 684
# S8a comments; its extension, §19.2: the other 534).
S9_SAMPLE_SIZES = {"first": 150, "extension": 534}
S9_RECORD = "s9_complete"  # the index's S9 record: {sample: {"screened": n, "families": [task id, ...]}} (s9_problems)
FAMILY_CAP = 2  # §15.6: at most 2 families come from one repository
S10_FINAL = ("passed", "rejected")  # the S10 outcomes of a processed family
B1 = VerifierCondition.repo_tests.value
B3 = VerifierCondition.diff_derived.value
LABELER_STATUS = "status.json"  # beside the independent labeler's spec: {"status": "usable" | "unusable", "round": 1 | 2}
LABELER_ROUNDS = (1, 2)  # §15.5, §19.8: the labeler as written (round 1) and after its one revision (round 2)
B3_SELECTION = "selection.json"  # beside a B3 verifier's spec: scripts/select_b3_tests.py's record
# The audit profile of every natural agent (tracecontract.controlled.NATURAL_PROFILE, written by
# scripts/audit_eval_generators.py --profile natural, which strict_reaudit.py reads to re-audit with the same profile).
NATURAL_AUDIT_PROFILE = "natural-agent:v1"
# The entries of labels/generator_audit.json (each named after its agent's workspace) that a natural PR-review family
# needs before its run: one audit of every agent of the natural recipe (D64), by role, as D64's table of workspaces and
# audit entries lists them. Further entries are needed where the family's records count further agents: a reviser per
# revision of an audited verifier (REVISER, i = 1 .. its audit record's iterations), the labeler's revision
# (LABELER_REVISION, when the labeler's status.json records round 2) and at least one reviewer of the reference checks
# (REFCHECK_REVIEWER). Other entries (the fixers of the reference checks, whose rounds no record counts, and a checker)
# are checked when present and are not required.
NATURAL_AUDIT_ROLES: dict[str, tuple[str, ...]] = {
    "contract proposers": ("contract-initial", "contract-full"),
    "generators": ("testgen-initial", "testgen-full", "freeform", "diff-derived", "attack-initial", "attack-full",
                   "alt-initial", "alt-full"),
    "reference-contract drafter": ("refcontract",),
    "reference-check writer": ("refcheck",),
    "labeler writer": ("labeler",),
    "pool generators": ("eval-alt-1", "eval-alt-2", "eval-nm-1", "eval-nm-2", "eval-nm-3"),
    "mappers": ("mapper-1", "mapper-2"),
}
REVISER = "revise-{variant}-{i}"  # the reviser of round i of initial_audited (variant initial) or full_audited (full)
AUDITED_VARIANTS = {VerifierCondition.initial_audited.value: "initial", VerifierCondition.full_audited.value: "full"}
REFCHECK_REVIEWER = re.compile(r"refcheck-review-\d+")  # every natural family's reference checks are reviewed
LABELER_REVISION = "labeler-revision"


def _harness_version(v: str | None) -> tuple[int, ...] | None:
    m = re.fullmatch(r"tc-harness/(\d+(?:\.\d+)*)", v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def run_problems(*, repeats: int, harness: str | None, run_id: str | None = None, runs_root: Path = R / "results" / "runs",
                 natural_runs_root: Path | None = roots.NATURAL_RUNS) -> list[str]:
    """Problems with the parameters of a new run (protocol v0.7 §15.3, v0.8 §16.1). The run id must be new both under
    ``runs_root`` (``results/runs``) and under ``natural_runs_root`` (``data/natural/runs``, where evaluate writes a
    natural PR-review run; None: not checked)."""
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
    if run_id is not None and natural_runs_root is not None and (natural_runs_root / run_id).exists():
        out.append(f"run: data/natural/runs/{run_id} already exists; a new run needs a new run id (recorded runs are not "
                   "changed)")
    return out


def _reported_apart(m: TaskManifest) -> tuple[str, ...]:
    """The prefixes of the acceptance gate's reasons that the pre-flight reports itself: a failed reconstruction check,
    and for a natural PR-review task its S10 record and its row in the committed index (:func:`natural_record_problems`)."""
    return ("reconstruction:", "s10:", "index:") if m.population == Population.natural_pr_review else ("reconstruction:",)


def gate_problems(td: Path, m: TaskManifest, *, pilot: bool) -> list[str]:
    """The task acceptance gate as ``tracecontract evaluate`` applies it (what :func:`_reported_apart` names is reported
    apart)."""
    g = task_gate(td, R)
    apart = _reported_apart(m)
    refusals = [r for r in g.refusals if not r.startswith(apart)]
    if refusals:
        return [f"{m.task_id}: refused by the acceptance gate ({'; '.join(refusals)})"]
    others = [r for r in g.reasons if not r.startswith(apart)]
    if g.refusals or (g.status == "accepted" and not others):
        return []  # only checks that main reports itself stand in the way
    first = others[0] if others else "the gate passes, but the task was not accepted (tracecontract accept-task)"
    if pilot:
        print(f"WARN: {m.task_id}: not accepted through the acceptance gate (status {g.status!r}; {len(others)} reason(s), "
              f"first: {first}); checked as an automated pilot (--pilot)")
        return []
    return [(f"{m.task_id}: not accepted through the acceptance gate (status {g.status!r}; {len(others)} reason(s), first: "
             f"{first}); pass --pilot here and to evaluate for an automated pilot")]


def _args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="preflight_final_run.py", description=__doc__.split("\n", 1)[0])
    ap.add_argument("tasks", nargs="+", help="task directories (tasks/<id>; data/natural/tasks/<id> for natural PR-review tasks)")
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


# --- natural PR-review tasks (see the module docstring) ----------------------------------------------------------------

def _json_object(path: Path) -> dict[str, Any] | None:
    """The JSON object in ``path``, or None (no file, unreadable, or not an object)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _task_order(task_id: str) -> tuple[int, str]:
    m = re.fullmatch(r"NP-(\d+)", task_id)
    return (int(m.group(1)) if m else 10 ** 9, task_id)


# Why contract.committed_text gives no text: it folds every case into None, so the reason names them all.
INDEX_NOT_SHOWN = ("git gives no text for it from the HEAD commit: the directory is not a git repository that git will "
                   "read, the repository has no commit, its HEAD commit does not hold the file, or the file is not UTF-8")


def committed_index(repo_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """The natural tasks' index (:data:`NATURAL_INDEX`) as the HEAD commit of the repository at ``repo_root`` holds it,
    read as the acceptance gate reads it (``contract.committed_text``): ``(index, None)``, or ``(None, why it cannot be
    read)``. The working tree's index, which ``tracecontract natural-index`` rewrites before it is committed, is not
    read, and no ``GIT_*`` variable of the caller (a hook's ``GIT_DIR``) redirects git."""
    text = committed_text(repo_root, NATURAL_INDEX)
    if text is None:  # committed_text does not say why git gave no text, so neither can the reason
        return None, INDEX_NOT_SHOWN
    try:
        index = json.loads(text)
    except ValueError:
        return None, "it is not JSON"
    if not isinstance(index, dict) or not isinstance(index.get("tasks"), list):
        return None, "it lists no tasks"
    return index, None


def index_rows(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The rows of a committed index (:func:`committed_index`) by task id."""
    return {r["task_id"]: r for r in index["tasks"] if isinstance(r, dict) and isinstance(r.get("task_id"), str)}


def row_sample(row: dict[str, Any]) -> str | None:
    """The S9 sample of an index row (its ``sample``: one of :data:`S9_SAMPLE_SIZES`, which ``natural_pr.sample_of``
    gives by task id), or None when it names neither."""
    sample = row.get("sample")
    return sample if isinstance(sample, str) and sample in S9_SAMPLE_SIZES else None


def natural_record_problems(td: Path, m: TaskManifest, index: dict[str, Any] | None) -> list[str]:
    """A natural PR-review task's S10 record and its row in the committed index (protocol §15.6, §16.4): ``s10.json``
    records the outcome ``passed``, and the committed index gives the task ``s11`` true. An index that cannot be read is
    reported once, for the run (:func:`building_problems`)."""
    out = []
    s10 = _json_object(td / S10_RECORD)
    if s10 is None:
        out.append(f"{m.task_id}: no readable {S10_RECORD}, so nothing shows that the family passed S10 (protocol §15.6, "
                   "§16.4)")
    elif s10.get("outcome") != "passed":
        out.append(f"{m.task_id}: its S10 outcome ({S10_RECORD}) is {s10.get('outcome')!r}, not 'passed'; only a family that "
                   "passes S10 is built and run (protocol §15.6, §16.4)")
    if index is not None:
        row = index_rows(index).get(m.task_id)
        if row is None:
            out.append(f"{m.task_id}: no row in the committed index ({NATURAL_INDEX} in the HEAD commit)")
        elif row.get("s11") is not True:
            out.append(f"{m.task_id}: not S11 in the committed index ({NATURAL_INDEX} in the HEAD commit); S11 means passing "
                       "S10 within the family cap (protocol §16.4)")
    return out


def natural_pool_problem(m: TaskManifest, held: list[Candidate]) -> str | None:
    """What is wrong with a natural PR-review family's held-out pool (None if nothing): it must be :data:`NATURAL_POOL`."""
    counts = Counter(c.origin for c in held)
    if all(counts[o] == n for o, n in NATURAL_POOL.items()) and set(counts) <= set(NATURAL_POOL):
        return None
    found = {o.value: counts[o] for o in CandidateOrigin if counts[o]}
    want = ", ".join(f"{o.value} {n}" for o, n in NATURAL_POOL.items())
    return (f"{m.task_id}: held-out pool {found} is not a natural PR-review family's ({want}, and nothing else; protocol "
            "§15.6)")


def source_evidence_problems(m: TaskManifest, held: list[Candidate]) -> list[str]:
    """The pre-review state's source-evidence label (protocol §15.6): present, and invalid with respect to the correction."""
    out = []
    for c in held:
        if c.origin != CandidateOrigin.natural_pre_review:
            continue
        label = c.source_evidence_label()
        if label is None:
            out.append(f"{m.task_id}: {c.candidate_id} has no source-evidence label (labeler kind source_evidence), the label "
                       "of the pre-review acceptance estimand (protocol §15.6)")
        elif label.value != "invalid":
            out.append(f"{m.task_id}: {c.candidate_id}: its source-evidence label is {label.value!r}; protocol §15.6 labels "
                       "the pre-review state invalid with respect to the correction")
    return out


def near_miss_problems(td: Path, m: TaskManifest, held: list[Candidate]) -> list[str]:
    """At least :data:`CORRECTION_NEAR_MISSES` of a natural family's near misses target the correction (protocol §15.6):
    one of their construction labels names a scored active requirement of the reference contract that is introduced at
    a correction event (``contract.correction_event_ids``: the review comment and the reviewer's later replies, as
    make-contract reads them). Requirement ids are not printed (they are the drafter's)."""
    nms = [c for c in held if c.origin == CandidateOrigin.constructed_near_miss]
    if not nms:
        return []  # the pool check reports it
    why = "nothing shows that its near misses target the correction (protocol §15.6)"
    rel = m.contracts.get(ContractVariant.reference.value)
    if rel is None:
        return [f"{m.task_id}: the task has no reference contract, so {why}"]
    try:
        contract = load(td / rel, TaskContract)
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return [f"{m.task_id}: the reference contract {rel} does not load ({type(exc).__name__}), so {why}"]
    try:
        session = load(td / SESSION_FILE, Session)
    except Exception as exc:  # noqa: BLE001
        return [(f"{m.task_id}: {SESSION_FILE} does not load ({type(exc).__name__}), so its correction events are unknown "
                 f"and {why}")]
    corrections = set(correction_event_ids(session))
    targets = {r.req_id for r in contract.requirements if r.active and r.scored and r.introduced_at in corrections}
    known = {r.req_id for r in contract.requirements}
    on, off = [], []
    for c in nms:
        named = {rid for lb in c.labels if lb.labeler_kind == LabelerKind.construction for rid in lb.violated_requirements}
        if named & targets:
            on.append(c.candidate_id)
        elif not named:
            off.append(f"{c.candidate_id} names no requirement in a construction label")
        elif not named & known:
            off.append(f"{c.candidate_id} names no requirement of the reference contract")
        else:
            off.append(f"{c.candidate_id} names no scored active requirement introduced at a correction event")
    if len(on) >= CORRECTION_NEAR_MISSES:
        return []
    return [(f"{m.task_id}: {len(on)} of its {len(nms)} near misses target the correction; at least {CORRECTION_NEAR_MISSES} "
             "must name, in a construction label, a scored active requirement of the reference contract introduced at the "
             f"review comment or a reply (the reference contract has {len(targets)}; protocol §15.6): {'; '.join(off)}")]


def generation_start(c: Candidate) -> tuple[datetime | None, str | None]:
    """When the agent run that generated a constructed candidate started (``generation.budget.started_at``, with a time
    zone; for a record that combines runs, the earliest start), and the recorded text; None for a record without one."""
    gen = getattr(c, "generation", None)  # Candidate.generation: the record add-candidate --generation-record keeps
    budget = getattr(gen, "budget", None)
    raw = budget.get("started_at") if isinstance(budget, dict) else None
    return (_time(raw), raw) if isinstance(raw, str) else (None, None)


def frozen_before_pool_problems(m: TaskManifest, specs: list[tuple[str, VerifierSpec]], held: list[Candidate]) -> list[str]:
    """Every frozen verifier of a natural family (``specs``: where each is registered, ``task.json`` or
    ``verifiers_extra.json``, and the spec) was frozen before the first of its valid alternatives and near misses was
    generated (protocol §15.5: the labeler is frozen before any natural held-out candidate exists; §19.7: a family's
    verifiers are frozen before its held-out pool is generated). A verifier that is not frozen is reported apart.

    The start of a pool candidate's generation is the evidence, so its generation record must also be complete
    (``verifier.generation_record_problems``, as ``add-candidate --generation-record`` requires for a natural task;
    §15.6: every generated artifact carries one): a start time alone, as a hand-registered candidate might hold it, does
    not show which agent run it times. A start that such a record holds still counts towards the earliest start."""
    pool = [c for c in held if c.origin in (CandidateOrigin.valid_alternative, CandidateOrigin.constructed_near_miss)]
    if not pool:
        return []
    problems = []
    starts = []
    for c in pool:
        t, raw = generation_start(c)
        if t is None:
            problems.append(f"{m.task_id}: {c.candidate_id} records no start of its generation (generation.budget.started_at, "
                            "with a time zone), so nothing shows that the family's verifiers were frozen before it was "
                            "generated (protocol §15.5, §19.7)")
        else:
            starts.append((t, raw, c.candidate_id))
            incomplete = generation_record_problems(getattr(c, "generation", None))
            if incomplete:
                problems.append(f"{m.task_id}: {c.candidate_id}: its generation record is not complete "
                                f"({'; '.join(incomplete)}); every generated artifact carries a complete one (protocol "
                                "§15.6; add-candidate --generation-record), and its start is the evidence that the "
                                "family's verifiers were frozen before it was generated (§15.5, §19.7)")
    first = min(starts, key=lambda x: x[0]) if starts else None
    for where, s in specs:
        if not s.frozen:
            continue
        what = f"{m.task_id}: verifier {s.verifier_id} ({where})"
        at = _time(s.frozen_at)
        if at is None:
            problems.append(f"{what} records no time of freezing (frozen_at {s.frozen_at!r}), so nothing shows that it was "
                            "frozen before the held-out pool was generated (protocol §15.5, §19.7)")
        elif first is not None and at >= first[0]:
            problems.append(f"{what} was frozen at {s.frozen_at}, not before the first candidate of the held-out pool was "
                            f"generated ({first[2]}, started at {first[1]}); protocol §19.7 freezes a family's verifiers "
                            "before its held-out pool is generated")
    return problems


def sidecar_specs(td: Path, m: TaskManifest) -> list[tuple[str, VerifierSpec]]:
    """The verifiers that ``verifiers_extra.json`` adds (as evaluate adds them), by path, quietly: one that does not load
    is left out here (``--with-extra-verifiers`` reports it, and a natural run needs that option)."""
    try:
        paths = [p for p in extra_verifier_paths(td) if p not in m.verifiers]
    except Exception:  # noqa: BLE001
        return []
    def spec(p: str) -> VerifierSpec | None:
        try:
            return load(td / p, VerifierSpec)
        except Exception:  # noqa: BLE001
            return None

    return [(p, s) for p, s in ((p, spec(p)) for p in paths) if s is not None]


class LabelerStatus(NamedTuple):
    """What an independent labeler's ``status.json`` records (:func:`labeler_status`)."""

    usable: bool  # the record says "usable" (and records a round of LABELER_ROUNDS)
    round: int | None  # the round it records, when that is one of LABELER_ROUNDS
    said: str  # what the record says, for the note of a labeler that is not usable
    problem: str | None  # why the record fails the pre-flight (a round that is not 1 or 2), or None


def labeler_status(td: Path, rel: str) -> LabelerStatus:
    """The ``status.json`` (beside the spec ``rel``) of an independent labeler: usable only if it says ``usable``; a
    record that says anything else, nothing, or that is missing or unreadable, is not (a note: the second labeling leaves
    the labeler out). A readable record must record the round, 1 (as written) or 2 (after the one revision that §15.5
    allows); any other round, or none, is a problem: a labeler revised twice is outside the protocol, and without the
    round nothing shows whether a revision (whose audit the family needs) exists."""
    path = (td / rel).parent / LABELER_STATUS
    rec = _json_object(path)
    shown = path.relative_to(td).as_posix() if path.is_relative_to(td) else str(path)
    if rec is None:
        return LabelerStatus(False, None, f"no readable {shown}", None)
    raw = rec.get("round")
    rnd = raw if isinstance(raw, int) and not isinstance(raw, bool) and raw in LABELER_ROUNDS else None
    status = rec.get("status")
    problem = None if rnd is not None else (
        f"{shown} records {'no round' if raw is None else f'round {raw!r}'}; an independent labeler records round 1 as "
        "written or round 2 after its one revision (protocol §15.5, §19.8), and is reported unusable if it still fails")
    return LabelerStatus(status == "usable" and rnd is not None, rnd, f"{shown} says {status!r}", problem)


def b3_selections(td: Path) -> list[tuple[str, dict[str, Any]]]:
    """The B3 selection records of a task (``verifiers/<id>/selection.json`` of condition diff_derived), by path."""
    out = []
    for p in sorted((td / "verifiers").glob(f"*/{B3_SELECTION}")):
        rec = _json_object(p)
        if rec is not None and rec.get("condition") == B3:
            out.append((p.relative_to(td).as_posix(), rec))
    return out


def b3_unavailable(td: Path) -> str | None:
    """The B3 selection record that shows B3 unavailable for the family (every record of the task kept no test), or None."""
    recs = b3_selections(td)
    if recs and all(rec.get("b3_available") is False for _, rec in recs):
        return recs[0][0]
    return None


def unavailable_baselines(td: Path, m: TaskManifest, missing: list[str]) -> list[tuple[str, str]]:
    """Among the conditions ``missing`` (named with ``--conditions``, with no verifier in the task), B1 and B3 when the
    family's records show them unavailable, each with its note (see the module docstring)."""
    out = []
    if B1 in missing:
        b1 = (_json_object(td / S10_RECORD) or {}).get("b1")
        if isinstance(b1, dict) and b1.get("available") is False:
            out.append((B1, (f"{m.task_id}: B1 ({B1}) is unavailable for this family: {S10_RECORD} records it as unavailable "
                             "(b1.available false; protocol §17.2, not a rejection); the run has no B1 verdict for it")))
    if B3 in missing:
        rel = b3_unavailable(td)
        if rel is not None:
            out.append((B3, (f"{m.task_id}: B3 ({B3}) is unavailable for this family: its test selection kept no test ({rel}, "
                             "b3_available false; scripts/select_b3_tests.py); the run has no B3 verdict for it")))
    return out


def natural_audits_missing(present: set[str], specs: list[VerifierSpec], labeler_round: int | None) -> list[str]:
    """The entries of ``labels/generator_audit.json`` that a natural PR-review family needs (:data:`NATURAL_AUDIT_ROLES`,
    the revisers its audited verifiers' audit records count, a reviewer of the reference checks, the labeler's revision
    when ``labeler_round`` is 2 or more) and that are not ``present``, in the order of the recipe (D64)."""
    roles = NATURAL_AUDIT_ROLES
    need = [*roles["contract proposers"], *roles["generators"]]
    for cond, variant in AUDITED_VARIANTS.items():
        rounds = max((s.audit.iterations for s in specs if s.condition.value == cond and s.audit is not None), default=0)
        need += [REVISER.format(variant=variant, i=i) for i in range(1, rounds + 1)]
    need += [*roles["reference-contract drafter"], *roles["reference-check writer"]]
    if not any(REFCHECK_REVIEWER.fullmatch(ws) for ws in present):
        need.append("refcheck-review-1")
    need += roles["labeler writer"]
    if labeler_round is not None and labeler_round >= 2:
        need.append(LABELER_REVISION)
    need += [*roles["pool generators"], *roles["mappers"]]
    return [ws for ws in dict.fromkeys(need) if ws not in present]


def natural_audit_entry_problems(task_id: str, ws: str, rec: Any) -> list[str]:
    """The problems of the entry ``ws`` of a natural PR-review family's ``labels/generator_audit.json`` before its strict
    re-audit (checked apart): it was made with the natural-agent profile (:data:`NATURAL_AUDIT_PROFILE`), and, if the
    audit flags it, it has a written ``assessment``. The profile flags an agent by its ``hits`` (tool inputs) or its
    ``exposures`` (tool outputs), and records either in ``flagged``; every hit and exposure is assessed in writing."""
    if not isinstance(rec, dict):
        return [f"{task_id}: generator audit {ws} is not an audit record (a JSON object)"]
    out = []
    if rec.get("profile") != NATURAL_AUDIT_PROFILE:
        out.append(f"{task_id}: generator audit {ws} was not made with the natural-agent profile (its profile is "
                   f"{rec.get('profile')!r}, not {NATURAL_AUDIT_PROFILE!r}; scripts/audit_eval_generators.py --task-dir "
                   "<task dir> --profile natural audits every natural agent's tool inputs and outputs)")
    hits, exposures = rec.get("hits"), rec.get("exposures")
    if (hits or exposures or rec.get("flagged")) and not rec.get("assessment"):
        flags = [f"{len(v) if isinstance(v, list) else 1} {what}" for v, what in ((hits, "hit(s)"), (exposures, "exposure(s)"))
                 if v]
        out.append(f"{task_id}: generator audit {ws} has unassessed flags ({', '.join(flags) or 'flagged'}); every hit "
                   f"and exposure of the natural-agent profile is assessed in writing (assessment)")
    return out


def unprocessed_families(rows: list[dict[str, Any]], sample: str | None = None) -> list[str]:
    """The index rows without an S10 outcome (:data:`S10_FINAL`) in a repository that still has an open place: fewer than
    :data:`FAMILY_CAP` accepted families (§15.6, §17.3, §19.3; a repository with 2 accepted families builds no other).
    With ``sample``, only the rows of that sample (the index's ``sample``; §20.2) are reported, while a repository's
    accepted families are still counted over every row: the cap applies to both samples together (§19.3)."""
    repos: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        key = ("repo", str(r["repo_id"])) if r.get("repo_id") is not None else ("task", str(r.get("task_id")))
        repos.setdefault(key, []).append(r)
    out = []
    for rs in repos.values():
        if sum(r.get("s11") is True for r in rs) >= FAMILY_CAP:
            continue
        for r in rs:
            if sample is not None and row_sample(r) != sample:
                continue
            s10 = r.get("s10")
            if (s10.get("outcome") if isinstance(s10, dict) else None) not in S10_FINAL:
                out.append(str(r.get("task_id")))
    return sorted(out, key=_task_order)


def _int(value: Any) -> bool:
    """An integer that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def s9_problems(index: dict[str, Any], samples: tuple[str, ...] | None = None) -> list[str]:
    """What keeps the committed index from showing that S9 has been completed for both samples (or for those of
    ``samples``: one, for a run of §20.2), with every family it yields in the index (the second branch of §19.5's stop
    rule; see the module docstring). The index's S9 record (:data:`S9_RECORD`) gives, for each sample of
    :data:`S9_SAMPLE_SIZES`, ``screened``, the number of the sample's comments that S9 has screened (an S9 outcome:
    qualifies, fails, or excluded because the judges disagree), which must be the whole sample, and ``families``, the
    task ids of the families and reserves formed from the sample's qualifying comments (one family per PR; §15.6, §17.3,
    §19.3). Each of them must have a row in the index, so that no family of a sample that S9 has completed can be left
    out of :func:`unprocessed_families`. A bare ``true`` shows neither."""
    record = index.get(S9_RECORD, {})
    if not isinstance(record, dict):
        return [f"{S9_RECORD} in the index is {json.dumps(record)}, not an S9 record by sample"]
    rows = set(index_rows(index))
    out = []
    for sample, size in S9_SAMPLE_SIZES.items():
        if samples is not None and sample not in samples:
            continue
        rec = record.get(sample)
        at = f"{S9_RECORD}.{sample}"
        if not isinstance(rec, dict):
            what = "absent" if sample not in record else json.dumps(rec)
            out.append(f"S9 is not recorded as complete for the {sample} sample ({at} in the index is {what}, not the "
                       "number of its comments screened and the task ids of its families and reserves)")
            continue
        screened, families = rec.get("screened"), rec.get("families")
        if not (_int(screened) and screened == size):
            out.append(f"S9 has not screened the whole {sample} sample ({at}.screened is {screened!r}, the sample has "
                       f"{size} comments)")
        if not (isinstance(families, list) and all(isinstance(t, str) and t for t in families)):
            out.append(f"{at}.families is not a list of task ids, so nothing shows which families the {sample} sample "
                       "yields")
        else:
            absent = sorted(set(families) - rows, key=_task_order)
            if absent:
                shown = ", ".join(absent[:10]) + (", ..." if len(absent) > 10 else "")
                out.append(f"{len(absent)} of the {sample} sample's families and reserves ({at}.families) have no row in "
                           f"the index ({shown})")
    return out


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _ids(task_ids: list[str], limit: int = 10) -> str:
    """Task ids in id order, the first ``limit`` of them."""
    ids = sorted(task_ids, key=_task_order)
    return ", ".join(ids[:limit]) + (", ..." if len(ids) > limit else "")


def building_problems(index: dict[str, Any] | None, why: str | None, sample: str | None = None) -> list[str]:
    """Whether building has stopped by the committed index (see the module docstring): no natural verifier is graded on a
    held-out candidate before then (§19.7), or, for a run of §20.2, before the run of its family.

    Without ``sample``, the rule of §19.5 for both samples together: building has stopped at :data:`STOP_ACCEPTED`
    accepted tasks of both samples, or when S9 is complete for both samples with every family they yield in the index
    (:func:`s9_problems`) and every one of those families has been processed (:func:`unprocessed_families`).

    With ``sample``, the rule of §20.2 (D71) for the run of that sample (:data:`NATURAL_RUN_SAMPLES`): ``first``
    (``natural-pr-v1``), when S9 is complete for the first sample and every family of it has been processed; ``extension``
    (``natural-pr-v2``), at :data:`STOP_ACCEPTED` accepted tasks in all (both samples), or when S9 is complete for the
    extension and every family of it has been processed. A repository's open places are counted over both samples."""
    if sample is not None and sample not in S9_SAMPLE_SIZES:
        raise ValueError(f"no S9 sample {sample!r} (the samples are {', '.join(S9_SAMPLE_SIZES)})")
    if index is None:
        return [(f"natural: the committed index ({NATURAL_INDEX} in the HEAD commit) cannot be read ({why}), so nothing shows "
                 "that building has stopped or which families are accepted (protocol §16.4, §19.5)")]
    rows = list(index_rows(index).values())
    accepted = sum(r.get("s11") is True for r in rows)
    if sample != "first" and accepted >= STOP_ACCEPTED:  # 30 in all: no branch of natural-pr-v1's rule (§20.2)
        return []
    unscreened = s9_problems(index, None if sample is None else (sample,))
    pending = unprocessed_families(rows, sample)
    if not unscreened and not pending:
        return []
    open_ = list(unscreened)
    if pending:
        whose = "of a repository" if sample is None else f"of {SAMPLE_NAMES[sample]} in a repository"
        open_.append(f"{len(pending)} {_plural(len(pending), 'family', 'families')} {whose} with an open place "
                     f"{_plural(len(pending), 'has', 'have')} no S10 outcome ({', '.join(pending)})")
    if sample is None:
        return [(f"natural: building has not stopped by the committed index: it counts {accepted} accepted task(s) of both "
                 f"samples, and protocol §19.5 stops building at {STOP_ACCEPTED} or when every family of both samples has "
                 f"been processed; {'; '.join(open_)}. No natural verifier is graded on a held-out candidate before building "
                 "stops (§19.7)")]
    run = next(r for r, s in NATURAL_RUN_SAMPLES.items() if s == sample)
    if sample == "first":
        rule = (f"protocol §20.2 grades its accepted families in {run} once S9 is complete for it and every family and "
                "reserve of it has been processed")
    else:
        rule = (f"it counts {accepted} accepted task(s) in all, and protocol §20.2 grades the extension's accepted families "
                f"in {run} at {STOP_ACCEPTED} accepted tasks in all or once every family and reserve of the extension has "
                "been processed")
    return [(f"natural: building has not stopped for {SAMPLE_NAMES[sample]} by the committed index: {rule}; "
             f"{'; '.join(open_)}. No natural verifier is graded on a held-out candidate of a family before that family's "
             "run (§20.2)")]


# §20.2 (D71): what the natural arm's runs are, as the run-id and composition checks say it.
TWO_RUNS = ("protocol §20.2 grades the natural arm in two runs, natural-pr-v1 for the accepted families of the first sample "
            "and natural-pr-v2 for those of the extension")


def natural_run_id_problems(run_id: str | None) -> list[str]:
    """A run with natural PR-review tasks is one of the arm's two runs, :data:`NATURAL_RUN_SAMPLES` (§20.2, D71), so it is
    given one of their run ids, which :func:`run_problems` then checks is new (a natural run under another id would grade
    accepted families again)."""
    if run_id is None:
        return [(f"natural: pass --run-id natural-pr-v1 or natural-pr-v2 here and to evaluate: {TWO_RUNS}, and the "
                 "pre-flight checks that the run has not been made")]
    if run_id not in NATURAL_RUN_SAMPLES:
        return [f"natural: the run id is {run_id!r}; {TWO_RUNS}"]
    return []


def natural_run_problems(given: list[tuple[str, bool]], index: dict[str, Any] | None, run_id: str | None = None) -> list[str]:
    """A run with natural PR-review tasks (``given``: each task id and whether it is one) grades no task of another
    population (§15.2). By the samples of the committed index (§20.2, D71), it never mixes the two samples, and the run
    ``run_id`` (one of :data:`NATURAL_RUN_SAMPLES`) grades every accepted family of its sample and no family of the other.
    A row of the index that names neither sample fails: nothing shows which run grades it. A given task without a row is
    reported by :func:`natural_record_problems`."""
    others = [tid for tid, natural in given if not natural]
    out = []
    if others:
        out.append(f"natural: the run mixes natural:pr-review tasks with tasks of other populations ({', '.join(others)}); "
                   "each population gets its own run (protocol §15.2)")
    if index is None:
        return out
    rows = index_rows(index)
    unknown = [tid for tid, r in rows.items() if row_sample(r) is None]
    if unknown:
        out.append(f"natural: {len(unknown)} {_plural(len(unknown), 'row', 'rows')} of the committed index ({_ids(unknown)}) "
                   f"{_plural(len(unknown), 'names', 'name')} neither sample ('first' or 'extension'), so nothing shows "
                   f"which run grades {_plural(len(unknown), 'it', 'them')} ({TWO_RUNS})")
    natural = list(dict.fromkeys(tid for tid, is_natural in given if is_natural))
    by_sample: dict[str, list[str]] = {}
    for tid in natural:
        s = row_sample(rows.get(tid, {}))
        if s is not None:
            by_sample.setdefault(s, []).append(tid)
    sample = NATURAL_RUN_SAMPLES.get(run_id or "")
    if sample is None:  # the run id is refused (natural_run_id_problems); the samples must not be mixed all the same
        if len(by_sample) > 1:
            shown = "; ".join(f"{s}: {_ids(by_sample[s])}" for s in S9_SAMPLE_SIZES if s in by_sample)
            out.append(f"natural: the run mixes the two samples ({shown}); {TWO_RUNS}")
        return out
    other = [tid for s, tids in by_sample.items() if s != sample for tid in tids]
    if other:
        other_sample = next(s for s in S9_SAMPLE_SIZES if s != sample)
        other_run = next(r for r, s in NATURAL_RUN_SAMPLES.items() if s == other_sample)
        mixes = "mixes the two samples: it " if by_sample.get(sample) else ""
        out.append(f"natural: the run {run_id} {mixes}includes families of {SAMPLE_NAMES[other_sample]} ({_ids(other)}), "
                   f"but it grades the accepted families of {SAMPLE_NAMES[sample]} only, and {other_run} those of "
                   f"{SAMPLE_NAMES[other_sample]} (protocol §20.2)")
    accepted = [tid for tid, r in rows.items() if r.get("s11") is True and row_sample(r) == sample]
    left_out = sorted(set(accepted) - set(natural), key=_task_order)
    if left_out:
        out.append(f"natural: the run leaves out accepted families of {SAMPLE_NAMES[sample]} in the committed index "
                   f"({', '.join(left_out)}); the run {run_id} grades every accepted family of {SAMPLE_NAMES[sample]} "
                   "(protocol §20.2)")
    return out


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

    tasks = list(map(Path, a.tasks))
    # A run with a natural PR-review task: the committed index, read once (protocol §16.4, §19.5, §20.2).
    natural_run = any(roots.is_natural_pr(td) for td in tasks)
    index, index_why = committed_index(R) if natural_run else (None, None)
    given: list[tuple[str, bool]] = []  # each task id, and whether it is a natural PR-review task
    for td in tasks:
        m = load(td / "task.json", TaskManifest)
        natural = m.population == Population.natural_pr_review
        given.append((m.task_id, natural))
        specs = [load(td / p, VerifierSpec) for p in m.verifiers]
        extras, extra_problems = (extra_verifier_problems(td, m, specs, a.conditions, with_strata=bool(names))
                                  if a.with_extra_verifiers else ([], []))
        # A natural family's verifiers, where each is registered: task.json and the sidecar (read whatever the options).
        side = sidecar_specs(td, m) if natural else []
        labeler_round: int | None = None
        if natural:
            graded = graded_verifiers([*specs, *extras], a.conditions)
            if not a.with_extra_verifiers and not any(s.verifier_id == INDEPENDENT_LABELER for s in specs):
                problems.append(f"{m.task_id}: a natural PR-review run grades the family's independent labeler "
                                f"({INDEPENDENT_LABELER}, registered in {EXTRA_VERIFIERS}); pass --with-extra-verifiers here "
                                "and to evaluate (protocol §15.5, §15.6)")
            elif not names and not any(s.verifier_id == INDEPENDENT_LABELER for s in graded):
                problems.append(f"{m.task_id}: the run grades no independent labeler (verifier {INDEPENDENT_LABELER} of "
                                f"{EXTRA_VERIFIERS}, condition {LABEL_SUPPORT_CONDITION!r}); its verdicts are the second "
                                "labeling of a natural PR-review family (protocol §15.5, §15.6)")
            labelers = [(rel, s) for rel, s in [*zip(m.verifiers, specs), *side] if s.verifier_id == INDEPENDENT_LABELER]
            if labelers:
                status = labeler_status(td, labelers[0][0])
                labeler_round = status.round
                if status.problem is not None:
                    problems.append(f"{m.task_id}: the independent labeler: {status.problem}")
                elif not status.usable:
                    note(f"{m.task_id}: the independent labeler is not usable for this family ({status.said}); the second "
                         "labeling leaves it out (protocol §15.5)")
        missing_conditions = sorted(set(a.conditions or []) - {s.condition.value for s in [*specs, *extras]})
        if natural:  # B1 or B3 that the family's records show unavailable is a note (§17.2), not a missing condition
            for cond, msg in unavailable_baselines(td, m, missing_conditions):
                missing_conditions.remove(cond)
                note(msg)
        if missing_conditions:
            problems.append(f"{m.task_id}: no verifier for condition(s) {missing_conditions}")
        problems += [f"{m.task_id}: reconstruction: {p}" for p in recorded_check(td, R).problems]
        problems += gate_problems(td, m, pilot=a.pilot)
        if natural:
            problems += natural_record_problems(td, m, index)
        for s in specs:
            if not s.frozen:
                selection = b3_unavailable(td) if natural and s.condition.value == B3 else None
                hint = ("" if selection is None else f"; its test selection kept no test ({selection}, b3_available false), "
                        "so B3 is unavailable and this verifier must be kept out of the run (scripts/select_b3_tests.py)")
                problems.append(f"{m.task_id}: verifier {s.verifier_id} not frozen{hint}")
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
        if natural:
            pool = natural_pool_problem(m, held)
            if pool is not None:
                pool_problem(pool)
        elif by_origin[CandidateOrigin.observed_pre_correction] != 1 or by_origin[CandidateOrigin.valid_alternative] != 2 \
                or by_origin[CandidateOrigin.constructed_near_miss] != 5:
            pool_problem(f"{m.task_id}: incomplete held-out pool {({k.value: v for k, v in by_origin.items() if v})}")
        for c in held:
            if not has_d19_proposal(c):
                pool_problem(f"{m.task_id}: {c.candidate_id} has no D19 proposal")
        if natural:  # the pool's labels, its near misses' targets and its freezing order (§15.5, §15.6, §19.7)
            for p in [*source_evidence_problems(m, held), *near_miss_problems(td, m, held),
                      *frozen_before_pool_problems(m, [*(("task.json", s) for s in specs),
                                                       *((EXTRA_VERIFIERS, s) for _, s in side)], held)]:
                pool_problem(p)
        from tracecontract.tasks import verify_snapshot

        try:  # where the task's base snapshot lives: snapshots/ for a controlled task, data/natural/snapshots for a natural one
            snapshots: Path | None = roots.snapshot_root(td, repo=R)
        except roots.RootError as exc:
            snapshots = None
            problems.append(f"{m.task_id}: base snapshot: its recorded snapshot root is unusable ({exc})")
        if snapshots is None:
            pass
        elif not (snapshots / m.task_id).is_dir():
            if natural:
                where = snapshots / m.task_id
                shown = where.relative_to(R).as_posix() if where.is_relative_to(R) else str(where)
                problems.append(f"{m.task_id}: base snapshot not built ({shown} does not exist; the S10 build writes a natural "
                                "PR-review task's base, natural_pr.compile_pr_task, not `tracecontract snapshot`)")
            else:
                problems.append(f"{m.task_id}: base snapshot not built (run `tracecontract snapshot tasks/{m.task_id}`)")
        elif not verify_snapshot(td, snapshots):
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
        if snapshots is not None and (snapshots / m.task_id).is_dir():
            from tracecontract.duplicates import same_code_duplicates

            rec = same_code_duplicates(td, snapshots)
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
            if natural:  # natural-agent:v1 flags tool inputs (hits) and tool outputs (exposures); each is assessed
                for p in natural_audit_entry_problems(m.task_id, ws, rec):
                    audit_problem(p)
                if not isinstance(rec, dict):
                    continue
            elif rec.get("hits") and not rec.get("assessment"):
                audit_problem(f"{m.task_id}: generator audit {ws} has unassessed hits")
            strict = rec.get("strict_reaudit")
            if not strict:
                audit_problem(f"{m.task_id}: generator audit {ws} has no strict re-audit (scripts/strict_reaudit.py, D44)")
            elif not strict.get("assessment") or any("error" in t for t in strict.get("transcripts", {}).values()):
                audit_problem(f"{m.task_id}: strict re-audit of {ws} is unassessed or lacks a transcript")
        if natural:  # an audit of every agent of the natural recipe (D64); those of the pool generators are pool problems
            missing = natural_audits_missing(set(audit) - {"_rules"}, [*specs, *(s for _, s in side)], labeler_round)
            pool_roles = set(NATURAL_AUDIT_ROLES["pool generators"])
            own = [ws for ws in missing if ws not in pool_roles and not generates_held_out(ws, m.task_id, held)]
            if own:
                problems.append(f"{m.task_id}: generator audits missing for {own}")
            if len(own) < len(missing):
                pool_problem(f"{m.task_id}: generator audits missing for {[ws for ws in missing if ws not in own]}")
        else:
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
    if natural_run:  # the run as a whole (§20.2, D71): one of the two runs, of every accepted family of its sample only,
        # once building has stopped for that sample (for a run id that names neither run: §19.5 over both samples)
        problems += building_problems(index, index_why, NATURAL_RUN_SAMPLES.get(a.run_id or ""))
        problems += natural_run_problems(given, index, a.run_id)
        problems += natural_run_id_problems(a.run_id)
    from tracecontract.sandbox.docker_runner import HARNESS_VERSION

    # The run id is new under the repository's results/runs and data/natural/runs (R: where every other check looks too).
    problems += run_problems(repeats=a.repeats, harness=HARNESS_VERSION, run_id=a.run_id, runs_root=R / "results" / "runs",
                             natural_runs_root=R / NATURAL_RUNS_REL)
    running = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True, check=False).stdout.split()
    if running:
        problems.append(f"{len(running)} container(s) running; a run needs an idle host")
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=R, capture_output=True, text=True,
                           check=False).stdout.strip()
    if dirty:
        problems.append("git working tree not clean")
    for p in problems:
        print("FAIL:", p)
    print("preflight:", "ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
