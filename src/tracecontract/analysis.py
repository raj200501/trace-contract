"""Analysis of recorded evaluation runs (tables are generated from records only).

Inputs: ``results/runs/<run_id>/results.jsonl`` + ``manifest.json`` and the task
directories (candidate labels, reference contracts). Output:
``analysis.json`` and ``analysis.md`` in the run directory.

Label policy:
* primary: final human labels only (``Candidate.final_label``);
* ``allow_proposed=True`` (automated pilot): fall back to the latest proposed label
  (model / construction). Every table produced this way is marked as an automated
  pilot and must not be described as validated ground truth.

Populations and candidate strata:
* every row carries its task's population; a run whose tasks come from more than one
  population is refused (:class:`MixedPopulations`) unless ``pool_populations=True``
  (``--pool-populations``), which marks the pooled tables and reports each population on
  its own rows (``by_population``);
* every row carries its candidate's stratum (:mod:`tracecontract.strata`): ``task`` for
  the task's own candidates, else the stratum the run graded it in; candidate strata are
  pooled, and also reported one by one (``by_stratum``).

These keys appear only for a run with a population other than ``controlled`` or with a
stratum candidate, so runs recorded before them (pilot-v0.2 to pilot-v0.3.3) regenerate
byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from .metrics import ConditionSummary, Row, paired_difference, summarize
from .schemas import Candidate, CandidateOrigin, LabelerKind, Population, TaskContract, TaskManifest, VerificationResult
from .store import load, read_jsonl, write_json
from .strata import TASK_STRATUM, StratumError, run_stratum_candidates

PILOT_LABELER = "builder:refcheck+regression+construction:v1"  # decision log D19
_CHECKS: dict[str, dict] = {}  # construction checks by candidate id (filled by build_rows for policy "check")
CONSTRUCTED = (CandidateOrigin.constructed_near_miss, CandidateOrigin.valid_alternative)
# The population of every run recorded before populations were reported; a run with another
# population, or with more than one, gets the population keys of the output.
DEFAULT_POPULATION = Population.controlled.value


class MixedPopulations(ValueError):
    """The run's tasks come from more than one population and pooling was not asked for (``--pool-populations``)."""


def candidate_label(c: Candidate, policy: str):
    """Label used for analysis under a label policy.

    * ``human``: adjudicated / latest human label only (primary analysis).
    * ``pilot``: human label if present, else the pre-specified automated proposal
      (rule D19, labeler ``PILOT_LABELER``); candidates without one are unlabeled.
    * ``construction`` (exploratory, not pre-specified): human label if present, else
      the construction label for constructed candidates and the D19 proposal for the
      others.
    * ``check`` (exploratory, post hoc): human label if present, else the independent
      construction check's assessed label (``labels/construction_checks.json``); unsure
      or unchecked candidates are unlabeled.
    """
    human = c.final_label()
    if human is not None or policy == "human":
        return human
    if policy == "check" and c.candidate_id in _CHECKS:
        assessed = _CHECKS[c.candidate_id].get("assessed_label")
        if assessed in ("valid", "invalid"):
            return SimpleNamespace(value=assessed, violated_requirements=_CHECKS[c.candidate_id].get("violated_requirements", []))
        return None
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
    if not later:  # e.g. only REGRESSION: no reference requirement to classify by
        return "unspecified"
    return "correction_violating" if any(later) else "initial_violating"


