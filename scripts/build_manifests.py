"""Build data/manifests/{provenance_index,rejection_ledger}.json (decision log D47, D51; protocol v0.8 §16.4).

Inputs:

* the task provenance records, ``tasks/<id>/provenance.json`` (frozen: only read), each with the
  task's triage proposal from its sidecar ``tasks/<id>/triage.json`` (the record's own ``triage``
  field where a task has no sidecar);
* the natural-data screening rows, ``data/manifests/screening_natural.json``, one per screened
  session;
* screening funnels: the files ``data/manifests/screening_natural_*.json`` that have a ``stages``
  list (deterministic stages, counts only, no per-candidate rows);
* stage results: the files ``data/manifests/screening_natural_*.json`` that have a ``stage`` and
  per-candidate ``rows`` (``screening_natural_aidev_s9.json``). Every failure of such a stage
  becomes one ledger row with the stage and its reason, keyed by ids only (comment, PR and
  repository ids). A comment the judges disagree on is excluded and counted, not a failure. A
  comment whose PR has no later commit that changes the commented file also gets the reason
  "no later commit changes the commented file" (§16.4);
* the index of the natural PR-review tasks, ``data/manifests/natural_tasks_index.json`` (written by
  ``tracecontract natural-index``, protocol v0.9 §17.4): every family it records as rejected at S10
  becomes one ledger row with stage S10 and its reason, keyed by ids only, with the reserve that takes
  its place (§17.3) where there is one.

Any other ``screening_natural_*.json`` file is refused, so that no file is summarised as what it
is not. Every screened session appears in the index (accepted, pending, or rejected), so that
valid-task yield is always reported over ALL screened sessions, by population. The ledger's note
has one clause per population, describing the screening state that these files record.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

R = Path(__file__).resolve().parents[1]
_FIELDS = ("record_id", "session_id", "population", "source_id", "repo_url", "base_commit", "licenses", "permission_basis",
           "trace_sha256", "snapshot_manifest_sha256", "capture_method", "redaction_status", "task_family_id", "eligibility",
           "rejection_reasons", "triage", "accessed")
NO_LATER_COMMIT = "no later commit changes the commented file"  # protocol v0.8 §16.4
_EXCLUDED = "judges_disagree"  # excluded and counted, not a failure (protocol §15.6)
NATURAL_INDEX = "natural_tasks_index.json"  # natural PR-review tasks: S10 outcomes (protocol v0.9 §17.4)


def _triage(task_dir: Path, record: dict[str, Any]) -> Any:
    """The task's triage proposal: its sidecar's, else the provenance record's own field."""
    path = task_dir / "triage.json"
    if not path.is_file():
        return record.get("triage")
    side = json.loads(path.read_text(encoding="utf-8"))
    if side.get("task_id") != task_dir.name or side.get("provenance_record_id") != record.get("record_id"):
        raise ValueError(f"{path}: the sidecar names task {side.get('task_id')!r} and record "
                         f"{side.get('provenance_record_id')!r}, not {task_dir.name!r} and {record.get('record_id')!r}")
    return side["triage"]


