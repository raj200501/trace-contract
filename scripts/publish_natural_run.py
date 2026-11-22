"""Publish a natural run's shareable outputs: ``data/natural/runs/<run>`` to ``results/runs/<run>`` (protocol §17.4,
decision log D47; build plan WP-H and section 9).

Usage: python -I scripts/publish_natural_run.py data/natural/runs/<run> --out results/runs/<run> --aidev-logins <AIDev dir>
           --screening-texts <S9 texts.jsonl> --screening-texts <S9x texts.jsonl> [--tasks-root data/natural/tasks]
           [--private-markers <file.json>]

A natural run (``tracecontract evaluate ... --out-root data/natural/runs``) keeps its results, logs and report in the
git-ignored ``data/natural/runs``: its ``results.jsonl`` holds B1's check ids (upstream test names), check messages and
diagnostics, which carry upstream code. This script writes exactly four files into ``results/runs/<run>/``:

* ``manifest.json``, ``analysis.json`` and ``analysis.md``, copied byte for byte;
* ``results_public.jsonl``: one line per line of the private ``results.jsonl`` (one graded pair), holding only
  :data:`PUBLIC_FIELDS`: the ids, the outcome, the reward, the harness version, the sha256 of the pair's log, the number
  of checks by status (:data:`CHECK_STATUSES`) and the sha256 of the private line (its UTF-8 bytes, without the line
  break). No check id, message or diagnostic.

Before anything is written, each of the four texts is checked as the pre-push scan (``scripts/scan_tracked_files.py
--aidev-logins --natural-texts --screening-texts``) will read it at its new place: windows of the natural thread texts
and of the screening texts (every sampled comment of S9 and S9x, built or not), and those texts too short for a window,
matched whole down to the scan's minimum (3 words with a letter and 12 characters, or 8 characters of a script written
without spaces); the AIDev logins of the S9 sample (the scan's login list, D66); @handles; the natural repositories'
names and owners (also in URLs); the natural tasks' code lines (patches, verifiers' files and base snapshots, less the
scan's idioms: every base line, where the scan looks only for those that name something of their own) and check ids;
credentials, session-local paths, e-mail addresses and the private markers. A finding is reported by its location and
kind only, and then nothing is written (exit status 1).

Refused before anything is written (exit status 2): a ``RUN_DIR`` that is not ``data/natural/runs/<run>``; an ``--out``
that is not ``results/runs/<run>`` for the same ``<run>``; a run name that does not start with ``natural-`` (the
``.gitignore`` rules that keep a natural run's ``results.jsonl`` and ``report.html`` out of git match
``results/runs/natural-*/``); a run without ``manifest.json``, ``results.jsonl``, ``analysis.json`` or ``analysis.md``, or
whose manifest records no ``finished_at``; an ``--out`` directory that holds any file other than the four. The checks
fail closed, so also refused: an empty login list (the AIDev files gave no login for the sampled PRs); no screening texts,
or texts that lack a sampled comment; a natural task's file that cannot be read, and a base snapshot that a task
records but that is missing or holds no code line; a manifest that lists no task; and a task that is not a task
directory directly under ``--tasks-root`` (a ``task_dir`` that does not exist or lies elsewhere), whose code and check
ids could not be read, or whose base snapshot (``roots.snapshot_root``) is not the one read with the natural tasks or
gave no code line (:func:`run_snapshots`). A relative ``--tasks-root`` is read from the repository's root, as the scan
reads it.

The AIDev files are third-party data, so run the script with ``python -I``, as the scan.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tracecontract import roots
from tracecontract.schemas import VerificationResult

REPO = Path(__file__).resolve().parents[1]
COPIED = ("manifest.json", "analysis.json", "analysis.md")
PRIVATE_RESULTS = "results.jsonl"
PUBLIC = "results_public.jsonl"
PUBLISHED = (*COPIED, PUBLIC)
CHECK_STATUSES = ("passed", "failed", "error", "skipped", "missing")  # schemas.CheckResult.status
PUBLIC_FIELDS = ("run_id", "task_id", "verifier_id", "candidate_id", "outcome", "reward", "harness_version", "log_sha256",
                 "check_counts", "private_line_sha256")
RUN_PREFIX = "natural-"


class Refused(Exception):
    """The run, or the place it would be published to, is refused; nothing has been written."""


def scan_module() -> Any:
    """``scripts/scan_tracked_files.py`` as a module: the pre-push scan whose matchers the checks use."""
    spec = importlib.util.spec_from_file_location("scan_tracked_files", Path(__file__).with_name("scan_tracked_files.py"))
    if spec is None or spec.loader is None:
        raise SystemExit("publish_natural_run: cannot load scripts/scan_tracked_files.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def locations(run_dir: str | Path, out: str | Path, *, repo: Path = REPO) -> tuple[Path, Path]:
    """The run directory and the publication directory, resolved; :class:`Refused` unless the run is
    ``data/natural/runs/<run>``, the publication ``results/runs/<run>`` and ``<run>`` starts with ``natural-``."""
    repo = Path(repo).resolve()
    run, dest = Path(run_dir).resolve(), Path(out).resolve()
    if run.parent != (repo / "data" / "natural" / "runs").resolve() or not run.name:
        raise Refused(f"{run_dir}: a natural run is published only from data/natural/runs/<run>, the git-ignored root of "
                      "the natural runs (§17.4)")
    if dest.parent != (repo / "results" / "runs").resolve() or dest.name != run.name:
        raise Refused(f"{out}: a natural run is published only to results/runs/<run>, here results/runs/{run.name}")
    if not run.name.startswith(RUN_PREFIX):
        raise Refused(f"{run.name}: a natural run's name starts with {RUN_PREFIX!r}, so that the .gitignore rules for "
                      "results/runs/natural-*/ keep its results.jsonl and report.html out of git")
    return run, dest


def public_record(line: str) -> dict[str, Any]:
    """The public line of one private result line (:data:`PUBLIC_FIELDS`)."""
    try:
        r = VerificationResult.model_validate_json(line)
    except ValidationError as exc:
        raise Refused(f"{PRIVATE_RESULTS}: a line is not a verification result ({exc.error_count()} error(s))") from None
    counts = dict.fromkeys(CHECK_STATUSES, 0)
    for c in r.checks:
        counts[c.status] += 1
    rec = {"run_id": r.run_id, "task_id": r.task_id, "verifier_id": r.verifier_id, "candidate_id": r.candidate_id,
           "outcome": r.outcome.value, "reward": r.reward, "harness_version": r.harness_version,
           "log_sha256": r.log_sha256, "check_counts": counts,
           "private_line_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest()}
    assert tuple(rec) == PUBLIC_FIELDS
    return rec


def public_lines(results: str) -> str:
    """``results_public.jsonl`` for the text of a private ``results.jsonl``, line by line (blank lines skipped)."""
    return "".join(json.dumps(public_record(ln), ensure_ascii=False) + "\n" for ln in results.split("\n") if ln.strip())


def _rel(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def run_snapshots(manifest: dict[str, Any], *, repo: Path, tasks_root: Path, natural: Any) -> list[str]:
    """The run's task ids, once its tasks' material is known to have been read. The checks fail closed, so
    :class:`Refused` (nothing read is trusted, nothing written) unless the manifest lists tasks and each of them is a
    task directory directly under ``tasks_root`` whose code lines or check ids ``natural`` (the scan's
    :func:`natural_material` of ``tasks_root``) holds, and whose base snapshot (``roots.snapshot_root``) is the one
    ``natural`` read code lines from: a task whose material cannot be read would be checked against nothing."""
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise Refused("manifest.json lists no task, so the run's outputs cannot be checked against its tasks' material")
    root = tasks_root.resolve()
    loaded = set(natural.task_ids)
    ids: list[str] = []
    for t in tasks:
        tid = str(t.get("task_id") or "") if isinstance(t, dict) else ""
        recorded = t.get("task_dir") if isinstance(t, dict) else None
        td = (repo / recorded) if recorded else tasks_root / tid
        where = recorded or "no task_dir recorded"
        if not tid or td.resolve() != root / tid or not td.is_dir():
            raise Refused(f"{tid or 'a task'} ({where}): not a task directory under {_rel(tasks_root, repo)}, the natural "
                          "tasks whose material the outputs are checked against; give the run's --tasks-root")
        if tid not in loaded:
            raise Refused(f"{tid}: {_rel(td, repo)} was not read with the natural tasks")
        if tid not in natural.code.labels and tid not in natural.check_ids.labels:
            raise Refused(f"{tid}: no code line or check id of the task could be read (candidates, verifiers)")
        try:
            base = roots.snapshot_root(td, repo=repo) / tid
        except roots.RootError as exc:
            raise Refused(f"{tid}: its base snapshot cannot be located ({exc})") from None
        if not base.is_dir():
            raise Refused(f"{tid}: no base snapshot at {_rel(base, repo)}")
        read = natural.base_snapshot(tid)
        if read is None or read[0].resolve() != base.resolve():
            raise Refused(f"{tid}: its base snapshot at {_rel(base, repo)} is not the one read with the natural tasks "
                          f"({_rel(read[0], repo) if read else 'none'})")
        if not read[1]:
            raise Refused(f"{tid}: no code line could be read from its base snapshot at {_rel(base, repo)}")
        ids.append(tid)
    return ids


def check_texts(texts: dict[str, str], rel_dest: str, *, scan: Any, natural: Any, logins: list[tuple[str, re.Pattern]],
                private: list[re.Pattern]) -> int:
    """Report and count the findings in the texts to be published (see the module docstring)."""
    return sum(scan.scan_file(f"{rel_dest}/{name}", text.encode("utf-8"), private, logins, natural, aidev=True)
               for name, text in texts.items())


def publish(run_dir: str | Path, out: str | Path, *, logins: list[tuple[str, re.Pattern]],
            screening: list[str | Path] | tuple[str | Path, ...], private: list[re.Pattern] | None = None,
            tasks_root: str | Path | None = None, repo: Path = REPO, scan: Any = None) -> int:
    """Publish the run (see the module docstring); the number of findings, 0 when the four files were written.
    ``screening``: the screening texts of every sampled comment, as for the scan's ``--screening-texts`` (relative to
    ``repo`` or absolute); ``tasks_root``: the natural tasks, relative to ``repo`` or absolute (default
    ``data/natural/tasks``)."""
    run, dest = locations(run_dir, out, repo=repo)
    if not logins:
        raise Refused("no AIDev login to check against (the AIDev files gave none for the sampled PRs), so the login "
                      "check would be off")
    if not screening:
        raise Refused("no screening texts, so the sampled comments that no natural task holds would not be checked; give "
                      "the S9 and S9x texts (--screening-texts)")
    missing = [f for f in (*COPIED, PRIVATE_RESULTS) if not (run / f).is_file()]
    if missing:
        raise Refused(f"{run}: no {', '.join(missing)} (run the analysis before publishing)")
    data = {f: (run / f).read_bytes() for f in COPIED}
    try:
        texts = {f: b.decode("utf-8") for f, b in data.items()}
        texts[PUBLIC] = public_lines((run / PRIVATE_RESULTS).read_text(encoding="utf-8"))
        manifest = json.loads(texts["manifest.json"])
    except (UnicodeDecodeError, ValueError) as exc:
        raise Refused(f"{run}: unreadable run record ({exc.__class__.__name__})") from None
    if not isinstance(manifest, dict) or not manifest.get("finished_at"):
        raise Refused(f"{run}: manifest.json records no finished_at; publish a finished run")
    if dest.exists():
        other = sorted(p.name for p in dest.iterdir() if p.name not in PUBLISHED) if dest.is_dir() else [dest.name]
        if other:
            raise Refused(f"{dest}: holds {', '.join(other)} besides the published files; only the four files are published")
    scan = scan if scan is not None else scan_module()
    repo = Path(repo).resolve()
    troot = Path(tasks_root) if tasks_root is not None else Path("data") / "natural" / "tasks"
    troot = troot if troot.is_absolute() else repo / troot  # as the scan resolves it: against the repository
    try:
        natural = scan.natural_material(troot, [p if Path(p).is_absolute() else repo / p for p in screening],
                                        distinctive_base=False)  # every base line, not only those the scan looks for
    except (FileNotFoundError, ValueError) as exc:  # the message names --natural-texts or --screening-texts
        raise Refused(str(exc)) from None
    run_tasks = run_snapshots(manifest, repo=repo, tasks_root=troot, natural=natural)
    rel_dest = f"results/runs/{dest.name}"
    hits = check_texts(texts, rel_dest, scan=scan, natural=natural, logins=logins, private=list(private or []))
    if hits:
        print(f"publish_natural_run: {hits} finding(s) in the files to be published to {rel_dest}; nothing written")
        return hits
    dest.mkdir(exist_ok=True)
    for f, b in data.items():
        (dest / f).write_bytes(b)
    (dest / PUBLIC).write_text(texts[PUBLIC], encoding="utf-8")
    print(f"published {run.name} to {rel_dest}: {', '.join(COPIED)} copied, {texts[PUBLIC].count(chr(10))} line(s) in "
          f"{PUBLIC}; checked against the {scan.natural_summary(natural)} (the base snapshots of the run's "
          f"{len(run_tasks)} task(s) among them) and {len(logins)} AIDev login(s) and name(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir", help="data/natural/runs/<run>")
    ap.add_argument("--out", required=True, help="results/runs/<run>")
    ap.add_argument("--aidev-logins", required=True, metavar="DIR", help="the AIDev files, as for the scan")
    ap.add_argument("--tasks-root", default=None,
                    help="the natural tasks, relative to the repository or absolute (default data/natural/tasks)")
    ap.add_argument("--screening-texts", action="append", required=True, metavar="FILE",
                    help="the screening texts of every sampled comment (S9 and S9x), as for the scan (repeatable)")
    ap.add_argument("--private-markers", default=None, metavar="FILE", help="as for the scan")
    a = ap.parse_args(argv)
    try:
        locations(a.run_dir, a.out)  # refused before the AIDev files are read
        scan = scan_module()
        logins = scan.login_patterns(scan.aidev_logins(a.aidev_logins))
        private = scan.load_private(a.private_markers) if a.private_markers else []
        n = publish(a.run_dir, a.out, logins=logins, private=private, tasks_root=a.tasks_root, scan=scan,
                    screening=a.screening_texts)
    except Refused as exc:
        print(f"publish_natural_run: refused: {exc}", file=sys.stderr)
        return 2
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
