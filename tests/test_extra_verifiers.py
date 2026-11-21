"""Label-support verifiers registered beside a frozen task (verifiers_extra.json; protocol §15.5).

Synthetic fixture tasks only (a temporary directory); the recorded tasks are read, never written.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tracecontract.evaluate import EXTRA_VERIFIERS, extra_verifier_paths, load_task

REPO = Path(__file__).resolve().parents[1]


def test_recorded_tasks_register_the_independent_labeler_only_in_the_sidecar():
    for t in ("CS-01", "CS-02", "CS-03", "CS-04"):
        tdir = REPO / "tasks" / t
        m, specs, _ = load_task(tdir)
        assert "verifiers/independent_label/spec.json" not in m.verifiers  # task.json is frozen
        assert "independent_label" not in {s.verifier_id for s in specs}
        assert extra_verifier_paths(tdir) == ["verifiers/independent_label/spec.json"]
        _, with_extra, _ = load_task(tdir, extra=True)
        ids = [s.verifier_id for s in with_extra]
        assert ids.count("independent_label") == 1 and len(ids) == len(specs) + 1
        lab = json.loads((tdir / "verifiers" / "independent_label" / "spec.json").read_text())
        assert lab["frozen"] is True and lab["condition"] == "reference_check"
        status = json.loads((tdir / "verifiers" / "independent_label" / "status.json").read_text())
        assert status["status"] == "usable"


def test_missing_sidecar_means_no_extra_verifiers(tmp_path):
    assert extra_verifier_paths(tmp_path) == []
    (tmp_path / EXTRA_VERIFIERS).write_text(json.dumps({"verifiers": ["verifiers/x/spec.json"]}))
    assert extra_verifier_paths(tmp_path) == ["verifiers/x/spec.json"]


def test_build_verifier_sidecar_leaves_task_json_unchanged(tmp_path, monkeypatch):
    import shutil
    from tracecontract import cli
    src = REPO / "tasks" / "CS-03"
    t = tmp_path / "CS-03"
    shutil.copytree(src, t, ignore=shutil.ignore_patterns("candidates", "labels", "strata"))
    (t / EXTRA_VERIFIERS).unlink()
    before = hashlib.sha256((t / "task.json").read_bytes()).hexdigest()
    vdir = t / "verifiers" / "independent_label2"
    shutil.copytree(t / "verifiers" / "independent_label" / "tests", vdir / "tests")
    rec = json.loads((t / "verifiers" / "independent_label" / "spec.json").read_text())["generation"]
    b = rec["budget"]
    args = ["build-verifier", str(t), "independent_label2", "--condition", "reference_check", "--contract-id", "CS-03-reference",
            "--sidecar", "--gen-run-id", rec["run_id"], "--config", rec["generator"], "--prompt-sha256", rec["prompt_sha256"],
            "--started-at", b["started_at"], "--ended-at", b["ended_at"], "--wall-s", str(b["wall_s"]),
            "--tool-calls", str(b["tool_calls"]), "--run-record", b["run_record"]]
    if b.get("turns") is not None:
        args += ["--turns", str(b["turns"])]
    if b.get("tokens") is not None:
        args += ["--tokens", str(b["tokens"])]
    monkeypatch.setattr(cli, "_out", lambda obj: None)
    cli.main(args)
    assert hashlib.sha256((t / "task.json").read_bytes()).hexdigest() == before
    assert extra_verifier_paths(t) == ["verifiers/independent_label2/spec.json"]