def screening_files(manifests: Path) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    """(funnels, stage results) among ``screening_natural_*.json``, each as (file name, content)."""
    funnels, stages = [], []
    for f in sorted(manifests.glob("screening_natural_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("stages"), list):
            funnels.append((f.name, d))
        elif isinstance(d, dict) and isinstance(d.get("stage"), str) and isinstance(d.get("rows"), list):
            stages.append((f.name, d))
        else:
            raise ValueError(f"{f}: neither a screening funnel (a 'stages' list) nor a stage result ('stage' and 'rows')")
    return funnels, stages


def stage_rejections(result: dict[str, Any]) -> list[dict[str, Any]]:
    """One ledger row per candidate that fails the stage, keyed by its ids, with the stage and its reason."""
    out = []
    for r in result["rows"]:
        reason = r.get("failure_reason")
        if r.get("qualifies") or reason in (None, _EXCLUDED):
            continue
        reasons = [reason]
        if "diff_commit" in r and r["diff_commit"] is None and r.get("commits_reachable"):
            reasons.insert(0, NO_LATER_COMMIT)
        out.append({"source_id": f"comment:{r['comment_id']}", "population": result["population"], "stage": result["stage"],
                    "reasons": reasons, "comment_id": r["comment_id"], "pr_id": r["pr_id"], "repo_id": r["repo_id"]})
    return out


def s10_rejections(index: dict[str, Any]) -> list[dict[str, Any]]:
    """One ledger row per family the natural-task index records as rejected at S10, keyed by its ids, with its reason."""
    out = []
    for t in index.get("tasks", []):
        s10 = t.get("s10") or {}
        if s10.get("outcome") != "rejected":
            continue
        row = {"source_id": f"pr:{t.get('pr_id')}", "population": index.get("population"), "stage": s10.get("stage") or "S10",
               "reasons": [s10.get("reason")], "comment_id": t.get("comment_id"), "pr_id": t.get("pr_id"),
               "repo_id": t.get("repo_id"), "task_id": t.get("task_id")}
        if t.get("replaced_by"):
            row["replaced_by"] = t["replaced_by"]
        out.append(row)
    return out


def _s10_part(index: dict[str, Any], failed: int) -> str:
    counts = index.get("counts") or {}
    others = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()) if k != "rejected")
    return (f"of the {len(index.get('tasks', []))} families and reserves of S10 in {NATURAL_INDEX}, {failed} are rejected (in "
            f"this ledger with stage S10 and their reasons)" + (f" and {others}" if others else ""))


def _funnel_part(funnel: dict[str, Any]) -> str:
    stages = {st.get("id"): st for st in funnel["stages"]}
    last = stages.get("S8a") or funnel["stages"][-1]
    return (f"{last.get('count')} {last.get('unit')}s on {last.get('prs')} PRs survive stage {last.get('id')} "
            f"(a funnel, not per-candidate rows)")


def _stage_part(result: dict[str, Any], failed: int) -> str:
    rows = result["rows"]
    qualify = sum(bool(r.get("qualifies")) for r in rows)
    excluded = sum(r.get("failure_reason") == _EXCLUDED for r in rows)
    summary = result.get("summary") or {}
    for key, n in (("comments", len(rows)), ("qualifying", qualify), ("failed", failed), ("excluded_judges_disagree", excluded)):
        if key in summary and summary[key] != n:
            raise ValueError(f"{result['stage']} result: its summary says {key} = {summary[key]}, its rows give {n}")
    st = result["stage"]
    return (f"of the {len(rows)} sampled for {st}, {qualify} qualify, {failed} fail (in this ledger with stage {st} and "
            f"their reasons) and {excluded} are excluded because the judges disagree")


