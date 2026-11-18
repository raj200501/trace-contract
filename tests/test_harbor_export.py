"""Offline check of the Harbor export layout on the committed fixture task (decision log D20, D40).

The wheelhouse download is replaced by an empty directory, so the test needs neither
network nor Docker; scripts/harbor_validate.sh runs the real Harbor trials.
"""

from __future__ import annotations

import json
from pathlib import Path

import tracecontract.harbor_export as hx

FX = Path(__file__).parent / "fixtures" / "harbor_fx01"


def test_export_layout_from_committed_fixture(tmp_path, monkeypatch):
    wh = tmp_path / "wheelhouse"
    wh.mkdir()
    monkeypatch.setattr(hx, "ensure_wheelhouse", lambda reqs, cache: wh)
    assert (FX / "snapshots" / "FX-01" / "calc.py").is_file()  # base snapshot is tracked (not git-ignored)
    out = tmp_path / "harbor_task"
    hx.export_task(FX / "tasks" / "FX-01", "v1", out, snapshot_root=FX / "snapshots", cache_dir=tmp_path / "cache",
                   candidates=["FX-01-reference", "FX-01-wrong"], network="local-validation")
    assert (out / "tests" / "harness" / "tc_sandbox.py").is_file()
    assert (out / "tests" / "verifier_tests" / "test_add.py").is_file()
    assert (out / "environment" / "app" / "calc.py").read_text() == (FX / "snapshots" / "FX-01" / "calc.py").read_text()
    names = {p.name for p in out.rglob("*")}
    assert "task.toml" in names
    # Held-out candidates never enter the agent environment.
    assert not any("FX-01-wrong" in p.read_text(errors="replace") for p in (out / "environment").rglob("*") if p.is_file())
    sol = [p for p in (out / "solution").rglob("*") if p.is_file()]
    assert sol and any("FX-01-wrong" in p.as_posix() or "FX-01-wrong" in p.read_text(errors="replace") for p in sol)
