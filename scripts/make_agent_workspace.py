"""Isolated workspace for one generator or fresh agent (protocol v0.7 §15.4-§15.6, v0.8 §16.2, v0.11 §19; decision log
D44, D46, D47, D50, D55).

Usage: python scripts/make_agent_workspace.py <task dir> --role <role> --root <dir> --name <name>
           [--instruction <file> | --variant u1|final] [--image <tag> [--pythonpath <path>] [--pytest-args <args>]
           [--no-smoke] [--run-python-only]] [--tests-from <dir>] [--dev-candidates <id> ...]
           [--candidates <id> ...] [--snapshots <dir>] [--sealed <dir> ...] [--forbid <dir> ...]
           [--allow-outside-paths] [--allow-existing-paths-in-copies]

It creates the new directory ``<root>/<name>``, outside the repository, holding only what
the role may see (``ROLES``, and for natural PR-review tasks ``NATURAL_ROLES``, below):

* ``repo/``: a copy (not a link) of the task's base snapshot, checked against the
  snapshot's recorded manifest first, made a fresh git repository with one base commit
  (fixed author, committer and date, so every workspace of a task has the same commit id).
  git runs with an allowlisted environment: no ``GIT_*`` variable of the caller (``GIT_DIR``,
  ``GIT_WORK_TREE``, ``GIT_INDEX_FILE`` ...) reaches it, only the fixed identity, date and
  configuration variables. ``--snapshots`` defaults to where the task's population keeps its base
  snapshots (``tracecontract.roots.snapshot_root``: ``<repo-root>/snapshots``, and for a natural
  PR-review task the root its provenance records, ``data/natural/snapshots``);
* ``instruction.md``: the ``--instruction`` file; for the fresh role, ``--variant`` instead builds
  the instruction of protocol §15.4 from the task's scripted turns: ``u1`` is U1, ``final`` is U1,
  the line ``Later in the session the user added:`` and U2. Each absolute path of the session's
  old workspace in U1 and U2 is replaced by the corresponding path of this workspace (§16.2,
  :func:`substitute_paths`): the old workspace itself, its repository checkout (and any path under
  it), ``run_tests.sh`` and ``run_python.sh``. Nothing else is changed, and every substitution is
  recorded. For a role that reads a contract, the instruction is rendered from that contract;
* for generator roles, only the inputs the role may read: the contract of its variant
  (``contract.json``: the active scored requirements with id, kind, statement, observable
  and the user turn that introduced them, as ``export-gen-workspace`` wrote it), the graded
  part of the reference diff (``reference.diff``, without the session agent's test files),
  and the rendered session (``session.txt``) or its first user request
  (``session_first_prompt.txt``);
* with ``--image``: ``run_tests.sh`` and ``run_python.sh``, the sandbox wrappers of the
  controlled sessions (``tracecontract.controlled.RUN_TESTS_SH`` and ``RUN_PYTHON_SH``), which run
  the working copy read-only and offline in that image (a role that runs no code has none, and a
  natural near miss has ``run_python.sh`` only, below; ``--run-python-only`` writes ``run_python.sh``
  alone for any role, for a role whose prompt runs no repository tests, and the manifest lists the
  scripts written). A ``--variant`` workspace needs both, as its instruction names them. Leaving
  ``run_tests.sh`` out offers no test runner, but it prevents nothing: ``run_python.sh`` runs any
  Python in the same image, ``run_python.sh -m pytest`` included, so whether an agent ran the
  repository's tests is shown by the audit of its transcript, not by its workspace.
  :func:`check_wrappers` checks that each is that template rendered
  for this workspace, executable, and that its one command runs the code only in the Docker
  sandbox. Unless ``--no-smoke`` is given, the command line also runs them
  (:func:`smoke_wrappers`): Python runs in the image, ``/repo`` is the workspace's ``repo/``,
  read-only, with no network, and pytest answers;
* ``scratch/``: a private scratch directory (mode 0700) for the agent's notes and scripts,
  in place of any shared scratch directory;
* ``manifest.json``: the sha256 of every other file, by its path in the workspace
  (``repo/.git`` is represented by the base commit id), with the role and its inputs, the
  instruction's sha256 and, for a variant, the variant and the recorded substitutions.

**Natural PR-review tasks** (population ``natural:pr-review``, protocol §15.6, built under the git-ignored
``data/natural/``). Every role reads the session as its rendered thread (``tasks.render_session``): the linked
issue, and in the full render the review comment's diff hunk, the comment and the reviewer's later replies, behind
a fixed banner. The PR body and the commit messages are never shown (:func:`agent_only_events`): a workspace is
refused if one of its texts (the instruction, every role input, the copied tests and harness docs, the manifest) names
one of those events by its id, or if a text that is not code (the instruction, the session texts and records, the
contracts, the manifest; not the diffs, patches, tests and harness docs) holds the whole text of one of them, or one
of its lines, of at least :data:`MIN_LEAK` characters with the whitespace collapsed, unless an event the thread shows
holds that text too (:func:`agent_only_leaks`). Nor may any
file name, text or the manifest of a workspace name a held-out candidate (split ``eval``) of the task
(:func:`heldout_problems`; the checker reads its candidates under neutral labels, below). The roles above keep their
inputs, except that on a natural task

* ``near-miss`` has ``run_python.sh`` only, no ``run_tests.sh``: the workspace offers no test runner, as the
  natural near-miss prompt has no repository-test step (internal review ``integrity:M2``: the controlled
  near-miss generators ran B1's tests on their states before registration). This is not enforced:
  ``run_python.sh -m pytest`` runs the repository's tests on the agent's state in the same image, so that a
  near-miss generator did not run them is for the audit of its transcript to show, not for this workspace;
* ``labeler`` also gets the harness docs under ``harness/`` (:func:`harness_docs`): an excerpt of the grading
  harness module ``tc_sandbox`` with its docstring and public API, the lint rules of verifier tests (an excerpt of
  ``tracecontract.verifier``) and the FX-01 example tests, all copied verbatim, as the controlled labeler writers
  read them (D55). For its single revision (§15.5, §19.8) it may get a copy of its own tests (``--tests-from``,
  the task's ``verifiers/independent_label/tests``);
* ``freeform`` and ``diff-derived`` need no instruction: their prompt is the instruction, their session text the
  task statement.

The natural-arm roles (``NATURAL_ROLES``) are for natural PR-review tasks only:

* ``contract-initial``, ``contract-full``: the proposers of the ``initial_only`` and ``full_session`` contracts.
  ``session_first_prompt.txt`` or ``session.txt``, and ``session_events.json`` (``tasks.render_session_events``:
  the events that text shows, which ``tracecontract check-proposals`` reads back). No ``repo/``, no wrappers, no
  instruction;
* ``refcontract``: the drafter of the reference contract. ``session.txt``, ``reference.diff``, ``addressing.diff``
  and ``session_events.json`` of the ``reference`` variant. ``addressing.diff`` is the graded part of the change
  from the pre-review state to the reference, ``patches.filter_patch(patches.diff_dirs(base + pre-review,
  base + reference))`` (:func:`addressing_diff`); the manifest records the two states by origin and patch sha256.
  No ``repo/``, no wrappers;
* ``reviser-initial``, ``reviser-full``: a reviser of an audited verifier (C2, C4). The variant's contract,
  ``reference.diff``, the verifier's tests (``--tests-from``: the task's ``verifiers/initial_audited/tests`` or
  ``verifiers/full_audited/tests``, copied to ``tests/``) and the graded part of each development candidate that
  ``--dev-candidates`` names (``devcands/<id>.patch``). A held-out candidate is refused, and so is a development
  candidate outside the audit set ``v1:<variant>`` of the reviser's variant, which ``tracecontract audit
  --audit-set`` grades (:func:`in_audit_set`: the no-op, the reference, and the candidates whose ``produced_by``
  holds ``v1:<variant>``);
* ``refcheck-review``: the reviewer and the fixer of the reference checks. The reference contract,
  ``reference.diff`` and the checks (``--tests-from``: the task's ``verifiers/reference_check/tests``);
* ``mapper``: the three contracts only, ``contracts/initial_only.json``, ``contracts/full_session.json`` and
  ``contracts/reference.json`` (every requirement with its id, kind, status, scored and subjective flags,
  statement, observable, supersession links, rationale, the user turn that introduced it and its quotes from user
  turns; :func:`mapper_contract`). No ``repo/``, no wrappers;
* ``checker``: the optional construction checker. The reference contract, ``reference.diff`` and the graded part
  of each held-out candidate that ``--candidates`` names, under a neutral label: ``candidates/candidate-<k>.patch``,
  numbered in the order of the candidates' patch sha256 (:func:`checker_labels`), so that no held-out id reaches the
  workspace. The manifest records each label's patch sha256, and the printed output maps the labels to the
  candidate ids (``candidate_labels``), for the host. A development candidate (the reference among them) and the
  no-op are refused.

The graded part of a patch is what the grader applies: ``patches.filter_patch`` removes the test files and the test
configuration, as for ``reference.diff``.

Before the workspace is kept, :func:`check_workspace` checks it, and a failed check removes
it again: the top level holds only the role's entries; there is no symlink, hard link or
special file; ``repo/`` equals the snapshot and its git history is the one base commit; no
file equals a file of forbidden material, other than a file of the base snapshot itself or a
copy that the role asked for (the tests of ``--tests-from`` and the candidate patches): the
repository's ``tasks/``, ``results/``, ``docs/``, ``data/`` and ``paper/``, the sealed directory
(``--sealed``, default ``/home/user/.tc_sealed``), the third-party data under ``/home/user/ext``,
the build session's old workspaces (``/home/user/cs_workspaces``, ``/home/user/gen_workspaces``),
and every other workspace beside the new one (except what this tool wrote there, as its manifest
records it, wherever in that workspace a copy of it lies: an agent's copy of a file it was given
is not its work). Beside the new workspace lie the directories in the root and, when the root's parent
could itself be a root (the location rules below accept it), the directories in that parent that are
workspaces or hold one (directly or one level further down), whatever else exists there: so a group root's
sibling groups and workspaces, and a task root's sibling task roots, are always scanned (:func:`forbidden_for`).
A plain directory beside the new workspace (one that is not a workspace, such as a group of workspaces) is
forbidden material too, except for the workspaces it holds, which count as workspaces. So nothing from
``tasks/*/verifiers`` (other than the tests a role asks for with ``--tests-from``), ``tasks/*/candidates``,
``tasks/*/labels``, ``results/``, ``docs/``, ``data/controlled``, ``data/natural``, sealed material or another
agent's work is present; the reference diff, and for the roles that ask for them the addressing diff and the
candidate patches, are the only texts derived from candidates. The root may be a plain directory that groups
workspaces (for example one workspace per attack state). The root (and so the workspace) may not lie inside
(or around) the repository, a sealed directory, the third-party data (``/home/user/ext`` always), an old
workspace, a ``--forbid`` directory (such as the build session's scratch directory) or a Claude session
directory: ``/tmp/claude-*`` (so neither ``/tmp`` nor ``/`` is a root), ``~/.claude``, the study home's
``.claude`` and ``$CLAUDE_CONFIG_DIR`` (:func:`session_dirs`); nor may it lie in a directory named ``.claude``,
hold one directly, or lie inside another workspace. A refused build removes the workspace, and the directories
it created for the root while they are empty.

No text written into the workspace (the instruction, every role input, the wrappers and the
manifest) may name an absolute path outside the workspace (:func:`outside_paths`): the
controlled sessions' first prompts and transcripts name their own old workspace.
``--allow-outside-paths`` keeps such paths, but only if none of them exists, nor the directory
holding it below the top level (:func:`exists_near`); the old-workspace paths that a recorded
substitution names in the manifest must not exist either. The copied tests and the harness docs
are code that runs in the grading container: they may name its paths (``/tmp/...``,
``/mnt/candidate``) on the same condition, without ``--allow-outside-paths``, and never a Claude session
directory; the manifest lists them (``inputs.container_paths``). A path they name that exists (a generator
may have written its own workspace's path into a test) refuses the build, unless
``--allow-existing-paths-in-copies`` is given: it keeps such paths, listed under
``inputs.existing_container_paths``, except a path in or around a location that a root may not lie in or
around (the repository, sealed material, the third-party data, an old workspace, a ``--forbid`` directory, a
Claude session directory). The copies are kept byte for byte: they are the tests of a task verifier.

The manifest is printed as JSON, with the workspace's path; keep it with the private run
record. Model identifiers have no place in the workspace or the manifest.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import tracecontract
from tracecontract import roots
from tracecontract.contract import render_instruction
from tracecontract.controlled import RUN_PYTHON_SH, RUN_TESTS_SH
from tracecontract.ingest.github_pr import SOURCE_FORMAT as PR_SOURCE_FORMAT
from tracecontract.patches import diff_dirs, filter_patch
from tracecontract.schemas import (
    Candidate,
    CandidateOrigin,
    EventKind,
    Population,
    Session,
    Snapshot,
    Split,
    TaskContract,
    TaskManifest,
)
from tracecontract.snapshot import manifest
from tracecontract.store import load
from tracecontract.tasks import render_session, session_for_task, verify_snapshot
from tracecontract.verifier import hash_test_dir

REPO = Path(__file__).resolve().parents[1]
TOOL = "scripts/make_agent_workspace.py"
STUDY_HOME = Path("/home/user")  # the build environment's home, where the study's material lives
FORBIDDEN_DIRS = ("tasks", "results", "docs", "data", "paper")  # under the repository root
DEFAULT_SEALED = tuple(dict.fromkeys((STUDY_HOME / ".tc_sealed", Path.home() / ".tc_sealed")))
DEFAULT_EXTERNAL = (STUDY_HOME / "ext",)  # third-party data (decision log D47)
OLD_WORKSPACES = (STUDY_HOME / "cs_workspaces", STUDY_HOME / "gen_workspaces")  # sealed and removed (D50)
VARIANTS = ("u1", "final")
FINAL_JOINER = "Later in the session the user added:"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*")
_SHELL_SAFE = re.compile(r"[A-Za-z0-9._/-]+")
_PYTHONPATH = re.compile(r"[A-Za-z0-9._/:-]+")
_EMPTY = hashlib.sha256(b"").hexdigest()  # an empty file carries no material
_ABS_PATH = re.compile(r"(?<![\w.~:/-])/[\w.@%+=,-]+(?:/[\w.@%+=,-]+)*")
# Generic system locations that hold no study material: a path under one of them is not an outside path.
# The bare /tmp is not either, but a path under /tmp is (the build session's scratch directory is there).
_SYSTEM = ("/dev", "/proc", "/sys", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/etc")
# Where the Claude harness keeps session directories; no workspace lies there or around them, and no text may name one.
_SESSION_TMP = "/tmp/claude-"
_SESSION_HOMES = (Path.home() / ".claude", STUDY_HOME / ".claude")  # configuration and session records
# A line of an agent-only event (the PR body, a commit message) at least this long, whitespace collapsed, is distinctive
# enough to count as that event's text in a workspace text; shorter ones ("Initial plan") are not.
MIN_LEAK = 40
# The neutral name of the k-th held-out candidate in a checker workspace (checker_labels).
CHECKER_LABEL = "candidate-{k}"
_GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "dev",
            "GIT_AUTHOR_EMAIL": "dev@localhost", "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@localhost",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"}
# The caller's variables that git may see; every other variable, and every GIT_* variable, is dropped.
_ENV_PASS = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")
_PROBE = ("import os, socket, sys\n"
          "print('python', *sys.version_info[:2])\n"
          "try:\n    open('/repo/.tc_wrapper_probe', 'w')\n    print('repo writable')\n"
          "except OSError:\n    print('repo read-only')\n"
          "try:\n    socket.create_connection(('1.1.1.1', 53), timeout=3)\n    print('network')\n"
          "except OSError:\n    print('no network')\n"
          "print('entries', len(os.listdir('/repo')))\n")


@dataclass(frozen=True)
class Role:
    """What one role may read besides the base snapshot and its instruction.

    The first four fields are those of the controlled roles; the others have the controlled roles' behaviour as their
    defaults, so a role that leaves them alone builds what it built before.
    """

    contract: str | None = None  # the contract variant it reads
    reference_diff: bool = False  # the graded part of the reference diff
    session: str | None = None  # "full": the rendered session; "first_prompt": its first user request
    note: str = ""
    repo: bool = True  # repo/: a copy of the base snapshot
    wrappers: str = "both"  # what --image writes: "both" wrappers, "run_python" only, or "none" (--image refused)
    harness_docs: bool = False  # harness/: the harness API, the lint rules and the example tests
    session_events: str | None = None  # session_events.json: what the variant's proposer is shown
    addressing_diff: bool = False  # addressing.diff: the graded change from the pre-review state to the reference
    contracts: tuple[str, ...] = ()  # contracts/<variant>.json (the mapper)
    tests: str = "no"  # --tests-from: "no", "optional" or "required"
    tests_verifiers: tuple[str, ...] = ()  # the task verifiers whose tests/ --tests-from may copy
    candidates: str | None = None  # "dev": --dev-candidates as devcands/<id>.patch; "eval": --candidates as candidates/
    instruction: str = "auto"  # "auto": rendered from the contract, else --instruction required; or "optional"

    def instruction_rule(self) -> str:
        """``contract`` (rendered from the role's contract; ``--instruction`` replaces it), ``required`` or
        ``optional`` (an instruction.md only from ``--instruction``)."""
        if self.instruction != "auto":
            return self.instruction
        return "contract" if self.contract else "required"


ROLES: dict[str, Role] = {
    "fresh": Role(note="fresh-agent attempt (protocol §15.4, §16.2): the instruction only (--variant u1|final, or a file)"),
    "testgen-initial": Role("initial_only", True, note="C1/C2 test generator (§4)"),
    "testgen-full": Role("full_session", True, note="C3/C4 test generator (§4)"),
    "freeform": Role(None, True, "full", note="B2 test generator: the whole session (§4)"),
    "diff-derived": Role(None, True, "first_prompt", note="B3 test generator: the initial request and the reference diff (§15.6)"),
    "attack-initial": Role("initial_only", True, note="development attacks on the initial-only verifiers (audit:v1)"),
    "attack-full": Role("full_session", True, note="development attacks on the correction-aware verifiers (audit:v1)"),
    "alt-initial": Role("initial_only", note="development valid alternative from the initial-only contract"),
    "alt-full": Role("full_session", note="development valid alternative from the full-session contract"),
    "alternative": Role("reference", note="held-out valid alternative (§5): no reference diff"),
    "near-miss": Role("reference", True, note="held-out near miss (§5); natural task: run_python.sh only (not enforced: "
                                              "python -m pytest runs through it; the audit shows what ran)"),
    "refcheck": Role("reference", True, note="reference-check writer (§5)"),
    "labeler": Role("reference", note="independent labeler (§15.5): no reference diff; natural task: harness docs"),
}
# The natural arm's roles (protocol §15.5, §15.6, §19): for natural PR-review tasks only.
NATURAL_ROLES: dict[str, Role] = {
    "contract-initial": Role(session="first_prompt", session_events="initial_only", repo=False, wrappers="none",
                             instruction="optional", note="initial-only contract proposer: the issue and its events; no repo"),
    "contract-full": Role(session="full", session_events="full_session", repo=False, wrappers="none", instruction="optional",
                          note="full-session contract proposer: the rendered thread and its events; no repo"),
    "refcontract": Role(reference_diff=True, session="full", session_events="reference", addressing_diff=True, repo=False,
                        wrappers="none", instruction="optional",
                        note="reference-contract drafter: thread, reference and addressing diffs, events; no repo"),
    "reviser-initial": Role("initial_only", True, tests="required", tests_verifiers=("initial_audited",), candidates="dev",
                            note="reviser of C2: its tests (--tests-from), dev candidates' patches (--dev-candidates)"),
    "reviser-full": Role("full_session", True, tests="required", tests_verifiers=("full_audited",), candidates="dev",
                         note="reviser of C4: its tests (--tests-from), dev candidates' patches (--dev-candidates)"),
    "refcheck-review": Role("reference", True, tests="required", tests_verifiers=("reference_check",),
                            note="reviewer and fixer of the reference checks (--tests-from)"),
    "mapper": Role(contracts=("initial_only", "full_session", "reference"), repo=False, wrappers="none",
                   instruction="optional", note="requirement mapper: the three contracts only; no repo, no code"),
    "checker": Role("reference", True, candidates="eval",
                    note="construction checker (advisory): held-out candidates' patches (--candidates), by neutral label"),
}
# How the controlled roles differ on a natural PR-review task (see the module docstring).
NATURAL_CHANGES: dict[str, dict[str, Any]] = {
    "near-miss": {"wrappers": "run_python"},
    "labeler": {"harness_docs": True, "tests": "optional", "tests_verifiers": ("independent_label",)},
    "freeform": {"instruction": "optional"},
    "diff-derived": {"instruction": "optional"},
}
_FILES = {"contract": "contract.json", "reference_diff": "reference.diff", "full": "session.txt",
          "first_prompt": "session_first_prompt.txt", "session_events": "session_events.json",
          "addressing_diff": "addressing.diff"}
_WRAPPERS = (("run_tests.sh", RUN_TESTS_SH), ("run_python.sh", RUN_PYTHON_SH))
_WRAPPER_SETS = {"both": ("run_tests.sh", "run_python.sh"), "run_python": ("run_python.sh",), "none": ()}
_CANDIDATE_DIRS = {"dev": "devcands", "eval": "candidates"}
# The harness docs of a natural labeler (D55: the harness API, the lint rules and the synthetic example of the test
# format): the public API of the harness module, the lint code of the verifier module, and the FX-01 example tests.
HARNESS_DIR = "harness"
HARNESS_API_FILE = f"{HARNESS_DIR}/tc_sandbox_api.py"
LINT_RULES_FILE = f"{HARNESS_DIR}/lint_rules.py"
EXAMPLE_TESTS_DIR = f"{HARNESS_DIR}/example_tests"
HARNESS_API = ("CallResult", "run_python", "CmdResult", "run_cmd")
LINT_RULES = ("ALLOWED_IMPORTS", "FORBIDDEN_PATH_PREFIXES", "discover_checks", "LintIssue", "_is_parametrize",
              "lint_process_separated", "_only_ok_check")
_PACKAGE = Path(tracecontract.__file__).resolve().parent
HARNESS_MODULE = _PACKAGE / "sandbox" / "harness" / "tc_sandbox.py"
VERIFIER_MODULE = _PACKAGE / "verifier.py"
EXAMPLE_TESTS = REPO / "tests" / "fixtures" / "harbor_fx01" / "tasks" / "FX-01" / "verifiers" / "v1" / "tests"
_API_HEADER = ("# The harness API of verifier tests: an excerpt of the grading harness module tc_sandbox, which a test\n"
               "# imports as `from tc_sandbox import run_python, run_cmd` (the grader provides the module).\n"
               "# Copied verbatim: the module's docstring and its public API (CallResult, run_python, CmdResult, run_cmd).\n"
               "# The trusted internals these call are left out, so this file is documentation; it does not run.\n")
_LINT_HEADER = ("# The lint rules that every verifier test file must pass (`tracecontract lint-tests <tests dir>`): an\n"
                "# excerpt of the study's verifier module, copied verbatim (its docstring and the lint code).\n"
                "# Documentation; it does not run on its own.\n")


class WorkspaceError(RuntimeError):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def role_for(name: str, population: Population) -> Role:
    """The role ``name`` as it applies to a task of ``population`` (see the module docstring)."""
    if name in NATURAL_ROLES:
        if population != Population.natural_pr_review:
            raise WorkspaceError(f"role {name} is a role of the natural arm: for natural PR-review tasks only, not "
                                 f"{population.value}")
        return NATURAL_ROLES[name]
    if name not in ROLES:
        raise WorkspaceError(f"unknown role {name!r}; one of {sorted(ROLES | NATURAL_ROLES)}")
    if population == Population.natural_pr_review and name in NATURAL_CHANGES:
        return dataclasses.replace(ROLES[name], **NATURAL_CHANGES[name])
    return ROLES[name]


def git_env() -> dict[str, str]:
    """The environment of every git call: the allowlisted variables of the caller, then the fixed GIT_* ones."""
    return {**{k: os.environ[k] for k in _ENV_PASS if k in os.environ}, **_GIT_ENV}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env=git_env()).stdout


def _is_workspace(d: Path) -> bool:
    """Whether ``d`` is a workspace made by this tool (its manifest names the tool)."""
    try:
        return json.loads((d / "manifest.json").read_text(encoding="utf-8")).get("tool") == TOOL
    except (OSError, ValueError, AttributeError):
        return False


def _subdirs(d: Path) -> list[Path]:
    """The directories directly in ``d`` (no symlinks), sorted; none if ``d`` cannot be listed."""
    try:
        return sorted(x for x in d.iterdir() if x.is_dir() and not x.is_symlink())
    except OSError:
        return []


def outside_paths(text: str, ws: Path) -> list[str]:
    """The absolute paths that ``text`` names outside the workspace ``ws``, normalised.

    A path counts if its first component is a real top-level entry of this host, and it is neither the
    bare ``/`` or ``/tmp`` nor under a generic system location (``/usr``, ``/dev``, ``/proc`` ...). Tokens
    that are no path on this host do not count: the sandbox's ``/repo``, a closing tag such as
    ``</tool_use_error>``, a sed script, ``seek(0)/write``.
    """
    top = set(os.listdir("/"))
    out = set()
    for tok in _ABS_PATH.findall(text):
        p = os.path.normpath(tok.rstrip(".,:;"))
        first = p.lstrip("/").split("/", 1)[0]
        if not first or first not in top or p == "/tmp" or _inside(Path(p), ws) \
                or any(p == s or p.startswith(s + "/") for s in _SYSTEM):
            continue
        out.add(p)
    return sorted(out)


def exists_near(p: str) -> bool:
    """Whether a named outside path, or the directory holding it unless that is ``/`` or a top-level directory such
    as ``/tmp``, exists on this host: an agent pointed there would find what is beside it."""
    parent = os.path.dirname(p)
    return os.path.lexists(p) or (parent.count("/") > 1 and os.path.lexists(parent))


def old_workspace(m: TaskManifest, repo_root: Path) -> tuple[str, str]:
    """(old workspace, old repository checkout) of a controlled session: the workspace its scenario recorded."""
    scen = repo_root / "data" / m.population.value / "scenarios" / f"{m.task_id}.json"
    try:
        checkout = json.loads(scen.read_text(encoding="utf-8"))["workspace"]
    except (OSError, ValueError, KeyError, TypeError):
        raise WorkspaceError(f"{m.task_id}: no recorded session workspace in {scen}") from None
    if not isinstance(checkout, str) or not checkout.startswith("/"):
        raise WorkspaceError(f"{m.task_id}: the recorded session workspace is not an absolute path")
    checkout = os.path.normpath(checkout)
    return os.path.dirname(checkout), checkout


def substitute_paths(text: str, old_root: str, old_checkout: str, ws: Path) -> tuple[str, list[dict]]:
    """Protocol v0.8 §16.2: ``text`` with each absolute path of the old workspace replaced by the corresponding path of
    the attempt workspace ``ws``, and one record per distinct substitution (``from``, ``to`` relative to ``ws`` with
    ``.`` for ``ws`` itself, ``count``).

    The old workspace corresponds to ``ws``, its checkout (and any path under it) to ``ws/repo``, and its
    ``run_tests.sh`` and ``run_python.sh`` to those of ``ws``. Any other path under the old workspace has no
    corresponding path and is refused, and so is any trace of the old workspace the substitution could not place.
    """
    fixed = {old_root: ws, old_checkout: ws / "repo", f"{old_root}/run_tests.sh": ws / "run_tests.sh",
             f"{old_root}/run_python.sh": ws / "run_python.sh"}
    counts: dict[tuple[str, str], int] = {}

    def sub(m: re.Match[str]) -> str:
        tok = m.group(0)
        core = tok.rstrip(".,:;")
        p = os.path.normpath(core)
        if not (p == old_root or p.startswith(old_root + "/")):
            return tok
        if p in fixed:
            new = fixed[p]
        elif p.startswith(old_checkout + "/"):
            new = ws / "repo" / p[len(old_checkout) + 1:]
        else:
            raise WorkspaceError(f"{p} has no corresponding path in the attempt workspace (protocol §16.2)")
        counts[(core, os.path.relpath(new, ws))] = counts.get((core, os.path.relpath(new, ws)), 0) + 1
        return str(new) + tok[len(core):]

    out = _ABS_PATH.sub(sub, text)
    if old_root in out:
        raise WorkspaceError(f"the old workspace {old_root} is still named after the substitution")
    return out, [{"from": a, "to": b, "count": n} for (a, b), n in counts.items()]


def fresh_instruction(m: TaskManifest, variant: str, old_root: str, old_checkout: str, ws: Path) -> tuple[str, list[dict]]:
    """The §15.4 instruction ``variant`` (``u1``, or ``final`` = U1, the joining line and U2) with the §16.2
    substitutions, and their records by turn."""
    if variant not in VARIANTS:
        raise WorkspaceError(f"unknown variant {variant!r}; one of {list(VARIANTS)}")
    turns = m.scripted_turns[:1 if variant == "u1" else 2]
    if len(turns) < (1 if variant == "u1" else 2):
        raise WorkspaceError(f"{m.task_id} has no scripted turns for variant {variant}")
    texts, records = [], []
    for k, turn in enumerate(turns, 1):
        text, subs = substitute_paths(turn, old_root, old_checkout, ws)
        texts.append(text)
        records += [{"turn": f"U{k}", **s} for s in subs]
    body = texts[0] if variant == "u1" else f"{texts[0]}\n\n{FINAL_JOINER}\n\n{texts[1]}"
    return body + "\n", records


# --------------------------------------------------------------------------- role inputs


@dataclass
class Inputs:
    """What :func:`role_inputs` gives a role: its texts by path in the workspace, and what the manifest records."""

    texts: dict[str, str]  # every text but the copied tests and the harness docs
    container: dict[str, str] = dataclasses.field(default_factory=dict)  # tests and harness docs: code of the container
    copies: set[str] = dataclasses.field(default_factory=set)  # sha256 of the copies the role asked for
    record: dict[str, Any] = dataclasses.field(default_factory=dict)  # manifest "inputs" beyond the controlled keys
    session: Session | None = None  # the task's session: always loaded for a natural PR-review task (agent_only_leaks)


def _contract(task_dir: Path, m: TaskManifest, variant: str) -> TaskContract:
    rel = m.contracts.get(variant)
    if not rel or not (task_dir / rel).is_file():
        raise WorkspaceError(f"{m.task_id} has no {variant} contract (sealed or missing)")
    return load(task_dir / rel, TaskContract)


def _candidates(task_dir: Path, m: TaskManifest) -> list[Candidate]:
    return [load(task_dir / p, Candidate) for p in m.candidates]


def _reference(task_dir: Path, m: TaskManifest) -> Candidate:
    ref = next((c for c in _candidates(task_dir, m) if c.origin == CandidateOrigin.reference), None)
    if ref is None:
        raise WorkspaceError(f"{m.task_id} has no reference candidate")
    return ref


def mapper_contract(c: TaskContract, order: dict[str, int]) -> str:
    """A contract as the mapper reads it (``contracts/<variant>.json``): every requirement, with what the mapping needs
    (id, kind, status, the scored and subjective flags, statement, observable, the supersession and conflict links,
    rationale, the user turn that introduced it, and its quotes from user turns, by turn). ``order`` numbers the
    session's user turns from 1. It is a derived record, never the stored contract file (which also holds the
    record of the run that proposed it)."""
    reqs = [{"req_id": r.req_id, "kind": r.kind.value, "status": r.status.value, "scored": r.scored,
             "subjective": r.subjective, "statement": r.statement, "observable": r.observable,
             "supersedes": r.supersedes, "superseded_by": r.superseded_by, "conflicts_with": r.conflicts_with,
             "rationale": r.rationale, "introduced_in_user_turn": order.get(r.introduced_at),
             "evidence": [{"user_turn": order[e.event_id], "quote": e.quote} for e in r.evidence if e.event_id in order]}
            for r in c.requirements]
    return json.dumps({"variant": c.variant.value, "requirements": reqs}, indent=2) + "\n"


def _materialize(snapshot: Path, patch: str, dest: Path) -> None:
    """``dest``: a copy of the base snapshot with ``patch`` applied by ``git apply`` in a repository of its own (the
    allowlisted git environment, so no caller's ``GIT_*`` variable redirects it), without that repository."""
    shutil.copytree(snapshot, dest, symlinks=True)
    if not patch.strip():
        return
    if (dest / ".git").exists():
        raise WorkspaceError(f"the base snapshot {snapshot} holds a .git entry")
    pfile = dest.parent / f"{dest.name}.diff"
    pfile.write_text(patch, encoding="utf-8")
    _git(dest, "init", "-q", "--template=")
    _git(dest, "apply", "--whitespace=nowarn", str(pfile))
    shutil.rmtree(dest / ".git")


def addressing_diff(task_dir: Path, m: TaskManifest, snapshot: Path) -> tuple[str, dict[str, Any]]:
    """The graded part of the change from the pre-review state to the reference:
    ``filter_patch(diff_dirs(base + pre-review, base + reference))``, and its record (the two states, by origin and
    patch sha256, and the number of protected files removed; the pre-review state's id is held-out, so it is not
    named)."""
    cands = _candidates(task_dir, m)
    ref = _reference(task_dir, m)
    pre = [c for c in cands if c.origin == CandidateOrigin.natural_pre_review]
    if len(pre) != 1:
        raise WorkspaceError(f"{m.task_id} has {len(pre)} natural_pre_review candidates; the addressing diff needs one")
    with tempfile.TemporaryDirectory(prefix="tc_addressing_") as tmp:
        states = {}
        for key, c in (("pre-review", pre[0]), ("reference", ref)):
            states[key] = Path(tmp) / key
            try:
                _materialize(snapshot, c.patch, states[key])
            except subprocess.CalledProcessError as exc:
                raise WorkspaceError(f"{c.candidate_id} does not apply to the base snapshot: "
                                     f"{(exc.stderr or '').strip()[-300:]}") from None
        diff = diff_dirs(states["pre-review"], states["reference"])
    patch, rep = filter_patch(diff)
    return patch, {"from_origin": pre[0].origin.value, "from_patch_sha256": pre[0].patch_sha256, "to": ref.candidate_id,
                   "to_patch_sha256": ref.patch_sha256, "removed_protected": len(rep.removed_protected)}


def in_audit_set(c: Candidate, task_id: str, variant: str) -> bool:
    """Whether the audit set ``v1:<variant>`` selects the development candidate ``c``, as ``tracecontract audit
    --audit-set v1:<variant>`` does (``cli.cmd_audit``): the no-op (its id starts with ``<task>-noop``), the reference,
    or a candidate whose ``produced_by`` holds ``v1:<variant>``."""
    return (c.candidate_id.startswith(task_id + "-noop") or c.origin == CandidateOrigin.reference
            or f"v1:{variant}" in c.produced_by)


def checker_labels(cands: list[Candidate]) -> list[tuple[str, Candidate]]:
    """The checker's neutral label of each candidate (:data:`CHECKER_LABEL`), numbered from 1 in the order of the
    candidates' patch sha256 (ties by id): an order that says nothing of a candidate's origin or id."""
    ordered = sorted(cands, key=lambda c: (c.patch_sha256, c.candidate_id))
    return [(CHECKER_LABEL.format(k=k), c) for k, c in enumerate(ordered, 1)]


def candidate_patches(task_dir: Path, m: TaskManifest, ids: tuple[str, ...], kind: str,
                      variant: str | None) -> tuple[dict[str, str], dict[str, str]]:
    """The graded part of each named candidate's patch, by its path in the workspace, and the record of the patches.

    ``dev`` (a reviser of ``variant``): development candidates only, and of those only the audit set ``v1:<variant>``
    (:func:`in_audit_set`), as ``devcands/<id>.patch``; the record maps each id to its patch sha256.
    ``eval`` (the checker): held-out candidates only, not the no-op, as ``candidates/<label>.patch`` under the neutral
    labels of :func:`checker_labels`; the record maps each label to the candidate's patch sha256, and names no id.
    """
    if len(set(ids)) != len(ids):
        raise WorkspaceError(f"a candidate is named twice: {sorted(i for i in set(ids) if ids.count(i) > 1)}")
    by_id = {c.candidate_id: c for c in _candidates(task_dir, m)}
    chosen = []
    for cid in ids:
        c = by_id.get(cid)
        if c is None or not _NAME.fullmatch(cid):
            raise WorkspaceError(f"{m.task_id} has no candidate {cid!r}")
        if kind == "dev":
            if c.split != Split.dev:
                raise WorkspaceError(f"{cid} is a held-out candidate (split {c.split.value}): a reviser sees development "
                                     "candidates only")
            if variant is None or not in_audit_set(c, m.task_id, variant):
                raise WorkspaceError(f"{cid} was not built for the {variant} contract: it is not in the audit set "
                                     f"v1:{variant} (the no-op, the reference, and the candidates whose produced_by holds "
                                     f"v1:{variant}), and a reviser sees its own variant's audit set only")
        else:
            if c.split != Split.eval:
                raise WorkspaceError(f"{cid} is a development candidate (split {c.split.value}): the checker checks "
                                     "held-out candidates only")
            if c.origin == CandidateOrigin.noop:
                raise WorkspaceError(f"{cid} is the no-op: it has no change to check")
        chosen.append(c)
    named = [(c.candidate_id, c) for c in chosen] if kind == "dev" else checker_labels(chosen)
    texts = {f"{_CANDIDATE_DIRS[kind]}/{name}.patch": filter_patch(c.patch)[0] for name, c in named}
    return texts, {name: c.patch_sha256 for name, c in named}


def checker_label_map(task_dir: Path, ids: tuple[str, ...]) -> dict[str, str]:
    """label -> candidate id for a checker workspace built with ``--candidates ids`` (what the host needs to read the
    checker's verdicts; it is printed with the manifest and never written into the workspace)."""
    m = load(task_dir / "task.json", TaskManifest)
    by_id = {c.candidate_id: c for c in _candidates(task_dir, m)}
    return {label: c.candidate_id for label, c in checker_labels([by_id[i] for i in ids])}


def copy_tests(src: Path, task_dir: Path, verifiers: tuple[str, ...]) -> tuple[dict[str, str], dict[str, Any]]:
    """The test files of ``src`` (one of the task's ``verifiers/<id>/tests`` for ``id`` in ``verifiers``) by their
    path under ``tests/``, and their record (where from, the directory's content hash, the number of files)."""
    src = src.resolve()
    allowed = {(task_dir / "verifiers" / v / "tests").resolve(): v for v in verifiers}
    if src not in allowed:
        raise WorkspaceError(f"--tests-from must be the task's {' or '.join(f'verifiers/{v}/tests' for v in verifiers)}, "
                             f"not {src}")
    if not src.is_dir():
        raise WorkspaceError(f"--tests-from {src} is not a directory")
    texts: dict[str, str] = {}
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if "__pycache__" in rel.parts:
            continue
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise WorkspaceError(f"--tests-from holds a symlink or special file: {rel.as_posix()}")
        if p.is_file():
            try:
                texts[f"tests/{rel.as_posix()}"] = p.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                raise WorkspaceError(f"--tests-from holds a file that is not UTF-8 text: {rel.as_posix()}") from None
    if not any(PurePosixPath(k).name.startswith("test_") and k.endswith(".py") for k in texts):
        raise WorkspaceError(f"--tests-from {src} holds no test_*.py file")
    return texts, {"from": src.relative_to(task_dir.resolve()).as_posix(), "verifier": allowed[src],
                   "content_sha256": hash_test_dir(src), "n_files": len(texts)}


def _excerpt(path: Path, names: tuple[str, ...], header: str) -> str:
    """``header``, then the module docstring and the source of each top-level definition in ``names`` of the Python
    module ``path``, copied verbatim (decorators included), in that order."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    def segment(node: ast.stmt) -> str:
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        return "".join(lines[start - 1:node.end_lineno]).rstrip("\n")

    found: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.setdefault(node.name, node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for t in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(t, ast.Name):
                    found.setdefault(t.id, node)
    missing = [n for n in names if n not in found]
    if missing:
        raise WorkspaceError(f"{path.name} no longer defines {missing}: the harness docs need updating")
    parts = [header.rstrip("\n")]
    first = tree.body[0] if tree.body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        parts.append(segment(first))
    parts += [segment(found[n]) for n in names]
    return "\n\n\n".join(parts) + "\n"


def harness_docs() -> tuple[dict[str, str], dict[str, Any]]:
    """The harness docs of a natural labeler, by path in the workspace, and their record: the harness API
    (:data:`HARNESS_API_FILE`), the lint rules (:data:`LINT_RULES_FILE`) and the FX-01 example tests
    (:data:`EXAMPLE_TESTS_DIR`), with the sha256 of each source."""
    if not EXAMPLE_TESTS.is_dir():
        raise WorkspaceError(f"the FX-01 example tests are missing ({EXAMPLE_TESTS})")
    texts = {HARNESS_API_FILE: _excerpt(HARNESS_MODULE, HARNESS_API, _API_HEADER),
             LINT_RULES_FILE: _excerpt(VERIFIER_MODULE, LINT_RULES, _LINT_HEADER)}
    for p in sorted(EXAMPLE_TESTS.glob("test_*.py")):
        texts[f"{EXAMPLE_TESTS_DIR}/{p.name}"] = p.read_bytes().decode("utf-8")
    return texts, {"files": sorted(texts), "sources_sha256": {
        "tc_sandbox": _sha(HARNESS_MODULE), "verifier": _sha(VERIFIER_MODULE), "example_tests": hash_test_dir(EXAMPLE_TESTS)}}


def agent_only_events(session: Session) -> list[str]:
    """The ids of the events of a natural PR-review session that no reader is shown: the agent's PR body (unless it
    stands in for a missing issue, which the full thread shows in the issue's place) and every commit message. Empty
    for any other session.

    The thread shows the events that ``metadata["events"]`` names as the initial request, the correction context
    (the hunk), the correction and the replies (``ingest.github_pr.render_pr_thread``); every agent event (a commit is a
    tool call, the PR body an assistant text) and every commit the metadata lists is hidden unless it is one of them.
    """
    if session.source_format != PR_SOURCE_FORMAT:
        return []
    ids = session.metadata.get("events") or {}
    shown = {ids.get(k) for k in ("initial_request", "correction_context", "correction")} | set(ids.get("replies") or [])
    hidden = [*(ids.get("commits") or []), ids.get("agent_description")]
    hidden += [e.event_id for e in session.events if e.kind in (EventKind.tool_call, EventKind.assistant_text)]
    return sorted({i for i in hidden if isinstance(i, str) and i and i not in shown})


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _is_code(path: str) -> bool:
    """Whether a workspace text is code or a diff (the diffs, the candidate patches, the copied tests and the harness
    docs), which may coincide with code an agent-only event quotes; every other text is prose."""
    return path.endswith((".diff", ".patch")) or PurePosixPath(path).parts[0] in ("tests", HARNESS_DIR)


def _strings(obj: Any) -> Iterator[str]:
    """Every string of a JSON value, keys included."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def agent_only_leaks(texts: dict[str, str], session: Session) -> list[str]:
    """Problems with workspace ``texts`` (path -> text) that would show a natural PR-review session's agent-only events
    (:func:`agent_only_events`; none for any other session): a text that names one of them by its id, and a prose text
    (not :func:`_is_code`; a JSON file by its strings) that holds the whole text of one of them, or one of its lines, of
    at least :data:`MIN_LEAK` characters with the whitespace collapsed, unless an event the thread shows holds it too.
    Each problem names the file and the events, never the text."""
    hidden = agent_only_events(session)
    if not hidden:
        return []
    by_id, hidden_set = {e.event_id: e for e in session.events}, set(hidden)
    shown = _collapse("\n".join(e.text or "" for e in session.events if e.event_id not in hidden_set))
    pieces: dict[str, set[str]] = {}  # collapsed piece of an agent-only text -> its events
    for i in hidden:
        text = (by_id[i].text or "") if i in by_id else ""
        for piece in (text, *text.splitlines()):
            p = _collapse(piece)
            if len(p) >= MIN_LEAK and p not in shown:
                pieces.setdefault(p, set()).add(i)
    problems = []
    for f, t in sorted(texts.items()):
        named = [i for i in hidden if i in t]
        if named:
            problems.append(f"{f} names events that no reader of the thread is shown (the PR body or a commit message): "
                            f"{named}")
        if _is_code(f):
            continue
        prose = t
        if f.endswith(".json"):
            try:
                prose = "\n".join(_strings(json.loads(t)))
            except ValueError:
                pass
        prose = _collapse(prose)
        held = sorted({i for p, ev in pieces.items() if p in prose for i in ev})
        if held:
            problems.append(f"{f} holds the text of events that no reader of the thread is shown (the PR body or a "
                            f"commit message): {held}")
    return problems


def heldout_problems(m: TaskManifest, cands: list[Candidate], texts: dict[str, str]) -> list[str]:
    """Problems with workspace ``texts`` (path -> text; the manifest among them) of a natural PR-review task: a file
    name or a text that names a held-out candidate (split ``eval``) of the task. None for any other population."""
    if m.population != Population.natural_pr_review:
        return []
    ids = sorted({c.candidate_id for c in cands if c.split == Split.eval}, key=lambda i: (-len(i), i))
    problems = []
    for f, t in sorted(texts.items()):
        named = [i for i in ids if i in f or i in t]
        if named:
            problems.append(f"{f} names held-out candidates of {m.task_id}: {named}")
    return problems


def role_inputs(task_dir: Path, m: TaskManifest, role: Role, repo_root: Path, *, snapshot: Path | None = None,
                tests_from: Path | None = None, dev_ids: tuple[str, ...] = (), eval_ids: tuple[str, ...] = ()) -> Inputs:
    """The texts of the role's inputs, by path in the workspace, and their record (see the module docstring). The
    session is loaded for a natural PR-review task whatever the role, for the check of every text written
    (:func:`agent_only_leaks`, run once the instruction is known)."""
    texts: dict[str, str] = {}
    try:
        need = role.contract or role.session or role.contracts or role.session_events \
            or m.population == Population.natural_pr_review
        session = session_for_task(task_dir, repo_root) if need else None
    except FileNotFoundError as exc:
        raise WorkspaceError(f"{m.task_id}: session transcript missing ({exc.filename})") from None
    out = Inputs(texts, session=session)
    order = {p.event_id: i + 1 for i, p in enumerate(session.user_prompts())} if session is not None else {}
    if role.contract:
        c = _contract(task_dir, m, role.contract)
        reqs = [{"req_id": r.req_id, "kind": r.kind.value, "statement": r.statement, "observable": r.observable,
                 "introduced_in_user_turn": order.get(r.introduced_at)} for r in c.active() if r.scored]
        texts[_FILES["contract"]] = json.dumps({"variant": c.variant.value, "requirements": reqs}, indent=2) + "\n"
        texts["instruction.md"] = render_instruction(c)
    if role.reference_diff:
        texts[_FILES["reference_diff"]] = filter_patch(_reference(task_dir, m).patch)[0]
    if role.session:
        assert session is not None
        try:
            texts[_FILES[role.session]] = render_session(session, first_prompt_only=role.session == "first_prompt")
        except ValueError as exc:
            raise WorkspaceError(f"{m.task_id}: the session cannot be rendered for this role: {exc}") from None
    if role.session_events:
        assert session is not None
        from tracecontract import tasks

        render = getattr(tasks, "render_session_events", None)
        if render is None:
            raise WorkspaceError("this tree has no tasks.render_session_events, which writes session_events.json")
        try:
            texts[_FILES["session_events"]] = render(session, role.session_events)
        except ValueError as exc:
            raise WorkspaceError(f"{m.task_id}: the {role.session_events} events cannot be rendered: {exc}") from None
        out.record["session_events"] = role.session_events
    if role.addressing_diff:
        assert snapshot is not None
        texts[_FILES["addressing_diff"]], out.record["addressing_diff"] = addressing_diff(task_dir, m, snapshot)
    for v in role.contracts:
        texts[f"contracts/{v}.json"] = mapper_contract(_contract(task_dir, m, v), order)
    if role.contracts:
        out.record["contracts"] = list(role.contracts)
    if role.candidates:
        ids = dev_ids if role.candidates == "dev" else eval_ids
        patches, out.record["dev_candidates" if role.candidates == "dev" else "candidates"] = candidate_patches(
            task_dir, m, ids, role.candidates, role.contract)
        texts.update(patches)
        out.copies |= {_sha_text(t) for t in patches.values()}
    if tests_from is not None:
        tests, out.record["tests"] = copy_tests(tests_from, task_dir, role.tests_verifiers)
        out.container.update(tests)
        out.copies |= {_sha_text(t) for t in tests.values()}
    if role.harness_docs:
        docs, out.record["harness_docs"] = harness_docs()
        out.container.update(docs)
    return out


def _wrapper_pythonpath(candidate_pythonpath: str) -> str:
    """The task's candidate PYTHONPATH with the grader's /work mount replaced by the wrappers' /repo mount."""
    return ":".join("/repo" + e[len("/work"):] if e == "/work" or e.startswith("/work/") else e
                    for e in candidate_pythonpath.split(":") if e)


def _walk(ws: Path):
    """Every path in the workspace except the inside of ``repo/.git``."""
    for dirpath, dirnames, filenames in os.walk(ws):
        d = Path(dirpath)
        if d == ws / "repo":
            dirnames[:] = [x for x in dirnames if x != ".git"]
        for n in dirnames + filenames:
            yield d / n


def _files(root: Path) -> Iterator[Path]:
    """Regular files under ``root`` (no symlinks), without the inside of git directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x != ".git"]
        for n in filenames:
            p = Path(dirpath) / n
            if p.is_file() and not p.is_symlink():
                yield p


def _workspace_files(d: Path) -> Iterator[tuple[Path, set[str]]]:
    """(file, the hashes it may have) for every file of the workspace ``d``: what this tool wrote there, as its manifest
    records it, at that path or any other (an agent's copy of a file it was given is not its work, and a workspace built
    later may be given the same file); any other content is the agent's own work."""
    try:
        written = json.loads((d / "manifest.json").read_text(encoding="utf-8")).get("files", {})
        given = {h for h in written.values() if isinstance(h, str)}
    except (OSError, ValueError, AttributeError):
        given = set()
    for p in sorted(_files(d)):
        yield p, given


@dataclass(frozen=True)
class Forbidden:
    """Where forbidden material lies: whole directories, other workspaces (whose tool-written files may repeat), and
    plain directories beside the new workspace, such as a group of workspaces: their files are forbidden, except
    those of the workspaces they hold, which count as workspaces (``skip``, the new workspace, is left out)."""

    roots: tuple[Path, ...]
    workspaces: tuple[Path, ...] = ()
    groups: tuple[Path, ...] = ()
    skip: Path | None = None

    def files(self) -> Iterator[tuple[Path, set[str]]]:
        """(file, hashes it may have without being forbidden) for every file of forbidden material."""
        for root in self.roots:
            if root.is_dir():
                yield from ((p, set()) for p in sorted(_files(root)))
        for d in self.workspaces:
            yield from _workspace_files(d)
        for g in self.groups:
            yield from self._group_files(g)

    def _group_files(self, g: Path) -> Iterator[tuple[Path, set[str]]]:
        try:
            entries = sorted(g.iterdir())
        except OSError:  # it vanished, or is no directory
            return
        for e in entries:
            if e == self.skip or e.is_symlink() or e.name == ".git":
                continue
            if e.is_dir():
                yield from _workspace_files(e) if _is_workspace(e) else self._group_files(e)
            elif e.is_file():
                yield e, set()


def _holds_workspace(d: Path, depth: int = 2) -> bool:
    """Whether a workspace lies in ``d``, directly or at most ``depth`` levels down."""
    return any(_is_workspace(x) or (depth > 1 and _holds_workspace(x, depth - 1)) for x in _subdirs(d))


def forbidden_for(repo_root: Path, sealed: tuple[Path, ...], *, external: tuple[Path, ...] = DEFAULT_EXTERNAL,
                  old_workspaces: tuple[Path, ...] = OLD_WORKSPACES, root: Path | None = None,
                  ws: Path | None = None, parent: bool = False) -> Forbidden:
    """The forbidden material of a workspace ``ws`` under ``root`` (see the module docstring); ``root`` need not exist.

    Beside ``ws`` lie the directories in ``root`` and, with ``parent`` (the root's parent could itself be a root),
    the directories in the root's parent that are workspaces or hold one (directly or one level further down), however
    many other workspaces or groups exist there."""
    beside: list[Path] = []
    if root is not None:
        beside += [d for d in _subdirs(root) if d != ws]
        if parent and root.parent != root:
            beside += [d for d in _subdirs(root.parent) if d != root and (_is_workspace(d) or _holds_workspace(d))]
    return Forbidden(tuple(repo_root / d for d in FORBIDDEN_DIRS) + tuple(sealed) + tuple(external) + tuple(old_workspaces),
                     tuple(d for d in beside if _is_workspace(d)), tuple(d for d in beside if not _is_workspace(d)), ws)


def _forbidden_hashes(forbidden: Forbidden, allowed: set[str], sizes: set[int]) -> dict[str, str]:
    """sha256 -> one forbidden file with that content, for files of a size in ``sizes`` not also in the base snapshot.

    A file that vanishes while the material is walked (listed, then gone, or its directory gone, before it is read: a
    temporary file that a running S10 resolver renames under the git-ignored ``data/natural/s10_work``, for example) is
    skipped, since there is nothing left to read; every file still there is checked. No directory is left out of the
    walk: ``data/natural`` holds pseudonymised third-party text, and what the S10 work directory holds is not fixed.
    """
    out: dict[str, str] = {}
    for p, ok in forbidden.files():
        try:
            if p.stat().st_size not in sizes:
                continue
            h = _sha(p)
        except (FileNotFoundError, NotADirectoryError):  # it vanished after the listing
            continue
        if h not in allowed and h not in ok and h != _EMPTY:
            out.setdefault(h, str(p))
    return out


def _sandbox_problems(name: str, text: str, ws: Path) -> list[str]:
    """Problems with a wrapper's command: it must be one ``exec docker run`` of an offline, read-only container that
    mounts only the workspace's ``repo/``, read-only, at ``/repo``."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    logical, cur = [], ""
    for ln in lines:
        cur += ln[:-1] + " " if ln.endswith("\\") else ln
        if not ln.endswith("\\"):
            logical.append(cur)
            cur = ""
    if cur or len(logical) != 1:
        return [f"{name} must hold exactly one command"]
    try:
        words = shlex.split(logical[0])
    except ValueError:
        return [f"{name}: its command cannot be parsed"]
    problems = []
    if words[:3] != ["exec", "docker", "run"]:
        problems.append(f"{name} does not exec docker run")
    opts: list[tuple[str, str | None]] = []  # (flag, value) for every option, in either form
    for i, w in enumerate(words):
        if w.startswith("-"):
            flag, eq, value = w.partition("=")
            opts.append((flag, value if eq else (words[i + 1] if i + 1 < len(words) else None)))
    for flag, value in (("--network", "none"), ("--cap-drop", "ALL"), ("--security-opt", "no-new-privileges")):
        if (flag, value) not in opts:
            problems.append(f"{name}: no {flag} {value}")
    if any(f in ("--network", "--net") and v != "none" for f, v in opts):
        problems.append(f"{name}: a network other than none")
    if "--read-only" not in words:
        problems.append(f"{name}: the container is not read-only")
    banned = sorted({f for f, _ in opts if f in ("--privileged", "--pid", "--ipc", "--uts", "--userns", "--cgroupns",
                                                  "--cap-add", "--device", "--volumes-from", "--mount")})
    if banned:
        problems.append(f"{name}: {', '.join(banned)} not allowed")
    if [v for f, v in opts if f in ("-v", "--volume")] != [f"{ws / 'repo'}:/repo:ro"]:
        problems.append(f"{name}: it must mount only the workspace's repo/, read-only, at /repo")
    return problems


def check_wrappers(ws: Path, fmt: dict[str, str], names: tuple[str, ...] | None = None) -> list[str]:
    """Problems with the sandbox wrappers ``names`` (default both): each must be the controlled sessions' template
    (``controlled.RUN_TESTS_SH``, ``RUN_PYTHON_SH``) rendered with ``fmt`` for this workspace, an executable regular
    file whose one command runs the code only in the Docker sandbox (:func:`_sandbox_problems`)."""
    problems = []
    for name, tpl in _WRAPPERS:
        if names is not None and name not in names:
            continue
        p = ws / name
        if p.is_symlink() or not p.is_file():
            problems.append(f"{name} is missing")
            continue
        if not os.access(p, os.X_OK):
            problems.append(f"{name} is not executable")
        text = p.read_text(encoding="utf-8")
        if text != tpl.format(**fmt):
            problems.append(f"{name} is not the controlled sessions' wrapper rendered for this workspace")
        problems += _sandbox_problems(name, text, ws)
    return problems


def smoke_wrappers(ws: Path, timeout: int = 300, names: tuple[str, ...] | None = None) -> list[str]:
    """Run the wrappers ``names`` (default both; Docker): Python runs in the image, ``/repo`` is this workspace's
    ``repo/``, read-only, with no network, and ``run_tests.sh --version`` answers. Problems, or an empty list."""
    names = names if names is not None else _WRAPPER_SETS["both"]
    problems = []
    try:
        if "run_python.sh" in names:
            p = subprocess.run([str(ws / "run_python.sh"), "-c", _PROBE], capture_output=True, text=True, timeout=timeout,
                               stdin=subprocess.DEVNULL, check=False)
            lines = p.stdout.splitlines()
            want = ["repo read-only", "no network", f"entries {len(os.listdir(ws / 'repo'))}"]
            if p.returncode != 0 or len(lines) != 4 or not lines[0].startswith("python 3 ") or lines[1:] != want:
                problems.append(f"run_python.sh: exit {p.returncode}, output {lines[:4]!r}, expected Python 3 and "
                                f"{want!r}; {p.stderr.strip()[-300:]}")
        if "run_tests.sh" in names:
            q = subprocess.run([str(ws / "run_tests.sh"), "--version"], capture_output=True, text=True, timeout=timeout,
                               stdin=subprocess.DEVNULL, check=False)
            if q.returncode != 0:
                problems.append(f"run_tests.sh --version: exit {q.returncode}; {(q.stderr or q.stdout).strip()[-300:]}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"the wrappers did not run: {type(exc).__name__}: {exc}"]
    return problems


def check_workspace(ws: Path, *, expected: set[str], snapshot: Path | None, repo_root: Path, sealed: tuple[Path, ...],
                    forbidden: Forbidden | None = None, permitted: frozenset[str] = frozenset(),
                    wrappers: dict[str, str] | None = None, repo: bool = True, copies: frozenset[str] = frozenset(),
                    wrapper_names: tuple[str, ...] | None = None, existing_ok: frozenset[str] = frozenset()) -> list[str]:
    """Problems with a built workspace (empty when it holds only what its role may see).

    ``forbidden`` defaults to the repository's study directories and ``sealed``; ``permitted`` are the outside
    paths its texts may name (each must not exist, unless it is in ``existing_ok``: the existing paths that
    ``--allow-existing-paths-in-copies`` keeps in the copied tests and harness docs); ``wrappers`` is the rendering of
    the sandbox wrappers, if any (``wrapper_names`` of them, default both). Without ``repo``, the role has no
    ``repo/`` and ``snapshot`` may be None. ``copies`` are the sha256 values of the copies the role asked for, which
    may equal forbidden material.
    """
    forbidden = forbidden or Forbidden(tuple(repo_root / d for d in FORBIDDEN_DIRS) + tuple(sealed))
    problems = []
    top = {p.name for p in ws.iterdir()}
    if top != expected:
        problems.append(f"top level holds {sorted(top)}, expected {sorted(expected)}")
    for p in _walk(ws):
        st = p.lstat()
        if stat.S_ISLNK(st.st_mode):
            problems.append(f"symlink: {p.relative_to(ws)}")
        elif stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
            problems.append(f"hard link: {p.relative_to(ws)}")
        elif not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
            problems.append(f"special file: {p.relative_to(ws)}")
    base: list[tuple[str, str]] = sorted(manifest(snapshot)) if snapshot is not None else []
    if repo:
        assert snapshot is not None
        files = sorted((p.relative_to(ws / "repo").as_posix(), _sha(p)) for p in _walk(ws)
                       if p.is_file() and _inside(p, ws / "repo"))
        if files != base:
            problems.append("repo/ differs from the base snapshot")
        if (ws / "repo" / ".git").is_dir():
            if _git(ws / "repo", "rev-list", "--count", "HEAD").strip() != "1":
                problems.append("repo/ has more than its one base commit")
            tracked = sorted(x for x in _git(ws / "repo", "ls-files", "-z").split("\0") if x)
            if tracked != sorted(path for path, _ in base):
                problems.append("the base commit does not hold exactly the snapshot")
        else:
            problems.append("repo/ is not a git repository")
    own = [p for p in _walk(ws) if p.is_file() and not p.is_symlink() and not _inside(p, ws / "repo")]
    bad = _forbidden_hashes(forbidden, {h for _, h in base} | set(copies), {p.stat().st_size for p in own})
    for p in own:
        if _sha(p) in bad:
            problems.append(f"{p.relative_to(ws)} equals forbidden material ({bad[_sha(p)]})")
    for p in own:
        named = outside_paths(p.read_text(encoding="utf-8", errors="replace"), ws)
        if [x for x in named if x not in permitted]:
            problems.append(f"{p.relative_to(ws)} names paths outside the workspace: {[x for x in named if x not in permitted]}")
        existing = [x for x in named if exists_near(x) and x not in existing_ok]
        if existing:
            problems.append(f"{p.relative_to(ws)} names outside paths that exist: {existing}")
    if wrappers is not None:
        problems += check_wrappers(ws, wrappers, wrapper_names)
    return problems


def session_dirs() -> tuple[Path, ...]:
    """The Claude configuration and session directories that a root may lie neither in nor around, besides every
    ``/tmp/claude-*`` entry: ``~/.claude``, the study home's ``.claude`` and ``$CLAUDE_CONFIG_DIR`` when it is set."""
    extra = os.environ.get("CLAUDE_CONFIG_DIR")
    return tuple(dict.fromkeys(Path(d).resolve() for d in (*_SESSION_HOMES, *((extra,) if extra else ()))))


def _location_rules(repo_root: Path, sealed: tuple[Path, ...], external: tuple[Path, ...],
                    old_workspaces: tuple[Path, ...], forbid: tuple[Path, ...]) -> list[tuple[Path, str]]:
    """(directory, what it is) for every location that a root may lie neither in nor around (Claude session directories
    apart, :func:`_location_refusal`)."""
    return [(repo_root, "the repository"), (REPO, "the repository"), *((s, "sealed material") for s in sealed),
            *((Path(e).resolve(), "third-party data") for e in (*external, *DEFAULT_EXTERNAL)),
            *((Path(o).resolve(), "an old workspace") for o in old_workspaces),
            *((Path(f).resolve(), "a forbidden directory") for f in forbid)]


def _rule_refusal(p: Path, rules: list[tuple[Path, str]]) -> str | None:
    """Why ``p`` lies inside or around a location of ``rules``, or None."""
    for no, why in rules:
        if _inside(p, no) or _inside(no, p):
            return f"inside (or around) {why} ({no})"
    return None


def _in_session_dir(p: Path, sessions: tuple[Path, ...]) -> bool:
    """Whether ``p`` lies inside or around a Claude session directory: ``/tmp/claude-*`` by its prefix (so ``/tmp`` and
    ``/`` are around one), a directory of ``sessions``, a directory named ``.claude`` on its path, or one it holds
    directly."""
    return (str(p).startswith(_SESSION_TMP) or _inside(Path(_SESSION_TMP), p) or ".claude" in p.parts
            or any(_inside(p, s) or _inside(s, p) for s in sessions) or os.path.lexists(p / ".claude"))


def _location_refusal(p: Path, rules: list[tuple[Path, str]], sessions: tuple[Path, ...]) -> str | None:
    """Why ``p`` (an absolute, normalised path) may not be or hold a workspace root, or None: it lies inside or around
    a location of ``rules`` or a Claude session directory (:func:`_in_session_dir`)."""
    why = _rule_refusal(p, rules)
    if why is None and _in_session_dir(p, sessions):
        why = "inside (or around) a Claude session directory"
    return why


def _check_location(root: Path, ws: Path, repo_root: Path, sealed: tuple[Path, ...], external: tuple[Path, ...],
                    old_workspaces: tuple[Path, ...], forbid: tuple[Path, ...], *,
                    sessions: tuple[Path, ...] | None = None) -> None:
    """Refuse a root (and so a workspace) inside or around the repository, sealed material, the third-party data, an
    old workspace, a forbidden directory or a Claude session directory (``sessions``, default :func:`session_dirs`),
    and a workspace inside another workspace. It only reads: nothing is created."""
    rules = _location_rules(repo_root, sealed, external, old_workspaces, forbid)
    sessions = session_dirs() if sessions is None else tuple(Path(s).resolve() for s in sessions)
    for p, what in ((root, "the root"), (ws, "the workspace")):
        why = _location_refusal(p, rules, sessions)
        if why:
            raise WorkspaceError(f"{what} {p} would lie {why}")
    if any(_is_workspace(a) for a in ws.parents):
        raise WorkspaceError(f"{ws} would lie inside another workspace")


def _missing_dirs(d: Path) -> list[Path]:
    """``d`` and those of its ancestors that do not exist yet, deepest first."""
    out = []
    while not os.path.lexists(d) and d.parent != d:
        out.append(d)
        d = d.parent
    return out


def _remove_if_empty(dirs: list[Path]) -> None:
    """Remove the directories ``dirs`` (deepest first) while they are empty: those a refused build created."""
    for d in dirs:
        try:
            d.rmdir()
        except OSError:
            break


def _check_options(r: Role, role: str, *, image: str | None, tests_from: Path | None, dev_candidates: tuple[str, ...],
                   candidates: tuple[str, ...], run_python_only: bool = False, variant: str | None = None) -> None:
    """Refuse an option the role does not take, and a missing one it needs."""
    if image is not None and r.wrappers == "none":
        raise WorkspaceError(f"role {role} runs no code: it has no sandbox wrappers, so give no --image")
    if run_python_only and (image is None or variant is not None):
        raise WorkspaceError("--run-python-only narrows the wrappers that --image writes, and a --variant instruction "
                             "names both: give --image and no --variant")
    if tests_from is not None and r.tests == "no":
        raise WorkspaceError(f"role {role} takes no --tests-from")
    if tests_from is None and r.tests == "required":
        raise WorkspaceError(f"role {role} needs --tests-from (the tests of {' or '.join(r.tests_verifiers)})")
    for given, kind, flag in ((dev_candidates, "dev", "--dev-candidates"), (candidates, "eval", "--candidates")):
        if given and r.candidates != kind:
            raise WorkspaceError(f"role {role} takes no {flag}")
        if not given and r.candidates == kind:
            raise WorkspaceError(f"role {role} needs {flag}")


def make_workspace(task_dir: Path, root: Path, *, role: str, name: str, instruction: Path | None = None,
                   variant: str | None = None, repo_root: Path = REPO, snapshot_root: Path | None = None,
                   image: str | None = None, pythonpath: str | None = None, pytest_args: str = "",
                   sealed: tuple[Path, ...] = DEFAULT_SEALED, external: tuple[Path, ...] = DEFAULT_EXTERNAL,
                   old_workspaces: tuple[Path, ...] = OLD_WORKSPACES, forbid: tuple[Path, ...] = (),
                   allow_outside_paths: bool = False, smoke: bool = False, tests_from: Path | None = None,
                   dev_candidates: tuple[str, ...] = (), candidates: tuple[str, ...] = (), run_python_only: bool = False,
                   allow_existing_paths_in_copies: bool = False) -> dict:
    """Build the workspace ``root/name`` for one agent in ``role``; return its manifest (see the module docstring)."""
    if role not in ROLES and role not in NATURAL_ROLES:
        raise WorkspaceError(f"unknown role {role!r}; one of {sorted(ROLES | NATURAL_ROLES)}")
    if not _NAME.fullmatch(name):
        raise WorkspaceError(f"workspace name {name!r} must match {_NAME.pattern}")
    if variant is not None and (role != "fresh" or instruction is not None or image is None):
        raise WorkspaceError("--variant builds a fresh attempt's instruction: role fresh, no --instruction, and --image "
                             "for the wrappers that the instruction names")
    task_dir, repo_root = task_dir.resolve(), repo_root.resolve()
    sealed = tuple(Path(s).resolve() for s in sealed if Path(s).is_dir())
    root = root.resolve()
    ws = root / name
    _check_location(root, ws, repo_root, sealed, external, old_workspaces, forbid)
    rules, sessions = _location_rules(repo_root, sealed, external, old_workspaces, forbid), session_dirs()
    if image is not None and (not _IMAGE.fullmatch(image) or not _SHELL_SAFE.fullmatch(str(ws))
                              or (pythonpath is not None and not _PYTHONPATH.fullmatch(pythonpath))):
        raise WorkspaceError("the wrappers need a plain image tag, PYTHONPATH and workspace path (no shell metacharacters)")
    m = load(task_dir / "task.json", TaskManifest)
    r = role_for(role, m.population)
    _check_options(r, role, image=image, tests_from=tests_from, dev_candidates=tuple(dev_candidates),
                   candidates=tuple(candidates), run_python_only=run_python_only, variant=variant)
    natural = m.population == Population.natural_pr_review
    cands = _candidates(task_dir, m) if natural else []
    snapshot = None
    if r.repo or r.addressing_diff:
        try:
            snapshot_root = (snapshot_root or roots.snapshot_root(task_dir, repo=repo_root)).resolve()
        except roots.RootError as exc:
            raise WorkspaceError(str(exc)) from None
        snapshot = snapshot_root / m.task_id
        if not snapshot.is_dir() or not verify_snapshot(task_dir, snapshot_root):
            raise WorkspaceError(f"base snapshot {snapshot} missing or different from its recorded manifest")
        odd = [p for p in snapshot.rglob("*") if p.is_symlink() or not (p.is_file() or p.is_dir())]
        if odd:
            raise WorkspaceError(f"base snapshot holds symlinks or special files: {[str(p) for p in odd[:5]]}")
    got = role_inputs(task_dir, m, r, repo_root, snapshot=snapshot, tests_from=tests_from, dev_ids=tuple(dev_candidates),
                      eval_ids=tuple(candidates))
    inputs = got.texts
    subs: list[dict] = []
    rule = r.instruction_rule()
    if instruction is not None:
        inputs["instruction.md"] = instruction.read_text(encoding="utf-8")
    elif variant is not None:
        old_root, old_checkout = old_workspace(m, repo_root)
        inputs["instruction.md"], subs = fresh_instruction(m, variant, old_root, old_checkout, ws)
        alive = sorted({s["from"] for s in subs if exists_near(s["from"])})
        if alive:
            raise WorkspaceError(f"the session's old workspace still exists ({alive}); it must be sealed first (D50)")
    if (rule != "optional" or "instruction.md" in inputs) and not inputs.get("instruction.md", "").strip():
        raise WorkspaceError(f"role {role} needs an instruction (--instruction{' or --variant' if role == 'fresh' else ''})")
    every = {**inputs, **got.container}  # every text written into the workspace but the wrappers and the manifest
    leaks = (agent_only_leaks(every, got.session) if got.session is not None else []) + heldout_problems(m, cands, every)
    if leaks:
        raise WorkspaceError("; ".join(leaks))
    named = {f: outside_paths(t, ws) for f, t in inputs.items()}
    outside = sorted({p for ps in named.values() for p in ps})
    where = "; ".join(f"{f}: {ps}" for f, ps in named.items() if ps)
    if outside and not allow_outside_paths:
        raise WorkspaceError(f"the workspace's texts name paths outside the workspace ({where}); --allow-outside-paths "
                             "keeps them if none exists")
    existing = [p for p in outside if exists_near(p)]
    if existing:
        raise WorkspaceError(f"the workspace's texts name outside paths that exist, or whose directory exists: {existing} "
                             f"({where})")
    in_container = {f: outside_paths(t, ws) for f, t in got.container.items()}
    container_paths = sorted({p for ps in in_container.values() for p in ps})
    in_copies = "; ".join(f"{f}: {ps}" for f, ps in in_container.items() if ps)
    session_named = [p for p in container_paths if _in_session_dir(Path(p), sessions)]
    if session_named:
        raise WorkspaceError(f"the copied tests or harness docs name a Claude session directory: {session_named} "
                             f"({in_copies})")
    existing_named = [p for p in container_paths if exists_near(p)]
    kept = [p for p in existing_named if _rule_refusal(Path(p), rules) is None] if allow_existing_paths_in_copies else []
    refused = [p for p in existing_named if p not in kept]
    if refused:
        hint = ("; --allow-existing-paths-in-copies keeps none of these: they lie in or around the repository, sealed "
                "material, the third-party data, an old workspace or a --forbid directory" if allow_existing_paths_in_copies
                else "; --allow-existing-paths-in-copies keeps such paths, except in or around the repository, sealed "
                     "material, the third-party data, an old workspace or a --forbid directory")
        raise WorkspaceError(f"the copied tests or harness docs name outside paths that exist, or whose directory exists: "
                             f"{refused} ({in_copies}){hint}")
    # What lies beside the new workspace, read before anything is created (a root that does not exist yet holds nothing).
    parent_ok = root.parent != root and _location_refusal(root.parent, rules, sessions) is None
    forbidden = forbidden_for(repo_root, sealed, external=tuple(Path(e).resolve() for e in external),
                              old_workspaces=tuple(Path(o).resolve() for o in old_workspaces), root=root, ws=ws,
                              parent=parent_ok)
    created = _missing_dirs(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _remove_if_empty(created)
        raise WorkspaceError(f"cannot create the root {root}: {exc}") from None
    try:
        ws.mkdir()
    except FileExistsError:  # then the root existed before: nothing was created
        raise WorkspaceError(f"{ws} exists; a workspace is always new") from None
    except OSError as exc:
        _remove_if_empty(created)
        raise WorkspaceError(f"cannot create {ws}: {exc}") from None
    names = (("run_python.sh",) if run_python_only else _WRAPPER_SETS[r.wrappers]) if image is not None else ()
    try:
        base: dict[str, Any] | None = None
        if r.repo:
            assert snapshot is not None
            shutil.copytree(snapshot, ws / "repo", symlinks=True)
            _git(ws / "repo", "init", "-q", "--template=", "-b", "main")
            _git(ws / "repo", "add", "-A", "-f")
            _git(ws / "repo", "commit", "-q", "--no-verify", "-m", f"base: {m.snapshot_source.commit[:12]}")
            base = {"snapshot_manifest_sha256": load(task_dir / (m.snapshot or "snapshot.json"), Snapshot).file_manifest_sha256,
                    "commit": _git(ws / "repo", "rev-parse", "HEAD").strip(), "n_files": len(manifest(snapshot))}
        for fname, text in inputs.items():
            (ws / fname).parent.mkdir(parents=True, exist_ok=True)
            (ws / fname).write_text(text, encoding="utf-8")
        for fname, text in got.container.items():
            (ws / fname).parent.mkdir(parents=True, exist_ok=True)
            (ws / fname).write_bytes(text.encode("utf-8"))
        if "tests" in got.record and hash_test_dir(ws / "tests") != got.record["tests"]["content_sha256"]:
            raise WorkspaceError("the copy of --tests-from differs from it")
        fmt: dict[str, str] | None = None
        if names:
            assert image is not None
            fmt = {"root": str(ws), "repo": str(ws / "repo"), "image": image,
                   "pythonpath": pythonpath or _wrapper_pythonpath(m.candidate_pythonpath),
                   "extra": " ".join(shlex.quote(x) for x in shlex.split(pytest_args))}
            for fname, tpl in _WRAPPERS:
                if fname in names:
                    (ws / fname).write_text(tpl.format(**fmt), encoding="utf-8")
                    (ws / fname).chmod(0o755)
        (ws / "scratch").mkdir(mode=0o700)
        (ws / "scratch").chmod(0o700)
        smoked = None
        if smoke and fmt is not None:
            trouble = check_wrappers(ws, fmt, names) or smoke_wrappers(ws, names=names)
            if trouble:
                raise WorkspaceError("the sandbox wrappers do not work: " + "; ".join(trouble))
            smoked = "passed"
        given = inputs.get("instruction.md")
        ins: dict[str, Any] = {"contract": r.contract, "reference_diff": r.reference_diff, "session": r.session,
               "instruction_sha256": None if given is None else hashlib.sha256(given.encode("utf-8")).hexdigest(),
               "instruction_from": None if given is None else "file" if instruction is not None else "variant" if variant
               else "contract"}
        if variant:
            ins |= {"variant": variant, "path_substitutions": subs}
        ins |= got.record
        if container_paths:
            ins["container_paths"] = container_paths
        if kept:
            ins["existing_container_paths"] = kept
        wrap: dict[str, Any] | None = None
        if fmt is not None:
            wrap = {"image": image, "pythonpath": fmt["pythonpath"], "pytest_args": fmt["extra"]}
            if names != _WRAPPER_SETS["both"]:
                wrap["scripts"] = list(names)
            if smoked:
                wrap["smoke"] = smoked
        rec = {
            "tool": TOOL, "task_id": m.task_id, "role": role, "name": name,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "inputs": ins,
            "base": base,
            "wrappers": wrap,
            "scratch": "scratch/",
            "files": {p.relative_to(ws).as_posix(): _sha(p) for p in sorted(_walk(ws)) if p.is_file()},
        }
        text = json.dumps(rec, indent=2) + "\n"
        named_heldout = heldout_problems(m, cands, {"manifest.json": text}) + (
            agent_only_leaks({"manifest.json": text}, got.session) if got.session is not None else [])
        if named_heldout:
            raise WorkspaceError("; ".join(named_heldout))
        (ws / "manifest.json").write_text(text, encoding="utf-8")
        expected = {"scratch", "manifest.json", *(PurePosixPath(f).parts[0] for f in (*inputs, *got.container)), *names} \
            | ({"repo"} if r.repo else set())
        permitted = frozenset(outside) | frozenset(s["from"] for s in subs) | frozenset(container_paths)
        problems = check_workspace(ws, expected=expected, snapshot=snapshot, repo_root=repo_root, sealed=sealed,
                                   forbidden=forbidden, permitted=permitted, wrappers=fmt, repo=r.repo,
                                   copies=frozenset(got.copies), wrapper_names=names or None,
                                   existing_ok=frozenset(kept))
        if problems:
            raise WorkspaceError("workspace check failed: " + "; ".join(problems))
    except BaseException:
        shutil.rmtree(ws, ignore_errors=True)
        _remove_if_empty(created)
        raise
    return rec


def main(argv: list[str]) -> int:
    notes = [f"  {k:16} {v.note}" for k, v in ROLES.items()]
    notes += ["natural-arm roles (natural PR-review tasks only):"] + [f"  {k:16} {v.note}" for k, v in NATURAL_ROLES.items()]
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="roles:\n" + "\n".join(notes))
    ap.add_argument("task")
    ap.add_argument("--role", required=True, choices=sorted(ROLES | NATURAL_ROLES))
    ap.add_argument("--root", required=True, help="directory outside the repository that holds the workspaces (it may "
                                                  "be a plain directory grouping workspaces, e.g. one per attack state)")
    ap.add_argument("--name", required=True, help="the new workspace's directory name, e.g. CS-01-fresh-A-u1-1")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--instruction", help="instruction file (required for roles that read no contract, unless --variant "
                                           "or the role needs none)")
    src.add_argument("--variant", choices=VARIANTS, help="fresh role: build the §15.4 instruction u1 or final, with the "
                                                         "§16.2 path substitution (needs --image)")
    ap.add_argument("--image", help="write the sandbox wrappers for this image tag")
    ap.add_argument("--pythonpath", help="PYTHONPATH inside the wrappers' container (default: the task's, under /repo)")
    ap.add_argument("--pytest-args", default="", help="extra pytest arguments for run_tests.sh, e.g. '-o addopts='")
    ap.add_argument("--no-smoke", action="store_true", help="with --image: do not run the wrappers once in Docker")
    ap.add_argument("--run-python-only", action="store_true",
                    help="with --image: write run_python.sh only, no run_tests.sh (for a role whose prompt runs no "
                         "repository tests; it prevents nothing: python -m pytest runs through run_python.sh)")
    ap.add_argument("--tests-from", help="reviser-*, refcheck-review, natural labeler: copy this task verifier's tests "
                                         "directory (verifiers/<id>/tests) into tests/")
    ap.add_argument("--dev-candidates", nargs="+", default=[], metavar="ID",
                    help="reviser-*: development candidates whose graded patches go to devcands/<id>.patch")
    ap.add_argument("--candidates", nargs="+", default=[], metavar="ID",
                    help="checker: held-out candidates whose graded patches go to candidates/candidate-<k>.patch (the "
                         "printed candidate_labels map the labels to the ids)")
    ap.add_argument("--sealed", action="append", help="sealed directory (repeatable; default /home/user/.tc_sealed)")
    ap.add_argument("--forbid", action="append", default=[], help="directory the root may not lie in (repeatable)")
    ap.add_argument("--allow-outside-paths", action="store_true",
                    help="keep absolute paths outside the workspace in its texts, if none of them exists")
    ap.add_argument("--allow-existing-paths-in-copies", action="store_true",
                    help="keep outside paths that exist in the copied tests and harness docs (listed in the manifest), "
                         "except in or around the repository, sealed material, the third-party data, an old workspace, "
                         "a --forbid directory or a Claude session directory")
    ap.add_argument("--repo-root", default=str(REPO), help="the study repository (default: this one)")
    ap.add_argument("--snapshots", help="directory of the base snapshots (default: where the task's population keeps "
                                        "them, tracecontract.roots.snapshot_root: <repo-root>/snapshots, or "
                                        "<repo-root>/data/natural/snapshots for a natural PR-review task)")
    a = ap.parse_args(argv)
    try:
        rec = make_workspace(Path(a.task), Path(a.root), role=a.role, name=a.name,
                             instruction=Path(a.instruction) if a.instruction else None, variant=a.variant,
                             repo_root=Path(a.repo_root), snapshot_root=Path(a.snapshots) if a.snapshots else None,
                             image=a.image, pythonpath=a.pythonpath, pytest_args=a.pytest_args,
                             sealed=tuple(Path(s) for s in a.sealed) if a.sealed else DEFAULT_SEALED,
                             forbid=tuple(Path(f) for f in a.forbid), allow_outside_paths=a.allow_outside_paths,
                             smoke=a.image is not None and not a.no_smoke,
                             tests_from=Path(a.tests_from) if a.tests_from else None,
                             dev_candidates=tuple(a.dev_candidates), candidates=tuple(a.candidates),
                             run_python_only=a.run_python_only,
                             allow_existing_paths_in_copies=a.allow_existing_paths_in_copies)
    except WorkspaceError as exc:
        print(f"make_agent_workspace: {exc}", file=sys.stderr)
        return 1
    out = {"workspace": str(Path(a.root).resolve() / a.name), **rec}
    if a.candidates:  # the checker's labels, for the host only: the workspace names no held-out id
        out["candidate_labels"] = checker_label_map(Path(a.task).resolve(), tuple(a.candidates))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
