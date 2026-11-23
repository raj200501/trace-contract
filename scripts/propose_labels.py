"""Propose labels for evaluation candidates (automated pilot only).

For each evaluation candidate of a task, or with ``--stratum NAME`` of one of its candidate
strata (``tasks/<id>/strata/<name>.json``):

1. grade it with the independent ``reference_check`` verifier (written from the
   reference contract, validated only on the reference solution and the no-op);
2. run the base repository's own tests (regression norm): a test that passes on the
   reference but fails on the candidate is a regression;
3. combine with the construction intent recorded when the candidate was built.

Decision rule (pre-specified, docs/decision_log.md D19; :func:`d19`):
* construction says valid  + reference checks pass + no regression   -> valid
* construction says invalid + reference checks fail a check mapped to a
  violated requirement (a failing regression check alone is not enough) -> invalid
* natural candidates (no construction label, or an origin in ``schemas.NATURAL_ORIGINS``:
  observed states, fresh attempts and natural pre-review states, which are never labeled by
  construction intent; protocol v0.7 §15.4, v0.8 §16.3): invalid if any reference check or
  regression fails (violated = requirements of failing checks), else valid. A natural
  pre-review state that passes the reference checks is ambiguous instead: the correction is
  not observable by the checks (protocol §15.6)
* any disagreement                                                    -> ambiguous
  (excluded from FA/FR, queued for human review)
* a missing decision                                                  -> ambiguous
  (the reference checks give no outcome but pass or task failure; or the regression norm
  gives none and names no failing check, e.g. a timeout of the repository tests, while
  the reference checks pass: "no regression" is then not known)

Repeats (``--repeats N``; :func:`combine_repeats`): the reference checks and the regression
norm are graded N times, each time as a single grade, and the rule above is applied to each
repeat. Repeats whose proposals differ are a missing decision, so the label is ambiguous. Two
proposals are the same when their value, violated requirements and reason are; for one
candidate, two proposals with the same value and violated requirements differ in their reason
only when both are ambiguous, so the label is the one a comparison of the labels alone would
give, and only the reason recorded for it differs. The regression norm's checks are then the
base tests that pass on the reference in each of N runs. N is 1 by default, which is the rule
as the pilot and fresh-v1 used it; a natural PR-review task is graded 3 times (D64), its
default and the only value accepted for it.

The reference checks must be the frozen ones: a frozen spec whose test files or check list
changed since it was frozen is refused before anything is graded or written. The base
snapshot is ``<root>/<task id>`` (the task id of ``task.json``), under the root that
``roots.snapshot_root`` names for the task: ``snapshots/``, or ``data/natural/snapshots/``
for a natural PR-review task.

Proposed labels are appended with ``labeler_kind = model``; they never replace or
hide human labels, and nothing here writes ``task.json``. A task's own candidates get
their labels in their files under ``candidates/`` and the log in
``labels/proposed_labels.json``; the base test paths rebuild ``labels/base_tests_overlay``.
A stratum's candidates get their labels in their files under
``strata/<name>/candidates/`` and the log in ``strata/<name>/proposed_labels.json``; their
regression norm is the task's recorded overlay, read and never rewritten, so base test
paths are refused with ``--stratum`` and nothing under ``labels/`` is written.

Every label is computed before any file is written, the overlay included: the base test
paths' overlay is built in a private scratch directory outside the task, the reference and
the candidates are graded with it there, and it replaces ``labels/base_tests_overlay`` only
once every label is known. A refusal on the way (the reference patch cannot be staged, the
base tests do not complete on the reference) therefore leaves the task as it was. No label,
log or overlay is written through a symbolic link (``labels/``, the log, the overlay).

A natural PR-review task (population ``natural:pr-review``; protocol §15.6, §17.2, §19.7, §20.2):

* D19 is the first step of the run of the task's sample (decision log D73): no natural verifier
  is graded on a held-out candidate of a family before that family's run (§20.2), and the run
  grades the family with every other accepted family of its sample. So D19 for ``natural-pr-v1``
  runs once building has stopped for the first sample and each of its accepted families has ended
  its seven phases (D73): every verifier, contract and candidate of the run is then frozen or
  registered, and no D19 grade can change any of them. A task is refused before anything is
  looked up, graded or written unless all of these hold, by records as the HEAD commit holds
  them, checked with the pre-flight's own functions (``scripts/preflight_final_run.py``), so that
  the gate and the pre-flight's check of the run cannot disagree on those records
  (:func:`building_problem`):
  * building has stopped for the task's own sample, the per-sample rule of §20.2 that D73 applies
    to D19: the task's row in the committed natural index (``committed_index``, ``index_rows``)
    names its sample (``row_sample``: ``first`` for ``natural-pr-v1``, ``extension`` for
    ``natural-pr-v2``), and ``building_problems`` finds nothing for that sample. So the first
    sample's families are labelled once building has stopped for the first sample, whatever the
    extension's state. A task with no row in the committed index, or whose row names neither
    sample, is refused;
  * every row of the committed index names a sample (``sample_problems``), as a natural run
    requires: nothing shows which run grades a row that names neither;
  * the committed phase-end log (``data/manifests/natural_phase_ends.jsonl``, to which
    ``scripts/record_phase_end.py`` appends a line at each phase end, and whose commits are the
    order record of D65) holds the lines of the phases P1 to P7, in order, of the task and of
    every accepted family of its sample (``accepted_families``, ``phase_end_problems``; D73). The
    order of the lines and their times are checked in the log as HEAD holds it; the order of the
    commits that added them stays the builder's record. A log that git does not give, or that
    holds a line that is not a phase-end record, refuses every task;
* its reference checks must be frozen, with the time of freezing and the hash of the scored
  check list recorded (``tracecontract freeze``), so that the labels are tied to the version
  frozen before the pool (§19.7); a controlled task's unfrozen reference checks are graded
  as before (all four CS tasks' are frozen);
* its regression norm is the base-test subset that S10 fixed, ``s10.json``
  ``base_tests.subset``: the default base test paths, and the only set accepted;
* its base snapshot must match ``snapshot.json``, and its image is only looked up, never
  built, with the id that ``snapshot.json`` records (``evaluate.find_image``); both are
  checked before anything is written;
* it has no candidate strata;
* ``labels/proposed_labels.json`` also records the base test paths and where they come from,
  the overlay's manifest hash (``snapshot.manifest_sha256``, as the natural index summarises
  ``labels/base_tests_overlay/``) and file count, the repeats, the frozen reference checks'
  hashes, the base snapshot's manifest hash and the image.

Usage: python scripts/propose_labels.py tasks/CS-01 [base test paths...]
       python scripts/propose_labels.py tasks/CS-01 --stratum fresh-v1
       python scripts/propose_labels.py data/natural/tasks/NP-03
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tracecontract import roots
from tracecontract.cli import CACHE
from tracecontract.sandbox.docker_runner import build_env_image, prepare_workspace, run_grader, verify_candidate
from tracecontract.schemas import (
    NATURAL_ORIGINS, Candidate, CandidateOrigin, CheckSpec, Isolation, Label, LabelerKind, Outcome, Population, Snapshot,
    Split, TaskManifest, VerificationResult, VerifierCondition, VerifierSpec,
)
from tracecontract.snapshot import manifest, manifest_sha256
from tracecontract.store import dump, load, write_json
from tracecontract.strata import load_stratum
from tracecontract.tasks import verify_snapshot
from tracecontract.verifier import check_frozen

LABELER = "builder:refcheck+regression+construction:v1"
NATURAL_REPEATS = 3  # D64: D19 grades a natural family's reference checks and regression norm three times (§15.3)
NATURAL_NORM_SOURCE = "s10.json base_tests.subset (protocol §17.2)"
OVERLAY = "labels/base_tests_overlay"
# The repository under which roots.snapshot_root resolves a task's recorded snapshot root, and whose HEAD commit holds the
# natural index and the phase-end log that show whether D19 may run on a natural task.
REPO = roots.REPO
# The pre-flight: its rules for when D19 may run on a natural task (building has stopped for the task's sample, and the
# committed phase-end log holds the phases P1 to P7 of every family of its run; protocol §20.2, decision log D73).
PREFLIGHT = Path(__file__).resolve().parent / "preflight_final_run.py"
_LISTED = 20  # failing checks listed per candidate (and per repeat) in the log and the label note


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def refuse(why: str) -> SystemExit:
    return SystemExit(f"propose_labels refused, nothing written: {why}")


def repeats_for(m: TaskManifest, repeats: int | None) -> int:
    """The number of repeats: 1 by default, 3 for a natural PR-review task (D64), which accepts no other value."""
    natural = m.population == Population.natural_pr_review
    if repeats is None:
        return NATURAL_REPEATS if natural else 1
    if repeats < 1:
        raise refuse(f"--repeats must be at least 1 (got {repeats})")
    if natural and repeats != NATURAL_REPEATS:
        raise refuse(f"{m.task_id} is a natural PR-review task: D19 grades it {NATURAL_REPEATS} times (D64), not {repeats}")
    return repeats


def _preflight() -> Any:
    """The pre-flight (:data:`PREFLIGHT`), loaded as a module."""
    spec = importlib.util.spec_from_file_location("tracecontract_preflight_final_run", PREFLIGHT)
    if spec is None or spec.loader is None:
        raise ImportError(f"no module at {PREFLIGHT}")
    preflight = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preflight)
    return preflight


def building_problem(repo: Path, task_id: str) -> str | None:
    """Why D19 may not run yet on the natural PR-review task ``task_id``, or None (the caller names the task). D19 grades
    the frozen reference checks on the family's held-out candidates, and no natural verifier is graded on a held-out
    candidate of a family before that family's run (protocol §20.2). The run of the family's sample grades it with every
    other accepted family of that sample, and D19 is that run's first step (decision log D73): D19 for ``natural-pr-v1``
    runs once building has stopped for the first sample and each of its accepted families has ended its seven phases, so
    that every verifier, contract and candidate of the run is frozen or registered by then, and no D19 grade can change
    any of them. By records as the HEAD commit of ``repo`` holds them, D19 needs:

    * building has stopped for the family's own sample (the rule of §20.2 for that sample, which D73 applies to D19):
      the family's row in the committed natural index (``committed_index``, ``index_rows``) names its sample
      (``row_sample``: ``first``, graded in ``natural-pr-v1``, or ``extension``, in ``natural-pr-v2``), and
      ``building_problems`` finds nothing for that sample. The rule for both samples together (§19.5, §19.7) would refuse
      the first sample's families until the extension is built. A task with no row in the committed index, or whose row
      names neither sample, is refused, since nothing then shows which run grades it;
    * the family is accepted (its row has ``s11`` true, §16.4): no run grades another, so D19 would be no run's step;
    * every row of the committed index names a sample (``sample_problems``): a row that names neither could be an
      accepted family of the task's sample that the run must grade, whose phase ends D19 would then not ask for;
    * the committed phase-end log holds the lines of the phases P1 to P7, in order, of the family and of every accepted
      family of its sample (``accepted_families``, the families that the run grades with it; ``phase_end_problems``;
      decision log D65, D73).

    These are the checks of the pre-flight's natural run (:data:`PREFLIGHT`) that the committed records decide, applied
    with its own functions to the run of the task's sample, so that the gate and the pre-flight cannot disagree on those
    records. If they cannot be applied, nothing shows that D19 may run, and the answer is a refusal."""
    try:
        preflight = _preflight()
        index, why = preflight.committed_index(repo)
        at = f"the committed index ({preflight.NATURAL_INDEX} in the HEAD commit)"
        run, families = None, [task_id]  # the run of the task's sample, once known, and whose phase ends D19 needs
        if index is None:  # it cannot be read: the pre-flight's reason, which needs no sample
            problems = preflight.building_problems(index, why)
        elif (row := preflight.index_rows(index).get(task_id)) is None:
            problems = [(f"{at} has no row for it, so nothing shows its sample, which run grades it, or whether building has "
                         "stopped for that sample (protocol §20.2; decision log D73)")]
        elif (sample := preflight.row_sample(row)) is None:
            said = f"its sample is {json.dumps(row['sample'])}" if "sample" in row else "it records no sample"
            problems = [(f"its row in {at} names neither sample ({said}; the samples are 'first' and 'extension'), so "
                         "nothing shows which run grades it, or whether building has stopped for its sample (protocol "
                         "§20.2; decision log D73)")]
        else:
            problems = [*preflight.building_problems(index, why, sample), *preflight.sample_problems(index)]
            if row.get("s11") is not True:  # no run grades a family that is not accepted
                problems.append(f"it is not S11 in {at}: a run grades only accepted families, so D19 has no run to be "
                                "the first step of (protocol §16.4, §20.2; decision log D73)")
            run = next(r for r, s in preflight.NATURAL_RUN_SAMPLES.items() if s == sample)
            families += preflight.accepted_families(index, sample)
        for p in preflight.phase_end_problems(repo, families):
            tid, _, rest = p.partition(": ")
            if tid == task_id:  # the caller names the task
                problems.append(rest)
            elif tid in families:  # another family of the task's run
                problems.append(f"{tid}, which {run} grades with it (D19 is the first step of that run, decision log D73): "
                                f"{rest}")
            else:  # a log that cannot be used: one problem for all the families
                problems.append(p)
    except Exception as exc:  # noqa: BLE001 - fail closed: rules that cannot be applied show nothing
        return (f"the pre-flight's rules for when D19 may run ({PREFLIGHT.name}: building has stopped for the task's sample, "
                "and the committed phase-end log holds the phases P1 to P7 of every family of its run) could not be applied "
                f"({type(exc).__name__}: {exc}), so nothing shows that D19 may run (protocol §20.2; decision log D65, D73)")
    return "; ".join(problems) or None


def frozen_problem(spec: VerifierSpec) -> str | None:
    """Why ``spec`` is not a frozen verifier that D19 can tie a natural task's labels to, or None: it must be frozen, with
    the time of freezing and the hash of its scored check list recorded (``verifier.freeze``)."""
    if spec.frozen and spec.frozen_at and spec.checks_sha256:
        return None
    return (f"the reference checks ({spec.verifier_id}) are not frozen (frozen: {spec.frozen}, frozen_at: {spec.frozen_at}, "
            f"checks_sha256: {spec.checks_sha256}); D19 grades a natural PR-review task's frozen reference checks only, so "
            "that its labels are tied to the version frozen before its pool (protocol §19.7; `tracecontract freeze <task> "
            "reference_check`)")


def linked(tdir: Path, *paths: Path) -> Path | None:
    """The first of ``paths`` (inside the task directory ``tdir``), or of the directories between ``tdir`` and it, that is
    a symbolic link; None if none is. Nothing is written through a link (it could lead into a tracked directory)."""
    for path in paths:
        rel = path.relative_to(tdir)
        for i in range(1, len(rel.parts) + 1):
            p = tdir.joinpath(*rel.parts[:i])
            if p.is_symlink():
                return p
    return None


def natural_base_tests(tdir: Path, m: TaskManifest, given: tuple[str, ...]) -> list[str]:
    """A natural PR-review task's regression norm: ``s10.json`` ``base_tests.subset``, in its recorded order.

    ``given`` (base test paths from the command line) must be that set, or empty; any other set is refused (§17.2:
    the subset is fixed from the base tree before any verifier exists, and B1 is built from the same subset).
    """
    try:
        s10 = json.loads((tdir / "s10.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s10 = None
    subset = ((s10 or {}).get("base_tests") or {}).get("subset") if isinstance(s10, dict) else None
    if not isinstance(subset, list) or not subset or not all(isinstance(p, str) and p for p in subset):
        raise refuse(f"{m.task_id}: s10.json records no base-test subset (base_tests.subset); the regression norm of a "
                     "natural PR-review task is that subset (§17.2)")
    if given and set(given) != set(subset):
        extra, missing = sorted(set(given) - set(subset)), sorted(set(subset) - set(given))
        raise refuse(f"{m.task_id} is a natural PR-review task: its regression norm is {NATURAL_NORM_SOURCE}; other base "
                     f"test paths are refused (not in the subset: {extra}; in the subset but not given: {missing})")
    return list(dict.fromkeys(subset))


def check_base_test_paths(base: Path, paths: tuple[str, ...]) -> None:
    """Each base test path is a relative path inside the base snapshot that exists there (checked before the overlay is
    rebuilt, so a bad path leaves it as it was)."""
    for tp in paths:
        p = Path(tp)
        if p.is_absolute() or ".." in p.parts or not p.parts:
            raise refuse(f"base test path {tp!r} must be a relative path inside the base snapshot")
        if not (base / p).exists():
            raise refuse(f"base test path {tp!r} does not exist in the base snapshot {base}")


def build_overlay(base: Path, overlay: Path, paths: tuple[str, ...]) -> None:
    """The base commit's copies of the base test paths, under ``overlay`` (a new directory; none without paths)."""
    for tp in paths:
        src, dst = base / tp, overlay / tp
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)


