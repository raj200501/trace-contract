"""Blinded human review of held-out candidates (annotation guide v0.3; decision log D43, D44).

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

from .schemas import Candidate, CandidateOrigin, Label, LabelerKind, Review, ReviewerKind, TaskContract, TaskManifest
from .store import dump, load

VALUES = ("valid", "invalid", "ambiguous")
DECISIONS = ("accept", "reject", "edit", "needs_discussion")
ORIGIN_GUESSES = ("pre-correction", "alternative", "near-miss", "unsure")
TEMPLATE = "label_template.json"  # deliberately not matched by the reviewers' labels_<id>.json
REVIEWER_ID = re.compile(r"^R[0-9]{1,3}$")  # pseudonymous ids only; never a name
_ORIGIN_CLASS = {CandidateOrigin.observed_pre_correction: "pre-correction", CandidateOrigin.valid_alternative: "alternative",
                 CandidateOrigin.constructed_near_miss: "near-miss"}


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
    """Write the blinded packet to ``out`` and the key to ``key_path`` (outside ``out``; never overwritten)."""
    from .analysis import _norm_patch
    from .sandbox.docker_runner import prepare_workspace
    from .tasks import verify_snapshot

    out, key_path = out.resolve(), key_path.resolve()
    if key_path.is_relative_to(out):
        raise ValueError("the key must be written outside the packet")
    if out.exists():
        raise ValueError(f"{out} exists; choose a new directory")
    if key_path.exists():
        raise ValueError(f"{key_path} exists; it may be the only record of an earlier packet's mapping")
    rng = random.Random(seed)  # order only; the ids themselves are unguessable
    key: dict = {"seed": seed, "created_at": _now(), "tasks": {}}
    used: set[str] = set()
    for td in task_dirs:
        m = load(td / "task.json", TaskManifest)
        if not verify_snapshot(td, snapshot_root):
            raise ValueError(f"{m.task_id}: base snapshot missing or modified (run `tracecontract snapshot`)")
        tout = out / m.task_id
        (tout / "candidates").mkdir(parents=True)
        (tout / "session.txt").write_text(_user_turns(td, repo_root), encoding="utf-8")
        ref = load(td / m.contracts["reference"], TaskContract)
        (tout / "reference_contract.md").write_text(_contract_text(ref), encoding="utf-8")
        groups: dict[str, list[Candidate]] = {}
        for c in sorted(held_out(td), key=lambda c: c.candidate_id):
            groups.setdefault(_norm_patch(c.patch), []).append(c)
        items = list(groups.items())
        rng.shuffle(items)
        tkey: dict[str, list[str]] = {}
        for diff, cands in items:
            oid = ""
            while not oid or oid in used:
                oid = "C" + secrets.token_hex(3)
            used.add(oid)
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
    (out / "README.md").write_text(PACKET_README, encoding="utf-8")
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
merged, do not open the study repository's `tasks/`, `results/`, `paper/`,
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
            if cr.get("decision") not in DECISIONS:
                raise ValueError(f"{f}: contract review {rid}: decision must be one of {DECISIONS}")
        scored = {r.req_id for r in ref.active() if r.scored} | {"REGRESSION"}
        for oid, lb in d["labels"].items():
            value, viol = lb.get("value"), list(lb.get("violated_requirements") or [])
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
    for t, revs in by_task.items():
        for oid, cids in key["tasks"][t].items():
            values = {rev: d["labels"][oid] for rev, d in revs.items()}
            if len({(v["value"], tuple(sorted(v.get("violated_requirements") or []))) for v in values.values()}) > 1:
                report["disagreements"].setdefault(t, []).append(
                    {"candidates": cids, "labels": {r: [v["value"], v.get("violated_requirements") or []] for r, v in values.items()}})
            for cid in cids:
                path = tasks_root / t / "candidates" / f"{cid}.json"
                c = load(path, Candidate)
                truth = _ORIGIN_CLASS.get(c.origin, "other")
                for rev, v in sorted(values.items()):
                    g = report["origin_guesses"].setdefault(rev, {"correct": 0, "wrong": 0, "unsure": 0})
                    g["unsure" if v["origin_guess"] == "unsure" else "correct" if v["origin_guess"] == truth else "wrong"] += 1
                    if not dry_run:
                        c.labels.append(Label(value=v["value"], violated_requirements=list(v.get("violated_requirements") or []),
                                              labeler=f"human:{rev}", labeler_kind=LabelerKind.human, adjudicated=False,
                                              timestamp=_now(), note=f"{(v.get('note') or '')[:2000]} "
                                              f"[origin guess: {v['origin_guess']}] {tag}"))
                        report["merged_labels"] += 1
                if not dry_run:
                    dump(c, path)
        ref_path = tasks_root / t / "contracts" / "reference.json"
        ref = load(ref_path, TaskContract)
        for r in ref.requirements:
            decisions = {rev: d["contract_reviews"][r.req_id] for rev, d in revs.items()}
            if len({v["decision"] for v in decisions.values()}) > 1:
                report["contract_disagreements"].setdefault(t, []).append(
                    {"requirement": r.req_id, "decisions": {rev: v["decision"] for rev, v in decisions.items()}})
            if dry_run:
                continue
            for rev, v in sorted(decisions.items()):
                r.reviews.append(Review(reviewer=f"human:{rev}", reviewer_kind=ReviewerKind.human, decision=v["decision"],
                                        timestamp=_now(), note=f"{(v.get('note') or '')[:2000]} {tag}"))
                report["merged_contract_reviews"] += 1
        if not dry_run:
            dump(ref, ref_path)
    return report
