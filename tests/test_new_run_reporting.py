"""The reporting rules of new runs (protocol v0.7 §15.7, v0.8 §16.6) in ``tracecontract analyze`` and the report.

A run graded with tc-harness/0.3.5 gets them by default: each distinct graded patch counted once,
the per-family table as the primary display, exact sign-flip p-values with their floors, the
oracle-gated view, bootstrap intervals in an appendix marked as not inferential below 10 families,
and, for fresh attempts, solve rates per configuration and variant with the audit exclusions. B3
(diff-derived) is in the condition order, the comparisons and the report. The report also names
the run's populations and shows pooled populations and strata separately.

Synthetic fixtures only: three hand-written task families, a hand-written run manifest and results
(no grading, no Docker), and fixture attempt records. They check code behaviour and are not
research evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tracecontract.analysis import NEW_RUN_RULES, PILOT_RULES, MixedPopulations, analyze, reporting_rules
from tracecontract.report import build_report
from tracecontract.schemas import (
    AttemptAudit, AttemptRecord, Candidate, CandidateOrigin, ContractVariant, EvidenceSpan, Label, LabelerKind, Outcome,
    Population, Requirement, RequirementKind, RequirementStatus, SnapshotSource, Split, TaskContract, TaskManifest,
    VerificationResult, sha256_text,
)
from tracecontract.store import append_jsonl, dump, write_json
from tracecontract.strata import StratumManifest

D19 = "builder:refcheck+regression+construction:v1"
T0 = "2026-11-22T10:00:00+00:00"
SHA = "cd" * 32
HARNESS = "tc-harness/0.3.5"
TASKS = ("T1", "T2", "T3")
VERIFIERS = ("initial_plain", "full_plain", "diff_derived")
# kind: (origin, D19 label, violated requirements, patch body); the same body is the same graded patch.
OWN = {"reference": (CandidateOrigin.reference, None, [], "ref"), "pre": (CandidateOrigin.observed_pre_correction, "invalid", ["R-corr"], "pre"),
       "alt": (CandidateOrigin.valid_alternative, "valid", [], "alt"), "nm": (CandidateOrigin.constructed_near_miss, "invalid", ["R-init"], "nm")}
DUP = {"nm-dup": (CandidateOrigin.constructed_near_miss, "invalid", ["R-corr"], "pre")}  # T1 only: the pre-correction patch
# kind: (D19 label, violated, configuration, variant, audit passed (None: not audited), patch body)
FRESH = {"fa-1": ("valid", [], "config-A", "u1", True, "fa1"), "fa-2": ("invalid", ["R-corr"], "config-B", "u1", True, "fa2"),
         "fa-3": ("valid", [], "config-A", "final", False, "fa3"), "fa-4": ("valid", [], "config-B", "final", None, "fa4")}
FRESH_IN = {"T1": ("fa-1", "fa-2", "fa-3"), "T2": ("fa-1", "fa-2", "fa-4")}
SAME_AS_PRE = {("T1", "fa-2")}  # this attempt's final state is T1's pre-correction state


def _patch(body: str) -> str:
    return f"--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-X = 1\n+X = '{body}'\n"


def _outcome(task: str, verifier: str, kind: str) -> str:
    """Stub outcomes: C1 accepts what the correction rules out, C3 does not, B3 accepts the near misses."""
    if kind == "reference":
        return "task_failure" if (task, verifier) == ("T3", "initial_plain") else "pass"  # C1 fails its reference in T3
    if kind == "nm-dup" and verifier == "diff_derived":
        return "pass"  # differs from the other candidates with the same graded patch
    if kind in ("pre", "nm-dup", "fa-2"):
        return "pass" if verifier == "initial_plain" else "task_failure"
    if kind == "nm":
        return "pass" if verifier == "diff_derived" else "task_failure"
    if kind == "alt" and (task, verifier) == ("T2", "initial_plain"):
        return "task_failure"
    return "pass"


def _cand(tid: str, kind: str, origin: CandidateOrigin, label: str | None, violated: list[str], body: str,
          attempt: AttemptRecord | None = None, extra: list[Label] = ()) -> Candidate:
    patch = _patch(body)
    labels = [Label(value=label, violated_requirements=violated, labeler=D19, labeler_kind=LabelerKind.model, timestamp=T0)] if label else []
    return Candidate(candidate_id=f"{tid}-{kind}", task_id=tid, origin=origin, split=Split.dev if kind == "reference" else Split.eval,
                     patch=patch, patch_sha256=sha256_text(patch), produced_by="fixture", labels=labels + list(extra),
                     attempt=None if attempt is None else attempt.model_copy(update={"patch_sha256": sha256_text(patch)}))


def _attempt(tid: str, kind: str, config: str, variant: str, passed: bool | None) -> AttemptRecord:
    audit = None if passed is None else AttemptAudit(profile="fresh-attempt:v1", passed=passed, audited_at=T0,
                                                     findings=[] if passed else ["read a file of the repository"])
    return AttemptRecord(attempt_id=f"fresh-v1-{tid}-{kind}", configuration=config, variant=variant, instruction_sha256=SHA,
                         started_at=T0, ended_at=T0, turns=9, tool_calls=30, ended="finished" if passed else "gave_up",
                         patch_sha256="0" * 64, run_record="private-runs/fresh-v1/x.json", audit=audit)


def _req(rid: str, kind: RequirementKind, event: str) -> Requirement:
    return Requirement(req_id=rid, statement=f"Statement of {rid}.", kind=kind, status=RequirementStatus.explicit, introduced_at=event,
                       evidence=[EvidenceSpan(event_id=event, start=0, end=1, quote="x")], proposer="fixture")


def _run(root: Path, *, harness: str = HARNESS, populations: dict[str, Population] | None = None,
         with_strata: bool = True, extra_labels: dict[str, list[Label]] | None = None) -> Path:
    """Tasks T1-T3 under ``root/tasks`` and a recorded run ``root/results/runs/r`` (manifest and results only)."""
    run = root / "results" / "runs" / "r"
    run.mkdir(parents=True)
    manifest = {"run_id": "r", "started_at": T0, "code_revision": "fixture", "tasks": []}
    for tid in TASKS:
        td = root / "tasks" / tid
        dump(TaskContract(contract_id=f"{tid}-reference", task_id=tid, session_id=f"{tid}-s", variant=ContractVariant.reference,
                          created_by="fixture", created_at=T0, requirements=[
                              _req("R-init", RequirementKind.change, f"{tid}-s/L000001.00"),
                              _req("R-corr", RequirementKind.invariant, f"{tid}-s/L000005.00")]), td / "contracts" / "reference.json")
        kinds = {**OWN, **(DUP if tid == "T1" else {})}
        cands = {k: _cand(tid, k, *spec, extra=(extra_labels or {}).get(f"{tid}-{k}", [])) for k, spec in kinds.items()}
        for k, c in cands.items():
            dump(c, td / "candidates" / f"{c.candidate_id}.json")
        pop = (populations or {}).get(tid, Population.controlled)
        dump(TaskManifest(task_id=tid, family_id=tid, population=pop, status="pending_review", provenance="provenance.json",
                          snapshot_source=SnapshotSource(repo_url="https://example.invalid/fixture", commit="0" * 40),
                          env_requirements=[], contracts={"reference": "contracts/reference.json"},
                          candidates=[f"candidates/{c.candidate_id}.json" for c in cands.values()]), td / "task.json")
        entry = {"task_id": tid, "family_id": tid, "verifiers": {v: {"condition": v} for v in VERIFIERS},
                 "candidates": {c.candidate_id: {"origin": c.origin.value, "patch_sha256": c.patch_sha256} for c in cands.values()}}
        graded = dict(cands)
        if with_strata and tid in FRESH_IN:
            rels = []
            for k in FRESH_IN[tid]:
                label, violated, config, variant, passed, body = FRESH[k]
                body = "pre" if (tid, k) in SAME_AS_PRE else body
                c = _cand(tid, k, CandidateOrigin.fresh_attempt, label, violated, body, _attempt(tid, k, config, variant, passed))
                rel = f"strata/fresh-v1/candidates/{c.candidate_id}.json"
                dump(c, td / rel)
                rels.append(rel)
                graded[k] = c
                entry["candidates"][c.candidate_id] = {"origin": c.origin.value, "patch_sha256": c.patch_sha256,
                                                       "stratum": "fresh-v1", "path": rel}
            sm = td / "strata" / "fresh-v1.json"
            dump(StratumManifest(stratum="fresh-v1", task_id=tid, candidates=rels), sm)
            entry["strata"] = {"fresh-v1": {"manifest": "strata/fresh-v1.json", "manifest_sha256": hashlib.sha256(sm.read_bytes()).hexdigest()}}
        manifest["tasks"].append(entry)
        for k, c in graded.items():
            for v in VERIFIERS:
                oc = _outcome(tid, v, k)
                append_jsonl(VerificationResult(run_id="r", task_id=tid, verifier_id=v, candidate_id=c.candidate_id, outcome=Outcome(oc),
                                                reward=1.0 if oc == "pass" else 0.0, started_at=T0, finished_at=T0, wall_s=0.1,
                                                harness_version=harness), run / "results.jsonl")
    write_json(manifest, run / "manifest.json")
    return run


@pytest.fixture()
def new_run(tmp_path) -> tuple[Path, dict]:
    run = _run(tmp_path)
    return run, analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=200)


def _cmp(a: dict, x: str, y: str, metric: str) -> dict:
    return next(d for d in a["comparisons"] if (d["a"], d["b"], d["metric"]) == (x, y, metric))


def test_the_rules_follow_the_harness_of_the_run():
    assert reporting_rules({"tc-harness/0.3.3": 240})[0] == PILOT_RULES  # every recorded pilot run
    assert reporting_rules(["tc-harness/0.1.0", "tc-harness/0.2.0", "stub"])[0] == PILOT_RULES
    rules, basis = reporting_rules(["tc-harness/0.3.3", "tc-harness/0.3.5"])
    assert rules == NEW_RUN_RULES and "tc-harness/0.3.5" in basis
    assert reporting_rules(["tc-harness/0.4.0"])[0] == NEW_RUN_RULES


def test_each_distinct_graded_patch_counts_once(new_run):
    _, a = new_run
    dp = a["distinct_patches"]
    # T1: 6 held-out candidates (fa-3 is excluded) of which pre, nm-dup and fa-2 share a patch; T2: 5; T3: 3.
    assert (dp["n_heldout"], dp["n_distinct"]) == (14, 12)
    (g,) = dp["groups"]
    assert (g["representative"], g["members"], g["label"], g["labels_agree"]) == ("T1-pre", ["T1-pre", "T1-fa-2", "T1-nm-dup"], "invalid", True)
    assert g["outcomes_differ"] == ["diff_derived"]  # counted as unresolved, a rejection
    fa = a["conditions"]["initial_plain"]["false_acceptance"]
    assert (fa["num"], fa["den"]) == (4, 7)
    every = a["sensitivity_every_candidate"]["initial_plain"]["false_acceptance"]
    assert (every["num"], every["den"]) == (6, 9)  # duplicates included, for comparison only
    b3 = a["conditions"]["diff_derived"]["false_acceptance"]
    assert (b3["num"], b3["den"]) == (3, 7)  # T1's unit is unresolved under B3, so rejected


def test_the_per_family_table_and_exact_sign_flip_tests(new_run):
    run, a = new_run
    assert a["per_family"]["initial_plain"] == {"T1": {"fa_num": 1, "fa_den": 2, "fr_num": 0, "fr_den": 2},
                                                "T2": {"fa_num": 2, "fa_den": 3, "fr_num": 1, "fr_den": 2},
                                                "T3": {"fa_num": 1, "fa_den": 2, "fr_num": 0, "fr_den": 1}}
    c = _cmp(a, "initial_plain", "full_plain", "fa")
    sf = c["signflip"]["pooled"]
    assert (sf["k"], sf["p_greater"], sf["p_two_sided"], sf["floor_one_sided"], sf["floor_two_sided"]) == (3, 0.125, 0.25, 0.125, 0.25)
    assert c["signflip"]["family_mean"]["p_greater"] == 0.125
    assert c["per_family_counts"]["T2"] == {"a_num": 2, "b_num": 0, "den": 3}
    fr = _cmp(a, "initial_plain", "full_plain", "fr")["signflip"]["pooled"]
    assert (fr["p_greater"], fr["zero_families"], fr["conditional_floor_one_sided"]) == (0.5, 2, 0.5)
    # B3 is compared with the correction-aware contract; there is no C4 in this run, so no B3 vs C4.
    assert [(d["a"], d["b"]) for d in a["comparisons"]][::2] == [("initial_plain", "full_plain"), ("diff_derived", "full_plain")]
    assert list(a["conditions"]) == ["initial_plain", "full_plain", "diff_derived"]
    assert all(d["ci95_not_inferential"] for d in [*a["comparisons"], *a["conditions"].values()])
    assert a["meta"]["bootstrap"]["inferential"] is False and a["meta"]["reporting_rules"]["rules"] == NEW_RUN_RULES
    assert "code/stats.py" in a["meta"]["inputs"]["files_sha256"]
    md = (run / "analysis.md").read_text()
    order = ["**Reporting rules of a new run**", "## Primary display", "## Paired comparisons: exact sign-flip",
             "**Null results.** 4 of 4 tested comparisons", "## Pooled false acceptance", "## Oracle-gated view",
             "## Distinct graded patches", "## Appendix: cluster-bootstrap intervals"]
    assert [md.index(x) for x in order] == sorted(md.index(x) for x in order)
    assert "| initial_plain | 1/2 | 0/2 | 2/3 | 1/2 | 1/2 | 0/1 | 0.57 (4/7) | 0.20 (1/5) |" in md
    assert "no two-sided p-value can go below 0.25, so none can reach 0.05" in md
    assert "not inferential: the run has 3 task families, fewer than 10" in md
    assert "## Per-family rates behind the macro rates" not in md  # the primary display replaces it
    main_table = md[md.index("## Pooled false acceptance"):md.index("## By candidate stratum")]
    assert "| initial_plain | 0.57 (4/7) | [" in main_table  # no bootstrap interval after the rate; the exact interval follows


def test_the_oracle_gated_view_reports_the_lost_yield(new_run):
    _, a = new_run
    c1 = a["oracle_gated"]["conditions"]["initial_plain"]
    assert (c1["cells_kept"], c1["cells"], c1["dropped"]) == (2, 3, {"T3": "does not pass its reference (task_failure)"})
    assert c1["lost_yield"] == {"invalid": 2, "valid": 1}
    assert (c1["false_acceptance"]["num"], c1["false_acceptance"]["den"]) == (3, 5)
    assert a["oracle_gated"]["conditions"]["full_plain"]["cells_kept"] == 3
    gated = next(d for d in a["oracle_gated"]["comparisons"] if (d["a"], d["metric"]) == ("initial_plain", "fa"))
    assert gated["tasks"] == ["T1", "T2"] and gated["signflip"]["pooled"]["p_greater"] == 0.25


def test_fresh_attempts_solve_rates_and_audit_exclusions(new_run):
    run, a = new_run
    f = a["fresh_attempts"]
    assert (f["n_attempts"], f["n_excluded"]) == (4, 2)
    assert {k: (d["attempts"], d["solved"], d["rate"]) for k, d in f["by_configuration_variant"].items()} == {
        "config-A/u1": (2, 2, 1.0), "config-B/u1": (2, 0, 0.0)}
    assert f["by_configuration_variant"]["config-A/u1"]["per_family"] == {"T1": {"attempts": 1, "solved": 1}, "T2": {"attempts": 1, "solved": 1}}
    assert [(x["candidate_id"], x["reason"].split(":")[0]) for x in f["excluded"]] == [
        ("T1-fa-3", "the fresh-attempt audit found a read of forbidden material"), ("T2-fa-4", "not audited")]
    assert f["u1_correction_violating"] == {"attempts": 4, "correction_violating": 2, "share": 0.5,
                                            "graded_by": {"initial_plain": {"accepted": 2, "n": 2}, "full_plain": {"accepted": 0, "n": 2}}}
    # Excluded attempts count nowhere: not in the outcomes, the strata tables or the label summary.
    listed = {r["candidate"] for rs in a["per_task"]["T1"].values() for r in rs}
    assert "T1-fa-3" not in listed and "T1-fa-1" in listed
    assert [x["candidate"] for x in a["labels"]["T1"]["strata"]["fresh-v1"]["candidates"]] == ["T1-fa-1", "T1-fa-2"]
    assert {q["candidate"] for q in a["labels"]["T1"]["strata"]["fresh-v1"]["review_queue"]} == {"T1-fa-1", "T1-fa-2"}
    fresh = a["by_stratum"]["fresh-v1"]["conditions"]["initial_plain"]["false_acceptance"]
    assert (fresh["num"], fresh["den"]) == (2, 2)  # within the stratum, T1-fa-2 is its own patch
    md = (run / "analysis.md").read_text()
    assert "| config-A | u1 | 2 | 2 | 0 | 0 | 1.00 | 2 / 0 / 0 | T1 1/1, T2 1/1 |" in md
    assert "* T2-fa-4 (T2, attempt fresh-v1-T2-fa-4): not audited" in md


def test_the_pilot_rules_can_be_asked_for_and_keep_the_earlier_tables(tmp_path):
    run = _run(tmp_path, with_strata=False)
    a = analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50, rules=PILOT_RULES)
    assert not {"per_family", "distinct_patches", "oracle_gated", "sensitivity_every_candidate"} & set(a)
    assert "reporting_rules" not in a["meta"] and "signflip" not in a["comparisons"][0]
    assert (a["conditions"]["initial_plain"]["false_acceptance"]["den"]) == 7  # T1-nm-dup counted on its own
    assert "code/stats.py" not in a["meta"]["inputs"]["files_sha256"]
    with pytest.raises(ValueError, match="unknown reporting rules"):
        analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50, rules="v9")
    b = analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50)
    assert b["meta"]["reporting_rules"]["rules"] == NEW_RUN_RULES  # the default for a run graded with 0.3.5


def test_the_report_of_a_new_run(new_run, tmp_path):
    run, _ = new_run
    html = build_report(run, tmp_path / "tasks", tmp_path, tmp_path / "report.html").read_text()
    for text in ("<b>Reporting rules of a new run</b>", "Primary display: rates per task family", "p (A &gt; B)",
                 "<b>Null results.</b>", "Oracle-gated view (secondary)", "Distinct graded patches", "Fresh-agent attempts",
                 "B3 diff-derived", "Appendix: cluster-bootstrap intervals", "<b>Not inferential:</b>", "<th>Stratum</th>",
                 "By candidate stratum", "excluded <span class='muted'>(not audited"):
        assert text in html, text
    assert html.index("Primary display") < html.index("Summary by verifier condition") < html.index("Appendix: cluster-bootstrap")
    assert "Sessions are <b>controlled</b>" in html  # a controlled run


def test_natural_sub_populations_are_reported_apart_and_never_called_controlled(tmp_path):
    pops = {"T1": Population.natural_pr_review, "T2": Population.natural_pr_review, "T3": Population.natural_chat}
    run = _run(tmp_path, populations=pops, with_strata=False)
    with pytest.raises(MixedPopulations, match=r"2 populations \(natural:chat: T3; natural:pr-review: T1, T2\)"):
        analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50)
    a = analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50, pool_populations=True)
    assert list(a["by_population"]) == ["natural:chat", "natural:pr-review"]
    assert a["by_population"]["natural:pr-review"]["tasks"] == ["T1", "T2"]
    html = build_report(run, tmp_path / "tasks", tmp_path, tmp_path / "report.html").read_text()
    banner = html[html.index("<div class='banner'>"):html.index("<h2>")]
    assert "<b>Populations pooled</b>" in banner and "natural PR-review" in banner and "controlled" not in banner
    assert "<h3>By population</h3>" in html and "<h4>natural:chat" in html


def test_a_natural_run_banner_names_its_population(tmp_path):
    pops = {t: Population.natural_pr_review for t in TASKS}
    run = _run(tmp_path, populations=pops, with_strata=False, harness="tc-harness/0.3.3")
    analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50)
    html = build_report(run, tmp_path / "tasks", tmp_path, tmp_path / "report.html").read_text()
    banner = html[html.index("<div class='banner'>"):html.index("<h2>")]
    assert "Tasks are <b>natural PR-review</b>" in banner and "controlled" not in banner


def test_source_evidence_labels_are_reported_apart_from_d19(tmp_path):
    se = Label(value="invalid", violated_requirements=["R-corr"], labeler="source-evidence:v1",
               labeler_kind=LabelerKind.source_evidence, timestamp=T0)
    run = _run(tmp_path, with_strata=False, extra_labels={f"{t}-pre": [se] for t in TASKS})
    a = analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50)
    s = a["source_evidence"]
    assert sorted(s["candidates"]) == ["T1/T1-pre", "T2/T2-pre", "T3/T3-pre"]
    assert s["conditions"]["initial_plain"]["invalid"] == {"accepted": 3, "n": 3}
    assert s["conditions"]["full_plain"]["invalid"] == {"accepted": 0, "n": 3}
    # D19 still labels the candidates: the source-evidence label is never a proposal or a human label.
    assert a["conditions"]["initial_plain"]["false_acceptance"]["den"] == 6
    assert "## Source-evidence labels (reported apart from D19)" in (run / "analysis.md").read_text()
