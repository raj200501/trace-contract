"""Keep the B3 (diff_derived) tests that fail on the base and pass on the reference, and remove the others.

Usage: python scripts/select_b3_tests.py TESTS_DIR --reference R1.json R2.json R3.json --noop N.json
                                         [--out FILE] [--dry-run] [--accept-grades-without-statuses]

TESTS_DIR is ``<task>/verifiers/<verifier id>/tests`` of a diff_derived verifier whose spec, built from exactly these
files and not frozen, was graded after it was built: R1 to R3 are three single grades of the task's reference
candidate and N a single grade of its development no-op, each the JSON that ``tracecontract grade`` prints without
``--repeats``. Single grades are needed because a repeated grade keeps the check statuses of its last run only. Both
candidates are in the development split. (Protocol §19.7 names the gradings made before building stops: the audit
loops, the reference checks and the labeler. The decision-log entry that fixes the natural recipe, planned as D61,
counts these selection grades as development grading under it.)

The rule, per test: it is kept if and only if its status is ``passed`` in each of the three reference grades and
``failed`` or ``error`` in the no-op grade. Every other test is removed, located with the ``ast`` module: its function
with its decorators (or its class, when nothing else is left in the class), the comment lines directly above it at
its indentation and the blank lines before them; and its key in the file's ``CHECK_REQUIREMENTS`` dict, where an
entry alone on its lines goes with those lines, and otherwise (or when that would not parse) the dict is rewritten
from the source text of the entries it keeps (comments inside it are then lost). The rest of each file stays byte for
byte as written. The edited files are checked in a temporary copy before anything is written: they parse, the tests
left are exactly the kept ones, the requirement keys of the kept tests are unchanged and no key of a removed test is
left, no code left refers to a removed test (by its name, by an attribute named after it, or by a string equal to
its id, as a dependency marker does), and ``lint-tests`` finds nothing. Then the files are written, each through a
temporary file and a rename, and ``selection.json`` (by default in the verifier directory, beside ``spec.json`` and
outside the tests) records the rule, the grades by sha256, every test's statuses, what was kept, what was removed and
why. If writing fails partway, every file written is put back as it was and no record is left. Check messages and
diagnostics are never copied: the record holds test ids, statuses, outcomes and hashes. Then the host rebuilds the
spec, confirms with the reference (``--repeats 3``) and the development no-op, and freezes.

If no test is kept, the tests are left as they are, so that no verifier without checks is made; ``selection.json``
records that B3 is unavailable for the family, and the exit status is 3. That verifier is not frozen.

Each grade is checked before it is used:
* a repeated grade is refused when it shows it: an unresolved outcome (its runs disagreed) or a diagnostic of a run
  after the first (``[run 1] ...``). A repeated grade whose runs agree and add no diagnostic, as passes and task
  failures do, cannot be told from a single grade by its JSON; its check statuses are then those of its last run,
  which is itself one single run of the candidate;
* a grade without check statuses (a timeout, a grader that did not complete or left no results, a collection error,
  a rejected patch) says nothing about any one test. It is refused unless ``--accept-grades-without-statuses`` is
  given; then no test passes that grade's part of the rule, so B3 is unavailable, and the record names the grade. An
  environment failure is always refused;
* a grade that started before the verifier's ``spec.json`` was last written was made on an earlier build, and is
  refused;
* the same grade given twice, as the same file or saved again (the same start, end and log hash), is refused.

Refused, with exit status 2 and nothing written: a tests directory outside that layout or without a spec; a spec
that is frozen, not diff_derived or not process-separated, or whose content hash or checks no longer match the files;
a grade that is not of this task and verifier, or of another harness version, or refused as above; grades whose
checks differ from the tests; a reference grade of a candidate that is not the development reference, or a no-op
grade of a candidate that is not the development no-op; a ``CHECK_REQUIREMENTS`` that cannot be edited by its syntax
tree; a result that refers to a removed test or does not lint clean; an existing selection record; a record location
(``--out``) in a verifiers directory other than the default place, or in the repository where git does not ignore it
(the record holds generated test ids).
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import symtable
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from tracecontract import roots
from tracecontract.sandbox.docker_runner import HARNESS_VERSION
from tracecontract.schemas import (
    Candidate,
    CandidateOrigin,
    Isolation,
    Outcome,
    Split,
    TaskManifest,
    VerificationResult,
    VerifierCondition,
    VerifierSpec,
)
from tracecontract.store import load
from tracecontract.verifier import (
    discover_checks,
    hash_test_dir,
    lint_process_separated,
    requirement_map_from_tests,
)

SCHEMA = "b3-selection:v1"
N_REFERENCE = 3
PASS_ON_REFERENCE = "passed"
FAIL_ON_NOOP = ("failed", "error")
RULE = ("a test is kept iff its status is passed in each of three single grades of the development reference and "
        "failed or error in a single grade of the development no-op; every other test is removed with its "
        "CHECK_REQUIREMENTS key")
ACCEPT_WITHOUT_STATUSES = "--accept-grades-without-statuses"
_REPEATED_RUN = re.compile(r"^\[run [1-9]\d*\] ")
_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)


class SelectionError(ValueError):
    """The inputs do not allow a selection, or the selected tests would not be valid; nothing is written."""


class WrittenError(RuntimeError):
    """Writing the selected tests or the record failed, or the written tests do not hash as they did when checked
    (a concurrent change?); the message says what was put back."""


@dataclass(frozen=True)
class Grade:
    role: str  # "reference" or "noop"
    n: int
    sha256: str
    result: VerificationResult

    @property
    def name(self) -> str:
        return f"{self.role} grade {self.n}"

    @property
    def statuses(self) -> dict[str, str]:
        return {c.check_id: c.status for c in self.result.checks}

    @property
    def run(self) -> tuple[str, str, str] | None:
        """What tells one grade from another when its file is saved again: its start, its end and its log's hash."""
        r = self.result
        return (r.started_at, r.finished_at, r.log_sha256) if r.log_sha256 else None


