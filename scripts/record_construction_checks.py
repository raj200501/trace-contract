"""Record independent construction checks (protocol v0.3 §11; advisory evidence only).

Reads the journals of held-out workflow runs, takes every checker result
(``check:*`` agents) and writes ``<tasks root>/<task>/labels/construction_checks.json``:
``{"checks": {candidate_id: {assessed_label, violated_requirements, regressions,
matches_claim, claim, plausible, evidence, checker, source}}}``. Two checker formats
are normalised: verdict-based (near miss: confirmed / violates_more_than_claimed /
not_confirmed; alternative: confirmed / not_confirmed) and assessed-label based. A
natural PR-review task's pre-review state is read as a near miss is (its source-evidence
claim is "invalid"). Labels are never changed.

``--tasks-root`` is the directory that holds the task directories: ``tasks/`` by default,
``data/natural/tasks`` for the natural arm, whose checks stay there (git-ignored, §17.4).
Every checked candidate must have its file under that root, and no record is written
through a symbolic link (``labels/`` or ``labels/construction_checks.json``, which could
lead into a tracked directory); nothing is written otherwise.

Usage: python scripts/record_construction_checks.py <workflow transcript dir> [...] [--tasks-root DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
TASKS_ROOT = R / "tasks"


def origin_of(cid: str, tasks_root: Path = TASKS_ROOT) -> tuple[str, str]:
    task = "-".join(cid.split("-")[:2])
    path = tasks_root / task / "candidates" / f"{cid}.json"
    if not path.is_file():
        raise SystemExit(f"record_construction_checks refused, nothing written: candidate {cid} has no file under {tasks_root} "
                         "(--tasks-root data/natural/tasks for a natural PR-review task)")
    c = json.loads(path.read_text())
    return task, c["origin"]


def normalise(chk: dict, origin: str) -> dict:
    if "assessed_label" in chk:
        return {k: chk.get(k) for k in ("assessed_label", "violated_requirements", "regressions", "matches_claim", "claim", "plausible", "evidence")}
    v, viol = chk.get("verdict"), chk.get("violated_requirements", [])
    if origin == "valid_alternative":
        assessed = {"confirmed": "valid", "not_confirmed": "invalid", "violates_more_than_claimed": "invalid"}.get(v or "", "unsure")
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


def main(*dirs: str, tasks_root: Path | str = TASKS_ROOT) -> None:
    root = Path(tasks_root).resolve()
    per_task: dict[str, dict] = {}
    for d in dirs:
        journal = Path(d) / "journal.jsonl"
        entries = [json.loads(line) for line in journal.read_text().split("\n") if line.strip()]  # JSON Lines: line feeds only
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
                task, origin = origin_of(chk["candidate_id"], root)
                rec = normalise(chk, origin)
                rec.update({"checker": f"model:claude-code-subagent:{e.get('label')}", "source": f"{Path(d).name}/{e.get('agentId')}"})
                per_task.setdefault(task, {})[chk["candidate_id"]] = rec
    for task in sorted(per_task):  # links, for every task before anything is written
        out = root / task / "labels" / "construction_checks.json"
        link = next((p for p in (out.parent, out) if p.is_symlink()), None)
        if link is not None:
            raise SystemExit(f"record_construction_checks refused, nothing written: {link} is a symbolic link; the record is "
                             "not written through it")
    for task, checks in sorted(per_task.items()):  # every candidate was found under the root before anything is written
        out = root / task / "labels" / "construction_checks.json"
        prev = json.loads(out.read_text()).get("checks", {}) if out.exists() else {}
        prev.update(checks)
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps({"note": "Independent construction checks (advisory evidence for human review; never change labels).",
                                   "checks": dict(sorted(prev.items()))}, indent=2) + "\n")
        print(task, len(checks), "checks recorded:", {k: v["assessed_label"] for k, v in sorted(checks.items())})


def cli(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dirs", nargs="+", metavar="DIR", help="a held-out workflow run's transcript directory (journal.jsonl)")
    ap.add_argument("--tasks-root", default=str(TASKS_ROOT), help="the directory holding the task directories (default: "
                    "tasks/; data/natural/tasks for the natural arm)")
    a = ap.parse_args(argv)
    main(*a.dirs, tasks_root=a.tasks_root)


if __name__ == "__main__":
    cli()
