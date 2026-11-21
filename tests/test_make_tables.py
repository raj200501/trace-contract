"""paper/make_tables.py: the arguments are checked first, and the outputs are replaced only after success.

The generator writes paper/generated/*.tex and paper/evidence_ledger.md. Every test points those
two outputs at a temporary directory (``GEN`` and ``LEDGER`` are monkeypatched), so a regression
can never delete or change the tracked tables. The tests read the recorded tasks and, in the last
one, the frozen pilot run and its comparison runs, read-only.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "paper" / "make_tables.py"
spec = importlib.util.spec_from_file_location("make_tables", SCRIPT)
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

# The command documented in README.md (Reproduce), without the interpreter.
README_ARGS = ["results/runs/pilot-v0.3.3", "--compare", "results/runs/pilot-v0.3.2", "results/runs/pilot-v0.3.1",
               "results/runs/pilot-v0.3", "results/runs/pilot-v0.2", "results/runs/pilot-v0.2-h2"]


def _tree(d: Path) -> dict[str, str]:
    """Every file under ``d`` (hidden ones included) with its sha256."""
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    """Stand-ins for paper/: a generated table, a stale one, an exploratory one, and the ledger."""
    paper = tmp_path / "paper"
    gen = paper / "generated"
    (gen / "exploratory").mkdir(parents=True)
    (gen / "results_summary.tex").write_text("table from an earlier invocation\n")
    (gen / "stale_table.tex").write_text("a table that no current input produces\n")
    (gen / "exploratory" / "per_family_table.tex").write_text("written by scripts/exploratory_reanalysis.py\n")
    (paper / "evidence_ledger.md").write_text("ledger from an earlier invocation\n")
    monkeypatch.setattr(mt, "GEN", gen)
    monkeypatch.setattr(mt, "LEDGER", paper / "evidence_ledger.md")
    return paper


def _unchanged(paper: Path, before: dict[str, str]) -> None:
    assert _tree(paper) == before
    assert not list(paper.glob(".make_tables-*")), "the temporary directory was left behind"


def test_help_writes_and_deletes_nothing(outputs, capsys):
    before = _tree(outputs)
    with pytest.raises(SystemExit) as e:
        mt.main(["--help"])
    assert e.value.code == 0
    assert "--compare" in capsys.readouterr().out
    _unchanged(outputs, before)


def test_bad_arguments_change_nothing(outputs, tmp_path):
    partial = tmp_path / "runs" / "partial"  # a run directory without analysis.json
    partial.mkdir(parents=True)
    (partial / "manifest.json").write_text('{"run_id": "partial"}\n')
    no_results = tmp_path / "runs" / "empty"  # a --compare directory without results.jsonl
    no_results.mkdir()
    before = _tree(outputs)
    for args in ([], [str(tmp_path / "runs" / "missing")], [str(partial)], [str(partial), "--compare", str(no_results)],
                 ["--compare", str(no_results)]):
        with pytest.raises(SystemExit) as e:
            mt.main(args)
        assert e.value.code == 2, args
        _unchanged(outputs, before)


def test_a_compare_directory_without_results_is_refused_before_anything_runs(outputs, tmp_path, capsys):
    run = tmp_path / "run"
    run.mkdir()
    (run / "analysis.json").write_text("{}\n")
    (run / "manifest.json").write_text('{"run_id": "run"}\n')
    before = _tree(outputs)
    with pytest.raises(SystemExit) as e:
        mt.main([str(run), "--compare", str(tmp_path / "mistyped")])
    assert e.value.code == 2
    assert "results.jsonl" in capsys.readouterr().err
    _unchanged(outputs, before)


def test_a_failure_while_generating_changes_nothing(outputs, tmp_path):
    run = tmp_path / "broken-run"
    run.mkdir()
    (run / "analysis.json").write_text("{}\n")  # no "meta": the run's tables fail after the task tables were written
    (run / "manifest.json").write_text('{"run_id": "broken-run"}\n')
    before = _tree(outputs)
    with pytest.raises(KeyError):
        mt.main([str(run)])
    _unchanged(outputs, before)


def test_the_readme_command_reproduces_the_tracked_tables(outputs, monkeypatch):
    tasks = sorted(p.parent.name for p in (ROOT / "tasks").glob("*/task.json"))
    if tasks != ["CS-01", "CS-02", "CS-03", "CS-04"]:
        pytest.skip("the tables cover every task directory; with tasks beyond the pilot's four they differ from the tracked ones")
    monkeypatch.chdir(ROOT)  # the documented command uses paths relative to the repository root
    mt.main(README_ARGS)
    tracked = ROOT / "paper" / "generated"
    names = sorted(p.name for p in tracked.glob("*.tex"))
    assert sorted(p.name for p in mt.GEN.glob("*.tex")) == names  # the stale table is gone, every table is there
    for name in names:
        assert (mt.GEN / name).read_bytes() == (tracked / name).read_bytes(), name
    assert mt.LEDGER.read_bytes() == (ROOT / "paper" / "evidence_ledger.md").read_bytes()
    assert (mt.GEN / "exploratory" / "per_family_table.tex").read_text() == "written by scripts/exploratory_reanalysis.py\n"
    assert not list(outputs.glob(".make_tables-*"))