@dataclass(frozen=True)
class Verifier:
    tests: Path
    task_dir: Path
    task: TaskManifest
    spec: VerifierSpec
    spec_written: datetime  # when spec.json was last written (to the second): no grade of it can be older
    checks: list[str]
    candidates: dict[str, Candidate]


# --------------------------------------------------------------------------- inputs


def load_grade(path: Path, role: str, n: int) -> Grade:
    try:
        data = path.read_bytes()
        result = VerificationResult.model_validate_json(data)
    except (OSError, ValidationError) as exc:
        raise SelectionError(f"{path.name}: not a grade result as tracecontract grade prints it "
                             f"({exc.__class__.__name__})") from None
    return Grade(role, n, hashlib.sha256(data).hexdigest(), result)


def _read[M: BaseModel](path: Path, cls: type[M]) -> M:
    try:
        return load(path, cls)
    except (OSError, ValidationError) as exc:
        raise SelectionError(f"{path.name}: not a readable {cls.__name__} ({exc.__class__.__name__})") from None


def load_verifier(tests: Path) -> Verifier:
    tests = tests.resolve()
    if not tests.is_dir():
        raise SelectionError(f"{tests.name}: not a directory")
    vdir = tests.parent
    task_dir = vdir.parent.parent
    if vdir.parent.name != "verifiers" or not (task_dir / "task.json").is_file():
        raise SelectionError("the tests directory must be <task>/verifiers/<verifier id>/tests")
    if not (vdir / "spec.json").is_file():
        raise SelectionError(f"{vdir.name}: no spec.json; build the verifier from these tests and grade it first")
    task = _read(task_dir / "task.json", TaskManifest)
    spec = _read(vdir / "spec.json", VerifierSpec)
    spec_written = datetime.fromtimestamp(int((vdir / "spec.json").stat().st_mtime), UTC)
    if spec.condition != VerifierCondition.diff_derived:
        raise SelectionError(f"{spec.verifier_id}: condition {spec.condition.value}; the selection is for B3 "
                             "(diff_derived) only")
    if spec.isolation != Isolation.process_separated:
        raise SelectionError(f"{spec.verifier_id}: not process-separated")
    if spec.frozen:
        raise SelectionError(f"{spec.verifier_id}: frozen; a frozen verifier is never changed")
    if spec.task_id != task.task_id or (task_dir / spec.test_dir).resolve() != tests:
        raise SelectionError(f"{spec.verifier_id}: the spec is not of this task and tests directory")
    if hash_test_dir(tests) != spec.content_sha256:
        raise SelectionError(f"{spec.verifier_id}: the tests changed since the spec was built; build and grade again")
    try:
        checks = discover_checks(tests)
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise SelectionError(f"{spec.verifier_id}: a test file does not parse ({exc.__class__.__name__})") from None
    twice = sorted({c for c in checks if checks.count(c) > 1})
    if twice:
        raise SelectionError(f"test names defined twice: {twice}")
    if set(checks) != {c.check_id for c in spec.checks}:
        raise SelectionError(f"{spec.verifier_id}: the spec's checks are not the tests in the directory; build again")
    candidates = {}
    for rel in task.candidates:
        cand = _read(task_dir / rel, Candidate)
        candidates[cand.candidate_id] = cand
    return Verifier(tests, task_dir, task, spec, spec_written, checks, candidates)