def install_overlay(staged: Path, overlay: Path) -> None:
    """Replace the task's overlay (``labels/base_tests_overlay``) by ``staged``, the overlay the labels were computed with:
    its files are copied as they are. Without base test paths nothing was staged, and the task keeps no overlay."""
    if overlay.is_dir():
        shutil.rmtree(overlay)
    elif overlay.exists():
        overlay.unlink()
    if staged.is_dir():
        shutil.copytree(staged, overlay)


def overlay_record(overlay: Path) -> dict[str, Any]:
    """The overlay's manifest hash and file count (``snapshot.manifest``: each file's path in the overlay and sha256)."""
    entries = manifest(overlay)
    return {"overlay_manifest_sha256": manifest_sha256(entries), "overlay_n_files": len(entries)}


def task_base(tdir: Path, m: TaskManifest) -> Path:
    """The task's base snapshot directory: ``<root>/<task id>``, the task id of ``task.json`` (the directory that
    ``tasks.verify_snapshot`` checks), under the root ``roots.snapshot_root`` names for the task (under :data:`REPO`)."""
    try:
        return roots.snapshot_root(tdir, repo=REPO) / m.task_id
    except roots.RootError as exc:
        raise refuse(str(exc)) from None


def task_image(tdir: Path, m: TaskManifest) -> tuple[str, str | None]:
    """``(tag, id)`` of the image the task is graded in. A natural PR-review task's image is only looked up, never built,
    and must have the id ``snapshot.json`` records (``evaluate.find_image``); any other task's image is built when it is
    missing (``build_env_image``), as before."""
    if m.population != Population.natural_pr_review:
        return build_env_image(m.env_requirements, CACHE / "images")
    from tracecontract import evaluate

    snap = load(tdir / (m.snapshot or "snapshot.json"), Snapshot)
    try:
        return evaluate.find_image(m, snap, CACHE / "images")
    except evaluate.RunRefused as exc:
        raise refuse(str(exc)) from None


