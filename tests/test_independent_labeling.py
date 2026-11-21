"""The independent labeler as a second labeling (protocol §15.4, §15.5), and the guard that keeps label support apart.

* When a run graded the label-support verifier ``independent_label`` (condition ``reference_check``, registered in
  ``verifiers_extra.json``), its outcome labels each candidate: valid if it passes, invalid on ``task_failure``,
  ambiguous on any other outcome, recorded as such. The analysis reports FA and FR per condition under the primary
  labels (D19) and under this labeling side by side, with the per-family tables, the agreement between D19 and the
  labeler (counts and a 2x2 table, per candidate stratum), and the fresh attempts' solve rates under each labeling.
* Neither label-support verifier (the reference checks, the labeler) is ever scored as an evaluated condition; a run
  that records one under an evaluated condition, or two verifiers of a task under one, is refused.

Synthetic fixtures only (tests/labeling_world.py): hand-written tasks and a stub grader instead of Docker. These
tests check code behaviour and are not research evidence.
"""

from __future__ import annotations

import json

import pytest

from labeling_world import TASKS, exit_code, install, make_task, run_evaluation
from tracecontract.analysis import (
    CONDITION_ORDER, INDEPENDENT_LABELER, LABEL_SUPPORT_CONDITION, PILOT_RULES, ConditionConflict, analyze, independent_label,
)
from tracecontract.report import build_report
from tracecontract.schemas import VerifierCondition


@pytest.fixture()
def world(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch)
    for t in TASKS:
        make_task(tmp_path, t)
    return tmp_path


@pytest.fixture()
def analysed(world):
    run = run_evaluation(world)
    return run, analyze(run, world / "tasks", allow_proposed=True, n_boot=50)


def _counts(x: dict) -> tuple[int, int, int, int]:
    fa, fr = x["false_acceptance"], x["false_rejection"]
    return fa["num"], fa["den"], fr["num"], fr["den"]


def test_the_labeler_outcome_gives_valid_invalid_or_ambiguous():
    assert independent_label("pass") == "valid" and independent_label("task_failure") == "invalid"
    for outcome in ("unresolved", "environment_failure", "verifier_error", "timeout"):
        assert independent_label(outcome) == "ambiguous"
    assert independent_label(None) is None  # not graded by the labeler: unlabeled


def test_a_second_labeling_with_all_three_verdicts(analysed):
    run, a = analysed
    x = a["independent_labeling"]
    assert (x["verifier"], x["tasks"]) == (INDEPENDENT_LABELER, ["T1", "T2"])
    # 14 held-out candidates (T2-fa-3 is excluded by its audit): each labeled once, duplicates included.
    assert x["labels"] == {"valid": 4, "invalid": 7, "ambiguous": 3, "not_graded": 0}
    assert x["ambiguous_outcomes"] == {"timeout": 1, "unresolved": 1, "verifier_error": 1}
    c = x["candidates"]
    assert "T2/T2-fa-3" not in c and len(c) == 14
    assert c["T1/T1-fa-4"] == {"label": "ambiguous", "outcome": "timeout", "d19": "invalid", "stratum": "fresh-v1"}
    assert c["T2/T2-fa-1"] == {"label": "ambiguous", "outcome": "unresolved", "d19": "valid", "stratum": "fresh-v1"}
    assert c["T2/T2-fa-4"]["label"] == "ambiguous" and c["T2/T2-fa-4"]["outcome"] == "verifier_error"
    assert (c["T2/T2-nm"]["label"], c["T2/T2-alt"]["label"], c["T1/T1-alt"]["label"]) == ("valid", "invalid", "valid")
    # The reference and the no-op are sanity checks of the labeler, never labeled candidates.
    assert x["sanity"]["T1"] == {"reference": {"pass": 1, "n": 1, "outcomes": {"pass": 1}},
                                 "noop": {"pass": 0, "n": 1, "outcomes": {"task_failure": 1}}}
    md = (run / "analysis.md").read_text()
    assert ("Held-out candidates: 4 valid, 7 invalid, 3 ambiguous (timeout 1, unresolved 1, verifier_error 1), 0 not graded"
            in md)
    # The primary labels are untouched: the labeler never changes a D19 label.
    labels = {r["candidate"]: r["label"] for rs in a["per_task"]["T2"].values() for r in rs}
    assert (labels["T2-nm"], labels["T2-alt"], labels["T2-fa-4"]) == ("invalid", "valid", "ambiguous")


