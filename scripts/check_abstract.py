"""Check the length of the paper's abstract as plain text (TeX markup removed).

Usage: .venv/bin/python scripts/check_abstract.py [paper/sections/abstract.tex] [--limit 1900] [--print]

The text between ``\\begin{abstract}`` and ``\\end{abstract}`` (the whole file if there is no such
environment) is reduced to what would be pasted into a plain-text abstract field:

* comments are dropped; formatting commands (``\\emph``, ``\\textbf``, ``\\texttt``, ...) keep their
  argument, and ``\\label`` is dropped;
* ``~``, ``\\,`` and ``\\ `` become spaces; ``\\%``, ``\\&``, ``\\_``, ``\\#`` and ``\\$`` their
  character; ``\\S`` the section sign; ``\\ldots`` and ``\\dots`` an ellipsis; ``---`` and ``--``
  dashes; two backquotes and two apostrophes a double quote; ``$...$`` keeps its content;
* each list item becomes a line that starts with ``- ``;
* whitespace inside a paragraph collapses to one space, and paragraphs are joined by a blank line,
  which counts as two characters.

Citations, references and every other command are reported as problems, since they have no
plain-text form, and the count is then not reliable. One summary line goes to stdout, problems to
stderr. Exit status 1 if the text is longer than ``--limit`` characters or a problem was found.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT = REPO / "paper" / "sections" / "abstract.tex"
LIMIT = 1900
KEEP_ARGUMENT = ("emph", "textbf", "textit", "texttt", "textsc", "textrm", "textsf", "textup", "mbox", "text", "url")
DROP_WITH_ARGUMENT = ("label",)
NO_PLAIN_FORM = ("cite", "ref", "eqref", "autoref", "cref", "Cref", "footnote")
ESCAPES = {r"\%": "%", r"\&": "&", r"\_": "_", r"\#": "#", r"\$": "$", r"\,": " ", "\\ ": " ", r"\@": ""}
WORD_SYMBOLS = {"S": "§", "ldots": "…", "dots": "…"}
ITEM = "\x00"

_ENV = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.S)
_COMMENT = re.compile(r"(?<!\\)%.*")
_NO_PLAIN = re.compile(r"\\(?:" + "|".join(NO_PLAIN_FORM) + r")(?![A-Za-z])\*?(?:\[[^\]]*\])?\{[^{}]*\}")
_ARGUMENT = re.compile(r"\\(" + "|".join(KEEP_ARGUMENT + DROP_WITH_ARGUMENT) + r")(?![A-Za-z])\*?\{([^{}]*)\}")
_LIST = re.compile(r"\\(?:begin|end)\{(?:itemize|enumerate)\}")
_ITEM = re.compile(r"\\item(?![A-Za-z])")
_MATH = re.compile(r"(?<!\\)\$(.*?)(?<!\\)\$", re.S)
_WORD_SYMBOL = re.compile(r"\\(" + "|".join(WORD_SYMBOLS) + r")(?![A-Za-z])")
_COMMAND = re.compile(r"\\(?:[A-Za-z]+|[^A-Za-z\s])")


def plain_text(tex: str) -> tuple[str, list[str]]:
    """``(text, problems)``: the abstract in ``tex`` as plain text, and the markup that has no plain form."""
    env = _ENV.search(tex)
    body = env.group(1) if env else tex
    body = "\n".join(_COMMENT.sub("", line) for line in body.splitlines())
    problems = [f"no plain-text form: {m.group(0)}" for m in _NO_PLAIN.finditer(body)]
    body = _NO_PLAIN.sub("", body)
    while True:  # innermost first, so that nested formatting commands are resolved too
        new = _ARGUMENT.sub(lambda m: "" if m.group(1) in DROP_WITH_ARGUMENT else m.group(2), body)
        if new == body:
            break
        body = new
    body = _ITEM.sub(ITEM, _LIST.sub("\n\n", body))
    body = _MATH.sub(lambda m: m.group(1), body)
    for escape, char in ESCAPES.items():
        body = body.replace(escape, char)
    body = _WORD_SYMBOL.sub(lambda m: WORD_SYMBOLS[m.group(1)], body)
    body = body.replace("---", "\u2014").replace("--", "\u2013").replace("``", '"').replace("''", '"').replace("~", " ")
    problems += [f"unconverted command: {c}" for c in sorted(set(_COMMAND.findall(body)))]
    body = body.replace("{", "").replace("}", "")
    paragraphs = []
    for block in re.split(r"\n[ \t]*\n", body):
        head, *items = block.split(ITEM)
        lines = ([" ".join(head.split())] if head.split() else []) + ["- " + " ".join(i.split()) for i in items if i.split()]
        if lines:
            paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs), problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Count the characters of the abstract with TeX markup removed.")
    ap.add_argument("path", nargs="?", type=Path, default=DEFAULT)
    ap.add_argument("--limit", type=int, default=LIMIT)
    ap.add_argument("--print", action="store_true", help="also print the plain text")
    a = ap.parse_args(argv)
    text, problems = plain_text(a.path.read_text(encoding="utf-8"))
    if a.print:
        print(text, end="\n\n")
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)
    over = len(text) > a.limit
    verdict = "TOO LONG" if over else "UNRELIABLE" if problems else "OK"
    print(f"abstract: {len(text)} characters without TeX markup (limit {a.limit}): {verdict}"
          + (f"; {len(problems)} problem(s)" if problems else ""))
    return 1 if over or problems else 0


if __name__ == "__main__":
    sys.exit(main())