def regression_spec(root: Path, m: TaskManifest, tag: str, ref: Candidate, *, base: Path,
                    repeats: int = 1) -> tuple[VerifierSpec, dict[str, Any]]:
    """In-process spec over the BASE repository tests of the overlay ``root / OVERLAY`` that pass on the reference, in
    each of ``repeats`` runs; and its record for the log (the runs, the checks, and the tests that passed in some run but
    not in all). The spec's test directory is :data:`OVERLAY`, relative to ``root``: the task directory for the recorded
    overlay of a stratum, the scratch directory for an overlay built from base test paths."""
    overlay = root / OVERLAY
    runs: list[set[str]] = []
    for i in range(repeats):
        ws, diags, _ = prepare_workspace(base, ref.patch)
        if ws is None:
            raise refuse(f"the reference patch could not be staged on the base snapshot: {diags}")
        try:
            raw, nonce = run_grader(tag, workspace=ws, mode=Isolation.in_process, overlay_dir=overlay,
                                    repo_test_args=m.repo_test_args, candidate_pythonpath=m.candidate_pythonpath)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        r = raw.results or {}
        if r.get("nonce") != nonce or r.get("status") != "completed" or r.get("timed_out") or getattr(raw, "timed_out", False):
            raise refuse(f"the base tests did not complete on the reference (run {i + 1} of {repeats}: status "
                         f"{r.get('status')!r}{', timed out' if r.get('timed_out') or getattr(raw, 'timed_out', False) else ''})")
        runs.append({t["nodeid"] for t in r.get("tests", []) if t["outcome"] == "passed"})
    passing = sorted(set.intersection(*runs))
    unstable = sorted(set.union(*runs) - set(passing))
    spec = VerifierSpec(verifier_id="regression_norm", task_id=m.task_id, condition=VerifierCondition.reference_check,
                        isolation=Isolation.in_process, test_dir=OVERLAY, checks=[CheckSpec(check_id=c) for c in passing],
                        content_sha256="base-tests")
    return spec, {"reference_runs": repeats, "n_checks": len(passing), "n_not_passing_in_every_reference_run": len(unstable),
                  "not_passing_in_every_reference_run": unstable[:_LISTED]}