def _started(g: Grade) -> datetime:
    try:
        t: datetime | None = datetime.fromisoformat(g.result.started_at)
    except ValueError:
        t = None
    if t is None or t.tzinfo is None:
        raise SelectionError(f"{g.name}: its start {g.result.started_at!r} is not an ISO 8601 time with a time zone")
    return t


def check_grades(v: Verifier, refs: list[Grade], noop: Grade, *, accept_without_statuses: bool = False) -> list[Grade]:
    """Refuse grades that are not three single grades of the reference and one of the development no-op of ``v``,
    made after its spec was written. Returns the grades without check statuses, which are refused unless
    ``accept_without_statuses``."""
    if len(refs) != N_REFERENCE:
        raise SelectionError(f"{N_REFERENCE} reference grades are needed (got {len(refs)})")
    grades = refs + [noop]
    runs = [g.run for g in grades if g.run is not None]
    if len({g.sha256 for g in grades}) != len(grades) or len(set(runs)) != len(runs):
        raise SelectionError("the same grade is given twice (the same file, or the same result saved again: the same "
                             "start, end and log hash); three separate single grades of the reference are needed")
    without = []
    for g in grades:
        r = g.result
        if r.task_id != v.task.task_id or r.verifier_id != v.spec.verifier_id:
            raise SelectionError(f"{g.name} is of {r.task_id}/{r.verifier_id}, not {v.task.task_id}/{v.spec.verifier_id}")
        if r.harness_version != HARNESS_VERSION:
            raise SelectionError(f"{g.name} was graded under {r.harness_version}, not {HARNESS_VERSION}")
        if _started(g) < v.spec_written:
            raise SelectionError(f"{g.name} started at {r.started_at}, before the verifier's spec.json was last written "
                                 f"({v.spec_written.isoformat()}): it is a grade of an earlier build; grade again")
        if r.outcome == Outcome.unresolved or any(_REPEATED_RUN.match(d) for d in r.diagnostics):
            raise SelectionError(f"{g.name} comes from repeated runs, which keep the statuses of the last run only; "
                                 "give single grades (tracecontract grade without --repeats)")
        if r.outcome == Outcome.environment_failure:
            raise SelectionError(f"{g.name} is an environment failure, which says nothing about the tests; grade again")
        if not r.checks:
            without.append(g)
        elif set(g.statuses) != set(v.checks):
            raise SelectionError(f"{g.name} graded other checks than the tests in the directory")
    ref_ids = sorted({g.result.candidate_id for g in refs})
    if len(ref_ids) != 1:
        raise SelectionError(f"the reference grades are of different candidates: {ref_ids}")
    ref, nop = v.candidates.get(ref_ids[0]), v.candidates.get(noop.result.candidate_id)
    if ref is None or ref.origin != CandidateOrigin.reference or ref.split != Split.dev:
        raise SelectionError(f"{ref_ids[0]} is not the task's development reference")
    if nop is None or nop.origin != CandidateOrigin.noop or nop.split != Split.dev:
        raise SelectionError(f"{noop.result.candidate_id} is not the task's development no-op (protocol §19.7: no "
                             "natural verifier is graded on a held-out candidate before building stops)")
    if without and not accept_without_statuses:
        listed = ", ".join(f"{g.name} ({g.result.outcome.value})" for g in without)
        raise SelectionError(f"no check statuses in {listed}: such a grade (a timeout, a grader that did not complete "
                             "or left no results, a collection error, a rejected patch) says nothing about any one "
                             f"test; grade again, or give {ACCEPT_WITHOUT_STATUSES} to let no test pass its part of "
                             "the rule (B3 is then unavailable)")
    return without


