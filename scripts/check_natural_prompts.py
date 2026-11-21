"""The natural arm's prompt templates (``experiments/prompts/natural/``): render a prompt, check a sent prompt against
its rendering, and compare every template with the frozen template it comes from (decision log D64; protocol
§15.5, §15.6, §19).

Usage:
  python scripts/check_natural_prompts.py render TEMPLATE [--variant NAME] [--set NAME=VALUE ...]
                [--set-file NAME=FILE ...] [--values FILE.json] [--out FILE] [--verify PROMPT_FILE] [--record FILE]
  python scripts/check_natural_prompts.py summary [--templates DIR] [--source-dir DIR ...] [--allow-missing-sources]
                [--json]
  python scripts/check_natural_prompts.py rendering

``render`` fills the template in and prints the sha256 of the prompt (of its UTF-8 bytes), with the template's name,
variant and file sha256. The values: ``--variant`` applies the values that the template fixes for one variant (its
``variant`` lines); ``--set NAME=VALUE``, ``--set-file NAME=FILE`` (the file's text, verbatim) and ``--values FILE.json``
(an object of strings) give the host's values, which are checked against :data:`PLACEHOLDERS` (a pattern, or a form
check such as the canonical JSON of the audit findings) and inserted as data, never read as template text (a value
that starts with ``@`` is data too). Every placeholder of the prompt needs a value, and a value no placeholder takes
is refused. ``--out FILE`` writes the prompt to a new file. ``--verify PROMPT_FILE`` checks that a sent prompt equals the
rendering: the file is the prompt as sent, or a workflow agent's first message (the harness's computed-task frame
with its two-space indent, read as ``scripts/agent_run_record.py`` reads it). ``--record FILE`` checks that a
generation record's ``prompt_sha256`` is the rendering's. Exit status 1 when a check fails.

``summary`` prints, for every template in the directory (default ``experiments/prompts/natural``), its sha256 and a
word-level comparison with its source template: per deviation, how many source words it removes and how many words
it adds, and whether every word outside the marked deviations is the source's. Exit status 1 when a template is
malformed, its source is missing or changed, or a word outside a marked deviation differs from the source.
``--source-dir`` names directories where a source script that is not in the repository is found (the labeler
workflow); it is looked up by file name and checked by its sha256. ``--allow-missing-sources`` reports such a source
that no ``--source-dir`` holds as not compared, instead of failing.

``rendering`` prints the sha256 of the fixed banner and block headers of the rendered PR threads
(``tracecontract.ingest.github_pr``), which every natural prompt's session input carries.

Template format ``natural-template/1``
--------------------------------------
* **Header**: every line before the first section line. A line that starts with ``#`` is a comment: the header's
  text for readers, which names the source template (a line ``# Source template: ...``) and describes every
  deviation applied (a line holding ``(x)`` for each deviation letter x). The other lines are fields:

  - ``name``: the template's name (``testgen:v1-natural``);
  - ``format``: ``natural-template/1``;
  - ``source-file``: the frozen script the template comes from, a repository-relative path, or a bare file name for
    a script outside the repository (looked up in ``--source-dir``); ``source-sha256``: its sha256;
  - ``source-expand``: ``NAME=SPEC ...``, constants of the script whose own text stands where the source names them
    (``COMMON``, ``CLI``, a function such as ``noRead``);
  - ``source-map``: ``EXPRESSION=PLACEHOLDER[@letters] ...``, source expressions that stand for a placeholder of the
    template (``T=TASK``); ``@letters`` marks a mapping whose value differs in kind from the source's (a deviation:
    the source's workspace under ``/home/user/gen_workspaces`` becomes the agent's own one);
  - ``deviations``: the letters of the deviations applied (decision log D64);
  - ``placeholders``: the placeholders of the prompt;
  - ``variant NAME``: ``PLACEHOLDER=VALUE ...``, the values that a variant fixes; ``@KEY`` names the template's value
    section ``PLACEHOLDER=KEY``, and an empty VALUE leaves the placeholder empty. A variant's values are template
    text: they may hold placeholders.

* **Sections**: ``@@ body <- SPEC`` starts the prompt, and ``@@ value PLACEHOLDER=KEY <- SPEC`` a value that the template
  fixes. ``<- SPEC`` names the source text of the section; a section without it is new text, every word of which must
  lie in a marked deviation. A section runs to the next section line, without its last line break.
* **SPEC**: ``Lm-Ln``, the statement on lines m to n of the source script (``const NAME = ...``, the body of an arrow
  function, ``return ...``, ``function name(...) { return ... }``); ``Ln:key``, the value of ``key`` on line n (in an
  object literal); ``Ln#k``, the k-th string literal on line n.
* **Text**: ``{NAME}`` (capitals, digits, underscores) is a placeholder. ``{{x}}...{{/}}`` marks a deviation of the
  letters x (one or more, comma-separated); an empty marker ``{{x}}{{/}}`` marks a place where source text is removed.
  Markers do not nest, and rendering removes them.

Comparison
----------
The source text of a section is the JavaScript string value of its SPEC, with each interpolated or concatenated
expression replaced: a ``source-map`` entry by its ``{PLACEHOLDER}``, a ``source-expand`` constant by its own text, any
other expression by ``${expression}`` (whitespace removed). Both texts are split into words at whitespace. The words
outside the marked deviations must be the source's words, in order; each deviation (a marked span, with every word it
touches) stands for any run of source words, or for none. The comparison is of words: line breaks and runs of spaces
are not compared.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tracecontract.ingest.pseudonymize_pr import _TIER, MODEL
from tracecontract.schemas import Outcome

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "experiments" / "prompts" / "natural"
WORKFLOWS = REPO / "experiments" / "prompts" / "workflows"
FORMAT = "natural-template/1"
TEMPLATE_GLOB = "*.txt"
# The decision-log entry that fixes these templates; every template's first line, the README and this module cite it.
DECISION = "D64"
NAT_WS = "/home/user/nat_ws"
# The study's CLI, as a natural agent may run it: by its absolute path, with one of these subcommands only (the CLI
# allowlist of the natural-agent audit profile, natural-agent:v1).
CLI_PATH = "/home/user/trace-contract/.venv/bin/tracecontract"
CLI_SUBCOMMANDS = ("lint-tests", "check-proposals")

# The harness's computed-task frame of a workflow agent's first message (scripts/agent_run_record.py).
TASK_FRAME = re.compile(r"\[Workflow harness [—-] computed task\]")
TASK_MARKER = "The computed task text follows:"
INDENT = "  "


class TemplateError(ValueError):
    """A template file is malformed, or a value does not fit it."""


class SourceError(ValueError):
    """A source script cannot be read as the template's header says."""


# --------------------------------------------------------------------------- placeholders


@dataclass(frozen=True)
class Placeholder:
    """A placeholder's rule. ``pattern``: what a host value must match in full (``None``: no pattern; then ``form``
    names the check of the value's form in :data:`FORM_CHECKS`, and only a template value has neither); ``template``:
    the value must come from the template (a variant or a value section), never from the host."""

    description: str
    pattern: str | None = None
    template: bool = False
    multiline: bool = False
    form: str | None = None


