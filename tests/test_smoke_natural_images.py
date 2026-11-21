"""scripts/smoke_natural_images.py with a fake grader: the verdict per image, where it writes, what it refuses.

No container runs here: every test replaces ``subprocess.run`` with a guard that fails on any call, and the grades
come from a fake grader. The wiring to the real grader is checked with ``verify_candidate`` replaced.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tracecontract.sandbox.docker_runner import HARNESS_VERSION
from tracecontract.schemas import CheckResult, Outcome, VerificationResult
from tracecontract.verifier import ALLOWED_IMPORTS, lint_process_separated

R = Path(__file__).resolve().parents[1]
IMAGES = ["tc-env:0123456789abcdef", "tc-env:fedcba9876543210"]
IDS = {IMAGES[0]: "sha256:" + "1" * 64, IMAGES[1]: "sha256:" + "2" * 64}
PROTECTED = "protected path change removed before grading: tests/test_calc.py"  # FX-01's candidates touch its tests
SUITES = ("v1", "probe")
CANDIDATES = ("FX-01-reference", "FX-01-wrong")
PROBE_CHECKS = ["test_smoke_probe.py::test_hypothesis_given", "test_smoke_probe.py::test_builtin_fixtures",
                "test_smoke_probe.py::TestClass::test_method"]


def _load():
    spec = importlib.util.spec_from_file_location("smoke_natural_images", R / "scripts" / "smoke_natural_images.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # its dataclasses resolve their annotations through the module
    spec.loader.exec_module(mod)
    return mod


smoke = _load()
FX = smoke.load_fixture()


@pytest.fixture(autouse=True)
def no_processes(monkeypatch):
    def refuse(*a, **kw):
        raise AssertionError(f"no process may start in these tests: {a[:1]}")
    monkeypatch.setattr(subprocess, "run", refuse)


def fake_grader(behaviour: dict | None = None):
    """Grades as the harness should (with both verifiers, FX-01-reference passes every check and FX-01-wrong fails
    every check), except where ``behaviour[(image, verifier, candidate)]`` gives (outcome, status, extra fields)."""
    calls = []

    def grade(image, suite, cand):
        calls.append((image, suite.name, cand.candidate_id))
        outcome, status, extra = (behaviour or {}).get((image, suite.name, cand.candidate_id),
                                                       (*smoke.EXPECTED[cand.candidate_id], {}))
        res = VerificationResult(
            run_id=smoke.RUN_ID, task_id="FX-01", verifier_id=suite.spec.verifier_id, candidate_id=cand.candidate_id,
            outcome=Outcome(outcome), reward=1.0 if outcome == "pass" else 0.0,
            checks=[CheckResult(check_id=c.check_id, status=status) for c in suite.spec.checks],
            diagnostics=[PROTECTED], started_at="2026-11-22T12:00:00+00:00", finished_at="2026-11-22T12:00:05+00:00",
            wall_s=5.0, harness_version=HARNESS_VERSION, log_sha256="ab" * 32)
        return res.model_copy(update=extra)
    return grade, calls


def fake_ids(ids: dict | None = None, *, change: str | None = None):
    seen: dict[str, int] = {}

    def image_id(image):
        seen[image] = seen.get(image, 0) + 1
        if image == change and seen[image] > 1:
            return "sha256:" + "9" * 64
        return (IDS if ids is None else ids).get(image)
    return image_id, seen


def _run(capsys, out: Path, *, images=IMAGES, grade=None, image_id=None) -> tuple[int, dict | None, str]:
    code = smoke.main(["--images", *images, "--out", str(out)], grade=grade, image_id=image_id)
    cap = capsys.readouterr()
    return code, (json.loads(out.read_text()) if out.is_file() else None), cap.err


def test_every_image_passes_when_both_verifiers_grade_as_expected(tmp_path, capsys):
    grade, calls = fake_grader()
    image_id, seen = fake_ids()
    out = tmp_path / "runrec" / "smoke.json"  # its directory is made
    code, report, _ = _run(capsys, out, images=IMAGES + IMAGES[:1], grade=grade, image_id=image_id)
    assert code == 0 and report["ok"] is True
    assert [r["image"] for r in report["images"]] == IMAGES  # each image once
    # every grade runs by the id the inspection gave, never by the tag
    assert calls == [(IDS[img], s, c) for img in IMAGES for s in SUITES for c in CANDIDATES for _ in range(3)]
    assert seen == {IMAGES[0]: 2, IMAGES[1]: 2}  # before and after the grades
    for row in report["images"]:
        assert row["ok"] and row["problems"] == [] and row["image_id"] == IDS[row["image"]]
        assert [(g["verifier"], g["candidate"], g["repeat"]) for g in row["grades"]] == [
            (s, c, k) for s in SUITES for c in CANDIDATES for k in (1, 2, 3)]
        assert {g["outcome"] for g in row["grades"] if g["candidate"] == "FX-01-wrong"} == {"task_failure"}
    assert report["harness_version"] == HARNESS_VERSION and report["repeats"] == 3 and report["graded_by"] == "image id"
    assert report["fixture"]["content_sha256"] == FX.spec.content_sha256
    assert report["verifiers"]["probe"]["checks"] == PROBE_CHECKS
    assert sorted(p.name for p in tmp_path.rglob("*")) == ["runrec", "smoke.json"]  # nothing else is written


def test_an_image_whose_grades_differ_fails_and_says_why(tmp_path, capsys):
    swallowed = {(IDS[IMAGES[1]], "v1", "FX-01-wrong"): ("pass", "passed", {})}  # e.g. a plugin that hides failures
    grade, _ = fake_grader(swallowed)
    code, report, _ = _run(capsys, tmp_path / "smoke.json", grade=grade, image_id=fake_ids()[0])
    assert code == 1 and report["ok"] is False
    good, bad = report["images"]
    assert good["ok"] is True and bad["ok"] is False
    assert "v1 FX-01-wrong grade 1: outcome pass, expected task_failure" in bad["problems"]
    assert "v1 FX-01-wrong grade 3: check test_add.py::test_add passed, expected failed" in bad["problems"]


def test_the_probe_fails_an_image_where_hypothesis_or_fixtures_misbehave(tmp_path, capsys):
    """FX-01 v1 grades as expected, but the probe's hypothesis check errors on the failing candidate (as it would if
    the example database could not be written in the read-only grader directory): the image fails."""
    check = PROBE_CHECKS[0]
    errored = [CheckResult(check_id=c, status="error" if c == check else "failed") for c in PROBE_CHECKS]
    grade, _ = fake_grader({(IDS[IMAGES[0]], "probe", "FX-01-wrong"): ("verifier_error", "failed", {"checks": errored})})
    code, report, _ = _run(capsys, tmp_path / "smoke.json", images=IMAGES[:1], grade=grade, image_id=fake_ids()[0])
    assert code == 1
    problems = report["images"][0]["problems"]
    assert "probe FX-01-wrong grade 2: outcome verifier_error, expected task_failure" in problems
    assert f"probe FX-01-wrong grade 2: check {check} error, expected failed" in problems
    assert not any(p.startswith("v1 ") for p in problems)


def test_the_probe_is_a_lint_clean_verifier_of_three_checks(tmp_path):
    suite = smoke.probe_suite(tmp_path, FX)
    tests = suite.task_dir / suite.spec.test_dir
    assert [c.check_id for c in suite.spec.checks] == PROBE_CHECKS
    assert all(c.requirement_ids == ["R1"] for c in suite.spec.checks)
    assert lint_process_separated(tests) == [] and "hypothesis" in ALLOWED_IMPORTS
    assert "from hypothesis import given" in (tests / smoke.PROBE_FILE).read_text()
    assert suite.spec.verifier_id == "probe" and suite.task_dir == tmp_path / "FX-01"


@pytest.mark.parametrize("extra, problem", [
    ({"diagnostics": [PROTECTED, "[run 0] tamper_detected: sys.modules"]}, "diagnostic [run 0] tamper_detected"),
    ({"harness_version": "tc-harness/0.3.4"}, "harness tc-harness/0.3.4"),
    ({"checks": [CheckResult(check_id="test_add.py::test_add", status="passed")]}, "graded checks"),
    ({"candidate_id": "FX-01-wrong"}, "the result is of FX-01/v1/FX-01-wrong"),
])
def test_tampering_another_harness_or_other_checks_fail_an_image(tmp_path, capsys, extra, problem):
    grade, _ = fake_grader({(IDS[IMAGES[0]], "v1", "FX-01-reference"): ("pass", "passed", extra)})
    code, report, _ = _run(capsys, tmp_path / "smoke.json", images=IMAGES[:1], grade=grade, image_id=fake_ids()[0])
    assert code == 1 and any(problem in p for p in report["images"][0]["problems"]), report["images"][0]["problems"]


def test_a_missing_or_changing_image_fails_and_a_missing_one_is_never_graded(tmp_path, capsys):
    grade, calls = fake_grader()
    image_id, _ = fake_ids({IMAGES[1]: IDS[IMAGES[1]]}, change=IMAGES[1])
    code, report, _ = _run(capsys, tmp_path / "smoke.json", grade=grade, image_id=image_id)
    assert code == 1
    missing, changed = report["images"]
    assert missing["image_id"] is None and missing["grades"] == [] and "not present locally" in missing["problems"][0]
    assert {img for img, _, _ in calls} == {IDS[IMAGES[1]]}  # graded in the image inspected first
    assert any("image id changed" in p for p in changed["problems"])


def test_a_grader_that_raises_is_a_problem_and_the_report_is_still_written(tmp_path, capsys):
    def grade(image, suite, cand):
        raise RuntimeError("docker run failed (125)")
    code, report, _ = _run(capsys, tmp_path / "smoke.json", images=IMAGES[:1], grade=grade, image_id=fake_ids()[0])
    assert code == 1 and report["ok"] is False and len(report["images"][0]["grades"]) == 12
    assert "v1 FX-01-reference grade 1: the grader raised RuntimeError: docker run failed (125)" in report["images"][0][
        "problems"]


def test_refused_runs_write_nothing_and_grade_nothing(tmp_path, capsys):
    grade, calls = fake_grader()
    inside = R / "results" / "smoke-should-not-exist.json"
    code, _, err = _run(capsys, inside, grade=grade, image_id=fake_ids()[0])
    assert code == 2 and "inside the repository" in err and not inside.exists()
    old = tmp_path / "smoke.json"
    old.write_text("{}")
    assert smoke.main(["--images", IMAGES[0], "--out", str(old)], grade=grade, image_id=fake_ids()[0]) == 2
    assert old.read_text() == "{}" and "exists" in capsys.readouterr().err
    for bad in ("-q", "tc-env:x y", ""):
        assert smoke.main([f"--images={bad}", "--out", str(tmp_path / "x.json")], grade=grade,
                          image_id=fake_ids()[0]) == 2
    assert calls == [] and not (tmp_path / "x.json").exists()


def test_the_fixture_must_be_the_frozen_fx01_verifier(tmp_path):
    root = tmp_path / "harbor_fx01"
    shutil.copytree(smoke.FIXTURE, root)
    assert smoke.load_fixture(root).spec.frozen
    test = root / "tasks" / "FX-01" / "verifiers" / "v1" / "tests" / "test_add.py"
    test.write_text(test.read_text() + "\n# changed\n")
    with pytest.raises(smoke.SmokeError, match="tests changed since the verifier was frozen"):
        smoke.load_fixture(root)


def test_the_real_grader_grades_once_per_call_and_keeps_no_logs(monkeypatch, tmp_path):
    seen = []

    def verify_candidate(**kw):
        seen.append(kw)
        return "result"
    monkeypatch.setattr(smoke, "verify_candidate", verify_candidate)
    probe = smoke.probe_suite(tmp_path, FX)
    grade = smoke.docker_grader(FX)
    assert grade(IDS[IMAGES[0]], smoke.fixture_suite(FX), FX.candidates["FX-01-wrong"]) == "result"
    assert grade(IDS[IMAGES[0]], probe, FX.candidates["FX-01-reference"]) == "result"
    v1, pr = seen
    for kw in seen:
        assert kw["image"] == IDS[IMAGES[0]] and kw["repeats"] == 1 and "log_dir" not in kw
        assert kw["base_dir"] == smoke.FIXTURE / "snapshots" / "FX-01"
    assert v1["task_dir"] == smoke.FIXTURE / "tasks" / "FX-01" and v1["spec"] is FX.spec
    assert v1["candidate"].candidate_id == "FX-01-wrong"
    assert pr["spec"] is probe.spec and (pr["task_dir"] / pr["spec"].test_dir / smoke.PROBE_FILE).is_file()


def test_the_image_id_comes_from_an_inspection_only(monkeypatch):
    commands = []

    def run(cmd, **kw):
        commands.append(cmd)
        found = cmd[-1] == IMAGES[0]
        return subprocess.CompletedProcess(cmd, 0 if found else 1, stdout=IDS[IMAGES[0]] + "\n" if found else "", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    assert smoke.docker_image_id(IMAGES[0]) == IDS[IMAGES[0]]
    assert smoke.docker_image_id(IMAGES[1]) is None
    assert commands == [["docker", "image", "inspect", "--format", "{{.Id}}", img] for img in IMAGES]
