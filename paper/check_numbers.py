"""Report every number in the manuscript's text that is not a generated number macro (restructure plan, part 8).

Usage: python paper/check_numbers.py [FILE.tex ...] [--generated DIR]

Default: main.tex's title and body and every section file that main.tex inputs (``\\input{sections/...}``); the
generated tables and figures are not read, since make_tables.py and make_figures.py write every number in them from a
record and list it in their ledgers. Reported, one line each (``file:line: kind: token``):

* a digit outside a number macro (``\\fv``, ``\\nat``, ``\\nrv``, ``\\plv``, ``\\dv``) and outside the exemptions below;
  dates and times in prose are not exempt;
* a count written as a word (zero to twenty, thirty to ninety by tens, hundred, half, dozen; zeros and zeroes; single,
  once, twice and thrice; "a pair of", across line breaks too) outside the allowlist (:data:`ALLOWED_PHRASES`);
* a number macro whose key no generated ``numbers.tex`` defines (it would print UNFILLED).

Exempt, and nothing else (the plan's narrow list): identifiers (task families CS-0n, NP-nn, FX-nn; conditions C1-C4 and
B1-B3; turns U1, U2 and the variants u1, u1+u2; stages S1-S11 with their primed and lettered forms; phases P0-P7; F0-F8;
decision-log entries D<n>; requirement ids R<n> and R-<name>; candidate, attempt, run and template ids; D64's numbered
decisions and protocol estimands; the names sha256, Apache-2.0, CC-BY-4.0 and their kin); protocol section numbers
(``\\S15.4``) and version names (v0.12, harness 0.3.5, Python 3.12); the arguments of
``\\ref``, ``\\label``, ``\\cite``, ``\\input`` and their kin; LaTeX lengths and column specifications; file names, paths
and revision hashes in ``\\texttt``; and the phrases of :data:`ALLOWED_PHRASES` (ordinals such as "first request" and
"second labeling" hold no count word; "single-pass" and "single-turn" name kinds of generation and of task; "once" as a
conjunction, and the counting rule "each distinct graded patch counts once"; "pair" as the noun of a graded
verifier-candidate pair, as in "every pair"). Comments are not read. Exit status 1 if anything is reported.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

PAPER = Path(__file__).resolve().parent
GENERATED = PAPER / "generated"
MAIN = PAPER / "main.tex"
# Number macro -> the subdirectory of paper/generated/ whose numbers.tex defines its keys (make_tables.py's modes).
NAMESPACES = {"fv": "fresh", "nat": "natural", "nrv": "natural_run", "plv": "pilot", "dv": "design"}
COUNT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
               "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
               "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "half", "dozen",
               # counts written as other words: "its single revision", "counted twice", "the zeros of C3 and C4"
               "zeros", "zeroes", "single", "once", "twice", "thrice")
# Counts written as phrases, matched across line breaks: "a pair of reviewers" (or "a frozen pair of verifiers") is two.
COUNT_PHRASES = (r"\ba\s+(?:[A-Za-z-]+\s+)?pair\s+of\b",)
# Phrases whose count words are names, not counts: the configurations' model statement (protocol §15.4), the sides of a
# test, the kinds of generation and of task ("single-pass", "single-turn"), "once" as a conjunction ("once building had
# stopped", "once every task has its reviews") and the counting rule of protocol §15.7 ("each distinct graded patch counts
# once"). Matched across line breaks and in any letter case.
ALLOWED_PHRASES = (r"one\s+model\s+family\s+of\s+one\s+provider", r"\b(?:one|two)-sided\b",
                   r"\b(?:one|two)-(?=\s*(?:and|or)\s+(?:one|two)-sided\b)", r"\bsingle-(?:pass|turn)\b",
                   r"\bonce(?=\s+(?:every|each|all|building|human|the|it|its|they|we|that|this|a|an)\b)",
                   r"\b(?:counts?|counted|patch)\s+once\b")

_MACRO = re.compile(r"\\(" + "|".join(NAMESPACES) + r")\{([^{}]*)\}")
_DEF = re.compile(r"^\\expandafter\\gdef\\csname ([a-z]+):([^\\]+)\\endcsname\{(.*)\}$", re.MULTILINE)
_COMMENT = re.compile(r"(?<!\\)%.*")
# Commands whose arguments are names, not numbers: removed with their optional and first mandatory argument.
_NAME_ARGS = re.compile(r"\\(?:ref|eqref|pageref|autoref|cref|Cref|nameref|label|cite[a-z]*|textcite|parencite|input|include|"
                        r"includegraphics|IfFileExists|url|href|hyperref|usepackage|documentclass|addbibresource|bibliography|"
                        r"begin|end)\*?(?:\[[^\]]*\])*\{[^{}]*\}")
_DEFINITION = re.compile(r"\\(?:new|renew|provide)command\*?\{\\[A-Za-z@]+\}(?:\[\d\])?(?:\[[^\]]*\])?|#\d")
_TABULAR = re.compile(r"\\begin\{(?:tabular\*?|tabularx|longtable|array)\}(?:\{[^{}]*\})?")
_SPANS = re.compile(r"\\multicolumn\{\d+\}\{[^{}]*\}|\\cmidrule(?:\([^)]*\))?\{[\d\-]+\}|\\cline\{[\d\-]+\}|"
                    r"\\setcounter\{[^{}]*\}\{\d+\}|\\renewcommand\{\\arraystretch\}\{[^{}]*\}")
_LENGTH = re.compile(r"-?\d*\.?\d+(?:pt|em|ex|in|cm|mm|bp|sp|pc|dd|cc)(?![A-Za-z])|"
                     r"-?\d*\.?\d+\s*\\(?:linewidth|textwidth|columnwidth|hsize|textheight|baselineskip)(?![A-Za-z])")
IDENTIFIERS = (
    r"\b(?:CS|NP|FX)-\d+(?:-[A-Za-z0-9_+]+)*",  # task families and the ids that start with them (CS-01-fresh-A-u1-1)
    r"\b(?:eval|dev)-[A-Za-z0-9_\-]*\d[A-Za-z0-9_\-]*",  # candidate ids of a pool (eval-alt-1, eval-nm-3)
    r"\b[BCDFPRSU]\d+[a-z]?(?:\$?'\$?)*(?![A-Za-z0-9])",  # C1, B3, D19, F8, P4, R15, S8a', S9x, U2
    r"\bR-[A-Za-z]+(?:-[A-Za-z]+)*",  # requirement ids (R-zero-step)
    r"\b[BCSU]_\{?\d+\}?",  # math forms U_1, U_{2}
    r"\bu\d+(?:\+u\d+)*\b",  # instruction variants u1, u1+u2
    r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*-v\d+(?:\.\d+)*(?:-[a-z0-9]+)*\b",  # run and stratum ids (pilot-v0.3.3, fresh-v1)
    r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*_v\d+(?:-[a-z0-9]+)*\b",  # template ids (alt_v1-natural)
    r"\b(?:audit:)?v\d+(?:\.\d+)*\b",  # version names (v0.12, audit:v1)
    r"(?<![\d.])\d+\.\d+\.\d+(?!\d|\.\d)",  # dotted version triples (harness 0.3.5), a sentence's full stop after it
    r"(?:\\S|§)(?:\s|~)*\d+(?:\.\d+)*[a-z]?",  # protocol sections (\S15.4)
    r"\b(?:sha|SHA)-?256\b",  # the hash function's name
    r"\b(?:Apache|CC-BY(?:-SA|-NC|-ND)*|L?GPL|AGPL|MPL|EPL)-\d+(?:\.\d+)*\b",  # licence identifiers (Apache-2.0, CC-BY-4.0)
    r"\bPython(?:~|\s)+\d+(?:\.\d+)+",  # Python versions (Python 3.12)
    r"\b(?:decision|deviation|estimand)s?(?:~|\s)+\d+\b",  # D64's numbered decisions; protocol estimands
)
_IDENTIFIER = re.compile("|".join(IDENTIFIERS))
_ALLOWED = re.compile("|".join(ALLOWED_PHRASES), re.IGNORECASE)
_DIGITS = re.compile(r"\d+(?:[.,]\d+)*")
_WORDS = re.compile(r"\b(?:" + "|".join(COUNT_WORDS) + r")\b", re.IGNORECASE)
_PHRASES = re.compile("|".join(COUNT_PHRASES), re.IGNORECASE)
_HEX = re.compile(r"[0-9a-f]{7,64}")


class Finding(NamedTuple):
    file: str
    line: int
    kind: str  # "digit", "count word" or "missing key"
    token: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.kind}: {self.token}"


def load_numbers(generated: Path = GENERATED) -> dict[str, dict[str, str]]:
    """``{namespace: {key: value}}`` of every generated numbers.tex (a namespace whose file does not exist is empty)."""
    out: dict[str, dict[str, str]] = {}
    for ns, sub in NAMESPACES.items():
        p = generated / sub / "numbers.tex"
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        out[ns] = {k: v for prefix, k, v in _DEF.findall(text) if prefix == ns}
    return out


def _blank(m: re.Match) -> str:
    """A removed span: one space, and the span's line breaks, so that line numbers stay right."""
    return " " + "\n" * m.group(0).count("\n")