_NAME_WORD = r"[A-Za-z_][A-Za-z0-9_.-]*"
# A check of a verifier, by its id as the grader reports it: the pytest node id of a test function in a test_*.py file
# of the tests directory (tracecontract.verifier.discover_checks), optionally inside a Test class.
CHECK_ID = r"(?:[A-Za-z0-9_.-]+/)*test_[A-Za-z0-9_]*\.py::(?:Test[A-Za-z0-9_]*::)?test[A-Za-z0-9_]*"
OUTCOMES = tuple(o.value for o in Outcome)  # a grade's outcome (tracecontract.schemas.Outcome)
_OUTCOME = "(?:" + "|".join(re.escape(o) for o in OUTCOMES) + ")"
# The host's validation of the reference checks, for their reviewers (decision log D64, deviation f): the reference's
# outcome in each of its three repeats, the development no-op's outcome, and the checks that failed (status failed or
# error) on the reference in any repeat, by check id, sorted and comma-separated, or "none".
VALIDATION_FORMAT = (f"reference, 3 repeats: {_OUTCOME}, {_OUTCOME}, {_OUTCOME}\ndev no-op: {_OUTCOME}\n"
                     f"checks failing on the reference: (?:none|{CHECK_ID}(?:, {CHECK_ID})*)")
# The audit findings a reviser is given: each finding's code and message, as the source workflow's audit runner
# returned them (its AUDIT_SCHEMA), serialised as JSON.stringify(findings, null, 1) was: json.dumps(indent=1).
FINDING_KEYS = ("code", "message")
# The issues a fixer of the reference checks is given: the review's issues with the keys of the source workflow's
# REVIEW_SCHEMA, in its order, serialised as JSON.stringify(review.issues) was: compact JSON.
ISSUE_KEYS = ("test", "kind", "requirement_ids", "explanation", "suggested_fix")
ISSUE_KINDS = ("over_specified", "unspecified_behavior", "wrong_expectation", "flaky_risk", "missing_coverage")
PLACEHOLDERS: dict[str, Placeholder] = {
    "TASK": Placeholder("the natural task id", r"NP-\d{2,}"),
    "WS": Placeholder("the agent's own workspace, /home/user/nat_ws/<task>/<role>[-k] (an attacker's group of states)",
                      r"/home/user/nat_ws/NP-\d{2,}/[A-Za-z0-9][A-Za-z0-9._-]*"),
    "SESSION_ID": Placeholder("the session id, whose events the rendered thread names", r"aidev-pr-\d+"),
    "PYTHONPATH": Placeholder("the task's candidate PYTHONPATH in the grading container (under /work)",
                              r"/work(?:/[A-Za-z0-9._-]+)*(?::/work(?:/[A-Za-z0-9._-]+)*)*"),
    "PYPATH": Placeholder("the PYTHONPATH of the workspace's sandbox wrappers (under /repo)",
                          r"/repo(?:/[A-Za-z0-9._-]+)*(?::/repo(?:/[A-Za-z0-9._-]+)*)*"),
    "TESTS": Placeholder("the pytest arguments of the family's base-test subset, for run_tests.sh",
                         r"[A-Za-z0-9_./:=+-]+(?: [A-Za-z0-9_./:=+-]+)*"),
    "K": Placeholder("the candidate's number in the held-out pool", r"[1-9]"),
    "TARGET": Placeholder("the reference requirement the near miss violates (given by the host)", _NAME_WORD),
    "ITER": Placeholder("the audit iteration of a reviser", r"[1-3]"),
    "FINDINGS": Placeholder("the host's audit findings: each finding's code and message, as json.dumps(indent=1)",
                            multiline=True, form="findings"),
    "ISSUES": Placeholder("the reviewer's issues: the review schema's five keys, as compact JSON", form="issues"),
    "VALIDATION": Placeholder("the host's validation of the reference checks: outcomes on the reference (3 repeats) "
                              "and the dev no-op, and the check ids of the checks failing on the reference",
                              VALIDATION_FORMAT, multiline=True, form="validation"),
    "FAILING": Placeholder("bare names, one check id per line, sorted and distinct (§19.8): the checks that failed on "
                           "the reference, and those mapped to a change requirement that passed on the no-op",
                           rf"{CHECK_ID}(?:\n{CHECK_ID})*", multiline=True, form="failing"),
    "MAPPER": Placeholder("the mapper's label", r"model:config-[A-Z]:mapper:v1(?:#2)?"),
    "CONDITION": Placeholder("the verifier condition", r"initial_plain|full_plain|llm_freeform|diff_derived",
                             template=True),
    "VARIANT": Placeholder("the contract variant", r"initial_only|full_session|reference", template=True),
    "SESSION_FILE": Placeholder("the session text in the workspace", None, template=True),
    "INPUTS": Placeholder("the inputs of a test generator", None, template=True, multiline=True),
    "MAP_TEXT": Placeholder("how a test generator maps tests to requirements", None, template=True),
    "STYLE": Placeholder("the approach of a held-out alternative", None, template=True),
    "SHARED": Placeholder("a near miss's sentence when an earlier near miss of the family has its target (empty "
                          "otherwise)", None, template=True),
}
_PLACEHOLDER = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")

# What no rendered prompt may hold: a path under the natural task data, a session-local path, a held-out candidate id
# of a natural task, or a model identifier or tier name (decision log D47, D56, D64). The identifiers are those the PR
# pseudonymiser masks (it leaves the session directory claude-0 alone). Its tier names include "instant", an ordinary
# word that a finding or an issue may use; a model named with it ("claude-instant ...") is a model identifier.
_TIERS = re.fullmatch(r"\(\?:([a-z|]+)\)", _TIER)
if _TIERS is None:
    raise ImportError("tracecontract.ingest.pseudonymize_pr._TIER is no longer a plain list of tier names")
TIER_WORDS = tuple(t for t in _TIERS.group(1).split("|") if t != "instant")
_FORBIDDEN_IN_PROMPT = (
    ("a path under data/natural", re.compile(r"data/natural")),
    ("a session-local path", re.compile("/tmp/claude-0/" + "-|/root/" + r"\.claude/projects")),
    ("a held-out candidate id", re.compile(r"NP-\d+-(?:eval-|pre-review)")),
    ("a model identifier", MODEL),
    ("a model tier name", re.compile(r"\b(?:" + "|".join(TIER_WORDS) + r")\b", re.IGNORECASE)),
)
# What no host value may hold besides: a path to the private run records (the templates name the directory only in
# their do-not-read lists), and a held-out candidate's name without the task id. The workspace (WS) is exempt: the
# held-out generators' workspaces are named after their candidates (eval-alt-1, eval-nm-1, ...).
_FORBIDDEN_IN_VALUES = (
    ("a private run-record path", re.compile(r"nat_runrec")),
    ("a held-out candidate's name", re.compile(r"(?<![\w-])(?:eval-(?:alt|nm)-\d+|pre-review)(?![\w-])")),
)
_VALUE_EXEMPT = ("WS",)


# --------------------------------------------------------------------------- reading the source scripts


@dataclass
class _Node:
    kind: str
    start: int
    end: int
    value: Any = None
    kids: tuple[_Node, ...] = ()


