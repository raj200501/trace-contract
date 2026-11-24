"""Training-data selection on a recorded run: the fresh attempts that each verifier condition would admit, gated and not.

This is the data step of the downstream experiment that ``experiments/downstream_plan_v0.1-draft.md`` plans, which has
not run. Nothing here trains, samples or downloads a model, and nothing here measures training value. The output says
which recorded attempts each condition's verifier would let into a training set, with the cell gate (the data filter)
and without it (a description of the verifier), and how many of those the label rule marks invalid, by kind. It never
replaces the run's own analysis. Its files state the configuration's standing (``standing``): ``post hoc`` when the
configuration was written after the run was graded and analysed, as for ``fresh-v1``, which makes the selection an
exploratory analysis of that run; ``pre-specified`` when it was fixed before the run was graded, which this script
cannot check (the decision log must record the configuration's sha256 before the grading).

Usage::

    python scripts/build_training_selection.py [--config configs/downstream/rft_selection_v0.1.json]
        [--run DIR] [--tasks-root DIR] [--out DIR] [--check]

``--run``, ``--tasks-root`` and ``--out`` default to the config's ``run.dir``, ``tasks_root`` and ``out``, which are
relative to the repository. ``--check`` writes nothing: it rebuilds the output and compares it byte for byte with the
files in the output directory (exit status 0 when they are identical, 1 when not).

Inputs, read and never written: the config; the run's ``manifest.json``, ``results.jsonl`` and, when it exists,
``analysis.json``; and the task directories that the run's manifest names, read with the analysis' own code
(:func:`tracecontract.analysis.build_rows`): ``task.json``, its candidate files, the reference contract, the stratum
candidates that the run graded and, for a natural PR-review task, its ``session.json`` (whose first user prompt the
negative types are compared with). The stratum manifests that the run's manifest names are hashed, not read. Outputs:
``<out>/selection_manifest.json`` and ``<out>/selection.md``, written only after every check has passed. No candidate
code is executed.

Every rule but one part of the cell gate is the run's or its analysis' own:

* **Attempts.** The run's fresh attempts (origin ``fresh_attempt``) that the analysis keeps.
  :func:`tracecontract.analysis.attempt_exclusion` excludes from every analysis an attempt without an attempt record
  or an audit verdict, or whose audit found a read of forbidden material; the manifest lists each with its reason.
  Other graded candidates (the reference solutions, for example) are not attempts and are counted, not selected.
* **Acceptance.** A condition admits an attempt when the run recorded the outcome ``pass`` for the pair: protocol §6
  (only ``pass`` yields reward) and ``tracecontract.metrics`` (accept(V, c) := outcome(V, c) == "pass"). For a pair
  graded with repeats, the grader records ``pass`` only when every repeat passed, since repeats that disagree make the
  pair ``unresolved`` (``tracecontract.sandbox.docker_runner.verify_candidate``; protocol §15.3). Every other outcome
  is a rejection.
* **Cell gate.** A condition contributes data from a task (a cell) only when the run recorded ``pass`` for the task's
  reference solution under that condition, which with repeats means on every repeat: the analysis' oracle-gated view
  (protocol §15.7; ``tracecontract.analysis._oracle_gated``). Where the run graded the task's no-op under the condition,
  the cell also needs the outcome ``task_failure`` for it. That second part is the plan's, not the analysis': the
  environment-synthesis pipelines that the study cites validate a verifier on the gold patch and on the pre-fix state.
  A cell that fails the gate is dropped, and the attempts that its condition admits there are the gate's lost yield.
  With ``cell_gate.noop_required``, a cell without a graded no-op refuses the run. The gated admitted sets are the data
  filters; the ungated ones are reported beside them, as a description of each verifier.
* **Labels.** The analysis' label rule (:func:`tracecontract.analysis.candidate_label`): policy ``pilot``, a human
  label where one exists, else the latest proposal of rule D19 (labeler ``analysis.PILOT_LABELER``); policy ``human``,
  human labels only.
* **Kinds of invalid attempt,** from the analysis' negative type of the row and the label's violated requirements: a
  *correction violator* violates a reference requirement introduced after the first user request (negative type
  ``correction_violating``); a *regression-only* attempt violates the regression norm and nothing else (violated
  requirements exactly ``REGRESSION``, which the analysis types ``unspecified``); every other invalid attempt
  (``initial_violating``, any other ``unspecified``) is ``other_invalid``, with its negative type recorded.

Counts are given per family and in total, with each family's count beside the total: for the attempts counted, by
instruction variant, and by variant and agent configuration. No rate is computed, and no total is presented as an
estimate of anything beyond the attempts counted.

Refusals. The script refuses, writes nothing and exits with status 2, printing every reason found at the step that
refuses. The steps run in this order, and a later one runs only when the earlier ones found nothing: the config; the
output directory; the run's manifest; the run's attempts, pairs, labels and cells; its ``analysis.json``; the rows of
each attempt. It refuses when:

* the config cannot be read, lacks a key or has one this script does not read, or states another standing, acceptance
  rule, refused outcomes, cell gate or label source, or a condition that is not an evaluated condition;
* the run's manifest cannot be read, names no task, another run or another number of repeats, or lacks a configured
  condition for a task; or the analysis cannot read the run's records (``analysis.ConditionConflict``, a stratum error);
* the run mixes populations (never pooled silently, as ``analysis.MixedPopulations``), holds no fresh attempt that the
  analysis keeps, or lacks the reference contract of a task with attempts;
* an attempt has no label under the label source: a run without labels;
* a pair that the selection reads (a kept attempt under a configured condition) is ``unresolved`` (its repeats
  disagree), ended in an infrastructure outcome, is missing, or is recorded more than once. The analysis counts such
  outcomes as rejections; a training set is not chosen by them. The outcomes of the reference and the no-op never
  refuse the run: they decide the cell gate. A cell without a graded no-op refuses it when ``cell_gate.noop_required``;
* the run's ``analysis.json``, when it exists, cannot be read or disagrees with the rows read here: an attempt's
  outcome or origin (and, under the same label rule, its label or negative type), the excluded attempts, or the cells
  that its oracle-gated view drops;
* an attempt's rows disagree with the label rule on its label or negative type;
* the output directory lies in ``results/runs/``, the run directory or the tasks root.

Determinism. The output is a function of the inputs' bytes: no clock, no git, no network; keys and lists are sorted;
paths are recorded relative to the repository (or by name), never as local absolute paths. The selection's code is
recorded by the sha256 of each file that ran, not by a git revision, which would change with every commit: this script,
and the package files that importing the analysis loads, together with, for a run with a natural PR-review task, those
that importing the modules which read its session loads (:data:`NATURAL_ENTRY`). Which package files those are is
found in a fresh interpreter (:func:`_package_files`), so that nothing this process imported before counts. The run's
own code revision is recorded as the run's manifest gives it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from tracecontract import analysis as tc_analysis
from tracecontract.analysis import (
    CONDITION_ORDER,
    LABEL_SUPPORT_CONDITION,
    PILOT_LABELER,
    ConditionConflict,
    _patch_key,
    attempt_exclusion,
    build_rows,
    candidate_label,
)
from tracecontract.metrics import INFRA
from tracecontract.schemas import CandidateOrigin, Population, TaskManifest
from tracecontract.store import load
from tracecontract.strata import StratumError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "downstream" / "rft_selection_v0.1.json"
CONFIG_SCHEMA = "tracecontract/downstream-selection-config/0.1"
SCHEMA = "tracecontract/training-selection/0.1"
MANIFEST = "selection_manifest.json"
TABLE = "selection.md"
# The standings a config may state: how the output names each, and when the configuration was written.
STANDINGS = {
    "post hoc": ("post hoc, exploratory (not pre-specified)", "after the run was graded and analysed"),
    "pre-specified": ("pre-specified, as its configuration states",
                      ("under a configuration fixed before the run was graded, which the decision log must show by its "
                       "sha256 and this file cannot")),
}
SHORT = {"initial_plain": "C1", "initial_audited": "C2", "full_plain": "C3", "full_audited": "C4", "llm_freeform": "B2",
         "repo_tests": "B1", "diff_derived": "B3"}
ATTEMPT = CandidateOrigin.fresh_attempt.value
REFERENCE = CandidateOrigin.reference.value
NOOP = CandidateOrigin.noop.value
REGRESSION = "REGRESSION"  # the regression norm's pseudo-requirement in a D19 label (scripts/propose_labels.py)
KINDS = ("correction_violator", "regression_only", "other_invalid")
LABEL_POLICIES = ("pilot", "human")  # the analysis' primary label rules (analysis.candidate_label)
# The run's acceptance rule, which the config must state as it is (protocol §6, §15.3; metrics.py; docker_runner.py).
ACCEPTANCE_RULE = {"admit_on": "pass", "repeats": "every", "other_outcomes": "rejected"}
# No verdict to select on: repeats that disagree (unresolved) and the infrastructure outcomes (metrics.INFRA).
REFUSED_OUTCOMES = sorted(INFRA)
# The cell gate's rule, which the config must state as it is; the config adds noop_required (true or false).
CELL_GATE = {"reference": "pass", "noop": "task_failure"}
EVALUATED = tuple(c for c in CONDITION_ORDER if c != LABEL_SUPPORT_CONDITION)
CONFIG_KEYS = frozenset({"schema", "experiment", "standing", "status", "run", "tasks_root", "out", "candidates",
                         "acceptance_rule", "refused_outcomes", "cell_gate", "label_source", "conditions",
                         "data_filters"})
# The modules that the analysis imports, inside analysis.natural_first_prompt, to read a natural PR-review task's session
# (tests check that they are these); the package files they load are hashed for a run with such a task.
NATURAL_ENTRY = ("tracecontract.tasks", "tracecontract.contract")
_PROBE = ("import json, sys\n"
          "sys.path.insert(0, sys.argv[1])\n"
          "def files():\n"
          "    return {getattr(m, '__file__', None) for k, m in list(sys.modules.items()) if k.split('.')[0] == 'tracecontract'}\n"
          "import tracecontract.analysis\n"
          "for name in sys.argv[2:]:\n"
          "    __import__(name)\n"
          "print(json.dumps(sorted(f for f in files() if f)))\n")
SESSION_FILE = "session.json"  # a natural PR-review task's session (tasks.PR_SESSION_FILE; tests check that they agree)

RULES = {
    "attempts": ("the run's fresh attempts (origin fresh_attempt) that the run's analysis keeps; "
                 "tracecontract.analysis.attempt_exclusion excludes from every analysis an attempt without an attempt record "
                 "or an audit verdict, or whose audit found a read of forbidden material (listed under excluded); other "
                 "graded candidates are not attempts and are counted under not_selected"),
    "acceptance": ("a condition admits an attempt when the run recorded the outcome pass for the pair (protocol §6: only "
                   "pass yields reward; tracecontract.metrics: accept(V, c) := outcome(V, c) == pass); for a pair graded with "
                   "repeats the grader records pass only when every repeat passed, since repeats that disagree make the pair "
                   "unresolved (tracecontract.sandbox.docker_runner.verify_candidate; protocol §15.3); every other outcome is "
                   "a rejection"),
    "cell_gate": ("a condition contributes data from a task (a cell) only when the run recorded pass for the task's reference "
                  "under that condition (on every repeat): the analysis' oracle-gated view (protocol §15.7); where the run "
                  "graded the task's no-op under the condition, the cell also needs task_failure for it (the plan's addition, "
                  "not the analysis'); the attempts that a condition admits in a dropped cell are its lost yield; the data "
                  "filters are the gated sets, and the ungated sets describe each verifier"),
    "refusals": ("a pair that the selection reads and that is unresolved, ended in an infrastructure outcome, is missing or "
                 "is recorded twice refuses the run, and so does an attempt without a label: the analysis counts such "
                 "outcomes as rejections, but a training set is not chosen by them; the outcomes of the reference and the "
                 "no-op decide the cell gate and never refuse the run, but with cell_gate.noop_required a cell without a "
                 "graded no-op does"),
    "labels": ("the analysis' label rule (tracecontract.analysis.candidate_label): policy pilot, a human label where one "
               "exists, else the latest proposal of rule D19; policy human, human labels only"),
    "kinds": {"correction_violator": ("invalid, with a violated requirement of the reference contract introduced after the "
                                      "first user request (the analysis' negative type correction_violating)"),
              "regression_only": ("invalid through the regression norm alone: the violated requirements are exactly "
                                  "REGRESSION (the analysis' negative type unspecified)"),
              "other_invalid": "any other invalid attempt (negative type initial_violating, or any other unspecified)"},
    "counts": ("per family and in total, with each family's count beside the total: for the attempts counted, by "
               "instruction variant, and by variant and agent configuration; no rate is computed, and no total is an "
               "estimate of anything beyond the attempts counted"),
    "distinct_graded_patches": ("attempts of a task whose patches are the same as graded (tracecontract.analysis._patch_key) "
                                "are one distinct graded patch; the counts above count attempts"),
}


class Refused(Exception):
    """The selection cannot be made as configured; nothing is written. ``reasons`` lists every reason found."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _shown(path: Path) -> str:
    """A path as recorded: relative to the repository when it lies inside it, else its name (never a local absolute path)."""
    p = path.resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.name


