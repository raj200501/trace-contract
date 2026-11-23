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


NUMBERS = {"fv": {"cv.n": "27", "cmp.c1-c3.fa.diff": "\\ensuremath{+}0.76", "run.pairs": "1{,}672", "cv.share": "67.5\\%",
                  "excluded.1": "CS-02-fresh-A-final-1"},
           "nat": {"s9.first.comments": "150"}, "nrv": {"families": "6"}, "plv": {"c1.fa": "6/17"}, "dv": {"design.k": "5"}}


def test_number_macros_are_expanded_from_the_generated_numbers():
    tex = ("\\begin{abstract}\\fv{cv.n} violators; difference \\fv{cmp.c1-c3.fa.diff}; \\fv{run.pairs} pairs; \\fv{cv.share}; "
           "\\nat{s9.first.comments}, \\nrv{families}, \\plv{c1.fa}, $k=\\dv{design.k}$; \\texttt{\\fv{excluded.1}}.\\end{abstract}")
    text, problems = ca.plain_text(tex, NUMBERS)
    assert problems == []
    assert text == "27 violators; difference +0.76; 1,672 pairs; 67.5%; 150, 6, 6/17, k=5; CS-02-fresh-A-final-1."


def test_a_number_key_that_is_not_generated_is_a_problem(tmp_path, capsys):
    text, problems = ca.plain_text("\\begin{abstract}We ran \\fv{attempts} attempts.\\end{abstract}", NUMBERS)
    assert problems == ["missing number key: \\fv{attempts}"] and text == "We ran attempts."
    p = tmp_path / "abstract.tex"
    p.write_text("\\begin{abstract}\nWe test \\fv{families} tasks.\n\\end{abstract}\n", encoding="utf-8")
    gen = tmp_path / "generated"
    (gen / "fresh").mkdir(parents=True)
    (gen / "fresh" / "numbers.tex").write_text("\\expandafter\\gdef\\csname fv:families\\endcsname{4}\n", encoding="utf-8")
    assert ca.main([str(p), "--generated", str(gen), "--print"]) == 0  # read from the generated files
    out = capsys.readouterr().out
    assert "We test 4 tasks." in out and "16 characters without TeX markup" in out
    assert ca.main([str(p), "--generated", str(tmp_path / "none")]) == 1  # generated nowhere: the count is unreliable
    assert "UNRELIABLE" in capsys.readouterr().out


def test_the_papers_abstract_expands_with_the_committed_numbers():
    """Whatever macros the paper's abstract uses are generated, so the gate counts the text as it prints."""
    text, problems = ca.plain_text(ca.DEFAULT.read_text(encoding="utf-8"), ca.check_numbers.load_numbers(ca.GENERATED))
    assert problems == [] and "\\" not in text and "UNFILLED" not in text
