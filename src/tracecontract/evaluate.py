"""Evaluation matrix: every applicable verifier x every evaluation candidate.

Each run writes to ``<out root>/<run_id>/`` (``results/runs`` by default; a run with a natural
PR-review task goes to a git-ignored root such as ``data/natural/runs``):

* ``manifest.json`` - run id, timestamps, code revision, image ids, verifier
  content hashes, candidate patch hashes, configuration, each task's directory;
* ``results.jsonl`` - one :class:`VerificationResult` per (verifier, candidate).

Runs are append-only. Re-running with the same run id resumes (completed pairs are
skipped); a changed frozen verifier aborts the run (bump the version instead).

Every task goes through the task acceptance gate (:func:`gate_tasks`) before anything
is written: a rejected task is always refused, and a task that has not been accepted
through the gate is evaluated only with ``pilot=True`` (``--pilot``), which the
manifest records together with each task's gate result.

Candidate strata (:mod:`tracecontract.strata`): ``strata=[...]`` (``--strata``) also grades
the candidates listed in ``tasks/<id>/strata/<name>.json``, and with ``only_strata``
(``--only-strata``) grades them instead of the task's own candidates; the reference solution
is graded as the sanity check either way. Strata never change ``task.json`` or the task's
candidate files. The manifest records each task's strata (file and sha256) and, for every
stratum candidate, its stratum and file (``tasks[].candidates[<id>].stratum`` and ``.path``).

Every refusal comes before anything is written, so a refused run leaves no directory
(:class:`RunRefused`): the acceptance gate, the strata, the run directory of a natural
PR-review task (only a git-ignored directory of the repository, such as ``data/natural/runs``,
and never a path that another git work tree does not ignore: :func:`private_location_problem`),
each task's base snapshot (one snapshot root per task, ``roots.snapshot_root``), its frozen
verifiers and its image, whose id must equal the ``environment.image_id`` that ``snapshot.json``
records (required for a natural PR-review task, whose image is only looked up and never rebuilt:
:func:`find_image`). Each manifest entry records the task directory relative to the repository
(``tasks[].task_dir``).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import task_gate
from .sandbox.docker_runner import Limits, build_env_image, verify_candidate
from .schemas import (
    Candidate, CandidateOrigin, Population, Snapshot, Split, TaskManifest, VerificationResult, VerifierSpec,
)
from .store import append_jsonl, load, read_jsonl, write_json
from .strata import Stratum, StratumError, load_strata
from .verifier import check_frozen

STUDY_HOME = Path("/home/user")  # the build environment's home, where the study's material lives
EXTERNAL_DATA = STUDY_HOME / "ext"  # third-party data (decision log D47)


def code_revision(repo_root: Path) -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root, capture_output=True, text=True).stdout.strip()
        return rev + ("+dirty" if dirty else "")
    except subprocess.CalledProcessError:
        return "unknown"


EXTRA_VERIFIERS = "verifiers_extra.json"


def extra_verifier_paths(task_dir: Path) -> list[str]:
    """Verifier specs registered in the task's sidecar ``verifiers_extra.json``, not in ``task.json``.

    Label-support verifiers added after a task's files were frozen (for example the
    independent labeler, protocol §15.5) are registered here, so the frozen ``task.json``
    is never changed. Evaluations include them only when asked to.
    """
    p = task_dir / EXTRA_VERIFIERS
    if not p.is_file():
        return []
    import json as _json
    data = _json.loads(p.read_text(encoding="utf-8"))
    return [str(x) for x in data.get("verifiers", [])]


def load_task(task_dir: Path, *, extra: bool = False) -> tuple[TaskManifest, list[VerifierSpec], list[Candidate]]:
    m = load(task_dir / "task.json", TaskManifest)
    paths = list(m.verifiers) + ([x for x in extra_verifier_paths(task_dir) if x not in m.verifiers] if extra else [])
    specs = [load(task_dir / p, VerifierSpec) for p in paths]
    cands = [load(task_dir / p, Candidate) for p in m.candidates]
    return m, specs, cands


class TaskRefused(ValueError):
    """The acceptance gate keeps a task out of the run (:func:`gate_tasks`)."""


class RunRefused(ValueError):
    """A check before the run keeps it from starting: a base snapshot, a frozen verifier, an image or the run directory
    (:func:`run_matrix`). Nothing has been written."""


def _git_env() -> dict[str, str]:
    """The environment for a git command that must answer for the directory it is run in: no ``GIT_DIR``,
    ``GIT_WORK_TREE`` or other ``GIT_*`` variable of the caller (a hook, for example) redirects it."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git_ignored(path: Path, repo_root: Path) -> bool:
    """True if the git work tree at ``repo_root`` ignores ``path`` (``git check-ignore``; a tracked path is not ignored).

    False for a path outside ``repo_root``, and whenever git cannot answer (no repository, no git)."""
    try:
        rel = Path(path).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return False
    try:
        p = subprocess.run(["git", "-C", str(repo_root), "check-ignore", "-q", "--", rel or "."], capture_output=True,
                           env=_git_env(), timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0


def git_work_trees(path: Path) -> list[Path]:
    """The git work trees that hold ``path`` (resolved), innermost first: the path itself and every ancestor of it that
    has a ``.git`` entry, a directory or the ``.git`` file of a linked work tree (``git worktree add``) or a submodule.

    A linked work tree or another clone of a repository shares that repository's history: what is committed there can
    be pushed with it."""
    real = Path(path).resolve()
    return [d for d in (real, *real.parents) if os.path.lexists(d / ".git")]


def private_location_problem(path: Path, repo_root: Path, *, inside_repo: bool = False) -> str | None:
    """Why ``path`` is no place for a natural task's run records or material, or an agent's workspace; ``None`` if it is one.

    Refused:

    * a path in a Claude session's directories (``/tmp/claude-*``, ``~/.claude``) or under ``/home/user/ext``, the
      third-party data (D47);
    * with ``inside_repo`` (the run directory of a natural PR-review task, §17.4), any path outside the repository
      ``repo_root``: such a run is written only under a git-ignored directory of the repository, ``data/natural/runs``;
    * a path in a git work tree that does not ignore it, since it could be committed there: the repository itself
      (``data/natural/`` is ignored, §17.4), and every work tree that holds the path (:func:`git_work_trees`), such as a
      linked work tree or another clone of the repository, or a repository nested in an ignored directory. A path in the
      repository whose ignore status git cannot tell (no git, or not a repository) is refused too.

    Any other path, outside every git work tree, is accepted.
    """
    given = Path(path).absolute()
    real = given.resolve()
    for p in (given, real):
        if len(p.parts) >= 3 and p.parts[1] == "tmp" and p.parts[2].startswith("claude-"):
            return f"{path} lies in a Claude session's directory (/tmp/claude-*)"
    sessions = dict.fromkeys((STUDY_HOME / ".claude", Path.home() / ".claude"))
    for name, d in (("the third-party data (D47)", EXTERNAL_DATA), *(("a Claude session's directory", s) for s in sessions)):
        d = d.resolve()
        if real == d or d in real.parents:
            return f"{path} lies under {d}, {name}"
    repo = Path(repo_root).resolve()
    inside = real == repo or repo in real.parents
    if inside_repo and not inside:
        return (f"{path} lies outside the repository {repo}; a natural PR-review task's run records are written only under a "
                "git-ignored directory of the repository (data/natural/runs, §17.4)")
    trees = git_work_trees(real)
    if inside and repo not in trees:
        trees.append(repo)  # the repository's own rule, also when no .git entry marks it (git then cannot answer)
    for tree in trees:
        if git_ignored(real, tree):
            continue
        if tree == repo:
            return f"{path} lies inside the repository and git does not ignore it, so it could be committed"
        return (f"{path} lies inside the git work tree {tree} and git does not ignore it there, so it could be committed "
                "(a linked work tree or a clone shares its repository's history)")
    return None


def env_image_tag(reqs: list[str]) -> str:
    """The tag that ``docker_runner.build_env_image`` gives the image of the pinned requirements ``reqs``."""
    from .sandbox.docker_runner import _req_hash

    return f"tc-env:{_req_hash(sorted(set(reqs)))}"


def local_image_id(tag: str) -> str | None:
    """The id of the image ``tag`` on this host (``docker image inspect``); ``None`` if there is none or Docker cannot
    say. It never builds or pulls an image."""
    try:
        p = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", tag], capture_output=True, text=True,
                           timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = p.stdout.strip()
    return found if p.returncode == 0 and found else None


def _recorded_image(m: TaskManifest, snap: Snapshot, tag: str) -> tuple[str | None, str | None]:
    """``(recorded image id, problem)`` from ``snapshot.json`` alone, before any image is looked up (:func:`image_problem`)."""
    env = snap.environment if isinstance(snap.environment, dict) else {}
    recorded = env.get("image_id") or None
    if m.population != Population.natural_pr_review:
        return recorded, None
    if not recorded:
        return None, (f"{m.task_id}: snapshot.json records no environment.image_id; a natural PR-review task is graded only "
                      "in the image its S10 step built and recorded")
    if env.get("image") != tag:
        return recorded, (f"{m.task_id}: its pinned requirements give the image tag {tag}, but snapshot.json records "
                          f"{env.get('image')!r}; the task's environment is not the one its S10 step recorded")
    return recorded, None


def image_problem(m: TaskManifest, snap: Snapshot, tag: str, image_id: str | None) -> str | None:
    """Why the task may not be graded in the image ``tag``, whose id on this host is ``image_id`` (``None``: there is no
    such image); ``None`` if it may.

    The id must equal the ``environment.image_id`` that ``snapshot.json`` records. A natural PR-review task must record
    one, with the tag (``environment.image``) that its pins give: its image was built and recorded by the S10 step, it
    is never rebuilt (:func:`find_image`), and two of them cannot be rebuilt from wheels (D59), so a rebuilt image would
    be another environment."""
    recorded, problem = _recorded_image(m, snap, tag)
    if problem or recorded is None:
        return problem
    if image_id is None:
        never = ("; a natural PR-review task's image is never rebuilt (its S10 step built and recorded it)"
                 if m.population == Population.natural_pr_review else "")
        return f"{m.task_id}: the image {tag} (id {recorded}) is not on this host{never}"
    if image_id != recorded:
        return (f"{m.task_id}: the image {tag} has the id {image_id}, but snapshot.json records {recorded}; a rebuilt "
                "image is another environment")
    return None


def find_image(m: TaskManifest, snap: Snapshot, cache_dir: Path) -> tuple[str, str]:
    """The image that the task is graded in, ``(tag, id)``; :class:`RunRefused` if it may not be (:func:`image_problem`).

    A natural PR-review task's image is only looked up (:func:`local_image_id`), never built: its recorded id and tag
    are checked first, and a missing image refuses the task. ``docker_runner.build_env_image`` would rebuild a missing
    image and give the rebuilt one the recorded tag, so that every later grade of the task would run in it. Any other
    task's image is built when it is missing (``build_env_image``), as before, and its id compared with the recorded one.
    """
    if m.population == Population.natural_pr_review:
        tag = env_image_tag(m.env_requirements)
        _, problem = _recorded_image(m, snap, tag)
        if problem:  # refused on the records alone, before Docker is asked
            raise RunRefused(problem)
        image_id = local_image_id(tag)
    else:
        tag, image_id = build_env_image(m.env_requirements, cache_dir)
    problem = image_problem(m, snap, tag, image_id)
    if problem or image_id is None:
        raise RunRefused(problem or f"{m.task_id}: no image {tag}")
    return tag, image_id


def _repo_relative(path: Path, root: Path) -> str | None:
    """``path`` relative to the repository root, in posix form; ``None`` for a path outside it."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _root_for(snapshot_root: Path | Mapping[str, Path], task_id: str) -> Path:
    if isinstance(snapshot_root, Mapping):
        if task_id not in snapshot_root:
            raise RunRefused(f"no snapshot root given for {task_id}")
        return Path(snapshot_root[task_id])
    return Path(snapshot_root)


def gate_tasks(task_dirs: list[Path], *, repo_root: Path, pilot: bool) -> dict[str, dict]:
    """Run the task acceptance gate on every task and return each result; raise :class:`TaskRefused` if any is refused.

    A task whose status or provenance is ``rejected`` is always refused. A task that is not
    accepted (status ``accepted`` and the gate still passing) is refused unless ``pilot``
    is set, so evaluating unaccepted tasks, as the automated pilot does, has to be asked for.
    """
    gates: dict[str, dict] = {}
    refused: list[str] = []
    for td in task_dirs:
        g = task_gate(td, repo_root)
        gates[g.task_id] = g.to_dict()
        if g.refusals:
            refused.append(f"{g.task_id}: refused ({'; '.join(g.refusals)})")
        elif not g.accepted and not pilot:
            first = g.reasons[0] if g.reasons else "the gate passes but the task was not accepted (tracecontract accept-task)"
            refused.append(f"{g.task_id}: not accepted (status {g.status!r}; {len(g.reasons)} gate reason(s), first: "
                           f"{first}); pass --pilot to evaluate it as an automated pilot")
    if refused:
        raise TaskRefused("\n".join(refused))
    return gates


def select_strata(task_dirs: list[Path], names: list[str], *, only_strata: bool = False,
                  prior: dict | None = None) -> dict[str, dict[str, Stratum]]:
    """The strata ``names`` of every task, by task id; raise :class:`StratumError` if one is missing or invalid.

    Every task must have every stratum (:func:`strata.load_strata`). In a resumed run (``prior`` is
    its manifest), a stratum candidate the run already recorded must keep its stratum and its patch,
    because its graded pairs are not graded again.
    """
    if only_strata and not names:
        raise StratumError("only_strata (--only-strata) needs at least one stratum (--strata NAME)")
    recorded = {t["task_id"]: t.get("candidates", {}) for t in (prior or {}).get("tasks", [])}
    out: dict[str, dict[str, Stratum]] = {}
    for td in task_dirs:
        m = load(td / "task.json", TaskManifest)
        if not names:
            out[m.task_id] = {}
            continue
        own = {load(td / p, Candidate).candidate_id for p in m.candidates}
        out[m.task_id] = load_strata(td, names, m.task_id, own)
        for st in out[m.task_id].values():
            for _, c in st.candidates:
                was = recorded.get(m.task_id, {}).get(c.candidate_id)
                if was is not None and (was.get("stratum"), was.get("patch_sha256")) != (st.name, c.patch_sha256):
                    raise StratumError(f"{m.task_id}: candidate {c.candidate_id} of stratum {st.name!r} is not the one this "
                                       "run recorded (another stratum or patch); use a new run id")
    return out


def check_inputs(task_dirs: list[Path], *, snapshot_root: Path | Mapping[str, Path], cache_dir: Path,
                 conditions: list[str] | None = None, require_frozen: bool = True,
                 extra_verifiers: bool = False) -> dict[str, tuple[str, str]]:
    """Check every task's inputs before anything is written; ``{task id: (image tag, image id)}``, or :class:`RunRefused`.

    Each task's base snapshot (under its own snapshot root) exists and matches its recorded manifest; each verifier of
    the selected conditions is frozen (unless ``require_frozen`` is off) and unchanged since; and the task's image is
    found, or for a task other than a natural PR-review one built, with the id that ``snapshot.json`` records
    (:func:`find_image`).
    """
    from .tasks import verify_snapshot

    loaded = []
    for td in task_dirs:  # the files first, then the images, so that a missing file never waits for an image build
        m, specs, _ = load_task(td, extra=extra_verifiers)
        root = _root_for(snapshot_root, m.task_id)
        base = root / m.task_id
        if not base.is_dir():
            raise RunRefused(f"snapshot for {m.task_id} not built at {base} (run `tracecontract snapshot`, or for a natural "
                             "PR-review task `tracecontract compile-pr-task`)")
        if not verify_snapshot(td, root):
            raise RunRefused(f"snapshot for {m.task_id} at {base} does not match its recorded manifest")
        for s in specs:
            if conditions and s.condition.value not in conditions:
                continue
            if require_frozen and not s.frozen:
                raise RunRefused(f"{s.verifier_id} is not frozen; freeze verifiers before final evaluation")
            try:
                check_frozen(s, td)
            except ValueError as exc:
                raise RunRefused(str(exc)) from None
        loaded.append((m, load(td / (m.snapshot or "snapshot.json"), Snapshot)))
    images: dict[str, tuple[str, str]] = {}
    for m, snap in loaded:
        images[m.task_id] = find_image(m, snap, cache_dir)
    return images


def run_matrix(task_dirs: list[Path], *, run_id: str, out_root: Path, cache_dir: Path,
               snapshot_root: Path | Mapping[str, Path], split: Split = Split.eval, conditions: list[str] | None = None,
               repeats: int = 1, limits: Limits | None = None, require_frozen: bool = True, repo_root: Path | None = None,
               include_reference: bool = True, pilot: bool = False, strata: list[str] | None = None,
               only_strata: bool = False, extra_verifiers: bool = False) -> Path:
    """Grade every selected verifier on every evaluation candidate into ``out_root/run_id`` (see the module docstring).

    ``snapshot_root`` is one directory for every task, or one per task id. Every refusal (:class:`TaskRefused`,
    :class:`~tracecontract.strata.StratumError`, :class:`RunRefused`) comes before anything is written.
    """
    root = repo_root or Path.cwd()
    gates = gate_tasks(task_dirs, repo_root=root, pilot=pilot)  # before anything is written
    out = out_root / run_id
    import json as _json

    prior = _json.loads((out / "manifest.json").read_text()) if (out / "manifest.json").exists() else None
    names = list(dict.fromkeys(strata or []))
    selected = select_strata(task_dirs, names, only_strata=only_strata, prior=prior)  # before anything is written
    natural = [td.name for td in task_dirs
               if load(td / "task.json", TaskManifest).population == Population.natural_pr_review]
    if natural:  # their results hold upstream code and check messages: never where git could commit them (§17.4)
        problem = private_location_problem(out, root, inside_repo=True)
        if problem:
            raise RunRefused(f"natural PR-review task(s) {', '.join(natural)}: the run directory {out} is refused: {problem}; "
                             "write the run under a git-ignored root such as data/natural/runs (--out-root)")
    # Every task's snapshot, frozen verifiers and image, before anything is written, so that a run cannot
    # stop part-way on a missing or modified input.
    images = check_inputs(task_dirs, snapshot_root=snapshot_root, cache_dir=cache_dir, conditions=conditions,
                          require_frozen=require_frozen, extra_verifiers=extra_verifiers)
    out.mkdir(parents=True, exist_ok=True)
    res_path = out / "results.jsonl"
    # Keyed by task as well: a stratum candidate's id is unique only within its task.
    done = {(r.task_id, r.verifier_id, r.candidate_id) for r in read_jsonl(res_path, VerificationResult)}
    invocation = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tasks": [d.name for d in task_dirs],
                  "code_revision": code_revision(root), "pilot": pilot}
    if names:
        invocation.update(strata=names, only_strata=only_strata)
    invocations = (prior or {}).get("invocations", []) + [invocation]
    prior_entries = {t["task_id"]: t for t in (prior or {}).get("tasks", [])}
    manifest = {
        "run_id": run_id,
        "started_at": prior["started_at"] if prior else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_revision": code_revision(root),
        "split": split.value,
        "repeats": repeats,
        "conditions": conditions,
        "limits": (limits or Limits()).__dict__,
        "tasks": [t for t in (prior or {}).get("tasks", []) if t["task_id"] not in {d.name for d in task_dirs}],
        "invocations": invocations,
        # Whether any invocation evaluated tasks without requiring the acceptance gate; one
        # recorded before the gate was enforced (no "pilot" key) counts as such.
        "pilot": any(inv.get("pilot", True) for inv in invocations),
    }
    if extra_verifiers:  # label-support verifiers from verifiers_extra.json were included
        manifest["extra_verifiers"] = True
    for td in task_dirs:
        m, specs, cands = load_task(td, extra=extra_verifiers)
        base = _root_for(snapshot_root, m.task_id) / m.task_id
        snap = load(td / (m.snapshot or "snapshot.json"), Snapshot)
        tag, image_id = images[m.task_id]
        entry: dict[str, Any] = {"task_id": m.task_id, "family_id": m.family_id, "task_dir": _repo_relative(td, root), "image": tag,
                 "image_id": image_id, "snapshot_manifest_sha256": snap.file_manifest_sha256,
                 "acceptance_gate": gates[m.task_id], "verifiers": {}, "candidates": {}}
        for s in specs:
            if conditions and s.condition.value not in conditions:
                continue
            if require_frozen and not s.frozen:
                raise ValueError(f"{s.verifier_id} is not frozen; freeze verifiers before final evaluation")
            check_frozen(s, td)
            entry["verifiers"][s.verifier_id] = {"condition": s.condition.value, "content_sha256": s.content_sha256,
                                                 "checks_sha256": s.checks_sha256, "n_checks": len(s.checks), "version": s.version}
        # Held-out candidates of the requested split, plus the reference solution as a
        # sanity check (protocol section 5: graded by every verifier, excluded from FA/FR);
        # with only_strata the task's own candidates are left out, except the reference.
        eval_cands = [c for c in cands if (c.split == split and not only_strata)
                      or (include_reference and c.origin == CandidateOrigin.reference)]
        for c in eval_cands:
            entry["candidates"][c.candidate_id] = {"origin": c.origin.value, "patch_sha256": c.patch_sha256}
        for st in selected[m.task_id].values():
            for rel, c in st.candidates:
                if c.split == split:
                    eval_cands.append(c)
                    entry["candidates"][c.candidate_id] = {"origin": c.origin.value, "patch_sha256": c.patch_sha256,
                                                           "stratum": st.name, "path": rel}
        # Stratum candidates that an earlier invocation of this run graded stay recorded, so the
        # analysis still finds their results.
        prev = prior_entries.get(m.task_id, {})
        for cid, rec in prev.get("candidates", {}).items():
            if "stratum" in rec:
                entry["candidates"].setdefault(cid, rec)
        strata_records = {**prev.get("strata", {}), **{n: st.record() for n, st in selected[m.task_id].items()}}
        if strata_records:
            entry["strata"] = strata_records
        manifest["tasks"].append(entry)
        write_json(manifest, out / "manifest.json")
        for s in specs:
            if s.verifier_id not in entry["verifiers"]:
                continue
            for c in eval_cands:
                if (s.task_id, s.verifier_id, c.candidate_id) in done:
                    continue
                res = verify_candidate(
                    image=tag, base_dir=base, spec=s, task_dir=td, candidate=c, run_id=run_id, repeats=repeats,
                    candidate_pythonpath=m.candidate_pythonpath, repo_test_args=m.repo_test_args, limits=limits,
                    log_dir=out / "logs",
                )
                append_jsonl(res, res_path)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_json(manifest, out / "manifest.json")
    return out
