"""Pair-by-pair agreement between two evaluation runs (test-retest / harness reliability).

Usage: python scripts/compare_runs.py results/runs/<old> results/runs/<new>
Writes <new>/compare_<old>.json and .md. A pair is a (verifier, candidate) graded in
both runs. Agreement is reported on reward (pass vs non-pass) and on the exact outcome,
separately for pairs whose verifier is unchanged between the runs (same version, test
content hash and scored check list: the check-list hash when both run manifests record
it, otherwise the number of scored checks) and for pairs whose verifier changed (for
example B1 re-selection, decision log D31). Every discordant pair is listed with both
runs' diagnostics.

Natural runs (build plan WP-H; protocol §17.4): when either run is a natural PR-review run
(:func:`is_natural`), the comparison holds outcomes and rewards only. Its output names each
pair by its ids and gives both runs' outcome and reward: no diagnostics, check ids, harness
versions or times, since a natural run's diagnostics and check ids carry upstream code. A
published natural run (``scripts/publish_natural_run.py``) has no ``results.jsonl``; its
``results_public.jsonl`` is read instead, and its check counts stand for the number of checks.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
NATURAL_RUNS = REPO / "data" / "natural" / "runs"
NATURAL_TASKS = "data/natural/"
NATURAL_PREFIX = "natural-"  # a natural run's name (scripts/publish_natural_run.py RUN_PREFIX)


def results_file(run: Path) -> Path:
    """``results.jsonl``, or for a published natural run without one, ``results_public.jsonl``."""
    private, public = run / "results.jsonl", run / "results_public.jsonl"
    return public if not private.is_file() and public.is_file() else private


def load(run: Path) -> dict[tuple[str, str], dict]:
    out = {}
    for line in results_file(run).read_text().split("\n"):  # JSON Lines: line feeds only
        if not line.strip():
            continue
        r = json.loads(line)
        out[(r["verifier_id"], r["candidate_id"])] = r
    return out


def verifiers(run: Path) -> dict[str, dict]:
    m = json.loads((run / "manifest.json").read_text())
    return {vid: v for t in m["tasks"] for vid, v in [(f"{t['task_id']}/{k}", v) for k, v in t["verifiers"].items()]}


def is_natural(run: Path) -> bool:
    """A natural run, whose diagnostics and check ids carry third-party code: it lies under ``data/natural/runs``; its
    name or its manifest's ``run_id`` starts with ``natural-`` (the prefix that ``scripts/publish_natural_run.py``
    requires and the ``.gitignore`` rules match); or a task of its manifest is a natural one: a candidate of origin
    ``natural_pre_review``, a ``task_dir`` under ``data/natural/``, or a natural population
    (:func:`tracecontract.natural_privacy.is_natural_population`: ``natural`` or ``natural:*``) in the ``task.json`` or
    ``session.json`` at its ``task_dir``, or, for a task graded from outside the repository (``task_dir`` null), at
    ``data/natural/tasks/<task id>``."""
    from tracecontract.natural_privacy import is_natural_population, task_population

    real = run.resolve()
    if real == NATURAL_RUNS.resolve() or NATURAL_RUNS.resolve() in real.parents or run.name.startswith(NATURAL_PREFIX):
        return True
    try:
        m = json.loads((run / "manifest.json").read_text())
    except (OSError, ValueError):
        return False
    if not isinstance(m, dict):
        return False
    if str(m.get("run_id") or "").startswith(NATURAL_PREFIX):
        return True
    for t in m.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        cands = t.get("candidates") if isinstance(t.get("candidates"), dict) else {}
        if any(isinstance(c, dict) and c.get("origin") == "natural_pre_review" for c in cands.values()):
            return True
        td = t.get("task_dir") or ""
        if td.startswith(NATURAL_TASKS):
            return True
        tdir = REPO / td if td else REPO / NATURAL_TASKS / "tasks" / str(t.get("task_id") or "")
        if tdir.is_dir() and is_natural_population(task_population(tdir)):
            return True
    return False


def n_checks(r: dict[str, Any]) -> int:
    """The number of checks of a result line: its checks, or a public line's check counts."""
    if "checks" in r:
        return len(r["checks"])
    return sum((r.get("check_counts") or {}).values())


