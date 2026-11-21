"""Offline checks of the Harbor export (decision log D20, D40).

The wheelhouse download is replaced by an empty directory, so the export tests need
neither network nor Docker; scripts/harbor_validate.sh runs the real Harbor trials.
The grade-script tests run the exported ``tc_harbor_grade.py`` locally against a fake
``/logs`` layout, with a fake ``tc_runner.py`` that plants rewards, reports
incomplete results or hangs. They need root, as the grade script does in Harbor.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import tracecontract.harbor_export as hx
from tracecontract.patches import DEFAULT_PROTECTED
from tracecontract.sandbox.docker_runner import HARNESS_VERSION

FX = Path(__file__).parent / "fixtures" / "harbor_fx01"


@pytest.fixture()
def no_wheelhouse(tmp_path, monkeypatch):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    monkeypatch.setattr(hx, "ensure_wheelhouse", lambda reqs, cache: wh)


def _fixture_copy(tmp_path: Path, **task_changes) -> Path:
    """A copy of the fixture (task and snapshot) with ``task_changes`` applied to its task.json."""
    root = tmp_path / "fx"
    shutil.copytree(FX, root)
    tj = root / "tasks" / "FX-01" / "task.json"
    tj.write_text(json.dumps({**json.loads(tj.read_text()), **task_changes}, indent=2) + "\n")
    return root


def _export(fx: Path, out: Path, **kw) -> Path:
    kw.setdefault("network", "local-validation")
    return hx.export_task(fx / "tasks" / "FX-01", "v1", out, snapshot_root=fx / "snapshots", cache_dir=out.parent / "cache", **kw)


def test_export_layout_from_committed_fixture(tmp_path, no_wheelhouse):
    assert (FX / "snapshots" / "FX-01" / "calc.py").is_file()  # base snapshot is tracked (not git-ignored)
    out = _export(FX, tmp_path / "harbor_task", candidates=["FX-01-reference", "FX-01-wrong"])
    assert (out / "tests" / "harness" / "tc_sandbox.py").is_file()
    assert (out / "tests" / "verifier_tests" / "test_add.py").is_file()
    assert (out / "environment" / "app" / "calc.py").read_text() == (FX / "snapshots" / "FX-01" / "calc.py").read_text()
    names = {p.name for p in out.rglob("*")}
    assert "task.toml" in names
    # Held-out candidates never enter the agent environment.
    assert not any("FX-01-wrong" in p.read_text(errors="replace") for p in (out / "environment").rglob("*") if p.is_file())
    sol = [p for p in (out / "solution").rglob("*") if p.is_file()]
    assert sol and any("FX-01-wrong" in p.as_posix() or "FX-01-wrong" in p.read_text(errors="replace") for p in sol)
    toml = (out / "task.toml").read_text()
    assert f'tracecontract_exporter_version = "{hx.EXPORTER_VERSION}"' in toml
    assert f'tracecontract_harness_version = "{HARNESS_VERSION}"' in toml
    assert f'version = "{hx.EXPORTER_VERSION.split("/")[1]}"' in toml
    assert f'EXPORTER = "{hx.EXPORTER_VERSION}"' in (out / "tests" / "tc_harbor_grade.py").read_text()


def test_export_packages_only_the_reference_by_default(tmp_path, no_wheelhouse):
    out = _export(FX, tmp_path / "harbor_task")  # candidates=None
    assert sorted(p.name for p in (out / "solution" / "candidates").iterdir()) == ["reference", "reference.deleted"]
    assert (out / "solution" / "candidates" / "reference" / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"
    # Nothing of the held-out candidate (its id or its code) is in the package.
    files = [p for p in out.rglob("*") if p.is_file() and p.suffix != ".whl"]
    assert not any("FX-01-wrong" in p.as_posix() or "return a - b" in p.read_text(errors="replace") for p in files)


def test_rejected_task_is_refused(tmp_path, no_wheelhouse):
    fx = _fixture_copy(tmp_path, status="rejected")
    out = tmp_path / "harbor_task"
    out.mkdir()
    (out / "keep").write_text("an earlier export")
    with pytest.raises(ValueError, match="rejected"):
        _export(fx, out)
    assert (out / "keep").is_file()  # refused before anything was written or removed
    # The explicit override is for fixtures only.
    _export(fx, out, allow_rejected_fixture=True)
    assert 'tracecontract_status = "rejected"' in (out / "task.toml").read_text()
    ctl = _fixture_copy(tmp_path / "ctl", status="rejected", population="controlled")
    with pytest.raises(ValueError, match="only a fixture"):
        _export(ctl, tmp_path / "ctl_task", allow_rejected_fixture=True)


def test_verifier_changed_after_freezing_is_refused(tmp_path, no_wheelhouse):
    fx = _fixture_copy(tmp_path)
    t = fx / "tasks" / "FX-01" / "verifiers" / "v1" / "tests" / "test_add.py"
    t.write_text(t.read_text() + "\ndef test_added_later():\n    assert True\n")
    with pytest.raises(ValueError, match="frozen hash"):
        _export(fx, tmp_path / "harbor_task")


@pytest.mark.parametrize("kw, match", [
    ({"candidates": ["FX-01-unknown"]}, "unknown candidates"),
    ({"network": "intented"}, "network must be one of"),
    ({"timeout_sec": 30.0}, "timeout_sec must exceed"),
])
def test_invalid_export_arguments_are_refused(tmp_path, no_wheelhouse, kw, match):
    with pytest.raises(ValueError, match=match):
        _export(FX, tmp_path / "harbor_task", **kw)


# --- the grade script, run locally against a fake /logs layout -------------------------------------------

CHECKS = ["test_add.py::test_add", "test_add.py::test_negative"]
PATHS_LINE = 'CAND, TESTS, OUT = "/app", "/tests", "/logs/verifier"'

# A stand-in for tc_runner.py. It records how the grade script left /logs/verifier when the runner started
# (candidate code runs only inside the runner), then acts out one scenario. The root-run ``plant`` stands for a
# planted reward that got past the lock; in ``timeout`` a shell running as the sandbox UID also keeps trying to
# plant one, as candidate code would.
FAKE_RUNNER = r'''
import json, os, subprocess, sys, time
MODE, OUT, BOX = %(mode)r, %(out)r, %(box)r
res = sys.argv[sys.argv.index("--results") + 1]
st = os.stat(OUT)
with open(os.path.join(BOX, "seen.json"), "w") as fh:
    json.dump({"mode": st.st_mode & 0o7777, "uid": st.st_uid, "sandbox_uid": int(os.environ["TC_SANDBOX_UID"])}, fh)


def plant():
    for name, text in (("reward.json", '{"reward": 1.0, "R1": 1.0}'), ("reward.txt", "1.0")):
        with open(os.path.join(OUT, name), "w") as fh:
            fh.write(text)


def results(tests, collect_errors=()):
    with open(os.path.join(res, "results.json"), "w") as fh:
        json.dump({"nonce": os.environ["TC_RUN_NONCE"], "status": "completed", "harness_version": "fake",
                   "tests": [{"nodeid": n, "outcome": o} for n, o in tests], "collect_errors": list(collect_errors),
                   "tamper_events": []}, fh)


CHECKS = %(checks)r
if MODE == "pass":
    results([(c, "passed") for c in CHECKS])
elif MODE == "fail":
    with open(os.path.join(OUT, "reward.txt"), "w") as fh:
        fh.write("1.0")
    results([(CHECKS[0], "passed"), (CHECKS[1], "failed")])
elif MODE == "collect":
    plant()
    os.symlink(os.path.join(BOX, "target.txt"), os.path.join(OUT, "reward.lnk"))
    os.mkdir(os.path.join(OUT, "reward.d"))
    results([], [{"nodeid": "test_add.py", "longrepr": "RuntimeError: collection-time sandbox call failed"}])
elif MODE == "timeout":
    uid = int(os.environ["TC_SANDBOX_UID"])
    loop = 'while :; do if echo 1.0 > "$1/reward.txt"; then echo planted >> "$2"; else echo denied >> "$2"; fi; sleep 0.1; done'
    subprocess.Popen(["/bin/sh", "-c", loop, "sh", OUT, os.path.join(BOX, "attempts", "log")], user=uid, group=uid,
                     extra_groups=[], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    deadline = time.time() + 4
    while time.time() < deadline and not os.path.exists(os.path.join(BOX, "attempts", "log")):
        time.sleep(0.05)
    plant()
    time.sleep(600)
'''


@pytest.fixture()
def box():
    """A world-traversable directory laid out like the verifier container (pytest's tmp_path is root-only)."""
    if os.geteuid() != 0:
        pytest.skip("the grade script runs as root (it makes /logs/verifier root-owned)")
    d = Path(tempfile.mkdtemp(prefix="tc_grade_"))
    d.chmod(0o755)
    (d / "app" / "tests").mkdir(parents=True)
    (d / "app" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (d / "app" / "tests" / "test_calc.py").write_text("def test_placeholder():\n    assert 1 == 1\n")  # protected
    (d / "tests" / "harness").mkdir(parents=True)
    (d / "tests" / "verifier_tests").mkdir()
    (d / "tests" / "base" / "tests").mkdir(parents=True)
    (d / "tests" / "base" / "tests" / "test_calc.py").write_text("def test_placeholder():\n    assert True\n")
    (d / "tests" / "expected_checks.json").write_text(json.dumps([{"check_id": c, "requirement_ids": ["R1"]} for c in CHECKS]))
    (d / "logs" / "verifier").mkdir(parents=True)
    (d / "logs" / "verifier").chmod(0o777)  # as Harbor 0.25.0 leaves it before the test
    (d / "attempts").mkdir()
    (d / "attempts").chmod(0o777)
    (d / "target.txt").write_text("untouched\n")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _run_grade(box: Path, mode: str, runner_timeout: int = 20) -> tuple[subprocess.CompletedProcess, Path]:
    out = box / "logs" / "verifier"
    (box / "tests" / "harness" / "tc_runner.py").write_text(
        FAKE_RUNNER % {"mode": mode, "out": str(out), "box": str(box), "checks": CHECKS})
    script = hx.render_grade_script(DEFAULT_PROTECTED, "/work", runner_timeout)
    assert script.count(PATHS_LINE) == 1
    script = script.replace(PATHS_LINE, f"CAND, TESTS, OUT = {str(box / 'app')!r}, {str(box / 'tests')!r}, {str(out)!r}")
    (box / "grade.py").write_text(script)
    proc = subprocess.run([sys.executable, "-I", str(box / "grade.py")], capture_output=True, text=True, timeout=120)
    return proc, out


def _rewards(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir() if p.name.startswith("reward."))


def _detail(out: Path) -> dict:
    return json.loads((out / "tc_detail.json").read_text())


def _seen(box: Path) -> dict:
    return json.loads((box / "seen.json").read_text())


def _live_pids(uid: int) -> list[int]:
    pids = []
    for entry in filter(str.isdigit, os.listdir("/proc")):
        try:
            status = Path(f"/proc/{entry}/status").read_text()
        except OSError:
            continue
        fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        if str(uid) in fields.get("Uid", "").split() and fields.get("State", "").split()[:1] not in (["Z"], ["X"]):
            pids.append(int(entry))
    return pids


def test_grade_normal_pass(box):
    (box / "logs" / "verifier" / "reward.json").symlink_to(box / "target.txt")  # a stale link must not be followed
    proc, out = _run_grade(box, "pass")
    assert proc.returncode == 0, proc.stderr
    assert _seen(box)["mode"] == 0o700 and _seen(box)["uid"] == 0  # locked before the runner started
    assert _rewards(out) == ["reward.json"] and not (out / "reward.json").is_symlink()
    assert json.loads((out / "reward.json").read_text()) == {"reward": 1.0, "R1": 1.0}
    assert (box / "target.txt").read_text() == "untouched\n"
    d = _detail(out)
    assert d["exporter"] == hx.EXPORTER_VERSION and d["checks"] == {c: "passed" for c in CHECKS}
    assert d["removed_protected"] == ["tests/test_calc.py"]
    st = out.stat()
    assert st.st_uid == 0 and st.st_mode & 0o777 == 0o755  # readable for the host side, writable by root only


def test_grade_normal_fail_removes_planted_reward(box):
    proc, out = _run_grade(box, "fail")
    assert proc.returncode == 0, proc.stderr
    assert _rewards(out) == ["reward.json"]
    assert json.loads((out / "reward.json").read_text()) == {"reward": 0.0, "R1": 0.0}
    assert _detail(out)["removed_reward_files"] == ["reward.txt"]


def test_grade_planted_reward_and_collection_error(box):
    proc, out = _run_grade(box, "collect")
    assert proc.returncode == 3, proc.stderr
    assert _rewards(out) == []
    assert (box / "target.txt").read_text() == "untouched\n"  # the planted link was removed, not followed
    d = _detail(out)
    assert d["removed_reward_files"] == ["reward.d", "reward.json", "reward.lnk", "reward.txt"]
    assert d["error"].startswith("incomplete grade") and d["collect_errors"][0]["nodeid"] == "test_add.py"
    assert set(d["checks"].values()) == {"missing"}


def test_grade_planted_reward_and_timeout(box):
    proc, out = _run_grade(box, "timeout", runner_timeout=6)
    assert proc.returncode == 3, proc.stderr
    assert _rewards(out) == []
    d = _detail(out)
    assert d["error"] == "grader timed out after 6 s"
    assert d["removed_reward_files"] == ["reward.json", "reward.txt"]
    assert d["reaped_sandbox_processes"] >= 1
    attempts = (box / "attempts" / "log").read_text().split()
    assert attempts and set(attempts) == {"denied"}  # the sandbox UID could not write /logs/verifier
    assert _live_pids(_seen(box)["sandbox_uid"]) == []  # nothing the sandbox UID started survived the grade script
