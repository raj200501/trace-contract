"""Smoke-test the trusted grader in natural task images before any generated verifier is graded in them.

Usage: python scripts/smoke_natural_images.py --images IMAGE [IMAGE ...] --out FILE

In each image, grades two process-separated verifiers on ``FX-01-reference`` and on ``FX-01-wrong``, three single
grades each:
* the frozen fixture verifier FX-01 ``v1`` (``tests/fixtures/harbor_fx01``), whose two checks call ``run_python``;
* a probe, written by this script to a temporary directory, of what generated verifiers may use beyond that: a
  hypothesis ``@given`` test (hypothesis is imported in the trusted process, and its example database meets the
  read-only grader directory when a failure is saved), pytest's own fixtures (``tmp_path``, ``monkeypatch``,
  ``request``) and a method of a test class. Its checks test FX-01's ``add`` as v1's do.
The process-separated runner calls ``pytest.main`` in the trusted process inside the image, and the pytest plugins
that some natural images pin load there; the harness has run in these images only in repository-test mode (S10).

An image passes when:
* the image is present, with the same id before and after its grades; every grade runs in the image of that id;
* for both verifiers, every grade of FX-01-reference is ``pass`` with every check ``passed``, and every grade of
  FX-01-wrong is ``task_failure`` with every check ``failed``;
* every grade is of the verifier's checks, under this harness version, and reports no tampering.
Any other result means: stop and decide on the harness before grading in that image.

Writes only ``--out``, a JSON report that must lie outside the repository and not exist yet: per image, the image id
and, per grade, the verifier, the outcome, the check statuses, the diagnostics and the log's sha256. Nothing is
written under ``tasks/``, ``data/`` or ``results/``: the grading copies the fixture's base and the tests to temporary
directories (the system's, which must lie outside the repository too), keeps no logs and runs one container at a
time. No image is built or pulled: a missing image is reported as missing. Exit status 0 if every image passes, 1 if
any does not, 2 if the run is refused.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from tracecontract.sandbox.docker_runner import HARNESS_VERSION, verify_candidate
from tracecontract.schemas import (
    Candidate,
    Isolation,
    TaskManifest,
    VerificationResult,
    VerifierSpec,
)
from tracecontract.store import load
from tracecontract.verifier import (
    build_spec,
    discover_checks,
    hash_test_dir,
    requirement_map_from_tests,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "harbor_fx01"
TASK_ID, VERIFIER_ID = "FX-01", "v1"
PROBE_ID, PROBE_FILE = "probe", "test_smoke_probe.py"
REPEATS = 3
RUN_ID = "smoke-natural-images"
SCHEMA = "natural-image-smoke:v1"
# candidate -> (expected outcome, expected status of every check), for both verifiers
EXPECTED = {"FX-01-reference": ("pass", "passed"), "FX-01-wrong": ("task_failure", "failed")}
_BAD_DIAGNOSTICS = ("tamper_detected", "harness version mismatch")
# FX-01-reference makes add(a, b) return a + b and FX-01-wrong a - b: every check passes on the one, fails on the other.
PROBE = textwrap.dedent('''\
    """Smoke probe of the trusted runner: hypothesis, pytest's fixtures and a test class, as generated verifiers use."""
    from hypothesis import given, settings
    from hypothesis import strategies as st
    from tc_sandbox import run_python

    CHECK_REQUIREMENTS = {"test_hypothesis_given": ["R1"], "test_builtin_fixtures": ["R1"], "TestClass::test_method": ["R1"]}


    @settings(max_examples=5, deadline=None)
    @given(st.integers(min_value=-20, max_value=20))
    def test_hypothesis_given(x):
        r = run_python(f"from calc import add\\nresult = add({x}, 3)")
        assert r.ok, r
        assert r.value == x + 3


    def test_builtin_fixtures(tmp_path, monkeypatch, request):
        monkeypatch.setenv("TC_SMOKE_PROBE", "1")
        note = tmp_path / "probe.txt"
        note.write_text("probe", encoding="utf-8")
        r = run_python("from calc import add\\nresult = add(20, 22)")
        assert r.ok, r
        assert r.value == 42
        assert note.read_text(encoding="utf-8") == "probe" and request.node.name == "test_builtin_fixtures"


    class TestClass:
        def test_method(self):
            r = run_python("from calc import add\\nresult = add(2, 2)")
            assert r.ok, r
            assert r.value == 4