def d19(origin: CandidateOrigin, construction: Label | None, *, infra: bool, rc_ok: bool, violated_rc: list[str],
        reg_fail: list[str], reg_infra: bool = False) -> tuple[str, list[str], str]:
    """D19's proposal for one candidate: ``(value, violated requirements, why)`` (rule in the module docstring).

    ``infra``: the reference checks gave no decision; ``rc_ok``: they all passed; ``violated_rc``: the
    requirements of the failing reference checks; ``reg_fail``: the failing regression-norm checks;
    ``reg_infra``: the regression norm gave no decision (no pass, no task failure) and names no failing
    check, so whether a regression holds is not known. A missing decision makes the label ambiguous
    wherever it is needed: a candidate whose reference checks fail is invalid without it.
    """
    regression = ["REGRESSION"] if reg_fail else []
    if infra:
        return "ambiguous", [], "reference checks did not produce a decision"
    undecided = rc_ok and reg_infra and not reg_fail  # "no regression" would be needed, and is not known
    if construction is None or origin in NATURAL_ORIGINS:  # a natural candidate: never by construction intent
        if rc_ok and origin == CandidateOrigin.natural_pre_review:
            return ("ambiguous", regression, "natural pre-review state passes the reference checks: the correction is not "
                    "observable by the checks")
        if undecided:
            return "ambiguous", [], "natural candidate passes reference checks; the regression norm did not produce a decision"
        if rc_ok and not reg_fail:
            return "valid", [], "natural candidate passes reference checks and regression norm"
        return "invalid", violated_rc + regression, "natural candidate fails reference checks and/or regression norm"
    if construction.value == "valid":
        if undecided:
            return "ambiguous", [], "construction valid, reference checks pass; the regression norm did not produce a decision"
        if rc_ok and not reg_fail:
            return "valid", [], "construction valid, confirmed by reference checks and regression norm"
        return "ambiguous", violated_rc + regression, "construction valid but checks fail"
    target = set(construction.violated_requirements)
    hit = bool(target & set(violated_rc)) or (bool(reg_fail) and "REGRESSION" in target)
    if not rc_ok and hit:
        return "invalid", sorted(target | set(violated_rc)), "construction invalid, confirmed on targeted requirement"
    if not rc_ok or reg_fail:
        return "ambiguous", violated_rc + regression, "construction invalid but failing checks map to other requirements"
    if undecided:
        return "ambiguous", [], "construction invalid, reference checks pass; the regression norm did not produce a decision"
    return "ambiguous", [], "construction invalid but reference checks and regression norm pass"