def select(v: Verifier, refs: list[Grade], noop: Grade) -> list[dict[str, Any]]:
    """Each test with its statuses, whether it is kept and, if not, why."""
    rows = []
    for cid in v.checks:
        ref = [g.statuses.get(cid) for g in refs]
        st = noop.statuses.get(cid)
        why = []
        if any(s != PASS_ON_REFERENCE for s in ref):
            why.append("not passed in every reference grade")
        if st not in FAIL_ON_NOOP:
            why.append("not failed (or error) on the development no-op")
        rows.append({"check_id": cid, "reference": ref, "noop": st, "kept": not why, "why": why})
    return rows


# --------------------------------------------------------------------------- editing by the syntax tree


def _line_starts(data: bytes) -> list[int]:
    starts = [0]
    for line in data.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _at(starts: list[int], line: int, col: int) -> int:
    return starts[line - 1] + col  # ast columns are UTF-8 byte offsets


def _end(node: ast.AST) -> tuple[int, int]:
    end_line, end_col = getattr(node, "end_lineno", None), getattr(node, "end_col_offset", None)
    assert end_line is not None and end_col is not None
    return end_line, end_col


def _lead(line: bytes) -> bytes:
    return line[:len(line) - len(line.lstrip(b" \t"))]


def _removal(lines: list[bytes], starts: list[int], node: ast.stmt, floor: int) -> tuple[int, int, bytes]:
    """The span to remove for a statement: its lines with its decorators, the comment lines directly above it at its
    indentation, and the blank lines above those, never above line ``floor`` (where the statement before it ends, or
    its class's first line). The lines between two statements hold no code and no string, so nothing else goes."""
    first = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
    indent, top = _lead(lines[first - 1]), first
    while top - 1 > floor and _lead(lines[top - 2]) == indent and lines[top - 2].lstrip().startswith(b"#"):
        top -= 1
    while top - 1 > floor and not lines[top - 2].strip():
        top -= 1
    return starts[top - 1], starts[_end(node)[0]], b""


def _source(data: bytes, starts: list[int], node: ast.expr) -> str:
    end_line, end_col = _end(node)
    return data[_at(starts, node.lineno, node.col_offset):_at(starts, end_line, end_col)].decode("utf-8")


def _requirements_value(node: ast.stmt) -> ast.expr | None:
    """The value of a top-level ``CHECK_REQUIREMENTS = ...`` (as ``requirement_map_from_tests`` reads it)."""
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CHECK_REQUIREMENTS" for t in node.targets):
        return node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "CHECK_REQUIREMENTS":
        return node.value
    return None


def _dict_edits(data: bytes, starts: list[int], value: ast.Dict, remove: set[str], *, by_line: bool,
                rel: str) -> list[tuple[int, int, bytes]]:
    """The edits that remove the keys in ``remove`` from a ``CHECK_REQUIREMENTS`` dict literal.

    ``by_line``: in a dict over several lines, an entry alone on its lines (with its comma and a comment after it) is
    removed with those lines, so the rest stays as written. Otherwise, or when an entry shares a line, the dict is
    rewritten from the source text of the entries it keeps."""
    pairs = [(k, v) for k, v in zip(value.keys, value.values)]
    keys = [k.value if isinstance(k, ast.Constant) and isinstance(k.value, str) else None for k, _ in pairs]
    if None in keys:
        raise SelectionError(f"{rel}: CHECK_REQUIREMENTS has a key that is not a string literal")
    gone = [i for i, key in enumerate(keys) if key in remove]
    if not gone:
        return []
    first_line, (last_line, last_col) = value.lineno, _end(value)
    if by_line and first_line != last_line:
        lines_of: dict[int, set[int]] = {}
        for i, (k, v) in enumerate(pairs):
            assert k is not None
            for ln in range(k.lineno, _end(v)[0] + 1):
                lines_of.setdefault(ln, set()).add(i)
        edits = []
        for i in gone:
            k, v = pairs[i]
            assert k is not None
            v_line, v_col = _end(v)
            before = data[starts[k.lineno - 1]:_at(starts, k.lineno, k.col_offset)]
            after = data[_at(starts, v_line, v_col):starts[v_line]].strip()
            after = after[1:].strip() if after.startswith(b",") else after
            if (before.strip() or (after and not after.startswith(b"#")) or k.lineno <= first_line
                    or v_line >= last_line or any(lines_of[ln] != {i} for ln in range(k.lineno, v_line + 1))):
                break
            edits.append((starts[k.lineno - 1], starts[v_line], b""))
        else:
            return edits
    items = [f"{_source(data, starts, k)}: {_source(data, starts, v)}" for i, (k, v) in enumerate(pairs)
             if i not in gone and k is not None]
    if not items:
        text = "{}"
    elif first_line == last_line:
        text = "{" + ", ".join(items) + "}"
    else:
        text = "{\n" + "".join(f"    {item},\n" for item in items) + "}"
    return [(_at(starts, first_line, value.col_offset), _at(starts, last_line, last_col), text.encode("utf-8"))]


