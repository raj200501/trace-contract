"""Blinded human review of held-out candidates (annotation guide v0.4; decision log D43-D45).

``export_packet`` writes, per task, what a reviewer needs to label the held-out
candidates without being told how any candidate was made:

* the session's user turns only (the assistant's text and tool calls would show its
  pre-correction edits and so identify the observed pre-correction state);
* the reference contract (requirement ids, kinds, statuses, statements, quotes);
* each distinct held-out change under a random id, in shuffled order: its graded diff
  (protected test files removed, git index lines dropped) and its file state (base
  snapshot plus that diff), which a reviewer can run with ``tracecontract
  sandbox-python``. Candidates with identical graded diffs share one id, so the packet
  does not reveal duplicates;
* a label template (``label_template.json``) keyed by the random ids, with a slot for a
  contract review of every reference requirement and an origin guess per candidate.

The packet holds no candidate id, origin, description, construction label, rule
proposal, construction check, verifier outcome or review-queue reason. It does not hide
what the code itself shows: near misses are small edits of the agent's final code and
the alternatives are independent implementations, so a reviewer may still infer
origin. The origin guesses measure how often that happens.

The packet is written outside the repository: it holds the session's turns and the
candidates' code (for a natural PR-review task, pseudonymised third-party text and
upstream code, protocol §17.4), and reviewers are told not to open the repository until
their labels are merged. ``export_packet`` refuses an ``out`` inside the repository it
reads (``repo_root``) or inside the study repository, git-ignored directories included,
before anything is written.

A natural PR-review task's pre-review state (origin ``natural_pre_review``) is the
"pre-correction" origin class of the origin guesses, as an observed pre-correction state
is: the agent's state before the reviewer's correction.

The mapping from random ids to candidates (the *key*) is written to a separate file
that the coordinator keeps; reviewers must not see it. ``merge_labels`` reads the
reviewers' files with the key, refuses to merge until every task has the required
number of complete reviews, and then appends the labels to the candidate records and
the contract reviews to the reference contract, as human decisions. Disagreements are
listed for adjudication; nothing is adjudicated here, and an unresolved disagreement
leaves the candidate without a final label (``Candidate.final_label``).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import roots
from .schemas import Candidate, CandidateOrigin, Label, LabelerKind, Review, ReviewerKind, TaskContract, TaskManifest
from .store import dump, load

VALUES = ("valid", "invalid", "ambiguous")
DECISIONS = ("accept", "reject", "edit", "needs_discussion")
ORIGIN_GUESSES = ("pre-correction", "alternative", "near-miss", "unsure")
TEMPLATE = "label_template.json"  # deliberately not matched by the reviewers' labels_<id>.json
REVIEWER_ID = re.compile(r"^R[0-9]{1,3}$")  # pseudonymous ids only; never a name
# The origin class an origin guess is scored against: a natural PR-review task's pre-review state is the agent's state
# before the reviewer's correction, so it is "pre-correction" as an observed pre-correction state is.
_ORIGIN_CLASS = {CandidateOrigin.observed_pre_correction: "pre-correction", CandidateOrigin.natural_pre_review: "pre-correction",
                 CandidateOrigin.valid_alternative: "alternative", CandidateOrigin.constructed_near_miss: "near-miss"}


def origin_class(origin: CandidateOrigin) -> str:
    """The origin class of the packet's origin guesses (``pre-correction``, ``alternative``, ``near-miss``), or ``other``."""
    return _ORIGIN_CLASS.get(origin, "other")


