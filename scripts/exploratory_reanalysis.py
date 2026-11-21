"""Post hoc, exploratory re-analysis of the frozen pilot run, and planning simulations.

Protocol v0.7 §15.1: re-analyses of ``pilot-v0.3.3`` made after 2026-11-21 are post hoc and
exploratory, are reported in ``results/analyses/pilot-v0.3.3-exploratory/`` and never replace the
pre-specified results. The views follow the reporting rules of §15.7: the per-family table is the
primary display; every paired comparison of §7 carries an exact sign-flip randomization p-value
over families with its attainable floor; each distinct graded patch counted once (a separate view,
since the frozen counting is kept for comparability); the oracle-gated view is secondary.

Usage::

    python scripts/exploratory_reanalysis.py [--run results/runs/pilot-v0.3.3]
        [--out results/analyses/pilot-v0.3.3-exploratory] [--no-simulation]

Reads, never writes: the run's ``results.jsonl``, ``manifest.json`` and ``analysis.json`` (for
consistency checks only), ``tasks/<id>/`` (task manifest, candidates, contracts and requirement
mappings, verifier specs, labels) and ``results/audits/``. Writes ``<out>/analysis.json``,
``<out>/analysis.md``, ``<out>/planning_simulation.json`` (``--no-simulation`` reads the existing
file instead), ``paper/generated/exploratory/*.tex`` and ``paper/evidence_ledger_exploratory.md``.
Labels are the automated D19 proposals; no human labels exist. No candidate code is executed.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import platform
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Sequence

from tracecontract.analysis import COMPARISONS, CONDITION_ORDER, _git_revision, _norm_patch, candidate_label, cohen_kappa
from tracecontract.metrics import clopper_pearson
from tracecontract.schemas import Candidate, LabelerKind, TaskContract, TaskManifest, VerifierSpec
from tracecontract.store import load, write_json
from tracecontract.verifier import checks_sha256

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "results" / "runs" / "pilot-v0.3.3"
DEFAULT_OUT = ROOT / "results" / "analyses" / "pilot-v0.3.3-exploratory"
GEN = ROOT / "paper" / "generated" / "exploratory"
LEDGER = ROOT / "paper" / "evidence_ledger_exploratory.md"
TAG = "post hoc, exploratory (not pre-specified)"
PLAN_TAG = "planning simulation for the draft precision plan, not an analysis of pilot outcomes; " + TAG
SHORT = {"initial_plain": "C1", "initial_audited": "C2", "full_plain": "C3", "full_audited": "C4",
         "llm_freeform": "B2", "repo_tests": "B1"}
# Figures recomputed by the design audit of D47 (oracle gate); reproduced in ``oracle_gated``.
DESIGN_AUDIT = {"initial_plain": {"fa": [5, 11], "fr": [0, 8]}, "full_plain": {"fa": [0, 11], "fr": [0, 8]},
                "full_audited": {"fa": [0, 11], "fr": [0, 8]}}
EQUIVALENCE_MARGIN = Fraction(1, 10)
SEED = 20261121

Labeling = Callable[["Cand"], "str | None"]


# ---------------------------------------------------------------- exact statistics

def signflip_counter(ints: Sequence[int]) -> Callable[[int], int]:
    """``ge(t)``: how many of the 2^K sign assignments of ``ints`` give a signed sum >= t.

    The distribution is the generating function prod(x^-v + x^v), packed into one Python integer
    with B = K + 2 bits per coefficient. Coefficients are counts at most 2^K, so they never carry;
    the sum of the coefficients above an exponent is read off modulo 2^B - 1. Exact and fast.
    """
    k = len(ints)
    nz = [abs(x) for x in ints if x]
    zeros, total_v, bits = k - len(nz), sum(nz), k + 2
    poly = 1
    for v in nz:
        poly += poly << (2 * v * bits)
    mask = (1 << bits) - 1

    def ge(t: int) -> int:
        e = t + total_v
        if e <= 0:
            return 1 << k
        if e > 2 * total_v:
            return 0
        return ((poly >> (e * bits)) % mask) << zeros
    return ge


def _integers(values: Sequence[Fraction]) -> list[int]:
    scale = 1
    for v in values:
        scale = math.lcm(scale, Fraction(v).denominator)
    return [int(Fraction(v) * scale) for v in values]


def signflip(values: Sequence[Fraction]) -> dict:
    """Exact sign-flip randomization test of the sum of per-family values over all 2^K assignments.

    H0: each family's value is symmetric about zero (for a paired difference: the two arms are
    exchangeable within the family). ``p_greater`` tests H1: sum > 0, ``p_less`` H1: sum < 0.
    The floor is the smallest p-value K families can give; the conditional floor is the smallest
    one the observed zero-difference families allow (a zero cannot change sign).
    """
    k = len(values)
    if k == 0:
        return {"k": 0, "statistic": None, "p_greater": None, "p_less": None, "p_two_sided": None,
                "floor_one_sided": None, "floor_two_sided": None, "zero_families": 0, "conditional_floor_one_sided": None}
    ints = _integers(values)
    t, total, ge = sum(ints), 1 << k, signflip_counter(ints)
    zeros = sum(1 for x in ints if x == 0)
    return {"k": k, "statistic": float(sum(Fraction(v) for v in values)), "p_greater": ge(t) / total, "p_less": ge(-t) / total,
            "p_two_sided": (min(total, 2 * ge(abs(t))) / total) if t else 1.0,
            "floor_one_sided": 1 / total, "floor_two_sided": min(1.0, 2 / total),
            "zero_families": zeros, "conditional_floor_one_sided": (1 << zeros) / total}


def chi2_cdf(x: float, df: int) -> float:
    """Chi-square CDF: the regularized lower incomplete gamma P(df/2, x/2), by its power series."""
    if x <= 0:
        return 0.0
    a, y = df / 2, x / 2
    term = total = 1 / a
    n = 0
    while term > 1e-16 * total:
        n += 1
        term *= y / (a + n)
        total += term
    return min(1.0, total * math.exp(-y + a * math.log(y) - math.lgamma(a)))


def chi2_ppf(q: float, df: int) -> float:
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if chi2_cdf(mid, df) < q else (lo, mid)
    return (lo + hi) / 2


@lru_cache(maxsize=None)
def cp_upper(k: int, n: int) -> float:
    """One-sided 97.5% Clopper-Pearson upper bound (the upper end of the two-sided 95% interval)."""
    return 1.0 if n == 0 else clopper_pearson(k, n, 0.05)[1]


# ---------------------------------------------------------------- data

@dataclass(frozen=True)
class Cand:
    """A held-out candidate with every labeling this re-analysis uses."""
    task_id: str
    family_id: str
    candidate_id: str
    origin: str
    d19: str | None                      # the pre-specified rule's proposal: valid, invalid or ambiguous
    d19_violated: tuple[str, ...]
    construction: str | None             # construction intent (constructed candidates only)
    construction_violated: tuple[str, ...]
    check: str | None                    # independent construction check (advisory)
    check_violated: tuple[str, ...]
    refcheck: str                        # reference-check verdict: valid when every reference check passes
    regression: bool                     # the regression norm failed
    patch_key: str                       # sha256 of the graded patch (protected paths and index lines removed)


@dataclass
class Pilot:
    run_id: str
    conditions: list[str]
    families: list[str]
    cands: list[Cand]
    outcome: dict[tuple[str, str, str], str]               # (task, condition, candidate) -> outcome
    failed: dict[tuple[str, str, str], frozenset[str]]
    passed: dict[tuple[str, str, str], frozenset[str]]
    reference_id: dict[str, str]
    specs: dict[tuple[str, str], VerifierSpec]
    mappings: dict[tuple[str, str, int], dict]              # (task, contract variant, mapper 1|2)
    upstream: dict[str, frozenset[str]]
    same_code_heldout: dict[str, list[str]]
    audits: dict[str, dict]                                 # file name -> recorded audit
    manifest: dict
    frozen: dict | None
    inputs: dict[str, str]


def _rel(p: Path) -> str:
    return str(p.resolve().relative_to(ROOT)) if p.resolve().is_relative_to(ROOT) else str(p)


def load_pilot(run_dir: Path, tasks_root: Path, audits_dir: Path) -> Pilot:
    inputs: dict[str, str] = {}

    def text(p: Path) -> str:
        data = p.read_bytes()
        inputs[_rel(p)] = hashlib.sha256(data).hexdigest()
        return data.decode("utf-8")

    manifest = json.loads(text(run_dir / "manifest.json"))
    results = [json.loads(x) for x in text(run_dir / "results.jsonl").splitlines() if x.strip()]
    frozen = json.loads(text(run_dir / "analysis.json")) if (run_dir / "analysis.json").exists() else None
    cond_of = {(t["task_id"], vid): v["condition"] for t in manifest["tasks"] for vid, v in t["verifiers"].items()}
    conditions = [c for c in CONDITION_ORDER if c in set(cond_of.values())]
    p = Pilot(run_id=manifest["run_id"], conditions=conditions, families=[], cands=[], outcome={}, failed={}, passed={},
              reference_id={}, specs={}, mappings={}, upstream={}, same_code_heldout={}, audits={}, manifest=manifest,
              frozen=frozen, inputs=inputs)
    for r in results:
        key = (r["task_id"], cond_of[(r["task_id"], r["verifier_id"])], r["candidate_id"])
        p.outcome[key] = r["outcome"]
        p.failed[key] = frozenset(c["check_id"] for c in r["checks"] if c["status"] != "passed")
        p.passed[key] = frozenset(c["check_id"] for c in r["checks"] if c["status"] == "passed")
    for t in manifest["tasks"]:
        tid, tdir = t["task_id"], tasks_root / t["task_id"]
        p.families.append(t["family_id"])
        m = TaskManifest.model_validate_json(text(tdir / "task.json"))
        proposals = json.loads(text(tdir / "labels" / "proposed_labels.json"))["candidates"]
        checks = json.loads(text(tdir / "labels" / "construction_checks.json"))["checks"]
        dups = json.loads(text(tdir / "labels" / "duplicates.json"))["duplicates"]
        p.same_code_heldout.update({cid: d["same_code_as_heldout"] for cid, d in dups.items() if d.get("same_code_as_heldout")})
        up = tdir / "verifiers" / "repo_tests" / "upstream_check_ids.json"
        p.upstream[tid] = frozenset(json.loads(text(up))["upstream_check_ids"]) if up.exists() else frozenset()
        for rel in m.verifiers:
            spec = VerifierSpec.model_validate_json(text(tdir / rel))
            if spec.condition.value in conditions:
                p.specs[(tid, spec.condition.value)] = spec
        for variant in ("initial_only", "full_session"):
            for k, prefix in ((1, "mapping_"), (2, "mapping2_")):
                mp = tdir / "contracts" / f"{prefix}{variant}.json"
                if mp.exists():
                    p.mappings[(tid, variant, k)] = json.loads(text(mp))
        by_id = {}
        for rel in m.candidates:
            c = Candidate.model_validate_json(text(tdir / rel))
            by_id[c.candidate_id] = c
        held = []
        for cid, info in t["candidates"].items():
            if info["origin"] == "reference":
                p.reference_id[tid] = cid
            if info["origin"] in ("reference", "noop"):
                continue
            c, prop, chk = by_id[cid], proposals[cid], checks.get(cid, {})
            lab = candidate_label(c, "pilot")
            cons_all = [lb for lb in c.labels if lb.labeler_kind == LabelerKind.construction]
            cons = cons_all[-1] if cons_all else None  # the latest, as the analysis's construction policy uses
            held.append(Cand(task_id=tid, family_id=t["family_id"], candidate_id=cid, origin=c.origin.value,
                             d19=lab.value if lab else None, d19_violated=tuple(lab.violated_requirements if lab else ()),
                             construction=cons.value if cons else None,
                             construction_violated=tuple(cons.violated_requirements if cons else ()),
                             check=chk.get("assessed_label"), check_violated=tuple(chk.get("violated_requirements", ())),
                             refcheck="valid" if prop["refcheck_outcome"] == "pass" else "invalid",
                             regression=bool(prop["regression_failed"]),
                             patch_key=hashlib.sha256(_norm_patch(c.patch).encode("utf-8")).hexdigest()))
            if prop["proposed"] != (lab.value if lab else None):
                raise SystemExit(f"{cid}: D19 label in the candidate file differs from labels/proposed_labels.json")
        p.cands += sorted(held, key=lambda c: (c.origin != "observed_pre_correction", c.candidate_id))
    for f in sorted(audits_dir.glob("*.json")):
        p.audits[f.name] = json.loads(text(f))
    text(Path(__file__))
    return p


def key(c: Cand) -> tuple[str, str]:
    return c.task_id, c.candidate_id


def accepted(p: Pilot, cond: str, c: Cand) -> bool:
    return p.outcome[(c.task_id, cond, c.candidate_id)] == "pass"


# Labelings. None excludes the candidate from FA and FR.
def lab_d19(c: Cand) -> str | None:
    return c.d19 if c.d19 in ("valid", "invalid") else None


def lab_amb_valid(c: Cand) -> str | None:
    return "valid" if c.d19 == "ambiguous" else lab_d19(c)


def lab_amb_invalid(c: Cand) -> str | None:
    return "invalid" if c.d19 == "ambiguous" else lab_d19(c)


def lab_construction(c: Cand) -> str | None:
    """Protocol v0.3's construction policy: construction intent; natural candidates keep their D19 label."""
    return c.construction or lab_d19(c)


def lab_construction_only(c: Cand) -> str | None:
    return c.construction


def lab_checks(c: Cand) -> str | None:
    return c.check if c.check in ("valid", "invalid") else None