def _balanced(text: str, start: int) -> int:
    """The index just past the brace group that opens at ``text[start]`` (``{``), or -1 if it is not closed."""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "\\":
            continue
        if c == "{" and (i == 0 or text[i - 1] != "\\"):
            depth += 1
        elif c == "}" and text[i - 1] != "\\":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _strip_group_after(text: str, pattern: re.Pattern, keep) -> str:
    """For each match of ``pattern`` that is followed by a brace group, replace the group by ``keep(group text)``
    (line breaks are kept)."""
    out, pos = [], 0
    for m in pattern.finditer(text):
        if m.start() < pos:
            continue
        j = m.end()
        if j >= len(text) or text[j] != "{":
            continue
        end = _balanced(text, j)
        if end < 0:
            continue
        out.append(text[pos:m.start()])
        out.append(keep(text[m.start():j], text[j + 1:end - 1]))
        pos = end
    out.append(text[pos:])
    return "".join(out)


def _texttt(cmd: str, content: str) -> str:
    """\\texttt: file names, paths, revision hashes and other single tokens are names; a token of a longer content is
    removed when it holds a dot, a slash, an underscore or is a hash."""
    flat = content.replace("\\_", "_").replace("{}", "")
    if not flat.split() or len(flat.split()) == 1:
        return " " + "\n" * content.count("\n")
    kept = [t for t in re.split(r"(\s+)", content) if not re.search(r"[./_]", t.replace("\\_", "_")) and not _HEX.fullmatch(t)]
    return " " + "".join(kept)