def ledger_note(screened: list[dict[str, Any]], funnels: Sequence[tuple[str, dict]] = (),
                stages: Sequence[tuple[str, dict]] = (), failed: dict[tuple[str, str], int] | None = None,
                s10: dict[str, Any] | None = None) -> str:
    """One clause per population: what its screening rows, funnels and stage results record."""
    failed = failed or {}
    pops: dict[str, dict[str, Any]] = {}

    def pop(name: str) -> dict[str, Any]:
        return pops.setdefault(name, {"sources": [], "revisions": set(), "parts": [], "rows": Counter()})

    for row in sorted(screened, key=lambda r: str((r.get("screening") or {}).get("method", "unrecorded"))):
        p = pop(str(row.get("population")))
        p["rows"][str(row.get("eligibility"))] += 1
        p["sources"].append(str((row.get("screening") or {}).get("method", "unrecorded")))
        p["revisions"].add(str(row.get("source_revision") or "unrecorded")[:8])
    judged = {(str(s.get("population")), s["stage"]) for _, s in stages}
    for _, f in funnels:
        p = pop(str(f.get("population")))
        p["sources"].append(str(f.get("generator")))
        p["revisions"].add(str((f.get("source") or {}).get("revision"))[:8])
        p["parts"].append(_funnel_part(f))
        sample = f.get("sample") or {}
        if sample.get("stage") and (str(f.get("population")), sample["stage"]) not in judged:
            p["parts"].append(f"its {sample['stage']} sample of {sample.get('size')} has no result in this ledger yet")
    for name, s in stages:
        p = pop(str(s.get("population")))
        p["sources"].append(name)
        p["parts"].append(_stage_part(s, failed.get((str(s.get("population")), s["stage"]), 0)))
    if s10 is not None:
        p = pop(str(s10.get("population")))
        p["sources"].append(NATURAL_INDEX)
        p["parts"].append(_s10_part(s10, failed.get((str(s10.get("population")), "S10"), 0)))
    parts = []
    for name, p in sorted(pops.items()):
        c = p["rows"]
        said = [f"{sum(c.values())} screened, {c['rejected']} rejected, {c['pending_review']} pending review, "
                f"{c['eligible']} eligible"] if c else []
        parts.append(f"{name} ({', '.join(dict.fromkeys(p['sources']))}; source revision "
                     f"{', '.join(sorted(p['revisions'] - {'None'}) or ['unrecorded'])}): " + ", and ".join(said + p["parts"]))
    if "natural:pr-review" not in pops:
        parts.append("natural:pr-review (AIDev v5): not screened yet")
    parts.append("SWE-chat: not screened (its dataset terms await the owner, D4)")
    return "Natural-data screening (decision log D47): " + "; ".join(parts) + "."


def build(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The provenance index and the rejection ledger of the repository at ``root``."""
    index, ledger = [], []
    for p in sorted((root / "tasks").glob("*/provenance.json")):
        d = json.loads(p.read_text())
        task = json.loads((p.parent / "task.json").read_text())
        row = {k: (_triage(p.parent, d) if k == "triage" else d.get(k)) for k in _FIELDS}
        row["task_status"] = task["status"]
        index.append(row)
        if d["eligibility"] == "rejected":
            ledger.append({"source_id": d["source_id"], "population": d["population"], "reasons": d["rejection_reasons"]})
    # Sessions screened outside tasks/ (natural-data screening), one row each.
    manifests = root / "data" / "manifests"
    extra = manifests / "screening_natural.json"
    screened = json.loads(extra.read_text()) if extra.exists() else []
    funnels, stages = screening_files(manifests) if manifests.is_dir() else ([], [])
    for row in screened:
        index.append(row)
        if row.get("eligibility") == "rejected":
            ledger.append({"source_id": row.get("source_id"), "population": row.get("population"),
                           "reasons": row.get("rejection_reasons")})
    failed: dict[tuple[str, str], int] = {}
    for _, s in stages:
        rows = stage_rejections(s)
        failed[(str(s.get("population")), s["stage"])] = len(rows)
        ledger += rows
    s10 = json.loads((manifests / NATURAL_INDEX).read_text(encoding="utf-8")) if (manifests / NATURAL_INDEX).is_file() else None
    if s10 is not None:
        rows = s10_rejections(s10)
        failed[(str(s10.get("population")), "S10")] = len(rows)
        ledger += rows
    by_pop: dict[str, Counter] = {}
    for row in index:
        c = by_pop.setdefault(row["population"], Counter())
        c["screened"] += 1
        c[row["eligibility"]] += 1
        c["accepted" if row.get("task_status") == "accepted" else "not_accepted"] += 1
    return ({"records": index, "yield_by_population": {k: dict(v) for k, v in by_pop.items()}},
            {"rejections": ledger, "note": ledger_note(screened, funnels, stages, failed, s10)})


def main() -> None:
    index, ledger = build(R)
    out = R / "data" / "manifests"
    out.mkdir(parents=True, exist_ok=True)
    (out / "provenance_index.json").write_text(json.dumps(index, indent=2) + "\n")
    (out / "rejection_ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
    print(json.dumps(index["yield_by_population"]))


if __name__ == "__main__":
    main()
