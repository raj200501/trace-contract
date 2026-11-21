"""Build data/manifests/{provenance_index,rejection_ledger}.json from task provenance records
and the natural-data screening rows (data/manifests/screening_natural.json). Screening funnels
(data/manifests/screening_natural_*.json, no per-candidate rows) are summarised in the note.

Every screened session appears in the index (accepted, pending, or rejected), so that
valid-task yield is always reported over ALL screened sessions, by population. The ledger's
note describes the screening state that the rows record (decision log D47).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

R = Path(__file__).resolve().parents[1]
_FIELDS = ("record_id", "session_id", "population", "source_id", "repo_url", "base_commit", "licenses", "permission_basis",
           "trace_sha256", "snapshot_manifest_sha256", "capture_method", "redaction_status", "task_family_id", "eligibility",
           "rejection_reasons", "accessed")


def _funnel_note(funnel: dict[str, Any]) -> str:
    """One clause for a deterministic screening funnel (e.g. screening_natural_aidev.json): no per-session rows."""
    stages = {st.get("id"): st for st in funnel.get("stages", [])}
    last = stages.get("S8a") or (funnel.get("stages") or [{}])[-1]
    sample = funnel.get("sample") or {}
    return (f"{funnel.get('population')} ({funnel.get('generator')}; source revision "
            f"{str((funnel.get('source') or {}).get('revision'))[:8]}): a funnel, not per-candidate rows; "
            f"{last.get('count')} {last.get('unit')}s on {last.get('prs')} PRs survive stage {last.get('id')}, "
            f"sample {sample.get('stage')} of {sample.get('size')}, none in this ledger yet")


def ledger_note(screened: list[dict[str, Any]], funnels: list[dict[str, Any]] = ()) -> str:
    """What the natural screening rows say: per population, how many were screened and their eligibility."""
    by_pop: dict[str, Counter] = {}
    methods: dict[str, set[str]] = {}
    revisions: dict[str, set[str]] = {}
    for row in screened:
        pop = str(row.get("population"))
        by_pop.setdefault(pop, Counter())[str(row.get("eligibility"))] += 1
        methods.setdefault(pop, set()).add(str((row.get("screening") or {}).get("method", "unrecorded")))
        revisions.setdefault(pop, set()).add(str(row.get("source_revision") or "unrecorded")[:8])
    parts = [f"{pop} ({', '.join(sorted(methods[pop]))}; source revision {', '.join(sorted(revisions[pop]))}): "
             f"{sum(c.values())} screened, {c['rejected']} rejected, {c['pending_review']} pending review, "
             f"{c['eligible']} eligible" for pop, c in sorted(by_pop.items())]
    parts += [_funnel_note(f) for f in funnels if f.get("population") not in by_pop]
    if "natural:pr-review" not in by_pop and not any(f.get("population") == "natural:pr-review" for f in funnels):
        parts.append("natural:pr-review (AIDev v5): not screened yet")
    parts.append("SWE-chat: not screened (its dataset terms await the owner, D4)")
    return "Natural-data screening (decision log D47): " + "; ".join(parts) + "."


def build(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The provenance index and the rejection ledger of the repository at ``root``."""
    index, ledger = [], []
    for p in sorted((root / "tasks").glob("*/provenance.json")):
        d = json.loads(p.read_text())
        task = json.loads((p.parent / "task.json").read_text())
        row = {k: d.get(k) for k in _FIELDS}
        row["task_status"] = task["status"]
        index.append(row)
        if d["eligibility"] == "rejected":
            ledger.append({"source_id": d["source_id"], "population": d["population"], "reasons": d["rejection_reasons"]})
    # Sessions screened outside tasks/ (natural-data screening), one row each.
    extra = root / "data" / "manifests" / "screening_natural.json"
    screened = json.loads(extra.read_text()) if extra.exists() else []
    funnels = [json.loads(f.read_text()) for f in sorted((root / "data" / "manifests").glob("screening_natural_*.json"))]
    for row in screened:
        index.append(row)
        if row.get("eligibility") == "rejected":
            ledger.append({"source_id": row.get("source_id"), "population": row.get("population"),
                           "reasons": row.get("rejection_reasons")})
    by_pop: dict[str, Counter] = {}
    for row in index:
        c = by_pop.setdefault(row["population"], Counter())
        c["screened"] += 1
        c[row["eligibility"]] += 1
        c["accepted" if row.get("task_status") == "accepted" else "not_accepted"] += 1
    return ({"records": index, "yield_by_population": {k: dict(v) for k, v in by_pop.items()}},
            {"rejections": ledger, "note": ledger_note(screened, funnels)})


def main() -> None:
    index, ledger = build(R)
    out = R / "data" / "manifests"
    out.mkdir(parents=True, exist_ok=True)
    (out / "provenance_index.json").write_text(json.dumps(index, indent=2) + "\n")
    (out / "rejection_ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
    print(json.dumps(index["yield_by_population"]))


if __name__ == "__main__":
    main()
