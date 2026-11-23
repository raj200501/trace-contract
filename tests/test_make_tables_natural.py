"""paper/make_tables.py --natural: the natural arm's screening tables (the funnel, S10 and the Trace Commons screen).

The S9 extension has no S10 outcome: its S10 step was stopped at a usage limit, and its families are to be built again
for natural-pr-v2 (decision log D66, D75; protocol §20.2). The tables state that instead of printing a pending marker, so
the posted PDF holds no UNFILLED text; the numbers and the first sample's cells do not change.

The committed screening records under data/manifests/ are read, never written: the generator's outputs (``GEN``,
``LEDGER``) point at a temporary directory.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_tables_natural_screening", ROOT / "paper" / "make_tables.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)


@pytest.fixture(scope="module")
def made(tmp_path_factory) -> Path:
    paper = tmp_path_factory.mktemp("natural") / "paper"
    (paper / "generated").mkdir(parents=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mt, "GEN", paper / "generated")
        mp.setattr(mt, "LEDGER", paper / "evidence_ledger.md")
        mt.main(["--natural"])
    return paper / "generated" / "natural"


def test_no_table_prints_a_pending_or_unfilled_marker(made):
    for f in sorted(made.glob("*.tex")):  # numbers.tex names the lookup, which can print the marker, in a comment only
        text = "\n".join(ln for ln in f.read_text().splitlines() if not ln.startswith("%"))
        assert "\\unfilled" not in text and "pending" not in text, f.name


def test_the_extension_s_s10_is_stated_as_not_run(made):
    funnel = (made / "natural_funnel.tex").read_text()
    assert re.search(r"^S10 processed / passed / rejected & \d+ / \d+ / \d+ & not run \\\\$", funnel, re.MULTILINE)
    assert re.search(r"^S11 accepted for building & \d+ & -- \\\\$", funnel, re.MULTILINE)
    assert "so its S10 and S11 were not run (decision log D66, D75)" in " ".join(funnel.split())
    s10 = " ".join((made / "natural_s10.tex").read_text().split())
    assert "have no S10 outcome, not run: the extension's S10 step was stopped at a usage limit" in s10
    assert "\\texttt{natural-pr-v2} (decision log D66, D75; protocol \\S20.2)" in s10


def test_the_numbers_are_those_the_paper_uses(made):
    assert (made / "numbers.tex").read_text() == (ROOT / "paper" / "generated" / "natural" / "numbers.tex").read_text()
