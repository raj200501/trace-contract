"""Verifier specs: hashing, check discovery, linting, and freezing.

A verifier is a directory of pytest files plus a :class:`VerifierSpec`. For the
process-separated isolation level, tests may touch candidate code only through
``tc_sandbox.run_python`` / ``tc_sandbox.run_cmd``. :func:`lint_process_separated`
enforces the parts of that rule that can be checked statically:

* no ``import`` of anything except the standard library, ``pytest``,
  ``hypothesis`` and ``tc_sandbox`` (so candidate modules are never imported into
  the grader process);
* no ``open()`` writes to a literal path in the candidate workspace or the results
  directory (other writes are not detected);
* no parametrised tests;
* each test makes a call (a sandbox call, or any call other than ``print``, ``len``
  or ``isinstance``) and has an assertion beyond ``r.ok`` (to limit
  no-exception-only checks, see tc_sandbox residual risk).

The prompts additionally ask that every test go through the sandbox and write only
under ``/tmp``; the lint does not verify that.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
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


# --------------------------------------------------------------------------- generation records

# What a generation record of a new run keeps in ``budget``: the run's times, its costs and
# where its private record is kept (protocol v0.7 §15.4, §15.6; decision log D42).
GENERATION_RUN_KEYS = ("started_at", "ended_at", "wall_s", "turns", "tokens", "tool_calls", "run_record")
CONFIG_LABEL = re.compile(r"config-[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_SESSION_LOCAL = ("/tmp/claude-", "/.claude/")


def generation_record(*, run_id: str | None, config: str | None, prompt_sha256: str | None, started_at: str | None,
                      ended_at: str | None, wall_s: float | None, tool_calls: int | None, run_record: str | None,
                      turns: int | None = None, tokens: int | None = None, notes: str = "") -> GenerationRecord:
    """The generation record of one agent run; ``ValueError`` unless it is complete (:func:`generation_record_problems`).

    Model identifiers are never written into the repository. ``config`` is a configuration
    label (``config-A``), stored as the record's ``generator``, and ``run_record`` points to
    the private run record, which says which model the configuration was. The times and
    costs of the run go into ``budget`` (``GENERATION_RUN_KEYS``); ``created_at`` is the end.
    """
    budget = {"started_at": started_at, "ended_at": ended_at, "wall_s": wall_s, "turns": turns, "tokens": tokens,
              "tool_calls": tool_calls, "run_record": run_record}
    rec = GenerationRecord(generator=config or "", run_id=run_id or "", prompt_sha256=prompt_sha256 or "",
                           created_at=ended_at or "", budget={k: v for k, v in budget.items() if v is not None}, notes=notes)
    problems = generation_record_problems(rec)
    if problems:
        raise ValueError("incomplete generation record: " + "; ".join(problems))
    return rec


def _time(value) -> datetime | None:
    try:
        t = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return t if t is not None and t.tzinfo is not None else None


def _count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def generation_record_problems(rec: GenerationRecord | None) -> list[str]:
    """What keeps ``rec`` from being a complete generation record of a new run (empty if it is complete).

    A complete record holds a run id; a configuration label (``config-<id>``, so never a model
    identifier); the prompt's sha256; start and end times (ISO 8601 with a time zone, the end
    not before the start, ``created_at`` a time too); turns or tokens; tool calls; the wall time
    (positive, and not longer than the time from start to end); and a pointer to the private
    run record. ``budget`` holds nothing else, and no field holds a session id or a
    session-local path. The pilot's records (run id "unrecorded", no hash, empty budget) are
    not complete; they are kept as recorded.
    """
    if rec is None:
        return ["no generation record"]
    out = []
    b = rec.budget
    if not rec.run_id.strip() or rec.run_id == "unrecorded" or any(c.isspace() for c in rec.run_id):
        out.append("run id missing (or 'unrecorded', or with whitespace)")
    if not CONFIG_LABEL.fullmatch(rec.generator):
        out.append(f"configuration label must look like 'config-A' (got {rec.generator!r}); model identifiers stay "
                   "in the private run record")
    if not _SHA256.fullmatch(rec.prompt_sha256):
        out.append("prompt sha256 missing or not 64 lowercase hex digits")
    start, end = _time(b.get("started_at")), _time(b.get("ended_at"))
    if start is None or end is None:
        out.append("start and end times must be ISO 8601 times with a time zone")
    elif end < start:
        out.append("the end time is before the start time")
    if _time(rec.created_at) is None:
        out.append("created_at must be an ISO 8601 time with a time zone")
    present = [k for k in ("turns", "tokens") if k in b]
    if not present:
        out.append("turns or tokens missing")
    out += [f"{k} must be a non-negative integer" for k in present if not _count(b[k])]
    if not _count(b.get("tool_calls")):
        out.append("tool calls missing or not a non-negative integer")
    wall = b.get("wall_s")
    if not isinstance(wall, (int, float)) or isinstance(wall, bool) or wall <= 0:
        out.append("wall time missing or not positive")
    elif start is not None and end is not None and end >= start and wall > (end - start).total_seconds() + 1:
        out.append("the wall time is longer than the time from start to end")
    if not isinstance(b.get("run_record"), str) or not b["run_record"].strip():
        out.append("pointer to the private run record missing")
    extra = sorted(set(b) - set(GENERATION_RUN_KEYS))
    if extra:
        out.append(f"budget holds unknown keys {extra}")
    texts = [rec.run_id, rec.generator, rec.notes, *(str(v) for v in b.values())]
    if any(_SESSION_ID.search(t) or any(m in t for m in _SESSION_LOCAL) for t in texts):
        out.append("a field holds a session id or a session-local path")
    return out


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
    require_generation: bool = False,
) -> VerifierSpec:
    """A spec for the tests in ``test_dir``. With ``require_generation`` an incomplete generation record is refused
    (``ValueError``, :func:`generation_record_problems`); ``build-verifier`` requires one for every generated verifier."""
    if require_generation:
        problems = generation_record_problems(generation)
        if problems:
            raise ValueError(f"{verifier_id}: no complete generation record: " + "; ".join(problems))
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


def checks_sha256(spec: VerifierSpec) -> str:
    """Hash of the scored check list: sorted check ids with their requirement ids."""
    items = sorted((c.check_id, sorted(c.requirement_ids)) for c in spec.checks)
    return hashlib.sha256(json.dumps(items, separators=(",", ":")).encode("utf-8")).hexdigest()


def freeze(spec: VerifierSpec, task_dir: Path) -> VerifierSpec:
    """Mark a verifier frozen; its content hash must match the files on disk.

    Freezing also records the hash of the scored check list and the time of freezing.
    An already frozen spec is refused: changing a frozen verifier requires a new version.
    """
    if spec.frozen:
        raise ValueError(f"{spec.verifier_id}: already frozen (at {spec.frozen_at or 'an unrecorded time'}); "
                         "build a new version instead of re-freezing")
    actual = hash_test_dir(task_dir / spec.test_dir)
    if actual != spec.content_sha256:
        raise ValueError(f"{spec.verifier_id}: test files changed since the spec was built")
    from datetime import datetime, timezone

    return spec.model_copy(update={"frozen": True, "checks_sha256": checks_sha256(spec),
                                   "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def check_frozen(spec: VerifierSpec, task_dir: Path) -> None:
    if not spec.frozen:
        return
    if hash_test_dir(task_dir / spec.test_dir) != spec.content_sha256:
        raise ValueError(f"{spec.verifier_id}: frozen verifier was modified; bump the version and rerun")
    if spec.checks_sha256 is None:
        raise ValueError(f"{spec.verifier_id}: frozen spec records no hash of its scored check list")
    if checks_sha256(spec) != spec.checks_sha256:
        raise ValueError(f"{spec.verifier_id}: scored check list changed after freezing; bump the version and rerun")


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