_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_ARROW = re.compile(r"(?:\([^()]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>\s*")
_BINARY = ("===", "!==", "==", "!=", "<=", ">=", "&&", "||", "+", "-", "*", "/", "%", "<", ">")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v"}
_STMT_FUNCTION = re.compile(r"\s*function\s+[A-Za-z_$][\w$]*\s*\([^()]*\)\s*\{")
_STMT_CONST = re.compile(r"\s*(?:export\s+)?(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=(?!=)\s*")
_STMT_RETURN = re.compile(r"\s*return\b\s*")
_RETURN = re.compile(r"\breturn\b")


class _Parser:
    """A reader of the JavaScript expressions that the workflow scripts build prompts from: string and template
    literals, ``+``, names, member access, calls, arrays (``[...].join(sep)``), parentheses and ternaries."""

    def __init__(self, text: str, i: int = 0) -> None:
        self.s, self.i = text, i

    def _skip(self) -> None:
        s = self.s
        while self.i < len(s):
            if s[self.i].isspace():
                self.i += 1
            elif s.startswith("//", self.i):
                j = s.find("\n", self.i)
                self.i = len(s) if j < 0 else j
            elif s.startswith("/*", self.i):
                j = s.find("*/", self.i + 2)
                if j < 0:
                    raise SourceError("an unterminated comment")
                self.i = j + 2
            else:
                break

    def _at(self, tok: str) -> bool:
        self._skip()
        return self.s.startswith(tok, self.i)

    def _expect(self, tok: str) -> None:
        if not self._at(tok):
            raise SourceError(f"expected {tok!r} at offset {self.i}, found {self.s[self.i:self.i + 20]!r}")
        self.i += len(tok)

    def expr(self) -> _Node:
        cond = self._binary()
        if self._at("?") and not self._at("?."):
            self.i += 1
            a = self.expr()
            self._expect(":")
            b = self.expr()
            return _Node("ternary", cond.start, b.end, kids=(cond, a, b))
        return cond

    def _binary(self) -> _Node:
        left = self._unary()
        while True:
            self._skip()
            if self.s.startswith("=>", self.i):
                return left
            op = next((o for o in _BINARY if self.s.startswith(o, self.i)), None)
            if op is None:
                return left
            self.i += len(op)
            right = self._unary()
            left = _Node("concat" if op == "+" else "binary", left.start, right.end, value=op, kids=(left, right))

    def _unary(self) -> _Node:
        self._skip()
        if self.s.startswith("!", self.i) and not self.s.startswith("!=", self.i):
            start = self.i
            self.i += 1
            x = self._unary()
            return _Node("unary", start, x.end, value="!", kids=(x,))
        return self._postfix()

    def _postfix(self) -> _Node:
        node = self._primary()
        while True:
            self._skip()
            s = self.s
            if s.startswith(".", self.i) and not s.startswith("...", self.i):
                self.i += 1
                self._skip()
                m = _IDENT.match(s, self.i)
                if not m:
                    raise SourceError(f"a member name expected at offset {self.i}")
                self.i = m.end()
                node = _Node("member", node.start, self.i, value=m.group(), kids=(node,))
            elif s.startswith("(", self.i):
                self.i += 1
                args: list[_Node] = []
                if not self._at(")"):
                    while True:
                        args.append(self.expr())
                        if self._at(","):
                            self.i += 1
                            continue
                        break
                self._expect(")")
                node = _Node("call", node.start, self.i, kids=(node, *args))
            elif s.startswith("[", self.i):
                self.i += 1
                index = self.expr()
                self._expect("]")
                node = _Node("index", node.start, self.i, kids=(node, index))
            else:
                return node

    def _primary(self) -> _Node:
        self._skip()
        s, i = self.s, self.i
        if i >= len(s):
            raise SourceError("the source ends inside an expression")
        c = s[i]
        if c in "'\"":
            return self._string(c)
        if c == "`":
            return self._template()
        if c == "(":
            self.i += 1
            x = self.expr()
            self._expect(")")
            return _Node("paren", i, self.i, kids=(x,))
        if c == "[":
            self.i += 1
            elems: list[_Node] = []
            while not self._at("]"):
                elems.append(self.expr())
                if self._at(","):
                    self.i += 1
                    continue
                break
            self._expect("]")
            return _Node("array", i, self.i, kids=tuple(elems))
        m = _NUMBER.match(s, i)
        if m:
            self.i = m.end()
            return _Node("number", i, self.i, value=m.group())
        m = _IDENT.match(s, i)
        if m:
            self.i = m.end()
            return _Node("name", i, self.i, value=m.group())
        raise SourceError(f"unexpected {c!r} at offset {i}")

    def _escape(self) -> str:
        s = self.s
        self.i += 1  # the backslash
        if self.i >= len(s):
            raise SourceError("the source ends inside an escape")
        c = s[self.i]
        self.i += 1
        if c in _ESCAPES:
            return _ESCAPES[c]
        if c == "0" and not (self.i < len(s) and s[self.i].isdigit()):
            return "\0"
        if c == "x":
            h = s[self.i:self.i + 2]
            self.i += 2
            return chr(int(h, 16))
        if c == "u":
            if s.startswith("{", self.i):
                j = s.index("}", self.i)
                h, self.i = s[self.i + 1:j], j + 1
            else:
                h = s[self.i:self.i + 4]
                self.i += 4
            return chr(int(h, 16))
        if c == "\n":  # a line continuation
            return ""
        return c

    def _string(self, quote: str) -> _Node:
        start = self.i
        self.i += 1
        out: list[str] = []
        while True:
            if self.i >= len(self.s):
                raise SourceError("an unterminated string literal")
            c = self.s[self.i]
            if c == quote:
                self.i += 1
                return _Node("string", start, self.i, value="".join(out))
            if c == "\\":
                out.append(self._escape())
            elif c == "\n":
                raise SourceError("a line break inside a string literal")
            else:
                out.append(c)
                self.i += 1

    def _template(self) -> _Node:
        start = self.i
        self.i += 1
        parts: list[str | _Node] = []
        buf: list[str] = []
        while True:
            if self.i >= len(self.s):
                raise SourceError("an unterminated template literal")
            c = self.s[self.i]
            if c == "`":
                self.i += 1
                if buf:
                    parts.append("".join(buf))
                return _Node("template", start, self.i, value=tuple(parts))
            if c == "\\":
                buf.append(self._escape())
            elif self.s.startswith("${", self.i):
                if buf:
                    parts.append("".join(buf))
                    buf = []
                self.i += 2
                parts.append(self.expr())
                self._expect("}")
            else:
                buf.append(c)
                self.i += 1


def _line_offsets(text: str) -> list[int]:
    """The offset of the start of each line (line 1 first), and the length of the text last."""
    offsets = [0]
    for m in re.finditer("\n", text):
        offsets.append(m.end())
    offsets.append(len(text) + 1)
    return offsets


_SPEC = re.compile(r"L(\d+)(?:-L(\d+)|:([A-Za-z_$][\w$]*)|#(\d+))?")