def test_fa_and_fr_under_each_labeling_side_by_side(analysed):
    run, a = analysed
    x = a["independent_labeling"]
    c1, c3 = x["conditions"]["initial_plain"], x["conditions"]["full_plain"]
    # Each distinct graded patch once (T1-fa-1 and T1-fa-5 are one unit), as the primary analysis counts.
    assert _counts(c1["primary"]) == _counts(a["conditions"]["initial_plain"]) == (5, 7, 0, 5)
    assert _counts(c1["independent_label"]) == (6, 7, 1, 3)
    assert (c1["primary"]["excluded_unlabeled_or_ambiguous"], c1["independent_label"]["excluded_unlabeled_or_ambiguous"]) == (1, 3)
    assert _counts(c3["primary"]) == _counts(a["conditions"]["full_plain"]) == (0, 7, 0, 5)
    assert _counts(c3["independent_label"]) == (2, 7, 1, 3)
    assert c1["primary"]["per_family"] == a["per_family"]["initial_plain"]
    assert c1["independent_label"]["per_family"] == {"T1": {"fa_num": 3, "fa_den": 4, "fr_num": 0, "fr_den": 2},
                                                     "T2": {"fa_num": 3, "fa_den": 3, "fr_num": 1, "fr_den": 1}}
    fresh = x["by_stratum"]["fresh-v1"]["conditions"]["full_plain"]
    assert (_counts(fresh["primary"]), _counts(fresh["independent_label"])) == ((0, 3, 0, 3), (1, 3, 0, 1))
    own = x["by_stratum"]["task"]["conditions"]["initial_plain"]  # the primary column is the main by-stratum table
    assert _counts(own["primary"]) == _counts(a["by_stratum"]["task"]["conditions"]["initial_plain"]) == (2, 4, 0, 2)
    assert _counts(own["independent_label"]) == (3, 4, 1, 2)
    md = (run / "analysis.md").read_text()
    assert "| initial_plain | 0.71 (5/7) | 0.86 (6/7) | 0.00 (0/5) | 0.33 (1/3) | 1 / 3 |" in md
    assert "| initial_plain | independent | 3/4 | 0/2 | 3/3 | 1/1 | 0.86 (6/7) | 0.33 (1/3) |" in md
    assert "| full_plain | primary | 0/4 | 0/3 | 0/3 | 0/2 | 0.00 (0/7) | 0.00 (0/5) |" in md
    assert md.index("## Independent labeler: a second labeling") < md.index("## Oracle-gated view")


def test_the_agreement_between_d19_and_the_labeler(analysed):
    run, a = analysed
    ag = a["independent_labeling"]["agreement"]
    fresh, own, pooled = ag["by_stratum"]["fresh-v1"], ag["by_stratum"]["task"], ag["pooled"]
    # fresh-v1: 7 units (T1-fa-1 and T1-fa-5 count once); 4 decided by both, 3 of them agree.
    assert (fresh["n_units"], fresh["n_decided_by_both"], fresh["agree"], fresh["disagree"]) == (7, 4, 3, 1)
    assert fresh["table"] == {"valid": {"valid": 1, "invalid": 1}, "invalid": {"valid": 0, "invalid": 2}}
    assert fresh["agreement"] == 0.75 and fresh["kappa"] == pytest.approx(0.5) and not fresh["exploratory"]
    assert fresh["crosstab"]["valid"]["ambiguous"] == 1 and fresh["crosstab"]["invalid"]["ambiguous"] == 1
    assert fresh["crosstab"]["ambiguous"]["ambiguous"] == 1 and fresh["crosstab"]["none"] == dict.fromkeys(fresh["crosstab"]["none"], 0)
    assert [(d["representative"], d["d19"], d["independent_label"]) for d in fresh["disagreements"]] == [("T1-fa-3", "valid", "invalid")]
    # The task's own candidates of controlled families existed before the labeler was written: exploratory (§15.5).
    assert (own["n_units"], own["agree"], own["disagree"], own["exploratory"]) == (6, 4, 2, True)
    assert own["table"] == {"valid": {"valid": 1, "invalid": 1}, "invalid": {"valid": 1, "invalid": 3}}
    assert own["kappa"] == pytest.approx(0.25) and "existed before the labeler was written" in own["why_exploratory"]
    assert (pooled["n_units"], pooled["n_decided_by_both"], pooled["agree"], pooled["exploratory"]) == (13, 10, 7, True)
    md = (run / "analysis.md").read_text()
    section = md[md.index("### Agreement between D19 and the independent labeler"):md.index("**All strata pooled**")]
    assert "**Stratum fresh-v1 (tasks: T1, T2)**: 7 unit(s); both decide 4: agree 3, disagree 1 (agreement 0.75, Cohen's kappa 0.50)." in section
    assert "| D19 \\ independent | valid | invalid |\n| --- | --- | --- |\n| valid | 1 | 1 |\n| invalid | 0 | 2 |" in section
    assert "D19 valid, independent ambiguous: 1; D19 invalid, independent ambiguous: 1; D19 ambiguous, independent ambiguous: 1." in section
    assert "**Exploratory:** these are the task's own candidates" in section
    assert "* T1-fa-3 (T1): D19 valid, independent invalid (outcome task_failure)" in section