def packet_location_problem(out: Path, repo_root: Path) -> str | None:
    """Why the packet may not be written to ``out``; ``None`` if it may.

    Refused: ``out`` inside the repository ``repo_root`` that the packet is read from, or inside the study repository
    (``roots.REPO``), git-ignored directories such as ``data/natural/`` included. The packet holds the session's turns
    and the candidates' code (a natural PR-review task's: third-party text and upstream code, §17.4), and its reviewers
    must not open the repository before their labels are merged. Both the path as given (made absolute, ``..`` taken
    out as written: ``<repo>/../p`` is outside) and its resolved form (links followed) are checked.
    """
    given = Path(os.path.abspath(out))
    for repo in dict.fromkeys((Path(os.path.abspath(repo_root)), roots.REPO)):
        for path, root in ((given, repo), (given.resolve(), repo.resolve())):
            if path == root or root in path.parents:
                return (f"{out} lies inside the repository {root}; the packet is written outside it (it holds the session's "
                        "turns and the candidates' code, and its reviewers must not open the repository)")
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def held_out(task_dir: Path) -> list[Candidate]:
    """The candidates humans label: evaluation split, without the no-op and the reference."""
    m = load(task_dir / "task.json", TaskManifest)
    cands = [load(task_dir / p, Candidate) for p in m.candidates]
    return [c for c in cands if c.split.value == "eval" and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]


def _user_turns(task_dir: Path, repo_root: Path) -> str:
    from .tasks import session_for_task

    try:
        s = session_for_task(task_dir, repo_root)
    except FileNotFoundError:
        return "(no transcript for this task)\n"
    return "\n".join(f"[{p.event_id}] USER:\n{p.text}\n" for p in s.user_prompts())


def _readable(d: Path) -> None:
    """The sandbox user (another UID) must be able to read a state directory."""
    for root, _dirs, files in os.walk(d):
        os.chmod(root, 0o755)
        for f in files:
            fp = Path(root) / f
            fp.chmod(fp.stat().st_mode | 0o644)


def _contract_text(c: TaskContract) -> str:
    lines = [f"# Reference contract ({c.task_id})", "",
             "Requirements the user's turns establish. Superseded and unresolved requirements are not scored.", ""]
    for r in c.requirements:
        lines.append(f"## {r.req_id} ({r.kind.value}, {r.status.value}{'' if r.scored else ', not scored'})")
        lines += ["", r.statement, ""]
        if r.observable:
            lines += [f"Observable: {r.observable}", ""]
        for e in r.evidence:
            lines.append(f"> \"{e.quote}\" ({e.event_id})")
        if not r.evidence:
            lines.append("(inferred; no quote)")
        lines.append("")
    return "\n".join(lines)


def _key_tag(key_path: Path) -> str:
    return hashlib.sha256(key_path.read_bytes()).hexdigest()[:12]


