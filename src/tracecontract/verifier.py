"""Verifier specs: hashing, check discovery, linting, and freezing.

A verifier is a directory of pytest files plus a :class:`VerifierSpec`. For the
process-separated isolation level, tests may touch candidate code only through
``tc_sandbox.run_python`` / ``tc_sandbox.run_cmd``. :func:`lint_process_separated`
enforces the parts of that rule that can be checked statically:

* no ``import`` of anything except the standard library, ``pytest``,
  ``hypothesis`` and ``tc_sandbox`` (so candidate modules are never imported into
  the grader process);
* no writes to the candidate workspace or the results directory;
* every test calls the sandbox, and every sandbox result is checked by more than
  ``r.ok`` alone (to limit no-exception-only checks, see tc_sandbox residual risk).
"""

from __future__ import annotations

import ast
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from .schemas import CheckSpec, GenerationRecord, Isolation, VerifierCondition, VerifierSpec

ALLOWED_IMPORTS = {"pytest", "hypothesis", "tc_sandbox"} | set(sys.stdlib_module_names)
FORBIDDEN_PATH_PREFIXES = ("/work", "/results", "/mnt/candidate")


def hash_test_dir(test_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(test_dir.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(test_dir).as_posix().encode() + b"\0")
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def discover_checks(test_dir: Path) -> list[str]:
    """Static pytest node ids (``file.py::test_x`` / ``file.py::TestC::test_x``).

    Parametrised tests are not expanded; verifier tests must not be parametrised
    (each scored check needs a stable, unique id).
    """
    ids: list[str] = []
    for f in sorted(test_dir.rglob("test_*.py")):
        rel = f.relative_to(test_dir).as_posix()
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                ids.append(f"{rel}::{node.name}")
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test"):
                        ids.append(f"{rel}::{node.name}::{sub.name}")
    return ids


@dataclass
class LintIssue:
    file: str
    line: int
    code: str
    message: str


def _is_parametrize(dec: ast.expr) -> bool:
    target = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(target, ast.Attribute) and target.attr == "parametrize"


def lint_process_separated(test_dir: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for f in sorted(test_dir.rglob("*.py")):
        rel = f.relative_to(test_dir).as_posix()
        src = f.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(f))
        except SyntaxError as exc:
            issues.append(LintIssue(rel, exc.lineno or 0, "syntax", str(exc)))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                        issues.append(LintIssue(rel, node.lineno, "forbidden_import", f"import {a.name}"))
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if node.level or mod not in ALLOWED_IMPORTS:
                    issues.append(LintIssue(rel, node.lineno, "forbidden_import", f"from {node.module} import ..."))
        # Writes to forbidden locations: open(<forbidden>, 'w'/'a'/'x') and similar.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open" and node.args:
                first = node.args[0]
                mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
                if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.startswith(FORBIDDEN_PATH_PREFIXES):
                    if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and set(mode.value) & set("wax+"):
                        issues.append(LintIssue(rel, node.lineno, "forbidden_write", f"write to {first.value}"))
        if f.name.startswith("test_"):
            for node in tree.body:
                funcs = []
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                    funcs = [node]
                elif isinstance(node, ast.ClassDef):
                    funcs = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]
                for fn in funcs:
                    if any(_is_parametrize(d) for d in fn.decorator_list):
                        issues.append(LintIssue(rel, fn.lineno, "parametrized", f"{fn.name}: parametrised checks are not allowed"))
                    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
                    names = {c.func.id if isinstance(c.func, ast.Name) else c.func.attr if isinstance(c.func, ast.Attribute) else "" for c in calls}
                    helper_calls = names & {"run_python", "run_cmd"}
                    if not helper_calls and not (names - {"print", "len", "isinstance"}):
                        issues.append(LintIssue(rel, fn.lineno, "no_sandbox_call", f"{fn.name}: does not exercise candidate code"))
                    asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
                    if not asserts:
                        issues.append(LintIssue(rel, fn.lineno, "no_assert", f"{fn.name}: has no assertions"))
                    elif all(_only_ok_check(a.test) for a in asserts):
                        issues.append(LintIssue(rel, fn.lineno, "ok_only", f"{fn.name}: only asserts r.ok (no value check)"))
    return issues


def _only_ok_check(expr: ast.expr) -> bool:
    """True if an assert expression only inspects ``<x>.ok``."""
    if isinstance(expr, ast.Attribute) and expr.attr == "ok":
        return True
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _only_ok_check(expr.operand)
    return False


def build_spec(
    *,
    verifier_id: str,
    task_id: str,
    condition: VerifierCondition,
    test_dir: Path,
    task_dir: Path,
    isolation: Isolation = Isolation.process_separated,
    contract_id: str | None = None,
    requirement_map: dict[str, list[str]] | None = None,
    generation: GenerationRecord | None = None,
    check_ids: list[str] | None = None,
) -> VerifierSpec:
    ids = check_ids if check_ids is not None else discover_checks(test_dir)
    requirement_map = requirement_map or {}
    return VerifierSpec(
        verifier_id=verifier_id,
        task_id=task_id,
        condition=condition,
        contract_id=contract_id,
        isolation=isolation,
        test_dir=test_dir.relative_to(task_dir).as_posix(),
        checks=[CheckSpec(check_id=c, requirement_ids=requirement_map.get(c, [])) for c in ids],
        content_sha256=hash_test_dir(test_dir),
        generation=generation,
    )


def freeze(spec: VerifierSpec, task_dir: Path) -> VerifierSpec:
    """Mark a verifier frozen; its content hash must match the files on disk."""
    actual = hash_test_dir(task_dir / spec.test_dir)
    if actual != spec.content_sha256:
        raise ValueError(f"{spec.verifier_id}: test files changed since the spec was built")
    return spec.model_copy(update={"frozen": True})


def check_frozen(spec: VerifierSpec, task_dir: Path) -> None:
    if spec.frozen and hash_test_dir(task_dir / spec.test_dir) != spec.content_sha256:
        raise ValueError(f"{spec.verifier_id}: frozen verifier was modified; bump the version and rerun")


def requirement_map_from_tests(test_dir: Path) -> dict[str, list[str]]:
    """Read ``CHECK_REQUIREMENTS = {"test_name": ["R1", ...]}`` from each test file.

    Keys may be bare test names or ``Class::test`` names; they are qualified with the
    file path to form check ids.
    """
    out: dict[str, list[str]] = {}
    for f in sorted(test_dir.rglob("test_*.py")):
        rel = f.relative_to(test_dir).as_posix()
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CHECK_REQUIREMENTS" for t in node.targets):
                try:
                    val = ast.literal_eval(node.value)
                except ValueError:
                    continue
                for k, v in dict(val).items():
                    out[f"{rel}::{k}"] = [str(x) for x in v]
    return out
