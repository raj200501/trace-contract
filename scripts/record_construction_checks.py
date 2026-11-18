"""Record independent construction checks (protocol v0.3 §11; advisory evidence only).

Reads the journals of held-out workflow runs, takes every checker result
(``check:*`` agents) and writes ``tasks/<task>/labels/construction_checks.json``:
``{"checks": {candidate_id: {assessed_label, violated_requirements, regressions,
matches_claim, claim, plausible, evidence, checker, source}}}``. Two checker formats
are normalised: verdict-based (near miss: confirmed / violates_more_than_claimed /
not_confirmed; alternative: confirmed / not_confirmed) and assessed-label based.
Labels are never changed.

Usage: python scripts/record_construction_checks.py <workflow transcript dir> [...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]


def origin_of(cid: str) -> tuple[str, str]:
    task = "-".join(cid.split("-")[:2])
    c = json.loads((R / "tasks" / task / "candidates" / f"{cid}.json").read_text())
    return task, c["origin"]


def normalise(chk: dict, origin: str) -> dict:
    if "assessed_label" in chk:
        return {k: chk.get(k) for k in ("assessed_label", "violated_requirements", "regressions", "matches_claim", "claim", "plausible", "evidence")}
    v, viol = chk.get("verdict"), chk.get("violated_requirements", [])
    if origin == "valid_alternative":
        assessed = {"confirmed": "valid", "not_confirmed": "invalid", "violates_more_than_claimed": "invalid"}.get(v, "unsure")
        matches = {"valid": "yes", "invalid": "no"}.get(assessed, "unsure")
    else:
        if v in ("confirmed", "violates_more_than_claimed"):
            assessed, matches = "invalid", ("yes" if v == "confirmed" else "no")
        elif v == "not_confirmed":
            assessed, matches = ("invalid" if viol else "valid"), "no"
        else:
            assessed, matches = "unsure", "unsure"
    if chk.get("regressions") and assessed == "valid":
        assessed = "invalid"
    return {"assessed_label": assessed, "violated_requirements": viol, "regressions": chk.get("regressions", []),
            "matches_claim": matches, "claim": chk.get("claimed"), "plausible": chk.get("plausible"),
            "evidence": chk.get("evidence"), "verdict": v}


def main(*dirs: str) -> None:
    per_task: dict[str, dict] = {}
    for d in dirs:
        journal = Path(d) / "journal.jsonl"
        entries = [json.loads(line) for line in journal.read_text().splitlines()]
        labels = {e["agentId"]: e.get("label", "") for e in entries if e.get("type") == "started"}
        for e in entries:
            e["label"] = labels.get(e.get("agentId"), "")
            if e.get("type") != "result" or not e["label"].startswith("check:"):
                continue
            res = e.get("result")
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except json.JSONDecodeError:
                    continue
            for chk in (res or {}).get("checks", []):
                task, origin = origin_of(chk["candidate_id"])
                rec = normalise(chk, origin)
                rec.update({"checker": f"model:claude-code-subagent:{e.get('label')}", "source": f"{Path(d).name}/{e.get('agentId')}"})
                per_task.setdefault(task, {})[chk["candidate_id"]] = rec
    for task, checks in sorted(per_task.items()):
        out = R / "tasks" / task / "labels" / "construction_checks.json"
        prev = json.loads(out.read_text()).get("checks", {}) if out.exists() else {}
        prev.update(checks)
        out.write_text(json.dumps({"note": "Independent construction checks (advisory evidence for human review; never change labels).",
                                   "checks": dict(sorted(prev.items()))}, indent=2) + "\n")
        print(task, len(checks), "checks recorded:", {k: v["assessed_label"] for k, v in sorted(checks.items())})


if __name__ == "__main__":
    main(*sys.argv[1:])