def _inside(path: Path, parent: Path) -> bool:
    p, q = path.resolve(), parent.resolve()
    return p == q or q in p.parents


def _positive_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def read_config(path: Path) -> tuple[dict, dict]:
    """The config and ``{file, sha256}``; :class:`Refused` lists every way in which it differs from what this script does."""
    try:
        raw = path.read_bytes()
        cfg = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise Refused([f"the config {_shown(path)} cannot be read as JSON ({type(exc).__name__}: {exc})"]) from None
    if not isinstance(cfg, dict):
        raise Refused([f"the config {_shown(path)} is not a JSON object"])
    why: list[str] = []
    if missing := sorted(CONFIG_KEYS - set(cfg)):
        why.append(f"the config lacks {', '.join(missing)}")
    if extra := sorted(set(cfg) - CONFIG_KEYS):
        why.append(f"the config has keys this script does not read: {', '.join(extra)}")
    if why:
        raise Refused(why)
    if cfg["schema"] != CONFIG_SCHEMA:
        why.append(f"the config's schema is {cfg['schema']!r}, not {CONFIG_SCHEMA!r}")
    if not isinstance(cfg["standing"], str) or cfg["standing"] not in STANDINGS:
        why.append(f"the config's standing {cfg['standing']!r} is not one of {', '.join(map(repr, STANDINGS))}")
    run = cfg["run"]
    if not (isinstance(run, dict) and set(run) == {"run_id", "dir", "repeats"} and isinstance(run["run_id"], str)
            and run["run_id"] and isinstance(run["dir"], str) and run["dir"] and _positive_int(run["repeats"])):
        why.append("the config's run must be {run_id, dir, repeats}: two non-empty strings and a positive number of repeats")
    for key in ("experiment", "status", "tasks_root", "out"):
        if not isinstance(cfg[key], str) or not cfg[key].strip():
            why.append(f"the config's {key} must be a non-empty string")
    if cfg["candidates"] != ATTEMPT:
        why.append(f"the config selects candidates {cfg['candidates']!r}; this script selects fresh attempts ({ATTEMPT!r}) only")
    if cfg["acceptance_rule"] != ACCEPTANCE_RULE:
        why.append(f"the config states the acceptance rule {json.dumps(cfg['acceptance_rule'], sort_keys=True)}, which is not "
                   f"the run's own rule {json.dumps(ACCEPTANCE_RULE, sort_keys=True)} (protocol §6, §15.3; "
                   "tracecontract.metrics; tracecontract.sandbox.docker_runner): a pass on every repeat admits, and every "
                   "other outcome rejects")
    if cfg["refused_outcomes"] != REFUSED_OUTCOMES:
        why.append(f"the config's refused outcomes {cfg['refused_outcomes']!r} are not the outcomes without a verdict that "
                   f"this script refuses ({REFUSED_OUTCOMES!r}: unresolved and the infrastructure outcomes, metrics.INFRA)")
    gate = cfg["cell_gate"]
    if not (isinstance(gate, dict) and set(gate) == {*CELL_GATE, "noop_required"}
            and {k: gate[k] for k in CELL_GATE} == CELL_GATE and isinstance(gate["noop_required"], bool)):
        why.append(f"the config's cell_gate must be {json.dumps(CELL_GATE, sort_keys=True)[:-1]}, \"noop_required\": true "
                   "or false}: a cell is kept when its verifier passes the task's reference and, where the no-op was graded, "
                   "fails on it")
    ls = cfg["label_source"]
    if not (isinstance(ls, dict) and set(ls) == {"policy", "labeler"}):
        why.append("the config's label_source must be {policy, labeler}")
    elif ls["policy"] not in LABEL_POLICIES:
        why.append(f"the label source's policy {ls['policy']!r} is not one of the analysis' primary label rules "
                   f"({', '.join(LABEL_POLICIES)})")
    elif ls["policy"] == "pilot" and ls["labeler"] != PILOT_LABELER:
        why.append(f"policy pilot reads rule D19's proposals, whose labeler is {PILOT_LABELER!r}, not {ls['labeler']!r}")
    elif ls["policy"] == "human" and ls["labeler"] is not None:
        why.append("policy human reads human labels only, so its labeler must be null")
    conds = cfg["conditions"]
    if not (isinstance(conds, list) and conds and all(isinstance(c, str) for c in conds)):
        why.append("the config's conditions must be a non-empty list of condition names")
        conds = []
    if len(set(conds)) != len(conds):
        why.append("the config names a condition more than once")
    for c in conds:
        if c not in EVALUATED:
            why.append(f"{c!r} is not an evaluated condition ({', '.join(EVALUATED)}); the label-support verifiers "
                       f"({LABEL_SUPPORT_CONDITION}) never are")
    filters = cfg["data_filters"]
    if not (isinstance(filters, dict) and filters and all(isinstance(k, str) and isinstance(v, str) for k, v in filters.items())):
        why.append("the config's data_filters must map each role to a condition")
    else:
        for role, c in sorted(filters.items()):
            if c not in conds:
                why.append(f"the data filter {role} ({c!r}) is not one of the config's conditions")
    if why:
        raise Refused(why)
    return cfg, {"file": _shown(path), "sha256": hashlib.sha256(raw).hexdigest()}