def build_rows(run_dir: Path, tasks_root: Path, *, allow_proposed: bool, policy: str | None = None) -> tuple[list[Row], dict]:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    results = read_jsonl(run_dir / "results.jsonl", VerificationResult)
    policy = policy or ("pilot" if allow_proposed else "human")
    meta: dict = {"label_policy": "proposed labels allowed (automated pilot)" if allow_proposed else "human labels only",
                  "label_rule": policy, "tasks": {},
                  "harness_versions": dict(Counter(r.harness_version for r in results))}
    cands: dict[tuple[str, str], Candidate] = {}
    stratum_of: dict[tuple[str, str], str] = {}  # stratum candidates only; the task's own are TASK_STRATUM
    fam: dict[str, str] = {}
    pop: dict[str, str] = {}
    refs: dict[str, TaskContract | None] = {}
    first: dict[str, str | None] = {}
    conditions: dict[tuple[str, str], str] = {}
    if policy == "check":
        _CHECKS.clear()
        for t in manifest["tasks"]:
            cp = tasks_root / t["task_id"] / "labels" / "construction_checks.json"
            if cp.exists():
                _CHECKS.update(json.loads(cp.read_text()).get("checks", {}))
    for t in manifest["tasks"]:
        tid = t["task_id"]
        tdir = tasks_root / tid
        m = load(tdir / "task.json", TaskManifest)
        fam[tid] = m.family_id
        pop[tid] = m.population.value
        for p in m.candidates:
            c = load(tdir / p, Candidate)
            cands[(tid, c.candidate_id)] = c
        for cid, (name, _, c) in run_stratum_candidates(tdir, t).items():  # as the run recorded them
            if (tid, cid) in cands:
                raise StratumError(f"{tid}: candidate {cid} of stratum {name!r} has the id of one of the task's own candidates")
            cands[(tid, cid)] = c
            stratum_of[(tid, cid)] = name
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
                        negative_type=_negative_type(c, label, refs[r.task_id], first[r.task_id]),
                        population=pop[r.task_id], stratum=stratum_of.get((r.task_id, r.candidate_id), TASK_STRATUM)))
    meta["n_results"] = len(results)
    return rows, meta


def _populations(rows: list[Row]) -> dict[str, list[str]]:
    """The populations of the rows' tasks: ``{population: sorted task ids}``."""
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        out[r.population].add(r.task_id)
    return {p: sorted(ts) for p, ts in sorted(out.items())}


def _describe(populations: dict[str, list[str]]) -> str:
    return "; ".join(f"{p}: {', '.join(ts)}" for p, ts in populations.items())


def _stratum_candidates(run_dir: Path, tasks_root: Path) -> dict[str, dict[str, tuple[str, str, Candidate]]]:
    """The stratum candidates the run graded, by task id (:func:`strata.run_stratum_candidates`); empty without strata."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    found = {t["task_id"]: run_stratum_candidates(tasks_root / t["task_id"], t) for t in manifest["tasks"]}
    return {tid: f for tid, f in found.items() if f}


def _condition_rates(s: ConditionSummary) -> dict:
    """FA, FR, infrastructure outcomes and exclusions of one condition summary, as the output records them."""
    return {"false_acceptance": {"rate": s.fa.value, "num": s.fa.num, "den": s.fa.den, "ci95": s.fa_ci, "macro": s.fa_macro,
                                 "exact95": s.fa_exact, "ci95_degenerate": s.fa_ci_degenerate},
            "false_rejection": {"rate": s.fr.value, "num": s.fr.num, "den": s.fr.den, "ci95": s.fr_ci, "macro": s.fr_macro,
                                "exact95": s.fr_exact, "ci95_degenerate": s.fr_ci_degenerate},
            "infrastructure": {"num": s.infra.num, "den": s.infra.den},
            "excluded_unlabeled_or_ambiguous": s.excluded_unlabeled}


def _by_group(primary: list[Row], conds: list[str], attr: str, n_boot: int) -> dict:
    """FA/FR by condition within each value of ``attr`` (``population`` or ``stratum``), on that group's rows only."""
    out: dict = {}
    for g in sorted({getattr(r, attr) for r in primary}, key=lambda g: (g != TASK_STRATUM, g)):
        sub = [r for r in primary if getattr(r, attr) == g]
        out[g] = {"tasks": sorted({r.task_id for r in sub}), "n_families": len({r.family_id for r in sub}),
                  "conditions": {c: _condition_rates(summarize(sub, condition=c, n_boot=n_boot))
                                 for c in conds if any(r.condition == c for r in sub)}}
    return out