def _requirement_dicts(tree: ast.Module, rel: str) -> list[ast.Dict]:
    out = []
    for node in tree.body:
        value = _requirements_value(node)
        if value is None:
            continue
        if not isinstance(value, ast.Dict):
            raise SelectionError(f"{rel}: CHECK_REQUIREMENTS is not a dict literal, so its keys cannot be removed")
        out.append(value)
    return out


def edit_file(data: bytes, remove: set[str], rel: str, *, by_line: bool = True) -> bytes:
    """``data`` without the tests named in ``remove`` (``test_x`` or ``TestC::test_x``) and their requirement keys."""
    try:
        tree = ast.parse(data, filename=rel)
    except SyntaxError as exc:
        raise SelectionError(f"{rel}: does not parse ({exc.msg})") from None
    lines, starts = data.splitlines(keepends=True), _line_starts(data)
    edits: list[tuple[int, int, bytes]] = []
    found: set[str] = set()
    for n, node in enumerate(tree.body):
        floor = _end(tree.body[n - 1])[0] if n else 0
        if isinstance(node, _FUNCS) and node.name in remove:
            edits.append(_removal(lines, starts, node, floor))
            found.add(node.name)
        elif isinstance(node, ast.ClassDef):
            methods = {k for k, s in enumerate(node.body) if isinstance(s, _FUNCS) and f"{node.name}::{s.name}" in remove}
            found |= {f"{node.name}::{getattr(node.body[k], 'name', '')}" for k in methods}
            if methods and len(methods) == len(node.body):  # nothing else is left in the class: remove it whole
                edits.append(_removal(lines, starts, node, floor))
            else:
                edits += [_removal(lines, starts, node.body[k], _end(node.body[k - 1])[0] if k else node.lineno)
                          for k in sorted(methods)]
    if found != remove:
        raise SelectionError(f"{rel}: tests not found by the syntax tree: {sorted(remove - found)}")
    dicts = _requirement_dicts(tree, rel)
    for value in dicts:
        edits += _dict_edits(data, starts, value, remove, by_line=by_line, rel=rel)
    edits.sort(reverse=True)
    for later, earlier in pairwise(edits):
        if earlier[1] > later[0]:
            raise SelectionError(f"{rel}: overlapping edits")
    out = data
    for start, end, text_bytes in edits:
        out = out[:start] + text_bytes + out[end:]
    try:
        new_dicts = _requirement_dicts(ast.parse(out, filename=rel), rel)
    except SyntaxError as exc:
        if by_line:  # e.g. an entry's comma on the line after it: rewrite the dicts from their entries instead
            return edit_file(data, remove, rel, by_line=False)
        raise SelectionError(f"{rel}: the edited file does not parse ({exc.msg})") from None
    try:
        want = [{k: x for k, x in ast.literal_eval(d).items() if k not in remove} for d in dicts]
        got = [ast.literal_eval(d) for d in new_dicts]
    except ValueError:
        raise SelectionError(f"{rel}: CHECK_REQUIREMENTS holds values that are not literals") from None
    if got != want:
        if by_line:  # an entry's lines held more than the entry: rewrite the dicts from their entries instead
            return edit_file(data, remove, rel, by_line=False)
        raise SelectionError(f"{rel}: the edited CHECK_REQUIREMENTS are not those of the kept tests")
    return out