def _kind(value: str | None, violated: list[str], negative_type: str) -> str | None:
    """The kind of an invalid attempt (module docstring); None for any other label."""
    if value != "invalid":
        return None
    if negative_type == "correction_violating":
        return "correction_violator"
    if negative_type == "unspecified" and set(violated) == {REGRESSION}:
        return "regression_only"
    return "other_invalid"


def _gate(rows: list, tasks: list[str], conds: list[str], noop_required: bool) -> tuple[dict, list[str]]:
    """The cell gate (module docstring): per configured condition and task, the outcomes recorded for the task's reference
    and no-op, whether the cell is kept and, if not, why; and the cells without a graded no-op when one is required."""
    graded: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for r in rows:
        if r.origin in (REFERENCE, NOOP):
            graded[(r.origin, r.task_id, r.condition)].append(r.outcome)
    cells: dict[str, dict[str, dict]] = {}
    lacking: list[str] = []
    for c in conds:
        cells[c] = {}
        for t in tasks:
            ref, noop = sorted(graded.get((REFERENCE, t, c), [])), sorted(graded.get((NOOP, t, c), []))
            passes = bool(ref) and all(o == CELL_GATE["reference"] for o in ref)
            fails = all(o == CELL_GATE["noop"] for o in noop) if noop else None
            drop = ("the reference was not graded" if not ref else None if passes else
                    f"does not pass its reference ({', '.join(ref)})")
            if drop is None and fails is False:
                drop = f"does not fail on its no-op ({', '.join(noop)})"
            if not noop and noop_required:
                lacking.append(f"{t} under {c}")
            cells[c][t] = {"reference": ref, "noop": noop, "passes_reference": passes, "fails_on_noop": fails,
                           "kept": drop is None, **({"dropped": drop} if drop else {})}
    why = ([(f"the config requires a graded no-op in every cell (cell_gate.noop_required), and {len(lacking)} cell(s) "
             f"have none: {', '.join(lacking)}")] if lacking else [])
    return cells, why


