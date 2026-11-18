"""Record held-out candidates whose code duplicates another candidate's (decision log D40).

Usage: python scripts/find_duplicates.py tasks/CS-01 [tasks/CS-02 ...] [--check]

Writes ``tasks/<id>/labels/duplicates.json`` (see ``tracecontract.duplicates``). With
``--check`` nothing is written; the exit code is 1 if a recorded file is missing or
differs from what the candidates and the base snapshot give now (used by
``scripts/preflight_final_run.py``). Needs the base snapshots (``tracecontract snapshot``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tracecontract.cli import SNAPSHOTS
from tracecontract.duplicates import same_code_duplicates
from tracecontract.tasks import verify_snapshot


def main(*args: str) -> int:
    check = "--check" in args
    bad = 0
    for td in (Path(a) for a in args if a != "--check"):
        if not verify_snapshot(td, SNAPSHOTS):
            print(f"{td.name}: base snapshot missing or modified (run `tracecontract snapshot {td}`)")
            bad += 1
            continue
        rec = same_code_duplicates(td, SNAPSHOTS)
        out = td / "labels" / "duplicates.json"
        text = json.dumps(rec, indent=2, sort_keys=True) + "\n"
        if check:
            if not out.exists() or out.read_text() != text:
                print(f"{td.name}: {out} is missing or out of date: {rec['duplicates']}")
                bad += 1
        else:
            out.write_text(text)
            print(f"{td.name}: {len(rec['duplicates'])} same-code duplicate(s) {rec['duplicates']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