def _global_reads(text: str, rel: str) -> tuple[set[str], set[str]]:
    """The names that a file's code reads as globals, in any scope, and the names bound at its top level."""
    top = symtable.symtable(text, rel, "exec")
    reads = {s.get_name() for s in top.get_symbols() if s.is_referenced()}
    todo = list(top.get_children())
    while todo:
        table = todo.pop()
        reads |= {s.get_name() for s in table.get_symbols() if s.is_referenced() and s.is_global()}
        todo += table.get_children()
    return reads, {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported()}


def dangling_references(tests: Path, removed: dict[str, set[str]]) -> list[str]:
    """Where the files under ``tests`` (the edited copy) still refer to a removed test, as ``file: name``.

    In the file that defined it: a global read of a removed function or of an emptied class (a call, an alias, a
    decorator argument), or an attribute named after a removed test or class that no definition left in the file has
    (``self.test_x()``, ``test_x.attr = ...``). In any file: a string equal to its id (``test_x``, ``TestC::test_x``
    in its own file, ``file.py::test_x`` anywhere), as a dependency marker names a test. A kept test would then fail
    with a NameError, or be skipped, at the confirming grade."""
    ids = {f"{rel}::{local}" for rel, names in removed.items() for local in names}
    found = []
    for f in sorted(tests.rglob("*.py")):
        rel = f.relative_to(tests).as_posix()
        try:
            text = f.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=rel)
            reads, bound = _global_reads(text, rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            raise SelectionError(f"{rel}: does not parse ({exc.__class__.__name__})") from None
        local = removed.get(rel, set())
        hits = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in ids | local}
        if local:
            outer = {name.split("::")[0] for name in local}  # removed functions, and the classes of removed methods
            names = outer | {name.split("::")[-1] for name in local}
            defined = {n.name for n in ast.walk(tree) if isinstance(n, (*_FUNCS, ast.ClassDef))}
            hits |= (reads & outer) - bound
            hits |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in names - defined}
        found += [f"{rel}: {h}" for h in sorted(hits)]
    return found


def edited_files(v: Verifier, rows: list[dict[str, Any]]) -> tuple[dict[str, bytes], str]:
    """The new content of every file that loses a test, checked in a temporary copy; and the new tests hash."""
    remove: dict[str, set[str]] = {}
    for row in rows:
        if not row["kept"]:
            rel, _, local = row["check_id"].partition("::")
            remove.setdefault(rel, set()).add(local)
    new = {rel: edit_file((v.tests / rel).read_bytes(), names, rel) for rel, names in sorted(remove.items())}
    kept = [row["check_id"] for row in rows if row["kept"]]
    removed = {row["check_id"] for row in rows if not row["kept"]}
    with tempfile.TemporaryDirectory(prefix="b3_select_") as tmp:
        copy = Path(tmp) / "tests"
        shutil.copytree(v.tests, copy, ignore=shutil.ignore_patterns("__pycache__"))
        for rel, data in new.items():
            (copy / rel).write_bytes(data)
        if discover_checks(copy) != kept:
            raise SelectionError("after the edit the tests are not exactly the kept ones")
        before, after = requirement_map_from_tests(v.tests), requirement_map_from_tests(copy)
        if set(after) & removed or {k: x for k, x in before.items() if k not in removed} != after:
            raise SelectionError("after the edit the requirement keys are not those of the kept tests")
        dangling = dangling_references(copy, remove)
        if dangling:
            raise SelectionError("after the edit, code left in the tests refers to removed tests (a kept test would fail "
                                 "or be skipped at the confirming grade): " + "; ".join(dangling))
        issues = lint_process_separated(copy)
        if issues:
            raise SelectionError("the selected tests do not lint clean: "
                                 + "; ".join(f"{i.file}:{i.line} {i.code}" for i in issues))
        return new, hash_test_dir(copy)


# --------------------------------------------------------------------------- writing