def lab_refcheck(c: Cand) -> str | None:
    return c.refcheck


# ---------------------------------------------------------------- counting

def _rate(num: int, den: int) -> dict:
    return {"num": num, "den": den, "rate": None if den == 0 else num / den}


def _j(fa: dict, fr: dict) -> float | None:
    return None if fa["rate"] is None or fr["rate"] is None else (1 - fr["rate"]) - fa["rate"]


def family_counts(p: Pilot, cond: str, label: Labeling, cands: Iterable[Cand] | None = None,
                  families: Sequence[str] | None = None) -> dict[str, dict[str, int]]:
    fams = list(families or p.families)
    out = {f: {"fa_num": 0, "fa_den": 0, "fr_num": 0, "fr_den": 0} for f in fams}
    for c in (p.cands if cands is None else cands):
        lab = label(c)
        if lab is None or c.family_id not in out:
            continue
        acc, d = accepted(p, cond, c), out[c.family_id]
        if lab == "invalid":
            d["fa_den"] += 1
            d["fa_num"] += int(acc)
        else:
            d["fr_den"] += 1
            d["fr_num"] += int(not acc)
    return out


def summarize(counts: dict[str, dict[str, int]]) -> dict:
    fams = {}
    for f, d in counts.items():
        fa, fr = _rate(d["fa_num"], d["fa_den"]), _rate(d["fr_num"], d["fr_den"])
        fams[f] = {"fa": fa, "fr": fr, "youden_j": _j(fa, fr)}
    fa = _rate(sum(d["fa_num"] for d in counts.values()), sum(d["fa_den"] for d in counts.values()))
    fr = _rate(sum(d["fr_num"] for d in counts.values()), sum(d["fr_den"] for d in counts.values()))
    mfa = [v["fa"]["rate"] for v in fams.values() if v["fa"]["rate"] is not None]
    mfr = [v["fr"]["rate"] for v in fams.values() if v["fr"]["rate"] is not None]
    macro = {"fa": sum(mfa) / len(mfa) if mfa else None, "fr": sum(mfr) / len(mfr) if mfr else None}
    macro["youden_j"] = None if macro["fa"] is None or macro["fr"] is None else (1 - macro["fr"]) - macro["fa"]
    return {"families": fams, "pooled": {"fa": fa, "fr": fr, "youden_j": _j(fa, fr)}, "macro": macro}


def paired(p: Pilot, a: str, b: str, metric: str, label: Labeling = lab_d19, cands: Iterable[Cand] | None = None,
           families: Sequence[str] | None = None) -> dict:
    """A - B on the same candidates, per family, with exact sign-flip p-values for two statistics.

    ``pooled``: the sum of per-family count differences (each candidate weighs the same; its
    mean is the pooled difference). ``family_mean``: the sum of per-family rate differences
    (each family weighs the same).
    """
    want = "invalid" if metric == "fa" else "valid"
    pool = list(p.cands if cands is None else cands)
    per, disc = {}, {"a_accepts_b_rejects": 0, "a_rejects_b_accepts": 0}
    for f in families or p.families:
        items = [c for c in pool if c.family_id == f and label(c) == want]
        an = sum(int(accepted(p, a, c) == (metric == "fa")) for c in items)
        bn = sum(int(accepted(p, b, c) == (metric == "fa")) for c in items)
        for c in items:
            xa, xb = accepted(p, a, c), accepted(p, b, c)
            disc["a_accepts_b_rejects"] += int(xa and not xb)
            disc["a_rejects_b_accepts"] += int(xb and not xa)
        per[f] = {"a_num": an, "b_num": bn, "den": len(items), "difference": (an - bn) / len(items) if items else None}
    used = [f for f, d in per.items() if d["den"]]
    n = sum(per[f]["den"] for f in used)
    pooled_v = [Fraction(per[f]["a_num"] - per[f]["b_num"]) for f in used]
    mean_v = [Fraction(per[f]["a_num"] - per[f]["b_num"], per[f]["den"]) for f in used]
    return {"a": a, "b": b, "metric": metric, "per_family": per, "n_labeled": n, "n_families": len(used),
            "a_total": sum(per[f]["a_num"] for f in used), "b_total": sum(per[f]["b_num"] for f in used),
            "pooled_difference": float(sum(pooled_v) / n) if n else None,
            "family_mean_difference": float(sum(mean_v) / len(mean_v)) if mean_v else None,
            "discordant": disc, "signflip": {"pooled": signflip(pooled_v), "family_mean": signflip(mean_v)}}


def tost(cmp: dict, margin: Fraction) -> dict:
    """Two one-sided sign-flip tests of |A - B| < margin (equivalence), for both statistics.

    H0a: A - B >= margin (values shifted by -margin, p_less); H0b: A - B <= -margin (shifted by
    +margin, p_greater). Equivalence is concluded only if both reject; the TOST p is the larger p.
    """
    per = [d for d in cmp["per_family"].values() if d["den"]]
    out = {"margin": float(margin)}
    for stat, val in (("pooled", lambda d, s: Fraction(d["a_num"] - d["b_num"]) - s * d["den"]),
                      ("family_mean", lambda d, s: Fraction(d["a_num"] - d["b_num"], d["den"]) - s)):
        upper = signflip([val(d, margin) for d in per])["p_less"]
        lower = signflip([val(d, -margin) for d in per])["p_greater"]
        out[stat] = {"p_upper": upper, "p_lower": lower, "p_tost": None if upper is None else max(upper, lower)}
    return out


# ---------------------------------------------------------------- views

def view_per_family(p: Pilot) -> dict:
    return {"tag": TAG, "label_rule": "D19 proposals; ambiguous excluded", "families": p.families,
            "conditions": {c: summarize(family_counts(p, c, lab_d19)) for c in p.conditions}}


def _cmp_key(a: str, b: str) -> str:
    return f"{a}_vs_{b}"


def view_paired(p: Pilot, label: Labeling = lab_d19, cands: Iterable[Cand] | None = None,
                families: Sequence[str] | None = None) -> dict:
    out = {}
    for a, b, desc in COMPARISONS:
        if a in p.conditions and b in p.conditions:
            out[_cmp_key(a, b)] = {"description": desc, **{m: paired(p, a, b, m, label, cands, families) for m in ("fa", "fr")}}
    return out


def view_agreement(p: Pilot) -> dict:
    labelers = {"refcheck": lab_refcheck, "construction": lab_construction, "construction_constructed_only": lab_construction_only,
                "checks": lab_checks, "d19": lab_d19}
    res: dict = {"tag": TAG, "labelers": {
        "refcheck": "reference-check verdict: valid iff every independent reference check passes (regression norm not included)",
        "construction": "construction intent for constructed candidates; the observed pre-correction states keep their D19 label (protocol v0.3 policy)",
        "construction_constructed_only": "construction intent; defined for constructed candidates only",
        "checks": "independent construction checks' assessed label (tasks/*/labels/construction_checks.json)",
        "d19": "D19 proposal; ambiguous candidates excluded"}, "conditions": {}, "between_labelers": {}}
    for cond in p.conditions:
        res["conditions"][cond] = {}
        for name, lab in labelers.items():
            xs, ys, conf = [], [], Counter()
            for c in p.cands:
                v = lab(c)
                if v is None:
                    continue
                acc = accepted(p, cond, c)
                xs.append(int(acc))
                ys.append(int(v == "valid"))
                conf[f"{v}_{'accepted' if acc else 'rejected'}"] += 1
            agree = sum(x == y for x, y in zip(xs, ys))
            res["conditions"][cond][name] = {"n": len(xs), "agree": agree, "rate": agree / len(xs) if xs else None,
                                             "kappa": cohen_kappa(xs, ys),
                                             "confusion": {k: conf[k] for k in ("valid_accepted", "valid_rejected", "invalid_accepted", "invalid_rejected")}}
    for x, y in (("refcheck", "construction_constructed_only"), ("refcheck", "checks"), ("construction_constructed_only", "checks"),
                 ("d19", "checks"), ("refcheck", "d19")):
        pairs = [(labelers[x](c), labelers[y](c)) for c in p.cands]
        pairs = [(u, v) for u, v in pairs if u is not None and v is not None]
        agree = sum(u == v for u, v in pairs)
        res["between_labelers"][f"{x}_vs_{y}"] = {"n": len(pairs), "agree": agree,
                                                  "kappa": cohen_kappa([int(u == "valid") for u, _ in pairs], [int(v == "valid") for _, v in pairs]),
                                                  "disagreements": [c.candidate_id for c in p.cands
                                                                    if labelers[x](c) is not None and labelers[y](c) is not None and labelers[x](c) != labelers[y](c)]}
    return res


def view_bounds(p: Pilot) -> dict:
    amb = [c for c in p.cands if c.d19 == "ambiguous"]
    res: dict = {"tag": TAG, "ambiguous": [{"candidate": c.candidate_id, "task": c.task_id, "construction": c.construction,
                                            "check": c.check, "accepted_by": [x for x in p.conditions if accepted(p, x, c)]} for c in amb],
                 "n_assignments": 2 ** len(amb), "conditions": {}, "comparisons": {}}

    def labeling(invalid_ids: frozenset) -> Labeling:
        return lambda c: ("invalid" if key(c) in invalid_ids else "valid") if c.d19 == "ambiguous" else lab_d19(c)

    assigns = [frozenset(key(c) for c, s in zip(amb, bits) if s) for bits in itertools.product((0, 1), repeat=len(amb))]
    for cond in p.conditions:
        d = {"as_valid": summarize(family_counts(p, cond, lab_amb_valid)),
             "as_invalid": summarize(family_counts(p, cond, lab_amb_invalid))}
        pooled = [(sorted(x[1] for x in inv), summarize(family_counts(p, cond, labeling(inv)))["pooled"]) for inv in assigns]
        sharp: dict = {}
        for metric in ("fa", "fr", "youden_j"):
            value = (lambda s: s["youden_j"]) if metric == "youden_j" else (lambda s, m=metric: s[m]["rate"])
            lo, hi = min(pooled, key=lambda x: value(x[1])), max(pooled, key=lambda x: value(x[1]))
            sharp[metric] = {"min": value(lo[1]), "max": value(hi[1]), "min_labeled_invalid": lo[0], "max_labeled_invalid": hi[0]}
            if metric != "youden_j":
                sharp[metric]["min_count"] = [lo[1][metric]["num"], lo[1][metric]["den"]]
                sharp[metric]["max_count"] = [hi[1][metric]["num"], hi[1][metric]["den"]]
        d["sharp"] = sharp
        res["conditions"][cond] = d
    for a, b, _ in COMPARISONS:
        k = _cmp_key(a, b)
        res["comparisons"][k] = {}
        for metric in ("fa", "fr"):
            va, vi = paired(p, a, b, metric, lab_amb_valid), paired(p, a, b, metric, lab_amb_invalid)
            diffs = [paired(p, a, b, metric, labeling(inv))["pooled_difference"] for inv in assigns]
            res["comparisons"][k][metric] = {
                scen: {"pooled_difference": x["pooled_difference"], "family_mean_difference": x["family_mean_difference"],
                       "n_labeled": x["n_labeled"], "per_family_difference": {f: v["difference"] for f, v in x["per_family"].items()},
                       "p_greater_pooled": x["signflip"]["pooled"]["p_greater"], "p_two_sided_pooled": x["signflip"]["pooled"]["p_two_sided"],
                       "p_greater_family_mean": x["signflip"]["family_mean"]["p_greater"]}
                for scen, x in (("as_valid", va), ("as_invalid", vi))}
            res["comparisons"][k][metric]["sharp_pooled_difference"] = {"min": min(diffs), "max": max(diffs)}
    return res


def _audit_record(p: Pilot, task: str, cond: str) -> dict:
    """The recorded audit that tested these tests' reference: the final audit for audited
    verifiers; for plain ones the first audit (iteration 0) of the audited verifier that starts
    from them (protocol §4)."""
    if cond.endswith("_audited"):
        spec = p.specs[(task, cond)]
        name = f"{task}-{cond}-iter{spec.audit.iterations}.json" if spec.audit else None
    elif cond.endswith("_plain"):
        name = f"{task}-{cond.replace('_plain', '_audited')}-iter0.json"
    else:
        return {"file": None, "note": "no audit (baseline)"}
    rec = p.audits.get(name or "")
    if rec is None:
        return {"file": name, "note": "missing"}
    ref = [r for r in rec["runs"] if r["origin"] == "reference"]
    return {"file": f"results/audits/{name}", "passed": rec["passed"], "reference_outcome": ref[0]["outcome"] if ref else None,
            "reference_not_passing": any(f["code"] == "reference_not_passing" for f in rec["findings"])}


