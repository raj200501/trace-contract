"""Blinded human review of held-out candidates (annotation guide v0.3; decision log D43).

``export_packet`` writes, per task, what a reviewer needs to label the held-out
candidates without seeing how any candidate was made:

* the rendered session (user turns, assistant text, abbreviated tool calls);
* the reference contract (requirement ids, kinds, statuses, statements, quotes);
* each held-out candidate under an opaque id, in shuffled order: its graded diff
  (protected test files removed, git index lines dropped) and its file state (base
  snapshot plus that diff), which a reviewer can run with ``tracecontract
  sandbox-python``;
* a label template keyed by the opaque ids.

The packet holds no candidate id, origin, description, construction label, rule
proposal, construction check, verifier outcome or review-queue reason. The mapping
from opaque ids to candidates (the *key*) is written to a separate file that the
coordinator keeps; reviewers must not see it. ``merge_labels`` reads the reviewers'
label files with the key, refuses to merge until every task has the required number
of complete reviews, and appends the labels to the candidate records as human labels.
Reviewers' disagreements are listed for adjudication; nothing is adjudicated here.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .schemas import Candidate, CandidateOrigin, Label, LabelerKind, TaskContract, TaskManifest
from .store import dump, load

VALUES = ("valid", "invalid", "ambiguous")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def held_out(task_dir: Path) -> list[Candidate]:
    """The candidates humans label: evaluation split, without the no-op and the reference."""
    m = load(task_dir / "task.json", TaskManifest)
    cands = [load(task_dir / p, Candidate) for p in m.candidates]
    return [c for c in cands if c.split.value == "eval" and c.origin not in (CandidateOrigin.noop, CandidateOrigin.reference)]


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


def export_packet(task_dirs: list[Path], out: Path, key_path: Path, *, snapshot_root: Path, repo_root: Path,
                  seed: int) -> dict:
    """Write the blinded packet to ``out`` and the id key to ``key_path`` (which must lie outside ``out``)."""
    from .analysis import _norm_patch
    from .sandbox.docker_runner import prepare_workspace
    from .tasks import render_session, session_for_task, verify_snapshot

    out, key_path = out.resolve(), key_path.resolve()
    if key_path.is_relative_to(out):
        raise ValueError("the key must be written outside the packet")
    if out.exists():
        raise ValueError(f"{out} exists; choose a new directory")
    rng = random.Random(seed)
    key: dict = {"seed": seed, "created_at": _now(), "tasks": {}}
    used: set[str] = set()
    for td in task_dirs:
        m = load(td / "task.json", TaskManifest)
        if not verify_snapshot(td, snapshot_root):
            raise ValueError(f"{m.task_id}: base snapshot missing or modified (run `tracecontract snapshot`)")
        tout = out / m.task_id
        (tout / "candidates").mkdir(parents=True)
        try:
            (tout / "session.txt").write_text(render_session(session_for_task(td, repo_root)), encoding="utf-8")
        except FileNotFoundError:
            (tout / "session.txt").write_text("(no transcript for this task)\n", encoding="utf-8")
        ref = load(td / m.contracts["reference"], TaskContract)
        (tout / "reference_contract.md").write_text(_contract_text(ref), encoding="utf-8")
        cands = held_out(td)
        rng.shuffle(cands)
        tkey: dict[str, str] = {}
        for c in cands:
            oid = ""
            while not oid or oid in used:
                oid = f"R{rng.randrange(16 ** 6):06x}"
            used.add(oid)
            ws, diags, err = prepare_workspace(snapshot_root / m.task_id, c.patch)
            if ws is None:
                raise ValueError(f"{m.task_id}: a candidate patch could not be applied ({err})")
            cdir = tout / "candidates" / oid
            cdir.mkdir()
            (cdir / "changes.diff").write_text(_norm_patch(c.patch) + "\n", encoding="utf-8")
            shutil.copytree(ws, cdir / "state", symlinks=False)
            shutil.rmtree(ws, ignore_errors=True)
            tkey[oid] = c.candidate_id
        key["tasks"][m.task_id] = tkey
        template = {"task_id": m.task_id, "reviewer": "", "labels": {
            oid: {"value": None, "violated_requirements": [], "note": ""} for oid in tkey}}
        (tout / "labels_template.json").write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(PACKET_README, encoding="utf-8")
    key["packet_files_sha256"] = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(out.rglob("*")) if p.is_file() and "/state/" not in str(p.relative_to(out))}
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    return {"packet": str(out), "key": str(key_path), "candidates": sum(len(v) for v in key["tasks"].values())}


PACKET_README = """# Blinded review packet