def _git_ignored(path: Path, repo: Path) -> bool | None:
    """Whether the git work tree at ``repo`` ignores ``path`` (a tracked path is not ignored); None when git cannot
    answer."""
    try:
        rel = path.relative_to(repo).as_posix()
        proc = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--", rel or "."], capture_output=True,
                              env={k: x for k, x in os.environ.items() if not k.startswith("GIT_")}, timeout=60,
                              check=False)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return None
    return {0: True, 1: False}.get(proc.returncode)


def record_location_problem(target: Path, default: Path, repo: Path = roots.REPO) -> str | None:
    """Why the selection record may not be written at ``target`` (resolved), or None.

    It may lie at ``default`` (beside the verifier's spec.json) or outside every verifiers directory, so that no
    verifier's files change (a tests directory is hashed); and never in the repository where git does not ignore it,
    since it holds generated test ids, which stay out of git (natural tasks live under the ignored data/natural/)."""
    if target != default and any(a.name == "verifiers" for a in target.parents):
        return ("--out lies in a task's verifiers directory: the record goes beside the verifier's spec.json (the "
                "default) or outside every verifiers directory, so that no verifier's files change")
    repo = repo.resolve()
    ignored = _git_ignored(target, repo) if target == repo or repo in target.parents else True
    if not ignored:
        where = "git does not ignore it" if ignored is False else "git cannot tell whether it ignores it"
        return (f"the record would lie in the repository where {where}, and it holds generated test ids, which stay "
                "out of git (a natural task lives under the ignored data/natural/)")
    return None


def _replace(path: Path, data: bytes, scratch: Path) -> None:
    """Write ``data`` to ``path`` through a temporary file in ``scratch`` (on the same file system) and a rename."""
    fd, tmp = tempfile.mkstemp(prefix=".b3_select_", dir=scratch)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def apply(v: Verifier, new: dict[str, bytes], after: str, target: Path, record_text: str) -> None:
    """Write the selected tests and the record as one step. The record file is claimed first; on any failure, and
    when the tests then do not hash as they did when checked, every test file written is put back as it was and the
    record is removed (``WrittenError``, which says so)."""
    originals = {rel: (v.tests / rel).read_bytes() for rel in new}
    try:
        fh = target.open("x", encoding="utf-8")
    except FileExistsError:
        raise SelectionError(f"{target.name} exists: a selection was already made for this verifier") from None
    done: list[str] = []
    try:
        for rel, data in new.items():
            _replace(v.tests / rel, data, v.tests.parent)  # the temporary file lies outside the hashed tests
            done.append(rel)
        if hash_test_dir(v.tests) != after:
            raise WrittenError("the written tests do not hash as they did when checked (a concurrent change?)")
        fh.write(record_text)
        fh.close()
    except BaseException as exc:
        with contextlib.suppress(OSError):
            fh.close()
        with contextlib.suppress(OSError):
            target.unlink()
        left = []
        for rel in done:
            try:
                _replace(v.tests / rel, originals[rel], v.tests.parent)
            except OSError:
                left.append(rel)
        if not isinstance(exc, (OSError, WrittenError)):
            raise
        why = str(exc) if isinstance(exc, WrittenError) else f"writing failed ({exc.__class__.__name__}: {exc})"
        state = (f"{left} could not be put back and stay edited: restore them by hand" if left else
                 "every test file written was put back as it was")
        record = (f"the unfinished record {target.name} could not be removed: remove it" if target.exists() else
                  "no selection record was written")
        raise WrittenError(f"{why}; {state}; {record}") from None