def export_packet(task_dirs: list[Path], out: Path, key_path: Path, *, snapshot_root: Path, repo_root: Path,
                  seed: int) -> dict:
    """Write the blinded packet to ``out`` (outside the repository: :func:`packet_location_problem`) and the key to
    ``key_path`` (outside ``out``; never overwritten)."""
    from .analysis import _norm_patch
    from .sandbox.docker_runner import prepare_workspace
    from .tasks import verify_snapshot

    problem = packet_location_problem(out, repo_root)
    if problem:
        raise ValueError(problem)
    out, key_path = out.resolve(), key_path.resolve()
    if key_path.is_relative_to(out):
        raise ValueError("the key must be written outside the packet")
    if out.exists():
        raise ValueError(f"{out} exists; choose a new directory")
    if key_path.exists():
        raise ValueError(f"{key_path} exists; it may be the only record of an earlier packet's mapping")
    tasks: list[tuple[Path, TaskManifest, TaskContract]] = []
    for td in task_dirs:  # every task is checked before anything is written
        m = load(td / "task.json", TaskManifest)
        if not verify_snapshot(td, snapshot_root):
            hint = ("a natural PR-review task's base is built by `tracecontract compile-pr-task`"
                    if m.population.value == roots.NATURAL_PR else "run `tracecontract snapshot`")
            raise ValueError(f"{m.task_id}: base snapshot missing or modified ({hint})")
        if "reference" not in m.contracts:
            raise ValueError(f"{m.task_id}: no reference contract; the reviewers judge the candidates against it")
        tasks.append((td, m, load(td / m.contracts["reference"], TaskContract)))
    rng = random.Random(seed)  # recorded in the key; the ids, and the order of folders and entries, come from secrets
    key: dict = {"seed": seed, "created_at": _now(), "tasks": {}}
    used: set[str] = set()
    for td, m, ref in tasks:
        tout = out / m.task_id
        (tout / "candidates").mkdir(parents=True)
        (tout / "session.txt").write_text(_user_turns(td, repo_root), encoding="utf-8")
        (tout / "reference_contract.md").write_text(_contract_text(ref), encoding="utf-8")
        groups: dict[str, list[Candidate]] = {}
        for c in sorted(held_out(td), key=lambda c: c.candidate_id):
            groups.setdefault(_norm_patch(c.patch), []).append(c)
        items = list(groups.items())
        rng.shuffle(items)
        named = []
        for diff, cands in items:
            oid = ""
            while not oid or oid in used:
                oid = "C" + secrets.token_hex(3)
            used.add(oid)
            named.append((oid, diff, cands))
        # Folders and template entries are made in the order of the random ids, so neither the
        # seed nor the creation order maps a position to a candidate.
        tkey: dict[str, list[str]] = {}
        for oid, diff, cands in sorted(named, key=lambda x: x[0]):
            ws, _diags, err = prepare_workspace(snapshot_root / m.task_id, cands[0].patch)
            if ws is None:
                raise ValueError(f"{m.task_id}: a candidate patch could not be applied ({err})")
            cdir = tout / "candidates" / oid
            cdir.mkdir()
            (cdir / "changes.diff").write_text(diff + "\n", encoding="utf-8")
            shutil.copytree(ws, cdir / "state", symlinks=False)
            shutil.rmtree(ws, ignore_errors=True)
            _readable(cdir / "state")
            tkey[oid] = [c.candidate_id for c in cands]
        key["tasks"][m.task_id] = tkey
        template = {"task_id": m.task_id, "reviewer": "",
                    "contract_reviews": {r.req_id: {"decision": None, "note": ""} for r in ref.requirements},
                    "labels": {oid: {"value": None, "violated_requirements": [], "origin_guess": None, "note": ""}
                               for oid in tkey}}
        (tout / TEMPLATE).write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    natural = any(m.population.value == roots.NATURAL_PR for _, m, _ in tasks)
    (out / "README.md").write_text(PACKET_README + (NATURAL_PACKET_README if natural else ""), encoding="utf-8")
    key["packet_files_sha256"] = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(out.rglob("*")) if p.is_file() and "/state/" not in str(p.relative_to(out))}
    key_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)  # only the coordinator may read it
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(key, indent=2) + "\n")
    return {"packet": str(out), "key": str(key_path), "items": sum(len(v) for v in key["tasks"].values()),
            "candidates": sum(len(c) for v in key["tasks"].values() for c in v.values())}


PACKET_README = """# Blinded review packet

One folder per task:

* `session.txt`: the user turns of the session;
* `reference_contract.md`: the requirements to judge against;
* `candidates/<id>/changes.diff`: one candidate's change to the base repository;
* `candidates/<id>/state/`: the base repository with that change applied;
* `label_template.json`: copy it to `labels_<your reviewer id>.json` and fill it in. Put
  your pseudonymous reviewer id (`R` and a number, e.g. `R1`), never your name, in
  `reviewer`.

The candidate ids are random. The packet does not say how a candidate was made, what
anyone else thinks of it, or how any verifier graded it. Until your labels have been
merged, do not open the study repository's `tasks/`, `results/`, `paper/`, `data/`,
`experiments/` or `docs/` folders (except `docs/annotation_guide.md`), its `README.md`
or `STATUS.md`, any HTML report or the git history; do not run `tracecontract
validate-task --show-candidates` or `render-session`; and do not discuss candidates or
requirements with the other reviewer.

To run code in a candidate's state (offline, unprivileged sandbox; needs Docker and the
study repository):

    tracecontract sandbox-python tasks/<task> <packet>/<task>/candidates/<id>/state -c '...'

Fill in, for each requirement in `contract_reviews`: `accept`, `reject`, `edit` (say
what to change in `note`) or `needs_discussion`. For each candidate in `labels`:
`value` is `valid`, `invalid` (with the violated requirement ids, or `REGRESSION` for
broken existing behaviour) or `ambiguous` (with a note saying what is unclear); see
`docs/annotation_guide.md`. `origin_guess` is your guess of how the candidate was made
(`pre-correction`: the agent's state before the user's correction; `alternative`: an
independent valid implementation; `near-miss`: a deliberately flawed variant;
`unsure`). It is used only to measure how blind the review was, never as a label. Give
each decision a short note with your reason.
"""

