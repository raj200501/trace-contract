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
* every condition named with ``--conditions`` has a verifier in the task;

and, for the run (every run started now is a new run under protocol v0.8):
* it grades every pair three times (``--repeats 3``; v0.7 §15.3, v0.8 §16.1);
* it uses ``tc-harness/0.3.5`` or a later harness (v0.8 §16.1): the version the grader
  (``tracecontract.sandbox.docker_runner``) would run now;
* its ``--run-id``, if given, names no recorded run (``results/runs/<id>`` is not changed);
* no other sandbox container is running and the git working tree is clean.

Pass the same ``--run-id``, ``--conditions``, ``--repeats`` and ``--pilot`` as to ``tracecontract
evaluate``; without ``--repeats`` the check assumes evaluate's default, one repeat, and fails.

Held-out candidates whose graded patch equals a development candidate's or another
held-out candidate's are reported as warnings (decision log D37). Same-code duplicates
(comments and docstrings ignored) must match the record in ``labels/duplicates.json``
(written by ``scripts/find_duplicates.py``; decision log D40), so a new one cannot go
unrecorded.

Usage: python scripts/preflight_final_run.py tasks/CS-01 tasks/CS-02 ... [--run-id ID] [--conditions C ...]
       [--repeats 3] [--pilot]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from tracecontract.analysis import PILOT_LABELER
from tracecontract.contract import task_gate
from tracecontract.reconstruction import recorded_check
from tracecontract.schemas import Candidate, CandidateOrigin, TaskManifest, VerifierSpec
from tracecontract.shadowing import shadowing_files
from tracecontract.store import load
from tracecontract.verifier import check_frozen

R = Path(__file__).resolve().parents[1]
NEW_RUN_REPEATS = 3  # protocol v0.7 §15.3: every new pair is graded three times
MIN_HARNESS = "tc-harness/0.3.5"  # protocol v0.8 §16.1: new runs use 0.3.5 (0.3.4 is never used for a run)


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
    return ap.parse_args(argv)


def shadowing_problems(m: TaskManifest, cands: list[Candidate]) -> list[str]:
    """One problem per candidate file that is a top-level module or package named like a guarded standard-library module."""
    return [f"{m.task_id}: {c.candidate_id} ships {path}, a top-level module named like the standard library's "
            f"`{mod}`; rejected before grading (tracecontract.shadowing)"
            for c in cands for path, mod in shadowing_files(c.patch, m.candidate_pythonpath)]


def main(*argv: str) -> int:
    a = _args(list(argv))
    problems: list[str] = []
    for td in map(Path, a.tasks):
        m = load(td / "task.json", TaskManifest)
        specs = [load(td / p, VerifierSpec) for p in m.verifiers]
        missing_conditions = sorted(set(a.conditions or []) - {s.condition.value for s in specs})
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
        cands = [load(td / p, Candidate) for p in m.candidates]
        problems += shadowing_problems(m, cands)
        held = [c for c in cands if c.split.value == "eval" and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]
        by_origin = {o: sum(c.origin == o for c in held) for o in CandidateOrigin}
        if by_origin[CandidateOrigin.observed_pre_correction] != 1 or by_origin[CandidateOrigin.valid_alternative] != 2 \
                or by_origin[CandidateOrigin.constructed_near_miss] != 5:
            problems.append(f"{m.task_id}: incomplete held-out pool {({k.value: v for k, v in by_origin.items() if v})}")
        for c in held:
            if c.final_label() is None and not any(lb.labeler == PILOT_LABELER for lb in c.labels):
                problems.append(f"{m.task_id}: {c.candidate_id} has no D19 proposal")
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
                print(f"WARN: {m.task_id}: held-out {c.candidate_id} has the same graded patch as development candidate {dev[k]}")
            if k in seen:
                print(f"WARN: {m.task_id}: held-out {c.candidate_id} has the same graded patch as held-out candidate {seen[k]}")
            seen.setdefault(k, c.candidate_id)
        if (SNAPSHOTS / m.task_id).is_dir():
            from tracecontract.duplicates import same_code_duplicates

            rec = same_code_duplicates(td, SNAPSHOTS)
            dp = td / "labels" / "duplicates.json"
            if not dp.exists() or json.loads(dp.read_text()) != rec:
                problems.append(f"{m.task_id}: same-code duplicates differ from labels/duplicates.json "
                                f"(run scripts/find_duplicates.py and disclose): {rec['duplicates']}")
            for cid, hits in rec["duplicates"].items():
                print(f"WARN: {m.task_id}: held-out {cid} has the same code (comments and docstrings ignored) as {hits}")
        audit_p = td / "labels" / "generator_audit.json"
        audit = json.loads(audit_p.read_text()) if audit_p.exists() else {}
        for ws, rec in audit.items():
            if ws == "_rules":
                continue
            if rec.get("hits") and not rec.get("assessment"):
                problems.append(f"{m.task_id}: generator audit {ws} has unassessed hits")
            strict = rec.get("strict_reaudit")
            if not strict:
                problems.append(f"{m.task_id}: generator audit {ws} has no strict re-audit (scripts/strict_reaudit.py, D44)")
            elif not strict.get("assessment") or any("error" in t for t in strict.get("transcripts", {}).values()):
                problems.append(f"{m.task_id}: strict re-audit of {ws} is unassessed or lacks a transcript")
        needed = {"eval-alt-1", "eval-alt-2", "eval-nm"}
        missing = sorted(needed - set(audit))
        if missing:
            problems.append(f"{m.task_id}: generator audits missing for {missing}")
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
