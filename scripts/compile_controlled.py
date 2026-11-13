"""Compile a finished controlled session (protocol CS-v1) into tasks/<id> and seal its ground truth.

Usage: python scripts/compile_controlled.py CS-04 more-itertools --pythonpath /work -- tests/test_more.py tests/test_recipes.py

Sealing: the reference contract written by compilation is moved, together with the
scenario and reference proposals, to the scratchpad 'sealed' directory until the
task's verifiers are frozen (decision log D12). `--unseal` restores them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from tracecontract.tasks import compile_controlled_task

R = Path(__file__).resolve().parents[1]
SP = Path("/tmp/claude-0/-home-user-trace-contract/3951c995-db7e-5b4e-a703-97e326bb42c5/scratchpad")


def seal(tid: str) -> None:
    dst = SP / "sealed" / tid
    dst.mkdir(parents=True, exist_ok=True)
    moves = {R / f"tasks/{tid}/contracts/reference.json": dst / "reference_contract.json",
             R / f"data/controlled/scenarios/{tid}.json": dst / "scenario.json",
             R / f"data/controlled/reference/{tid}.json": dst / "reference_proposals.json"}
    for src, d in moves.items():
        if src.exists():
            shutil.move(str(src), str(d))


def unseal(tid: str) -> None:
    src = SP / "sealed" / tid
    (R / "data/controlled/scenarios").mkdir(parents=True, exist_ok=True)
    (R / "data/controlled/reference").mkdir(parents=True, exist_ok=True)
    for s, d in {src / "reference_contract.json": R / f"tasks/{tid}/contracts/reference.json",
                 src / "scenario.json": R / f"data/controlled/scenarios/{tid}.json",
                 src / "reference_proposals.json": R / f"data/controlled/reference/{tid}.json"}.items():
        if s.exists():
            shutil.move(str(s), str(d))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task"); ap.add_argument("repo_dir", nargs="?")
    ap.add_argument("--pythonpath", default="/work"); ap.add_argument("--unseal", action="store_true")
    ap.add_argument("--overlay", action="append", default=[], help="relative path of a generated build artefact in the workspace")
    ap.add_argument("repo_test_args", nargs="*")
    a = ap.parse_args()
    tid = a.task
    if a.unseal:
        unseal(tid)
        print(json.dumps({"unsealed": tid}))
        return
    root = Path(f"/home/user/cs_workspaces/{tid}")
    sc_path = SP / "scenarios" / f"{tid}.json"
    sc = json.loads(sc_path.read_text())
    sc["_sha256"] = hashlib.sha256(sc_path.read_bytes()).hexdigest()
    props = json.loads((SP / "reference" / f"{tid}.json").read_text())
    ws = json.loads((root / "workspace_record.json").read_text())
    overlays = {rel: (root / a.repo_dir / rel).read_text() for rel in a.overlay}
    tdir = compile_controlled_task(
        scenario=sc, reference_proposals=props, transcript=root / "transcript.sanitized.jsonl",
        states={"after_U1": root / "states/after_U1", "final": root / "states/final"}, workspace_record=ws,
        tasks_root=R / "tasks", snapshot_root=R / "snapshots", cache_dir=Path.home() / ".cache/tracecontract",
        repo_test_args=a.repo_test_args, candidate_pythonpath=a.pythonpath, allowed_roots=(str(root),), overlays=overlays)
    # Keep copies of the scenario + reference proposals with the sealed material (restored at unseal).
    dst = SP / "sealed" / tid
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sc_path, dst / "scenario.json")
    shutil.copyfile(SP / "reference" / f"{tid}.json", dst / "reference_proposals.json")
    seal(tid)
    print(json.dumps({"compiled": str(tdir), "sealed": str(dst)}))


if __name__ == "__main__":
    main()
