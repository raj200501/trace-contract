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
from .schemas import Candidate, CandidateOrigin, LabelerKind, TaskContract, TaskManifest, VerificationResult
from .store import load, read_jsonl, write_json

PILOT_LABELER = "builder:refcheck+regression+construction:v1"  # decision log D19
CONSTRUCTED = (CandidateOrigin.constructed_near_miss, CandidateOrigin.valid_alternative)


def candidate_label(c: Candidate, policy: str):
    """Label used for analysis under a label policy.

    * ``human``: adjudicated / latest human label only (primary analysis).
    * ``pilot``: human label if present, else the pre-specified automated proposal
      (rule D19, labeler ``PILOT_LABELER``); candidates without one are unlabeled.
    * ``construction`` (exploratory, not pre-specified): human label if present, else
      the construction label for constructed candidates and the D19 proposal for the
      others.
    """
    human = c.final_label()
    if human is not None or policy == "human":
        return human
    if policy == "construction" and c.origin in CONSTRUCTED:
        cons = [lb for lb in c.labels if lb.labeler_kind == LabelerKind.construction]
        if cons:
            return cons[-1]
    pilot = [lb for lb in c.labels if lb.labeler == PILOT_LABELER]
    return pilot[-1] if pilot else None

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


def build_rows(run_dir: Path, tasks_root: Path, *, allow_proposed: bool, policy: str | None = None) -> tuple[list[Row], dict]:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    results = read_jsonl(run_dir / "results.jsonl", VerificationResult)
    policy = policy or ("pilot" if allow_proposed else "human")
    meta: dict = {"label_policy": "proposed labels allowed (automated pilot)" if allow_proposed else "human labels only",
                  "label_rule": policy, "tasks": {},
                  "harness_versions": dict(Counter(r.harness_version for r in results))}
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
        label = candidate_label(c, policy)
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
        fa_v, fr_v = s.fa.value, s.fr.value
        out["conditions"][c]["youden_j"] = None if fa_v is None or fr_v is None else (1 - fr_v) - fa_v
        tasks_c = sorted({r.task_id for r in primary if r.condition == c})
        any_neg = [any(r.outcome == "pass" for r in primary if r.condition == c and r.task_id == t and r.label == "invalid")
                   for t in tasks_c if any(r.label == "invalid" for r in primary if r.condition == c and r.task_id == t)]
        out["conditions"][c]["tasks_with_any_accepted_negative"] = {"num": sum(any_neg), "den": len(any_neg)}
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
    if allow_proposed:
        # Exploratory (not pre-specified): constructed candidates labeled by construction intent.
        srows, _ = build_rows(run_dir, tasks_root, allow_proposed=True, policy="construction")
        sprim = [r for r in srows if r.origin not in exclude_origins]
        out["sensitivity_construction_labels"] = {}
        for c in conds:
            ss = summarize(sprim, condition=c, n_boot=n_boot)
            out["sensitivity_construction_labels"][c] = {
                "fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den, "fa_ci95": ss.fa_ci,
                "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den, "fr_ci95": ss.fr_ci}
    out["labels"] = label_summary([tasks_root / t for t in tasks])
    out["coverage"] = {t: contract_coverage(tasks_root / t) for t in tasks}
    out["mapping_agreement"] = {t: mapping_agreement(tasks_root / t) for t in tasks}
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
              "| Condition | False acceptance | False rejection | Youden's J | Tasks with an accepted negative | Infra outcomes | Excluded (unlabeled/ambiguous) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for c, d in a["conditions"].items():
        fa, fr = d["false_acceptance"], d["false_rejection"]
        j = "n/a" if d.get("youden_j") is None else f"{d['youden_j']:+.2f}"
        tn = d.get("tasks_with_any_accepted_negative", {"num": 0, "den": 0})
        lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], fa['ci95'])} | {_fmt(fr['rate'], fr['num'], fr['den'], fr['ci95'])} | {j} | "
                     f"{tn['num']}/{tn['den']} | {d['infrastructure']['num']}/{d['infrastructure']['den']} | {d['excluded_unlabeled_or_ambiguous']} |")
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
    if a.get("sensitivity_construction_labels"):
        lines += ["", "## Exploratory sensitivity: construction-intent labels (not pre-specified)", "",
                  "Constructed candidates labeled by how they were built (near miss = invalid, alternative = valid), "
                  "including those the D19 rule marked ambiguous; natural candidates keep their D19 label.", "",
                  "| Condition | False acceptance | False rejection |", "| --- | --- | --- |"]
        for c, d in a["sensitivity_construction_labels"].items():
            lines.append(f"| {c} | {_fmt(d['fa'], d['fa_num'], d['fa_den'], d['fa_ci95'])} | {_fmt(d['fr'], d['fr_num'], d['fr_den'], d['fr_ci95'])} |")
    if a.get("labels"):
        lines += ["", "## Labels and human-review queue", "", "| Task | valid | invalid | ambiguous | unlabeled | queued for review |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for t, d in a["labels"].items():
            q = ", ".join(x["candidate"] for x in d["review_queue"]) or "-"
            lines.append(f"| {t} | {d['counts'].get('valid', 0)} | {d['counts'].get('invalid', 0)} | {d['counts'].get('ambiguous', 0)} | "
                         f"{d['counts'].get('unlabeled', 0)} | {q} |")
    if a.get("coverage"):
        lines += ["", "## Contract recovery (model mappings, proposals)", "",
                  "| Task | Variant | Coverage of active reference requirements (mapper 1) | Unsupported | Contradicting | Coverage (mapper 2) | Mapping agreement (kappa) |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for t, cov in a["coverage"].items():
            ag = a.get("mapping_agreement", {}).get(t, {})
            for v, d in cov.get("variants", {}).items():
                d2 = cov.get("variants_mapper2", {}).get(v)
                k = ag.get(v, {}).get("kappa")
                lines.append(f"| {t} | {v} | {_fmt(d['coverage'], len(d['covered']), len(cov['reference_scored']))} | "
                             f"{len(d['unsupported'])}/{d['n_recovered_scored']} | {len(d['contradicting'])} | "
                             f"{_fmt(d2['coverage'], len(d2['covered']), len(cov['reference_scored'])) if d2 else '-'} | "
                             f"{'n/a' if k is None else f'{k:.2f}'} |")
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


def _coverage_one(c: TaskContract, mapping: dict, ref_scored: set[str]) -> dict:
    rec = {r.req_id for r in c.active() if r.scored}
    contra = {rid: set(mapping.get("contradicts", {}).get(rid, [])) for rid in rec}
    # A recovered requirement covers a reference requirement it maps to, unless its
    # test would reject solutions satisfying that requirement (a contradiction).
    covered = {x for rid in rec for x in mapping["map"].get(rid, []) if x not in contra[rid]} & ref_scored
    unsupported = sorted(rid for rid in rec if not set(mapping["map"].get(rid, [])) & ref_scored)
    contradicting = sorted(rid for rid in rec if contra[rid] & ref_scored)
    return {"mapper_kind": mapping.get("mapper_kind"), "mapper": mapping.get("mapper"),
            "coverage": len(covered) / len(ref_scored) if ref_scored else None,
            "covered": sorted(covered), "missing": sorted(ref_scored - covered),
            "n_recovered_scored": len(rec), "unsupported": unsupported,
            "unsupported_rate": (len(unsupported) / len(rec)) if rec else None,
            "contradicting": contradicting,
            "superseded_requirements": sorted(r.req_id for r in c.requirements if r.status.value == "superseded" and r.scored)}


def contract_coverage(task_dir: Path) -> dict:
    """Requirement coverage / unsupported / contradicting rates of recovered contracts.

    Reads ``contracts/mapping_<variant>.json`` (mapper 1) and, when present,
    ``contracts/mapping2_<variant>.json`` (an independent second mapper):
    ``{"mapper": ..., "mapper_kind": "human"|"model", "map": {recovered_id: [reference_ids]},
    "contradicts": {recovered_id: [reference_ids]}}``. Model mappings are proposals.
    """
    m = load(task_dir / "task.json", TaskManifest)
    out: dict = {"task_id": m.task_id, "variants": {}, "variants_mapper2": {}}
    if "reference" not in m.contracts or not (task_dir / m.contracts["reference"]).exists():
        out["reference_scored"] = []
        return out
    ref = load(task_dir / m.contracts["reference"], TaskContract)
    ref_scored = {r.req_id for r in ref.active() if r.scored}
    out["reference_scored"] = sorted(ref_scored)
    for variant in ("initial_only", "full_session"):
        if variant not in m.contracts:
            continue
        c = load(task_dir / m.contracts[variant], TaskContract)
        for prefix, key in (("mapping_", "variants"), ("mapping2_", "variants_mapper2")):
            mp = task_dir / "contracts" / f"{prefix}{variant}.json"
            if mp.exists():
                out[key][variant] = _coverage_one(c, json.loads(mp.read_text()), ref_scored)
    return out


def cohen_kappa(a: list[int], b: list[int]) -> float | None:
    """Cohen's kappa for two binary raters over the same units."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1:
        return 1.0 if po == 1 else None
    return (po - pe) / (1 - pe)


def mapping_agreement(task_dir: Path) -> dict:
    """Agreement of the two independent mappers over (recovered, reference) requirement pairs."""
    m = load(task_dir / "task.json", TaskManifest)
    out: dict = {}
    if "reference" not in m.contracts or not (task_dir / m.contracts["reference"]).exists():
        return out
    ref = load(task_dir / m.contracts["reference"], TaskContract)
    ref_ids = sorted(r.req_id for r in ref.requirements)  # include superseded: mappers may map to them
    for variant in ("initial_only", "full_session"):
        p1, p2 = task_dir / "contracts" / f"mapping_{variant}.json", task_dir / "contracts" / f"mapping2_{variant}.json"
        if variant not in m.contracts or not (p1.exists() and p2.exists()):
            continue
        c = load(task_dir / m.contracts[variant], TaskContract)
        rec = sorted(r.req_id for r in c.active() if r.scored)
        m1, m2 = json.loads(p1.read_text()), json.loads(p2.read_text())
        res = {}
        for field in ("map", "contradicts"):
            a = [int(x in m1.get(field, {}).get(rid, [])) for rid in rec for x in ref_ids]
            b = [int(x in m2.get(field, {}).get(rid, [])) for rid in rec for x in ref_ids]
            res[field] = {"units": len(a), "agreement": (sum(x == y for x, y in zip(a, b)) / len(a)) if a else None,
                          "kappa": cohen_kappa(a, b),
                          "disagreements": [f"{rid}->{x}" for rid in rec for x in ref_ids
                                            if (x in m1.get(field, {}).get(rid, [])) != (x in m2.get(field, {}).get(rid, []))]}
        out[variant] = {"kappa": res["map"]["kappa"], "agreement": res["map"]["agreement"], "units": res["map"]["units"],
                        "map": res["map"], "contradicts": res["contradicts"]}
    return out


def label_summary(task_dirs: list[Path]) -> dict:
    """Proposed-label counts per task and the queue of candidates needing human review.

    Queued: candidates the D19 rule marked ambiguous, candidates without a proposal,
    and candidates whose independent construction check disagrees with the proposal
    (``labels/construction_checks.json``, advisory evidence only).
    """
    out: dict = {}
    for tdir in task_dirs:
        m = load(tdir / "task.json", TaskManifest)
        checks_p = tdir / "labels" / "construction_checks.json"
        checks = json.loads(checks_p.read_text()).get("checks", {}) if checks_p.exists() else {}
        counts: Counter = Counter()
        queue, rows = [], []
        for p in m.candidates:
            c = load(tdir / p, Candidate)
            if c.split.value != "eval" or c.origin in (CandidateOrigin.noop, CandidateOrigin.reference):
                continue
            lb = candidate_label(c, "pilot")
            value = lb.value if lb else "unlabeled"
            counts[value] += 1
            chk = checks.get(c.candidate_id)
            row = {"candidate": c.candidate_id, "origin": c.origin.value, "proposed": value,
                   "violated": lb.violated_requirements if lb else []}
            rows.append(row)
            assessed = chk.get("assessed_label") if chk else None
            row["check_assessed"] = assessed
            disagree = value in ("valid", "invalid") and assessed in ("valid", "invalid") and assessed != value
            if value in ("ambiguous", "unlabeled") or disagree:
                queue.append({**row, "reason": "ambiguous under D19" if value == "ambiguous" else
                              ("no proposal" if value == "unlabeled" else "construction check disagrees with proposal")})
        out[m.task_id] = {"counts": dict(counts), "candidates": rows, "review_queue": queue}
    return out