def parse_spec(text: str, spec: str) -> _Node:
    """The expression that ``spec`` names in the source script ``text`` (see the module docstring)."""
    m = _SPEC.fullmatch(spec)
    if not m:
        raise SourceError(f"bad source spec {spec!r} (Lm-Ln, Ln:key or Ln#k)")
    offs = _line_offsets(text)
    first = int(m.group(1))
    last = int(m.group(2) or first)
    if not 1 <= first <= last <= len(offs) - 1:
        raise SourceError(f"{spec}: the script has {len(offs) - 2} lines")
    start, end = offs[first - 1], offs[last] - 1  # the end of line `last`, before its line break
    if m.group(3):  # Ln:key
        km = re.compile(r"(?<![\w$])" + re.escape(m.group(3)) + r"\s*:\s*").search(text, start, end)
        if not km:
            raise SourceError(f"{spec}: line {first} has no key {m.group(3)!r}")
        return _Parser(text, km.end()).expr()
    if m.group(4):  # Ln#k
        want, n, i = int(m.group(4)), 0, start
        while i < end:
            if text[i] in "'\"`":
                p = _Parser(text, i)
                node = p._primary()
                n += 1
                if n == want:
                    return node
                i = p.i
            else:
                i += 1
        raise SourceError(f"{spec}: line {first} has {n} string literals")
    fm = _STMT_FUNCTION.match(text, start)
    if fm:
        rm = _RETURN.search(text, fm.end(), end)
        if not rm:
            raise SourceError(f"{spec}: the function has no return statement in the range")
        p = _Parser(text, rm.end())
    else:
        sm = _STMT_CONST.match(text, start) or _STMT_RETURN.match(text, start)
        i = sm.end() if sm else start
        am = _ARROW.match(text, i)
        p = _Parser(text, am.end() if am else i)
    node = p.expr()
    if node.end > end:
        raise SourceError(f"{spec}: the statement runs past line {last}")
    rest = text[node.end:end]
    if rest.strip(" \t\r\n;)}") != "":
        raise SourceError(f"{spec}: the range holds more than one statement (then {rest.strip()[:60]!r})")
    return node


@dataclass
class SourceText:
    """How a section's source text is built from a script: the constants to inline and the placeholder mapping."""

    text: str
    expand: dict[str, str]
    mapping: dict[str, str]
    used: set[str] = field(default_factory=set)

    def flatten(self, spec: str) -> str:
        """The source text of ``spec`` (see Comparison in the module docstring)."""
        return "".join(self._segments(parse_spec(self.text, spec), ()))

    def _segments(self, node: _Node, stack: tuple[str, ...]) -> list[str]:
        k = node.kind
        if k == "string":
            return [node.value]
        if k == "template":
            out: list[str] = []
            for part in node.value:
                out += [part] if isinstance(part, str) else self._segments(part, stack)
            return out
        if k == "concat":
            return self._segments(node.kids[0], stack) + self._segments(node.kids[1], stack)
        if k == "paren":
            return self._segments(node.kids[0], stack)
        key = re.sub(r"\s+", "", self.text[node.start:node.end])
        if key in self.mapping:
            self.used.add(key)
            return ["{" + self.mapping[key] + "}"]
        if k == "call":
            callee = node.kids[0]
            if (callee.kind == "member" and callee.value == "join" and callee.kids[0].kind == "array"
                    and len(node.kids) == 2):
                sep = self._segments(node.kids[1], stack)
                joined: list[str] = []
                for n, el in enumerate(callee.kids[0].kids):
                    joined += (sep if n else []) + self._segments(el, stack)
                return joined
            if callee.kind == "name" and callee.value in self.expand:
                return self._expansion(callee.value, stack)
        if k == "name" and node.value in self.expand:
            return self._expansion(node.value, stack)
        return ["${" + key + "}"]

    def _expansion(self, name: str, stack: tuple[str, ...]) -> list[str]:
        if name in stack:
            raise SourceError(f"source-expand {name} refers to itself")
        self.used.add(name)
        return self._segments(parse_spec(self.text, self.expand[name]), (*stack, name))


# --------------------------------------------------------------------------- templates


_MARK = re.compile(r"\{\{[^{}]*\}\}")
_OPEN = re.compile(r"\{\{([a-z](?:,[a-z])*)\}\}")
_CLOSE = "{{/}}"
_SECTION = re.compile(r"@@ (body|value ([A-Z][A-Z0-9_]*)=([A-Za-z0-9_.-]+))(?: <- (\S+))?\s*")
_FIELD = re.compile(r"([a-z][a-z0-9-]*(?: [A-Za-z0-9_.-]+)?):\s?(.*)")


@dataclass(frozen=True)
class Span:
    """A marked deviation: its letters, and where it lies in the section's text without markers."""

    letters: tuple[str, ...]
    start: int
    end: int


@dataclass
class Section:
    kind: str  # "body" or "value"
    placeholder: str | None
    key: str | None
    spec: str | None  # None: new text
    text: str  # with markers
    line: int  # the file line of its first text line

    @property
    def label(self) -> str:
        return "body" if self.kind == "body" else f"value {self.placeholder}={self.key}"


@dataclass
class Template:
    path: Path
    sha256: str
    fields: dict[str, str]
    comments: list[str]
    sections: list[Section]
    variants: dict[str, dict[str, str]]

    @property
    def name(self) -> str:
        return self.fields["name"]

    @property
    def body(self) -> Section:
        return next(s for s in self.sections if s.kind == "body")

    def value(self, placeholder: str, key: str) -> Section:
        for s in self.sections:
            if s.kind == "value" and s.placeholder == placeholder and s.key == key:
                return s
        raise TemplateError(f"{self.name}: no value section {placeholder}={key}")

    @property
    def deviations(self) -> list[str]:
        return self.fields.get("deviations", "").split()

    @property
    def placeholders(self) -> list[str]:
        return self.fields.get("placeholders", "").split()

    def pairs(self, key: str) -> dict[str, str]:
        """A field of ``NAME=VALUE`` words, as a dict."""
        out: dict[str, str] = {}
        for word in self.fields.get(key, "").split():
            name, sep, value = word.partition("=")
            if not sep or not name or not value:
                raise TemplateError(f"{self.name}: {key}: {word!r} is not NAME=VALUE")
            if name in out:
                raise TemplateError(f"{self.name}: {key}: {name} is given twice")
            out[name] = value
        return out


def strip_markers(text: str) -> tuple[str, list[Span]]:
    """The text without deviation markers, and the marked spans."""
    out: list[str] = []
    spans: list[Span] = []
    pos, size = 0, 0
    opened: tuple[tuple[str, ...], int] | None = None
    for m in _MARK.finditer(text):
        out.append(text[pos:m.start()])
        size += m.start() - pos
        tok = m.group()
        if tok == _CLOSE:
            if opened is None:
                raise TemplateError(f"a closing marker {_CLOSE} without an opening one, at offset {m.start()}")
            spans.append(Span(opened[0], opened[1], size))
            opened = None
        else:
            om = _OPEN.fullmatch(tok)
            if not om:
                raise TemplateError(f"a malformed deviation marker {tok!r}")
            if opened is not None:
                raise TemplateError(f"deviation markers do not nest ({tok!r} inside another)")
            opened = (tuple(om.group(1).split(",")), size)
        pos = m.end()
    if opened is not None:
        raise TemplateError("a deviation marker is not closed")
    out.append(text[pos:])
    return "".join(out), spans


