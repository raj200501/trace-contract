"""Reward-fidelity metrics with task-family clustering.

Definitions (fixed in experiments/protocol.md before the main experiment):

* accept(V, c) := outcome(V, c) == "pass". Every other outcome is a rejection in
  the primary analysis; infrastructure outcomes (environment_failure,
  verifier_error, timeout, unresolved) are also reported separately, and a
  sensitivity analysis excludes them.
* False acceptance FA(V) = P(accept | label = invalid).
* False rejection  FR(V) = P(reject | label = valid).
* Labels are final human labels; candidates whose label is ``ambiguous`` or
  missing are excluded from FA/FR and counted.

Uncertainty: percentile intervals from a cluster bootstrap that resamples task
families (the independent unit), never individual candidates or mutants.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

INFRA = {"environment_failure", "verifier_error", "timeout", "unresolved"}


@dataclass(frozen=True)
class Row:
    task_id: str
    family_id: str
    candidate_id: str
    condition: str
    outcome: str
    label: str | None  # "valid" | "invalid" | "ambiguous" | None
    origin: str = ""
    negative_type: str = ""  # e.g. "correction_violating", "other_invalid"


@dataclass
class Rate:
    num: int
    den: int

    @property
    def value(self) -> float | None:
        return None if self.den == 0 else self.num / self.den

    def __str__(self) -> str:
        v = self.value
        return "n/a (0/0)" if v is None else f"{v:.3f} ({self.num}/{self.den})"


@dataclass
class ConditionSummary:
    condition: str
    fa: Rate
    fr: Rate
    infra: Rate
    excluded_unlabeled: int
    fa_macro: float | None
    fr_macro: float | None
    per_task: dict[str, dict[str, Rate]] = field(default_factory=dict)
    fa_ci: tuple[float, float] | None = None
    fr_ci: tuple[float, float] | None = None


def _rates(rows: Iterable[Row], exclude_infra: bool = False) -> tuple[Rate, Rate, Rate, int]:
    fa_n = fa_d = fr_n = fr_d = inf_n = tot = excl = 0
    for r in rows:
        tot += 1
        if r.outcome in INFRA:
            inf_n += 1
            if exclude_infra:
                continue
        if r.label not in ("valid", "invalid"):
            excl += 1
            continue
        acc = r.outcome == "pass"
        if r.label == "invalid":
            fa_d += 1
            fa_n += acc
        else:
            fr_d += 1
            fr_n += not acc
    return Rate(fa_n, fa_d), Rate(fr_n, fr_d), Rate(inf_n, tot), excl


def _macro(per_task: dict[str, dict[str, Rate]], key: str) -> float | None:
    vals = [d[key].value for d in per_task.values() if d[key].value is not None]
    return None if not vals else sum(vals) / len(vals)


def summarize(rows: list[Row], *, condition: str, exclude_infra: bool = False, n_boot: int = 2000, seed: int = 0) -> ConditionSummary:
    rows = [r for r in rows if r.condition == condition]
    fa, fr, infra, excl = _rates(rows, exclude_infra)
    by_task: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_task[r.task_id].append(r)
    per_task = {}
    for t, rs in sorted(by_task.items()):
        tfa, tfr, tinf, _ = _rates(rs, exclude_infra)
        per_task[t] = {"fa": tfa, "fr": tfr, "infra": tinf}
    s = ConditionSummary(condition, fa, fr, infra, excl, _macro(per_task, "fa"), _macro(per_task, "fr"), per_task)
    s.fa_ci = cluster_bootstrap(rows, "fa", n_boot=n_boot, seed=seed, exclude_infra=exclude_infra)
    s.fr_ci = cluster_bootstrap(rows, "fr", n_boot=n_boot, seed=seed, exclude_infra=exclude_infra)
    return s


def cluster_bootstrap(rows: list[Row], metric: str, *, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05,
                      exclude_infra: bool = False) -> tuple[float, float] | None:
    """Percentile CI for pooled FA or FR, resampling task families."""
    fams: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        fams[r.family_id].append(r)
    keys = sorted(fams)
    if len(keys) < 2:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        sample = [r for k in (rng.choice(keys) for _ in keys) for r in fams[k]]
        fa, fr, _, _ = _rates(sample, exclude_infra)
        v = (fa if metric == "fa" else fr).value
        if v is not None:
            stats.append(v)
    if len(stats) < n_boot * 0.5:
        return None
    stats.sort()
    lo = stats[int((alpha / 2) * (len(stats) - 1))]
    hi = stats[int((1 - alpha / 2) * (len(stats) - 1))]
    return lo, hi


def paired_difference(rows: list[Row], cond_a: str, cond_b: str, metric: str, *, n_boot: int = 2000, seed: int = 0) -> dict:
    """FA/FR(cond_a) - FA/FR(cond_b) on candidates scored by BOTH conditions."""
    a = {(r.task_id, r.candidate_id): r for r in rows if r.condition == cond_a}
    b = {(r.task_id, r.candidate_id): r for r in rows if r.condition == cond_b}
    common = sorted(set(a) & set(b))
    ra = [a[k] for k in common]
    rb = [b[k] for k in common]

    def stat(xa: list[Row], xb: list[Row]) -> float | None:
        fa_a, fr_a, _, _ = _rates(xa)
        fa_b, fr_b, _, _ = _rates(xb)
        va, vb = ((fa_a, fa_b) if metric == "fa" else (fr_a, fr_b))
        if va.value is None or vb.value is None:
            return None
        return va.value - vb.value

    point = stat(ra, rb)
    fams: dict[str, list[int]] = defaultdict(list)
    for i, k in enumerate(common):
        fams[a[k].family_id].append(i)
    keys = sorted(fams)
    ci = None
    if len(keys) >= 2 and point is not None:
        rng = random.Random(seed)
        vals = []
        for _ in range(n_boot):
            idx = [i for kk in (rng.choice(keys) for _ in keys) for i in fams[kk]]
            v = stat([ra[i] for i in idx], [rb[i] for i in idx])
            if v is not None:
                vals.append(v)
        if vals:
            vals.sort()
            ci = (vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))])
    # Discordant pairs (McNemar-style counts), useful with tiny samples.
    disc = {"a_accepts_b_rejects": 0, "a_rejects_b_accepts": 0}
    for x, y in zip(ra, rb):
        if (metric == "fa" and x.label == "invalid") or (metric == "fr" and x.label == "valid"):
            xa, ya = x.outcome == "pass", y.outcome == "pass"
            if xa and not ya:
                disc["a_accepts_b_rejects"] += 1
            elif ya and not xa:
                disc["a_rejects_b_accepts"] += 1
    return {"metric": metric, "a": cond_a, "b": cond_b, "n_common": len(common), "n_families": len(keys),
            "difference": point, "ci95": ci, "discordant": disc}
