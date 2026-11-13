"""Analysis of recorded evaluation runs (tables are generated from records only).

Inputs: ``results/runs/<run_id>/results.jsonl`` + ``manifest.json`` and the task
directories (candidate labels, reference contracts). Output:
``analysis.json`` and ``analysis.md`` in the run directory.

Label policy:
* primary: final human labels only (``Candidate.final_label``);
* ``allow_proposed=True`` (automated pilot): fall back to the latest proposed label
  (model / construction). Every table produced this way is marked as an automated
  pilot and must not be described as validated ground truth.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .metrics import Row, paired_difference, summarize
from .schemas import Candidate, CandidateOrigin, TaskContract, TaskManifest, VerificationResult
from .store import load, read_jsonl, write_json

COMPARISONS = [
    ("initial_plain", "full_plain", "information lost: initial-only vs correction-aware contract (plain tests)"),
    ("initial_audited", "full_audited", "information lost: initial-only vs correction-aware contract (audited tests)"),
    ("initial_plain", "initial_audited", "audit effect, initial-only contract"),
    ("full_plain", "full_audited", "audit effect, correction-aware contract"),
    ("llm_freeform", "full_audited", "full-session LLM baseline vs structured contract + audit"),
    ("llm_freeform", "full_plain", "full-session LLM baseline vs structured contract (plain)"),
    ("repo_tests", "full_audited", "repository tests vs structured contract + audit"),
]
CONDITION_ORDER = ["initial_plain", "initial_audited", "full_plain", "full_audited", "llm_freeform", "repo_tests"]


def _negative_type(c: Candidate, label, ref: TaskContract | None, first_prompt_id: str | None) -> str:
    if label is None or label.value != "invalid":
        return ""
    if c.origin == CandidateOrigin.noop:
        return "noop"
    if not label.violated_requirements or ref is None:
        return "unspecified"
    later = []
    for rid in label.violated_requirements:
        try:
            r = ref.by_id(rid)
        except KeyError:
            continue
        later.append(r.introduced_at != first_prompt_id)
    return "correction_violating" if any(later) else "initial_violating"


def build_rows(run_dir: Path, tasks_root: Path, *, allow_proposed: bool) -> tuple[list[Row], dict]:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    results = read_jsonl(run_dir / "results.jsonl", VerificationResult)
    meta: dict = {"label_policy": "proposed labels allowed (automated pilot)" if allow_proposed else "human labels only",
                  "tasks": {}}
    cands: dict[tuple[str, str], Candidate] = {}
    fam: dict[str, str] = {}
    refs: dict[str, TaskContract | None] = {}
    first: dict[str, str | None] = {}
    conditions: dict[tuple[str, str], str] = {}
    for t in manifest["tasks"]:
        tid = t["task_id"]
        tdir = tasks_root / tid
        m = load(tdir / "task.json", TaskManifest)
        fam[tid] = m.family_id
        for p in m.candidates:
            c = load(tdir / p, Candidate)
            cands[(tid, c.candidate_id)] = c
        refp = tdir / m.contracts.get("reference", "contracts/reference.json")
        refs[tid] = load(refp, TaskContract) if refp.exists() else None
        first[tid] = None
        if refs[tid] is not None and refs[tid].requirements:
            intro = sorted({r.introduced_at for r in refs[tid].requirements})
            first[tid] = intro[0]
        for vid, v in t["verifiers"].items():
            conditions[(tid, vid)] = v["condition"]
    rows: list[Row] = []
    for r in results:
        c = cands.get((r.task_id, r.candidate_id))
        if c is None:
            continue
        label = c.final_label() or (c.proposed_label() if allow_proposed else None)
        rows.append(Row(task_id=r.task_id, family_id=fam[r.task_id], candidate_id=r.candidate_id,
                        condition=conditions.get((r.task_id, r.verifier_id), r.verifier_id), outcome=r.outcome.value,
                        label=label.value if label else None, origin=c.origin.value,
                        negative_type=_negative_type(c, label, refs[r.task_id], first[r.task_id])))
    meta["n_results"] = len(results)
    return rows, meta


def analyze(run_dir: Path, tasks_root: Path, *, allow_proposed: bool = False, n_boot: int = 2000,
            exclude_origins: tuple[str, ...] = ("reference", "noop")) -> dict:
    rows, meta = build_rows(run_dir, tasks_root, allow_proposed=allow_proposed)
    # The reference solution is development data for every generator (it is shown to
    # them) and the no-op is a sanity check; both are reported separately and excluded
    # from the primary FA/FR (pre-specified in experiments/protocol.md).
    primary = [r for r in rows if r.origin not in exclude_origins]
    conds = [c for c in CONDITION_ORDER if any(r.condition == c for r in rows)]
    out: dict = {"meta": meta, "conditions": {}, "comparisons": [], "sanity": {}, "by_negative_type": {},
                 "outcome_counts": {}, "per_task": {}}
    for c in conds:
        s = summarize(primary, condition=c, n_boot=n_boot)
        sx = summarize(primary, condition=c, exclude_infra=True, n_boot=n_boot)
        out["conditions"][c] = {
            "false_acceptance": {"rate": s.fa.value, "num": s.fa.num, "den": s.fa.den, "ci95": s.fa_ci, "macro": s.fa_macro},
            "false_rejection": {"rate": s.fr.value, "num": s.fr.num, "den": s.fr.den, "ci95": s.fr_ci, "macro": s.fr_macro},
            "infrastructure": {"num": s.infra.num, "den": s.infra.den},
            "excluded_unlabeled_or_ambiguous": s.excluded_unlabeled,
            "sensitivity_excluding_infra": {"fa": sx.fa.value, "fa_den": sx.fa.den, "fr": sx.fr.value, "fr_den": sx.fr.den},
        }
        out["outcome_counts"][c] = dict(Counter(r.outcome for r in rows if r.condition == c))
        for nt in ("correction_violating", "initial_violating", "unspecified"):
            sub = [r for r in primary if r.condition == c and r.negative_type == nt]
            if sub:
                acc = sum(r.outcome == "pass" for r in sub)
                out["by_negative_type"].setdefault(c, {})[nt] = {"accepted": acc, "n": len(sub)}
        sanity = {}
        for origin in exclude_origins:
            sub = [r for r in rows if r.condition == c and r.origin == origin]
            if sub:
                sanity[origin] = {"pass": sum(r.outcome == "pass" for r in sub), "n": len(sub),
                                  "outcomes": dict(Counter(r.outcome for r in sub))}
        out["sanity"][c] = sanity
    for a, b, desc in COMPARISONS:
        if a in conds and b in conds:
            for metric in ("fa", "fr"):
                d = paired_difference(primary, a, b, metric, n_boot=n_boot)
                d["description"] = desc
                out["comparisons"].append(d)
    tasks = sorted({r.task_id for r in rows})
    for t in tasks:
        out["per_task"][t] = {}
        for c in conds:
            sub = [r for r in primary if r.task_id == t and r.condition == c]
            out["per_task"][t][c] = [{"candidate": r.candidate_id, "origin": r.origin, "label": r.label,
                                      "negative_type": r.negative_type, "outcome": r.outcome} for r in sub]
    out["n_tasks"] = len(tasks)
    out["n_families"] = len({r.family_id for r in rows})
    write_json(out, run_dir / "analysis.json")
    (run_dir / "analysis.md").write_text(to_markdown(out), encoding="utf-8")
    return out


def _fmt(rate, num, den, ci=None) -> str:
    if rate is None:
        return f"n/a (0/{den})"
    s = f"{rate:.2f} ({num}/{den})"
    if ci:
        s += f" [{ci[0]:.2f}, {ci[1]:.2f}]"
    return s


def to_markdown(a: dict) -> str:
    lines = [f"# Analysis ({a['meta']['label_policy']})", "",
             f"Tasks: {a['n_tasks']} | independent task families: {a['n_families']} | results: {a['meta']['n_results']}", ""]
    if "automated pilot" in a["meta"]["label_policy"]:
        lines += ["> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth. "
                  "With this few task families the intervals are not meaningful evidence of an effect.", ""]
    lines += ["## False acceptance / false rejection by condition", "",
              "Rates with (numerator/denominator) and 95% cluster-bootstrap interval over task families where computable. "
              "Reference solution and no-op are excluded (see sanity table).", "",
              "| Condition | False acceptance | False rejection | Infra outcomes | Excluded (unlabeled/ambiguous) |",
              "| --- | --- | --- | --- | --- |"]
    for c, d in a["conditions"].items():
        fa, fr = d["false_acceptance"], d["false_rejection"]
        lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], fa['ci95'])} | {_fmt(fr['rate'], fr['num'], fr['den'], fr['ci95'])} | "
                     f"{d['infrastructure']['num']}/{d['infrastructure']['den']} | {d['excluded_unlabeled_or_ambiguous']} |")
    lines += ["", "## Accepted negatives by type", "", "| Condition | correction-violating | initial-violating | unspecified |", "| --- | --- | --- | --- |"]
    for c in a["conditions"]:
        bt = a["by_negative_type"].get(c, {})
        cell = lambda k: f"{bt[k]['accepted']}/{bt[k]['n']}" if k in bt else "-"  # noqa: E731
        lines.append(f"| {c} | {cell('correction_violating')} | {cell('initial_violating')} | {cell('unspecified')} |")
    lines += ["", "## Sanity checks (excluded from primary metrics)", "", "| Condition | reference passes | no-op passes |", "| --- | --- | --- |"]
    for c, s in a["sanity"].items():
        ref = s.get("reference", {})
        noop = s.get("noop", {})
        lines.append(f"| {c} | {ref.get('pass', '-')}/{ref.get('n', '-')} | {noop.get('pass', '-')}/{noop.get('n', '-')} |")
    lines += ["", "## Paired comparisons (same candidates)", "",
              "| A | B | Metric | A - B | 95% CI | n candidates | families | A acc & B rej | A rej & B acc |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for d in a["comparisons"]:
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]"
        lines.append(f"| {d['a']} | {d['b']} | {d['metric'].upper()} | {diff} | {ci} | {d['n_common']} | {d['n_families']} | "
                     f"{d['discordant']['a_accepts_b_rejects']} | {d['discordant']['a_rejects_b_accepts']} |")
    lines += ["", "## Per-task outcomes", ""]
    for t, conds in a["per_task"].items():
        lines += [f"### {t}", "", "| Candidate | Origin | Label | Negative type | " + " | ".join(conds) + " |",
                  "| --- | --- | --- | --- | " + " | ".join("---" for _ in conds) + " |"]
        cands = {}
        for c, rs in conds.items():
            for r in rs:
                cands.setdefault(r["candidate"], {"origin": r["origin"], "label": r["label"], "nt": r["negative_type"]})[c] = r["outcome"]
        for cid, d in sorted(cands.items()):
            lines.append(f"| {cid} | {d['origin']} | {d['label']} | {d['nt'] or '-'} | " + " | ".join(d.get(c, "-") for c in conds) + " |")
        lines.append("")
    return "\n".join(lines) + "\n"