def _tally(keys: list[tuple[str, str]], info: dict[tuple[str, str], dict], families: list[str], first: str) -> dict:
    """Counts of the attempts ``keys``, per family and in total: ``first`` (every one of them), valid, ambiguous, invalid
    and each kind of invalid attempt."""
    out = {name: {"total": 0, "per_family": {f: 0 for f in families}}
           for name in (first, "valid", "ambiguous", "invalid", *KINDS)}
    for k in keys:
        e = info[k]
        names = [first] + (["valid"] if e["label"] == "valid" else ["invalid", e["kind"]] if e["label"] == "invalid"
                           else ["ambiguous"])
        for n in names:
            out[n]["total"] += 1
            out[n]["per_family"][e["family_id"]] += 1
    return out


def _distinct(keys: list[tuple[str, str]], info: dict[tuple[str, str], dict]) -> int:
    """Distinct graded patches among ``keys``, counted within each task as the analysis counts them."""
    return len({(k[0], info[k]["graded_patch_sha256"]) for k in keys})


def _block(keys: list[tuple[str, str]], info: dict[tuple[str, str], dict], families: list[str], first: str) -> dict:
    """The tallies of ``keys``: all of them, by instruction variant, and by variant and agent configuration."""
    variants = sorted({e["variant"] for e in info.values()})
    configurations = sorted({e["configuration"] for e in info.values()})

    def tally(**match: str) -> dict:
        return _tally([k for k in keys if all(info[k][f] == v for f, v in match.items())], info, families, first)

    return {"counts": tally(),
            "by_variant": {v: tally(variant=v) for v in variants},
            "by_variant_and_configuration": {v: {g: tally(variant=v, configuration=g) for g in configurations}
                                             for v in variants},
            "distinct_graded_patches": _distinct(keys, info)}


def _against_analysis(run_dir: Path, pairs: dict[tuple[str, str, str], object], policy: str,
                      excluded: list[tuple[str, str]], gate: dict[str, dict[str, dict]]) -> dict:
    """Compare the rows read here with the run's ``analysis.json``, when it exists, and say what was compared.

    :class:`Refused` on any difference: an attempt's outcome or origin under a configured condition, its label and
    negative type when the analysis used the same label rule, the excluded attempts, and the cells that the analysis'
    oracle-gated view drops (the reference part of the cell gate), where the analysis has that view."""
    p = run_dir / "analysis.json"
    if not p.is_file():
        return {"analysis_json": "absent"}
    try:
        a = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise Refused([f"the run's analysis.json cannot be read ({type(exc).__name__}: {exc})"]) from None
    try:
        rule = (a.get("meta") or {}).get("label_rule")
        listed = {(t, e.get("candidate"), c): e for t, conds in (a.get("per_task") or {}).items()
                  for c, entries in conds.items() for e in entries}
    except (AttributeError, TypeError):
        raise Refused(["the run's analysis.json holds no per-task listing in the form the analysis writes"]) from None
    fields = ["origin", "outcome"] + (["label", "negative_type"] if rule == policy else [])
    diffs = []
    for (t, cid, c), r in sorted(pairs.items()):
        e = listed.get((t, cid, c))
        if e is None:
            diffs.append(f"{cid} under {c} is not in analysis.json's per-task listing")
            continue
        diffs += [f"{cid} under {c}: {f} {e.get(f)!r} in analysis.json, {getattr(r, f)!r} in the records"
                  for f in fields if e.get(f) != getattr(r, f)]
    fresh = a.get("fresh_attempts")
    with_excluded = isinstance(fresh, dict) and isinstance(fresh.get("excluded"), list)
    if with_excluded:
        theirs = sorted((x.get("task_id"), x.get("candidate_id")) for x in fresh["excluded"])
        if theirs != sorted(excluded):
            diffs.append(f"analysis.json excludes the attempts {theirs}, and the analysis' rule excludes {sorted(excluded)} now")
    og = a.get("oracle_gated")
    with_gate = isinstance(og, dict) and isinstance(og.get("conditions"), dict)
    if with_gate:
        for c, cells in sorted(gate.items()):
            entry = og["conditions"].get(c)
            if not (isinstance(entry, dict) and isinstance(entry.get("dropped"), dict)):
                diffs.append(f"analysis.json's oracle-gated view has no {c}")
                continue
            theirs = sorted(t for t in entry["dropped"] if t in cells)
            mine = sorted(t for t, cell in cells.items() if not cell["passes_reference"])
            if theirs != mine:
                diffs.append(f"under {c}, analysis.json's oracle-gated view drops {theirs}, and the reference gate drops {mine}")
    if diffs:
        raise Refused([f"the run's analysis.json disagrees with the records read here ({len(diffs)}): "
                       + "; ".join(diffs[:20]) + ("; ..." if len(diffs) > 20 else "")])
    return {"analysis_json": "matches", "analysis_label_rule": rule, "compared_fields": fields,
            "compared_pairs": len(pairs), "excluded_attempts_compared": with_excluded, "oracle_gated_compared": with_gate}