def parse_template(path: Path) -> Template:
    """Read a template file (see the module docstring); refuse one whose header or sections are malformed."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise TemplateError(f"{path.name}: not UTF-8 text") from None
    lines = text.split("\n")
    fields: dict[str, str] = {}
    comments: list[str] = []
    variants: dict[str, dict[str, str]] = {}
    sections: list[Section] = []
    i = 0
    while i < len(lines) and not lines[i].startswith("@@ "):
        line = lines[i]
        i += 1
        if not line.strip():
            continue
        if line.startswith("#"):
            comments.append(line)
            continue
        fm = _FIELD.fullmatch(line)
        if not fm:
            raise TemplateError(f"{path.name}:{i}: neither a comment nor a field: {line[:60]!r}")
        key, value = fm.group(1), fm.group(2).strip()
        if key.startswith("variant "):
            vname = key.split(" ", 1)[1]
            if vname in variants:
                raise TemplateError(f"{path.name}:{i}: variant {vname} is defined twice")
            variants[vname] = {}
            for word in value.split():
                name, sep, val = word.partition("=")
                if not sep or not _PLACEHOLDER.fullmatch("{" + name + "}"):
                    raise TemplateError(f"{path.name}:{i}: variant {vname}: {word!r} is not PLACEHOLDER=VALUE")
                variants[vname][name] = val
            continue
        if key in fields:
            raise TemplateError(f"{path.name}:{i}: the field {key} is given twice")
        fields[key] = value
    while i < len(lines):
        sm = _SECTION.fullmatch(lines[i])
        if not sm:
            raise TemplateError(f"{path.name}:{i + 1}: a malformed section line {lines[i][:60]!r}")
        start = i + 1
        i += 1
        body: list[str] = []
        while i < len(lines) and not lines[i].startswith("@@ "):
            body.append(lines[i])
            i += 1
        # without the line break before the next section line (or the file's last)
        content = "\n".join(body).removesuffix("\n")
        kind = "body" if sm.group(1) == "body" else "value"
        sections.append(Section(kind, sm.group(2), sm.group(3), sm.group(4), content, start + 1))
    t = Template(path, hashlib.sha256(raw).hexdigest(), fields, comments, sections, variants)
    _check_template(t)
    return t


def _check_template(t: Template) -> None:
    """Refuse a template whose header lacks what the format asks for, or whose sections do not fit it."""
    where = t.path.name
    for key in ("name", "format", "source-file", "source-sha256", "deviations", "placeholders"):
        if not t.fields.get(key):
            raise TemplateError(f"{where}: the header has no {key} field")
    if t.fields["format"] != FORMAT:
        raise TemplateError(f"{where}: format {t.fields['format']!r}, not {FORMAT}")
    if not re.fullmatch(r"[0-9a-f]{64}", t.fields["source-sha256"]):
        raise TemplateError(f"{where}: source-sha256 is not a sha256")
    if not any(c.startswith("# Source template:") for c in t.comments):
        raise TemplateError(f"{where}: the header names no source template (a line '# Source template: ...')")
    letters = t.deviations
    if len(set(letters)) != len(letters) or not all(re.fullmatch(r"[a-z]", x) for x in letters):
        raise TemplateError(f"{where}: deviations must be distinct single letters, not {letters}")
    text = "\n".join(t.comments)
    undescribed = [x for x in letters if f"({x})" not in text]
    if undescribed:
        raise TemplateError(f"{where}: the header does not describe the deviation(s) {undescribed}")
    if [s.kind for s in t.sections].count("body") != 1:
        raise TemplateError(f"{where}: a template has exactly one body section")
    keys = [(s.placeholder, s.key) for s in t.sections if s.kind == "value"]
    if len(set(keys)) != len(keys):
        raise TemplateError(f"{where}: a value section is given twice")
    declared = set(t.placeholders)
    unknown = sorted(declared - set(PLACEHOLDERS))
    if unknown:
        raise TemplateError(f"{where}: unknown placeholders {unknown} (see PLACEHOLDERS)")
    used_letters: set[str] = set()
    used_names: set[str] = set()
    for s in t.sections:
        clean, spans = strip_markers(s.text)
        for sp in spans:
            bad = [x for x in sp.letters if x not in letters]
            if bad:
                raise TemplateError(f"{where}: {s.label}: deviation {bad} is not in the header's deviations")
            used_letters |= set(sp.letters)
        used_names |= set(_PLACEHOLDER.findall(clean))
        if s.kind == "value" and s.placeholder not in declared:
            raise TemplateError(f"{where}: value section {s.label} is for an undeclared placeholder")
        if s.kind == "value" and not PLACEHOLDERS[s.placeholder].template:
            raise TemplateError(f"{where}: {s.placeholder} is the host's value, not the template's")
    for name, value in ((n, v) for vs in t.variants.values() for n, v in vs.items()):
        if name not in declared:
            raise TemplateError(f"{where}: a variant sets the undeclared placeholder {name}")
        if value.startswith("@"):
            t.value(name, value[1:])
        else:
            used_names |= set(_PLACEHOLDER.findall(value))
    for entry, target in t.pairs("source-map").items():
        name, _, devs = target.partition("@")
        if name not in declared:
            raise TemplateError(f"{where}: source-map {entry} names the undeclared placeholder {name}")
        bad = [x for x in devs.split(",") if devs and x not in letters]
        if bad:
            raise TemplateError(f"{where}: source-map {entry}: deviation {bad} is not in the header's deviations")
        used_letters |= set(devs.split(",")) if devs else set()
    undeclared = sorted(used_names - declared)
    if undeclared:
        raise TemplateError(f"{where}: the text uses undeclared placeholders {undeclared}")
    unused = sorted(declared - used_names - {s.placeholder for s in t.sections if s.kind == "value"}
                    - {n for vs in t.variants.values() for n in vs})
    if unused:
        raise TemplateError(f"{where}: declared placeholders {unused} are not used")
    unapplied = [x for x in letters if x not in used_letters]
    if unapplied:
        raise TemplateError(f"{where}: deviation(s) {unapplied} are declared but marked nowhere")


def load_templates(directory: Path = TEMPLATES) -> list[Template]:
    """Every template of the directory, by name; refuse two templates of one name."""
    out = [parse_template(p) for p in sorted(directory.glob(TEMPLATE_GLOB))]
    names = [t.name for t in out]
    if len(set(names)) != len(names):
        raise TemplateError(f"two templates share a name: {sorted(n for n in set(names) if names.count(n) > 1)}")
    return out


# --------------------------------------------------------------------------- comparison


@dataclass
class Hunk:
    """One deviation in a section: its letters, its file line, the source words it removes and the words it adds."""

    letters: tuple[str, ...]
    line: int
    removed: list[str]
    added: list[str]


@dataclass
class Comparison:
    label: str
    source_words: int
    kept_words: int  # words outside the deviations, each the source's
    hunks: list[Hunk]
    problems: list[str]
    notes: list[str]


def _find(words: list[str], run: list[str], start: int) -> int:
    """The first index at or after ``start`` where ``run`` occurs in ``words``, or -1."""
    n = len(run)
    for i in range(start, len(words) - n + 1):
        if words[i:i + n] == run:
            return i
    return -1


def compare_section(source: str | None, text: str, *, label: str = "body", first_line: int = 1) -> Comparison:
    """Compare a section's ``text`` (with markers) with its ``source`` text (``None``: new text); see the module
    docstring."""
    clean, spans = strip_markers(text)
    words = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", clean)]

    def line_of(offset: int) -> int:
        return first_line + clean.count("\n", 0, offset)

    # The pattern: runs of words outside the deviations, separated by wildcards (deviations with the words they touch).
    runs: list[list[str]] = [[]]
    wilds: list[Hunk] = []
    events: list[tuple[int, int, Any]] = []  # (offset, order, item): words, and empty spans between words
    inside: dict[int, list[Span]] = {}
    for n, (ws, we, _) in enumerate(words):
        # A span touches the word if they overlap; an empty span (a removal) only if it lies strictly inside the word.
        inside[n] = [sp for sp in spans
                     if (sp.start != sp.end and ws < sp.end and sp.start < we) or (sp.start == sp.end and ws < sp.start < we)]
        events.append((ws, 1, n))
    for sp in spans:
        if sp.start == sp.end and not any(ws < sp.start < we for ws, we, _ in words):
            events.append((sp.start, 0, sp))
    events.sort(key=lambda e: (e[0], e[1]))
    last_wild = False
    for _, _, item in events:
        if isinstance(item, Span) or inside[item]:
            sps = [item] if isinstance(item, Span) else inside[item]
            letters = tuple(sorted({x for sp in sps for x in sp.letters}))
            if not last_wild:
                wilds.append(Hunk(letters, line_of(sps[0].start), [], []))
                runs.append([])
            else:
                wilds[-1].letters = tuple(sorted(set(wilds[-1].letters) | set(letters)))
            if not isinstance(item, Span):
                wilds[-1].added.append(words[item][2])
            last_wild = True
        else:
            runs[-1].append(words[item][2])
            last_wild = False
    kept = sum(len(r) for r in runs)
    problems: list[str] = []
    notes: list[str] = []
    if source is None:
        if kept:
            first = next(r for r in runs if r)
            problems.append(f"{label}: new text outside a marked deviation, from {' '.join(first[:8])!r}")
        return Comparison(label, 0, 0, wilds, problems, notes)
    src = source.split()
    positions: list[int] = []
    pos = 0
    for idx, run in enumerate(runs):
        if len(runs) == 1:
            ok = run == src
            start = 0
        elif idx == 0:
            ok, start = src[:len(run)] == run, 0
        elif idx == len(runs) - 1:
            start = len(src) - len(run)
            ok = start >= pos and src[start:] == run
        else:
            start = _find(src, run, pos)
            ok = start >= 0
        if not ok:
            longest = 0
            for size in range(len(run), 0, -1):
                if _find(src, run[:size], pos) >= 0:
                    longest = size
                    break
            at = " ".join(run[longest:longest + 8]) or "(the end of the source)"
            problems.append(f"{label}: an unmarked difference from the source: after {' '.join(run[:longest][-6:])!r} "
                            f"the text has {at!r}" if longest else
                            f"{label}: an unmarked difference from the source at {' '.join(run[:8])!r}")
            break
        positions.append(start)
        pos = start + len(run)
    else:
        for n, hunk in enumerate(wilds):
            begin = positions[n] + len(runs[n])
            hunk.removed = src[begin:positions[n + 1]]
            if not hunk.removed and not hunk.added:
                notes.append(f"{label}: line {hunk.line}: deviation {','.join(hunk.letters)} changes nothing")
            elif hunk.removed == hunk.added:
                notes.append(f"{label}: line {hunk.line}: deviation {','.join(hunk.letters)} equals the source text")
    return Comparison(label, len(src), kept, wilds, problems, notes)


def find_source(name: str, source_dirs: list[Path]) -> Path | None:
    """A template's source script: a repository-relative path, or a bare file name in the workflow exports or in one
    of ``source_dirs``."""
    if "/" in name:
        p = REPO / name
        return p if p.is_file() else None
    for d in (WORKFLOWS, *source_dirs):
        p = Path(d) / name
        if p.is_file():
            return p
    return None


def compare_template(t: Template, source_dirs: list[Path], *, allow_missing: bool = False) -> dict[str, Any]:
    """The comparison of every section of ``t`` with its source (see the module docstring). ``allow_missing``: a source
    outside the repository (a bare file name) that no ``source_dirs`` holds is reported as not compared, not as a
    problem; a source in the repository must always be there."""
    out: dict[str, Any] = {"name": t.name, "file": _rel(t.path), "sha256": t.sha256, "source_file": t.fields["source-file"],
                           "source_sha256": t.fields["source-sha256"], "problems": [], "notes": [], "sections": []}
    path = find_source(t.fields["source-file"], source_dirs)
    if path is None:
        if allow_missing and "/" not in t.fields["source-file"]:
            out["source"] = "not available"
            out["notes"].append(f"source {t.fields['source-file']} lies outside the repository and was not given "
                                "(--source-dir): not compared")
            return out
        out["source"] = "missing"
        out["problems"].append(f"source {t.fields['source-file']} not found (give --source-dir for a script outside "
                               "the repository)")
        return out
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != t.fields["source-sha256"]:
        out["source"] = "changed"
        out["problems"].append(f"source {t.fields['source-file']} has sha256 {hashlib.sha256(raw).hexdigest()}, not the "
                               "header's")
        return out
    out["source"] = "checked"
    src = SourceText(raw.decode("utf-8"), t.pairs("source-expand"),
                     {k: v.partition("@")[0] for k, v in t.pairs("source-map").items()})
    for s in t.sections:
        try:
            source = src.flatten(s.spec) if s.spec else None
        except SourceError as exc:
            out["problems"].append(f"{s.label}: {exc}")
            continue
        c = compare_section(source, s.text, label=s.label, first_line=s.line)
        out["problems"] += c.problems
        out["notes"] += c.notes
        out["sections"].append({"section": c.label, "source_spec": s.spec, "source_words": c.source_words,
                                "kept_words": c.kept_words,
                                "deviations": [{"letters": "".join(h.letters), "line": h.line, "removed": len(h.removed),
                                                "added": len(h.added)} for h in c.hunks]})
    unused = sorted((set(src.expand) | set(src.mapping)) - src.used)
    if unused and not out["problems"]:
        out["problems"].append(f"source-expand or source-map entries the source never uses: {unused}")
    out["mapped_deviations"] = {k: v.partition("@")[2] for k, v in t.pairs("source-map").items() if "@" in v}
    return out


# --------------------------------------------------------------------------- rendering


def _json_objects(name: str, value: str, keys: tuple[str, ...], *, indent: int | None) -> list[dict[str, Any]]:
    """``value`` as a JSON list of objects with exactly ``keys``, in that order, refused unless it is the canonical
    serialisation of that list (``json.dumps`` with ``indent``, or compact), so that the prompt follows from the data."""
    try:
        data = json.loads(value)
    except ValueError:
        raise TemplateError(f"{name}: not JSON") from None
    if not isinstance(data, list) or not all(isinstance(x, dict) and tuple(x) == keys for x in data):
        raise TemplateError(f"{name}: a JSON list of objects with the keys {', '.join(keys)} (in that order) expected")
    canonical = (json.dumps(data, indent=indent, ensure_ascii=False) if indent is not None
                 else json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    if value != canonical:
        how = f"json.dumps(..., indent={indent}, ensure_ascii=False)" if indent is not None else \
            "json.dumps(..., ensure_ascii=False, separators=(',', ':'))"
        raise TemplateError(f"{name}: not in its canonical form, {how}")
    return data


def _form_findings(value: str, values: dict[str, str]) -> None:
    for f in _json_objects("FINDINGS", value, FINDING_KEYS, indent=1):
        if not all(isinstance(f[k], str) for k in FINDING_KEYS):
            raise TemplateError("FINDINGS: a finding's code and message are strings")


def _form_issues(value: str, values: dict[str, str]) -> None:
    for i in _json_objects("ISSUES", value, ISSUE_KEYS, indent=None):
        if i["kind"] not in ISSUE_KINDS or not isinstance(i["requirement_ids"], list) \
                or not all(isinstance(x, str) for x in i["requirement_ids"]) \
                or not all(isinstance(i[k], str) for k in ("test", "explanation", "suggested_fix")):
            raise TemplateError(f"ISSUES: an issue is not of the review schema's form (kind one of {', '.join(ISSUE_KINDS)}; "
                                "requirement_ids a list of strings; the other fields strings)")


def _distinct_sorted(name: str, names: list[str]) -> None:
    if names != sorted(set(names)):
        raise TemplateError(f"{name}: the check ids must be distinct and sorted, so that their order says nothing of their "
                            "kind (§19.8, D58)")


def _form_validation(value: str, values: dict[str, str]) -> None:
    lines = value.split("\n")
    listed = lines[2].split(": ", 1)[1]
    names = [] if listed == "none" else listed.split(", ")
    _distinct_sorted("VALIDATION", names)
    reference = lines[0].split(": ", 1)[1].split(", ")
    if all(o == Outcome.passed.value for o in reference) and names:
        raise TemplateError("VALIDATION: the reference passed in every repeat, so no check failed on it")


def _form_failing(value: str, values: dict[str, str]) -> None:
    _distinct_sorted("FAILING", value.split("\n"))


FORM_CHECKS = {"findings": _form_findings, "issues": _form_issues, "validation": _form_validation,
               "failing": _form_failing}


def _check_value(name: str, value: str, values: dict[str, str]) -> None:
    rule = PLACEHOLDERS[name]
    if not rule.multiline and "\n" in value:
        raise TemplateError(f"{name}: one line expected")
    if not value.strip():
        raise TemplateError(f"{name}: an empty value")
    if rule.pattern is not None and not re.fullmatch(rule.pattern, value):
        raise TemplateError(f"{name}: {value[:80]!r} does not match {rule.pattern} ({rule.description})")
    if rule.form is not None:
        FORM_CHECKS[rule.form](value, values)
    if name == "WS":
        task = values.get("TASK")
        if task is not None and not value.startswith(f"{NAT_WS}/{task}/"):
            raise TemplateError(f"WS: {value} is not a workspace of {task} under {NAT_WS}/{task}/")
    if name not in _VALUE_EXEMPT:
        for what, pat in _FORBIDDEN_IN_VALUES:
            if pat.search(value):
                raise TemplateError(f"{name}: the value names {what}")


def render(t: Template, *, variant: str | None = None, values: dict[str, str] | None = None) -> str:
    """The prompt: the body without markers, the template's own values (the variant's, and the value sections that it
    names with ``@``) inserted as template text, then the host's ``values`` inserted as data, whatever their first
    character (see the module docstring)."""
    values = dict(values or {})
    fragments: dict[str, str] = {}
    if variant is not None:
        if variant not in t.variants:
            raise TemplateError(f"{t.name} has no variant {variant!r}; its variants: {sorted(t.variants)}")
        fragments.update(t.variants[variant])
    elif t.variants:
        raise TemplateError(f"{t.name} has variants {sorted(t.variants)}: give --variant")
    for name in values:
        if name in fragments:
            raise TemplateError(f"{name} is fixed by the template (variant {variant}); it takes no host value")
        if name not in PLACEHOLDERS:
            raise TemplateError(f"unknown placeholder {name}")
        if PLACEHOLDERS[name].template:
            raise TemplateError(f"{name} is the template's value (a variant or a value section), not the host's")
    texts: dict[str, str] = {}
    for name, value in fragments.items():
        texts[name] = strip_markers(t.value(name, value[1:]).text)[0] if value.startswith("@") else value
        nested = [n for n in _PLACEHOLDER.findall(texts[name]) if n in fragments]
        if nested:
            raise TemplateError(f"the value of {name} uses the template's own placeholders {nested}")
    body = _PLACEHOLDER.sub(lambda m: texts.get(m.group(1), m.group(0)), strip_markers(t.body.text)[0])
    needed = set(_PLACEHOLDER.findall(body))
    missing = sorted(needed - set(values))
    if missing:
        raise TemplateError(f"{t.name}{' ' + variant if variant else ''}: no value for {missing}")
    extra = sorted(set(values) - needed)
    if extra:
        raise TemplateError(f"{t.name}{' ' + variant if variant else ''}: the prompt has no placeholder {extra}")
    for name in sorted(values):
        _check_value(name, values[name], values)
    prompt = _PLACEHOLDER.sub(lambda m: values[m.group(1)], body)
    for what, pat in _FORBIDDEN_IN_PROMPT:
        if pat.search(prompt):
            raise TemplateError(f"{t.name}: the prompt names {what}")
    bad_cli = cli_problems(prompt)
    if bad_cli:
        raise TemplateError(f"{t.name}: the prompt names {'; '.join(bad_cli)} (the natural-agent audit allows only "
                            f"{CLI_PATH} {'|'.join(CLI_SUBCOMMANDS)} on the agent's own files)")
    return prompt


def cli_problems(prompt: str) -> list[str]:
    """Where a prompt names the study's CLI otherwise than the natural-agent audit allows: by a relative path, or with a
    subcommand other than :data:`CLI_SUBCOMMANDS` (a mention followed by a comma, as in the preamble, names no call)."""
    out = []
    prefix = CLI_PATH[:-len(".venv/bin/tracecontract")]
    for m in re.finditer(r"\.venv/bin/tracecontract", prompt):
        if not prompt[:m.start()].endswith(prefix):
            out.append(f"the CLI by a relative path, at offset {m.start()}")
            continue
        nm = re.match(r",|\s+(\S+)", prompt[m.end():])
        if nm is None or (nm.group(0) != "," and nm.group(1) not in CLI_SUBCOMMANDS):
            out.append(f"a CLI call other than {' or '.join(CLI_SUBCOMMANDS)}, at offset {m.start()}")
    return out


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sent_prompt(text: str) -> str:
    """The prompt in a sent-prompt file: the computed task inside a workflow agent's harness frame (without the frame
    and the two-space indent, as scripts/agent_run_record.py reads it), else the file's text, verbatim."""
    if not TASK_FRAME.match(text):
        return text
    at = text.find(TASK_MARKER)
    if at < 0:
        raise TemplateError("the file has a computed-task frame line but no line introducing the task text")
    body = text[at + len(TASK_MARKER):]
    if body and not body.startswith("\n"):
        raise TemplateError("the computed-task frame does not end its line before the task text")
    lines = []
    for n, line in enumerate(body[1:].split("\n"), 1):
        if line.startswith(INDENT):
            lines.append(line[len(INDENT):])
        elif line == "":
            lines.append(line)
        else:
            raise TemplateError(f"line {n} of the computed task text is not indented as the harness indents it")
    return "\n".join(lines)