''')


class SmokeError(ValueError):
    """The smoke test cannot run as asked; nothing is written."""


@dataclass(frozen=True)
class Fixture:
    task_dir: Path
    snapshot: Path
    task: TaskManifest
    spec: VerifierSpec
    candidates: dict[str, Candidate]


@dataclass(frozen=True)
class Suite:
    """A verifier graded in each image: its spec and the task directory its tests are found from."""

    name: str
    spec: VerifierSpec
    task_dir: Path


Grader = Callable[[str, Suite, Candidate], VerificationResult]
ImageId = Callable[[str], str | None]


def _read[M: BaseModel](path: Path, cls: type[M]) -> M:
    try:
        return load(path, cls)
    except (OSError, ValidationError) as exc:
        raise SmokeError(f"{path.name}: not a readable {cls.__name__} ({exc.__class__.__name__})") from None


def load_fixture(root: Path = FIXTURE) -> Fixture:
    """The FX-01 task, its frozen process-separated verifier v1 (its tests unchanged) and its two candidates."""
    task_dir, snapshot = root / "tasks" / TASK_ID, root / "snapshots" / TASK_ID
    task = _read(task_dir / "task.json", TaskManifest)
    spec = _read(task_dir / "verifiers" / VERIFIER_ID / "spec.json", VerifierSpec)
    if spec.isolation != Isolation.process_separated or not spec.frozen:
        raise SmokeError(f"{TASK_ID}/{VERIFIER_ID} is not a frozen process-separated verifier")
    tests = task_dir / spec.test_dir  # the fixture's frozen spec predates check-list hashes: its files are checked
    if hash_test_dir(tests) != spec.content_sha256 or discover_checks(tests) != [c.check_id for c in spec.checks]:
        raise SmokeError(f"{TASK_ID}/{VERIFIER_ID}: the tests changed since the verifier was frozen")
    if not snapshot.is_dir():
        raise SmokeError(f"{TASK_ID}: the base snapshot is missing")
    candidates = {}
    for rel in task.candidates:
        cand = _read(task_dir / rel, Candidate)  # the model checks the patch against its sha256
        if cand.candidate_id in EXPECTED:
            candidates[cand.candidate_id] = cand
    if set(candidates) != set(EXPECTED):
        raise SmokeError(f"{TASK_ID}: candidates {sorted(set(EXPECTED) - set(candidates))} are missing")
    return Fixture(task_dir, snapshot, task, spec, candidates)


def fixture_suite(fx: Fixture) -> Suite:
    return Suite(VERIFIER_ID, fx.spec, fx.task_dir)


def probe_suite(root: Path, fx: Fixture) -> Suite:
    """The probe verifier, written under ``root`` (a temporary directory outside the repository)."""
    task_dir = root / TASK_ID
    tests = task_dir / "verifiers" / PROBE_ID / "tests"
    tests.mkdir(parents=True)
    (tests / PROBE_FILE).write_text(PROBE, encoding="utf-8")
    spec = build_spec(verifier_id=PROBE_ID, task_id=TASK_ID, condition=fx.spec.condition, test_dir=tests,
                      task_dir=task_dir, requirement_map=requirement_map_from_tests(tests))
    return Suite(PROBE_ID, spec, task_dir)


def docker_grader(fx: Fixture) -> Grader:
    """One single grade of a fixture candidate with a verifier in an image, with nothing kept but the result."""
    def grade(image: str, suite: Suite, candidate: Candidate) -> VerificationResult:
        return verify_candidate(image=image, base_dir=fx.snapshot, spec=suite.spec, task_dir=suite.task_dir,
                                candidate=candidate, run_id=RUN_ID, repeats=1,
                                candidate_pythonpath=fx.task.candidate_pythonpath, repo_test_args=fx.task.repo_test_args)
    return grade


def docker_image_id(image: str) -> str | None:
    """The local image's id, or None when it is not present (it is never built or pulled here)."""
    try:
        proc = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image], capture_output=True,
                              text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and out.startswith("sha256:") else None


def _problems(suite: Suite, cid: str, repeat: int, res: VerificationResult) -> list[str]:
    want_outcome, want_status = EXPECTED[cid]
    where = f"{suite.name} {cid} grade {repeat}"
    out = []
    if (res.task_id, res.verifier_id, res.candidate_id) != (TASK_ID, suite.spec.verifier_id, cid):
        out.append(f"{where}: the result is of {res.task_id}/{res.verifier_id}/{res.candidate_id}")
    if res.outcome.value != want_outcome:
        out.append(f"{where}: outcome {res.outcome.value}, expected {want_outcome}")
    statuses = {c.check_id: c.status for c in res.checks}
    want_checks = sorted(c.check_id for c in suite.spec.checks)
    if set(statuses) != set(want_checks):
        out.append(f"{where}: graded checks {sorted(statuses)}, expected {want_checks}")
    out += [f"{where}: check {k} {s}, expected {want_status}" for k, s in sorted(statuses.items()) if s != want_status]
    if res.harness_version != HARNESS_VERSION:
        out.append(f"{where}: harness {res.harness_version}, expected {HARNESS_VERSION}")
    out += [f"{where}: diagnostic {d}" for d in res.diagnostics if any(b in d for b in _BAD_DIAGNOSTICS)]
    return out


def smoke(images: list[str], fx: Fixture, suites: list[Suite], *, grade: Grader, image_id: ImageId) -> dict[str, Any]:
    """The report: each image's grades and problems; ``ok`` when every image passes. Each image is graded by the id
    that its inspection gave, so that every grade runs in the image that was checked."""
    started = _now()
    rows = []
    for image in dict.fromkeys(images):
        before = image_id(image)
        row: dict[str, Any] = {"image": image, "image_id": before, "grades": [], "problems": []}
        if before is None:
            row["problems"].append("the image is not present locally (it is never built or pulled here)")
        else:
            for suite in suites:
                for cid in EXPECTED:
                    for k in range(1, REPEATS + 1):
                        try:
                            res = grade(before, suite, fx.candidates[cid])
                        except Exception as exc:  # noqa: BLE001 - any failure of a grade is recorded, the report written
                            row["grades"].append({"verifier": suite.name, "candidate": cid, "repeat": k,
                                                  "error": exc.__class__.__name__})
                            row["problems"].append(f"{suite.name} {cid} grade {k}: the grader raised "
                                                   f"{exc.__class__.__name__}: {str(exc)[:300]}")
                            continue
                        row["grades"].append({
                            "verifier": suite.name, "candidate": cid, "repeat": k, "outcome": res.outcome.value,
                            "checks": {c.check_id: c.status for c in res.checks},
                            "harness_version": res.harness_version, "diagnostics": list(res.diagnostics),
                            "wall_s": round(res.wall_s, 3), "log_sha256": res.log_sha256, "started_at": res.started_at})
                        row["problems"] += _problems(suite, cid, k, res)
            after = image_id(image)
            if after != before:
                row["problems"].append(f"the image id changed during the grades (now {after})")
        row["ok"] = not row["problems"]
        rows.append(row)
    return {
        "schema": SCHEMA, "harness_version": HARNESS_VERSION, "repeats": REPEATS, "run_id": RUN_ID,
        "graded_by": "image id",
        "fixture": {"task_id": TASK_ID, "verifier_id": VERIFIER_ID, "content_sha256": fx.spec.content_sha256,
                    "checks_sha256": fx.spec.checks_sha256,
                    "candidates": {cid: {"patch_sha256": fx.candidates[cid].patch_sha256, "expected_outcome": o,
                                         "expected_check_status": s} for cid, (o, s) in EXPECTED.items()}},
        "verifiers": {s.name: {"content_sha256": s.spec.content_sha256, "checks": [c.check_id for c in s.spec.checks]}
                      for s in suites},
        "started_at": started, "finished_at": _now(), "images": rows,
        "ok": bool(rows) and all(r["ok"] for r in rows),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _inside_repo(path: Path) -> bool:
    p = path.resolve()
    return p == REPO or REPO in p.parents


def out_path(out: Path) -> Path:
    """``--out``, refused inside the repository, when it exists, and when its directory is a file."""
    if _inside_repo(out):
        raise SmokeError("--out lies inside the repository; the report is written outside it")
    p = out.resolve()
    if out.exists() or out.is_symlink() or p.exists():
        raise SmokeError(f"--out {p.name} exists; an earlier report is never overwritten")
    if p.parent.exists() and not p.parent.is_dir():
        raise SmokeError("--out: its parent is not a directory")
    return p


def main(argv: list[str] | None = None, *, grade: Grader | None = None, image_id: ImageId | None = None) -> int:
    ap = argparse.ArgumentParser(prog="smoke_natural_images.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--images", nargs="+", required=True, help="image tags or ids, e.g. a task's environment image")
    ap.add_argument("--out", type=Path, required=True, help="the JSON report, outside the repository; must not exist")
    a = ap.parse_args(argv)
    try:
        bad = [i for i in a.images if not i.strip() or i.startswith("-") or any(c.isspace() for c in i)]
        if bad:
            raise SmokeError(f"not an image name: {bad}")
        out = out_path(a.out)
        if _inside_repo(Path(tempfile.gettempdir())):
            raise SmokeError("the system's temporary directory lies inside the repository")
        fx = load_fixture()
    except SmokeError as exc:
        print(f"smoke_natural_images: refused, nothing written: {exc}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="tc_smoke_probe_") as tmp:
        suites = [fixture_suite(fx), probe_suite(Path(tmp), fx)]
        report = smoke(a.images, fx, suites, grade=grade or docker_grader(fx), image_id=image_id or docker_image_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as fh:
        fh.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"out": str(out), "ok": report["ok"],
                      "images": {r["image"]: "ok" if r["ok"] else f"{len(r['problems'])} problem(s)"
                                 for r in report["images"]}}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