def _inputs(run_dir: Path, tasks_root: Path, run_manifest: dict, with_analysis: bool) -> dict[str, str]:
    """sha256 of every file the selection read (and of the stratum manifests), by a key that does not depend on where the
    files lie."""
    files = {"run/manifest.json": _sha(run_dir / "manifest.json"), "run/results.jsonl": _sha(run_dir / "results.jsonl")}
    if with_analysis:
        files["run/analysis.json"] = _sha(run_dir / "analysis.json")
    for t in run_manifest["tasks"]:
        tid = t["task_id"]
        td = tasks_root / tid
        m = load(td / "task.json", TaskManifest)
        rels = {"task.json", m.contracts.get("reference", "contracts/reference.json"), *m.candidates}
        rels |= {s["manifest"] for s in (t.get("strata") or {}).values() if isinstance(s, dict) and s.get("manifest")}
        rels |= {rec["path"] for rec in (t.get("candidates") or {}).values() if rec.get("stratum") and rec.get("path")}
        if m.population == Population.natural_pr_review:
            rels.add(SESSION_FILE)
        for rel in sorted(rels):
            if (td / rel).is_file():
                files[f"tasks/{tid}/{rel}"] = _sha(td / rel)
    return dict(sorted(files.items()))


@lru_cache(maxsize=2)
def _package_files(natural: bool) -> tuple[str, ...]:
    """The package files, relative to the package, that importing the analysis loads (and, with ``natural``, importing
    :data:`NATURAL_ENTRY` as well), found in a fresh interpreter with this one's executable and this package."""
    pkg = Path(tc_analysis.__file__).resolve().parent
    out = subprocess.run([sys.executable, "-I", "-B", "-c", _PROBE, str(pkg.parent), *(NATURAL_ENTRY if natural else ())],
                         capture_output=True, text=True, check=True).stdout
    return tuple(sorted(Path(f).resolve().relative_to(pkg).as_posix() for f in json.loads(out)))


def _code(natural: bool) -> dict[str, str]:
    pkg = Path(tc_analysis.__file__).resolve().parent
    files = {"scripts/build_training_selection.py": _sha(Path(__file__).resolve())}
    files.update({f"src/tracecontract/{name}": _sha(pkg / name) for name in _package_files(natural)})
    return dict(sorted(files.items()))