def view_oracle_gated(p: Pilot) -> dict:
    sanity = {}
    for t in p.families:
        sanity[t] = {}
        for cond in p.conditions:
            out = p.outcome[(t, cond, p.reference_id[t])]
            sanity[t][cond] = {"reference_outcome_in_run": out, "kept": out == "pass", "audit": _audit_record(p, t, cond)}
    kept = {cond: [t for t in p.families if sanity[t][cond]["kept"]] for cond in p.conditions}
    with_audit = [v for t in sanity.values() for v in t.values() if v["audit"].get("reference_outcome")]
    audits_agree = all((v["audit"]["reference_outcome"] == "pass") == v["kept"] for v in with_audit)
    per_arm = {}
    for cond in p.conditions:
        cands = [c for c in p.cands if c.family_id in kept[cond]]
        s = summarize(family_counts(p, cond, lab_d19, cands, kept[cond]))
        per_arm[cond] = {"cells_kept": len(kept[cond]), "cells": len(p.families), "families_kept": kept[cond],
                         "heldout_kept": len(cands), "heldout": len(p.cands),
                         "labeled_kept": sum(1 for c in cands if lab_d19(c)), "labeled": sum(1 for c in p.cands if lab_d19(c)),
                         "pooled": s["pooled"], "per_family": s["families"]}
    common = {}
    for a, b, _ in COMPARISONS:
        fams = [t for t in p.families if t in kept[a] and t in kept[b]]
        cands = [c for c in p.cands if c.family_id in fams]
        common[_cmp_key(a, b)] = {"families": fams, **{m: paired(p, a, b, m, lab_d19, cands, fams) for m in ("fa", "fr")}}
    repro = {}
    for cond, want in DESIGN_AUDIT.items():
        arm = per_arm[cond]["pooled"]
        got: dict = {"per_arm": {m: [arm[m]["num"], arm[m]["den"]] for m in ("fa", "fr")}}
        got["per_arm_matches"] = got["per_arm"] == want
        if cond != "initial_plain":
            fams = [t for t in p.families if t in kept["initial_plain"] and t in kept[cond]]
            s = summarize(family_counts(p, cond, lab_d19, [c for c in p.cands if c.family_id in fams], fams))["pooled"]
            got["common_support_with_initial_plain"] = {m: [s[m]["num"], s[m]["den"]] for m in ("fa", "fr")}
            got["common_support_matches"] = got["common_support_with_initial_plain"] == want
        repro[cond] = {"design_audit": want, "recomputed": got}
    dropped = {c: [t for t in p.families if t not in kept[c]] for c in p.conditions}
    lost = ", ".join(f"{SHORT[c]} loses {', '.join(v)}" for c, v in dropped.items() if v) or "no arm loses a cell"
    c1 = per_arm["initial_plain"]["pooled"]
    explanation = (f"Per-arm gating drops only the cells of an arm that fails its own reference ({lost}), so C1 keeps "
                   f"{_c(c1['fa'])} invalid and {_c(c1['fr'])} valid candidates. The design audit's figures for C3/C4 are "
                   "the common-support counts of their comparison with C1, which drops the same families for both arms. Per "
                   "arm, " + "; ".join(f"{SHORT[c]} keeps {_c(per_arm[c]['pooled']['fa'])} invalid and {_c(per_arm[c]['pooled']['fr'])} valid"
                                       for c in ("full_plain", "full_audited")) + ".")
    return {"tag": TAG, "rule": "drop a verifier x task cell when the verifier does not pass the task's reference solution in the run's sanity grading",
            "reference_sanity": sanity, "audits_agree_with_run": audits_agree, "dropped_cells": dropped, "per_arm": per_arm,
            "common_support": common,
            "design_audit_reproduction": repro, "explanation": explanation}


def _distinct(p: Pilot) -> tuple[list[Cand], list[dict]]:
    groups: dict[tuple[str, str], list[Cand]] = {}
    for c in p.cands:
        groups.setdefault((c.task_id, c.patch_key), []).append(c)
    # Same code apart from comments and docstrings (labels/duplicates.json, held-out pairs only).
    merged = list(groups.values())
    for cid, others in p.same_code_heldout.items():
        ga = next(g for g in merged if any(c.candidate_id == cid for c in g))
        for o in others:
            gb = next(g for g in merged if any(c.candidate_id == o for c in g))
            if ga is not gb:
                ga += gb
                merged.remove(gb)
    reps, info = [], []
    for g in merged:
        reps.append(g[0])
        if len(g) > 1:
            same_out = all(len({accepted(p, cond, c) for c in g}) == 1 for cond in p.conditions)
            info.append({"representative": g[0].candidate_id, "members": [c.candidate_id for c in g],
                         "labels": [c.d19 for c in g], "same_outcome_under_every_condition": same_out})
    reps.sort(key=lambda c: (p.families.index(c.family_id), c.origin != "observed_pre_correction", c.candidate_id))
    return reps, info


def view_distinct(p: Pilot) -> dict:
    reps, groups = _distinct(p)
    labs = Counter(c.d19 for c in reps)
    return {"tag": TAG, "rule": "held-out candidates with the same graded patch (or the same code apart from comments and docstrings, "
                                "labels/duplicates.json) count once; the representative is the pre-correction state, else the first id",
            "groups": groups, "n_heldout": len(p.cands), "n_distinct": len(reps),
            "distinct_by_label": {k: labs.get(k, 0) for k in ("invalid", "valid", "ambiguous")},
            "conditions": {c: summarize(family_counts(p, c, lab_d19, reps)) for c in p.conditions},
            "paired": view_paired(p, lab_d19, reps)}


def _contract_variant(spec: VerifierSpec) -> str | None:
    if not spec.contract_id:
        return None
    return spec.contract_id.split(f"{spec.task_id}-", 1)[1]


def _covers(p: Pilot, task: str, cond: str, mapper: int) -> Callable[[str], set[str]] | None:
    """Reference requirements a check of this verifier maps to (mapper's map minus its contradictions)."""
    spec = p.specs[(task, cond)]
    if cond == "repo_tests":
        up = p.upstream[task]
        return lambda check: {"REGRESSION"} if check in up else set()
    variant = _contract_variant(spec)
    mp = p.mappings.get((task, variant, mapper)) if variant else None
    if mp is None:
        return None
    req = {ch.check_id: ch.requirement_ids for ch in spec.checks}

    def covers(check: str) -> set[str]:
        out: set[str] = set()
        for rid in req.get(check, []):
            out |= set(mp["map"].get(rid, [])) - set(mp.get("contradicts", {}).get(rid, []))
        return out
    return covers


def view_right_reason(p: Pilot) -> dict:
    res: dict = {"tag": TAG,
                 "rule": ("a rejection of an invalid candidate counts only if at least one failing check passes on the task's reference "
                          "solution and maps, through the verifier's requirement map and the contract mapping (mapper 1; mapper 2 as a "
                          "sensitivity), to a requirement the candidate violates (its D19 violated list, plus REGRESSION when the "
                          "regression norm failed); other rejections count as acceptances"),
                 "notes": {"repo_tests": "B1 has no requirement map; this re-analysis maps its checks from the base commit's own tests "
                                         "to the regression norm (REGRESSION) and its agent-added checks to nothing",
                           "llm_freeform": "B2's checks map to its own requirement list, which has no mapping to the reference "
                                           "contract: not evaluable; only the reference-passing criterion is reported"},
                 "conditions": {}}
    invalid = [c for c in p.cands if lab_d19(c) == "invalid"]
    for cond in p.conditions:
        evaluable = all(_covers(p, t, cond, 1) is not None for t in p.families)
        fam = {f: {"invalid": 0, "rejected": 0, "reference_passing_failure": 0, "right_reason": 0, "right_reason_mapper2": 0}
               for f in p.families}
        details = []
        for c in invalid:
            d = fam[c.family_id]
            d["invalid"] += 1
            if accepted(p, cond, c):
                continue
            d["rejected"] += 1
            k = (c.task_id, cond, c.candidate_id)
            ref_ok = p.failed[k] & p.passed[(c.task_id, cond, p.reference_id[c.task_id])]
            d["reference_passing_failure"] += int(bool(ref_ok))
            viol = set(c.d19_violated) | ({"REGRESSION"} if c.regression else set())
            row = {"candidate": c.candidate_id, "failing_checks": len(p.failed[k]), "failing_and_passing_on_reference": len(ref_ok)}
            for mapper, field in ((1, "right_reason"), (2, "right_reason_mapper2")):
                cov = _covers(p, c.task_id, cond, mapper)
                if cov is None:
                    continue
                hits = sorted({r for ch in ref_ok for r in cov(ch)} & viol)
                d[field] += int(bool(hits))
                row[f"mapper{mapper}_requirements_hit"] = hits
            details.append(row)
        tot = {k2: sum(v[k2] for v in fam.values()) for k2 in ("invalid", "rejected", "reference_passing_failure", "right_reason", "right_reason_mapper2")}
        n = tot["invalid"]
        entry = {"evaluable": evaluable, "families": fam, "total": tot,
                 "fa_reported": _rate(n - tot["rejected"], n),
                 "fa_reference_passing": _rate(n - tot["reference_passing_failure"], n), "rejections": details}
        if evaluable:
            entry["fa_right_reason"] = _rate(n - tot["right_reason"], n)
            if cond != "repo_tests":
                entry["fa_right_reason_mapper2"] = _rate(n - tot["right_reason_mapper2"], n)
        res["conditions"][cond] = entry
    return res


def view_natural_negatives(p: Pilot) -> dict:
    """The draft precision plan's primary endpoint in the pilot: C1 vs C3 on the naturally observed negatives only."""
    nat = [c for c in p.cands if c.origin == "observed_pre_correction"]
    eligible = [c for c in nat if lab_d19(c) == "invalid"]
    cmp = paired(p, "initial_plain", "full_plain", "fa", lab_d19, eligible)
    lo, hi = clopper_pearson(len(eligible), len(nat)) if nat else (None, None)
    return {"tag": TAG, "population": "observed pre-correction states labeled invalid by D19 (the pilot has no other natural negative)",
            "states": {c.family_id: {"candidate": c.candidate_id, "d19": c.d19, "initial_plain": p.outcome[(c.task_id, "initial_plain", c.candidate_id)],
                                     "full_plain": p.outcome[(c.task_id, "full_plain", c.candidate_id)]} for c in nat},
            "eligible_families": len(eligible), "families": len(nat), "eligibility_exact95": [lo, hi], "comparison": cmp}


def view_equivalence(p: Pilot) -> dict:
    floor = 1 / (1 << len(p.families))
    res: dict = {"tag": TAG, "question": "is B2 (full-session LLM tests) equivalent to C3/C4 (structured contract) within the margin?",
                 "margin": float(EQUIVALENCE_MARGIN), "alpha_one_sided": 0.05, "floor_one_sided": floor,
                 "attainable": f"with {len(p.families)} families the smallest one-sided sign-flip p is {floor:g}, so equivalence "
                               + ("cannot be concluded at one-sided alpha 0.05 whatever the data" if floor > 0.05 else "is attainable"),
                 "comparisons": {}}
    for b in ("full_plain", "full_audited"):
        for lname, lab in (("d19", lab_d19), ("ambiguous_as_invalid", lab_amb_invalid), ("checks", lab_checks)):
            for metric in ("fa", "fr"):
                cmp = paired(p, "llm_freeform", b, metric, lab)
                res["comparisons"].setdefault(_cmp_key("llm_freeform", b), {}).setdefault(lname, {})[metric] = {
                    "per_family": cmp["per_family"], "pooled_difference": cmp["pooled_difference"],
                    "family_mean_difference": cmp["family_mean_difference"], "n_labeled": cmp["n_labeled"],
                    "discordant": cmp["discordant"], "tost": tost(cmp, EQUIVALENCE_MARGIN),
                    "floor_one_sided": cmp["signflip"]["pooled"]["floor_one_sided"]}
    return res


def consistency(p: Pilot, per_family: dict) -> dict:
    """The re-analysis reads the data as the frozen analysis did; any mismatch stops the script."""
    out: dict = {}
    fz = p.frozen
    if fz is not None:
        bad = []
        for cond in p.conditions:
            mine, theirs = per_family["conditions"][cond], fz["conditions"][cond]
            for m, k in (("fa", "false_acceptance"), ("fr", "false_rejection")):
                if [mine["pooled"][m]["num"], mine["pooled"][m]["den"]] != [theirs[k]["num"], theirs[k]["den"]]:
                    bad.append(f"{cond} {m} pooled")
            for t, x in theirs["per_task_rates"].items():
                f = mine["families"][t]
                if [f["fa"]["num"], f["fa"]["den"], f["fr"]["num"], f["fr"]["den"]] != [x["fa_num"], x["fa_den"], x["fr_num"], x["fr_den"]]:
                    bad.append(f"{cond} {t} per family")
            for lname, lab, sect in (("construction", lab_construction, "sensitivity_construction_labels"),
                                     ("checks", lab_checks, "sensitivity_check_labels")):
                s = summarize(family_counts(p, cond, lab))["pooled"]
                x = fz.get(sect, {}).get(cond)
                if x and [s["fa"]["num"], s["fa"]["den"], s["fr"]["num"], s["fr"]["den"]] != [x["fa_num"], x["fa_den"], x["fr_num"], x["fr_den"]]:
                    bad.append(f"{cond} {lname} sensitivity")
            dups = set(fz.get("duplicates", {}))
            s = summarize(family_counts(p, cond, lab_d19, [c for c in p.cands if c.candidate_id not in dups]))["pooled"]
            x = fz.get("sensitivity_without_duplicates", {}).get(cond)
            if x and [s["fa"]["num"], s["fa"]["den"], s["fr"]["num"], s["fr"]["den"]] != [x["fa_num"], x["fa_den"], x["fr_num"], x["fr_den"]]:
                bad.append(f"{cond} without-duplicates sensitivity")
        out["counts_match_frozen_analysis"] = not bad
        out["mismatches"] = bad
    spec_bad = []
    for t in p.manifest["tasks"]:
        for vid, v in t["verifiers"].items():
            spec = p.specs[(t["task_id"], v["condition"])]
            if checks_sha256(spec) != v.get("checks_sha256") or spec.content_sha256 != v.get("content_sha256"):
                spec_bad.append(f"{t['task_id']}/{vid}")
    out["requirement_maps_match_run_manifest"] = not spec_bad
    out["requirement_map_mismatches"] = spec_bad
    out["d19_labels_match_proposed_labels"] = True  # checked while loading (the script stops otherwise)
    if spec_bad or out.get("mismatches"):
        raise SystemExit(f"consistency check failed: {out}")
    return out