def analyze(run_dir: Path, tasks_root: Path, *, allow_proposed: bool = False, n_boot: int = 2000,
            exclude_origins: tuple[str, ...] = ("reference", "noop"), pool_populations: bool = False) -> dict:
    rows, meta = build_rows(run_dir, tasks_root, allow_proposed=allow_proposed)
    populations = _populations(rows)
    if len(populations) > 1 and not pool_populations:  # refused before anything is written
        raise MixedPopulations(f"the run mixes {len(populations)} populations ({_describe(populations)}), and populations are "
                               "never pooled silently: pass pool_populations (--pool-populations) to pool them and report "
                               "each population separately, or evaluate each population in a run of its own")
    # The reference solution is development data for every generator (it is shown to
    # them) and the no-op is a sanity check; both are reported separately and excluded
    # from the primary FA/FR (pre-specified in experiments/protocol.md).
    primary = [r for r in rows if r.origin not in exclude_origins]
    conds = [c for c in CONDITION_ORDER if any(r.condition == c for r in rows)]
    # Population and stratum keys only where they say something (see the module docstring).
    with_populations = any(p != DEFAULT_POPULATION for p in populations)
    with_strata = any(r.stratum != TASK_STRATUM for r in rows)
    out: dict = {"meta": meta, "conditions": {}, "comparisons": [], "sanity": {}, "by_negative_type": {},
                 "outcome_counts": {}, "per_task": {}}
    for c in conds:
        s = summarize(primary, condition=c, n_boot=n_boot)
        sx = summarize(primary, condition=c, exclude_infra=True, n_boot=n_boot)
        out["conditions"][c] = {
            **_condition_rates(s),
            "per_task_rates": {t: {"fa_num": v["fa"].num, "fa_den": v["fa"].den, "fr_num": v["fr"].num, "fr_den": v["fr"].den}
                               for t, v in s.per_task.items()},
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
                                      "negative_type": r.negative_type, "outcome": r.outcome,
                                      **({"stratum": r.stratum} if with_strata else {})} for r in sub]
    out["n_tasks"] = len(tasks)
    out["n_families"] = len({r.family_id for r in rows})
    if with_populations:
        out["meta"]["populations"] = populations
    if len(populations) > 1:
        out["meta"]["population_pooling"] = (f"pooled across {len(populations)} populations ({_describe(populations)}) "
                                             "with --pool-populations; by_population reports each population separately")
        out["by_population"] = _by_group(primary, conds, "population", n_boot)
    stratum_cands = ({t: f for t, f in _stratum_candidates(run_dir, tasks_root).items() if t in tasks}
                     if with_strata else {})
    if with_strata:
        manifest = json.loads((run_dir / "manifest.json").read_text())
        out["meta"]["strata"] = {t["task_id"]: t["strata"] for t in manifest["tasks"] if t.get("strata") and t["task_id"] in tasks}
        out["by_stratum"] = _by_group(primary, conds, "stratum", n_boot)
    if allow_proposed:
        # Exploratory (not pre-specified): constructed candidates labeled by construction intent.
        srows, _ = build_rows(run_dir, tasks_root, allow_proposed=True, policy="construction")
        sprim = [r for r in srows if r.origin not in exclude_origins]
        out["sensitivity_construction_labels"] = {}
        for c in conds:
            ss = summarize(sprim, condition=c, n_boot=n_boot)
            out["sensitivity_construction_labels"][c] = {
                "fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den, "fa_ci95": ss.fa_ci,
                "fa_exact95": ss.fa_exact, "fa_ci95_degenerate": ss.fa_ci_degenerate,
                "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den, "fr_ci95": ss.fr_ci,
                "fr_exact95": ss.fr_exact, "fr_ci95_degenerate": ss.fr_ci_degenerate}
    if allow_proposed:
        out.update(_post_hoc(run_dir, tasks_root, rows, primary, conds, n_boot, exclude_origins,
                             {t: [c for _, _, c in f.values()] for t, f in stratum_cands.items()}))
    by_name: dict[str, dict[str, list[Candidate]]] = {}  # {task: {stratum: candidates}}
    for t, f in stratum_cands.items():
        for name, _, c in f.values():
            by_name.setdefault(t, {}).setdefault(name, []).append(c)
    out["labels"] = label_summary([tasks_root / t for t in tasks], strata=by_name)
    out["coverage"] = {t: contract_coverage(tasks_root / t) for t in tasks}
    out["mapping_agreement"] = {t: mapping_agreement(tasks_root / t) for t in tasks}
    out["meta"]["inputs"] = _input_hashes(run_dir, [tasks_root / t for t in tasks],
                                          [(tasks_root / t, rel) for t, f in stratum_cands.items() for _, rel, _ in f.values()])
    write_json(out, run_dir / "analysis.json")
    (run_dir / "analysis.md").write_text(to_markdown(out), encoding="utf-8")
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_revision(cwd: Path) -> str | None:
    """HEAD, with ``+dirty`` when tracked files differ from it (as in evaluate.code_revision)."""
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True).stdout.strip() or None
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd,
                               capture_output=True, text=True).stdout.strip()
    except OSError:
        return None
    return None if rev is None else rev + ("+dirty" if dirty else "")