def build_selection(cfg: dict, cfg_meta: dict, run_dir: Path, tasks_root: Path) -> dict:
    """The selection manifest (a dict) of ``run_dir`` under ``cfg``; :class:`Refused` lists every reason it cannot be made."""
    try:
        run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise Refused([f"the run's manifest.json cannot be read ({type(exc).__name__}: {exc})"]) from None
    want = cfg["run"]
    conds = list(cfg["conditions"])
    why: list[str] = []
    if run_manifest.get("run_id") != want["run_id"]:
        why.append(f"the run directory holds the run {run_manifest.get('run_id')!r}, and the config is for {want['run_id']!r}")
    if run_manifest.get("repeats") != want["repeats"]:
        why.append(f"the run graded each pair {run_manifest.get('repeats')!r} time(s), and the config states {want['repeats']}")
    if not run_manifest.get("tasks"):
        why.append("the run's manifest names no task")
    for t in run_manifest.get("tasks") or []:
        recorded = {v.get("condition") for v in (t.get("verifiers") or {}).values()}
        why += [f"{t.get('task_id')}: the run graded no verifier under the condition {c}" for c in conds if c not in recorded]
    if why:
        raise Refused(why)
    policy = cfg["label_source"]["policy"]
    cands: dict = {}
    try:
        rows, meta = build_rows(run_dir, tasks_root, allow_proposed=policy == "pilot", policy=policy, candidates=cands)
        tms = {t["task_id"]: load(tasks_root / t["task_id"] / "task.json", TaskManifest) for t in run_manifest["tasks"]}
    except (ConditionConflict, StratumError, OSError, ValueError, KeyError) as exc:
        raise Refused([f"the run's records cannot be read as the analysis reads them ({type(exc).__name__}: {exc})"]) from None
    family = {tid: m.family_id for tid, m in tms.items()}
    populations = sorted({r.population for r in rows})
    if len(populations) > 1:
        why.append(f"the run mixes the populations {', '.join(populations)}, which are never pooled silently")
    attempts = {k: c for k, c in cands.items() if c.origin == CandidateOrigin.fresh_attempt}
    excluded = {k: w for k, c in attempts.items() if (w := attempt_exclusion(c)) is not None}
    kept = {k: c for k, c in sorted(attempts.items()) if k not in excluded}
    if not kept:
        why.append(f"the run holds no fresh attempt (origin {ATTEMPT}) that the analysis keeps")
        raise Refused(why)
    no_reference = sorted({tid for tid, _ in kept
                           if not (tasks_root / tid / tms[tid].contracts.get("reference", "contracts/reference.json")).is_file()})
    if no_reference:
        why.append(f"no reference contract for {', '.join(no_reference)}: the kinds of invalid attempt cannot be told apart")
    by_pair: dict[tuple[str, str, str], list] = defaultdict(list)
    for r in rows:
        if (r.task_id, r.candidate_id) in kept and r.condition in conds:
            by_pair[(r.task_id, r.candidate_id, r.condition)].append(r)
    pairs: dict[tuple[str, str, str], object] = {}
    problems: dict[str, list[str]] = defaultdict(list)
    for tid, cid in kept:
        for c in conds:
            rs = by_pair.get((tid, cid, c), [])
            if not rs:
                problems["missing"].append(f"{cid} under {c}")
            elif len(rs) > 1:
                problems["recorded more than once"].append(f"{cid} under {c} ({len(rs)} results)")
            elif rs[0].outcome == "unresolved":
                problems["unresolved (its repeats disagree)"].append(f"{cid} under {c}")
            elif rs[0].outcome in INFRA:
                problems["an infrastructure outcome"].append(f"{cid} under {c} ({rs[0].outcome})")
            else:
                pairs[(tid, cid, c)] = rs[0]
    for what, items in sorted(problems.items()):
        why.append(f"{len(items)} selected pair(s) {what}, so no verdict to select on: {', '.join(items)}")
    labels = {k: candidate_label(c, policy) for k, c in kept.items()}
    unlabeled = [cid for (_, cid), lab in labels.items() if lab is None]
    if len(unlabeled) == len(kept):
        why.append(f"no attempt has a label under the label source (policy {policy}"
                   + (", human labels only" if policy == "human" else "") + "): a run without labels")
    elif unlabeled:
        why.append(f"{len(unlabeled)} of the {len(kept)} attempts have no label under the label source (policy {policy}): "
                   + ", ".join(unlabeled))
    tasks = sorted({tid for tid, _ in kept})
    gate, lacking = _gate(rows, tasks, conds, cfg["cell_gate"]["noop_required"])
    why += lacking
    if why:
        raise Refused(why)
    consistency = _against_analysis(run_dir, pairs, policy, sorted(excluded), gate)
    families = sorted({family[tid] for tid, _ in kept})
    info: dict[tuple[str, str], dict] = {}
    for (tid, cid), c in kept.items():
        lab = labels[(tid, cid)]
        nts = {pairs[(tid, cid, cond)].negative_type for cond in conds}
        if len(nts) != 1 or {pairs[(tid, cid, cond)].label for cond in conds} != {lab.value}:
            raise Refused([f"{cid}: its rows disagree on its label or negative type ({sorted(nts)})"])
        nt = nts.pop()
        violated = sorted(lab.violated_requirements)
        info[(tid, cid)] = {
            "task_id": tid, "family_id": family[tid], "candidate_id": cid, "variant": c.attempt.variant,
            "configuration": c.attempt.configuration, "patch_sha256": c.patch_sha256, "graded_patch_sha256": _patch_key(c),
            "label": lab.value, "human_label": c.final_label() is not None, "violated_requirements": violated,
            "negative_type": nt, "kind": _kind(lab.value, violated, nt),
            "outcomes": {cond: pairs[(tid, cid, cond)].outcome for cond in conds}}
    keys = list(info)

    def ids(ks: list[tuple[str, str]]) -> list[str]:
        return sorted(info[k]["candidate_id"] for k in ks)

    roles = {c: sorted(r for r, x in cfg["data_filters"].items() if x == c) for c in conds}
    conditions = {}
    for c in conds:
        admitted = [k for k in keys if info[k]["outcomes"][c] == "pass"]
        gated = [k for k in admitted if gate[c][k[0]]["kept"]]
        lost = [k for k in admitted if not gate[c][k[0]]["kept"]]
        conditions[c] = {"short": SHORT.get(c, c), "data_filter_roles": roles[c], "cells": gate[c],
                         "cells_dropped": sorted(t for t, cell in gate[c].items() if not cell["kept"]),
                         "gated": {"admitted": ids(gated), **_block(gated, info, families, "admitted")},
                         "ungated": {"admitted": ids(admitted), **_block(admitted, info, families, "admitted")},
                         "lost_to_the_gate": {"admitted": ids(lost), "counts": _tally(lost, info, families, "admitted")}}
    graded = {(r.task_id, r.candidate_id) for r in rows}
    not_selected = Counter(cands[k].origin.value for k in graded if k not in attempts)
    human = sum(e["human_label"] for e in info.values())
    natural = any(m.population == Population.natural_pr_review for m in tms.values())
    run_meta = {"run_id": run_manifest["run_id"], "code_revision": run_manifest.get("code_revision"),
                "repeats": run_manifest["repeats"], "started_at": run_manifest.get("started_at"),
                "finished_at": run_manifest.get("finished_at"), "results": meta["n_results"],
                "harness_versions": dict(sorted(meta["harness_versions"].items())), "population": populations[0]}
    tag, when = STANDINGS[cfg["standing"]]
    return {
        "schema": SCHEMA,
        "standing": cfg["standing"],
        "tag": f"{tag}: built from the records of {run_manifest['run_id']} {when}; it never replaces that run's analysis",
        "status": cfg["status"],
        "what_this_step_does": ("lists, for each condition, the kept attempts that its verifier admits, with the cell gate "
                                "(the data filter) and without it, and counts them by label and kind; it trains, samples and "
                                "downloads no model, and nothing here measures training value"),
        "experiment": cfg["experiment"],
        "config": cfg_meta,
        "code_revision": {
            "run": run_manifest.get("code_revision"),
            "selection": ("the selection's code is identified by the sha256 of each file that ran (selection_files_sha256), "
                          "not by a git revision, so that the output regenerates byte for byte at any commit that holds the "
                          "same code"),
            "selection_files_sha256": _code(natural)},
        "run": run_meta,
        "inputs_sha256": _inputs(run_dir, tasks_root, run_manifest, consistency["analysis_json"] == "matches"),
        "rules": RULES,
        "acceptance_rule": dict(ACCEPTANCE_RULE),
        "refused_outcomes": list(REFUSED_OUTCOMES),
        "cell_gate": dict(cfg["cell_gate"]),
        "label_source": {"policy": policy, "labeler": cfg["label_source"]["labeler"],
                         "attempts_with_a_human_label": human},
        "data_filters": dict(sorted(cfg["data_filters"].items())),
        "condition_order": conds,
        "families": families,
        "tasks": tasks,
        "excluded": [{"task_id": t, "candidate_id": cid, "attempt_id": attempts[(t, cid)].attempt.attempt_id
                      if attempts[(t, cid)].attempt else None, "reason": w} for (t, cid), w in sorted(excluded.items())],
        "not_selected": dict(sorted(not_selected.items())),
        "attempts": {info[k]["candidate_id"]: {f: v for f, v in info[k].items() if f != "candidate_id"} for k in keys},
        "pool": _block(keys, info, families, "attempts"),
        "conditions": conditions,
        "consistency": consistency,
    }