def build_analysis(p: Pilot) -> dict:
    per_family = view_per_family(p)
    return {
        "meta": {"tag": TAG, "run_id": p.run_id,
                 "protocol": "experiments/protocol.md v0.7 §15.1 (re-analyses of pilot-v0.3.3 are post hoc and exploratory) and §15.7 (reporting rules)",
                 "label_policy": "automated pilot: D19 rule proposals and the other recorded labelings; no human labels",
                 "generated_by": "python scripts/exploratory_reanalysis.py", "git_revision": _git_revision(ROOT),
                 "families": p.families, "conditions": p.conditions, "n_heldout": len(p.cands),
                 "inputs_sha256": dict(sorted(p.inputs.items()))},
        "consistency": consistency(p, per_family),
        "per_family": per_family,
        "paired_comparisons": {"tag": TAG, "label_rule": "D19 proposals; ambiguous excluded",
                               "statistics": {"pooled": "sum over families of the count difference A - B (the pooled difference times n)",
                                              "family_mean": "sum over families of the rate difference A - B (each family weighs the same)"},
                               "direction": "p_greater tests H1: A - B > 0, i.e. the first-named arm of protocol §7 errs more",
                               "comparisons": view_paired(p)},
        "labeler_agreement": view_agreement(p),
        "ambiguous_bounds": view_bounds(p),
        "oracle_gated": view_oracle_gated(p),
        "distinct_patches": view_distinct(p),
        "right_reason": view_right_reason(p),
        "b2_equivalence": view_equivalence(p),
        "natural_negatives": view_natural_negatives(p),
    }


# ---------------------------------------------------------------- markdown