def reduce(tex: str) -> str:
    """``tex`` with comments, number macros and every exempt span removed (line breaks kept): what is left of it can hold
    a number only where one is written out."""
    text = "\n".join(_COMMENT.sub("", line) for line in tex.splitlines())
    text = _MACRO.sub(_blank, text)
    text = _NAME_ARGS.sub(_blank, text)
    text = _DEFINITION.sub(_blank, text)
    text = _strip_group_after(text, _TABULAR, lambda cmd, spec: " " + "\n" * spec.count("\n"))
    text = _SPANS.sub(_blank, text)
    text = _strip_group_after(text, re.compile(r"\\texttt"), _texttt)
    text = _LENGTH.sub(_blank, text)
    text = _IDENTIFIER.sub(_blank, text)
    return _ALLOWED.sub(_blank, text)


def findings(tex: str, name: str, numbers: dict[str, dict[str, str]] | None = None) -> list[Finding]:
    """Every literal number and count word of ``tex`` outside the exemptions, and (with ``numbers``, as
    :func:`load_numbers` returns them) every number macro whose key is not generated."""
    out: list[tuple[int, int, int, Finding]] = []  # (line, pass, position in the line, finding): in reading order
    text = reduce(tex)
    for i, line in enumerate(text.splitlines(), 1):
        out += [(i, 0, m.start(), Finding(name, i, "digit", m.group(0))) for m in _DIGITS.finditer(line)]
        out += [(i, 0, m.start(), Finding(name, i, "count word", m.group(0))) for m in _WORDS.finditer(line)]
    for m in _PHRASES.finditer(text):  # a phrase may run over a line break; it is reported on the line it starts on
        i = text.count("\n", 0, m.start()) + 1
        out.append((i, 0, m.start() - (text.rfind("\n", 0, m.start()) + 1), Finding(name, i, "count word", " ".join(m.group(0).split()))))
    if numbers is not None:
        plain = "\n".join(_COMMENT.sub("", line) for line in tex.splitlines())
        for i, line in enumerate(plain.splitlines(), 1):
            for m in _MACRO.finditer(line):
                if m.group(2) not in numbers.get(m.group(1), {}):
                    out.append((i, 1, m.start(), Finding(name, i, "missing key", f"\\{m.group(1)}{{{m.group(2)}}}")))
    return [f for *_, f in sorted(out, key=lambda x: x[:3])]


