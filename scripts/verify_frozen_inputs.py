"""Verify that the frozen pilot's inputs and outputs are unchanged; run it at the end of every phase.

Usage: .venv/bin/python scripts/verify_frozen_inputs.py [--rev c5ede4c] [--run results/runs/pilot-v0.3.3] [--allow-preexisting]

Checks against the frozen commit ``--rev``:

a. every file listed in the run's ``analysis.json`` under ``meta.inputs.files_sha256`` (135 for
   ``pilot-v0.3.3``) still has the recorded hash, with one exemption, for analysis code: a ``code/``
   key (a file under ``src/tracecontract/``) whose file changed since the run is reported as info
   and not counted as a difference. Analysis code may change after the run only as long as the
   outputs regenerate identically, which (d) checks; a code file that is missing is a difference;
b. git shows no difference between the commit and the working tree in the run directory, and
   no untracked file there;
c. ``experiments/protocol.md`` and ``docs/decision_log.md`` at the commit are byte prefixes of
   the current files (append-only);
d. ``tracecontract analyze <run> --allow-proposed-labels`` and ``tracecontract report`` regenerate
   ``analysis.md``, ``report.html`` and ``analysis.json`` in a temporary copy of the run directory
   (``manifest.json`` and ``results.jsonl`` only; never in place), byte for byte;
   ``analysis.json`` may differ only in the recorded git revision and, under the exemption of (a),
   in the recorded hashes of analysis code that changed since the run (reported as info);
e. (additional) no tracked frozen file is modified or deleted: every run directory under
   ``results/runs/`` at the commit, ``tasks/CS-0*/{task,provenance,snapshot}.json``, ``candidates/``, ``contracts/``,
   ``verifiers/``, ``labels/``, ``data/controlled/``, ``experiments/prompts/``,
   ``paper/evidence_ledger.md`` and ``paper/generated/*.tex``; new files are counted, not refused.
   There is no exemption here: a provenance record that differs only in its ``triage`` field is a
   modified frozen file. Triage proposals are kept in the sidecars ``tasks/<id>/triage.json``
   (decision log D47, D50);
f. (additional) every base snapshot ``snapshots/<id>`` has the manifest in ``tasks/<id>/snapshot.json``.

A difference that already exists at the frozen commit is reported as pre-existing: a hashed data
file (not analysis code, which falls under the exemption of (a)) whose content at the commit
already differs from the recorded hash and that has not changed since. Exit status 1 on any
difference; ``--allow-preexisting`` accepts the pre-existing ones. One summary line goes to stdout,
the details (the info lines first) to stderr.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FROZEN_REV = "c5ede4c"
RUN = "results/runs/pilot-v0.3.3"
EXPECTED_INPUTS = {"results/runs/pilot-v0.3.3": 135}
APPEND_ONLY = ("experiments/protocol.md", "docs/decision_log.md")
FROZEN_PATHS = ("data/controlled", "experiments/prompts", "paper/evidence_ledger.md", "paper/generated")
FROZEN_TASK_PARTS = ("task.json", "provenance.json", "snapshot.json", "candidates", "contracts", "verifiers", "labels")
_REVISION = re.compile(rb'"git_revision": (?:null|"[^"]*")')


class Findings:
    def __init__(self) -> None:
        self.new: list[str] = []
        self.preexisting: list[str] = []
        self.info: list[str] = []
        self.summary: dict[str, str] = {}

    def add(self, check: str, text: str, *, preexisting: bool = False) -> None:
        (self.preexisting if preexisting else self.new).append(f"({check}) {text}")


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, check=True).stdout


def _at_rev(rev: str, rel: str) -> bytes | None:
    try:
        return _git("show", f"{rev}:{rel}")
    except subprocess.CalledProcessError:
        return None


def _sha(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def _input_path(key: str, run: str) -> str:
    """Repository path of a ``files_sha256`` key (as ``analysis._input_hashes`` writes them)."""
    if key in ("results.jsonl", "manifest.json"):
        return f"{run}/{key}"
    if key.startswith("code/"):
        return f"src/tracecontract/{key[5:]}"
    return f"tasks/{key}"


def check_input_hashes(f: Findings, rev: str, run: str, recorded: dict[str, str]) -> dict[str, str]:
    """(a); returns ``{key: 'ok'|'pre-existing'|'new'}``."""
    status = {}
    for key, want in sorted(recorded.items()):
        rel = _input_path(key, run)
        p = REPO / rel
        cur = _sha(p.read_bytes()) if p.is_file() else None
        if cur == want:
            status[key] = "ok"
            continue
        frozen = _sha(_at_rev(rev, rel))
        pre = frozen is not None and frozen != want and cur == frozen
        what = "missing" if cur is None else f"sha256 {cur[:12]} != recorded {want[:12]}"
        if key.startswith("code/") and cur is not None:
            # Analysis code may change after the run as long as the outputs regenerate
            # identically, which (d) checks. Reported, not counted as a difference.
            status[key] = "code-changed"
            f.info.append(f"(a) {key}: {what}; code changed since the run (outputs checked by (d))")
            continue
        status[key] = "pre-existing" if pre else "new"
        f.add("a", f"{key}: {what}" + (f" (already so at {rev})" if pre else ""), preexisting=pre)
    n_ok = sum(v == "ok" for v in status.values())
    expect = EXPECTED_INPUTS.get(run)
    if expect is not None and len(recorded) != expect:
        f.add("a", f"analysis.json lists {len(recorded)} input files, expected {expect}")
    f.summary["a"] = f"{n_ok}/{len(recorded)} input hashes match"
    return status


def check_run_dir(f: Findings, rev: str, run: str) -> None:
    """(b)"""
    diff = _git("diff", "--name-status", "--no-renames", rev, "--", run).decode().splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", run).decode().splitlines()
    for ln in diff:
        f.add("b", f"{run}: {ln.replace(chr(9), ' ')} since {rev}")
    for ln in untracked:
        f.add("b", f"{run}: untracked {ln}")
    f.summary["b"] = "run directory unchanged" if not diff and not untracked else f"{len(diff) + len(untracked)} change(s) in the run directory"


def check_append_only(f: Findings, rev: str) -> None:
    """(c)"""
    bad = 0
    for rel in APPEND_ONLY:
        old, p = _at_rev(rev, rel), REPO / rel
        if old is None:
            f.add("c", f"{rel}: not in {rev}")
            bad += 1
        elif not p.is_file() or not p.read_bytes().startswith(old):
            cur = p.read_bytes() if p.is_file() else b""
            at = next((i for i, (x, y) in enumerate(zip(old, cur)) if x != y), min(len(old), len(cur)))
            line = old[:at].count(b"\n") + 1
            f.add("c", f"{rel}: the text at {rev} is not a prefix of the current file (first difference at line {line})")
            bad += 1
    f.summary["c"] = "protocol and decision log append-only" if not bad else f"{bad} append-only file(s) rewritten"


def _json_diff(a, b, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        return [d for k in sorted(set(a) | set(b)) for d in _json_diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _json_diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [path]


def check_regeneration(f: Findings, run: str, input_status: dict[str, str]) -> None:
    """(d) in a temporary copy of the run directory."""
    src = REPO / run
    tmp = Path(tempfile.mkdtemp(prefix="tc_frozen_"))
    try:
        copy = tmp / src.name
        copy.mkdir()
        for name in ("manifest.json", "results.jsonl"):
            shutil.copy2(src / name, copy / name)
        cli = [sys.executable, "-m", "tracecontract.cli"]
        for argv in (["analyze", str(copy), "--allow-proposed-labels"], ["report", str(copy), "--out", str(copy / "report.html")]):
            p = subprocess.run(cli + argv, cwd=tmp, capture_output=True, text=True)
            if p.returncode != 0:
                f.add("d", f"`tracecontract {argv[0]}` failed: {p.stderr.strip()[-300:]}")
                f.summary["d"] = "regeneration failed"
                return
        same = []
        for name in ("analysis.md", "report.html"):
            if (copy / name).read_bytes() == (src / name).read_bytes():
                same.append(name)
            else:
                f.add("d", f"{name} does not regenerate byte for byte")
        new, old = (copy / "analysis.json").read_bytes(), (src / "analysis.json").read_bytes()
        if len(_REVISION.findall(new)) != 1 or len(_REVISION.findall(old)) != 1:
            f.add("d", "analysis.json: the git revision field is not found exactly once")
        elif _REVISION.sub(b"", new) == _REVISION.sub(b"", old):
            same.append("analysis.json (except the git revision)")
        else:
            paths = [p for p in _json_diff(json.loads(old), json.loads(new)) if p != "meta.inputs.git_revision"]
            prefix = "meta.inputs.files_sha256."
            pre = [p for p in paths if p.startswith(prefix) and input_status.get(p[len(prefix):]) == "pre-existing"]
            code = [p for p in paths if p.startswith(prefix + "code/")]
            for p in code:
                f.info.append(f"(d) analysis.json differs at {p}: the recorded hash of analysis code that changed since the run")
            paths = [p for p in paths if p not in code]
            if not paths:
                same.append("analysis.json (except the git revision and the hashes of changed analysis code)")
            for p in paths:
                f.add("d", f"analysis.json differs at {p}" + (" (an input hash that was already off at the frozen commit)"
                                                               if p in pre else ""), preexisting=p in pre)
            if not paths and not code:
                f.add("d", "analysis.json differs only in formatting")
        f.summary["d"] = "regenerated identically: " + (", ".join(same) or "nothing")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_frozen_files(f: Findings, rev: str) -> None:
    """(e) tracked frozen files: modifications and deletions since ``rev``."""
    tasks = [t for t in _git("ls-tree", "--name-only", rev, "tasks/").decode().split() if fnmatch.fnmatch(t, "tasks/CS-0*")]
    runs = _git("ls-tree", "-d", "--name-only", rev, "results/runs/").decode().split()  # every existing run, not the index
    specs = list(FROZEN_PATHS) + runs + [f"{t}/{part}" for t in tasks for part in FROZEN_TASK_PARTS]
    rows = [ln.split("\t", 1) for ln in _git("diff", "--name-status", "--no-renames", rev, "--", *specs).decode().splitlines()]
    rows = [(s, p) for s, p in rows if not p.startswith("paper/generated/") or p.endswith(".tex")]
    added = [p for s, p in rows if s == "A"]
    added += _git("ls-files", "--others", "--exclude-standard", "--", *specs).decode().splitlines()
    changed = [(s, p) for s, p in rows if s != "A"]
    for s, p in changed:
        f.add("e", f"{p}: {'deleted' if s == 'D' else 'modified'} since {rev}")
    f.summary["e"] = f"{len(changed)} frozen file(s) changed, {len(added)} new file(s) beside them"


def check_snapshots(f: Findings) -> None:
    """(f) base snapshot manifests."""
    from tracecontract.snapshot import manifest, manifest_sha256

    tdirs = sorted(p for p in (REPO / "tasks").glob("CS-0*") if (p / "snapshot.json").is_file())
    ok = 0
    for t in tdirs:
        want = json.loads((t / "snapshot.json").read_text(encoding="utf-8"))["file_manifest_sha256"]
        base = REPO / "snapshots" / t.name
        got = manifest_sha256(manifest(base)) if base.is_dir() else None
        if got == want:
            ok += 1
        else:
            f.add("f", f"snapshots/{t.name}: " + ("not built" if got is None else f"manifest {got[:12]} != snapshot.json {want[:12]}"))
    f.summary["f"] = f"{ok}/{len(tdirs)} snapshots match"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rev", default=FROZEN_REV, help="the frozen commit")
    ap.add_argument("--run", default=RUN, help="the frozen run directory, relative to the repository")
    ap.add_argument("--allow-preexisting", action="store_true",
                    help="exit 0 if the only differences already existed at the frozen commit")
    a = ap.parse_args(argv)
    f = Findings()
    try:
        recorded = json.loads((REPO / a.run / "analysis.json").read_text(encoding="utf-8"))["meta"]["inputs"]["files_sha256"]
        status = check_input_hashes(f, a.rev, a.run, recorded)
        check_run_dir(f, a.rev, a.run)
        check_append_only(f, a.rev)
        check_regeneration(f, a.run, status)
        check_frozen_files(f, a.rev)
        check_snapshots(f)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, ImportError) as exc:
        f.add("-", f"verification could not run: {type(exc).__name__}: {exc}")
    for line in f.info:
        print("info: " + line, file=sys.stderr)
    for line in f.new + f.preexisting:
        print(line, file=sys.stderr)
    ok = not f.new and (a.allow_preexisting or not f.preexisting)
    verdict = "OK" if ok and not f.preexisting else "OK (pre-existing differences accepted)" if ok else "FAIL"
    parts = "; ".join(f"({k}) {v}" for k, v in sorted(f.summary.items()))
    print(f"frozen inputs vs {a.rev}: {verdict}: {len(f.new)} new, {len(f.preexisting)} pre-existing difference(s); {parts}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