def _input_hashes(run_dir: Path, task_dirs: list[Path], stratum_files: list[tuple[Path, str]] | None = None) -> dict:
    """Revision and file hashes of every input the analysis read (labels, contracts, mappings, checks) and of its code.

    ``stratum_files`` are the stratum candidates read, as ``(task_dir, file relative to it)``; with any,
    the hashes also cover them and ``strata.py``, which reads them (it reads nothing for a run without strata).
    """
    rev = _git_revision(run_dir)
    files: dict[str, str] = {"results.jsonl": _sha(run_dir / "results.jsonl"), "manifest.json": _sha(run_dir / "manifest.json")}
    pkg = Path(__file__).resolve().parent
    for name in ("analysis.py", "metrics.py", "schemas.py", "store.py", "patches.py") + (("strata.py",) if stratum_files else ()):
        files[f"code/{name}"] = _sha(pkg / name)
    for td in task_dirs:
        for pat in ("task.json", "candidates/*.json", "contracts/*.json", "labels/construction_checks.json",
                    "labels/duplicates.json", "verifiers/repo_tests/upstream_check_ids.json"):
            for f in sorted(td.glob(pat)):
                files[f"{td.name}/{f.relative_to(td)}"] = _sha(f)
    for td, rel in stratum_files or []:
        files[f"{td.name}/{rel}"] = _sha(td / rel)
    return {"git_revision": rev, "files_sha256": files}


_INDEX = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+.*$", re.M)


def _norm_patch(patch: str) -> str:
    """The patch as graded (protected test/config paths removed), without git index lines."""
    from .patches import filter_patch

    graded, _ = filter_patch(patch)
    return _INDEX.sub("", graded).strip()


