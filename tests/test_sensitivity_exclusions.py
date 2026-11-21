"""The sensitivity view of protocol v0.10 §18.1: ``tracecontract analyze <run> --sensitivity-exclusions FILE``.

* Each FILE (repeatable) is an audit report with an ``excluded`` list of attempt ids, or a JSON list of attempt ids.
* The main analysis is written as usual, byte for byte as without the flag; ``analysis_sensitivity.json`` and
  ``analysis_sensitivity.md`` recompute every table with those attempts excluded too, and say so first.
* A file that cannot be used is refused before anything is written; the report links the sensitivity view when the
  run directory holds it, and says when it was not computed with the current ``analysis.json``.

Synthetic fixtures only (tests/labeling_world.py), a stub grader instead of Docker; one test reads the format of the
recorded fresh-v1 audit reports, read only. These tests check code behaviour and are not research evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labeling_world import TASKS, attempt_id, exit_code, install, make_task, run_evaluation
from tracecontract.analysis import (
    PILOT_RULES, SENSITIVITY_JSON, SENSITIVITY_MD, SensitivityExclusionsError, analyze, read_sensitivity_exclusions,
)
from tracecontract.report import build_report
from tracecontract.schemas import Candidate
from tracecontract.store import load

REPO = Path(__file__).resolve().parents[1]
FRESH_V1 = REPO / "data" / "fresh" / "fresh-v1"


@pytest.fixture()
def run(tmp_path, monkeypatch) -> Path:
    install(tmp_path, monkeypatch)
    for t in TASKS:
        make_task(tmp_path, t)
    return run_evaluation(tmp_path)


def _files(root: Path) -> list[Path]:
    """An audit report for T2 (its automated audit flagged T2-fa-2, a false positive, and T2-fa-3, whose audit failed)
    and a plain list naming T1-fa-3 and an attempt of no task in the run."""
    report, extra = root / "audit_T2.json", root / "more" / "extra.json"
    report.write_text(json.dumps({"task_id": "T2", "excluded": [attempt_id("T2", "fa-2"), attempt_id("T2", "fa-3")],
                                  "manual_review": {"judged_false_positive": [attempt_id("T2", "fa-2")]}}))
    extra.parent.mkdir()
    extra.write_text(json.dumps([attempt_id("T1", "fa-3"), "fresh-v1-T9-fa-1"]))
    return [report, extra]


def _rates(a: dict, cond: str) -> tuple[int, int, int, int]:
    fa, fr = a["conditions"][cond]["false_acceptance"], a["conditions"][cond]["false_rejection"]
    return fa["num"], fa["den"], fr["num"], fr["den"]


def test_the_main_analysis_is_written_as_usual(run):
    tasks = run.parents[2] / "tasks"
    analyze(run, tasks, allow_proposed=True, n_boot=50)
    plain = {n: (run / n).read_bytes() for n in ("analysis.json", "analysis.md")}
    assert not (run / SENSITIVITY_JSON).exists() and not (run / SENSITIVITY_MD).exists()
    analyze(run, tasks, allow_proposed=True, n_boot=50, sensitivity_exclusions=_files(run.parents[2]))
    assert {n: (run / n).read_bytes() for n in plain} == plain  # the main analysis, byte for byte
    assert (run / SENSITIVITY_JSON).is_file() and (run / SENSITIVITY_MD).is_file()


def test_the_sensitivity_view_recomputes_every_table_with_the_listed_attempts_excluded(run):
    root = run.parents[2]
    main = analyze(run, root / "tasks", allow_proposed=True, n_boot=50, sensitivity_exclusions=_files(root))
    s = json.loads((run / SENSITIVITY_JSON).read_text())
    meta = s["meta"]["sensitivity"]
    assert [x["candidate_id"] for x in meta["excluded_here"]] == ["T1-fa-3", "T2-fa-2"]
    assert meta["excluded_here"][0] == {"task_id": "T1", "candidate_id": "T1-fa-3", "attempt_id": "fresh-v1-T1-fa-3"}
    assert [(x["candidate_id"], x["reason"]) for x in meta["already_excluded"]] == [
        ("T2-fa-3", "the fresh-attempt audit found a read of forbidden material")]
    assert meta["not_in_run"] == ["fresh-v1-T9-fa-1"]
    assert [(x["file"], x["kind"], len(x["ids"])) for x in meta["sources"]] == [
        ("audit_T2.json", "an audit report ('excluded' list)", 2), ("more/extra.json", "a JSON list of attempt ids", 2)]
    assert meta["primary_analysis"] == "analysis.json" and len(meta["primary_analysis_sha256"]) == 64
    # Recomputed with the two attempts excluded: the rates, the fresh attempts, the second labeling, the strata, the labels.
    assert (_rates(main, "initial_plain"), _rates(s, "initial_plain")) == ((5, 7, 0, 5), (4, 6, 0, 4))
    f = s["fresh_attempts"]
    assert (f["n_attempts"], f["n_excluded"]) == (6, 3)
    why = {x["candidate_id"]: x["reason"] for x in f["excluded"]}
    assert why["T2-fa-2"] == "sensitivity analysis only (protocol §18.1): listed in audit_T2.json"
    assert why["T1-fa-3"] == "sensitivity analysis only (protocol §18.1): listed in more/extra.json"
    assert s["independent_labeling"]["labels"] == {"valid": 4, "invalid": 5, "ambiguous": 3, "not_graded": 0}
    assert s["independent_labeling"]["agreement"]["by_stratum"]["fresh-v1"]["n_units"] == 5
    listed = {r["candidate"] for rs in s["per_task"]["T1"].values() for r in rs}
    assert "T1-fa-3" not in listed and "T1-fa-1" in listed
    assert [x["candidate"] for x in s["labels"]["T2"]["strata"]["fresh-v1"]["candidates"]] == ["T2-fa-1", "T2-fa-4"]
    assert s["by_stratum"]["fresh-v1"]["conditions"]["initial_plain"]["false_acceptance"]["den"] == 2
    assert s["meta"]["inputs"] == main["meta"]["inputs"]  # the same inputs; the files listed are hashed under sources
    md = (run / SENSITIVITY_MD).read_text()
    assert md.startswith("# Sensitivity analysis (proposed labels allowed (automated pilot))\n\n> **Sensitivity analysis, not the "
                         "primary analysis** (protocol §18.1). Every table below is recomputed with 2 more fresh attempt(s) excluded")
    assert "> Excluded here as well (2): T1-fa-3 (T1), T2-fa-2 (T2)." in md
    assert "> **Listed but not an attempt of this run** (1): fresh-v1-T9-fa-1." in md
    assert "Excluded from this sensitivity analysis (3):" in md
    assert "Sensitivity analysis" not in (run / "analysis.md").read_text()


def test_the_cli_writes_both_and_refuses_unusable_files_before_writing(run, capsys):
    root = run.parents[2]
    for name, content, message in (
            ("broken.json", "{not json", "broken.json: cannot be read as JSON"),
            ("object.json", json.dumps({"flagged": ["x"]}), "object.json: neither a JSON list of attempt ids nor an audit report"),
            ("numbers.json", json.dumps(["fresh-v1-T1-fa-1", 7]), "numbers.json: 1 listed entry is not an attempt id"),
            ("spaces.json", json.dumps({"excluded": ["two words"]}), "spaces.json: 1 listed entry is not an attempt id")):
        (root / name).write_text(content)
        code = exit_code(["analyze", str(run), "--allow-proposed-labels", "--n-boot", "50", "--sensitivity-exclusions", str(root / name)])
        assert isinstance(code, str) and code.startswith("analyze refused: ") and message in code, code
        with pytest.raises(SensitivityExclusionsError):
            read_sensitivity_exclusions([root / name], root)
    code = exit_code(["analyze", str(run), "--allow-proposed-labels", "--n-boot", "50", "--sensitivity-exclusions", str(root / "gone.json")])
    assert isinstance(code, str) and "gone.json: cannot be read as JSON" in code
    assert not any((run / n).exists() for n in ("analysis.json", "analysis.md", SENSITIVITY_JSON, SENSITIVITY_MD))
    capsys.readouterr()
    files = _files(root)
    argv = ["analyze", str(run), "--allow-proposed-labels", "--n-boot", "50"]
    assert exit_code(argv + [x for f in files for x in ("--sensitivity-exclusions", str(f))]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["sensitivity"] == {"analysis": str(run / SENSITIVITY_JSON), "markdown": str(run / SENSITIVITY_MD),
                                  "also_excluded": 2, "not_in_run": ["fresh-v1-T9-fa-1"]}
    assert exit_code(argv) == 0 and "sensitivity" not in json.loads(capsys.readouterr().out)


def test_the_report_links_the_sensitivity_view(run):
    root = run.parents[2]
    out = root / "site" / "report.html"
    analyze(run, root / "tasks", allow_proposed=True, n_boot=50)
    assert "Sensitivity analysis" not in build_report(run, root / "tasks", root, out).read_text()
    analyze(run, root / "tasks", allow_proposed=True, n_boot=50, sensitivity_exclusions=_files(root))
    html = build_report(run, root / "tasks", root, out).read_text()
    banner = html[html.index("<b>Sensitivity analysis</b>"):]
    banner = banner[:banner.index("</div>")]
    assert "It recomputes every table with 2 more fresh attempt(s) excluded: those listed in audit_T2.json, more/extra.json" in banner
    assert "1 listed id(s) name no attempt of this run" in banner
    assert "<a href='../results/runs/r/analysis_sensitivity.md'>" in banner and "../results/runs/r/analysis_sensitivity.json" in banner
    assert "not computed with the current analysis.json" not in banner
    # A later main analysis (here under other reporting rules) leaves the sensitivity view behind, and the report says so.
    analyze(run, root / "tasks", allow_proposed=True, n_boot=50, rules=PILOT_RULES)
    html = build_report(run, root / "tasks", root, run / "report.html").read_text()
    assert "<a href='analysis_sensitivity.md'>" in html  # the report beside the run: links relative to it
    assert "<b>It was not computed with the current analysis.json</b>" in html


@pytest.mark.skipif(not (FRESH_V1 / "audit_CS-01.json").is_file(), reason="the fresh-v1 audit reports are not in this checkout")
def test_the_recorded_fresh_v1_audit_reports_are_read_as_audit_reports():
    """Read only: the recorded reports' 'excluded' lists name attempt ids of the registered fresh-v1 candidates."""
    for task in ("CS-01", "CS-04"):
        path = FRESH_V1 / f"audit_{task}.json"
        report = json.loads(path.read_text())
        sources, reasons = read_sensitivity_exclusions([path], REPO)
        assert [(x["file"], x["kind"], x["ids"]) for x in sources] == [
            (f"data/fresh/fresh-v1/audit_{task}.json", "an audit report ('excluded' list)", report["excluded"])]
        assert report["excluded"] and set(reasons) == set(report["excluded"])
        stratum = REPO / "tasks" / task / "strata" / "fresh-v1"
        ids = {load(p, Candidate).attempt.attempt_id for p in sorted((stratum / "candidates").glob("*.json"))}
        assert set(report["excluded"]) <= ids  # every flagged attempt is a registered attempt, matched by its attempt id