def main_tex_text(tex: str) -> str:
    """The parts of main.tex that print as text: the title and the document body (the preamble's options and lengths
    are configuration). Lines outside them are kept blank, so line numbers stay main.tex's."""
    lines = tex.splitlines()
    keep = [""] * len(lines)
    body = False
    for i, line in enumerate(lines):
        if line.startswith(("\\title{", "\\author{")):
            keep[i] = line
        if line.startswith("\\begin{document}"):
            body = True
        if body:
            keep[i] = line
        if line.startswith("\\end{document}"):
            body = False
    return "\n".join(keep)


def manuscript_files(main: Path = MAIN) -> list[Path]:
    """The section files main.tex inputs (``\\input{sections/<name>}``), and those they input in turn, in reading order."""
    out: list[Path] = []

    def visit(p: Path) -> None:
        tex = "\n".join(_COMMENT.sub("", line) for line in p.read_text(encoding="utf-8").splitlines())
        for n in re.findall(r"\\input\{(sections/[^{}]+?)(?:\.tex)?\}", tex):
            q = main.parent / f"{n}.tex"
            if q not in out and q.is_file():
                out.append(q)
                visit(q)

    visit(main)
    return out


def check(files: list[Path], numbers: dict[str, dict[str, str]], main: Path = MAIN) -> list[Finding]:
    out = []
    for p in files:
        tex = p.read_text(encoding="utf-8")
        if p.resolve() == main.resolve():
            tex = main_tex_text(tex)
        try:
            name = str(p.resolve().relative_to(PAPER.parent))
        except ValueError:
            name = str(p)
        out += findings(tex, name, numbers)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="paper/check_numbers.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="*", type=Path, help="TeX files (default: main.tex and the sections it inputs)")
    ap.add_argument("--generated", type=Path, default=GENERATED, help="the directory of the generated numbers.tex files")
    a = ap.parse_args(argv)
    files = a.files or [MAIN, *manuscript_files()]
    out = check(files, load_numbers(a.generated))
    for f in out:
        print(f)
    by_kind = {k: sum(f.kind == k for f in out) for k in ("digit", "count word", "missing key")}
    print(f"check_numbers: {len(files)} file(s); " + ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in by_kind.items())
          + ("" if out else "; OK"), file=sys.stderr)
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