def main(old_dir: str, new_dir: str) -> None:
    old_p, new_p = Path(old_dir), Path(new_dir)
    natural = is_natural(old_p) or is_natural(new_p)
    old, new = load(old_p), load(new_p)
    vo, vn = verifiers(old_p), verifiers(new_p)
    common = sorted(set(old) & set(new))
    reward_disc, outcome_disc = [], []
    changed_verifier = []
    criteria: Counter = Counter()
    for k in common:
        a, b = old[k], new[k]
        key = f"{a['task_id']}/{k[0]}"
        oa, ob = vo.get(key, {}), vn.get(key, {})
        if oa.get("checks_sha256") and ob.get("checks_sha256"):
            criteria["check-list hash"] += 1
            same_checks = oa["checks_sha256"] == ob["checks_sha256"]
        else:
            criteria["number of checks"] += 1
            same_checks = n_checks(a) == n_checks(b)
        same = oa.get("version") == ob.get("version") and oa.get("content_sha256") == ob.get("content_sha256") and same_checks
        if not same:
            changed_verifier.append({"verifier_id": k[0], "candidate_id": k[1], "old": a["outcome"], "new": b["outcome"],
                                     "old_version": oa.get("version"), "new_version": ob.get("version"),
                                     "old_n_checks": n_checks(a), "new_n_checks": n_checks(b)})
            continue
        if natural:  # outcomes and rewards only
            row = {"verifier_id": k[0], "candidate_id": k[1], "old": a["outcome"], "new": b["outcome"],
                   "old_reward": a.get("reward"), "new_reward": b.get("reward")}
        else:
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
        "check_list_criterion": dict(criteria),
        "changed_verifier_reward_agreement": (sum((c["old"] == "pass") == (c["new"] == "pass") for c in changed_verifier)
                                              / len(changed_verifier)) if changed_verifier else None,
        "changed_verifier_pairs": changed_verifier,
        "only_in_old": len(set(old) - set(new)), "only_in_new": len(set(new) - set(old)),
        "reward_agreement": (n - len(reward_disc)) / n if n else None,
        "outcome_agreement": (n - len(outcome_disc)) / n if n else None,
        "reward_discordant": reward_disc, "outcome_discordant": outcome_disc,
    }
    if natural:
        summary["natural"] = "outcomes and rewards only: no diagnostics, check ids, harness versions or times"
    (new_p / f"compare_{old_p.name}.json").write_text(json.dumps(summary, indent=2) + "\n")
    md = [f"# Run comparison: {old_p.name} vs {new_p.name}", "",
          f"Pairs graded in both runs: {len(common)} (only in {old_p.name}: {summary['only_in_old']}, only in {new_p.name}: {summary['only_in_new']}).",
          f"Pairs with an unchanged verifier: {n}; pairs whose verifier changed between the runs: {len(changed_verifier)}.",
          "Scored check lists compared by: " + ", ".join(f"{k} ({v} pairs)" for k, v in criteria.items()) + ".", "",
          f"* Reward agreement on unchanged-verifier pairs (pass vs non-pass): {n - len(reward_disc)}/{n}",
          f"* Exact-outcome agreement on unchanged-verifier pairs: {n - len(outcome_disc)}/{n}",
          f"* Changed-verifier pairs with the same reward: {sum((c['old'] == 'pass') == (c['new'] == 'pass') for c in changed_verifier)}/{len(changed_verifier)}", ""]
    if natural:
        md += ["A natural run: outcomes and rewards only (no diagnostics, check ids, harness versions or times).", "",
               "| Verifier | Candidate | " + old_p.name + " | " + new_p.name + " |", "| --- | --- | --- | --- |"]
        for c in changed_verifier:
            md.append(f"| {c['verifier_id']} (v{c['old_version']}, {c['old_n_checks']} checks -> v{c['new_version']}, "
                      f"{c['new_n_checks']} checks; verifier changed) | {c['candidate_id']} | {c['old']} | {c['new']} |")
        for r in outcome_disc:
            md.append(f"| {r['verifier_id']} | {r['candidate_id']} | {r['old']} (reward {r['old_reward']}) | "
                      f"{r['new']} (reward {r['new_reward']}) |")
    else:
        md += ["| Verifier | Candidate | " + old_p.name + " | " + new_p.name + " | Diagnostics (old -> new) |",
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