def test_the_pilot_rules_count_every_candidate_in_the_agreement(world):
    run = run_evaluation(world)
    a = analyze(run, world / "tasks", allow_proposed=True, n_boot=50, rules=PILOT_RULES)
    fresh = a["independent_labeling"]["agreement"]["by_stratum"]["fresh-v1"]
    assert (fresh["n_units"], fresh["n_decided_by_both"], fresh["agree"]) == (8, 5, 4)  # T1-fa-5 now counts on its own
    assert "each candidate once" in a["independent_labeling"]["agreement"]["rule"]


def test_solve_rates_under_each_labeling(analysed):
    run, a = analysed
    cells = a["fresh_attempts"]["by_configuration_variant"]
    # Every attempt counts, the duplicate T1-fa-5 included; the excluded T2-fa-3 counts nowhere.
    assert {k: (d["attempts"], d["solved"], d["independent_label"]["solved"], d["independent_label"]["not_solved"],
                d["independent_label"]["undecided"]) for k, d in cells.items()} == {
        "config-A/final": (1, 1, 1, 0, 0), "config-A/u1": (3, 2, 1, 1, 1), "config-B/final": (2, 0, 0, 0, 2),
        "config-B/u1": (2, 1, 0, 2, 0)}
    assert cells["config-A/u1"]["independent_label"]["rate"] == pytest.approx(1 / 3)
    assert cells["config-A/u1"]["independent_label"]["per_family"] == {"T1": {"attempts": 2, "solved": 1}, "T2": {"attempts": 1, "solved": 0}}
    assert "undecided, counted as not solved" in a["fresh_attempts"]["rule_independent_label"]
    md = (run / "analysis.md").read_text()
    assert "### Solve rates under each labeling" in md
    assert "| config-A | u1 | 3 | 2 | 0.67 | 1 | 1 | 1 | 0.33 | T1 1/2, T2 0/1 |" in md


def test_label_support_verifiers_are_never_scored_as_conditions(analysed):
    run, a = analysed
    assert LABEL_SUPPORT_CONDITION not in CONDITION_ORDER
    evaluated = ["initial_plain", "full_plain"]
    assert list(a["conditions"]) == evaluated and list(a["per_family"]) == evaluated
    assert set(a["outcome_counts"]) == set(evaluated) and set(a["sanity"]) == set(evaluated)
    assert {(d["a"], d["b"]) for d in a["comparisons"]} == {("initial_plain", "full_plain")}
    assert all(set(conds) == set(evaluated) for conds in a["per_task"].values())
    assert set(a["oracle_gated"]["conditions"]) == set(evaluated) and set(a["independent_labeling"]["conditions"]) == set(evaluated)
    # Both label-support verifiers were graded on the 18 candidates that count, and kept apart.
    assert a["meta"]["label_support"]["results"] == {"independent_label": 18, "reference_check": 18}
    entry = json.loads((run / "manifest.json").read_text())["tasks"][0]
    assert entry["verifiers"]["independent_label"]["condition"] == entry["verifiers"]["reference_check"]["condition"] == "reference_check"
    md = (run / "analysis.md").read_text()
    for line in md.splitlines():
        assert not line.startswith(("| reference_check |", "| independent_label |")), line