def _f(x, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _s(x) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def _p(x) -> str:
    return "n/a" if x is None else f"{x:.4g}"


def _c(r: dict) -> str:
    return f"{r['num']}/{r['den']}"


def to_markdown(a: dict) -> str:
    fams, conds = a["meta"]["families"], a["meta"]["conditions"]
    nm = lambda c: f"{SHORT.get(c, c)} {c}"  # noqa: E731
    k_f, n_assign = len(fams), 2 ** len(fams)
    floor1, floor2 = _p(1 / n_assign), _p(2 / n_assign)
    ag0 = a["labeler_agreement"]["conditions"][conds[0]]
    n_amb = len(a["ambiguous_bounds"]["ambiguous"])
    L = [f"# Exploratory re-analysis of {a['meta']['run_id']}", "",
         f"> **{TAG[0].upper() + TAG[1:]}.** Protocol v0.7 §15.1: re-analyses of the frozen pilot made after 2026-11-21 are "
         "reported here and never replace its pre-specified results (`results/runs/pilot-v0.3.3/analysis.md`). Labels are "
         f"automated proposals (rule D19 and the other recorded labelings); no human labels exist. With {k_f} task families "
         f"no one-sided p-value below {floor1} is attainable, and nothing here is evidence of an effect.", "",
         "Generated by `python scripts/exploratory_reanalysis.py`. Inputs and their sha256 are in `analysis.json` "
         "(`meta.inputs_sha256`). The recomputed counts match the frozen analysis "
         f"({a['consistency'].get('counts_match_frozen_analysis')}), and every verifier's requirement map matches the "
         f"check-list hash in the run manifest ({a['consistency']['requirement_maps_match_run_manifest']}).", ""]
    tests = [(k, m, d["signflip"]["pooled"]["p_greater"]) for k, cmp in a["paired_comparisons"]["comparisons"].items()
             for m in ("fa", "fr") for d in (cmp[m],)]
    pmin = min(x[2] for x in tests)
    nm2 = lambda k, m: f"{' - '.join(SHORT[x] for x in k.split('_vs_'))} {m.upper()}"  # noqa: E731
    eqp = [d["tost"]["pooled"]["p_tost"] for by in a["b2_equivalence"]["comparisons"].values() for ms in by.values() for d in ms.values()]
    L += ["## Summary (generated from the tables below)", "",
          f"* {len(tests)} paired comparisons (protocol §7, FA and FR). The smallest one-sided sign-flip p-value is {_p(pmin)} "
          f"({', '.join(nm2(k, m) for k, m, v in tests if v == pmin)}); the attainable floor with {k_f} families is {floor1}. "
          f"No comparison reaches one-sided 0.05. One-sided p = 1 (no family where the first-named arm errs more): "
          f"{', '.join(nm2(k, m) for k, m, v in tests if v == 1.0) or 'none'}.",
          f"* B2 vs C3/C4 as equivalence (margin {a['b2_equivalence']['margin']:.2f}): the smallest TOST p is {_p(min(eqp))}; "
          f"{a['b2_equivalence']['attainable']}.",
          "* Oracle gate: " + ("; ".join(f"{SHORT[c]} fails its own reference in {', '.join(v)}" for c, v in
                                         a["oracle_gated"]["dropped_cells"].items() if v) or "every verifier passes its reference")
          + f". C1 then accepts {_c(a['oracle_gated']['per_arm']['initial_plain']['pooled']['fa'])} invalid and rejects "
          f"{_c(a['oracle_gated']['per_arm']['initial_plain']['pooled']['fr'])} valid candidates.",
          f"* Right reason: C1 rejects {a['right_reason']['conditions']['initial_plain']['total']['rejected']} of "
          f"{a['right_reason']['conditions']['initial_plain']['total']['invalid']} invalid candidates, "
          f"{a['right_reason']['conditions']['initial_plain']['total']['right_reason']} of them for a requirement the candidate "
          f"violates; C3 rejects {a['right_reason']['conditions']['full_plain']['total']['rejected']}, "
          f"{a['right_reason']['conditions']['full_plain']['total']['right_reason']} of them for the right reason.", ""]
    pf = a["per_family"]["conditions"]
    L += [f"## 1. Per-family table, the primary display ({TAG})", "",
          "FA: accepted / invalid; FR: rejected / valid; J = (1 - FR) - FA. D19 labels, ambiguous candidates excluded.", "",
          "| Condition | " + " | ".join(f"{f} FA | {f} FR | {f} J" for f in fams) + " | Pooled FA | Pooled FR | Pooled J | Macro J |",
          "| --- | " + " | ".join("--- | --- | ---" for _ in fams) + " | --- | --- | --- | --- |"]
    for c in conds:
        d = pf[c]
        cells = [f"{_c(d['families'][f]['fa'])} | {_c(d['families'][f]['fr'])} | {_s(d['families'][f]['youden_j'])}" for f in fams]
        L.append(f"| {nm(c)} | " + " | ".join(cells) + f" | {_c(d['pooled']['fa'])} | {_c(d['pooled']['fr'])} | "
                 f"{_s(d['pooled']['youden_j'])} | {_s(d['macro']['youden_j'])} |")
    L += ["", f"## 2. Paired comparisons of protocol §7, exact sign-flip p-values over families ({TAG})", "",
          f"Per-family difference A - B in FA or FR on the same candidates. Each p-value is exact over the 2^{k_f} = {n_assign} sign "
          "assignments of the per-family differences, for the pooled statistic (sum of count differences) / the family-mean "
          f"statistic (sum of rate differences). One-sided p tests H1: A - B > 0 (the first-named arm errs more). Floor: {floor1} "
          f"one-sided and {floor2} two-sided for {k_f} families; a family with zero difference cannot change sign, so the "
          f"conditional floor is 2^z/{n_assign} for z such families.", "",
          "| A | B | Metric | " + " | ".join(fams) + " | Pooled A-B | Family-mean A-B | Discordant (A acc & B rej / A rej & B acc) | "
          "p one-sided A>B | p one-sided A<B | p two-sided | Conditional floor |",
          "| --- | --- | --- | " + " | ".join("---" for _ in fams) + " | --- | --- | --- | --- | --- | --- | --- |"]
    for k, cmp in a["paired_comparisons"]["comparisons"].items():
        for m in ("fa", "fr"):
            d = cmp[m]
            sp, sm = d["signflip"]["pooled"], d["signflip"]["family_mean"]
            per = " | ".join(_s(d["per_family"][f]["difference"]) for f in fams)
            L.append(f"| {SHORT[d['a']]} | {SHORT[d['b']]} | {m.upper()} | {per} | {_s(d['pooled_difference'])} | "
                     f"{_s(d['family_mean_difference'])} | {d['discordant']['a_accepts_b_rejects']} / {d['discordant']['a_rejects_b_accepts']} | "
                     f"{_p(sp['p_greater'])} / {_p(sm['p_greater'])} | {_p(sp['p_less'])} / {_p(sm['p_less'])} | "
                     f"{_p(sp['p_two_sided'])} / {_p(sm['p_two_sided'])} | {_p(sp['conditional_floor_one_sided'])} |")
    ag = a["labeler_agreement"]
    L += ["", f"## 3. Agreement of each condition with three labelers on all {a['meta']['n_heldout']} held-out candidates ({TAG})", "",
          "Agreement: the condition accepts a candidate the labeler calls valid, or rejects one it calls invalid (agree/n, "
          "Cohen's kappa). Reference checks: valid iff every independent reference check passes (the regression norm is not "
          "part of this verdict). Construction intent: the four observed pre-correction states have none and keep their D19 "
          "label (protocol v0.3 policy); the constructed-only figure is in brackets. Independent checks: "
          f"`tasks/*/labels/construction_checks.json` (advisory). The D19 column ({ag0['d19']['n']} labeled) is given for reference.", "",
          f"| Condition | Reference checks | Construction intent [{ag0['construction_constructed_only']['n']} constructed] | Independent checks | D19 |",
          "| --- | --- | --- | --- | --- |"]
    for c in conds:
        d = ag["conditions"][c]
        cell = lambda x: f"{x['agree']}/{x['n']} (kappa {_f(x['kappa'])})"  # noqa: E731
        L.append(f"| {nm(c)} | {cell(d['refcheck'])} | {cell(d['construction'])} [{d['construction_constructed_only']['agree']}/"
                 f"{d['construction_constructed_only']['n']}] | {cell(d['checks'])} | {cell(d['d19'])} |")
    L += ["", "Between the labelers (agree/n, kappa; disagreements):", ""]
    for k, d in ag["between_labelers"].items():
        L.append(f"* {k.replace('_vs_', ' vs ')}: {d['agree']}/{d['n']} (kappa {_f(d['kappa'])}); {', '.join(d['disagreements']) or 'none'}")
    b = a["ambiguous_bounds"]
    L += ["", f"## 4. Bounds over the {n_amb} ambiguous near misses ({TAG})", "",
          f"The D19 rule marked {n_amb} near misses ambiguous: " + ", ".join(x["candidate"] for x in b["ambiguous"]) +
          f". All valid / all invalid, and the sharp range over all 2^{n_amb} = {b['n_assignments']} assignments (attained by "
          "different assignments).", "",
          "| Condition | FA all valid | FR all valid | FA all invalid | FR all invalid | FA range | FR range | J range |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in conds:
        d = b["conditions"][c]
        sh = d["sharp"]
        L.append(f"| {nm(c)} | {_c(d['as_valid']['pooled']['fa'])} | {_c(d['as_valid']['pooled']['fr'])} | "
                 f"{_c(d['as_invalid']['pooled']['fa'])} | {_c(d['as_invalid']['pooled']['fr'])} | "
                 f"[{sh['fa']['min_count'][0]}/{sh['fa']['min_count'][1]}, {sh['fa']['max_count'][0]}/{sh['fa']['max_count'][1]}] | "
                 f"[{sh['fr']['min_count'][0]}/{sh['fr']['min_count'][1]}, {sh['fr']['max_count'][0]}/{sh['fr']['max_count'][1]}] | "
                 f"[{_s(sh['youden_j']['min'])}, {_s(sh['youden_j']['max'])}] |")
    L += ["", "Paired comparisons under the two extreme labelings (pooled A - B; one-sided sign-flip p, pooled statistic) and the "
          f"range of the pooled difference over all {b['n_assignments']} assignments:", "",
          "| A | B | Metric | All valid: A-B (p) | All invalid: A-B (p) | Range of A-B |", "| --- | --- | --- | --- | --- | --- |"]
    for k, cmp in b["comparisons"].items():
        a_, b_ = k.split("_vs_")
        for m in ("fa", "fr"):
            d = cmp[m]
            L.append(f"| {SHORT[a_]} | {SHORT[b_]} | {m.upper()} | {_s(d['as_valid']['pooled_difference'])} ({_p(d['as_valid']['p_greater_pooled'])}) | "
                     f"{_s(d['as_invalid']['pooled_difference'])} ({_p(d['as_invalid']['p_greater_pooled'])}) | "
                     f"[{_s(d['sharp_pooled_difference']['min'])}, {_s(d['sharp_pooled_difference']['max'])}] |")
    og = a["oracle_gated"]
    L += ["", f"## 5. Oracle-gated view, secondary ({TAG})", "",
          "A verifier x task cell is dropped when the verifier does not pass the task's reference solution in the run's sanity "
          f"grading. The recorded audits {'agree' if og['audits_agree_with_run'] else 'DISAGREE'}: " + "; ".join(
              f"{t} {SHORT[c]}: run {og['reference_sanity'][t][c]['reference_outcome_in_run']}, audit "
              f"`{og['reference_sanity'][t][c]['audit'].get('file')}` reference {og['reference_sanity'][t][c]['audit'].get('reference_outcome')}"
              for t in fams for c in conds if not og["reference_sanity"][t][c]["kept"]) + ".", "",
          "| Condition | Cells kept (yield) | Held-out kept | FA | FR | J |", "| --- | --- | --- | --- | --- | --- |"]
    for c in conds:
        d = og["per_arm"][c]
        L.append(f"| {nm(c)} | {d['cells_kept']}/{d['cells']} | {d['heldout_kept']}/{d['heldout']} | {_c(d['pooled']['fa'])} | "
                 f"{_c(d['pooled']['fr'])} | {_s(d['pooled']['youden_j'])} |")
    L += ["", "Common support of each paired comparison (families where both arms pass their reference):", "",
          "| A | B | Families | FA A | FA B | p one-sided (FA) | FR A | FR B |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k, d in og["common_support"].items():
        fa, fr = d["fa"], d["fr"]
        L.append(f"| {SHORT[fa['a']]} | {SHORT[fa['b']]} | {', '.join(d['families'])} | {fa['a_total']}/{fa['n_labeled']} | "
                 f"{fa['b_total']}/{fa['n_labeled']} | {_p(fa['signflip']['pooled']['p_greater'])} | {fr['a_total']}/{fr['n_labeled']} | "
                 f"{fr['b_total']}/{fr['n_labeled']} |")
    L += ["", "Design-audit figures reproduced: " + "; ".join(
        f"{SHORT[c]} design audit FA {v['design_audit']['fa'][0]}/{v['design_audit']['fa'][1]}, FR {v['design_audit']['fr'][0]}/{v['design_audit']['fr'][1]}; "
        f"per arm FA {v['recomputed']['per_arm']['fa'][0]}/{v['recomputed']['per_arm']['fa'][1]}, FR {v['recomputed']['per_arm']['fr'][0]}/{v['recomputed']['per_arm']['fr'][1]}"
        + (f"; common support with C1 FA {v['recomputed']['common_support_with_initial_plain']['fa'][0]}/{v['recomputed']['common_support_with_initial_plain']['fa'][1]}, "
           f"FR {v['recomputed']['common_support_with_initial_plain']['fr'][0]}/{v['recomputed']['common_support_with_initial_plain']['fr'][1]}"
           if "common_support_with_initial_plain" in v["recomputed"] else "")
        for c, v in og["design_audit_reproduction"].items()) + ". " + og["explanation"]]
    dp = a["distinct_patches"]
    L += ["", f"## 6. Each distinct graded patch counted once ({TAG})", "",
          f"{dp['n_heldout']} held-out candidates, {dp['n_distinct']} distinct graded patches ("
          + ", ".join(f"{v} {k}" for k, v in dp["distinct_by_label"].items()) + "). Merged: "
          + ("; ".join(f"{', '.join(g['members'])} (labels {', '.join(str(x) for x in g['labels'])}; same outcome under every "
                       f"condition: {g['same_outcome_under_every_condition']})" for g in dp["groups"]) or "none") + ".", "",
          "| Condition | " + " | ".join(f"{f} FA | {f} FR" for f in fams) + " | Pooled FA | Pooled FR | Pooled J | p one-sided vs C3 (FA) |",
          "| --- | " + " | ".join("--- | ---" for _ in fams) + " | --- | --- | --- | --- |"]
    for c in conds:
        d = dp["conditions"][c]
        k = _cmp_key(c, "full_plain")
        pv = dp["paired"].get(k, {}).get("fa", {}).get("signflip", {}).get("pooled", {}).get("p_greater")
        L.append(f"| {nm(c)} | " + " | ".join(f"{_c(d['families'][f]['fa'])} | {_c(d['families'][f]['fr'])}" for f in fams)
                 + f" | {_c(d['pooled']['fa'])} | {_c(d['pooled']['fr'])} | {_s(d['pooled']['youden_j'])} | {_p(pv) if pv is not None else '-'} |")
    rr = a["right_reason"]
    L += ["", f"## 7. Right-reason view ({TAG})", "", "Rule: " + rr["rule"] + ".", "",
          "| Condition | Invalid rejected | Failing check passes on reference | Right reason (mapper 1) | Right reason (mapper 2) | "
          "FA as reported | FA right reason (mapper 1) |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for c in conds:
        d = rr["conditions"][c]
        t = d["total"]
        r1 = f"{t['right_reason']}/{t['invalid']}" if d["evaluable"] else "not evaluable"
        r2 = f"{t['right_reason_mapper2']}/{t['invalid']}" if "fa_right_reason_mapper2" in d else ("as mapper 1" if d["evaluable"] else "not evaluable")
        L.append(f"| {nm(c)} | {t['rejected']}/{t['invalid']} | {t['reference_passing_failure']}/{t['invalid']} | {r1} | {r2} | "
                 f"{_c(d['fa_reported'])} | {_c(d['fa_right_reason']) if d['evaluable'] else 'n/a'} |")
    L += ["", *[f"* {SHORT[k]}: {v}" for k, v in rr["notes"].items()], "", "Per family (right-reason rejections, mapper 1 / invalid):", ""]
    for c in conds:
        d = rr["conditions"][c]
        if d["evaluable"]:
            L.append(f"* {nm(c)}: " + ", ".join(f"{f} {v['right_reason']}/{v['invalid']}" for f, v in d["families"].items()))
    eq = a["b2_equivalence"]
    L += ["", f"## 8. B2 vs C3/C4 as an equivalence question ({TAG})", "",
          f"Margin +/-{eq['margin']:.2f} on FA and on FR; two one-sided sign-flip tests (TOST) at one-sided alpha "
          f"{eq['alpha_one_sided']}: {eq['attainable']}.", "",
          "| B2 vs | Labels | Metric | " + " | ".join(fams) + " | Pooled B2-C | Discordant (B2 acc & C rej / B2 rej & C acc) | TOST p (pooled / family mean) |",
          "| --- | --- | --- | " + " | ".join("---" for _ in fams) + " | --- | --- | --- |"]
    for k, by in eq["comparisons"].items():
        for lname, ms in by.items():
            for m, d in ms.items():
                L.append(f"| {SHORT[k.split('_vs_')[1]]} | {lname} | {m.upper()} | " + " | ".join(_s(d["per_family"][f]["difference"]) for f in fams)
                         + f" | {_s(d['pooled_difference'])} | {d['discordant']['a_accepts_b_rejects']} / {d['discordant']['a_rejects_b_accepts']} | "
                         f"{_p(d['tost']['pooled']['p_tost'])} / {_p(d['tost']['family_mean']['p_tost'])} |")
    nn = a["natural_negatives"]
    cmp = nn["comparison"]
    L += ["", f"## 9. The draft precision plan's primary endpoint in the pilot ({TAG})", "",
          f"C1 vs C3 FA on {nn['population']}: {nn['eligible_families']} of {nn['families']} families are eligible "
          f"(exact 95% interval of the share {_f(nn['eligibility_exact95'][0])} to {_f(nn['eligibility_exact95'][1])}).", "",
          "| Family | Pre-correction state | D19 | C1 | C3 |", "| --- | --- | --- | --- | --- |"]
    for f, s in nn["states"].items():
        L.append(f"| {f} | {s['candidate']} | {s['d19']} | {s['initial_plain']} | {s['full_plain']} |")
    sf = cmp["signflip"]["pooled"]
    L += ["", f"Per-family difference over the eligible families: "
          + ", ".join(f"{f} {_s(v['difference'])}" for f, v in cmp["per_family"].items() if v["den"])
          + f"; one-sided sign-flip p {_p(sf['p_greater'])} (floor {_p(sf['floor_one_sided'])} for {sf['k']} families)."]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- LaTeX tables and ledger

def tex(s) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&").replace("#", r"\#"))


def _dig(data: dict, path: str):
    for part in path.split("."):
        data = data[part]
    return data


class Ledger:
    """Every number printed in a table is read through ``v`` and listed with its JSON path."""

    def __init__(self, sources: dict[str, tuple[str, dict]]) -> None:
        self.sources = sources
        self.lines = ["# Evidence ledger (exploratory re-analysis and planning simulation)", "",
                      f"**{TAG[0].upper() + TAG[1:]}.** Every number in `paper/generated/exploratory/*.tex`, with the file and JSON "
                      "path it is read from. Generated by `python scripts/exploratory_reanalysis.py`; nothing is entered by hand. "
                      "The pre-specified pilot results and their ledger are `results/runs/pilot-v0.3.3/analysis.json` and "
                      "`paper/evidence_ledger.md`.", ""]
        self.table = ""

    def start(self, table: str) -> None:
        self.table = table
        self.lines += ["", f"## {table}", ""]

    def v(self, src: str, path: str):
        rel, data = self.sources[src]
        value = _dig(data, path)
        self.lines.append(f"- [{self.table}] `{path}` = {value} <- `{rel}`")
        return value


def _table(caption: str, label: str, spec: str, header: str, rows: list[str], size: str = "\\footnotesize") -> str:
    return (f"\\begin{{table}}[t]\\centering{size}\n\\caption{{\\textbf{{Post hoc, exploratory (not pre-specified).}} {caption}}}"
            f"\\label{{{label}}}\n\\begin{{tabular}}{{{spec}}}\\toprule {header} \\\\\\midrule\n" + "\n".join(rows)
            + "\n\\bottomrule\\end{tabular}\\end{table}\n")


def _frac(led: Ledger, src: str, path: str) -> str:
    return f"{led.v(src, path + '.num')}/{led.v(src, path + '.den')}"


def _num(x, fmt: str) -> str:
    return "--" if x is None else format(x, fmt)


def write_tables(a: dict, sim: dict | None, out_dir: Path) -> Ledger:
    GEN.mkdir(parents=True, exist_ok=True)
    for old in GEN.glob("*.tex"):
        old.unlink()  # every table is regenerated; none may survive from an earlier invocation
    srcs = {"a": (_rel(out_dir / "analysis.json"), a)}
    if sim is not None:
        srcs["s"] = (_rel(out_dir / "planning_simulation.json"), sim)
    led = Ledger(srcs)
    fams, conds = a["meta"]["families"], a["meta"]["conditions"]
    cn = lambda c: tex(f"{SHORT[c]} {c}")  # noqa: E731

    led.start("per_family_table")
    rows = []
    for c in conds:
        base = f"per_family.conditions.{c}"
        cells = [f"{_frac(led, 'a', f'{base}.families.{f}.fa')} $\\cdot$ {_frac(led, 'a', f'{base}.families.{f}.fr')} $\\cdot$ "
                 f"{_num(led.v('a', f'{base}.families.{f}.youden_j'), '+.2f')}" for f in fams]
        rows.append(f"{cn(c)} & " + " & ".join(cells) + f" & {_frac(led, 'a', base + '.pooled.fa')} $\\cdot$ {_frac(led, 'a', base + '.pooled.fr')}"
                    f" $\\cdot$ {_num(led.v('a', base + '.pooled.youden_j'), '+.2f')} \\\\")
    (GEN / "per_family_table.tex").write_text(_table(
        "Per-family table, the primary display (protocol v0.7 \\S15.7): FA (accepted/invalid) $\\cdot$ FR (rejected/valid) $\\cdot$ "
        "Youden's $J$ per task family and pooled, run \\texttt{pilot-v0.3.3}, D19 labels (automated proposals), ambiguous excluded.",
        "tab:expl-per-family", "l" + "c" * (len(fams) + 1), "Condition & " + " & ".join(tex(f) for f in fams) + " & Pooled", rows))

    led.start("paired_signflip_table")
    rows = []
    for k in a["paired_comparisons"]["comparisons"]:
        for m in ("fa", "fr"):
            base = f"paired_comparisons.comparisons.{k}.{m}"
            d = a["paired_comparisons"]["comparisons"][k][m]
            per = " & ".join(_num(led.v("a", f"{base}.per_family.{f}.difference"), "+.2f") for f in fams)
            rows.append(f"{SHORT[d['a']]} -- {SHORT[d['b']]} & {m.upper()} & {per} & {_num(led.v('a', base + '.pooled_difference'), '+.2f')} & "
                        f"{led.v('a', base + '.discordant.a_accepts_b_rejects')}/{led.v('a', base + '.discordant.a_rejects_b_accepts')} & "
                        f"{_p(led.v('a', base + '.signflip.pooled.p_greater'))} & {_p(led.v('a', base + '.signflip.pooled.p_two_sided'))} & "
                        f"{_p(led.v('a', base + '.signflip.family_mean.p_greater'))} & {_p(led.v('a', base + '.signflip.pooled.conditional_floor_one_sided'))} \\\\")
    sf0 = "paired_comparisons.comparisons.initial_plain_vs_full_plain.fa.signflip.pooled"
    (GEN / "paired_signflip_table.tex").write_text(_table(
        f"Paired comparisons of protocol \\S7 with exact sign-flip randomization p-values over the {led.v('a', sf0 + '.k')} families "
        "(all sign assignments). Per-family and pooled differences A$-$B; discordant: A accepts \\& B rejects / A rejects \\& B accepts. "
        "$p_1$: one-sided, H1: A$-$B$>0$; $p_2$: two-sided; pooled (count-weighted) statistic, and $p_1$ for the family-mean "
        f"statistic. Attainable floor: {_p(led.v('a', sf0 + '.floor_one_sided'))} one-sided, {_p(led.v('a', sf0 + '.floor_two_sided'))} "
        "two-sided; cond.\\ floor: the smallest one-sided p the families with zero difference allow.", "tab:expl-paired", "ll" + "r" * len(fams) + "rrrrrr",
        "A -- B & Metric & " + " & ".join(tex(f) for f in fams) + " & Pooled & Disc. & $p_1$ & $p_2$ & $p_1$ (mean) & Cond.\\ floor", rows,
        size="\\scriptsize"))

    led.start("labeler_agreement_table")
    rows = []
    for c in conds:
        base = f"labeler_agreement.conditions.{c}"
        cell = lambda n: f"{led.v('a', f'{base}.{n}.agree')}/{led.v('a', f'{base}.{n}.n')} ({_num(led.v('a', f'{base}.{n}.kappa'), '.2f')})"  # noqa: E731
        rows.append(f"{cn(c)} & {cell('refcheck')} & {cell('construction')} & {cell('construction_constructed_only')} & {cell('checks')} & {cell('d19')} \\\\")
    ag0 = f"labeler_agreement.conditions.{conds[0]}"
    (GEN / "labeler_agreement_table.tex").write_text(_table(
        f"Agreement (agree/n, Cohen's $\\kappa$) of each condition's accept/reject with each labeler on all {led.v('a', 'meta.n_heldout')} "
        "held-out candidates of \\texttt{pilot-v0.3.3}, the ambiguous ones included. Reference checks: valid iff every independent "
        "reference check passes. Construction intent: the observed pre-correction states keep their D19 label; ``constructed'': "
        f"the {led.v('a', ag0 + '.construction_constructed_only.n')} constructed candidates only. Independent checks: advisory "
        f"construction checks. D19: the {led.v('a', ag0 + '.d19.n')} candidates it labels.",
        "tab:expl-agreement", "lccccc", "Condition & Ref.\\ checks & Construction & Constructed & Indep.\\ checks & D19", rows))

    led.start("ambiguous_bounds_table")
    rows = []
    for c in conds:
        base = f"ambiguous_bounds.conditions.{c}"
        sh = f"{base}.sharp"
        rows.append(f"{cn(c)} & {_frac(led, 'a', base + '.as_valid.pooled.fa')} & {_frac(led, 'a', base + '.as_valid.pooled.fr')} & "
                    f"{_frac(led, 'a', base + '.as_invalid.pooled.fa')} & {_frac(led, 'a', base + '.as_invalid.pooled.fr')} & "
                    f"[{_num(led.v('a', sh + '.fa.min'), '.2f')}, {_num(led.v('a', sh + '.fa.max'), '.2f')}] & "
                    f"[{_num(led.v('a', sh + '.fr.min'), '.2f')}, {_num(led.v('a', sh + '.fr.max'), '.2f')}] \\\\")
    (GEN / "ambiguous_bounds_table.tex").write_text(_table(
        f"Rates with the {len(led.v('a', 'ambiguous_bounds.ambiguous'))} near misses that rule D19 marked ambiguous treated as valid, "
        f"and as invalid, and the sharp range of the pooled rate over all {led.v('a', 'ambiguous_bounds.n_assignments')} assignments "
        "of their labels (the ends are attained by different assignments).",
        "tab:expl-bounds", "lcccccc", "Condition & FA (valid) & FR (valid) & FA (invalid) & FR (invalid) & FA range & FR range", rows))

    led.start("oracle_gated_table")
    rows = []
    for c in conds:
        base = f"oracle_gated.per_arm.{c}"
        rows.append(f"{cn(c)} & {led.v('a', base + '.cells_kept')}/{led.v('a', base + '.cells')} & "
                    f"{led.v('a', base + '.heldout_kept')}/{led.v('a', base + '.heldout')} & {_frac(led, 'a', base + '.pooled.fa')} & "
                    f"{_frac(led, 'a', base + '.pooled.fr')} \\\\")
    for k in ("initial_plain_vs_full_plain", "initial_audited_vs_full_audited"):
        base = f"oracle_gated.common_support.{k}"
        d = a["oracle_gated"]["common_support"][k]
        rows.append(f"{SHORT[d['fa']['b']]} on {SHORT[d['fa']['a']]}'s support & {len(led.v('a', base + '.families'))}/{len(fams)} & -- & "
                    f"{led.v('a', base + '.fa.b_total')}/{led.v('a', base + '.fa.n_labeled')} & "
                    f"{led.v('a', base + '.fr.b_total')}/{led.v('a', base + '.fr.n_labeled')} \\\\")
    da = "oracle_gated.design_audit_reproduction.full_plain.design_audit"
    agree = "agree" if led.v("a", "oracle_gated.audits_agree_with_run") else "do not all agree"
    (GEN / "oracle_gated_table.tex").write_text(_table(
        "Oracle-gated view (secondary, protocol v0.7 \\S15.7): a verifier $\\times$ task cell is dropped when the verifier does "
        f"not pass the task's reference solution (run sanity grading; the recorded audits {agree}). Cells kept is the per-arm "
        "yield. Last rows: the correction-aware arm on the families where the initial-only arm passes its reference (the "
        f"design audit's {led.v('a', da + '.fa')[0]}/{led.v('a', da + '.fa')[1]} and {led.v('a', da + '.fr')[0]}/{led.v('a', da + '.fr')[1]}).",
        "tab:expl-gated", "lcccc", "Condition & Cells kept & Held-out kept & FA & FR", rows))

    led.start("distinct_patches_table")
    rows = []
    for c in conds:
        base = f"distinct_patches.conditions.{c}"
        rows.append(f"{cn(c)} & " + " & ".join(f"{_frac(led, 'a', f'{base}.families.{f}.fa')} $\\cdot$ {_frac(led, 'a', f'{base}.families.{f}.fr')}" for f in fams)
                    + f" & {_frac(led, 'a', base + '.pooled.fa')} $\\cdot$ {_frac(led, 'a', base + '.pooled.fr')} \\\\")
    (GEN / "distinct_patches_table.tex").write_text(_table(
        f"Each distinct graded patch counted once: {led.v('a', 'distinct_patches.n_distinct')} distinct patches among "
        f"{led.v('a', 'distinct_patches.n_heldout')} held-out candidates (the observed pre-correction state of CS-04 and one of its "
        "near misses have the same graded patch). FA (accepted/invalid) $\\cdot$ FR (rejected/valid) per family and pooled, D19 labels.",
        "tab:expl-distinct", "l" + "c" * (len(fams) + 1), "Condition & " + " & ".join(tex(f) for f in fams) + " & Pooled", rows))

    led.start("right_reason_table")
    rows = []
    for c in conds:
        base = f"right_reason.conditions.{c}"
        d = a["right_reason"]["conditions"][c]
        tot = f"{base}.total"
        rr1 = f"{led.v('a', tot + '.right_reason')}/{led.v('a', tot + '.invalid')}" if d["evaluable"] else "n/e"
        rr2 = f"{led.v('a', tot + '.right_reason_mapper2')}/{led.v('a', tot + '.invalid')}" if "fa_right_reason_mapper2" in d else ("n/e" if not d["evaluable"] else "--")
        rows.append(f"{cn(c)} & {led.v('a', tot + '.rejected')}/{led.v('a', tot + '.invalid')} & "
                    f"{led.v('a', tot + '.reference_passing_failure')}/{led.v('a', tot + '.invalid')} & {rr1} & {rr2} & "
                    f"{_frac(led, 'a', base + '.fa_reported')} & {_frac(led, 'a', base + '.fa_right_reason') if d['evaluable'] else 'n/e'} \\\\")
    (GEN / "right_reason_table.tex").write_text(_table(
        "Right-reason view: a rejection of an invalid candidate counts only if a failing check passes on the reference and maps "
        "(verifier requirement map, then contract mapping) to a requirement the candidate violates; other rejections count as "
        "acceptances. n/e: not evaluable (B2 has no mapping to the reference contract). B1: checks from the base commit's own "
        "tests are mapped to the regression norm by this re-analysis.", "tab:expl-right-reason", "lcccccc",
        "Condition & Rejected & Fails a ref.-passing check & Right reason (m1) & Right reason (m2) & FA & FA right reason", rows))

    led.start("b2_equivalence_table")
    rows = []
    for k, by in a["b2_equivalence"]["comparisons"].items():
        for lname in by:
            for m in ("fa", "fr"):
                base = f"b2_equivalence.comparisons.{k}.{lname}.{m}"
                rows.append(f"B2 -- {SHORT[k.split('_vs_')[1]]} & {LABEL_TEX.get(lname, tex(lname))} & {m.upper()} & "
                            + " & ".join(_num(led.v("a", f"{base}.per_family.{f}.difference"), "+.2f") for f in fams)
                            + f" & {_num(led.v('a', base + '.pooled_difference'), '+.2f')} & {led.v('a', base + '.discordant.a_accepts_b_rejects')}/"
                            f"{led.v('a', base + '.discordant.a_rejects_b_accepts')} & {_p(led.v('a', base + '.tost.pooled.p_tost'))} \\\\")
    (GEN / "b2_equivalence_table.tex").write_text(_table(
        f"B2 (full-session LLM tests) against C3/C4 as an equivalence question, margin $\\pm${led.v('a', 'b2_equivalence.margin'):.2f}: "
        "per-family and pooled differences, discordant pairs (B2 accepts \\& C rejects / B2 rejects \\& C accepts) and the TOST "
        f"p-value (two one-sided sign-flip tests, pooled statistic). No p below {_p(led.v('a', 'b2_equivalence.floor_one_sided'))} is "
        f"attainable, so equivalence cannot be concluded at one-sided $\\alpha={led.v('a', 'b2_equivalence.alpha_one_sided')}$. "
        "Labels: D19; the ambiguous near misses as invalid; the independent checks.",
        "tab:expl-equivalence", "lll" + "r" * len(fams) + "rrr",
        "Pair & Labels & Metric & " + " & ".join(tex(f) for f in fams) + " & Pooled & Disc. & TOST $p$", rows, size="\\scriptsize"))

    if sim is not None:
        _planning_tables(sim, led)
    return led


LABEL_TEX = {"d19": "D19", "ambiguous_as_invalid": "amb.\\ as invalid", "checks": "indep.\\ checks",
             "null_rare": "null, rare events", "delta20_mid": "$\\Delta=0.20$, $\\tau$ mid",
             "delta35_high_pilotlike": "$\\Delta=0.35$, $\\tau$ high (pilot-like)"}


def _key_tex(k: str) -> str:
    """A JSON key of the planning output as table text ("icc=30pct" -> "0.30", "m=2_K=10" -> "$m=2$, $K=10$")."""
    if k in LABEL_TEX:
        return LABEL_TEX[k]
    parts = []
    for part in k.split("_K="):
        name, _, val = part.rpartition("=")
        if val.endswith(("pct", "pp")):
            parts.append(f"{int(val[:-3] if val.endswith('pct') else val[:-2]) / 100:.2f}")
        elif name in ("n_neg", "n", "m"):
            parts.append(f"${name.replace('n_neg', 'n')}={val}$")
        else:
            parts.append(f"$K={val}$")
    return ", ".join(parts)


def _natkey(k: str) -> list:
    """Natural sort key, so that K=4 sorts before K=12 whatever order the JSON was read in."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", k)]


def _ordered(d: dict) -> list[str]:
    order = list(COVERAGE_SCENARIOS)
    return sorted(d, key=lambda k: (order.index(k), []) if k in order else (len(order), _natkey(k)))


def _planning_tables(sim: dict, led: Ledger) -> None:
    led.start("planning_coverage_table")
    rows = []
    for sk in _ordered(sim["coverage"]["scenarios"]):
        sc = sim["coverage"]["scenarios"][sk]
        for kk in _ordered(sc["cells"]):
            base = f"coverage.scenarios.{sk}.cells.{kk}"
            rows.append(f"{_key_tex(sk)} & {led.v('s', base + '.K')} & {_num(led.v('s', base + '.signflip_coverage'), '.3f')} & "
                        f"{_num(led.v('s', base + '.signflip_coverage_attainable'), '.3f')} ({_num(led.v('s', base + '.attainable_level'), '.3f')}) & "
                        f"{_num(led.v('s', base + '.bootstrap_coverage'), '.3f')} \\\\")
    (GEN / "planning_coverage_table.tex").write_text(_table(
        "\\emph{Planning simulation, not an analysis of pilot outcomes.} Coverage of the two-sided 95\\% interval for the mean "
        "per-family FA difference, by inverting the exact sign-flip test over families, against the cluster-bootstrap "
        "percentile interval; in brackets the attainable level of the inverted interval with the smallest attainable "
        "$\\alpha$ (for $K=4$, 1/16 per side). Scenarios and replicates: \\texttt{planning\\_simulation.json}.",
        "tab:plan-coverage", "lrccc", "Scenario & $K$ & Sign-flip 95\\% & Sign-flip (attainable level) & Bootstrap 95\\%", rows))
    led.start("planning_family_counts_table")
    rows = []
    fc = sim["family_counts"]
    for nk in _ordered(fc["min_families"]):
        byd = fc["min_families"][nk]
        for dk in _ordered(byd):
            byt, cells = byd[dk], []
            for tk in ("tau=low", "tau=mid", "tau=high"):
                if tk not in byt:
                    cells.append("--")
                    continue
                v80, v90 = led.v("s", f"family_counts.min_families.{nk}.{dk}.{tk}.power80"), led.v("s", f"family_counts.min_families.{nk}.{dk}.{tk}.power90")
                cells.append(f"{v80 if v80 is not None else '$>$max'} / {v90 if v90 is not None else '$>$max'}")
            rows.append(f"{_key_tex(nk)} & {_key_tex(dk)} & " + " & ".join(cells) + " \\\\")
    (GEN / "planning_family_counts_table.tex").write_text(_table(
        "\\emph{Planning simulation, not an analysis of pilot outcomes.} Smallest number of eligible families (grid in "
        "\\texttt{planning\\_simulation.json}) at which the exact one-sided sign-flip test of the C1$-$C3 FA difference reaches "
        "80\\% / 90\\% power at one-sided $\\alpha=0.025$, by negatives per family ($n$), true mean difference $\\Delta$ and the "
        "between-family SD $\\tau$ taken from the pilot's uncertainty (low, point estimate, high; capped where infeasible). With "
        "$n=1$ the SD does not matter.", "tab:plan-families", "llccc", "$n$ & $\\Delta$ & $\\tau$ low & $\\tau$ mid & $\\tau$ high", rows))
    led.start("planning_fr_valid_per_family_table")
    rows = []
    vp = sim["fr_guardrail"]["valid_per_family"]
    ks = _ordered(next(iter(vp.values())))
    for ik in _ordered(vp):
        cells = []
        for kk in ks:
            x0, x1 = led.v("s", f"fr_guardrail.valid_per_family.{ik}.{kk}.x=0"), led.v("s", f"fr_guardrail.valid_per_family.{ik}.{kk}.x=1")
            cells.append(f"{x0 if x0 is not None else '--'} / {x1 if x1 is not None else '--'}")
        rows.append(f"{_key_tex(ik)} & " + " & ".join(cells) + " \\\\")
    (GEN / "planning_fr_valid_per_family_table.tex").write_text(_table(
        "\\emph{Planning calculation, not an analysis of pilot outcomes.} Valid candidates per family needed for the FR guardrail "
        "(the one-sided 97.5\\% Clopper-Pearson bound on the correction-aware verifier's FR, on the Kish effective sample size "
        "for the stated intra-family correlation, below 0.10) when 0 / 1 false rejections are observed in all; --: not reachable "
        "with up to 40 per family.", "tab:plan-fr", "l" + "c" * len(ks), "ICC & " + " & ".join(f"$K={kk[2:]}$" for kk in ks), rows))
    led.start("planning_method_checks_table")
    rows = []
    for ik in _ordered(sim["fr_guardrail"]["signflip_shifted"]):
        for ck in _ordered(sim["fr_guardrail"]["signflip_shifted"][ik]):
            rows.append(f"FR non-inferiority, shifted sign-flip & {_key_tex(ik)} & {_key_tex(ck)} & "
                        f"{_num(led.v('s', f'fr_guardrail.signflip_shifted.{ik}.{ck}.type1_error'), '.3f')} & -- \\\\")
    for ik in _ordered(sim["fr_guardrail"]["deff_bound"]):
        for ck in _ordered(sim["fr_guardrail"]["deff_bound"][ik]):
            rows.append(f"FR bound, design effect & {_key_tex(ik)} & {_key_tex(ck)} & "
                        f"{_num(led.v('s', f'fr_guardrail.deff_bound.{ik}.{ck}.type1_error'), '.3f')} & "
                        f"{_num(led.v('s', f'fr_guardrail.deff_bound.{ik}.{ck}.power'), '.3f')} \\\\")
    for ck in _ordered(sim["equivalence"]["cells"]):
        rows.append(f"Equivalence TOST, shifted sign-flip & -- & {_key_tex(ck)} & "
                    f"{_num(led.v('s', f'equivalence.cells.{ck}.type1_error_at_margin'), '.3f')} & "
                    f"{_num(led.v('s', f'equivalence.cells.{ck}.power_at_zero'), '.3f')} \\\\")
    frd, eqd = "fr_guardrail.design", "equivalence.design"
    (GEN / "planning_method_checks_table.tex").write_text(_table(
        "\\emph{Planning simulation, not an analysis of pilot outcomes.} Rejection rate at the null boundary (nominal "
        f"{led.v('s', 'fr_guardrail.alpha_one_sided')}) and power of the candidate methods for the FR guardrail (margin "
        f"{led.v('s', 'fr_guardrail.margin')}; true FR {led.v('s', frd + '.boundary_c3')} vs {led.v('s', frd + '.boundary_c1')} at "
        f"the boundary for the shifted test, {led.v('s', frd + '.bound_null_c3')} for the bound, whose ICC is assumed "
        f"{led.v('s', frd + '.icc_assumed')}; power at FR {led.v('s', frd + '.power_c3')}) and for the B2 vs C3/C4 equivalence "
        f"(margin {led.v('s', 'equivalence.margin')}; boundary {led.v('s', eqd + '.boundary_b2')} vs {led.v('s', eqd + '.boundary_c3')}; "
        f"power at equal rates {led.v('s', eqd + '.equal_rate')}). $m$: valid candidates per family; $n$: negatives per family.",
        "tab:plan-methods", "lllcc", "Method & True ICC & Design & Size & Power", rows, size="\\scriptsize"))
    led.start("planning_annotation_hours_table")
    rows = []
    ah = sim["annotation_hours"]
    for t in _ordered(ah["packet_sizes"]):
        base = f"annotation_hours.packet_sizes.{t}"
        rows.append(f"{tex(t)} & {led.v('s', base + '.items')} & {led.v('s', base + '.changed_lines_total')} & "
                    f"{led.v('s', base + '.session_user_words')} & {led.v('s', base + '.requirements')} & "
                    + " & ".join(_num(led.v("s", f"annotation_hours.per_task_hours.{t}.{lvl}.total"), ".1f") for lvl in ("low", "central", "high")) + " \\\\")
    rows.append("All four & -- & -- & -- & -- & " + " & ".join(_num(led.v("s", f"annotation_hours.pilot_total_hours.{lvl}"), ".1f")
                                                             for lvl in ("low", "central", "high")) + " \\\\")
    (GEN / "planning_annotation_hours_table.tex").write_text(_table(
        "\\emph{Planning estimate from assumed reading and decision times, not measurements.} Blinded review-packet sizes per "
        "task (distinct items, changed diff lines, words of the user turns, reference requirements) and the estimated person-hours "
        "for two reviewers plus adjudication (low / central / high assumptions in \\texttt{planning\\_simulation.json}).",
        "tab:plan-hours", "lrrrrrrr", "Task & Items & Changed lines & User words & Req. & Low & Central & High", rows))


# ---------------------------------------------------------------- planning simulation

def _beta_ab(mean: float, sd: float) -> tuple[float, float] | None:
    if sd <= 0:
        return None
    c = mean * (1 - mean) / (sd * sd) - 1
    if c <= 0:
        raise ValueError(f"infeasible beta: mean {mean}, sd {sd}")
    return mean * c, (1 - mean) * c


def _feasible_sd(mean: float, sd: float) -> tuple[float, bool]:
    cap = math.sqrt(0.9 * mean * (1 - mean))
    return (cap, True) if sd > cap else (sd, False)


def _draw(rng: random.Random, mean: float, ab: tuple[float, float] | None) -> float:
    return mean if ab is None else rng.betavariate(*ab)


@dataclass(frozen=True)
class Arms:
    """Per-family acceptance probabilities of two arms on the same candidates: independent Betas."""
    mean_a: float
    sd_a: float
    mean_b: float
    sd_b: float

    def draw_family(self, rng: random.Random, n: int) -> int:
        pa = _draw(rng, self.mean_a, _beta_ab(self.mean_a, self.sd_a))
        pb = _draw(rng, self.mean_b, _beta_ab(self.mean_b, self.sd_b))
        return sum(rng.random() < pa for _ in range(n)) - sum(rng.random() < pb for _ in range(n))


SD_C3 = 0.05  # between-family SD of the correction-aware arm's own rate (assumption)


def _arms(delta: float, base: float, tau: float) -> tuple[Arms, float, bool]:
    """C1 = base + delta, C3 = base; tau is the SD of the per-family true difference."""
    sd_a, capped = _feasible_sd(base + delta, math.sqrt(max(0.0, tau * tau - SD_C3 * SD_C3)))
    return Arms(base + delta, sd_a, base, SD_C3), math.sqrt(sd_a * sd_a + SD_C3 * SD_C3), capped


def pilot_inputs(a: dict) -> dict:
    """Between-family SD of the C1 - C3 FA difference in the pilot, and its uncertainty (chi-square, K - 1 df)."""
    cmp = a["paired_comparisons"]["comparisons"]["initial_plain_vs_full_plain"]["fa"]
    per = cmp["per_family"]
    d = [Fraction(v["a_num"] - v["b_num"], v["den"]) for v in per.values()]
    k = len(d)
    mean = sum(d) / k
    s2 = float(sum((x - mean) ** 2 for x in d) / (k - 1))
    noise = [(v["a_num"] / v["den"]) * (1 - v["a_num"] / v["den"]) / v["den"] + (v["b_num"] / v["den"]) * (1 - v["b_num"] / v["den"]) / v["den"]
             for v in per.values()]
    vbar = sum(noise) / k
    q10, q90 = chi2_ppf(0.10, k - 1), chi2_ppf(0.90, k - 1)
    tau = {"low": math.sqrt(max(0.0, s2 * (k - 1) / q90 - vbar)), "mid": math.sqrt(max(0.0, s2 - vbar)),
           "high": math.sqrt(max(0.0, s2 * (k - 1) / q10 - vbar))}
    nn = a["natural_negatives"]
    natural = {"eligible_families": nn["eligible_families"], "families": nn["families"], "eligibility_exact95": nn["eligibility_exact95"],
               "c1_minus_c3_fa": {f: v["difference"] for f, v in nn["comparison"]["per_family"].items() if v["den"]},
               "p_greater": nn["comparison"]["signflip"]["pooled"]["p_greater"],
               "note": "too few to estimate a between-family SD; the SD below comes from all negatives of the designed pools"}
    return {"natural_negatives": natural, "c1_minus_c3_fa_per_family": {f: float(x) for f, x in zip(per, d)}, "mean": float(mean), "sd_observed": math.sqrt(s2),
            "binomial_noise_variance_mean": vbar, "chi2_df": k - 1, "chi2_q10": q10, "chi2_q90": q90,
            "sd_observed_q10_q90": [math.sqrt(s2 * (k - 1) / q90), math.sqrt(s2 * (k - 1) / q10)], "tau": tau,
            "note": "tau: SD of the true per-family difference, observed variance minus the mean binomial variance, at the 10th "
                    "percentile, point estimate and 90th percentile of the observed SD's chi-square uncertainty"}


def _test_reject(ints: list[int], alpha: float, side: str) -> bool:
    ge = signflip_counter(ints)
    t, total = sum(ints), 1 << len(ints)
    p = ge(t) / total if side == "greater" else ge(-t) / total
    return p <= alpha


def coverage_cell(rng: random.Random, arms: Arms, delta: Fraction, k: int, n: int, reps: int, n_boot: int) -> dict:
    """Coverage of the inverted exact sign-flip interval and of the cluster-bootstrap percentile interval."""
    alpha_att = max(0.025, 1 / (1 << k))
    lo = hi = lo_att = hi_att = boot_cov = 0
    for _ in range(reps):
        diffs = [arms.draw_family(rng, n) for _ in range(k)]
        ints = [delta.denominator * x - delta.numerator * n for x in diffs]  # n * denominator * (d_f - delta)
        hi += _test_reject(ints, 0.025, "greater")
        lo += _test_reject(ints, 0.025, "less")
        hi_att += _test_reject(ints, alpha_att, "greater")
        lo_att += _test_reject(ints, alpha_att, "less")
        means = sorted(sum(diffs[rng.randrange(k)] for _ in range(k)) / (k * n) for _ in range(n_boot))
        boot_cov += means[int(0.025 * (n_boot - 1))] <= float(delta) <= means[int(0.975 * (n_boot - 1))]
    return {"K": k, "reps": reps, "noncoverage_interval_above_truth": hi / reps, "noncoverage_interval_below_truth": lo / reps,
            "signflip_coverage": 1 - (hi + lo) / reps, "attainable_level": 1 - 2 * alpha_att,
            "signflip_coverage_attainable": 1 - (hi_att + lo_att) / reps, "bootstrap_coverage": boot_cov / reps, "bootstrap_resamples": n_boot}


def power_cell(rng: random.Random, arms: Arms, k: int, n: int, reps: int) -> float:
    return sum(_test_reject([arms.draw_family(rng, n) for _ in range(k)], 0.025, "greater") for _ in range(reps)) / reps


def _rng(*parts) -> random.Random:
    return random.Random(":".join(str(x) for x in (SEED, *parts)))


COVERAGE_SCENARIOS = {  # name: (C3 rate, delta, tau key or fixed tau, negatives per family)
    "null_rare": (0.05, Fraction(0), 0.05, 2),
    "delta20_mid": (0.05, Fraction(1, 5), "mid", 2),
    "delta35_high_pilotlike": (0.05, Fraction(7, 20), "high", 4),
}
K_COVERAGE = (4, 6, 8, 12, 20)
K_POWER = (6, 8, 10, 12, 16, 20, 24, 30, 40, 50, 60, 80, 100, 120, 150, 200)
DELTAS = {"delta=10pp": Fraction(1, 10), "delta=20pp": Fraction(1, 5), "delta=35pp": Fraction(7, 20)}
N_NEG = (1, 2, 4)


def sim_coverage(inputs: dict, reps: int, n_boot: int) -> dict:
    out: dict = {"alpha_two_sided": 0.05, "scenarios": {}}
    for name, (base, delta, tau_k, n) in COVERAGE_SCENARIOS.items():
        tau = inputs["tau"][tau_k] if isinstance(tau_k, str) else tau_k
        arms, tau_eff, capped = _arms(float(delta), base, tau)
        cells = {f"K={k}": coverage_cell(_rng("coverage", name, k), arms, delta, k, n, reps, n_boot) for k in K_COVERAGE}
        out["scenarios"][name] = {"c3_rate": base, "c1_rate": base + float(delta), "delta": float(delta), "tau_requested": tau,
                                  "tau_effective": tau_eff, "tau_capped": capped, "negatives_per_family": n, "cells": cells}
    return out


def sim_family_counts(inputs: dict, reps: int) -> dict:
    out: dict = {"alpha_one_sided": 0.025, "c3_rate": 0.05, "reps": reps, "K_grid": list(K_POWER), "power": {}, "min_families": {},
                 "tau_used": {}}
    for n in N_NEG:
        nk = f"n_neg={n}"
        out["power"][nk], out["min_families"][nk] = {}, {}
        for dk, delta in DELTAS.items():
            out["power"][nk][dk], out["min_families"][nk][dk] = {}, {}
            for tk in (("tau=mid",) if n == 1 else ("tau=low", "tau=mid", "tau=high")):
                arms, tau_eff, capped = _arms(float(delta), 0.05, inputs["tau"][tk.split("=")[1]])
                out["tau_used"].setdefault(dk, {})[tk] = {"tau_effective": tau_eff, "capped": capped}
                curve: dict = {}
                for k in K_POWER:
                    curve[f"K={k}"] = power_cell(_rng("power", n, dk, tk, k), arms, k, n, reps)
                    if len(curve) >= 2 and min(list(curve.values())[-2:]) >= 0.97:
                        break  # power is (nearly) monotone in K; the rest of the grid adds nothing
                out["power"][nk][dk][tk] = curve
                first = lambda target: next((int(kk[2:]) for kk, v in curve.items() if v >= target), None)  # noqa: E731
                out["min_families"][nk][dk][tk] = {"power80": first(0.80), "power90": first(0.90)}
                k80 = first(0.80)
                out.setdefault("screened_families_for_power80", {}).setdefault(nk, {}).setdefault(dk, {})[tk] = {
                    f"eligible_share={int(e * 100)}pct": None if k80 is None else math.ceil(k80 / e) for e in (0.5, 0.8, 1.0)}
    return out


def _deff_bound_rejects(x: int, k: int, m: int, rho: float) -> bool:
    """FR guardrail met: the one-sided 97.5% Clopper-Pearson bound, on the Kish effective sample size, is below 0.10."""
    deff = 1 + (m - 1) * rho
    n_eff = int(k * m / deff)
    x_eff = min(n_eff, math.ceil(x / deff - 1e-12))
    return cp_upper(x_eff, n_eff) < 0.10


def _beta_icc(mean: float, rho: float) -> tuple[float, float] | None:
    if rho <= 0:
        return None
    c = 1 / rho - 1
    return mean * c, (1 - mean) * c


FR_DESIGN = {"boundary_c1": 0.02, "boundary_c3": 0.12, "bound_null_c3": 0.10, "power_c3": 0.02, "icc_assumed": 0.3}
EQ_DESIGN = {"boundary_b2": 0.15, "boundary_c3": 0.05, "equal_rate": 0.05, "sd_between_families": 0.05}


def sim_fr_guardrail(reps: int) -> dict:
    """Checks of the FR non-inferiority guardrail methods, and the valid candidates per family it needs."""
    out: dict = {"margin": 0.10, "alpha_one_sided": 0.025, "reps": reps, "design": FR_DESIGN, "signflip_shifted": {}, "deff_bound": {},
                 "valid_per_family": {}}
    # (a) The shifted sign-flip test of FR_C3 - FR_C1 < 0.10, at the boundary (true difference 0.10).
    for rho in (0.0, 0.3):
        for m in (2, 4):
            for k in (10, 20, 40):
                c1, c3 = FR_DESIGN["boundary_c1"], FR_DESIGN["boundary_c3"]
                rng, ab1, ab3, rej = _rng("fr-signflip", rho, m, k), _beta_icc(c1, rho), _beta_icc(c3, rho), 0
                for _ in range(reps):
                    ints = []
                    for _f in range(k):
                        r1, r3 = _draw(rng, c1, ab1), _draw(rng, c3, ab3)
                        x1, x3 = sum(rng.random() < r1 for _ in range(m)), sum(rng.random() < r3 for _ in range(m))
                        ints.append(10 * (x3 - x1) - m)  # 10 m ((x3 - x1)/m - 1/10)
                    rej += _test_reject(ints, 0.025, "less")
                out["signflip_shifted"].setdefault(f"icc={int(rho * 100)}pct", {})[f"m={m}_K={k}"] = {"type1_error": rej / reps, "m": m, "K": k}
    # (b) The design-effect Clopper-Pearson bound on FR_C3 alone (conservative, since FR_C1 >= 0), assumed ICC 0.3.
    for rho_true in (0.0, 0.3, 0.6):
        for m in (2, 3, 4):
            for k in (20, 30, 40):
                cell = {}
                for fr_true, what in ((FR_DESIGN["bound_null_c3"], "type1_error"), (FR_DESIGN["power_c3"], "power")):
                    rng, ab, hit = _rng("fr-deff", rho_true, m, k, fr_true), _beta_icc(fr_true, rho_true), 0
                    for _ in range(reps):
                        x = 0
                        for _f in range(k):
                            r = _draw(rng, fr_true, ab)
                            x += sum(rng.random() < r for _ in range(m))
                        hit += _deff_bound_rejects(x, k, m, FR_DESIGN["icc_assumed"])
                    cell[what] = hit / reps
                out["deff_bound"].setdefault(f"icc_true={int(rho_true * 100)}pct", {})[f"m={m}_K={k}"] = {"m": m, "K": k, **cell}
    # (c) Valid candidates per family for the guardrail to be met with 0 or 1 observed false rejections.
    for rho in (0.0, 0.1, 0.3, 0.5):
        row = {}
        for k in (10, 15, 20, 30, 40, 60):
            need = {}
            for x in (0, 1):
                need[f"x={x}"] = next((m for m in range(1, 41) if _deff_bound_rejects(x, k, m, rho)), None)
            row[f"K={k}"] = need
        out["valid_per_family"][f"icc={int(rho * 100)}pct"] = row
    out["one_per_family_bound"] = {f"K={k}": {"bound_with_0": cp_upper(0, k), "met_with_0": cp_upper(0, k) < 0.10}
                                   for k in (20, 30, 36, 40, 60)}
    return out


def sim_equivalence(reps: int) -> dict:
    """The shifted sign-flip TOST for B2 vs C3/C4 FA, margin 0.10: level at the margin and power at zero difference."""
    out: dict = {"margin": 0.10, "alpha_one_sided": 0.025, "reps": reps, "design": EQ_DESIGN, "cells": {}}
    sd, c3 = EQ_DESIGN["sd_between_families"], EQ_DESIGN["boundary_c3"]
    for n in (2, 4):
        for k in (10, 20, 40, 60):
            cell = {}
            for what, mean_a in (("type1_error_at_margin", EQ_DESIGN["boundary_b2"]), ("power_at_zero", EQ_DESIGN["equal_rate"])):
                arms, rng, eq = Arms(mean_a, sd, c3, sd), _rng("equivalence", n, k, what), 0
                for _ in range(reps):
                    diffs = [arms.draw_family(rng, n) for _ in range(k)]
                    up = _test_reject([10 * x - n for x in diffs], 0.025, "less")
                    low = _test_reject([10 * x + n for x in diffs], 0.025, "greater")
                    eq += up and low
                cell[what] = eq / reps
            out["cells"][f"n={n}_K={k}"] = {"n": n, "K": k, **cell}
    return out


HOURS = {  # minutes unless stated; low = fast reviewer, high = slow reviewer (assumptions, not measurements)
    "reviewers_per_task": 2,
    "session_words_per_minute": {"low": 200, "central": 150, "high": 100},
    "contract_words_per_minute": {"low": 150, "central": 100, "high": 70},
    "per_requirement_decision": {"low": 2, "central": 3, "high": 5},
    "per_candidate_fixed": {"low": 6, "central": 10, "high": 20},
    "per_changed_diff_line": {"low": 0.1, "central": 0.2, "high": 0.4},
    "per_candidate_sandbox": {"low": 2, "central": 5, "high": 10},
    "per_task_setup": {"low": 10, "central": 15, "high": 30},
    "adjudicated_share_of_items": {"low": 0.1, "central": 0.2, "high": 0.35},
    "per_adjudication": {"low": 10, "central": 15, "high": 25},
}


def packet_sizes(task_dirs: Sequence[Path]) -> dict:
    """What a reviewer reads per task in the blinded packet, from the packet builder's own functions."""
    from tracecontract.review import _contract_text, _user_turns, held_out

    out = {}
    for td in task_dirs:
        m = load(td / "task.json", TaskManifest)
        ref = load(td / m.contracts["reference"], TaskContract)
        groups: dict[str, list[str]] = {}
        for c in held_out(td):
            groups.setdefault(_norm_patch(c.patch), []).append(c.candidate_id)
        items = []
        for diff in groups:
            lines = diff.splitlines()
            items.append({"diff_lines": len(lines), "changed_lines": sum(1 for x in lines if x[:1] in "+-" and x[:3] not in ("+++", "---"))})
        out[m.task_id] = {"session_user_words": len(_user_turns(td, ROOT).split()), "contract_words": len(_contract_text(ref).split()),
                          "requirements": len(ref.requirements), "items": len(items), "candidates": sum(len(v) for v in groups.values()),
                          "changed_lines_total": sum(x["changed_lines"] for x in items), "diff_lines_total": sum(x["diff_lines"] for x in items)}
    return out


def _task_minutes(s: dict, level: str) -> dict:
    h = HOURS
    reviewer = (h["per_task_setup"][level] + s["session_user_words"] / h["session_words_per_minute"][level]
                + s["contract_words"] / h["contract_words_per_minute"][level] + s["requirements"] * h["per_requirement_decision"][level]
                + s["items"] * (h["per_candidate_fixed"][level] + h["per_candidate_sandbox"][level])
                + s["changed_lines_total"] * h["per_changed_diff_line"][level])
    adjudication = h["adjudicated_share_of_items"][level] * s["items"] * h["per_adjudication"][level]
    return {"per_reviewer": reviewer, "adjudication": adjudication, "total": h["reviewers_per_task"] * reviewer + adjudication}


def annotation_hours(task_dirs: Sequence[Path], family_targets: Sequence[int]) -> dict:
    sizes = packet_sizes(task_dirs)
    per_task = {t: {lvl: {k: v / 60 for k, v in _task_minutes(s, lvl).items()} for lvl in ("low", "central", "high")} for t, s in sizes.items()}
    tot = {lvl: sum(v[lvl]["total"] for v in per_task.values()) for lvl in ("low", "central", "high")}
    n = len(sizes)
    mean = {k: sum(s[k] for s in sizes.values()) / n for k in ("session_user_words", "contract_words", "requirements", "items", "changed_lines_total")}
    per_item_lines = mean["changed_lines_total"] / mean["items"]
    projection = {}
    for items in (6, 8):
        fam = dict(mean, items=items, changed_lines_total=per_item_lines * items)
        per_fam = {lvl: _task_minutes(fam, lvl)["total"] / 60 for lvl in ("low", "central", "high")}
        projection[f"items={items}"] = {"per_family_hours": per_fam,
                                        "families": {f"K={k}": {lvl: per_fam[lvl] * k for lvl in per_fam} for k in family_targets}}
    return {"assumptions_minutes": HOURS, "packet_sizes": sizes, "per_task_hours": per_task, "pilot_total_hours": tot,
            "mean_changed_lines_per_item": per_item_lines, "projection": projection,
            "note": "assumed reading and decision times, not measurements; replace them by the times recorded in the first two reviews"}


def run_simulation(a: dict, tasks_root: Path, reps: int = 1000, cov_reps: int = 2000, n_boot: int = 400) -> dict:
    inputs = pilot_inputs(a)
    return {"tag": PLAN_TAG, "seed": SEED, "python": platform.python_version(),
            "generated_by": "python scripts/exploratory_reanalysis.py",
            "dgp": {"families": "independent; per family, each arm's acceptance probability is drawn from a Beta distribution with "
                                "the stated mean and SD (arms independent given the family); candidates are Bernoulli given it",
                    "c3_sd_between_families": SD_C3,
                    "tau": "SD of the per-family true difference C1 - C3; the C1 SD is chosen to give it, capped at 0.9 of the "
                           "largest Beta variance where the pilot's upper value is infeasible",
                    "pool_composition": "the pilot's pools were designed (2 alternatives, 5 near misses mostly targeting the "
                                        "correction, and the observed pre-correction state per family), so its between-family SD "
                                        "describes designed pools, not natural variation; it is used here only as a planning input"},
            "pilot_inputs": inputs,
            "coverage": sim_coverage(inputs, cov_reps, n_boot),
            "family_counts": sim_family_counts(inputs, reps),
            "fr_guardrail": sim_fr_guardrail(cov_reps),
            "equivalence": sim_equivalence(cov_reps),
            "annotation_hours": annotation_hours([tasks_root / t for t in a["meta"]["families"]], (10, 20, 30, 40, 60, 100))}


# ---------------------------------------------------------------- main

def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--tasks", type=Path, default=ROOT / "tasks")
    ap.add_argument("--audits", type=Path, default=ROOT / "results" / "audits")
    ap.add_argument("--no-simulation", action="store_true", help="reuse the existing planning_simulation.json")
    args = ap.parse_args(argv)
    p = load_pilot(args.run, args.tasks, args.audits)
    a = build_analysis(p)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(a, args.out / "analysis.json")
    (args.out / "analysis.md").write_text(to_markdown(a), encoding="utf-8")
    sim_path = args.out / "planning_simulation.json"
    if args.no_simulation:
        sim = json.loads(sim_path.read_text()) if sim_path.exists() else None
    else:
        write_json(run_simulation(a, args.tasks), sim_path)
        sim = json.loads(sim_path.read_text())  # tables read what was written, as with --no-simulation
    led = write_tables(a, sim, args.out)
    LEDGER.write_text("\n".join(led.lines) + "\n", encoding="utf-8")
    print(f"wrote {_rel(args.out)}/analysis.json, analysis.md{', planning_simulation.json' if not args.no_simulation else ''}; "
          f"tables in {_rel(GEN)}; ledger with {sum(1 for x in led.lines if x.startswith('- ['))} values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