# Added to the README when the packet holds a natural PR-review task (protocol §15.6, §17.4).
NATURAL_PACKET_README = """
## Tasks from public pull-request threads

Some tasks come from public GitHub pull requests. Their `session.txt` holds the linked
issue, the reviewer's comment and the same reviewer's later replies, pseudonymised; the
code the comment was made on is not shown, since it would identify a candidate. Their
states hold the project's own code, under its licence. For these tasks, `pre-correction`
is the agent's state that the reviewer commented on. Until your labels have been merged,
do not look up the thread, its repository or its commits online: they show how the
candidates were made. Keep the packet private; do not copy its texts or code elsewhere.

These tasks are not in the study repository's `tasks/` folder. To run code in one of
their candidates' states, give `sandbox-python` the task as `data/natural/tasks/<task>`;
the command reads the task's environment from there, and the rule above still holds: do
not open that folder yourself.

    tracecontract sandbox-python data/natural/tasks/<task> <packet>/<task>/candidates/<id>/state -c '...'
"""


def merge_labels(label_files: list[Path], key_path: Path, tasks_root: Path, *, min_reviewers: int = 2,
                 dry_run: bool = False) -> dict:
    """Validate reviewers' files and append their decisions to the task records as human decisions.

    Labels go to the candidate records, contract reviews to the reference contract. Nothing
    is merged unless every task in the key has ``min_reviewers`` complete reviews, and a
    packet's reviews cannot be merged twice.
    """
    key = json.loads(key_path.read_text(encoding="utf-8"))
    tag = f"[blinded packet {_key_tag(key_path)}]"
    by_task: dict[str, dict[str, dict]] = {}
    for f in label_files:
        if f.name == TEMPLATE:
            raise ValueError(f"{f}: this is the empty template; pass the reviewers' labels_<id>.json files")
        d = json.loads(f.read_text(encoding="utf-8"))
        t, rev = d.get("task_id"), (d.get("reviewer") or "").strip()
        if t not in key["tasks"]:
            raise ValueError(f"{f}: unknown task {t!r}")
        if not REVIEWER_ID.match(rev):
            raise ValueError(f"{f}: reviewer id missing or not a pseudonymous id like R1")
        if rev in by_task.setdefault(t, {}):
            raise ValueError(f"{f}: second file from reviewer {rev!r} for {t}")
        if set(d.get("labels", {})) != set(key["tasks"][t]):
            raise ValueError(f"{f}: labels must cover exactly the packet's candidates for {t}")
        ref = load(tasks_root / t / "contracts" / "reference.json", TaskContract)
        if set(d.get("contract_reviews", {})) != {r.req_id for r in ref.requirements}:
            raise ValueError(f"{f}: contract_reviews must cover exactly the reference requirements of {t}")
        for rid, cr in d["contract_reviews"].items():
            if not isinstance(cr, dict) or cr.get("decision") not in DECISIONS:
                raise ValueError(f"{f}: contract review {rid}: decision must be one of {DECISIONS}")
            if not isinstance(cr.get("note") or "", str):
                raise ValueError(f"{f}: contract review {rid}: note must be text")
        scored = {r.req_id for r in ref.active() if r.scored} | {"REGRESSION"}
        for oid, lb in d["labels"].items():
            if not isinstance(lb, dict):
                raise ValueError(f"{f}: {oid}: a label must be an object")
            raw_viol = lb.get("violated_requirements") or []
            if not isinstance(raw_viol, list) or not all(isinstance(x, str) for x in raw_viol):
                raise ValueError(f"{f}: {oid}: violated_requirements must be a list of requirement ids")
            if not isinstance(lb.get("note") or "", str):
                raise ValueError(f"{f}: {oid}: note must be text")
            value, viol = lb.get("value"), list(raw_viol)
            if value not in VALUES:
                raise ValueError(f"{f}: {oid}: value must be one of {VALUES}")
            if lb.get("origin_guess") not in ORIGIN_GUESSES:
                raise ValueError(f"{f}: {oid}: origin_guess must be one of {ORIGIN_GUESSES}")
            if value == "invalid":
                if not viol or set(viol) - scored:
                    raise ValueError(f"{f}: {oid}: an invalid label needs violated ids of active scored requirements "
                                     f"or REGRESSION (got {viol})")
            elif viol:
                raise ValueError(f"{f}: {oid}: a {value} label must not list violated requirements")
            if value == "ambiguous" and not (lb.get("note") or "").strip():
                raise ValueError(f"{f}: {oid}: an ambiguous label needs a note saying what is unclear")
        by_task[t][rev] = d
    short = {t: len(by_task.get(t, {})) for t in key["tasks"] if len(by_task.get(t, {})) < min_reviewers}
    if short:
        raise ValueError(f"not merging: tasks with fewer than {min_reviewers} complete reviews: {short}")
    for t, revs in by_task.items():
        for cids in key["tasks"][t].values():
            for cid in cids:
                c = load(tasks_root / t / "candidates" / f"{cid}.json", Candidate)
                if any(lb.labeler_kind == LabelerKind.human and tag in lb.note for lb in c.labels):
                    raise ValueError(f"{t}/{cid}: labels from this packet were merged already")
    report: dict = {"merged_labels": 0, "merged_contract_reviews": 0, "disagreements": {}, "contract_disagreements": {},
                    "origin_guesses": {}}
    updates: dict[Path, object] = {}  # every record to write, built in memory before anything is written
    for t, revs in by_task.items():
        for oid, cids in key["tasks"][t].items():
            values = {rev: d["labels"][oid] for rev, d in revs.items()}
            if len({(v["value"], tuple(sorted(v.get("violated_requirements") or []))) for v in values.values()}) > 1:
                report["disagreements"].setdefault(t, []).append(
                    {"candidates": cids, "labels": {r: [v["value"], v.get("violated_requirements") or []] for r, v in values.items()}})
            for cid in cids:
                path = tasks_root / t / "candidates" / f"{cid}.json"
                c = load(path, Candidate)
                truth = origin_class(c.origin)
                for rev, v in sorted(values.items()):
                    g = report["origin_guesses"].setdefault(rev, {"correct": 0, "wrong": 0, "unsure": 0})
                    g["unsure" if v["origin_guess"] == "unsure" else "correct" if v["origin_guess"] == truth else "wrong"] += 1
                    c.labels.append(Label(value=v["value"], violated_requirements=list(v.get("violated_requirements") or []),
                                          labeler=f"human:{rev}", labeler_kind=LabelerKind.human, adjudicated=False,
                                          timestamp=_now(), note=f"{(v.get('note') or '')[:2000]} "
                                          f"[origin guess: {v['origin_guess']}] {tag}"))
                    report["merged_labels"] += 1
                updates[path] = c
        ref_path = tasks_root / t / "contracts" / "reference.json"
        ref = load(ref_path, TaskContract)
        for r in ref.requirements:
            decisions = {rev: d["contract_reviews"][r.req_id] for rev, d in revs.items()}
            if len({v["decision"] for v in decisions.values()}) > 1:
                report["contract_disagreements"].setdefault(t, []).append(
                    {"requirement": r.req_id, "decisions": {rev: v["decision"] for rev, v in decisions.items()}})
            for rev, v in sorted(decisions.items()):
                r.reviews.append(Review(reviewer=f"human:{rev}", reviewer_kind=ReviewerKind.human, decision=v["decision"],
                                        timestamp=_now(), note=f"{(v.get('note') or '')[:2000]} {tag}"))
                report["merged_contract_reviews"] += 1
        updates[ref_path] = ref
    if dry_run:
        report["merged_labels"] = report["merged_contract_reviews"] = 0
        return report
    originals = {path: path.read_bytes() for path in updates}
    try:
        for path, record in updates.items():
            dump(record, path)
    except BaseException:
        for path, data in originals.items():  # all or nothing
            path.write_bytes(data)
        raise
    return report
