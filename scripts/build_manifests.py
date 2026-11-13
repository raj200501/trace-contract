"""Build data/manifests/{provenance_index,rejection_ledger}.json from task provenance records.

Every screened session appears in the index (accepted, pending, or rejected), so that
valid-task yield is always reported over ALL screened sessions, by population.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

R = Path(__file__).resolve().parents[1]


def main() -> None:
    index, ledger = [], []
    for p in sorted((R / "tasks").glob("*/provenance.json")):
        d = json.loads(p.read_text())
        task = json.loads((p.parent / "task.json").read_text())
        row = {k: d.get(k) for k in ("record_id", "session_id", "population", "source_id", "repo_url", "base_commit",
                                     "licenses", "permission_basis", "trace_sha256", "snapshot_manifest_sha256",
                                     "capture_method", "redaction_status", "task_family_id", "eligibility",
                                     "rejection_reasons", "accessed")}
        row["task_status"] = task["status"]
        index.append(row)
        if d["eligibility"] == "rejected":
            ledger.append({"source_id": d["source_id"], "population": d["population"], "reasons": d["rejection_reasons"]})
    # Sessions screened outside tasks/ (e.g. natural-data screening) are appended here when they exist.
    extra = R / "data" / "manifests" / "screening_natural.json"
    if extra.exists():
        for row in json.loads(extra.read_text()):
            index.append(row)
            if row.get("eligibility") == "rejected":
                ledger.append({"source_id": row.get("source_id"), "population": row.get("population"), "reasons": row.get("rejection_reasons")})
    by_pop = {}
    for row in index:
        c = by_pop.setdefault(row["population"], Counter())
        c["screened"] += 1
        c[row["eligibility"]] += 1
        c["accepted" if row.get("task_status") == "accepted" else "not_accepted"] += 1
    out = R / "data" / "manifests"
    out.mkdir(parents=True, exist_ok=True)
    (out / "provenance_index.json").write_text(json.dumps({"records": index, "yield_by_population": {k: dict(v) for k, v in by_pop.items()}}, indent=2) + "\n")
    (out / "rejection_ledger.json").write_text(json.dumps({"rejections": ledger, "note": "Natural-data screening has not started (SWE-chat access blocked)."}, indent=2) + "\n")
    print(json.dumps({k: dict(v) for k, v in by_pop.items()}))


if __name__ == "__main__":
    main()
