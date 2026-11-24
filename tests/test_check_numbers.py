"""paper/check_numbers.py: every digit and count word outside a number macro is reported, with the plan's narrow
exemptions (restructure plan, part 8), and every number macro whose key no generated numbers.tex defines.

Synthetic TeX strings and temporary files, plus the manuscript's own files: the natural section's template, which holds
no literal number, and every section main.tex inputs, the main text and the appendices alike. The draft's earlier
sections were retired once the move-map check had passed (restructure plan, part 3), and none is left.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_numbers", ROOT / "paper" / "check_numbers.py")
cn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cn)

# The draft's sections as they stood before the restructure (restructure plan, part 3): main.tex inputs none of them
# any more, and the move-map check retired their files.
RETIRED = {"data.tex", "method.tex", "protocol.tex", "results.tex", "results_fresh.tex", "results_natural.tex",
           "results_pilot.tex", "analysis.tex", "limitations.tex", "appendix.tex"}
# The main text in the plan's order (part 2), each section clean.
MAIN_TEXT = ("abstract.tex", "introduction.tex", "design.tex", "results_controlled.tex", "pilot.tex", "natural.tex",
             "related.tex", "discussion.tex", "threats.tex", "ethics.tex", "reproducibility.tex")
# The appendices in the plan's order (part 3: A to I), after the main text.
APPENDICES = ("app_protocol.tex", "app_deviations.tex", "app_grading.tex", "app_construction.tex", "app_fresh.tex",
              "app_pilot.tex", "app_natural.tex", "app_natural_cases.tex", "app_annotation.tex", "app_provenance.tex")


def kinds(tex: str, numbers=None) -> list[tuple[str, str]]:
    return [(f.kind, f.token) for f in cn.findings(tex, "x.tex", numbers)]


def test_digits_and_count_words_outside_macros_are_reported_with_their_lines():
    tex = "First line.\nC1 accepts 24 of the \\fv{cv.n} violators,\nand four families.\n% 99 in a comment\nHalf of them, 0.5\\%.\n"
    out = cn.findings(tex, "x.tex")
    assert [(f.line, f.kind, f.token) for f in out] == [(2, "digit", "24"), (3, "count word", "four"),
                                                         (5, "count word", "Half"), (5, "digit", "0.5")]
    assert str(out[0]) == "x.tex:2: digit: 24"


def test_dates_and_times_in_prose_are_not_exempt():
    assert [t for _, t in kinds("hashed on 2026-11-21 at 08:30:39 UTC")] == ["2026", "11", "21", "08", "30", "39"]


@pytest.mark.parametrize("tex", [
    "CS-01, CS-04, NP-03, NP-20 and FX-12",  # task families
    "C1 to C4, B1--B3, U1 and U2, $U_1$, $U_{2}$, \\texttt{u1} and u1+u2",  # conditions, turns and variants
    "stages S1--S8a, S8a', S9x and S11; phases P0 to P7; F0--F8",  # stages and phases
    "D19, D28--D31 and D64, decision~17, deviation~3 and estimand 3",  # decision-log entries and numbered items
    "R1, R15 and R-zero-step",  # requirement ids
    "CS-01-fresh-A-u1-1, CS-02-pre-correction, eval-alt-1 and eval-nm-3",  # candidate and attempt ids
    "pilot-v0.3.3, fresh-v1, natural-pr-v2, pilot-v0.2-h2 and pilot-v0.3.5-regrade",  # run ids
    "alt_v1-natural and refcontract_v1",  # template ids
    "protocol~\\S15.4, \\S\\ref{sec:intro}, \\S 20.3 and v0.12, audit:v1, harness 0.3.5.",  # sections and versions
    "its sha256 and SHA-256",  # the hash function's name
    "under MIT, Apache-2.0 or BSD; AIDev is CC-BY-4.0; a Python~3.12 environment",  # licence ids and Python versions
    "\\ref{tab:x1}, \\label{sec:2}, \\cite{wang2025are}, \\citep[p.~3]{a1}, \\input{generated/x2}",  # name arguments
    "\\IfFileExists{generated/fresh/numbers.tex}{\\input{generated/fresh/numbers.tex}}{}",
    "\\begin{tabular}{@{}p{0.14\\linewidth}rr@{}}\\multicolumn{2}{c}{x} \\cmidrule(lr){2-3}\\\\[4pt]",  # specs, lengths
    "\\setlength{\\tabcolsep}{4pt}\\hspace{0pt}\\vspace{-2pt}",
    "\\texttt{paper/make\\_tables.py}, \\texttt{e9c9c91}, \\texttt{tc-harness/0.3.5}",  # file names and hashes
    "\\texttt{make\\_tables.py -{}-natural-run results/runs/natural-pr-v1}",
    "one model family of one\nprovider; one-sided and two-sided p; one- and two-sided floors",  # the allowed phrases
    "the first request, the second labeling and the third duplicate",  # ordinals hold no count word
    "single-pass generation and single-turn tasks",  # kinds of generation and of task
    "once building had stopped; Once human labels exist; merging once every task has its reviews",  # "once" as a conjunction
    "each distinct graded patch counts once; each distinct graded patch once",  # the counting rule of protocol \u00a715.7
    "every pair, per pair, an unresolved pair, the run's pairs and Pairs of the run",  # a graded pair, a noun
    "\\providecommand{\\nrcaveat}[1]{#1} \\nrv{d19.np03.ambiguous} \\plv{c1.fa} \\dv{design.k} \\nat{s11.first}",
])
def test_the_exemptions_report_nothing(tex):
    assert kinds(tex) == []


def test_numbers_near_the_exemptions_are_still_reported():
    assert kinds("C1 accepts 6 of 17") == [("digit", "6"), ("digit", "17")]
    assert kinds("the 12 checks of D19") == [("digit", "12")]
    assert kinds("harness 0.3 and 0.125") == [("digit", "0.3"), ("digit", "0.125")]  # two parts: a value, not a version
    assert kinds("\\texttt{rejects 3 of 4}") == [("digit", "3"), ("digit", "4")]  # \texttt with words is text
    assert kinds("$2^4=16$ sign assignments") == [("digit", "2"), ("digit", "4"), ("digit", "16")]
    assert kinds("a 3 in gap") == [("digit", "3")]  # a length needs its unit next to the number
    assert kinds("one model family") == [("count word", "one")]  # only the whole phrase is allowed
    assert kinds("twenty-one and a dozen") == [("count word", "twenty"), ("count word", "one"), ("count word", "dozen")]
    # Counts written as other words or as a phrase, which a review found slipping past the word list.
    assert kinds("Its single revision there; a single run") == [("count word", "single"), ("count word", "single")]
    assert kinds("counted twice, run thrice, graded once more") == [("count word", "twice"), ("count word", "thrice"),
                                                                     ("count word", "once")]
    assert kinds("the zeros of C3 and C4; Zeroes") == [("count word", "zeros"), ("count word", "Zeroes")]
    assert kinds("by a pair of model mappers, a frozen pair\nof verifiers") == [("count word", "a pair of"),
                                                                              ("count word", "a frozen pair of")]
    assert [f.line for f in cn.findings("x\nby a pair\nof reviewers", "x.tex")] == [2]  # the line a phrase starts on


def test_a_macro_whose_key_is_not_generated_is_reported():
    numbers = {"fv": {"cv.n": "27"}, "nat": {}, "nrv": {}, "plv": {}, "dv": {}}
    out = kinds("\\fv{cv.n} and \\fv{cv.missing}; \\dv{design.k}\n% \\fv{commented.out}", numbers)
    assert out == [("missing key", "\\fv{cv.missing}"), ("missing key", "\\dv{design.k}")]
    assert kinds("\\fv{cv.missing}") == []  # without the generated numbers, keys are not checked


def test_load_numbers_reads_every_namespace(tmp_path):
    (tmp_path / "fresh").mkdir()
    (tmp_path / "fresh" / "numbers.tex").write_text(
        "% header\n\\expandafter\\gdef\\csname fv:cv.n\\endcsname{27}\n\\expandafter\\gdef\\csname fv:c3.fa\\endcsname{2/29}\n")
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "numbers.tex").write_text("\\expandafter\\gdef\\csname dv:design.k\\endcsname{5}\n")
    got = cn.load_numbers(tmp_path)
    assert got == {"fv": {"cv.n": "27", "c3.fa": "2/29"}, "nat": {}, "nrv": {}, "plv": {}, "dv": {"design.k": "5"}}


def test_main_tex_is_read_from_its_title_and_body_only(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text("\\documentclass[11pt]{article}\n\\usepackage[margin=1in]{geometry}\n\\usepackage[maxbibnames=6]{biblatex}\n"
                    "\\title{A Title With 2 Numbers}\n\\begin{document}\nBody with 3.\n\\input{sections/a}\n\\end{document}\n")
    (tmp_path / "sections").mkdir()
    (tmp_path / "sections" / "a.tex").write_text("Section text with seven words.\n\\input{sections/b}\n")
    (tmp_path / "sections" / "b.tex").write_text("Nested 8.\n")
    assert [p.name for p in cn.manuscript_files(main)] == ["a.tex", "b.tex"]
    out = cn.check([main, *cn.manuscript_files(main)], {ns: {} for ns in cn.NAMESPACES}, main=main)
    assert [(Path(f.file).name, f.line, f.token) for f in out] == [("main.tex", 4, "2"), ("main.tex", 6, "3"),
                                                                    ("a.tex", 1, "seven"), ("b.tex", 1, "8")]


def test_the_exit_status_follows_the_findings(tmp_path, capsys):
    clean, dirty = tmp_path / "clean.tex", tmp_path / "dirty.tex"
    clean.write_text("C3 accepts \\fv{cv.c3} of the violators.\n")
    dirty.write_text("C3 accepts 0 of the violators.\n")
    gen = tmp_path / "generated"
    (gen / "fresh").mkdir(parents=True)
    (gen / "fresh" / "numbers.tex").write_text("\\expandafter\\gdef\\csname fv:cv.c3\\endcsname{0/27}\n")
    assert cn.main([str(clean), "--generated", str(gen)]) == 0
    assert "OK" in capsys.readouterr().err
    assert cn.main([str(dirty), "--generated", str(gen)]) == 1
    assert "dirty.tex:1: digit: 0" in capsys.readouterr().out
    assert cn.main([str(clean), "--generated", str(tmp_path / "none")]) == 1  # the key is generated nowhere
    assert "missing key: \\fv{cv.c3}" in capsys.readouterr().out


def test_the_natural_template_holds_no_literal_number_and_every_key_is_generated():
    # the template and its part in Appendix G, which App. G inputs (decision log D80)
    out = cn.check([ROOT / "paper" / "sections" / n for n in ("natural.tex", "app_natural_cases.tex")], cn.load_numbers())
    assert out == [], [str(f) for f in out]


def test_every_section_main_tex_inputs_is_clean():
    files = cn.manuscript_files()
    out = cn.check([cn.MAIN, *files], cn.load_numbers())  # main.tex's own title and body included
    assert out == [], [str(f) for f in out]


def test_the_retired_sections_are_gone():
    names = {p.name for p in cn.manuscript_files()}
    assert not RETIRED & names, sorted(RETIRED & names)
    assert not [n for n in RETIRED if (ROOT / "paper" / "sections" / n).exists()]


def test_the_main_text_comes_first_and_the_appendices_follow_in_the_plan_s_order():
    names = [p.name for p in cn.manuscript_files()]
    assert tuple(names) == MAIN_TEXT + APPENDICES, names