def combine_repeats(proposals: list[tuple[str, list[str], str]]) -> tuple[str, list[str], str]:
    """D19 over repeated gradings (D64): the repeats' proposal when every repeat gives the same one (value, violated
    requirements and reason), else a missing decision, so ambiguous. One repeat is D19 as it was."""
    first = proposals[0]
    if all(p == first for p in proposals[1:]):
        return first
    given = "; ".join(f"{value} {violated}" for value, violated, _ in proposals)
    return "ambiguous", [], f"the {len(proposals)} repeats give different proposals ({given}): a missing decision"


def one_repeat(rc: VerificationResult, rr: VerificationResult | None, req_of: dict[str, list[str]]) -> dict[str, Any]:
    """One repeat's outcomes, failing checks and D19 inputs (``inputs``: the keyword arguments of :func:`d19`)."""
    failed_rc = [k.check_id for k in rc.checks if k.status != "passed"]
    if rr is not None:
        reg_fail = [k.check_id for k in rr.checks if k.status != "passed"]
        reg_outcome = rr.outcome.value
        # No decision: e.g. a timeout or an environment failure, which records no check at all.
        reg_infra = rr.outcome not in (Outcome.passed, Outcome.task_failure) and not reg_fail
    else:
        reg_fail, reg_outcome, reg_infra = [], "not run", False
    inputs = {"infra": rc.outcome not in (Outcome.passed, Outcome.task_failure), "rc_ok": rc.outcome == Outcome.passed,
              "violated_rc": sorted({r for f in failed_rc for r in req_of.get(f, [])}), "reg_fail": reg_fail,
              "reg_infra": reg_infra}
    return {"refcheck_outcome": rc.outcome.value, "refcheck_failed": failed_rc, "regression_outcome": reg_outcome,
            "regression_failed": reg_fail, "inputs": inputs}


