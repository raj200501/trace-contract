"""scripts/check_abstract.py: TeX markup removal, the character count and the exit status.

Synthetic TeX strings and temporary files, plus one check that the paper's abstract is within the limit.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_abstract.py"
spec = importlib.util.spec_from_file_location("check_abstract", SCRIPT)
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)


def test_markup_is_removed_and_paragraphs_are_kept():
    tex = ("\\documentclass{article}\n\\begin{abstract}\n% a comment line\n"
           "We ran \\emph{four} tasks (\\texttt{tc\\_x}, \\textbf{\\emph{nested}})~and 6--12 checks\\label{x}; % note\n"
           "``quoted'' 5\\% of \\S2 --- see\\ldots\n\nSecond paragraph with $J$.\n\\end{abstract}\nignored text\n")
    text, problems = ca.plain_text(tex)
    assert problems == []
    assert text == ('We ran four tasks (tc_x, nested) and 6\u201312 checks; "quoted" 5% of \u00a72 \u2014 see\u2026'
                    "\n\nSecond paragraph with J.")
    assert len(text) == len("We ran four tasks (tc_x, nested) and 6\u201312 checks; \"quoted\" 5% of \u00a72 \u2014 see\u2026") + 2 + len(
        "Second paragraph with J.")


def test_list_items_become_lines():
    text, problems = ca.plain_text("Fragile:\n\\begin{itemize}\n\\item one;\n\\item  two\n  lines.\n\\end{itemize}\nEnd.")
    assert problems == []
    assert text == "Fragile:\n\n- one;\n- two lines.\n\nEnd."


def test_citations_and_unknown_commands_are_problems():
    text, problems = ca.plain_text("\\begin{abstract}As shown \\cite{swechat} in \\S\\ref{sec:x}, \\foo{y} \\Section.\\end{abstract}")
    assert "no plain-text form: \\cite{swechat}" in problems and "no plain-text form: \\ref{sec:x}" in problems
    assert "unconverted command: \\foo" in problems and "unconverted command: \\Section" in problems
    assert "swechat" not in text and "sec:x" not in text


def test_exit_status_follows_the_limit(tmp_path, capsys):
    p = tmp_path / "abstract.tex"
    p.write_text("\\begin{abstract}\n" + "x" * 30 + "\n\\end{abstract}\n", encoding="utf-8")
    assert ca.main([str(p), "--limit", "30"]) == 0
    assert "30 characters without TeX markup (limit 30): OK" in capsys.readouterr().out
    assert ca.main([str(p), "--limit", "29"]) == 1
    assert "TOO LONG" in capsys.readouterr().out
    p.write_text("\\begin{abstract}short \\cite{a}\\end{abstract}", encoding="utf-8")
    assert ca.main([str(p)]) == 1
    assert "UNRELIABLE" in capsys.readouterr().out


def test_the_papers_abstract_is_within_the_limit():
    text, problems = ca.plain_text(ca.DEFAULT.read_text(encoding="utf-8"))
    assert problems == []
    assert 0 < len(text) <= ca.LIMIT