def _post_hoc(run_dir: Path, tasks_root: Path, rows: list[Row], primary: list[Row], conds: list[str], n_boot: int,
              exclude_origins: tuple[str, ...], stratum_cands: dict[str, list[Candidate]] | None = None) -> dict:
    """Exploratory analyses added after the internal review (protocol v0.4; never primary).

    ``stratum_cands`` (by task id) are the stratum candidates the run graded; the duplicate check covers them too.
    """
    out: dict = {}
    # 1. Near-miss acceptance by D19 status (confirmed invalid vs ambiguous).
    xt: dict = {}
    for c in conds:
        nm = [r for r in rows if r.condition == c and r.origin == "constructed_near_miss"]
        xt[c] = {k: {"accepted": sum(r.outcome == "pass" for r in nm if r.label == lab), "n": sum(r.label == lab for r in nm)}
                 for k, lab in (("confirmed_invalid", "invalid"), ("ambiguous", "ambiguous"))}
    out["near_miss_crosstab"] = xt
    # 2. Rates under the independent construction checks' assessed labels.
    crows, _ = build_rows(run_dir, tasks_root, allow_proposed=True, policy="check")
    cprim = [r for r in crows if r.origin not in exclude_origins]
    out["sensitivity_check_labels"] = {}
    for c in conds:
        ss = summarize(cprim, condition=c, n_boot=n_boot)
        out["sensitivity_check_labels"][c] = {"fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den,
                                              "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den}
    # 3. Held-out candidates duplicating a development candidate or another held-out candidate.
    dup: dict = {}
    for t in sorted({r.task_id for r in rows}):
        m = load(tasks_root / t / "task.json", TaskManifest)
        cands = [load(tasks_root / t / p, Candidate) for p in m.candidates] + (stratum_cands or {}).get(t, [])
        dev = {_norm_patch(c.patch): c.candidate_id for c in cands if c.split.value == "dev" and c.patch}
        seen: dict[str, str] = {}
        for c in sorted(cands, key=lambda c: (c.origin != CandidateOrigin.observed_pre_correction, c.candidate_id)):
            if c.split.value != "eval" or c.origin in (CandidateOrigin.noop, CandidateOrigin.reference) or not c.patch:
                continue
            k = _norm_patch(c.patch)
            hits = {}
            if k in dev:
                hits["same_patch_as_dev"] = dev[k]
            if k in seen:
                hits["same_patch_as_heldout"] = seen[k]
            else:
                seen[k] = c.candidate_id
            if hits:
                dup[c.candidate_id] = {"task_id": t, **hits}
        # Same code apart from comments and docstrings (recorded by scripts/find_duplicates.py, D40).
        dp = tasks_root / t / "labels" / "duplicates.json"
        if dp.exists():
            for cid, hits in json.loads(dp.read_text()).get("duplicates", {}).items():
                dup.setdefault(cid, {"task_id": t}).update({k: ", ".join(v) for k, v in hits.items()})
    out["duplicates"] = dup
    if dup:
        drows = [r for r in primary if r.candidate_id not in dup]
        out["sensitivity_without_duplicates"] = {}
        for c in conds:
            ss = summarize(drows, condition=c, n_boot=n_boot)
            out["sensitivity_without_duplicates"][c] = {"fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den,
                                                        "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den}
    # 4. B1 restricted to checks that exist in the base commit's own tests (not added by the agent).
    up: dict[str, set] = {}
    for t in sorted({r.task_id for r in rows}):
        f = tasks_root / t / "verifiers" / "repo_tests" / "upstream_check_ids.json"
        if f.exists():
            up[t] = set(json.loads(f.read_text())["upstream_check_ids"])
    if up:
        label_of = {(r.task_id, r.candidate_id): r for r in primary if r.condition == "repo_tests"}
        b1 = []
        for res in read_jsonl(run_dir / "results.jsonl", VerificationResult):
            key = (res.task_id, res.candidate_id)
            if res.verifier_id != "repo_tests" or key not in label_of or res.task_id not in up:
                continue
            ok = all(ch.status == "passed" for ch in res.checks if ch.check_id in up[res.task_id])
            r0 = label_of[key]
            b1.append(Row(task_id=r0.task_id, family_id=r0.family_id, candidate_id=r0.candidate_id, condition="repo_tests_upstream",
                          outcome="pass" if ok else "task_failure", label=r0.label, origin=r0.origin,
                          population=r0.population, stratum=r0.stratum))
        ss = summarize(b1, condition="repo_tests_upstream", n_boot=n_boot)
        out["b1_upstream_only"] = {"fa": ss.fa.value, "fa_num": ss.fa.num, "fa_den": ss.fa.den,
                                   "fr": ss.fr.value, "fr_num": ss.fr.num, "fr_den": ss.fr.den,
                                   "n_checks": {t: len(v) for t, v in up.items()}}
    return out


def _fmt(rate, num, den, ci=None) -> str:
    if rate is None:
        return f"n/a (0/{den})"
    s = f"{rate:.2f} ({num}/{den})"
    if ci:
        s += f" [{ci[0]:.2f}, {ci[1]:.2f}]"
    return s


def _exact(x: dict) -> str:
    return "n/a" if not x.get("exact95") else f"[{x['exact95'][0]:.2f}, {x['exact95'][1]:.2f}]"


def _group_markdown(title: str, intro: str, groups: dict) -> list[str]:
    """One FA/FR table per group (a population or a candidate stratum), each on its own rows."""
    lines = ["", f"## {title}", "", intro]
    for g, d in groups.items():
        lines += ["", f"### {g} (tasks: {', '.join(d['tasks'])}; families: {d['n_families']})", "",
                  "| Condition | False acceptance | FA exact 95% | False rejection | FR exact 95% | Infra outcomes | Excluded (unlabeled/ambiguous) |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for c, x in d["conditions"].items():
            fa, fr = x["false_acceptance"], x["false_rejection"]
            star = lambda y: "*" if y.get("ci95_degenerate") else ""  # noqa: E731
            lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], fa['ci95'])}{star(fa)} | {_exact(fa)} | "
                         f"{_fmt(fr['rate'], fr['num'], fr['den'], fr['ci95'])}{star(fr)} | {_exact(fr)} | "
                         f"{x['infrastructure']['num']}/{x['infrastructure']['den']} | {x['excluded_unlabeled_or_ambiguous']} |")
    return lines


def _label_row(name: str, d: dict) -> str:
    q = ", ".join(x["candidate"] for x in d["review_queue"]) or "-"
    return (f"| {name} | {d['counts'].get('valid', 0)} | {d['counts'].get('invalid', 0)} | {d['counts'].get('ambiguous', 0)} | "
            f"{d['counts'].get('unlabeled', 0)} | {q} |")