def _common(values: list[str]) -> str:
    """The outcome every repeat gave, else ``unresolved`` (as ``verify_candidate`` names repeats that disagree)."""
    return values[0] if len(set(values)) == 1 else Outcome.unresolved.value


def _union(lists: list[list[str]]) -> list[str]:
    return list(dict.fromkeys(x for lst in lists for x in lst))


def label_candidates(cands: dict[str, tuple[str, Candidate]], *, m: TaskManifest, tdir: Path, base: Path, tag: str,
                     refcheck: VerifierSpec, reg_spec: VerifierSpec | None, reg_root: Path, repeats: int
                     ) -> tuple[dict[str, Any], list[tuple[str, Candidate]]]:
    """D19 for each held-out candidate of ``cands`` (the no-op left out): ``repeats`` single grades of the reference checks
    and of the regression norm (``reg_spec``, whose overlay lies under ``reg_root``), :func:`d19` on each, and
    :func:`combine_repeats`. Returns the log's candidate entries and the candidate records to write; nothing is written."""
    req_of = {c.check_id: c.requirement_ids for c in refcheck.checks}
    entries: dict[str, Any] = {}
    writes: list[tuple[str, Candidate]] = []
    for cid, (rel, c) in sorted(cands.items()):
        if c.split != Split.eval or c.origin == CandidateOrigin.noop:
            continue
        runs = []
        for _ in range(repeats):
            rc = verify_candidate(image=tag, base_dir=base, spec=refcheck, task_dir=tdir, candidate=c, run_id="labels",
                                  candidate_pythonpath=m.candidate_pythonpath)
            rr = verify_candidate(image=tag, base_dir=base, spec=reg_spec, task_dir=reg_root, candidate=c, run_id="labels",
                                  candidate_pythonpath=m.candidate_pythonpath,
                                  repo_test_args=m.repo_test_args) if reg_spec is not None else None
            runs.append(one_repeat(rc, rr, req_of))
        construction = next((lb for lb in c.labels if lb.labeler_kind == LabelerKind.construction), None)
        proposals = [d19(c.origin, construction, **r["inputs"]) for r in runs]
        value, violated, why = combine_repeats(proposals)
        note: dict[str, Any] = {
            "refcheck_outcome": _common([r["refcheck_outcome"] for r in runs]),
            "refcheck_failed": _union([r["refcheck_failed"] for r in runs])[:_LISTED],
            "regression_outcome": _common([r["regression_outcome"] for r in runs]),
            "regression_failed": _union([r["regression_failed"] for r in runs])[:_LISTED]}
        entry: dict[str, Any] = {}
        if repeats > 1:
            note.update(repeats=repeats, repeats_agree=len({json.dumps(p) for p in proposals}) == 1)
            entry["repeat_results"] = [{"refcheck_outcome": r["refcheck_outcome"], "refcheck_failed": r["refcheck_failed"][:_LISTED],
                                        "regression_outcome": r["regression_outcome"],
                                        "regression_failed": r["regression_failed"][:_LISTED], "proposed": p[0], "violated": p[1],
                                        "why": p[2]} for r, p in zip(runs, proposals, strict=True)]
        note["construction"] = construction.model_dump(mode="json") if construction else None
        lab = Label(value=value, violated_requirements=violated, labeler=LABELER, labeler_kind=LabelerKind.model,
                    timestamp=now(), note=why + " | " + json.dumps(note)[:3000])
        writes.append((rel, c.model_copy(update={"labels": [lb for lb in c.labels if lb.labeler != LABELER] + [lab]})))
        entries[cid] = {"origin": c.origin.value, "proposed": value, "violated": violated, "why": why, **note, **entry}
        print(f"{cid:38s} {c.origin.value:24s} -> {value:9s} {violated} ({why})")
    return entries, writes


