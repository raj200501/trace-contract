"""Unit tests: patch policy, leakage detection, verifier linting, aggregation, metrics, audit.

Synthetic fixtures only; no Docker required.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tracecontract.audit import run_audit
from tracecontract.metrics import Row, paired_difference, summarize
from tracecontract.patches import apply_patch, diff_dirs, filter_patch
from tracecontract.sandbox.docker_runner import HARNESS_VERSION, RawRun, aggregate
from tracecontract.schemas import (
    Candidate,
    CandidateOrigin,
    CheckSpec,
    Isolation,
    Label,
    LabelerKind,
    Outcome,
    Split,
    VerificationResult,
    VerifierCondition,
    VerifierSpec,
    sha256_text,
)
from tracecontract.snapshot import leakage_check
from tracecontract.verifier import build_spec, check_frozen, discover_checks, freeze, lint_process_separated


def _tree(root: Path, files: dict[str, str]) -> Path:
    for k, v in files.items():
        p = root / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v)
    return root


# --------------------------------------------------------------------------- patches


def test_diff_and_apply_roundtrip(tmp_path):
    base = _tree(tmp_path / "base", {"pkg/a.py": "x = 1\n", "README": "hi\n"})
    new = _tree(tmp_path / "new", {"pkg/a.py": "x = 2\n", "pkg/b.py": "y = 3\n", "README": "hi\n"})
    patch = diff_dirs(base, new)
    assert "a/pkg/a.py" in patch and "b/pkg/b.py" in patch
    ws, _ = apply_patch(base, patch, tmp_path / "ws")
    assert (ws / "pkg/a.py").read_text() == "x = 2\n" and (ws / "pkg/b.py").read_text() == "y = 3\n"


@pytest.mark.parametrize("bad_path, reason", [
    ("../../etc/passwd", "parent-directory"),
    ("/etc/passwd", "absolute"),
    (".git/config", ".git"),
])
def test_filter_rejects_unsafe_paths(bad_path, reason):
    patch = f"diff --git a/{bad_path} b/{bad_path}\n--- a/{bad_path}\n+++ b/{bad_path}\n@@ -1 +1 @@\n-a\n+b\n"
    _, rep = filter_patch(patch)
    assert not rep.ok and any(reason in e for e in rep.errors)


def test_filter_rejects_binary_and_symlink():
    binary = "diff --git a/x.bin b/x.bin\nGIT binary patch\nliteral 1\nAA\n"
    assert not filter_patch(binary)[1].ok
    link = "diff --git a/l b/l\nnew file mode 120000\n--- /dev/null\n+++ b/l\n@@ -0,0 +1 @@\n+/etc/passwd\n"
    assert not filter_patch(link)[1].ok


def test_filter_strips_protected_test_files(tmp_path):
    base = _tree(tmp_path / "base", {"src/m.py": "a = 1\n", "tests/test_m.py": "def test(): pass\n", "conftest.py": ""})
    new = _tree(tmp_path / "new", {"src/m.py": "a = 2\n", "tests/test_m.py": "def test(): assert True\n", "conftest.py": "import os\n"})
    approved, rep = filter_patch(diff_dirs(base, new))
    assert rep.ok
    assert rep.accepted_paths == ["src/m.py"]
    assert set(rep.removed_protected) == {"tests/test_m.py", "conftest.py"}
    assert "tests/test_m.py" not in approved


def test_leakage_check_detects_solution_in_snapshot(tmp_path):
    base = _tree(tmp_path / "base", {"m.py": "old\n"})
    solved = _tree(tmp_path / "solved", {"m.py": "new\n"})
    patch = diff_dirs(base, solved)
    assert leakage_check(base, patch).passed
    leaky = leakage_check(solved, patch, reference_base=base)
    assert not leaky.passed and leaky.leaked_paths == ["m.py"]
    (base / ".git").mkdir()
    assert ".git" in leakage_check(base, patch).leaked_paths


# --------------------------------------------------------------------------- verifier


GOOD_TEST = textwrap.dedent('''
    from tc_sandbox import run_python

    def test_value():
        r = run_python("from m import f\\nresult = f(2)")
        assert r.ok, r
        assert r.value == 4
''')


def test_discover_and_lint(tmp_path):
    d = _tree(tmp_path / "v", {"test_a.py": GOOD_TEST})
    assert discover_checks(d) == ["test_a.py::test_value"]
    assert lint_process_separated(d) == []
    bad = _tree(tmp_path / "bad", {"test_b.py": textwrap.dedent('''
        import pytest
        import mypkg
        from tc_sandbox import run_python

        def test_ok_only():
            r = run_python("import m")
            assert r.ok

        @pytest.mark.parametrize("x", [1, 2])
        def test_param(x):
            r = run_python("result = 1")
            assert r.value == 1

        def test_write():
            open("/results/results.json", "w").write("{}")
            assert True
    ''')})
    codes = {i.code for i in lint_process_separated(bad)}
    assert {"forbidden_import", "ok_only", "parametrized", "forbidden_write"} <= codes


def test_freeze_detects_modification(tmp_path):
    task = tmp_path / "task"
    d = _tree(task / "verifiers" / "v1", {"test_a.py": GOOD_TEST})
    spec = build_spec(verifier_id="v1", task_id="t", condition=VerifierCondition.full_plain, test_dir=d, task_dir=task)
    frozen = freeze(spec, task)
    check_frozen(frozen, task)
    (d / "test_a.py").write_text(GOOD_TEST + "\n# edited\n")
    with pytest.raises(ValueError, match="frozen verifier was modified"):
        check_frozen(frozen, task)


# --------------------------------------------------------------------------- aggregation


def _spec(isolation=Isolation.process_separated):
    return VerifierSpec(verifier_id="v", task_id="t", condition=VerifierCondition.full_plain, isolation=isolation,
                        test_dir="tests", checks=[CheckSpec(check_id="test_a.py::t1"), CheckSpec(check_id="test_a.py::t2")],
                        content_sha256="x")


def _raw(results=None, **kw):
    base = dict(exit_code=0, timed_out=False, results=results, stdout="", stderr="", wall_s=1.0)
    base.update(kw)
    return RawRun(**base)


def _res(nonce="n", tests=(("test_a.py::t1", "passed"), ("test_a.py::t2", "passed")), **kw):
    d = {"nonce": nonce, "status": "completed", "harness_version": HARNESS_VERSION,
         "tests": [{"nodeid": n, "outcome": o, "duration": 0.1, "longrepr": ""} for n, o in tests],
         "collect_errors": [], "tamper_events": []}
    d.update(kw)
    return d


@pytest.mark.parametrize("raw, expected", [
    (_raw(_res()), Outcome.passed),
    (_raw(None), Outcome.verifier_error),  # missing results file
    (_raw(_res(nonce="stale")), Outcome.verifier_error),  # stale/foreign results
    (_raw(_res(status="harness_error", error="boom")), Outcome.verifier_error),
    (_raw(_res(tests=(("test_a.py::t1", "passed"),))), Outcome.verifier_error),  # missing check
    (_raw(_res(tests=(("test_a.py::t1", "passed"), ("test_a.py::t2", "failed")))), Outcome.task_failure),
    (_raw(_res(tests=(("test_a.py::t1", "passed"), ("test_a.py::t2", "error")))), Outcome.verifier_error),
    (_raw(_res(tests=(("test_a.py::t1", "passed"), ("test_a.py::t2", "skipped")))), Outcome.verifier_error),
    (_raw(_res(tests=(("test_a.py::t1", "passed"), ("test_a.py::t2", "passed"), ("test_a.py::t3", "passed")))), Outcome.verifier_error),
    (_raw(_res(collect_errors=[{"nodeid": "test_a.py", "longrepr": "SyntaxError"}])), Outcome.verifier_error),
    (_raw(None, timed_out=True, exit_code=None), Outcome.timeout),
    (_raw(None, docker_error="docker run failed (125)"), Outcome.environment_failure),
])
def test_aggregate_outcomes(raw, expected):
    outcome, _, _ = aggregate(raw, _spec(), "n")
    assert outcome == expected


def test_aggregate_never_passes_without_results_even_if_exit_zero():
    outcome, _, diags = aggregate(_raw(None, exit_code=0), _spec(), "n")
    assert outcome != Outcome.passed and "no results" in diags[0]


def test_in_process_errors_count_as_task_failure():
    raw = _raw(_res(tests=(("test_a.py::t1", "passed"), ("test_a.py::t2", "error"))))
    assert aggregate(raw, _spec(Isolation.in_process), "n")[0] == Outcome.task_failure


def test_reward_invariant():
    with pytest.raises(ValueError):
        VerificationResult(run_id="r", task_id="t", verifier_id="v", candidate_id="c", outcome=Outcome.task_failure,
                           reward=1.0, started_at="s", finished_at="f", wall_s=0, harness_version="h")


# --------------------------------------------------------------------------- metrics


def _rows():
    rows = []
    # family f1: task t1 ; family f2: task t2
    for task, fam in (("t1", "f1"), ("t2", "f2")):
        rows += [
            Row(task, fam, "neg", "initial", "pass", "invalid"),
            Row(task, fam, "pos", "initial", "task_failure", "valid"),
            Row(task, fam, "neg", "full", "task_failure", "invalid"),
            Row(task, fam, "pos", "full", "pass", "valid"),
            Row(task, fam, "amb", "full", "pass", "ambiguous"),
            Row(task, fam, "inf", "full", "verifier_error", "invalid"),
        ]
    return rows


def test_summarize_rates():
    s = summarize(_rows(), condition="initial", n_boot=200)
    assert s.fa.value == 1.0 and s.fr.value == 1.0 and s.fa_macro == 1.0
    f = summarize(_rows(), condition="full", n_boot=200)
    assert f.fa.num == 0 and f.fa.den == 4  # infra counted as rejection in the primary analysis
    assert f.excluded_unlabeled == 2 and f.infra.num == 2
    fx = summarize(_rows(), condition="full", exclude_infra=True, n_boot=200)
    assert fx.fa.den == 2
    assert f.fa_ci is not None


def test_paired_difference():
    d = paired_difference(_rows(), "initial", "full", "fa", n_boot=200)
    assert d["difference"] == pytest.approx(1.0) and d["n_families"] == 2
    assert d["discordant"]["a_accepts_b_rejects"] == 2


def test_single_family_has_no_ci():
    rows = [r for r in _rows() if r.family_id == "f1"]
    assert summarize(rows, condition="initial", n_boot=100).fa_ci is None


# --------------------------------------------------------------------------- audit


def _cand(cid, origin, split=Split.dev, violated=()):
    labels = [Label(value="invalid", violated_requirements=list(violated), labeler="gen", labeler_kind=LabelerKind.construction,
                    timestamp="t")] if violated else []
    return Candidate(candidate_id=cid, task_id="t", origin=origin, split=split, patch="", patch_sha256=sha256_text(""),
                     produced_by="fixture", labels=labels)


def test_audit_findings_and_holdout_guard(tmp_path):
    task = tmp_path
    _tree(task / "tests", {"test_a.py": GOOD_TEST})
    spec = _spec().model_copy(update={"checks": [CheckSpec(check_id="test_a.py::t1", requirement_ids=["R1"]),
                                                 CheckSpec(check_id="test_a.py::t2", requirement_ids=[])]})
    outcomes = {"ref": Outcome.passed, "noop": Outcome.task_failure, "atk": Outcome.passed, "alt": Outcome.task_failure}

    def grade(s, c, repeats):
        oc = outcomes[c.candidate_id]
        return VerificationResult(run_id="r", task_id="t", verifier_id="v", candidate_id=c.candidate_id, outcome=oc,
                                  reward=1.0 if oc == Outcome.passed else 0.0, started_at="s", finished_at="f",
                                  wall_s=0, harness_version="h")

    dev = [_cand("ref", CandidateOrigin.reference), _cand("noop", CandidateOrigin.noop),
           _cand("atk", CandidateOrigin.dev_attack, violated=["R1"]), _cand("alt", CandidateOrigin.valid_alternative)]
    rep = run_audit(spec, None, dev, grade, task_dir=task)
    codes = {f.code for f in rep.findings}
    assert not rep.passed and {"false_acceptance_dev", "false_rejection_dev"} <= codes
    with pytest.raises(ValueError, match="held out"):
        run_audit(spec, None, [_cand("e", CandidateOrigin.constructed_near_miss, split=Split.eval)], grade, task_dir=task)