One folder per task:

* `session.txt`: the session (user turns, assistant text, abbreviated tool calls);
* `reference_contract.md`: the requirements to judge against;
* `candidates/<id>/changes.diff`: one candidate's change to the base repository;
* `candidates/<id>/state/`: the base repository with that change applied;
* `labels_template.json`: copy it to `labels_<your name>.json` and fill it in.

The candidate ids are random. The packet does not say how a candidate was made, what
anyone else thinks of it, or how any verifier graded it. Until you have recorded every
label, do not open the study repository's `tasks/*/candidates/`, `tasks/*/labels/`
(including `review_queue.json`), `results/`, `paper/` or the HTML reports, and do not
discuss candidates with the other reviewer.

To run code in a candidate's state (offline, unprivileged sandbox; needs Docker and the
study repository):

    tracecontract sandbox-python tasks/<task> <packet>/<task>/candidates/<id>/state -c '...'

Labels (see `docs/annotation_guide.md`): `valid`, `invalid` with the violated
requirement ids (or `REGRESSION` for broken existing behaviour), or `ambiguous` with a
note saying what is unclear. Give each label a short note with your reason.
"""


def merge_labels(label_files: list[Path], key_path: Path, tasks_root: Path, *, min_reviewers: int = 2,
                 dry_run: bool = False) -> dict:
    """Validate reviewers' label files and append them to the candidate records as human labels."""
    key = json.loads(key_path.read_text(encoding="utf-8"))
    by_task: dict[str, dict[str, dict]] = {}
    for f in label_files:
        d = json.loads(f.read_text(encoding="utf-8"))
        t, rev = d.get("task_id"), (d.get("reviewer") or "").strip()
        if t not in key["tasks"]:
            raise ValueError(f"{f}: unknown task {t!r}")
        if not rev:
            raise ValueError(f"{f}: reviewer name missing")
        if rev in by_task.setdefault(t, {}):
            raise ValueError(f"{f}: second file from reviewer {rev!r} for {t}")
        ids = set(key["tasks"][t])
        if set(d["labels"]) != ids:
            raise ValueError(f"{f}: labels must cover exactly the packet's candidates for {t}")
        ref = load(tasks_root / t / "contracts" / "reference.json", TaskContract)
        req_ids = {r.req_id for r in ref.requirements} | {"REGRESSION"}
        for oid, lb in d["labels"].items():
            if lb.get("value") not in VALUES:
                raise ValueError(f"{f}: {oid}: value must be one of {VALUES}")
            bad = set(lb.get("violated_requirements") or []) - req_ids
            if bad:
                raise ValueError(f"{f}: {oid}: unknown requirement ids {sorted(bad)}")
            if lb["value"] == "invalid" and not lb.get("violated_requirements"):
                raise ValueError(f"{f}: {oid}: an invalid label needs violated requirement ids or REGRESSION")
        by_task[t][rev] = d
    short = {t: len(by_task.get(t, {})) for t in key["tasks"] if len(by_task.get(t, {})) < min_reviewers}
    if short:
        raise ValueError(f"not merging: tasks with fewer than {min_reviewers} complete reviews: {short}")
    report: dict = {"merged": 0, "disagreements": {}}
    for t, revs in by_task.items():
        for oid, cid in key["tasks"][t].items():
            values = {rev: d["labels"][oid] for rev, d in revs.items()}
            if len({(v["value"], tuple(sorted(v.get("violated_requirements") or []))) for v in values.values()}) > 1:
                report["disagreements"].setdefault(t, []).append(
                    {"candidate": cid, "labels": {r: [v["value"], v.get("violated_requirements") or []] for r, v in values.items()}})
            if dry_run:
                continue
            path = tasks_root / t / "candidates" / f"{cid}.json"
            c = load(path, Candidate)
            for rev, v in sorted(values.items()):
                c.labels.append(Label(value=v["value"], violated_requirements=list(v.get("violated_requirements") or []),
                                      labeler=f"human:{rev}", labeler_kind=LabelerKind.human, adjudicated=False,
                                      timestamp=_now(), note=(v.get("note") or "")[:2000] + " [blinded packet]"))
                report["merged"] += 1
            dump(c, path)
    return report