def first_difference(a: str, b: str) -> str:
    """Where two texts first differ, by line and column (no text is repeated)."""
    la, lb = a.split("\n"), b.split("\n")
    for n, (x, y) in enumerate(zip(la, lb, strict=False), 1):
        if x != y:
            col = next((i for i, (p, q) in enumerate(zip(x, y, strict=False)) if p != q), min(len(x), len(y)))
            return f"line {n}, column {col + 1}"
    return f"line {min(len(la), len(lb)) + 1} (one text has {abs(len(la) - len(lb))} more line(s))"


# --------------------------------------------------------------------------- command line


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return p.name


def _values(a: argparse.Namespace) -> dict[str, str]:
    values: dict[str, str] = {}

    def put(name: str, value: str, how: str) -> None:
        if name in values:
            raise TemplateError(f"{name} is given twice ({how})")
        values[name] = value

    if a.values:
        data = json.loads(Path(a.values).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise TemplateError(f"{a.values}: an object of strings expected")
        for k, v in data.items():
            put(k, v, "--values")
    for item in a.set or []:
        name, sep, value = item.partition("=")
        if not sep:
            raise TemplateError(f"--set {item!r}: NAME=VALUE expected")
        put(name, value, "--set")
    for item in a.set_file or []:
        name, sep, value = item.partition("=")
        if not sep:
            raise TemplateError(f"--set-file {item!r}: NAME=FILE expected")
        put(name, Path(value).read_text(encoding="utf-8"), "--set-file")
    return values


def cmd_render(a: argparse.Namespace) -> int:
    t = parse_template(Path(a.template))
    prompt = render(t, variant=a.variant, values=_values(a))
    digest = sha256_text(prompt)
    ok = True
    report: dict[str, Any] = {"template": t.name, "template_file": _rel(t.path), "template_sha256": t.sha256,
                              "variant": a.variant, "prompt_sha256": digest}
    if a.out:
        out = Path(a.out)
        if out.exists():
            raise TemplateError(f"{out} exists; the prompt is written to a new file only")
        out.write_text(prompt, encoding="utf-8")
        report["written"] = str(out)
    if a.verify:
        sent = sent_prompt(Path(a.verify).read_text(encoding="utf-8"))
        same = sent == prompt
        report["verify"] = "equal" if same else f"different from the rendering at {first_difference(sent, prompt)}"
        ok &= same
    if a.record:
        rec = json.loads(Path(a.record).read_text(encoding="utf-8"))
        want = rec.get("prompt_sha256") if isinstance(rec, dict) else None
        report["record"] = "equal" if want == digest else f"prompt_sha256 {want!r} is not the rendering's"
        ok &= want == digest
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


def summarize(directory: Path, source_dirs: list[Path], *, allow_missing: bool = False) -> list[dict[str, Any]]:
    """The summary of every template in ``directory`` (see :func:`compare_template`)."""
    return [compare_template(t, source_dirs, allow_missing=allow_missing) for t in load_templates(directory)]


def _summary_lines(rows: list[dict[str, Any]]) -> Iterator[str]:
    for r in rows:
        yield f"{r['name']}  {r['file']}"
        yield f"  sha256 {r['sha256']}"
        yield f"  source {r['source_file']} (sha256 {r['source_sha256'][:16]}...): {r.get('source')}"
        for s in r["sections"]:
            per: dict[str, list[int]] = {}
            for d in s["deviations"]:
                acc = per.setdefault(d["letters"], [0, 0, 0])
                acc[0] += 1
                acc[1] += d["removed"]
                acc[2] += d["added"]
            devs = "; ".join(f"({k}) {n} place(s), -{rm} +{ad} words" for k, (n, rm, ad) in sorted(per.items()))
            yield (f"  {s['section']} <- {s['source_spec'] or 'new text'}: {s['source_words']} source words, "
                   f"{s['kept_words']} kept word for word" + (f"; {devs}" if devs else ""))
        for k, v in r.get("mapped_deviations", {}).items():
            yield f"  source-map {k}: deviation ({v})"
        for n in r["notes"]:
            yield f"  note: {n}"
        for p in r["problems"]:
            yield f"  PROBLEM: {p}"
        yield f"  result: {'ok' if not r['problems'] else 'FAILED'}"


def cmd_summary(a: argparse.Namespace) -> int:
    rows = summarize(Path(a.templates), [Path(d) for d in a.source_dir or []], allow_missing=a.allow_missing_sources)
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        for line in _summary_lines(rows):
            print(line)
    return 0 if all(not r["problems"] for r in rows) else 1


def rendering_version() -> dict[str, Any]:
    """The sha256 of the PR-thread renderer's fixed banner and block headers (WP-B), and the session-events format."""
    from tracecontract import tasks
    from tracecontract.ingest.github_pr import PR_THREAD_BANNER, PR_THREAD_HEADERS

    return {"banner_sha256": sha256_text(PR_THREAD_BANNER),
            "headers_sha256": sha256_text(json.dumps(PR_THREAD_HEADERS, sort_keys=True, ensure_ascii=False)),
            "headers": dict(PR_THREAD_HEADERS), "session_events_format": getattr(tasks, "SESSION_EVENTS_FORMAT", None)}


def cmd_rendering(a: argparse.Namespace) -> int:
    print(json.dumps(rendering_version(), indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render", help="fill a template in, print the prompt's sha256, and check a sent prompt")
    p.add_argument("template")
    p.add_argument("--variant")
    p.add_argument("--set", action="append", metavar="NAME=VALUE")
    p.add_argument("--set-file", action="append", metavar="NAME=FILE")
    p.add_argument("--values", metavar="FILE.json")
    p.add_argument("--out", metavar="FILE", help="write the prompt to this new file")
    p.add_argument("--verify", metavar="PROMPT_FILE", help="check that this sent prompt equals the rendering")
    p.add_argument("--record", metavar="FILE", help="check that this generation record's prompt_sha256 is the rendering's")
    p.set_defaults(fn=cmd_render)
    p = sub.add_parser("summary", help="every template's sha256 and its word-level comparison with its source")
    p.add_argument("--templates", default=str(TEMPLATES))
    p.add_argument("--source-dir", action="append", metavar="DIR",
                   help="a directory holding a source script outside the repository (looked up by file name)")
    p.add_argument("--allow-missing-sources", action="store_true",
                   help="report a source outside the repository that no --source-dir holds as not compared, not as a "
                        "failure")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_summary)
    p = sub.add_parser("rendering", help="the sha256 of the PR-thread banner and headers")
    p.set_defaults(fn=cmd_rendering)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (TemplateError, SourceError, OSError, ValueError) as exc:
        print(f"check_natural_prompts: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