def _cell(entry: dict, families: list[str]) -> str:
    return f"{entry['total']} ({', '.join(str(entry['per_family'][f]) for f in families)})"


def _name(cond: str) -> str:
    short = SHORT.get(cond)
    return f"{short} `{cond}`" if short else f"`{cond}`"


def _rows(sel: dict, columns) -> list[str]:
    """Table rows: the pool, then each condition gated (its data filter) and ungated; ``columns(block, first)`` gives a
    row's cells from a block of tallies, ``first`` naming its first tally."""
    n = len(sel["tasks"])
    lines = [f"| *every kept attempt (the pool)* | | | {' | '.join(columns(sel['pool'], 'attempts'))} |"]
    for c in sel["condition_order"]:
        d = sel["conditions"][c]
        role = ", ".join(f"data filter `{r}`" for r in d["data_filter_roles"]) or "reported only"
        lines.append(f"| {_name(c)} | {role} | gated: {n - len(d['cells_dropped'])} of {n} | "
                     f"{' | '.join(columns(d['gated'], 'admitted'))} |")
        lines.append(f"| {_name(c)} | descriptive | ungated: {n} of {n} | {' | '.join(columns(d['ungated'], 'admitted'))} |")
    return lines


def render_markdown(sel: dict) -> str:
    """The short tables of a selection manifest; every value comes from the manifest."""
    fams, run, pool = sel["families"], sel["run"], sel["pool"]["counts"]
    order = sel["condition_order"]
    n = pool["attempts"]["total"]
    u1 = sel["pool"]["by_variant"].get("u1", {}).get("attempts", {}).get("total", 0)
    ls = sel["label_source"]
    if ls["policy"] == "human":
        labels = "human labels only"
    elif ls["attempts_with_a_human_label"]:
        labels = (f"human labels for {ls['attempts_with_a_human_label']} attempt(s), else rule D19's proposals "
                  f"(labeler `{ls['labeler']}`), which are model proposals")
    else:
        labels = f"rule D19's proposals (labeler `{ls['labeler']}`), which are model proposals; no attempt has a human label"
    excluded = "; ".join(f"`{e['candidate_id']}` ({e['reason']})" for e in sel["excluded"]) or "none"
    others = ", ".join(f"{k} `{o}`" for o, k in sel["not_selected"].items()) or "none"
    con = sel["consistency"]
    fields = [f.replace("_", " ") for f in con.get("compared_fields", [])]
    also = [x for x, on in (("its excluded attempts", con.get("excluded_attempts_compared")),
                            ("the cells its oracle-gated view drops", con.get("oracle_gated_compared"))) if on]
    compared = ("The run has no `analysis.json` to compare with." if con["analysis_json"] == "absent" else
                f"Every selected pair's {', '.join(fields[:-1])} and {fields[-1]} match the run's `analysis.json`"
                + (f", and so do {' and '.join(also)}." if also else "."))
    design = (f" {u1} of the {n} attempts saw only the first request (variant `u1`), by the run's design, and the "
              "invalid counts below follow from that design.") if u1 else ""
    tag, when = STANDINGS[sel["standing"]]
    banner = (f"> **{tag[0].upper() + tag[1:]}.** Built from the records of `{run['run_id']}` {when}; it never replaces the "
              "run's own analysis (`analysis.md` in the run directory). This step trains, samples and downloads no model, "
              f"and nothing here measures training value. The configuration's status: {sel['status']} Labels: {labels}. "
              "Fresh attempts are made without any verifier, reference or label (protocol §15.4), so none was optimised "
              f"against a verifier.{design}")
    provenance = (f"Generated by `python scripts/build_training_selection.py --config {sel['config']['file']}` (config "
                  f"sha256 `{sel['config']['sha256'][:12]}`). The run: code revision "
                  f"`{(run['code_revision'] or 'not recorded')[:12]}`, each pair graded {run['repeats']} times, "
                  f"{', '.join(sorted(run['harness_versions']))}. Every input's sha256, and the selection code's, are in "
                  f"`{MANIFEST}`. {compared}")
    acceptance = ("* **Acceptance, the run's own rule.** A condition admits an attempt when the run recorded `pass` for "
                  f"the pair. Each pair was graded {run['repeats']} times, and the grader records `pass` only when every "
                  "repeat passed: repeats that disagree are `unresolved` (protocol §6, §15.3). Every other outcome is a "
                  "rejection. No pair read here is unresolved, missing, recorded twice or ended in an infrastructure "
                  "outcome; the script refuses a run where one is.")
    cells = [(c, t, cell) for c in order for t, cell in sel["conditions"][c]["cells"].items()]
    with_noop = sum(bool(cell["noop"]) for _, _, cell in cells)
    noop = ("The run graded no no-op of these tasks, so the gate here is its reference part alone, which is the "
            "analysis' oracle-gated view (protocol §15.7)." if not with_noop else
            f"The run graded the no-op in {with_noop} of the {len(cells)} cells.")
    dropped = "; ".join(f"{SHORT.get(c, c)} drops {t} ({cell['dropped']})" for c, t, cell in cells if not cell["kept"])
    gate = ("* **The cell gate.** A condition contributes data from a task only when its verifier passes the task's "
            "reference (a recorded `pass`, on every repeat) and, where the run graded the task's no-op, fails on it (a "
            f"recorded `task_failure`). {noop} The data filters are the gated sets; the ungated rows describe each "
            f"verifier. {('Dropped cells: ' + dropped + '.') if dropped else 'No cell is dropped.'}")
    attempts = (f"* **Attempts.** {n} fresh attempts that the run's analysis keeps. Excluded by its rule: {excluded}. "
                f"Graded candidates that are not attempts, not selected: {others}.")
    kinds = ("* **Kinds of invalid attempt.** A correction violator breaks a reference requirement introduced after the "
             "first request; a regression-only attempt breaks only the regression norm (violated requirements exactly "
             "`REGRESSION`); other: any other invalid attempt.")
    legend = (f"Each cell: the total, then the counts of {', '.join(fams)} in parentheses. A total is the sum of its "
              "families' counts, not an estimate; no rate is given. Attempts: in the first row every kept attempt, in the "
              "others the attempts the condition admits. Tasks: the cells (tasks) whose data a row counts.")
    cols = ("invalid", "correction_violator", "regression_only", "other_invalid", "valid", "ambiguous")
    lines = [f"# Training-data selection on `{run['run_id']}`", "", banner, "", provenance, "", acceptance, gate, attempts,
             kinds, "", legend, "",
             ("| Condition | Role in the plan | Tasks | Attempts | Invalid | Correction violators | Regression-only "
              "| Other invalid | Valid | Ambiguous |"),
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    lines += _rows(sel, lambda b, first: [_cell(b["counts"][k], fams) for k in (first, *cols)])
    variants = sorted(sel["pool"]["by_variant"])
    lines += ["", "By instruction variant (the same cells, for the attempts of each variant):", "",
              "| Condition | Role in the plan | Tasks | " + " | ".join(f"`{v}`: attempts | `{v}`: invalid" for v in variants)
              + " |", "| --- | --- | --- | " + " | ".join("--- | ---" for _ in variants) + " |"]
    lines += _rows(sel, lambda b, first: [_cell(b["by_variant"][v][k], fams) for v in variants for k in (first, "invalid")])
    configurations = sorted({g for v in sel["pool"]["by_variant_and_configuration"].values() for g in v})
    groups = [(v, g) for v in variants for g in configurations]
    lines += ["", "By instruction variant and agent configuration (the same cells, for the attempts of each):", "",
              "| Condition | Role in the plan | Tasks | "
              + " | ".join(f"`{v}`, `{g}`: attempts | `{v}`, `{g}`: invalid" for v, g in groups) + " |",
              "| --- | --- | --- | " + " | ".join("--- | ---" for _ in groups) + " |"]
    lines += _rows(sel, lambda b, first: [_cell(b["by_variant_and_configuration"][v][g][k], fams)
                                          for v, g in groups for k in (first, "invalid")])
    distinct = [(f"{SHORT.get(c, c)} {which}", sel["conditions"][c][which]) for c in order for which in ("gated", "ungated")]
    if sel["pool"]["distinct_graded_patches"] == n and all(
            b["distinct_graded_patches"] == b["counts"]["admitted"]["total"] for _, b in distinct):
        lines += ["", ("No two kept attempts of a task share a graded patch, so every count of attempts above is also a "
                       "count of distinct graded patches.")]
    else:
        lines += ["", f"Distinct graded patches among the attempts counted: pool {sel['pool']['distinct_graded_patches']} of "
                  f"{n}; " + "; ".join(f"{name} {b['distinct_graded_patches']} of {b['counts']['admitted']['total']}"
                                       for name, b in distinct) + "."]
    return "\n".join(lines) + "\n"


def outputs(sel: dict) -> dict[str, bytes]:
    """The output files' bytes: the manifest as the repository writes JSON (store.write_json) and the table."""
    return {MANIFEST: (json.dumps(sel, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            TABLE: render_markdown(sel).encode("utf-8")}


def _write(out_dir: Path, files: dict[str, bytes]) -> None:
    """Write every file next to its target, then move each into place."""
    out_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[str, Path]] = []
    try:
        for name, data in sorted(files.items()):
            fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=out_dir)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.chmod(tmp, 0o644)
            staged.append((tmp, out_dir / name))
        for tmp, dst in staged:
            os.replace(tmp, dst)
    finally:
        for tmp, _ in staged:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _summary(sel: dict) -> str:
    parts = []
    for c in sel["condition_order"]:
        d = sel["conditions"][c]
        k = d["gated"]["counts"]
        parts.append(f"{SHORT.get(c, c)} admits {k['admitted']['total']} gated ({k['invalid']['total']} invalid: "
                     f"{k['correction_violator']['total']} correction violators, {k['regression_only']['total']} "
                     f"regression-only, {k['other_invalid']['total']} other), {d['ungated']['counts']['admitted']['total']} "
                     "ungated")
    return (f"{sel['run']['run_id']}: {sel['pool']['counts']['attempts']['total']} kept attempts, {len(sel['excluded'])} "
            "excluded; " + "; ".join(parts))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="the selection config (default: %(default)s)")
    ap.add_argument("--run", type=Path, help="the run directory (default: the config's run.dir)")
    ap.add_argument("--tasks-root", type=Path, help="the task directories (default: the config's tasks_root)")
    ap.add_argument("--out", type=Path, help="the output directory (default: the config's out)")
    ap.add_argument("--check", action="store_true", help="write nothing; compare a rebuilt output with the files in --out")
    a = ap.parse_args(argv)
    try:
        cfg, cfg_meta = read_config(a.config)
        run_dir = a.run if a.run is not None else ROOT / cfg["run"]["dir"]
        tasks_root = a.tasks_root if a.tasks_root is not None else ROOT / cfg["tasks_root"]
        out_dir = a.out if a.out is not None else ROOT / cfg["out"]
        if any(_inside(out_dir, p) for p in (ROOT / "results" / "runs", run_dir, tasks_root)):
            raise Refused([(f"the output directory {_shown(out_dir)} lies in results/runs/, the run directory or the tasks "
                            "root, which this script never writes")])
        sel = build_selection(cfg, cfg_meta, run_dir, tasks_root)
    except Refused as exc:
        print(f"build_training_selection: refused, nothing written ({len(exc.reasons)} reason(s)):", file=sys.stderr)
        for reason in exc.reasons:
            print(f"  - {reason}", file=sys.stderr)
        return 2
    files = outputs(sel)
    if a.check:
        differ = [name for name, data in sorted(files.items())
                  if not (out_dir / name).is_file() or (out_dir / name).read_bytes() != data]
        if differ:
            print(f"build_training_selection: does not regenerate byte for byte in {_shown(out_dir)}: {', '.join(differ)}",
                  file=sys.stderr)
            return 1
        print(f"build_training_selection: regenerates byte for byte: {', '.join(sorted(files))} in {_shown(out_dir)}")
        return 0
    _write(out_dir, files)
    print(f"build_training_selection: {_summary(sel)}; wrote {', '.join(sorted(files))} in {_shown(out_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