def main(task_dir: str, *base_test_paths: str, stratum: str | None = None, repeats: int | None = None) -> None:
    tdir = Path(task_dir).resolve()
    m = load(tdir / "task.json", TaskManifest)
    natural = m.population == Population.natural_pr_review
    if stratum is not None and base_test_paths:
        raise SystemExit("with --stratum the regression norm is the task's recorded base-test overlay "
                         "(labels/base_tests_overlay, read only); base test paths are not accepted")
    n = repeats_for(m, repeats)
    if natural:
        if stratum is not None:
            raise refuse(f"{m.task_id} is a natural PR-review task, which has no candidate strata (natural-pr-v1 grades the "
                         "task's own pool)")
        # §20.2, D73: D19 grades the reference checks on held-out candidates, the first step of the run (building_problem)
        building = building_problem(REPO, m.task_id)
        if building:
            raise refuse(f"{m.task_id}: {building}")
        base_test_paths = tuple(natural_base_tests(tdir, m, base_test_paths))
    own = {load(tdir / p, Candidate).candidate_id: (p, load(tdir / p, Candidate)) for p in m.candidates}
    ref = next(c for _, c in own.values() if c.origin == CandidateOrigin.reference)
    if stratum is not None:  # checked (paths, ids, no links) before anything is graded or written
        cands = {c.candidate_id: (rel, c) for rel, c in load_stratum(tdir, stratum, m.task_id).candidates}
    else:
        cands = own
    refcheck = load(tdir / "verifiers" / "reference_check" / "spec.json", VerifierSpec)
    try:  # the frozen reference checks, unchanged since freezing; checked before anything is built, graded or written
        check_frozen(refcheck, tdir)
    except ValueError as exc:
        raise SystemExit(f"propose_labels refused: {exc}") from None
    if natural and (problem := frozen_problem(refcheck)):  # and frozen at all, for a natural task
        raise refuse(f"{m.task_id}: {problem}")
    base = task_base(tdir, m)
    if natural and not verify_snapshot(tdir, base.parent):
        raise refuse(f"{m.task_id}: base snapshot missing or modified at {base} (a natural PR-review task's base is built "
                     "by `tracecontract compile-pr-task`)")
    log_path = tdir / "labels" / "proposed_labels.json" if stratum is None else tdir / "strata" / stratum / "proposed_labels.json"
    overlay = tdir / OVERLAY
    link = linked(tdir, log_path, overlay)
    if link is not None:
        raise refuse(f"{link} is a symbolic link; the label log and the overlay are never written or read through a link")
    if stratum is None:
        check_base_test_paths(base, base_test_paths)
    tag, image_id = task_image(tdir, m)
    # The base-test overlay (the repository's own tests at the BASE commit): for the task's own candidates it is built from
    # the base test paths in a scratch directory, graded there and put in place once every label is known; a stratum's
    # regression norm is the task's recorded overlay, read where it is.
    stage = Path(tempfile.mkdtemp(prefix="tc_label_overlay_")) if stratum is None else None
    try:
        if stage is not None:
            build_overlay(base, stage / OVERLAY, base_test_paths)
        reg_root = stage if stage is not None else tdir
        use_overlay = bool(base_test_paths) if stage is not None else overlay.is_dir()
        reg_spec, reg_record = regression_spec(reg_root, m, tag, ref, base=base, repeats=n) if use_overlay else (None, None)
        log: dict[str, Any] = {"task_id": m.task_id, "labeler": LABELER, "created_at": now(), "candidates": {}}
        if stratum is not None:
            log.update(stratum=stratum, regression_overlay=OVERLAY if reg_spec else None)
        if natural or n > 1:
            log["repeats"] = n
            norm: dict[str, Any] = {"base_test_paths": list(base_test_paths) if stratum is None else None,
                                    "overlay": OVERLAY if reg_spec else None}
            if natural:
                norm["source"] = NATURAL_NORM_SOURCE
            if reg_spec is not None and reg_record is not None:
                norm.update(overlay_record(reg_root / OVERLAY), **reg_record)
            log["regression_norm"] = norm
        if natural:
            snap = load(tdir / (m.snapshot or "snapshot.json"), Snapshot)
            log.update(population=m.population.value, rule="D19, natural PR-review task (protocol §15.6; repeats: D64)",
                       reference_check={"verifier_id": refcheck.verifier_id, "content_sha256": refcheck.content_sha256,
                                        "checks_sha256": refcheck.checks_sha256, "frozen_at": refcheck.frozen_at},
                       base_snapshot_manifest_sha256=snap.file_manifest_sha256, image={"tag": tag, "id": image_id})
        log["candidates"], writes = label_candidates(cands, m=m, tdir=tdir, base=base, tag=tag, refcheck=refcheck,
                                                     reg_spec=reg_spec, reg_root=reg_root, repeats=n)
        # Every label is computed: now the overlay they were computed with, the candidates' records and the log.
        if stage is not None:
            install_overlay(stage / OVERLAY, overlay)
        for rel, c2 in writes:
            dump(c2, tdir / rel)  # a stratum candidate stays in its stratum's file (rel is strata/<name>/candidates/...)
        write_json(log, log_path)
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


def cli(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("task_dir")
    ap.add_argument("base_test_paths", nargs="*", help="the base commit's test files or directories (the regression norm); "
                    "a natural PR-review task's are s10.json base_tests.subset, the default and the only set accepted")
    ap.add_argument("--stratum", metavar="NAME", help="label the candidates of this candidate stratum instead of the task's own")
    ap.add_argument("--repeats", type=int, metavar="N", help="grade the reference checks and the regression norm N times and "
                    f"apply D19 to each; repeats that disagree are a missing decision (default 1; {NATURAL_REPEATS} for a "
                    "natural PR-review task, the only value accepted there, D64)")
    a = ap.parse_args(argv)
    main(a.task_dir, *a.base_test_paths, stratum=a.stratum, repeats=a.repeats)


if __name__ == "__main__":
    cli()