# --------------------------------------------------------------------------- command line


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def run(tests: Path, reference: list[Path], noop: Path, *, out: Path | None = None, dry_run: bool = False,
        accept_without_statuses: bool = False) -> tuple[int, dict]:
    """Select and (unless ``dry_run``) apply; returns the exit status and the selection record."""
    tests = tests.resolve()
    default = tests.parent / "selection.json"
    target = out.resolve() if out is not None else default
    problem = record_location_problem(target, default)
    if problem:
        raise SelectionError(problem)
    if not dry_run and (target.exists() or (out is not None and out.is_symlink())):
        raise SelectionError(f"{target.name} exists: a selection was already made for this verifier")
    v = load_verifier(tests)
    refs = [load_grade(p, "reference", n) for n, p in enumerate(reference, 1)]
    nop = load_grade(noop, "noop", 1)
    without = check_grades(v, refs, nop, accept_without_statuses=accept_without_statuses)
    rows = select(v, refs, nop)
    kept = [r["check_id"] for r in rows if r["kept"]]
    removed = [r["check_id"] for r in rows if not r["kept"]]
    new, after = edited_files(v, rows) if kept else ({}, v.spec.content_sha256)
    record = {
        "schema": SCHEMA, "rule": RULE, "task_id": v.task.task_id, "verifier_id": v.spec.verifier_id,
        "condition": v.spec.condition.value, "tests_dir": v.spec.test_dir,
        "tests_sha256_before": v.spec.content_sha256, "tests_sha256_after": after,
        "reference_candidate": refs[0].result.candidate_id, "noop_candidate": nop.result.candidate_id,
        "grades": [{"role": g.role, "n": g.n, "file_sha256": g.sha256, "outcome": g.result.outcome.value,
                    "started_at": g.result.started_at, "finished_at": g.result.finished_at,
                    "harness_version": g.result.harness_version, "log_sha256": g.result.log_sha256,
                    "n_statuses": len(g.result.checks)} for g in refs + [nop]],
        "grades_without_statuses": [g.name for g in without],
        "tests": rows, "kept": kept, "removed": removed,
        "applied": bool(kept) and not dry_run, "b3_available": bool(kept), "selected_at": _now(),
        "next": ("rebuild the spec from the selected tests (build-verifier), confirm with a grade of the reference "
                 "with --repeats 3 and a grade of the development no-op, then freeze" if kept else
                 "no test is kept: B3 is unavailable for this family; the tests were left as they were; do not freeze "
                 "this verifier, which fails the selection rule, and keep it out of the run"),
    }
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        apply(v, new, after, target, json.dumps(record, indent=2, sort_keys=True) + "\n")
    return (0 if kept else 3), record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="select_b3_tests.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("tests", type=Path, help="<task>/verifiers/<verifier id>/tests of the diff_derived verifier")
    ap.add_argument("--reference", nargs=N_REFERENCE, type=Path, required=True, metavar="GRADE",
                    help="three single grades of the development reference (tracecontract grade JSON)")
    ap.add_argument("--noop", type=Path, required=True, metavar="GRADE", help="a single grade of the development no-op")
    ap.add_argument("--out", type=Path, help="the selection record (default: selection.json in the verifier directory)")
    ap.add_argument("--dry-run", action="store_true", help="print the selection, write nothing")
    ap.add_argument(ACCEPT_WITHOUT_STATUSES, dest="accept_without_statuses", action="store_true",
                    help="use a grade without check statuses (no test then passes its part of the rule, so B3 is "
                         "unavailable) instead of refusing it")
    a = ap.parse_args(argv)
    try:
        status, record = run(a.tests, a.reference, a.noop, out=a.out, dry_run=a.dry_run,
                             accept_without_statuses=a.accept_without_statuses)
    except SelectionError as exc:
        print(f"select_b3_tests: refused, nothing written: {exc}", file=sys.stderr)
        return 2
    except WrittenError as exc:
        print(f"select_b3_tests: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:  # reading the inputs or making the temporary copy, before any file of the task is written
        print(f"select_b3_tests: refused, nothing written: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2
    for name in record["grades_without_statuses"]:
        print(f"select_b3_tests: {name} has no check statuses ({ACCEPT_WITHOUT_STATUSES}), so no test passes its part "
              "of the rule", file=sys.stderr)
    if not record["b3_available"]:
        print(f"select_b3_tests: no test is kept, so B3 is unavailable for {record['task_id']}: do not freeze "
              f"{record['verifier_id']}", file=sys.stderr)
    print(json.dumps({"task_id": record["task_id"], "verifier_id": record["verifier_id"], "kept": len(record["kept"]),
                      "removed": len(record["removed"]), "applied": record["applied"],
                      "b3_available": record["b3_available"], "dry_run": a.dry_run,
                      **({"tests": record["tests"]} if a.dry_run else {}), "next": record["next"]}, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
