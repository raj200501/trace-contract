"""Record held-out candidates whose code duplicates another candidate's (decision log D40).

Usage: python scripts/find_duplicates.py tasks/CS-01 [tasks/CS-02 ...] [--check]
       python scripts/find_duplicates.py data/natural/tasks/NP-03 [--check]

Writes ``<task dir>/labels/duplicates.json`` (see ``tracecontract.duplicates``). With
``--check`` nothing is written; the exit code is 1 if a recorded file is missing or
differs from what the candidates and the base snapshot give now (used by
``scripts/preflight_final_run.py``).

Each task's base snapshot is the one ``roots.snapshot_root`` names, and it must match the
task's ``snapshot.json``: ``snapshots/<id>`` (``tracecontract snapshot``), or
``data/natural/snapshots/<id>`` for a natural PR-review task (built by ``tracecontract
compile-pr-task``; never looked for under ``snapshots/``). Held-out candidates are compared
with the development candidates (for a natural task, the dev attacks with the pre-review
state among the held-out ones) and with each other, the natural state first, so a
constructed candidate that reproduces the pre-review state is listed as its duplicate
(``duplicates.representative_order``).

A task whose recorded snapshot root is unusable (``roots.RootError``) fails, and the record
is never written through a symbolic link (``labels/`` or ``labels/duplicates.json``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tracecontract import roots
from tracecontract.duplicates import same_code_duplicates
from tracecontract.tasks import verify_snapshot

REPO = roots.REPO  # the repository under which roots.snapshot_root resolves a task's recorded snapshot root


def main(*args: str) -> int:
    check = "--check" in args
    bad = 0
    for td in (Path(a) for a in args if a != "--check"):
        try:
            root = roots.snapshot_root(td, repo=REPO)
        except roots.RootError as exc:
            print(f"{td.name}: {exc}")
            bad += 1
            continue
        if not verify_snapshot(td, root):
            if roots.is_natural_pr(td):
                print(f"{td.name}: base snapshot missing or modified under {root} (a natural PR-review task's base is built "
                      "by `tracecontract compile-pr-task`)")
            else:
                print(f"{td.name}: base snapshot missing or modified (run `tracecontract snapshot {td}`)")
            bad += 1
            continue
        rec = same_code_duplicates(td, root)
        out = td / "labels" / "duplicates.json"
        text = json.dumps(rec, indent=2, sort_keys=True) + "\n"
        link = next((p for p in (out.parent, out) if p.is_symlink()), None)  # labels/ or the record itself
        if check:
            if not out.exists() or out.read_text() != text:
                print(f"{td.name}: {out} is missing or out of date: {rec['duplicates']}")
                bad += 1
        elif link is not None:
            print(f"{td.name}: {link} is a symbolic link; the record is not written through it")
            bad += 1
        else:
            out.parent.mkdir(exist_ok=True)
            out.write_text(text)
            print(f"{td.name}: {len(rec['duplicates'])} same-code duplicate(s) {rec['duplicates']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