def to_markdown(a: dict) -> str:
    lines = [f"# Analysis ({a['meta']['label_policy']})", "",
             f"Tasks: {a['n_tasks']} | independent task families: {a['n_families']} | results: {a['meta']['n_results']}", ""]
    if "automated pilot" in a["meta"]["label_policy"]:
        lines += ["> **Automated pilot.** Labels are model/construction proposals, not human-adjudicated ground truth. "
                  "With this few task families the intervals are not meaningful evidence of an effect.", ""]
    pops = a["meta"].get("populations")
    if pops and len(pops) > 1:
        lines += [f"> **Populations pooled** (`--pool-populations`). This run mixes {len(pops)} populations "
                  f"({_describe(pops)}). The tables below pool them; each population is reported separately "
                  "under \"By population\".", ""]
    elif pops:
        lines += [f"Population: {_describe(pops)}.", ""]
    lines += ["## False acceptance / false rejection by condition", "",
              "Rates with (numerator/denominator) and 95% cluster-bootstrap interval over task families where computable. "
              "Reference solution and no-op are excluded (see sanity table).", "",
              "Intervals marked * are degenerate (every family has the same rate, so resampling families cannot vary them); "
              "the exact (Clopper-Pearson) interval ignores clustering and is given only as a reference scale.", "",
              "| Condition | False acceptance | FA exact 95% | FA macro | False rejection | FR exact 95% | FR macro | Youden's J | Tasks with an accepted negative | Infra outcomes | Excluded (unlabeled/ambiguous) |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c, d in a["conditions"].items():
        fa, fr = d["false_acceptance"], d["false_rejection"]
        j = "n/a" if d.get("youden_j") is None else f"{d['youden_j']:+.2f}"
        tn = d.get("tasks_with_any_accepted_negative", {"num": 0, "den": 0})
        ex = lambda x: "n/a" if not x.get("exact95") else f"[{x['exact95'][0]:.2f}, {x['exact95'][1]:.2f}]"  # noqa: E731
        mac = lambda x: "n/a" if x.get("macro") is None else f"{x['macro']:.2f}"  # noqa: E731
        star = lambda x: "*" if x.get("ci95_degenerate") else ""  # noqa: E731
        lines.append(f"| {c} | {_fmt(fa['rate'], fa['num'], fa['den'], fa['ci95'])}{star(fa)} | {ex(fa)} | {mac(fa)} | "
                     f"{_fmt(fr['rate'], fr['num'], fr['den'], fr['ci95'])}{star(fr)} | {ex(fr)} | {mac(fr)} | {j} | "
                     f"{tn['num']}/{tn['den']} | {d['infrastructure']['num']}/{d['infrastructure']['den']} | {d['excluded_unlabeled_or_ambiguous']} |")
    if a.get("by_population"):
        lines += _group_markdown("By population", "Each population on its own rows, with its own task families "
                                 "(reference solution and no-op excluded). The tables above pool the populations. "
                                 "Intervals marked * are degenerate.", a["by_population"])
    if a.get("by_stratum"):
        lines += _group_markdown("By candidate stratum", f"`{TASK_STRATUM}` is the task's own candidates (task.json); every "
                                 "other stratum's candidates are listed in tasks/<id>/strata/<name>.json (reference solution "
                                 "and no-op excluded). The tables above pool the strata. Intervals marked * are degenerate.",
                                 a["by_stratum"])
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
    lines += ["", "## Per-family rates behind the macro rates", "",
              "| Condition | " + " | ".join(f"{t} FA | {t} FR" for t in sorted(a["per_task"])) + " |",
              "| --- | " + " | ".join("--- | ---" for _ in a["per_task"]) + " |"]
    for c, d in a["conditions"].items():
        pt = d.get("per_task_rates", {})
        cells = []
        for t in sorted(a["per_task"]):
            x = pt.get(t)
            cells += ["-", "-"] if x is None else [f"{x['fa_num']}/{x['fa_den']}", f"{x['fr_num']}/{x['fr_den']}"]
        lines.append(f"| {c} | " + " | ".join(cells) + " |")
    lines += ["", "## Paired comparisons (same candidates)", "",
              "Intervals marked * are degenerate (every family has the same difference).", "",
              "| A | B | Metric | A - B | 95% CI | n labeled for metric | families | A acc & B rej | A rej & B acc |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for d in a["comparisons"]:
        diff = "n/a" if d["difference"] is None else f"{d['difference']:+.2f}"
        ci = "n/a" if not d["ci95"] else f"[{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}]" + ("*" if d.get("ci95_degenerate") else "")
        lines.append(f"| {d['a']} | {d['b']} | {d['metric'].upper()} | {diff} | {ci} | {d.get('n_metric', d['n_common'])} | {d['n_families']} | "
                     f"{d['discordant']['a_accepts_b_rejects']} | {d['discordant']['a_rejects_b_accepts']} |")
    if a.get("sensitivity_construction_labels"):
        lines += ["", "## Exploratory sensitivity: construction-intent labels (protocol v0.3; not pre-specified)", "",
                  "Constructed candidates labeled by how they were built (near miss = invalid, alternative = valid), "
                  "including those the D19 rule marked ambiguous; the observed pre-correction state keeps its D19 label. "
                  "Intervals marked * are degenerate.", "",
                  "| Condition | False acceptance | FA exact 95% | False rejection | FR exact 95% |", "| --- | --- | --- | --- | --- |"]
        for c, d in a["sensitivity_construction_labels"].items():
            st = lambda k: "*" if d.get(f"{k}_ci95_degenerate") else ""  # noqa: E731
            exs = lambda k: "n/a" if not d.get(f"{k}_exact95") else f"[{d[k + '_exact95'][0]:.2f}, {d[k + '_exact95'][1]:.2f}]"  # noqa: E731
            lines.append(f"| {c} | {_fmt(d['fa'], d['fa_num'], d['fa_den'], d['fa_ci95'])}{st('fa')} | {exs('fa')} | "
                         f"{_fmt(d['fr'], d['fr_num'], d['fr_den'], d['fr_ci95'])}{st('fr')} | {exs('fr')} |")
    if a.get("near_miss_crosstab"):
        lines += ["", "## Post-hoc analyses after the internal review (exploratory, not pre-specified)", "",
                  "### Near misses accepted, by label status", "", "| Condition | D19-confirmed invalid | D19 ambiguous |", "| --- | --- | --- |"]
        for c, d in a["near_miss_crosstab"].items():
            lines.append(f"| {c} | {d['confirmed_invalid']['accepted']}/{d['confirmed_invalid']['n']} | {d['ambiguous']['accepted']}/{d['ambiguous']['n']} |")
    if a.get("sensitivity_check_labels"):
        lines += ["", "### Rates under the independent construction checks' labels", "",
                  "| Condition | False acceptance | False rejection |", "| --- | --- | --- |"]
        for c, d in a["sensitivity_check_labels"].items():
            lines.append(f"| {c} | {_fmt(d['fa'], d['fa_num'], d['fa_den'])} | {_fmt(d['fr'], d['fr_num'], d['fr_den'])} |")
    if a.get("duplicates"):
        lines += ["", "### Held-out candidates that duplicate another candidate (same graded patch, or same code apart from comments and docstrings)", ""]
        for cid, d in a["duplicates"].items():
            lines.append(f"* {cid}: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in d.items() if k != "task_id"))
        lines += ["", "| Condition | FA without duplicates | FR without duplicates |", "| --- | --- | --- |"]
        for c, d in a.get("sensitivity_without_duplicates", {}).items():
            lines.append(f"| {c} | {_fmt(d['fa'], d['fa_num'], d['fa_den'])} | {_fmt(d['fr'], d['fr_num'], d['fr_den'])} |")
    if a.get("b1_upstream_only"):
        d = a["b1_upstream_only"]
        lines += ["", "### B1 restricted to the base commit's own tests (checks added by the session agent removed)", "",
                  f"False acceptance {_fmt(d['fa'], d['fa_num'], d['fa_den'])}; false rejection {_fmt(d['fr'], d['fr_num'], d['fr_den'])}."]
    if a.get("labels"):
        lines += ["", "## Labels and human-review queue", "", "| Task | valid | invalid | ambiguous | unlabeled | queued for review |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for t, d in a["labels"].items():
            lines.append(_label_row(t, d))
            lines += [_label_row(f"{t} (stratum {s})", sd) for s, sd in d.get("strata", {}).items()]
    if a.get("coverage"):
        lines += ["", "## Contract recovery (model mappings, proposals)", "",
                  "| Task | Variant | Coverage of active reference requirements (mapper 1) | Covered but contradicted | Unsupported | Contradicting | Coverage (mapper 2) | Mapping agreement (kappa) |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for t, cov in a["coverage"].items():
            ag = a.get("mapping_agreement", {}).get(t, {})
            for v, d in cov.get("variants", {}).items():
                d2 = cov.get("variants_mapper2", {}).get(v)
                k = ag.get(v, {}).get("kappa")
                lines.append(f"| {t} | {v} | {_fmt(d['coverage'], len(d['covered']), len(cov['reference_scored']))} | "
                             f"{', '.join(d.get('covered_but_contradicted', [])) or '-'} | "
                             f"{len(d['unsupported'])}/{d['n_recovered_scored']} | {len(d['contradicting'])} | "
                             f"{_fmt(d2['coverage'], len(d2['covered']), len(cov['reference_scored'])) if d2 else '-'} | "
                             f"{'n/a' if k is None else f'{k:.2f}'} |")
    lines += ["", "## Per-task outcomes", ""]
    strat = bool(a.get("by_stratum"))  # a Stratum column only for a run with candidate strata
    for t, conds in a["per_task"].items():
        lines += [f"### {t}", "", f"| Candidate | {'Stratum | ' if strat else ''}Origin | Label | Negative type | " + " | ".join(conds) + " |",
                  f"| --- | {'--- | ' if strat else ''}--- | --- | --- | " + " | ".join("---" for _ in conds) + " |"]
        cands = {}
        for c, rs in conds.items():
            for r in rs:
                cands.setdefault(r["candidate"], {"origin": r["origin"], "label": r["label"], "nt": r["negative_type"],
                                                  "stratum": r.get("stratum", "")})[c] = r["outcome"]
        for cid, d in sorted(cands.items()):
            lines.append(f"| {cid} | {d['stratum'] + ' | ' if strat else ''}{d['origin']} | {d['label']} | {d['nt'] or '-'} | "
                         + " | ".join(d.get(c, "-") for c in conds) + " |")
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
    # Covered by one recovered requirement but contradicted by another one (reported, not subtracted).
    contradicted_anywhere = {x for rid in rec for x in contra[rid]}
    covered_but_contradicted = sorted(covered & contradicted_anywhere)
    return {"mapper_kind": mapping.get("mapper_kind"), "mapper": mapping.get("mapper"),
            "coverage": len(covered) / len(ref_scored) if ref_scored else None,
            "covered": sorted(covered), "missing": sorted(ref_scored - covered),
            "n_recovered_scored": len(rec), "unsupported": unsupported,
            "unsupported_rate": (len(unsupported) / len(rec)) if rec else None,
            "contradicting": contradicting, "covered_but_contradicted": covered_but_contradicted,
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


def label_summary(task_dirs: list[Path], strata: dict[str, dict[str, list[Candidate]]] | None = None) -> dict:
    """Proposed-label counts per task and the queue of candidates needing human review.

    Queued: candidates the D19 rule marked ambiguous, candidates without a proposal,
    and candidates whose independent construction check disagrees with the proposal
    (``labels/construction_checks.json``, advisory evidence only).

    ``strata`` (``{task_id: {stratum: candidates}}``) adds, under the task's ``strata`` key,
    the same summary for each stratum's candidates.
    """
    out: dict = {}
    for tdir in task_dirs:
        m = load(tdir / "task.json", TaskManifest)
        checks_p = tdir / "labels" / "construction_checks.json"
        checks = json.loads(checks_p.read_text()).get("checks", {}) if checks_p.exists() else {}
        out[m.task_id] = _label_pool([load(tdir / p, Candidate) for p in m.candidates], checks)
        if (strata or {}).get(m.task_id):
            out[m.task_id]["strata"] = {name: _label_pool(cs, checks) for name, cs in strata[m.task_id].items()}
    return out


def _label_pool(cands: list[Candidate], checks: dict) -> dict:
    """Label counts, label rows and review queue of one pool of candidates (held-out ones; no reference, no no-op)."""
    counts: Counter = Counter()
    queue, rows = [], []
    for c in cands:
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
        if c.human_disagreement():
            queue.append({**row, "reason": "human reviewers disagree; adjudication needed"})
        elif value in ("ambiguous", "unlabeled") or disagree:
            queue.append({**row, "reason": "ambiguous under D19" if value == "ambiguous" else
                          ("no proposal" if value == "unlabeled" else "construction check disagrees with proposal")})
    return {"counts": dict(counts), "candidates": rows, "review_queue": queue}
