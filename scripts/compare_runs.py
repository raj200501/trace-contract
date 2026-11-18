"""Pair-by-pair agreement between two evaluation runs (test-retest / harness reliability).

Usage: python scripts/compare_runs.py results/runs/<old> results/runs/<new>
Writes <new>/compare_<old>.json and .md. A pair is a (verifier, candidate) graded in
both runs. Agreement is reported on reward (pass vs non-pass) and on the exact outcome,
separately for pairs whose verifier is unchanged between the runs (same version, test
content hash and number of scored checks) and for pairs whose verifier changed (for
example B1 re-selection, decision log D31). Every discordant pair is listed with both
runs' diagnostics.
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


def verifiers(run: Path) -> dict[str, dict]:
    m = json.loads((run / "manifest.json").read_text())
    return {vid: v for t in m["tasks"] for vid, v in [(f"{t['task_id']}/{k}", v) for k, v in t["verifiers"].items()]}


def main(old_dir: str, new_dir: str) -> None:
    old_p, new_p = Path(old_dir), Path(new_dir)
    old, new = load(old_p), load(new_p)
    vo, vn = verifiers(old_p), verifiers(new_p)
    common = sorted(set(old) & set(new))
    reward_disc, outcome_disc = [], []
    changed_verifier = []
    for k in common:
        a, b = old[k], new[k]
        key = f"{a['task_id']}/{k[0]}"
        oa, ob = vo.get(key, {}), vn.get(key, {})
        same = (oa.get("version") == ob.get("version") and oa.get("content_sha256") == ob.get("content_sha256")
                and len(a.get("checks", [])) == len(b.get("checks", [])))
        if not same:
            changed_verifier.append({"verifier_id": k[0], "candidate_id": k[1], "old": a["outcome"], "new": b["outcome"],
                                     "old_version": oa.get("version"), "new_version": ob.get("version"),
                                     "old_n_checks": len(a.get("checks", [])), "new_n_checks": len(b.get("checks", []))})
            continue
        row = {"verifier_id": k[0], "candidate_id": k[1], "old": a["outcome"], "new": b["outcome"],
               "old_harness": a.get("harness_version"), "new_harness": b.get("harness_version"),
               "old_diagnostics": a.get("diagnostics", [])[:4], "new_diagnostics": b.get("diagnostics", [])[:4],
               "old_wall_s": round(a.get("wall_s") or 0, 1), "new_wall_s": round(b.get("wall_s") or 0, 1)}
        if (a["outcome"] == "pass") != (b["outcome"] == "pass"):
            reward_disc.append(row)
        if a["outcome"] != b["outcome"]:
            outcome_disc.append(row)
    n = len(common) - len(changed_verifier)
    summary = {
        "old_run": old_p.name, "new_run": new_p.name, "pairs_in_both": len(common),
        "pairs_same_verifier": n, "pairs_changed_verifier": len(changed_verifier),
        "changed_verifier_reward_agreement": (sum((c["old"] == "pass") == (c["new"] == "pass") for c in changed_verifier)
                                              / len(changed_verifier)) if changed_verifier else None,
        "changed_verifier_pairs": changed_verifier,
        "only_in_old": len(set(old) - set(new)), "only_in_new": len(set(new) - set(old)),
        "reward_agreement": (n - len(reward_disc)) / n if n else None,
        "outcome_agreement": (n - len(outcome_disc)) / n if n else None,
        "reward_discordant": reward_disc, "outcome_discordant": outcome_disc,
    }
    (new_p / f"compare_{old_p.name}.json").write_text(json.dumps(summary, indent=2) + "\n")
    md = [f"# Run comparison: {old_p.name} vs {new_p.name}", "",
          f"Pairs graded in both runs: {len(common)} (only in {old_p.name}: {summary['only_in_old']}, only in {new_p.name}: {summary['only_in_new']}).",
          f"Pairs with an unchanged verifier: {n}; pairs whose verifier changed between the runs: {len(changed_verifier)}.", "",
          f"* Reward agreement on unchanged-verifier pairs (pass vs non-pass): {n - len(reward_disc)}/{n}",
          f"* Exact-outcome agreement on unchanged-verifier pairs: {n - len(outcome_disc)}/{n}",
          f"* Changed-verifier pairs with the same reward: {sum((c['old'] == 'pass') == (c['new'] == 'pass') for c in changed_verifier)}/{len(changed_verifier)}", "",
          "| Verifier | Candidate | " + old_p.name + " | " + new_p.name + " | Diagnostics (old -> new) |",
          "| --- | --- | --- | --- | --- |"]
    for c in changed_verifier:
        md.append(f"| {c['verifier_id']} (v{c['old_version']}, {c['old_n_checks']} checks -> v{c['new_version']}, {c['new_n_checks']} checks) | "
                  f"{c['candidate_id']} | {c['old']} | {c['new']} | verifier changed |")
    for r in outcome_disc:
        md.append(f"| {r['verifier_id']} | {r['candidate_id']} | {r['old']} ({r['old_wall_s']} s) | {r['new']} ({r['new_wall_s']} s) | "
                  f"{'; '.join(r['old_diagnostics'])[:160]} -> {'; '.join(r['new_diagnostics'])[:160]} |")
    (new_p / f"compare_{old_p.name}.md").write_text("\n".join(md) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if not k.endswith("discordant") and k != "changed_verifier_pairs"}, indent=1))
    for r in outcome_disc:
        print(" ", r["verifier_id"], r["candidate_id"], r["old"], "->", r["new"])


if __name__ == "__main__":
    main(*sys.argv[1:])
