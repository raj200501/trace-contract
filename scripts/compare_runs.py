"""Pair-by-pair agreement between two evaluation runs (test-retest / harness reliability).

Usage: python scripts/compare_runs.py results/runs/<old> results/runs/<new>
Writes <new>/compare_<old>.json and .md. A pair is a (verifier, candidate) graded in
both runs. Agreement is reported on reward (pass vs non-pass) and on the exact outcome;
every discordant pair is listed with both runs' diagnostics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(run: Path) -> dict[tuple[str, str], dict]:
    out = {}
    for line in (run / "results.jsonl").read_text().splitlines():
        r = json.loads(line)
        out[(r["verifier_id"], r["candidate_id"])] = r
    return out


def main(old_dir: str, new_dir: str) -> None:
    old_p, new_p = Path(old_dir), Path(new_dir)
    old, new = load(old_p), load(new_p)
    common = sorted(set(old) & set(new))
    reward_disc, outcome_disc = [], []
    for k in common:
        a, b = old[k], new[k]
        row = {"verifier_id": k[0], "candidate_id": k[1], "old": a["outcome"], "new": b["outcome"],
               "old_harness": a.get("harness_version"), "new_harness": b.get("harness_version"),
               "old_diagnostics": a.get("diagnostics", [])[:4], "new_diagnostics": b.get("diagnostics", [])[:4],
               "old_wall_s": round(a.get("wall_s") or 0, 1), "new_wall_s": round(b.get("wall_s") or 0, 1)}
        if (a["outcome"] == "pass") != (b["outcome"] == "pass"):
            reward_disc.append(row)
        if a["outcome"] != b["outcome"]:
            outcome_disc.append(row)
    n = len(common)
    summary = {
        "old_run": old_p.name, "new_run": new_p.name, "pairs_in_both": n,
        "only_in_old": len(set(old) - set(new)), "only_in_new": len(set(new) - set(old)),
        "reward_agreement": (n - len(reward_disc)) / n if n else None,
        "outcome_agreement": (n - len(outcome_disc)) / n if n else None,
        "reward_discordant": reward_disc, "outcome_discordant": outcome_disc,
    }
    (new_p / f"compare_{old_p.name}.json").write_text(json.dumps(summary, indent=2) + "\n")
    md = [f"# Run comparison: {old_p.name} vs {new_p.name}", "",
          f"Pairs graded in both runs: {n} (only in {old_p.name}: {summary['only_in_old']}, only in {new_p.name}: {summary['only_in_new']}).", "",
          f"* Reward agreement (pass vs non-pass): {n - len(reward_disc)}/{n}",
          f"* Exact-outcome agreement: {n - len(outcome_disc)}/{n}", "",
          "| Verifier | Candidate | " + old_p.name + " | " + new_p.name + " | Diagnostics (old -> new) |",
          "| --- | --- | --- | --- | --- |"]
    for r in outcome_disc:
        md.append(f"| {r['verifier_id']} | {r['candidate_id']} | {r['old']} ({r['old_wall_s']} s) | {r['new']} ({r['new_wall_s']} s) | "
                  f"{'; '.join(r['old_diagnostics'])[:160]} -> {'; '.join(r['new_diagnostics'])[:160]} |")
    (new_p / f"compare_{old_p.name}.md").write_text("\n".join(md) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if not k.endswith("discordant")}, indent=1))
    for r in outcome_disc:
        print(" ", r["verifier_id"], r["candidate_id"], r["old"], "->", r["new"])


if __name__ == "__main__":
    main(*sys.argv[1:])