def test_without_the_labeler_there_is_no_second_labeling(world):
    run = run_evaluation(world, extra_verifiers=False)  # the reference checks (task.json) are still graded
    a = analyze(run, world / "tasks", allow_proposed=True, n_boot=50)
    assert "independent_labeling" not in a and "rule_independent_label" not in a["fresh_attempts"]
    assert all("independent_label" not in d for d in a["fresh_attempts"]["by_configuration_variant"].values())
    assert a["meta"]["label_support"]["results"] == {"reference_check": 18}
    assert list(a["conditions"]) == ["initial_plain", "full_plain"]
    assert "Independent labeler" not in (run / "analysis.md").read_text()


def test_another_label_support_verifier_is_kept_apart_and_is_not_the_labeler(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch)
    for t in TASKS:  # a second labeler under another id: label support by its condition, but not the second labeling
        make_task(tmp_path, t, sidecar={"independent_label2": VerifierCondition.reference_check})
    run = run_evaluation(tmp_path)
    a = analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50)
    assert a["meta"]["label_support"]["results"] == {"independent_label2": 18, "reference_check": 18}
    assert list(a["conditions"]) == ["initial_plain", "full_plain"] and "independent_labeling" not in a


@pytest.mark.parametrize("sidecar, message", [
    ({"independent_label": VerifierCondition.full_plain},
     "the label-support verifier independent_label is recorded under the evaluated condition 'full_plain'"),
    ({"independent_label": VerifierCondition.reference_check, "extra_c1": VerifierCondition.initial_plain},
     "verifiers extra_c1, initial_plain are all recorded under the evaluated condition 'initial_plain'"),
])
def test_a_verifier_that_would_be_scored_as_a_condition_is_refused(tmp_path, monkeypatch, sidecar, message):
    install(tmp_path, monkeypatch)
    for t in TASKS:
        make_task(tmp_path, t, sidecar=sidecar)
    run = run_evaluation(tmp_path)  # grading records it; the analysis refuses to score it
    with pytest.raises(ConditionConflict, match=message):
        analyze(run, tmp_path / "tasks", allow_proposed=True, n_boot=50)
    code = exit_code(["analyze", str(run), "--allow-proposed-labels", "--n-boot", "50"])
    assert isinstance(code, str) and code.startswith("analyze refused: T1: ") and message in code
    assert not (run / "analysis.json").exists() and not (run / "analysis.md").exists()  # nothing was written


def test_a_reference_check_recorded_under_an_evaluated_condition_is_refused(world):
    run = run_evaluation(world)
    path = run / "manifest.json"
    m = json.loads(path.read_text())
    m["tasks"][1]["verifiers"]["reference_check"]["condition"] = "full_audited"
    path.write_text(json.dumps(m))
    with pytest.raises(ConditionConflict, match="T2: the label-support verifier reference_check is recorded under the evaluated "
                                                "condition 'full_audited'"):
        analyze(run, world / "tasks", allow_proposed=True, n_boot=50)
    assert not (run / "analysis.json").exists()


def test_the_report_shows_the_second_labeling(analysed, tmp_path):
    run, _ = analysed
    html = build_report(run, tmp_path / "tasks", tmp_path, tmp_path / "report.html").read_text()
    for text in ("<h3>Independent labeler: a second labeling</h3>", "<h4>Agreement between D19 and the independent labeler</h4>",
                 "<h4>Solve rates under each labeling</h4>", "<b>Exploratory:</b>", "<th>FA, independent</th>",
                 "independent_label<br><span class='muted'>label support, not a condition</span>",
                 "reference_check<br><span class='muted'>label support, not a condition</span>"):
        assert text in html, text
    assert "initial_plain<br><span class='muted'>label support" not in html
    assert "Sensitivity analysis" not in html  # no sensitivity view in this run directory
